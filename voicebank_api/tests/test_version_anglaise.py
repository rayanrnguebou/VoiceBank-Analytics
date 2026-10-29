"""Version anglaise : réponses, erreurs, e-mails et rapports PDF dans la langue de l'interface (Accept-Language)."""
import io
import json
import re
from pathlib import Path

from app import courriel, i18n

EN = {"Accept-Language": "en", "X-Forwarded-For": "192.0.2.201"}


def test_dictionnaire_coherent():
    """Chaque gabarit anglais n'utilise que des variables présentes dans le texte français."""
    brut = json.loads((Path(i18n.__file__).parent / "traductions" / "en.json").read_text(encoding="utf-8"))
    brut.pop("__mots__"); brut.pop("__titres__")
    for fr, en in brut.items():
        assert set(re.findall(r"\{(\w+)\}", en)) <= set(re.findall(r"\{(\w+)\}", fr)), fr
        assert en.strip(), fr


def test_traduction_exacte_et_gabarits():
    t = lambda s: i18n.traduire(s, "en")
    assert t("Identifiants incorrects.") == "Incorrect credentials."
    assert t("Serveur introuvable : db.banque.cm") == "Server not found: db.banque.cm"
    assert t("3 fois le montant habituel pour « virement »") == "3 times the usual amount for “virement”"
    assert t("Montant total des transactions par mois") == "Total amount of transactions per month"
    assert t("Douala") == "Douala"                                   # donnée : inchangée
    assert i18n.traduire("Identifiants incorrects.", "fr") == "Identifiants incorrects."
    # Valeurs codées jamais traduites dans les réponses (l'interface filtre dessus)
    assert i18n.traduire_objet({"niveau_risque": "Critique", "statut": "En cours", "texte": "Aucune action."}, "en") == \
        {"niveau_risque": "Critique", "statut": "En cours", "texte": "No action."}
    assert i18n.depuis_entete("en-GB,en;q=0.9,fr;q=0.8") == "en" and i18n.depuis_entete("fr-FR") == "fr"
    assert i18n.depuis_entete(None) == "fr"


def test_erreurs_et_reponses_en_anglais(client, admin):
    r = client.post("/auth/login", headers=EN, json={"nom": "inconnu.anglais", "mot_de_passe": "x"})
    assert r.status_code == 401 and r.json()["detail"] == "Incorrect credentials."
    r = client.post("/auth/login", headers={"X-Forwarded-For": "192.0.2.202"}, json={"nom": "inconnu.anglais", "mot_de_passe": "x"})
    assert r.json()["detail"] == "Identifiants incorrects."
    assert client.get("/admin/utilisateurs", headers=EN).json()["detail"] == "Authentication required"
    # Fiche des modèles (démonstration) : textes traduits
    f = client.get("/sources/0/modeles", headers={**admin, **EN}).json()["data"]
    texte = json.dumps(f, ensure_ascii=False)
    assert "Fraud detection (demo)" in texte and "Détection de fraude" not in texte


def test_langue_memorisee_pour_les_emails(client, admin, monkeypatch):
    from app import db
    client.get("/auth/moi", headers={**admin, **EN})
    assert db.ecrire("SELECT langue FROM voicebank.utilisateurs WHERE nom = 'rayan'").scalar() == "en"
    m = courriel.Message(sujet="Votre compte est protégé", titre="Votre compte est protégé", salutation="Bonjour,",
                         paragraphes=["Lien invalide ou expiré."], bouton=("Autoriser cet appareil", "https://x"),
                         details=[("Rôle", "Analyste")])
    en = courriel.traduire_message(m, "en")
    assert en.titre == "Your account is protected" and en.salutation == "Hello," and en.paragraphes == ["Invalid or expired link."]
    assert en.bouton == ("Authorise this device", "https://x") and en.details[0][0] == "Role"
    html = courriel.rendre_html(en)
    assert 'lang="en"' in html and "Kind regards," in html and "Cordialement" not in html
    assert "Cordialement," in courriel.rendre_html(m)
    client.get("/auth/moi", headers=admin)                     # retour au français
    assert db.ecrire("SELECT langue FROM voicebank.utilisateurs WHERE nom = 'rayan'").scalar() == "fr"


def test_rapport_pdf_en_anglais(client, admin):
    from tests.test_connecteur import base_pg  # noqa: F401  (la base de test des connecteurs)
    sources = client.get("/sources", headers=admin).json()["data"]
    ids = [s["id"] for s in sources if not s.get("demo") and s.get("statut") == "pret"]
    if not ids:
        import pytest
        pytest.skip("aucune base connectée dans cette session de tests")
    r = client.get(f"/sources/{ids[0]}/rapport?periode=semaine", headers={**admin, **EN})
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    from pypdf import PdfReader
    texte = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Period summary" in texte and "Synthèse de la période" not in texte
