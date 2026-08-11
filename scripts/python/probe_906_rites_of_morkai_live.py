"""Probe #906 -- confrontation LIVE du port de `1211 RitesOfMorkai` (`spaceWolfPriest` << Baldr >>).

Ce que ce probe MESURE, volet par volet, en confrontant le PORT au CAST NATIF sur le MEME etat :

  V1  ZONE INSPIREE -- quelles unites recoivent `EffectType.RitesOfMorkai` (0x5de = 1502) ?
      Le natif cible `Cache(Owner + UnitsWithoutTrait(SurroundingFriends(Owner, range, unique, 3),
      0x5 = Mechanical, 3))`. Le montage place autour de Baldr un allie MECANIQUE (`admecMarshall`,
      traits `[Hero, Mechanical]`) : s'il est inspire, le filtre de trait est mort.
  V2  SOUS-ENSEMBLE FINAL VENGEANCE -- quelles unites recoivent `RitesOfMorkai_ExtraDamage`
      (0x5f9 = 1529) ? Le natif cible `Filter(<la MEME zone>, HasTrait(ActiveTarget, 0x3f6 =
      FinalJustice) | HasEffect(ActiveTarget, 0x5ae = FinalVengeance_UnitEffect, onlyActive: 0,
      Both))`. Le montage place `astraCreed` (traits `[Hero]`, donc SANS FinalJustice) a cote de
      `spaceWulfen` (`[Hero, FinalJustice, Unstoppable]`) : si les deux recoivent 1529, le `Filter`
      est mort ; si aucun ne le recoit, c'est la POSE qui l'est.
  V3  ATTAQUE NORMALE DE SUIVI -- l'audit classe 1211 en `EFFECT/BUFF` et ne voit donc PAS le
      troisieme volet. Le natif termine par `If(AmountIsGreaterThanZero(<cibles>),
      UseNormalAttack(Owner, SortUnitsByDamageUtility(...)))`. Le montage amene un ennemi au
      contact : le natif doit le FRAPPER dans le meme `applyAction`.

CE QUE LE TEMOIN DISCRIMINE (et ce qu'il ne discrimine pas) -- lire avant de croire un vert :

  * il DISCRIMINE les trois volets ci-dessus **parce que le roster est choisi pour cela** : quatre
    allies de traits DIFFERENTS (FinalJustice+non-mecanique / FinalJustice+non-mecanique / ni l'un
    ni l'autre / MECANIQUE) -> quatre verdicts attendus DISTINCTS (1502+1529 / 1502+1529 / 1502
    seul / rien). Un port qui poserait tout sur tout le monde, ou rien du tout, ROUGIT.
  * il NE discrimine PAS le rayon : `RitesOfMorkai.constants.range` vaut **1**, donc
    `SurroundingFriends(range=1)` et un `AdjacentFriends` seraient indistinguables ici. Un port qui
    lirait la mauvaise constante passerait tant que les allies sont au contact -- c'est pourquoi le
    bras `--far` ECARTE un allie a 2 hexes : il doit alors N'ETRE PAS inspire.
  * il NE discrimine PAS l'ORDRE des trois volets (buff, buff, attaque) : les deux poses sont
    deterministes et la comparaison porte sur l'etat FINAL.
  * il NE discrimine PAS le `unitSelectionType = 0 = Any` du `SortUnitsByDamageUtility` : les deux
    selecteurs sources portent deja leurs filtres, donc `Any` et `OnlyAliveAndTargetable` rendent
    le meme ensemble sur un plateau sans unite intargetable. Reste un fait LU au desassemblage.

Usage (depuis scripts/python, session Frida DEJA warmee -- ce probe ne (re)injecte JAMAIS) :

    python probe_906_rites_of_morkai_live.py [--board MC1_67] [--seed 777] [--far] [--keep]

Sortie ASCII only (cp1252). Le runner est dispose en fin de course sauf `--keep`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import catalog_inject as CI                                    # noqa: E402
from rl_collect_batch import _rpc, _resolve_session            # noqa: E402
from engine.entities.pathfinding.board import Board            # noqa: E402
from engine.entities.effect_type import EffectType             # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType   # noqa: E402
from engine.runner.snapshot import load_state                  # noqa: E402
from engine.runner.prng import IntBasedMersenneTwister         # noqa: E402
from engine.runner.components import UnitComponent, PositionComponent   # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES    # noqa: E402

RITES = int(ActiveAbilityType.RitesOfMorkai)                   # 1211
EFF_INSPIRED = int(EffectType.RitesOfMorkai)                   # 0x5de = 1502
EFF_EXTRA = int(EffectType.RitesOfMorkai_ExtraDamage)          # 0x5f9 = 1529
# Baldr EN TETE (c'est le caster). Les trois suivants sont choisis pour DISCRIMINER, cf. l'en-tete :
#   spaceWulfen   [Hero, FinalJustice, Unstoppable]  -> 1502 + 1529
#   astraCreed    [Hero]                             -> 1502 SEUL
#   admecMarshall [Hero, Mechanical]                 -> NI l'un NI l'autre
P_UNITS = "spaceWolfPriest,spaceWulfen,astraCreed,admecMarshall"
A_UNITS = "orksNob,orksWarboss"
LOGS = HERE.parents[1] / "logs"


# --------------------------------------------------------------------------- RPC helpers

def decision(sid, rid, include_inactive=False):
    return (_rpc(sid, "decisionView",
                 [{"runnerId": rid, "maxRank": 2, "allAbilities": True,
                   "includeInactive": bool(include_inactive)}], timeout=300).get("result") or {})


def apply_action(sid, rid, action):
    return (_rpc(sid, "applyAction", [{"runnerId": rid, "action": action}],
                 timeout=180).get("result") or {})


def movable(sid, rid):
    return (_rpc(sid, "aiMovableTiles", [{"runnerId": rid}], timeout=60).get("result") or {})


def units_by_id(view):
    return {u.get("id"): u for u in (view.get("units") or [])}


def gc_traits(visual_id):
    """Traits gameconfig d'un `visualId` -- pour DIRE ce que le placement exerce, pas pour decider."""
    import gameconfig as GC
    return ((GC.unit(visual_id) or {}).get("traits") or []) if visual_id else []


