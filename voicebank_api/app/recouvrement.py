"""Recouvrement des crédits en retard : dossiers, priorités, relances, promesses et paiements.

Chaque crédit en retard ou en défaut de la base devient un dossier suivi par l'équipe (statut, personne assignée,
historique). VoiceBank ne garde que la référence du crédit et les montants : le nom et le téléphone du client sont
relus dans la base de l'organisation à chaque affichage, jamais copiés.

Priorité = montant dû × chance de récupération de l'étape (retard ou défaut). Tant que l'équipe n'a pas clos assez
de dossiers, on part de repères prudents (60 % pour un retard, 25 % pour un défaut) ; dès 10 dossiers clos dans une
étape, c'est le taux réellement obtenu par l'équipe qui est utilisé.
"""
import re
from datetime import date, datetime, timedelta

from . import db

STATUTS = {"a_contacter": "À contacter", "contacte": "Contacté", "promesse": "Promesse de paiement",
           "paiement_partiel": "Paiement partiel", "regle": "Réglé", "injoignable": "Injoignable",
           "contentieux": "Contentieux", "irrecouvrable": "Irrécouvrable"}
OUVERTS = ("a_contacter", "contacte", "promesse", "paiement_partiel", "injoignable", "contentieux")
CLOS = ("regle", "irrecouvrable")
NATURES = ("appel", "sms", "whatsapp", "promesse", "paiement", "commentaire", "statut", "assignation")
CHANCE_DEFAUT = {"retard": 0.60, "defaut": 0.25}
MIN_DOSSIERS_CLOS = 10
MESSAGE_DEFAUT = ("Bonjour {client}, sauf erreur de notre part, votre crédit {reference} présente un impayé de {montant}. "
                  "Merci de régulariser au plus vite{paiement}. Pour toute question, répondez à ce message. {signature}")


class DossierRefuse(ValueError):
    """Message affichable."""


# ── Synchronisation avec la base de l'organisation ─────────────────────────────

def synchroniser(id_source: int, credits: list[dict], complet: bool) -> None:
    """Ouvre un dossier pour chaque nouveau crédit en retard, met à jour l'étape et le montant des dossiers ouverts,
    et clôt (« Réglé ») ceux dont le crédit n'est plus en retard dans la base, si la liste lue est complète."""
    existants = {l.ref_credit: l for l in db.ecrire(
        "SELECT id_dossier, ref_credit, statut, etape, montant_du FROM voicebank.dossiers_recouvrement WHERE id_source = :s",
        {"s": id_source}).lignes}
    vus = set()
    nouveaux, majs = [], []
    for c in credits:
        vus.add(c["ref"])
        d = existants.get(c["ref"])
        if d is None:
            nouveaux.append({"s": id_source, "r": c["ref"][:200], "e": c["etape"], "m": c.get("montant")})
        elif d.statut in OUVERTS and (d.etape != c["etape"] or _diff(d.montant_du, c.get("montant"))):
            majs.append({"i": d.id_dossier, "e": c["etape"], "m": c.get("montant")})
    if nouveaux:
        db.ecrire("INSERT INTO voicebank.dossiers_recouvrement (id_source, ref_credit, etape, montant_du) "
                  "VALUES (:s, :r, :e, :m) ON CONFLICT (id_source, ref_credit) DO NOTHING", nouveaux)
    for m in majs:
        db.ecrire("UPDATE voicebank.dossiers_recouvrement SET etape = :e, montant_du = :m, date_maj = LOCALTIMESTAMP "
                  "WHERE id_dossier = :i", m)
    if complet:
        regles = [d for r, d in existants.items() if r not in vus and d.statut in OUVERTS]
        for d in regles:
            db.ecrire("UPDATE voicebank.dossiers_recouvrement SET statut = 'regle', date_cloture = LOCALTIMESTAMP, "
                      "date_maj = LOCALTIMESTAMP, maj_par = 'système', montant_recupere = GREATEST(montant_recupere, "
                      "COALESCE(montant_du, 0)) WHERE id_dossier = :i", {"i": d.id_dossier})
            _action(d.id_dossier, "système", "statut", "Crédit régularisé dans la base : dossier clos (Réglé).")


def _diff(a, b) -> bool:
    if a is None or b is None:
        return (a is None) != (b is None)
    return abs(float(a) - float(b)) > 0.005


def _action(id_dossier: int, auteur: str, nature: str, texte: str, montant=None):
    db.ecrire("INSERT INTO voicebank.actions_recouvrement (id_dossier, auteur, nature, texte, montant) "
              "VALUES (:d, :a, :n, :t, :m)", {"d": id_dossier, "a": auteur[:64], "n": nature, "t": texte[:2000], "m": montant})


