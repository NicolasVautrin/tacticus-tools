/** RPCs SNAPSHOT stats/config/effets : combatSnapshot (capteur #100 abilityStates),
 *  statModSources, effectAbilityStates, unitAbilityStates, abilityConfigProbe, varTrace*.
 *  Scinde de rpc-view.ts (2026-07-11, >2300 l. — seuil ~1000 l.) ; l'API RPC est
 *  INCHANGEE (memes noms ctx.rpc.*), agregee par registerView (rpc-view.ts). */
import {
    class_get_element_class, class_get_name, class_get_namespace, class_instance_size,
    class_is_valuetype, findClass, findClassAnywhere, findMethod,
    fieldOffsetOr, findMethodByParamClasses, findMethodByParamCount, getFieldOffset,
    readIl2cppString, s,
} from "../../il2cpp/helpers.js";
import { invokeMethod } from "../../il2cpp/invoke.js";
import { dumpEnum } from "../../il2cpp/enum-dump.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import { runnerClass, runnerOff } from "../../game/runner.js";
import { getRunner } from "../../game/runner-registry.js";
import { setTraceOrigin } from "../../game/trace-origin.js";
import {
    EntityType, forEachComponent, forEachEntity, projectMatchState,
    readBattleStatus, unitFootComponentClass,
} from "../../game/match-state.js";
import {
    readAllEffects, readEffectsByUnit, readEffectsByTile, readRoundCapClock,
    readEffectAbilityStateRaw,
} from "../../game/effects.js";
import { state } from "../../game/state.js";
import { readDamagePredictionResult } from "../../game/damage-prediction.js";
import {
    LIVE_PROBE as RARITY_PROBE, RarityResolution, resolveRarityChannel,
} from "../../game/rarity.js";
import { queueOnMainThread } from "../../runtime/queue.js";
import { abilityName } from "../../data/ability-names.js";
import { TARGETING_RULE_BITS } from "../../data/targeting-rule-names.js";
import { Ctx } from "../../controller.js";
import {
    ActionResult, ActionSpec, abilityStateLayout, activeAbilityMsgClass, applyOneAction,
    attackQueryOff, battleInServicesOff, dpqInServicesOff, entityServicesClass,
    extractTiles, extractTilePtrs,
    entityExtClass, finishUnitTurnMsgClass, getMovableTilesMi, getTilesMi, getTurnsFinishedMi,
    getUnitMainTile,
    invokeBool, invokeInt, isAliveMi, isCtrlByCurMi, LIST_SIZE, moveUnitMsgClass, movementQueryOff,
    mowAbilityTypes, nullableLayoutOf, readAbilityState, readTileCoord, readTurnsEnded, resolveDpq,
    servicesOff,
    summarize, turnsEndedLayout, unitAbilityTypes,
    unitExtClass,
} from "./internals.js";
import { applyAiMsgMi } from "../../game/ai-control.js";
import {
    classFieldsDump, computeAttackPlans, computeDangerZone, computeExposure,
    projectMowsFull, projectUnitsFull, readParentLink,
} from "./projection.js";

// --- Snapshot one-shot des stats de combat résolues (prédiction 100% offline, doc §16) ---
// `UnitExtensions.GetStat(actor, StatType, StatPart, Nullable<BEntityId>)` (static 4-args
// @180ed3cb0) → valeur résolue (boxée int @+0x10). StatPart.Current=0 = valeur courante.
// StatType (enum): Attack=0 Movement=1 Defense=3 Health=5 BlockChance=7 BlockDamage=8
// CriticalChance=9 CriticalDamage=10 FixedArmor=16 ExtraHits=17 ExtraPierceMelee=21
// ExtraPierceRanged=22 ExtraMaxDamage=25 ExtraPierce=26. Faction/class/profil/traits = gameconfig ;
// effets = decisionView. C'est le SEUL accès live (one-shot au chargement BC) du prédicteur offline.
const getStatMi = unitExtClass ? findMethodByParamCount(unitExtClass, "GetStat", 4) : null;
// StatType ids (enum) partagés par `combatSnapshot` + `statModSources` — source unique
// (évite la divergence si on ajoute un stat d'un côté seulement, cf. discipline « check own port »).
const COMBAT_STAT_IDS: Record<string, number> = {
    attack: 0, movement: 1, defense: 3, health: 5, blockChance: 7,
    blockDamage: 8, critChance: 9, critDamage: 10,
    turnsStarted: 12,   // #122 : UnitComponent.turnsStarted@+0x58 (incr. StartTurn) = rounds started ;
                        // GetStat(unit,0xc) = UnitTurnsStartedFormula.Calculate @180f2d6c0. Base des
                        // hits Executioner (RoundsStarted).
    fixedArmor: 16,
    extraHits: 17, activeAbilityLevel: 18, numberOfMembers: 20,
    extraPierceMelee: 21, extraPierceRanged: 22, extraHitsMelee: 23,
    // 24 ExtraRange : la table sautait de 23 a 25, et le trou etait INVISIBLE -- un port qui
    // pose ce stat n'avait aucun moyen de l'observer. Constate le 2026-07-27 sur le volet
    // Movement/Range de RealityUnbound, livre sans mesure faute de canal.
    extraRange: 24,
    extraMaxDamage: 25, extraPierce: 26,
    // #477-r15-r4 — `StatType.Range` (2). Le trou était du MÊME genre que celui d'`extraRange`
    // ci-dessus, mais sur un stat que le jeu ÉCRIT dans son flux de replay : la surcharge
    // `IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags(unit)` émet
    // `Tag=UnitStats_Range` (31) depuis `StatComponent$$get_CurrentValue` du composant que le
    // `case 2` d'`IdunBattle.Entities.UnitExtensions$$GetStatComponent` associe à `StatType.Range`
    // — appariement PROUVÉ par identité de pointeur de classe entre les deux décompilés, pas
    // déduit du nom. Aucun RPC ne le publiait, donc l'émetteur de flux posait `0` EN DUR.
    //
    // ⚠ CE QUE `GetStat(unit, Range, StatPart.Current)` REND EXACTEMENT, et pourquoi c'est le
    // mirror 1:1 de la lecture native : le `case 2` de la jumptable d'`UnitExtensions$$GetStat`
    // charge le MÊME pointeur de classe, puis appelle
    // `IdunBattle.Entities.Components.StatComponent$$GetStatPart`, dont les `case 0` (Current) ET
    // `case 2` (Maximum) rendent tous deux `get_CurrentValue(this)`. Ce n'est donc pas une
    // approximation du tag : c'est le même appel.
    //
    // ⚠ `GetStat` exige `entity.Type == EntityType.Unit` pour ce `StatType` (la 2ᵉ liste du switch,
    // celle qui n'accepte PAS `EntityType.Machine`) : sur une Machine of War il rend un pointeur
    // nul, que `getStatP` publie en `null` = PAS MESURÉ. Le tri-état est ce qui rend ce cas
    // lisible plutôt que rabattu sur un `0` qui se lirait comme une mesure.
    range: 2,
};

// --- #477-r15-r7 — les `StatType` lus UNIQUEMENT en `StatPart.Maximum`, HORS de la table ------
//
// POURQUOI UNE SECONDE TABLE, ET PAS UNE ENTRÉE DE PLUS DANS `COMBAT_STAT_IDS`. Celle-ci n'est
// pas seulement la table de `combatSnapshot` : elle est publiée telle quelle sous `statTypes`, et
// `engine/entities/stats.py::seed_unit_stats` l'ITÈRE pour seeder un `StatComponent` par entrée
// dans tout `UnitContext` reconstruit d'une capture live. Or `StatType.Armor` (4) n'est PAS un
// `StatComponent` côté natif — c'est un `IdunBattle.Entities.Components.FillUpStatComponent`,
// comme la santé et les membres (`engine/entities/stats.py::_FILLUP_STATS`). L'ajouter à
// `COMBAT_STAT_IDS` ferait donc matérialiser un composant de la MAUVAISE famille, en plus de
// publier un `stats.armor` que personne ne lit. La table séparée n'alimente QUE les buffers d'id
// de `getStatP` — elle ne sort pas du RPC.
//
// CE QUE MESURE `armor` ICI, ET POURQUOI C'EST LE MIRROR EXACT DU TAG. La surcharge
// `IdunBattle.Entities.UnitExtensions$$GetFullStateUpdateTags(unit)` émet
// `Tag=UnitStats_MaxArmor` (13) depuis
// `IdunBattle.Entities.Components.FillUpStatComponent$$get_CurrentMaximumValue()` du composant
// d'ARMURE. `IdunBattle.Entities.UnitExtensions$$GetStat` n'a PAS de switch écrit : son `case 4`
// passe par une jumptable, dont l'entrée charge le MÊME `Il2CppClass*` de `T` et le MÊME
// `MethodInfo*` de `GetComponent<T>` que la ligne du tag — identité de pointeur relue sur les
// deux décompilés, pas déduite du nom — puis appelle
// `IdunBattle.Entities.Components.FillUpStatComponent$$GetStatPart`, dont le `case 2` (Maximum)
// EST `get_CurrentMaximumValue()`. `GetStat(unit, StatType.Armor, StatPart.Maximum)` est donc
// littéralement l'appel du tag.
//
// ⚠ `IdunBattle.Entities.UnitExtensions$$GetStatComponent`, LUI, n'a aucun `case 4` — ni `case 5`
// (santé), ni `case 0x14` (membres) : les trois « fill-up » en sont absents. Conclure de cette
// absence que l'armure n'a pas de canal est le piège exact que cette tranche a levé : `GetStat`
// ne passe PAS par `GetStatComponent`, il porte sa PROPRE jumptable, et celle-ci couvre les
// trois. C'est la même voie que `healthMax` (#45b') et `numberOfMembersMax` (#477-r15-r5)
// empruntent déjà.
//
// ⚠ Comme `range`, `StatType.Armor` est dans la 2ᵉ liste du switch de garde de `GetStat`, celle
// qui exige `entity.Type == EntityType.Unit` : sur une Machine of War l'appel rend un pointeur
// nul, publié en `null` = PAS MESURÉ (jamais rabattu sur `0`).
const STAT_IDS_MAX_SEUL: Record<string, number> = {
    armor: 4,
};

// --- UnitFlag PAR UNITÉ (O5) — mirror de `IdunBattle.Entities.UnitExtensions$$HasFlag` ---
//
// `IdunBattle.Entities.Components.UnitFlagsComponent` range ses flags dans un
// `idun.shared.collections.OrderedSet<UnitFlag>` @+0x10 (cf. son `$$.ctor`), et son `$$Has` n'y
// accède QUE par un appel d'interface FULLY-SHARED générique. La disposition interne de ce set
// n'est donc pas lisible de façon fiable depuis Frida — on ne la lit PAS. On invoque à la place la
// fonction NOMMÉE que le jeu appelle lui-même (`HasFlag(unit, flag)` : c'est littéralement la ligne
// `uVar1 = UnitExtensions.HasFlag(defender, 0x13)` d'`ApplyTraitDamageLimitsToDamage`), une fois
// par valeur d'enum. Read-only intégral.
const hasFlagMi = unitExtClass ? findMethodByParamCount(unitExtClass, "HasFlag", 2) : null;

// TRAITS RUNTIME (#233) — même raison, même remède que les flags ci-dessus. Le port
// reconstruisait les traits depuis le substrat (gameconfig + dérivation d'alliance) et depuis son
// propre leaf `AddTrait` : il ne pouvait RIEN confronter. Un trait accordé EN BATAILLE lui était
// invisible.
//
// SÉMANTIQUE, lue au décompilé de `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` —
// trois collections, et la première est un VETO :
//
//   HasTrait(t) == !retirés(+0x50).Contains(t) && ( permanents(+0x40).Contains(t)
//                                                || temporaires(+0x48).Contains(t) )
//
// `IdunBattle.Operations.AddTraitOperation$$Execute` écrit `+0x40` quand `isTemporary == 0`,
// `+0x48` sinon. ⚠ `IdunBattle.Operations.RemoveTraitOperation$$RemoveTrait` NE remplit PAS `+0x50` :
// il RETIRE de `+0x40`/`+0x48` selon le même `isTemporary`. Le retrait est donc DESTRUCTIF sur les
// ensembles additifs, pas additif sur un ensemble de veto — l'écrivain de `+0x50` reste à
// identifier (résidu nommé de #233).
//
// POURQUOI ON N'EXPOSE PAS LES TROIS COLLECTIONS SÉPARÉMENT : ce sont des
// `idun.shared.collections.OrderedSet<UnitTrait>` interrogés par appel d'interface FULLY-SHARED —
// exactement la disposition que le bloc `unitFlags` déclare non lisible de façon fiable. La lire
// « quand même » reviendrait à deviner un layout, précisément ce que la doctrine interdit. On
// invoque donc la fonction NOMMÉE que le jeu appelle lui-même, `UnitExtensions$$HasTrait(unit,
// trait)`, une fois par valeur d'enum : elle rend l'ensemble EFFECTIF, veto compris — c'est-à-dire
// ce que TOUS les gates de traits lisent réellement.
const hasTraitMi = unitExtClass ? findMethodByParamCount(unitExtClass, "HasTrait", 2) : null;

// Valeurs de `IdunBattle.Entities.Enum.UnitTrait`, LUES AU RUNTIME — même discipline que
// `unitFlagTypes` : aucune table du dépôt, une renumérotation de build se propage seule.
let unitTraitTypesCache: Record<string, number> | null = null;
function unitTraitTypes(): Record<string, number> {
    if (unitTraitTypesCache) return unitTraitTypesCache;
    const raw = dumpEnum("IdunSharedAssembly.dll", "IdunBattle.Entities.Enum", "UnitTrait") ?? {};
    const out: Record<string, number> = {};
    for (const k of Object.keys(raw)) {
        const v = parseInt(raw[k], 10);
        if (Number.isFinite(v)) out[k] = v;
    }
    unitTraitTypesCache = out;
    return out;
}

