// Champ à suggestions : on tape quelques lettres, la liste se filtre (sans tenir compte des accents ni des
// majuscules) ; flèches + Entrée, ou clic, pour choisir. « libre » accepte aussi une valeur hors liste.
import { useState, useEffect, useRef, useId, useMemo } from "react";
import { ChevronDown, ChevronUp, Check } from "lucide-react";
import { champ } from "./ui";

export const normaliser = t => String(t ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

// Les valeurs qui commencent par la saisie d'abord, puis celles dont un mot commence par elle, puis le reste
export function filtrer(options, saisie) {
  const s = normaliser(saisie);
  if (!s) return options;
  const debut = [], mot = [], dedans = [];
  for (const o of options) {
    const n = normaliser(o.libelle);
    if (n.startsWith(s)) debut.push(o);
    else if (n.split(/[\s\-'’(]+/).some(m => m.startsWith(s))) mot.push(o);
    else if (n.includes(s)) dedans.push(o);
  }
  return debut.length || mot.length ? [...debut, ...mot] : dedans;   // milieu de mot seulement à défaut de mieux
}

export default function ChampListe({ valeur, onChange, options, dark, libre = false, placeholder, required = false,
                                     maxLength = 120, id, nom, max = 50, className = "", ...props }) {
  const opts = useMemo(() => (options || []).map(o => (typeof o === "string" ? { valeur: o, libelle: o } : o)), [options]);
  const libelleDe = v => (opts.find(o => o.valeur === v)?.libelle ?? (v || ""));
  const [texte, setTexte] = useState(libelleDe(valeur));
  const [ouvert, setOuvert] = useState(false);
  const [actif, setActif] = useState(0);
  const [tape, setTape] = useState(false);       // tant qu'on n'a rien tapé, toute la liste reste visible
  const liste = useRef(null);
  const auto = useId();
  const idListe = `${id || auto}-liste`;

  useEffect(() => { setTexte(libelleDe(valeur)); }, [valeur, opts]); // eslint-disable-line react-hooks/exhaustive-deps

  const resultats = (tape ? filtrer(opts, texte) : opts).slice(0, max);

  const choisir = o => {
    setTexte(o.libelle); setOuvert(false); setTape(false);
    if (o.valeur !== valeur) onChange(o.valeur);
  };

  const valider = () => {        // à la sortie du champ
    setOuvert(false); setTape(false);
    if (!tape) return;
    const exact = opts.find(o => normaliser(o.libelle) === normaliser(texte));
    if (exact) return choisir(exact);
    if (libre) { if (texte.trim() !== (valeur || "")) onChange(texte.trim()); return; }
    const r = filtrer(opts, texte);
    if (texte.trim() && r.length === 1) return choisir(r[0]);
    if (!texte.trim() && !required) { onChange(""); return; }
    setTexte(libelleDe(valeur));   // saisie qui ne correspond à rien : on revient à la dernière valeur valide
  };

  useEffect(() => {
    const el = liste.current?.children[actif];
    if (el?.scrollIntoView) el.scrollIntoView({ block: "nearest" });
  }, [actif]);

  const clavier = e => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!ouvert) { setOuvert(true); return; }
      const n = resultats.length + (proposerLibre ? 1 : 0);
      if (n) setActif(a => (a + (e.key === "ArrowDown" ? 1 : n - 1)) % n);
    } else if (e.key === "Enter" && ouvert) {
      e.preventDefault();
      if (resultats[actif]) choisir(resultats[actif]);
      else valider();
    } else if (e.key === "Escape" && ouvert) {
      e.preventDefault(); setOuvert(false); setTape(false); setTexte(libelleDe(valeur));
    } else if (e.key === "Tab" && ouvert && tape && resultats.length && !libre) {
      choisir(resultats[actif] || resultats[0]);
    }
  };

  // « Utiliser … » seulement quand aucune valeur connue ne commence par la saisie
  const proposerLibre = libre && tape && texte.trim() && !opts.some(o => normaliser(o.libelle).startsWith(normaliser(texte)));

  return (
    <div className={`relative ${className}`}>
      <input
        id={id} name={nom} role="combobox" aria-expanded={ouvert} aria-controls={idListe} aria-autocomplete="list"
        aria-activedescendant={ouvert && resultats[actif] ? `${idListe}-${actif}` : undefined}
        autoComplete="off" value={texte} placeholder={placeholder} required={required} maxLength={maxLength}
        onChange={e => { setTexte(e.target.value); setTape(true); setOuvert(true); setActif(0); }}
        onFocus={e => { e.target.select(); setOuvert(true); setActif(Math.max(0, opts.findIndex(o => o.valeur === valeur))); }}
        onClick={() => setOuvert(true)}
        onBlur={valider} onKeyDown={clavier}
        className={`${champ(dark)} pr-8`} {...props}
      />
      {(ouvert ? <ChevronUp size={15} aria-hidden="true" className={`absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none ${dark ? "text-gray-400" : "text-gray-500"}`} />
        : <ChevronDown size={15} aria-hidden="true" className={`absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none ${dark ? "text-gray-400" : "text-gray-500"}`} />)}
      {ouvert && (resultats.length > 0 || proposerLibre || tape) && (
        <ul ref={liste} onMouseDown={e => e.preventDefault()} id={idListe} role="listbox"
          className={`absolute z-30 mt-1 w-full max-h-60 overflow-auto rounded-xl border shadow-lg py-1 text-sm ${
            dark ? "bg-gray-800 border-gray-600 text-gray-100" : "bg-white border-gray-200 text-gray-900"}`}>
          {resultats.map((o, i) => (
            <li key={o.valeur} id={`${idListe}-${i}`} role="option" aria-label={o.libelle} aria-selected={o.valeur === valeur}
              onMouseDown={e => { e.preventDefault(); choisir(o); }} onClick={e => e.preventDefault()} onMouseEnter={() => setActif(i)}
              className={`px-3 py-1.5 cursor-pointer flex items-center justify-between gap-2 ${
                i === actif ? (dark ? "bg-gray-700" : "bg-foret-50") : ""}`}>
              <span className="truncate"><Surligne texte={o.libelle} saisie={tape ? texte : ""} /></span>
              {o.valeur === valeur && <Check size={14} className="text-foret-500 flex-shrink-0" />}
            </li>
          ))}
          {proposerLibre && (
            <li role="option" aria-selected={false} id={`${idListe}-${resultats.length}`}
              onMouseDown={e => { e.preventDefault(); setOuvert(false); setTape(false); onChange(texte.trim()); }} onClick={e => e.preventDefault()}
              className={`px-3 py-1.5 cursor-pointer italic ${actif === resultats.length ? (dark ? "bg-gray-700" : "bg-foret-50") : ""} ${dark ? "text-gray-300" : "text-gray-600"}`}>
              Utiliser « {texte.trim()} »
            </li>
          )}
          {!resultats.length && !proposerLibre && (
            <li className={`px-3 py-1.5 ${dark ? "text-gray-400" : "text-gray-500"}`}>Aucun résultat</li>
          )}
        </ul>
      )}
    </div>
  );
}

// Met en gras la partie qui correspond à la saisie
function Surligne({ texte, saisie }) {
  const s = normaliser(saisie);
  if (!s) return texte;
  const i = normaliser(texte).indexOf(s);     // NFD + suppression des accents garde la même longueur pour le français
  if (i < 0 || normaliser(texte).length !== texte.length) return texte;
  return <>{texte.slice(0, i)}<strong className="font-semibold">{texte.slice(i, i + s.length)}</strong>{texte.slice(i + s.length)}</>;
}

// Choix dans une liste : menu classique quand il y a peu de valeurs (un clic suffit), recherche au-delà
export function Choix({ valeur, onChange, options, dark, seuil = 6, ...props }) {
  const opts = (options || []).map(o => (typeof o === "string" ? { valeur: o, libelle: o } : o));
  if (opts.length <= seuil) {
    return (
      <select value={valeur ?? ""} onChange={e => onChange(e.target.value)} className={champ(dark)}
        aria-label={props["aria-label"]} id={props.id} required={props.required}>
        {opts.map(o => <option key={o.valeur} value={o.valeur}>{o.libelle}</option>)}
      </select>
    );
  }
  return <ChampListe valeur={valeur} onChange={onChange} options={opts} dark={dark} placeholder="Tape les premières lettres…" {...props} />;
}
