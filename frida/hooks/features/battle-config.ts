// Live BattleConfiguration inspection + (eventually) mutation.
//
// BattleConfiguration is the per-battle config stitched by
// CampaignGameModeSource.LoadBattle() and stored at _currentBattle (+0x80).
// We read from the amorce-captured campaignGameModeSourcePtr — so any inspection RPC requires
// a successful amorce first.
//
// Layout reference (from decompilation):
//   BattleConfiguration                     class
//     +0x10  Id                             string
//     +0x28  SpawnPointSetIndex             int
//     +0x30  Player                         PlayersConfiguration
//     +0x40  PredefinedUnits                List<PredefinedUnits>
//     +0x68  Board                          BattleConfigBoardConfiguration
//     +0x80  Units                          List<UnitConfiguration>  (templates)
//     +0x88  Tiles                          List<BattleConfigTileConfiguration> (palette)
//
//   ⚠ LES NEUF BOOLEENS SONT CONSECUTIFS A PARTIR DE +0xE0, ET SE RESSEMBLENT TOUS.
//   Cette ligne a porte `+0xE7 RandomizeAiInput` — c'est FAUX d'un octet, `+0xE7` est
//   `DisableRandomness` (#10022-r1). L'erreur etait INVISIBLE parce que les deux valent
//   `false` au seed : un accord en regime degenere. Chaque ligne cite ci-dessous l'ancre
//   NOMMEE qui la fixe ; les positions sans ancre sont deduites de l'ordre de
//   serialisation Newtonsoft de `data/seed-bc.json`, encadre par deux ancres.
//     +0xE0  UseGroupForAddUnit         bool   IdunBattle.Core.Services.BattleQuery$$get_UseGroupForAddUnit
//     +0xE1  NoAutomaticUnitTurns       bool   IdunBattle.Core.Services.BattleQuery$$get_NoAutomaticUnitTurns
//     +0xE2  EnableIdunAbilities        bool   (position)
//     +0xE3  IsTestBattle               bool   (position)
//     +0xE4  DisableTimeouts            bool   (position)
//     +0xE5  DisableAnimatorRecovery    bool   (position)
//     +0xE6  DisableActiveAbilitiesOnAI bool   IdunBattle.Runner.IdunRunner$$Initialize -> param `disableActiveAbilities`
//     +0xE7  DisableRandomness          bool   idun.IdunMainView$$ShowBattle (gate du seed horloge)
//     +0xE8  RandomizeAiInput           bool   IdunBattle.Runner.IdunRunner$$Initialize -> param `configurationRandomizeAiInput`
//
//   PredefinedUnits (per-player squad)      class
//     +0x10  Id                             PlayerId (enum int)
//     +0x18  Units                          List<PredefinedUnit>
//
//   PredefinedUnit                          class
//     +0x10  UnitId                         string
//     +0x18  RemainingHealth                Nullable<int>
//     +0x20  MaxHealth                      Nullable<int>
//
//   UnitConfiguration (template)            class
//     +0x10  Id                             string
//     +0x18  VisualId                       string
//     +0x28  Faction                        string
//     +0x38  Health                         int
//
//   BattleConfigBoardConfiguration          class
//     +0x10  Id                             string
//     +0x18  Width                          int
//     +0x1C  Height                         int
//
//   System.Collections.Generic.List<T>      class (IL2CPP)
//     +0x10  _items                         T[]  (Il2CppArray: len at +0x18, data at +0x20)
//     +0x18  _size                          int

import {
    readIl2cppString, findClassAnywhere, findMethod, class_get_methods, class_get_name,
    class_get_namespace, class_get_parent, method_get_name, method_get_param_count,
    methodEntry, s as cstr, MethodRef,
    domain_get, domain_get_assemblies, assembly_get_image, image_get_class,
    image_get_class_count,
} from "../il2cpp/helpers.js";
import { createManagedString } from "../il2cpp/invoke.js";
import { queueOnMainThread } from "../runtime/queue.js";
import {
    getCampaignGameModeSourcePtr, getMowEventGameModeSourcePtr,
    getPvpGameModeSourcePtr, tryActiveDiscoveryOfSources,
    findPvpGameModeSourceViaHeap,
} from "./campaign-builder.js";
// Le REGISTRE d'instances de source, par CLASSE REELLE, et son controle de peremption. C'est ce
// qui remplace le pointeur global servi sans verification -- cf. l'en-tete du module.
import {
    etatDuRegistre, instanceDeSource, poserCapteursDInstance, siConcordante,
} from "../game/source-instances.js";
import { buildRunner, runnerApplyMi } from "../game/runner.js";
import { lineupDeLaSource } from "../game/source-lineup.js";
// LE REGISTRE DES COMPOSITIONS. Second consommateur de la MEME decision que celle que
// `GetBattleLineup` posera au deploiement -- sans quoi on bufferait des unites qui ne descendent
// pas. Cf. l'en-tete de `lineup-poser.ts`.
import { compositionRetenue } from "./lineup-poser.js";
import { dumpEnum } from "../il2cpp/enum-dump.js";
import { registerRunner, getRunner as getRegistryRunner,
    listRunners as listRegistryRunners, MAX_RUNNERS }
    from "../game/runner-registry.js";
import {
    findClass, findCtorByParamCount, findMethodByParamCount, methodParamClass,
    getFieldInfo, field_get_type, type_get_class_or_element_class, class_instance_size,
} from "../il2cpp/helpers.js";
import { il2cpp_object_new, invokeMethod } from "../il2cpp/invoke.js";
import { bcDeLaSourceMontee, bcDeLaVueVivante, sourceMontee } from "./source-vivante.js";
// (!)FORME B. Le FOYER du réceptacle `EnvironmentAbilities` -- même objet que celui que posent
// `guild-war-config` (buffs de zone) et `sandbox-mode` (pression de fin d'Arène). Son ctor natif
// ne crée AUCUN de ses trois membres : une troisième copie du geste aurait divergé, et ce sont
// des ÉCRITURES en mémoire managée, où une divergence ne donne pas un résultat différent mais un
// CRASH. Pas de cycle : `environment-abilities` n'importe pas ce module.
import * as envAbilities from "./environment-abilities.js";
import { champPointeur, estRefus } from "./lecture-champs.js";
import { triggeredAbilityName } from "../data/triggered-ability-names.js";
import { deserializeFromJson, isDeserializerReady } from "../il2cpp/serializer.js";
import { getFieldOffset } from "../il2cpp/helpers.js";
import { serializeToJson as _serializeBcToJson } from "../il2cpp/serializer.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { log } from "../runtime/diag.js";
import { Ctx } from "../controller.js";

// --- Diag : hook AddPredefinedMachines pour savoir si elle fire pendant
//     Initialize. Si oui → la condition mode-skip n'est pas la cause, c'est
//     ailleurs (IsMachineOfWar(unitId)=false, slot manquant, etc.).
//     Si non → SetupGameOperation.Execute() la skip → faut hooker plus haut. ---
let _addPredefMachinesFires = 0;
const setupGameOpClass = findClassAnywhere(
    "IdunBattle.Operations", "SetupGameOperation");
const addPredefMachinesMi = setupGameOpClass
    ? findMethod(setupGameOpClass, "AddPredefinedMachines") : null;
if (addPredefMachinesMi) {
    try {
        Interceptor.attach(addPredefMachinesMi.ptr, {
            onEnter() { _addPredefMachinesFires++; },
        });
        log("[battle-config] AddPredefinedMachines hooked for diag");
    } catch (e) {
        log("[battle-config] AddPredefinedMachines hook failed: " + (e as Error).message);
    }
} else {
    log("[battle-config] AddPredefinedMachines method not resolved");
}

// --- PredefinedMachine class resolution (for BC.PredefinedMachines patch) ---

const predefinedMachinesOfWarClass = findClassAnywhere(
    "IdunBattle.Configuration", "PredefinedMachinesOfWar");
const predefinedMachineOfWarClass = findClassAnywhere(
    "IdunBattle.Configuration", "PredefinedMachineOfWar");
const predefinedMachinesOfWarCtor = predefinedMachinesOfWarClass
    ? findCtorByParamCount(predefinedMachinesOfWarClass, 0) : null;
// PredefinedMachineOfWar a un ctor(string unitId) + un ctor() — on prend
// celui à 1 arg pour init avec UnitId.
const predefinedMachineOfWarCtor1 = predefinedMachineOfWarClass
    ? findCtorByParamCount(predefinedMachineOfWarClass, 1) : null;
const predefinedMachineOfWarCtor0 = predefinedMachineOfWarClass
    ? findCtorByParamCount(predefinedMachineOfWarClass, 0) : null;

// --- Offsets ---

const CGMS_OFF_CURRENT_BATTLE = 0x80;
// MachinesOfWarEventGameModeSource a son _currentBattle a un offset different
// (+0xF0 vs +0x80 pour Campaign). On essaie d'abord Campaign puis MoW Event.
const MOWE_OFF_CURRENT_BATTLE = 0xF0;
// PvpGameModeSource._currentBattle @+0xD8
const PVP_OFF_CURRENT_BATTLE = 0xD8;

const BC_OFF_ID = 0x10;
// BC.GameMode est `Nullable<GameMode>` @0x18. Mono Nullable<int> layout :
// hasValue @+0 (1B + 3B padding), value @+4 (4B). Donc hasValue @0x18,
// value @0x1C. GameMode enum : Campaign=0, PvP=1, MachinesOfWarEvent=15.
const BC_OFF_GAMEMODE_HASVALUE = 0x18;
const BC_OFF_GAMEMODE_VALUE = 0x1C;
// BC.RuleSet est `Nullable<SyncPvpRuleSet>` @0x20. SyncPvpRuleSet enum :
// Deathmatch=0, Heist=1, KingOfTheHill=2, Territories=3, Boosts=4,
// EscortTheSummons=5, Draft=6, Boosts_Infested=7.
const BC_OFF_RULESET_HASVALUE = 0x20;
const BC_OFF_RULESET_VALUE = 0x24;
const BC_OFF_SPAWN_POINT_SET_INDEX = 0x28;
const BC_OFF_PREDEFINED_UNITS = 0x40;
const BC_OFF_PREDEFINED_MACHINES = 0x48;  // List<PredefinedMachinesOfWar>
// PredefinedMachinesOfWar : Id (PlayerId enum int) @+0x10, MachineOfWar
// (PredefinedMachineOfWar wrapper) @+0x18.
const PMOW_OFF_PLAYER_ID = 0x10;
const PMOW_OFF_MACHINE = 0x18;
// PredefinedMachineOfWar : UnitId (string) @+0x10.
const PMOW_OFF_UNIT_ID = 0x10;
const BC_OFF_BOARD = 0x68;
const BC_OFF_UNITS = 0x80;       // List<UnitConfiguration>
const BC_OFF_TILES = 0x88;       // List<BattleConfigTileConfiguration>
// #10022-r1 : etait 0xE7 — c'est `DisableRandomness`, pas `RandomizeAiInput`. Voir la table
// des neuf booleens en tete de fichier. En ECRITURE, l'octet fautif figeait le seed de la
// bataille au lieu de randomiser l'ordre d'activation IA.
const BC_OFF_RANDOMIZE_AI = 0xE8;

const LIST_OFF_ITEMS = 0x10;
const LIST_OFF_SIZE = 0x18;

const ARRAY_OFF_LEN = 0x18;
const ARRAY_OFF_DATA = 0x20;

const PU_OFF_ID = 0x10;
const PU_OFF_UNITS = 0x18;

const PUNIT_OFF_UNIT_ID = 0x10;
// ⛔ `PUNIT_OFF_REMAINING_HP` (0x18) et `PUNIT_OFF_MAX_HP` (0x20) retirés (2026-08-23). Ils étaient
// morts AVANT le nettoyage de `templateOverrides` — déclarés, jamais lus, et le commentaire disait
// lui-même « confirm at runtime », ce qui n'a jamais eu lieu. Un offset non confronté est un piège
// qui attend un lecteur ; `classFields` les re-dérive sur le build chargé si le besoin revient.

const UC_OFF_ID = 0x10;
const UC_OFF_VISUAL_ID = 0x18;
const UC_OFF_FACTION = 0x28;
const UC_OFF_HEALTH = 0x38;
// ⛔ `UC_OFF_DAMAGE` (0x50) retiré avec `templateOverrides` : `inspectBattleConfig` échantillonne
// `Id`/`VisualId`/`Faction`/`Health`, jamais `Damage`. Les quatre ci-dessus restent parce qu'ils
// sont EXERCÉS à chaque appel, donc confrontés ; celui-là ne l'était plus par personne.

const BCBC_OFF_ID = 0x10;        // Board.Id (also at +0x10 on master BoardConfiguration but with different base)
const BCBC_OFF_WIDTH = 0x18;
const BCBC_OFF_HEIGHT = 0x1C;

// --- Helpers ---

/** Resolve the live BattleConfiguration from the amorce-captured campaignGameModeSourcePtr.
 * Si Campaign source absent ou BC null, fallback sur MoW Event source
 * (offset _currentBattle different : 0xF0 vs 0x80). User doit avoir navigué
 * manuellement vers le MoW Event in-game pour que ce dernier soit capturé. */
// Un `_currentBattle` valide DOIT être une `IdunBattle.Configuration.BattleConfiguration`
// (class_get_name -> "BattleConfiguration"). Une source de mode PÉRIMÉE (typiquement une
// source PvP résiduelle après une nav PvP) peut garder à cet offset un objet à moitié
// démonté / pré-désérialisé — `JPropertyKeyedCollection` (JSON Newtonsoft), PAS une BC.
// Sans ce garde, la priorité PvP masquait une BC campagne VALIDE avec ce JObject stale ->
// `buildRunner` passait un non-BC à `Initialize` -> lecture de champs BC à des offsets
// faux -> access violation « system error » (crash opaque, diag: runner_init_threw
// step=initialize configKlass=JPropertyKeyedCollection). On type-check par NOM de classe
// (robuste, sur l'objet runtime, sans dépendre d'une résolution de classe au load).
function isBattleConfig(bc: NativePointer): boolean {
    try {
        const klass = bc.readPointer();
        if (klass.isNull()) return false;
        return cstr(class_get_name(klass) as NativePointer) === "BattleConfiguration";
    } catch { return false; }
}

/** Lit `src._currentBattle` (offset `off`) et ne le rend QUE si c'est une BattleConfiguration
 *  valide. Un candidat non-BC (source stale) est signalé et rejeté (jamais rendu) -> on tombe
 *  sur la source suivante. */
function readCurrentBattleIfValid(
    src: NativePointer, off: number, tag: string,
): NativePointer | null {
    try {
        const bc = src.add(off).readPointer();
        if (bc.isNull()) return null;
        if (isBattleConfig(bc)) return bc;
        let kn = "?";
        try { kn = cstr(class_get_name(bc.readPointer()) as NativePointer); } catch { /* */ }
        log(`[battle-config] getLiveBattleConfig: ${tag} _currentBattle n'est pas une `
            + `BattleConfiguration (classe=${kn}) -> source stale ignorée`);
        return null;
    } catch { return null; }
}

export function getLiveBattleConfig(): NativePointer | null {
    // ⚠ LA SOURCE RÉELLEMENT MONTÉE PASSE AVANT TOUTES LES SOURCES CAPTURÉES, ET C'EST UN
    // CORRECTIF, PAS UN CONFORT. Les trois candidats ci-dessous sont des sources CAPTURÉES au
    // vol (amorce, hooks de ctor) : aucune ne connaît `SandboxGameModeSource`. Mesuré le
    // 2026-08-22 -- un onslaught `Waves_Imperial_22` MONTÉ et tournant, et `getLiveBattleConfig`
    // rendait la BC `Campaign1_06` / board `C1_01` d'une source qui ne jouait plus.
    //
    // ⚠ CE QUI REND LA PANNE INVISIBLE : la BC périmée est PARFAITEMENT LISIBLE. Elle porte un
    // `Id`, un board, ses templates -- `inspectBattleConfig` la décrit sans broncher, et une
    // mutation appliquée dessus rend `relu: true` sans avoir le moindre effet. Le type-guard
    // ci-dessous ne peut rien contre ça : l'objet EST une `BattleConfiguration` valide, elle
    // n'est simplement plus celle qu'on joue. Seule la source montée le sait.
    // ⚠ LA VUE VIVANTE PASSE AVANT LA SOURCE MÉMORISÉE, ET C'EST LE MÊME CORRECTIF POUSSÉ D'UN
    // CRAN. `bcDeLaSourceMontee` se SOUVIENT de ce que NOUS avons monté ; elle est donc muette sur
    // une bataille RÉELLE, et carrément trompeuse sur une bataille ouverte avant nous — le
    // souvenir d'hier a l'air aussi vivant que la vérité d'aujourd'hui. Mesuré le 2026-08-23 :
    // onslaught réel en déploiement, ce chemin rendait la BC du banc de la veille (détail et
    // pointeurs dans `bcDeLaVueVivante`). La DÉCOUVERTE, elle, ne peut pas se périmer.
    const bcVue = bcDeLaVueVivante();
    if (bcVue !== null && isBattleConfig(bcVue)) return bcVue;

    const bcMontee = bcDeLaSourceMontee();
    if (bcMontee !== null && isBattleConfig(bcMontee)) return bcMontee;

    // Priorité : Pvp > MoW Event > Campaign. Quand l'user navigue vers un mode plus avancé
    // (PvP, MoW), on veut sa BC en priorité (plus riche : RuleSet, MoW ammo, templates :pvp).
    // CHAQUE candidat est TYPE-GUARDÉ (BattleConfiguration) : une source stale d'un mode
    // supérieur ne peut plus masquer une BC valide d'un mode inférieur.
    const pSrc = getPvpGameModeSourcePtr();
    if (pSrc !== null) {
        const bc = readCurrentBattleIfValid(pSrc, PVP_OFF_CURRENT_BATTLE, "PvP");
        if (bc !== null) return bc;
    }
    const mSrc = getMowEventGameModeSourcePtr();
    if (mSrc !== null) {
        const bc = readCurrentBattleIfValid(mSrc, MOWE_OFF_CURRENT_BATTLE, "MoW");
        if (bc !== null) return bc;
    }
    const cSrc = getCampaignGameModeSourcePtr();
    if (cSrc !== null) {
        const bc = readCurrentBattleIfValid(cSrc, CGMS_OFF_CURRENT_BATTLE, "Campaign");
        if (bc !== null) return bc;
    }
    return null;
}

/** Read a managed `List<T>` of reference-type elements. Returns the raw
 * Il2CppArray pointer + element count. Element i lives at `arrayPtr + 0x20 + i*8`
 * (already-typed reference). Returns null if the list itself is null. */
function readManagedList(
    listPtr: NativePointer,
): { array: NativePointer; size: number } | null {
    if (listPtr.isNull()) return null;
    try {
        const items = listPtr.add(LIST_OFF_ITEMS).readPointer();
        const size = listPtr.add(LIST_OFF_SIZE).readS32();
        if (items.isNull() || size < 0 || size > 10000) return null;
        return { array: items, size };
    } catch { return null; }
}

function readListItem(
    listInfo: { array: NativePointer; size: number }, i: number,
): NativePointer {
    return listInfo.array.add(ARRAY_OFF_DATA + i * Process.pointerSize)
        .readPointer();
}

/** La partie AVANT le `:` d'un `unitId`.
 *
 *  ⚠ C'est ce que fait `IdunBattle.Configuration.UnitConfigId$$CreateFromString` : il SCINDE, et
 *  `PureId` ne garde jamais le suffixe. On compare donc des `PureId`, jamais des chaines brutes --
 *  `tyranNpc3Termagant:6` et `tyranNpc3Termagant` designent la meme unite de catalogue. */
function pureId(brut: string): string {
    const i = brut.indexOf(":");
    return i < 0 ? brut : brut.slice(0, i);
}

/** Les `PureId` de `BC.PredefinedUnits`, tous joueurs confondus. `null` = PAS LU.
 *
 *  ⚠ TRI-ETAT, et il porte une decision : `null` (champ illisible) ne doit pas se lire comme
 *  « aucune unite predefinie ». Rendre `[]` sur une lecture ratee ferait poser un debuff SANS
 *  cible -- installe, compte a 1, et parfaitement inerte. L'appelant AVERTIT au lieu de deviner.
 *
 *  ⚠ POURQUOI TOUS LES JOUEURS SANS DISTINCTION DE CAMP : sur les BC que le jeu produit vraiment,
 *  ce champ porte l'ADVERSAIRE et lui seul -- mesure du 2026-08-23, une BC d'Arene reelle n'a
 *  qu'UN groupe (le sien), et les unites du joueur entrent par `AddUnitMessage` au deploiement
 *  (`GetPvpLevelConfig` recoit `overrideMainPlayerUnits = 0`, lu au decompile). Meme forme cote
 *  onslaught. Lire le camp exigerait de parcourir `BC.Player.Players`, un `SortedDictionary`
 *  (arbre rouge-noir) sur le thread principal, a cette fenetre-la : le cout n'est pas justifie
 *  tant que la mesure dit qu'il n'y a qu'un camp ici.
 *  ⚠ LA LIMITE EST REELLE ET SE DIT : sur une BC qui porterait les DEUX camps (une sandbox montee
 *  avec `--units`, par exemple), `ciblesAuto: "adversaire"` viserait AUSSI les siennes. */
function unitesPredefinies(bc: NativePointer): string[] | null {
    try {
        const pu = readManagedList(bc.add(BC_OFF_PREDEFINED_UNITS).readPointer());
        if (pu === null) return null;
        const out = new Set<string>();
        for (let i = 0; i < pu.size; i++) {
            const grp = readListItem(pu, i);
            if (grp.isNull()) continue;
            const units = readManagedList(grp.add(PU_OFF_UNITS).readPointer());
            if (units === null) continue;
            for (let j = 0; j < units.size; j++) {
                const p = readListItem(units, j);
                if (p.isNull()) continue;
                const id = readIl2cppString(p.add(PUNIT_OFF_UNIT_ID).readPointer());
                if (id) out.add(pureId(id));
            }
        }
        // Les MACHINES comptent comme des unites adverses -- meme liste, mesure sur la BC d'Arene
        // reelle ou `tyranBiovore:pvp` est en `PredefinedMachines`, pas en `PredefinedUnits`.
        // Les offsets sont ceux qu'`inspectBattleConfig` exerce a chaque appel, donc confrontes.
        const pm = readManagedList(bc.add(BC_OFF_PREDEFINED_MACHINES).readPointer());
        if (pm !== null) {
            for (let i = 0; i < pm.size; i++) {
                const entry = readListItem(pm, i);
                if (entry.isNull()) continue;
                const mp = entry.add(PMOW_OFF_MACHINE).readPointer();
                if (mp.isNull()) continue;
                const id = readIl2cppString(mp.add(PMOW_OFF_UNIT_ID).readPointer());
                if (id) out.add(pureId(id));
            }
        }
        return Array.from(out);
    } catch { return null; }
}

