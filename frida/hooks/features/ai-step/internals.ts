import {
    class_get_fields, class_get_name,
    field_get_name, field_get_type,
    findClass, findClassAnywhere, findCtorByParamCount,
    findMethod, findMethodByParamCount, getFieldInfo, getFieldOffset, methodParamClassName, s,
    type_get_class_or_element_class,
} from "../../il2cpp/helpers.js";
import { il2cpp_object_new, invokeMethod } from "../../il2cpp/invoke.js";
import { gcRoot } from "../../il2cpp/gc-root.js";
import { runnerApplyMi, runnerClass, runnerOff } from "../../game/runner.js";
import {
    EntityType, forEachComponent, forEachEntity, positionComponentClass,
    projectMatchState, readBattleStatus,
} from "../../game/match-state.js";
import { aiControlClass, applyAiMsgMi } from "../../game/ai-control.js";
import {
    ensureStreamHooks, popApply, pushApply, StreamEvent,
} from "../../game/apply-stack.js";
import { abilityName } from "../../data/ability-names.js";
import { dumpEnum } from "../../il2cpp/enum-dump.js";

// --- Résolution statique (une fois au load) ---

// AiControl.GetAi(Nullable<BEntityId>) → IAiPlayerStrategy.
export const getAiMi = findMethod(aiControlClass!, "GetAi");
// Fallback direct : AiControl._defaultPlayerAiStrategy (cas standard joueur).
export const defaultStratOff = getFieldOffset(aiControlClass!, "_defaultPlayerAiStrategy");

// Helpers statiques UnitExtensions (IdunBattle.Entities) — invocables, zéro
// offset brut. Servent à calculer le set « units à activer » de façon vivante
// (gère les kills) : un squad est à activer s'il est contrôlé par le joueur
// courant ET vivant ET a encore une action.
export const unitExtClass = findClassAnywhere("IdunBattle.Entities", "UnitExtensions");
export const hasActionLeftMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "HasActionLeft", 1) : null;
export const isAliveMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "IsAlive", 2) : null;
export const isCtrlByCurMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "IsControlledByCurrentPlayer", 2) : null;
export const isRangedMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "IsRanged", 1) : null;
// `UnitExtensions.IsTargetable @180ed8ff0` = `!HasFlag(unit, 0x11)` (flag 0x11 = « ne peut être
// ciblé », posé par TeleportStrike/Deep-Strike tant que l'unité n'a pas agi). Miroir du filtre de
// `MovementActionGenerator.<FindClosestEnemy>d__8 @181197f10` : la feuille MinDist(16) ne mesure
// QU'AUX ennemis ciblables (une unité deep-strike non-atterrie est ignorée du ClosestEnemy). #57l.
export const isTargetableMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "IsTargetable", 1) : null;
// #N11 — `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(unit) -> Int32` : le compteur
// PER-UNITÉ que lit `OwnerHasFinishedMinTurns` (#171), et qu'AUCUN RPC n'exposait — `load_state`
// laissait donc `UnitComponent.turns_finished` à 0 pour toute unité chargée d'un snapshot
// mi-bataille. Ce n'est PAS un `StatType`, donc ni `combatSnapshot.stats` ni `GetStat` ne peuvent
// l'atteindre : il fallait un accesseur à lui.
// On invoque la fonction NOMMÉE plutôt que de lire le champ à `+0x5c` (l'offset que citait la
// fiche du résidu) : un offset brut est vrai jusqu'à la prochaine MAJ et faux SILENCIEUSEMENT
// après, là où le symbole se re-résout tout seul.
export const getTurnsFinishedMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "GetTurnsFinished", 1) : null;

// EndTurnMessage — appliqué pour passer la main à l'autre équipe quand
// l'épuisement de l'énumérateur n'a pas auto-flippé le tour.
export const endTurnClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Messages", "EndTurnMessage");
export const endTurnCtor = endTurnClass ? findCtorByParamCount(endTurnClass, 0) : null;

// MovementQuery.GetMovableTilesFor(unit, ignoreUnitFlags, MovementOptions) →
// IOrderedSet<IEntity> (tiles atteignables). L'instance vit sur le runner
// (<MovementQuery>k__BackingField). 3-param overload (cf. move-options.ts).
export const movementQueryClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Core.Services", "MovementQuery");
export const getMovableTilesMi = movementQueryClass
    ? findMethodByParamCount(movementQueryClass, "GetMovableTilesFor", 3) : null;
export const movementQueryOff = getFieldOffset(
    runnerClass!, "<MovementQuery>k__BackingField");
// IAttackQuery.GetAllTilesInAbilityRange(unit, possibleTiles, includeNormalAttack)
// → tiles frappables depuis un ensemble de positions. Move ∪ ça = danger zone.
// L'instance vit sur le runner (<AttackQuery>k__BackingField).
export const attackQueryOff = getFieldOffset(
    runnerClass!, "<AttackQuery>k__BackingField");
// IDamagePredictionQuery.GetAllPredictions(attacker, selectedAttackerTile,
// ActiveAbilityType) → IDictionary<IEntity, DamagePredictionResult>.
// Layout du `DamagePredictionResult` : `frida/hooks/game/damage-prediction.ts`
// (re-dérivé sur `rnca9r7q6c`, #276 — les offsets qui figuraient ici dataient de
// `gqfc5mff6c` et étaient faux depuis la migration).
// L'instance vit dans EntityServices (container god-object) tenu par le runner
// via <Services>@0xC8 ; EntityServices.<DamagePredictionQuery>@0x88.
export const servicesOff = getFieldOffset(runnerClass!, "<Services>k__BackingField");
export const entityServicesClass = findClass(
    "BattleLogicAssembly.dll", "IdunBattle.Core.Services", "EntityServices");
export const dpqInServicesOff = entityServicesClass
    ? getFieldOffset(entityServicesClass, "<DamagePredictionQuery>k__BackingField") : -1;
// IBattleQuery vit dans EntityServices.<Battle>@0x70 (god-object services). Porte
// GetAllValidTargetsFromAllPossibleMovementTiles(unit, ActiveAbilityType, bool
// ignoreMovementFlag) → ValidTargets = énumération des cibles LÉGALES de l'ability
// TOUTE-LE-TOUR (toutes positions de move incluses). C'est ce que l'IA (BasePlaybook)
// consomme pour ses abilities non-attaque aussi (buff/summon/hex). Read-only.
// cf. docs/rl/ai-step-toolkit.md §« Légalité ability + RAISON structurée ».
export const battleInServicesOff = entityServicesClass
    ? getFieldOffset(entityServicesClass, "<Battle>k__BackingField") : -1;
// PositionComponent : Coordinate.Column @0x10, Row @0x14 (cf. move-options).
export const POS_COL_OFF = 0x10;
export const POS_ROW_OFF = 0x14;

// --- Abilities concrètes d'une unité (pour ranker) ---
// L'attaque normale a un id TYPÉ PAR UNITÉ (ex. Loki_NormalAttack=69), PAS
// l'abstrait NormalAttack=17 (absent des components → GetOrNull échoue).
// ActiveAbilityComponent : Abilities (KeyedCollection) @0x20, NormalAttackType
// @0x28 ; GetActives() → List<ActiveAbility> ; Components.ActiveAbility.AbilityName
// @0x44 = son ActiveAbilityType.
export const activeAbilityComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "ActiveAbilityComponent");
export const normalAttackTypeOff = activeAbilityComponentClass
    ? getFieldOffset(activeAbilityComponentClass, "NormalAttackType") : -1;
// MoW : leurs abilities ne sont PAS l'attaque normale (NormalAttackType=0) mais
// Primary/SecondaryMachineAbilityType (artillerie). Offsets résolus runtime.
export const primaryMachineAbilityOff = activeAbilityComponentClass
    ? getFieldOffset(activeAbilityComponentClass, "PrimaryMachineAbilityType") : -1;
export const secondaryMachineAbilityOff = activeAbilityComponentClass
    ? getFieldOffset(activeAbilityComponentClass, "SecondaryMachineAbilityType") : -1;
export const getActivesMi = activeAbilityComponentClass
    ? findMethodByParamCount(activeAbilityComponentClass, "GetActives", 0) : null;
// GetActives filtre par IsActiveAbility(type) → RATE les actives GRANTED-par-trigger
// (ex. heal du passif TwistedScience, id 1167 : castable mais hors enum « active »).
// GetUnusedAbilities itère la MÊME collection mais filtre par le flag « unused » (@0x28)
// → INCLUT les granted. On l'utilise pour compléter l'énumération (cf. unitAbilityTypes).
export const getUnusedAbilitiesMi = activeAbilityComponentClass
    ? findMethodByParamCount(activeAbilityComponentClass, "GetUnusedAbilities", 0) : null;
