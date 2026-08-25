// LE HUD DE DEPLOIEMENT — les relais poses sur l'ecran : `Show`, la pose, la depose, le clear,
// les chemins de bascule heros/MoW, et le forcage du bouton START.
//
// Extrait de `deployment-draft.ts` le 2026-08-26. Frontiere mesuree : 45 symboles, 2 entrees.
// C'est le dernier gros etage : apres lui, `deployment-draft` ne garde que l'ebauche de roster,
// la phase de deploiement et le diagnostic de pose.
//
// ⚠ CE MODULE PORTE LE PIEGE DE NOMS DE LA SOIREE. `vidangeFires` / `listenerVidange` designent
// ICI les tirs de `ClearWidgets` -- PAS la vidange de la memoire a la retraite, qui vit dans
// `deployment-memoire` sous `vidangeRetraiteFires` / `listenerVidangeRetraite`. Les deux se
// ressemblent, un renommage global les a deja confondus, et ca COMPILE : `deploymentHudArmer`
// publiait alors le mauvais compteur et son desarmement detachait le mauvais listener.
//
// ⚠ LE CLEAR INVALIDE LA PHOTO DES PLACEHOLDERS (`viderLaPhotoDesPlaceholders`), et il doit le
// faire meme en regime OBSERVER -- d'ou sa place avant le `return` de `armerClear`. C'est un
// geste EN BLOC qui ne passe par aucun de nos deux points de photo.

import { Ctx } from "../controller.js";
import {
    findClassAnywhere, findMethodByParamCount, findMethod, getFieldOffset, readIl2cppString,
    class_get_name, s,
} from "../il2cpp/helpers.js";
import { invokeMethod, createManagedString } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { elementsDeListe, estRefus as estRefusLecture } from "./lecture-champs.js";
import {
    Refus, refus, lireTete, teteTriviale, ghidraVA, pileGhidra, NS_VIEWS, CLS_VIEWS,
} from "./deployment-socle.js";
import {
    hudInstance, assurerHud, compteDict, etatDuBouton, unitesDuPlateau, compteJoueur,
    marquerLesUnitesDuPlateau, idsDesUnitesDuJoueur, retirerDuRunner, apresImages,
    definirHudInstance, definirHudSource, dernierIdJoueurHumain, derniersCouples,
    NS_HUD, CLS_HUD, Pose, compterSurLePlateau,
} from "./deployment-plateau.js";
import {
    memoirePoses, memoireAuto, memoireRejeuArme, memoriser, rejouerMemoire, photographierPlaceholders,
    viderLaPhotoDesPlaceholders, definirMemoireRejeuArme, definirMemoireDernier, syncAuto,
    definirSyncDernier, memoireBataille, tracerPose, definirMemoireMoW,
    definirListenerMoW, listenerMoW,
} from "./deployment-memoire.js";
import { dicoVivant, NS_PREFAB, CLS_VIEWS_PREFAB, vuesDePose } from "./deployment-prefab.js";
import { classeDerriere } from "./deployment-pool.js";

export let listenerShow: InvocationListener | null = null;

export let listenerPose: InvocationListener | null = null;

export let listenerBoard: InvocationListener | null = null;

export let hudEtat: Record<string, unknown> | null = null;

// ⚠ LES CINQ APPELANTS DE `PrepareFor...` SONT TOUS LÀ, et c'est la leçon : la première liste
// n'en portait que trois, donc un tir de `PrepareFor...` restait SANS ORIGINE et rendait les
// compteurs mutuellement incompatibles. `PutUnitIntoHand` et `SetCurrentlySelectedUnit` sont les
// deux qui manquaient -- ce sont les chemins de SÉLECTION, pas ceux de la bascule de MODE.
export const CHEMINS_BASCULE = [
    "EmptyMachineOfWarPlatformTapped", "EmptySpawnPointTapped",
    "HandleOnSwitchToMachinesOfWarUnitsTapped", "HandleOnSwitchToStandardUnitsTapped",
    "ShowStandardUnitSelection", "PrepareForStandardUnitMachineOfWarSelectionSwitch",
    "PutUnitIntoHand", "SetCurrentlySelectedUnit", "RemoveUnit",
] as const;

export const cheminsListeners: Record<string, InvocationListener> = {};

export const cheminsEtat: Record<string, unknown> = {};

/**
 * Les chemins dont l'ARGUMENT porte une identité d'unité, et comment le lire.
 *
 * ⚠ POURQUOI L'ARGUMENT, ET PAS SEULEMENT LE COMPTEUR. Symptôme mesuré le 2026-08-19 : une
 * unité ôtée du plateau revient au roster et RESTE sur le plateau. La cause est structurelle —
 * le HUD ne connaît que des `PlaceholderUnitView`, nos unités sont RÉELLES sur le runner, et
 * le seul relais qui atteigne une unité réelle est celui du bouton « tout enlever »
 * (`HandleOnRemoveAllHeroesPressed`, cf. `armerClear`). La dépose unité par unité n'en a aucun.
 *
 * ⚠ RESTE À SAVOIR QUELLE MÉTHODE LA PORTE, ET LES COMPTEURS SEULS NE LE DISENT PAS :
 * `PutUnitIntoHand` a tiré 9 fois pour 4 poses acceptées, donc elle porte AUSSI la prise en
 * main depuis le roster — son nom le dit. Y accrocher un `RemoveUnitMessage` ferait disparaître
 * une unité au simple clic sur le roster. L'identité capturée ici est ce qui tranchera :
 * une dépose nomme l'unité DU PLATEAU, une prise en main nomme celle qu'on saisit.
 */
export const CHEMINS_ARG: Record<string, "chaine" | "unitConfigId"> = {
    PutUnitIntoHand: "chaine",
    RemoveUnit: "unitConfigId",
};

/**
 * Ce qu'on peut LIRE d'un `IdunBattle.Configuration.UnitConfigId`.
 *
 * C'est un type VALEUR de 48 octets (`classes.tsv`), donc passé PAR ADRESSE. On ne prétend PAS
 * en connaître la disposition : on rend les six mots, et pour chacun la chaîne IL2CPP qu'il
 * désigne s'il en désigne une. Les trois `.ctor` déclarent `pureId : System.String` en tête, ce
 * qui fait du premier mot le candidat — mais c'est la LECTURE qui le dira, pas ce commentaire.
 *
 * `readIl2cppString` borne la longueur et avale ses propres accès invalides : le passer sur un
 * mot qui n'est pas une chaîne rend `null`, jamais une lecture sauvage.
 */
export function lireUnitConfigId(p: NativePointer): Record<string, unknown> {
    if (p.isNull()) return { nul: true };
    const mots: Array<{ i: number; hex: string; chaine: string | null }> = [];
    for (let i = 0; i < 6; i++) {
        try {
            const m = p.add(i * 8).readPointer();
            mots.push({ i, hex: m.toString(), chaine: readIl2cppString(m) });
        } catch { mots.push({ i, hex: "ILLISIBLE", chaine: null }); }
    }
    const porteur = mots.find((m) => m.chaine !== null);
    return { unitId: porteur ? porteur.chaine : null,
             motPorteur: porteur ? porteur.i : null, mots };
}

/**
 * L'ÉTAT VIVANT DE LA BASCULE HÉROS <-> MACHINES OF WAR.
 *
 * ⚠ L'instantané de `Show` NE SUFFIT PAS : ces trois champs bougent à chaque clic sur un point
 * de spawn, longtemps après le dernier `Show`. Symptôme qui l'a exigé (2026-08-19) : cliquer un
 * emplacement MoW bascule bien le roster, cliquer ensuite un spawn héros ne le ramène PAS.
 *
 * Le décompilé nomme les deux causes possibles, et elles sont indiscernables à l'écran :
 *   `UnitDeploymentHud$$EmptySpawnPointTapped` ne fait RIEN si `_isMachinesOfWarSelection` est
 *   déjà faux ; et `ShowStandardUnitSelection` LÈVE si `_units` est nul (le clic paraît alors
 *   sans effet, l'exception étant avalée par la boucle d'évènements Unity).
 *
 * Résolus PAR NOM, et l'offset est CONFRONTÉ à celui du décompilé — un renommage se signale au
 * lieu d'être subi.
 */
