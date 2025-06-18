from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, 
    QProgressBar, QTableWidget, QTableWidgetItem, QPushButton, 
    QTextEdit, QGroupBox, QGridLayout, QSplitter, QHeaderView,
    QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette

import time
from typing import Dict, Any, Optional
from datetime import datetime


class SystemMonitorDialog(QDialog):
    """系统监控对话框"""
    
    def __init__(self, fs_system, parent=None):
        super().__init__(parent)
        self.fs_system = fs_system
        self.setWindowTitle("系统监控")
        self.setModal(False)
        self.resize(800, 600)
        
        self._setup_ui()
        self._setup_timer()
        self._connect_signals()
        
        # 初始更新
        self._update_all_tabs()
    
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
        
        # 基本信息组
        basic_group = QGroupBox("基本信息")
        basic_layout = QGridLayout(basic_group)
        
        self.disk_status_label = QLabel("磁盘状态: 未知")
        self.user_count_label = QLabel("用户数量: 0")
        self.uptime_label = QLabel("运行时间: 0秒")
        self.last_update_label = QLabel("最后更新: 从未")
        
        basic_layout.addWidget(QLabel("磁盘状态:"), 0, 0)
        basic_layout.addWidget(self.disk_status_label, 0, 1)
        basic_layout.addWidget(QLabel("用户数量:"), 1, 0)
        basic_layout.addWidget(self.user_count_label, 1, 1)
        basic_layout.addWidget(QLabel("运行时间:"), 2, 0)
        basic_layout.addWidget(self.uptime_label, 2, 1)
        basic_layout.addWidget(QLabel("最后更新:"), 3, 0)
        basic_layout.addWidget(self.last_update_label, 3, 1)
        
        layout.addWidget(basic_group)
        
        # 系统指标组
        metrics_group = QGroupBox("系统指标")
        metrics_layout = QGridLayout(metrics_group)
        
        self.cpu_progress = QProgressBar()
        self.memory_progress = QProgressBar()
        self.disk_progress = QProgressBar()
        self.cache_progress = QProgressBar()
        
        metrics_layout.addWidget(QLabel("CPU使用率:"), 0, 0)
        metrics_layout.addWidget(self.cpu_progress, 0, 1)
        metrics_layout.addWidget(QLabel("内存使用率:"), 1, 0)
        metrics_layout.addWidget(self.memory_progress, 1, 1)
        metrics_layout.addWidget(QLabel("磁盘使用率:"), 2, 0)
        metrics_layout.addWidget(self.disk_progress, 2, 1)
        metrics_layout.addWidget(QLabel("缓存命中率:"), 3, 0)
        metrics_layout.addWidget(self.cache_progress, 3, 1)
        
        layout.addWidget(metrics_group)
        layout.addStretch()
        
        return widget
    
    def _create_performance_tab(self) -> QWidget:
        """创建性能监控标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 操作统计组
        stats_group = QGroupBox("操作统计")
        stats_layout = QGridLayout(stats_group)
        
        self.total_ops_label = QLabel("总操作数: 0")
        self.success_ops_label = QLabel("成功操作: 0")
        self.failed_ops_label = QLabel("失败操作: 0")
        self.success_rate_label = QLabel("成功率: 0%")
        self.avg_duration_label = QLabel("平均耗时: 0ms")
        
        stats_layout.addWidget(self.total_ops_label, 0, 0)
        stats_layout.addWidget(self.success_ops_label, 0, 1)
        stats_layout.addWidget(self.failed_ops_label, 1, 0)
        stats_layout.addWidget(self.success_rate_label, 1, 1)
        stats_layout.addWidget(self.avg_duration_label, 2, 0)
        
        layout.addWidget(stats_group)
        
        # 操作类型统计表格
        self.operation_table = QTableWidget()
        self.operation_table.setColumnCount(5)
        self.operation_table.setHorizontalHeaderLabels([
            "操作类型", "总次数", "成功次数", "失败次数", "平均耗时(ms)"
        ])
        self.operation_table.horizontalHeader().setStretchLastSection(True)
        
        layout.addWidget(QLabel("操作类型统计:"))
        layout.addWidget(self.operation_table)
        
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
        self.cache_table.setColumnCount(3)
        self.cache_table.setHorizontalHeaderLabels([
            "缓存类型", "当前大小", "最大大小"
        ])
        self.cache_table.horizontalHeader().setStretchLastSection(True)
        
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
        
        # 错误摘要
        summary_group = QGroupBox("错误摘要")
        summary_layout = QGridLayout(summary_group)
        
        self.total_errors_label = QLabel("总错误数: 0")
        self.critical_errors_label = QLabel("严重错误: 0")
        self.error_errors_label = QLabel("一般错误: 0")
        self.warning_errors_label = QLabel("警告: 0")
        
        summary_layout.addWidget(self.total_errors_label, 0, 0)
        summary_layout.addWidget(self.critical_errors_label, 0, 1)
        summary_layout.addWidget(self.error_errors_label, 1, 0)
        summary_layout.addWidget(self.warning_errors_label, 1, 1)
        
        layout.addWidget(summary_group)
        
        # 错误日志文本区域
        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        self.error_text.setMaximumHeight(300)
        
        layout.addWidget(QLabel("最近错误日志:"))
        layout.addWidget(self.error_text)
        
        # 错误操作按钮
        button_layout = QHBoxLayout()
        self.clear_errors_btn = QPushButton("清空错误记录")
        self.export_errors_btn = QPushButton("导出错误日志")
        button_layout.addWidget(self.clear_errors_btn)
        button_layout.addWidget(self.export_errors_btn)
        button_layout.addStretch()
        
        layout.addLayout(button_layout)
        
        return widget
    
    def _setup_timer(self):
        """设置定时器"""
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_all_tabs)
        self.update_timer.start(5000)  # 每5秒更新一次
    
    def _connect_signals(self):
        """连接信号"""
        self.refresh_btn.clicked.connect(self._update_all_tabs)
        self.export_btn.clicked.connect(self._export_report)
        self.close_btn.clicked.connect(self.accept)
        
        self.run_health_check_btn.clicked.connect(self._run_health_check)
        self.clear_cache_btn.clicked.connect(self._clear_cache)
        self.refresh_cache_btn.clicked.connect(self._update_cache_tab)
        self.clear_errors_btn.clicked.connect(self._clear_errors)
        self.export_errors_btn.clicked.connect(self._export_errors)
    
    def _update_all_tabs(self):
        """更新所有标签页"""
        try:
            self._update_overview_tab()
            self._update_performance_tab()
            self._update_health_tab()
            self._update_cache_tab()
            self._update_error_tab()
            
            # 更新最后更新时间
            self.last_update_label.setText(f"最后更新: {datetime.now().strftime('%H:%M:%S')}")
            
        except Exception as e:
            print(f"更新系统监控失败: {e}")
    
    def _update_overview_tab(self):
        """更新系统概览标签页"""
        try:
            status = self.fs_system.get_system_status()
            
            # 基本信息
            self.disk_status_label.setText(f"磁盘状态: {'已格式化' if status.get('disk_formatted') else '未格式化'}")
            self.user_count_label.setText(f"用户数量: {status.get('user_count', 0)}")
            
            # 系统指标
            if status.get('system_metrics'):
                metrics = status['system_metrics']
                self.cpu_progress.setValue(int(metrics.get('cpu_percent', 0)))
                self.memory_progress.setValue(int(metrics.get('memory_percent', 0)))
                self.disk_progress.setValue(int(metrics.get('disk_usage_percent', 0)))
                self.cache_progress.setValue(int(metrics.get('cache_hit_rate', 0)))
            
        except Exception as e:
            print(f"更新概览标签页失败: {e}")
    
    def _update_performance_tab(self):
        """更新性能监控标签页"""
        try:
            stats = self.fs_system.performance_monitor.get_operation_stats()
            
            # 操作统计
            total_ops = stats.get('total_operations', 0)
            success_ops = stats.get('successful_operations', 0)
            failed_ops = stats.get('failed_operations', 0)
            success_rate = stats.get('success_rate', 0)
            avg_duration = stats.get('average_duration', 0)
            
            self.total_ops_label.setText(f"总操作数: {total_ops}")
            self.success_ops_label.setText(f"成功操作: {success_ops}")
            self.failed_ops_label.setText(f"失败操作: {failed_ops}")
            self.success_rate_label.setText(f"成功率: {success_rate:.1f}%")
            self.avg_duration_label.setText(f"平均耗时: {avg_duration*1000:.1f}ms")
            
            # 操作类型统计（这里简化处理，实际应该按类型分组）
            self.operation_table.setRowCount(1)
            self.operation_table.setItem(0, 0, QTableWidgetItem("所有操作"))
            self.operation_table.setItem(0, 1, QTableWidgetItem(str(total_ops)))
            self.operation_table.setItem(0, 2, QTableWidgetItem(str(success_ops)))
            self.operation_table.setItem(0, 3, QTableWidgetItem(str(failed_ops)))
            self.operation_table.setItem(0, 4, QTableWidgetItem(f"{avg_duration*1000:.1f}"))
            
        except Exception as e:
            print(f"更新性能标签页失败: {e}")
    
    def _update_health_tab(self):
        """更新健康检查标签页"""
        try:
            health_results = self.fs_system.health_checker.run_all_checks()
            
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
            
        except Exception as e:
            print(f"更新健康检查标签页失败: {e}")
    
    def _update_cache_tab(self):
        """更新缓存状态标签页"""
        try:
            cache_stats = self.fs_system.cache_manager.get_stats()
            
            self.cache_table.setRowCount(len(cache_stats))
            
            for i, (cache_type, size) in enumerate(cache_stats.items()):
                self.cache_table.setItem(i, 0, QTableWidgetItem(cache_type))
                self.cache_table.setItem(i, 1, QTableWidgetItem(str(size)))
                self.cache_table.setItem(i, 2, QTableWidgetItem("1000"))  # 最大大小
            
        except Exception as e:
            print(f"更新缓存标签页失败: {e}")
    
    def _update_error_tab(self):
        """更新错误日志标签页"""
        try:
            error_summary = self.fs_system.error_handler.get_error_summary()
            
            # 错误摘要
            total_errors = error_summary.get('total_errors', 0)
            by_severity = error_summary.get('by_severity', {})
            
            self.total_errors_label.setText(f"总错误数: {total_errors}")
            self.critical_errors_label.setText(f"严重错误: {by_severity.get('critical', 0)}")
            self.error_errors_label.setText(f"一般错误: {by_severity.get('error', 0)}")
            self.warning_errors_label.setText(f"警告: {by_severity.get('warning', 0)}")
            
            # 错误日志
            recent_errors = self.fs_system.error_handler.get_recent_errors(50)
            error_text = ""
            
            for error in recent_errors:
                timestamp = error.timestamp.strftime('%H:%M:%S')
                severity = error.severity.value
                message = error.message
                error_text += f"[{timestamp}] [{severity}] {message}\n"
            
            self.error_text.setPlainText(error_text)
            
        except Exception as e:
            print(f"更新错误日志标签页失败: {e}")
    
    def _export_report(self):
        """导出系统报告"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出系统报告", "system_report.json", "JSON文件 (*.json)"
            )
            
            if file_path:
                if self.fs_system.export_system_report(file_path):
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
    
    def _clear_cache(self):
        """清空缓存"""
        try:
            reply = QMessageBox.question(
                self, "确认", "确定要清空所有缓存吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.fs_system.cache_manager.clear_all()
                self._update_cache_tab()
                QMessageBox.information(self, "完成", "所有缓存已清空")
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"清空缓存时出错: {e}")
    
    def _clear_errors(self):
        """清空错误记录"""
        try:
            reply = QMessageBox.question(
                self, "确认", "确定要清空所有错误记录吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.fs_system.error_handler.clear_errors()
                self._update_error_tab()
                QMessageBox.information(self, "完成", "所有错误记录已清空")
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"清空错误记录时出错: {e}")
    
    def _export_errors(self):
        """导出错误日志"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出错误日志", "error_log.json", "JSON文件 (*.json)"
            )
            
            if file_path:
                if self.fs_system.error_handler.export_errors_to_json(file_path):
                    QMessageBox.information(self, "成功", f"错误日志已导出到: {file_path}")
                else:
                    QMessageBox.warning(self, "失败", "导出错误日志失败")
                    
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出错误日志时出错: {e}")
    
    def closeEvent(self, event):
        """关闭事件"""
        self.update_timer.stop()
        super().closeEvent(event) 