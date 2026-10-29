// Génère public/referentiel/villes/<ISO>.json et public/referentiel/banques/<ISO>.json
//
// Sources (libres) :
//  - villes : GeoNames (CC BY 4.0, https://www.geonames.org) via le paquet npm « all-the-cities » (MIT) :
//    toutes les localités de 1 000 habitants ou plus, triées par population, quartiers exclus ;
//    noms français pour les grandes villes (Bruxelles, Londres, Le Caire…), le nom d'origine reste cherchable.
//  - banques : registre SWIFT/BIC public (github.com/PeterNotenboom/SwiftCodes, MIT) : établissements bancaires
//    seulement, noms remis en forme ; sigle déduit pour la recherche (BICEC, CBAO, SGBS…).
//    Afrique : liste vérifiée pays par pays (outils/banques_afrique.txt, d'après Wikipédia) en priorité, le registre
//    SWIFT n'apportant que les banques centrales et de développement absentes (il contient des banques disparues).
//
// Utilisation (dans un dossier de travail) :
//   npm i all-the-cities@3 pbf@3
//   for c in CM SN ...; do curl -sO https://raw.githubusercontent.com/PeterNotenboom/SwiftCodes/master/AllCountries/$c.json; done
//   node voicebank-ui/outils/generer_referentiel.mjs <dossier node_modules/all-the-cities> <dossier swift> <dossier public>
import fs from "fs";
import path from "path";
import { createRequire } from "module";
import { PAYS } from "../src/listes.js";

const [dossierVilles, dossierSwift, dossierPublic] = process.argv.slice(2);
const require = createRequire(path.resolve(dossierVilles) + "/");
const villes = require(path.resolve(dossierVilles, "index.js"));

// ── Noms français des grandes villes (nom GeoNames → nom français) ──────────────
const FRANCAIS = {
  DZ: { Algiers: "Alger" }, EG: { Cairo: "Le Caire", Alexandria: "Alexandrie", Giza: "Gizeh", Luxor: "Louxor", "Port Said": "Port-Saïd", Aswan: "Assouan", "Asyūţ": "Assiout", Ismailia: "Ismaïlia" },
  MA: { Marrakesh: "Marrakech", Tangier: "Tanger", Sale: "Salé", Kenitra: "Kénitra", "Oujda-Angad": "Oujda", "Fes": "Fès", Meknes: "Meknès", Tetouan: "Tétouan", Essaouira: "Essaouira" },
  LY: { Benghazi: "Benghazi", "Mişrātah": "Misrata" }, ZA: { "Cape Town": "Le Cap" }, ET: { "Addis Ababa": "Addis-Abeba" },
  TD: { "N'Djamena": "N'Djaména", Kelo: "Kélo" }, MU: { "Port Louis": "Port-Louis" }, CV: { Praia: "Praia" },
  CM: { Limbe: "Limbé", Ngaoundere: "Ngaoundéré", Edea: "Edéa", Ebolowa: "Ebolowa" },
  BE: { Brussels: "Bruxelles", Antwerpen: "Anvers", Gent: "Gand", Brugge: "Bruges", Leuven: "Louvain", Mechelen: "Malines", Kortrijk: "Courtrai", Aalst: "Alost", Oostende: "Ostende", "Sint-Niklaas": "Saint-Nicolas", Ieper: "Ypres", Tongeren: "Tongres" },
  DE: { Hamburg: "Hambourg", "Köln": "Cologne", "Frankfurt am Main": "Francfort", Hannover: "Hanovre", Bremen: "Brême", "Nürnberg": "Nuremberg", Dresden: "Dresde", Aachen: "Aix-la-Chapelle", Mainz: "Mayence", Trier: "Trèves", Koblenz: "Coblence", Braunschweig: "Brunswick", "Saarbrücken": "Sarrebruck", "Freiburg": "Fribourg-en-Brisgau", "Regensburg": "Ratisbonne", "Augsburg": "Augsbourg", "Lübeck": "Lübeck" },
  GB: { London: "Londres", Edinburgh: "Édimbourg", Dover: "Douvres", Canterbury: "Cantorbéry" },
  IT: { Genoa: "Gênes", Venice: "Venise", Padova: "Padoue", Bologna: "Bologne", Palermo: "Palerme", Verona: "Vérone", Parma: "Parme", Pisa: "Pise", Siena: "Sienne", Messina: "Messine", Catania: "Catane", Livorno: "Livourne", Bergamo: "Bergame", Mantova: "Mantoue", Syracuse: "Syracuse", Torino: "Turin", Milano: "Milan", Napoli: "Naples", Firenze: "Florence" },
  ES: { Barcelona: "Barcelone", Valencia: "Valence", Sevilla: "Séville", Zaragoza: "Saragosse", "Córdoba": "Cordoue", Granada: "Grenade", Murcia: "Murcie", Salamanca: "Salamanque", Toledo: "Tolède", Pamplona: "Pampelune", "Donostia / San Sebastián": "Saint-Sébastien", "A Coruña": "La Corogne", Tarragona: "Tarragone", "Cádiz": "Cadix", "Málaga": "Malaga" },
  PT: { Lisbon: "Lisbonne" }, NL: { "The Hague": "La Haye", Nijmegen: "Nimègue", Leiden: "Leyde", Groningen: "Groningue", "Almere Stad": "Almere" },
  CH: { "Zürich": "Zurich", Basel: "Bâle", Bern: "Berne", Luzern: "Lucerne", "Sankt Gallen": "Saint-Gall", "Biel/Bienne": "Bienne", Schaffhausen: "Schaffhouse", Solothurn: "Soleure", Chur: "Coire" },
  AT: { Vienna: "Vienne", Salzburg: "Salzbourg", "Klagenfurt am Wörthersee": "Klagenfurt" },
  PL: { Warsaw: "Varsovie", "Kraków": "Cracovie" }, RO: { Bucharest: "Bucarest" }, CZ: { Pilsen: "Plzeň" },
  GR: { Athens: "Athènes", "Thessaloníki": "Thessalonique", Piraeus: "Le Pirée", "Irákleion": "Héraklion", "Pátra": "Patras", "Lárisa": "Larissa" },
  RU: { Moscow: "Moscou", "Saint Petersburg": "Saint-Pétersbourg" }, UA: { Kyiv: "Kiev" }, DK: { Copenhagen: "Copenhague" },
  CY: { Nicosia: "Nicosie" }, MD: { Chisinau: "Chișinău" }, IE: { Luimneach: "Limerick", Gaillimh: "Galway" },
  BY: { "Homyel'": "Gomel", Mahilyow: "Moguilev", Hrodna: "Grodno" }, LT: { Vilnius: "Vilnius" },
  US: { "New York City": "New York", Philadelphia: "Philadelphie", "New Orleans": "La Nouvelle-Orléans" },
  CA: { "Québec": "Québec", "Montreal": "Montréal" }, TN: {}, SN: {},
};

