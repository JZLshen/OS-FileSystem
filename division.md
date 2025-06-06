### 1、沈航：

负责讲解和演示整个项目的“心脏”部分，这部分逻辑最复杂，也是工作量的核心体现。

* **负责模块**:
    1.  `fs_core/file_ops.py` (文件操作逻辑)
    2.  `fs_core/dir_ops.py` (目录操作逻辑)
    3.  `fs_core/disk_manager.py` (底层磁盘块和Inode管理)
    4.  `gui/main_window.py` (主界面的构建与事件处理)
* **讲解内容**:
    * **演示**: 完整地演示文件系统的所有主要GUI功能（浏览、创建、删除、重命名、打开文本编辑器、查看属性等）。
    * **代码讲解**: 重点讲解一两个核心操作的实现，例如：
        * **`write_file`**: 解释如何处理数据块的分配、写入，以及文件变短时的截断逻辑。
        * **`_resolve_path_to_inode_id`**: 解释如何实现路径解析，处理绝对/相对路径和 `.`、`..`。
        * **`main_window.py`**: 解释GUI是如何通过信号和槽机制调用后端的这些操作函数的。

---

### 2、郭修文：讲数据结构

这个任务是理解整个文件系统的基石。它代码量不大，但概念非常重要，是讲解其他一切功能的基础。

* **负责模块**:
    1.  `fs_core/datastructures.py`
* **讲解内容**:
    * 向评委详细解释文件系统的核心数据结构。
    * **`Inode`**: 逐个字段讲解其作用（为什么要有 `link_count`？`permissions` 是如何存储的？`data_block_indices` 是什么？）。**强调 Inode 不存储文件名，这是关键概念。**
    * **`DirectoryEntry`**: 讲解它作为“文件名”和“Inode”之间的桥梁的作用。
    * **`Superblock`**: 解释它为什么是文件系统的“总管”，记录了哪些宏观信息。

---

### 3、李宗泽：用户认证与会话管理

这个任务负责一个完整且独立的功能模块——用户系统。

* **负责模块**:
    1.  `user_management/user_auth.py`
    2.  `gui/login_window.py`
* **讲解内容**:
    * **演示**: 完整地演示用户登录和（如果实现了）登出的过程。
    * **代码讲解**:
        * 解释 `login_window.py` 是如何获取用户输入并传递给后端的。
        * 讲解 `user_auth.py` 中 `login` 函数的认证逻辑。
        * 解释系统是如何在 `UserAuthenticator` 中跟踪当前登录用户（`current_user`）和当前工作目录（`current_cwd_inode_id`）的，这是实现多用户和 `cd` 命令的基础。
        * 讲解为每个用户维护一个独立的打开文件表（`OFT`）的重要性。

---

### 4、赵正熙：持久化与启动引导

这个任务负责讲解系统如何“开机”和“关机”，即状态的保存与加载。

* **负责模块**:
    1.  `fs_core/persistence_manager.py`
    2.  `main.py` (程序启动和初始化部分)
* **讲解内容**:
    * 向评委解释项目是如何做到“可以保存，以便下次开机时再用”的。
    * **`persistence_manager.py`**: 讲解 `save_disk_image` 和 `load_disk_image` 函数，说明是如何使用 `pickle` 模块将整个 `DiskManager` 对象序列化到 `simulated_disk.img` 文件中的。
    * **`main.py`**: 讲解程序的启动流程：
        * 如何检查 `simulated_disk.img` 文件是否存在。
        * 如果文件存在，如何调用 `load_disk_image` 加载现有文件系统。
        * 如果文件不存在，如何创建一个新的 `DiskManager` 实例，并最终（在格式化后）启动系统。
    * 可以补充讲解 `main_window.py` 中的 `closeEvent` 是如何触发最终的 `save_disk_image` 调用的。
