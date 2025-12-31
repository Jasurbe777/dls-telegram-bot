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

YOUTUBE_LINK = cfg.get("youtube_link")
INSTAGRAM_LINK = cfg.get("instagram_link")

logging.basicConfig(level=logging.INFO)

if not BOT_TOKEN:
    raise RuntimeError("BOT TOKEN topilmadi!")


# ================== BOT ==================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())


# ================== DATABASE ==================
conn = sqlite3.connect("submissions.db")
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
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
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def save_config():
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ================== START ==================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    text = (
        f"👋 Salom!\n\n"
        f"👤 Egasi: {cfg.get('owner_name')}\n"
        f"ℹ️ {cfg.get('owner_about')}\n\n"
        f"Boshlash uchun tugmani bosing 👇"
    )

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Boshlash", callback_data="start_flow")) # type: ignore

    await message.answer(text, reply_markup=kb)

    if is_admin(message.from_user.id):
        admin_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        admin_kb.add("🏆 TOP-100 postlar")
        admin_kb.add("Reklamalarni sozlash")
        admin_kb.add("Sozlash (raqam kiritish)")
    await message.answer("🔧 Admin panel", reply_markup=admin_kb)


# ================== START FLOW ==================
@dp.callback_query_handler(lambda c: c.data == "start_flow")
async def start_flow(cb: types.CallbackQuery):
    promo_channels = cfg.get("promo_channels", [])

    if not promo_channels:
        await cb.message.answer(
            "📸 Dream League akkauntingiz skrinshotini yuboring:"
        )
        await Form.waiting_screenshot.set()
        await cb.answer()
        return

    kb = InlineKeyboardMarkup(row_width=1)

    for ch in promo_channels:
        url = ch if ch.startswith("http") else f"https://t.me/{ch.lstrip('@')}"
        kb.add(InlineKeyboardButton("Obuna bo‘lish", url=url)) # type: ignore

    kb.add(
        InlineKeyboardButton(
            "Men obuna bo‘ldim (tekshirilsin)",
            callback_data="check_subs"
        ) # type: ignore
    )

    await cb.message.answer(
        "Iltimos, quyidagi kanallarga a’zo bo‘ling va so‘ng tekshirish tugmasini bosing:",
        reply_markup=kb
    )
    await cb.answer()

@dp.message_handler(
    lambda m: is_admin(m.from_user.id)
    and m.text
    and m.text.strip().lower() == "sozlash (raqam kiritish)"
)
async def admin_set_counter(message: types.Message):
    await message.answer(
        "🔢 Ishtirokchilar tartib raqamini kiriting.\n\n"
        "Masalan:\n"
        "1  → 1 dan boshlanadi\n"
        "10 → 10 dan boshlanadi"
    )
    await AdminForm.waiting_counter.set()

@dp.message_handler(state=AdminForm.waiting_counter)
async def process_counter_input(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.finish()
        return

    text = message.text.strip()

    if not text.isdigit() or int(text) < 1:
        await message.answer(
            "❌ Noto‘g‘ri raqam.\n"
            "Iltimos, 1 yoki undan katta butun son kiriting."
        )
        return

    new_counter = int(text)
    cfg["submission_counter"] = new_counter
    save_config()

    await message.answer(
        f"✅ Tayyor!\n"
        f"Keyingi ishtirokchi raqami {new_counter} dan boshlanadi."
    )

    await state.finish()


# ================== CHECK SUBS ==================
@dp.callback_query_handler(lambda c: c.data == "check_subs")
async def check_subs(cb: types.CallbackQuery):
    promo_channels = cfg.get("promo_channels", [])

    # Agar admin reklama qo‘shmagan bo‘lsa — o‘tkazib yuboriladi
    if not promo_channels:
        await cb.message.answer(
            "📸 Dream League profilingiz rasmini yuboring:"
        )
        await Form.waiting_screenshot.set()
        await cb.answer()
        return

    for ch in promo_channels:
        chat_id = ch if ch.startswith("-100") else "@" + ch.lstrip("@").replace("https://t.me/", "")
        try:
            member = await bot.get_chat_member(chat_id, cb.from_user.id)
            if member.status in ("left", "kicked"):
                await cb.message.answer(
                    f"❌ Siz {ch} kanaliga obuna bo‘lmagansiz."
                )
                await cb.answer()
                return
        except Exception:
            await cb.message.answer(
                f"⚠️ Kanalni tekshirib bo‘lmadi: {ch}"
            )
            await cb.answer()
            return

    await cb.message.answer(
        "✅ Hammasi joyida.\n📸 Dream Leagua profilingiz rasmini yuboring:"
    )
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
        await message.answer("❌ Jamoa nomi noto‘g‘ri. Qayta kiriting:")
        return

    await state.update_data(team=team)

    data = await state.get_data()
    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    await state.update_data(username=username)

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("Tasdiqlash", callback_data="confirm")) # type: ignore
    kb.add(InlineKeyboardButton("Tahrirlash", callback_data="edit")) # type: ignore

    caption = (
        f"👤 {username}\n"
        f"🏷 Jamoa: {team}\n\n"
        f"Maʼlumotlar to‘g‘rimi?"
    )

    await message.answer_photo(
        photo=data["photo_file_id"],
        caption=caption,
        reply_markup=kb
    )

    await Form.waiting_confirm.set()


