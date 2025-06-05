# main_window.py
import sys
import time
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeView,
    QTableView,
    QLineEdit,
    QSplitter,
    QStatusBar,
    QMenuBar,
    QSizePolicy,
    QStyle,
    QInputDialog,
    QMessageBox,
    QMenu,
    QHeaderView,
)
from PyQt6.QtGui import QAction, QStandardItemModel, QStandardItem, QIcon, QKeySequence
from PyQt6.QtCore import Qt, QSize, QModelIndex, QPoint

# 从您的项目中导入
from fs_core.dir_ops import (
    list_directory,
    make_directory,
    remove_directory,
    rename_item,
)  # 导入 rename_item
from fs_core.file_ops import create_file, delete_file
from fs_core.datastructures import (
    FileType,
    DirectoryEntry,
)  # Permissions 如果在此定义或在fs_utils

# from fs_core.datastructures import Permissions # 假设 Permissions 在此定义
from fs_core.fs_utils import get_inode_path_str

# from fs_core.fs_utils import check_permission # 假设权限检查函数在这里

from .text_editor_dialog import TextEditorDialog
from .properties_dialog import PropertiesDialog  # <-- 导入属性对话框

# 为自定义数据角色定义常量
INODE_ID_ROLE = Qt.ItemDataRole.UserRole
IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 1
TYPE_STR_ROLE = Qt.ItemDataRole.UserRole + 2
CHILDREN_LOADED_ROLE = Qt.ItemDataRole.UserRole + 3


