"""Envoi d'e-mails : Brevo (API HTTPS) en priorité, sinon SMTP. Sans configuration, rien n'est envoyé."""
import html
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from . import config

log = logging.getLogger("voicebank")


class EnvoiImpossible(Exception):
    pass


SERVEURS_LOCAUX = {"localhost", "127.0.0.1", "::1", "mailpit", "mailhog"}   # serveurs de test (Mailpit…)


def _smtp_local() -> bool:
    return config.SMTP_HOTE.lower() in SERVEURS_LOCAUX


def disponible() -> bool:
    return bool(config.EMAIL_EXPEDITEUR and (config.BREVO_API_KEY or (
        config.SMTP_HOTE and (config.SMTP_UTILISATEUR or _smtp_local()))))


def _html(titre: str, paragraphes: list[str], code: str | None = None) -> str:
    corps = "".join(f'<p style="margin:0 0 14px;color:#374151;font-size:15px;line-height:1.5">{html.escape(p)}</p>'
                    for p in paragraphes)
    bloc = (f'<p style="margin:8px 0 22px;font-size:30px;letter-spacing:8px;font-weight:700;color:#14432f;'
            f'font-family:Consolas,monospace">{html.escape(code)}</p>') if code else ""
    return (f'<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;padding:28px;'
            f'border:1px solid #e5e7eb;border-radius:12px">'
            f'<p style="margin:0 0 18px;font-weight:700;color:#1F654D">VoiceBank Analytics</p>'
            f'<h1 style="font-size:19px;color:#111827;margin:0 0 14px">{html.escape(titre)}</h1>{bloc}{corps}'
            f'<p style="margin:22px 0 0;color:#9CA3AF;font-size:12px">Message automatique, merci de ne pas y répondre.</p></div>')


def envoyer(destinataire: str, sujet: str, titre: str, paragraphes: list[str], code: str | None = None):
    if not disponible():
        raise EnvoiImpossible("Aucun service d'e-mail configuré")
    texte = "\n\n".join([titre] + ([code] if code else []) + paragraphes)
    contenu_html = _html(titre, paragraphes, code)
    if config.BREVO_API_KEY:
        r = httpx.post("https://api.brevo.com/v3/smtp/email", timeout=15, headers={
            "api-key": config.BREVO_API_KEY, "accept": "application/json", "content-type": "application/json"},
            json={"sender": {"name": config.EMAIL_NOM_EXPEDITEUR, "email": config.EMAIL_EXPEDITEUR},
                  "to": [{"email": destinataire}], "subject": sujet, "htmlContent": contenu_html, "textContent": texte})
        if r.status_code >= 300:
            raise EnvoiImpossible(f"Brevo a refusé l'envoi ({r.status_code})")
        return
    msg = EmailMessage()
    msg["Subject"], msg["To"] = sujet, destinataire
    msg["From"] = formataddr((config.EMAIL_NOM_EXPEDITEUR, config.EMAIL_EXPEDITEUR))
    msg.set_content(texte)
    msg.add_alternative(contenu_html, subtype="html")
    contexte = ssl.create_default_context()
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
