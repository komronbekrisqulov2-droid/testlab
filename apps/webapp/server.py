"""
Telegram Mini App (Web App) serveri.

aiohttp.web orqali interaktiv test yechish sahifasini, media proksisini va API'larini taqdim etadi.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any, TYPE_CHECKING

from aiohttp import web

import modules.registry  # noqa: F401 - ensure all ORM models are registered
from apps.bot.texts import uz
from core.config import settings
from core.exceptions import AlreadyAnsweredError, TestLabError
from core.logging import get_logger
from infrastructure.database.engine import get_session
from modules.assessment.service import AssessmentService
from modules.catalog.service import CatalogService
from modules.identity.models import User
from modules.identity.repository import UserRepository

if TYPE_CHECKING:
    from aiogram import Bot

log = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Media fayllarini xotirada keshlaymiz: media_id -> (bytes, content_type)
_media_cache: dict[int, tuple[bytes, str]] = {}


def validate_telegram_init_data(init_data: str, bot_token: str) -> dict[str, Any] | None:
    """
    Telegram WebApp `initData` tekshiruvi (HMAC-SHA256).

    Muvaffaqiyatli bo'lsa, parslangan ma'lumotlar lug'atini (ichidagi user_obj bilan) qaytaradi.
    Aks holda None.
    """
    if not init_data or not bot_token:
        return None
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        calculated_hash = hmac.new(
            secret_key, data_check_string.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(calculated_hash, received_hash):
            user_raw = parsed.get("user")
            if user_raw:
                parsed["user_obj"] = json.loads(user_raw)
            return parsed
        return None
    except Exception as err:
        log.warning("Telegram initData tekshirishda xato: %s", err)
        return None


async def handle_test_page(request: web.Request) -> web.Response:
    """Interaktiv test yechish sahifasi."""
    if not settings.webapp.enabled:
        return web.Response(
            text="<h2>⚠️ Mini App vaqtincha to'xtatilgan</h2><p>Administrator tomonidan ilova vaqtincha o'chirilgan. Iltimos, testlarni bot orqali yeching.</p>",
            content_type="text/html",
            status=403,
        )
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return web.Response(text="Web App sahifasi topilmadi", status=404)
    return web.FileResponse(index_file)


async def handle_api_test_data(request: web.Request) -> web.Response:
    """Test haqidagi ma'lumotlarni JSON formatida qaytaradi."""
    if not settings.webapp.enabled:
        return web.json_response({"error": "Mini App vaqtincha o'chirilgan"}, status=403)

    test_id_str = request.match_info.get("test_id", "")
    if not test_id_str.isdigit():
        return web.json_response({"error": "Yaroqsiz test ID"}, status=400)

    test_id = int(test_id_str)
    async with get_session() as session:
        catalog = CatalogService(session)
        test = await catalog.tests.get(test_id)
        if test is None:
            return web.json_response({"error": "Test topilmadi"}, status=404)

        media_items = await catalog.media.list_by_test(test.id)

        key = test.answer_key or ""
        q_count = len(key) if key else test.questions_count
        if test.is_randomized and test.random_questions_count:
            q_count = test.random_questions_count

        user_id_str = request.query.get("user_id")
        question_order = None
        if user_id_str and user_id_str.isdigit():
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(int(user_id_str))
            if user is not None:
                assessment = AssessmentService(session)
                active = await assessment.attempts.get_active(user.id, test.id)
                if active is None and test.is_randomized:
                    try:
                        active = await assessment.begin(test, user)
                    except Exception:
                        pass
                if test.is_randomized and active is not None and active.question_order:
                    question_order = [int(x) for x in active.question_order.split(",") if x.isdigit()]
                    q_count = len(question_order)

        is_practice = False
        official_score = None
        if user_id_str and user_id_str.isdigit():
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(int(user_id_str))
            if user is not None:
                assessment = AssessmentService(session)
                used = await assessment.attempts.count_by_user_and_test(user.id, test.id)
                if used > 0:
                    is_practice = True
                    first = await assessment.attempts.get_first_completed(user.id, test.id)
                    if first:
                        official_score = {
                            "score": first.score,
                            "max_score": first.max_score,
                            "percentage": round(first.percentage, 1),
                        }

        # Variantlar soni: 'E' harfi bo'lsa 5 ta, aks holda standart 4 ta (A, B, C, D)
        has_e = any(c in key.upper() for c in "EFGHIJKLMNOPQRSTUVWXYZ")
        options_count = 5 if has_e else 4

        data = {
            "id": test.id,
            "number": test.number,
            "title": test.title,
            "questionsCount": q_count,
            "questions_count": q_count,
            "optionsCount": options_count,
            "timeLimitSec": test.time_limit_sec,
            "time_limit_sec": test.time_limit_sec,
            "isRandomized": bool(test.is_randomized),
            "questionOrder": question_order,
            "isPractice": is_practice,
            "officialScore": official_score,
            "allowPractice": getattr(test, "allow_practice", True),
            "media": [
                {
                    "id": m.id,
                    "type": m.media_type,
                    "url": f"/api/media/{m.id}",
                }
                for m in media_items
            ],
        }
        return web.json_response(data)