/** Combien de tours de VAGUES la BC programme -- `UnitSpawningOverTime.Tiers._count`.
 *
 *  `0` = aucune vague. `null` = PAS MESURE. Dans les DEUX cas non nuls, `ciblesAuto` est
 *  INCOMPLET et doit le DIRE.
 *
 *  ⚠ ON COMPTE, ON NE PARCOURT PAS. `Tiers` est un `Dictionary<Int32, Dictionary<PlayerId, Wave>>` :
 *  des cles de TYPE VALEUR imbriquees, c'est-a-dire exactement le geste qui a tue le process le
 *  2026-08-21 sur `EnvironmentAbilities.AbilitiesConfigurations`. Lire `_count` est un `readS32`
 *  sur un champ resolu par nom -- aucun boxage, aucune enumeration.
 *
 *  ⇒ Consequence assumee : en ONSLAUGHT, `ciblesAuto: "adversaire"` ne couvre que la POSE
 *  INITIALE. Le tirage des vagues (4 a 7 types sur un pool de 12) passe par
 *  `onslaught_commun.py`, qui lit le SUR-ENSEMBLE du tier dans la progression du compte et le
 *  passe en cibles EXPLICITES -- rater un type coute la bataille, en viser un qui n'apparait
 *  jamais ne coute rien. */
/** Les deux camps de la BC, DERIVES -- `{ miens, adverses }` en `PureId`. `null` = PAS DERIVABLE.
 *
 * ⛔ CE QUI A RENDU CETTE FONCTION NECESSAIRE, ET C'ETAIT UNE INVERSION COMPLETE.
 * La premiere version posait « `PredefinedUnits` = l'adversaire », mesure sur une BC d'Arene ou ce
 * champ ne porte effectivement que lui. Rejoue sur une BC A VAGUES (onslaught, tier 18) le
 * 2026-08-23, le meme champ portait **MES CINQ UNITES** : le `-100 %` s'est donc arme sur ma
 * propre equipe (9 cibles = mes 5 + les 4 de vague) et l'Immune sur PERSONNE (0 cible, tout
 * retranche). Le patch se retournait integralement. Une regle tiree d'UN mode n'est pas une regle.
 *
 * LA REGLE, ELLE, SE DERIVE -- structure identique mesuree sur les deux modes :
 *
 *     Player.Players = { "<playerId>": { TeamId, PlayerType, Name } }
 *        PlayerType 0 = le JOUEUR HUMAIN     (Name "player")
 *        PlayerType 1 = l'adversaire         (Name "enemy")
 *        PlayerType 2 = l'environnement      (Name "Environment", TeamId 0)
 *
 * Mon equipe = le `TeamId` du joueur a `PlayerType 0`. Est ADVERSE tout ce qui appartient a un
 * `TeamId` different. Chaque groupe de `PredefinedUnits`/`PredefinedMachines` porte son `Id`
 * (= playerId), et `Tiers[<tour>]` est KEYE par playerId -- donc les vagues se rattachent a un
 * camp, elles aussi.
 *
 * ⚠ ON REFUSE PLUTOT QUE DE DEVINER : s'il n'y a pas EXACTEMENT un joueur a `PlayerType 0`, on
 * rend `null`. Un patch sans cible est inerte et se voit ; un patch aux cibles INVERSEES gagne la
 * bataille pour l'adversaire.
 *
 * ⚠ ON PASSE PAR LA SERIALISATION, comme `dumpBattleConfig`. Lire `Player.Players` nativement
 * demanderait de marcher un `SortedDictionary` (arbre rouge-noir) a cles de TYPE VALEUR, sur le
 * thread principal, a la fenetre de chargement. Newtonsoft le fait deja, et rend la MEME forme que
 * `bc_apparitions.py` lit cote Python -- une seule forme pour deux lecteurs. */
function campsDeLaBc(bc: NativePointer): {
    miens: string[]; adverses: string[]; summonsDe: (ids: string[]) => string[];
} | null {
    let json: string | null;
    try { json = _serializeBcToJson(bc); } catch { return null; }
    if (json === null) return null;
    let o: Record<string, unknown>;
    try { o = JSON.parse(json) as Record<string, unknown>; } catch { return null; }

    const players = ((o["Player"] as Record<string, unknown> | null)
        ?? {})["Players"] as Record<string, Record<string, unknown>> | null | undefined;
    if (players === null || players === undefined) return null;
    const equipeDe = new Map<string, number>();
    const humains: string[] = [];
    for (const [pid, p] of Object.entries(players)) {
        if (p === null || typeof p !== "object") continue;
        const team = p["TeamId"];
        if (typeof team === "number") equipeDe.set(pid, team);
        if (p["PlayerType"] === 0) humains.push(pid);
    }
    if (humains.length !== 1) return null;          // ni deviner, ni choisir
    const monEquipe = equipeDe.get(humains[0]);
    if (monEquipe === undefined) return null;

    // ⛔ ON GARDE L'ID ENTIER, SUFFIXE COMPRIS -- ne PAS le reduire au `PureId` ici.
    // `IdunBattle.Configuration.UnitConfigId$$Equals` compare PureId, Rarity, Level ET IsBorrowed :
    // `necroNpc1Warrior` (Level nul) n'egale donc PAS l'unite `necroNpc1Warrior:18`. C'est le
    // convertisseur d'`environment-abilities` qui scinde `:<entier>` vers `Level` -- lui donner un
    // id deja rogne lui retire la seule information qui apparie.
    // Mesure du 2026-08-23 : en pre-rognant ici, le `-100 %` n'appariait AUCUN NPC (tous suffixes
    // par leur niveau) alors qu'il appariait tous les HEROS (jamais suffixes) -- ce qui se lisait
    // comme << les NPC sont immunises >>, une conclusion entierement fausse. Le meme patch, arme
    // avec les ids SUFFIXES ecrits a la main, mordait parfaitement sur les NPC d'onslaught.
    const miens = new Set<string>();
    const adverses = new Set<string>();
    const ranger = (pid: unknown, id: unknown): void => {
        if (typeof id !== "string" || id === "") return;
        const t = equipeDe.get(String(pid));
        if (t === undefined) return;               // joueur inconnu : on ne classe pas au hasard
        (t === monEquipe ? miens : adverses).add(id);
    };

    for (const g of (o["PredefinedUnits"] as Array<Record<string, unknown>> | null) ?? []) {
        for (const u of (g?.["Units"] as Array<Record<string, unknown>> | null) ?? []) {
            ranger(g?.["Id"], u?.["UnitId"]);
        }
    }
    for (const m of (o["PredefinedMachines"] as Array<Record<string, unknown>> | null) ?? []) {
        const mow = m?.["MachineOfWar"] as Record<string, unknown> | null;
        ranger(m?.["Id"], mow?.["UnitId"]);
    }
    const tiers = ((o["UnitSpawningOverTime"] as Record<string, unknown> | null)
        ?? {})["Tiers"] as Record<string, unknown> | null | undefined;
    for (const parJoueur of Object.values(tiers ?? {})) {
        if (parJoueur === null || typeof parJoueur !== "object") continue;
        for (const [pid, spec] of Object.entries(parJoueur as Record<string, unknown>)) {
            const aSpawner = (spec as Record<string, unknown> | null)?.["ToSpawn"];
            if (!Array.isArray(aSpawner)) continue;
            for (const s of aSpawner) ranger(pid, (s as Record<string, unknown> | null)?.["UnitId"]);
        }
    }
    return {
        miens: Array.from(miens), adverses: Array.from(adverses),
        summonsDe: indexerSummons(o),
    };
}

/** Le nom des abilities, LU AU RUNTIME. Mémoïsé : `dumpEnum` parcourt tous les champs de la classe.
 *
 *  ⚠ ON NE FIGE PAS CETTE TABLE. Un ordinal recopié dans le dépôt devient faux au changement de
 *  build, EN SILENCE -- et ici la faute serait invisible : on chercherait la mauvaise clé dans le
 *  catalogue, `Constants` sortirait `undefined`, et le résultat serait « cette unité ne summone
 *  rien ». Exactement le faux zéro qu'on vient de payer. */
let _nomsAbility: { actives: Map<number, string>; passives: Map<number, string> } | null = null;
function nomsAbility(): { actives: Map<number, string>; passives: Map<number, string> } {
    if (_nomsAbility !== null) return _nomsAbility;
    const inverser = (r: Record<string, string> | null): Map<number, string> => {
        const m = new Map<number, string>();
        for (const [nom, val] of Object.entries(r ?? {})) {
            const n = Number(val);
            if (Number.isFinite(n) && !m.has(n)) m.set(n, nom);
        }
        return m;
    };
    _nomsAbility = {
        actives: inverser(dumpEnum("IdunSharedAssembly.dll", "IdunBattle.Entities.Enum",
                                   "ActiveAbilityType")),
        passives: inverser(dumpEnum("IdunSharedAssembly.dll", "IdunBattle.Entities.Enum",
                                    "TriggeredAbilityType")),
    };
    return _nomsAbility;
}

/**
 * QUI PEUT INVOQUER QUOI — l'index `unité -> unités qu'elle fait apparaître`.
 *
 * ⛔ UN SUMMON N'EST DANS AUCUNE DES DEUX VOIES QU'ON LISAIT. Il n'est ni dans `PredefinedUnits`
 * (il n'existe pas encore), ni dans le pool déployable (le joueur ne le choisit pas) : il naît en
 * cours de bataille, sur l'équipe de SON INVOCATEUR. Un buff/debuff « par camp » qui ne le nomme
 * pas le laisse donc intact -- et c'est silencieux, comme toujours.
 *
 * ⚠ LA JOINTURE EST LE PIÈGE, ET ELLE A DÉJÀ RENDU UN FAUX ZÉRO. `BC.Abilities.*` est keyé par
 * NOM (`Incursion`, `Possession`, `HungeringSwarm`), alors que `BC.Units[].ActiveAbilities` porte
 * des ORDINAUX (`1022`). Joindre les deux directement rend **0 unité capable de summon** sur une
 * BC qui en contient 17 -- un zéro parfaitement lisible, et faux. L'ordinal passe par
 * `ActiveAbilityType` / `TriggeredAbilityType`.
 *
 * ⚠ DEUX ENUMS DIFFÉRENTS, ET LES ORDINAUX SE CHEVAUCHENT : `1022` vaut `BringerOfDespair` en
 * ACTIF et `AutoSummonOnDamage` en PASSIF. Prendre le mauvais ne lève pas, il désigne autre chose.
 * La voie (`ActiveAbilities` / `PassiveAbilities`) est ce qui tranche -- jamais l'ordinal seul.
 *
 * La constante s'appelle `unitId`, `unitId_2`, ou `unitIds` (liste séparée par des virgules) : on
 * retient toute clé qui CONTIENT `unitid`, plutôt que de fermer la liste sur les trois formes
 * connues -- une quatrième passerait inaperçue.
 */
function indexerSummons(o: Record<string, unknown>): (ids: string[]) => string[] {
    const noms = nomsAbility();
    const cat = (o["Abilities"] as Record<string, unknown> | null) ?? {};
    const catActives = (cat["ActiveAbilities"] as Record<string, unknown> | null) ?? {};
    const catPassives = (cat["PassiveAbilities"] as Record<string, unknown> | null) ?? {};
    const units = (o["Units"] as Array<Record<string, unknown>> | null) ?? [];

    // Les formes EXACTES que ce combat utilise, par `PureId` : la constante d'ability donne un id
    // NU (`tyranSmnSporeMine`), mais le combat peut porter `tyranNpc1Hormagaunt:1` ET `:pvp`. On
    // vise les deux -- `UnitConfigId$$Equals` compare le `Level`, donc un id nu n'apparie pas une
    // unité suffixée, et l'inverse non plus.
    const formesParPure = new Map<string, Set<string>>();
    for (const u of units) {
        const id = u?.["Id"];
        if (typeof id !== "string" || id === "") continue;
        const p = pureId(id);
        const s = formesParPure.get(p) ?? new Set<string>();
        s.add(id);
        formesParPure.set(p, s);
    }

    const depuisConfig = (cfg: unknown): string[] => {
        const c = (cfg as Record<string, unknown> | null)?.["Constants"];
        if (c === null || typeof c !== "object") return [];
        const out: string[] = [];
        for (const [k, v] of Object.entries(c as Record<string, unknown>)) {
            if (!k.toLowerCase().includes("unitid")) continue;
            for (const x of String(v).split(",")) {
                const t = x.trim();
                if (t !== "") out.push(t);
            }
        }
        return out;
    };

    // `unité -> summons`, indexé sur l'id ENTIER **et** sur son `PureId` : l'appelant nous passe
    // des cibles qui peuvent porter un suffixe (`tyranNpc3Termagant:pvp`) ou non.
    const parUnite = new Map<string, Set<string>>();
    for (const u of units) {
        const id = u?.["Id"];
        if (typeof id !== "string" || id === "") continue;
        const trouves = new Set<string>();
        const collecter = (aid: unknown, table: Map<number, string>,
                           catalogue: Record<string, unknown>): void => {
            if (typeof aid !== "number") return;
            const nom = table.get(aid);
            if (nom === undefined) return;
            for (const s of depuisConfig(catalogue[nom])) {
                // On pose l'id NU (ce que dit la config) ET toutes les formes que ce combat
                // utilise pour le même `PureId`.
                trouves.add(s);
                for (const f of formesParPure.get(pureId(s)) ?? []) trouves.add(f);
            }
        };
        for (const a of (u["ActiveAbilities"] as unknown[] | null) ?? []) {
            collecter(a, noms.actives, catActives);
        }
        for (const a of (u["PassiveAbilities"] as unknown[] | null) ?? []) {
            collecter(a, noms.passives, catPassives);
        }
        // La RELIQUE est un `TriggeredAbilityType` comme les passifs -- et elle summone
        // (`CallInReinforcements`). L'oublier laisserait un porteur de relique invoquer en paix.
        collecter(u["TertiaryAbility"], noms.passives, catPassives);
        if (trouves.size === 0) continue;
        for (const cle of [id, pureId(id)]) {
            const s = parUnite.get(cle) ?? new Set<string>();
            for (const t of trouves) s.add(t);
            parUnite.set(cle, s);
        }
    }

    return (ids: string[]): string[] => {
        const out = new Set<string>();
        for (const id of ids) {
            for (const cle of [id, pureId(id)]) {
                for (const s of parUnite.get(cle) ?? []) out.add(s);
            }
        }
        return Array.from(out);
    };
}

/** Les `PureId` que le CALENDRIER DE VAGUES programme -- `UnitSpawningOverTime.Tiers`.
 *
 *  `null` = PAS LU (jamais a confondre avec « aucune vague », qui est `[]`).
 *
 *  ⚠ ON PASSE PAR LA SERIALISATION, ET C'EST LE CHOIX SUR. `Tiers` est un
 *  `Dictionary<Int32, Dictionary<PlayerId, Wave>>` : marcher ses `_entries` a la main demanderait
 *  de decoder des cles de TYPE VALEUR imbriquees. Newtonsoft sait deja le faire -- c'est la meme
 *  voie que `dumpBattleConfig`, et la meme forme que `bc_apparitions.py` lit cote Python
 *  (`Tiers[<round>][<player>].ToSpawn[].UnitId`), donc une seule forme pour deux lecteurs.
 *
 *  ⚠ LE COUT EST CONDITIONNEL, ET C'EST POURQUOI L'APPELANT COMPTE D'ABORD : on ne serialise la BC
 *  (200 a 600 Ko) QUE si `Tiers` porte au moins un tour. Une BC d'Arene n'en porte aucun, donc le
 *  cas courant ne paie rien. */
function unitesDesVagues(bc: NativePointer): string[] | null {
    let json: string | null;
    try { json = _serializeBcToJson(bc); } catch { return null; }
    if (json === null) return null;
    try {
        const o = JSON.parse(json) as Record<string, unknown>;
        const uso = o["UnitSpawningOverTime"] as Record<string, unknown> | null | undefined;
        const tiers = (uso ?? {})["Tiers"] as Record<string, unknown> | null | undefined;
        if (tiers === null || tiers === undefined) return [];
        const out = new Set<string>();
        for (const parJoueur of Object.values(tiers)) {
            if (parJoueur === null || typeof parJoueur !== "object") continue;
            for (const spec of Object.values(parJoueur as Record<string, unknown>)) {
                if (spec === null || typeof spec !== "object") continue;
                const aSpawner = (spec as Record<string, unknown>)["ToSpawn"];
                if (!Array.isArray(aSpawner)) continue;
                for (const s of aSpawner) {
                    const id = (s as Record<string, unknown> | null)?.["UnitId"];
                    if (typeof id === "string" && id !== "") out.add(pureId(id));
                }
            }
        }
        return Array.from(out);
    } catch { return null; }
}

function nombreDeVagues(bc: NativePointer): number | null {
    try {
        const uso = champPointeur(bc, "UnitSpawningOverTime");
        if (estRefus(uso)) return null;
        const tiers = champPointeur(uso as NativePointer, "Tiers");
        if (estRefus(tiers)) return null;
        const d = tiers as NativePointer;
        const off = getFieldOffset(d.readPointer(), "_count");
        return off < 0 ? null : d.add(off).readS32();
    } catch { return null; }
}

// --- Inspection RPC ---

interface BattleConfigSnapshot {
    ok: boolean;
    bcPtr?: string;
    id?: string | null;
    /** GameMode enum value (Campaign=0, PvP=1, ..., MoWEvent=15). null si Nullable.hasValue=false. */
    gameMode?: number | null;
    /** SyncPvpRuleSet enum value (Deathmatch=0, Heist=1, ...). null si Nullable.hasValue=false. */
    ruleSet?: number | null;
    spawnPointSetIndex?: number;
    randomizeAiInput?: boolean;
    board?: {
        ptr: string;
        id: string | null;
        width: number;
        height: number;
    };
    palette?: { tileTypeCount: number };
    templates?: {
        unitTemplateCount: number;
        sample: Array<{ id: string | null; visualId: string | null;
                        faction: string | null; health: number }>;
    };
    predefinedUnits?: Array<{
        playerId: number;
        unitCount: number;
        units: Array<{ unitId: string | null }>;
    }>;
    /** List<PredefinedMachinesOfWar> — MoW à deployer auto par
     * runner.Initialize(). Souvent vide en mode Campaign (qui hardcode
     * SupportsMachinesOfWar=false → le GameModeSource ne peuple pas). */
    predefinedMachines?: Array<{
        playerId: number;
        unitId: string | null;
    }>;
    err?: string;
}

