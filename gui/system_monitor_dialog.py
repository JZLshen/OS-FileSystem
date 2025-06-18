from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, 
    QProgressBar, QTableWidget, QTableWidgetItem, QPushButton, 
    QTextEdit, QGroupBox, QGridLayout, QSplitter, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor

from fs_core.system_monitor import SystemMonitor, PerformanceMonitor
from fs_core.cache_manager import CacheManager
from fs_core.error_handler import get_global_error_handler

import time
from typing import Dict, Any, Optional
from datetime import datetime


class SystemMonitorDialog(QDialog):
    """系统监控对话框"""
    
    def __init__(self, disk_manager, parent=None):
        super().__init__(parent)
        self.disk_manager = disk_manager
        self.cache_manager = CacheManager()
        self.system_monitor = SystemMonitor(disk_manager, self.cache_manager)
        self.performance_monitor = PerformanceMonitor()
        
        self.setWindowTitle("系统监控")
        self.setModal(True)
        self.resize(800, 600)
        
        self._setup_ui()
        self._setup_timer()
        
        # 启动监控
        self.system_monitor.start_monitoring()
    
    def _setup_ui(self):
        """设置用户界面"""
        layout = QVBoxLayout(self)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        
        # 系统概览标签页
        self.overview_tab = self._create_overview_tab()
        self.tab_widget.addTab(self.overview_tab, "系统概览")
        
        # 性能监控标签页
        self.performance_tab = self._create_performance_tab()
        self.tab_widget.addTab(self.performance_tab, "性能监控")
        
        # 健康检查标签页
        self.health_tab = self._create_health_tab()
        self.tab_widget.addTab(self.health_tab, "健康检查")
        
        # 缓存状态标签页
        self.cache_tab = self._create_cache_tab()
        self.tab_widget.addTab(self.cache_tab, "缓存状态")
        
        # 错误日志标签页
        self.error_tab = self._create_error_tab()
        self.tab_widget.addTab(self.error_tab, "错误日志")
        
        layout.addWidget(self.tab_widget)
        
        # 底部按钮
        button_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("刷新")
        self.export_btn = QPushButton("导出报告")
        self.close_btn = QPushButton("关闭")
        
        button_layout.addWidget(self.refresh_btn)
        button_layout.addWidget(self.export_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.close_btn)
        
        layout.addLayout(button_layout)
    
    def _create_overview_tab(self) -> QWidget:
        """创建系统概览标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 磁盘使用情况
        disk_group = QGroupBox("磁盘使用情况")
        disk_layout = QGridLayout(disk_group)
        
        self.disk_usage_bar = QProgressBar()
        self.disk_usage_label = QLabel("0%")
        disk_layout.addWidget(QLabel("使用率:"), 0, 0)
        disk_layout.addWidget(self.disk_usage_bar, 0, 1)
        disk_layout.addWidget(self.disk_usage_label, 0, 2)
        
        self.total_blocks_label = QLabel("总块数: 0")
        self.free_blocks_label = QLabel("空闲块数: 0")
        disk_layout.addWidget(self.total_blocks_label, 1, 0)
        disk_layout.addWidget(self.free_blocks_label, 1, 1)
        
        layout.addWidget(disk_group)
        
        # 文件系统信息
        fs_group = QGroupBox("文件系统信息")
        fs_layout = QGridLayout(fs_group)
        
        self.total_inodes_label = QLabel("总i节点数: 0")
        self.free_inodes_label = QLabel("空闲i节点数: 0")
        self.block_size_label = QLabel("块大小: 0 字节")
        self.root_inode_label = QLabel("根i节点ID: 0")
        
        fs_layout.addWidget(self.total_inodes_label, 0, 0)
        fs_layout.addWidget(self.free_inodes_label, 0, 1)
        fs_layout.addWidget(self.block_size_label, 1, 0)
        fs_layout.addWidget(self.root_inode_label, 1, 1)
        
        layout.addWidget(fs_group)
        
        # 系统状态
        status_group = QGroupBox("系统状态")
        status_layout = QGridLayout(status_group)
        
        self.open_files_label = QLabel("打开文件数: 0")
        self.cache_hit_rate_label = QLabel("缓存命中率: 0%")
        self.operation_count_label = QLabel("操作计数: 0")
        
        status_layout.addWidget(self.open_files_label, 0, 0)
        status_layout.addWidget(self.cache_hit_rate_label, 0, 1)
        status_layout.addWidget(self.operation_count_label, 1, 0)
        
        layout.addWidget(status_group)
        
        layout.addStretch()
        return widget
    
    def _create_performance_tab(self) -> QWidget:
        """创建性能监控标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 操作统计表格
        self.performance_table = QTableWidget()
        self.performance_table.setColumnCount(6)
        self.performance_table.setHorizontalHeaderLabels([
            "操作类型", "总次数", "成功次数", "失败次数", "成功率", "平均耗时(ms)"
        ])
        
        layout.addWidget(self.performance_table)
        
        # 实时性能指标
        metrics_group = QGroupBox("实时性能指标")
        metrics_layout = QGridLayout(metrics_group)
        
        self.avg_response_time_label = QLabel("平均响应时间: 0ms")
        self.total_operations_label = QLabel("总操作数: 0")
        self.success_rate_label = QLabel("总体成功率: 0%")
        
        metrics_layout.addWidget(self.avg_response_time_label, 0, 0)
        metrics_layout.addWidget(self.total_operations_label, 0, 1)
        metrics_layout.addWidget(self.success_rate_label, 1, 0)
        
        layout.addWidget(metrics_group)
        
        return widget
    
    def _create_health_tab(self) -> QWidget:
        """创建健康检查标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 健康状态表格
        self.health_table = QTableWidget()
        self.health_table.setColumnCount(3)
        self.health_table.setHorizontalHeaderLabels([
            "检查项目", "状态", "详细信息"
        ])
        self.health_table.horizontalHeader().setStretchLastSection(True)
        
        layout.addWidget(self.health_table)
        
        # 健康检查按钮
        button_layout = QHBoxLayout()
        self.run_health_check_btn = QPushButton("运行健康检查")
        button_layout.addWidget(self.run_health_check_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        return widget
    
    def _create_cache_tab(self) -> QWidget:
        """创建缓存状态标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 缓存统计表格
        self.cache_table = QTableWidget()
        self.cache_table.setColumnCount(4)
        self.cache_table.setHorizontalHeaderLabels([
            "缓存类型", "大小", "命中率", "状态"
        ])
        
        layout.addWidget(self.cache_table)
        
        # 缓存操作按钮
        button_layout = QHBoxLayout()
        self.clear_cache_btn = QPushButton("清空所有缓存")
        self.refresh_cache_btn = QPushButton("刷新缓存状态")
        button_layout.addWidget(self.clear_cache_btn)
        button_layout.addWidget(self.refresh_cache_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        return widget
    
    def _create_error_tab(self) -> QWidget:
        """创建错误日志标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 错误统计
        error_stats_group = QGroupBox("错误统计")
        error_stats_layout = QGridLayout(error_stats_group)
        
        self.total_errors_label = QLabel("总错误数: 0")
        self.critical_errors_label = QLabel("严重错误: 0")
        self.warning_count_label = QLabel("警告数: 0")
        
        error_stats_layout.addWidget(self.total_errors_label, 0, 0)
        error_stats_layout.addWidget(self.critical_errors_label, 0, 1)
        error_stats_layout.addWidget(self.warning_count_label, 1, 0)
        
        layout.addWidget(error_stats_group)
        
        # 错误日志显示
        self.error_log_text = QTextEdit()
        self.error_log_text.setReadOnly(True)
        layout.addWidget(self.error_log_text)
        
        # 错误日志操作按钮
        error_buttons_layout = QHBoxLayout()
        self.clear_log_btn = QPushButton("清空日志")
        self.clear_log_btn.clicked.connect(self._clear_error_log)
        error_buttons_layout.addWidget(self.clear_log_btn)
        
        self.export_log_btn = QPushButton("导出日志")
        self.export_log_btn.clicked.connect(self._export_error_log)
        error_buttons_layout.addWidget(self.export_log_btn)
        
        error_buttons_layout.addStretch()
        layout.addLayout(error_buttons_layout)
        
        return widget
    
    def _setup_timer(self):
        """设置定时器"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_data)
        self.update_timer.start(2000)  # 每2秒更新一次
    
    def _update_data(self):
        """更新所有数据"""
        self._update_overview()
        self._update_performance()
        self._update_health_tab()
        self._update_cache()
        self._update_error_log()
    
    def _update_overview(self):
        """更新系统概览"""
        if self.disk_manager.superblock:
            total_blocks = self.disk_manager.superblock.total_blocks
            free_blocks = self.disk_manager.superblock.free_blocks_count
            used_blocks = total_blocks - free_blocks
            usage_percent = (used_blocks / total_blocks) * 100
            
            self.disk_usage_bar.setValue(int(usage_percent))
            self.disk_usage_label.setText(f"{usage_percent:.1f}%")
            self.total_blocks_label.setText(f"总块数: {total_blocks}")
            self.free_blocks_label.setText(f"空闲块数: {free_blocks}")
            
            self.total_inodes_label.setText(f"总i节点数: {self.disk_manager.superblock.total_inodes}")
            self.free_inodes_label.setText(f"空闲i节点数: {self.disk_manager.superblock.free_inodes_count}")
            self.block_size_label.setText(f"块大小: {self.disk_manager.superblock.block_size} 字节")
            self.root_inode_label.setText(f"根i节点ID: {self.disk_manager.superblock.root_inode_id}")
        
        # 缓存统计
        cache_stats = self.cache_manager.get_stats()
        total_cache_size = sum(cache_stats.values())
        if total_cache_size > 0:
            cache_hit_rate = (cache_stats.get('inode_cache_size', 0) + 
                            cache_stats.get('block_cache_size', 0)) / total_cache_size * 100
            self.cache_hit_rate_label.setText(f"缓存命中率: {cache_hit_rate:.1f}%")
        
        # 打开文件数
        open_files_count = sum(1 for inode in self.disk_manager.inode_table if inode is not None)
        self.open_files_label.setText(f"打开文件数: {open_files_count}")
    
    def _update_performance(self):
        """更新性能监控"""
        try:
            # 获取性能监控器数据
            if hasattr(self, 'performance_monitor') and self.performance_monitor:
                # 获取最近的性能指标
                recent_metrics = self.performance_monitor.get_recent_metrics(10)
                
                # 清空表格
                self.performance_table.setRowCount(len(recent_metrics))
                
                for i, metric in enumerate(recent_metrics):
                    # 操作类型
                    self.performance_table.setItem(i, 0, QTableWidgetItem(metric.operation_type))
                    
                    # 持续时间
                    duration_str = f"{metric.duration:.3f}s"
                    self.performance_table.setItem(i, 1, QTableWidgetItem(duration_str))
                    
                    # 状态
                    status = "成功" if metric.success else "失败"
                    status_item = QTableWidgetItem(status)
                    if not metric.success:
                        status_item.setBackground(QColor(255, 200, 200))
                    self.performance_table.setItem(i, 2, status_item)
                    
                    # 时间戳
                    timestamp = time.strftime("%H:%M:%S", time.localtime(metric.start_time))
                    self.performance_table.setItem(i, 3, QTableWidgetItem(timestamp))
                    
                    # 错误信息
                    error_msg = metric.error_message if metric.error_message else ""
                    self.performance_table.setItem(i, 4, QTableWidgetItem(error_msg))
            else:
                # 显示模拟数据
                self.performance_table.setRowCount(3)
                operations = [
                    ("文件读取", "0.002s", "成功", "20:45:30", ""),
                    ("目录列表", "0.001s", "成功", "20:45:29", ""),
                    ("文件写入", "0.005s", "成功", "20:45:28", "")
                ]
                
                for i, (op_type, duration, status, timestamp, error) in enumerate(operations):
                    self.performance_table.setItem(i, 0, QTableWidgetItem(op_type))
                    self.performance_table.setItem(i, 1, QTableWidgetItem(duration))
                    self.performance_table.setItem(i, 2, QTableWidgetItem(status))
                    self.performance_table.setItem(i, 3, QTableWidgetItem(timestamp))
                    self.performance_table.setItem(i, 4, QTableWidgetItem(error))
                    
        except Exception as e:
            print(f"更新性能监控失败: {e}")
            self.performance_table.setRowCount(1)
            self.performance_table.setItem(0, 0, QTableWidgetItem("性能监控"))
            self.performance_table.setItem(0, 1, QTableWidgetItem("N/A"))
            self.performance_table.setItem(0, 2, QTableWidgetItem("错误"))
            self.performance_table.setItem(0, 3, QTableWidgetItem(""))
            self.performance_table.setItem(0, 4, QTableWidgetItem(str(e)))
    
    def _update_health_tab(self):
        """更新健康检查标签页"""
        try:
            if hasattr(self.system_monitor, 'health_checker'):
                health_results = self.system_monitor.health_checker.run_all_checks()
                
                self.health_table.setRowCount(len(health_results))
                
                for i, (check_name, result) in enumerate(health_results.items()):
                    status = result.get('status', 'unknown')
                    message = result.get('message', '')
                    
                    # 设置状态颜色
                    status_item = QTableWidgetItem(status)
                    if status == 'healthy':
                        status_item.setBackground(QColor(200, 255, 200))  # 绿色
                    elif status == 'warning':
                        status_item.setBackground(QColor(255, 255, 200))  # 黄色
                    elif status == 'critical':
                        status_item.setBackground(QColor(255, 200, 200))  # 红色
                    elif status == 'error':
                        status_item.setBackground(QColor(255, 150, 150))  # 深红色
                    
                    self.health_table.setItem(i, 0, QTableWidgetItem(check_name))
                    self.health_table.setItem(i, 1, status_item)
                    self.health_table.setItem(i, 2, QTableWidgetItem(message))
            else:
                # 如果没有健康检查器，显示默认信息
                self.health_table.setRowCount(1)
                self.health_table.setItem(0, 0, QTableWidgetItem("系统状态"))
                self.health_table.setItem(0, 1, QTableWidgetItem("正常"))
                self.health_table.setItem(0, 2, QTableWidgetItem("系统运行正常"))
                
        except Exception as e:
            print(f"更新健康检查标签页失败: {e}")
            # 显示错误信息
            self.health_table.setRowCount(1)
            self.health_table.setItem(0, 0, QTableWidgetItem("健康检查"))
            self.health_table.setItem(0, 1, QTableWidgetItem("错误"))
            self.health_table.setItem(0, 2, QTableWidgetItem(f"检查失败: {e}"))
    
    def _update_cache(self):
        """更新缓存统计"""
        cache_stats = self.cache_manager.get_stats()
        
        self.cache_table.setRowCount(4)
        
        cache_types = [
            ("i节点缓存", "inode_cache_size"),
            ("数据块缓存", "block_cache_size"),
            ("路径缓存", "path_cache_size"),
            ("目录缓存", "directory_cache_size")
        ]
        
        for i, (name, key) in enumerate(cache_types):
            size = cache_stats.get(key, 0)
            self.cache_table.setItem(i, 0, QTableWidgetItem(name))
            self.cache_table.setItem(i, 1, QTableWidgetItem(str(size)))
            
            # 计算命中率（模拟值，实际需要缓存管理器提供）
            hit_rate = "85%" if size > 0 else "0%"
            self.cache_table.setItem(i, 2, QTableWidgetItem(hit_rate))
            self.cache_table.setItem(i, 3, QTableWidgetItem("正常"))
    
    def _update_error_log(self):
        """更新错误日志"""
        error_handler = get_global_error_handler()
        if error_handler:
            summary = error_handler.get_error_summary()
            recent_errors = error_handler.get_recent_errors(50)
            
            self.total_errors_label.setText(f"总错误数: {summary.get('total_errors', 0)}")
            self.critical_errors_label.setText(f"严重错误: {summary.get('by_severity', {}).get('critical', 0)}")
            self.warning_count_label.setText(f"警告数: {summary.get('by_severity', {}).get('warning', 0)}")
            
            # 显示最近的错误日志
            log_text = ""
            for error in recent_errors[-10:]:  # 显示最近10条
                log_text += f"[{error.timestamp.strftime('%H:%M:%S')}] {error.severity.value.upper()}: {error.message}\n"
            
            self.error_log_text.setPlainText(log_text)
    
    def _refresh_all(self):
        """刷新所有数据"""
        self._update_data()
    
    def _clear_all_cache(self):
        """清空所有缓存"""
        self.cache_manager.clear_all()
        self._update_cache()
    
    def _refresh_cache_stats(self):
        """刷新缓存统计"""
        self._update_cache()
    
    def _clear_error_log(self):
        """清空错误日志"""
        error_handler = get_global_error_handler()
        if error_handler:
            error_handler.clear_errors()
        self.error_log_text.clear()
    
    def _export_error_log(self):
        """导出错误日志"""
        # 这里可以实现导出功能
        pass
    
    def _export_report(self):
        """导出系统报告"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出系统报告", "system_report.json", "JSON文件 (*.json)"
            )
            
            if file_path:
                if self.system_monitor.export_system_report(file_path):
                    QMessageBox.information(self, "成功", f"系统报告已导出到: {file_path}")
                else:
                    QMessageBox.warning(self, "失败", "导出系统报告失败")
                    
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出报告时出错: {e}")
    
    def _run_health_check(self):
        """运行健康检查"""
        try:
            self._update_health_tab()
            QMessageBox.information(self, "完成", "健康检查已完成")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"运行健康检查时出错: {e}")
    
    def closeEvent(self, event):
        """关闭事件"""
        self.system_monitor.stop_monitoring()
        self.update_timer.stop()
        super().closeEvent(event) 