// Valeurs de `IdunBattle.Entities.Enum.UnitFlag`, LUES AU RUNTIME (`dumpEnum` — littéraux de la
// métadonnée IL2CPP), jamais recopiées dans une table du dépôt : une RENUMÉROTATION au prochain
// build se propage alors toute seule. Une constante en dur, elle, resterait syntaxiquement valide
// et deviendrait FAUSSE en silence — c'est exactement le mode de panne que le diff `enums.tsv` de
// la procédure de MAJ sert à rattraper, et qu'on préfère ne pas créer. Mémoïsé : `dumpEnum` parcourt
// les champs de la classe, inutile de le refaire à chaque unité.
let unitFlagTypesCache: Record<string, number> | null = null;
function unitFlagTypes(): Record<string, number> {
    if (unitFlagTypesCache) return unitFlagTypesCache;
    const raw = dumpEnum("IdunSharedAssembly.dll", "IdunBattle.Entities.Enum", "UnitFlag") ?? {};
    const out: Record<string, number> = {};
    for (const k of Object.keys(raw)) {
        const v = parseInt(raw[k], 10);
        if (Number.isFinite(v)) out[k] = v;
    }
    unitFlagTypesCache = out;
    return out;
}

// --- #419-r1-tr14-r5-r2-r2-r1 — l'état PRÉ-FABRIQUE des actives -------------------------------
//
// POURQUOI CE CANAL EXISTE. La garde du repli générique de
// `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` teste la collection
// **AVANT** que la générique n'y soit ajoutée. Or le seul canal du port
// (`UnitContext.active_abilities`, alimenté par `unitAbilityStates.units[].actives`) lit
// l'`ActiveAbilityComponent` **APRÈS** la fabrique : il contient donc déjà la réponse, ce qui rend
// la garde tautologique et court-circuite les trois voies amont. `normal_attack_already_present`
// (`engine/services/custom_normal_attack.py`) est porté mais délibérément NON branché pour cette
// seule raison.
//
// LE SUBSTRAT EXACT, LU. `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromActive`
// énumère `config.<+0xa0>` ; la disposition mesurée au runtime (RPC `classFields`, build
// `rnca9r7q6c`) nomme ce champ `IdunBattle.Configuration.UnitConfiguration.ActiveAbilities`, un
// `List<ActiveAbilityType>` — accord exact entre le décompilé et les métadonnées, sur les deux
// voisins aussi (`PassiveAbilities` @+0xa8 et `Traits` @+0xd0, cités par la case-doc de la tranche).
//
// LA JOINTURE entité → configuration est LUE, pas supposée :
// `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent(entity, config)` écrit
// `baseUnitComponent.<Id @+0x10> = config.<Id @+0x10>` (et `VisualId` depuis `config+0x18`).
// La clé est donc `BaseUnitComponent.Id`, obtenu par la fonction NOMMÉE
// `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent` — celle-là même que la fabrique
// appelle. Plusieurs entités peuvent partager une configuration (deux camps, même unité) : c'est
// une jointure N→1, et `configIdCollisions` publie le cas contraire s'il se présente.
const battleConfigurationClass = findClassAnywhere(
    "IdunBattle.Configuration", "BattleConfiguration");
const unitConfigurationClass = findClassAnywhere(
    "IdunBattle.Configuration", "UnitConfiguration");
const baseUnitComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "BaseUnitComponent");
const getBaseUnitComponentMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "GetBaseUnitComponent", 1) : null;
// Offsets résolus PAR NOM, sans repli littéral : un nom absent doit rendre « pas mesuré »
// (`configActives: null`), jamais la lecture d'un offset devenu celui d'un autre champ. Les
// littéraux du décompilé ne servent qu'au diagnostic `configLayout`, pour qu'un désaccord se voie.
const BC_UNITS_OFF = battleConfigurationClass
    ? getFieldOffset(battleConfigurationClass, "Units") : -1;
const UC_ID_OFF = unitConfigurationClass
    ? getFieldOffset(unitConfigurationClass, "Id") : -1;
const UC_VISUALID_OFF = unitConfigurationClass
    ? getFieldOffset(unitConfigurationClass, "VisualId") : -1;
const UC_ACTIVES_OFF = unitConfigurationClass
    ? getFieldOffset(unitConfigurationClass, "ActiveAbilities") : -1;
const BUC_ID_OFF = baseUnitComponentClass
    ? getFieldOffset(baseUnitComponentClass, "Id") : -1;

// --- #1039 — le canal `rarity`, résolu PAR NOM et LAZY --------------------------------
//
// LAZY, et pas au chargement comme `game/damage-prediction.ts` : la résolution lit les
// champs STATIQUES LITTÉRAUX de l'enum (`dumpEnumClass` → `il2cpp_field_static_get_value`),
// et une classe jamais initialisée n'a pas de disposition exploitable — c'est le piège que
// `damage-prediction.ts` documente sur `List\`1` (`boxedSize: 0`, tous les champs à
// `offset: 0`). Le premier appel de `combatSnapshot` arrive après le warmup, donc après
// l'init IL2CPP. Même idiome que `unitFlagTypes()` / `unitTraitTypes()` ci-dessous.
//
// La RÉSOLUTION vit dans `game/rarity.ts` — pas ici — parce qu'elle est paramétrée par un
// `RarityProbe` et donc EXÉCUTABLE hors Frida (`tools/probe-1039-rarity-canal.ts`). Poser
// le capteur sans ce levier l'aurait laissé invalidable jusqu'à la prochaine fenêtre de
// reinject.
let rarityResolutionCache: RarityResolution | null = null;
function rarityResolution(): RarityResolution {
    if (rarityResolutionCache) return rarityResolutionCache;
    let r: RarityResolution;
    try { r = resolveRarityChannel(RARITY_PROBE); }
    catch (e) {
        r = { channel: null, drift: [],
            errors: ["RESOLUTION DU CANAL RARETE EN ECHEC (#1039) : "
                + (e as Error).message] };
    }
    rarityResolutionCache = r;
    return r;
}

/** Le STRIDE d'un `T[]` managé, DÉRIVÉ du tableau lui-même (`class_get_element_class` +
 *  `class_is_valuetype` + `class_instance_size`) plutôt que supposé. `null` = indéterminable :
 *  l'appelant doit alors répondre « je ne sais pas lire », jamais rendre des nombres plausibles
 *  (cf. la docstring de `class_get_element_class`). */
function arrayElementInfo(items: NativePointer): {
    stride: number | null; elemClass: string | null;
} {
    if (!class_get_element_class || !class_is_valuetype || !class_instance_size) {
        return { stride: null, elemClass: null };
    }
    try {
        const ek = class_get_element_class(items.readPointer()) as NativePointer;
        if (ek.isNull()) return { stride: null, elemClass: null };
        let elemClass: string | null = null;
        try { elemClass = s(class_get_name(ek) as NativePointer); } catch { /* */ }
        const stride = (class_is_valuetype(ek) as number) !== 0
            ? (class_instance_size(ek) as number) - 0x10
            : Process.pointerSize;
        return { stride, elemClass };
    } catch { return { stride: null, elemClass: null }; }
}

/** `List<T>` d'IL2CPP : `_items` (T[]) @0x10, `_size` @0x18, éléments dès `items+0x20`.
 *  Rend les pointeurs bruts des éléments RÉFÉRENCE, ou `null` (= pas lisible). */
function readRefList(list: NativePointer, cap: number): NativePointer[] | null {
    if (list.isNull()) return null;
    try {
        const items = list.add(0x10).readPointer();
        const size = list.add(0x18).readS32();
        if (items.isNull() || size < 0 || size > cap) return null;
        const out: NativePointer[] = [];
        for (let i = 0; i < size; i++) {
            out.push(items.add(0x20 + i * Process.pointerSize).readPointer());
        }
        return out;
    } catch { return null; }
}

/** Le `List<ActiveAbilityType>` d'une `UnitConfiguration`, en TRI-ÉTAT : `values === null`
 *  signifie **PAS MESURÉ** (liste nulle, taille aberrante, ou stride non dérivable / ≠ 4) —
 *  distinct d'un `[]`, qui est la mesure « cette configuration ne porte aucun actif », et qui
 *  est justement le cas MAJORITAIRE du seed (50 des 175 entrées). Confondre les deux ferait
 *  répondre « le repli générique s'applique » à une unité dont on n'a rien lu. */
function readEnumIntList(list: NativePointer): {
    values: number[] | null; stride: number | null; elemClass: string | null;
} {
    if (list.isNull()) return { values: null, stride: null, elemClass: null };
    try {
        const items = list.add(0x10).readPointer();
        const size = list.add(0x18).readS32();
        if (items.isNull() || size < 0 || size > 256) {
            return { values: null, stride: null, elemClass: null };
        }
        const { stride, elemClass } = arrayElementInfo(items);
        if (stride !== 4) return { values: null, stride, elemClass };
        const values: number[] = [];
        for (let i = 0; i < size; i++) values.push(items.add(0x20 + i * 4).readS32());
        return { values, stride, elemClass };
    } catch { return { values: null, stride: null, elemClass: null }; }
}

/** Index `UnitConfiguration.Id` → actives de CONFIGURATION, lu sur la `BattleConfiguration` que
 *  le runner conserve (`IdunRunner.<Configuration>k__BackingField`, la même que consomment
 *  `simGetBattleConfig` / `buildMirrorFromSource`).
 *
 *  Rend AUSSI le layout observé : un canal qui ne dit pas ce qu'il a résolu laisse un `null` de
 *  panne indiscernable d'un `null` de mesure. */
function readConfigActives(runner: NativePointer): {
    byId: Record<string, number[]>; layout: Record<string, unknown>;
} {
    const byId: Record<string, number[]> = {};
    const layout: Record<string, unknown> = {
        battleConfigurationClassResolved: !!battleConfigurationClass,
        unitConfigurationClassResolved: !!unitConfigurationClass,
        baseUnitComponentClassResolved: !!baseUnitComponentClass,
        getBaseUnitComponentResolved: !!getBaseUnitComponentMi,
        unitsOff: BC_UNITS_OFF, idOff: UC_ID_OFF, visualIdOff: UC_VISUALID_OFF,
        activeAbilitiesOff: UC_ACTIVES_OFF, baseUnitComponentIdOff: BUC_ID_OFF,
        // Littéraux LUS (décompilé `GetCustomNormalAttackTypeFromActive` / `InitBaseComponent`,
        // disposition `rnca9r7q6c`) — diagnostic seul, jamais utilisés pour lire.
        decompiledActiveAbilitiesOff: 0xa0, decompiledUnitConfigurationIdOff: 0x10,
        bcResolved: false, bcUnits: null as number | null,
        bcUnitsWithActives: null as number | null,
        configIdCollisions: [] as string[],
        elemClass: null as string | null, elemStride: null as number | null,
        unreadableActiveLists: 0,
    };
    if (BC_UNITS_OFF < 0 || UC_ID_OFF < 0 || UC_ACTIVES_OFF < 0) return { byId, layout };
    let bc: NativePointer;
    try { bc = runner.add(runnerOff.config).readPointer(); } catch { return { byId, layout }; }
    if (bc.isNull()) return { byId, layout };
    let unitList: NativePointer;
    try { unitList = bc.add(BC_UNITS_OFF).readPointer(); } catch { return { byId, layout }; }
    const configs = readRefList(unitList, 4096);
    if (configs === null) return { byId, layout };
    layout.bcResolved = true;
    layout.bcUnits = configs.length;
    let withActives = 0;
    let unreadable = 0;
    for (const cfg of configs) {
        if (cfg.isNull()) continue;
        let id: string | null = null;
        try { id = readIl2cppString(cfg.add(UC_ID_OFF).readPointer()); } catch { /* */ }
        if (!id) continue;
        let actives: NativePointer;
        try { actives = cfg.add(UC_ACTIVES_OFF).readPointer(); } catch { continue; }
        const got = readEnumIntList(actives);
        if (got.elemClass !== null) layout.elemClass = got.elemClass;
        if (got.stride !== null) layout.elemStride = got.stride;
        if (got.values === null) { unreadable++; continue; }
        if (Object.prototype.hasOwnProperty.call(byId, id)) {
            (layout.configIdCollisions as string[]).push(id);
        }
        byId[id] = got.values;
        if (got.values.length > 0) withActives++;
    }
    layout.bcUnitsWithActives = withActives;
    layout.unreadableActiveLists = unreadable;
    return { byId, layout };
}

/** `BaseUnitComponent.Id` d'une entité — la CLÉ de jointure vers `UnitConfiguration.Id`,
 *  obtenue par la fonction nommée qu'appelle la fabrique elle-même. `null` = pas mesuré. */