function inspectBattleConfig(): BattleConfigSnapshot {
    const bc = getLiveBattleConfig();
    if (bc === null) {
        return {
            ok: false,
            err: "no live BattleConfiguration — amorce not run OR " +
                 "LoadBattle hasn't fired yet (amorce retreats too early?)",
        };
    }

    const snap: BattleConfigSnapshot = { ok: true, bcPtr: bc.toString() };

    try {
        snap.id = readIl2cppString(bc.add(BC_OFF_ID).readPointer());
        // Nullable<GameMode>/Nullable<SyncPvpRuleSet> : hasValue @+0, value @+4
        snap.gameMode = bc.add(BC_OFF_GAMEMODE_HASVALUE).readU8() !== 0
            ? bc.add(BC_OFF_GAMEMODE_VALUE).readS32() : null;
        snap.ruleSet = bc.add(BC_OFF_RULESET_HASVALUE).readU8() !== 0
            ? bc.add(BC_OFF_RULESET_VALUE).readS32() : null;
        snap.spawnPointSetIndex = bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).readS32();
        snap.randomizeAiInput = bc.add(BC_OFF_RANDOMIZE_AI).readU8() !== 0;
    } catch (e) {
        snap.err = `header read: ${(e as Error).message}`;
    }

    // Board
    try {
        const board = bc.add(BC_OFF_BOARD).readPointer();
        if (!board.isNull()) {
            snap.board = {
                ptr: board.toString(),
                id: readIl2cppString(board.add(BCBC_OFF_ID).readPointer()),
                width: board.add(BCBC_OFF_WIDTH).readS32(),
                height: board.add(BCBC_OFF_HEIGHT).readS32(),
            };
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | board: ${(e as Error).message}`;
    }

    // Tiles palette
    try {
        const tiles = readManagedList(bc.add(BC_OFF_TILES).readPointer());
        if (tiles) snap.palette = { tileTypeCount: tiles.size };
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | tiles: ${(e as Error).message}`;
    }

    // Unit templates (with a small sample to verify offsets)
    try {
        const units = readManagedList(bc.add(BC_OFF_UNITS).readPointer());
        if (units) {
            const sample = [];
            // Bumped to 30 to find MoW/PvP-suffixed templates.
            const N = Math.min(units.size, 200);
            for (let i = 0; i < N; i++) {
                const uc = readListItem(units, i);
                if (uc.isNull()) continue;
                sample.push({
                    id: readIl2cppString(uc.add(UC_OFF_ID).readPointer()),
                    visualId: readIl2cppString(
                        uc.add(UC_OFF_VISUAL_ID).readPointer()),
                    faction: readIl2cppString(
                        uc.add(UC_OFF_FACTION).readPointer()),
                    health: uc.add(UC_OFF_HEALTH).readS32(),
                });
            }
            snap.templates = {
                unitTemplateCount: units.size,
                sample,
            };
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | templates: ${(e as Error).message}`;
    }

    // PredefinedMachines (MoW deployment list)
    try {
        const pm = readManagedList(
            bc.add(BC_OFF_PREDEFINED_MACHINES).readPointer());
        if (pm) {
            const mows: Array<{ playerId: number; unitId: string | null }> = [];
            for (let i = 0; i < pm.size; i++) {
                const entry = readListItem(pm, i);
                if (entry.isNull()) continue;
                const playerId = entry.add(PMOW_OFF_PLAYER_ID).readS32();
                let unitId: string | null = null;
                try {
                    const machinePtr = entry.add(PMOW_OFF_MACHINE).readPointer();
                    if (!machinePtr.isNull()) {
                        unitId = readIl2cppString(
                            machinePtr.add(PMOW_OFF_UNIT_ID).readPointer());
                    }
                } catch { /* leave null */ }
                mows.push({ playerId, unitId });
            }
            snap.predefinedMachines = mows;
        } else {
            snap.predefinedMachines = [];
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | predefMachines: ${(e as Error).message}`;
    }

    // PredefinedUnits (composition per player)
    try {
        const pu = readManagedList(bc.add(BC_OFF_PREDEFINED_UNITS).readPointer());
        if (pu) {
            const players: BattleConfigSnapshot["predefinedUnits"] = [];
            for (let i = 0; i < pu.size; i++) {
                const grp = readListItem(pu, i);
                if (grp.isNull()) continue;
                const playerId = grp.add(PU_OFF_ID).readS32();
                const unitsList = readManagedList(
                    grp.add(PU_OFF_UNITS).readPointer());
                const units: Array<{ unitId: string | null }> = [];
                if (unitsList) {
                    for (let j = 0; j < unitsList.size; j++) {
                        const pUnit = readListItem(unitsList, j);
                        if (pUnit.isNull()) continue;
                        units.push({
                            unitId: readIl2cppString(
                                pUnit.add(PUNIT_OFF_UNIT_ID).readPointer()),
                        });
                    }
                }
                players.push({
                    playerId,
                    unitCount: unitsList?.size ?? 0,
                    units,
                });
            }
            snap.predefinedUnits = players;
        }
    } catch (e) {
        snap.err = (snap.err ?? "") + ` | predef: ${(e as Error).message}`;
    }

    return snap;
}

// --- Patch / mutation API ---
//
// A `BattleConfigPatch` describes a set of in-place mutations to apply to
// the next BattleConfiguration assembled by LoadBattle. Stored in module
// state via `setBattleConfigPatch`; applied automatically by the
// LoadBattle.onLeave hook on CampaignGameModeSource. `consumeOnce` (default
// true) auto-clears the patch after a single application so a subsequent
// human-driven battle isn't accidentally affected.

interface BattleConfigPatch {
    // ⛔ `aiUnits`, `aiUnitsAt` ET `templateOverrides` RETIRÉS (2026-08-23), avec
    // `UnitStatsOverride`, l'index `templatesById` et `mergeAiUnitsSpec`. Reliques de l'époque où
    // le harnais fabriquait la BC lui-même ; depuis qu'on laisse la SOURCE la monter, plus rien ne
    // les appelle — mesuré, ZÉRO appelant dans le dépôt, la seule occurrence restante étant une
    // docstring de `unit_map.py`.
    //
    // ⚠ ET DEUX D'ENTRE EUX MENTAIENT, CE QUI EST PIRE QU'INUTILE :
    //
    //   * `aiUnitsAt` était déclaré, documenté... et SANS EFFET : `mergeAiUnitsSpec` rendait `null`
    //     dessus, sous un « TODO: handle partial slot replacement ». Un champ qui no-ope en
    //     silence est un piège, pas une fonctionnalité inachevée.
    //
    //   * le swat d'`aiUnits` sautait la validation par template en invoquant
    //     « BattleConfiguration.Units holds the PLAYER roster, not AI enemies ». C'est FAUX :
    //     mesuré sur 6 replays RÉELS, `BC.Units` porte ~175 gabarits qui contiennent les DEUX
    //     camps — 19/19 des ennemis de `PredefinedUnits` y sont, et 23/23 des unités du joueur.
    //     La validation était donc possible depuis le début ; c'est la justification écrite qui
    //     l'a fait renoncer.
    //
    // Le patch de stats a d'ailleurs un pendant vivant et meilleur : `rl_duel --unit-modifier`,
    // qui pousse de VRAIS `StatModifier` par une Operation là où celui-ci écrasait un scalaire du
    // template.

    /** Toggle the BattleConfiguration.RandomizeAiInput flag. */
    randomizeAi?: boolean;
    /** Set the spawn-point preset index (each board has 1-N presets). */
    spawnPointSetIndex?: number;
    /** Le calendrier de vagues -- `BC.UnitSpawningOverTime.Tiers`, forme
     *  `{ "<tour>": { "<playerId>": <Wave> } }`.
     *
     *  ⚠ APPLIQUÉ AU `LoadBattle.onLeave`, DONC SUR LA BC QUE LA SOURCE VIENT DE PRODUIRE, en
     *  mémoire -- aucune sérialisation, aucune substitution. C'est le seul moment où le
     *  calendrier est encore modifiable : `OperationProcessor$$AddPlayer(..., spawnsPerTurn,
     *  ...)` le transcrit dans le `PlayerComponent` au SETUP, et ne le relit jamais.
     *
     *  ⚠ LES VALEURS QUI MARCHENT SE LISENT SUR UNE BC PRODUITE PAR LE JEU (un onslaught en
     *  porte six). Mesuré le 2026-08-22 : `SpawnPointTag` vaut `"defaultGroup"` -- et il ne
     *  s'apparie à AUCUN `Tag` du board, dont les 17 points portent la chaîne vide. C'est une
     *  clé de CONVENTION du moteur, pas une référence au plateau : la « dériver du board » est
     *  un raisonnement faux qui se donne l'air rigoureux. `Index` est incrémenté d'une vague à
     *  l'autre (0,1,2,…), pas remis à zéro. */
    unitSpawningOverTime?: unknown;
    /** Compagnons de `Tiers` dans le nœud, conservés à leur valeur par défaut sauf demande. */
    useAtomicGroup?: boolean;
    useSpawnPointFromUnitIndex?: boolean;
    /** Les abilities d'ENVIRONNEMENT à INSTALLER -- `BC.EnvironmentAbilities`, le RÉCEPTACLE,
     *  et surtout PAS le catalogue `BC.Abilities.EnvironmentAbilities` (166 définitions).
     *
     *  `abilityType` est un ordinal de `IdunBattle.Entities.Enum.TriggeredAbilityType`, `niveau`
     *  choisit dans les tableaux de variables de la config (0 = le natif n'arme rien).
     *
     *  ⚠ CE QUI DÉCIDE DE LA CIBLE EST LE `CreateTrigger` DE L'ABILITY, PAS UN ARGUMENT D'ICI --
     *  il n'existe aucun champ « équipe » à passer. Mesuré au décompilé sur `t6dpr4k06g` :
     *    `EnvReinforcementShield` (1270) = `On(UnitAdded) | On(InitialMatchUnitAdded)`
     *        `AND IsHero(Actor) AND IsInTeam(Actor, 1)` -> l'équipe du JOUEUR (`TeamId=1`,
     *        `playerId=11`, `PlayerType=0` dans `BC.Player.Players`) ;
     *    `EnvStartProtection` (1280) = `On(TurnStart_EffectActivation)` gardé par
     *        `TotalTurnsFinished == <const>`, cible `_allAliveUnits - _currentTurnUnits`,
     *        donc le camp qui NE joue PAS -- team-agnostique, et pas forcément le tien. */
    environmentAbilities?: Array<{ abilityType: number; niveau: number }>;
    /** Les DÉFINITIONS à poser dans le CATALOGUE -- `BC.Abilities.EnvironmentAbilities`, le
     *  dictionnaire à clé CHAÎNE, et surtout PAS `env.AbilitiesConfigurations` (clé de type
     *  valeur, dont l'insertion à la main a tué le process le 2026-08-21).
     *
     *  Deux usages, tous deux mesurés :
     *    * DOTER une ability qui n'a aucune config ici -- sans quoi son premier
     *      `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` LÈVE, et ça remonte
     *      en « system error » au cast ou au déploiement (#254) ;
     *    * CHANGER une constante existante -- ex. `EnhancementDamageBoost.extraDmgPct` de `20`
     *      à `-100`, qui met les dégâts de la cible à ZÉRO (multiplicateur `1 + pct/100`, borné
     *      à zéro en dessous de -100).
     *
     *  ⚠ Les valeurs sont des CHAÎNES, comme dans la BC (`{"extraDmgPct": "-100"}`).
     *
     *  ⚠ LA CLÉ EST UN ORDINAL, PAS UN NOM, et ce n'est pas un choix de confort : le
     *  dictionnaire du catalogue est keyé par un `TriggeredAbilityConfigId` (un TYPE VALEUR --
     *  le JSON le fait passer pour une chaîne), donc on ne l'écrit pas soi-même. On passe par
     *  `AbilitiesConfiguration$$AddEnvironmentAbility(TriggeredAbilityType, …)`, qui prend un
     *  ENUM PLAT et fabrique la clé lui-même.
     *
     *  ⚠ CONSÉQUENCE : les VARIANTES sont hors d'atteinte. `EnhancementAddTrait:Stationary` est
     *  un `TriggeredAbilityType` PLUS un `VariantId`, et l'ordinal seul ne l'exprime pas. Les 106
     *  variantes restent joignables par la voie SEED BC (Newtonsoft y construit les clés), pas
     *  par ce patch. `nom` est purement DÉCORATIF -- il n'entre dans aucune clé. */
    environmentAbilityConfigs?: Array<{ abilityType: number; nom?: string;
                                        constants?: Record<string, string>;
                                        variables?: Record<string, string[]> }>;
    /** Les ENHANCEMENTS -- la SECONDE liste du réceptacle, et la SEULE qui cible par unité NOMMÉE.
     *
     *  `environmentAbilities` (ci-dessus) installe des abilities dont la cible est écrite dans
     *  leur `CreateTrigger` : rien à passer. Une entrée d'enhancement porte, elle, une liste
     *  `Targets` d'`unitId` que `IdunBattleLogic.Entities.DSLTriggers$$IsEnhancementTarget`
     *  confronte -- c'est l'équivalent du `unitAmount` de l'UI d'incursion, et `stack` celui de
     *  son `stacks`. Le catalogue de la BC porte **106** variantes `EnhancementAddTrait:<Trait>`
     *  déjà configurées, dont le gameconfig n'en expose que quatre.
     *
     *  ⚠ Une ability gardée par `IsEnhancementTarget` sans `cibles` ne tire JAMAIS -- le retour
     *  le DIT (`note`) plutôt que de le laisser deviner. */
    environmentEnhancements?: Array<envAbilities.SpecEnhancement>;
    // ⛔ `viderPredefinedUnits` A ÉTÉ RETIRÉ (2026-08-23) — voir le pavé au site d'application,
    // dans `applyPatchToConfig`. En deux lignes : il vidait `BC.PredefinedUnits` pour rattraper une
    // BC fabriquée par le ctor sandbox, qui confond catalogue et pose. Sur une BC montée par sa
    // SOURCE — la forme que le jeu produit vraiment — `PredefinedUnits` porte l'ADVERSAIRE, et le
    // vider effacerait l'ennemi. Le besoin disparaît avec le ctor, pas avec l'outil.

    // ⛔ `playerTeamIds` ET `spawnGroupPlayerIndexes` ONT ÉTÉ RETIRÉS (2026-08-23), 327 lignes.
    //
    // Ils réécrivaient `BC.Player.Players[].TeamId` (par parcours du dictionnaire ET de l'arbre
    // rouge-noir d'un `SortedDictionary`) et `Board.SpawnPointSets[].SpawnPointGroups[]
    // .TeamWithPlayerIndex`, pour contourner « le camp adverse disparaît quand on inverse les
    // équipes ».
    //
    // ⚠ CE SYMPTÔME N'ÉTAIT PAS LE LEUR. Mesuré et clos par #10046 : inverser les `TeamId`
    // FONCTIONNE côté natif -- les cinq abandons muets de la pose sont négatifs et les 10 unités
    // montent. La disparition venait d'une COLLISION DE TUILES causée par un `TWPI 0` codé en dur
    // dans `rl_duel.py`, donc du HARNAIS. Deux mécanismes de contournement sont donc restés
    // armés sans cible, avec leur propre piège d'idempotence (« appliqué deux fois, ça se
    // défait ») et un parcours d'arbre rouge-noir à borne dure sur le thread principal du jeu.
    //
    // Ce qu'ils visaient reste atteignable par `environmentEnhancements` ci-dessus, qui vise des
    // unités NOMMÉES sans toucher à aucune équipe.
    // Détail : `docs/rl/case-10046-pose-des-unites-predefinies.md` §5ter.

    // ⛔ `turnOrder` RETIRÉ (2026-08-23), avec `ecrireOrdreDesTours`, `--ordre-des-tours` et
    // `--adversaire-ouvre`. Aucun appelant par programme : les probes qui citent `TurnOrder`
    // le LISENT depuis un seed BC sur disque (`probe_889r9`, `probe_462r4…`, `probe_1083r3`), elles
    // n'écrivaient jamais par ce canal. Seule une invocation manuelle d'`env_ability_patch`
    // l'atteignait.
    //
    // ⚠ CE QU'ON PERD, ET IL FAUT LE SAVOIR AVANT DE LE REFAIRE : c'était le SEUL levier du
    // bouclier d'environnement. `EnvStartProtection` (1280) cible `_allAliveUnits -
    // _currentTurnUnits` au tout premier `TurnStart_EffectActivation` (gardé par
    // `TotalTurnsFinished == 0`) : elle protège LE CAMP QUI N'OUVRE PAS. Le défaut `[11, 12, 13]`
    // fait ouvrir le joueur, donc le bouclier va à l'adversaire — mesuré le 2026-08-22 en bataille
    // réelle, 7 boucliers de 500 partis du mauvais côté. Mettre `12` en tête retournait la
    // soustraction.
    //
    // ⚠ ET LA VOIE ÉVIDENTE POUR LE REFAIRE EST FAUSSE : le ciblage de cette ability est
    // team-agnostique (aucun `IsInTeam`), donc passer par les ÉQUIPES n'y change rien.
    // `EnvReinforcementShield` (1270), la seule qui vise nommément l'équipe du joueur, a 0
    // occurrence dans le gameconfig. Si le besoin revient, c'est bien `BC.Player.TurnOrder` qu'il
    // faut réordonner — une `List<PlayerId>` de structs à 4 octets, en PERMUTATION seulement.

    /** If true (default), the patch is cleared after a single application. */
    consumeOnce?: boolean;
}

interface PatchApplyResult {
    ok: boolean;
    appliedAt: string;            // ISO timestamp
    bcPtr: string;
    operations: string[];         // human-readable log of what was changed
    warnings: string[];
}

let pendingPatch: BattleConfigPatch | null = null;
let lastApply: PatchApplyResult | null = null;

/** Y a-t-il un patch en attente ? Pour les gardes qui doivent DECIDER dans le jeu, sans RPC.
 *
 *  ⛔ EXPOSE PLUTOT QUE DUPLIQUE. `pendingPatch` est module-prive ; un garde qui tiendrait son
 *  propre drapeau << un patch est arme >> derivereait en silence des que quelqu'un arme ou
 *  retire par un autre chemin -- et un garde qui se croit inutile ne protege rien. */
export function patchEnAttente(): BattleConfigPatch | null { return pendingPatch; }

/** RETIRER le patch en attente, depuis le jeu. Rend ce qui a ete retire (`null` = rien).
 *  Le seul appelant prevu est `garde-boss-patch.ts`, avant qu'une tentative de boss soit
 *  DEPENSEE : le retrait doit avoir lieu AVANT que la BC soit construite, donc bien avant
 *  `LoadBattle.onLeave` ou le patch s'appliquerait. */
export function retirerPatchEnAttente(): BattleConfigPatch | null {
    const p = pendingPatch;
    pendingPatch = null;
    return p;
}
/** Le dernier passage REFUSE au `LoadBattle.onLeave` faute d'avoir rendu une `BattleConfiguration`.
 *  Publie a cote de `lastApply`, jamais a sa place : c'est ce qui distingue « le hook n'est pas
 *  pose » de « le hook est pose, mais l'ancrage vise un corps deduplique ». */
let lastRejet: {
    rejeteA: string; source: string; classeRendue: string | null; ptr: string; motif: string;
} | null = null;
/** Le RECENSEMENT de la pose. `null` = pose pas encore tentée -- jamais à lire comme « aucune ».
 *
 *  `posees`               : `<Classe>.<chargeur>` réellement ancrés — un patch ne peut mordre QUE là.
 *  `couvertesParHeritage` : pas de chargeur propre, mais celui dont elles héritent EST ancré.
 *  `refuseesDecision`     : écartées par `SOURCES_REFUSEES` (elles touchent d'autres joueurs).
 *  `refuseesHeritage`     : leur chargeur EST le corps de la base — l'ancrer déborderait sur tout.
 *  `nonResolues`          : implémentent `IGameModeSource` et ne sont couvertes par RIEN. Un vrai
 *                           trou, et le seul champ à lire comme tel.
 *
 *  ⚠ Les cinq sont publiés parce qu'un armement doit pouvoir se CONFRONTER à ce qui est ancré.
 *  Le 2026-08-23, l'onslaught n'était couvert par rien et le seul endroit qui le disait était une
 *  ligne de `log` : un `pending` parfaitement visible, et la certitude fausse que ça mordrait. */
let sourcesAncrees: {
    posees: string[]; nonResolues: string[]; couvertesParHeritage: string[];
    refuseesHeritage: string[]; refuseesDecision: string[];
} | null = null;
let sourcesRefusees: string[] = [];

// ⛔ LES NEUF OFFSETS D'ÉCRITURE DE `UnitConfiguration` SONT RETIRÉS AVEC `templateOverrides`
// (2026-08-23) : `Armor` 0x44, `FixedArmor` 0x48, `Shield` 0x4C, `Movement` 0x54, `Range` 0x5C,
// `CritChance` 0x60, `CritDamage` 0x64, `BlockChance` 0x68, `BlockDamage` 0x6C.
//
// ⚠ ON GARDE LA MÉTHODE, PAS LES NOMBRES — ET C'EST LE CHOIX PRUDENT. Un offset conservé « au cas
// où » ne se re-vérifie jamais : il survit au changement de build, reste plausible, et écrit à
// côté en silence. Ceux-ci se re-dérivent en une commande, sur le build CHARGÉ :
//     rpc `classFields` { ns: "IdunBattle.Configuration", cls: "UnitConfiguration" }
// (c'est ainsi qu'on a trouvé `IdunRunner.<Configuration>k__BackingField@+0xb0` le même jour).
//
// Les offsets de LECTURE restent déclarés plus haut : `inspectBattleConfig` les exerce à chaque
// appel, donc eux sont confrontés en permanence.

// --- LE CALENDRIER DE VAGUES, ÉCRIT DANS LA BC ---------------------------------------------
//
// ⚠ FOYER UNIQUE. `bcWaveSet` (wave-inject.ts) et le patch `LoadBattle.onLeave` écrivent tous
// deux `BC.UnitSpawningOverTime` ; deux implémentations dériveraient, et celle qui ne sert pas
// pourrirait en silence. Le champ se résout PAR NOM sur la classe de l'objet — les offsets en
// dur de ce fichier valent chacun pour UNE classe, en appliquer un à une autre lirait un champ
// voisin et rendrait un pointeur plausible.
//
// ⚠ ON DÉSÉRIALISE L'OBJET ENTIER PLUTÔT QUE DE LE CONSTRUIRE. `Tiers` est un
// `Dictionary<Int32, Dictionary<PlayerId, Wave>>` : le bâtir à la main exigerait de boxer des
// clés de type valeur, ce qui a déjà tué le process le 2026-08-21 sur
// `EnvironmentAbilities.AbilitiesConfigurations`. Newtonsoft convertit les clés JSON (chaînes)
// vers `Int32` — c'est la forme que le jeu SÉRIALISE lui-même, on la lui rend telle quelle.
export interface EcritureCalendrier {
    ok: boolean;
    offset?: string;
    noeudAvant?: string;
    noeudApres?: string;
    relu?: boolean;
    octetsJson?: number;
    error?: string;
}

export function ecrireCalendrierDeVagues(
    bc: NativePointer, tiers: unknown,
    opts?: { useAtomicGroup?: boolean; useSpawnPointFromUnitIndex?: boolean },
): EcritureCalendrier {
    let klass: NativePointer;
    try { klass = bc.readPointer(); } catch (e) {
        return { ok: false, error: "classe de la BC illisible : " + (e as Error).message };
    }
    if (klass.isNull()) return { ok: false, error: "la BC porte une classe NULLE" };
    let nomClasse: string;
    try { nomClasse = cstr(class_get_name(klass) as NativePointer); }
    catch (e) { return { ok: false, error: "nom de classe illisible : " + (e as Error).message }; }
    if (nomClasse !== "BattleConfiguration") {
        return {
            ok: false,
            error: "l'objet est un `" + nomClasse + "`, pas une `BattleConfiguration` -- écrire "
                + "dedans corromprait un objet d'un autre type",
        };
    }
    let off = -1;
    for (const nom of ["UnitSpawningOverTime", "<UnitSpawningOverTime>k__BackingField"]) {
        off = getFieldOffset(klass, nom);
        if (off >= 0) break;
    }
    if (off < 0) {
        return {
            ok: false,
            error: "`BattleConfiguration.UnitSpawningOverTime` ABSENT sous ses deux écritures "
                + "connues -- chemin PÉRIMÉ sur ce build",
        };
    }
    let avant: string;
    try { avant = bc.add(off).readPointer().toString(); }
    catch (e) { return { ok: false, error: "lecture du champ : " + (e as Error).message }; }

    if (!isDeserializerReady()) {
        return {
            ok: false,
            error: "`JsonConvert.DeserializeObject` non résolu -- le nœud ne peut pas être "
                + "construit sans lui, et je ne le fabrique pas à la main",
        };
    }
    const kUso = findClassAnywhere("IdunBattle.Configuration",
                                   "UnitSpawningOverTimeConfiguration");
    if (!kUso) {
        return {
            ok: false,
            error: "classe `IdunBattle.Configuration.UnitSpawningOverTimeConfiguration` "
                + "introuvable -- chemin PÉRIMÉ sur ce build",
        };
    }
    const json = JSON.stringify({
        Tiers: tiers,
        UseAtomicGroup: opts?.useAtomicGroup ?? false,
        UseSpawnPointFromUnitIndex: opts?.useSpawnPointFromUnitIndex ?? false,
    });
    let noeud: NativePointer;
    try { noeud = deserializeFromJson(json, kUso); }
    catch (e) {
        return {
            ok: false,
            error: "désérialisation d'`UnitSpawningOverTimeConfiguration` : "
                + (e as Error).message,
        };
    }
    if (noeud.isNull()) {
        return { ok: false, error: "nœud désérialisé en NUL -- rien n'a été écrit" };
    }
    // ⚠ ENRACINER AVANT D'ÉCRIRE : le GC d'IL2CPP ne voit pas notre référence JS, et un objet
    // frais peut être collecté entre sa création et l'écriture du champ.
    gcRoot.add(noeud);
    try { bc.add(off).writePointer(noeud); }
    catch (e) { return { ok: false, error: "écriture du champ : " + (e as Error).message }; }
    let apres: string;
    try { apres = bc.add(off).readPointer().toString(); } catch { apres = "?"; }
    return {
        ok: true, offset: "+0x" + off.toString(16), noeudAvant: avant, noeudApres: apres,
        relu: apres === noeud.toString(), octetsJson: json.length,
    };
}

// ---------------------------------------------------------------------------------------
// LES ABILITIES D'ENVIRONNEMENT -- INSTALLER, ET SAVOIR SI ELLES SONT INSTALLABLES.
//
// DEUX CHAMPS PORTENT CE NOM, ET LES CONFONDRE EST LE PIEGE :
//
//   `BattleConfiguration.EnvironmentAbilities`        <- le RECEPTACLE : ce qui est INSTALLE
//   `BattleConfiguration.Abilities.EnvironmentAbilities` <- le CATALOGUE : 166 DEFINITIONS
//
// Le premier dit « cette bataille joue ces abilities-la » ; le second dit « voici a quoi
// ressemble chacune ». Un grep de la BC trouve un nom dans le SECOND et fait croire au PREMIER
// -- c'est la mesure du 2026-08-22 sur `EnvEndBombardment`, trouve TROIS fois dans une BC dont
// la liste des installees etait VIDE.
//
// ⚠ ET LE CATALOGUE EST UNE CONDITION QUI N'EMET AUCUN SIGNAL, exactement comme le `UnitId`
// d'une vague (cf. `unitSpawningOverTime` ci-dessus) : `EnvReinforcementShield` est ABSENT du
// catalogue de `data/seed-bc.json` (166 entrees), alors que `EnvStartProtection` y est avec son
// `shieldHp: 500`. On PUBLIE donc, pour chaque ability demandee, si son nom est au catalogue --
// pour qu'un echec ait un NOM AVANT d'etre observe, au lieu de trois causes accusees a tort.
export interface EcritureEnvironnement {
    ok: boolean;
    offset?: string;
    noeudAvant?: string;
    noeudApres?: string;
    relu?: boolean;
    /** Ce qui est REELLEMENT dans le receptacle -- compte des membres, pas un « configure ». */
    installees?: Record<string, unknown>;
    /** FUSION dans le receptacle de la progression, ou receptacle NEUF. Les deux n'ont pas les
     *  memes consequences : la seconde jetterait ce que le mode avait pose. */
    voie?: string;
    /** Le nombre de definitions du catalogue. `null` = pas lu. Un catalogue a 0 et un catalogue
     *  a 166 ne racontent pas la meme histoire quand rien n'apparait en bataille. */
    tailleCatalogue?: number | null;
    detail?: Array<Record<string, unknown>>;
    /** La SECONDE liste, quand on lui a demandé quelque chose. Séparée de `detail` : les deux
     *  listes ne ciblent pas pareil, les confondre dans un même tableau les ferait lire pareil. */
    detailEnhancements?: Array<Record<string, unknown>>;
    error?: string;
}

/** Le nom d'une ability est-il au CATALOGUE de cette BC ?
 *
 *  Tri-etat : `null` = PAS MESURE, jamais rendu comme un `false` -- « absent » et « pas
 *  regarde » n'autorisent pas la meme conclusion.
 *
 *  ⚠ CETTE SONDE A MENTI, ET LA FORME DU MENSONGE EST INSTRUCTIVE. Premiere version : elle
 *  appelait `ContainsKey` avec une chaine managee, SANS verifier le type de cle du
 *  dictionnaire. Mesure du 2026-08-22 : elle a rendu ABSENT pour `EnvStartProtection` alors
 *  que le catalogue vivant le PORTE (166 definitions, verifie en serialisant la BC). Une
 *  reponse UNIFORME sur toutes les entrees est la signature d'une sonde cassee, pas d'un
 *  catalogue vide -- et elle a failli faire accuser le catalogue a la place du vrai defaut.
 *
 *  Le correctif n'est pas un ajustement : c'est un REFUS DE REPONDRE quand la question ne se
 *  pose pas. On lit le type du parametre de `ContainsKey` ; si ce n'est pas `System.String`,
 *  la cle est un type valeur (un `TriggeredAbilityConfigId`, serialise en nom mais pas stocke
 *  comme tel) et l'appel n'a aucun sens -- on rend `null`. */
function catalogueContient(bc: NativePointer, nom: string): boolean | null {
    try {
        const abilities = champPointeur(bc, "Abilities");
        if (estRefus(abilities)) return null;
        const dict = champPointeur(abilities as NativePointer, "EnvironmentAbilities");
        if (estRefus(dict)) return null;
        const d = dict as NativePointer;
        const mHas = findMethodByParamCount(d.readPointer(), "ContainsKey", 1);
        if (!mHas) return null;
        // LE CRAN QUI MANQUAIT : la cle est-elle vraiment une chaine ?
        const kParam = methodParamClass(mHas.info, 0);
        if (!kParam) return null;
        let nomParam: string;
        try { nomParam = cstr(class_get_name(kParam) as NativePointer); } catch { return null; }
        if (nomParam !== "String") return null;
        const r = invokeMethod(mHas.info, d, [createManagedString(nom)]);
        if (r.isNull()) return null;
        // ⚠ `il2cpp_runtime_invoke` BOXE les types valeur : le `bool` est a +0x10, pas au
        // pointeur lui-meme. Le lire au mauvais endroit rendrait un vrai/faux plausible.
        return r.add(0x10).readU8() !== 0;
    } catch { return null; }
}

/** Le nombre de definitions du catalogue -- un FAIT, la ou `catalogueContient` peut se taire.
 *  `null` = pas lu. Publie systematiquement : un catalogue a 0 et un catalogue a 166 ne
 *  racontent pas la meme histoire quand rien n'apparait en bataille. */
function catalogueTaille(bc: NativePointer): number | null {
    try {
        const abilities = champPointeur(bc, "Abilities");
        if (estRefus(abilities)) return null;
        const dict = champPointeur(abilities as NativePointer, "EnvironmentAbilities");
        if (estRefus(dict)) return null;
        const d = dict as NativePointer;
        const off = getFieldOffset(d.readPointer(), "_count");
        return off < 0 ? null : d.add(off).readS32();
    } catch { return null; }
}

// ---------------------------------------------------------------------------------------
// LE CATALOGUE -- `BC.Abilities.EnvironmentAbilities`, ET POURQUOI ON N'Y ECRIT PAS SOI-MEME.
//
// ⚠ LA CLE N'EST PAS UNE CHAINE, ET LE JSON LE FAIT CROIRE. Une BC serialisee montre
// `{"EnvStartProtection": {...}}` -- on lit un nom, on conclut `Dictionary<String, ...>`. FAUX :
// mesure du 2026-08-23 sur une BC `SandboxGameModeSource` vivante, le parametre de `ContainsKey`
// est un `TriggeredAbilityConfigId`. Un `TriggeredAbilityConfigId` SE SERIALISE en nom sans etre
// STOCKE comme tel -- c'est exactement le piege que `catalogueContient` documente depuis le
// 2026-08-22, et il se referme une seconde fois des qu'on veut ECRIRE au lieu de lire.
//
// ⇒ Insertion a la main = boxage d'une cle de type valeur = le geste qui a tue le process le
//   2026-08-21 (`Tacticus.exe.30620.dmp`). ON NE L'ECRIT PAS.
//
// ⚠ LA SORTIE EST QUE LE NATIF A SA PROPRE METHODE, et elle est keyee par un ENUM PLAT :
//
//     IdunBattle.Configuration.AbilitiesConfiguration$$AddEnvironmentAbility(
//         id: IdunBattle.Entities.Enum.TriggeredAbilityType, configuration: AbilityConfiguration)
//     IdunBattle.Configuration.AbilitiesConfiguration$$GetEnvironmentAbility(
//         abilityType: IdunBattle.Entities.Enum.TriggeredAbilityType) -> AbilityConfiguration
//
// Un `int`. C'est le natif qui fabrique le `TriggeredAbilityConfigId`, donc plus rien a boxer.
// Le getter donne en prime une RELECTURE qui ne depend d'aucune convention de cle.
//
// ⚠ IL EXISTE DEUX SURCHARGES A DEUX PARAMETRES (l'autre prend un `TriggeredAbilityConfigId`), et
// `findMethodByParamCount` en choisirait une AU HASARD. On selectionne par le TYPE du premier
// parametre -- se tromper ici ne rend pas un mauvais resultat, ca crashe.
//
// ⚠ CE QUE CETTE VOIE NE SAIT PAS FAIRE : une VARIANTE. `EnhancementAddTrait:Stationary` est un
// `TriggeredAbilityType` PLUS un `VariantId`, et l'enum seul ne peut pas l'exprimer. Les 106
// variantes `EnhancementAddTrait:<Trait>` restent donc joignables par la voie SEED BC (ou
// Newtonsoft construit les cles) et PAS par ce patch. On le DIT au lieu de le laisser decouvrir.
interface EcritureCatalogue {
    ok: boolean;
    /** Le compte du dictionnaire AVANT / APRES -- un fait, pas un « configuré ». */
    tailleAvant?: number | null;
    tailleApres?: number | null;
    detail?: Array<Record<string, unknown>>;
    error?: string;
}

/** La surcharge dont le PREMIER PARAMÈTRE est du type demandé — jamais « la première trouvée ». */
function methodeParTypeDuPremierParam(
    klass: NativePointer, nom: string, nbParams: number, nomTypeAttendu: string,
): { info: NativePointer } | null {
    let k = klass;
    while (!k.isNull()) {
        const it = Memory.alloc(Process.pointerSize);
        it.writePointer(ptr(0));
        let m: NativePointer;
        while (!(m = class_get_methods(k, it) as NativePointer).isNull()) {
            try {
                if (cstr(method_get_name(m) as NativePointer) !== nom) continue;
                if ((method_get_param_count(m) as number) !== nbParams) continue;
                const kp = methodParamClass(m, 0);
                if (!kp) continue;
                if (cstr(class_get_name(kp) as NativePointer) === nomTypeAttendu) {
                    return { info: m };
                }
            } catch { /* méthode illisible : on passe, on ne devine pas */ }
        }
        break; // pas d'héritage à remonter : la méthode est déclarée sur la classe elle-même
    }
    return null;
}

/** ÉCRIRE des définitions dans le CATALOGUE de la BC — la moitié qui manquait au patch.
 *
 *  Sans elle, `environmentAbilities` pouvait installer une ability dont aucune config n'existe :
 *  le natif lève au premier `GetNumberConstant`, et le patch n'avait qu'un `avertissement` à
 *  offrir. Mesuré sur `EnvAttemptDebuff`, absent des 166 définitions du seed BC.
 *
 *  ⚠ ON ÉCRASE UNE ENTRÉE EXISTANTE SANS RIEN DEMANDER, ET C'EST VOULU : c'est le seul moyen de
 *  changer une constante déjà définie (`EnhancementDamageBoost.extraDmgPct` de `20` à `-100`).
 *  Le retour DIT, par entrée, si elle existait avant — pour qu'un écrasement soit lu, pas subi. */
export function ecrireCatalogueEnvironnement(
    bc: NativePointer,
    entrees: Array<{ abilityType: number; nom?: string; constants?: Record<string, string>;
                     variables?: Record<string, string[]> }>,
): EcritureCatalogue {
    if (!isDeserializerReady()) {
        return { ok: false, error: "`JsonConvert.DeserializeObject` non résolu -- une "
            + "`AbilityConfiguration` ne peut pas être construite" };
    }
    const abilities = champPointeur(bc, "Abilities");
    if (estRefus(abilities)) {
        return { ok: false, error: "`BC.Abilities` : " + (abilities as { error: string }).error };
    }
    const cfgAbilities = abilities as NativePointer;

    const kCfg = findClassAnywhere("IdunBattle.Configuration", "AbilityConfiguration");
    if (!kCfg) {
        return { ok: false, error: "classe `IdunBattle.Configuration.AbilityConfiguration` "
            + "introuvable -- chemin PÉRIMÉ sur ce build" };
    }
    const kAbilities = cfgAbilities.readPointer();
    const mAdd = methodeParTypeDuPremierParam(
        kAbilities, "AddEnvironmentAbility", 2, "TriggeredAbilityType");
    const mGet = methodeParTypeDuPremierParam(
        kAbilities, "GetEnvironmentAbility", 1, "TriggeredAbilityType");
    if (!mAdd) {
        return { ok: false, error: "`AbilitiesConfiguration$$AddEnvironmentAbility(TriggeredAbility"
            + "Type, AbilityConfiguration)` INTROUVABLE -- on ne se replie PAS sur la surcharge à "
            + "`TriggeredAbilityConfigId` : sa clé est un type valeur, et la boxer est le geste "
            + "qui a tué le process le 2026-08-21" };
    }

    // ⚠ `GetEnvironmentAbility` NE SAIT PAS DIRE « ABSENT », ET S'EN SERVIR REND UN VERT VACANT.
    // Mesure du 2026-08-23 : sur `EnvAttemptDebuff`, il rendait NON-NUL *avant* l'écriture alors
    // que le compte du dictionnaire passait de 166 à 167 -- l'entrée n'y était donc pas. Il
    // fabrique un défaut au lieu de rendre `null`. Une vérification bâtie dessus aurait rendu
    // `relu=true` quoi qu'il arrive, y compris si l'insertion avait échoué : c'est le capteur
    // qui confirme l'hypothèse l'ayant fait naître, encore lui.
    //
    // Le seul signal HONNÊTE est le COMPTE du dictionnaire, pris avant et après CHAQUE entrée :
    //   apres > avant  -> entrée NEUVE, réellement insérée
    //   apres == avant -> une entrée existait déjà et vient d'être ÉCRASÉE (le geste voulu quand
    //                     on change une constante) -- ou l'insertion n'a rien fait, et les deux
    //                     sont indistinguables par le compte seul. On le DIT.
    const getterNonNul = (t: number): boolean | null => {
        if (!mGet) return null;
        try {
            const buf = Memory.alloc(4); buf.writeS32(t | 0);
            return !invokeMethod(mGet.info, cfgAbilities, [buf]).isNull();
        } catch { return null; }
    };

    const tailleAvant = catalogueTaille(bc);
    const detail: Array<Record<string, unknown>> = [];
    for (const e of entrees) {
        const nom = e.nom ?? triggeredAbilityName(e.abilityType);
        const compteAvant = catalogueTaille(bc);
        // La forme que le jeu SÉRIALISE lui-même — on la lui rend telle quelle.
        const charge = {
            Variables: e.variables ?? {},
            Constants: e.constants ?? {},
            AttackRangeType: 0,
            VariablesAffectedByUnitRarityMultiplier: [] as number[],
            TutorialAbilityBehaviours: {},
        };
        let cfg: NativePointer;
        try { cfg = deserializeFromJson(JSON.stringify(charge), kCfg); }
        catch (err) {
            return { ok: false, tailleAvant, detail,
                error: "`" + nom + "` : désérialisation de l'`AbilityConfiguration` : "
                    + (err as Error).message };
        }
        if (cfg.isNull()) {
            return { ok: false, tailleAvant, detail,
                error: "`" + nom + "` : l'`AbilityConfiguration` s'est désérialisée en NUL" };
        }
        gcRoot.add(cfg);
        try {
            const buf = Memory.alloc(4); buf.writeS32(e.abilityType | 0);
            invokeMethod(mAdd.info, cfgAbilities, [buf, cfg]);
        } catch (err) {
            return { ok: false, tailleAvant, detail,
                error: "`" + nom + "` : `AddEnvironmentAbility` a LEVÉ : " + (err as Error).message };
        }
        const compteApres = catalogueTaille(bc);
        const neuve = (compteAvant !== null && compteApres !== null)
            ? compteApres > compteAvant : null;
        detail.push({
            abilityType: e.abilityType, nom,
            constants: e.constants ?? {},
            compteAvant, compteApres,
            /** `true` = entrée NEUVE (le compte a monté) · `false` = une entrée existait et a été
             *  ÉCRASÉE, OU rien n'a bougé — le compte seul ne les sépare pas · `null` = pas mesuré. */
            neuve,
            /** ⚠ NE PROUVE RIEN SUR L'ABSENCE : ce getter fabrique un défaut au lieu de rendre
             *  `null` (mesuré le 2026-08-23). Publié pour la lecture, jamais comme verdict. */
            getterNonNul: getterNonNul(e.abilityType),
            note: neuve === false
                ? "compte INCHANGÉ : soit la définition existante a été ÉCRASÉE (le geste voulu "
                  + "pour changer une constante), soit l'insertion n'a rien fait -- le compte ne "
                  + "sépare pas les deux"
                : undefined,
        });
    }
    return { ok: true, tailleAvant, tailleApres: catalogueTaille(bc), detail };
}

/** INSTALLER des abilities d'environnement sur la BC que la source vient de produire.
 *
 *  ⚠ MEME FENETRE QUE LE CALENDRIER DE VAGUES : on ecrit au `LoadBattle.onLeave`, sur l'objet
 *  en memoire, sans aucune serialisation ni substitution.
 *
 *  ⚠ LE RECEPTACLE NE SE CONSTRUIT PAS AU CTOR. `EnvironmentAbilities..ctor` laisse ses trois
 *  membres NULS ; `creerReceptacle` passe par Newtonsoft parce que ces membres sont des
 *  generiques INFLATES, introuvables par leur nom.
 *
 *  ⚠ `AbilitiesConfigurations` reste VIDE, et c'est le choix deja pris par `guild-war-config` :
 *  sa cle est un TYPE VALEUR, et se tromper de convention ne leve pas -- ca CRASHE le jeu
 *  (2026-08-21, `Tacticus.exe.30620.dmp`). L'hypothese est que le CATALOGUE de la BC suffit ;
 *  `catalogueContient` la rend verifiable au lieu de la laisser tacite. */
export function ecrireAbilitesEnvironnement(
    bc: NativePointer, demandes: Array<{ abilityType: number; niveau: number }>,
    enhancements: envAbilities.SpecEnhancement[] = [],
): EcritureEnvironnement {
    let klass: NativePointer;
    try { klass = bc.readPointer(); } catch (e) {
        return { ok: false, error: "classe de la BC illisible : " + (e as Error).message };
    }
    if (klass.isNull()) return { ok: false, error: "la BC porte une classe NULLE" };
    let nomClasse: string;
    try { nomClasse = cstr(class_get_name(klass) as NativePointer); }
    catch (e) { return { ok: false, error: "nom de classe illisible : " + (e as Error).message }; }
    if (nomClasse !== "BattleConfiguration") {
        return {
            ok: false,
            error: "l'objet est un `" + nomClasse + "`, pas une `BattleConfiguration` -- écrire "
                + "dedans corromprait un objet d'un autre type",
        };
    }
    let off = -1;
    for (const nom of ["EnvironmentAbilities", "<EnvironmentAbilities>k__BackingField"]) {
        off = getFieldOffset(klass, nom);
        if (off >= 0) break;
    }
    if (off < 0) {
        return {
            ok: false,
            error: "`BattleConfiguration.EnvironmentAbilities` ABSENT sous ses deux écritures "
                + "connues -- chemin PÉRIMÉ sur ce build",
        };
    }
    let avant: string;
    try { avant = bc.add(off).readPointer().toString(); }
    catch (e) { return { ok: false, error: "lecture du champ : " + (e as Error).message }; }

    // ⚠ ON FUSIONNE, ON NE REMPLACE PAS -- ET C'EST UNE EXIGENCE DU CHEMIN REEL.
    // `CampaignGameModeSource$$LoadBattle` appelle `ApplyEnvironmentAbilitiesFromProgression`
    // AVANT que ce hook ne rende la main (xrefs mesurees : la campagne, l'evenement de
    // campagne, l'amicale, le boss de guilde et la guerre de guilde passent TOUS par la).
    // Ecrire un receptacle neuf jetterait donc en silence les abilities que la progression du
    // joueur vient d'y poser. On REUTILISE celui qui est deja la quand il est utilisable, et on
    // DIT laquelle des deux voies a servi.
    let env: NativePointer;
    let voie: string;
    const existant = (() => {
        try {
            const p = bc.add(off).readPointer();
            if (p.isNull()) return null;
            // Type-garde : on n'ajoute pas dans un objet dont on ne sait pas ce qu'il est.
            const n = cstr(class_get_name(p.readPointer()) as NativePointer);
            // ⛔ CE GARDE N'ACCEPTAIT QU'UNE CLASSE, ET C'EST CE QUI A FAIT ECRIRE DANS LE VIDE.
            // Deux receptacles coexistent -- `EnvironmentAbilities` (celui qu'on fabrique) et
            // `EnvironmentAbilitiesConfiguration` (celui que la BC porte nativement, notamment
            // sur l'evenement Machines of War). Comparer a un NOM EN DUR faisait juger le second
            // « d'un autre type », donc REMPLACER le receptacle du mode par le notre : le moteur
            // ne lisait plus jamais ce qu'on y mettait, l'installation rendait `ok` / `relu=true`,
            // et il ne se creait AUCUNE entite (mesure A/B du 2026-08-24 : 44 effets / 145
            // entites, a l'identique, avec ou sans patch, des deux cotes).
            // On patche desormais CELUI QUI EST LA -- le foyer sait nommer les membres des deux.
            return envAbilities.estUnReceptacle(n) ? p : null;
        } catch { return null; }
    })();
    if (existant !== null) {
        env = existant;
        let classe = "?";
        try { classe = cstr(class_get_name(env.readPointer()) as NativePointer); } catch { /* noop */ }
        voie = `FUSION dans le réceptacle DÉJÀ POSÉ (\`${classe}\`)`;
    } else {
        const envR = envAbilities.creerReceptacle();
        if (estRefus(envR)) return { ok: false, error: (envR as { error: string }).error };
        env = envR as NativePointer;
        voie = "réceptacle NEUF (le champ était nul ou d'une classe INCONNUE de ce foyer)";
    }

    const tailleCatalogue = catalogueTaille(bc);
    const detail: Array<Record<string, unknown>> = [];
    for (const d of demandes) {
        const nom = triggeredAbilityName(d.abilityType);
        const auCatalogue = catalogueContient(bc, nom);
        const pose = envAbilities.ajouterAbility(env, d.abilityType, d.niveau);
        if (estRefus(pose)) {
            return { ok: false, error: "`" + nom + "` : " + (pose as { error: string }).error };
        }
        detail.push({
            abilityType: d.abilityType, nom, niveau: d.niveau,
            arme: pose === true,
            // `false` = le natif n'arme pas non plus a niveau 0 ; ce n'est pas un echec.
            raison: pose === false ? "niveau 0 -- le natif n'arme pas non plus" : undefined,
            auCatalogue,
            avertissement: auCatalogue === false
                ? "ABSENTE du catalogue `Abilities.EnvironmentAbilities` de cette BC ("
                  + tailleCatalogue + " définitions) -- si rien n'apparaît en bataille, c'est "
                  + "la première cause à regarder, et elle n'émettra AUCUNE trace"
                : (auCatalogue === null
                    ? "catalogue NON MESURÉ (clé non-`String` ou dictionnaire illisible) -- "
                      + "cette sonde se TAIT plutôt que de rendre un `absent` qu'elle ne peut "
                      + "pas établir"
                    : undefined),
        });
    }

    // Les ENHANCEMENTS -- la SECONDE liste du réceptacle, celle qui cible par unité NOMMÉE.
    const detailEnh: Array<Record<string, unknown>> = [];
    for (const e of enhancements) {
        const auCatalogue = catalogueContient(bc, e.ability);
        const pose = envAbilities.ajouterEnhancement(env, e);
        if (estRefus(pose)) {
            return { ok: false, error: "`" + e.ability + "` : " + (pose as { error: string }).error };
        }
        detailEnh.push({
            ability: e.ability, niveau: e.niveau ?? 1, playerId: e.playerId ?? null,
            cibles: e.cibles ?? [], stack: e.stack ?? 1,
            // CE QUI EST REELLEMENT ECRIT dans `Targets`, apres scission du suffixe par le mirror
            // de `UnitConfigId$$CreateFromString`. Sans cet écho, un `:6` mal apparié ne se verrait
            // NULLE PART : l'installation resterait `ok` et la liste compterait 1.
            ciblesResolues: (pose as { ciblesResolues?: unknown[] }).ciblesResolues,
            auCatalogue,
            note: (pose as { note?: string }).note,
            avertissement: auCatalogue === false
                ? "ABSENTE du catalogue de cette BC -- son premier `GetNumberConstant` LÈVERA "
                  + "(« system error »). Poser sa config par `environmentAbilityConfigs` AVANT."
                : undefined,
        });
    }

    // La ré-écriture du champ est INUTILE en fusion (l'objet est déjà en place) mais elle est
    // faite quand même : elle est idempotente, et elle donne le `relu` qui atteste.
    try { bc.add(off).writePointer(env); }
    catch (e) { return { ok: false, error: "écriture du champ : " + (e as Error).message }; }
    let apres: string;
    try { apres = bc.add(off).readPointer().toString(); } catch { apres = "?"; }
    return {
        ok: true, offset: "+0x" + off.toString(16), noeudAvant: avant, noeudApres: apres,
        relu: apres === env.toString(), voie, tailleCatalogue,
        // « CONFIGURE » N'EST PAS « INSTALLE » : seul le compte des membres tranche.
        installees: envAbilities.resume(env),
        detail,
        detailEnhancements: detailEnh.length > 0 ? detailEnh : undefined,
    };
}

/** `srcInstance` = l'instance de la SOURCE qui vient de produire cette BC, quand on l'a (hook
 *  `LoadBattle.onLeave`). C'est le SEUL endroit d'où la composition du joueur est lisible : la BC
 *  ne la porte pas en PvP -- cf. `game/source-lineup.ts`. `null` depuis les voies qui patchent une
 *  BC déjà montée (`applyBattleConfigPatch`, runner) : `ciblesAuto: "moi"` s'y rabat sur les camps
 *  dérivés de la BC, et le DIT. */
/** L'instance CAPTEE d'une source, quand personne ne l'a declaree -- le repli de la voie LIVE.
 *
 * ⛔ IL EXISTE PARCE QUE LA VOIE OU LES MIROIRS COUTENT EST JUSTEMENT CELLE QUI NE DECLARE RIEN.
 * `declarerSourceDeChargement` est appele par les FORGES ; la bataille que le joueur lance
 * lui-meme n'a personne pour le faire. Or c'est la, et seulement la, qu'un miroir non SIGNALE
 * coute une unite reelle -- on ne le retire plus, on le NOMME, et le nommer exige cette lecture.
 *
 * ⚠ CE QU'ON EN TIRE, ET CE QU'ON N'EN TIRE PAS. L'instance peut etre celle d'une bataille
 * PRECEDENTE : on ne lui demande donc RIEN qui depende de la bataille en cours. `GetBattleLineup`
 * lit la composition SAUVEGARDEE du mode -- la meme que le HUD va pre-poser -- donc une instance
 * plus ancienne rend la meme reponse. Ne pas etendre cet usage sans re-verifier ce point.
 *
 * ⚠ TOUT MODE ABSENT DE CETTE TABLE REND `null`, ET LE REFUS SE DIT (`MIROIRS NON VERIFIABLES`).
 * Rendre une source d'un AUTRE mode serait pire que rien : on annoncerait des miroirs tires d'une
 * composition qui n'est pas celle de cette bataille.
 *
 * ⛔ ET IL VALIDE LA CLASSE, DEPUIS LE 2026-08-26. Il rendait le pointeur capte TEL QUEL, sans le
 * confronter a la source qui charge -- alors que la voie DECLAREE, elle, avait ce cran depuis
 * toujours (`sourceConcordante`). Mesure : le pointeur `Pvp` portait un `SummonUnitModel` a
 * l'application, puis un `MachinesOfWarEventTokenWidgetVisuals` une heure plus tard -- objet
 * libere, ADRESSE RECYCLEE. `lineupDeLaSource` a refuse de lire (juste), donc 0 cible, donc buff
 * et Immune poses SUR PERSONNE, sans erreur. Un pointeur perime est desormais OUBLIE et NOMME.
 *
 * ⚠ ET LA TABLE DE QUATRE PREFIXES ETAIT LE SECOND TROU : l'ONSLAUGHT, l'incursion, l'endless --
 * toutes ancrees -- n'avaient AUCUN repli, donc `moi` y rendait 0 sans meme un pointeur a
 * accuser. Le registre generique (`game/source-instances.ts`) est keye par la classe REELLE lue
 * sur l'objet : il couvre toute source qu'un capteur traverse, sans liste a tenir. Les quatre
 * capteurs historiques restent consultes ENSUITE, valides par le meme controle. */
function repliSourceCaptee(source: string | null): { src: NativePointer | null; note: string | null } {
    if (source === null) return { src: null, note: null };
    // ⛔ LE TRANSPORT SE TRAITE AVANT LE REGISTRE, ET C'EST UNE REGRESSION MESUREE (2026-08-26).
    // `Sandbox` n'est PAS un mode : la BC qu'elle substitue vient de la derniere FORGE, et c'est
    // a celle-la qu'il faut demander la composition. Des que mes propres capteurs ont range une
    // instance de `SandboxGameModeSource` au registre, la consulter en premier rendait un
    // pointeur PARFAITEMENT VALIDE qui ne sait rien de la lineup -- `voie=lineup` (5 unites) est
    // retombe a `voie=aucune` (0 cible) d'un montage a l'autre, sans qu'aucune ligne du patch
    // n'ait bouge. Un repli juste ne se mesure pas a la validite du pointeur mais a ce qu'il
    // SAIT REPONDRE.
    if (source.startsWith("Sandbox")) {
        const t = derniereSourceForgee;
        return { src: t !== null && !t.isNull() ? t : null, note: null };
    }
    // 1. LE REGISTRE GENERIQUE : il connait toute source qu'un capteur a traversee.
    const r = instanceDeSource(source);
    if (r.src !== null) return r;
    // 2. Les capteurs HISTORIQUES ensuite -- meme controle de classe.
    const p = source.startsWith("Pvp") ? getPvpGameModeSourcePtr()
        : source.startsWith("Campaign") ? getCampaignGameModeSourcePtr()
        : source.startsWith("MachinesOfWarEvent") ? getMowEventGameModeSourcePtr()
        : null;
    const c = siConcordante(p, source);
    // La note du registre prime : c'est celle qui nomme le pointeur qu'on vient de jeter.
    return { src: c.src, note: r.note ?? c.note };
}

function applyPatchToConfig(
    bc: NativePointer, patch: BattleConfigPatch, srcInstance: NativePointer | null = null,
    // ⚠ LE NOM DE LA SOURCE N'EST PLUS DECORATIF : il choisit le repli de `repliSourceCaptee`.
    // `null` (voies qui patchent une BC deja montee) => aucun repli, donc aucune liste de
    // miroirs, et ca se DIT au lieu de passer pour « aucun miroir ».
    source: string | null = null,
): PatchApplyResult {
    const ops: string[] = [];
    const warnings: string[] = [];

    // Toggle randomize AI
    if (patch.randomizeAi !== undefined) {
        try {
            bc.add(BC_OFF_RANDOMIZE_AI).writeU8(patch.randomizeAi ? 1 : 0);
            ops.push(`randomizeAi=${patch.randomizeAi}`);
        } catch (e) {
            warnings.push(`randomizeAi: ${(e as Error).message}`);
        }
    }

    // Le calendrier de vagues -- MUTATION de la BC produite, jamais une substitution.
    if (patch.unitSpawningOverTime !== undefined && patch.unitSpawningOverTime !== null) {
        const w = ecrireCalendrierDeVagues(bc, patch.unitSpawningOverTime, {
            useAtomicGroup: patch.useAtomicGroup,
            useSpawnPointFromUnitIndex: patch.useSpawnPointFromUnitIndex,
        });
        if (w.ok) {
            const n = typeof patch.unitSpawningOverTime === "object"
                ? Object.keys(patch.unitSpawningOverTime as object).length : 0;
            ops.push(`unitSpawningOverTime=${n} tour(s) @${w.offset} `
                + `(${w.noeudAvant} -> ${w.noeudApres}, relu=${w.relu})`);
        } else {
            warnings.push(`unitSpawningOverTime: ${w.error}`);
        }
    }

    // ⛔ `viderPredefinedUnits` RETIRÉ (2026-08-23) -- ET CE N'ÉTAIT PAS UN OUTIL, C'ÉTAIT UNE
    // RUSTINE SUR UNE BC MAL FORMÉE.
    //
    // Il vidait `BC.PredefinedUnits` pour rendre utilisable la phase de déploiement d'un banc
    // sandbox. Le besoin venait entièrement de `SandboxWavesBattleConfig`, dont le ctor CONFOND
    // catalogue et pose : mesuré sur les 4 combinaisons de `startUnits`/`allUnits`, aucune ne rend
    // « catalogué mais pas posé » -- l'état qu'EST une phase de déploiement.
    //
    // Or la forme que le jeu produit vraiment est tout autre, et elle est mesurée sur 6 replays
    // RÉELS : `PredefinedUnits` porte l'ADVERSAIRE (que des `*Npc*`), et les unités du joueur
    // entrent par des `AddUnitMessage` (`player=11`) émis avant le `StartBattleMessage`, depuis
    // les placeholders du déploiement (`idun.IdunMainView$$AddUnitsFromPlaceholdersAndRunnerStartMatch`).
    // Sur une telle BC, vider `PredefinedUnits` EFFACERAIT L'ENNEMI.
    //
    // Laisser la SOURCE monter sa BC supprime le problème à la racine : plus de catalogue
    // incomplet, donc plus rien à rattraper. Le seul appelant (`sandbox_onslaught.py`) est retiré
    // avec lui.

    // ⚠ LE CATALOGUE D'ABORD, ET L'ORDRE N'EST PAS COSMÉTIQUE. Une ability installée sans sa
    // définition fait LEVER son premier `GetNumberConstant` ; poser la config APRÈS l'installation
    // laisserait donc une fenêtre où la BC est armée et incohérente. On dote, PUIS on installe.
    if (patch.environmentAbilityConfigs !== undefined && patch.environmentAbilityConfigs !== null
        && patch.environmentAbilityConfigs.length > 0) {
        const w = ecrireCatalogueEnvironnement(bc, patch.environmentAbilityConfigs);
        if (w.ok) {
            const lu = (w.detail ?? []).map((d) =>
                `${d.nom}:${d.neuve === true ? "NEUVE" : (d.neuve === false ? "écrase-ou-inerte"
                    : "non mesurée")}`);
            ops.push(`environmentAbilityConfigs ${lu.join(" ")} `
                + `(catalogue ${w.tailleAvant} -> ${w.tailleApres})`);
            for (const d of w.detail ?? []) {
                // On n'alerte QUE sur ce qu'on ne sait pas mesurer. Un compte inchangé est le
                // régime NORMAL d'un écrasement de constante -- en faire un warning banaliserait
                // le canal, et c'est le canal qui porte les vraies causes muettes.
                if (d.neuve === null) {
                    warnings.push(`environmentAbilityConfigs[${d.nom}]: compte du catalogue NON `
                        + `MESURÉ -- l'insertion n'est ni confirmée ni infirmée`);
                }
            }
        } else {
            warnings.push(`environmentAbilityConfigs: ${w.error}`);
        }
    }

    // Les abilities d'environnement -- MUTATION du même objet, à la même fenêtre.
    // Les DEUX listes du réceptacle passent par le MÊME appel : il n'y a qu'une acquisition du
    // réceptacle (fusion ou neuf), donc pas deux chances d'en créer un second et de jeter le
    // premier.
    const demandesEnv = patch.environmentAbilities ?? [];
    // ⚠ LES CIBLES `ciblesAuto` SE RESOLVENT ICI, PAS A L'ARMEMENT -- c'est tout l'interet : la BC
    // n'existe qu'a cette fenetre, donc c'est le seul moment ou l'adversaire est ENUMERABLE. Un
    // patch arme une fois mord alors sur n'importe quelle source (PvP, onslaught, ...) sans qu'on
    // ait a renommer ses cibles a chaque proposition.
    const specsEnh = patch.environmentEnhancements ?? [];
    // Les camps sont derives UNE fois (la serialisation coute, et deux entrees `ciblesAuto` la
    // paieraient deux fois) -- et seulement si quelqu'un les demande.
    const camps = specsEnh.some((e) => e.ciblesAuto !== undefined) ? campsDeLaBc(bc) : null;
    if (camps !== null) {
        ops.push(`camps derives : ${camps.miens.length} unite(s) a MOI, `
            + `${camps.adverses.length} ADVERSE(S) (PredefinedUnits + machines + vagues, `
            + `classees par TeamId)`);
    }
    // La composition du joueur ne se lit PAS dans la BC (vide en PvP) : on la DEMANDE a la source.
    // On ne paie l'invocation que si quelqu'un vise `moi`, et seulement quand la source est la --
    // c'est-a-dire au `LoadBattle.onLeave`, ou l'on est deja sur le thread principal.
    const veutMoi = specsEnh.some((e) => e.ciblesAuto === "moi");
    // ⛔ `adversaire` A BESOIN DE MA COMPOSITION LUI AUSSI -- POUR L'EXCLURE, ET C'EST MESURE.
    // `UnitConfigId$$Equals` ignore `IsPvpOpponent` : une cible ecrite pour la copie d'en face
    // apparie AUSSI la mienne. Mesure du 2026-08-24, sandbox PvP montee avec deux miroirs
    // (`custoTrajann`, `ultraTigurius` des deux cotes) : `effectsAll` rend
    // `EnhancementDamageBoost` sur `[80,82,84,86,88, 91,93]` -- 91 et 93 sont MES deux unites,
    // a -100 % de degats. Les trois non partagees sont propres. La branche `moi` faisait deja
    // cette soustraction, dans l'autre sens ; il manquait la symetrique.
    const veutAdversaire = specsEnh.some((e) => e.ciblesAuto === "adversaire");
    // ⚠ ET LA VOIE LIVE NE DECLARE PERSONNE. `srcInstance` n'est renseignee que par une FORGE.
    // Sur la bataille que le joueur lance lui-meme -- exactement celle qu'il faut proteger --
    // elle est nulle, et `camps.miens` est VIDE en PvP (les unites entrent au deploiement).
    // On se rabat donc sur l'instance CAPTEE de la meme classe : `GetBattleLineup` y lit la
    // composition SAUVEGARDEE du mode, qui est justement celle que le HUD va pre-poser.
    const repli = srcInstance === null
        ? repliSourceCaptee(source) : { src: null, note: null };
    if (repli.note !== null) warnings.push(repli.note);
    const instancePourLineup = srcInstance ?? repli.src;
    const lineupSource = ((veutMoi || veutAdversaire) && instancePourLineup !== null)
        ? lineupDeLaSource(instancePourLineup) : null;
    // ⛔ LE REGISTRE PRIME SUR LA SOURCE, ET C'EST TOUT L'INTERET DU MONTAGE.
    // Si une composition a ete RETENUE pour ce mode, c'est ELLE que `GetBattleLineup` posera au
    // deploiement. Buffer ce que la source a sauvegarde alors que le deploiement recevra autre
    // chose ferait poser les buffs sur des unites qui ne descendent JAMAIS -- aucune erreur levee,
    // des buffs bien installes, et un resultat qui se lit « les buffs ne marchent pas ».
    // On REMPLACE donc `unites`, et on le DIT : un remplacement tu se lirait comme une mesure.
    const retenue = lineupSource === null ? null : compositionRetenue(lineupSource.classe);
    if (lineupSource !== null && retenue !== null) {
        ops.push(`lineup RETENUE au registre (${retenue.origine}) : ${retenue.ids.length} unite(s)`
            + ` -- REMPLACE la composition sauvegardee de \`${lineupSource.classe}\``
            + ` (${lineupSource.unites === null ? "NON MESUREE" : lineupSource.unites.length}),`
            + ` parce que c'est elle que \`GetBattleLineup\` posera au deploiement`);
        lineupSource.unites = retenue.ids.slice();
    }
    if (lineupSource !== null) {
        ops.push(`lineup demandee a \`${lineupSource.classe}\` : `
            + `${lineupSource.unites === null ? "NON MESUREE" : lineupSource.unites.length} unite(s)`
            + `, places=${lineupSource.places}, mow=${lineupSource.mow ?? "aucune"}`
            + (lineupSource.refus !== null ? ` -- ${lineupSource.refus}` : ""));
    }
    const demandesEnh = specsEnh.map((e) => {
        if (e.ciblesAuto === undefined) return e;
        if (camps === null) {
            // ⚠ SANS CAMPS, ON NE POSE RIEN. Une entree sans cible est INERTE et se voit ; une
            // entree aux cibles INVERSEES arme le `-100 %` sur sa propre equipe -- mesure du
            // 2026-08-23 sur une BC a vagues, 9 cibles dont mes 5 unites.
            warnings.push(`environmentEnhancements[${e.ability}]: \`ciblesAuto\` demande mais les `
                + `CAMPS ne sont pas derivables (\`Player.Players\` illisible, ou pas exactement `
                + `un joueur \`PlayerType 0\`) -- entree posee SANS cible plutot qu'a l'envers`);
            return { ...e, cibles: [] };
        }
        if (e.ciblesAuto === "adversaire") {
            // ⛔ ET SES SUMMONS. Un adversaire qui invoque en cours de bataille amène des unités
            // qu'AUCUNE lecture de la BC ne nomme -- elles n'existent pas encore. Sans elles, un
            // `-100 %` laisse intacte la moitié d'une équipe tyranide, en silence.
            const smn = camps.summonsDe(camps.adverses);
            if (smn.length > 0) {
                ops.push(`environmentEnhancements[${e.ability}]: +${smn.length} SUMMON(S) que `
                    + `l'adversaire peut invoquer (derives de ses abilities)`);
            }
            const base = Array.from(new Set([...camps.adverses, ...smn]));
            // ⛔ ON NE RETIRE RIEN. AUCUN MIROIR N'EST SOUSTRAIT, ET C'EST UN CHOIX EXPLICITE.
            //
            // Le canal ne sait pas discriminer : `IdunBattle.Configuration.UnitConfigId$$Equals`
            // compare EXACTEMENT quatre choses, lues au decompile le 2026-08-24 (plus sur une
            // phrase d'aide) : `PureId` (+0x00, `String.op_Equality`), `Rarity` (+0x08,
            // `Nullable` -- `HasValue` ET `Value`), `Level` (+0x10, idem), `IsBorrowed` (+0x18,
            // octet). `IsPvpOpponent` n'est JAMAIS lu. En PvP les entrees adverses portent
            // `Rarity: null, Level: null, IsBorrowed: false` -- et les miennes aussi, sinon la
            // correspondance MESUREE n'aurait pas eu lieu. Les quatre champs coincident : viser
            // la copie d'en face SEULE est impossible par ce canal, et il ne sert a rien de
            // chercher.
            //
            // ⇒ Il ne restait que deux regimes, et l'arbitrage est celui de l'utilisateur
            // (2026-08-24, transpose de la GUERRE DE GUILDE ou il tient depuis toujours) :
            //   * retirer l'id  => MA copie est epargnee, mais LA SIENNE aussi -- l'adversaire
            //                      garde une unite pleine ;
            //   * garder l'id   => les deux copies portent le debuff.
            // << Je prefere qu'une de mes unites soit debuff plutot qu'une unite adverse ne le
            // soit pas. >> Le debuff est donc COMPLET, toujours, et c'est a l'utilisateur de ne
            // pas descendre une unite que l'adversaire aligne aussi.
            //
            // ⚠ CE N'EST PAS UNIVERSEL : sur le boss de guilde les cibles portent `Level: 23`.
            // La ou le niveau est porte ET differe entre les deux copies, `Equals` discrimine
            // tout seul et la question ne se pose meme pas. Le probleme est propre aux modes qui
            // NEUTRALISENT le niveau, dont le PvP.
            //
            // ⚠ MAIS ON NE SE TAIT PAS. La lecture de ma composition est CONSERVEE -- non plus
            // pour soustraire, mais pour NOMMER les ids qui vont retomber sur moi. C'est la
            // seule chose qui permette a l'utilisateur d'exercer l'arbitrage qu'il vient de
            // prendre : sans la liste, << c'est a moi de m'en assurer >> n'est pas jouable.
            // On compare sur le `PureId` -- le suffixe `:pvp` porte le mode, pas l'identite.
            const miennes = new Set<string>([
                ...camps.miens.map(pureId),
                ...(lineupSource?.unites ?? []).map(pureId),
                ...(lineupSource?.mow != null ? [pureId(lineupSource.mow)] : []),
            ]);
            const miroirs = base.filter((c) => miennes.has(pureId(c)));
            if (miroirs.length > 0) {
                // AVERTISSEMENT, pas `ops` : c'est une unite reelle qui va jouer diminuee.
                warnings.push(`environmentEnhancements[${e.ability}]: ${miroirs.length} MIROIR(S) `
                    + `-- ${miroirs.map(pureId).join(", ")} -- present(s) DANS LES DEUX camps. `
                    + `Ils sont VISES QUAND MEME (choix assume : mieux vaut ma copie debuffee `
                    + `qu'une unite adverse epargnee). NE PAS LES DESCENDRE si tu peux l'eviter.`);
            }
            // ⚠ NE PAS SE TAIRE QUAND ON N'A PAS PU REGARDER. Sans ma composition, l'absence de
            // miroir signale n'est PAS une absence de miroir : le dire est ce qui distingue
            // « aucun » de « je n'ai pas su verifier ». Un silence identique dans les deux cas
            // ferait descendre une equipe en croyant la liste vide.
            if (miennes.size === 0) {
                warnings.push(`environmentEnhancements[${e.ability}]: MIROIRS NON VERIFIABLES `
                    + `-- ma composition n'est pas mesurable ici (source declaree : `
                    + `${srcInstance !== null ? "oui" : "NON"}, repli capte : `
                    + `${instancePourLineup !== null ? "oui" : "NON"}, camps.miens=`
                    + `${camps.miens.length}). Le debuff part COMPLET ; personne ne peut te dire `
                    + `lesquelles de tes unites le porteront aussi.`);
            } else {
                // ⚠ ET LA PORTEE DE LA LISTE SE DIT, MEME QUAND ELLE EST VIDE. `GetBattleLineup`
                // rend la composition SAUVEGARDEE -- celle que le HUD va pre-poser -- pas celle
                // qui sera REELLEMENT descendue. Changer d'equipe au deploiement (ou la forcer
                // par `--mes-unites` sur un banc) sort de ce que la liste a pu regarder, et
                // aucune lecture de cette fenetre ne peut le savoir : les unites n'entrent
                // qu'au deploiement, apres. Mesure du 2026-08-24 : 6 ids lus, 0 miroir annonce,
                // et deux miroirs FORCES bel et bien debuffes -- la lecture etait juste, son
                // ensemble ne les contenait pas.
                ops.push(`environmentEnhancements[${e.ability}]: miroirs cherches contre `
                    + `${miennes.size} id(s) a moi (voie=${lineupSource?.voie ?? "BC"}) -- `
                    + `${miroirs.length} trouve(s) ; liste tiree de la composition ANNONCEE, `
                    + `pas d'une equipe changee au deploiement`);
            }
            // Le debuff part sur TOUT le camp adverse, miroirs compris.
            return { ...e, cibles: base };
        }
        // `moi` : ON DEMANDE LA COMPOSITION A LA SOURCE, puis on RETRANCHE tout ce qui est adverse.
        //
        // ⛔ NE PAS SE CONTENTER DE `camps.miens`. Mesure du 2026-08-23 sur une BC PvP REELLE
        // (forgee, sans consommer de tentative) : `camps.miens` y est VIDE -- les unites du joueur
        // n'entrent qu'au DEPLOIEMENT, par `AddUnitMessage`, donc APRES cette fenetre. La BC ne
        // porte pas la reponse ; la SOURCE, elle, la connait, et c'est elle qui la donnera au HUD.
        // Foyer unique de cette demande : `game/source-lineup.ts`.
        //
        // ⛔ LA REGLE EST ASYMETRIQUE, ET C'EST UN CHOIX EXPLICITE (utilisateur, 2026-08-24) :
        //   * le DEBUFF part sur le camp adverse COMPLET -- tant pis si mes unites miroir le
        //     prennent aussi (mieux vaut ma copie diminuee qu'une unite adverse epargnee) ;
        //   * le BUFF, lui, ne touche JAMAIS une unite du camp adverse. Tout id present en face
        //     est RETIRE de mes cibles.
        // Les deux branches ne se ressemblent donc pas, et il ne faut pas les << harmoniser >>.
        //
        // ⚠ POURQUOI RETRANCHER PLUTOT QUE S'EN REMETTRE AU `-100 %`. Un buff qui fuit sur la copie
        // d'en face serait ANNULE si celle-ci portait deja le facteur zero du debuff -- mesure :
        // `GetMultiplierFromDamageBonus(-100)` rend `0`, et les contributions d'une meme face se
        // composent PAR PRODUIT. Mais cette annulation ne vaut QUE pour un buff sur l'axe DEGAT,
        // ET si le debuff a reellement couvert cet id, ET s'il a ete LU par le runner -- trois
        // conditions que ce hook ne peut verifier a cette fenetre. `EnhancementRegeneration`
        // (+PV max), un `EnhancementAddTrait:*` ou un `EnhancementSummon*` ne sont dans AUCUN
        // accumulateur de degat : ils arriveraient intacts chez l'adversaire. Retrancher est
        // inconditionnel ; se reposer sur l'absorption ne l'est pas.
        //
        // ⚠ CE QUE CA COUTE, ET C'EST ACCEPTE : mon unite miroir ne recoit pas le buff. On ne peut
        // pas faire mieux -- `IdunBattle.Configuration.UnitConfigId$$Equals` compare `PureId`,
        // `Rarity`, `Level` et `IsBorrowed`, jamais `IsPvpOpponent`, et en PvP les quatre
        // coincident entre les deux copies. Viser la mienne seule est impossible par ce canal.
        //
        // ⚠ DEUX GRANULARITES, ET C'EST VOULU : on CIBLE avec l'id ENTIER (le suffixe porte le
        // `Level`, sans quoi rien n'apparie), mais on COMPARE sur le `PureId` -- un homonyme d'en
        // face s'ecrit `worldKharn:pvp` et designe pourtant le meme `worldKharn`.
        const exclus = new Set(camps.adverses.map(pureId));
        // La MACHINE DE GUERRE est une unite a moi comme une autre, et elle n'apparait dans AUCUNE
        // des deux autres voies : `GetBattleLineup` ne rend que les heros, et la BC ne porte que
        // les `PredefinedMachines` de l'adversaire.
        // ⛔ ET SI LA COMPOSITION SAUVEGARDEE EST VIDE, ON BUFFE LE POOL. Sur un mode a run
        // (l'evenement Machines of War / Incursion), `GetBattleLineup` lit l'etat de RUN : tant
        // qu'aucun run n'est demarre elle rend `[]`, et `moi` n'a RIEN a nommer. La source connait
        // pourtant les 24 unites que le HUD proposera (`GetUnlockedUnits`). Viser le POOL couvre
        // donc n'importe quelle equipe que le joueur descendra ensuite.
        // ⚠ C'EST LE POOL, PAS L'EQUIPE, et `source-lineup` le DIT par `voie`. Sans risque pour un
        // buff -- viser une unite qui ne descend jamais ne coute rien -- mais faux pour compter.
        const depuisSource = lineupSource === null ? [] : [
            ...(lineupSource.unites ?? []),
            ...(lineupSource.unites !== null && lineupSource.unites.length === 0
                ? (lineupSource.deployables ?? []) : []),
            ...(lineupSource.mow !== null ? [lineupSource.mow] : []),
        ];
        // ⛔ ET MES SUMMONS. Symetrique du camp adverse : mes invocations naissent EN COURS de
        // bataille, donc elles ne sont ni dans la BC ni dans le pool deployable. Un buff qui les
        // oublie laisse une part de l'equipe non buffee, sans rien signaler.
        const mesUnites = Array.from(new Set([
            ...(e.cibles ?? []), ...depuisSource, ...camps.miens,
        ]));
        const mesSummons = camps.summonsDe(mesUnites);
        if (mesSummons.length > 0) {
            ops.push(`environmentEnhancements[${e.ability}]: +${mesSummons.length} SUMMON(S) que `
                + `mes unites peuvent invoquer (derives de leurs abilities)`);
        }
        const base = Array.from(new Set([...mesUnites, ...mesSummons]));
        // ⛔ AUCUNE UNITE DU CAMP ADVERSE NE RECOIT LE BUFF. Retrait inconditionnel.
        const gardees = base.filter((c) => !exclus.has(pureId(c)));
        const retires = base.filter((c) => exclus.has(pureId(c)));
        if (retires.length > 0) {
            // ⚠ LE REGIME DU POOL N'EST PAS CELUI DE LA LINEUP, ET LE COMPTE SEUL LES CONFOND.
            // Quand la composition sauvegardee est VIDE, `depuisSource` se rabat sur les
            // DEPLOYABLES -- une centaine d'ids, qui contiennent presque surement TOUT le camp
            // d'en face. Le retrait y porte alors sur l'equipe adverse ENTIERE, ce qui est JUSTE
            // mais n'a rien a voir en volume avec << deux miroirs >>. On le DIT separement : un
            // retrait massif signale surtout qu'on buffe un POOL, pas une equipe.
            const surLePool = lineupSource !== null && lineupSource.unites !== null
                && lineupSource.unites.length === 0;
            const noms = retires.map(pureId);
            const extrait = noms.slice(0, 12).join(", ")
                + (noms.length > 12 ? `, +${noms.length - 12} autre(s)` : "");
            ops.push(`environmentEnhancements[${e.ability}]: ${retires.length} cible(s) RETIREE(S) `
                + `du BUFF -- ${extrait} -- presente(s) dans le camp ADVERSE. `
                // ⚠ ASCII SEULEMENT dans ce qui est IMPRIME : la console Windows est en cp1252,
                // un `⚠` dans la chaine y leve `UnicodeEncodeError` cote Python. Les COMMENTAIRES
                // (comme celui-ci) ne partent nulle part et peuvent en porter.
                + `\`Equals\` ne lit pas \`IsPvpOpponent\` : les buffer buffait la copie d'en face.`
                + (surLePool
                    ? ` ATTENTION -- liste tiree du POOL DEPLOYABLE (composition sauvegardee `
                        + `vide), pas d'une equipe : ce retrait porte sur tout le camp adverse, `
                        + `pas sur quelques miroirs.`
                    : ""));
            // ⚠ AVERTISSEMENT SEPARE quand le retrait touche une unite que je vais REELLEMENT
            // descendre : ce n'est plus un id theorique du pool, c'est un heros de ma lineup qui
            // jouera SANS le buff. Le compte ci-dessus ne le distingue pas.
            if (!surLePool) {
                warnings.push(`environmentEnhancements[${e.ability}]: ${retires.length} unite(s) `
                    + `de MA composition ne recevront PAS le buff (${extrait}) -- l'adversaire `
                    + `aligne le meme id, et le buffer le buffait lui aussi. Cout ASSUME.`);
            }
        }
        ops.push(`environmentEnhancements[${e.ability}]: ${gardees.length} cible(s) = `
            + `${depuisSource.length} de la SOURCE (voie=${lineupSource?.voie ?? "aucune"}) `
            + `U ${camps.miens.length} de la BC `
            + `U ${(e.cibles ?? []).length} fournie(s) - ${retires.length} adverse(s)`);
        if (gardees.length === 0) {
            warnings.push(`environmentEnhancements[${e.ability}]: AUCUNE cible -- `
                + (lineupSource === null
                    ? `la SOURCE n'a pas ete transmise (patch applique hors \`LoadBattle\`), et la `
                        + `BC ne porte pas la composition du joueur`
                    : `la source \`${lineupSource.classe}\` a repondu : `
                        + `${lineupSource.refus ?? "aucune unite"}`));
        }
        // Le buff ne part QUE sur ce qui n'appartient pas au camp adverse.
        return { ...e, cibles: gardees };
    });
    if (demandesEnv.length > 0 || demandesEnh.length > 0) {
        const w = ecrireAbilitesEnvironnement(bc, demandesEnv, demandesEnh);
        if (w.ok) {
            const inst = JSON.stringify(w.installees);
            // ⚠ `voie` EST PUBLIEE, et elle ne l'etait PAS. Elle dit si on a FUSIONNE dans le
            // receptacle du mode ou POSE le notre par-dessus -- exactement la distinction qui
            // separe « le moteur lira » de « le moteur ne lira jamais ». Elle etait calculee,
            // rendue par `ecrireAbilitesEnvironnement`, et jetee ici : le diagnostic du
            // 2026-08-24 a coute plusieurs heures faute de cette seule ligne.
            ops.push(`environmentAbilities=${demandesEnv.length} + enhancements=`
                + `${demandesEnh.length} demandée(s) `
                + `@${w.offset} (${w.noeudAvant} -> ${w.noeudApres}, relu=${w.relu}) `
                + `voie=${w.voie} installées=${inst}`);
            // L'absence au catalogue ne fait PAS échouer l'écriture -- elle est ANNONCÉE, parce
            // que c'est une cause qui, sinon, n'émet aucune trace.
            for (const d of w.detail ?? []) {
                if (d.avertissement) warnings.push(`environmentAbilities[${d.nom}]: ${d.avertissement}`);
            }
            for (const d of w.detailEnhancements ?? []) {
                if (d.avertissement) {
                    warnings.push(`environmentEnhancements[${d.ability}]: ${d.avertissement}`);
                }
                if (d.note) warnings.push(`environmentEnhancements[${d.ability}]: ${d.note}`);
                // ⛔ LES CIBLES RESOLUES ETAIENT CALCULEES PUIS JETEES, et c'est ce qui a rendu
                // un diagnostic impossible le 2026-08-24. `ajouterEnhancement` publie déjà
                // `ciblesResolues` -- les `UnitConfigId` EXACTS écrits dans `Targets`, après
                // scission du suffixe par `UnitConfigId$$CreateFromString` -- mais ce site n'en
                // lisait que `avertissement`/`note`, et `getBattleConfigPatchStatus` ne publie
                // que `operations`/`warnings`. Résultat : la seule question qui décide si un
                // enhancement peut apparier (« QUELLE FORME d'id a-t-on écrite ? ») n'était
                // lisible NULLE PART, alors que la réponse était en mémoire.
                //
                // `IdunBattle.Entities.Selectors.EnhancementTargetSelector$$Select` compare par
                // `IdunBattle.Configuration.UnitConfigId$$op_Equality`, donc sur PureId ET
                // Rarity ET Level. Un id nu (`worldKharn`) et un id suffixé (`worldKharn:50`)
                // sont DEUX cibles différentes, et rien ne le signale : l'installation reste
                // `ok`, la liste compte juste, et l'effet ne se pose pas.
                //
                // ⚠ AUCUN PLAFOND ICI, C'EST DELIBERE. Tronquer la liste ferait exactement ce
                // que ce commit repare : cacher la cible qu'on n'a pas regardée. On imprime tout,
                // et le compte avec.
                const cr = (d as { ciblesResolues?: unknown[] }).ciblesResolues;
                if (Array.isArray(cr)) {
                    ops.push(`environmentEnhancements[${d.ability}]: ${cr.length} `
                        + `Target(s) ECRITE(S) = ${JSON.stringify(cr)}`);
                }
            }
        } else {
            warnings.push(`environmentAbilities: ${w.error}`);
        }
    }

    // SpawnPointSetIndex
    if (patch.spawnPointSetIndex !== undefined) {
        try {
            bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).writeS32(
                patch.spawnPointSetIndex);
            ops.push(`spawnPointSetIndex=${patch.spawnPointSetIndex}`);
        } catch (e) {
            warnings.push(
                `spawnPointSetIndex: ${(e as Error).message}`);
        }
    }

    // ⛔ L'INDEX `templatesById`, LE SWAP `aiUnits` ET LES `templateOverrides` SONT RETIRÉS
    // (2026-08-23) — cf. le pavé sur `BattleConfigPatch`. Trois raisons, dans cet ordre :
    // aucun appelant ; `aiUnitsAt` no-opait en silence ; et la justification du swap
    // (« `BC.Units` = roster du joueur ») est DÉMENTIE par 6 replays réels, où les deux camps y
    // figurent (19/19 ennemis, 23/23 unités du joueur, ~175 gabarits).

    return {
        ok: warnings.length === 0,
        appliedAt: new Date().toISOString(),
        bcPtr: bc.toString(),
        operations: ops,
        warnings,
    };
}

