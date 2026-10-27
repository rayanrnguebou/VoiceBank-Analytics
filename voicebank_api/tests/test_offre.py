"""Offre publique : essai gratuit en lecture seule, quotas, abonnements et paiement sécurisé."""
import hashlib
import hmac
import json
import os
from urllib.parse import urlsplit, urlunsplit

import psycopg2
import pytest

from app import config, paiement

MDP = "Essai-Voicebank-2026"


def _sql(sql, params=None):
    a = urlsplit(os.environ.get("TEST_PG_ADMIN_URL", "postgresql://postgres@/postgres?host=/tmp&port=5433"))
    with psycopg2.connect(urlunsplit((a.scheme, a.netloc, "/voicebank_test", a.query, ""))) as c, c.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall() if cur.description else None


def _inscrire(client, email, mdp=MDP, **extra):
    corps = {"nom_complet": "Awa Bello", "email": email, "mot_de_passe": mdp, "profil": "professionnel",
             "accepte_conditions": True, **extra}
    return client.post("/auth/essai", json=corps)


def _h(rep):
    return {"Authorization": f"Bearer {rep.json()['access_token']}"}


@pytest.fixture
def visiteur(client):
    """Nouveau visiteur à chaque test (le nom varie pour éviter les doublons)."""
    _visiteur.n += 1
    email = f"visiteur{_visiteur.n}@exemple.cm"
    r = _inscrire(client, email)
    assert r.status_code == 200, r.text
    return email, _h(r)


def _visiteur():
    pass


_visiteur.n = 0

ORGA = {"raison_sociale": "Mutuelle du Littoral", "secteur": "microfinance", "taille": "11-50", "pays": "Cameroun",
        "ville": "Douala", "responsable": "Jean Mballa", "fonction": "Directeur des risques",
        "email": "risques@mutuelle.cm", "telephone": "+237 690 00 00 00", "niu": "M0123456789"}


def _commander(client, h, formule="semaine", **extra):
    return client.post("/abonnement/commander", headers=h, json={
        "formule": formule, "type_client": "organisation", "organisation": ORGA, "accepte_conditions": True, **extra})


# ── Essai gratuit ────────────────────────────────────────────────────

def test_formules_publiques(client):
    j = client.get("/abonnement/formules").json()
    prix = {f["code"]: f["prix"] for f in j["formules"]}
    assert prix == {"jour": 500, "semaine": 2000, "mois": 6000, "annee": 60000}
    assert {f["code"]: f["economie_pct"] for f in j["formules"]}["annee"] > 60
    assert j["paiement"] == "indisponible" and j["essai_jours"] == 3


def test_inscription_essai(client):
    r = _inscrire(client, "Kevin.Tagne@Exemple.CM")
    assert r.status_code == 200 and r.json()["role"] == "visiteur"
    assert r.json()["utilisateur"] == "kevin.tagne@exemple.cm"
    # Connexion avec l'e-mail, quelle que soit la casse
    assert client.post("/auth/login", json={"nom": "KEVIN.TAGNE@exemple.cm", "mot_de_passe": MDP}).status_code == 200
    acces = client.get("/auth/moi", headers=_h(r)).json()["acces"]
    assert acces["type"] == "essai" and acces["lecture_seule"] and not acces["expire"]
    assert 2.9 * 86400 < acces["secondes_restantes"] <= 3 * 86400 and acces["quota_questions"] == 30


@pytest.mark.parametrize("email,mdp,extra,message", [
    ("kevin.tagne@exemple.cm", MDP, {}, "existe déjà"),
    ("pas-un-email", MDP, {}, "e-mail invalide"),
    ("faible@exemple.cm", "court", {}, "12 caractères"),
    ("robot@exemple.cm", MDP, {"site_web": "http://spam"}, "impossible"),
    ("refus@exemple.cm", MDP, {"accepte_conditions": False}, "conditions"),
])
def test_inscription_refusee(client, email, mdp, extra, message):
    r = _inscrire(client, email, mdp, **extra)
    assert r.status_code == 400 and message in r.json()["detail"], r.text


