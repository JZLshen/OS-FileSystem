import time
import pickle  # Though not directly used in all functions, good for file_ops module
from typing import Tuple, Optional, List

from .disk_manager import DiskManager

# Ensure all necessary datastructures are imported, including new ones
from .datastructures import (
    Inode,
    DirectoryEntry,
    FileType,
    Permissions,
    OpenMode,
    OpenFileEntry,
)

# We need helpers from dir_ops
from .dir_ops import (
    _read_directory_entries,
    _write_directory_entries,
    _resolve_path_to_inode_id,
)

# UserAuthenticator is needed for open/close to manage file descriptors
from user_management.user_auth import UserAuthenticator


# 默认新文件权限 (rw-r--r--)
DEFAULT_FILE_PERMISSIONS = 0o644


def create_file(
    dm: DiskManager, current_user_uid: int, parent_inode_id: int, new_file_name: str
) -> Tuple[bool, str, Optional[int]]:
    """
    在指定的父目录下创建一个新的空文件。
    (此函数内容与您提供的一致，保持不变)
    """
    # 1. 基本名称验证
    if not new_file_name or "/" in new_file_name or new_file_name in [".", ".."]:
        return False, f"Error: Invalid file name '{new_file_name}'.", None
    if len(new_file_name) > 255:  # 假设最大文件名长度
        return False, "Error: File name too long.", None

    # 2. 获取父目录i节点并检查其有效性
    parent_inode = dm.get_inode(parent_inode_id)
    if not parent_inode:
        return (
            False,
            f"Error: Parent directory (inode {parent_inode_id}) not found.",
            None,
        )
    if parent_inode.type != FileType.DIRECTORY:  # Make sure parent is a directory
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
        if entry.name == new_file_name:
            return (
                False,
                f"Error: Directory or file '{new_file_name}' already exists in parent (inode {parent_inode_id}).",
                None,
            )

    # --- 开始分配资源 ---
    # 4. 为新文件分配i节点
    new_inode_id = dm.allocate_inode(uid_for_inode=current_user_uid)
    if new_inode_id is None:
        return False, "Error: No free inodes available for new file.", None

    # 5. 初始化新文件的i节点
    current_timestamp = int(time.time())
    new_file_inode = Inode(
        inode_id=new_inode_id,
        file_type=FileType.FILE,  # 设置类型为 FILE
        owner_uid=current_user_uid,
        permissions=DEFAULT_FILE_PERMISSIONS,
    )  # 使用文件默认权限

    new_file_inode.size = 0  # 文件初始大小为0
    new_file_inode.link_count = 1  # 文件在父目录中的一个条目
    new_file_inode.atime = new_file_inode.mtime = new_file_inode.ctime = (
        current_timestamp
    )

    dm.inode_table[new_inode_id] = new_file_inode

    # 6. 在父目录中添加新文件的条目
    new_entry_for_parent = DirectoryEntry(name=new_file_name, inode_id=new_inode_id)
    parent_entries.append(new_entry_for_parent)

    if not _write_directory_entries(dm, parent_inode_id, parent_entries):
        dm.inode_table[new_inode_id] = None
        dm.free_inode(new_inode_id)
        return (
            False,
            f"Error: Failed to update parent directory (inode {parent_inode_id}) with new file entry.",
            None,
        )

    parent_inode.mtime = current_timestamp
    parent_inode.ctime = current_timestamp
    parent_inode.atime = current_timestamp

    return (
        True,
        f"File '{new_file_name}' created successfully (inode {new_inode_id}).",
        new_inode_id,
    )


