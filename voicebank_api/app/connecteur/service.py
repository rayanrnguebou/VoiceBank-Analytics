"""Sources de données des organisations : enregistrement, analyse, questions. Isolation stricte :
une source n'est visible et interrogeable que par son propriétaire (la source de démonstration est
commune et en lecture seule)."""
import json
import logging
import threading
import time

from .. import catalogue, config, db, devises, resume
from ..garde_sql import message_refus
from ..masquage import est_colonne_personnelle, masquer_valeur
from . import analyse, fichiers, garde
from . import questions as Q
from .connexion import (TYPES, _lieu, chiffrer, connexion_lecture, dechiffrer, est_erreur_encodage, executer,
                        message_erreur, moteur)

log = logging.getLogger("voicebank")

DEMO_ID = 0
TABLES_DEMO = {"clients", "transactions", "credits", "alertes_fraude"}
_demo = {"profil": None, "date": 0.0}


class SourceRefusee(Exception):
    """Message affichable."""


# Une source est visible par son créateur et par tous les membres de son organisation cliente.
# Portée d'un compte : ses bases, et celles de son organisation — sauf si son accès est limité à certaines bases
# (table acces_sources : aucune ligne pour lui = toutes les bases de l'organisation).
_PORTEE = ("(proprietaire = :p OR (id_org IS NOT NULL AND "
           "id_org = (SELECT u.id_org FROM voicebank.utilisateurs u WHERE u.nom = :p) AND "
           "(NOT EXISTS (SELECT 1 FROM voicebank.acces_sources a WHERE a.utilisateur = :p) OR "
           " EXISTS (SELECT 1 FROM voicebank.acces_sources a WHERE a.utilisateur = :p "
           "         AND a.id_source = voicebank.sources_donnees.id_source))))")
_ORG = "(SELECT u.id_org FROM voicebank.utilisateurs u WHERE u.nom = :p)"


# ── Lecture / écriture des sources ─────────────────────────────────────

def _ligne(id_source: int, proprietaire: str):
    r = db.ecrire("SELECT id_source, proprietaire, nom, type_source, config_chiffree, resume_connexion, statut, "
                  "erreur, profil, masquer_pii, devise, date_creation, date_analyse FROM voicebank.sources_donnees "
                  f"WHERE id_source = :i AND {_PORTEE}", {"i": id_source, "p": proprietaire})
    if not r.lignes:
        raise SourceRefusee("Source introuvable")
    return r.lignes[0]


def _resume_public(l) -> dict:
    p = l.profil or {}
    return {"id": l.id_source, "nom": l.nom, "type": l.type_source, "libelle_type": TYPES[l.type_source]["libelle"],
            "connexion": l.resume_connexion, "statut": l.statut, "erreur": l.erreur, "masquer_pii": l.masquer_pii,
            "domaine": p.get("domaine"), "score_qualite": p.get("score_qualite"), "resume": p.get("resume"),
            "devise": devise_source(l), "devise_choisie": l.devise, "devise_detectee": p.get("devise_detectee"),
            "date_analyse": l.date_analyse.isoformat() if l.date_analyse else None, "demo": False}


def profil_demo() -> dict:
    if _demo["profil"] is None or time.time() - _demo["date"] > 3600:
        _demo["profil"] = analyse.analyser(db.moteur_lecture, "demo", "postgres", "voicebank", TABLES_DEMO)
        _demo["date"] = time.time()
    return _demo["profil"]


def source_demo_publique() -> dict:
    p = _demo["profil"] or {}
    return {"id": DEMO_ID, "nom": "Démonstration VoiceBank", "type": "demo", "libelle_type": TYPES["demo"]["libelle"],
            "connexion": "Données fictives de la banque de démonstration", "statut": "pret", "erreur": None,
            "masquer_pii": True, "devise": "XAF", "devise_choisie": None, "devise_detectee": "XAF",
            "domaine": p.get("domaine", "banque"), "score_qualite": p.get("score_qualite"),
            "resume": p.get("resume"), "date_analyse": p.get("date_analyse"), "demo": True}


