#!/usr/bin/env python
"""probe #308 -- MONTAGE NOMME du `+1` que l'attaque NORMALE ajoute a son utilite d'ACTION.

QUESTION BINAIRE : retirer ce `+1` change-t-il une decision OBSERVABLE, et le montage le voit-il ?

NATIF (relu au decompile, build `rnca9r7q6c` -- TROIS corps DISTINCTS, adresses distinctes, pas une
deduplication) :

    IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility
        -> FixMath.NET.Fix64$$op_Implicit(0)                     # la BASE rend Fix64(0)
    IdunBattle.AI.Playbook.Loki.ALoki_NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility
        -> FixMath.NET.Fix64$$op_Implicit(1)                     # Fix64(1)
    IdunBattle.AI.Playbook.Idun.NormalAttackPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility
        -> FixMath.NET.Fix64$$op_Implicit(1)                     # Fix64(1)
    IdunBattle.AI.Playbook.Loki.Loki_NormalBossAttackPlaybook$$CalculateCustomUtility
        -> FixMath.NET.Fix64$$op_Implicit(1)                     # Fix64(1)

Le terme entre dans le comparatif AVANT tout argmax -- lu dans
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility` :

    u  = Fix64(0)
    c  = vtable[+0x338](...)                                  # CalculateCustomUtility
    if c == BaseUtility.<statics+0x18> or c == <statics+0x20>: return Nullable VIDE
    if c == BaseUtility.<statics+0x10>:                        return Nullable(MaxValue)
    u  = Fix64.op_Addition(u, c)                               # <-- le +1 est ici
    u  = Fix64.op_Addition(u, CalculateUtilityFromPredictions(...))
    if vtable[+0x328](u):                                      # ShouldExecute
        u += vtable[+0x348](...)                               # fold EFFET
        u += UtilityAttackCase.Base(...)
        u += CalculateUtilityFromTilePrediction(...)           # terme Tile(7)
        return Nullable(u)

=> l'attaque normale bat tout autre actif Comparable tant que
`u_pair(autre) - u_pair(normale) < 1` a tuile egale. C'est ce regime, et lui seul, que ce montage
fabrique -- une fenetre d'exactement UN point d'utilite.

COTE PORT : `engine.playbook.common.NormalAttackPlaybook.calculate_custom_utility` rend `1.0`, la
base `engine.playbook.base.ComparablePlaybook.calculate_custom_utility` rend `0.0`, et
`engine.ai.action_generators.ComparableAbilityGenerator._action_utility` fait
`u_action = u_full + custom`. Le terme est DEJA porte et DEJA juste : ce probe ne le porte pas, il
le GARDE.

MONTAGE (fixture nommee `NA_BONUS_FIXTURE`) :
  - `custoBladeChampion` (Kariyan) SEUL cote joueur. Son kit est un duel a deux termes exactement :
    l'attaque NORMALE (melee, 3 coups, profil Power, pierce 40) et l'active `MartialInspiration`
    (1191). C'est le porteur du datapoint historique #64 (`2468 s18 u77` : 69 = 20.981 pair + 40
    tile + 1 = 61.981 bat 1191 = 21.728 + 40 + 0 = 61.728).
  - `necroWarden` SEUL cote adverse, AMENE AU CONTACT du caster (`applyAction move`) : les deux
    abilities sont alors castables depuis la tuile COURANTE du caster, donc comparables a terme
    Tile identique.
  - le passif `LegacyOfCombat` est RETIRE (`--unit-stat custoBladeChampion:PassiveAbilities=[]`) :
    controle de MONTAGE, pas une modification du mecanisme sous test. Un passif porte parfois un
    terme de TUILE que le port n'a pas (mesure #27-r1 sur `ModifiedExoarmour_LikesMovingPerTile`),
    ce qui ferait diverger moteur et natif pour une raison ETRANGERE au `+1`.
  - CURSEUR : `--unit-stat custoBladeChampion:Damage=<D>`. Il deplace l'utilite de l'attaque
    NORMALE (dont la base vient de l'arme) et **pas** celle de 1191, dont la base est
    `round(minDmg x (extraDmgPct x TotalAttacksMade + 100)/100)` -- entierement issue de la config
    d'ability (`MartialInspirationPlaybook.u003CMakeDamagePredictionsu003Ed__2$$MoveNext`). Le probe
    le MESURE (`pairUtility(1191)` bit-identique sur tout le balayage), il ne le suppose pas.

CALIBRAGE : `--auto` bisecte sur `Damage` le seuil ou le NATIF bascule de 1191 vers l'attaque
normale, au pas de 1. Juste AU-DESSUS de ce seuil, `u_pair(1191) - u_pair(69)` est compris entre
`1 - pente` et `1` : le natif joue la normale UNIQUEMENT grace au `+1`. C'est la fenetre.

VERDICTS RENDUS :
  V1 la fenetre est REELLE   : natif = attaque normale, et `0 < pair(1191) - pair(69) < 1` ;
  V2 le moteur SUIT le natif dans la fenetre (et dans le bras temoin, sous le seuil) ;
  V3 SENSIBILITE / MUTATION  : le MEME moteur dont on force `calculate_custom_utility` a `0.0`
     bascule sur 1191 dans la fenetre -> le `+1` est LOAD-BEARING et le montage le VOIT ;
  V4 le curseur est PROPRE   : `pairUtility(1191)` est invariant sur tout le balayage `Damage`.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_308_normal_attack_bonus.py                      # fixture de reference
    python probe_308_normal_attack_bonus.py --auto               # re-bisecte la fenetre
    python probe_308_normal_attack_bonus.py --auto --board C3_01 --seed 777

ASCII only (cp1252). Sorties sous `logs/` (relatif au checkout). Dispose SES runners.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import hexgeo

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

CARRIER = "custoBladeChampion"    # Kariyan -- normale (melee 3 coups) + MartialInspiration (1191)
TARGET = "necroWarden"            # cible robuste, amenee au contact
BOARD = "MC1_67"
SEED = 3081
RANK = 17
MARTIAL_INSPIRATION = 1191

# `Damage` du caster ENCADRANT la bascule native, MESURES par `--auto` (bisection au pas de 1) sur
# la fixture de reference (MC1_67 / seed 3081, passif retire). Ils ne sont pas un reglage de
# gameplay : ce sont les deux bras d'un A/B.
#   D_BELOW  -- juste SOUS le seuil : le natif joue 1191 (bras TEMOIN, le `+1` ne suffit pas) ;
#   D_WINDOW -- juste AU-DESSUS : le natif joue la NORMALE alors que le scorer natif de PAIRE
#               classe 1191 DEVANT -> seul le `+1` explique ce choix (bras DISCRIMINANT).
# Re-derivables a tout moment par `--auto` ; le montage REFUSE de conclure s'ils ne produisent plus
# le regime (cf. `verdicts`), plutot que de mesurer du vide.
#
# MESURE (2026-07-30, build `rnca9r7q6c`, bisection au pas de 1 sur [200, 2000]) -- le seuil natif
# est EXACTEMENT la ou l'ecart de paire franchit 1 :
#     Damage=1189 : pair(69)=20.8714  pair(1191)=21.9021  gap=1.0307 > 1  -> natif joue 1191
#     Damage=1190 : pair(69)=20.9065  pair(1191)=21.9021  gap=0.9955 < 1  -> natif joue 69
# Un pas de 1 sur `Damage` vaut ~0.035 point d'utilite : la fenetre est donc traversee a la
# resolution la plus fine que le curseur permette.
#
# GENERALISATION mesuree le meme jour (C3_01 / seed 777 / cible `ultraCalgar`, regime numerique tout
# AUTRE -- pair 8.7850 / 9.8019) : bascule a Damage 1397 / 1398, gap 1.0169 -> 0.9959. Le seuil tombe
# donc ENCORE au franchissement de 1.0 a une echelle d'utilite deux fois plus petite -> le terme est
# un `+1` ABSOLU, pas un facteur relatif.
#
# CIBLE A EVITER pour ce montage : `tauCrisis` (trait `BigTarget`). Le port y sous-predit 1191 --
# raw [1496, 2244] au lieu de [1795, 2693], soit le facteur x1.2 qu'il applique pourtant a l'attaque
# normale ([1428, 2142] -> [1713, 2571]) -- ce qui fait diverger moteur et natif pour une raison
# ETRANGERE au terme teste (pair natif 21.2822 vs porte 17.7352). Residu DISTINCT, inventorie :
# `docs/rl/port-residuals-inventory.md` §4.a `N16` (backlog `#308-r`).
D_BELOW, D_WINDOW = 1189, 1190

STATE = ROOT / "logs" / "runners" / "probe_308_na_bonus.json"

# Bornes de RECHERCHE de la bisection (pas des valeurs de gameplay) : a `Damage` tres bas la
# normale est ecrasee par 1191, a `Damage` tres haut elle ecrase 1191.
BISECT_LO, BISECT_HI = 1, 40000


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


# ---------------------------------------------------------------- harnais runner
def _build(sid, damage: int, board: str, seed: int, state_file: Path,
           target: str = TARGET) -> int:
    """Monte le runner de la fixture. Chaque build REMPLACE le scope de CE `--state-file` : le
    runner ENREGISTRE dans ce fichier est dispose par `rl_duel build` lui-meme, les freres des
    autres agents sont intouches.

    NE PAS effacer le state-file avant le build. Ce probe enchaine une VINGTAINE de builds (la
    bisection) sur le meme fichier : l'effacer prive `rl_duel build` du runnerId a remplacer, donc
    chaque iteration FUIT un runner. Mesure du 2026-07-30 : cap `MAX_RUNNERS` (50) sature en une
    seule passe, 49 orphelins a purger. Le prix a payer est qu'un state-file PERIME (run precedent
    tue) pourrait etre relu tel quel -- d'ou la verification que le runnerId a bien CHANGE."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    prev = None
    if state_file.exists():
        try:
            prev = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
        except Exception:                                   # noqa: BLE001  (fichier illisible)
            state_file.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
         "--state-file", str(state_file), "--board", board, "--rank", str(RANK),
         "--p-units", CARRIER, "--a-units", target,
         "--crit", "0,0", "--block-target", "0,0",
         "--unit-stat", "%s:PassiveAbilities=[]" % CARRIER,
         "--unit-stat", "%s:Damage=%d" % (CARRIER, damage)],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO (Damage=%d) : %s"
                           % (damage, (proc.stderr or proc.stdout or "")[-600:]))
    rid = int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])
    if prev is not None and rid == prev:
        raise RuntimeError("build KO (Damage=%d) : le state-file rend encore le runner %d -- "
                           "aucun nouveau runner n'a ete construit : %s"
                           % (damage, prev, (proc.stderr or proc.stdout or "")[-600:]))
    return rid


