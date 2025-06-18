import time
import pickle
from typing import Tuple, Optional, List, Dict, Any
from .disk_manager import DiskManager
from .datastructures import Inode, DirectoryEntry, FileType, Permissions
from .permissions_utils import (
    check_permission, can_access_directory, can_modify_directory, can_delete_file
)

# NOTE: The import of 'delete_file' is moved inside the 'remove_directory' function to prevent circular import.

DEFAULT_DIRECTORY_PERMISSIONS = 0o755


def _read_directory_entries(
    dm: DiskManager, dir_inode_id: int
) -> Optional[List[DirectoryEntry]]:
    dir_inode = dm.get_inode(dir_inode_id)
    if not dir_inode or dir_inode.type != FileType.DIRECTORY:
        print(f"Error: Inode {dir_inode_id} is not a valid directory.")
        return None
    if not dir_inode.data_block_indices:
        return []
    block_id = dir_inode.data_block_indices[0]
    try:
        raw_data = dm.read_block(block_id)
        entries: List[DirectoryEntry] = pickle.loads(raw_data)
        return entries
    except EOFError:
        return []
    except Exception as e:
        print(
            f"Error reading/unpickling directory entries for inode {dir_inode_id} in block {block_id}: {e}"
        )
        return None


def _write_directory_entries(
    dm: DiskManager, dir_inode_id: int, entries: List[DirectoryEntry]
) -> bool:
    dir_inode = dm.get_inode(dir_inode_id)
    if not dir_inode or dir_inode.type != FileType.DIRECTORY:
        return False
    if not dir_inode.data_block_indices:
        # This case should ideally be handled by the caller, e.g., by allocating a block first
        return False
    block_id = dir_inode.data_block_indices[0]
    try:
        serialized_entries = pickle.dumps(entries)
        if len(serialized_entries) > dm.superblock.block_size:
            # Future implementation should handle multi-block directories
            return False
        dm.write_block(block_id, serialized_entries)
        dir_inode.size = len(entries)
        current_timestamp = int(time.time())
        dir_inode.mtime = dir_inode.ctime = dir_inode.atime = current_timestamp
        return True
    except Exception as e:
        print(
            f"Error pickling/writing directory entries for inode {dir_inode_id} in block {block_id}: {e}"
        )
        return False


def _read_symlink_target(dm: DiskManager, symlink_inode: Inode) -> Optional[str]:
    """Helper function: Reads the content (target path) of a symbolic link inode."""
    if symlink_inode.type != FileType.SYMBOLIC_LINK:
        return None
    if not symlink_inode.data_block_indices:
        return ""
    block_id = symlink_inode.data_block_indices[0]
    try:
        raw_data = dm.read_block(block_id)
        target_path_bytes = raw_data[: symlink_inode.size]
        return target_path_bytes.decode("utf-8")
    except Exception as e:
        print(f"Failed to read symbolic link content (inode {symlink_inode.id}): {e}")
        return None


def _resolve_path_to_inode_id(
    dm: DiskManager, current_dir_inode_id: int, root_inode_id: int, path: str
) -> Optional[int]:
    """
    Resolves a path string to its target inode ID, handling symbolic links and preventing loops.
    """
    SYMLINK_MAX_DEPTH = 40

    def resolve_recursive(
        start_inode_id: int, path_components: List[str], depth: int
    ) -> Optional[int]:
        if depth > SYMLINK_MAX_DEPTH:
            print("Error: Too many symbolic links encountered (possible loop).")
            return None

        current_inode_id = start_inode_id

        for i, component in enumerate(path_components):
            current_inode = dm.get_inode(current_inode_id)
            if not current_inode or current_inode.type != FileType.DIRECTORY:
                return None

            entries = _read_directory_entries(dm, current_inode_id)
            if entries is None:
                return None

            found_entry = next((e for e in entries if e.name == component), None)

            if not found_entry:
                return None

            next_inode = dm.get_inode(found_entry.inode_id)
            if not next_inode:
                return None

            # If it's a symlink AND not the last component of the path, resolve it.
            # If it IS the last component, we return the symlink's inode itself, not its target.
            if (
                next_inode.type == FileType.SYMBOLIC_LINK
                and i < len(path_components) - 1
            ):
                target_path_str = _read_symlink_target(dm, next_inode)
                if target_path_str is None:
                    return None

                remaining_components = path_components[i + 1 :]

                if target_path_str.startswith("/"):
                    new_start_node_id = root_inode_id
                    new_components = [
                        c for c in target_path_str.split("/") if c
                    ] + remaining_components
                else:
                    new_start_node_id = current_inode_id
                    new_components = [
                        c for c in target_path_str.split("/") if c
                    ] + remaining_components

                return resolve_recursive(new_start_node_id, new_components, depth + 1)

            current_inode_id = next_inode.id

        return current_inode_id

    if not path:
        return current_dir_inode_id

    start_node_id = root_inode_id if path.startswith("/") else current_dir_inode_id

    # Simplified normalization, mainly handles empty components from slashes
    components = [c for c in path.split("/") if c]
    if not path.startswith("/"):
        # For relative path, components are as is
        pass
    else:
        # For absolute path, already handled by start_node_id
        pass

    return resolve_recursive(start_node_id, components, 0)


