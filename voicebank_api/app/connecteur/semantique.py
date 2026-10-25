"""Vocabulaire métier (français / anglais) pour comprendre une base inconnue : rôle des colonnes,
entités des tables, domaine d'activité. Utilisé par l'analyse et par le moteur de questions local."""
import re
import unicodedata


def normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def jetons(nom: str) -> list[str]:
    """« CustomerID » → [customer, id] ; « date_ouverture » → [date, ouverture]."""
    nom = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(nom or ""))
    return [j for j in normaliser(nom).split() if j]


def singulier(mot: str) -> str:
    if len(mot) > 3 and mot.endswith(("s", "x")) and not mot.endswith(("ss", "us", "is")):
        return mot[:-1]
    return mot


def formes(mot: str) -> set[str]:
    """Formes possibles d'un mot : « branches » → {branches, branche, branch}, « agencies » → agency."""
    f = {mot, singulier(mot)}
    if len(mot) > 4 and mot.endswith("es"):
        f.add(mot[:-2])
    if len(mot) > 4 and mot.endswith("ies"):
        f.add(mot[:-3] + "y")
    return f


# ── Rôles des colonnes ─────────────────────────────────────────────────
ROLES = {
    "secret": {"password", "passwd", "pwd", "mdp", "motdepasse", "hash", "token", "secret", "salt", "cvv", "pin", "otp"},
    "drapeau_fraude": {"fraude", "fraud", "frauduleux", "frauduleuse", "fraudulent", "suspect", "suspicious",
                       "anomalie", "anomaly", "isfraud"},
    "montant": {"montant", "amount", "amt", "solde", "balance", "prix", "price", "cout", "cost", "total", "valeur",
                "value", "salaire", "salary", "revenu", "income", "depot", "deposit", "retrait", "withdrawal",
                "encours", "outstanding", "principal", "interet", "interest", "frais", "fee", "fees", "mensualite",
                "installment", "capital", "prime", "premium", "fcfa", "xaf", "eur", "usd", "ca", "chiffre",
                "debit", "credit", "paye", "paid", "du", "due", "plafond", "limit", "epargne", "savings", "loyer"},
    "taux": {"taux", "rate", "pct", "pourcentage", "percent", "ratio", "tx"},
    "score": {"score", "note", "rating", "risque", "risk", "notation", "probabilite", "proba"},
    "quantite": {"quantite", "qty", "quantity", "nombre", "nb", "count", "duree", "duration", "age", "jours",
                 "days", "anciennete", "tenure", "effectif"},
    "date": {"date", "dt", "jour", "day", "created", "updated", "modified", "timestamp", "heure", "time",
             "echeance", "debut", "fin", "start", "end", "ouverture", "opened", "closed", "cloture", "periode",
             "annee", "year", "naissance", "birth", "dob", "at", "le", "on", "valeur_date"},
    "statut": {"statut", "status", "etat", "state", "situation", "stage", "decision", "resultat", "result",
               "actif", "active", "valide", "approved", "approuve"},
    "geographie": {"ville", "city", "pays", "country", "region", "quartier", "district", "agence", "branch",
                   "departement", "province", "commune", "zone", "localite", "town", "state_province", "site"},
    "categorie": {"type", "categorie", "category", "classe", "class", "segment", "produit", "product", "canal",
                  "channel", "mode", "methode", "method", "genre", "sexe", "gender", "profession", "secteur",
                  "sector", "devise", "currency", "banque", "bank", "motif", "reason", "niveau", "level",
                  "garantie", "collateral", "offre", "plan", "groupe", "group", "nature", "famille", "family",
                  "marque", "brand", "operateur", "operator", "reseau", "network", "internationale", "diaspora"},
    "identifiant": {"id", "code", "ref", "reference", "numero", "num", "no", "uuid", "guid", "key", "cle",
                    "matricule", "identifiant"},
}
# Données personnelles : jamais envoyées à l'IA, masquées si demandé
PII = {
    "nom": {"nom", "name", "lastname", "surname", "prenom", "firstname", "fullname", "nomcomplet", "raisonsociale"},
    "email": {"email", "mail", "courriel"},
    "telephone": {"telephone", "tel", "phone", "mobile", "gsm", "portable", "msisdn"},
    "adresse": {"adresse", "address", "rue", "street", "bp", "postal", "zip"},
    "naissance": {"naissance", "birth", "dob", "birthday"},
    "identite": {"cni", "passport", "passeport", "nid", "nin", "ssn", "niu", "piece", "idcard", "cin"},
    "compte_bancaire": {"iban", "rib", "bic", "swift", "card", "carte", "pan", "cardnumber", "accountnumber"},
}

