import time
import pickle
from typing import Tuple, Optional, List, Dict, Any
from .disk_manager import DiskManager
from .datastructures import Inode, DirectoryEntry, FileType, Permissions
from .permissions_utils import check_permission

# 默认新目录权限 (rwxr-xr-x)
DEFAULT_DIRECTORY_PERMISSIONS = 0o755


def _read_directory_entries(
    dm: DiskManager, dir_inode_id: int
) -> Optional[List[DirectoryEntry]]:
    """
    辅助函数：读取并反序列化目录inode中的目录条目列表。
    """
    dir_inode = dm.get_inode(dir_inode_id)
    if not dir_inode or dir_inode.type != FileType.DIRECTORY:
        print(f"Error: Inode {dir_inode_id} is not a valid directory.")
        return None

    if not dir_inode.data_block_indices:
        # 一个有效目录至少应该有一个数据块给 . 和 ..
        # 但如果允许空目录（除了.和..），那这里返回空列表可能是对的
        # 但在格式化根目录时，我们已经创建了.和..，所以这里可以认为不应为空
        print(f"Warning: Directory inode {dir_inode_id} has no data blocks listed.")
        return []

    # 为简单起见，我们假设目录的所有条目都存储在第一个数据块中。
    # 实际文件系统需要处理跨多个数据块的目录。
    block_id = dir_inode.data_block_indices[0]
    try:
        raw_data = dm.read_block(block_id)
        # pickle.loads 应该能处理末尾的空字节（如果块未填满）
        entries: List[DirectoryEntry] = pickle.loads(raw_data)
        return entries
    except EOFError:  # 文件末尾错误，可能块是空的或pickle数据不完整
        print(
            f"Warning: EOFError while unpickling entries for inode {dir_inode_id}. Block {block_id} might be empty or corrupted."
        )
        return []  # 返回空列表，表示没有成功读取到条目
    except Exception as e:
        print(
            f"Error reading/unpickling directory entries for inode {dir_inode_id} in block {block_id}: {e}"
        )
        return None


def _write_directory_entries(
    dm: DiskManager, dir_inode_id: int, entries: List[DirectoryEntry]
) -> bool:
    """
    辅助函数：序列化目录条目列表并将其写入目录inode的第一个数据块。
    """
    dir_inode = dm.get_inode(dir_inode_id)
    if not dir_inode or dir_inode.type != FileType.DIRECTORY:
        print(
            f"Error: Inode {dir_inode_id} is not a valid directory for writing entries."
        )
        return False

    if not dir_inode.data_block_indices:
        print(
            f"Error: Directory inode {dir_inode_id} has no data blocks allocated to write entries."
        )
        return False  # 目录必须先有分配好的数据块

    # 同样，简化处理，只写入第一个数据块
    block_id = dir_inode.data_block_indices[0]
    try:
        serialized_entries = pickle.dumps(entries)
        if len(serialized_entries) > dm.superblock.block_size:
            # TODO: 未来需要支持目录条目跨多个数据块存储
            print(
                f"Error: Directory entries for inode {dir_inode_id} exceed single block size ({len(serialized_entries)} > {dm.superblock.block_size}). Multi-block directories not yet supported."
            )
            return False

        dm.write_block(block_id, serialized_entries)
        dir_inode.size = len(entries)  # 更新目录大小为条目数量
        current_timestamp = int(time.time())
        dir_inode.mtime = current_timestamp  # 内容修改时间
        dir_inode.atime = current_timestamp  # 访问时间（技术上写也是一种访问）
        # ctime (状态更改时间) 通常在i节点本身被修改时更新，这里修改了size和mtime，也算
        dir_inode.ctime = current_timestamp
        return True
    except Exception as e:
        print(
            f"Error pickling/writing directory entries for inode {dir_inode_id} in block {block_id}: {e}"
        )
        return False