def make_directory(
    dm: DiskManager, current_user_uid: int, parent_inode_id: int, new_dir_name: str
) -> Tuple[bool, str, Optional[int]]:
    if not new_dir_name or "/" in new_dir_name or new_dir_name in [".", ".."]:
        return False, f"Error: Invalid directory name '{new_dir_name}'.", None

    parent_inode = dm.get_inode(parent_inode_id)
    if not parent_inode or parent_inode.type != FileType.DIRECTORY:
        return (
            False,
            f"Error: Parent (inode {parent_inode_id}) is not a directory.",
            None,
        )

    if not can_modify_directory(parent_inode, current_user_uid):
        return (
            False,
            f"Error: Permission denied. User {current_user_uid} cannot create directories in parent (inode {parent_inode_id}).",
            None,
        )

    parent_entries = _read_directory_entries(dm, parent_inode_id)
    if parent_entries is None:
        return (
            False,
            f"Error: Could not read entries of parent directory (inode {parent_inode_id}).",
            None,
        )
    if any(entry.name == new_dir_name for entry in parent_entries):
        return (
            False,
            f"Error: Name '{new_dir_name}' already exists in the current directory.",
            None,
        )

    new_inode_id = dm.allocate_inode(uid_for_inode=current_user_uid)
    if new_inode_id is None:
        return False, "Error: No free inodes available.", None

    new_data_block_id = dm.allocate_data_block()
    if new_data_block_id is None:
        dm.free_inode(new_inode_id)
        return False, "Error: No free data blocks available.", None

    current_timestamp = int(time.time())
    new_dir_inode = Inode(
        inode_id=new_inode_id,
        file_type=FileType.DIRECTORY,
        owner_uid=current_user_uid,
        permissions=DEFAULT_DIRECTORY_PERMISSIONS,
    )
    new_dir_inode.data_block_indices.append(new_data_block_id)
    new_dir_inode.blocks_count = 1
    new_dir_inode.link_count = 2
    new_dir_inode.atime = new_dir_inode.mtime = new_dir_inode.ctime = current_timestamp
    dm.inode_table[new_inode_id] = new_dir_inode

    dot_entry = DirectoryEntry(name=".", inode_id=new_inode_id)
    dot_dot_entry = DirectoryEntry(name="..", inode_id=parent_inode_id)
    dir_entries = [dot_entry, dot_dot_entry]
    new_dir_inode.size = len(dir_entries)

    try:
        serialized_entries = pickle.dumps(dir_entries)
        if len(serialized_entries) > dm.superblock.block_size:
            dm.free_data_block(new_data_block_id)
            dm.free_inode(new_inode_id)
            return False, "Error: Directory entries too large for a single block.", None

        dm.write_block(new_data_block_id, serialized_entries)

    except Exception as e:
        dm.free_data_block(new_data_block_id)
        dm.free_inode(new_inode_id)
        return False, f"Error creating directory entries: {e}.", None

    new_entry_for_parent = DirectoryEntry(name=new_dir_name, inode_id=new_inode_id)
    parent_entries.append(new_entry_for_parent)
    if not _write_directory_entries(dm, parent_inode_id, parent_entries):
        dm.free_data_block(new_data_block_id)
        dm.free_inode(new_inode_id)
        return (
            False,
            f"Error: Failed to update parent directory (inode {parent_inode_id}) with new directory entry.",
            None,
        )

    parent_inode.mtime = current_timestamp
    parent_inode.ctime = current_timestamp
    parent_inode.atime = current_timestamp

    return (
        True,
        f"Directory '{new_dir_name}' created successfully (inode {new_inode_id}).",
        new_inode_id,
    )


