"""Organisations clientes : abonnement partagé, administrateur d'organisation, invitations par e-mail,
limite de comptes selon la formule, particuliers à compte unique, bases partagées, cloisonnement."""
import re
from urllib.parse import parse_qs, urlsplit

import pytest

from app import config
from tests.test_offre import MDP, ORGA, _h, _inscrire, _sql
from tests.test_recuperation import capturer

NOUVEAU = "Mangrove-Kribi-2027!"
PARTICULIER = {"nom_complet": "Paul Ndzi", "profession": "Analyste crédit", "pays": "Cameroun", "ville": "Yaoundé",
               "email": "paul.ndzi@exemple.cm", "telephone": "+237 677 00 00 00"}
_n = [0]


@pytest.fixture
def boite(monkeypatch):
    monkeypatch.setattr(config, "BREVO_API_KEY", "cle-de-test")
    monkeypatch.setattr(config, "EMAIL_EXPEDITEUR", "no-reply@voicebank.test")
    monkeypatch.setattr(config, "PAIEMENT_SIMULATION", True)
    return capturer(monkeypatch, [])


def _abonne(client, formule="mois", type_client="organisation", raison="Coopérative Test"):
    """Visiteur → paiement simulé → abonné. Retourne (email, en-têtes)."""
    _n[0] += 1
    email = f"org{_n[0]}@exemple.cm"
    h = _h(_inscrire(client, email))
    corps = {"formule": formule, "type_client": type_client, "accepte_conditions": True}
    if type_client == "organisation":
        corps["organisation"] = {**ORGA, "raison_sociale": f"{raison} {_n[0]}", "email": email}
    else:
        corps["particulier"] = {**PARTICULIER, "email": email}
    cmd = client.post("/abonnement/commander", headers=h, json=corps)
    assert cmd.status_code == 200, cmd.text
    v = client.get(f"/abonnement/verifier/{cmd.json()['reference']}", headers=h).json()
    assert v["statut"] == "paye", v
    return email, {"Authorization": f"Bearer {v['jeton']['access_token']}"}


def _lien(boite, email):
    m = [e for e in boite if e["a"] == email and e["bouton"] and "invitation=" in e["bouton"][1]]
    assert m, boite
    q = parse_qs(urlsplit(m[-1]["bouton"][1]).query)
    return q["invitation"][0], q["compte"][0]


def test_le_payeur_devient_administrateur_de_son_organisation(client, boite):
    email, h = _abonne(client)
    o = client.get("/organisation", headers=h).json()["data"]
    assert o["type"] == "organisation" and o["nom"].startswith("Coopérative Test")
    assert o["mon_role"] == "admin" and o["peut_gerer"] and o["limite_comptes"] == config.COMPTES_PAR_FORMULE["mois"]
    assert o["comptes_actifs"] == 1 and o["active"]
    acces = client.get("/auth/moi", headers=h).json()["acces"]
    assert acces["organisation"] == o["nom"] and acces["role_org"] == "admin" and acces["gere_abonnement"]
    # Reçu de paiement professionnel
    recu = next(e for e in boite if "Paiement confirmé" in e["sujet"])
    assert recu["details"]["Comptes inclus"] == str(config.COMPTES_PAR_FORMULE["mois"])
    assert recu["details"]["Organisation"] == o["nom"]


