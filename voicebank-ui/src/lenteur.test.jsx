import { render, screen, act } from "@testing-library/react";
import { http, DELAI_LENT_MS, messageErreur } from "./api";
import { IndicateurCalcul } from "./maintenance";

// Adaptateur axios factice : répond après `ms` millisecondes
const repondApres = ms => config => new Promise(ok => setTimeout(() => ok({ data: {}, status: 200, statusText: "OK", headers: {}, config }), ms));

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("une analyse longue affiche « calcul en cours », puis le message disparaît", async () => {
  render(<IndicateurCalcul />);
  const req = http.get("/sources/1/risques/operations", { adapter: repondApres(DELAI_LENT_MS + 3000) });
  await act(async () => { await vi.advanceTimersByTimeAsync(DELAI_LENT_MS - 100); });
  expect(screen.queryByText(/Calcul en cours/)).toBeNull();          // rapide : rien d'affiché
  await act(async () => { await vi.advanceTimersByTimeAsync(200); });
  expect(screen.getByRole("status")).toHaveTextContent("Calcul en cours sur le serveur");
  await act(async () => { await vi.advanceTimersByTimeAsync(3000); await req; });
  expect(screen.queryByText(/Calcul en cours/)).toBeNull();
});

test("les vérifications de fond (santé, maintenance, connexion) ne déclenchent pas le message", async () => {
  render(<IndicateurCalcul />);
  const req = http.get("/health", { silencieux: true, adapter: repondApres(DELAI_LENT_MS * 2) });
  await act(async () => { await vi.advanceTimersByTimeAsync(DELAI_LENT_MS + 500); });
  expect(screen.queryByText(/Calcul en cours/)).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(DELAI_LENT_MS); await req; });
});

test("délai dépassé : message qui rassure (le calcul continue)", () => {
  expect(messageErreur({ code: "ECONNABORTED" })).toMatch(/Le calcul continue/);
});
