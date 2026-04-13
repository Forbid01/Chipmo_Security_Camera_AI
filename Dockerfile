FROM python:3.11-slim

# Системийн шаардлагатай сангуудыг (OpenCV, FFmpeg) суулгах
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libstdc++6 \
    ffmpeg \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir PyJWT python-jose[cryptography]
# Асах команд
CMD ["python", "shoplift_detector/main.py"]