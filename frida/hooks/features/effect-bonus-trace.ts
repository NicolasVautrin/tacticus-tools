// #462-r4a-r1 — CAPTEUR du canal d'un bonus de degat d'EFFET, face ATTAQUANT vs DEFENSEUR.
//
// ── LE RESIDU QU'IL DOIT FERMER ───────────────────────────────────────────────────────────────
// `docs/rl/case-462-r4a-canal-du-multiplicateur.md` §6 : la MESURE (6 regimes, dont 2 a deux faces)
// etablit que les %-list d'effets se composent SANS arrondi intercale, donc qu'elles ne traversent
// PAS l'etage `Multiplier@0x30`. Deux lectures restaient ouvertes, aucune tranchee :
//   (a) le `damageBonus` d'un effet remplit `@0x48/@0x50` (l'entree CAPEE de la liste `@0x18`) et
//       non le canal `Multiplier` ;
//   (b) le decompile Ghidra confond deux corps distincts sous le meme symbole.
// Et la face ATTAQUANT de l'additif n'est pas observable : rien ne distingue ce que verse la
// fabrique attaquante de ce que verse son homologue defenseur.
//
// ── CE QUE LA RE A DEJA ETABLI (build `rnca9r7q6c`, relu le 2026-08-04) ───────────────────────
// `IdunBattle.Core.Services.DamageModifiers$$Add(this, damageBonus, modifier)` — la surcharge
// 2-ARGUMENTS, celle des effets — remis en C# :
//
//     if (modifier.HasValue)            Add(this, modifier.Value);        // -> Multiplier@0x30 *= v
//     if (damageBonus.@0x28.HasValue)   this.@0x10 += Fix64(v);           // ADDITIF
//     if (damageBonus.@0x30.HasValue)   this.@0x10 -= Fix64(v);           // SOUSTRACTIF
//     if (damageBonus.@0x48.HasValue) {                                   // POURCENTAGE + CAP
//         entry = { One + PctMultiplier(@0x48.Value), Fix64(@0x50.Value) };
//         this.@0x18.Add(entry);                                          // -> LISTE CAPEE
//     }
//     if (touched) this.@0x38.Add(damageBonus);                           // liste de tracabilite
//
// et `DamageModifiers$$Add(this, modifier)` — la surcharge 1-ARGUMENT — est un `Multiplier@0x30 *=
// modifier` sec. La lecture (a) est donc CORROBOREE PAR LE DECOMPILE : un pourcentage porte par le
// `damageBonus` part dans la liste capee, PAS dans `Multiplier`.
//
// ⚠ MAIS CE N'EST PAS SUFFISANT, et c'est la raison d'etre de ce capteur : le MEME `DamageBonus`
// peut alimenter les DEUX canaux selon l'APPELANT. Lu dans
// `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction`, un champ
// de pourcentage est converti par
// `IdunBattle.Core.Services.BaseCalculations$$GetFloatMultiplierFromPercentage` puis passe comme
// TROISIEME argument (`modifier`) — donc vers `Multiplier@0x30`, l'etage arrondi. Savoir « ce que
// la fabrique produit » ne dit donc RIEN sans savoir « ou l'appelant le verse ». Le capteur
// mesure les DEUX, sur le MEME evenement.
//
// ── LES QUATRE ANCRAGES (tous resolus RUNTIME, aucune RVA en dur) ─────────────────────────────
//  1. `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack`
//     — la FABRIQUE nommee par le residu. Retour `System.Nullable<IdunBattle.Entities.Effects
//     .EffectBonus>` (0x58 octets ; `EffectBonus` = 0x50, taille DEBOXEE de `classes.tsv`
//     qui publie 96 = 0x60 header compris).
//     ⚠ PORTEE REELLE, mesuree sur `frida/methods.tsv` : ce nom couvre **107 corps** — un par
//     effet concret. Le symbole hooke ici est le FORWARDER de la classe de base, qui delegue a un
//     slot virtuel. Un effet qui SURCHARGE `CreateEffectDamageBonusForAttack` ne passe PAS par
//     lui. C'est pourquoi l'ancrage 3 existe : lui voit TOUT, quelle que soit l'origine.
//  2. `DamageCalculations$$CalculateAttackerModifiersForPrediction` et
//     `DamageCalculations$$CalculateDefenderModifiersForPrediction` — ils ETIQUETTENT la face.
//     C'est LE point qui repond au residu (« on ne sait pas distinguer ce que cette fabrique verse
//     de ce que verse son homologue defenseur ») : tout evenement capte pendant leur fenetre porte
//     `face: "attacker" | "defender"`. Hors fenetre -> `face: null`, jamais une face devinee.
//  3. `DamageModifiers$$Add` — les DEUX surcharges. C'est le CANAL D'ATTERRISSAGE : on lit
//     l'accumulateur AVANT et APRES, donc on voit LEQUEL des trois etages a bouge
//     (`additive@0x10`, `cappedList@0x18` count, `multiplier@0x30`). Aucune deduction.
//  4. rien d'autre. Pas de hook sur les 107 corps concrets (35 attaches = cctor cascade).
//
// ── DISCIPLINE (section « Ne jamais » du CLAUDE.md) ───────────────────────────────────────────
// `DamageModifiers$$Add` est sur le chemin de degat, donc CHAUD. Ce module :
//   * n'arme RIEN au `register` (comme `hitTrace`, `modifierObserve`, `scorerDamageTrace`) ;
//   * s'arme sur `effectBonusTraceOn` UNIQUEMENT, sur etat stable (post-amorce) ;
//   * porte un BUDGET d'evenements (`budget`, defaut 4000) qui coupe la capture toute seule —
//     un capteur laisse ON par megarde s'eteint au lieu de saturer une session partagee ;
//   * ne fait AUCUNE allocation ni backtrace dans le chemin chaud quand `trace.on` est faux.
// Les Interceptor.attach restent poses apres un `Off` (Frida ne detache pas a la demande sans
// risque) : le gate `trace.on` est teste EN PREMIER dans chaque callback, cout ~nul.
//
// ── CE QU'ON PUBLIE, ET POURQUOI DU BRUT ──────────────────────────────────────────────────────
// Les offsets de champ de `EffectBonus` sont DEDUITS de l'ABI des fabriques statiques
// (`EffectBonus$$ForAddition` / `ForPercentIncrease` / `ForSubtraction` / `ForOverride` :
// chacune ecrit SON slot et met les autres a zero), pas lus dans une table de champs nommee.
// C'est une HYPOTHESE, et un capteur ne doit jamais publier une hypothese comme une mesure.
// On publie donc TROIS niveaux, dans cet ordre de fiabilite :
//   * `rawHex`     — les octets, verite non interpretable a tort ;
//   * `fields`     — le layout NOMME lu au runtime (`class_get_fields`), l'arbitre ;
//   * `guess`      — l'interpretation best-effort, explicitement etiquetee.
// Corollaire operationnel : une interpretation fausse se corrige cote Python, SANS seconde
// fenetre de reinjection.
//
// RPC : effectBonusTrace{On,Off,Clear,Dump,Layout}.