def lister(proprietaire: str) -> list[dict]:
    r = db.ecrire("SELECT id_source, proprietaire, nom, type_source, config_chiffree, resume_connexion, statut, erreur, "
                  "profil, masquer_pii, devise, date_creation, date_analyse FROM voicebank.sources_donnees "
                  f"WHERE {_PORTEE} ORDER BY date_creation DESC", {"p": proprietaire})
    return [source_demo_publique()] + [_resume_public(l) for l in r.lignes]


def detail(id_source: int, proprietaire: str) -> dict:
    if id_source == DEMO_ID:
        return {**source_demo_publique(), "profil": profil_demo()}
    l = _ligne(id_source, proprietaire)
    return {**_resume_public(l), "profil": l.profil}


def _resume_connexion(type_source: str, cfg: dict) -> str:
    if type_source == "fichier":
        return ", ".join(cfg.get("fichiers", []))[:200]
    return f"{cfg.get('utilisateur')}@{cfg.get('hote')}:{cfg.get('port') or TYPES[type_source]['port']}/{cfg.get('base')}"[:200]


def _moteur_source(l):
    if l.type_source == "fichier":
        r = db.ecrire("SELECT nom_fichier, contenu FROM voicebank.sources_fichiers WHERE id_source = :i ORDER BY id_fichier",
                      {"i": l.id_source})
        chemin = fichiers.construire_sqlite(l.id_source, [(x.nom_fichier, bytes(x.contenu)) for x in r.lignes])
        return moteur("fichier", {}, chemin)
    return moteur(l.type_source, dechiffrer(l.config_chiffree))


def _schema(type_source: str, cfg: dict) -> str | None:
    if type_source in ("mysql", "fichier"):
        return None
    return (cfg.get("schema") or TYPES[type_source]["schema"])


# ── Test de connexion (sans rien enregistrer) ───────────────────────────

def _droits_ecriture(conn, type_source: str, schema: str | None) -> bool | None:
    try:
        if type_source == "postgresql":
            return bool(conn.exec_driver_sql(
                "SELECT COALESCE(bool_or(has_table_privilege(c.oid, 'INSERT') OR has_table_privilege(c.oid, 'UPDATE') "
                "OR has_table_privilege(c.oid, 'DELETE')), FALSE) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relkind = 'r' AND n.nspname = %(s)s", {"s": schema or "public"}).scalar())
        if type_source == "mysql":
            droits = " ".join(r[0] for r in conn.exec_driver_sql("SHOW GRANTS").fetchall()).upper()
            return any(m in droits for m in ("ALL PRIVILEGES", "INSERT", "UPDATE", "DELETE", "DROP"))
        if type_source == "oracle":
            return bool(conn.exec_driver_sql(
                "SELECT COUNT(*) FROM (SELECT privilege FROM session_privs WHERE privilege IN ('INSERT ANY TABLE', "
                "'UPDATE ANY TABLE', 'DELETE ANY TABLE', 'DROP ANY TABLE', 'ALTER ANY TABLE') "
                "UNION ALL SELECT privilege FROM user_tab_privs WHERE grantee = USER AND privilege IN ('INSERT', 'UPDATE', 'DELETE') "
                "UNION ALL SELECT privilege FROM role_tab_privs WHERE role IN (SELECT role FROM session_roles) "
                "AND privilege IN ('INSERT', 'UPDATE', 'DELETE') "
                "UNION ALL SELECT 'PROPRIETAIRE' FROM user_tables)").scalar())
        if type_source == "sqlserver":
            return bool(conn.exec_driver_sql(
                "SELECT CASE WHEN IS_ROLEMEMBER('db_datawriter') = 1 OR IS_ROLEMEMBER('db_owner') = 1 THEN 1 ELSE 0 END").scalar())
    except Exception:
        conn.rollback()
    return None


