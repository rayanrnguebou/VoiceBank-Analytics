# VOICEBANK ANALYTICS - Dockerfile API FastAPI
# Auteur : Nguebou Temgoua Rayan

FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel

# Chemin correct depuis la racine du dépôt
COPY voicebank_api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier l'API
COPY voicebank_api/ .

# Copier les modèles IA
COPY voicebank_ia/ ./voicebank_ia/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]