def carriers(view, effect_type):
    """Ids des unites qui PORTENT `effect_type` dans la vue (canal `decisionView.units[].effects`)."""
    return sorted(u.get("id") for u in (view.get("units") or [])
                  if any(e.get("effectType") == effect_type for e in (u.get("effects") or [])))


# --------------------------------------------------------------------------- board

def bfs_dist(board: Board, src: tuple, dst: tuple) -> int:
    a, b = board.id_at(*src), board.id_at(*dst)
    if a is None or b is None:
        return 10 ** 6
    seen, q = {a: 0}, deque([a])
    while q:
        t = q.popleft()
        if t == b:
            return seen[t]
        for n in board.neighbours(t):
            if n not in seen:
                seen[n] = seen[t] + 1
                q.append(n)
    return 10 ** 6


def pos_of(view, uid):
    p = units_by_id(view).get(uid, {}).get("pos") or {}
    return (p.get("col"), p.get("row"))


# --------------------------------------------------------------------------- montage

def build(seed, board_id, state_file, seed_bc, p_units, a_units, hp_target):
    # ⚠ `--hp-target` gonfle les PV des a-units, et c'est LOAD-BEARING pour le volet V3 : au premier
    # jet la cible mourait (10040 PV pour 12063 de degat), donc le natif et le port rendaient tous
    # deux `hp = 0` -- un accord SATURE, ou un port qui infligerait 11000 aurait passe. Avec des PV
    # tres au-dessus du coup, la comparaison porte sur le MONTANT et non sur la seule mort.
    cmd = [sys.executable, "rl_duel.py", "build",
           "--seed", str(seed), "--board", board_id, "--seed-bc", str(seed_bc),
           "--p-units", p_units, "--a-units", a_units, "--hp-target", str(hp_target),
           "--state-file", str(state_file), "--no-ai"]
    r = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        raise RuntimeError("rl_duel build KO")
    st = json.loads(Path(state_file).read_text(encoding="utf-8"))
    return int(st["runnerId"])


