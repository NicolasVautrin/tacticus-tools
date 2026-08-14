"""#1050 -- confrontation LIVE d'`OptimizedGait` (passif 0x4b5 = 1205 d'`admecRuststalker`).

Monte la geometrie que les DEUX triggers exigent -- un allie MECHANICAL qui attaque un ennemi
ADJACENT au porteur -- puis confronte, sur le MEME etat, ce que le NATIF execute et ce que le PORT
execute.

    python probe_1050_optimized_gait.py --state-file <absolu>.json [--seed 777] [--board MC1_67]

Ce que le probe MESURE (et non ce qu'il suppose) :

  1. le NATIF declenche-t-il l'attaque reactive ? -> le sous-arbre `[Ability_Power e=<porteur>
     << OptimizedGait >>]` des events du cast, son nombre de coups, son `DamageProfileType`, son
     `Attack_Weapon_IsMelee` et son `Passive_Ability_Type` ;
  2. le PORT l'inscrit-il et la declenche-t-il sur le MEME vecteur `On(9 = Attack)`, avec les MEMES
     parametres ?
  3. le DISCRIMINANT d'`isMelee` : l'attaque DECLENCHANTE est RANGED (`necroWarden`, portee 3) et
     l'attaque REACTIVE est MELEE -- parce que le natif lit `IBattleQuery.<slot 7> AreUnitsInMelee(
     owner, target)`, la GEOMETRIE porteur<->cible, et NON la nature de l'arme du declencheur. Un
     port qui rabattrait `is_melee` sur `ev.ranged` rendrait `IsMelee=0` : ce bras-la separe les
     deux lectures.

⚠ CE PROBE N'EST PAS UN TEST (il MESURE). Le cliquet est
`tests/engine/runner/test_1050_optimized_gait_offline.py`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import probe_247_splash_targeting as P247                            # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402
from engine.dsl.event_trigger_type import EventTriggerType           # noqa: E402
from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402
from engine.runner.operations.triggers.base import TriggerEvent      # noqa: E402
from engine.runner.operations.triggers.dispatch.core import (        # noqa: E402
    collect_triggered_abilities, evaluate_trigger_operation)

PORTEUR = "admecRuststalker"          # Exitor-Rho -- LINEUP, dans le pool
ALLIE_MECH = "necroWarden"            # Makhotep -- `Mechanical`, arme RANGED (portee 3)
ENNEMI = "orksRuntherd"


def _rl(*args, state_file=None):
    cmd = [sys.executable, "rl_duel.py"] + list(args)
    if state_file:
        cmd += ["--state-file", str(state_file)]
    r = subprocess.run(cmd, capture_output=True, text=True,
                       cwd=str(Path(__file__).resolve().parent))
    return r.stdout + r.stderr


def _pos(dv, uid):
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            p = u.get("pos") or {}
            if p.get("col") is None:
                return None
            return (int(p["col"]), int(p["row"]))
    return None


def _ids(dv):
    """`{visualId: entityId}` du `decisionView`."""
    out = {}
    for u in (dv.get("units") or []):
        vid = u.get("visualId") or u.get("unitId")
        if vid and vid not in out:
            out[vid] = int(u.get("id"))
    return out


def _seed_rng(state, rng_state) -> None:
    """Cale `state.rng` sur l'etat MT CAPTURE (`dumpRng`).

    ⚠ SANS ce calage, `AttackDamageOperation.execute_ability_attack` **SKIPPE le degat et rend
    `None`** (garde defensive documentee). Le port rend alors le BON trigger, la BONNE cible... et
    `attack = null` : une attaque qui n'attaque pas, sans erreur. Mesure de ce probe au 1er jet."""
    from engine.runner.prng import IntBasedMersenneTwister
    if not (isinstance(rng_state, dict) and rng_state.get("mt")):
        return
    rng = IntBasedMersenneTwister()
    rng.mt = list(rng_state["mt"])
    rng.mti = rng_state["mti"]
    state.rng = rng


def _capture(sid, rid):
    dv = P247._dv(sid, rid)
    ob = P247._r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = P247._r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = P247._r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    _seed_rng(st, P247._r(sid, "dumpRng", {"runnerId": rid}, 30))
    return dv, st


def _damage_profile_id():
    """L'ORDINAL du profil que le port lit pour ce passif -- a confronter au `DamageProfileType`
    des events natifs. `constants.damageProfile` est un NOM (`Energy`) ; le natif publie l'ordinal
    de `IdunBattle.Entities.Enum.DamageProfileType`."""
    from engine.runner.operations.triggers.loki.optimized_gait import _damage_profile
    nom = _damage_profile()
    try:
        from engine.entities.damage_profile_type import DamageProfileType
        return "%s=%d" % (nom, int(DamageProfileType[nom]))
    except Exception:
        return nom