def delete_file(
    dm: DiskManager,
    current_user_uid: int,
    parent_inode_id: int,
    file_name_to_delete: str,
) -> Tuple[bool, str]:
    """
    从指定的父目录下删除一个文件。
    (此函数内容与您提供的一致，保持不变)
    """
    if file_name_to_delete in [".", ".."]:
        return (
            False,
            f"Error: Cannot delete '{file_name_to_delete}'. It is a special directory entry.",
        )

    parent_inode = dm.get_inode(parent_inode_id)
    if not parent_inode:
        return False, f"Error: Parent directory (inode {parent_inode_id}) not found."
    if parent_inode.type != FileType.DIRECTORY:
        return False, f"Error: Parent (inode {parent_inode_id}) is not a directory."

    parent_entries = _read_directory_entries(dm, parent_inode_id)
    if parent_entries is None:
        return (
            False,
            f"Error: Could not read entries of parent directory (inode {parent_inode_id}).",
        )

    file_entry_to_delete: Optional[DirectoryEntry] = None
    entry_index_to_delete: Optional[int] = None
    for i, entry in enumerate(parent_entries):
        if entry.name == file_name_to_delete:
            file_entry_to_delete = entry
            entry_index_to_delete = i
            break

    if file_entry_to_delete is None or entry_index_to_delete is None:
        return (
            False,
            f"Error: File '{file_name_to_delete}' not found in directory (inode {parent_inode_id}).",
        )

    file_inode_id = file_entry_to_delete.inode_id
    file_inode = dm.get_inode(file_inode_id)

    if not file_inode:
        print(
            f"Warning: Dangling directory entry '{file_name_to_delete}' found. Inode {file_inode_id} missing. Removing entry..."
        )
        parent_entries.pop(entry_index_to_delete)
        _write_directory_entries(dm, parent_inode_id, parent_entries)
        return (
            False,
            f"Error: File inode {file_inode_id} for '{file_name_to_delete}' not found, but entry existed. Entry removed.",
        )

    if file_inode.type == FileType.DIRECTORY:
        return (
            False,
            f"Error: '{file_name_to_delete}' is a directory. Use 'rmdir' or equivalent to delete directories.",
        )

    for block_idx in file_inode.data_block_indices:
        dm.free_data_block(block_idx)

    file_inode.data_block_indices = []
    file_inode.blocks_count = 0
    file_inode.size = 0

    dm.free_inode(file_inode_id)

    parent_entries.pop(entry_index_to_delete)

    if not _write_directory_entries(dm, parent_inode_id, parent_entries):
        return (
            False,
            f"Critical Error: File resources freed, but failed to update parent directory (inode {parent_inode_id}). Filesystem might be inconsistent.",
        )

    current_timestamp = int(time.time())
    parent_inode.mtime = current_timestamp
    parent_inode.ctime = current_timestamp
    parent_inode.atime = current_timestamp

    return True, f"File '{file_name_to_delete}' deleted successfully."


# --- 新增函数 ---


def _parse_open_mode(mode_str: str) -> Optional[OpenMode]:
    """辅助函数：将字符串模式转换为OpenMode枚举。"""
    mode_str = mode_str.lower()
    if mode_str == "r":
        return OpenMode.READ
    elif mode_str == "w":
        return OpenMode.WRITE
    elif mode_str == "a":
        return OpenMode.APPEND
    elif mode_str == "r+":
        return OpenMode.READ_WRITE
    else:
        return None