import { Ctx } from "../controller.js";
import {
    class_get_name, class_get_parent, findClassAnywhere, findMethod,
    findMethodByParamCount, s,
} from "../il2cpp/helpers.js";
import { classFieldsDump } from "./ai-step/projection.js";
import { getTraceOrigin, OriginBuffers } from "../game/trace-origin.js";
import { arm, disarm, capturing, extinguish, armedReport } from "../game/armed-runners.js";
import { log } from "../runtime/diag.js";

// Cap PAR ORIGINE de chaque famille (meme convention que scorer-damage-trace).
const CAP = 4000;
// Budget par defaut d'un `On` : nombre TOTAL d'evenements captes avant auto-extinction.
const DEFAULT_BUDGET = 4000;

// ── Tailles de struct, DEBOXEES ───────────────────────────────────────────────────────────────
// `data/symbols/<build>/frida/classes.tsv` publie la taille BOXEE d'un ValueType (header 0x10
// compris — cf. reference_symbol_table_versioned). Les tailles utiles sont donc :
//   IdunBattle.Entities.Effects.EffectBonus     96 boxe -> 0x50
//   System.Nullable<EffectBonus>                        -> 0x58 (0x50 + hasValue, aligne)
//   IdunBattle.Core.Services.DamageBonus       104 boxe -> 0x58
//   IdunBattle.Core.Services.DamageModifiers    80 boxe -> 0x40
// Elles sont RE-DERIVEES au runtime quand la classe se resout (`sizeOfValueType`), et ces
// litteraux ne servent que de borne de lecture defensive.
const EFFECT_BONUS_NULLABLE_BYTES = 0x58;
const DAMAGE_BONUS_BYTES = 0x58;

// ── Offsets RELATIFS lus au decompile (autorises : ce sont des champs de struct) ──────────────
// `IdunBattle.Core.Services.DamageModifiers` (0x40), tel que le lisent
// `DamageModifiers$$Add` et `DamageCalculations$$ApplyCappedModifiers` :
const DM_ADDITIVE = 0x10;    // Fix64 — l'accumulateur additif (`+=` / `-=` des flats)
const DM_CAPPED_LIST = 0x18; // List<{mult, cap}> — la liste CAPEE (le canal des pourcentages)
const DM_MULTIPLIER = 0x30;  // Fix64 — l'etage MULTIPLICATEUR (arrondi a CHAQUE etage)
const DM_BONUS_LIST = 0x38;  // List<DamageBonus> — tracabilite
// `IdunBattle.Core.Services.DamageBonus` (0x58) — les quatre Nullable que `Add` DEREFERENCE.
// Les noms sont ceux de leur ROLE observe dans `Add`, pas des noms C# : le layout nomme est
// publie par `effectBonusTraceLayout`, et c'est LUI qui fait foi.
const DB_FLAT_PLUS = 0x28;   // Nullable<int> -> `this.additive += Fix64(v)`
const DB_FLAT_MINUS = 0x30;  // Nullable<int> -> `this.additive -= Fix64(v)`
const DB_PCT = 0x48;         // Nullable<int> -> entree de la liste capee : mult = One + Pct(v)
const DB_CAP = 0x50;         // Nullable<int> -> entree de la liste capee : cap
// List<T> IL2CPP : _size @+0x18 (meme constante que ai-step/internals.LIST_SIZE ; on ne l'importe
// pas pour garder ce module autonome du sous-arbre ai-step).
const LIST_SIZE = 0x18;