export function etatBasculeHud(): Record<string, unknown> | null {
    if (hudInstance === null || hudInstance.isNull()) return null;
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    if (!k) return { erreur: `classe \`${NS_HUD}.${CLS_HUD}\` introuvable` };
    const champs: Array<{ nom: string; attendu: number; type: "bool" | "liste" }> = [
        { nom: "_isMachinesOfWarSelection", attendu: 0x221, type: "bool" },
        { nom: "_hasMachinesOfWar", attendu: 0x222, type: "bool" },
        { nom: "_units", attendu: 0x230, type: "liste" },
    ];
    const out: Record<string, unknown> = {};
    for (const c of champs) {
        const off = getFieldOffset(k, c.nom);
        if (off < 0) { out[c.nom] = { absent: true }; continue; }
        try {
            if (c.type === "bool") {
                out[c.nom] = { valeur: hudInstance.add(off).readU8() !== 0,
                               offset: off, attendu: c.attendu, concorde: off === c.attendu };
            } else {
                const l = hudInstance.add(off).readPointer();
                out[c.nom] = { nul: l.isNull(), taille: l.isNull() ? null : l.add(0x18).readS32(),
                               offset: off, attendu: c.attendu, concorde: off === c.attendu };
            }
        } catch (e) { out[c.nom] = { erreur: (e as Error).message }; }
    }
    return out;
}

export const hudPoses: Array<{ unitId: string | null; mow: boolean; accepte: boolean }> = [];

// ⚠ L'ÉTAGE QUI POSE VRAIMENT. `TryMarkUnitAsPlaced` n'est que la comptabilité du roster —
// mesuré : il rend `true` (l'unité se grise) alors que le plateau ne bouge pas.
// `StateMachineActions$$UnitDeployment_PlaceUnitOnBoard` interroge le HUD puis délègue à un
// SECOND étage ; c'est celui-là qu'il faut voir.
export const hudBoard: Array<{
    unitId: string | null; col: number; row: number; manuel: boolean; playerId: number;
    retour: number;
}> = [];