def remove_directory(
    dm: DiskManager,
    current_user_uid: int,
    parent_inode_id: int,
    dir_name_to_delete: str,
) -> Tuple[bool, str]:
    from .file_ops import delete_file  # Moved import to prevent circular dependency

    if not dir_name_to_delete or dir_name_to_delete in [".", ".."]:
        return False, f"Error: Cannot remove special directory '{dir_name_to_delete}'."

    parent_inode = dm.get_inode(parent_inode_id)
    if not parent_inode or parent_inode.type != FileType.DIRECTORY:
        return False, f"Error: Parent (inode {parent_inode_id}) is not a directory."

    if not can_modify_directory(parent_inode, current_user_uid):
        return (
            False,
            f"Error: Permission denied. User {current_user_uid} cannot delete directories in parent (inode {parent_inode_id}).",
        )

    parent_entries = _read_directory_entries(dm, parent_inode_id)
    if parent_entries is None:
        return (
            False,
            f"Error: Could not read entries of parent directory (inode {parent_inode_id}).",
        )

    dir_entry_to_delete = next(
        (e for e in parent_entries if e.name == dir_name_to_delete), None
    )
    if dir_entry_to_delete is None:
        return (
            False,
            f"Error: Directory '{dir_name_to_delete}' not found in parent directory (inode {parent_inode_id}).",
        )

    target_dir_inode_id = dir_entry_to_delete.inode_id
    target_dir_inode = dm.get_inode(target_dir_inode_id)

    if not target_dir_inode:
        parent_entries.remove(dir_entry_to_delete)
        _write_directory_entries(dm, parent_inode_id, parent_entries)
        return (
            False,
            f"Error: Inode for '{dir_name_to_delete}' not found. Dangling entry removed.",
        )

    if target_dir_inode.type != FileType.DIRECTORY:
        return (
            False,
            f"Error: '{dir_name_to_delete}' is not a directory. Use 'rm' for files.",
        )

    if not can_delete_file(target_dir_inode, current_user_uid):
        return (
            False,
            f"Error: Permission denied. User {current_user_uid} cannot delete directory '{dir_name_to_delete}'.",
        )

    target_dir_entries = _read_directory_entries(dm, target_dir_inode_id)
    if target_dir_entries is None:
        return (
            False,
            f"Error: Could not read entries of directory '{dir_name_to_delete}' for deletion.",
        )

    for entry in list(target_dir_entries):
        if entry.name in [".", ".."]:
            continue

        entry_inode = dm.get_inode(entry.inode_id)
        if not entry_inode:
            continue

        if entry_inode.type == FileType.DIRECTORY:
            success, msg = remove_directory(
                dm, current_user_uid, target_dir_inode_id, entry.name
            )
            if not success:
                return False, f"Failed to delete subdirectory '{entry.name}': {msg}"
        else:
            success, msg = delete_file(
                dm, current_user_uid, target_dir_inode_id, entry.name
            )
            if not success:
                return False, f"Failed to delete file '{entry.name}': {msg}"

    parent_entries_refreshed = _read_directory_entries(dm, parent_inode_id)
    if parent_entries_refreshed is None:
        return (
            False,
            "Critical Error: Could not re-read parent directory after deleting children.",
        )

    final_entry_to_delete = next(
        (e for e in parent_entries_refreshed if e.name == dir_name_to_delete), None
    )
    if final_entry_to_delete:
        parent_entries_refreshed.remove(final_entry_to_delete)
        if not _write_directory_entries(dm, parent_inode_id, parent_entries_refreshed):
            return (
                False,
                f"Error: Failed to update parent directory (inode {parent_inode_id}).",
            )

    parent_inode.link_count -= 1
    current_timestamp = int(time.time())
    parent_inode.mtime = parent_inode.ctime = parent_inode.atime = current_timestamp

    for block_idx in target_dir_inode.data_block_indices:
        dm.free_data_block(block_idx)
    target_dir_inode.data_block_indices.clear()
    target_dir_inode.blocks_count = 0
    target_dir_inode.size = 0
    dm.free_inode(target_dir_inode_id)

    return (
        True,
        f"Directory '{dir_name_to_delete}' and its contents were successfully deleted.",
    )


