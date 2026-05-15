# VOICEBANK - Endpoints Whisper a ajouter dans main.py
# Auteur : Nguebou Temgoua Rayan
# Colle ce code dans main.py juste avant la derniere ligne @app.get("/health")

import whisper as whisper_lib
import tempfile

# ── Chargement Whisper ────────────────────────────────
whisper_model = None

def charger_whisper():
    global whisper_model
    try:
        print("  Chargement Whisper 'base'...")
        whisper_model = whisper_lib.load_model("base")
        print("  OK Whisper charge")
    except Exception as e:
        print(f"  ATTENTION Whisper non charge : {e}")

charger_whisper()


# ── Endpoint 1 : Transcription seule ─────────────────
@app.post("/vocal/transcrire")
async def transcrire_audio(fichier: UploadFile = File(...)):
    """Recoit un fichier audio WAV/MP3/M4A et retourne le texte transcrit."""
    if not whisper_model:
        raise HTTPException(503, "Whisper non disponible")

    contenu = await fichier.read()
    extension = fichier.filename.split(".")[-1] if fichier.filename else "wav"

    with tempfile.NamedTemporaryFile(suffix=f".{extension}", delete=False) as f:
        f.write(contenu)
        chemin_tmp = f.name

    try:
        result = whisper_model.transcribe(
            chemin_tmp,
            language="fr",
            fp16=False,
            temperature=0.0,
        )
        texte = result["text"].strip()
        return {
            "status" : "ok",
            "texte"  : texte,
            "langue" : result.get("language", "fr"),
        }
    except Exception as e:
        raise HTTPException(500, f"Erreur transcription : {str(e)}")
    finally:
        os.unlink(chemin_tmp)


# ── Endpoint 2 : Pipeline complet voix -> SQL -> data ─
@app.post("/vocal/pipeline-complet")
async def pipeline_vocal_complet(fichier: UploadFile = File(...)):
    """Pipeline complet : fichier audio -> Whisper -> Gemini -> SQL -> resultats."""
    if not whisper_model:
        raise HTTPException(503, "Whisper non disponible")

    debut = time.time()
    contenu = await fichier.read()
    extension = fichier.filename.split(".")[-1] if fichier.filename else "wav"

    with tempfile.NamedTemporaryFile(suffix=f".{extension}", delete=False) as f:
        f.write(contenu)
        chemin_tmp = f.name

    try:
        # 1. Whisper -> texte
        result = whisper_model.transcribe(
            chemin_tmp,
            language="fr",
            fp16=False,
            temperature=0.0,
        )
        texte = result["text"].strip()

        # 2. Gemini -> SQL
        sql_genere = texte_vers_sql(texte)

        # 3. PostgreSQL -> donnees
        colonnes, rows = executer_sql(sql_genere)

        duree_ms = int((time.time() - debut) * 1000)

        # 4. Logger
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO voicebank.logs_vocaux
                    (texte_transcrit, requete_sql, succes, duree_ms)
                    VALUES (:texte, :sql, :succes, :duree)
                """), {
                    "texte" : texte,
                    "sql"   : sql_genere,
                    "succes": True,
                    "duree" : duree_ms,
                })
                conn.commit()
        except Exception:
            pass

        return {
            "status"      : "ok",
            "texte_audio" : texte,
            "sql"         : sql_genere,
            "colonnes"    : colonnes,
            "total"       : len(rows),
            "data"        : rows,
            "duree_ms"    : duree_ms,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Erreur pipeline vocal : {str(e)}")
    finally:
        os.unlink(chemin_tmp)
