"""Lance les tests de bout en bout : vrai navigateur (Playwright) contre l'API et l'interface, sur une base de test.

Prépare tout seul :
  1. une base VoiceBank de test `vbe2e` (schéma, comptes à privilèges minimaux, données de démonstration fictives)
     et une base « externe » `banque_externe` (5 tables en anglais) pour le connecteur ;
  2. un faux serveur d'e-mails (les e-mails arrivent dans sortie/mails, rien ne sort de la machine) ;
  3. l'interface construite et servie sur http://localhost:3000 ;
  4. l'API sur http://localhost:8000, relancée avec d'autres réglages quand un test le demande.

Puis exécute les scénarios dans l'ordre (chacun prépare ses propres comptes) et affiche un bilan.

  python tests_e2e/lancer.py --pg postgresql://postgres:postgres@localhost:5432/postgres
  python tests_e2e/lancer.py --pg … --seulement test_ui,attaques     # quelques scénarios
Prérequis : psql, Node (npm ci déjà fait dans voicebank-ui), dépendances de l'API, `pip install playwright requests`
et `playwright install chromium` (ou E2E_CHROMIUM=/chemin/vers/chrome).
"""
import argparse
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent
SORTIE = ICI / "sortie"
PY = sys.executable

# Ordre : les premiers scénarios créent les comptes dont les suivants se servent (organisation, analyste…)
SCENARIOS = [
    ("test_ui", {}), ("test_v31", {}), ("test_v32", {}), ("test_finitions", {}), ("test_monnaie", {}),
    ("test_conversation", {}), ("test_dictee", {}), ("test_maintenance", {}),
    ("test_offre", {}), ("test_referentiel", {}), ("test_listes", {}),
    ("test_organisation", {}), ("test_connecteur", {}), ("test_risques_org", {}), ("test_surveillance", {}), ("test_recouvrement", {}),
    ("test_roles", {}), ("test_tableau_recuperation", {}), ("test_double_auth", {}),
    ("test_2fa_obligatoire", {"DOUBLE_AUTH_ADMINS": "obligatoire"}),
    ("test_sso", {}), ("test_anglais", {}), ("test_confort", {}), ("test_approbation", {}), ("test_cookies", {}), ("test_compatibilite", {}),
    ("attaques", {}),
    ("captures_magasin", {}),           # lancé seulement à la demande : --seulement captures_magasin
]


def url_base(admin: str, base: str, user: str | None = None, mdp: str | None = None) -> str:
    p = urlsplit(admin)
    hote = p.netloc.split("@")[-1]
    if user is None:
        auth = p.netloc.split("@")[0] + "@" if "@" in p.netloc else ""
    else:
        auth = f"{user}:{mdp}@" if mdp else f"{user}@"
    return urlunsplit((p.scheme, auth + hote, f"/{base}", p.query, ""))


def psql(url: str, *args: str):
    subprocess.run(["psql", url, "-X", "-q", "-v", "ON_ERROR_STOP=1", *args], check=True, stdout=subprocess.DEVNULL,
                   env={**os.environ, "PGOPTIONS": "-c client_min_messages=warning"})


def attendre(url: str, secondes: int = 120):
    fin = time.time() + secondes
    while time.time() < fin:
        try:
            if urllib.request.urlopen(url, timeout=5).status == 200:
                return
        except Exception:
            time.sleep(1)
    raise SystemExit(f"{url} ne répond pas après {secondes} s")


def port_libre(port: int):
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(f"Le port {port} est déjà utilisé (un ancien serveur de test ?) : arrête-le avant de relancer.")


def demarrer(cmd, **kw):
    """Processus de fond dans son propre groupe : arrêté avec tous ses enfants (npx lance node, etc.)."""
    return subprocess.Popen(cmd, start_new_session=True, **kw)