def list_directory(
    dm: DiskManager, dir_inode_id: int
) -> Tuple[bool, str, Optional[List[Dict[str, Any]]]]:
    target_dir_inode = dm.get_inode(dir_inode_id)
    if not target_dir_inode or target_dir_inode.type != FileType.DIRECTORY:
        return False, f"Error: Inode {dir_inode_id} is not a valid directory.", None

    entries = _read_directory_entries(dm, dir_inode_id)
    if entries is None:
        return (
            False,
            f"Error: Could not read entries for directory (inode {dir_inode_id}).",
            None,
        )

    detailed_entries: List[Dict[str, Any]] = []
    for entry in entries:
        entry_inode = dm.get_inode(entry.inode_id)
        if not entry_inode:
            print(
                f"Warning: Could not find inode {entry.inode_id} for entry '{entry.name}'. Skipping."
            )
            continue
        detailed_entries.append(
            {
                "name": entry.name,
                "inode_id": entry.inode_id,
                "type": entry_inode.type.name,
                "size": entry_inode.size,
                "permissions": entry_inode.permissions,
                "mtime": entry_inode.mtime,
                "link_count": entry_inode.link_count,
                "owner_uid": entry_inode.owner_uid,
            }
        )

    target_dir_inode.atime = int(time.time())
    return (
        True,
        f"Successfully listed directory (inode {dir_inode_id}).",
        detailed_entries,
    )


def change_directory(
    dm: DiskManager, current_cwd_inode_id: int, root_inode_id: int, target_path: str
) -> Tuple[bool, str, Optional[int]]:
    if current_cwd_inode_id is None or root_inode_id is None:
        return False, "Error: CWD or root directory not properly initialized.", None
    new_cwd_inode_id = _resolve_path_to_inode_id(
        dm, current_cwd_inode_id, root_inode_id, target_path
    )
    if new_cwd_inode_id is None:
        return False, f"Error: Path '{target_path}' not found or is invalid.", None
    target_inode = dm.get_inode(new_cwd_inode_id)
    if not target_inode:
        return False, f"Error: Resolved inode {new_cwd_inode_id} does not exist.", None
    if target_inode.type != FileType.DIRECTORY:
        return False, f"Error: Path '{target_path}' is not a directory.", None
    return (
        True,
        f"Current directory changed to inode {new_cwd_inode_id}.",
        new_cwd_inode_id,
    )


def rename_item(
    dm: DiskManager, user_uid: int, parent_inode_id: int, old_name: str, new_name: str
) -> Tuple[bool, str]:
    if not new_name or "/" in new_name or new_name in [".", ".."]:
        return False, f"Error: Invalid new name '{new_name}'."
    if old_name == new_name:
        return True, "New and old names are the same."

    parent_inode = dm.get_inode(parent_inode_id)
    if not parent_inode or parent_inode.type != FileType.DIRECTORY:
        return False, f"Error: Parent (inode {parent_inode_id}) is not a directory."
    if not check_permission(parent_inode, user_uid, Permissions.WRITE):
        return (
            False,
            f"Permission denied: Cannot write to parent directory (inode {parent_inode_id}).",
        )

    entries = _read_directory_entries(dm, parent_inode_id)
    if entries is None:
        return False, f"Error: Could not read parent directory entries."

    entry_to_rename = next((e for e in entries if e.name == old_name), None)
    if entry_to_rename is None:
        return False, f"Error: Item '{old_name}' not found."
    if any(e.name == new_name for e in entries):
        return False, f"Error: Name '{new_name}' already exists."

    target_inode_id = entry_to_rename.inode_id
    entry_to_rename.name = new_name

    if not _write_directory_entries(dm, parent_inode_id, entries):
        entry_to_rename.name = old_name  # Attempt to roll back change in memory
        return False, f"Error: Failed to update parent directory entries."

    current_timestamp = int(time.time())
    parent_inode.mtime = parent_inode.ctime = parent_inode.atime = current_timestamp
    target_inode = dm.get_inode(target_inode_id)
    if target_inode:
        target_inode.ctime = current_timestamp

    return True, f"Item '{old_name}' successfully renamed to '{new_name}'."