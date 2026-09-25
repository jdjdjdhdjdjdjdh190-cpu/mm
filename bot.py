import asyncio
import os
import tempfile
import urllib.request
from functools import wraps

from dotenv import load_dotenv

from telethon import TelegramClient, events
from telethon.tl.functions.channels import (
    CreateChannelRequest,
    EditAdminRequest,
    InviteToChannelRequest,
    TogglePreHistoryHiddenRequest,
    EditPhotoRequest,
)
from telethon.tl.functions.messages import (
    EditChatDefaultBannedRightsRequest,
    ExportChatInviteRequest,
)
from telethon.tl.types import (
    ChatAdminRights,
    ChatBannedRights,
    InputChatUploadedPhoto,
)
from telethon.errors import (
    ChatNotModifiedError,
    FloodWaitError,
    UserAlreadyParticipantError,
)

from telegram import Update, ChatPermissions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()
PHONE = os.getenv("PHONE", "").strip()

OGU_BOT_TOKEN = os.getenv("OGU_BOT_TOKEN", "").strip()
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "").strip()
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

OGU_BOT_USERNAME = os.getenv("OGU_BOT_USERNAME", "OGUMMdrobot").strip().lstrip("@")
CRYPTO_BOT_USERNAME = os.getenv(
    "CRYPTO_BOT_USERNAME", "aerivuecryptobot"
).strip().lstrip("@")

# Direct image URL supplied by you.
GROUP_PHOTO_URL = "https://i.ibb.co/99Tdr8Qn/group-logo.jpg"

GROUP_TITLE = "MM Group | @aerivue"
GROUP_ABOUT = "Please Make sure you check the username twice before dealing."

SESSION_NAME = "mm_userbot_session"


# ============================================================
# VALIDATION
# ============================================================

if not API_ID or not API_HASH:
    raise RuntimeError("API_ID / API_HASH missing in .env")

if not PHONE:
    raise RuntimeError("PHONE missing in .env")

if not OGU_BOT_TOKEN:
    raise RuntimeError("OGU_BOT_TOKEN missing in .env")

if not CRYPTO_BOT_TOKEN:
    raise RuntimeError("CRYPTO_BOT_TOKEN missing in .env")

if not ADMIN_USER_ID:
    raise RuntimeError("ADMIN_USER_ID missing in .env")


# ============================================================
# TELETHON USERBOT
# ============================================================

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

MEMBER_RIGHTS = ChatBannedRights(
    until_date=None,
    view_messages=False,
    send_messages=False,
    send_media=False,
    send_stickers=True,
    send_gifs=True,
    send_games=True,
    send_inline=True,
    embed_links=True,
    send_polls=True,
    change_info=True,
    invite_users=True,
    pin_messages=True,
)

ADMIN_RIGHTS = ChatAdminRights(
    change_info=True,
    post_messages=True,
    edit_messages=True,
    delete_messages=True,
    ban_users=True,
    invite_users=True,
    pin_messages=True,
    add_admins=False,
    anonymous=False,
    manage_call=True,
    other=True,
)

FIRST_MESSAGE = """**Please State the deal exactly.**

1. Who is the buyer and seller?
2. What is the deal about?
3. What crypto am i holding ? ( Bitcoin , litecoin , USDT Tether , ERC20 etc )
4. State additional information if necessary."""


# ============================================================
# HELPERS
# ============================================================

async def download_group_photo():
    """
    Downloads the configured image URL into a temporary file.
    Returns the local path or None if the download fails.
    """
    try:
        suffix = ".jpg"
        fd, path = tempfile.mkstemp(prefix="mm_group_", suffix=suffix)
        os.close(fd)

        loop = asyncio.get_running_loop()

        await loop.run_in_executor(
            None,
            lambda: urllib.request.urlretrieve(GROUP_PHOTO_URL, path),
        )

        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path

        try:
            os.remove(path)
        except OSError:
            pass

    except Exception as e:
        print(f"[PHOTO] Download failed: {e}")

    return None