async def handle_api_media(request: web.Request) -> web.Response:
    """Telegram media faylini brauzer / Web App da ko'rsatish uchun proksi."""
    media_id_str = request.match_info.get("media_id", "")
    if not media_id_str.isdigit():
        return web.Response(text="Yaroqsiz media ID", status=400)

    media_id = int(media_id_str)
    if media_id in _media_cache:
        data, content_type = _media_cache[media_id]
        return web.Response(
            body=data,
            content_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    async with get_session() as session:
        catalog = CatalogService(session)
        media = await catalog.media.get(media_id)
        if media is None or not media.file_id:
            return web.Response(text="Media topilmadi", status=404)

        bot: Bot | None = request.app.get("bot")
        if bot is None:
            return web.Response(text="Bot ulanmagan", status=503)

        try:
            tg_file = await bot.get_file(media.file_id)
            if not tg_file.file_path:
                return web.Response(text="Fayl yo'li topilmadi", status=404)

            buf = io.BytesIO()
            await bot.download_file(tg_file.file_path, destination=buf)
            data = buf.getvalue()

            file_lower = (tg_file.file_path or "").lower()
            if file_lower.endswith(".png"):
                content_type = "image/png"
            elif file_lower.endswith(".webp"):
                content_type = "image/webp"
            elif file_lower.endswith(".gif"):
                content_type = "image/gif"
            elif file_lower.endswith(".pdf"):
                content_type = "application/pdf"
            else:
                content_type = "image/jpeg"

            if len(_media_cache) >= 100:
                _media_cache.pop(next(iter(_media_cache)), None)
            _media_cache[media_id] = (data, content_type)
            return web.Response(
                body=data,
                content_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )
        except Exception as e:
            log.warning("Media yuklab olishda xato (%s): %s", media_id, e)
            return web.Response(text="Media yuklab olinmadi", status=500)


def _is_test_env() -> bool:
    """Sinov yoki mahalliy test muhitini aniqlaydi."""
    import os
    import sys
    return (
        "pytest" in sys.modules
        or "_env" in sys.modules
        or os.environ.get("TEST_MODE") == "1"
        or any("test" in arg.lower() for arg in sys.argv)
    )


async def _get_auth_user(
    request: web.Request,
    body: dict[str, Any] | None = None,
    session = None,
) -> User | None:
    """So'rov yuborgan foydalanuvchini init_data (HMAC) orqali xavfsiz aniqlaydi."""
    body_data = body or {}
    init_data = (
        body_data.get("init_data")
        or request.headers.get("X-Telegram-Init-Data")
        or request.query.get("init_data")
        or ""
    ).strip()
    user_id = (
        body_data.get("user_id")
        or request.headers.get("X-Telegram-User-Id")
        or request.query.get("user_id")
    )
    bot = request.app.get("bot")
    bot_token = bot.token if (bot and hasattr(bot, "token")) else settings.bot.token

    auth_id: int | None = None
    if init_data:
        val = validate_telegram_init_data(init_data, bot_token)
        if val and "user_obj" in val:
            auth_id = val["user_obj"].get("id")
    elif user_id and _is_test_env():
        # Xavfsizlik: faqat sinov/ishlab chiqish rejimida xom user_id ga ruxsat beriladi
        try:
            auth_id = int(user_id)
        except Exception:
            auth_id = None

    if auth_id and session is not None:
        user_repo = UserRepository(session)
        return await user_repo.get_by_telegram_id(auth_id)
    return None



async def handle_api_submit(request: web.Request) -> web.Response:
    """Mini App orqali yuborilgan javoblarni qabul qiladi va hisoblaydi."""
    test_id_str = request.match_info.get("test_id", "")
    if not test_id_str.isdigit():
        return web.json_response({"error": "Yaroqsiz test ID"}, status=400)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Noto'g'ri JSON format"}, status=400)

    raw_answers = (body.get("answers") or "").strip()
    tab_switches = int(body.get("tab_switches") or 0)
    is_disqualified = bool(body.get("disqualified") or False)

    init_data = (body.get("init_data") or "").strip()
    bot = request.app.get("bot")
    bot_token = bot.token if bot else settings.bot.token

    if init_data:
        validated = validate_telegram_init_data(init_data, bot_token)
        if not validated or "user_obj" not in validated:
            return web.json_response(
                {"error": "Xavfsizlik xatosi: Telegram WebApp autentifikatsiyasi tasdiqlanmadi."},
                status=401,
            )

    test_id = int(test_id_str)
    async with get_session() as session:
        catalog = CatalogService(session)
        user_repo = UserRepository(session)
        test = await catalog.tests.get(test_id)
        if test is None:
            return web.json_response({"error": "Test topilmadi"}, status=404)

        user = await _get_auth_user(request, body, session)

        if user is None:
            # Mehmon rejimi (botda ro'yxatdan o'tmagan yoki oddiy brauzer)
            correct = 0
            key = test.answer_key or ""
            for i in range(min(len(key), len(raw_answers))):
                if key[i].upper() == raw_answers[i].upper():
                    correct += 1
            total = len(key) if key else len(raw_answers)
            pct = (correct / total * 100) if total else 0.0
            return web.json_response({
                "ok": True,
                "score": correct,
                "total": total,
                "percentage": round(pct, 1),
                "guest": True,
            })

        assessment = AssessmentService(session)

        # Allaqachon topshirilgan bo'lsa tekshirish
        try:
            submit = await assessment.submit(
                test,
                user,
                raw_answers,
                tab_switches_count=tab_switches,
                is_disqualified=is_disqualified,
            )
        except AlreadyAnsweredError:
            # Foydalanuvchiga xatolik emas, oxirgi urinishini chiroyli ko'rsatamiz
            from modules.assessment.repository import AttemptRepository
            attempt_repo = AttemptRepository(session)
            attempt_page = await attempt_repo.list_by_user(user.id, page=1, per_page=10)
            matching = [a for a in attempt_page.items if a.test_id == test.id and a.is_finished]
            if matching:
                last_attempt = matching[0]
                return web.json_response({
                    "ok": True,
                    "already_answered": True,
                    "score": last_attempt.score,
                    "total": last_attempt.max_score,
                    "percentage": round(last_attempt.percentage, 1),
                    "passed": last_attempt.is_passed,
                    "attempt_id": last_attempt.id,
                    "message": "Siz ushbu testni allaqachon topshirgansiz!",
                })
            return web.json_response({"error": "Siz bu testga allaqachon javob bergansiz."}, status=400)
        except TestLabError as e:
            return web.json_response({"error": e.user_text()}, status=400)

        # Telegram chatga hisobotni yuboramiz
        bot = request.app.get("bot")
        if bot is not None:
            try:
                from apps.bot.keyboards.inline import notification_keyboard, result_keyboard
                from modules.assessment.repository import AttemptRepository
                from modules.certification.service import CertificateService

                if is_disqualified:
                    msg_text = (
                        f"🚨 <b>Test qoidabuzarlik sababli bekor qilindi!</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n\n"
                        f"📌 Test kodi: <b>{test.number}</b> ({test.title})\n"
                        f"⚠️ <b>Sabab:</b> Siz test jarayonida {tab_switches} marta test oynasidan chiqdingiz (boshqa ilovaga o‘tdingiz).\n\n"
                        f"📊 Natijangiz: <b>0 ball (Bekor qilingan)</b>\n"
                        f"ℹ️ Bu haqda o‘qituvchi hisobotida qayd etildi."
                    )
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=msg_text,
                    )
                else:
                    certificates = CertificateService(session)
                    can_certify, _ = await certificates.can_issue(submit.attempt, submit.test)

                    hide_keys = test.should_hide_answers

                    kb = result_keyboard(
                        submit.test.id,
                        attempt_id=submit.attempt.id,
                        can_get_certificate=can_certify,
                        hide_analysis=hide_keys,
                    )
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=uz.result(submit, hide_keys=hide_keys),
                        reply_markup=kb,
                    )

                # Muallifga bildirishnoma (faqat rasmiy 1-urinishda)
                if not getattr(submit.attempt, "is_practice", False) and test.author_id and test.author_id != user.id:
                    author = await user_repo.get(test.author_id)
                    if author and author.notifications_enabled and not author.is_banned:
                        try:
                            await bot.send_message(
                                author.telegram_id,
                                uz.teacher_notification(submit, user),
                                reply_markup=notification_keyboard(test.id),
                            )
                        except Exception:
                            pass

                # Ota-ona / repetitorlarga bildirishnoma (faqat rasmiy 1-urinishda)
                if not getattr(submit.attempt, "is_practice", False):
                    parents = await user_repo.get_parent_links(user.id)
                    for link in parents:
                        try:
                            await bot.send_message(
                                link.parent_telegram_id,
                                uz.parent_notification(submit, user),
                            )
                        except Exception:
                            pass

            except Exception as notify_err:
                log.warning("Mini App orqali yuborilgan natijani botga chiqarishda xato: %s", notify_err)

        total_q = len(submit.questions) if submit.questions else (submit.test.questions_count or 1)
        return web.json_response({
            "ok": True,
            "is_practice": getattr(submit.attempt, "is_practice", False),
            "attempt_number": getattr(submit.attempt, "attempt_number", 1),
            "score": submit.correct,
            "total": total_q,
            "percentage": round(submit.percentage, 1),
            "passed": submit.passed,
            "attempt_id": submit.attempt.id,
            "disqualified": is_disqualified,
            "tab_switches": tab_switches,
        })