def tester(type_source: str, cfg: dict) -> dict:
    """Essaie la connexion ; un vieux serveur MySQL dont le texte n'est pas en UTF-8 est relu en Latin-1 (le réglage
    retenu est rangé dans `cfg`, puis gardé avec la source)."""
    try:
        return _tester(type_source, cfg)
    except SourceRefusee as e:
        if type_source != "mysql" or cfg.get("jeu_caracteres") or "encodage inattendu" not in str(e):
            raise
        cfg["jeu_caracteres"] = "latin1"
        try:
            return _tester(type_source, cfg)
        except SourceRefusee:
            cfg.pop("jeu_caracteres", None)
            raise e


def _tester(type_source: str, cfg: dict) -> dict:
    if type_source not in ("postgresql", "mysql", "sqlserver", "oracle"):
        raise SourceRefusee("Type de base inconnu")
    try:
        eng = moteur(type_source, cfg)
        from sqlalchemy import inspect
        with connexion_lecture(eng, type_source) as conn:
            version = ".".join(str(x) for x in (eng.dialect.server_version_info or ())[:3]) or "?"
            ecriture = _droits_ecriture(conn, type_source, _schema(type_source, cfg))
        tables = inspect(eng).get_table_names(schema=_schema(type_source, cfg))
    except SourceRefusee:
        raise
    except Exception as e:
        log.info("Test de connexion échoué (%s) : %s", type_source, e)
        raise SourceRefusee(message_erreur(e))
    return {"ok": True, "version": version, "tables": len(tables), "apercu_tables": sorted(tables)[:12],
            "droits_ecriture": ecriture,
            "avertissement": ("Ce compte peut MODIFIER les données. VoiceBank ne l'utilise qu'en lecture, mais crée "
                              "plutôt un compte en lecture seule (voir l'aide).") if ecriture else None}


# ── Création, analyse, suppression ─────────────────────────────────────

def _verifier_quota(proprietaire: str, role: str):
    n = db.ecrire(f"SELECT COUNT(*) FROM voicebank.sources_donnees WHERE {_PORTEE}", {"p": proprietaire}).scalar()
    maximum = config.CONNECTEUR_MAX_SOURCES * (4 if role == "admin" else 1)
    if n >= maximum:
        raise SourceRefusee(f"Nombre maximal de sources atteint ({maximum}). Supprime une source pour en ajouter une.")


def creer(proprietaire: str, role: str, nom: str, type_source: str, cfg: dict) -> int:
    _verifier_quota(proprietaire, role)
    tester(type_source, cfg)                       # on n'enregistre que ce qui fonctionne
    garde_cfg = {k: cfg.get(k) for k in ("hote", "port", "base", "utilisateur", "mot_de_passe", "ssl", "schema",
                                         "jeu_caracteres") if k != "jeu_caracteres" or cfg.get(k)}
    r = db.ecrire("INSERT INTO voicebank.sources_donnees (proprietaire, nom, type_source, config_chiffree, resume_connexion, "
                  f"id_org) VALUES (:p, :n, :t, :c, :r, {_ORG}) RETURNING id_source",
                  {"p": proprietaire, "n": nom, "t": type_source, "c": chiffrer(garde_cfg),
                   "r": _resume_connexion(type_source, cfg)})
    return r.scalar()


def creer_depuis_fichiers(proprietaire: str, role: str, nom: str, contenus: list[tuple[str, bytes]]) -> int:
    _verifier_quota(proprietaire, role)
    if not contenus or len(contenus) > fichiers.MAX_FICHIERS:
        raise SourceRefusee(f"Envoie entre 1 et {fichiers.MAX_FICHIERS} fichiers")
    try:
        tables = fichiers.tables_depuis(contenus)             # lecture complète : refuse tôt un fichier invalide
    except fichiers.FichierRefuse as e:
        raise SourceRefusee(str(e))
    except Exception as e:
        log.info("Fichier illisible : %s", e)
        raise SourceRefusee("Fichier illisible : vérifie qu'il s'agit bien d'un CSV ou d'un Excel .xlsx")
    r = db.ecrire("INSERT INTO voicebank.sources_donnees (proprietaire, nom, type_source, resume_connexion, id_org) "
                  f"VALUES (:p, :n, 'fichier', :r, {_ORG}) RETURNING id_source",
                  {"p": proprietaire, "n": nom, "r": _resume_connexion("fichier", {"fichiers": [n for n, _ in contenus]})})
    id_source = r.scalar()
    for n, c in contenus:
        db.ecrire("INSERT INTO voicebank.sources_fichiers (id_source, nom_fichier, contenu, taille) VALUES (:i, :n, :c, :t)",
                  {"i": id_source, "n": n[:200], "c": c, "t": len(c)})
    log.info("Source fichiers %s : %d table(s)", id_source, len(tables))
    return id_source


