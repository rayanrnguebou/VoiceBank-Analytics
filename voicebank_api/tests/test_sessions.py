"""Mes appareils : sessions ouvertes, déconnexion à distance, e-mail lors d'une connexion depuis un appareil inconnu."""
from app import securite
from tests.test_offre import MDP, _h, _inscrire
from tests.test_organisations import boite  # noqa: F401  (fixture)

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"


def _login(client, email, appareil, ua=CHROME):
    r = client.post("/auth/login", json={"nom": email, "mot_de_passe": MDP},
                    headers={"X-Appareil": appareil, "User-Agent": ua})
    assert r.status_code == 200, r.text
    return _h(r)


def _alertes(boite, email):  # noqa: F811
    return [e for e in boite if e["a"] == email and "Nouvelle connexion" in e["sujet"]]


def test_appareil_inconnu_prevenu_par_e_mail(client, boite):  # noqa: F811
    email = "appareils.mail@exemple.cm"
    assert _inscrire(client, email).status_code == 200            # 1re session : pas d'alerte
    _login(client, email, "portable-1")
    alertes = _alertes(boite, email)
    assert len(alertes) == 1
    assert alertes[0]["details"]["Appareil"] == "Chrome · Windows" and "Mot de passe" in alertes[0]["details"]["Méthode"]
    _login(client, email, "portable-1")                              # appareil déjà connu : pas de nouvel e-mail
    assert len(_alertes(boite, email)) == 1
    _login(client, email, "telephone-2", IPHONE)
    assert _alertes(boite, email)[-1]["details"]["Appareil"] == "Safari · iPhone"


def test_liste_et_deconnexion_a_distance(client):
    email = "appareils.liste@exemple.cm"
    _inscrire(client, email)
    pc = _login(client, email, "pc")
    tel = _login(client, email, "tel", IPHONE)
    liste = client.get("/moi/sessions", headers=pc).json()["data"]
    courante = [s for s in liste if s["courante"]]
    assert len(courante) == 1 and courante[0]["appareil"] == "Chrome · Windows"
    autre = next(s for s in liste if s["appareil"] == "Safari · iPhone")
    assert autre["active"]
    # La session en cours ne se ferme pas ici ; une autre session, si
    assert client.post(f"/moi/sessions/{courante[0]['id']}/deconnecter", headers=pc).status_code == 400
    assert client.post(f"/moi/sessions/{autre['id']}/deconnecter", headers=pc).status_code == 200
    assert client.get("/auth/moi", headers=tel).status_code == 401
    assert client.get("/auth/moi", headers=pc).status_code == 200
    assert not next(s for s in client.get("/moi/sessions", headers=pc).json()["data"] if s["id"] == autre["id"])["active"]
    # Impossible de fermer la session de quelqu'un d'autre
    autre_compte = _h(_inscrire(client, "appareils.autre@exemple.cm"))
    assert client.post(f"/moi/sessions/{courante[0]['id']}/deconnecter", headers=autre_compte).status_code == 404
    assert client.get("/auth/moi", headers=pc).status_code == 200


def test_deconnecter_tous_les_autres_appareils(client):
    email = "appareils.tous@exemple.cm"
    h_essai = _h(_inscrire(client, email))
    a, b = _login(client, email, "a"), _login(client, email, "b")
    # Jeton émis avant la mise à jour (sans session) : fermé lui aussi
    ancien = {"Authorization": "Bearer " + securite.creer_jeton(securite.Utilisateur(email, "visiteur"),
                                                                  securite.version_jeton(email))}
    assert client.get("/auth/moi", headers=ancien).status_code == 200
    r = client.post("/moi/sessions/deconnecter-autres", headers=a)
    assert r.status_code == 200 and r.json()["deconnectees"] >= 2
    nouveau = _h(r)
    for h in (h_essai, b, ancien, a):
        assert client.get("/auth/moi", headers=h).status_code == 401
    assert client.get("/auth/moi", headers=nouveau).status_code == 200
    # Le jeton renouvelé garde la même session
    renouvele = _h(client.post("/auth/renouveler", headers=nouveau))
    actives = [s for s in client.get("/moi/sessions", headers=renouvele).json()["data"] if s["active"]]
    assert len(actives) == 1 and actives[0]["courante"]


def test_resume_du_navigateur():
    from app.sessions import resume_navigateur
    assert resume_navigateur(CHROME) == "Chrome · Windows"
    assert resume_navigateur(IPHONE) == "Safari · iPhone"
    assert resume_navigateur("Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0") == "Firefox · Linux"
    assert resume_navigateur("Mozilla/5.0 (Linux; Android 15) Chrome/141.0 Mobile Safari/537.36 Edg/141.0") == "Edge · Android"
    assert resume_navigateur("") == "Navigateur inconnu"
