import asyncio
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

import yt_dlp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import FSInputFile, Message

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["BOT_TOKEN"]            # tokenni faqat hosting sozlamasida saqlang
PORT = int(os.environ.get("PORT", "8080"))  # tekin hostinglar uchun health-check porti
COOKIES = os.environ.get("COOKIES_FILE")    # ixtiyoriy: Instagram cookies.txt yo'li
MAX_BYTES = 49 * 1024 * 1024                # Telegram bot limiti ~50 MB
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}
URL_RE = re.compile(
    r"https?://(?:[\w-]+\.)?(?:instagram\.com|tiktok\.com)/\S+", re.IGNORECASE
)

bot = Bot(TOKEN)
dp = Dispatcher()
sem = asyncio.Semaphore(2)  # bir vaqtda 2 tadan ortiq yuklash bo'lmasin


def download(url: str, folder: str) -> list[Path]:
    opts = {
        "outtmpl": str(Path(folder) / "%(id)s_%(autonumber)s.%(ext)s"),
        "format": "best[ext=mp4][filesize<49M]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": False,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
    }
    if COOKIES and os.path.exists(COOKIES):
        opts["cookiefile"] = COOKIES
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = [p for p in sorted(Path(folder).iterdir()) if p.suffix.lower() in VIDEO_EXT]
    return files


@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "Salom! 👋\nInstagram yoki TikTok video havolasini yuboring, men yuklab beraman 🎬"
    )


@dp.message(F.text.regexp(URL_RE))
async def handle_link(m: Message):
    url = URL_RE.search(m.text).group(0)
    status = await m.answer("⏳ Yuklanmoqda...")
    folder = tempfile.mkdtemp(prefix="dl_")
    try:
        async with sem:
            files = await asyncio.to_thread(download, url, folder)
        if not files:
            await m.answer("❌ Video topilmadi. Havola ochiq (public) ekanini tekshiring.")
            return
        for f in files[:5]:
            if f.stat().st_size > MAX_BYTES:
                await m.answer("⚠️ Video 50 MB dan katta, Telegram orqali yuborib bo'lmaydi.")
                continue
            await m.answer_video(FSInputFile(f), supports_streaming=True)
    except Exception:
        logging.exception("Yuklashda xato: %s", url)
        await m.answer(
            "❌ Yuklab bo'lmadi. Havola ochiq ekanini tekshiring yoki keyinroq urinib ko'ring."
        )
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        try:
            await status.delete()
        except Exception:
            pass


@dp.message(F.text)
async def other(m: Message):
    await m.answer("Iltimos, Instagram yoki TikTok havolasini yuboring.")


async def start_web():
    """Tekin hostinglar port talab qilgani uchun kichik health-check server."""
    app = web.Application()
    app.router.add_get("/", lambda request: web.Response(text="ok"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()


async def main():
    await start_web()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