export const componentsActiveAbilityClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "ActiveAbility");
export const abilityNameOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "AbilityName") : -1;
// ÉTAT RUNTIME par actif (components.ActiveAbility) — l'info LIVE absente de
// gameconfig (qui n'a que noms+stats statiques) : savoir ce qui est castable CE
// tour (cooldown/munitions/disabled). Offsets résolus PAR NOM (robuste au build).
// (CanStillBeUsed@0x28, RemainingCooldownTurns@0x2C, IsDisabled@0x35,
// AmmoCost@0x38, HasEnoughAmmo@0x40.)
//
// ⚠ La disposition INTERNE d'un `Nullable<T>` ne se suppose pas — elle est résolue par
// réflexion (`nullableIntLayout` plus bas). Ce commentaire annonçait `{ int value @+0 ;
// bool hasValue @+4 }` ; c'est FAUX, et ça a été MESURÉ (#579-r1, cf. la docstring de
// `nullableIntLayout`).
export const abCanUseOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "CanStillBeUsed") : -1;
export const abCooldownOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "RemainingCooldownTurns") : -1;
export const abDisabledOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "IsDisabled") : -1;
export const abAmmoCostOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "AmmoCost") : -1;
export const abHasAmmoOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "HasEnoughAmmo") : -1;
// AbilityState PER-ABILITY (#100) : chaque entrée `ActiveAbility` porte SON couple
// {Level@+0, VariableMultiplierPercentage@+4} (struct AbilityState 12 o, dump TypeDefIndex 24402)
// — c'est CE niveau que le natif passe au playbook (MakeDamagePredictions 5e arg) et que
// `TryGetVariableArrayForLevel @181577510` consomme (idx = Level.ToZeroBasedIndex clampé table ;
// × mult/100 si var ∈ variablesAffectedByRarityBonus). PAS le canal global unitConfig
// (activeAbilityLevel × abilityVariablesMultiplier) : mesuré u80 PlasmaCannon natif =
// maxDmg[65]×120 = 1396 vs global 50×180 = 1594 (faux). Mirror `get_AbilityState @180f8fc40` :
// OverrideAbilityState (Nullable<AbilityState> @0x58, hasValue @+0xc) PRIME sur _abilityState @0x4c.
export const abStateOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "_abilityState") : -1;
export const abOverrideStateOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "OverrideAbilityState") : -1;
// #433-r4-r2-r1-r1-c-r1 — le TOUR DE DERNIÈRE UTILISATION, seul champ de la marche (f) de
// `IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason` qu'AUCUN canal ne publiait.
// Le foyer natif est `IdunBattle.Core.Services.AttackQuery$$IsAlreadyUsedThisTurn(this,
// activeAbilityType, activeAbility)`, lu verbatim sur `rnca9r7q6c` :
//
//   if (this.<+0x10> != 0)                             -> false        // court-circuit
//   if (StaticBattleRules.ActiveAbility.IsRegularAbilityType(type))   -> false
//   if (!activeAbility.<Nullable @+0x20>.HasValue)     -> false
//   turnsEnded = TurnComponent.GetAmountOfTurnsEnded(StateExtensions.GetMatchTurn(this.<+0x20>), 0)
//   return hasValue && (value == turnsEnded)
//
// ⚠ Le sens de la 2ᵉ marche : le natif rend `false` quand le type EST une attaque régulière
// (`if ((char)IsRegularAbilityType(...) == '\0')` garde le corps) — une attaque normale n'est
// donc jamais « déjà utilisée ce tour ». Lu, pas déduit du nom.
//
// Le champ `@+0x20` est `UnresetedLastTurnUsed` — nom MESURÉ au runtime (métadonnées IL2CPP,
// `classFields("IdunBattle.Entities.Components", "ActiveAbility")` sur `rnca9r7q6c`), pas
// inféré : son voisin `LastTurnUsed` @+0x18 est un AUTRE `Nullable<int>` du même composant, et
// choisir à l'oeil entre les deux aurait été un coup de dé. Les deux sont donc publiés, pour
// que la fenêtre puisse CONFRONTER lequel le natif lit plutôt que me croire sur parole.
//
// Résolution par NOM et AUCUN repli littéral (contraste voulu avec `fieldOffsetOr`) : un nom
// absent au prochain build doit rendre « pas mesuré », jamais la lecture d'un offset devenu
// celui d'un autre champ. Le layout observé est publié par `abilityStateLayout()`.
export const abLastTurnUsedOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "LastTurnUsed") : -1;
export const abUnresetedLastTurnUsedOff = componentsActiveAbilityClass
    ? getFieldOffset(componentsActiveAbilityClass, "UnresetedLastTurnUsed") : -1;

/** La disposition INTERNE du `Nullable<T>` d'un champ, RÉSOLUE PAR RÉFLEXION — jamais
 *  supposée : `champ -> type -> classe Nullable`1 -> offsets de ses champs `hasValue`/`value``.
 *  C'est déjà le patron de `game/match-state.ts` pour `UnitComponent.DeathReason`.
 *
 *  ⚠ **EXPORTÉ (#347-r3) — FOYER UNIQUE, et il l'est devenu parce qu'une COPIE avait repoussé.**
 *  Le capteur de mouvement d'`actorStats` (`rpc-snapshot.ts`) supposait `hasValue` à `+8` et
 *  sortait `tiles: null` sur ses quatre champs à la fenêtre du 2026-08-08 ; sa première
 *  réparation ré-écrivait ICI, en local, la même résolution par réflexion. Deux exemplaires de
 *  la même parade, c'est le patron que `case-287-r12` a déjà eu à défaire en TROIS exemplaires.
 *  Tout nouveau lecteur de `Nullable<T>` consomme CETTE fonction.
 *
 *  ⚠ `il2cpp_field_get_offset` sur un VALUE TYPE rend l'offset BOXÉ (header 0x10 inclus) →
 *  on soustrait `0x10` pour l'offset INLINE dans la struct.
 *
 *  `null` = disposition non résolue → l'appelant répond « PAS MESURÉ », jamais une lecture
 *  à une convention devinée. */
export function nullableLayoutOf(klass: NativePointer | null, fieldName: string): {
    hasValueOff: number; valueOff: number;
} | null {
    if (!klass) return null;
    const f = getFieldInfo(klass, fieldName);
    if (!f) return null;
    try {
        const k = type_get_class_or_element_class(
            field_get_type(f) as NativePointer) as NativePointer;
        if (k.isNull()) return null;
        const hv = (getFieldOffset(k, "hasValue") as number) - 0x10;
        const v = (getFieldOffset(k, "value") as number) - 0x10;
        if (hv < 0 || v < 0) return null;
        return { hasValueOff: hv, valueOff: v };
    } catch { return null; }
}

// Les quatre `Nullable<int>` de `IdunBattle.Entities.Components.ActiveAbility` partagent la
// MÊME instanciation, donc la même disposition ; on la résout par champ quand même, pour
// qu'un champ dont le type changerait ne soit pas lu à la disposition d'un voisin.
const nlLastTurnUsed = nullableLayoutOf(componentsActiveAbilityClass, "LastTurnUsed");
const nlUnresetedLastTurnUsed = nullableLayoutOf(
    componentsActiveAbilityClass, "UnresetedLastTurnUsed");
const nlCooldown = nullableLayoutOf(componentsActiveAbilityClass, "RemainingCooldownTurns");
const nlAmmoCost = nullableLayoutOf(componentsActiveAbilityClass, "AmmoCost");
const nlOverrideState = nullableLayoutOf(componentsActiveAbilityClass, "OverrideAbilityState");

/** `Nullable<int>` d'IL2CPP lu en TRI-ÉTAT : `{ value, hasValue }` où `hasValue === null`
 *  signifie **PAS MESURÉ** (offset du champ non résolu, disposition du Nullable non résolue,
 *  ou lecture en faute) — distinct de `hasValue === false`, qui est une MESURE (Nullable vide).
 *
 *  ## La disposition n'est PAS `{ value, hasValue }` — c'est MESURÉ (#579-r1)
 *
 *  Ce foyer lisait `hasValue` à `+4` et `value` à `+0`. **Faux** : `System.Nullable`1` déclare
 *  `hasValue` PUIS `value`, donc `{ bool hasValue @+0 (+3 de bourrage) ; T value @+4 }`.
 *  Trois lectures concordantes :
 *
 *  1. **LIVE, discriminante** — deux casts dans la MÊME bataille, à `GetAmountOfTurnsEnded`
 *     = **6** puis **19** : le capteur publiait `unresetedLastTurnUsed = 1` **aux deux**.
 *     Or `IdunBattle.Operations.SetActiveAbilityUsedOperation$$Execute` et
 *     `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` écrivent tous deux
 *     `Nullable(TurnComponent.GetAmountOfTurnsEnded(GetMatchTurn(state), 0))` dans
 *     `LastTurnUsed@+0x18` ET `UnresetedLastTurnUsed@+0x20`, et
 *     `IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEnded` =
 *     `Sum(dict@+0x40.Values) + turnsToAdd` est monotone : les deux valeurs stockées NE
 *     PEUVENT PAS être toutes deux `1`. Le `1` publié était le bit `hasValue`.
 *  2. **Métadonnées IL2CPP** — `classFields("System", "Nullable`1")` rend l'ordre de
 *     déclaration `hasValue` puis `value`.
 *  3. **Décompilé** — `IdunBattle.Core.Services.AttackQuery$$IsAlreadyUsedThisTurn` prend
 *     l'octet lu comme `HasValue` sur `fields[0]` et l'int comparé au compteur sur
 *     `fields[0] + 0x20` (= `fields[1]`, `sizeof(FieldInfo)`) ; idem
 *     `IdunBattle.Entities.Components.ActiveAbility$$get_IsInCooldown`, dont l'octet
 *     `HasValue` sort de `fields[0]`.
 *
 *  Le reste du dépôt documentait déjà `hasValue @+0` (`game/match-state.ts`,
 *  `features/battle-config.ts`, `features/mow-builder.ts`, `features/normalize-bc/formula.ts`,
 *  `features/ai-step/rpc-snapshot.ts`) ; ce foyer-ci était le seul à l'inverse, et
 *  `features/effect-bonus-trace.ts` NOMMAIT la contradiction sans la trancher. */
function readNullableInt(base: NativePointer, off: number,
                         layout: { hasValueOff: number; valueOff: number } | null): {
    value: number | null; hasValue: boolean | null;
} {
    if (off < 0 || !layout) return { value: null, hasValue: null };
    try {
        const has = base.add(off + layout.hasValueOff).readU8() !== 0;
        return { value: has ? base.add(off + layout.valueOff).readS32() : null, hasValue: has };
    } catch { return { value: null, hasValue: null }; }
}

/** Lit l'état castable d'un objet components.ActiveAbility (élément de GetActives).
 *  `cooldown`=null si Nullable sans valeur (= prêt). Tous champs best-effort. */
