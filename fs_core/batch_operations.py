import time
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .datastructures import FileType
from .disk_manager import DiskManager


class OperationType(Enum):
    """操作类型枚举"""
    CREATE_FILE = "create_file"
    DELETE_FILE = "delete_file"
    CREATE_DIR = "create_dir"
    DELETE_DIR = "delete_dir"
    COPY_FILE = "copy_file"
    MOVE_FILE = "move_file"
    RENAME = "rename"


@dataclass
class BatchOperation:
    """批量操作条目"""
    operation_type: OperationType
    source_path: str
    target_path: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    status: str = "pending"  # pending, running, completed, failed
    result: Optional[Any] = None
    error_message: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None


class BatchOperationManager:
    """批量操作管理器"""
    
    def __init__(self, disk_manager: DiskManager, max_workers: int = 4):
        self.disk_manager = disk_manager
        self.max_workers = max_workers
        self.operations: List[BatchOperation] = []
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.lock = threading.RLock()
        self.progress_callback: Optional[Callable[[int, int], None]] = None
        
    def add_operation(self, operation: BatchOperation) -> int:
        """添加操作到队列"""
        with self.lock:
            operation_id = len(self.operations)
            self.operations.append(operation)
            return operation_id
    
    def set_progress_callback(self, callback: Callable[[int, int], None]):
        """设置进度回调函数"""
        self.progress_callback = callback
    
    def execute_batch(self) -> Dict[str, Any]:
        """执行批量操作"""
        if not self.operations:
            return {"success": True, "message": "没有操作需要执行"}
        
        total_operations = len(self.operations)
        completed_operations = 0
        failed_operations = 0
        
        # 标记所有操作为运行状态
        for op in self.operations:
            op.status = "running"
            op.start_time = time.time()
        
        # 提交任务到线程池
        futures = []
        for op in self.operations:
            future = self.executor.submit(self._execute_single_operation, op)
            futures.append(future)
        
        # 等待所有任务完成
        for future in as_completed(futures):
            try:
                result = future.result()
                completed_operations += 1
                if self.progress_callback:
                    self.progress_callback(completed_operations, total_operations)
            except Exception as e:
                failed_operations += 1
                print(f"批量操作执行失败: {e}")
        
        # 生成报告
        report = self._generate_report(completed_operations, failed_operations)
        return report
    
    def _execute_single_operation(self, operation: BatchOperation) -> bool:
        """执行单个操作"""
        try:
            if operation.operation_type == OperationType.CREATE_FILE:
                result = self._create_file_operation(operation)
            elif operation.operation_type == OperationType.DELETE_FILE:
                result = self._delete_file_operation(operation)
            elif operation.operation_type == OperationType.CREATE_DIR:
                result = self._create_dir_operation(operation)
            elif operation.operation_type == OperationType.DELETE_DIR:
                result = self._delete_dir_operation(operation)
            elif operation.operation_type == OperationType.COPY_FILE:
                result = self._copy_file_operation(operation)
            elif operation.operation_type == OperationType.MOVE_FILE:
                result = self._move_file_operation(operation)
            elif operation.operation_type == OperationType.RENAME:
                result = self._rename_operation(operation)
            else:
                raise ValueError(f"不支持的操作类型: {operation.operation_type}")
            
            operation.status = "completed"
            operation.result = result
            operation.end_time = time.time()
            return True
            
        except Exception as e:
            operation.status = "failed"
            operation.error_message = str(e)
            operation.end_time = time.time()
            return False
    
    def _create_file_operation(self, operation: BatchOperation) -> bool:
        """创建文件操作"""
        # 这里需要实现具体的文件创建逻辑
        # 暂时返回True作为占位符
        return True
    
    def _delete_file_operation(self, operation: BatchOperation) -> bool:
        """删除文件操作"""
        # 这里需要实现具体的文件删除逻辑
        return True
    
    def _create_dir_operation(self, operation: BatchOperation) -> bool:
        """创建目录操作"""
        # 这里需要实现具体的目录创建逻辑
        return True
    
    def _delete_dir_operation(self, operation: BatchOperation) -> bool:
        """删除目录操作"""
        # 这里需要实现具体的目录删除逻辑
        return True
    
    def _copy_file_operation(self, operation: BatchOperation) -> bool:
        """复制文件操作"""
        # 这里需要实现具体的文件复制逻辑
        return True
    
    def _move_file_operation(self, operation: BatchOperation) -> bool:
        """移动文件操作"""
        # 这里需要实现具体的文件移动逻辑
        return True
    
    def _rename_operation(self, operation: BatchOperation) -> bool:
        """重命名操作"""
        # 这里需要实现具体的重命名逻辑
        return True
    
    def _generate_report(self, completed: int, failed: int) -> Dict[str, Any]:
        """生成执行报告"""
        total = len(self.operations)
        success_rate = (completed / total * 100) if total > 0 else 0
        
        report = {
            "total_operations": total,
            "completed_operations": completed,
            "failed_operations": failed,
            "success_rate": success_rate,
            "operations": []
        }
        
        for i, op in enumerate(self.operations):
            op_report = {
                "id": i,
                "type": op.operation_type.value,
                "source": op.source_path,
                "target": op.target_path,
                "status": op.status,
                "error": op.error_message,
                "duration": op.end_time - op.start_time if op.end_time and op.start_time else None
            }
            report["operations"].append(op_report)
        
        return report
    
    def clear_operations(self):
        """清空操作队列"""
        with self.lock:
            self.operations.clear()
    
    def get_operation_status(self, operation_id: int) -> Optional[Dict[str, Any]]:
        """获取操作状态"""
        with self.lock:
            if 0 <= operation_id < len(self.operations):
                op = self.operations[operation_id]
                return {
                    "status": op.status,
                    "result": op.result,
                    "error": op.error_message,
                    "duration": op.end_time - op.start_time if op.end_time and op.start_time else None
                }
            return None
    
    def cancel_operation(self, operation_id: int) -> bool:
        """取消操作"""
        with self.lock:
            if 0 <= operation_id < len(self.operations):
                op = self.operations[operation_id]
                if op.status == "pending":
                    op.status = "cancelled"
                    return True
            return False
    
    def shutdown(self):
        """关闭线程池"""
        self.executor.shutdown(wait=True)


