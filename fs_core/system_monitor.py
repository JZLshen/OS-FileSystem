import time
import psutil
import threading
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from collections import deque, defaultdict
import json
import os


@dataclass
class SystemMetrics:
    """系统指标数据类"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    disk_usage_percent: float
    active_connections: int
    open_files_count: int
    cache_hit_rate: float
    operation_count: int
    average_response_time: float


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    operation_type: str
    start_time: float
    end_time: float
    duration: float
    success: bool
    error_message: Optional[str] = None
    additional_data: Dict[str, Any] = field(default_factory=dict)


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics_history: deque = deque(maxlen=max_history)
        self.operation_timers: Dict[str, float] = {}
        self.lock = threading.RLock()
        
    def start_operation(self, operation_id: str) -> None:
        """开始操作计时"""
        with self.lock:
            self.operation_timers[operation_id] = time.time()
    
    def end_operation(self, operation_id: str, operation_type: str, 
                     success: bool = True, error_message: Optional[str] = None,
                     additional_data: Optional[Dict[str, Any]] = None) -> Optional[PerformanceMetrics]:
        """结束操作计时并记录指标"""
        with self.lock:
            if operation_id not in self.operation_timers:
                return None
            
            start_time = self.operation_timers.pop(operation_id)
            end_time = time.time()
            duration = end_time - start_time
            
            metrics = PerformanceMetrics(
                operation_type=operation_type,
                start_time=start_time,
                end_time=end_time,
                duration=duration,
                success=success,
                error_message=error_message,
                additional_data=additional_data or {}
            )
            
            self.metrics_history.append(metrics)
            return metrics
    
    def get_operation_stats(self, operation_type: Optional[str] = None) -> Dict[str, Any]:
        """获取操作统计信息"""
        with self.lock:
            if operation_type:
                metrics = [m for m in self.metrics_history if m.operation_type == operation_type]
            else:
                metrics = list(self.metrics_history)
            
            if not metrics:
                return {}
            
            durations = [m.duration for m in metrics]
            success_count = sum(1 for m in metrics if m.success)
            
            return {
                "total_operations": len(metrics),
                "successful_operations": success_count,
                "failed_operations": len(metrics) - success_count,
                "success_rate": success_count / len(metrics) * 100,
                "average_duration": sum(durations) / len(durations),
                "min_duration": min(durations),
                "max_duration": max(durations),
                "total_duration": sum(durations)
            }
    
    def get_recent_metrics(self, count: int = 100) -> List[PerformanceMetrics]:
        """获取最近的性能指标"""
        with self.lock:
            return list(self.metrics_history)[-count:]
    
    def clear_history(self) -> None:
        """清空历史记录"""
        with self.lock:
            self.metrics_history.clear()
            self.operation_timers.clear()


class SystemMonitor:
    """系统监控器"""
    
    def __init__(self, disk_manager, cache_manager=None, update_interval: float = 1.0):
        self.disk_manager = disk_manager
        self.cache_manager = cache_manager
        self.update_interval = update_interval
        self.metrics_history: deque = deque(maxlen=1000)
        self.is_monitoring = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.lock = threading.RLock()
        self.callbacks: List[Callable[[SystemMetrics], None]] = []
        
        # 添加健康检查器
        self.health_checker = HealthChecker(disk_manager, cache_manager)
        
    def start_monitoring(self) -> None:
        """开始监控"""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self) -> None:
        """停止监控"""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
    
    def _monitor_loop(self) -> None:
        """监控循环"""
        while self.is_monitoring:
            try:
                metrics = self._collect_metrics()
                self._store_metrics(metrics)
                self._notify_callbacks(metrics)
                time.sleep(self.update_interval)
            except Exception as e:
                print(f"系统监控错误: {e}")
    
    def _collect_metrics(self) -> SystemMetrics:
        """收集系统指标"""
        # CPU使用率（模拟）
        cpu_percent = 0.0
        
        # 内存使用率（模拟）
        memory_percent = 0.0
        
        # 磁盘使用率
        disk_usage_percent = 0
        if hasattr(self.disk_manager, 'superblock') and self.disk_manager.superblock:
            total_blocks = self.disk_manager.superblock.total_blocks
            free_blocks = self.disk_manager.superblock.free_blocks_count
            disk_usage_percent = ((total_blocks - free_blocks) / total_blocks) * 100
        
        # 活跃连接数（模拟）
        active_connections = 0
        
        # 打开文件数（模拟）
        open_files_count = 0
        if hasattr(self.disk_manager, 'inode_table'):
            open_files_count = sum(1 for inode in self.disk_manager.inode_table if inode is not None)
        
        # 缓存命中率
        cache_hit_rate = 0
        if self.cache_manager:
            stats = self.cache_manager.get_stats()
            total_requests = sum(stats.values())
            if total_requests > 0:
                cache_hit_rate = (stats.get('inode_cache_size', 0) + 
                                stats.get('block_cache_size', 0)) / total_requests * 100
        
        # 操作计数（从性能监控器获取）
        operation_count = 0
        
        # 平均响应时间
        average_response_time = 0
        
        return SystemMetrics(
            timestamp=time.time(),
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            disk_usage_percent=disk_usage_percent,
            active_connections=active_connections,
            open_files_count=open_files_count,
            cache_hit_rate=cache_hit_rate,
            operation_count=operation_count,
            average_response_time=average_response_time
        )
    
    def _store_metrics(self, metrics: SystemMetrics) -> None:
        """存储指标"""
        with self.lock:
            self.metrics_history.append(metrics)
    
    def _notify_callbacks(self, metrics: SystemMetrics) -> None:
        """通知回调函数"""
        for callback in self.callbacks:
            try:
                callback(metrics)
            except Exception as e:
                print(f"回调函数执行错误: {e}")
    
    def add_callback(self, callback: Callable[[SystemMetrics], None]) -> None:
        """添加回调函数"""
        self.callbacks.append(callback)
    
    def remove_callback(self, callback: Callable[[SystemMetrics], None]) -> None:
        """移除回调函数"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def get_current_metrics(self) -> Optional[SystemMetrics]:
        """获取当前指标"""
        with self.lock:
            if self.metrics_history:
                return self.metrics_history[-1]
            return None
    
    def get_metrics_history(self, duration_seconds: float = 3600) -> List[SystemMetrics]:
        """获取指定时间范围内的指标历史"""
        with self.lock:
            cutoff_time = time.time() - duration_seconds
            return [m for m in self.metrics_history if m.timestamp >= cutoff_time]
    
    def get_average_metrics(self, duration_seconds: float = 300) -> Optional[SystemMetrics]:
        """获取指定时间范围内的平均指标"""
        metrics = self.get_metrics_history(duration_seconds)
        if not metrics:
            return None
        
        return SystemMetrics(
            timestamp=time.time(),
            cpu_percent=sum(m.cpu_percent for m in metrics) / len(metrics),
            memory_percent=sum(m.memory_percent for m in metrics) / len(metrics),
            disk_usage_percent=sum(m.disk_usage_percent for m in metrics) / len(metrics),
            active_connections=sum(m.active_connections for m in metrics) // len(metrics),
            open_files_count=sum(m.open_files_count for m in metrics) // len(metrics),
            cache_hit_rate=sum(m.cache_hit_rate for m in metrics) / len(metrics),
            operation_count=sum(m.operation_count for m in metrics),
            average_response_time=sum(m.average_response_time for m in metrics) / len(metrics)
        )


