from .datastructures import Inode, Permissions


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
