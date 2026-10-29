import { useState } from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import ChampListe, { filtrer, Choix } from "./ChampListe";
import { NOMS_PAYS, indicatif } from "./listes";

const opts = l => l.map(x => ({ valeur: x, libelle: x }));

function Banc({ depart = "", ...props }) {
  const [v, setV] = useState(depart);
  return <><label>Pays<ChampListe valeur={v} onChange={setV} {...props} /></label><output data-testid="v">{v}</output></>;
}

test("filtre sans tenir compte des accents ni des majuscules, début de nom en premier", () => {
  const r = filtrer(opts(["Bénin", "Cameroun", "Guinée-Bissau", "Bissau test"]), "bis");
  expect(r.map(o => o.valeur)).toEqual(["Bissau test", "Guinée-Bissau"]);
  expect(filtrer(opts(["Côte d'Ivoire", "Congo"]), "cote").map(o => o.valeur)).toEqual(["Côte d'Ivoire"]);
  expect(filtrer(opts(NOMS_PAYS), "came")[0].valeur).toBe("Cameroun");
  expect(indicatif("France")).toBe("33");
});

test("taper quelques lettres puis Entrée choisit la première suggestion", () => {
  render(<Banc options={NOMS_PAYS} />);
  const champ = screen.getByRole("combobox");
  fireEvent.focus(champ);
  fireEvent.change(champ, { target: { value: "sén" } });
  expect(screen.getByRole("option", { name: "Sénégal" })).toBeInTheDocument();
  fireEvent.keyDown(champ, { key: "Enter" });
  expect(screen.getByTestId("v")).toHaveTextContent("Sénégal");
  expect(champ).toHaveValue("Sénégal");
});

test("flèches et clic ; une saisie hors liste est refusée, sauf en saisie libre", () => {
  const { unmount } = render(<Banc depart="Gabon" options={["Gabon", "Gambie", "Ghana"]} />);
  const champ = screen.getByRole("combobox");
  fireEvent.focus(champ);
  fireEvent.change(champ, { target: { value: "ga" } });
  fireEvent.keyDown(champ, { key: "ArrowDown" });
  fireEvent.keyDown(champ, { key: "Enter" });
  expect(screen.getByTestId("v")).toHaveTextContent("Gambie");
  fireEvent.change(champ, { target: { value: "zzz" } });
  expect(screen.getByText("Aucun résultat")).toBeInTheDocument();
  fireEvent.blur(champ);
  expect(champ).toHaveValue("Gambie");          // retour à la dernière valeur valide
  unmount();

  render(<Banc options={["Douala", "Yaoundé"]} libre />);
  const ville = screen.getByRole("combobox");
  fireEvent.focus(ville);
  fireEvent.change(ville, { target: { value: "Nkongsamba" } });
  fireEvent.mouseDown(screen.getByRole("option", { name: /Utiliser « Nkongsamba »/ }));
  expect(screen.getByTestId("v")).toHaveTextContent("Nkongsamba");
});

test("Choix : menu classique pour une liste courte, recherche pour une longue", () => {
  const { rerender } = render(<Choix valeur="Non" onChange={() => {}} options={["Non", "Oui"]} />);
  expect(screen.getByRole("combobox").tagName).toBe("SELECT");
  rerender(<Choix valeur="Douala" onChange={() => {}} options={["Douala", "Yaoundé", "Garoua", "Kribi", "Buea", "Limbé", "Bafoussam"]} />);
  expect(screen.getByRole("combobox").tagName).toBe("INPUT");
});

test("référentiel : l'autre nom ou le sigle sert à la recherche, pas à l'affichage", () => {
  const { versOptions } = require("./referentiel");
  const villes = versOptions(["Paris", "Londres|London", "Bruxelles|Brussels"]);
  expect(villes[1]).toEqual({ valeur: "Londres", libelle: "Londres", alias: "London" });
  expect(filtrer(villes, "lond").map(o => o.valeur)).toEqual(["Londres"]);
  expect(filtrer(villes, "brus").map(o => o.valeur)).toEqual(["Bruxelles"]);
  const banques = versOptions(["Afriland First Bank", "Banque Internationale du Cameroun pour l'Épargne et le Crédit (BICEC)|BICEC"]);
  expect(filtrer(banques, "bicec")[0].valeur).toMatch(/^Banque Internationale du Cameroun/);
  expect(filtrer(banques, "first").map(o => o.valeur)).toEqual(["Afriland First Bank"]);
});
