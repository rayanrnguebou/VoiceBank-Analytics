"""Suivi des alertes des bases connectées : chaque opération atypique devient une alerte avec un statut, une personne
assignée et un historique (commentaires, changements de statut, assignations).

Retour au modèle :
* une alerte classée « fausse alerte » ne revient plus, même si l'opération reste atypique ;
* la précision mesurée sur les verdicts (fraudes confirmées / alertes jugées) est affichée dans la fiche du modèle ;
* elle règle les notifications immédiates (seuil_notification) : un modèle qui se trompe souvent n'alerte plus que
  pour le plus critique, un modèle fiable alerte aussi pour le risque élevé.
"""
import hashlib
import json
from datetime import datetime

from sqlalchemy import text

from . import db

STATUTS = {"nouvelle": "Nouvelle", "en_cours": "En cours", "fraude_confirmee": "Fraude confirmée",
           "fausse_alerte": "Fausse alerte", "resolue": "Résolue"}
FERMES = ("fraude_confirmee", "fausse_alerte", "resolue")
NIVEAUX_SUIVIS = ("Critique", "Élevé")          # les 2 % les plus atypiques : une file de travail tenable
VERDICTS_MIN = 10                     # verdicts nécessaires avant d'ajuster les notifications


class SuiviRefuse(Exception):
    """Action refusée sur une alerte (message affichable)."""


def ref_operation(o: dict) -> str:
    """Identifiant stable d'une opération : sa clé dans la base, sinon une empreinte de ses valeurs."""
    if o.get("id") not in (None, "", "None", "nan"):
        return str(o["id"])[:200]
    brut = json.dumps([o.get("date"), round(float(o.get("montant") or 0), 2), o.get("categories")], sort_keys=True,
                      default=str)
    return "empreinte:" + hashlib.sha256(brut.encode()).hexdigest()[:32]


def enregistrer(id_source: int, operations: list[dict]) -> list[dict]:
    """Crée les alertes des opérations très atypiques (niveau Élevé ou Critique) ; met à jour score et niveau des alertes
    encore ouvertes. Retourne les alertes NOUVELLEMENT créées (pour les notifications)."""
    nouvelles = []
    for o in operations:
        if o.get("niveau_risque") not in NIVEAUX_SUIVIS:
            continue
        r = db.ecrire(
            "INSERT INTO voicebank.suivi_alertes (id_source, ref_operation, date_operation, montant, niveau, score, "
            "raisons, categories) VALUES (:s, :r, :d, :m, :n, :sc, CAST(:ra AS JSONB), CAST(:c AS JSONB)) "
            "ON CONFLICT (id_source, ref_operation) DO UPDATE SET niveau = EXCLUDED.niveau, score = EXCLUDED.score, "
            "raisons = EXCLUDED.raisons WHERE voicebank.suivi_alertes.statut NOT IN ('fraude_confirmee', "
            "'fausse_alerte', 'resolue') RETURNING id_suivi, (xmax = 0) AS creee",
            {"s": id_source, "r": ref_operation(o), "d": _date(o.get("date")), "m": o.get("montant"),
             "n": o["niveau_risque"], "sc": o.get("score") or 0, "ra": json.dumps(o.get("raisons") or [], default=str),
             "c": json.dumps(o.get("categories") or {}, default=str)})
        if r.lignes and r.lignes[0].creee:
            nouvelles.append({**o, "id_suivi": r.lignes[0].id_suivi})
    return nouvelles


def _date(v):
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)[:19])
    except ValueError:
        return None


def annoter(id_source: int, operations: list[dict]) -> list[dict]:
    """Ajoute à chaque opération l'état de son alerte (statut, personne assignée, nombre de commentaires)."""
    refs = {ref_operation(o): o for o in operations}
    if not refs:
        return operations
    r = db.ecrire("SELECT a.id_suivi, a.ref_operation, a.statut, a.assigne_a, a.date_maj, "
                  "(SELECT COUNT(*) FROM voicebank.commentaires_alerte c WHERE c.id_suivi = a.id_suivi "
                  " AND c.nature = 'commentaire') AS commentaires "
                  "FROM voicebank.suivi_alertes a WHERE a.id_source = :s AND a.ref_operation = ANY(:r)",
                  {"s": id_source, "r": list(refs)})
    suivis = {l.ref_operation: l for l in r.lignes}
    res = []
    for ref, o in refs.items():
        l = suivis.get(ref)
        res.append({**o, "suivi": None if l is None else {
            "id": l.id_suivi, "statut": l.statut, "libelle_statut": STATUTS[l.statut], "assigne_a": l.assigne_a,
            "commentaires": int(l.commentaires), "date_maj": l.date_maj.isoformat() if l.date_maj else None}})
    return res


