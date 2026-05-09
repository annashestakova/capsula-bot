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
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
INSTAGRAM = "https://instagram.com/capsula_volos"
PHONE = os.environ.get("MASTER_PHONE", "+375291234567")
CARD = os.environ.get("CARD_NUMBER", "0000 0000 0000 0000")  # твоя карта

HAIR_PRICES = {45:729,50:760,55:790,60:853,65:915,70:961,75:1054,80:1116}

AI_SYSTEM = f"""Ты — умный ассистент мастера по наращиванию волос Анны (@capsula_volos, Брест).
Отвечаешь тепло, профессионально, коротко — 2-4 предложения. На русском.

УСЛУГИ И ЦЕНЫ:
- Горячее капсульное: 1.6 BYN/капсула + волосы отдельно
  Волосы: 45см=729р, 50=760, 55=790, 60=853, 65=915, 70=961, 75=1054, 80=1116 BYN
- Биопротеиновое: работа 390 + волосы 80 = 470 BYN итого
- Ленточное (биоленты): от 200 BYN
- Голливудское: от 200 BYN
- Коррекция: от 80 BYN
- Снятие капсул: 0.4 BYN/прядь
- Снятие биопротеина: 50 BYN/100г

ПРОДУКТЫ:
- Бесплатный чек-лист «Топ-5 вопросов о наращивании» — в боте
- Гайд по уходу за нарощенными волосами — 9 BYN
- Персональная консультация по подбору метода — 19 BYN

Если спрашивают о записи — говори что можно через кнопку «Записаться».
Если о покупке гайда — кнопка «Купить гайд»."""


class AIState(StatesGroup):
    chatting = State()


# ─── КЛАВИАТУРЫ ──────────────────────────────────────────────────────────────

def main_menu():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🎁 Получить бесплатный чек-лист", callback_data="checklist"))
    b.row(InlineKeyboardButton(text="✨ Подобрать метод — квиз", callback_data="quiz"))
    b.row(
        InlineKeyboardButton(text="💰 Рассчитать стоимость", callback_data="calc"),
        InlineKeyboardButton(text="📅 Записаться", callback_data="book"),
    )
    b.row(InlineKeyboardButton(text="🤖 Спросить ИИ-консультанта", callback_data="ai"))
    b.row(
        InlineKeyboardButton(text="📋 Услуги и цены", callback_data="services"),
        InlineKeyboardButton(text="🛍 Магазин", callback_data="shop"),
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
    b.row(InlineKeyboardButton(text="🛍 Купить гайд — 9 BYN", callback_data="buy_guide"))
    b.row(InlineKeyboardButton(text="← Меню", callback_data="menu"))
    return b.as_markup()


def ai_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📅 Записаться", callback_data="book"))
    b.row(InlineKeyboardButton(text="🛍 Купить консультацию — 19 BYN", callback_data="buy_consult"))
    b.row(InlineKeyboardButton(text="← Выйти из чата", callback_data="menu"))
    return b.as_markup()


def shop_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📚 Гайд по уходу — 9 BYN", callback_data="buy_guide"))
    b.row(InlineKeyboardButton(text="💬 Консультация ИИ — 19 BYN", callback_data="buy_consult"))
    b.row(InlineKeyboardButton(text="🎁 Бесплатный чек-лист", callback_data="checklist"))
    b.row(InlineKeyboardButton(text="← Меню", callback_data="menu"))
    return b.as_markup()


def pay_kb(product: str, price: str):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"✅ Я оплатила {price}", callback_data=f"paid_{product}"))
    b.row(InlineKeyboardButton(text="← Назад", callback_data="shop"))
    return b.as_markup()


# ─── ТЕКСТЫ ──────────────────────────────────────────────────────────────────

WELCOME = (
    "💜 Привет, <b>{name}</b>!\n\n"
    "Я — помощник мастера по наращиванию волос <b>Анны</b>\n"
    "📍 Брест · @capsula_volos\n\n"
    "🎁 Забери бесплатный чек-лист прямо сейчас\n"
    "✨ Подберу метод · 💰 Рассчитаю стоимость · 📅 Запишу\n\n"
    "Выбирай 👇"
)