def make_directory(
    dm: DiskManager, current_user_uid: int, parent_inode_id: int, new_dir_name: str
) -> Tuple[bool, str, Optional[int]]:
    """
    在指定的父目录下创建一个新目录。
    Args:
        dm: DiskManager 实例。
        current_user_uid: 当前用户的UID，用于设置新目录的所有者。
        parent_inode_id: 父目录的i节点ID。
        new_dir_name: 新目录的名称。
    Returns:
        Tuple[bool, str, Optional[int]]: (操作是否成功, 消息, 新目录的i节点ID（如果成功）)
    """
    # 1. 基本名称验证
    if not new_dir_name or "/" in new_dir_name or new_dir_name in [".", ".."]:
        return False, f"Error: Invalid directory name '{new_dir_name}'.", None
    if len(new_dir_name) > 255:  # 假设最大文件名长度
        return False, "Error: Directory name too long.", None

    # 2. 获取父目录i节点并检查其有效性
    parent_inode = dm.get_inode(parent_inode_id)
    if not parent_inode:
        return (
            False,
            f"Error: Parent directory (inode {parent_inode_id}) not found.",
            None,
        )
    if parent_inode.type != FileType.DIRECTORY:
        return (
            False,
            f"Error: Parent (inode {parent_inode_id}) is not a directory.",
            None,
        )

    # 3. 检查父目录下是否已存在同名文件/目录
    parent_entries = _read_directory_entries(dm, parent_inode_id)
    if parent_entries is None:  # 读取父目录条目失败
        return (
            False,
            f"Error: Could not read entries of parent directory (inode {parent_inode_id}).",
            None,
        )

    for entry in parent_entries:
        if entry.name == new_dir_name:
            return (
                False,
                f"Error: Directory or file '{new_dir_name}' already exists in parent (inode {parent_inode_id}).",
                None,
            )

    # --- 开始分配资源 ---
    # 4. 为新目录分配i节点
    new_inode_id = dm.allocate_inode(uid_for_inode=current_user_uid)
    if new_inode_id is None:
        return False, "Error: No free inodes available for new directory.", None

    # 5. 为新目录的数据块（用于存储.和..）分配数据块
    new_data_block_id = dm.allocate_data_block()
    if new_data_block_id is None:
        dm.free_inode(new_inode_id)  # 回滚已分配的i节点
        return False, "Error: No free data blocks available for new directory.", None

    # 6. 初始化新目录的i节点
    current_timestamp = int(time.time())
    new_dir_inode = Inode(
        inode_id=new_inode_id,
        file_type=FileType.DIRECTORY,
        owner_uid=current_user_uid,
        permissions=DEFAULT_DIRECTORY_PERMISSIONS,
    )
    new_dir_inode.data_block_indices.append(new_data_block_id)
    new_dir_inode.blocks_count = 1
    new_dir_inode.link_count = 2  # 一个是 "."，另一个是其在父目录中的条目
    new_dir_inode.atime = new_dir_inode.mtime = new_dir_inode.ctime = current_timestamp
    dm.inode_table[new_inode_id] = new_dir_inode
    # 7. 在新目录的数据块中创建 "." 和 ".." 条目
    dot_entry = DirectoryEntry(name=".", inode_id=new_inode_id)
    dot_dot_entry = DirectoryEntry(name="..", inode_id=parent_inode_id)
    new_dir_entries = [dot_entry, dot_dot_entry]

    # 8. 将新目录的条目写入其数据块
    if not _write_directory_entries(dm, new_inode_id, new_dir_entries):
        dm.free_data_block(new_data_block_id)  # 回滚
        dm.free_inode(new_inode_id)  # 回滚
        return (
            False,
            f"Error: Failed to write entries for new directory (inode {new_inode_id}).",
            None,
        )

    # new_dir_inode.size 已经在 _write_directory_entries 中被更新为条目数量
    dm.inode_table[new_inode_id] = new_dir_inode  # 将配置好的新i节点存入i节点表

    # 9. 在父目录中添加新目录的条目
    new_entry_for_parent = DirectoryEntry(name=new_dir_name, inode_id=new_inode_id)
    parent_entries.append(new_entry_for_parent)

    if not _write_directory_entries(dm, parent_inode_id, parent_entries):
        # 这一步失败比较复杂，因为新目录的i节点和数据块已经创建并写入。
        # 理想情况下需要更复杂的事务回滚，但目前简化处理：
        # 尝试删除已创建的新目录i节点和数据块。
        # (这部分可以做得更完善，例如实现一个内部的 _delete_inode_recursive)
        dm.free_data_block(new_data_block_id)
        dm.free_inode(new_inode_id)
        # 注意：父目录的条目可能已部分修改但未成功写回，可能导致不一致。
        return (
            False,
            f"Error: Failed to update parent directory (inode {parent_inode_id}) with new entry.",
            None,
        )

    # 10. 更新父目录i节点的链接数和时间戳
    parent_inode.link_count += 1  # 因为新目录的 ".." 指向父目录
    parent_inode.mtime = current_timestamp
    parent_inode.ctime = current_timestamp
    parent_inode.atime = current_timestamp

    return (
        True,
        f"Directory '{new_dir_name}' created successfully (inode {new_inode_id}).",
        new_inode_id,
    )


