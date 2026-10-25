"""Résumé du résultat d'une question, puis commentaire plus poussé (conseils, interprétation).
L'interface lit le résumé à voix haute, puis enchaîne sur le commentaire, qui n'est pas affiché.

* Avec Gemini : résumé rédigé à partir des colonnes NON personnelles et d'un extrait limité.
* Sans Gemini : résumé local calculé (nombre de résultats, totaux, élément en tête).
"""
import json
import logging
from contextvars import ContextVar

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
    if x == int(x) or x >= 1000:          # pas de centimes à l'oral au-delà de 1 000
        return signe + f"{round(x):,}".replace(",", " ")
    return signe + f"{x:,.2f}".replace(",", " ").replace(".", ",")


# Monnaie d'affichage de la requête en cours (les montants reçus sont déjà convertis)
MONNAIE = ContextVar("monnaie", default="FCFA")


def _unite(colonne: str) -> str:
    from .devises import est_colonne_monetaire
    c = colonne.lower()
    if est_colonne_monetaire(c) or "fcfa" in c:
        return " " + MONNAIE.get()
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
    if cat is None and num and len(colonnes) <= 4:
        # Colonnes aux noms inconnus (bases connectées) : la première colonne qui n'est pas la mesure
        cat = next((c for c in colonnes if c != num and not est_colonne_personnelle(c)
                    and c.lower() not in ("annee", "mois")), None)
    phrase = f"{formater_nombre(n)} résultats."
    liste_detaillee = any(c.lower().startswith("id_") for c in colonnes)   # une ligne = un élément
    if liste_detaillee and num:
        valeurs = [l[num] for l in lignes if isinstance(l.get(num), (int, float))]
        if valeurs and any(m in num.lower() for m in ("montant", "solde", "volume")):
            phrase += f" Montant total : {formater_nombre(sum(valeurs))} {MONNAIE.get()}"
            phrase += f", le plus élevé : {formater_nombre(max(valeurs))} {MONNAIE.get()}."
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
        phrase += f" Montant total : {formater_nombre(total)} {MONNAIE.get()}."
    return phrase


# ── Commentaire vocal : explication plus poussée, lue APRÈS le résumé (jamais affichée) ──

_CONSEILS_THEMES = [
    (("fraud", "alerte", "suspect"),
     "Côté risque, traite en priorité les alertes critiques encore ouvertes, et regarde de près les "
     "opérations de nuit et internationales : ce sont elles qui concentrent le plus de fraudes."),
    (("défaut", "defaut", "impay", "retard"),
     "Pour limiter les pertes, compare la mensualité au revenu de ces emprunteurs : au-delà d'un tiers, "
     "le risque grimpe vite. La page Score de crédit t'explique dossier par dossier ce qui pèse."),
    (("crédit", "credit", "prêt", "pret", "encours"),
     "Pense à croiser ce résultat avec les retards de paiement : un encours élevé n'est un problème "
     "que s'il est mal remboursé."),
    (("diaspora",),
     "La diaspora est un relais de croissance : transferts réguliers, épargne en devises. Une offre "
     "dédiée, avec des frais de transfert réduits, peut fidéliser ces clients."),
    (("solde", "top", "meilleur", "plus riche"),
     "Ces clients à forte valeur méritent un suivi personnalisé : un conseiller attitré limite le "
     "risque qu'ils partent à la concurrence."),
    (("transaction", "volume", "canal", "mobile"),
     "Surveille la part du mobile money dans ces volumes : c'est le canal qui croît le plus vite, "
     "mais aussi celui où la fraude évolue le plus."),
]


def _part(x, total):
    return round(100 * x / total) if total else 0


