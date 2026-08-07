"""TheQuickening (active 1151, bloodMephiston) — teleport-ECHANGE + free melee attack faction-gatee.

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$ExecuteBehaviour` (IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor) : cast TILE-TARGET (le joueur/IA
choisit une TUILE a portee-mouvement 2). Le caster s'y TELEPORTE ; l'unite eventuellement presente sur la
tuile (filtre `Attackable`) est ECHANGEE vers la tuile d'origine du caster. Puis le caster ET l'unite
echangee, SI faction BloodAngels (natif `HasFaction(unit, 0xe=14)`), executent une attaque melee immediate
depuis leur nouvelle position, avec le stat Attack OVERRIDE par la formule config
(`PercentageOfAttackCappedAtMax`).

Arbre natif (`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$ExecuteBehaviour`, 7 `AActiveAbility.Execute` sequentiels) :
  1. `SetCache(CasterTile@0x168) & Reserve(Caster@0x160, Target@0x178) &
      GetMoveOutBehaviour(Caster) & GetMoveOutBehaviour(Attackable@Target)`
  2. `GetMoveInBehaviour(Caster -> Target) & GetMoveInBehaviour(Attackable -> CasterTile@0x168)`
  3. `GetTriggerMovementAbilitiesBehaviour(Caster)`   (EvaluateAbilities(0x1c=28) on-move)
  4. `GetTriggerAttackBehaviour(Caster)`               (free attack, gate HasFaction 14)
  5. `GetTriggerMovementAbilitiesBehaviour(Attackable)`
  6. `GetTriggerAttackBehaviour(Attackable)`
  7. `InvalidateCaches`

`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetMoveOutBehaviour` : `RemoveEffect(EffectFromOwner(unit, 0x19)) & AddEffect(0x414 Untargetable,
caster-src, unit) & MoveUnit(unit -> Null)`  (lift off-board, marqueur transit).
`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetMoveInBehaviour`  : `MoveUnit(unit -> tile) & RemoveEffect(unit, 0x414)`  (atterrissage).
`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour` : `If(HasFaction(unit, 0xe=14),
    AddEffect(0x529 ForcedInMelee, AbilityStateReference, unit, Nullable<int>(1))
    & AddStatOverrideEffect(unit, 0x510 Attack_Override, PercentageOfAttackCappedAtMax(Attack, dmgPct, maxDmg))
    & PerformAIAttackFromCurrentPosition(unit, utilityEntity=unit, customUtility=<lambda>, skipAtomic=0)
    & RemoveEffect(unit, 0x510) & RemoveEffect(unit, 0x529))`
  — ORDRE relu au decompile (chaine `op_BitwiseAnd`) : l'AddEffect(0x529) precede l'AddStatOverride.
  L'effet 0x529 n'est PAS decoratif : `IdunBattle.Core.Services.TargetingQuery$$GetRange` fait
  `if (HasEffect(unit, 0x529)) range = Math.Min(1, range)` -> c'est LUI qui restreint la free-attack a
  l'adjacence. Le port le POSE donc reellement (feuille `AddEffect`) et le retire (feuille `RemoveEffect`).

MESURE LIVE (probe_217, runner build) — cast de meph(2,6) sur tuile ally(4,7) : POST meph=(4,7)
ally=(2,6) (SWAP net) ; effets Untargetable(0x414)/ForcedInMelee(0x529)/TemporaryStatOverride(0x510)
TOUS ajoutes ET retires DANS le cast (net-zero, aucun effet persistant) ; Attack_Override meph=1204,
ally=4818 = la formule config. Le port materialise donc l'observable NET :
  - l'ECHANGE de positions (deterministe, coeur de la divergence) ;
  - la free-attack melee faction-BloodAngels (override Attack, cible ennemi adjacent) via
    `set_stat_override`(= 0x510) + le pipeline d'attaque normale + `remove_stat_override`.

RESIDUS documentes (case-217) :
  - EvaluateAbilities(28) (phases 3/5, on-move triggers) NON porte -> surface passive separee
    (aucun on-move passif BloodAngels au roster teste) ;
  - le filtre `Attackable = UnitsWithoutTrait(0x1b=27)` du swap-unit est APPROXIME par « toute unite
    vivante sur la tuile cible autre que le caster » (aucune unite trait-27 sur une tuile de swap teste) ;
  - le CHOIX de cible de `PerformAIAttackFromCurrentPosition` (moteur d'utilite AI natif + le
    `customUtility` propre a ce call-site) est approxime par l'ennemi le plus proche A PORTEE — portee
    clampee a 1 par l'effet ForcedInMelee, cf. ci-dessus ; le roll de degat reste RNG (non bit-exact).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ..base import ActiveAbility
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddEffect, RemoveEffect
from ..targeting import RANGE_FROM_CONFIG, RANGED_BOOL_FALSE, TargetingOptions
from ..targeting_rule import TargetingRule as TR
from .summon import perform_ai_attack_from_current_position
from ...operations.movement import MoveUnitOperation
from ...components import StatsComponent, PositionComponent, UnitComponent
from ....entities.stats import StatType
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effect_type import EffectType
from ....entities.effects.magnitude import ability_var
from ....entities.selectors.accessors import CasterTile, SelectTile, Target
from ....entities.selectors.tiles import Caster, MovableTilesInRange
from ....entities.selectors.units import Enemies, Sub
from ....dsl.effects import ExecutionContext
from ..targeting import unit_of_entity                             # #484 : hisse, cf. ci-dessous
from ...components import get_feet_count                           # #484 : hisse, cf. ci-dessous
from ....dsl.base import Const

if TYPE_CHECKING:
    from ...state import State

# `HasFaction(unit, 0xe=14)` IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour : faction hardcodee du gate free-attack = BloodAngels (la
# faction de Mephiston, le porteur ; l'echange ne beneficie du coup gratuit QU'aux BloodAngels).
_BLOODANGELS = "BloodAngels"
_ABILITY = "TheQuickening"
# `AddEffect(0x529, ...)` / `RemoveEffect(0x529)` de `GetTriggerAttackBehaviour`. C'est le PARAMETRE
# CONTEXTUEL lu par `IdunBattle.Core.Services.TargetingQuery$$GetRange` (`range = Math.Min(1, range)`)
# qui reduit le domaine de cible de la free-attack a l'adjacence.
FORCED_IN_MELEE = int(EffectType.ForcedInMelee)      # 1321 = 0x529


def _pos(e) -> Optional[tuple]:
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _tile_pos(state: "State", tile_id) -> Optional[tuple]:
    board = getattr(state, "board", None)
    if board is None or tile_id is None:
        return None
    t = board.by_id.get(tile_id) if hasattr(board, "by_id") else None
    if not t:
        return None
    return (t.get("col"), t.get("row"))


def _living_unit_id_on(state: "State", pos: tuple, exclude_id: int) -> Optional[int]:
    """Id de l'unite VIVANTE occupant la tuile `pos` (autre que `exclude_id`) — approx du selecteur natif
    `Attackable(Units(Target)) = UnitsWithoutTrait(0x1b=27)` (le filtre trait-27 n'est pas materialise :
    aucune unite trait-27 sur une tuile de swap teste). Tie-break `id` (deterministe)."""
    best = None
    for oid, e in state.entities.items():
        if oid == exclude_id:
            continue
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue
        if _pos(e) == pos and (best is None or oid < best):
            best = oid
    return best


def _unit_faction(state: "State", unit_id: int) -> Optional[str]:
    """FactionId (string gameconfig) de l'unite — gate `HasFaction(unit, 0xe=14=BloodAngels)`."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    vis = uc.visual_id if uc is not None else None
    if vis is None:
        return None
    return (GC.unit(vis) or {}).get("FactionId")


