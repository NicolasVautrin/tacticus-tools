"""Probe #120bis-spawn -- la TUILE DE SPAWN de Kell : `SwornProtectorAbility$$GetSpawnTile`.

CRITERE. Le natif fait apparaitre Kell sur l'argmax du bucket
`[ WeightedUtility(7 = Tile), WeightedUtility(0x34 = 52 SwornProtector_AvoidAdjacentEnemies) ]`,
dont le 2e terme vaut `-20 x #ennemis adjacents a la tuile candidate`. Le collapse d'avant
(`First(CanAddUnit(AdjacentTiles(owner)))`) prenait la 1re tuile libre dans l'ordre
`board.neighbours`. Consequence OBSERVABLE mesuree par
`docs/rl/case-120bis-flailswing-haze-confound.md` Sec.4 : apres le `SwitchPosition`, Creed se
retrouve du cote OPPOSE a l'attaquant -- `d(caster, creed) == 2` sur 3/3 montages live, contre
`d == 1` sur 163 des 316 couples adjacents de `MC1_67` avec le collapse.

CE QUE CE PROBE MESURE -- un ACCORD, pas une plausibilite :
  * **`d(attaquant, creed)` APRES la cascade**, offline vs live. C'est LE critere : la tuile de
    spawn decide de quel cote Creed atterrit apres le `SwitchPosition`, donc de cette distance ;
  * la tuile de Kell offline vs live -- rendue pour la tracabilite, mais **NON DISCRIMINANTE** :
    apres le switch Kell occupe la tuile de DEPART de Creed des deux cotes, quelle que soit la
    tuile de spawn. Elle est egale meme quand le port se trompe (mesure ci-dessous). Un probe qui
    n'aurait garde qu'elle aurait rendu un VERT sur un port faux.

CONTRE-EPREUVE (arbre temoin `origin/master` = `a2fff7a4`, extrait par `git archive`, MEME session,
MEMES trois montages) :

    montage        temoin (collapse)   ce port   natif (live)
    att (4,4)        d_off = 1          d = 2       d = 2
    att (2,4)        d_off = 1          d = 2       d = 2
    att (3,3)        d_off = 2          d = 1       d = 1
    ACCORD             0/3               3/3          --

Le 3e montage est INVERSE (le collapse rend 2 la ou le natif rend 1) : l'accord du port n'est donc
pas un biais << toujours 2 >>, c'est bien le TRI qui decide, montage par montage.

⚠ **LE MONTAGE EST NON DEGENERE, ET C'EST LA MOITIE DU TRAVAIL.** Creed est amene sur `(3,4)`, une
tuile de `MC1_67` a SIX voisins jouables (meme geometrie que `test_sworn_protector_kell_live.py`) :
sur un coin de board, l'anneau de spawn se reduit a une seule candidate et le tri COINCIDE avec
l'enumeration -- un accord y prouverait exactement RIEN. L'attaquant est en outre DEPLACE sur
plusieurs voisins differents, ce qui fait bouger l'argmax d'un montage a l'autre.

ASCII only (cp1252). Usage: python probe_120bis_spawn_tile.py [--seed 4242] [--board MC1_67]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402
from engine.runner.runner import Runner  # noqa: E402
from engine.runner.messages import AttackUnitMessage  # noqa: E402
from engine.runner.components import PositionComponent, UnitComponent  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_120bis_spawn_tile.json"
CREED = "astraCreed"
KELL = "astraSmnKell"
FOE = "necroWarden"
NORMAL_ATTACK = 69                      # `Loki_NormalAttack` (meme id que le test live)
CREED_TILE = (3, 4)                     # SIX voisins jouables sur MC1_67
#: Les tuiles d'attaque essayees, toutes voisines de `CREED_TILE` -- une seule ne discriminerait pas.
ATTACK_TILES = ((4, 4), (2, 4), (3, 3))


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"])
    rng.mti = s["mti"]
    return rng


def build(seed, board):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(STATE), "--board", board,
            "--p-units", CREED, "--a-units", f"{FOE},necroDestroyer",
            "--hp-player", "400000", "--hp-target", "400000"]
    proc = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not STATE.exists():
        print(f"[sp] build KO: {(proc.stderr or proc.stdout or '')[-600:]}")
        sys.exit(2)
    return json.loads(STATE.read_text())["runnerId"]


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _units(dec):
    return [u for u in (dec.get("units") or []) if u.get("alive")]


def _by_vis(dec, vis):
    return next((u for u in _units(dec) if u.get("visualId") == vis), None)


def _off_pos(state, uid):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _off_kell(state):
    """Le Kell OFFLINE : une unite `astraSmnKell` vivante, quel que soit son id (le spawn en cree un
    neuf). On ne filtre pas sur le parent, pour ne pas dependre du cablage de `Unit_Parent_Id`."""
    for uid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.alive and uc.visual_id == KELL:
            return int(uid)
    return None


def _act(rpc, rid, action, t=120):
    return rpc("applyAction", {"runnerId": rid, "action": action}, t) or {}


def _place(rpc, rid, creed, foe, att_tile):
    """Amene Creed sur `CREED_TILE` et l'attaquant sur `att_tile`, en pilotant les DEUX camps
    (`applyAction` ne verifie pas la propriete). Le trajet passe par des tuiles intermediaires :
    la portee de mouvement d'un tour ne suffit pas a traverser le board."""
    _act(rpc, rid, {"kind": "move", "unitId": creed, "to": {"col": 2, "row": 2}})
    _act(rpc, rid, {"kind": "endturn"})
    _act(rpc, rid, {"kind": "move", "unitId": foe, "to": {"col": 5, "row": 6}})
    _act(rpc, rid, {"kind": "endturn"})
    _act(rpc, rid, {"kind": "move", "unitId": creed,
                    "to": {"col": CREED_TILE[0], "row": CREED_TILE[1]}})
    _act(rpc, rid, {"kind": "endturn"})
    _act(rpc, rid, {"kind": "move", "unitId": foe,
                    "to": {"col": att_tile[0], "row": att_tile[1]}})


