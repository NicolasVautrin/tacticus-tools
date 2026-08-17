// guild-boss-config — LE BOSS DE GUILDE COURANT, ET LES LIMITATIONS DE ROSTER QUI L'ACCOMPAGNENT.
//
// POURQUOI. Le gameconfig VERSIONNE ne porte PAS les encounters de guild boss : on y trouve
// ses coffres (`chest_guildboss_defeated_*`, `guildboss_season_end_reward_*`) mais ni
// `boardId`, ni `unitId`, ni PV, ni NPC. Ils viennent du SERVEUR et vivent dans la
// progression. Il n'existe donc AUCUNE voie « tout depuis le fichier » -- lire la progression
// est obligatoire, et c'est ce que ce module fait.
//
// LA CHAINE, meme forme que `pvp-opponents.ts` :
//
//     ViewCommandExecutor._guildBossProgression   ->  GuildBossProgression
//       GetGuildBossBattleConfiguration(idx)      ->  GuildBossConfiguration
//       GetDeployableUnits(idx, includeLocked)    ->  List<String>
//
// LA CONFIGURATION REMPLIT 11 DES 14 ARGUMENTS DU CTOR SANDBOX, un pour un :
//
//     BoardId -> boardId          BossUnitId -> bossUnitId
//     EggUnitId -> npc1UnitId     DragonlingUnitId -> npc2UnitId
//     BossHealth -> health        RemainingBossHealth -> remainingHealth
//     MaxRoundAmount -> rounds    SpawnPointSetIndex -> spawnPointIndex
//     BossModifiers / Enemies / UnitModifiers -> idem
//
// Les trois qui restent sont NOTRE camp (`playerType`, `playerUnits`,
// `playerMachineOfWarUnit`) -- exactement ce que la phase de deploiement doit choisir.
//
// ⚠ LA LIMITATION DE ROSTER EST `DisallowedFactions`, ET LA REGLE EST LUE AU DECOMPILE.
// `GuildBossProgression$$GetDeployableUnitsPooled` teste le champ `+0x60` de la configuration
// (soit `DisallowedFactions`) :
//
//     si IsNullOrEmpty(config + 0x60)                  -> l'unite est ACCEPTEE
//     sinon si !Contains(config + 0x60, <faction>)     -> l'unite est ACCEPTEE
//
// Autrement dit : liste vide => tout passe ; liste non vide => passe ce qui n'y est PAS.
//
// ⚠ ET LA SIGNATURE N'EST PAS CELLE QU'ON CROIT. `GetDeployableUnitsPooled` prend
// `(encounterIndex : EncounterIndex, includeLocked : Boolean)` -- PAS zero parametre. Le
// booleen choisit le slot d'interface `0xc` ou `0xe3` sur la progression d'unites, les deux
// memes slots que cote PvP. « Avec ou sans les unites verrouillees » est donc un CHOIX, pas un
// defaut : ce module le rend explicite et le publie.
//
// ⚠ CE QUE LES DEUX NATIFS INVOQUES FONT, VERIFIE AU DECOMPILE AVANT DE LES APPELER.
// `GetGuildBossBattleConfiguration` ALLOUE un objet et le remplit depuis les modeles ; il
// n'ecrit RIEN sur le compte. `GetDeployableUnitsPooled` lit et alloue depuis un pool. Aucun
// `Send*GameEvent`, aucun appel reseau. C'est ce qui autorise l'invocation.
//
// ⚠ ET IL NE FAUT PAS MONTER LE BOSS PAR SA PROPRE SOURCE. `GuildBossGameModeSource` porte un
// `SendLoadBattleGameEventInternal` qui enregistre une tentative AU CHARGEMENT ; la surface de
// `SandboxGameModeSource` n'en porte aucun. Le montage passe donc par la sandbox -- c'est ce
// qui rend l'operation gratuite.
//
// LECTURE SEULE : aucune ecriture, aucune tentative consommee.

import {
    findClassAnywhere, findMethodByParamCount, getFieldOffset, MethodRef,
} from "../il2cpp/helpers.js";
import { executeurVivant, Refus as RefusVue } from "./view-command.js";
import {
    champInt, champPointeur, champTexte, estRefus, listeDeTextes, refus,
} from "./lecture-champs.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";

/** `EncounterIndex` est un TYPE VALEUR d'un seul `Int32` (`boxedSize` = 20 = 0x10 + 4).
 *  `il2cpp_runtime_invoke` attend un pointeur vers la VALEUR, pas vers une boite. */
function argIndex(i: number): NativePointer {
    const p = Memory.alloc(4);
    p.writeS32(i);
    return p;
}

function argBool(b: boolean): NativePointer {
    const p = Memory.alloc(1);
    p.writeU8(b ? 1 : 0);
    return p;
}

