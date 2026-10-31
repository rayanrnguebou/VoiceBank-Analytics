"""Clés d'API : le logiciel bancaire de l'organisation demande un score de fraude AVANT de valider une opération.

Une clé est liée à une base connectée. Elle s'affiche une seule fois à sa création (« vb_… ») ; VoiceBank ne garde
que son empreinte SHA-256 et ses 12 premiers caractères pour la reconnaître dans la liste. L'appel est refusé si la
clé est révoquée, si le compte qui l'a créée n'est plus actif ou si l'abonnement est échu.
"""
import hashlib
import ipaddress
import secrets

from . import db
from .securite import _SQL_ACCES_EXPIRE

MAX_CLES = 10
MAX_RESEAUX = 20
DECISIONS = {"Critique": "bloquer", "Élevé": "verifier"}
MODES = ("actif", "observation")   # observation : VoiceBank note sans bloquer (réponse « accepter »)


class CleRefusee(ValueError):
    """Message affichable."""


def _empreinte(cle: str) -> str:
    return hashlib.sha256(cle.encode()).hexdigest()


def normaliser_ips(texte: str | None) -> str | None:
    """« 41.202.0.0/16, 102.244.1.7 » → forme normalisée ; vide → None (toutes les adresses). Lève CleRefusee."""
    morceaux = [m.strip() for m in (texte or "").replace(";", ",").replace("\n", ",").split(",") if m.strip()]
    if len(morceaux) > MAX_RESEAUX:
        raise CleRefusee(f"{MAX_RESEAUX} adresses ou réseaux au plus par clé.")
    reseaux = []
    for m in morceaux:
        try:
            reseaux.append(str(ipaddress.ip_network(m, strict=False)))
        except ValueError:
            raise CleRefusee(f"Adresse IP ou réseau invalide : {m[:60]} (exemples : 41.202.10.5 ou 41.202.0.0/16)")
    return ", ".join(dict.fromkeys(reseaux)) or None


def ip_autorisee(ip: str, ips: str | None) -> bool:
    if not ips:
        return True
    try:
        adresse = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if getattr(adresse, "ipv4_mapped", None):
        adresse = adresse.ipv4_mapped
    return any(adresse in ipaddress.ip_network(r, strict=False) for r in ips.split(", ") if r)


def creer(id_source: int, nom: str, par: str, test: bool = False, mode: str = "actif", ips: str | None = None) -> dict:
    if mode not in MODES:
        raise CleRefusee("Mode inconnu")
    ips = normaliser_ips(ips)
    n = db.ecrire("SELECT COUNT(*) FROM voicebank.cles_api WHERE id_source = :s AND NOT revoquee", {"s": id_source}).scalar()
    if n >= MAX_CLES:
        raise CleRefusee(f"{MAX_CLES} clés actives au plus par base : révoque d'abord une clé inutilisée.")
    # Clé de test reconnaissable au premier coup d'œil (« vb_test_… ») : jamais d'alerte, jamais comptée
    cle = ("vb_test_" if test else "vb_") + secrets.token_urlsafe(32)
    prefixe = cle[:16 if test else 12]
    r = db.ecrire("INSERT INTO voicebank.cles_api (id_source, nom, prefixe, empreinte, cree_par, test, mode, ips_autorisees) "
                  "VALUES (:s, :n, :p, :e, :c, :t, :m, :i) RETURNING id_cle, date_creation",
                  {"s": id_source, "n": nom.strip()[:80], "p": prefixe, "e": _empreinte(cle), "c": par[:64],
                   "t": test, "m": mode, "i": ips}).lignes[0]
    return {"id": r.id_cle, "nom": nom.strip()[:80], "prefixe": prefixe, "cle": cle, "test": test, "mode": mode,
            "ips_autorisees": ips, "date_creation": r.date_creation.isoformat()}