def _view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)


def _by_visual(dv, vis):
    for u in (dv.get("units") or []):
        if u.get("visualId") == vis:
            return u
    return None


def _pos(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _normal_attack_id(dv, uid):
    """Id CONCRET de l'attaque normale du caster (`kind == "normal"` de `decisionView`) -- PER-UNITE,
    jamais le 17 generique (cf. `NormalAttackType@0x28`)."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    for a in ((u or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return a.get("id")
    return None


def _adjacent_free(brd, center, occupied):
    """Une tuile libre VOISINE au sens NATIF (`boardGraph.neighbours`), pas au sens hexgeo."""
    for tid in brd.neighbours(brd.id_at(*center)):
        c = brd.coord(tid)
        t = brd.by_id.get(tid) or {}
        if c and c not in occupied and t.get("walkable") and not t.get("isWall"):
            return c
    return None


def place(sid, rid, target: str = TARGET) -> dict:
    """Pose la GEOMETRIE : la cible est amenee AU CONTACT du caster, qui ne bouge pas. Rend les ids
    et l'id d'attaque normale. Un placement REFUSE ne leve rien cote runner -- on le CONSTATE et on
    refuse de mesurer, plutot que de degrader silencieusement le montage en un scenario ou les deux
    bras seraient identiques."""
    from engine.entities.pathfinding.board import Board
    dv = _view(sid, rid)
    car, tgt = _by_visual(dv, CARRIER), _by_visual(dv, target)
    if car is None or tgt is None:
        raise RuntimeError("roster incomplet : carrier=%s target=%s" % (car, tgt))
    cid, tid = car["id"], tgt["id"]
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    brd = Board(bg["tiles"], adjacency="native_sym")
    occupied = {p for p in (_pos(u) for u in (dv.get("units") or [])) if p}
    cpos = _pos(car)
    spot = _adjacent_free(brd, cpos, occupied - {_pos(tgt)})
    if spot is None:
        raise RuntimeError("aucune tuile libre voisine du caster @%s" % (cpos,))
    _move(sid, rid, tid, spot[0], spot[1])
    dv = _view(sid, rid)
    cpos, tpos = _pos(_by_visual(dv, CARRIER)), _pos(_by_visual(dv, target))
    if cpos is None or tpos is None or hexgeo.distance(cpos, tpos) != 1:
        raise RuntimeError("contact NON etabli : caster @%s cible @%s" % (cpos, tpos))
    na = _normal_attack_id(dv, cid)
    if na is None:
        raise RuntimeError("aucune attaque normale (`kind == normal`) sur u%d" % cid)
    return {"caster": cid, "target": tid, "normal": na, "caster_pos": cpos, "target_pos": tpos,
            "dv": dv}


# ---------------------------------------------------------------- mesures
def native_choice(sid, rid, cid):
    """Action que l'IA NATIVE propose pour le caster (`aiDryRunAllUnits`) : (abilityType, tuile)."""
    dr = _r(sid, "aiDryRunAllUnits", {"runnerId": rid}, 180)
    prop = next((u.get("proposed") for u in (dr.get("units") or [])
                 if u.get("unitId") == cid), []) or []
    ab = next((m.get("abilityType") for m in prop if m.get("cls") == "ActiveAbilityMessage"), None)
    mv = next((((m.get("to") or {}).get("col"), (m.get("to") or {}).get("row"))
               for m in prop if m.get("cls") == "MoveUnitMessage"), None)
    return ab, mv


def native_pair(sid, rid, cid, tid, ability, tile):
    """`pairUtility` = `ComparablePlaybook<T>$$CalculateUtilityFromPredictions` invoque en direct :
    la valeur EXACTE que le bucket natif attribue a la paire, SANS le terme Tile ni le custom."""
    r = _r(sid, "pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tid,
                                "abilityType": int(ability),
                                "col": tile[0], "row": tile[1]}, 90)
    return r.get("utility")


