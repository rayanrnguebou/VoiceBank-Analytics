// Villes et banques d'un pays, chargées à la demande (public/referentiel/<type>/<ISO>.json, une fois par session).
// Format d'un fichier : ["Nom", "Nom|autre nom ou sigle", …] ; l'autre nom sert seulement à la recherche.
import { useEffect, useState } from "react";
import { PAYS, VILLES } from "./listes";

const cache = new Map();

export const isoDe = pays => (PAYS.find(([n]) => n === pays) || [])[2] || null;

export function versOptions(liste) {
  return (liste || []).map(x => {
    const [nom, ...autres] = String(x).split("|");
    return { valeur: nom, libelle: nom, alias: autres.join("|") || undefined };
  });
}

export function chargerReferentiel(type, iso) {
  if (!iso) return Promise.resolve([]);
  const cle = `${type}/${iso}`;
  if (!cache.has(cle)) {
    cache.set(cle, fetch(`${process.env.PUBLIC_URL || ""}/referentiel/${cle}.json`)
      .then(r => (r.ok ? r.json() : []))
      .then(versOptions)
      .catch(() => { cache.delete(cle); return []; }));
  }
  return cache.get(cle);
}

// Options d'un pays ; « avant » : valeurs à proposer en tête (ex. celles que le modèle connaît)
export function useReferentiel(type, pays, avant = []) {
  const iso = isoDe(pays);
  const [options, setOptions] = useState(() => fusionner(avant, versOptions(type === "villes" ? VILLES[pays] : [])));
  const [chargement, setChargement] = useState(false);
  const cleAvant = avant.join("|");
  useEffect(() => {
    let actif = true;
    const secours = versOptions(type === "villes" ? VILLES[pays] : []);
    setOptions(fusionner(avant, secours));
    if (!iso) return undefined;
    setChargement(true);
    chargerReferentiel(type, iso).then(liste => {
      if (actif) { setOptions(fusionner(avant, liste.length ? liste : secours)); setChargement(false); }
    });
    return () => { actif = false; };
  }, [type, iso, pays, cleAvant]); // eslint-disable-line react-hooks/exhaustive-deps
  return { options, chargement };
}

function fusionner(avant, liste) {
  const vus = new Set();
  const res = [];
  for (const o of [...versOptions(avant), ...liste]) {
    const k = [o.valeur, ...String(o.alias || "").split("|")].filter(Boolean).map(x => x.toLowerCase());
    if (k.some(x => vus.has(x))) continue;      // « BICEC » déjà connu : on ne propose pas une 2e fois la même banque
    k.forEach(x => vus.add(x)); res.push(o);
  }
  return res;
}
