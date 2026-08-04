"""probe #433-r4-r2-r1-r1-a -- les gates `UseWholeBoard` que la tranche precedente n'avait PAS lus.

LE CRITERE BINAIRE. Pour chaque ability `UseWholeBoard` dont `GetDynamicInvalidTargetReason` etait
classe `GATE_NOT_READ`, le port rend-il la zone EXACTE, ou une borne superieure (il ne retrecit pas,
donc il attribue des tuiles que le natif refuse) ?

CE QUE LA LECTURE A DONNE, ET QUE CE PROBE CONFRONTE :

  * `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetTiles` court-circuite AVANT
    `GetRange` : `if ((rules >> 0xa & 1) && !(rules >> 0xe & 1)) return new OrderedSet<Tile>()`,
    soit `TargetIsFriendly` sans `TargetIsEnemy` -> zone VIDE. `1100 SorcerousFacade` et
    `1143 ForwardSpotter` tombent la : elles surchargent bien le slot `klass+0x478`, mais leur gate
    n'est JAMAIS atteint.

  * les sept autres rendent `0` (valide) sur une tuile SANS unite. Le discriminant vient de la
    lambda `TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__2`,
    qui ne passe PAS au delegue l'element de la liste mais l'entite qu'elle en RESOUT :
    `entity = (rules & TargetIsTile) ? EntityExtensions.GetMainTile(elem)
                                     : UnitExtensions.GetUnit(elem)`.
    Or `GetPossibleTargetTiles` force `onlyTiles: 1`, donc les elements SONT des tuiles : sur une
    tuile vide, une ability sans `TargetIsTile` recoit `entity == null`
    (`EntityExtensions$$IsUnit(null)` rend `false` -- LU, la fonction teste le nul avant tout).

LE MONTAGE, et pourquoi il est DISCRIMINANT. Le porteur natif de la plupart de ces abilities porte
AUSSI une seconde ability `UseWholeBoard` SANS gate (`astraOrdnanceBattery` = `MalleusRocketLauncher`
+ `ForwardSpotter`, `deathCrawler` = `PlagueburstMortar` + `EntropyCannons`) : la zone y est le
plateau entier QUOI QU'IL ARRIVE, donc le porteur natif ne separe RIEN. On GREFFE alors l'ability
seule (`catalog_inject.write_grafted_seed_bc(kind="active")`, `replace=True`) sur un heros du pool a
ARME DE MELEE SEULE -- `custoBladeChampion`, `unit_weapon_range == 1`. Les deux modeles en
competition rendent alors des partitions MAXIMALEMENT eloignees sur un sweep `d = 2..10` :

    zone = plateau entier  -> « en portee » 40/40
    zone = vide            -> « en portee »  0/40  (seule l'arme de melee subsiste, hors sweep)

GARDE ANTI-DEGENERESCENCE. Le probe REFUSE un greffon dont l'arme porterait au-dela de `d = 1` :
sans cela « zone = portee d'arme » donnerait le meme resultat par coincidence et la mesure ne
prouverait rien (le piege mesure de #558).

CE QUE LA GREFFE NE COUVRE PAS, et c'est ecrit : les stats, traits et armes du VRAI porteur. Elle
est legitime ici parce que le court-circuit `rules` est purement statique et que les sept gates
lus testent la CIBLE (ou la tuile), pas le caster -- sauf `1025 SkyStrike` (`DidMove(caster)`) et
`1200 SquigLaunchas` (Orks adjacents au caster), dont les branches concernees sont en AVAL du test
qui rend `0` sur une tuile vide.

Usage (ASCII only, depuis scripts/python) :
  python probe_433_r4_r2_r1_r1_a_whole_board_gates.py --step read
  python probe_433_r4_r2_r1_r1_a_whole_board_gates.py --step graft --ability 1145
  python probe_433_r4_r2_r1_r1_a_whole_board_gates.py --step native --enemy thousTzaangor
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                     # noqa: E402
from rl_collect_batch import _resolve_session, _rpc               # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

CASTER = "tauCrisis"          # HERO du pool ; seul porteur `lineup` de 1077 EarlyWarningOverride
ABILITY = 1077                # ActiveAbilityType.EarlyWarningOverride -- l'oracle du bonus
GRAFT_HOST = "custoBladeChampion"   # arme de MELEE seule (`unit_weapon_range == 1`)
BOARD = "MC1_67"
SEED = "777"
DIST = 8                      # O et Y non adjacents -> BRANCHE A pure du playbook
MOVEMENT = 6

#: Le LOT : les abilities `UseWholeBoard` qui etaient `GATE_NOT_READ` avant cette tranche.
LOT = [1011, 1025, 1100, 1143, 1145, 1168, 1200, 1201, 1213]


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(enemy, seed_bc=None):
    state = ROOT / "logs" / "runners" / ("p433r4r2r1r1a-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--board", BOARD,
            "--state-file", str(state), "--p-units", CASTER, "--a-units", enemy,
            "--hp-target", "90000", "--hp-player", "90000",
            "--unit-stat", "%s:Movement=%d" % (CASTER, MOVEMENT)]
    if seed_bc:
        argv += ["--seed-bc", str(seed_bc)]
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
    except Exception:                                             # pragma: no cover - diagnostic
        pass


def _grafted_seed(ability_id, host=GRAFT_HOST):
    """Un seed BC ou `host` ne porte QUE `ability_id` en ACTIVE (`replace=True`)."""
    import catalog_inject as CI
    from engine.entities.active_ability_type import ActiveAbilityType
    name = ActiveAbilityType(int(ability_id)).name
    out = ROOT / "logs" / "runners" / ("seedbc-graft-%s-%s.json" % (name, uuid.uuid4().hex[:6]))
    out.parent.mkdir(parents=True, exist_ok=True)
    path, reports = CI.write_grafted_seed_bc(out, ["%s:%s" % (host, name)],
                                             replace=True, kind="active")
    return path, reports


def _units(sid, rid, enemy):
    dv = _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    c = next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER), None)
    e = next((u for u in (dv.get("units") or []) if u.get("visualId") == enemy), None)
    return dv, c, e


def _place(sid, rid, caster_id, enemy_id, O, Y):
    for uid, p in ((enemy_id, Y), (caster_id, O)):
        _r(sid, "applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 90)
    for _ in range(4):
        _r(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
        by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        if (by_unit.get(caster_id) or {}).get("tiles"):
            return True
    return False


_BOARD_CACHE: dict = {}


def _board_maps(sid, enemy):
    """`(elev, walk, wall)` du board -- lus UNE fois et memoises : le board est le meme pour tout le
    lot, et chaque lecture coute un runner du budget partage.

    `wall` (`boardGraph.isWall` = `TileComponent+0x41`) est le second volet du predicat de LIGNE DE
    VUE (#433-r4-r2-r1-r2) et NE se deduit PAS de `walk` : `TileExtensions.IsWalkable` agrege le mur
    ET le terrain infranchissable, la ou
    `MovementQuery$$u003CGetTilesObscuringTerrainu003Eg__DetermineBlockingWalls` lit le seul drapeau."""
    if _BOARD_CACHE:
        return _BOARD_CACHE["elev"], _BOARD_CACHE["walk"], _BOARD_CACHE["wall"]
    rid, err = _build(enemy)
    if rid is None:
        raise RuntimeError("build KO (board) : %s" % err)
    try:
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    finally:
        _dispose(sid, rid)
    tiles = bg.get("tiles") or []
    pos_of = {t["id"]: (t["col"], t["row"]) for t in tiles}
    _BOARD_CACHE["elev"] = {pos_of[t["id"]]: t.get("elevation") for t in tiles}
    _BOARD_CACHE["walk"] = {pos_of[t["id"]]: bool(t.get("walkable")) for t in tiles}
    _BOARD_CACHE["wall"] = {pos_of[t["id"]]: bool(t.get("isWall")) for t in tiles}
    return _BOARD_CACHE["elev"], _BOARD_CACHE["walk"], _BOARD_CACHE["wall"]


def _pick_far(elev, walk, want):
    cands = sorted(p for p in walk if walk[p] and elev.get(p) is not None)
    for O in cands:
        for Y in cands:
            if hexgeo.distance(O, Y) == want:
                return O, Y
    return None, None


def _entity_actives(unit_row):
    """Les ids d'ability ACTIVE REELLEMENT montes sur l'entite, lus dans la ligne `decisionView`.

    Le schema publie l'ability sous plusieurs cles selon la voie (`type`, `abilityType`, `id`) ;
    on les essaie toutes plutot que d'en supposer une -- un `[]` silencieux ferait passer une
    greffe non appliquee pour une mesure."""
    out = set()
    for a in (unit_row.get("abilities") or []):
        if not isinstance(a, dict):
            continue
        if str(a.get("kind") or a.get("family") or "active").lower() not in ("active", "granted"):
            continue
        for k in ("type", "abilityType", "activeAbilityType", "id"):
            v = a.get(k)
            if isinstance(v, int):
                out.add(int(v))
                break
    return sorted(out)


def _nc_partition(sid, rid, uid, enemy_pos):
    """`({P : bonus == 0}, {P : bonus == 50})` -- `bonus = util + 10 * Sum_E d(P,E)`.

    Meme isolant que `probe_433_r4_r2_r1_ability_range._nc_partition`, et meme VERROU : la
    partition n'est attribuable qu'a EXACTEMENT UN ennemi vivant."""
    nat = _r(sid, "ncEvaluate", {"runnerId": rid, "unitId": uid, "abilityType": ABILITY,
                                 "sweep": True}, 180)
    in_range, out_range = set(), set()
    for p in (nat.get("positions") or []):
        if p.get("util") is None:
            continue
        P = tuple(p["pos"])
        b = round(p["util"] + 10 * sum(hexgeo.distance(P, e) for e in enemy_pos), 6)
        (in_range if b == 0 else out_range).add(P)
    return in_range, out_range


# ------------------------------------------------------------------------------------------------
# --step read : la ventilation OFFLINE du lot
# ------------------------------------------------------------------------------------------------
def step_read():
    from engine.services import ability_range as ar
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.entities.active_ability_type import ActiveAbilityType

    whole = set()
    for aid, cls in ABILITY_CLASSES.items():
        opts = getattr(cls, "TARGETING_OPTIONS", None)
        rng = getattr(opts, "range", None) if opts is not None else None
        if rng is not None and getattr(rng, "use_whole_board", False):
            whole.add(int(aid))
    # 2e source du volet PORTEE depuis `#433-r4-r2-r1-r2-r2-r1-r1` : le `range` vit avec les trois
    # autres champs du meme ctor, `ability_range.TARGETING_RANGE_BY_ABILITY` ayant ete supprimee.
    from engine.runner.abilities.targeting import TARGETING_OPTIONS_UNPORTED
    for aid, opts in TARGETING_OPTIONS_UNPORTED.items():
        if getattr(opts.range, "use_whole_board", False):
            whole.add(int(aid))

    by_regime: dict = {}
    for aid in sorted(whole):
        by_regime.setdefault(ar.dynamic_target_gate_of(aid), []).append(aid)
    print("abilities UseWholeBoard connues du port : %d" % len(whole))
    for reg in sorted(by_regime):
        print("  %-28s %2d  %s" % (reg, len(by_regime[reg]), by_regime[reg]))
    print("")
    print("zone VIDE par le court-circuit `rules` de GetPossibleTargetTiles :")
    empty = sorted(a for a in ABILITY_CLASSES if ar.target_tiles_zone_is_empty(a))
    for aid in empty:
        cls = ABILITY_CLASSES[aid]
        wb = aid in whole
        print("  %-5d %-38s wholeBoard=%-5s rules=%s"
              % (aid, getattr(cls, "__name__", "?"), wb,
                 hex(int(getattr(getattr(cls, "TARGETING_OPTIONS", None), "rules", 0)))))
    print("")
    print("LE LOT (#-r1-r1-a), regime porte apres lecture :")
    for aid in LOT:
        try:
            nm = ActiveAbilityType(aid).name
        except ValueError:
            nm = "?"
        print("  %-5d %-30s gate=%-22s zone_vide=%-5s reach=%s"
              % (aid, nm, ar.dynamic_target_gate_of(aid), ar.target_tiles_zone_is_empty(aid),
                 ar.ability_range_value(aid, GRAFT_HOST)))
    return 0


# ------------------------------------------------------------------------------------------------
# --step graft / --step native : la ZONE mesuree, natif contre port
# ------------------------------------------------------------------------------------------------
def sweep(sid, enemy, seed_bc=None, ability_ids=None):
    """La MESURE, rendue en donnees -- `{"error": ...}` sur refus. `--step` l'imprime, le test
    live l'assertionne : la mesure n'existe qu'a UN endroit."""
    from engine.services import ability_range as ar
    from engine.runner.abilities.targeting import unit_weapon_range

    if seed_bc is not None:
        wr = unit_weapon_range(enemy, None)
        if wr is None or int(wr) > 1:
            return {"error": "anti-degenerescence : le greffon %s a une arme de portee %s -- "
                             "« zone = portee d'arme » rendrait le meme resultat par coincidence"
                             % (enemy, wr)}

    elev, walk, wall = _board_maps(sid, enemy)
    O, Y = _pick_far(elev, walk, DIST)
    if O is None:
        return {"error": "aucune paire walkable a distance %d sur %s" % (DIST, BOARD)}
    rid, err = _build(enemy, seed_bc)
    if rid is None:
        return {"error": "build KO -- %s" % err}
    try:
        _dv, c, e = _units(sid, rid, enemy)
        if c is None or e is None:
            return {"error": "caster ou ennemi absent du decisionView"}
        if not _place(sid, rid, c["id"], e["id"], O, Y):
            return {"error": "montage non installe (pas de tuile candidate)"}
        dv, c, e = _units(sid, rid, enemy)
        posn = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("pos")}
        if posn.get(c["id"]) != O or posn.get(e["id"]) != Y:
            return {"error": "positions non atteintes %r" % (posn,)}
        foes = [(u.get("visualId"), (u["pos"]["col"], u["pos"]["row"]))
                for u in (dv.get("units") or [])
                if u.get("pos") and u.get("alive") and not u.get("ctrl")]
        if len(foes) != 1:
            return {"error": "montage IMPUR, %d ennemis vivants %r" % (len(foes), foes)}
        # Ce que le NATIF a REELLEMENT monte sur l'entite -- la greffe se verifie, elle ne se
        # suppose pas (`KIT gameconfig != ENTITE`). On lit l'entite, pas le kit.
        got = _entity_actives(e)
        note = None
        if seed_bc is not None:
            want = sorted(ability_ids or [])
            if not set(want) <= set(got):
                return {"error": "la greffe n'a PAS mordu -- entite.abilities=%r, %r absente "
                                 "(cles de l'unite : %r)" % (got, want, sorted(e))}
            if set(got) != set(want):
                # `KIT gameconfig != ENTITE` : le natif monte parfois une ability COMPAGNE
                # (ex. `1011 TunnelingHorror` amene `1060 TunnelingHorror_Appear`). On mesure alors
                # ce que le natif a REELLEMENT monte, on ne le masque pas.
                note = "le natif a monte %r au lieu de %r -- le port lit la MEME liste" % (got, want)
                ability_ids = got
        in_range, out_range = _nc_partition(sid, rid, c["id"], [Y])
        allp = sorted(in_range | out_range)
        modeled = {P for P in allp
                   if ar.is_tile_in_range_of_any_ability(Y, P, enemy, ability_ids=ability_ids,
                                                         elev_by_pos=elev, is_wall_by_pos=wall)}
        by_d: dict = {}
        for P in allp:
            by_d.setdefault(hexgeo.distance(P, Y), []).append(P in in_range)
        return {"enemy": enemy, "entity_abilities": got, "note": note, "O": O, "Y": Y,
                "n_sweep": len(allp), "natif_in_range": sorted(in_range),
                "par_distance": {d: (sum(1 for x in v if x), len(v)) for d, v in sorted(by_d.items())},
                "faux_positifs": sorted(modeled - in_range),
                "faux_negatifs": sorted(in_range - modeled),
                "exact": modeled == in_range}
    finally:
        _dispose(sid, rid)