# ── Entités (tables) ───────────────────────────────────────────────────
ENTITES = {      # du plus précis au plus général : « LoanRepayments » → remboursements
    "remboursements": {"remboursement", "repayment", "echeance", "installment", "echeancier", "schedule"},
    "alertes": {"alerte", "alert", "fraude", "fraud", "incident", "anomalie", "suspicion"},
    "sinistres": {"sinistre", "claim", "indemnisation"},
    "contrats": {"police", "policy", "contrat", "contract", "souscription", "subscription"},
    "épargne": {"epargne", "saving", "savings"},
    "groupes": {"tontine", "groupe", "group", "association", "cooperative", "gie"},
    "transactions": {"transaction", "txn", "trx", "operation", "mouvement", "movement", "transfer", "transfert",
                     "virement", "payment", "paiement", "ecriture", "entry", "versement", "retrait", "depot"},
    "crédits": {"credit", "pret", "loan", "financement", "microcredit", "dossier", "emprunt"},
    "comptes": {"compte", "account", "acct", "wallet", "portefeuille"},
    "clients": {"client", "customer", "cust", "membre", "member", "adherent", "abonne", "beneficiaire",
                "souscripteur", "assure", "tiers", "partner", "partenaire", "contact", "person", "personne"},
    "agences": {"agence", "branch", "guichet", "agency", "succursale", "office"},
    "employés": {"employe", "employee", "staff", "agent", "collaborateur", "gestionnaire", "conseiller", "officer"},
    "produits": {"produit", "product", "offre", "article", "item", "service"},
    "ventes": {"facture", "invoice", "vente", "sale", "commande", "order", "achat", "purchase"},
}
NON_PERSONNES = (set().union(*(m for k, m in ENTITES.items() if k not in ("clients", "employés")))
                 | ROLES["geographie"] | ROLES["categorie"] | {"company", "societe", "entreprise", "file", "fichier"})
DOMAINES = [
    ("assurance", {"contrats", "sinistres"}),
    ("microfinance", {"groupes", "épargne"}),
    ("banque", {"comptes", "transactions", "crédits", "remboursements"}),
    ("commerce", {"ventes", "produits"}),
]
LIBELLES_ROLES = {
    "identifiant": "Identifiant", "montant": "Montant", "quantite": "Quantité", "taux": "Taux", "score": "Score",
    "date": "Date", "statut": "Statut", "categorie": "Catégorie", "geographie": "Lieu", "drapeau_fraude": "Fraude",
    "texte": "Texte", "mesure": "Mesure", "secret": "Secret (jamais lu)",
}


def role_par_nom(nom: str) -> tuple[str | None, str | None]:
    """(rôle, type de donnée personnelle) d'après le nom de la colonne."""
    j = jetons(nom)
    colle = "".join(j)
    ens = set(j) | {colle} | {singulier(x) for x in j}
    pii = next((k for k, mots in PII.items() if ens & mots), None)
    if pii == "nom" and ens & NON_PERSONNES:
        pii = None          # « branch_name », « nom_produit » : pas une personne
    if ens & ROLES["secret"]:
        return "secret", None
    # « numero_compte », « account_number » : identifiant bancaire personnel
    if ({"numero", "num", "number", "no"} & ens) and ({"compte", "account", "carte", "card"} & ens):
        return "identifiant", "compte_bancaire"
    if pii == "naissance":
        return "date", pii
    forts = {"type", "categorie", "category", "statut", "status", "etat", "state", "mode", "canal", "channel",
             "segment", "classe", "class", "niveau", "level"}
    if ens & forts and not ens & ROLES["drapeau_fraude"]:
        return ("statut" if ens & ROLES["statut"] else "categorie"), pii
    for role in ("drapeau_fraude", "date", "taux", "score", "montant", "quantite", "statut", "geographie",
                 "categorie", "identifiant"):
        if ens & ROLES[role]:
            # « id_client » est un identifiant même s'il contient un nom d'entité
            if role != "identifiant" and ({"id", "uuid", "guid"} & set(j)) and len(j) <= 3:
                return "identifiant", pii
            return role, pii
    return None, pii


