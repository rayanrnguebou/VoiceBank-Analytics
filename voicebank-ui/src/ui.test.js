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