# ── Priorités et lecture ───────────────────────────────────────────────────────

def chances(id_source: int) -> dict:
    """Chance de récupération par étape : taux réel de l'équipe dès 10 dossiers clos, sinon repère prudent."""
    r = db.ecrire("SELECT etape, COUNT(*) AS n, COUNT(*) FILTER (WHERE statut = 'regle') AS regles, "
                  "SUM(montant_du) FILTER (WHERE statut IN ('regle', 'irrecouvrable')) AS du, "
                  "SUM(LEAST(montant_recupere, COALESCE(montant_du, montant_recupere))) AS recupere "
                  "FROM voicebank.dossiers_recouvrement WHERE id_source = :s AND statut IN ('regle', 'irrecouvrable') "
                  "GROUP BY etape", {"s": id_source}).lignes
    res = {e: {"taux": v, "source": "repere"} for e, v in CHANCE_DEFAUT.items()}
    for l in r:
        if l.etape in res and l.n >= MIN_DOSSIERS_CLOS:
            taux = float(l.recupere or 0) / float(l.du) if l.du else l.regles / l.n
            res[l.etape] = {"taux": round(min(max(taux, 0.0), 1.0), 3), "source": "equipe", "dossiers_clos": int(l.n)}
    res["preventif"] = res["retard"]
    return res


def dossiers(id_source: int, credits: dict[str, dict], statut: str = "ouverts", limite: int = 300) -> list[dict]:
    if statut == "ouverts":
        filtre, p = "statut = ANY(:st)", {"st": list(OUVERTS)}
    elif statut == "clos":
        filtre, p = "statut = ANY(:st)", {"st": list(CLOS)}
    elif statut in STATUTS:
        filtre, p = "statut = :st", {"st": statut}
    else:
        filtre, p = "TRUE", {}
    lignes = db.ecrire(
        "SELECT d.*, (SELECT COUNT(*) FROM voicebank.actions_recouvrement a WHERE a.id_dossier = d.id_dossier "
        "AND a.nature IN ('appel', 'sms', 'whatsapp')) AS relances, (SELECT MAX(date_action) FROM "
        "voicebank.actions_recouvrement a WHERE a.id_dossier = d.id_dossier AND a.nature IN ('appel', 'sms', "
        f"'whatsapp')) AS derniere_relance FROM voicebank.dossiers_recouvrement d WHERE id_source = :s AND {filtre}",
        {"s": id_source, **p}).lignes
    ch = chances(id_source)
    res = []
    aujourdhui = date.today()
    for l in lignes:
        du = float(l.montant_du or 0)
        reste = max(du - float(l.montant_recupere or 0), 0.0)
        c = credits.get(l.ref_credit, {})
        promesse_depassee = bool(l.promesse_date and l.statut == "promesse" and l.promesse_date < aujourdhui)
        priorite = reste * ch.get(l.etape, ch["retard"])["taux"] * (1.3 if promesse_depassee else 1.0)
        res.append({"id": l.id_dossier, "ref": l.ref_credit, "etape": l.etape, "statut": l.statut,
                    "libelle_statut": STATUTS[l.statut], "montant_du": du, "montant_recupere": float(l.montant_recupere or 0),
                    "reste": reste, "priorite": round(priorite, 2), "assigne_a": l.assigne_a,
                    "promesse_date": l.promesse_date.isoformat() if l.promesse_date else None,
                    "promesse_montant": float(l.promesse_montant) if l.promesse_montant is not None else None,
                    "promesse_depassee": promesse_depassee, "relances": int(l.relances or 0),
                    "derniere_relance": l.derniere_relance.isoformat() if l.derniere_relance else None,
                    "date_ouverture": l.date_ouverture.isoformat(), "client": c.get("client"),
                    "telephone": c.get("telephone"), "jours_retard": c.get("jours_retard"),
                    "statut_base": c.get("statut_base")})
    res.sort(key=lambda d: (d["statut"] in CLOS, -d["priorite"]))
    return res[:limite]


