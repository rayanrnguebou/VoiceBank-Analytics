"""Masquage des données personnelles pour le rôle analyste.

Un analyste voit les chiffres et les identifiants techniques (CLI-000123), pas l'identité
des clients. Seul l'administrateur voit les noms en clair.
"""
import re

_MOTS_PERSONNELS = {"nom", "prenom", "telephone", "tel", "email", "mail", "naissance", "adresse"}


def est_colonne_personnelle(colonne: str) -> bool:
    mots = set(re.split(r"[^a-z]+", colonne.lower()))
    return bool(mots & _MOTS_PERSONNELS) or {"numero", "compte"} <= mots


def masquer_valeur(colonne: str, valeur):
    if valeur is None:
        return None
    s, c = str(valeur), colonne.lower()
    if "mail" in c and "@" in s:
        return s[0] + "***@" + s.split("@", 1)[1]
    if "tel" in c:
        return "*** ** ** " + s[-2:]
    if "compte" in c:
        return "****" + s[-4:]
    if "naissance" in c:
        return s[:4] + "-**-**"
    return (s[0] + "***") if s else s


def masquer_lignes(colonnes: list[str], lignes: list[dict], role: str) -> list[dict]:
    if role == "admin":
        return lignes
    a_masquer = [c for c in colonnes if est_colonne_personnelle(c)]
    if not a_masquer:
        return lignes
    return [{**l, **{c: masquer_valeur(c, l.get(c)) for c in a_masquer}} for l in lignes]


def masquer_ligne(ligne: dict, role: str) -> dict:
    return masquer_lignes(list(ligne.keys()), [ligne], role)[0]
