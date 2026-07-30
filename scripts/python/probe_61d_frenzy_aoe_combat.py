"""#61 -- VOLET AoE de FrenziedFiring (1036), face **COMBAT** : le natif qui caste vs le port.

Pendant COMBAT de `probe_61c_frenzy_aoe.py` (qui, lui, confronte la face DECISION/playbook).
L'artefact natif est `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$ExecuteBehaviour` :

    hitsNode = GetHitsForOriginalTarget(this)
    A = SetCache(hitsNode) & AttackWithAttackDamage(caster@0x160, target@0x178, hits = hitsNode)
    B = SetCache(hitsNode) & AttackWithAttackDamage(caster@0x160,
                                AdjacentEnemies(caster@0x160, targetTiles@0x190, 1),
                                hits = DSLFactory.Direct(1))
    AtomicGroup(0x4e, <ExecuteBehaviour>b__0)   ou b__0 = Execute( op_Addition(A, B) )

Le probe DRIVE la geometrie (K ennemis sur l'anneau hex de la cible), rejoue l'ability OFFLINE avec
`state.rng` cale (`dumpRng`), PUIS la caste LIVE dans le MEME etat, et compare PAR CIBLE le nombre de
coups appliques ET le degat par coup.

  - oracle NATIF   : un evenement de degat par COUP applique (`Amount` + `Target_Id` +
                     `Active_Ability_Type == 1036`), meme compteur que `probe_61_ability_hits.py`.
  - oracle MOTEUR  : `ABILITY_CLASSES[1036].execute_behaviour` (arbre DSL `frenzied_firing_tree`).

LE CASTER EST DEPLACE, en DERNIER, juste avant le cast : le `UnitFlag.Moved` que
`IdunBattle.Operations.MoveUnitOperation$$Execute` pose desarme le +25% ranged d'`HeavyWeapon_ExtraDmg`
que Volk porte, et `load_state` le lit du MEME canal que le natif
(`combatSnapshot.units[].unitFlags` -> `snapshot._load_unit_flags` -> `components.unit_has_moved`).
L'ORDRE est contraint par le turn-flow, pas par le port : une unite qui a bouge n'a plus d'action
pendante, et sur un roster 1 vs 4 tout deplacement ADVERSE qui suit fait basculer `currentPlayer`
(mesure) -- le cast deviendrait illegal.

Aucune valeur attendue codee en dur : l'oracle est le natif qui tourne. ASCII only.

CLI (depuis scripts/python) :
  python probe_61d_frenzy_aoe_combat.py --board MC1_67 --seed 61301 --k 0   # volet AoE INERTE
  python probe_61d_frenzy_aoe_combat.py --board MC1_67 --seed 61302 --k 3   # volet AoE MORDANT
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo
import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

FRENZY = 1036
CASTER_VIS = "blackObliterator"
# TEMOINS NEUTRES par defaut : AUCUN trait/effet qui morde le canal de coups partage (`GetAttackHits`
# -- BigTarget/Parry/Camouflage/Diminutive/MasterAnnihilator/LightCover). Ce choix ISOLE le volet
# porte : sur un roster quelconque, les malus/bonus du canal (deja livres en case-61, appliques aux
# DEUX vecteurs) melangeraient leur verdict au mien.
FOE_VIS = ["necroWarden", "necroOverlord", "admecMarshall", "eldarAutarch"]
# `DamageProfileType.HeavyRound` = le profil des DEUX volets de 1036 (`GetDamageProfile` config).
PROFILE_HEAVY_ROUND = 19


def _res(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def rpc(sid, method, body=None, timeout=120):
    return _res(R._rpc(sid, method, [body] if body is not None else [], timeout=timeout))


def decision(sid, rid):
    return rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _move(sid, rid, uid, coord):
    rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": coord[0], "row": coord[1]}}}, 60)


def build(sid, seed, board, foes=None):
    """Monte un runner ISOLE (state-file dans logs/, hors data/) et rend son runnerId."""
    state = ROOT / "logs" / f"probe61d-{seed}.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--roster", "1",
            "--p-units", CASTER_VIS, "--a-units", ",".join(foes or FOE_VIS),
            "--hp-target", "90000"]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("build KO: %s" % ((p.stderr or p.stdout or "")[-500:]))
        return None, state
    return json.loads(state.read_text())["runnerId"], state


def _my_turn(sid, rid, owner, max_turns=8):
    for _ in range(max_turns):
        if decision(sid, rid).get("currentPlayer") == owner:
            return True
        rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return False


def _step_caster_aside(sid, rid, board, cid, tpos, forbidden):
    """PAS MINIMAL du caster, sous contraintes de geometrie : destination a distance 2..3 de la cible
    (ni adjacente -- ce qui changerait le `Count` de tuiles libres lu par
    `FrenziedFiringAbility$$GetHitsForOriginalTarget` -- ni hors portee), hors de `forbidden`
    (l'anneau AoE + la tuile de la cible) et hors des tuiles occupees. Le `UnitFlag.Moved` que
    `MoveUnitOperation$$Execute` pose est LU par `load_state` (`snapshot._load_unit_flags`), donc le
    gate no-move d'`HeavyWeapon_ExtraDmg` se ferme des deux cotes. UN SEUL essai : une unite ne
    dispose que d'UN deplacement par tour. Rend la position finale, inchangee si rien ne convient."""
    mt = rpc(sid, "aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
    row = next((x for x in ((mt or {}).get("units") or []) if x.get("unitId") == cid), None)
    dv = decision(sid, rid)
    cur = _pos(next((u for u in (dv.get("units") or []) if u.get("id") == cid), None))
    occupied = {_pos(u) for u in (dv.get("units") or []) if u.get("alive")} - {cur}

    def nbf(c):
        nid = board.id_at(c[0], c[1])
        return len([n for n in board.neighbours(nid) if board.walkable(n)]) if nid is not None else 0

    tiles = [c for c in ((t["col"], t["row"]) for t in ((row or {}).get("tiles") or []))
             if c != cur and c not in forbidden and c not in occupied
             and (tpos is None or 2 <= hexgeo.distance(c, tpos) <= 3)]
    if not tiles:
        return cur
    tiles.sort(key=lambda c: (hexgeo.distance(c, cur) if cur else 0, -nbf(c)))
    _move(sid, rid, cid, tiles[0])
    return _pos(next((u for u in (decision(sid, rid).get("units") or [])
                      if u.get("id") == cid), None)) or cur


def offline_cast(sid, rid, cid, tid):
    """Rejoue 1036 OFFLINE depuis l'etat live courant (`state.rng` cale via `dumpRng`, DERNIER RPC
    avant le cast live). Rend `{target: [degats par coup]}`."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.abilities.handler import ABILITY_CLASSES

    cls = ABILITY_CLASSES.get(FRENZY)
    if cls is None:
        return None, "AUCUNE classe portee pour 1036 (ABILITY_CLASSES)"
    bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym") if isinstance(bg, dict) and bg.get("tiles") \
        else None
    dv = decision(sid, rid)
    ob = rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = rpc(sid, "combatSnapshot", {"runnerId": rid}, 90)
    st = load_state(dv, ob, snap, board=board)
    s0 = rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    rng = IntBasedMersenneTwister()
    if isinstance(s0, dict) and s0.get("mt"):
        rng.mt = list(s0["mt"]); rng.mti = s0["mti"]
    else:
        return None, "dumpRng KO (rng non cale -> aucune comparaison per-coup possible)"
    st.rng = rng
    res = cls().execute_behaviour(st, cid, tid) or {}
    out, extra = {}, {}

    def _row(t, atk):
        out[t] = list((atk or {}).get("per_hit") or [])
        ah = (atk or {}).get("additional_hits") or {}
        if ah.get("per_hit"):
            extra[t] = list(ah["per_hit"])          # canal #179 (profil PROPRE, hors arbre 1036)

    _row(tid, res.get("origin_attack"))
    for row in (res.get("aoe") or []):
        _row(row["target"], row.get("attack"))
    return out, extra, None


def live_cast(sid, rid, cid, tid):
    """Caste 1036 LIVE et rend `({target: [degats des coups HeavyRound]}, {target: [autres coups]})`.

    VENTILATION PAR PROFIL, indispensable : le caster `blackObliterator` porte EN PERMANENCE un effet
    du cycle `FleshmetalGuns` (canal #179 `additional_hit_groups`), qui greffe sur CHAQUE attaque des
    coups d'un profil PROPRE (Melta/Flame/HeavyRound selon le tour du cycle). Ces coups sont produits
    par `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`,
    une sous-operation de l'`AttackDamageOperation$$Execute` — ils N'APPARTIENNENT PAS a l'arbre
    `FrenziedFiringAbility$$ExecuteBehaviour`. On les separe par `DamageProfileType` (tag natif) pour
    mesurer le volet porte sans ce bruit."""
    res = rpc(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": FRENZY},
        "captureEvents": True}, 120)
    per, other = {}, {}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" not in td or td.get("Active_Ability_Type") != FRENZY:
                continue
            dst = per if td.get("DamageProfileType") == PROFILE_HEAVY_ROUND else other
            dst.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return per, other, res


def _fmt(per):
    return " ".join("u%s:%dx%s" % (t, len(v), v) for t, v in sorted(per.items(),
                                                                    key=lambda x: x[0] or 0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sid", type=int)
    ap.add_argument("--runner", type=int)
    ap.add_argument("--seed", default="61301")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--k", type=int, default=3, help="nb d'ennemis places sur l'anneau de la cible")
    ap.add_argument("--foes", default=",".join(FOE_VIS), help="roster adverse (temoins neutres)")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    sid = a.sid or R._resolve_session()
    state = None
    rid = a.runner
    if rid is None:
        rid, state = build(sid, a.seed, a.board, [x for x in a.foes.split(",") if x.strip()])
        if rid is None:
            return 2
    try:
        from engine.entities.pathfinding.board import Board
        bg = rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        board = Board(bg["tiles"], adjacency="native_sym")
        dv = decision(sid, rid)
        me = next((u for u in (dv.get("units") or [])
                   if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
        foes = [u for u in (dv.get("units") or [])
                if u.get("owner") != (me or {}).get("owner") and u.get("alive")]
        if me is None or len(foes) < 1:
            print("caster/ennemis absents (me=%s foes=%d)" % (bool(me), len(foes)))
            return 2
        if not _my_turn(sid, rid, me.get("owner")):
            print("tour du caster non atteint")
            return 2

        walk = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

        def nb_free(coord):
            return [n for n in board.neighbours(board.id_at(coord[0], coord[1]))
                    if board.walkable(n)]

        cpos = _pos(me)
        open_tiles = [c for c in walk
                      if len(nb_free(c)) == 6 and 2 <= hexgeo.distance(c, cpos) <= 3]
        if not open_tiles:
            print("board sans tuile a 6 voisins marchables a portee du caster @%s" % (cpos,))
            return 2
        tcoord = max(open_tiles, key=lambda c: hexgeo.distance(c, cpos))
        tgt, others = foes[0], foes[1:]
        _move(sid, rid, tgt["id"], tcoord)
        dv = decision(sid, rid)
        tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt["id"]), None)
        tcoord = _pos(tu) or tcoord
        # Anneau exploitable = voisins marchables de la cible, hors tuile du caster, tries du PLUS
        # LOIN du caster au plus proche : un ennemi pose entre le caster et la cible OBSCURCIT la
        # ligne de tir et rend le cast ILLEGAL (mesure : k=3 sur les voisins « cote caster » ->
        # `applyAction ability` accepte mais n'emet AUCUN degat). On garnit donc l'anneau par
        # l'arriere de la cible.
        ring = sorted((board.coord(n) for n in nb_free(tcoord) if board.coord(n) != cpos),
                      key=lambda c: -hexgeo.distance(c, cpos))
        far = [c for c in walk if hexgeo.distance(c, tcoord) > 4
               and hexgeo.distance(c, cpos) > 4]
        for i, u in enumerate(others):
            if i < a.k and i < len(ring):
                _move(sid, rid, u["id"], ring[i])
            elif far:
                _move(sid, rid, u["id"], far[(i * 7) % len(far)])

        dv = decision(sid, rid)
        tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt["id"]), None)
        real = _pos(tu)
        adj_foes = sorted(u.get("id") for u in (dv.get("units") or [])
                          if u.get("alive") and u.get("id") != tgt["id"]
                          and u.get("owner") != me.get("owner") and _pos(u)
                          and hexgeo.distance(_pos(u), real) == 1)

        # Garde de LEGALITE : sans elle, un cast refuse (ligne de tir obscurcie) rend 0 event de
        # degat et se lirait a tort comme « le natif ne fait rien ».
        at = rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": me["id"],
                                         "abilityType": FRENZY}, 120)
        ab = next((x for u in (at.get("units") or []) for x in (u.get("abilities") or [])
                   if x.get("abilityId") == FRENZY), {})
        if tgt["id"] not in [x.get("targetId") for x in (ab.get("fromHere") or [])]:
            print("cast u%s -> u%s NON legal depuis la position courante (fromHere=%s)"
                  % (me["id"], tgt["id"], [x.get("targetId") for x in (ab.get("fromHere") or [])]))
            return 2

        # DEPLACEMENT REEL DU CASTER, en DERNIER (cf. en-tete). Il doit venir APRES tout le pilotage
        # adverse : une unite qui a bouge n'a plus d'action pendante, donc bouger un ennemi ensuite
        # ferait BASCULER le tour (roster 1 vs 4, mesure) et le cast deviendrait illegal.
        moved_to = _step_caster_aside(sid, rid, board, me["id"], real, set(ring) | {real})
        print("caster DEPLACE %s -> %s (UnitFlag.Moved pose)" % (cpos, moved_to))
        if moved_to == cpos:
            print("aucun pas du caster ne preserve la geometrie -> flag Moved non exerce")
        at = rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": me["id"],
                                         "abilityType": FRENZY}, 120)
        ab = next((x for u in (at.get("units") or []) for x in (u.get("abilities") or [])
                   if x.get("abilityId") == FRENZY), {})
        if tgt["id"] not in [x.get("targetId") for x in (ab.get("fromHere") or [])]:
            print("le pas du caster vers %s a rendu le cast illegal" % (moved_to,))
            return 2

        off, off_extra, err = offline_cast(sid, rid, me["id"], tgt["id"])
        if off is None:
            print("offline KO: %s" % err)
            return 2
        live, other, res = live_cast(sid, rid, me["id"], tgt["id"])

        print("\n[#61d frenzy AoE COMBAT] runner=%s board=%s k=%d ok=%s"
              % (rid, a.board, a.k, (res or {}).get("ok")))
        print("  caster u%s @%s (DEPLACE depuis %s) | cible u%s @%s (voisins marchables=%d)"
              % (me["id"], moved_to, cpos, tgt["id"], real, len(nb_free(real))))
        print("  ennemis ADJACENTS a la cible (= volet AoE attendu) : %s" % (adj_foes or "aucun"))
        print("  NATIF HeavyRound (= l'arbre 1036)  %s" % _fmt(live))
        print("  NATIF autres profils (canal #179)  %s" % (_fmt(other) or "aucun"))
        print("  MOTEUR HeavyRound                  %s" % _fmt(off))
        print("  MOTEUR canal #179                  %s" % (_fmt(off_extra) or "aucun"))
        if not live:                       # aucun event : le cast a-t-il seulement eu lieu ?
            print("  (diag) applyAction -> %s" % json.dumps(
                {k: v for k, v in (res or {}).items() if k != "actions"})[:400])
            kinds = [(act.get("kind"), len(act.get("events") or []))
                     for act in ((res or {}).get("actions") or [])]
            print("  (diag) actions=%s" % kinds)
            allt = set()
            for act in ((res or {}).get("actions") or []):
                for e in (act.get("events") or []):
                    td = e.get("tags")
                    td = json.loads(td) if isinstance(td, str) else (td or {})
                    if "Amount" in td:
                        allt.add((td.get("Active_Ability_Type"), td.get("Target_Id")))
            print("  (diag) events de degat (abilityType, target) = %s" % sorted(allt, key=str))
        nat_n = {t: len(v) for t, v in live.items()}
        off_n = {t: len(v) for t, v in off.items() if v}
        print("  verdict CIBLES : %s" % ("OK" if set(nat_n) == set(off_n)
                                         else "MISMATCH nat=%s port=%s"
                                              % (sorted(nat_n), sorted(off_n))))
        print("  verdict COUPS  : %s" % ("OK" if nat_n == off_n
                                         else "MISMATCH nat=%s port=%s" % (nat_n, off_n)))
        same_ph = all(list(live.get(t) or []) == list(off.get(t) or [])
                      for t in set(nat_n) | set(off_n))
        print("  verdict PER-COUP : %s" % ("BIT-EXACT" if same_ph else "DIFF"))
        return 0 if (nat_n == off_n and same_ph) else 1
    finally:
        if state is not None and not a.keep:
            rpc(sid, "disposeRunner", {"runnerId": rid}, 20)
            state.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
