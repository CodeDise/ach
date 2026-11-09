# 🚀 Telegram Auto-Uploader & Channel Aggregator Bot

A production-ready, highly efficient, and scalable Telegram Auto-Uploader & Channel Aggregator Bot built using **Python 3.11+**, **Pyrogram v2+**, **Motor (Async MongoDB)**, **AsyncIO**, and **APScheduler**.

Designed specifically for anime, series, and movie distribution channels requiring zero-duplication multi-quality releases, external file store integration, automated Sunday bilingual polls, dynamic FFmpeg watermarking, and resilient multi-cluster MongoDB failover.

---

## 📋 Table of Contents
1. [Core Architectural Highlights](#-core-architectural-highlights)
2. [Critical Constraints & Standards](#-critical-constraints--standards)
3. [Feature Breakdown](#-feature-breakdown)
   - [External File Storage Bot Integration](#1-external-file-storage-bot-integration)
   - [Dynamic Regex Metadata Parsing & Flexible Quality](#2-dynamic-regex-metadata-parsing--flexible-quality)
   - [Multi-Quality Aggregation & Live Inline Editing](#3-multi-quality-aggregation--live-inline-editing)
   - [Channel Setup, Formats & Poster Mapping](#4-channel-setup-formats--poster-mapping)
   - [FFmpeg Watermarking & Visual Preview](#5-ffmpeg-watermarking--visual-preview)
   - [Automatic Private Channel Invite Link Generation](#6-automatic-private-channel-invite-link-generation)
   - [Automated Sunday Bilingual Poll](#7-automated-sunday-bilingual-poll)
   - [MongoDB Multi-Cluster Redundancy & Telemetry](#8-mongodb-multi-cluster-redundancy--telemetry)
   - [Admin Control Panel & User Promotion](#9-admin-control-panel--user-promotion)
4. [Command Reference](#-command-reference)
5. [Environment Variables](#-environment-variables)
6. [Installation & Deployment](#-installation--deployment)
7. [Pushing to GitHub](#-pushing-to-github)

---

## 🌟 Core Architectural Highlights

- **Modular Architecture**:
  - `bot.py`: Main entry point, Pyrogram Client lifecycle, invite link generator, startup sync.
  - `config.py`: Environment variable loader, default templates, constants.
  - `database.py`: Motor Async MongoDB engine with transparent multi-cluster failover and collection helpers.
  - `parser.py`: Regex extraction engine supporting customizable bracket formats and scene naming conventions.
  - `watermark.py`: FFmpeg overlay processing and visual preview frame generator.
  - `scheduler.py`: APScheduler Sunday 10:00 PM IST cron job runner.
  - `handlers/admin.py`: Comprehensive admin commands without underscores.
  - `handlers/uploader.py`: Media upload processor, lock concurrency controller, dynamic keyboard editor.
  - `handlers/callbacks.py`: Centralized callback router for interactive inline dashboards.
- **Race Condition Prevention**: Uses per-slug `asyncio.Lock()` to process multiple simultaneous quality uploads of the exact same episode sequentially without button conflicts.
- **FloodWait Shield**: Wraps Telegram API operations in automatic exponential backoff retry loops.

---

## ⚡ Critical Constraints & Standards

1. **NO Underscores in Commands**:
   All Telegram commands strictly follow alphanumeric or single-word formatting (e.g. `/addadmin`, `/setchannel`, `/setposter`, `/adddb`, `/deldb`, `/dbstatus`, `/clearall`).
2. **Strict English Localization**:
   All prompts, command menus, help texts, logs, and button labels are 100% English (except the designated bilingual Sunday poll).
3. **Dynamic Admin Persistence**:
   Admins added via `/addadmin` are saved in MongoDB and automatically cached in memory on bot startup for instant filter verification.

---

## 🛠 Feature Breakdown

### 1. External File Storage Bot Integration
- When media is received, the bot stores it in a designated File Storage Database Channel (`EXTERNAL_DB_CHANNEL_ID`).
- Retrieves the storage message ID and dynamically constructs direct start links referencing the external File Storage Bot:
  ```
  https://t.me/<ExternalFileStorageBot>?start=file_<message_id>
  ```
- No internal link database required. Fully compatible with standard external Telegram file store bots.

### 2. Dynamic Regex Metadata Parsing & Flexible Quality
- Parses both bracket structures (e.g., `[Jujutsu Kaisen] [S02] [E05] [Hindi-Eng] [720p].mkv`) and standard scene formats (`Demon.Slayer.S04E08.720p.WEB-DL.Hindi.mkv`).
- **Flexible Quality**: Extracts **ANY** resolution string (e.g., `240p`, `360p`, `480p`, `540p`, `720p`, `1080p`, `1440p`, `2160p`, `4K`, `Remux`, `WEB-DL`, `BluRay`, `HDRip`, `CAMRip`). Does **NOT** filter, restrict, or hardcode qualities.

### 3. Multi-Quality Aggregation & Live Inline Editing
- Groups uploads matching the same `(title, season, episode)`:
  - **First Quality Received**: Publishes the initial formatted post to Target Main Channels with an inline button strictly labeled by its quality (e.g., `[ 720p ]`).
  - **Subsequent Qualities Received**: Edits the existing post's inline keyboard via `edit_message_reply_markup` without reposting, duplicating content, or altering the caption.

### 4. Channel Setup, Formats & Poster Mapping
- Link Target Main Channels (`/setchannel`) and Update Channels (`/setupdatechannel`).
- Displays an inline prompt upon setting a channel to assign custom posters immediately.
- Custom formats:
  - **Normal Format**: Caption template for Main Channel posts (`/setnormalformat`).
  - **Update Format**: Alert template for Update Channel posts (`/setupdateformat`).
- Poster Assignment:
  - Send `/setposter <Title>` and reply with the poster image (Photo or Document). Auto-detects media format.

### 5. FFmpeg Watermarking & Visual Preview
- Global toggle to enable or disable FFmpeg watermarking.
- Watermark positions: `top-left`, `top-right`, `bottom-left`, `bottom-right`, `center`.
- Visual preview generator (`/previewwm`): Produces a real sample frame so admins can check placement and font size before enabling.

### 6. Automatic Private Channel Invite Link Generation
- Ensures bot has `Invite Users via Link` permissions.
- Automatically exports or generates private invite links for linked private channels to enable tracking and button links.

### 7. Automated Sunday Bilingual Poll
- Scheduled via APScheduler to execute **every Sunday at 10:00 PM IST (22:00 IST)**.
- Tracks all unique titles uploaded from Sunday to Sunday in MongoDB.
- Posts a bilingual poll to linked Update Channels:
  ```
  [English] What was your favorite episode this week?
  [Hindi] इस हफ्ते का आपका पसंदीदा एपिसोड कौन सा था?
  ```
- Handles split polls if titles exceed Telegram's 10-option limit.
- Resets the weekly tracking list after publishing.

### 8. MongoDB Multi-Cluster Redundancy & Telemetry
- Supports a pool of MongoDB URIs with automatic failover.
- `/adddb <uri>` and `/deldb <uri>` to modify cluster nodes dynamically.
- `/dbstatus`: Displays live ping latency (ms), active cluster node, and record counts for admins, channels, posts, posters, and weekly poll titles.
- `/clearall`: Secure data wipe dialog with confirmation prompt.

---

## ⌨️ Command Reference

| Command | Description |
| :--- | :--- |
| `/start` | Launch bot and view status / admin dashboard |
| `/help` | Detailed command help guide |
| `/adminpanel` | Interactive visual admin control panel |
| `/addadmin <id/uname>` | Grant admin privileges |
| `/deladmin <id/uname>` | Revoke admin privileges |
| `/adminlist` | View all registered administrators |
| `/setchannel <id>` | Link Target Main Channel |
| `/delchannel <id>` | Unlink Target Main Channel |
| `/setupdatechannel <id>` | Link Update Channel |
| `/delupdatechannel <id>` | Unlink Update Channel |
| `/channellist` | View all configured channels and invite links |
| `/setposter <Title>` | Map poster photo/document to a title |
| `/delposter <Title>` | Remove poster mapping |
| `/posterlist` | List all assigned title posters |
| `/setnormalformat` | Configure Main Channel caption template |
| `/setupdateformat` | Configure Update Channel alert template |
| `/setstoragebot <uname>` | Configure External File Storage Bot |
| `/setdbchannel <id>` | Configure External Storage Database Channel |
| `/watermark` | Watermark settings and toggle menu |
| `/previewwm` | Render live sample visual watermark preview |
| `/adddb <uri>` | Add redundant MongoDB cluster URI |
| `/deldb <uri>` | Remove MongoDB cluster URI |
| `/dbstatus` | Live database telemetry, latency, and record counts |
| `/clearall` | Wipe all channels, posts, posters, and tracked data |
| `/pollnow` | Manually dispatch the Sunday bilingual poll |
| `/stats` | View bot system statistics |

---

## ⚙️ Environment Variables

Create a `.env` file in the project root:

```env
API_ID=12345678
API_HASH=0123456789abcdef0123456789abcdef
BOT_TOKEN=1234567890:ABCdefGhIJKlmNoPQRsTUVwxyZ

OWNER_ID=123456789
ADMIN_IDS=123456789,987654321

MONGO_URI=mongodb+srv://user:pass@cluster0.mongodb.net/?retryWrites=true&w=majority
MONGO_URIS=mongodb+srv://user:pass@cluster1.mongodb.net/?retryWrites=true&w=majority
DATABASE_NAME=TelegramAutoUploaderBot

EXTERNAL_STORAGE_BOT=ExternalFileStorageBot
EXTERNAL_DB_CHANNEL_ID=-1001234567890
STORAGE_START_PARAM_FORMAT=file_{msg_id}

MAIN_CHANNEL_ID=
UPDATE_CHANNEL_ID=
LOG_CHANNEL_ID=

ENABLE_WATERMARK=false
WATERMARK_TEXT=@MyTelegramChannel
WATERMARK_POSITION=bottom-right
WATERMARK_FONT_SIZE=28
WATERMARK_FONT_COLOR=white

WEEKLY_POLL_TIMEZONE=Asia/Kolkata
WEEKLY_POLL_HOUR=22
WEEKLY_POLL_MINUTE=0
```

---

## 🚀 Installation & Deployment

### Local / VPS Setup

1. **Clone repository**:
   ```bash
   git clone <YOUR_GITHUB_REPO_URL>
   cd <REPO_FOLDER>
   ```

2. **Create Python virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install FFmpeg** (Optional, for video watermarking):
   ```bash
   sudo apt-get update && sudo apt-get install -y ffmpeg
   ```

5. **Configure environment**:
   ```bash
   cp .env.example .env
   nano .env  # fill in your credentials
   ```

6. **Run the bot**:
   ```bash
   python3 bot.py
   ```

---

## 📦 Pushing to GitHub

To push this codebase to your GitHub repository:

```bash
# 1. Initialize git (if not already initialized)
git init

# 2. Add all files and make initial commit
git add .
git commit -m "feat: complete Telegram Auto-Uploader & Channel Aggregator Bot"

# 3. Set branch to main
git branch -M main

# 4. Link your GitHub repository remote
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPOSITORY>.git

# 5. Push to GitHub
git push -u origin main
```
