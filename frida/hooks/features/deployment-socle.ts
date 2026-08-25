// LE SOCLE DU DEPLOIEMENT — les outils que TOUS les modules de la famille partagent.
//
// Extrait de `deployment-draft.ts` le 2026-08-26, alors qu'il atteignait 7137 lignes pour une
// consigne de depot a ~1000. Ce fichier est une FEUILLE : il n'importe rien de la famille, donc
// les autres modules peuvent l'importer sans jamais fermer de cycle. C'est ce qui rend la suite
// du decoupage possible -- sans lui, `deployment-prefab` devrait reimporter `refus` et
// `lireTete` a `deployment-draft`, qui l'importe deja.
//
// Ce qu'il porte, et rien d'autre :
//   * `Refus` / `refus`      — la forme unique du refus nomme (100 usages dans la famille) ;
//   * `Tete` / `lireTete` / `teteTriviale` — la garde anti-deduplication IL2CPP : un corps
//     trivial a une adresse PARTAGEE, s'y attacher basculerait N methodes ;
//   * `ghidraVA` / `pileGhidra` / `pileGhidraFroide` — citer une adresse en RVA lisible ;
//   * `taille` / `boolBoxe`  — deux conversions IL2CPP sans etat.
//
// ⚠ AUCUN ETAT MUTABLE ICI, ET C'EST LA REGLE DU MODULE. ESM interdit d'assigner un
// `export let` depuis un autre module : tout etat pose ici deviendrait soit fige, soit un jeu
// d'accesseurs. L'etat appartient au module qui le mute.

import { class_instance_size, il2cppBase, il2cppSize } from "../il2cpp/helpers.js";

export interface Refus { ok: false; error: string }

export function refus(error: string): Refus { return { ok: false, error }; }

/** Octets lus en tête de corps pour le garde de trivialité. */
export const OCTETS_TETE = 8;

export interface Tete {
    hex: string | null;
    /** Index du premier `ret` (0xC3) dans la tête, ou `null` s'il n'y en a pas. */
    retA: number | null;
    erreur: string | null;
}

/** Lit la tête du corps. Ne lève jamais — un refus de lecture est un refus, pas un silence. */
export function lireTete(p: NativePointer): Tete {
    try {
        const buf = p.readByteArray(OCTETS_TETE);
        if (!buf) return { hex: null, retA: null, erreur: "lecture vide" };
        const o = new Uint8Array(buf);
        let retA: number | null = null;
        for (let i = 0; i < o.length; i++) {
            if (o[i] === 0xc3) { retA = i; break; }
        }
        const hex = Array.from(o).map((b) => b.toString(16).padStart(2, "0")).join(" ");
        return { hex, retA, erreur: null };
    } catch (e) {
        return { hex: null, retA: null, erreur: "lecture refusée : " + (e as Error).message };
    }
}

/**
 * Le corps ressemble-t-il à une constante dédupliquée ? Voir l'en-tête.
 *
 * ⚠ UN SAUT N'EST PAS UN CORPS TRIVIAL, ET LES CONFONDRE A COÛTÉ UN CAPTEUR ENTIER, EN SILENCE.
 * `lireTete` cherche un `0xc3` N'IMPORTE OÙ dans les huit premiers octets — il ne décode rien.
 * Sur un THUNK (`e9 <rel32>`), le premier octet du DÉPLACEMENT peut valoir `0xc3` et se lit
 * alors comme un `ret`. Mesuré le 2026-08-19 sur
 * `IdunBattle.View.Game.IdunGameViews$$Enable`, dont la tête est `e9 c3 db a1 ff 48 89 4c` :
 * le garde annonçait « corps TRIVIAL, ret à l'octet 1 », l'ancrage était refusé, `vuesJeu`
 * restait NUL — et la MoW n'était donc jamais reposée au retry, sans qu'aucun message ne
 * nomme la cause.
 *
 * Un corps trivial dédupliqué commence par `b8 <imm32> c3`, `33 c0 c3`, `31 c0 c3` ou `c3` nu :
 * JAMAIS par un saut. Écarter les têtes de saut ne relâche donc rien du garde — ça lui retire
 * un faux positif.
 */
export function teteTriviale(t: Tete): boolean {
    if (t.hex === null) return false;
    const premier = parseInt(t.hex.slice(0, 2), 16);
    // `e9` = jmp rel32, `eb` = jmp rel8 : une trampoline, pas une constante.
    if (premier === 0xe9 || premier === 0xeb) return false;
    return t.retA !== null;
}

export function ghidraVA(p: NativePointer): string {
    return ptr("0x180000000").add(p.sub(il2cppBase)).toString();
}