function readEntityConfigId(entity: NativePointer): string | null {
    if (!getBaseUnitComponentMi || BUC_ID_OFF < 0) return null;
    try {
        const comp = invokeMethod(getBaseUnitComponentMi.info, null, [entity]);
        if (comp.isNull()) return null;
        return readIl2cppString(comp.add(BUC_ID_OFF).readPointer());
    } catch { return null; }
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function registerViewSnapshot(ctx: Ctx): void {
    /** SNAPSHOT one-shot des STATS DE COMBAT RÉSOLUES par unité (prédiction 100% offline,
     *  doc §16). Lit `UnitExtensions.GetStat(entity, StatType)` pour chaque stat combat-
     *  pertinente. C'est le SEUL accès live du prédicteur offline (à appeler une fois au
     *  chargement de la BattleConfig) ; faction/class/profil viennent de gameconfig, effets de
     *  decisionView. Les TRAITS, eux, sont publiés ICI (`units[].traits`, #233) : le gameconfig ne
     *  donne que les traits de DÉPART, et un trait accordé en bataille lui échappe.
     *  La RARETÉ suit (`units[].rarity`, #1039) : même forme de trou, mais sur `idun.meta.Rarity`
     *  — le gameconfig ne porte que `BaseRarity`, qui répond à une AUTRE question.
     *  Read-only. body: { runnerId } */
    ctx.rpc.combatSnapshot = (
        body?: { runnerId?: number; debugOnly?: string[] },
    ): Promise<unknown> => queueOnMainThread(() => {
        // DIAGNOSTIC #175 — `debugOnly` restreint le snapshot aux sous-lectures NOMMÉES, pour
        // isoler laquelle empoisonne un runner contenant une Machine (toute pose d'effet
        // ultérieure y devient un no-op silencieux). Absent => comportement NORMAL, inchangé :
        // c'est un levier de mesure, pas un mode de fonctionnement.
        // On ne référence QUE les sous-lectures qui INVOQUENT du natif — `readShields` est une
        // lecture mémoire pure (aucun `invokeMethod`), elle ne peut rien muter, donc pas de bouton.
        const only: string[] | null = Array.isArray(body?.debugOnly) ? body!.debugOnly! : null;
        const wants = (part: string): boolean => only === null || only.indexOf(part) >= 0;
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);   // attribution des traces (cf. game/trace-origin.ts)
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getStatMi) return { ok: false, error: "UnitExtensions.GetStat(4) non résolu" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };

        const STAT_IDS = COMBAT_STAT_IDS;
        const idBufs: Record<string, NativePointer> = {};
        for (const k of Object.keys(STAT_IDS)) {
            const buf = Memory.alloc(4); buf.writeS32(STAT_IDS[k]); idBufs[k] = buf;
        }
        // #477-r15-r7 : les ids lus UNIQUEMENT en `StatPart.Maximum` reçoivent leur buffer ici,
        // et NULLE PART ailleurs — ni dans la boucle `stats`, ni dans `statTypes` (cf. le
        // commentaire de `STAT_IDS_MAX_SEUL` : `seed_unit_stats` itère la table publiée).
        for (const k of Object.keys(STAT_IDS_MAX_SEUL)) {
            const buf = Memory.alloc(4); buf.writeS32(STAT_IDS_MAX_SEUL[k]); idBufs[k] = buf;
        }
        const partBuf = Memory.alloc(4); partBuf.writeS32(0);        // StatPart.Current
        const partBufInit = Memory.alloc(4); partBufInit.writeS32(3); // StatPart.Initial (=base)
        const partBufMax = Memory.alloc(4); partBufMax.writeS32(2);  // StatPart 2 = MAX agrégé (#45b')
        // Nullable<BEntityId> = null (HasValue=false) : struct zéroé (taille large par sûreté).
        const nullId = Memory.alloc(16); for (let i = 0; i < 16; i += 4) nullId.add(i).writeS32(0);
        const getStatP = (e: NativePointer, k: string, pb: NativePointer): number | null => {
            try {
                const r = invokeMethod(getStatMi!.info, null, [e, idBufs[k], pb, nullId]);
                return r.isNull() ? null : r.add(0x10).readS32();
            } catch { return null; }
        };
        const getStat = (e: NativePointer, k: string): number | null => getStatP(e, k, partBuf);

        // DÉGÂT D'ARME de l'attaque normale (one-shot) : le dégât/hits ne sont PAS des StatType
        // unité (la stat Attack agrégée ≠ dégât d'arme résolu). On capture la PRÉDICTION native
        // de l'attaque normale par paire via `CachedDamagePredictionQuery.GetNormalAttackPrediction
        // (attacker, target, attackerPosition)` (slot 13) — contrairement à `GetAllPredictions`,
        // CE chemin ne filtre PAS par portée (cible explicite) → capturable à froid au déploiement.
        // Le dégât de BASE est indépendant de la cible (cf. mesures) sauf effets de réduction sur la
        // cible → on prend le MAX sur plusieurs cibles ennemies = base NON réduite.
        //   UnitPosition (dump.cs @385083) = struct 8o {IList Tiles} ; obtenue via
        //   UnitExtensions.GetUnitPosition(unit, state). Le `DamagePredictionResult` rendu est
        //   décodé par `game/damage-prediction.ts` (offsets re-dérivés #276) — pas d'offset ici.
        const dpq = resolveDpq(runner);
        const getNormPredMi = dpq.isNull() ? null
            : findMethodByParamCount(dpq.readPointer(), "GetNormalAttackPrediction", 3);
        const getUnitPosMi = entityExtClass
            ? findMethodByParamCount(entityExtClass, "GetUnitPosition", 2) : null;
        // Toutes les entités COMBATTANTES vivantes (cibles de référence pour la
        // prédiction ET lignes du snapshot). Machine INCLUSE (#93) : les MoW
        // portent des stats et se font attaquer comme les squads, mais elles
        // étaient absentes du snapshot — leur prédiction offline n'avait donc
        // aucune stat résolue à confronter.
        const allUnits: Array<{ e: NativePointer; id: number; entityType: number }> = [];
        // #429-r1-r3-r1 : les entités NON vivantes, gardées à part. Le filtre `isAliveMi` ci-dessous
        // rend le canal `unitFlags` STRUCTURELLEMENT aveugle à `UnitFlag.Fled` (9) — mesuré le
        // 2026-08-05 : une unité qui a FUI (trait `BattleFatigue` →
        // `IdunBattle.Operations.FleeOperation$$Execute`, seul écrivain du flag) garde ses PV
        // PLEINS (hp 1000/1000) mais `IdunBattle.Entities.UnitExtensions$$IsAlive` rend FAUX pour
        // elle (le prédicat teste aussi le flag 6 `Dead` ET l'appartenance à la collection). Elle
        // disparaît donc du snapshot, et le port la reconstruit en unité VIVANTE INTACTE : son
        // mirror d'`IdunBattle.Entities.UnitExtensions$$IsAliveAndNotFled` ne peut pas mordre, et
        // le port frappait (10375 dégâts) une cible que le natif refuse au rang du MESSAGE.
        // Bloc SÉPARÉ et MINIMAL (id + type + flags) : la projection lourde reste alive-only, donc
        // aucun consommateur existant ne change de forme.
        const notAlive: Array<{ e: NativePointer; id: number; entityType: number }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit && ty !== EntityType.Machine) return;
            if (!invokeBool(isAliveMi, [e, statePtr])) { notAlive.push({ e, id, entityType: ty }); return; }
            allUnits.push({ e, id, entityType: ty });
        });
        // DÉGÂT DE BASE de l'attaque normale (one-shot, iso-AI) via `GetNormalAttackPrediction
        // (attacker, target, pos)`. Ce chemin calcule pour les cibles ATTEIGNABLES (0 sinon) ; au
        // déploiement seuls les alliés sont adjacents → ils donnent la base (le dégât de base EST
        // indépendant de la cible, cf. mesures, sauf armes Blast/multi-membres). On retient donc
        // la meilleure entrée NON NULLE = dégât de base d'arme. Les réductions par cible sont
        // appliquées offline (decisionView.effects) ; le détail par cible (Blast) = amélioration.
        const readNormalAttack = (attacker: NativePointer): Record<string, unknown> => {
            if (dpq.isNull()) return { error: "dpq null" };
            if (!getNormPredMi) return { error: "GetNormalAttackPrediction(3) non résolu sur "
                + s(class_get_name(dpq.readPointer()) as NativePointer) };
            if (!getUnitPosMi) return { error: "GetUnitPosition(2) non résolu" };
            let posPtr: NativePointer;
            try {
                const pos = invokeMethod(getUnitPosMi.info, null, [attacker, statePtr]);
                if (pos.isNull()) return { error: "GetUnitPosition null" };
                posPtr = pos.add(0x10);                              // struct UnitPosition (8o)
            } catch (err) { return { error: "GetUnitPosition: " + (err as Error).message }; }
            let best: Record<string, unknown> | null = null;
            let reachable = 0;
            for (const t of allUnits) {
                if (t.e.equals(attacker)) continue;
                // #175 — NE JAMAIS prédire contre une MACHINE. Un seul appel
                // `GetNormalAttackPrediction(attaquant, cible = Machine, pos)` suffit à rendre
                // TOUTE pose d'effet ultérieure sur CE runner un no-op SILENCIEUX (l'action est
                // consommée, `applyAction` rend ok=true, le dégât passe, mais `AddEffect` n'écrit
                // plus rien). La sortie muette est le gate d'immunité de
                // `IdunBattle.Operations.AddEffectOperation$$Execute` — l'appel d'interface slot
                // +0x28 sur la définition d'effet : c'est sa SEULE sortie qui ne logue pas, les
                // deux autres (cible nulle, `UnitExtensions$$HasFlag(cible, 6)`) tracent.
                //
                // BISSECTÉ live (`probe_175_combatsnapshot_machine.py`), pas supposé — et ça a
                // RÉFUTÉ le correctif que la fiche #175 proposait. Mesures :
                //   readNormalAttack SEULE                  -> NO-OP  (suffit à empoisonner)
                //   les 5 autres sous-lectures, chacune     -> POSE
                //   GetUnitPosition seul, sans prédiction   -> POSE
                //   MoW exclue comme ATTAQUANTE (le fix proposé) -> NO-OP  <- INERTE
                //   MoW exclue comme CIBLE (ci-dessous)     -> POSE
                // Le vecteur est donc la Machine en CIBLE, pas en attaquant : gater sur
                // l'attaquant aurait livré un correctif qui ne corrige rien, sans rien signaler.
                //
                // Ce qu'on perd : rien. Le dégât de base d'arme est indépendant de la cible (cf.
                // le commentaire de tête), et l'attaquant garde toutes les cibles UNIT. Ce qu'on
                // ne sait pas encore : POURQUOI le natif se comporte ainsi (le prédicteur cache
                // délègue, cf. `CachedDamagePredictionQuery$$GetNormalAttackPrediction`) — c'est
                // un CONTOURNEMENT mesuré, pas une réparation du natif.
                if (t.entityType === EntityType.Machine) continue;
                let boxed: NativePointer;
                try { boxed = invokeMethod(getNormPredMi.info, dpq, [attacker, t.e, posPtr]); }
                catch { continue; }
                if (boxed.isNull()) continue;
                // Struct BOXÉ : champs à `boxed+0x10`. Décodage centralisé (#276).
                const p = readDamagePredictionResult(boxed.add(0x10));
                const hMax = p.healthDmgMax;
                if (hMax <= 0) continue;                             // cible non atteignable → 0
                reachable++;
                if (best === null || hMax > (best.maxDmg as number)) {
                    best = {
                        minDmg: p.healthDmgMin, maxDmg: hMax,
                        hits: p.appliedHits, mightCrit: p.mightCrit,
                        vsTarget: t.id,
                        ...(p.shapeErrors ? { shapeErrors: p.shapeErrors } : {}),
                    };
                }
            }
            if (best) { best.reachable = reachable; return best; }
            return { error: "aucune cible atteignable au déploiement (base non capturable)" };
        };

        // --- multiplier d'ability-variable PAR ENTITÉ (UnitConfiguration via BattleQuery.GetUnitConfig) ---
        // `AbilityVariablesMultiplierPercentage` (UnitConfiguration@0x74, dérivé progression) scale les
        // variables d'ability « rareté » (ex. PowerTrip.armorIgnored §17.21). PAS porté sur l'entité ; on
        // remonte via le registre `BattleQuery.GetUnitConfig(unitId)` (EntityServices.<Battle>@battleInServices).
        // Clé = la VisualId (string managée) de l'unité (UnitComponent.VisualId@0x20 ; Id==VisualId). Offsets
        // UnitConfiguration (dump gqfc5mff6c) : mult@0x74, tertiaryMult@0x78, Level@0x7C, ActiveAbilityLevel
        // @0xB8, PassiveAbilityLevel@0xBC (struct Level = int). Per-entité (≠ BC offline par visualId).
        const battleQ = (servicesOff >= 0 && battleInServicesOff >= 0)
            ? (() => {
                const sv = runner.add(servicesOff).readPointer();
                return sv.isNull() ? ptr(0) : sv.add(battleInServicesOff).readPointer();
            })() : ptr(0);
        const getUnitConfigMi = (!battleQ.isNull())
            ? findMethodByParamCount(battleQ.readPointer(), "GetUnitConfig", 1) : null;
        const unitCompClass = findClassAnywhere("IdunBattle.Entities.Components", "UnitComponent");
        const VISUALID_OFF = 0x20;     // (Base)UnitComponent.VisualId (System.String)
        const UCFG = { mult: 0x74, tertMult: 0x78, level: 0x7c, activeLvl: 0xb8, passiveLvl: 0xbc };
        const readUnitConfig = (e: NativePointer): Record<string, unknown> => {
            if (!getUnitConfigMi) return { error: "GetUnitConfig(1) non résolu" };
            if (!unitCompClass) return { error: "UnitComponent non résolu" };
            let vidPtr: NativePointer | null = null;
            forEachComponent(e, (comp, klass) => {
                if (vidPtr === null && klass.equals(unitCompClass)) {
                    const p = comp.add(VISUALID_OFF).readPointer();
                    if (!p.isNull()) vidPtr = p;
                }
            });
            if (!vidPtr) return { error: "visualId introuvable" };
            let cfg: NativePointer;
            try { cfg = invokeMethod(getUnitConfigMi.info, battleQ, [vidPtr]); }
            catch (err) { return { error: "GetUnitConfig: " + (err as Error).message }; }
            if (cfg.isNull()) return { error: "config null" };
            // #1039 — la rareté de CONFIGURATION, TÉMOIN de la source que la fabrique copie
            // (`UnitFactory$$InitBaseComponent` : `component+0x74 = config+0x80`). Ce n'est
            // PAS le canal qui fait foi : `units[].rarity` ci-dessous lit le COMPOSANT, ce
            // que les trois gates lisent. Publier les deux rend visible le seul régime où
            // ils peuvent diverger — la jointure `GetUnitConfig(visualId)` est N→1, donc
            // deux entités de même `VisualId` (la même unité dans les deux camps) partagent
            // la configuration rendue ici alors qu'elles ont chacune LEUR composant.
            // ⚠ L'offset est résolu par NOM sur `UnitConfiguration` : `UCFG.mult` juste
            // au-dessus est `UnitConfiguration+0x74`, exactement l'offset qu'occupe la
            // RARETÉ dans `BaseUnitComponent`. Recopier « 0x74 » d'un struct à l'autre
            // rendrait `100`/`180` là où on attend `0..5`, sans lever.
            const rch = rarityResolution().channel;
            return {
                visualId: readIl2cppString(vidPtr),
                abilityVariablesMultiplier: cfg.add(UCFG.mult).readS32(),
                tertiaryAbilityVariablesMultiplier: cfg.add(UCFG.tertMult).readS32(),
                level: cfg.add(UCFG.level).readS32(),
                activeAbilityLevel: cfg.add(UCFG.activeLvl).readS32(),
                passiveAbilityLevel: cfg.add(UCFG.passiveLvl).readS32(),
                rarity: (rch !== null && rch.configOffset >= 0)
                    ? cfg.add(rch.configOffset).readS32() : null,
            };
        };

        // RARETÉ EN BATAILLE (#1039) — `BaseUnitComponent.Rarity`, le champ que lisent les
        // TROIS gates (`UnitExtensions$$HasRarity`, `UnitsWithRaritySelector$$Select`,
        // `HasRarityTrigger$$ShouldTrigger`), et le seul.
        //
        // POURQUOI PAR `GetBaseUnitComponent` ET PAS PAR `forEachComponent`. Le filtre par
        // classe employé plus haut (`klass.equals(unitCompClass)`) ne voit que
        // `IdunBattle.Entities.Components.UnitComponent` : une MACHINE OF WAR porte un
        // `MachineComponent`, et `readUnitConfig` lui rend donc `{error: "visualId
        // introuvable"}`. Un capteur bâti sur cette voie serait AVEUGLE AUX MoW — c'est-à-dire
        // aveugle aux porteurs mêmes des abilities mythiques qui motivent ce canal.
        // `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent` sert les deux familles
        // (`MachineComponent` DÉRIVE de `BaseUnitComponent`), et c'est littéralement la
        // fonction que les trois gates appellent — on invoque la fonction NOMMÉE du jeu
        // plutôt que de deviner quelle classe concrète chercher.
        //
        // TRI-ÉTAT : `null` = PAS MESURÉ (canal refusé, composant introuvable, invocation en
        // échec). Jamais `0` — `0` est `Rarity.Common`, une valeur parfaitement plausible,
        // donc un repli sur `0` rendrait la panne indiscernable d'une mesure.
        const readRarity = (e: NativePointer): number | null => {
            const ch = rarityResolution().channel;
            if (ch === null || !getBaseUnitComponentMi) return null;
            try {
                const comp = invokeMethod(getBaseUnitComponentMi.info, null, [e]);
                if (comp.isNull()) return null;
                return comp.add(ch.componentOffset).readS32();
            } catch { return null; }
        };

        // BOUCLIERS (ShieldComponent @180fa8770) : liste d'instances @+0x10 (List<ShieldInstance>,
        // _items@+0x10/_size@+0x18 ; éléments = pointeurs, data array @+0x20). ShieldInstance :
        // id@+0x10, amount@+0x30, remaining Nullable<int>@+0x3c (None=permanent). Layout du Nullable
        // incertain → on émet remainingRaw=[s32@0x3c, s32@0x40] pour trancher en validation, + une
        // estimation `remaining` (convention .NET {hasValue@0, value@4} : has=byte@0x3c, val=s32@0x40).
        const shieldCompClass = findClassAnywhere("IdunBattle.Entities.Components", "ShieldComponent");
        const SH = { id: 0x10, amount: 0x30, rem0: 0x3c, rem1: 0x40 };
        const readShields = (e: NativePointer): Array<Record<string, unknown>> => {
            if (!shieldCompClass) return [];
            let comp: NativePointer | null = null;
            forEachComponent(e, (c, klass) => {
                if (comp === null && klass.equals(shieldCompClass)) comp = c;
            });
            if (comp === null) return [];
            const list = (comp as NativePointer).add(0x10).readPointer();
            if (list.isNull()) return [];
            const items = list.add(0x10).readPointer();
            const size = list.add(0x18).readS32();
            if (items.isNull() || size <= 0 || size > 64) return [];
            const out: Array<Record<string, unknown>> = [];
            for (let i = 0; i < size; i++) {
                const inst = items.add(0x20 + i * 8).readPointer();
                if (inst.isNull()) continue;
                const w0 = inst.add(SH.rem0).readS32();
                const w1 = inst.add(SH.rem1).readS32();
                const has = inst.add(SH.rem0).readU8();   // convention .NET hasValue@+0
                out.push({
                    id: inst.add(SH.id).readS32(),
                    amount: inst.add(SH.amount).readS32(),
                    remaining: has ? w1 : null,
                    remainingRaw: [w0, w1],
                });
            }
            return out;
        };

        // ÉTAT DE TOUR PAR UNITÉ (#223) — deux champs de `UnitComponent` qu'AUCUN RPC n'exposait,
        // et dont l'absence forçait DEUX mécaniques à se valider par contournement :
        //
        //  * `currentTurnStartTile` @+0x18c (`int`, id de TUILE ; 0 = aucune). ÉCRIT par
        //    `IdunBattle.Operations.StartTurnOperation$$Execute`, juste après le bump de
        //    `turnsStarted@+0x58`, sur le MÊME composant :
        //    `mainTile = EntityExtensions.GetMainTile(unit) ; comp[0x18c] = mainTile?.Id ?? 0`.
        //    C'est la tuile où l'unité se trouvait au DÉBUT DE SON PROPRE TOUR — surtout PAS
        //    « the hex he moved from » comme l'annonce le texte i2, qui MENT : une unité qui bouge
        //    deux fois dans le tour garde la tuile du début. RELU par
        //    `IdunBattle.Entities.Selectors.CurrentTurnStartTileSelector$$Select`, qui rend une
        //    liste VIDE quand le champ vaut 0 -> on émet `null` (le port le représente par `None`).
        //    Sans lui, un `load_state` frais partait à `None` et le time-ghost de `thousTerminator`
        //    (`GhostRevive`/`TimeFlux_Revive`) ne se posait qu'après un `StartTurnOperation`.
        //
        //  * `chargedUnitIds` @+0x190 (`List<int>`). Second conjoint de
        //    `IdunBattle.Core.Services.BattleQuery$$IsCharging` =
        //    `AreEntitiesAdjacent(caster, target) && ChargedUnitIds.Contains(target.Id)`.
        //    Le décompilé lit `*(longlong *)(comp + 400)` — 400 décimal = 0x190 — puis
        //    `List<T>$$Contains` : c'est donc bien une LISTE, pas un `OrderedSet` (contrairement
        //    à `UnitFlagsComponent`, dont la disposition interne n'est PAS lisible et qu'on
        //    interroge par invocation). Sa disposition l'est : `_items`@+0x10, `_size`@+0x18,
        //    données du tableau @+0x20, éléments de 4 octets.
        //    Sans lui, `load_state` ne pouvait pas seeder l'état de charge : la face PRÉDICTION
        //    sur état rechargé restait restrictive, et `test_avalanche_of_muscle_live` avait dû
        //    être supprimé faute de pouvoir exprimer le prédicat (il déclarait la charge via le
        //    proxy `set_moved_flag`, que `964dd15` a cessé d'honorer).
        //
        // Lecture MÉMOIRE PURE (aucun `invokeMethod`) : comme `readShields`, elle ne peut rien
        // muter, donc pas de bouton `debugOnly`. Un seul parcours de composants pour les DEUX
        // champs. `null` = non mesuré (composant/classe introuvable), à distinguer de `0`/`[]`
        // = mesuré et vide.
        const UTS = { startTile: 0x18c, charged: 0x190 };
        const readUnitTurnState = (e: NativePointer): Record<string, unknown> => {
            if (!unitCompClass) return { currentTurnStartTile: null, chargedUnitIds: null };
            let comp: NativePointer | null = null;
            forEachComponent(e, (c, klass) => {
                if (comp === null && klass.equals(unitCompClass)) comp = c;
            });
            if (comp === null) return { currentTurnStartTile: null, chargedUnitIds: null };
            const c = comp as NativePointer;
            const startTile = c.add(UTS.startTile).readS32();
            const charged: number[] = [];
            const list = c.add(UTS.charged).readPointer();
            if (!list.isNull()) {
                const items = list.add(0x10).readPointer();
                const size = list.add(0x18).readS32();
                if (!items.isNull() && size > 0 && size <= 64) {
                    for (let i = 0; i < size; i++) charged.push(items.add(0x20 + i * 4).readS32());
                }
            }
            // 0 = « aucune tuile » côté natif (le sélecteur rend alors une liste vide) -> `null`,
            // pour que le port ne confonde pas avec la tuile d'id 0.
            return { currentTurnStartTile: startTile === 0 ? null : startTile,
                     chargedUnitIds: charged };
        };

        // FLAGS de l'unité (O5) : ids de `UnitFlag` actuellement POSÉS, par invocation de
        // `HasFlag(unit, flag)` sur chaque valeur d'enum. Valeurs DÉDUPLIQUÉES (un enum C# admet
        // des alias de même valeur ; deux noms ne font qu'un seul flag).
        //
        // `null` (et non `[]`) quand la mesure n'a PAS pu se faire — méthode irrésolue ou enum vide.
        // La distinction est le tout du canal : `[]` dit « lu, aucun flag posé », `null` dit « pas
        // lu ». Les rabattre l'un sur l'autre ferait passer un capteur MORT pour une unité sans
        // flags, et le consommateur offline retomberait silencieusement sur un défaut au lieu de
        // garder sa dérivation de repli (même discipline que `invokeInt`, cf. `internals.ts`).
        const flagTypes = wants("unitFlags") ? unitFlagTypes() : {};
        const flagValues = Array.from(new Set(Object.keys(flagTypes).map((k) => flagTypes[k])))
            .sort((a, b) => a - b);
        const flagBuf = Memory.alloc(4);
        const readUnitFlags = (e: NativePointer): number[] | null => {
            if (!hasFlagMi || flagValues.length === 0) return null;
            const out: number[] = [];
            for (const v of flagValues) {
                flagBuf.writeS32(v);
                if (invokeBool(hasFlagMi, [e, flagBuf])) out.push(v);
            }
            return out;
        };

        // TRAITS EFFECTIFS (#233) : ids `UnitTrait` que le natif considère POSÉS, veto `+0x50`
        // compris. Même forme que `readUnitFlags` — valeurs DÉDUPLIQUÉES (un enum C# admet des
        // alias), et `null` (jamais `[]`) quand la mesure n'a pas pu se faire : `[]` dit « lu,
        // aucun trait », `null` dit « pas lu ». Les confondre ferait passer un capteur MORT pour
        // une unité sans trait, et le consommateur offline retomberait en silence sur sa
        // dérivation de repli au lieu de savoir qu'il n'a rien mesuré.
        const traitTypes = wants("traits") ? unitTraitTypes() : {};
        const traitValues = Array.from(new Set(Object.keys(traitTypes).map((k) => traitTypes[k])))
            .sort((a, b) => a - b);
        const traitBuf = Memory.alloc(4);
        const readUnitTraits = (e: NativePointer): number[] | null => {
            if (!hasTraitMi || traitValues.length === 0) return null;
            const out: number[] = [];
            for (const v of traitValues) {
                traitBuf.writeS32(v);
                if (invokeBool(hasTraitMi, [e, traitBuf])) out.push(v);
            }
            return out;
        };

        const units: Array<Record<string, unknown>> = [];
        for (const { e, id, entityType } of allUnits) {
            const stats: Record<string, number | null> = {};
            // AXE STAT-MODIFICATION (§7bis prediction.md) : delta Current-Initial par StatType.
            // `CalculateModifiersFromStatModifications` @181004380 ne s'active QUE si CurrentValue !=
            // BaseValue → un delta non-nul = présence de modifications de stat (source des modifiers de
            // dégât par-cible non exposés comme effets nommés, ex. le +50% sur worldTerminator). Emis
            // pour NOMMER le modifier par capture (INPUT), pas pour deviner.
            const statDelta: Record<string, number> = {};
            if (wants("stats")) {
                for (const k of Object.keys(STAT_IDS)) {
                    stats[k] = getStat(e, k);
                    const init = getStatP(e, k, partBufInit);
                    if (init !== null && stats[k] !== null && stats[k] !== init) {
                        statDelta[k] = (stats[k] as number) - init;
                    }
                }
            }
            // #45b' : MaxHealth EFFECTIF (StatPart=2 = agrégat base+modifications, clamp cape
            // inclus) — la lecture EXACTE de `DamageUtility.<EvaluateAttackInSteps>d__2
            // @1810e2280` : `GetStat(target, Health=5, 2, null)` pour combinedMax. Le champ
            // struct MaximumValue@0x14 (observeBattle.hpMax) est la BASE : il rate les bumps
            // mid-bataille (TwistedScience +2992 sur u87, 777 s15 — utilité native 2.8836
            // reconstruite exacte avec 14036). DYNAMIQUE -> refresh par pas côté Python.
            const healthMax = wants("stats") ? getStatP(e, "health", partBufMax) : null;
            // #477-r15-r5 — le MAXIMUM des membres, la grandeur que `stats.numberOfMembers` ne
            // discrimine PAS. Les deux tags du flux de replay lisent le MÊME composant par deux
            // accesseurs DIFFÉRENTS de `IdunBattle.Entities.Components.FillUpStatComponent` :
            //
            //   Tag=UnitStats_InitAliveMembers (4)  <- champ BRUT `RemainingValue(+0x18)`
            //   Tag=UnitStats_MaxMembers      (17)  <- `FillUpStatComponent$$get_CurrentMaximumValue()`
            //
            // et `FillUpStatComponent$$GetStatPart` rend EXACTEMENT l'un ou l'autre selon le
            // `StatPart` : `case 0` (Current) -> `*(int*)(this+0x18)`, `case 2` (Maximum) ->
            // `get_CurrentMaximumValue()`. Publier le second est donc le mirror 1:1 du second tag,
            // au même titre que `healthMax` l'est pour `UnitStats_MaxHealth`.
            //
            // ⚠ AU DÉPLOIEMENT LES DEUX COÏNCIDENT (aucun membre mort, aucune modification), et
            // c'est précisément pourquoi le canal manquant ne se voyait pas : un accord dans ce
            // régime ne prouve rien. Ils divergent dès qu'un membre meurt (`RemainingValue` baisse,
            // le maximum non) ou qu'une modification de stat porte sur `+0x28`.
            const numberOfMembersMax = wants("stats")
                ? getStatP(e, "numberOfMembers", partBufMax) : null;
            // #477-r15-r7 — le MAXIMUM d'ARMURE, dernière grandeur du groupe `System_GameSetup`
            // que l'émetteur de flux COPIAIT de l'oracle. Exactement la même paire de lectures que
            // les membres ci-dessus, sur le troisième `FillUpStatComponent` :
            //
            //   Tag=UnitStats_InitRemainingArmor (3)  <- champ BRUT `RemainingValue(+0x18)`
            //   Tag=UnitStats_MaxArmor          (13)  <- `FillUpStatComponent$$get_CurrentMaximumValue()`
            //
            // Le port lisait `observeBattle.armorMax`, qui est le champ BRUT `MaximumValue(+0x14)`
            // (`game/match-state.ts::projectSquadStats`) — une TROISIÈME lecture, ni l'une ni
            // l'autre des deux ci-dessus. Elle coïncide avec le tag au déploiement PAR
            // CONSTRUCTION, parce que `get_CurrentMaximumValue()` vaut
            // `MaximumValue(+0x14) + clamp(Modification(+0x28), -Initial(+0x10), IntMax - Initial)`
            // (ou l'override de `ValueOverride$$GetOverrideValueWithModification(+0x38)`), et que
            // ces deux termes sont nuls tant qu'aucune opération n'est intercalée. Un accord dans
            // ce régime ne prouve donc rien — c'est ce que `probe_477r15r7_max_discrimine.py`
            // mesure séparément.
            const armorMax = wants("stats") ? getStatP(e, "armor", partBufMax) : null;
            // AbilityState PER-ABILITY (#100) : {level, multiplier} de chaque entrée ActiveAbility
            // (_abilityState @0x4c, Override @0x58 prime — cf. internals.readAbilityState). C'est le
            // couple que le natif passe au playbook (5e arg MakeDamagePredictions) et qui indexe les
            // variables config (TryGetVariableArrayForLevel @181577510) — le global unitConfig
            // (activeAbilityLevel×abilityVariablesMultiplier) est un AUTRE canal (u80 : 65×120 vs 50×180).
            const abilityStates = wants("abilityStates")
                ? unitAbilityTypes(e, true)
                    .filter((a) => a.level !== undefined)
                    .map((a) => ({ id: a.id, name: a.name, kind: a.kind,
                        level: a.level, multiplier: a.multiplier }))
                : [];
            units.push({
                entityId: id, entityType,
                ctrl: wants("ctrl") ? invokeBool(isCtrlByCurMi, [e, statePtr]) : null,
                // #N11 : compteur PER-UNITÉ de tours termines (`UnitExtensions.GetTurnsFinished`),
                // lu par le gate `OwnerHasFinishedMinTurns`. `null` = non mesuré (methode
                // irresolue), a distinguer de `0` = a fini zero tour.
                turnsFinished: wants("turnsFinished")
                    ? invokeInt(getTurnsFinishedMi, [e]) : null,
                // ⚠ `armorMax` ICI est `StatPart.Maximum` (l'accesseur). `observeBattle` publie un
                // champ du MÊME NOM qui est le champ BRUT `MaximumValue(+0x14)` : ce sont DEUX RPC
                // et DEUX lectures distinctes, et c'est justement leur écart qui est mesuré.
                stats, statDelta, healthMax, numberOfMembersMax, armorMax,
                // O5 : `UnitFlagsComponent` de l'unité, projeté en ids `UnitFlag` posés. Sans lui,
                // la face DÉCISION offline n'avait AUCUN accès live aux flags (`PreventOverkill`
                // =19, `Moved` =0, `Untargetable` =17, `DisableTriggers` =18…) et devait les
                // DÉRIVER de leurs effets poseurs. `null` = non mesuré, `[]` = mesuré sans flag.
                unitFlags: wants("unitFlags") ? readUnitFlags(e) : null,
                // #233 : traits REELLEMENT portes en bataille (gameconfig + AddTrait + veto de
                // retrait), la ou le port ne savait que les RECONSTRUIRE depuis le substrat.
                // C'est ce que lisent les 33 gates de traits recenses.
                traits: wants("traits") ? readUnitTraits(e) : null,
                // #1039 : la RARETÉ EN BATAILLE (`idun.meta.Rarity`), ordinal de
                // `BaseUnitComponent.Rarity`. `null` = PAS MESURÉ (cf. `readRarity`).
                // Le port n'avait AUCUN canal : ni `observeBattle`, ni `combatSnapshot`, ni
                // `decisionView` ne la publiaient, et le gameconfig répond à une AUTRE
                // question (`BaseRarity` est la rareté de BASE, pas l'effective). Sans elle,
                // tout gate `HasRarity` / `UnitsWithRarity` était inévaluable — et le rabattre
                // sur « toujours vrai » aurait été une dégradation PERMISSIVE silencieuse,
                // d'autant plus invisible que `rl_duel build` impose `targetRarity = 5` à
                // toute unité normalisée : dans ce régime DÉGÉNÉRÉ, un port sans gate est
                // d'accord avec le natif partout.
                rarity: wants("rarity") ? readRarity(e) : null,
                normalAttack: wants("normalAttack") ? readNormalAttack(e) : null,
                unitConfig: wants("unitConfig") ? readUnitConfig(e) : null,
                shields: readShields(e), abilityStates,
                // #378 : `ChildComponent.ParentId` — le lien enfant -> SUMMONER, TRI-ÉTAT
                // (`parentId` + `parentMeasured`). MÊME lecteur que `decisionView.units[]`
                // (`readParentLink`, source unique) : les deux canaux ne peuvent pas diverger.
                //
                // POURQUOI ICI, alors que `decisionView` le publie déjà. Ce sont deux régimes,
                // pas deux copies. `combatSnapshot` est (a) le canal de SEED de `load_state`
                // (l'ECS reconstruit d'une capture live n'a AUCUN autre moyen de connaître le
                // parent d'un summon apparu avant la capture — la simulation ne l'a pas spawné)
                // et (b) le canal RE-LU PAR PAS (`playbook/scene.py::refresh_shields`), donc le
                // seul qui suive un summon apparu MID-BATAILLE. `decisionView`, lui, n'est
                // interrogé que LAZY. Sans cette ligne, `parent_by_id` restait vide sur les deux
                // faces et la chance du jumeau drone `1307 DefenderOfTheGreaterGood_ExtraHitsDrone`
                // se lisait sur SES tours au lieu de ceux de son summoner (résidu de #372).
                //
                // Lecture MÉMOIRE PURE (aucun `invokeMethod`) : comme `readShields` et
                // `readUnitTurnState`, elle ne peut rien muter -> pas de bouton `debugOnly`.
                ...readParentLink(e),
                // #223 : `currentTurnStartTile` + `chargedUnitIds` (cf. le bloc `readUnitTurnState`).
                ...readUnitTurnState(e),
            });
        }
        // #429-r1-r3-r1 : le bloc NON VIVANT, réduit à ce que le filtre alive-only rendait
        // inatteignable — `entityId` + `unitFlags`. AUCUNE stat, aucune prédiction : ces
        // sous-lectures supposent une unité en jeu. TRI-ÉTAT conservé (`null` = pas mesuré).
        // `[]` ici veut dire « lu, aucune entité non vivante », jamais « pas lu ».
        //
        // #1039 : `rarity` y figure AUSSI. Une unité qui a FUI garde sa rareté — elle est
        // portée par `BaseUnitComponent`, pas par l'état de vie — et `load_state` reconstruit
        // ces entités-là depuis ce bloc. L'omettre ici aurait fait des unités non vivantes
        // les seules sans rareté mesurée, une asymétrie que rien dans le natif ne justifie.
        const unitsNotAlive = wants("unitFlags")
            ? notAlive.map((u) => ({ entityId: u.id, entityType: u.entityType,
                unitFlags: readUnitFlags(u.e),
                rarity: wants("rarity") ? readRarity(u.e) : null }))
            : null;
        // `unitFlagTypes` = {nom: id} de l'enum, au MÊME titre que `statTypes` : le consommateur
        // nomme les ids qu'il lit sans recopier de table chez lui.
        //
        // #1039 — `rarityTypes` suit la MÊME discipline, mais avec un cran de plus qui lui est
        // propre : la table n'est pas cherchée par son nom, elle est DÉRIVÉE DU CHAMP LUI-MÊME
        // (classe du type de `BaseUnitComponent.Rarity`). CINQ enums du build portent
        // exactement les six mêmes membres aux mêmes ordinaux (`idun.meta.Rarity`,
        // `IdunMetaLogic.UserProgress.Model.{Unit,Item,Upgrade,XpBook}Rarity`) : un mauvais
        // appariement serait SILENCIEUX EN ORDINAL. `rarityEnum` publie le nom PLEIN pour que
        // le consommateur puisse l'ASSERTIONNER, et `rarityLayout` dit ce qui a été résolu —
        // sans lui, un `rarity: null` de PANNE serait indiscernable d'un `null` de mesure.
        const rr = wants("rarity") ? rarityResolution() : null;
        return { ok: true, runner: label, statTypes: STAT_IDS,
            unitFlagTypes: wants("unitFlags") ? flagTypes : null,
            rarityEnum: rr && rr.channel ? rr.channel.enumFullName : null,
            rarityTypes: rr && rr.channel ? rr.channel.members : null,
            rarityLayout: rr === null ? null : {
                componentOffset: rr.channel ? rr.channel.componentOffset : -1,
                configOffset: rr.channel ? rr.channel.configOffset : -1,
                errors: rr.errors, drift: rr.drift,
            },
            units, unitsNotAlive };
    });

    /** PER-SOURCE STAT-MODIFICATION breakdown — la sonde DÉFINITIVE pour SOURCER un
     *  `statDelta` opaque : « le +1298 Attack sur u92 vient de QUELLE entité ? »
     *  devient une LECTURE au lieu d'une triangulation (base↔tuile + recon allié +
     *  gameconfig). Chemin natif VÉRIFIÉ (décompilé) :
     *    `UnitExtensions.GetStat(entity, statType, StatPart=5, Nullable<BEntityId> src)`
     *    → `StatComponent.GetStatPart @180fa8bb0` case 5/9 :
     *        • src.HasValue=false → `*(int*)(comp+0x10)` = TOTAL Σ des modifications
     *        • src.HasValue=true  → `ValueModification.GetModificationFromEntity(
     *            comp+0x10, srcId) @180fadf10` → Dict<BEntityId,Modifier> keyé par
     *          l'ENTITÉ SOURCE du buff → contribution de CETTE source.
     *  On lit le total (part 5, src null) par stat ; si non-nul, on SCANNE toutes les
     *  entités comme sources candidates (BEntityId = `forEachEntity` id) et on garde
     *  les contributions non-nulles. `residual = total - Σ(sources)` : 0 = tout
     *  attribué à des entités (cas aura d'allié / self-buff) ; non-nul = une source
     *  non-entité (modif SETUP `ModifyUnit*` / système) → à investiguer, pas deviner.
     *  Ne matérialise QUE ce qui est présent dans la ValueModification À CET INSTANT
     *  (une aura d'adjacence n'y est que si l'unité est actuellement adjacente au
     *  porteur — cf. #49 : re-évaluée par candidat en prédiction). Read-only, one-shot.
     *  body: { runnerId?, unitId?, stats?: string[], minAbs?=1 } */
    ctx.rpc.statModSources = (
        body?: {
            runnerId?: number; unitId?: number; stats?: string[]; minAbs?: number;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        if (!getStatMi) return { ok: false, error: "UnitExtensions.GetStat(4) non résolu" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };

        const requested = (Array.isArray(body?.stats) && body!.stats!.length)
            ? body!.stats!.filter((k) => k in COMBAT_STAT_IDS)
            : Object.keys(COMBAT_STAT_IDS);
        const minAbs = typeof body?.minAbs === "number"
            ? Math.abs(body.minAbs) : 1;

        const idBufs: Record<string, NativePointer> = {};
        for (const k of requested) {
            const buf = Memory.alloc(4); buf.writeS32(COMBAT_STAT_IDS[k]); idBufs[k] = buf;
        }
        const partBuf5 = Memory.alloc(4); partBuf5.writeS32(5);   // StatPart = branche modification
        // Nullable<BEntityId> — layout Mono : hasValue byte @+0, value(int32 BEntityId) @+4.
        const nullSrc = Memory.alloc(16); for (let i = 0; i < 16; i += 4) nullSrc.add(i).writeS32(0);
        const srcBuf = Memory.alloc(16); for (let i = 0; i < 16; i += 4) srcBuf.add(i).writeS32(0);
        srcBuf.writeU8(1);   // HasValue = true (réécrit srcBuf+4 = value à chaque source)
        // GetStat(4-arg) rend un int BOXÉ → valeur signée @+0x10 (idem combatSnapshot).
        const getMod = (e: NativePointer, k: string, src: NativePointer): number => {
            try {
                const r = invokeMethod(getStatMi!.info, null, [e, idBufs[k], partBuf5, src]);
                return r.isNull() ? 0 : r.add(0x10).readS32();
            } catch { return 0; }
        };

        // Toutes les entités = sources candidates ; entités COMBATTANTES vivantes
        // (filtrées par unitId) = cibles. Machine INCLUSE (#93) : une MoW porte
        // des ValueModification comme une squad — sans elle, un statDelta de MoW
        // restait insourçable.
        const allEntities: Array<{ e: NativePointer; id: number; isUnit: boolean }> = [];
        const targetUnits: Array<{ e: NativePointer; id: number; entityType: number }> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            const isUnit = ty === EntityType.Unit;
            allEntities.push({ e, id, isUnit });
            const isCombatant = isUnit || ty === EntityType.Machine;
            if (isCombatant && (body?.unitId === undefined || id === body.unitId)
                && invokeBool(isAliveMi, [e, statePtr])) {
                targetUnits.push({ e, id, entityType: ty });
            }
        });

        const units: Array<Record<string, unknown>> = [];
        for (const { e, id, entityType } of targetUnits) {
            const mods: Record<string, unknown> = {};
            for (const k of requested) {
                const total = getMod(e, k, nullSrc);
                if (Math.abs(total) < minAbs) continue;          // pas de modification → skip le scan
                const bySource: Array<Record<string, unknown>> = [];
                for (const src of allEntities) {
                    srcBuf.add(4).writeS32(src.id);              // value = BEntityId de la source
                    const amount = getMod(e, k, srcBuf);
                    if (amount !== 0) {
                        bySource.push({
                            source: src.id, amount,
                            self: src.id === id, sourceIsUnit: src.isUnit,
                        });
                    }
                }
                const attributed = bySource.reduce(
                    (a, b) => a + (b.amount as number), 0);
                mods[k] = { total, residual: total - attributed, bySource };
            }
            units.push({
                entityId: id, entityType,
                ctrl: invokeBool(isCtrlByCurMi, [e, statePtr]), mods,
            });
        }
        return { ok: true, runner: label, statTypes: COMBAT_STAT_IDS, units };
    });

    /** ABILITY-STATE BAKÉ des entités-effets (#68/#75) — lit, par effet, le struct
     *  `EffectComponent.AbilityStateReference` (@0x18) : {Owner, AbilityType, Nullable<AbilityState
     *  {Level, VariableMultiplierPercentage}>}. C'est CE state que `BaseEffect.GetAbilityState
     *  @180f11780` expose aux nœuds `ConfigVar` du bonus combat (`CreateEffectDamageBonusForAttack
     *  @180f6bee0`) — la mesure DIRECTE du multiplier combat d'un additif d'effet (SmashaEad :
     *  attendu ≠ 180 pour expliquer +300 vs prédiction 599). Read-only, one-shot, aucun Interceptor.
     *  body: { runnerId?, effectType? } */
    ctx.rpc.effectAbilityStates = (
        body?: { runnerId?: number; effectType?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const effects: Array<Record<string, unknown>> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Effect) return;
            const info = readEffectAbilityStateRaw(e);
            if (info === null) return;
            if (typeof body?.effectType === "number"
                && info.effectType !== body.effectType) return;
            effects.push({ effectId: id, ...info });
        });
        return { ok: true, runner: label, effects };
    });

    /** ABILITY-STATE des INSTANCES d'ability par unité (#68/#75) — dump brut des
     *  `ActiveAbility` (ActiveAbilityComponent.Abilities@0x20, dump gqfc5mff6c TypeDefIndex
     *  11390 : AbilityName@0x44, _abilityState{Level@0x4C, VariableMultiplierPercentage@0x50,
     *  Counter@0x54}, OverrideAbilityState(Nullable)@0x58) et des `TriggeredAbility`
     *  (TriggeredAbilityComponent+0x18, instance : Level{level@0x20, mult@0x24}, +0x28).
     *  Résolution du state combat d'un effet triggered-sourced (`UnitExtensions.GetAbilityState
     *  @180eced70` : mapping statique triggered→active `GetActiveAbilityUsedForConfig @1815808e0`
     *  PUIS `ActiveAbility.get_AbilityState @180f8fc40` = override ?? _abilityState).
     *  Read-only, one-shot. body: { runnerId?, unitId? }
     *
     *  #477-r15-r6 : chaque entrée d'`actives[]` porte désormais `state` = `readAbilityState` de
     *  CETTE instance (usable / cooldown / disabled / ammoCost / hasAmmo / level / multiplier /
     *  lastTurnUsed…). C'est le SEUL canal qui couvre l'entrée d'ATTAQUE NORMALE, que
     *  `ActiveAbilityComponent$$GetActives` — donc `decisionView` — filtre. */
    ctx.rpc.unitAbilityStates = (
        body?: { runnerId?: number; unitId?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const aacClass = findClassAnywhere("IdunBattle.Entities.Components", "ActiveAbilityComponent");
        const tacClass = findClassAnywhere("IdunBattle.Entities.Components", "TriggeredAbilityComponent");
        const aaClass = findClassAnywhere("IdunBattle.Entities.Components", "ActiveAbility");
        if (!aacClass) return { ok: false, error: "ActiveAbilityComponent non résolu" };
        // `fieldOffsetOr` et NON `|| fallback` — cf. le commentaire d'`actorStats` plus bas et la
        // docstring de `fieldOffsetOr` : un nom absent vaut **-1**, truthy en JS.
        const AAC_ABILITIES = fieldOffsetOr(aacClass, "Abilities", 0x20);
        const AA = {
            name: aaClass ? fieldOffsetOr(aaClass, "AbilityName", 0x44) : 0x44,
            state: aaClass ? fieldOffsetOr(aaClass, "_abilityState", 0x4c) : 0x4c,
            override: aaClass ? fieldOffsetOr(aaClass, "OverrideAbilityState", 0x58) : 0x58,
        };
        // KeyedCollection/Collection<T> : IList items @0x10 → List {items@0x10, size@0x18, éléments
        // ref 8 o dès 0x20} (même walk que statModSources SH / MAJ 11 dumpTriggeredMult, validé).
        const readInstList = (collection: NativePointer): NativePointer[] => {
            const out: NativePointer[] = [];
            try {
                const list = collection.add(0x10).readPointer();
                if (list.isNull()) return out;
                const items = list.add(0x10).readPointer();
                const size = list.add(0x18).readS32();
                if (items.isNull() || size <= 0 || size > 64) return out;
                for (let i = 0; i < size; i++) {
                    const inst = items.add(0x20 + i * 8).readPointer();
                    if (!inst.isNull()) out.push(inst);
                }
            } catch { /* walk partiel */ }
            return out;
        };
        // #419-r1-tr14-r5-r2-r2-r1 — l'index PRÉ-fabrique, lu UNE fois par appel (la
        // `BattleConfiguration` ne bouge pas pendant la bataille).
        const cfg = readConfigActives(runner);
        const units: Array<Record<string, unknown>> = [];
        let cfgUnmatched = 0;
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit && ty !== EntityType.Machine) return;
            if (body?.unitId !== undefined && id !== body.unitId) return;
            const actives: Array<Record<string, unknown>> = [];
            const triggered: Array<Record<string, unknown>> = [];
            forEachComponent(e, (comp, klass) => {
                if (aacClass && klass.equals(aacClass)) {
                    try {
                        const coll = comp.add(AAC_ABILITIES).readPointer();
                        if (!coll.isNull()) {
                            for (const inst of readInstList(coll)) {
                                const ov: number[] = [];
                                for (let i = 0; i < 4; i++) {
                                    try { ov.push(inst.add(AA.override + i * 4).readS32()); }
                                    catch { break; }
                                }
                                actives.push({
                                    type: inst.add(AA.name).readS32(),
                                    level: inst.add(AA.state).readS32(),
                                    mult: inst.add(AA.state + 4).readS32(),
                                    counter: inst.add(AA.state + 8).readS32(),
                                    overrideRaw: ov,
                                    // #477-r15-r6 — l'ÉTAT CASTABLE de CETTE instance, lu ici
                                    // plutôt qu'apparié depuis `decisionView`.
                                    //
                                    // POURQUOI CE CANAL-CI ET PAS L'AUTRE. `decisionView` énumère
                                    // par `ActiveAbilityComponent$$GetActives`, qui FILTRE : la
                                    // seule entrée d'attaque normale en sort par
                                    // `AbilityComponent.NormalAttackType`, SANS objet
                                    // `ActiveAbility` derrière, donc sans `usable`/`cooldown`/
                                    // `disabled`. Les trois tags correspondants du flux de replay
                                    // étaient donc posés à l'état neuf, non mesurés. La boucle
                                    // ci-dessus, elle, itère `Abilities@0x20` ÉLÉMENT PAR ÉLÉMENT
                                    // — la MÊME collection, dans le MÊME ordre, qu'itère
                                    // `IdunBattle.Operations.AddUnitOperation$$Execute` : ce que
                                    // `readAbilityState` en tire couvre TOUTES les entrées,
                                    // attaque normale comprise, et n'a aucun appariement à faire.
                                    //
                                    // SOUS-OBJET, pas un spread : `state.level` / `state.multiplier`
                                    // sont `ActiveAbility$$get_AbilityState()` (l'OVERRIDE prime),
                                    // c'est-à-dire ce que le natif écrit dans les tags 24/25 ;
                                    // `level` / `mult` / `counter` ci-dessus restent le champ BRUT
                                    // `_abilityState`. Les deux se valent tant qu'aucun override
                                    // n'existe (`overrideRaw` le publie), et les fusionner sous un
                                    // même nom rendrait indiscernables deux lectures distinctes.
                                    state: readAbilityState(inst),
                                });
                            }
                        }
                    } catch { /* composant illisible */ }
                }
                if (tacClass && klass.equals(tacClass)) {
                    try {
                        const coll = comp.add(0x18).readPointer();
                        if (!coll.isNull()) {
                            for (const inst of readInstList(coll)) {
                                const raw: number[] = [];
                                for (let i = 0; i < 12; i++) {
                                    try { raw.push(inst.add(0x10 + i * 4).readS32()); }
                                    catch { break; }
                                }
                                triggered.push({
                                    level: inst.add(0x20).readS32(),
                                    mult: inst.add(0x24).readS32(),
                                    raw,
                                });
                            }
                        }
                    } catch { /* composant illisible */ }
                }
            });
            if (actives.length || triggered.length) {
                // TRI-ÉTAT STRICT. `configId === null` = la clé de jointure n'a pas pu être lue ;
                // `configId` lu mais absent de l'index = entité SANS configuration dans la BC
                // (une unité INVOQUÉE, typiquement — elle naît d'une opération de spawn, pas de
                // `BC.Units`). Les deux rendent `configActives: null`, c'est-à-dire PAS MESURÉ.
                // Un `[]` signifie « la configuration existe et ne porte aucun actif », ce qui
                // est le cas de 50 des 175 entrées du seed : rabattre l'un sur l'autre ferait
                // exactement l'inverse de ce que ce canal existe pour permettre.
                const configId = readEntityConfigId(e);
                const raw = (configId !== null
                    && Object.prototype.hasOwnProperty.call(cfg.byId, configId))
                    ? cfg.byId[configId] : null;
                if (raw === null) cfgUnmatched++;
                units.push({
                    entityId: id, actives, triggered,
                    configId,
                    configActives: raw === null ? null : raw.map((t) => ({
                        type: t, name: abilityName(t) ?? "id:" + t,
                    })),
                });
            }
        });
        return {
            ok: true, runner: label, units,
            // #433-r4-r2-r1-r1-c-r1 — même compteur que `decisionView.turnsEnded` : le canal qui
            // porte l'état d'ability doit porter l'échelle à laquelle il se compare.
            turnsEnded: readTurnsEnded(statePtr),
            turnsEndedLayout: turnsEndedLayout(),
            // #419-r1-tr14-r5-r2-r2-r1 — ce que le capteur a RÉSOLU, et combien d'entités
            // n'ont pas de configuration jointe (attendu > 0 dès qu'il y a des invoqués).
            configLayout: { ...cfg.layout, unmatchedEntities: cfgUnmatched },
            // #477-r15-r6 — la disposition que `actives[].state` a réellement résolue. Un offset
            // résolu par NOM est juste ou ABSENT (`-1`), jamais approximatif ; mais le lecteur ne
            // peut pas distinguer « champ lu » de « champ non trouvé, clé absente » sans qu'on le
            // lui dise. C'est la même raison qu'ailleurs dans ce fichier, et c'est ce qui permet à
            // un consommateur de LEVER au lieu de retomber sur une valeur par défaut.
            abilityStateLayout: abilityStateLayout(),
        };
    });

    /** PROBE de la config d'ability RÉELLEMENT enregistrée côté battle (#68/#75) —
     *  invoque `AbilitiesDatabase.GetConfig(<kind> id)` (registre du runner, via
     *  `EntityServices.<Abilities>@0x40`) puis `AbilityConfiguration.GetVariableForLevel
     *  @181576fb0` (varType, AbilityState{level,mult,counter}, dontThrow) sur une grille
     *  (level, mult) → la VALEUR exacte que le combat résout (formule native
     *  `round_fix64(table[level-1] x mult/100)` si var rarity-flaggée, cf.
     *  `TryGetVariableArrayForLevel @181577510`). Dump aussi la liste rarity-flag
     *  (config+0x28) + la klass concrète du config. Read-only (invokes purs).
     *  body: { runnerId?, id, kind: "triggered"|"active", varType?=8, grid?=[[lvl,mult],…] } */
    ctx.rpc.abilityConfigProbe = (
        body?: {
            runnerId?: number; id?: number; kind?: string; varType?: number;
            grid?: Array<[number, number]>;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.id !== "number") return { ok: false, error: "id requis" };
        let runner: NativePointer;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
        } else if (state.liveRunner) {
            runner = state.liveRunner;
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (servicesOff < 0) return { ok: false, error: "servicesOff non résolu" };
        const services = runner.add(servicesOff).readPointer();
        if (services.isNull()) return { ok: false, error: "services null" };
        const abilitiesOff = entityServicesClass
            ? fieldOffsetOr(entityServicesClass, "<Abilities>k__BackingField", 0x40) : 0x40;
        const db = services.add(abilitiesOff).readPointer();
        if (db.isNull()) return { ok: false, error: "AbilitiesDatabase null" };
        const dbKlass = db.readPointer();
        const paramClass = body.kind === "active" ? "ActiveAbilityType" : "TriggeredAbilityType";
        const getConfigMi = findMethodByParamClasses(dbKlass, "GetConfig", [paramClass]);
        if (!getConfigMi) return { ok: false, error: `GetConfig(${paramClass}) non résolu` };
        const idBuf = Memory.alloc(4); idBuf.writeS32(body.id);
        let cfg: NativePointer;
        try { cfg = invokeMethod(getConfigMi.info, db, [idBuf]); }
        catch (e) { return { ok: false, error: "GetConfig: " + (e as Error).message }; }
        if (cfg.isNull()) return { ok: false, error: "config null" };
        const cfgKlass = cfg.readPointer();
        const cfgClassName = s(class_get_name(cfgKlass) as NativePointer);
        // GetVariableForLevel(AbilityVariableType, AbilityState, bool) — 3 params.
        const gvflMi = findMethodByParamCount(cfgKlass, "GetVariableForLevel", 3);
        if (!gvflMi) return { ok: false, error: "GetVariableForLevel(3) non résolu", cfgClassName };
        const varType = typeof body.varType === "number" ? body.varType : 8; // extraDmg=8
        const varBuf = Memory.alloc(4); varBuf.writeS32(varType);
        const noThrow = Memory.alloc(4); noThrow.writeU8(1);
        const stateBuf = Memory.alloc(12);
        const grid: Array<[number, number]> = (body.grid && body.grid.length)
            ? body.grid
            : [[50, 180], [50, 100], [50, 90], [49, 180], [65, 100], [64, 100], [1, 180]];
        const values: Array<Record<string, unknown>> = [];
        for (const [lvl, mult] of grid) {
            stateBuf.writeS32(lvl); stateBuf.add(4).writeS32(mult); stateBuf.add(8).writeS32(0);
            let v: number | null = null; let err: string | null = null;
            try {
                const r = invokeMethod(gvflMi.info, cfg, [varBuf, stateBuf, noThrow]);
                v = r.isNull() ? null : r.add(0x10).readS32();
            } catch (e) { err = (e as Error).message; }
            values.push({ level: lvl, mult, value: v, ...(err ? { err } : {}) });
        }
        // Liste rarity-flag (`_variablesAffectedByRarityBonus`, config+0x28 d'après
        // TryGetVariableArrayForLevel @181577510) : List<AbilityVariableType> (ints).
        const rarityFlagged: number[] = [];
        try {
            const list = cfg.add(0x28).readPointer();
            if (!list.isNull()) {
                const items = list.add(0x10).readPointer();
                const size = list.add(0x18).readS32();
                if (!items.isNull() && size > 0 && size <= 64) {
                    for (let i = 0; i < size; i++) rarityFlagged.push(items.add(0x20 + i * 4).readS32());
                }
            }
        } catch { /* liste illisible */ }
        return { ok: true, cfgClassName, id: body.id, kind: paramClass, varType, values,
            rarityFlagged, cfgPtr: cfg.toString() };
    });

    // --- TRACE one-shot de la résolution de variable d'ability (#68/#75, étendu #57c-C) ---
    // Interceptor.attach TEMPORAIRE sur `AbilityConfiguration.GetVariableForLevel @181576fb0`
    // (l'API externe, basse fréquence — PAS un hot path). Capture {varType, state{level,mult},
    // cfg ptr, backtrace RVAs, VALEUR retournée (int brut RAX)} : la donnée runtime que le
    // décompilé ne peut pas donner. La VALEUR + la pile identifient la config/mécanisme sans
    // ambiguïté (leçon #57c-C : le couple {state,varType} seul est sous-déterminé — coïncidences
    // 831/1496 multi-configs ont coûté 2 fausses pistes ; c'est value=2992 dans la pile
    // GetAdditionalHitsFromEffectsInternal @180e59150 qui a tranché ExplosiveMaladies).
    // ARM ON-DEMAND uniquement (jamais auto-armé — leçon modifier-observe), à retirer via
    // varTraceRemove sitôt la mesure faite.
    let varTraceListener: InvocationListener | null = null;
    const varTraceBuf: Array<Record<string, unknown>> = [];
    ctx.rpc.varTraceInstall = (): Promise<unknown> => queueOnMainThread(() => {
        if (varTraceListener) return { ok: true, already: true };
        const cfgClass = findClassAnywhere("IdunBattle.Configuration", "AbilityConfiguration");
        if (!cfgClass) return { ok: false, error: "AbilityConfiguration non résolu" };
        // GetVariableForLevel(varType, state, noThrow) @181576fb0 — l'API EXTERNE (au-dessus de
        // TryGetVariableArrayForLevel) : onLeave lit la VALEUR RÉSOLUE (boxed int @+0x10) — la
        // donnée qui identifie la config/var sans ambiguïté (le couple {state} seul est sous-
        // déterminé : coïncidences 831/1496 multi-configs, vécu #57c-C).
        const mi = findMethodByParamCount(cfgClass, "GetVariableForLevel", 3);
        if (!mi || mi.ptr.isNull()) return { ok: false, error: "GetVariableForLevel non résolu" };
        const gaBase = Process.getModuleByName("GameAssembly.dll").base;
        varTraceListener = Interceptor.attach(mi.ptr, {
            onEnter(args) {
                try {
                    const st = args[2];
                    (this as InvocationContext & { entry?: Record<string, unknown> }).entry = {
                        varType: args[1].toInt32(),
                        level: st.readS32(),
                        mult: st.add(4).readS32(),
                        counter: st.add(8).readS32(),
                        cfg: args[0].toString(),
                        // RVAs GameAssembly de la pile d'appel (VA ghidra = RVA + 0x180000000).
                        bt: Thread.backtrace(this.context, Backtracer.ACCURATE)
                            .filter((a) => a.compare(gaBase) >= 0)
                            .slice(0, 10)
                            .map((a) => a.sub(gaBase).toString()),
                    };
                } catch { /* frame illisible */ }
            },
            onLeave(retval) {
                const entry = (this as InvocationContext & { entry?: Record<string, unknown> }).entry;
                if (!entry || varTraceBuf.length >= 500) return;
                // retour = int BRUT (registre RAX), pas un boxed object.
                entry.value = retval.toInt32();
                varTraceBuf.push(entry);
            },
        });
        return { ok: true, installed: true };
    });
    ctx.rpc.varTraceRead = (
        body?: { reset?: boolean; varType?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        const entries = (typeof body?.varType === "number")
            ? varTraceBuf.filter((e) => e.varType === body.varType)
            : varTraceBuf.slice();
        const out = { ok: true, count: varTraceBuf.length, entries };
        if (body?.reset) varTraceBuf.length = 0;
        return out;
    });
    ctx.rpc.varTraceRemove = (): Promise<unknown> => queueOnMainThread(() => {
        if (varTraceListener) { varTraceListener.detach(); varTraceListener = null; }
        varTraceBuf.length = 0;
        return { ok: true };
    });

    /** ATTACK-HISTORY par unité (`ActorStatisticsComponent` @180f92980) — capteur des compteurs
     *  runtime de combat, dont `TotalTurnsWithAttacksMade` que le natif consomme pour le buff
     *  MartialInspiration (#106 : `+33% Damage` par tour où l'unité a attaqué cette bataille ; base
     *  prédiction 1-coup = `var12 · (100 + 33·count)/100`). Compteur PER-UNIT non exposé ailleurs
     *  (ni decisionView ni combatSnapshot). Offsets CONFIRMÉS par TROIS lectures indépendantes du
     *  décompilé : `TotalAttacksMadeFormula.Calculate @180f25b90` lit `*(comp+0x20)` ;
     *  `TotalTurnsWithAttacksMadeFormula.Calculate @180f26780` lit `*(comp+0x30)` ; `RegisterAttackMade
     *  @180f91b50` incrémente `+0x20` à CHAQUE attaque et `+0x30` UNE fois/tour (gate « déjà attaqué ce
     *  tour » @+0x40). Classe résolue par NOM (findClassAnywhere) ; offset par `getFieldOffset` avec
     *  fallback décompilé. Read-only, one-shot, aucun Interceptor. body: { runnerId?, unitId? } */
    ctx.rpc.actorStats = (
        body?: { runnerId?: number; unitId?: number },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const asClass = findClassAnywhere("IdunBattle.Entities.Components", "ActorStatisticsComponent");
        if (!asClass) return { ok: false, error: "ActorStatisticsComponent non résolu" };
        // Offsets int32 sur le composant (décompilé, 3 confirmations). Nom d'abord, repli décompilé
        // ensuite — via `fieldOffsetOr`, JAMAIS via `|| fallback`.
        // ⚠ L'idiome `getFieldOffset(...) || 0x20` qui figurait ici était FAUX : `getFieldOffset`
        // rend **-1** sur un nom absent, et `-1` est *truthy* en JS, donc le repli n'était jamais
        // pris et le hook lisait `comp - 1`. MESURÉ (`probe_340_r1_actorstats_live.py`) sur les deux
        // champs de tuiles ci-dessous, qui rendaient tous deux la MÊME valeur constante
        // (-1201836032) — signature d'une lecture à la même adresse. Détail : `fieldOffsetOr`.
        const OFF_TOTAL = fieldOffsetOr(asClass, "TotalAttacksMade", 0x20);
        const OFF_TURNS = fieldOffsetOr(asClass, "TotalTurnsWithAttacksMade", 0x30);
        // TUILES PARCOURUES (case-322-r2) — le MÊME composant, trois compteurs contigus, écrits
        // par `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` (`+0xec += n` cumul BATAILLE,
        // `+0xf0 += n` cumul CE TOUR, garde `n < 1` -> no-op) et roulés en FIN de tour par
        // `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn` (`+0xf4 = +0xf0`
        // si `wasOwnTurn`, puis `+0xf0 = 0` INCONDITIONNEL). `+0xf0` est ce que
        // `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` rend — la seule entrée
        // de `ModifiedExoarmour_ExtraDmg`, et le terme RÉEL que la face PRÉDICTION ne pouvait pas
        // lire faute de capteur. Offsets CONFIRMÉS par TROIS lectures indépendantes du décompilé :
        // `RecordTilesMoved` (écrit `+0xec`/`+0xf0`), `TilesMovedThisTurnFormula$$Calculate` (lit
        // `+0xf0`) et `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile` (les
        // SAUVEGARDE avant l'action simulée et les RESTAURE après). Même contrat `fieldOffsetOr` +
        // repli décompilé que les deux compteurs ci-dessus.
        // MESURE (2026-07-31) : seul `TilesMovedThisTurn` porte un nom qui EXISTE dans les
        // métadonnées — les deux autres se repliaient donc, et c'est précisément ce repli que le
        // `|| 0x...` cassait. Vérification : `probe_340_r1_actorstats_live.py` exige des trois
        // champs les DEUX transitions du composant (un pas -> `+0xec += n` et `+0xf0 = n` ;
        // `EndTurnOperation` -> `+0xf4 = +0xf0` puis `+0xf0 = 0`).
        const OFF_TILES_BATTLE = fieldOffsetOr(asClass, "TilesMovedThisBattle", 0xec);
        const OFF_TILES_TURN = fieldOffsetOr(asClass, "TilesMovedThisTurn", 0xf0);
        const OFF_TILES_LAST = fieldOffsetOr(asClass, "TilesMovedLastTurn", 0xf4);
        const units: Array<Record<string, unknown>> = [];
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty !== EntityType.Unit && ty !== EntityType.Machine) return;
            if (body?.unitId !== undefined && id !== body.unitId) return;
            let comp: NativePointer | null = null;
            forEachComponent(e, (c, klass) => {
                if (comp === null && klass.equals(asClass)) comp = c;
            });
            if (comp === null) return;
            const cp = comp as NativePointer;
            units.push({
                entityId: id,
                totalAttacksMade: cp.add(OFF_TOTAL).readS32(),
                totalTurnsWithAttacksMade: cp.add(OFF_TURNS).readS32(),
                tilesMovedThisBattle: cp.add(OFF_TILES_BATTLE).readS32(),
                tilesMovedThisTurn: cp.add(OFF_TILES_TURN).readS32(),
                tilesMovedLastTurn: cp.add(OFF_TILES_LAST).readS32(),
                // #347-r1 — l'HISTORIQUE de position du tour, sur le MÊME appel.
                movement: readMovementPositions(e, statePtr),
            });
        });
        return {
            ok: true, runner: label, units,
            // #347-r1 — ce que le capteur de position a RÉSOLU. `movement: null` sur toutes
            // les unités serait sinon indiscernable de « aucune unité n'a bougé ».
            movementLayout: movementLayout(),
        };
    });

    /** #231-r — TOUTES les entités-effet du state, y compris celles qui ne sont PLUS dans la
     *  liste possédée de leur owner. `decisionView.units[].effects` et `tileMeta.tiles[].effects`
     *  partent tous deux d'`EffectsOwnedComponent.ActiveEffectIds` : un effet absent y est
     *  AMBIGU entre « jamais posé », « posé puis RETIRÉ » et « vivant hors de la liste », et
     *  aucun des deux canaux ne peut les séparer — `includeInactive` compris, puisqu'il ne
     *  desserre que le filtre `IsActive`, pas l'appartenance à la liste.
     *
     *  Le décompilé tranche la moitié du problème et le capteur mesure l'autre :
     *  `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` écrit `EffectComponent.OwnerId`
     *  puis fait `List.Add` sur l'`EffectsOwnedComponent` de CETTE MÊME entité — donc un effet
     *  POSÉ est toujours dans la liste de son owner au moment de la pose ;
     *  `IdunBattle.Operations.RemoveEffectOperation$$Execute` fait `List.Remove` puis pose
     *  `BeingRemoved` (+0x5e) et `Removed` (+0x5f) **sans détruire l'entité**. Trois régimes,
     *  trois signatures LISIBLES :
     *    - l'entité n'apparaît pas du tout        -> JAMAIS POSÉ (gate d'`AddEffectOperation`) ;
     *    - `inOwnerList: false, removed: true`    -> POSÉ PUIS RETIRÉ ;
     *    - `inOwnerList: false, removed: false`   -> ORPHELIN (vivant hors de la liste).
     *
     *  Cas d'usage d'origine : `1197 EffectType.MasterOfTheTutelaries` (#231 §7), dont la
     *  triggered `1173` fire alors que l'effet est absent des deux canaux. Sa durée est
     *  LUE au décompilé — `…MasterOfTheTutelariesAbility$$ExecuteBehaviour` passe à
     *  `DSLBehaviors$$AddEffect` le nœud `<DSLFormulas>+0x20`, que
     *  `IdunBattleLogic.Entities.DSLFormulas$$.ctor` construit avec le littéral **1**.
     *  Read-only, une passe d'entités, aucun Interceptor.
     *  body: { runnerId?, effectType?, includeRemoved?=true } */
    ctx.rpc.effectsAll = (
        body?: { runnerId?: number; effectType?: number; includeRemoved?: boolean },
    ): Promise<unknown> => queueOnMainThread(() => {
        let runner: NativePointer; let label: string;
        if (typeof body?.runnerId === "number") {
            try { runner = getRunner(body.runnerId).runner; }
            catch (e) { return { ok: false, error: (e as Error).message }; }
            setTraceOrigin(body.runnerId);
            label = "build#" + body.runnerId;
        } else if (state.liveRunner) {
            runner = state.liveRunner; label = "live";
        } else { return { ok: false, error: "no runner — pass runnerId" }; }
        if (runner.isNull()) return { ok: false, error: label + " runner null" };
        const statePtr = runner.add(runnerOff.state).readPointer();
        if (statePtr.isNull()) return { ok: false, error: "state null" };
        const includeRemoved = body?.includeRemoved !== false;
        let effects = readAllEffects(statePtr);
        if (typeof body?.effectType === "number") {
            const want = body.effectType | 0;
            effects = effects.filter((e) => e.effectType === want);
        }
        if (!includeRemoved) effects = effects.filter((e) => !e.removed);
        return {
            ok: true, runner: label, count: effects.length, effects,
            // Ventilation, pour que le lecteur n'ait pas à la recalculer — et pour qu'un
            // `count: 0` DISE de quoi il est le zéro.
            orphanCount: effects.filter((e) => !e.inOwnerList && !e.removed).length,
            removedCount: effects.filter((e) => e.removed).length,
        };
    });

}