def test_invitation_activation_et_abonnement_partage(client, boite):
    email, h = _abonne(client)
    r = client.post("/organisation/membres", headers=h, json={"email": "Analyste.A@Exemple.cm", "nom_complet": "Awa Bello",
                                                              "role_org": "analyste"})
    assert r.status_code == 200, r.text
    assert r.json()["invitation_envoyee"] and "mot_de_passe_provisoire" not in r.json()
    inv = next(e for e in boite if e["a"] == "analyste.a@exemple.cm")
    assert "Coopérative Test" in inv["sujet"] and inv["details"]["Rôle"] == "Analyste"
    jeton, compte = _lien(boite, "analyste.a@exemple.cm")
    assert compte == "analyste.a@exemple.cm"
    # Avant activation : impossible de se connecter
    statut = {m["nom"]: m["statut"] for m in client.get("/organisation", headers=h).json()["data"]["membres"]}
    assert statut[compte] == "invitation_en_attente"
    # Mauvais jeton, puis bon jeton : connexion directe
    assert client.post("/auth/invitation", json={"identifiant": compte, "jeton": "x" * 43, "nouveau": NOUVEAU}).status_code == 400
    a = client.post("/auth/invitation", json={"identifiant": compte, "jeton": jeton, "nouveau": NOUVEAU})
    assert a.status_code == 200, a.text
    ha = _h(a)
    assert client.post("/auth/invitation", json={"identifiant": compte, "jeton": jeton, "nouveau": NOUVEAU}).status_code == 400
    # L'analyste partage l'abonnement de son organisation, sans le gérer
    acces = client.get("/auth/moi", headers=ha).json()["acces"]
    assert acces["organisation"].startswith("Coopérative Test") and acces["role_org"] == "analyste"
    assert not acces["expire"] and not acces["gere_abonnement"]
    assert client.post("/vocal/question", headers=ha, json={"texte": "top 3 clients par solde"}).status_code == 200
    assert client.post("/abonnement/commander", headers=ha, json={"formule": "mois", "type_client": "organisation",
                                                                  "organisation": ORGA, "accepte_conditions": True}).status_code == 403
    assert client.post("/organisation/membres", headers=ha, json={"email": "x@exemple.cm", "nom_complet": "X Y"}).status_code == 403
    # Il ne voit pas l'administration de la plateforme
    for url in ("/admin/utilisateurs", "/admin/audit", "/signalements"):
        assert client.get(url, headers=ha).status_code == 403, url
    # L'abonnement échu bloque toute l'organisation
    _sql("UPDATE voicebank.organisations SET abonnement_fin = LOCALTIMESTAMP - INTERVAL '1 day' WHERE id_org = "
         "(SELECT id_org FROM voicebank.utilisateurs WHERE nom = %s)", (email,))
    assert client.post("/vocal/question", headers=ha, json={"texte": "top 3 clients par solde"}).status_code == 402
    assert client.post("/vocal/question", headers=h, json={"texte": "top 3 clients par solde"}).status_code == 402


def test_limite_de_comptes_selon_la_formule(client, boite):
    _, h = _abonne(client, formule="jour")
    limite = config.COMPTES_PAR_FORMULE["jour"]
    for i in range(limite - 1):
        assert client.post("/organisation/membres", headers=h, json={"email": f"lim{_n[0]}-{i}@exemple.cm",
                                                                     "nom_complet": f"Membre {i}"}).status_code == 200
    r = client.post("/organisation/membres", headers=h, json={"email": f"lim{_n[0]}-trop@exemple.cm", "nom_complet": "En trop"})
    assert r.status_code == 400 and "Limite atteinte" in r.json()["detail"]
    # Désactiver un compte libère une place ; on ne peut pas se désactiver soi-même
    m = f"lim{_n[0]}-0@exemple.cm"
    assert client.post(f"/organisation/membres/{m}/modifier", headers=h, json={"actif": False}).status_code == 200
    assert client.post("/organisation/membres", headers=h, json={"email": f"lim{_n[0]}-trop@exemple.cm",
                                                                 "nom_complet": "En trop"}).status_code == 200
    assert client.post(f"/organisation/membres/{m}/modifier", headers=h, json={"actif": True}).status_code == 400
    moi = next(x for x in client.get("/organisation", headers=h).json()["data"]["membres"] if x["moi"])["nom"]
    assert client.post(f"/organisation/membres/{moi}/modifier", headers=h, json={"actif": False}).status_code == 400
    # Doublon d'adresse
    r = client.post("/organisation/membres", headers=h, json={"email": m.upper(), "nom_complet": "Doublon"})
    assert r.status_code == 400


def test_promotion_administrateur_et_dernier_admin(client, boite):
    _, h = _abonne(client)
    client.post("/organisation/membres", headers=h, json={"email": f"promo{_n[0]}@exemple.cm", "nom_complet": "Promu"})
    m = f"promo{_n[0]}@exemple.cm"
    jeton, _ = _lien(boite, m)
    hm = _h(client.post("/auth/invitation", json={"identifiant": m, "jeton": jeton, "nouveau": NOUVEAU}))
    assert client.post(f"/organisation/membres/{m}/modifier", headers=h, json={"role_org": "admin"}).status_code == 200
    # Changement de rôle : sa session est révoquée, il se reconnecte en administrateur
    assert client.get("/organisation", headers=hm).status_code == 401
    hm = _h(client.post("/auth/login", json={"nom": m, "mot_de_passe": NOUVEAU}))
    assert client.get("/organisation", headers=hm).json()["data"]["peut_gerer"]


def test_particulier_compte_unique(client, boite):
    _, h = _abonne(client, type_client="particulier")
    o = client.get("/organisation", headers=h).json()["data"]
    assert o["type"] == "particulier" and o["limite_comptes"] == 1 and not o["peut_gerer"]
    r = client.post("/organisation/membres", headers=h, json={"email": f"coll{_n[0]}@exemple.cm", "nom_complet": "Collègue"})
    assert r.status_code == 400 and "un seul compte" in r.json()["detail"]