def _events_optimized_gait(evts, porteur_id):
    """Les coups du sous-arbre `[Ability_Power e=<porteur> << OptimizedGait >>]`, aplatis.

    On ne cherche PAS le libellé : on filtre les `UnitDamaged` dont l'`Attacker_Id` est le PORTEUR
    -- le libellé de groupe est une commodité d'affichage, l'attribution est la mesure."""
    out = []

    def walk(node):
        if isinstance(node, list):
            for x in node:
                walk(x)
            return
        if not isinstance(node, dict):
            return
        tags = node.get("tags") or {}
        if node.get("type") == "UnitDamaged" or "Amount" in tags:
            if int(tags.get("Attacker_Id", -1)) == int(porteur_id):
                out.append({"amount": int(tags.get("Amount", 0)),
                            "profile": tags.get("DamageProfileType"),
                            "passive": tags.get("Passive_Ability_Type"),
                            "crit": tags.get("Attack_DidCrit")})
        for k in ("children", "events", "nodes"):
            if node.get(k):
                walk(node[k])

    walk(evts)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--keep", action="store_true", help="ne pas disposer le runner en sortie")
    a = ap.parse_args()

    print("[1050] montage : porteur=%s allie=%s ennemi=%s board=%s seed=%s"
          % (PORTEUR, ALLIE_MECH, ENNEMI, a.board, a.seed))
    out = _rl("build", "--seed", a.seed, "--board", a.board,
              "--p-units", "%s,%s" % (PORTEUR, ALLIE_MECH), "--a-units", ENNEMI, "--no-ai",
              state_file=a.state_file)
    rid = None
    for ln in out.splitlines():
        if "runnerId=" in ln:
            rid = int(ln.split("runnerId=")[1].split()[0])
            break
    if rid is None:
        print(out[-2000:])
        print("[1050] FAIL : build sans runnerId")
        return 2
    sid = _resolve_session()
    print("[1050] runner=%s session=%s" % (rid, sid))

    dv, _ = _capture(sid, rid)
    ids = _ids(dv)
    porteur, allie, ennemi = ids.get(PORTEUR), ids.get(ALLIE_MECH), ids.get(ENNEMI)
    print("[1050] entites : porteur=%s allie=%s ennemi=%s" % (porteur, allie, ennemi))
    if None in (porteur, allie, ennemi):
        print("[1050] FAIL : roster incomplet %s" % ids)
        return 2

    # --- GEOMETRIE : on DRIVE les positions, on ne les subit pas ------------------------------
    # Cible : le porteur ADJACENT a l'ennemi (le gate `IsAdjacent(Owner, Target)`), l'allie a
    # portee de tir de l'ennemi mais PAS adjacent -- c'est ce qui rend le discriminant `isMelee`
    # separant (declencheur RANGED, reaction MELEE).
    ep = _pos(dv, ennemi)
    print("[1050] ennemi @%s" % (ep,))
    voisins = []
    st_board = None
    for step in range(6):
        dv, st = _capture(sid, rid)
        st_board = st.board
        pp, ap_, ep = _pos(dv, porteur), _pos(dv, allie), _pos(dv, ennemi)
        et = st_board.id_at(ep[0], ep[1])
        voisins = [st_board.coord(t) for t in st_board.neighbours(et)]
        adjacent = pp in voisins
        a_dist_ok = ap_ not in voisins
        print("[1050] tour %d : porteur@%s allie@%s ennemi@%s voisins=%s adjacent=%s"
              % (step, pp, ap_, ep, voisins, adjacent))
        if adjacent and a_dist_ok:
            break
        # rapprocher : le porteur vise une tuile VOISINE de l'ennemi, l'allie reste en retrait
        cible = None
        for v in voisins:
            if v != ap_:
                cible = v
                break
        if cible is not None:
            _rl("act", "move", "--unit", str(porteur), "--to", "%d,%d" % cible,
                state_file=a.state_file)
        _rl("act", "move", "--unit", str(allie), "--to",
            "%d,%d" % (max(0, ep[0] - 2), max(0, ep[1] - 2)), state_file=a.state_file)
        _rl("act", "finish", "--unit", str(porteur), state_file=a.state_file)
        _rl("act", "endturn", state_file=a.state_file)
        _rl("act", "endturn", state_file=a.state_file)

    dv, st = _capture(sid, rid)
    pp, ap_, ep = _pos(dv, porteur), _pos(dv, allie), _pos(dv, ennemi)
    et = st.board.id_at(ep[0], ep[1])
    voisins = [st.board.coord(t) for t in st.board.neighbours(et)]
    if pp not in voisins:
        print("[1050] NON CONFRONTE : le porteur n'a pas pu se rendre adjacent (porteur@%s "
              "voisins=%s)" % (pp, voisins))
        if not a.keep:
            _rl("dispose", state_file=a.state_file)
        return 3

    # --- VOLET PORT : inscription + vecteur `On(9 = Attack)` -----------------------------------
    inscrites = sorted({type(x).__name__ for x in collect_triggered_abilities(st)
                        if int(getattr(x, "owner_id", -1) or -1) == int(porteur)
                        and type(x).__name__.startswith("OptimizedGait")})
    print("[1050] PORT inscription : %s" % (inscrites or "AUCUNE"))
    ev = TriggerEvent(int(EventTriggerType.Attack), int(allie), int(ennemi),
                      ranged=True, profile=None)
    res_port = [r for r in (evaluate_trigger_operation(st, ev) or [])
                if r.get("ability") == "OptimizedGait"]
    print("[1050] PORT On(9) -> %s" % json.dumps(res_port, default=str)[:1400])

    # --- VOLET NATIF : la MEME attaque, jouee pour de vrai --------------------------------------
    out = _rl("act", "ability", "--caster", str(allie), "--target", str(ennemi),
              "--ability", "69", state_file=a.state_file)
    lignes = out.splitlines()
    natif = [ln.strip() for ln in lignes
             if ("Attacker_Id=%d" % porteur) in ln or "OptimizedGait" in ln]
    print("[1050] NATIF (lignes du porteur) :")
    for ln in natif:
        print("   " + ln[:200])

    # --- CONFRONTATION --------------------------------------------------------------------------
    coups_natifs = [ln for ln in natif if "UnitDamaged" in ln]
    # ⚠ ` Amount=` avec l'espace : la ligne porte AUSSI `Shields_RemainingAmount=0`, et un split sur
    # `Amount=` nu prend CELUI-LA (mesure : montants `[0, 0]` au 1er jet, un zero parfaitement
    # lisible et entierement faux).
    montants_natifs = [int(ln.split(" Amount=")[1].split()[0])
                       for ln in coups_natifs if " Amount=" in ln]
    profils = sorted({ln.split("DamageProfileType=")[1].split()[0]
                      for ln in coups_natifs if "DamageProfileType=" in ln})
    passifs = sorted({ln.split("Passive_Ability_Type=")[1].split()[0]
                      for ln in coups_natifs if "Passive_Ability_Type=" in ln})
    # `Attack_Weapon_IsMelee` du sous-arbre du PORTEUR : c'est le tag `InformWeapon` que la reaction
    # pose, et il vit dans la ligne `Info` QUI SUIT `[Ability_Power e=<porteur>]` -- elle ne porte ni
    # `Attacker_Id` ni le nom de l'ability, donc on la prend par sa POSITION dans la cascade.
    melee = []
    for i, ln in enumerate(lignes):
        if "Ability_Power e=%d" % porteur in ln:
            for suite in lignes[i + 1:i + 3]:
                if "Attack_Weapon_IsMelee=" in suite:
                    melee.append(suite.split("Attack_Weapon_IsMelee=")[1].split()[0])
                    break
    melee_declencheur = []
    for i, ln in enumerate(lignes):
        if "Ability_Power e=%d" % allie in ln:
            for suite in lignes[i + 1:i + 3]:
                if "Attack_Weapon_IsMelee=" in suite:
                    melee_declencheur.append(suite.split("Attack_Weapon_IsMelee=")[1].split()[0])
                    break
    port_hits, port_total = [], None
    for r in res_port:
        atk = r.get("attack") or {}
        # `per_hit_health` = la part SANTE par coup (ce que `UnitDamaged.Amount` porte cote natif).
        port_hits = [int(x) for x in (atk.get("per_hit_health") or atk.get("per_hit") or [])]
        port_total = atk.get("total")
    print("[1050] BILAN")
    print("   NATIF  : coups=%d montants=%s profils=%s passif=%s isMelee(reaction)=%s "
          "isMelee(declencheur)=%s"
          % (len(coups_natifs), montants_natifs, profils, passifs, melee, melee_declencheur))
    print("   PORT   : declenche=%s coups=%d montants=%s total=%s is_melee=%s use_special=%s "
          "profil=%s"
          % (bool(res_port), len(port_hits), port_hits, port_total,
             [r.get("is_melee") for r in res_port], [r.get("use_special") for r in res_port],
             _damage_profile_id()))
    print("   ⚠ les MONTANTS ne sont PAS comparables bit-a-bit sur ce montage : le port rejoue le "
          "trigger SEUL sur l'etat d'AVANT, le natif le joue APRES les coups d'arme du declencheur "
          "-- deux positions differentes dans le MEME flux MT. Ce qui est confronte ici : le "
          "DECLENCHEMENT, le NOMBRE de coups, le PROFIL, la SOURCE (1205) et `isMelee`.")
    ok = bool(res_port) and len(coups_natifs) > 0
    ok = ok and all(bool(r.get("is_melee")) for r in res_port) and melee == ["1"]
    ok = ok and len(port_hits) == len(coups_natifs)
    # le DISCRIMINANT : le declencheur est RANGED, la reaction est MELEE -- deux lectures
    # differentes, et c'est ce qui interdit de rabattre `is_melee` sur `ev.ranged`.
    print("   DISCRIMINANT isMelee : declencheur=%s reaction=%s -> %s"
          % (melee_declencheur, melee,
             "SEPARANT" if melee_declencheur == ["0"] and melee == ["1"] else "NON separant"))
    print("[1050] %s" % ("OK" if ok else "DIVERGENCE"))
    if not a.keep:
        _rl("dispose", state_file=a.state_file)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