# 其他目录操作函数 (如 list_directory, change_directory) 将在这里添加
def list_directory(
    dm: DiskManager, dir_inode_id: int
) -> Tuple[bool, str, Optional[List[Dict[str, Any]]]]:
    """
    列出指定目录的内容。
    Args:
        dm: DiskManager 实例。
        dir_inode_id: 要列出内容的目录的i节点ID。
    Returns:
        Tuple[bool, str, Optional[List[Dict[str, Any]]]]:
            (操作是否成功, 消息, 目录条目详细信息列表（如果成功）)
        每个条目字典包含: 'name', 'inode_id', 'type', 'size', 'permissions', 'mtime', 'link_count'
    """
    # 1. 获取并验证目录i节点
    target_dir_inode = dm.get_inode(dir_inode_id)
    if not target_dir_inode:
        return False, f"Error: Directory with inode ID {dir_inode_id} not found.", None
    if target_dir_inode.type != FileType.DIRECTORY:
        return False, f"Error: Inode {dir_inode_id} is not a directory.", None

    # 2. 读取目录条目
    entries = _read_directory_entries(dm, dir_inode_id)
    if entries is None:  # 读取失败
        return (
            False,
            f"Error: Could not read entries for directory (inode {dir_inode_id}).",
            None,
        )

    # 3. 收集每个条目的详细信息
    detailed_entries: List[Dict[str, Any]] = []
    if not entries:  # 目录为空（但通常至少有 . 和 ..）
        # 如果 _read_directory_entries 在EOFError时返回空列表，这里会命中
        # print(f"Directory (inode {dir_inode_id}) is empty or failed to read entries fully.")
        # 即使是空列表，也认为是成功读取了“无内容”
        pass

    for entry in entries:
        entry_inode = dm.get_inode(entry.inode_id)
        if not entry_inode:
            print(
                f"Warning: Could not find inode {entry.inode_id} for entry '{entry.name}' in directory {dir_inode_id}. Skipping."
            )
            detailed_entries.append(
                {
                    "name": entry.name,
                    "inode_id": entry.inode_id,
                    "type": "UNKNOWN",
                    "size": 0,
                    "permissions": "---",
                    "mtime": 0,
                    "link_count": 0,
                    "error": "Inode not found",
                }
            )
            continue

        # 将时间戳转换为可读格式 (可选，或由调用方处理)
        # mtime_readable = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(entry_inode.mtime))

        detailed_entries.append(
            {
                "name": entry.name,
                "inode_id": entry.inode_id,
                "type": entry_inode.type.name,  # 'FILE' or 'DIRECTORY'
                "size": entry_inode.size,
                "permissions": oct(entry_inode.permissions),  # e.g., '0o755'
                "mtime": entry_inode.mtime,  # Unix timestamp
                # 'mtime_readable': mtime_readable, # 可选的可读时间
                "link_count": entry_inode.link_count,
                "owner_uid": entry_inode.owner_uid,  # 添加所有者信息
            }
        )

    target_dir_inode.atime = int(time.time())  # 更新访问时间
    return (
        True,
        f"Successfully listed directory (inode {dir_inode_id}).",
        detailed_entries,
    )