async def promote_with_title(entity, user, rank, retries=3):
    for attempt in range(1, retries + 1):
        try:
            await client(
                EditAdminRequest(
                    channel=entity,
                    user_id=user,
                    admin_rights=ADMIN_RIGHTS,
                    rank=rank,
                )
            )
            print(f"[ADMIN] Promoted: {rank}")
            return True

        except Exception as e:
            print(
                f"[ADMIN] Promote {rank} attempt "
                f"{attempt}/{retries} failed: {e}"
            )

            if attempt < retries:
                await asyncio.sleep(2)

    return False


async def delete_message_safely(message):
    try:
        await message.delete()
    except Exception:
        pass


# ============================================================
# /mm USERBOT COMMAND
# ============================================================

@client.on(events.NewMessage(pattern=r"^/mm(?:@\w+)?$"))
async def mm_handler(event):
    try:
        # Delete /mm command immediately.
        await delete_message_safely(event)

        # ----------------------------------------------------
        # 1. CREATE PRIVATE MEGAGROUP
        # ----------------------------------------------------
        result = await client(
            CreateChannelRequest(
                title=GROUP_TITLE,
                about=GROUP_ABOUT,
                megagroup=True,
            )
        )

        group = result.chats[0]
        group_entity = await client.get_entity(group.id)

        print(f"[MM] Group created: {group.id}")

        # ----------------------------------------------------
        # 2. SHOW PREVIOUS HISTORY
        # ----------------------------------------------------
        try:
            await client(
                TogglePreHistoryHiddenRequest(
                    channel=group_entity,
                    enabled=False,
                )
            )
        except ChatNotModifiedError:
            pass
        except Exception as e:
            print(f"[MM] History toggle: {e}")

        # ----------------------------------------------------
        # 3. DEFAULT MEMBER PERMISSIONS
        # ----------------------------------------------------
        try:
            await client(
                EditChatDefaultBannedRightsRequest(
                    peer=group_entity,
                    banned_rights=MEMBER_RIGHTS,
                )
            )
        except Exception as e:
            print(f"[MM] Permissions: {e}")

        # ----------------------------------------------------
        # 4. GROUP PHOTO FROM URL
        # ----------------------------------------------------
        photo_path = await download_group_photo()

        if photo_path:
            try:
                uploaded = await client.upload_file(photo_path)

                await client(
                    EditPhotoRequest(
                        channel=group_entity,
                        photo=InputChatUploadedPhoto(uploaded),
                    )
                )

                print("[MM] Group photo set")

            except Exception as e:
                print(f"[MM] Photo upload: {e}")

            finally:
                try:
                    os.remove(photo_path)
                except OSError:
                    pass
        else:
            print("[MM] Group photo skipped")

        # ----------------------------------------------------
        # 5. GET + INVITE BOTH BOTS
        # ----------------------------------------------------
        ogu = await client.get_entity(OGU_BOT_USERNAME)
        crypto = await client.get_entity(CRYPTO_BOT_USERNAME)

        try:
            await client(
                InviteToChannelRequest(
                    channel=group_entity,
                    users=[ogu, crypto],
                )
            )
            print("[MM] OGU + Crypto bots invited")

        except UserAlreadyParticipantError:
            print("[MM] Bots already in group")

        except Exception as e:
            print(f"[MM] Invite error: {e}")

        await asyncio.sleep(2)

        # ----------------------------------------------------
        # 6. PROMOTE USER + BOTH BOTS
        # ----------------------------------------------------
        me = await client.get_me()

        await promote_with_title(
            group_entity,
            me,
            "Middleman",
        )

        await promote_with_title(
            group_entity,
            ogu,
            "OGU BOT",
        )

        await promote_with_title(
            group_entity,
            crypto,
            "Crypto BOT",
        )

        await asyncio.sleep(1)

        # ----------------------------------------------------
        # 7. SEND + PIN FIRST MESSAGE
        # ----------------------------------------------------
        msg = await client.send_message(
            group_entity,
            FIRST_MESSAGE,
            parse_mode="md",
        )

        try:
            await client.pin_message(
                group_entity,
                msg,
                notify=False,
            )
            print("[MM] First message pinned")
        except Exception as e:
            print(f"[MM] Pin failed: {e}")

        # ----------------------------------------------------
        # 8. EXPORT REAL INVITE LINK
        # ----------------------------------------------------
        try:
            invite = await client(
                ExportChatInviteRequest(
                    peer=group_entity,
                )
            )

            real_link = invite.link

            # Temporary helper message.
            # Crypto BOT detects this and replaces it with a
            # clean forwarded-link message.
            await client.send_message(
                group_entity,
                f"CRYPTO_LINK::{real_link}",
            )

            # Success message in original chat.
            await client.send_message(
                event.chat_id,
                "Please Join this Group and Send it to the next "
                "person who is involved in the deal.\n\n"
                f"{real_link}",
            )

            print(f"[MM] Invite link: {real_link}")

        except Exception as e:
            print(f"[MM] Invite link error: {e}")
            await client.send_message(
                event.chat_id,
                f"Group created, but invite link generation failed: {e}",
            )

    except FloodWaitError as e:
        await client.send_message(
            event.chat_id,
            f"Flood wait – try again in {e.seconds}s",
        )

    except Exception as e:
        try:
            await client.send_message(
                event.chat_id,
                f"Error: {e}",
            )
        except Exception:
            pass

        print(f"[MM] Full error: {e}")


