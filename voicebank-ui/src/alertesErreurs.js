// Alertes d'erreurs de l'interface (Sentry, offre gratuite). Chargé seulement si REACT_APP_SENTRY_DSN est défini :
// sinon, rien n'est téléchargé. Aucune donnée personnelle : pas d'IP, pas de texte saisi, adresses nettoyées.
const DSN = import.meta.env.REACT_APP_SENTRY_DSN;

function nettoyerUrl(url) {
  try {
    const u = new URL(url);
    return `${u.origin}${u.pathname}`;          // les paramètres (?invitation=, ?deblocage=…) peuvent être secrets
  } catch (e) {
    return undefined;
  }
}

export const alertesInterfaceActives = !!DSN;

// Bouton « Envoyer une erreur de test » : une erreur de l'interface part chez Sentry (projet « navigateur »).
export async function envoyerErreurTestInterface(par) {
  if (!DSN) throw new Error("REACT_APP_SENTRY_DSN absent");
  const Sentry = await import("@sentry/browser");
  if (!Sentry.getClient()) await demarrerAlertesErreurs();
  const id = Sentry.captureException(new Error(`Erreur de test VoiceBank (interface), déclenchée par ${par} : la surveillance fonctionne.`));
  await Sentry.flush(5000);
  return id;
}

export function demarrerAlertesErreurs() {
  if (!DSN) return Promise.resolve();
  return import("@sentry/browser").then(Sentry => {
    Sentry.init({
      dsn: DSN,
      environment: import.meta.env.MODE,
      sendDefaultPii: false,
      tracesSampleRate: 0,
      beforeSend(evenement) {
        if (evenement.request) {
          evenement.request = { url: nettoyerUrl(evenement.request.url) };
        }
        delete evenement.user;
        return evenement;
      },
      beforeBreadcrumb(miette) {
        if (miette.category === "ui.input") return null;               // jamais le contenu des champs
        if (miette.data?.url) miette.data.url = nettoyerUrl(miette.data.url) || miette.data.url;
        if (miette.data?.to) miette.data.to = nettoyerUrl(new URL(miette.data.to, window.location.origin).href);
        if (miette.data?.from) miette.data.from = nettoyerUrl(new URL(miette.data.from, window.location.origin).href);
        return miette;
      },
    });
  }).catch(() => { /* surveillance indisponible : sans effet sur l'application */ });
}
