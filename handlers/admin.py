"""
Admin Command Handlers module.
Handles dynamic admin management, channel links, invite links, poster mapping,
custom caption formats, external storage configuration, multi-cluster redundancy,
watermark controls, data wipe, and status reports.
Strictly contains NO underscores in commands and 100% English localization.
"""

import logging
import os
from pyrogram import Client, filters
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import Config
from database import db
from scheduler import poll_scheduler
from watermark import WatermarkEngine

logger = logging.getLogger(__name__)


# Custom dynamic admin filter
async def _is_admin(_, __, message: Message) -> bool:
    if not message.from_user:
        return False
    return db.is_admin(message.from_user.id)

admin_filter = filters.create(_is_admin)


# Pending state tracking for interactive multi-step commands
# E.g. waiting for poster photo or custom format text
PENDING_STATES = {}


# =============================================================================
# START & HELP COMMANDS
# =============================================================================

@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    """Start command handler with role-aware greeting."""
    user_id = message.from_user.id
    if db.is_admin(user_id):
        text = (
            "<b>👋 Welcome to Telegram Auto-Uploader & Aggregator Bot</b>\n\n"
            "You are authorized as an <b>Administrator</b>.\n\n"
            "<b>Quick Actions:</b>\n"
            "• Send or forward any video/document to automatically upload and aggregate.\n"
            "• Use /adminpanel to access the full management interface.\n"
            "• Use /help to see all available commands."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎛 Open Admin Panel", callback_data="admin:menu")],
            [InlineKeyboardButton("📊 Database Status", callback_data="admin:dbstatus"),
             InlineKeyboardButton("💧 Watermark Menu", callback_data="admin:watermark")]
        ])
    else:
        text = (
            "<b>👋 Hello!</b>\n\n"
            "This is an automated media aggregator bot. "
            "Please use the official channels to browse and download content."
        )
        markup = None

    await message.reply_text(text, reply_markup=markup, disable_web_page_preview=True)


@Client.on_message(filters.command("help") & admin_filter)
async def help_handler(client: Client, message: Message):
    """Displays comprehensive English help menu with all available commands."""
    help_text = (
        "<b>📖 Admin Command Reference</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "<b>👑 Admin Management:</b>\n"
        "• <code>/addadmin &lt;id/username&gt;</code> - Grant admin privileges\n"
        "• <code>/deladmin &lt;id/username&gt;</code> - Revoke admin privileges\n"
        "• <code>/adminlist</code> - View all registered admins\n\n"
        "<b>📢 Channel Management:</b>\n"
        "• <code>/setchannel &lt;chat_id&gt;</code> - Link Target Main Channel\n"
        "• <code>/delchannel &lt;chat_id&gt;</code> - Unlink Target Main Channel\n"
        "• <code>/setupdatechannel &lt;chat_id&gt;</code> - Link Update Channel\n"
        "• <code>/delupdatechannel &lt;chat_id&gt;</code> - Unlink Update Channel\n"
        "• <code>/channellist</code> - View all linked channels & invite links\n\n"
        "<b>🖼 Poster Management:</b>\n"
        "• <code>/setposter &lt;Title&gt;</code> - Map poster image to a title\n"
        "• <code>/delposter &lt;Title&gt;</code> - Remove poster mapping\n"
        "• <code>/posterlist</code> - List all stored title posters\n\n"
        "<b>🤖 Storage & Formats:</b>\n"
        "• <code>/setstoragebot &lt;username&gt;</code> - Set External File Storage Bot\n"
        "• <code>/setdbchannel &lt;channel_id&gt;</code> - Set Storage Database Channel\n"
        "• <code>/setnormalformat</code> - Configure Main Channel caption format\n"
        "• <code>/setupdateformat</code> - Configure Update Channel caption format\n\n"
        "<b>💧 FFmpeg Watermarking:</b>\n"
        "• <code>/watermark</code> - Open watermark configuration menu\n"
        "• <code>/previewwm</code> - Generate live sample visual preview\n\n"
        "<b>🗄 Multi-Cluster Database & Maintenance:</b>\n"
        "• <code>/adddb &lt;mongo_uri&gt;</code> - Add redundant MongoDB cluster URI\n"
        "• <code>/deldb &lt;mongo_uri&gt;</code> - Remove MongoDB cluster URI\n"
        "• <code>/dbstatus</code> - Live latency, active node, and collection telemetry\n"
        "• <code>/clearall</code> - Wipe all channel, post, and poster data\n"
        "• <code>/pollnow</code> - Trigger Sunday bilingual poll immediately\n"
        "• <code>/adminpanel</code> - Interactive visual control panel"
    )
    await message.reply_text(help_text, disable_web_page_preview=True)


