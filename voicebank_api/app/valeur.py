"""« Valeur créée » : ce que VoiceBank a rapporté à l'organisation sur une période, en chiffres vérifiables.

* argent récupéré : paiements enregistrés dans les dossiers de recouvrement ;
* fraude évitée : montant des alertes confirmées comme fraudes (l'opération a été arrêtée ou signalée) ;
* alertes traitées et dossiers réglés ;
* temps gagné : questions répondues × 15 minutes. C'est une hypothèse, affichée comme telle : le temps qu'il faut
  à un analyste pour écrire la requête, la vérifier et mettre le résultat en forme.
Tous les montants sont dans la monnaie de la base.
"""
from datetime import datetime, timedelta

from . import db

DEMO_ID = 0
MINUTES_PAR_QUESTION = 15


def _membres(id_source: int, utilisateur: str) -> list[str]:
    """Personnes dont les questions comptent : les membres de l'organisation propriétaire de la base."""
    if id_source == DEMO_ID:
        return [utilisateur]
    r = db.ecrire("SELECT u.nom FROM voicebank.sources_donnees s JOIN voicebank.utilisateurs u ON "
                  "((s.id_org IS NOT NULL AND u.id_org = s.id_org) OR (s.id_org IS NULL AND u.nom = s.proprietaire)) "
                  "WHERE s.id_source = :s", {"s": id_source}).lignes
    return [l.nom for l in r] or [utilisateur]


def calculer(id_source: int, utilisateur: str, jours: int = 30) -> dict:
    depuis = datetime.now() - timedelta(days=jours)
    p = {"s": id_source, "d": depuis}
    recupere = float(db.ecrire(
        "SELECT COALESCE(SUM(a.montant), 0) FROM voicebank.actions_recouvrement a JOIN voicebank.dossiers_recouvrement d "
        "ON d.id_dossier = a.id_dossier WHERE d.id_source = :s AND a.nature = 'paiement' AND a.date_action >= :d", p).scalar())
    dossiers = db.ecrire(
        "SELECT COUNT(*) FILTER (WHERE statut = 'regle' AND date_cloture >= :d) AS regles, "
        "COALESCE(SUM(GREATEST(COALESCE(montant_du, 0) - montant_recupere, 0)) FILTER (WHERE statut NOT IN "
        "('regle', 'irrecouvrable')), 0) AS reste FROM voicebank.dossiers_recouvrement WHERE id_source = :s", p).lignes[0]
    if id_source == DEMO_ID:
        f = db.ecrire(
            "SELECT COUNT(*) FILTER (WHERE a.decision = 'Fraude confirmée') AS fraudes, "
            "COALESCE(SUM(t.montant_fcfa) FILTER (WHERE a.decision = 'Fraude confirmée'), 0) AS montant, "
            "COUNT(*) AS traitees FROM voicebank.alertes_fraude a LEFT JOIN voicebank.transactions t "
            "ON t.id_transaction = a.id_transaction WHERE a.traitee AND a.date_traitement >= :d", p).lignes[0]
    else:
        f = db.ecrire(
            "SELECT COUNT(*) FILTER (WHERE statut = 'fraude_confirmee') AS fraudes, "
            "COALESCE(SUM(montant) FILTER (WHERE statut = 'fraude_confirmee'), 0) AS montant, COUNT(*) AS traitees "
            "FROM voicebank.suivi_alertes WHERE id_source = :s AND date_cloture >= :d", p).lignes[0]
    questions = int(db.ecrire("SELECT COUNT(*) FROM voicebank.logs_vocaux WHERE succes AND utilisateur = ANY(:u) "
                              "AND date_requete >= :d", {"u": _membres(id_source, utilisateur), "d": depuis}).scalar())
    semaines = db.ecrire(
        "SELECT date_trunc('week', a.date_action)::date AS semaine, SUM(a.montant) AS montant "
        "FROM voicebank.actions_recouvrement a JOIN voicebank.dossiers_recouvrement d ON d.id_dossier = a.id_dossier "
        "WHERE d.id_source = :s AND a.nature = 'paiement' AND a.date_action >= :d GROUP BY 1 ORDER BY 1", p).lignes
    reste = float(dossiers.reste)
    return {
        "jours": jours, "depuis": depuis.date().isoformat(),
        "recupere": recupere, "dossiers_regles": int(dossiers.regles), "reste_a_recouvrer": reste,
        "taux_recuperation": round(recupere / (recupere + reste), 4) if recupere + reste else None,
        "fraude_evitee": float(f.montant or 0), "fraudes_confirmees": int(f.fraudes or 0), "alertes_traitees": int(f.traitees or 0),
        "questions": questions, "heures_gagnees": round(questions * MINUTES_PAR_QUESTION / 60, 1),
        "minutes_par_question": MINUTES_PAR_QUESTION,
        "total": recupere + float(f.montant or 0),
        "par_semaine": [{"semaine": l.semaine.isoformat(), "montant": float(l.montant or 0)} for l in semaines],
    }
