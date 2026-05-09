import asyncio
import logging
import os
from datetime import datetime, timedelta, date
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
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "")
INSTAGRAM = "https://instagram.com/volos_capsula/"
PHONE = os.environ.get("MASTER_PHONE", "+375291234567")
CARD = os.environ.get("CARD_NUMBER", "0000 0000 0000 0000")

HAIR_PRICES = {45:729,50:760,55:790,60:853,65:915,70:961,75:1054,80:1116}

# Расписание: будни 18:00-23:00, выходные 11:00-23:00
WEEKDAY_SLOTS = ["18:00","18:30","19:00","19:30","20:00","20:30","21:00","21:30","22:00","22:30"]
WEEKEND_SLOTS = ["11:00","11:30","12:00","12:30","13:00","13:30","14:00","14:30","15:00","15:30",
                 "16:00","16:30","17:00","17:30","18:00","18:30","19:00","19:30","20:00","20:30",
                 "21:00","21:30","22:00","22:30"]

# Хранилище в памяти
bookings: dict = {}      # {f"{date}_{time}": {"user_id":..,"name":..,"phone":..,"method":..,"status":..}}
blocked_dates: set = {}  # {"2025-05-10", ...}
warmup_queue: list = []  # [{"user_id":..,"stage":..,"send_at":..,"method":..}]

AI_SYSTEM = f"""Ты — умный ассистент мастера по наращиванию волос Анны (@volos_capsula, Брест).
Отвечаешь тепло, профессионально, по-русски. 2-4 предложения максимум.
УСЛУГИ И ЦЕНЫ:
- Горячее капсульное: 1.6 BYN/капсула + волосы (45см=729р, 50=760, 55=790, 60=853, 65=915, 70=961, 75=1054, 80=1116)
- Биопротеиновое: 390 работа + 80 волосы = 470 BYN
- Ленточное (биоленты): от 200 BYN
- Коррекция: от 80 BYN
- Снятие капсул: 0.4/прядь, биопротеин: 50/100г
Запись — через кнопку «Записаться» в боте. Не придумывай цены."""

class AIState(StatesGroup):
    chatting = State()

class BookState(StatesGroup):
    choose_date = State()
    choose_time = State()
    enter_name = State()
    enter_phone = State()
    confirm = State()

class AdminState(StatesGroup):
    blocking_date = State()

def get_available_dates(days_ahead=14):
    dates = []
    today = date.today()
    for i in range(1, days_ahead+1):
        d = today + timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        if ds not in blocked_dates:
            dates.append(d)
    return dates

def get_slots_for_date(d: date):
    slots = WEEKEND_SLOTS if d.weekday() >= 5 else WEEKDAY_SLOTS
    ds = d.strftime("%Y-%m-%d")
    free = [t for t in slots if f"{ds}_{t}" not in bookings or bookings[f"{ds}_{t}"]["status"] == "cancelled"]
    return free