// --- #347-r1 : HISTORIQUE DE POSITION DU TOUR ------------------------------------------------
//
// CE QUE CE CAPTEUR DÉBLOQUE. Le lift-off de `TheQuickening` (`MoveUnit` vers une
// `UnitPosition` vide) **sort avant** `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` :
// la branche `Count(position) == 0 && MoveUnitOptions+0x15` d'
// `IdunBattle.Operations.MoveUnitOperation$$Execute` retire l'unité du board et retourne. C'est
// le **move-in** qui facture, avec `movementStartPosition =
// IdunBattle.Entities.EntityExtensions$$GetPreviousPositionThisTurn(unit)` — donc une valeur qui
// dépend de l'HISTORIQUE de mouvement du tour, et qu'aucun RPC ne publiait.
//
// ⚠ LE COMPOSANT N'EST PAS CELUI QUE `case-347` §8 NOMME. La fiche écrit
// « `UnitComponent+0x98` » ; mesuré sur le build `rnca9r7q6c` (`dumpEntityComponents`),
// `UnitComponent+0x98` est `PendingHit`. Les quatre `Nullable<UnitPositionId>` vivent sur
// **`IdunBattle.Entities.Components.MovementComponent`** :
//     TurnStartPosition @+0x78 · PreviousPosition @+0x88 ·
//     PreviousPositionThisTurn @+0x98 · PendingPosition @+0xa8
// et c'est bien `+0x98` que lit `GetPreviousPositionThisTurn` (`local_38 = *(comp+0x98)`,
// `uStack_30 = *(comp+0xa0)`), qu'écrit
// `IdunBattle.Operations.SetUnitPositionOperation$$SavePreviousPosition` et que remet à zéro
// `IdunBattle.Entities.Behaviours.ResetPreviousPositionBehaviour$$Execute`. L'offset coïncide,
// le COMPOSANT non — un capteur écrit sur la foi de la fiche aurait lu `PendingHit`.
//
// LAYOUT. `Nullable<UnitPositionId>` = 16 octets : la valeur (un `UnitPositionId`, 8 o = un
// `List<BEntityId>` — `classes.tsv` publie 24, taille BOXÉE, header 0x10 déduit) puis
// `hasValue` à +8. C'est ce qu'établissent les quatre champs espacés de 0x10 ET
// `SavePreviousPosition`, qui écrit 16 octets en deux `undefined8`.
//
// DÉCODAGE. On n'ouvre PAS le `List<BEntityId>` à la main : `hasValue` lu au champ, puis
// `IdunBattle.Core.UnitPositionIdExtensions$$ToTileList(positionId, state)` INVOQUÉ (la valeur
// est passée par POINTEUR, convention value-type d'`il2cpp_runtime_invoke` — même idiome que
// l'`AbilityState` de `makeDamagePredictions`), puis `extractTiles`. Le natif fait exactement
// cet appel pour matérialiser une position.
const movementComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "MovementComponent");
const unitPositionIdExtClass = findClassAnywhere(
    "IdunBattle.Core", "UnitPositionIdExtensions");
