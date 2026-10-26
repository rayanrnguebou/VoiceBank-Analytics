"""Mot de passe oublié : code à 6 chiffres par e-mail (anti-énumération, expiration, essais, usage unique)."""
import re

import pytest

from app import config, recuperation
from tests.test_comptes import BON_MDP, _activer, _admin_sql, _h, _login

NOUVEAU = "Mangrove-Kribi-2027!"


@pytest.fixture
def boite(monkeypatch):
    """Active l'envoi d'e-mails et capture les messages au lieu de les envoyer."""
    envoyes = []
    monkeypatch.setattr(config, "BREVO_API_KEY", "cle-de-test")
    monkeypatch.setattr(config, "EMAIL_EXPEDITEUR", "no-reply@voicebank.test")
    return capturer(monkeypatch, envoyes)


def capturer(monkeypatch, envoyes):
    """Les e-mails (synchrones ou en arrière-plan) sont rendus puis gardés en mémoire."""
    from app import courriel

    def garder(dest, m):
        courriel.rendre_html(m), courriel.rendre_texte(m)          # le rendu ne doit jamais échouer
        envoyes.append({"a": dest, "sujet": m.sujet, "code": m.code, "texte": " ".join(m.paragraphes + m.apres),
                        "bouton": m.bouton, "details": dict(m.details), "message": m})
    monkeypatch.setattr(courriel, "envoyer_message", garder)
    monkeypatch.setattr(courriel, "envoyer_en_arriere_plan", garder)
    return envoyes


def _code(boite, email):
    m = [e for e in boite if e["a"] == email and e["code"]]
    assert m, boite
    return m[-1]["code"]


def test_indisponible_sans_service_d_email(client, monkeypatch):
    monkeypatch.setattr(config, "BREVO_API_KEY", "")
    monkeypatch.setattr(config, "SMTP_HOTE", "")
    assert client.get("/auth/options").json() == {"oubli_par_email": False}
    assert client.post("/auth/oubli", json={"identifiant": "rayan"}).status_code == 503


def test_parcours_complet_avec_un_compte_interne(client, admin, boite):
    h = _activer(client, admin, "awa.recup")
    assert client.get("/auth/options").json() == {"oubli_par_email": True}
    # Le titulaire ajoute son adresse (mot de passe actuel exigé)
    assert client.post("/auth/email", headers=h, json={"mot_de_passe": "faux", "email": "awa@exemple.cm"}).status_code == 400
    r = client.post("/auth/email", headers=h, json={"mot_de_passe": BON_MDP, "email": "Awa@Exemple.cm"})
    assert r.status_code == 200 and r.json()["email"] == "awa@exemple.cm"
    assert client.get("/auth/moi", headers=h).json()["email"] == "awa@exemple.cm"
    # Demande par l'identifiant ou par l'e-mail : même réponse
    r1 = client.post("/auth/oubli", json={"identifiant": "awa.recup"})
    assert r1.status_code == 200
    code1 = _code(boite, "awa@exemple.cm")
    assert re.fullmatch(r"\d{6}", code1) and code1 in boite[-1]["sujet"]
    client.post("/auth/oubli", json={"identifiant": "AWA@exemple.cm"})
    code2 = _code(boite, "awa@exemple.cm")
    # Une nouvelle demande annule l'ancien code
    if code1 != code2:
        r = client.post("/auth/oubli/confirmer", json={"identifiant": "awa.recup", "code": code1, "nouveau": NOUVEAU})
        assert r.status_code == 400
    # Mot de passe trop faible : refusé sans consommer le code
    r = client.post("/auth/oubli/confirmer", json={"identifiant": "awa.recup", "code": code2, "nouveau": "court"})
    assert r.status_code == 400 and "caractères" in r.json()["detail"]
    r = client.post("/auth/oubli/confirmer", json={"identifiant": "awa@exemple.cm", "code": code2, "nouveau": NOUVEAU})
    assert r.status_code == 200, r.text
    # Les sessions ouvertes sont révoquées, l'ancien mot de passe ne marche plus, le nouveau oui
    assert client.get("/auth/moi", headers=h).status_code == 401
    assert _login(client, "awa.recup", BON_MDP).status_code == 401
    assert _login(client, "awa.recup", NOUVEAU).status_code == 200
    # Code à usage unique, confirmation envoyée au titulaire
    r = client.post("/auth/oubli/confirmer", json={"identifiant": "awa.recup", "code": code2, "nouveau": "Autre-Mot-2027!x"})
    assert r.status_code == 400
    assert any("modifié" in e["sujet"] for e in boite)
    # E-mail professionnel : vouvoiement, signature, bouton
    avec_code = [e for e in boite if e["code"]][-1]
    html = __import__("app.courriel", fromlist=["x"]).rendre_html(avec_code["message"])
    assert "Cordialement" in html and config.EMAIL_SIGNATURE_NOM in html and avec_code["code"] in html
    assert "votre" in html and " ton " not in html


def test_aucune_information_sur_l_existence_d_un_compte(client, admin, boite):
    a = client.post("/auth/oubli", json={"identifiant": "personne@nulle-part.cm"})
    b = client.post("/auth/oubli", json={"identifiant": "rayan"})          # compte sans e-mail
    assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert not boite
    r = client.post("/auth/oubli/confirmer", json={"identifiant": "personne@nulle-part.cm", "code": "123456",
                                                   "nouveau": NOUVEAU})
    assert r.status_code == 400 and r.json()["detail"] == recuperation.REFUS


