"""Approbation sur le téléphone : la double authentification par notification, avec choix du nombre.

Parcours
1. Une fois : sur le téléphone (VoiceBank ajouté à l'écran d'accueil), la personne, déjà connectée avec son code à
   6 chiffres, enregistre l'appareil (code à 6 chiffres redemandé). Le téléphone reçoit un secret aléatoire, gardé
   dans le navigateur ; seule son empreinte est en base.
2. À chaque connexion : après le mot de passe, l'ordinateur demande l'approbation. Une notification part vers les
   téléphones enregistrés ; l'ordinateur affiche un nombre (10 à 99) que la personne doit toucher sur le téléphone
   parmi trois. Bon nombre : la connexion s'ouvre ; mauvais nombre ou « Ce n'était pas moi » : la demande est refusée
   (et, dans le second cas, un e-mail d'alerte part).

Garde-fous : demande valable 2 minutes, liée à la tentative de connexion (empreinte du jeton intermédiaire), usage
unique ; réponse seulement avec le secret d'un appareil enregistré du même compte ; le code à 6 chiffres et les codes
de secours restent toujours utilisables.
Les clés de notification (VAPID) sont créées au premier besoin et gardées chiffrées dans voicebank.parametres.
"""
import base64
import hashlib
import json
import logging
import secrets
import threading
from datetime import datetime

from . import config, courriel, db

log = logging.getLogger("voicebank")
DUREE_S = 120
MAX_APPAREILS = 5
CLE_VAPID = "vapid"
ENVOI_EN_FOND = True


class ApprobationRefusee(Exception):
    """Message affichable."""


def _empreinte(texte: str) -> str:
    return hashlib.sha256(f"{config.JWT_SECRET[:16]}:{texte}".encode()).hexdigest()


# ── Clés VAPID (identité de l'émetteur des notifications) ──────────────
_vapid: dict = {}
_verrou = threading.Lock()


def _cles() -> dict:
    """{"public": clé publique (base64url, pour le navigateur), "pem": clé privée}. Créées une seule fois."""
    with _verrou:
        if _vapid:
            return _vapid
        from .connecteur.connexion import chiffrer, dechiffrer
        l = db.ecrire("SELECT valeur FROM voicebank.parametres WHERE cle = :c", {"c": CLE_VAPID}).lignes
        if not l:
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
            from py_vapid import Vapid
            v = Vapid()
            v.generate_keys()
            public = base64.urlsafe_b64encode(
                v.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)).decode().rstrip("=")
            valeur = {"public": public, "prive": chiffrer({"pem": v.private_pem().decode()})}
            db.ecrire("INSERT INTO voicebank.parametres (cle, valeur, modifie_par) VALUES (:c, CAST(:v AS JSONB), 'systeme') "
                      "ON CONFLICT (cle) DO NOTHING", {"c": CLE_VAPID, "v": json.dumps(valeur)})
            l = db.ecrire("SELECT valeur FROM voicebank.parametres WHERE cle = :c", {"c": CLE_VAPID}).lignes
        valeur = l[0].valeur
        _vapid.update(public=valeur["public"], pem=dechiffrer(valeur["prive"])["pem"])
        return _vapid


def cle_publique() -> str:
    return _cles()["public"]


# ── Appareils d'approbation ────────────────────────────────────────────
def appareils(nom: str) -> list[dict]:
    r = db.ecrire("SELECT id_appareil, nom, date_ajout, derniere_utilisation FROM voicebank.appareils_approbation "
                  "WHERE utilisateur = :n ORDER BY date_ajout DESC", {"n": nom})
    return [{"id": l.id_appareil, "nom": l.nom, "date_ajout": l.date_ajout.isoformat(),
             "derniere_utilisation": l.derniere_utilisation.isoformat() if l.derniere_utilisation else None}
            for l in r.lignes]