class MainWindow(QMainWindow):
    def __init__(
        self,
        disk_manager_instance,
        user_authenticator_instance,
        persistence_manager_instance,
    ):
        super().__init__()
        self.disk_manager = disk_manager_instance
        self.user_auth = user_authenticator_instance
        self.pm = persistence_manager_instance

        current_user = self.user_auth.get_current_user()
        username = current_user.username if current_user else "N/A"
        self.current_cwd_inode_id = self.user_auth.get_cwd_inode_id()
        initial_path_str = "/"
        if (
            self.current_cwd_inode_id is not None
            and self.disk_manager
            and self.disk_manager.is_formatted
            and self.disk_manager.superblock
        ):
            initial_path_str = get_inode_path_str(
                self.disk_manager, self.current_cwd_inode_id
            )
        else:
            initial_path_str = "[Uninitialized Path]"

        self.setWindowTitle(f"模拟文件系统 - 用户: {username}")
        self.setGeometry(100, 100, 900, 600)

        self._create_base_actions()  # 创建所有QAction实例
        self._create_menus()  # 创建菜单栏并将QAction添加到菜单
        self._create_status_bar()

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        self.address_bar = QLineEdit(initial_path_str)
        self.address_bar.setReadOnly(True)
        main_layout.addWidget(self.address_bar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self.dir_tree_view = QTreeView()
        self.dir_tree_model = QStandardItemModel()
        self.dir_tree_view.setModel(self.dir_tree_model)
        self.dir_tree_view.setHeaderHidden(True)
        self.dir_tree_view.clicked.connect(self.on_directory_item_clicked)
        self.dir_tree_view.expanded.connect(self.on_tree_item_expanded)
        self.dir_tree_view.doubleClicked.connect(self.on_directory_item_clicked)
        self.splitter.addWidget(self.dir_tree_view)

        self.file_list_view = QTableView()
        self.file_list_model = QStandardItemModel()
        self.file_list_model.setHorizontalHeaderLabels(
            ["名称", "大小", "类型", "修改日期"]
        )
        self.file_list_view.setModel(self.file_list_model)
        self.file_list_view.setSelectionBehavior(
            QTableView.SelectionBehavior.SelectRows
        )
        self.file_list_view.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.file_list_view.verticalHeader().setVisible(False)
        self.file_list_view.horizontalHeader().setStretchLastSection(True)
        self.file_list_view.setAlternatingRowColors(True)
        self.file_list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list_view.customContextMenuRequested.connect(
            self._show_list_context_menu
        )
        self.file_list_view.doubleClicked.connect(
            self.on_item_double_clicked_in_list_view
        )
        self.splitter.addWidget(self.file_list_view)

        self.splitter.setSizes([250, 650])
        self.dir_tree_view.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.file_list_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(self.splitter)

        print(
            f"MainWindow initialized for user: {username}. Initial CWD inode: {self.current_cwd_inode_id}"
        )
        if (
            self.disk_manager
            and self.disk_manager.is_formatted
            and self.disk_manager.superblock
            and self.disk_manager.superblock.root_inode_id is not None
        ):
            root_inode_id = self.disk_manager.superblock.root_inode_id
            root_item = QStandardItem("/")
            root_item.setIcon(self._get_folder_icon())
            root_item.setEditable(False)
            root_item.setData(root_inode_id, INODE_ID_ROLE)
            root_item.setData(True, IS_DIR_ROLE)
            root_item.setData(False, CHILDREN_LOADED_ROLE)
            self.dir_tree_model.appendRow(root_item)
            self._populate_children_in_tree(root_item, root_inode_id)
            self.dir_tree_view.expand(root_item.index())
            self._populate_file_list_view(root_inode_id)
        else:
            self.status_bar.showMessage("错误：磁盘未格式化或无法访问根目录", 5000)

    def _get_folder_icon(self) -> QIcon:
        icon = QIcon.fromTheme("folder", QIcon.fromTheme("inode-directory"))
        if icon.isNull():
            style = self.style()
            icon = (
                style.standardIcon(style.StandardPixmap.SP_DirIcon)
                if style
                else QIcon()
            )
        return icon

    def _get_file_icon(self) -> QIcon:
        icon = QIcon.fromTheme("text-x-generic", QIcon.fromTheme("document-default"))
        if icon.isNull():
            style = self.style()
            icon = (
                style.standardIcon(style.StandardPixmap.SP_FileIcon)
                if style
                else QIcon()
            )
        return icon

    def _add_directory_to_tree(
        self, parent_item: QStandardItem, dir_name: str, inode_id: int
    ):
        item = QStandardItem(dir_name)
        item.setIcon(self._get_folder_icon())
        item.setEditable(False)
        item.setData(inode_id, INODE_ID_ROLE)
        item.setData(True, IS_DIR_ROLE)
        item.setData(False, CHILDREN_LOADED_ROLE)
        parent_item.appendRow(item)
        placeholder_item = QStandardItem()
        item.appendRow(placeholder_item)
        return item

    def _populate_children_in_tree(
        self, parent_q_item: QStandardItem, parent_inode_id: int
    ):
        if not self.disk_manager or not self.user_auth:
            return

        # 概念性权限检查 (请替换为您的实际 check_permission 调用)
        # current_user = self.user_auth.get_current_user()
        # parent_inode = self.disk_manager.get_inode(parent_inode_id)
        # if not parent_inode or not check_permission(parent_inode, current_user.uid, Permissions.READ | Permissions.EXECUTE):
        #     parent_q_item.setData(True, CHILDREN_LOADED_ROLE) # 标记为已尝试加载
        #     # 可以选择性地显示一个 "权限不足" 的子项或清空
        #     # parent_q_item.removeRows(0, parent_q_item.rowCount())
        #     # print(f"权限不足，无法列出目录 inode {parent_inode_id}")
        #     return

        parent_q_item.removeRows(0, parent_q_item.rowCount())
        success, _, entries = list_directory(self.disk_manager, parent_inode_id)

        if not success or entries is None:
            parent_q_item.setData(True, CHILDREN_LOADED_ROLE)
            return

        entries.sort(
            key=lambda x: (
                x.get("type") != FileType.DIRECTORY.name,
                x.get("name", "").lower(),
            )
        )

        if not entries:
            parent_q_item.setData(True, CHILDREN_LOADED_ROLE)
            return

        for entry in entries:
            if entry.get("type") == FileType.DIRECTORY.name:
                if entry.get("name") in [".", ".."]:
                    continue
                self._add_directory_to_tree(
                    parent_q_item, entry.get("name"), entry.get("inode_id")
                )
        parent_q_item.setData(True, CHILDREN_LOADED_ROLE)

    def on_tree_item_expanded(self, index: QModelIndex):
        if not index.isValid():
            return
        item_being_expanded = self.dir_tree_model.itemFromIndex(index)
        if not item_being_expanded:
            return
        if not item_being_expanded.data(CHILDREN_LOADED_ROLE):
            item_inode_id = item_being_expanded.data(INODE_ID_ROLE)
            if item_inode_id is not None:
                self._populate_children_in_tree(item_being_expanded, item_inode_id)

    def on_directory_item_clicked(self, index: QModelIndex):
        if not index.isValid():
            return
        item_inode_id = index.data(INODE_ID_ROLE)
        item_is_dir = index.data(IS_DIR_ROLE)

        if item_inode_id is not None and item_is_dir:
            # 概念性权限检查
            # current_user = self.user_auth.get_current_user()
            # target_inode = self.disk_manager.get_inode(item_inode_id)
            # if not target_inode or not check_permission(target_inode, current_user.uid, Permissions.EXECUTE):
            #     QMessageBox.warning(self, "权限不足", f"无法访问目录。")
            #     return

            self.current_cwd_inode_id = item_inode_id
            self.user_auth.set_cwd_inode_id(
                item_inode_id
            )  # 更新 UserAuthenticator 中的 CWD
            self.address_bar.setText(
                get_inode_path_str(self.disk_manager, item_inode_id)
            )
            self._populate_file_list_view(item_inode_id)

    def on_item_double_clicked_in_list_view(self, index: QModelIndex):
        if not index.isValid():
            return
        row = index.row()
        name_column_model_index = self.file_list_model.index(row, 0)
        item_inode_id = self.file_list_model.data(
            name_column_model_index, INODE_ID_ROLE
        )
        item_is_dir = self.file_list_model.data(name_column_model_index, IS_DIR_ROLE)
        item_name = self.file_list_model.data(
            name_column_model_index, Qt.ItemDataRole.DisplayRole
        )

        if item_inode_id is None or item_name is None:
            return

        if item_is_dir:
            # 概念性权限检查
            # current_user = self.user_auth.get_current_user()
            # target_inode = self.disk_manager.get_inode(item_inode_id)
            # if not target_inode or not check_permission(target_inode, current_user.uid, Permissions.EXECUTE):
            #     QMessageBox.warning(self, "权限不足", f"无法进入目录 '{item_name}'。")
            #     return
            print(f"ListView: Directory '{item_name}' double-clicked. Navigating...")
            self.current_cwd_inode_id = item_inode_id
            self.user_auth.set_cwd_inode_id(item_inode_id)
            current_path_str = get_inode_path_str(self.disk_manager, item_inode_id)
            self.address_bar.setText(current_path_str)
            self._populate_file_list_view(item_inode_id)
            self._expand_and_select_in_tree(item_inode_id)
        else:  # File
            print(
                f"ListView: File '{item_name}' (inode {item_inode_id}) double-clicked."
            )
            is_text_file = any(
                item_name.lower().endswith(ext)
                for ext in [".txt", ".py", ".md", ".json", ".csv", ".log"]
            )
            if is_text_file:
                parent_path_for_file = get_inode_path_str(
                    self.disk_manager, self.current_cwd_inode_id
                )
                if parent_path_for_file.startswith("[Error"):
                    QMessageBox.critical(
                        self, "错误", f"无法确定父目录路径以打开 '{item_name}'。"
                    )
                    return
                file_path_str = (
                    f"/{item_name}"
                    if parent_path_for_file == "/"
                    else f"{parent_path_for_file}/{item_name}"
                )

                editor_dialog = TextEditorDialog(
                    self.disk_manager,
                    self.user_auth,
                    self.pm,
                    file_path_str,
                    item_name,
                    self,
                )
                editor_dialog.exec()
                self._refresh_current_views()
            else:
                self._gui_action_show_properties(item_inode_id_to_show=item_inode_id)

    def _expand_and_select_in_tree(self, target_inode_id: int):
        print(
            f"TODO: Implement robust expand and select in tree for inode {target_inode_id}"
        )

    def _populate_file_list_view(self, dir_inode_id: int):
        self.file_list_model.setRowCount(0)
        # 概念性权限检查
        # current_user = self.user_auth.get_current_user()
        # dir_inode = self.disk_manager.get_inode(dir_inode_id)
        # if not dir_inode or not check_permission(dir_inode, current_user.uid, Permissions.READ):
        #     self.status_bar.showMessage(f"权限不足，无法读取目录 inode {dir_inode_id}", 3000)
        #     return

        self.status_bar.showMessage(
            f"正在加载目录 inode {dir_inode_id} 的内容...", 2000
        )
        success, _, entries = list_directory(self.disk_manager, dir_inode_id)
        if not success or entries is None:
            self.status_bar.showMessage(
                f"无法读取目录 inode {dir_inode_id} 的内容: {entries if entries else '未知错误'}",
                3000,
            )  # 更具体的错误提示
            return

        if entries:
            entries.sort(
                key=lambda x: (
                    x.get("type") != FileType.DIRECTORY.name,
                    x.get("name", "").lower(),
                )
            )
            for entry in entries:
                if entry.get("name") == "." or entry.get("name") == "..":
                    continue
                name_str = entry.get("name", "N/A")
                size_val = entry.get("size", 0)
                type_str = entry.get("type", "UNKNOWN")  # FileType.XXX.name
                mtime_val = entry.get("mtime", 0)

                name_item = QStandardItem(name_str)
                name_item.setEditable(False)
                name_item.setData(entry.get("inode_id"), INODE_ID_ROLE)
                name_item.setData(type_str == FileType.DIRECTORY.name, IS_DIR_ROLE)
                name_item.setData(type_str, TYPE_STR_ROLE)
                name_item.setIcon(
                    self._get_folder_icon()
                    if type_str == FileType.DIRECTORY.name
                    else self._get_file_icon()
                )

                size_item = QStandardItem(
                    f"{size_val} B" if type_str != FileType.DIRECTORY.name else ""
                )
                size_item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                size_item.setEditable(False)

                type_display_item = QStandardItem(type_str)
                type_display_item.setEditable(False)

                mtime_readable = (
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime_val))
                    if mtime_val and mtime_val > 0
                    else "N/A"
                )
                date_item = QStandardItem(mtime_readable)
                date_item.setEditable(False)
                self.file_list_model.appendRow(
                    [name_item, size_item, type_display_item, date_item]
                )

    def _create_base_actions(self):
        """创建所有QAction实例并设置它们。"""
        self.new_folder_action = QAction(
            self._get_folder_icon(), "新建文件夹(&N)...", self
        )
        self.new_folder_action.setStatusTip("在当前位置创建一个新文件夹")
        self.new_folder_action.triggered.connect(self._gui_action_new_folder)

        self.new_file_action = QAction(self._get_file_icon(), "新建文件(&F)...", self)
        self.new_file_action.setStatusTip("在当前位置创建一个新空文件")
        self.new_file_action.triggered.connect(self._gui_action_new_file)

        delete_icon = QIcon.fromTheme("edit-delete", QIcon.fromTheme("list-remove"))
        if delete_icon.isNull():
            style = self.style()
            delete_icon = (
                style.standardIcon(style.StandardPixmap.SP_TrashIcon)
                if style
                else QIcon()
            )
        self.delete_action = QAction(delete_icon, "删除(&D)", self)
        self.delete_action.setShortcut(QKeySequence("Delete"))
        self.delete_action.setStatusTip("删除选中的文件或文件夹")
        self.delete_action.triggered.connect(
            self._gui_action_delete_item_from_selection
        )

        exit_icon_menu = QIcon.fromTheme("application-exit")
        if exit_icon_menu.isNull():
            style = self.style()
            exit_icon_menu = (
                style.standardIcon(style.StandardPixmap.SP_DialogCloseButton)
                if style
                else QIcon()
            )
        self.exit_action = QAction(exit_icon_menu, "&退出", self)
        self.exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self.exit_action.setStatusTip("退出应用程序")
        self.exit_action.triggered.connect(self.close)

        # 重命名动作
        rename_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_FileDialogListView
        )  # 使用一个不同的标准图标
        self.rename_action = QAction(rename_icon, "重命名(&R)...", self)
        self.rename_action.setStatusTip("重命名选中的文件或文件夹")
        self.rename_action.setShortcut(QKeySequence("F2"))
        self.rename_action.triggered.connect(self._gui_action_rename_item)

        # 属性动作
        properties_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_FileDialogInfoView
        )
        self.properties_action = QAction(properties_icon, "属性(&I)", self)
        self.properties_action.setStatusTip("查看选中项目的属性")
        # 这个action的triggered主要用于主菜单（如果添加的话）。上下文菜单会动态创建。
        self.properties_action.triggered.connect(self._gui_action_show_properties)

    def _create_menus(self):
        """创建菜单栏并将已定义的QAction添加到菜单。"""
        menu_bar = self.menuBar()
        self.file_menu = menu_bar.addMenu("&文件")

        self.file_menu.addAction(self.new_folder_action)
        self.file_menu.addAction(self.new_file_action)
        self.file_menu.addAction(self.rename_action)  # 添加重命名到主菜单
        self.file_menu.addAction(self.properties_action)  # 添加属性到主菜单
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.delete_action)
        self.file_menu.addSeparator()
        self.file_menu.addAction(self.exit_action)

    def _create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("准备就绪", 3000)

    def closeEvent(self, event):
        if self.disk_manager and self.disk_manager.is_formatted and self.pm:
            self.pm.save_disk_image(self.disk_manager)
        super().closeEvent(event)

    def _gui_action_new_folder(self):
        if not self.user_auth or self.current_cwd_inode_id is None:
            QMessageBox.warning(self, "错误", "会话或CWD无效")
            return
        current_user = self.user_auth.get_current_user()
        if not current_user:
            QMessageBox.warning(self, "错误", "无用户信息")
            return

        # 概念性权限检查
        # parent_inode = self.disk_manager.get_inode(self.current_cwd_inode_id)
        # if not parent_inode or not check_permission(parent_inode, current_user.uid, Permissions.WRITE):
        #     QMessageBox.warning(self, "权限不足", "无法在当前目录创建文件夹。"); return

        folder_name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称:")
        if ok and folder_name:
            folder_name = folder_name.strip()
            if not folder_name:
                QMessageBox.warning(self, "错误", "名称不能为空")
                return
            if "/" in folder_name:
                QMessageBox.warning(self, "错误", "名称不能含 '/'")
                return

            success, message, _ = make_directory(
                self.disk_manager,
                current_user.uid,
                self.current_cwd_inode_id,
                folder_name,
            )
            (
                QMessageBox.information(self, "结果", message)
                if success
                else QMessageBox.warning(self, "结果", message)
            )
            if success and self.pm:
                self.pm.save_disk_image(self.disk_manager)
                self._refresh_current_views()
        elif ok:
            QMessageBox.warning(self, "错误", "名称不能为空")

    def _gui_action_new_file(self):
        if not self.user_auth or self.current_cwd_inode_id is None:
            QMessageBox.warning(self, "错误", "会话或CWD无效")
            return
        current_user = self.user_auth.get_current_user()
        if not current_user:
            QMessageBox.warning(self, "错误", "无用户信息")
            return

        # 概念性权限检查
        # parent_inode = self.disk_manager.get_inode(self.current_cwd_inode_id)
        # if not parent_inode or not check_permission(parent_inode, current_user.uid, Permissions.WRITE):
        #     QMessageBox.warning(self, "权限不足", "无法在当前目录创建文件。"); return

        file_name, ok = QInputDialog.getText(self, "新建文件", "文件名称:")
        if ok and file_name:
            file_name = file_name.strip()
            if not file_name:
                QMessageBox.warning(self, "错误", "名称不能为空")
                return
            if "/" in file_name:
                QMessageBox.warning(self, "错误", "名称不能含 '/'")
                return

            success, message, _ = create_file(
                self.disk_manager,
                current_user.uid,
                self.current_cwd_inode_id,
                file_name,
            )
            (
                QMessageBox.information(self, "结果", message)
                if success
                else QMessageBox.warning(self, "结果", message)
            )
            if success and self.pm:
                self.pm.save_disk_image(self.disk_manager)
                self._refresh_current_views()
        elif ok:
            QMessageBox.warning(self, "错误", "名称不能为空")

    def _gui_action_delete_item_from_selection(self):
        selected_indexes = self.file_list_view.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.information(
                self, "提示", "请在右侧文件列表中选择一个项目进行删除。"
            )
            return

        name_column_index = selected_indexes[0]
        item_name = self.file_list_model.data(
            name_column_index, Qt.ItemDataRole.DisplayRole
        )
        item_inode_id = self.file_list_model.data(name_column_index, INODE_ID_ROLE)
        item_type_str = self.file_list_model.data(name_column_index, TYPE_STR_ROLE)

        if (
            item_name is None
            or item_inode_id is None
            or item_type_str is None
            or item_name in [".", ".."]
        ):
            QMessageBox.warning(self, "错误", f"无法删除选中的项目 '{item_name}'。")
            return
        self._execute_delete_item(
            item_name, item_inode_id, item_type_str, self.current_cwd_inode_id
        )

    def _execute_delete_item(
        self,
        item_name: str,
        item_inode_id: int,
        item_type_str: str,
        parent_inode_id: int,
    ):
        current_user = self.user_auth.get_current_user()
        if not current_user:
            QMessageBox.warning(self, "错误", "未找到当前用户信息.")
            return

        # 概念性权限检查 (对父目录的写权限)
        # parent_inode = self.disk_manager.get_inode(parent_inode_id)
        # if not parent_inode or not check_permission(parent_inode, current_user.uid, Permissions.WRITE):
        #     QMessageBox.warning(self, "权限不足", f"无法删除 '{item_name}' (父目录权限不足)。"); return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"您确定要删除 '{item_name}' 吗？\n此操作无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.No:
            return

        success, message = False, ""
        uid = current_user.uid
        if item_type_str == FileType.FILE.name:
            success, message = delete_file(
                self.disk_manager, uid, parent_inode_id, item_name
            )
        elif item_type_str == FileType.DIRECTORY.name:
            # 对于 rmdir，还可能需要检查目录是否为空，以及对目录本身的权限（取决于实现）
            success, message = remove_directory(
                self.disk_manager, uid, parent_inode_id, item_name
            )
        else:
            QMessageBox.critical(self, "错误", f"未知类型: {item_type_str}")
            return

        if success:
            QMessageBox.information(self, "成功", f"'{item_name}' 已删除.")
            if self.pm:
                self.pm.save_disk_image(self.disk_manager)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "删除失败", message)

    def _gui_action_rename_item(self):
        selected_indexes = self.file_list_view.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.information(
                self, "提示", "请在右侧文件列表中选择一个项目进行重命名。"
            )
            return

        name_column_index = selected_indexes[0]
        old_name = self.file_list_model.data(
            name_column_index, Qt.ItemDataRole.DisplayRole
        )

        if old_name is None or old_name in [".", ".."]:
            QMessageBox.warning(self, "错误", f"无法重命名特殊条目 '{old_name}'。")
            return

        new_name, ok = QInputDialog.getText(
            self, "重命名", f"请输入 '{old_name}' 的新名称:", text=old_name
        )
        if ok and new_name:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, "错误", "新名称不能为空。")
                return
            if "/" in new_name:
                QMessageBox.warning(self, "错误", "名称不能包含 '/'。")
                return
            if new_name == old_name:
                return

            current_user = self.user_auth.get_current_user()
            if not current_user:
                QMessageBox.warning(self, "错误", "无用户信息。")
                return

            # 概念性权限检查 (对父目录的写权限)
            # parent_inode = self.disk_manager.get_inode(self.current_cwd_inode_id)
            # if not parent_inode or not check_permission(parent_inode, current_user.uid, Permissions.WRITE):
            #     QMessageBox.warning(self, "权限不足", "无法重命名 (父目录权限不足)。"); return

            success, message = rename_item(
                self.disk_manager,
                current_user.uid,
                self.current_cwd_inode_id,
                old_name,
                new_name,
            )
            if success:
                QMessageBox.information(self, "成功", message)
                if self.pm:
                    self.pm.save_disk_image(self.disk_manager)
                self._refresh_current_views()
            else:
                QMessageBox.warning(self, "重命名失败", message)
        elif ok and not new_name:
            QMessageBox.warning(self, "错误", "新名称不能为空。")

    def _show_list_context_menu(self, point: QPoint):
        menu = QMenu(self.file_list_view)
        global_point = self.file_list_view.viewport().mapToGlobal(point)
        index_under_cursor = self.file_list_view.indexAt(point)

        item_name_ctx = None
        item_inode_id_ctx = None
        item_type_str_ctx = None

        if index_under_cursor.isValid():
            row = index_under_cursor.row()
            name_column_model_index = self.file_list_model.index(row, 0)
            item_name_ctx = self.file_list_model.data(
                name_column_model_index, Qt.ItemDataRole.DisplayRole
            )
            item_inode_id_ctx = self.file_list_model.data(
                name_column_model_index, INODE_ID_ROLE
            )
            item_type_str_ctx = self.file_list_model.data(
                name_column_model_index, TYPE_STR_ROLE
            )

            if (
                item_name_ctx is not None
                and item_inode_id_ctx is not None
                and item_type_str_ctx is not None
                and item_name_ctx not in [".", ".."]
            ):
                delete_ctx_action = QAction(
                    self._get_delete_icon(), f"删除 '{item_name_ctx}'", self
                )
                delete_ctx_action.triggered.connect(
                    lambda checked=False, name=item_name_ctx, inode_id=item_inode_id_ctx, type_str=item_type_str_ctx, parent_id=self.current_cwd_inode_id: self._execute_delete_item(
                        name, inode_id, type_str, parent_id
                    )
                )
                menu.addAction(delete_ctx_action)

                rename_ctx_action = QAction(
                    self.rename_action.icon(), f"重命名 '{item_name_ctx}'...", self
                )
                rename_ctx_action.triggered.connect(
                    self._gui_action_rename_item
                )  # Relies on current selection; ensure selection matches item under cursor
                menu.addAction(rename_ctx_action)

                properties_ctx_action = QAction(
                    self.properties_action.icon(), f"属性 '{item_name_ctx}'...", self
                )
                properties_ctx_action.triggered.connect(
                    lambda checked=False, inode_id_to_show=item_inode_id_ctx: self._gui_action_show_properties(
                        inode_id_to_show=inode_id_to_show
                    )
                )
                menu.addAction(properties_ctx_action)
                menu.addSeparator()

        menu.addAction(self.new_folder_action)
        menu.addAction(self.new_file_action)
        menu.exec(global_point)

    def _get_delete_icon(self) -> QIcon:
        icon = QIcon.fromTheme(
            "edit-delete", QIcon.fromTheme("list-remove", QIcon.fromTheme("user-trash"))
        )
        if icon.isNull():
            style = self.style()
            icon = (
                style.standardIcon(style.StandardPixmap.SP_TrashIcon)
                if style
                else QIcon()
            )
        return icon

    def _refresh_current_views(self):
        if self.current_cwd_inode_id is None:
            return
        current_path_str = get_inode_path_str(
            self.disk_manager, self.current_cwd_inode_id
        )
        if current_path_str.startswith(
            "[Error"
        ):  # Handle case where CWD itself becomes invalid (e.g. deleted from another session)
            QMessageBox.warning(
                self,
                "错误",
                f"当前工作目录无效: {current_path_str}。将尝试重置到根目录。",
            )
            # Attempt to reset to root, or handle more gracefully
            root_inode_id = (
                self.disk_manager.superblock.root_inode_id
                if self.disk_manager.superblock
                else None
            )
            if root_inode_id is not None:
                self.current_cwd_inode_id = root_inode_id
                self.user_auth.set_cwd_inode_id(root_inode_id)
                current_path_str = get_inode_path_str(self.disk_manager, root_inode_id)
            else:  # Critical error, cannot find root
                self.address_bar.setText("[错误：无法访问文件系统根目录]")
                self.file_list_model.setRowCount(0)
                # Consider disabling most UI elements or closing application
                return

        self.address_bar.setText(current_path_str)
        self._populate_file_list_view(self.current_cwd_inode_id)

        q_item_for_cwd = None
        if self.dir_tree_model.rowCount() > 0:
            root_gui_item = self.dir_tree_model.item(0)

            def find_item_by_inode_id_recursive(
                parent_item: QStandardItem, inode_id_to_find: int
            ) -> Optional[QStandardItem]:
                if parent_item.data(INODE_ID_ROLE) == inode_id_to_find:
                    return parent_item
                for row in range(parent_item.rowCount()):
                    child_item = parent_item.child(row, 0)
                    if child_item:  # Check if child_item is not None
                        found_in_grandchild = find_item_by_inode_id_recursive(
                            child_item, inode_id_to_find
                        )
                        if found_in_grandchild:
                            return found_in_grandchild
                return None

            q_item_for_cwd = find_item_by_inode_id_recursive(
                root_gui_item, self.current_cwd_inode_id
            )

        if q_item_for_cwd:
            q_item_for_cwd.setData(False, CHILDREN_LOADED_ROLE)
            if self.dir_tree_view.isExpanded(q_item_for_cwd.index()):
                self._populate_children_in_tree(
                    q_item_for_cwd, self.current_cwd_inode_id
                )
            else:
                if q_item_for_cwd.hasChildren():
                    q_item_for_cwd.removeRows(0, q_item_for_cwd.rowCount())
                # Add a placeholder if it's a directory that might have children after a refresh
                # This is tricky because list_directory is needed to know if it *will* have children
                # For now, _populate_children_in_tree (called on expansion) handles adding placeholders
                # A simple way: if it has no children after clearing, add a placeholder to ensure expander shows
                # if q_item_for_cwd.data(IS_DIR_ROLE) and q_item_for_cwd.rowCount() == 0:
                #     q_item_for_cwd.appendRow(QStandardItem()) # Add placeholder
        else:
            if self.dir_tree_model.rowCount() > 0:
                root_gui_item = self.dir_tree_model.item(0)
                if (
                    root_gui_item
                ):  # Refresh root if CWD item not found (e.g., if CWD is root)
                    self._populate_children_in_tree(
                        root_gui_item, root_gui_item.data(INODE_ID_ROLE)
                    )

    def _gui_action_show_properties(self, item_inode_id_to_show: Optional[int] = None):
        inode_id_for_props = None
        name_for_props = "未知项目"

        if item_inode_id_to_show is not None:
            inode_id_for_props = item_inode_id_to_show
            # Try to find name in current list view model (most direct source if right-clicked)
            found_in_list = False
            for row in range(self.file_list_model.rowCount()):
                idx = self.file_list_model.index(row, 0)
                if self.file_list_model.data(idx, INODE_ID_ROLE) == inode_id_for_props:
                    name_for_props = self.file_list_model.data(
                        idx, Qt.ItemDataRole.DisplayRole
                    )
                    found_in_list = True
                    break
            if (
                not found_in_list
            ):  # Fallback if not in list (e.g. properties of CWD itself, or item from tree)
                path_for_name = get_inode_path_str(
                    self.disk_manager, inode_id_for_props
                )
                if path_for_name and not path_for_name.startswith("[Error"):
                    name_for_props = (
                        path_for_name.split("/")[-1] if path_for_name != "/" else "/"
                    )
                else:
                    QMessageBox.warning(
                        self, "错误", f"无法为 inode {inode_id_for_props} 确定名称。"
                    )
                    return
        else:  # Called from main menu, use current selection in file_list_view
            selected_indexes = self.file_list_view.selectionModel().selectedRows()
            if (
                not selected_indexes
            ):  # If no selection, show properties for Current Working Directory
                inode_id_for_props = self.current_cwd_inode_id
                if (
                    inode_id_for_props is None
                ):  # Should not happen if app is properly initialized
                    QMessageBox.information(
                        self, "提示", "没有选中的项目，当前目录也无效。"
                    )
                    return
                path_of_cwd = get_inode_path_str(self.disk_manager, inode_id_for_props)
                name_for_props = (
                    path_of_cwd.split("/")[-1] if path_of_cwd != "/" else "/"
                )
            else:
                name_column_index = selected_indexes[0]
                inode_id_for_props = self.file_list_model.data(
                    name_column_index, INODE_ID_ROLE
                )
                name_for_props = self.file_list_model.data(
                    name_column_index, Qt.ItemDataRole.DisplayRole
                )

        if inode_id_for_props is None:
            QMessageBox.warning(self, "错误", "无法确定要显示属性的项目。")
            return

        target_inode = self.disk_manager.get_inode(inode_id_for_props)
        if not target_inode:
            QMessageBox.warning(
                self, "错误", f"无法找到 inode {inode_id_for_props} 的详细信息。"
            )
            return

        if target_inode.id == self.disk_manager.superblock.root_inode_id:
            name_for_props = "/"  # Ensure root is named "/"

        full_path_str = ""
        if target_inode.type == FileType.FILE:
            # For a file, its name (name_for_props) is in a parent directory.
            # If this was selected from a list view, the list view's directory is its parent.
            # We assume self.current_cwd_inode_id is the parent for files from the list.
            parent_path = get_inode_path_str(
                self.disk_manager, self.current_cwd_inode_id
            )  # Path of CWD
            if parent_path.startswith("[Error"):
                full_path_str = f"[父路径错误]/{name_for_props}"
            elif parent_path == "/":
                full_path_str = f"/{name_for_props}"
            else:
                full_path_str = f"{parent_path}/{name_for_props}"
        elif target_inode.type == FileType.DIRECTORY:
            full_path_str = get_inode_path_str(self.disk_manager, target_inode.id)
            if full_path_str.startswith("[Error"):
                full_path_str = f"[目录路径错误 ({target_inode.id})]"
        else:
            full_path_str = "[未知类型路径]"

        item_details = {
            "name": name_for_props,
            "inode_id": target_inode.id,
            "type": target_inode.type.name,
            "size": target_inode.size,
            "owner_uid": target_inode.owner_uid,
            "permissions": oct(target_inode.permissions),
            "atime": target_inode.atime,
            "mtime": target_inode.mtime,
            "ctime": target_inode.ctime,
            "link_count": target_inode.link_count,
            "blocks_count": target_inode.blocks_count,
            "full_path": full_path_str,
        }
        dialog = PropertiesDialog(item_details, self)
        dialog.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # --- Mocking backend for UI testing ---
    class MockInode:
        def __init__(
            self, id_val, type_val, name="", size=0
        ):  # Renamed id to id_val, type to type_val
            self.id = id_val
            self.type = type_val
            self.name = name
            self.permissions = 0o755 if self.type == FileType.DIRECTORY else 0o644
            self.owner_uid = 0
            self.size = (
                size  # For directories, this would be num_entries in real system
            )
            self.mtime = time.time()
            self.link_count = 2 if self.type == FileType.DIRECTORY else 1
            self.data_block_indices = []
            self.blocks_count = 0

    class MockDiskManager:
        def __init__(self):
            self.is_formatted = True

            class MockSuperblock:  # Inner class for superblock mock
                root_inode_id = 0
                total_inodes = 20
                block_size = 512

            self.superblock = MockSuperblock()
            self.inodes_map = {
                0: MockInode(
                    0, FileType.DIRECTORY, "/", size=5
                ),  # Root, size is num entries
                1: MockInode(1, FileType.DIRECTORY, "dirA", size=3),
                2: MockInode(2, FileType.FILE, "fileA.txt", size=1024),
                3: MockInode(3, FileType.DIRECTORY, "dirB", size=2),
                4: MockInode(4, FileType.DIRECTORY, "subDirA1", size=3),
                5: MockInode(5, FileType.FILE, "deep.txt", size=50),
            }
            self.next_mock_inode_id = 6
            self.dir_entries_map = {
                0: [
                    DirectoryEntry(".", 0),
                    DirectoryEntry("..", 0),
                    DirectoryEntry("dirA", 1),
                    DirectoryEntry("fileA.txt", 2),
                    DirectoryEntry("dirB", 3),
                ],
                1: [
                    DirectoryEntry(".", 1),
                    DirectoryEntry("..", 0),
                    DirectoryEntry("subDirA1", 4),
                ],
                3: [DirectoryEntry(".", 3), DirectoryEntry("..", 0)],
                4: [
                    DirectoryEntry(".", 4),
                    DirectoryEntry("..", 1),
                    DirectoryEntry("deep.txt", 5),
                ],
            }

        def get_inode(self, inode_id):
            return self.inodes_map.get(inode_id)

        def allocate_inode(self, uid):  # uid not used in mock
            mock_id = self.next_mock_inode_id
            self.next_mock_inode_id += 1
            return mock_id

        def allocate_data_block(self):
            return (
                1000 + self.next_mock_inode_id
            )  # Dummy block ID, just needs to be uniqueish

        def write_block(self, block_id, data):
            # print(f"Mock DM: Writing to block {block_id} (simulated)")
            pass

        def save_disk_image(self):
            print("Mock DM: Disk image saved (simulated).")

        def free_inode(self, inode_id):
            print(f"Mock DM: Inode {inode_id} freed (simulated)")
            if inode_id in self.inodes_map:
                del self.inodes_map[inode_id]
            # Also remove from any dir_entries_map if it was a directory
            if inode_id in self.dir_entries_map:
                del self.dir_entries_map[inode_id]

        def free_data_block(self, block_id):
            print(f"Mock DM: Block {block_id} freed (simulated)")

    class MockUser:
        username = "test_user"
        uid = 0

    class MockAuth:
        current_user = MockUser()
        current_user_cwd_inode_id = 0
        current_user_open_files = {}

        def get_current_user(self):
            return self.current_user

        def get_cwd_inode_id(self):
            return self.current_user_cwd_inode_id

        def set_cwd_inode_id(self, inode_id):
            self.current_user_cwd_inode_id = inode_id

    class MockPersistenceManager:
        def save_disk_image(self, disk):
            print("Mock PM: Disk image saved (simulated).")

    # --- Reformatted Mock Functions ---

    def mock_list_directory(dm_mock, inode_id_mock):
        # print(f"Mock list_directory called for inode: {inode_id_mock}")
        _entries = dm_mock.dir_entries_map.get(inode_id_mock, [])
        detailed_mock_entries = []
        for entry_obj in _entries:
            inode = dm_mock.get_inode(entry_obj.inode_id)
            if inode:
                detailed_mock_entries.append(
                    {
                        "name": entry_obj.name,
                        "inode_id": entry_obj.inode_id,
                        "type": inode.type.name,
                        "size": inode.size,
                        "permissions": oct(inode.permissions),
                        "mtime": inode.mtime,
                        "link_count": inode.link_count,
                        "owner_uid": inode.owner_uid,
                    }
                )
        return True, "Mock success", detailed_mock_entries

    def mock_make_directory(dm_mock, uid, parent_id, name):
        print(f"Mock make_directory: parent_inode={parent_id}, name='{name}'")

        # Check for existing name in parent
        for entry in dm_mock.dir_entries_map.get(parent_id, []):
            if entry.name == name:
                return (
                    False,
                    f"Mock: '{name}' already exists in parent inode {parent_id}.",
                    None,
                )

        new_id = dm_mock.allocate_inode(uid)
        if parent_id not in dm_mock.dir_entries_map:
            # This case implies parent_id is not a directory in the mock or is empty before . and ..
            # For a valid parent directory, it should exist in dir_entries_map.
            dm_mock.dir_entries_map[parent_id] = [
                DirectoryEntry(".", parent_id),
                DirectoryEntry("..", parent_id),
            ]  # simplified parent

        dm_mock.dir_entries_map[parent_id].append(DirectoryEntry(name, new_id))
        dm_mock.inodes_map[new_id] = MockInode(
            new_id, FileType.DIRECTORY, name, size=2
        )  # New dir has . & ..
        dm_mock.dir_entries_map[new_id] = [
            DirectoryEntry(".", new_id),
            DirectoryEntry("..", parent_id),
        ]

        parent_inode = dm_mock.get_inode(parent_id)
        if parent_inode:
            parent_inode.size = len(dm_mock.dir_entries_map[parent_id])
            parent_inode.link_count += 1
        return True, f"Mock directory '{name}' (inode {new_id}) created.", new_id

    def mock_create_file(dm_mock, uid, parent_id, name):
        print(f"Mock create_file: parent_inode={parent_id}, name='{name}'")

        for entry in dm_mock.dir_entries_map.get(parent_id, []):
            if entry.name == name:
                return (
                    False,
                    f"Mock: '{name}' already exists in parent inode {parent_id}.",
                    None,
                )

        new_id = dm_mock.allocate_inode(uid)
        if parent_id not in dm_mock.dir_entries_map:
            dm_mock.dir_entries_map[parent_id] = [
                DirectoryEntry(".", parent_id),
                DirectoryEntry("..", parent_id),
            ]

        dm_mock.dir_entries_map[parent_id].append(DirectoryEntry(name, new_id))
        dm_mock.inodes_map[new_id] = MockInode(new_id, FileType.FILE, name, size=0)

        parent_inode = dm_mock.get_inode(parent_id)
        if parent_inode:
            parent_inode.size = len(dm_mock.dir_entries_map[parent_id])
        return True, f"Mock file '{name}' (inode {new_id}) created.", new_id

    def mock_delete_file(dm_mock, uid, parent_id, name):
        print(f"Mock delete_file: parent_inode={parent_id}, name='{name}'")
        entries = dm_mock.dir_entries_map.get(parent_id, [])
        entry_to_del = next((e for e in entries if e.name == name), None)

        if entry_to_del:
            target_inode = dm_mock.get_inode(entry_to_del.inode_id)
            if target_inode and target_inode.type == FileType.FILE:
                entries.remove(entry_to_del)  # Remove from parent's list
                if entry_to_del.inode_id in dm_mock.inodes_map:
                    del dm_mock.inodes_map[entry_to_del.inode_id]  # Delete inode

                parent_inode = dm_mock.get_inode(parent_id)
                if parent_inode:
                    parent_inode.size = len(entries)
                return True, f"Mock file '{name}' deleted."
            else:
                return False, f"Mock: '{name}' is not a file or its inode is missing."
        return False, f"Mock: File '{name}' not found."

    def mock_remove_directory(dm_mock, uid, parent_id, name):
        print(f"Mock remove_directory: parent_inode={parent_id}, name='{name}'")
        parent_entries = dm_mock.dir_entries_map.get(parent_id, [])
        entry_to_del = next((e for e in parent_entries if e.name == name), None)

        if entry_to_del:
            target_inode = dm_mock.get_inode(entry_to_del.inode_id)
            if target_inode and target_inode.type == FileType.DIRECTORY:
                target_dir_own_entries = dm_mock.dir_entries_map.get(
                    entry_to_del.inode_id, []
                )
                if len(target_dir_own_entries) <= 2:  # Empty if only '.' and '..'
                    parent_entries.remove(entry_to_del)
                    if entry_to_del.inode_id in dm_mock.dir_entries_map:
                        del dm_mock.dir_entries_map[entry_to_del.inode_id]
                    if entry_to_del.inode_id in dm_mock.inodes_map:
                        del dm_mock.inodes_map[entry_to_del.inode_id]

                    parent_inode = dm_mock.get_inode(parent_id)
                    if parent_inode:
                        parent_inode.size = len(parent_entries)
                        parent_inode.link_count -= 1
                    return True, f"Mock directory '{name}' removed."
                else:
                    return False, "Mock: Directory not empty."
            else:
                return (
                    False,
                    f"Mock: '{name}' is not a directory or its inode is missing.",
                )
        return False, f"Mock: Directory '{name}' not found."

    def mock_get_inode_path_str(dm_mock, inode_id_mock):
        if inode_id_mock == 0:  # Assuming 0 is always root in mock
            return "/"

        path_segments = []
        current_lookup_id = inode_id_mock
        visited_ids_for_path = set()  # To detect loops or missing links

        max_depth_for_mock = len(dm_mock.inodes_map)  # Safety break

        while current_lookup_id != 0 and current_lookup_id not in visited_ids_for_path:
            if len(path_segments) >= max_depth_for_mock:
                return f"/[path_too_long_or_loop_for_inode:{inode_id_mock}]"

            visited_ids_for_path.add(current_lookup_id)

            current_name_in_parent = None
            parent_id_of_current = None
            found_link_to_parent = False

            # Find current_lookup_id's name and its parent_id by searching all directory entries
            for p_id, p_entries in dm_mock.dir_entries_map.items():
                for entry in p_entries:
                    if entry.inode_id == current_lookup_id and entry.name not in [
                        ".",
                        "..",
                    ]:
                        current_name_in_parent = entry.name
                        parent_id_of_current = p_id
                        found_link_to_parent = True
                        break
                if found_link_to_parent:
                    break

            if current_name_in_parent:
                path_segments.insert(0, current_name_in_parent)
            else:
                # If not found in any parent's entry list (could be an orphan, or root which is handled)
                # Or if it's a dir whose 'name' attribute we stored in MockInode
                mock_node_obj = dm_mock.get_inode(current_lookup_id)
                if mock_node_obj and mock_node_obj.name and mock_node_obj.name != "/":
                    path_segments.insert(
                        0, mock_node_obj.name
                    )  # Fallback to inode's own name
                else:
                    path_segments.insert(0, f"[orphan_or_error:{current_lookup_id}]")
                break  # Can't trace further reliably

            if parent_id_of_current is None:  # Should have been found if name was found
                break

            current_lookup_id = parent_id_of_current  # Move up to the parent

        if path_segments:
            return "/" + "/".join(path_segments)
        elif inode_id_mock == 0:  # Already handled, but defensive
            return "/"
        else:  # Path couldn't be constructed but wasn't root (e.g. orphan directly under conceptual root)
            mock_node_obj_final = dm_mock.get_inode(inode_id_mock)
            if mock_node_obj_final and mock_node_obj_final.name:
                return f"/{mock_node_obj_final.name}"  # Single segment from root
            return f"/[unresolved_path_for_inode:{inode_id_mock}]"

    # Save original functions
    _original_list_directory = list_directory
    _original_make_directory = make_directory
    _original_create_file = create_file
    _original_delete_file = delete_file
    _original_remove_directory = remove_directory
    _original_get_inode_path_str = get_inode_path_str

    # Override with mocks
    list_directory = mock_list_directory
    make_directory = mock_make_directory
    create_file = mock_create_file
    delete_file = mock_delete_file
    remove_directory = mock_remove_directory
    get_inode_path_str = mock_get_inode_path_str

    # Create mock instances
    mock_dm = MockDiskManager()
    mock_auth = MockAuth()
    mock_pm = MockPersistenceManager()

    # Create and show the main window with mock objects
    main_win = MainWindow(mock_dm, mock_auth, mock_pm)
    main_win.show()

    exit_code = app.exec()  # Start event loop

    # Restore original functions
    list_directory = _original_list_directory
    make_directory = _original_make_directory
    create_file = _original_create_file
    delete_file = _original_delete_file
    remove_directory = _original_remove_directory
    get_inode_path_str = _original_get_inode_path_str

    sys.exit(exit_code)
