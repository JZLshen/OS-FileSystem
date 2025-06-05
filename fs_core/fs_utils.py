from typing import Tuple, Optional, List

# 需要从其他模块导入必要的类和函数
from .datastructures import Inode, DirectoryEntry, FileType
from .disk_manager import DiskManager

# _read_directory_entries 用于读取目录内容
from .dir_ops import _read_directory_entries


def _get_inode_dot_dot_points_to(dm: DiskManager, dir_inode_id: int) -> Optional[int]:
    """
    对于给定的目录inode ID，读取其 ".." 条目，并返回 ".." 指向的inode ID。
    """
    dir_inode = dm.get_inode(dir_inode_id)
    if not dir_inode or dir_inode.type != FileType.DIRECTORY:
        # print(f"Debug _get_inode_dot_dot_points_to: {dir_inode_id} is not a directory or not found.")
        return None

    entries = _read_directory_entries(dm, dir_inode_id)
    if entries is None:
        # print(f"Debug _get_inode_dot_dot_points_to: Could not read entries for {dir_inode_id}.")
        return None

    for entry in entries:
        if entry.name == "..":
            return entry.inode_id

    # print(f"Debug _get_inode_dot_dot_points_to: '..' entry not found in {dir_inode_id}.")
    return None  # '..' 条目未找到 (理论上不应发生在格式正确的目录中，除了根的特殊情况)


def _find_name_of_child_in_parent(
    dm: DiskManager, parent_inode_id: int, child_inode_id: int
) -> Optional[str]:
    """
    在给定的父目录inode ID中，查找特定子inode ID对应的目录条目名称。
    """
    parent_inode = dm.get_inode(parent_inode_id)
    if not parent_inode or parent_inode.type != FileType.DIRECTORY:
        # print(f"Debug _find_name_of_child_in_parent: Parent {parent_inode_id} is not a directory or not found.")
        return None

    entries = _read_directory_entries(dm, parent_inode_id)
    if entries is None:
        # print(f"Debug _find_name_of_child_in_parent: Could not read entries for parent {parent_inode_id}.")
        return None

    for entry in entries:
        if entry.inode_id == child_inode_id:
            # 排除返回 "." 或 ".." 作为路径的一部分，除非它是最终目标（但通常不会）
            # if entry.name in ['.', '..'] and child_inode_id != parent_inode_id : # Be careful with root's . and ..
            #     continue
            return entry.name

    # print(f"Debug _find_name_of_child_in_parent: Child {child_inode_id} not found in parent {parent_inode_id}.")
    return None


def get_inode_path_str(dm: DiskManager, target_inode_id: int) -> str:
    """
    获取给定i节点ID的完整绝对路径字符串。
    Args:
        dm: DiskManager 实例。
        target_inode_id: 目标i节点的ID。
    Returns:
        str: 绝对路径字符串，或错误/未知路径的表示。
    """
    if not dm.superblock or dm.superblock.root_inode_id is None:
        return "[Error: Filesystem not initialized or no root]"

    root_inode_id = dm.superblock.root_inode_id

    if target_inode_id == root_inode_id:
        # 目标就是根目录
        target_inode = dm.get_inode(target_inode_id)
        if target_inode and target_inode.type == FileType.DIRECTORY:
            return "/"
        else:  # 根i节点不是目录或不存在（严重错误）
            return "[Error: Root inode is invalid]"

    path_segments: List[str] = []
    current_inode_id_to_find_name_for = target_inode_id

    # 安全计数器，防止因文件系统损坏（如 .. 循环）导致的死循环
    # 最大深度可以设置为系统中i节点的总数
    max_depth = dm.superblock.total_inodes
    safety_count = 0

    while current_inode_id_to_find_name_for != root_inode_id:
        if safety_count >= max_depth:
            return "[Error: Path resolution exceeded max depth or loop detected]"
        safety_count += 1

        # 1. 获取当前inode的父inode ID (通过读取当前inode的 '..' 条目)
        parent_actual_inode_id = _get_inode_dot_dot_points_to(
            dm, current_inode_id_to_find_name_for
        )

        if parent_actual_inode_id is None:
            # 无法找到当前inode的父inode (例如，当前inode不是目录，或者目录损坏没有'..')
            # 这也可能是因为 target_inode_id 是一个文件，文件本身没有 '..' 条目。
            # 对于文件，我们需要其父目录的ID来查找其名称。
            # 这个函数目前更适合查找目录的路径。如果target_inode_id是文件，
            # 调用者需要提供其父目录ID，或者我们需要不同的策略。
            # 假设调用者确保 target_inode_id 是目录，或者我们接受这种局限。
            # 如果是文件，我们需要一种方法来知道它的父目录ID。
            # 暂时，如果_get_inode_dot_dot_points_to失败，我们认为路径无法构建。
            return f"[Error: Could not determine parent of inode {current_inode_id_to_find_name_for}]"

        # 2. 在父目录中找到当前inode的名字
        name_in_parent = _find_name_of_child_in_parent(
            dm, parent_actual_inode_id, current_inode_id_to_find_name_for
        )

        if name_in_parent is None:
            # 在父目录中找不到当前inode的条目（文件系统不一致）
            return f"[Error: Inode {current_inode_id_to_find_name_for} not found in its supposed parent (inode {parent_actual_inode_id})]"

        path_segments.insert(0, name_in_parent)  # 将找到的名字插入到路径段列表的开头

        # 3. 更新当前处理的inode为其父inode，继续向上查找
        current_inode_id_to_find_name_for = parent_actual_inode_id

        # 如果父目录就是根目录，并且我们已经添加了当前节点的名字，那么路径构建完成
        if (
            current_inode_id_to_find_name_for == root_inode_id and name_in_parent
        ):  # name_in_parent确保不是根的自引用
            break

    # 组合路径段
    if not path_segments and target_inode_id != root_inode_id:
        # 如果没有收集到任何路径段，但目标又不是根，说明有问题
        # 这可能发生在target_inode_id的父目录就是根目录，但循环条件提前退出的情况
        # 应该在循环中正确处理了根的直接子节点
        # 或者target_inode_id的 '..' 直接指向了root，那么它的名字应该在root中找到
        # 如果上面逻辑正确，这里不应该执行
        return (
            f"[Error: Path for inode {target_inode_id} could not be fully constructed]"
        )

    final_path = "/" + "/".join(path_segments)
    return final_path