def arreter(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=20)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def preparer_bases(admin: str, mdp_app: str, mdp_lecteur: str):
    print("→ Bases de test (vbe2e, banque_externe)", flush=True)
    for base in ("vbe2e", "banque_externe"):
        psql(admin, "-c", f"DROP DATABASE IF EXISTS {base} WITH (FORCE)", "-c", f"CREATE DATABASE {base}")
    vb = url_base(admin, "vbe2e")
    init = RACINE / "voicebank_db" / "init"
    for f in ("01_init_voicebank.sql", "02_corrections_rag.sql"):
        psql(vb, "-f", str(init / f))
    psql(vb, "-v", f"app_pwd={mdp_app}", "-v", f"reader_pwd={mdp_lecteur}",
         "-f", str(RACINE / "voicebank_db" / "securite" / "roles.sql"))
    subprocess.run([PY, "-m", "app.outils.generer_demo"], cwd=RACINE / "voicebank_api", check=True,
                   env={**os.environ, "ADMIN_DATABASE_URL": vb}, stdout=subprocess.DEVNULL)
    ext = url_base(admin, "banque_externe")
    psql(admin, "-c", "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'lecteur_ext') THEN "
                      "CREATE ROLE lecteur_ext LOGIN PASSWORD 'Lecteur-2026!'; END IF; END $$")
    psql(ext, "-f", str(ICI / "donnees" / "banque_externe.sql"))
    psql(ext, "-c", "GRANT USAGE ON SCHEMA public TO lecteur_ext; GRANT SELECT ON ALL TABLES IN SCHEMA public TO lecteur_ext")


def _port_requete(requete: str) -> int:
    """Port donné dans la requête de l'URL (connexion par socket : ?host=/tmp&port=5433)."""
    from urllib.parse import parse_qs
    return int(parse_qs(requete).get("port", ["5432"])[0])


