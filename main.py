import asyncio
import logging
import os
import anthropic as anthropic_sdk

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
INSTAGRAM = "https://instagram.com/capsula_volos"
PHONE = os.environ.get("MASTER_PHONE", "+375291234567")

HAIR_PRICES = {45:729,50:760,55:790,60:853,65:915,70:961,75:1054,80:1116}

AI_SYSTEM = """Ты — умный ассистент мастера по наращиванию волос Анны (@capsula_volos, Брест).
Отвечаешь тепло и профессионально. Знаешь всё об услугах:

УСЛУГИ И ЦЕНЫ:
- Горячее капсульное: 1.6 BYN/капсула + волосы (45см=729р, 50см=760р, 55см=790р, 60см=853р, 65см=915р, 70см=961р, 75см=1054р, 80см=1116р)
- Биопротеиновое: 390 BYN работа + 80 BYN волосы = 470 BYN итого
- Ленточное (биоленты): от 160 BYN
- Голливудское: от 200 BYN
- Коррекция: от 80 BYN
- Снятие капсул: 0.4 BYN/прядь
- Снятие биопротеина: 50 BYN/100г

Отвечай кратко — 2-4 предложения. На русском языке.
Если спрашивают о записи — говори что можно записаться через кнопку «Записаться» в боте.
Не придумывай цены которых нет в списке."""


class AIState(StatesGroup):
    chatting = State()


def main_menu():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✨ Подобрать метод — квиз", callback_data="quiz"))
    b.row(
        InlineKeyboardButton(text="💰 Рассчитать стоимость", callback_data="calc"),
        InlineKeyboardButton(text="📅 Записаться", callback_data="book"),
    )
    b.row(
        InlineKeyboardButton(text="🤖 Спросить ИИ-консультанта", callback_data="ai"),
    )
    b.row(
        InlineKeyboardButton(text="📋 Услуги и цены", callback_data="services"),
        InlineKeyboardButton(text="📞 Контакты", callback_data="contacts"),
    )
    b.row(InlineKeyboardButton(text="📸 Instagram @capsula_volos", url=INSTAGRAM))
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


def ai_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📅 Записаться", callback_data="book"))
    b.row(InlineKeyboardButton(text="← Выйти из чата", callback_data="menu"))
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
    "• Волосы: 729–1116 BYN (45–80 см)\n"
    "• Время: 3–5 ч · Носка: 3–4 мес\n\n"
    "💜 <b>Биопротеиновое</b>\n"
    "• Итого: <b>470 BYN</b> (работа 390 + волосы 80)\n"
    "• Любой объём и длина\n\n"
    "🎀 <b>Ленточное (биоленты)</b>\n"
    "• от 160 BYN · Время: 40–90 мин\n\n"
    "👑 <b>Голливудское</b>\n"
    "• от 200 BYN · Без клея и термо\n\n"
    "✂️ <b>Снятие:</b> капсулы 0.4/прядь · биопротеин 50/100г\n"
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

BOOKING_TEXT = (
    "📅 <b>Запись на процедуру</b>\n\n"
    "Напиши мне:\n"
    "• Имя\n"
    "• Телефон\n"
    "• Метод наращивания\n"
    "• Удобную дату и время\n\n"
    f"📱 Или напрямую: {PHONE}\n"
    "📸 Instagram: @capsula_volos"
)


