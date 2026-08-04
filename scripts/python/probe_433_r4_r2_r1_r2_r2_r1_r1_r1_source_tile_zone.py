"""#433-r4-r2-r1-r2-r2-r1-r1-r1 -- la TUILE SOURCE dans la zone de `GetTilesInRange`.

LA QUESTION BINAIRE. La zone d'une ability contient-elle la tuile du CASTER, et sous quelle
condition ? Le port modelisait la zone par un RAYON (`d <= tiles_in_range_reach`), ce qui inclut
`d = 0` INCONDITIONNELLEMENT. La fiche `case-433-r4-r2-r1-r2-r2-r1-r1` §7 avait ATTRIBUE l'ecart
au seul regime `OnlyAdjacent` et n'avait pas corrige, au motif que « la branche `(int)range == 0`
rend `casterTiles`, donc la regle n'est pas uniforme ».

CE QUE LA LECTURE DIT (et qui RE-CADRE la premisse). La regle EST uniforme, mais pas la ou on la
cherchait : elle ne vit pas entierement dans `TargetingQuery$$GetTilesInRange`. Cascade relue :

    (int)range < 0            -> OrderedSet VIDE
    range.UseWholeBoard       -> <IBattleQuery 0x69> GetAllTiles()                     INCLUT
    (int)range == 0           -> `rules >> 0xf & 1` ? new OrderedSet(casterTiles) : VIDE
    range.OnlyAdjacent        -> <0x51> BattleQuery$$GetAdjacentTiles(casterTiles, false,
                                        !bit43, true)                                  EXCLUT
    rules & TargetIsAtRange   -> <0x64> BattleQuery$$GetTilesAtDistance(casterTiles,
                                        (int)range, false)                             ANNEAU
    sinon                     -> <0x67> BattleQuery$$GetSurroundingTiles(casterTiles,
                                        (int)range, false, !bit43, false,
                                        includeCenter: `rules >> 0xf & 1`)

puis, DANS L'APPELANT `TargetingQuery$$GetPossibleTargetsForOptions` et avant les trois `RemoveAll` :

    if (rules >> 0xf & 1)          tiles.<IOrderedSet slot 0>(casterTiles)   // CasterIsPossibleTarget
    if (rules & 0x200000000000000) tiles.<IOrderedSet slot 0>(casterTiles)   // TargetIsCasterOrEnemy

Le slot 0 est un AJOUT -- lu, pas devine : `MovementQuery$$GetMovablePositionsFor` l'invoque sur le
meme couple (interface, receveur) avec `EntityExtensions$$IterateTiles(unit)`, et le movable set
d'une unite CONTIENT sa tuile courante. Le slot 1 de la meme interface est `RemoveAll(Predicate)`.

=> la tuile source est dans la zone ssi `UseWholeBoard | CasterIsPossibleTarget | TargetIsCasterOrEnemy`.

Ce probe MESURE le gisement : combien de couples (ability, unite) changent, ventiles par branche.
Le TEST qui garde le port est `tests/engine/test_433_r4_r2_r1_r2_r2_r1_r1_r1_source_tile_zone_offline.py`.
ASCII only.
"""
from __future__ import annotations

import argparse
import sys