def engine_choice(sid, rid, cid, bonus=None):
    """Decision MOTEUR pour le caster. `bonus` non None -> MUTATION : `NormalAttackPlaybook.
    calculate_custom_utility` est force a cette valeur pendant l'appel (et SEULEMENT pendant).
    `bonus=0.0` neutralise donc exactement le terme sous test."""
    import engine_validate as EV
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.playbook.common import NormalAttackPlaybook

    rpc = (lambda m, b, t=90: _r(sid, m, b, t))                   # noqa: E731
    dv = _view(sid, rid)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
    wt = W.load()
    predictor = _scene.build_predictor(rpc, rid)
    if predictor is None:
        raise RuntimeError("build_predictor KO (combatSnapshot indisponible)")

    orig = NormalAttackPlaybook.calculate_custom_utility
    if bonus is not None:
        NormalAttackPlaybook.calculate_custom_utility = (
            lambda self, ctx, tile, target, ab, _v=float(bonus): _v)
    try:
        a = EV.engine_decide(sid, rid, dv, mov_by_unit, cid, wt, predictor)
    finally:
        NormalAttackPlaybook.calculate_custom_utility = orig
    return a.get("ability"), a.get("to")


def ported_bonus() -> tuple:
    """Les DEUX termes portes, lus sur les classes (pas re-derives) : (base, normale)."""
    from engine.playbook.base import ComparablePlaybook
    from engine.playbook.common import NormalAttackPlaybook
    return (ComparablePlaybook.calculate_custom_utility(None, None, None, None, None),
            NormalAttackPlaybook.calculate_custom_utility(None, None, None, None, None))