async def ask_claude(question: str, history: list) -> str:
    if not ANTHROPIC_API_KEY:
        return "ИИ-ассистент пока недоступен. Напишите Анне напрямую! 💜"
    try:
        client = anthropic_sdk.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        messages = history[-6:] + [{"role": "user", "content": question}]
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=AI_SYSTEM,
            messages=messages,
        )
        return resp.content[0].text
    except Exception as e:
        logger.error(f"Claude error: {e}")
        return "Не смогла ответить. Напишите Анне напрямую 💜"


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
    async def start(message: Message, state: FSMContext):
        await state.clear()
        name = message.from_user.first_name or "красавица"
        await message.answer(WELCOME.format(name=name), reply_markup=main_menu())

    @dp.message(Command("help"))
    async def help_cmd(message: Message, state: FSMContext):
        await state.clear()
        await message.answer(
            "💜 Команды:\n/start — главное меню\n/services — услуги\n/book — запись\n/ai — ИИ консультант",
            reply_markup=main_menu(),
        )

    @dp.callback_query(F.data == "menu")
    async def cb_menu(cb: CallbackQuery, state: FSMContext):
        await state.clear()
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
            f"📅 Хочет записаться!\n"
            f"👤 {cb.from_user.first_name} @{cb.from_user.username or '—'}\n"
            f"🆔 {cb.from_user.id}"
        )

    # --- ИИ ---
    @dp.callback_query(F.data == "ai")
    async def cb_ai(cb: CallbackQuery, state: FSMContext):
        await state.set_state(AIState.chatting)
        await state.update_data(history=[])
        await cb.message.edit_text(
            "🤖 <b>ИИ-консультант Анны</b>\n\n"
            "Задай любой вопрос о наращивании!\n"
            "Знаю всё о методах, ценах, уходе.\n\n"
            "<i>Для выхода нажми «Выйти из чата»</i>",
            reply_markup=ai_kb()
        )
        await cb.answer()

    @dp.message(AIState.chatting, F.text)
    async def ai_chat(message: Message, state: FSMContext):
        data = await state.get_data()
        history = data.get("history", [])
        thinking = await message.answer("💭 Думаю...")
        answer = await ask_claude(message.text, history)
        history.append({"role": "user", "content": message.text})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 6:
            history = history[-6:]
        await state.update_data(history=history)
        await thinking.delete()
        await message.answer(answer, reply_markup=ai_kb())

    # --- КАЛЬКУЛЯТОР ---
    @dp.callback_query(F.data == "calc")
    async def cb_calc(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🔥 Капсульное (1.6 BYN/кап)", callback_data="calc_cap"))
        b.row(InlineKeyboardButton(text="💜 Биопротеиновое (470 BYN)", callback_data="calc_bio"))
        b.row(InlineKeyboardButton(text="🎀 Ленточное (от 160 BYN)", callback_data="calc_tape"))
        b.row(InlineKeyboardButton(text="👑 Голливудское (от 200 BYN)", callback_data="calc_holl"))
        b.row(InlineKeyboardButton(text="✂️ Снятие", callback_data="calc_rem"))
        b.row(InlineKeyboardButton(text="← Назад", callback_data="menu"))
        await cb.message.edit_text("💰 <b>Калькулятор стоимости</b>\n\nВыбери метод:", reply_markup=b.as_markup())
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
            "🎀 <b>Ленточное наращивание</b>\n\n💰 <b>от 160 BYN</b>\n\n<i>Точная стоимость уточняется</i>",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_holl")
    async def cb_calc_holl(cb: CallbackQuery):
        await cb.message.edit_text(
            "👑 <b>Голливудское наращивание</b>\n\n💰 <b>от 200 BYN</b>\n\nБез клея и термовоздействия",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_rem")
    async def cb_calc_rem(cb: CallbackQuery):
        await cb.message.edit_text(
            "✂️ <b>Снятие наращивания</b>\n\n"
            "• Капсулы (натуральные): <b>0.4 BYN/прядь</b>\n"
            "  100 прядей = 40 BYN\n\n"
            "• Биопротеин: <b>50 BYN/100г</b>\n"
            "  150г = 75 BYN",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_cap")
    async def cb_calc_cap(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        for n in [80, 100, 120, 150, 200]:
            total = round(n * 1.6, 1)
            b.button(text=f"{n} капсул = {total} BYN", callback_data=f"cap_{n}")
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
        hair_lines = "\n".join(f"• {l} см — итого <b>{work + p:.0f} BYN</b>" for l, p in HAIR_PRICES.items())
        await cb.message.edit_text(
            f"🔥 <b>Горячее капсульное — {n} капсул</b>\n\n"
            f"Работа: <b>{work} BYN</b>\n\n"
            f"<b>Итого с волосами:</b>\n{hair_lines}\n\n"
            f"<i>Без волос (свои): {work} BYN</i>",
            reply_markup=book_kb()
        )
        await cb.answer()

    # --- КВИЗ ---
    @dp.callback_query(F.data == "quiz")
    async def cb_quiz(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="До плеч (до 30 см)", callback_data="q1_short"))
        b.row(InlineKeyboardButton(text="До лопаток (30–45 см)", callback_data="q1_mid"))
        b.row(InlineKeyboardButton(text="Длиннее лопаток (45+ см)", callback_data="q1_long"))
        await cb.message.edit_text(
            "✨ <b>Подбор метода — 3 вопроса</b>\n\n<b>Вопрос 1:</b> Длина волос сейчас?",
            reply_markup=b.as_markup()
        )
        await cb.answer()

    @dp.callback_query(F.data.startswith("q1_"))
    async def cb_q2(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="Тонкие / редкие", callback_data=f"q2_thin|{cb.data}"))
        b.row(InlineKeyboardButton(text="Средние", callback_data=f"q2_mid|{cb.data}"))
        b.row(InlineKeyboardButton(text="Густые", callback_data=f"q2_thick|{cb.data}"))
        await cb.message.edit_text("<b>Вопрос 2:</b> Плотность волос?", reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data.startswith("q2_"))
    async def cb_q3(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="Хочу длину", callback_data=f"q3_len|{cb.data}"))
        b.row(InlineKeyboardButton(text="Хочу объём / густоту", callback_data=f"q3_vol|{cb.data}"))
        b.row(InlineKeyboardButton(text="Хочу быстро", callback_data=f"q3_fast|{cb.data}"))
        b.row(InlineKeyboardButton(text="Бережный метод", callback_data=f"q3_gentle|{cb.data}"))
        await cb.message.edit_text("<b>Вопрос 3:</b> Чего хочешь добиться?", reply_markup=b.as_markup())
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
            f"{icon} <b>Твой метод: {method}</b>\n\n💰 {price}\n\n{desc}\n\nЗаписаться? 👇",
            reply_markup=book_kb()
        )
        await cb.answer()

    # --- СВОБОДНЫЙ ТЕКСТ ---
    @dp.message(F.text)
    async def any_text(message: Message, state: FSMContext):
        current = await state.get_state()
        if current == AIState.chatting:
            return
        t = message.text.lower()
        if any(w in t for w in ["цен", "сколько", "стоит", "прайс"]):
            await message.answer(SERVICES_TEXT, reply_markup=book_kb())
        elif any(w in t for w in ["запис", "прийти", "приём"]):
            await message.answer(BOOKING_TEXT, reply_markup=back_kb())
        elif any(w in t for w in ["привет", "здравств", "добрый", "hello", "hi"]):
            name = message.from_user.first_name or "красавица"
            await message.answer(WELCOME.format(name=name), reply_markup=main_menu())
        else:
            await message.answer("💜 Выбирай что интересует 👇", reply_markup=main_menu())

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Bot started with AI")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