def test_visiteur_en_lecture_seule(client, visiteur):
    email, h = visiteur
    assert client.get("/dashboard", headers=h).status_code == 200
    assert client.post("/ia/score-credit", headers=h, json={
        "montant_fcfa": 1e6, "mensualite_fcfa": 1e5, "revenu_annuel_fcfa": 5e6, "type_credit": "x",
        "garantie": "x", "banque": "x"}).status_code != 403          # calcul sans écriture : permis
    ecritures = [
        ("/alertes/1/traiter", {"decision": "Faux positif"}),
        ("/signalements", {"question": "q"}),
        ("/vocal/corriger", {"question": "qq", "sql_correct": "SELECT 1"}),
        ("/rag/corrections/1/supprimer", None),
        ("/admin/evaluation", None),
        ("/admin/utilisateurs", {"nom": "pirate"}),
        ("/admin/utilisateurs/rayan/modifier", {"actif": False}),
        ("/admin/utilisateurs/rayan/reinitialiser", None),
        ("/signalements/1/traiter", {"statut": "Rejeté"}),
    ]
    for route, corps in ecritures:
        r = client.post(route, headers=h, json=corps) if corps else client.post(route, headers=h)
        assert r.status_code == 403 and "lecture seule" in r.json()["detail"], (route, r.text)
    assert client.get("/admin/abonnements", headers=h).status_code == 403


def test_visiteur_voit_l_administration_anonymisee(client, visiteur, admin):
    email, h = visiteur
    comptes = client.get("/admin/utilisateurs", headers=h).json()
    noms = {c["nom"] for c in comptes["data"]}
    assert comptes["lecture_seule"] and email in noms and "r***" in noms and "rayan" not in noms
    assert not any("@" in n and n != email for n in noms)            # aucun autre visiteur listé
    audit = client.get("/admin/audit", headers=h).json()
    assert audit["evenements"] and all(e["utilisateur"] == email for e in audit["evenements"])
    assert all(q["utilisateur"] == email for q in audit["questions"])
    assert client.get("/admin/evaluation", headers=h).status_code == 200
    assert client.get("/rag/corrections", headers=h).status_code == 200
    # SQL en lecture : autorisé, noms masqués ; tables des comptes et paiements inaccessibles
    r = client.post("/sql/executer", headers=h, json={"sql": "SELECT nom, prenom FROM voicebank.clients LIMIT 3"})
    assert r.status_code == 200 and all(l["nom"].endswith("***") for l in r.json()["data"])
    for table in ("utilisateurs", "paiements", "profils_facturation"):
        assert client.post("/sql/executer", headers=h, json={"sql": f"SELECT * FROM voicebank.{table}"}).status_code == 400


def test_quota_de_questions(client, visiteur, monkeypatch):
    _, h = visiteur
    monkeypatch.setattr(config, "QUOTA_QUESTIONS_ESSAI", 2)
    for _ in range(2):
        assert client.post("/vocal/question", headers=h, json={"texte": "Crédits en défaut"}).status_code == 200
    r = client.post("/vocal/question", headers=h, json={"texte": "Crédits en défaut"})
    assert r.status_code == 429 and "Quota du jour" in r.json()["detail"]


def test_essai_expire(client, visiteur):
    email, h = visiteur
    _sql("UPDATE voicebank.utilisateurs SET essai_fin = LOCALTIMESTAMP - INTERVAL '1 minute' WHERE nom = %s", (email,))
    r = client.get("/dashboard", headers=h)
    assert r.status_code == 402 and "essai gratuit est terminé" in r.json()["detail"]
    assert client.get("/auth/moi", headers=h).json()["acces"]["expire"] is True
    assert client.post("/auth/login", json={"nom": email, "mot_de_passe": MDP}).status_code == 200   # pour payer
    assert client.get("/abonnement/moi", headers=h).status_code == 200


# ── Abonnements et paiement ──────────────────────────────────────────