// --- Spawn helper: materialize PredefinedUnits into runner via AddUnitMessage ---
//
// buildRunner gives us a SKELETON (tiles + match + players) but no Unit
// entities. We need to apply AddUnitMessage(unitId, playerId, col, row) for
// each PredefinedUnit, using the SpawnPointGroup matching the player's team.
//
// Layout reminders:
//   BattleConfiguration.Board.SpawnPointSets : List<SpawnPointSetConfiguration>
//   SpawnPointSetConfiguration.SpawnPointGroups : List<SpawnPointGroupConfiguration>
//   SpawnPointGroupConfiguration:
//     +0x10  TeamWithPlayerIndex (int)
//     +0x14  MachineOfWarPosition
//     +0x18  SpawnPoints : List<SpawnPointConfiguration>
//   SpawnPointConfiguration : BattleConfigPosition
//     +0x10  Column
//     +0x14  Row
//   AddUnitMessage (4-arg ctor): (string unitId, PlayerId, int col, int row)
//     +0x28  SpawnSource (set to Deployment=5 per launch.ts)

const BCBC_OFF_SPAWN_POINT_SETS = 0x28; // BattleConfigBoardConfiguration
const SPS_OFF_SPAWN_GROUPS = 0x10;      // SpawnPointSetConfiguration
const SPG_OFF_TEAM_PLAYER_INDEX = 0x10; // SpawnPointGroupConfiguration
const SPG_OFF_SPAWN_POINTS = 0x18;
const SP_OFF_COL = 0x10;
const SP_OFF_ROW = 0x14;

const addUnitMsgClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Messages", "AddUnitMessage");
const addUnitMsgCtor4 = addUnitMsgClass
    ? findCtorByParamCount(addUnitMsgClass, 4) : null;

function buildAddUnitMessage(
    unitId: string, playerId: number, col: number, row: number,
): NativePointer {
    if (!addUnitMsgClass) throw new Error("AddUnitMessage class not found");
    if (!addUnitMsgCtor4) throw new Error("AddUnitMessage 4-arg ctor not found");
    const msg = il2cpp_object_new(addUnitMsgClass) as NativePointer;
    if (msg.isNull()) throw new Error("il2cpp_object_new(AddUnitMessage) returned null");
    gcRoot.add(msg);
    const unitIdStr = createManagedString(unitId);
    const pidBuf = Memory.alloc(4); pidBuf.writeS32(playerId);
    const colBuf = Memory.alloc(4); colBuf.writeS32(col);
    const rowBuf = Memory.alloc(4); rowBuf.writeS32(row);
    invokeMethod(addUnitMsgCtor4.info, msg, [unitIdStr, pidBuf, colBuf, rowBuf]);
    // SpawnSource = Deployment (5) — matches what the live game writes
    // for pre-battle player placements.
    msg.add(0x28).writeS32(5);
    return msg;
}