// ── Lectures elementaires ─────────────────────────────────────────────────────────────────────

/** Fix64 = Q32.32 signe. Lecture BigInt obligatoire (un int64 ne tient pas dans un double). */
function readFix64(p: NativePointer): number {
    try {
        let raw = BigInt(p.readS64().toString());
        if (raw >= (1n << 63n)) raw -= (1n << 64n);
        return Number(raw) / 4294967296;
    } catch { return NaN; }
}

/** Octets bruts en hex — la SEULE lecture qu'aucune erreur d'interpretation ne peut fausser. */
function readHex(p: NativePointer, n: number): string | null {
    try { return p.readByteArray(n) === null ? null : hexOf(p, n); }
    catch { return null; }
}
function hexOf(p: NativePointer, n: number): string {
    let out = "";
    for (let i = 0; i < n; i++) {
        const b = p.add(i).readU8();
        out += (b < 16 ? "0" : "") + b.toString(16);
    }
    return out;
}

/** Un `Nullable<int>` IL2CPP, lu dans les DEUX ordres possibles.
 *
 *  L'ordre des deux champs n'est PAS le meme partout dans ce depot : `ai-step/internals.ts`
 *  documente `MovementOptions.OverrideRange` en `hasValue@+0, value@+4`, tandis que
 *  `scorer-damage-trace.ts` lit les deux hypotheses cote a cote « pour lever l'ambiguite
 *  gshared ». Ce capteur ne tranche donc pas a l'aveugle : il rend les deux, et la premiere
 *  mesure tranche (le champ `cap`, borne connue du gameconfig, est le discriminant naturel). */
function readNullableInt(p: NativePointer): { hv0: number; v4: number; v0: number; hv4: number } {
    try {
        return {
            hv0: p.readU8(),            // hypothese A : has_value @+0
            v4: p.add(4).readS32(),     //               value     @+4
            v0: p.readS32(),            // hypothese B : value     @+0
            hv4: p.add(4).readU8(),     //               has_value @+4
        };
    } catch { return { hv0: -1, v4: -1, v0: -1, hv4: -1 }; }
}

// ── Etat ──────────────────────────────────────────────────────────────────────────────────────

/** Face COURANTE, posee par les hooks `Calculate{Attacker,Defender}ModifiersForPrediction`.
 *  `null` = hors fenetre (chemin non instrumente, ou combat plutot que prediction) — on NE
 *  devine JAMAIS une face : un evenement non attribue le dit. */
let curFace: "attacker" | "defender" | null = null;
/** Profondeur de la fenetre — les deux faces peuvent s'imbriquer (le defenseur est calcule
 *  DANS la passe attaquante sur certains chemins). Une pile evite qu'un `onLeave` interne
 *  efface la face de son englobant. */
const faceStack: Array<"attacker" | "defender"> = [];

// LA PORTE N'EST PLUS UN BOOLEEN DE MODULE (#483) : `trace.on` est un ACCESSEUR qui
// consulte l'armement PAR RUNNER contre l'origine COURANTE. Cf. game/armed-runners.ts.
const trace: { readonly on: boolean; seq: number; budget: number } = {
    get on(): boolean { return capturing("effectBonus"); },
    seq: 0, budget: DEFAULT_BUDGET,
};

/** Budget DEPENSE PAR ORIGINE (#483). Il l'etait globalement, ce qui rouvrait le meme mode de
 *  panne par une autre porte : deux acteurs en parallele partageaient un compteur, et
 *  l'epuisement de l'un ETEIGNAIT la capture de l'autre — silencieusement. Meme raison que le
 *  CAP par bucket d'`OriginBuffers` : « un acteur bavard ne peut plus affamer les autres ». */
const spentByOrigin = new Map<number | null, number>();

/** Un evenement consomme le budget DE SON ORIGINE ; a l'epuisement la capture s'ETEINT POUR
 *  ELLE (elle ne se contente pas de jeter). C'est ce qui empeche un capteur oublie de peser
 *  sur une session partagee, sans emporter les autres acteurs avec lui. */
function spend(): boolean {
    if (!trace.on) return false;
    const k = getTraceOrigin();
    const spent = spentByOrigin.get(k) ?? 0;
    if (spent >= trace.budget) {
        // `extinguish` garantit `capturingFor(k) === false` — sans quoi le test ci-dessus se
        // rejouerait a chaque evenement (extinction sterile). Il retire l'armement NOMINATIF
        // de k et, si c'est le GLOBAL qui couvrait k, le global : c'est le prix de la
        // post-condition, et le regime cible (chaque appelant passe son runnerId) ne le paie pas.
        extinguish("effectBonus", k);
        log("[effect-bonus-trace] budget epuise (" + trace.budget + ") pour origine "
            + (k === null ? "live" : String(k)) + " — capture ETEINTE pour ELLE");
        return false;
    }
    spentByOrigin.set(k, spent + 1);
    return true;
}

/** Depense de l'origine INTERROGEE (compte-rendu). Sans `runnerId` : total toutes origines —
 *  un chiffre agrege qui ne doit pas se lire comme celui d'un acteur. */
