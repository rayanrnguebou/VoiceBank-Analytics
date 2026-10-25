"""Mot de passe oublié : code à 6 chiffres envoyé par e-mail.

Sécurité :
* la réponse à une demande est toujours la même (on ne révèle pas si un compte existe) et l'e-mail
  part en arrière-plan (pas de différence de temps de réponse) ;
* seule l'empreinte HMAC du code est stockée ; il expire après CODE_RECUPERATION_MIN minutes,
  ne sert qu'une fois, est détruit après 5 essais faux, et une nouvelle demande annule l'ancien ;
* 3 demandes par heure et par compte au plus (en plus de la limite par adresse IP de l'API) ;
* le changement déverrouille le compte et déconnecte toutes les sessions ; un e-mail de confirmation
  prévient le titulaire.
"""
import hashlib
import hmac
import logging
import secrets
import threading
from datetime import timedelta

from . import config, courriel, db
from .securite import CompteRefuse, EMAIL_VALIDE, _HASH_FACTICE, hacher, mode_base, verifier_politique

import bcrypt

log = logging.getLogger("voicebank")

MAX_ESSAIS = 5
MAX_DEMANDES_HEURE = 3
REFUS = "Code incorrect ou expiré. Demande un nouveau code si besoin."


def _empreinte(nom: str, code: str) -> str:
    return hmac.new(config.JWT_SECRET.encode(), f"{nom}:{code}".encode(), hashlib.sha256).hexdigest()


def _compte(identifiant: str):
    i = identifiant.strip()
    r = db.ecrire("SELECT nom, email, nom_complet FROM voicebank.utilisateurs WHERE actif AND email IS NOT NULL "
                  "AND (nom = :i OR LOWER(email) = LOWER(:i)) LIMIT 1", {"i": i})
    return r.lignes[0] if r.lignes else None


def _envoyer_en_arriere_plan(*args, **kwargs):
    def tache():
        try:
            courriel.envoyer(*args, **kwargs)
        except Exception as e:
            log.warning("E-mail non envoyé : %s", e)
    threading.Thread(target=tache, daemon=True).start()


def disponible() -> bool:
    return mode_base() and courriel.disponible()


def demander(identifiant: str, ip: str | None = None) -> str | None:
    """Envoie un code si le compte existe et a une adresse e-mail. Retourne le nom du compte (pour le
    journal) ou None ; l'appelant répond toujours la même chose."""
    if not disponible():
        return None
    l = _compte(identifiant)
    if l is None:
        return None
    n = db.ecrire("SELECT COUNT(*) FROM voicebank.codes_recuperation WHERE utilisateur = :n "
                  "AND date_creation > LOCALTIMESTAMP - INTERVAL '1 hour'", {"n": l.nom}).scalar()
    if n >= MAX_DEMANDES_HEURE:
        log.info("Récupération : trop de demandes pour '%s'", l.nom)
        return None
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.ecrire("UPDATE voicebank.codes_recuperation SET utilise = TRUE WHERE utilisateur = :n AND NOT utilise",
              {"n": l.nom})
    db.ecrire("INSERT INTO voicebank.codes_recuperation (utilisateur, empreinte, expire, adresse_ip) "
              "VALUES (:n, :e, LOCALTIMESTAMP + :d, :ip)",
              {"n": l.nom, "e": _empreinte(l.nom, code), "d": timedelta(minutes=config.CODE_RECUPERATION_MIN),
               "ip": (ip or "")[:64]})
    prenom = (l.nom_complet or "").split(" ")[0]
    _envoyer_en_arriere_plan(
        l.email, f"{code} : ton code VoiceBank", "Réinitialisation de ton mot de passe",
        [f"Bonjour{' ' + prenom if prenom else ''},",
         f"Voici ton code pour choisir un nouveau mot de passe. Il est valable {config.CODE_RECUPERATION_MIN} minutes "
         "et ne peut servir qu'une fois.",
         "Ne le communique à personne : l'équipe VoiceBank ne te le demandera jamais.",
         "Si tu n'as rien demandé, ignore ce message : ton mot de passe actuel reste valable."],
        code=code)
    return l.nom


