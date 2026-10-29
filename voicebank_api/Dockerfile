# VoiceBank Analytics — API FastAPI
# Build depuis la RACINE du dépôt : docker build -f voicebank_api/Dockerfile .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ENV=production
WORKDIR /app

COPY voicebank_api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY voicebank_api/main.py ./main.py
COPY voicebank_api/app ./app
COPY voicebank_api/evaluation/questions.json ./evaluation/questions.json
COPY voicebank_ia/modeles_sauvegardes ./voicebank_ia/modeles_sauvegardes
COPY voicebank_whisper ./voicebank_whisper
COPY voicebank_db/init ./voicebank_db/init
COPY voicebank_api/demarrer.sh ./demarrer.sh

# Utilisateur sans privilèges
# Modèles Whisper local téléchargés au 1er démarrage dans un volume (voir docker-compose)
ENV WHISPER_LOCAL_DOSSIER=/app/modeles_whisper HF_HOME=/app/modeles_whisper/hf
RUN useradd --create-home --uid 10001 voicebank && mkdir -p /app/modeles_whisper && chown -R voicebank /app
USER voicebank

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/health/vivant').status==200 else 1)"
CMD ["sh", "/app/demarrer.sh"]