def open_file(
    dm: DiskManager, auth: UserAuthenticator, path_str: str, mode_str: str
) -> Tuple[bool, str, Optional[int]]:
    """
    打开一个文件，返回文件描述符。
    """
    current_user = auth.get_current_user()
    if not current_user:
        return False, "Error: No user logged in.", None

    current_user_uid = current_user.uid  # 获取UID，以备将来权限检查或设置所有者
    cwd_inode_id = auth.get_cwd_inode_id()

    if (
        cwd_inode_id is None
        or dm.superblock is None
        or dm.superblock.root_inode_id is None
    ):
        return False, "Error: CWD or root directory not properly initialized.", None
    root_inode_id = dm.superblock.root_inode_id

    open_mode = _parse_open_mode(mode_str)
    if open_mode is None:
        return (
            False,
            f"Error: Invalid open mode '{mode_str}'. Supported modes: r, w, a, r+.",
            None,
        )

    resolved_inode_id = _resolve_path_to_inode_id(
        dm, cwd_inode_id, root_inode_id, path_str
    )
    file_inode: Optional[Inode] = None
    file_inode_id: Optional[int] = None  # 用来存储最终要操作的文件的inode ID

    if resolved_inode_id is not None:  # 路径指向一个已存在的i节点
        _inode_check = dm.get_inode(resolved_inode_id)
        if not _inode_check:
            return (
                False,
                f"Internal Error: Resolved inode {resolved_inode_id} exists in path but not in table.",
                None,
            )
        if _inode_check.type == FileType.DIRECTORY:
            return False, f"Error: Path '{path_str}' is a directory.", None
        # 是一个已存在的文件
        file_inode_id = resolved_inode_id
        file_inode = _inode_check

    # 根据模式处理文件不存在或需要创建的情况
    if file_inode_id is None:  # 文件不存在
        if open_mode in [
            OpenMode.READ,
            OpenMode.READ_WRITE,
        ]:  # r, r+ 模式要求文件必须存在
            return False, f"Error: File '{path_str}' not found.", None
        elif open_mode in [
            OpenMode.WRITE,
            OpenMode.APPEND,
        ]:  # w, a 模式，如果文件不存在则创建
            # 需要找到父目录的inode和文件名
            path_parts = [comp for comp in path_str.split("/") if comp]  # 清理路径组件
            if not path_parts:
                return (
                    False,
                    f"Error: Invalid path for file creation '{path_str}'.",
                    None,
                )

            file_name_to_create = path_parts[-1]

            if len(path_parts) == 1:  # 文件在CWD下创建，或path_str是 "/filename"
                parent_path_for_creation = "." if not path_str.startswith("/") else "/"
            else:
                parent_path_for_creation = "/".join(path_parts[:-1])
                if path_str.startswith("/"):
                    parent_path_for_creation = "/" + parent_path_for_creation

            parent_inode_id_for_create = _resolve_path_to_inode_id(
                dm, cwd_inode_id, root_inode_id, parent_path_for_creation
            )

            if parent_inode_id_for_create is None:
                return (
                    False,
                    f"Error: Parent directory for '{path_str}' (resolved as '{parent_path_for_creation}') not found or invalid.",
                    None,
                )

            success_create, msg_create, new_file_inode_id = create_file(
                dm, current_user_uid, parent_inode_id_for_create, file_name_to_create
            )
            if not success_create or new_file_inode_id is None:
                return False, f"Error creating file '{path_str}': {msg_create}", None

            file_inode_id = new_file_inode_id
            file_inode = dm.get_inode(file_inode_id)
            if not file_inode:  # 创建后应立即能获取
                return (
                    False,
                    f"Internal Error: Newly created file inode {file_inode_id} not found.",
                    None,
                )
            print(f"File '{path_str}' created during open.")
        else:  # 不应到达此逻辑分支
            return (
                False,
                "Internal error: Unhandled open mode for non-existent file.",
                None,
            )

    # 此时，file_inode 和 file_inode_id 应该都已有效（指向现有文件或新创建的文件）
    if file_inode is None or file_inode_id is None:  # 防御性检查
        return False, "Internal error: File inode could not be determined.", None

    # (未来：权限检查)

    if open_mode == OpenMode.WRITE:  # 'w' 模式，如果文件存在，则清空内容
        if (
            file_inode.size > 0 or file_inode.data_block_indices
        ):  # 只有当文件实际有内容时才执行截断
            print(
                f"Opening '{path_str}' in write mode, truncating existing file (inode {file_inode_id})."
            )
            for block_idx in file_inode.data_block_indices:
                dm.free_data_block(block_idx)
            file_inode.data_block_indices = []
            file_inode.blocks_count = 0
            file_inode.size = 0
            current_timestamp = int(time.time())
            file_inode.mtime = current_timestamp
            file_inode.ctime = current_timestamp
            file_inode.atime = current_timestamp  # 截断也是一种访问和修改

    # 创建OpenFileEntry
    oft_entry = OpenFileEntry(
        inode_id=file_inode_id, mode=open_mode, inode_ref=file_inode
    )

    # 分配文件描述符
    fd = auth.allocate_fd(oft_entry)
    if fd == -1:
        return (
            False,
            "Error: Could not allocate file descriptor (e.g., too many open files).",
            None,
        )

    file_inode.atime = int(time.time())  # 打开操作更新访问时间
    return (
        True,
        f"File '{path_str}' (inode {file_inode_id}) opened successfully with mode '{open_mode.name}' (fd={fd}).",
        fd,
    )


