// Présentation des applications : à chaque ouverture, pour tout le monde ; le bandeau des cookies vient après.
import { render, screen, fireEvent, act } from "@testing-library/react";
import { PresentationApplications, doitPresenter } from "./presentation";
import { dire, oublierVoix } from "./film";

vi.mock("./alertesErreurs", () => ({ demarrerAlertesErreurs: () => {} }));
const consentir = () => localStorage.setItem("voicebank_consentement", JSON.stringify({ version: 1, erreurs: false, date: new Date().toISOString() }));

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); });

test("visiteur sans compte : présentation affichée, fermée par « Continuer sur le site »", () => {
  consentir();
  render(<PresentationApplications />);
  expect(screen.getByRole("dialog", { name: "VoiceBank, aussi dans ta poche" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Activer le son" })).toBeInTheDocument();       // le film démarre, muet
  fireEvent.click(screen.getByRole("button", { name: "Passer la vidéo" }));
  expect(screen.getByRole("heading", { name: "VoiceBank, aussi dans ta poche" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Continuer sur le site" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(doitPresenter()).toBe(true);                  // à la prochaine ouverture (ou rechargement) : de nouveau
});

test("s'affiche même si les cookies ne sont pas encore choisis, et prévient le bandeau à la fermeture", () => {
  const fermee = vi.fn();
  window.addEventListener("voicebank-presentation-fermee", fermee);
  render(<PresentationApplications />);
  fireEvent.click(screen.getByRole("button", { name: "Fermer" }));
  expect(fermee).toHaveBeenCalled();
  window.removeEventListener("voicebank-presentation-fermee", fermee);
});

test("toujours affichée, même avec un compte et une session ouverte", () => {
  sessionStorage.setItem("voicebank_jeton", JSON.stringify({ token: "x", expire: Date.now() + 3600000 }));
  render(<PresentationApplications />);
  expect(screen.getByRole("dialog", { name: "VoiceBank, aussi dans ta poche" })).toBeInTheDocument();
});

test("le film enchaîne ses scènes puis montre la carte finale ; la voix lit chaque scène quand le son est activé", async () => {
  vi.useFakeTimers();
  const lues = [];
  window.SpeechSynthesisUtterance = function (t) { this.text = t; };
  window.speechSynthesis = { getVoices: () => [], cancel: () => {}, speak: u => { lues.push(u.text); setTimeout(() => u.onend(), 100); } };
  consentir();
  render(<PresentationApplications />);
  fireEvent.click(screen.getByRole("button", { name: "Activer le son" }));
  for (let i = 0; i < 5; i++) await act(async () => { await vi.advanceTimersByTimeAsync(6000); });
  expect(screen.getByRole("heading", { name: "VoiceBank, aussi dans ta poche" })).toBeInTheDocument();
  expect(lues[0]).toMatch(/^Bienvenue sur VoiceBank/);
  expect(lues.length).toBe(6);                          // 5 scènes + la phrase de fin
  vi.useRealTimers();
  delete window.speechSynthesis; delete window.SpeechSynthesisUtterance;
});

test("voix humaine enregistrée : jouée quand elle existe, sinon synthèse vocale (et repli si le fichier ne se lit pas)", async () => {
  const lues = [], jouees = [];
  window.SpeechSynthesisUtterance = function (t) { this.text = t; };
  window.speechSynthesis = { getVoices: () => [], cancel: () => {}, speak: u => { lues.push(u.text); u.onend(); } };
  const fetchAvant = global.fetch, audioAvant = window.Audio;
  global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ fr: ["accueil", "fraude"], en: [] }) }));
  window.Audio = function (src) {
    this.src = src; this.pause = () => {};
    this.play = () => { jouees.push(src); if (src.endsWith("fraude.mp3")) return Promise.reject(new Error("bloqué")); setTimeout(() => this.onended?.(), 0); return Promise.resolve(); };
  };
  oublierVoix();
  const fini = () => new Promise(r => setTimeout(r, 10));
  const f1 = vi.fn(); dire("Bienvenue", f1, "accueil"); await fini();
  const f2 = vi.fn(); dire("Pose tes questions", f2, "voix"); await fini();
  const f3 = vi.fn(); dire("Fraude", f3, "fraude"); await fini();
  expect(jouees).toEqual(["/film/voix/fr/accueil.mp3", "/film/voix/fr/fraude.mp3"]);
  expect(lues).toEqual(["Pose tes questions", "Fraude"]);           // « voix » sans fichier ; « fraude » illisible
  expect(f1).toHaveBeenCalledTimes(1); expect(f2).toHaveBeenCalledTimes(1); expect(f3).toHaveBeenCalledTimes(1);
  global.fetch = fetchAvant; window.Audio = audioAvant; oublierVoix();
  delete window.speechSynthesis; delete window.SpeechSynthesisUtterance;
});
