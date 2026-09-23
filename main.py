import os
import logging
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
import yt_dlp
from shazamio import Shazam

# Logging
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE").strip()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
shazam = Shazam()

# Vaqtincha yuklangan videolarni saqlash uchun lug'at (media_id -> file_path)
media_store = {}

# Render uchun soxta HTTP server
async def handle_ping(request):
    return web.Response(text="Bot is active!")

async def start_dummy_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# /start buyrug'i
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 **Xush kelibsiz!**\n\n"
        "Instagram va TikTok video havolasini yuboring. Men videoni yuklab beraman "
        "va uning musiqasini Shazam orqali topib berishim mumkin!"
    )

# Video havolasini qabul qilish
@dp.message(F.text)
async def process_video_link(message: types.Message):
    url = message.text.strip()
    
    is_instagram = "instagram.com" in url
    is_tiktok = "tiktok.com" in url or "vt.tiktok.com" in url

    if not (is_instagram or is_tiktok):
        await message.answer("⚠️ Iltimos, faqat **Instagram** yoki **TikTok** havolasini yuboring!")
        return

    status_msg = await message.answer("📥 Video tahlil qilinmoqda...")

    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    file_id = f"{message.from_user.id}_{message.message_id}"
    output_template = f"downloads/{file_id}.%(ext)s"

    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
        }
    }

    try:
        loop = asyncio.get_event_loop()
        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)

        file_path = await loop.run_in_executor(None, download)

        if file_path and os.path.exists(file_path):
            media_store[file_id] = file_path
            
            # Tanlov tugmalari
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="📹 Videoni olish", callback_data=f"video:{file_id}"),
                        InlineKeyboardButton(text="🎵 Audiosini olish", callback_data=f"audio:{file_id}")
                    ],
                    [
                        InlineKeyboardButton(text="🔎 Shazam (To'liq musiqasi)", callback_data=f"shazam:{file_id}")
                    ]
                ]
            )
            await status_msg.edit_text("✅ Video tayyor! Qanday formatda yuklamoqchisiz?", reply_markup=keyboard)
        else:
            await status_msg.edit_text("❌ Videoni yuklab bo'lmadi.")

    except Exception as e:
        logging.error(f"Xatolik: {e}")
        await status_msg.edit_text("❌ Xatolik yuz berdi. Video havolasi yoki profil yopiq bo'lishi mumkin.")

# Tugmalar bosilganda ishlovchi handler
@dp.callback_query(F.data.startswith(("video:", "audio:", "shazam:")))
async def handle_choice(call: types.CallbackQuery):
    action, file_id = call.data.split(":")
    file_path = media_store.get(file_id)

    if not file_path or not os.path.exists(file_path):
        await call.answer("⚠️ Fayl topilmadi yoki muddati o'tgan.", show_alert=True)
        return

    if action == "video":
        await call.message.edit_text("📤 Video yuborilmoqda...")
        await call.message.answer_video(video=FSInputFile(file_path), caption="📹 Videongiz tayyor!")
        await call.message.delete()
        _clean_file(file_id)

    elif action == "audio":
        await call.message.edit_text("🎼 Audio ajratib olinmoqda...")
        audio_path = f"downloads/{file_id}.mp3"
        
        # Videodan mp3 ajratish (FFmpeg)
        proc = await asyncio.create_subprocess_exec(
            'ffmpeg', '-y', '-i', file_path, '-vn', '-acodec', 'libmp3lame', '-q:a', '2', audio_path,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
        await proc.communicate()

        if os.path.exists(audio_path):
            await call.message.answer_audio(audio=FSInputFile(audio_path), caption="🎵 Videodagi audio")
            os.remove(audio_path)
            await call.message.delete()
        else:
            await call.message.answer("❌ Audioni ajratishda xatolik bo'ldi.")
        _clean_file(file_id)

    elif action == "shazam":
        await call.message.edit_text("🔎 Shazam orqali musiqa qidirilmoqda...")
        
        try:
            # Shazam orqali tahlil qilish
            out = await shazam.recognize(file_path)
            track = out.get('track')

            if not track:
                await call.message.edit_text("❌ Afsuski, ushbu videodagi musiqa Shazam bazasidan topilmadi.")
                _clean_file(file_id)
                return

            title = track.get('title')
            subtitle = track.get('subtitle')
            song_name = f"{subtitle} - {title}"

            await call.message.edit_text(f"🎧 Topildi: **{song_name}**\n📥 To'liq MP3 yuklanmoqda...")

            # YouTube'dan to'liq musiqani qidirish va yuklash
            full_audio_path = f"downloads/full_{file_id}.mp3"
            ydl_opts_audio = {
                'format': 'bestaudio/best',
                'outtmpl': full_audio_path.replace('.mp3', ''),
                'default_search': 'ytsearch1',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
            }

            loop = asyncio.get_event_loop()
            def download_full_song():
                with yt_dlp.YoutubeDL(ydl_opts_audio) as ydl:
                    ydl.download([song_name])

            await loop.run_in_executor(None, download_full_song)

            if os.path.exists(full_audio_path):
                await call.message.answer_audio(
                    audio=FSInputFile(full_audio_path),
                    caption=f"🎵 **{song_name}**\n\n🔎 *Shazam orqali topildi*"
                )
                os.remove(full_audio_path)
                await call.message.delete()
            else:
                await call.message.answer(f"🎶 Musiqa nomi: **{song_name}**, lekin MP3 faylini yuklash imkoni bo'lmadi.")

        except Exception as e:
            logging.error(f"Shazam xatosi: {e}")
            await call.message.edit_text("❌ Musiqani aniqlashda xatolik yuz berdi.")
            
        finally:
            _clean_file(file_id)

def _clean_file(file_id):
    file_path = media_store.pop(file_id, None)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception as e:
            logging.error(f"O'chirishda xatolik: {e}")

async def main():
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    await start_dummy_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