class API:
    def __init__(self, env: dict):
        self.env, self.proc, self.reglages = env, None, None

    def assurer(self, reglages: dict):
        if self.proc and self.reglages == reglages:
            return
        self.arreter()
        journal = open(SORTIE / "api.log", "a")
        self.proc = demarrer([PY, "-m", "uvicorn", "main:app", "--port", "8000"], cwd=RACINE / "voicebank_api",
                             env={**self.env, **reglages}, stdout=journal, stderr=subprocess.STDOUT)
        self.reglages = reglages
        attendre("http://localhost:8000/health")
        print(f"→ API démarrée {reglages or ''}", flush=True)

    def arreter(self):
        if self.proc:
            arreter(self.proc)
            self.proc = None


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--pg", default=os.environ.get("E2E_PG_ADMIN", "postgresql://postgres@localhost:5432/postgres"),
                   help="URL d'un superutilisateur PostgreSQL (bases de test créées puis recréées à chaque lancement)")
    a.add_argument("--seulement", help="scénarios à lancer, séparés par des virgules")
    a.add_argument("--sans-construire", action="store_true", help="réutiliser voicebank-ui/build")
    o = a.parse_args()
    SORTIE.mkdir(exist_ok=True)
    (SORTIE / "api.log").write_text("")
    mails = SORTIE / "mails"
    mails.mkdir(exist_ok=True)
    for f in mails.glob("*.eml"):
        f.unlink()

    mdp_app, mdp_lecteur = secrets.token_hex(12), secrets.token_hex(12)
    preparer_bases(o.pg, mdp_app, mdp_lecteur)
    import bcrypt
    h = lambda m: bcrypt.hashpw(m.encode(), bcrypt.gensalt(4)).decode()  # noqa: E731
    p = urlsplit(o.pg)
    env_api = {**os.environ,
               "ENV": "production", "JWT_SECRET": secrets.token_hex(32),
               "VOICEBANK_USERS": f"rayan:admin:{h('Test-Admin-2026!')},analyste1:analyste:{h('Test-Analyste-2026!')}",
               "DATABASE_URL": url_base(o.pg, "vbe2e", "voicebank_app", mdp_app),
               "READONLY_DATABASE_URL": url_base(o.pg, "vbe2e", "voicebank_reader", mdp_lecteur),
               "WHISPER_LOCAL": "false", "RATE_LIMIT_ACTIF": "false", "PAIEMENT_SIMULATION": "true",
               "CONNECTEUR_RESEAU_PRIVE": "true", "URL_INTERFACE": "http://localhost:3000", "TACHES_AUTO": "false",
               "SMTP_HOTE": "localhost", "SMTP_PORT": "1025", "EMAIL_EXPEDITEUR": "voicebank@exemple.cm",
               "DOUBLE_AUTH_ADMINS": "facultative", "GEMINI_API_KEY": "", "GROQ_API_KEY": "",
               "GOOGLE_CLIENT_ID": "e2e-google", "GOOGLE_CLIENT_SECRET": "e2e",
               "MICROSOFT_CLIENT_ID": "e2e-microsoft", "MICROSOFT_CLIENT_SECRET": "e2e",
               "TURNSTILE_SECRET": "", "SENTRY_DSN": ""}
    env_tests = {**os.environ, "E2E_BASE": url_base(o.pg, "vbe2e"), "E2E_MAILS": str(mails),
                 "E2E_SOURCE_HOTE": p.hostname or "127.0.0.1", "E2E_SOURCE_PORT": str(p.port or _port_requete(p.query)),
                 "PYTHONPATH": str(ICI), "PYTHONUNBUFFERED": "1"}

    for port in (3000, 8000, 1025):
        port_libre(port)
    fond = [demarrer([PY, str(ICI / "serveur_mails.py"), str(mails), "1025"], stdout=subprocess.DEVNULL)]
    ui = RACINE / "voicebank-ui"
    if not o.sans_construire:
        print("→ Construction de l'interface", flush=True)
        subprocess.run(["npm", "run", "build"], cwd=ui, check=True, stdout=subprocess.DEVNULL,
                       env={**os.environ, "REACT_APP_API_URL": "http://localhost:8000", "REACT_APP_TURNSTILE_SITE_KEY": "",
                            "REACT_APP_SENTRY_DSN": ""})
    fond.append(demarrer(["npx", "vite", "preview", "--port", "3000", "--strictPort"], cwd=ui,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    attendre("http://localhost:3000/")
    api = API(env_api)
    choix = set(o.seulement.split(",")) if o.seulement else None
    bilan = []
    captures = SORTIE / "captures"
    captures.mkdir(exist_ok=True)
    try:
        for nom, reglages in SCENARIOS:
            if (choix and nom not in choix) or (not choix and nom == "captures_magasin"):
                continue
            api.assurer(reglages)
            print(f"\n══ {nom}", flush=True)
            debut = time.time()
            try:
                r = subprocess.run([PY, str(ICI / f"{nom}.py")], cwd=captures, env=env_tests, timeout=900,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                sortie, ok = r.stdout, r.returncode == 0
            except subprocess.TimeoutExpired as e:
                sortie, ok = (e.stdout or b"").decode(errors="replace") + "\nDélai dépassé (15 min)", False
            print(sortie, flush=True)
            if not ok and os.environ.get("GITHUB_ACTIONS"):
                # Annotation lisible sur la page de l'exécution, sans télécharger les journaux
                fin = "\n".join(sortie.strip().splitlines()[-45:])
                print(f"::error title=Bout en bout : {nom}::" + fin.replace("%", "%25").replace("\r", "").replace("\n", "%0A"))
            bilan.append((nom, ok, time.time() - debut))
            if not ok:          # un scénario interrompu ne doit pas laisser la maintenance active pour les suivants
                psql(env_tests["E2E_BASE"], "-c", "DELETE FROM voicebank.parametres WHERE cle = 'maintenance'")
                time.sleep(16)  # l'API garde l'état de maintenance 15 s en mémoire
    finally:
        api.arreter()
        for f in fond:
            arreter(f)
    print("\n══ Bilan")
    for nom, ok, d in bilan:
        print(f"{'OK    ' if ok else 'ÉCHEC '} {nom} ({d:.0f} s)")
    echecs = [n for n, ok, _ in bilan if not ok]
    print(f"{len(bilan) - len(echecs)}/{len(bilan)} scénarios réussis")
    if echecs:
        print(f"Journal de l'API : {SORTIE / 'api.log'} ; captures : {captures}")
        sys.exit(1)


if __name__ == "__main__":
    main()
