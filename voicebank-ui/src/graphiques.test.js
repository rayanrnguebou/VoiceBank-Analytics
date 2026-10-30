import { detecterTypeGraphique, formaterValeur } from "./graphiques";
import { chargerHistorique, sauverHistorique, MAX_HISTORIQUE, MAX_LIGNES_HISTO } from "./panneaux/Historique";
import { reglesMotDePasse } from "./panneaux/Comptes";

const villes = n => Array.from({ length: n }, (_, i) => ({ ville: `Ville ${i}`, total: i * 10 }));

test("type de graphique choisi d'après les colonnes et le nombre de lignes", () => {
  expect(detecterTypeGraphique(["ville"], [])).toBe("table");
  expect(detecterTypeGraphique(["total"], [{ total: 3 }])).toBe("kpi");
  expect(detecterTypeGraphique(["mois", "montant"], [{ mois: "2026-01", montant: 1 }, { mois: "2026-02", montant: 2 }])).toBe("line");
  expect(detecterTypeGraphique(["ville", "total"], villes(5))).toBe("bar");
  expect(detecterTypeGraphique(["statut"], [{ statut: "a" }, { statut: "b" }])).toBe("pie");
  expect(detecterTypeGraphique(["ville", "total"], villes(30))).toBe("area");
  // Base connectée aux noms inconnus : une catégorie et une valeur
  expect(detecterTypeGraphique(["region", "chiffre"], [{ region: "Nord", chiffre: 3 }, { region: "Sud", chiffre: 4 }])).toBe("bar");
  expect(detecterTypeGraphique(["a", "b", "c", "d", "e"], [{ a: "x", b: 1, c: 2, d: 3, e: 4 }, { a: "y", b: 1, c: 2, d: 3, e: 4 }])).toBe("table");
});

test("montants abrégés sur les axes", () => {
  expect(formaterValeur(2_500_000)).toBe("2.5M");
  expect(formaterValeur(1_500)).toBe("1.5k");
  expect(formaterValeur(null)).toBe("");
  expect(formaterValeur("Douala")).toBe("Douala");
});

test("historique de session : limité en nombre d'entrées et en lignes, séparé par utilisateur", () => {
  sessionStorage.clear();
  const entrees = Array.from({ length: MAX_HISTORIQUE + 5 }, (_, i) => ({ id: i, question: `q${i}`,
    data: Array.from({ length: MAX_LIGNES_HISTO + 10 }, (_, j) => ({ j })) }));
  sauverHistorique("awa", entrees);
  const relu = chargerHistorique("awa");
  expect(relu).toHaveLength(MAX_HISTORIQUE);
  expect(relu[0].data).toHaveLength(MAX_LIGNES_HISTO);
  expect(chargerHistorique("paul")).toEqual([]);
  sessionStorage.setItem("voicebank_historique_casse", "{pas du json");
  expect(chargerHistorique("casse")).toEqual([]);
});

test("règles du mot de passe affichées pendant la saisie (mêmes que l'API)", () => {
  const ok = r => r.map(x => x.ok);
  expect(ok(reglesMotDePasse("court", "awa"))).toEqual([false, false, true]);
  expect(ok(reglesMotDePasse("Baobab-Douala-2026", "awa"))).toEqual([true, true, true]);
  expect(ok(reglesMotDePasse("Awa-Baobab-2026!", "awa"))).toEqual([true, true, false]);
});
