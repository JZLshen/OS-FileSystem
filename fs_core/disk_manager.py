import pickle
import time
from typing import List, Optional, Tuple

from .datastructures import Inode, DirectoryEntry, Superblock, FileType, Permissions

# 默认配置 (未来可以移到 config.py)
DEFAULT_NUM_INODES = 1024
DEFAULT_NUM_BLOCKS = 4096  # 4096个块
DEFAULT_BLOCK_SIZE = 512  # 每个块512字节
ROOT_UID = 0  # 根用户的UID


class DiskManager:
    def __init__(self):
        self.superblock: Optional[Superblock] = None
        self.inode_bitmap: List[bool] = []  # True 表示空闲, False 表示已分配
        self.data_block_bitmap: List[bool] = []  # True 表示空闲, False 表示已分配

        self.inode_table: List[Optional[Inode]] = []
        # 数据块存储，每个块是 bytearray，方便修改和按字节存储
        self.data_blocks: List[Optional[bytearray]] = []

        self.is_formatted = False  # 标记磁盘是否已格式化

    def _initialize_storage(self, num_inodes: int, num_blocks: int, block_size: int):
        """内部方法：初始化存储结构，在格式化时调用"""
        self.superblock = Superblock(
            total_blocks=num_blocks, total_inodes=num_inodes, block_size=block_size
        )

        self.inode_bitmap = [True] * num_inodes
        self.data_block_bitmap = [True] * num_blocks

        self.inode_table = [None] * num_inodes
        self.data_blocks = [
            bytearray(block_size) for _ in range(num_blocks)
        ]  # 初始化数据块

        self.is_formatted = False  # 重置格式化标记，直到格式化完成

    def format_disk(
        self,
        num_inodes: int = DEFAULT_NUM_INODES,
        num_blocks: int = DEFAULT_NUM_BLOCKS,
        block_size: int = DEFAULT_BLOCK_SIZE,
    ) -> bool:
        """
        格式化磁盘：
        1. 初始化超级块。
        2. 初始化i节点位图和数据块位图。
        3. 初始化i节点表和数据块区域。
        4. 创建根目录 "/"。
        """
        print(
            f"Formatting disk with {num_inodes} inodes, {num_blocks} blocks, {block_size}B block size..."
        )
        self._initialize_storage(num_inodes, num_blocks, block_size)

        if self.superblock is None:  # Should not happen if _initialize_storage worked
            print("Error: Superblock not initialized.")
            return False

        # 1. 为根目录分配一个i节点
        root_inode_id = self.allocate_inode(uid_for_inode=ROOT_UID)
        if root_inode_id is None:
            print("Error: Could not allocate inode for root directory.")
            return False

        self.superblock.root_inode_id = root_inode_id

        # 2. 获取并配置根i节点
        root_inode = Inode(
            inode_id=root_inode_id,
            file_type=FileType.DIRECTORY,
            owner_uid=ROOT_UID,
            # 根目录权限 rwxr-xr-x (0o755)
            permissions=0o755,
        )
        root_inode.link_count = (
            2  # 一个来自自身 ".", 一个来自父目录 (根目录的 ".." 也指向自身)
        )

        # 3. 为根目录的目录项分配一个数据块
        root_data_block_id = self.allocate_data_block()
        if root_data_block_id is None:
            # 需要回滚已分配的 root_inode_id
            self.free_inode(root_inode_id)
            print("Error: Could not allocate data block for root directory.")
            return False

        root_inode.data_block_indices.append(root_data_block_id)
        root_inode.blocks_count = 1

        # 4. 创建 "." 和 ".." 目录项
        # 对于根目录, "." 和 ".." 都指向根i节点本身
        dot_entry = DirectoryEntry(name=".", inode_id=root_inode_id)
        dot_dot_entry = DirectoryEntry(name="..", inode_id=root_inode_id)

        dir_entries: List[DirectoryEntry] = [dot_entry, dot_dot_entry]
        root_inode.size = len(dir_entries)  # 目录大小可以定义为条目数量

        # 5. 将目录项序列化并写入数据块
        try:
            serialized_entries = pickle.dumps(dir_entries)
            if len(serialized_entries) > self.superblock.block_size:
                # 这是一个错误情况，初始的根目录条目不应超过一个块大小
                self.free_data_block(root_data_block_id)
                self.free_inode(root_inode_id)
                print(
                    f"Error: Root directory entries too large for a single block ({len(serialized_entries)} > {self.superblock.block_size})."
                )
                return False

            self.write_block(root_data_block_id, serialized_entries)

        except pickle.PickleError as e:
            self.free_data_block(root_data_block_id)
            self.free_inode(root_inode_id)
            print(f"Error pickling root directory entries: {e}")
            return False

        # 6. 更新i节点表
        self.inode_table[root_inode_id] = root_inode

        self.is_formatted = True
        print(f"Disk formatted successfully. Root Inode ID: {root_inode_id}")
        print(f"Superblock state: {self.superblock}")
        return True

    def allocate_inode(
        self, uid_for_inode: int
    ) -> Optional[int]:  # uid_for_inode is for Inode creation
        if not self.superblock or self.superblock.free_inodes_count == 0:
            return None
        try:
            inode_id = self.inode_bitmap.index(True)  # 找到第一个空闲的i节点
            self.inode_bitmap[inode_id] = False
            self.superblock.free_inodes_count -= 1

            # 实际的 Inode 对象创建和存储在 inode_table 由调用方（如 format 或 create_file）完成
            # 这里只负责分配ID并更新位图和超级块计数
            return inode_id
        except ValueError:  # 没有找到 True，即没有空闲i节点
            return None

    def free_inode(self, inode_id: int):
        if (
            not self.superblock
            or inode_id < 0
            or inode_id >= self.superblock.total_inodes
        ):
            print(f"Error: Invalid inode_id {inode_id} to free.")
            return
        if not self.inode_bitmap[inode_id]:  # 如果本来就是已分配状态
            self.inode_bitmap[inode_id] = True
            self.superblock.free_inodes_count += 1
            self.inode_table[inode_id] = None  # 清除i节点表中的条目
        else:
            print(f"Warning: Inode {inode_id} was already free.")

    def allocate_data_block(self) -> Optional[int]:
        if not self.superblock or self.superblock.free_blocks_count == 0:
            return None
        try:
            block_id = self.data_block_bitmap.index(True)  # 找到第一个空闲数据块
            self.data_block_bitmap[block_id] = False
            self.superblock.free_blocks_count -= 1
            return block_id
        except ValueError:
            return None

    def free_data_block(self, block_id: int):
        if (
            not self.superblock
            or block_id < 0
            or block_id >= self.superblock.total_blocks
        ):
            print(f"Error: Invalid block_id {block_id} to free.")
            return
        if not self.data_block_bitmap[block_id]:  # 如果本来就是已分配状态
            self.data_block_bitmap[block_id] = True
            self.superblock.free_blocks_count += 1
            # 可选：清除数据块内容
            # self.data_blocks[block_id] = bytearray(self.superblock.block_size)
        else:
            print(f"Warning: Data block {block_id} was already free.")

    def write_block(self, block_id: int, data: bytes):
        if (
            not self.superblock
            or block_id < 0
            or block_id >= self.superblock.total_blocks
        ):
            raise IndexError("Block ID out of bounds.")
        if len(data) > self.superblock.block_size:
            raise ValueError("Data larger than block size.")

        # 将数据拷贝到目标块，不足部分用0填充 (如果传入数据较短)
        block_data = bytearray(data)
        block_data.extend(b"\0" * (self.superblock.block_size - len(block_data)))
        self.data_blocks[block_id] = block_data

        # 更新相关i节点的mtime和atime应由文件操作逻辑处理

    def read_block(self, block_id: int) -> bytearray:
        if (
            not self.superblock
            or block_id < 0
            or block_id >= self.superblock.total_blocks
        ):
            raise IndexError("Block ID out of bounds.")
        if (
            self.data_blocks[block_id] is None
        ):  # Should not happen if block is allocated
            return bytearray(self.superblock.block_size)  # Return empty block
        return self.data_blocks[block_id]

    def get_inode(self, inode_id: int) -> Optional[Inode]:
        if (
            not self.is_formatted
            or inode_id < 0
            or not self.superblock
            or inode_id >= self.superblock.total_inodes
        ):
            return None
        return self.inode_table[inode_id]

    # --- 未来持久化相关方法 ---
    # def save_disk_image(self, filename: str):
    #     # ... 实现保存整个DiskManager状态到文件 ...
    #     pass

    # def load_disk_image(self, filename: str):
    #     # ... 实现从文件加载DiskManager状态 ...
    #     pass
