"""Foydalanuvchilar repozitoriysi."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from core.datetime_utils import days_ago, local_date, utcnow
from core.logging import get_logger
from core.security.permissions import Role
from infrastructure.database.repository import BaseRepository, Page
from modules.identity.models import User

log = get_logger(__name__)


class UserRepository(BaseRepository[User]):
    """Foydalanuvchilar bilan ishlash."""

    model = User

    # ------------------------------------------------------------------
    #  O'qish
    # ------------------------------------------------------------------

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        clean = username.lstrip("@").strip().lower()
        if not clean:
            return None
        result = await self.session.execute(
            select(User).where(func.lower(User.username) == clean).limit(1)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    #  Yaratish
    # ------------------------------------------------------------------

    async def get_or_create(
        self,
        telegram_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> tuple[User, bool]:
        """
        Foydalanuvchini topadi yoki yaratadi.

        POYGA HIMOYASI
        --------------
        Telegram bir nechta update'ni bir vaqtda yuborishi mumkin
        (foydalanuvchi `/start` ni ikki marta tez bosgan bo'lsa). Har
        biri alohida sessiyada ishlanadi, ikkalasi ham SELECT paytida
        "yo'q" deb ko'radi va ikkalasi ham INSERT qiladi — natijada
        `UNIQUE constraint failed` xatosi chiqadi.

        Yechim: INSERT xato bersa, demak boshqasi ulgurgan. Tranzaksiyani
        yopib, yozuvni qaytadan o'qiymiz.

        `rollback()` — savepoint emas: SQLite WAL rejimida joriy
        tranzaksiya eski suratni ko'rishda davom etadi va qayta o'qish
        yana bo'sh natija qaytarardi.

        Returns:
            (foydalanuvchi, yangi_yaratildimi)
        """
        found = await self.get_by_telegram_id(telegram_id)
        if found is not None:
            return found, False

        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=Role.STUDENT.value,
            last_active_at=utcnow(),
        )
        self.session.add(user)

        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()

            existing = await self.get_by_telegram_id(telegram_id)
            if existing is None:
                #  Boshqa sabab — bu haqiqiy xato, yashirmaymiz
                raise

            log.debug("Bir vaqtda yaratishga urinish: %s", telegram_id)
            return existing, False

        return user, True

    # ------------------------------------------------------------------
    #  Yangilash
    # ------------------------------------------------------------------

    async def touch(self, user: User, *, username: str | None = None) -> None:
        """
        Faollik vaqtini va Telegram ma'lumotlarini yangilaydi.

        Username Telegram tomonda o'zgarishi mumkin — har murojaatda
        tekshirib turamiz, aks holda bazadagi ma'lumot eskirib qoladi.
        """
        user.last_active_at = utcnow()

        if username is not None and username != user.username:
            user.username = username

        await self.session.flush()

    async def set_role(self, user: User, role: str) -> User:
        user.role = role
        await self.session.flush()
        return user

    async def ban(self, user: User, reason: str | None = None) -> User:
        user.is_banned = True
        user.ban_reason = reason
        user.banned_at = utcnow()
        await self.session.flush()
        return user

    async def unban(self, user: User) -> User:
        user.is_banned = False
        user.ban_reason = None
        user.banned_at = None
        await self.session.flush()
        return user

    async def add_xp(self, user: User, amount: int) -> int:
        """XP qo'shadi va yangi qiymatni qaytaradi."""
        user.xp = max(0, user.xp + amount)
        await self.session.flush()
        return user.xp

    async def touch_streak(self, user: User) -> tuple[int, bool]:
        """
        Ketma-ket faol kunlar seriyasini yangilaydi.

        Test yechilganda chaqiriladi — seriya «har kuni test yeching»
        degan ma'noni bildiradi, «har kuni tugma bosing» degan emas.

        HISOB MAHALLIY SANA BO'YICHA
        ----------------------------
        Kunlar `local_date()` bilan solishtiriladi, `utcnow()` bilan
        emas: aks holda O'zbekistonda kechqurun soat 05:00 dan keyin
        yechilgan test allaqachon «ertangi» UTC kuniga tushib, seriya
        haqsiz uzilardi.

        Kecha yechgan bo'lsa    -> seriya o'sadi
        Bugun allaqachon yechgan -> o'zgarmaydi (kuniga bir marta)
        Boshqa har qanday holat  -> seriya 1 dan qayta boshlanadi

        Returns:
            (seriya kunlari, seriya shu chaqiruvda o'sdimi)
        """
        today = local_date()
        last = local_date(user.streak_updated_on) if user.streak_updated_on else None

        #  Bugun allaqachon hisoblangan — ikkinchi test seriyani oshirmaydi
        if last == today:
            return user.streak_days, False

        if last is not None and (today - last).days == 1:
            user.streak_days += 1
        else:
            #  Uzilgan seriya, birinchi test yoki soat noto'g'ri
            #  ko'rsatgan holat — hammasi 1 dan boshlanadi
            user.streak_days = 1

        user.streak_updated_on = utcnow()
        await self.session.flush()
        return user.streak_days, True

    async def promote_admins(self, telegram_ids: set[int]) -> int:
        """
        `.env` dagi adminlarga admin rolini beradi.

        Bot startida chaqiriladi. Bazada bo'lmaganlarga tegmaydi —
        ular `/start` bosganda avtomatik admin bo'ladi.

        Returns:
            Roli o'zgargan foydalanuvchilar soni.
        """
        if not telegram_ids:
            return 0

        return await self.bulk_update(
            where=(
                User.telegram_id.in_(telegram_ids)
                & (User.role != Role.ADMIN.value)
                & (User.role != Role.SUPER_ADMIN.value)
            ),
            role=Role.ADMIN.value,
        )

    # ------------------------------------------------------------------
    #  Qidiruv va ro'yxatlar (admin panel uchun)
    # ------------------------------------------------------------------

    async def search(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 10,
    ) -> Page[User]:
        """
        Ism, familiya, username, telefon yoki ID bo'yicha qidiradi.

        Foydalanuvchi nima yozishini oldindan bilmaymiz — shuning uchun
        hamma maydonda bir vaqtda qidiramiz.
        """
        clean = query.strip().lstrip("@")
        pattern = f"%{clean.lower()}%"

        conditions = [
            func.lower(User.first_name).like(pattern),
            func.lower(User.last_name).like(pattern),
            func.lower(User.username).like(pattern),
            User.phone.like(f"%{clean}%"),
        ]

        #  Raqam kiritilgan bo'lsa — Telegram ID bo'yicha ham qidiramiz
        if clean.isdigit():
            conditions.append(User.telegram_id == int(clean))

        statement = (
            select(User)
            .where(User.deleted_at.is_(None), or_(*conditions))
            .order_by(User.last_active_at.desc().nullslast())
        )
        return await self.paginate(statement, page=page, per_page=per_page)

    async def list_all(
        self,
        *,
        page: int = 1,
        per_page: int = 10,
        role: str | None = None,
        banned: bool | None = None,
        active_since: datetime | None = None,
    ) -> Page[User]:
        """Filtrlangan foydalanuvchilar ro'yxati."""
        statement = select(User).where(User.deleted_at.is_(None))

        if role is not None:
            statement = statement.where(User.role == role)
        if banned is not None:
            statement = statement.where(User.is_banned.is_(banned))
        if active_since is not None:
            statement = statement.where(User.last_active_at >= active_since)

        statement = statement.order_by(User.created_at.desc())
        return await self.paginate(statement, page=page, per_page=per_page)

    async def list_for_export(
        self,
        *,
        role: str | None = None,
        active_since: datetime | None = None,
    ) -> list[User]:
        """Excel hisoboti uchun — sahifalashsiz."""
        statement = select(User).where(User.deleted_at.is_(None))

        if role is not None:
            statement = statement.where(User.role == role)
        if active_since is not None:
            statement = statement.where(User.last_active_at >= active_since)

        result = await self.session.execute(statement.order_by(User.created_at.desc()))
        return list(result.scalars().all())

    async def list_broadcast_targets(
        self,
        *,
        roles: list[str] | None = None,
    ) -> list[int]:
        """
        Ommaviy xabar yuboriladigan Telegram ID'lar.

        Faqat ID qaytadi, butun obyekt emas: 50 000 foydalanuvchini
        model qilib yuklash keraksiz xotira va vaqt sarfi — yuborish
        uchun `telegram_id` dan boshqa hech narsa ishlatilmaydi.

        Chetda qoladiganlar:
          * bloklanganlar — ular bilan aloqa uzilgan,
          * bildirishnomani o'chirganlar — bu ularning tanlovi,
          * o'chirilgan hisoblar.
        """
        statement = select(User.telegram_id).where(
            User.deleted_at.is_(None),
            User.is_banned.is_(False),
            User.notifications_enabled.is_(True),
        )

        if roles:
            statement = statement.where(User.role.in_(roles))

        result = await self.session.execute(statement.order_by(User.id))
        return [int(row[0]) for row in result.all()]

    async def top_by_xp(self, limit: int = 10) -> list[User]:
        """Reyting — XP bo'yicha eng yuqori foydalanuvchilar."""
        statement = (
            select(User)
            .where(
                User.deleted_at.is_(None),
                User.is_banned.is_(False),
                User.show_in_leaderboard.is_(True),
                User.xp > 0,
            )
            .order_by(User.xp.desc(), User.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def xp_rank(self, user: User) -> int:
        """Foydalanuvchining XP bo'yicha o'rni (1 dan boshlab)."""
        higher = await self.session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.deleted_at.is_(None),
                User.is_banned.is_(False),
                User.show_in_leaderboard.is_(True),
                User.xp > user.xp,
            )
        )
        return int(higher or 0) + 1

    async def count_leaderboard_users(self) -> int:
        """Reytingda qatnashayotgan jami foydalanuvchilar soni."""
        count = await self.session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.deleted_at.is_(None),
                User.is_banned.is_(False),
                User.show_in_leaderboard.is_(True),
            )
        )
        return int(count or 0)

    # ------------------------------------------------------------------
    #  Statistika (admin dashboard)
    # ------------------------------------------------------------------

    async def stats(self) -> dict[str, int]:
        """Dashboard uchun asosiy sonlar — bitta so'rovda emas, aniq."""
        total = await self.session.scalar(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None))
        )
        registered = await self.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None), User.is_registered.is_(True))
        )
        banned = await self.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None), User.is_banned.is_(True))
        )
        today = await self.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None), User.last_active_at >= days_ago(1))
        )
        week = await self.session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.deleted_at.is_(None), User.last_active_at >= days_ago(7))
        )
        teachers = await self.session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.deleted_at.is_(None),
                User.role.in_([Role.TEACHER.value, Role.MODERATOR.value,
                               Role.ADMIN.value, Role.SUPER_ADMIN.value]),
            )
        )

        return {
            "total": int(total or 0),
            "registered": int(registered or 0),
            "banned": int(banned or 0),
            "active_today": int(today or 0),
            "active_week": int(week or 0),
            "teachers": int(teachers or 0),
        }

    # ------------------------------------------------------------------
    #  Ota-ona / Repetitor bog'lanishi
    # ------------------------------------------------------------------

    async def link_parent(
        self,
        student_id: int,
        parent_telegram_id: int,
        parent_name: str | None = None,
        relationship_type: str = "parent",
    ):
        """O'quvchiga ota-ona yoki repetitorni ulaydi."""
        from modules.identity.models import ParentStudentLink

        stmt = select(ParentStudentLink).where(
            ParentStudentLink.student_id == student_id,
            ParentStudentLink.parent_telegram_id == parent_telegram_id,
        )
        res = await self.session.execute(stmt)
        link = res.scalars().first()
        if link is not None:
            link.is_active = True
            link.parent_name = parent_name
            link.relationship_type = relationship_type
        else:
            link = ParentStudentLink(
                student_id=student_id,
                parent_telegram_id=parent_telegram_id,
                parent_name=parent_name,
                relationship_type=relationship_type,
                is_active=True,
            )
            self.session.add(link)

        await self.session.commit()
        return link

    async def get_parent_links(self, student_id: int):
        """O'quvchiga ulangan barcha faol ota-ona/repetitorlarni qaytaradi."""
        from modules.identity.models import ParentStudentLink

        stmt = select(ParentStudentLink).where(
            ParentStudentLink.student_id == student_id,
            ParentStudentLink.is_active == True,
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def unlink_parent(self, student_id: int, target_id: int) -> bool:
        """Ota-onani uzadi."""
        from sqlalchemy import or_
        from modules.identity.models import ParentStudentLink

        stmt = select(ParentStudentLink).where(
            ParentStudentLink.student_id == student_id,
            or_(
                ParentStudentLink.parent_telegram_id == target_id,
                ParentStudentLink.id == target_id,
            ),
            ParentStudentLink.is_active == True,
        )
        res = await self.session.execute(stmt)
        link = res.scalars().first()
        if link:
            link.is_active = False
            await self.session.commit()
            return True
        return False

