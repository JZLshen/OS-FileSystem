import time
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QDialogButtonBox,
    QScrollArea,
    QWidget,
)
from PyQt6.QtCore import Qt


class PropertiesDialog(QDialog):
    def __init__(self, item_details: dict, parent=None):
        super().__init__(parent)
        self.item_details = item_details
        self.setWindowTitle(f"属性 - {item_details.get('name', 'N/A')}")
        self.setMinimumWidth(450)  # 设置最小宽度
        self.setMinimumHeight(400)  # 设置最小高度

        main_layout = QVBoxLayout(self)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area)

        content_widget = QWidget()
        scroll_area.setWidget(content_widget)

        form_layout = QFormLayout(content_widget)
        form_layout.setRowWrapPolicy(
            QFormLayout.RowWrapPolicy.WrapAllRows
        )  # 允许长内容换行
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)  # 标签左对齐
        form_layout.setFormAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )  # 表单整体左上对齐

        def format_permissions(perm_octal_str, item_type_str):
            try:
                if not perm_octal_str or not perm_octal_str.startswith("0o"):
                    return "N/A (无效格式)" if perm_octal_str else "N/A"
                p = int(perm_octal_str, 8)

                # 假设 item_type_str 是 'DIRECTORY' 或 'FILE' (来自 FileType.DIRECTORY.name)
                type_char = "d" if item_type_str == "DIRECTORY" else "-"

                modes = [type_char]
                for i in range(3):
                    perm_group = (p >> (6 - i * 3)) & 0b111
                    modes.append("r" if perm_group & 0b100 else "-")
                    modes.append("w" if perm_group & 0b010 else "-")
                    modes.append("x" if perm_group & 0b001 else "-")
                return "".join(modes)
            except ValueError:
                return f"N/A (转换错误: {perm_octal_str})"
            except Exception as e:
                return f"N/A (未知错误: {e})"

        def add_read_only_row(label_text, value_text):
            line_edit = QLineEdit(str(value_text))
            line_edit.setReadOnly(True)
            line_edit.setStyleSheet(
                "QLineEdit { background-color: #f0f0f0; border: 1px solid #cccccc; }"
            )  # 浅灰色背景
            form_layout.addRow(label_text, line_edit)

        add_read_only_row("名称:", item_details.get("name", "N/A"))
        add_read_only_row("类型:", item_details.get("type", "N/A"))

        full_path_le = QLineEdit(str(item_details.get("full_path", "N/A")))
        full_path_le.setReadOnly(True)
        full_path_le.setCursorPosition(0)  # 从头显示
        full_path_le.setStyleSheet(
            "QLineEdit { background-color: #f0f0f0; border: 1px solid #cccccc; }"
        )
        form_layout.addRow("完整路径:", full_path_le)

        size_val = item_details.get("size", 0)
        if (
            item_details.get("type") == "DIRECTORY"
        ):  # 假设 FileType.DIRECTORY.name == "DIRECTORY"
            add_read_only_row("大小:", f"{size_val} (条目数)")
        else:
            add_read_only_row("大小:", f"{size_val} 字节")

        add_read_only_row("所有者 UID:", str(item_details.get("owner_uid", "N/A")))

        permissions_oct_str = str(item_details.get("permissions", "0o000"))
        item_type_for_perm = str(
            item_details.get("type", "FILE")
        )  # 默认为文件类型以生成权限字符串
        permissions_rwx_str = format_permissions(
            permissions_oct_str, item_type_for_perm
        )
        add_read_only_row("权限:", f"{permissions_rwx_str} ({permissions_oct_str})")

        def format_time(timestamp):
            return (
                time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
                if timestamp and timestamp > 0
                else "N/A"
            )

        add_read_only_row(
            "修改日期 (mtime):", format_time(item_details.get("mtime", 0))
        )
        add_read_only_row(
            "访问日期 (atime):", format_time(item_details.get("atime", 0))
        )
        add_read_only_row(
            "状态更改 (ctime):", format_time(item_details.get("ctime", 0))
        )

        add_read_only_row("Inode ID:", str(item_details.get("inode_id", "N/A")))
        add_read_only_row("链接数:", str(item_details.get("link_count", "N/A")))
        add_read_only_row("占用块数:", str(item_details.get("blocks_count", "N/A")))

        # 新增：加密和压缩状态
        is_encrypted = item_details.get("is_encrypted", False)
        is_compressed = item_details.get("is_compressed", False)
        add_read_only_row("加密状态:", "是" if is_encrypted else "否")
        add_read_only_row("压缩状态:", "是" if is_compressed else "否")

        # 新增：文件系统信息
        add_read_only_row("文件系统:", "模拟UNIX文件系统")
        add_read_only_row("块大小:", str(item_details.get("block_size", "512")) + " 字节")

        # 新增：访问统计
        access_count = item_details.get("access_count", 0)
        add_read_only_row("访问次数:", str(access_count))

        # 新增：创建时间（如果有）
        ctime = item_details.get("ctime", 0)
        if ctime > 0:
            add_read_only_row("创建时间:", format_time(ctime))

        # 新增：文件类型详细信息
        file_type = item_details.get("type", "未知")
        if file_type == "DIRECTORY":
            add_read_only_row("目录项数:", str(item_details.get("size", 0)))
        elif file_type == "SYMBOLIC_LINK":
            target_path = item_details.get("target_path", "N/A")
            add_read_only_row("目标路径:", target_path)
        else:
            add_read_only_row("文件类型:", "普通文件")

        # 新增：权限详细信息
        permissions = item_details.get("permissions", 0o644)
        owner_perms = (permissions >> 6) & 0b111
        group_perms = (permissions >> 3) & 0b111
        other_perms = permissions & 0b111
        
        perm_details = f"所有者: {oct(owner_perms)[2:]} 组: {oct(group_perms)[2:]} 其他: {oct(other_perms)[2:]}"
        add_read_only_row("权限详情:", perm_details)

        # 新增：文件状态
        status_items = []
        if is_encrypted:
            status_items.append("已加密")
        if is_compressed:
            status_items.append("已压缩")
        if item_details.get("is_hardlink", False):
            status_items.append("硬链接")
        if not status_items:
            status_items.append("正常")
        add_read_only_row("文件状态:", ", ".join(status_items))

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        main_layout.addWidget(button_box)