def possible(nom: str) -> bool:
    return bool(db.ecrire("SELECT 1 FROM voicebank.appareils_approbation WHERE utilisateur = :n LIMIT 1",
                          {"n": nom}).lignes)


def enregistrer(nom: str, nom_appareil: str, abonnement: dict) -> str:
    """Retourne le secret de l'appareil (à garder dans le téléphone ; jamais renvoyé ensuite)."""
    point = str(abonnement.get("endpoint", ""))
    cles = abonnement.get("keys") or {}
    if not point.startswith("https://") or not cles.get("p256dh") or not cles.get("auth"):
        raise ApprobationRefusee("Abonnement aux notifications invalide : réautorise les notifications puis réessaie.")
    n = db.ecrire("SELECT COUNT(*) FROM voicebank.appareils_approbation WHERE utilisateur = :n", {"n": nom}).scalar()
    if n >= MAX_APPAREILS:
        raise ApprobationRefusee(f"{MAX_APPAREILS} téléphones au maximum : retire d'abord un ancien téléphone.")
    secret = secrets.token_urlsafe(32)
    db.ecrire("DELETE FROM voicebank.appareils_approbation WHERE utilisateur = :n AND abonnement->>'endpoint' = :p",
              {"n": nom, "p": point})                     # même téléphone enregistré une seconde fois
    db.ecrire("INSERT INTO voicebank.appareils_approbation (utilisateur, nom, abonnement, empreinte_secret) "
              "VALUES (:n, :a, CAST(:b AS JSONB), :e)",
              {"n": nom, "a": nom_appareil[:120], "b": json.dumps({"endpoint": point, "keys": {
                  "p256dh": str(cles["p256dh"])[:200], "auth": str(cles["auth"])[:100]}}), "e": _empreinte(secret)})
    return secret


def retirer(nom: str, id_appareil: int) -> None:
    if not db.ecrire("DELETE FROM voicebank.appareils_approbation WHERE id_appareil = :i AND utilisateur = :n",
                     {"i": id_appareil, "n": nom}).rowcount:
        raise ApprobationRefusee("Téléphone introuvable")


def retirer_tout(nom: str) -> None:
    db.ecrire("DELETE FROM voicebank.appareils_approbation WHERE utilisateur = :n", {"n": nom})


def _appareil_par_secret(secret: str):
    l = db.ecrire("SELECT id_appareil, utilisateur FROM voicebank.appareils_approbation WHERE empreinte_secret = :e",
                  {"e": _empreinte(secret or "")}).lignes
    if not l:
        raise ApprobationRefusee("Ce téléphone n'est plus enregistré pour approuver les connexions.")
    return l[0]


# ── Demandes ───────────────────────────────────────────────────────────
def _envoyer(abonnement: dict, contenu: dict) -> bool:
    """Envoie la notification ; False si le téléphone s'est désabonné (à retirer)."""
    from pywebpush import WebPushException, webpush
    from py_vapid import Vapid
    try:
        webpush(abonnement, json.dumps(contenu), vapid_private_key=Vapid.from_pem(_cles()["pem"].encode()),
                vapid_claims={"sub": f"mailto:{config.EMAIL_CONTACT or 'contact@voicebank.invalid'}"}, ttl=DUREE_S,
                timeout=10, headers={"Urgency": "high"})
        return True
    except WebPushException as e:
        code = getattr(e.response, "status_code", None)
        if code in (404, 410):
            return False
        log.warning("Notification d'approbation non envoyée (%s)", code or e)
        return True
    except Exception:
        log.exception("Notification d'approbation non envoyée")
        return True