def gather(sid, rid, board, anchor_id, movers, target_dist, max_rounds=12):
    """Rapproche `movers` de l'unite `anchor_id` jusqu'a `dist <= target_dist[uid]`.

    ⚠ On DEPLACE les unites -- on ne se plaint jamais de la geometrie de spawn. Chaque unite a sa
    distance CIBLE : c'est ce qui permet au bras `--far` de garder un allie a 2 hexes, hors du
    `SurroundingFriends(range = 1)`."""
    for rnd in range(max_rounds):
        view = decision(sid, rid)
        ub = units_by_id(view)
        anchor = pos_of(view, anchor_id)
        reste = [u for u in movers
                 if ub.get(u, {}).get("alive")
                 and bfs_dist(board, pos_of(view, u), anchor) > target_dist[u]]
        if not reste:
            return rnd
        for mu in (movable(sid, rid).get("units") or []):
            uid = mu.get("unitId")
            if uid not in reste:
                continue
            tiles = [(t["col"], t["row"]) for t in (mu.get("tiles") or [])
                     if t.get("col") is not None]
            if not tiles:
                continue
            # on VISE la distance cible, pas le minimum : un allie `--far` doit s'arreter a 2.
            want = target_dist[uid]
            best = min(tiles, key=lambda t: (abs(bfs_dist(board, t, anchor) - want),
                                             bfs_dist(board, t, anchor)))
            apply_action(sid, rid, {"kind": "move", "unitId": uid,
                                    "to": {"col": best[0], "row": best[1]}})
        apply_action(sid, rid, {"kind": "endturn"})
    return -1


def capture(sid, rid):
    bg = _rpc(sid, "boardGraph", [{"runnerId": rid}], 60).get("result") or {}
    board = Board(bg["tiles"], adjacency="evenq")
    dv = decision(sid, rid, include_inactive=True)
    ob = _rpc(sid, "observeBattle", [{"runnerId": rid}], 60).get("result") or {}
    snap = _rpc(sid, "combatSnapshot", [{"runnerId": rid}], 60).get("result") or {}
    return board, dv, ob, snap


# --------------------------------------------------------------------------- face PORT

def run_port(board, dv, ob, snap, caster_id, seed):
    """Execute le PORT de 1211 sur l'etat capture AVANT le cast natif, et rend son diagnostic."""
    st = load_state(dv, ob, snap, board=board)
    st.rng = IntBasedMersenneTwister(seed)
    klass = ABILITY_CLASSES.get(RITES)
    if klass is None:
        raise RuntimeError("1211 absente d'ABILITY_CLASSES -- le port n'est pas cable")
    diag = klass().execute_behaviour(st, caster_id, caster_id)
    porte_1502 = sorted(int(p["target"]) for p in (diag.get("inspired") or [])
                        if p.get("target") is not None)
    porte_1529 = sorted(int(p["target"]) for p in (diag.get("extra_damage") or [])
                        if p.get("target") is not None)
    atk = diag.get("normal_attack") or {}
    return diag, porte_1502, porte_1529, atk


# --------------------------------------------------------------------------- main

