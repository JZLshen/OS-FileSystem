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
)
from PyQt6.QtGui import QAction, QStandardItemModel, QStandardItem, QIcon, QKeySequence
from PyQt6.QtCore import Qt, QModelIndex, QPoint, QItemSelectionModel

from fs_core.disk_manager import DiskManager
from user_management.user_auth import UserAuth
from fs_core.dir_ops import (
    list_directory,
    make_directory,
    remove_directory,
    rename_item,
    _resolve_path_to_inode_id,
)
from fs_core.file_ops import create_file, delete_file, create_symbolic_link, create_hard_link, encrypt_file, compress_file
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
        
        # 创建工具栏
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        
        # 添加地址栏
        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("输入路径...")
        self.address_bar.returnPressed.connect(self.navigate_to_path)
        toolbar.addWidget(QLabel("地址:"))
        toolbar.addWidget(self.address_bar)
        
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
        self.file_list_view = QTableView()
        self.file_list_model = QStandardItemModel()
        self.file_list_view.setModel(self.file_list_model)
        self.file_list_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_list_view.doubleClicked.connect(self.on_file_double_clicked)
        
        # 设置文件列表的列标题
        self.file_list_model.setHorizontalHeaderLabels(["名称", "类型", "大小", "权限", "所有者", "修改时间"])        
        # 设置列宽
        header = self.file_list_view.horizontalHeader()
        header.setStretchLastSection(True)
        
        # 添加到布局
        layout.addWidget(self.dir_tree_view, 1)
        layout.addWidget(self.file_list_view, 2)
        
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
    
    def go_forward(self):
        """前进"""
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            path, inode_id = self.history[self.history_index]
            self.navigate_to_directory(path, inode_id, update_history=False)
    
    def go_up(self):
        """上级目录"""
        if self.current_cwd_inode_id != self.disk_manager.superblock.root_inode_id:
            # 获取当前目录的父目录
            current_inode = self.disk_manager.get_inode(self.current_cwd_inode_id)
            if current_inode and hasattr(current_inode, 'parent_inode_id') and current_inode.parent_inode_id is not None:
                self.current_cwd_inode_id = current_inode.parent_inode_id
                self.user_auth.set_cwd_inode_id(current_inode.parent_inode_id)
                self._refresh_current_views()

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
        selected_items = self.file_list_view.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "选择错误", "请先选择要创建硬链接的文件")
            return

        # 获取选中的行
        row = selected_items[0].row()
        file_name = self.file_list_model.item(row, 0).text()
        
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
        selected_items = self.file_list_view.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "选择错误", "请先选择要加密的文件")
            return
        
        # 获取选中的行
        row = selected_items[0].row()
        file_name = self.file_list_model.item(row, 0).text()
        
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
        selected_items = self.file_list_view.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "选择错误", "请先选择要压缩的文件")
            return
        
        # 获取选中的行
        row = selected_items[0].row()
        file_name = self.file_list_model.item(row, 0).text()
        
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
        selected_items = self.file_list_view.selectedIndexes()
        if not selected_items:
            QMessageBox.warning(self, "选择错误", "请先选择要删除的文件或目录")
            return

        # 获取选中的行
        row = selected_items[0].row()
        item_name = self.file_list_model.item(row, 0).text()
        
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
    
    def on_file_double_clicked(self, index):
        """文件列表双击事件"""
        row = index.row()
        item_name = self.file_list_model.item(row, 0).text()
        item_type = self.file_list_model.item(row, 1).text()
        
        if item_type == "目录":
            # 导航到目录
            success, msg, entries = list_directory(self.disk_manager, self.current_cwd_inode_id)
            if not success:
                QMessageBox.warning(self, "错误", f"无法读取目录内容：{msg}")
                return

            target_inode_id = None
            for entry in entries:
                if entry.get("name") == item_name:
                    target_inode_id = entry.get("inode_id")
                    break
            
            if target_inode_id is not None:
                self.current_cwd_inode_id = target_inode_id
                self.user_auth.set_cwd_inode_id(target_inode_id)
                self._refresh_current_views()
        else:
            # 打开文件
            self.open_file(item_name)
    
    def open_file(self, file_name: str):
        """打开文件"""
        # 这里可以实现文件编辑器
        QMessageBox.information(self, "文件", f"打开文件：{file_name}")
    
    def _populate_tree_view(self):
        """填充树状视图"""
        self.dir_tree_model.clear()
        
        # 添加根目录
        root_inode_id = self.disk_manager.superblock.root_inode_id
        root_item = QStandardItem("/")
        root_item.setData(root_inode_id, INODE_ID_ROLE)
        root_item.setData(True, IS_DIR_ROLE)
        root_item.setData(False, CHILDREN_LOADED_ROLE)
        self.dir_tree_model.appendRow(root_item)
        
        # 展开根目录
        self.dir_tree_view.expand(root_item.index())
    
    def _populate_children_in_tree(self, parent_item: QStandardItem, parent_inode_id: int):
        """递归填充树状视图的子项"""
        if parent_item.data(CHILDREN_LOADED_ROLE):
            return

        success, msg, entries = list_directory(self.disk_manager, parent_inode_id)
        if not success:
            return
        
        # 清空现有子项
        parent_item.removeRows(0, parent_item.rowCount())
        
        # 添加子目录
        for entry in entries:
            if entry.get("type") == FileType.DIRECTORY:
                child_item = QStandardItem(entry.get("name"))
                child_item.setData(entry.get("inode_id"), INODE_ID_ROLE)
                child_item.setData(True, IS_DIR_ROLE)
                child_item.setData(False, CHILDREN_LOADED_ROLE)
                parent_item.appendRow(child_item)
        
        # 标记为已加载
        parent_item.setData(True, CHILDREN_LOADED_ROLE)
    
    def _populate_file_list_view(self, inode_id: int):
        """填充文件列表视图"""
        self.file_list_model.setRowCount(0)
        
        success, msg, entries = list_directory(self.disk_manager, inode_id)
        if not success:
            return
        
        for entry in entries:
            row = self.file_list_model.rowCount()
            self.file_list_model.insertRow(row)
            
            # 名称
            name_item = QStandardItem(entry.get("name"))
            self.file_list_model.setItem(row, 0, name_item)
            
            # 类型
            type_str = "目录" if entry.get("type") == FileType.DIRECTORY else "文件"
            if entry.get("is_hardlink"):
                type_str += " (硬链接)"
            if entry.get("is_encrypted"):
                type_str += " (加密)"
            if entry.get("is_compressed"):
                type_str += " (压缩)"
            self.file_list_model.setItem(row, 1, QStandardItem(type_str))
            
            # 大小
            size_str = str(entry.get("size", 0)) + " B"
            self.file_list_model.setItem(row, 2, QStandardItem(size_str))
            
            # 权限
            permissions = entry.get("permissions", 0o644)
            perm_str = oct(permissions)[2:]  # 去掉0o前缀
            self.file_list_model.setItem(row, 3, QStandardItem(perm_str))
            
            # 所有者
            owner_str = str(entry.get("owner_uid", 0))
            self.file_list_model.setItem(row, 4, QStandardItem(owner_str))
            
            # 修改时间
            mtime = entry.get("mtime", 0)
            time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            self.file_list_model.setItem(row, 5, QStandardItem(time_str))
    
    def _refresh_current_views(self):
        """刷新当前视图"""
        # 更新地址栏
        current_path_str = get_inode_path_str(self.disk_manager, self.current_cwd_inode_id)
        self.address_bar.setText(current_path_str)
        
        # 刷新文件列表
        self._populate_file_list_view(self.current_cwd_inode_id)
        
        # 刷新树状视图
        self._populate_tree_view()

    def prompt_format_disk(self):
        reply = QMessageBox.question(
            self,
            "磁盘未格式化",
            "检测到磁盘未格式化，是否现在进行格式化？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # 执行格式化
            if self.disk_manager.format_disk():
                QMessageBox.information(self, "格式化成功", "磁盘已成功格式化！")
                self._populate_tree_view()
                self._refresh_current_views()
            else:
                QMessageBox.critical(self, "格式化失败", "磁盘格式化失败，请检查磁盘空间或配置。")
        else:
            QMessageBox.warning(self, "未格式化", "磁盘未格式化，部分功能将不可用。")


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
