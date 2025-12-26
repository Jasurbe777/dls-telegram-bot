import logging, os, json, sqlite3, re
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# ================= CONFIG =================
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT TOKEN topilmadi")

with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

ADMIN_ID = int(cfg["admin_id"])
cfg.setdefault("contest_end", None)
cfg.setdefault("submission_counter", 1)

def save_cfg():
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

bot = Bot(BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# ================= DATABASE =================
db = sqlite3.connect("database.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS submissions(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    username TEXT,
    team TEXT,
    photo TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS ads(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT UNIQUE
)
""")
db.commit()

# ================= HELPERS =================
def is_admin(uid):
    return uid == ADMIN_ID

def uname(user):
    return f"@{user.username}" if user.username else user.full_name

def has_submitted(uid):
    cur.execute("SELECT 1 FROM submissions WHERE user_id=?", (uid,))
    return cur.fetchone() is not None

def contest_active():
    if not cfg["contest_end"]:
        return False
    return datetime.utcnow() < datetime.fromisoformat(cfg["contest_end"])

def has_ads():
    cur.execute("SELECT COUNT(*) FROM ads")
    return cur.fetchone()[0] > 0

async def check_subs(user_id):
    cur.execute("SELECT channel FROM ads")
    rows = cur.fetchall()
    not_sub = []

    for (ch,) in rows:
        ch = ch.replace("https://t.me/", "").replace("@", "")
        try:
            member = await bot.get_chat_member(f"@{ch}", user_id)
            if member.status not in ("member", "administrator", "creator"):
                not_sub.append(f"@{ch}")
        except:
            not_sub.append(f"@{ch}")
    return not_sub

def admin_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📋 Ishtirokchilar ro‘yxati")
    kb.add("⏳ Konkursni boshqarish")
    kb.add("🔢 Sozlash (raqam kiritish)")
    kb.add("📢 Reklamalarni boshqarish")
    return kb

# ================= STATES =================
class UserForm(StatesGroup):
    photo = State()
    team = State()
    confirm = State()

class AdminForm(StatesGroup):
    contest_time = State()
    edit_counter = State()
    add_ad = State()

# ================= START =================
@dp.message_handler(commands="start", state="*")
async def start(msg: types.Message, state: FSMContext):
    await state.finish()

    if is_admin(msg.from_user.id):
        await msg.answer("👑 Admin panel", reply_markup=admin_kb())
        return

    if not contest_active():
        await msg.answer(
            "Salom, bu DLS ISMOILOV konkursida qatnashish uchun yaratilgan bot ✅\n\n"
            "⛔ Hozircha konkurs yopiq."
        )
        return

    if has_submitted(msg.from_user.id):
        await msg.answer(
            "Salom, bu DLS ISMOILOV konkursida qatnashish uchun yaratilgan bot ✅\n\n"
            "❌ Siz allaqachon qatnashgansiz."
        )
        return

    kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("Boshlash", callback_data="start_user")
    )
    await msg.answer(
        "Salom, bu DLS ISMOILOV konkursida qatnashish uchun yaratilgan bot ✅\n\n"
        "Botdagi shartlarga rioya qiling va konkursda bemalol qatnashavering ❗️",
        reply_markup=kb
    )

# ================= USER FLOW =================
@dp.callback_query_handler(lambda c: c.data == "start_user")
async def start_user(cb: types.CallbackQuery):
    if has_ads():
        not_sub = await check_subs(cb.from_user.id)

        if not_sub:
            kb = types.InlineKeyboardMarkup(row_width=1)

            for ch in not_sub:
                kb.add(
                    types.InlineKeyboardButton(
                        "Obuna bo‘lish",
                        url=f"https://t.me/{ch.replace('@','')}"
                    )
                )

            kb.add(
                types.InlineKeyboardButton(
                    "Men obuna bo‘ldim (tekshirilsin)",
                    callback_data="check_subs"
                )
            )

            await cb.message.answer(
                "Iltimos, quyidagi kanallarga obuna bo‘ling va so‘ng tekshirish tugmasini bosing:",
                reply_markup=kb
            )
            await cb.answer()
            return

    await cb.message.answer("📸 Dream League profilingiz rasmini yuboring:")
    await UserForm.photo.set()
    await cb.answer()

@dp.callback_query_handler(lambda c: c.data == "check_subs")
async def recheck_subs(cb: types.CallbackQuery):
    not_sub = await check_subs(cb.from_user.id)

    if not_sub:
        text = "❌ Siz hali quyidagi kanal(lar)ga obuna bo‘lmadingiz:\n\n"
        text += "\n".join(not_sub)

        kb = types.InlineKeyboardMarkup(row_width=1)
        for ch in not_sub:
            kb.add(
                types.InlineKeyboardButton(
                    "Obuna bo‘lish",
                    url=f"https://t.me/{ch.replace('@','')}"
                )
            )

        kb.add(
            types.InlineKeyboardButton(
                "Men obuna bo‘ldim (tekshirilsin)",
                callback_data="check_subs"
            )
        )

        await cb.message.answer(text, reply_markup=kb)
        await cb.answer()
        return

    await cb.message.answer("📸 Dream League profilingiz rasmini yuboring:")
    await UserForm.photo.set()
    await cb.answer()

# ================= USER FORM =================
@dp.message_handler(content_types=types.ContentType.PHOTO, state=UserForm.photo)
async def get_photo(msg: types.Message, state: FSMContext):
    await state.update_data(photo=msg.photo[-1].file_id)
    await msg.answer("🏷 Jamoa nomini kiriting:")
    await UserForm.team.set()

@dp.message_handler(state=UserForm.team)
async def get_team(msg: types.Message, state: FSMContext):
    await state.update_data(team=msg.text)
    data = await state.get_data()

    cap = (
        f"👤 {uname(msg.from_user)}\n"
        f"🏷 Jamoa nomi : {data['team']}\n\n"
        f"Tasdiqlaysizmi?"
    )

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ Tasdiqlash", callback_data="confirm"),
        types.InlineKeyboardButton("✏️ Tahrirlash", callback_data="edit")
    )

    await msg.answer_photo(data["photo"], caption=cap, reply_markup=kb)
    await UserForm.confirm.set()

@dp.callback_query_handler(lambda c: c.data == "edit", state=UserForm.confirm)
async def edit(cb: types.CallbackQuery):
    await cb.message.answer("✏️ Yangi jamoa nomini kiriting:")
    await UserForm.team.set()

@dp.callback_query_handler(lambda c: c.data == "confirm", state=UserForm.confirm)
async def confirm(cb: types.CallbackQuery, state: FSMContext):
    user = cb.from_user
    if has_submitted(user.id):
        await cb.message.answer("❌ Qayta yuborish mumkin emas")
        await state.finish()
        return

    data = await state.get_data()
    cur.execute(
        "INSERT INTO submissions(user_id,username,team,photo) VALUES(?,?,?,?)",
        (user.id, uname(user), data["team"], data["photo"])
    )
    db.commit()

    num = cfg["submission_counter"]
    cfg["submission_counter"] += 1
    save_cfg()

    caption = (
        f"🏆 {num}_Ishtirokchimiz {uname(user)}\n"
        f"📌 Jamoa nomi : {data['team']}\n\n"
        f"✅ BIZDAN UZOQLASHMANG ♻️\n"
        f"👇👇👇\n"
        f"https://t.me/dream_league_Uzb"
    )

    await bot.send_photo(ADMIN_ID, data["photo"], caption=caption)
    await bot.send_photo(user.id, data["photo"], caption=caption)

    await cb.message.answer("✅ Qabul qilindi")
    await state.finish()

# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
