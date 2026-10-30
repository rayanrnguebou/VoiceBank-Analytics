// Questions favorites : étoile sur une réponse, barre des favoris de la base choisie, envoi du lundi.
import { render, screen, fireEvent, waitFor, renderHook, act } from "@testing-library/react";
import { useFavoris, BarreFavoris, BoutonFavori } from "./panneaux/Favoris";

const appels = [];
let liste = [];

vi.mock("./api", async (original) => {
  const reel = await original();
  return { ...reel, http: {
    get: async url => { appels.push(`get ${url}`); return { data: { data: liste } }; },
    post: async (url, corps) => { appels.push(`post ${url} ${JSON.stringify(corps || {})}`); return { data: { status: "ok" } }; },
  } };
});

beforeEach(() => { appels.length = 0; liste = []; });

const FAVORIS = [
  { id: 1, question: "Top 10 clients par solde", id_source: 0, envoi_hebdo: false },
  { id: 2, question: "Crédits en défaut", id_source: 0, envoi_hebdo: true },
  { id: 3, question: "Ventes par agence", id_source: 7, envoi_hebdo: false },
];

test("l'étoile ajoute la question, puis la retire (insensible à la casse)", async () => {
  liste = [FAVORIS[0]];
  const { result } = renderHook(() => useFavoris(true));
  await waitFor(() => expect(result.current.liste).toHaveLength(1));
  expect(result.current.trouve("top 10 CLIENTS par solde ", 0)).toBeTruthy();
  expect(result.current.trouve("Top 10 clients par solde", 7)).toBeFalsy();     // autre base
  await act(() => result.current.basculer("Top 10 clients par solde", 0));
  expect(appels).toContain("post /favoris/1/supprimer {}");
  await act(() => result.current.basculer("Alertes critiques", 0, "EUR"));
  expect(appels).toContain('post /favoris {"question":"Alertes critiques","id_source":0,"devise":"EUR"}');
});

test("la barre ne montre que les favoris de la base choisie ; un clic relance la question", async () => {
  const favoris = { liste: FAVORIS, erreur: null, envoi: vi.fn(), supprimer: vi.fn() };
  const poser = vi.fn();
  render(<BarreFavoris favoris={favoris} idSource={0} onPoser={poser} />);
  expect(screen.getByText("Crédits en défaut")).toBeInTheDocument();
  expect(screen.queryByText("Ventes par agence")).toBeNull();
  fireEvent.click(screen.getByText("Top 10 clients par solde"));
  expect(poser).toHaveBeenCalledWith("Top 10 clients par solde");
  // Réglages : envoi chaque lundi
  fireEvent.click(screen.getByRole("button", { name: "Réglages du favori « Top 10 clients par solde »" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "chaque lundi par e-mail" }));
  expect(favoris.envoi).toHaveBeenCalledWith(FAVORIS[0], true);
});

test("sans favori pour cette base, rien n'est affiché ; étoile pleine si la question est gardée", () => {
  const { container } = render(<BarreFavoris favoris={{ liste: FAVORIS, erreur: null }} idSource={99} onPoser={() => {}} />);
  expect(container).toBeEmptyDOMElement();
  render(<BoutonFavori actif onClick={() => {}} />);
  expect(screen.getByRole("button", { name: "Retirer des favoris" })).toHaveAttribute("aria-pressed", "true");
});