export function readAbilityState(ab: NativePointer): {
    usable?: boolean; cooldown?: number | null; disabled?: boolean;
    ammoCost?: number | null; hasAmmo?: boolean;
    level?: number; multiplier?: number;
    lastTurnUsed?: number | null; lastTurnUsedHasValue?: boolean | null;
    unresetedLastTurnUsed?: number | null;
    unresetedLastTurnUsedHasValue?: boolean | null;
} {
    const st: {
        usable?: boolean; cooldown?: number | null; disabled?: boolean;
        ammoCost?: number | null; hasAmmo?: boolean;
        level?: number; multiplier?: number;
        lastTurnUsed?: number | null; lastTurnUsedHasValue?: boolean | null;
        unresetedLastTurnUsed?: number | null;
        unresetedLastTurnUsedHasValue?: boolean | null;
    } = {};
    // #433-r4-r2-r1-r1-c-r1 — les DEUX `Nullable<int>` de tour, en tri-état, lus AVANT le `try`
    // qui suit. Ce n'est pas un détail de placement : `readNullableInt` ne lève jamais (il porte
    // sa propre garde), donc les quatre clés existent TOUJOURS dans la réponse — alors qu'une
    // faute sur une lecture ANTÉRIEURE, à l'intérieur du `try`, les ferait disparaître. Une clé
    // ABSENTE et une clé à `null` se lisent pareil de loin, mais la première ne dit pas si le
    // capteur a seulement essayé. On publie la valeur BRUTE et son `hasValue`, jamais un booléen
    // pré-calculé : la comparaison au compteur (`turnsEnded`, au niveau réponse) appartient au
    // moteur, qui doit pouvoir la refaire à l'identique du natif — marche `IsRegularAbilityType`
    // comprise, et elle n'est pas dans ce champ.
    const lastTurn = readNullableInt(ab, abLastTurnUsedOff, nlLastTurnUsed);
    st.lastTurnUsed = lastTurn.value;
    st.lastTurnUsedHasValue = lastTurn.hasValue;
    const unreseted = readNullableInt(ab, abUnresetedLastTurnUsedOff, nlUnresetedLastTurnUsed);
    st.unresetedLastTurnUsed = unreseted.value;
    st.unresetedLastTurnUsedHasValue = unreseted.hasValue;
    try {
        if (abCanUseOff >= 0) st.usable = ab.add(abCanUseOff).readU8() !== 0;
        // ⚠ MÊME disposition que ci-dessus, et c'est le point du correctif #579-r1 : ces deux
        // Nullable étaient lus à l'envers depuis toujours. Conséquence MESURABLE côté port —
        // `cooldown` valait `1` pour TOUT cooldown non nul (c'est le bit `hasValue` qui
        // sortait), donc `engine/runner/operations/ability_reset.py` (`remaining_cooldown > 1`,
        // mirror d'`EntityCanHaveActiveAbilityReset`) ne pouvait JAMAIS être vrai.
        // Les prédicats de PRÉSENCE, eux, coïncidaient par accident : `value & 0xff != 0`
        // équivaut à `HasValue && Value > 0` (= `ActiveAbility$$get_IsInCooldown`) tant que la
        // valeur tient sur un octet non nul.
        const cd = readNullableInt(ab, abCooldownOff, nlCooldown);
        if (cd.hasValue !== null) st.cooldown = cd.value;
        if (abDisabledOff >= 0) st.disabled = ab.add(abDisabledOff).readU8() !== 0;
        const ammo = readNullableInt(ab, abAmmoCostOff, nlAmmoCost);
        if (ammo.hasValue !== null) st.ammoCost = ammo.value;
        if (abHasAmmoOff >= 0) st.hasAmmo = ab.add(abHasAmmoOff).readU8() !== 0;
        // niveau/mult PER-ABILITY (#100) — mirror get_AbilityState @180f8fc40 (Override prime).
        // Le `HasValue` du `Nullable<AbilityState>` est lui aussi résolu par réflexion : le
        // `+0xc` codé ici supposait la disposition `{ AbilityState value @+0 ; bool hasValue
        // @+0xc }`, symétrique de celle qu'on vient de réfuter. Disposition non résolue =>
        // on ne teste pas l'override (repli sur `_abilityState`, comportement d'avant #100).
        let stOff = -1;
        if (abOverrideStateOff >= 0 && nlOverrideState
            && ab.add(abOverrideStateOff + nlOverrideState.hasValueOff).readU8() !== 0) {
            stOff = abOverrideStateOff + nlOverrideState.valueOff;
        } else if (abStateOff >= 0) stOff = abStateOff;
        if (stOff >= 0) {
            st.level = ab.add(stOff).readS32();          // AbilityState.Level @+0 (Idun.Shared.Level = int)
            st.multiplier = ab.add(stOff + 4).readS32(); // .VariableMultiplierPercentage @+4
        }
    } catch { /* */ }
    return st;
}

/** La DISPOSITION observée de `IdunBattle.Entities.Components.ActiveAbility` — ce que
 *  `readAbilityState` a réellement résolu, publié tel quel.
 *
 *  Pourquoi un capteur publie son propre layout (#279, #448-r1-r1-r1-r1) : un offset résolu par
 *  nom est juste ou ABSENT, jamais approximatif — mais le lecteur, lui, ne peut pas distinguer
 *  « champ lu à 0x20 » de « champ non trouvé, valeur nulle » sans qu'on le lui dise. Les
 *  littéraux `decompiled*` sont ceux LUS dans
 *  `IdunBattle.Core.Services.AttackQuery$$IsAlreadyUsedThisTurn` (`+0x20`) et dans la
 *  disposition mesurée du build `rnca9r7q6c` : ils ne sont JAMAIS utilisés pour lire, seulement
 *  pour qu'un désaccord saute aux yeux. */
export function abilityStateLayout(): Record<string, unknown> {
    return {
        classResolved: !!componentsActiveAbilityClass,
        canStillBeUsed: abCanUseOff, remainingCooldownTurns: abCooldownOff,
        isDisabled: abDisabledOff, ammoCost: abAmmoCostOff, hasEnoughAmmo: abHasAmmoOff,
        abilityName: abilityNameOff, abilityState: abStateOff,
        overrideAbilityState: abOverrideStateOff,
        lastTurnUsed: abLastTurnUsedOff,
        unresetedLastTurnUsed: abUnresetedLastTurnUsedOff,
        decompiledUnresetedLastTurnUsed: 0x20,   // lu dans `AttackQuery$$IsAlreadyUsedThisTurn`
        decompiledLastTurnUsed: 0x18,            // voisin, disposition mesurée `rnca9r7q6c`
        // #579-r1 — la disposition INTERNE des Nullable, RÉSOLUE (jamais supposée). `null` =
        // non résolue => les champs correspondants sortent en « PAS MESURÉ ». Publiée parce
        // que c'est exactement ce qu'un lecteur ne peut pas deviner, et parce que l'ancienne
        // convention (inverse) a produit un capteur vert qui publiait le bit `hasValue` à la
        // place du tour.
        nullableLayout: {
            lastTurnUsed: nlLastTurnUsed, unresetedLastTurnUsed: nlUnresetedLastTurnUsed,
            remainingCooldownTurns: nlCooldown, ammoCost: nlAmmoCost,
            overrideAbilityState: nlOverrideState,
        },
    };
}

// --- Compteur de tours ÉCOULÉS — l'autre moitié de `IsAlreadyUsedThisTurn` (#433-r4-r2-r1-r1-c-r1)
//
// `IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEnded(this, turnsToAdd)` =
// `Sum(this.<Dictionary @+0x40>.Values) + turnsToAdd`. C'est CE compteur — et pas le `turn`
// déjà publié, qui est `GetAmountOfTurnsStartedByCurrentPlayer` (cf. `game/match-state.ts`) —
// que le natif compare à `ActiveAbility.UnresetedLastTurnUsed`. Publier le champ SANS lui
// laisserait la question indécidable côté moteur : les deux grandeurs ne coïncident pas.
//
// On INVOQUE la méthode nommée plutôt que de refaire la somme : la sémantique reste celle du
// natif même si le dictionnaire change de forme.
export const turnComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "TurnComponent");
export const getAmountOfTurnsEndedMi = turnComponentClass
    ? findMethodByParamCount(turnComponentClass, "GetAmountOfTurnsEnded", 1) : null;

/** Le `TurnComponent` du state — mirror de `IdunBattle.Entities.StateExtensions$$GetMatchTurn`,
 *  qui est un `GetFirstWithComponent<TurnComponent>` : PREMIÈRE entité qui porte ce composant,
 *  quel que soit son `EntityType` (on ne présuppose donc pas l'entité `Match`). */
export function findTurnComponent(statePtr: NativePointer): NativePointer | null {
    if (!turnComponentClass) return null;
    let found = ptr(0);          // sentinelle plutôt que `null` — même idiome que getAbilityComponent
    try {
        forEachEntity(statePtr, (e) => {
            if (!found.isNull()) return;
            forEachComponent(e, (comp, klass) => {
                if (found.isNull() && klass.equals(turnComponentClass!)) found = comp;
            });
        });
    } catch { /* walk partiel */ }
    return found.isNull() ? null : found;
}

/** `TurnComponent.GetAmountOfTurnsEnded(0)` sur le state, ou `null` = PAS MESURÉ (classe ou
 *  méthode non résolue, aucune entité porteuse, invoke en faute). Jamais `0` par défaut : `0`
 *  est une valeur LÉGITIME du domaine (premier tour), et la confondre avec une panne de lecture
 *  ferait répondre « cette ability a été utilisée ce tour » à toute ability dont le Nullable
 *  vaut 0. Même discipline qu'`invokeInt`. */
export function readTurnsEnded(statePtr: NativePointer): number | null {
    if (!getAmountOfTurnsEndedMi) return null;
    const tc = findTurnComponent(statePtr);
    if (tc === null) return null;
    // 8 octets à ZÉRO : couvre `int turnsToAdd` (les 4 premiers) comme un éventuel
    // `Nullable<int>` (HasValue=0 → GetValueOrDefault=0). Le type réel du paramètre est
    // publié tel quel par `turnsEndedLayout()` — on ne le devine pas, on le montre.
    const arg = Memory.alloc(8); arg.writeU64(0);
    try {
        const r = invokeMethod(getAmountOfTurnsEndedMi.info, tc, [arg]);
        return r.isNull() ? null : r.add(0x10).readS32();
    } catch { return null; }
}

/** Ce que le capteur a résolu pour le compteur de tours — même rôle qu'`abilityStateLayout`. */
export function turnsEndedLayout(): Record<string, unknown> {
    return {
        classResolved: !!turnComponentClass,
        methodResolved: !!getAmountOfTurnsEndedMi,
        paramClass: getAmountOfTurnsEndedMi
            ? methodParamClassName(getAmountOfTurnsEndedMi.info, 0) : null,
    };
}

// EntityExtensions.GetMainTile(entity, state) → la tile courante de l'unité
// (GetMovableTilesFor exclut la tile d'origine ; on l'ajoute au set candidat
// pour que « rester sur place et attaquer » soit rankée).
// R1 : cet ajout est FIDÈLE, pas une commodité d'outillage — le tactic natif fait
// exactement le même geste. ABaseAiUnitTactic$$GenerateActionTiles appelle
// IBattleQuery+0xe = BattleQuery$$GetCurrentAndMovablePositionsFor, qui SEEDE son
// OrderedSet avec GetUnitPosition(unit) puis UnionWith(GetMovablePositionsFor(...)).
// Côté natif la position courante est donc candidate ET PREMIÈRE de l'énumération
// (tie-break Bucket keep-first). cf. docs/rl/case-r1-origin-action-tile.md.
export const entityExtClass = findClassAnywhere("IdunBattle.Entities", "EntityExtensions");
export const getMainTileMi = entityExtClass
    ? findMethodByParamCount(entityExtClass, "GetMainTile", 2) : null;
// EntityExtensions.GetTiles(entity, state) → IList<IEntity> du footprint courant
// (multi-tuiles MoW gérées). Sert à fabriquer un UnitPosition value {Tiles=…} sans
// passer par son ctor ambigu — pour `GetValidTargets(unit, UnitPosition, ability)`
// « depuis la tuile courante, sans bouger » (cf. abilityTargets.fromHere).
export const getTilesMi = entityExtClass
    ? findMethodByParamCount(entityExtClass, "GetTiles", 2) : null;

// #26 — filtres RESTANTS de `MovementActionGenerator.<FindClosestEnemy>d__8.MoveNext @181197f10`
// (ordre natif : skip si CurrentOwnerIsEnvironment / !IsTargetable / IsIrrelevantObject / IsDead,
// puis restriction aux `GetOnlyTargets` si la liste est non vide) :
//   `EntityExtensions.CurrentOwnerIsEnvironment @180eb4d00` = GetCurrentPlayer(e,state).Owner.Type==2
//     (unité possédée par le joueur Environment/neutre) ;
//   `UnitExtensions.IsIrrelevantObject @180ed86d0` = trait 27, ou trait 13 avec stat0 <= 0 (décor) ;
//   `UnitExtensions.GetOnlyTargets @180ed1b10` = List<int> d'ids de cibles FORCÉES (taunt/forced-target,
//     champ +0x50 du composant ; pas de composant OU OwnerComponent.IsOverridden → liste vide).
// Tous invoqués NATIFS (aucune sémantique portée côté hooks). Consommés par pathDistToEnemies
// (rpc-board.ts) ; guardés null (méthode non résolue => pas de filtre, dégradation sûre).
export const currentOwnerIsEnvMi = entityExtClass
    ? findMethodByParamCount(entityExtClass, "CurrentOwnerIsEnvironment", 2) : null;