async def handle_analysis_page(request: web.Request) -> web.Response:
    """O'qituvchi uchun savollar tahlili (Gemini AI) Mini App sahifasi."""
    analysis_file = STATIC_DIR / "analysis.html"
    if not analysis_file.exists():
        return web.Response(text="Analysis Mini App sahifasi topilmadi", status=404)
    return web.FileResponse(analysis_file)


async def handle_api_analysis_data(request: web.Request) -> web.Response:
    """Test tahlili uchun to'liq ma'lumotlarni qaytaradi."""
    test_id_str = request.match_info.get("test_id", "")
    if not test_id_str.isdigit():
        return web.json_response({"error": "Yaroqsiz test ID"}, status=400)

    test_id = int(test_id_str)
    async with get_session() as session:
        catalog = CatalogService(session)
        test = await catalog.tests.get(test_id)
        if test is None:
            return web.json_response({"error": "Test topilmadi"}, status=404)

        user = await _get_auth_user(request, session=session)
        if not user or (test.author_id != user.id and not user.is_admin):
            return web.json_response(
                {"error": "Ruxsat etilmadi: Siz ushbu test muallifi emassiz."},
                status=403,
            )

        media_items = await catalog.media.list_by_test(test.id)
        explanations_dict = await catalog.get_explanations(test.id)

        key = test.answer_key or ""
        q_count = len(key) if key else test.questions_count

        explanations_data = {}
        for q_num, exp in explanations_dict.items():
            if q_num > 0:
                explanations_data[str(q_num)] = {
                    "question": q_num,
                    "answer": key[q_num - 1].upper() if (key and q_num <= len(key)) else "",
                    "explanation": exp.explanation_text,
                    "mediaType": exp.media_type,
                    "mediaFileId": exp.media_file_id,
                }

        data = {
            "id": test.id,
            "number": test.number,
            "title": test.title,
            "questionsCount": q_count,
            "answerKey": key,
            "geminiConfigured": bool(settings.gemini.api_key),
            "media": [
                {
                    "id": m.id,
                    "type": m.media_type,
                    "url": f"/api/media/{m.id}",
                }
                for m in media_items
            ],
            "explanations": explanations_data,
        }
        return web.json_response(data)