const normaliser = t => String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// Villes déjà connues de l'application (listes.js) : gardées et prioritaires
import { VILLES } from "../src/listes.js";

const parPays = {};
for (const v of villes) {
  if (v.featureCode === "PPLX" || v.featureCode === "PPLH") continue;     // quartier ou lieu disparu
  if (/\((Kreis|kerület)|^Sector \d|kerület$/.test(v.name)) continue;
  (parPays[v.country] ||= []).push(v);
}

fs.mkdirSync(path.join(dossierPublic, "referentiel/villes"), { recursive: true });
fs.mkdirSync(path.join(dossierPublic, "referentiel/banques"), { recursive: true });

// ── Banques ─────────────────────────────────────────────────────────────────────
const MOTS_BANQUE = /\b(BANKING|BANCA\w*|CREDICOOP|BANK|BANKA|BANKEN|BANKI|BANQUE|BANQUES|BANCA|BANCO|BANC|BANCAIRE|BANCARIA|BANKHAUS|SPARKASSE|SPARBANK|SPAREBANK|SPARBANKEN|VOLKSBANK|RAIFFEISEN\w*|CAJA|CAIXA|CASSA|CAISSE|EPARGNE|SAVINGS|BUILDING SOCIETY|CREDIT UNION|MICROFINANCE|KREDITBANK|CREDITO|CREDIT (AGRICOLE|MUTUEL|DU|DE|LYONNAIS|COOPERATIF|FONCIER|MUNICIPAL|IMMOBILIER|SUISSE|COMMUNAUTAIRE|INDUSTRIEL|AND COMMERCE|INTERNATIONAL|POPULAIRE|MARITIME))\b|\w+BANK\b|\w+BANCO\b|\w+BANKEN\b|\w+KASSE\b|\w+BANQUE\b/;
const MARQUES = /\b(SOCIETE GENERALE|HSBC|BNP PARIBAS|PARIBAS|ABN AMRO|NATIXIS|BOURSORAMA|LCL|SCB CAMEROUN|BC PME|CIH|ATTIJARIWAFA|ING|KBC|BELFIUS|ARGENTA|CRELAN|NORDEA|DANSKE|UNICREDIT|INTESA SANPAOLO|SANTANDER|BBVA|SABADELL|DEXIA|UBS|JULIUS BAER|PICTET|LOMBARD ODIER|BARCLAYS|LLOYDS|NATWEST|MONZO|REVOLUT|N26|QONTO|BRED|CIC|BPCE|AXA BANQUE|HELLO BANK|ORANGE BANK|SHINE|NICKEL|UBA|BSIC|BICIA|BICIM|BICIG|BICI|BCI|BNI|FNB|SBI|DBM|HFC|BM MADAGASCAR|BMOI|BOA|NSIA|SGBCI|SIB|BIAO CI)\b/;
const EXCLURE = /FIXED INCOME|FUTURES|COMMUNICATIONS INTERNATIONALES|CORPORATE FINANCE|\bNOMINEES?\b|CUSTODY|TOBACCO|ASSURANCE|INSURANCE|VERSICHERUNG|ASSICURAZION|SEGUROS|BOURSE|SECURITIES|CLEARING|DEPOSITAIRE|DEPOSITORY|ASSET MANAGEMENT|GESTION\b|FUND\b|FONDS|TELECOM|AIRLINE|AIRWAYS|PETROLEUM|BRASSERIES|MINISTERE|MINISTRY|TRESOR|TREASURY|STOCK EXCHANGE|BOERSE|BÖRSE|LEASING|FACTORING|\bBROKER|\bCAPITAL MARKETS|BRANCH|NIEDERLASSUNG|PRIVATE EQUITY|BROKING|TRADING|HOLDING\b|ELECTRONICS|\bOIL\b|MOTORS|\bTRUST COMPANY|CREDIT MANAGEMENT|MARKET SERVICES|WEALTH MANAGEMENT|INVESTMENT MANAGEMENT|\bLLP\b|\bBV\b|SUCCURSALE|FILIALE|ZWEIGNIEDERLASSUNG|REPRESENTATIVE OFFICE|BUREAU DE REPRESENTATION/;
const FORMES = /[,.]?\s*\b(S\.?A\.?S?|SA|SAS|PLC|LTD|LIMITED|AG|SPA|S\.P\.A|N\.?V|SE|GMBH|EG|E\.G|KGAA|KG|AB|ASA|A\/S|AS|OYJ|SCRL|SCOP|SARL|S\.A\.R\.L|SCA|SCS|INC|CORP|PJSC|JSC|OJSC|CJSC|SC|SRL|S\.R\.L|D\.D|D\.O\.O|A\.D|PLC\.)\.?\s*$/i;
const ACCENTS = { SOCIETE: "Société", GENERALE: "Générale", GENERAL: "Général", CREDIT: "Crédit", EPARGNE: "Épargne", DEVELOPPEMENT: "Développement",
  SENEGAL: "Sénégal", SENEGALAISE: "Sénégalaise", COTE: "Côte", EQUATORIALE: "Équatoriale", REPUBLIQUE: "République", ALGERIE: "Algérie",
  ETATS: "États", ECONOMIQUE: "Économique", COOPERATIVE: "Coopérative", BENIN: "Bénin", ETRANGER: "Étranger", REGIONALE: "Régionale",
  CENTRALE: "Centrale", MUTUALISTES: "Mutualistes", REGLEMENT: "Règlement", INTERETS: "Intérêts", PRIVEE: "Privée", ISLAMIQUE: "Islamique",
  SAHELO: "Sahélo", CAMEROUNAISE: "Camerounaise", GABONAISE: "Gabonaise", TCHADIENNE: "Tchadienne", CONGOLAISE: "Congolaise",
  IVOIRIENNE: "Ivoirienne", MALIENNE: "Malienne", GUINEE: "Guinée", GUINEENNE: "Guinéenne", NIGERIENNE: "Nigérienne", ECO: "Éco",
  AGRICOLE: "Agricole", DEPOTS: "Dépôts", ETAT: "État", COMMERCIALE: "Commerciale", FEDERALE: "Fédérale", MAURITANIENNE: "Mauritanienne",
  TUNISIENNE: "Tunisienne", HOTELIER: "Hôtelier", EXTERIEUR: "Extérieur", FRANCAISE: "Française", FRANCAISES: "Françaises",
  FRANCAIS: "Français", REGIONALES: "Régionales", HELVETIQUE: "Helvétique", COMPAGNIE: "Compagnie", ANONYME: "Anonyme", MAROCAINE: "Marocaine", ALGERIENNE: "Algérienne", REUNION: "Réunion", MEDITERRANEE: "Méditerranée" };
const PETITS = new Set(["DE", "DU", "DES", "LA", "LE", "LES", "ET", "POUR", "AU", "AUX", "EN", "OF", "THE", "AND", "FOR", "DI", "DEL", "DELLA", "DA", "DO", "DOS", "Y", "VON", "UND", "FUR", "FÜR", "VOOR", "VAN", "DER", "EN", "L", "D"]);
const SIGLES = new Set(["UBA", "BOA", "BNP", "HSBC", "ING", "KBC", "BCP", "BPCE", "CIC", "LCL", "BGFI", "BICEC", "BICIS", "CBAO", "SGBS", "BIAO", "BCEAO", "BEAC", "NSIA", "BNDE", "BHS", "CNCAS", "SCB", "BC", "PME", "NFC", "CCA", "UBC", "BMCE", "BMCI", "CIH", "BMOI", "BFV", "BNI", "BDK", "BRM", "BSIC", "SIB", "ABC", "BCI", "BIM", "UBS", "BCV", "BCGE", "BCN", "ZKB", "DZ", "GLS", "KCB", "NCBA", "GTB", "BDM", "BCS", "BRS", "BTP", "ATB", "STB", "BH", "BNA", "UIB", "UBCI", "BIAT", "ABN", "AMRO", "NN", "RBS", "TSB", "BPI", "CGD", "BBVA", "BCV", "LBBW", "DKB", "NRW", "IKB", "SEB", "SNS", "BNG", "OTP", "PKO", "BPH", "BRD", "BCR", "CEC", "DSK", "UBB", "AIB", "KfW".toUpperCase()]);

const SPECIAUX = { BGFIBANK: "BGFIBank", GTBANK: "GTBank", CITIBANK: "Citibank", FIRSTBANK: "FirstBank", ORABANK: "Orabank",
  ECOBANK: "Ecobank", SONABANQUE: "Sonabanque", RABOBANK: "Rabobank", "BANKINTER": "Bankinter", ATTIJARIWAFA: "Attijariwafa" };
const FRANCAIS_MOTS = /\b(BANQUE|BANCAIRE|PRIVEE|COMPAGNIE|GROUPE|SOCIETE|CAISSE|DE|DU|DES|LA|LE|POUR|ET|AU|AUX|MUTUEL\w*|CREDIT (AGRICOLE|MUTUEL|DU|LYONNAIS|COOPERATIF|FONCIER|COMMUNAUTAIRE))\b/;

function titre(nom) {
  const francais = FRANCAIS_MOTS.test(nom.toUpperCase());
  return nom.split(/(\s+|-|\/|\(|\)|')/).map((m, i, tout) => {
    if (!/[A-Za-zÀ-ÿ]/.test(m)) return m;
    const u = m.toUpperCase();
    const apres = tout[i - 1] === "'";
    if (apres && u === "S") return "s";                                     // Karamouzi's
    if (SPECIAUX[u]) return SPECIAUX[u];
    if (i > 0 && (PETITS.has(u) || ((u === "L" || u === "D") && tout[i + 1] === "'"))) return u.toLowerCase();
    if (SIGLES.has(u.replace(/\./g, "")) || /^([A-Z]\.){2,}$/.test(u)) return u;
    if (!/[AEIOUYÀ-ÿ]/.test(u) && u.length <= 5) return u;                // sans voyelle : sigle (SGBC, CBC)
    if (francais && ACCENTS[u]) return ACCENTS[u];
    if (!francais && ACCENTS[u] && !["CREDIT", "GENERAL", "CENTRALE", "AGRICOLE", "COMMERCIALE", "ISLAMIQUE", "REGIONALE"].includes(u)) return ACCENTS[u];
    return u[0] + u.slice(1).toLowerCase();
  }).join("").replace(/^./, c => c.toUpperCase());
}

// Sigle tiré des initiales : « Banque Internationale du Cameroun pour l'Épargne et le Crédit » → BICEC
function sigle(nom) {
  const mots = nom.replace(/\(.*?\)/g, "").split(/[\s\-/]+/).map(m => m.replace(/^(l|d)'/i, ""))
    .filter(m => m && !PETITS.has(m.toUpperCase()) && /^[A-Za-zÀ-ÿ]/.test(m));
  return mots.length >= 3 ? mots.map(m => normaliser(m)[0].toUpperCase()).join("") : null;
}

const MOTS_GEO = new Set(["UK", "USA", "US", "SUISSE", "FRANCE", "LUX", "CI", "EUROPE", "ASIA", "CHINA", "INDIA", "PARIS", "LONDON", "SA", "NV", "AG"]);
const JOURNAL = process.env.JOURNAL ? [] : null;
process.on("exit", () => JOURNAL && console.error("EXCLUS :\n" + JOURNAL.join("\n")));

// ── Banques d'Afrique vérifiées (outils/banques_afrique.txt) ────────────────────
const VERIFIEES = {};
{
  let iso = null;
  for (const ligne of fs.readFileSync(new URL("./banques_afrique.txt", import.meta.url), "utf8").split("\n")) {
    const l = ligne.trim();
    if (!l || l.startsWith("# ")) continue;
    if (l.startsWith("## ")) { iso = l.slice(3).trim(); VERIFIEES[iso] ||= []; continue; }
    if (iso) VERIFIEES[iso].push(l);
  }
}
// Mots qui ne distinguent pas deux banques d'un même pays
const NEUTRES = new Set(["bank", "banque", "banco", "banca", "the", "of", "de", "du", "des", "la", "le", "et", "and", "pour", "for",
  "limited", "ltd", "plc", "sa", "group", "groupe", "international", "internationale", "s", "c", "sc", "n", "a"]);
// Même banque en anglais et en français : « African Development Bank » = « Banque Africaine de Développement »
const SYNONYMES = { african: "africaine", africain: "africaine", development: "developpement", central: "centrale", national: "nationale",
  commercial: "commerciale", islamic: "islamique", agricultural: "agricole", investment: "investissement", popular: "populaire" };
const jetons = (nom, pays) => new Set(normaliser(nom.replace(/\(.*?\)/g, " ")).replace(/[^a-z0-9]+/g, " ").split(" ")
  .map(m => SYNONYMES[m] || m).filter(m => m.length > 1 && !NEUTRES.has(m) && !pays.has(m)));
function doublon(a, b) {
  if (!a.size || !b.size) return false;
  const [petit, grand] = a.size <= b.size ? [a, b] : [b, a];
  return [...petit].every(m => grand.has(m));
}
const INSTITUTIONS = /CENTRAL|CENTRALE|RESERVE|DEVELOPMENT|DEVELOPPEMENT|DÉVELOPPEMENT|AFRICAN EXPORT-IMPORT|AFREXIM/i;
const ETRANGERES = /KOREA|CHINA|INDIA|JAPAN|KUWAIT|SAUDI|ARAB ECONOMIC|ISLAMIC DEVELOPMENT|\bOF (THE )?(UNITED STATES|AMERICA)/i;   // bureaux de représentation

function banquesVerifiees(iso, nomPays, swift) {
  const pays = new Set(normaliser(`${nomPays} ${iso}`).split(/[^a-z]+/).filter(Boolean));
  ["cameroon", "senegal", "ivoire", "nigeria", "ghana", "kenya", "gabon", "congo", "tchad", "chad", "mali", "niger", "benin", "togo",
   "burkina", "faso", "guinea", "guinee", "maroc", "morocco", "tunisie", "tunisia", "algerie", "algeria", "egypt", "madagascar", "rdc",
   "drc", "centrafrique", "uganda", "tanzania", "rwanda", "burundi", "ethiopia", "zambia", "zimbabwe", "malawi", "mozambique",
   "mocambique", "angola", "namibia", "botswana", "mauritius", "maurice", "sudan", "somalia", "liberia", "gambia", "sierra", "leone",
   "eswatini", "lesotho", "djibouti", "comores", "seychelles", "mauritanie", "libya", "cabo", "verde", "tome", "principe", "eritrea"]
    .forEach(m => pays.add(m));
  const sortie = [], cles = [];
  for (const l of VERIFIEES[iso]) {
    const s = (l.match(/\(([^()]{2,15})\)\s*$/) || [])[1];
    sortie.push(s ? `${l}|${s}` : l);
    cles.push({ j: jetons(l, pays), s: s ? normaliser(s).replace(/[^a-z0-9]/g, "") : null });
  }
  for (const b of swift) {                                    // registre SWIFT : banques centrales et de développement seulement
    const [libelle] = b.split("|");
    if (!INSTITUTIONS.test(libelle) || ETRANGERES.test(libelle)) continue;
    const j = jetons(libelle, pays), compact = normaliser(libelle).replace(/[^a-z0-9]/g, "");
    if (cles.some(c => doublon(c.j, j) || (c.s && c.s === compact))) continue;
    sortie.push(b); cles.push({ j, s: null });
  }
  return sortie.sort((a, b) => a.localeCompare(b, "fr"));
}

function banquesDe(iso) {
  const f = path.join(dossierSwift, `${iso}.json`);
  if (!fs.existsSync(f)) return [];
  const brut = JSON.parse(fs.readFileSync(f, "utf8")).list.map(x => x.bank.trim().replace(/\s+/g, " "));
  const nombreux = new Set(brut).size > 120;          // grands pays : on ne garde que ce qui est clairement une banque
  const vus = new Map();
  for (const b of brut) {
    const u = b.toUpperCase();
    if (EXCLURE.test(u)) continue;
    const sansPoints = u.replace(/\.(?=[A-Z]\.)|(?<=\b[A-Z])\./g, "");    // B.I.C.I. → BICI
    if (!MOTS_BANQUE.test(u) && !MARQUES.test(sansPoints)) { if (!nombreux && JOURNAL) JOURNAL.push(`${iso}: ${b}`); continue; }
    let propre = b.replace(/\((FORMERLY|FORMER|EX)\b[^)]*\)/gi, " ").replace(/\)\s*,.*$/, ")").replace(/\bNV\/SA\b|\bSA\//gi, " ")
      .replace(/\bSOCIETE AN\b/gi, "SOCIETE ANONYME").replace(/\b(LTD|LIMITED|PLC|N\.A)\b\.?/gi, " ").replace(/\s+/g, " ").replace(/\(\s+/g, "(").replace(/\s+\)/g, ")");
    for (let k = 0; k < 3; k++) propre = propre.replace(FORMES, "").trim();
    propre = propre.replace(/\s*\(\s*\)/g, "").replace(/[,.\s]+$/, "").trim();
    const entre = propre.match(/\(([A-Z.\s&-]{2,15})\)/);                 // sigle entre parenthèses
    const brutSigle = entre ? entre[1].replace(/[.\s]/g, "") : "";
    const sigleParenthese = brutSigle.length >= 2 && brutSigle.length <= 6 && !MOTS_GEO.has(brutSigle) ? brutSigle : null;
    const cle = normaliser(propre.replace(/\(.*?\)/g, "")).replace(/[^a-z0-9]/g, "");
    if (!cle || vus.has(cle)) continue;
    const libelle = titre(propre);
    const s = sigleParenthese || sigle(libelle);
    vus.set(cle, s && normaliser(s) !== normaliser(libelle) ? `${libelle}|${s}` : libelle);
  }
  return [...vus.values()].sort((a, b) => a.localeCompare(b, "fr"));
}

// ── Écriture ─────────────────────────────────────────────────────────────────────
let totalVilles = 0, totalBanques = 0;
const resume = [];
for (const [nomPays, , iso] of PAYS) {
  const fr = FRANCAIS[iso] || {};
  const liste = (parPays[iso] || []).sort((a, b) => b.population - a.population);
  const vus = new Map(), sortie = [];
  const ajouter = (nom, alias) => {
    const k = normaliser(nom);
    const avecAlias = alias && normaliser(alias) !== k ? `${nom}|${alias}` : nom;
    if (vus.has(k)) { if (avecAlias !== nom && !sortie[vus.get(k)].includes("|")) sortie[vus.get(k)] = avecAlias; return; }
    vus.set(k, sortie.length);
    sortie.push(avecAlias);
  };
  for (const v of VILLES[nomPays] || []) ajouter(v);        // villes déjà proposées : en tête
  for (const v of liste) ajouter(fr[v.name] || v.name, fr[v.name] ? v.name : null);
  if (sortie.length) fs.writeFileSync(path.join(dossierPublic, `referentiel/villes/${iso}.json`), JSON.stringify(sortie));
  const banques = VERIFIEES[iso] ? banquesVerifiees(iso, nomPays, banquesDe(iso)) : banquesDe(iso);
  if (banques.length) fs.writeFileSync(path.join(dossierPublic, `referentiel/banques/${iso}.json`), JSON.stringify(banques));
  totalVilles += sortie.length; totalBanques += banques.length;
  resume.push(`${iso} ${sortie.length}/${banques.length}`);
}
console.log(resume.join("  "));
console.log(`Total : ${totalVilles} villes, ${totalBanques} banques`);
