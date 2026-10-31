"""Crédits à recouvrer dans la base d'une organisation, quel que soit son schéma.

On reprend la table de crédits reconnue pour le score de crédit (statut avec « retard », « défaut »…), puis :
* les crédits **en retard** ou **en défaut** deviennent des dossiers de recouvrement ;
* le montant dû est la colonne la plus parlante (« encours », « impayé », « reste dû »…, sinon le montant) ;
* le nom et le téléphone du client sont cherchés dans la table elle-même, sinon dans la table liée (clé étrangère
  ou nom de colonne « id_client » → « clients »), pour pouvoir appeler ou écrire ;
* les jours de retard sont calculés si une date d'échéance existe.
Lecture seule, sur 2 000 dossiers au plus.
"""
from datetime import date, datetime

import pandas as pd
from sqlglot import exp

from . import semantique as sem
from .risques import MOTS_CLOS, RisqueIndisponible, _jetons_valeur, _memo, table_credits
from .tableau import _c, _Executeur, _table

LIMITE = 2000
MOTS_RETARD = {"retard", "late", "overdue", "arrears", "impaye", "impayes", "echu"}
MOTS_DEFAUT = {"defaut", "default", "defaulted", "contentieux", "douteux", "npl", "charged", "chargedoff", "writeoff",
               "perte", "radie", "litige", "sinistre"}
MOTS_DU = {"encours", "outstanding", "restant", "reste", "du", "due", "impaye", "arrears", "solde", "balance", "capital"}
MOTS_ECHEANCE = {"echeance", "due", "prochaine", "next", "exigible", "retard"}


def etape(valeur) -> str | None:
    """« retard » (récupérable rapidement), « defaut » (plus difficile), ou None (crédit sain ou clos)."""
    j = _jetons_valeur(valeur)
    if j & MOTS_CLOS:
        return None
    if j & MOTS_DEFAUT:
        return "defaut"
    if j & MOTS_RETARD:
        return "retard"
    return None


def _colonne_du(t: dict):
    montants = [c for c in t["colonnes"] if c["role"] == "montant" and c["nature"] == "nombre" and not c.get("pii")]
    for c in montants:
        if set(sem.jetons(c["nom"])) & MOTS_DU:
            return c
    return next((c for c in montants if not set(sem.jetons(c["nom"])) & {"revenu", "income", "salaire", "mensualite"}),
                montants[0] if montants else None)


def _colonne_echeance(t: dict):
    return next((c for c in t["colonnes"] if c["role"] == "date" and set(sem.jetons(c["nom"])) & MOTS_ECHEANCE), None)


def _contact(profil: dict, t: dict):
    """(table du client, colonne de jointure dans les crédits, colonne cible, colonne nom, colonne téléphone)."""
    def cherche(table):
        noms = [c["nom"] for c in table["colonnes"] if c.get("pii") == "nom"]
        est_prenom = lambda n: bool(set(sem.jetons(n)) & {"prenom", "firstname", "first", "given"})  # noqa: E731
        prenom = next((n for n in noms if est_prenom(n)), None)
        nom = next((n for n in noms if n != prenom), None)
        tel = next((c["nom"] for c in table["colonnes"] if c.get("pii") == "telephone"), None)
        return nom, prenom, tel
    nom, prenom, tel = cherche(t)
    if nom and tel:
        return None, None, None, (nom, prenom), tel
    tables = {x["nom"]: x for x in profil.get("tables", []) if not x.get("erreur")}
    for r in profil.get("relations", []):
        if r["de"] == t["nom"] and r["vers"] in tables and r.get("colonne_cible"):
            n2, p2, t2 = cherche(tables[r["vers"]])
            if t2 or n2 or p2:
                return tables[r["vers"]], r["colonne"], r["colonne_cible"], (n2, p2) if (n2 or p2) else None, t2
    return None, None, None, (nom, prenom) if (nom or prenom) else None, tel


