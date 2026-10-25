"""Abonnements et paiement (NotchPay : MTN MoMo, Orange Money, cartes bancaires, en FCFA).

Règles de sécurité :
* le montant et la durée viennent UNIQUEMENT de la configuration serveur (jamais du navigateur) ;
* la page de paiement est hébergée par NotchPay : aucune donnée de carte ou de mobile money
  ne transite par VoiceBank ;
* un paiement n'est activé qu'après une vérification serveur à serveur auprès de NotchPay
  (statut « complete », même référence, même montant, même devise) ;
* les webhooks sont authentifiés (HMAC SHA-256 du corps brut, comparaison à temps constant) ;
* l'activation est idempotente : un même paiement ne prolonge l'abonnement qu'une seule fois.
"""
import hashlib
import hmac
import json
import logging
import secrets

import httpx
from sqlalchemy import text

from . import config, db

log = logging.getLogger("voicebank")


class PaiementRefuse(Exception):
    """Erreur affichable à l'utilisateur."""


def disponible() -> bool:
    return bool(config.NOTCHPAY_PUBLIC_KEY) or config.PAIEMENT_SIMULATION


def mode() -> str:
    if config.NOTCHPAY_PUBLIC_KEY:
        cle = config.NOTCHPAY_PUBLIC_KEY.lower()
        # Anciennes clés « test_… », nouvelles « pk_test.… »
        return "test" if cle.startswith(("test_", "pk_test", "pk.test")) or "_test." in cle else "reel"
    return "simulation" if config.PAIEMENT_SIMULATION else "indisponible"


def formules() -> list[dict]:
    jour = config.FORMULES["jour"][2]
    res = []
    for code, (libelle, jours, prix) in config.FORMULES.items():
        economie = round(100 * (1 - prix / (jour * jours))) if jours > 1 and jour else 0
        res.append({"code": code, "libelle": libelle, "duree_jours": jours, "prix": prix,
                    "devise": config.DEVISE, "economie_pct": max(economie, 0)})
    return res


# ── Échanges avec NotchPay ───────────────────────────────────────────

def _client() -> httpx.Client:
    return httpx.Client(base_url=config.NOTCHPAY_URL, timeout=20,
                        headers={"Authorization": config.NOTCHPAY_PUBLIC_KEY, "Accept": "application/json"})


def _initialiser_notchpay(reference: str, montant: int, client: dict, description: str) -> tuple[str, str | None]:
    corps = {"amount": montant, "currency": config.DEVISE, "reference": reference, "description": description,
             "callback": f"{config.URL_INTERFACE}/?paiement={reference}",
             "customer": {"name": client["nom"], "email": client["email"], "phone": client.get("telephone") or None}}
    try:
        with _client() as c:
            r = c.post("/payments", json=corps)
    except httpx.HTTPError as e:
        log.warning("NotchPay injoignable : %s", e)
        raise PaiementRefuse("Le service de paiement est injoignable, réessaie dans un instant.")
    if r.status_code not in (200, 201):
        log.warning("NotchPay a refusé l'initialisation (%s) : %s", r.status_code, r.text[:300])
        raise PaiementRefuse("Le service de paiement a refusé la demande. Vérifie ton e-mail et ton numéro.")
    data = r.json()
    url = data.get("authorization_url")
    if not url or not str(url).startswith("https://"):
        raise PaiementRefuse("Réponse inattendue du service de paiement.")
    return url, (data.get("transaction") or {}).get("reference")


def _verifier_notchpay(reference_fournisseur: str) -> dict | None:
    try:
        with _client() as c:
            r = c.get(f"/payments/{reference_fournisseur}")
    except httpx.HTTPError as e:
        log.warning("NotchPay injoignable pour la vérification : %s", e)
        return None
    if r.status_code not in (200, 202):
        return None
    return r.json().get("transaction") or None


def signature_valide(corps_brut: bytes, signature: str | None) -> bool:
    if not config.NOTCHPAY_HASH_KEY or not signature:
        return False
    attendu = hmac.new(config.NOTCHPAY_HASH_KEY.encode(), corps_brut, hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendu, signature.strip().lower())


# ── Commandes ────────────────────────────────────────────────────────

def commander(utilisateur: str, formule: str, type_client: str, informations: dict) -> dict:
    """Enregistre la facturation et la commande, puis retourne l'adresse de paiement."""
    if formule not in config.FORMULES:
        raise PaiementRefuse("Formule inconnue")
    if not disponible():
        raise PaiementRefuse("Le paiement en ligne n'est pas encore activé. Contacte-nous pour t'abonner.")
    libelle, jours, montant = config.FORMULES[formule]
    db.ecrire("INSERT INTO voicebank.profils_facturation (utilisateur, type_client, informations) "
              "VALUES (:u, :t, CAST(:i AS JSONB)) ON CONFLICT (utilisateur) DO UPDATE SET "
              "type_client = EXCLUDED.type_client, informations = EXCLUDED.informations, date_maj = NOW()",
              {"u": utilisateur, "t": type_client, "i": json.dumps(informations, ensure_ascii=False)})
    reference = "vb-" + secrets.token_hex(12)
    fournisseur = "notchpay" if config.NOTCHPAY_PUBLIC_KEY else "simulation"
    db.ecrire("INSERT INTO voicebank.paiements (reference, utilisateur, formule, duree_jours, montant, devise, "
              "fournisseur) VALUES (:r, :u, :f, :j, :m, :d, :fo)",
              {"r": reference, "u": utilisateur, "f": formule, "j": jours, "m": montant,
               "d": config.DEVISE, "fo": fournisseur})
    if fournisseur == "simulation":
        url, ref_f = f"{config.URL_INTERFACE}/?paiement={reference}", "sim-" + reference
    else:
        nom = informations.get("raison_sociale") or informations.get("nom_complet") or utilisateur
        url, ref_f = _initialiser_notchpay(reference, montant, {
            "nom": str(nom)[:100], "email": informations.get("email") or utilisateur,
            "telephone": informations.get("telephone")}, f"VoiceBank Analytics — abonnement {libelle}")
    db.ecrire("UPDATE voicebank.paiements SET reference_fournisseur = :rf WHERE reference = :r",
              {"r": reference, "rf": ref_f})
    return {"reference": reference, "url_paiement": url, "montant": montant, "devise": config.DEVISE,
            "formule": formule, "mode": mode()}


