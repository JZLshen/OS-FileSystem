import sys
import time
from PyQt6.QtWidgets import QApplication

from fs_core.disk_manager import DiskManager
from fs_core.persistence_manager import PersistenceManager, DEFAULT_DISK_IMAGE_PATH
from user_management.user_auth import UserAuthenticator
from gui.login_window import LoginWindow
from gui.main_window import MainWindow

# Import backend operation functions
from fs_core.dir_ops import (
    make_directory,
    list_directory,
    change_directory,
    _resolve_path_to_inode_id,
    remove_directory,
)
from fs_core.file_ops import (
    create_file,
    delete_file,
    open_file,
    close_file,
    write_file,
    read_file,
)
from fs_core.datastructures import FileType
from fs_core.fs_utils import get_inode_path_str


def main_application_loop(
    disk: DiskManager, auth: UserAuthenticator, pm: PersistenceManager
):
    """
    Main text-based command loop, entered after successful GUI login.
    """
    # Login is now handled by GUI, so auth.current_user should be set.
    if not auth.get_current_user():
        print("Critical Error: No user session found after login. Exiting.")
        return

    print(
        f"\n--- Simulated File System Shell (User: {auth.get_current_user().username}) ---"
    )
    # Welcome message can be part of GUI login success or here.
    # print(f"Welcome, {auth.current_user.username}!")

    # --- Command Loop ---
    while True:
        current_user_obj = auth.get_current_user()
        if not current_user_obj:
            print("User logged out. Exiting shell.")
            break

        cwd_inode_id = auth.get_cwd_inode_id()
        if (
            cwd_inode_id is None
            or disk.superblock is None
            or disk.superblock.root_inode_id is None
        ):
            print("Error: Critical CWD or disk issue. Exiting loop.")
            break

        prompt_cwd_display = get_inode_path_str(disk, cwd_inode_id)

        try:
            command_input = input(
                f"{current_user_obj.username}@{prompt_cwd_display}$ "
            ).strip()
        except EOFError:
            print("\nExiting (EOF received).")
            break
        except KeyboardInterrupt:  # Allow Ctrl+C to break the inner loop gracefully
            print(
                "\nCommand loop interrupted by user (Ctrl+C). Type 'exit' to quit application."
            )
            continue

        if not command_input:
            continue

        parts = command_input.split()
        command = parts[0].lower()
        args = parts[1:]

        if command == "exit" or command == "quit":
            print("Exiting command loop.")
            break
        elif command == "mkdir":
            if len(args) == 1:
                dir_name = args[0]
                uid = current_user_obj.uid
                success_mkdir, msg_mkdir, _ = make_directory(
                    disk, uid, cwd_inode_id, dir_name
                )
                print(msg_mkdir)
                if success_mkdir:
                    pm.save_disk_image(disk)
            else:
                print("Usage: mkdir <directory_name>")
        elif command == "ls" or command == "dir":
            target_list_inode = cwd_inode_id
            path_to_list = "."
            if args:
                path_to_list = args[0]
                if disk.superblock is None:
                    print("Error: Disk not properly initialized for path resolution.")
                    continue
                resolved_target_inode_id = _resolve_path_to_inode_id(
                    disk, cwd_inode_id, disk.superblock.root_inode_id, path_to_list
                )
                if resolved_target_inode_id is not None:
                    target_list_inode_obj = disk.get_inode(resolved_target_inode_id)
                    if (
                        target_list_inode_obj
                        and target_list_inode_obj.type == FileType.DIRECTORY
                    ):
                        target_list_inode = resolved_target_inode_id
                    elif (
                        target_list_inode_obj
                        and target_list_inode_obj.type == FileType.FILE
                    ):
                        permissions_oct = oct(target_list_inode_obj.permissions)
                        print(
                            f"-{permissions_oct[2:]:<4} {target_list_inode_obj.link_count:2d} uid:{target_list_inode_obj.owner_uid:<3} {target_list_inode_obj.size:6d}B "
                            f"{time.strftime('%b %d %H:%M', time.localtime(target_list_inode_obj.mtime))} {path_to_list.split('/')[-1]}"
                        )
                        continue
                    else:
                        print(
                            f"Error: Cannot access '{path_to_list}': No such file or directory, or not a directory for listing."
                        )
                        continue
                else:
                    print(
                        f"Error: Cannot access '{path_to_list}': No such file or directory"
                    )
                    continue

            success_ls, msg_ls, contents = list_directory(disk, target_list_inode)
            if success_ls and contents is not None:
                if not contents:
                    current_path_name_for_msg = (
                        "Current directory"
                        if target_list_inode == cwd_inode_id and path_to_list == "."
                        else f"Directory '{path_to_list}'"
                    )
                    print(f"({current_path_name_for_msg} is empty)")
                for item in contents:
                    perm_str = item.get("permissions", "---")
                    item_type_char = (
                        "d" if item.get("type") == FileType.DIRECTORY.name else "-"
                    )
                    link_cnt = item.get("link_count", 0)
                    owner = item.get("owner_uid", "N/A")
                    size = item.get("size", 0)
                    mtime_val = item.get("mtime", 0)
                    mtime_readable = (
                        time.strftime("%b %d %H:%M", time.localtime(mtime_val))
                        if mtime_val
                        else "N/A"
                    )
                    name = item.get("name", "N/A")
                    print(
                        f"{item_type_char}{perm_str[2:]:<4} {link_cnt:2d} uid:{owner:<3} {size:6d}B {mtime_readable} {name}"
                    )
            elif not success_ls:
                print(msg_ls)

        elif command == "cd" or command == "chdir":
            if len(args) == 1:
                target_path_str = args[0]
                if disk.superblock is None:
                    print("Error: Disk not properly initialized for cd.")
                    continue
                success_cd, msg_cd, new_potential_cwd_id = change_directory(
                    disk, cwd_inode_id, disk.superblock.root_inode_id, target_path_str
                )
                print(msg_cd)
                if success_cd and new_potential_cwd_id is not None:
                    auth.set_cwd_inode_id(new_potential_cwd_id)
            else:
                print("Usage: cd <path>")
        elif command == "pwd":
            current_path_for_pwd = get_inode_path_str(disk, cwd_inode_id)
            print(current_path_for_pwd)
        elif command == "logout":
            success_logout, msg_logout = auth.logout()
            print(msg_logout)
            if success_logout:
                break
        elif command == "create" or command == "touch":
            if len(args) == 1:
                file_name = args[0]
                if current_user_obj is None:
                    print("Error: No current user.")
                    continue
                uid = current_user_obj.uid
                success_create, msg_create, _ = create_file(
                    disk, uid, cwd_inode_id, file_name
                )
                print(msg_create)
                if success_create:
                    pm.save_disk_image(disk)
            else:
                print(f"Usage: {command} <file_name>")
        elif command == "rm":
            if len(args) == 1:
                file_name_to_del = args[0]
                if current_user_obj is None or cwd_inode_id is None:
                    print("Error: User or CWD not properly set.")
                    continue
                uid = current_user_obj.uid
                if (
                    "/" in file_name_to_del
                ):  # Basic check, proper path resolution for parent needed for full support
                    # For now, only allow deleting from CWD if path is complex
                    # This part would need a helper to get (parent_inode_id, actual_name) from a path
                    resolved_target_inode_id = _resolve_path_to_inode_id(
                        disk,
                        cwd_inode_id,
                        disk.superblock.root_inode_id,
                        file_name_to_del,
                    )
                    if resolved_target_inode_id is not None:
                        # Need to find parent of resolved_target_inode_id and the name component
                        # This is complex, for now, we simplify or disallow
                        print(
                            "Error: rm with full paths not fully implemented. Delete files from CWD by name only for now."
                        )
                        continue
                    else:
                        print(f"Error: File or path '{file_name_to_del}' not found.")
                        continue
                else:
                    parent_for_rm = cwd_inode_id
                    actual_file_name_for_rm = file_name_to_del

                success_delete, msg_delete = delete_file(
                    disk, uid, parent_for_rm, actual_file_name_for_rm
                )
                print(msg_delete)
                if success_delete:
                    pm.save_disk_image(disk)
            else:
                print("Usage: rm <file_name_in_cwd>")
        elif command == "rmdir":
            if len(args) == 1:
                dir_name_to_del = args[0]
                if current_user_obj is None or cwd_inode_id is None:
                    print("Error: User or CWD not properly set.")
                    continue
                uid = current_user_obj.uid
                if "/" in dir_name_to_del:  # Similar limitation as rm for now
                    print(
                        "Error: rmdir with paths (/) not yet fully supported. Please provide dirname in CWD."
                    )
                    continue
                else:
                    parent_for_rmdir = cwd_inode_id
                    actual_dir_name_for_rmdir = dir_name_to_del
                success_rmdir, msg_rmdir = remove_directory(
                    disk, uid, parent_for_rmdir, actual_dir_name_for_rmdir
                )
                print(msg_rmdir)
                if success_rmdir:
                    pm.save_disk_image(disk)
            else:
                print("Usage: rmdir <directory_name_in_cwd>")
        elif command == "open":
            if len(args) == 2:
                file_path_to_open = args[0]
                mode_to_open = args[1]
                success_open, msg_open, fd_open = open_file(
                    disk, auth, file_path_to_open, mode_to_open
                )
                print(msg_open)
            else:
                print("Usage: open <file_path> <mode (r, w, a, r+)>")
        elif command == "close":
            if len(args) == 1:
                try:
                    fd_to_close = int(args[0])
                    success_close, msg_close = close_file(auth, fd_to_close)
                    print(msg_close)
                except ValueError:
                    print("Error: File descriptor must be an integer.")
            else:
                print("Usage: close <file_descriptor>")
        elif command == "oft" or command == "fds":
            if auth.current_user and auth.current_user_open_files:
                print("Currently open file descriptors:")
                for fd_num, oft_entry_obj in auth.current_user_open_files.items():
                    print(f"  FD: {fd_num}, {oft_entry_obj}")
            else:
                print("No files are currently open by this user.")
        elif command == "write":
            if len(args) >= 2:
                try:
                    fd_to_write = int(args[0])
                    content_to_write_str = " ".join(args[1:])
                    if content_to_write_str.startswith(
                        '"'
                    ) and content_to_write_str.endswith('"'):
                        content_to_write_str = content_to_write_str[1:-1]
                    elif content_to_write_str.startswith(
                        "'"
                    ) and content_to_write_str.endswith("'"):
                        content_to_write_str = content_to_write_str[1:-1]

                    success_write, msg_write, bytes_written = write_file(
                        disk, auth, fd_to_write, content_to_write_str
                    )
                    print(msg_write)
                    if (
                        success_write
                        and bytes_written is not None
                        and bytes_written > 0
                    ):
                        pm.save_disk_image(disk)
                except ValueError:
                    print("Error: File descriptor must be an integer.")
                except Exception as e:
                    print(f"Error during write operation: {e}")
            else:
                print('Usage: write <file_descriptor> "content to write"')
        elif command == "read":
            if len(args) == 2:
                try:
                    fd_to_read = int(args[0])
                    num_bytes = int(args[1])

                    if num_bytes < 0:
                        print("Error: Number of bytes to read cannot be negative.")
                        continue

                    success_read, msg_read, bytes_data_read = read_file(
                        disk, auth, fd_to_read, num_bytes
                    )

                    if success_read and bytes_data_read is not None:
                        if not bytes_data_read and num_bytes > 0:
                            print(msg_read)
                        else:
                            try:
                                decoded_content = bytes_data_read.decode("utf-8")
                                print(
                                    f"Read {len(bytes_data_read)} bytes from fd {fd_to_read}:"
                                )
                                print("---BEGIN CONTENT---")
                                print(decoded_content)
                                print("---END CONTENT---")
                            except UnicodeDecodeError:
                                print(
                                    f"Read {len(bytes_data_read)} bytes (binary data or wrong encoding) from fd {fd_to_read}:"
                                )
                                print(f"Raw bytes: {bytes_data_read}")
                    else:
                        print(msg_read)

                except ValueError:
                    print(
                        "Error: File descriptor and number of bytes must be integers."
                    )
                except Exception as e:
                    print(f"Error during read operation: {e}")
            else:
                print("Usage: read <file_descriptor> <num_bytes_to_read>")
        else:
            if command:  # Only print if a command was actually typed
                print(f"Command not found: {command}")

    print("Simulated file system session ended.")