def _resolve_path_to_inode_id(
    dm: DiskManager, current_dir_inode_id: int, root_inode_id: int, path: str
) -> Optional[int]:
    """
    解析路径字符串，返回目标i节点ID。
    Args:
        dm: DiskManager 实例。
        current_dir_inode_id: 当前工作目录的i节点ID。
        root_inode_id: 根目录的i节点ID。
        path: 要解析的路径字符串。
    Returns:
        Optional[int]: 目标路径的i节点ID，如果路径无效或未找到则返回None。
    """
    if not path:  # 空路径通常指当前目录
        return current_dir_inode_id

    # 确定起始i节点
    if path.startswith("/"):
        current_processing_inode_id = root_inode_id
        path = path.lstrip("/")  # 移除开头的'/'以便分割
        if not path:  # 路径是 "/"
            return root_inode_id
    else:
        current_processing_inode_id = current_dir_inode_id

    components = [comp for comp in path.split("/") if comp]  # 按'/'分割并移除空组件

    for component in components:
        current_inode_obj = dm.get_inode(current_processing_inode_id)
        if not current_inode_obj or current_inode_obj.type != FileType.DIRECTORY:
            # 当前处理的路径部分不是一个目录（在到达最终目标之前）
            return None

        entries = _read_directory_entries(dm, current_processing_inode_id)
        if entries is None:  # 读取目录内容失败
            return None

        if component == ".":
            continue  # '.' 指当前目录，无需改变 current_processing_inode_id
        elif component == "..":
            found_parent = False
            for entry in entries:
                if entry.name == "..":
                    current_processing_inode_id = entry.inode_id
                    found_parent = True
                    break
            if not found_parent:  # '..' 条目未找到 (不应发生于格式正确的目录)
                return None
        else:  # 普通名称组件
            found_component = False
            for entry in entries:
                if entry.name == component:
                    target_inode_obj = dm.get_inode(entry.inode_id)
                    if not target_inode_obj:  # 目标i节点不存在
                        return None
                    # 如果这是路径的最后一个组件，它可以是文件或目录
                    # 如果不是最后一个组件，它必须是目录
                    if (
                        component != components[-1]
                        and target_inode_obj.type != FileType.DIRECTORY
                    ):
                        return None  # 路径中的某个中间部分不是目录

                    current_processing_inode_id = entry.inode_id
                    found_component = True
                    break
            if not found_component:  # 未找到路径组件
                return None

    return current_processing_inode_id


def change_directory(
    dm: DiskManager,
    current_cwd_inode_id: int,  # 当前CWD
    root_inode_id: int,  # 根ID
    target_path: str,  # 目标路径字符串
) -> Tuple[bool, str, Optional[int]]:  # 返回 (成功, 消息, 新的CWD_inode_id)
    """
    更改当前工作目录。
    Args:
        dm: DiskManager 实例。
        current_cwd_inode_id: 当前的CWD i节点ID。
        root_inode_id: 根目录的i节点ID。
        target_path: 目标目录的路径字符串。
    Returns:
        Tuple[bool, str, Optional[int]]: (操作是否成功, 消息, 新的CWD i节点ID（如果成功）)
    """
    if current_cwd_inode_id is None or root_inode_id is None:
        return False, "Error: CWD or root directory not properly initialized.", None

    new_cwd_inode_id = _resolve_path_to_inode_id(
        dm, current_cwd_inode_id, root_inode_id, target_path
    )

    if new_cwd_inode_id is None:
        return False, f"Error: Path '{target_path}' not found or is invalid.", None

    target_inode = dm.get_inode(new_cwd_inode_id)
    if not target_inode:
        # 这理论上不应发生，如果_resolve_path_to_inode_id返回了一个ID
        return False, f"Error: Resolved inode {new_cwd_inode_id} does not exist.", None

    if target_inode.type != FileType.DIRECTORY:
        return (
            False,
            f"Error: Path '{target_path}' (inode {new_cwd_inode_id}) is not a directory.",
            None,
        )

    # 成功，返回新的CWD i节点ID，调用者负责更新 UserAuthenticator 中的状态
    return (
        True,
        f"Current directory changed to inode {new_cwd_inode_id}.",
        new_cwd_inode_id,
    )