# =============================================================================
# ADMIN PANEL (MAIN DASHBOARD)
# =============================================================================

@Client.on_message(filters.command("adminpanel") & admin_filter)
async def adminpanel_handler(client: Client, message: Message):
    """Interactive Admin Control Panel."""
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
    await message.reply_text(text, reply_markup=markup)


# =============================================================================
# DYNAMIC ADMIN MANAGEMENT COMMANDS
# =============================================================================

@Client.on_message(filters.command("addadmin") & admin_filter)
async def addadmin_handler(client: Client, message: Message):
    """Grant admin privileges to a user by ID, username, or message reply."""
    target_id = None
    target_username = ""

    # Check if replying to a user's message
    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
        target_username = message.reply_to_message.from_user.username or ""
    elif len(message.command) > 1:
        arg = message.command[1].strip().lstrip("@")
        if arg.isdigit() or (arg.startswith("-") and arg[1:].isdigit()):
            target_id = int(arg)
        else:
            try:
                user = await client.get_users(arg)
                target_id = user.id
                target_username = user.username or ""
            except Exception as e:
                await message.reply_text(f"❌ Could not resolve user: {str(e)}")
                return
    else:
        await message.reply_text(
            "<b>Usage:</b>\n"
            "• <code>/addadmin &lt;user_id&gt;</code>\n"
            "• <code>/addadmin &lt;username&gt;</code>\n"
            "• Reply to a user with <code>/addadmin</code>"
        )
        return

    if not target_id:
        await message.reply_text("❌ Invalid user specified.")
        return

    success = await db.add_admin(target_id, target_username, added_by=message.from_user.id)
    if success:
        await message.reply_text(
            f"✅ <b>Successfully granted admin privileges:</b>\n"
            f"• <b>User ID:</b> <code>{target_id}</code>\n"
            f"• <b>Username:</b> @{target_username or 'None'}"
        )
    else:
        await message.reply_text("❌ Failed to add admin to database.")


@Client.on_message(filters.command("deladmin") & admin_filter)
async def deladmin_handler(client: Client, message: Message):
    """Revoke admin privileges from a user."""
    target_id = None

    if message.reply_to_message and message.reply_to_message.from_user:
        target_id = message.reply_to_message.from_user.id
    elif len(message.command) > 1:
        arg = message.command[1].strip().lstrip("@")
        if arg.isdigit() or (arg.startswith("-") and arg[1:].isdigit()):
            target_id = int(arg)
        else:
            try:
                user = await client.get_users(arg)
                target_id = user.id
            except Exception as e:
                await message.reply_text(f"❌ Could not resolve user: {str(e)}")
                return
    else:
        await message.reply_text(
            "<b>Usage:</b>\n"
            "• <code>/deladmin &lt;user_id&gt;</code>\n"
            "• <code>/deladmin &lt;username&gt;</code>\n"
            "• Reply to an admin with <code>/deladmin</code>"
        )
        return

    if target_id == Config.OWNER_ID:
        await message.reply_text("❌ You cannot revoke privileges from the Bot Owner.")
        return

    success = await db.remove_admin(target_id)
    if success:
        await message.reply_text(f"✅ Admin privileges revoked for User ID: <code>{target_id}</code>.")
    else:
        await message.reply_text("❌ Admin not found or could not be removed.")


@Client.on_message(filters.command("adminlist") & admin_filter)
async def adminlist_handler(client: Client, message: Message):
    """List all registered administrators."""
    admins = await db.get_all_admins()
    lines = ["<b>👥 Registered Administrators:</b>\n"]
    lines.append(f"👑 <b>Owner:</b> <code>{Config.OWNER_ID}</code>\n")

    for a in admins:
        uid = a.get("user_id")
        uname = a.get("username")
        display = f"@{uname}" if uname else f"ID: {uid}"
        lines.append(f"• <code>{uid}</code> ({display})")

    await message.reply_text("\n".join(lines))


# =============================================================================
# CHANNEL CONFIGURATION COMMANDS
# =============================================================================