def _print(res, tag):
    if "error" in res:
        print("  REFUS : %s" % res["error"])
        return 1
    if res.get("note"):
        print("  NOTE : %s" % res["note"])
    print("  %-34s entite.abilities=%r  sweep=%d"
          % (tag, res["entity_abilities"], res["n_sweep"]))
    # La SEULE tuile OCCUPEE du sweep est celle du caster : c'est le seul point ou un gate
    # `GATE_VALID_ON_EMPTY_TILE` peut mordre, et le seul moyen de le VOIR sur ce montage.
    print("  O(caster)=%r  Y(ennemi)=%r  -- O est la seule tuile du sweep portant une unite"
          % (res["O"], res["Y"]))
    line = "  natif en portee par distance :"
    for d, (n, tot) in sorted(res["par_distance"].items()):
        line += "  d%d=%d/%d" % (d, n, tot)
    print(line)
    print("  port : FP=%d FN=%d -> %s"
          % (len(res["faux_positifs"]), len(res["faux_negatifs"]),
             "EXACT" if res["exact"] else "DIVERGE"))
    if res["faux_positifs"]:
        print("  faux positifs : %r" % (res["faux_positifs"][:10],))
    if res["faux_negatifs"]:
        print("  faux negatifs : %r" % (res["faux_negatifs"][:10],))
    return 0 if res["exact"] else 1


