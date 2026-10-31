// Barre latérale de navigation (fixe sur grand écran, tiroir sur mobile)
import { useEffect } from "react";
import { tx } from "../i18n";
import SelecteurLangue from "../SelecteurLangue";
import {
  AudioLines, HandCoins, TrendingUp, LayoutDashboard, ShieldAlert, ScanSearch, Landmark, History,
  GraduationCap, Target, DatabaseZap, ScrollText, ChartColumn, ExternalLink, LogOut, X, UsersRound, KeyRound, CreditCard, Wallet,
  Building2, Wrench, ClipboardCheck, BellRing } from "lucide-react";

const POWER_BI_URL = import.meta.env.REACT_APP_POWER_BI_URL || "";

export function Logo() {
  // Monogramme : une onde sonore sur fond laiton (même dessin que public/favicon.svg)
  return (
    <svg width="32" height="32" viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#C9A13B" />
      <path d="M7 13v6M11.5 9v14M16 6v20M20.5 9v14M25 13v6" stroke="#0F3D35" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

function Lien({ id, libelle, Icone, page, allerA, badge, badgeAlerte }) {
  const actif = page === id;
  return (
    <button
      onClick={() => allerA(id)}
      aria-current={actif ? "page" : undefined}
      className={`group relative w-full flex items-center gap-3 pl-4 pr-3 py-2 rounded-lg text-sm transition-colors
        focus:outline-none focus-visible:ring-2 focus-visible:ring-laiton-400 ${
        actif ? "bg-white/10 text-white font-medium" : "text-foret-100/75 hover:bg-white/5 hover:text-white"}`}
    >
      {actif && <span className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-laiton-400" aria-hidden="true" />}
      <Icone size={17} strokeWidth={1.75} className={actif ? "text-laiton-300" : "text-foret-100/60 group-hover:text-foret-100"} />
      <span className="flex-1 text-left">{libelle}</span>
      {badge > 0 && (
        <span className={`min-w-[1.5rem] px-1.5 py-0.5 rounded-full text-[11px] font-semibold tabular-nums text-center ${
          badgeAlerte ? "bg-red-500 text-white" : "bg-white/10 text-foret-100"}`}>
          {badge > 999 ? "999+" : badge}
        </span>
      )}
    </button>
  );
}

export default function BarreLaterale({ page, allerA, estAdmin, voitAdmin, externe, session, acces, nbHistorique, compteurs, ouverte, onFermer, onDeconnexion, onMotDePasse }) {
  useEffect(() => {
    if (!ouverte) return;
    const echap = e => e.key === "Escape" && onFermer();
    window.addEventListener("keydown", echap);
    return () => window.removeEventListener("keydown", echap);
  }, [ouverte, onFermer]);

  const aller = id => { allerA(id); onFermer(); };
  const props = { page, allerA: aller };

  return (
    <>
      {ouverte && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={onFermer} aria-hidden="true" />}
      <aside
        className={`fixed lg:sticky top-0 left-0 z-40 h-screen w-64 flex-shrink-0 flex flex-col bg-foret-900 text-white
          transition-transform duration-200 lg:translate-x-0 ${ouverte ? "translate-x-0" : "-translate-x-full"}`}
        aria-label={tx("Navigation principale")}
      >
        <div className="flex items-center gap-3 px-5 pt-5 pb-6">
          <Logo />
          <div className="flex-1 min-w-0">
            <p className="font-semibold leading-tight">{tx("VoiceBank")}</p>
            <p className="text-xs text-foret-100/60 leading-tight">{tx("Analytics")}</p>
          </div>
          <button onClick={onFermer} className="lg:hidden p-1.5 rounded-md hover:bg-white/10" aria-label={tx("Fermer le menu")}>
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 space-y-1">
          <Lien id="assistant" libelle={tx("Assistant vocal")} Icone={AudioLines} {...props} />
          <Lien id="tableau" libelle={tx("Tableau de bord")} Icone={LayoutDashboard} {...props} />
          <Lien id="donnees" libelle={tx("Mes données")} Icone={DatabaseZap} {...props} />

          <p className="px-4 pt-5 pb-1.5 text-xs text-foret-100/45">{tx("Risques")}</p>
          <Lien id="alertes" libelle={tx("Alertes de fraude")} Icone={ShieldAlert}
            badge={compteurs.alertes} badgeAlerte {...props} />
          <Lien id="analyse" libelle={tx("Analyse de transaction")} Icone={ScanSearch} {...props} />
          <Lien id="credit" libelle={tx("Score de crédit")} Icone={Landmark} {...props} />
          <Lien id="recouvrement" libelle={tx("Recouvrement")} Icone={HandCoins} {...props} />
          <Lien id="modeles" libelle={tx("Fiche des modèles")} Icone={ClipboardCheck} {...props} />

          <p className="px-4 pt-5 pb-1.5 text-xs text-foret-100/45">{tx("Rapports")}</p>
          <Lien id="valeur" libelle={tx("Valeur créée")} Icone={TrendingUp} {...props} />
          <Lien id="historique" libelle={tx("Historique")} Icone={History} badge={nbHistorique} {...props} />
          {!(acces?.type === "essai") && <Lien id="notifications" libelle={tx("Notifications")} Icone={BellRing} {...props} />}
          {POWER_BI_URL && (
            <a href={POWER_BI_URL} target="_blank" rel="noopener noreferrer"
              className="group w-full flex items-center gap-3 pl-4 pr-3 py-2 rounded-lg text-sm text-foret-100/75 hover:bg-white/5 hover:text-white">
              <ChartColumn size={17} strokeWidth={1.75} className="text-foret-100/60 group-hover:text-foret-100" />
              <span className="flex-1">{tx("Rapport Power BI")}</span>
              <ExternalLink size={13} className="text-foret-100/50" />
            </a>
          )}

          {externe && (
            <>
              <p className="px-4 pt-5 pb-1.5 text-xs text-foret-100/45">{acces?.organisation ? tx("Mon organisation") : tx("Mon compte")}</p>
              {acces?.organisation && (
                <Lien id="organisation" libelle={acces.type_organisation === "particulier" ? tx("Mon compte") : tx("Membres")}
                  Icone={Building2} {...props} />
              )}
              {acces?.organisation && acces.type_organisation !== "particulier" && ["admin", "auditeur"].includes(acces.role_org) && (
                <Lien id="journal" libelle={tx("Journal")} Icone={ScrollText} {...props} />
              )}
              <Lien id="abonnement" libelle={tx("Abonnement")} Icone={CreditCard} {...props} />
            </>
          )}

          {voitAdmin && (
            <>
              <p className="px-4 pt-5 pb-1.5 text-xs text-foret-100/45 flex items-center gap-2">
                {tx("Administration")}
                {!estAdmin && <span className="px-1.5 py-0.5 rounded bg-white/10 text-[10px] uppercase tracking-wide text-foret-100/70">{tx("Démo")}</span>}
              </p>
              <Lien id="apprentissage" libelle={tx("Apprentissage")} Icone={GraduationCap} badge={compteurs.signalements} {...props} />
              <Lien id="fiabilite" libelle={tx("Fiabilité")} Icone={Target} {...props} />
              <Lien id="audit" libelle={tx("Audit")} Icone={ScrollText} {...props} />
              <Lien id="comptes" libelle={tx("Comptes")} Icone={UsersRound} {...props} />
              {estAdmin && <Lien id="abonnements" libelle={tx("Abonnements")} Icone={Wallet} {...props} />}
              {estAdmin && <Lien id="maintenance" libelle={tx("Maintenance")} Icone={Wrench} {...props} />}
            </>
          )}
        </nav>

        <div className="mx-3 mt-2 flex justify-end"><SelecteurLangue /></div>
        <div className="m-3 mt-2 p-3 rounded-xl bg-white/5 flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-laiton-400 text-foret-900 flex items-center justify-center font-semibold uppercase">
            {session.utilisateur.slice(0, 1)}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{session.utilisateur}</p>
            <p className="text-xs text-foret-100/60 truncate" title={acces?.organisation || undefined}>
              {session.role === "client" && acces?.organisation
                ? `${{ admin: tx("Admin"), analyste: tx("Analyste"), lecteur: tx("Lecteur"), auditeur: tx("Auditeur") }[acces.role_org] || tx("Membre")} · ${acces.organisation}`
                : { admin: tx("Administrateur"), analyste: tx("Analyste"), visiteur: tx("Essai gratuit"), client: tx("Abonné") }[session.role] || session.role}
            </p>
          </div>
          <button onClick={() => { onMotDePasse(); onFermer(); }} aria-label={tx("Changer mon mot de passe et la double authentification")} title={tx("Sécurité du compte : mot de passe, double authentification")}
            className="p-2 rounded-lg text-foret-100/70 hover:text-white hover:bg-white/10">
            <KeyRound size={16} />
          </button>
          <button onClick={onDeconnexion} aria-label={tx("Se déconnecter")} title={tx("Se déconnecter")}
            className="p-2 rounded-lg text-foret-100/70 hover:text-white hover:bg-white/10">
            <LogOut size={16} />
          </button>
        </div>
      </aside>
    </>
  );
}
