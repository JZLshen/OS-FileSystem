from .datastructures import Inode, Permissions
import time
from typing import Tuple, Optional
from .datastructures import FileType
from .disk_manager import DiskManager


def check_permission(inode: Inode, user_uid: int, required_permission: int) -> bool:
    """
    检查用户对inode是否拥有所需权限。
    Args:
        inode: 目标文件的 Inode 对象。
        user_uid: 当前用户的 UID。
        required_permission: 所需的权限位 (例如 Permissions.READ, Permissions.WRITE)。
    Returns:
        bool: True 如果有权限, False 如果没有。
    """
    if user_uid == 0:  # root 用户总是有权限
        return True

    if inode.owner_uid == user_uid:  # 文件所有者
        # 检查所有者权限位
        # 假设 inode.permissions 是一个整数，例如 0o754 (rwxr-xr--)
        # 例如，所有者权限在最高的3位: (inode.permissions >> 6) & required_permission == required_permission
        owner_perms = (inode.permissions >> 6) & 0b111
        if (owner_perms & required_permission) == required_permission:
            return True
    # (如果引入了组的概念，在这里添加组权限检查)
    else:  # 其他用户
        # 检查其他用户权限位
        # 例如，其他用户权限在最低的3位: (inode.permissions & 0b000111) & required_permission == required_permission
        other_perms = inode.permissions & 0b111
        if (other_perms & required_permission) == required_permission:
            return True

    return False


def chmod(
    disk: DiskManager,
    uid: int,
    target_inode_id: int,
    new_permissions: int
) -> Tuple[bool, str]:
    """
    修改文件或目录的权限
    
    Args:
        disk: 磁盘管理器
        uid: 执行操作的用户ID
        target_inode_id: 目标i节点ID
        new_permissions: 新的权限（八进制）
    
    Returns:
        (成功标志, 消息)
    """
    try:
        # 检查目标i节点是否存在
        target_inode = disk.get_inode(target_inode_id)
        if not target_inode:
            return False, f"错误：i节点 {target_inode_id} 不存在。"
        
        # 检查权限：只有文件所有者或root用户可以修改权限
        if uid != 0 and uid != target_inode.owner_uid:
            return False, "错误：只有文件所有者或root用户可以修改权限。"
        
        # 验证权限值
        if not (0 <= new_permissions <= 0o777):
            return False, "错误：权限值必须在 0-777 范围内。"
        
        # 更新权限
        old_permissions = target_inode.permissions
        target_inode.permissions = new_permissions
        target_inode.ctime = int(time.time())
        
        # 更新i节点表
        disk.inode_table[target_inode_id] = target_inode
        
        return True, f"权限已从 {oct(old_permissions)} 修改为 {oct(new_permissions)}。"
        
    except Exception as e:
        return False, f"修改权限时出错：{e}"


def chown(
    disk: DiskManager,
    uid: int,
    target_inode_id: int,
    new_owner_uid: int,
    new_group_id: Optional[int] = None
) -> Tuple[bool, str]:
    """
    修改文件或目录的所有者和组
    
    Args:
        disk: 磁盘管理器
        uid: 执行操作的用户ID
        target_inode_id: 目标i节点ID
        new_owner_uid: 新的所有者用户ID
        new_group_id: 新的组ID（可选）
    
    Returns:
        (成功标志, 消息)
    """
    try:
        # 检查目标i节点是否存在
        target_inode = disk.get_inode(target_inode_id)
        if not target_inode:
            return False, f"错误：i节点 {target_inode_id} 不存在。"
        
        # 检查权限：只有root用户可以修改所有者
        if uid != 0:
            return False, "错误：只有root用户可以修改文件所有者。"
        
        # 验证新的所有者ID
        if new_owner_uid < 0:
            return False, "错误：用户ID不能为负数。"
        
        # 更新所有者和组
        old_owner_uid = target_inode.owner_uid
        old_group_id = target_inode.group_id
        
        target_inode.owner_uid = new_owner_uid
        if new_group_id is not None:
            target_inode.group_id = new_group_id
        
        target_inode.ctime = int(time.time())
        
        # 更新i节点表
        disk.inode_table[target_inode_id] = target_inode
        
        group_msg = f"，组从 {old_group_id} 修改为 {target_inode.group_id}" if new_group_id is not None else ""
        return True, f"所有者已从 {old_owner_uid} 修改为 {new_owner_uid}{group_msg}。"
        
    except Exception as e:
        return False, f"修改所有者时出错：{e}"