def test_commande_sans_paiement_configure(client, visiteur):
    _, h = visiteur
    r = _commander(client, h)
    assert r.status_code == 400 and "pas encore activé" in r.json()["detail"]


def test_commande_infos_obligatoires(client, visiteur, monkeypatch):
    _, h = visiteur
    monkeypatch.setattr(config, "PAIEMENT_SIMULATION", True)
    r = client.post("/abonnement/commander", headers=h, json={
        "formule": "mois", "type_client": "particulier", "organisation": ORGA, "accepte_conditions": True})
    assert r.status_code == 400 and "Complète" in r.json()["detail"]
    mauvais = {**ORGA, "telephone": "abc"}
    r = client.post("/abonnement/commander", headers=h, json={
        "formule": "mois", "type_client": "organisation", "organisation": mauvais, "accepte_conditions": True})
    assert r.status_code == 422
    assert client.post("/abonnement/commander", headers=h, json={
        "formule": "gratuit", "type_client": "organisation", "organisation": ORGA, "accepte_conditions": True}
    ).status_code == 422


def test_comptes_internes_sans_abonnement(client, analyste):
    assert _commander(client, analyste).status_code == 400


def test_parcours_paiement_simule(client, visiteur, monkeypatch):
    email, h = visiteur
    monkeypatch.setattr(config, "PAIEMENT_SIMULATION", True)
    _sql("UPDATE voicebank.utilisateurs SET essai_fin = LOCALTIMESTAMP - INTERVAL '1 minute' WHERE nom = %s", (email,))
    # Le prix envoyé par le navigateur est ignoré : seul le serveur fixe le montant
    r = _commander(client, h, formule="semaine", montant=1, prix=1)
    assert r.status_code == 200, r.text
    cmd = r.json()
    assert cmd["montant"] == 2000 and cmd["mode"] == "simulation" and cmd["url_paiement"].endswith(cmd["reference"])
    assert _sql("SELECT montant, statut FROM voicebank.paiements WHERE reference = %s", (cmd["reference"],)) == [(2000, "en_attente")]
    infos = _sql("SELECT type_client, informations->>'raison_sociale' FROM voicebank.profils_facturation "
                 "WHERE utilisateur = %s", (email,))
    assert infos == [("organisation", "Mutuelle du Littoral")]

    v = client.get(f"/abonnement/verifier/{cmd['reference']}", headers=h).json()
    assert v["statut"] == "paye" and v["jeton"]["role"] == "client"
    fin1 = v["abonnement_fin"]
    # L'ancien jeton (visiteur) reste valable, et l'accès est rouvert
    assert client.get("/dashboard", headers=h).status_code == 200
    acces = client.get("/auth/moi", headers=h).json()["acces"]
    assert acces["type"] == "abonnement" and acces["formule"] == "semaine" and 6.9 * 86400 < acces["secondes_restantes"]
    # Toujours en lecture seule sur les données partagées
    assert client.post("/alertes/1/traiter", headers=h, json={"decision": "Faux positif"}).status_code == 403
    # Vérifier deux fois ne prolonge pas deux fois
    assert client.get(f"/abonnement/verifier/{cmd['reference']}", headers=h).json()["abonnement_fin"] == fin1
    # Un deuxième achat s'ajoute à la fin du premier
    cmd2 = _commander(client, h, formule="jour").json()
    v2 = client.get(f"/abonnement/verifier/{cmd2['reference']}", headers=h).json()
    assert v2["abonnement_fin"] > fin1
    assert [p["statut"] for p in client.get("/abonnement/moi", headers=h).json()["paiements"]] == ["paye", "paye"]


def test_paiement_d_un_autre_introuvable(client, visiteur, monkeypatch):
    _, h = visiteur
    monkeypatch.setattr(config, "PAIEMENT_SIMULATION", True)
    ref = _commander(client, h).json()["reference"]
    autre = _h(_inscrire(client, "curieux@exemple.cm"))
    assert client.get(f"/abonnement/verifier/{ref}", headers=autre).status_code == 404
    assert client.get("/abonnement/verifier/x' OR 1=1", headers=autre).status_code in (404, 422)


