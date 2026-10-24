"""Mesure de fiabilité : on pose les questions de evaluation/questions.json et on compare le
RÉSULTAT obtenu à celui de la requête de référence (exactitude à l'exécution).

Une réponse est juste si elle renvoie le même nombre de lignes et si chaque colonne de la
référence se retrouve (mêmes valeurs, à l'arrondi près) dans une colonne de la réponse. Les
colonnes en plus (nom, banque…) ne sont pas pénalisées.
"""
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from . import config, db, nl2sql
from .garde_sql import SQLRefuse, valider_sql

log = logging.getLogger("voicebank")
FICHIER_QUESTIONS = Path(__file__).resolve().parent.parent / "evaluation" / "questions.json"


def charger_questions() -> list[dict]:
    return json.loads(FICHIER_QUESTIONS.read_text(encoding="utf-8"))


def _norm(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    return s[:10] if len(s) >= 19 and s[4] == "-" and s[10] == "T" else s  # horodatage -> date


def _cle_tri(v):
    return (0, v, "") if isinstance(v, float) else (1, 0.0, str(v))


def _colonnes_egales(a: list, b: list) -> bool:
    a, b = sorted(map(_norm, a), key=_cle_tri), sorted(map(_norm, b), key=_cle_tri)
    for x, y in zip(a, b):
        if isinstance(x, float) and isinstance(y, float):
            if abs(x - y) > max(0.01, 0.005 * abs(x)):
                return False
        elif x != y:
            return False
    return len(a) == len(b)


def _inclus(petit: list, grand: list) -> bool:
    """Chaque valeur de `petit` existe dans `grand` (multiensemble, à l'arrondi près)."""
    from collections import Counter
    arrondi = lambda v: round(v, 2) if isinstance(v, float) else v  # noqa: E731
    reste = Counter(arrondi(_norm(v)) for v in grand)
    for v in map(lambda x: arrondi(_norm(x)), petit):
        if reste[v] <= 0:
            return False
        reste[v] -= 1
    return True


def comparer(ref_cols, ref_lignes, cols, lignes, limite: int | None = None) -> bool:
    """`limite` : LIMIT d'affichage de la réponse (liste volontairement tronquée, ex. 100 lignes).
    Dans ce cas, la réponse est juste si elle est un sous-ensemble exact de la référence."""
    gen = [[l[c] for l in lignes] for c in cols]
    if limite and len(lignes) == limite < len(ref_lignes):
        return all(any(_inclus(g, [l[rc] for l in ref_lignes]) for g in gen) for rc in ref_cols)
    if len(ref_lignes) != len(lignes):
        return False
    return all(any(_colonnes_egales([l[rc] for l in ref_lignes], g) for g in gen) for rc in ref_cols)


def _limite(sql: str) -> int | None:
    import re
    m = re.search(r"\blimit\s+(\d+)\s*;?\s*$", sql.strip(), flags=re.I)
    return int(m.group(1)) if m else None


def _executer(sql: str):
    return db.lire(valider_sql(sql, 100_000), brut=True)


def evaluer_question(q: dict) -> dict:
    debut = time.time()
    res = {"id": q["id"], "categorie": q["categorie"], "question": q["question"]}
    try:
        ref_cols, ref_lignes = _executer(q["sql_reference"])
    except Exception as e:
        return {**res, "statut": "reference_invalide", "erreur": str(e)[:200]}
    contexte = q.get("contexte")
    try:
        question = nl2sql.normaliser_question(q["question"])
        if contexte:
            def cols_prec():
                return _executer(contexte["sql"])[0]
            sql, source, _, avert, _ = nl2sql.texte_vers_sql_avec_contexte(question, contexte, cols_prec)
        else:
            sql, source, _, avert = nl2sql.texte_vers_sql(question)
    except nl2sql.IAIndisponible:
        return {**res, "statut": "non_traitee", "source": None, "duree_ms": int((time.time() - debut) * 1000)}
    res.update(source=source, sql=sql, avertissement=avert)
    try:
        cols, lignes = _executer(sql)
    except (SQLRefuse, Exception) as e:
        return {**res, "statut": "erreur_sql", "erreur": str(e)[:200]}
    juste = comparer(ref_cols, ref_lignes, cols, lignes, _limite(sql))
    statut = "juste" if juste else ("approximative" if avert else "faux")
    if avert:  # réponse partielle signalée à l'utilisateur : comptée à part, jamais comme juste
        res["source"] = "approximation"
        statut = "approximative"
    return {**res, "statut": statut, "duree_ms": int((time.time() - debut) * 1000)}


def evaluer(questions: list[dict] | None = None) -> dict:
    questions = questions or charger_questions()
    details = [evaluer_question(q) for q in questions]
    valides = [d for d in details if d["statut"] != "reference_invalide"]
    justes = sum(d["statut"] == "juste" for d in valides)

    def stats(groupe):
        n = len(groupe)
        ok = sum(d["statut"] == "juste" for d in groupe)
        return {"questions": n, "justes": ok, "taux": round(100 * ok / n, 1) if n else None}

    par_categorie = {c: stats([d for d in valides if d["categorie"] == c])
                     for c in sorted({d["categorie"] for d in valides})}
    par_source = {s: stats([d for d in valides if (d.get("source") or "aucune") == s])
                  for s in sorted({d.get("source") or "aucune" for d in valides})}
    return {"date": datetime.now().isoformat(timespec="seconds"), "nb_questions": len(valides),
            "nb_reussies": justes, "taux_reussite": round(100 * justes / len(valides), 1) if valides else 0,
            "gemini_actif": bool(config.GEMINI_API_KEY), "par_categorie": par_categorie,
            "par_source": par_source, "details": details}


# ── Exécution en arrière-plan depuis l'API (une seule à la fois) ──
_verrou = threading.Lock()
etat = {"en_cours": False, "lance_par": None, "debut": None}


def lancer_en_arriere_plan(utilisateur: str) -> bool:
    if not _verrou.acquire(blocking=False):
        return False
    etat.update(en_cours=True, lance_par=utilisateur, debut=datetime.now().isoformat(timespec="seconds"))

    def _travail():
        try:
            r = evaluer()
            db.ecrire("INSERT INTO voicebank.evaluations (utilisateur, nb_questions, nb_reussies, taux_reussite, "
                      "gemini_actif, details) VALUES (:u, :n, :ok, :t, :g, CAST(:d AS JSONB))",
                      {"u": utilisateur, "n": r["nb_questions"], "ok": r["nb_reussies"], "t": r["taux_reussite"],
                       "g": r["gemini_actif"], "d": json.dumps(r, ensure_ascii=False, default=str)})
        except Exception:
            log.exception("Évaluation impossible")
        finally:
            etat.update(en_cours=False)
            _verrou.release()

    threading.Thread(target=_travail, daemon=True, name="evaluation").start()
    return True