CHECKLIST_TEXT = (
    "🎁 <b>Топ-5 вопросов о наращивании волос</b>\n\n"
    "Отвечаю на самые частые вопросы клиенток:\n\n"
    "❓ <b>1. Больно ли наращивание?</b>\n"
    "Нет. Капсулы крепятся к своему волосу — никаких ощущений.\n\n"
    "❓ <b>2. Можно ли красить нарощенные волосы?</b>\n"
    "Можно, но только корни. Красить длину не рекомендую — "
    "это сокращает срок носки.\n\n"
    "❓ <b>3. Как долго держится наращивание?</b>\n"
    "Капсульное — 3–4 месяца до коррекции.\n"
    "Ленточное и биопротеин — 2–3 месяца.\n\n"
    "❓ <b>4. Выпадут ли свои волосы?</b>\n"
    "Нет, при правильном уходе и своевременной коррекции "
    "свои волосы не страдают.\n\n"
    "❓ <b>5. Что нельзя делать с нарощенными?</b>\n"
    "Нельзя: спать с мокрыми волосами, использовать масла у корней, "
    "расчёсывать от корня без фиксации.\n\n"
    "💜 <b>Хочешь полный гайд по уходу?</b>\n"
    "PDF с подробными правилами — всего 9 BYN 👇"
)

