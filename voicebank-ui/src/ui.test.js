import { versCsv, nomFichier } from "./ui";

test("CSV compatible Excel : BOM, point-virgule, décimales et guillemets", () => {
  const csv = versCsv(["ville", "montant", "note"], [
    { ville: "Douala", montant: 1234.5, note: 'dit "urgent"; à voir' },
    { ville: "Yaoundé", montant: null, note: "" },
  ]);
  expect(csv.charCodeAt(0)).toBe(0xfeff);
  expect(csv.slice(1).split("\r\n")).toEqual([
    "ville;montant;note", 'Douala;1234,5;"dit ""urgent""; à voir"', "Yaoundé;;",
  ]);
  expect(nomFichier("Crédits en défaut à Douala ?", "csv")).toMatch(/^voicebank_credits-en-defaut-a-douala_\d{4}-\d{2}-\d{2}\.csv$/);
});

test("monnaie : conversions et affichage", () => {
  const { fabriquerOutils } = require("./devise");
  const liste = [{ code: "XAF", libelle: "FCFA", nom: "", decimales: 0, taux_par_fcfa: 1 },
                 { code: "EUR", libelle: "€", nom: "", decimales: 2, taux_par_fcfa: 1 / 655.957 }];
  const eur = fabriquerOutils(liste, "EUR");
  expect(eur.formater(655957).replace(/\s/g, " ")).toBe("1 000 €");
  expect(eur.formater(6559570000, { compact: true }).replace(/\s/g, " ")).toBe("10 M €");
  expect(Math.round(eur.versFcfa(10))).toBe(6560);
  const xaf = fabriquerOutils(liste, "XAF");
  expect(xaf.formater(2000).replace(/\s/g, " ")).toBe("2 000 FCFA");
  const { libelleColonne } = require("./devise");
  expect(libelleColonne("montant_fcfa", { devise: "EUR", colonnes_monetaires: ["montant_fcfa"] })).toBe("montant (€)");
  expect(libelleColonne("nb_clients", { devise: "EUR", colonnes_monetaires: ["montant_fcfa"] })).toBe("nb_clients");
});

test("export CSV : une formule venant des données n'est jamais exécutée par Excel", () => {
  const csv = versCsv(["nom", "montant"], [
    { nom: "=HYPERLINK(\"http://pirate.cm\",\"clic\")", montant: -1500 },
    { nom: "+33 6 12", montant: 2 }, { nom: "@SUM(A1)", montant: 3 }, { nom: "Normal", montant: 4 }]);
  const lignes = csv.split("\r\n");
  expect(lignes[1].startsWith("\"'=HYPERLINK")).toBe(true);
  expect(lignes[1].endsWith(";-1500")).toBe(true);          // un vrai nombre négatif reste un nombre
  expect(lignes[2]).toBe("'+33 6 12;2");
  expect(lignes[3]).toBe("'@SUM(A1);3");
  expect(lignes[4]).toBe("Normal;4");
});