@Client.on_message(filters.command("setchannel") & admin_filter)
async def setchannel_handler(client: Client, message: Message):
    """Link Target Main Channel where aggregated posts will be published."""
    if len(message.command) < 2:
        await message.reply_text(
            "<b>Usage:</b> <code>/setchannel &lt;chat_id_or_username&gt;</code>\n\n"
            "<i>Make sure the bot is an Administrator in the target channel with post permissions.</i>"
        )
        return

    arg = message.command[1].strip()
    try:
        chat = await client.get_chat(arg)
    except Exception as e:
        await message.reply_text(f"❌ Failed to access channel: {str(e)}")
        return

    # Generate private invite link if channel is private
    invite_link = ""
    try:
        invite_link = chat.invite_link or ""
        if not invite_link:
            link_obj = await client.create_chat_invite_link(chat.id)
            invite_link = link_obj.invite_link
    except Exception as e:
        logger.warning("Could not create invite link for channel %s: %s", chat.id, str(e))

    await db.add_channel(
        chat_id=chat.id,
        title=chat.title or "Main Channel",
        username=chat.username or "",
        invite_link=invite_link,
        channel_type="main",
    )
    await db.update_settings({"main_channel_id": chat.id})

    # Requirement 4: Upon setting a channel, display an inline button to trigger poster configuration
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Configure Poster Now", callback_data="admin:posters:prompt")]
    ])

    await message.reply_text(
        f"✅ <b>Target Main Channel Configured:</b>\n"
        f"• <b>Title:</b> {chat.title}\n"
        f"• <b>ID:</b> <code>{chat.id}</code>\n"
        f"• <b>Invite Link:</b> {invite_link or 'Public'}\n\n"
        f"<i>Click the button below to assign a custom poster image for titles.</i>",
        reply_markup=markup,
    )


@Client.on_message(filters.command("delchannel") & admin_filter)
async def delchannel_handler(client: Client, message: Message):
    """Unlink Target Main Channel."""
    if len(message.command) < 2:
        await message.reply_text("<b>Usage:</b> <code>/delchannel &lt;chat_id&gt;</code>")
        return

    chat_id = int(message.command[1].strip())
    success = await db.remove_channel(chat_id)
    if success:
        await message.reply_text(f"✅ Channel <code>{chat_id}</code> removed successfully.")
    else:
        await message.reply_text("❌ Channel not found.")


@Client.on_message(filters.command("setupdatechannel") & admin_filter)
async def setupdatechannel_handler(client: Client, message: Message):
    """Link Update Channel where update notifications and Sunday polls will be posted."""
    if len(message.command) < 2:
        await message.reply_text("<b>Usage:</b> <code>/setupdatechannel &lt;chat_id_or_username&gt;</code>")
        return

    arg = message.command[1].strip()
    try:
        chat = await client.get_chat(arg)
    except Exception as e:
        await message.reply_text(f"❌ Failed to access channel: {str(e)}")
        return

    invite_link = ""
    try:
        invite_link = chat.invite_link or ""
        if not invite_link:
            link_obj = await client.create_chat_invite_link(chat.id)
            invite_link = link_obj.invite_link
    except Exception as e:
        logger.warning("Could not create invite link for update channel %s: %s", chat.id, str(e))

    await db.add_channel(
        chat_id=chat.id,
        title=chat.title or "Update Channel",
        username=chat.username or "",
        invite_link=invite_link,
        channel_type="update",
    )
    await db.update_settings({"update_channel_id": chat.id})

    await message.reply_text(
        f"✅ <b>Update Channel Configured:</b>\n"
        f"• <b>Title:</b> {chat.title}\n"
        f"• <b>ID:</b> <code>{chat.id}</code>\n"
        f"• <b>Invite Link:</b> {invite_link or 'Public'}\n\n"
        f"<i>Release notifications and Sunday bilingual polls will be dispatched here.</i>"
    )


@Client.on_message(filters.command("delupdatechannel") & admin_filter)
async def delupdatechannel_handler(client: Client, message: Message):
    """Unlink Update Channel."""
    if len(message.command) < 2:
        await message.reply_text("<b>Usage:</b> <code>/delupdatechannel &lt;chat_id&gt;</code>")
        return

    chat_id = int(message.command[1].strip())
    success = await db.remove_channel(chat_id)
    if success:
        await message.reply_text(f"✅ Update Channel <code>{chat_id}</code> removed.")
    else:
        await message.reply_text("❌ Channel not found.")