def modifier(id_source: int, id_cle: int, mode: str | None = None, ips: str | None = None, changer_ips: bool = False) -> dict:
    """Passer de l'observation au blocage réel (ou l'inverse), changer les adresses autorisées."""
    champs, p = [], {"s": id_source, "i": id_cle}
    if mode is not None:
        if mode not in MODES:
            raise CleRefusee("Mode inconnu")
        champs.append("mode = :m"); p["m"] = mode
    if changer_ips:
        champs.append("ips_autorisees = :ips"); p["ips"] = normaliser_ips(ips)
    if champs:
        r = db.ecrire(f"UPDATE voicebank.cles_api SET {', '.join(champs)} WHERE id_source = :s AND id_cle = :i AND NOT revoquee", p)
        if not r.rowcount:
            raise CleRefusee("Clé introuvable")
    c = next((c for c in lister(id_source) if c["id"] == id_cle), None)
    if c is None:
        raise CleRefusee("Clé introuvable")
    return c


def lister(id_source: int) -> list[dict]:
    r = db.ecrire("SELECT id_cle, nom, prefixe, cree_par, date_creation, derniere_utilisation, premiere_utilisation, "
                  "nb_appels, revoquee, mode, test, ips_autorisees, derniere_utilisation > LOCALTIMESTAMP - INTERVAL '10 minutes' AS en_ligne "
                  "FROM voicebank.cles_api WHERE id_source = :s ORDER BY revoquee, date_creation DESC", {"s": id_source}).lignes
    return [{"id": l.id_cle, "nom": l.nom, "prefixe": l.prefixe, "cree_par": l.cree_par,
             "date_creation": l.date_creation.isoformat(),
             "derniere_utilisation": l.derniere_utilisation.isoformat() if l.derniere_utilisation else None,
             "premiere_utilisation": l.premiere_utilisation.isoformat() if l.premiere_utilisation else None,
             "nb_appels": int(l.nb_appels), "revoquee": l.revoquee, "mode": l.mode, "test": l.test,
             "ips_autorisees": l.ips_autorisees, "en_ligne": bool(l.en_ligne) and not l.revoquee}
            for l in r]


def noter_appel(id_cle: int, id_source: int, reponse: dict, montant: float, devise: str, duree_ms: int,
                mode: str = "actif") -> None:
    """Chaque réponse de l'API est gardée 90 jours pour le suivi en direct (pas de donnée personnelle du client)."""
    import json
    # decision : celle de VoiceBank (en observation, la réponse renvoyée était « accepter »)
    db.ecrire("INSERT INTO voicebank.appels_api (id_cle, id_source, reference, montant, devise, decision, niveau, score, "
              "raisons, duree_ms, id_alerte, mode) VALUES (:c, :s, :r, :m, :d, :de, :n, :sc, CAST(:ra AS JSONB), :t, :a, :mo)",
              {"c": id_cle, "s": id_source, "r": (reponse.get("reference") or None), "m": montant, "d": devise,
               "mo": mode, "de": reponse.get("decision_voicebank") or reponse["decision"], "n": reponse["niveau"], "sc": reponse["score"],
               "ra": json.dumps(reponse.get("raisons") or [], ensure_ascii=False), "t": duree_ms, "a": reponse.get("id_alerte")})


