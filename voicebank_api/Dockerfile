# VOICEBANK ANALYTICS - Dockerfile API FastAPI
# Auteur : Nguebou Temgoua Rayan

FROM python:3.10-slim

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Dossier de travail
WORKDIR /app

# Installer les dependances systeme (ffmpeg pour Whisper)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel

# Copier et installer les dependances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY . .

# Port expose
EXPOSE 8000

# Lancement
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
