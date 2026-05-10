import asyncio, logging, os
from datetime import datetime, timedelta, date, time as dtime
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

BOT_TOKEN = os.environ.get("BOT_TOKEN","")
ADMIN_ID = int(os.environ.get("ADMIN_ID","0"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY","")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY","")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL","")
INSTAGRAM = "https://www.instagram.com/volos_capsula/"
PHONE = os.environ.get("MASTER_PHONE","+375291234567")
CARD = os.environ.get("CARD_NUMBER","0000 0000 0000 0000")

GUIDE_URL = "https://raw.githubusercontent.com/annashestakova/capsula-bot/main/guide_volos_capsula.pdf"

SERVICE_DURATION = {
    "Снятие капсул":       2,
    "Снятие биопротеина":  3,
    "Загущение":           5,
    "Наращивание":         9,
    "Биопротеиновое":      6,
    "Коррекция":           4,
}

SERVICE_PRICES = {
    "Снятие капсул":       "0.4 BYN/прядь",
    "Снятие биопротеина":  "50 BYN/100г",
    "Загущение":           "от 160 BYN",
    "Наращивание":         "1.6 BYN/капсула",
    "Биопротеиновое":      "350–400 BYN",
    "Коррекция":           "от 80 BYN",
}

SERVICE_HOURS = {
    "Снятие капсул":       "1–2 ч",
    "Снятие биопротеина":  "1–2 ч",
    "Загущение":           "2–3 ч",
    "Наращивание":         "4–6 ч",
    "Биопротеиновое":      "2–4 ч",
    "Коррекция":           "2–3 ч",
}

YANDEX_MAPS_URL = os.environ.get("YANDEX_MAPS_URL", "https://yandex.by/maps/org/u_anny/90436287873/reviews/?ll=23.678135%2C52.105687&z=15")
NEW_CLIENT_DISCOUNT = 20

HAIR_PRICES = {45:734,50:765,55:795,60:858,65:920,70:966,75:1059,80:1121}

bookings: dict = {}
blocked_dates: set = set()
clients: dict = {}

AI_SYSTEM = """Ты — помощник мастера по наращиванию волос Анны (@volos_capsula, Брест).
Отвечай тепло, по-русски, кратко (2-4 предложения). Никогда не добавляй услуги которые клиент не просил.

ПРАВИЛА РАСЧЁТА:

1. КАПСУЛЬНОЕ НАРАЩИВАНИЕ (славянский натуральный волос):
   - Работа: кол-во капсул × 1.6 BYN
   - Волосы (только натуральные славянские, цена с наценкой):
     45см = 734 BYN, 50см = 765, 55см = 795, 60см = 858,
     65см = 920, 70см = 966, 75см = 1059, 80см = 1121
   - ИТОГО = работа + волосы
   - Рекомендации по количеству капсул:
     Тонкие волосы: от 200 капсул
     Средние волосы: от 270 капсул
     Густые волосы: от 450 капсул
   - Если не спрашивают про волосы — называй только стоимость работы
   - Если спрашивают общую стоимость — уточни густоту волос и нужна ли длина

2. БИОПРОТЕИНОВОЕ: 350-400 BYN (волосы включены). Доплата за густоту +30-50 BYN.

3. ЛЕНТОЧНОЕ (биоленты): от 200 BYN. Время 40-90 мин.

4. СНЯТИЕ: капсулы 0.4 BYN/прядь, биопротеин 50 BYN/100г.

5. КОРРЕКЦИЯ: от 80 BYN.

ВАЖНО:
- Не добавляй снятие и коррекцию если не спросили
- При вопросе о стоимости капсульного — уточни: густота волос (тонкие/средние/густые) и нужна ли длина
- Запись только через кнопку в боте
- Волосы только натуральные славянские"""

DAY_RU = ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]
MONTH_RU = ["","янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"]

def get_work_slots(d: date) -> list[str]:
    if d.weekday() >= 5:
        start, end = 11*2, 23*2
    else:
        start, end = 18*2, 23*2
    slots = []
    for i in range(start, end):
        h, m = divmod(i * 30, 60)
        slots.append(f"{h:02d}:{m:02d}")
    return slots

def get_booked_slots(ds: str) -> set[str]:
    occupied = set()
    for key, bk in bookings.items():
        if key.startswith(ds) and bk["status"] != "cancelled":
            d_str, t = key.split("_", 1)
            dur = SERVICE_DURATION.get(bk.get("service",""), 2)
            h, m = map(int, t.split(":"))
            start_mins = h*60 + m
            for i in range(dur):
                total = start_mins + i*30
                th, tm = divmod(total, 60)
                occupied.add(f"{th:02d}:{tm:02d}")
    return occupied

def get_free_slots(d: date, service: str) -> list[str]:
    ds = d.strftime("%Y-%m-%d")
    if ds in blocked_dates:
        return []
    all_slots = get_work_slots(d)
    occupied = get_booked_slots(ds)
    dur = SERVICE_DURATION.get(service, 2)
    free = []
    for i, slot in enumerate(all_slots):
        need = all_slots[i:i+dur]
        if len(need) == dur and not any(s in occupied for s in need):
            free.append(slot)
    return free

def get_week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())

