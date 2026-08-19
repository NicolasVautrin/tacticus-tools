#!/usr/bin/env python
"""probe_250_blacklegion_targeting -- ARMEMENT des gates de cible du module `blacklegion`.

CE QUE CE PROBE MESURE
----------------------
Cinq abilities Black Legion entraient dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` ->
`get_invalid_target_reason` commence par `options = getattr(ability, "TARGETING_OPTIONS", None)` et
rend 0 immediatement : AUCUN gate. Degradation PERMISSIVE -- ni erreur ni crash, invisible en
self-play.

    1021 Incursion            FORME 1 (flags directs)  0x4020      RANGE_FROM_CONFIG (2)
    1022 BringerOfDespair     FORME 3 (preset +0x40)   0x4000      RANGE_ADJACENT
    1036 FrenziedFiring       FORME 3 (preset +0x140)  0x4002      RANGE_FROM_CONFIG (3)
    1147 HadesAutocannons     FORME 1 (flags directs)  0x46006000  RANGE_WHOLE_BOARD
    1148 DaemonicOrdnance     FORME 1 (flags directs)  0x46000040  RANGE_WHOLE_BOARD

Detail par ability (ctors, presets, decomposition bit a bit) : `docs/rl/case-250-blacklegion-
targeting.md` et les commentaires de `engine/runner/abilities/blacklegion.py`.

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` appelle
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` -> la cascade native
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`. Le probe rejoue le gate OFFLINE
sur le MEME etat fige, en N versions : `apres` (le port), `avant` (`TARGETING_OPTIONS = None`, l'etat
de `master`) et les CONTREFACTUELS par champ declares dans `SPECS`.

DEUX GEOMETRIES, et elles ne prouvent PAS la meme chose
-------------------------------------------------------
Le champ `forceMeleeTarget` n'est lisible QUE quand un ennemi est au contact du caster
(`TargetingQuery$$GetRange` n'entre dans `Math.Min(1, v)` que sous
`AttackQuery$$ShouldApplyRangedInMelee`). Inversement, la valeur NUMERIQUE de la portee de config
n'est lisible que quand ce clamp N'EST PAS arme (sinon toute portee se reduit a 1).

  * geometrie `far`  -- AUCUN ennemi au contact : discrimine la PORTEE (le contrefactuel qui
    raccourcit la portee faux-refuse une cible que le natif accepte) ;
  * geometrie `near` -- un ennemi au contact : discrimine `forceMeleeTarget` (le contrefactuel qui
    l'annule faux-accepte une cible que le natif refuse).

Les deux couples board/seed exiges portent donc chacun UN discriminant distinct, au lieu de rejouer
deux fois la meme preuve. La geometrie est CONDUITE (`--no-ai`, les DEUX camps pilotes), jamais
subie.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_250_blacklegion_targeting.py --ability 1021
    python probe_250_blacklegion_targeting.py --ability 1036 --geom near --seed 31337 --board C4_09

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from dataclasses import replace as _replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (RANGE_ADJACENT,       # noqa: E402
                                               RANGE_WHOLE_BOARD,
                                               RANGED_BOOL_FALSE,
                                               RANGED_BOOL_TRUE,
                                               custom_range,
                                               entity_tiles,
                                               get_invalid_caster_reason,
                                               get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

FOE_VIS = "necroWarden"
TOURS_DE_CHAUFFE = 6               # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
_seq = itertools.count()


# --- SPECS par ability ---------------------------------------------------------------------------
# `wants` = distances (au sens `hexgeo.distance` des MAIN TILES) auxquelles amener les 3 ennemis,
# PAR GEOMETRIE. `variants` = les contrefactuels a jouer, avec leur ATTENDU :
#   "discriminant" -> DOIT produire >= 1 ligne en desaccord avec le natif (sinon le champ n'est pas
#                     prouve et le probe ECHOUE : une validation qui ne discrimine rien n'en est pas
#                     une) ;
#   "inerte"       -> DOIT produire 0 ligne en desaccord (et c'est un resultat A DIRE, pas a
#                     maquiller en preuve).
SPECS = {
    1021: {
        "name": "Incursion",
        "caster": "blackPossession",
        "ally": "blackTerminator",
        "geom": {"far": (2, 3, 4), "near": (1, 2, 4)},
        "variants": {
            # le bit 14 : seul rempart contre le cast sur un allie / sur soi-meme
            "sansEnemy": (lambda o: _replace(o, rules=int(o.rules) & ~int(TR.TargetIsEnemy)),
                          {"far": "discriminant", "near": "discriminant"}),
            # portee non lue = etat permissif : tout ce qui est hors portee passe
            "sansRange": (lambda o: _replace(o, range=None),
                          {"far": "discriminant", "near": "discriminant"}),
            # RANGE_ADJACENT au lieu de RANGE_FROM_CONFIG(2) : faux-refuse la cible a d=2, mais
            # SEULEMENT quand le clamp melee n'est pas deja arme -> inerte en geometrie `near`.
            "rangeAdjacent": (lambda o: _replace(o, range=RANGE_ADJACENT),
                              {"far": "discriminant", "near": "inerte"}),
            # `forceMeleeTarget` annule : ne se voit QUE si un ennemi est au contact du caster
            "forceMeleeFalse": (lambda o: _replace(o, force_melee_target=RANGED_BOOL_FALSE),
                                {"far": "inerte", "near": "discriminant"}),
            # bit 5 : la cible doit avoir >= 1 tuile libre au contact -- en terrain degage, inerte
            "sansFreeAdj": (lambda o: _replace(
                o, rules=int(o.rules) & ~int(TR.TargetHasFreeAdjacentTile)),
                {"far": "inerte", "near": "inerte"}),
        },
    },
    1022: {
        "name": "BringerOfDespair",
        "caster": "blackTerminator",
        "ally": "blackPossession",
        "geom": {"far": (1, 2, 4), "near": (1, 2, 3)},
        "variants": {
            "sansEnemy": (lambda o: _replace(o, rules=int(o.rules) & ~int(TR.TargetIsEnemy)),
                          {"far": "discriminant", "near": "discriminant"}),
            "sansRange": (lambda o: _replace(o, range=None),
                          {"far": "discriminant", "near": "discriminant"}),
            # MEME portee numerique (1), mais SANS le regime `onlyAdjacent` : c'est ce
            # contrefactuel-la qui prouve que le champ lu est le REGIME, pas « une portee ».
            "rangeDist2": (lambda o: _replace(o, range=custom_range(2)),
                           {"far": "discriminant", "near": "discriminant"}),
            # la portee EST deja l'adjacence -> le clamp melee n'a rien a clamper
            "forceMeleeTrue": (lambda o: _replace(o, force_melee_target=RANGED_BOOL_TRUE),
                               {"far": "inerte", "near": "inerte"}),
        },
    },
    1036: {
        "name": "FrenziedFiring",
        "caster": "blackObliterator",
        "ally": "blackTerminator",
        "geom": {"far": (2, 3, 5), "near": (1, 3, 5)},
        "variants": {
            "sansEnemy": (lambda o: _replace(o, rules=int(o.rules) & ~int(TR.TargetIsEnemy)),
                          {"far": "discriminant", "near": "discriminant"}),
            "sansRange": (lambda o: _replace(o, range=None),
                          {"far": "discriminant", "near": "discriminant"}),
            # portee 2 au lieu de la portee de config 3 : faux-refuse la cible a d=3 -- visible
            # SEULEMENT hors clamp melee.
            "range2": (lambda o: _replace(o, range=custom_range(2)),
                       {"far": "discriminant", "near": "inerte"}),
            "forceMeleeFalse": (lambda o: _replace(o, force_melee_target=RANGED_BOOL_FALSE),
                                {"far": "inerte", "near": "discriminant"}),
            # bit 1 : 1036 ne surcharge PAS `GetDynamicInvalidTargetReason` -> le defaut 0 de la
            # base est le mirror exact, et le bit est INERTE. Resultat a dire, pas a maquiller.
            "sansDynamic": (lambda o: _replace(
                o, rules=int(o.rules) & ~int(TR.TargetMatchesDynamicRule)),
                {"far": "inerte", "near": "inerte"}),
        },
    },
    1147: {
        "name": "HadesAutocannons",
        "caster": "blackForgefiend",        # MACHINE OF WAR (hors plateau)
        "mow": True,
        "ally": "blackTerminator",
        # Le SUMMONER adverse : son `Incursion` (1021) fait apparaitre jusqu'a 6
        # `blackSmnBloodletter` DANS SON CAMP -- les seules cibles que `TargetIsSummon` accepte.
        "summoner": ("blackPossession", 1021),
        "geom": {"far": (2, 3, 5), "near": (1, 3, 5)},
        "variants": {
            "sansEnemy": (lambda o: _replace(o, rules=int(o.rules) & ~int(TR.TargetIsEnemy)),
                          {"far": "discriminant", "near": "discriminant"}),
            # LA regle de 1147 : « a targeted enemy SUMMON ». Sans elle, le port accepte tout
            # ennemi -- exactement ce que la 1re mesure a montre (natif 0x2000, port 0x0).
            "sansSummon": (lambda o: _replace(o, rules=int(o.rules) & ~int(TR.TargetIsSummon)),
                           {"far": "discriminant", "near": "discriminant"}),
            # Les DEUX contrefactuels de portee sont INERTES, et pour DEUX raisons independantes :
            # `UseWholeBoard` court-circuite `GetRange`, ET le caster MoW n'a AUCUNE tuile
            # (`_tile_of` -> None -> `get_range` rend None). La portee n'est donc pas discriminable
            # pour ce porteur : c'est un resultat a DIRE, pas a maquiller en preuve.
            "sansRange": (lambda o: _replace(o, range=None),
                          {"far": "inerte", "near": "inerte"}),
            "rangeDist1": (lambda o: _replace(o, range=custom_range(1)),
                           {"far": "inerte", "near": "inerte"}),
        },
    },
    1148: {
        "name": "DaemonicOrdnance",
        "caster": "blackForgefiend",        # MACHINE OF WAR (hors plateau)
        "mow": True,
        "ally": "blackTerminator",
        # 1148 cible une TUILE : les lignes UNITE ne suffisent pas (le natif y resout
        # `GetMainTile(unite)`, toujours marchable -> acceptees des deux cotes, aucun gain).
        # Il faut interroger des TUILES du board, marchables ET non marchables.
        "tile_targets": True,
        "geom": {"far": (2, 3, 5), "near": (1, 3, 5)},
        "variants": {
            # Le SEUL bit qui refuse : une tuile-cible NON MARCHABLE, `AllowUnwalkableTargetTile`
            # (bit 43) etant absent -> le natif rend le LITTERAL 1 = `TargetingRule.ValidRequest`.
            "sansTile": (lambda o: _replace(o, rules=int(o.rules) & ~int(TR.TargetIsTile)),
                         {"far": "discriminant", "near": "discriminant"}),
            # ... et l'ECHAPPATOIRE que le masque n'a PAS : avec `AllowUnwalkableTargetTile`, le
            # natif accepterait la tuile non marchable.
            "allowUnwalkable": (lambda o: _replace(
                o, rules=int(o.rules) | int(TR.AllowUnwalkableTargetTile)),
                {"far": "discriminant", "near": "discriminant"}),
            # Portee NON discriminable (memes deux raisons que 1147 : UseWholeBoard + caster MoW
            # sans tuile).
            "sansRange": (lambda o: _replace(o, range=None),
                          {"far": "inerte", "near": "inerte"}),
            "rangeDist1": (lambda o: _replace(o, range=custom_range(1)),
                           {"far": "inerte", "near": "inerte"}),
        },
    },
}


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def seed_bc_with_ammo(ammo: int = 9) -> Path:
    """Seed BC PATCHE : `Player.Players[].MachineOfWarAmmo <- ammo`, ecrit sous `logs/` (JAMAIS
    dans `data/`, qui est versionne et ne contient que des ENTREES).

    POURQUOI : le stock de munitions vit dans `IdunBattle.Entities.Components.PlayerComponent+0x6c`,
    pose UNE SEULE fois par `IdunBattle.Operations.AddPlayerOperation$$Execute` depuis
    `BC.Player.Players[].MachineOfWarAmmo` -- **0 dans le seed** -- et AUCUNE operation native ne
    l'incremente. Or `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` (l'entree de
    l'oracle `abilityReason`) COURT-CIRCUITE sur
    `IdunBattle.Entities.Components.ActiveAbility$$get_CanCurrentlyBeUsed` et rend le litteral `1`
    (`TargetingRule.ValidRequest`) AVANT d'atteindre la cascade -- donc sans munitions, TOUTES les
    lignes valent 0x1 et rien n'est mesurable. Le patch ne touche PAS le ciblage : il ouvre
    seulement la porte de `CanCurrentlyBeUsed`."""
    src = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for pl in (((src.get("Player") or {}).get("Players")) or {}).values():
        if isinstance(pl, dict) and "MachineOfWarAmmo" in pl:
            pl["MachineOfWarAmmo"] = int(ammo)
    out = ROOT / "logs" / ("_probe250-seedbc-%d.json" % os.getpid())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(src), encoding="utf-8")
    return out


def _build(sid, seed: str, board: str, p_units: str, a_units: str, mow: str = "",
           seed_bc: "Path | None" = None):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe250-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai",
            "--p-units", p_units, "--a-units", a_units]
    if mow:
        argv += ["--p-mow", mow]
    if seed_bc is not None:
        argv += ["--seed-bc", str(seed_bc)]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-500:])
        time.sleep(10)


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _by_vis(dec, vis):
    for u in (dec.get("units") or []):
        if u.get("visualId") == vis and u.get("alive"):
            return u
    return None


def _my_turn(sid, rid, caster_vis, maxit=8):
    """Rend la main au camp du CASTER (chaine d'`endturn`, runner `--no-ai`). Le camp est vise
    NOMMEMENT : tester `currentPlayer == <unite ctrl>.owner` serait une tautologie, et ce probe
    pilote les DEUX camps pour monter sa geometrie."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        me = _by_vis(d, caster_vis)
        if me is not None and me.get("ctrl"):
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- montage

def _wait_movable(sid, rid, unit_id, maxit=6):
    """Tuiles de deplacement de `unit_id`, en enchainant les `endturn` jusqu'a ce que son camp AIT la
    main. On ne COMPTE surtout pas les `endturn` : quand toutes les unites d'un camp ont agi le
    moteur bascule DEJA seul, et un `endturn` de plus decalerait la parite."""
    for _ in range(maxit):
        t = _movable(sid, rid, unit_id)
        if t:
            return t
        _act(sid, rid, {"kind": "endturn"}, 60)
    return []


def _step_toward(sid, rid, unit_id, goal_pos, want: int) -> bool:
    """Rapproche (ou eloigne) `unit_id` jusqu'a une distance `want` de `goal_pos`, dans la limite de
    SON deplacement du tour. Rend True si un `move` a ete emis."""
    tiles = _wait_movable(sid, rid, unit_id)
    if not tiles:
        return False
    best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, goal_pos) - want), t))
    _act(sid, rid, {"kind": "move", "unitId": unit_id,
                    "to": {"col": best[0], "row": best[1]}}, 90)
    return True


