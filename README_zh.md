# IMA 知识库下载器

图形界面工具，粘贴 IMA 知识库分享链接，自动递归下载所有文件到本地。无需安装，双击 `start.bat` 即可运行。

> **[English README available here](./README.md)**

---

## 功能特点

- 📋 粘贴分享链接，`share_id` 自动提取
- 📁 递归遍历所有子文件夹，按分类分组并发（同一类在一个线程，多类并行）
- ⚡ 智能并发 + 浏览器打印网页为 PDF（链接类内容优先转 PDF）
- 🔄 增量下载：已存在的文件自动跳过
- 🎨 现代美观 GUI（ttk 样式，进度条，简洁大方）
- 🌙 暗色主题，一键启动 start.bat

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

**Windows 用户：**  
双击 **`start.bat`**，首次运行会自动：
1. 检查 Python 是否可用
2. 安装 `requests` 依赖（仅首次需要）
3. 弹出 GUI 窗口

后续使用：直接双击 `start.bat` 即可。

**macOS / Linux 用户：**  
打开终端，进入项目文件夹，运行：

```bash
# 首次运行（安装依赖）
pip install requests

# 启动 GUI
python gui.py
```

或者创建一键启动脚本：

```bash
# 创建 start.sh
echo '#!/bin/bash' > start.sh
echo 'pip install requests -q' >> start.sh
echo 'python gui.py' >> start.sh
chmod +x start.sh

# 运行
./start.sh
```

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
├── gui.py           # GUI 主程序（现代 ttk 界面）
├── api_service.py   # IMA API 调用封装
├── downloader.py    # 下载引擎（支持分组并发 + 网页打印 PDF）
├── models.py        # 数据模型
├── traverser.py     # 递归收集 + 分类分组
├── sync_manager.py  # CLI 同步
├── main.py          # CLI 入口
├── requirements.txt # 仅需 requests
├── start.bat        # 一键启动
├── README.md        # 英文
└── README_zh.md     # 本文件
```

---

## 配置参数

如需修改参数，编辑 `downloader.py`：

```python
TIMEOUT = 30                  # HTTP 请求超时（秒）
MAX_WORKERS = 20              # 文件下载线程数
MAX_CATEGORY_WORKERS = 6      # 分类并行数（同一分类内单线程）
```

---

## 常见问题

**Q：双击 `start.bat` 没反应 / 一闪而过，没有主界面？**
A：常见原因：
1. Python 未安装 tkinter（安装 Python 时勾选 "tcl/tk and IDLE"）。
2. 运行时错误被隐藏。
   - 右键编辑 start.bat，在末尾加 `pause`，重新运行查看错误。
   - 或直接双击运行 `python gui.py` （会显示控制台错误）。
启动脚本已优化，会尝试回退并提示。

**Q：提示"无法提取 share_id"？**
A：检查分享链接是否完整，确保包含 `shareId=xxxxxxxx` 这段。把 IMA 复制的整段文字直接粘贴即可，程序会自动提取。

**Q：下载到一半取消了，再次运行会重复下载吗？**
A：不会。已存在的文件自动跳过，不会重复下载。

**Q：某个文件下载失败了怎么办？**
A：日志区会显示 `[FAIL] 文件名 — 错误原因`，确认问题后重新运行即可，已下载的文件不会重复下载。

**Q：链接类内容现在怎么处理？**
A：优先用浏览器 headless 打印为 PDF（类似 Ctrl+P 保存 PDF），失败则保存为可双击的 .url 链接文件。

**Q：下载很多文件时会更快吗？**
A：是的！现在按顶层分类分组：同一分类的文件在一个线程内下载，不同分类并行（默认最多 6 个分类并发）。

---

*Python 重写版，基于 [itscj1014/ima-download](https://github.com/itscj1014/ima-download)（Java 原版）*