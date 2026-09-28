"""
Javob berish va baholash — biznes mantiq.

Kalit rejimida "urinish" bir zumda yakunlanadi: o'quvchi testni
qog'ozda/rasmdan yechib bo'lgan, botga faqat javoblarini yuboradi.
Shuning uchun vaqt hisoblanmaydi va oraliq holat saqlanmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.datetime_utils import fmt_duration, utcnow
from core.exceptions import (
    AlreadyAnsweredError,
    PermissionDeniedError,
    TestNotAvailableError,
    ValidationError,
)
from core.logging import get_logger
from core.security.permissions import Permission
from modules.assessment.models import (
    Attempt,
    AttemptStatus,
    StudentMistake,
    grade_for,
)
from modules.assessment.repository import AttemptRepository

from modules.catalog.answer_key import BLANK, compare, parse_answers
from modules.catalog.models import Test
from modules.catalog.repository import TestRepository
from modules.identity.models import User
from modules.identity.repository import UserRepository

log = get_logger(__name__)

# --- XP mukofotlari ---
XP_FINISHED = 5
XP_PER_CORRECT = 2
XP_PASSED_BONUS = 15
XP_PERFECT_BONUS = 50
XP_STREAK_BONUS = 5      # seriya o'sgan kunda (2-kundan boshlab)


@dataclass(slots=True)
class QuestionResult:
    """Bitta savol bo'yicha natija."""

    number: int
    given: str | None      # o'quvchi tanlagan harf (katta), javobsiz bo'lsa None
    correct: str           # to'g'ri javob (katta harf)
    verdict: bool | None   # True / False / None (javobsiz)
    original_number: int | None = None

    @property
    def icon(self) -> str:
        if self.verdict is True:
            return "✅"
        if self.verdict is False:
            return "❌"
        return "➖"

    @property
    def points(self) -> int:
        return 1 if self.verdict is True else 0


@dataclass(slots=True)
class Recalculated:
    """
    Kalit tuzatilgach o'zgargan natija.

    O'quvchiga xabar yuborish uchun kerak: «Natijangiz yangilandi».
    """

    attempt: Attempt
    user: User
    before: float
    after: float
    was_passed: bool
    now_passed: bool

    @property
    def improved(self) -> bool:
        return self.after > self.before

    @property
    def newly_passed(self) -> bool:
        """Ilgari o'tmagan edi, endi o'tdi."""
        return self.now_passed and not self.was_passed


@dataclass(slots=True)
class SubmitResult:
    """Tekshiruvdan keyingi to'liq natija."""

    attempt: Attempt
    test: Test
    questions: list[QuestionResult]
    correct: int
    wrong: int
    skipped: int
    percentage: float
    grade: str
    passed: bool
    xp_earned: int
    rank: int
    participants: int
    streak: int = 0
    streak_grew: bool = False
    tab_switches_count: int = 0
    is_disqualified: bool = False