def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--p-units", default=P_UNITS,
                    help="spaceWolfPriest doit rester EN TETE (c'est Baldr, le caster)")
    ap.add_argument("--a-units", default=A_UNITS)
    ap.add_argument("--far", action="store_true",
                    help="garde le 3e allie a 2 hexes : il doit alors N'ETRE PAS inspire "
                         "(discrimine `SurroundingFriends(range = constants.range = 1)`)")
    ap.add_argument("--allies-first", action="store_true",
                    help="place les allies AVANT l'ennemi -> le MECANIQUE arrive au contact et son "
                         "exclusion prouve le filtre de trait ; en contrepartie l'ennemi reste "
                         "enferme a 2 hexes et le volet V3 n'est pas exerce (cf. l'en-tete)")
    ap.add_argument("--hp-target", type=int, default=60000,
                    help="PV des a-units -- assez HAUT pour que le coup ne SATURE pas (cf. build)")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)

    LOGS.mkdir(parents=True, exist_ok=True)
    seed_bc = LOGS / "seed_bc_906_swp.json"
    state_file = LOGS / "probe_906_rites_state.json"
    p, units, abils = CI.write_augmented_seed_bc(seed_bc, ["spaceWolfPriest"])
    print("[inject] seed BC augmente (HORS data/) -> %s" % p)
    print("[inject] units=%s abils=%s" % (units, abils))

    sid = _resolve_session()
    rid = build(a.seed, a.board, state_file, seed_bc, a.p_units, a.a_units, a.hp_target)
    print("[build] sid=%d runnerId=%d board=%s seed=%d hp_target=%d"
          % (sid, rid, a.board, a.seed, a.hp_target))
    print("[build] p_units=%s | a_units=%s" % (a.p_units, a.a_units))
    rc = 0
    try:
        board, dv0, _, _ = capture(sid, rid)
        view = decision(sid, rid)
        # `ctrl` bascule a chaque `endturn` : on fige les deux camps ICI et on n'y revient plus.
        mine = [u["id"] for u in (view.get("units") or []) if u.get("ctrl")]
        foes = [u["id"] for u in (view.get("units") or []) if not u.get("ctrl")]
        vis = {u["id"]: u.get("visualId") for u in (view.get("units") or [])}
        baldr = mine[0]
        print("[roster] mine=%s foes=%s" % ([(u, vis.get(u)) for u in mine],
                                            [(u, vis.get(u)) for u in foes]))
        print("[roster] Baldr=u%d (%s)" % (baldr, vis.get(baldr)))

        # DEPLACER -- on ne se plaint jamais de la geometrie de spawn. ⚠ **L'ORDRE COMPTE, ET AUCUN
        # DES DEUX N'EXERCE TOUT** : Baldr n'a que SIX voisins. Allies d'abord, ils les occupent et
        # l'ennemi reste ENFERME a 2 hexes -> V3 non exerce (mesure du 1er jet ; le temoin de
        # non-degenerescence l'a refuse, il ne s'est pas tu). Ennemi d'abord, c'est le 4e allie
        # (`admecMarshall`, le MECANIQUE) qui reste a 2 -> son exclusion de la zone ne prouve plus
        # rien du filtre de trait, seulement de la portee. D'ou **deux bras**, et un rapport de
        # DISCRIMINATION qui dit lequel est exerce. Le tour bascule a chaque `endturn`, donc
        # `gather` avance quel que soit le camp mobile.
        want = {u: 1 for u in mine[1:]}
        if a.far and len(mine) >= 4:
            want[mine[3]] = 2
        wf = {foes[0]: 1}
        if a.allies_first:
            n = gather(sid, rid, board, baldr, list(want), want)
            print("[gather] allies places apres %d rounds (cibles=%s)" % (n, want))
            n2 = gather(sid, rid, board, baldr, list(wf), wf)
            print("[gather] ennemi u%d amene au contact apres %d rounds" % (foes[0], n2))
        else:
            n2 = gather(sid, rid, board, baldr, list(wf), wf)
            print("[gather] ennemi u%d amene au contact apres %d rounds" % (foes[0], n2))
            n = gather(sid, rid, board, baldr, list(want), want)
            print("[gather] allies places apres %d rounds (cibles=%s)" % (n, want))

        # rendre le tour a mon camp
        for _ in range(4):
            if units_by_id(decision(sid, rid)).get(baldr, {}).get("ctrl"):
                break
            apply_action(sid, rid, {"kind": "endturn"})

        board, dv, ob, snap = capture(sid, rid)
        geo = {u: bfs_dist(board, pos_of(dv, u), pos_of(dv, baldr)) for u in mine + foes}
        print("[geo] distances a Baldr : %s" % {("u%d/%s" % (u, vis.get(u))): d
                                                for u, d in geo.items()})
        hp0 = {u.get("id"): u.get("hp") for u in (dv.get("units") or [])}

        # --- face PORT (sur l'etat AVANT) ---------------------------------------------
        diag, p1502, p1529, patk = run_port(board, dv, ob, snap, baldr, a.seed)
        print("[PORT] 1502 sur %s" % [("u%d/%s" % (u, vis.get(u))) for u in p1502])
        print("[PORT] 1529 sur %s" % [("u%d/%s" % (u, vis.get(u))) for u in p1529])
        print("[PORT] attaque normale : %s" % json.dumps(
            {"target": patk.get("target"), "skipped": patk.get("skipped"),
             "total": (patk.get("attack") or {}).get("total")}))

        # --- face NATIVE ---------------------------------------------------------------
        before_1502 = carriers(dv, EFF_INSPIRED)
        before_1529 = carriers(dv, EFF_EXTRA)
        print("[NATIF] AVANT cast : 1502=%s 1529=%s" % (before_1502, before_1529))
        res = apply_action(sid, rid, {"kind": "ability", "casterId": baldr,
                                      "targetId": baldr, "abilityType": RITES})
        print("[NATIF] applyAction ok=%s err=%s" % (res.get("ok"), res.get("error")))
        after = decision(sid, rid, include_inactive=True)
        n1502 = carriers(after, EFF_INSPIRED)
        n1529 = carriers(after, EFF_EXTRA)
        hp1 = {u.get("id"): u.get("hp") for u in (after.get("units") or [])}
        damaged = {u: (hp0.get(u), hp1.get(u)) for u in hp0
                   if hp0.get(u) is not None and hp1.get(u) is not None and hp1[u] < hp0[u]}
        print("[NATIF] 1502 sur %s" % [("u%d/%s" % (u, vis.get(u))) for u in n1502])
        print("[NATIF] 1529 sur %s" % [("u%d/%s" % (u, vis.get(u))) for u in n1529])
        print("[NATIF] unites qui ont PERDU des PV : %s"
              % {("u%d/%s" % (u, vis.get(u))): v for u, v in damaged.items()})

        # --- CONFRONTATION --------------------------------------------------------------
        print("")
        print("=== CONFRONTATION ===")
        ok = True
        for label, port_set, nat_set in (("V1 zone 1502", p1502, n1502),
                                         ("V2 filtre 1529", p1529, n1529)):
            same = sorted(port_set) == sorted(nat_set)
            ok &= same
            print("  %-16s port=%-22s natif=%-22s %s"
                  % (label, port_set, nat_set, "OK" if same else "DIVERGE"))
        # V3 : l'attaque normale a-t-elle eu lieu, sur QUI, et pour COMBIEN ?
        # ⚠ L'IDENTITE DE LA CIBLE NE SUFFIT PAS : un port qui infligerait 100 au lieu de 12063
        # rendrait le MEME ensemble « unites blessees ». On confronte donc l'ETAT DE PV, en
        # projetant le total du port sur les PV de depart (mirror du clamp a 0 du natif).
        nat_target = sorted(damaged) if damaged else []
        port_target = [patk.get("target")] if patk.get("target") is not None else []
        same3 = sorted(port_target) == nat_target
        hp_verdict = "(pas de cible)"
        if port_target and nat_target and port_target[0] in hp0:
            tid = port_target[0]
            total = (patk.get("attack") or {}).get("total")
            attendu = None if total is None else max(0, int(hp0[tid]) - int(total))
            obtenu = hp1.get(tid)
            same_hp = attendu is not None and obtenu is not None and attendu == obtenu
            same3 &= bool(same_hp)
            hp_verdict = ("hp: %s - %s -> port=%s natif=%s %s"
                          % (hp0[tid], total, attendu, obtenu, "OK" if same_hp else "DIVERGE"))
        ok &= same3
        print("  %-16s port=%-22s natif=%-22s %s"
              % ("V3 attaque", port_target, nat_target, "OK" if same3 else "DIVERGE"))
        print("  %-16s %s" % ("", hp_verdict))
        # TEMOIN DE NON-DEGENERESCENCE : un accord sur DEUX ensembles vides ne prouve rien.
        # ⚠ On SEPARE deux natures que le premier jet confondait : une DIVERGENCE (le port et le
        # natif ne disent pas la meme chose -> rouge de FIDELITE) et un VOLET NON EXERCE (le
        # montage n'a pas arme ce volet -> rouge de MONTAGE, et seulement si ce bras devait
        # l'armer). Les melanger faisait lire « ROUGE » sur un bras `--allies-first` parfaitement
        # concordant, dont on SAIT qu'il enferme l'ennemi.
        montage_ko = False
        if not n1502:
            print("  [TEMOIN] REGIME DEGENERE : le natif n'a pose AUCUN 1502 -- l'accord ne vaut rien")
            montage_ko = True
        if not n1529 and not a.far:
            print("  [TEMOIN] REGIME DEGENERE : aucun 1529 natif -- le volet V2 n'est pas exerce")
            montage_ko = True
        if not damaged:
            if a.allies_first:
                print("  [TEMOIN] volet V3 NON EXERCE, et c'est ATTENDU de ce bras : les allies "
                      "places d'abord occupent les voisins de Baldr et enferment l'ennemi. "
                      "Jouer le bras par defaut pour V3.")
            else:
                print("  [TEMOIN] MONTAGE KO : aucune unite blessee -- le volet V3 devait etre "
                      "exerce par ce bras")
                montage_ko = True
        if montage_ko:
            ok = False
        # DISCRIMINATION : les deux ensembles doivent DIFFERER, sinon le filtre n'est pas teste.
        if n1502 and n1529 and sorted(n1502) == sorted(n1529):
            print("  [TEMOIN] NON DISCRIMINANT : 1502 et 1529 portent sur le MEME ensemble --"
                  " le `Filter` Final Vengeance n'est pas exerce par ce roster")
        # CE QUE CE RUN EXERCE VRAIMENT, allie par allie -- une exclusion ne prouve le FILTRE DE
        # TRAIT que si l'unite etait A PORTEE. Sans ce bloc, un `admecMarshall` reste a 2 hexes
        # ferait lire son absence de la zone comme une preuve du filtre `Mechanical` alors qu'elle
        # ne prouve que la portee. C'est exactement l'ecart entre les deux bras.
        print("  --- ce que ce placement EXERCE ---")
        for u in mine[1:]:
            d = geo.get(u)
            tr = (gc_traits(vis.get(u)) or [])
            dedans = u in n1502
            if d is not None and d <= 1:
                quoi = ("EXERCE le filtre de trait (a portee, %s)"
                        % ("EXCLU" if not dedans else "inclus"))
            else:
                quoi = "n'exerce QUE la portee (hors range, exclusion non concluante sur le trait)"
            print("      u%-3d %-16s dist=%-3s traits=%-42s %s"
                  % (u, vis.get(u), d, ",".join(tr), quoi))
        print("")
        print("[906] %s" % ("OK -- les trois volets concordent" if ok else "ROUGE"))
        rc = 0 if ok else 1
    finally:
        if not a.keep:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=60)
            print("[dispose] runner %d dispose" % rid)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