def analyser(id_source: int, proprietaire: str):
    db.ecrire("UPDATE voicebank.sources_donnees SET statut = 'analyse', erreur = NULL WHERE id_source = :i AND " + _PORTEE,
              {"i": id_source, "p": proprietaire})
    try:
        l = _ligne(id_source, proprietaire)
        cfg = dechiffrer(l.config_chiffree) if l.config_chiffree else {}
        eng = _moteur_source(l)
        try:
            profil = analyse.analyser(eng, l.type_source, TYPES[l.type_source]["dialecte"], _schema(l.type_source, cfg))
        except Exception as e:
            # Vieux serveur MySQL au texte hors UTF-8 : nouvel essai en Latin-1, gardé pour la suite si ça marche
            if l.type_source != "mysql" or cfg.get("jeu_caracteres") or not est_erreur_encodage(e):
                raise
            log.warning("Source %s : texte hors UTF-8%s ; nouvel essai en Latin-1", id_source, _lieu(e))
            cfg["jeu_caracteres"] = "latin1"
            eng = moteur("mysql", cfg)
            profil = analyse.analyser(eng, l.type_source, TYPES[l.type_source]["dialecte"], _schema(l.type_source, cfg))
            db.ecrire("UPDATE voicebank.sources_donnees SET config_chiffree = :c WHERE id_source = :i",
                      {"c": chiffrer(cfg), "i": id_source})
        profil["devise_detectee"] = devises.detecter_devise(profil)
        db.ecrire("UPDATE voicebank.sources_donnees SET statut = 'pret', profil = CAST(:p AS JSONB), date_analyse = NOW() "
                  "WHERE id_source = :i", {"i": id_source, "p": json.dumps(profil, ensure_ascii=False, default=str)})
    except Exception as e:
        log.warning("Analyse de la source %s impossible : %s", id_source, e, exc_info=True)
        db.ecrire("UPDATE voicebank.sources_donnees SET statut = 'erreur', erreur = :e WHERE id_source = :i",
                  {"i": id_source, "e": message_erreur(e)[:500]})


def _structure(profil: dict | None) -> dict[str, set[str]]:
    return {t["nom"]: {c["nom"] for c in t.get("colonnes", [])} for t in (profil or {}).get("tables", []) if not t.get("erreur")}


def reanalyser(id_source: int, proprietaire: str) -> dict:
    """Ré-analyse planifiée : met le profil à jour sans jamais retirer la base de la surveillance. Si la base est
    injoignable, l'ancien profil est gardé. Retourne les changements de structure (tables, colonnes)."""
    l = _ligne(id_source, proprietaire)
    if l.type_source == "fichier":
        return {"ignoree": "fichiers : structure fixe"}
    cfg = dechiffrer(l.config_chiffree)
    try:
        profil = analyse.analyser(_moteur_source(l), l.type_source, TYPES[l.type_source]["dialecte"], _schema(l.type_source, cfg))
    except Exception as e:
        log.warning("Ré-analyse de la source %s impossible : %s", id_source, e)
        return {"erreur": message_erreur(e)}
    profil["devise_detectee"] = devises.detecter_devise(profil)
    avant, apres = _structure(l.profil), _structure(profil)
    communes = avant.keys() & apres.keys()
    changements = {
        "tables_ajoutees": sorted(apres.keys() - avant.keys()), "tables_supprimees": sorted(avant.keys() - apres.keys()),
        "colonnes_ajoutees": sorted(f"{t}.{c}" for t in communes for c in apres[t] - avant[t]),
        "colonnes_supprimees": sorted(f"{t}.{c}" for t in communes for c in avant[t] - apres[t]),
    }
    db.ecrire("UPDATE voicebank.sources_donnees SET profil = CAST(:p AS JSONB), date_analyse = NOW(), erreur = NULL "
              "WHERE id_source = :i", {"i": id_source, "p": json.dumps(profil, ensure_ascii=False, default=str)})
    return {k: v for k, v in changements.items() if v}