def demander(nom: str, jeton_connexion: str, navigateur: str, ip: str | None) -> dict:
    """Crée (ou reprend) la demande liée à cette tentative de connexion et prévient les téléphones."""
    empreinte = _empreinte(jeton_connexion)
    deja = db.ecrire("SELECT id_demande, nombre FROM voicebank.demandes_approbation WHERE empreinte_connexion = :e "
                     "AND statut = 'attente' AND expire > LOCALTIMESTAMP", {"e": empreinte}).lignes
    if deja:
        return {"id": deja[0].id_demande, "nombre": deja[0].nombre, "expire_dans_s": DUREE_S}
    telephones = db.ecrire("SELECT id_appareil, abonnement FROM voicebank.appareils_approbation WHERE utilisateur = :n",
                           {"n": nom}).lignes
    if not telephones:
        raise ApprobationRefusee("Aucun téléphone enregistré pour approuver les connexions : utilise ton code à 6 chiffres.")
    nombre = secrets.randbelow(90) + 10
    autres = set()
    while len(autres) < 2:
        x = secrets.randbelow(90) + 10
        if x != nombre:
            autres.add(x)
    choix = sorted([nombre, *autres])
    id_demande = secrets.token_urlsafe(16)
    db.ecrire("INSERT INTO voicebank.demandes_approbation (id_demande, utilisateur, empreinte_connexion, nombre, choix, "
              "navigateur, adresse_ip, expire) VALUES (:i, :n, :e, :nb, CAST(:c AS JSONB), :nav, :ip, "
              "LOCALTIMESTAMP + make_interval(secs => :d))",
              {"i": id_demande, "n": nom, "e": empreinte, "nb": nombre, "c": json.dumps(choix), "nav": navigateur[:120],
               "ip": ip, "d": DUREE_S})
    from . import i18n
    langue = db.ecrire("SELECT langue FROM voicebank.utilisateurs WHERE nom = :n", {"n": nom}).scalar() or "fr"
    contenu = {"type": "approbation", "id": id_demande,
               "titre": i18n.traduire("VoiceBank : connexion demandée", langue),
               "texte": i18n.traduire(f"{navigateur} · {ip or 'adresse inconnue'} · touche pour approuver ou refuser", langue)}

    def envoyer_tout():
        for t in telephones:
            if not _envoyer(t.abonnement, contenu):
                db.ecrire("DELETE FROM voicebank.appareils_approbation WHERE id_appareil = :i", {"i": t.id_appareil})
    if ENVOI_EN_FOND:          # l'ordinateur affiche le nombre tout de suite, même si le service de notification traîne
        threading.Thread(target=envoyer_tout, daemon=True, name="notification-approbation").start()
    else:
        envoyer_tout()
    return {"id": id_demande, "nombre": nombre, "expire_dans_s": DUREE_S}


def detail(id_demande: str, secret: str) -> dict:
    """Ce que le téléphone affiche : d'où vient la demande, et les trois nombres."""
    app = _appareil_par_secret(secret)
    l = db.ecrire("SELECT utilisateur, choix, statut, navigateur, adresse_ip, date_creation, expire > LOCALTIMESTAMP AS valide "
                  "FROM voicebank.demandes_approbation WHERE id_demande = :i", {"i": id_demande}).lignes
    if not l or l[0].utilisateur != app.utilisateur:
        raise ApprobationRefusee("Demande introuvable")
    d = l[0]
    statut = d.statut if d.valide or d.statut != "attente" else "expiree"
    return {"compte": d.utilisateur, "navigateur": d.navigateur, "adresse_ip": d.adresse_ip,
            "date": d.date_creation.isoformat(), "choix": d.choix if statut == "attente" else [], "statut": statut}