def close_file(auth: UserAuthenticator, fd: int) -> Tuple[bool, str]:
    """
    关闭一个已打开的文件。
    """
    current_user = auth.get_current_user()  # 检查是否有用户登录
    if not current_user:
        return False, "Error: No user logged in to close a file for."

    oft_entry_to_close = auth.get_oft_entry(fd)
    if oft_entry_to_close is None:
        return False, f"Error: Invalid file descriptor {fd}."

    # (未来：如果实现了写缓冲，在此处将缓冲数据刷入磁盘)
    # e.g., if oft_entry_to_close.is_dirty: flush_buffers_to_disk(dm, oft_entry_to_close)

    if auth.release_fd(fd):
        # inode = oft_entry_to_close.inode_ref
        # inode.atime = int(time.time()) # 关闭一般不更新atime，读写时更新
        return (
            True,
            f"File descriptor {fd} (inode {oft_entry_to_close.inode_id}) closed successfully.",
        )
    else:
        # 这理论上不应发生，如果 get_oft_entry 成功了
        return False, f"Error: Failed to release file descriptor {fd} (internal error)."


def write_file(
    dm: DiskManager, auth: UserAuthenticator, fd: int, content_str: str
) -> Tuple[bool, str, Optional[int]]:
    current_user = auth.get_current_user()
    if not current_user:
        return False, "错误：无用户登录。", None

    oft_entry = auth.get_oft_entry(fd)
    if oft_entry is None:
        return False, f"错误：无效的文件描述符 {fd}。", None

    if oft_entry.mode not in [OpenMode.WRITE, OpenMode.APPEND, OpenMode.READ_WRITE]:
        return (
            False,
            f"错误：文件 (fd={fd}) 未以可写模式打开 (当前模式: {oft_entry.mode.name})。",
            None,
        )

    try:
        content_bytes = content_str.encode("utf-8")
    except UnicodeEncodeError as e:
        return False, f"错误：内容编码为UTF-8失败: {e}", None

    len_content_bytes = len(content_bytes)
    # if len_content_bytes == 0: # 写入空内容也是一种有效的写入，会截断文件
    #     pass # 继续执行，以便文件被截断（如果需要）

    file_inode = oft_entry.inode_ref
    current_offset = oft_entry.offset  # 通常在“保存”操作前，这个offset会被重置为0
    block_size = dm.superblock.block_size

    bytes_written_this_call = 0
    content_bytes_ptr = 0

    # --- 开始写入循环 ---
    while (
        content_bytes_ptr < len_content_bytes
    ):  # 改为 content_bytes_ptr，因为 bytes_written_this_call 是总写入
        logical_block_idx = current_offset // block_size
        offset_in_block = current_offset % block_size
        physical_block_id: Optional[int] = None
        current_block_data: bytearray

        if logical_block_idx < len(file_inode.data_block_indices):
            physical_block_id = file_inode.data_block_indices[logical_block_idx]
            try:
                # 如果是从头覆盖写(offset_in_block=0)，并且这是该块的第一次写入，
                # 则不需要读取旧数据，可以直接用新数据覆盖。
                # 但为了通用性（部分覆盖），先读取。
                current_block_data = dm.read_block(physical_block_id)
            except IndexError:
                return (
                    False,
                    f"内部错误：无效的物理块ID {physical_block_id} (inode {file_inode.id})。",
                    bytes_written_this_call,
                )
        else:
            if logical_block_idx != len(file_inode.data_block_indices):
                return (
                    False,
                    f"内部错误：非连续逻辑块访问 (inode {file_inode.id})。",
                    bytes_written_this_call,
                )
            physical_block_id = dm.allocate_data_block()
            if physical_block_id is None:
                # 更新实际写入的字节和文件大小，即使磁盘满了
                if (
                    oft_entry.offset > file_inode.size
                ):  # 这个offset是写入前的oft_entry.offset + bytes_written_this_call
                    file_inode.size = (
                        oft_entry.offset
                    )  # 更新为已成功写入的部分结束的位置
                # file_inode.size 应该反映实际成功写入数据后的文件大小
                # current_offset 在这里是已成功写入的下一个位置
                file_inode.size = current_offset  # 更新为已成功写入字节的末尾

                file_inode.mtime = file_inode.atime = file_inode.ctime = int(
                    time.time()
                )
                oft_entry.offset = current_offset  # 更新OFT条目中的偏移量
                return (
                    False,
                    f"错误：磁盘已满。部分写入 {bytes_written_this_call} 字节。",
                    bytes_written_this_call,
                )
            file_inode.data_block_indices.append(physical_block_id)
            file_inode.blocks_count += 1
            current_block_data = bytearray(block_size)

        space_in_current_block = block_size - offset_in_block
        bytes_to_write_in_this_block = min(
            len_content_bytes - content_bytes_ptr,
            space_in_current_block,  # 使用 content_bytes_ptr
        )
        data_chunk_to_write = content_bytes[
            content_bytes_ptr : content_bytes_ptr + bytes_to_write_in_this_block
        ]
        current_block_data[
            offset_in_block : offset_in_block + bytes_to_write_in_this_block
        ] = data_chunk_to_write
        try:
            dm.write_block(physical_block_id, bytes(current_block_data))
        except (IndexError, ValueError) as e:
            file_inode.size = current_offset  # 尽可能更新大小
            oft_entry.offset = current_offset
            return (
                False,
                f"内部错误：写入块 {physical_block_id} 失败。{e}",
                bytes_written_this_call,
            )

        current_offset += bytes_to_write_in_this_block
        content_bytes_ptr += bytes_to_write_in_this_block
        bytes_written_this_call += bytes_to_write_in_this_block
    # --- 写入循环结束 ---

    # 新文件大小就是 current_offset (如果从0开始写，就是 len_content_bytes)
    new_file_size = current_offset

    # --- 文件截断/收缩逻辑 ---
    # 这个 new_file_size 是基于 oft_entry.offset (通常是0) + len_content_bytes 计算得到的最终文件大小
    # 如果 oft_entry.offset 不是0开始的（例如追加），那么 new_file_size 是追加后的总大小
    # 对于覆盖保存操作，调用者应确保 oft_entry.offset=0

    old_num_blocks_allocated = file_inode.blocks_count  # 使用 blocks_count 更可靠
    # 计算新文件大小需要多少个块 (向上取整)
    required_num_blocks = (
        (new_file_size + block_size - 1) // block_size if new_file_size > 0 else 0
    )

    if required_num_blocks < old_num_blocks_allocated:
        # 需要释放多余的数据块
        blocks_to_free = file_inode.data_block_indices[required_num_blocks:]
        for block_idx_to_free in blocks_to_free:
            dm.free_data_block(block_idx_to_free)

        file_inode.data_block_indices = file_inode.data_block_indices[
            :required_num_blocks
        ]

    file_inode.blocks_count = required_num_blocks
    # --- 文件截断/收缩逻辑结束 ---

    file_inode.size = new_file_size  # 最终更新 inode 的 size
    oft_entry.offset = new_file_size  # 更新OFT中的文件指针到文件末尾

    current_timestamp = int(time.time())
    file_inode.mtime = current_timestamp
    file_inode.atime = current_timestamp
    file_inode.ctime = current_timestamp

    return (
        True,
        f"{bytes_written_this_call} 字节成功写入 fd {fd}。",
        bytes_written_this_call,
    )


