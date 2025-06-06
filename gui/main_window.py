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
from PyQt6.QtCore import Qt, QModelIndex, QPoint, QItemSelectionModel

from fs_core.dir_ops import (
    list_directory,
    make_directory,
    remove_directory,
    rename_item,
    _resolve_path_to_inode_id,
)
from fs_core.file_ops import create_file, delete_file, create_symbolic_link
from fs_core.datastructures import FileType
from fs_core.fs_utils import get_inode_path_str
from user_management.user_auth import ROOT_UID

from .text_editor_dialog import TextEditorDialog
from .properties_dialog import PropertiesDialog

# Custom Data Roles
INODE_ID_ROLE = Qt.ItemDataRole.UserRole
IS_DIR_ROLE = Qt.ItemDataRole.UserRole + 1
TYPE_STR_ROLE = Qt.ItemDataRole.UserRole + 2
CHILDREN_LOADED_ROLE = Qt.ItemDataRole.UserRole + 3


class SortableStandardItem(QStandardItem):
    """A QStandardItem subclass that allows sorting by a custom key."""

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
                # Fallback to QStandardItem's default comparison (text-based)
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
        self.address_bar = QLineEdit()  # Moved here to be accessible earlier

        self.setWindowTitle(f"模拟文件系统 - 用户: {username}")
        self.setGeometry(100, 100, 900, 600)

        self._create_base_actions()
        self._create_menus()
        self._create_status_bar()
        self._setup_central_widget()

        self._initialize_views()

    def _setup_central_widget(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        main_layout.addWidget(self.address_bar)
        self.address_bar.setReadOnly(True)

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
        main_layout.addWidget(self.splitter)

    def _initialize_views(self):
        initial_path_str = (
            get_inode_path_str(self.disk_manager, self.current_cwd_inode_id)
            if self.current_cwd_inode_id is not None
            else "[Uninitialized]"
        )
        self.address_bar.setText(initial_path_str)

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
            self._refresh_current_views()
            if self.file_list_model.rowCount() > 0:
                self.file_list_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        else:
            self.status_bar.showMessage("错误：磁盘未格式化或无法访问根目录", 5000)

        self._update_go_up_action_state()

    # ICON METHODS
    def _get_folder_icon(self) -> QIcon:
        icon = QIcon.fromTheme(
            "folder-open",
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon),
        )
        return icon

    def _get_file_icon(self) -> QIcon:
        icon = QIcon.fromTheme(
            "text-plain", self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        )
        return icon

    def _get_symlink_icon(self) -> QIcon:
        return self.style().standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon)

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

    def _populate_children_in_tree(
        self, parent_q_item: QStandardItem, parent_inode_id: int
    ):
        if not self.disk_manager or not self.user_auth:
            return
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
        for entry in entries:
            if entry.get("type") == FileType.DIRECTORY.name and entry.get(
                "name"
            ) not in [".", ".."]:
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
            self.current_cwd_inode_id = item_inode_id
            self.user_auth.set_cwd_inode_id(item_inode_id)
            self._refresh_current_views()

    def on_item_double_clicked_in_list_view(self, index: QModelIndex):
        if not index.isValid():
            return

        name_col_idx = self.file_list_model.index(index.row(), 0)
        item_inode_id = self.file_list_model.data(name_col_idx, INODE_ID_ROLE)
        item_type_str = self.file_list_model.data(name_col_idx, TYPE_STR_ROLE)
        item_name = self.file_list_model.data(name_col_idx, Qt.ItemDataRole.DisplayRole)
        item_is_dir = self.file_list_model.data(name_col_idx, IS_DIR_ROLE)

        if item_inode_id is None or item_name is None:
            return

        if item_type_str == FileType.SYMBOLIC_LINK.name:
            # Construct the absolute path of the link itself to resolve it
            current_path = get_inode_path_str(
                self.disk_manager, self.current_cwd_inode_id
            )
            link_full_path = (
                f"{current_path}/{item_name}"
                if current_path != "/"
                else f"/{item_name}"
            )

            resolved_inode_id = _resolve_path_to_inode_id(
                self.disk_manager,
                self.current_cwd_inode_id,
                self.disk_manager.superblock.root_inode_id,
                link_full_path,
            )

            if resolved_inode_id is None:
                QMessageBox.warning(
                    self, "链接无效", f"符号链接 '{item_name}' 指向的目标不存在或无效。"
                )
                return

            target_inode = self.disk_manager.get_inode(resolved_inode_id)
            if not target_inode:
                QMessageBox.warning(self, "链接无效", "无法获取链接目标的信息。")
                return

            if target_inode.type == FileType.DIRECTORY:
                # If link target is a directory, navigate to it
                self.current_cwd_inode_id = resolved_inode_id
                self.user_auth.set_cwd_inode_id(resolved_inode_id)
                self._refresh_current_views()
                self._expand_and_select_in_tree(resolved_inode_id)
            else:  # Link target is a file
                self._open_file_by_inode(resolved_inode_id)
            return

        if item_is_dir:
            self.current_cwd_inode_id = item_inode_id
            self.user_auth.set_cwd_inode_id(item_inode_id)
            self._refresh_current_views()
            self._expand_and_select_in_tree(item_inode_id)
        else:  # Regular file
            self._open_file_by_inode(item_inode_id, item_name)

    def _open_file_by_inode(self, inode_id: int, name_hint: Optional[str] = None):
        """辅助函数：当已知文件的inode时，打开该文件。"""
        target_inode = self.disk_manager.get_inode(inode_id)
        if not target_inode:
            QMessageBox.critical(self, "错误", f"无法找到inode {inode_id}。")
            return

        # 修正：通过父目录路径和文件名来构建完整路径
        parent_path = get_inode_path_str(self.disk_manager, self.current_cwd_inode_id)
        if parent_path.startswith("[Error"):
            QMessageBox.critical(self, "错误", f"无法解析父目录路径以打开文件。")
            return

        file_name = name_hint
        if not file_name:  # 如果没有从UI获得文件名，则需要查找
            success, _, parent_entries = list_directory(
                self.disk_manager, self.current_cwd_inode_id
            )
            if success and parent_entries:
                found_entry = next(
                    (e for e in parent_entries if e.get("inode_id") == inode_id), None
                )
                if found_entry:
                    file_name = found_entry.get("name")

        if not file_name:
            QMessageBox.critical(
                self, "错误", f"在当前目录中找不到inode {inode_id}对应的文件名。"
            )
            return

        file_path = (
            f"{parent_path}/{file_name}" if parent_path != "/" else f"/{file_name}"
        )

        # 检查是否是文本文件并使用编辑器打开
        is_text = any(
            file_name.lower().endswith(ext)
            for ext in [".txt", ".py", ".md", ".json", ".csv", ".log"]
        )
        if is_text:
            editor = TextEditorDialog(
                self.disk_manager, self.user_auth, self.pm, file_path, file_name, self
            )
            editor.exec()
            self._refresh_current_views()
        else:
            self._gui_action_show_properties(item_inode_id_to_show=inode_id)

    def _expand_and_select_in_tree(self, target_inode_id: int):
        # A simple approach to select if visible and expand:
        root = self.dir_tree_model.invisibleRootItem()
        found_item = None
        path_items = []

        def find_item_recursive(parent_item, target_id):
            nonlocal found_item, path_items
            if found_item:
                return True

            for row in range(parent_item.rowCount()):
                current_item = parent_item.child(row, 0)
                if not current_item:
                    continue

                path_items.append(current_item)
                if current_item.data(INODE_ID_ROLE) == target_id:
                    found_item = current_item
                    return True

                if current_item.data(IS_DIR_ROLE):
                    if find_item_recursive(current_item, target_id):
                        return True
                path_items.pop()
            return False

        if self.dir_tree_model.rowCount() > 0:
            root_gui_item = self.dir_tree_model.item(0)
            path_items.append(root_gui_item)
            if root_gui_item.data(INODE_ID_ROLE) == target_inode_id:
                found_item = root_gui_item
            else:
                find_item_recursive(root_gui_item, target_inode_id)

        if found_item:
            for item_in_path in path_items[:-1]:
                if item_in_path and item_in_path.index().isValid():
                    self.dir_tree_view.expand(item_in_path.index())
            self.dir_tree_view.setCurrentIndex(found_item.index())
            self.dir_tree_view.scrollTo(
                found_item.index(), QAbstractItemView.ScrollHint.PositionAtCenter
            )

    def _populate_file_list_view(self, dir_inode_id: int):
        self.file_list_model.setRowCount(0)
        self.status_bar.showMessage(f"正在加载目录 inode {dir_inode_id}...", 1000)
        success, _, entries = list_directory(self.disk_manager, dir_inode_id)
        if not success or entries is None:
            return

        for entry in entries:
            if entry.get("name") in [".", ".."]:
                continue

            type_str = entry.get("type", "UNKNOWN")
            name_item = QStandardItem(entry.get("name", "N/A"))
            name_item.setEditable(False)
            name_item.setData(entry.get("inode_id"), INODE_ID_ROLE)
            name_item.setData(type_str == FileType.DIRECTORY.name, IS_DIR_ROLE)
            name_item.setData(type_str, TYPE_STR_ROLE)

            if type_str == FileType.DIRECTORY.name:
                name_item.setIcon(self._get_folder_icon())
            elif type_str == FileType.SYMBOLIC_LINK.name:
                name_item.setIcon(self._get_symlink_icon())
            else:
                name_item.setIcon(self._get_file_icon())

            size_val = entry.get("size", 0)
            size_str = f"{size_val} B" if type_str != FileType.DIRECTORY.name else ""
            size_item = SortableStandardItem(size_str, size_val)
            size_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            size_item.setEditable(False)

            type_item = QStandardItem(type_str)
            type_item.setEditable(False)

            mtime_val = entry.get("mtime", 0)
            mtime_str = (
                time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime_val))
                if mtime_val > 0
                else "N/A"
            )
            date_item = SortableStandardItem(mtime_str, int(mtime_val))
            date_item.setEditable(False)

            self.file_list_model.appendRow([name_item, size_item, type_item, date_item])

        self._update_go_up_action_state()

    def _create_base_actions(self):
        style = self.style()
        self.go_up_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogToParent),
            "上一级(&U)",
            self,
        )
        self.go_up_action.setStatusTip("返回上一级目录")
        self.go_up_action.triggered.connect(self._gui_action_go_up)

        self.new_folder_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DirIcon),
            "新建文件夹(&N)...",
            self,
        )
        self.new_folder_action.setStatusTip("在当前位置创建一个新文件夹")
        self.new_folder_action.triggered.connect(self._gui_action_new_folder)

        self.new_file_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileIcon),
            "新建文件(&F)...",
            self,
        )
        self.new_file_action.setStatusTip("在当前位置创建一个新空文件")
        self.new_file_action.triggered.connect(self._gui_action_new_file)

        self.create_link_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon),
            "创建链接...",
            self,
        )
        self.create_link_action.setStatusTip("为选中的项目创建一个符号链接")
        self.create_link_action.triggered.connect(self._gui_action_create_link)

        self.rename_action = QAction("重命名(&R)...", self)
        self.rename_action.setStatusTip("重命名选中的文件或文件夹")
        self.rename_action.setShortcut(QKeySequence("F2"))
        self.rename_action.triggered.connect(self._gui_action_rename_item)

        self.properties_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView),
            "属性(&I)",
            self,
        )
        self.properties_action.setStatusTip("查看选中项目的属性")
        self.properties_action.triggered.connect(self._gui_action_show_properties)

        self.delete_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_TrashIcon), "删除(&D)", self
        )
        self.delete_action.setShortcut(QKeySequence("Delete"))
        self.delete_action.setStatusTip("删除选中的文件或文件夹")
        self.delete_action.triggered.connect(
            self._gui_action_delete_item_from_selection
        )

        self.create_user_action = QAction("创建用户...", self)
        self.create_user_action.setStatusTip("创建一个新用户 (仅限管理员)")
        self.create_user_action.triggered.connect(self._gui_action_create_user)

        self.format_disk_action = QAction("格式化磁盘...", self)
        self.format_disk_action.setStatusTip(
            "格式化整个磁盘，所有数据将丢失 (仅限管理员)"
        )
        self.format_disk_action.triggered.connect(self._gui_action_format_disk)

        self.exit_action = QAction(
            style.standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton),
            "&退出",
            self,
        )
        self.exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self.exit_action.setStatusTip("退出应用程序")
        self.exit_action.triggered.connect(self.close)

    def _create_menus(self):
        menu_bar = self.menuBar()
        menu_bar.addAction(self.go_up_action)
        menu_bar.addSeparator()

        file_menu = menu_bar.addMenu("文件(&F)")
        file_menu.addAction(self.new_folder_action)
        file_menu.addAction(self.new_file_action)
        file_menu.addAction(self.create_link_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        edit_menu = menu_bar.addMenu("编辑(&E)")
        edit_menu.addAction(self.rename_action)
        edit_menu.addAction(self.delete_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.properties_action)

        admin_menu = menu_bar.addMenu("系统管理(&S)")
        admin_menu.addAction(self.create_user_action)
        admin_menu.addAction(self.format_disk_action)

        is_admin = (
            self.user_auth.get_current_user()
            and self.user_auth.get_current_user().uid == ROOT_UID
        )
        admin_menu.setEnabled(is_admin)

    def _create_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("准备就绪", 3000)

    def closeEvent(self, event):
        if self.disk_manager and self.disk_manager.is_formatted and self.pm:
            self.pm.save_disk_image(self.disk_manager)
        super().closeEvent(event)

    def _gui_action_new_folder(self):
        current_user = self.user_auth.get_current_user()
        if not current_user or self.current_cwd_inode_id is None:
            QMessageBox.warning(self, "错误", "会话或CWD无效")
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
        current_user = self.user_auth.get_current_user()
        if not current_user or self.current_cwd_inode_id is None:
            QMessageBox.warning(self, "错误", "会话或CWD无效")
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

    def _gui_action_create_link(self):
        selected_indexes = self.file_list_view.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.information(self, "提示", "请先选择一个文件或目录来创建链接。")
            return

        name_col_idx = self.file_list_model.index(selected_indexes[0].row(), 0)
        target_name = self.file_list_model.data(
            name_col_idx, Qt.ItemDataRole.DisplayRole
        )

        parent_path = get_inode_path_str(self.disk_manager, self.current_cwd_inode_id)
        if parent_path.startswith("[Error"):
            QMessageBox.warning(self, "错误", "无法确定目标项目的父路径。")
            return

        target_full_path = (
            f"{parent_path}/{target_name}" if parent_path != "/" else f"/{target_name}"
        )

        default_link_name = f"{target_name} 的链接"
        link_name, ok = QInputDialog.getText(
            self,
            "创建链接",
            f"在当前目录创建指向 '{target_name}' 的链接，\n请输入链接名称:",
            text=default_link_name,
        )

        if ok and link_name:
            link_name = link_name.strip()
            if not link_name:
                QMessageBox.warning(self, "错误", "链接名称不能为空.")
                return
            if "/" in link_name:
                QMessageBox.warning(self, "错误", "链接名称不能包含'/'。")
                return

            current_user = self.user_auth.get_current_user()
            if not current_user:
                QMessageBox.warning(self, "错误", "无用户信息。")
                return

            success, msg, _ = create_symbolic_link(
                self.disk_manager,
                current_user.uid,
                self.current_cwd_inode_id,
                link_name,
                target_full_path,
            )
            (
                QMessageBox.information(self, "结果", msg)
                if success
                else QMessageBox.warning(self, "失败", msg)
            )
            if success:
                self._refresh_current_views()

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
        self, item_name, item_inode_id, item_type_str, parent_inode_id
    ):
        current_user = self.user_auth.get_current_user()
        if not current_user:
            QMessageBox.warning(self, "错误", "未找到当前用户信息.")
            return

        confirm_msg = (
            f"<b>警告：您确定要删除文件夹 '{item_name}' 及其所有内容吗？</b>"
            if item_type_str == FileType.DIRECTORY.name
            else f"您确定要删除 '{item_name}' 吗？"
        ) + "\n\n此操作无法撤销。"
        reply = QMessageBox.question(
            self,
            "确认删除",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        uid = current_user.uid
        success, message = False, ""
        if item_type_str in [FileType.FILE.name, FileType.SYMBOLIC_LINK.name]:
            success, message = delete_file(
                self.disk_manager, uid, parent_inode_id, item_name
            )
        elif item_type_str == FileType.DIRECTORY.name:
            success, message = remove_directory(
                self.disk_manager, uid, parent_inode_id, item_name
            )

        if success:
            QMessageBox.information(self, "成功", f"'{item_name}' 已删除。")
            if self.pm:
                self.pm.save_disk_image(self.disk_manager)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "删除失败", message)

    def _gui_action_rename_item(self):
        selected_indexes = self.file_list_view.selectionModel().selectedRows()
        if not selected_indexes:
            QMessageBox.information(self, "提示", "请选择一个项目进行重命名.")
            return

        name_col_idx = self.file_list_model.index(selected_indexes[0].row(), 0)
        old_name = self.file_list_model.data(name_col_idx, Qt.ItemDataRole.DisplayRole)

        if old_name is None or old_name in [".", ".."]:
            QMessageBox.warning(self, "错误", f"无法重命名 '{old_name}'。")
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
        elif ok:
            QMessageBox.warning(self, "错误", "新名称不能为空。")

    def _show_list_context_menu(self, point: QPoint):
        menu = QMenu(self.file_list_view)
        global_point = self.file_list_view.viewport().mapToGlobal(point)
        index_under_cursor = self.file_list_view.indexAt(point)

        if index_under_cursor.isValid():
            name_col_idx = self.file_list_model.index(index_under_cursor.row(), 0)
            item_name = self.file_list_model.data(
                name_col_idx, Qt.ItemDataRole.DisplayRole
            )
            if item_name and item_name not in [".", ".."]:
                current_selection = self.file_list_view.selectionModel()
                current_selection.clearSelection()
                current_selection.select(
                    name_col_idx.siblingAtRow(name_col_idx.row()),
                    QItemSelectionModel.SelectionFlag.Rows
                    | QItemSelectionModel.SelectionFlag.Select,
                )

                menu.addAction(self.rename_action)
                menu.addAction(self.delete_action)
                menu.addAction(self.properties_action)
                menu.addAction(self.create_link_action)
                menu.addSeparator()

        menu.addAction(self.new_folder_action)
        menu.addAction(self.new_file_action)
        menu.exec(global_point)

    def _refresh_current_views(self):
        """
        在操作后刷新所有相关视图（地址栏、文件列表、树状视图）以反映最新状态。
        """
        if self.current_cwd_inode_id is None:
            return

        # 1. 更新地址栏
        current_path_str = get_inode_path_str(
            self.disk_manager, self.current_cwd_inode_id
        )
        if current_path_str.startswith("[Error"):
            QMessageBox.warning(
                self,
                "错误",
                f"当前工作目录无效: {current_path_str}。将尝试重置到根目录。",
            )
            root_id = (
                self.disk_manager.superblock.root_inode_id
                if self.disk_manager.superblock
                else None
            )
            if root_id is not None:
                self.current_cwd_inode_id = root_id
                self.user_auth.set_cwd_inode_id(root_id)
                current_path_str = get_inode_path_str(self.disk_manager, root_id)
            else:
                self.address_bar.setText("[错误：无法访问文件系统根目录]")
                self.file_list_model.setRowCount(0)
                self.dir_tree_model.clear()
                self._update_go_up_action_state()
                return
        self.address_bar.setText(current_path_str)

        # 2. 保存文件列表视图当前的排序状态
        header = self.file_list_view.horizontalHeader()
        sort_info = (header.sortIndicatorSection(), header.sortIndicatorOrder())

        # 3. 重新填充文件列表视图
        self._populate_file_list_view(self.current_cwd_inode_id)

        # 4. 恢复文件列表的排序状态
        if self.file_list_model.rowCount() > 0:
            self.file_list_view.sortByColumn(*sort_info)

        # 5. 更新“返回上一级”按钮的状态
        self._update_go_up_action_state()

        # 6. 刷新树状视图中当前目录的子节点
        # 这是一个简化的刷新逻辑，确保在树状图中已展开的当前目录能反映其子目录的变化
        q_item_for_cwd = None
        if self.dir_tree_model.rowCount() > 0:
            root_gui_item = self.dir_tree_model.item(0)

            # 递归函数，用于在树状模型中查找对应inode_id的QStandardItem
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

        # 如果在树中找到了当前目录的项，并且它是展开的，就重新加载它的子项
        if q_item_for_cwd:
            q_item_for_cwd.setData(
                False, CHILDREN_LOADED_ROLE
            )  # 标记为“未加载”以强制刷新
            if self.dir_tree_view.isExpanded(q_item_for_cwd.index()):
                self._populate_children_in_tree(
                    q_item_for_cwd, self.current_cwd_inode_id
                )
            else:
                # 如果未展开，则清空其现有子项（通常是占位符），以便下次展开时重新加载
                q_item_for_cwd.removeRows(0, q_item_for_cwd.rowCount())
                # 如果它是个目录，重新添加一个占位符以显示展开箭头
                if q_item_for_cwd.data(IS_DIR_ROLE):
                    q_item_for_cwd.appendRow(QStandardItem())

        # 1. 更新地址栏
        current_path_str = get_inode_path_str(
            self.disk_manager, self.current_cwd_inode_id
        )
        if current_path_str.startswith("[Error"):
            QMessageBox.warning(
                self,
                "错误",
                f"当前工作目录无效: {current_path_str}。将尝试重置到根目录。",
            )
            root_id = (
                self.disk_manager.superblock.root_inode_id
                if self.disk_manager.superblock
                else None
            )
            if root_id is not None:
                self.current_cwd_inode_id = root_id
                self.user_auth.set_cwd_inode_id(root_id)
                current_path_str = get_inode_path_str(self.disk_manager, root_id)
            else:
                self.address_bar.setText("[错误：无法访问文件系统根目录]")
                self.file_list_model.setRowCount(0)
                self.dir_tree_model.clear()
                self._update_go_up_action_state()
                return
        self.address_bar.setText(current_path_str)

        # 2. 保存文件列表视图当前的排序状态
        header = self.file_list_view.horizontalHeader()
        sort_info = (header.sortIndicatorSection(), header.sortIndicatorOrder())

        # 3. 重新填充文件列表视图
        self._populate_file_list_view(self.current_cwd_inode_id)

        # 4. 恢复文件列表的排序状态
        if self.file_list_model.rowCount() > 0:
            self.file_list_view.sortByColumn(*sort_info)

        # 5. 更新“返回上一级”按钮的状态
        self._update_go_up_action_state()

        # 6. 刷新树状视图中当前目录的子节点
        # 这是一个简化的刷新逻辑，确保在树状图中已展开的当前目录能反映其子目录的变化
        q_item_for_cwd = None
        if self.dir_tree_model.rowCount() > 0:
            root_gui_item = self.dir_tree_model.item(0)

            # 递归函数，用于在树状模型中查找对应inode_id的QStandardItem
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

        # 如果在树中找到了当前目录的项，并且它是展开的，就重新加载它的子项
        if q_item_for_cwd:
            q_item_for_cwd.setData(
                False, CHILDREN_LOADED_ROLE
            )  # 标记为“未加载”以强制刷新
            if self.dir_tree_view.isExpanded(q_item_for_cwd.index()):
                self._populate_children_in_tree(
                    q_item_for_cwd, self.current_cwd_inode_id
                )
            else:
                # 如果未展开，则清空其现有子项（通常是占位符），以便下次展开时重新加载
                q_item_for_cwd.removeRows(0, q_item_for_cwd.rowCount())
                # 如果它是个目录，重新添加一个占位符以显示展开箭头
                if q_item_for_cwd.data(IS_DIR_ROLE):
                    q_item_for_cwd.appendRow(QStandardItem())

    def _gui_action_show_properties(self, item_inode_id_to_show: Optional[int] = None):
        inode_id_for_props, name_for_props = None, "未知项目"

        if item_inode_id_to_show is not None:
            inode_id_for_props = item_inode_id_to_show
            # 尝试从当前文件列表中找到它的名字
            for row in range(self.file_list_model.rowCount()):
                idx = self.file_list_model.index(row, 0)
                if self.file_list_model.data(idx, INODE_ID_ROLE) == inode_id_for_props:
                    name_for_props = self.file_list_model.data(
                        idx, Qt.ItemDataRole.DisplayRole
                    )
                    break
        else:
            selected_indexes = self.file_list_view.selectionModel().selectedRows()
            if not selected_indexes:
                # 如果没有选中项，则显示当前目录的属性
                inode_id_for_props = self.current_cwd_inode_id
                if inode_id_for_props is None:
                    QMessageBox.information(self, "提示", "没有选中的项目。")
                    return
            else:
                name_col_idx = self.file_list_model.index(selected_indexes[0].row(), 0)
                inode_id_for_props = self.file_list_model.data(
                    name_col_idx, INODE_ID_ROLE
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

        # --- 修正：为所有类型的文件/链接正确构建路径 ---
        full_path_str = ""
        if target_inode.type == FileType.DIRECTORY:
            full_path_str = get_inode_path_str(self.disk_manager, target_inode.id)
            name_for_props = full_path_str.split("/")[-1] or "/"
        else:  # 对于文件和符号链接
            parent_path = get_inode_path_str(
                self.disk_manager, self.current_cwd_inode_id
            )
            if parent_path.startswith("[Error"):
                full_path_str = f"[父路径错误]/{name_for_props}"
            else:
                full_path_str = (
                    f"{parent_path}/{name_for_props}"
                    if parent_path != "/"
                    else f"/{name_for_props}"
                )

        if full_path_str.startswith("[Error"):
            QMessageBox.warning(
                self, "路径警告", f"无法完全解析项目路径: {full_path_str}"
            )

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
        if not (
            self.user_auth.get_current_user()
            and self.user_auth.get_current_user().uid == ROOT_UID
        ):
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
            return

        success, message = self.user_auth.create_user(new_username, new_password)
        (
            QMessageBox.information(self, "结果", message)
            if success
            else QMessageBox.warning(self, "创建失败", message)
        )

    def _gui_action_format_disk(self):
        if not (
            self.user_auth.get_current_user()
            and self.user_auth.get_current_user().uid == ROOT_UID
        ):
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

        if self.disk_manager.format_disk():
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
                self.user_auth.set_cwd_inode_id(new_root_id)
                self.current_cwd_inode_id = new_root_id

                self.dir_tree_model.clear()
                root_item = QStandardItem("/")
                root_item.setIcon(self._get_folder_icon())
                root_item.setEditable(False)
                root_item.setData(new_root_id, INODE_ID_ROLE)
                root_item.setData(True, IS_DIR_ROLE)
                root_item.setData(False, CHILDREN_LOADED_ROLE)
                self.dir_tree_model.appendRow(root_item)
                self._populate_children_in_tree(root_item, new_root_id)
                self.dir_tree_view.expand(root_item.index())
                self._refresh_current_views()
            else:
                QMessageBox.critical(self, "错误", "格式化后无法找到根目录。")
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
        parent_inode_id = _resolve_path_to_inode_id(
            self.disk_manager,
            self.current_cwd_inode_id,
            self.disk_manager.superblock.root_inode_id,
            "..",
        )
        if parent_inode_id is not None:
            self.current_cwd_inode_id = parent_inode_id
            self.user_auth.set_cwd_inode_id(parent_inode_id)
            self._refresh_current_views()
            self._expand_and_select_in_tree(parent_inode_id)
        else:
            QMessageBox.warning(self, "错误", "无法确定上一级目录。")

    def _update_go_up_action_state(self):
        is_not_root = (
            self.current_cwd_inode_id is not None
            and self.disk_manager.superblock
            and self.current_cwd_inode_id != self.disk_manager.superblock.root_inode_id
        )
        self.go_up_action.setEnabled(is_not_root)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Dummy classes for standalone testing
    class MockDisk:
        def __init__(self):
            self.is_formatted = True
            self.superblock = type("SB", (), {"root_inode_id": 0})()
            self.inodes = {
                0: type("Inode", (), {"id": 0, "type": FileType.DIRECTORY})()
            }
            self.dir_entries = {0: []}

        def get_inode(self, id):
            return self.inodes.get(id)

        def format_disk(self):
            print("Mock format")
            return True

        def save_disk_image(self):
            pass

    class MockAuth:
        def __init__(self):
            self.user = type("User", (), {"username": "mock", "uid": 0})()
            self.cwd = 0

        def get_current_user(self):
            return self.user

        def get_cwd_inode_id(self):
            return self.cwd

        def set_cwd_inode_id(self, id):
            self.cwd = id

        def create_user(self, u, p):
            return True, f"Mock user {u} created."

    class MockPM:
        def save_disk_image(self, disk):
            pass

    # Mock backend functions
    def mock_list_dir(dm, id):
        return True, "", []

    def mock_resolve(dm, cwd, root, path):
        return 0 if path in ["/", ".."] else None

    original_list_dir = list_directory
    original_resolve = _resolve_path_to_inode_id
    list_directory = mock_list_dir
    _resolve_path_to_inode_id = mock_resolve

    main_win = MainWindow(MockDisk(), MockAuth(), MockPM())
    main_win.show()

    exit_code = app.exec()

    list_directory = original_list_dir
    _resolve_path_to_inode_id = original_resolve

    sys.exit(exit_code)