export function armerHud(): true | Refus {
    if (listenerShow && listenerPose) return true;
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    if (!k) return refus(`\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE sur ce build`);
    const miShow = findMethodByParamCount(k, "Show", 4);
    const miPose = findMethodByParamCount(k, "TryMarkUnitAsPlaced", 2);
    if (!miShow) return refus("`UnitDeploymentHud$$Show` INTROUVABLE (4 paramètres)");
    if (!miPose) {
        return refus("`UnitDeploymentHud$$TryMarkUnitAsPlaced` INTROUVABLE (2 paramètres)");
    }
    for (const [nom, mi] of [["Show", miShow], ["TryMarkUnitAsPlaced", miPose]] as const) {
        const t = lireTete(mi.ptr);
        if (t.erreur !== null) return refus(`tête de \`${nom}\` ILLISIBLE (${t.erreur})`);
        if (teteTriviale(t)) {
            return refus(`REFUS : \`${CLS_HUD}$$${nom}\` résout sur un corps TRIVIAL `
                + `(ret à l'octet ${t.retA}) -- adresse probablement PARTAGÉE. Cf. §8.`);
        }
    }
    const offTous = getFieldOffset(k, "_allUnitModels");
    const offDebl = getFieldOffset(k, "_allUnlockedUnitModels");
    const offInput = getFieldOffset(k, "_disabledInput");
    if (offTous < 0 || offDebl < 0) {
        return refus("champ(s) absent(s) de `UnitDeploymentHud` sur ce build : "
            + `_allUnitModels=${offTous} _allUnlockedUnitModels=${offDebl} `
            + "-- chemin PÉRIMÉ, pas de repli sur un offset");
    }
    if (!listenerShow) {
        listenerShow = Interceptor.attach(miShow.ptr, {
            onEnter(args) {
                // `Show` remplit les dictionnaires : on lit APRÈS, pas avant.
                (this as unknown as { hud: NativePointer; mn: number; mx: number }).hud = args[0];
                definirHudInstance(args[0]);
                definirHudSource("Show");     // l'autorité : celui que le jeu vient d'afficher
                // ⚠ COMPTER LES ENTRÉES, PAS SEULEMENT LES SORTIES. `Show` VIDE les trois
                // dictionnaires en tête (`ClearWidgets`) et ne les remplit qu'à la fin : un
                // `Show` qui lève entre les deux laisse l'écran avec 0 modèle, et le compteur
                // de SORTIE, lui, ne bouge pas -- on croit alors qu'un seul `Show` a eu lieu et
                // qu'il s'est bien passé. `entrees > sorties` EST la signature de ce cas.
                showEnters++;
                dansShow = true;
                (this as unknown as { mn: number }).mn = args[2].toInt32();
                (this as unknown as { mx: number }).mx = args[3].toInt32();
            },
            onLeave() {
                const self = this as unknown as { hud: NativePointer; mn: number; mx: number };
                dansShow = false;
                try {
                    hudEtat = {
                        hud: self.hud.toString(),
                        minUnitsPossible: self.mn, maxUnitsPossible: self.mx,
                        allUnitModels: compteDict(self.hud.add(offTous).readPointer()),
                        allUnlockedUnitModels: compteDict(self.hud.add(offDebl).readPointer()),
                        // ⚠ LE POINTEUR, PAS SEULEMENT LE COMPTE. Un dictionnaire qui retombe à
                        // zéro peut avoir été VIDÉ (`Clear`) ou REMPLACÉ (le champ réaffecté à
                        // un objet neuf). Les deux se lisent « 0 » et appellent des enquêtes
                        // opposées ; seule l'identité de l'objet les sépare.
                        allUnitModelsPtr: self.hud.add(offTous).readPointer().toString(),
                        allUnlockedUnitModelsPtr: self.hud.add(offDebl).readPointer().toString(),
                        disabledInput: offInput < 0
                            ? null : self.hud.add(offInput).readU8() !== 0,
                    };
                } catch (e) { hudEtat = { erreur: (e as Error).message }; }
                // Le TÉMOIN D'ORDRE du capteur `StartMatch` : compter les affichages du HUD
                // suffit à dire si `StartMatch` a tiré AVANT (donc au montage) ou APRÈS (donc
                // au clic). Pas d'horloge à interpréter, pas de natif invoqué.
                showFires++;
                // ⛔ ON N'INVOQUE RIEN ICI — on ENFILE. Sans ce cran, une BC pré-remplie affiche
                // un START gris : le HUD ne compte que ce que LUI a posé, et `UpdateButtons`
                // n'a aucun appelant après le montage dans ce régime.
                if (syncAuto) planifierSync(6);
                // ⛔ ON N'INVOQUE RIEN ICI NON PLUS : `rejouerMemoire` ENFILE. C'est le retour
                // de la phase de déploiement (retry) qui doit rendre l'équipe déjà composée.
                //
                // ⛔ ET LE JETON EST EXIGÉ, PAS SEULEMENT `memoireAuto`. Ce `Show` tire sur TOUT
                // écran de déploiement -- y compris celui d'une bataille RÉELLE que le joueur
                // vient d'ouvrir lui-même. Mesuré le 2026-08-22 sur un combat officiel contre le
                // boss : la composition d'une sandbox précédente s'y est reposée toute seule.
                // `memoireRejeuArme` n'est posé que par `sandboxModeBcOverride`, donc une
                // bataille qu'on n'a pas montée ne peut plus rien déclencher.
                if (memoireAuto && memoireRejeuArme) {
                    definirMemoireRejeuArme(false);  // USAGE UNIQUE -- consommé avant de tirer
                    rejouerMemoire();
                } else if (memoireAuto) {
                    definirMemoireDernier("rejeu REFUSÉ : aucun jeton -- cette bataille n'a "
                        + `pas été montée par la sandbox (mémoire de ${memoireBataille ?? "aucune"})`);
                }
            },
        });
    }
    if (!listenerPose) {
        listenerPose = Interceptor.attach(miPose.ptr, {
            onEnter(args) {
                const self = this as unknown as { uid: string | null; mow: boolean };
                self.uid = null;
                try { self.uid = readIl2cppString(args[1]); } catch { /* best effort */ }
                self.mow = args[2].toInt32() !== 0;
            },
            onLeave(retval) {
                const self = this as unknown as { uid: string | null; mow: boolean };
                if (hudPoses.length < 32) {
                    hudPoses.push({ unitId: self.uid, mow: self.mow,
                                    accepte: (retval.toInt32() & 0xff) !== 0 });
                }
                // Ce chemin porte AUSSI la reprise en main (cf. §`PutUnitIntoHand`) : c'est donc
                // le seul endroit où un RETRAIT se voit. Sans photo ici, ôter une unité juste
                // avant de retraiter commiterait une composition qui la contient encore.
                photographierPlaceholders();
            },
        });
    }
    if (!listenerMoW) {
        // LE PENDANT MoW de `UnitDeployment_PlaceUnitOnBoard`. Même étage, autre signature :
        // pas de colonne/ligne, mais une `MachineOfWarPosition`.
        const kam = findClassAnywhere("IdunBattle.View.FSM", "StateMachineActions");
        const mm = kam
            ? findMethodByParamCount(kam, "UnitDeployment_PlaceMachineOfWarUnitOnBoard", 4)
            : null;
        if (mm && !mm.ptr.isNull()) {
            const tm = lireTete(mm.ptr);
            if (tm.erreur === null && !teteTriviale(tm)) {
                definirListenerMoW(Interceptor.attach(mm.ptr, {
                    onEnter(args) {
                        try {
                            const uid = readIl2cppString(args[1]);
                            if (uid === null || uid === "") return;
                            // args[2]=isManual, args[3]=playerId, args[4]=position
                            definirMemoireMoW({ unitId: uid, playerId: args[3].toInt32(),
                                                position: args[4].toInt32() });
                        } catch { /* best effort : la mémoire MoW reste ce qu'elle était */ }
                    },
                }));
            }
        }
    }
    if (!listenerBoard) {
        const ka = findClassAnywhere("IdunBattle.View.FSM", "StateMachineActions");
        if (!ka) return refus("`IdunBattle.View.FSM.StateMachineActions` INTROUVABLE");
        const mb = findMethodByParamCount(ka, "UnitDeployment_PlaceUnitOnBoard", 5);
        if (!mb) {
            return refus("`StateMachineActions$$UnitDeployment_PlaceUnitOnBoard` INTROUVABLE "
                + "(5 paramètres)");
        }
        const tb = lireTete(mb.ptr);
        if (tb.erreur !== null) return refus(`tête de \`PlaceUnitOnBoard\` ILLISIBLE`);
        if (teteTriviale(tb)) {
            return refus("REFUS : `UnitDeployment_PlaceUnitOnBoard` résout sur un corps "
                + `TRIVIAL (ret à l'octet ${tb.retA}) -- adresse PARTAGÉE. Cf. §8.`);
        }
        listenerBoard = Interceptor.attach(mb.ptr, {
            onEnter(args) {
                const self = this as unknown as {
                    uid: string | null; c: number; r: number; m: boolean; p: number;
                };
                self.uid = null;
                try { self.uid = readIl2cppString(args[1]); } catch { /* best effort */ }
                self.c = args[2].toInt32();
                self.r = args[3].toInt32();
                self.m = (args[4].toInt32() & 0xff) !== 0;
                self.p = args[5].toInt32();
            },
            onLeave(retval) {
                const self = this as unknown as {
                    uid: string | null; c: number; r: number; m: boolean; p: number;
                };
                if (hudBoard.length < 32) {
                    hudBoard.push({ unitId: self.uid, col: self.c, row: self.r,
                                    manuel: self.m, playerId: self.p,
                                    retour: retval.toInt32() & 0xff });
                }
                // ⛔ ON N'INVOQUE RIEN ICI — on ENFILE. Sans ce cran, la pose ne produit qu'un
                // `PlaceholderUnitView` que rien ne convertit en sandbox : START démarre une
                // bataille sans unité du joueur, qui se termine aussitôt.
                //
                // ⚠ Le retour n'est PAS un critère : mesuré, `AddPlaceholderUnit` rend `0`
                // AUSSI en succès (sa dernière instruction est une émission d'événement). On
                // enfile donc sur la pose, et c'est la RELECTURE DU PLATEAU qui tranche.
                //
                // (!)LE COMMIT AUTOMATIQUE QUI VIVAIT ICI EST SUPPRIMÉ. Il appliquait un
                // `AddUnitMessage` au runner À CHAQUE POSE, en plus du placeholder que le HUD
                // venait de créer : deux comptabilités pour un seul plafond, et le START
                // convertissait les placeholders PAR-DESSUS les unités réelles.
                photographierPlaceholders();
            },
        });
    }
    // ⚠ LES CHEMINS DE LA BASCULE HÉROS <-> MoW, COMPTÉS -- parce qu'un état AU REPOS ne
    // distingue pas « l'aller-retour a eu lieu » de « rien n'a bougé ». Mesuré le 2026-08-19 :
    // après un clic MoW puis un clic spawn héros, `_isMachinesOfWarSelection` valait `false`,
    // ce qui est AUSSI sa valeur initiale -- la lecture au repos ne prouvait donc rien. On
    // compte les tirs et on relève le drapeau À L'ENTRÉE et À LA SORTIE : c'est la TRANSITION
    // qui est le fait.
    armerChemins(k);
    // ⛔ OBSERVATION PURE sur `ClearWidgets`. On relève les trois comptes AVANT et APRÈS, et
    // l'état des compteurs de `Show` au moment du tir : c'est ce triplet qui NOMME l'appelant
    // sans avoir à lire une pile (`Show` incrémente `showEnters` à l'entrée, donc un tir de
    // `ClearWidgets` avec `showEnters` inchangé depuis le tir précédent vient de l'AUTRE
    // appelant, `IdunMainView$$EndBattleAndGoToMeta`).
    if (!listenerVidange) {
        const mClear = findMethodByParamCount(k, "ClearWidgets", 0);
        if (mClear && !mClear.ptr.isNull()) {
            const offTous2 = getFieldOffset(k, "_allUnitModels");
            const offPl2 = getFieldOffset(k, "_currentlyPlacedUnits");
            const lire = (hud: NativePointer): Record<string, unknown> => {
                const o: Record<string, unknown> = {};
                try { o.allUnitModels = compteDict(hud.add(offTous2).readPointer()); }
                catch { o.allUnitModels = null; }
                try {
                    const l = hud.add(offPl2).readPointer();
                    o.placees = l.isNull() ? null
                        : l.add(getFieldOffset(l.readPointer(), "_size")).readS32();
                } catch { o.placees = null; }
                return o;
            };
            listenerVidange = Interceptor.attach(mClear.ptr, {
                onEnter(args) {
                    const s = this as unknown as { hud: NativePointer; av: unknown; se: number };
                    s.hud = args[0];
                    s.se = showEnters;
                    s.av = offTous2 >= 0 && offPl2 >= 0 ? lire(args[0]) : null;
                },
                onLeave() {
                    const s = this as unknown as { hud: NativePointer; av: unknown; se: number };
                    vidangeFires++;
                    if (vidangeTrace.length < 24) {
                        vidangeTrace.push({
                            n: vidangeFires, avant: s.av,
                            apres: offTous2 >= 0 && offPl2 >= 0 ? lire(s.hud) : null,
                            showEntersAuTir: s.se, showFiresAuTir: showFires,
                            // EXACT, et pas une soustraction de compteurs : `Show` lève ce
                            // drapeau à son entrée et le baisse à sa sortie, sur le MÊME thread.
                            appelant: dansShow ? "UnitDeploymentHud$$Show"
                                : "IdunMainView$$EndBattleAndGoToMeta (seul autre appelant)",
                        });
                    }
                },
            });
        }
    }
    Interceptor.flush();
    return true;
}

