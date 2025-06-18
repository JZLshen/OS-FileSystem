import time
from enum import Enum
from typing import List, Dict, Optional


# 定义文件类型枚举
class FileType(Enum):
    FILE = 1
    DIRECTORY = 2
    SYMBOLIC_LINK = 3


# 定义权限常量
class Permissions:
    READ = 0b100  # 4
    WRITE = 0b010  # 2
    EXECUTE = 0b001  # 1
    # 示例: 读写权限 = READ | WRITE = 0b110 = 6


class Inode:
    """
    i节点 (文件或目录的元数据)
    """

    def __init__(
        self,
        inode_id: int,
        file_type: FileType,
        owner_uid: int,
        permissions: int = (Permissions.READ | Permissions.WRITE),
        group_id: int = 0,  # 新增：所属组ID
        is_encrypted: bool = False,  # 新增：加密标记
        is_compressed: bool = False,  # 新增：压缩标记
    ):
        self.id: int = inode_id  # i节点编号
        self.type: FileType = file_type  # 文件类型 (FILE 或 DIRECTORY)
        self.size: int = 0  # 文件大小 (字节) / 目录中条目数 (一种可能的实现)
        self.blocks_count: int = 0  # 占用的数据块数量
        self.data_block_indices: List[int] = []  # 直接块索引
        self.indirect_block_indices: List[int] = []  # 新增：单级间接块索引
        self.double_indirect_block_indices: List[int] = []  # 新增：双级间接块索引
        self.owner_uid: int = owner_uid  # 所有者用户ID
        self.group_id: int = group_id  # 新增：所属组ID
        self.permissions: int = permissions  # 权限 (简化版)
        current_time = int(time.time())
        self.atime: int = current_time  # 最后访问时间 (access time)
        self.mtime: int = (
            current_time  # 最后修改时间 (modification time) - 文件内容修改
        )
        self.ctime: int = current_time  # 最后状态更改时间 (change time) - 元数据修改
        self.link_count: int = 1  # 硬链接计数 (用于删除文件/目录)
        self.is_encrypted: bool = is_encrypted  # 新增：加密标记
        self.is_compressed: bool = is_compressed  # 新增：压缩标记

    def __repr__(self) -> str:
        return (
            f"Inode(id={self.id}, type='{self.type.name}', size={self.size}, "
            f"owner_uid={self.owner_uid}, group_id={self.group_id}, permissions={oct(self.permissions)}, "
            f"links={self.link_count}, encrypted={self.is_encrypted}, compressed={self.is_compressed})"
        )


class DirectoryEntry:
    """
    目录项 (用于在目录的数据块中存储条目)
    """

    def __init__(self, name: str, inode_id: int, is_hardlink: bool = False):
        if "/" in name:  # 简单检查，目录项名不应包含路径分隔符
            raise ValueError("DirectoryEntry name cannot contain '/'")
        if len(name) > 255:  # 简单文件名长度限制
            raise ValueError("DirectoryEntry name too long (max 255 chars)")

        self.name: str = name  # 文件或目录名
        self.inode_id: int = inode_id  # 指向该文件或目录的i节点编号
        self.is_hardlink: bool = is_hardlink  # 新增：是否为硬链接

    def __repr__(self) -> str:
        return f"DirectoryEntry(name='{self.name}', inode_id={self.inode_id}, is_hardlink={self.is_hardlink})"


class Superblock:
    """
    超级块 (文件系统的总体信息)
    """

    def __init__(self, total_blocks: int, total_inodes: int, block_size: int):
        self.magic_number: int = 0x53494D4653  # "SIMFS"的ASCII表示, 用于校验
        self.total_blocks: int = total_blocks  # 总数据块数量
        self.total_inodes: int = total_inodes  # 总i节点数量
        self.block_size: int = block_size  # 每个数据块的大小 (字节)

        self.free_blocks_count: int = total_blocks
        self.free_inodes_count: int = total_inodes

        # 可以后续在 DiskManager 中具体实现空闲块和空闲i节点的管理方式
        # 例如: self.free_block_bitmap: List[bool]
        # 例如: self.free_inode_bitmap: List[bool]

        self.root_inode_id: Optional[int] = None  # 根目录 "/" 的 i节点ID

    def __repr__(self) -> str:
        return (
            f"Superblock(magic=0x{self.magic_number:X}, total_blocks={self.total_blocks}, "
            f"total_inodes={self.total_inodes}, block_size={self.block_size}, "
            f"root_inode_id={self.root_inode_id})"
        )


# 定义文件打开模式的枚举
class OpenMode(Enum):
    READ = 1  # r: 只读
    WRITE = 2  # w: 只写 (如果文件存在则清空，不存在则创建)
    APPEND = 3  # a: 追加 (如果文件不存在则创建)
    READ_WRITE = 4  # r+: 读写 (文件必须存在)
    # WRITE_READ_CREATE = 5 # w+: 读写 (清空或创建) - 更复杂的模式可以后续添加


class OpenFileEntry:
    """
    打开文件表中的条目 (OFT Entry)
    这个条目将由用户的"文件描述符表"直接持有。
    """

    def __init__(
        self, inode_id: int, mode: OpenMode, inode_ref: Inode
    ):  # 添加inode_ref方便访问size等
        self.inode_id: int = inode_id  # 文件的i节点ID
        self.inode_ref: Inode = (
            inode_ref  # 对文件Inode对象的直接引用 (方便快速获取size等)
        )
        self.mode: OpenMode = mode  # 打开模式 (READ, WRITE, APPEND, READ_WRITE)
        self.offset: int = 0  # 当前文件读写指针/偏移量

        if mode == OpenMode.APPEND:
            # 如果是追加模式，偏移量应初始化为文件末尾
            self.offset = inode_ref.size

    def __repr__(self) -> str:
        return (
            f"OpenFileEntry(inode_id={self.inode_id}, mode={self.mode.name}, "
            f"offset={self.offset}, file_size={self.inode_ref.size})"
        )
