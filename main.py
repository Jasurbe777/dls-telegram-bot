import json
import os
import sqlite3
import logging

from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# ================= CONFIG =================
with open("config.json", encoding="utf-8") as f:
    cfg = json.load(f)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or cfg.get("bot_token")
ADMIN_ID = int(cfg["admin_id"])

if not BOT_TOKEN:
    raise RuntimeError("BOT TOKEN yo‘q")

logging.basicConfig(level=logging.INFO)

bot = Bot(BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ================= DATABASE =================
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
conn.commit()

# ================= STATES =================
class Form(StatesGroup):
    screenshot = State()
    team = State()
    confirm = State()

class AdminState(StatesGroup):
    counter = State()
    promo = State()

# ================= HELPERS =================
def is_admin(uid):
    return uid == ADMIN_ID

def already_sent(uid):
    cur.execute("SELECT 1 FROM submissions WHERE user_id=?", (uid,))
    return cur.fetchone() is not None

def save_config():
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def admin_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📋 Ishtirokchilar ro‘yxati")
    kb.add("⏳ Konkursni boshqarish")
    kb.add("🔢 Sozlash (raqam kiritish)")
    kb.add("📢 Reklamalarni boshqarish")
    return kb

# ================= START =================
@dp.message_handler(commands=["start"], state="*")
async def start(msg: types.Message, state: FSMContext):
    await state.finish()

    await msg.answer(
        "Salom, bu DLS ISMOILOV konkursida qatnashish uchun yaratilgan bot ✅\n\n"
        "Botdagi shartlarga rioya qiling va konkursda bemalol qatnashavering ❗️"
    )

    if is_admin(msg.from_user.id):
        await msg.answer("👑 Admin panel", reply_markup=admin_keyboard())

# ================= USER FLOW =================
@dp.message_handler(lambda m: m.text == "Boshlash")
async def user_start(msg: types.Message):
    if already_sent(msg.from_user.id):
        await msg.answer("✅ Siz allaqachon ma’lumot yuborgansiz.")
        return

    await msg.answer("📸 Skrinshot yuboring:")
    await Form.screenshot.set()

@dp.message_handler(content_types=types.ContentType.PHOTO, state=Form.screenshot)
async def get_photo(msg: types.Message, state: FSMContext):
    await state.update_data(photo=msg.photo[-1].file_id)
    await msg.answer("🏷 Jamoa nomini kiriting:")
    await Form.team.set()

@dp.message_handler(state=Form.team)
async def get_team(msg: types.Message, state: FSMContext):
    await state.update_data(team=msg.text.strip())

    data = await state.get_data()
    username = f"@{msg.from_user.username}" if msg.from_user.username else msg.from_user.full_name

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Tasdiqlash", callback_data="confirm"))
    kb.add(types.InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit"))

    await msg.answer_photo(
        data["photo"],
        caption=f"👤 {username}\n🏷 Jamoa: {data['team']}",
        reply_markup=kb
    )
    await Form.confirm.set()

@dp.callback_query_handler(text="edit", state=Form.confirm)
async def edit(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("🏷 Jamoa nomini qayta kiriting:")
    await Form.team.set()
    await cb.answer()

@dp.callback_query_handler(text="confirm", state=Form.confirm)
async def confirm(cb: types.CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    if already_sent(uid):
        await cb.message.answer("❌ Siz allaqachon yuborgansiz.")
        await state.finish()
        return

    data = await state.get_data()
    username = f"@{cb.from_user.username}" if cb.from_user.username else cb.from_user.full_name

    cur.execute(
        "INSERT INTO submissions VALUES (?,?,?,?)",
        (uid, username, data["team"], data["photo"])
    )
    conn.commit()

    n = cfg.get("submission_counter", 1)
    cfg["submission_counter"] = n + 1
    save_config()

    caption = (
        f"🏆 {n}_Ishtirokchimiz {username}\n"
        f"📌 Jamoa nomi : {data['team']}\n\n"
        "✅ BIZDAN UZOQLASHMANG ♻️\n"
        "👇👇👇\n"
        "https://t.me/dream_league_Uzb"
    )

    await bot.send_photo(ADMIN_ID, data["photo"], caption=caption)
    await bot.send_photo(uid, data["photo"], caption=caption)

    await cb.message.answer("✅ Ma’lumotlar yuborildi!")
    await state.finish()
    await cb.answer()

# ================= ADMIN BUTTONS =================
@dp.message_handler(text="📋 Ishtirokchilar ro‘yxati")
async def admin_list(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return

    cur.execute("SELECT username, team FROM submissions")
    rows = cur.fetchall()

    if not rows:
        await msg.answer("📭 Hozircha ishtirokchilar yo‘q")
        return

    text = f"👥 Jami: {len(rows)} ta\n\n"
    for i, (u, t) in enumerate(rows, 1):
        text += f"{i}. {u} — {t}\n"

    await msg.answer(text)

@dp.message_handler(text="🔢 Sozlash (raqam kiritish)")
async def admin_counter(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    await msg.answer("🔢 Boshlang‘ich raqamni kiriting:")
    await AdminState.counter.set()

@dp.message_handler(state=AdminState.counter)
async def save_counter(msg: types.Message, state: FSMContext):
    if not msg.text.isdigit():
        await msg.answer("❌ Faqat raqam kiriting")
        return
    cfg["submission_counter"] = int(msg.text)
    save_config()
    await msg.answer("✅ Saqlandi")
    await state.finish()

@dp.message_handler(text="📢 Reklamalarni boshqarish")
async def admin_ads(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return

    ads = cfg.get("promo_channels", [])
    text = "📢 Reklama kanallari:\n\n"
    for a in ads:
        text += f"- {a}\n"
    text += "\nYangi kanal linkini yuboring:"

    await msg.answer(text)
    await AdminState.promo.set()

@dp.message_handler(state=AdminState.promo)
async def add_ad(msg: types.Message, state: FSMContext):
    cfg.setdefault("promo_channels", []).append(msg.text.strip())
    save_config()
    await msg.answer("✅ Kanal qo‘shildi")
    await state.finish()

@dp.message_handler(text="⏳ Konkursni boshqarish")
async def contest_ctrl(msg: types.Message):
    if not is_admin(msg.from_user.id):
        return
    status = "🟢 Ochiq" if cfg.get("contest_open", True) else "🔴 Yopiq"
    await msg.answer(f"Konkurs holati: {status}")

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