/**
 * ANCRER LES CHEMINS DE BASCULE — sorti d'`armerHud` pour être RÉVERSIBLE NOMMÉMENT.
 *
 * ⚠ POURQUOI CE DÉCOUPAGE EXISTE. `deploymentHudArmer {armer:false}` ne détachait que
 * `Show`/`TryMarkUnitAsPlaced`/`AddPlaceholderUnit` : les neuf ancrages ci-dessous SURVIVAIENT à
 * tout désarmement, sans qu'aucun RPC ne puisse les ôter. Or `deploymentMowBasculer` INVOQUE
 * `HandleOnSwitchToMachinesOfWarUnitsTapped`, qui est dans la liste — on ancre donc la méthode
 * qu'on appelle, et le décompilé nomme deux autres ancrés dans sa descendance
 * (`PrepareForStandardUnitMachineOfWarSelectionSwitch`, `ShowStandardUnitSelection`). Tant que le
 * robinet manquait, « l'ancrage est-il la cause ? » n'était pas une question MESURABLE.
 */
export function armerChemins(k: NativePointer, seulement?: readonly string[]): string[] {
    const faits: string[] = [];
    for (const nom of CHEMINS_BASCULE) {
        if (seulement !== undefined && !seulement.includes(nom)) continue;
        if (cheminsListeners[nom] !== undefined) continue;
        const mi = findMethod(k, nom);
        if (!mi || mi.ptr.isNull()) { cheminsEtat[nom] = { introuvable: true }; continue; }
        // ⚠ ON PUBLIE LA VA, ET CE N'EST PAS DÉCORATIF. Mesuré le 2026-08-19 : trois compteurs
        // MUTUELLEMENT INCOMPATIBLES (`PrepareFor...` à 1 tir alors que ses DEUX seuls appelants
        // étaient l'un à 0 et l'autre sous une garde fausse). Un ancrage peut tomber sur un corps
        // DÉDUPLIQUÉ ou sur une surcharge voisine ; sans l'adresse, on croit le compteur et on
        // conclut à l'envers. La tête est contrôlée pour la même raison (cf. §8).
        const t = lireTete(mi.ptr);
        cheminsEtat[nom] = { fires: 0, transitions: [], args: [], va: ghidraVA(mi.ptr),
                             teteTriviale: t.erreur === null ? teteTriviale(t) : null,
                             teteErreur: t.erreur };
        const genreArg = CHEMINS_ARG[nom];
        cheminsListeners[nom] = Interceptor.attach(mi.ptr, {
            onEnter(args) {
                const s = this as unknown as {
                    av: boolean | null; hud: NativePointer; arg: unknown;
                };
                s.hud = args[0];
                s.av = lireDrapeauMoW(args[0]);
                // ⛔ LECTURE DE MÉMOIRE SEULEMENT, jamais une invocation. C'est la leçon des
                // deux gels : appeler un natif depuis un callback d'interception fige le jeu.
                s.arg = undefined;
                if (genreArg !== undefined) {
                    try {
                        s.arg = genreArg === "chaine"
                            ? readIl2cppString(args[1])
                            : lireUnitConfigId(args[1]);
                    } catch (e) { s.arg = { erreur: (e as Error).message }; }
                }
            },
            onLeave() {
                const s = this as unknown as {
                    av: boolean | null; hud: NativePointer; arg: unknown;
                };
                const e = cheminsEtat[nom] as {
                    fires: number; transitions: unknown[]; args: unknown[];
                };
                e.fires++;
                if (e.transitions.length < 16) {
                    e.transitions.push({ avant: s.av, apres: lireDrapeauMoW(s.hud) });
                }
                if (s.arg !== undefined && e.args.length < 16) e.args.push(s.arg);
                // LE RELAIS DE DÉPOSE. Il vit ICI et pas sur un ancrage à lui : le chemin est
                // le même que celui qu'on observe, et en poser deux sur une seule méthode ne
                // ferait qu'ajouter un ordre de tir à raisonner.
                if (deposeAuto && nom === "PutUnitIntoHand"
                    && typeof s.arg === "string" && s.arg !== "") {
                    retirerSiSurLePlateau(s.arg);
                }
            },
        });
        faits.push(nom);
    }
    return faits;
}

/** Détacher les chemins de bascule -- tous, ou seulement ceux nommés. Rend les noms ÔTÉS. */
export function desarmerChemins(seulement?: readonly string[]): string[] {
    const faits: string[] = [];
    for (const nom of Object.keys(cheminsListeners)) {
        if (seulement !== undefined && !seulement.includes(nom)) continue;
        cheminsListeners[nom].detach();
        delete cheminsListeners[nom];
        faits.push(nom);
    }
    if (faits.length > 0) Interceptor.flush();
    return faits;
}

/** Le drapeau `_isMachinesOfWarSelection` d'une instance de HUD, ou `null` s'il est illisible. */
export function lireDrapeauMoW(hud: NativePointer): boolean | null {
    try {
        const k = findClassAnywhere(NS_HUD, CLS_HUD);
        if (!k) return null;
        const off = getFieldOffset(k, "_isMachinesOfWarSelection");
        if (off < 0) return null;
        return hud.add(off).readU8() !== 0;
    } catch { return null; }
}

// --- CAPTEUR PUR sur `IdunBattle.Runner.IdunRunner$$StartMatch` -------------------------------
// Deux questions d'un coup, et AUCUNE écriture :
//   QUAND  -- `showsAvant` compte les affichages du HUD de déploiement déjà survenus. Tirer à
//             `showsAvant == 0` = au MONTAGE ; à `showsAvant >= 1` = APRÈS l'écran, donc au clic.
//             Un compteur d'ordre répond mieux qu'une horloge : rien à interpréter.
//   SUR QUI -- `runner` est le `this` de l'appel, comparé au runner publié par le pump. Égaux
//             ⇒ UN SEUL runner (chargé puis démarré). Différents ⇒ il y en a bien deux.
export let showFires = 0;

export let showEnters = 0;

/** Les tirs de `ClearWidgets` — LE seul vidangeur de `_allUnitModels` et de `_currentlyPlacedUnits`.
 *  Deux appelants au binaire : `UnitDeploymentHud$$Show` (en tête, avant son remplissage) et
 *  `IdunMainView$$EndBattleAndGoToMeta`. Compter les tirs et les confronter aux entrées de `Show`
 *  DÉSIGNE lequel a vidé : un tir sans entrée de `Show` vient de la sortie de bataille. */
export let vidangeFires = 0;

export const vidangeTrace: Array<Record<string, unknown>> = [];

export let listenerVidange: InvocationListener | null = null;

/** L'ancrage sur `Dictionary.Clear`, armé À LA DEMANDE et filtré par pointeur (cf.
 *  `deploymentVidangeArmer`). Les cibles sont relevées à l'armement : ce sont les dictionnaires
 *  VIVANTS du HUD, pas des offsets — si l'un est remplacé par un autre objet, il sort du filtre,
 *  et c'est un RÉSULTAT (le vidage serait alors une RÉAFFECTATION de champ, pas un `Clear`). */
export let listenerDictClear: InvocationListener | null = null;

export const ciblesVidange: Array<{ nom: string; ptr: NativePointer }> = [];

export const dictClearTrace: Array<Record<string, unknown>> = [];

/** `true` entre l'entrée et la sortie de `Show`. Même thread, donc c'est EXACT — là où une
 *  soustraction de compteurs ne l'est pas (un `Show` qui lève ne sort jamais). */
