"""Face DECISION de `ThriceBlessedConflagration` (1187) confrontee au LIVE (#129).

`IdunBattle.AI.Playbook.Loki.ThriceBlessedConflagrationPlaybook$$EvaluateNonComparable` existe cote
natif ; jusqu'a #129 le moteur n'avait AUCUNE feuille NonComparable pour 1187 -> l'ability ne
pouvait JAMAIS etre proposee. La feuille portee mirrore :

    Bucket(min = Fix64(1))                                       # ThriceBlessedConflagrationPlaybook$$.cctor
    pour chaque cible eligible T de GetEligibleTargetsSelectable :
        bestLine = ThriceBlessedConflagrationAbility$$GetTilesInBestLine(ability)
                 = Target@0x178 op_Addition GetTilesInLine( First(SortByFormula(
                       SurroundingTiles(Target@0x178, includeCenter=0, r=1, 0, 0),
                       Count(GetTilesInLine(Subject@0x180)), DESC), 1) )
        util     = Fix64.FromInt( |Enemies(Owner@0x148, bestLine)| )
        GenerateAction(position, T, util) + Bucket.AddAction     # argmax STRICT, keep-first au tie

CE QUE CE TEST GARDE :
  [A] CONFORMITE + ARGMAX SUR LES CIBLES -- sur un etat ou le natif CASTE REELLEMENT 1187, le port
      rend la MEME ability sur la MEME cible, et cette cible n'est PAS la premiere eligible (un port
      keep-first, ou un port qui ne compterait qu'un ennemi, se tromperait de cible).
  [B] LES QUIRKS DE GEOMETRIE (`SurroundingTiles` SANS porte d'elevation + settings de ligne 0/0) --
      la MEME feuille remise a la geometrie de DarkTalonStrike (`AdjacentTiles` + settings 1/1), ce
      qu'un copier-coller de la feuille 1092 produirait, rend une decision DIFFERENTE du natif.
      SKIP explicite si aucun board MoW-capable du pool ne porte la marche requise.

Porteur : `adeptExorcist` (MACHINE OF WAR, Adepta Sororitas) -- present dans `--list-pool` (8 MoW
spawnables). LEVIER MUNITIONS : le seed BC part a `BC.Player.Players[*].MachineOfWarAmmo = 0`,
sans quoi aucune MoW ne caste (meme levier que `test_storm_speeder_live`).

ORACLE = l'IA NATIVE sur le MEME etat. `aiDryRunAllUnits` n'itere QUE les `EntityType.Unit` -- une
MoW n'y figure pas ; l'oracle est donc `aiStepDryRun` (`CalculateNextActionForPlayer`, LECTURE
SEULE, `mutated: false`), jamais `aiPredict`.

Lit l'etat LIVE, aucune tuile hardcodee. ASCII only.
Probe jumeau : `scripts/python/probe_129_thrice_blessed_decision.py`.
"""
from __future__ import annotations

import json
import uuid
from collections import deque
from pathlib import Path

import pytest

import hexgeo
from engine import battle_query as bq

ABILITY = 1187
MOW = "adeptExorcist"
P_UNITS = "adeptCanoness,adeptRetributor"
A_UNITS = "necroDestroyer,necroWarden,necroDestroyer"
ROOT = Path(__file__).resolve().parents[4]
CUBE_DIRS = [(0, -1, 1), (1, -1, 0), (1, 0, -1), (0, 1, -1), (-1, 1, 0), (-1, 0, 1)]


# --------------------------------------------------------------------------- harnais

