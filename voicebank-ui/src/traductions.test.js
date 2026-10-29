// Chaque texte affiché avec tx("…") doit avoir sa version anglaise : un texte oublié resterait en français.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import en from "./traductions/en.json";

function fichiers(dossier) {
  return readdirSync(dossier).flatMap(f => {
    const p = join(dossier, f);
    if (statSync(p).isDirectory()) return f === "traductions" ? [] : fichiers(p);
    return /\.jsx?$/.test(f) && !/\.test\./.test(f) && f !== "i18n.js" ? [p] : [];
  });
}

test("tous les textes de l'interface ont une traduction anglaise", () => {
  const manquants = [];
  let total = 0;
  for (const f of fichiers(join(__dirname))) {
    const source = readFileSync(f, "utf8");
    for (const m of source.matchAll(/\btx\(\s*"((?:[^"\\]|\\.)*)"/g)) {
      total += 1;
      const texte = JSON.parse(`"${m[1]}"`);
      if (!(texte in en)) manquants.push(`${f.split("/src/")[1]} : ${texte}`);
    }
  }
  expect(total).toBeGreaterThan(1000);
  expect(manquants).toEqual([]);
});

test("les variables {x} sont les mêmes en français et en anglais", () => {
  const variables = t => [...t.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort().join(",");
  const differents = Object.entries(en).filter(([fr, anglais]) => variables(fr) !== variables(anglais)).map(([fr]) => fr);
  expect(differents).toEqual([]);
});
