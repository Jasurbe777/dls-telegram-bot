import logging
import json
import os
import sqlite3

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# ================== CONFIG ==================
with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or cfg.get("bot_token")
ADMIN_ID = int(cfg.get("admin_id"))

logging.basicConfig(level=logging.INFO)

if not BOT_TOKEN:
    raise RuntimeError("BOT TOKEN yo‘q")

# ================== BOT ==================
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

# ================== STATES ==================
class Form(StatesGroup):
    waiting_screenshot = State()
    waiting_team = State()
    waiting_confirm = State()

class AdminForm(StatesGroup):
    waiting_promo = State()
    waiting_counter = State()

# ================== HELPERS ==================
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def save_config():
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def user_already_submitted(user_id: int) -> bool:
    cur.execute("SELECT 1 FROM submissions WHERE user_id = ?", (user_id,))
    return cur.fetchone() is not None

# ================== START ==================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    if user_already_submitted(message.from_user.id):
        await message.answer(
            "✅ Siz allaqachon maʼlumot yuborgansiz.\n"
            "Yangi yuborish mumkin emas."
        )
        return

    text = (
        "Salom, bu DLS ISMOILOV konkursida qatnashish uchun yaratilgan bot ✅\n\n"
        "Botdagi shartlarga rioya qiling va konkursda bemalol qatnashavering ❗️"
    )

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Boshlash", callback_data="start_flow"))

    await message.answer(text, reply_markup=kb)

    if is_admin(message.from_user.id):
        admin_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        admin_kb.add("Ishtirokchilar ro‘yxati")
        admin_kb.add("Konkursni boshqarish")
        admin_kb.add("Sozlash (raqam kiritish)")
        admin_kb.add("Reklamalarni boshqarish")
        await message.answer("👑 Admin panel", reply_markup=admin_kb)

# ================== START FLOW ==================
@dp.callback_query_handler(lambda c: c.data == "start_flow")
async def start_flow(cb: types.CallbackQuery):
    if user_already_submitted(cb.from_user.id):
        await cb.message.answer(
            "❌ Siz allaqachon maʼlumot yuborgansiz."
        )
        await cb.answer()
        return

    promo_channels = cfg.get("promo_channels", [])

    if not promo_channels:
        await cb.message.answer("📸 Dream League profilingiz skrinshotini yuboring:")
        await Form.waiting_screenshot.set()
        await cb.answer()
        return

    kb = InlineKeyboardMarkup(row_width=1)
    for ch in promo_channels:
        url = ch if ch.startswith("http") else f"https://t.me/{ch.lstrip('@')}"
        kb.add(InlineKeyboardButton("🔘 Obuna bo‘lish", url=url))

    kb.add(InlineKeyboardButton("Men obuna bo‘ldim (tekshirilsin)", callback_data="check_subs"))

    await cb.message.answer(
        "Iltimos, quyidagi kanallarga obuna bo‘ling:",
        reply_markup=kb
    )
    await cb.answer()

# ================== CHECK SUBS ==================
@dp.callback_query_handler(lambda c: c.data == "check_subs")
async def check_subs(cb: types.CallbackQuery):
    for ch in cfg.get("promo_channels", []):
        chat = ch.replace("https://t.me/", "").lstrip("@")
        try:
            member = await bot.get_chat_member(f"@{chat}", cb.from_user.id)
            if member.status in ("left", "kicked"):
                await cb.message.answer(
                    f"❌ Siz hali @{chat} kanaliga obuna bo‘lmadingiz."
                )
                await cb.answer()
                return
        except:
            await cb.message.answer(f"⚠️ @{chat} tekshirib bo‘lmadi")
            await cb.answer()
            return

    await cb.message.answer("📸 Skrinshot yuboring:")
    await Form.waiting_screenshot.set()
    await cb.answer()

# ================== SCREENSHOT ==================
@dp.message_handler(content_types=["photo"], state=Form.waiting_screenshot)
async def get_screenshot(message: types.Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await message.answer("🏷 Jamoa nomini kiriting:")
    await Form.waiting_team.set()

@dp.message_handler(state=Form.waiting_team)
async def get_team(message: types.Message, state: FSMContext):
    team = message.text.strip()
    if not team:
        await message.answer("❌ Jamoa nomi noto‘g‘ri.")
        return

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name

    await state.update_data(team=team, username=username)

    data = await state.get_data()

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Tasdiqlash", callback_data="confirm"))
    kb.add(InlineKeyboardButton("Tahrirlash", callback_data="edit"))

    caption = (
        f"👤 {username}\n"
        f"🏷 Jamoa: {team}\n\n"
        "Maʼlumotlar to‘g‘rimi?"
    )

    await message.answer_photo(
        photo=data["photo_file_id"],
        caption=caption,
        reply_markup=kb
    )

    await Form.waiting_confirm.set()

# ================== CONFIRM ==================
@dp.callback_query_handler(lambda c: c.data == "confirm", state=Form.waiting_confirm)
async def confirm(cb: types.CallbackQuery, state: FSMContext):
    if user_already_submitted(cb.from_user.id):
        await cb.message.answer("❌ Siz allaqachon yuborgansiz.")
        await state.finish()
        await cb.answer()
        return

    data = await state.get_data()
    user = cb.from_user

    cur.execute(
        "INSERT INTO submissions (user_id, username, team, photo_file_id) VALUES (?,?,?,?)",
        (user.id, data["username"], data["team"], data["photo_file_id"])
    )
    conn.commit()

    counter = cfg.get("submission_counter", 1)
    cfg["submission_counter"] = counter + 1
    save_config()

    caption = (
        f"🏆 {counter}_Ishtirokchimiz {data['username']}\n"
        f"📌 Jamoa nomi : {data['team']}\n\n"
        "✅ BIZDAN UZOQLASHMANG ♻️\n"
        "👇👇👇\n"
        "https://t.me/dream_league_Uzb"
    )

    await bot.send_photo(ADMIN_ID, data["photo_file_id"], caption=caption)
    await bot.send_photo(user.id, data["photo_file_id"], caption=caption)

    await cb.message.answer("✅ Maʼlumotlaringiz qabul qilindi!")
    await state.finish()
    await cb.answer()

# ================== RUN ==================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
