import logging
import os
import json
import sqlite3

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

conn = sqlite3.connect("submissions.db")
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
conn.commit()


# ================== HELPERS ==================

def save_config():
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def has_submitted(user_id: int) -> bool:
    cur.execute("SELECT 1 FROM submissions WHERE user_id = ? LIMIT 1", (user_id,))
    return cur.fetchone() is not None


def get_display_username(user: types.User) -> str:
    return f"@{user.username}" if user.username else user.full_name


# ================== STATES ==================

class Form(StatesGroup):
    waiting_screenshot = State()
    waiting_team = State()
    waiting_confirm = State()


# ================== START ==================

@dp.message_handler(commands=["start"], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()

    # ===== ADMIN =====
    if is_admin(message.from_user.id):
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("📋 Ishtirokchilar ro‘yxati", callback_data="admin_list")) # type: ignore

        if cfg.get("contest_open", True):
            kb.add(types.InlineKeyboardButton("🔴 Konkursni yopish", callback_data="contest_close")) # type: ignore
        else:
            kb.add(types.InlineKeyboardButton("🟢 Konkursni ochish", callback_data="contest_open")) # type: ignore

        await message.answer("👑 Admin panel", reply_markup=kb)
        return

    # ===== CLOSED =====
    if not cfg.get("contest_open", True):
        await message.answer("⛔ Konkurs hozircha yopiq.")
        return

    if has_submitted(message.from_user.id):
        await message.answer("❌ Siz allaqachon qatnashgansiz.")
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Boshlash", callback_data="start_flow")) # type: ignore

    await message.answer(
        "Salom, bu DLS ISMOILOV konkursida qatnashish uchun yaratilgan bot ✅",
        reply_markup=kb
    )


# ================== START FLOW ==================

@dp.callback_query_handler(lambda c: c.data == "start_flow")
async def start_flow(cb: types.CallbackQuery):
    await cb.message.answer("📸 Iltimos, skrinshotni yuboring:")
    await Form.waiting_screenshot.set()
    await cb.answer()


# ================== SCREENSHOT ==================

@dp.message_handler(content_types=types.ContentType.PHOTO, state=Form.waiting_screenshot)
async def get_screenshot(message: types.Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await message.answer("🏷 Jamoa nomini kiriting:")
    await Form.waiting_team.set()


# ================== TEAM ==================

@dp.message_handler(state=Form.waiting_team)
async def get_team(message: types.Message, state: FSMContext):
    await state.update_data(team=message.text)

    data = await state.get_data()
    username = get_display_username(message.from_user)

    caption = (
        f"👤 Ishtirokchi: {username}\n"
        f"🏷 Jamoa nomi: {data['team']}\n\n"
        f"Ma’lumotlarni tasdiqlaysizmi?"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data="confirm"), # type: ignore
        types.InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit") # type: ignore
    )

    await message.answer_photo(
        data["photo_file_id"],
        caption=caption,
        reply_markup=kb
    )
    await Form.waiting_confirm.set()


# ================== EDIT ==================

@dp.callback_query_handler(lambda c: c.data == "edit", state=Form.waiting_confirm)
async def edit(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("✏️ Yangi jamoa nomini kiriting:")
    await Form.waiting_team.set()
    await cb.answer()


# ================== CONFIRM ==================

@dp.callback_query_handler(lambda c: c.data == "confirm", state=Form.waiting_confirm)
async def confirm(cb: types.CallbackQuery, state: FSMContext):
    user = cb.from_user

    if has_submitted(user.id):
        await cb.message.answer("❌ Qayta yuborish mumkin emas.")
        await state.finish()
        return

    data = await state.get_data()
    username = get_display_username(user)

    cur.execute(
        "INSERT INTO submissions (user_id, username, team, photo_file_id) VALUES (?,?,?,?)",
        (user.id, username, data["team"], data["photo_file_id"])
    )
    conn.commit()

    counter = cfg.get("submission_counter", 1)
    cfg["submission_counter"] = counter + 1
    save_config()

    caption = (
        f"🏆 {counter}_Ishtirokchimiz {username}\n"
        f"📌 Jamoa nomi : {data['team']}\n\n"
        f"✅ BIZDAN UZOQLASHMANG ♻️\n"
        f"👇👇👇\n"
        f"https://t.me/dream_league_Uzb"
    )

    await bot.send_photo(ADMIN_ID, data["photo_file_id"], caption=caption)
    await cb.message.answer("✅ Ma’lumotlar qabul qilindi.")
    await bot.send_photo(user.id, data["photo_file_id"], caption=caption)

    await state.finish()
    await cb.answer()


# ================== ADMIN LIST ==================

@dp.callback_query_handler(lambda c: c.data == "admin_list")
async def admin_list(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return

    cur.execute("SELECT username, team FROM submissions")
    rows = cur.fetchall()

    text = f"📊 Jami ishtirokchilar: {len(rows)}\n\n"
    for i, (u, t) in enumerate(rows, 1):
        text += f"{i}. {u} — {t}\n"

    await cb.message.answer(text)
    await cb.answer()


# ================== CONTEST CONTROL ==================

@dp.callback_query_handler(lambda c: c.data == "contest_close")
async def contest_close(cb: types.CallbackQuery):
    cfg["contest_open"] = False
    save_config()
    await cb.message.answer("⛔ Konkurs yopildi.")
    await cb.answer()


@dp.callback_query_handler(lambda c: c.data == "contest_open")
async def contest_open(cb: types.CallbackQuery):
    cfg["contest_open"] = True
    save_config()
    await cb.message.answer("🟢 Konkurs ochildi.")
    await cb.answer()


# ================== RUN ==================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
