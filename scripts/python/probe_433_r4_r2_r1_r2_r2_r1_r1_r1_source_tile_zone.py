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
import json
import subprocess
import sys
import uuid
from pathlib import Path

import gameconfig as GC                                                  # noqa: E402
import hexgeo                                                            # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES              # noqa: E402
from engine.runner.abilities.targeting import (TARGETING_OPTIONS_UNPORTED,  # noqa: E402
                                               targeting_options_for)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.services import ability_range as AR                          # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

#: Les deux bits qui RE-AJOUTENT `casterTiles` en aval de `GetTilesInRange`.
CASTER_ADDED = int(TR.CasterIsPossibleTarget) | int(TR.TargetIsCasterOrEnemy)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
SEED = "777"

#: `MovementOptions.OverrideRange` a la mesure -- borne le movable set sans l'annuler.
#:
#: ⚠ CE QUE L'ORACLE PEUT ET NE PEUT PAS EXPRIMER, mesure du 2026-08-05. Le hook enchaine
#: `MovementQuery$$GetMovableTilesFor(unit, ..., opts)` puis
#: `AttackQuery$$GetAllTilesInAbilityRange(unit, <ce set>, includeNormalAttack: 1)` -- donc
#: `possiblePositions` est le movable set, et il **ne contient PAS la tuile courante** (c'est
#: `GetMovablePositionsFor`, l'AUTRE surcharge, qui l'y ajoute). Deux consequences :
#:   * `overrideRange: 0` rend `tiles: []` ET `threatTiles: []` pour toutes les unites -- un
#:     verdict lu la-dessus serait un artefact de montage, pas une reponse ;
#:   * la question ne se pose donc pas « la tuile COURANTE est-elle menacee » (elle l'est toujours,
#:     couverte depuis n'importe laquelle de ses voisines) mais sur l'ENSEMBLE rendu : le port est
#:     evalue en UNION sur le MEME movable set, et on compare les ensembles.
MEASURE_RANGE = 1

#: LA PAIRE. Meme `unit_threat_reach` (1), tous deux au pool, et un SEUL bit les separe :
#:   * `astraBullgryn` / `1017 FragBomb` (0x80040) -- aucun bit n'ajoute le caster -> la tuile
#:     source est HORS zone (son ability est `RANGE_ADJACENT`, son attaque normale est de melee) ;
#:   * `orksRuntherd` / `1045 GetEmRuntz` (0x8004) -- `CasterIsPossibleTarget` + `RANGE_SELF` ->
#:     la tuile source EST la zone de l'ability.
#: Le modele RAYON d'avant rendait `True` pour les DEUX (`d = 0 <= reach = 1`) : la paire est ce
#: qui separe les deux modeles, une unite seule ne le ferait pas.
PAIR_EXCLUT = "astraBullgryn"
PAIR_INCLUT = "orksRuntherd"
PAIR_BOARD = "MC1_67"
FILLER = "necroWarden"


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