@Client.on_message(filters.command("channellist") & admin_filter)
async def channellist_handler(client: Client, message: Message):
    """Display all configured Target Main and Update Channels."""
    channels = await db.get_channels()
    if not channels:
        await message.reply_text("ℹ️ No channels currently configured. Use <code>/setchannel</code> to link one.")
        return

    lines = ["<b>📢 Linked Channels:</b>\n"]
    for c in channels:
        ctype = c.get("type", "main").upper()
        title = c.get("title", "Untitled")
        cid = c.get("chat_id")
        link = c.get("invite_link") or (f"@{c.get('username')}" if c.get("username") else "No Link")
        lines.append(f"• <b>[{ctype}]</b> {title} (<code>{cid}</code>)\n  🔗 Link: {link}\n")

    await message.reply_text("\n".join(lines), disable_web_page_preview=True)


# =============================================================================
# POSTER MANAGEMENT COMMANDS
# =============================================================================

@Client.on_message(filters.command("setposter") & admin_filter)
async def setposter_handler(client: Client, message: Message):
    """
    Map a poster to a title.
    Supports:
    1. Replying to a photo or document with: /setposter <Title>
    2. Sending /setposter <Title> and then replying with the photo/document.
    """
    if len(message.command) < 2:
        await message.reply_text(
            "<b>Usage:</b>\n"
            "Reply to a photo or document with:\n"
            "<code>/setposter &lt;Title&gt;</code>\n\n"
            "<i>Example: /setposter Naruto Shippuden</i>"
        )
        return

    title = " ".join(message.command[1:]).strip()

    # Check if replied to media
    reply = message.reply_to_message
    if reply and (reply.photo or reply.document):
        file_id = ""
        media_type = "photo"
        if reply.photo:
            file_id = reply.photo.file_id
            media_type = "photo"
        elif reply.document:
            file_id = reply.document.file_id
            media_type = "document"

        success = await db.set_poster(title, file_id, media_type)
        if success:
            await message.reply_text(
                f"✅ <b>Poster Assigned Successfully!</b>\n"
                f"• <b>Title:</b> {title}\n"
                f"• <b>Media Type:</b> {media_type.title()}"
            )
        else:
            await message.reply_text("❌ Failed to save poster into database.")
        return

    # Otherwise set pending state waiting for media
    PENDING_STATES[message.from_user.id] = {
        "action": "await_poster_media",
        "title": title,
    }
    await message.reply_text(
        f"📸 <b>Waiting for Poster Media:</b>\n\n"
        f"Now send or reply with the poster image (as Photo or Document) for: <b>{title}</b>."
    )


@Client.on_message(filters.command("delposter") & admin_filter)
async def delposter_handler(client: Client, message: Message):
    """Delete a poster mapping."""
    if len(message.command) < 2:
        await message.reply_text("<b>Usage:</b> <code>/delposter &lt;Title&gt;</code>")
        return

    title = " ".join(message.command[1:]).strip()
    success = await db.delete_poster(title)
    if success:
        await message.reply_text(f"✅ Poster for <b>{title}</b> removed successfully.")
    else:
        await message.reply_text(f"❌ No poster found for <b>{title}</b>.")


@Client.on_message(filters.command("posterlist") & admin_filter)
async def posterlist_handler(client: Client, message: Message):
    """List all stored posters."""
    posters = await db.get_all_posters()
    if not posters:
        await message.reply_text("ℹ️ No custom posters currently stored. Use <code>/setposter</code> to add one.")
        return

    lines = ["<b>🖼 Stored Posters:</b>\n"]
    for p in posters:
        lines.append(f"• <b>{p.get('title')}</b> ({p.get('media_type', 'photo').title()})")

    await message.reply_text("\n".join(lines))


# =============================================================================
# CAPTION FORMAT COMMANDS
# =============================================================================

@Client.on_message(filters.command("setnormalformat") & admin_filter)
async def setnormalformat_handler(client: Client, message: Message):
    """Set custom caption template for Main Channel posts."""
    if len(message.command) < 2:
        settings = await db.get_settings()
        current = settings.get("normal_format", Config.DEFAULT_NORMAL_FORMAT)
        await message.reply_text(
            f"<b>Current Normal Caption Format:</b>\n<pre>{current}</pre>\n\n"
            f"<b>Available Variables:</b>\n"
            f"• <code>{{title}}</code> - Title of show/movie\n"
            f"• <code>{{season}}</code> - Season (e.g. S01)\n"
            f"• <code>{{episode}}</code> - Episode (e.g. E05)\n"
            f"• <code>{{audio}}</code> - Audio track\n"
            f"• <code>{{quality}}</code> - Extracted resolution\n\n"
            f"<b>Usage:</b> <code>/setnormalformat &lt;your_format_text&gt;</code>"
        )
        return

    new_fmt = message.text.split(None, 1)[1]
    await db.update_settings({"normal_format": new_fmt})
    await message.reply_text("✅ <b>Main Channel Normal Format updated successfully!</b>")