def commentaire_local(question: str, colonnes: list[str], lignes: list[dict]) -> str:
    """Interprétation simple et conseils, calculés sans IA."""
    q = (question + " " + " ".join(colonnes)).lower()
    phrases = []
    if not lignes:
        return ("Aucune donnée ne correspond. Essaie d'élargir la période ou de retirer un filtre, "
                "et vérifie l'orthographe du nom de la ville ou de la banque.")
    num = _colonne_numerique(colonnes, lignes)
    cat = _colonne_categorie(colonnes, lignes)
    temporel = next((c for c in colonnes if any(t in c.lower() for t in ("mois", "annee", "année", "date"))), None)
    valeurs = [l for l in lignes if isinstance(l.get(num), (int, float))] if num else []

    if temporel and num and len(valeurs) >= 3:
        serie = sorted(valeurs, key=lambda l: str(l[temporel]))
        premier, dernier = serie[0][num], serie[-1][num]
        if premier:
            evol = round(100 * (dernier - premier) / abs(premier))
            sens = "une hausse" if evol > 0 else "une baisse" if evol < 0 else "une stabilité"
            phrases.append(f"Sur la période, on observe {sens} de {abs(evol)} % entre le début et la fin.")
        pic = max(serie, key=lambda l: l[num])
        phrases.append(f"Le point le plus haut est atteint en {pic[temporel]}.")
    elif cat and num and len(valeurs) >= 2:
        tri = sorted(valeurs, key=lambda l: l[num], reverse=True)
        total = sum(l[num] for l in tri)
        part = _part(tri[0][num], total)
        if part >= 40:
            phrases.append(f"{tri[0][cat]} pèse à lui seul {part} % du total : c'est une forte concentration, "
                           f"donc une dépendance à surveiller.")
        elif part <= 100 / len(tri) * 1.5:
            phrases.append("La répartition est assez équilibrée, aucun élément ne domine vraiment.")
        else:
            phrases.append(f"{tri[0][cat]} arrive en tête avec {part} % du total.")
        if tri[-1][num] and len(tri) >= 3:
            ecart = tri[0][num] / tri[-1][num]
            if ecart >= 3:
                phrases.append(f"L'écart est important : le premier fait {formater_nombre(round(ecart, 1))} fois "
                               f"plus que le dernier, {tri[-1][cat]}.")
    elif len(lignes) == 1 and num:
        phrases.append("C'est un indicateur unique : pour l'interpréter, compare-le au mois précédent "
                       "ou à une autre banque.")
    elif len(lignes) >= 50:
        phrases.append("La liste est longue : affine-la avec un filtre, par ville ou par banque, "
                       "pour faire ressortir les cas prioritaires.")

    for mots, conseil in _CONSEILS_THEMES:
        if any(m in q for m in mots):
            phrases.append(conseil)
            break
    return " ".join(phrases[:4]) or "Ouvre le graphique pour explorer le détail de ce résultat."


# ── Relance : question posée à l'oral à la fin, à laquelle on répond de vive voix ──
# Questions de suivi que les règles locales savent traiter sans IA.
_SUIVIS = [
    (("fraud", "alerte", "suspect"), "Veux-tu voir les alertes critiques encore à traiter ?", "Alertes critiques"),
    (("défaut", "defaut", "crédit", "credit", "prêt", "pret"),
     "Veux-tu que je te liste les crédits en défaut ?", "Crédits en défaut"),
    (("solde", "client", "diaspora"), "Veux-tu voir les dix clients qui ont le plus gros solde ?",
     "Top 10 clients par solde"),
    (("transaction", "volume", "ville", "canal"), "Veux-tu voir les transactions frauduleuses par banque ?",
     "Transactions frauduleuses par banque"),
]
RELANCE_OUVERTE = "As-tu une autre question ?"


def relance_locale(question: str) -> dict:
    q = question.lower()
    for mots, texte, suivante in _SUIVIS:
        if any(m in q for m in mots) and suivante.lower() not in q:
            return {"texte": texte, "question": suivante}
    return {"texte": RELANCE_OUVERTE, "question": None}


def _relance(texte, question) -> dict | None:
    texte = str(texte or "").strip().replace("\n", " ")[:200]
    if not texte:
        return None
    if not texte.endswith("?"):
        texte = texte.rstrip(" .!") + " ?"
    question = str(question or "").strip()[:300] or None
    return {"texte": texte, "question": question}