def test_cloisonnement_entre_organisations(client, boite):
    _, h1 = _abonne(client, raison="Banque A")
    _, h2 = _abonne(client, raison="Banque B")
    membres2 = client.get("/organisation", headers=h2).json()["data"]["membres"]
    autre = membres2[0]["nom"]
    assert client.post(f"/organisation/membres/{autre}/modifier", headers=h1, json={"actif": False}).status_code == 400
    assert client.post(f"/organisation/membres/{autre}/inviter", headers=h1).status_code == 400
    noms1 = {m["nom"] for m in client.get("/organisation", headers=h1).json()["data"]["membres"]}
    assert autre not in noms1


def test_sources_partagees_dans_l_organisation(client, boite):
    _, h = _abonne(client)
    m = f"src{_n[0]}@exemple.cm"
    client.post("/organisation/membres", headers=h, json={"email": m, "nom_complet": "Lectrice"})
    jeton, _ = _lien(boite, m)
    ha = _h(client.post("/auth/invitation", json={"identifiant": m, "jeton": jeton, "nouveau": NOUVEAU}))
    csv = ("Date;Ville;Montant\n" + "\n".join(f"0{1 + i % 9}/01/2025;Douala;{i * 100}" for i in range(1, 30))).encode()
    r = client.post("/sources/fichiers?synchrone=true", headers=h, data={"nom": "Ventes partagées"},
                    files=[("fichiers", ("ventes.csv", csv, "text/csv"))])
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    # L'analyste voit et interroge la source de son organisation, mais ne peut ni en ajouter ni la supprimer
    lst = client.get("/sources", headers=ha).json()
    assert sid in [s["id"] for s in lst["data"]] and not lst["peut_ajouter"]
    assert client.post(f"/sources/{sid}/question", headers=ha, json={"texte": "Montant total par ville"}).status_code == 200
    assert client.get(f"/sources/{sid}/tableau", headers=ha).status_code == 200
    assert client.post(f"/sources/{sid}/supprimer", headers=ha).status_code == 403
    # Une autre organisation ne la voit pas
    _, h_autre = _abonne(client, raison="Autre")
    assert client.get(f"/sources/{sid}", headers=h_autre).status_code == 404


def test_sans_service_d_email_mot_de_passe_provisoire(client, monkeypatch):
    monkeypatch.setattr(config, "PAIEMENT_SIMULATION", True)
    monkeypatch.setattr(config, "BREVO_API_KEY", "")
    monkeypatch.setattr(config, "SMTP_HOTE", "")
    _, h = _abonne(client)
    r = client.post("/organisation/membres", headers=h, json={"email": f"sans{_n[0]}@exemple.cm", "nom_complet": "Sans Mail"})
    assert r.status_code == 200 and not r.json()["invitation_envoyee"]
    mdp = r.json()["mot_de_passe_provisoire"]
    login = client.post("/auth/login", json={"nom": f"sans{_n[0]}@exemple.cm", "mot_de_passe": mdp})
    assert login.status_code == 200 and login.json()["doit_changer_mot_de_passe"]


def test_super_administrateur_et_email_de_test(client, admin, boite):
    _abonne(client, raison="Visible")
    orgs = client.get("/admin/organisations", headers=admin).json()["data"]
    assert any(o["nom"].startswith("Visible") and o["membres"] == 1 for o in orgs)
    r = client.post("/admin/email-test", headers=admin, json={"destinataire": "rayan@exemple.cm"})
    assert r.status_code == 200 and boite[-1]["a"] == "rayan@exemple.cm"


def test_email_de_test_affiche_la_raison_d_un_echec(client, admin, monkeypatch):
    from app import courriel
    monkeypatch.setattr(config, "BREVO_API_KEY", "cle")
    monkeypatch.setattr(config, "EMAIL_EXPEDITEUR", "no-reply@voicebank.test")

    def refus(dest, m):
        raise courriel.EnvoiImpossible("Brevo a refusé l'envoi (401) : Unrecognised IP address")
    monkeypatch.setattr(courriel, "envoyer_message", refus)
    r = client.post("/admin/email-test", headers=admin, json={"destinataire": "rayan@exemple.cm"})
    assert r.status_code == 502 and "Unrecognised IP" in r.json()["detail"]


def test_rendu_des_emails():
    from app import courriel, organisations
    m = organisations.message_invitation("Awa <b>", "Banque & Co", "Jean", "analyste", "awa@x.cm",
                                         "https://site/?invitation=abc&compte=awa%40x.cm")
    h = courriel.rendre_html(m)
    assert "Awa &lt;b&gt;" in h and "Banque &amp; Co" in h and "Activer mon compte" in h and "Cordialement" in h
    t = courriel.rendre_texte(m)
    assert "Activer mon compte : https://site/?invitation=abc" in t and config.EMAIL_SIGNATURE_NOM in t
    assert re.search(r"<table[^>]*max-width:580px", h)