def _ammo_bc(ammo: int = 5) -> Path:
    """Seed BC + munitions de MoW. `munitionsCost = 1` gate le cast de 1187 et le seed part a 0."""
    src = ROOT / "data" / "seed-bc.json"
    if not src.exists():
        pytest.skip("data/seed-bc.json absent (python dump_boards.py)")
    bc = json.loads(src.read_text(encoding="utf-8"))
    for _pid, p in ((bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(p, dict) and p.get("PlayerType") != 2:        # Environment exclu
            p["MachineOfWarAmmo"] = ammo
    out = ROOT / "data" / "rl-state" / f"bc-129-{uuid.uuid4().hex[:8]}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return out


def _board(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    tiles = bg.get("tiles") or []
    if not tiles:
        pytest.skip("boardGraph indispo")
    return ({(t["col"], t["row"]): t.get("elevation") for t in tiles},
            {(t["col"], t["row"]): bool(t.get("walkable")) for t in tiles})


def _positions(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    return dv, {u["id"]: (u["pos"]["col"], u["pos"]["row"])
                for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")}


def _move_ring(p, walk, elev):
    """`TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` : le graphe de MOUVEMENT natif
    (walkable + porte `|Delta elev| < 2`) — les waypoints du driver de placement."""
    if elev.get(p) is None:
        return []
    return [n for n in hexgeo.neighbors(p[0], p[1])
            if walk.get(n) and elev.get(n) is not None and abs(elev[n] - elev[p]) < 2]


def _gated_path(src, dst, walk, elev):
    if src == dst:
        return [src]
    prev, q = {src: None}, deque([src])
    while q:
        cur = q.popleft()
        for n in _move_ring(cur, walk, elev):
            if n in prev:
                continue
            prev[n] = cur
            if n == dst:
                path, x = [], n
                while x is not None:
                    path.append(x)
                    x = prev[x]
                return list(reversed(path))
            q.append(n)
    return []


def _drive_to(rpc, rid, walk, elev, wanted: dict, rounds: int = 16) -> bool:
    """DOCTRINE « drive positions, don't blame geometry » : waypoints sur le CHEMIN de mouvement
    natif (le plus loin d'abord), `endturn` x2 pour re-armer le deplacement des deux camps."""
    for _ in range(rounds):
        _dv, pos = _positions(rpc, rid)
        if all(pos.get(u) == d for u, d in wanted.items()):
            return True
        occupied = set(pos.values())
        for uid, dest in wanted.items():
            cur = pos.get(uid)
            if cur is None or cur == dest:
                continue
            for p in reversed(_gated_path(cur, dest, walk, elev)[1:]):
                if not walk.get(p) or (p in occupied and p != dest):
                    continue
                r = rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid, "to": {"col": p[0], "row": p[1]}}}, 60)
                if isinstance(r, dict) and r.get("ok") \
                        and (r.get("actions") or [{}])[0].get("mutated"):
                    occupied.discard(cur)
                    occupied.add(p)
                    break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    _dv, pos = _positions(rpc, rid)
    return all(pos.get(u) == d for u, d in wanted.items())


def _native(rpc, rid, allies):
    """`aiStepDryRun` = `CalculateNextActionForPlayer` en LECTURE SEULE (`mutated: false`).
    `aiDryRunAllUnits` n'itere QUE les `EntityType.Unit` : la MoW n'y figure PAS (mesure) -- d'ou
    cet oracle-la. Il rend la PROCHAINE action du JOUEUR, toutes unites confondues : on CLOT donc
    d'abord l'activation de chaque allie (`finish`, `UnitStats_ActionsAvailable: 0`, `mutated:
    false`) pour que la seule proposition restante soit celle de la MACHINE OF WAR."""
    for u in allies:
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "finish", "unitId": u}}, 60)
    st = rpc("aiStepDryRun", {"runnerId": rid}, 180)
    for m in ((st.get("action") or {}).get("messages") or []):
        if m.get("cls") == "ActiveAbilityMessage":
            return {"ability": m.get("abilityType"), "target": m.get("targetId"),
                    "caster": m.get("casterId")}
    return {"ability": None, "target": None, "caster": None}


def _leaf(rpc, rid, cid, myplayer, elev, walk):
    """La FEUILLE portee, sur l'etat LIVE. `engine_decide` ne peut PAS servir ici : son bridge
    exclut les MACHINES OF WAR (`engine.ai.state_bridge._dv_units` : « MoW EXCLUES -- le natif ne
    met que `EntityType.Unit` dans `decisionView.units` »), donc il n'a aucune entree pour le SEUL
    porteur de 1187. Ce qui est confronte est exactement ce que calcule `EvaluateNonComparable`."""
    from engine.playbook import noncomparable as NC
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    epos = [(u["pos"]["col"], u["pos"]["row"]) for u in units
            if u.get("owner") != myplayer and u.get("pos")]
    ctx = NC.NCContext(
        uid=cid, origin=None, reach_nc=[], epos=epos, fpos=[], plan={}, hp_cur_by_id={},
        ability_targets=lambda u, a: rpc("abilityTargets",
                                         {"runnerId": rid, "unitId": u, "abilityType": a}, 120),
        units=units, walkable_by_pos=walk, elev_by_pos=elev)
    return NC.PLAYBOOKS[ABILITY].generate_candidates(ctx)