const toTileListMi = unitPositionIdExtClass
    ? findMethodByParamCount(unitPositionIdExtClass, "ToTileList", 2) : null;
/** Les quatre champs, avec leur repli décompilé. `fieldOffsetOr` et JAMAIS `|| fallback` :
 *  `getFieldOffset` rend **-1** sur un nom absent, truthy en JS (#340-r1). */
const MOVEMENT_POS_FIELDS: ReadonlyArray<{ key: string; name: string; fallback: number }> = [
    { key: "turnStartPosition", name: "TurnStartPosition", fallback: 0x78 },
    { key: "previousPosition", name: "PreviousPosition", fallback: 0x88 },
    { key: "previousPositionThisTurn", name: "PreviousPositionThisTurn", fallback: 0x98 },
    { key: "pendingPosition", name: "PendingPosition", fallback: 0xa8 },
];

// --- #347-r3 : la DISPOSITION du `Nullable<T>` se DÉRIVE, elle ne se suppose pas ------------
//
// CE QUE LA FENÊTRE DU 2026-08-08 A MESURÉ. Le canal fonctionne — la transition
// `previousPositionThisTurn: null` -> non-null au premier pas est nette, et l'unité qui NE bouge
// PAS reste à `null` — mais `tiles` sortait `null` sur les quatre champs : le DÉCODAGE était muet.
//
// ⚠ ET LA TRANSITION NE DISCRIMINE PAS LA CAUSE, c'est ce qui rend la dérivation obligatoire.
// La version d'avant lisait `hasValue` à `off + 8`, c'est-à-dire en supposant la disposition
// `{ T value; bool hasValue; }`. Or `frida/hooks/game/match-state.ts` a DÉJÀ mesuré l'inverse sur
// ce build pour `MachinePlatformComponent` : « Mono Nullable<T> layout : hasValue @+0 (1B +
// padding), value @+4 ». Sous CETTE disposition, l'octet lu à `off + 8` est l'octet de poids
// faible du POINTEUR de liste — nul quand le champ est vide, non nul quand la liste existe : le
// drapeau « marche » PAR ACCIDENT, et l'adresse passée à `ToTileList` désigne alors le drapeau au
// lieu de la valeur, donc l'invocation ne rend rien. Les deux hypothèses expliquent EXACTEMENT la
// même transition ; aucune mesure de terrain ne peut les séparer.
//
// LA SORTIE N'EST PAS DE CHOISIR, C'EST DE LIRE. Le natif lui-même ne suppose rien :
// `IdunBattle.Entities.EntityExtensions$$GetPreviousPositionThisTurn` calcule l'adresse de
// `hasValue` depuis les métadonnées du type. On fait pareil — le champ `PreviousPositionThisTurn`
// porte son `Il2CppType`, dont la classe est le `Nullable<UnitPositionId>` INFLATÉ, dont on
// ÉNUMÈRE les champs : `value` et `hasValue` y donnent leurs offsets. Aucune des deux
// dispositions n'est écrite dans ce fichier.
//
// ⚠ **ON NE RE-DÉRIVE RIEN ICI** : `nullableLayoutOf` vit dans `./internals.js`, posé par
// `#579-r1` sur EXACTEMENT le même défaut (`readAbilityState` lisait `hasValue` à `+4` et
// publiait le bit à la place de la valeur — deux casts d'une même bataille rendaient tous deux
// `unresetedLastTurnUsed = 1`, ce qu'un compteur MONOTONE ne peut pas faire). La première
// réparation de ce capteur-ci en écrivait une SECONDE copie ; elle est retirée, et la fonction
// d'`internals` est exportée. Deux exemplaires de la même parade, c'est le patron que
// `case-287-r12` a déjà eu à défaire en trois exemplaires.
//
// Ce que le foyer rend : `{ hasValueOff, valueOff }` DÉJÀ corrigés du header d'objet BOXÉ (0x10),
// ou `null` si la disposition n'est pas résolue — auquel cas on répond « PAS MESURÉ », jamais une
// lecture à une convention devinée.