def _alerte(id_source: int, id_suivi: int):
    r = db.ecrire("SELECT * FROM voicebank.suivi_alertes WHERE id_suivi = :i AND id_source = :s",
                  {"i": id_suivi, "s": id_source})
    if not r.lignes:
        raise SuiviRefuse("Alerte introuvable")
    return r.lignes[0]


def _jsonable(l) -> dict:
    return {k: (v.isoformat() if hasattr(v, "isoformat") else float(v) if k in ("montant", "score") and v is not None
                else v) for k, v in l._mapping.items()}


def detail(id_source: int, id_suivi: int) -> dict:
    a = _alerte(id_source, id_suivi)
    h = db.ecrire("SELECT auteur, nature, texte, date_commentaire FROM voicebank.commentaires_alerte "
                  "WHERE id_suivi = :i ORDER BY date_commentaire, id_commentaire", {"i": id_suivi})
    return {**_jsonable(a), "libelle_statut": STATUTS[a.statut],
            "historique": [_jsonable(l) for l in h.lignes]}


def personnes_assignables(id_source: int) -> list[dict]:
    """Membres actifs de l'organisation propriétaire de la source (ou son propriétaire, hors organisation)."""
    r = db.ecrire("SELECT u.nom, COALESCE(u.nom_complet, u.nom) AS nom_complet FROM voicebank.sources_donnees s "
                  "JOIN voicebank.utilisateurs u ON u.actif AND ((s.id_org IS NOT NULL AND u.id_org = s.id_org) "
                  " OR (s.id_org IS NULL AND u.nom = s.proprietaire)) "
                  "WHERE s.id_source = :s ORDER BY u.nom_complet NULLS LAST, u.nom", {"s": id_source})
    return [{"nom": l.nom, "nom_complet": l.nom_complet} for l in r.lignes]


def modifier(id_source: int, id_suivi: int, par: str, statut: str | None = None, assigne_a: str | None = None,
             desassigner: bool = False, commentaire: str | None = None) -> dict:
    a = _alerte(id_source, id_suivi)
    commentaire = (commentaire or "").strip()
    if statut is not None and statut not in STATUTS:
        raise SuiviRefuse("Statut inconnu")
    if statut in ("fraude_confirmee", "fausse_alerte") and not commentaire and statut != a.statut:
        raise SuiviRefuse("Explique ton verdict en une phrase : il sert de retour au modèle et de trace pour l'audit.")
    if assigne_a and assigne_a not in {p["nom"] for p in personnes_assignables(id_source)}:
        raise SuiviRefuse("Cette personne ne fait pas partie de l'organisation")
    with db.moteur_app.begin() as conn:            # tout ou rien : statut, assignation et historique ensemble
        if statut and statut != a.statut:
            conn.execute(text("UPDATE voicebank.suivi_alertes SET statut = :st, date_maj = LOCALTIMESTAMP, maj_par = :p, "
                              "date_cloture = CASE WHEN :st IN ('fraude_confirmee', 'fausse_alerte', 'resolue') "
                              "THEN LOCALTIMESTAMP END WHERE id_suivi = :i"), {"st": statut, "p": par, "i": id_suivi})
            conn.execute(text("INSERT INTO voicebank.commentaires_alerte (id_suivi, auteur, nature, texte) "
                              "VALUES (:i, :p, 'statut', :t)"),
                         {"i": id_suivi, "p": par, "t": f"{STATUTS[a.statut]} → {STATUTS[statut]}"})
        nouvel_assigne = None if desassigner else assigne_a
        if (assigne_a or desassigner) and nouvel_assigne != a.assigne_a:
            conn.execute(text("UPDATE voicebank.suivi_alertes SET assigne_a = :a, date_maj = LOCALTIMESTAMP, maj_par = :p, "
                              "statut = CASE WHEN statut = 'nouvelle' AND :a IS NOT NULL THEN 'en_cours' ELSE statut END "
                              "WHERE id_suivi = :i"), {"a": nouvel_assigne, "p": par, "i": id_suivi})
            conn.execute(text("INSERT INTO voicebank.commentaires_alerte (id_suivi, auteur, nature, texte) "
                              "VALUES (:i, :p, 'assignation', :t)"),
                         {"i": id_suivi, "p": par, "t": f"Assignée à {nouvel_assigne}" if nouvel_assigne else "Assignation retirée"})
        if commentaire:
            conn.execute(text("INSERT INTO voicebank.commentaires_alerte (id_suivi, auteur, nature, texte) "
                              "VALUES (:i, :p, 'commentaire', :t)"), {"i": id_suivi, "p": par, "t": commentaire[:2000]})
            conn.execute(text("UPDATE voicebank.suivi_alertes SET date_maj = LOCALTIMESTAMP, maj_par = :p WHERE id_suivi = :i"),
                         {"p": par, "i": id_suivi})
    return detail(id_source, id_suivi)


