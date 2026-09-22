import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
import yt_dlp
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Render Web Service uchun veb-server
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

def download_media(url: str, output_path: str):
    ydl_opts = {
        # TikTok va Instagram uchun eng yaxshi format, YouTube uchun m8a/mp4
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        # Server IP blokirovkasidan o'tish uchun maxsus sozlamalar
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'web_embedded', 'mweb'],
                'skip': ['hls', 'dash']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1'
        }
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return output_path

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "Assalomu alaykum! Menga **Instagram**, **YouTube** yoki **TikTok** video linkini yuboring.",
        parse_mode="Markdown"
    )

@dp.message(F.text.startswith("http"))
async def handle_link(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("⏳ Video yuklanmoqda...")
    file_path = f"video_{message.from_user.id}.mp4"
    
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, download_media, url, file_path)
        await status_msg.edit_text("📤 Telegram'ga yuborilmoqda...")
        
        video_file = types.FSInputFile(file_path)
        await message.answer_video(video=video_file, caption="✅ Videongiz tayyor!")
        await status_msg.delete()
    except Exception as e:
        error_text = str(e)
        if "confirm you're not a bot" in error_text or "403" in error_text:
            await status_msg.edit_text("❌ YouTube ushbu server IP-manzilini bloklagan. Shorts yoki boshqa qisqa videolarni sinab ko'ring.")
        else:
            await status_msg.edit_text(f"❌ Xatolik yuz berdi: Videoni yuklab bo'lmadi.")
        print(f"Xato batafsil: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def main():
    print("Bot va Web Server ishga tushdi...")
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