# ------------------------------------------------------------------------------------------------
# LE VOLET LIVE -- oracle `aiMovableTiles {threat: true}` =
# `IdunBattle.Core.Services.AttackQuery$$GetAllTilesInAbilityRange(unit, possiblePositions, true)`,
# le MEME slot 0xe qu'interroge `BattleQuery$$IsTileInRangeOfAnyAbility`.
# ------------------------------------------------------------------------------------------------


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(board, p_units, a_units):
    state = ROOT / "logs" / "runners" / ("p433r1-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", board,
            "--state-file", str(state), "--p-units", p_units, "--a-units", a_units,
            "--hp-target", "90000", "--hp-player", "90000"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        return None, (p.stderr or p.stdout or "")[-1500:]
    return json.loads(state.read_text())["runnerId"], None


def _dispose(sid, rid):
    if rid is None:
        return
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception:                                                    # pragma: no cover
        pass


def _obs(sid, rid):
    o = _r(sid, "observeBattle", {"runnerId": rid}, 120)
    return {u["squadId"]: ((u["col"], u["row"]), u.get("visualId"))
            for u in (o.get("units") or [])
            if not u.get("isDead") and u.get("col") is not None}


def _threat(sid, rid):
    mov = _r(sid, "aiMovableTiles",
             {"runnerId": rid, "threat": True, "side": "all",
              "overrideRange": MEASURE_RANGE}, 150)
    return {u.get("unitId"): ([(t["col"], t["row"]) for t in (u.get("tiles") or [])],
                              {(t["col"], t["row"]) for t in (u.get("threatTiles") or [])})
            for u in (mov.get("units") or [])}


class _ModeleRayon:
    """Le contre-factuel d'AVANT : la zone est le DISQUE de `tiles_in_range_reach`.

    C'est EXACTEMENT ce que faisait `_ability_covers_tile` (`d <= base`) et le terme d'attaque
    normale (`d <= portee d'arme`) avant cette tranche -- pas « aucune option », qui serait un
    AUTRE regime et ne dirait rien du modele."""

    def __enter__(self):
        self._z, self._n = AR.tiles_in_range_zone_contains, AR.normal_attack_zone_contains

        def zone(aid, vis, d):
            r = AR.tiles_in_range_reach(aid, vis)
            return None if r is None else (int(d) <= int(r))

        def normale(nid, vis, d):
            from engine.runner.abilities.targeting import unit_weapon_range
            w = unit_weapon_range(vis, None)
            return None if w is None else (int(d) <= int(w))

        AR.tiles_in_range_zone_contains, AR.normal_attack_zone_contains = zone, normale
        AR._REACH_CACHE.clear()
        return self

    def __exit__(self, *_exc):
        AR.tiles_in_range_zone_contains, AR.normal_attack_zone_contains = self._z, self._n
        AR._REACH_CACHE.clear()
        return False


def _dv_state(sid, rid, visual):
    """L'etat par ability (`decisionView`, `allAbilities: true`) -- le canal des TROIS gates CASTER
    que `AttackQuery$$GetAllTilesInAbilityRange` (surcharge 4 arguments) evalue AVANT les slots
    9/10. Sans lui le port ne peut PAS voir qu'une ability est annulee (#433-r4-r2-r1-r1-c)."""
    from engine.services import ability_caster_gates as acg
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 1}, 180)
    row = next((u for u in (dv.get("units") or []) if u.get("visualId") == visual), None)
    if row is None:
        return None, None
    return acg.ability_state_map(row), acg.normal_attack_id(row)


def _port_zone(move_tiles, all_tiles, visual, elev, walk, wall, fog, ability_ids=None,
               ability_state=None, normal_attack_id=None):
    """Le port, evalue en UNION sur le MOVABLE SET -- le meme `possiblePositions` que le natif.

    `ability_ids=[]` isole le terme de l'ATTAQUE NORMALE : c'est la DECOMPOSITION PAR ETAGE, le
    seul moyen de dire si un ecart vient de la zone d'une ability ou d'un etage AMONT qui l'annule
    (`AttackQuery$$GetAllTilesInAbilityRange` surcharge 4 arguments : slot 0x14, slot 0x13, puis
    `GetInvalidCasterReason` -- chacun fait rendre un ensemble VIDE)."""
    AR._REACH_CACHE.clear()
    out = set()
    for T in all_tiles:
        for X in move_tiles:
            if AR.is_tile_in_range_of_any_ability(X, T, visual, ability_ids=ability_ids,
                                                  elev_by_pos=elev, ability_state=ability_state,
                                                  normal_attack_id=normal_attack_id,
                                                  is_wall_by_pos=wall, walkable_by_pos=walk,
                                                  is_in_fog_by_pos=fog):
                out.add(T)
                break
    return out


def _board_maps(sid, rid):
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    tiles = bg.get("tiles") or []
    pos = {t["id"]: (t["col"], t["row"]) for t in tiles}
    return ({pos[t["id"]]: t.get("elevation") for t in tiles},
            {pos[t["id"]]: bool(t.get("walkable")) for t in tiles},
            {pos[t["id"]]: bool(t.get("isWall")) for t in tiles},
            {pos[t["id"]]: bool(t.get("isInFog")) for t in tiles})