function spentFor(runnerId?: number): number {
    if (typeof runnerId === "number") return spentByOrigin.get(runnerId) ?? 0;
    let n = 0;
    for (const v of spentByOrigin.values()) n += v;
    return n;
}

/** Ce que rend la FABRIQUE (ancrage 1) : le `Nullable<EffectBonus>` brut + son layout. */
interface FactoryEvent {
    seq: number;
    originRunnerId: number | null;
    face: string | null;        // "attacker" | "defender" | null (hors fenetre)
    effectClass: string;        // classe CONCRETE de l'effet (this) — qui a produit ce bonus
    rawHex: string | null;      // les 0x58 octets du Nullable<EffectBonus>
    hasValue: number;           // octet @+0x50 (candidat has_value du Nullable englobant)
    /** Interpretation best-effort — HYPOTHESE, cf. l'en-tete. Chaque entree = un slot de
     *  `EffectBonus` non nul, avec le nom de classe de la formule qui l'occupe : c'est CE
     *  champ qui dit, pour un effet donne, s'il produit un POURCENTAGE ou un ADDITIF. */
    guess: Array<{ off: number; role: string; cls: string | null }>;
}

/** Ce que consomme l'ACCUMULATEUR (ancrage 3) : le canal ou ca atterrit REELLEMENT. */
interface AddEvent {
    seq: number;
    originRunnerId: number | null;
    face: string | null;
    overload: number;              // 2 = (damageBonus, modifier) ; 1 = (modifier)
    accum: string;                 // ptr de l'accumulateur — distingue deux DamageModifiers vivants
    // --- entree ---
    bonusHex: string | null;       // les 0x58 octets du DamageBonus (overload 2 seulement)
    flatPlus: ReturnType<typeof readNullableInt> | null;
    flatMinus: ReturnType<typeof readNullableInt> | null;
    pct: ReturnType<typeof readNullableInt> | null;
    cap: ReturnType<typeof readNullableInt> | null;
    modifierHex: string | null;    // les 16 octets du Nullable<Fix64> modifier
    modifierValue: number;         // Fix64 @+0 (interpretation value-first)
    modifierHasValue: number;      // octet @+8
    // --- accumulateur AVANT / APRES : c'est CA qui tranche le canal, sans deduction ---
    addBefore: number; addAfter: number;          // additive@0x10
    multBefore: number; multAfter: number;        // multiplier@0x30
    cappedBefore: number; cappedAfter: number;    // count de la liste capee@0x18
    bonusListBefore: number; bonusListAfter: number;
}

const factoryTrace = new OriginBuffers<FactoryEvent>(CAP, "dropNew");
const addTrace = new OriginBuffers<AddEvent>(CAP, "dropNew");

// ── Ce que les hooks de FACE ont pose, et ce qu'ils ont TRAVERSE ──────────────────────────────
//
// ⚠ CE BLOC EXISTE PARCE QU'UNE MESURE EST RESTEE INDECIDABLE SANS LUI (2026-08-04). La capture
// a rendu 693 `Add`, TOUS etiquetes `attacker`, ZERO `defender`. Deux lectures incompatibles
// expliquaient ce meme chiffre, et rien de ce que le capteur publiait ne les separait :
//   (a) la fenetre DEFENSEUR n'est pas traversee sur ce chemin — un resultat ;
//   (b) le hook DEFENSEUR n'a pas ete pose (surcharge non resolue) — une panne de capteur.
// Un capteur doit pouvoir dire laquelle. `facesPosed` repond a (b) — quelles surcharges,
// avec quelle arite, ont recu un `Interceptor.attach` — et `faceEnters` repond a (a) :
// combien de fois CHAQUE fenetre a ete franchie, INDEPENDAMMENT de tout `Add`. Une fenetre
// traversee 0 fois avec un hook pose est une mesure ; sans le compteur, c'est une ambiguite.
const facesPosed: Array<{ name: string; params: number; face: string; ptr: string }> = [];
const faceEnters: { attacker: number; defender: number } = { attacker: 0, defender: 0 };

// ── Layout runtime (l'ARBITRE de toute interpretation) ────────────────────────────────────────

interface LayoutEntry {
    cls: string; size: number;
    fields: Array<{ name: string; offset: number; type: string }>;
    /** Les MEMES champs, ramenes a l'origine de la struct NUE (`offset - 0x10` sur un ValueType).
     *  ⚠ CE CHAMP EXISTE PARCE QUE SON ABSENCE A DEJA INDUIT EN ERREUR (mesure du 2026-08-04).
     *  `field_get_offset` publie l'offset dans la representation BOXEE — en-tete d'objet de
     *  0x10 compris — alors que les constantes de ce module (`DM_*`, `DB_*`) sont les offsets
     *  de la struct NUE, celle que les `Add` recoivent par pointeur. Lus cote a cote, les deux
     *  series semblent toutes decalees et se lisent comme « tous les offsets du capteur sont
     *  faux » ; elles concordent EXACTEMENT une fois l'en-tete retire. Un capteur qui publie
     *  deux referentiels sans les nommer fabrique un faux ecart. */
    nakedFields?: Array<{ name: string; offset: number; type: string }>;
    isValueType?: boolean;
    note?: string;
}
/** Bit `IL2CPP_CLASS_VALUE_TYPE` du `Il2CppClass` (byte de flags @+0x127 sur ce build). Lu en
 *  best-effort : `undefined` = pas mesure, jamais un `false` fabrique. */