def week_kb(week_start: date, service: str):
    b = InlineKeyboardBuilder()
    ws = week_start
    we = ws + timedelta(days=6)
    b.row(InlineKeyboardButton(
        text=f"📅 {ws.day} {MONTH_RU[ws.month]} — {we.day} {MONTH_RU[we.month]}",
        callback_data="noop"
    ))
    btns = []
    today = date.today()
    for i in range(7):
        d = ws + timedelta(days=i)
        if d <= today or d.strftime("%Y-%m-%d") in blocked_dates:
            btns.append(InlineKeyboardButton(text="✗", callback_data="noop"))
            continue
        free = get_free_slots(d, service)
        if not free:
            btns.append(InlineKeyboardButton(text="✗", callback_data="noop"))
        else:
            btns.append(InlineKeyboardButton(
                text=f"{DAY_RU[i]} {d.day} ({len(free)})",
                callback_data=f"cal_{d.strftime('%Y-%m-%d')}"
            ))
    for i in range(0, len(btns), 4):
        b.row(*btns[i:i+4])
    prev = week_start - timedelta(days=7)
    next_ = week_start + timedelta(days=7)
    nav = []
    if prev >= date.today() - timedelta(days=7):
        nav.append(InlineKeyboardButton(text="← Пред. неделя", callback_data=f"week_{prev.strftime('%Y-%m-%d')}"))
    nav.append(InlineKeyboardButton(text="След. неделя →", callback_data=f"week_{next_.strftime('%Y-%m-%d')}"))
    b.row(*nav)
    b.row(InlineKeyboardButton(text="← Изменить услугу", callback_data="book"))
    return b.as_markup()

def times_kb(ds: str, service: str):
    d = date.fromisoformat(ds)
    free = get_free_slots(d, service)
    b = InlineKeyboardBuilder()
    dur = SERVICE_DURATION.get(service, 2)
    h_dur = dur * 0.5
    b.row(InlineKeyboardButton(
        text=f"📅 {d.day} {MONTH_RU[d.month]} · {service} (~{h_dur:.0f}–{h_dur+1:.0f}ч)",
        callback_data="noop"
    ))
    for t in free:
        h, m = map(int, t.split(":"))
        end_m = h*60 + m + dur*30
        eh, em = divmod(end_m, 60)
        b.button(text=f"{t}–{eh:02d}:{em:02d}", callback_data=f"time_{ds}_{t}")
    b.adjust(3)
    ws = get_week_start(d)
    b.row(InlineKeyboardButton(text="← Другой день", callback_data=f"week_{ws.strftime('%Y-%m-%d')}"))
    return b.as_markup()

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
    b.row(InlineKeyboardButton(text="📸 Instagram @volos_capsula", url=INSTAGRAM))
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

def services_book_kb():
    b = InlineKeyboardBuilder()
    for svc in SERVICE_DURATION:
        price = SERVICE_PRICES.get(svc,"")
        hours = SERVICE_HOURS.get(svc,"")
        b.row(InlineKeyboardButton(
            text=f"{svc} · {hours} · {price}",
            callback_data=f"svc_{svc}"
        ))
    b.row(InlineKeyboardButton(text="← Назад", callback_data="menu"))
    return b.as_markup()

def confirm_kb(ds, t, service):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Отправить заявку", callback_data=f"confirm_{ds}_{t}"))
    b.row(InlineKeyboardButton(text="✏️ Изменить", callback_data="book"))
    return b.as_markup()

def shop_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🎁 Топ-5 вопросов — БЕСПЛАТНО", callback_data="free_guide"))
    b.row(InlineKeyboardButton(text="💎 Гайд «Уход за волосами» — 9 BYN", callback_data="buy_guide"))
    b.row(InlineKeyboardButton(text="🤖 ИИ-консультация — 19 BYN", callback_data="buy_consult"))
    b.row(InlineKeyboardButton(text="← Назад", callback_data="menu"))
    return b.as_markup()

def pay_kb(product):
    b = InlineKeyboardBuilder()
    prices = {"guide":"9 BYN","consult":"19 BYN"}
    b.row(InlineKeyboardButton(text=f"✅ Оплатил(а) {prices.get(product,'')}", callback_data=f"paid_{product}"))
    b.row(InlineKeyboardButton(text="← Назад", callback_data="shop"))
    return b.as_markup()

def ai_kb():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📅 Записаться", callback_data="book"))
    b.row(InlineKeyboardButton(text="← Выйти", callback_data="menu"))
    return b.as_markup()

def admin_booking_kb(key):
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"adm_ok_{key}"),
        InlineKeyboardButton(text="❌ Отменить", callback_data=f"adm_no_{key}"),
    )
    return b.as_markup()

class BookState(StatesGroup):
    choose_service = State()
    choose_date = State()
    choose_time = State()
    enter_name = State()
    enter_phone = State()
    confirm = State()

class AIState(StatesGroup):
    chatting = State()

class AdminState(StatesGroup):
    blocking = State()
    unblocking = State()

async def notify_admin(bot, text, kb=None):
    if ADMIN_ID:
        try: await bot.send_message(ADMIN_ID, text, reply_markup=kb)
        except Exception as e: logger.error(f"Admin: {e}")