def statistiques(id_source: int, depuis: datetime | None = None) -> dict:
    """Chiffres du suivi (sur une période si `depuis`) : alertes par niveau et par statut, délai de traitement,
    précision mesurée sur les verdicts."""
    p = {"s": id_source, "d": depuis}
    filtre = "AND date_detection >= :d" if depuis else ""
    r = db.ecrire("SELECT COUNT(*) AS total, "
                  "COUNT(*) FILTER (WHERE niveau = 'Critique') AS critiques, "
                  "COUNT(*) FILTER (WHERE niveau = 'Élevé') AS elevees, COUNT(*) FILTER (WHERE niveau = 'Moyen') AS moyennes, "
                  "COUNT(*) FILTER (WHERE statut NOT IN ('fraude_confirmee', 'fausse_alerte', 'resolue')) AS ouvertes, "
                  "COUNT(*) FILTER (WHERE statut = 'nouvelle') AS nouvelles, "
                  "COUNT(*) FILTER (WHERE statut = 'fraude_confirmee') AS fraudes_confirmees, "
                  "COUNT(*) FILTER (WHERE statut = 'fausse_alerte') AS fausses_alertes, "
                  "COUNT(*) FILTER (WHERE statut = 'resolue') AS resolues, "
                  "AVG(EXTRACT(EPOCH FROM (date_cloture - date_detection)) / 3600) FILTER (WHERE date_cloture IS NOT NULL) "
                  " AS delai_moyen_h "
                  f"FROM voicebank.suivi_alertes WHERE id_source = :s {filtre}", p).lignes[0]
    d = {k: (round(float(v), 1) if k == "delai_moyen_h" and v is not None else (int(v) if v is not None else None))
         for k, v in r._mapping.items()}
    d.update(precision(id_source))
    return d


def precision(id_source: int) -> dict:
    """Part de fraudes confirmées parmi les alertes jugées (toutes périodes)."""
    r = db.ecrire("SELECT COUNT(*) FILTER (WHERE statut = 'fraude_confirmee') AS vraies, "
                  "COUNT(*) FILTER (WHERE statut = 'fausse_alerte') AS fausses "
                  "FROM voicebank.suivi_alertes WHERE id_source = :s", {"s": id_source}).lignes[0]
    jugees = int(r.vraies) + int(r.fausses)
    return {"verdicts": jugees, "precision": round(int(r.vraies) / jugees, 3) if jugees else None}


def seuil_notification(id_source: int) -> dict:
    """Quelles nouvelles alertes méritent un e-mail immédiat, d'après les verdicts déjà rendus."""
    p = precision(id_source)
    if p["verdicts"] < VERDICTS_MIN:
        return {"niveaux": ["Critique"], "score_min": 0.0, "raison": "par défaut (pas encore assez de verdicts)"}
    if p["precision"] >= 0.6:
        return {"niveaux": ["Critique", "Élevé"], "score_min": 0.0,
                "raison": f"modèle fiable sur vos verdicts ({p['precision'] * 100:.0f} % de fraudes confirmées)"}
    if p["precision"] < 0.25:
        return {"niveaux": ["Critique"], "score_min": 0.998,
                "raison": f"beaucoup de fausses alertes ({p['precision'] * 100:.0f} % de fraudes confirmées) : "
                          "seules les plus extrêmes sont envoyées"}
    return {"niveaux": ["Critique"], "score_min": 0.0,
            "raison": f"{p['precision'] * 100:.0f} % de fraudes confirmées sur vos verdicts"}


def marquer_notifiees(ids: list[int]):
    if ids:
        db.ecrire("UPDATE voicebank.suivi_alertes SET notifiee = TRUE WHERE id_suivi = ANY(:i)", {"i": ids})
