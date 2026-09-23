import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
import aiohttp
from shazamio import Shazam
import yt_dlp

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)

# Token va API kalitlari
BOT_TOKEN = os.getenv("BOT_TOKEN", "8685324789:AAHvmECdQAv8fOmOMA0BmR7bdi07b5ewvUM").strip()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Bot start buyrug'i
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Salom! Men Instagram, TikTok va YouTube videolarini yuklab beruvchi hamda "
        "musiqalarni Shazam qiluvchi botman.\n\n"
        "Manga video/audio havola (link) yuboring yoki o'z audiongizni/ovozli xabaringizni jo'nating!"
    )

# Audio yoki Ovozli xabar kelsa (Shazam funksiyasi)
@dp.message(F.audio | F.voice)
async def handle_audio(message: types.Message):
    msg = await message.answer("🔍 Musiqa qidirilmoqda, kuting...")
    
    file_id = message.audio.file_id if message.audio else message.voice.file_id
    file_info = await bot.get_file(file_id)
    file_path = file_info.file_path
    
    download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    temp_filename = f"temp_{message.from_user.id}.ogg"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                if response.status == 200:
                    with open(temp_filename, 'wb') as f:
                        f.write(await response.read())
                else:
                    await msg.edit_text("❌ Faylni yuklab olishda xatolik yuz berdi.")
                    return

        shazam = Shazam()
        out = await shazam.recognize(temp_filename)
        
        if 'track' in out:
            track = out['track']
            title = track.get('title', 'Noma'lum')
            subtitle = track.get('subtitle', 'Noma'lum')
            
            caption = f"🎵 **Topilgan musiqa:**\n\n📌 **Nomi:** {title}\n👤 **Ijrochi:** {subtitle}"
            
            # YouTube orqali ushbu nomdagi MP3'ni izlab yuklash
            search_query = f"ytsearch1:{title} {subtitle}"
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'shazam_{message.from_user.id}.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
            }
            
            await msg.edit_text("📥 Musiqaning to'liq MP3 varianti yuklanmoqda...")
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([search_query]))
            
            mp3_file = f"shazam_{message.from_user.id}.mp3"
            if os.path.exists(mp3_file):
                await message.answer_audio(
                    audio=types.FSInputFile(mp3_file),
                    caption=caption,
                    parse_mode="Markdown"
                )
                os.remove(mp3_file)
                await msg.delete()
            else:
                await msg.edit_text(f"{caption}\n\n⚠️ MP3 faylini yuklab bo'lmadi.", parse_mode="Markdown")
        else:
            await msg.edit_text("❌ Afsuski, ushbu musiqa topilmadi.")

    except Exception as e:
        logging.error(f"Shazam error: {e}")
        await msg.edit_text("⚠️ Musiqani aniqlashda xatolik yuz berdi.")
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

# Video linklar (Instagram / TikTok / YouTube) va boshqa matnlar kelganda
@dp.message(F.text)
async def handle_text(message: types.Message):
    url = message.text.strip()
    
    if not (url.startswith("http://") or url.startswith("https://")):
        await message.answer("Iltimos, to'g'ri havolani (link) yuboring!")
        return

    msg = await message.answer("📥 Video haqida ma'lumot olinmoqda...")

    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': f'download_{message.from_user.id}.%(ext)s',
        'quiet': True,
    }

    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True))
        
        filename = f"download_{message.from_user.id}.mp4"
        if not os.path.exists(filename):
            # Boshqa kengaytmada yuklangan bo'lishi mumkin
            for f in os.listdir('.'):
                if f.startswith(f"download_{message.from_user.id}"):
                    filename = f
                    break

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎵 Audiosini ajratib olish (MP3)", callback_data=f"audio_{message.from_user.id}")]
        ])

        await msg.edit_text("📤 Telegramga yuklanmoqda...")
        await message.answer_video(
            video=types.FSInputFile(filename),
            caption="✅ Videongiz tayyor!",
            reply_markup=keyboard
        )
        await msg.delete()

    except Exception as e:
        logging.error(f"Download error: {e}")
        await msg.edit_text("❌ Videoni yuklab bo'lmadi. Havola to'g'riligini tekshiring.")

# Audioni ajratish tugmasi bosilganda
@dp.callback_query(F.data.startswith("audio_"))
async def extract_audio_callback(callback: types.CallbackQuery):
    user_id = callback.data.split("_")[1]
    
    if str(callback.from_user.id) != user_id:
        await callback.answer("Bu tugma siz uchun emas!", show_alert=True)
        return

    await callback.answer("🎵 Audio ajratib olinmoqda...")
    
    video_file = None
    for f in os.listdir('.'):
        if f.startswith(f"download_{user_id}"):
            video_file = f
            break

    if not video_file or not os.path.exists(video_file):
        await callback.message.answer("⚠️ Video fayli topilmadi yoki o'chib ketgan.")
        return

    mp3_file = f"extracted_{user_id}.mp3"
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': mp3_file.replace('.mp3', ''),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
    }

    try:
        # Kodni ishlatib audioni MP3 ga o'tkazish
        cmd = f"ffmpeg -i {video_file} -vn -ar 44100 -ac 2 -b:a 192k {mp3_file} -y"
        proc = await asyncio.create_subprocess_shell(cmd)
        await proc.communicate()

        if os.path.exists(mp3_file):
            await callback.message.answer_audio(
                audio=types.FSInputFile(mp3_file),
                caption="🎵 Videodan ajratib olingan audio!"
            )
            os.remove(mp3_file)
        else:
            await callback.message.answer("❌ Audioni ajratib bo'lmadi.")

    except Exception as e:
        logging.error(f"Audio extraction error: {e}")
        await callback.message.answer("⚠️ Audioni ajratishda xatolik yuz berdi.")
    finally:
        if video_file and os.path.exists(video_file):
            os.remove(video_file)

async def main():
    print("Bot muvaffaqiyatli ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
