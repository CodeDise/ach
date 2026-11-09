"""
Media Uploader & Multi-Quality Aggregator module.
Handles incoming video and document media, forwards/uploads to External Storage DB Channel,
generates external bot retrieval links, aggregates multi-quality releases,
and performs real-time dynamic inline button edits on target channel posts.
Includes AsyncIO lock concurrency control and FloodWait protection.
"""

import asyncio
import logging
import os
import tempfile
from typing import Dict, List, Optional
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, MessageNotModified
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from database import db
from handlers.admin import admin_filter
from parser import MetadataParser
from watermark import WatermarkEngine

logger = logging.getLogger(__name__)

# Global aggregation locks dictionary to prevent race conditions during concurrent multi-quality uploads
AGGREGATION_LOCKS: Dict[str, asyncio.Lock] = {}
GLOBAL_UPLOAD_LOCK = asyncio.Lock()


def get_aggregation_lock(slug: str) -> asyncio.Lock:
    """Return an asyncio Lock dedicated to the unique episode/movie slug."""
    if slug not in AGGREGATION_LOCKS:
        AGGREGATION_LOCKS[slug] = asyncio.Lock()
    return AGGREGATION_LOCKS[slug]


def sort_quality_key(quality: str) -> int:
    """Helper to sort quality buttons logically by resolution height."""
    q = quality.lower().strip()
    if "4k" in q or "2160" in q:
        return 2160
    if "1440" in q:
        return 1440
    if "1080" in q:
        return 1080
    if "720" in q:
        return 720
    if "540" in q:
        return 540
    if "480" in q:
        return 480
    if "360" in q:
        return 360
    if "240" in q:
        return 240
    if "144" in q:
        return 144
    return 9999  # Place non-resolution strings like Remux, WEB-DL at the end


def build_quality_keyboard(qualities: Dict[str, Dict[str, str]]) -> InlineKeyboardMarkup:
    """
    Construct sleek inline keyboard buttons labeled strictly by quality name.
    Arranges buttons 2 per row.
    """
    sorted_qualities = sorted(qualities.items(), key=lambda item: sort_quality_key(item[0]))
    keyboard = []
    current_row = []

    for quality_label, data in sorted_qualities:
        url = data.get("url", "")
        # Strictly labeled by its extracted quality name as requested (e.g., [ 720p ])
        btn_text = f"[ {quality_label} ]"
        current_row.append(InlineKeyboardButton(btn_text, url=url))
        if len(current_row) == 2:
            keyboard.append(current_row)
            current_row = []

    if current_row:
        keyboard.append(current_row)

    return InlineKeyboardMarkup(keyboard)


