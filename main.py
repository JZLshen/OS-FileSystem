import sys
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QTimer
from fs_core.disk_manager import DiskManager
from fs_core.persistence_manager import PersistenceManager
from fs_core.error_handler import get_global_error_handler, set_global_error_handler, ErrorHandler, ErrorSeverity, ErrorCategory
from user_management.user_auth import UserAuthenticator
from gui.login_window import LoginWindow
from gui.main_window import MainWindow

def setup_global_error_handler():
    """设置全局错误处理器"""
    error_handler = ErrorHandler()
    set_global_error_handler(error_handler)
    
    def global_exception_handler(exc_type, exc_value, exc_traceback):
        """全局异常处理器"""
        if error_handler:
            error_handler.log_error(
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.SYSTEM,
                message=f"未捕获的异常: {exc_type.__name__}: {exc_value}",
                exception=exc_value,
                context={
                    "traceback": traceback.format_tb(exc_traceback)
                }
            )
    
    sys.excepthook = global_exception_handler
    return error_handler

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置全局错误处理器
    error_handler = setup_global_error_handler()
    
    try:
        # 初始化持久化管理器
        persistence_manager = PersistenceManager()
        # 优先尝试加载磁盘镜像
        disk_manager = persistence_manager.load_disk_image()
        if disk_manager is None:
            print("未找到现有磁盘镜像，创建新的磁盘管理器")
            disk_manager = DiskManager()
        
        # 初始化用户认证
        user_auth = UserAuthenticator()
        
        # 显示登录窗口
        login_window = LoginWindow(user_auth, disk_manager)
        if login_window.exec() == 1:  # 使用1代替LoginWindow.Accepted
            # 登录成功，显示主窗口
            main_window = MainWindow(disk_manager=disk_manager, user_auth=user_auth)
            main_window.show()
            
            # 设置应用程序关闭时的保存回调
            def save_on_exit():
                try:
                    print("正在保存磁盘镜像...")
                    if persistence_manager.save_disk_image(disk_manager):
                        print("磁盘镜像保存成功")
                        error_handler.log_error(
                            severity=ErrorSeverity.INFO,
                            category=ErrorCategory.SYSTEM,
                            message="磁盘镜像保存成功"
                        )
                    else:
                        print("磁盘镜像保存失败")
                        error_handler.log_error(
                            severity=ErrorSeverity.ERROR,
                            category=ErrorCategory.SYSTEM,
                            message="磁盘镜像保存失败"
                        )
                except Exception as e:
                    error_handler.log_error(
                        severity=ErrorSeverity.ERROR,
                        category=ErrorCategory.SYSTEM,
                        message=f"保存磁盘镜像时发生异常: {e}",
                        exception=e
                    )
            
            app.aboutToQuit.connect(save_on_exit)
            
            # 运行应用程序
            sys.exit(app.exec())
        else:
            print("登录失败或用户取消")
            # 即使登录失败也要保存磁盘镜像
            try:
                print("正在保存磁盘镜像...")
                if persistence_manager.save_disk_image(disk_manager):
                    print("磁盘镜像保存成功")
                else:
                    print("磁盘镜像保存失败")
            except Exception as e:
                error_handler.log_error(
                    severity=ErrorSeverity.ERROR,
                    category=ErrorCategory.SYSTEM,
                    message=f"登录失败后保存磁盘镜像时发生异常: {e}",
                    exception=e
                )
            sys.exit(0)
            
    except Exception as e:
        error_handler.log_error(
            severity=ErrorSeverity.CRITICAL,
            category=ErrorCategory.SYSTEM,
            message=f"程序启动时发生严重错误: {e}",
            exception=e
        )
        QMessageBox.critical(None, "启动错误", f"程序启动失败:\n{e}")
        sys.exit(1)

if __name__ == "__main__":
    main()