def live(sid, board=None, fillers=3, swap=False) -> dict:
    """La paire, sur UN SEUL runner : les deux casters sont dans la meme bataille, donc le natif
    repond aux deux questions dans le MEME etat -- aucune variable de montage ne les separe.

    Ce que la paire garantit : `astraBullgryn` et `orksRuntherd` ont le MEME `unit_threat_reach`
    (1) et ne different que par `CasterIsPossibleTarget`. Le modele RAYON versait, pour les deux,
    tout le disque de rayon 1 autour de CHAQUE position possible -- donc les positions elles-memes.
    Le modele ZONE ne verse une position que pour `orksRuntherd` (`RANGE_SELF` + le bit)."""
    # Les fillers ne sont pas du remplissage : ils OCCUPENT les tuiles de spawn voisines, et c'est
    # ce qui reduit le movable set des deux casters -- le seul regime ou les deux modeles different
    # (cf. MEASURE_RANGE). Sans eux, chaque position possible est couverte depuis une autre et
    # l'ecart se referme tout seul : accord PARFAIT des deux modeles, donc zero preuve.
    paire = [PAIR_INCLUT, PAIR_EXCLUT] if swap else [PAIR_EXCLUT, PAIR_INCLUT]
    rid, err = _build(board or PAIR_BOARD,
                      ",".join(paire + [FILLER] * int(fillers)),
                      "%s,%s" % (FILLER, FILLER))
    if rid is None:
        return {"error": "build KO -- %s" % err}
    try:
        out = {"board": board or PAIR_BOARD, "runner": rid, "unites": {}}
        elev, walk, wall, fog = _board_maps(sid, rid)
        allp = sorted(elev)
        th, u0 = None, None
        for _ in range(6):
            th, u0 = _threat(sid, rid), _obs(sid, rid)
            if any(v[0] for v in th.values()):
                break
            _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        by_vis = {v[1]: k for k, v in (u0 or {}).items()}
        for vis in (PAIR_EXCLUT, PAIR_INCLUT):
            uid = by_vis.get(vis)
            if uid is None:
                out["unites"][vis] = {"error": "absent du runner (%r)" % sorted(by_vis)}
                continue
            pos = u0[uid][0]
            move, natif = th.get(uid) or ([], set())
            if not move:
                out["unites"][vis] = {"error": "movable set VIDE -- ce montage ne mesure rien"}
                continue
            natif &= set(allp)
            st, na_id = _dv_state(sid, rid, vis)
            apres = _port_zone(move, allp, vis, elev, walk, wall, fog,
                               ability_state=st, normal_attack_id=na_id)
            with _ModeleRayon():
                avant = _port_zone(move, allp, vis, elev, walk, wall, fog,
                                   ability_state=st, normal_attack_id=na_id)
            out["unites"][vis] = {
                "pos": pos, "n_move": len(move), "move": sorted(move),
                "rules": "0x%x" % int(targeting_options_for(
                    [int(getattr(__import__("engine.entities.active_ability_type",
                                            fromlist=["ActiveAbilityType"]).ActiveAbilityType, n))
                     for n in (GC.unit(vis) or {}).get("activeAbilities", [])][0]).rules),
                "reach": AR.unit_threat_reach(vis),
                # L'ETAGE isole : l'attaque normale SEULE. Si le natif l'egale, c'est que son
                # ability ne verse RIEN -- un etage AMONT l'a annulee, et l'ecart n'est pas dans
                # la zone.
                "n_normale_seule": len(_port_zone(move, allp, vis, elev, walk, wall, fog,
                                                  ability_ids=[])),
                "n_natif": len(natif), "n_avant": len(avant), "n_apres": len(apres),
                "fp_avant": sorted(avant - natif), "fn_avant": sorted(natif - avant),
                "fp_apres": sorted(apres - natif), "fn_apres": sorted(natif - apres),
                "positions_dans_natif": sorted(t for t in move if t in natif),
                "maxd_natif": max([hexgeo.distance(t, pos) for t in natif] or [-1]),
            }
        return out
    finally:
        _dispose(sid, rid)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", default="all",
                    choices=("all", "inventaire", "borne", "live"))
    ap.add_argument("--board", default=None)
    ap.add_argument("--fillers", type=int, default=3,
                    help="unites de remplissage cote joueur : elles OCCUPENT les tuiles de spawn "
                         "voisines et REDUISENT le movable set de la paire (cf. MEASURE_RANGE)")
    ap.add_argument("--swap", action="store_true",
                    help="inverse l-ordre des deux casters : leurs tuiles de spawn "
                         "changent, donc leur movable set aussi")
    args = ap.parse_args()
    if args.step == "live":
        sid = _resolve_session()
        res = live(sid, args.board, args.fillers, args.swap)
        print(json.dumps(res, indent=2, sort_keys=True, default=str))
        if res.get("error"):
            return 1
        ok = True
        for vis, d in sorted(res["unites"].items()):
            if d.get("error"):
                print("%-16s ERREUR: %s" % (vis, d["error"]))
                ok = False
                continue
            exact = not d["fp_apres"] and not d["fn_apres"]
            ok = ok and exact
            print("%-16s rules=%s reach=%s n_move=%d | natif=%d (normale seule=%d)  "
                  "AVANT=%d (FP %d / FN %d)  APRES=%d (FP %d / FN %d) -> %s"
                  % (vis, d["rules"], d["reach"], d["n_move"], d["n_natif"],
                     d["n_normale_seule"], d["n_avant"],
                     len(d["fp_avant"]), len(d["fn_avant"]), d["n_apres"],
                     len(d["fp_apres"]), len(d["fn_apres"]),
                     "EXACT" if exact else "ECART"))
        return 0 if ok else 1
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