def analyser_en_arriere_plan(id_source: int, proprietaire: str, synchrone: bool = False):
    if synchrone:
        analyser(id_source, proprietaire)
    else:
        threading.Thread(target=analyser, args=(id_source, proprietaire), daemon=True).start()


def supprimer(id_source: int, proprietaire: str):
    r = db.ecrire("DELETE FROM voicebank.sources_donnees WHERE id_source = :i AND " + _PORTEE,
                  {"i": id_source, "p": proprietaire})
    if not r.rowcount:
        raise SourceRefusee("Source introuvable")
    db.ecrire("DELETE FROM voicebank.dossiers_recouvrement WHERE id_source = :i", {"i": id_source})
    db.ecrire("DELETE FROM voicebank.cles_api WHERE id_source = :i", {"i": id_source})
    for f in fichiers.CACHE.glob(f"source_{int(id_source)}_*.sqlite"):
        f.unlink(missing_ok=True)


def monnaie(id_source: int, proprietaire: str) -> str:
    """Monnaie dans laquelle la base enregistre ses montants."""
    return "XAF" if id_source == DEMO_ID else devise_source(_ligne(id_source, proprietaire))


def devise_source(l) -> str:
    return (l.devise or (l.profil or {}).get("devise_detectee") or "XAF").strip().upper()


def modifier_devise(id_source: int, proprietaire: str, devise: str | None):
    r = db.ecrire("UPDATE voicebank.sources_donnees SET devise = :d WHERE id_source = :i AND " + _PORTEE,
                  {"i": id_source, "p": proprietaire, "d": devise})
    if not r.rowcount:
        raise SourceRefusee("Source introuvable")


def modifier_masquage(id_source: int, proprietaire: str, masquer: bool):
    r = db.ecrire("UPDATE voicebank.sources_donnees SET masquer_pii = :m WHERE id_source = :i AND " + _PORTEE,
                  {"i": id_source, "p": proprietaire, "m": masquer})
    if not r.rowcount:
        raise SourceRefusee("Source introuvable")


# ── Questions ─────────────────────────────────────────────────────────

FORMAT_MASQUE = {"email": "email", "telephone": "telephone", "compte_bancaire": "numero_compte",
                 "naissance": "date_naissance"}


def _colonnes_sensibles(profil: dict) -> tuple[set[str], dict[str, str]]:
    """(colonnes secrètes, {colonne personnelle: type de donnée})."""
    secrets, perso = set(), {}
    for t in profil.get("tables", []):
        for c in t["colonnes"]:
            if c["role"] == "secret":
                secrets.add(c["nom"].lower())
            elif c["pii"]:
                perso[c["nom"].lower()] = c["pii"]
    return secrets, perso


def _masquer(colonnes, lignes, perso: dict[str, str]):
    a_masquer = {c: FORMAT_MASQUE.get(perso.get(c.lower()), "nom" if c.lower() in perso else c)
                 for c in colonnes if c.lower() in perso or est_colonne_personnelle(c)}
    if not a_masquer:
        return lignes
    return [{**l, **{c: masquer_valeur(fmt, l.get(c)) for c, fmt in a_masquer.items()}} for l in lignes]


