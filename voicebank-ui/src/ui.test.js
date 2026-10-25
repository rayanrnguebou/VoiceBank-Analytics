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