function isValueType(k: NativePointer): boolean | undefined {
    try { return (k.add(0x127).readU8() & 0x01) !== 0; } catch { return undefined; }
}

function dumpLayout(ns: string, cls: string): LayoutEntry | { cls: string; error: string } {
    const k = findClassAnywhere(ns, cls);
    if (!k) return { cls: ns + "." + cls, error: "classe non resolue" };
    let size = -1;
    try { size = k.add(0x18).readS32(); } catch { /* laisse -1 */ }
    const fields = classFieldsDump(k);
    const vt = isValueType(k);
    return {
        cls: ns + "." + cls, size, fields,
        isValueType: vt,
        nakedFields: fields.map((f) => ({ ...f, offset: f.offset - 0x10 })),
        note: "`fields` = offsets BOXES (en-tete d'objet 0x10 compris, tels que rendus par"
            + " field_get_offset). `nakedFields` = les memes moins 0x10 : c'est CE referentiel"
            + " que les constantes DM_*/DB_* de ce module emploient, parce qu'un ValueType"
            + " passe aux `Add` par pointeur n'a pas d'en-tete. Comparer aux constantes SANS"
            + " cette conversion fabrique un ecart de 0x10 qui n'existe pas.",
    };
}

// ── Ancrage 1 : la FABRIQUE ───────────────────────────────────────────────────────────────────

/** Slots de `EffectBonus` deduits de l'ABI des fabriques statiques (cf. l'en-tete). HYPOTHESE :
 *  `effectBonusTraceLayout` publie le layout NOMME, qui fait foi. */
const EFFECT_BONUS_SLOTS: Array<[number, string]> = [
    [0x00, "trigger"],
    [0x08, "bonusPct"],       // ForPercentIncrease / ForPercentDecrease (formule negative)
    [0x10, "addition"],       // ForAddition / ForAdditionWithMinimum
    [0x18, "subtraction"],    // ForSubtraction
    [0x20, "minimum"],        // ForAdditionWithMinimum
    [0x28, "override"],       // ForOverride
];

let factoryInstalled = false;
function installFactoryHook(): boolean {
    if (factoryInstalled) return true;
    const klass = findClassAnywhere("IdunBattle.Entities.Effects", "DamageModifierAbilityEffect");
    if (!klass) {
        log("[effect-bonus-trace] DamageModifierAbilityEffect non resolue — fabrique non hookee");
        return false;
    }
    const mi = findMethod(klass, "CreateEffectDamageBonusForAttack");
    if (!mi || mi.ptr.isNull()) {
        log("[effect-bonus-trace] CreateEffectDamageBonusForAttack non resolue");
        return false;
    }
    Interceptor.attach(mi.ptr, {
        onEnter(args) {
            // ABI Microsoft x64 : un struct de 0x58 octets se rend PAR BUFFER — RCX = le buffer
            // de retour, RDX = `this`. Ghidra le montre (`return this;` ou `this` est RCX).
            // On capture les deux ici et on lit le buffer dans onLeave (a l'entree il est vide).
            const self = this as { _ret?: NativePointer; _eff?: NativePointer; _on?: boolean };
            self._on = trace.on;
            if (!trace.on) return;
            self._ret = args[0];
            self._eff = args[1];
        },
        onLeave() {
            const self = this as { _ret?: NativePointer; _eff?: NativePointer; _on?: boolean };
            if (!self._on || !trace.on) return;
            if (!spend()) return;
            try {
                const buf = self._ret;
                if (!buf || buf.isNull()) return;
                let effectClass = "?";
                try {
                    const e = self._eff;
                    if (e && !e.isNull()) {
                        effectClass = s(class_get_name(e.readPointer()) as NativePointer);
                    }
                } catch { /* laisse "?" */ }
                const guess: Array<{ off: number; role: string; cls: string | null }> = [];
                for (const [off, role] of EFFECT_BONUS_SLOTS) {
                    try {
                        const f = buf.add(off).readPointer();
                        if (f.isNull()) continue;
                        let cls: string | null = null;
                        try { cls = s(class_get_name(f.readPointer()) as NativePointer); }
                        catch { cls = null; }
                        guess.push({ off, role, cls });
                    } catch { /* slot suivant */ }
                }
                factoryTrace.push({
                    seq: ++trace.seq,
                    originRunnerId: getTraceOrigin(),
                    face: curFace,
                    effectClass,
                    rawHex: readHex(buf, EFFECT_BONUS_NULLABLE_BYTES),
                    hasValue: (() => { try { return buf.add(0x50).readU8(); } catch { return -1; } })(),
                    guess,
                });
            } catch { /* transient */ }
        },
    });
    factoryInstalled = true;
    log("[effect-bonus-trace] hooke DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack @ "
        + mi.ptr);
    return true;
}

// ── Ancrage 2 : l'ETIQUETAGE DE FACE ──────────────────────────────────────────────────────────

