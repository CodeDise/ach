"""
Configuration module for Telegram Auto-Uploader & Channel Aggregator Bot.
Loads configuration from environment variables and provides sensible defaults.
"""

import os
from typing import List, Set
from dotenv import load_dotenv

# Load .env if present
load_dotenv()


def _get_int_list(var_name: str, default: str = "") -> Set[int]:
    val = os.getenv(var_name, default).strip()
    if not val:
        return set()
    result = set()
    for item in val.split(","):
        item = item.strip()
        if item.isdigit() or (item.startswith("-") and item[1:].isdigit()):
            result.add(int(item))
    return result


def _get_str_list(var_name: str, default: str = "") -> List[str]:
    val = os.getenv(var_name, default).strip()
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


class Config:
    # --- Telegram API Credentials ---
    API_ID: int = int(os.getenv("API_ID", "0"))
    API_HASH: str = os.getenv("API_HASH", "").strip()
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

    # --- Admins & Owners ---
    OWNER_ID: int = int(os.getenv("OWNER_ID", "0"))
    ADMIN_IDS: Set[int] = _get_int_list("ADMIN_IDS")
    if OWNER_ID:
        ADMIN_IDS.add(OWNER_ID)

    # --- MongoDB Settings ---
    MONGO_URI: str = os.getenv(
        "MONGO_URI",
        "mongodb://localhost:27017"
    ).strip()
    MONGO_URIS: List[str] = _get_str_list("MONGO_URIS")
    if MONGO_URI and MONGO_URI not in MONGO_URIS:
        MONGO_URIS.insert(0, MONGO_URI)
    DATABASE_NAME: str = os.getenv("DATABASE_NAME", "TelegramAutoUploaderBot").strip()

    # --- External File Storage Bot ---
    EXTERNAL_STORAGE_BOT: str = os.getenv("EXTERNAL_STORAGE_BOT", "").strip().lstrip("@")
    EXTERNAL_DB_CHANNEL_ID: int = int(os.getenv("EXTERNAL_DB_CHANNEL_ID", "0"))
    STORAGE_START_PARAM_FORMAT: str = os.getenv("STORAGE_START_PARAM_FORMAT", "file_{msg_id}").strip()

    # --- Configured Channels ---
    MAIN_CHANNEL_ID: int = int(os.getenv("MAIN_CHANNEL_ID", "0"))
    UPDATE_CHANNEL_ID: int = int(os.getenv("UPDATE_CHANNEL_ID", "0"))
    LOG_CHANNEL_ID: int = int(os.getenv("LOG_CHANNEL_ID", "0"))

    # --- Watermarking Defaults ---
    ENABLE_WATERMARK: bool = os.getenv("ENABLE_WATERMARK", "false").lower() in ("true", "1", "yes")
    WATERMARK_TEXT: str = os.getenv("WATERMARK_TEXT", "@MyChannel").strip()
    WATERMARK_POSITION: str = os.getenv("WATERMARK_POSITION", "bottom-right").strip().lower()
    WATERMARK_FONT_SIZE: int = int(os.getenv("WATERMARK_FONT_SIZE", "28"))
    WATERMARK_FONT_COLOR: str = os.getenv("WATERMARK_FONT_COLOR", "white").strip()

    # --- Weekly Poll Settings ---
    WEEKLY_POLL_TIMEZONE: str = os.getenv("WEEKLY_POLL_TIMEZONE", "Asia/Kolkata").strip()
    WEEKLY_POLL_HOUR: int = int(os.getenv("WEEKLY_POLL_HOUR", "22"))
    WEEKLY_POLL_MINUTE: int = int(os.getenv("WEEKLY_POLL_MINUTE", "0"))

    # --- Default Post Formats ---
    DEFAULT_NORMAL_FORMAT: str = (
        "<b>🎬 {title}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Season:</b> {season} | <b>Episode:</b> {episode}\n"
        "<b>Audio:</b> {audio}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>👇 Select quality to download or stream:</i>"
    )

    DEFAULT_UPDATE_FORMAT: str = (
        "<b>⚡ New Release Alert!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "<b>Title:</b> {title}\n"
        "<b>Season:</b> {season} | <b>Episode:</b> {episode}\n"
        "<b>Audio:</b> {audio}\n"
        "<b>Available Qualities:</b> {qualities}\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "👉 <a href=\"{main_post_link}\">Click here to view episode post</a>"
    )

    # --- Watermark Positions Map ---
    WATERMARK_POSITIONS = {
        "top-left": "x=25:y=25",
        "top-right": "x=w-tw-25:y=25",
        "bottom-left": "x=25:y=h-th-25",
        "bottom-right": "x=w-tw-25:y=h-th-25",
        "center": "x=(w-tw)/2:y=(h-th)/2",
    }