SERVICES_TEXT = (
    "✨ <b>Услуги и цены</b>\n\n"
    "🔥 <b>Горячее капсульное</b>\n"
    "• Работа: <b>1.6 BYN/капсула</b>\n"
    "• 100 капсул = 160 BYN · 150 = 240 BYN\n"
    "• Волосы: от 729 BYN (45 см) до 1116 BYN (80 см)\n"
    "• Время: 3–5 ч · Носка: 3–4 мес\n\n"
    "💜 <b>Биопротеиновое</b>\n"
    "• Итого: <b>470 BYN</b> (работа 390 + волосы 80)\n"
    "• Любой объём и длина — цена фиксированная\n\n"
    "🎀 <b>Ленточное (биоленты невидимые)</b>\n"
    "• <b>от 200 BYN</b> · Время: 40–90 мин\n"
    "• Носка: 2–3 месяца\n\n"
    "✂️ <b>Снятие:</b>\n"
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

BOOKING_TEXT = (
    "📅 <b>Запись на процедуру</b>\n\n"
    "Напиши:\n"
    "• Имя\n"
    "• Телефон\n"
    "• Метод наращивания\n"
    "• Удобную дату и время\n\n"
    f"📱 Или напрямую: {PHONE}\n"
    "📸 Instagram: @capsula_volos"
)

GUIDE_TEXT = (
    "📚 <b>Гайд «Уход за нарощенными волосами»</b>\n\n"
    "PDF-гайд с полными правилами ухода:\n"
    "✅ Как правильно расчёсывать\n"
    "✅ Какие средства использовать\n"
    "✅ Как спать чтобы капсулы держались дольше\n"
    "✅ Что категорически нельзя\n"
    "✅ Как продлить срок носки до максимума\n\n"
    "💰 Стоимость: <b>9 BYN</b>\n\n"
    f"Переведи на карту: <code>{CARD}</code>\n"
    "В комментарии напиши: <b>гайд</b>\n\n"
    "После оплаты нажми кнопку ниже 👇"
)

CONSULT_TEXT = (
    "💬 <b>Персональная консультация по подбору метода</b>\n\n"
    "ИИ-ассистент Анны проведёт разбор:\n"
    "✅ Подберёт метод под твои волосы\n"
    "✅ Рассчитает точную стоимость\n"
    "✅ Ответит на все вопросы\n"
    "✅ Расскажет как подготовиться\n\n"
    "💰 Стоимость: <b>19 BYN</b>\n\n"
    f"Переведи на карту: <code>{CARD}</code>\n"
    "В комментарии: <b>консультация</b>\n\n"
    "После оплаты нажми кнопку ниже 👇"
)


async def ask_claude(question: str, history: list) -> str:
    if not ANTHROPIC_API_KEY:
        return "ИИ-ассистент временно недоступен. Напишите Анне напрямую! 💜"
    try:
        client = anthropic_sdk.AsyncAnthropic(
            api_key=ANTHROPIC_API_KEY,
            base_url=ANTHROPIC_BASE_URL,
        )
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
        return "Не смогла ответить прямо сейчас. Напишите Анне напрямую 💜"


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

    # ─── СТАРТ ───────────────────────────────────────────────────────────────

    @dp.message(CommandStart())
    async def start(message: Message, state: FSMContext):
        await state.clear()
        name = message.from_user.first_name or "красавица"
        await message.answer(WELCOME.format(name=name), reply_markup=main_menu())
        await notify_admin(bot,
            f"👤 Новый пользователь: {name} @{message.from_user.username or '—'} "
            f"(ID: {message.from_user.id})"
        )

    @dp.callback_query(F.data == "menu")
    async def cb_menu(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        name = cb.from_user.first_name or "красавица"
        await cb.message.edit_text(WELCOME.format(name=name), reply_markup=main_menu())
        await cb.answer()

    # ─── ЧЕКЛИСТ (лид-магнит) ────────────────────────────────────────────────

    @dp.callback_query(F.data == "checklist")
    async def cb_checklist(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="📚 Купить полный гайд — 9 BYN", callback_data="buy_guide"))
        b.row(InlineKeyboardButton(text="📅 Записаться на процедуру", callback_data="book"))
        b.row(InlineKeyboardButton(text="← Меню", callback_data="menu"))
        await cb.message.edit_text(CHECKLIST_TEXT, reply_markup=b.as_markup())
        await cb.answer()

    # ─── МАГАЗИН ─────────────────────────────────────────────────────────────

    @dp.callback_query(F.data == "shop")
    async def cb_shop(cb: CallbackQuery):
        await cb.message.edit_text(
            "🛍 <b>Магазин Анны</b>\n\n"
            "Полезные материалы по наращиванию волос:",
            reply_markup=shop_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "buy_guide")
    async def cb_buy_guide(cb: CallbackQuery):
        await cb.message.edit_text(GUIDE_TEXT, reply_markup=pay_kb("guide", "9 BYN"))
        await cb.answer()

    @dp.callback_query(F.data == "buy_consult")
    async def cb_buy_consult(cb: CallbackQuery):
        await cb.message.edit_text(CONSULT_TEXT, reply_markup=pay_kb("consult", "19 BYN"))
        await cb.answer()

    @dp.callback_query(F.data == "paid_guide")
    async def cb_paid_guide(cb: CallbackQuery):
        await cb.message.edit_text(
            "✅ <b>Спасибо!</b>\n\n"
            "Анна проверит оплату и пришлёт гайд в течение нескольких часов.\n\n"
            "Если не получила — напиши напрямую: @capsula_volos 💜",
            reply_markup=back_kb()
        )
        await notify_admin(bot,
            f"💰 ОПЛАТА ГАЙДА (9 BYN)\n"
            f"👤 {cb.from_user.first_name} @{cb.from_user.username or '—'}\n"
            f"🆔 {cb.from_user.id}\n\n"
            f"Отправь PDF-гайд клиенту!"
        )
        await cb.answer()

    @dp.callback_query(F.data == "paid_consult")
    async def cb_paid_consult(cb: CallbackQuery, state: FSMContext):
        await state.set_state(AIState.chatting)
        await state.update_data(history=[], paid=True)
        await cb.message.edit_text(
            "✅ <b>Отлично! Консультация активирована.</b>\n\n"
            "🤖 Я — персональный ИИ-ассистент Анны.\n"
            "Задавай любые вопросы о наращивании — отвечу развёрнуто!\n\n"
            "<i>Для выхода нажми «← Выйти»</i>",
            reply_markup=ai_kb()
        )
        await notify_admin(bot,
            f"💰 ОПЛАТА КОНСУЛЬТАЦИИ (19 BYN)\n"
            f"👤 {cb.from_user.first_name} @{cb.from_user.username or '—'}\n"
            f"🆔 {cb.from_user.id}"
        )
        await cb.answer()

    # ─── УСЛУГИ ──────────────────────────────────────────────────────────────

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
        await notify_admin(bot,
            f"📅 Хочет записаться!\n"
            f"👤 {cb.from_user.first_name} @{cb.from_user.username or '—'}\n"
            f"🆔 {cb.from_user.id}"
        )

    # ─── ИИ-ЧАТ ──────────────────────────────────────────────────────────────

    @dp.callback_query(F.data == "ai")
    async def cb_ai(cb: CallbackQuery, state: FSMContext):
        await state.set_state(AIState.chatting)
        await state.update_data(history=[])
        await cb.message.edit_text(
            "🤖 <b>ИИ-консультант Анны</b>\n\n"
            "Задай любой вопрос о наращивании!\n"
            "Знаю всё о методах, ценах, уходе.\n\n"
            "<i>Нажми «← Выйти» чтобы вернуться в меню</i>",
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

    # ─── КАЛЬКУЛЯТОР ─────────────────────────────────────────────────────────

    @dp.callback_query(F.data == "calc")
    async def cb_calc(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🔥 Капсульное (1.6 BYN/кап)", callback_data="calc_cap"))
        b.row(InlineKeyboardButton(text="💜 Биопротеиновое (470 BYN)", callback_data="calc_bio"))
        b.row(InlineKeyboardButton(text="🎀 Ленточное (от 200 BYN)", callback_data="calc_tape"))
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
            "🎀 <b>Ленточное наращивание (биоленты)</b>\n\n"
            "💰 <b>от 200 BYN</b>\n\n"
            "<i>Точная стоимость зависит от объёма</i>",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_rem")
    async def cb_calc_rem(cb: CallbackQuery):
        await cb.message.edit_text(
            "✂️ <b>Снятие наращивания</b>\n\n"
            "• Капсулы: <b>0.4 BYN/прядь</b>\n"
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
            b.button(text=f"{n} капсул — {total} BYN", callback_data=f"cap_{n}")
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
            f"• {l} см — итого <b>{work + p:.0f} BYN</b>"
            for l, p in HAIR_PRICES.items()
        )
        await cb.message.edit_text(
            f"🔥 <b>Горячее капсульное — {n} капсул</b>\n\n"
            f"Работа: <b>{work} BYN</b>\n\n"
            f"<b>С волосами (итого):</b>\n{hair_lines}\n\n"
            f"<i>Свои волосы: только работа {work} BYN</i>",
            reply_markup=book_kb()
        )
        await cb.answer()

    # ─── КВИЗ ────────────────────────────────────────────────────────────────

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
            method, icon, price = "Ленточное (биоленты)", "🎀", "от 200 BYN"
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
            f"Записаться или узнать точную стоимость? 👇",
            reply_markup=book_kb()
        )
        await cb.answer()

    # ─── СВОБОДНЫЙ ТЕКСТ ─────────────────────────────────────────────────────

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
        elif any(w in t for w in ["гайд", "уход", "купить"]):
            await message.answer(GUIDE_TEXT, reply_markup=pay_kb("guide", "9 BYN"))
        elif any(w in t for w in ["привет", "здравств", "добрый", "hello", "hi"]):
            name = message.from_user.first_name or "красавица"
            await message.answer(WELCOME.format(name=name), reply_markup=main_menu())
        else:
            await message.answer("💜 Выбирай что интересует 👇", reply_markup=main_menu())

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Bot started with AI + Shop")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
