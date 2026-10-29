// Monnaie d'affichage choisie par l'utilisateur. Les données sont stockées en FCFA (XAF) : on convertit
// à l'affichage (tarifs, indicateurs, alertes, crédits) ; les réponses aux questions arrivent déjà
// converties par l'API, qui rédige aussi le résumé parlé dans la bonne monnaie.
import { createContext, useContext, useEffect, useState, useCallback, useMemo } from "react";
import { http } from "./api";

const XAF_PAR_EUR = 655.957;
// Repli si l'API est injoignable : FCFA et euro à parité fixe, autres taux indicatifs
const PAR_DEFAUT = [
  { code: "XAF", libelle: "FCFA", nom: "Franc CFA (CEMAC)", decimales: 0, taux_par_fcfa: 1 },
  { code: "XOF", libelle: "FCFA", nom: "Franc CFA (UEMOA)", decimales: 0, taux_par_fcfa: 1 },
  { code: "EUR", libelle: "€", nom: "Euro", decimales: 2, taux_par_fcfa: 1 / XAF_PAR_EUR },
  { code: "USD", libelle: "$", nom: "Dollar américain", decimales: 2, taux_par_fcfa: 1.08 / XAF_PAR_EUR },
  { code: "GBP", libelle: "£", nom: "Livre sterling", decimales: 2, taux_par_fcfa: 0.85 / XAF_PAR_EUR },
  { code: "CAD", libelle: "$ CA", nom: "Dollar canadien", decimales: 2, taux_par_fcfa: 1.48 / XAF_PAR_EUR },
  { code: "CHF", libelle: "CHF", nom: "Franc suisse", decimales: 2, taux_par_fcfa: 0.95 / XAF_PAR_EUR },
  { code: "CNY", libelle: "¥", nom: "Yuan chinois", decimales: 2, taux_par_fcfa: 7.8 / XAF_PAR_EUR },
  { code: "NGN", libelle: "₦", nom: "Naira nigérian", decimales: 0, taux_par_fcfa: 1650 / XAF_PAR_EUR },
];
const CLE = "voicebank_devise";

const Contexte = createContext(null);

export function fabriquerOutils(liste, code) {
  const d = liste.find(x => x.code === code) || liste[0];
  const convertir = xaf => (xaf == null || isNaN(Number(xaf)) ? null : Number(xaf) * d.taux_par_fcfa);
  const nombre = (v, decimales) => Number(v).toLocaleString("fr-FR", { maximumFractionDigits: decimales, minimumFractionDigits: 0 });
  // Montant déjà exprimé dans la monnaie choisie
  const formaterValeur = (v, { compact = false } = {}) => {
    if (v == null || isNaN(Number(v))) return "--";
    const x = Number(v), a = Math.abs(x);
    if (compact && a >= 1e9) return `${nombre(x / 1e9, 1)} Mds ${d.libelle}`;
    if (compact && a >= 1e6) return `${nombre(x / 1e6, 1)} M ${d.libelle}`;
    return `${nombre(x, a >= 1000 ? 0 : d.decimales)} ${d.libelle}`;
  };
  return {
    code: d.code, libelle: d.libelle, nom: d.nom, decimales: d.decimales, fcfa: d.code === "XAF" || d.code === "XOF",
    convertir,
    versFcfa: v => (v === "" || v == null ? v : Number(v) / d.taux_par_fcfa),
    formater: (xaf, options) => formaterValeur(convertir(xaf), options),     // montant stocké en FCFA
    formaterValeur,
  };
}

export function FournisseurDevise({ children }) {
  const [liste, setListe] = useState(PAR_DEFAUT);
  const [infos, setInfos] = useState(null);
  const [code, setCodeEtat] = useState(() => {
    try { return localStorage.getItem(CLE) || "XAF"; } catch (e) { return "XAF"; }
  });
  useEffect(() => {
    http.get("/devises", { timeout: 90000 }).then(r => {
      if (r.data?.devises?.length) { setListe(r.data.devises); setInfos({ source: r.data.source, date: r.data.date }); }
    }).catch(() => {});
  }, []);
  const setCode = useCallback(c => {
    setCodeEtat(c);
    try { localStorage.setItem(CLE, c); } catch (e) { /* rien */ }
  }, []);
  const valeur = useMemo(() => ({ ...fabriquerOutils(liste, code), liste, setCode, infos }), [liste, code, setCode, infos]);
  return <Contexte.Provider value={valeur}>{children}</Contexte.Provider>;
}

export function useDevise() {
  return useContext(Contexte) || { ...fabriquerOutils(PAR_DEFAUT, "XAF"), liste: PAR_DEFAUT, setCode: () => {}, infos: null };
}

export function SelecteurDevise({ className = "", compact = false }) {
  const d = useDevise();
  return (
    <select aria-label="Monnaie" title="Monnaie d'affichage des montants" value={d.code} onChange={e => d.setCode(e.target.value)}
      className={className}>
      {d.liste.map(x => <option key={x.code} value={x.code}>{compact ? `${x.code === "XOF" ? "FCFA UEMOA" : x.code === "XAF" ? "FCFA" : x.code} ${x.code === "XAF" || x.code === "XOF" ? "" : x.libelle}`.trim() : `${x.nom} (${x.libelle})`}</option>)}
    </select>
  );
}

// Libellé d'une colonne monétaire : « montant_fcfa » affiché « montant (€) » quand la monnaie change
export function libelleColonne(nom, item) {
  if (!item?.devise || !(item.colonnes_monetaires || []).includes(nom)) return nom;
  const d = PAR_DEFAUT.find(x => x.code === item.devise);
  const base = nom.replace(/_?(fcfa|xaf)$/i, "").replace(/(^|_)(fcfa|xaf)(_|$)/i, "$1$3");
  return `${base} (${d ? d.libelle : item.devise})`;
}