async def ask_claude(q, history):
    groq_key = GROQ_API_KEY
    if groq_key:
        try:
            import httpx
            msgs = [{"role":"system","content":AI_SYSTEM}]
            for h in (history or [])[-6:]:
                msgs.append(h)
            msgs.append({"role":"user","content":q})
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                    json={"model": "llama-3.1-8b-instant", "messages": msgs, "max_tokens": 300},
                    timeout=15
                )
                data = r.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"Groq: {e}")

    if not ANTHROPIC_API_KEY:
        return f"ИИ недоступен. Напишите напрямую: {PHONE} 💜"
    try:
        import anthropic as sdk
        kw = {"api_key": ANTHROPIC_API_KEY}
        if ANTHROPIC_BASE_URL: kw["base_url"] = ANTHROPIC_BASE_URL
        client = sdk.AsyncAnthropic(**kw)
        msgs = (history or [])[-6:] + [{"role":"user","content":q}]
        r = await client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=300, system=AI_SYSTEM, messages=msgs)
        return r.content[0].text
    except Exception as e:
        logger.error(f"Claude: {e}")
        return f"Не смогла ответить. Напишите: {PHONE} 💜"

async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задан!")
        return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    scheduler = AsyncIOScheduler(timezone="Europe/Minsk")

    async def send_reminders():
        now = datetime.now()
        yesterday_ds = (now - timedelta(hours=24)).strftime("%Y-%m-%d")
        for key, bk in list(bookings.items()):
            ds = key.split("_")[0]
            if ds == yesterday_ds and bk["status"] == "confirmed" and not bk.get("review_reminder_sent"):
                bookings[key]["review_reminder_sent"] = True
                b = InlineKeyboardBuilder()
                b.row(InlineKeyboardButton(text="💌 Отправить запрос на отзыв", callback_data=f"send_review_{key}"))
                await notify_admin(bot,
                    f"⭐ <b>Напоминание об отзыве!</b>\n\n"
                    f"Вчера была процедура:\n"
                    f"👤 {bk['name']} · {bk['phone']}\n"
                    f"✨ {bk.get('service','')}\n\n"
                    f"Нажми кнопку чтобы отправить клиентке запрос на отзыв 👇",
                    kb=b.as_markup()
                )
        remind_ds = (now + timedelta(hours=24)).strftime("%Y-%m-%d")
        for key, bk in list(bookings.items()):
            ds = key.split("_")[0]
            if ds == remind_ds and bk["status"] == "confirmed" and not bk.get("reminded"):
                t = key.split("_", 1)[1]
                try:
                    await bot.send_message(bk["user_id"],
                        f"💜 Напоминание!\n\nЗавтра в <b>{t}</b>\n✨ {bk.get('service','')}\n\nЖдём тебя! 🌸",
                        reply_markup=main_menu())
                    bookings[key]["reminded"] = True
                except: pass

    scheduler.add_job(send_reminders, "interval", hours=1)
    scheduler.start()

    @dp.message(CommandStart())
    async def start(message: Message, state: FSMContext):
        await state.clear()
        name = message.from_user.first_name or "красавица"
        clients[message.from_user.id] = {
            "name": message.from_user.first_name,
            "username": message.from_user.username,
        }
        await message.answer(
            f"💜 Привет, <b>{name}</b>!\n\n"
            "Я — помощник мастера наращивания волос <b>Анны</b>\n"
            "📍 Брест · @volos_capsula\n\n"
            "✨ Подберу метод · 💰 Рассчитаю · 📅 Запишу\n"
            "🎁 Новым клиентам скидка 20% на первое наращивание!\n\n"
            "Выбирай 👇",
            reply_markup=main_menu()
        )

    @dp.callback_query(F.data == "menu")
    async def cb_menu(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        await cb.message.edit_text(
            f"💜 Главное меню\n\n<b>{cb.from_user.first_name or 'Красавица'}</b>, чем могу помочь?",
            reply_markup=main_menu()
        )
        await cb.answer()

    @dp.callback_query(F.data == "noop")
    async def cb_noop(cb: CallbackQuery):
        await cb.answer()

    # ── ЗАПИСЬ ────────────────────────────────────────────────────────────
    @dp.callback_query(F.data == "book")
    async def cb_book(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        await state.set_state(BookState.choose_service)
        await cb.message.edit_text("📅 <b>Запись на процедуру</b>\n\nВыбери услугу:", reply_markup=services_book_kb())
        await cb.answer()

    @dp.callback_query(BookState.choose_service, F.data.startswith("svc_"))
    async def cb_svc(cb: CallbackQuery, state: FSMContext):
        service = cb.data.replace("svc_", "")
        await state.update_data(service=service)
        await state.set_state(BookState.choose_date)
        ws = get_week_start(date.today() + timedelta(days=1))
        await cb.message.edit_text(f"📅 <b>{service}</b>\n\nВыбери удобный день:", reply_markup=week_kb(ws, service))
        await cb.answer()

    @dp.callback_query(F.data.startswith("week_"))
    async def cb_week(cb: CallbackQuery, state: FSMContext):
        ds = cb.data.replace("week_", "")
        ws = date.fromisoformat(ds)
        data = await state.get_data()
        service = data.get("service", "Наращивание")
        await cb.message.edit_text(f"📅 <b>{service}</b>\n\nВыбери удобный день:", reply_markup=week_kb(ws, service))
        await cb.answer()

    @dp.callback_query(F.data.startswith("cal_"))
    async def cb_cal(cb: CallbackQuery, state: FSMContext):
        ds = cb.data.replace("cal_", "")
        data = await state.get_data()
        service = data.get("service", "Наращивание")
        await state.update_data(date=ds)
        await state.set_state(BookState.choose_time)
        d = date.fromisoformat(ds)
        await cb.message.edit_text(
            f"📅 <b>{d.day} {MONTH_RU[d.month]}, {DAY_RU[d.weekday()]}</b>\n✨ {service}\n\nВыбери время начала:",
            reply_markup=times_kb(ds, service)
        )
        await cb.answer()

    @dp.callback_query(BookState.choose_time, F.data.startswith("time_"))
    async def cb_time(cb: CallbackQuery, state: FSMContext):
        parts = cb.data.split("_", 2)
        ds, t = parts[1], parts[2]
        data = await state.get_data()
        service = data.get("service", "Наращивание")
        d = date.fromisoformat(ds)
        free = get_free_slots(d, service)
        if t not in free:
            await cb.answer("⚠️ Это время уже занято! Выбери другое.", show_alert=True)
            return
        await state.update_data(date=ds, time=t)
        await state.set_state(BookState.enter_name)
        await cb.message.edit_text(f"✅ <b>{ds} в {t}</b>\n✨ {service}\n\nКак тебя зовут?")
        await cb.answer()

    @dp.message(BookState.enter_name, F.text)
    async def book_name(message: Message, state: FSMContext):
        if len(message.text.strip()) < 2:
            await message.answer("Введи имя (минимум 2 символа):")
            return
        await state.update_data(name=message.text.strip())
        await state.set_state(BookState.enter_phone)
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="📱 Написать через Telegram", callback_data="use_tg_contact"))
        await message.answer("📱 Введи номер телефона\n\nИли нажми кнопку — и Анна напишет тебе в Telegram 👇", reply_markup=b.as_markup())

    @dp.callback_query(BookState.enter_phone, F.data == "use_tg_contact")
    async def cb_use_tg(cb: CallbackQuery, state: FSMContext):
        tg = f"@{cb.from_user.username}" if cb.from_user.username else f"ID: {cb.from_user.id}"
        await state.update_data(phone=tg)
        data = await state.get_data()
        dur = SERVICE_DURATION.get(data.get('service',''), 2)
        t = data.get('time','')
        if t:
            h, m = map(int, t.split(":"))
            end_m = h*60 + m + dur*30
            eh, em = divmod(end_m, 60)
            end_t = f"{eh:02d}:{em:02d}"
        else:
            end_t = "—"
        await state.set_state(BookState.confirm)
        await cb.message.edit_text(
            f"📋 <b>Проверь заявку:</b>\n\n📅 {data.get('date','')}\n🕐 {t} – {end_t}\n"
            f"✨ {data.get('service','')}\n👤 {data.get('name','')}\n📱 {tg}\n\nВсё верно?",
            reply_markup=confirm_kb(data.get('date',''), t, data.get('service',''))
        )
        await cb.answer()

    @dp.message(BookState.enter_phone, F.text)
    async def book_phone(message: Message, state: FSMContext):
        phone = message.text.strip()
        if len("".join(c for c in phone if c.isdigit())) < 9:
            await message.answer("Введи корректный номер:")
            return
        await state.update_data(phone=phone)
        data = await state.get_data()
        dur = SERVICE_DURATION.get(data['service'], 2)
        h, m = map(int, data['time'].split(":"))
        end_m = h*60 + m + dur*30
        eh, em = divmod(end_m, 60)
        await state.set_state(BookState.confirm)
        await message.answer(
            f"📋 <b>Проверь заявку:</b>\n\n📅 {data['date']}\n🕐 {data['time']} – {eh:02d}:{em:02d}\n"
            f"✨ {data['service']}\n👤 {data['name']}\n📱 {data['phone']}\n\nВсё верно?",
            reply_markup=confirm_kb(data['date'], data['time'], data['service'])
        )

    @dp.callback_query(BookState.confirm, F.data.startswith("confirm_"))
    async def book_confirm(cb: CallbackQuery, state: FSMContext, bot: Bot):
        data = await state.get_data()
        await state.clear()
        ds, t = data['date'], data['time']
        key = f"{ds}_{t}"
        bookings[key] = {
            "user_id": cb.from_user.id,
            "name": data['name'],
            "phone": data['phone'],
            "service": data['service'],
            "status": "pending",
            "reminded": False,
        }
        dur = SERVICE_DURATION.get(data['service'], 2)
        h, m = map(int, t.split(":"))
        end_m = h*60 + m + dur*30
        eh, em = divmod(end_m, 60)
        await notify_admin(bot,
            f"🆕 <b>Новая заявка!</b>\n\n📅 {ds}\n🕐 {t}–{eh:02d}:{em:02d}\n"
            f"✨ {data['service']}\n👤 {data['name']}\n📱 {data['phone']}\n"
            f"🆔 @{cb.from_user.username or '—'}",
            kb=admin_booking_kb(key)
        )
        await cb.message.edit_text(
            f"🎉 <b>Заявка отправлена!</b>\n\n📅 {ds} в {t}\n✨ {data['service']}\n\nАнна свяжется для подтверждения 💜",
            reply_markup=main_menu()
        )
        await cb.answer()

    # ── АДМИН ─────────────────────────────────────────────────────────────
    @dp.callback_query(F.data.startswith("adm_ok_"))
    async def adm_ok(cb: CallbackQuery, bot: Bot):
        if cb.from_user.id != ADMIN_ID: return
        key = cb.data.replace("adm_ok_","")
        if key in bookings:
            bookings[key]["status"] = "confirmed"
            uid = bookings[key]["user_id"]
            ds, t = key.split("_",1)
            try:
                await bot.send_message(uid,
                    f"✅ <b>Запись подтверждена!</b>\n\n📅 {ds} в {t}\n✨ {bookings[key]['service']}\n\nЖдём тебя! 💜",
                    reply_markup=main_menu())
            except: pass
        await cb.message.edit_text(cb.message.text + "\n\n✅ Подтверждено")
        await cb.answer("Клиент уведомлён ✅")

    @dp.callback_query(F.data.startswith("adm_no_"))
    async def adm_no(cb: CallbackQuery, bot: Bot):
        if cb.from_user.id != ADMIN_ID: return
        key = cb.data.replace("adm_no_","")
        if key in bookings:
            uid = bookings[key]["user_id"]
            ds, t = key.split("_",1)
            bookings[key]["status"] = "cancelled"
            try:
                await bot.send_message(uid, f"😔 Время {ds} в {t} недоступно.\n\nВыбери другое 👇", reply_markup=book_kb())
            except: pass
        await cb.message.edit_text(cb.message.text + "\n\n❌ Отменено")
        await cb.answer("Клиент уведомлён ❌")

    @dp.callback_query(F.data.startswith("send_review_"))
    async def send_review(cb: CallbackQuery, bot: Bot):
        if cb.from_user.id != ADMIN_ID: return
        key = cb.data.replace("send_review_","")
        if key not in bookings:
            await cb.answer("Запись не найдена")
            return
        bk = bookings[key]
        uid = bk["user_id"]
        name = bk["name"].split()[0] if bk["name"] else "красавица"
        review_text = (
            f"💜 {name}, привет!\n\n"
            f"Прошли сутки после наращивания — как твои новые волосы? "
            f"Надеюсь, уже успела насладиться их красотой 😍\n\n"
            f"Если понравился результат — буду очень рада отзыву. Это займёт 2 минуты 🙏\n\n"
            f"👇 Оставить отзыв на Яндекс Картах:"
        )
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="⭐ Оставить отзыв", url=YANDEX_MAPS_URL))
        try:
            await bot.send_message(uid, review_text, reply_markup=b.as_markup())
            await cb.message.edit_text(cb.message.text + f"\n\n✅ Запрос на отзыв отправлен {name}!")
            await cb.answer("Отправлено! ✅")
        except Exception as e:
            await cb.answer(f"Ошибка: {e}", show_alert=True)

    @dp.message(Command("admin"))
    async def cmd_admin(message: Message):
        if message.from_user.id != ADMIN_ID: return
        pending = [k for k,v in bookings.items() if v["status"]=="pending"]
        confirmed = [k for k,v in bookings.items() if v["status"]=="confirmed"]
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🚫 Закрыть день", callback_data="adm_block"))
        b.row(InlineKeyboardButton(text="✅ Открыть день", callback_data="adm_unblock"))
        b.row(InlineKeyboardButton(text="📊 Все записи", callback_data="adm_all"))
        await message.answer(
            f"👑 <b>Админ-панель</b>\n\n⏳ Ожидают: <b>{len(pending)}</b>\n"
            f"✅ Подтверждено: <b>{len(confirmed)}</b>\n🚫 Закрытых дней: <b>{len(blocked_dates)}</b>\n"
            f"👥 Клиентов: <b>{len(clients)}</b>",
            reply_markup=b.as_markup()
        )

    @dp.callback_query(F.data == "adm_block")
    async def adm_block(cb: CallbackQuery, state: FSMContext):
        if cb.from_user.id != ADMIN_ID: return
        await state.set_state(AdminState.blocking)
        await cb.message.edit_text("🚫 Введи дату для закрытия:\n<code>ГГГГ-ММ-ДД</code>\nНапр: <code>2025-05-20</code>")
        await cb.answer()

    @dp.callback_query(F.data == "adm_unblock")
    async def adm_unblock(cb: CallbackQuery, state: FSMContext):
        if cb.from_user.id != ADMIN_ID: return
        await state.set_state(AdminState.unblocking)
        closed = ", ".join(sorted(blocked_dates)) or "нет"
        await cb.message.edit_text(f"✅ Введи дату для открытия:\n<code>ГГГГ-ММ-ДД</code>\n\nЗакрыты: {closed}")
        await cb.answer()

    @dp.message(AdminState.blocking, F.text)
    async def adm_block_date(message: Message, state: FSMContext):
        if message.from_user.id != ADMIN_ID: return
        try:
            date.fromisoformat(message.text.strip())
            blocked_dates.add(message.text.strip())
            await state.clear()
            await message.answer(f"🚫 День <b>{message.text.strip()}</b> закрыт.")
        except: await message.answer("Неверный формат. Введи как: <code>2025-05-20</code>")

    @dp.message(AdminState.unblocking, F.text)
    async def adm_unblock_date(message: Message, state: FSMContext):
        if message.from_user.id != ADMIN_ID: return
        try:
            date.fromisoformat(message.text.strip())
            blocked_dates.discard(message.text.strip())
            await state.clear()
            await message.answer(f"✅ День <b>{message.text.strip()}</b> открыт.")
        except: await message.answer("Неверный формат.")

    @dp.callback_query(F.data == "adm_all")
    async def adm_all(cb: CallbackQuery):
        if cb.from_user.id != ADMIN_ID: return
        items = [(k,v) for k,v in bookings.items() if v["status"] in ("pending","confirmed")]
        items.sort(key=lambda x: x[0])
        if not items:
            await cb.message.edit_text("Записей нет.", reply_markup=back_kb())
        else:
            text = "📋 <b>Актуальные записи:</b>\n\n"
            for k, v in items[:10]:
                ds, t = k.split("_",1)
                icon = "⏳" if v["status"]=="pending" else "✅"
                text += f"{icon} {ds} {t} — {v['name']} {v['phone']}\n   {v['service']}\n\n"
            await cb.message.edit_text(text, reply_markup=back_kb())
        await cb.answer()

    # ── УСЛУГИ ────────────────────────────────────────────────────────────
    @dp.callback_query(F.data == "services")
    async def cb_services(cb: CallbackQuery):
        await cb.message.edit_text(
            "✨ <b>Услуги и цены</b>\n\n"
            "🔥 <b>Наращивание капсульное</b>\n  1.6 BYN/капсула + волосы (45–80 см)\n  Время: 4–6 ч\n\n"
            "💜 <b>Биопротеиновое</b>\n  350–400 BYN (с волосами)\n  +30–50 BYN за густоту\n  Время: 2–4 ч\n\n"
            "🎀 <b>Загущение</b>\n  от 160 BYN · Время: 2–3 ч\n\n"
            "✂️ <b>Снятие капсул:</b> 0.4 BYN/прядь\n"
            "✂️ <b>Снятие биопротеина:</b> 50 BYN/100г\n"
            "🔄 <b>Коррекция:</b> от 80 BYN",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "contacts")
    async def cb_contacts(cb: CallbackQuery):
        await cb.message.edit_text(
            f"📞 <b>Контакты</b>\n\n👩 Мастер: <b>Анна</b>\n📍 Брест (адрес при записи)\n📱 {PHONE}\n📸 @volos_capsula",
            reply_markup=back_kb()
        )
        await cb.answer()

    # ── МАГАЗИН ───────────────────────────────────────────────────────────
    @dp.callback_query(F.data == "shop")
    async def cb_shop(cb: CallbackQuery):
        await cb.message.edit_text("🛍 <b>Магазин Анны</b>", reply_markup=shop_kb())
        await cb.answer()

    @dp.callback_query(F.data == "free_guide")
    async def cb_free_guide(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="💎 Полный гайд по уходу — 9 BYN", callback_data="buy_guide"))
        b.row(InlineKeyboardButton(text="📅 Записаться", callback_data="book"))
        b.row(InlineKeyboardButton(text="← Меню", callback_data="menu"))
        await cb.message.edit_text(
            "🎁 <b>3 секрета, которые мастера не говорят вслух</b>\n\n"
            "Я работаю с наращиванием 5 лет — вот что реально важно знать:\n\n"
            "<b>Секрет 1. Капсулы роняет не техника — роняет уход</b>\n"
            "90% потерь из-за 3 ошибок: мокрые волосы в хвост, шампунь без пенки, расчёска от корней.\n\n"
            "<b>Секрет 2. Температура важнее средств</b>\n"
            "Горячая вода у корней разрушает капсулы быстрее любого шампуня. "
            "Тёплая вода = +3 недели носки.\n\n"
            "<b>Секрет 3. Опоздание на коррекцию = двойные расходы</b>\n"
            "Опоздание на 2 недели → капсулы у концов, колтуны, потеря пучков. "
            "Переделка стоит как новое наращивание.\n\n"
            "——————————————\n"
            "Это лишь верхушка айсберга 👆\n\n"
            "💎 <b>В полном гайде (9 BYN):</b>\n"
            "✅ Пошаговый уход на каждый день\n"
            "✅ Какие средства реально работают (HADAT, TIGI, L'Oréal)\n"
            "✅ Стоп-лист — 8 вещей которые убивают наращивание\n"
            "✅ Лайфхаки которых нет в интернете\n"
            "✅ График ухода по неделям до коррекции\n\n"
            "Клиентки которые следуют гайду носят наращивание 4+ месяца 💜\n\n"
            "👇 Хочешь такой же результат?",
            reply_markup=b.as_markup()
        )
        await cb.answer()

    @dp.callback_query(F.data == "buy_guide")
    async def cb_buy_guide(cb: CallbackQuery):
        card_text = f"\n\n💳 Перевод на карту: <code>{CARD}</code>" if CARD and CARD != "0000 0000 0000 0000" else f"\n\n📱 Напишите для оплаты: {PHONE}"
        await cb.message.edit_text(
            f"💎 <b>Гайд «Уход за нарощенными волосами»</b>\n\n"
            "Что внутри:\n"
            "✨ Как правильно расчёсывать\n✨ Какие средства использовать\n"
            "✨ Как мыть голову\n✨ Что делать перед сном\n"
            "✨ Стоп-лист — что категорически нельзя\n✨ Как продлить носку до максимума\n\n"
            f"💰 Стоимость: <b>9 BYN</b>{card_text}\n\nПосле перевода нажми кнопку ниже 👇",
            reply_markup=pay_kb("guide")
        )
        await cb.answer()

    @dp.callback_query(F.data == "buy_consult")
    async def cb_buy_consult(cb: CallbackQuery):
        await cb.message.edit_text(
            f"🤖 <b>ИИ-консультация</b>\n\n✨ Подбор метода\n✨ Точная стоимость\n✨ Ответы на вопросы\n\n"
            f"💰 <b>19 BYN</b>\nКарта: <code>{CARD}</code>",
            reply_markup=pay_kb("consult")
        )
        await cb.answer()

    @dp.callback_query(F.data.startswith("paid_"))
    async def cb_paid(cb: CallbackQuery, bot: Bot):
        product = cb.data.replace("paid_","")
        names = {"guide":"Гайд по уходу (9 BYN)","consult":"ИИ-консультация (19 BYN)"}
        await notify_admin(bot,
            f"💰 <b>Новая оплата!</b>\n\nПродукт: {names.get(product,product)}\n"
            f"👤 {cb.from_user.first_name} @{cb.from_user.username or '—'}\n"
            f"🆔 {cb.from_user.id}\n\nПроверь платёж и подтверди отправку!"
        )
        if product == "guide":
            await cb.message.edit_text(
                "⏳ Анна проверяет платёж и пришлёт гайд в течение нескольких минут 💜\n\nОбычно это занимает 5-10 минут.",
                reply_markup=back_kb()
            )
            b = InlineKeyboardBuilder()
            b.row(InlineKeyboardButton(text="✅ Отправить гайд клиентке", callback_data=f"send_guide_{cb.from_user.id}"))
            await notify_admin(bot,
                f"📖 Нажми чтобы отправить гайд клиентке @{cb.from_user.username or cb.from_user.id}",
                kb=b.as_markup()
            )
        else:
            await cb.message.edit_text("✅ Оплата получена! Анна свяжется для начала консультации 💜", reply_markup=back_kb())
        await cb.answer()

    # ── ОТПРАВКА ГАЙДА ────────────────────────────────────────────────────
    @dp.callback_query(F.data.startswith("send_guide_"))
    async def cb_send_guide(cb: CallbackQuery, bot: Bot):
        if cb.from_user.id != ADMIN_ID: return
        uid = int(cb.data.replace("send_guide_",""))
        caption = (
            "💜 <b>Твой персональный гайд готов!</b>\n\n"
            "«Секреты долгой носки наращивания» — всё, что нужно знать "
            "для красоты волос до следующей коррекции.\n\n"
            "📌 Сохрани и возвращайся когда нужно!\n\n"
            "По любым вопросам — всегда на связи 💜\n"
            "Instagram: @volos_capsula"
        )
        try:
            await bot.send_document(
                uid,
                document=GUIDE_URL,
                caption=caption,
                reply_markup=InlineKeyboardBuilder().row(
                    InlineKeyboardButton(text="📅 Записаться на коррекцию", callback_data="book")
                ).as_markup()
            )
            await cb.message.edit_text(cb.message.text + "\n\n✅ Гайд (PDF) отправлен!")
            await cb.answer("Гайд отправлен ✅")
        except Exception as e:
            await cb.answer(f"Ошибка: {e}", show_alert=True)

    # ── КВИЗ ──────────────────────────────────────────────────────────────
    @dp.callback_query(F.data == "quiz")
    async def cb_quiz(cb: CallbackQuery, state: FSMContext):
        await state.clear()
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="До плеч (до 30 см)", callback_data="q1_short"))
        b.row(InlineKeyboardButton(text="До лопаток (30–45 см)", callback_data="q1_mid"))
        b.row(InlineKeyboardButton(text="Длиннее лопаток", callback_data="q1_long"))
        await cb.message.edit_text("✨ <b>Квиз</b>\n\n<b>Вопрос 1:</b> Длина волос?", reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data.startswith("q1_"))
    async def q2(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="Тонкие / редкие", callback_data=f"q2_thin|{cb.data}"))
        b.row(InlineKeyboardButton(text="Средние", callback_data=f"q2_mid|{cb.data}"))
        b.row(InlineKeyboardButton(text="Густые", callback_data=f"q2_thick|{cb.data}"))
        await cb.message.edit_text("<b>Вопрос 2:</b> Плотность?", reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data.startswith("q2_"))
    async def q3(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="Хочу длину", callback_data=f"q3_len|{cb.data}"))
        b.row(InlineKeyboardButton(text="Хочу объём", callback_data=f"q3_vol|{cb.data}"))
        b.row(InlineKeyboardButton(text="Быстро", callback_data=f"q3_fast|{cb.data}"))
        b.row(InlineKeyboardButton(text="Бережно", callback_data=f"q3_gentle|{cb.data}"))
        await cb.message.edit_text("<b>Вопрос 3:</b> Цель?", reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data.startswith("q3_"))
    async def q_res(cb: CallbackQuery):
        d = cb.data
        if "thin" in d or "fast" in d: m,i,p="Загущение","🎀","от 160 BYN"; desc="Быстро и бережно."
        elif "gentle" in d: m,i,p="Биопротеиновое","💜","350–400 BYN"; desc="Без стресса для волос."
        else: m,i,p="Наращивание","🔥","1.6 BYN/капсула"; desc="Универсальный метод, 3-4 месяца."
        await cb.message.edit_text(f"{i} <b>{m}</b>\n\n💰 {p}\n{desc}", reply_markup=book_kb())
        await cb.answer()

    # ── КАЛЬКУЛЯТОР ───────────────────────────────────────────────────────
    @dp.callback_query(F.data == "calc")
    async def cb_calc(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🔥 Капсульное", callback_data="calc_cap"))
        b.row(InlineKeyboardButton(text="💜 Биопротеиновое — 350–400 BYN", callback_data="calc_bio"))
        b.row(InlineKeyboardButton(text="🎀 Загущение — от 160 BYN", callback_data="calc_tape"))
        b.row(InlineKeyboardButton(text="✂️ Снятие", callback_data="calc_rem"))
        b.row(InlineKeyboardButton(text="← Назад", callback_data="menu"))
        await cb.message.edit_text("💰 <b>Калькулятор</b>", reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data == "calc_bio")
    async def calc_bio(cb: CallbackQuery):
        await cb.message.edit_text(
            "💜 <b>Биопротеиновое</b>\n\nБазовая: <b>350 BYN</b> (с волосами)\nДоплата за густоту: <b>+30–50 BYN</b>\n\n💰 Итого: <b>350–400 BYN</b>",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_tape")
    async def calc_tape(cb: CallbackQuery):
        await cb.message.edit_text("🎀 <b>Загущение</b>\n\n💰 <b>от 160 BYN</b>", reply_markup=book_kb())
        await cb.answer()

    @dp.callback_query(F.data == "calc_rem")
    async def calc_rem(cb: CallbackQuery):
        await cb.message.edit_text(
            "✂️ <b>Снятие</b>\n\n• Капсулы: 0.4 BYN/прядь (100пр = 40 BYN)\n• Биопротеин: 50 BYN/100г",
            reply_markup=book_kb()
        )
        await cb.answer()

    @dp.callback_query(F.data == "calc_cap")
    async def calc_cap(cb: CallbackQuery):
        b = InlineKeyboardBuilder()
        for n in [80,100,120,150,200]:
            b.button(text=f"{n}кап={round(n*1.6,1)}р", callback_data=f"cap_{n}")
        b.adjust(2)
        b.row(InlineKeyboardButton(text="← Назад", callback_data="calc"))
        await cb.message.edit_text("🔥 <b>Капсульное — 1.6 BYN/капсула</b>", reply_markup=b.as_markup())
        await cb.answer()

    @dp.callback_query(F.data.startswith("cap_"))
    async def cap_res(cb: CallbackQuery):
        n = int(cb.data.split("_")[1])
        w = round(n*1.6,1)
        lines = "\n".join(f"• {l}см → {w+p:.0f} BYN" for l,p in HAIR_PRICES.items())
        await cb.message.edit_text(
            f"🔥 <b>{n} капсул</b>\nРабота: <b>{w} BYN</b>\n\n<b>С волосами:</b>\n{lines}",
            reply_markup=book_kb()
        )
        await cb.answer()

    # ── ИИ ────────────────────────────────────────────────────────────────
    @dp.callback_query(F.data == "ai")
    async def cb_ai(cb: CallbackQuery, state: FSMContext):
        await state.set_state(AIState.chatting)
        await state.update_data(history=[])
        await cb.message.edit_text(
            "🤖 <b>ИИ-консультант</b>\n\nЗадай любой вопрос!\n\n<i>← Выйти — для возврата</i>",
            reply_markup=ai_kb()
        )
        await cb.answer()

    @dp.message(AIState.chatting, F.text)
    async def ai_msg(message: Message, state: FSMContext):
        data = await state.get_data()
        history = data.get("history",[])
        thinking = await message.answer("💭 Думаю...")
        answer = await ask_claude(message.text, history)
        history = (history + [{"role":"user","content":message.text}, {"role":"assistant","content":answer}])[-6:]
        await state.update_data(history=history)
        await thinking.delete()
        await message.answer(answer, reply_markup=ai_kb())

    # ── СВОБОДНЫЙ ТЕКСТ ───────────────────────────────────────────────────
    @dp.message(F.text)
    async def any_text(message: Message, state: FSMContext):
        cur = await state.get_state()
        skip = [AIState.chatting, BookState.enter_name, BookState.enter_phone, AdminState.blocking, AdminState.unblocking]
        if cur in [str(s) for s in skip]: return
        t = message.text.lower()
        if any(w in t for w in ["цен","сколько","стоит","прайс"]):
            await message.answer("Кратко о ценах 👇", reply_markup=back_kb())
        elif any(w in t for w in ["запис","прийти","время"]):
            await message.answer("📅 Выбирай удобное время 👇", reply_markup=book_kb())
        elif any(w in t for w in ["привет","здравств","добрый","hello"]):
            name = message.from_user.first_name or "красавица"
            await message.answer(f"💜 Привет, <b>{name}</b>! 👇", reply_markup=main_menu())
        else:
            await message.answer("💜 Выбирай 👇", reply_markup=main_menu())

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
