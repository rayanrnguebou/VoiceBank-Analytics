"""Clés d'API : le logiciel bancaire de l'organisation demande un score de fraude AVANT de valider une opération.

Une clé est liée à une base connectée. Elle s'affiche une seule fois à sa création (« vb_… ») ; VoiceBank ne garde
que son empreinte SHA-256 et ses 12 premiers caractères pour la reconnaître dans la liste. L'appel est refusé si la
clé est révoquée, si le compte qui l'a créée n'est plus actif ou si l'abonnement est échu.
"""
import hashlib
import secrets

from . import db
from .securite import _SQL_ACCES_EXPIRE

MAX_CLES = 10
DECISIONS = {"Critique": "bloquer", "Élevé": "verifier"}


class CleRefusee(ValueError):
    """Message affichable."""


def _empreinte(cle: str) -> str:
    return hashlib.sha256(cle.encode()).hexdigest()


def creer(id_source: int, nom: str, par: str) -> dict:
    n = db.ecrire("SELECT COUNT(*) FROM voicebank.cles_api WHERE id_source = :s AND NOT revoquee", {"s": id_source}).scalar()
    if n >= MAX_CLES:
        raise CleRefusee(f"{MAX_CLES} clés actives au plus par base : révoque d'abord une clé inutilisée.")
    cle = "vb_" + secrets.token_urlsafe(32)
    r = db.ecrire("INSERT INTO voicebank.cles_api (id_source, nom, prefixe, empreinte, cree_par) "
                  "VALUES (:s, :n, :p, :e, :c) RETURNING id_cle, date_creation",
                  {"s": id_source, "n": nom.strip()[:80], "p": cle[:12], "e": _empreinte(cle), "c": par[:64]}).lignes[0]
    return {"id": r.id_cle, "nom": nom.strip()[:80], "prefixe": cle[:12], "cle": cle, "date_creation": r.date_creation.isoformat()}


def lister(id_source: int) -> list[dict]:
    r = db.ecrire("SELECT id_cle, nom, prefixe, cree_par, date_creation, derniere_utilisation, nb_appels, revoquee "
                  "FROM voicebank.cles_api WHERE id_source = :s ORDER BY revoquee, date_creation DESC", {"s": id_source}).lignes
    return [{"id": l.id_cle, "nom": l.nom, "prefixe": l.prefixe, "cree_par": l.cree_par,
             "date_creation": l.date_creation.isoformat(),
             "derniere_utilisation": l.derniere_utilisation.isoformat() if l.derniere_utilisation else None,
             "nb_appels": int(l.nb_appels), "revoquee": l.revoquee} for l in r]


def revoquer(id_source: int, id_cle: int) -> None:
    r = db.ecrire("UPDATE voicebank.cles_api SET revoquee = TRUE WHERE id_source = :s AND id_cle = :i",
                  {"s": id_source, "i": id_cle})
    if not r.rowcount:
        raise CleRefusee("Clé introuvable")


def verifier(cle: str) -> tuple[int, str]:
    """(base, compte au nom duquel lire la base) ; lève CleRefusee sinon. Compte l'appel."""
    if not cle or not cle.startswith("vb_") or len(cle) > 80:
        raise CleRefusee("Clé d'API absente ou invalide.")
    r = db.ecrire(
        "SELECT k.id_cle, k.id_source, k.revoquee, k.cree_par AS nom, "
        "(SELECT actif FROM voicebank.utilisateurs WHERE nom = k.cree_par) AS actif, "
        f"(SELECT {_SQL_ACCES_EXPIRE} FROM voicebank.utilisateurs WHERE nom = k.cree_par) AS expire "
        "FROM voicebank.cles_api k WHERE k.empreinte = :e", {"e": _empreinte(cle)}).lignes
    if not r or r[0].revoquee or not r[0].actif:
        raise CleRefusee("Clé d'API absente ou invalide.")
    if r[0].expire:
        raise CleRefusee("Abonnement échu : renouvelle-le pour continuer à utiliser l'API.")
    db.ecrire("UPDATE voicebank.cles_api SET nb_appels = nb_appels + 1, derniere_utilisation = LOCALTIMESTAMP "
              "WHERE id_cle = :i", {"i": r[0].id_cle})
    return r[0].id_source, r[0].nom