def remove_directory(
    dm: DiskManager,
    current_user_uid: int,
    parent_inode_id: int,
    dir_name_to_delete: str,
) -> Tuple[bool, str]:
    """
    从指定的父目录下删除一个空目录。
    Args:
        dm: DiskManager 实例。
        current_user_uid: 当前用户的UID (未来可用于权限检查)。
        parent_inode_id: 父目录的i节点ID。
        dir_name_to_delete: 要删除的目录的名称。
    Returns:
        Tuple[bool, str]: (操作是否成功, 消息)
    """
    # 1. 基本名称验证
    if not dir_name_to_delete or dir_name_to_delete in [".", ".."]:
        return False, f"Error: Cannot remove special directory '{dir_name_to_delete}'."

    # 2. 获取父目录i节点并检查其有效性
    parent_inode = dm.get_inode(parent_inode_id)
    if not parent_inode:
        return False, f"Error: Parent directory (inode {parent_inode_id}) not found."
    if parent_inode.type != FileType.DIRECTORY:
        return False, f"Error: Parent (inode {parent_inode_id}) is not a directory."

    # 3. 在父目录中查找要删除的目录条目
    parent_entries = _read_directory_entries(dm, parent_inode_id)
    if parent_entries is None:
        return (
            False,
            f"Error: Could not read entries of parent directory (inode {parent_inode_id}).",
        )

    dir_entry_to_delete: Optional[DirectoryEntry] = None
    entry_index_in_parent: Optional[int] = None
    for i, entry in enumerate(parent_entries):
        if entry.name == dir_name_to_delete:
            dir_entry_to_delete = entry
            entry_index_in_parent = i
            break

    if dir_entry_to_delete is None or entry_index_in_parent is None:
        return (
            False,
            f"Error: Directory '{dir_name_to_delete}' not found in parent directory (inode {parent_inode_id}).",
        )

    # 4. 获取并验证目标目录i节点
    target_dir_inode_id = dir_entry_to_delete.inode_id
    target_dir_inode = dm.get_inode(target_dir_inode_id)

    if not target_dir_inode:
        # 数据不一致：父目录中有条目，但对应的i节点丢失。
        print(
            f"Warning: Dangling directory entry '{dir_name_to_delete}' found. Inode {target_dir_inode_id} missing. Removing entry..."
        )
        parent_entries.pop(entry_index_in_parent)
        _write_directory_entries(dm, parent_inode_id, parent_entries)  # 尝试清理
        return (
            False,
            f"Error: Directory inode {target_dir_inode_id} for '{dir_name_to_delete}' not found. Dangling entry removed from parent.",
        )

    if target_dir_inode.type != FileType.DIRECTORY:
        return (
            False,
            f"Error: '{dir_name_to_delete}' (inode {target_dir_inode_id}) is not a directory. Use 'rm' to delete files.",
        )

    # (未来步骤: 权限检查)

    # 5. 检查目标目录是否为空 (只包含 "." 和 "..")
    target_dir_entries = _read_directory_entries(dm, target_dir_inode_id)
    if target_dir_entries is None:
        return (
            False,
            f"Error: Could not read entries of directory '{dir_name_to_delete}' (inode {target_dir_inode_id}) to check if empty.",
        )

    if len(target_dir_entries) > 2:
        # 检查是否真的只有 "." 和 ".."
        # (一个更严格的检查会确认这两个条目确实是 "." 和 "..")
        is_truly_empty = True
        if len(target_dir_entries) == 2:
            names = {entry.name for entry in target_dir_entries}
            if not ("." in names and ".." in names):
                is_truly_empty = (
                    False  # 有两个条目但不是预期的 . 和 .. （理论上不应发生）
                )
        else:  # 大于2个条目
            is_truly_empty = False

        if not is_truly_empty:
            return (
                False,
                f"Error: Directory '{dir_name_to_delete}' (inode {target_dir_inode_id}) is not empty.",
            )

    # --- 开始执行删除 ---
    # 6. 从父目录中移除该目录的条目
    parent_entries.pop(entry_index_in_parent)
    if not _write_directory_entries(dm, parent_inode_id, parent_entries):
        # 如果更新父目录失败，这是一个比较麻烦的状态，因为我们还没开始释放目标目录的资源
        # 但父目录的内容可能已在内存中被修改。最好是能有一种方式撤销内存中的修改或标记不一致。
        return (
            False,
            f"Error: Failed to update parent directory (inode {parent_inode_id}) after removing entry for '{dir_name_to_delete}'. Operation aborted before freeing resources.",
        )

    # 7. 更新父目录i节点的链接数和时间戳
    parent_inode.link_count -= 1  # 因为被删除目录的 ".." 不再指向父目录
    current_timestamp = int(time.time())
    parent_inode.mtime = current_timestamp
    parent_inode.ctime = current_timestamp  # link_count 和 mtime 更改都算 ctime 更改
    parent_inode.atime = current_timestamp

    # 8. 释放被删除目录的资源
    # 8a. 释放其数据块 (只应有一个数据块，包含 "." 和 "..")
    for block_idx in target_dir_inode.data_block_indices:
        dm.free_data_block(block_idx)
    target_dir_inode.data_block_indices = []
    target_dir_inode.blocks_count = 0
    target_dir_inode.size = 0  # 条目数为0

    # 8b. 释放其i节点
    dm.free_inode(target_dir_inode_id)
    # target_dir_inode.link_count 在被删除前应为2 (来自父目录的条目和自身的'.')
    # 父目录条目被删除后，逻辑上它的链接数减为1 (只剩'.')。
    # '..' 指向父目录，所以当父目录的link_count因它而减少后，它的使命也完成了。
    # free_inode 会将其从 inode_table 中移除。

    return True, f"Directory '{dir_name_to_delete}' removed successfully."


