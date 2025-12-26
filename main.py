import logging
import os
import json
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup


# ================== CONFIG ==================

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT TOKEN topilmadi!")

with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

ADMIN_ID = int(cfg["admin_id"])

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())


# ================== DATABASE ==================

conn = sqlite3.connect("database.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    username TEXT,
    team TEXT,
    photo_file_id TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS ads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT,
    expires_at TEXT
)
""")

conn.commit()


# ================== HELPERS ==================

def save_config():
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def has_submitted(uid: int) -> bool:
    cur.execute("SELECT 1 FROM submissions WHERE user_id=?", (uid,))
    return cur.fetchone() is not None


def get_username(user: types.User) -> str:
    return f"@{user.username}" if user.username else user.full_name


def clean_expired_ads():
    now = datetime.utcnow().isoformat()
    cur.execute("DELETE FROM ads WHERE expires_at <= ?", (now,))
    conn.commit()


def get_active_ads_text() -> str:
    clean_expired_ads()
    cur.execute("SELECT channel FROM ads")
    rows = cur.fetchall()
    if not rows:
        return ""
    text = "\n".join([f"👉 {r[0]}" for r in rows])
    return f"\n\n📢 Reklama:\n{text}"


def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True) # type: ignore
    kb.add("📋 Ishtirokchilar ro‘yxati")

    if cfg.get("contest_open", True):
        kb.add("⛔ Konkursni yopish")
    else:
        kb.add("🟢 Konkursni ochish")

    kb.add("📢 Reklama kanalini qo‘shish")
    kb.add("🗑 Reklama kanalini o‘chirish")
    kb.add("🔢 Sozlash (raqam kiritish)")
    return kb


# ================== STATES ==================

class Form(StatesGroup):
    screenshot = State()
    team = State()
    confirm = State()

class AdForm(StatesGroup):
    channel = State()
    duration = State()


# ================== START ==================

@dp.message_handler(commands=["start"], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()

    if is_admin(message.from_user.id):
        await message.answer("👑 Admin panel", reply_markup=admin_keyboard())
        return

    if not cfg.get("contest_open", True):
        await message.answer("⛔ Konkurs yopiq.")
        return

    if has_submitted(message.from_user.id):
        await message.answer("❌ Siz allaqachon qatnashgansiz.")
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Boshlash", callback_data="start_flow")) # type: ignore

    await message.answer("📸 Konkursda qatnashish uchun boshlang:", reply_markup=kb)


# ================== USER FLOW ==================

@dp.callback_query_handler(lambda c: c.data == "start_flow")
async def start_flow(cb: types.CallbackQuery):
    await cb.message.answer("📸  Dream League profilingiz rasmini yuboring:")
    await Form.screenshot.set()
    await cb.answer()


@dp.message_handler(content_types=types.ContentType.PHOTO, state=Form.screenshot)
async def screenshot(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("🏷 Jamoa nomini kiriting:")
    await Form.team.set()


@dp.message_handler(state=Form.team)
async def team(message: types.Message, state: FSMContext):
    await state.update_data(team=message.text)

    data = await state.get_data()
    caption = (
        f"👤 {get_username(message.from_user)}\n"
        f"🏷 Jamoa: {data['team']}\n\n"
        "Tasdiqlaysizmi?"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data="confirm"), # type: ignore
        types.InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit") # type: ignore
    )

    await message.answer_photo(data["photo"], caption=caption, reply_markup=kb)
    await Form.confirm.set()


@dp.callback_query_handler(lambda c: c.data == "edit", state=Form.confirm)
async def edit(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("✏️ Yangi jamoa nomini kiriting:")
    await Form.team.set()
    await cb.answer()


@dp.callback_query_handler(lambda c: c.data == "confirm", state=Form.confirm)
async def confirm(cb: types.CallbackQuery, state: FSMContext):
    user = cb.from_user
    if has_submitted(user.id):
        await cb.message.answer("❌ Qayta yuborish mumkin emas.")
        await state.finish()
        return

    data = await state.get_data()
    username = get_username(user)

    cur.execute(
        "INSERT INTO submissions (user_id, username, team, photo_file_id) VALUES (?,?,?,?)",
        (user.id, username, data["team"], data["photo"])
    )
    conn.commit()

    counter = cfg.get("submission_counter", 1)
    cfg["submission_counter"] = counter + 1
    save_config()

    caption = (
        f"🏆 {counter}_Ishtirokchimiz {username}\n"
        f"📌 Jamoa nomi : {data['team']}"
        + get_active_ads_text()
    )

    await bot.send_photo(ADMIN_ID, data["photo"], caption=caption)
    await bot.send_photo(user.id, data["photo"], caption=caption)

    await cb.message.answer("✅ Qabul qilindi.")
    await state.finish()
    await cb.answer()


# ================== ADMIN ADS ==================

@dp.message_handler(lambda m: m.text == "📢 Reklama kanalini qo‘shish")
async def add_ad(message: types.Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("📢 Kanal linkini yuboring:")
    await AdForm.channel.set()


@dp.message_handler(state=AdForm.channel)
async def ad_channel(message: types.Message, state: FSMContext):
    await state.update_data(channel=message.text)
    await message.answer("⏳ Necha kun bo‘lsin? (masalan: 3)")
    await AdForm.duration.set()


@dp.message_handler(state=AdForm.duration)
async def ad_duration(message: types.Message, state: FSMContext):
    days = int(message.text)
    data = await state.get_data()

    expires = datetime.utcnow() + timedelta(days=days)

    cur.execute(
        "INSERT INTO ads (channel, expires_at) VALUES (?,?)",
        (data["channel"], expires.isoformat())
    )
    conn.commit()

    await message.answer("✅ Reklama qo‘shildi.", reply_markup=admin_keyboard())
    await state.finish()


@dp.message_handler(lambda m: m.text == "🗑 Reklama kanalini o‘chirish")
async def remove_ad(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    cur.execute("SELECT id, channel FROM ads")
    rows = cur.fetchall()
    if not rows:
        await message.answer("📭 Reklamalar yo‘q.")
        return

    text = "🗑 O‘chirish uchun ID yuboring:\n\n"
    for r in rows:
        text += f"{r[0]}. {r[1]}\n"

    await message.answer(text)


# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
