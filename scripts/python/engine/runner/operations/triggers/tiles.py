"""Ability-triggers du namespace natif `IdunBattleLogic.Entities.Abilities.Tiles.*` — abilities portées
par le TERRAIN (tile-def), pas par une unité. 1 fonction par ability native (VA citée) :
- `DryBushFireSpreadAbility` — propagation du feu entre tuiles DryBush au tick d'environnement.
- `FirstAidHealAbility` (#130) — heal-on-tile au début du tour (à porter).
- `ThornsBlockMovementAbility` (#198) — stat-mod DEFENSE de tuile posé/retiré à l'entrée/sortie.
- `LightCoverAbility` (résidu O3) — pose de l'effet de couverture 1013 à l'ENTRÉE sur la tuile."""
from __future__ import annotations

from ...state import State
from ...components import (PositionComponent, UnitComponent, OwnerComponent, StatsComponent,
                          HealthComponent)
from ....entities.traits.unit_trait import UnitTrait, has_any_trait, has_trait
from .loki import FIRE_TILE
from ....entities.effect_type import EffectType
from ....entities.effects.loki.hits import LIGHT_COVER_TILE_ID
from ....entities.stats import StatType, CAPTURED_SOURCE
from ..effects import AddEffectOperation
from ..heal import HealUnitOperation

# Propagation DryBush->DryBush (RE #127, `DryBushFireSpreadAbility`IdunBattleLogic.Entities.Abilities.Tiles.DryBushFireSpreadAbility$$CreateBehaviour/IdunBattleLogic.Entities.Abilities.Tiles.DryBushFireSpreadAbility$$CreateTrigger). La proba est le
# `GetNumberConstant(config,0x25)` du tile-ability = globalValue `dryBushFireSpreadProbability` (=10, PAS hardcodé).
DRYBUSH_FIRE_SPREAD_PCT_KEY = "dryBushFireSpreadProbability"  # globalValues=10 : proba/tick d'allumer une voisine DryBush.
DRYBUSH_TERRAIN = "DryBush"       # TileId du terrain DryBush ; seules ces tuiles portent `DryBushFireSpreadAbility`
#   (le filtre natif `TilesWithTriggeredAbility(0x39=DryBushFireSpread=57)` <=> `tile_def_id == 'DryBush'`).


def dry_bush_fire_spread(state: State) -> list[dict]:
    """`DryBushFireSpreadAbility` (IdunBattleLogic.Entities.Abilities.Tiles.DryBushFireSpreadAbility$$CreateTrigger = `On(0x14) & HasEffect(self@0x148, Fire=5)` ;
    IdunBattleLogic.Entities.Abilities.Tiles.DryBushFireSpreadAbility$$CreateBehaviour) — PROPAGATION du feu entre tuiles DryBush au tick d'environnement (`On(0x14)`).
    Chaque tuile DryBush EN FEU tente d'allumer ses voisines DryBush intactes :

        Maybe(SetOnFire,
              AdjacentTiles(self@0x148) & TilesWithTriggeredAbility(0x39=DryBushFireSpread=57)
                                        & EntitiesWithoutEffects(Fire=5),
              chance = GetNumberConstant(config, 0x25) = globalValues `dryBushFireSpreadProbability` = 10)

    - SOURCE = tuile DryBush en feu. Seules les tuiles DryBush portent `DryBushFireSpreadAbility` (le trigger
      gate `HasEffect(self,5)`) → une tuile NON-DryBush en feu (ex. Grass allumée par `OnFireDamageAbility`) ne
      propage PAS. Le filtre cible natif `TilesWithTriggeredAbility(0x39)` <=> `tile_def_id == 'DryBush'`.
    - TARGET = voisine hex DryBush SANS `FireEffect` (idempotence via `AddEffectOperation`, no-op si déjà en feu).
    - 1 `next_bool(10)` par voisine (`Maybe` per-cible, MÊME motif que `FireOfAbsolution`). Durée du feu posé =
      `DefaultAmountOfRounds(5)`=2 (aucun override natif à la pose, cf. `OnFireDamageAbility`IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour).

    SNAPSHOT : l'ensemble des tuiles en feu est figé en début de tick → une tuile allumée CE tick ne propage
    pas à son tour le MÊME tick (le trigger natif gate `HasEffect(self,5)` à l'instant du dispatch). ⚠ GAP RNG
    (flaggé, comme `FireOfAbsolution`) : l'ORDRE des tirages `next_bool` (par tuile-source puis par voisine) et
    vs les autres consommateurs RNG du tick 0x14 n'est PAS calibré bit-exact → la propagation est stochastique,
    non reproductible coup-pour-coup. No-op si pas de board/effects/rng ou aucune tuile DryBush en feu."""
    if state.board is None or state.effects is None or state.rng is None:
        return []
    import gameconfig as GC
    prob = int(GC.global_value(DRYBUSH_FIRE_SPREAD_PCT_KEY) or 0)   # dryBushFireSpreadProbability = 10 (non hardcodé)
    if prob <= 0:
        return []
    # SNAPSHOT source : tuiles DryBush actuellement en feu (seules les DryBush portent l'ability de propagation).
    burning = [tid for tid, t in state.board.by_id.items()
               if t.get("tileDefId") == DRYBUSH_TERRAIN
               and state.effects.has_effect(tid, effect_type=FIRE_TILE)]
    if not burning:
        return []
    out: list[dict] = []
    for tid in burning:
        for nid in state.board.neighbours(tid):            # AdjacentTiles(self) = voisins hex du board (géométrie)
            if state.board.tile_def_id(nid) != DRYBUSH_TERRAIN:       # TilesWithTriggeredAbility(DryBushFireSpread=57)
                continue
            if state.effects.has_effect(nid, effect_type=FIRE_TILE):  # EntitiesWithoutEffects(Fire=5) : déjà en feu → skip
                continue
            if not state.rng.next_bool(prob):              # Maybe(chance=dryBushFireSpreadProbability)
                continue
            if AddEffectOperation.execute(state, source=tid, target=nid,
                                          effect_type=FIRE_TILE, name="Fire") is not None:  # durée _DEFAULT_ROUNDS[5]=2
                out.append({"tile_effect": "Fire", "spread_to_tile": nid, "from_tile": tid,
                            "placement": "DryBushFireSpread"})
    return out