def _paiement(reference: str):
    r = db.ecrire("SELECT reference, utilisateur, formule, duree_jours, montant, devise, statut, fournisseur, "
                  "reference_fournisseur, abonnement_fin FROM voicebank.paiements WHERE reference = :r "
                  "OR reference_fournisseur = :r", {"r": reference})
    return r.lignes[0] if r.lignes else None


def _activer(p) -> bool:
    """Passe le paiement à « payé » et prolonge l'abonnement, dans une transaction et une seule fois
    (la ligne du paiement est verrouillée : deux confirmations simultanées ne comptent qu'une fois)."""
    with db.moteur_app.begin() as conn:
        statut = conn.execute(text("SELECT statut FROM voicebank.paiements WHERE reference = :r FOR UPDATE"),
                              {"r": p.reference}).scalar()
        if statut != "en_attente":
            return False
        fin = conn.execute(text(
            "UPDATE voicebank.utilisateurs SET "
            "role = CASE WHEN role IN ('visiteur', 'client') THEN 'client' ELSE role END, "
            "abonnement_fin = GREATEST(COALESCE(abonnement_fin, LOCALTIMESTAMP), LOCALTIMESTAMP) "
            "                 + make_interval(days => :j), formule = :f "
            "WHERE nom = :u RETURNING abonnement_fin"),
            {"u": p.utilisateur, "j": p.duree_jours, "f": p.formule}).scalar()
        conn.execute(text("UPDATE voicebank.paiements SET statut = 'paye', date_paiement = LOCALTIMESTAMP, "
                          "abonnement_fin = :fin WHERE reference = :r"), {"r": p.reference, "fin": fin})
    log.info("Abonnement %s activé pour %s (paiement %s)", p.formule, p.utilisateur, p.reference)
    return True


def verifier(reference: str, utilisateur: str | None = None) -> dict:
    """Vérifie un paiement auprès du fournisseur et l'active s'il est confirmé.
    `utilisateur` : si fourni, le paiement doit lui appartenir."""
    p = _paiement(reference)
    if p is None or (utilisateur and p.utilisateur != utilisateur):
        raise PaiementRefuse("Paiement introuvable")
    if p.statut == "en_attente":
        if p.fournisseur == "simulation":
            if not config.PAIEMENT_SIMULATION:
                raise PaiementRefuse("Paiement introuvable")
            _activer(p)
        else:
            t = _verifier_notchpay(p.reference_fournisseur or p.reference)
            statut = (t or {}).get("status")
            conforme = (t is not None and statut == "complete"
                        and str(t.get("trxref") or t.get("merchant_reference") or p.reference) == p.reference
                        and int(float(t.get("amount") or 0)) == p.montant
                        and str(t.get("currency") or "").upper() == p.devise)
            if conforme:
                _activer(p)
            elif statut == "complete":
                log.error("Paiement %s NON conforme (montant / devise / référence) : %s", p.reference, t)
            elif statut in ("failed", "canceled", "expired"):
                db.ecrire("UPDATE voicebank.paiements SET statut = :s WHERE reference = :r AND statut = 'en_attente'",
                          {"r": p.reference, "s": "annule" if statut == "canceled" else "echoue"})
        p = _paiement(p.reference)
    return {"reference": p.reference, "statut": p.statut, "formule": p.formule, "montant": p.montant,
            "devise": p.devise, "abonnement_fin": p.abonnement_fin.isoformat() if p.abonnement_fin else None}


def traiter_webhook(corps_brut: bytes, signature: str | None) -> str:
    if not signature_valide(corps_brut, signature):
        raise PaiementRefuse("Signature invalide")
    try:
        evt = json.loads(corps_brut)
    except ValueError:
        raise PaiementRefuse("Corps invalide")
    data = evt.get("data") if isinstance(evt.get("data"), dict) else evt
    refs = [data.get(k) for k in ("trxref", "merchant_reference", "reference") if data.get(k)]
    for ref in refs:
        try:
            # On ne fait pas confiance au contenu du webhook : on revérifie auprès de NotchPay.
            return verifier(str(ref))["statut"]
        except PaiementRefuse:
            continue
    return "ignore"


def mes_paiements(utilisateur: str) -> list[dict]:
    r = db.ecrire("SELECT reference, formule, montant, devise, statut, date_creation, date_paiement, abonnement_fin "
                  "FROM voicebank.paiements WHERE utilisateur = :u ORDER BY date_creation DESC LIMIT 20",
                  {"u": utilisateur})
    return [{k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in l._mapping.items()} for l in r.lignes]