@Client.on_message(filters.command("setupdateformat") & admin_filter)
async def setupdateformat_handler(client: Client, message: Message):
    """Set custom caption template for Update Channel alerts."""
    if len(message.command) < 2:
        settings = await db.get_settings()
        current = settings.get("update_format", Config.DEFAULT_UPDATE_FORMAT)
        await message.reply_text(
            f"<b>Current Update Caption Format:</b>\n<pre>{current}</pre>\n\n"
            f"<b>Available Variables:</b>\n"
            f"• <code>{{title}}</code> - Title of show/movie\n"
            f"• <code>{{season}}</code> - Season (e.g. S01)\n"
            f"• <code>{{episode}}</code> - Episode (e.g. E05)\n"
            f"• <code>{{audio}}</code> - Audio track\n"
            f"• <code>{{qualities}}</code> - Comma-separated qualities\n"
            f"• <code>{{main_post_link}}</code> - Direct Telegram link to main post\n\n"
            f"<b>Usage:</b> <code>/setupdateformat &lt;your_format_text&gt;</code>"
        )
        return

    new_fmt = message.text.split(None, 1)[1]
    await db.update_settings({"update_format": new_fmt})
    await message.reply_text("✅ <b>Update Channel Format updated successfully!</b>")


# =============================================================================
# EXTERNAL FILE STORAGE BOT INTEGRATION COMMANDS
# =============================================================================

@Client.on_message(filters.command("setstoragebot") & admin_filter)
async def setstoragebot_handler(client: Client, message: Message):
    """Configure external File Storage Bot username."""
    if len(message.command) < 2:
        settings = await db.get_settings()
        current = settings.get("external_storage_bot", "")
        await message.reply_text(
            f"<b>Current External Storage Bot:</b> @{current or 'None'}\n\n"
            f"<b>Usage:</b> <code>/setstoragebot &lt;username&gt;</code>"
        )
        return

    username = message.command[1].strip().lstrip("@")
    await db.update_settings({"external_storage_bot": username})
    await message.reply_text(f"✅ External File Storage Bot updated to: @{username}")


@Client.on_message(filters.command("setdbchannel") & admin_filter)
async def setdbchannel_handler(client: Client, message: Message):
    """Configure external File Storage Database Channel ID."""
    if len(message.command) < 2:
        settings = await db.get_settings()
        current = settings.get("external_db_channel_id", 0)
        await message.reply_text(
            f"<b>Current Storage DB Channel:</b> <code>{current or 'None'}</code>\n\n"
            f"<b>Usage:</b> <code>/setdbchannel &lt;channel_id&gt;</code>\n"
            f"<i>Example: /setdbchannel -1001234567890</i>"
        )
        return

    try:
        cid = int(message.command[1].strip())
    except ValueError:
        await message.reply_text("❌ Invalid channel ID. Please provide an integer starting with -100.")
        return

    await db.update_settings({"external_db_channel_id": cid})
    await message.reply_text(f"✅ Storage Database Channel ID updated to: <code>{cid}</code>")


# =============================================================================
# WATERMARKING & PREVIEW COMMANDS
# =============================================================================

@Client.on_message(filters.command("watermark") & admin_filter)
async def watermark_handler(client: Client, message: Message):
    """Watermark settings and toggle menu."""
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
        "Use buttons below to toggle watermarking or generate a visual preview:"
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
        [InlineKeyboardButton("🔙 Back to Admin Panel", callback_data="admin:menu")],
    ])
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.command("previewwm") & admin_filter)
async def previewwm_handler(client: Client, message: Message):
    """Generate and send visual preview sample of watermark."""
    settings = await db.get_settings()
    wm_text = settings.get("watermark_text", "@MyChannel")
    pos = settings.get("watermark_position", "bottom-right")
    font_size = int(settings.get("watermark_font_size", 28))
    font_color = settings.get("watermark_font_color", "white")

    status_msg = await message.reply_text("⏳ Generating visual watermark preview...")
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
        await message.reply_photo(preview_path, caption=caption)
        try:
            os.remove(preview_path)
        except Exception:
            pass
        await status_msg.delete()
    else:
        await status_msg.edit_text(
            "⚠️ <b>Preview Generation Failed:</b>\n"
            "Please ensure FFmpeg is installed and accessible on the server."
        )


