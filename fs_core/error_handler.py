import logging
import traceback
import sys
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import threading
import json
import os


class ErrorSeverity(Enum):
    """错误严重程度枚举"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """错误类别枚举"""
    FILE_SYSTEM = "file_system"
    DISK_OPERATION = "disk_operation"
    USER_AUTH = "user_auth"
    GUI = "gui"
    NETWORK = "network"
    CACHE = "cache"
    PERMISSION = "permission"
    VALIDATION = "validation"
    SYSTEM = "system"


@dataclass
class ErrorRecord:
    """错误记录数据类"""
    timestamp: datetime
    severity: ErrorSeverity
    category: ErrorCategory
    message: str
    exception: Optional[Exception] = None
    stack_trace: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[str] = None
    operation: Optional[str] = None
    file_path: Optional[str] = None


class ErrorHandler:
    """错误处理器"""
    
    def __init__(self, log_file: str = "filesystem.log", max_log_size: int = 10 * 1024 * 1024):
        self.log_file = log_file
        self.max_log_size = max_log_size
        self.error_records: List[ErrorRecord] = []
        self.error_callbacks: List[Callable[[ErrorRecord], None]] = []
        self.lock = threading.RLock()
        
        # 设置日志记录器
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志记录"""
        # 创建日志记录器
        self.logger = logging.getLogger('FileSystem')
        self.logger.setLevel(logging.DEBUG)
        
        # 创建文件处理器
        file_handler = logging.FileHandler(self.log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def log_error(self, severity: ErrorSeverity, category: ErrorCategory, 
                  message: str, exception: Optional[Exception] = None,
                  context: Optional[Dict[str, Any]] = None,
                  user_id: Optional[str] = None,
                  operation: Optional[str] = None,
                  file_path: Optional[str] = None) -> ErrorRecord:
        """记录错误"""
        with self.lock:
            # 确保severity和category是枚举类型
            if isinstance(severity, str):
                try:
                    severity = ErrorSeverity(severity)
                except ValueError:
                    severity = ErrorSeverity.ERROR
            
            if isinstance(category, str):
                try:
                    category = ErrorCategory(category)
                except ValueError:
                    category = ErrorCategory.SYSTEM
            
            error_record = ErrorRecord(
                timestamp=datetime.now(),
                severity=severity,
                category=category,
                message=message,
                exception=exception,
                stack_trace=traceback.format_exc() if exception else None,
                context=context or {},
                user_id=user_id,
                operation=operation,
                file_path=file_path
            )
            
            # 添加到记录列表
            self.error_records.append(error_record)
            
            # 记录到日志文件
            log_message = f"[{category.value}] {message}"
            if exception:
                log_message += f" - Exception: {str(exception)}"
            if context:
                log_message += f" - Context: {context}"
            
            if severity == ErrorSeverity.DEBUG:
                self.logger.debug(log_message)
            elif severity == ErrorSeverity.INFO:
                self.logger.info(log_message)
            elif severity == ErrorSeverity.WARNING:
                self.logger.warning(log_message)
            elif severity == ErrorSeverity.ERROR:
                self.logger.error(log_message)
            elif severity == ErrorSeverity.CRITICAL:
                self.logger.critical(log_message)
            
            # 通知回调函数
            self._notify_callbacks(error_record)
            
            return error_record
    
    def add_error_callback(self, callback: Callable[[ErrorRecord], None]) -> None:
        """添加错误回调函数"""
        self.error_callbacks.append(callback)
    
    def remove_error_callback(self, callback: Callable[[ErrorRecord], None]) -> None:
        """移除错误回调函数"""
        if callback in self.error_callbacks:
            self.error_callbacks.remove(callback)
    
    def _notify_callbacks(self, error_record: ErrorRecord) -> None:
        """通知回调函数"""
        for callback in self.error_callbacks:
            try:
                callback(error_record)
            except Exception as e:
                print(f"错误回调函数执行失败: {e}")
    
    def get_error_summary(self, duration_hours: float = 24) -> Dict[str, Any]:
        """获取错误摘要"""
        with self.lock:
            cutoff_time = datetime.now().timestamp() - (duration_hours * 3600)
            recent_errors = [
                e for e in self.error_records 
                if e.timestamp.timestamp() >= cutoff_time
            ]
            
            summary = {
                "total_errors": len(recent_errors),
                "by_severity": {},
                "by_category": {},
                "most_common_errors": {}
            }
            
            # 按严重程度统计
            for severity in ErrorSeverity:
                count = sum(1 for e in recent_errors if e.severity == severity)
                summary["by_severity"][severity.value] = count
            
            # 按类别统计
            for category in ErrorCategory:
                count = sum(1 for e in recent_errors if e.category == category)
                summary["by_category"][category.value] = count
            
            # 最常见的错误消息
            error_messages = {}
            for error in recent_errors:
                error_messages[error.message] = error_messages.get(error.message, 0) + 1
            
            summary["most_common_errors"] = dict(
                sorted(error_messages.items(), key=lambda x: x[1], reverse=True)[:10]
            )
            
            return summary
    
    def get_recent_errors(self, count: int = 100) -> List[ErrorRecord]:
        """获取最近的错误记录"""
        with self.lock:
            return self.error_records[-count:]
    
    def clear_errors(self) -> None:
        """清空错误记录"""
        with self.lock:
            self.error_records.clear()
    
    def export_errors_to_json(self, file_path: str) -> bool:
        """导出错误记录到JSON文件"""
        try:
            with self.lock:
                export_data = {
                    "export_timestamp": datetime.now().isoformat(),
                    "total_errors": len(self.error_records),
                    "errors": []
                }
                
                for error in self.error_records:
                    error_data = {
                        "timestamp": error.timestamp.isoformat(),
                        "severity": error.severity.value,
                        "category": error.category.value,
                        "message": error.message,
                        "exception": str(error.exception) if error.exception else None,
                        "stack_trace": error.stack_trace,
                        "context": error.context,
                        "user_id": error.user_id,
                        "operation": error.operation,
                        "file_path": error.file_path
                    }
                    export_data["errors"].append(error_data)
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)
                
                return True
                
        except Exception as e:
            print(f"导出错误记录失败: {e}")
            return False