# ============================================================
# PYTHON-TELEGRAM-BOT ADMIN DECORATOR
# ============================================================

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user

        if not user or user.id != ADMIN_USER_ID:
            return

        return await func(update, context)

    return wrapper


# ============================================================
# OGU BOT
# ============================================================

@admin_only
async def rec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /rec <amount>"
        )
        return

    amount = " ".join(context.args)

    text = (
        "Funds Recieved Successfully\n"
        f"Total amount - {amount}"
    )

    await update.message.reply_text(text)
    await delete_ptb_message(update.message)


@admin_only
async def ref(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /ref <amount>"
        )
        return

    text = (
        "Please Lock in with the your exact address "
        "that the Middleman Deal was heading with."
    )

    await update.message.reply_text(text)
    await delete_ptb_message(update.message)


@admin_only
async def lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /lock <amount>"
        )
        return

    amount = " ".join(context.args)

    try:
        await context.bot.set_chat_title(
            chat_id=update.effective_chat.id,
            title=f"{amount} | Locked",
        )
    except Exception as e:
        print(f"[OGU] Title change: {e}")

    text = (
        "Address have been locked successfully and it is "
        "pending for the Verification."
    )

    await update.message.reply_text(text)
    await delete_ptb_message(update.message)


@admin_only
async def tos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /tos <amount>"
        )
        return

    amount = " ".join(context.args)

    text = f"""Please send Same {amount} of Crypto to Release the Refund Transaction.

Terms of Service

Refunds will not be provided if the transaction is canceled without mutual confirmation from both the buyer and the seller. If a deal is canceled or time-wasted, the buyer must send the middleman an amount equal to the funds currently held. Once this additional amount has been received, the full held amount will be released within 48 hours through OGU staff support. This security measure is in place to prevent fraudulent refund attempts. If, during the investigation, OGU staff determines that the party requesting a refund was engaging in a scam attempt, the full amount will be permanently withheld.

Reference - t.me/mmtos"""

    await update.message.reply_text(text)
    await delete_ptb_message(update.message)


# ============================================================
# CRYPTO BOT
# ============================================================

async def on_new_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message

    if not msg or not msg.text:
        return

    # --------------------------------------------------------
    # CRYPTO_LINK helper from Telethon userbot
    # --------------------------------------------------------
    if msg.text.startswith("CRYPTO_LINK::"):
        real_link = msg.text.split(
            "CRYPTO_LINK::",
            1,
        )[1].strip()

        # Delete helper message.
        try:
            await msg.delete()
        except Exception:
            pass

        # Send clean separate message.
        text = (
            "Please forward this link to the next person "
            "who is involved in the deal.\n\n"
            f"{real_link}"
        )

        try:
            await context.bot.send_message(
                chat_id=msg.chat_id,
                text=text,
            )
        except Exception as e:
            print(f"[CRYPTO] Link message error: {e}")

        return

    # --------------------------------------------------------
    # After OGU /rec
    # --------------------------------------------------------
    if "Funds Recieved Successfully" in msg.text:
        try:
            await context.bot.send_message(
                chat_id=msg.chat_id,
                text="Funds Notification message.",
            )
        except Exception as e:
            print(f"[CRYPTO] Funds notification error: {e}")