@pytest.fixture
def notchpay(monkeypatch):
    """NotchPay simulé : on contrôle la réponse de la vérification serveur à serveur."""
    monkeypatch.setattr(config, "NOTCHPAY_PUBLIC_KEY", "pk_test_cle")
    monkeypatch.setattr(config, "NOTCHPAY_HASH_KEY", "cle-de-hash-webhook")
    etat = {"transaction": None, "inits": []}

    def init(reference, montant, client, description):
        etat["inits"].append((reference, montant, client))
        return "https://pay.notchpay.co/pay_test", "trx.test_" + reference

    monkeypatch.setattr(paiement, "_initialiser_notchpay", init)
    monkeypatch.setattr(paiement, "_verifier_notchpay", lambda ref: etat["transaction"])
    return etat


def test_notchpay_verification_stricte(client, visiteur, notchpay):
    email, h = visiteur
    cmd = _commander(client, h, formule="mois").json()
    assert cmd["url_paiement"] == "https://pay.notchpay.co/pay_test" and cmd["mode"] == "test"
    assert notchpay["inits"][-1][1] == 6000 and notchpay["inits"][-1][2]["email"] == "risques@mutuelle.cm"
    url = f"/abonnement/verifier/{cmd['reference']}"
    base = {"trxref": cmd["reference"], "amount": 6000, "currency": "XAF"}
    for faux in ({**base, "status": "pending"}, {**base, "status": "complete", "amount": 60},
                 {**base, "status": "complete", "currency": "EUR"},
                 {**base, "status": "complete", "trxref": "vb-autre-reference"}):
        notchpay["transaction"] = faux
        assert client.get(url, headers=h).json()["statut"] == "en_attente", faux
    notchpay["transaction"] = {**base, "status": "complete"}
    assert client.get(url, headers=h).json()["statut"] == "paye"


def test_notchpay_echec(client, visiteur, notchpay):
    _, h = visiteur
    cmd = _commander(client, h).json()
    notchpay["transaction"] = {"trxref": cmd["reference"], "amount": 2000, "currency": "XAF", "status": "failed"}
    assert client.get(f"/abonnement/verifier/{cmd['reference']}", headers=h).json()["statut"] == "echoue"


def test_webhook_signe(client, visiteur, notchpay):
    email, h = visiteur
    cmd = _commander(client, h).json()
    corps = json.dumps({"event": "payment.complete", "data": {"trxref": cmd["reference"]}}).encode()
    signe = hmac.new(b"cle-de-hash-webhook", corps, hashlib.sha256).hexdigest()
    # Signature absente ou fausse : refusé, rien n'est activé
    for sig in (None, "0" * 64, hmac.new(b"autre-cle", corps, hashlib.sha256).hexdigest()):
        r = client.post("/paiements/notchpay/webhook", content=corps,
                        headers={"x-notch-signature": sig} if sig else {})
        assert r.status_code == 401
    # Signature valide mais NotchPay ne confirme pas : le contenu du webhook ne suffit pas
    notchpay["transaction"] = {"trxref": cmd["reference"], "amount": 2000, "currency": "XAF", "status": "pending"}
    r = client.post("/paiements/notchpay/webhook", content=corps, headers={"x-notch-signature": signe})
    assert r.json()["paiement"] == "en_attente"
    notchpay["transaction"]["status"] = "complete"
    r = client.post("/paiements/notchpay/webhook", content=corps, headers={"x-notch-signature": signe})
    assert r.status_code == 200 and r.json()["paiement"] == "paye"
    assert client.get("/auth/moi", headers=h).json()["role"] == "client"
    inconnu = json.dumps({"data": {"trxref": "vb-inexistant"}}).encode()
    r = client.post("/paiements/notchpay/webhook", content=inconnu,
                    headers={"x-notch-signature": hmac.new(b"cle-de-hash-webhook", inconnu, hashlib.sha256).hexdigest()})
    assert r.json()["paiement"] == "ignore"