/**
 * UNE PILE ENTRANTE, RENDUE EN ADRESSES GHIDRA — pour NOMMER l'appelant au lieu de le deviner.
 *
 * ⚠ POURQUOI PAS `DebugSymbol.fromAddress`. Mesuré le 2026-08-20 : sur ce binaire il rend
 * l'export le plus proche, donc `mono_type_size` pour absolument tout le code de jeu — un
 * backtrace de 16 frames où 15 portent le même nom faux. Ces frames ne sont pas anonymes, elles
 * sont MAL nommées, ce qui est pire : on lit un nom et on le croit. La conversion vers l'espace
 * Ghidra, elle, est exacte, et `data/symbols/<build>/ghidra/functions.tsv` fait le reste hors
 * ligne (`ghidra_symbols.py whereis`).
 *
 * Les frames HORS de l'image du jeu sont rendues telles quelles, avec leur module : elles sont
 * généralement du runtime ou de l'agent Frida lui-même, et les faire passer par `ghidraVA`
 * fabriquerait une adresse qui ne désigne rien.
 */
export function pileGhidra(ctx: CpuContext, max = 20): Array<Record<string, unknown>> {
    const out: Array<Record<string, unknown>> = [];
    let frames: NativePointer[] = [];
    try { frames = Thread.backtrace(ctx, Backtracer.ACCURATE); }
    catch { try { frames = Thread.backtrace(ctx, Backtracer.FUZZY); } catch { return out; } }
    for (const a of frames.slice(0, max)) {
        const delta = a.sub(il2cppBase);
        const dans = delta.compare(ptr(0)) >= 0 && delta.compare(ptr(il2cppSize)) < 0;
        if (dans) { out.push({ ghidraVA: ghidraVA(a) }); continue; }
        let mod: string | null = null;
        try { mod = Process.findModuleByAddress(a)?.name ?? null; } catch { /* best effort */ }
        out.push({ brut: a.toString(), module: mod, horsImage: true });
    }
    return out;
}

/**
 * LA MÊME PILE, EN RÉGIME FROID — aucune API Frida qui touche au processus.
 *
 * ⛔ CE VARIANT EXISTE PARCE QUE L'AUTRE A TUÉ LE JEU. Mesuré le 2026-08-20, minidump à l'appui
 * (`Tacticus.exe.26196.dmp`, 02:09:20) : un `Interceptor.attach` sur `FUN_180201a80` — le fond
 * commun de TOUS les jets IL2CPP — dont le `onEnter` appelait `decodeManagedException` (qui
 * ré-entre dans `il2cpp_class_get_name`) et `Process.findModuleByAddress`. On ré-entre donc dans
 * le runtime PENDANT qu'il déroule une exception. Le jeu est mort au premier tir.
 *
 * Sur un chemin de jet, on ne fait QUE des lectures mémoire et de l'arithmétique. Résoudre les
 * noms est le travail du LECTEUR du RPC, dans un contexte sain — et c'est possible parce qu'un
 * `Il2CppClass*` est permanent, là où l'objet exception, lui, peut avoir été ramassé.
 */
export function pileGhidraFroide(ctx: CpuContext, max = 16): string[] {
    const out: string[] = [];
    let frames: NativePointer[] = [];
    try { frames = Thread.backtrace(ctx, Backtracer.FUZZY); } catch { return out; }
    for (const a of frames.slice(0, max)) {
        const delta = a.sub(il2cppBase);
        const dans = delta.compare(ptr(0)) >= 0 && delta.compare(ptr(il2cppSize)) < 0;
        out.push(dans ? ghidraVA(a) : "hors-image:" + a.toString());
    }
    return out;
}

/**
 * Booléen rendu par `invokeMethod`. **À N'OUBLIER SOUS AUCUN PRÉTEXTE.**
 *
 * `il2cpp_runtime_invoke` BOXE les retours de type valeur : le pointeur rendu désigne une boîte
 * managée, et le `Boolean` vit à `+0x10`. Lire `retour.toInt32()` lit les 32 bits BAS DU
 * POINTEUR — quasi jamais nuls — donc rend **`true` inconditionnellement**.
 *
 * Ce n'est pas une précaution théorique : c'est exactement la faute qui a fait répondre
 * `HasPrefabForUnitId = true` sur des unités ABSENTES du dictionnaire, réfuter à tort la bonne
 * cause, et faire dire à `deploymentPrefabCharger` « déjà présent -- rien fait » alors qu'il
 * n'avait rien créé. Un capteur qui ne peut rendre que `true` ne mesure rien.
 */
export function boolBoxe(p: NativePointer): boolean {
    if (p.isNull()) return false;
    return p.add(0x10).readU8() !== 0;
}

/** Taille d'instance. `il2cpp_class_instance_size` peut manquer de l'export : on LÈVE avec le
 *  nom plutôt que de cloner sur une taille devinée — un clone tronqué laisserait des champs à
 *  zéro sans la moindre erreur. */
