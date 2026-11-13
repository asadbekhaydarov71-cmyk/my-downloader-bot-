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
from shazamio import Shazam

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ["BOT_TOKEN"]
PORT = int(os.environ.get("PORT", "8080"))
COOKIES = os.environ.get("COOKIES_FILE")
# Faqat o'zingiz uchun: Telegram ID(lar)ni vergul bilan yozing. Bo'sh bo'lsa hamma foydalana oladi.
ALLOWED = {
    int(x) for x in os.environ.get("ALLOWED_USERS", "").replace(" ", "").split(",") if x
