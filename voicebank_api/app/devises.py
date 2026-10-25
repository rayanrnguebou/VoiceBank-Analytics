"""Monnaies d'affichage. Les données sont stockées en FCFA (XAF) ; l'utilisateur choisit la monnaie
dans laquelle il veut lire les montants (réponses, résumés parlés, graphiques, tarifs…).

* FCFA CEMAC (XAF) et FCFA UEMOA (XOF) : parité fixe 1 = 1, et 1 € = 655,957 FCFA (parité officielle) ;
* autres monnaies : taux de référence de la Banque centrale européenne (via frankfurter.app), mis en
  cache 12 h ; sans réseau, des taux indicatifs sont utilisés et signalés comme tels.
"""
import logging
import re
import threading
import time

import httpx

log = logging.getLogger("voicebank")

XAF_PAR_EUR = 655.957
DEVISES = {
    "XAF": {"libelle": "FCFA", "nom": "Franc CFA (CEMAC)", "en_toutes_lettres": "FCFA", "decimales": 0},
    "XOF": {"libelle": "FCFA", "nom": "Franc CFA (UEMOA)", "en_toutes_lettres": "FCFA", "decimales": 0},
    "EUR": {"libelle": "€", "nom": "Euro", "en_toutes_lettres": "euros", "decimales": 2},
    "USD": {"libelle": "$", "nom": "Dollar américain", "en_toutes_lettres": "dollars", "decimales": 2},
    "GBP": {"libelle": "£", "nom": "Livre sterling", "en_toutes_lettres": "livres sterling", "decimales": 2},
    "CAD": {"libelle": "$ CA", "nom": "Dollar canadien", "en_toutes_lettres": "dollars canadiens", "decimales": 2},
    "CHF": {"libelle": "CHF", "nom": "Franc suisse", "en_toutes_lettres": "francs suisses", "decimales": 2},
    "CNY": {"libelle": "¥", "nom": "Yuan chinois", "en_toutes_lettres": "yuans", "decimales": 2},
    "NGN": {"libelle": "₦", "nom": "Naira nigérian", "en_toutes_lettres": "nairas", "decimales": 0},
}
# Unités de monnaie étrangère pour 1 € (repli si la BCE est injoignable)
INDICATIFS_PAR_EUR = {"USD": 1.08, "GBP": 0.85, "CAD": 1.48, "CHF": 0.95, "CNY": 7.8, "NGN": 1650.0}
_cache = {"taux": None, "date": None, "source": "indicatif", "maj": 0.0}
_verrou = threading.Lock()


def _actualiser():
    """Taux BCE (base euro), au plus une fois toutes les 12 h."""
    if _cache["taux"] is not None and time.time() - _cache["maj"] < 12 * 3600:
        return
    with _verrou:
        if _cache["taux"] is not None and time.time() - _cache["maj"] < 12 * 3600:
            return
        codes = ",".join(c for c in INDICATIFS_PAR_EUR if c != "NGN")       # la BCE ne publie pas le naira
        try:
            r = httpx.get(f"https://api.frankfurter.app/latest?from=EUR&to={codes}", timeout=5)
            r.raise_for_status()
            data = r.json()
            _cache.update(taux={**INDICATIFS_PAR_EUR, **{k: float(v) for k, v in data["rates"].items()}},
                          date=data.get("date"), source="BCE")
        except Exception as e:
            log.info("Taux de change BCE indisponibles (%s) : taux indicatifs utilisés", e)
            _cache.update(taux=dict(INDICATIFS_PAR_EUR), date=None, source="indicatif")
        _cache["maj"] = time.time()


def taux(devise: str) -> float:
    """Unités de `devise` pour 1 FCFA."""
    devise = (devise or "XAF").upper()
    if devise in ("XAF", "XOF"):
        return 1.0
    if devise == "EUR":
        return 1 / XAF_PAR_EUR
    if devise not in DEVISES:
        raise ValueError(f"Monnaie non prise en charge : {devise}")
    _actualiser()
    return _cache["taux"][devise] / XAF_PAR_EUR


def convertir(montant, de: str = "XAF", vers: str = "XAF"):
    if montant is None or not isinstance(montant, (int, float)) or isinstance(montant, bool):
        return montant
    if (de or "XAF").upper() == (vers or "XAF").upper():
        return montant
    v = montant / taux(de) * taux(vers)
    d = DEVISES[(vers or "XAF").upper()]["decimales"]
    return round(v) if d == 0 else round(v, d)


def liste() -> dict:
    _actualiser()
    return {"devises": [{"code": c, **d, "taux_par_fcfa": taux(c)} for c, d in DEVISES.items()],
            "source": "fixe (parité officielle) et " + ("BCE" if _cache["source"] == "BCE" else "indicatif"),
            "date": _cache["date"]}


# ── Colonnes monétaires (base VoiceBank et noms courants) ──────────────
_MOTS_MONETAIRES = {"montant", "solde", "fcfa", "xaf", "volume", "encours", "revenu", "mensualite", "prix", "cout",
                    "amount", "balance", "principal", "price", "cost", "salaire", "salary", "income", "depot",
                    "retrait", "valeur", "total", "capital", "frais", "fee", "fees", "premium", "prime", "ca"}
_MOTS_NON_MONETAIRES = {"nb", "nombre", "count", "taux", "rate", "pct", "score", "id", "duree", "age", "jours",
                        "mois", "annee", "probabilite", "proba"}


def est_colonne_monetaire(nom: str) -> bool:
    mots = set(re.split(r"[^a-z0-9]+", str(nom).lower()))
    if mots & _MOTS_NON_MONETAIRES:
        return False
    return bool(mots & _MOTS_MONETAIRES)


def convertir_lignes(colonnes: list[str], lignes: list[dict], vers: str, de: str = "XAF",
                     monetaires: set[str] | None = None) -> tuple[list[dict], list[str]]:
    """Convertit les colonnes monétaires. Retourne (lignes, colonnes converties)."""
    cibles = [c for c in colonnes if (c.lower() in monetaires if monetaires is not None else est_colonne_monetaire(c))]
    cibles = [c for c in cibles if any(isinstance(l.get(c), (int, float)) and not isinstance(l.get(c), bool) for l in lignes)]
    if not cibles or (de or "XAF").upper() == (vers or "XAF").upper():
        return lignes, cibles
    return [{**l, **{c: convertir(l.get(c), de, vers) for c in cibles}} for l in lignes], cibles


def detecter_devise(profil: dict) -> str | None:
    """Monnaie d'une base connectée, d'après une colonne « currency / devise » (valeur dominante)."""
    for t in profil.get("tables", []):
        for c in t.get("colonnes", []):
            if set(re.split(r"[^a-z]+", c["nom"].lower())) & {"currency", "devise", "monnaie", "ccy"}:
                for v in c.get("valeurs") or []:
                    code = str(v["valeur"]).strip().upper()
                    code = {"FCFA": "XAF", "CFA": "XAF", "€": "EUR", "$": "USD"}.get(code, code)
                    if code in DEVISES:
                        return code
    return None