export const isIrrelevantObjMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "IsIrrelevantObject", 1) : null;
export const getOnlyTargetsMi = unitExtClass
    ? findMethodByParamCount(unitExtClass, "GetOnlyTargets", 1) : null;

/** Invoque une méthode statique retournant bool (résultat boxé : valeur @0x10). */
export function invokeBool(
    mi: { info: NativePointer } | null, args: NativePointer[],
): boolean {
    if (!mi) return false;
    try {
        const r = invokeMethod(mi.info, null, args);
        return !r.isNull() && r.add(0x10).readU8() !== 0;
    } catch { return false; }
}

/** Invoque une méthode statique retournant bool, EN TRI-ÉTAT : `null` — PAS `false` — quand la
 *  méthode est irrésolue ou l'appel échoue. Pendant exact d'`invokeInt` sur l'axe booléen.
 *
 *  POURQUOI CE JUMEAU EXISTE, alors qu'`invokeBool` répond déjà (#969-r4). Les deux formes ne
 *  sont pas interchangeables, et le régime décide. `invokeBool` sert des filtres où le repli
 *  `false` est une DÉGRADATION SÛRE et assumée (`pathDistToEnemies` : méthode non résolue ⇒ pas
 *  de filtre). Un CANAL PUBLIÉ, lui, n'a pas ce luxe : `CurrentOwnerIsEnvironment` est FAUX pour
 *  la quasi-totalité des unités, donc un capteur en panne qui rendrait `false` serait d'accord
 *  avec le natif PARTOUT — sauf exactement dans le régime qu'il existe pour mesurer. Le
 *  rabattement serait invisible, et c'est la définition même de la panne indiscernable d'une
 *  mesure (même argument que le `0` de `turnsFinished`, que le `0` de `Rarity.Common` en #1039,
 *  et que le `0` = « niveau verrouillé » en #1036-r8). */
export function invokeBoolOrNull(
    mi: { info: NativePointer } | null, args: NativePointer[],
): boolean | null {
    if (!mi) return null;
    try {
        const r = invokeMethod(mi.info, null, args);
        return r.isNull() ? null : r.add(0x10).readU8() !== 0;
    } catch { return null; }
}

/** Invoque une méthode statique retournant Int32 (résultat boxé : valeur @0x10, comme le bool).
 *  Rend `null` — PAS 0 — quand la méthode est irrésolue ou l'appel échoue : un 0 muet se lirait
 *  comme « cette unité n'a fini aucun tour », ce qui est une VALEUR LÉGITIME du domaine. Le
 *  consommateur doit pouvoir distinguer « mesuré à 0 » de « pas mesuré ». */
export function invokeInt(
    mi: { info: NativePointer } | null, args: NativePointer[],
): number | null {
    if (!mi) return null;
    try {
        const r = invokeMethod(mi.info, null, args);
        return r.isNull() ? null : r.add(0x10).readS32();
    } catch { return null; }
}

// Champs des IInputMessage (offsets validés sur le dump kqkbjqfb6c).
export const MSG_OFF = {
    moveUnitId: 0x10,       // MoveUnitMessage.UnitId (BEntityId)
    moveFeet: 0x18,         // MoveUnitMessage.UnitFeetPositions (List<Position>)
    abilCaster: 0x10,       // ActiveAbilityMessage.CasterId
    abilTarget: 0x14,       // ActiveAbilityMessage.TargetId
    abilType: 0x18,         // ActiveAbilityMessage.ActiveAbilityType (enum int)
    finishUnitId: 0x10,     // FinishUnitTurnMessage.UnitId
} as const;

// List<T> IL2CPP : _items @0x10, _size @0x18, données du tableau dès +0x20.
export const LIST_ITEMS = 0x10;
export const LIST_SIZE = 0x18;
export const ARRAY_FIRST = 0x20;
// Position : value-type 8 octets { Column:int@0, Row:int@4 }.
export const POS_STRIDE = 8;

// --- Construction de messages (applyAction : appliquer MON coup) ---
// Classes IInputMessage que je construis from scratch (il2cpp_object_new + ctor
// 0-arg + écriture des champs), puis applique via AiControl.ApplyAiMessage —
// le MÊME chemin prouvé que les messages générés par l'IA (cf. aiPlayByUnit).
//   MoveUnitMessage     : UnitId@0x10, UnitFeetPositions@0x18 (List<Position>),
//                         SkipFlags@0x20. UnitFeetPositions = FOOTPRINT de
//                         destination (get_To = feet[0]), PAS le chemin —
//                         le moteur recalcule le trajet + l'overwatch.
//   ActiveAbilityMessage: CasterId@0x10, TargetId@0x14, ActiveAbilityType@0x18,
//                         SkipFlags@0x1C. Pas de position → bouger AVANT si
//                         besoin. Les MoW ne bougent pas → ability seule.
//   FinishUnitTurnMessage: UnitId@0x10.
export const moveUnitMsgClass = findClassAnywhere("IdunBattle.Messages", "MoveUnitMessage");
export const activeAbilityMsgClass = findClassAnywhere(
    "IdunBattle.Messages", "ActiveAbilityMessage");
export const finishUnitTurnMsgClass = findClassAnywhere(
    "IdunBattle.Messages", "FinishUnitTurnMessage");

/** Classe d'un champ (par nom) — sert à récupérer le type inflé List<Position>
 *  du champ UnitFeetPositions (instanciation générique, non trouvable par nom). */
export function fieldClass(klass: NativePointer, fieldName: string): NativePointer {
    const it = Memory.alloc(Process.pointerSize); it.writePointer(ptr(0));
    let f: NativePointer;
    while (!(f = class_get_fields(klass, it) as NativePointer).isNull()) {
        if (s(field_get_name(f) as NativePointer) === fieldName) {
            try {
                return type_get_class_or_element_class(
                    field_get_type(f) as NativePointer) as NativePointer;
            } catch { return ptr(0); }
        }
    }
    return ptr(0);
}
export const listPositionClass = moveUnitMsgClass
    ? fieldClass(moveUnitMsgClass, "UnitFeetPositions") : ptr(0);
export const listPositionCtor = (listPositionClass && !listPositionClass.isNull())
    ? findCtorByParamCount(listPositionClass, 0) : null;
export const listPositionAddMi = (listPositionClass && !listPositionClass.isNull())
    ? findMethodByParamCount(listPositionClass, "Add", 1) : null;
export const moveCtor0 = moveUnitMsgClass ? findCtorByParamCount(moveUnitMsgClass, 0) : null;
export const abilityCtor0 = activeAbilityMsgClass
    ? findCtorByParamCount(activeAbilityMsgClass, 0) : null;
export const finishCtor0 = finishUnitTurnMsgClass
    ? findCtorByParamCount(finishUnitTurnMsgClass, 0) : null;

/** Construit une List<Position> peuplée des tiles `feet` (footprint). */
export function buildPositionList(
    feet: Array<{ col: number; row: number }>,
): NativePointer {
    if (!listPositionClass || listPositionClass.isNull() || !listPositionAddMi) {
        return ptr(0);
    }
    const list = il2cpp_object_new(listPositionClass) as NativePointer;
    if (list.isNull()) return ptr(0);
    if (listPositionCtor) invokeMethod(listPositionCtor.info, list, null);
    for (const f of feet) {
        const pos = Memory.alloc(POS_STRIDE);
        pos.writeS32(f.col); pos.add(4).writeS32(f.row);
        invokeMethod(listPositionAddMi.info, list, [pos]);  // Position by-value (ptr)
    }
    return list;
}

/** MoveUnitMessage(unitId, feet). feet = footprint destination (1 tile pour les
 *  unités mono-tile). */
export function buildMoveMsg(
    unitId: number, feet: Array<{ col: number; row: number }>,
): NativePointer {
    if (!moveUnitMsgClass) return ptr(0);
    const msg = il2cpp_object_new(moveUnitMsgClass) as NativePointer;
    if (msg.isNull()) return ptr(0);
    if (moveCtor0) invokeMethod(moveCtor0.info, msg, null);
    const list = buildPositionList(feet);
    if (list.isNull()) return ptr(0);
    gcRoot.add(list);
    msg.add(MSG_OFF.moveUnitId).writeS32(unitId);      // BEntityId = int
    msg.add(MSG_OFF.moveFeet).writePointer(list);      // List<Position>
    msg.add(0x20).writeU8(0);                          // SkipFlags = false
    return msg;
}

/** ActiveAbilityMessage(caster, target, abilityType). Validation complète
 *  (SkipFlags=false) → fidèle (portée/action/overwatch jugés par le moteur). */
export function buildAbilityMsg(
    casterId: number, targetId: number, abilityType: number,
): NativePointer {
    if (!activeAbilityMsgClass) return ptr(0);
    const msg = il2cpp_object_new(activeAbilityMsgClass) as NativePointer;
    if (msg.isNull()) return ptr(0);
    if (abilityCtor0) invokeMethod(abilityCtor0.info, msg, null);
    msg.add(MSG_OFF.abilCaster).writeS32(casterId);
    msg.add(MSG_OFF.abilTarget).writeS32(targetId);
    msg.add(MSG_OFF.abilType).writeS32(abilityType);
    msg.add(0x1c).writeU8(0);   // SkipFlags = false (0x1D/0x1E/0x20 → défaut ctor)
    return msg;
}

/** FinishUnitTurnMessage(unitId) — termine explicitement l'activation. */
export function buildFinishMsg(unitId: number): NativePointer {
    if (!finishUnitTurnMsgClass) return ptr(0);
    const msg = il2cpp_object_new(finishUnitTurnMsgClass) as NativePointer;
    if (msg.isNull()) return ptr(0);
    if (finishCtor0) invokeMethod(finishCtor0.info, msg, null);
    msg.add(MSG_OFF.finishUnitId).writeS32(unitId);
    return msg;
}

export interface ActionSpec {
    /** PAS de kind `attack` — et c'est voulu : l'attaque normale est une ability
     *  comme les autres, dont l'`ActiveAbilityType` est PER-UNIT (`NormalAttackType`,
     *  ex. 69). Un kind `attack` dédié ferait deux façons d'exprimer la même chose et
     *  masquerait quelle ability a réellement tiré — or ce type concret est une donnée
     *  qui porte (cf. mémoire `ability_normal_attack_concrete`). Le refus est LEVÉ
     *  (cf. `applyOneAction`), pas rendu. */
    kind: "move" | "ability" | "finish" | "endturn";
    unitId?: number;
    to?: { col: number; row: number };
    feet?: Array<{ col: number; row: number }>;
    casterId?: number;
    targetId?: number;
    abilityType?: number;
}