export let dansShow = false;

// ============================================================================
// LE BOUTON START — pourquoi il reste GRIS quand les unités sont PRÉ-POSITIONNÉES.
//
// `idun.ui.UnitDeploymentHud$$UpdateButtons` compte les unités de `_currentlyPlacedUnits`
// (+0x1b8) et relaie à `idun.ui.UnitDeploymentHudButtons$$UpdateState(gameMode, count, mowCount,
// min, max)`, dont le corps décide :
//
//     count <  min  ->  Animator.SetInteger(<etat>, 0)   // BOUTON DÉSACTIVÉ
//     count >= max  ->  ... SetInteger(<etat>, 2)        // plein
//     sinon         ->  ... SetInteger(<etat>, 1)        // actif
//
// ⚠ MESURÉ : la comptabilité du HUD et la composition RÉELLE de la bataille sont DEUX choses
// SÉPARÉES, et en sandbox aucune ne nourrit l'autre. Déclarer les unités dans `bc.Units` les
// fait bien APPARAÎTRE sur le plateau, mais `_currentlyPlacedUnits` reste VIDE — donc
// `count = 0 < min` et le bouton est gris. Symétriquement, les poser par le HUD active le
// bouton mais ne crée que des `PlaceholderUnitView`.
//
// On force donc le COMPTE que le relais reçoit, pas la liste : c'est le même patron que le
// forçage de phase et celui des bornes, tous deux éprouvés. Défaut = le `min` que le relais
// reçoit lui-même, pour rendre le bouton ACTIF sans le déclarer PLEIN.

export const NS_BOUTONS = "idun.ui";

export const CLS_BOUTONS = "UnitDeploymentHudButtons";

export let listenerBouton: InvocationListener | null = null;

export let boutonImpose: number | null = null;

export let boutonFires = 0;

/** Le compte dérivé du plateau, calculé HORS hook puis mis en cache. `null` = jamais calculé —
 *  ce qui n'est PAS zéro : le relais laisse alors passer ce que le HUD croit. */
export let compteCache: number | null = null;

export let compteCacheDetail: Record<string, number | string> | null = null;

export const boutonObs: Array<{
    recu: number; impose: number; min: number; max: number;
    source: string; plateau: Record<string, number | string>;
}> = [];

/**
 * L'inventaire des unités RÉELLEMENT présentes sur le plateau, une entrée par vue.
 *
 * ⚠ LE JOUEUR SE DEMANDE PAR `FirstPlayerEntityIdOfHumanOnThisDevice`, PAS PAR
 * `get_CurrentPlayerEntityId` : le second désigne le joueur DU TOUR COURANT, et pendant le
 * déploiement il ne désigne pas le propriétaire de l'appareil. Mesuré : le premier apparie 5
 * unités sur 8, le second en appariait **0**.
 *
 * ⚠ TROIS NUMÉROTATIONS COEXISTENT sur une vue, et les confondre ne lève RIEN — on les publie
 * donc toutes les trois plutôt que d'en élire une (c'est ainsi qu'on a vu que le `playerId 11`
 * de l'écran était JUSTE, après l'avoir soupçonné à tort).
 */








export let listenerClear: InvocationListener | null = null;

export let clearAuto = false;

export let clearFires = 0;

export let clearDernier: unknown = null;

/** Relais sur le clear natif. Il LAISSE le corps natif faire son travail (vider
 *  `_currentlyPlacedUnits`, ôter les placeholders) et ENFILE le retrait des unités RÉELLES. */
export function armerClear(): true | Refus {
    if (listenerClear) return true;
    const k = findClassAnywhere(NS_HUD, CLS_HUD);
    const mi = k ? findMethodByParamCount(k, "HandleOnRemoveAllHeroesPressed", 0) : null;
    if (!mi) {
        return refus("`UnitDeploymentHud$$HandleOnRemoveAllHeroesPressed` INTROUVABLE "
            + "(0 paramètre)");
    }
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête du clear ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus("REFUS : `UnitDeploymentHud$$HandleOnRemoveAllHeroesPressed` résout sur un "
            + `corps TRIVIAL (ret à l'octet ${t.retA}) -- adresse probablement PARTAGÉE`);
    }
    listenerClear = Interceptor.attach(mi.ptr, {
        onLeave() {
            clearFires++;
            // ⛔ LE CLEAR INVALIDE LA PHOTO, ET IL DOIT LE FAIRE MÊME EN RÉGIME OBSERVER --
            // d'où sa place AVANT le `return` ci-dessous.
            //
            // C'est un geste EN BLOC : il ne passe pas par `PutUnitIntoHand`, donc aucun de nos
            // deux points de photo ne le voit. Sans cette ligne, vider le plateau puis retraiter
            // commiterait la composition qu'on vient précisément d'effacer -- l'inverse exact du
            // geste du joueur, écrit sans que rien ne le signale.
            //
            // ⚠ ON POSE `[]`, ON NE RELIT PAS. Le retrait ne se voit pas dans la frame de l'appel
            // (même décalage que la pose, cf. l'en-tête du raccourci) : une relecture ici rendrait
            // le plateau ENCORE PLEIN et réécrirait la mauvaise photo. `[]` = « mesuré, et vide »,
            // ce qui est exactement ce que le joueur vient de dire. Une pose ultérieure
            // re-photographie, donc rien n'est perdu.
            viderLaPhotoDesPlaceholders();
            if (!clearAuto) return;
            // ⛔ CE CALLBACK N'INVOQUE RIEN, ET C'EST LA LEÇON DE DEUX GELS. Il ne fait
            // qu'ENFILER : la file est drainée par le pump, sur le thread principal, hors de
            // toute interception. Invoquer ici gèle le jeu.
            queueOnMainThread(() => retirerDuRunner(null)).then(
                (r) => { clearDernier = r; },
                (e) => { clearDernier = { ok: false, error: String(e) }; });
        },
    });
    return true;
}

export let deposeAuto = false;

export let deposeDernier: unknown = null;

export const deposeTrace: unknown[] = [];

/**
 * LA DÉPOSE UNITÉ PAR UNITÉ — le pendant du relais de CLEAR, sur un seul héros.
 *
 * ⚠ LE CHEMIN A ÉTÉ MESURÉ, PAS DEVINÉ, et la première hypothèse était FAUSSE.
 * `UnitDeploymentHud$$RemoveUnit(unitConfigId)` porte le nom qu'il faut et ne tire JAMAIS
 * (0 tir sur un cycle complet pose + dépose, ancrage contrôlé : VA `0x180e2f220`, tête non
 * triviale). C'est `PutUnitIntoHand(unitId)` qui porte les DEUX gestes — mesuré 2 tirs pour
 * 1 pose acceptée, avec le MÊME argument (`worldKharn`) les deux fois.
 *
 * ⇒ L'ARGUMENT NE DISCRIMINE PAS. Ce qui discrimine est l'ÉTAT DU PLATEAU : si l'unité nommée
 * y est déjà, le tir est une DÉPOSE (elle revient en main) ; sinon c'est une SAISIE depuis le
 * roster, et il n'y a rien à retirer. Le no-op est donc le comportement CORRECT dans un cas
 * sur deux — il est tracé pour qu'on ne le confonde pas avec un raté.
 *
 * ⛔ ON N'INVOQUE RIEN DEPUIS LE CALLBACK : on ENFILE. La décision elle-même (relire le
 * plateau, résoudre l'entité) se prend sur la file du thread principal, hors de toute
 * interception — c'est la leçon des deux gels, et c'est exactement ce que fait `armerClear`.
 * Le plateau lu en différé reste valable : tout le défaut est que le natif ne le touche pas.
 */