# =============================================================================
# MULTI-CLUSTER DATABASE REDUNDANCY COMMANDS
# =============================================================================

@Client.on_message(filters.command("adddb") & admin_filter)
async def adddb_handler(client: Client, message: Message):
    """Add a redundant MongoDB cluster URI."""
    if len(message.command) < 2:
        await message.reply_text(
            "<b>Usage:</b> <code>/adddb &lt;mongodb_uri&gt;</code>\n\n"
            "<i>Example: /adddb mongodb+srv://user:pass@cluster2.mongodb.net/</i>"
        )
        return

    uri = message.command[1].strip()
    success = await db.add_mongo_uri(uri)
    if success:
        await message.reply_text("✅ <b>New MongoDB Cluster URI added to redundancy pool.</b>")
    else:
        await message.reply_text("❌ URI already exists in the pool or is invalid.")


@Client.on_message(filters.command("deldb") & admin_filter)
async def deldb_handler(client: Client, message: Message):
    """Remove a MongoDB cluster URI."""
    if len(message.command) < 2:
        await message.reply_text("<b>Usage:</b> <code>/deldb &lt;mongodb_uri&gt;</code>")
        return

    uri = message.command[1].strip()
    success = await db.remove_mongo_uri(uri)
    if success:
        await message.reply_text("✅ <b>MongoDB Cluster URI removed from pool.</b>")
    else:
        await message.reply_text("❌ URI not found or cannot remove the last remaining cluster.")


@Client.on_message(filters.command("dbstatus") & admin_filter)
async def dbstatus_handler(client: Client, message: Message):
    """Live database status monitoring and collection record counters."""
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
        [InlineKeyboardButton("🔄 Refresh Telemetry", callback_data="admin:dbstatus")]
    ])
    await message.reply_text(text, reply_markup=markup)


# =============================================================================
# DATA WIPE & WEEKLY POLL MANUAL TRIGGER
# =============================================================================

@Client.on_message(filters.command("clearall") & admin_filter)
async def clearall_handler(client: Client, message: Message):
    """Complete data wipe with confirmation step."""
    text = (
        "<b>⚠️ CAUTION: Clear All Data Request</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "This operation will permanently wipe:\n"
        "• All linked Main and Update channels\n"
        "• All tracked aggregated post mappings\n"
        "• All custom posters\n"
        "• All weekly poll title records\n\n"
        "<i>Bot Owner privileges and database connections will be preserved.</i>\n\n"
        "Are you absolutely sure you want to proceed?"
    )
    markup = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚠️ Yes, Wipe Everything", callback_data="admin:clearall:confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="admin:clearall:cancel"),
        ]
    ])
    await message.reply_text(text, reply_markup=markup)


@Client.on_message(filters.command("pollnow") & admin_filter)
async def pollnow_handler(client: Client, message: Message):
    """Manually trigger the Sunday bilingual poll for testing or immediate broadcast."""
    status_msg = await message.reply_text("⏳ Generating and publishing bilingual weekly poll...")
    success = await poll_scheduler.publish_weekly_poll()
    if success:
        await status_msg.edit_text("✅ <b>Weekly bilingual poll published successfully to Update Channels!</b>")
    else:
        await status_msg.edit_text(
            "⚠️ <b>Poll Not Published:</b>\n"
            "Either no titles were uploaded this week, or no Update Channel is configured."
        )


@Client.on_message(filters.command("stats") & admin_filter)
async def stats_handler(client: Client, message: Message):
    """System statistics report."""
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
    await message.reply_text(text)


# =============================================================================
# MEDIA REPLY LISTENER FOR POSTER ASSIGNMENT
# =============================================================================

@Client.on_message(filters.private & (filters.photo | filters.document) & admin_filter)
async def poster_media_listener(client: Client, message: Message):
    """Intercept incoming media if admin was prompted to send a poster."""
    user_id = message.from_user.id
    state = PENDING_STATES.get(user_id)

    if not state or state.get("action") != "await_poster_media":
        # Pass through to regular uploader
        return

    title = state.get("title", "")
    file_id = ""
    media_type = "photo"

    if message.photo:
        file_id = message.photo.file_id
        media_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        media_type = "document"

    del PENDING_STATES[user_id]

    success = await db.set_poster(title, file_id, media_type)
    if success:
        await message.reply_text(
            f"✅ <b>Poster Successfully Set for:</b> <code>{title}</code>\n"
            f"• <b>Format:</b> {media_type.title()}"
        )
    else:
        await message.reply_text("❌ Failed to save poster into database.")
