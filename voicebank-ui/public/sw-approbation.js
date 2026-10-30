// VoiceBank : notifications « approuver la connexion » (double authentification sur le téléphone).
// Le contenu arrive chiffré ; seul ce téléphone peut le lire. Toucher la notification ouvre l'écran d'approbation.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

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
