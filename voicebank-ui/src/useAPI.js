// Hook d'appel à l'API avec état de chargement et message d'erreur lisible
import { useState, useCallback } from "react";
import { http, messageErreur } from "./api";

export function useAPI() {
  const [chargement, setChargement] = useState(false);
  const [erreur, setErreur]         = useState(null);

  const appeler = useCallback(async (methode, url, data = null, options = {}) => {
    setChargement(true);
    setErreur(null);
    try {
      const config = { method: methode, url, ...options };
      if (data) config.data = data;
      const res = await http(config);
      return res.data;
    } catch (e) {
      setErreur(messageErreur(e));
      return null;
    } finally {
      setChargement(false);
    }
  }, []);

  return { appeler, chargement, erreur, setErreur };
}