def repondre(id_demande: str, secret: str, nombre: int | None, refuser: bool, ip: str | None) -> str:
    """« approuvee » ou « refusee ». Un mauvais nombre refuse la demande (pas de seconde chance)."""
    app = _appareil_par_secret(secret)
    l = db.ecrire("SELECT utilisateur, nombre, navigateur, adresse_ip FROM voicebank.demandes_approbation "
                  "WHERE id_demande = :i AND statut = 'attente' AND expire > LOCALTIMESTAMP",
                  {"i": id_demande}).lignes
    if not l or l[0].utilisateur != app.utilisateur:
        raise ApprobationRefusee("Cette demande a expiré ou a déjà reçu une réponse.")
    d = l[0]
    if refuser:
        statut, motif = "refusee", "pas_moi"
    elif nombre == d.nombre:
        statut, motif = "approuvee", None
    else:
        statut, motif = "refusee", "mauvais_nombre"
    maj = db.ecrire("UPDATE voicebank.demandes_approbation SET statut = :s, motif = :m WHERE id_demande = :i "
                    "AND statut = 'attente'", {"s": statut, "m": motif, "i": id_demande})
    if not maj.rowcount:
        raise ApprobationRefusee("Cette demande a déjà reçu une réponse.")
    db.ecrire("UPDATE voicebank.appareils_approbation SET derniere_utilisation = LOCALTIMESTAMP WHERE id_appareil = :i",
              {"i": app.id_appareil})
    from . import audit
    audit.journaliser(d.utilisateur, f"approbation_{statut}", {"motif": motif, "navigateur": d.navigateur,
                                                               "ip_connexion": d.adresse_ip}, ip)
    if motif == "pas_moi":
        _alerter(d.utilisateur, d.navigateur, d.adresse_ip)
    return statut


def etat(id_demande: str, jeton_connexion: str) -> tuple[str, str]:
    """Pour l'ordinateur qui attend : (statut, utilisateur). « approuvee » n'est rendu qu'une fois (puis « utilisee »)."""
    l = db.ecrire("SELECT utilisateur, statut, motif, expire > LOCALTIMESTAMP AS valide FROM voicebank.demandes_approbation "
                  "WHERE id_demande = :i AND empreinte_connexion = :e", {"i": id_demande, "e": _empreinte(jeton_connexion)}).lignes
    if not l:
        raise ApprobationRefusee("Demande introuvable")
    d = l[0]
    if d.statut == "approuvee":
        if not db.ecrire("UPDATE voicebank.demandes_approbation SET statut = 'utilisee' WHERE id_demande = :i "
                         "AND statut = 'approuvee'", {"i": id_demande}).rowcount:
            return "utilisee", d.utilisateur
        return "approuvee", d.utilisateur
    if d.statut == "attente" and not d.valide:
        return "expiree", d.utilisateur
    return (d.motif or d.statut) if d.statut == "refusee" else d.statut, d.utilisateur


def _alerter(nom: str, navigateur: str | None, ip: str | None):
    if not courriel.disponible():
        return
    l = db.ecrire("SELECT email, nom_complet FROM voicebank.utilisateurs WHERE nom = :n", {"n": nom}).lignes
    if not l or not l[0].email:
        return
    courriel.envoyer_en_arriere_plan(l[0].email, courriel.Message(
        sujet="Tentative de connexion bloquée sur votre compte VoiceBank",
        titre="Connexion refusée depuis votre téléphone",
        salutation=f"Bonjour {l[0].nom_complet}," if l[0].nom_complet else "Bonjour,",
        paragraphes=["Vous avez indiqué sur votre téléphone ne pas être à l'origine d'une tentative de connexion. Elle a "
                     "été bloquée. Comme elle est passée après le mot de passe, quelqu'un connaît probablement votre "
                     "mot de passe."],
        details=[("Date", datetime.now().strftime("%d/%m/%Y %H:%M")), ("Appareil", navigateur or "inconnu"),
                 ("Adresse IP", ip or "inconnue")],
        bouton=("Changer mon mot de passe", config.URL_INTERFACE),
        apres=["Changez votre mot de passe dès maintenant (« Sécurité de mon compte »), puis choisissez « Déconnecter "
               "les autres appareils »."],
        apercu="Tentative de connexion bloquée",
        note="E-mail de sécurité envoyé quand une connexion est refusée depuis le téléphone."))