export interface UnitChange {
    squadId: number;
    from?: { col: number; row: number } | null;
    to?: { col: number; row: number } | null;
    moved?: boolean;
    hpBefore?: number | null;
    hpAfter?: number | null;
    hpDelta?: number;
    killed?: boolean;
    appeared?: boolean;
}

/** Diff de deux summaries : units déplacées / blessées / tuées / apparues. */
export function diffUnits(before: StateSummary, after: StateSummary): UnitChange[] {
    const bById = new Map(before.units.map((u) => [u.squadId, u]));
    const changes: UnitChange[] = [];
    const posKey = (p: { col: number; row: number } | null) =>
        p ? p.col + "," + p.row : "x";
    const afterIds = new Set<number>();
    for (const a of after.units) {
        afterIds.add(a.squadId);
        const b = bById.get(a.squadId);
        if (!b) {
            changes.push({ squadId: a.squadId, appeared: true, to: a.pos, hpAfter: a.hp });
            continue;
        }
        const moved = posKey(b.pos) !== posKey(a.pos);
        const hpDelta = (a.hp ?? 0) - (b.hp ?? 0);
        if (moved || hpDelta !== 0) {
            changes.push({
                squadId: a.squadId, from: b.pos, to: a.pos, moved,
                hpBefore: b.hp, hpAfter: a.hp, hpDelta,
            });
        }
    }
    for (const b of before.units) {
        if (!afterIds.has(b.squadId)) {
            changes.push({ squadId: b.squadId, killed: true, hpBefore: b.hp });
        }
    }
    return changes;
}

export interface ActionResult {
    kind: string;
    ok: boolean;
    error: string | null;
    mutated: boolean;
    changes: UnitChange[];
    /** Cascade StreamDispatcher capturée pendant l'apply (UnitDamaged,
     *  ReceiveEffect, groups…) — révèle l'overwatch / DoT / crit qu'un simple
     *  diff HP confond. tags = Dict<TagKey,int> JSON (Effect_Type, dégâts…). */
    events: StreamEvent[];
    eventCount: number;
    stage: number | null;
    currentPlayer: number | null;
    /** ABILITY uniquement (absent sinon) — détection du NO-OP moteur silencieux
     *  (TF12). `actionConsumed` = le cast a-t-il consommé l'activation du caster
     *  (HasActionLeft true→false) ; `spawned` = nb d'entités apparues (summon).
     *  Un cast `ok=true` qui n'a PAS consommé l'action (`actionConsumed=false`)
     *  est un no-op moteur : ex. Abraxas `MasterOfTheTutelaries` émet un event
     *  `User_UseAbility` (donc `eventCount>=1`, le filet `eventCount==0` le rate)
     *  mais ne summon RIEN et laisse Abraxas « à activer ». null = état d'action
     *  inconnu (caster introuvable / HasActionLeft non résolu). */
    spawned?: number;
    actionConsumed?: boolean | null;
}

/** ptr d'une entité par squadId courant (ou ptr(0)) — lookup ponctuel pour lire
 *  HasActionLeft du caster avant/après un apply (les ptrs managés peuvent bouger
 *  au GC → re-résoudre par id de part et d'autre de l'invoke). */
function findEntityById(statePtr: NativePointer, id: number): NativePointer {
    let found = ptr(0);
    forEachEntity(statePtr, (e, eid) => {
        if (found.isNull() && eid === id) found = e;
    });
    return found;
}

/** HasActionLeft du caster (true/false) ou null si non lisible. */
function readHasAction(statePtr: NativePointer, casterId: number | undefined): boolean | null {
    if (casterId === undefined || !hasActionLeftMi) return null;
    const p = findEntityById(statePtr, casterId);
    if (p.isNull()) return null;
    try { return invokeBool(hasActionLeftMi, [p]); } catch { return null; }
}

/** Construit + applique UNE action via ApplyAiMessage, en snapshotant l'état
 *  AVANT/APRÈS → diff observable. Coeur de la décomposition « 2 temps » :
 *  un appel = une action, on observe, puis on décide la suivante. */
export function applyOneAction(
    runner: NativePointer, aiControl: NativePointer, action: ActionSpec,
): ActionResult {
    let msg: NativePointer = ptr(0);
    let buildErr: string | null = null;
    try {
        if (action.kind === "move") {
            const feet = action.feet ?? (action.to ? [action.to] : []);
            if (!feet.length || action.unitId === undefined) {
                buildErr = "move: need unitId + to/feet";
            } else { msg = buildMoveMsg(action.unitId, feet); }
        } else if (action.kind === "ability") {
            // Cible = entité (targetId) OU hex libre (to → entité-tuile).
            let tgt = action.targetId;
            if (tgt === undefined && action.to) {
                const sp = runner.add(runnerOff.state).readPointer();
                const tid = findTileEntityId(sp, action.to.col, action.to.row);
                if (tid < 0) {
                    buildErr = "ability: no tile entity at "
                        + action.to.col + "," + action.to.row;
                } else { tgt = tid; }
            }
            if (action.casterId === undefined || tgt === undefined
                || action.abilityType === undefined) {
                buildErr = "ability: need casterId + (targetId|to) + abilityType";
            } else {
                msg = buildAbilityMsg(action.casterId, tgt, action.abilityType);
            }
        } else if (action.kind === "finish") {
            if (action.unitId === undefined) buildErr = "finish: need unitId";
            else msg = buildFinishMsg(action.unitId);
        } else if (action.kind === "endturn") {
            if (!endTurnClass) buildErr = "endturn: EndTurnMessage class missing";
            else {
                msg = il2cpp_object_new(endTurnClass) as NativePointer;
                if (!msg.isNull() && endTurnCtor) {
                    invokeMethod(endTurnCtor.info, msg, null);
                }
            }
        } else {
            buildErr = "kind inconnu: " + action.kind
                + " (valides: move | ability | finish | endturn)"
                // L'attaque normale N'EST PAS un kind : c'est une ability dont le
                // type est PER-UNIT (NormalAttackType, ex. 69 — PAS 17, qui est le
                // type de la FAMILLE). D'où ce rappel dans le message : les deux
                // agents de #263 ont écrit {kind:"attack"} et lu le refus comme une
                // mesure. Le message doit apprendre le chemin, pas juste refuser.
                // ASCII dans le MESSAGE : il finit dans les `print` des sondes
                // Python, dont la console Windows est en cp1252.
                + ((action.kind as string) === "attack"
                    ? " -- l'attaque normale EST une ability : {kind:\"ability\","
                      + " casterId, targetId, abilityType:<NormalAttackType de"
                      + " l'unite>}"
                    : "");
        }
    } catch (e) { buildErr = "build: " + (e as Error).message; }

    // ⚠ ON LÈVE — on ne rend PAS `ok:false`. Un échec de CONSTRUCTION veut dire que
    // le moteur n'a JAMAIS vu le message : il n'y a RIEN à mesurer. Rendu en valeur
    // de retour, il se lit comme « l'action n'a rien fait » — c'est-à-dire comme un
    // RÉSULTAT. Le 2026-07-29, deux agents indépendants (#263) y ont perdu leurs
    // mesures : 13 attaques jamais émises pour l'un, un « l'ennemi n'inflige aucun
    // dégât » pour l'autre alors que l'ennemi n'attaquait pas du tout. Aucun des
    // ~250 montages Python ne lit `ok` — la levée remonte en HTTP 500 et les fait
    // donc tous échouer FORT, sans éditer une seule ligne côté appelant.
    // Ne PAS transformer ça en retour silencieux « pour la robustesse ».
    if (buildErr || msg.isNull()) {
        throw new Error("applyAction: " + (buildErr ?? "build a rendu null")
            + " -- RIEN n'a ete soumis au moteur, il n'y a AUCUNE mesure ici");
    }

    const statePtr0 = runner.add(runnerOff.state).readPointer();
    const before = summarize(statePtr0);
    // Activation du caster AVANT l'apply (ability seulement) — pour détecter le
    // no-op moteur silencieux (TF12) : un cast qui ne consomme pas l'action.
    const hadAction = action.kind === "ability"
        ? readHasAction(statePtr0, action.casterId) : null;
    gcRoot.add(msg);
    // Frame de capture : ApplyAiMessage est hooké en NON-top par message-trace
    // (il le suppose imbriqué dans runner.Apply), donc appelé en direct ici il
    // n'a aucune frame → les StreamDispatcher events tomberaient dans le vide.
    // On pushe NOTRE frame autour de l'invoke → toute la cascade (dont
    // l'overwatch déclenché par l'ability) atterrit dans `events`.
    ensureStreamHooks();
    const events: StreamEvent[] = [];
    pushApply("built", events);
    let applyErr: string | null = null;
    try {
        // EndTurnMessage passe par runner.Apply (message moteur, pas IA) ;
        // move/ability/finish par AiControl.ApplyAiMessage (chemin IA).
        if (action.kind === "endturn") {
            invokeMethod(runnerApplyMi!.info, runner, [msg]);
        } else {
            invokeMethod(applyAiMsgMi!.info, aiControl, [msg]);
        }
    } catch (e) { applyErr = (e as Error).message; }
    finally {
        try { popApply(); } catch { /* */ }
        try { gcRoot.remove(msg); } catch { /* */ }
    }

    const statePtr1 = runner.add(runnerOff.state).readPointer();
    const after = summarize(statePtr1);
    const st = readBattleStatus(statePtr1);
    const changes = diffUnits(before, after);
    const result: ActionResult = {
        kind: action.kind, ok: applyErr === null, error: applyErr,
        mutated: before.sig !== after.sig, changes,
        events, eventCount: events.length,
        stage: st.stage, currentPlayer: st.currentTurnPlayer,
    };
    if (action.kind === "ability") {
        result.spawned = changes.filter((c) => c.appeared).length;
        const hasAction = readHasAction(statePtr1, action.casterId);
        // actionConsumed=true ssi l'activation a basculé true→false. false si elle
        // est restée true (NO-OP : cast non enregistré comme action). null si
        // l'un des deux reads a échoué (caster introuvable / méthode non résolue).
        result.actionConsumed = (hadAction === null || hasAction === null)
            ? null : (hadAction === true && hasAction === false);
    }
    return result;
}

/** Lit une List<Position> (chemin des pieds de l'unité). */
export function readPositionList(
    listPtr: NativePointer, max = 64,
): Array<{ col: number; row: number }> {
    if (listPtr.isNull()) return [];
    try {
        const items = listPtr.add(LIST_ITEMS).readPointer();
        const size = listPtr.add(LIST_SIZE).readS32();
        if (items.isNull() || size <= 0 || size > 1000) return [];
        const out: Array<{ col: number; row: number }> = [];
        const n = Math.min(size, max);
        for (let i = 0; i < n; i++) {
            const base = items.add(ARRAY_FIRST + i * POS_STRIDE);
            out.push({ col: base.readS32(), row: base.add(4).readS32() });
        }
        return out;
    } catch { return []; }
}

