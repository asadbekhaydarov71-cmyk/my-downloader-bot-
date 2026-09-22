import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
import yt_dlp
from aiohttp import web

# =========================
# BOT SOZLAMALARI
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN topilmadi!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================
# RENDER WEB SERVER
# =========================

async def handle(request):
    return web.Response(text="Bot is running!")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.getenv("PORT", 8080))

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        port
    )

    await site.start()

    print(f"Web server {port}-portda ishga tushdi")


# =========================
# VIDEO YUKLASH
# =========================

def download_media(url: str, output_path: str):

    ydl_opts = {

        # Eng yaxshi MP4 video + M4A audio
        "format":
            "bv*[ext=mp4]+ba[ext=m4a]/"
            "b[ext=mp4]/"
            "b",

        # Fayl nomi
        "outtmpl": output_path,

        # Video va audioni MP4 qilib birlashtirish
        "merge_output_format": "mp4",

        # FFmpeg
        "postprocessors": [
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            }
        ],

        # YouTube JS challenge uchun Deno
        "js_runtimes": {
            "deno": {}
        },

        # EJS komponentlarini ishlatishga ruxsat
        "remote_components": [
            "ejs:npm"
        ],

        # SSL
        "nocheckcertificate": True,

        # Geo bypass
        "geo_bypass": True,

        # User-Agent
        "http_headers": {
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36",

            "Accept-Language":
                "en-US,en;q=0.9",
        },

        # Loglarni ko‘rsatish
        "quiet": False,
        "no_warnings": False,

        # Playlist emas, bitta video
        "noplaylist": True,

        # Retry
        "retries": 5,

        # Fragment retry
        "fragment_retries": 5,

        # Socket timeout
        "socket_timeout": 30,
    }

    print(f"Yuklanmoqda: {url}")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

        if info:
            print(
                f"Yuklandi: "
                f"{info.get('title', 'Nomaʼlum')}"
            )

    return output_path


# =========================
# /START
# =========================

@dp.message(CommandStart())
async def start_cmd(message: types.Message):

    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "Menga Instagram, YouTube yoki TikTok "
        "video havolasini yuboring.\n\n"
        "📥 Men videoni yuklab Telegramga yuboraman."
    )


# =========================
# LINK QABUL QILISH
# =========================

@dp.message(F.text.startswith("http"))
async def handle_link(message: types.Message):

    url = message.text.strip()

    status_msg = await message.answer(
        "⏳ Video aniqlanmoqda..."
    )

    # Har bir foydalanuvchi uchun alohida fayl
    file_path = f"/tmp/video_{message.from_user.id}.mp4"

    try:

        await status_msg.edit_text(
            "⏳ Video yuklanmoqda..."
        )

        # Blocking yt-dlp ni alohida thread'da ishlatamiz
        loop = asyncio.get_running_loop()

        await loop.run_in_executor(
            None,
            download_media,
            url,
            file_path
        )

        # Fayl borligini tekshirish
        if not os.path.exists(file_path):

            raise FileNotFoundError(
                "Yuklangan video fayli topilmadi."
            )

        file_size = os.path.getsize(file_path)

        print(
            f"Fayl hajmi: "
            f"{file_size / 1024 / 1024:.2f} MB"
        )

        await status_msg.edit_text(
            "📤 Video Telegramga yuborilmoqda..."
        )

        video_file = types.FSInputFile(
            file_path
        )

        await message.answer_video(
            video=video_file,
            caption="✅ Videongiz tayyor!"
        )

        await status_msg.delete()

    except Exception as e:
    error_text = repr(e)

    print("=" * 70)
    print("YT-DLP XATOSI:")
    print(error_text)
    print("=" * 70)

    try:
        await status_msg.edit_text(
            f"❌ Xatolik:\n\n{error_text[:3500]}"
        )
    except Exception:
        pass

    finally:

        # Vaqtinchalik faylni o‘chirish
        if os.path.exists(file_path):

            try:
                os.remove(file_path)
            except Exception:
                pass


# =========================
# BOTNI ISHGA TUSHIRISH
# =========================

async def main():

    print("=" * 50)
    print("BOT ISHGA TUSHMOQDA...")
    print("=" * 50)

    await start_web_server()

    print("Telegram polling boshlandi...")

    await dp.start_polling(bot)


# =========================
# START
# =========================

if __name__ == "__main__":
    asyncio.run(main())