def main_menu():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🎁 Бесплатный гайд", callback_data="free_guide"))
    b.row(InlineKeyboardButton(text="✨ Подобрать метод — квиз", callback_data="quiz"))
    b.row(
        InlineKeyboardButton(text="💰 Стоимость", callback_data="calc"),
        InlineKeyboardButton(text="📅 Записаться", callback_data="book"),
    )
    b.row(
        InlineKeyboardButton(text="🛍 Магазин", callback_data="shop"),
        InlineKeyboardButton(text="🤖 Спросить ИИ", callback_data="ai"),
    )
    b.row(
        InlineKeyboardButton(text="📋 Услуги", callback_data="services"),
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

def dates_kb():
    b = InlineKeyboardBuilder()
    dates = get_available_dates()
    days_ru = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
    months_ru = ["","янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"]
    for d in dates:
        slots = get_slots_for_date(d)
        if slots:
            label = f"{d.day} {months_ru[d.month]} ({days_ru[d.weekday()]}) — {len(slots)} окон"
            b.row(InlineKeyboardButton(text=label, callback_data=f"date_{d.strftime('%Y-%m-%d')}"))
    b.row(InlineKeyboardButton(text="← Назад", callback_data="menu"))
    return b.as_markup()

def times_kb(ds: str):
    d = date.fromisoformat(ds)
    slots = get_slots_for_date(d)
    b = InlineKeyboardBuilder()
    for t in slots:
        b.button(text=t, callback_data=f"time_{ds}_{t}")
    b.adjust(4)
    b.row(InlineKeyboardButton(text="← Другой день", callback_data="book"))
    return b.as_markup()

def methods_kb():
    b = InlineKeyboardBuilder()
    for m in ["Горячее капсульное","Биопротеиновое","Ленточное (биоленты)","Коррекция","Снятие"]:
        b.row(InlineKeyboardButton(text=m, callback_data=f"bm_{m}"))
    return b.as_markup()

def confirm_kb(ds, t):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Отправить заявку", callback_data=f"confirm_{ds}_{t}"))
    b.row(InlineKeyboardButton(text="✏️ Изменить", callback_data="book"))
    return b.as_markup()

def shop_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🎁 Гайд «Топ-5 вопросов» — БЕСПЛАТНО", callback_data="free_guide"))
    b.row(InlineKeyboardButton(text="💎 Гайд «Уход за волосами» — 9 BYN", callback_data="buy_guide"))
    b.row(InlineKeyboardButton(text="🤖 ИИ-консультация — 19 BYN", callback_data="buy_consult"))
    b.row(InlineKeyboardButton(text="← Назад", callback_data="menu"))
    return b.as_markup()

def pay_kb(product: str, price: str):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"✅ Я оплатил(а) {price}", callback_data=f"paid_{product}"))
    b.row(InlineKeyboardButton(text="← Назад", callback_data="shop"))
    return b.as_markup()

def ai_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📅 Записаться", callback_data="book"))
    b.row(InlineKeyboardButton(text="← Выйти", callback_data="menu"))
    return b.as_markup()

def admin_booking_kb(key: str):
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_ok_{key}"),
        InlineKeyboardButton(text="❌ Отменить", callback_data=f"adm_no_{key}"),
    )
    return b.as_markup()

async def notify_admin(bot: Bot, text: str, kb=None):
    if ADMIN_ID:
        try:
            await bot.send_message(ADMIN_ID, text, reply_markup=kb)
        except Exception as e:
            logger.error(f"Admin notify error: {e}")

async def ask_claude(question: str, history: list) -> str:
    if not ANTHROPIC_API_KEY:
        return f"ИИ-ассистент пока недоступен. Напишите Анне напрямую: {PHONE} 💜"
    try:
        import anthropic as sdk
        kwargs = {"api_key": ANTHROPIC_API_KEY}
        if ANTHROPIC_BASE_URL:
            kwargs["base_url"] = ANTHROPIC_BASE_URL
        client = sdk.AsyncAnthropic(**kwargs)
        messages = (history or [])[-6:] + [{"role": "user", "content": question}]
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=AI_SYSTEM,
            messages=messages,
        )
        return resp.content[0].text
    except Exception as e:
        logger.error(f"Claude error: {e}")
        return f"Не смогла ответить. Напишите Анне: {PHONE} 💜"