export function taille(klass: NativePointer): number {
    if (class_instance_size === null) {
        throw new Error("`il2cpp_class_instance_size` absent de ce build : clonage IMPOSSIBLE");
    }
    return class_instance_size(klass) as number;
}

// --- LES NOMS NATIFS PARTAGES PAR LA FAMILLE ---------------------------------------
// Remontes ici le 2026-08-26 : `deployment-pool` en cite dix, et les lui laisser dans
// `deployment-draft` aurait ferme un cycle (draft importe pool).

export const NS_SRC = "IdunBattle.ViewLogic.BattleSource";

export const METHODE = "GetUnitsForDeploymentHUD";

// ============================================================================
// PHASE DE DÉPLOIEMENT (#10020-r1) — forcer une sandbox à passer par l'écran de
// déploiement au lieu de sauter directement en `Running`.
//
// LA CHAÎNE, mesurée le 2026-08-17 (`t6dpr4k06g`), décompilée puis confrontée sur les objets
// VIVANTS (cf. `docs/rl/case-10020-lien-vue-source-sens-unique.md` §7-§8) :
//
//   IdunBattle.View.Game.IdunGameViews$$Enable(this, skipUnitDeployment)
//       si skipUnitDeployment == 0 ET <slot 0x34>(this+0x138 = _visualBattleQuery) :
//              -> IdunBattle.View.FSM.UnitSelectionFsm$$UnitDeployment       (PHASE DE DEPLOIEMENT)
//       sinon  -> IdunBattle.View.FSM.UnitSelectionFsm$$StartMatch           (direct en jeu)
//
//   IdunBattle.View.FSM.VisualBattleQuery$$ShouldShowUnitDeploymentHud  =  relais PUR vers
//       <slot 0x29>(this+0x80 = _gameModeSource : IGameModeSource)
//
// Sur une sandbox les DEUX rendent `false` (invoqués sur les objets vivants), et le corps de
// `SandboxGameModeSource$$ShouldShowUnitDeployment` est un `return 0` **CONSTANT** : aucun réglage
// de BC ni de gameconfig ne le fera basculer. D'où ce hook.
//
// ⛔ POURQUOI ON N'ANCRE PAS LA SOURCE, ET POURQUOI C'EST LE POINT CENTRAL DE CE MODULE
// -------------------------------------------------------------------------------------
// `SandboxGameModeSource$$ShouldShowUnitDeployment` résout au runtime sur un corps que **~745
// `MethodInfo` PARTAGENT** (745 xrefs DATA + 122 appels directs ; Ghidra le nomme d'après une
// classe sans rapport, `Stash.Native.StashNative$$get_IsPurchaseProcessing`). IL2CPP déduplique les
// corps triviaux : `return 0` n'a pas d'identité. S'y attacher basculerait à `true` TOUT ce qui rend
// « faux constant » dans le jeu — sans erreur, sans symptôme qui désigne la cause.
//
// Le dépôt portait déjà « l'absence dans la table ne prouve RIEN » : c'était le versant LECTURE.
// Ici c'est le versant ÉCRITURE, et il ne rate pas une conclusion — il fait un dégât.
//
// ⇒ On ancre le RELAIS, un étage au-dessus : il a un VRAI corps, donc une adresse propre
// (2 xrefs DATA : son `MethodInfo` + son entrée de vtable).
//
// ET LE GARDE EST EXÉCUTABLE, PAS ÉCRIT — une prose n'arrête pas un comportement. `teteTriviale()`
// lit les premiers octets du corps résolu et REFUSE l'attache si un `ret` (0xC3) tombe dans les 8
// premiers : un corps qui rend une constante rette en 1 à 4 octets, un relais réel commence par sa
// garde de cctor et son test de nullité. Le refus PUBLIE les octets, pour qu'on juge sur pièce et
// pas sur un verdict.
//
// RÉGIMES — `forcer` est FAUX par défaut, donc armer n'écrit RIEN.
//   OBSERVER : on lit le `skipUnitDeployment` que le jeu passe à `Enable`, et ce que le relais rend.
//              C'est la seule base sur laquelle on saura si forcer a un sens.
//   FORCER   : `onLeave` remplace le retour du relais par `true`. `Interceptor.attach`, JAMAIS
//              `replace` (un stop de session avec un `replace` actif crashe le jeu).
//
// ⚠ `VisualBattleQuery` sert TOUS les modes, pas seulement la sandbox : forcer sans désarmer ferait
// apparaître une phase de déploiement là où le jeu n'en veut pas. D'où l'armement explicite.

export const NS_VBQ = "IdunBattle.View.FSM";

export const CLS_VBQ = "VisualBattleQuery";

export const METH_VBQ = "ShouldShowUnitDeploymentHud";

export const NS_VIEWS = "IdunBattle.View.Game";

export const CLS_VIEWS = "IdunGameViews";

export const CLS_SANDBOX = "SandboxGameModeSource";
