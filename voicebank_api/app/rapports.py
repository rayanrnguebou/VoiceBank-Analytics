"""Rapports PDF de risque (hebdomadaire ou mensuel) pour la direction et la conformité.

Contenu : synthèse chiffrée de la période, points d'attention rédigés automatiquement, alertes ouvertes les plus
critiques, portefeuille de crédits, fiches des modèles (fiabilité, dérive) et méthodologie. Aucune donnée
personnelle : les opérations sont désignées par leur référence, jamais par le nom du client.
"""
import io
from datetime import datetime, timedelta

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from . import db, suivi
from .connecteur import service as sources

FORET, LAITON, GRIS, CLAIR = colors.HexColor("#0E332D"), colors.HexColor("#B8892F"), colors.HexColor("#5B6B66"), \
    colors.HexColor("#EEF3F1")
COULEURS = {"Critique": colors.HexColor("#DC2626"), "Élevé": colors.HexColor("#EA580C"),
            "Moyen": colors.HexColor("#CA8A04"), "Faible": colors.HexColor("#16A34A")}
PERIODES = {"semaine": ("hebdomadaire", 7), "mois": ("mensuel", 30)}


def _t(texte) -> str:
    """Texte sûr pour les polices PDF standard (pas de caractères hors Latin-1) et pour le balisage Paragraph."""
    s = str("" if texte is None else texte)
    for a, b in (("≥", ">="), ("≤", "<="), ("→", "->"), ("–", "-"), ("—", "-"), ("…", "..."), ("’", "'"),
                 (" ", " "), (" ", " "), ("×", "x"), ("²", "2")):
        s = s.replace(a, b)
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _nombre(v, dec: int = 0) -> str:
    if v is None:
        return "-"
    return f"{float(v):,.{dec}f}".replace(",", " ").replace(".", ",")