class _dark_talon_like:
    """MUTATION : la feuille 1187 remise a la geometrie de DarkTalonStrike (1092) -- ring
    `AdjacentTiles` (porte INCONDITIONNELLE `|Delta elev| < 2`) + settings de ligne `1/1`. C'est
    EXACTEMENT le port qu'un copier-coller de la feuille 1092 produirait."""

    def __enter__(self):
        import engine.playbook.noncomparable.thrice_blessed_conflagration as TBC
        self._TBC, self._orig = TBC, (bq.get_surrounding_tiles, TBC._line_enemy_count)

        def ring(p, radius=1, include_center=False, check_walkable=True,
                 walkable_at=None, elevation_at=None, tile_exists=None):
            return bq.get_adjacent_tiles(p, walkable_at=walkable_at, elevation_at=elevation_at,
                                         tile_exists=tile_exists)

        def line(aim, direction, enemy_set, walkable_at, elevation_at, tile_exists):
            n = 0
            for t in bq.get_tiles_behind(aim, direction, max_count=None, check_walkable=True,
                                         update_reference=True, walkable_at=walkable_at,
                                         elevation_at=elevation_at, tile_exists=tile_exists):
                if t not in enemy_set:
                    break
                n += 1
            return n

        bq.get_surrounding_tiles, TBC._line_enemy_count = ring, line
        return self

    def __exit__(self, *exc):
        bq.get_surrounding_tiles, self._TBC._line_enemy_count = self._orig
        return False


def _find_line(elev, walk, want_step=None, exclude=(), prefer=()):
    """(P, [P+d, P+2d]) : chaine alignee walkable. `want_step` exige la MARCHE
    `|elev(P+d) - elev(P)| >= want_step` (la ligne restant, elle, sur un palier UNIQUE) --
    c'est ce qui separe `SurroundingTiles` (sans porte d'elevation) d'`AdjacentTiles`.
    `prefer` = tuiles a essayer EN PREMIER pour `P` (ex. la position actuelle du porteur)."""
    cube = {p: hexgeo.to_cube(p[0], p[1]) for p in elev}
    order = [p for p in prefer if p in elev] + [p for p in sorted(elev) if p not in prefer]
    for P in order:
        if not walk.get(P) or elev.get(P) is None or P in exclude:
            continue                               # tuile deja tenue par un autre allie
        px, _py, pz = cube[P]
        for d in CUBE_DIRS:
            chain = [hexgeo.from_cube(px + d[0] * k, pz + d[2] * k) for k in (1, 2)]
            if any(t not in cube or not walk.get(t) or elev.get(t) is None or t in exclude
                   for t in chain):
                continue
            if want_step is None:
                if len({elev[t] for t in [P] + chain}) != 1:
                    continue                       # palier UNIQUE -> aucun gate d'elevation exerce
            else:
                if abs(elev[chain[0]] - elev[P]) < want_step or elev[chain[0]] != elev[chain[1]]:
                    continue
            return P, chain
    return None


def _setup(rpc, rid, want_step):
    """Place l'allie de PLUS GRAND id sur `P` avec la chaine d'ennemis alignee derriere lui, et NE
    TOUCHE PAS aux autres allies. `fromHere` est enumere par id CROISSANT (mesure) -> la cible de
    l'argmax arrive donc EN QUEUE : un port keep-first se tromperait de cible."""
    elev, walk = _board(rpc, rid)
    dv, pos = _positions(rpc, rid)
    m = next((x for x in (dv.get("mows") or []) if x.get("visualId") == MOW), None)
    if m is None:
        pytest.skip(f"MoW {MOW} non deployee")
    cid, myplayer = m["casterId"], m.get("owner")
    mine = sorted(u["id"] for u in (dv.get("units") or [])
                  if u.get("owner") == myplayer and u.get("alive"))
    foes = [u["id"] for u in (dv.get("units") or [])
            if u.get("owner") != myplayer and u.get("alive")]
    if len(mine) < 2 or len(foes) < 2:
        pytest.skip(f"roster insuffisant (allies={mine} ennemis={foes})")
    strong = mine[-1]
    others = {pos[u] for u in mine[:-1] if pos.get(u)}      # jamais un ennemi sur un allie
    win = _find_line(elev, walk, want_step=want_step, exclude=others,
                     prefer=[pos[strong]] if pos.get(strong) else [])
    if win is None:
        pytest.skip(f"le board du runner n'offre pas de ligne de 3 tuiles (want_step={want_step})")
    P, chain = win
    wanted = {strong: P, foes[0]: chain[0], foes[1]: chain[1]}
    if not _drive_to(rpc, rid, walk, elev, wanted):
        _dv, pos = _positions(rpc, rid)
        pytest.skip(f"placement incomplet: {({u: pos.get(u) for u in wanted})} != {wanted}")
    _dv, pos = _positions(rpc, rid)
    return {"cid": cid, "myplayer": myplayer, "elev": elev, "walk": walk, "pos": pos,
            "P": P, "chain": chain, "allies": mine, "strong": strong,
            "enemy": {pos[f] for f in foes if pos.get(f)}}


@pytest.fixture(scope="module")
def ammo_bc():
    p = _ammo_bc()
    yield p
    p.unlink(missing_ok=True)


# --------------------------------------------------------------------------- les tests

