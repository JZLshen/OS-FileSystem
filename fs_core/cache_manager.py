import time
from typing import Dict, Any, Optional, Tuple
from collections import OrderedDict
import threading


class CacheEntry:
    """缓存条目类"""
    
    def __init__(self, key: str, value: Any, ttl: int = 300):
        self.key = key
        self.value = value
        self.created_time = time.time()
        self.last_access = time.time()
        self.ttl = ttl  # 生存时间（秒）
        self.access_count = 0
    
    def is_expired(self) -> bool:
        """检查缓存条目是否过期"""
        return time.time() - self.created_time > self.ttl
    
    def access(self):
        """记录访问"""
        self.last_access = time.time()
        self.access_count += 1


class LRUCache:
    """LRU（最近最少使用）缓存实现"""
    
    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                if entry.is_expired():
                    del self.cache[key]
                    return None
                
                entry.access()
                # 移动到末尾（最近使用）
                self.cache.move_to_end(key)
                return entry.value
            return None
    
    def put(self, key: str, value: Any, ttl: int = 300) -> None:
        """放入缓存"""
        with self.lock:
            if key in self.cache:
                # 更新现有条目
                self.cache.move_to_end(key)
                entry = self.cache[key]
                entry.value = value
                entry.created_time = time.time()
                entry.ttl = ttl
            else:
                # 添加新条目
                if len(self.cache) >= self.max_size:
                    # 移除最旧的条目
                    self.cache.popitem(last=False)
                
                entry = CacheEntry(key, value, ttl)
                self.cache[key] = entry
    
    def remove(self, key: str) -> bool:
        """移除缓存条目"""
        with self.lock:
            return self.cache.pop(key, None) is not None
    
    def clear(self) -> None:
        """清空缓存"""
        with self.lock:
            self.cache.clear()
    
    def cleanup_expired(self) -> int:
        """清理过期条目，返回清理的数量"""
        with self.lock:
            expired_keys = [
                key for key, entry in self.cache.items() 
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self.cache[key]
            return len(expired_keys)
    
    def size(self) -> int:
        """返回缓存大小"""
        with self.lock:
            return len(self.cache)


class CacheManager:
    """缓存管理器，管理不同类型的缓存"""
    
    def __init__(self):
        self.inode_cache = LRUCache(max_size=500)  # i节点缓存
        self.block_cache = LRUCache(max_size=1000)  # 数据块缓存
        self.path_cache = LRUCache(max_size=200)  # 路径解析缓存
        self.directory_cache = LRUCache(max_size=100)  # 目录内容缓存
        
        # 启动清理线程
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """启动定期清理线程"""
        def cleanup_worker():
            while True:
                try:
                    time.sleep(60)  # 每分钟清理一次
                    self.inode_cache.cleanup_expired()
                    self.block_cache.cleanup_expired()
                    self.path_cache.cleanup_expired()
                    self.directory_cache.cleanup_expired()
                except Exception:
                    pass  # 忽略清理过程中的错误
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
    
    def get_inode(self, inode_id: int) -> Optional[Any]:
        """获取缓存的i节点"""
        return self.inode_cache.get(f"inode_{inode_id}")
    
    def put_inode(self, inode_id: int, inode: Any, ttl: int = 600) -> None:
        """缓存i节点"""
        self.inode_cache.put(f"inode_{inode_id}", inode, ttl)
    
    def get_block(self, block_id: int) -> Optional[Any]:
        """获取缓存的数据块"""
        return self.block_cache.get(f"block_{block_id}")
    
    def put_block(self, block_id: int, block_data: Any, ttl: int = 300) -> None:
        """缓存数据块"""
        self.block_cache.put(f"block_{block_id}", block_data, ttl)
    
    def get_path(self, path_key: str) -> Optional[Any]:
        """获取缓存的路径解析结果"""
        return self.path_cache.get(f"path_{path_key}")
    
    def put_path(self, path_key: str, result: Any, ttl: int = 300) -> None:
        """缓存路径解析结果"""
        self.path_cache.put(f"path_{path_key}", result, ttl)
    
    def get_directory(self, dir_inode_id: int) -> Optional[Any]:
        """获取缓存的目录内容"""
        return self.directory_cache.get(f"dir_{dir_inode_id}")
    
    def put_directory(self, dir_inode_id: int, contents: Any, ttl: int = 60) -> None:
        """缓存目录内容"""
        self.directory_cache.put(f"dir_{dir_inode_id}", contents, ttl)
    
    def invalidate_inode(self, inode_id: int) -> None:
        """使i节点缓存失效"""
        self.inode_cache.remove(f"inode_{inode_id}")
    
    def invalidate_block(self, block_id: int) -> None:
        """使数据块缓存失效"""
        self.block_cache.remove(f"block_{block_id}")
    
    def invalidate_directory(self, dir_inode_id: int) -> None:
        """使目录缓存失效"""
        self.directory_cache.remove(f"dir_{dir_inode_id}")
    
    def invalidate_path_cache(self) -> None:
        """使所有路径缓存失效"""
        self.path_cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "inode_cache_size": self.inode_cache.size(),
            "block_cache_size": self.block_cache.size(),
            "path_cache_size": self.path_cache.size(),
            "directory_cache_size": self.directory_cache.size(),
        }
    
    def clear_all(self) -> None:
        """清空所有缓存"""
        self.inode_cache.clear()
        self.block_cache.clear()
        self.path_cache.clear()
        self.directory_cache.clear() 