async def handle_api_analysis_generate(request: web.Request) -> web.Response:
    """Gemini AI API orqali test savollarining yechimlarini tahlil qiladi."""
    test_id_str = request.match_info.get("test_id", "")
    if not test_id_str.isdigit():
        return web.json_response({"ok": False, "error": "Yaroqsiz test ID"}, status=400)

    test_id = int(test_id_str)
    try:
        body = await request.json()
    except Exception:
        body = {}

    api_key = (body.get("apiKey") or settings.gemini.api_key or "").strip()
    if not api_key:
        return web.json_response({
            "ok": False,
            "error": "Gemini API kaliti topilmadi. Iltimos, API kalitini kiriting yoki serverda GEMINI_API_KEY sozlang."
        }, status=400)

    async with get_session() as session:
        catalog = CatalogService(session)
        test = await catalog.tests.get(test_id)
        if test is None:
            return web.json_response({"ok": False, "error": "Test topilmadi"}, status=404)

        user = await _get_auth_user(request, body, session)
        if not user or (test.author_id != user.id and not user.is_admin):
            return web.json_response(
                {"ok": False, "error": "Ruxsat etilmadi: Siz ushbu test muallifi emassiz."},
                status=403,
            )

        media_items = await catalog.media.list_by_test(test.id)
        bot: Bot | None = request.app.get("bot")

        # Rasmlarni yuklab, base64 formatiga o'giramiz
        image_parts = []
        if bot:
            for m in media_items:
                if m.media_type in ("photo", "document") and m.file_id:
                    try:
                        tg_file = await bot.get_file(m.file_id)
                        if tg_file.file_path:
                            buf = io.BytesIO()
                            await bot.download_file(tg_file.file_path, destination=buf)
                            img_bytes = buf.getvalue()
                            b64_data = base64.b64encode(img_bytes).decode("utf-8")
                            mime = "image/jpeg"
                            if tg_file.file_path.endswith(".png"):
                                mime = "image/png"
                            elif tg_file.file_path.endswith(".webp"):
                                mime = "image/webp"
                            image_parts.append({
                                "inline_data": {
                                    "mime_type": mime,
                                    "data": b64_data,
                                }
                            })
                    except Exception as err:
                        log.warning("Media yuklab olishda xatolik (%s): %s", m.id, err)

        key = test.answer_key or ""
        q_count = len(key) if key else test.questions_count

        # Har bir savolning rasmiy to'g'ri kalitini aniq ro'yxat qilib tuzamiz
        key_list = []
        for i in range(min(len(key), q_count)):
            key_list.append(f"• {i+1}-savolning TO'G'RI javobi: '{key[i].upper()}'")
        key_details = "\n".join(key_list)

        prompt = (
            f"Siz professional repetitor, tajribali fan o'qituvchisi va metodistsiz.\n"
            f"Test nomi: '{test.title}'\n"
            f"Savollar soni: {q_count} ta.\n\n"
            f"RASMIY VA QAT'IY JAVOBLAR RO'YXATI:\n"
            f"{key_details}\n\n"
            f"QAT'IY QOIDALAR (GUIDED AI):\n"
            f"1. Siz boshqa variantni to'g'ri deb tanlashingiz QAT'IYAN TAQIQLANADI! Yuqorida ko'rsatilgan har bir savolning to'g'ri javobi (harfi) 100% rasmiy va haqiqiy deb qabul qilinsin.\n"
            f"2. Sening asosiy vazifang — berilgan test varaqasi rasmlaridagi savolni o'qib, aynan nima uchun ko'rsatilgan javob to'g'ri kelishini matematik formulalar, qoidalar yoki mantiqiy xulosalar bilan bosqichma-bosqich o'quvchiga isbotlab berish.\n"
            f"3. Boshqa xato variantlar nima sababdan to'g'ri kelmasligini ham qisqa va lo'nda tushuntiring.\n"
            f"4. Har bir yechim o'zbek tilida, aniq, lo'nda va 2-4 jumlada bo'lsin.\n\n"
            f"Format talabi: Faqat quyidagi JSON strukturasida javob bering:\n"
            f"{{\n"
            f"  \"solutions\": [\n"
            f"    {{\"question\": 1, \"answer\": \"{key[0].upper() if key else 'A'}\", \"explanation\": \"1-savol isboti, formulasi va qoidasi...\"}}\n"
            f"  ]\n"
            f"}}"
        )

        parts = [{"text": prompt}] + image_parts

        model_name = settings.gemini.model or "gemini-flash-lite-latest"
        models_to_try = []
        for m in [model_name, "gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest", "gemini-2.5-flash"]:
            if m and m not in models_to_try:
                models_to_try.append(m)

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        }

        try:
            import aiohttp
            async with aiohttp.ClientSession() as http_client:
                last_err = "Gemini tahlilida xatolik"
                for target_model in models_to_try:
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
                    try:
                        async with http_client.post(gemini_url, json=payload, timeout=aiohttp.ClientTimeout(total=75)) as resp:
                            resp_data = await resp.json()
                            if resp.status == 200:
                                candidates = resp_data.get("candidates", [])
                                if candidates:
                                    content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}").strip()
                                    if content_text.startswith("```"):
                                        content_text = re.sub(r"^```(?:json)?\s*", "", content_text)
                                        content_text = re.sub(r"\s*```$", "", content_text).strip()
                                    parsed_json = json.loads(content_text)
                                    solutions = parsed_json.get("solutions", [])
                                    return web.json_response({
                                        "ok": True,
                                        "solutions": solutions,
                                    })
                            last_err = resp_data.get("error", {}).get("message", f"Gemini API xatosi ({resp.status})")
                            log.warning("Gemini model '%s' bilan xatolik: %s. Boshqa model sinab ko'rilmoqda...", target_model, last_err)
                    except Exception as req_err:
                        last_err = str(req_err)
                        log.warning("Gemini so'rov xatosi (%s): %s", target_model, req_err)

                return web.json_response({"ok": False, "error": last_err}, status=400)

        except Exception as err:
            log.error("Gemini API chaqirishda xato: %s", err, exc_info=True)
            return web.json_response({"ok": False, "error": f"Tahlil jarayonida xatolik: {err}"}, status=500)