def confirmer(identifiant: str, code: str, nouveau: str) -> str:
    """Change le mot de passe si le code est bon. Retourne le nom du compte."""
    if not disponible():
        raise CompteRefuse("La récupération par e-mail n'est pas activée : contacte ton administrateur.")
    code = "".join(c for c in (code or "") if c.isdigit())
    l = _compte(identifiant)
    nom = l.nom if l else identifiant.strip()
    verifier_politique(nouveau, nom.split("@")[0])
    if l is None or len(code) != 6:
        bcrypt.checkpw(b"x", _HASH_FACTICE)
        raise CompteRefuse(REFUS)
    r = db.ecrire("SELECT id_code, empreinte FROM voicebank.codes_recuperation WHERE utilisateur = :n AND NOT utilise "
                  "AND expire > LOCALTIMESTAMP AND tentatives < :m ORDER BY date_creation DESC LIMIT 1",
                  {"n": l.nom, "m": MAX_ESSAIS})
    c = r.lignes[0] if r.lignes else None
    if c is None:
        raise CompteRefuse(REFUS)
    if not hmac.compare_digest(c.empreinte, _empreinte(l.nom, code)):
        db.ecrire("UPDATE voicebank.codes_recuperation SET tentatives = tentatives + 1, "
                  "utilise = (tentatives + 1 >= :m) WHERE id_code = :i", {"i": c.id_code, "m": MAX_ESSAIS})
        raise CompteRefuse(REFUS)
    # Consommation atomique : un même code ne peut pas servir deux fois en parallèle
    if not db.ecrire("UPDATE voicebank.codes_recuperation SET utilise = TRUE WHERE id_code = :i AND NOT utilise",
                     {"i": c.id_code}).rowcount:
        raise CompteRefuse(REFUS)
    db.ecrire("UPDATE voicebank.utilisateurs SET hash_mdp = :h, doit_changer_mdp = FALSE, mdp_provisoire_expire = NULL, "
              "echecs_connexion = 0, verrouille_jusqua = NULL, date_modif_mdp = LOCALTIMESTAMP, "
              "version_jeton = version_jeton + 1 WHERE nom = :n", {"n": l.nom, "h": hacher(nouveau)})
    _envoyer_en_arriere_plan(
        l.email, "Ton mot de passe VoiceBank a été modifié", "Mot de passe modifié",
        ["Le mot de passe de ton compte VoiceBank vient d'être changé avec un code envoyé à cette adresse. "
         "Toutes les sessions ouvertes ont été déconnectées.",
         "Si ce n'est pas toi, préviens immédiatement ton administrateur."])
    return l.nom


def definir_email(nom: str, mot_de_passe: str, email: str | None) -> str | None:
    """Adresse de récupération d'un compte (mot de passe actuel exigé). None : supprime l'adresse."""
    if not mode_base():
        raise CompteRefuse("Indisponible pour le moment")
    r = db.ecrire("SELECT hash_mdp, role FROM voicebank.utilisateurs WHERE nom = :n", {"n": nom})
    if not r.lignes or not bcrypt.checkpw(mot_de_passe.encode()[:72], r.lignes[0].hash_mdp.encode()):
        raise CompteRefuse("Mot de passe actuel incorrect")
    if r.lignes[0].role == "visiteur" or r.lignes[0].role == "client":
        raise CompteRefuse("Ton adresse e-mail est ton identifiant : elle ne peut pas être changée ici.")
    if email is not None:
        email = email.strip().lower()
        if len(email) > 64 or not EMAIL_VALIDE.fullmatch(email):
            raise CompteRefuse("Adresse e-mail invalide")
    pris = email and db.ecrire("SELECT 1 FROM voicebank.utilisateurs WHERE LOWER(email) = :e AND nom <> :n",
                               {"e": email, "n": nom}).lignes
    if pris:
        raise CompteRefuse("Cette adresse est déjà utilisée par un autre compte")
    db.ecrire("UPDATE voicebank.utilisateurs SET email = :e WHERE nom = :n", {"e": email, "n": nom})
    return email