def test_suivi_administrateur(client, admin):
    j = client.get("/admin/abonnements", headers=admin).json()
    assert j["paiements"] and j["synthese"]["revenus"] >= 2000
    p = next(p for p in j["paiements"] if p["informations"])
    assert p["type_client"] in ("organisation", "particulier")
    actions = {e["action"] for e in client.get("/admin/audit?limit=500", headers=admin).json()["evenements"]}
    assert {"essai_cree", "abonnement_commande", "abonnement_paye"} <= actions


def test_tables_d_abonnement_invisibles_pour_le_lecteur():
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        with psycopg2.connect(os.environ["READONLY_DATABASE_URL"]) as c:
            c.cursor().execute("SELECT * FROM voicebank.paiements")


def test_limite_inscriptions_non_contournable(client):
    from app.main import limiter
    limiter.enabled = True
    try:
        codes = []
        for i in range(5):
            # Le client invente une adresse différente à chaque fois : seule la dernière (proxy) compte
            r = client.post("/auth/essai", headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7"}, json={
                "nom_complet": "Robot", "email": f"robot{i}@exemple.cm", "mot_de_passe": MDP,
                "accepte_conditions": True})
            codes.append(r.status_code)
    finally:
        limiter.enabled = False
        limiter.reset()
    assert codes[:3] == [200] * 3 and codes[3:] == [429, 429], codes


# ── Initialisation NotchPay : numéro normalisé, nouvel essai sans numéro, raison affichée ──

@pytest.mark.parametrize("brut,attendu", [
    ("+237 690 00 00 00", "+237690000000"), ("690000000", "+237690000000"), ("00237 670000000", "+237670000000"),
    ("+33 6 12 34 56 78", "+33612345678"), ("abc", None), ("", None), (None, None)])
def test_telephone_international(brut, attendu):
    assert paiement.telephone_international(brut) == attendu


class _Rep:
    def __init__(self, code, corps):
        self.status_code, self._corps, self.text = code, corps, json.dumps(corps)

    def json(self):
        return self._corps


def _faux_client(monkeypatch, reponses, appels):
    class C:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json):
            appels.append(json)
            return reponses.pop(0)
    monkeypatch.setattr(paiement, "_client", lambda: C())


def test_numero_refuse_puis_paiement_sans_numero(monkeypatch):
    appels = []
    _faux_client(monkeypatch, [_Rep(422, {"message": "Invalid phone", "errors": {"customer.phone": ["invalid"]}}),
                               _Rep(201, {"authorization_url": "https://pay.notchpay.co/x", "transaction": {"reference": "trx.1"}})],
                 appels)
    url, ref = paiement._initialiser_notchpay("vb-1", 500, {"nom": "Paul", "email": "p@x.cm", "telephone": "+33 6 12 34 56 78"}, "d")
    assert url == "https://pay.notchpay.co/x" and ref == "trx.1"
    assert appels[0]["customer"]["phone"] == "+33612345678" and "phone" not in appels[1]["customer"]


def test_refus_affiche_la_raison_de_notchpay(monkeypatch):
    appels = []
    refus = _Rep(422, {"message": "The given data was invalid", "errors": {"customer.email": ["The email is invalid"]}})
    _faux_client(monkeypatch, [refus, refus], appels)
    with pytest.raises(paiement.PaiementRefuse, match="customer.email : The email is invalid"):
        paiement._initialiser_notchpay("vb-2", 500, {"nom": "Paul", "email": "p@x", "telephone": "690000000"}, "d")
    _faux_client(monkeypatch, [_Rep(401, {"message": "Unauthenticated"})], appels)
    with pytest.raises(paiement.PaiementRefuse, match="NOTCHPAY_PUBLIC_KEY"):
        paiement._initialiser_notchpay("vb-3", 500, {"nom": "Paul", "email": "p@x.cm"}, "d")