def repondre(id_source: int, proprietaire: str, role: str, question: str, devise: str = "XAF") -> dict:
    debut = time.time()
    if id_source == DEMO_ID:
        profil, type_source, eng, masquer = profil_demo(), "demo", db.moteur_lecture, role != "admin"
        devise_base = "XAF"
    else:
        l = _ligne(id_source, proprietaire)
        if l.statut != "pret" or not l.profil:
            raise SourceRefusee("Analyse de la source en cours : réessaie dans un instant." if l.statut == "analyse"
                                else "La source n'a pas pu être analysée : relance l'analyse.")
        profil, type_source, masquer = l.profil, l.type_source, l.masquer_pii
        devise_base = devise_source(l)
        try:
            eng = _moteur_source(l)
        except Exception as e:
            raise SourceRefusee(message_erreur(e))
    if catalogue.est_question_structure(question):
        nom = "Démonstration VoiceBank" if id_source == DEMO_ID else l.nom
        return {**catalogue.reponse(profil, question, nom), "source_donnees": id_source,
                "duree_ms": int((time.time() - debut) * 1000), "devise": devise, "devise_base": devise_base}
    dialecte = profil["dialecte"]
    autorisees = {t["nom"].lower() for t in profil["tables"] if not t.get("erreur")}
    schemas = {(profil.get("schema") or "").lower()} - {""}
    secrets, perso = _colonnes_sensibles(profil)

    tentatives, avertissement = [], None
    sql_ia = Q.sql_gemini(question, profil, dialecte)
    if sql_ia:
        tentatives.append(("gemini", sql_ia))
    local = Q.sql_local(question, profil, dialecte)
    if local:
        tentatives.append(("local", local[0]))
    if not tentatives:
        raise SourceRefusee("Je n'ai pas compris la question pour cette base. Essaie par exemple : "
                            + " ; ".join(f"« {s} »" for s in profil.get("suggestions", [])[:3]))
    derniere_erreur = None
    for source, sql in tentatives:
        try:
            sur = garde.valider(sql, dialecte, autorisees, 1000, schemas)
            colonnes_req = {c.lower() for c in _colonnes_citees(sur, dialecte)}
            if colonnes_req & secrets:
                raise garde.SQLRefuse("Colonne secrète demandée")
            colonnes, lignes = executer(eng, type_source, sur, 1000)
            break
        except garde.SQLRefuse as e:
            derniere_erreur = message_refus(e)
            log.info("Requête %s refusée sur la source %s : %s", source, id_source, e)
        except Exception as e:
            derniere_erreur = "La requête n'a pas pu être exécutée sur la base."
            log.info("Requête %s en échec sur la source %s : %s", source, id_source, e)
    else:
        raise SourceRefusee(derniere_erreur or "Requête impossible")
    if source == "local" and sql_ia:
        avertissement = "Réponse calculée par le moteur local (la requête de l'IA n'a pas abouti)."
    # Jamais de secret affiché ; données personnelles masquées si demandé
    colonnes = [c for c in colonnes if c.lower() not in secrets]
    lignes = [{c: l[c] for c in colonnes} for l in lignes]
    if masquer:
        lignes = _masquer(colonnes, lignes, perso)
    # Montants : de la monnaie de la base vers la monnaie choisie par l'utilisateur
    montants = {c["nom"].lower() for t in profil["tables"] for c in t["colonnes"] if c["role"] == "montant"}
    monetaires = {c.lower() for c in colonnes
                  if c.lower() in montants or any(m in c.lower() for m in montants if len(m) >= 4)}
    lignes, converties = devises.convertir_lignes(colonnes, lignes, devise, devise_base, monetaires)
    sans_perso = [c for c in colonnes if c.lower() not in perso and not est_colonne_personnelle(c)]
    r = resume.resumer(question, sans_perso, [{c: l[c] for c in sans_perso} for l in lignes], devise)
    suggestion = next((s for s in profil.get("suggestions", []) if s.lower() != question.strip().lower()), None)
    relance = ({"texte": f"Veux-tu voir aussi : {suggestion[0].lower() + suggestion[1:]} ?", "question": suggestion}
               if suggestion else None)
    return {"status": "ok", "question": question, "sql": sur, "source": "gemini" if source == "gemini" else "rule",
            "source_donnees": id_source, "avertissement": avertissement, "colonnes": colonnes, "total": len(lignes),
            "data": lignes, "duree_ms": int((time.time() - debut) * 1000), "resume": r["resume"],
            "commentaire": r["commentaire"], "relance": relance, "suite": False,
            "devise": devise, "devise_base": devise_base, "colonnes_monetaires": [c for c in colonnes if c.lower() in monetaires]}


