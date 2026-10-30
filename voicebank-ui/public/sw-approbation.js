// VoiceBank : travailleur du site (enregistré à chaque visite, nom gardé pour les téléphones déjà inscrits).
// 1. Notifications « approuver la connexion » (double authentification sur le téléphone) : le contenu arrive chiffré.
// 2. Page « hors ligne » quand il n'y a pas d'Internet (application Android et icône sur l'écran d'accueil).
// Rien d'autre n'est mis en cache : les données restent toujours celles du serveur.
const CACHE = "voicebank-hors-ligne-v1";
self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.add(new Request("/hors-ligne.html", { cache: "reload" }))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil((async () => {
    for (const nom of await caches.keys()) if (nom !== CACHE) await caches.delete(nom);
    await self.clients.claim();
  })());
});

// Pages seulement (pas l'API, pas les fichiers) : le réseau d'abord, la page « hors ligne » s'il ne répond pas
self.addEventListener("fetch", e => {
  if (e.request.mode !== "navigate" || new URL(e.request.url).origin !== self.location.origin) return;
  e.respondWith(fetch(e.request).catch(async () => (await caches.match("/hors-ligne.html")) || Response.error()));
});

self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) { d = {}; }
  if (d.type !== "approbation" || !d.id) return;
  e.waitUntil(self.registration.showNotification(d.titre || "VoiceBank : connexion demandée", {
    body: d.texte || "Touche pour approuver ou refuser.",
    tag: `approbation-${d.id}`,
    icon: "/logo192.png",
    badge: "/logo192.png",
    requireInteraction: true,
    data: { url: `/?approbation=${encodeURIComponent(d.id)}` },
  }));
});

// Toucher la notification : si VoiceBank est déjà ouvert (par exemple sur l'écran de connexion qui attend), on affiche
// la demande PAR-DESSUS, sans quitter la page en cours ; sinon on ouvre l'écran d'approbation.
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL(e.notification.data?.url || "/", self.location.origin);
  const id = url.searchParams.get("approbation");
  e.waitUntil((async () => {
    const fenetres = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const ouverte = fenetres.find(f => f.focused) || fenetres[0];
    if (ouverte && id) {
      ouverte.postMessage({ type: "voicebank-approbation", id });
      return ouverte.focus();
    }
    return self.clients.openWindow(url.href);
  })());
});