# ---------------------------------------------------------------- cellule + bisection
def measure(sid, damage: int, board: str, seed: int, state_file: Path, verbose=True,
            target: str = TARGET) -> dict:
    """UNE cellule de l'A/B : monte la fixture a ce `Damage`, pose la geometrie, et rend
    natif / moteur / moteur MUTE + les deux `pairUtility` natives depuis la tuile du caster."""
    rid = _build(sid, damage, board, seed, state_file, target=target)
    g = place(sid, rid, target=target)
    cid, tid, na, cpos = g["caster"], g["target"], g["normal"], g["caster_pos"]
    nab, nmv = native_choice(sid, rid, cid)
    eab, _ = engine_choice(sid, rid, cid)
    mab, _ = engine_choice(sid, rid, cid, bonus=0.0)
    p_na = native_pair(sid, rid, cid, tid, na, cpos)
    p_mi = native_pair(sid, rid, cid, tid, MARTIAL_INSPIRATION, cpos)
    row = {"damage": damage, "runner": rid, "caster": cid, "target": tid, "normal": na,
           "target_visual": target, "caster_pos": cpos, "target_pos": g["target_pos"],
           "native": nab, "native_move": nmv, "engine": eab, "engine_zero_bonus": mab,
           "pair_normal": p_na, "pair_1191": p_mi,
           "gap": (None if (p_na is None or p_mi is None) else p_mi - p_na)}
    if verbose:
        print("   Damage=%-6d r%-4d natif ab=%-5s mv=%-8s | moteur ab=%-5s | moteur SANS le +1 "
              "ab=%-5s | pair(%d)=%s pair(1191)=%s gap=%s"
              % (damage, rid, nab, nmv, eab, mab, na, _f(p_na), _f(p_mi), _f(row["gap"])))
    return row