def credits_a_recouvrer(eng, type_source: str, profil: dict, cle) -> dict:
    """Crédits en retard ou en défaut, dans la monnaie de la base."""
    def calcul():
        tc = table_credits(profil)
        if tc is None:
            raise RisqueIndisponible("Aucune table de crédits avec un statut de retard ou de défaut n'a été reconnue dans "
                                     "cette base (ex. colonne « statut » avec « En retard », « En défaut »).")
        t, statut = tc
        valeurs = [v["valeur"] for v in statut.get("valeurs", [])]
        cibles = [v for v in valeurs if etape(v)]
        if not cibles:
            raise RisqueIndisponible("Aucun crédit en retard ou en défaut dans cette base.")
        ident = (t.get("cle_primaire") or [None])[0]
        if not ident:
            raise RisqueIndisponible(f"La table « {t['nom']} » n'a pas d'identifiant de crédit : impossible de suivre "
                                     "les dossiers un par un.")
        du, echeance = _colonne_du(t), _colonne_echeance(t)
        tclient, jointure, cible, noms, tel = _contact(profil, t)
        req = _Executeur(eng, type_source, profil)
        a = exp.to_identifier("cr", quoted=True)
        b = exp.to_identifier("cl", quoted=True)

        def col(nom, alias, table=a):
            return exp.alias_(exp.column(exp.to_identifier(nom, quoted=True), table=table), alias, quoted=True)
        champs = [col(ident, "ref"), col(statut["nom"], "statut")]
        if du:
            champs.append(col(du["nom"], "montant"))
        if echeance:
            champs.append(col(echeance["nom"], "echeance"))
        source_contact = b if tclient else a
        if noms and noms[0]:
            champs.append(col(noms[0], "nom", source_contact))
        if noms and noms[1]:
            champs.append(col(noms[1], "prenom", source_contact))
        if tel:
            champs.append(col(tel, "telephone", source_contact))
        q = exp.select(*champs).from_(exp.alias_(_table(t, req.schema), a, table=True))
        if tclient:
            q = q.join(exp.alias_(_table(tclient, req.schema), b, table=True),
                       on=exp.EQ(this=exp.column(exp.to_identifier(jointure, quoted=True), table=a),
                                 expression=exp.column(exp.to_identifier(cible, quoted=True), table=b)), join_type="left")
        q = q.where(exp.column(exp.to_identifier(statut["nom"], quoted=True), table=a).isin(*[exp.Literal.string(str(v)) for v in cibles]))
        lignes = req(q, LIMITE)
        if lignes is None and tclient:           # jointure refusée ou impossible : sans les coordonnées de la table liée
            champs = [c for c in champs if c.find(exp.Column).table != "cl"]
            q = exp.select(*champs).from_(exp.alias_(_table(t, req.schema), a, table=True)).where(
                exp.column(exp.to_identifier(statut["nom"], quoted=True), table=a).isin(*[exp.Literal.string(str(v)) for v in cibles]))
            lignes, tel = req(q, LIMITE), None
        if lignes is None:
            raise RisqueIndisponible("Lecture des crédits à recouvrer impossible.")
        aujourdhui = date.today()
        dossiers = []
        for l in lignes:
            et = etape(l.get("statut"))
            if not et or l.get("ref") is None:
                continue
            m = pd.to_numeric(l.get("montant"), errors="coerce")
            jours = None
            e = l.get("echeance")
            if e is not None:
                try:
                    d = e.date() if isinstance(e, datetime) else e if isinstance(e, date) else pd.to_datetime(e).date()
                    jours = max((aujourdhui - d).days, 0)
                except (ValueError, TypeError):
                    jours = None
            client = " ".join(str(x) for x in (l.get("prenom"), l.get("nom")) if x not in (None, "")) or None
            dossiers.append({"ref": str(l["ref"]), "etape": et, "statut_base": str(l.get("statut")),
                             "montant": None if pd.isna(m) else float(m), "jours_retard": jours,
                             "client": client, "telephone": None if l.get("telephone") in (None, "") else str(l["telephone"])})
        return {"table": t["nom"], "colonne_statut": statut["nom"], "colonne_montant": du["nom"] if du else None,
                "colonne_echeance": echeance["nom"] if echeance else None, "contact": bool(tel),
                "complet": len(lignes) < LIMITE, "dossiers": dossiers}
    return _memo(("recouvrement",) + tuple(cle), calcul)
