import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
INSTAGRAM = "https://instagram.com/capsula_volos"
PHONE = os.environ.get("MASTER_PHONE", "+375291234567")

HAIR_PRICES = {45:729,50:760,55:790,60:853,65:915,70:961,75:1054,80:1116}


def main_menu():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✨ Подобрать метод — квиз", callback_data="quiz"))
    b.row(
        InlineKeyboardButton(text="💰 Рассчитать стоимость", callback_data="calc"),
        InlineKeyboardButton(text="📅 Записаться", callback_data="book"),
    )
    b.row(
        InlineKeyboardButton(text="📋 Услуги и цены", callback_data="services"),
        InlineKeyboardButton(text="📞 Контакты", callback_data="contacts"),
    )
    b.row(InlineKeyboardButton(text="📸 Instagram", url=INSTAGRAM))
    return b.as_markup()


def back_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="← Главное меню", callback_data="menu"))
    return b.as_markup()


def book_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📅 Записаться", callback_data="book"))
    b.row(InlineKeyboardButton(text="← Меню", callback_data="menu"))
    return b.as_markup()


WELCOME = (
    "💜 Привет, <b>{name}</b>!\n\n"
    "Я — помощник мастера по наращиванию волос <b>Анны</b>\n"
    "📍 Брест · @capsula_volos\n\n"
    "✨ Подберу метод · 💰 Рассчитаю стоимость · 📅 Запишу\n\n"
    "Выбирай 👇"
)

SERVICES_TEXT = (
    "✨ <b>Услуги и цены</b>\n\n"
    "🔥 <b>Горячее капсульное</b>\n"
    "• Работа: 1.6 BYN/капсула\n"
    "• Волосы: от 729 BYN (45 см) до 1116 BYN (80 см)\n"
    "• Время: 3–5 часов · Носка: 3–4 месяца\n\n"
    "💜 <b>Биопротеиновое</b>\n"
    "• Работа: 390 BYN + волосы 80 BYN = <b>470 BYN</b>\n"
    "• Любой объём и длина\n\n"
    "🎀 <b>Ленточное (биоленты)</b>\n"
    "• от 160 BYN\n"
    "• Время: 40–90 мин · Носка: 2–3 месяца\n\n"
    "✂️ <b>Снятие</b>\n"
    "• Капсулы: 0.4 BYN/прядь\n"
    "• Биопротеин: 50 BYN/100г\n\n"
    "🔄 <b>Коррекция</b> — от 80 BYN"
)

CONTACTS_TEXT = (
    "📞 <b>Контакты</b>\n\n"
    "👩 Мастер: <b>Анна</b>\n"
    "📍 Брест (адрес при записи)\n"
    f"📱 {PHONE}\n"
    "📸 @capsula_volos\n\n"
    "Записаться можно прямо здесь 💜"
)

QUIZ_TEXT = (
    "✨ <b>Подбор метода — 3 вопроса</b>\n\n"
    "<b>Вопрос 1:</b> Какая сейчас длина волос?"
)

BOOKING_TEXT = (
    "📅 <b>Запись на процедуру</b>\n\n"
    "Напиши мне:\n"
    "• Своё имя\n"
    "• Телефон\n"
    "• Желаемый метод\n"
    "• Удобную дату и время\n\n"
    f"📱 Или напиши напрямую: {PHONE}\n"
    f"📸 Instagram: @capsula_volos"
)