# firstAidRecovery = GetNumberConstant(FirstAidHeal.config, 0x13) mirroté à la globalValue NOMMÉE (=35), MÊME
# pattern que fireDmgPct=GetNumberConstant(0x12) : l'ordre JSON des globalValues NE mappe PAS l'enum NumberConstant
# (vérifié), la résolution se fait par NOM. Confirmé LIVE (heal observé = 35 % maxHP).
FIRSTAID_RECOVERY_KEY = "firstAidRecovery"   # % de la maxHP soigné au début du tour sur une tuile FirstAid.
FIRSTAID_HEAL_EXCLUDE_TRAIT = UnitTrait.Immune   # `UnitsWithoutTrait(0x19=25=Immune)` : exclut les immunisés au heal.


def first_aid_heal(state: State, player_id: int) -> list[dict]:
    """`FirstAidHealAbility` (Abilities.Tiles, IdunBattleLogic.Entities.Abilities.Tiles.FirstAidHealAbility$$CreateBehaviour = `AddEffect(tile, 10=FirstAidHealEffect)`)
    + `FirstAidHealEffect` : trigger `IdunBattle.Entities.Effects.FirstAidHealEffect$$CreateTargetTrigger` = `On(0x13) & IsTurnOf(Units(units-on-tile))` ;
    behaviour `IdunBattle.Entities.Effects.FirstAidHealEffect$$CreateTargetTriggerBehaviour` (LU) = `Heal(tiles, targets, amount)` avec
    `amount = PercentageOf(StatAmount(target, Health=5, Initial=2)=maxHP, Direct(GetNumberConstant(config,0x13)=
    firstAidRecovery%))` et `targets = Tiles(UnitsWithoutTrait(Units(tile), 0x19=25=Immune)) & targetSelector@0x88`.

    Au DÉBUT DU TOUR du `player_id` (event 0x13 émis par `IdunBattle.Operations.StartTurnOperation$$Execute`), chaque unité
    VIVANTE du player posée sur une tuile FirstAid (hors trait Immune=25) est soignée de `firstAidRecovery`% (=35,
    globalValue) de sa maxHP. Le soin passe par `HealUnitOperation` (clamp maxHP + gate Cursed). `IsTurnOf` =
    l'occupant appartient au player courant (l'ennemi debout sur une tuile FirstAid n'est PAS soigné à MON tour).
    Tuiles FirstAid = terrain STATIQUE (`board.coords_with_terrain('FirstAid')`, `tileDefId`). No-op sans board /
    healPct / occupant. Reste à confirmer LIVE (board FirstAid + unité du player dessus au StartTurn -> heal 35%)."""
    board = getattr(state, "board", None)
    if board is None:
        return []
    coords = board.coords_with_terrain("FirstAid")
    if not coords:
        return []
    import gameconfig as GC
    healpct = int(GC.global_value(FIRSTAID_RECOVERY_KEY) or 0)   # 35 : GetNumberConstant(FirstAidHeal, 0x13)
    if healpct <= 0:
        return []
    out: list[dict] = []
    for (col, row) in coords:
        # occupant VIVANT de la tuile appartenant au player courant (`IsTurnOf(units-on-tile)`).
        uid = None
        for eid, e in state.entities.items():
            pc = e.get_component(PositionComponent)
            if pc is None or (pc.col, pc.row) != (col, row):
                continue
            uc = e.get_component(UnitComponent)
            if uc is not None and not uc.alive:
                continue
            oc = e.get_component(OwnerComponent)
            if oc is None or oc.player != int(player_id):       # IsTurnOf : unité du player courant seulement
                continue
            uid = int(eid)
            break
        if uid is None:
            continue
        e = state.get_entity(uid)
        sc = e.get_component(StatsComponent) if e is not None else None
        if sc is not None and has_trait(sc.ctx.traits, FIRSTAID_HEAL_EXCLUDE_TRAIT):  # UnitsWithoutTrait(0x19=Immune)
            continue
        thc = e.get_component(HealthComponent) if e is not None else None
        if thc is None or thc.hp_max is None:
            continue
        amount = round(int(thc.hp_max) * healpct / 100)         # PercentageOf(maxHP, firstAidRecovery%)
        tile_id = board.id_at(col, row)                          # source = la tuile FirstAid
        healed = HealUnitOperation.execute(state, uid, amount, source_id=tile_id)
        if healed > 0:
            out.append({"tile_effect": "FirstAid", "tile": tile_id, "unit": uid,
                        "heal": healed, "pct": healpct, "on_event": 0x13})
    return out


