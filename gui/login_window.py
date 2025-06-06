import sys
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)
from PyQt6.QtCore import Qt


class LoginWindow(QDialog):
    def __init__(
        self, user_authenticator_instance=None, disk_manager_instance=None
    ):  # 接收 UserAuthenticator 实例
        super().__init__()
        self.user_auth = user_authenticator_instance  # 保存实例引用
        self.disk_manager = disk_manager_instance
        self.logged_in_user = None  # 用于存储登录成功的用户对象

        self.setWindowTitle("模拟文件系统 - 登录")
        self.setGeometry(300, 300, 300, 150)  # x, y, width, height

        layout = QVBoxLayout()

        # 用户名行
        user_layout = QHBoxLayout()
        self.user_label = QLabel("用户名:")
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("请输入用户名 (如 root)")
        user_layout.addWidget(self.user_label)
        user_layout.addWidget(self.user_input)
        layout.addLayout(user_layout)

        # 密码行
        pass_layout = QHBoxLayout()
        self.pass_label = QLabel("密  码:")  # 使用中文空格对齐
        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("请输入密码 (如 root_password)")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)  # 设置为密码模式
        pass_layout.addWidget(self.pass_label)
        pass_layout.addWidget(self.pass_input)
        layout.addLayout(pass_layout)

        # 消息标签 (用于显示登录结果)
        self.message_label = QLabel("")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)  # 居中对齐
        layout.addWidget(self.message_label)

        # 按钮行
        button_layout = QHBoxLayout()
        self.login_button = QPushButton("登录")
        self.login_button.clicked.connect(
            self.handle_login
        )  # 连接点击事件到 handle_login 方法

        self.exit_button = QPushButton("退出")
        self.exit_button.clicked.connect(self.close)  # 点击退出直接关闭窗口

        button_layout.addStretch(1)  # 添加伸缩因子，使按钮靠右
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.exit_button)
        button_layout.addStretch(1)
        layout.addLayout(button_layout)

        self.setLayout(layout)

        # 允许按回车键触发登录
        self.user_input.returnPressed.connect(self.login_button.click)
        self.pass_input.returnPressed.connect(self.login_button.click)

    def handle_login(self):
        username = self.user_input.text()
        password = self.pass_input.text()

        if not username or not password:
            self.message_label.setText("<font color='red'>用户名和密码不能为空!</font>")
            return

        if self.user_auth:
            # 从 self.disk_manager 获取 root_inode_id
            # disk_manager 实例应该在 LoginWindow 初始化时通过构造函数传入并保存为 self.disk_manager
            root_id_for_login: Optional[int] = None  # 默认为 None

            if (
                hasattr(self, "disk_manager") and self.disk_manager
            ):  # 检查 disk_manager 是否存在
                if self.disk_manager.is_formatted and self.disk_manager.superblock:
                    root_id_for_login = self.disk_manager.superblock.root_inode_id
                elif not self.disk_manager.is_formatted:
                    # 磁盘未格式化，root_inode_id 自然是 None 或无效
                    # UserAuthenticator.login() 需要能处理这种情况（通常意味着CWD无法正确设置到根）
                    # 此时，主程序流程（如 main.py 中的 main_application_loop）在登录后应提示格式化
                    print(
                        "LoginWindow: Disk is not formatted. root_inode_id for login will be None."
                    )
            else:
                # disk_manager 未传递给 LoginWindow
                print(
                    "LoginWindow: DiskManager instance not available. root_inode_id for login will be None."
                )

            success, message = self.user_auth.login(
                username, password, root_inode_id=root_id_for_login
            )

            if success:
                self.message_label.setText(
                    f"<font color='green'>{message}</font>"
                )  # 显示登录成功及CWD信息
                self.logged_in_user = self.user_auth.get_current_user()  # 保存登录用户
                # QMessageBox.information(self, "登录成功", f"欢迎, {username}!") # 这条信息可以由主程序决定是否显示
                self.accept()  # 关闭对话框并返回接受状态
            else:
                self.message_label.setText(f"<font color='red'>{message}</font>")
                self.pass_input.clear()  # 登录失败，清空密码框
        else:
            # 这是UserAuthenticator实例未传递的情况，用于独立测试UI
            self.message_label.setText(
                "<font color='orange'>UserAuthenticator未配置 (UI测试模式)</font>"
            )
            # 模拟登录成功以便测试窗口关闭
            if username == "test" and password == "test":
                QMessageBox.information(
                    self, "登录成功 (模拟)", f"欢迎, {username}!"
                )  # 在模拟模式下也显示欢迎
                self.accept()
            else:
                self.message_label.setText(
                    "<font color='red'>模拟登录失败 (请输入 test/test)</font>"
                )
                self.pass_input.clear()


# 这部分用于独立测试 LoginWindow UI，实际应用中它会被主程序调用
if __name__ == "__main__":
    # from ..user_management.user_auth import UserAuthenticator # 用于独立测试时
    # auth_for_test = UserAuthenticator() # 创建一个实例

    app = QApplication(sys.argv)
    # login_win = LoginWindow(auth_for_test) # 传递实例
    login_win = LoginWindow()  # 不传递实例，进入UI测试模式

    # login_win.show() # 直接显示
    # sys.exit(app.exec())

    # 通常LoginWindow作为对话框使用
    if login_win.exec():  # 以模态对话框方式显示，exec()会阻塞直到对话框关闭
        print("登录成功 (模拟用户，如果 user_auth 未提供)")
        if login_win.logged_in_user:  # 如果真的登录了
            print(f"用户 {login_win.logged_in_user.username} 已登录")
        # 在这里可以打开主窗口
        # main_app_window = YourMainWindow()
        # main_app_window.show()
        # sys.exit(app.exec()) # 如果要保持应用运行以显示主窗口
    else:
        print("登录取消或失败。")
    sys.exit()  # 退出应用