async def safe_edit_markup(client: Client, chat_id: int, message_id: int, markup: InlineKeyboardMarkup):
    """Safely edit inline reply markup with FloodWait management."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await client.edit_message_reply_markup(chat_id, message_id, reply_markup=markup)
            return True
        except FloodWait as e:
            logger.warning("FloodWait of %d seconds on chat %d", e.value, chat_id)
            await asyncio.sleep(e.value + 1)
        except MessageNotModified:
            return True
        except Exception as e:
            logger.error("Failed to edit message reply markup in %d: %s", chat_id, str(e))
            return False
    return False


@Client.on_message(
    filters.private
    & (filters.video | filters.document)
    & admin_filter
)
async def media_upload_handler(client: Client, message: Message):
    """
    Main handler for admin media uploads and forwardings.
    Parses metadata, optionally applies FFmpeg watermark, forwards to storage channel,
    generates external storage bot retrieval link, and aggregates quality buttons.
    """
    # 1. Determine media object and original filename
    media = message.video or message.document
    if not media:
        return

    # Check mime type if document to ensure it's a video file or generic document
    filename = getattr(media, "file_name", "") or "video.mp4"
    caption = message.caption or ""

    status_msg = await message.reply_text("🔍 <b>Processing media file...</b>\n<i>Parsing metadata...</i>")

    # 2. Extract Metadata (dynamic regex, flexible quality support)
    meta = MetadataParser.parse(filename, caption)
    title = meta["title"]
    season = meta["season"]
    episode = meta["episode"]
    audio = meta["audio"]
    quality = meta["quality"]
    slug = meta["slug"]

    logger.info(
        "Extracted Metadata: Title='%s' | Season='%s' | Episode='%s' | Audio='%s' | Quality='%s' | Slug='%s'",
        title, season, episode, audio, quality, slug,
    )

    # 3. Verify Storage Configuration
    settings = await db.get_settings()
    storage_bot = settings.get("external_storage_bot")
    storage_channel_id = settings.get("external_db_channel_id")

    if not storage_bot or not storage_channel_id:
        await status_msg.edit_text(
            "⚠️ <b>External Storage Not Configured:</b>\n\n"
            "Please configure the External Storage Bot and Database Channel first:\n"
            "• <code>/setstoragebot &lt;username&gt;</code>\n"
            "• <code>/setdbchannel &lt;channel_id&gt;</code>"
        )
        return

    # 4. Track title for the Sunday weekly bilingual poll
    await db.add_weekly_title(title=title, season=season, episode=episode)

    # 5. Acquire aggregation lock for this specific show/episode
    slug_lock = get_aggregation_lock(slug)
    async with slug_lock:
        stored_msg_id = None

        # Check Watermarking
        enable_watermark = settings.get("enable_watermark", False)
        if enable_watermark and WatermarkEngine.is_ffmpeg_installed() and message.video:
            await status_msg.edit_text(
                f"📥 <b>Downloading video for watermarking...</b>\n"
                f"<b>Title:</b> {title} ({quality})"
            )
            temp_dir = tempfile.mkdtemp()
            input_path = os.path.join(temp_dir, f"input_{filename}")
            output_path = os.path.join(temp_dir, f"wm_{filename}")

            try:
                # Download file
                await message.download(file_name=input_path)
                await status_msg.edit_text("💧 <b>Applying FFmpeg watermark...</b>")

                wm_text = settings.get("watermark_text", "@MyChannel")
                wm_pos = settings.get("watermark_position", "bottom-right")
                wm_size = int(settings.get("watermark_font_size", 28))
                wm_color = settings.get("watermark_font_color", "white")

                success = await WatermarkEngine.apply_watermark(
                    input_file=input_path,
                    output_file=output_path,
                    text=wm_text,
                    position=wm_pos,
                    font_size=wm_size,
                    font_color=wm_color,
                )

                upload_file = output_path if success else input_path
                await status_msg.edit_text("📤 <b>Uploading watermarked file to Storage Channel...</b>")

                sent_storage_msg = await client.send_video(
                    chat_id=storage_channel_id,
                    video=upload_file,
                    caption=f"{title} - {season}{episode} [{quality}] [{audio}]",
                )
                stored_msg_id = sent_storage_msg.id
            except Exception as e:
                logger.error("Error during watermarking workflow: %s", str(e))
                # Fallback to direct forward if download/watermark fails
                stored_msg = await message.copy(chat_id=storage_channel_id)
                stored_msg_id = stored_msg.id
            finally:
                # Cleanup temporary files
                try:
                    if os.path.exists(temp_dir):
                        for f in os.listdir(temp_dir):
                            os.remove(os.path.join(temp_dir, f))
                        os.rmdir(temp_dir)
                except Exception:
                    pass
        else:
            # Direct forward/copy to storage channel (ultra-fast, zero bandwidth)
            await status_msg.edit_text("🚀 <b>Forwarding file to Storage Database Channel...</b>")
            try:
                stored_msg = await message.copy(chat_id=storage_channel_id)
                stored_msg_id = stored_msg.id
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                stored_msg = await message.copy(chat_id=storage_channel_id)
                stored_msg_id = stored_msg.id
            except Exception as e:
                await status_msg.edit_text(
                    f"❌ <b>Storage Forward Error:</b>\n{str(e)}\n\n"
                    f"Ensure the bot is an Administrator in the storage channel: <code>{storage_channel_id}</code>"
                )
                return

        # 6. Generate External Storage Bot retrieval link
        # Format: https://t.me/ExternalFileStorageBot?start=file_<msg_id>
        start_fmt = settings.get("storage_start_param_format", "file_{msg_id}")
        start_param = start_fmt.replace("{msg_id}", str(stored_msg_id))
        retrieval_link = f"https://t.me/{storage_bot}?start={start_param}"

        # 7. Check if active target channel post exists in database
        existing_post = await db.get_post_by_slug(slug)

        main_channels = await db.get_channels("main")
        if not main_channels and Config.MAIN_CHANNEL_ID:
            main_channels = [{"chat_id": Config.MAIN_CHANNEL_ID}]

        update_channels = await db.get_channels("update")
        if not update_channels and Config.UPDATE_CHANNEL_ID:
            update_channels = [{"chat_id": Config.UPDATE_CHANNEL_ID}]

        if not main_channels:
            await status_msg.edit_text(
                "⚠️ <b>No Target Main Channel linked:</b>\n"
                "Please configure a target channel using: <code>/setchannel &lt;chat_id&gt;</code>\n\n"
                f"<i>File saved to storage with link:</i>\n{retrieval_link}"
            )
            return

        if existing_post:
            # =================================================================
            # MULTI-QUALITY AGGREGATION: EXISTING POST FOUND -> DYNAMIC EDIT
            # =================================================================
            await status_msg.edit_text(
                f"🔄 <b>Existing post found for {title} {season}{episode}!</b>\n"
                f"Appending new quality button: <b>[ {quality} ]</b>..."
            )

            qualities = existing_post.get("qualities", {})
            qualities[quality] = {
                "url": retrieval_link,
                "storage_msg_id": stored_msg_id,
            }

            # Build updated inline keyboard containing all qualities
            updated_keyboard = build_quality_keyboard(qualities)

            main_post_records = existing_post.get("main_posts", [])
            for post_ref in main_post_records:
                chat_id = post_ref.get("channel_id")
                msg_id = post_ref.get("message_id")
                # Dynamically edit reply markup WITHOUT rewriting caption or reposting!
                await safe_edit_markup(client, chat_id, msg_id, updated_keyboard)

            # Update database record
            await db.save_aggregated_post(
                slug=slug,
                title=title,
                season=season,
                episode=episode,
                audio=audio,
                qualities=qualities,
                main_posts=main_post_records,
                update_posts=existing_post.get("update_posts", []),
            )

            # Send update alert to Update Channels
            quality_list_str = ", ".join(f"[{q}]" for q in qualities.keys())
            first_main_post = main_post_records[0] if main_post_records else {}
            main_link = ""
            if first_main_post:
                cid_str = str(first_main_post.get("channel_id")).replace("-100", "")
                main_link = f"https://t.me/c/{cid_str}/{first_main_post.get('message_id')}"

            update_fmt = settings.get("update_format", Config.DEFAULT_UPDATE_FORMAT)
            update_text = update_fmt.format(
                title=title,
                season=season,
                episode=episode,
                audio=audio,
                qualities=quality_list_str,
                main_post_link=main_link or retrieval_link,
            )

            for uch in update_channels:
                try:
                    await client.send_message(
                        chat_id=uch["chat_id"],
                        text=update_text,
                        disable_web_page_preview=True,
                    )
                except Exception as e:
                    logger.warning("Could not dispatch update alert to %s: %s", uch["chat_id"], str(e))

            await status_msg.edit_text(
                f"✅ <b>Successfully Aggregated New Quality!</b>\n\n"
                f"• <b>Title:</b> {title}\n"
                f"• <b>Season / Episode:</b> {season} | {episode}\n"
                f"• <b>Added Quality:</b> <code>{quality}</code>\n"
                f"• <b>All Qualities:</b> {quality_list_str}\n"
                f"• <b>Direct Link:</b> <a href=\"{retrieval_link}\">Storage Retrieval</a>\n\n"
                f"<i>Existing channel post inline buttons were dynamically updated!</i>",
                disable_web_page_preview=True,
            )

        else:
            # =================================================================
            # NO EXISTING POST: CREATE CLEAN POST WITH INITIAL QUALITY BUTTON
            # =================================================================
            await status_msg.edit_text(
                f"✨ <b>Creating initial channel post for {title} {season}{episode}...</b>"
            )

            qualities = {
                quality: {
                    "url": retrieval_link,
                    "storage_msg_id": stored_msg_id,
                }
            }
            initial_keyboard = build_quality_keyboard(qualities)

            # Check if custom poster is configured
            poster = await db.get_poster(title)

            # Format caption with custom normal format
            normal_fmt = settings.get("normal_format", Config.DEFAULT_NORMAL_FORMAT)
            formatted_caption = normal_fmt.format(
                title=title,
                season=season,
                episode=episode,
                audio=audio,
                quality=quality,
            )

            main_post_records = []

            for mch in main_channels:
                cid = mch["chat_id"]
                try:
                    if poster:
                        media_file_id = poster.get("file_id")
                        media_type = poster.get("media_type", "photo")
                        if media_type == "photo":
                            sent_p = await client.send_photo(
                                chat_id=cid,
                                photo=media_file_id,
                                caption=formatted_caption,
                                reply_markup=initial_keyboard,
                            )
                        else:
                            sent_p = await client.send_document(
                                chat_id=cid,
                                document=media_file_id,
                                caption=formatted_caption,
                                reply_markup=initial_keyboard,
                            )
                    else:
                        sent_p = await client.send_message(
                            chat_id=cid,
                            text=formatted_caption,
                            reply_markup=initial_keyboard,
                            disable_web_page_preview=True,
                        )

                    main_post_records.append({
                        "channel_id": cid,
                        "message_id": sent_p.id,
                        "type": "main",
                    })
                except Exception as e:
                    logger.error("Failed to publish initial post to %s: %s", cid, str(e))

            # Send Update Channel alert
            first_main_post = main_post_records[0] if main_post_records else {}
            main_link = ""
            if first_main_post:
                cid_str = str(first_main_post.get("channel_id")).replace("-100", "")
                main_link = f"https://t.me/c/{cid_str}/{first_main_post.get('message_id')}"

            update_fmt = settings.get("update_format", Config.DEFAULT_UPDATE_FORMAT)
            update_text = update_fmt.format(
                title=title,
                season=season,
                episode=episode,
                audio=audio,
                qualities=f"[{quality}]",
                main_post_link=main_link or retrieval_link,
            )

            update_post_records = []
            for uch in update_channels:
                try:
                    sent_u = await client.send_message(
                        chat_id=uch["chat_id"],
                        text=update_text,
                        disable_web_page_preview=True,
                    )
                    update_post_records.append({
                        "channel_id": uch["chat_id"],
                        "message_id": sent_u.id,
                        "type": "update",
                    })
                except Exception as e:
                    logger.warning("Could not dispatch update alert to %s: %s", uch["chat_id"], str(e))

            # Save in database
            await db.save_aggregated_post(
                slug=slug,
                title=title,
                season=season,
                episode=episode,
                audio=audio,
                qualities=qualities,
                main_posts=main_post_records,
                update_posts=update_post_records,
            )

            await status_msg.edit_text(
                f"✅ <b>Initial Channel Post Created Successfully!</b>\n\n"
                f"• <b>Title:</b> {title}\n"
                f"• <b>Season / Episode:</b> {season} | {episode}\n"
                f"• <b>Initial Quality:</b> <code>{quality}</code>\n"
                f"• <b>Poster Attached:</b> {'Yes' if poster else 'No'}\n"
                f"• <b>Direct Link:</b> <a href=\"{retrieval_link}\">Storage Retrieval</a>\n\n"
                f"<i>Future quality uploads for this episode will automatically attach buttons here!</i>",
                disable_web_page_preview=True,
            )
