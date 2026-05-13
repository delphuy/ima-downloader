# IMA 知识库下载器

图形界面工具，粘贴 IMA 知识库分享链接，自动递归下载所有文件到本地。无需安装，双击 `start.bat` 即可运行。

> **[English README available here](./README.md)**

---

## 功能特点

- 📋 粘贴分享链接，`share_id` 自动提取
- 📁 递归遍历所有子文件夹
- ⚡ 并发下载（20 线程），速度快
- 🔄 增量下载：已存在的文件自动跳过，再次运行可断点续传
- 🌙 暗色主题 GUI，一键启动

---

## 快速开始

### 1. 安装 Python

需要 **Python 3.8 或以上版本**。

- 下载地址：<https://www.python.org/downloads/>
- ⚠️ 安装时务必勾选 **`Add Python to PATH`**（非常重要）

验证安装：

```bash
python --version
```

### 2. 启动程序

双击 **`start.bat`**，首次运行会自动：
1. 检查 Python 是否可用
2. 安装 `requests` 依赖（仅首次需要）
3. 弹出 GUI 窗口

后续使用：直接双击 `start.bat` 即可。

---

## 使用步骤

1. 打开 **IMA 知识库** → 点击右上角 **分享 → 复制链接**
2. **双击 `start.bat`**，稍等片刻，GUI 窗口弹出
3. 将链接**粘贴**到"分享链接"文本框
4. **选择保存目录**（默认保存到 `downloads/` 文件夹）
5. 点击 **▶ 开始下载**，等待完成即可

下载过程中：
- 顶部进度条显示当前文件 `[第几个/总数] 文件名`
- 日志区显示跳过、完成、失败等关键信息
- 下载开始后输入框自动锁定，防止误操作
- 如需中断，点击 **⏹ 取消**

---

## 增量下载（断点续传）

程序每次运行前自动扫描保存目录，已存在的文件直接跳过，不会重复下载。

**场景**：第一次下载中断了，再次双击 `start.bat`，已完成的文件自动跳过，只下载缺失的部分。

---

## 目录结构

```
.
├── gui.py           # GUI 主程序（双击 start.bat 启动它）
├── api_service.py   # IMA API 调用封装
├── downloader.py    # 文件下载（并发 + 断点续传）
├── models.py        # 数据模型
├── sync_manager.py  # 递归遍历 + 失败重试
├── main.py          # CLI 入口
├── requirements.txt # Python 依赖（仅需 requests）
├── start.bat        # 一键启动脚本
├── README.md        # 英文说明
└── README_zh.md     # 本文件
```

---

## 配置参数

如需修改并发线程数、请求超时等参数，编辑 `downloader.py`：

```python
TIMEOUT = 30       # HTTP 请求超时（秒）
MAX_WORKERS = 20   # 并发下载线程数
```

---

## 常见问题

**Q：双击 `start.bat` 没反应 / 一闪而过？**
A：右键 → 编辑 打开 `start.bat`，在最后加一行 `pause`，保存后重新双击运行，可以看到错误信息。最常见原因是 Python 没有加入 PATH。

**Q：提示"无法提取 share_id"？**
A：检查分享链接是否完整，确保包含 `shareId=xxxxxxxx` 这段。把 IMA 复制的整段文字直接粘贴即可，程序会自动提取。

**Q：下载到一半取消了，再次运行会重复下载吗？**
A：不会。已存在的文件自动跳过，不会重复下载。

**Q：某个文件下载失败了怎么办？**
A：日志区会显示 `[FAIL] 文件名 — 错误原因`，确认问题后重新运行即可，已下载的文件不会重复下载。

---

*Python 重写版，基于 [itscj1014/ima-download](https://github.com/itscj1014/ima-download)（Java 原版）*