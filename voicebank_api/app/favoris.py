"""Questions favorites : relancées en un clic depuis l'assistant ; si l'utilisateur le demande, la réponse du jour
lui est envoyée chaque lundi matin par e-mail (résumé, premières lignes, fichier CSV complet).

La question est rejouée avec les droits ACTUELS du compte (rôle, masquage des données personnelles, accès à la base) :
un compte désactivé, un essai terminé ou une base retirée n'envoient plus rien.
"""
import csv
import io
import logging
from datetime import datetime, timedelta

from . import config, courriel, db
from .connecteur import service as sources

log = logging.getLogger("voicebank")
MAX_FAVORIS = 20


class FavoriRefuse(Exception):
    """Message affichable."""


def lister(nom: str) -> list[dict]:
    r = db.ecrire("SELECT f.id_favori, f.question, f.id_source, f.devise, f.envoi_hebdo, f.date_creation, f.dernier_envoi, "
                  "s.nom AS nom_source FROM voicebank.questions_favorites f "
                  "LEFT JOIN voicebank.sources_donnees s ON s.id_source = f.id_source "
                  "WHERE f.utilisateur = :n ORDER BY f.date_creation DESC", {"n": nom})
    return [{"id": l.id_favori, "question": l.question, "id_source": l.id_source or 0,
             "base": l.nom_source or "Démonstration VoiceBank", "devise": l.devise, "envoi_hebdo": l.envoi_hebdo,
             "dernier_envoi": l.dernier_envoi.isoformat() if l.dernier_envoi else None} for l in r.lignes]


def ajouter(nom: str, question: str, id_source: int, devise: str) -> dict:
    question = " ".join(question.split())[:500]
    if len(question) < 3:
        raise FavoriRefuse("Question trop courte")
    if id_source:
        try:
            sources.detail(id_source, nom)               # la base doit être accessible à ce compte
        except sources.SourceRefusee:
            raise FavoriRefuse("Base introuvable")
    n = db.ecrire("SELECT COUNT(*) FROM voicebank.questions_favorites WHERE utilisateur = :n", {"n": nom}).scalar()
    if n >= MAX_FAVORIS:
        raise FavoriRefuse(f"{MAX_FAVORIS} favoris au maximum : retire d'abord une question.")
    r = db.ecrire("INSERT INTO voicebank.questions_favorites (utilisateur, question, id_source, devise) "
                  "VALUES (:n, :q, :s, :d) ON CONFLICT DO NOTHING RETURNING id_favori",
                  {"n": nom, "q": question, "s": id_source or None, "d": devise})
    if not r.lignes:
        raise FavoriRefuse("Cette question est déjà dans tes favoris.")
    return next(f for f in lister(nom) if f["id"] == r.scalar())


def modifier(nom: str, id_favori: int, envoi_hebdo: bool) -> None:
    if not db.ecrire("UPDATE voicebank.questions_favorites SET envoi_hebdo = :e WHERE id_favori = :i AND utilisateur = :n",
                     {"e": envoi_hebdo, "i": id_favori, "n": nom}).rowcount:
        raise FavoriRefuse("Favori introuvable")


def supprimer(nom: str, id_favori: int) -> None:
    if not db.ecrire("DELETE FROM voicebank.questions_favorites WHERE id_favori = :i AND utilisateur = :n",
                     {"i": id_favori, "n": nom}).rowcount:
        raise FavoriRefuse("Favori introuvable")


# ── Envoi du lundi ────────────────────────────────────────────────────
def _executer(l) -> dict:
    """Rejoue la question avec les droits actuels du compte."""
    from .api.commun import _question_vers_resultat
    from .securite import Utilisateur
    if l.id_source:
        return sources.repondre(l.id_source, l.utilisateur, l.role, l.question, l.devise)
    return _question_vers_resultat(l.question, Utilisateur(l.utilisateur, l.role, id_org=l.id_org, role_org=l.role_org),
                                   None, True, l.devise)


def _csv(colonnes: list[str], lignes: list[dict]) -> bytes:
    sortie = io.StringIO()
    w = csv.writer(sortie, delimiter=";")
    w.writerow(colonnes)
    for l in lignes:
        w.writerow([l.get(c, "") for c in colonnes])
    return ("﻿" + sortie.getvalue()).encode("utf-8")      # BOM : Excel ouvre les accents correctement


def message(l, res: dict) -> courriel.Message:
    colonnes, lignes = res.get("colonnes") or [], res.get("data") or []
    details = []
    for ligne in lignes[:10]:
        valeurs = [str(ligne.get(c, "")) for c in colonnes]
        if valeurs:
            details.append((valeurs[0][:60], " · ".join(valeurs[1:])[:120] or "—"))
    base = l.nom_source or "Démonstration VoiceBank"
    return courriel.Message(
        sujet=f"Votre question de la semaine : « {l.question[:80]} »",
        titre=l.question[:150],
        salutation=f"Bonjour {l.nom_complet}," if l.nom_complet else "Bonjour,",
        paragraphes=[res.get("resume") or f"{len(lignes)} résultat(s).",
                     f"Base interrogée : {base}. Les {min(10, len(lignes))} premières lignes sont ci-dessous ; "
                     "le fichier joint contient toutes les lignes."] if lignes else
                    [res.get("resume") or "Aucun résultat cette semaine pour cette question."],
        details=details, bouton=("Ouvrir VoiceBank", config.URL_INTERFACE),
        pieces=[(f"voicebank_{datetime.now():%Y-%m-%d}.csv", _csv(colonnes, lignes), "text/csv")] if lignes else [],
        apercu=f"{len(lignes)} résultat(s) · {base}",
        note="Envoi choisi dans l'assistant (Favoris → « chaque lundi par e-mail »). Décochez-le pour ne plus le recevoir.")


def envoyer_du_lundi(maintenant_local: datetime) -> dict:
    """Le lundi après 7 h (heure de Douala), une fois par semaine et par favori."""
    if maintenant_local.weekday() != 0 or maintenant_local.hour < 7 or not courriel.disponible():
        return {"ignoree": "pas lundi matin" if courriel.disponible() else "e-mails non configurés"}
    seuil = maintenant_local.replace(tzinfo=None) - timedelta(days=6)
    a_envoyer = db.ecrire(
        "SELECT f.id_favori, f.utilisateur, f.question, f.id_source, f.devise, s.nom AS nom_source, u.role, u.id_org, "
        "u.role_org, u.email, u.nom_complet FROM voicebank.questions_favorites f "
        "JOIN voicebank.utilisateurs u ON u.nom = f.utilisateur "
        "LEFT JOIN voicebank.sources_donnees s ON s.id_source = f.id_source "
        "WHERE f.envoi_hebdo AND u.actif AND u.email IS NOT NULL AND (f.dernier_envoi IS NULL OR f.dernier_envoi < :s)",
        {"s": seuil}).lignes
    res = {"envoyes": 0, "erreurs": 0}
    for l in a_envoyer:
        from .securite import _ligne as ligne_compte
        compte = ligne_compte(l.utilisateur)
        if compte is None or compte.acces_expire:
            continue                                     # essai terminé ou abonnement échu : plus d'envoi
        try:
            courriel.envoyer_message(l.email, message(l, _executer(l)))      # dans la langue du destinataire
            res["envoyes"] += 1
        except Exception:
            log.exception("Favori %s : envoi impossible", l.id_favori)
            res["erreurs"] += 1
        db.ecrire("UPDATE voicebank.questions_favorites SET dernier_envoi = LOCALTIMESTAMP WHERE id_favori = :i",
                  {"i": l.id_favori})
    return res
