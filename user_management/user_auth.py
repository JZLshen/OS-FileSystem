from typing import Optional, Dict, Tuple

# 假设 OpenFileEntry 定义在 fs_core.datastructures 中
# 如果您的项目结构使得这个导入有问题，您可能需要调整 OpenFileEntry 的位置或导入路径
from fs_core.datastructures import OpenFileEntry  # <--- 新增：导入 OpenFileEntry

# 可以在 config.py 中定义默认用户，这里先硬编码
DEFAULT_USERS_DATA = {
    "root": {
        "uid": 0,
        "password": "root_password",
        "home_inode_id": None,
    },  # home_inode_id 可以在格式化后设置
    "guest": {"uid": 1000, "password": "guest_password", "home_inode_id": None},
}
# ROOT_UID 应该与 disk_manager.py 中的 ROOT_UID 一致
ROOT_UID = 0


class User:
    """
    用户信息类
    """

    def __init__(
        self,
        uid: int,
        username: str,
        password_hash: str,
        home_inode_id: Optional[int] = None,
    ):
        self.uid: int = uid
        self.username: str = username
        self.password_hash: str = password_hash  # 实际应用中应存储密码的哈希值
        self.home_inode_id: Optional[int] = home_inode_id  # 用户家目录的i节点ID

    def __repr__(self) -> str:
        return f"User(uid={self.uid}, username='{self.username}', home_inode_id={self.home_inode_id})"


class UserAuthenticator:
    """
    用户认证和会话管理
    """

    def __init__(self):
        self.users: Dict[str, User] = {}
        self._load_default_users()

        self.current_user: Optional[User] = None
        self.current_user_cwd_inode_id: Optional[int] = None  # 已有：CWD i节点ID

        # 新增：当前用户打开的文件描述符表 {fd: OpenFileEntry}
        self.current_user_open_files: Dict[int, OpenFileEntry] = {}
        self._next_fd: int = 0  # 新增：用于分配简单的、递增的文件描述符

    def _load_default_users(self):
        """加载/初始化默认用户"""
        for username, data in DEFAULT_USERS_DATA.items():
            self.users[username] = User(
                uid=data["uid"],
                username=username,
                password_hash=data["password"],  # 简化：密码直接存储
                home_inode_id=data["home_inode_id"],
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

        if user.password_hash == password_plaintext:
            self.current_user = user
            # 设置初始CWD
            if user.uid == ROOT_UID and root_inode_id is not None:
                self.current_user_cwd_inode_id = root_inode_id
            elif user.home_inode_id is not None:
                self.current_user_cwd_inode_id = user.home_inode_id
            elif root_inode_id is not None:
                self.current_user_cwd_inode_id = root_inode_id
            else:
                self.current_user_cwd_inode_id = None

            # 新增：清空/重置打开文件相关状态
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

            # 新增：处理打开的文件
            if self.current_user_open_files:
                print(
                    f"Warning: User '{username}' logged out with {len(self.current_user_open_files)} open file(s). Forcing close."
                )
                self.current_user_open_files.clear()  # 清空打开文件表

            self.current_user = None
            self.current_user_cwd_inode_id = None
            self._next_fd = 0  # 新增：重置fd分配器

            return True, f"User '{username}' logged out successfully."
        else:
            return False, "Logout failed: No user is currently logged in."

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

    # --- 新增：文件描述符管理方法 ---
    def allocate_fd(self, oft_entry: OpenFileEntry) -> int:
        """为当前用户分配一个新的文件描述符并关联OFT条目。"""
        if not self.current_user:
            # 实际应用中，如果current_user为None，此方法不应被调用
            # 或者应该返回一个表示错误的特殊值（如-1）或抛出异常
            print("Error: No user logged in to allocate fd for.")
            return -1  # 返回-1表示错误

        # 简单的fd分配：查找最小的可用fd，从0开始
        fd_to_assign = 0
        while fd_to_assign in self.current_user_open_files:
            fd_to_assign += 1

        # 如果需要，可以限制最大fd数量或最大打开文件数
        # if fd_to_assign > MAX_OPEN_FILES_PER_USER:
        #     return -1 # 或抛出异常

        self.current_user_open_files[fd_to_assign] = oft_entry
        # 更新 _next_fd 不是必须的，如果总是查找最小可用fd
        # 但如果想让fd大致递增，可以在fd_to_assign >= self._next_fd时更新
        if fd_to_assign >= self._next_fd:
            self._next_fd = fd_to_assign + 1

        return fd_to_assign

    def get_oft_entry(self, fd: int) -> Optional[OpenFileEntry]:
        """根据文件描述符获取关联的OFT条目。"""
        if not self.current_user:
            return None
        return self.current_user_open_files.get(fd)

    def release_fd(self, fd: int) -> bool:
        """释放一个文件描述符及其关联的OFT条目。"""
        if not self.current_user:
            return False  # 或者抛出异常
        if fd in self.current_user_open_files:
            del self.current_user_open_files[fd]
            # 当fd被释放后，_next_fd 不需要改变，因为 allocate_fd 会查找最小可用fd
            # 如果 _next_fd 用于严格递增且不重用，则此处也不修改
            return True
        return False  # fd 不存在或不属于当前用户