# --- Swamp (et famille) : stat-mod DEFENSE de tuile statique (#198) --------------------------------
# `IdunBattleLogic.Entities.Abilities.Tiles.ThornsBlockMovementAbility$$CreateBehaviour` (nom INTERNE de l'ability ; assignée par la tile-
# config Unity au tile-def **Swamp**, PAS à un terrain "Thorns" — aucun board n'a de tileDefId "Thorns", et
# la description localisée est `SwampBlockMovement idun.shared.utils.IdunLocalization.Abilities$$SwampBlockMovementDescription`) = `AddBlockEnteringUnitsEffect(#131)` &
# `AddStaticStatModifierEffectToOwner(0xb, stat 3=DEFENSE, Direct(GetNumberConstant(config, 0x14)))`.
# L'effet concret `ThornsDefenseReductionEffect` (`IdunBattle.Entities.Effects.ThornsDefenseReductionEffect$$CreateTargetSelector` =
# `UnitsWithoutTrait(Units(tile,1,3), Immune=25)`) pose la réduction DEFENSE sur l'occupant NON-Immune de
# la tuile ; #197 en consomme la face combat (fold DEFENSE -> ×1.5). #198 = la matérialisation DYNAMIQUE :
# gagner/perdre la modification en ENTRANT/SORTANT de la tuile pendant le runner-sim. ⚠ #194/#197 nommaient
# ce terrain "Thorns" (hypothèse nom-d'ability -> terrain) ; la marche live (probe_198_map) l'a RÉFUTÉ.
#
# HARDCODE (source Unity asset, NON dérivable offline) : la constante `GetNumberConstant(config, 0x14)` vit
# dans une Unity asset config (`idun.IdunUniverse$$GetTileConfigurations`), ABSENTE du gameconfig JSON
# (vérifié : `GC.ability(...)` = None, aucun globalValue). Valeur + terrain CAPTÉS LIVE par marche multi-
# terrain (probe_198_map, C2_19) : `{Grass:0, Trench:0, DryBush:0, Swamp:-50}` → seule **Swamp** porte le
# stat-mod DEFENSE (**−50**), générique au tile-def (jakhal DEFENSE 50 vs base 100). À RE-CAPTURER si les
# assets tuile changent (spécifique au hash de build, comme les dumps Il2CppDumper). Signe négatif =
# réduction. La FAMILLE (DryBush/Shrub bonus #126 — mesurés à 0 ici, donc INACTIFS/non-DEFENSE ; SpiderWeb)
# a des signes/constantes PROPRES : HORS table = no-op fidèle tant qu'un board/scénario ne les mesure pas
# (ne JAMAIS deviner un signe/valeur ; ajouter une entrée dès qu'une constante est captée live).
TILE_DEFENSE_STAT_MODS = {"Swamp": -50}   # tile_def_id -> delta DEFENSE (AStaticStatModifierEffect, stat 3)
TILE_DEFENSE_EXCLUDE_TRAIT = UnitTrait.Immune   # `UnitsWithoutTrait(Units(tile), 0x19=25=Immune)`


