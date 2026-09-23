# 1. Asosiy Python bazasini yuklaymiz
FROM python:3.11-slim

# 2. Videodan audio ajratish uchun ffmpeg dasturini o'rnatamiz
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 3. Ishchi papkani belgilaymiz
WORKDIR /app

# 4. Kerakli kutubxonalar ro'yxatini ko'chirib o'tkazamiz
COPY requirements.txt .

# 5. Python kutubxonalarini o'rnatamiz
RUN pip install --no-cache-dir -r requirements.txt

# 6. Loyihadagi barcha fayllarni ko'chirib o'tkazamiz
COPY . .

# 7. Botni ishga tushiramiz
CMD ["python", "main.py"]
