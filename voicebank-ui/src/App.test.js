import { render, screen, fireEvent } from '@testing-library/react';
import App from './App';

test("accueil : choix visiteur ou organisation, puis essai ou connexion", () => {
  sessionStorage.clear();
  render(<App />);
  expect(screen.getByText(/Tu es…/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Organisation/i }));
  expect(screen.getByRole('button', { name: /Se connecter/i })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Visiteur/i }));
  expect(screen.getByRole('button', { name: /Démarrer l'essai gratuit/i })).toBeDisabled();
});