/** Ce que le capteur a RÉSOLU — publié au niveau réponse (tri-état). */
function movementLayout(): Record<string, unknown> {
    const ref = movementComponentClass
        ? nullableLayoutOf(movementComponentClass, "PreviousPositionThisTurn") : null;
    return {
        componentResolved: movementComponentClass !== null,
        toTileListResolved: toTileListMi !== null,
        offsets: movementComponentClass
            ? Object.fromEntries(MOVEMENT_POS_FIELDS.map(
                (f) => [f.key, fieldOffsetOr(movementComponentClass, f.name, f.fallback)]))
            : null,
        // #347-r3 — la disposition DÉRIVÉE, publiée telle quelle. `null` / `derived: false` =
        // PAS MESURÉE : le lecteur ne doit pas pouvoir confondre « hasValue est à +8 » avec
        // « je n'ai pas su le lire ».
        nullableLayout: ref,
    };
}

/** Les quatre `Nullable<UnitPositionId>` d'une unité, décodées en hex.
 *  `null` (au niveau du champ) = `hasValue == 0` — le natif n'a pas de position enregistrée.
 *  `null` (au niveau de l'objet) = capteur MUET : composant absent ou classe non résolue.
 *
 *  ⚠ Chaque champ publie sa CAUSE (`decode`) et ses 16 octets BRUTS. La version d'avant rendait
 *  `{ tiles: null }` pour QUATRE causes distinctes — méthode non résolue, invocation levée, liste
 *  nulle, disposition fausse — ce qui a coûté une fenêtre : la mesure disait « muet » sans dire
 *  de quoi. Le brut est ce qui permet de trancher SANS réinjecter. */