def rename_item(
    dm: DiskManager, user_uid: int, parent_inode_id: int, old_name: str, new_name: str
) -> Tuple[bool, str]:
    """
    重命名在父目录下的一个文件或目录。
    Args:
        dm: DiskManager 实例。
        user_uid: 当前用户的 UID。
        parent_inode_id: 父目录的 i节点 ID。
        old_name: 要重命名的项目旧名称。
        new_name: 项目的新名称。
    Returns:
        Tuple[bool, str]: (操作是否成功, 消息)
    """
    if not new_name or "/" in new_name or new_name in [".", ".."]:
        return False, f"错误：无效的新名称 '{new_name}'。"
    if len(new_name) > 255:  # 假设最大文件名长度
        return False, "错误：新名称过长。"
    if old_name == new_name:
        # 通常认为名称相同不是错误，但也不执行任何操作
        return True, "新旧名称相同，未执行任何操作。"

    parent_inode = dm.get_inode(parent_inode_id)
    if not parent_inode:
        return False, f"错误：父目录 (inode {parent_inode_id}) 未找到。"
    if parent_inode.type != FileType.DIRECTORY:
        return False, f"错误：父节点 (inode {parent_inode_id}) 不是一个目录。"

    # 权限检查: 需要对父目录有写权限才能重命名其下的条目
    if not check_permission(parent_inode, user_uid, Permissions.WRITE):
        return False, f"权限不足：无法写入父目录 (inode {parent_inode_id})。"

    entries = _read_directory_entries(dm, parent_inode_id)
    if entries is None:
        return False, f"错误：无法读取父目录 (inode {parent_inode_id}) 的条目。"

    old_entry_index = -1
    target_inode_id = -1  # 被重命名项目的inode_id

    for i, entry in enumerate(entries):
        if entry.name == new_name:
            return False, f"错误：名称 '{new_name}' 在目录中已存在。"
        if entry.name == old_name:
            old_entry_index = i
            target_inode_id = entry.inode_id
            # 不在此处 break，继续检查 new_name 是否冲突

    if old_entry_index == -1:
        return False, f"错误：项目 '{old_name}' 在目录中未找到。"

    # 修改目录条目中的名称
    entries[old_entry_index].name = new_name

    # 将修改后的条目列表写回父目录的数据块
    if not _write_directory_entries(dm, parent_inode_id, entries):
        # 如果写入失败，理论上应该尝试恢复条目名称，但为简化，这里直接报告错误
        return False, f"错误：更新父目录 (inode {parent_inode_id}) 条目失败。"

    # 更新时间戳
    current_timestamp = int(time.time())
    parent_inode.mtime = current_timestamp  # 父目录内容修改时间
    parent_inode.ctime = current_timestamp  # 父目录元数据（mtime）更改时间
    parent_inode.atime = current_timestamp  # 父目录访问时间（写也是一种访问）

    # 更新被重命名项目本身的 ctime (元数据更改时间，因为其在父目录中的名称变了)
    target_inode = dm.get_inode(target_inode_id)
    if target_inode:
        target_inode.ctime = current_timestamp

    # 持久化操作通常由调用者（例如GUI或主循环）在成功后统一处理
    # pm.save_disk_image(dm)

    return True, f"项目 '{old_name}' 已成功重命名为 '{new_name}'。"
