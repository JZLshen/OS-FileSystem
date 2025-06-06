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
    QAbstractItemView,
)
from PyQt6.QtGui import QAction, QStandardItemModel, QStandardItem, QIcon, QKeySequence
from PyQt6.QtCore import (
    Qt,
    QSize,
    QModelIndex,
    QPoint,
    QItemSelectionModel,
)  # 确保 QItemSelectionModel 导入

# 从您的项目中导入
from fs_core.dir_ops import (
    list_directory,
    make_directory,
    remove_directory,
    rename_item,
    _resolve_path_to_inode_id,  # 确保导入 _resolve_path_to_inode_id
)
from fs_core.file_ops import create_file, delete_file
from fs_core.datastructures import (
    FileType,
    DirectoryEntry,
)

from fs_core.fs_utils import get_inode_path_str
from user_management.user_auth import ROOT_UID  # 导入 ROOT_UID

from .text_editor_dialog import TextEditorDialog
from .properties_dialog import PropertiesDialog

# 为自定义数据角色定义常量
INODE_ID_ROLE = Qt.ItemDataRole.UserRole
IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 1
TYPE_STR_ROLE = Qt.ItemDataRole.UserRole + 2
CHILDREN_LOADED_ROLE = Qt.ItemDataRole.UserRole + 3