def tile_defense_mod(terrain: str | None) -> int:
    """Delta DEFENSE (`AStaticStatModifierEffect` stat 3) qu'une tuile `terrain` pose sur son occupant
    non-Immune. 0 si le terrain n'a pas de stat-mod DEFENSE connu (mirror : pas de
    `ThornsDefenseReductionEffect` -> aucune contribution). Seule Swamp est captée (cf. table)."""
    return TILE_DEFENSE_STAT_MODS.get(terrain or "", 0)


def apply_tile_defense_on_move(state: State, unit_id: int,
                               from_pos: tuple | None, to_pos: tuple) -> dict | None:
    """#198 — matérialise le stat-mod DEFENSE de tuile à la transition `from_pos`->`to_pos`, mirror
    apply-on-enter / revert-on-leave de `ThornsDefenseReductionEffect`.

    L'occupant non-Immune d'une tuile à stat-mod DEFENSE (Thorns…) porte `tile_defense_mod(terrain)` sur sa
    DEFENSE. À la transition, on ajoute au TOTAL DEFENSE la **différence** `tile_defense_mod(to) −
    tile_defense_mod(from)`. Le −X cuit au LOAD (unité DÉJÀ sur la tuile) vit dans le lump `CAPTURED_SOURCE`
    de sa `ValueModification` DEFENSE (résidu `seed_unit_stats`) — l'y ajuster maintient l'invariant
    UNIFORMÉMENT (unité déjà-posée ET unité entrante), sans toucher le seeding partagé prédiction (#197
    intact) : la face combat/from_state relit `ctx.stats[DEFENSE]` muté. Le fold #197
    (`calculate_modifiers_from_stat_modifications`) somme les contributions par-source ⇒ un `captured` ajusté
    reste un unique `EffectBonus` ; retombe à 0 (`reverse_modification`) quand l'unité quitte tout terrain à
    stat-mod ⇒ le gate `Current==Initial` du fold rend ×1.0. Gate Immune (mirror `UnitsWithoutTrait`).
    No-op (`None`) sans board / hors terrain à stat-mod (delta nul) / unité Immune / pas de composant DEFENSE."""
    board = state.board
    if board is None:
        return None
    from_terr = board.terrain_at(from_pos[0], from_pos[1]) if from_pos is not None else None
    to_terr = board.terrain_at(to_pos[0], to_pos[1])
    delta = tile_defense_mod(to_terr) - tile_defense_mod(from_terr)
    if delta == 0:                                   # transition sans changement de stat-mod DEFENSE
        return None
    e = state.get_entity(unit_id)
    sc = e.get_component(StatsComponent) if e is not None else None
    if sc is None or getattr(sc, "ctx", None) is None:
        return None
    if has_trait(sc.ctx.traits, TILE_DEFENSE_EXCLUDE_TRAIT):   # `UnitsWithoutTrait(Immune)` : Immune exclu
        return None
    comp = sc.ctx.stats.components.get(int(StatType.DEFENSE))
    if comp is None:
        return None
    cur = comp.modification.per_source.get(CAPTURED_SOURCE, 0)
    new = cur + delta
    if new == 0:
        comp.modification.reverse_modification(CAPTURED_SOURCE)   # plus de résidu -> retrait exact
    else:
        comp.modification.modify(CAPTURED_SOURCE, new)
    return {"tile_defense": unit_id, "from": from_terr, "to": to_terr,
            "delta": delta, "defense_now": comp.get_current_value()}


# --- LightCover (DryBush) : pose de l'effet de couverture a l'ENTREE sur la tuile (residu O3) -------
# `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$.cctor` remplit la liste STATIQUE de
# `UnitTrait` EXCLUS lue par le `UnitsWithoutTraits` de `UnitsThatNeedEffect` : `Add(0x3f9)` `Add(0x405)`
# `Add(0)` = **BigTarget(1017), Vehicle(1029), Mounted(0)** -- ces unites ne beneficient PAS du cover.
LIGHT_COVER_EXCLUDED_TRAITS = (UnitTrait.BigTarget, UnitTrait.Vehicle, UnitTrait.Mounted)


