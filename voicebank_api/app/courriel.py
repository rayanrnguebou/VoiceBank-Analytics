"""E-mails transactionnels : modèle professionnel commun (en-tête, bouton, récapitulatif, signature).

Envoi par Brevo (API HTTPS) en priorité, sinon SMTP. Sans configuration, rien n'est envoyé.
La mise en page utilise des tableaux et des styles en ligne : c'est ce que les messageries (Gmail,
Outlook, mobiles) affichent correctement.
"""
import html
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from . import config

log = logging.getLogger("voicebank")

FORET, FORET_FONCE, LAITON, TEXTE, DISCRET, FOND = "#1F654D", "#14432F", "#C9A13B", "#1F2937", "#6B7280", "#F3F5F4"


class EnvoiImpossible(Exception):
    pass


SERVEURS_LOCAUX = {"localhost", "127.0.0.1", "::1", "mailpit", "mailhog"}   # serveurs de test (Mailpit…)


def _smtp_local() -> bool:
    return config.SMTP_HOTE.lower() in SERVEURS_LOCAUX


def disponible() -> bool:
    return bool(config.EMAIL_EXPEDITEUR and (config.BREVO_API_KEY or (
        config.SMTP_HOTE and (config.SMTP_UTILISATEUR or _smtp_local()))))


@dataclass
class Message:
    sujet: str
    titre: str
    paragraphes: list[str]
    salutation: str = "Bonjour,"
    code: str | None = None                                  # code à recopier (affiché en grand)
    bouton: tuple[str, str] | None = None                    # (libellé, adresse)
    details: list[tuple[str, str]] = field(default_factory=list)   # récapitulatif (reçu, compte…)
    apres: list[str] = field(default_factory=list)           # paragraphes après le bouton
    apercu: str = ""                                         # texte d'aperçu dans la boîte de réception
    note: str | None = None                                  # mention discrète en bas (sécurité…)


def _e(t) -> str:
    return html.escape(str(t))


def _paragraphes(lignes: list[str]) -> str:
    return "".join(f'<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:{TEXTE}">{_e(p)}</p>' for p in lignes)


def rendre_html(m: Message) -> str:
    site = config.URL_INTERFACE
    code = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 22px"><tr>'
            f'<td style="background:{FOND};border:1px solid #D9E2DD;border-radius:10px;padding:14px 26px;'
            f'font-family:Consolas,Menlo,monospace;font-size:30px;font-weight:700;letter-spacing:8px;color:{FORET_FONCE}">'
            f'{_e(m.code)}</td></tr></table>') if m.code else ""
    bouton = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 22px"><tr>'
              f'<td style="border-radius:8px;background:{FORET}">'
              f'<a href="{_e(m.bouton[1])}" style="display:inline-block;padding:13px 26px;font-size:15px;font-weight:700;'
              f'color:#FFFFFF;text-decoration:none;border-radius:8px">{_e(m.bouton[0])}</a></td></tr></table>'
              f'<p style="margin:0 0 18px;font-size:12px;line-height:1.5;color:{DISCRET}">Si le bouton ne fonctionne pas, '
              f'copiez ce lien dans votre navigateur :<br><a href="{_e(m.bouton[1])}" style="color:{FORET};word-break:break-all">'
              f'{_e(m.bouton[1])}</a></p>') if m.bouton else ""
    details = ""
    if m.details:
        lignes = "".join(
            f'<tr><td style="padding:9px 14px;font-size:13px;color:{DISCRET};border-bottom:1px solid #E5E7EB;width:42%">{_e(k)}</td>'
            f'<td style="padding:9px 14px;font-size:14px;color:{TEXTE};font-weight:600;border-bottom:1px solid #E5E7EB">{_e(v)}</td></tr>'
            for k, v in m.details)
        details = (f'<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:4px 0 22px;'
                   f'border:1px solid #E5E7EB;border-radius:8px;border-collapse:separate;overflow:hidden">{lignes}</table>')
    contact = (f' · <a href="mailto:{_e(config.EMAIL_CONTACT)}" style="color:{FORET};text-decoration:none">'
               f'{_e(config.EMAIL_CONTACT)}</a>') if config.EMAIL_CONTACT else ""
    signature = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:26px;border-top:1px solid #E5E7EB;'
                 f'padding-top:18px;width:100%"><tr><td style="padding-top:18px">'
                 f'<p style="margin:0 0 2px;font-size:14px;color:{TEXTE}">Cordialement,</p>'
                 f'<p style="margin:10px 0 0;font-size:15px;font-weight:700;color:{FORET_FONCE}">{_e(config.EMAIL_SIGNATURE_NOM)}</p>'
                 f'<p style="margin:2px 0 0;font-size:13px;color:{DISCRET}">{_e(config.EMAIL_SIGNATURE_FONCTION)}</p>'
                 f'<p style="margin:6px 0 0;font-size:13px;color:{DISCRET}">'
                 f'<a href="{_e(site)}" style="color:{FORET};text-decoration:none">{_e(site.replace("https://", "").replace("http://", ""))}</a>'
                 f'{contact}</p></td></tr></table>')
    note = (f'<p style="margin:18px 0 0;font-size:12px;line-height:1.5;color:{DISCRET}">{_e(m.note)}</p>') if m.note else ""
    return f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{_e(m.sujet)}</title></head>