export function retirerSiSurLePlateau(unitId: string): void {
    queueOnMainThread(() => {
        const u = unitesDuPlateau();
        if (!Array.isArray(u)) {
            return { ok: false, unitId, error: "plateau non lisible : " + String(u) };
        }
        const cible = u.find((x) => x.duJoueur && x.unitId === unitId);
        if (!cible) {
            return { ok: true, unitId, action: "aucune",
                     raison: "pas sur le plateau -- c'est une SAISIE, pas une dépose" };
        }
        return { ok: true, unitId, action: "retire", entityId: cible.entityId,
                 retrait: retirerDuRunner([cible.entityId]) };
    }).then(
        (r) => { deposeDernier = r; if (deposeTrace.length < 16) deposeTrace.push(r); },
        (e) => { deposeDernier = { ok: false, unitId, error: String(e) }; });
}

/** Enfile la synchronisation HUD, avec un nombre BORNÉ de reprises : quand `Show` tire, le
 *  plateau peut n'être pas encore peuplé, et un unique essai rendrait « 0 marquée » sans que
 *  rien soit en défaut. */
export function planifierSync(reste: number): void {
    queueOnMainThread(() => marquerLesUnitesDuPlateau()).then((r) => {
        definirSyncDernier(r);
        const n = (r as { marquees?: number }).marquees ?? 0;
        if (n === 0 && reste > 0) planifierSync(reste - 1);
    }, (e) => { definirSyncDernier({ ok: false, error: String(e) }); });
}

/** Deuxième temps : le plateau a-t-il VRAIMENT grossi ? Tant que non, on repasse — l'ajout
 *  transite par le flux de bataille et ne se voit pas dans la frame de l'`Apply` (mesuré sur le
 *  retrait : instantané à 5, réel à 4 une seconde plus tard). */
export function verifierPuisNettoyer(p: Pose, avant: number | null, reste: number): void {
    queueOnMainThread((): Record<string, unknown> => {
        const apres = compteJoueur();
        if (avant !== null && apres !== null && apres > avant) {
            // L'unité est RÉELLE : le placeholder ferait doublon à l'écran.
            const kv = findClassAnywhere(NS_PREFAB, CLS_VIEWS_PREFAB);
            const mRem = kv ? findMethodByParamCount(kv, "RemovePlaceholderUnit", 1) : null;
            let ote: boolean | string = "`IdunGameViews$$RemovePlaceholderUnit` INTROUVABLE";
            if (mRem && vuesDePose !== null && !vuesDePose.isNull()) {
                try {
                    invokeMethod(mRem.info, vuesDePose, [createManagedString(p.unitId)]);
                    ote = true;
                } catch (e) { ote = "LEVÉ : " + (e as Error).message; }
            }
            return { ok: true, unitId: p.unitId, avant, apres, placeholderOte: ote };
        }
        if (reste > 0) return { attendre: true };
        return { ok: false, unitId: p.unitId, avant, apres,
                 error: "`Apply` est passé mais AUCUNE unité n'est apparue. Le runner ne "
                     + "construit que ce dont la CONFIGURATION est dans la BC -- mesuré : "
                     + "`spaceBlackmane` (hors BC) passe sans erreur et rien n'apparaît, "
                     + "`ultraInceptorSgt` (dans la BC) crée l'unité. Il faut enrichir la BC "
                     + "(`catalog_inject` / `--p-units`), donc un remontage.",
                 placeholderOte: "LAISSÉ EN PLACE -- c'est la seule trace visible de ta pose" };
    }).then((r) => {
        if ((r as { attendre?: boolean }).attendre === true) {
            verifierPuisNettoyer(p, avant, reste - 1);
            return;
        }
        tracerPose(r);
    }, (e) => tracerPose({ ok: false, unitId: p.unitId, error: String(e) }));
}

/** Premier temps : appliquer l'`AddUnitMessage` — le MÊME message que le harnais RL emploie. */



















export function armerBouton(): true | Refus {
    if (listenerBouton) return true;
    const k = findClassAnywhere(NS_BOUTONS, CLS_BOUTONS);
    if (!k) return refus(`\`${NS_BOUTONS}.${CLS_BOUTONS}\` INTROUVABLE sur ce build`);
    const mi = findMethodByParamCount(k, "UpdateState", 5);
    if (!mi) return refus(`\`${CLS_BOUTONS}$$UpdateState\` INTROUVABLE (5 paramètres)`);
    const t = lireTete(mi.ptr);
    if (t.erreur !== null) return refus(`tête de \`UpdateState\` ILLISIBLE (${t.erreur})`);
    if (teteTriviale(t)) {
        return refus(`REFUS : \`${CLS_BOUTONS}$$UpdateState\` résout sur un corps TRIVIAL `
            + `(ret à l'octet ${t.retA}) -- adresse PARTAGÉE. Cf. §8.`);
    }
    listenerBouton = Interceptor.attach(mi.ptr, {
        onEnter(args) {
            boutonFires++;
            const recu = args[2].toInt32();
            const mn = args[4].toInt32();
            const mx = args[5].toInt32();
            // ⛔ CE CALLBACK N'INVOQUE RIEN, ET C'EST LA LEÇON D'UN GEL.
            // La version précédente appelait `compterSurLePlateau()` ICI : elle invoquait donc
            // deux natifs et parcourait un dictionnaire DEPUIS UN CALLBACK D'INTERCEPTION, sur le
            // thread de rendu, à CHAQUE rafraîchissement du bouton. C'est le motif que le dépôt
            // interdit (« ne jamais invoquer un natif depuis un hook »), et le jeu s'est figé.
            // Le compte est désormais calculé HORS hook (`deploymentBoutonArmer {rafraichir}`)
            // et seulement LU ici.
            const surPlateau = compteCache;
            const plateau: Record<string, number | string> = compteCacheDetail
                ?? { cache: "jamais calculé -- appeler `rafraichir: true`" };
            // Ordre : consigne explicite > compte dérivé du plateau > ce que le HUD croit.
            // ⚠ On ne descend JAMAIS sous `recu` : le HUD sait ce qu'il a posé lui-même, et une
            // dérivation ratée ne doit pas RETIRER des unités qu'il a comptées.
            const derive = surPlateau !== null ? Math.max(recu, surPlateau) : recu;
            const impose = boutonImpose !== null ? boutonImpose : derive;
            if (impose !== recu) args[2] = ptr(impose);
            if (boutonObs.length < 32) {
                boutonObs.push({ recu, impose, min: mn, max: mx,
                                 source: boutonImpose !== null ? "consigne"
                                     : surPlateau !== null ? "plateau" : "HUD (non dérivé)",
                                 plateau });
            }
        },
    });
    Interceptor.flush();
    return true;
}

