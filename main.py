import asyncio
import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

import yt_dlp
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["BOT_TOKEN"]
PORT = int(os.environ.get("PORT", "8080"))
COOKIES = os.environ.get("COOKIES_FILE")
# Faqat o'zingiz uchun: Telegram ID(lar)ni vergul bilan yozing. Bo'sh bo'lsa hamma foydalana oladi.
ALLOWED = {
    int(x) for x in os.environ.get("ALLOWED_USERS", "").replace(" ", "").split(",") if x
}
MAX_BYTES = 49 * 1024 * 1024
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv"}
URL_RE = re.compile(
    r"https?://(?:[\w-]+\.)?(?:instagram\.com|tiktok\.com|youtube\.com|youtu\.be)/\S+",
    re.IGNORECASE,
)

bot = Bot(TOKEN)
dp = Dispatcher()
sem = asyncio.Semaphore(2)
PENDING: dict[str, str] = {}  # qisqa kalit -> havola


def allowed(user_id: int) -> bool:
    return not ALLOWED or user_id in ALLOWED


def base_opts(folder: str) -> dict:
    opts = {
        "outtmpl": str(Path(folder) / "%(id)s_%(autonumber)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
    }
    if COOKIES and os.path.exists(COOKIES):
        opts["cookiefile"] = COOKIES
    return opts


def dl_video(url: str, folder: str, height: int) -> list[Path]:
    opts = base_opts(folder)
    opts["format"] = (
        f"bv*[height<={height}][ext=mp4]+ba[ext=m4a]/"
        f"b[height<={height}][ext=mp4]/b[height<={height}]/b"
    )
    opts["merge_output_format"] = "mp4"
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return [p for p in sorted(Path(folder).iterdir()) if p.suffix.lower() in VIDEO_EXT]


def dl_audio(target: str, folder: str) -> list[Path]:
    """target: havola yoki 'ytsearch1:qidiruv matni'."""
    opts = base_opts(folder)
    opts["format"] = "bestaudio/best"
    opts["noplaylist"] = True
    opts["postprocessors"] = [
        {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
    ]
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([target])
    return [p for p in sorted(Path(folder).iterdir()) if p.suffix.lower() == ".mp3"]


async def recognize(path: Path):
    from shazamio import Shazam  # kech import: muammo bo'lsa ham bot ishga tushadi

    shazam = Shazam()
    fn = getattr(shazam, "recognize", None) or shazam.recognize_song
    out = await fn(str(path))
    track = (out or {}).get("track")
    if not track:
        return None
    return track.get("title"), track.get("subtitle")


def keyboard(key: str) -> InlineKeyboardMarkup:
    def b(text, choice):
        return InlineKeyboardButton(text=text, callback_data=f"q:{key}:{choice}")

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [b("360p", "360"), b("480p", "480"), b("720p", "720")],
            [b("🎵 MP3", "mp3"), b("🔎 Musiqani topish", "shz")],
        ]
    )


@dp.message(CommandStart())
async def start(m: Message):
    await m.answer(
        "Salom! 👋\nInstagram, TikTok yoki YouTube havolasini yuboring, keyin sifat yoki MP3 ni tanlang."
    )


@dp.message(Command("id"))
async def my_id(m: Message):
    await m.answer(f"Sizning Telegram ID: {m.from_user.id}")


@dp.message(F.text.regexp(URL_RE))
async def handle_link(m: Message):
    if not allowed(m.from_user.id):
        await m.answer("Bu bot shaxsiy foydalanish uchun.")
        return
    url = URL_RE.search(m.text).group(0)
    key = uuid.uuid4().hex[:8]
    if len(PENDING) > 200:
        PENDING.pop(next(iter(PENDING)))
    PENDING[key] = url
    await m.answer("Nimani yuklaymiz?", reply_markup=keyboard(key))


@dp.callback_query(F.data.startswith("q:"))
async def on_choice(cb: CallbackQuery):
    if not allowed(cb.from_user.id):
        await cb.answer()
        return
    _, key, choice = cb.data.split(":")
    url = PENDING.get(key)
    if not url:
        await cb.answer("Havola eskirgan, qayta yuboring.", show_alert=True)
        return
    await cb.answer()
    msg = cb.message
    await msg.edit_text("⏳ Yuklanmoqda...")
    folder = tempfile.mkdtemp(prefix="dl_")
    try:
        async with sem:
            if choice in ("360", "480", "720"):
                files = await asyncio.to_thread(dl_video, url, folder, int(choice))
                await send_files(msg, files, kind="video")
            elif choice == "mp3":
                files = await asyncio.to_thread(dl_audio, url, folder)
                await send_files(msg, files, kind="audio")
            elif choice == "shz":
                await shazam_flow(msg, url, folder)
    except Exception:
        logging.exception("Xato: %s", url)
        await msg.answer("❌ Bajarib bo'lmadi. Havola ochiq ekanini tekshiring yoki keyinroq urinib ko'ring.")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        try:
            await msg.delete()
        except Exception:
            pass


async def send_files(msg: Message, files: list[Path], kind: str):
    if not files:
        await msg.answer("❌ Fayl topilmadi.")
        return
    for f in files[:5]:
        if f.stat().st_size > MAX_BYTES:
            await msg.answer("⚠️ Fayl 50 MB dan katta. Pastroq sifatni tanlang.")
            continue
        if kind == "video":
            await msg.answer_video(FSInputFile(f), supports_streaming=True)
        else:
            await msg.answer_audio(FSInputFile(f))


async def shazam_flow(msg: Message, url: str, folder: str):
    files = await asyncio.to_thread(dl_audio, url, folder)
    if not files:
        await msg.answer("❌ Audio ajratib bo'lmadi.")
        return
    try:
        result = await recognize(files[0])
    except Exception as e:
        logging.exception("Shazam xatosi")
        await msg.answer(
            f"❌ Shazam xizmati hozir ishlamayapti.\n\n{type(e).__name__}: {str(e)[:300]}"
        )
        return
    if not result:
        await msg.answer("🤷 Qo'shiq aniqlanmadi.")
        return
    title, artist = result
    await msg.answer(f"🎶 {artist} — {title}\nMP3 qidirilmoqda...")
    song_folder = tempfile.mkdtemp(prefix="song_")
    try:
        songs = await asyncio.to_thread(
            dl_audio, f"ytsearch1:{artist} - {title}", song_folder
        )
        if not songs:
            await msg.answer("MP3 topilmadi.")
            return
        f = songs[0]
        if f.stat().st_size > MAX_BYTES:
            await msg.answer("⚠️ MP3 50 MB dan katta.")
            return
        await msg.answer_audio(FSInputFile(f), title=title, performer=artist)
    finally:
        shutil.rmtree(song_folder, ignore_errors=True)


@dp.message(F.text)
async def other(m: Message):
    await m.answer("Iltimos, Instagram, TikTok yoki YouTube havolasini yuboring.")


async def start_web():
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