export interface DecodedMsg {
    cls: string;
    unitId?: number;
    casterId?: number;
    targetId?: number;
    abilityType?: number;
    to?: { col: number; row: number } | null;
    pathLen?: number;
}

/** Décode un IInputMessage selon son type runtime. */
export function decodeMsg(msg: NativePointer, cls: string): DecodedMsg {
    try {
        switch (cls) {
            case "MoveUnitMessage": {
                const path = readPositionList(msg.add(MSG_OFF.moveFeet).readPointer());
                return {
                    cls,
                    unitId: msg.add(MSG_OFF.moveUnitId).readS32(),
                    to: path.length ? path[path.length - 1] : null,
                    pathLen: path.length,
                };
            }
            case "ActiveAbilityMessage":
                return {
                    cls,
                    casterId: msg.add(MSG_OFF.abilCaster).readS32(),
                    targetId: msg.add(MSG_OFF.abilTarget).readS32(),
                    abilityType: msg.add(MSG_OFF.abilType).readS32(),
                };
            case "FinishUnitTurnMessage":
                return { cls, unitId: msg.add(MSG_OFF.finishUnitId).readS32() };
            default:
                return { cls };
        }
    } catch { return { cls }; }
}

/** Décode la List<IInputMessage> yieldée par un MoveNext (l'action d'1 unité). */
export function decodeMsgList(list: NativePointer): {
    count: number; messages: DecodedMsg[];
} {
    if (list.isNull()) return { count: 0, messages: [] };
    let items: NativePointer; let size: number;
    try {
        items = list.add(LIST_ITEMS).readPointer();
        size = list.add(LIST_SIZE).readS32();
    } catch { return { count: 0, messages: [] }; }
    if (items.isNull() || size <= 0 || size > 200) {
        return { count: size, messages: [] };
    }
    const out: DecodedMsg[] = [];
    for (let i = 0; i < size; i++) {
        let msg: NativePointer;
        try { msg = items.add(ARRAY_FIRST + i * Process.pointerSize).readPointer(); }
        catch { continue; }
        if (msg.isNull()) continue;
        let cls = "?";
        try { cls = s(class_get_name(msg.readPointer()) as NativePointer); }
        catch { /* keep ? */ }
        out.push(decodeMsg(msg, cls));
    }
    return { count: size, messages: out };
}

export interface StateSummary {
    turn: number | null;
    playerOnTurn: number | null;
    units: Array<{
        squadId: number; pos: { col: number; row: number } | null;
        hp: number | null; ownerId: number | null;
    }>;
    sig: string;
}

/** Résumé compact de l'état (assez pour eyeball + détecter une mutation). */
export function summarize(statePtr: NativePointer): StateSummary {
    const proj = projectMatchState(statePtr);
    const units = proj.units.map((u) => ({
        squadId: u.squadId, pos: u.pos,
        hp: u.hp, ownerId: u.ownerId,
    }));
    const sig = units
        .map((u) => `${u.squadId}:${u.pos ? u.pos.col + "," + u.pos.row : "x"}:${u.hp}`)
        .sort()
        .join("|");
    return { turn: proj.turn, playerOnTurn: proj.playerOnTurn, units, sig };
}

/** Résout l'IEntity du joueur dont l'id == playerId (le player on turn).
 *  Pas de GetEntity (qui vit sur un Query, pas sur MatchState) : on scanne
 *  les entités de l'état — le player est l'entité portant ce BEntityId. */
export function resolvePlayerEntity(
    statePtr: NativePointer, playerId: number,
): NativePointer {
    let found = ptr(0);
    forEachEntity(statePtr, (e, id) => {
        if (found.isNull() && id === playerId) found = e;
    });
    return found;
}

/** Résout la stratégie IA du joueur courant. GetAi gère default/human/env ;
 *  fallback sur le champ _defaultPlayerAiStrategy si GetAi échoue. */
export function resolveStrategy(
    aiControl: NativePointer, playerId: number,
): { strategy: NativePointer; src: string; err: string | null } {
    let err: string | null = null;
    if (getAiMi) {
        try {
            // Nullable<BEntityId> : 8 octets, hasValue @0 (1B + pad), value @4.
            const nullable = Memory.alloc(8);
            nullable.writeU8(1);
            nullable.add(4).writeS32(playerId);
            const strat = invokeMethod(getAiMi.info, aiControl, [nullable]);
            if (!strat.isNull()) return { strategy: strat, src: "GetAi", err: null };
        } catch (e) { err = (e as Error).message; }
    }
    // Fallback champ direct.
    try {
        const strat = aiControl.add(defaultStratOff).readPointer();
        if (!strat.isNull()) {
            return { strategy: strat, src: "_defaultPlayerAiStrategy", err };
        }
    } catch { /* fallthrough */ }
    return { strategy: ptr(0), src: "none", err };
}

export interface DryRunResult {
    ok: boolean;
    error?: string;
    runner?: string;
    playerId?: number | null;
    strategySrc?: string;
    strategyErr?: string | null;
    hasNext?: boolean;
    moveNextCalls?: number;
    emptyYields?: number;
    action?: { count: number; messages: DecodedMsg[] } | null;
    /** L'unité activée (UnitId du MoveUnitMessage, sinon du Finish). */
    activatedUnitId?: number | null;
    mutated?: boolean;
    before?: StateSummary;
}

/** Itère une List<IInputMessage> en renvoyant pour chaque message son PTR
 *  brut (pour runner.Apply) ET son décodage. */
export function processMsgList(
    list: NativePointer,
): Array<{ ptr: NativePointer; decoded: DecodedMsg }> {
    const out: Array<{ ptr: NativePointer; decoded: DecodedMsg }> = [];
    if (list.isNull()) return out;
    let items: NativePointer; let size: number;
    try {
        items = list.add(LIST_ITEMS).readPointer();
        size = list.add(LIST_SIZE).readS32();
    } catch { return out; }
    if (items.isNull() || size <= 0 || size > 200) return out;
    for (let i = 0; i < size; i++) {
        let msg: NativePointer;
        try { msg = items.add(ARRAY_FIRST + i * Process.pointerSize).readPointer(); }
        catch { continue; }
        if (msg.isNull()) continue;
        let cls = "?";
        try { cls = s(class_get_name(msg.readPointer()) as NativePointer); }
        catch { /* keep ? */ }
        out.push({ ptr: msg, decoded: decodeMsg(msg, cls) });
    }
    return out;
}

/** Squads (EntityType.Unit) « à activer » par le joueur courant : contrôlés
 *  par lui ET vivants ET ayant encore une action. Calculé sur l'état VIVANT
 *  (gère les kills) via les helpers UnitExtensions. */
export function toActivateSquads(statePtr: NativePointer): number[] {
    const out: number[] = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        if (!invokeBool(isCtrlByCurMi, [e, statePtr])) return;
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        if (!invokeBool(hasActionLeftMi, [e])) return;
        out.push(id);
    });
    return out;
}

/** Squads activables du joueur courant AVEC leur ptr d'entité, ordonnés selon
 *  `order` : "asc"/"desc" par squadId, ou une liste explicite de squadIds (les
 *  ids absents sont rejetés en fin). Sert à IMPOSER l'ordre d'activation
 *  (contourne PickNextUnit). Le ptr d'entité d'un squad est stable sur la
 *  battle (l'objet persiste même mort) ; on re-vérifie vivant/action au moment
 *  de jouer. */
export function validSquadsOrdered(
    statePtr: NativePointer, order: "asc" | "desc" | number[],
): Array<{ id: number; ptr: NativePointer }> {
    const list: Array<{ id: number; ptr: NativePointer }> = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        if (!invokeBool(isCtrlByCurMi, [e, statePtr])) return;
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        if (!invokeBool(hasActionLeftMi, [e])) return;
        list.push({ id, ptr: e });
    });
    if (Array.isArray(order)) {
        const rank = new Map<number, number>();
        order.forEach((sid, i) => rank.set(sid, i));
        list.sort((a, b) =>
            (rank.get(a.id) ?? 9999) - (rank.get(b.id) ?? 9999));
    } else if (order === "asc") {
        list.sort((a, b) => a.id - b.id);
    } else {
        list.sort((a, b) => b.id - a.id);
    }
    return list;
}

export interface DemoState {
    units: Array<{
        squadId: number; pos: { col: number; row: number } | null;
        hp: number | null; owner: number | null; team: number | null;
    }>;
    toActivate: number[];
}

/** Snapshot d'état pour une démo IL (avant l'application de l'action). */
export function captureStateForDemo(statePtr: NativePointer): DemoState {
    const proj = projectMatchState(statePtr);
    return {
        units: proj.units.map((u) => ({
            squadId: u.squadId, pos: u.pos, hp: u.hp,
            owner: u.ownerId, team: u.teamId ?? null,
        })),
        toActivate: toActivateSquads(statePtr),
    };
}

/** Applique un EndTurnMessage sur le runner (passe la main à l'autre équipe). */
export function applyEndTurn(runner: NativePointer, events?: StreamEvent[]): boolean {
    if (!endTurnClass || !runnerApplyMi) return false;
    const msg = il2cpp_object_new(endTurnClass) as NativePointer;
    if (msg.isNull()) return false;
    gcRoot.add(msg);
    // Si `events` fourni : wrappe l'apply dans une frame pour capturer les
    // effets de FRONTIÈRE de tour (ticks d'AoE de tile, DoT, abilities déclenchées
    // en fin de tour) — sinon ils tomberaient dans le vide (runner.Apply hooké
    // NON-top par message-trace). C'est là que se résout l'artillerie retardée.
    if (events) { ensureStreamHooks(); pushApply("built", events); }
    try {
        if (endTurnCtor) invokeMethod(endTurnCtor.info, msg, null);
        invokeMethod(runnerApplyMi.info, runner, [msg]);
    } finally {
        if (events) { try { popApply(); } catch { /* */ } }
        try { gcRoot.remove(msg); } catch { /* best effort */ }
    }
    return true;
}

export interface UnitProposal {
    unitId: number;
    hasActionLeft: boolean;
    pumps: number;
    exhausted: boolean;
    proposed: DecodedMsg[];
}