def statistiques(id_source: int, depuis: datetime | None = None) -> dict:
    p = {"s": id_source, "d": depuis or datetime(1970, 1, 1)}
    r = db.ecrire(
        "SELECT COUNT(*) FILTER (WHERE statut = ANY(:ouverts)) AS ouverts, "
        "COALESCE(SUM(GREATEST(COALESCE(montant_du, 0) - montant_recupere, 0)) FILTER (WHERE statut = ANY(:ouverts)), 0) AS reste_du, "
        "COUNT(*) FILTER (WHERE statut = 'promesse') AS promesses, "
        "COALESCE(SUM(promesse_montant) FILTER (WHERE statut = 'promesse'), 0) AS montant_promis, "
        "COUNT(*) FILTER (WHERE statut = 'promesse' AND promesse_date < CURRENT_DATE) AS promesses_depassees, "
        "COUNT(*) FILTER (WHERE statut = 'regle' AND date_cloture >= :d) AS regles, "
        "COUNT(*) FILTER (WHERE assigne_a IS NULL AND statut = ANY(:ouverts)) AS non_assignes "
        "FROM voicebank.dossiers_recouvrement WHERE id_source = :s",
        {**p, "ouverts": list(OUVERTS)}).lignes[0]
    recupere = db.ecrire("SELECT COALESCE(SUM(a.montant), 0) FROM voicebank.actions_recouvrement a JOIN "
                         "voicebank.dossiers_recouvrement d ON d.id_dossier = a.id_dossier WHERE d.id_source = :s "
                         "AND a.nature = 'paiement' AND a.date_action >= :d", p).scalar()
    relances = db.ecrire("SELECT COUNT(*) FROM voicebank.actions_recouvrement a JOIN voicebank.dossiers_recouvrement d "
                         "ON d.id_dossier = a.id_dossier WHERE d.id_source = :s AND a.nature IN ('appel', 'sms', 'whatsapp') "
                         "AND a.date_action >= :d", p).scalar()
    return {"ouverts": int(r.ouverts), "reste_du": float(r.reste_du), "promesses": int(r.promesses),
            "montant_promis": float(r.montant_promis), "promesses_depassees": int(r.promesses_depassees),
            "regles": int(r.regles), "non_assignes": int(r.non_assignes), "recupere": float(recupere or 0),
            "relances": int(relances or 0)}


def _dossier(id_source: int, id_dossier: int):
    r = db.ecrire("SELECT * FROM voicebank.dossiers_recouvrement WHERE id_source = :s AND id_dossier = :i",
                  {"s": id_source, "i": id_dossier}).lignes
    if not r:
        raise DossierRefuse("Dossier introuvable")
    return r[0]


def historique(id_source: int, id_dossier: int) -> list[dict]:
    _dossier(id_source, id_dossier)
    r = db.ecrire("SELECT auteur, nature, texte, montant, date_action FROM voicebank.actions_recouvrement "
                  "WHERE id_dossier = :d ORDER BY date_action DESC, id_action DESC", {"d": id_dossier}).lignes
    return [{"auteur": l.auteur, "nature": l.nature, "texte": l.texte,
             "montant": float(l.montant) if l.montant is not None else None, "date": l.date_action.isoformat()} for l in r]


# ── Actions de l'équipe ────────────────────────────────────────────────────────

