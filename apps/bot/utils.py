"""Telegram bilan ishlashda takrorlanadigan amallar."""

from __future__ import annotations

import re

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InputMediaDocument, InputMediaPhoto, Message

from core.logging import get_logger

log = get_logger(__name__)

#  Telegram xabar chegarasi
MAX_MESSAGE_LENGTH = 4096

#  Bitta albomda ko'pi bilan shuncha rasm
MEDIA_GROUP_LIMIT = 10

#  E'tiborsiz qoldirsa bo'ladigan xatolar — bular haqiqiy muammo emas
IGNORABLE = (
    "message is not modified",
    "message to edit not found",
    "query is too old",
    "message can't be edited",
    "message to delete not found",
)

_HTML_TAG = re.compile(r"<(/)?([a-zA-Z0-9]+)(?:\s+[^>]*)?>")


def _close_html_tags(text: str) -> str:
    """Ochiq qolgan HTML teglarini yopadi."""
    stack: list[str] = []
    for match in _HTML_TAG.finditer(text):
        is_closing = bool(match.group(1))
        tag = match.group(2).lower()
        if is_closing:
            if stack and stack[-1] == tag:
                stack.pop()
        else:
            stack.append(tag)
    return text + "".join(f"</{tag}>" for tag in reversed(stack))


def _is_ignorable(error: TelegramBadRequest) -> bool:
    text = str(error).lower()
    return any(fragment in text for fragment in IGNORABLE)


def trim(text: str) -> str:
    """
    Xabarni Telegram chegarasiga sig'diradi.

    Kesish HTML tegining o'rtasiga tushmasligi uchun oxirgi qator
    chegarasidan kesamiz va ochiq qolgan teglarni xavfsiz yopamiz.
    """
    if len(text) <= MAX_MESSAGE_LENGTH:
        return text

    limit = MAX_MESSAGE_LENGTH - 60
    cut = text.rfind("\n", 0, limit)
    if cut < limit // 2:
        cut = limit

    # Agar cut tegning o'rtasiga tushib qolsa (< belgisidan keyin lekin > dan oldin)
    last_open = text.rfind("<", 0, cut)
    last_close = text.rfind(">", 0, cut)
    if last_open > last_close:
        cut = last_open

    sliced = text[:cut]
    closed = _close_html_tags(sliced)
    return closed + "\n\n<i>… ro'yxat qisqartirildi</i>"


async def safe_answer(callback: CallbackQuery, text: str | None = None, *, alert: bool = False) -> bool:
    """CallbackQuery'ga xatosiz javob beradi."""
    try:
        await callback.answer(text=text, show_alert=alert)
        return True
    except TelegramBadRequest as error:
        if not _is_ignorable(error):
            log.warning("Callback javobida kutilmagan xato: %s", error)
        return False


async def safe_edit(
    callback: CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """
    Xabarni tahrirlaydi.

    Rasm yoki hujjatli xabarlarda edit_text ishlamaydi — bunday holatda
    eski xabar o'chirilib yangisi yuboriladi.
    """
    message = callback.message
    if message is None:
        return False

    text = trim(text)

    if getattr(message, "photo", None) or getattr(message, "document", None):
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(text, reply_markup=reply_markup)
        return True

    try:
        await message.edit_text(text, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as error:
        if _is_ignorable(error):
            return True
        log.warning("Xabar tahrirlab bo'lmadi (%s), yangisi yuborilmoqda", error)
        try:
            await message.delete()
        except Exception:
            pass
        try:
            await message.answer(text, reply_markup=reply_markup)
            return True
        except Exception:
            pass
        return False


async def safe_delete(message: Message) -> None:
    """Xabarni o'chiradi. O'chirib bo'lmasa xato bermaydi."""
    try:
        await message.delete()
    except Exception:
        pass


async def _send_media_chunk(message: Message, chunk: list) -> int:
    """Bir xil turdagi fayllar (faqat rasmlar yoki faqat hujjatlar) guruhini yuboradi."""
    if not chunk:
        return 0

    if len(chunk) == 1:
        item = chunk[0]
        if item.media_type == "document":
            await message.answer_document(item.file_id, caption=item.caption)
        else:
            await message.answer_photo(item.file_id, caption=item.caption)
        return 1

    try:
        if chunk[0].media_type == "document":
            group_media = [
                InputMediaDocument(media=item.file_id, caption=item.caption)
                for item in chunk
            ]
        else:
            group_media = [
                InputMediaPhoto(media=item.file_id, caption=item.caption)
                for item in chunk
            ]
        await message.answer_media_group(media=group_media)
        return len(chunk)

    except TelegramBadRequest as error:
        log.warning("Albom yuborishda xatolik (%s), birma-bir yuborilmoqda", error)
        count = 0
        for item in chunk:
            try:
                if item.media_type == "document":
                    await message.answer_document(item.file_id, caption=item.caption)
                else:
                    await message.answer_photo(item.file_id, caption=item.caption)
                count += 1
            except Exception as inner_err:
                log.warning("Fayl/rasm yuborilmadi: %s", inner_err)
        return count


async def send_media_group(message: Message, media_items: list) -> int:
    """
    Test rasmlari va fayllarini (PDF, Word va h.k.) yuboradi.

    Telegram qoidasiga ko'ra albomda rasm va hujjatni aralashtirib bo'lmaydi.
    Shuning uchun rasmlar va hujjatlar alohida guruhlarga ajratiladi.

    Returns:
        Yuborilgan fayllar soni.
    """
    if not media_items:
        return 0

    photos = [m for m in media_items if m.media_type != "document"]
    documents = [m for m in media_items if m.media_type == "document"]
    sent = 0

    for start in range(0, len(photos), MEDIA_GROUP_LIMIT):
        sent += await _send_media_chunk(
            message, photos[start : start + MEDIA_GROUP_LIMIT]
        )

    for start in range(0, len(documents), MEDIA_GROUP_LIMIT):
        sent += await _send_media_chunk(
            message, documents[start : start + MEDIA_GROUP_LIMIT]
        )

    return sent