import gameconfig as GC                                                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting import (TARGETING_OPTIONS_UNPORTED,  # noqa: E402
                                               targeting_options_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.services import ability_range as AR                          # noqa: E402

#: Les deux bits qui RE-AJOUTENT `casterTiles` en aval de `GetTilesInRange`.
CASTER_ADDED = int(TR.CasterIsPossibleTarget) | int(TR.TargetIsCasterOrEnemy)


def catalogue() -> list:
    """Les `visualId` du catalogue gameconfig (`GC.all_unit_ids()` rend un DICT `{kind: [ids]}` --
    l'aplatir, sinon le balayage porte sur trois pseudo-unites)."""
    idx = GC.all_unit_ids()
    ids = sorted({u for kind in ("lineup", "npc", "summons") for u in (idx.get(kind) or [])})
    if len(ids) < 100:
        raise RuntimeError("catalogue a %d entrees -- substrat SUSPECT, pas une mesure" % len(ids))
    return ids


def ability_ids() -> list:
    """Les ids dont les `TargetingOptions` sont RE-lues, par les DEUX sources du foyer."""
    ids = {int(a) for a in ABILITY_CLASSES
           if getattr(ABILITY_CLASSES[a], "TARGETING_OPTIONS", None) is not None}
    ids |= {int(a) for a in TARGETING_OPTIONS_UNPORTED}
    return sorted(ids)


def branche(aid) -> str:
    """La branche de `GetTilesInRange` que cette ability prend, dans l'ORDRE natif."""
    opts = targeting_options_for(aid)
    rng = getattr(opts, "range", None) if opts is not None else None
    if rng is None or rng.override_range_func:
        return "non_lu"
    if rng.use_whole_board:
        return "whole_board"
    if rng.override_range == 0:
        return "range_zero"
    if int(rng.only_adjacent) == 0:
        return "only_adjacent"
    if int(getattr(opts, "rules", 0)) & int(TR.TargetIsAtRange):
        return "at_range"
    return "radius"


def caster_ajoute(aid) -> bool:
    opts = targeting_options_for(aid)
    return bool(int(getattr(opts, "rules", 0) or 0) & CASTER_ADDED)


def inventaire() -> dict:
    """Ventilation des abilities par branche, et compte des couples (ability, unite) dont la
    reponse a `d = 0` CHANGE entre le modele RAYON (avant) et le modele ZONE (apres)."""
    cat, aids = catalogue(), ability_ids()
    par_branche: dict = {}
    couples = deplaces = 0
    for aid in aids:
        br = branche(aid)
        par_branche.setdefault(br, []).append(aid)
        for vis in cat:
            reach = AR.tiles_in_range_reach(aid, vis)
            if reach is None:
                continue                       # le port ne decide pas -> aucun terme, avant COMME apres
            couples += 1
            avant = 0 <= reach                 # `d <= reach` a d = 0 : TOUJOURS vrai
            apres = bool(AR.tiles_in_range_zone_contains(aid, vis, 0))
            deplaces += int(avant != apres)
    return {"catalogue": len(cat), "abilities": len(aids), "couples": couples,
            "deplaces_a_d0": deplaces,
            "par_branche": {k: len(v) for k, v in sorted(par_branche.items())},
            "avec_caster_ajoute": sum(1 for a in aids if caster_ajoute(a))}


def borne_superieure_tient() -> tuple:
    """La zone doit rester INCLUSE dans le disque de rayon `tiles_in_range_reach` : les deux
    fonctions partagent `_range_terms`, donc un desaccord signalerait un FORK entre elles."""
    cat, aids = catalogue(), ability_ids()
    testes = fautes = 0
    for aid in aids:
        for vis in cat[:120]:
            reach = AR.tiles_in_range_reach(aid, vis)
            if reach is None:
                continue
            borne = min(int(reach), 8)
            for d in range(0, borne + 3):
                z = AR.tiles_in_range_zone_contains(aid, vis, d)
                testes += 1
                if z and d > int(reach):
                    fautes += 1
    return testes, fautes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", default="all",
                    choices=("all", "inventaire", "borne"))
    args = ap.parse_args()
    if args.step in ("all", "inventaire"):
        inv = inventaire()
        print("catalogue=%(catalogue)d abilities=%(abilities)d couples=%(couples)d" % inv)
        print("couples dont la reponse a d=0 CHANGE : %(deplaces_a_d0)d" % inv)
        print("abilities qui RE-AJOUTENT casterTiles (bit 15 ou 57) : %(avec_caster_ajoute)d" % inv)
        for br, n in inv["par_branche"].items():
            print("  branche %-14s %d" % (br, n))
    if args.step in ("all", "borne"):
        testes, fautes = borne_superieure_tient()
        print("borne superieure : %d points testes, %d hors borne" % (testes, fautes))
        if fautes:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