let faceInstalled = false;
function installFaceHooks(): boolean {
    if (faceInstalled) return true;
    const klass = findClassAnywhere("IdunBattle.Core.Services", "DamageCalculations");
    if (!klass) {
        log("[effect-bonus-trace] DamageCalculations non resolue — face NON etiquetee");
        return false;
    }
    // Les deux familles portent PLUSIEURS surcharges (`CalculateDefenderModifiersForPrediction`
    // existe en 2 et 3 parametres). On les hooke TOUTES : rater une surcharge laisserait des
    // evenements a face `null` qu'on serait tente d'attribuer a la main.
    let posed = 0;
    for (const [name, face] of [
        ["CalculateAttackerModifiersForPrediction", "attacker"],
        ["CalculateDefenderModifiersForPrediction", "defender"],
    ] as Array<[string, "attacker" | "defender"]>) {
        for (const n of [2, 3]) {
            const mi = findMethodByParamCount(klass, name, n);
            if (!mi || mi.ptr.isNull()) continue;
            Interceptor.attach(mi.ptr, {
                onEnter() {
                    // ⚠ Le depilage se conditionne a CE QU'ON A EMPILE, jamais a `trace.on`.
                    // `trace.on` peut basculer ENTRE l'entree et la sortie (budget epuise) : un
                    // `onLeave` gate sur lui sauterait le depilage, la pile fuirait, et
                    // `curFace` resterait colle — les evenements du `On` SUIVANT porteraient une
                    // face FAUSSE. Une face fausse est pire qu'une face absente : elle se lit
                    // comme une mesure.
                    const self = this as { _pushed?: boolean };
                    self._pushed = false;
                    if (!trace.on) return;
                    faceEnters[face]++;
                    faceStack.push(face);
                    curFace = face;
                    self._pushed = true;
                },
                onLeave() {
                    const self = this as { _pushed?: boolean };
                    if (!self._pushed) return;
                    // Depile SA face — pas la derniere : sur un chemin imbrique, un `onLeave`
                    // qui viderait la pile effacerait la face de l'appel englobant.
                    const i = faceStack.lastIndexOf(face);
                    if (i >= 0) faceStack.splice(i, 1);
                    curFace = faceStack.length ? faceStack[faceStack.length - 1] : null;
                },
            });
            posed++;
            facesPosed.push({ name, params: n, face, ptr: mi.ptr.toString() });
            log("[effect-bonus-trace] hooke " + name + "(" + n + ") -> face=" + face
                + " @ " + mi.ptr);
        }
    }
    if (!posed) {
        log("[effect-bonus-trace] AUCUNE surcharge Calculate*ModifiersForPrediction resolue");
        return false;
    }
    faceInstalled = true;
    return true;
}

// ── Ancrage 3 : le CANAL D'ATTERRISSAGE ───────────────────────────────────────────────────────

function readAccum(p: NativePointer | undefined):
{ add: number; mult: number; capped: number; bonuses: number } {
    const out = { add: NaN, mult: NaN, capped: -1, bonuses: -1 };
    if (!p || p.isNull()) return out;
    try { out.add = readFix64(p.add(DM_ADDITIVE)); } catch { /* */ }
    try { out.mult = readFix64(p.add(DM_MULTIPLIER)); } catch { /* */ }
    try {
        const l = p.add(DM_CAPPED_LIST).readPointer();
        out.capped = l.isNull() ? -1 : l.add(LIST_SIZE).readS32();
    } catch { /* */ }
    try {
        const l = p.add(DM_BONUS_LIST).readPointer();
        out.bonuses = l.isNull() ? -1 : l.add(LIST_SIZE).readS32();
    } catch { /* */ }
    return out;
}

