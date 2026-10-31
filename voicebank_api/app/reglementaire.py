"""Documents réglementaires préparés à partir du travail fait dans VoiceBank.

* **Projet de déclaration de soupçon** (lutte contre le blanchiment) à partir d'une fraude confirmée : opération,
  motifs (raisons du modèle et constats de l'équipe), chronologie, mesures prises. C'est un PROJET : le déclarant
  habilité le vérifie, le complète (identité du client, pièces) et le transmet lui-même à la cellule de
  renseignement financier (ANIF au Cameroun et dans la CEMAC selon le pays, TRACFIN en France…). Rappel de
  l'interdiction d'informer le client.
* **État de la qualité du portefeuille de crédits** : encours sain, en retard, en défaut, ratio de créances en
  souffrance, répartition par segment, suivi du recouvrement. Aide à la préparation des états prudentiels ; ne
  remplace pas les formats officiels de l'autorité de supervision (COBAC, ACPR…).
"""
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from . import db, recouvrement as R
from .connecteur import service as sources
from .rapports import _contexte_source, _nombre, _styles, _t, _tableau, _tuiles


def _c(texte) -> str:
    """Texte de cellule de tableau (pas de balisage : on retire l'échappement fait pour les paragraphes)."""
    return _t(texte).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


class DocumentRefuse(ValueError):
    """Message affichable."""


def _pdf(elements, titre: str) -> bytes:
    import io
    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm,
                            bottomMargin=14 * mm, title=titre, author="VoiceBank Analytics")
    doc.build(elements)
    return tampon.getvalue()


def _organisation(id_source: int, proprietaire: str) -> str:
    if id_source == sources.DEMO_ID:
        return "Démonstration VoiceBank (données fictives)"
    src = _contexte_source(id_source)
    return f"{src.organisation or src.proprietaire} · base « {src.nom} »"


def declaration_soupcon(id_source: int, id_suivi: int, par: str) -> tuple[bytes, str]:
    r = db.ecrire("SELECT * FROM voicebank.suivi_alertes WHERE id_source = :s AND id_suivi = :i",
                  {"s": id_source, "i": id_suivi}).lignes
    if not r:
        raise DocumentRefuse("Alerte introuvable")
    a = r[0]
    if a.statut != "fraude_confirmee":
        raise DocumentRefuse("Le projet de déclaration se prépare à partir d'une fraude confirmée par l'équipe.")
    histo = db.ecrire("SELECT auteur, nature, texte, date_commentaire FROM voicebank.commentaires_alerte "
                      "WHERE id_suivi = :i ORDER BY date_commentaire", {"i": id_suivi}).lignes
    devise = sources.monnaie(id_source, par)
    lib = "FCFA" if devise in ("XAF", "XOF") else devise
    s = _styles()
    el = [
        Paragraph(_t("PROJET — Déclaration de soupçon"), s["titre"]),
        Paragraph(_t(f"{_organisation(id_source, par)} · préparé par {par} le {datetime.now():%d/%m/%Y à %H:%M} · "
                     f"référence interne VB-{id_source}-{id_suivi}"), s["sous"]),
        Paragraph(_t("À vérifier, compléter et transmettre par le déclarant habilité à la cellule de renseignement "
                     "financier compétente (ANIF au Cameroun et dans les pays de la CEMAC, TRACFIN en France…), "
                     "selon le formulaire officiel. Ne jamais informer le client ni un tiers de cette déclaration."),
                  s["petit"]),
        Paragraph(_t("1. Opération concernée"), s["h2"]),
        _tableau([["Élément", "Valeur"],
                  ["Référence de l'opération", _c(a.ref_operation)],
                  ["Date de l'opération", _c(f"{a.date_operation:%d/%m/%Y %H:%M}" if a.date_operation else "non renseignée")],
                  ["Montant", _c(f"{_nombre(a.montant)} {lib}" if a.montant is not None else "-")],
                  *[[_c(str(k)), _c(str(v))] for k, v in (a.categories or {}).items()],
                  ["Détectée par VoiceBank le", _c(f"{a.date_detection:%d/%m/%Y %H:%M}")],
                  ["Niveau de risque / score", _c(f"{a.niveau} · plus atypique que {float(a.score) * 100:.1f} % des opérations")]],
                 [60 * mm, 118 * mm]),
        Paragraph(_t("2. Motifs du soupçon"), s["h2"]),
    ]
    for x in a.raisons or []:
        el.append(Paragraph(_t(f"- {x.get('variable')} : {x.get('detail') or x.get('valeur') or ''}"), s["puce"]))
    constats = [h for h in histo if h.nature == "commentaire" or "Fraude confirmée" in (h.texte or "")]
    el.append(Paragraph(_t("Constats de l'équipe :"), s["p"]))
    for h in constats or []:
        el.append(Paragraph(_t(f"- {h.texte} ({h.auteur}, {h.date_commentaire:%d/%m/%Y})"), s["puce"]))
    if not constats:
        el.append(Paragraph(_t("• (à compléter)"), s["puce"]))
    el += [
        Paragraph(_t("3. Chronologie du traitement"), s["h2"]),
        _tableau([["Date", "Par", "Action"]] + [[_c(f"{h.date_commentaire:%d/%m/%Y %H:%M}"), _c(h.auteur), _c(h.texte)]
                                                 for h in histo] or [["-", "-", "-"]], [32 * mm, 40 * mm, 106 * mm]),
        Paragraph(_t("4. À compléter par le déclarant"), s["h2"]),
    ]
    for ligne in ("Identité complète du client et des bénéficiaires (pièce, adresse, profession)",
                  "Comptes et opérations liés, origine et destination des fonds",
                  "Mesures conservatoires prises (blocage, gel, clôture)",
                  "Pièces jointes (relevés, justificatifs, échanges)",
                  "Nom, fonction et signature du déclarant habilité"):
        el.append(Paragraph(_t(f"[ ] {ligne}"), s["puce"]))
    el += [Spacer(1, 8), Paragraph(_t("Document préparé automatiquement par VoiceBank à partir de l'alerte et de son "
                                      "suivi. Il ne constitue pas une déclaration tant qu'il n'a pas été transmis par "
                                      "le déclarant habilité."), s["petit"])]
    return _pdf(el, "Projet de déclaration de soupçon"), f"projet_declaration_soupcon_VB-{id_source}-{id_suivi}.pdf"


