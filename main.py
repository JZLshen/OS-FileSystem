import sys
from PyQt6.QtWidgets import QApplication
from fs_core.disk_manager import DiskManager
from user_management.user_auth import UserAuthenticator
from gui.login_window import LoginWindow
from gui.main_window import MainWindow

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 创建磁盘管理器
    disk_manager = DiskManager()
    
    # 创建用户认证器
    user_auth = UserAuthenticator()
    
    # 显示登录窗口
    login_window = LoginWindow(user_auth)
    if login_window.exec() == 1:  # 登录成功
        # 创建主窗口
        main_window = MainWindow(disk_manager=disk_manager, user_auth=user_auth)
        main_window.show()
        
        # 运行应用程序
        sys.exit(app.exec())
    else:
        print("登录失败或用户取消")
        sys.exit(0)

if __name__ == "__main__":
    main()