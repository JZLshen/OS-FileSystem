from typing import Optional, Dict, Tuple
from fs_core.datastructures import OpenFileEntry

# 可以在 config.py 中定义默认用户，这里先硬编码
DEFAULT_USERS_DATA = {
    "root": {
        "uid": 0,
        "password": "root",
        "home_inode_id": None,
    },  # home_inode_id 可以在格式化后设置
    "guest": {"uid": 1000, "password": "guest", "home_inode_id": None},
}
# ROOT_UID 应该与 disk_manager.py 中的 ROOT_UID 一致
ROOT_UID = 0


class User:
    """
    用户信息类
    """

    def __init__(
        self,
        username: str,
        password: str,
        uid: int,
        group_id: int = 0,
        is_admin: bool = False,
        home_inode_id: Optional[int] = None,
    ):
        self.username = username
        self.password = password
        self.uid = uid
        self.group_id = group_id
        self.is_admin = is_admin
        self.home_inode_id = home_inode_id

    def __repr__(self) -> str:
        return f"User(uid={self.uid}, username='{self.username}', group_id={self.group_id}, is_admin={self.is_admin})"


class UserAuthenticator:
    """
    用户认证和会话管理
    """

    def __init__(self):
        self.users: Dict[str, User] = {}
        self._load_default_users()

        self.current_user: Optional[User] = None
        self.current_user_cwd_inode_id: Optional[int] = None

        self.current_user_open_files: Dict[int, OpenFileEntry] = {}
        self._next_fd: int = 0

    def _load_default_users(self):
        """加载/初始化默认用户"""
        for username, data in DEFAULT_USERS_DATA.items():
            self.users[username] = User(
                username=username,
                password=data["password"],
                uid=data["uid"],
                group_id=0,
                is_admin=False,
                home_inode_id=data.get("home_inode_id"),
            )
        print(f"Initialized users: {list(self.users.keys())}")

    def login(
        self,
        username: str,
        password_plaintext: str,
        root_inode_id: Optional[int] = None,
    ) -> Tuple[bool, str]:
        if self.current_user:
            return (
                False,
                f"Another user '{self.current_user.username}' is already logged in. Please logout first.",
            )

        user = self.users.get(username)
        if not user:
            return False, f"Login failed: User '{username}' not found."

        if user.password == password_plaintext:
            self.current_user = user
            if user.uid == ROOT_UID and root_inode_id is not None:
                self.current_user_cwd_inode_id = root_inode_id
            elif user.home_inode_id is not None:
                self.current_user_cwd_inode_id = user.home_inode_id
            elif root_inode_id is not None:  # Fallback to root if user home not set
                self.current_user_cwd_inode_id = root_inode_id
            else:
                self.current_user_cwd_inode_id = (
                    None  # Should not happen if disk is formatted
                )

            self.current_user_open_files = {}
            self._next_fd = 0
            return (
                True,
                f"User '{username}' logged in successfully. CWD set to inode {self.current_user_cwd_inode_id}.",
            )
        else:
            return False, f"Login failed: Incorrect password for user '{username}'."

    def logout(self) -> Tuple[bool, str]:
        if self.current_user:
            username = self.current_user.username
            if self.current_user_open_files:
                print(
                    f"Warning: User '{username}' logged out with {len(self.current_user_open_files)} open file(s). Forcing close."
                )
                self.current_user_open_files.clear()

            self.current_user = None
            self.current_user_cwd_inode_id = None
            self._next_fd = 0
            return True, f"User '{username}' logged out successfully."
        else:
            return False, "Logout failed: No user is currently logged in."

    def create_user(
        self,
        username: str,
        password: str,
        group_id: int = 0,
        is_admin: bool = False,
    ) -> Tuple[bool, str]:
        if not username:
            return False, "错误：用户名不能为空。"
        if username in self.users:
            return False, f"错误：用户 '{username}' 已存在。"

        assigned_uid: int
        existing_uids = {user.uid for user in self.users.values()}

        if not existing_uids:  # 如果除了默认用户外没有其他用户了
            assigned_uid = 1000
        else:
            # 确保从现有最大非root UID之后开始，或者至少是1000
            max_non_root_uid = 0
            for uid_val in existing_uids:
                if uid_val != ROOT_UID and uid_val > max_non_root_uid:
                    max_non_root_uid = uid_val
            assigned_uid = max(1000, max_non_root_uid + 1)

        while assigned_uid in existing_uids or assigned_uid == ROOT_UID:
            assigned_uid += 1

        # 实际应用中，密码应哈希存储
        # password_hash_to_store = some_hash_function(password)
        password_hash_to_store = password  # 保持项目当前简化逻辑

        user = User(
            username=username,
            password=password_hash_to_store,
            uid=assigned_uid,
            group_id=group_id,
            is_admin=is_admin,
        )
        self.users[username] = user
        print(
            f"User '{username}' (UID: {assigned_uid}) created and added to self.users list."
        )
        return True, f"用户 '{username}' (UID: {assigned_uid}) 创建成功。"

    def get_current_user_uid(self) -> Optional[int]:
        return self.current_user.uid if self.current_user else None

    def get_current_user(self) -> Optional[User]:
        return self.current_user

    def get_cwd_inode_id(self) -> Optional[int]:
        if self.current_user:
            return self.current_user_cwd_inode_id
        return None

    def set_cwd_inode_id(self, inode_id: int) -> bool:
        if self.current_user:
            self.current_user_cwd_inode_id = inode_id
            return True
        return False

    def allocate_fd(self, oft_entry: OpenFileEntry) -> int:
        if not self.current_user:
            print("Error: No user logged in to allocate fd for.")
            return -1

        fd_to_assign = 0
        while fd_to_assign in self.current_user_open_files:
            fd_to_assign += 1

        self.current_user_open_files[fd_to_assign] = oft_entry
        if (
            fd_to_assign >= self._next_fd
        ):  # _next_fd 只是一个优化提示，实际分配是查找最小可用
            self._next_fd = fd_to_assign + 1
        return fd_to_assign

    def get_oft_entry(self, fd: int) -> Optional[OpenFileEntry]:
        if not self.current_user:
            return None
        return self.current_user_open_files.get(fd)

    def release_fd(self, fd: int) -> bool:
        if not self.current_user:
            return False
        if fd in self.current_user_open_files:
            del self.current_user_open_files[fd]
            return True
        return False


# 为了向后兼容，创建一个别名
UserAuth = UserAuthenticator