/** Read all SpawnPointGroups in the BC's active SpawnPointSet, each with
 * its team-player-index and spawn point coordinates. */
function readAllSpawnGroups(bc: NativePointer): Array<{
    teamWithPlayerIndex: number;
    points: Array<{ col: number; row: number }>;
}> {
    const board = bc.add(BC_OFF_BOARD).readPointer();
    if (board.isNull()) return [];
    const setIdx = bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).readS32();
    const sets = readManagedList(
        board.add(BCBC_OFF_SPAWN_POINT_SETS).readPointer());
    if (!sets || setIdx < 0 || setIdx >= sets.size) return [];
    const set = readListItem(sets, setIdx);
    const groups = readManagedList(set.add(SPS_OFF_SPAWN_GROUPS).readPointer());
    if (!groups) return [];
    const out = [];
    for (let g = 0; g < groups.size; g++) {
        const grp = readListItem(groups, g);
        if (grp.isNull()) continue;
        const tpi = grp.add(SPG_OFF_TEAM_PLAYER_INDEX).readS32();
        const spawnPts = readManagedList(
            grp.add(SPG_OFF_SPAWN_POINTS).readPointer());
        const points: Array<{ col: number; row: number }> = [];
        if (spawnPts) {
            for (let i = 0; i < spawnPts.size; i++) {
                const sp = readListItem(spawnPts, i);
                if (sp.isNull()) continue;
                points.push({
                    col: sp.add(SP_OFF_COL).readS32(),
                    row: sp.add(SP_OFF_ROW).readS32(),
                });
            }
        }
        out.push({ teamWithPlayerIndex: tpi, points });
    }
    return out;
}

/** Auto-spawn every unit listed in BC.PredefinedUnits into the given runner.
 * Maps PredefinedUnits[i] to SpawnPointGroup[i].SpawnPoints[j] positionally
 * — relies on the convention that PredefinedUnits and SpawnPointGroups are
 * declared in the same order (typically [human, ai]). Returns per-player
 * spawn count + any errors. */
function spawnPredefinedUnitsInto(
    runner: NativePointer, bc: NativePointer,
): {
    ok: boolean;
    spawned: Array<{
        playerId: number; pickedGroupIndex: number;
        teamWithPlayerIndex: number; count: number; errors: string[];
    }>;
} {
    if (!runnerApplyMi) throw new Error("runner.Apply not resolved");
    const pu = readManagedList(bc.add(BC_OFF_PREDEFINED_UNITS).readPointer());
    if (!pu) return { ok: false, spawned: [] };

    const allGroups = readAllSpawnGroups(bc);
    // Heuristic to find which SpawnPointGroup serves a given PredefinedUnits
    // group: pick the spawn group with enough points AND the largest count,
    // preferring exact size match if it exists. Skip groups already consumed
    // by a previous PredefinedUnits group in the same call.
    const consumed = new Set<number>();
    const pickGroup = (needed: number) => {
        let bestIdx = -1;
        let bestScore = -Infinity;
        for (let i = 0; i < allGroups.length; i++) {
            if (consumed.has(i)) continue;
            const avail = allGroups[i].points.length;
            if (avail < needed) continue;
            // Score: prefer exact match (high), penalize over-allocation,
            // but reward more available slots over less.
            const score = avail === needed ? 1000 : avail - needed * 2;
            if (score > bestScore) { bestScore = score; bestIdx = i; }
        }
        return bestIdx;
    };

    const result: Array<{
        playerId: number; pickedGroupIndex: number;
        teamWithPlayerIndex: number; count: number; errors: string[];
    }> = [];
    for (let g = 0; g < pu.size; g++) {
        const grp = readListItem(pu, g);
        if (grp.isNull()) continue;
        const playerId = grp.add(PU_OFF_ID).readS32();
        const unitsList = readManagedList(
            grp.add(PU_OFF_UNITS).readPointer());
        if (!unitsList) {
            result.push({
                playerId, pickedGroupIndex: -1, teamWithPlayerIndex: -1,
                count: 0, errors: ["units list null"],
            });
            continue;
        }
        const pickedIdx = pickGroup(unitsList.size);
        if (pickedIdx < 0) {
            result.push({
                playerId, pickedGroupIndex: -1, teamWithPlayerIndex: -1,
                count: 0,
                errors: [`no SpawnPointGroup with at least ${unitsList.size} ` +
                         `points available (groups: ${allGroups.map(
                            (g, i) => `${i}=${g.points.length}`).join(",")})`],
            });
            continue;
        }
        consumed.add(pickedIdx);
        const picked = allGroups[pickedIdx];
        const errors: string[] = [];
        let count = 0;
        for (let i = 0; i < unitsList.size; i++) {
            const pUnit = readListItem(unitsList, i);
            if (pUnit.isNull()) continue;
            const unitId = readIl2cppString(
                pUnit.add(PUNIT_OFF_UNIT_ID).readPointer());
            if (!unitId) { errors.push(`slot ${i}: null unitId`); continue; }
            const sp = picked.points[i];
            try {
                const msg = buildAddUnitMessage(
                    unitId, playerId, sp.col, sp.row);
                invokeMethod(runnerApplyMi.info, runner, [msg]);
                count++;
            } catch (e) {
                errors.push(`slot ${i} (${unitId} @ ${sp.col},${sp.row}): ` +
                            `${(e as Error).message}`);
            }
        }
        result.push({
            playerId, pickedGroupIndex: pickedIdx,
            teamWithPlayerIndex: picked.teamWithPlayerIndex,
            count, errors,
        });
    }
    return { ok: result.every((r) => r.errors.length === 0), spawned: result };
}

