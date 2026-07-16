"""Ability-triggers du namespace natif `IdunBattleLogic.Entities.Abilities.Tiles.*` — abilities portées
par le TERRAIN (tile-def), pas par une unité. 1 fonction par ability native (VA citée) :
- `DryBushFireSpreadAbility` — propagation du feu entre tuiles DryBush au tick d'environnement.
- `FirstAidHealAbility` (#130) — heal-on-tile au début du tour (à porter).
- `ThornsBlockMovementAbility` (#198) — stat-mod DEFENSE de tuile posé/retiré à l'entrée/sortie."""
from __future__ import annotations

from ...state import State
from ...components import (PositionComponent, UnitComponent, OwnerComponent, StatsComponent,
                          HealthComponent)
from ....entities.traits import UnitTrait, has_trait
from .loki import FIRE_TILE

# Propagation DryBush->DryBush (RE #127, `DryBushFireSpreadAbility`@1811bf5c0/@1811bf730). La proba est le
# `GetNumberConstant(config,0x25)` du tile-ability = globalValue `dryBushFireSpreadProbability` (=10, PAS hardcodé).
DRYBUSH_FIRE_SPREAD_PCT_KEY = "dryBushFireSpreadProbability"  # globalValues=10 : proba/tick d'allumer une voisine DryBush.
DRYBUSH_TERRAIN = "DryBush"       # TileId du terrain DryBush ; seules ces tuiles portent `DryBushFireSpreadAbility`
#   (le filtre natif `TilesWithTriggeredAbility(0x39=DryBushFireSpread=57)` <=> `tile_def_id == 'DryBush'`).


def dry_bush_fire_spread(state: State) -> list[dict]:
    """`DryBushFireSpreadAbility` (CreateTrigger @1811bf730 = `On(0x14) & HasEffect(self@0x148, Fire=5)` ;
    CreateBehaviour @1811bf5c0) — PROPAGATION du feu entre tuiles DryBush au tick d'environnement (`On(0x14)`).
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
      `DefaultAmountOfRounds(5)`=2 (aucun override natif à la pose, cf. `OnFireDamageAbility`@1811c3a60).

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
    from ..effects import AddEffectOperation                # lazy : évite le cycle triggers<->effects
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
    """`FirstAidHealAbility` (Abilities.Tiles, CreateBehaviour @1811c0490 = `AddEffect(tile, 10=FirstAidHealEffect)`)
    + `FirstAidHealEffect` : trigger `CreateTargetTrigger @180f44250` = `On(0x13) & IsTurnOf(Units(units-on-tile))` ;
    behaviour `CreateTargetTriggerBehaviour @180f44090` (LU) = `Heal(tiles, targets, amount)` avec
    `amount = PercentageOf(StatAmount(target, Health=5, Initial=2)=maxHP, Direct(GetNumberConstant(config,0x13)=
    firstAidRecovery%))` et `targets = Tiles(UnitsWithoutTrait(Units(tile), 0x19=25=Immune)) & targetSelector@0x88`.

    Au DÉBUT DU TOUR du `player_id` (event 0x13 émis par `StartTurnOperation.Execute @180ea3fb0`), chaque unité
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
    from ..heal import HealUnitOperation                         # lazy : primitive de soin runner (#94)
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
# `ThornsBlockMovementAbility.CreateBehaviour @1811c8d70` (nom INTERNE de l'ability ; assignée par la tile-
# config Unity au tile-def **Swamp**, PAS à un terrain "Thorns" — aucun board n'a de tileDefId "Thorns", et
# la description localisée est `SwampBlockMovement @1809cdf10`) = `AddBlockEnteringUnitsEffect(#131)` &
# `AddStaticStatModifierEffectToOwner(0xb, stat 3=DEFENSE, Direct(GetNumberConstant(config, 0x14)))`.
# L'effet concret `ThornsDefenseReductionEffect` (`CreateTargetSelector @180f47ea0` =
# `UnitsWithoutTrait(Units(tile,1,3), Immune=25)`) pose la réduction DEFENSE sur l'occupant NON-Immune de
# la tuile ; #197 en consomme la face combat (fold DEFENSE -> ×1.5). #198 = la matérialisation DYNAMIQUE :
# gagner/perdre la modification en ENTRANT/SORTANT de la tuile pendant le runner-sim. ⚠ #194/#197 nommaient
# ce terrain "Thorns" (hypothèse nom-d'ability -> terrain) ; la marche live (probe_198_map) l'a RÉFUTÉ.
#
# HARDCODE (source Unity asset, NON dérivable offline) : la constante `GetNumberConstant(config, 0x14)` vit
# dans une Unity asset config (`IdunUniverse.GetTileConfigurations @1807a7d60`), ABSENTE du gameconfig JSON
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
    from ....entities.stats import StatType, CAPTURED_SOURCE
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
