import logging
import json
import sqlite3

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import (
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# ================== LOG ==================
logging.basicConfig(level=logging.INFO)

# ================== CONFIG ==================
with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

BOT_TOKEN = cfg.get("bot_token")
ADMIN_ID = int(cfg.get("admin_id"))
CHANNEL_ID = cfg.get("channel_id", "@dream_league_Uzb")
PROMO_CHANNELS = cfg.get("promo_channels", [])
CONTEST_OPEN = cfg.get("contest_open", True)

# ================== BOT ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ================== DB ==================
conn = sqlite3.connect("submissions.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS submissions (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    team TEXT,
    photo TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS channel_posts (
    post_id INTEGER PRIMARY KEY,
    post_link TEXT,
    total_reactions INTEGER DEFAULT 0,
    reactions_text TEXT DEFAULT ''
)
""")

conn.commit()

# ================== FSM ==================
class Form(StatesGroup):
    waiting_photo = State()
    waiting_team = State()
    waiting_confirm = State()

# ================== HELPERS ==================
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def already_sent(uid: int) -> bool:
    cur.execute("SELECT 1 FROM submissions WHERE user_id=?", (uid,))
    return cur.fetchone() is not None

async def check_subs(user_id: int) -> list:
    not_joined = []
    for ch in PROMO_CHANNELS:
        chat_id = ch.replace("https://t.me/", "").strip()
        if not chat_id.startswith("@") and not chat_id.startswith("-100"):
            chat_id = "@" + chat_id
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status not in ("member", "administrator", "creator"):
                not_joined.append(chat_id)
        except Exception:
            not_joined.append(chat_id)
    return not_joined

# ================== /START ==================
@dp.message_handler(commands=["start"], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()

    if already_sent(message.from_user.id):
        await message.answer("❌ Siz allaqachon ma’lumot yuborgansiz.")
        return

    text = (
        "Salom, bu DLS ISMOILOV konkursida qatnashish uchun yaratilgan bot ✅\n\n"
        "Botdagi shartlarga rioya qiling va konkursda bemalol qatnashavering ❗️"
    )

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Boshlash", callback_data="start_flow"))

    await message.answer(text, reply_markup=kb)

    if is_admin(message.from_user.id):
        admin_kb = ReplyKeyboardMarkup(resize_keyboard=True)
        admin_kb.add("🏆 TOP-100 postlar")
        await message.answer("🔧 Admin panel", reply_markup=admin_kb)

# ================== START FLOW ==================
@dp.callback_query_handler(text="start_flow")
async def start_flow(cb: types.CallbackQuery):
    if not CONTEST_OPEN:
        await cb.message.answer("⛔ Konkurs yopilgan.")
        await cb.answer()
        return

    not_joined = await check_subs(cb.from_user.id)
    if not_joined:
        text = "❌ Iltimos, quyidagi kanallarga obuna bo‘ling:\n\n"
        kb = InlineKeyboardMarkup()
        for ch in not_joined:
            kb.add(InlineKeyboardButton("Obuna bo‘lish", url=f"https://t.me/{ch.lstrip('@')}"))
        kb.add(InlineKeyboardButton("Tasdiqlash", callback_data="start_flow"))
        await cb.message.answer(text, reply_markup=kb)
        await cb.answer()
        return

    await cb.message.answer("📸 Rasm yuboring:")
    await Form.waiting_photo.set()
    await cb.answer()

# ================== PHOTO ==================
@dp.message_handler(content_types=types.ContentType.PHOTO, state=Form.waiting_photo)
async def get_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("🏷 Jamoa nomini kiriting:")
    await Form.waiting_team.set()

# ================== TEAM ==================
@dp.message_handler(state=Form.waiting_team)
async def get_team(message: types.Message, state: FSMContext):
    await state.update_data(team=message.text)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Tasdiqlash", callback_data="confirm"))
    kb.add(InlineKeyboardButton("Tahrirlash", callback_data="edit"))

    await message.answer("✅ Ma’lumotlarni tasdiqlang:", reply_markup=kb)
    await Form.waiting_confirm.set()

# ================== EDIT ==================
@dp.callback_query_handler(text="edit", state=Form.waiting_confirm)
async def edit(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("🏷 Jamoa nomini qayta kiriting:")
    await Form.waiting_team.set()
    await cb.answer()

# ================== CONFIRM ==================
@dp.callback_query_handler(text="confirm", state=Form.waiting_confirm)
async def confirm(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    if already_sent(uid):
        await cb.message.answer("❌ Siz allaqachon yuborgansiz.")
        await state.finish()
        await cb.answer()
        return

    data = await state.get_data()
    username = f"@{cb.from_user.username}" if cb.from_user.username else cb.from_user.full_name

    cur.execute(
        "INSERT INTO submissions VALUES (?,?,?,?)",
        (uid, username, data["team"], data["photo"])
    )
    conn.commit()

    caption = (
        f"🏆 Ishtirokchi: {username}\n"
        f"📌 Jamoa: {data['team']}\n\n"
        "✅ BIZDAN UZOQLASHMANG ♻️\n"
        "👇👇👇\n"
        "https://t.me/dream_league_Uzb"
    )

    await bot.send_photo(ADMIN_ID, data["photo"], caption=caption)
    await bot.send_photo(uid, data["photo"], caption=caption)

    await cb.message.answer("✅ Ma’lumotlar yuborildi!")
    await state.finish()
    await cb.answer()

# ================== TOP-100 ==================
@dp.message_handler(lambda m: m.text and "TOP-100" in m.text)
async def top_100(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    cur.execute("""
        SELECT post_link, total_reactions, reactions_text
        FROM channel_posts
        WHERE total_reactions > 0
        ORDER BY total_reactions DESC
        LIMIT 100
    """)
    rows = cur.fetchall()

    if not rows:
        await message.answer("❌ Ma’lumot yo‘q.")
        return

    text = "🏆 TOP-100 POSTLAR\n\n"
    for i, (link, total, details) in enumerate(rows, 1):
        block = f"{i}. 📊 {total}\n{details}\n{link}\n\n"
        if len(text) + len(block) > 3800:
            await message.answer(text)
            text = ""
        text += block

    if text:
        await message.answer(text)

# ================== RUN ==================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