def tableau_de_bord(id_source: int, proprietaire: str, devise: str = "XAF") -> dict:
    """Indicateurs et graphiques adaptés à la base, montants dans la monnaie choisie."""
    from . import tableau
    if id_source == DEMO_ID:
        profil, type_source, eng, devise_base, nom = profil_demo(), "demo", db.moteur_lecture, "XAF", "Démonstration VoiceBank"
        date_analyse = profil.get("date_analyse")
    else:
        l = _ligne(id_source, proprietaire)
        if l.statut != "pret" or not l.profil:
            raise SourceRefusee("Analyse de la source en cours : réessaie dans un instant." if l.statut == "analyse"
                                else "La source n'a pas pu être analysée : relance l'analyse.")
        profil, type_source, devise_base, nom = l.profil, l.type_source, devise_source(l), l.nom
        date_analyse = l.date_analyse.isoformat() if l.date_analyse else None
        eng = None
    calcul = lambda: tableau.calculer(eng if eng is not None else _moteur_source(l), type_source, profil)  # noqa: E731
    try:
        brut = tableau.tableau((id_source, proprietaire, date_analyse, devise_base), calcul)
    except Exception as e:
        log.info("Tableau de bord de la source %s impossible : %s", id_source, e)
        raise SourceRefusee(message_erreur(e))
    conv = lambda v: devises.convertir(v, devise_base, devise)  # noqa: E731
    indicateurs = [{**i, "valeur": conv(i["valeur"])} if i["type"] == "montant" else dict(i) for i in brut["indicateurs"]]
    graphiques = []
    for g in brut["graphiques"]:
        cles = {s["cle"] for s in g["series"] if s.get("montant")}
        graphiques.append({**g, "donnees": [{k: conv(v) if k in cles else v for k, v in p.items()} for p in g["donnees"]]})
    return {"source": {"id": id_source, "nom": nom}, "devise": devise, "devise_base": devise_base,
            "domaine": profil.get("domaine"), "indicateurs": indicateurs, "graphiques": graphiques}


# ── Risques adaptés à la base (fraude, crédit) ───────────────────────

def _contexte(id_source: int, proprietaire: str):
    """(profil, type_source, moteur, monnaie de la base, clé de cache)."""
    if id_source == DEMO_ID:
        p = profil_demo()
        return p, "demo", db.moteur_lecture, "XAF", (0, p.get("date_analyse"))
    l = _ligne(id_source, proprietaire)
    if l.statut != "pret" or not l.profil:
        raise SourceRefusee("Analyse de la source en cours : réessaie dans un instant." if l.statut == "analyse"
                            else "La source n'a pas pu être analysée : relance l'analyse.")
    try:
        eng = _moteur_source(l)
    except Exception as e:
        raise SourceRefusee(message_erreur(e))
    return l.profil, l.type_source, eng, devise_source(l), (id_source, l.date_analyse.isoformat() if l.date_analyse else None)


def _risque(action):
    from . import risques
    try:
        return action(risques)
    except risques.RisqueIndisponible as e:
        raise SourceRefusee(str(e))
    except SourceRefusee:
        raise
    except Exception as e:
        log.warning("Analyse de risque impossible : %s", e)
        raise SourceRefusee("Analyse impossible sur cette base pour le moment.")


def operations_atypiques(id_source: int, proprietaire: str, devise: str = "XAF") -> dict:
    """Opérations atypiques de la base ; sur une base d'organisation, chacune devient une alerte suivie
    (statut, personne assignée) — les montants sont enregistrés dans la monnaie de la base."""
    from .. import suivi
    profil, ts, eng, base, cle = _contexte(id_source, proprietaire)
    res = _risque(lambda r: r.operations_atypiques(eng, ts, profil, base, cle, limite=200))
    ops = res["operations"]
    if id_source != DEMO_ID:
        suivi.enregistrer(id_source, ops)
        ops = suivi.annoter(id_source, ops)
    conv = lambda v: devises.convertir(v, base, devise)  # noqa: E731
    ops = [{**o, "montant": conv(o["montant"]), "raisons": [
        {**f, "valeur": f["valeur"] if f["variable"] != "Montant" else None} for f in o["raisons"]]} for o in ops]
    return {**res, "operations": ops, "devise": devise, "suivi_actif": id_source != DEMO_ID}


