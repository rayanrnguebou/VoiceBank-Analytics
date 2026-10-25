import { interpreterReponse } from "./conversation";

test("réponses orales : oui, non, question", () => {
  for (const t of ["Oui", "oui vas-y", "D'accord", "OK", "volontiers !", "Oui, s'il te plaît", "ouais bien sûr"]) {
    expect(interpreterReponse(t).type).toBe("oui");
  }
  for (const t of ["Non", "non merci", "Merci, c'est tout", "C'est bon", "Stop", "non pas maintenant"]) {
    expect(interpreterReponse(t).type).toBe("non");
  }
  expect(interpreterReponse("  ").type).toBe("vide");
  expect(interpreterReponse("Et à Douala ?")).toEqual({ type: "question", texte: "Et à Douala ?" });
  expect(interpreterReponse("oui, et seulement pour BICEC en 2025")).toEqual(
    { type: "question", texte: "Et seulement pour BICEC en 2025" });
  expect(interpreterReponse("crédits en défaut").texte).toBe("Crédits en défaut");
});