export function registerHud(ctx: Ctx): void {
    /** Relais sur le bouton CLEAR de l'écran. Armé, un appui ôte AUSSI les unités réelles. */
    ctx.rpc.deploymentClearArmer = (body?: {
        armer?: boolean; confirmer?: boolean;
    }): unknown => {
        const etat = () => ({ arme: listenerClear !== null, actif: clearAuto,
                              fires: clearFires, dernier: clearDernier });
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`armer: true` + `confirmer: true` : le clair de l'écran APPLIQUERA "
                         + "des `RemoveUnitMessage` sur la bataille en cours" };
        }
        if (body.armer === false) {
            if (listenerClear) { try { listenerClear.detach(); } catch { /* best effort */ } }
            listenerClear = null; clearAuto = false;
            return { ok: true, ...etat() };
        }
        if (body.confirmer !== true) return refus("`confirmer: true` exigé");
        const r = armerClear();
        if (r !== true) return r;
        clearAuto = true;
        return { ok: true, ...etat() };
    };

    /**
     * Relais sur la DÉPOSE unité par unité — le pendant de `deploymentClearArmer`, qui ne
     * couvre que le bouton « tout enlever ». Armé, ôter une unité du plateau ôte AUSSI
     * l'unité RÉELLE du runner. Cf. `retirerSiSurLePlateau` pour le chemin, mesuré.
     */
    ctx.rpc.deploymentDeposeArmer = (body?: {
        armer?: boolean; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const etat = () => ({
            actif: deposeAuto,
            ancre: cheminsListeners["PutUnitIntoHand"] !== undefined,
            chemin: cheminsEtat["PutUnitIntoHand"] ?? null,
            dernier: deposeDernier, trace: deposeTrace,
        });
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`armer: true` + `confirmer: true` : ôter une unité du plateau "
                         + "APPLIQUERA un `RemoveUnitMessage` sur la bataille en cours. Le "
                         + "chemin est `PutUnitIntoHand`, qui porte AUSSI la saisie depuis le "
                         + "roster -- c'est la présence sur le plateau qui les sépare." };
        }
        if (body.armer === false) { deposeAuto = false; return { ok: true, ...etat() }; }
        if (body.confirmer !== true) return refus("`confirmer: true` exigé");
        // ⚠ L'ANCRAGE VIT DANS `armerHud`, comme pour `deploymentSyncArmer` : sans lui, rien
        // ne tirera et l'armement rendrait un `actif: true` qui ne tient RIEN.
        const r = armerHud();
        if (r !== true) return r;
        deposeAuto = true;
        return { ok: true, ...etat() };
    };

    /**
     * LA VOIE DE POSE DES HÉROS — runner direct (défaut) ou étage FSM.
     *
     * `armer: true` fait passer `deploymentMemoire {rejouer}` par
     * `StateMachineActions$$UnitDeployment_PlaceUnitOnBoard`, la méthode que le CLIC HUMAIN
     * invoque. Les héros deviennent alors des PLACEHOLDERS comptés par le HUD, au lieu d'unités
     * réelles invisibles de lui (START à 0/5, un seul placeholder dans la boucle du START).
     */


    ctx.rpc.deploymentBoutonArmer = (body?: {
        armer?: boolean; compte?: number; confirmer?: boolean; rafraichir?: boolean;
    }): Promise<unknown> | unknown => {
        // Le calcul se fait ICI, sur la file du thread principal — JAMAIS dans le callback.
        if (body?.rafraichir === true) {
            return queueOnMainThread(() => {
                const d = compterSurLePlateau();
                compteCacheDetail = d;
                compteCache = typeof d.unitesDuJoueurHumain === "number"
                    ? d.unitesDuJoueurHumain : null;
                const sortie: Record<string, unknown> = { ok: true, compteCache, detail: d };
                // ⚠ SANS CE SECOND TEMPS, LE CACHE NE SERT À RIEN SUR DES UNITÉS PRÉ-POSITIONNÉES.
                // `UpdateButtons` n'a que cinq appelants (`Show`, `TryMarkUnitAsPlaced`,
                // `PutUnitIntoHand`, `RemoveUnit`, `HandleOnRemoveAllHeroesPressed`) : quand les
                // unités viennent de `bc.Units`, AUCUN ne se produit après le montage. Le bouton
                // reste donc figé sur l'état calculé à `Show`, où le cache n'existait pas encore.
                // On provoque donc le rafraîchissement.
                //
                // ⚠ On invoque `UpdateButtons`, qui n'est PAS ancré ; c'est `UpdateState`, qu'il
                // appelle, qui l'est. Et l'appel part de la FILE DU THREAD PRINCIPAL, pas d'un
                // callback d'interception — c'est cette distinction-là, et non l'ancrage, qui a
                // gelé le jeu deux fois ce soir.
                if (hudInstance === null || hudInstance.isNull()) {
                    sortie.rafraichi = false;
                    sortie.raison = "aucune instance de HUD captée (`Show` n'a pas tiré)";
                    return sortie;
                }
                const c = classeDerriere(hudInstance);
                if (c.classe !== CLS_HUD) {
                    sortie.rafraichi = false;
                    sortie.raison = `le pointeur de HUD ne porte plus \`${CLS_HUD}\` mais `
                        + `\`${c.classe ?? c.erreur}\` -- PÉRIMÉ, on n'invoque rien dessus`;
                    return sortie;
                }
                const kh = findClassAnywhere(NS_HUD, CLS_HUD);
                const mUp = kh ? findMethodByParamCount(kh, "UpdateButtons", 0) : null;
                if (!mUp) {
                    sortie.rafraichi = false;
                    sortie.raison = "`UnitDeploymentHud$$UpdateButtons` INTROUVABLE (0 paramètre)";
                    return sortie;
                }
                const avant = boutonFires;
                try { invokeMethod(mUp.info, hudInstance, null); }
                catch (e) {
                    sortie.rafraichi = false;
                    sortie.raison = "`UpdateButtons` a levé : " + (e as Error).message;
                    return sortie;
                }
                // Le TÉMOIN : le relais a-t-il vraiment re-tiré ? Sans lui, « rafraîchi » ne
                // dirait que « l'appel est passé », ce qui ne prouve rien.
                sortie.rafraichi = boutonFires > avant;
                sortie.relaisTirs = boutonFires - avant;
                sortie.dernier = boutonObs.length > 0 ? boutonObs[boutonObs.length - 1] : null;
                return sortie;
            });
        }
        const etat = () => ({
            arme: listenerBouton !== null, impose: boutonImpose, fires: boutonFires,
            obs: boutonObs.slice(-8), bouton: etatDuBouton(),
        });
        if (body == null || body.armer === undefined) {
            return { ok: true, lecture: true, ...etat(),
                     note: "`armer: true` + `confirmer: true` : ce relais RÉÉCRIT le compte "
                         + "d'unités posées que le HUD utilise pour activer START" };
        }
        if (body.armer === false) {
            if (listenerBouton) { try { listenerBouton.detach(); } catch { /* best effort */ } }
            listenerBouton = null; boutonImpose = null;
            return { ok: true, arme: false };
        }
        if (body.confirmer !== true) return refus("`confirmer: true` exigé");
        if (body.compte !== undefined) boutonImpose = body.compte;
        const r = armerBouton();
        if (r !== true) return r;
        return { ok: true, ...etat() };
    };

    /**
     * LE HUD — les DEUX dictionnaires, et le VERDICT de chaque clic. Observation pure.
     *
     * `{ armer: true }` ancre `Show` (lit les comptes après remplissage) et
     * `TryMarkUnitAsPlaced` (capture unitId + retour). Sans corps : lecture.
     */
    ctx.rpc.deploymentHudArmer = (body?: { armer?: boolean }): unknown => {
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true,
                     arme: listenerShow !== null && listenerPose !== null,
                     etat: hudEtat, bascule: etatBasculeHud(), chemins: cheminsEtat,
                     poses: hudPoses, plateau: hudBoard,
                     shows: { entrees: showEnters, sorties: showFires,
                              leveEnCours: showEnters > showFires },
                     clears: { fires: vidangeFires, trace: vidangeTrace } };
        }
        if (body.armer === false) {
            if (listenerShow) { listenerShow.detach(); listenerShow = null; }
            if (listenerPose) { listenerPose.detach(); listenerPose = null; }
            if (listenerBoard) { listenerBoard.detach(); listenerBoard = null; }
            // ⚠ `listenerVidange` = l'observation de `ClearWidgets`, PAS la vidange à la
            // retraite (`listenerVidangeRetraite`), qui n'est pas un relais de HUD et ne doit
            // jamais tomber avec eux. Les deux noms se ressemblent, un renommage global les a
            // déjà confondus une fois -- et ça compile, puisque les deux existent.
            if (listenerVidange) { listenerVidange.detach(); listenerVidange = null; }
            Interceptor.flush();
            return { ok: true, arme: false, action: "retire" };
        }
        const r = armerHud();
        if (r !== true) return r;
        return { ok: true, arme: true, etat: hudEtat, poses: hudPoses, plateau: hudBoard,
                 note: "`Show` publie les deux comptes ; `TryMarkUnitAsPlaced` publie le "
                     + "verdict de chaque clic. Un premier dictionnaire plein et un second "
                     + "vide EST la signature de « je sélectionne mais je ne pose pas »." };
    };

    /**
     * SE BRANCHER SUR LE VIDANGEUR, ET LIRE LA PILE ENTRANTE.
     *
     * ⚠ C'EST LA RÉPONSE À « L'ERREUR ARRIVE TROP TARD ». Le « system error » du START est un
     * SYMPTÔME : quand il tombe, la cause a déjà eu lieu, et son backtrace SEH ne nomme que des
     * `mono_type_size`. Ce qu'on sait en revanche, c'est QUOI a bougé : les trois dictionnaires
     * du HUD passent de 102 à 0. On s'ancre donc sur le geste lui-même — `Dictionary.Clear` — et
     * on relève la pile AU MOMENT du vidage. L'appelant est alors LU, pas déduit.
     *
     * ⚠ RÉSOLU SUR L'INSTANCE INFLATÉE, jamais sur la définition générique : `findMethod` sur
     * une définition rend le THUNK d'invocation, pas le corps gshared — un ancrage qui se
     * déclare posé et ne tire jamais (#259-b). On part donc de la classe du dictionnaire VIVANT.
     *
     * ⚠ ET IL EST FILTRÉ PAR POINTEUR, PREMIÈRE INSTRUCTION. Ce corps est partagé par toutes les
     * instanciations de même forme : sans filtre, c'est un broad-hook sur du hot path, exactement
     * ce que le `CLAUDE.md` proscrit. On compare `args[0]` aux trois dictionnaires du HUD et on
     * sort. Il s'arme et se désarme À LA DEMANDE — pas au montage.
     */
    ctx.rpc.deploymentVidangeArmer = (body?: {
        armer?: boolean; confirmer?: boolean;
    }): Promise<unknown> | unknown => {
        const etat = () => ({
            arme: listenerDictClear !== null, cibles: ciblesVidange.map((c) => c.nom),
            tirs: dictClearTrace.length, trace: dictClearTrace,
        });
        if (!body || body.armer === undefined) return { ok: true, lecture: true, ...etat() };
        if (body.armer === false) {
            if (listenerDictClear) { listenerDictClear.detach(); listenerDictClear = null; }
            ciblesVidange.length = 0;
            Interceptor.flush();
            return { ok: true, action: "detache", ...etat() };
        }
        if (body.confirmer !== true) {
            return refus("ANCRAGE SUR UN CORPS PARTAGÉ -- exige `confirmer: true`. "
                + "`Dictionary.Clear` est un corps gshared appelé par tout le jeu ; le filtre "
                + "par pointeur est la première instruction, mais le trampoline, lui, est payé "
                + "par TOUS les appelants. À désarmer dès la mesure prise.");
        }
        return queueOnMainThread((): Record<string, unknown> => {
            if (hudInstance === null || hudInstance.isNull()) {
                return { ok: false, error: "aucun `UnitDeploymentHud` capturé" };
            }
            const k = findClassAnywhere(NS_HUD, CLS_HUD);
            if (!k) return { ok: false, error: `\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE` };
            if (listenerDictClear) return { ok: true, action: "deja arme", ...etat() };
            ciblesVidange.length = 0;
            for (const nom of ["_unitModels", "_allUnitModels", "_allUnlockedUnitModels"]) {
                const off = getFieldOffset(k, nom);
                if (off < 0) continue;
                try {
                    const d = hudInstance.add(off).readPointer();
                    if (!d.isNull()) ciblesVidange.push({ nom, ptr: d });
                } catch { /* champ illisible : on le DIT par son absence de la liste */ }
            }
            if (ciblesVidange.length === 0) {
                return { ok: false, error: "aucun des trois dictionnaires n'est lisible -- rien "
                    + "à filtrer, et un ancrage SANS filtre est refusé" };
            }
            const kDict = ciblesVidange[0].ptr.readPointer();
            const mClear = findMethod(kDict, "Clear");
            if (!mClear || mClear.ptr.isNull()) {
                return { ok: false, error: "`Clear` INTROUVABLE sur la classe du dictionnaire "
                    + "VIVANT (instance inflatée)" };
            }
            const t = lireTete(mClear.ptr);
            listenerDictClear = Interceptor.attach(mClear.ptr, {
                onEnter(args) {
                    // FILTRE D'ABORD. Tout le reste est derrière cette comparaison.
                    const self = args[0];
                    let nom: string | null = null;
                    for (const c of ciblesVidange) {
                        if (c.ptr.equals(self)) { nom = c.nom; break; }
                    }
                    if (nom === null) return;
                    if (dictClearTrace.length >= 16) return;
                    let avant: string | number | null = null;
                    try { avant = compteDict(self); } catch { /* laisse null */ }
                    dictClearTrace.push({
                        champ: nom, dictionnaire: self.toString(), comptaAvant: avant,
                        dansShow, showEnters, showFires,
                        pile: pileGhidra(this.context, 24),
                    });
                },
            });
            Interceptor.flush();
            return { ok: true, action: "attache", clearVA: ghidraVA(mClear.ptr), tete: t,
                     classeDict: s(class_get_name(kDict) as NativePointer), ...etat() };
        });
    };

    /**
     * LE ROBINET DES NEUF ANCRAGES DE BASCULE — ce qui rend « est-ce NOUS ? » MESURABLE.
     *
     * ⚠ CE RPC EXISTE PARCE QU'UNE OBSERVATION PURE N'ÉTAIT PAS ÔTABLE. `deploymentHudArmer
     * {armer:false}` ne détache que `Show`, `TryMarkUnitAsPlaced` et `AddPlaceholderUnit` ; les
     * neuf `CHEMINS_BASCULE` restaient en place pour la vie de la session. Or nous INVOQUONS
     * `HandleOnSwitchToMachinesOfWarUnitsTapped`, qui en fait partie — et le décompilé en nomme
     * deux autres dans sa descendance. La règle « ne jamais ancrer la méthode qu'on invoque »
     * était donc violée sans qu'aucun geste ne permette de le vérifier.
     *
     * Lecture seule sans `armer`. `seulement: [...]` restreint aux noms donnés — c'est la forme
     * du contrôle : ôter les TROIS de la chaîne d'appel, retenter, et garder les six autres
     * armés pour que la mesure ne perde pas ses témoins.
     */
    ctx.rpc.deploymentCheminsArmer = (body?: {
        armer?: boolean; seulement?: string[];
    }): unknown => {
        const inventaire = (): Record<string, unknown> => {
            const out: Record<string, unknown> = {};
            for (const nom of CHEMINS_BASCULE) {
                out[nom] = { ancre: cheminsListeners[nom] !== undefined,
                             etat: cheminsEtat[nom] ?? null };
            }
            return out;
        };
        if (!body || body.armer === undefined) {
            return { ok: true, lecture: true, connus: CHEMINS_BASCULE.slice(),
                     ancres: Object.keys(cheminsListeners), chemins: inventaire() };
        }
        const seulement = Array.isArray(body.seulement) && body.seulement.length > 0
            ? body.seulement : undefined;
        if (seulement !== undefined) {
            const inconnus = seulement.filter((n) => !CHEMINS_BASCULE.includes(
                n as typeof CHEMINS_BASCULE[number]));
            if (inconnus.length > 0) {
                return refus(`noms HORS de \`CHEMINS_BASCULE\` : ${inconnus.join(", ")} -- `
                    + `les neuf connus sont ${CHEMINS_BASCULE.join(", ")}`);
            }
        }
        if (body.armer === false) {
            const otes = desarmerChemins(seulement);
            return { ok: true, action: "detache", otes,
                     restentAncres: Object.keys(cheminsListeners), chemins: inventaire() };
        }
        const k = findClassAnywhere(NS_HUD, CLS_HUD);
        if (!k) return refus(`\`${NS_HUD}.${CLS_HUD}\` INTROUVABLE sur ce build`);
        const poses = armerChemins(k, seulement);
        Interceptor.flush();
        return { ok: true, action: "attache", poses,
                 ancres: Object.keys(cheminsListeners), chemins: inventaire() };
    };
}
