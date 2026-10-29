"""Langue des réponses de l'API : français (texte de référence, écrit dans le code) ou anglais.

La langue vient de l'en-tête Accept-Language envoyé par l'interface (« en » ou « fr »). Les textes destinés à
l'utilisateur ne sont pas réécrits un par un : les réponses JSON, les messages d'erreur, les e-mails et les rapports
PDF passent par `traduire`, qui reconnaît chaque phrase française du dictionnaire `traductions/en.json`, y compris
quand elle contient des valeurs variables (gabarits « {nom} » : « Serveur introuvable : {hote} »).

Les valeurs codées (niveaux « Critique », statuts…) ne sont pas dans le dictionnaire : elles restent identiques pour
que l'interface puisse filtrer dessus ; c'est elle qui les affiche traduites.
"""
import contextvars
import json
import re
from functools import lru_cache
from pathlib import Path

LANGUES = ("fr", "en")
_langue: contextvars.ContextVar[str] = contextvars.ContextVar("langue", default="fr")
_PLACE = re.compile(r"\{(\w+)\}")


def langue() -> str:
    return _langue.get()


def definir(code: str | None):
    """Fixe la langue du contexte courant (requête, tâche) ; retourne le jeton pour revenir en arrière."""
    return _langue.set(code if code in LANGUES else "fr")


def depuis_entete(valeur: str | None) -> str:
    """« en-GB,en;q=0.9 » → en ; tout le reste → fr."""
    premiere = (valeur or "").split(",")[0].strip().lower()
    return "en" if premiere.startswith("en") else "fr"


@lru_cache(maxsize=1)
def _dictionnaire():
    brut = json.loads((Path(__file__).parent / "traductions" / "en.json").read_text(encoding="utf-8"))
    mots = brut.pop("__mots__", {})          # mots seulement traduits à l'intérieur d'une phrase connue
    titres = brut.pop("__titres__", {})      # titres de graphiques et d'indicateurs (« X par Y ») : champ « titre » seulement
    exact, gabarits, sans_prefixe = {}, {}, []
    for fr, en in brut.items():
        if not _PLACE.search(fr):
            exact[fr] = en
            continue
        morceaux, vus = [], set()
        pos = 0
        for m in _PLACE.finditer(fr):
            morceaux.append(re.escape(fr[pos:m.start()]))
            nom = m.group(1)
            morceaux.append(f"(?P=g_{nom})" if nom in vus else f"(?P<g_{nom}>.+?)")
            vus.add(nom)
            pos = m.end()
        morceaux.append(re.escape(fr[pos:]))
        motif = re.compile("^" + "".join(morceaux) + "$", re.S)
        prefixe = fr[:fr.index("{")]
        entree = (motif, en, len(_PLACE.sub("", fr)))
        if len(prefixe) >= 3:
            gabarits.setdefault(prefixe[:3], []).append(entree)
        else:
            sans_prefixe.append(entree)
    for liste in [*gabarits.values(), sans_prefixe]:
        liste.sort(key=lambda e: -e[2])          # le gabarit le plus précis d'abord
    return exact, gabarits, sans_prefixe, mots, _compiler_titres(titres)


def _compiler_titres(titres: dict) -> list:
    res = []
    for fr, en in titres.items():
        motif = "^" + _PLACE.sub(lambda m: f"(?P<g_{m.group(1)}>.+?)", re.escape(fr).replace(r"\{", "{").replace(r"\}", "}")) + "$"
        res.append((re.compile(motif, re.S), en, len(_PLACE.sub("", fr))))
    res.sort(key=lambda e: -e[2])                             # le titre le plus précis (le plus de texte fixe) d'abord
    res = [(m, en) for m, en, _ in res]
    return res


def traduire_titre(texte: str, code: str | None = None) -> str:
    code = code or _langue.get()
    if code != "en" or not isinstance(texte, str):
        return texte
    exact, _, _, mots, titres = _dictionnaire()
    for motif, en in titres:
        m = motif.match(texte)
        if m:
            vals = {k[2:]: mots.get(v, mots.get(v.lower(), v)) for k, v in m.groupdict().items()}
            return _PLACE.sub(lambda x: vals.get(x.group(1), x.group(0)), en)
    return traduire(texte, code)


def traduire(texte, code: str | None = None, _profondeur: int = 0):
    """Texte dans la langue demandée (ou celle du contexte). Inchangé si inconnu du dictionnaire."""
    code = code or _langue.get()
    if code != "en" or not isinstance(texte, str) or len(texte) < 2:
        return texte
    exact, gabarits, sans_prefixe, mots, _ = _dictionnaire()
    if texte in exact:
        return exact[texte]
    nu = texte.strip()
    if nu != texte and nu in exact:                          # espaces autour conservés
        debut = texte[:len(texte) - len(texte.lstrip())]
        return debut + exact[nu] + texte[len(texte.rstrip()):]
    for motif, en, _ in gabarits.get(texte[:3], []) + sans_prefixe:
        m = motif.match(texte)
        if m:
            valeurs = {k[2:]: (mots.get(v.strip()) or (traduire(v, code, _profondeur + 1) if _profondeur < 2 else v))
                       for k, v in m.groupdict().items()}
            return _PLACE.sub(lambda x: valeurs.get(x.group(1), x.group(0)), en)
    return texte


def mot(valeur, code: str | None = None):
    """Valeur codée (niveau « Critique », statut « Fraude confirmée »…) traduite pour l'affichage (PDF, e-mails)."""
    code = code or _langue.get()
    if code != "en" or not isinstance(valeur, str):
        return valeur
    exact, _, _, mots, _ = _dictionnaire()
    return mots.get(valeur) or exact.get(valeur) or valeur


CLES_INTOUCHABLES = {"sql", "requete", "access_token", "jeton_2fa", "token", "url", "email", "utilisateur",
                     "code", "id", "role", "role_org", "statut", "niveau_risque", "niveau", "valeur",
                     "verificateur", "secret", "uri", "qr_svg", "codes_secours", "decision", "colonne", "table"}


def traduire_objet(o, code: str | None = None, cle: str | None = None):
    """Traduit récursivement les textes d'une réponse JSON (jamais les clés ni les champs techniques)."""
    code = code or _langue.get()
    if code != "en":
        return o
    if isinstance(o, str):
        if cle in CLES_INTOUCHABLES:
            return o
        return traduire_titre(o, code) if cle in ("titre", "sous_titre", "libelle") else traduire(o, code)
    if isinstance(o, dict):
        return {k: traduire_objet(v, code, k) for k, v in o.items()}
    if isinstance(o, list):
        return [traduire_objet(v, code, cle) for v in o]
    return o