/** La `GuildBossProgression` vivante, via le foyer `executeurVivant`. */
export function progressionGuildBoss(): NativePointer | RefusVue {
    const exec = executeurVivant();
    if (estRefus(exec)) return exec;
    const kExec = findClassAnywhere("idun.shared.commands", "ViewCommandExecutor");
    if (!kExec) return refus("classe `idun.shared.commands.ViewCommandExecutor` introuvable");
    const off = getFieldOffset(kExec, "_guildBossProgression");
    if (off < 0) {
        return refus("`_guildBossProgression` ABSENT de `ViewCommandExecutor` sur ce build "
            + "-- chemin PERIME");
    }
    const p = (exec as NativePointer).add(off).readPointer();
    if (p.isNull()) {
        return refus("`ViewCommandExecutor._guildBossProgression` est NUL -- le mode guild boss "
            + "n'est PAS cable. C'est un defaut de CABLAGE, pas une absence de guilde.");
    }
    return p;
}

/** Resout une methode sur la classe REELLE de la progression (jamais par un nom de namespace :
 *  l'objet derriere `IGuildBossProgression` est une `GuildBossProgression`). */
function methodeDe(prog: NativePointer, nom: string, arite: number): MethodRef | RefusVue {
    let k: NativePointer;
    try { k = prog.readPointer(); } catch { return refus("classe de la progression illisible"); }
    if (k.isNull()) return refus("slot de classe NUL sur la progression");
    const mi = findMethodByParamCount(k, nom, arite);
    if (!mi || mi.ptr.isNull()) {
        return refus(`\`${nom}\` (${arite} parametre(s)) INTROUVABLE sur ce build -- signature `
            + "CHANGEE, on ne devine pas une arite de remplacement");
    }
    return mi;
}

/**
 * La `GuildBossConfiguration` d'un encounter.
 *
 * ⚠ Le natif rend **0** (et non une levee) quand ses `Contract.Require` echouent -- mesure au
 * decompile : il exige `this+0xc0` et `this+0x98` non nuls. Ce zero SIGNIFIE « la progression
 * existe mais n'a pas ses donnees » (pas de guilde, pas de saison en cours, pas encore
 * synchronise), et c'est un etat parfaitement legitime qu'il faut NOMMER plutot que de rendre
 * comme une panne.
 */
function configuration(prog: NativePointer, idx: number): NativePointer | RefusVue {
    const mi = methodeDe(prog, "GetGuildBossBattleConfiguration", 1);
    if (estRefus(mi)) return mi;
    let r: NativePointer;
    try { r = invokeMethod(mi.info, prog, [argIndex(idx)]); }
    catch (e) { return refus("`GetGuildBossBattleConfiguration` a leve : " + (e as Error).message); }
    if (r.isNull()) {
        return refus(`\`GetGuildBossBattleConfiguration(${idx})\` a rendu NUL. Au decompile, ce `
            + "retour signifie que les `Contract.Require` de la progression ont echoue : elle "
            + "vit, mais SANS DONNEES (pas de guilde, pas de saison active, ou pas encore "
            + "synchronisee). Ce n'est pas une panne de lecture.");
    }
    gcRoot.add(r);
    return r;
}

/** Le roster deployable, filtres du mode APPLIQUES par le natif lui-meme. */
function deployables(prog: NativePointer, idx: number, includeLocked: boolean):
    string[] | RefusVue {
    const mi = methodeDe(prog, "GetDeployableUnits", 2);
    if (estRefus(mi)) return mi;
    let r: NativePointer;
    try { r = invokeMethod(mi.info, prog, [argIndex(idx), argBool(includeLocked)]); }
    catch (e) { return refus("`GetDeployableUnits` a leve : " + (e as Error).message); }
    if (r.isNull()) return refus("`GetDeployableUnits` a rendu NUL");
    gcRoot.add(r);
    const l = listeDeTextes(r);
    if (l === null) return refus("liste deployable ILLISIBLE -- ce n'est pas une `List<String>`");
    return l;
}

/**
 * LE ROSTER GUILD BOSS, sous la forme que la substitution du HUD attend : la BOITE rendue par
 * `GetDeployableUnitsPooled`.
 *
 * ⚠ ON N'EMPRUNTE PAS A UNE `GuildBossGameModeSource`, ET C'EST DELIBERE. Elle n'est captee
 * par aucun de nos ancrages, et surtout son `IsUnitDeployable` ne fait que DELEGUER a la
 * progression (slot d'interface `0x36`, avec son index d'encounter). La progression est donc
 * le FOYER de la regle, pas un contournement : on s'y adresse directement, avec une dependance
 * de moins.
 *
 * ⚠ Rend la BOITE, pas la valeur : `PooledList<T>` est un TYPE VALEUR, donc
 * `il2cpp_runtime_invoke` la boxe, et c'est a l'appelant de deboxer (+0x10) comme il le fait
 * deja pour les deux autres preteurs. Rendre la boite la ou l'appelant attend la valeur lui
 * ferait lire l'en-tete d'objet comme si c'etait le conteneur.
 */