if __name__ == "__main__":
    # 1. 初始化PyQt应用程序实例 (任何GUI组件都需要)
    app = QApplication(sys.argv)

    # 2. 初始化后端核心组件
    pm = PersistenceManager()
    auth = UserAuthenticator()  # 用户认证器实例

    # 尝试加载磁盘镜像
    print(f"Attempting to load disk image from '{DEFAULT_DISK_IMAGE_PATH}'...")
    loaded_disk = pm.load_disk_image()

    if loaded_disk:
        disk = loaded_disk
        print("Disk loaded from image.")
    else:
        print(
            "No existing disk image found or failed to load. Initializing a new DiskManager."
        )
        disk = DiskManager()
        # 如果磁盘是全新的，它是未格式化的。
        # LoginWindow -> auth.login -> main_application_loop(如果保留) 中的逻辑需要处理这种情况，
        # 例如，在登录后，如果磁盘未格式化，主应用(GUI或文本)应提示用户格式化。

    # 3. 显示登录窗口
    # 将 authenticator 和 disk manager 实例传递给 LoginWindow。
    # 这要求 LoginWindow 的 __init__ 方法能够接收 disk_manager_instance，
    # 并且其 handle_login 方法能够使用 disk_manager 来获取 root_inode_id 以便调用 auth.login()。
    login_dialog = LoginWindow(
        user_authenticator_instance=auth, disk_manager_instance=disk
    )

    login_successful = False
    # login_dialog.exec() 会以模态方式显示对话框，并阻塞直到对话框关闭。
    # 如果 LoginWindow 调用了 self.accept() (通常在登录逻辑成功后)，exec() 返回 True (或等效的Accepted值)。
    # 如果调用了 self.reject() 或用户关闭了对话框，返回 False (或等效的Rejected值)。
    if login_dialog.exec():
        # 再次检查 UserAuthenticator 是否真的有用户登录，以确认后端登录也成功了
        if auth.get_current_user():
            print(f"GUI Login successful for user: {auth.get_current_user().username}.")
            login_successful = True
        else:
            # 这种情况可能发生在 login_dialog.accept() 被调用了（例如，在UI的测试模式下），
            # 但 UserAuthenticator 内部并没有成功建立用户会话。
            print(
                "Login dialog was accepted, but no user session established in authenticator. Exiting."
            )
            # login_successful 保持 False
    else:
        print("Login canceled or failed via GUI. Exiting application.")
        # login_successful 保持 False

    # 4. 如果通过GUI登录成功，则创建并显示主GUI窗口
    main_gui_window = None  # 初始化以备后用
    if login_successful:
        # 检查磁盘是否需要格式化 (特别是如果这是一个新创建的磁盘实例)
        if not disk.is_formatted:
            print("Disk is not formatted (checked after successful login).")
            # 在实际的GUI应用中，这里可能会弹出一个对话框提示用户格式化，
            # 或者主窗口自己处理未格式化磁盘的情况。
            # 为了继续，我们可以在这里强制格式化或让用户决定（当前文本模式是在main_application_loop中处理）
            # 暂时，我们依赖主窗口或后续逻辑（如果仍调用文本循环）来处理。
            # 重要的是，主窗口现在将是主要的交互界面。

        main_gui_window = MainWindow(
            disk_manager_instance=disk,
            user_authenticator_instance=auth,
            persistence_manager_instance=pm,
        )
        main_gui_window.show()
        # QApplication的事件循环将在下面通过 app.exec() 启动
    else:
        # 如果登录不成功，应用程序将退出
        print("Application will exit due to login failure or cancellation from GUI.")
        sys.exit(1)  # 退出并返回一个错误码

    # 5. 启动Qt主事件循环
    # 这将使应用程序保持运行，处理事件，直到最后一个窗口关闭或调用了 app.quit()。
    # 当所有Qt窗口（如此处是 main_gui_window）关闭后，app.exec() 才会返回。
    exit_code = app.exec()

    # 此部分代码在Qt事件循环结束后执行 (例如，当主窗口被关闭时)
    # 磁盘的保存现在主要由 MainWindow 的 closeEvent 方法处理，以确保优雅关闭。
    # 此处的保存可以作为备用，但如果 MainWindow 处理得当，可能就是多余的。
    print("\nApplication event loop finished.")
    # if disk and disk.is_formatted:
    #     print("Attempting to save disk image (final check, should be handled by MainWindow.closeEvent)...")
    #     # pm.save_disk_image(disk) # 通常 MainWindow 的 closeEvent 会处理最终保存
    # else:
    #     print("Disk not saved by main.py exit (ensure MainWindow.closeEvent handles saving).")

    print("Application closed.")
    sys.exit(exit_code)