def entite_table(nom: str) -> str | None:
    j = set().union(*(formes(x) for x in jetons(nom))) | {"".join(jetons(nom))} if jetons(nom) else set()
    for entite, mots in ENTITES.items():
        if j & mots:
            return entite
    return None


def domaine(entites: set[str]) -> str:
    for nom, requises in DOMAINES:
        if len(entites & requises) >= (1 if nom in ("assurance", "microfinance") else 2):
            return nom
    if "crédits" in entites:
        return "banque"
    return "générique"


def humaniser(nom: str) -> str:
    return " ".join(jetons(nom)) or str(nom)


# ── Traductions pour comprendre une base en anglais avec une question en français ──
TRADUCTIONS = {
    "canal": {"channel"}, "canaux": {"channel"}, "ville": {"city", "town"}, "pays": {"country"},
    "statut": {"status", "state"}, "etat": {"status", "state"}, "solde": {"balance"}, "montant": {"amount"},
    "agence": {"branch", "agency"}, "devise": {"currency"}, "taux": {"rate"}, "client": {"customer"},
    "produit": {"product"}, "genre": {"gender"}, "sexe": {"gender", "sex"}, "date": {"date"},
    "categorie": {"category"}, "region": {"region", "state"}, "employe": {"employee", "staff"},
    "pret": {"loan"}, "credit": {"loan", "credit"}, "paiement": {"payment"}, "compte": {"account"},
    "fraude": {"fraud"}, "interet": {"interest"}, "duree": {"duration", "term", "tenure"},
    "revenu": {"income", "revenue"}, "salaire": {"salary"}, "secteur": {"sector", "industry"},
    "profession": {"occupation", "job", "profession"}, "age": {"age"}, "prix": {"price"}, "vente": {"sale"},
    "facture": {"invoice"}, "commande": {"order"}, "quantite": {"quantity", "qty"}, "mois": {"month"},
    "annee": {"year"}, "operateur": {"operator", "carrier"}, "frais": {"fee", "fees"},
}
# Valeurs fréquentes : « en retard » doit trouver « late » ou « overdue »
VALEURS_SYNONYMES = {
    "retard": {"late", "overdue", "arrears", "past due", "en retard", "retard"},
    "defaut": {"default", "defaulted", "en defaut", "defaut", "npl"},
    "actif": {"active", "actif", "open", "ouvert", "en cours", "current"},
    "cours": {"active", "en cours", "current", "ongoing"},
    "clos": {"closed", "clos", "cloture", "ferme", "settled", "repaid", "rembourse"},
    "rembourse": {"repaid", "settled", "closed", "paid", "rembourse"},
    "paye": {"paid", "settled", "paye", "regle"},
    "attente": {"pending", "en attente", "waiting"},
    "annule": {"cancelled", "canceled", "annule", "void"},
    "rejete": {"rejected", "declined", "refused", "rejete", "refuse"},
    "approuve": {"approved", "accepted", "approuve", "accepte", "valide"},
    "echoue": {"failed", "echoue", "error"},
    "homme": {"m", "male", "homme", "h"}, "femme": {"f", "female", "femme"},
}


def mots_etendus(mots) -> set[str]:
    """Mots de la question + leurs formes + leurs traductions anglaises."""
    base = set().union(*(formes(m) for m in mots)) if mots else set()
    res = set(base)
    for m in base:
        res |= TRADUCTIONS.get(m, set())
    return res