// --- LoadBattle.onLeave : LE canal de mutation de BC ------------------------------------------
//
// Applique le patch en attente a la `BattleConfiguration` que le chargeur vient de RENDRE, dans
// l'intervalle entre sa fabrication et sa remise au runner. Plusieurs `Interceptor.attach` sur la
// meme methode sont surs -- `mode-source-capture.ts` y est deja pour la CAPTURE.
//
// ⚠ C'EST LA SEULE FENETRE QUI MORDE, MESURE LE 2026-08-23. Muter la BC APRES coup ne fait RIEN :
// le runner lit `BC.EnvironmentAbilities` a son `Initialize` et plus personne ne relit la BC
// ensuite. Sur un onslaught reel en deploiement, `applyBattleConfigPatchNow` a ecrit au BON
// pointeur (`installees: {EnhancementAbilities: 1}`) et `EnhancementDamageBoost` etait ABSENT des
// 404 effets portes en jeu.
//
// ⚠ DEUX FAMILLES DE CHARGEUR, ET UNE LISTE DE NOMS NE LES VOIT PAS. Mesure sur `methods.tsv` :
// NEUF sources surchargent `LoadBattle(isRestart)` (Campaign, Sandbox, Onslaught, Endless,
// Friendly, TreasureBeach, AutomaticBattles, SyncPvp, LinearHeroEvent) ; HUIT ne l'overrident PAS
// et implementent un `LoadBattleInternal` que la base appelle (CampaignEvent, GuildBoss,
// GuildWars, LegendaryEvent, MachinesOfWarEvent, Pvp, PvpStarterSeason, SurvivalEvent). Les deux
// rendent une `BattleConfiguration`, donc le canal vaut pour les deux -- encore faut-il viser la
// methode que CHAQUE source implemente vraiment.
//
// ⇒ ON DECOUVRE AU LIEU D'ENUMERER. On balaye les classes qui descendent d'`AGameModeSource` et on
// ancre, pour chacune, le chargeur qu'elle DECLARE. Un mode neuf est couvert sans qu'on y pense --
// c'est le regime demande : par defaut on accepte, on GARDE par exception.
//
// ⚠ `findMethod` itere `class_get_methods`, donc les methodes DECLAREES : une source qui
// n'implemente pas le nom cherche rend `null`, jamais le corps herite de la base. C'est ce qui
// rend la decouverte sure -- sans quoi ancrer une source de la 2e famille par le nom `LoadBattle`
// aurait attrape la BASE, donc toutes les autres d'un coup. Le recensement publie le chargeur
// retenu pour CHAQUE source, ce qui rend ce fait verifiable a chaque injection au lieu d'etre cru.

/** Les noms de chargeur cherches, dans l'ordre de preference. */
const NOMS_DE_CHARGEUR = ["LoadBattle", "LoadBattleInternal"] as const;

const SOURCES_REFUSEES: Readonly<Record<string, string>> = {
    SyncPvpGameModeSource:
        "PvP synchrone -- un adversaire reel joue en face.",
    // ⛔ FAUX ANCRAGE, MESURE le 2026-08-23. Son `LoadBattle` tire en PERMANENCE -- y compris quand
    // aucune bataille n'est montee -- et son retval n'est JAMAIS une `BattleConfiguration` : quatre
    // types differents observes sur autant de tirs (`List`1`, `RectTransform`, `UnitEntity`,
    // `DefaultJsonNameTable`). Signature du corps TRIVIAL DEDUPLIQUE par IL2CPP : la classe declare
    // un stub, IL2CPP fusionne son corps avec celui de dizaines de methodes sans rapport, et
    // `findMethod` rend ce corps partage. On n'ancre donc pas une source, on ancre un carrefour.
    //
    // Le degat n'est pas la corruption -- la garde de type refuse d'ecrire, c'est son role -- mais
    // l'EFFACEMENT : chaque tir ecrase `lastApply`, donc le seul temoin de ce qu'une VRAIE source a
    // installe. Mesure : une BC PvP forgee a 18:32 etait deja recouverte a 18:33 par un tir de ce
    // stub, `bcPtr` different, cibles introuvables. On lisait « les camps ne sont pas derivables »
    // en croyant juger le PvP, alors qu'on jugeait un `RectTransform`.
    TestSceneBattleModeSource:
        "corps TRIVIAL DEDUPLIQUE : le `LoadBattle` resolu est partage avec des methodes sans "
        + "rapport, tire hors de toute bataille et rend n'importe quel type -- il EFFACE `lastApply`.",
};

const NS_BASE = "IdunBattle.ViewLogic.BattleSource";
const CLS_BASE = "AGameModeSource";
const CLS_INTERFACE = "IGameModeSource";

/** `il2cpp_class_get_interfaces(klass, &iter)` -- résolu paresseusement, comme `dsl-node-probe`. */
let _classGetInterfaces: NativeFunction<NativePointer, [NativePointer, NativePointer]> | null = null;
let _cgiTente = false;
function classGetInterfaces(): typeof _classGetInterfaces {
    if (_cgiTente) return _classGetInterfaces;
    _cgiTente = true;
    try {
        const mod = Process.findModuleByName("GameAssembly.dll");
        const p = mod ? mod.findExportByName("il2cpp_class_get_interfaces") : null;
        if (p !== null) {
            _classGetInterfaces = new NativeFunction(p, "pointer", ["pointer", "pointer"]);
        }
    } catch { _classGetInterfaces = null; }
    return _classGetInterfaces;
}

/** Toutes les classes qui implémentent `IGameModeSource`, DIRECTEMENT OU PAR HÉRITAGE.
 *
 *  ⚠ AUCUN DES DEUX CRITÈRES ÉVIDENTS N'EST COMPLET, ET LES DEUX RENDENT UN RECENSEMENT
 *  D'APPARENCE SAINE. Mesuré le 2026-08-23, deux fois, sur le harnais vivant :
 *
 *    * balayer les DESCENDANTES d'`AGameModeSource` -> 8 sources, toutes en `LoadBattleInternal`.
 *      Il n'y a pas UNE hiérarchie mais TROIS racines : `Campaign`, `Onslaught`, `SyncPvp` et
 *      `LinearHeroEvent` sont des SŒURS d'`AGameModeSource` sous `AProgressionGameModeSource` ;
 *      `Endless` passe par `ATestGameModeSource` ; `Sandbox` dérive de `Object` DIRECTEMENT.
 *
 *    * balayer les interfaces DÉCLARÉES -> 10 sources, exactement les autres.
 *      `il2cpp_class_get_interfaces` ne rend que ce que la classe déclare ELLE-MÊME : les
 *      sous-classes d'`AGameModeSource` héritent l'implémentation sans la redéclarer.
 *
 *  Les deux ont rendu `nonResolues: []` — donc muets sur ce qu'ils ne visitaient pas. C'est le
 *  mode de panne du jour : un recenseur ne peut pas rendre zéro sur ce qu'il ne visite pas.
 *
 *  ⇒ L'UNION : on remonte la chaîne de parenté et on teste les interfaces À CHAQUE ÉTAGE.
 *
 *  ⚠ ET LE NOM NE MARCHE PAS NON PLUS : filtrer sur un suffixe « GameModeSource » couvrirait le
 *  build d'aujourd'hui et raterait en silence la première source nommée autrement.
 *
 *  Si `il2cpp_class_get_interfaces` n'est pas exporté, on rend `null` — PAS une liste vide : le
 *  recensement doit dire « pas mesuré », jamais « aucune source ». */
function sourcesDeMode(): NativePointer[] | null {
    const cgi = classGetInterfaces();
    const cible = findClassAnywhere(NS_BASE, CLS_INTERFACE);
    if (cgi === null || cible === null) return null;
    const it = Memory.alloc(Process.pointerSize);

    const declare = (k: NativePointer): boolean => {
        try {
            it.writePointer(ptr(0));
            let ifc: NativePointer;
            let garde = 0;
            while (!(ifc = cgi(k, it) as NativePointer).isNull() && garde++ < 64) {
                if (ifc.equals(cible)) return true;
            }
        } catch { /* illisible */ }
        return false;
    };

    const out: NativePointer[] = [];
    const domain = domain_get() as NativePointer;
    const taille = Memory.alloc(4);
    const assemblees = domain_get_assemblies(domain, taille) as NativePointer;
    const nbAsm = taille.readU32();
    for (let i = 0; i < nbAsm; i++) {
        const asm = assemblees.add(i * Process.pointerSize).readPointer();
        let image: NativePointer;
        try { image = assembly_get_image(asm) as NativePointer; } catch { continue; }
        let nb = 0;
        try { nb = image_get_class_count(image) as number; } catch { continue; }
        for (let j = 0; j < nb; j++) {
            let k: NativePointer;
            try { k = image_get_class(image, j) as NativePointer; } catch { continue; }
            if (k.isNull() || k.equals(cible)) continue;
            // La classe elle-même, puis ses ancêtres — profondeur réelle mesurée : 2 à 3.
            let p: NativePointer | null = k;
            for (let d = 0; d < 8 && p !== null && !p.isNull(); d++) {
                if (declare(p)) { out.push(k); break; }
                try { p = class_get_parent(p) as NativePointer; } catch { break; }
            }
        }
    }
    return out;
}


function installLoadBattleHook(): void {
    const poses: string[] = [];
    const manquantes: string[] = [];
    const heritees: string[] = [];

    const refusees: string[] = [];
    const heriteesCouvertes: string[] = [];
    const sansChargeurPropre: Array<{ klass: NativePointer; nom: string }> = [];
    const ancres = new Set<string>();

    // ⛔ LE CORPS DE LA BASE — RÉSOLU POUR ÊTRE REFUSÉ, JAMAIS ANCRÉ. Ancrer
    // `AGameModeSource.LoadBattle` couvrirait d'un coup TOUTES les sources qui ne l'overrident
    // pas. `findMethod` n'itère que les méthodes
    // DÉCLARÉES, donc ce cas ne devrait pas se produire — on le teste quand même, parce qu'un
    // garde de PORTÉE ne se fonde pas sur une propriété d'un helper qu'on ne contrôle pas.
    const kBase = findClassAnywhere(NS_BASE, CLS_BASE);
    const ptrsBase = new Set<string>();
    for (const nom of NOMS_DE_CHARGEUR) {
        const m = kBase ? findMethod(kBase, nom) : null;
        if (m) ptrsBase.add(m.ptr.toString());
    }

    const trouvees = sourcesDeMode();
    if (trouvees === null) {
        // TRI-ÉTAT : NON MESURÉ, jamais « aucune source ». Un recensement vide qui se lit comme
        // un fait ferait armer des patchs qui ne mordront nulle part.
        sourcesAncrees = { posees: [], nonResolues: ["<ENUMERATION IMPOSSIBLE>"],
                           couvertesParHeritage: [],
                           refuseesHeritage: [], refuseesDecision: [] };
        log("[battle-config] `il2cpp_class_get_interfaces` ou `IGameModeSource` INTROUVABLE — "
            + "aucune source découverte, patch hook désactivé (NON MESURÉ, pas « aucune »)");
        return;
    }
    for (const klass of trouvees) {
        const cls = cstr(class_get_name(klass) as NativePointer);
        const ns = cstr(class_get_namespace(klass) as NativePointer);

        const motif = SOURCES_REFUSEES[cls];
        if (motif !== undefined) {
            refusees.push(cls);
            log(`[battle-config] ${cls} NON ancrée (décision) : ${motif}`);
            continue;
        }

        // Le chargeur qu'elle DÉCLARE, dans l'ordre de préférence.
        let choisi: { nom: string; m: MethodRef } | null = null;
        for (const nom of NOMS_DE_CHARGEUR) {
            const m = findMethod(klass, nom);
            if (m) { choisi = { nom, m }; break; }
        }
        if (choisi === null) {
            // Ni l'un ni l'autre : elle hérite le chargeur d'un ancêtre. Ce n'est un TROU que si
            // cet ancêtre n'est pas ancré — sinon la source est couverte, et l'afficher parmi les
            // « non résolues » ferait croire à une brèche. On tranche par le CODE.
            sansChargeurPropre.push({ klass, nom: `${ns}.${cls}` });
            continue;
        }
        if (ptrsBase.has(choisi.m.ptr.toString())) {
            heritees.push(`${cls}.${choisi.nom}`);
            log(`[battle-config] REFUS d'ancrer ${cls} : son \`${choisi.nom}\` EST le corps de `
                + "`AGameModeSource` — l'ancrer couvrirait toutes les sources qui ne l'overrident "
                + "pas, dont celles délibérément refusées.");
            continue;
        }
        if (attacherPatchSurLoadBattle(choisi.m.ptr, cls)) {
            poses.push(`${cls}.${choisi.nom}`);
            ancres.add(choisi.m.ptr.toString());
            // ⛔ ET ON CAPTE L'INSTANCE, POUR TOUTES LES SOURCES ANCREES -- pas seulement les
            // quatre que `repliSourceCaptee` connaissait. Sans ca, `ciblesAuto: "moi"` rend 0 sur
            // l'onslaught, l'incursion et l'endless, en silence. Les capteurs sont poses sur des
            // methodes de CHARGEMENT, jamais sur ce `LoadBattle` (un second listener avec
            // `onEnter` a deja rendu 17 ancrages muets) ni sur un getter chaud.
            poserCapteursDInstance(klass, cls);
        }
    }

    // Les sources SANS chargeur propre : couvertes si l'ancêtre dont elles héritent est ancré.
    // ⚠ ON LE DÉRIVE, ON NE LE SUPPOSE PAS. Trois d'entre elles (`DebugReplay`, `Trailer`,
    // `UserReplay`) héritent d'`AReplayGameModeSource`, qui EST ancrée — les laisser en « non
    // résolues » ferait lire une brèche là où il n'y en a pas. L'inverse serait pire : conclure
    // « couverte » sans vérifier laisserait un vrai trou invisible.
    for (const { klass, nom } of sansChargeurPropre) {
        let couverte = false;
        let p: NativePointer | null = klass;
        for (let d = 0; d < 8 && p !== null && !p.isNull() && !couverte; d++) {
            try { p = class_get_parent(p) as NativePointer; } catch { break; }
            if (p === null || p.isNull()) break;
            for (const n of NOMS_DE_CHARGEUR) {
                const m = findMethod(p, n);
                if (m && ancres.has(m.ptr.toString())) { couverte = true; break; }
            }
        }
        if (couverte) heriteesCouvertes.push(nom);
        else manquantes.push(nom);
    }
    sourcesRefusees = refusees.slice();
    // ⚠ PUBLIÉ, PAS SEULEMENT LOGGÉ. C'est le cran qui manquait le 2026-08-23 : le hook n'était
    // posé que sur la campagne et le banc, l'onslaught n'était donc PATCHABLE PAR RIEN, et le seul
    // endroit qui le disait était cette ligne de `log`. Résultat : un patch armé, un `pending`
    // parfaitement visible, et une certitude fausse que « ça mordra au prochain load ». Un
    // armement doit pouvoir se confronter à la liste des sources RÉELLEMENT ancrées.
    sourcesAncrees = { posees: poses.slice(), nonResolues: manquantes.slice(),
                       refuseesHeritage: heritees.slice(), refuseesDecision: sourcesRefusees,
                       couvertesParHeritage: heriteesCouvertes.slice() };
    if (poses.length === 0) {
        log("[battle-config] AUCUNE source patchable résolue (" + manquantes.join(", ")
            + ") — patch hook désactivé");
        return;
    }
    log("[battle-config] LoadBattle.onLeave patch hook installé sur : " + poses.join(", ")
        + (manquantes.length > 0 ? " | NON RÉSOLUES : " + manquantes.join(", ") : "")
        + (heritees.length > 0 ? " | REFUSÉES (corps hérité) : " + heritees.join(", ") : ""));
}

/** La source dont le `LoadBattle` est DÉTOURNÉ par un override de BC (`sandboxModeBcOverride`),
 *  ou `null`. Déclarée par le porteur de l'override, jamais devinée ici. */
let sourceDetourneeParOverride: string | null = null;

/** `sandbox-mode` DÉCLARE qu'il remplacera le retour de `<source>.LoadBattle` par un objet à lui.
 *  Passer `null` à la levée de l'override. */
export function declarerOverrideDeBc(source: string | null): void {
    sourceDetourneeParOverride = source;
}

/** L'INSTANCE de source dont on sait qu'elle est en train de charger, DÉCLARÉE par son appelant.
 *
 * ⛔ ELLE NE PEUT PAS ÊTRE CAPTURÉE, ET C'EST MESURÉ. La voie évidente -- un `onEnter` qui garde
 * `args[0]` -- fait CESSER le tir de l'`onLeave` : mesure du 2026-08-23, les 17 ancrages muets
 * d'un coup, en silence, pendant qu'une bataille était en déploiement. Donc le porteur DÉCLARE,
 * comme pour l'override de BC juste au-dessus.
 *
 * ⚠ CE QUE ÇA CHANGE : `ciblesAuto: "moi"` a besoin de la source, parce que **la composition du
 * joueur n'est PAS dans la BC** hors campagne -- elle est déployée par le HUD. Sans elle, `moi`
 * se rabat sur `camps.miens`, qui vaut **0** sur un event ou un duel d'Arène. Mesure du
 * 2026-08-24 sur l'Incursion : `camps derives : 0 unite(s) a MOI, 6 ADVERSE(S)`.
 *
 * ⚠ QUI PEUT DÉCLARER : celui qui INVOQUE `LoadBattleInternal` lui-même, donc les forges. La voie
 * LIVE (le joueur qui lance sa bataille) n'a personne pour déclarer -- elle reste sur le repli, et
 * `lastApply` le DIT (`lineup demandee a ...` absent). Ne pas lire ce champ comme une garantie. */
let sourceEnChargement: NativePointer | null = null;

/** DÉCLARER l'instance de source qui va charger, puis la RETIRER (`null`) dès le retour.
 *  Toujours dans un `finally` : un pointeur laissé là serait servi au chargement SUIVANT, qui
 *  n'est pas le sien. */
export function declarerSourceDeChargement(src: NativePointer | null): void {
    sourceEnChargement = src !== null && !src.isNull() ? src : null;
    // ⛔ ON GARDE AUSSI LA DERNIERE, HORS DU `finally` -- ET C'EST CE QUI SAUVE LE BANC.
    // La declaration est retiree des le retour de l'invoke, alors que sur un montage SANDBOX le
    // patch s'applique PLUS TARD, a la substitution, sous le nom `SandboxGameModeSource`. A cet
    // instant plus personne n'est declare : mesure du 2026-08-24, `(source declaree : NON, repli
    // capte : NON)` sur le banc PvP meme -- donc le banc ne pouvait pas eprouver la lecture de
    // composition qu'il devait eprouver.
    // La sandbox est un TRANSPORT : la BC qu'elle substitue vient de la derniere forge. Lui
    // demander sa lineup est donc juste, et `GetBattleLineup` lit de toute facon la composition
    // SAUVEGARDEE du mode -- une instance un peu ancienne rend la meme reponse.
    if (sourceEnChargement !== null) derniereSourceForgee = sourceEnChargement;
}

/** La derniere source qu'une FORGE a declaree, jamais effacee. Sert au seul cas ou le patch
 *  s'applique sous un nom de TRANSPORT (`SandboxGameModeSource`) : cf. `repliSourceCaptee`. */
let derniereSourceForgee: NativePointer | null = null;

/** L'instance déclarée, MAIS SEULEMENT SI SA CLASSE EST CELLE QUI VIENT DE CHARGER.
 *
 * ⛔ C'EST LE CRAN QUI REND LA DÉCLARATION SÛRE. Un déclarant qui ne peut pas nettoyer (un
 * `onEnter` sans `onLeave` -- et lui en ajouter un est exactement le geste qui tue un hook)
 * laisse forcément un pointeur derrière lui. Sans cette confrontation, le chargement SUIVANT,
 * d'un tout autre mode, se verrait servir la source du précédent et lui demanderait une lineup :
 * une réponse plausible, pour la mauvaise bataille. Ici une instance qui ne concorde pas est
 * simplement IGNORÉE, et le désaccord est DIT plutôt que tu.
 *
 * `source` est le nom de classe sous lequel l'ancrage a été posé (`attacherPatchSurLoadBattle`). */
function sourceConcordante(source: string): { src: NativePointer | null; note: string | null } {
    if (sourceEnChargement === null) return { src: null, note: null };
    let classe: string | null = null;
    try { classe = cstr(class_get_name(sourceEnChargement.readPointer()) as NativePointer); }
    catch { classe = null; }
    if (classe === source) return { src: sourceEnChargement, note: null };
    return {
        src: null,
        note: `instance de source DECLAREE mais NON CONCORDANTE (\`${classe ?? "?"}\` declaree, `
            + `\`${source}\` charge) -- ignoree ; \`ciblesAuto: "moi"\` se rabat sur les camps de la BC`,
    };
}

