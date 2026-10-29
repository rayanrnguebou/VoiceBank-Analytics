"""Mode maintenance et annonces, réglés depuis l'administration (sans redéploiement).

* **Maintenance active** : toutes les routes répondent 503 avec le message choisi, sauf pour l'administrateur
  de la plateforme (qui peut se connecter et travailler) et quelques routes publiques (santé, état).
  En secours, la variable d'environnement MAINTENANCE=true l'active même si la base est indisponible.
* **Annonce** : bandeau « maintenance prévue » affiché à tous avant l'intervention.
L'état est gardé dans voicebank.parametres et relu toutes les 15 secondes au plus.
"""
import json
import logging
import time
from datetime import datetime, timedelta

from . import config, db

log = logging.getLogger("voicebank")

CLE = "maintenance"
MESSAGE_DEFAUT = ("VoiceBank Analytics est en maintenance pour une mise à jour. Le service revient très vite : "
                  "merci de votre patience.")
_cache = {"etat": None, "date": 0.0}
VIDE = {"active": False, "message": MESSAGE_DEFAUT, "fin_prevue": None,
        "annonce": None, "modifie_par": None, "date_modif": None}


def _env_active() -> bool:
    return config._env("MAINTENANCE", "false").lower() == "true"


def etat(force: bool = False) -> dict:
    if not force and _cache["etat"] is not None and time.time() - _cache["date"] < 15:
        e = _cache["etat"]
    else:
        e = dict(VIDE)
        try:
            r = db.ecrire("SELECT valeur, modifie_par, date_modif FROM voicebank.parametres WHERE cle = :c", {"c": CLE})
            if r.lignes:
                v = r.lignes[0].valeur or {}
                e.update({k: v.get(k, e[k]) for k in ("active", "message", "fin_prevue", "annonce")},
                         modifie_par=r.lignes[0].modifie_par, date_modif=r.lignes[0].date_modif.isoformat())
        except Exception as ex:          # base indisponible : on garde le dernier état connu
            log.debug("Lecture de l'état de maintenance impossible : %s", ex)
            if _cache["etat"] is not None:
                e = _cache["etat"]
        _cache.update(etat=e, date=time.time())
    if _env_active():
        e = {**e, "active": True}
    # Annonce périmée : n'est plus affichée
    a = e.get("annonce")
    if a and a.get("fin"):
        try:
            # Heures saisies dans le fuseau de l'administrateur (le serveur est en UTC) : l'interface masque
            # l'annonce à l'heure exacte ; ici, on la retire au plus tard 14 h après (tous fuseaux confondus).
            if datetime.fromisoformat(a["fin"]) + timedelta(hours=14) < datetime.now():
                e = {**e, "annonce": None}
        except ValueError:
            pass
    return e


def derniere_connue() -> bool:
    """Maintenance active d'après le dernier état lu (sans interroger la base : sondes de santé)."""
    return bool((_cache["etat"] or {}).get("active")) or _env_active()


def public() -> dict:
    e = etat()
    return {"active": e["active"], "message": e["message"] or MESSAGE_DEFAUT, "fin_prevue": e["fin_prevue"],
            "annonce": e["annonce"]}


def modifier(par: str, active: bool, message: str | None, fin_prevue: str | None, annonce: dict | None) -> dict:
    valeur = {"active": bool(active), "message": (message or "").strip()[:500] or MESSAGE_DEFAUT,
              "fin_prevue": fin_prevue or None, "annonce": annonce or None}
    db.ecrire("INSERT INTO voicebank.parametres (cle, valeur, modifie_par, date_modif) "
              "VALUES (:c, CAST(:v AS JSONB), :p, LOCALTIMESTAMP) ON CONFLICT (cle) DO UPDATE SET "
              "valeur = EXCLUDED.valeur, modifie_par = EXCLUDED.modifie_par, date_modif = EXCLUDED.date_modif",
              {"c": CLE, "v": json.dumps(valeur, ensure_ascii=False), "p": par})
    return etat(force=True)


# Routes toujours accessibles pendant la maintenance
OUVERTES = ("/health", "/maintenance", "/auth/login", "/auth/options", "/auth/moi", "/auth/renouveler",
            "/devises", "/abonnement/formules", "/paiements/notchpay/webhook", "/docs", "/openapi.json")
