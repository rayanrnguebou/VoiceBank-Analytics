// Bandeau des cookies : refus aussi simple que l'acceptation, choix mémorisé, rapports d'erreurs seulement avec accord.
import { render, screen, fireEvent, act } from "@testing-library/react";
import { BandeauCookies, lireConsentement, ouvrirGestionCookies } from "./consentement";

const demarrer = vi.fn();
vi.mock("./alertesErreurs", () => ({ demarrerAlertesErreurs: () => demarrer() }));

beforeEach(() => { localStorage.clear(); demarrer.mockClear(); });

test("premier passage : bandeau visible ; « Tout refuser » mémorise le refus sans démarrer Sentry", () => {
  render(<BandeauCookies />);
  expect(screen.getByRole("dialog", { name: "Ta vie privée, tes choix" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Tout refuser" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(lireConsentement().erreurs).toBe(false);
  expect(demarrer).not.toHaveBeenCalled();
});

test("« Tout accepter » démarre les rapports d'erreurs ; le bandeau ne revient pas", () => {
  const { unmount } = render(<BandeauCookies />);
  fireEvent.click(screen.getByRole("button", { name: "Tout accepter" }));
  expect(lireConsentement().erreurs).toBe(true);
  expect(demarrer).toHaveBeenCalledTimes(1);
  unmount();
  render(<BandeauCookies />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("« Gérer les cookies » rouvre le détail et permet de retirer son accord", () => {
  localStorage.setItem("voicebank_consentement", JSON.stringify({ version: 1, erreurs: true, date: new Date().toISOString() }));
  render(<BandeauCookies />);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  act(() => ouvrirGestionCookies());
  expect(screen.getByText("Strictement nécessaires")).toBeInTheDocument();
  const interrupteur = screen.getByRole("switch", { name: "Rapports d'erreurs anonymes" });
  expect(interrupteur).toBeChecked();
  fireEvent.click(interrupteur);
  fireEvent.click(screen.getByRole("button", { name: "Enregistrer mes choix" }));
  expect(lireConsentement().erreurs).toBe(false);
});

test("choix de plus de 6 mois : redemandé", () => {
  localStorage.setItem("voicebank_consentement", JSON.stringify({ version: 1, erreurs: false, date: "2025-01-01T00:00:00Z" }));
  render(<BandeauCookies />);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});
