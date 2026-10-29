// Sécurité de mon compte : appareils (déconnexion à distance) et données personnelles (export, effacement).
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SectionAppareils } from "./panneaux/Appareils";
import { SectionMesDonnees } from "./panneaux/MesDonnees";

const appels = [];
let reponses = {};

vi.mock("./api", async (original) => {
  const reel = await original();
  const http = Object.assign(
    async config => { appels.push(`${config.method} ${config.url}`); return { data: reponses[`${config.method} ${config.url}`] ?? { status: "ok" } }; },
    { get: async url => { appels.push(`get ${url}`); return { data: reponses[`get ${url}`] }; } });
  return { ...reel, http, appliquerJeton: d => ({ token: d.access_token }) };
});

beforeEach(() => { appels.length = 0; reponses = {}; });

const SESSIONS = {
  "get /moi/sessions": { data: [
    { id: "courante-1234", appareil: "Chrome · Windows", adresse_ip: "41.202.1.1", derniere_activite: "2026-10-29T22:00:00", active: true, courante: true },
    { id: "telephone-5678", appareil: "Safari · iPhone", adresse_ip: "41.202.9.9", derniere_activite: "2026-10-29T21:00:00", active: true, courante: false },
    { id: "ancienne-9999", appareil: "Firefox · Linux", adresse_ip: null, derniere_activite: "2026-10-20T08:00:00", active: false, courante: false },
  ] },
};

test("mes appareils : cet appareil signalé, un autre déconnecté à distance", async () => {
  reponses = SESSIONS;
  render(<SectionAppareils />);
  expect(await screen.findByText("Safari · iPhone")).toBeInTheDocument();
  expect(screen.getByText("cet appareil")).toBeInTheDocument();
  expect(screen.getByText(/terminée/)).toBeInTheDocument();
  // Un seul bouton « Déconnecter » : pas sur cet appareil ni sur une session terminée
  const boutons = screen.getAllByRole("button", { name: "Déconnecter" });
  expect(boutons).toHaveLength(1);
  fireEvent.click(boutons[0]);
  await waitFor(() => expect(appels).toContain("post /moi/sessions/telephone-5678/deconnecter"));
  expect(await screen.findByText("Safari · iPhone est déconnecté.")).toBeInTheDocument();
});

test("déconnecter les autres appareils : confirmation, puis nouveau jeton pour cet appareil", async () => {
  reponses = { ...SESSIONS, "post /moi/sessions/deconnecter-autres": { access_token: "nouveau", deconnectees: 1 } };
  const onSession = vi.fn();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<SectionAppareils onSession={onSession} />);
  fireEvent.click(await screen.findByRole("button", { name: "Déconnecter les autres appareils" }));
  await waitFor(() => expect(onSession).toHaveBeenCalledWith({ token: "nouveau" }));
});

test("mes données : effacement impossible expliqué", async () => {
  reponses = { "get /moi/effacement": { possible: false, raison: "Vous êtes le seul administrateur de votre organisation.", conservation: {} } };
  render(<SectionMesDonnees />);
  expect(await screen.findByText(/seul administrateur/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Supprimer mon compte" })).toBeNull();
  expect(screen.getByRole("button", { name: "Télécharger mes données" })).toBeInTheDocument();
});

test("supprimer mon compte : bouton actif seulement après avoir tapé SUPPRIMER", async () => {
  reponses = { "get /moi/effacement": { possible: true, conservation: { paiements: "10 ans", journal_audit: "5 ans" } } };
  render(<SectionMesDonnees />);
  fireEvent.click(await screen.findByRole("button", { name: "Supprimer mon compte" }));
  expect(screen.getByText(/paiements et facturation \(10 ans\)/)).toBeInTheDocument();
  const confirmer = screen.getByRole("button", { name: "Effacer définitivement" });
  fireEvent.change(screen.getByLabelText("Mot de passe"), { target: { value: "Baobab-Douala-2026" } });
  expect(confirmer).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Tape SUPPRIMER pour confirmer"), { target: { value: "supprimer" } });
  expect(confirmer).toBeEnabled();
  const deconnexion = vi.fn();
  window.addEventListener("voicebank:deconnexion", deconnexion);
  fireEvent.click(confirmer);
  await waitFor(() => expect(appels).toContain("post /moi/supprimer"));
  await waitFor(() => expect(deconnexion).toHaveBeenCalled());
});
