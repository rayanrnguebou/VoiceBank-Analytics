"""Import de fichiers Excel / CSV : chaque feuille ou fichier devient une table d'une petite base SQLite
isolée, propre à la source. Les fichiers d'origine sont gardés en base (chiffrement au repos du
fournisseur), la base SQLite n'est qu'un cache reconstruit à la demande (le disque de Render est éphémère)."""
import csv
import hashlib
import io
import logging
import re
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

from .. import config
from . import semantique as sem

log = logging.getLogger("voicebank")

EXTENSIONS = {"csv", "txt", "xlsx"}
MAX_LIGNES = 200_000
MAX_COLONNES = 200
MAX_FICHIERS = 5
CACHE = Path(tempfile.gettempdir()) / "voicebank_sources"
RE_DATE_FR = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")
RE_DATE_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


class FichierRefuse(Exception):
    pass


def nom_table(nom: str, deja: set) -> str:
    base = "_".join(sem.jetons(Path(nom).stem))[:50] or "table"
    if base[0].isdigit():
        base = "t_" + base
    nom, i = base, 2
    while nom in deja:
        nom, i = f"{base}_{i}", i + 1
    deja.add(nom)
    return nom


def verifier(nom_fichier: str, contenu: bytes):
    ext = nom_fichier.rsplit(".", 1)[-1].lower() if "." in nom_fichier else ""
    if ext not in EXTENSIONS:
        raise FichierRefuse(f"{nom_fichier} : format non pris en charge (CSV ou Excel .xlsx)")
    if len(contenu) > config.CONNECTEUR_TAILLE_FICHIER_MO * 1024 * 1024:
        raise FichierRefuse(f"{nom_fichier} : fichier trop volumineux ({config.CONNECTEUR_TAILLE_FICHIER_MO} Mo maximum)")
    if not contenu:
        raise FichierRefuse(f"{nom_fichier} : fichier vide")
    if ext == "xlsx" and not contenu.startswith(b"PK"):
        raise FichierRefuse(f"{nom_fichier} : ce n'est pas un vrai fichier Excel")
    return ext


def _lire_csv(contenu: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texte = contenu.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    try:
        sep = csv.Sniffer().sniff(texte[:20000], delimiters=",;\t|").delimiter
    except csv.Error:
        sep = ";" if texte[:2000].count(";") > texte[:2000].count(",") else ","
    df = pd.read_csv(io.StringIO(texte), sep=sep, dtype=str, nrows=MAX_LIGNES + 1, keep_default_na=True)
    return df


def _nettoyer(df: pd.DataFrame) -> pd.DataFrame:
    """Colonnes lisibles, nombres « 1 250 000,50 » convertis, dates JJ/MM/AAAA mises au format ISO."""
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if len(df) > MAX_LIGNES:
        raise FichierRefuse(f"Plus de {MAX_LIGNES:,} lignes : découpe le fichier".replace(",", " "))
    if df.shape[1] > MAX_COLONNES:
        raise FichierRefuse(f"Plus de {MAX_COLONNES} colonnes")
    vus, noms = set(), []
    for c in df.columns:
        n = "_".join(sem.jetons(str(c)))[:60] or "colonne"
        n = ("c_" + n) if n[0].isdigit() else n
        base, i = n, 2
        while n in vus:
            n, i = f"{base}_{i}", i + 1
        vus.add(n); noms.append(n)
    df.columns = noms
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_datetime64_any_dtype(s):
            df[c] = s.dt.strftime("%Y-%m-%d")
            continue
        if s.dtype != object:
            continue
        txt = s.dropna().astype(str).str.strip()
        if not len(txt):
            continue
        if txt.str.match(RE_DATE_FR).mean() > 0.9:
            df[c] = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce").dt.strftime("%Y-%m-%d")
        elif txt.str.match(RE_DATE_ISO).mean() > 0.9:
            df[c] = pd.to_datetime(s, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
        elif not txt.str.match(r"^0\d").mean() > 0.2:
            num = pd.to_numeric(txt.str.replace(" ", "", regex=False).str.replace("\xa0", "", regex=False)
                                .str.replace(" ", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")
            if num.notna().mean() > 0.97:
                df[c] = pd.to_numeric(s.astype(str).str.replace(" ", "", regex=False).str.replace("\xa0", "", regex=False)
                                      .str.replace(" ", "", regex=False).str.replace(",", ".", regex=False), errors="coerce")
    return df


def tables_depuis(fichiers: list[tuple[str, bytes]]) -> dict[str, pd.DataFrame]:
    tables, deja = {}, set()
    for nom, contenu in fichiers:
        ext = verifier(nom, contenu)
        if ext == "xlsx":
            feuilles = pd.read_excel(io.BytesIO(contenu), sheet_name=None, dtype=object, engine="openpyxl")
            for feuille, df in feuilles.items():
                if df.dropna(how="all").empty:
                    continue
                nom_t = nom_table(feuille if len(feuilles) > 1 else nom, deja)
                tables[nom_t] = _nettoyer(df)
        else:
            tables[nom_table(nom, deja)] = _nettoyer(_lire_csv(contenu))
    if not tables:
        raise FichierRefuse("Aucune donnée trouvée dans les fichiers")
    return tables


def construire_sqlite(id_source: int, fichiers: list[tuple[str, bytes]]) -> Path:
    """Base SQLite de la source, en cache (reconstruite si absente ou si les fichiers ont changé)."""
    empreinte = hashlib.sha256(b"".join(hashlib.sha256(c).digest() for _, c in fichiers)).hexdigest()[:16]
    CACHE.mkdir(parents=True, exist_ok=True, mode=0o700)
    chemin = CACHE / f"source_{int(id_source)}_{empreinte}.sqlite"
    if chemin.exists():
        return chemin
    for ancien in CACHE.glob(f"source_{int(id_source)}_*.sqlite"):
        ancien.unlink(missing_ok=True)
    tmp = chemin.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    conn = sqlite3.connect(tmp)
    try:
        for nom, df in tables_depuis(fichiers).items():
            df.to_sql(nom, conn, index=False)
        conn.commit()
    finally:
        conn.close()
    tmp.replace(chemin)
    return chemin
