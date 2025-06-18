from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QMessageBox,
    QSizePolicy,
)
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtCore import Qt

from fs_core.file_ops import open_file, read_file, write_file, close_file
from fs_core.datastructures import OpenFileEntry, Inode


class TextEditorDialog(QDialog):
    def __init__(
        self,
        disk_manager,
        user_auth,
        persistence_manager,
        file_path_str,
        file_name,
        parent=None,
    ):
        super().__init__(parent)
        self.dm = disk_manager
        self.auth = user_auth
        self.pm = persistence_manager
        self.file_path = file_path_str  # 完整路径字符串，供 open_file 使用
        self.file_name = file_name

        self.fd = None
        self.is_edit_mode = False
        self.original_content_on_edit_start = ""  # 用于比较是否真的发生修改

        self.setWindowTitle(f"{self.file_name} - 只读模式")
        self.setGeometry(200, 200, 700, 500)  # x, y, width, height

        self._setup_ui()
        self._initial_load()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)  # 初始只读
        self.text_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.text_edit)

        button_layout = QHBoxLayout()
        self.edit_button = QPushButton("编辑")
        self.edit_button.clicked.connect(self._toggle_edit_mode)
        button_layout.addWidget(self.edit_button)

        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self._save_file)
        self.save_button.setVisible(False)  # 初始隐藏
        button_layout.addWidget(self.save_button)

        button_layout.addStretch()

        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(
            self.reject
        )  # reject 会尝试关闭窗口，触发 closeEvent
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

    def _initial_load(self):
        """以只读模式加载文件内容"""
        self._open_and_read_file(read_only=True)
        # self.text_edit.document().setModified(False) 在 _open_and_read_file 中处理

    def _open_and_read_file(self, read_only=True):
        if self.fd is not None:
            # 关闭之前打开的文件描述符
            success_close, msg_close = close_file(self.auth, self.fd)
            if not success_close:
                QMessageBox.warning(
                    self, "关闭旧文件失败", f"关闭旧文件描述符失败: {msg_close}"
                )
            self.fd = None

        mode_str = "r" if read_only else "r+"
        success_open, msg_open, new_fd = open_file(
            self.dm, self.auth, self.file_path, mode_str
        )

        if success_open and new_fd is not None:
            self.fd = new_fd

            oft_entry = self.auth.get_oft_entry(self.fd)
            if oft_entry and oft_entry.inode_ref:
                file_size_to_read = oft_entry.inode_ref.size
            else:
                QMessageBox.critical(
                    self,
                    "错误",
                    f"无法获取文件 {self.file_path} 的详细信息 (OFT 条目)。",
                )
                self.text_edit.setPlainText(f"打开文件后无法获取元数据: {msg_open}")
                self.edit_button.setEnabled(False)
                if self.fd is not None:  # 尝试关闭刚打开的FD
                    close_file(self.auth, self.fd)
                    self.fd = None
                return

            success_read, msg_read, content_bytes = read_file(
                self.dm, self.auth, self.fd, file_size_to_read
            )

            if success_read and content_bytes is not None:
                try:
                    decoded_content = content_bytes.decode("utf-8")
                    self.text_edit.setPlainText(decoded_content)
                    if self.is_edit_mode:
                        self.original_content_on_edit_start = decoded_content
                    # 清除因 setPlainText 带来的 modified 状态，确保初始加载时不认为文件被修改过
                    self.text_edit.document().setModified(False)
                except UnicodeDecodeError:
                    self.text_edit.setPlainText("错误：文件内容无法以UTF-8解码。")
                    QMessageBox.warning(
                        self, "解码错误", "文件内容可能不是有效的UTF-8编码文本。"
                    )
                    self.edit_button.setEnabled(False)
            else:
                self.text_edit.setPlainText(f"读取文件内容失败: {msg_read}")
                QMessageBox.critical(self, "读取失败", f"无法读取文件内容: {msg_read}")
                self.edit_button.setEnabled(False)
        else:
            self.text_edit.setPlainText(f"打开文件失败: {msg_open}")
            QMessageBox.critical(
                self, "打开失败", f"无法打开文件 '{self.file_path}': {msg_open}"
            )
            self.edit_button.setEnabled(False)

    def _toggle_edit_mode(self):
        if not self.is_edit_mode:  # 从只读切换到编辑
            self.is_edit_mode = True
            self.setWindowTitle(f"{self.file_name} - 编辑模式")
            self._open_and_read_file(read_only=False)  # 以 r+ 模式重新打开
            if self.fd is None:  # 如果重新打开失败
                self.is_edit_mode = False  # 切换失败，恢复状态
                self.setWindowTitle(f"{self.file_name} - 只读模式")
                return

            self.text_edit.setReadOnly(False)
            # original_content_on_edit_start 和 setModified(False) 已在 _open_and_read_file 中处理
            self.edit_button.setText("取消编辑")
            self.save_button.setVisible(True)
            self.text_edit.setFocus()
        else:  # 从编辑切换回只读 (或取消编辑)
            if self.text_edit.document().isModified():
                reply = QMessageBox.question(
                    self,
                    "未保存的更改",
                    "您有未保存的更改。要保存吗？",
                    QMessageBox.StandardButton.Save
                    | QMessageBox.StandardButton.Discard
                    | QMessageBox.StandardButton.Cancel,
                )
                if reply == QMessageBox.StandardButton.Save:
                    if not self._save_file():
                        return
                elif reply == QMessageBox.StandardButton.Cancel:
                    return

            self.is_edit_mode = False
            self.setWindowTitle(f"{self.file_name} - 只读模式")
            self._open_and_read_file(read_only=True)
            self.text_edit.setReadOnly(True)
            # self.text_edit.document().setModified(False) 已在 _open_and_read_file 中处理
            self.edit_button.setText("编辑")
            self.save_button.setVisible(False)

    def _save_file(self):
        if not self.is_edit_mode or self.fd is None:
            QMessageBox.warning(self, "保存错误", "文件未处于编辑模式或未正确打开。")
            return False

        current_content_str = self.text_edit.toPlainText()

        oft_entry = self.auth.get_oft_entry(self.fd)
        if oft_entry:
            oft_entry.offset = 0  # 关键：重置偏移量以覆盖
        else:
            QMessageBox.critical(self, "保存错误", "无法获取文件打开信息（OFT条目）。")
            return False

        # 再次强调：下面的 write_file 需要能正确处理文件覆盖和可能的截断
        success_write, msg_write, bytes_written = write_file(
            self.dm, self.auth, self.fd, current_content_str
        )

        if success_write:
            QMessageBox.information(self, "保存成功", f"文件已保存，共写入 {bytes_written} 字节。")
            self.text_edit.document().setModified(False)
            self.original_content_on_edit_start = current_content_str
            
            # 强制关闭文件描述符，避免资源泄漏
            if self.fd is not None:
                close_file(self.auth, self.fd)
                self.fd = None
            
            return True
        else:
            QMessageBox.critical(self, "保存失败", f"写入文件失败: {msg_write}")
            return False

    def closeEvent(self, event: QCloseEvent):
        """窗口关闭事件处理"""
        if self.text_edit.document().isModified():
            reply = QMessageBox.question(
                self,
                "未保存的更改",
                "您有未保存的更改。要保存吗？",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                if not self._save_file():
                    event.ignore()  # 保存失败，阻止关闭
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()  # 取消关闭
                return

        # 确保关闭文件描述符
        if self.fd is not None:
            close_file(self.auth, self.fd)
            self.fd = None

        event.accept()

    def reject(self):
        """拒绝对话框（关闭按钮）"""
        # 检查是否有未保存的更改
        if self.text_edit.document().isModified():
            reply = QMessageBox.question(
                self,
                "未保存的更改",
                "您有未保存的更改。要保存吗？",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                if not self._save_file():
                    return  # 保存失败，不关闭
            elif reply == QMessageBox.StandardButton.Cancel:
                return  # 取消关闭

        # 确保关闭文件描述符
        if self.fd is not None:
            close_file(self.auth, self.fd)
            self.fd = None

        super().reject()
