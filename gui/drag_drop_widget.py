from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QProgressBar, QMessageBox,
    QDialog, QDialogButtonBox, QTextEdit, QComboBox, QSpinBox,
    QGroupBox, QCheckBox, QFileDialog
)
from PyQt6.QtCore import Qt, QMimeData, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap

import os
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass


@dataclass
class DragDropItem:
    """拖拽项目数据类"""
    name: str
    path: str
    item_type: str  # file, directory, symlink
    size: int = 0
    source_path: str = ""


class DragDropListWidget(QListWidget):
    """支持拖拽的列表控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        
    def dragEnterEvent(self, event: QDragEnterEvent):
        """处理拖拽进入事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)
    
    def dropEvent(self, event: QDropEvent):
        """处理拖拽放下事件"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    self.add_file_item(file_path)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
    
    def add_file_item(self, file_path: str):
        """添加文件项目"""
        if os.path.exists(file_path):
            item = QListWidgetItem()
            item.setText(os.path.basename(file_path))
            item.setData(Qt.ItemDataRole.UserRole, file_path)
            
            # 设置图标
            if os.path.isdir(file_path):
                item.setIcon(self.style().standardIcon(
                    self.style().StandardPixmap.SP_DirIcon
                ))
            else:
                item.setIcon(self.style().standardIcon(
                    self.style().StandardPixmap.SP_FileIcon
                ))
            
            self.addItem(item)
    
    def get_selected_items(self) -> List[DragDropItem]:
        """获取选中的项目"""
        items = []
        for item in self.selectedItems():
            file_path = item.data(Qt.ItemDataRole.UserRole)
            if file_path and os.path.exists(file_path):
                drag_item = DragDropItem(
                    name=os.path.basename(file_path),
                    path=file_path,
                    item_type="directory" if os.path.isdir(file_path) else "file",
                    size=os.path.getsize(file_path) if os.path.isfile(file_path) else 0
                )
                items.append(drag_item)
        return items


class BatchOperationDialog(QDialog):
    """批量操作对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量操作")
        self.setModal(True)
        self.resize(600, 500)
        
        self.source_items: List[DragDropItem] = []
        self.target_directory = ""
        self.operation_type = "copy"
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        """设置用户界面"""
        layout = QVBoxLayout(self)
        
        # 源文件区域
        source_group = QGroupBox("源文件/目录")
        source_layout = QVBoxLayout(source_group)
        
        self.source_list = DragDropListWidget()
        source_layout.addWidget(self.source_list)
        
        source_buttons_layout = QHBoxLayout()
        self.add_files_btn = QPushButton("添加文件")
        self.add_dirs_btn = QPushButton("添加目录")
        self.clear_source_btn = QPushButton("清空")
        
        source_buttons_layout.addWidget(self.add_files_btn)
        source_buttons_layout.addWidget(self.add_dirs_btn)
        source_buttons_layout.addWidget(self.clear_source_btn)
        source_buttons_layout.addStretch()
        
        source_layout.addLayout(source_buttons_layout)
        layout.addWidget(source_group)
        
        # 操作类型选择
        operation_group = QGroupBox("操作类型")
        operation_layout = QHBoxLayout(operation_group)
        
        self.operation_combo = QComboBox()
        self.operation_combo.addItems(["复制", "移动", "创建符号链接"])
        operation_layout.addWidget(QLabel("操作:"))
        operation_layout.addWidget(self.operation_combo)
        operation_layout.addStretch()
        
        layout.addWidget(operation_group)
        
        # 目标目录
        target_group = QGroupBox("目标目录")
        target_layout = QHBoxLayout(target_group)
        
        self.target_edit = QTextEdit()
        self.target_edit.setMaximumHeight(60)
        self.target_edit.setPlaceholderText("拖拽目录到这里或手动输入路径")
        
        self.browse_target_btn = QPushButton("浏览...")
        
        target_layout.addWidget(self.target_edit)
        target_layout.addWidget(self.browse_target_btn)
        
        layout.addWidget(target_group)
        
        # 选项
        options_group = QGroupBox("选项")
        options_layout = QVBoxLayout(options_group)
        
        self.overwrite_check = QCheckBox("覆盖已存在的文件")
        self.overwrite_check.setChecked(True)
        
        self.preserve_attributes_check = QCheckBox("保留文件属性")
        self.preserve_attributes_check.setChecked(True)
        
        options_layout.addWidget(self.overwrite_check)
        options_layout.addWidget(self.preserve_attributes_check)
        
        layout.addWidget(options_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        layout.addWidget(button_box)
        
        self.button_box = button_box
    
    def _connect_signals(self):
        """连接信号"""
        self.add_files_btn.clicked.connect(self._add_files)
        self.add_dirs_btn.clicked.connect(self._add_directories)
        self.clear_source_btn.clicked.connect(self.source_list.clear)
        self.browse_target_btn.clicked.connect(self._browse_target)
        
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        
        # 操作类型改变时更新按钮状态
        self.operation_combo.currentTextChanged.connect(self._on_operation_changed)
    
    def _add_files(self):
        """添加文件"""
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "", "所有文件 (*.*)"
        )
        for file_path in files:
            self.source_list.add_file_item(file_path)
    
    def _add_directories(self):
        """添加目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择目录")
        if directory:
            self.source_list.add_file_item(directory)
    
    def _browse_target(self):
        """浏览目标目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择目标目录")
        if directory:
            self.target_edit.setText(directory)
    
    def _on_operation_changed(self, operation: str):
        """操作类型改变时的处理"""
        if operation == "创建符号链接":
            self.preserve_attributes_check.setEnabled(False)
        else:
            self.preserve_attributes_check.setEnabled(True)
    
    def get_operation_config(self) -> Dict[str, Any]:
        """获取操作配置"""
        return {
            "source_items": self.source_list.get_selected_items(),
            "target_directory": self.target_edit.toPlainText().strip(),
            "operation_type": self.operation_combo.currentText(),
            "overwrite": self.overwrite_check.isChecked(),
            "preserve_attributes": self.preserve_attributes_check.isChecked()
        }
    
    def set_progress(self, value: int, maximum: int):
        """设置进度"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(maximum)
        self.progress_bar.setValue(value)
    
    def hide_progress(self):
        """隐藏进度条"""
        self.progress_bar.setVisible(False)


class BatchOperationWorker(QThread):
    """批量操作工作线程"""
    
    progress_updated = pyqtSignal(int, int)
    operation_completed = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, operation_config: Dict[str, Any], operation_callback: Callable):
        super().__init__()
        self.operation_config = operation_config
        self.operation_callback = operation_callback
        self.is_cancelled = False
    
    def run(self):
        """执行批量操作"""
        try:
            source_items = self.operation_config["source_items"]
            target_directory = self.operation_config["target_directory"]
            operation_type = self.operation_config["operation_type"]
            
            total_items = len(source_items)
            completed_items = 0
            
            for item in source_items:
                if self.is_cancelled:
                    break
                
                try:
                    # 调用操作回调函数
                    result = self.operation_callback(item, target_directory, operation_type)
                    if result:
                        completed_items += 1
                    
                    self.progress_updated.emit(completed_items, total_items)
                    
                except Exception as e:
                    self.error_occurred.emit(f"处理 {item.name} 时出错: {str(e)}")
            
            # 发送完成信号
            self.operation_completed.emit({
                "total": total_items,
                "completed": completed_items,
                "cancelled": self.is_cancelled
            })
            
        except Exception as e:
            self.error_occurred.emit(f"批量操作失败: {str(e)}")
    
    def cancel(self):
        """取消操作"""
        self.is_cancelled = True


class DragDropWidget(QWidget):
    """主拖拽控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.operation_callback: Optional[Callable] = None
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        """设置用户界面"""
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel("拖拽文件或目录到这里进行批量操作")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                color: #666;
                padding: 20px;
                border: 2px dashed #ccc;
                border-radius: 10px;
                background-color: #f9f9f9;
            }
        """)
        layout.addWidget(title_label)
        
        # 批量操作按钮
        self.batch_operation_btn = QPushButton("批量操作")
        self.batch_operation_btn.setEnabled(False)
        layout.addWidget(self.batch_operation_btn)
        
        # 拖拽提示
        hint_label = QLabel("支持的文件操作：\n• 复制文件/目录\n• 移动文件/目录\n• 创建符号链接\n• 批量重命名")
        hint_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        hint_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(hint_label)
        
        layout.addStretch()
    
    def _connect_signals(self):
        """连接信号"""
        self.batch_operation_btn.clicked.connect(self._show_batch_operation_dialog)
    
    def dragEnterEvent(self, event: QDragEnterEvent):
        """处理拖拽进入事件"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("background-color: #e8f4fd; border: 2px solid #0078d4;")
    
    def dragLeaveEvent(self, event):
        """处理拖拽离开事件"""
        self.setStyleSheet("")
    
    def dropEvent(self, event: QDropEvent):
        """处理拖拽放下事件"""
        self.setStyleSheet("")
        
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            file_paths = []
            
            for url in urls:
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if os.path.exists(file_path):
                        file_paths.append(file_path)
            
            if file_paths:
                self._show_batch_operation_dialog(file_paths)
        
        event.acceptProposedAction()
    
    def _show_batch_operation_dialog(self, file_paths: List[str] = None):
        """显示批量操作对话框"""
        dialog = BatchOperationDialog(self)
        
        if file_paths:
            for file_path in file_paths:
                dialog.source_list.add_file_item(file_path)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.get_operation_config()
            if config["source_items"] and config["target_directory"]:
                self._execute_batch_operation(config, dialog)
    
    def _execute_batch_operation(self, config: Dict[str, Any], dialog: BatchOperationDialog):
        """执行批量操作"""
        if not self.operation_callback:
            QMessageBox.warning(self, "错误", "未设置操作回调函数")
            return
        
        # 创建工作线程
        worker = BatchOperationWorker(config, self.operation_callback)
        worker.progress_updated.connect(dialog.set_progress)
        worker.operation_completed.connect(self._on_operation_completed)
        worker.error_occurred.connect(self._on_operation_error)
        
        # 启动线程
        worker.start()
        
        # 等待完成
        worker.wait()
        
        dialog.hide_progress()
    
    def _on_operation_completed(self, result: Dict[str, Any]):
        """操作完成处理"""
        message = f"批量操作完成\n总计: {result['total']} 项\n成功: {result['completed']} 项"
        if result['cancelled']:
            message += "\n操作已取消"
        
        QMessageBox.information(self, "完成", message)
    
    def _on_operation_error(self, error_message: str):
        """操作错误处理"""
        QMessageBox.critical(self, "错误", error_message)
    
    def set_operation_callback(self, callback: Callable):
        """设置操作回调函数"""
        self.operation_callback = callback
        self.batch_operation_btn.setEnabled(True) 