def _f(v):
    return "None" if v is None else ("%.4f" % v)


def bisect_native_flip(sid, board: str, seed: int, state_file: Path,
                       lo: int = BISECT_LO, hi: int = BISECT_HI,
                       target: str = TARGET) -> tuple:
    """Encadre au pas de 1 le `Damage` ou le NATIF bascule de 1191 vers l'attaque normale.
    Rend `(lo, hi)` avec `hi == lo + 1` : `lo` = dernier bras 1191 (temoin), `hi` = premier bras
    normale (fenetre). C'est ce qui rend la fixture PORTABLE : sur un autre plateau ou un autre
    seed, le point d'equilibre du duel n'est pas le meme et un `Damage` fige mesurerait du vide."""
    cache: dict = {}

    def picks_normal(d: int) -> bool:
        """Bras LEGER : le seuil ne depend que du NATIF, on n'evalue donc pas le moteur ici (la
        cellule complete est re-mesuree ensuite sur les deux bras retenus)."""
        if d not in cache:
            rid = _build(sid, d, board, seed, state_file, target=target)
            g = place(sid, rid, target=target)
            nab, _ = native_choice(sid, rid, g["caster"])
            cache[d] = (nab is not None and nab == g["normal"])
            print("   bisect Damage=%-6d -> natif ab=%s%s"
                  % (d, nab, " (normale)" if cache[d] else ""))
        return cache[d]

    if picks_normal(lo):
        raise RuntimeError("a Damage=%d le natif joue DEJA l'attaque normale : borne basse trop "
                           "haute" % lo)
    if not picks_normal(hi):
        raise RuntimeError("a Damage=%d le natif joue ENCORE 1191 : borne haute trop basse" % hi)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if picks_normal(mid):
            hi = mid
        else:
            lo = mid
    return lo, hi


# ---------------------------------------------------------------- scenario + verdicts
def scenario(board: str = BOARD, seed: int = SEED, damages=None, state_file=None,
             auto: bool = False, verbose: bool = True, target: str = TARGET,
             bisect_lo: int = BISECT_LO, bisect_hi: int = BISECT_HI) -> dict:
    """Monte les deux bras (temoin + fenetre) et rend `{rows, damages, ...}`.
    `auto=True` re-derive les deux `Damage` par bisection au lieu de lire les constantes."""
    sid = _resolve_session()
    sf = Path(state_file) if state_file else STATE
    if auto or not damages:
        if verbose:
            print("=== bisection du seuil de bascule natif (board=%s seed=%s cible=%s) ==="
                  % (board, seed, target))
        lo, hi = bisect_native_flip(sid, board, seed, sf, lo=bisect_lo, hi=bisect_hi,
                                    target=target)
        damages = [lo, hi]
        if verbose:
            print("=== seuil encadre : Damage %d (natif -> 1191) / %d (natif -> normale) ==="
                  % (lo, hi))
    rows = {}
    for d in damages:
        rows[d] = measure(sid, d, board, seed, sf, verbose=verbose, target=target)
    base_c, normal_c = ported_bonus()
    return {"board": board, "seed": seed, "target": target, "damages": list(damages), "rows": rows,
            "ported_base": base_c, "ported_normal": normal_c, "state_file": str(sf)}