class FileOperationBatch:
    """文件操作批量处理器"""
    
    def __init__(self, disk_manager: DiskManager):
        self.disk_manager = disk_manager
        self.batch_manager = BatchOperationManager(disk_manager)
    
    def create_files_batch(self, file_paths: List[str], content: str = "") -> int:
        """批量创建文件"""
        for file_path in file_paths:
            operation = BatchOperation(
                operation_type=OperationType.CREATE_FILE,
                source_path=file_path,
                parameters={"content": content}
            )
            self.batch_manager.add_operation(operation)
        return len(file_paths)
    
    def delete_files_batch(self, file_paths: List[str]) -> int:
        """批量删除文件"""
        for file_path in file_paths:
            operation = BatchOperation(
                operation_type=OperationType.DELETE_FILE,
                source_path=file_path
            )
            self.batch_manager.add_operation(operation)
        return len(file_paths)
    
    def create_dirs_batch(self, dir_paths: List[str]) -> int:
        """批量创建目录"""
        for dir_path in dir_paths:
            operation = BatchOperation(
                operation_type=OperationType.CREATE_DIR,
                source_path=dir_path
            )
            self.batch_manager.add_operation(operation)
        return len(dir_paths)
    
    def copy_files_batch(self, source_target_pairs: List[Tuple[str, str]]) -> int:
        """批量复制文件"""
        for source, target in source_target_pairs:
            operation = BatchOperation(
                operation_type=OperationType.COPY_FILE,
                source_path=source,
                target_path=target
            )
            self.batch_manager.add_operation(operation)
        return len(source_target_pairs)
    
    def move_files_batch(self, source_target_pairs: List[Tuple[str, str]]) -> int:
        """批量移动文件"""
        for source, target in source_target_pairs:
            operation = BatchOperation(
                operation_type=OperationType.MOVE_FILE,
                source_path=source,
                target_path=target
            )
            self.batch_manager.add_operation(operation)
        return len(source_target_pairs)
    
    def execute_all(self, progress_callback: Optional[Callable[[int, int], None]] = None) -> Dict[str, Any]:
        """执行所有批量操作"""
        if progress_callback:
            self.batch_manager.set_progress_callback(progress_callback)
        return self.batch_manager.execute_batch()
    
    def clear_batch(self):
        """清空批量操作"""
        self.batch_manager.clear_operations()
    
    def get_batch_status(self) -> Dict[str, Any]:
        """获取批量操作状态"""
        return {
            "pending_operations": len([op for op in self.batch_manager.operations if op.status == "pending"]),
            "running_operations": len([op for op in self.batch_manager.operations if op.status == "running"]),
            "completed_operations": len([op for op in self.batch_manager.operations if op.status == "completed"]),
            "failed_operations": len([op for op in self.batch_manager.operations if op.status == "failed"]),
            "total_operations": len(self.batch_manager.operations)
        } 