# 新增：用于自定义排序的QStandardItem子类
class SortableStandardItem(QStandardItem):
    def __init__(self, display_text="", sort_key_data=None):
        super().__init__(display_text)
        self.sort_key = sort_key_data if sort_key_data is not None else display_text

    def __lt__(self, other):
        if isinstance(other, SortableStandardItem):
            try:
                if self.sort_key is None and other.sort_key is None:
                    return False
                if self.sort_key is None:
                    return True
                if other.sort_key is None:
                    return False
                return self.sort_key < other.sort_key
            except TypeError:
                # 回退到 QStandardItem 的默认比较 (基于文本)
                return super().__lt__(other)
        return super().__lt__(other)


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

        self._create_base_actions()
        self._create_menus()
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
        self.file_list_view.setSortingEnabled(True)
        self.splitter.addWidget(self.file_list_view)

        self.splitter.setSizes([250, 650])
        self.dir_tree_view.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.file_list_view.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(self.splitter)

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
            self._populate_file_list_view(
                self.current_cwd_inode_id
                if self.current_cwd_inode_id is not None
                else root_inode_id
            )  # 使用 CWD 或 root
            self._update_go_up_action_state()
            if self.file_list_model.rowCount() > 0:
                self.file_list_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        else:
            self.status_bar.showMessage("错误：磁盘未格式化或无法访问根目录", 5000)
            self._update_go_up_action_state()  # 即使出错也更新，确保禁用

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
        item.setData(False, CHILDREN_LOADED_ROLE)  # Initially not loaded
        parent_item.appendRow(item)
        # Add a placeholder item if this directory itself might have children,
        # to ensure the expander arrow is shown.
        placeholder_item = QStandardItem()
        item.appendRow(placeholder_item)
        return item

    def _populate_children_in_tree(
        self, parent_q_item: QStandardItem, parent_inode_id: int
    ):
        if not self.disk_manager or not self.user_auth:
            return

        parent_q_item.removeRows(
            0, parent_q_item.rowCount()
        )  # Clear existing children (like placeholder)
        success, _, entries = list_directory(self.disk_manager, parent_inode_id)

        if not success or entries is None:
            parent_q_item.setData(
                True, CHILDREN_LOADED_ROLE
            )  # Mark as attempted to load
            return

        entries.sort(
            key=lambda x: (
                x.get("type") != FileType.DIRECTORY.name,
                x.get("name", "").lower(),
            )
        )

        has_dirs_to_add = False
        for entry in entries:
            if entry.get("type") == FileType.DIRECTORY.name:
                if entry.get("name") in [".", ".."]:
                    continue
                self._add_directory_to_tree(
                    parent_q_item, entry.get("name"), entry.get("inode_id")
                )
                has_dirs_to_add = True

        parent_q_item.setData(True, CHILDREN_LOADED_ROLE)
        # If no actual subdirectories were added, and it's a directory,
        # it might still need a placeholder if we want to differentiate visually
        # between "expanded but empty" and "not yet expanded".
        # However, the current logic in _add_directory_to_tree already adds placeholder for each dir.

    def on_tree_item_expanded(self, index: QModelIndex):
        if not index.isValid():
            return
        item_being_expanded = self.dir_tree_model.itemFromIndex(index)
        if not item_being_expanded:
            return

        # Check if children are already loaded or if it's a placeholder
        # The CHILDREN_LOADED_ROLE helps distinguish actual loading from just having a placeholder
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
            self.current_cwd_inode_id = item_inode_id
            self.user_auth.set_cwd_inode_id(item_inode_id)
            self.address_bar.setText(
                get_inode_path_str(self.disk_manager, item_inode_id)
            )
            self._populate_file_list_view(item_inode_id)
            self._update_go_up_action_state()

    def on_item_double_clicked_in_list_view(self, index: QModelIndex):
        if not index.isValid():
            return

        name_column_model_index = self.file_list_model.index(index.row(), 0)
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
            self.current_cwd_inode_id = item_inode_id
            self.user_auth.set_cwd_inode_id(item_inode_id)
            current_path_str = get_inode_path_str(self.disk_manager, item_inode_id)
            self.address_bar.setText(current_path_str)
            self._populate_file_list_view(item_inode_id)
            self._update_go_up_action_state()
            self._expand_and_select_in_tree(item_inode_id)
        else:
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
                self._refresh_current_views()  # Refresh in case file content (size) changed
            else:
                self._gui_action_show_properties(item_inode_id_to_show=item_inode_id)

    def _expand_and_select_in_tree(self, target_inode_id: int):
        # Placeholder - robust implementation is complex
        print(f"Placeholder: _expand_and_select_in_tree for inode {target_inode_id}")
        # A simple approach to select if visible and expand:
        root = self.dir_tree_model.invisibleRootItem()
        indices_to_check = [root.index()]

        # BFS or DFS to find the item
        queue = [
            self.dir_tree_model.item(i) for i in range(self.dir_tree_model.rowCount())
        ]
        found_item = None

        path_items = []  # To store path from root to found_item

        def find_item_recursive(parent_item, target_id):
            nonlocal found_item, path_items
            if found_item:
                return True  # Already found

            for row in range(parent_item.rowCount()):
                current_item = parent_item.child(row, 0)
                if not current_item:
                    continue

                path_items.append(current_item)
                if current_item.data(INODE_ID_ROLE) == target_id:
                    found_item = current_item
                    return True

                if current_item.data(IS_DIR_ROLE):  # Only recurse into directories
                    # If children not loaded, expanding it will load them via on_tree_item_expanded
                    # self.dir_tree_view.expand(current_item.index()) # Might trigger loading
                    if find_item_recursive(current_item, target_id):
                        return True
                path_items.pop()  # Backtrack
            return False

        if self.dir_tree_model.rowCount() > 0:
            root_gui_item = self.dir_tree_model.item(
                0
            )  # Assuming single root item ("/")
            path_items.append(root_gui_item)
            if root_gui_item.data(INODE_ID_ROLE) == target_inode_id:
                found_item = root_gui_item
            else:
                find_item_recursive(root_gui_item, target_inode_id)

        if found_item:
            # Expand all parents in the path
            for item_in_path in path_items[
                :-1
            ]:  # Exclude the target item itself for expansion
                if item_in_path and item_in_path.index().isValid():
                    self.dir_tree_view.expand(item_in_path.index())

            # Select the target item
            self.dir_tree_view.setCurrentIndex(found_item.index())
            self.dir_tree_view.scrollTo(
                found_item.index(), QAbstractItemView.ScrollHint.PositionAtCenter
            )

    def _populate_file_list_view(self, dir_inode_id: int):
        self.file_list_model.setRowCount(0)
        self.status_bar.showMessage(
            f"正在加载目录 inode {dir_inode_id} 的内容...", 2000
        )
        success, msg_ls_unused, entries = list_directory(
            self.disk_manager, dir_inode_id
        )
        if not success or entries is None:
            self.status_bar.showMessage(
                f"无法读取目录 inode {dir_inode_id} 的内容: {msg_ls_unused if msg_ls_unused else '未知错误'}",
                3000,
            )
            return

        if entries:
            # No need to sort here if setSortingEnabled(True) is used,
            # unless a very specific initial non-column-click sort is required.
            # The view will handle sorting based on the last clicked header or initial default.
            # entries.sort(key=lambda x: (x.get("type") != FileType.DIRECTORY.name, x.get("name", "").lower()))

            for entry in entries:
                if entry.get("name") == "." or entry.get("name") == "..":
                    continue

                name_str = entry.get("name", "N/A")
                size_val = entry.get("size", 0)
                type_str = entry.get("type", "UNKNOWN")
                mtime_val = entry.get("mtime", 0)
                inode_id_val = entry.get("inode_id")

                name_item = QStandardItem(name_str)
                name_item.setEditable(False)
                name_item.setData(inode_id_val, INODE_ID_ROLE)
                name_item.setData(type_str == FileType.DIRECTORY.name, IS_DIR_ROLE)
                name_item.setData(type_str, TYPE_STR_ROLE)
                name_item.setIcon(
                    self._get_folder_icon()
                    if type_str == FileType.DIRECTORY.name
                    else self._get_file_icon()
                )

                display_size_str = ""
                actual_sort_size_key = 0
                if type_str != FileType.DIRECTORY.name:
                    display_size_str = f"{size_val} B"
                    actual_sort_size_key = int(size_val)
                else:
                    display_size_str = ""
                    actual_sort_size_key = int(size_val)
                size_item = SortableStandardItem(display_size_str, actual_sort_size_key)
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
                actual_sort_mtime_key = (
                    int(mtime_val) if mtime_val and mtime_val > 0 else 0
                )
                date_item = SortableStandardItem(mtime_readable, actual_sort_mtime_key)
                date_item.setEditable(False)

                self.file_list_model.appendRow(
                    [name_item, size_item, type_display_item, date_item]
                )
        self._update_go_up_action_state()  # Update after populating

    def _create_base_actions(self):
        self.new_folder_action = QAction(
            self._get_folder_icon(), "新建文件夹(&N)...", self
        )
        self.new_folder_action.setStatusTip("在当前位置创建一个新文件夹")
        self.new_folder_action.triggered.connect(self._gui_action_new_folder)

        self.new_file_action = QAction(self._get_file_icon(), "新建文件(&F)...", self)
        self.new_file_action.setStatusTip("在当前位置创建一个新空文件")
        self.new_file_action.triggered.connect(self._gui_action_new_file)

        self.create_user_action = QAction("创建用户...", self)
        self.create_user_action.setStatusTip("创建一个新用户 (仅限管理员)")
        self.create_user_action.triggered.connect(self._gui_action_create_user)

        self.format_disk_action = QAction("格式化磁盘...", self)
        self.format_disk_action.setStatusTip(
            "格式化整个磁盘，所有数据将丢失 (仅限管理员)"
        )
        self.format_disk_action.triggered.connect(self._gui_action_format_disk)

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

        rename_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_FileDialogListView
        )
        self.rename_action = QAction(rename_icon, "重命名(&R)...", self)
        self.rename_action.setStatusTip("重命名选中的文件或文件夹")
        self.rename_action.setShortcut(QKeySequence("F2"))
        self.rename_action.triggered.connect(self._gui_action_rename_item)

        properties_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_FileDialogInfoView
        )
        self.properties_action = QAction(properties_icon, "属性(&I)", self)
        self.properties_action.setStatusTip("查看选中项目的属性")
        self.properties_action.triggered.connect(self._gui_action_show_properties)

        go_up_icon = self.style().standardIcon(
            QStyle.StandardPixmap.SP_FileDialogToParent
        )
        self.go_up_action = QAction(go_up_icon, "上一级(&U)", self)
        self.go_up_action.setStatusTip("返回上一级目录")
        self.go_up_action.triggered.connect(self._gui_action_go_up)
        self.go_up_action.setEnabled(False)

    def _create_menus(self):
        menu_bar = self.menuBar()

        menu_bar.addAction(self.go_up_action)  # 上一级按钮放前面
        menu_bar.addSeparator()

        menu_bar.addAction(self.new_folder_action)
        menu_bar.addAction(self.new_file_action)
        menu_bar.addAction(self.rename_action)
        menu_bar.addAction(self.properties_action)
        menu_bar.addAction(self.delete_action)
        menu_bar.addSeparator()

        # 管理/系统相关的操作可以放在一个子菜单或后面
        admin_menu = menu_bar.addMenu("系统管理")
        admin_menu.addAction(self.create_user_action)
        admin_menu.addAction(self.format_disk_action)

        menu_bar.addSeparator()
        menu_bar.addAction(self.exit_action)

        # 设置管理员按钮的初始状态
        is_admin = (
            self.user_auth
            and self.user_auth.get_current_user()
            and self.user_auth.get_current_user().uid == ROOT_UID
        )
        self.create_user_action.setEnabled(is_admin)
        self.format_disk_action.setEnabled(is_admin)

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

        name_column_model_index = self.file_list_model.index(
            selected_indexes[0].row(), 0
        )
        item_name = self.file_list_model.data(
            name_column_model_index, Qt.ItemDataRole.DisplayRole
        )
        item_inode_id = self.file_list_model.data(
            name_column_model_index, INODE_ID_ROLE
        )
        item_type_str = self.file_list_model.data(
            name_column_model_index, TYPE_STR_ROLE
        )

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
                self, "提示", "请在右侧文件列表中选择一个项目进行重命名."
            )
            return

        name_column_model_index = self.file_list_model.index(
            selected_indexes[0].row(), 0
        )
        old_name = self.file_list_model.data(
            name_column_model_index, Qt.ItemDataRole.DisplayRole
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

        item_name_ctx, item_inode_id_ctx, item_type_str_ctx = None, None, None

        if index_under_cursor.isValid():
            name_column_model_index = self.file_list_model.index(
                index_under_cursor.row(), 0
            )
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
                item_name_ctx
                and item_inode_id_ctx is not None
                and item_type_str_ctx
                and item_name_ctx not in [".", ".."]
            ):
                # Ensure item is selected before showing context menu for actions like rename
                current_selection = self.file_list_view.selectionModel()
                current_selection.clearSelection()
                current_selection.select(
                    name_column_model_index.siblingAtRow(name_column_model_index.row()),
                    QItemSelectionModel.SelectionFlag.Rows
                    | QItemSelectionModel.SelectionFlag.Select,
                )

                delete_ctx_action = QAction(
                    self._get_delete_icon(), f"删除 '{item_name_ctx}'", self
                )
                delete_ctx_action.triggered.connect(
                    lambda: self._execute_delete_item(
                        item_name_ctx,
                        item_inode_id_ctx,
                        item_type_str_ctx,
                        self.current_cwd_inode_id,
                    )
                )
                menu.addAction(delete_ctx_action)

                rename_ctx_action = QAction(
                    self.rename_action.icon(), f"重命名 '{item_name_ctx}'...", self
                )
                rename_ctx_action.triggered.connect(self._gui_action_rename_item)
                menu.addAction(rename_ctx_action)

                properties_ctx_action = QAction(
                    self.properties_action.icon(), f"属性 '{item_name_ctx}'...", self
                )
                properties_ctx_action.triggered.connect(
                    lambda: self._gui_action_show_properties(
                        item_inode_id_to_show=item_inode_id_ctx
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
        if current_path_str.startswith("[Error"):
            QMessageBox.warning(
                self,
                "错误",
                f"当前工作目录无效: {current_path_str}。将尝试重置到根目录。",
            )
            root_inode_id = (
                self.disk_manager.superblock.root_inode_id
                if self.disk_manager.superblock
                else None
            )
            if root_inode_id is not None:
                self.current_cwd_inode_id = root_inode_id
                self.user_auth.set_cwd_inode_id(root_inode_id)
                current_path_str = get_inode_path_str(self.disk_manager, root_inode_id)
            else:
                self.address_bar.setText("[错误：无法访问文件系统根目录]")
                self.file_list_model.setRowCount(0)
                return
        self.address_bar.setText(current_path_str)

        header = self.file_list_view.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        self._populate_file_list_view(self.current_cwd_inode_id)
        if self.file_list_model.rowCount() > 0:
            self.file_list_view.sortByColumn(sort_column, sort_order)
        self._update_go_up_action_state()  # Update "Go Up" button state

        # Refresh tree view for current directory's parent to reflect changes
        # This is a simplified refresh, more complex logic might be needed for perfect sync
        q_item_for_cwd = None
        if self.dir_tree_model.rowCount() > 0:
            root_gui_item = self.dir_tree_model.item(0)

            # ... (find_item_by_inode_id_recursive remains the same)
            def find_item_by_inode_id_recursive(
                parent_item: QStandardItem, inode_id_to_find: int
            ) -> Optional[QStandardItem]:
                if parent_item.data(INODE_ID_ROLE) == inode_id_to_find:
                    return parent_item
                for row in range(parent_item.rowCount()):
                    child_item = parent_item.child(row, 0)
                    if child_item:
                        found = find_item_by_inode_id_recursive(
                            child_item, inode_id_to_find
                        )
                        if found:
                            return found
                return None

            q_item_for_cwd = find_item_by_inode_id_recursive(
                root_gui_item, self.current_cwd_inode_id
            )

        if q_item_for_cwd:
            # Force reload of children for the CWD item in the tree
            q_item_for_cwd.setData(False, CHILDREN_LOADED_ROLE)  # Mark as not loaded
            # If it's expanded, repopulate. If not, clear to force repopulation on next expand.
            if self.dir_tree_view.isExpanded(q_item_for_cwd.index()):
                self._populate_children_in_tree(
                    q_item_for_cwd, self.current_cwd_inode_id
                )
            else:  # If not expanded, just clear current children (placeholders)
                q_item_for_cwd.removeRows(0, q_item_for_cwd.rowCount())
                if q_item_for_cwd.data(
                    IS_DIR_ROLE
                ):  # Add placeholder back if it's a directory
                    q_item_for_cwd.appendRow(QStandardItem())
        elif self.current_cwd_inode_id == (
            self.disk_manager.superblock.root_inode_id
            if self.disk_manager.superblock
            else -1
        ):
            # If CWD is root and not found as an item (e.g. after format), refresh root
            if self.dir_tree_model.rowCount() > 0:
                root_gui_item = self.dir_tree_model.item(0)
                if (
                    root_gui_item
                    and root_gui_item.data(INODE_ID_ROLE) == self.current_cwd_inode_id
                ):
                    self._populate_children_in_tree(
                        root_gui_item, self.current_cwd_inode_id
                    )

    def _gui_action_show_properties(self, item_inode_id_to_show: Optional[int] = None):
        inode_id_for_props, name_for_props = None, "未知项目"
        if item_inode_id_to_show is not None:
            inode_id_for_props = item_inode_id_to_show
            found_in_list = False
            for row in range(self.file_list_model.rowCount()):
                idx = self.file_list_model.index(row, 0)
                if self.file_list_model.data(idx, INODE_ID_ROLE) == inode_id_for_props:
                    name_for_props = self.file_list_model.data(
                        idx, Qt.ItemDataRole.DisplayRole
                    )
                    found_in_list = True
                    break
            if not found_in_list:
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
        else:
            selected_indexes = self.file_list_view.selectionModel().selectedRows()
            if not selected_indexes:
                inode_id_for_props = self.current_cwd_inode_id
                if inode_id_for_props is None:
                    QMessageBox.information(
                        self, "提示", "没有选中的项目，当前目录也无效。"
                    )
                    return
                path_of_cwd = get_inode_path_str(self.disk_manager, inode_id_for_props)
                name_for_props = (
                    path_of_cwd.split("/")[-1] if path_of_cwd != "/" else "/"
                )
            else:
                name_column_model_index = self.file_list_model.index(
                    selected_indexes[0].row(), 0
                )
                inode_id_for_props = self.file_list_model.data(
                    name_column_model_index, INODE_ID_ROLE
                )
                name_for_props = self.file_list_model.data(
                    name_column_model_index, Qt.ItemDataRole.DisplayRole
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
            name_for_props = "/"

        full_path_str = "[路径解析中...]"  # Default
        # Determine parent inode ID for constructing full path of files
        parent_inode_id_for_path = (
            self.current_cwd_inode_id
        )  # Assume current CWD is parent for items in list view

        if target_inode.type == FileType.FILE:
            # Try to get path of parent directory
            # If target_inode_id_to_show was from context menu, self.current_cwd_inode_id is its parent.
            # If it was properties of CWD itself (which is a dir), that's handled by DIRECTORY case.
            parent_path_str = get_inode_path_str(
                self.disk_manager, parent_inode_id_for_path
            )
            if parent_path_str.startswith("[Error"):
                full_path_str = f"{parent_path_str}/{name_for_props}"
            elif parent_path_str == "/":
                full_path_str = f"/{name_for_props}"
            else:
                full_path_str = f"{parent_path_str}/{name_for_props}"
        elif target_inode.type == FileType.DIRECTORY:
            full_path_str = get_inode_path_str(self.disk_manager, target_inode.id)

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

    def _gui_action_create_user(self):
        current_user = self.user_auth.get_current_user()
        if not current_user or current_user.uid != ROOT_UID:
            QMessageBox.warning(self, "权限不足", "只有root用户才能创建新用户。")
            return

        new_username, ok_user = QInputDialog.getText(self, "创建新用户", "新用户名:")
        if not (ok_user and new_username.strip()):
            if ok_user:
                QMessageBox.warning(self, "输入错误", "用户名不能为空。")
            return
        new_username = new_username.strip()

        new_password, ok_pass = QInputDialog.getText(
            self,
            "创建新用户",
            f"用户 '{new_username}' 的密码:",
            QLineEdit.EchoMode.Password,
        )
        if not ok_pass:
            return  # User cancelled password input
        # Allow empty password, but UserAuthenticator might reject it if it has policies

        success, message = self.user_auth.create_user(new_username, new_password)

        (
            QMessageBox.information(self, "结果", message)
            if success
            else QMessageBox.warning(self, "创建失败", message)
        )
        # No disk persistence for user list in this version of UserAuthenticator

    def _gui_action_format_disk(self):
        current_user = self.user_auth.get_current_user()
        if not current_user or current_user.uid != ROOT_UID:
            QMessageBox.warning(self, "权限不足", "只有root用户才能格式化磁盘。")
            return

        reply = QMessageBox.critical(
            self,
            "确认格式化",
            "<b>警告：此操作将格式化整个模拟磁盘，所有数据都将永久丢失！</b>\n\n您确定要继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success_format = self.disk_manager.format_disk()
        if success_format:
            QMessageBox.information(
                self, "格式化成功", "磁盘已成功格式化。\n系统状态已重置。"
            )
            if self.pm:
                self.pm.save_disk_image(self.disk_manager)

            if (
                self.disk_manager.superblock
                and self.disk_manager.superblock.root_inode_id is not None
            ):
                new_root_id = self.disk_manager.superblock.root_inode_id
                self.user_auth.set_cwd_inode_id(
                    new_root_id
                )  # Reset CWD for current (root) user
                self.current_cwd_inode_id = new_root_id

                # Reset Tree View
                self.dir_tree_model.clear()
                root_item = QStandardItem("/")
                root_item.setIcon(self._get_folder_icon())
                root_item.setEditable(False)
                root_item.setData(new_root_id, INODE_ID_ROLE)
                root_item.setData(True, IS_DIR_ROLE)
                root_item.setData(False, CHILDREN_LOADED_ROLE)
                self.dir_tree_model.appendRow(root_item)
                self._populate_children_in_tree(
                    root_item, new_root_id
                )  # Load root's children
                self.dir_tree_view.expand(root_item.index())

                self._refresh_current_views()  # This will also call _populate_file_list_view for the new root
            else:
                QMessageBox.critical(
                    self, "错误", "格式化后无法找到根目录，系统可能不稳定。"
                )
                self.address_bar.setText("[错误：系统未正确初始化]")
                self.file_list_model.setRowCount(0)
                self.dir_tree_model.setRowCount(0)
        else:
            QMessageBox.critical(self, "格式化失败", "磁盘格式化过程中发生错误。")
        self._update_go_up_action_state()

    def _gui_action_go_up(self):
        if (
            self.current_cwd_inode_id is None
            or not self.disk_manager.superblock
            or self.current_cwd_inode_id == self.disk_manager.superblock.root_inode_id
        ):
            return

        parent_inode_id = _resolve_path_to_inode_id(  # Use the imported one
            self.disk_manager,
            self.current_cwd_inode_id,
            self.disk_manager.superblock.root_inode_id,
            "..",
        )

        if parent_inode_id is not None:
            self.current_cwd_inode_id = parent_inode_id
            self.user_auth.set_cwd_inode_id(parent_inode_id)
            self.address_bar.setText(
                get_inode_path_str(self.disk_manager, parent_inode_id)
            )
            self._populate_file_list_view(
                parent_inode_id
            )  # This calls _update_go_up_action_state
            self._expand_and_select_in_tree(parent_inode_id)
        else:
            QMessageBox.warning(self, "错误", "无法确定上一级目录。")

    def _update_go_up_action_state(self):
        if (
            self.current_cwd_inode_id is not None
            and self.disk_manager
            and self.disk_manager.superblock
            and self.current_cwd_inode_id != self.disk_manager.superblock.root_inode_id
        ):
            self.go_up_action.setEnabled(True)
        else:
            self.go_up_action.setEnabled(False)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    class MockInode:  # Simplified
        def __init__(
            self,
            id_val,
            type_val,
            name="",
            size=0,
            mtime=None,
            owner_uid=0,
            permissions=0o644,
            link_count=1,
            blocks_count=0,
        ):
            self.id = id_val
            self.type = type_val
            self.name = name
            self.size = size
            self.mtime = mtime if mtime is not None else time.time()
            self.atime = self.mtime
            self.ctime = self.mtime
            self.owner_uid = owner_uid
            self.permissions = permissions
            self.link_count = link_count
            self.blocks_count = blocks_count
            if self.type == FileType.DIRECTORY:
                self.permissions = 0o755
                self.link_count = 2

    class MockDiskManager:  # Simplified
        def __init__(self):
            self.is_formatted = True
            self.superblock = type(
                "SB", (), {"root_inode_id": 0, "total_inodes": 20, "block_size": 512}
            )()
            self.inodes_map = {}
            self.dir_entries_map = {}
            self._init_mock_data()

        def _init_mock_data(self):
            self.inodes_map = {
                0: MockInode(0, FileType.DIRECTORY, "/", size=3),
                1: MockInode(1, FileType.DIRECTORY, "dirA", size=2),
                2: MockInode(2, FileType.FILE, "fileA.txt", size=1024),
                3: MockInode(
                    3, FileType.FILE, "fileB.log", size=200, mtime=time.time() - 3600
                ),
            }
            self.dir_entries_map = {
                0: [
                    DirectoryEntry(".", 0),
                    DirectoryEntry("..", 0),
                    DirectoryEntry("dirA", 1),
                    DirectoryEntry("fileA.txt", 2),
                    DirectoryEntry("fileB.log", 3),
                ],
                1: [DirectoryEntry(".", 1), DirectoryEntry("..", 0)],
            }
            self.inodes_map[0].size = len(self.dir_entries_map[0])  # Correct dir size
            self.inodes_map[1].size = len(self.dir_entries_map[1])

        def get_inode(self, inode_id):
            return self.inodes_map.get(inode_id)

        def format_disk(self):
            print("Mock DM: format_disk called")
            self._init_mock_data()
            return True

        def save_disk_image(self):
            print("Mock DM: Disk image saved (simulated).")

    class MockUserAuth:  # Simplified
        def __init__(self):
            self.current_user = type(
                "User", (), {"username": "mock_root", "uid": ROOT_UID}
            )()
            self.cwd_inode_id = 0

        def get_current_user(self):
            return self.current_user

        def get_cwd_inode_id(self):
            return self.cwd_inode_id

        def set_cwd_inode_id(self, inode_id):
            self.cwd_inode_id = inode_id

        def create_user(self, u, p):
            print(f"Mock UA: create_user({u}, {p})")
            return True, f"Mock user {u} created."

    class MockPersistenceManager:  # Simplified
        def save_disk_image(self, disk):
            print("Mock PM: Disk image saved (simulated).")

    _original_list_directory = list_directory
    _original_resolve_path = _resolve_path_to_inode_id

    # Mock essential backend functions
    def mock_list_directory_minimal(dm_mock, inode_id_mock):
        entries = dm_mock.dir_entries_map.get(inode_id_mock, [])
        detailed_mock_entries = []
        for entry_obj in entries:
            inode = dm_mock.get_inode(entry_obj.inode_id)
            if inode:
                detailed_mock_entries.append(
                    {
                        "name": entry_obj.name,
                        "inode_id": entry_obj.inode_id,
                        "type": inode.type.name,
                        "size": inode.size,
                        "mtime": inode.mtime,
                    }
                )
        return True, "Mock success", detailed_mock_entries

    def mock_resolve_path_minimal(dm_mock, cwd_id, root_id, path_str):
        if path_str == "..":
            if cwd_id == root_id:
                return root_id
            for (
                p_id,
                entries,
            ) in dm_mock.dir_entries_map.items():  # Find parent of cwd_id
                if any(
                    e.inode_id == cwd_id and e.name != "." and e.name != ".."
                    for e in entries
                ):
                    return p_id
            return None  # Should not happen if cwd_id is not root
        # Basic name resolution in CWD
        if path_str in [e.name for e in dm_mock.dir_entries_map.get(cwd_id, [])]:
            return next(
                e.inode_id
                for e in dm_mock.dir_entries_map.get(cwd_id, [])
                if e.name == path_str
            )
        if path_str == "/":
            return root_id
        if not path_str:
            return cwd_id  # current dir for empty path
        return None  # Simplified

    list_directory = mock_list_directory_minimal
    _resolve_path_to_inode_id = mock_resolve_path_minimal

    mock_dm_instance = MockDiskManager()
    mock_auth_instance = MockUserAuth()
    mock_pm_instance = MockPersistenceManager()

    main_win = MainWindow(mock_dm_instance, mock_auth_instance, mock_pm_instance)
    main_win.show()
    app_exit_code = app.exec()

    list_directory = _original_list_directory  # Restore
    _resolve_path_to_inode_id = _original_resolve_path

    sys.exit(app_exit_code)