def resume_gemini(question: str, colonnes: list[str], lignes: list[dict]) -> dict | None:
    """Un seul appel Gemini : résumé, commentaire et relance."""
    from .nl2sql import client_gemini
    client = client_gemini()
    if client is None:
        return None
    sures = [c for c in colonnes if not est_colonne_personnelle(c)]
    extrait = [{c: l.get(c) for c in sures} for l in lignes[:30]]
    prompt = (
        f"Tu es l'assistant vocal d'une banque en Afrique centrale (montants exprimés en {MONNAIE.get()}). Tu réponds à un "
        "analyste bancaire. Les textes seront lus à voix haute : phrases courtes, pas de listes, "
        "pas de symboles, nombres arrondis (millions/milliards en toutes lettres), jamais de SQL.\n"
        "Réponds UNIQUEMENT avec un objet JSON contenant ces clés :\n"
        '- "resume" : une ou deux phrases avec les chiffres clés du résultat ;\n'
        '- "commentaire" : trois à cinq phrases qui vont PLUS LOIN que le résumé, sans le répéter : '
        "ce que le résultat révèle (concentration, écarts, tendance, anomalies), les risques ou "
        "opportunités pour la banque, une ou deux actions concrètes à mener. Ne termine PAS par une "
        "question. N'invente aucun chiffre absent des données ; une hypothèse doit être présentée "
        "comme telle ;\n"
        '- "relance" : UNE question courte posée à l\'analyste pour proposer l\'analyse suivante la plus '
        "utile, à laquelle il peut répondre par oui ou non (ex. « Veux-tu voir l'évolution par mois ? ») ;\n"
        '- "question_suivante" : cette même analyse écrite comme une demande autonome et courte à poser '
        "à la base de données, compréhensible sans le contexte (ex. « Évolution mensuelle des "
        "transactions frauduleuses à Douala »).\n\n"
        f"Question : <<<{question}>>>\nNombre total de lignes : {len(lignes)}\n"
        f"Extrait (30 lignes max) : {json.dumps(extrait, ensure_ascii=False, default=str)[:6000]}\n")
    try:
        rep = client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt,
                                             config={"response_mime_type": "application/json"})
        brut = (rep.text or "").strip()
    except Exception as e:
        log.warning("Résumé Gemini impossible : %s", e)
        return None
    try:
        data = json.loads(brut.removeprefix("```json").removesuffix("```").strip())
        texte = str(data.get("resume") or "").strip().replace("\n", " ")[:600]
        comm = str(data.get("commentaire") or "").strip().replace("\n", " ")[:1500] or None
        relance = _relance(data.get("relance"), data.get("question_suivante"))
    except (ValueError, AttributeError):
        texte, comm, relance = brut.replace("\n", " ")[:600], None, None      # réponse en texte libre
    return {"resume": texte, "commentaire": comm, "relance": relance} if texte else None


def resumer(question: str, colonnes: list[str], lignes: list[dict], devise: str = "XAF") -> dict:
    """Retourne {resume, commentaire, relance, source} ; source = 'gemini' ou 'local'.
    `devise` : monnaie dans laquelle les montants de `lignes` sont déjà exprimés."""
    from .devises import DEVISES
    MONNAIE.set(DEVISES.get(devise, DEVISES["XAF"])["en_toutes_lettres"])
    if lignes:
        r = resume_gemini(question, colonnes, lignes)
        if r:
            return {"resume": r["resume"],
                    "commentaire": r["commentaire"] or commentaire_local(question, colonnes, lignes),
                    "relance": r["relance"] or relance_locale(question), "source": "gemini"}
    return {"resume": resume_local(question, colonnes, lignes),
            "commentaire": commentaire_local(question, colonnes, lignes),
            "relance": relance_locale(question) if lignes else {"texte": RELANCE_OUVERTE, "question": None},
            "source": "local"}