def agir(id_source: int, id_dossier: int, par: str, nature: str, texte: str | None = None, montant: float | None = None,
         date_promesse: date | None = None, statut: str | None = None, assigne_a: str | None = None,
         desassigner: bool = False) -> dict:
    """Une action sur un dossier : relance (appel, SMS, WhatsApp), promesse, paiement reçu, commentaire,
    changement de statut ou assignation. Le statut suit les actions (paiement complet → Réglé…)."""
    d = _dossier(id_source, id_dossier)
    if nature not in NATURES:
        raise DossierRefuse("Action inconnue")
    du = float(d.montant_du or 0)
    texte = (texte or "").strip()
    maj = {}
    if nature in ("appel", "sms", "whatsapp"):
        libelle = {"appel": "Appel", "sms": "SMS envoyé", "whatsapp": "Message WhatsApp envoyé"}[nature]
        _action(id_dossier, par, nature, f"{libelle}{' : ' + texte if texte else ''}")
        if d.statut == "a_contacter":
            maj["statut"] = "contacte"
    elif nature == "promesse":
        if not date_promesse or not montant or montant <= 0:
            raise DossierRefuse("Indique la date et le montant promis.")
        if date_promesse < date.today():
            raise DossierRefuse("La date promise est déjà passée.")
        if date_promesse > date.today() + timedelta(days=365):
            raise DossierRefuse("Date promise trop lointaine (un an au plus).")
        maj.update(statut="promesse", promesse_date=date_promesse, promesse_montant=montant)
        _action(id_dossier, par, "promesse", f"Promesse : {_fmt(montant)} le {date_promesse.strftime('%d/%m/%Y')}"
                + (f" — {texte}" if texte else ""), montant)
    elif nature == "paiement":
        if not montant or montant <= 0:
            raise DossierRefuse("Indique le montant reçu.")
        recupere = float(d.montant_recupere or 0) + montant
        maj["montant_recupere"] = recupere
        # Moins d'une unité de monnaie restante (centimes que l'écran arrondit) : le dossier est réglé
        maj["statut"] = "regle" if du and recupere > du - 1 else "paiement_partiel"
        _action(id_dossier, par, "paiement", f"Paiement reçu : {_fmt(montant)}" + (f" — {texte}" if texte else ""), montant)
    elif nature == "commentaire":
        if not texte:
            raise DossierRefuse("Le commentaire est vide.")
        _action(id_dossier, par, "commentaire", texte)
    elif nature == "statut":
        if statut not in STATUTS:
            raise DossierRefuse("Statut inconnu")
        if statut in ("irrecouvrable", "contentieux") and len(texte) < 5:
            raise DossierRefuse("Explique ta décision en quelques mots.")
        maj["statut"] = statut
        _action(id_dossier, par, "statut", f"{STATUTS[d.statut]} → {STATUTS[statut]}" + (f" : {texte}" if texte else ""))
    elif nature == "assignation":
        if desassigner:
            maj["assigne_a"] = None
            _action(id_dossier, par, "assignation", "Dossier désassigné")
        else:
            if not assigne_a:
                raise DossierRefuse("Choisis la personne.")
            maj["assigne_a"] = assigne_a
            _action(id_dossier, par, "assignation", f"Assigné à {assigne_a}")
    if "statut" in maj and maj["statut"] != "promesse" and d.statut == "promesse":
        maj.update(promesse_date=None, promesse_montant=None)
    if maj:
        nouveau = maj.get("statut", d.statut)
        maj["date_cloture"] = datetime.now() if nouveau in CLOS else None
        champs = ", ".join(f"{k} = :{k}" for k in maj)
        db.ecrire(f"UPDATE voicebank.dossiers_recouvrement SET {champs}, date_maj = LOCALTIMESTAMP, maj_par = :par "
                  "WHERE id_dossier = :i", {**maj, "par": par[:64], "i": id_dossier})
    d = _dossier(id_source, id_dossier)
    return {"id": d.id_dossier, "statut": d.statut, "libelle_statut": STATUTS[d.statut],
            "montant_recupere": float(d.montant_recupere or 0), "assigne_a": d.assigne_a,
            "promesse_date": d.promesse_date.isoformat() if d.promesse_date else None,
            "promesse_montant": float(d.promesse_montant) if d.promesse_montant is not None else None,
            "historique": historique(id_source, id_dossier)}


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


# ── Message de relance ─────────────────────────────────────────────────────────

def reglages(id_source: int) -> dict:
    v = db.ecrire("SELECT valeur FROM voicebank.parametres WHERE cle = :c", {"c": f"recouvrement:{id_source}"}).scalar()
    return {"paiement": "", "signature": "", "modele": MESSAGE_DEFAUT, **(v or {})}


def enregistrer_reglages(id_source: int, par: str, paiement: str, signature: str, modele: str | None) -> dict:
    import json
    valeur = {"paiement": paiement.strip()[:300], "signature": signature.strip()[:120],
              "modele": (modele or MESSAGE_DEFAUT).strip()[:800] or MESSAGE_DEFAUT}
    db.ecrire("INSERT INTO voicebank.parametres (cle, valeur, modifie_par) VALUES (:c, CAST(:v AS JSONB), :p) "
              "ON CONFLICT (cle) DO UPDATE SET valeur = EXCLUDED.valeur, modifie_par = EXCLUDED.modifie_par, "
              "date_modif = LOCALTIMESTAMP", {"c": f"recouvrement:{id_source}", "v": json.dumps(valeur), "p": par[:64]})
    return valeur


def message(reglage: dict, client: str | None, reference: str, montant: str) -> str:
    paiement = reglage.get("paiement") or ""
    texte = (reglage.get("modele") or MESSAGE_DEFAUT).format_map(_Defaut(
        client=client or "Madame, Monsieur", reference=reference, montant=montant,
        paiement=f" : {paiement}" if paiement else "", signature=reglage.get("signature") or ""))
    return re.sub(r"\s+", " ", texte).strip()


class _Defaut(dict):
    def __missing__(self, cle):
        return "{" + cle + "}"


def numero_international(tel: str | None, indicatif: str = "237") -> str | None:
    """Numéro au format international sans « + » (pour wa.me et sms:) ; 9 chiffres camerounais → +237."""
    if not tel:
        return None
    n = re.sub(r"\D", "", tel)
    if n.startswith("00"):
        n = n[2:]
    if len(n) == 9 and indicatif:
        n = indicatif + n
    return n if 8 <= len(n) <= 15 else None
