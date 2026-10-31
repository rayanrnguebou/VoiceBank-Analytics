// Fonctions récentes utilisées par certaines bibliothèques (graphiques, PDF) : ajoutées si le navigateur ne les a pas
// (iPhone sous iOS 14-15.3, anciens navigateurs Android). Importé EN PREMIER par index.jsx.
if (!Object.hasOwn) {
  Object.defineProperty(Object, "hasOwn", {
    value: (objet, cle) => Object.prototype.hasOwnProperty.call(Object(objet), cle), configurable: true, writable: true,
  });
}
if (!Array.prototype.at) {
  Object.defineProperty(Array.prototype, "at", {
    value(n) { const i = Math.trunc(n) || 0; return this[i < 0 ? this.length + i : i]; }, configurable: true, writable: true,
  });
}
if (typeof window !== "undefined" && !window.structuredClone) {
  // Suffisant pour les usages des bibliothèques (objets simples, erreurs) ; jamais de fonctions à copier.
  window.structuredClone = valeur => (valeur === undefined ? undefined : valeur instanceof Error
    ? Object.assign(new valeur.constructor(valeur.message), valeur) : JSON.parse(JSON.stringify(valeur)));
}