def test_essais_limites_expiration_et_demandes(client, admin, boite):
    h = _activer(client, admin, "paul.recup")
    client.post("/auth/email", headers=h, json={"mot_de_passe": BON_MDP, "email": "paul@exemple.cm"})
    client.post("/auth/oubli", json={"identifiant": "paul.recup"})
    bon = _code(boite, "paul@exemple.cm")
    faux = f"{(int(bon) + 1) % 1_000_000:06d}"
    for _ in range(recuperation.MAX_ESSAIS):
        assert client.post("/auth/oubli/confirmer", json={"identifiant": "paul.recup", "code": faux,
                                                          "nouveau": NOUVEAU}).status_code == 400
    # Après 5 essais faux, même le bon code est refusé
    assert client.post("/auth/oubli/confirmer", json={"identifiant": "paul.recup", "code": bon,
                                                      "nouveau": NOUVEAU}).status_code == 400
    # Code expiré
    client.post("/auth/oubli", json={"identifiant": "paul.recup"})
    code = _code(boite, "paul@exemple.cm")
    _admin_sql("UPDATE voicebank.codes_recuperation SET expire = LOCALTIMESTAMP - INTERVAL '1 minute' "
               "WHERE utilisateur = 'paul.recup'")
    assert client.post("/auth/oubli/confirmer", json={"identifiant": "paul.recup", "code": code,
                                                      "nouveau": NOUVEAU}).status_code == 400
    # 3 demandes par heure au plus : la 4e n'envoie rien (et répond pareil)
    assert client.post("/auth/oubli", json={"identifiant": "paul.recup"}).status_code == 200
    avant = len(boite)
    assert client.post("/auth/oubli", json={"identifiant": "paul.recup"}).status_code == 200
    assert len(boite) == avant == 3


def test_compte_verrouille_debloque_par_la_recuperation(client, admin, boite):
    h = _activer(client, admin, "lea.recup")
    client.post("/auth/email", headers=h, json={"mot_de_passe": BON_MDP, "email": "lea@exemple.cm"})
    for _ in range(5):
        _login(client, "lea.recup", "mauvais")
    assert _login(client, "lea.recup", BON_MDP).status_code == 401           # verrouillé
    client.post("/auth/oubli", json={"identifiant": "lea@exemple.cm"})
    r = client.post("/auth/oubli/confirmer", json={"identifiant": "lea.recup", "code": _code(boite, "lea@exemple.cm"),
                                                   "nouveau": NOUVEAU})
    assert r.status_code == 200
    assert _login(client, "lea.recup", NOUVEAU).status_code == 200


def test_email_a_la_creation_et_unicite(client, admin, boite):
    r = client.post("/admin/utilisateurs", headers=admin, json={"nom": "marc.recup", "email": "marc@exemple.cm"})
    assert r.status_code == 200
    r = client.post("/admin/utilisateurs", headers=admin, json={"nom": "marc.bis", "email": "MARC@exemple.cm"})
    assert r.status_code == 400 and "déjà" in r.json()["detail"]
    r = client.post("/admin/utilisateurs", headers=admin, json={"nom": "marc.ter", "email": "pas-un-email"})
    assert r.status_code == 400
    # Un visiteur ne change pas son e-mail (c'est son identifiant)
    e = client.post("/auth/essai", json={"nom_complet": "Test Visiteur", "email": "visiteur.recup@exemple.cm",
                                         "mot_de_passe": BON_MDP, "accepte_conditions": True})
    assert e.status_code == 200, e.text
    r = client.post("/auth/email", headers=_h(e), json={"mot_de_passe": BON_MDP, "email": "autre@exemple.cm"})
    assert r.status_code == 400
    # …mais peut récupérer son mot de passe avec
    client.post("/auth/oubli", json={"identifiant": "visiteur.recup@exemple.cm"})
    assert _code(boite, "visiteur.recup@exemple.cm")


def test_envoi_par_brevo(monkeypatch):
    from app import courriel
    appels = []

    class Rep:
        status_code = 201
        text = ""

        @staticmethod
        def json():
            return {"message": "Unrecognised IP address 1.2.3.4"}
    monkeypatch.setattr(config, "BREVO_API_KEY", "cle-de-test")
    monkeypatch.setattr(config, "EMAIL_EXPEDITEUR", "no-reply@voicebank.test")
    monkeypatch.setattr(courriel.httpx, "post", lambda url, **kw: appels.append((url, kw)) or Rep())
    courriel.envoyer("a@b.cm", "Sujet", "Titre <b>", ["Ligne & suite"], code="012345")
    url, kw = appels[0]
    assert url.endswith("/v3/smtp/email") and kw["headers"]["api-key"] == "cle-de-test"
    assert kw["json"]["to"] == [{"email": "a@b.cm"}] and "012345" in kw["json"]["htmlContent"]
    assert "Titre &lt;b&gt;" in kw["json"]["htmlContent"] and "Ligne &amp; suite" in kw["json"]["htmlContent"]
    Rep.status_code = 401
    with pytest.raises(courriel.EnvoiImpossible, match="401.*Unrecognised IP"):
        courriel.envoyer("a@b.cm", "Sujet", "Titre", ["x"])