<body style="margin:0;padding:0;background:{FOND};font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<span style="display:none;max-height:0;overflow:hidden;opacity:0">{_e(m.apercu or m.titre)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{FOND};padding:28px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:580px;background:#FFFFFF;border-radius:14px;overflow:hidden;border:1px solid #E1E7E4">
<tr><td style="background:{FORET_FONCE};padding:22px 32px">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="width:34px;height:34px;background:{LAITON};border-radius:8px;text-align:center;font-weight:800;color:{FORET_FONCE};font-size:16px">V</td>
<td style="padding-left:12px;font-size:17px;font-weight:700;color:#FFFFFF">VoiceBank <span style="color:{LAITON}">Analytics</span></td>
</tr></table></td></tr>
<tr><td style="padding:32px 32px 28px">
<h1 style="margin:0 0 18px;font-size:21px;line-height:1.35;color:{TEXTE}">{_e(m.titre)}</h1>
<p style="margin:0 0 14px;font-size:15px;line-height:1.6;color:{TEXTE}">{_e(m.salutation)}</p>
{_paragraphes(m.paragraphes)}{code}{details}{bouton}{_paragraphes(m.apres)}{signature}{note}
</td></tr></table>
<p style="max-width:580px;margin:16px auto 0;font-size:11px;line-height:1.5;color:#9CA3AF;text-align:center">
Message automatique envoyé par VoiceBank Analytics, merci de ne pas y répondre directement.<br>
Interrogez vos données bancaires à la voix : fraude, crédit, clients.</p>
</td></tr></table></body></html>'''


def rendre_texte(m: Message) -> str:
    parties = [m.titre, "", m.salutation, ""] + m.paragraphes
    if m.code:
        parties += ["", f"    {m.code}", ""]
    if m.details:
        parties += [""] + [f"{k} : {v}" for k, v in m.details] + [""]
    if m.bouton:
        parties += ["", f"{m.bouton[0]} : {m.bouton[1]}", ""]
    parties += m.apres + ["", "Cordialement,", config.EMAIL_SIGNATURE_NOM, config.EMAIL_SIGNATURE_FONCTION,
                          config.URL_INTERFACE + (f" · {config.EMAIL_CONTACT}" if config.EMAIL_CONTACT else "")]
    if m.note:
        parties += ["", m.note]
    return "\n".join(parties)


def envoyer_message(destinataire: str, m: Message):
    """Envoie le message ; lève EnvoiImpossible avec une raison lisible en cas d'échec."""
    if not disponible():
        raise EnvoiImpossible("Aucun service d'e-mail configuré (BREVO_API_KEY ou SMTP_HOTE, et EMAIL_EXPEDITEUR)")
    texte, contenu_html = rendre_texte(m), rendre_html(m)
    if config.BREVO_API_KEY:
        try:
            r = httpx.post("https://api.brevo.com/v3/smtp/email", timeout=15, headers={
                "api-key": config.BREVO_API_KEY, "accept": "application/json", "content-type": "application/json"},
                json={"sender": {"name": config.EMAIL_NOM_EXPEDITEUR, "email": config.EMAIL_EXPEDITEUR},
                      "replyTo": {"email": config.EMAIL_CONTACT or config.EMAIL_EXPEDITEUR},
                      "to": [{"email": destinataire}], "subject": m.sujet, "htmlContent": contenu_html,
                      "textContent": texte})
        except httpx.HTTPError as e:
            raise EnvoiImpossible(f"Brevo injoignable : {e}")
        if r.status_code >= 300:
            try:
                detail = r.json().get("message") or r.text
            except ValueError:
                detail = r.text
            raise EnvoiImpossible(f"Brevo a refusé l'envoi ({r.status_code}) : {str(detail)[:300]}")
        return
    msg = EmailMessage()
    msg["Subject"], msg["To"] = m.sujet, destinataire
    msg["From"] = formataddr((config.EMAIL_NOM_EXPEDITEUR, config.EMAIL_EXPEDITEUR))
    if config.EMAIL_CONTACT:
        msg["Reply-To"] = config.EMAIL_CONTACT
    msg.set_content(texte)
    msg.add_alternative(contenu_html, subtype="html")
    contexte = ssl.create_default_context()
    try:
        if config.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(config.SMTP_HOTE, 465, context=contexte, timeout=15) as s:
                s.login(config.SMTP_UTILISATEUR, config.SMTP_MOT_DE_PASSE)
                s.send_message(msg)
        else:
            with smtplib.SMTP(config.SMTP_HOTE, config.SMTP_PORT, timeout=15) as s:
                if not _smtp_local():            # chiffrement obligatoire hors serveur de test local
                    s.starttls(context=contexte)
                if config.SMTP_UTILISATEUR:
                    s.login(config.SMTP_UTILISATEUR, config.SMTP_MOT_DE_PASSE)
                s.send_message(msg)
    except (smtplib.SMTPException, OSError) as e:
        raise EnvoiImpossible(f"Serveur SMTP : {e}")


def envoyer(destinataire: str, sujet: str, titre: str, paragraphes: list[str], code: str | None = None):
    """Forme simple (compatibilité)."""
    envoyer_message(destinataire, Message(sujet=sujet, titre=titre, paragraphes=paragraphes, code=code))


def envoyer_en_arriere_plan(destinataire: str, m: Message):
    """N'attend pas l'envoi (pas de différence de temps de réponse, pas de blocage de l'API)."""
    import threading

    def tache():
        try:
            envoyer_message(destinataire, m)
            log.info("E-mail « %s » envoyé", m.sujet)
        except Exception as e:
            log.warning("E-mail non envoyé (%s) : %s", m.sujet, e)
    threading.Thread(target=tache, daemon=True).start()
