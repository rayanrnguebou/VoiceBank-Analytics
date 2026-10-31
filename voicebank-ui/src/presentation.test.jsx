// Présentation des applications : à chaque ouverture tant qu'aucun compte n'a servi sur l'appareil, après les cookies.
import { render, screen, fireEvent, act } from "@testing-library/react";
import { PresentationApplications, doitPresenter } from "./presentation";
import { EVENEMENT_CHOISI } from "./consentement";

vi.mock("./alertesErreurs", () => ({ demarrerAlertesErreurs: () => {} }));
const consentir = () => localStorage.setItem("voicebank_consentement", JSON.stringify({ version: 1, erreurs: false, date: new Date().toISOString() }));

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });

test("visiteur sans compte : présentation affichée, fermée par « Continuer sur le site »", () => {
  consentir();
  render(<PresentationApplications />);
  expect(screen.getByRole("dialog", { name: "VoiceBank, aussi dans ta poche" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Continuer sur le site" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(doitPresenter()).toBe(false);                 // pas de nouveau dans le même onglet
  sessionStorage.clear();
  expect(doitPresenter()).toBe(true);                  // nouvelle ouverture : de nouveau
});

test("attend le choix des cookies avant de s'afficher", () => {
  render(<PresentationApplications />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  consentir();
  act(() => window.dispatchEvent(new Event(EVENEMENT_CHOISI)));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

test("plus jamais une fois qu'un compte s'est connecté sur l'appareil", () => {
  consentir();
  localStorage.setItem("voicebank_compte_connu", "1");
  render(<PresentationApplications />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
