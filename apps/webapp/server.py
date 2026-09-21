"""
Telegram Mini App (Web App) serveri.

aiohttp.web orqali interaktiv test yechish sahifasini, media proksisini va API'larini taqdim etadi.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

import modules.registry  # noqa: F401 - ensure all ORM models are registered
from apps.bot.texts import uz
from core.config import settings
from core.exceptions import AlreadyAnsweredError, TestLabError
from core.logging import get_logger
from infrastructure.database.engine import get_session
from modules.assessment.service import AssessmentService
from modules.catalog.service import CatalogService
from modules.identity.repository import UserRepository

if TYPE_CHECKING:
    from aiogram import Bot

log = get_logger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Media fayllarini xotirada keshlaymiz: media_id -> (bytes, content_type)
_media_cache: dict[int, tuple[bytes, str]] = {}


async def handle_test_page(request: web.Request) -> web.Response:
    """Interaktiv test yechish sahifasi."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return web.Response(text="Web App sahifasi topilmadi", status=404)
    return web.FileResponse(index_file)


async def handle_api_test_data(request: web.Request) -> web.Response:
    """Test haqidagi ma'lumotlarni JSON formatida qaytaradi."""
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
        return web.Response(body=data, content_type=content_type)

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

            content_type = "image/jpeg"
            if tg_file.file_path.endswith(".png"):
                content_type = "image/png"
            elif tg_file.file_path.endswith(".webp"):
                content_type = "image/webp"

            _media_cache[media_id] = (data, content_type)
            return web.Response(body=data, content_type=content_type)
        except Exception as e:
            log.warning("Media yuklab olishda xato (%s): %s", media_id, e)
            return web.Response(text="Media yuklab olinmadi", status=500)


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
    user_id = body.get("user_id")

    test_id = int(test_id_str)
    async with get_session() as session:
        catalog = CatalogService(session)
        test = await catalog.tests.get(test_id)
        if test is None:
            return web.json_response({"error": "Test topilmadi"}, status=404)

        user = None
        user_repo = UserRepository(session)
        if user_id:
            try:
                user = await user_repo.get_by_telegram_id(int(user_id))
            except Exception:
                user = None

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
            submit = await assessment.submit(test, user, raw_answers)
        except AlreadyAnsweredError:
            # Foydalanuvchiga xatolik emas, oxirgi urinishini chiroyli ko'rsatamiz
            from modules.assessment.repository import AttemptRepository
            attempt_repo = AttemptRepository(session)
            attempts = await attempt_repo.list_by_user(user.id, limit=10)
            matching = [a for a in attempts if a.test_id == test.id and a.is_finished]
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

        # Telegram chatga rasmli hisobotni yuboramiz
        bot = request.app.get("bot")
        if bot is not None:
            try:
                from aiogram.types import BufferedInputFile

                from apps.bot.handlers.student.result import HISTORY_SIZE, _render_card
                from apps.bot.keyboards.inline import notification_keyboard, result_keyboard
                from modules.assessment.repository import AttemptRepository
                from modules.certification.service import CertificateService

                attempts_repo = AttemptRepository(session)
                history = await attempts_repo.recent_percentages(user.id, limit=HISTORY_SIZE)
                certificates = CertificateService(session)
                can_certify, _ = await certificates.can_issue(submit.attempt, submit.test)

                card = _render_card(submit, user, history)
                kb = result_keyboard(
                    submit.test.id,
                    attempt_id=submit.attempt.id,
                    can_get_certificate=can_certify,
                )
                if card:
                    photo = BufferedInputFile(card, filename=f"result_{submit.attempt.id}.png")
                    await bot.send_photo(
                        chat_id=user.telegram_id,
                        photo=photo,
                        caption=uz.result(submit),
                        reply_markup=kb,
                    )
                else:
                    await bot.send_message(
                        chat_id=user.telegram_id,
                        text=uz.result(submit),
                        reply_markup=kb,
                    )

                # Muallifga bildirishnoma
                if test.author_id and test.author_id != user.id:
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

                # Ota-ona / repetitorlarga bildirishnoma
                parents = await user_repo.get_parent_links(user.id)
                for link in parents:
                    parent_user = await user_repo.get(link.parent_user_id)
                    if parent_user:
                        try:
                            await bot.send_message(
                                parent_user.telegram_id,
                                uz.parent_result_notification(submit, user),
                            )
                        except Exception:
                            pass

            except Exception as notify_err:
                log.warning("Mini App orqali yuborilgan natijani botga chiqarishda xato: %s", notify_err)

        total_q = len(submit.questions) if submit.questions else (submit.test.questions_count or 1)
        return web.json_response({
            "ok": True,
            "score": submit.correct,
            "total": total_q,
            "percentage": round(submit.percentage, 1),
            "passed": submit.passed,
            "attempt_id": submit.attempt.id,
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

        prompt = (
            f"Siz mahoratli repetitor va metodist o'qituvchisiz.\n"
            f"Test nomi: '{test.title}'\n"
            f"Savollar soni: {q_count} ta.\n"
            f"To'g'ri javoblar kaliti: '{key.upper()}'.\n\n"
            f"VAZIFA:\n"
            f"Berilgan test varaqasi rasmi(lari)dagi savollarni diqqat bilan o'qing.\n"
            f"Har bir savol uchun (1 dan {q_count} gacha) nima sababdan aynan shu javob to'g'riligini "
            f"o'quvchiga o'zbek tilida bosqichma-bosqich, ravon va tushunarli qilib yechimini yozing.\n"
            f"Har bir savol yechimi 1-3 ta lo'nda va aniq jumlalardan iborat bo'lsin.\n\n"
            f"Format talabi: Quyidagi JSON strukturasida javob bering:\n"
            f"{{\n"
            f"  \"solutions\": [\n"
            f"    {{\"question\": 1, \"answer\": \"A\", \"explanation\": \"Yechim tushuntirishi...\"}},\n"
            f"    {{\"question\": 2, \"answer\": \"B\", \"explanation\": \"Yechim tushuntirishi...\"}}\n"
            f"  ]\n"
            f"}}"
        )

        parts = [{"text": prompt}] + image_parts

        model_name = settings.gemini.model or "gemini-3.5-flash-lite"
        models_to_try = []
        for m in [model_name, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-latest"]:
            if m and m not in models_to_try:
                models_to_try.append(m)

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.3,
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
                        async with http_client.post(gemini_url, json=payload, timeout=aiohttp.ClientTimeout(total=50)) as resp:
                            resp_data = await resp.json()
                            if resp.status == 200:
                                candidates = resp_data.get("candidates", [])
                                if candidates:
                                    content_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
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
    app.router.add_get("/test/{test_id}", handle_test_page)
    app.router.add_get("/api/test/{test_id}", handle_api_test_data)
    app.router.add_get("/api/media/{media_id}", handle_api_media)
    app.router.add_post("/api/test/{test_id}/submit", handle_api_submit)

    # Gemini AI Savollar Tahlili Mini App marshrutlari
    app.router.add_get("/analysis/{test_id}", handle_analysis_page)
    app.router.add_get("/api/analysis/{test_id}", handle_api_analysis_data)
    app.router.add_post("/api/analysis/{test_id}/generate", handle_api_analysis_generate)
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