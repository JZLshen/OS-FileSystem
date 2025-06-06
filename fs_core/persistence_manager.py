import pickle
from typing import Optional
import os
from .disk_manager import DiskManager

DEFAULT_DISK_IMAGE_PATH = "simulated_disk.img"


class PersistenceManager:
    def save_disk_image(
        self, disk_manager: DiskManager, filepath: str = DEFAULT_DISK_IMAGE_PATH
    ) -> bool:
        """
        将DiskManager对象的状态保存到文件。
        Args:
            disk_manager: 要保存的DiskManager实例。
            filepath: 保存文件的路径。
        Returns:
            bool: 保存是否成功。
        """
        if not disk_manager.is_formatted:
            # 对于未格式化的磁盘，通常不应该有太多有意义的数据去保存，
            # 但如果确实执行了保存，它会保存当前 DiskManager 的空或初始状态。
            # 根据需求，也可以选择不保存未格式化的磁盘或发出更强的警告/错误。
            print(
                "Warning: Attempting to save a disk that is not fully formatted or has no superblock. Saving current state."
            )
            # 如果连 superblock 都没有，可能意味着它是一个全新的、未初始化的 DiskManager 实例。
            if disk_manager.superblock is None:
                print(
                    "DiskManager has no superblock. Saving an empty/uninitialized state."
                )

        try:
            with open(filepath, "wb") as f:
                pickle.dump(disk_manager, f, pickle.HIGHEST_PROTOCOL)
            print(f"Disk image saved successfully to {filepath}")
            return True
        except Exception as e:
            print(f"Error saving disk image to {filepath}: {e}")
            return False

    def load_disk_image(
        self, filepath: str = DEFAULT_DISK_IMAGE_PATH
    ) -> Optional[DiskManager]:
        """
        从文件加载DiskManager对象的状态。
        Args:
            filepath: 加载文件的路径。
        Returns:
            Optional[DiskManager]: 加载的DiskManager实例，如果失败则返回None。
        """
        if not os.path.exists(filepath):
            print(
                f"Persistence: Disk image file '{filepath}' not found. A new disk will need to be formatted."
            )
            return None

        try:
            with open(filepath, "rb") as f:
                disk_manager = pickle.load(f)

            # 基本验证
            if not isinstance(disk_manager, DiskManager):
                print(
                    f"Error: Loaded object from {filepath} is not a DiskManager instance."
                )
                return None

            # 一个被正确保存的、格式化过的磁盘应该有一个超级块。
            # is_formatted 状态也应该被pickle正确地保存和恢复。
            # 我们主要信任pickle能够恢复对象状态。
            # 如果superblock存在，那么is_formatted也应该是True。
            if disk_manager.superblock is not None and not disk_manager.is_formatted:
                # 这种情况理论上不应发生，如果superblock存在，is_formatted也应为True。
                # 但为了稳健，如果发现这种不一致，可以尝试修正或警告。
                print(
                    f"Warning: Loaded disk from {filepath} has a superblock but was marked as not formatted. Setting is_formatted to True."
                )
                disk_manager.is_formatted = True
            elif disk_manager.superblock is None and disk_manager.is_formatted:
                print(
                    f"Warning: Loaded disk from {filepath} has no superblock but was marked as formatted. This is inconsistent."
                )
                # 此时可能需要将 is_formatted 设为 False 或认为加载失败
                # disk_manager.is_formatted = False # 或者直接返回None
                # return None

            print(f"Disk image loaded successfully from {filepath}")
            return disk_manager

        except (
            FileNotFoundError
        ):  # 这个检查理论上已被上面的 os.path.exists 覆盖，但保留无妨
            print(
                f"Persistence: Disk image file '{filepath}' not found (double check). A new disk will need to be formatted."
            )
            return None
        except (
            pickle.UnpicklingError,
            EOFError,
            AttributeError,
            ImportError,
            IndexError,
        ) as e:
            # 这些是常见的pickle反序列化错误，可能表示文件损坏或版本不兼容
            print(
                f"Error loading disk image from {filepath}. File may be corrupted or incompatible: {e}"
            )
            return None
        except Exception as e:  # 捕获其他潜在错误
            print(
                f"An unexpected error occurred while loading disk image from {filepath}: {e}"
            )
            return None