// ─── #296 — REMISE À ZÉRO DES FLAGS DE TOUR (opt-in de `sweepAllUnitProposals`) ────────
//
// POURQUOI. Le sweep n'est un oracle FIDÈLE que sur un tour FRAIS. Mesuré le 2026-07-30
// sur un même build (`--advance 2`, board MC1_67) :
//
//   | séquence                            | `repair_prediction` | playbooks évalués           |
//   |-------------------------------------|---------------------|-----------------------------|
//   | dry-run IMMÉDIAT après build        | 5                   | 4 dont Repair_GalvanicField |
//   | dry-run APRÈS un `aiturn` intercalé | 0                   | 2                           |
//
// Les deux abilities DÉRIVÉES (`RepairType`@0x2c, `NormalAttackType`@0x28) disparaissent
// ENSEMBLE de l'énumération, alors que les cibles sont PLUS abîmées à ce moment-là — et
// sans la moindre erreur. Toute mesure de décision prise après un tour consommé est donc
// silencieusement PARTIELLE. La cause est en amont : `ActiveAbilityActionGenerator.
// u003CGenerateActionsu003Ed__7$$MoveNext` commence par `if (HasFlag(unit, 2 =
// ActiveAbilityUsed)) return 0` — AVANT `GetUnitAbilitiesInOrder`, donc l'attaque normale
// tombe avec les actives (établi par #17, PR #318).
//
// CE QU'ON N'INVENTE PAS. Le jeu a SA fonction pour ça :
// `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags(this,
//  bool removeNoActionAvailable, bool removeMoved)`. Son corps (relu sur `rnca9r7q6c`)
// retire TOUJOURS `ActiveAbilityUsed(2)`, `TurnFinished(3)` et `TurnTerminated(0x1b)` ;
// `NoActionAvailable(4)` sous le 1er booléen ; `Moved(0)`, `ArrivedAtFinalTile(1)` et
// `Teleported(0xc)` sous le 2nd. On n'énumère donc AUCUN ensemble « flags de tour » de
// notre cru — c'est le natif qui le définit, et un changement de build le suit tout seul.
//
// ⚠ Sa signature décompilée est DÉCALÉE par le `sret` (elle rend une struct de 7 octets) :
// Ghidra nomme `this` le buffer de retour et attribue `removeNoActionAvailable` à ce qui est
// en fait le 1er booléen. C'est EXACTEMENT le piège qui avait rendu `PredictRepair` faux sur
// tous ses arguments (#278) — les noms de paramètres IL2CPP sont justes, leur POSITION ne
// l'est pas. On ne lit donc PAS cette struct de retour : on mesure nous-mêmes, avant/après.
//
// CONTRAT READ-ONLY. On relève les flags POSÉS avant (par `UnitExtensions$$HasFlag`, une
// fois par valeur d'enum — le même canal que `combatSnapshot`), on appelle `RemoveTurnFlags`,
// on balaie, puis on RE-POSE par `UnitFlagsComponent$$Add` exactement ce qui a disparu. La
// restauration est donc MESURÉE, pas déduite d'un layout. Le `mutated` du RPC reste la
// garde : s'il passe à `true`, la restauration a échoué et la mesure ne vaut rien.
const unitFlagsComponentClass = findClassAnywhere(
    "IdunBattle.Entities.Components", "UnitFlagsComponent");
const unitExtClassFlags = findClassAnywhere("IdunBattle.Entities", "UnitExtensions");
const removeTurnFlagsMi = unitFlagsComponentClass
    ? findMethodByParamCount(unitFlagsComponentClass, "RemoveTurnFlags", 2) : null;
const flagsAddMi = unitFlagsComponentClass
    ? findMethodByParamCount(unitFlagsComponentClass, "Add", 1) : null;
const hasFlagMiFlags = unitExtClassFlags
    ? findMethodByParamCount(unitExtClassFlags, "HasFlag", 2) : null;

/** Le reset est-il montable ? `false` -> l'appelant doit REFUSER, pas balayer sans. */
export function turnFlagResetAvailable(): boolean {
    return !!(unitFlagsComponentClass && removeTurnFlagsMi && flagsAddMi && hasFlagMiFlags
        && unitFlagValues().length > 0);
}

/** Quel maillon manque — pour que le refus NOMME sa cause au lieu d'être opaque. */
export function turnFlagResetDiagnostic(): string {
    return `classe=${!!unitFlagsComponentClass} RemoveTurnFlags=${!!removeTurnFlagsMi} `
        + `Add=${!!flagsAddMi} HasFlag=${!!hasFlagMiFlags} `
        + `valeursEnum=${unitFlagValues().length}`;
}

/** Valeurs de `IdunBattle.Entities.Enum.UnitFlag`, LUES AU RUNTIME et dédupliquées (un
 *  enum C# admet des alias). Aucune table du dépôt : une renumérotation de build se
 *  propage seule — même discipline que `unitFlagTypes` de `rpc-snapshot.ts`. */
let unitFlagValuesCache: number[] | null = null;
function unitFlagValues(): number[] {
    if (unitFlagValuesCache) return unitFlagValuesCache;
    const raw = dumpEnum("IdunSharedAssembly.dll", "IdunBattle.Entities.Enum", "UnitFlag") ?? {};
    const vals = Object.keys(raw)
        .map((k) => parseInt(raw[k], 10))
        .filter((v) => Number.isFinite(v));
    unitFlagValuesCache = Array.from(new Set(vals)).sort((a, b) => a - b);
    return unitFlagValuesCache;
}

function unitFlagsComponentOf(entity: NativePointer): NativePointer | null {
    if (!unitFlagsComponentClass) return null;
    let found: NativePointer | null = null;
    forEachComponent(entity, (comp, klass) => {
        if (found) return;
        if (klass.equals(unitFlagsComponentClass)) found = comp;
    });
    return found;
}

export interface TurnFlagReset {
    unitId: number;
    /** Flags effectivement RETIRÉS par le natif — donc ceux à re-poser après. */
    cleared: number[];
    /** Flags qu'on n'a PAS réussi à restaurer. Non vide = la mesure est à jeter. */
    notRestored: number[];
    error?: string;
}

/** Sweep READ-ONLY : pour chaque squad contrôlé+vivant du joueur courant,
 *  pompe `CalculateNextActionForUnit(unit)` et lit l'action proposée SANS
 *  l'appliquer. Chaque proposition est conditionnée au MÊME état courant
 *  (« si l'unité jouait en premier »). `moveNextRef` cache le MethodInfo
 *  MoveNext entre appels. Ne mute pas le runner.
 *
 *  `opts.resetTurnFlags` (#296) répond à l'AUTRE question : « que proposerait chaque unité
 *  si son tour n'était PAS entamé ? » — seule façon d'obtenir un oracle de DÉCISION
 *  per-unité pour un SUMMON, dont le natif termine le tour dès l'apparition
 *  (`SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` -> `FinishUnitTurn(spawned,
 *  isTerminated: true)`). Le reset porte sur les MÊMES squads que le balayage — c'est la
 *  raison pour laquelle il vit ICI et non chez l'appelant : une seconde énumération
 *  pourrait diverger de celle qui est réellement balayée. */
export function sweepAllUnitProposals(
    statePtr: NativePointer, strategy: NativePointer,
    calcUnitMi: { info: NativePointer }, maxPump: number,
    moveNextRef: { mi: { info: NativePointer; ptr: NativePointer } | null },
    opts?: { resetTurnFlags?: boolean },
): { units: UnitProposal[]; pumps: number; turnFlagsReset?: TurnFlagReset[] } {
    const squads: Array<{ id: number; ptr: NativePointer; hasAction: boolean }> = [];
    forEachEntity(statePtr, (e, id, ty) => {
        if (ty !== EntityType.Unit) return;
        if (!invokeBool(isCtrlByCurMi, [e, statePtr])) return;
        if (!invokeBool(isAliveMi, [e, statePtr])) return;
        squads.push({ id, ptr: e, hasAction: invokeBool(hasActionLeftMi, [e]) });
    });

    const wantReset = opts?.resetTurnFlags === true && turnFlagResetAvailable();
    const resets: TurnFlagReset[] = [];
    const compById = new Map<number, NativePointer>();
    const flagBuf = Memory.alloc(4);
    const boolBuf = Memory.alloc(1);
    const flagsOf = (e: NativePointer): number[] => {
        const on: number[] = [];
        for (const v of unitFlagValues()) {
            flagBuf.writeS32(v);
            if (invokeBool(hasFlagMiFlags!, [e, flagBuf])) on.push(v);
        }
        return on;
    };
    if (wantReset) {
        for (const sq of squads) {
            const comp = unitFlagsComponentOf(sq.ptr);
            if (!comp) continue;
            const had = flagsOf(sq.ptr);
            const rec: TurnFlagReset = { unitId: sq.id, cleared: [], notRestored: [] };
            try {
                boolBuf.writeU8(1);
                invokeMethod(removeTurnFlagsMi!.info, comp, [boolBuf, boolBuf]);
                const now = new Set(flagsOf(sq.ptr));
                rec.cleared = had.filter((v) => !now.has(v));
            } catch (e) {
                rec.error = (e as Error).message;
            }
            compById.set(sq.id, comp);
            resets.push(rec);
        }
    }

    const out: UnitProposal[] = [];
    let pumps = 0;
    try {
        for (const sq of squads) {
            let chunk: DecodedMsg[] = [];
            let p = 0; let exhausted = false; let err: string | null = null;
            try {
                const e = invokeMethod(calcUnitMi.info, strategy, [sq.ptr]);
                if (e.isNull()) { exhausted = true; }
                else {
                    gcRoot.add(e);
                    try {
                        if (!moveNextRef.mi) {
                            moveNextRef.mi = findMethod(e.readPointer(), "MoveNext");
                        }
                        while (moveNextRef.mi && p < maxPump) {
                            const boxed = invokeMethod(moveNextRef.mi.info, e, null);
                            p++; pumps++;
                            if (boxed.isNull() || boxed.add(0x10).readU8() === 0) {
                                exhausted = true; break;
                            }
                            const decoded = decodeMsgList(e.add(0x18).readPointer());
                            if (decoded.count > 0) { chunk = decoded.messages; break; }
                        }
                    } finally { try { gcRoot.remove(e); } catch { /* */ } }
                }
            } catch (ex) { err = (ex as Error).message; }
            out.push({
                unitId: sq.id, hasActionLeft: sq.hasAction, pumps: p, exhausted,
                proposed: err ? [{ cls: "ERR:" + err }] : chunk,
            });
        }
    } finally {
        // RESTAURATION INCONDITIONNELLE. Même si le balayage jette, l'état doit revenir
        // tel quel : un dry-run « read-only » qui laisserait le runner amputé de ses flags
        // de tour fausserait TOUS les appels suivants, et en silence.
        if (wantReset) {
            for (const rec of resets) {
                const comp = compById.get(rec.unitId);
                const sq = squads.find((x) => x.id === rec.unitId);
                if (!comp || !sq) continue;
                for (const v of rec.cleared) {
                    try {
                        flagBuf.writeS32(v);
                        invokeMethod(flagsAddMi!.info, comp, [flagBuf]);
                    } catch { /* constaté juste après */ }
                    flagBuf.writeS32(v);
                    if (!invokeBool(hasFlagMiFlags!, [sq.ptr, flagBuf])) {
                        rec.notRestored.push(v);
                    }
                }
            }
        }
    }
    return { units: out, pumps, turnFlagsReset: wantReset ? resets : undefined };
}

