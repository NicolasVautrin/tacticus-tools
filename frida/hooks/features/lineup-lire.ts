// LIRE LA COMPOSITION QUE LE JOUEUR AMÈNERA — surface de lecture, rien d'autre.
//
// POURQUOI CE MODULE EXISTE
// -------------------------
// `game/source-lineup.ts` porte LA réponse à « quelles unités le joueur amène-t-il ? » et il est
// déjà appelé au bon endroit (`battle-config.ts`, au `LoadBattle.onLeave`). Mais il n'avait
// AUCUNE surface RPC : la seule façon de voir sa réponse était de déclencher un patch de BC qui
// vise les camps. Pour la question « la composition est-elle vide, faut-il la décider ? », on veut
// LIRE sans patcher, sans monter de bataille, et sans rien dépenser.
//
// Ce module n'est QUE cela. Il n'ancre rien, n'écrit rien, ne monte rien.
//
// ⚠ LE PARAMÈTRE DE `GetBattleLineup` EST UNE TAILLE, PAS UN INDEX — et c'est le piège qui rendrait
// cette lecture MENSONGÈRE si on l'ignorait. Mesuré le 2026-08-23 : `0 -> []`, `1 -> 1 élément`,
// `2 -> 2`, `18 -> 18`. Le natif rend la composition sauvegardée AJUSTÉE au nombre de places
// demandé. Demander `0` rend donc un tableau vide qui se lit « aucune composition » alors qu'on a
// demandé zéro place. `lineupDeLaSource` prend pour défaut `MaxUnitsPossibleToStartBattle`, LU sur
// la source — on ne passe `places` ici que pour une mesure délibérée, jamais pour « corriger ».
//
// ⚠ TRI-ÉTAT, PARTOUT. Un capteur de source qui ne rend pas d'instance donne `refus`, JAMAIS une
// composition vide. Les deux se lisent autrement pareil, et le zéro de complaisance ferait
// conclure « il faut décider la composition » sur une panne de lecture — exactement l'inverse de
// ce qu'on cherche à établir.
//
// ⚠ CE QUE ÇA NE DIT PAS. La composition rendue est celle que la source a SAUVEGARDÉE, donc celle
// que le HUD de déploiement va pré-poser. Ce n'est pas la preuve que le runner la recevra : entre
// les deux il y a le déploiement et ses `AddUnitMessage`. Lire ici, c'est décider ; vérifier que
// ça mord est une autre mesure, en bataille.

import { Ctx } from "../controller.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { lineupDeLaSource } from "../game/source-lineup.js";
// Le FOYER des captures de `*GameModeSource`. On ne re-marche AUCUNE de ces chaînes ici : ce
// module consomme un pointeur de source, il n'a pas à savoir comment on l'obtient.
import {
    getCampaignGameModeSourcePtr, getGuildBossGameModeSourcePtr,
    getMowEventGameModeSourcePtr, getPvpGameModeSourcePtr,
} from "./campaign-builder.js";
// ⛔ LE VERROU QUI EVITE UN GEL, pas une precaution de style. Ce module INVOQUE
// `GetBattleLineup` ; `lineup-poser` l'ANCRE. Invoquer une methode qu'on ancre fait retomber
// l'appel natif dans notre propre trampoline pendant que Frida veut y executer du JS sur un
// thread qui tient deja le runtime -- gel mesure trois fois sur trois dans ce depot. On REFUSE
// la lecture pendant l'armement au lieu de la tenter.
import { estArme as poseurArme } from "./lineup-poser.js";

/** Les modes dont une source est CAPTÉE par `campaign-builder`. Un mode absent d'ici n'est pas
 *  « sans composition » — il est HORS DE PORTÉE DE CE LECTEUR, et le refus le dit. */
const CAPTEURS: Readonly<Record<string, () => NativePointer | null>> = {
    campagne: getCampaignGameModeSourcePtr,
    pvp: getPvpGameModeSourcePtr,
    mow: getMowEventGameModeSourcePtr,
    guildBoss: getGuildBossGameModeSourcePtr,
};

export function register(ctx: Ctx): void {
    /**
     * `lineupSource { mode?, places?, avecMow? }` — LECTURE PURE.
     *
     * `mode` par défaut `campagne` : c'est la source la mieux instrumentée du dépôt, la seule dont
     * `ShouldShowUnitDeployment` soit visible en table, et celle dont les nœuds portent une
     * composition NON VIDE — donc le seul terrain où « ma substitution a mordu » se distingue de
     * « rien n'a changé ».
     */
    ctx.rpc.lineupSource = (body?: {
        mode?: string; places?: number; avecMow?: boolean;
    }): Promise<unknown> | unknown => {
        // ⛔ REFUS AVANT TOUT : voir le verrou en tete de fichier. Un `ok:false` explicite vaut
        // infiniment mieux qu'un jeu fige, et il NOMME le geste qui debloque.
        if (poseurArme()) {
            return {
                ok: false,
                refus: "`lineupPoser` est ARME sur `GetBattleLineup` -- lire l'invoquerait, donc "
                    + "on retomberait dans notre propre trampoline (gel). Desarmer d'abord : "
                    + "`lineupPoserArmer { armer: false }`.",
            };
        }
        const mode = body?.mode ?? "campagne";
        const capteur = CAPTEURS[mode];
        if (capteur === undefined) {
            return {
                ok: false,
                refus: `mode inconnu \`${mode}\` -- connus : ${Object.keys(CAPTEURS).join(", ")}`,
                modesConnus: Object.keys(CAPTEURS),
            };
        }
        return queueOnMainThread(() => {
            let src: NativePointer | null;
            try {
                src = capteur();
            } catch (e) {
                return { ok: false, mode, refus: `capteur de source a levé : ${(e as Error).message}` };
            }
            if (src === null || src.isNull()) {
                return {
                    ok: false, mode,
                    refus: "aucune instance de source CAPTÉE pour ce mode -- ce n'est PAS "
                        + "« composition vide », c'est « pas mesuré ». La capture se fait quand le "
                        + "jeu construit la source : ouvrir l'écran du mode, puis relire.",
                };
            }
            const r = lineupDeLaSource(src, {
                places: body?.places,
                avecMow: body?.avecMow ?? true,
            });
            // `...r` porte deja `ok` : le restater le ferait ecraser en silence.
            return { mode, srcPtr: src.toString(), ...r };
        });
    };
}