async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан!")
        return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    scheduler = AsyncIOScheduler(timezone="Europe/Minsk")

    # ─── НАПОМИНАНИЯ ────────────────────────────────────────────────────────
    async def send_reminders():
        now = datetime.now()
        tomorrow = (now + timedelta(hours=24)).strftime("%Y-%m-%d")
        for key, bk in list(bookings.items()):
            ds, t = key.split("_", 1)
            if ds == tomorrow and bk["status"] == "confirmed" and not bk.get("reminded"):
                try:
                    await bot.send_message(
                        bk["user_id"],
                        f"💜 Напоминаем о записи!\n\n"
                        f"📅 Завтра в {t}\n"
                        f"✨ {bk['method']}\n\n"
                        f"Ждём тебя! Если что-то изменилось — напиши заранее.",
                        reply_markup=main_menu()
                    )
                    bookings[key]["reminded"] = True
                except Exception as e:
                    logger.error(f"Reminder error: {e}")

    # ─── ПРОГРЕВ ────────────────────────────────────────────────────────────
    async def send_warmup():
        now = datetime.now()
        msgs = {
            1: ("💜 Ты смотрела какой метод тебе подходит?\n\nЕсть свободные окна на этой неделе — запишись прямо сейчас! 👇", book_kb()),
            2: ("✨ Есть несколько свободных окон!\n\nЗапишись сейчас — капсульное от 160 BYN, результат на 3-4 месяца 💜", book_kb()),
            3: ("🎁 Специально для тебя — при записи в этом месяце бесплатная консультация по уходу!\n\nНажми «Записаться» 👇", book_kb()),
        }
        for item in list(warmup_queue):
            if datetime.fromisoformat(item["send_at"]) <= now and not item.get("sent"):
                stage = item["stage"]
                if stage in msgs:
                    text, kb = msgs[stage]
                    try:
                        await bot.send_message(item["user_id"], text, reply_markup=kb)
                        item["sent"] = True
                    except Exception:
                        pass

    scheduler.add_job(send_reminders, "interval", hours=1)
    scheduler.add_job(send_warmup, "interval", minutes=30)
    scheduler.start()

    # ─── ХЭНДЛЕРЫ ───────────────────────────────────────────────────────────

    @dp.message(CommandStart())
    async def start(message: Message, state: FSMContext):
        await state.clear()
        name = message.from_user.first_name or "красавица"
        # Добавляем в прогрев через 24ч если не запишется
        warmup_queue.append({
            "user_id": message.from_user.id,
            "stage": 1,
            "send_at": (datetime.now() + timedelta(hours=24)).isoformat(),
        })
        await message.answer(
            f"💜 Привет, <b>{name}</b>!\n\n"
            "Я — помощник мастера наращивания волос <b>Анны</b>\n"
            "📍 Брест · @volos_capsula\n\n"
            "✨ Подберу метод · 💰 Рассчитаю стоимость\n"
            "📅 Запишу · 🎁 Бесплатный гайд\n\n"
            "Выбирай 👇",
            reply_markup=main_menu()
        )

    @dp.callback_query(F.data == "menu")
    async def cb_menu(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        await cb.message.edit_text(
            f"💜 Главное меню\n\nЧем могу помочь, <b>{cb.from_user.first_name or 'красавица'}</b>?",
            reply_markup=main_menu()
        )
        await cb.answer()

    @dp.callback_query(F.data == "services")
    async def cb_services(cb: CallbackQuery):
        await cb.message.edit_text(
            "✨ <b>Услуги и цены</b>\n\n"
            "🔥 <b>Горячее капсульное</b>\n"
            "• 1.6 BYN/капсула + волосы (45-80см)\n"
            "• Время: 3–5 ч · Носка: 3–4 мес\n\n"
            "💜 <b>Биопротеиновое</b>\n"
            "• Итого: <b>470 BYN</b> (390+80)\n\n"
            "🎀 <b>Ленточное (биоленты)</b>\n"
            "• от <b>200 BYN</b> · 40–90 мин\n\n"
            "✂️ Снятие капсул: 0.4/прядь\n"
            "✂️ Снятие биопротеина: 50/100г\n"
            "🔄 Коррекция: от 80 BYN",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "contacts")
    async def cb_contacts(cb: CallbackQuery):
        await cb.message.edit_text(
            f"📞 <b>Контакты</b>\n\n👩 Мастер: <b>Анна</b>\n📍 Брест\n"
            f"📱 {PHONE}\n📸 @volos_capsula",
            reply_markup=back_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "shop")
    async def cb_shop(cb: CallbackQuery):
        await cb.message.edit_text("🛍 <b>Магазин Анны</b>\n\nВыбери что тебя интересует:", reply_markup=shop_kb())
        await cb.answer()

    @dp.callback_query(F.data == "free_guide")
    async def cb_free_guide(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="💎 Полный гайд по уходу — 9 BYN", callback_data="buy_guide"))
        b.row(InlineKeyboardButton(text="📅 Записаться", callback_data="book"))
        b.row(InlineKeyboardButton(text="← Меню", callback_data="menu"))
        await cb.message.edit_text(
            "🎁 <b>Топ-5 вопросов о наращивании</b>\n\n"
            "<b>1. Больно ли?</b>\nАбсолютно нет — капсулы крепятся к волосу без боли.\n\n"
            "<b>2. Можно ли красить?</b>\nТолько корни. Нарощенные не красить — сократит срок.\n\n"
            "<b>3. Как долго держатся?</b>\nКапсульное 3-4 мес, ленточное 2-3 мес.\n\n"
            "<b>4. Бассейн и сауна?</b>\nБассейн — в шапочке. Сауна — ограниченно.\n\n"
            "<b>5. Что если пропустить коррекцию?</b>\nКапсулы сместятся, волосы начнут путаться.\n\n"
            "💜 Хочешь полный гайд по уходу — всего 9 BYN 👇",
            reply_markup=b.as_markup()
        )
        await cb.answer()

    @dp.callback_query(F.data == "buy_guide")
    async def cb_buy_guide(cb: CallbackQuery):
        await cb.message.edit_text(
            "💎 <b>Гайд «Уход за нарощенными волосами»</b>\n\n"
            "Что внутри:\n"
            "✨ Как правильно расчёсывать\n"
            "✨ Какие средства использовать\n"
            "✨ Как мыть голову\n"
            "✨ Что делать перед сном\n"
            "✨ Как продлить срок носки до максимума\n"
            "✨ Стоп-лист продуктов\n\n"
            f"💰 <b>9 BYN</b>\n\n"
            f"Перевод на карту: <code>{CARD}</code>\n"
            "После оплаты нажми кнопку ниже 👇",
            reply_markup=pay_kb("guide", "9 BYN")
        )
        await cb.answer()

    @dp.callback_query(F.data == "buy_consult")
    async def cb_buy_consult(cb: CallbackQuery):
        await cb.message.edit_text(
            "🤖 <b>ИИ-консультация по подбору метода</b>\n\n"
            "Персональный разбор для твоих волос:\n"
            "✨ Какой метод подходит именно тебе\n"
            "✨ Сколько капсул/прядей нужно\n"
            "✨ Точная стоимость под твои параметры\n"
            "✨ Ответы на все вопросы\n\n"
            f"💰 <b>19 BYN</b>\n\n"
            f"Перевод на карту: <code>{CARD}</code>\n"
            "После оплаты нажми кнопку ниже 👇",
            reply_markup=pay_kb("consult", "19 BYN")
        )
        await cb.answer()

    @dp.callback_query(F.data.startswith("paid_"))
    async def cb_paid(cb: CallbackQuery):
        product = cb.data.replace("paid_", "")
        names = {"guide": "Гайд по уходу (9 BYN)", "consult": "ИИ-консультация (19 BYN)"}
        await notify_admin(bot,
            f"💰 <b>Оплата!</b>\n\n"
            f"Продукт: {names.get(product, product)}\n"
            f"👤 {cb.from_user.first_name} @{cb.from_user.username or '—'}\n"
            f"🆔 {cb.from_user.id}\n\n"
            f"Отправь клиенту материал!"
        )
        await cb.message.edit_text(
            "✅ <b>Оплата получена!</b>\n\n"
            "Анна проверит платёж и пришлёт материал в течение нескольких минут 💜\n\n"
            "Если возникнут вопросы — напишите напрямую в Instagram @volos_capsula",
            reply_markup=back_kb()
        )
        await cb.answer()

    # ─── ЗАПИСЬ СО СЛОТАМИ ──────────────────────────────────────────────────

    @dp.callback_query(F.data == "book")
    async def cb_book(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        await state.set_state(BookState.choose_date)
        kb = dates_kb()
        dates = get_available_dates()
        if not any(get_slots_for_date(d) for d in dates):
            await cb.message.edit_text(
                "😔 К сожалению, свободных окон на ближайшие 2 недели нет.\n\n"
                f"Напишите напрямую: {PHONE}\n📸 @volos_capsula",
                reply_markup=back_kb()
            )
            await cb.answer()
            return
        await cb.message.edit_text(
            "📅 <b>Выбери удобную дату</b>\n\n"
            "Доступные дни на ближайшие 2 недели 👇",
            reply_markup=kb
        )
        await cb.answer()

    @dp.callback_query(BookState.choose_date, F.data.startswith("date_"))
    async def cb_choose_date(cb: CallbackQuery, state: FSMContext):
        ds = cb.data.replace("date_", "")
        await state.update_data(date=ds)
        await state.set_state(BookState.choose_time)
        await cb.message.edit_text(
            f"📅 <b>{ds}</b>\n\nВыбери удобное время 👇",
            reply_markup=times_kb(ds)
        )
        await cb.answer()

    @dp.callback_query(BookState.choose_time, F.data.startswith("time_"))
    async def cb_choose_time(cb: CallbackQuery, state: FSMContext):
        parts = cb.data.split("_", 2)
        ds, t = parts[1], parts[2]
        # Проверяем что слот ещё свободен
        key = f"{ds}_{t}"
        if key in bookings and bookings[key]["status"] != "cancelled":
            await cb.answer("⚠️ Это время только что заняли! Выбери другое.", show_alert=True)
            await cb.message.edit_text(
                f"📅 <b>{ds}</b>\n\nВыбери другое время 👇",
                reply_markup=times_kb(ds)
            )
            return
        await state.update_data(date=ds, time=t)
        await state.set_state(BookState.enter_name)
        await cb.message.edit_text(f"✅ Время: <b>{ds} в {t}</b>\n\nКак тебя зовут?")
        await cb.answer()

    @dp.message(BookState.enter_name, F.text)
    async def book_name(message: Message, state: FSMContext):
        if len(message.text.strip()) < 2:
            await message.answer("Введи имя (минимум 2 символа):")
            return
        await state.update_data(name=message.text.strip())
        await state.set_state(BookState.enter_phone)
        await message.answer("📱 Твой номер телефона:")

    @dp.message(BookState.enter_phone, F.text)
    async def book_phone(message: Message, state: FSMContext):
        phone = message.text.strip()
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) < 9:
            await message.answer("Введи корректный номер телефона:")
            return
        await state.update_data(phone=phone)
        await state.set_state(BookState.confirm)
        data = await state.get_data()
        await message.answer(
            f"📋 <b>Проверь данные:</b>\n\n"
            f"📅 {data['date']} в {data['time']}\n"
            f"👤 {data['name']}\n"
            f"📱 {data['phone']}\n\n"
            f"Выбери метод наращивания:",
            reply_markup=methods_kb()
        )

    @dp.callback_query(BookState.confirm, F.data.startswith("bm_"))
    async def book_method(cb: CallbackQuery, state: FSMContext):
        method = cb.data.replace("bm_", "")
        await state.update_data(method=method)
        data = await state.get_data()
        await cb.message.edit_text(
            f"✅ <b>Заявка готова:</b>\n\n"
            f"📅 {data['date']} в {data['time']}\n"
            f"✨ {method}\n"
            f"👤 {data['name']}\n"
            f"📱 {data['phone']}\n\n"
            f"Отправить заявку Анне?",
            reply_markup=confirm_kb(data['date'], data['time'])
        )
        await cb.answer()

    @dp.callback_query(BookState.confirm, F.data.startswith("confirm_"))
    async def book_confirm(cb: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        await state.clear()
        ds, t = data['date'], data['time']
        key = f"{ds}_{t}"

        # Предварительно бронируем
        bookings[key] = {
            "user_id": cb.from_user.id,
            "name": data['name'],
            "phone": data['phone'],
            "method": data['method'],
            "status": "pending",
            "reminded": False,
        }

        # Уведомляем Анну
        await notify_admin(bot,
            f"🆕 <b>Новая заявка!</b>\n\n"
            f"📅 {ds} в {t}\n"
            f"✨ {data['method']}\n"
            f"👤 {data['name']}\n"
            f"📱 {data['phone']}\n"
            f"🆔 @{cb.from_user.username or '—'} ({cb.from_user.id})",
            kb=admin_booking_kb(key)
        )

        # Убираем из прогрева
        for item in warmup_queue:
            if item.get("user_id") == cb.from_user.id:
                item["sent"] = True

        await cb.message.edit_text(
            "🎉 <b>Заявка отправлена!</b>\n\n"
            f"📅 {ds} в {t}\n"
            f"✨ {data['method']}\n\n"
            "Анна свяжется с тобой для подтверждения 💜\n\n"
            "📸 Пока загляни в Instagram @volos_capsula",
            reply_markup=main_menu()
        )
        await cb.answer()

    # ─── АДМИН: подтверждение/отмена ────────────────────────────────────────

    @dp.callback_query(F.data.startswith("adm_ok_"))
    async def adm_confirm(cb: CallbackQuery):
        if cb.from_user.id != ADMIN_ID:
            await cb.answer("Нет доступа")
            return
        key = cb.data.replace("adm_ok_", "")
        if key in bookings:
            bookings[key]["status"] = "confirmed"
            uid = bookings[key]["user_id"]
            ds, t = key.split("_", 1)
            try:
                await bot.send_message(uid,
                    f"✅ <b>Запись подтверждена!</b>\n\n"
                    f"📅 {ds} в {t}\n"
                    f"✨ {bookings[key]['method']}\n\n"
                    f"Ждём тебя! Адрес уточним за день до процедуры 💜",
                    reply_markup=main_menu()
                )
            except Exception:
                pass
        await cb.message.edit_text(cb.message.text + "\n\n✅ <b>Подтверждено</b>")
        await cb.answer("Клиент уведомлён ✅")

    @dp.callback_query(F.data.startswith("adm_no_"))
    async def adm_cancel(cb: CallbackQuery):
        if cb.from_user.id != ADMIN_ID:
            await cb.answer("Нет доступа")
            return
        key = cb.data.replace("adm_no_", "")
        if key in bookings:
            uid = bookings[key]["user_id"]
            ds, t = key.split("_", 1)
            bookings[key]["status"] = "cancelled"
            try:
                await bot.send_message(uid,
                    f"😔 К сожалению, время <b>{ds} в {t}</b> недоступно.\n\n"
                    "Выбери другое время 👇",
                    reply_markup=book_kb()
                )
            except Exception:
                pass
        await cb.message.edit_text(cb.message.text + "\n\n❌ <b>Отменено</b>")
        await cb.answer("Клиент уведомлён ❌")

    # ─── АДМИН: блокировка дат ───────────────────────────────────────────────

    @dp.message(Command("admin"))
    async def cmd_admin(message: Message):
        if message.from_user.id != ADMIN_ID:
            return
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🚫 Закрыть день", callback_data="adm_block"))
        b.row(InlineKeyboardButton(text="✅ Открыть день", callback_data="adm_unblock"))
        b.row(InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats"))
        b.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast"))
        await message.answer(
            f"👑 <b>Админ-панель</b>\n\n"
            f"📅 Заявок: {len([b for b in bookings.values() if b['status']=='pending'])}\n"
            f"✅ Подтверждено: {len([b for b in bookings.values() if b['status']=='confirmed'])}\n"
            f"🚫 Закрытых дней: {len(blocked_dates)}",
            reply_markup=b.as_markup()
        )

    @dp.callback_query(F.data == "adm_block")
    async def adm_block(cb: CallbackQuery, state: FSMContext):
        if cb.from_user.id != ADMIN_ID:
            return
        await state.set_state(AdminState.blocking_date)
        await state.update_data(action="block")
        await cb.message.edit_text(
            "🚫 Введи дату для закрытия в формате <b>ГГГГ-ММ-ДД</b>\n"
            "Например: <code>2025-05-15</code>"
        )
        await cb.answer()

    @dp.callback_query(F.data == "adm_unblock")
    async def adm_unblock(cb: CallbackQuery, state: FSMContext):
        if cb.from_user.id != ADMIN_ID:
            return
        await state.set_state(AdminState.blocking_date)
        await state.update_data(action="unblock")
        await cb.message.edit_text(
            "✅ Введи дату для открытия в формате <b>ГГГГ-ММ-ДД</b>\n"
            f"Закрытые дни: {', '.join(sorted(blocked_dates)) or 'нет'}"
        )
        await cb.answer()

    @dp.message(AdminState.blocking_date, F.text)
    async def adm_date_input(message: Message, state: FSMContext):
        if message.from_user.id != ADMIN_ID:
            return
        try:
            date.fromisoformat(message.text.strip())
            ds = message.text.strip()
        except ValueError:
            await message.answer("Неверный формат. Введи дату как: <code>2025-05-15</code>")
            return
        data = await state.get_data()
        await state.clear()
        if data["action"] == "block":
            blocked_dates.add(ds)
            await message.answer(f"🚫 День <b>{ds}</b> закрыт для записи.")
        else:
            blocked_dates.discard(ds)
            await message.answer(f"✅ День <b>{ds}</b> открыт для записи.")

    @dp.callback_query(F.data == "adm_stats")
    async def adm_stats(cb: CallbackQuery):
        if cb.from_user.id != ADMIN_ID:
            return
        pending = [k for k,v in bookings.items() if v["status"]=="pending"]
        confirmed = [k for k,v in bookings.items() if v["status"]=="confirmed"]
        text = f"📊 <b>Статистика</b>\n\n⏳ Ожидают: {len(pending)}\n✅ Подтверждено: {len(confirmed)}\n🚫 Закрытых дней: {len(blocked_dates)}"
        if pending:
            text += "\n\n<b>Ожидают подтверждения:</b>\n"
            for k in pending[:5]:
                b = bookings[k]
                text += f"• {k.replace('_',' ')} — {b['name']} {b['phone']}\n"
        await cb.message.edit_text(text, reply_markup=back_kb())
        await cb.answer()

    # ─── КВИЗ ───────────────────────────────────────────────────────────────

    @dp.callback_query(F.data == "quiz")
    async def cb_quiz(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="До плеч (до 30 см)", callback_data="q1_short"))
        b.row(InlineKeyboardButton(text="До лопаток (30–45 см)", callback_data="q1_mid"))
        b.row(InlineKeyboardButton(text="Длиннее лопаток (45+ см)", callback_data="q1_long"))
        await cb.message.edit_text(
            "✨ <b>Квиз — подбор метода</b>\n\n<b>Вопрос 1:</b> Длина волос?",
            reply_markup=b.as_markup()
        )
        await cb.answer()

    @dp.callback_query(F.data.startswith("q1_"))
    async def q2(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="Тонкие / редкие", callback_data=f"q2_thin|{cb.data}"))
        b.row(InlineKeyboardButton(text="Средние", callback_data=f"q2_mid|{cb.data}"))
        b.row(InlineKeyboardButton(text="Густые", callback_data=f"q2_thick|{cb.data}"))
        await cb.message.edit_text("<b>Вопрос 2:</b> Плотность волос?", reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data.startswith("q2_"))
    async def q3(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="Хочу длину", callback_data=f"q3_len|{cb.data}"))
        b.row(InlineKeyboardButton(text="Хочу объём", callback_data=f"q3_vol|{cb.data}"))
        b.row(InlineKeyboardButton(text="Хочу быстро", callback_data=f"q3_fast|{cb.data}"))
        b.row(InlineKeyboardButton(text="Бережный метод", callback_data=f"q3_gentle|{cb.data}"))
        await cb.message.edit_text("<b>Вопрос 3:</b> Чего хочешь?", reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data.startswith("q3_"))
    async def q_result(cb: CallbackQuery):
        d = cb.data
        if "thin" in d or "fast" in d:
            m,i,p = "Ленточное (биоленты)","🎀","от 200 BYN"
            desc = "Биоленты — быстро, бережно, идеально для тонких волос."
        elif "gentle" in d:
            m,i,p = "Голливудское","👑","от 200 BYN"
            desc = "Трессы на косичках — без клея, волосы не пострадают."
        else:
            m,i,p = "Горячее капсульное","🔥","от 160 BYN"
            desc = "Универсальный метод. Держится 3–4 месяца."
        await cb.message.edit_text(
            f"{i} <b>Твой метод: {m}</b>\n\n💰 {p}\n\n{desc}",
            reply_markup=book_kb()
        )
        await cb.answer()

    # ─── КАЛЬКУЛЯТОР ────────────────────────────────────────────────────────

    @dp.callback_query(F.data == "calc")
    async def cb_calc(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🔥 Горячее капсульное", callback_data="calc_cap"))
        b.row(InlineKeyboardButton(text="💜 Биопротеиновое — 470 BYN", callback_data="calc_bio"))
        b.row(InlineKeyboardButton(text="🎀 Ленточное — от 200 BYN", callback_data="calc_tape"))
        b.row(InlineKeyboardButton(text="✂️ Снятие", callback_data="calc_rem"))
        b.row(InlineKeyboardButton(text="← Назад", callback_data="menu"))
        await cb.message.edit_text("💰 <b>Калькулятор</b>\n\nВыбери метод:", reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data == "calc_bio")
    async def calc_bio(cb: CallbackQuery):
        await cb.message.edit_text(
            "💜 <b>Биопротеиновое</b>\n\nРабота: 390 BYN\nВолосы: +80 BYN\n\n💰 <b>Итого: 470 BYN</b>",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_tape")
    async def calc_tape(cb: CallbackQuery):
        await cb.message.edit_text("🎀 <b>Ленточное</b>\n\n💰 <b>от 200 BYN</b>", reply_markup=book_kb())
        await cb.answer()

    @dp.callback_query(F.data == "calc_rem")
    async def calc_rem(cb: CallbackQuery):
        await cb.message.edit_text(
            "✂️ <b>Снятие</b>\n\n• Капсулы: 0.4 BYN/прядь\n  100 прядей = 40 BYN\n\n• Биопротеин: 50 BYN/100г\n  150г = 75 BYN",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_cap")
    async def calc_cap(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        for n in [80,100,120,150,200]:
            b.button(text=f"{n} кап = {round(n*1.6,1)} BYN", callback_data=f"cap_{n}")
        b.adjust(1)
        b.row(InlineKeyboardButton(text="← Назад", callback_data="calc"))
        await cb.message.edit_text("🔥 <b>Капсульное — 1.6 BYN/капсула</b>\n\nВыбери количество:", reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data.startswith("cap_"))
    async def cap_result(cb: CallbackQuery):
        n = int(cb.data.split("_")[1])
        work = round(n*1.6, 1)
        lines = "\n".join(f"• {l}см → итого {work+p:.0f} BYN" for l,p in HAIR_PRICES.items())
        await cb.message.edit_text(
            f"🔥 <b>{n} капсул</b>\nРабота: <b>{work} BYN</b>\n\n<b>С волосами:</b>\n{lines}",
            reply_markup=book_kb()
        )
        await cb.answer()

    # ─── ИИ ─────────────────────────────────────────────────────────────────

    @dp.callback_query(F.data == "ai")
    async def cb_ai(cb: CallbackQuery, state: FSMContext):
        await state.set_state(AIState.chatting)
        await state.update_data(history=[])
        await cb.message.edit_text(
            "🤖 <b>ИИ-консультант</b>\n\nЗадай любой вопрос о наращивании!\n\n<i>Для выхода нажми ← Выйти</i>",
            reply_markup=ai_kb()
        )
        await cb.answer()

    @dp.message(AIState.chatting, F.text)
    async def ai_msg(message: Message, state: FSMContext):
        data = await state.get_data()
        history = data.get("history", [])
        thinking = await message.answer("💭 Думаю...")
        answer = await ask_claude(message.text, history)
        history.append({"role":"user","content":message.text})
        history.append({"role":"assistant","content":answer})
        if len(history) > 6:
            history = history[-6:]
        await state.update_data(history=history)
        await thinking.delete()
        await message.answer(answer, reply_markup=ai_kb())

    # ─── СВОБОДНЫЙ ТЕКСТ ────────────────────────────────────────────────────

    @dp.message(F.text)
    async def any_text(message: Message, state: FSMContext):
        if await state.get_state() in [AIState.chatting, BookState.enter_name,
                                        BookState.enter_phone, AdminState.blocking_date]:
            return
        t = message.text.lower()
        if any(w in t for w in ["цен","сколько","стоит","прайс"]):
            await message.answer(
                "💰 Кратко о ценах:\n🔥 Капсульное: 1.6 BYN/капсула\n💜 Биопротеин: 470 BYN\n🎀 Ленточное: от 200 BYN",
                reply_markup=book_kb()
            )
        elif any(w in t for w in ["запис","прийти","приём","время"]):
            await message.answer("📅 Выбери удобное время 👇", reply_markup=book_kb())
        elif any(w in t for w in ["привет","здравств","добрый","hello"]):
            name = message.from_user.first_name or "красавица"
            await message.answer(
                f"💜 Привет, <b>{name}</b>! Выбирай что интересует 👇",
                reply_markup=main_menu()
            )
        else:
            await message.answer("💜 Выбирай что интересует 👇", reply_markup=main_menu())

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Bot started — full version with slots")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