@admin_only
async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to a user to mute."
        )
        return

    user_id = update.message.reply_to_message.from_user.id

    await context.bot.restrict_chat_member(
        chat_id=update.effective_chat.id,
        user_id=user_id,
        permissions=ChatPermissions(
            can_send_messages=False,
        ),
    )

    await update.message.reply_text("User muted.")
    await delete_ptb_message(update.message)


@admin_only
async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to a user to unmute."
        )
        return

    user_id = update.message.reply_to_message.from_user.id

    await context.bot.restrict_chat_member(
        chat_id=update.effective_chat.id,
        user_id=user_id,
        permissions=ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
        ),
    )

    await update.message.reply_text("User unmuted.")
    await delete_ptb_message(update.message)


@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "Reply to a user to ban."
        )
        return

    user_id = update.message.reply_to_message.from_user.id

    await context.bot.ban_chat_member(
        chat_id=update.effective_chat.id,
        user_id=user_id,
    )

    await update.message.reply_text("User banned.")
    await delete_ptb_message(update.message)


async def delete_ptb_message(message):
    try:
        await message.delete()
    except Exception:
        pass


# ============================================================
# BUILD TELEGRAM BOT APPLICATIONS
# ============================================================

def build_ogu_app():
    app = Application.builder().token(OGU_BOT_TOKEN).build()

    app.add_handler(CommandHandler("rec", rec))
    app.add_handler(CommandHandler("ref", ref))
    app.add_handler(CommandHandler("lock", lock))
    app.add_handler(CommandHandler("tos", tos))

    return app


def build_crypto_app():
    app = Application.builder().token(CRYPTO_BOT_TOKEN).build()

    # Message handler must be before/alongside command handlers.
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            on_new_message,
        )
    )

    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("ban", ban))

    return app


# ============================================================
# START ALL 3 CLIENTS IN ONE PYTHON FILE
# ============================================================

async def start_ptb_app(app, name):
    await app.initialize()
    await app.start()
    await app.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )
    print(f"[{name}] polling started")


async def stop_ptb_app(app, name):
    try:
        if app.updater and app.updater.running:
            await app.updater.stop()

        if app.running:
            await app.stop()

        await app.shutdown()

        print(f"[{name}] stopped")

    except Exception as e:
        print(f"[{name}] shutdown error: {e}")


async def main():
    print("=" * 60)
    print("MM USERBOT + OGU BOT + CRYPTO BOT")
    print("=" * 60)

    ogu_app = build_ogu_app()
    crypto_app = build_crypto_app()

    # Start the Telethon userbot.
    print("[USERBOT] Starting...")
    await client.start(phone=PHONE)
    print("[USERBOT] Running")

    # Start OGU bot.
    await start_ptb_app(
        ogu_app,
        "OGU BOT",
    )

    # Start Crypto bot.
    await start_ptb_app(
        crypto_app,
        "CRYPTO BOT",
    )

    print("=" * 60)
    print("ALL SYSTEMS ONLINE")
    print("Use /mm from your Telegram user account.")
    print("=" * 60)

    try:
        # Keep the same asyncio loop alive for all 3 clients.
        await client.run_until_disconnected()

    finally:
        print("[SYSTEM] Shutting down...")

        await stop_ptb_app(
            crypto_app,
            "CRYPTO BOT",
        )

        await stop_ptb_app(
            ogu_app,
            "OGU BOT",
        )

        if client.is_connected():
            await client.disconnect()

        print("[SYSTEM] Shutdown complete")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