def _quickening_override(state: "State", attacker_id: int, level, mult: int) -> Optional[int]:
    """Valeur d'override Attack de la free-attack = `IdunBattleLogic.Entities.DSLFactory$$PercentageOfAttackCappedAtMax` :
    `min(maxDmg[level]xmult, round(unit.Attack x dmgPct[level]/100))`. `level`/`mult` = ceux de
    l'ability de MEPH (config lue via `ability+0x60`) ; `Attack` = celui de l'unite qui attaque
    (`StatAmount(unit, Attack)`). maxDmg est rarity-scale (`variablesAffectedByRarityBonus`), dmgPct non."""
    e = state.get_entity(attacker_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    atk = int(sc.ctx.stat(StatType.ATTACK))
    pct = ability_var(_ABILITY, "dmgPct", level, multiplier_pct=mult)          # non rarity-scale -> mult inerte
    cap = ability_var(_ABILITY, "maxDmg", level, multiplier_pct=mult)          # rarity-scale par mult
    if pct is None:
        return None
    val = round(atk * int(pct) / 100.0)
    if cap is not None:
        val = min(val, int(cap))
    return int(val)


def _free_melee_attack(state: "State", caster_id: int, unit_id: int, level, mult: int,
                       ectx: ExecutionContext) -> Optional[dict]:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetTriggerAttackBehaviour`
    pour UNE unite (gate `HasFaction(unit, 0xe=14)` = BloodAngels deja verifie par l'appelant).

    MIRROR de la chaine `op_BitwiseAnd` du DECOMPILE, **dans l'ordre natif** (le decompile enchaine
    `uVar7 & local_38 & uVar6 & uVar5 & uVar8`) :
      1. `AddEffect(0x529 ForcedInMelee, source=AbilityStateReference, target=unit, duree=Nullable<int>(1))`
      2. `AddStatOverrideEffect(unit, 0x510 Attack_Override, PercentageOfAttackCappedAtMax(...))`
      3. `PerformAIAttackFromCurrentPosition(unit, utilityEntity=unit, customUtility=<lambda>, skipAtomic=0)`
      4. `RemoveEffect(unit, 0x510)`
      5. `RemoveEffect(unit, 0x529)`

    L'etape 1 n'est PAS decorative : `IdunBattle.Core.Services.TargetingQuery$$GetRange` fait
    `if (HasEffect(unit, 0x529)) range = Math.Min(1, range)` — c'est ELLE qui reduit le domaine de cible
    de l'etape 3 a l'ADJACENCE. Le port pose donc reellement l'effet (feuille `AddEffect`) avant d'appeler
    le noeud, et le retire apres (feuille `RemoveEffect`) : le domaine melee EMERGE du contexte au lieu
    d'etre code en dur ici (de-fork — il n'existe qu'UN port de `PerformAIAttackFromCurrentPosition`,
    `loki/summon.py::perform_ai_attack_from_current_position`, dispatch after-hit inclus).

    `set_stat_override(ATTACK, V)` = le canal 0x510 : le pipeline d'attaque normale lit `ctx.stat(ATTACK)=V`
    (base=V) ; l'override est RETIRE apres (net-zero, conforme a la cascade live). None si rng non cale /
    override indisponible / aucune cible legale a portee 1 (PerformAIAttack no-op sans cible, trace live)."""
    if state.rng is None:
        return None
    V = _quickening_override(state, unit_id, level, mult)
    if V is None:
        return None
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None:
        return None
    # source = `AActiveAbility.get_AbilityStateReference` (l'ability de MEPH = le caster du cast) ;
    # cible = `param_3` = l'unite qui attaque (le caster OU l'unite echangee) -> `Target()`.
    ents = entities_from_state(state, caster_id, unit_id)
    # (1) AddEffect(0x529) : duree = `Nullable<int>(1)` LITTERALE du decompile (pas un TurnsFromRounds).
    AddEffect(FORCED_IN_MELEE, "ForcedInMelee", Target(), duration_turns=1).execute(ents, ectx)
    # (2) AddStatOverrideEffect(0x510)
    sc.ctx.stats.set_stat_override(StatType.ATTACK, int(V))
    try:
        # (3) LE noeud (corps unique) : cible AI-choisie a portee COURANTE — clampee a 1 par l'effet (1).
        r = perform_ai_attack_from_current_position(state, unit_id)
    finally:
        sc.ctx.stats.remove_stat_override(StatType.ATTACK)  # (4) RemoveEffect(0x510) -> net-zero
        RemoveEffect(FORCED_IN_MELEE, Target()).execute(ents, ectx)   # (5) RemoveEffect(0x529) -> net-zero
    if r is None:
        return None
    return {"attacker": unit_id, "target": r["target"], "override": int(V), "total": r.get("total"),
            "after_hit": r.get("after_hit")}


class TheQuickeningAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$ExecuteBehaviour` (id 1151, bloodMephiston). Cast TILE-TARGET :
    le caster se TELEPORTE sur la tuile ciblee (portee-mouvement 2) ; l'unite eventuellement presente y
    est ECHANGEE vers la tuile d'origine du caster ; puis caster + unite-echangee (SI BloodAngels)
    attaquent en melee depuis leur nouvelle position (Attack override par la formule config).

    `target_id` = id de TUILE (cast tile-target, `NCContext.tile_id_by_pos` cote decision ; abilityTargets
    kind='tile'). IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor : `TargetingOptions(...,0x806000000)` + `AActiveAbility(...,2)`."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.TheQuickening)  # 1151
    ABILITY_ID = "TheQuickening"          # cle gameconfig -- lue par `SetConfigValuesInTargetingOptions`

    # GATE DE CIBLE (#115) -- FORME 2, « PRESET + FLAGS », VERIFIEE au decompile (et non supposee) :
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$.ctor` recopie
    # `<TargetingOptions statics>+0x200` PUIS appelle
    #   `TargetingOptions..ctor(&opts, &preset, 0x806000000, 0)`
    # Cette surcharge recopie le preset champ par champ SAUF `Rules`, qu'elle COMBINE :
    # `*(dst+0x28) = param_3 | *(preset+0x28)`. Le litteral 0x806000000 n'est donc PAS le masque.
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit le preset +0x200 :
    #     +0x200 isSelfCasting    = 0
    #     +0x208 range           <- `TargetingRange` statics+0x18 = RANGE_FROM_CONFIG
    #     +0x220 forceMeleeTarget = 1 = RangedBool.False
    #     +0x228 rules            = 0x42
    # => masque EFFECTIF = `0x806000000 | 0x42` = **0x806000042**.
    # Decomposition EXHAUSTIVE (`IdunBattle.Core.Services.TargetingRule`), somme = 0x806000042 :
    #     0x2           TargetMatchesDynamicRule       -> non surcharge cote port -> defaut 0
    #     0x40          TargetIsTile                   -> cast TILE-TARGET. Regle PORTEE dans son
    #                   volet « tuile non marchable » (rend le litteral `ValidRequest`) ; elle
    #                   aiguille aussi `_targets_the_caster`.
    #     0x2000000     AllowObscuredTargetByElevation -> PERMISSIF (pas un refus)
    #     0x4000000     AllowObscuredTargetByWalls     -> PERMISSIF (les deux = le composite
    #                   `AllowObscuredTarget` 0x6000000 de l'enum)
    #     0x800000000   CasterHas1Tiles                -> regle du volet CASTER
    #                   (`GetInvalidCasterReason`), NON PORTEE : elle exige que le caster occupe
    #                   EXACTEMENT une tuile, ce qui est le cas de tout heros a empreinte 1.
    # PORTEE (#241) : `RANGE_FROM_CONFIG` -> `AActiveAbility$$SetConfigValuesInTargetingOptions`
    # pose `overrideRange = constants.range` de `TheQuickening` = **2** (la « portee-mouvement 2 »
    # du kit, confirmee au binaire) ; `forceMeleeTarget = RangedBool.False` -> aucun clamp de melee.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsTile
        | TR.AllowObscuredTargetByElevation
        | TR.AllowObscuredTargetByWalls
        | TR.CasterHas1Tiles
    ), range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$GetDynamicInvalidTargetReason`
        (#287-r5-r1) -- MIRROR du decompile :

            range = Configuration.GetNumberConstant(0x16 range);
            sel   = DSLSelectors$$MovableTilesInRange(caster@0x48, casterTile@0x50, Direct(range),
                                                      ignoreFlags = 1, ignoreUnitsOnTiles = 1);
            sel   = sel op_Subtraction DSLSelectors$$Enemies(caster@0x48, sel, 3);
            ents  = AbilityEntities(caster, caster, target, ..., casterTiles, ...);
            if (!sel.SelectTiles(ents).<ICollection slot 4 Contains>(target)) return 0x8000000;
            unit = UnitExtensions$$GetUnit(target, state@0x18);
            if (unit == null) return 0;
            if (GetFeetCount(unit) != GetFeetCount(caster)) return 2;
            return 0;

        `0x8000000` = `TargetingRule.TargetIsInRange`, `2` = `TargetingRule.TargetMatchesDynamicRule`.
        Les deux slots sont LUS dans `data/symbols/<build>/metadata/interface_slots.tsv`
        (`ITargetsSelector 10 SelectTiles 1`, et `ICollection<T>` slot 4 = `Contains`).

        SEMANTIQUE, avec le masque TILE-TARGET `0x806000042` : le caster ne peut se teleporter que
        sur une tuile atteignable en `range` = 2 pas ; et s'il y a quelqu'un dessus, l'ECHANGE exige
        la MEME EMPREINTE des deux cotes (`GetFeetCount` = `GetUnitFeetIds(unit).Count`, le NOMBRE de
        pieds -- pas une taille de stat). Un heros a 1 pied ne peut donc pas echanger sa place avec
        une MoW multi-hex, et inversement.

        ⚠ `ignoreUnitsOnTiles = 1`, LU au call-site (`CONCAT71(..., 1)` en 6e argument) -- c'est le
        SEUL des call-sites portes qui le pose. Il desarme le `IsFreeTile(allowAnyUnit)` du
        `RemoveAll` de `MovementQuery$$AnyOrFillMoveableTiles`, donc l'ensemble rendu inclut les
        tuiles OCCUPEES : sans lui, aucune tuile d'echange ne serait jamais ciblable. Le port le
        propage au noeud `MovableTilesInRange` (qui rend alors le `visited` du BFS, cf. sa docstring).

        ⚠ LE `op_Subtraction` DES ENNEMIS EST INERTE, ET C'EST UNE LECTURE, PAS UN OUBLI.
        `IdunBattleLogic.Entities.DSLSelectors$$Enemies(of, entities, 3)` construit un
        `UnitsByTeamSelector` dont `$$CountOrAdd` alimente son resultat par
        `TargetsSelector$$SelectAllActors` -- lequel RESOUT chaque entite-tuile en son OCCUPANT et
        ajoute l'UNITE. Le membre droit est donc un ensemble d'entites UNITE, tandis que le gauche
        (`MovableTilesInRange`) est un ensemble d'entites TUILE ; or
        `IdunBattle.DSL.CombinedSelector$$SelectExclusion` compare par identite d'entite
        (`ICollection.Contains` sur la liste de droite). Aucune tuile n'y est donc retiree.
        Cote port l'inertie EMERGE de la meme cause -- `Enemies.select` filtre `isinstance(u, dict)`
        et les ids de tuile n'en sont pas -- au lieu d'etre codee : le jour ou le natif changerait de
        domaine, l'arbre porte changerait avec lui. Le `3` est `onlyAlive = true`
        (`DSLSelectors$$Enemies(this, of, entities, onlyAlive)` delegue en `(onlyAlive & 0xff) + 2`).

        `target_id` est un id de TUILE (cast tile-target) : `Contains` se lit donc directement sur
        l'ensemble d'ids que rend le noeud. Tuile hors board / `range` illisible -> `0` (convention
        permissive du module ; le natif, lui, n'atteint cette regle que sur une tuile enumeree)."""
        # #484 : les quatre differes qui vivaient ici etaient GRATUITS au sens de
        # `probe_270r4r2r2` -- leur MODULE cible est deja importe au niveau de CE fichier, donc
        # ni cycle possible ni cout evite. Ils sont HISSES (en tete), pas supprimes : « la cible
        # est deja importee » porte sur le MODULE, pas sur chaque NOM, et seul
        # `entities_from_state` etait un veritable OMBRAGE (homonyme module-level ligne 57, qui
        # rendait le nom local a TOUTE la fonction). Les supprimer tous a d'abord ete essaye et
        # a produit des `NameError` sur `Caster`/`SelectTile`/`Sub`/`unit_of_entity`/
        # `get_feet_count` -- rattrape par le re-jeu (`test_287r5r1_charge_tiles_offline.py`).
        board = getattr(state, "board", None)
        if target_id is None or board is None or int(target_id) not in getattr(board, "by_id", {}):
            return 0
        raw = ((GC.ability(self.ABILITY_ID) or {}).get("constants") or {}).get("range")
        if raw is None:
            return 0
        try:
            rng = int(raw)                              # GetNumberConstant(0x16 = range)
        except (TypeError, ValueError):
            return 0
        # `MovableTilesInRangeSelector$$Select` resout son `unitTileSelector` (+0x28) par
        # `TargetsSelector$$SelectTile` -- UNE tuile de depart, pas l'empreinte (#459).
        pool = MovableTilesInRange(Caster(), SelectTile(CasterTile()), Const(rng),
                                   ignore_flags=True, ignore_units_on_tiles=True)
        # Le natif re-utilise LA MEME instance des deux cotes du `op_Subtraction` (`pvVar6`).
        sel = Sub(pool, Enemies(pool))
        ents = entities_from_state(state, int(caster_id), None)
        if int(target_id) not in {int(t) for t in sel.evaluate(ents)}:
            return int(TR.TargetIsInRange)
        # `UnitExtensions$$GetUnit(target, state@0x18)` : sur une TUILE le natif rend son OCCUPANT
        # (foyer `targeting.unit_of_entity`). Le CASTER lui-meme en fait partie -- le natif ne
        # l'exclut pas, et sur sa propre tuile les deux `GetFeetCount` coincident donc a `0`.
        occupant = unit_of_entity(state, int(target_id))
        if occupant is None:                            # `GetUnit(target) == null` -> 0
            return 0
        if get_feet_count(state, occupant) != get_feet_count(state, int(caster_id)):
            return int(TR.TargetMatchesDynamicRule)
        return 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = getattr(state, "board", None)
        caster = state.get_entity(caster_id)
        if caster is None or board is None:
            return {"quickening": True, "swapped": None, "moved": False}
        origin = _pos(caster)
        target_pos = _tile_pos(state, target_id)
        if target_pos is None or origin is None or target_pos == origin:
            return {"quickening": True, "swapped": None, "moved": False}
        # unite echangee = occupant vivant de la tuile cible (approx `Attackable(Units(Target))`)
        swap_id = _living_unit_id_on(state, target_pos, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)     # porte le bus des Operations (MoveUnit)
        # --- phases 1-2 : SWAP (MoveOut+MoveIn ; effets Untargetable transitoires = net-zero) ---------
        # natif = lift-off (MoveUnit -> Null) puis MoveIn ; MoveUnitOperation pose la position sans check
        # d'occupation -> l'echange direct (caster->target, swap->origin) rend l'etat NET identique.
        # `record_tiles=False` (case-322-r1). Le natif fait un LIFT-OFF (`MoveUnit` vers une
        # `UnitPosition` VIDE, via `IdunBattleLogic.Entities.DSLBehaviors$$MoveUnit` avec un
        # selecteur de tuiles `None()`) puis un MOVE-IN. #347 a relu les deux moities, et
        # l'explication portee ici jusque-la etait FAUSSE (elle attribuait au lift-off la branche
        # degeneree de `CalculatePaths`) :
        #   * LIFT-OFF -> **0 tuile**. `IdunBattle.Operations.MoveUnitOperation$$Execute` teste
        #     `Count(position) == 0` ET l'octet `MoveUnitOptions+0x15` (`allowNullTargetPosition`,
        #     que `GetMoveOutBehaviour` pose via son 6e selecteur d'options) : il retire l'unite du
        #     board et **RETOURNE** par `EvaluateAfterMoveTriggers`, AVANT `CalculatePaths` et
        #     avant tout `RecordTilesMoved`.
        #   * MOVE-IN -> `GetNumTilesMoved(connectedPath)`, avec
        #     `movementStartPosition = GetPreviousPositionThisTurn(unit)` quand la position
        #     COURANTE est vide (elle l'est : l'unite est hors board). Ce champ
        #     (`UnitComponent+0x98`) est ecrit par `IdunBattle.Operations.SetUnitPositionOperation
        #     $$SavePreviousPosition` et efface par `IdunBattle.Entities.Behaviours.
        #     ResetPreviousPositionBehaviour$$Execute` : la quantite facturee depend donc de
        #     l'HISTORIQUE de mouvement du tour, pas seulement de la geometrie du cast. S'il est
        #     vide, `CalculatePaths` prend sa branche `Count(movementStartPosition) == 0` et rend
        #     `[endTile, endTile]` -> 1 tuile.
        # Le port fait l'echange DIRECT (pas de lift-off), donc ce `connectedPath` n'est pas
        # reproductible depuis ce montage, et la valeur native n'est pas MESURABLE non plus (aucun
        # consommateur du compteur n'est atteignable par ce chemin, cf. `docs/rl/
        # case-347-tiles-moved-call-sites.md` SS5). On n'enregistre donc RIEN plutot que de
        # facturer une valeur devinee. RESIDU NOMME `#347-r1` (sous-comptage, jamais
        # sur-comptage).
        # VECTEUR AFTER-MOVE (#448-r1-r1-r2-r1) : `TheQuickeningAbility$$GetMoveInBehaviour` et
        # `$$GetMoveOutBehaviour` sont deux des 30 call-sites de `DSLBehaviors$$MoveUnit` (xrefs
        # exhaustives), donc les deux moities natives passent par `MoveUnitOperation$$Execute` et
        # JOUENT le vecteur. Le port fait l'echange DIRECT (une Operation par unite au lieu de
        # lift-off + move-in), il joue donc UN vecteur par unite la ou le natif en joue deux (celui
        # du lift-off part avec `movementSteps = 0` par la branche « position VIDE »). SOUS-COMPTAGE
        # assume, jamais sur-comptage -- meme sens que le residu `#347-r1` ci-dessus.
        # `arrive_at_final_tile=False` : defaut de feuille DSL (octet `MoveUnitOptions+0x10` = 1 des
        # que le selecteur `MoveUnitBehaviourOptions+0x18` est nul).
        MoveUnitOperation(caster_id, target_pos, record_tiles=False,
                          arrive_at_final_tile=False).execute(state, ectx.bus)
        if swap_id is not None:
            MoveUnitOperation(swap_id, origin, record_tiles=False,
                              arrive_at_final_tile=False).execute(state, ectx.bus)
        # --- phases 4/6 : free melee attack faction-BloodAngels (caster PUIS unite-echangee) ----------
        # config (maxDmg/dmgPct/level/mult) = celle de l'ability de MEPH (le caster) ; Attack = per-unit.
        csc = caster.get_component(StatsComponent)
        level = getattr(csc.ctx, "active_ability_level", None) if csc else None
        mult = int(getattr(csc.ctx, "ability_variables_multiplier", 100) or 100) if csc else 100
        attacks = []
        for uid in ([caster_id] + ([swap_id] if swap_id is not None else [])):
            if _unit_faction(state, uid) != _BLOODANGELS:      # gate HasFaction(unit, 14)
                continue
            a = _free_melee_attack(state, caster_id, uid, level, mult, ectx)
            if a is not None:
                attacks.append(a)
        return {"quickening": True, "caster": caster_id, "target_tile": target_id,
                "to": target_pos, "swapped": swap_id, "moved": True, "attacks": attacks, "dsl": False}