# ================== CONFIRM ==================
@dp.callback_query_handler(lambda c: c.data == "edit", state=Form.waiting_confirm)
async def edit(cb: types.CallbackQuery, state: FSMContext):
    await cb.message.answer("🏷 Jamoa nomini qayta kiriting:")
    await Form.waiting_team.set()
    await cb.answer()


@dp.callback_query_handler(lambda c: c.data == "confirm", state=Form.waiting_confirm)
async def confirm(cb: types.CallbackQuery, state: FSMContext):
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

    admin_caption = (
    f"🏆 {counter}_Ishtirokchimiz {data['username']}\n"
    f"📌 Jamoa nomi : {data['team']}\n\n"
    f"✅ BIZDAN UZOQLASHMANG ♻️\n"
    f"👇👇👇\n"
    f"https://t.me/dream_league_Uzb"
    )

    # Adminga yuborish
    await bot.send_photo(
        ADMIN_ID,
        data["photo_file_id"],
        caption=admin_caption
    )

    # Foydalanuvchining o‘ziga ham yuborish
    await bot.send_photo(
        cb.from_user.id,
        data["photo_file_id"],
        caption=admin_caption
    )

    await cb.message.answer(
        "✅ Maʼlumotlaringiz qabul qilindi va adminga yuborildi. Omad! 🍀"
    )

    await state.finish()
    await cb.answer()



# ================== ADMIN ==================
@dp.message_handler(lambda m: is_admin(m.from_user.id) and m.text == "Reklamalarni sozlash")
async def admin_promos(message: types.Message):
    kb = InlineKeyboardMarkup()
    for i, ch in enumerate(cfg.get("promo_channels", [])):
        kb.add(InlineKeyboardButton(f"❌ {ch}", callback_data=f"delpromo:{i}")) # type: ignore
    kb.add(InlineKeyboardButton("➕ Kanal qo‘shish", callback_data="addpromo")) # type: ignore
    await message.answer("📢 Reklama kanallari:", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "addpromo")
async def addpromo(cb: types.CallbackQuery):
    await cb.message.answer("➕ Kanal username yoki linkini kiriting:")
    await AdminForm.waiting_promo.set()
    await cb.answer()


@dp.message_handler(state=AdminForm.waiting_promo)
async def savepromo(message: types.Message, state: FSMContext):
    cfg.setdefault("promo_channels", []).append(message.text.strip())
    save_config()
    await message.answer("✅ Kanal qo‘shildi")
    await state.finish()


@dp.callback_query_handler(lambda c: c.data.startswith("delpromo:"))
async def delpromo(cb: types.CallbackQuery):
    idx = int(cb.data.split(":")[1])
    cfg["promo_channels"].pop(idx)
    save_config()
    await cb.message.answer("🗑 Kanal o‘chirildi")
    await cb.answer()

@dp.message_handler(lambda m: m.text)
async def debug_all_text(message: types.Message):
    print("TEXT KELDI >>>", repr(message.text))

# ================== RUN ==================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)

@dp.message_handler(lambda m: m.text and "TOP-100" in m.text)
async def top_100(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("⏳ TOP-100 hisoblanmoqda...")

    cur.execute("""
        SELECT post_link, total_reactions, reactions_text
        FROM channel_posts
        WHERE total_reactions > 0
        ORDER BY total_reactions DESC
        LIMIT 100
    """)
    rows = cur.fetchall()

    if not rows:
        await message.answer("❌ Ma’lumot yo‘q. Avval reaksiyalarni yangilang.")
        return

    text = "🏆 TOP-100 ENG KO‘P REAKSIYA OLGAN POSTLAR\n\n"

    for i, (link, total, details) in enumerate(rows, start=1):
        block = (
            f"{i}. 📊 Jami: {total}\n"
            f"{details}\n"
            f"🔗 {link}\n\n"
        )

        if len(text) + len(block) > 3800:
            await message.answer(text, disable_web_page_preview=True)
            text = ""

        text += block

    if text:
        await message.answer(text, disable_web_page_preview=True)