def activite(id_source: int, id_cle: int, apres: int = 0) -> dict:
    """Tableau de bord en direct d'un logiciel branché : état, chiffres du jour, 24 dernières heures, derniers appels."""
    cle = next((c for c in lister(id_source) if c["id"] == id_cle), None)
    if cle is None:
        raise CleRefusee("Clé introuvable")
    p = {"c": id_cle}
    j = db.ecrire(
        "SELECT COUNT(*) AS appels, COUNT(*) FILTER (WHERE decision = 'accepter') AS acceptees, "
        "COUNT(*) FILTER (WHERE decision = 'verifier') AS a_verifier, COUNT(*) FILTER (WHERE decision = 'bloquer') AS bloquees, "
        "COALESCE(SUM(montant) FILTER (WHERE decision = 'bloquer'), 0) AS montant_bloque, "
        "COALESCE(SUM(montant) FILTER (WHERE decision = 'verifier'), 0) AS montant_a_verifier, "
        "COALESCE(SUM(montant), 0) AS montant_total, ROUND(AVG(duree_ms)) AS duree_moyenne_ms, "
        "percentile_cont(0.95) WITHIN GROUP (ORDER BY duree_ms) AS duree_p95_ms, "
        "COUNT(*) FILTER (WHERE id_alerte IS NOT NULL) AS alertes "
        "FROM voicebank.appels_api WHERE id_cle = :c AND date_appel >= CURRENT_DATE", p).lignes[0]
    heures = db.ecrire(
        "SELECT date_trunc('hour', date_appel) AS h, decision, COUNT(*) AS n FROM voicebank.appels_api "
        "WHERE id_cle = :c AND date_appel >= date_trunc('hour', LOCALTIMESTAMP) - INTERVAL '23 hours' GROUP BY 1, 2", p).lignes
    maintenant = db.ecrire("SELECT date_trunc('hour', LOCALTIMESTAMP)").scalar()
    from datetime import timedelta
    grille = {maintenant - timedelta(hours=23 - i): {"accepter": 0, "verifier": 0, "bloquer": 0} for i in range(24)}
    for l in heures:
        if l.h in grille and l.decision in grille[l.h]:
            grille[l.h][l.decision] = int(l.n)
    appels = db.ecrire(
        "SELECT id_appel, date_appel, reference, montant, devise, decision, niveau, score, raisons, duree_ms, id_alerte, mode "
        "FROM voicebank.appels_api WHERE id_cle = :c AND id_appel > :a ORDER BY id_appel DESC LIMIT 50",
        {"c": id_cle, "a": apres}).lignes
    return {
        "cle": cle,
        "aujourdhui": {k: (float(v) if k.startswith("montant") or k.startswith("duree") else int(v or 0)) if v is not None else None
                       for k, v in j._mapping.items()},
        "par_heure": [{"heure": h.isoformat(), **v} for h, v in sorted(grille.items())],
        "appels": [{"id": l.id_appel, "date": l.date_appel.isoformat(), "reference": l.reference,
                    "montant": float(l.montant) if l.montant is not None else None, "devise": l.devise,
                    "decision": l.decision, "niveau": l.niveau, "score": float(l.score), "raisons": l.raisons or [],
                    "duree_ms": l.duree_ms, "id_alerte": l.id_alerte, "mode": l.mode} for l in appels],
    }


def revoquer(id_source: int, id_cle: int) -> None:
    r = db.ecrire("UPDATE voicebank.cles_api SET revoquee = TRUE WHERE id_source = :s AND id_cle = :i",
                  {"s": id_source, "i": id_cle})
    if not r.rowcount:
        raise CleRefusee("Clé introuvable")


class IpRefusee(CleRefusee):
    """Clé valide, mais appel depuis une adresse non autorisée (403)."""


def verifier(cle: str, ip: str | None = None) -> dict:
    """{source, nom (compte au nom duquel lire la base), id_cle, mode, test} ; lève CleRefusee sinon. Compte l'appel."""
    if not cle or not cle.startswith("vb_") or len(cle) > 80:
        raise CleRefusee("Clé d'API absente ou invalide.")
    r = db.ecrire(
        "SELECT k.id_cle, k.id_source, k.revoquee, k.cree_par AS nom, k.mode, k.test, k.ips_autorisees, "
        "(SELECT actif FROM voicebank.utilisateurs WHERE nom = k.cree_par) AS actif, "
        f"(SELECT {_SQL_ACCES_EXPIRE} FROM voicebank.utilisateurs WHERE nom = k.cree_par) AS expire "
        "FROM voicebank.cles_api k WHERE k.empreinte = :e", {"e": _empreinte(cle)}).lignes
    if not r or r[0].revoquee or not r[0].actif:
        raise CleRefusee("Clé d'API absente ou invalide.")
    if r[0].expire:
        raise CleRefusee("Abonnement échu : renouvelle-le pour continuer à utiliser l'API.")
    if not ip_autorisee(ip or "", r[0].ips_autorisees):
        raise IpRefusee(f"Adresse IP non autorisée pour cette clé : {(ip or '?')[:64]}. Ajoute-la dans VoiceBank → API.")
    db.ecrire("UPDATE voicebank.cles_api SET nb_appels = nb_appels + 1, derniere_utilisation = LOCALTIMESTAMP, "
              "premiere_utilisation = COALESCE(premiere_utilisation, LOCALTIMESTAMP) WHERE id_cle = :i", {"i": r[0].id_cle})
    return {"source": r[0].id_source, "nom": r[0].nom, "id_cle": r[0].id_cle, "mode": r[0].mode, "test": r[0].test}