function readMovementPositions(
    entity: NativePointer, statePtr: NativePointer,
): Record<string, unknown> | null {
    if (!movementComponentClass) return null;
    let comp: NativePointer | null = null;
    forEachComponent(entity, (c, klass) => {
        if (comp === null && klass.equals(movementComponentClass)) comp = c;
    });
    if (comp === null) return null;
    const cp = comp as NativePointer;
    const out: Record<string, unknown> = {};
    for (const f of MOVEMENT_POS_FIELDS) {
        const off = fieldOffsetOr(movementComponentClass, f.name, f.fallback);
        // Les 16 octets du `Nullable`, en U32 — publiés QUOI QU'IL ARRIVE. C'est la seule donnée
        // qui survit à une erreur de disposition, et donc la seule qui permette de la corriger.
        const raw: number[] = [];
        for (let i = 0; i < 4; i++) {
            try { raw.push(cp.add(off + i * 4).readU32()); } catch { raw.push(-1); }
        }
        const lay = nullableLayoutOf(movementComponentClass, f.name);
        if (!lay) {
            out[f.key] = { raw, tiles: null, decode: "layout-not-derived" };
            continue;
        }
        let hasValue = false;
        try { hasValue = cp.add(off + lay.hasValueOff).readU8() !== 0; }
        catch { out[f.key] = { raw, tiles: null, decode: "hasValue-unreadable" }; continue; }
        if (!hasValue) { out[f.key] = null; continue; }
        if (!toTileListMi) {
            out[f.key] = { raw, tiles: null, decode: "no-ToTileList" }; continue;
        }
        try {
            const list = invokeMethod(
                toTileListMi.info, null, [cp.add(off + lay.valueOff), statePtr]);
            if (list.isNull()) { out[f.key] = { raw, tiles: null, decode: "null-list" }; continue; }
            out[f.key] = { raw, tiles: extractTiles(list), decode: "ok" };
        } catch (e) {
            out[f.key] = { raw, tiles: null, decode: "threw", error: (e as Error).message };
        }
    }
    return out;
}