def read_file(
    dm: DiskManager, auth: UserAuthenticator, fd: int, num_bytes_to_read: int
) -> Tuple[bool, str, Optional[bytes]]:
    """
    从打开的文件读取内容。
    Args:
        dm: DiskManager 实例。
        auth: UserAuthenticator 实例。
        fd: 要读取的文件的文件描述符。
        num_bytes_to_read: 希望读取的字节数。
    Returns:
        Tuple[bool, str, Optional[bytes]]: (操作是否成功, 消息, 读取到的字节串（如果成功）)
    """
    current_user = auth.get_current_user()
    if not current_user:
        return False, "Error: No user logged in.", None

    oft_entry = auth.get_oft_entry(fd)
    if oft_entry is None:
        return False, f"Error: Invalid file descriptor {fd}.", None

    # 1. 检查文件打开模式是否可读
    if oft_entry.mode not in [
        OpenMode.READ,
        OpenMode.READ_WRITE,
        OpenMode.APPEND,
    ]:  # APPEND mode can also allow reading in some systems after opening
        # Standard POSIX 'a' (append) opens for writing only. 'a+' opens for reading and appending.
        # Our current OpenMode.APPEND is simplified. If we want strict POSIX 'a', reading should fail.
        # For now, let's assume our APPEND is like 'a+' and allows reading. Or restrict to READ and READ_WRITE.
        # Let's be stricter for now:
        if oft_entry.mode not in [OpenMode.READ, OpenMode.READ_WRITE]:
            return (
                False,
                f"Error: File (fd={fd}) not opened in a readable mode (current mode: {oft_entry.mode.name}).",
                None,
            )

    if num_bytes_to_read < 0:
        return False, "Error: Number of bytes to read cannot be negative.", None
    if num_bytes_to_read == 0:
        return True, "0 bytes read (requested 0 bytes).", b""

    file_inode = oft_entry.inode_ref
    current_offset = oft_entry.offset
    file_size = file_inode.size
    block_size = dm.superblock.block_size

    # 2. 处理文件末尾 (EOF)
    if current_offset >= file_size:
        return True, "End of file reached.", b""  # 返回空字节串表示EOF

    # 3. 计算实际可以读取的字节数
    # 不能超过请求的字节数，也不能超过从当前偏移量到文件末尾的剩余字节数
    bytes_can_actually_read = min(num_bytes_to_read, file_size - current_offset)

    if (
        bytes_can_actually_read <= 0
    ):  # 如果计算后可读为0或负（理论上current_offset < file_size时不会为负）
        return (
            True,
            "End of file reached (or no more data to read from current offset).",
            b"",
        )

    # 4. 循环读取数据
    read_data_chunks: List[bytes] = []
    bytes_read_so_far = 0

    temp_offset = current_offset  # 使用临时偏移量进行计算，最后一次性更新OFT中的offset

    while bytes_read_so_far < bytes_can_actually_read:
        logical_block_idx = temp_offset // block_size
        offset_in_block = temp_offset % block_size

        # 检查逻辑块索引是否有效 (不应超出已分配的块范围)
        if logical_block_idx >= len(file_inode.data_block_indices):
            # 尝试读取超出文件实际分配块的范围，这表示已达文件内容末尾或文件损坏
            # (bytes_can_actually_read 的计算应该已经阻止了这种情况，除非inode.size与分配的块不符)
            print(
                f"Warning: Attempting to read beyond allocated blocks for inode {file_inode.id}. "
                f"Logical block {logical_block_idx}, but only {len(file_inode.data_block_indices)} blocks allocated. "
                f"File size: {file_size}, current offset: {temp_offset}."
            )
            break  # 停止读取

        physical_block_id = file_inode.data_block_indices[logical_block_idx]

        try:
            block_content_bytearray = dm.read_block(physical_block_id)
        except IndexError:
            return (
                False,
                f"Internal Error: Invalid physical block id {physical_block_id} for inode {file_inode.id}.",
                None,
            )

        # 从当前块中读取多少字节
        bytes_to_read_from_this_block = min(
            block_size - offset_in_block, bytes_can_actually_read - bytes_read_so_far
        )

        data_chunk = bytes(
            block_content_bytearray[
                offset_in_block : offset_in_block + bytes_to_read_from_this_block
            ]
        )
        read_data_chunks.append(data_chunk)

        temp_offset += bytes_to_read_from_this_block
        bytes_read_so_far += bytes_to_read_from_this_block

    # 5. 合并读取到的数据块
    final_read_data = b"".join(read_data_chunks)

    # 6. 更新OFT条目中的偏移量和文件i节点的访问时间
    oft_entry.offset = temp_offset  # 更新实际的偏移量
    file_inode.atime = int(time.time())

    return (
        True,
        f"{len(final_read_data)} bytes read successfully from fd {fd}.",
        final_read_data,
    )
