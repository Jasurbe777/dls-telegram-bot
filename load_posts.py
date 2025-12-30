from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
import sqlite3

# ================== SOZLAMALAR ==================
API_ID = 32007886              # <-- seniki
API_HASH = "d0fc26bb2222d069b72d4f875661ac1c"   # <-- seniki
CHANNEL = "dream_league_Uzb"     # @ belgisisiz
DB_NAME = "submissions.db"

# ================== DB ULANISH ==================
conn = sqlite3.connect(DB_NAME)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS channel_posts (
    post_id INTEGER PRIMARY KEY,
    post_link TEXT
)
""")
conn.commit()

# ================== TELETHON ==================
client = TelegramClient("session_loader", API_ID, API_HASH)

async def main():
    await client.start()
    print("✅ Telegramga ulandi")

    channel = await client.get_entity(CHANNEL)

    offset_id = 0
    limit = 100
    total_loaded = 0

    while True:
        history = await client(GetHistoryRequest(
            peer=channel,
            offset_id=offset_id,
            offset_date=None,
            add_offset=0,
            limit=limit,
            max_id=0,
            min_id=0,
            hash=0
        ))

        if not history.messages:
            break

        for msg in history.messages:
            if not msg.id:
                continue

            post_id = msg.id
            post_link = f"https://t.me/{CHANNEL}/{post_id}"

            cur.execute(
                "INSERT OR IGNORE INTO channel_posts (post_id, post_link) VALUES (?, ?)",
                (post_id, post_link)
            )
            total_loaded += 1
            offset_id = msg.id

        conn.commit()
        print(f"📥 Yuklandi: {total_loaded} ta post")

        if len(history.messages) < limit:
            break

    print(f"\n🎉 YAKUNLANDI! Jami yuklangan postlar: {total_loaded}")
    await client.disconnect()

with client:
    client.loop.run_until_complete(main())
