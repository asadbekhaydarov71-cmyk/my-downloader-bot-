import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
import yt_dlp

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def download_media(url: str, output_path: str):
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return output_path

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer("Assalomu alaykum! Menga YouTube yoki Instagram video linkini yuboring.")

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
        await status_msg.edit_text("❌ Xatolik: Videoni yuklab bo'lmadi.")
        print(f"Xato: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def main():
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
