"""Données personnelles (loi n° 2024/017) : export, effacement d'un compte, durées de conservation."""
import json

import itertools

from tests.test_offre import MDP, ORGA, _h, _inscrire, _sql
from tests.test_organisations import NOUVEAU, PARTICULIER, _base, _lien, boite  # noqa: F401  (fixture)

_compteur = itertools.count(1)


def _abonne(client, type_client="organisation"):
    """Visiteur → paiement simulé → abonné (adresses propres à ce fichier). Retourne (email, en-têtes)."""
    email = f"dp{next(_compteur)}@exemple.cm"
    h = _h(_inscrire(client, email))
    corps = {"formule": "mois", "type_client": type_client, "accepte_conditions": True}
    if type_client == "organisation":
        corps["organisation"] = {**ORGA, "raison_sociale": f"Données perso {email}", "email": email}
    else:
        corps["particulier"] = {**PARTICULIER, "email": email}
    cmd = client.post("/abonnement/commander", headers=h, json=corps)
    assert cmd.status_code == 200, cmd.text
    v = client.get(f"/abonnement/verifier/{cmd.json()['reference']}", headers=h).json()
    return email, {"Authorization": f"Bearer {v['jeton']['access_token']}"}


def _membre(client, h, boite, role, nom):  # noqa: F811
    m = f"{nom}.{next(_compteur)}@exemple.cm"
    r = client.post("/organisation/membres", headers=h, json={"email": m, "nom_complet": nom.title(), "role_org": role})
    assert r.status_code == 200, r.text
    jeton, _ = _lien(boite, m)
    return m, _h(client.post("/auth/invitation", json={"identifiant": m, "jeton": jeton, "nouveau": NOUVEAU}))