def step_graft(sid, abilities):
    from engine.entities.active_ability_type import ActiveAbilityType
    rc = 0
    for aid in abilities:
        try:
            nm = ActiveAbilityType(int(aid)).name
        except ValueError:
            nm = "?"
        print("")
        print("=== %d %s  greffee sur %s ===" % (int(aid), nm, GRAFT_HOST))
        seed, reports = _grafted_seed(aid)
        print("  seed BC greffe : %s" % (reports,))
        rc |= _print(sweep(sid, GRAFT_HOST, seed, [int(aid)]), "graft %d" % int(aid))
    return rc


def step_native(sid, enemies):
    rc = 0
    for enemy in enemies:
        print("")
        print("=== porteur NATIF %s ===" % enemy)
        rc |= _print(sweep(sid, enemy), "natif %s" % enemy)
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="read", choices=["read", "graft", "native"])
    ap.add_argument("--ability", action="append", type=int, default=None)
    ap.add_argument("--enemy", action="append", default=None)
    a = ap.parse_args()
    if a.step == "read":
        return step_read()
    sid = _resolve_session()
    if not sid:
        print("aucune session Frida")
        return 1
    if a.step == "graft":
        return step_graft(sid, a.ability or LOT)
    return step_native(sid, a.enemy or ["thousTzaangor"])


if __name__ == "__main__":
    sys.exit(main())