async def handle_api_analysis_chat(request: web.Request) -> web.Response:
    """O'qituvchi va Gemini o'rtasida bitta savol yechimini to'g'rilash / takomillashtirish chati."""
    test_id_str = request.match_info.get("test_id", "")
    if not test_id_str.isdigit():
        return web.json_response({"ok": False, "error": "Yaroqsiz test ID"}, status=400)

    test_id = int(test_id_str)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Noto'g'ri so'rov formati"}, status=400)

    q_num = body.get("questionNumber")
    if not q_num or not isinstance(q_num, int):
        return web.json_response({"ok": False, "error": "Savol raqami ko'rsatilmadi"}, status=400)

    teacher_message = (body.get("message") or "").strip()
    if not teacher_message:
        return web.json_response({"ok": False, "error": "Xabar matni bo'sh bo'lmasligi kerak"}, status=400)

    current_explanation = (body.get("currentExplanation") or "").strip()
    api_key = (body.get("apiKey") or settings.gemini.api_key or "").strip()
    if not api_key:
        return web.json_response({
            "ok": False,
            "error": "Gemini API kaliti topilmadi. Kalitni kiriting yoki serverda sozlang."
        }, status=400)

    async with get_session() as session:
        catalog = CatalogService(session)
        test = await catalog.tests.get(test_id)
        if test is None:
            return web.json_response({"ok": False, "error": "Test topilmadi"}, status=404)

        user = await _get_auth_user(request, body, session)
        if not user or (test.author_id != user.id and not user.is_admin):
            return web.json_response(
                {"ok": False, "error": "Ruxsat etilmadi: Siz ushbu test muallifi emassiz."},
                status=403,
            )

        media_items = await catalog.media.list_by_test(test.id)
        bot: Bot | None = request.app.get("bot")

        # Rasmlarni yuklab olamiz
        image_parts = []
        if bot:
            for m in media_items:
                if m.media_type in ("photo", "document") and m.file_id:
                    try:
                        tg_file = await bot.get_file(m.file_id)
                        if tg_file.file_path:
                            buf = io.BytesIO()
                            await bot.download_file(tg_file.file_path, destination=buf)
                            img_bytes = buf.getvalue()
                            b64_data = base64.b64encode(img_bytes).decode("utf-8")
                            mime = "image/jpeg"
                            if tg_file.file_path.endswith(".png"):
                                mime = "image/png"
                            elif tg_file.file_path.endswith(".webp"):
                                mime = "image/webp"
                            image_parts.append({
                                "inline_data": {
                                    "mime_type": mime,
                                    "data": b64_data,
                                }
                            })
                    except Exception as err:
                        log.warning("Media yuklab olishda xatolik (%s): %s", m.id, err)

        key = test.answer_key or ""
        correct_answer = key[q_num - 1].upper() if (len(key) >= q_num) else "?"

        prompt = (
            f"Siz professional repetitor, tajribali fan o'qituvchisi va metodistsiz.\n"
            f"Hozir siz o'qituvchi bilan birgalikda {q_num}-savol yechimini (izohini) muhokama qilyapsiz va takomillashtiryapsiz.\n\n"
            f"TEST MA'LUMOTLARI:\n"
            f"- Test nomi: '{test.title}'\n"
            f"- Savol: {q_num}-savol\n"
            f"- Rasmiy to'g'ri javob varianti: '{correct_answer}'\n\n"
            f"HOZIRGI MAVJUD YECHIM / IZOH:\n"
            f"\"\"\"{current_explanation or '(Hozircha yechim yozilmagan)'}\"\"\"\n\n"
            f"O'QITUVCHINING KO'RSATMASI / E'TIROZI / TAKLIFI:\n"
            f"\"\"\"{teacher_message}\"\"\"\n\n"
            f"QAT'IY QOIDALAR:\n"
            f"1. O'qituvchi bildirgan e'tiroz yoki ko'rsatmani inobatga oling (masalan: formulalarni to'g'rilang, hisob-kitobdagi xatolikni tuzating, soddaroq yoki qisqaroq yozing).\n"
            f"2. Rasmiy to'g'ri javob varianti '{correct_answer}'. Yechim aynan shu variant to'g'riligini mantiqiy va matematik isbotlab berishi shart.\n"
            f"3. Yangilangan yechim o'zbek tilida, aniq, pedagogik jihatdan to'g'ri va o'quvchi uchun tushunarli shaklda bo'lsin.\n"
            f"4. Javobingizni FAQAT quyidagi JSON formatida qaytaring:\n"
            f"{{\n"
            f"  \"updated_explanation\": \"Savolning yangi, to'liq va to'g'rilangan yechim matni...\",\n"
            f"  \"ai_reply\": \"O'qituvchiga qisqa xushmuomala javob (masalan: 'Hisob-kitob qayta tekshirildi va tushuntirish to'g'rilandi')\"\n"
            f"}}"
        )

        parts = [{"text": prompt}] + image_parts

        model_name = settings.gemini.model or "gemini-flash-lite-latest"
        models_to_try = []
        for m in [model_name, "gemini-flash-lite-latest", "gemini-flash-latest", "gemini-pro-latest", "gemini-2.5-flash"]:
            if m and m not in models_to_try:
                models_to_try.append(m)

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.2,
                "response_mime_type": "application/json",
            },
        }

        try:
            import aiohttp
            async with aiohttp.ClientSession() as http_client:
                last_err = "Gemini bilan muloqotda xatolik"
                for target_model in models_to_try:
                    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
                    try:
                        async with http_client.post(gemini_url, json=payload, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                            resp_data = await resp.json()
                            if resp.status == 200:
                                candidates = resp_data.get("candidates", [])
                                if candidates:
                                    content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}").strip()
                                    if content_text.startswith("```"):
                                        content_text = re.sub(r"^```(?:json)?\s*", "", content_text)
                                        content_text = re.sub(r"\s*```$", "", content_text).strip()
                                    parsed_json = json.loads(content_text)
                                    updated_explanation = parsed_json.get("updated_explanation", "").strip()
                                    ai_reply = parsed_json.get("ai_reply", "Izoh yangilandi").strip()
                                    return web.json_response({
                                        "ok": True,
                                        "question": q_num,
                                        "updated_explanation": updated_explanation,
                                        "ai_reply": ai_reply,
                                    })
                            last_err = resp_data.get("error", {}).get("message", f"Gemini API xatosi ({resp.status})")
                            log.warning("Gemini chat model '%s' bilan xatolik: %s", target_model, last_err)
                    except Exception as req_err:
                        last_err = str(req_err)
                        log.warning("Gemini chat so'rov xatosi (%s): %s", target_model, req_err)

                return web.json_response({"ok": False, "error": last_err}, status=400)

        except Exception as err:
            log.error("Gemini chat API chaqirishda xato: %s", err, exc_info=True)
            return web.json_response({"ok": False, "error": f"Chat jarayonida xatolik: {err}"}, status=500)




