# Python-ийн хамгийн тогтвортой хувилбар
FROM python:3.11-slim

# Системийн шаардлагатай сангуудыг (OpenCV, FFmpeg) суулгах
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libstdc++6 \
    ffmpeg \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Ажлын хавтас үүсгэх
WORKDIR /app

# Төслийн файлуудыг хуулах
COPY . .

# Python сангуудыг суулгах
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Асах команд
CMD ["python", "shoplift_detector/main.py"]