class HealthChecker:
    """健康检查器"""
    
    def __init__(self, disk_manager, cache_manager=None):
        self.disk_manager = disk_manager
        self.cache_manager = cache_manager
        self.health_checks: Dict[str, Callable] = {}
        self._register_default_checks()
    
    def _register_default_checks(self) -> None:
        """注册默认的健康检查"""
        self.register_check("disk_space", self._check_disk_space)
        self.register_check("inode_availability", self._check_inode_availability)
        self.register_check("cache_health", self._check_cache_health)
        self.register_check("file_system_integrity", self._check_file_system_integrity)
    
    def register_check(self, name: str, check_function: Callable) -> None:
        """注册健康检查函数"""
        self.health_checks[name] = check_function
    
    def run_all_checks(self) -> Dict[str, Dict[str, Any]]:
        """运行所有健康检查"""
        results = {}
        for name, check_function in self.health_checks.items():
            try:
                result = check_function()
                results[name] = result
            except Exception as e:
                results[name] = {
                    "status": "error",
                    "message": f"检查执行失败: {str(e)}",
                    "details": {}
                }
        return results
    
    def _check_disk_space(self) -> Dict[str, Any]:
        """检查磁盘空间"""
        if not self.disk_manager.superblock:
            return {
                "status": "error",
                "message": "磁盘未格式化",
                "details": {}
            }
        
        total_blocks = self.disk_manager.superblock.total_blocks
        free_blocks = self.disk_manager.superblock.free_blocks_count
        used_blocks = total_blocks - free_blocks
        usage_percent = (used_blocks / total_blocks) * 100
        
        if usage_percent > 90:
            status = "critical"
        elif usage_percent > 75:
            status = "warning"
        else:
            status = "healthy"
        
        return {
            "status": status,
            "message": f"磁盘使用率: {usage_percent:.1f}%",
            "details": {
                "total_blocks": total_blocks,
                "free_blocks": free_blocks,
                "used_blocks": used_blocks,
                "usage_percent": usage_percent
            }
        }
    
    def _check_inode_availability(self) -> Dict[str, Any]:
        """检查i节点可用性"""
        if not self.disk_manager.superblock:
            return {
                "status": "error",
                "message": "磁盘未格式化",
                "details": {}
            }
        
        total_inodes = self.disk_manager.superblock.total_inodes
        free_inodes = self.disk_manager.superblock.free_inodes_count
        used_inodes = total_inodes - free_inodes
        usage_percent = (used_inodes / total_inodes) * 100
        
        if usage_percent > 90:
            status = "critical"
        elif usage_percent > 75:
            status = "warning"
        else:
            status = "healthy"
        
        return {
            "status": status,
            "message": f"i节点使用率: {usage_percent:.1f}%",
            "details": {
                "total_inodes": total_inodes,
                "free_inodes": free_inodes,
                "used_inodes": used_inodes,
                "usage_percent": usage_percent
            }
        }
    
    def _check_cache_health(self) -> Dict[str, Any]:
        """检查缓存健康状态"""
        if not self.cache_manager:
            return {
                "status": "warning",
                "message": "缓存管理器未启用",
                "details": {}
            }
        
        stats = self.cache_manager.get_stats()
        total_cache_size = sum(stats.values())
        
        if total_cache_size == 0:
            status = "warning"
            message = "缓存为空"
        elif total_cache_size > 1000:
            status = "warning"
            message = "缓存使用量较高"
        else:
            status = "healthy"
            message = "缓存状态正常"
        
        return {
            "status": status,
            "message": message,
            "details": stats
        }
    
    def _check_file_system_integrity(self) -> Dict[str, Any]:
        """检查文件系统完整性"""
        if not self.disk_manager.superblock:
            return {
                "status": "error",
                "message": "磁盘未格式化",
                "details": {}
            }
        
        # 检查根目录是否存在
        root_inode = None
        if self.disk_manager.superblock.root_inode_id is not None:
            root_inode = self.disk_manager.get_inode(self.disk_manager.superblock.root_inode_id)
        
        if not root_inode:
            return {
                "status": "critical",
                "message": "根目录不存在",
                "details": {}
            }
        
        # 检查位图一致性
        bitmap_issues = []
        for i, inode in enumerate(self.disk_manager.inode_table):
            if inode is not None and self.disk_manager.inode_bitmap[i]:
                bitmap_issues.append(f"i节点 {i} 存在但位图标记为空闲")
            elif inode is None and not self.disk_manager.inode_bitmap[i]:
                bitmap_issues.append(f"i节点 {i} 不存在但位图标记为已使用")
        
        if bitmap_issues:
            return {
                "status": "critical",
                "message": f"发现 {len(bitmap_issues)} 个位图不一致问题",
                "details": {"issues": bitmap_issues}
            }
        
        return {
            "status": "healthy",
            "message": "文件系统完整性检查通过",
            "details": {}
        }