def formulaire_operation(id_source: int, proprietaire: str, devise: str = "XAF") -> dict:
    profil, ts, eng, base, cle = _contexte(id_source, proprietaire)
    f = _risque(lambda r: r.formulaire_operation(eng, ts, profil, base, cle))
    return {**f, "devise": devise, "montant_habituel": devises.convertir(f["montant_habituel"], base, devise)}


def analyser_operation(id_source: int, proprietaire: str, montant: float, heure: int | None, categories: dict,
                       devise: str = "XAF") -> dict:
    profil, ts, eng, base, cle = _contexte(id_source, proprietaire)
    montant_base = devises.convertir(montant, devise, base)
    res = _risque(lambda r: r.analyser_operation(eng, ts, profil, base, cle, montant_base, heure, categories))
    for f in res["facteurs"]:
        if f["variable"] == "Montant":
            f["valeur"] = None
    return res


def portefeuille_credits(id_source: int, proprietaire: str, devise: str = "XAF") -> dict:
    profil, ts, eng, base, cle = _contexte(id_source, proprietaire)
    res = _risque(lambda r: r.portefeuille(eng, ts, profil, base, cle))
    a_risque = [{**c, "montant": None if c.get("montant") is None else devises.convertir(c["montant"], base, devise)}
                for c in res.get("a_risque", [])]
    return {**res, "a_risque": a_risque, "devise": devise, "devise_base": base}


def fiches_modeles(id_source: int, proprietaire: str) -> dict:
    """Fiches des modèles appris sur la base (fraude et crédit), chacune indépendante de l'autre."""
    profil, ts, eng, base, cle = _contexte(id_source, proprietaire)
    res = {}
    for nom, f in (("operations", "fiche_operations"), ("credits", "fiche_credits")):
        try:
            res[nom] = _risque(lambda r: getattr(r, f)(eng, ts, profil, base, cle))
        except SourceRefusee as e:
            res[nom] = {"indisponible": str(e)}
    return res


def credits_a_recouvrer(id_source: int, proprietaire: str, role: str) -> tuple[dict, str, bool]:
    """(crédits en retard ou en défaut, monnaie de la base, données personnelles masquées pour cet utilisateur)."""
    from . import recouvrement
    profil, ts, eng, base, cle = _contexte(id_source, proprietaire)
    masquer = role != "admin" if id_source == DEMO_ID else bool(_ligne(id_source, proprietaire).masquer_pii)
    return _risque(lambda r: recouvrement.credits_a_recouvrer(eng, ts, profil, cle)), base, masquer


def test_historique(id_source: int, proprietaire: str) -> tuple[dict, str]:
    """Ce que les modèles auraient repéré sur l'historique de la base (crédits, fraude), chacun indépendant."""
    from . import historique
    profil, ts, eng, base, cle = _contexte(id_source, proprietaire)
    res = {}
    for nom, f in (("credits", lambda r: historique.credits(eng, ts, profil, cle)),
                   ("fraude", lambda r: historique.fraude(eng, ts, profil, base, cle))):
        try:
            res[nom] = _risque(f)
        except SourceRefusee as e:
            res[nom] = {"indisponible": str(e)}
    return res, base


def operations_base(id_source: int, proprietaire: str) -> tuple[dict, str]:
    """Opérations atypiques dans la monnaie de la base (pour le suivi et les tâches automatiques)."""
    profil, ts, eng, base, cle = _contexte(id_source, proprietaire)
    return _risque(lambda r: r.operations_atypiques(eng, ts, profil, base, cle, limite=200)), base


def _colonnes_citees(sql: str, dialecte: str) -> set[str]:
    import sqlglot
    from sqlglot import exp
    try:
        return {c.name for c in sqlglot.parse_one(sql, read=dialecte).find_all(exp.Column)}
    except Exception:
        return set()
