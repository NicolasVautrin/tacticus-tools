"""probe #419-r1-tr14-r5-r2-r1-r2-r1-r1-r3 -- l'ORDRE des deux tests de `GetTilesInRange`.

QUESTION BINAIRE
    Quand la portee vaut 0 ET que `OnlyAdjacent` est vrai, la zone de `GetTilesInRange` est-elle
    `casterTiles` (rayon 0) ou les tuiles ADJACENTES (rayon 1) ?

CE QUE DIT LE DECOMPILE (verite ; relu a l'octet sur le build courant)

  `IdunBattle.Core.Services.TargetingQuery$$GetTilesInRange(caster, casterTiles, options, range)` :

      if      ((int)range < 0)       -> OrderedSet VIDE
      else if (range._5_1_)          -> <IBattleQuery slot 0x69>()  = GetAllTiles()
      else if ((int)range == 0)      -> casterTiles     (ou VIDE si le bit 15 de `rules` est absent)
      else if (range._4_1_)          -> tuiles ADJACENTES
      else                           -> GetTilesInRadius(casterTiles, (int)range, ...)

  Le test de la VALEUR precede donc celui d'`OnlyAdjacent` : la reponse est **rayon 0**.

  C'est l'ORDRE INVERSE de l'autre consommateur du meme `Range`,
  `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, qui teste `range._4_1_` EN
  PREMIER et ne lit `(int)range` que dans la branche `!OnlyAdjacent`. Deux consommateurs, deux
  ordres : les aligner « par symetrie » serait un faux dans un sens ou dans l'autre. C'est aussi
  pourquoi le `None` de `tiles_in_range_reach` sur une portee NON OBSERVABLE est CORRECT et ne doit
  PAS devenir le tri-etat de `get_range` (cran garde par
  `test_419r1tr14r5r2r1r2r1r1_only_adjacent_live.py`).

CE QUE CE PROBE MESURE (offline, sans runner)

  Etape `order` -- le cran qui peut ROUGIR. Le gisement REEL etant vide (etape `sweep`), un
    balayage seul serait un inventaire deguise en garde-fou : il rendrait vert quel que soit
    l'ordre du code. On pose donc un `TargetingRange` SYNTHETIQUE `{onlyAdjacent = True,
    overrideRange = 0}` dans la table locale, et on exige `tiles_in_range_reach -> 0`.
    Contre-cran : le MEME range a `overrideRange = 1` doit rendre 1 (le port ne doit pas rendre 0
    partout), et `{onlyAdjacent = False, overrideRange = 0}` doit rendre 0 (statu quo `RANGE_SELF`).

  Etape `sweep` -- la POPULATION, pour dire si l'ecart est atteignable aujourd'hui : chaque ability
    dont le `TargetingRange` est RE-lu (registre `ABILITY_CLASSES` + `TARGETING_RANGE_BY_ABILITY`)
    x chaque unite du catalogue gameconfig. On ventile les couples par (portee resolue, gate
    d'adjacence) et on compte ceux que l'ordre corrige DEPLACE.

VERDICT
    rc 0 si (a) les trois crans d'ordre tiennent, (b) le balayage a un perimetre NON VIDE, et
    (c) le nombre de couples deplaces est COHERENT avec la ventilation qu'il imprime (un deplacement
    non nul n'est pas un echec : c'est une mesure, et elle doit alors etre confrontee live).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                   # noqa: E402

from engine.services import ability_range as AR                           # noqa: E402
from engine.runner.abilities.targeting import (                           # noqa: E402
    RANGED_BOOL_FALSE, RANGED_BOOL_TRUE, TargetingRange)

#: Un id d'ability qui n'existe dans AUCUNE des deux sources -- il ne peut donc rien ecraser.
_SYNTH_ID = 999_419


def _catalogue() -> list:
    """Les `visualId` du catalogue gameconfig, tries (meme substrat que `unit_weapon_range`).

    `GC.all_unit_ids()` rend un DICT `{kind: [ids]}` -- l'aplatir, sinon le balayage porte sur
    TROIS pseudo-unites et rend un chiffre qui a l'air d'une mesure."""
    idx = GC.all_unit_ids()
    ids = sorted({u for kind in ("lineup", "npc", "summons") for u in (idx.get(kind) or [])})
    if len(ids) < 100:
        raise RuntimeError("catalogue a %d entrees -- substrat SUSPECT, pas une mesure" % len(ids))
    return ids


class _Synth:
    """Pose un `TargetingRange` SYNTHETIQUE dans `TARGETING_RANGE_BY_ABILITY` le temps d'un cran.
    Restauration GARANTIE (la table est un attribut de module, partage)."""

    def __init__(self, rng):
        self._rng = rng

    def __enter__(self):
        AR.TARGETING_RANGE_BY_ABILITY[_SYNTH_ID] = self._rng
        return self

    def __exit__(self, *exc):
        AR.TARGETING_RANGE_BY_ABILITY.pop(_SYNTH_ID, None)
        return False


def step_order(vis: str | None = None) -> int:
    """Les trois crans d'ORDRE, sur un `TargetingRange` synthetique."""
    vis = vis or _catalogue()[0]
    cases = [
        ("onlyAdjacent=True  overrideRange=0",
         TargetingRange(only_adjacent=RANGED_BOOL_TRUE, override_range=0), 0,
         "`(int)range == 0` precede `OnlyAdjacent` -> casterTiles, rayon 0"),
        ("onlyAdjacent=True  overrideRange=1",
         TargetingRange(only_adjacent=RANGED_BOOL_TRUE, override_range=1), 1,
         "portee non nulle -> la branche `OnlyAdjacent` mord, rayon 1"),
        ("onlyAdjacent=False overrideRange=0",
         TargetingRange(only_adjacent=RANGED_BOOL_FALSE, override_range=0), 0,
         "statu quo `RANGE_SELF` -- inchange par la correction d'ordre"),
    ]
    print("=== ETAPE order -- `TargetingRange` SYNTHETIQUE, caster `%s`" % vis)
    rc = 0
    for label, rng, attendu, why in cases:
        with _Synth(rng):
            got = AR.tiles_in_range_reach(_SYNTH_ID, vis)
        ok = got == attendu
        print("  %-38s -> %-6s (attendu %s)  %s" % (label, got, attendu, "OK" if ok else "MISMATCH"))
        print("      %s" % why)
        if not ok:
            rc = 1
    if rc:
        print("[FAIL] l'ordre des deux tests de `GetTilesInRange` n'est pas celui du natif")
    return rc


