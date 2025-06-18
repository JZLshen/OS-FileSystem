from .datastructures import Inode, Permissions
import time
from typing import Tuple, Optional
from .datastructures import FileType
from .disk_manager import DiskManager
from user_management.user_auth import ROOT_UID


def check_permission(inode: Inode, user_uid: int, operation: str) -> bool:
    """
    检查用户是否有权限执行指定操作
    
    Args:
        inode: 目标i节点
        user_uid: 用户UID
        operation: 操作类型 ('read', 'write', 'execute', 'delete')
    
    Returns:
        bool: 是否有权限
    """
    # root用户拥有所有权限
    if user_uid == ROOT_UID:
        return True
    
    # 所有者权限检查
    if inode.owner_uid == user_uid:
        return _check_owner_permission(inode, operation)
    
    # 其他用户权限检查
    return _check_other_permission(inode, operation)


def _check_owner_permission(inode: Inode, operation: str) -> bool:
    """检查所有者权限"""
    permissions = inode.permissions
    
    if operation == 'read':
        return bool(permissions & (Permissions.READ << 6))
    elif operation == 'write':
        return bool(permissions & (Permissions.WRITE << 6))
    elif operation == 'execute':
        return bool(permissions & (Permissions.EXECUTE << 6))
    elif operation == 'delete':
        # 删除需要写权限
        return bool(permissions & (Permissions.WRITE << 6))
    else:
        return False


def _check_other_permission(inode: Inode, operation: str) -> bool:
    """检查其他用户权限"""
    permissions = inode.permissions
    
    if operation == 'read':
        return bool(permissions & Permissions.READ)
    elif operation == 'write':
        return bool(permissions & Permissions.WRITE)
    elif operation == 'execute':
        return bool(permissions & Permissions.EXECUTE)
    elif operation == 'delete':
        # 删除需要写权限
        return bool(permissions & Permissions.WRITE)
    else:
        return False


def can_read_file(inode: Inode, user_uid: int) -> bool:
    """检查是否可以读取文件"""
    return check_permission(inode, user_uid, 'read')


def can_write_file(inode: Inode, user_uid: int) -> bool:
    """检查是否可以写入文件"""
    return check_permission(inode, user_uid, 'write')


def can_execute_file(inode: Inode, user_uid: int) -> bool:
    """检查是否可以执行文件"""
    return check_permission(inode, user_uid, 'execute')


def can_delete_file(inode: Inode, user_uid: int) -> bool:
    """检查是否可以删除文件"""
    return check_permission(inode, user_uid, 'delete')


def can_access_directory(inode: Inode, user_uid: int) -> bool:
    """检查是否可以访问目录"""
    return check_permission(inode, user_uid, 'execute')


def can_modify_directory(inode: Inode, user_uid: int) -> bool:
    """检查是否可以修改目录（创建/删除文件）"""
    return check_permission(inode, user_uid, 'write')


def get_permission_string(permissions: int) -> str:
    """将权限数字转换为字符串表示"""
    def get_perm_char(perm_bits: int) -> str:
        chars = []
        chars.append('r' if perm_bits & Permissions.READ else '-')
        chars.append('w' if perm_bits & Permissions.WRITE else '-')
        chars.append('x' if perm_bits & Permissions.EXECUTE else '-')
        return ''.join(chars)
    
    owner_perm = (permissions >> 6) & 0b111
    group_perm = (permissions >> 3) & 0b111
    other_perm = permissions & 0b111
    
    return f"{get_perm_char(owner_perm)}{get_perm_char(group_perm)}{get_perm_char(other_perm)}"


def set_permission(inode: Inode, user_uid: int, new_permissions: int) -> bool:
    """
    设置文件权限
    
    Args:
        inode: 目标i节点
        user_uid: 执行操作的用户UID
        new_permissions: 新的权限值
    
    Returns:
        bool: 是否设置成功
    """
    # 只有所有者或root可以修改权限
    if user_uid != ROOT_UID and inode.owner_uid != user_uid:
        return False
    
    inode.permissions = new_permissions
    return True


def change_owner(inode: Inode, current_user_uid: int, new_owner_uid: int) -> bool:
    """
    更改文件所有者
    
    Args:
        inode: 目标i节点
        current_user_uid: 执行操作的用户UID
        new_owner_uid: 新的所有者UID
    
    Returns:
        bool: 是否更改成功
    """
    # 只有root可以更改所有者
    if current_user_uid != ROOT_UID:
        return False
    
    inode.owner_uid = new_owner_uid
    return True


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