def _round(rpc, rid, board, att_tile):
    """UN montage : place, rejoue OFFLINE l'attaque normale, puis la MEME attaque LIVE, compare."""
    dec = _dv(rpc, rid)
    creed_u, foe_u = _by_vis(dec, CREED), _by_vis(dec, FOE)
    if creed_u is None or foe_u is None:
        print("[sp] roster live incomplet")
        return None
    creed, foe = creed_u["id"], foe_u["id"]
    _place(rpc, rid, creed, foe, att_tile)

    dec = _dv(rpc, rid)
    creed_u, foe_u = _by_vis(dec, CREED), _by_vis(dec, FOE)
    if creed_u is None or foe_u is None:
        return None
    cpos, apos = _pos(creed_u), _pos(foe_u)
    if hexgeo.distance(cpos, apos) != 1:
        print(f"[sp] att_tile={att_tile}: pas au contact ({apos} vs {cpos}) -- non discriminant")
        return None
    # TEMOIN NON DEGENERE : combien de tuiles libres autour de Creed ? 1 seule => aucun tri possible.
    ctid = board.id_at(cpos[0], cpos[1])
    occ = {_pos(u) for u in _units(dec)}
    free = [board.coord(t) for t in board.neighbours(ctid) if board.coord(t) not in occ]
    if len(free) < 2:
        print(f"[sp] att_tile={att_tile}: {len(free)} tuile(s) libre(s) -- REGIME DEGENERE, ecarte")
        return None

    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    state = load_state(dec, ob, snap, board=board)
    if s0 and s0.get("mt"):
        state.rng = _seed_rng(s0)

    # --- OFFLINE : l'attaque normale de l'ennemi sur Creed reveille SwornProtector ---
    # Voie NORMALE du port (`DamageHandler.visit_AttackUnitMessage`) -- c'est celle qui emet
    # `On(0x2a = PreUnitAbility)` pour une attaque d'ARME, donc celle qui reveille SwornProtector.
    # (`ActiveAbilityMessage(69)` passerait par le registre d'abilities, ou `Loki_NormalAttack`
    # n'a pas de classe : `ported:False`, aucun vecteur, aucun Kell -- un no-op silencieux.)
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(attacker_id=foe, target_id=creed))
    ok = _off_kell(state)
    off_kell_pos = _off_pos(state, ok) if ok is not None else None
    off_d = None
    if _off_pos(state, foe) and _off_pos(state, creed):
        off_d = hexgeo.distance(_off_pos(state, foe), _off_pos(state, creed))

    # --- LIVE : la MEME attaque ---
    r = _act(rpc, rid, {"kind": "ability", "casterId": foe, "targetId": creed,
                        "abilityType": NORMAL_ATTACK}, 240)
    a0 = ((r or {}).get("actions") or [{}])[0]
    if not a0.get("ok"):
        print(f"[sp] att_tile={att_tile}: attaque LIVE KO {str(r)[:250]}")
        return None
    dec2 = _dv(rpc, rid)
    lk, lc, la = _by_vis(dec2, KELL), _by_vis(dec2, CREED), _by_vis(dec2, FOE)
    live_kell_pos = _pos(lk) if lk is not None else None
    live_d = (hexgeo.distance(_pos(la), _pos(lc))
              if (la is not None and lc is not None) else None)

    row = {"att_tile": att_tile, "creed0": cpos, "free": len(free),
           "kell_off": off_kell_pos, "kell_live": live_kell_pos,
           "d_off": off_d, "d_live": live_d}
    print(f"[sp] att={apos} creed0={cpos} libres={len(free)} | KELL off={off_kell_pos} "
          f"live={live_kell_pos} | d(att,creed) off={off_d} live={live_d}")
    return row


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="4242")
    ap.add_argument("--board", default="MC1_67")
    a = ap.parse_args(argv if argv is not None else sys.argv[1:])

    sid = _resolve_session()

    def rpc(m, b, t=90):
        return _r(sid, m, b, t)

    rows = []
    for att_tile in ATTACK_TILES:
        rid = build(a.seed, a.board)      # un runner NEUF par geometrie (Kell est one-shot)
        print(f"[sp] runner={rid} att_tile={att_tile}")
        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            if not (isinstance(bg, dict) and bg.get("tiles")):
                print("[sp] boardGraph KO")
                continue
            row = _round(rpc, rid, Board(bg["tiles"], adjacency="native_sym"), att_tile)
            if row is not None:
                rows.append(row)
        finally:
            rpc("disposeRunner", {"runnerId": rid}, 60)

    if not rows:
        print("[sp] AUCUN montage NON DEGENERE joue -- rien n'est mesure, verdict IMPOSSIBLE")
        return 2
    same = [r for r in rows if r["kell_off"] == r["kell_live"]]
    dsame = [r for r in rows if r["d_off"] == r["d_live"]]
    print(f"[sp] ACCORD d(att,creed) : {len(dsame)}/{len(rows)}   <- LE critere | "
          f"tuile de Kell (non discriminante) : {len(same)}/{len(rows)}")
    # TEMOIN DE NON-DEGENERESCENCE : si le natif rend la MEME distance sur tous les montages, un
    # accord ne separe rien d'une constante. On l'exige explicitement plutot que de le supposer.
    if len(rows) > 1 and len({r["d_live"] for r in rows}) < 2:
        print("[sp] REGIME DEGENERE : le natif rend la meme distance partout -- accord SANS VALEUR")
        return 2
    for r in rows:
        if r["d_off"] != r["d_live"]:
            print(f"[sp]   DESACCORD {r}")
    ok = len(dsame) == len(rows)
    print("[sp] " + ("PROBE OK" if ok else "PROBE KO"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