/**
 * APPLIQUER le patch en attente à UNE `BattleConfiguration`, et publier le témoin.
 *
 * ⛔ CE FOYER EST PUBLIC PARCE QUE LA SANDBOX NE MUTE PAS, ELLE SUBSTITUE. `sandboxModeBcOverride`
 * désérialise un objet À PART puis fait `retval.replace(...)` sur le même `LoadBattle` que nous :
 * notre mutation portait donc sur l'objet que PLUS PERSONNE ne lit, pendant que la bataille
 * tournait sur le sien. Mesuré le 2026-08-23 -- patch écrit sur `0x22c13b0e200`, BC vivante
 * `0x22c1021c600`, `ok: true` et `relu: true` DES DEUX CÔTÉS, aucun signal.
 *
 * ⚠ ET C'EST LA SANDBOX QUI PERD LE PLUS À CE SILENCE : son objet est d'éprouver ce que le patch
 * FAIT. Un banc où le patch est le seul à ne pas s'appliquer valide un chemin que la vraie
 * bataille ne suit pas -- pire que pas de banc. L'override reste le TRANSPORT (monter une BC
 * arbitraire) ; le patch, lui, passe par le même pipeline des deux côtés.
 *
 * ⚠ UNE SEULE APPLICATION : le hook de `<source>.LoadBattle` s'EFFACE quand cette source est
 * déclarée détournée (`declarerOverrideDeBc`). Sans ce cran, `consumeOnce` serait consommé par la
 * mutation inutile et l'override ne recevrait rien -- exactement la panne d'origine, déplacée.
 */
export function appliquerPatchEnAttenteSur(
    bc: NativePointer, source: string, srcInstance: NativePointer | null = null,
): boolean {
    if (pendingPatch === null || bc.isNull()) return false;
    const nomRetour = (() => {
        try { return cstr(class_get_name(bc.readPointer()) as NativePointer); }
        catch { return null; }
    })();
    if (nomRetour !== "BattleConfiguration") {
        lastRejet = {
            rejeteA: new Date().toISOString(), source,
            classeRendue: nomRetour, ptr: bc.toString(),
            motif: "l'objet visé n'est pas une `BattleConfiguration` -- rien n'a été écrit, et "
                + "`lastApply` est LAISSÉ INTACT.",
        };
        return false;
    }
    const patch = pendingPatch;
    if (patch.consumeOnce !== false) pendingPatch = null;
    try {
        const result = applyPatchToConfig(bc, patch, srcInstance, source);
        result.operations.unshift(`source=${source}`);
        lastApply = result;
        log(`[battle-config] patch applied (${source}): ${result.operations.join("; ")}`
            + (result.warnings.length > 0 ? ` | warnings: ${result.warnings.join("; ")}` : ""));
        return true;
    } catch (e) {
        log(`[battle-config] patch threw: ${(e as Error).message}`);
        lastApply = {
            ok: false, appliedAt: new Date().toISOString(), bcPtr: bc.toString(),
            operations: [`source=${source}`],
            warnings: [`exception: ${(e as Error).message}`],
        };
        return false;
    }
}

/** Pose le canal de mutation sur UN `LoadBattle`. Rend `false` si l'attache échoue — une source
 *  manquante n'est pas une panne du patch, seulement un mode qu'on ne peut pas piloter. */
function attacherPatchSurLoadBattle(ptr: NativePointer, source: string): boolean {
    try {
        Interceptor.attach(ptr, {
            // ⛔ PAS D'`onEnter` SUR CE LISTENER -- IL EN TUE LE TIR, MESURE DEUX FOIS.
            // On en avait posé un pour capturer `args[0]` (la source, seule à connaître la
            // composition du joueur, dont `ciblesAuto: "moi"` a besoin). Effet mesuré le
            // 2026-08-23 : plus AUCUN `onLeave` ne tire -- ni `lastApply` ni `lastRejet` pendant
            // qu'une bataille de campagne était en déploiement à l'écran, et les 17 ancrages
            // devenus muets D'UN COUP. Même symptôme, même cause, sur le listener d'override de
            // `sandbox-mode`. La dégradation est TOTALEMENT SILENCIEUSE : `sourcesAncrees.posees`
            // continue d'annoncer 17 sources, parce qu'elle rapporte l'INSTALLATION, pas le TIR.
            //
            // ⚠ CE QUE ÇA COÛTE, ET C'EST ASSUMÉ : `ciblesAuto: "moi"` ne peut pas interroger la
            // source depuis ici, donc il se rabat sur les camps dérivés de la BC. Un meilleur
            // ciblage ne vaut pas la perte du canal de mutation tout entier.
            onLeave(retval) {
                if (pendingPatch === null) return;
                if (retval.isNull()) return;
                // ⛔ CETTE SOURCE EST DETOURNEE : son retour sera REMPLACE par l'objet d'un
                // override, et muter `retval` ici n'atteindrait que l'objet abandonne. On laisse
                // le porteur de l'override appliquer -- il vise le bon objet, et il est SEUL a
                // savoir lequel. Consommer `consumeOnce` ici le priverait du patch.
                if (sourceDetourneeParOverride === source) return;
                // ⛔ LE TYPE D'ABORD, ET AVANT DE TOUCHER `lastApply`. Un chargeur qui ne rend pas
                // une `BattleConfiguration` n'a rien a nous dire -- mais tant que son passage
                // ECRIVAIT `lastApply`, il EFFACAIT le seul temoin de ce qu'une vraie source avait
                // installe. Mesure du 2026-08-23, DEUX fois : `TestSceneBattleModeSource` (retval
                // `List`1` / `RectTransform` / `UnitEntity` / `DefaultJsonNameTable`) puis
                // `AReplayGameModeSource` (`this` = `ExpeditionProgressionData`, retval `List`1`).
                // Ce sont des corps TRIVIAUX DEDUPLIQUES par IL2CPP : on croit ancrer une methode,
                // on ancre un carrefour partage avec des dizaines d'autres.
                //
                // ⚠ ON REFUSE PAR INVARIANT, PAS PAR LISTE NOIRE. Nommer les deux coupables connus
                // laisserait passer le troisieme -- et il y en aura un, la deduplication ne se
                // decrete pas. Le rejet est publie dans `lastRejet` : muet, il ferait chercher un
                // hook qui ne se pose pas.
                const nomRetour = (() => {
                    try { return cstr(class_get_name(retval.readPointer()) as NativePointer); }
                    catch { return null; }
                })();
                if (nomRetour !== "BattleConfiguration") {
                    lastRejet = {
                        rejeteA: new Date().toISOString(), source,
                        classeRendue: nomRetour, ptr: retval.toString(),
                        motif: "le chargeur n'a pas rendu une `BattleConfiguration` -- corps "
                            + "trivial DEDUPLIQUE, l'ancrage vise un carrefour partage. `lastApply` "
                            + "est LAISSE INTACT : un passage qui n'ecrit rien n'efface rien.",
                    };
                    return;
                }
                const patch = pendingPatch;
                if (patch.consumeOnce !== false) {
                    pendingPatch = null; // consume now to avoid re-apply
                }
                try {
                    // L'instance de source est DÉCLARÉE par qui la connaît (une forge, ou le
                    // capteur `onEnter` d'un builder), jamais capturée ici : un `onEnter` sur CE
                    // listener le tuerait. Elle n'est retenue que si sa CLASSE concorde avec la
                    // source qui charge -- sinon c'est un reliquat, et on le DIT.
                    const declaree = sourceConcordante(source);
                    const result = applyPatchToConfig(retval, patch, declaree.src, source);
                    if (declaree.note !== null) result.warnings.push(declaree.note);
                    // La SOURCE est publiée : sans elle, un `lastApply` ne dit pas si le patch a
                    // mordu sur la campagne ou sur le banc, et les deux se lisent pareil.
                    result.operations.unshift(`source=${source}`);
                    lastApply = result;
                    log(`[battle-config] patch applied (${source}): ` +
                        `${result.operations.join("; ")}` +
                        (result.warnings.length > 0
                            ? ` | warnings: ${result.warnings.join("; ")}`
                            : ""));
                } catch (e) {
                    log(`[battle-config] patch threw: ${(e as Error).message}`);
                    lastApply = {
                        ok: false,
                        appliedAt: new Date().toISOString(),
                        bcPtr: retval.toString(),
                        operations: [],
                        warnings: [`exception: ${(e as Error).message}`],
                    };
                }
            },
        });
        return true;
    } catch (e) {
        log(`[battle-config] attache sur ${source}.LoadBattle refusée : ${(e as Error).message}`);
        return false;
    }
}

export function register(ctx: Ctx): void {
    installLoadBattleHook();

    ctx.rpc.inspectBattleConfig = () => queueOnMainThread(
        () => inspectBattleConfig());

    /** Dump SpawnPointSets structure for the live BC — useful to figure
     * out which group serves which player. */
    ctx.rpc.inspectSpawnPoints = () => queueOnMainThread(() => {
        const bc = getLiveBattleConfig();
        if (bc === null) return { ok: false, err: "no live BC" };
        const board = bc.add(BC_OFF_BOARD).readPointer();
        if (board.isNull()) return { ok: false, err: "board null" };
        const setIdx = bc.add(BC_OFF_SPAWN_POINT_SET_INDEX).readS32();
        const sets = readManagedList(
            board.add(BCBC_OFF_SPAWN_POINT_SETS).readPointer());
        if (!sets) return { ok: false, err: "spawn point sets null" };
        const allSets = [];
        for (let s = 0; s < sets.size; s++) {
            const set = readListItem(sets, s);
            const groups = readManagedList(
                set.add(SPS_OFF_SPAWN_GROUPS).readPointer());
            const grpInfo = [];
            if (groups) {
                for (let g = 0; g < groups.size; g++) {
                    const grp = readListItem(groups, g);
                    const team = grp.add(SPG_OFF_TEAM_PLAYER_INDEX).readS32();
                    const pts = readManagedList(
                        grp.add(SPG_OFF_SPAWN_POINTS).readPointer());
                    const ptList = [];
                    if (pts) {
                        for (let p = 0; p < pts.size; p++) {
                            const sp = readListItem(pts, p);
                            ptList.push({
                                col: sp.add(SP_OFF_COL).readS32(),
                                row: sp.add(SP_OFF_ROW).readS32(),
                            });
                        }
                    }
                    grpInfo.push({
                        groupIndex: g,
                        teamWithPlayerIndex: team,
                        count: ptList.length,
                        points: ptList,
                    });
                }
            }
            allSets.push({
                setIndex: s,
                active: s === setIdx,
                groupCount: groups?.size ?? 0,
                groups: grpInfo,
            });
        }
        return { ok: true, activeSetIndex: setIdx, sets: allSets };
    });

    /** Set the patch applied at the next LoadBattle. Pass null/undefined
     * fields to leave them unchanged. Default consumeOnce=true means the
     * patch is cleared after one application — set consumeOnce=false to
     * make it sticky across multiple battles. */
    ctx.rpc.setBattleConfigPatch = (patch: BattleConfigPatch) => {
        if (!patch || typeof patch !== "object") {
            return { ok: false, err: "patch must be an object" };
        }
        pendingPatch = { ...patch };
        return {
            ok: true,
            stored: pendingPatch,
            note: "applied at next CampaignGameModeSource.LoadBattle",
        };
    };

    ctx.rpc.clearBattleConfigPatch = () => {
        pendingPatch = null;
        return { ok: true };
    };

    ctx.rpc.getBattleConfigPatchStatus = () => ({
        ok: true,
        pending: pendingPatch,
        lastApply,
        lastRejet,
        // `sourcesAncrees.posees` dit sur QUELS modes un `pending` peut mordre. Un patch armé pour
        // un mode absent de cette liste n'a AUCUNE chance de s'appliquer -- et rien d'autre ne le
        // signale. `null` = pose pas encore tentée, ce n'est PAS « aucune ».
        sourcesAncrees,
        // Les INSTANCES de source connues, et le compte de pointeurs périmés jetés. `retenues: 0`
        // dit « aucun capteur n'a tiré » -- à ne pas lire comme « aucune source ».
        instancesDeSource: etatDuRegistre(),
    });

    /** Apply a patch DIRECTLY to the live BattleConfiguration (no LoadBattle
     * required). Useful when the battle is already loaded and you want to
     * tweak stats mid-deployment, or when inspectBattleConfig already shows
     * a live config. */
    ctx.rpc.applyBattleConfigPatchNow = (patch: BattleConfigPatch) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) {
                return {
                    ok: false,
                    err: "no live BattleConfiguration to mutate",
                };
            }
            const result = applyPatchToConfig(bc, patch);
            lastApply = result;
            return result;
        });
    };

    /** Build a fresh ISOLATED IdunRunner from the live captured
     * BattleConfiguration, optionally applying a patch first.
     *
     * This is the clean RL workflow: no UI involvement, no in-game battle
     * lifecycle. The new runner is constructed with the patched config —
     * since StartingActions (spawn messages) are built INSIDE Initialize()
     * from PredefinedUnits, our patch IS reflected in what spawns.
     *
     * The runner is registered in the runner-registry; the returned
     * `runnerId` can then be used with `observeBattle({runnerId})`,
     * `applyAddUnit`, `startBattle`, etc.
     *
     * The original captured BC is mutated in-place. Callers wanting to
     * preserve the original should clone it first (not yet implemented). */
    ctx.rpc.diagPredefMachinesFires = () => ({ fires: _addPredefMachinesFires });

    /** Sérialise la BC live (Pvp prioritaire, fallback Campaign) en JSON
     * Newtonsoft. Le JSON peut ensuite être passé à `initRunner` pour
     * construire un runner isolé reproductible. */
    ctx.rpc.dumpBattleConfig = () => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return { ok: false, err: "no live BC" };
            try {
                // serializeToJson est dans il2cpp/serializer.ts. Faut l'importer.
                const json = _serializeBcToJson(bc);
                if (json === null) return { ok: false, err: "serializeToJson returned null" };
                return { ok: true, bcPtr: bc.toString(), jsonLength: json.length, configJson: json };
            } catch (e) {
                return { ok: false, err: (e as Error).message };
            }
        });
    };

    /** Force discovery heap-scan : trouve les GameModeSource instances déjà
     * vivantes en mémoire (après reinject ou inject mid-game). Utile pour
     * retrouver une battle PvP/MoW Event déjà lancée. */
    ctx.rpc.discoverSources = async (opts?: {
        chunkMb?: number; pauseMs?: number;
    }) => {
        // tryActiveDiscoveryOfSources is sync — Campaign scan is short.
        const ok = await queueOnMainThread(() => tryActiveDiscoveryOfSources());
        // Pvp via heap scan chunked + async (yield au main thread Tacticus
        // entre chunks, pour ne pas trigger UnityFreezeDetector).
        if (getPvpGameModeSourcePtr() === null) {
            try {
                await findPvpGameModeSourceViaHeap({
                    chunkMb: opts?.chunkMb ?? 4,
                    pauseMs: opts?.pauseMs ?? 30,
                });
            } catch { /* leave null */ }
        }
        return {
            ok,
            campaign: getCampaignGameModeSourcePtr()?.toString() || null,
            pvp: getPvpGameModeSourcePtr()?.toString() || null,
            mowEvent: getMowEventGameModeSourcePtr()?.toString() || null,
        };
    };

    /** Override BC.RuleSet (Nullable<SyncPvpRuleSet>). Test hypothesis :
     * SetupGameOperation peut gate AddPredefinedMachines sur RuleSet != null. */
    ctx.rpc.setBattleConfigRuleSet = (opts: { rule: number | null }) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return { ok: false, err: "no live BC" };
            const prevHas = bc.add(BC_OFF_RULESET_HASVALUE).readU8();
            const prevVal = bc.add(BC_OFF_RULESET_VALUE).readS32();
            if (opts.rule === null) {
                bc.add(BC_OFF_RULESET_HASVALUE).writeU8(0);
                bc.add(BC_OFF_RULESET_VALUE).writeS32(0);
            } else {
                bc.add(BC_OFF_RULESET_HASVALUE).writeU8(1);
                bc.add(BC_OFF_RULESET_VALUE).writeS32(opts.rule | 0);
            }
            return {
                ok: true,
                prev: { hasValue: prevHas !== 0, value: prevVal },
                cur: { hasValue: opts.rule !== null, value: opts.rule ?? 0 },
            };
        });
    };

    /** Override BC.GameMode (Nullable<GameMode>). Set to 1 (PvP) to unlock
     * MoW handling — Campaign (0) skips MoW deployment in
     * SetupGameOperation. Pass null to clear (hasValue=false). */
    ctx.rpc.setBattleConfigGameMode = (opts: { mode: number | null }) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return { ok: false, err: "no live BC" };
            const prevHas = bc.add(BC_OFF_GAMEMODE_HASVALUE).readU8();
            const prevVal = bc.add(BC_OFF_GAMEMODE_VALUE).readS32();
            if (opts.mode === null) {
                bc.add(BC_OFF_GAMEMODE_HASVALUE).writeU8(0);
                bc.add(BC_OFF_GAMEMODE_VALUE).writeS32(0);
            } else {
                bc.add(BC_OFF_GAMEMODE_HASVALUE).writeU8(1);
                bc.add(BC_OFF_GAMEMODE_VALUE).writeS32(opts.mode | 0);
            }
            return {
                ok: true,
                prev: { hasValue: prevHas !== 0, value: prevVal },
                cur: { hasValue: opts.mode !== null, value: opts.mode ?? 0 },
            };
        });
    };

    /** Add a MoW to the live BC.PredefinedMachines list. The MoW will be
     * auto-deployed by runner.Initialize() when the next runner is built
     * from this BC. Campaign mode normally leaves this list empty
     * (SupportsMachinesOfWar=false) — calling this is how we inject MoW
     * into our RL battles. To deploy a *player* MoW use `applyAddMachine`
     * (runtime AddMachineMessage) instead — players add their MoW after
     * Initialize(), like for units (applyAddUnit). */
    ctx.rpc.addPredefinedMachine = (opts: {
        playerId: number; unitId: string;
    }) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return {
                ok: false, err: "no live BC — amorce first" };
            if (!predefinedMachinesOfWarClass
                || !predefinedMachinesOfWarCtor
                || !predefinedMachineOfWarClass
                || !(predefinedMachineOfWarCtor1 || predefinedMachineOfWarCtor0)) {
                return { ok: false, err: "PredefinedMachine class/ctor not resolved" };
            }
            try {
                // 1. PredefinedMachineOfWar { UnitId }
                const inner = il2cpp_object_new(
                    predefinedMachineOfWarClass) as NativePointer;
                if (inner.isNull()) throw new Error("alloc PredefinedMachineOfWar");
                gcRoot.add(inner);
                const unitIdStr = createManagedString(opts.unitId);
                if (predefinedMachineOfWarCtor1) {
                    invokeMethod(predefinedMachineOfWarCtor1.info, inner,
                        [unitIdStr]);
                } else {
                    invokeMethod(predefinedMachineOfWarCtor0!.info, inner, null);
                    inner.add(PMOW_OFF_UNIT_ID).writePointer(unitIdStr);
                }
                // 2. PredefinedMachinesOfWar wrapper { Id=playerId, MachineOfWar=inner }
                const wrapper = il2cpp_object_new(
                    predefinedMachinesOfWarClass) as NativePointer;
                if (wrapper.isNull()) throw new Error("alloc PredefinedMachinesOfWar");
                gcRoot.add(wrapper);
                invokeMethod(predefinedMachinesOfWarCtor.info, wrapper, null);
                wrapper.add(PMOW_OFF_PLAYER_ID).writeS32(opts.playerId);
                wrapper.add(PMOW_OFF_MACHINE).writePointer(inner);
                // 3. List<PredefinedMachinesOfWar>.Add(wrapper)
                const listPtr = bc.add(BC_OFF_PREDEFINED_MACHINES).readPointer();
                if (listPtr.isNull()) {
                    return { ok: false, err: "BC.PredefinedMachines list is null" };
                }
                const listKlass = listPtr.readPointer();
                const addMi = findMethodByParamCount(listKlass, "Add", 1);
                if (!addMi) return { ok: false, err: "List.Add(1) not found" };
                invokeMethod(addMi.info, listPtr, [wrapper]);
                return { ok: true, playerId: opts.playerId,
                         unitId: opts.unitId,
                         listSize: listPtr.add(LIST_OFF_SIZE).readS32() };
            } catch (e) {
                return { ok: false, err: (e as Error).message };
            }
        });
    };

    /** Auto-spawn all PredefinedUnits into the given runner. Maps each
     * PredefinedUnits group to the SpawnPointGroup at the same index, and
     * each unit to its corresponding SpawnPoint. */
    ctx.rpc.spawnPredefinedUnits = (opts: { runnerId: number }) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) return { ok: false, err: "no live BC" };
            try {
                const entry = getRegistryRunner(opts.runnerId);
                return spawnPredefinedUnitsInto(entry.runner, bc);
            } catch (e) {
                return { ok: false, err: (e as Error).message };
            }
        });
    };

    // `owner` (2e argument, facultatif) : étiquette du propriétaire enregistrée
    // dans le registre — cf. runner-registry.ts.
    ctx.rpc.buildPatchedRunner = (patch?: BattleConfigPatch, owner?: string) => {
        return queueOnMainThread(() => {
            const bc = getLiveBattleConfig();
            if (bc === null) {
                return {
                    ok: false,
                    err: "no live BattleConfiguration captured — " +
                         "autoBootExtraire first",
                };
            }
            // Same hard cap as initAndStart — this path never disposed
            // siblings (already coexist), only the gcRoot budget guard
            // was missing.
            const active = listRegistryRunners();
            if (active.length >= MAX_RUNNERS) {
                return {
                    ok: false,
                    err: "runner cap reached (" + MAX_RUNNERS + ") — dispose "
                         + "one first (disposeRunner). Active runnerIds: "
                         + active.map((r) => r.runnerId).join(", "),
                };
            }
            let patchResult: PatchApplyResult | null = null;
            if (patch) {
                patchResult = applyPatchToConfig(bc, patch);
                lastApply = patchResult;
            }
            try {
                const handle = buildRunner(bc);
                const entry = registerRunner(handle,
                    { autoDispose: false, owner });
                log(`[battle-config] buildPatchedRunner: runnerId=` +
                    `${entry.runnerId} runner=${handle.runner} seed=${handle.seed}`);
                return {
                    ok: true,
                    runnerId: entry.runnerId,
                    runner: handle.runner.toString(),
                    seed: handle.seed,
                    bcPtr: bc.toString(),
                    patch: patchResult,
                };
            } catch (e) {
                return {
                    ok: false,
                    err: `buildRunner failed: ${(e as Error).message}`,
                    patch: patchResult,
                };
            }
        });
    };
}