async def notify_admin(bot: Bot, text: str):
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, text)
        except Exception:
            pass


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан!")
        return

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    @dp.message(CommandStart())
    async def start(message: Message):
        name = message.from_user.first_name or "красавица"
        await message.answer(WELCOME.format(name=name), reply_markup=main_menu())

    @dp.message(Command("help"))
    async def help_cmd(message: Message):
        await message.answer(
            "💜 Команды:\n/start — главное меню\n/services — услуги\n/book — запись",
            reply_markup=main_menu(),
        )

    @dp.message(Command("services"))
    async def services_cmd(message: Message):
        await message.answer(SERVICES_TEXT, reply_markup=book_kb())

    @dp.message(Command("book"))
    async def book_cmd(message: Message):
        await message.answer(BOOKING_TEXT, reply_markup=back_kb())

    @dp.callback_query(F.data == "menu")
    async def cb_menu(cb: CallbackQuery):
        name = cb.from_user.first_name or "красавица"
        await cb.message.edit_text(WELCOME.format(name=name), reply_markup=main_menu())
        await cb.answer()

    @dp.callback_query(F.data == "services")
    async def cb_services(cb: CallbackQuery):
        await cb.message.edit_text(SERVICES_TEXT, reply_markup=book_kb())
        await cb.answer()

    @dp.callback_query(F.data == "contacts")
    async def cb_contacts(cb: CallbackQuery):
        await cb.message.edit_text(CONTACTS_TEXT, reply_markup=back_kb())
        await cb.answer()

    @dp.callback_query(F.data == "book")
    async def cb_book(cb: CallbackQuery):
        await cb.message.edit_text(BOOKING_TEXT, reply_markup=back_kb())
        await cb.answer()
        await notify_admin(
            bot,
            f"📅 Клиент хочет записаться!\n"
            f"👤 {cb.from_user.first_name} @{cb.from_user.username or '—'}\n"
            f"🆔 {cb.from_user.id}"
        )

    @dp.callback_query(F.data == "calc")
    async def cb_calc(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🔥 Капсульное (1.6 BYN/кап)", callback_data="calc_cap"))
        b.row(InlineKeyboardButton(text="💜 Биопротеиновое (470 BYN)", callback_data="calc_bio"))
        b.row(InlineKeyboardButton(text="🎀 Ленточное (от 160 BYN)", callback_data="calc_tape"))
        b.row(InlineKeyboardButton(text="← Назад", callback_data="menu"))
        await cb.message.edit_text(
            "💰 <b>Калькулятор стоимости</b>\n\nВыбери метод:",
            reply_markup=b.as_markup()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_bio")
    async def cb_calc_bio(cb: CallbackQuery):
        await cb.message.edit_text(
            "💜 <b>Биопротеиновое наращивание</b>\n\n"
            "Работа: 390 BYN\nВолосы: +80 BYN\n\n"
            "💰 <b>Итого: 470 BYN</b>\n\n"
            "<i>Объём и длина не влияют на цену</i>",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_tape")
    async def cb_calc_tape(cb: CallbackQuery):
        await cb.message.edit_text(
            "🎀 <b>Ленточное наращивание</b>\n\n"
            "💰 <b>от 160 BYN</b>\n\n"
            "<i>Точная стоимость уточняется на консультации</i>",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_cap")
    async def cb_calc_cap(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        for n in [80, 100, 120, 150, 200]:
            total = round(n * 1.6, 1)
            b.button(
                text=f"{n} капсул = {total} BYN",
                callback_data=f"cap_{n}"
            )
        b.adjust(1)
        b.row(InlineKeyboardButton(text="← Назад", callback_data="calc"))
        await cb.message.edit_text(
            "🔥 <b>Горячее капсульное — 1.6 BYN/капсула</b>\n\nВыбери количество:",
            reply_markup=b.as_markup()
        )
        await cb.answer()

    @dp.callback_query(F.data.startswith("cap_"))
    async def cb_cap_result(cb: CallbackQuery):
        n = int(cb.data.split("_")[1])
        work = round(n * 1.6, 1)
        hair_lines = "\n".join(
            f"• {l} см — итого {work + p:.0f} BYN"
            for l, p in HAIR_PRICES.items()
        )
        await cb.message.edit_text(
            f"🔥 <b>Горячее капсульное — {n} капсул</b>\n\n"
            f"Работа: <b>{work} BYN</b>\n\n"
            f"<b>+ волосы (итого с волосами):</b>\n{hair_lines}\n\n"
            f"<i>Без волос (свои): {work} BYN</i>",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "quiz")
    async def cb_quiz(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="До плеч (до 30 см)", callback_data="q1_short"))
        b.row(InlineKeyboardButton(text="До лопаток (30–45 см)", callback_data="q1_mid"))
        b.row(InlineKeyboardButton(text="Длиннее лопаток (45+ см)", callback_data="q1_long"))
        await cb.message.edit_text(QUIZ_TEXT, reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data.startswith("q1_"))
    async def cb_q2(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="Тонкие / редкие", callback_data=f"q2_thin_{cb.data}"))
        b.row(InlineKeyboardButton(text="Средние", callback_data=f"q2_mid_{cb.data}"))
        b.row(InlineKeyboardButton(text="Густые", callback_data=f"q2_thick_{cb.data}"))
        await cb.message.edit_text(
            "✨ <b>Вопрос 2:</b> Плотность волос?",
            reply_markup=b.as_markup()
        )
        await cb.answer()

    @dp.callback_query(F.data.startswith("q2_"))
    async def cb_q3(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="Хочу длину", callback_data=f"q3_len_{cb.data}"))
        b.row(InlineKeyboardButton(text="Хочу объём / густоту", callback_data=f"q3_vol_{cb.data}"))
        b.row(InlineKeyboardButton(text="Хочу быстро", callback_data=f"q3_fast_{cb.data}"))
        b.row(InlineKeyboardButton(text="Бережный метод", callback_data=f"q3_gentle_{cb.data}"))
        await cb.message.edit_text(
            "✨ <b>Вопрос 3:</b> Чего хочешь добиться?",
            reply_markup=b.as_markup()
        )
        await cb.answer()

    @dp.callback_query(F.data.startswith("q3_"))
    async def cb_result(cb: CallbackQuery):
        d = cb.data
        if "thin" in d or "fast" in d:
            method, icon, price = "Ленточное (биоленты)", "🎀", "от 160 BYN"
            desc = "Биоленты — быстро, бережно, идеально для тонких волос."
        elif "gentle" in d:
            method, icon, price = "Голливудское", "👑", "от 200 BYN"
            desc = "Трессы на косичках — без клея, волосы не пострадают."
        else:
            method, icon, price = "Горячее капсульное", "🔥", "1.6 BYN/капсула"
            desc = "Универсальный метод. Биопротеин, держится 3–4 месяца."
        await cb.message.edit_text(
            f"{icon} <b>Твой метод: {method}</b>\n\n"
            f"💰 {price}\n\n{desc}\n\n"
            "Хочешь записаться? 👇",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.message(F.text)
    async def any_text(message: Message):
        t = message.text.lower()
        if any(w in t for w in ["цен", "сколько", "стоит", "прайс"]):
            await message.answer(SERVICES_TEXT, reply_markup=book_kb())
        elif any(w in t for w in ["запис", "прийти", "приём"]):
            await message.answer(BOOKING_TEXT, reply_markup=back_kb())
        elif any(w in t for w in ["привет", "здравств", "добрый", "hello"]):
            name = message.from_user.first_name or "красавица"
            await message.answer(WELCOME.format(name=name), reply_markup=main_menu())
        else:
            await message.answer(
                "💜 Выбери что тебя интересует 👇",
                reply_markup=main_menu()
            )

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