def dispose(res) -> None:
    """Dispose le DERNIER runner du probe (les builds anterieurs ont deja ete remplaces par le
    scope de CE state-file). Jamais les runners des autres."""
    sid = _resolve_session()
    rids = {r["runner"] for r in res["rows"].values()}
    for rid in sorted(rids):
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def verdicts(res) -> int:
    ds = res["damages"]
    lo_row, hi_row = res["rows"][ds[0]], res["rows"][ds[-1]]
    na = hi_row["normal"]
    ok = True
    print("\n=== VERDICTS ===")
    # V1 -- la fenetre existe : le natif joue la normale alors que son PROPRE scorer de paire
    # classe 1191 devant, d'un ecart strictement inferieur a 1.
    gap = hi_row["gap"]
    v1 = (hi_row["native"] == na and gap is not None and 0.0 < gap < 1.0)
    ok = ok and v1
    print("  V1 fenetre du `+1` a Damage=%d : natif=%s (normale=%d) et pair(1191)-pair(%d)=%s "
          "-> %s" % (ds[-1], hi_row["native"], na, na, _f(gap),
                     "DANS ]0,1[ -- seul le +1 explique le choix natif" if v1
                     else "HORS REGIME -- le montage ne conclut RIEN, re-calibrer avec --auto"))
    # V1b -- bras TEMOIN : sous le seuil, le natif prefere 1191 (le `+1` ne suffit plus).
    v1b = (lo_row["native"] == MARTIAL_INSPIRATION)
    ok = ok and v1b
    print("  V1b bras temoin a Damage=%d : natif=%s -> %s"
          % (ds[0], lo_row["native"],
             "1191, la bascule est bien encadree" if v1b else "PAS 1191 -- bras temoin invalide"))
    # V2 -- le moteur suit le natif dans les DEUX bras.
    bad = [d for d in ds if res["rows"][d]["engine"] != res["rows"][d]["native"]]
    ok = ok and not bad
    print("  V2 accord moteur<->natif : %d/%d bras%s"
          % (len(ds) - len(bad), len(ds),
             "" if not bad else " -- DIVERGE sur Damage=%s" % bad))
    # V3 -- MUTATION : sans le `+1`, le moteur bascule sur 1191 dans la fenetre.
    v3 = (hi_row["engine_zero_bonus"] == MARTIAL_INSPIRATION
          and hi_row["engine_zero_bonus"] != hi_row["native"])
    ok = ok and v3
    print("  V3 mutation (`calculate_custom_utility` force a 0.0) a Damage=%d : moteur=%s vs "
          "natif=%s -> %s" % (ds[-1], hi_row["engine_zero_bonus"], hi_row["native"],
                              "DIVERGE, le +1 est LOAD-BEARING et le montage le voit" if v3
                              else "aucune divergence -- le montage NE PROUVE RIEN"))
    # V4 -- curseur propre : `Damage` ne deplace QUE l'attaque normale.
    p_mi = {d: res["rows"][d]["pair_1191"] for d in ds}
    v4 = (len(set(v for v in p_mi.values() if v is not None)) == 1)
    ok = ok and v4
    print("  V4 curseur propre : pair(1191) = %s -> %s"
          % ({d: _f(v) for d, v in p_mi.items()},
             "INVARIANT en Damage" if v4 else "VARIE -- le curseur touche AUSSI 1191, confond"))
    # V5 -- les deux termes portes, tels qu'ils sont dans le code.
    v5 = (res["ported_base"] == 0.0 and res["ported_normal"] == 1.0)
    ok = ok and v5
    print("  V5 termes portes : base=%r normale=%r -> %s"
          % (res["ported_base"], res["ported_normal"],
             "0.0 / 1.0 = mirror du natif" if v5 else "NE MIRRORENT PLUS le natif"))
    print("\n%s" % ("PROBE OK -- le `+1` de l'attaque normale est necessaire, mesure, et garde"
                    if ok else "PROBE KO -- voir les lignes ci-dessus"))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--target", default=TARGET, help="visualId de la cible (axe de generalisation)")
    ap.add_argument("--auto", action="store_true",
                    help="re-bisecte le seuil de bascule natif au lieu de lire D_BELOW/D_WINDOW")
    ap.add_argument("--damages", default=None, help="deux Damage explicites 'lo,hi'")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    damages = [int(x) for x in a.damages.split(",")] if a.damages else [D_BELOW, D_WINDOW]
    res = None
    try:
        res = scenario(board=a.board, seed=a.seed, damages=damages, auto=a.auto,
                       target=a.target)
        return verdicts(res)
    finally:
        if res is not None and not a.keep:
            dispose(res)
            print("(runners du probe disposes)")


if __name__ == "__main__":
    sys.exit(main())
