import sys
import time
import os
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
    QToolBar,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QFileDialog,
)
from PyQt6.QtGui import QAction, QStandardItemModel, QStandardItem, QIcon, QKeySequence
from PyQt6.QtCore import Qt, QModelIndex, QPoint, QItemSelectionModel, QTimer

from fs_core.disk_manager import DiskManager
from user_management.user_auth import UserAuth
from fs_core.dir_ops import (
    list_directory,
    make_directory,
    remove_directory,
    rename_item,
    _resolve_path_to_inode_id,
)
from fs_core.file_ops import create_file, delete_file, create_symbolic_link, create_hard_link, encrypt_file, compress_file, write_file_content
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

# 文件/目录/符号链接图标
FILE_ICON = QIcon.fromTheme("text-x-generic")
DIR_ICON = QIcon.fromTheme("folder")
LINK_ICON = QIcon.fromTheme("emblem-symbolic-link")


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
    def __init__(self, disk_manager: DiskManager, user_auth: UserAuth):
        super().__init__()
        self.disk_manager = disk_manager
        self.user_auth = user_auth
        self.current_user_id = user_auth.get_current_user_uid()
        self.current_cwd_inode_id = user_auth.get_cwd_inode_id()
        
        # 添加历史记录
        self.history = []
        self.history_index = -1
        
        self.setWindowTitle("UNIX风格文件系统")
        self.setGeometry(100, 100, 1200, 800)
        
        # 设置现代化样式
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            QToolBar {
                background-color: #ffffff;
                border-bottom: 1px solid #e0e0e0;
                spacing: 5px;
                padding: 5px;
            }
            QToolBar QPushButton {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
            }
            QToolBar QPushButton:hover {
                background-color: #e9ecef;
                border-color: #adb5bd;
            }
            QToolBar QPushButton:pressed {
                background-color: #dee2e6;
            }
            QLineEdit {
                border: 1px solid #ced4da;
                border-radius: 4px;
                padding: 6px 10px;
                background-color: white;
            }
            QLineEdit:focus {
                border-color: #007bff;
                outline: none;
            }
            QTreeView, QTableView {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                gridline-color: #f8f9fa;
                selection-background-color: #007bff;
                selection-color: white;
            }
            QTreeView::item:hover, QTableView::item:hover {
                background-color: #f8f9fa;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                border: none;
                border-bottom: 1px solid #dee2e6;
                padding: 8px;
                font-weight: 600;
            }
            QStatusBar {
                background-color: #ffffff;
                border-top: 1px solid #e0e0e0;
                color: #6c757d;
            }
            QMenuBar {
                background-color: #ffffff;
                border-bottom: 1px solid #e0e0e0;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 8px 12px;
            }
            QMenuBar::item:selected {
                background-color: #f8f9fa;
            }
            QMenu {
                background-color: white;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 8px 20px;
                border-radius: 2px;
            }
            QMenu::item:selected {
                background-color: #007bff;
                color: white;
            }
        """)
        
        # 创建工具栏
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        
        # 添加地址栏
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("输入路径...")
        self.address_bar.returnPressed.connect(self.navigate_to_path)
        toolbar.addWidget(QLabel("地址:"))
        toolbar.addWidget(self.address_bar)
        
        # 添加地址栏分段导航
        self.address_segments = QToolBar()
        self.address_segments.setStyleSheet("QToolBar { border: none; }")
        toolbar.addWidget(self.address_segments)
        
        # 添加系统监控按钮
        monitor_action = QAction("系统监控", self)
        monitor_action.triggered.connect(self.show_system_monitor)
        toolbar.addAction(monitor_action)
        
        # 添加导航按钮
        back_action = QAction("后退", self)
        back_action.triggered.connect(self.go_back)
        toolbar.addAction(back_action)
        
        forward_action = QAction("前进", self)
        forward_action.triggered.connect(self.go_forward)
        toolbar.addAction(forward_action)
        
        up_action = QAction("上级", self)
        up_action.triggered.connect(self.go_up)
        toolbar.addAction(up_action)
        
        refresh_action = QAction("刷新", self)
        refresh_action.triggered.connect(self.refresh_view)
        toolbar.addAction(refresh_action)
        
        toolbar.addSeparator()
        
        # 添加文件操作按钮
        new_file_action = QAction("新建文件", self)
        new_file_action.triggered.connect(self.create_new_file)
        toolbar.addAction(new_file_action)
        
        new_dir_action = QAction("新建目录", self)
        new_dir_action.triggered.connect(self.create_new_directory)
        toolbar.addAction(new_dir_action)
        
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(self.delete_selected)
        toolbar.addAction(delete_action)
        
        toolbar.addSeparator()
        
        # 添加高级功能按钮
        hardlink_action = QAction("创建硬链接", self)
        hardlink_action.triggered.connect(self.create_hardlink)
        toolbar.addAction(hardlink_action)
        
        encrypt_action = QAction("加密", self)
        encrypt_action.triggered.connect(self.encrypt_file)
        toolbar.addAction(encrypt_action)
        
        compress_action = QAction("压缩", self)
        compress_action.triggered.connect(self.compress_file)
        toolbar.addAction(compress_action)
        
        # 创建主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QHBoxLayout(central_widget)

        # 创建左侧树状视图
        self.dir_tree_view = QTreeView()
        self.dir_tree_model = QStandardItemModel()
        self.dir_tree_view.setModel(self.dir_tree_model)
        self.dir_tree_view.setHeaderHidden(True)
        self.dir_tree_view.setMaximumWidth(300)
        self.dir_tree_view.clicked.connect(self.on_tree_item_clicked)
        
        # 创建右侧文件列表视图
        self.file_list = QTableWidget()
        self.file_list.setColumnCount(5)
        self.file_list.setHorizontalHeaderLabels(["名称", "类型", "大小", "修改时间", "权限"])
        
        # 设置列宽
        self.file_list.setColumnWidth(0, 200)  # 名称
        self.file_list.setColumnWidth(1, 80)   # 类型
        self.file_list.setColumnWidth(2, 100)  # 大小
        self.file_list.setColumnWidth(3, 150)  # 修改时间
        self.file_list.setColumnWidth(4, 100)  # 权限
        
        # 启用排序
        self.file_list.setSortingEnabled(True)
        
        # 设置选择模式
        self.file_list.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_list.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        
        # 连接信号
        self.file_list.itemDoubleClicked.connect(self._on_file_double_clicked)
        self.file_list.itemSelectionChanged.connect(self._on_selection_changed)
        
        # 右键菜单
        self.file_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_context_menu)
        
        # 拖放支持
        self.file_list.setDragEnabled(True)
        self.file_list.setAcceptDrops(True)
        self.file_list.setDropIndicatorShown(True)
        
        # 设置样式
        self.file_list.setAlternatingRowColors(True)
        self.file_list.setShowGrid(True)
        self.file_list.setGridStyle(Qt.PenStyle.SolidLine)
        
        # 设置表头样式
        header = self.file_list.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # 名称列自适应
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)    # 类型列固定
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # 大小列固定
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)    # 时间列固定
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # 权限列固定
        
        # 设置表头字体
        font = header.font()
        font.setBold(True)
        header.setFont(font)
        
        # 设置表头背景色
        header.setStyleSheet("""
            QHeaderView::section {
                background-color: #f0f0f0;
                border: 1px solid #d0d0d0;
                padding: 4px;
                font-weight: bold;
            }
            QHeaderView::section:hover {
                background-color: #e0e0e0;
            }
        """)
        
        # 添加到布局
        layout.addWidget(self.dir_tree_view, 1)
        layout.addWidget(self.file_list, 2)
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 检查磁盘是否已格式化
        if not self.disk_manager.is_formatted or not self.disk_manager.superblock:
            self.prompt_format_disk()
        else:
            # 初始化视图
            self._populate_tree_view()
            self._refresh_current_views()

        # 设置状态栏
        self.statusBar().showMessage("就绪")

    def navigate_to_path(self):
        """导航到地址栏指定的路径"""
        path = self.address_bar.text().strip()
        if not path:
            return

        # 解析路径
        if path.startswith('/'):
            # 绝对路径
            target_path = path
        else:
            # 相对路径
            target_path = os.path.join(self.current_path, path)
        
        # 标准化路径
        target_path = os.path.normpath(target_path)
        
        # 检查路径是否存在
        success, msg, inode_id = _resolve_path_to_inode_id(
            self.disk_manager,
            self.current_cwd_inode_id,
            self.disk_manager.superblock.root_inode_id,
            target_path,
        )
        if not success:
            QMessageBox.warning(self, "路径错误", f"无法访问路径：{msg}")
            return

        # 导航到目标路径
        self.navigate_to_directory(target_path, inode_id)
    
    def go_back(self):
        """后退"""
        if self.history_index > 0:
            self.history_index -= 1
            path, inode_id = self.history[self.history_index]
            self.navigate_to_directory(path, inode_id, update_history=False)
            self.statusBar().showMessage(f"后退到: {path}")
    
    def go_forward(self):
        """前进"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            path, inode_id = self.history[self.history_index]
            self.navigate_to_directory(path, inode_id, update_history=False)
            self.statusBar().showMessage(f"前进到: {path}")
    
    def go_up(self):
        """上级目录"""
        if self.current_cwd_inode_id != self.disk_manager.superblock.root_inode_id:
            # 获取当前目录的父目录
            success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
            if success:
                for entry in entries:
                    if entry.get("name") == "..":
                        parent_inode_id = entry.get("inode_id")
                        if parent_inode_id != self.current_cwd_inode_id:
                            # 获取父目录路径
                            parent_path = get_inode_path_str(self.disk_manager, parent_inode_id)
                            self.navigate_to_directory(parent_path, parent_inode_id)
                            self.statusBar().showMessage(f"上级目录: {parent_path}")
                            return
            else:
                QMessageBox.warning(self, "错误", f"无法读取当前目录：{msg}")
        else:
            self.statusBar().showMessage("已在根目录")

    def refresh_view(self):
        """刷新视图"""
        self._refresh_current_views()
    
    def navigate_to_directory(self, path: str, inode_id: int, update_history: bool = True):
        """导航到指定目录"""
        # 更新当前路径
        self.current_cwd_inode_id = inode_id
        self.user_auth.set_cwd_inode_id(inode_id)
        
        # 更新历史记录
        if update_history:
            # 移除当前位置之后的历史记录
            self.history = self.history[:self.history_index + 1]
            # 添加新位置
            self.history.append((path, inode_id))
            self.history_index = len(self.history) - 1
            # 限制历史记录长度
            if len(self.history) > 50:
                self.history.pop(0)
                self.history_index -= 1
        
        # 刷新视图
        self._refresh_current_views()
    
    def create_hardlink(self):
        """创建硬链接"""
        selected_items = self.file_list.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "选择错误", "请先选择要创建硬链接的文件")
            return

        # 获取选中的行
        row = selected_items[0].row()
        file_name = self.file_list.item(row, 0).text()
        
        # 获取目标文件的i节点ID
        success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
        if not success:
            QMessageBox.warning(self, "错误", f"无法读取目录内容：{msg}")
            return

        target_inode_id = None
        for entry in entries:
            if entry.get("name") == file_name:
                target_inode_id = entry.get("inode_id")
                break
        
        if target_inode_id is None:
            QMessageBox.warning(self, "错误", "无法找到目标文件")
            return

        # 获取硬链接名称
        link_name, ok = QInputDialog.getText(self, "创建硬链接", "请输入硬链接名称")
        if not ok or not link_name:
            return
        
        # 创建硬链接
        success, msg, _ = create_hard_link(
            self.disk_manager,
            self.current_user_id,
            self.current_cwd_inode_id,
            link_name,
            target_inode_id
        )
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)
    
    def encrypt_file(self):
        """加密文件"""
        selected_items = self.file_list.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "选择错误", "请先选择要加密的文件")
            return
        
        # 获取选中的行
        row = selected_items[0].row()
        file_name = self.file_list.item(row, 0).text()
        
        # 获取目标文件的i节点ID
        success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
        if not success:
            QMessageBox.warning(self, "错误", f"无法读取目录内容：{msg}")
            return
        
        target_inode_id = None
        for entry in entries:
            if entry.get("name") == file_name:
                target_inode_id = entry.get("inode_id")
                break
        
        if target_inode_id is None:
            QMessageBox.warning(self, "错误", "无法找到目标文件")
            return
        
        # 获取密码
        password, ok = QInputDialog.getText(self, "加密文件", "请输入加密密码：", QLineEdit.EchoMode.Password)
        if not ok or not password:
            return
        
        # 加密文件
        success, msg = encrypt_file(
            self.disk_manager,
            self.current_user_id,
            target_inode_id,
            password
        )
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)
    
    def compress_file(self):
        """压缩文件"""
        selected_items = self.file_list.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "选择错误", "请先选择要压缩的文件")
            return
        
        # 获取选中的行
        row = selected_items[0].row()
        file_name = self.file_list.item(row, 0).text()
        
        # 获取目标文件的i节点ID
        success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
        if not success:
            QMessageBox.warning(self, "错误", f"无法读取目录内容：{msg}")
            return
        
        target_inode_id = None
        for entry in entries:
            if entry.get("name") == file_name:
                target_inode_id = entry.get("inode_id")
                break
        
        if target_inode_id is None:
            QMessageBox.warning(self, "错误", "无法找到目标文件")
            return
        
        # 获取压缩级别
        compression_level, ok = QInputDialog.getInt(
            self, "压缩文件", "请输入压缩级别(1-9)：", 6, 1, 9, 1
        )
        if not ok:
            return
        
        # 压缩文件
        success, msg = compress_file(
            self.disk_manager,
            self.current_user_id,
            target_inode_id,
            compression_level
        )
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)

    def create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu('文件')
        
        new_file_action = QAction('新建文件', self)
        new_file_action.triggered.connect(self.create_new_file)
        file_menu.addAction(new_file_action)
        
        new_dir_action = QAction('新建目录', self)
        new_dir_action.triggered.connect(self.create_new_directory)
        file_menu.addAction(new_dir_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction('退出', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 编辑菜单
        edit_menu = menubar.addMenu('编辑')
        
        delete_action = QAction('删除', self)
        delete_action.triggered.connect(self.delete_selected)
        edit_menu.addAction(delete_action)
        
        # 视图菜单
        view_menu = menubar.addMenu('视图')
        
        refresh_action = QAction('刷新', self)
        refresh_action.triggered.connect(self.refresh_view)
        view_menu.addAction(refresh_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu('工具')
        
        hardlink_action = QAction('创建硬链接', self)
        hardlink_action.triggered.connect(self.create_hardlink)
        tools_menu.addAction(hardlink_action)
        
        encrypt_action = QAction('加密文件', self)
        encrypt_action.triggered.connect(self.encrypt_file)
        tools_menu.addAction(encrypt_action)
        
        compress_action = QAction('压缩文件', self)
        compress_action.triggered.connect(self.compress_file)
        tools_menu.addAction(compress_action)
    
    def create_new_file(self):
        """创建新文件"""
        file_name, ok = QInputDialog.getText(self, "新建文件", "请输入文件名")
        if not ok or not file_name:
            return
        
        success, msg, _ = create_file(
            self.disk_manager,
            self.current_user_id,
            self.current_cwd_inode_id,
            file_name
        )
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)
    
    def create_new_directory(self):
        """创建新目录"""
        dir_name, ok = QInputDialog.getText(self, "新建目录", "请输入目录名")
        if not ok or not dir_name:
            return

        success, msg, _ = make_directory(
            self.disk_manager,
            self.current_user_id,
            self.current_cwd_inode_id,
            dir_name
        )
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)
    
    def delete_selected(self):
        """删除选中的文件或目录"""
        indexes = self.file_list.selectedIndexes()
        if not indexes:
            QMessageBox.warning(self, "选择错误", "请先选择要删除的文件或目录")
            return

        # 获取选中的行
        row = indexes[0].row()
        item_name = self.file_list.item(row, 0).text()
        
        # 确认删除
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除 '{item_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            success, msg = delete_file(
                self.disk_manager,
                self.current_user_id,
                self.current_cwd_inode_id,
                item_name
            )

            if success:
                QMessageBox.information(self, "成功", msg)
                self._refresh_current_views()
            else:
                QMessageBox.warning(self, "错误", msg)
    
    def on_tree_item_clicked(self, index):
        """树状视图项点击事件"""
        item = self.dir_tree_model.itemFromIndex(index)
        inode_id = item.data(INODE_ID_ROLE)
        if inode_id is not None:
            self.current_cwd_inode_id = inode_id
            self.user_auth.set_cwd_inode_id(inode_id)
            self._refresh_current_views()
    
    def _on_file_double_clicked(self, index):
        """文件列表双击事件"""
        row = index.row()
        item_name = self.file_list.item(row, 0).text()
        item_type = self.file_list.item(row, 1).text()
        
        if "目录" in item_type:
            # 进入目录
            self._navigate_to_directory(item_name)
        elif "文件" in item_type:
            # 打开文件
            self.open_file(item_name)
    
    def _on_selection_changed(self):
        """选择变化时更新状态栏"""
        self.update_status_bar()

    def open_file(self, file_name: str):
        """打开文件（文本编辑器）"""
        from fs_core.persistence_manager import PersistenceManager
        persistence_manager = PersistenceManager()
        file_path = f"{self.address_bar.text()}/{file_name}"
        editor = TextEditorDialog(
            self.disk_manager, 
            self.user_auth, 
            persistence_manager,
            file_path,
            file_name
        )
        editor.exec()
    
    def _populate_tree_view(self):
        """填充树状视图"""
        self.dir_tree_model.clear()
        
        # 添加根目录
        root_inode_id = self.disk_manager.superblock.root_inode_id
        root_item = QStandardItem("/")
        root_item.setData(root_inode_id, INODE_ID_ROLE)
        root_item.setData(True, IS_DIR_ROLE)
        root_item.setData(False, CHILDREN_LOADED_ROLE)
        root_item.setIcon(DIR_ICON)
        self.dir_tree_model.appendRow(root_item)
        
        # 展开根目录
        self.dir_tree_view.expand(root_item.index())
        
        # 连接展开信号
        self.dir_tree_view.expanded.connect(self._on_tree_item_expanded)

    def _on_tree_item_expanded(self, index):
        """树状视图项展开事件"""
        item = self.dir_tree_model.itemFromIndex(index)
        if item and not item.data(CHILDREN_LOADED_ROLE):
            inode_id = item.data(INODE_ID_ROLE)
            if inode_id is not None:
                self._populate_children_in_tree(item, inode_id)
    
    def _populate_children_in_tree(self, parent_item: QStandardItem, parent_inode_id: int):
        """递归填充树状视图的子项"""
        if parent_item.data(CHILDREN_LOADED_ROLE):
            return

        success, msg, entries = list_directory(self.disk_manager, parent_inode_id)
        if not success:
            return
        
        # 清空现有子项
        parent_item.removeRows(0, parent_item.rowCount())
        
        # 添加子目录（跳过'.'和'..'）
        for entry in entries:
            if entry.get("type") == "DIRECTORY" and entry.get("name") not in [".", ".."]:
                child_item = QStandardItem(entry.get("name"))
                child_item.setData(entry.get("inode_id"), INODE_ID_ROLE)
                child_item.setData(True, IS_DIR_ROLE)
                child_item.setData(False, CHILDREN_LOADED_ROLE)
                child_item.setIcon(DIR_ICON)
                parent_item.appendRow(child_item)
        
        # 标记为已加载
        parent_item.setData(True, CHILDREN_LOADED_ROLE)
    
    def _populate_file_list_view(self, inode_id: int):
        """填充文件列表视图"""
        self.file_list.setRowCount(0)
        
        success, msg, entries = list_directory(self.disk_manager, inode_id)
        if not success:
            return
        
        for entry in entries:
            # 跳过'.'和'..'条目
            if entry.get("name") in [".", ".."]:
                continue
                
            row = self.file_list.rowCount()
            self.file_list.insertRow(row)
            
            # 名称
            name_item = QTableWidgetItem(entry.get("name"))
            self.file_list.setItem(row, 0, name_item)
            
            # 类型
            type_code = entry.get("type")
            if type_code == "DIRECTORY":
                type_str = "目录"
            elif type_code == "SYMBOLIC_LINK":
                type_str = "符号链接"
            else:
                type_str = "文件"
            if entry.get("is_hardlink"):
                type_str += " (硬链接)"
            if entry.get("is_encrypted"):
                type_str += " (加密)"
            if entry.get("is_compressed"):
                type_str += " (压缩)"
            type_item = QTableWidgetItem(type_str)
            self.file_list.setItem(row, 1, type_item)
            
            # 大小
            size_str = str(entry.get("size", 0)) + " B"
            size_item = QTableWidgetItem(size_str)
            self.file_list.setItem(row, 2, size_item)
            
            # 权限
            permissions = entry.get("permissions", 0o644)
            perm_str = oct(permissions)[2:]
            perm_item = QTableWidgetItem(perm_str)
            self.file_list.setItem(row, 4, perm_item)
            
            # 修改时间
            mtime = entry.get("mtime", 0)
            time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            time_item = QTableWidgetItem(time_str)
            self.file_list.setItem(row, 3, time_item)
            
            # 设置图标
            icon = FILE_ICON
            if type_code == "DIRECTORY":
                icon = DIR_ICON
            elif type_code == "SYMBOLIC_LINK":
                icon = LINK_ICON
            name_item.setIcon(icon)
    
    def _refresh_current_views(self):
        """刷新当前视图"""
        # 更新地址栏
        current_path_str = get_inode_path_str(self.disk_manager, self.current_cwd_inode_id)
        self.address_bar.setText(current_path_str)
        
        # 更新地址栏分段导航
        self.update_address_segments(current_path_str)
        
        # 刷新文件列表
        self._populate_file_list_view(self.current_cwd_inode_id)
        
        # 刷新树状视图
        self._populate_tree_view()
        
        # 更新状态栏
        self.update_status_bar()

    def prompt_format_disk(self):
        reply = QMessageBox.question(
            self,
            "磁盘未格式化",
            "检测到磁盘未格式化，是否现在进行格式化？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            # 执行格式化
            if self.disk_manager.format_disk():
                QMessageBox.information(self, "格式化成功", "磁盘已成功格式化！")
                # After formatting, the root inode ID is available.
                # Update the CWD for both the window and the user authenticator.
                if self.disk_manager.superblock:
                    self.current_cwd_inode_id = self.disk_manager.superblock.root_inode_id
                    self.user_auth.set_cwd_inode_id(self.current_cwd_inode_id)
                self._populate_tree_view()
                self._refresh_current_views()
            else:
                QMessageBox.critical(self, "格式化失败", "磁盘格式化失败，请检查磁盘空间或配置。")
        else:
            QMessageBox.warning(self, "未格式化", "部分功能将不可用。")

    def _show_context_menu(self, pos):
        """显示文件列表右键菜单"""
        indexes = self.file_list.selectedIndexes()
        if not indexes:
            return
            
        menu = QMenu(self)
        
        # 文件操作
        open_action = QAction("打开", self)
        open_action.triggered.connect(self.open_selected_file)
        open_action.setShortcut(QKeySequence.StandardKey.Open)
        menu.addAction(open_action)
        
        menu.addSeparator()
        
        # 编辑操作
        copy_action = QAction("复制", self)
        copy_action.triggered.connect(self.copy_selected)
        copy_action.setShortcut(QKeySequence.StandardKey.Copy)
        menu.addAction(copy_action)
        
        cut_action = QAction("剪切", self)
        cut_action.triggered.connect(self.cut_selected)
        cut_action.setShortcut(QKeySequence.StandardKey.Cut)
        menu.addAction(cut_action)
        
        paste_action = QAction("粘贴", self)
        paste_action.triggered.connect(self.paste_items)
        paste_action.setShortcut(QKeySequence.StandardKey.Paste)
        menu.addAction(paste_action)
        
        menu.addSeparator()
        
        # 文件管理
        rename_action = QAction("重命名", self)
        rename_action.triggered.connect(self.rename_selected)
        rename_action.setShortcut(QKeySequence("F2"))
        menu.addAction(rename_action)
        
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(self.delete_selected)
        delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        menu.addAction(delete_action)
        
        menu.addSeparator()
        
        # 高级功能
        properties_action = QAction("属性", self)
        properties_action.triggered.connect(self.show_properties_selected)
        properties_action.setShortcut(QKeySequence("Alt+Enter"))
        menu.addAction(properties_action)
        
        # 加密/解密子菜单
        if len(indexes) == 1:  # 单个文件
            crypto_menu = menu.addMenu("加密/解密")
            
            encrypt_action = QAction("加密", self)
            encrypt_action.triggered.connect(self.encrypt_selected)
            crypto_menu.addAction(encrypt_action)
            
            decrypt_action = QAction("解密", self)
            decrypt_action.triggered.connect(self.decrypt_selected)
            crypto_menu.addAction(decrypt_action)
            
            # 压缩/解压子菜单
            compress_menu = menu.addMenu("压缩/解压")
            
            compress_action = QAction("压缩", self)
            compress_action.triggered.connect(self.compress_selected)
            compress_menu.addAction(compress_action)
            
            decompress_action = QAction("解压", self)
            decompress_action.triggered.connect(self.decompress_selected)
            compress_menu.addAction(decompress_action)
        
        menu.addSeparator()
        
        # 链接操作
        link_menu = menu.addMenu("链接")
        
        hardlink_action = QAction("创建硬链接", self)
        hardlink_action.triggered.connect(self.create_hardlink_selected)
        link_menu.addAction(hardlink_action)
        
        symlink_action = QAction("创建符号链接", self)
        symlink_action.triggered.connect(self.create_symlink_selected)
        link_menu.addAction(symlink_action)
        
        menu.addSeparator()
        
        # 其他操作
        copy_path_action = QAction("复制路径", self)
        copy_path_action.triggered.connect(self.copy_path_selected)
        menu.addAction(copy_path_action)
        
        refresh_action = QAction("刷新", self)
        refresh_action.triggered.connect(self.refresh_view)
        refresh_action.setShortcut(QKeySequence.StandardKey.Refresh)
        menu.addAction(refresh_action)
        
        menu.exec(self.file_list.viewport().mapToGlobal(pos))

    def open_selected_file(self):
        """打开选中的文件"""
        indexes = self.file_list.selectedIndexes()
        if len(indexes) == 1:
            row = indexes[0].row()
            file_name = self.file_list.item(row, 0).text()
            self.open_file(file_name)

    def copy_selected(self):
        """复制选中的文件"""
        indexes = self.file_list.selectedIndexes()
        if indexes:
            file_names = [self.file_list.item(idx.row(), 0).text() for idx in indexes]
            # 这里可以实现复制到剪贴板的逻辑
            QMessageBox.information(self, "复制", f"已复制 {len(file_names)} 个文件")

    def cut_selected(self):
        """剪切选中的文件"""
        indexes = self.file_list.selectedIndexes()
        if indexes:
            file_names = [self.file_list.item(idx.row(), 0).text() for idx in indexes]
            # 这里可以实现剪切的逻辑
            QMessageBox.information(self, "剪切", f"已剪切 {len(file_names)} 个文件")

    def paste_items(self):
        """粘贴文件"""
        try:
            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()
            
            if mime_data.hasUrls():
                # 从剪贴板获取文件URL
                urls = mime_data.urls()
                for url in urls:
                    if url.isLocalFile():
                        file_path = url.toLocalFile()
                        file_name = os.path.basename(file_path)
                        
                        # 检查目标目录是否已存在同名文件
                        success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
                        if success:
                            existing_names = [entry.get("name") for entry in entries]
                            if file_name in existing_names:
                                # 询问是否覆盖
                                reply = QMessageBox.question(
                                    self, "文件已存在", 
                                    f"文件 '{file_name}' 已存在，是否覆盖？",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                                )
                                if reply == QMessageBox.StandardButton.No:
                                    continue
                        
                        # 读取源文件内容
                        try:
                            with open(file_path, 'rb') as f:
                                content = f.read()
                            
                            # 创建新文件
                            success, msg, inode_id = create_file(
                                self.disk_manager,
                                self.current_user_id,
                                self.current_cwd_inode_id,
                                file_name
                            )
                            
                            if success and inode_id:
                                # 写入文件内容
                                write_success, write_msg = write_file_content(
                                    self.disk_manager, inode_id, content
                                )
                                if write_success:
                                    QMessageBox.information(self, "成功", f"已粘贴文件：{file_name}")
                                else:
                                    QMessageBox.warning(self, "错误", f"写入文件内容失败：{write_msg}")
                            else:
                                QMessageBox.warning(self, "错误", f"创建文件失败：{msg}")
                                
                        except Exception as e:
                            QMessageBox.warning(self, "错误", f"读取源文件失败：{e}")
                
                # 刷新视图
                self._refresh_current_views()
                
            elif mime_data.hasText():
                # 从剪贴板获取文本
                text = mime_data.text()
                if text.strip():
                    # 创建文本文件
                    file_name = "粘贴的文本.txt"
                    
                    # 检查文件名是否已存在
                    counter = 1
                    while True:
                        success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
                        if success:
                            existing_names = [entry.get("name") for entry in entries]
                            if file_name not in existing_names:
                                break
                            file_name = f"粘贴的文本_{counter}.txt"
                            counter += 1
                    
                    # 创建文件
                    success, msg, inode_id = create_file(
                        self.disk_manager,
                        self.current_user_id,
                        self.current_cwd_inode_id,
                        file_name
                    )
                    
                    if success and inode_id:
                        # 写入文本内容
                        write_success, write_msg = write_file_content(
                            self.disk_manager, inode_id, text.encode('utf-8')
                        )
                        if write_success:
                            QMessageBox.information(self, "成功", f"已粘贴文本到文件：{file_name}")
                            self._refresh_current_views()
                        else:
                            QMessageBox.warning(self, "错误", f"写入文件内容失败：{write_msg}")
                    else:
                        QMessageBox.warning(self, "错误", f"创建文件失败：{msg}")
            else:
                QMessageBox.information(self, "粘贴", "剪贴板中没有可粘贴的文件或文本")
                
        except Exception as e:
            QMessageBox.warning(self, "错误", f"粘贴操作失败：{e}")

    def encrypt_selected(self):
        """加密选中的文件"""
        indexes = self.file_list.selectedIndexes()
        if len(indexes) == 1:
            row = indexes[0].row()
            file_name = self.file_list.item(row, 0).text()
            self.encrypt_file_by_name(file_name)

    def decrypt_selected(self):
        """解密选中的文件"""
        indexes = self.file_list.selectedIndexes()
        if len(indexes) == 1:
            row = indexes[0].row()
            file_name = self.file_list.item(row, 0).text()
            self.decrypt_file_by_name(file_name)

    def compress_selected(self):
        """压缩选中的文件"""
        indexes = self.file_list.selectedIndexes()
        if len(indexes) == 1:
            row = indexes[0].row()
            file_name = self.file_list.item(row, 0).text()
            self.compress_file_by_name(file_name)

    def decompress_selected(self):
        """解压选中的文件"""
        indexes = self.file_list.selectedIndexes()
        if len(indexes) == 1:
            row = indexes[0].row()
            file_name = self.file_list.item(row, 0).text()
            self.decompress_file_by_name(file_name)

    def create_hardlink_selected(self):
        """为选中的文件创建硬链接"""
        indexes = self.file_list.selectedIndexes()
        if len(indexes) == 1:
            row = indexes[0].row()
            file_name = self.file_list.item(row, 0).text()
            self.create_hardlink_by_name(file_name)

    def create_symlink_selected(self):
        """为选中的文件创建符号链接"""
        indexes = self.file_list.selectedIndexes()
        if len(indexes) == 1:
            row = indexes[0].row()
            file_name = self.file_list.item(row, 0).text()
            self.create_symlink_by_name(file_name)

    def encrypt_file_by_name(self, file_name: str):
        """根据文件名加密文件"""
        # 获取目标文件的i节点ID
        success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
        if not success:
            QMessageBox.warning(self, "错误", f"无法读取目录内容：{msg}")
            return
        
        target_inode_id = None
        for entry in entries:
            if entry.get("name") == file_name:
                target_inode_id = entry.get("inode_id")
                break
        
        if target_inode_id is None:
            QMessageBox.warning(self, "错误", "无法找到目标文件")
            return
        
        # 获取密码
        password, ok = QInputDialog.getText(self, "加密文件", "请输入加密密码：", QLineEdit.EchoMode.Password)
        if not ok or not password:
            return
        
        # 加密文件
        success, msg = encrypt_file(self.disk_manager, self.current_user_id, target_inode_id, password)
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)

    def decrypt_file_by_name(self, file_name: str):
        """根据文件名解密文件"""
        # 获取目标文件的i节点ID
        success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
        if not success:
            QMessageBox.warning(self, "错误", f"无法读取目录内容：{msg}")
            return
        
        target_inode_id = None
        for entry in entries:
            if entry.get("name") == file_name:
                target_inode_id = entry.get("inode_id")
                break
        
        if target_inode_id is None:
            QMessageBox.warning(self, "错误", "无法找到目标文件")
            return
        
        # 获取密码
        password, ok = QInputDialog.getText(self, "解密文件", "请输入解密密码：", QLineEdit.EchoMode.Password)
        if not ok or not password:
            return
        
        # 解密文件
        from fs_core.file_ops import decrypt_file
        success, msg = decrypt_file(self.disk_manager, self.current_user_id, target_inode_id, password)
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)

    def compress_file_by_name(self, file_name: str):
        """根据文件名压缩文件"""
        # 获取目标文件的i节点ID
        success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
        if not success:
            QMessageBox.warning(self, "错误", f"无法读取目录内容：{msg}")
            return
        
        target_inode_id = None
        for entry in entries:
            if entry.get("name") == file_name:
                target_inode_id = entry.get("inode_id")
                break
        
        if target_inode_id is None:
            QMessageBox.warning(self, "错误", "无法找到目标文件")
            return
        
        # 获取压缩级别
        compression_level, ok = QInputDialog.getInt(
            self, "压缩文件", "请输入压缩级别(1-9)：", 6, 1, 9, 1
        )
        if not ok:
            return
        
        # 压缩文件
        success, msg = compress_file(self.disk_manager, self.current_user_id, target_inode_id, compression_level)
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)

    def decompress_file_by_name(self, file_name: str):
        """根据文件名解压文件"""
        # 获取目标文件的i节点ID
        success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
        if not success:
            QMessageBox.warning(self, "错误", f"无法读取目录内容：{msg}")
            return
        
        target_inode_id = None
        for entry in entries:
            if entry.get("name") == file_name:
                target_inode_id = entry.get("inode_id")
                break
        
        if target_inode_id is None:
            QMessageBox.warning(self, "错误", "无法找到目标文件")
            return
        
        # 解压文件
        from fs_core.file_ops import decompress_file
        success, msg = decompress_file(self.disk_manager, self.current_user_id, target_inode_id)
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)

    def create_hardlink_by_name(self, file_name: str):
        """根据文件名创建硬链接"""
        # 获取目标文件的i节点ID
        success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
        if not success:
            QMessageBox.warning(self, "错误", f"无法读取目录内容：{msg}")
            return

        target_inode_id = None
        for entry in entries:
            if entry.get("name") == file_name:
                target_inode_id = entry.get("inode_id")
                break
        
        if target_inode_id is None:
            QMessageBox.warning(self, "错误", "无法找到目标文件")
            return

        # 获取硬链接名称
        link_name, ok = QInputDialog.getText(self, "创建硬链接", "请输入硬链接名称")
        if not ok or not link_name:
            return
        
        # 创建硬链接
        success, msg, _ = create_hard_link(
            self.disk_manager,
            self.current_user_id,
            self.current_cwd_inode_id,
            link_name,
            target_inode_id
        )
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)

    def create_symlink_by_name(self, file_name: str):
        """根据文件名创建符号链接"""
        # 获取目标路径
        target_path, ok = QInputDialog.getText(self, "创建符号链接", "请输入目标路径")
        if not ok or not target_path:
            return

        # 获取符号链接名称
        link_name, ok = QInputDialog.getText(self, "创建符号链接", "请输入符号链接名称")
        if not ok or not link_name:
            return
        
        # 创建符号链接
        success, msg, _ = create_symbolic_link(
            self.disk_manager,
            self.current_user_id,
            self.current_cwd_inode_id,
            link_name,
            target_path
        )
        
        if success:
            QMessageBox.information(self, "成功", msg)
            self._refresh_current_views()
        else:
            QMessageBox.warning(self, "错误", msg)

    def update_address_segments(self, path: str):
        """更新地址栏分段导航"""
        # 清空现有分段
        self.address_segments.clear()
        
        if not path or path == "/":
            # 根目录
            root_btn = QPushButton("/")
            root_btn.clicked.connect(lambda: self.navigate_to_root())
            self.address_segments.addWidget(root_btn)
            return
        
        # 分割路径
        segments = path.strip("/").split("/")
        current_path = ""
        
        for i, segment in enumerate(segments):
            if i > 0:
                current_path += "/"
            current_path += segment
            
            # 创建分段按钮
            btn = QPushButton(segment)
            btn.setStyleSheet("QPushButton { border: none; background: transparent; }")
            btn.clicked.connect(lambda checked, p=current_path: self.navigate_to_segment(p))
            self.address_segments.addWidget(btn)
            
            # 添加分隔符（除了最后一个）
            if i < len(segments) - 1:
                separator = QLabel("/")
                separator.setStyleSheet("QLabel { color: #666; }")
                self.address_segments.addWidget(separator)

    def navigate_to_root(self):
        """导航到根目录"""
        if self.disk_manager.superblock:
            self.navigate_to_directory("/", self.disk_manager.superblock.root_inode_id)

    def navigate_to_segment(self, path: str):
        """导航到指定路径段"""
        success, msg, inode_id = _resolve_path_to_inode_id(
            self.disk_manager,
            self.current_cwd_inode_id,
            self.disk_manager.superblock.root_inode_id,
            path,
        )
        if success:
            self.navigate_to_directory(path, inode_id)

    def update_status_bar(self):
        """更新状态栏信息"""
        selected_items = self.file_list.selectedIndexes()
        if selected_items:
            # 显示选中项信息
            count = len(set(idx.row() for idx in selected_items))
            if count == 1:
                row = selected_items[0].row()
                name = self.file_list.item(row, 0).text()
                size = self.file_list.item(row, 2).text()
                self.statusBar().showMessage(f"已选择: {name} ({size})")
            else:
                self.statusBar().showMessage(f"已选择 {count} 个项目")
        else:
            # 显示当前目录信息
            success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
            if success:
                file_count = sum(1 for entry in entries if entry.get("type") != FileType.DIRECTORY)
                dir_count = sum(1 for entry in entries if entry.get("type") == FileType.DIRECTORY)
                self.statusBar().showMessage(f"当前目录: {file_count} 个文件, {dir_count} 个目录")
            else:
                self.statusBar().showMessage("就绪")

    def rename_selected(self):
        """重命名选中的文件或目录"""
        indexes = self.file_list.selectedIndexes()
        if not indexes:
            QMessageBox.warning(self, "选择错误", "请先选择要重命名的文件或目录")
            return
            
        idx = indexes[0]
        old_name = self.file_list.item(idx.row(), 0).text()
        new_name, ok = QInputDialog.getText(self, "重命名", f"将 '{old_name}' 重命名为:")
        if ok and new_name and new_name != old_name:
            success, msg = rename_item(self.disk_manager, self.current_user_id, self.current_cwd_inode_id, old_name, new_name)
            if success:
                QMessageBox.information(self, "成功", msg)
                self._refresh_current_views()
            else:
                QMessageBox.warning(self, "错误", msg)

    def show_properties_selected(self):
        """显示选中文件的属性"""
        indexes = self.file_list.selectedIndexes()
        if not indexes:
            QMessageBox.warning(self, "选择错误", "请先选择要查看属性的文件或目录")
            return
            
        idx = indexes[0]
        name = self.file_list.item(idx.row(), 0).text()
        # 这里可以调用属性对话框
        QMessageBox.information(self, "属性", f"文件属性：{name}")

    def copy_path_selected(self):
        """复制选中文件的路径"""
        indexes = self.file_list.selectedIndexes()
        if not indexes:
            QMessageBox.warning(self, "选择错误", "请先选择要复制路径的文件或目录")
            return
            
        paths = [self.file_list.item(idx.row(), 0).text() for idx in indexes]
        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(paths))
        QMessageBox.information(self, "复制路径", f"已复制 {len(paths)} 个路径到剪贴板")

    def show_system_monitor(self):
        """显示系统监控对话框"""
        from .system_monitor_dialog import SystemMonitorDialog
        dialog = SystemMonitorDialog(self.disk_manager, self)
        dialog.exec()


if __name__ == "__main__":
    # 测试代码
    app = QApplication(sys.argv)

    class MockDisk:
        def __init__(self):
            self.superblock = type('obj', (object,), {
                'root_inode_id': 0
            })()

        def get_inode(self, id):
            return None

        def format_disk(self):
            pass

        def save_disk_image(self):
            pass

    class MockAuth:
        def __init__(self):
            self.current_user_id = 0

        def get_current_user(self):
            return None

        def get_cwd_inode_id(self):
            return 0

        def set_cwd_inode_id(self, id):
            pass

        def create_user(self, u, p):
            pass

    def mock_list_dir(dm, id):
        return True, "success", []

    def mock_resolve(dm, cwd, root, path):
        return True, "success", 0

    # 替换导入的函数
    list_directory = mock_list_dir
    _resolve_path_to_inode_id = mock_resolve

    main_win = MainWindow(MockDisk(), MockAuth())
    main_win.show()
    sys.exit(app.exec())