class FileSystemException(Exception):
    """文件系统异常基类"""
    
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.FILE_SYSTEM,
                 severity: ErrorSeverity = ErrorSeverity.ERROR, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.category = category
        self.severity = severity
        self.context = context or {}


class DiskOperationException(FileSystemException):
    """磁盘操作异常"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, ErrorCategory.DISK_OPERATION, ErrorSeverity.ERROR, context)


class PermissionException(FileSystemException):
    """权限异常"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, ErrorCategory.PERMISSION, ErrorSeverity.WARNING, context)


class ValidationException(FileSystemException):
    """验证异常"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, ErrorCategory.VALIDATION, ErrorSeverity.WARNING, context)


class ResourceNotFoundException(FileSystemException):
    """资源未找到异常"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, ErrorCategory.FILE_SYSTEM, ErrorSeverity.ERROR, context)


class OperationNotSupportedException(FileSystemException):
    """操作不支持异常"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, ErrorCategory.FILE_SYSTEM, ErrorSeverity.WARNING, context)


class ErrorContext:
    """错误上下文管理器"""
    
    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler
        self.context: Dict[str, Any] = {}
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # 记录异常
            self.error_handler.log_error(
                severity=ErrorSeverity.ERROR,
                category=ErrorCategory.SYSTEM,
                message=str(exc_val),
                exception=exc_val,
                context=self.context
            )
        return False  # 不抑制异常
    
    def add_context(self, key: str, value: Any) -> 'ErrorContext':
        """添加上下文信息"""
        self.context[key] = value
        return self
    
    def set_user_id(self, user_id: str) -> 'ErrorContext':
        """设置用户ID"""
        self.context['user_id'] = user_id
        return self
    
    def set_operation(self, operation: str) -> 'ErrorContext':
        """设置操作名称"""
        self.context['operation'] = operation
        return self
    
    def set_file_path(self, file_path: str) -> 'ErrorContext':
        """设置文件路径"""
        self.context['file_path'] = file_path
        return self


class ErrorReporter:
    """错误报告器"""
    
    def __init__(self, error_handler: ErrorHandler):
        self.error_handler = error_handler
    
    def report_file_operation_error(self, operation: str, file_path: str, 
                                   error: Exception, user_id: Optional[str] = None) -> None:
        """报告文件操作错误"""
        self.error_handler.log_error(
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.FILE_SYSTEM,
            message=f"文件操作失败: {operation}",
            exception=error,
            context={"operation": operation, "file_path": file_path},
            user_id=user_id,
            operation=operation,
            file_path=file_path
        )
    
    def report_permission_error(self, operation: str, file_path: str,
                               user_id: str, required_permissions: str) -> None:
        """报告权限错误"""
        self.error_handler.log_error(
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.PERMISSION,
            message=f"权限不足: {operation}",
            context={
                "operation": operation,
                "file_path": file_path,
                "required_permissions": required_permissions
            },
            user_id=user_id,
            operation=operation,
            file_path=file_path
        )
    
    def report_validation_error(self, field: str, value: Any, 
                               expected_format: str) -> None:
        """报告验证错误"""
        self.error_handler.log_error(
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.VALIDATION,
            message=f"验证失败: {field}",
            context={
                "field": field,
                "value": value,
                "expected_format": expected_format
            }
        )
    
    def report_disk_error(self, operation: str, block_id: Optional[int] = None,
                         inode_id: Optional[int] = None) -> None:
        """报告磁盘错误"""
        self.error_handler.log_error(
            severity=ErrorSeverity.ERROR,
            category=ErrorCategory.DISK_OPERATION,
            message=f"磁盘操作失败: {operation}",
            context={
                "operation": operation,
                "block_id": block_id,
                "inode_id": inode_id
            },
            operation=operation
        )
    
    def report_cache_error(self, operation: str, cache_type: str,
                          key: Optional[str] = None) -> None:
        """报告缓存错误"""
        self.error_handler.log_error(
            severity=ErrorSeverity.WARNING,
            category=ErrorCategory.CACHE,
            message=f"缓存操作失败: {operation}",
            context={
                "operation": operation,
                "cache_type": cache_type,
                "key": key
            },
            operation=operation
        )


# 全局错误处理器实例
_global_error_handler: Optional[ErrorHandler] = None


def get_global_error_handler() -> ErrorHandler:
    """获取全局错误处理器"""
    global _global_error_handler
    if _global_error_handler is None:
        _global_error_handler = ErrorHandler()
    return _global_error_handler


def set_global_error_handler(error_handler: ErrorHandler) -> None:
    """设置全局错误处理器"""
    global _global_error_handler
    _global_error_handler = error_handler


def log_error(severity: ErrorSeverity, category: ErrorCategory, message: str,
              exception: Optional[Exception] = None, **kwargs) -> ErrorRecord:
    """记录错误的便捷函数"""
    return get_global_error_handler().log_error(
        severity, category, message, exception, **kwargs
    ) 