class AssessmentService:
    """Javoblarni qabul qilish va baholash."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.attempts = AttemptRepository(session)
        self.tests = TestRepository(session)
        self.users = UserRepository(session)

    # ==================================================================
    #  TEKSHIRUVLAR
    # ==================================================================

    async def ensure_can_answer(self, test: Test, user: User) -> None:
        """
        Foydalanuvchi bu testga javob bera oladimi?

        Raises:
            PermissionDeniedError / TestNotAvailableError / AlreadyAnsweredError
        """
        if not user.can(Permission.TEST_SOLVE):
            raise PermissionDeniedError("Test yechish uchun ro'yxatdan o'ting.")

        reason = test.closed_reason()
        if reason:
            raise TestNotAvailableError(reason)

        if not test.answer_key:
            raise TestNotAvailableError("Bu testda javoblar kaliti yo'q.")

        if test.max_attempts > 0:
            used = await self.attempts.count_by_user_and_test(user.id, test.id)
            if used >= test.max_attempts:
                raise AlreadyAnsweredError(
                    "Siz bu testga allaqachon javob bergansiz.",
                    hint=(
                        f"Har bir testga faqat <b>{test.max_attempts} marta</b> "
                        f"javob berish mumkin."
                    ),
                )

        if test.classroom_id is not None:
            from modules.classroom.repository import ClassroomRepository

            cls_repo = ClassroomRepository(self.session)
            is_mem = await cls_repo.is_member(test.classroom_id, user.id)
            if not is_mem and test.author_id != user.id and not user.is_admin:
                cls_obj = await cls_repo.get(test.classroom_id)
                cls_name = cls_obj.name if cls_obj else "Yopiq sinf"
                raise TestNotAvailableError(
                    f"🔒 Ushbu test faqat <b>«{cls_name}»</b> guruhi o'quvchilari uchun mo'ljallangan.",
                    hint="Guruhga a'zo bo'lish uchun o'qituvchingizdan taklif havolasini oling.",
                )

    # ==================================================================
    #  VAQT CHEGARASI
    # ==================================================================

    async def begin(self, test: Test, user: User) -> Attempt | None:
        """
        Vaqt hisobini boshlaydi.

        NIMA UCHUN ALOHIDA QADAM
        ------------------------
        Vaqt chegarasi bo'lgan testda "qachon boshlandi" degan savolga
        javob kerak. Uni FSM'da saqlash ishonchsiz: bot qayta ishga
        tushsa yoki o'quvchi boshqa qurilmadan kirsa — yo'qoladi.

        Shuning uchun BAZADA `IN_PROGRESS` urinish yaratiladi. Uning
        `deadline` maydoni muddatni belgilaydi.

        Vaqt chegarasi yo'q bo'lsa hech narsa yaratilmaydi — ortiqcha
        yozuv saqlashning hojati yo'q.

        Returns:
            Boshlangan urinish, yoki None (vaqt cheklanmagan bo'lsa).
        """
        #  Yakunlanmagan urinish bormi? Bo'lsa davom ettiramiz.
        #  Agar muddati o'tib ketgan bo'lsa — uni yopib yangi tekshiramiz.
        active = await self.attempts.get_active(user.id, test.id)
        if active is not None:
            if active.is_expired:
                await self.expire(active)
            else:
                return active

        if test.time_limit_sec <= 0 and not test.is_randomized:
            return None

        now = utcnow()
        deadline = now + timedelta(seconds=test.time_limit_sec) if test.time_limit_sec > 0 else None

        question_order_str = None
        effective_key = None
        max_score = len(test.key_letters) or 1

        if test.is_randomized and test.key_letters:
            import random
            total_q = len(test.key_letters)
            k = test.random_questions_count
            if k and 0 < k < total_q:
                order = random.sample(range(1, total_q + 1), k)
            else:
                order = list(range(1, total_q + 1))
                random.shuffle(order)
            question_order_str = ",".join(map(str, order))
            effective_key = "".join(test.key_letters[i - 1] for i in order)
            max_score = len(order)

        return await self.attempts.create(
            test_id=test.id,
            user_id=user.id,
            status=AttemptStatus.IN_PROGRESS.value,
            started_at=now,
            deadline=deadline,
            max_score=max_score,
            question_order=question_order_str,
            effective_key=effective_key,
        )

    async def expire(self, attempt: Attempt) -> Attempt:
        """
        Muddati o'tgan urinishni yopadi.

        Natija 0 — javob yuborilmagan. Lekin urinish SANALADI
        (`EXPIRED` ham yakunlangan holat): vaqtida ulgurmaslik ham
        natija, aks holda o'quvchi testni ochib tashlab ketib, keyin
        yangi urinish olaverardi.

        `finished_at` hozirgi vaqt emas, `deadline` qilib qo'yiladi —
        urinish aslida o'sha payt tugagan. Fon vazifasi kechikib
        ishlagani natija tarixini buzmasligi kerak.
        """
        reference = attempt.deadline or utcnow()

        return await self.attempts.update_fields(
            attempt,
            status=AttemptStatus.EXPIRED.value,
            finished_at=reference,
            duration_sec=max(0, int((reference - attempt.started_at).total_seconds())),
            score=0,
            percentage=0.0,
            grade=grade_for(0.0)[0],
            is_passed=False,
            correct_count=0,
            wrong_count=0,
            skipped_count=attempt.max_score,
        )

    async def expire_overdue(self, *, limit: int = 200) -> list[Attempt]:
        """
        Muddati o'tgan BARCHA urinishlarni yopadi (fon vazifasi).

        Returns:
            Yopilgan urinishlar — o'quvchiga xabar yuborish uchun.
        """
        overdue = await self.attempts.list_overdue(limit=limit)
        if not overdue:
            return []

        for attempt in overdue:
            await self.expire(attempt)

        #  Keshlangan statistika endi eskirdi — faqat tegilgan
        #  testlarni qayta hisoblaymiz, hammasini emas
        for test_id in {attempt.test_id for attempt in overdue}:
            test = await self.tests.get(test_id)
            if test is not None:
                await self.tests.refresh_stats(test)

        log.info("⏳ Muddati o'tgan %d ta urinish yopildi", len(overdue))
        return overdue

    # ==================================================================
    #  JAVOB BERISH
    # ==================================================================

    async def submit(
        self,
        test: Test,
        user: User,
        raw: str,
        *,
        tab_switches_count: int = 0,
        is_disqualified: bool = False,
    ) -> SubmitResult:
        """
        Javoblarni qabul qiladi, tekshiradi va natijani qaytaradi.
        """
        await self.ensure_can_answer(test, user)

        #  --- Vaqt chegarasi ---
        #  `begin()` ochib qo'ygan urinish bo'lsa, javoblar O'SHA yozuvga
        #  yoziladi. Ilgari bu yerda har safar YANGI qator yaratilardi va
        #  ochilgan urinish `IN_PROGRESS` holatida abadiy osilib qolardi.
        active = await self.attempts.get_active(user.id, test.id)

        if active is not None and active.is_expired:
            await self.expire(active)
            raise TestNotAvailableError(
                "⏳ Vaqt tugadi — javoblaringiz qabul qilinmadi.",
                hint=(
                    f"Bu testga <b>{fmt_duration(test.time_limit_sec)}</b> "
                    f"vaqt berilgan edi."
                ),
            )

        # Random test bo'lsa, aynan shu urinishga biriktirilgan aralashtirilgan kalitni olamiz
        if active is not None and active.effective_key:
            key = active.effective_key
        elif test.is_randomized:
            active = await self.begin(test, user)
            key = active.effective_key if (active and active.effective_key) else test.key_letters
        else:
            key = test.key_letters

        expected = len(key)

        parsed = parse_answers(raw, expected=expected)

        if parsed.is_empty and not is_disqualified:
            raise ValidationError(
                "Hech qanday javob topilmadi.",
                hint="Kamida bitta savolga javob bering.",
            )

        #  Test raqami ko'rsatilgan bo'lsa — mos kelishini tekshiramiz.
        #  Aks holda o'quvchi 12-testning javobini 13-testga yuborib
        #  qo'yishi va nima uchun 0% olganini tushunmasligi mumkin.
        if parsed.test_number is not None and parsed.test_number != test.number:
            raise ValidationError(
                f"Siz <b>{parsed.test_number}</b>-testga javob yubordingiz, "
                f"lekin hozir <b>{test.number}</b>-test ochiq.",
                hint="Javoblarni test raqamisiz yuboring yoki to'g'ri raqamni yozing.",
            )

        order_map = [int(x) for x in active.question_order.split(",") if x.isdigit()] if (active and active.question_order) else None
        results, correct, wrong, skipped = self._grade(key, parsed.letters, order_map=order_map)

        max_score = expected or 1

        if is_disqualified:
            final_correct = 0
            final_wrong = max_score
            final_skipped = 0
            percentage = 0.0
            grade = "F"
            passed = False
            status = AttemptStatus.CANCELLED.value
        else:
            final_correct = correct
            final_wrong = wrong
            final_skipped = skipped
            percentage = round(correct / max_score * 100, 1)
            grade = grade_for(percentage)[0]
            passed = percentage >= test.pass_score
            status = AttemptStatus.FINISHED.value

        now = utcnow()
        result_fields = dict(
            status=status,
            submitted_key=parsed.letters,
            finished_at=now,
            score=final_correct,
            max_score=max_score,
            percentage=percentage,
            grade=grade,
            is_passed=passed,
            correct_count=final_correct,
            wrong_count=final_wrong,
            skipped_count=final_skipped,
            tab_switches_count=tab_switches_count,
            is_disqualified=is_disqualified,
        )

        if active is not None:
            #  Vaqt chegarasi bor edi — haqiqiy davomiylik ma'lum
            attempt = await self.attempts.update_fields(
                active,
                duration_sec=max(0, int((now - active.started_at).total_seconds())),
                **result_fields,
            )
        else:
            #  Kalit rejimi: o'quvchi testni qog'ozda yechgan, botga
            #  faqat javoblarini yuboradi — davomiylik o'lchanmaydi
            attempt = await self.attempts.create(
                test_id=test.id,
                user_id=user.id,
                started_at=now,
                duration_sec=0,
                **result_fields,
            )

        await self.attempts.refresh(attempt, "test", "user")
        await self.tests.refresh_stats(test)

        # Xatolar daftariga yozish (faqat diskvalifikatsiya bo'lmagan bo'lsa)
        if not is_disqualified:
            for q in results:
                if q.verdict is not True:
                    real_q_num = q.original_number if q.original_number is not None else q.number
                    stmt = select(StudentMistake).where(
                        StudentMistake.user_id == user.id,
                        StudentMistake.test_id == test.id,
                        StudentMistake.question_number == real_q_num,
                        StudentMistake.is_resolved == False,
                    )
                    existing_res = await self.session.execute(stmt)
                    existing = existing_res.scalars().first()
                    if existing is not None:
                        existing.given_answer = q.given or "-"
                        existing.correct_answer = q.correct
                        existing.attempt_id = attempt.id
                    else:
                        mistake = StudentMistake(
                            user_id=user.id,
                            test_id=test.id,
                            attempt_id=attempt.id,
                            question_number=real_q_num,
                            given_answer=q.given or "-",
                            correct_answer=q.correct,
                            is_resolved=False,
                        )
                        self.session.add(mistake)

            streak, streak_grew = await self.users.touch_streak(user)
            xp = await self._award_xp(user, attempt, streak_grew=streak_grew)
        else:
            streak = getattr(user, "streak_days", 0)
            streak_grew = False
            xp = 0

        rank, participants = await self.attempts.rank_in_test(attempt)

        log.info(
            "Javob: user=%s test=№%s natija=%s%% (%d/%d) o'rin=%d anti_cheat=(switches=%d, disq=%s)",
            user.telegram_id, test.number, percentage, final_correct, max_score, rank,
            tab_switches_count, is_disqualified,
        )

        return SubmitResult(
            attempt=attempt,
            test=test,
            questions=results,
            correct=final_correct,
            wrong=final_wrong,
            skipped=final_skipped,
            percentage=percentage,
            grade=grade,
            passed=passed,
            xp_earned=xp,
            rank=rank,
            participants=participants,
            streak=streak,
            streak_grew=streak_grew,
            tab_switches_count=tab_switches_count,
            is_disqualified=is_disqualified,
        )

    async def get_mistakes(self, user_id: int, test_id: int | None = None) -> list[StudentMistake]:
        """Foydalanuvchining hal qilinmagan xatolarini qaytaradi."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        stmt = (
            select(StudentMistake)
            .where(StudentMistake.user_id == user_id, StudentMistake.is_resolved == False)
        )
        if test_id is not None:
            stmt = stmt.where(StudentMistake.test_id == test_id)

        stmt = stmt.options(selectinload(StudentMistake.test)).order_by(StudentMistake.created_at.desc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count_mistakes(self, user_id: int, test_id: int | None = None) -> int:
        """Hal qilinmagan xatolar soni."""
        from sqlalchemy import func, select

        stmt = (
            select(func.count())
            .select_from(StudentMistake)
            .where(StudentMistake.user_id == user_id, StudentMistake.is_resolved == False)
        )
        if test_id is not None:
            stmt = stmt.where(StudentMistake.test_id == test_id)

        total = await self.session.scalar(stmt)
        return int(total or 0)

    async def resolve_mistake(
        self,
        user_id: int,
        test_id_or_mistake_id: int,
        question_number: int | None = None,
    ) -> bool:
        """Xatoni yechildi deb belgilaydi."""
        from sqlalchemy import select

        if question_number is None:
            stmt = select(StudentMistake).where(
                StudentMistake.id == test_id_or_mistake_id,
                StudentMistake.user_id == user_id,
                StudentMistake.is_resolved == False,
            )
        else:
            stmt = select(StudentMistake).where(
                StudentMistake.user_id == user_id,
                StudentMistake.test_id == test_id_or_mistake_id,
                StudentMistake.question_number == question_number,
                StudentMistake.is_resolved == False,
            )
        res = await self.session.execute(stmt)
        mistakes_to_resolve = list(res.scalars().all())
        if mistakes_to_resolve:
            now_dt = utcnow()
            for mistake in mistakes_to_resolve:
                mistake.is_resolved = True
                mistake.resolved_at = now_dt
            await self.session.commit()
            return True
        return False

    async def clear_mistakes(self, user_id: int) -> int:
        """Foydalanuvchining barcha xatolarini tozalaydi."""
        from sqlalchemy import update

        stmt = (
            update(StudentMistake)
            .where(StudentMistake.user_id == user_id, StudentMistake.is_resolved == False)
            .values(is_resolved=True, resolved_at=utcnow())
        )
        res = await self.session.execute(stmt)
        await self.session.commit()
        return res.rowcount or 0

    # ==================================================================
    #  BAHOLASH
    # ==================================================================


    @staticmethod
    def _grade(
        key: str,
        submitted: str,
        *,
        order_map: list[int] | None = None,
    ) -> tuple[list[QuestionResult], int, int, int]:
        """
        Javoblarni solishtiradi va savolma-savol natija tuzadi.

        Returns:
            (natijalar, to'g'ri, xato, javobsiz)
        """
        verdicts = compare(key, submitted)

        results: list[QuestionResult] = []
        correct = wrong = skipped = 0

        for index, verdict in enumerate(verdicts):
            given = submitted[index] if index < len(submitted) else BLANK

            if verdict is True:
                correct += 1
            elif verdict is False:
                wrong += 1
            else:
                skipped += 1

            orig_num = order_map[index] if (order_map and index < len(order_map)) else (index + 1)
            results.append(
                QuestionResult(
                    number=index + 1,
                    given=None if given == BLANK else given.upper(),
                    correct=key[index].upper(),
                    verdict=verdict,
                    original_number=orig_num,
                )
            )

        return results, correct, wrong, skipped

    async def _award_xp(
        self,
        user: User,
        attempt: Attempt,
        *,
        streak_grew: bool = False,
    ) -> int:
        """Natijaga qarab XP beradi."""
        earned = XP_FINISHED + attempt.correct_count * XP_PER_CORRECT

        if attempt.is_passed:
            earned += XP_PASSED_BONUS
        if attempt.percentage >= 100:
            earned += XP_PERFECT_BONUS

        #  Seriya bonusi faqat u haqiqatan o'sganda beriladi. Birinchi
        #  kun (seriya = 1) bonussiz: aks holda «seriya» so'zi ma'nosini
        #  yo'qotadi — har kim birinchi testidayoq oladi.
        if streak_grew and user.streak_days >= 2:
            earned += XP_STREAK_BONUS

        await self.users.add_xp(user, earned)
        return earned

    # ==================================================================
    #  QAYTA HISOBLASH (kalit tuzatilganda)
    # ==================================================================

    async def recalculate_all(self, test: Test) -> list[Recalculated]:
        """
        Testning BARCHA natijalarini yangi kalit bo'yicha qayta hisoblaydi.

        NIMA UCHUN KERAK
        ----------------
        O'qituvchi kalitda adashsa (7-savolni C o'rniga B deb belgilasa),
        30 ta o'quvchi haqsiz "xato" oladi. Ilgari yagona yechim — testni
        o'chirib qaytadan boshlash edi.

        Endi kalit tuzatiladi va hamma natija qayta hisoblanadi.
        Bu **ishonch** masalasi: o'qituvchi xato qilishdan qo'rqmaydi.

        Returns:
            Faqat O'ZGARGAN natijalar ro'yxati (xabar yuborish uchun).
        """
        key = test.key_letters
        if not key:
            return []

        attempts = await self.attempts.list_all_by_test(test.id)
        changes: list[Recalculated] = []

        for attempt in attempts:
            before_percentage = attempt.percentage
            before_passed = attempt.is_passed

            if attempt.question_order:
                order = [int(x) for x in attempt.question_order.split(",") if x.isdigit()]
                effective_key = "".join(key[i - 1] for i in order if 0 < i <= len(key))
                attempt.effective_key = effective_key
                attempt_key = effective_key
                max_score = len(order)
                order_map = order
            else:
                attempt_key = key
                max_score = len(key)
                order_map = None

            results, correct, wrong, skipped = self._grade(
                attempt_key, attempt.submitted_key or "", order_map=order_map
            )

            percentage = round(correct / max_score * 100, 1) if max_score else 0.0

            attempt.score = correct
            attempt.max_score = max_score
            attempt.percentage = percentage
            attempt.correct_count = correct
            attempt.wrong_count = wrong
            attempt.skipped_count = skipped
            attempt.grade = grade_for(percentage)[0]
            attempt.is_passed = percentage >= test.pass_score

            if abs(percentage - before_percentage) > 0.05:
                changes.append(Recalculated(
                    attempt=attempt,
                    user=attempt.user,
                    before=before_percentage,
                    after=percentage,
                    was_passed=before_passed,
                    now_passed=attempt.is_passed,
                ))

        await self.session.flush()
        await self.tests.refresh_stats(test)

        log.info(
            "Qayta hisoblandi: test=№%s urinishlar=%d o'zgardi=%d",
            test.number, len(attempts), len(changes),
        )
        return changes

    async def preview_recalculation(
        self,
        test: Test,
        new_key: str,
    ) -> tuple[int, int]:
        """
        Kalit o'zgarsa nechta natija o'zgarishini OLDINDAN hisoblaydi.

        Bazaga tegmaydi — o'qituvchiga tasdiqlashdan oldin ko'rsatiladi:
        «30 ta javob qayta hisoblanadi, 18 tasi o'zgaradi».

        Returns:
            (jami urinishlar, o'zgaradiganlar)
        """
        attempts = await self.attempts.list_all_by_test(test.id)

        if not attempts:
            return 0, 0

        key = new_key.lower()
        max_score = len(key)
        changed = 0

        for attempt in attempts:
            _, correct, _, _ = self._grade(key, attempt.submitted_key or "")
            percentage = round(correct / max_score * 100, 1) if max_score else 0.0
            if abs(percentage - attempt.percentage) > 0.05:
                changed += 1

        return len(attempts), changed

    # ==================================================================
    #  TAHLIL (o'qituvchi uchun)
    # ==================================================================

    async def question_breakdown(self, test: Test) -> list[dict[str, object]]:
        """
        Har bir savol bo'yicha statistika: qaysi savol qiyin bo'lgan.

        Hisob `submitted_key` va `answer_key` ni solishtirish orqali —
        qo'shimcha jadval ham, so'rov ham kerak emas.
        Randomizatsiyalangan testlarda har bir o'quvchining `question_order`i
        bo'yicha haqiqiy savol raqamiga to'g'ri ulanadi.
        """
        key = test.key_letters
        if not key:
            return []

        attempts = await self.attempts.list_all_by_test(test.id)
        total = len(attempts)

        correct = [0] * len(key)
        wrong = [0] * len(key)
        skipped = [0] * len(key)
        presented = [0] * len(key)
        #  Har bir savol uchun: {tanlangan harf -> necha marta}
        chosen: list[dict[str, int]] = [{} for _ in key]

        for attempt in attempts:
            submitted = attempt.submitted_key or ""
            if attempt.question_order:
                order = [int(x) for x in attempt.question_order.split(",") if x.isdigit()]
                for idx, orig_q in enumerate(order):
                    orig_idx = orig_q - 1
                    if 0 <= orig_idx < len(key):
                        presented[orig_idx] += 1
                        given = submitted[idx] if idx < len(submitted) else BLANK
                        expected_letter = key[orig_idx].upper()
                        if given == BLANK:
                            skipped[orig_idx] += 1
                        elif given.upper() == expected_letter:
                            correct[orig_idx] += 1
                        else:
                            wrong[orig_idx] += 1
                            letter = given.upper()
                            chosen[orig_idx][letter] = chosen[orig_idx].get(letter, 0) + 1
            else:
                for index, verdict in enumerate(compare(key, submitted)):
                    if index >= len(key):
                        break
                    presented[index] += 1
                    if verdict is True:
                        correct[index] += 1
                    elif verdict is False:
                        wrong[index] += 1
                        letter = submitted[index].upper()
                        chosen[index][letter] = chosen[index].get(letter, 0) + 1
                    else:
                        skipped[index] += 1

        rows: list[dict[str, object]] = []
        for index in range(len(key)):
            q_presented = presented[index] if presented[index] > 0 else total
            rate = correct[index] / q_presented if q_presented else 0.0

            #  Eng ko'p tanlangan xato variant. Teng bo'lsa alifbo
            #  tartibida — natija yurishdan yurishga o'zgarmasin.
            top_letter, top_count = "", 0
            if chosen[index]:
                top_letter, top_count = max(
                    sorted(chosen[index].items()),
                    key=lambda pair: pair[1],
                )

            rows.append({
                "number": index + 1,
                "correct_letter": key[index].upper(),
                "correct": correct[index],
                "wrong": wrong[index],
                "skipped": skipped[index],
                "rate": rate,
                "note": self._difficulty_note(rate, q_presented),
                "top_wrong": top_letter,
                "top_wrong_count": top_count,
                "suspect_key": self._is_suspect_key(
                    correct=correct[index],
                    top_wrong_count=top_count,
                    participants=q_presented,
                ),
            })

        return rows

    #  Kalit shubhali deb belgilanadigan chegara. Past qo'yilsa har bir
    #  qiyin savol «kalit xato» deb ayblanadi va ogohlantirish qadrini
    #  yo'qotadi — shuning uchun ataylab qattiq.
    SUSPECT_MIN_PARTICIPANTS = 5
    SUSPECT_MAX_CORRECT_RATE = 0.2
    SUSPECT_MIN_AGREEMENT = 0.7

    @classmethod
    def _is_suspect_key(
        cls,
        *,
        correct: int,
        top_wrong_count: int,
        participants: int,
    ) -> bool:
        """
        Kalitning o'zi noto'g'ri bo'lishi mumkinmi?

        Belgisi: deyarli hech kim «to'g'ri» javobni topmagan, LEKIN
        xato qilganlarning katta qismi AYNAN BIR XIL harfni tanlagan.
        Tasodifiy xatolar bunday to'planmaydi — variantlar bo'ylab
        sochilib ketadi. Bir joyga to'planishi ko'pincha o'qituvchi
        kalitni yozayotib adashganini bildiradi.

        Kam ishtirokchida hisob ishonchsiz: 2 kishidan 2 tasi bir xil
        xato qilishi butunlay tasodif bo'lishi mumkin.
        """
        if participants < cls.SUSPECT_MIN_PARTICIPANTS:
            return False
        if correct / participants > cls.SUSPECT_MAX_CORRECT_RATE:
            return False

        return top_wrong_count / participants >= cls.SUSPECT_MIN_AGREEMENT

    @staticmethod
    def _difficulty_note(rate: float, participants: int) -> str:
        """Savol qanchalik qiyin bo'lganini so'z bilan izohlaydi."""
        if participants == 0:
            return "Ma'lumot yo'q"
        if rate >= 0.9:
            return "Juda oson"
        if rate >= 0.7:
            return "Oson"
        if rate >= 0.5:
            return "O'rtacha"
        if rate >= 0.3:
            return "Qiyin"
        return "Juda qiyin ⚠️"
