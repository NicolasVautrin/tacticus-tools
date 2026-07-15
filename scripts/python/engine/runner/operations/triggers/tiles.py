"""Ability-triggers du namespace natif `IdunBattleLogic.Entities.Abilities.Tiles.*` — abilities portées
par le TERRAIN (tile-def), pas par une unité. 1 fonction par ability native (VA citée) :
- `DryBushFireSpreadAbility` — propagation du feu entre tuiles DryBush au tick d'environnement.
- `FirstAidHealAbility` (#130) — heal-on-tile au début du tour (à porter)."""
from __future__ import annotations

from ...state import State
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
