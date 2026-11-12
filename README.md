# IMA Knowledge Base Downloader v1.0.8

A desktop tool: paste an IMA Knowledge Base share link → log in with a WeChat QR scan → download **every file as its full original** (PDF / Word / images), each byte-verified and page-counted. No ima client, no OpenAPI credentials — just double-click `start.bat`.

> **[中文版使用说明，请点击这里](./README_zh.md)**

---

## What's different in v1.0.8

Older versions (v1.0.4 – v1.0.7) worked around server restrictions: OpenAPI credentials only worked for bases you created, anonymous mode only got first-page preview images, and the harvest channel depended on signatures left behind by the ima desktop client. **v1.0.8 takes a different route**: it replicates the ima web login (WeChat QR) and then mints per-item **original-file** URLs through the same encrypted-envelope protocol the web client uses — no previews, no desktop client, no credential pasting.

- 📱 **WeChat QR login**: one click, one scan; the token auto-renews, rescan only when it expires
- 📋 Paste a share link — `share_id` extracted automatically
- 📁 Recursive traversal; the output folder mirrors the knowledge base exactly
- ⬇️ **Originals only**: complete PDFs (not cover images), complete .docx files, original image bytes
- 🔬 **Verify on download**: every finished file is byte-compared against the server-reported size; PDFs parsed with `pypdf` for page counts, Word files checked as containers, images checked by magic bytes
- 📄 A per-file verify report lands next to the download (`_v108_原件校验报告.json`), and every run ends with `originals N · skipped M · failed 0 · PDF pages P · X MB`
- 🔄 Incremental: existing verified files are skipped automatically
- ⚡ Multi-threaded (8 workers by default, toggleable)
- 🌙 Dark theme, bilingual UI (中/EN)

---

## Quick Start

### 1. Install Python

Requires **Python 3.8+** — check **`Add Python to PATH`** during install (<https://www.python.org/downloads/>).

### 2. Launch

**Windows:** double-click **`start.bat`** (first run auto-installs `requests` / `cryptography` / `pypdf`).

**macOS / Linux:**

```bash
pip install requests cryptography pypdf
python gui.py
```

### 3. Use

1. Open the IMA knowledge base → **Share → Copy Link**
2. Double-click `start.bat`, paste the link into the input box
3. First time: click **"📱 QR Login"** — the QR image opens automatically; scan it with WeChat and confirm on your phone (the session is saved locally to `ima_session.json`; you rarely need to scan again)
4. Click **"▶ Start Download"**

The finish line reads: `originals N · skipped M · failed 0 · PDF pages P · X MB`, plus a per-file verify report.

---

## How it works (v1.0.8)

1. **QR login**: the exact WeChat OAuth flow of ima.qq.com (qrconnect → long-poll → `auth_login/login`), yielding an IMA-TOKEN (2 h validity, auto-renewed)
2. **Traversal**: `knowledge_share_get/get_share_info` walks every folder and collects all `media_id`s
3. **Minting**: the `file_manager/get_media` encrypted-envelope protocol (AES-128-GCM body + RSA-OAEP key wrap) exchanges each `media_id` for a signed direct URL to the original
4. **Download + verify**: concurrent download into a folder named after the knowledge base; per-file byte comparison + format parsing (pypdf pages / Office container / image magic)

> The session ticket is stored in plaintext at `ima_session.json` next to the tool — local only, **do not share it**.

---

## FAQ

**Q: Why the QR scan? Can I skip it?**
A: No — the server only signs original-file URLs for logged-in users (anonymous requests get first-page previews; that was the whole v1.0.7-era problem). After one scan the token auto-renews, so rescans are rare.

**Q: It says "please log in first" / my login expired.**
A: Click "📱 QR Login" and scan once more. Already-downloaded files won't be touched.

**Q: A run was interrupted — will it re-download everything?**
A: No. Files that exist with the right size are skipped (and re-verified in place); only missing ones are fetched.

**Q: A file failed. Now what?**
A: The log shows the reason; just run again. Failures are pinned at the top of the verify report.

**Q: "Cannot extract share_id"?**
A: Paste the entire share text IMA gives you — the ID is extracted automatically.

**Q: Where is the verify report?**
A: `_v108_原件校验报告.json` inside the knowledge-base folder — per-file bytes, pages, and verdicts.

---

## Project Structure

```
.
├── gui.py             # GUI entry (v1.0.8 QR login + originals pipeline)
├── ima_auth.py        # WeChat QR login / token auto-renewal
├── original_minter.py # Encrypted-envelope minting + download + verification
├── traverser.py       # Recursive share traversal
├── downloader.py      # File download engine (used by the pipeline)
├── models.py          # Data models
├── api_service.py     # IMA share API
├── main.py            # CLI entry (optional)
├── requirements.txt   # requests / cryptography / pypdf
├── start.bat          # Launcher
└── README.md          # This file
```

> `sync_manager.py` / `client_harvest.py` / `probe_openapi.py` are leftovers from the old channels and have been removed from the repo in v1.0.8; `downloader.py` remains a dependency of the traversal-download pipeline.

---

## Version history (one-liners)

- **v1.0.8**: QR login + encrypted-envelope originals, full byte/page verification (current)
- v1.0.7: ima desktop-client signature harvest channel
- v1.0.6: byte-verify on completion
- v1.0.4–v1.0.5: OpenAPI credential dual-engine + anonymous fallback chain
- v1.0.3 and earlier: anonymous direct download (dead after the server policy change)

---

*Python port of [itscj1014/ima-download](https://github.com/itscj1014/ima-download) (original Java version)*
