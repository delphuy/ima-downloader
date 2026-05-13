# IMA Knowledge Base Downloader

A cross-platform desktop tool to recursively download files from IMA Knowledge Base via share links — no install required, just double-click `start.bat`.

> **[中文版使用说明，请点击这里](./README_zh.md)**

---

## Features

- 📋 Paste a share link — `share_id` extracted automatically
- 📁 Recursive traversal of all subfolders
- ⚡ Concurrent downloads (20 threads)
- 🔄 Incremental download: skip existing files, resume anytime
- 🌙 Dark-themed GUI, one-click startup

---

## Quick Start

### 1. Install Python

Requires **Python 3.8 or above**.

- Download: <https://www.python.org/downloads/>
- ⚠️ Be sure to check **Add Python to PATH** during install

Verify:

```bash
python --version
```

### 2. Launch

Double-click **`start.bat`**. On first run it will:
1. Check Python availability
2. Install the `requests` dependency (one-time only)
3. Open the GUI

Subsequent runs: just double-click `start.bat` — done.

---

## How to Use

1. Open the **IMA Knowledge Base** → click **Share → Copy Link**
2. Double-click **`start.bat`**, wait for the GUI window
3. **Paste the link** into the share-link text box
4. **Choose save folder** (default: `downloads/`)
5. Click **▶ Start Download**

During download:
- Top progress bar shows current file `[N/Total] filename.ext`
- Log area shows skip / success / failure events
- All inputs are locked during download to prevent accidents
- Click **⏹ Cancel** to abort

---

## Incremental Download

The program scans the save directory before each run. Already-downloaded files are skipped automatically — no duplicates, safe to re-run anytime.

---

## Project Structure

```
.
├── gui.py           # GUI main entry (start via start.bat)
├── api_service.py   # IMA API wrapper
├── downloader.py    # Download engine (concurrent + resume)
├── models.py        # Data models
├── sync_manager.py  # Recursive traversal + retry logic
├── main.py          # CLI entry point
├── requirements.txt # Python dependencies (requests only)
├── start.bat        # One-click launcher
└── README.md        # This file
```

---

## Configuration

To tweak concurrency or timeouts, edit `downloader.py`:

```python
TIMEOUT = 30       # HTTP request timeout (seconds)
MAX_WORKERS = 20   # Concurrent download threads
```

---

## FAQ

**Q: `start.bat` flashes and disappears with no window?**
A: Right-click → Edit `start.bat`, add `pause` on the last line, save and re-run to see the error. Most common cause: Python is not in PATH.

**Q: "Cannot extract share_id"?**
A: Make sure the copied link contains `shareId=xxxxxxxx`. Paste the full text as-is — the program extracts the ID automatically.

**Q: Download was interrupted. Will it re-download everything?**
A: No. Already-present files are skipped automatically on re-run.

**Q: A file failed to download. What now?**
A: The log shows `[FAIL] filename — error reason`. Fix the issue and re-run — already-downloaded files won't be duplicated.

---

*Python port of [itscj1014/ima-download](https://github.com/itscj1014/ima-download) (original Java version)*