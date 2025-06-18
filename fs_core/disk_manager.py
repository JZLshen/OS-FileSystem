import pickle
import time
from typing import List, Optional, Tuple

from .datastructures import Inode, DirectoryEntry, Superblock, FileType, Permissions

# 默认配置
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
        if inode_id is None:
            return None
        if (
            not self.is_formatted
            or inode_id < 0
            or not self.superblock
            or inode_id >= self.superblock.total_inodes
        ):
            return None
        return self.inode_table[inode_id]

    def allocate_indirect_block(self) -> Optional[int]:
        """
        分配间接块
        
        Returns:
            分配的块ID，失败返回None
        """
        return self.allocate_data_block()
    
    def allocate_double_indirect_block(self) -> Optional[int]:
        """
        分配双重间接块
        
        Returns:
            分配的块ID，失败返回None
        """
        return self.allocate_data_block()
    
    def read_indirect_block(self, block_id: int) -> List[int]:
        """
        读取间接块中的块索引列表
        
        Args:
            block_id: 间接块ID
        
        Returns:
            块索引列表
        """
        try:
            data = self.read_block(block_id)
            if data:
                return pickle.loads(data)
            return []
        except Exception:
            return []
    
    def write_indirect_block(self, block_id: int, block_indices: List[int]) -> bool:
        """
        写入间接块中的块索引列表
        
        Args:
            block_id: 间接块ID
            block_indices: 块索引列表
        
        Returns:
            是否成功
        """
        try:
            data = pickle.dumps(block_indices)
            self.write_block(block_id, data)
            return True
        except Exception:
            return False
    
    def get_file_block_indices(self, inode) -> List[int]:
        """
        获取文件的所有数据块索引（包括间接块）
        
        Args:
            inode: 文件的i节点
        
        Returns:
            所有数据块索引的列表
        """
        block_indices = []
        
        # 直接块
        block_indices.extend(inode.data_block_indices)
        
        # 间接块
        for indirect_block_id in inode.indirect_block_indices:
            indirect_indices = self.read_indirect_block(indirect_block_id)
            block_indices.extend(indirect_indices)
        
        # 双重间接块
        for double_indirect_block_id in inode.double_indirect_block_indices:
            double_indirect_indices = self.read_indirect_block(double_indirect_block_id)
            for indirect_block_id in double_indirect_indices:
                indirect_indices = self.read_indirect_block(indirect_block_id)
                block_indices.extend(indirect_indices)
        
        return block_indices
    
    def allocate_file_blocks(self, inode, required_blocks: int) -> bool:
        """
        为文件分配所需的数据块
        
        Args:
            inode: 文件的i节点
            required_blocks: 需要的块数量
        
        Returns:
            是否成功
        """
        try:
            # 计算还需要多少块
            current_blocks = len(inode.data_block_indices)
            for indirect_block_id in inode.indirect_block_indices:
                indirect_indices = self.read_indirect_block(indirect_block_id)
                current_blocks += len(indirect_indices)
            for double_indirect_block_id in inode.double_indirect_block_indices:
                double_indirect_indices = self.read_indirect_block(double_indirect_block_id)
                for indirect_block_id in double_indirect_indices:
                    indirect_indices = self.read_indirect_block(indirect_block_id)
                    current_blocks += len(indirect_indices)
            
            needed_blocks = required_blocks - current_blocks
            if needed_blocks <= 0:
                return True
            
            # 优先使用直接块
            direct_blocks_needed = min(needed_blocks, 12 - len(inode.data_block_indices))
            for _ in range(direct_blocks_needed):
                block_id = self.allocate_data_block()
                if block_id is None:
                    return False
                inode.data_block_indices.append(block_id)
                inode.blocks_count += 1
            
            needed_blocks -= direct_blocks_needed
            if needed_blocks <= 0:
                return True
            
            # 使用间接块
            blocks_per_indirect = self.superblock.block_size // 4  # 假设块索引是4字节
            
            while needed_blocks > 0:
                # 检查是否需要新的间接块
                if len(inode.indirect_block_indices) == 0 or \
                   len(self.read_indirect_block(inode.indirect_block_indices[-1])) >= blocks_per_indirect:
                    # 分配新的间接块
                    new_indirect_block = self.allocate_indirect_block()
                    if new_indirect_block is None:
                        return False
                    inode.indirect_block_indices.append(new_indirect_block)
                    inode.blocks_count += 1
                
                # 在最后一个间接块中添加块索引
                last_indirect_block_id = inode.indirect_block_indices[-1]
                indirect_indices = self.read_indirect_block(last_indirect_block_id)
                
                block_id = self.allocate_data_block()
                if block_id is None:
                    return False
                
                indirect_indices.append(block_id)
                self.write_indirect_block(last_indirect_block_id, indirect_indices)
                inode.blocks_count += 1
                needed_blocks -= 1
            
            return True
            
        except Exception:
            return False
    
    def free_file_blocks(self, inode) -> None:
        """
        释放文件的所有数据块
        
        Args:
            inode: 文件的i节点
        """
        try:
            # 释放直接块
            for block_id in inode.data_block_indices:
                self.free_data_block(block_id)
            
            # 释放间接块
            for indirect_block_id in inode.indirect_block_indices:
                # 先释放间接块指向的数据块
                indirect_indices = self.read_indirect_block(indirect_block_id)
                for block_id in indirect_indices:
                    self.free_data_block(block_id)
                # 再释放间接块本身
                self.free_data_block(indirect_block_id)
            
            # 释放双重间接块
            for double_indirect_block_id in inode.double_indirect_block_indices:
                # 先释放双重间接块指向的间接块
                double_indirect_indices = self.read_indirect_block(double_indirect_block_id)
                for indirect_block_id in double_indirect_indices:
                    # 释放间接块指向的数据块
                    indirect_indices = self.read_indirect_block(indirect_block_id)
                    for block_id in indirect_indices:
                        self.free_data_block(block_id)
                    # 释放间接块本身
                    self.free_data_block(indirect_block_id)
                # 再释放双重间接块本身
                self.free_data_block(double_indirect_block_id)
                
        except Exception:
            pass