let addInstalled = false;
function installAddHooks(): boolean {
    if (addInstalled) return true;
    const klass = findClassAnywhere("IdunBattle.Core.Services", "DamageModifiers");
    if (!klass) {
        log("[effect-bonus-trace] DamageModifiers non resolue — canal non hooke");
        return false;
    }
    // 2 params = `Add(damageBonus, modifier)` (les EFFETS) ; 1 param = `Add(modifier)` (le canal
    // MULTIPLICATEUR sec, celui des modifications de stat). Departagees par leur COMPTE
    // d'arguments, jamais par l'ordre des adresses (cf. le piege documente dans
    // scorer-damage-trace : deux corps sous un meme symbole se departagent par la SIGNATURE).
    let posed = 0;
    for (const n of [2, 1]) {
        const mi = findMethodByParamCount(klass, "Add", n);
        if (!mi || mi.ptr.isNull()) continue;
        Interceptor.attach(mi.ptr, {
            onEnter(args) {
                const self = this as {
                    _on?: boolean; _self?: NativePointer;
                    _bonus?: NativePointer; _mod?: NativePointer;
                    _before?: ReturnType<typeof readAccum>;
                };
                self._on = trace.on;
                if (!trace.on) return;
                try {
                    self._self = args[0];
                    if (n === 2) { self._bonus = args[1]; self._mod = args[2]; }
                    else { self._bonus = undefined; self._mod = args[1]; }
                    self._before = readAccum(self._self);
                } catch { self._on = false; }
            },
            onLeave() {
                const self = this as {
                    _on?: boolean; _self?: NativePointer;
                    _bonus?: NativePointer; _mod?: NativePointer;
                    _before?: ReturnType<typeof readAccum>;
                };
                if (!self._on || !trace.on) return;
                if (!spend()) return;
                try {
                    const before = self._before ?? readAccum(undefined);
                    const after = readAccum(self._self);
                    const b = self._bonus;
                    const m = self._mod;
                    addTrace.push({
                        seq: ++trace.seq,
                        originRunnerId: getTraceOrigin(),
                        face: curFace,
                        overload: n,
                        accum: self._self ? self._self.toString() : "0x0",
                        bonusHex: (b && !b.isNull()) ? readHex(b, DAMAGE_BONUS_BYTES) : null,
                        flatPlus: (b && !b.isNull()) ? readNullableInt(b.add(DB_FLAT_PLUS)) : null,
                        flatMinus: (b && !b.isNull()) ? readNullableInt(b.add(DB_FLAT_MINUS)) : null,
                        pct: (b && !b.isNull()) ? readNullableInt(b.add(DB_PCT)) : null,
                        cap: (b && !b.isNull()) ? readNullableInt(b.add(DB_CAP)) : null,
                        // ⚠ LES DEUX SURCHARGES NE PASSENT PAS LE MODIFIER DE LA MEME FACON, et
                        // les confondre lirait de la memoire arbitraire :
                        //   * surcharge 2 : `Nullable<Fix64>` = 16 octets > 8, donc passe PAR
                        //     REFERENCE — le decompile le confirme (`get_HasValue(modifier)`
                        //     deref l'argument). `m` est un POINTEUR.
                        //   * surcharge 1 : `Fix64` = 8 octets, passe PAR VALEUR en registre
                        //     (`op_Multiply(this[0x30], modifier)`). `m` EST la valeur brute ;
                        //     la deferencer serait une lecture a une adresse fabriquee.
                        // `modifierHasValue` n'a de sens que pour la surcharge 2 ; pour la 1 on
                        // rend -1 (« sans objet »), jamais un `true` fabrique.
                        modifierHex: (n === 2 && m && !m.isNull()) ? readHex(m, 16) : null,
                        modifierValue: (() => {
                            try {
                                if (!m) return NaN;
                                if (n === 2) return m.isNull() ? NaN : readFix64(m);
                                let raw = BigInt(m.toString());       // valeur Fix64 NUE
                                if (raw >= (1n << 63n)) raw -= (1n << 64n);
                                return Number(raw) / 4294967296;
                            } catch { return NaN; }
                        })(),
                        // ⚠ MESURE 2026-08-04 : sur 30 evenements de la surcharge 2, cet octet
                        // valait `51` — pas un booleen. L'octet @+8 du `Nullable<Fix64>` n'est
                        // donc PAS son `has_value` sur ce build (padding, ou layout
                        // value-first inverse). Un capteur ne publie pas un octet arbitraire
                        // sous un nom qui promet un booleen : hors {0,1} on rend `-1`
                        // (« pas mesure »), et l'octet brut reste lisible dans `modifierHex`.
                        // La question se tranche de toute facon SANS lui : quand `modifier` a
                        // une valeur, la surcharge 2 DELEGUE a la surcharge 1, dont l'evenement
                        // porte le multiplicateur reellement applique.
                        modifierHasValue: (() => {
                            try {
                                if (n !== 2) return -1;               // sans objet (Fix64 nu)
                                if (!m || m.isNull()) return -1;
                                const b = m.add(8).readU8();
                                return (b === 0 || b === 1) ? b : -1;
                            } catch { return -1; }
                        })(),
                        addBefore: before.add, addAfter: after.add,
                        multBefore: before.mult, multAfter: after.mult,
                        cappedBefore: before.capped, cappedAfter: after.capped,
                        bonusListBefore: before.bonuses, bonusListAfter: after.bonuses,
                    });
                } catch { /* transient */ }
            },
        });
        posed++;
        log("[effect-bonus-trace] hooke DamageModifiers$$Add(" + n + ") @ " + mi.ptr);
    }
    if (!posed) {
        log("[effect-bonus-trace] AUCUNE surcharge DamageModifiers$$Add resolue");
        return false;
    }
    addInstalled = true;
    return true;
}

// ── Armement ──────────────────────────────────────────────────────────────────────────────────

let armed = false;
/** INSTALLE les trois familles de hooks (idempotent). Renomme depuis `arm()` (#483) :
 *  l'INSTALLATION physique et l'ARMEMENT de la capture sont deux choses distinctes
 *  depuis que la seconde est par runner — les confondre sous un meme nom invitait la
 *  faute que ce module corrige. */
function installAllHooks(): { factory: boolean; face: boolean; add: boolean } {
    const r = {
        factory: installFactoryHook(),
        face: installFaceHooks(),
        add: installAddHooks(),
    };
    armed = r.factory || r.face || r.add;
    return r;
}