async def handle_api_analysis_save(request: web.Request) -> web.Response:
    """Mini App orqali yuborilgan yechimlarni bazaga saqlaydi."""
    test_id_str = request.match_info.get("test_id", "")
    if not test_id_str.isdigit():
        return web.json_response({"ok": False, "error": "Yaroqsiz test ID"}, status=400)

    test_id = int(test_id_str)
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Noto'g'ri so'rov formati"}, status=400)

    solutions = body.get("solutions", [])
    if not isinstance(solutions, list):
        return web.json_response({"ok": False, "error": "Yechimlar ro'yxati topilmadi"}, status=400)

    async with get_session() as session:
        catalog = CatalogService(session)
        test = await catalog.tests.get(test_id)
        if test is None:
            return web.json_response({"ok": False, "error": "Test topilmadi"}, status=404)

        user = await _get_auth_user(request, body, session)
        if not user or (test.author_id != user.id and not user.is_admin):
            return web.json_response(
                {"ok": False, "error": "Ruxsat etilmadi: Siz ushbu test muallifi emassiz."},
                status=403,
            )

        from modules.catalog.models import QuestionExplanation
        from sqlalchemy import select

        saved = 0
        for sol in solutions:
            q_num = sol.get("question")
            explanation = (sol.get("explanation") or "").strip()
            if not q_num or not isinstance(q_num, int):
                continue

            stmt = select(QuestionExplanation).where(
                QuestionExplanation.test_id == test.id,
                QuestionExplanation.question_number == q_num,
            )
            res = await session.execute(stmt)
            item = res.scalars().first()
            if item is not None:
                item.explanation_text = explanation
            else:
                item = QuestionExplanation(
                    test_id=test.id,
                    question_number=q_num,
                    explanation_text=explanation,
                    media_type="text",
                )
                session.add(item)
            saved += 1

        await session.commit()
        return web.json_response({"ok": True, "saved_count": saved})


