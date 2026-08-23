// source-vivante — QUELLE SOURCE DE MODE JOUE EN CE MOMENT.
//
// POURQUOI CE MODULE EXISTE, ET CE QU'IL RÉPARE.
// `getLiveBattleConfig` (battle-config.ts) cherchait la `BattleConfiguration` sur les sources
// CAPTURÉES — Pvp, MoW Event, Campaign — et n'a jamais connu `SandboxGameModeSource`. Mesuré le
// 2026-08-22 : avec un onslaught `Waves_Imperial_22` MONTÉ et tournant, `inspectBattleConfig`
// rendait `Campaign1_06` / board `C1_01`, c'est-à-dire la BC d'une source qui ne jouait plus.
//
// ⚠ LE DÉGÂT N'EST PAS L'ABSENCE DE RÉPONSE, C'EST LA RÉPONSE PLAUSIBLE. Une BC périmée porte un
// `Id` et un board parfaitement lisibles : rien ne signale qu'on regarde un objet mort. Une
// mutation appliquée là passe (`relu: true`), et n'a AUCUN effet — le moteur lit ailleurs. C'est
// exactement ce qui a fait conclure « muter la BC live ne marche pas » alors que la mutation
// visait le mauvais objet.
//
// Ce module ne fait qu'une chose : retenir la source passée à `StartMatch`, pour que les lecteurs
// de BC puissent la consulter AVANT les sources capturées. Il ne lit rien lui-même.

import { class_get_name, getFieldOffset, s } from "../il2cpp/helpers.js";
import { vueVivanteCourante } from "./retreat-capture.js";

/** La dernière source réellement passée à `ViewCommandExecutor$$StartMatch`. */
let derniereSource: NativePointer | null = null;
let derniereSourceClasse: string | null = null;

/** À appeler APRÈS un `StartMatch` réussi, avec la source qu'on lui a donnée. */
export function noterSourceMontee(src: NativePointer): void {
    if (src.isNull()) return;
    derniereSource = src;
    try { derniereSourceClasse = s(class_get_name(src.readPointer()) as NativePointer); }
    catch { derniereSourceClasse = null; }
}

/** Oublier la source — après une sortie de bataille, pour ne pas servir un pointeur mort. */
export function oublierSourceMontee(): void {
    derniereSource = null;
    derniereSourceClasse = null;
}

export function sourceMontee(): { ptr: NativePointer; classe: string | null } | null {
    if (derniereSource === null) return null;
    return { ptr: derniereSource, classe: derniereSourceClasse };
}

/** La `BattleConfiguration` de la source montée, ou `null`.
 *
 *  ⚠ L'OFFSET SE RÉSOUT PAR NOM, SUR LA CLASSE DE L'OBJET. Chaque source porte `_currentBattle`
 *  à un offset qui lui est propre (`battle-config.ts` en code trois en dur, un par source) ;
 *  appliquer celui d'une source à une autre lirait un champ voisin et rendrait un pointeur
 *  plausible. On résout donc sur la classe RÉELLE, et on rend `null` si le champ n'y est pas.
 *
 *  ⚠ AUCUN TYPE-GUARD ICI : c'est l'appelant qui vérifie que l'objet lu est bien une
 *  `BattleConfiguration`. Ce module ne connaît pas ce type et n'a pas à le connaître. */
/** La `BattleConfiguration` de la bataille RÉELLEMENT à l'écran — DÉCOUVERTE, pas mémorisée.
 *
 *  ⚠ SE SOUVENIR NE PEUT RIEN POUR UNE BATAILLE OUVERTE AVANT NOUS. `noterSourceMontee` n'est
 *  appelée qu'au montage d'un banc (`sandbox-mode.ts`, seul appelant) : une bataille RÉELLE, ou
 *  une bataille déjà en déploiement quand la session s'attache, ne l'informe JAMAIS. Pire,
 *  `oublierSourceMontee` n'est appelée nulle part — donc le pointeur survit à sa bataille et sert
 *  un objet mort avec aplomb.
 *
 *  ⚠ MESURÉ LE 2026-08-23, ET C'EST CE QUI A COÛTÉ LE DIAGNOSTIC. Un onslaught RÉEL en phase de
 *  déploiement : `getLiveBattleConfig` rendait `0x1707825c400`, la BC du banc sandbox de la
 *  veille — encore vivante, encore porteuse de sa mutation (sa liste d'enhancements est passée de
 *  1 à 2 quand on l'a repatchée, ce qu'une réutilisation d'adresse ne ferait pas). La vraie valait
 *  `0x17072f70a00`, confirmée par DEUX chemins concordants : `IdunMainView._currentBattle` et
 *  `IdunMainView.runner.<Configuration>k__BackingField`. Une mutation appliquée entre-temps rendait
 *  `relu: true` sans le moindre effet.
 *
 *  (!) LE RUNNER D'ABORD, LA VUE ENSUITE. C'est le runner qui JOUE la BC ; `_currentBattle` de la
 *  vue est le second témoin, gardé parce qu'il concorde et qu'il couvre le cas où le runner n'est
 *  pas encore posé. Les deux offsets se résolvent PAR NOM sur la classe réelle.
 *
 *  ⚠ AUCUN TYPE-GUARD ICI, comme pour `bcDeLaSourceMontee` : c'est l'appelant qui vérifie. */
export function bcDeLaVueVivante(): NativePointer | null {
    const vue = vueVivanteCourante();
    if (vue === null || vue.isNull()) return null;
    let klass: NativePointer;
    try { klass = vue.readPointer(); } catch { return null; }
    if (klass.isNull()) return null;

    const offRunner = getFieldOffset(klass, "runner");
    if (offRunner >= 0) {
        try {
            const runner = vue.add(offRunner).readPointer();
            if (!runner.isNull()) {
                const kRunner = runner.readPointer();
                if (!kRunner.isNull()) {
                    const offCfg = getFieldOffset(kRunner, "<Configuration>k__BackingField");
                    if (offCfg >= 0) {
                        const bc = runner.add(offCfg).readPointer();
                        if (!bc.isNull()) return bc;
                    }
                }
            }
        } catch { /* le runner n'est pas lisible : on tombe sur la vue */ }
    }
    for (const nom of ["_currentBattle", "_battleConfiguration"]) {
        const off = getFieldOffset(klass, nom);
        if (off < 0) continue;
        try {
            const bc = vue.add(off).readPointer();
            if (!bc.isNull()) return bc;
        } catch { /* champ illisible : on essaie l'écriture suivante */ }
    }
    return null;
}

export function bcDeLaSourceMontee(): NativePointer | null {
    if (derniereSource === null) return null;
    let klass: NativePointer;
    try { klass = derniereSource.readPointer(); } catch { return null; }
    if (klass.isNull()) return null;
    for (const nom of ["_currentBattle", "<CurrentBattle>k__BackingField", "CurrentBattle"]) {
        const off = getFieldOffset(klass, nom);
        if (off < 0) continue;
        try {
            const bc = derniereSource.add(off).readPointer();
            if (!bc.isNull()) return bc;
        } catch { /* champ illisible : on essaie l'écriture suivante */ }
    }
    return null;
}