export function register(ctx: Ctx): void {
    /** ARME les hooks (idempotent) et OUVRE la capture.
     *  body: { budget? } — nombre total d'evenements avant auto-extinction (defaut 4000).
     *  ⚠ A n'appeler que sur session STABLE (post-amorce) : ces hooks sont sur le chemin de
     *  degat. Le register n'arme RIEN de lui-meme, par construction. */
    ctx.rpc.effectBonusTraceOn = (
        body?: { budget?: number; runnerId?: number },
    ): unknown => {
        const r = installAllHooks();
        trace.budget = (typeof body?.budget === "number" && body.budget > 0)
            ? (body.budget | 0) : DEFAULT_BUDGET;
        // Le budget se remet a zero POUR L'ORIGINE ARMEE seulement (#483) : un `On` d'un
        // acteur ne doit pas recharger — ni remettre a zero le compteur publie — d'un autre.
        // Armement GLOBAL (pas de runnerId) : on repart de zero partout, comme avant.
        if (typeof body?.runnerId === "number") spentByOrigin.delete(body.runnerId);
        else spentByOrigin.clear();
        // Repart d'une pile de faces VIDE. Un `Off` (ou une extinction par budget) survenu au
        // milieu d'une fenetre native laisse au pire une entree orpheline ; l'heriter ferait
        // porter a la capture suivante une face qui n'est pas la sienne.
        faceStack.length = 0;
        curFace = null;
        faceEnters.attacker = 0;
        faceEnters.defender = 0;
        arm("effectBonus", body?.runnerId);
        return {
            ok: true, armed, hooks: r, budget: trace.budget,
            ...armedReport("effectBonus", body?.runnerId),
        };
    };

    /** DESARME. Sans `runnerId` : le GLOBAL seulement — les armements nominatifs des autres
     *  acteurs survivent (#483). C'est CE `finally`-la qui tronquait les mesures voisines. */
    ctx.rpc.effectBonusTraceOff = (body?: { runnerId?: number }): unknown => {
        disarm("effectBonus", body?.runnerId);
        return {
            ok: true, spent: spentFor(body?.runnerId), budget: trace.budget,
            ...armedReport("effectBonus", body?.runnerId),
        };
    };

    ctx.rpc.effectBonusTraceClear = (body?: { runnerId?: number }): unknown => {
        const rid = typeof body?.runnerId === "number" ? body.runnerId : undefined;
        factoryTrace.clear(rid);
        addTrace.clear(rid);
        if (rid === undefined) { trace.seq = 0; spentByOrigin.clear(); }
        else spentByOrigin.delete(rid);
        return { ok: true };
    };

    /** DUMP. body: { runnerId? } — sans lui, toutes origines confondues (ordre `seq`). */
    ctx.rpc.effectBonusTraceDump = (body?: { runnerId?: number }): unknown => {
        const rid = typeof body?.runnerId === "number" ? body.runnerId : undefined;
        return {
            ok: true,
            ...armedReport("effectBonus", rid), armed,
            spent: spentFor(rid), budget: trace.budget,
            // Ce que les hooks de face ONT POSE, et combien de fois chaque fenetre a ete
            // FRANCHIE — sans ces deux-la, un `0 defender` dans `adds` ne separe pas
            // « fenetre non traversee » de « hook non pose ». Cf. le bloc de declaration.
            facesPosed, faceEnters: { ...faceEnters },
            factory: factoryTrace.entries(rid),
            adds: addTrace.entries(rid),
        };
    };

    /** LAYOUT NOMME des structs en jeu — l'ARBITRE de toute interpretation d'offset publiee
     *  par ce module. A lire AVANT d'exploiter `guess` : si un champ nomme contredit un slot
     *  devine, c'est le champ nomme qui a raison, et l'interpretation se corrige cote Python
     *  sans nouvelle fenetre de reinjection.
     *  Publie aussi la chaine d'heritage de `DamageModifierAbilityEffect` : c'est elle qui dit
     *  quels effets concrets passent par le FORWARDER hooke (ancrage 1) et lesquels le
     *  surchargent — donc la PORTEE reelle du capteur. */
    ctx.rpc.effectBonusTraceLayout = (): unknown => {
        const chain: string[] = [];
        try {
            let k = findClassAnywhere("IdunBattle.Entities.Effects", "DamageModifierAbilityEffect");
            let depth = 0;
            while (k && !k.isNull() && depth < 8) {
                chain.push(s(class_get_name(k) as NativePointer));
                k = class_get_parent(k) as NativePointer;
                depth++;
            }
        } catch { /* best effort */ }
        return {
            ok: true,
            layouts: [
                dumpLayout("IdunBattle.Entities.Effects", "EffectBonus"),
                dumpLayout("IdunBattle.Core.Services", "DamageBonus"),
                dumpLayout("IdunBattle.Core.Services", "DamageModifiers"),
                dumpLayout("IdunBattle.Core.Services", "SimpleDamageBonus"),
            ],
            damageModifierAbilityEffectChain: chain,
            // Les offsets que CE module utilise, publies pour confrontation directe au layout
            // ci-dessus. Un ecart ici est un bug de capteur, pas une decouverte de jeu.
            assumedOffsets: {
                damageModifiers: {
                    additive: DM_ADDITIVE, cappedList: DM_CAPPED_LIST,
                    multiplier: DM_MULTIPLIER, bonusList: DM_BONUS_LIST,
                },
                damageBonus: {
                    flatPlus: DB_FLAT_PLUS, flatMinus: DB_FLAT_MINUS,
                    pct: DB_PCT, cap: DB_CAP,
                },
                effectBonusSlots: EFFECT_BONUS_SLOTS.map(([o, r]) => ({ off: o, role: r })),
            },
        };
    };
}