def test_thrice_blessed_decision_live(rpc, build_runner, ammo_bc):
    """[A] Sur un etat ou le natif CASTE 1187, le port rend la MEME ability sur la MEME cible --
    et cette cible est celle de l'ARGMAX, pas la premiere eligible."""
    rid = build_runner("4242", ["--board", "C1_02", "--seed-bc", str(ammo_bc),
                                "--p-units", P_UNITS, "--a-units", A_UNITS, "--p-mow", MOW,
                                "--hp-target", "90000", "--hp-player", "90000"])["rid"]
    for _ in range(2):     # `initialCooldownTurns = 1` (gameconfig 1187)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    s = _setup(rpc, rid, want_step=None)
    import engine.playbook.noncomparable.thrice_blessed_conflagration as TBC
    utils = {u: TBC._beam_count(s["pos"][u], s["enemy"], s["walk"], s["elev"])
             for u in s["allies"] if s["pos"].get(u)}
    u_strong = utils[s["strong"]]

    got = _leaf(rpc, rid, s["cid"], s["myplayer"], s["elev"], s["walk"])
    nat = _native(rpc, rid, [u for u in s["allies"]])
    ctx = (f"P={s['P']} chain={s['chain']} strong={s['strong']} utils={utils} ; "
           f"natif={nat} moteur={got}")
    assert nat["ability"] == ABILITY, f"le natif ne CASTE PAS 1187 -- l'etat ne prouve rien : {ctx}"
    assert all(u_strong > v for k, v in utils.items() if k != s["strong"]), (
        f"la cible de l'argmax ne DOMINE pas strictement : l'argmax n'est pas exerce -- {ctx}")
    assert u_strong >= TBC.ThriceBlessedConflagrationPlaybook.MIN_UTILITY, f"util < MIN -- {ctx}"
    assert len(got) == 1, f"le port ne propose pas 1187 -- {ctx}"
    assert (got[0]["ability"], got[0]["target"]) == (nat["ability"], nat["target"]), (
        f"decision offline != natif -- {ctx}")
    assert nat["target"] == s["strong"] and s["strong"] != min(s["allies"]), (
        f"le natif ne vise pas une cible de QUEUE de `fromHere` (ordre id croissant) : un port "
        f"keep-first passerait aussi, le test perdrait sa discriminance -- {ctx}")
    assert got[0]["pred"] == float(u_strong), f"utilite offline != beam count -- {ctx}"


@pytest.mark.parametrize("board,seed", [("C1_38", "4242"), ("C1_25", "777")])
def test_thrice_blessed_decision_elevation_step_live(rpc, build_runner, ammo_bc, board, seed):
    """[B] Le ring de 1187 est `SurroundingTiles` (`IsTileValidForList(tile, src, 1, 0)` : walkable
    SANS porte d'elevation) et sa ligne a des settings `0/0` -- une MARCHE `>= 2` entre la cible et
    ses ennemis ne coupe donc RIEN. La meme feuille a la geometrie DarkTalonStrike (`AdjacentTiles`
    + settings `1/1`) perd le beam -> decision DIFFERENTE du natif. Sans cette 2e mesure, le test
    serait incapable d'echouer sur un copier-coller de la feuille 1092."""
    rid = build_runner(seed, ["--board", board, "--seed-bc", str(ammo_bc),
                              "--p-units", P_UNITS, "--a-units", A_UNITS, "--p-mow", MOW,
                              "--hp-target", "90000", "--hp-player", "90000"])["rid"]
    for _ in range(2):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    s = _setup(rpc, rid, want_step=2)
    got = _leaf(rpc, rid, s["cid"], s["myplayer"], s["elev"], s["walk"])
    with _dark_talon_like():
        mute = _leaf(rpc, rid, s["cid"], s["myplayer"], s["elev"], s["walk"])
    nat = _native(rpc, rid, s["allies"])
    ctx = (f"board={board} P={s['P']}(elev {s['elev'][s['P']]}) chain={s['chain']}"
           f"(elev {[s['elev'][c] for c in s['chain']]}) ; natif={nat} moteur={got} mute={mute}")
    assert nat["ability"] == ABILITY, f"le natif ne CASTE PAS 1187 sur ce relief -- {ctx}"
    assert len(got) == 1 and (got[0]["ability"], got[0]["target"]) == \
        (nat["ability"], nat["target"]), f"decision offline != natif -- {ctx}"
    assert not mute or (mute[0]["ability"], mute[0]["target"]) != (nat["ability"], nat["target"]), (
        f"la geometrie DarkTalonStrike rend DEJA la decision native : les quirks (ring sans porte "
        f"d'elevation, settings 0/0) ne sont PAS exerces -- {ctx}")
