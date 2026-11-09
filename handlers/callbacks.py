"""
Callback Query Handlers module.
Manages all interactive inline keyboard navigation, toggles, confirmation prompts,
watermark position menus, and live status refreshes.
Strictly English localized.
"""

import logging
import os
from pyrogram import Client
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from config import Config
from database import db
from scheduler import poll_scheduler
from watermark import WatermarkEngine

logger = logging.getLogger(__name__)


@Client.on_callback_query()
async def callback_router(client: Client, query: CallbackQuery):
    """Central router for inline callback buttons."""
    user_id = query.from_user.id
    if not db.is_admin(user_id):
        await query.answer("⛔ Access Denied: Administrator privileges required.", show_alert=True)
        return

    data = query.data

    # --- Close Window ---
    if data == "admin:close":
        await query.message.delete()
        return

    # --- Main Dashboard ---
    if data == "admin:menu":
        settings = await db.get_settings()
        text = (
            "<b>🎛 Administrator Control Panel</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>External Storage Bot:</b> @{settings.get('external_storage_bot') or 'Not Set'}\n"
            f"<b>Storage DB Channel:</b> <code>{settings.get('external_db_channel_id') or 'Not Set'}</code>\n"
            f"<b>Watermark Status:</b> {'🟢 Enabled' if settings.get('enable_watermark') else '🔴 Disabled'}\n"
            f"<b>Watermark Position:</b> <code>{settings.get('watermark_position', 'bottom-right')}</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Select an option below to manage bot configurations:"
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📢 Channels", callback_data="admin:channels"),
                InlineKeyboardButton("🖼 Posters", callback_data="admin:posters"),
            ],
            [
                InlineKeyboardButton("🤖 Storage Bot", callback_data="admin:storage"),
                InlineKeyboardButton("💧 Watermark", callback_data="admin:watermark"),
            ],
            [
                InlineKeyboardButton("🗄 Database", callback_data="admin:dbstatus"),
                InlineKeyboardButton("👥 Admins", callback_data="admin:admins"),
            ],
            [
                InlineKeyboardButton("📊 System Stats", callback_data="admin:stats"),
                InlineKeyboardButton("🗳 Test Weekly Poll", callback_data="admin:pollnow"),
            ],
            [
                InlineKeyboardButton("⚠️ Wipe All Data", callback_data="admin:clearall:prompt"),
                InlineKeyboardButton("❌ Close Panel", callback_data="admin:close"),
            ],
        ])
        await query.message.edit_text(text, reply_markup=markup)
        await query.answer()
        return

    # --- Channels Sub-Menu ---
    if data == "admin:channels":
        channels = await db.get_channels()
        lines = ["<b>📢 Configured Channels:</b>\n"]
        for c in channels:
            ctype = c.get("type", "main").upper()
            title = c.get("title", "Untitled")
            cid = c.get("chat_id")
            link = c.get("invite_link") or (f"@{c.get('username')}" if c.get("username") else "No Link")
            lines.append(f"• <b>[{ctype}]</b> {title} (<code>{cid}</code>)\n  🔗 {link}\n")

        if not channels:
            lines.append("<i>No channels linked yet.</i>\n")

        lines.append("\n<b>Commands:</b>\n• <code>/setchannel &lt;chat_id&gt;</code>\n• <code>/setupdatechannel &lt;chat_id&gt;</code>")

        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin:menu")]
        ])
        await query.message.edit_text("\n".join(lines), reply_markup=markup, disable_web_page_preview=True)
        await query.answer()
        return

    # --- Posters Sub-Menu ---
    if data in ("admin:posters", "admin:posters:prompt"):
        posters = await db.get_all_posters()
        lines = ["<b>🖼 Custom Media Posters:</b>\n"]
        for p in posters:
            lines.append(f"• <b>{p.get('title')}</b> ({p.get('media_type', 'photo').title()})")

        if not posters:
            lines.append("<i>No custom posters registered yet.</i>\n")

        lines.append(
            "\n<b>How to Assign a Poster:</b>\n"
            "Send <code>/setposter &lt;Title&gt;</code> and reply with the poster image (Photo or Document).\n"
            "To remove: <code>/delposter &lt;Title&gt;</code>"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin:menu")]
        ])
        await query.message.edit_text("\n".join(lines), reply_markup=markup)
        await query.answer()
        return

    # --- Storage Bot Sub-Menu ---
    if data == "admin:storage":
        settings = await db.get_settings()
        bot_uname = settings.get("external_storage_bot") or "Not Configured"
        db_cid = settings.get("external_db_channel_id") or "Not Configured"
        param_fmt = settings.get("storage_start_param_format", "file_{msg_id}")

        text = (
            "<b>🤖 External File Storage Bot Setup</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Bot Username:</b> @{bot_uname}\n"
            f"<b>Storage DB Channel:</b> <code>{db_cid}</code>\n"
            f"<b>URL Start Format:</b> <code>https://t.me/{bot_uname}?start={param_fmt}</code>\n\n"
            "<b>Configuration Commands:</b>\n"
            "• <code>/setstoragebot &lt;username&gt;</code>\n"
            "• <code>/setdbchannel &lt;channel_id&gt;</code>"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin:menu")]
        ])
        await query.message.edit_text(text, reply_markup=markup)
        await query.answer()
        return

    # --- Admins Sub-Menu ---
    if data == "admin:admins":
        admins = await db.get_all_admins()
        lines = ["<b>👥 Registered Administrators:</b>\n"]
        lines.append(f"👑 <b>Owner:</b> <code>{Config.OWNER_ID}</code>\n")
        for a in admins:
            uid = a.get("user_id")
            uname = a.get("username")
            display = f"@{uname}" if uname else f"ID: {uid}"
            lines.append(f"• <code>{uid}</code> ({display})")

        lines.append("\n<b>Commands:</b>\n• <code>/addadmin &lt;id/username&gt;</code>\n• <code>/deladmin &lt;id/username&gt;</code>")
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin:menu")]
        ])
        await query.message.edit_text("\n".join(lines), reply_markup=markup)
        await query.answer()
        return

    # --- System Stats ---
    if data == "admin:stats":
        status = await db.get_db_status()
        counts = status.get("counts", {})
        text = (
            "<b>📊 System Statistics Overview</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Total Admins:</b> {counts.get('admins', 0)}\n"
            f"• <b>Linked Main Channels:</b> {counts.get('channels', 0)}\n"
            f"• <b>Linked Update Channels:</b> {counts.get('update_channels', 0)}\n"
            f"• <b>Aggregated Episode Posts:</b> {counts.get('posts', 0)}\n"
            f"• <b>Assigned Posters:</b> {counts.get('posters', 0)}\n"
            f"• <b>Weekly Tracked Titles:</b> {counts.get('weekly_titles', 0)}\n"
            f"• <b>Database Latency:</b> {status.get('latency_ms')} ms\n"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin:menu")]
        ])
        await query.message.edit_text(text, reply_markup=markup)
        await query.answer()
        return

    # --- Live Database Telemetry ---
    if data == "admin:dbstatus":
        status = await db.get_db_status()
        counts = status.get("counts", {})
        text = (
            "<b>🗄 MongoDB Multi-Cluster Telemetry</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Connection State:</b> {'🟢 Online' if status['status'] == 'Online' else '🔴 Offline'}\n"
            f"<b>Active Node:</b> <code>{status['active_node']}</code>\n"
            f"<b>Active Node Index:</b> [{status['node_index']} / {status['total_nodes']}]\n"
            f"<b>Ping Latency:</b> <code>{status['latency_ms']} ms</code>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "<b>📊 Record Counters:</b>\n"
            f"• <b>Admins:</b> {counts.get('admins', 0)}\n"
            f"• <b>Main Channels:</b> {counts.get('channels', 0)}\n"
            f"• <b>Update Channels:</b> {counts.get('update_channels', 0)}\n"
            f"• <b>Aggregated Posts:</b> {counts.get('posts', 0)}\n"
            f"• <b>Custom Posters:</b> {counts.get('posters', 0)}\n"
            f"• <b>Weekly Poll Titles:</b> {counts.get('weekly_titles', 0)}"
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh Telemetry", callback_data="admin:dbstatus")],
            [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin:menu")],
        ])
        await query.message.edit_text(text, reply_markup=markup)
        await query.answer("Database telemetry refreshed.")
        return

    # --- Watermark Sub-Menu ---
    if data == "admin:watermark":
        settings = await db.get_settings()
        is_enabled = settings.get("enable_watermark", False)
        pos = settings.get("watermark_position", "bottom-right")
        wm_text = settings.get("watermark_text", "@MyChannel")
        font_size = settings.get("watermark_font_size", 28)

        text = (
            "<b>💧 FFmpeg Watermarking Configuration</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Status:</b> {'🟢 Enabled' if is_enabled else '🔴 Disabled'}\n"
            f"<b>Overlay Text:</b> <code>{wm_text}</code>\n"
            f"<b>Position:</b> <code>{pos}</code>\n"
            f"<b>Font Size:</b> <code>{font_size}</code>\n"
            f"<b>FFmpeg Installed:</b> {'✅ Yes' if WatermarkEngine.is_ffmpeg_installed() else '⚠️ No'}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "Select an option below to toggle or adjust watermark settings:"
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "🔴 Disable Watermark" if is_enabled else "🟢 Enable Watermark",
                    callback_data="wm:toggle",
                )
            ],
            [
                InlineKeyboardButton("📍 Set Position", callback_data="wm:position:menu"),
                InlineKeyboardButton("👁 Visual Preview", callback_data="wm:preview"),
            ],
            [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin:menu")],
        ])
        await query.message.edit_text(text, reply_markup=markup)
        await query.answer()
        return

    # --- Watermark Toggle ---
    if data == "wm:toggle":
        settings = await db.get_settings()
        current = settings.get("enable_watermark", False)
        new_val = not current
        await db.update_settings({"enable_watermark": new_val})
        await query.answer(f"Watermark {'Enabled' if new_val else 'Disabled'}")
        # Refresh watermark menu
        query.data = "admin:watermark"
        await callback_router(client, query)
        return

    # --- Watermark Position Menu ---
    if data == "wm:position:menu":
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Top-Left", callback_data="wm:pos:top-left"),
                InlineKeyboardButton("Top-Right", callback_data="wm:pos:top-right"),
            ],
            [InlineKeyboardButton("Center", callback_data="wm:pos:center")],
            [
                InlineKeyboardButton("Bottom-Left", callback_data="wm:pos:bottom-left"),
                InlineKeyboardButton("Bottom-Right", callback_data="wm:pos:bottom-right"),
            ],
            [InlineKeyboardButton("🔙 Back to Watermark", callback_data="admin:watermark")],
        ])
        await query.message.edit_text(
            "<b>📍 Select Watermark Position:</b>\n\n"
            "Choose which corner or location the watermark should be placed:",
            reply_markup=markup,
        )
        await query.answer()
        return

    # --- Watermark Position Selection ---
    if data.startswith("wm:pos:"):
        new_pos = data.split(":", 2)[2]
        await db.update_settings({"watermark_position": new_pos})
        await query.answer(f"Position set to: {new_pos}")
        query.data = "admin:watermark"
        await callback_router(client, query)
        return

    # --- Watermark Visual Preview Button ---
    if data == "wm:preview":
        await query.answer("Generating visual preview...", show_alert=False)
        settings = await db.get_settings()
        wm_text = settings.get("watermark_text", "@MyChannel")
        pos = settings.get("watermark_position", "bottom-right")
        font_size = int(settings.get("watermark_font_size", 28))
        font_color = settings.get("watermark_font_color", "white")

        preview_path = await WatermarkEngine.generate_preview(
            text=wm_text,
            position=pos,
            font_size=font_size,
            font_color=font_color,
        )

        if preview_path and os.path.exists(preview_path):
            caption = (
                f"<b>👁 Watermark Visual Preview Sample</b>\n"
                f"• <b>Text:</b> <code>{wm_text}</code>\n"
                f"• <b>Position:</b> <code>{pos}</code>\n"
                f"• <b>Font Size:</b> {font_size}px"
            )
            await query.message.reply_photo(preview_path, caption=caption)
            try:
                os.remove(preview_path)
            except Exception:
                pass
        else:
            await query.message.reply_text("⚠️ Preview generation failed. Please verify FFmpeg installation.")
        return

    # --- Manual Poll Trigger Button ---
    if data == "admin:pollnow":
        await query.answer("Dispatching weekly poll...", show_alert=False)
        success = await poll_scheduler.publish_weekly_poll()
        if success:
            await query.message.reply_text("✅ <b>Weekly bilingual poll published successfully to Update Channels!</b>")
        else:
            await query.message.reply_text("⚠️ <b>Poll failed:</b> No titles uploaded this week or no Update Channel linked.")
        return

    # --- Clear All Data Prompt ---
    if data == "admin:clearall:prompt":
        text = (
            "<b>⚠️ CAUTION: Clear All Data Request</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "This will permanently erase:\n"
            "• All linked Main and Update channels\n"
            "• All aggregated post records\n"
            "• All custom title posters\n"
            "• All tracked weekly titles\n\n"
            "<i>Owner authorization and MongoDB cluster pool will be preserved.</i>\n\n"
            "Confirm data wipe?"
        )
        markup = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⚠️ Yes, Wipe Everything", callback_data="admin:clearall:confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="admin:clearall:cancel"),
            ]
        ])
        await query.message.edit_text(text, reply_markup=markup)
        await query.answer()
        return

    # --- Clear All Data Confirm ---
    if data == "admin:clearall:confirm":
        success = await db.clear_all_data()
        if success:
            await query.message.edit_text(
                "✅ <b>Database Wipe Completed:</b>\n"
                "All channels, aggregated posts, posters, and tracked titles have been removed.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin:menu")]
                ])
            )
        else:
            await query.message.edit_text(
                "❌ Error occurred while attempting data wipe.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin:menu")]
                ])
            )
        await query.answer("Data wipe executed.")
        return

    # --- Clear All Data Cancel ---
    if data == "admin:clearall:cancel":
        query.data = "admin:menu"
        await callback_router(client, query)
        return
