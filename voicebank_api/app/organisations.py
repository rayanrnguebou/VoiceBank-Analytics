"""Organisations clientes : abonnement partagé, administrateur d'organisation, membres invités par e-mail.

* L'abonnement appartient à l'ORGANISATION : tous ses membres y ont accès tant qu'il est valide.
* Celui qui paie le premier abonnement devient l'administrateur de son organisation. Il invite des
  membres (analystes ou administrateurs) dans la limite de sa formule ; un particulier a un seul compte.
* Un membre reçoit un e-mail d'invitation avec un lien d'activation (valable INVITATION_HEURES heures,
  usage unique) pour choisir lui-même son mot de passe. Sans service d'e-mail, l'administrateur reçoit à
  la place un mot de passe provisoire à transmettre.
"""
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote

from sqlalchemy import text

from . import config, courriel, db
from .securite import (EMAIL_VALIDE, CompteRefuse, Utilisateur, hacher, mdp_provisoire, verifier_politique)

log = logging.getLogger("voicebank")

ROLES_ORG = {"admin": "Administrateur", "analyste": "Analyste"}
FORMULES_LIBELLES = {k: v[0] for k, v in config.FORMULES.items()}


def _date(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _montant(m: int, devise: str = "XAF") -> str:
    return f"{m:,}".replace(",", " ") + (" FCFA" if devise in ("XAF", "XOF") else f" {devise}")


def limite_comptes(type_org: str, formule: str | None) -> int:
    if type_org == "particulier":
        return 1
    return config.COMPTES_PAR_FORMULE.get(formule or "", config.COMPTES_PAR_FORMULE["jour"])


def _org(id_org: int):
    r = db.ecrire("SELECT id_org, nom, type_org, formule, abonnement_fin, actif, date_creation, "
                  "COALESCE(abonnement_fin > LOCALTIMESTAMP, FALSE) AS active "
                  "FROM voicebank.organisations WHERE id_org = :o", {"o": id_org})
    if not r.lignes:
        raise CompteRefuse("Organisation introuvable")
    return r.lignes[0]


def infos(u: Utilisateur) -> dict:
    o = _org(u.id_org)
    membres = db.ecrire(
        "SELECT nom, nom_complet, email, role_org, actif, doit_changer_mdp, derniere_connexion, date_creation, "
        "COALESCE(doit_changer_mdp AND mdp_provisoire_expire < LOCALTIMESTAMP, FALSE) AS invitation_expiree "
        "FROM voicebank.utilisateurs WHERE id_org = :o ORDER BY actif DESC, role_org, nom", {"o": u.id_org}).lignes
    actifs = sum(1 for m in membres if m.actif)
    return {
        "id": o.id_org, "nom": o.nom, "type": o.type_org, "formule": o.formule,
        "formule_libelle": FORMULES_LIBELLES.get(o.formule or "", None),
        "abonnement_fin": o.abonnement_fin.isoformat() if o.abonnement_fin else None, "active": o.active,
        "limite_comptes": limite_comptes(o.type_org, o.formule), "comptes_actifs": actifs,
        "mon_role": u.role_org, "peut_gerer": u.admin_org and o.type_org == "organisation",
        "email_disponible": courriel.disponible(),
        "membres": [{
            "nom": m.nom, "nom_complet": m.nom_complet, "email": m.email, "role_org": m.role_org, "actif": m.actif,
            "statut": ("desactive" if not m.actif else "invitation_expiree" if m.invitation_expiree
                       else "invitation_en_attente" if m.doit_changer_mdp else "actif"),
            "derniere_connexion": m.derniere_connexion.isoformat() if m.derniere_connexion else None,
            "moi": m.nom == u.nom} for m in membres],
    }


# ── Création à l'activation d'un abonnement ──────────────────────────

def activer_abonnement(conn, utilisateur: str, formule: str, jours: int) -> tuple[int, datetime]:
    """Dans la transaction du paiement : crée l'organisation si besoin (le payeur en devient
    l'administrateur), puis prolonge son abonnement. Retourne (id_org, nouvelle fin)."""
    u = conn.execute(text("SELECT nom, id_org, nom_complet FROM voicebank.utilisateurs WHERE nom = :u FOR UPDATE"),
                     {"u": utilisateur}).first()
    id_org = u.id_org
    f = conn.execute(text("SELECT type_client, informations FROM voicebank.profils_facturation WHERE utilisateur = :u"),
                     {"u": utilisateur}).first()
    type_org = (f.type_client if f else None) or "particulier"
    infos_f = (f.informations if f else None) or {}
    nom = (infos_f.get("raison_sociale") if type_org == "organisation" else None) \
        or infos_f.get("nom_complet") or u.nom_complet or utilisateur
    if id_org is not None and f is not None:
        # Renouvellement : un particulier qui passe à une formule « Organisation » change de type
        conn.execute(text("UPDATE voicebank.organisations SET type_org = :t, nom = CASE WHEN :t = 'organisation' "
                          "THEN :n ELSE nom END WHERE id_org = :o"), {"t": type_org, "n": str(nom)[:150], "o": id_org})
    if id_org is None:
        id_org = conn.execute(text(
            "INSERT INTO voicebank.organisations (nom, type_org, cree_par) VALUES (:n, :t, :u) RETURNING id_org"),
            {"n": str(nom)[:150], "t": type_org, "u": utilisateur}).scalar()
        conn.execute(text("UPDATE voicebank.utilisateurs SET id_org = :o, role_org = 'admin' WHERE nom = :u"),
                     {"o": id_org, "u": utilisateur})
        conn.execute(text("UPDATE voicebank.sources_donnees SET id_org = :o WHERE proprietaire = :u AND id_org IS NULL"),
                     {"o": id_org, "u": utilisateur})
    fin = conn.execute(text(
        "UPDATE voicebank.organisations SET formule = :f, actif = TRUE, abonnement_fin = "
        "GREATEST(COALESCE(abonnement_fin, LOCALTIMESTAMP), LOCALTIMESTAMP) + make_interval(days => :j) "
        "WHERE id_org = :o RETURNING abonnement_fin"), {"f": formule, "j": jours, "o": id_org}).scalar()
    conn.execute(text("UPDATE voicebank.utilisateurs SET role = 'client', abonnement_fin = :fin, formule = :f "
                      "WHERE nom = :u AND role IN ('visiteur', 'client')"), {"u": utilisateur, "fin": fin, "f": formule})
    return id_org, fin


# ── Invitations ──────────────────────────────────────────────────────

def _empreinte(nom: str, jeton: str) -> str:
    return hmac.new(config.JWT_SECRET.encode(), f"invitation:{nom}:{jeton}".encode(), hashlib.sha256).hexdigest()


def _lien(nom: str, jeton: str) -> str:
    return f"{config.URL_INTERFACE}/?invitation={jeton}&compte={quote(nom)}"


def message_invitation(nom_complet: str | None, organisation: str, invite_par: str, role_org: str,
                       identifiant: str, lien: str) -> courriel.Message:
    return courriel.Message(
        sujet=f"Invitation à rejoindre {organisation} sur VoiceBank Analytics",
        titre=f"Vous êtes invité(e) à rejoindre {organisation}",
        salutation=f"Bonjour {nom_complet}," if nom_complet else "Bonjour,",
        paragraphes=[f"{invite_par} vous a créé un compte sur VoiceBank Analytics, la plateforme d'analyse vocale des "
                     f"données bancaires de {organisation}.",
                     "Pour l'activer, choisissez votre mot de passe en cliquant sur le bouton ci-dessous :"],
        details=[("Organisation", organisation), ("Identifiant", identifiant), ("Rôle", ROLES_ORG.get(role_org, role_org)),
                 ("Lien valable", f"{config.INVITATION_HEURES} heures")],
        bouton=("Activer mon compte", lien),
        apres=["Une fois connecté(e), posez vos questions à la voix ou au clavier : réponses chiffrées, graphiques "
               "et analyse parlée sur les données de votre organisation."],
        apercu=f"{invite_par} vous invite à rejoindre {organisation}",
        note="Si vous ne vous attendiez pas à cette invitation, ignorez ce message : aucun compte ne sera activé sans vous.")


def _creer_invitation(nom: str) -> str:
    jeton = secrets.token_urlsafe(32)
    db.ecrire("UPDATE voicebank.codes_recuperation SET utilise = TRUE WHERE utilisateur = :n AND NOT utilise "
              "AND type_code = 'invitation'", {"n": nom})
    db.ecrire("INSERT INTO voicebank.codes_recuperation (utilisateur, empreinte, expire, type_code) "
              "VALUES (:n, :e, LOCALTIMESTAMP + :d, 'invitation')",
              {"n": nom, "e": _empreinte(nom, jeton), "d": timedelta(hours=config.INVITATION_HEURES)})
    return jeton


def _nom_affiche(nom: str) -> str:
    r = db.ecrire("SELECT COALESCE(nom_complet, nom) FROM voicebank.utilisateurs WHERE nom = :n", {"n": nom})
    return r.scalar() or nom


def _envoyer_invitation(nom: str, par: str) -> dict:
    """Envoi SYNCHRONE (l'administrateur doit savoir si l'e-mail est parti). Sans e-mail : mot de passe provisoire."""
    l = db.ecrire("SELECT u.nom, u.email, u.nom_complet, u.role_org, o.nom AS organisation FROM voicebank.utilisateurs u "
                  "JOIN voicebank.organisations o ON o.id_org = u.id_org WHERE u.nom = :n", {"n": nom}).lignes[0]
    mdp = mdp_provisoire()
    db.ecrire("UPDATE voicebank.utilisateurs SET hash_mdp = :h, doit_changer_mdp = TRUE, mdp_provisoire_expire = "
              "LOCALTIMESTAMP + :d, echecs_connexion = 0, verrouille_jusqua = NULL, version_jeton = version_jeton + 1 "
              "WHERE nom = :n", {"n": nom, "h": hacher(mdp), "d": timedelta(hours=config.INVITATION_HEURES)})
    if courriel.disponible() and l.email:
        jeton = _creer_invitation(nom)
        try:
            courriel.envoyer_message(l.email, message_invitation(
                l.nom_complet, l.organisation, _nom_affiche(par), l.role_org, nom, _lien(nom, jeton)))
            return {"invitation_envoyee": True, "email": l.email}
        except courriel.EnvoiImpossible as e:
            log.warning("Invitation de %s non envoyée : %s", nom, e)
            return {"invitation_envoyee": False, "erreur_envoi": str(e), "mot_de_passe_provisoire": mdp,
                    "valable_heures": config.INVITATION_HEURES}
    return {"invitation_envoyee": False, "mot_de_passe_provisoire": mdp, "valable_heures": config.INVITATION_HEURES}


def inviter(par: Utilisateur, email: str, nom_complet: str, role_org: str) -> dict:
    if not par.admin_org:
        raise CompteRefuse("Réservé à l'administrateur de l'organisation")
    o = _org(par.id_org)
    if o.type_org != "organisation":
        raise CompteRefuse("Un abonnement particulier comprend un seul compte. Choisissez une formule « Organisation » "
                           "pour inviter vos collègues.")
    if not o.active:
        raise CompteRefuse("L'abonnement de l'organisation est échu : renouvelez-le pour inviter des membres.")
    if role_org not in ROLES_ORG:
        raise CompteRefuse("Rôle inconnu")
    email = email.strip().lower()
    if len(email) > 64 or not EMAIL_VALIDE.fullmatch(email):
        raise CompteRefuse("Adresse e-mail invalide")
    nom_complet = " ".join(nom_complet.split())[:120]
    if len(nom_complet) < 2:
        raise CompteRefuse("Indique le nom complet de la personne")
    limite = limite_comptes(o.type_org, o.formule)
    with db.moteur_app.begin() as conn:
        # Verrou sur l'organisation : deux invitations simultanées ne dépassent pas la limite
        conn.execute(text("SELECT 1 FROM voicebank.organisations WHERE id_org = :o FOR UPDATE"), {"o": o.id_org})
        n = conn.execute(text("SELECT COUNT(*) FROM voicebank.utilisateurs WHERE id_org = :o AND actif"),
                         {"o": o.id_org}).scalar()
        if n >= limite:
            raise CompteRefuse(f"Limite atteinte : votre formule comprend {limite} comptes. Désactivez un compte ou "
                               "passez à une formule supérieure.")
        if conn.execute(text("SELECT 1 FROM voicebank.utilisateurs WHERE nom = :e OR LOWER(email) = :e"),
                        {"e": email}).first():
            raise CompteRefuse("Un compte existe déjà avec cette adresse e-mail")
        conn.execute(text(
            "INSERT INTO voicebank.utilisateurs (nom, role, hash_mdp, doit_changer_mdp, mdp_provisoire_expire, cree_par, "
            "email, nom_complet, id_org, role_org) VALUES (:e, 'client', :h, TRUE, LOCALTIMESTAMP + :d, :p, :e, :c, :o, :r)"),
            {"e": email, "h": hacher(secrets.token_urlsafe(24)), "d": timedelta(hours=config.INVITATION_HEURES),
             "p": par.nom, "c": nom_complet, "o": o.id_org, "r": role_org})
    return {"nom": email, "role_org": role_org, **_envoyer_invitation(email, par.nom)}


def _membre(par: Utilisateur, nom: str):
    if not par.admin_org:
        raise CompteRefuse("Réservé à l'administrateur de l'organisation")
    r = db.ecrire("SELECT nom, role_org, actif, doit_changer_mdp FROM voicebank.utilisateurs WHERE nom = :n AND id_org = :o",
                  {"n": nom, "o": par.id_org})
    if not r.lignes:
        raise CompteRefuse("Membre introuvable")
    return r.lignes[0]


def renvoyer_invitation(par: Utilisateur, nom: str) -> dict:
    m = _membre(par, nom)
    if not m.actif:
        raise CompteRefuse("Réactive d'abord ce compte")
    if nom == par.nom:
        raise CompteRefuse("Utilise « Changer mon mot de passe » pour ton propre compte")
    return {"nom": nom, **_envoyer_invitation(nom, par.nom)}


def modifier_membre(par: Utilisateur, nom: str, role_org: str | None, actif: bool | None) -> dict:
    m = _membre(par, nom)
    if role_org is not None and role_org not in ROLES_ORG:
        raise CompteRefuse("Rôle inconnu")
    if nom == par.nom and (actif is False or (role_org and role_org != "admin")):
        raise CompteRefuse("Tu ne peux pas désactiver ton propre compte ni retirer tes droits d'administrateur")
    if m.role_org == "admin" and m.actif and (actif is False or (role_org and role_org != "admin")):
        n = db.ecrire("SELECT COUNT(*) FROM voicebank.utilisateurs WHERE id_org = :o AND role_org = 'admin' AND actif "
                      "AND nom <> :n", {"o": par.id_org, "n": nom}).scalar()
        if not n:
            raise CompteRefuse("L'organisation doit garder au moins un administrateur actif")
    if actif is True and not m.actif:
        o = _org(par.id_org)
        n = db.ecrire("SELECT COUNT(*) FROM voicebank.utilisateurs WHERE id_org = :o AND actif", {"o": par.id_org}).scalar()
        if n >= limite_comptes(o.type_org, o.formule):
            raise CompteRefuse("Limite de comptes de la formule atteinte : désactive d'abord un autre compte")
    changements = {}
    if role_org is not None and role_org != m.role_org:
        changements["role_org"] = role_org
    if actif is not None and actif != m.actif:
        changements["actif"] = actif
    if changements:
        db.ecrire("UPDATE voicebank.utilisateurs SET role_org = COALESCE(:r, role_org), actif = COALESCE(:a, actif), "
                  "version_jeton = version_jeton + 1 WHERE nom = :n AND id_org = :o",
                  {"r": changements.get("role_org"), "a": changements.get("actif"), "n": nom, "o": par.id_org})
    return changements


def renommer(par: Utilisateur, nom: str):
    if not par.admin_org:
        raise CompteRefuse("Réservé à l'administrateur de l'organisation")
    nom = " ".join(nom.split())[:150]
    if len(nom) < 2:
        raise CompteRefuse("Nom trop court")
    db.ecrire("UPDATE voicebank.organisations SET nom = :n WHERE id_org = :o", {"n": nom, "o": par.id_org})


def activer_invitation(identifiant: str, jeton: str, nouveau: str) -> tuple[Utilisateur, int]:
    """Lien d'invitation → mot de passe choisi par la personne, compte actif, connexion directe."""
    refus = "Lien d'activation invalide ou expiré. Demande à ton administrateur de renvoyer l'invitation."
    nom = identifiant.strip().lower()
    verifier_politique(nouveau, nom.split("@")[0])
    r = db.ecrire("SELECT c.id_code, c.empreinte FROM voicebank.codes_recuperation c JOIN voicebank.utilisateurs u "
                  "ON u.nom = c.utilisateur WHERE c.utilisateur = :n AND c.type_code = 'invitation' AND NOT c.utilise "
                  "AND c.expire > LOCALTIMESTAMP AND u.actif ORDER BY c.date_creation DESC LIMIT 1", {"n": nom})
    c = r.lignes[0] if r.lignes else None
    if c is None or not hmac.compare_digest(c.empreinte, _empreinte(nom, jeton or "")):
        raise CompteRefuse(refus)
    if not db.ecrire("UPDATE voicebank.codes_recuperation SET utilise = TRUE WHERE id_code = :i AND NOT utilise",
                     {"i": c.id_code}).rowcount:
        raise CompteRefuse(refus)
    l = db.ecrire("UPDATE voicebank.utilisateurs SET hash_mdp = :h, doit_changer_mdp = FALSE, mdp_provisoire_expire = NULL, "
                  "echecs_connexion = 0, verrouille_jusqua = NULL, date_modif_mdp = LOCALTIMESTAMP, "
                  "derniere_connexion = LOCALTIMESTAMP, version_jeton = version_jeton + 1 WHERE nom = :n "
                  "RETURNING nom, role, id_org, role_org, version_jeton", {"n": nom, "h": hacher(nouveau)}).lignes[0]
    return Utilisateur(l.nom, l.role, False, False, l.id_org, l.role_org), l.version_jeton


# ── E-mails liés à l'abonnement ──────────────────────────────────────

def message_paiement(nom_complet: str | None, organisation: str, type_org: str, formule: str, montant: int,
                     devise: str, reference: str, fin, limite: int) -> courriel.Message:
    details = [("Formule", FORMULES_LIBELLES.get(formule, formule)), ("Montant payé", _montant(montant, devise)),
               ("Référence", reference), ("Date", _date(datetime.now())), ("Accès jusqu'au", _date(fin))]
    if type_org == "organisation":
        details.insert(0, ("Organisation", organisation))
        details.append(("Comptes inclus", str(limite)))
    return courriel.Message(
        sujet=f"Paiement confirmé : abonnement {FORMULES_LIBELLES.get(formule, formule)} VoiceBank Analytics",
        titre="Merci, votre abonnement est actif",
        salutation=f"Bonjour {nom_complet}," if nom_complet else "Bonjour,",
        paragraphes=["Nous avons bien reçu votre paiement. Voici le récapitulatif de votre abonnement :"],
        details=details,
        bouton=("Accéder à VoiceBank", config.URL_INTERFACE),
        apres=(["En tant qu'administrateur de votre organisation, invitez vos analystes depuis le menu « Mon organisation » : "
                "chacun recevra un e-mail pour activer son compte, et tous partagent cet abonnement."]
               if type_org == "organisation" else
               ["Vous pouvez dès maintenant brancher vos propres données (menu « Mes données ») et les interroger à la voix."]),
        apercu=f"Abonnement actif jusqu'au {_date(fin)}",
        note="Conservez cet e-mail : il tient lieu de reçu. Pour une facture au nom de votre organisation, "
             "répondez à l'adresse de contact indiquée.")


def envoyer_recu(reference: str):
    """Après activation d'un paiement : reçu à l'e-mail de facturation (et au compte s'il diffère)."""
    if not courriel.disponible():
        return
    r = db.ecrire("SELECT p.reference, p.formule, p.montant, p.devise, p.abonnement_fin, u.email, u.nom, u.nom_complet, "
                  "o.nom AS organisation, o.type_org, o.formule AS formule_org, f.informations "
                  "FROM voicebank.paiements p JOIN voicebank.utilisateurs u ON u.nom = p.utilisateur "
                  "LEFT JOIN voicebank.organisations o ON o.id_org = u.id_org "
                  "LEFT JOIN voicebank.profils_facturation f ON f.utilisateur = p.utilisateur WHERE p.reference = :r",
                  {"r": reference})
    if not r.lignes:
        return
    l = r.lignes[0]
    infos_f = l.informations or {}
    m = message_paiement(infos_f.get("responsable") or infos_f.get("nom_complet") or l.nom_complet,
                         l.organisation or "", l.type_org or "particulier", l.formule, l.montant, l.devise, l.reference,
                         l.abonnement_fin, limite_comptes(l.type_org or "particulier", l.formule_org))
    destinataires = {x.strip().lower() for x in (infos_f.get("email"), l.email or (l.nom if "@" in l.nom else None)) if x}
    for d in destinataires:
        courriel.envoyer_en_arriere_plan(d, m)


def message_bienvenue_essai(nom_complet: str | None, jours: int) -> courriel.Message:
    return courriel.Message(
        sujet="Bienvenue sur VoiceBank Analytics : votre essai gratuit a commencé",
        titre="Bienvenue sur VoiceBank Analytics",
        salutation=f"Bonjour {nom_complet}," if nom_complet else "Bonjour,",
        paragraphes=[f"Votre essai gratuit de {jours} jours est ouvert. Vous pouvez explorer toutes les fonctions sur "
                     "des données bancaires de démonstration (fictives) :"],
        details=[("Assistant vocal", "posez vos questions en français, à la voix ou au clavier"),
                 ("Fraude", "alertes et analyse de transaction par IA"),
                 ("Crédit", "score de défaut expliqué facteur par facteur"),
                 ("Vos données", "brancher votre base ou vos fichiers Excel après abonnement")],
        bouton=("Commencer", config.URL_INTERFACE),
        apres=["Pour utiliser VoiceBank avec les données de votre organisation et inviter vos collègues, choisissez une "
               "formule depuis le menu « Abonnement »."],
        apercu=f"Votre essai gratuit de {jours} jours est ouvert")


def lister() -> list[dict]:
    """Toutes les organisations (super-administrateur)."""
    r = db.ecrire("SELECT o.id_org, o.nom, o.type_org, o.formule, o.abonnement_fin, o.actif, o.date_creation, "
                  "COALESCE(o.abonnement_fin > LOCALTIMESTAMP, FALSE) AS active, "
                  "(SELECT COUNT(*) FROM voicebank.utilisateurs u WHERE u.id_org = o.id_org AND u.actif) AS membres, "
                  "(SELECT string_agg(u.nom, ', ') FROM voicebank.utilisateurs u WHERE u.id_org = o.id_org "
                  " AND u.role_org = 'admin' AND u.actif) AS administrateurs, "
                  "(SELECT COALESCE(SUM(p.montant), 0) FROM voicebank.paiements p WHERE p.id_org = o.id_org "
                  " AND p.statut = 'paye') AS total_paye "
                  "FROM voicebank.organisations o ORDER BY o.date_creation DESC")
    return [{**{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in l._mapping.items()},
             "limite_comptes": limite_comptes(l.type_org, l.formule)} for l in r.lignes]
