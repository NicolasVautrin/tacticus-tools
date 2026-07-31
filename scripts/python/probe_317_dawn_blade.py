#!/usr/bin/env python
"""Probe #317 -- MONTAGE NOMME de `DawnBlade_HealAbility` (1re tranche de l'inventaire des 13
appelants de `IdunBattleLogic.Entities.DSLBehaviors$$Repair`).

LE PIEGE QUE CE MONTAGE VERROUILLE. La classe native s'appelle `DawnBlade_HealAbility` et lit la
variable `hpToHeal` (`AbilityVariableType` 0x20) -- mais elle construit un
`IdunBattleLogic.Entities.DSLBehaviors$$Repair(..., RepairBehaviourOptions$$ForRepair)`. La voie
d'execution est donc `IdunBattle.Operations.RepairUnitOperation$$Execute`, PAS `HealUnitOperation`.
Les deux Operations finissant sur le MEME `FillUpStatComponent$$FillUp`, un mauvais cablage serait
INVISIBLE en regime nominal : il ne se voit qu'aux etages qui les separent. D'ou les regimes R3/R4.

--------------------------------------------------------------------------- POURQUOI OFFLINE

Le montage est OFFLINE et deterministe (State nu + board REEL, zero RNG, zero runner) : la question
posee ici est « le cablage et les ETAGES sont-ils les bons », et elle se tranche sur un `State` --
exactement comme `probe_301_kill_unit_trigger_channels.py`.

⚠ MISE A JOUR #357. Ce probe disait aussi « `DawnBlade` n'a AUCUN porteur confrontable par le
harnais », et c'etait vrai a l'ecriture :
  * les 5 porteurs qui l'ont EN DUR (`gameconfig.relicAbilities`) sont des npc, et le sondage
    `--pool` ci-dessous MESURE que `tauNpcFarsight` injecte au catalogue **ne passe pas** la
    normalisation `buildNormalizedBC` au rank 17 -> il n'entre pas au pool spawnable ;
  * le seul porteur non-npc, `tauFarsight`, l'obtient par l'item relique `R_Crit_DawnBlade`,
    materialise dans `BattleConfiguration.Units[].TertiaryAbility` -- canal qu'aucun rail ne lisait.
Les DEUX obstacles sont leves : #237 pose la relique (injection catalogue + `--equip-relic`), #357
la fait LIRE. La confrontation live vit dans `probe_357_relic_rail.py`. Le sondage `--pool` reste
ici parce que sa reponse (le npc ne se normalise pas) est TOUJOURS vraie -- seule sa CONCLUSION
« donc aucun porteur confrontable » ne l'est plus.

--------------------------------------------------------------------------- LES REGIMES

  R0  NOMINAL   porteur BLESSE, kill en MELEE            -> repaired == hpToHeal[lvl]
  R1  GATE      porteur a PV PLEINS, kill en MELEE       -> repaired == 0
                `AttackQuery$$EntityCanBeRepaired` : `IsDamagedUnit` faux, `removeEffects` vrai mais
                aucun effet negatif, pas de flag 0x18 -> REFUS. ⚠ Contraste `LivingMetal`, ou le
                gate etait TAUTOLOGIQUE (son `CreateTrigger` porte un `IsDamaged(self)` qui le
                garantissait) : ici le `CreateTrigger` n'en a PAS, donc le gate MORD pour de vrai.
  R2  RANGED    porteur BLESSE, kill a DISTANCE          -> le trigger ne MATCHE pas
                (`IsDefeatedByMeleeAttack`)
  R3  CURSED    porteur BLESSE + `EffectType.Cursed` (79) -> repaired == hpToHeal[lvl]
                `HealUnitOperation$$Execute` fait `HasEffect(target, 0x4f)` et force 0 ;
                `RepairUnitOperation$$Execute` n'a AUCUN test de ce type. C'EST LE DISCRIMINANT :
                le seul regime ou heal et repair rendent des valeurs DIFFERENTES sur un porteur sain
                par ailleurs.
  R4  MODIFIER  porteur BLESSE + `NanoscarabRepairProtocols` (1545) -> repaired > hpToHeal[lvl]
                le `RepairModifier` de `DamagePrediction$$PredictRepair` ne vit que sur la voie
                repair. 2e discriminant, CHIFFRE.

--------------------------------------------------------------- CONTRE-EPREUVE (`--mutate heal`)

Rebranche la feuille sur `HealUnitOperation` (la faute #310, transposee ici). R3 et R4 doivent
ROUGIR ; R0/R1/R2 restent verts -- et c'est precisement pourquoi un montage qui ne testerait que le
montant nominal ne prouverait RIEN.

Reproduire :

    cd scripts/python
    python probe_317_dawn_blade.py
    python probe_317_dawn_blade.py --mutate heal
    python probe_317_dawn_blade.py --pool        # sondage de confrontabilite (session live requise)

Sorties dans `logs/` (chemin RELATIF, jamais `data/`). ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
_ROOT = _PYDIR.parents[1]

CARRIER = "tauNpcFarsight"        # `gameconfig.relicAbilities = ['DawnBlade']` (les 5 npc Farsight)
VICTIM = "orksNob"
BOARD_ID = "MC1_67"
DAWN_BLADE_TRIGGERED_ID = 1501    # `TriggeredAbilityType.DawnBlade`
CURSED_EFFECT_TYPE = 79           # `EffectType.Cursed` -- gate EXCLUSIF du soin
NANOSCARAB_EFFECT_TYPE = 1545     # `NanoscarabRepairProtocolsEffect` -- `RepairBonus` ForAddition
NANOSCARAB_EFFECT_NAME = "NanoscarabRepairProtocols"
RANK = 17

MUTATIONS = ("heal",)


def _board():
    """Board REEL (`MC1_67`), en adjacence `evenq` -- la meme construction que `probe_120`."""
    import board as B
    from engine.entities.pathfinding import Board as EngineBoard
    p = _ROOT / "data" / "boards" / "global" / (BOARD_ID + ".json")
    dump = json.loads(p.read_text(encoding="utf-8"))
    bd = B.Board({"Board": dump["board"], "SpawnPointSetIndex": dump.get("spawnPointsSet", 0)})
    tiles = []
    for i, (col, row) in enumerate(sorted(bd.playable_tiles())):
        t = bd.tile(col, row) or {}
        tiles.append({"id": i + 1, "col": col, "row": row, "walkable": True,
                      "tileDefId": t.get("tileId"), "elevation": t.get("elevation")})
    return EngineBoard(tiles, adjacency="evenq")


def _add_unit(state, vid, col, row, team, player, hp, hp_max, alive=True):
    import gameconfig as GC
    from engine.runner.components import (UnitComponent, OwnerComponent, StatsComponent,
                                          HealthComponent, PositionComponent)
    from engine.entities.unit_context import UnitContext
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=vid, alive=alive))
    e.add_component(OwnerComponent(team=team, player=player))
    ctx = UnitContext(entity_id=e.id, visual_id=vid, active_ability_level=50,
                      passive_ability_level=50, ability_variables_multiplier=100)
    ctx.traits = list((GC.unit(vid) or {}).get("traits") or [])
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
    e.add_component(PositionComponent(col=col, row=row))
    return e.id


def _scene(carrier_hp, carrier_max, victim_col, victim_row, effects=()):
    """Le porteur en (2,2), la victime DEJA MORTE en `(victim_col, victim_row)`.

    On ne TUE pas la victime : on draine le vecteur `On(UnitDeath = 0)` sur un etat ou elle est deja
    `alive = False` -- meme choix que `probe_301` (le montage teste le TRIGGER, pas le pipeline de
    degat qui l'emet)."""
    from engine.runner.state import State
    from engine.entities import EffectsState
    state = State()
    state.board = _board()
    state.effects = EffectsState.seed({})
    carrier = _add_unit(state, CARRIER, 2, 2, team=1, player=3, hp=carrier_hp, hp_max=carrier_max)
    victim = _add_unit(state, VICTIM, victim_col, victim_row, team=2, player=4,
                       hp=0, hp_max=10000, alive=False)
    for name, etype, level in effects:
        from engine.entities.effects import EffectFactory
        state.effects.add_effect(carrier, EffectFactory.create(
            {"name": name, "effectType": etype, "level": level, "source": carrier},
            ability_variables_multiplier=100))
    return state, carrier, victim


def _fire(state, carrier, victim) -> list:
    """Emet `On(UnitDeath = 0)` avec `actor = killer = carrier`, `target = dying = victim`."""
    from engine.runner.operations.triggers import unit_death_triggers
    return unit_death_triggers(state, victim, carrier) or []


def _dawn_events(out: list) -> list:
    return [e for e in out if isinstance(e, dict) and e.get("relic") == "DawnBlade"]


def _patch_heal():
    """MUTATION : la feuille `Repair` appelle `HealUnitOperation` au lieu de `RepairUnitOperation`.

    On remplace `RepairUnitOperation.execute` par une delegation au soin -- c'est EXACTEMENT la faute
    #310 (`LivingMetal` cable sur le soin), transposee sur cette tranche. La cle de retour est
    conservee pour que seuls les ETAGES rougissent, jamais un renommage."""
    from engine.runner.operations import repair as RP
    from engine.runner.operations.heal import HealUnitOperation
    saved = RP.RepairUnitOperation.execute

    @staticmethod
    def _as_heal(state, caster_id, target_id, amount, scope=0, remove_effects=False):
        return HealUnitOperation.execute(state, target_id, int(amount))
    RP.RepairUnitOperation.execute = _as_heal
    return lambda: setattr(RP.RepairUnitOperation, "execute", saved)


def run(mutate=None) -> dict:
    """Joue les 5 regimes et rend le releve. Ne LEVE pas : c'est l'appelant (le test) qui juge."""
    assert mutate in (None,) + MUTATIONS, "mutation inconnue : %s" % (mutate,)
    from engine.runner.operations.triggers.loki.dawn_blade import hp_to_heal
    undo = _patch_heal() if mutate == "heal" else (lambda: None)
    res: dict = {"mutate": mutate}
    try:
        # R0 NOMINAL -- victime ADJACENTE (2,1) au porteur (2,2) en evenq.
        st, car, vic = _scene(2000, 100000, 2, 1)
        from engine.runner.components import HealthComponent
        res["amount"] = hp_to_heal(st, car)
        ev = _dawn_events(_fire(st, car, vic))
        res["R0"] = {"events": len(ev), "repaired": (ev[0]["repaired"] if ev else 0),
                     "hp_after": st.get_entity(car).get_component(HealthComponent).hp}
        # R1 GATE -- porteur a PV PLEINS.
        st, car, vic = _scene(100000, 100000, 2, 1)
        ev = _dawn_events(_fire(st, car, vic))
        res["R1"] = {"events": len(ev), "repaired": (ev[0]["repaired"] if ev else 0)}
        # R2 RANGED -- victime NON adjacente (2,6).
        st, car, vic = _scene(2000, 100000, 2, 6)
        ev = _dawn_events(_fire(st, car, vic))
        res["R2"] = {"events": len(ev), "repaired": (ev[0]["repaired"] if ev else 0)}
        # R3 CURSED -- `EffectType.Cursed` (79) sur le PORTEUR : le SOIN l'annule, la REPARATION non.
        st, car, vic = _scene(2000, 100000, 2, 1, effects=(("Cursed", CURSED_EFFECT_TYPE, 1),))
        ev = _dawn_events(_fire(st, car, vic))
        res["R3"] = {"events": len(ev), "repaired": (ev[0]["repaired"] if ev else 0)}
        # R4 MODIFIER -- `NanoscarabRepairProtocols` (1545) sur le PORTEUR : `RepairModifier` de
        # `PredictRepair`, ignore par le soin.
        st, car, vic = _scene(2000, 100000, 2, 1,
                              effects=((NANOSCARAB_EFFECT_NAME, NANOSCARAB_EFFECT_TYPE, 50),))
        ev = _dawn_events(_fire(st, car, vic))
        res["R4"] = {"events": len(ev), "repaired": (ev[0]["repaired"] if ev else 0)}
    finally:
        undo()
    return res


def pool_probe() -> int:
    """Sondage de CONFRONTABILITE : `tauNpcFarsight` injecte entre-t-il au pool normalise ?

    Rend sa reponse au lieu de la supposer. Session live requise (RPC `buildNormalizedBC`)."""
    sys.path.insert(0, str(_PYDIR))
    import catalog_inject as CI
    import rl_collect_batch as R
    out = _ROOT / "logs" / ("probe_317_dawn_blade-%d" % os.getpid())
    out.mkdir(parents=True, exist_ok=True)
    seed = json.loads((_ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    bc, added, added_ab, _unres = CI.augment(seed, [CARRIER], RANK)
    node = bc.setdefault("Abilities", {}).setdefault("PassiveAbilities", {})
    if "DawnBlade" not in node:                       # `_ability_names` ignore `relicAbilities`
        node["DawnBlade"] = CI.synthesize_ability("DawnBlade")
    for u in bc["Units"]:
        if u.get("Id") == CARRIER and DAWN_BLADE_TRIGGERED_ID not in (u.get("PassiveAbilities") or []):
            u["PassiveAbilities"] = list(u.get("PassiveAbilities") or []) + [DAWN_BLADE_TRIGGERED_ID]
    (out / "seed-bc-dawnblade.json").write_text(json.dumps(bc), encoding="utf-8")
    sid = R._resolve_session()
    _tmpl, pool, pool_mow = R._normalize_and_extract_pool(
        sid, bc, RANK, board_dump=R._load_board_dump(BOARD_ID))
    ok = CARRIER in pool or CARRIER in pool_mow
    print("[317/pool] +%d unite(s) au catalogue | pool normalise = %d regulieres + %d MoW | %s "
          "spawnable = %s" % (len(added), len(pool), len(pool_mow), CARRIER, ok))
    if not ok:
        print("[317/pool] => les 5 porteurs `relicAbilities` sont npc et ne passent pas la "
              "normalisation. La voie CONFRONTABLE est l'autre : le heros `tauFarsight` injecte "
              "au catalogue + `--equip-relic tauFarsight:DawnBlade:<lvl>` (#237), lu par le rail "
              "tertiaire (#357). Cf. `probe_357_relic_rail.py`.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mutate", choices=MUTATIONS)
    ap.add_argument("--pool", action="store_true",
                    help="sondage de confrontabilite (session live requise)")
    a = ap.parse_args()
    if a.pool:
        return pool_probe()
    r = run(a.mutate)
    print("[317] DawnBlade -- hpToHeal[lvl] = %s | mutation = %s" % (r["amount"], r["mutate"]))
    for k in ("R0", "R1", "R2", "R3", "R4"):
        print("   %-3s events=%d repaired=%s" % (k, r[k]["events"], r[k]["repaired"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
