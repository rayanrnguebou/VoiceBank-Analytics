import { render, screen } from '@testing-library/react';
import App from './App';

test("affiche l'écran de connexion sans session", () => {
  sessionStorage.clear();
  render(<App />);
  expect(screen.getByText(/Accès réservé/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /Se connecter/i })).toBeInTheDocument();
});
