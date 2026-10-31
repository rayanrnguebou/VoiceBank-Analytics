"""Questions sur la structure des données (« quelles tables ? », « que contient la base ? »).

Sans ce raccourci, l'IA écrit une requête sur `information_schema`, que la garde SQL refuse à juste titre
(tables système). On répond donc à partir du profil déjà calculé de la base : tables consultables,
nombre de lignes et colonnes, sans jamais citer les colonnes secrètes (mots de passe, jetons…).
"""
import re
import unicodedata

_MOTIFS = re.compile(
    r"\b(quel(le)?s?\s+(sont\s+les\s+)?(tables?|colonnes?|champs)"
    r"|(liste|lister|affiche|montre|donne)(\s*-?\s*moi)?\s+(la\s+liste\s+des\s+|les\s+|des\s+)?(tables?|colonnes?|champs)"
    r"|(structure|schema|contenu|organisation)\s+(de\s+la\s+|des\s+)?(base|donnees|bdd)"
    r"|que\s+contient\s+(la\s+base|les\s+donnees)"
    r"|quel(le)?s?\s+(donnees|informations)\s+(as\s*-?\s*tu|avez\s*-?\s*vous|sont\s+disponibles|contient|y\s+a\s*-?\s*t\s*-?\s*il)"
    r"|information_schema"
    r"|what\s+(tables|columns|data)|list\s+(the\s+)?(tables|columns)|database\s+(schema|structure))\b"
)


def _simplifier(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"\s+", " ", t.replace("'", " ")).strip()


def est_question_structure(question: str) -> bool:
    return bool(_MOTIFS.search(_simplifier(question)))


def reponse(profil: dict, question: str, nom_base: str) -> dict:
    """Résultat au même format qu'une réponse SQL : une ligne par table consultable."""
    lignes = []
    for t in profil.get("tables", []):
        if t.get("erreur"):
            continue
        colonnes = [c["nom"] for c in t.get("colonnes", []) if c.get("role") != "secret"]
        lignes.append({"table": t["nom"], "nb_lignes": int(t.get("lignes") or 0),
                       "colonnes": ", ".join(colonnes)})
    noms = ", ".join(l["table"] for l in lignes)
    resume = (f"« {nom_base} » contient {len(lignes)} table{'s' if len(lignes) > 1 else ''} "
              f"consultable{'s' if len(lignes) > 1 else ''} : {noms}." if lignes
              else f"Aucune table consultable dans « {nom_base} ».")
    exemples = profil.get("suggestions") or []
    relance = ({"texte": f"Veux-tu voir aussi : {exemples[0][0].lower() + exemples[0][1:]} ?", "question": exemples[0]}
               if exemples else None)
    return {"status": "ok", "question": question, "sql": None, "source": "rule", "avertissement": None,
            "colonnes": ["table", "nb_lignes", "colonnes"], "total": len(lignes), "data": lignes,
            "resume": resume, "resume_source": "local",
            "commentaire": "Les tables internes du système ne sont jamais accessibles.",
            "relance": relance, "suite": False, "colonnes_monetaires": []}
