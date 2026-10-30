// Approbation sur le téléphone : l'ordinateur attend le bon nombre ; le téléphone le choisit.
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { AttenteApprobation, EcranApprobation } from "./panneaux/Approbation";

const appels = [];
let reponses = {};

vi.mock("./api", async (original) => {
  const reel = await original();
  return { ...reel, appliquerJeton: d => ({ token: d.access_token }), http: {
    get: async url => ({ data: reponses[`get ${url}`] }),
    post: async (url, corps) => {
      appels.push(`${url} ${JSON.stringify(corps)}`);
      const r = reponses[`post ${url}`];
      return { data: typeof r === "function" ? r() : r };
    },
  } };
});

beforeEach(() => { appels.length = 0; reponses = {}; localStorage.clear(); });
afterEach(() => vi.useRealTimers());

test("l'ordinateur affiche le nombre puis se connecte quand le téléphone a approuvé", async () => {
  vi.useFakeTimers();
  let tours = 0;
  reponses = {
    "post /auth/2fa/approbation/demander": { id: "demande-1234", nombre: 47, expire_dans_s: 120 },
    "post /auth/2fa/approbation/etat": () => (++tours < 2 ? { statut: "attente" } : { access_token: "session" }),
  };
  const onConnecte = vi.fn();
  render(<AttenteApprobation etape={{ jeton: "j2fa" }} onConnecte={onConnecte} onCode={() => {}} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(10); });
  expect(screen.getByLabelText("Nombre à choisir : 47")).toHaveTextContent("47");
  await act(async () => { await vi.advanceTimersByTimeAsync(4100); });
  expect(onConnecte).toHaveBeenCalledWith({ token: "session" });
});

test("mauvais nombre : refus expliqué, renvoi possible, et repli sur le code", async () => {
  vi.useFakeTimers();
  reponses = {
    "post /auth/2fa/approbation/demander": { id: "demande-1234", nombre: 47 },
    "post /auth/2fa/approbation/etat": { statut: "mauvais_nombre" },
  };
  const onCode = vi.fn();
  render(<AttenteApprobation etape={{ jeton: "j2fa" }} onConnecte={() => {}} onCode={onCode} />);
  await act(async () => { await vi.advanceTimersByTimeAsync(10); });
  await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
  expect(screen.getByRole("alert")).toHaveTextContent("Mauvais nombre");
  expect(screen.getByRole("button", { name: "Renvoyer la notification" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Utiliser plutôt le code à 6 chiffres" }));
  expect(onCode).toHaveBeenCalled();
});

test("le téléphone non enregistré ne peut rien approuver", () => {
  render(<EcranApprobation idDemande="demande-1234" onFermer={() => {}} />);
  expect(screen.getByRole("alert")).toHaveTextContent("n'est pas enregistré");
});

test("le téléphone montre la demande, trois nombres et « Ce n'était pas moi »", async () => {
  localStorage.setItem("voicebank_approbation_secret", "s".repeat(43));
  reponses = {
    "post /approbation/demande-1234": { compte: "rayan", navigateur: "Chrome · Windows", adresse_ip: "41.202.1.1",
      date: "2026-10-30T13:40:00", choix: [12, 47, 83], statut: "attente" },
    "post /approbation/demande-1234/repondre": { statut: "approuvee" },
  };
  render(<EcranApprobation idDemande="demande-1234" onFermer={() => {}} />);
  expect(await screen.findByText("Chrome · Windows")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Ce n'était pas moi" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "47" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Connexion approuvée"));
  expect(appels.at(-1)).toBe(`/approbation/demande-1234/repondre {"secret":"${"s".repeat(43)}","nombre":47}`);
});