def _resolved_range(aid: int, vis: str):
    """`(ov, only_adjacent)` tels que `tiles_in_range_reach` les resout -- ou None si la cascade
    sort avant (range non RE-lu, delegue, whole board, portee non observable)."""
    rng = AR.targeting_range_of(aid)
    if rng is None or rng.override_range_func or rng.use_whole_board:
        return None
    ov = rng.override_range
    if ov is None and rng.use_range_from_config:
        ov = AR._config_range(aid)
        if ov is None:
            return None
    if ov is None:
        from engine.runner.abilities.targeting import unit_weapon_range
        ov = unit_weapon_range(vis, None)
        if ov is None:
            return None
    return int(ov), AR._ranged_bool_is_true(rng.only_adjacent, vis)


def _ability_ids() -> list:
    """Les ids dont le `TargetingRange` est RE-lu, par les DEUX sources de `targeting_range_of`."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    ids = {int(a) for a, c in ABILITY_CLASSES.items()
           if getattr(getattr(c, "TARGETING_OPTIONS", None), "range", None) is not None}
    ids |= {int(a) for a in AR.TARGETING_RANGE_BY_ABILITY}
    return sorted(ids)


def step_sweep() -> int:
    """La POPULATION : combien de couples (ability, unite) l'ordre corrige DEPLACE-t-il ?"""
    aids, cat = _ability_ids(), _catalogue()
    tot = zero = zero_adj = deplaces = 0
    par_ability = {}
    for aid in aids:
        for vis in cat:
            got = _resolved_range(aid, vis)
            if got is None:
                continue
            ov, adj = got
            tot += 1
            if ov == 0:
                zero += 1
                if adj:
                    zero_adj += 1
                    deplaces += 1                     # avant : 1 (adjacentes) ; apres : 0
                    par_ability[aid] = par_ability.get(aid, 0) + 1
    print("\n=== ETAPE sweep -- %d abilities a `TargetingRange` RE-lu x %d unites"
          % (len(aids), len(cat)))
    print("  couples a portee RESOLUE (la cascade va jusqu'aux deux tests) : %d" % tot)
    print("  dont portee NULLE (`(int)range == 0`)                         : %d" % zero)
    print("  dont portee NULLE **et** gate d'adjacence ARME                : %d" % zero_adj)
    print("  couples DEPLACES par l'ordre corrige (1 -> 0)                 : %d" % deplaces)
    if par_ability:
        print("  ventilation par ability :")
        for aid, n in sorted(par_ability.items()):
            print("    %-6d %d couple(s)" % (aid, n))
    else:
        print("  -> gisement VIDE : aucune ability RE-lue ne combine `overrideRange/config = 0`")
        print("     avec un `onlyAdjacent` vrai. Les cinq `TargetingRange` statiques l'expliquent :")
        print("     seuls RANGE_SELF (ov=0) et RANGE_FROM_CONFIG portent `onlyAdjacent = False`,")
        print("     et les deux qui l'arment (RANGE_ADJACENT ov=1, RANGE_ADJACENT_IF_MELEE_CASTER")
        print("     ov=<arme> >= 1) ont une portee NON NULLE. Le correctif est donc un MIRROR")
        print("     STRUCTUREL : port fidele NON CONFRONTE, et non un bug corrige.")
    if tot == 0:
        print("[FAIL] perimetre VIDE -- le balayage ne mesure rien")
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=("order", "sweep", "all"), default="all")
    a = ap.parse_args(argv)
    rc = 0
    if a.step in ("order", "all"):
        rc |= step_order()
    if a.step in ("sweep", "all"):
        rc |= step_sweep()
    print("VERDICT: %s" % ("PASS" if rc == 0 else "FAIL"))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