def light_cover_on_enter(state: State, mover_id: int) -> list[dict]:
    """`LightCoverAbility` (Abilities.Tiles.Loki) — MIRROR 1:1 du decompile (build `gqfc5mff6c`) :

        `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$CreateTrigger` =
            ( On(0x19=MatchInit) | On(0x32=UnitAdded) | On(0x24=UnitPositionChanged_1)
              | On(0x2d=UnitRevived) | On(0x2e=UnitResurrected) )
            & NOT AmountIsZero( UnitsThatNeedEffect )
        `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$CreateBehaviour` =
            AddEffect( 0x3f5 = 1013 LightCover, AbilityStateReference, UnitsThatNeedEffect )
        `IdunBattleLogic.Entities.Abilities.Tiles.Loki.LightCoverAbility$$UnitsThatNeedEffect` =
            UnitsWithoutTraits( EntitiesWithoutEffects( Units(coverPatch@0x148, 1, 3), [0x3f5] ),
                                <liste statique du cctor>, 3 )

    C'est la face MANQUANTE du residu O3 (evolution des effets de TUILE) : le gate compute-time
    `AreEqual(coverPatch, target)` de `IdunBattle.Entities.Effects.Loki.LightCoverEffect$$CreateEffect
    HitsBonusForAttack` (porte, cf. `entities/effects/loki/hits.py`) neutralise deja l'effet quand
    l'unite QUITTE le cover -- c'est le comportement natif (ground truth live : l'effet est CONSERVE,
    seul le gate tombe). Mais rien ne le POSAIT quand une unite ENTRE sur une tuile de cover pendant
    le runner-sim : le seed ne connait que les unites deja posees au chargement. Sans ce vecteur, une
    cible qui court se mettre a couvert continuait d'encaisser tous ses coups ranged.

    VECTEUR : `On(0x24 = UnitPositionChanged_1)`, le PREMIER des trois events qu'emet
    `IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers` (0x24 -> 0x4 -> 0x1d) --
    d'ou l'appel en TETE d'`after_move_triggers`. `coverPatch@0x148` = la tuile PORTEUSE de l'ability,
    identifiee par son `tileDefId` (`LIGHT_COVER_TILE_ID` = "DryBush", le seul terrain hote sur ce
    build) : la tuile CONCERNEE par le move est celle ou le mover vient d'arriver.

    DUREE : la surcharge `AddEffect` a 4 arguments ne passe AUCUN noeud de duree ->
    `DefaultAmountOfRounds(1013)` est NULL (1013 hors table) -> duree 0 = **PERMANENT**, exactement ce
    que rend le capteur live (`remaining = 0`). Le retrait n'est donc PAS un timer : c'est le gate
    compute-time. No-op si pas de board / hors tuile de cover / mover mort / trait exclu / effet deja
    present (`EntitiesWithoutEffects(0x3f5)`, redondant avec le gate deja-present d'`AddEffectOperation`
    mais mirrore explicitement)."""
    board = state.board
    if board is None or state.effects is None:
        return []
    e = state.get_entity(mover_id)
    pc = e.get_component(PositionComponent) if e is not None else None
    if pc is None:
        return []
    uc = e.get_component(UnitComponent)
    if uc is not None and not uc.alive:
        return []
    if board.terrain_at(pc.col, pc.row) != LIGHT_COVER_TILE_ID:   # `coverPatch` = la tuile porteuse
        return []
    sc = e.get_component(StatsComponent)
    traits = getattr(sc.ctx, "traits", None) if sc is not None else None
    if has_any_trait(traits or [], LIGHT_COVER_EXCLUDED_TRAITS):  # `UnitsWithoutTraits(<cctor>)`
        return []
    et = int(EffectType.LightCover)                                # 0x3f5 = 1013
    if state.effects.has_effect(mover_id, effect_type=et):         # `EntitiesWithoutEffects(0x3f5)`
        return []
    tile_id = board.id_at(pc.col, pc.row)
    eff = AddEffectOperation.execute(state, source=tile_id, target=mover_id,
                                     effect_type=et, name="LightCover")
    if eff is None:
        return []
    return [{"tile_effect": "LightCover", "tile": tile_id, "unit": int(mover_id),
             "on_event": 0x24}]