def etat_portefeuille(id_source: int, par: str, role: str) -> tuple[bytes, str]:
    lus, base, _ = sources.credits_a_recouvrer(id_source, par, role)
    port = sources.portefeuille_credits(id_source, par, base)
    lib = "FCFA" if base in ("XAF", "XOF") else base
    retard = [c for c in lus["dossiers"] if c["etape"] == "retard"]
    defaut = [c for c in lus["dossiers"] if c["etape"] == "defaut"]
    somme = lambda l: sum(c["montant"] or 0 for c in l)  # noqa: E731
    n_total = port["credits"]
    souffrance = len(retard) + len(defaut)
    stats = R.statistiques(id_source)
    s = _styles()
    el = [
        Paragraph(_t("État de la qualité du portefeuille de crédits"), s["titre"]),
        Paragraph(_t(f"{_organisation(id_source, par)} · table « {port['table']} » · arrêté au {datetime.now():%d/%m/%Y}"),
                  s["sous"]),
        Paragraph(_t("Aide à la préparation des états prudentiels : ne remplace pas les formats officiels de l'autorité de "
                     "supervision (COBAC, ACPR…). Montants lus dans la base, sur 20 000 crédits au plus."), s["petit"]),
        Paragraph(_t("1. Synthèse"), s["h2"]),
        _tuiles([("Crédits", _nombre(n_total)), ("En retard", _nombre(len(retard))), ("En défaut", _nombre(len(defaut))),
                 ("Créances en souffrance", f"{100 * souffrance / n_total:.1f} %".replace(".", ",") if n_total else "-")]),
        Spacer(1, 6),
        _tableau([["Catégorie", "Nombre", f"Montant ({lib})"],
                  ["En retard", _nombre(len(retard)), _nombre(somme(retard))],
                  ["En défaut ou contentieux", _nombre(len(defaut)), _nombre(somme(defaut))],
                  ["Total en souffrance", _nombre(souffrance), _nombre(somme(retard) + somme(defaut))]],
                 [90 * mm, 30 * mm, 58 * mm], aligner_droite=(1, 2)),
        Paragraph(_t("2. Ancienneté des retards"), s["h2"]),
    ]
    tranches = [("0 à 30 jours", 0, 30), ("31 à 90 jours", 31, 90), ("91 à 180 jours", 91, 180), ("Plus de 180 jours", 181, 10 ** 6)]
    avec_jours = [c for c in lus["dossiers"] if c.get("jours_retard") is not None]
    if avec_jours:
        el.append(_tableau([["Ancienneté", "Nombre", f"Montant ({lib})"]] + [
            [l, _nombre(len(g)), _nombre(somme(g))] for l, a, b in tranches
            for g in [[c for c in avec_jours if a <= c["jours_retard"] <= b]]], [90 * mm, 30 * mm, 58 * mm], aligner_droite=(1, 2)))
    else:
        el.append(Paragraph(_t("La base n'a pas de date d'échéance reconnue : ancienneté non calculable."), s["p"]))
    el.append(Paragraph(_t("3. Taux de défaut par segment"), s["h2"]))
    for seg in port.get("segments", [])[:3]:
        el.append(Paragraph(_t(seg["libelle"]), s["p"]))
        el.append(_tableau([["Groupe", "Crédits", "Défauts", "Taux"]] + [
            [_c(g["valeur"]), _nombre(g["credits"]), _nombre(g["defauts"]), f"{100 * g['taux_defaut']:.1f} %".replace(".", ",")]
            for g in seg["groupes"][:8]], [80 * mm, 30 * mm, 30 * mm, 38 * mm], aligner_droite=(1, 2, 3)))
        el.append(Spacer(1, 4))
    el += [
        Paragraph(_t("4. Recouvrement"), s["h2"]),
        _tableau([["Indicateur", "Valeur"],
                  ["Dossiers en cours", _nombre(stats["ouverts"])],
                  [f"Reste à recouvrer ({lib})", _nombre(stats["reste_du"])],
                  [f"Récupéré depuis l'ouverture des dossiers ({lib})", _nombre(stats["recupere"])],
                  ["Promesses de paiement en cours", _nombre(stats["promesses"])],
                  ["Promesses dont la date est dépassée", _nombre(stats["promesses_depassees"])]],
                 [120 * mm, 58 * mm], aligner_droite=(1,)),
    ]
    return _pdf(el, "État de la qualité du portefeuille"), f"etat_portefeuille_{datetime.now():%Y-%m-%d}.pdf"