export interface UnitDemo {
    turnIndex: number;
    player: number;
    activatedUnitId: number;
    move: { to: { col: number; row: number } | null; pathLen: number };
    toActivate: number[];
    units: DemoState["units"];
}

/** Lit (col,row) d'une tile via sa PositionComponent. */
export function readTileCoord(tile: NativePointer): { col: number; row: number } {
    let col = -1; let row = -1;
    if (positionComponentClass && !tile.isNull()) {
        try {
            forEachComponent(tile, (comp, klass) => {
                if (!klass.equals(positionComponentClass!)) return;
                try { col = comp.add(POS_COL_OFF).readS32(); } catch { /* */ }
                try { row = comp.add(POS_ROW_OFF).readS32(); } catch { /* */ }
            });
        } catch { /* */ }
    }
    return { col, row };
}

/** Résout (col,row) → entityId de la TILE à ce hex (EntityType.Tile=0, coord via
 *  PositionComponent). Nécessaire pour les abilities ciblant un HEX LIBRE (summons
 *  type AlphaWarrior/ForwardSpotter, mur DutyEternal, marquage sur case vide) :
 *  `ActiveAbilityMessage` n'a PAS de champ position → on cible l'entité-tuile (le
 *  moteur prend son hex). -1 si aucune tile à ce hex. */
export function findTileEntityId(
    statePtr: NativePointer, col: number, row: number,
): number {
    let found = -1;
    forEachEntity(statePtr, (e, id, ty) => {
        if (found >= 0 || ty !== EntityType.Tile) return;
        const c = readTileCoord(e);
        if (c.col === col && c.row === row) found = id;
    });
    return found;
}

/** Extrait les tiles d'un IOrderedSet<IEntity> (List<T> : items@0x10, size@0x18,
 *  données dès +0x20). */
export function extractTiles(
    orderedSet: NativePointer,
): Array<{ col: number; row: number }> {
    const out: Array<{ col: number; row: number }> = [];
    if (orderedSet.isNull()) return out;
    let items: NativePointer; let size: number;
    try {
        items = orderedSet.add(LIST_ITEMS).readPointer();
        size = orderedSet.add(LIST_SIZE).readS32();
    } catch { return out; }
    if (items.isNull() || size <= 0 || size > 1000) return out;
    for (let i = 0; i < size; i++) {
        let tile: NativePointer;
        try { tile = items.add(ARRAY_FIRST + i * Process.pointerSize).readPointer(); }
        catch { continue; }
        if (tile.isNull()) continue;
        out.push(readTileCoord(tile));
    }
    return out;
}

/** Comme extractTiles mais CONSERVE le pointeur de chaque tile — nécessaire au
 *  shrink-and-recall (on doit pouvoir `set.Remove(tilePtr)` la meilleure tile
 *  entre deux appels de GetBestTileToAttackFrom). */
export function extractTilePtrs(
    orderedSet: NativePointer,
): Array<{ ptr: NativePointer; col: number; row: number }> {
    const out: Array<{ ptr: NativePointer; col: number; row: number }> = [];
    if (orderedSet.isNull()) return out;
    let items: NativePointer; let size: number;
    try {
        items = orderedSet.add(LIST_ITEMS).readPointer();
        size = orderedSet.add(LIST_SIZE).readS32();
    } catch { return out; }
    if (items.isNull() || size <= 0 || size > 1000) return out;
    for (let i = 0; i < size; i++) {
        let tile: NativePointer;
        try { tile = items.add(ARRAY_FIRST + i * Process.pointerSize).readPointer(); }
        catch { continue; }
        if (tile.isNull()) continue;
        const c = readTileCoord(tile);
        out.push({ ptr: tile, col: c.col, row: c.row });
    }
    return out;
}

/** ActiveAbilityComponent d'une unité (ou ptr null). */
export function getAbilityComponent(unit: NativePointer): NativePointer {
    let comp = ptr(0);
    if (!activeAbilityComponentClass) return comp;
    try {
        forEachComponent(unit, (c, klass) => {
            if (comp.isNull() && klass.equals(activeAbilityComponentClass!)) comp = c;
        });
    } catch { /* */ }
    return comp;
}

/** ActiveAbilityType CONCRETS d'une unité : son attaque normale
 *  (NormalAttackType @0x28) + (si includeActives) ses actives (GetActives →
 *  .AbilityName @0x44). Filtre 0/None. C'est ce qu'il faut passer à
 *  GetBestTileToAttackFrom (pas l'abstrait 17). */
export interface AbilityInfo {
    id: number; name: string; kind: string;
    // état runtime (actives uniquement ; absent pour l'attaque normale = toujours
    // dispo). usable=castable ce tour ; cooldown=tours restants (null=prêt) ;
    // disabled ; ammoCost (null=pas de coût) ; hasAmmo.
    usable?: boolean; cooldown?: number | null; disabled?: boolean;
    ammoCost?: number | null; hasAmmo?: boolean;
    // niveau/mult PER-ABILITY (AbilityState @0x4c, capteur #100) — indexent les variables
    // config (maxDmg/nrOfHits/…) de CETTE ability, ≠ canal global unitConfig.
    level?: number; multiplier?: number;
    // #433-r4-r2-r1-r1-c-r1 — tour de dernière utilisation, en TRI-ÉTAT :
    // `<x>HasValue === null` = PAS MESURÉ (offset non résolu), `false` = mesuré et vide,
    // `true` = mesuré avec valeur. `unresetedLastTurnUsed` est celui que lit
    // `AttackQuery$$IsAlreadyUsedThisTurn` ; `lastTurnUsed` est son voisin, publié pour que
    // la confrontation soit possible sans seconde fenêtre.
    lastTurnUsed?: number | null; lastTurnUsedHasValue?: boolean | null;
    unresetedLastTurnUsed?: number | null; unresetedLastTurnUsedHasValue?: boolean | null;
}
export function unitAbilityTypes(
    unit: NativePointer, includeActives: boolean,
): AbilityInfo[] {
    const out: AbilityInfo[] = [];
    const comp = getAbilityComponent(unit);
    if (comp.isNull()) return out;
    if (normalAttackTypeOff >= 0) {
        try {
            const na = comp.add(normalAttackTypeOff).readS32();
            if (na !== 0) {
                out.push({ id: na, name: abilityName(na) ?? "id:" + na, kind: "normal" });
            }
        } catch { /* */ }
    }
    if (includeActives && getActivesMi && abilityNameOff >= 0) {
        try {
            const list = invokeMethod(getActivesMi.info, comp, null);
            if (!list.isNull()) {
                const items = list.add(LIST_ITEMS).readPointer();
                const size = list.add(LIST_SIZE).readS32();
                if (!items.isNull() && size > 0 && size < 64) {
                    for (let i = 0; i < size; i++) {
                        const ab = items
                            .add(ARRAY_FIRST + i * Process.pointerSize).readPointer();
                        if (ab.isNull()) continue;
                        const t = ab.add(abilityNameOff).readS32();
                        if (t === 0) continue;
                        const dup = out.find((e) => e.id === t);
                        if (dup) {
                            // id déjà émis (l'attaque NORMALE, poussée depuis NormalAttackType sans
                            // objet ActiveAbility) → MERGER l'état live + AbilityState (#100) au lieu
                            // de le perdre par dedup.
                            Object.assign(dup, readAbilityState(ab));
                        } else {
                            // état LIVE (cooldown/munitions/disabled) lu sur l'objet
                            // ActiveAbility — l'info que gameconfig ne peut pas donner.
                            out.push({
                                id: t, name: abilityName(t) ?? "id:" + t, kind: "active",
                                ...readAbilityState(ab),
                            });
                        }
                    }
                }
            }
        } catch { /* */ }
    }
    // Pass complémentaire : abilities GRANTED-par-trigger que GetActives rate (filtre
    // IsActiveAbility) mais qui sont castables — ex. heal du passif TwistedScience (1167).
    // GetUnusedAbilities itère la même collection, filtrée par « unused » (@0x28) → les inclut.
    if (includeActives && getUnusedAbilitiesMi && abilityNameOff >= 0) {
        try {
            const list = invokeMethod(getUnusedAbilitiesMi.info, comp, null);
            if (!list.isNull()) {
                const items = list.add(LIST_ITEMS).readPointer();
                const size = list.add(LIST_SIZE).readS32();
                if (!items.isNull() && size > 0 && size < 64) {
                    for (let i = 0; i < size; i++) {
                        const ab = items
                            .add(ARRAY_FIRST + i * Process.pointerSize).readPointer();
                        if (ab.isNull()) continue;
                        const t = ab.add(abilityNameOff).readS32();
                        if (t !== 0 && !out.some((e) => e.id === t)) {
                            out.push({
                                id: t, name: abilityName(t) ?? "id:" + t, kind: "granted",
                                ...readAbilityState(ab),
                            });
                        }
                    }
                }
            }
        } catch { /* */ }
    }
    return out;
}

/** Abilities d'un MoW (Machine) : NormalAttack(=0 souvent) + actives + surtout
 *  Primary/SecondaryMachineAbilityType (= l'artillerie, ce qu'on TIRE). */
export function mowAbilityTypes(
    machine: NativePointer,
): Array<{ id: number; name: string; kind: string }> {
    const out = unitAbilityTypes(machine, true);  // normal + actives
    const comp = getAbilityComponent(machine);
    if (!comp.isNull()) {
        const extra: Array<[number, string]> = [
            [primaryMachineAbilityOff, "machinePrimary"],
            [secondaryMachineAbilityOff, "machineSecondary"],
        ];
        for (const [off, kind] of extra) {
            if (off < 0) continue;
            try {
                const t = comp.add(off).readS32();
                if (t !== 0 && !out.some((e) => e.id === t)) {
                    out.push({ id: t, name: abilityName(t) ?? "id:" + t, kind });
                }
            } catch { /* */ }
        }
    }
    return out;
}

/** Tile courante d'une unité — EntityExtensions.GetMainTile(unit, state). */
export function getUnitMainTile(
    unit: NativePointer, statePtr: NativePointer,
): NativePointer {
    if (!getMainTileMi) return ptr(0);
    try { return invokeMethod(getMainTileMi.info, null, [unit, statePtr]); }
    catch { return ptr(0); }
}

// ===== Cœur partagé (utilisé par aiAttackRank ET decisionView) =====

/** Instance DamagePredictionQuery du runner via EntityServices.<DPQ>@0x88
 *  (runner.<Services>@0xC8). ptr(0) si indisponible. */
export function resolveDpq(runner: NativePointer): NativePointer {
    if (servicesOff < 0 || dpqInServicesOff < 0) return ptr(0);
    try {
        const services = runner.add(servicesOff).readPointer();
        if (services.isNull()) return ptr(0);
        return services.add(dpqInServicesOff).readPointer();
    } catch { return ptr(0); }
}