class MetricsExporter:
    """指标导出器"""
    
    def __init__(self, system_monitor: SystemMonitor, performance_monitor: PerformanceMonitor):
        self.system_monitor = system_monitor
        self.performance_monitor = performance_monitor
    
    def export_metrics_to_json(self, file_path: str, duration_seconds: float = 3600) -> bool:
        """导出指标到JSON文件"""
        try:
            system_metrics = self.system_monitor.get_metrics_history(duration_seconds)
            performance_metrics = self.performance_monitor.get_recent_metrics(1000)
            
            export_data = {
                "export_timestamp": time.time(),
                "duration_seconds": duration_seconds,
                "system_metrics": [
                    {
                        "timestamp": m.timestamp,
                        "cpu_percent": m.cpu_percent,
                        "memory_percent": m.memory_percent,
                        "disk_usage_percent": m.disk_usage_percent,
                        "active_connections": m.active_connections,
                        "open_files_count": m.open_files_count,
                        "cache_hit_rate": m.cache_hit_rate,
                        "operation_count": m.operation_count,
                        "average_response_time": m.average_response_time
                    }
                    for m in system_metrics
                ],
                "performance_metrics": [
                    {
                        "operation_type": m.operation_type,
                        "start_time": m.start_time,
                        "end_time": m.end_time,
                        "duration": m.duration,
                        "success": m.success,
                        "error_message": m.error_message,
                        "additional_data": m.additional_data
                    }
                    for m in performance_metrics
                ]
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"导出指标失败: {e}")
            return False
    
    def export_health_report(self, file_path: str, health_checker: HealthChecker) -> bool:
        """导出健康检查报告"""
        try:
            health_results = health_checker.run_all_checks()
            
            report = {
                "timestamp": time.time(),
                "health_checks": health_results,
                "summary": {
                    "total_checks": len(health_results),
                    "healthy": sum(1 for r in health_results.values() if r["status"] == "healthy"),
                    "warnings": sum(1 for r in health_results.values() if r["status"] == "warning"),
                    "critical": sum(1 for r in health_results.values() if r["status"] == "critical"),
                    "errors": sum(1 for r in health_results.values() if r["status"] == "error")
                }
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            print(f"导出健康报告失败: {e}")
            return False 