def _styles():
    st = getSampleStyleSheet()
    return {
        "titre": ParagraphStyle("titre", parent=st["Title"], fontName="Helvetica-Bold", fontSize=18, textColor=FORET,
                                alignment=TA_LEFT, spaceAfter=2),
        "sous": ParagraphStyle("sous", parent=st["Normal"], fontSize=9.5, textColor=GRIS, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=st["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, textColor=FORET,
                             spaceBefore=12, spaceAfter=6),
        "p": ParagraphStyle("p", parent=st["Normal"], fontSize=9.5, leading=13),
        "petit": ParagraphStyle("petit", parent=st["Normal"], fontSize=8, leading=10.5, textColor=GRIS),
        "puce": ParagraphStyle("puce", parent=st["Normal"], fontSize=9.5, leading=13, leftIndent=10, bulletIndent=0),
    }


def _tableau(lignes, largeurs, entete=True, aligner_droite=()):
    t = Table(lignes, colWidths=largeurs, repeatRows=1 if entete else 0)
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.5), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("ROWBACKGROUNDS", (0, 1 if entete else 0), (-1, -1), [colors.white, CLAIR]),
             ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5DEDA")),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if entete:
        style += [("BACKGROUND", (0, 0), (-1, 0), FORET), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5)]
    for c in aligner_droite:
        style.append(("ALIGN", (c, 0), (c, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def _tuiles(valeurs: list[tuple[str, str]]):
    """Indicateurs clés en tuiles (4 par ligne)."""
    cellules = [[Paragraph(f"<font size=7.5 color='#5B6B66'>{_t(l)}</font><br/><font size=13><b>{_t(v)}</b></font>",
                           _styles()["p"]) for l, v in valeurs[i:i + 4]] for i in range(0, len(valeurs), 4)]
    for ligne in cellules:
        ligne += [""] * (4 - len(ligne))
    t = Table(cellules, colWidths=[43 * mm] * 4)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CLAIR), ("BOX", (0, 0), (-1, -1), 0.5, colors.white),
                           ("INNERGRID", (0, 0), (-1, -1), 3, colors.white),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    return t


def _graphique_alertes(par_jour: list[tuple[str, int]]):
    d = Drawing(172 * mm, 42 * mm)
    g = VerticalBarChart()
    g.x, g.y, g.width, g.height = 8 * mm, 8 * mm, 160 * mm, 30 * mm
    g.data = [[n for _, n in par_jour] or [0]]
    g.categoryAxis.categoryNames = [j for j, _ in par_jour] or [""]
    g.categoryAxis.labels.fontSize = 6.5
    g.categoryAxis.labels.angle = 0 if len(par_jour) <= 10 else 45
    g.categoryAxis.labels.boxAnchor = "n" if len(par_jour) <= 10 else "ne"
    g.valueAxis.labels.fontSize = 7
    g.valueAxis.valueMin = 0
    g.bars[0].fillColor = FORET
    g.bars[0].strokeColor = None
    d.add(g)
    return d


def _contexte_source(id_source: int):
    r = db.ecrire("SELECT s.id_source, s.nom, s.proprietaire, s.id_org, o.nom AS organisation "
                  "FROM voicebank.sources_donnees s LEFT JOIN voicebank.organisations o ON o.id_org = s.id_org "
                  "WHERE s.id_source = :s", {"s": id_source})
    if not r.lignes:
        raise sources.SourceRefusee("Source introuvable")
    return r.lignes[0]


def generer(id_source: int, proprietaire: str, periode: str = "semaine", maintenant: datetime | None = None
            ) -> tuple[bytes, str]:
    """Retourne (contenu PDF, nom de fichier). `proprietaire` : compte au nom duquel la base est lue."""
    if periode not in PERIODES:
        raise ValueError("Période inconnue")
    sources.detail(id_source, proprietaire)                    # contrôle d'accès
    src = _contexte_source(id_source)
    adjectif, jours = PERIODES[periode]
    fin = maintenant or datetime.now()
    debut = fin - timedelta(days=jours)
    s = _styles()
    stats = suivi.statistiques(id_source, debut)
    total = suivi.statistiques(id_source)
    try:
        ops, devise = sources.operations_base(id_source, proprietaire)
        resume = ops["resume"]
    except sources.SourceRefusee:
        resume, devise = None, None
    fiches = sources.fiches_modeles(id_source, proprietaire)
    try:
        credits = sources.portefeuille_credits(id_source, proprietaire, devise or "XAF")
    except sources.SourceRefusee:
        credits = None
    lib_devise = "FCFA" if devise in ("XAF", "XOF", None) else devise

    elements = [
        Paragraph(_t(f"Rapport de risque {adjectif}"), s["titre"]),
        Paragraph(_t(f"{src.organisation or 'Compte ' + src.proprietaire} · base « {src.nom} » · du "
                     f"{debut:%d/%m/%Y} au {fin:%d/%m/%Y} · généré le {datetime.now():%d/%m/%Y à %H:%M}"), s["sous"]),
    ]

    # 1. Synthèse
    elements.append(Paragraph("Synthèse de la période", s["h2"]))
    elements.append(_tuiles([
        ("Opérations analysées", _nombre(resume["analysees"]) if resume else "-"),
        ("Alertes détectées", _nombre(stats["total"])),
        ("dont critiques", _nombre(stats["critiques"])),
        ("Encore ouvertes (total)", _nombre(total["ouvertes"])),
        ("Fraudes confirmées", _nombre(stats["fraudes_confirmees"])),
        ("Fausses alertes", _nombre(stats["fausses_alertes"])),
        ("Délai moyen de traitement", f"{_nombre(stats['delai_moyen_h'], 1)} h" if stats["delai_moyen_h"] is not None else "-"),
        ("Précision des alertes", f"{_nombre(total['precision'] * 100)} %" if total["precision"] is not None else "à mesurer"),
    ]))
    par_jour = db.ecrire("SELECT to_char(date_detection::date, 'DD/MM') AS j, COUNT(*) AS n FROM voicebank.suivi_alertes "
                         "WHERE id_source = :s AND date_detection >= :d GROUP BY date_detection::date "
                         "ORDER BY date_detection::date", {"s": id_source, "d": debut}).lignes
    if par_jour:
        elements += [Spacer(1, 6), Paragraph("Alertes détectées par jour", s["petit"]),
                     _graphique_alertes([(l.j, int(l.n)) for l in par_jour])]

    # 2. Points d'attention
    points = []
    ouvertes_crit = db.ecrire("SELECT COUNT(*) FROM voicebank.suivi_alertes WHERE id_source = :s AND niveau = 'Critique' "
                              "AND statut NOT IN ('fraude_confirmee', 'fausse_alerte', 'resolue')", {"s": id_source}).scalar()
    if ouvertes_crit:
        points.append(f"{ouvertes_crit} alerte(s) critique(s) encore ouverte(s) : à traiter en priorité.")
    non_assignees = db.ecrire("SELECT COUNT(*) FROM voicebank.suivi_alertes WHERE id_source = :s AND assigne_a IS NULL "
                              "AND statut = 'nouvelle'", {"s": id_source}).scalar()
    if non_assignees:
        points.append(f"{non_assignees} nouvelle(s) alerte(s) sans responsable : pensez à les assigner.")
    if total["precision"] is not None and total["verdicts"] >= suivi.VERDICTS_MIN:
        points.append(f"Sur {total['verdicts']} verdicts rendus, {_nombre(total['precision'] * 100)} % des alertes "
                      "étaient de vraies fraudes.")
    elif total["verdicts"] < suivi.VERDICTS_MIN:
        points.append(f"{total['verdicts']} verdict(s) rendu(s) : classez les alertes (fraude confirmée / fausse alerte) "
                      "pour mesurer la précision du modèle et affiner les notifications.")
    der = (fiches.get("operations") or {}).get("derive") or {}
    if der.get("etat") in ("a_surveiller", "forte"):
        points.append(f"Dérive des habitudes : {der['detail']}")
    if credits and credits.get("taux_defaut") is not None:
        points.append(f"Portefeuille de crédits : taux de défaut observé de {_nombre(credits['taux_defaut'] * 100, 1)} % "
                      f"sur {_nombre(credits['credits'])} crédits.")
    if not points:
        points.append("Rien de particulier à signaler sur la période.")
    elements.append(Paragraph("Points d'attention", s["h2"]))
    elements += [Paragraph(_t(p), s["puce"], bulletText="•") for p in points]

    # 3. Alertes ouvertes les plus critiques
    rang = "CASE niveau WHEN 'Critique' THEN 0 WHEN 'Élevé' THEN 1 ELSE 2 END"
    ouvertes = db.ecrire("SELECT ref_operation, date_operation, montant, niveau, raisons, statut, assigne_a "
                         "FROM voicebank.suivi_alertes WHERE id_source = :s AND statut NOT IN ('fraude_confirmee', "
                         f"'fausse_alerte', 'resolue') ORDER BY {rang}, score DESC LIMIT 15", {"s": id_source}).lignes
    elements.append(Paragraph("Alertes ouvertes les plus critiques", s["h2"]))
    if ouvertes:
        lignes = [["Opération", "Date", f"Montant ({lib_devise})", "Niveau", "Raison principale", "Statut", "Assignée à"]]
        for a in ouvertes:
            raison = (a.raisons or [{}])[0]
            lignes.append([Paragraph(_t(str(a.ref_operation)[:18]), s["petit"]),
                           f"{a.date_operation:%d/%m/%Y}" if a.date_operation else "-", _nombre(a.montant),
                           Paragraph(f"<font color='{COULEURS.get(a.niveau, GRIS).hexval()}'><b>{_t(a.niveau)}</b></font>",
                                     s["petit"]),
                           Paragraph(_t(raison.get("detail") or raison.get("variable") or ""), s["petit"]),
                           _t(suivi.STATUTS[a.statut]), Paragraph(_t(a.assigne_a or "-"), s["petit"])])
        elements.append(_tableau(lignes, [24 * mm, 18 * mm, 24 * mm, 16 * mm, 50 * mm, 18 * mm, 24 * mm],
                                 aligner_droite=(2,)))
    else:
        elements.append(Paragraph("Aucune alerte ouverte.", s["p"]))

    # 4. Portefeuille de crédits
    if credits:
        elements.append(Paragraph("Portefeuille de crédits", s["h2"]))
        elements.append(_tuiles([("Crédits", _nombre(credits["credits"])), ("En défaut ou en retard", _nombre(credits["defauts"])),
                                 ("Taux de défaut", f"{_nombre(credits['taux_defaut'] * 100, 1)} %"),
                                 ("En cours", _nombre(credits["en_cours"]))]))
        segs = []
        for seg in credits.get("segments", [])[:3]:
            for g in seg["groupes"][:3]:
                segs.append([_t(seg["libelle"]), Paragraph(_t(g["valeur"]), s["petit"]), _nombre(g["credits"]),
                             f"{_nombre(g['taux_defaut'] * 100, 1)} %"])
        if segs:
            elements += [Spacer(1, 6), _tableau([["Segment", "Valeur", "Crédits", "Taux de défaut"]] + segs,
                                                 [45 * mm, 70 * mm, 25 * mm, 30 * mm], aligner_droite=(2, 3))]
        risque = credits.get("a_risque") or []
        if risque:
            lignes = [["Crédit", f"Montant ({lib_devise})", "Probabilité de défaut", "Niveau"]]
            lignes += [[_t(c.get("id") or "-"), _nombre(c.get("montant")), f"{_nombre(c['probabilite_defaut'] * 100, 1)} %",
                        _t(c["niveau_risque"])] for c in risque[:10]]
            elements += [Spacer(1, 6), Paragraph("Crédits en cours les plus à risque", s["petit"]),
                         _tableau(lignes, [45 * mm, 40 * mm, 45 * mm, 40 * mm], aligner_droite=(1, 2))]

    # 5. Fiches des modèles
    elements.append(Paragraph("Modèles d'IA utilisés", s["h2"]))
    for cle in ("operations", "credits"):
        f = fiches.get(cle) or {}
        if f.get("indisponible") and not f.get("nom"):
            continue
        bloc = [Paragraph(f"<b>{_t(f.get('nom'))}</b>", s["p"])]
        if f.get("indisponible"):
            bloc.append(Paragraph(_t(f["indisponible"]), s["petit"]))
        else:
            don = f.get("donnees") or {}
            bloc.append(Paragraph(_t(f"Données : « {don.get('table')} », "
                                     f"{_nombre(don.get('operations') or don.get('credits'))} lignes ; variables : "
                                     f"{', '.join(don.get('variables') or [])}."), s["petit"]))
            fia = f.get("fiabilite") or {}
            if fia.get("explication"):
                bloc.append(Paragraph(_t("Fiabilité : " + fia["explication"]), s["petit"]))
            if (f.get("derive") or {}).get("etat"):
                bloc.append(Paragraph(_t(f"Dérive ({f['derive']['periode_recente']}) : {f['derive']['detail']} "
                                         f"(indice {_nombre(f['derive']['indice'], 3)})"), s["petit"]))
        elements.append(KeepTogether(bloc + [Spacer(1, 5)]))

    # 6. Méthodologie
    elements.append(Paragraph("Méthodologie et limites", s["h2"]))
    for texte in ["Les modèles apprennent les habitudes de votre base (montants par type d'opération, valeurs rares, "
                  "heures) et signalent ce qui s'en écarte ; ils orientent la vérification humaine, ils ne décident pas.",
                  "Les alertes classées « fausse alerte » ne sont plus signalées ; les verdicts servent à mesurer la "
                  "précision et à régler les notifications.",
                  "Aucune donnée personnelle (nom, numéro de compte, téléphone) n'est utilisée par les modèles ni "
                  "reproduite dans ce rapport."]:
        elements.append(Paragraph(_t(texte), s["puce"], bulletText="•"))

    pied = _t(f"VoiceBank Analytics · {src.organisation or src.proprietaire} · document confidentiel")

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(GRIS)
        canvas.drawString(18 * mm, 10 * mm, pied.replace("&amp;", "&"))
        canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
        canvas.setStrokeColor(LAITON)
        canvas.setLineWidth(1.2)
        canvas.line(18 * mm, 287 * mm, 192 * mm, 287 * mm)
        canvas.restoreState()

    tampon = io.BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"Rapport de risque {adjectif}",
                            author="VoiceBank Analytics", subject=str(src.nom))
    doc.build(elements, onFirstPage=page, onLaterPages=page)
    nom = f"voicebank_rapport_{adjectif}_{fin:%Y-%m-%d}.pdf"
    return tampon.getvalue(), nom
