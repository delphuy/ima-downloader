# IMA Knowledge Base Downloader

A cross-platform desktop tool to recursively download files from IMA Knowledge Base via share links — no install required, just double-click `start.bat`.

> **[中文版使用说明，请点击这里](./README_zh.md)**

---

## Features

- 📋 Paste a share link — `share_id` extracted automatically
- 📁 Recursive traversal grouped by top-level categories (parallel categories, sequential within category)
- ⚡ Smart concurrency + browser "Print to PDF" for link-type content
- 🔄 Incremental download
- 🎨 Modern clean GUI (ttk styled, progress bar)
- 🌙 Dark theme, one-click start.bat

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

**Windows:**  
Double-click **`start.bat`**. On first run it will:
1. Check Python availability
2. Install the `requests` dependency (one-time only)
3. Open the GUI

Subsequent runs: just double-click `start.bat` — done.

**macOS / Linux:**  
Open Terminal, navigate to the project folder, then run:

```bash
# First run (install dependencies)
pip install requests

# Launch the GUI
python gui.py
```

Or create a shell script for one-click launch:

```bash
# Create start.sh
echo '#!/bin/bash' > start.sh
echo 'pip install requests -q' >> start.sh
echo 'python gui.py' >> start.sh
chmod +x start.sh

# Run
./start.sh
```

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
├── gui.py           # Modern GUI (ttk)
├── api_service.py   # IMA API wrapper
├── downloader.py    # Download engine (grouped concurrency + PDF print)
├── models.py        # Data models
├── traverser.py     # Collection + grouping
├── sync_manager.py  # CLI
├── main.py          # CLI entry
├── requirements.txt # requests only
├── start.bat        # Launcher
└── README.md        # This file
```

---

## Configuration

Edit `downloader.py` for advanced tuning:

```python
TIMEOUT = 30                  # HTTP timeout
MAX_WORKERS = 20              # File threads
MAX_CATEGORY_WORKERS = 6      # Parallel categories (sequential inside each)
```

---

## FAQ

**Q: `start.bat` flashes and disappears with no window?**
A: Common causes:
1. Python was installed without tcl/tk (reinstall and check "tcl/tk and IDLE").
2. Silent error.
   - Edit start.bat and add `pause` at the end, or run `python gui.py` directly from console to see errors.
The launcher now has better fallback and the GUI shows a message box on fatal errors.

**Q: "Cannot extract share_id"?**
A: Make sure the copied link contains `shareId=xxxxxxxx`. Paste the full text as-is — the program extracts the ID automatically.

**Q: Download was interrupted. Will it re-download everything?**
A: No. Already-present files are skipped automatically on re-run.

**Q: A file failed to download. What now?**
A: The log shows `[FAIL] filename — error reason`. Fix the issue and re-run — already-downloaded files won't be duplicated.

**Q: What about link/URL content?**
A: It prefers to "print" the page to PDF using headless browser (like Ctrl+P → Save as PDF). Falls back to a clickable .url shortcut if it fails (e.g. verification page).

**Q: Faster for large collections?**
A: Yes — files are grouped by top-level category. Same category downloads in one thread; different categories run in parallel (default max 6 categories).

---

*Python port of [itscj1014/ima-download](https://github.com/itscj1014/ima-download) (original Java version)*