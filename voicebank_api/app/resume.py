"""Résumé en une ou deux phrases du résultat d'une question (lu à voix haute par l'interface).

* Avec Gemini : résumé rédigé à partir des colonnes NON personnelles et d'un extrait limité.
* Sans Gemini : résumé local calculé (nombre de résultats, totaux, élément en tête).
"""
import json
import logging

from . import config
from .masquage import est_colonne_personnelle

log = logging.getLogger("voicebank")

_INDICES_NUMERIQUES = ("nb_", "nombre", "total", "montant", "solde", "volume", "count", "somme",
                       "moyen", "taux", "score", "encours")
_INDICES_CATEGORIES = ("banque", "ville", "pays", "type", "statut", "canal", "niveau", "mois",
                       "categorie", "profession", "garantie", "devise", "annee", "tranche")


def formater_nombre(v) -> str:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    signe, x = ("-" if x < 0 else ""), abs(x)
    if x >= 1e9:
        return f"{signe}{x / 1e9:.1f} milliards".replace(".", ",")
    if x >= 1e6:
        return f"{signe}{x / 1e6:.1f} millions".replace(".", ",")
    if x == int(x):
        return signe + f"{int(x):,}".replace(",", " ")
    return signe + f"{x:,.2f}".replace(",", " ").replace(".", ",")


def _unite(colonne: str) -> str:
    c = colonne.lower()
    if "fcfa" in c or "montant" in c or "solde" in c or "volume" in c or "encours" in c:
        return " FCFA"
    if "taux" in c or "pct" in c:
        return " %"
    return ""


def _colonne_numerique(colonnes, lignes):
    nums = [c for c in colonnes if all(isinstance(l.get(c), (int, float)) or l.get(c) is None for l in lignes)
            and any(isinstance(l.get(c), (int, float)) for l in lignes) and not c.lower().startswith("id")]
    for indice in _INDICES_NUMERIQUES:
        for c in nums:
            if indice in c.lower():
                return c
    return nums[0] if nums else None


def _colonne_categorie(colonnes, lignes):
    for indice in _INDICES_CATEGORIES:
        for c in colonnes:
            if indice in c.lower() and not est_colonne_personnelle(c):
                return c
    return None


def resume_local(question: str, colonnes: list[str], lignes: list[dict]) -> str:
    n = len(lignes)
    if n == 0:
        return "Aucun résultat ne correspond à cette question."
    num = _colonne_numerique(colonnes, lignes)
    if n == 1:
        parties = [f"{c.replace('_', ' ')} : {formater_nombre(v)}{_unite(c)}"
                   for c, v in lignes[0].items() if not est_colonne_personnelle(c) and v is not None
                   and not c.lower().startswith("id")][:4]
        return ("Résultat : " + ", ".join(parties) + ".") if parties else "Un seul résultat trouvé."
    cat = _colonne_categorie(colonnes, lignes)
    phrase = f"{formater_nombre(n)} résultats."
    liste_detaillee = any(c.lower().startswith("id_") for c in colonnes)   # une ligne = un élément
    if liste_detaillee and num:
        valeurs = [l[num] for l in lignes if isinstance(l.get(num), (int, float))]
        if valeurs and any(m in num.lower() for m in ("montant", "solde", "volume")):
            phrase += f" Montant total : {formater_nombre(sum(valeurs))} FCFA"
            phrase += f", le plus élevé : {formater_nombre(max(valeurs))} FCFA."
        return phrase
    if cat and num and n <= 50:
        tri = sorted((l for l in lignes if l.get(num) is not None), key=lambda l: l[num], reverse=True)
        if tri:
            phrase += (f" En tête : {tri[0][cat]} avec {formater_nombre(tri[0][num])}{_unite(num)}"
                       f" ({num.replace('_', ' ')})")
            if len(tri) > 1:
                phrase += f", suivi de {tri[1][cat]} ({formater_nombre(tri[1][num])}{_unite(num)})"
            phrase += "."
    elif num and any(m in num.lower() for m in ("montant", "solde", "volume")):
        total = sum(l[num] for l in lignes if isinstance(l.get(num), (int, float)))
        phrase += f" Montant total : {formater_nombre(total)} FCFA."
    return phrase


def resume_gemini(question: str, colonnes: list[str], lignes: list[dict]) -> str | None:
    from .nl2sql import client_gemini
    client = client_gemini()
    if client is None:
        return None
    sures = [c for c in colonnes if not est_colonne_personnelle(c)]
    extrait = [{c: l.get(c) for c in sures} for l in lignes[:30]]
    prompt = (
        "Tu es l'assistant vocal d'une banque. Résume en UNE ou DEUX phrases courtes, en français, "
        "le résultat ci-dessous pour un analyste bancaire. Donne les chiffres clés arrondis (FCFA, %, "
        "millions/milliards en toutes lettres), sans jargon technique, sans parler de SQL, sans "
        "inventer de chiffre absent des données. Le texte sera lu à voix haute.\n\n"
        f"Question : <<<{question}>>>\nNombre total de lignes : {len(lignes)}\n"
        f"Extrait (30 lignes max) : {json.dumps(extrait, ensure_ascii=False, default=str)[:6000]}\n\nRésumé :")
    try:
        rep = client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt)
        texte = (rep.text or "").strip().replace("\n", " ")
        return texte[:600] or None
    except Exception as e:
        log.warning("Résumé Gemini impossible : %s", e)
        return None


def resumer(question: str, colonnes: list[str], lignes: list[dict]) -> tuple[str, str]:
    """Retourne (résumé, source) avec source = 'gemini' ou 'local'."""
    if lignes:
        texte = resume_gemini(question, colonnes, lignes)
        if texte:
            return texte, "gemini"
    return resume_local(question, colonnes, lignes), "local"