def chgrp(
    disk: DiskManager,
    uid: int,
    target_inode_id: int,
    new_group_id: int
) -> Tuple[bool, str]:
    """
    修改文件或目录的组
    
    Args:
        disk: 磁盘管理器
        uid: 执行操作的用户ID
        target_inode_id: 目标i节点ID
        new_group_id: 新的组ID
    
    Returns:
        (成功标志, 消息)
    """
    try:
        # 检查目标i节点是否存在
        target_inode = disk.get_inode(target_inode_id)
        if not target_inode:
            return False, f"错误：i节点 {target_inode_id} 不存在。"
        
        # 检查权限：只有文件所有者或root用户可以修改组
        if uid != 0 and uid != target_inode.owner_uid:
            return False, "错误：只有文件所有者或root用户可以修改组。"
        
        # 验证新的组ID
        if new_group_id < 0:
            return False, "错误：组ID不能为负数。"
        
        # 更新组
        old_group_id = target_inode.group_id
        target_inode.group_id = new_group_id
        target_inode.ctime = int(time.time())
        
        # 更新i节点表
        disk.inode_table[target_inode_id] = target_inode
        
        return True, f"组已从 {old_group_id} 修改为 {new_group_id}。"
        
    except Exception as e:
        return False, f"修改组时出错：{e}"


def get_permissions_string(permissions: int) -> str:
    """
    将权限数字转换为字符串表示
    
    Args:
        permissions: 权限数字（八进制）
    
    Returns:
        权限字符串（如 "rwxr-xr-x"）
    """
    permission_chars = ['---', '--x', '-w-', '-wx', 'r--', 'r-x', 'rw-', 'rwx']
    
    owner = permission_chars[(permissions >> 6) & 0o7]
    group = permission_chars[(permissions >> 3) & 0o7]
    other = permission_chars[permissions & 0o7]
    
    return owner + group + other


def parse_permissions_string(permission_str: str) -> Optional[int]:
    """
    将权限字符串解析为数字
    
    Args:
        permission_str: 权限字符串（如 "rwxr-xr-x"）
    
    Returns:
        权限数字，解析失败返回None
    """
    if len(permission_str) != 9:
        return None
    
    permission_map = {'r': 4, 'w': 2, 'x': 1, '-': 0}
    
    try:
        owner = sum(permission_map[c] for c in permission_str[0:3])
        group = sum(permission_map[c] for c in permission_str[3:6])
        other = sum(permission_map[c] for c in permission_str[6:9])
        
        return (owner << 6) | (group << 3) | other
    except KeyError:
        return None


def check_access(
    inode,
    uid: int,
    operation: str
) -> bool:
    """
    检查用户是否有指定操作的权限
    
    Args:
        inode: 要检查的i节点
        uid: 用户ID
        operation: 操作类型 ("read", "write", "execute")
    
    Returns:
        是否有权限
    """
    # root用户拥有所有权限
    if uid == 0:
        return True
    
    # 所有者权限
    if inode.owner_uid == uid:
        if operation == "read" and (inode.permissions & 0o400):
            return True
        elif operation == "write" and (inode.permissions & 0o200):
            return True
        elif operation == "execute" and (inode.permissions & 0o100):
            return True
    
    # 组权限（简化实现）
    if inode.group_id == 0:  # 假设组ID为0表示默认组
        if operation == "read" and (inode.permissions & 0o040):
            return True
        elif operation == "write" and (inode.permissions & 0o020):
            return True
        elif operation == "execute" and (inode.permissions & 0o010):
            return True
    
    # 其他用户权限
    if operation == "read" and (inode.permissions & 0o004):
        return True
    elif operation == "write" and (inode.permissions & 0o002):
        return True
    elif operation == "execute" and (inode.permissions & 0o001):
        return True
    
    return False