def _spawn_enemy_summons(sid, rid, summoner_vis, victim_vis, ability_type, rng_hex=2, maxit=10):
    """Fait caster son ability de SUMMON par le summoner ADVERSE sur une unite de MON camp : les
    invoques apparaissent DANS LE CAMP DU SUMMONER (project_summon_team_model), donc ce sont des
    SUMMONS ENNEMIS pour la MoW -- les seules cibles que `TargetIsSummon` (bit 13) accepte.

    C'est le seul chemin qui rend le masque de 1147 mesurable des DEUX cotes : sans un summon
    ennemi vivant, toutes les lignes sont des refus et rien ne prouve que la cascade est atteinte."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        s, v = _by_vis(d, summoner_vis), _by_vis(d, victim_vis)
        if s is None or v is None:
            return []
        if hexgeo.distance(_pos(s), _pos(v)) <= rng_hex:
            _act(sid, rid, {"kind": "ability", "casterId": int(s["id"]),
                            "targetId": int(v["id"]), "abilityType": int(ability_type)}, 150)
            d2 = _dv(sid, rid)
            return [u for u in (d2.get("units") or [])
                    if u.get("alive") and u.get("visualId") == "blackSmnBloodletter"]
        if not _step_toward(sid, rid, int(s["id"]), _pos(v), 1):
            return []
    return []


def _drive(sid, rid, caster_vis, ally_vis, wants, rounds=16):
    """Monte la geometrie DEMANDEE et rend `(casterPos, allyId, {unitId: distanceVoulue})`.
    `wants` = 3 distances (un ennemi chacune) ; l'allie est amene au CONTACT (seule ligne qui isole
    `TargetIsEnemy` du volet portee)."""
    d = _dv(sid, rid)
    foes0 = sorted((u for u in (d.get("units") or []) if u.get("alive") and not u.get("ctrl")),
                   key=lambda u: u["id"])
    if len(foes0) < len(wants):
        raise RuntimeError("il faut >= %d ennemis" % len(wants))
    want = {int(foes0[i]["id"]): int(wants[i]) for i in range(len(wants))}
    for it in range(rounds):
        d = _dv(sid, rid)
        units = {int(u["id"]): u for u in (d.get("units") or []) if u.get("alive")}
        caster = _by_vis(d, caster_vis)
        ally = _by_vis(d, ally_vis)
        if caster is None or ally is None or any(i not in units for i in want):
            raise RuntimeError("montage impossible (mort ou absent)")
        cp = _pos(caster)
        cur = {i: hexgeo.distance(cp, _pos(units[i])) for i in want}
        d_ally = hexgeo.distance(cp, _pos(ally))
        print("  [drive %d] caster=%s d(ennemis)=%s d(allie)=%d"
              % (it, cp, sorted(cur.values()), d_ally))
        if all(cur[i] == want[i] for i in want) and d_ally == 1:
            return int(ally["id"]), want
        if d_ally != 1:
            _step_toward(sid, rid, int(ally["id"]), cp, 1)
        for i, target_d in want.items():
            d2 = _dv(sid, rid)
            c2 = _by_vis(d2, caster_vis)
            u2 = {int(u["id"]): u for u in (d2.get("units") or []) if u.get("alive")}
            if i not in u2 or c2 is None:
                continue
            if hexgeo.distance(_pos(c2), _pos(u2[i])) != target_d:
                _step_toward(sid, rid, i, _pos(c2), target_d)
    raise RuntimeError("geometrie %s non atteinte apres %d rounds" % (list(wants), rounds))


# --------------------------------------------------------------------------- variantes du port

def _ability(aid: int, variant: str):
    klass = ABILITY_CLASSES[aid]
    if variant == "apres":
        return klass()
    if variant == "avant":
        class _NoMask(klass):            # meme classe, masque retire -> AUCUN gate (etat `master`)
            __slots__ = ()
            TARGETING_OPTIONS = None
        return _NoMask()
    transform = SPECS[aid]["variants"][variant][0]
    opts = transform(klass.TARGETING_OPTIONS)

    class _Variant(klass):
        __slots__ = ()
        TARGETING_OPTIONS = opts
    return _Variant()


def _native_reason(sid, rid, cid, tid, aid):
    nat = _r(sid, "abilityReason",
             {"runnerId": rid, "casterId": cid, "targetId": tid, "abilityType": aid}, 60)
    tr = (nat or {}).get("targetReason") or {}
    cr = (nat or {}).get("casterReason") or {}
    h = tr.get("hex")
    val = int(h, 16) if isinstance(h, str) else None
    if val is None and tr.get("ruleClass") == "NoBrokenTargetingRule":
        val = 0
    ch = cr.get("hex")
    cval = int(ch, 16) if isinstance(ch, str) else (
        0 if cr.get("ruleClass") == "NoBrokenTargetingRule" else None)
    return val, (tr.get("reasons") or []), tr.get("ruleClass"), cval


def _feet_distance(st, board, cid, tid):
    """Distance EFFECTIVE au sens du natif : `MovementQuery.GetDistance(casterTiles, target)` prend
    les EMPREINTES completes (BigTarget = plusieurs pieds), pas la seule MainTile."""
    src = entity_tiles(st, cid) or []
    dst = entity_tiles(st, tid) or []
    if not src or not dst:
        return None
    return min(hexgeo.distance(a, b) for a in src for b in dst)


def measure(sid, aid: int, geom: str, board_id: str, seed: str) -> dict:
    """LA MESURE, partagee par le probe (qui l'imprime) et par le test de garde (qui l'assertionne).

    Monte un runner `--no-ai`, CONDUIT la geometrie demandee, fige l'etat, et rend UNE LIGNE PAR
    CIBLE VIVANTE : le verdict NATIF (`abilityReason` -> `AttackQuery$$GetInvalidTargetReason`) et
    le verdict du port pour CHAQUE variante (`apres`, `avant`, contrefactuels). Dispose SON runner.
    """
    spec = SPECS[aid]
    variants = ["apres", "avant"] + sorted(spec["variants"])
    caster_vis, ally_vis = spec["caster"], spec["ally"]
    is_mow = spec.get("mow", False)
    # Le caster MoW ne se deploie pas via `--p-units` : il passe par `--p-mow`, et c'est l'ALLIE
    # qui sert d'unite pilotable pour monter la geometrie (la MoW, elle, ne bouge pas).
    p_units = ally_vis if is_mow else (caster_vis + "," + ally_vis)
    summoner = spec.get("summoner")
    a_units = ",".join(([summoner[0]] if summoner else []) + [FOE_VIS] * 3)

    rid, state_file = _build(sid, seed, board_id, p_units, a_units,
                             mow=(caster_vis if is_mow else ""),
                             seed_bc=(seed_bc_with_ammo() if is_mow else None))
    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        summons = []
        if is_mow:
            # Caster MACHINE OF WAR : il n'a NI tuile NI portee (`RANGE_WHOLE_BOARD`), donc la
            # geometrie n'a rien a discriminer -- on ne la conduit pas. L'allie du montage est
            # l'unite pilotable de son camp, qui sert de ligne ALLIE.
            if summoner:
                summons = _spawn_enemy_summons(sid, rid, summoner[0], ally_vis, summoner[1])
                print("  [summons] %d summon(s) ennemi(s) : %s"
                      % (len(summons), [int(u["id"]) for u in summons]))
            _my_turn(sid, rid, ally_vis)
        else:
            _drive(sid, rid, caster_vis, ally_vis, spec["geom"][geom])
            _my_turn(sid, rid, caster_vis)

        dv = _dv(sid, rid)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        caster_u = _by_vis(dv, caster_vis)
        if caster_u is None:
            # MACHINE OF WAR : la cle est `decisionView.mows[].casterId` -- c'est CELLE que
            # `snapshot._load_machines` pose comme id d'entite ECS, et celle que `applyAction`
            # attend. `observeBattle.mows[].id` est un id d'entite NATIF distinct : s'en servir
            # rendait le caster introuvable des DEUX cotes (oracle muet + port sans entite).
            m = next((x for x in (dv.get("mows") or [])
                      if x.get("visualId") == caster_vis
                      and x.get("alive", not x.get("isDead", False))), None)
            if m is None:
                raise RuntimeError("caster %s introuvable (ni unite ni MoW)" % caster_vis)
            caster_u = {"id": int(m.get("casterId")), "visualId": caster_vis,
                        "pos": m.get("pos"), "owner": m.get("owner")}
        cid = int(caster_u["id"])

        nat0 = _r(sid, "abilityReason", {"runnerId": rid, "casterId": cid, "abilityType": aid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            raise RuntimeError("boardGraph indisponible")
        board = Board(bg["tiles"], adjacency="native_sym")
        st = load_state(dv, ob, snap, board=board)

        rows = []
        for u in (dv.get("units") or []):
            if not u.get("alive"):
                continue
            tid = int(u["id"])
            # le camp se lit sur `owner`, JAMAIS sur `ctrl` (qui designe le joueur COURANT et
            # s'inverse des qu'on a pilote une unite adverse pour monter la geometrie)
            side = "CASTER" if tid == cid else (
                "ALLIE" if u.get("owner") == caster_u.get("owner") else "ENNEMI")
            nat_val, nat_reasons, nat_class, nat_caster = _native_reason(sid, rid, cid, tid, aid)
            row = {"label": "%s %s" % (side, u.get("visualId")), "targetId": tid,
                   "dist": _feet_distance(st, board, cid, tid),
                   "nat": nat_val, "nat_reasons": nat_reasons, "nat_class": nat_class,
                   "nat_caster": nat_caster}
            for v in variants:
                row[v] = int(get_invalid_target_reason(st, cid, tid, _ability(aid, v)))
            rows.append(row)

        if spec.get("tile_targets"):
            # Cibles TUILE : le seul domaine ou `TargetIsTile` (bit 6) peut REFUSER -- il exige une
            # tuile MARCHABLE, `AllowUnwalkableTargetTile` (bit 43) etant absent du masque. On prend
            # deux tuiles de chaque cote du predicat pour encadrer la regle des DEUX bords ; l'id de
            # tuile EST un id d'entite du `MatchState` (meme espace que `abilityReason.targetId` et
            # que `state.board.by_id`).
            occupied = {int(u["id"]) for u in (dv.get("units") or [])}
            walk = [t for t in sorted(board.by_id) if board.walkable(t) and t not in occupied]
            unwalk = [t for t in sorted(board.by_id) if not board.walkable(t)]
            for tid, kind in ([(t, "TUILE marchable") for t in walk[:2]]
                              + [(t, "TUILE non-marchable") for t in unwalk[:2]]):
                nat_val, nat_reasons, nat_class, nat_caster = _native_reason(sid, rid, cid, tid, aid)
                row = {"label": "%s %s" % (kind, board.coord(tid)), "targetId": int(tid),
                       "dist": _feet_distance(st, board, cid, tid),
                       "nat": nat_val, "nat_reasons": nat_reasons, "nat_class": nat_class,
                       "nat_caster": nat_caster}
                for v in variants:
                    row[v] = int(get_invalid_target_reason(st, cid, tid, _ability(aid, v)))
                rows.append(row)
        # CONTRE-ORACLE ENSEMBLISTE (`abilityTargets` -> `AttackQuery$$GetValidTargets(unit,
        # UnitPosition, ability)`, un chemin natif DISTINCT de `GetInvalidTargetReason`). Il tranche
        # le doute souleve sur les casters MACHINE OF WAR : la surcharge 4 arguments de
        # `AttackQuery$$GetInvalidTargetReason` COURT-CIRCUITE sur
        # `ActiveAbilityComponent.GetOrNull(...) == null` / `!CanCurrentlyBeUsed` et rend alors le
        # litteral `1` SANS avoir traverse la cascade -- un `0x1` ne dit donc RIEN du masque. Ici on
        # verifie que les deux oracles racontent la MEME histoire : `fromHere` (cast legal sans
        # bouger) doit coincider avec les lignes que le port ACCEPTE.
        at = _r(sid, "abilityTargets",
                {"runnerId": rid, "unitId": cid, "abilityType": aid}, 120)
        native_set = set()
        for u in ((at or {}).get("units") or []):
            if int(u.get("unitId", -1)) != cid:
                continue
            for ab in (u.get("abilities") or []):
                if int(ab.get("abilityId", -1)) == aid:
                    native_set = {int(t["targetId"]) for t in (ab.get("fromHere") or [])
                                  if t.get("targetId") is not None}
        return {"caster": cid, "rows": rows, "variants": variants,
                "native_valid_targets": sorted(native_set),
                "port_caster": int(get_invalid_caster_reason(st, cid, _ability(aid, "apres"))),
                "abilityState": (nat0 or {}).get("abilityState") or {},
                "runner": rid, "board": board_id, "seed": seed, "geom": geom}
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
        finally:
            state_file.unlink(missing_ok=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ability", type=int, required=True, choices=sorted(SPECS))
    ap.add_argument("--geom", default="far", choices=("far", "near"))
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args(argv)

    aid = int(a.ability)
    spec = SPECS[aid]
    sid = _resolve_session()
    out = measure(sid, aid, a.geom, a.board, a.seed)
    rows, variants, cid = out["rows"], out["variants"], out["caster"]
    print("[build] runner=%d ability=%d(%s) geom=%s board=%s seed=%s"
          % (out["runner"], aid, spec["name"], a.geom, a.board, a.seed))
    print("[state] caster=u%d(%s) abilityState=%s" % (cid, spec["caster"], out["abilityState"]))

    opts = ABILITY_CLASSES[aid].TARGETING_OPTIONS
    print("\n[reasons] caster=u%d ability=%d masque=0x%x range=%s forceMelee=%s"
          % (cid, aid, int(opts.rules), opts.range, opts.force_melee_target))
    print("  %-28s %-5s %-4s %-13s %-24s" % ("cible", "id", "d", "natif", "regle")
          + "".join("%-17s" % v for v in variants) + "accord")
    n_agree = n_gain = 0
    cf = {v: 0 for v in variants}
    for r in rows:
        agree = (r["nat"] == r["apres"])
        n_agree += 1 if agree else 0
        gain = (r["nat"] not in (None, 0)) and r["avant"] == 0
        n_gain += 1 if gain else 0
        for v in variants:
            if r["nat"] != r[v]:
                cf[v] += 1
        print("  %-28s %-5d %-4s %-13s %-24s%s%s%s"
              % (r["label"], r["targetId"], r["dist"],
                 "-" if r["nat"] is None else hex(r["nat"]),
                 ",".join(r["nat_reasons"]) or r["nat_class"] or "-",
                 "".join("%-17s" % hex(r[v]) for v in variants),
                 "OK" if agree else "MISMATCH", "  <-GAIN" if gain else ""))

    has_acc = any(r["nat"] == 0 for r in rows)
    print("\n[bilan] accord natif/APRES : %d/%d ; lignes ou le natif REFUSE et AVANT rendait 0 "
          "(casts illegaux que master acceptait) : %d" % (n_agree, len(rows), n_gain))
    print("[garde] au moins une cible ACCEPTEE (0x0) : %s -> le court-circuit d'ability "
          "(`CanCurrentlyBeUsed`) ne mord pas" % ("OUI" if has_acc else "NON"))
    print("[volet CASTER] casterReason natif = %s ; port = %s"
          % (sorted(x for x in set(r["nat_caster"] for r in rows) if x is not None),
             hex(out["port_caster"])))
    ids = {r["targetId"] for r in rows}
    nat_set = set(out["native_valid_targets"]) & ids
    reason_set = {r["targetId"] for r in rows if r["nat"] == 0}
    port_set = {r["targetId"] for r in rows if r["apres"] == 0}
    print("[contre-oracle ENSEMBLISTE] abilityTargets.fromHere = %s ; abilityReason==0 = %s ; "
          "port ACCEPTE = %s -> les deux oracles natifs sont %s"
          % (sorted(nat_set), sorted(reason_set), sorted(port_set),
             "D'ACCORD" if nat_set == reason_set else "DIVERGENTS"))
    print("[contrefactuels] lignes en DESACCORD avec le natif quand on neutralise/inverse "
          "un champ (geometrie %s) :" % a.geom)
    cf_ok = True
    for v in sorted(spec["variants"]):
        attendu = spec["variants"][v][1][a.geom]
        ok = (cf[v] > 0) if attendu == "discriminant" else (cf[v] == 0)
        cf_ok = cf_ok and ok
        print("    %-18s %d/%d  attendu=%-13s %s"
              % (v, cf[v], len(rows), attendu, "OK" if ok else "ECART"))
    ok = (n_agree == len(rows) and has_acc and n_gain > 0 and cf_ok)
    print("[VERDICT] %s" % ("PASS" if ok else "FAIL"))
    print("[RAW] " + json.dumps(rows))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