def test_export_de_mes_donnees(client):
    h = _h(_inscrire(client, "export.donnees@exemple.cm"))
    client.post("/vocal/question", headers=h, json={"texte": "top 3 clients par solde"})
    r = client.get("/moi/donnees", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    d = json.loads(r.content)
    assert d["compte"]["email"] == "export.donnees@exemple.cm" and d["compte"]["role"] == "visiteur"
    assert d["questions_posees"][0]["question"] == "top 3 clients par solde"
    assert d["durees_de_conservation"]["paiements"] == "10 ans"
    texte = r.text
    for secret in ("hash_mdp", "$2b$", "secret_chiffre", "config_chiffree", "codes_secours"):
        assert secret not in texte, secret
    assert any(e["action"] == "export_donnees" for e in client.get("/moi/donnees", headers=h).json()["journal_d_activite"])


def test_effacement_par_le_titulaire(client):
    email = "efface.moi@exemple.cm"
    h = _h(_inscrire(client, email))
    client.post("/vocal/question", headers=h, json={"texte": "top 3 clients par solde"})
    assert client.get("/moi/effacement", headers=h).json()["possible"] is True
    assert client.post("/moi/supprimer", headers=h, json={"mot_de_passe": MDP, "confirmation": "oui"}).status_code == 400
    assert client.post("/moi/supprimer", headers=h, json={"mot_de_passe": "faux", "confirmation": "SUPPRIMER"}).status_code == 400
    r = client.post("/moi/supprimer", headers=h, json={"mot_de_passe": MDP, "confirmation": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    # Session fermée, connexion impossible, adresse libérée (nouvelle inscription possible)
    assert client.get("/auth/moi", headers=h).status_code == 401
    assert client.post("/auth/login", json={"nom": email, "mot_de_passe": MDP}).status_code == 401
    assert _sql("SELECT COUNT(*) FROM voicebank.utilisateurs WHERE nom = %s OR email = %s", (email, email))[0][0] == 0
    assert _sql("SELECT COUNT(*) FROM voicebank.logs_vocaux WHERE utilisateur = %s", (email,))[0][0] == 0
    pseudo = _sql("SELECT detail->>'pseudonyme' FROM voicebank.journal_audit WHERE action = 'compte_efface' "
                    "AND detail->>'compte' = %s", (email,))[0][0]
    p = _sql("SELECT actif, email, nom_complet, efface_le IS NOT NULL FROM voicebank.utilisateurs WHERE nom = %s", (pseudo,))
    assert p == [(False, None, None, True)]
    assert _inscrire(client, email).status_code == 200


def test_paiements_gardes_au_nom_du_pseudonyme(client, boite):  # noqa: F811
    email, h = _abonne(client, type_client="particulier")
    _base(client, h, "Ventes du particulier")
    r = client.post("/moi/supprimer", headers=h, json={"mot_de_passe": MDP, "confirmation": "SUPPRIMER"})
    assert r.status_code == 200, r.text
    pseudo = _sql("SELECT detail->>'pseudonyme' FROM voicebank.journal_audit WHERE action = 'compte_efface' "
                    "AND detail->>'compte' = %s", (email,))[0][0]
    assert _sql("SELECT COUNT(*) FROM voicebank.paiements WHERE utilisateur = %s AND statut = 'paye'", (pseudo,))[0][0] == 1
    assert _sql("SELECT COUNT(*) FROM voicebank.profils_facturation WHERE utilisateur = %s", (pseudo,))[0][0] == 1
    assert _sql("SELECT COUNT(*) FROM voicebank.sources_donnees WHERE proprietaire IN (%s, %s)", (email, pseudo))[0][0] == 0
    assert _sql("SELECT o.actif FROM voicebank.organisations o JOIN voicebank.utilisateurs u ON u.id_org = o.id_org "
                  "WHERE u.nom = %s", (pseudo,)) == [(False,)]


def test_organisation_dernier_administrateur_et_membre(client, boite):  # noqa: F811
    email, h = _abonne(client)
    membre, hm = _membre(client, h, boite, "analyste", "efface.membre")
    id_base = _base(client, h, "Base du membre")
    _sql("UPDATE voicebank.sources_donnees SET proprietaire = %s WHERE id_source = %s", (membre, id_base))
    # Seul administrateur avec un membre actif : refus expliqué
    r = client.get("/moi/effacement", headers=h).json()
    assert r["possible"] is False and "seul administrateur" in r["raison"]
    assert client.post("/moi/supprimer", headers=h, json={"mot_de_passe": MDP, "confirmation": "SUPPRIMER"}).status_code == 409
    # Le membre s'efface : sa base reste à l'organisation (transmise à l'administrateur)
    r = client.post("/moi/supprimer", headers=hm, json={"mot_de_passe": NOUVEAU, "confirmation": "supprimer"})
    assert r.status_code == 200, r.text
    assert _sql("SELECT proprietaire FROM voicebank.sources_donnees WHERE id_source = %s", (id_base,)) == [(email,)]
    noms = {m["nom"] for m in client.get("/organisation", headers=h).json()["data"]["membres"]}
    assert membre not in noms and not any(n.startswith("efface-") for n in noms)
    assert client.get("/moi/effacement", headers=h).json()["possible"] is True


def test_comptes_internes_et_effacement_par_l_administrateur(client, admin, analyste):
    assert client.get("/moi/effacement", headers=analyste).json()["possible"] is False
    assert client.post("/admin/utilisateurs/analyste1/effacer", headers=admin).status_code == 409
    assert client.post("/admin/utilisateurs/inconnu/effacer", headers=admin).status_code == 404
    _inscrire(client, "demande.par.mail@exemple.cm")
    assert client.post("/admin/utilisateurs/demande.par.mail@exemple.cm/effacer", headers=analyste).status_code == 403
    r = client.post("/admin/utilisateurs/demande.par.mail@exemple.cm/effacer", headers=admin)
    assert r.status_code == 200 and r.json()["pseudonyme"].startswith("efface-")
    assert client.post("/admin/utilisateurs/" + r.json()["pseudonyme"] + "/effacer", headers=admin).status_code == 404
    comptes = {c["nom"] for c in client.get("/admin/utilisateurs", headers=admin).json()["data"]}
    assert r.json()["pseudonyme"] not in comptes and "demande.par.mail@exemple.cm" not in comptes


def test_durees_de_conservation():
    from app import donnees_personnelles as dp
    _inscrire_direct = "INSERT INTO voicebank.utilisateurs (nom, role, hash_mdp, actif, doit_changer_mdp, email, essai_fin) " \
                       "VALUES ('essai.oublie@exemple.cm', 'visiteur', 'x', TRUE, FALSE, 'essai.oublie@exemple.cm', " \
                       "LOCALTIMESTAMP - INTERVAL '100 days')"
    _sql(_inscrire_direct)
    _sql("INSERT INTO voicebank.logs_vocaux (texte_original, utilisateur, date_requete) VALUES "
         "('ancienne', 'x', LOCALTIMESTAMP - INTERVAL '13 months'), ('recente', 'x', LOCALTIMESTAMP)")
    _sql("INSERT INTO voicebank.journal_audit (utilisateur, action, date_evenement) VALUES "
         "('x', 'tres_ancien', LOCALTIMESTAMP - INTERVAL '6 years'), ('x', 'recent_conserve', LOCALTIMESTAMP - INTERVAL '4 years')")
    _sql("INSERT INTO voicebank.echecs_connexion (identifiant, ip, echecs, dernier_echec) VALUES "
         "('vieux', '9.9.9.9', 2, LOCALTIMESTAMP - INTERVAL '2 days')")
    res = dp.appliquer_conservation()
    assert res["questions"] >= 1 and res["journal_audit"] >= 1 and res["echecs_connexion"] >= 1
    assert res["essais_effaces"] >= 1
    assert _sql("SELECT texte_original FROM voicebank.logs_vocaux WHERE utilisateur = 'x'") == [("recente",)]
    assert _sql("SELECT action FROM voicebank.journal_audit WHERE utilisateur = 'x'") == [("recent_conserve",)]
    assert _sql("SELECT COUNT(*) FROM voicebank.utilisateurs WHERE email = 'essai.oublie@exemple.cm'")[0][0] == 0


def test_l_application_ne_peut_ni_supprimer_un_compte_ni_effacer_l_audit_recent():
    import os
    import psycopg2
    # Compte de l'application (DATABASE_URL des tests) ; ne pas importer conftest : il recréerait la base
    with psycopg2.connect(os.environ["DATABASE_URL"].replace("postgresql+psycopg2://", "postgresql://")) as c:
        cur = c.cursor()
        for req in ("DELETE FROM voicebank.utilisateurs WHERE nom = 'rayan'",
                    "DELETE FROM voicebank.journal_audit",
                    "SELECT voicebank.pseudonymiser_compte('rayan', 'efface-x')"):
            try:
                cur.execute(req)
                raise AssertionError(req)
            except psycopg2.Error:
                c.rollback()