export function rosterPooledGuildBoss(idx: number, includeLocked: boolean):
    NativePointer | RefusVue {
    const prog = progressionGuildBoss();
    if (estRefus(prog)) return prog;
    const mi = methodeDe(prog as NativePointer, "GetDeployableUnitsPooled", 2);
    if (estRefus(mi)) return mi;
    let r: NativePointer;
    try { r = invokeMethod(mi.info, prog as NativePointer, [argIndex(idx), argBool(includeLocked)]); }
    catch (e) { return refus("`GetDeployableUnitsPooled` a leve : " + (e as Error).message); }
    if (r.isNull()) return refus("`GetDeployableUnitsPooled` a rendu NUL");
    gcRoot.add(r);
    return r;
}

export function register(ctx: Ctx): void {
    /**
     * Le boss courant et ses limitations de roster.
     *
     * `{ encounterIndex }` choisit l'encounter (defaut 0) ; `{ includeLocked }` decide si les
     * unites verrouillees comptent (defaut `false` -- ce que l'ecran montre).
     *
     * ⚠ Publie TOUJOURS `cable` et `donnees` separement : une progression CABLEE mais SANS
     * DONNEES est un etat distinct d'une progression absente, et les confondre ferait chercher
     * un bug de harnais la ou il n'y a qu'une saison inactive.
     */
    ctx.rpc.guildBossConfig = (body?: {
        encounterIndex?: number; includeLocked?: boolean;
    }): Promise<unknown> => queueOnMainThread(() => {
        const idx = body?.encounterIndex ?? 0;
        const includeLocked = body?.includeLocked === true;

        const prog = progressionGuildBoss();
        if (estRefus(prog)) return { ...prog, cable: false, donnees: false };

        const cfg = configuration(prog as NativePointer, idx);
        if (estRefus(cfg)) {
            // CABLE (on tient la progression) mais SANS DONNEES -- la distinction est le point.
            return { ...cfg, cable: true, donnees: false,
                     progression: (prog as NativePointer).toString(), encounterIndex: idx };
        }

        const interdites = (() => {
            const l = champPointeur(cfg as NativePointer, "DisallowedFactions");
            if (estRefus(l)) return null;
            return l.isNull() ? [] : listeDeTextes(l);
        })();
        const ennemis = (() => {
            const l = champPointeur(cfg as NativePointer, "Enemies");
            if (estRefus(l)) return null;
            return l.isNull() ? [] : listeDeTextes(l);
        })();

        const dep = deployables(prog as NativePointer, idx, includeLocked);

        return {
            ok: true, cable: true, donnees: true,
            encounterIndex: idx, includeLocked,
            progression: (prog as NativePointer).toString(),
            // Les 11 champs qui remplissent le ctor `SandboxGuildBossBattleConfig`.
            boss: {
                boardId: champTexte(cfg as NativePointer, "BoardId"),
                bossUnitId: champTexte(cfg as NativePointer, "BossUnitId"),
                npc1UnitId: champTexte(cfg as NativePointer, "EggUnitId"),
                npc2UnitId: champTexte(cfg as NativePointer, "DragonlingUnitId"),
                spawnPointIndex: champInt(cfg as NativePointer, "SpawnPointSetIndex"),
                health: champInt(cfg as NativePointer, "BossHealth"),
                remainingHealth: champInt(cfg as NativePointer, "RemainingBossHealth"),
                rounds: champInt(cfg as NativePointer, "MaxRoundAmount"),
                bossRarity: champInt(cfg as NativePointer, "BossRarity"),
                unitSet: champTexte(cfg as NativePointer, "UnitSet"),
                enemies: ennemis,
            },
            // LES LIMITATIONS. `null` = pas lu ; `[]` = lu et VIDE, ce qui d'apres le decompile
            // signifie « aucune faction interdite, tout le roster passe ».
            limitations: {
                disallowedFactions: interdites,
                regle: interdites === null
                    ? "NON LUE"
                    : (interdites.length === 0
                        ? "aucune faction interdite -- tout le roster deployable passe"
                        : "une unite passe si sa faction n'est PAS dans `disallowedFactions`"),
                deployables: estRefus(dep) ? null : dep,
                nbDeployables: estRefus(dep) ? null : dep.length,
                refusDeployables: estRefus(dep) ? dep.error : null,
            },
            // Ces trois-la ne viennent PAS du boss : c'est le camp du joueur, donc le draft.
            aChoisir: ["playerType", "playerUnits", "playerMachineOfWarUnit"],
        };
    });
}