def create_webapp(bot: Bot | None = None) -> web.Application:
    """aiohttp web ilovasini shakllantiradi."""
    app = web.Application()
    if bot is not None:
        app["bot"] = bot
    app.router.add_get("/", lambda r: web.Response(text="TestLab WebApp Running", content_type="text/plain"))
    app.router.add_get("/health", lambda r: web.json_response({"status": "ok"}))
    app.router.add_get("/test/{test_id}", handle_test_page)
    app.router.add_get("/api/test/{test_id}", handle_api_test_data)
    app.router.add_get("/api/media/{media_id}", handle_api_media)
    app.router.add_post("/api/test/{test_id}/submit", handle_api_submit)

    # Gemini AI Savollar Tahlili Mini App marshrutlari
    app.router.add_get("/analysis/{test_id}", handle_analysis_page)
    app.router.add_get("/api/analysis/{test_id}", handle_api_analysis_data)
    app.router.add_post("/api/analysis/{test_id}/generate", handle_api_analysis_generate)
    app.router.add_post("/api/analysis/{test_id}/chat", handle_api_analysis_chat)
    app.router.add_post("/api/analysis/{test_id}/save", handle_api_analysis_save)

    app.router.add_static("/static/", STATIC_DIR)
    return app


create_webapp_app = create_webapp


async def start_webapp_server(
    bot: Bot | None = None,
    host: str = "0.0.0.0",
    port: int = 8088,
) -> web.AppRunner:
    """Web serverni ishga tushiradi."""
    app = create_webapp(bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("🌐 Web App server ishga tushdi: http://%s:%d", host, port)
    return runner