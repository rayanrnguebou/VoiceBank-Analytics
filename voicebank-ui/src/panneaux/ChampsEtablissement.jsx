// Pays, banque et ville d'une opération ou d'un crédit (formulaires de démonstration).
// Toutes les banques et localités du pays sont proposées ; celles que le modèle a apprises viennent en tête.
import ChampListe from "../ChampListe";
import { NOMS_PAYS } from "../listes";
import { useReferentiel } from "../referentiel";
import { etiquette } from "../ui";
import { tx } from "../i18n";

export const PAYS_MODELE = "Cameroun";      // la banque de démonstration est camerounaise

const marquer = (options, connues) => {
  const k = new Set((connues || []).map(x => x.toLowerCase()));
  return options.map(o => (k.has(o.valeur.toLowerCase()) ? { ...o, note: tx("appris par le modèle") } : o));
};

export default function ChampsEtablissement({ dark, valeurs, maj, connues = {}, avecVille = true }) {
  const pays = valeurs.pays || PAYS_MODELE;
  const local = pays === PAYS_MODELE;
  const banques = useReferentiel("banques", pays, local ? connues.banque : []);
  const villes = useReferentiel("villes", avecVille ? pays : null, local ? connues.ville : []);
  const changerPays = p => {
    if (p === pays) return;
    const auPays = p === PAYS_MODELE;
    maj({ pays: p, banque: auPays ? connues.banque?.[0] || "" : "", ...(avecVille ? { ville: auPays ? connues.ville?.[0] || "" : "" } : {}) });
  };
  return (
    <>
      <label>
        <span className={etiquette(dark)}>{tx("Pays")}</span>
        <ChampListe dark={dark} valeur={pays} onChange={changerPays} options={NOMS_PAYS} required placeholder={tx("Tape les premières lettres…")} />
      </label>
      <label>
        <span className={etiquette(dark)}>{tx("Banque")}</span>
        <ChampListe dark={dark} valeur={valeurs.banque || ""} onChange={v => maj({ banque: v })} libre required maxLength={120}
          options={marquer(banques.options, local ? connues.banque : [])} placeholder={tx("Nom ou sigle (ex. BICEC, UBA)…")} />
      </label>
      {avecVille && (
        <label>
          <span className={etiquette(dark)}>{tx("Ville")}</span>
          <ChampListe dark={dark} valeur={valeurs.ville || ""} onChange={v => maj({ ville: v })} libre required maxLength={80}
            options={marquer(villes.options, local ? connues.ville : [])} placeholder={tx("Tape les premières lettres…")} />
        </label>
      )}
    </>
  );
}
