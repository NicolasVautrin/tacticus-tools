#!/usr/bin/env python
"""Probe #351 -- SorcerousFacade (1100) : le natif emet DEUX events de degat, le port en emettait UN.

CE QUE LE DECOMPILE DIT (`rnca9r7q6c`, lu VERBATIM)
---------------------------------------------------
`IdunBattle.AI.Playbook.Loki.SorcerousFacadePlaybook$$MakeDamagePredictions` (la fin du corps) :

    sel = TargetsSelector.SelectFirst(SorcerousFacadeAbility.GetTarget(ability),
                                      entities{Caster, CasterTile = casterPosition.MainTile,
                                               CasterTiles = casterPosition});
    if (sel == null) return <liste VIDE statique>;
    list = TExtensions.ToList([ new ProbableDamageEvent(sel, battleQuery.<slot 0x22>(caster, sel,
                                                                                     casterPosition)) ]);
    list.AddRange( ComparablePlaybook<T>.GenerateMultiHitAttackPredictions(
                       caster, casterPosition, sel,
                       targets = DSLSelectors.Get(sel),                    // mono-cible
                       damage  = DSLFormulas.Half(DSLFormulas.Sum(Get(GetVariableForLevel(0xc = minDmg)),
                                                                  Get(GetVariableForLevel(0xd = maxDmg))), 0),
                       hits    = GetNumberConstant(0x2f = nrOfHits),
                       profil  = <vide>) );
    return list;

TROIS faits que ce corps etablit, et qu'aucun nom ne laissait deviner :

  1. **`AddRange` AJOUTE, il ne SUBSTITUE pas.** La liste rendue a DEUX elements.
  2. **Les deux events portent sur `sel`**, le MEME ennemi -- pas sur deux cibles differentes. Ce
     n'est donc pas un volet AoE : c'est deux predictions sur une seule cible.
  3. **La cible PASSEE a `MakeDamagePredictions` (l'ALLIE Psyker) n'entre pas dans la prediction** :
     le playbook la remplace par `sel`. Le probe le MESURE en interrogeant l'oracle sur les deux
     cibles et en exigeant la MEME reponse.

LE RESIDU QUE CE PROBE FERME (#351)
-----------------------------------
Le port avait DEUX implementations du MEME artefact natif -- un FORK :

  * `engine.playbook.loki_custom.SorcerousFacadePlaybook.make_damage_predictions` reconstruisait les
    deux events A LA MAIN (juste, mais duplique) ;
  * `engine.playbook.prediction.abilities.make_damage_predictions` SUBSTITUAIT l'attaque normale au
    batch (ancien `_PREDICT_VIA_NORMAL_ATTACK`) et rendait donc UN SEUL event.

Le second est le chemin qu'interroge le harnais de mesure de #344/#350 : d'ou son bras MUET sur 1100
(l'attaque normale ne lit aucune moyenne minDmg/maxDmg -> les quatre variantes d'arrondi y
coincidaient -> bras NON DISCRIMINANT -> ECHEC). La reparation supprime le fork : le chemin generique
mirror l'AJOUT (`_PREPEND_NORMAL_ATTACK_EVENT` + `_PLAYBOOK_PROFILE_OVERRIDE[1100]`), et le playbook
ne garde que la seule chose que le natif y ecrit de special -- la SUBSTITUTION DE CIBLE.

CE QUE CE PROBE MESURE
----------------------
  A. compte + SEQUENCE des events, natif vs les DEUX chemins du port (ils doivent coincider tous les
     trois -- c'est la preuve que le fork est ferme, pas seulement qu'un des deux est juste) ;
  B. l'oracle interroge sur l'ALLIE et sur l'ENNEMI rend la MEME sequence (la cible passee est
     ignoree par la prediction) ;
  C. A/B CAUSAL, le seul bras qui prouve que le fix est NECESSAIRE : `_PREPEND_NORMAL_ATTACK_EVENT`
     vide -> le port retombe a UN event et l'attaque normale disparait. Un accord obtenu sans ce
     bras ne distinguerait pas « porte » de « deja bon par ailleurs » ;
  D. A/B CAUSAL sur le profil : `_PLAYBOOK_PROFILE_OVERRIDE[1100]` retire -> le 2e event applique le
     percage de `Psychic` au lieu du profil VIDE, et les bornes CHANGENT sur cible blindee.

DEUX BRAS, parce qu'aucun ne peut porter les deux A/B
------------------------------------------------------
  * `noarmor` (`--armor-target 0`) : sans l'etage armure, la base du 2e event traverse jusqu'aux
    bornes observees -- c'est la que l'ARRONDI et le TERME EN TETE se voient. Le percage, lui, n'y
    a aucun objet : retirer le profil n'y change RIEN, et le probe l'EXIGE dans ce sens.
  * `armor` (armure native) : `Psychic` perce 100, le profil VIDE perce 0. Sur cible blindee, les
    deux se separent violemment (plancher a 1 point/coup contre la valeur pleine) -- c'est la que
    le PROFIL se voit. En revanche le plancher ecrase la base, donc l'arrondi n'y discrimine plus.

ASCII only (cp1252). Usage (depuis scripts/python) :
    python probe_351_facade_event_count.py
    python probe_351_facade_event_count.py --level 8 --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                          # noqa: E402

FACADE = 1100
FACADE_NAME = "SorcerousFacade"
BOARD = "MC1_67"
CENTER = (3, 4)
CASTER = "thousTzaangor"        # Yazaghor -- HERO, porteur de 1100, DANS le pool spawnable
ALLY = "thousSorcerer"          # allie Psyker : la cible LEGALE de 1100 (masque TargetIsFriendly)
VICTIM = "ultraTitus"           # l'ennemi que `sel` doit designer (le plus proche)
FILLER_A = "ultraCalgar"        # le SECOND ennemi -- relegue LOIN (cf. `_place`)
FAR_TILE = (6, 0)
# Niveau 8 : minDmg 25 + maxDmg 50 = 75 = 3 mod 4 -- la classe de parite ou l'arrondi de la moyenne
# (demi-vers-le-pair, registre (a4) de #350) se SEPARE de la troncature.
LEVEL = 8
MULT = 100


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def _build(state_file: Path, seed: int, level: int, mult: int, armor_target) -> int:
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", BOARD, "--rank", "17",
           "--p-units", "%s,%s" % (CASTER, ALLY),
           "--a-units", "%s,%s" % (VICTIM, FILLER_A),
           "--unit-stat", "%s:ActiveAbilityLevel=%d,AbilityVariablesMultiplierPercentage=%d"
                          % (CASTER, level, mult),
           "--crit", "0,0", "--block-target", "0,0", "--no-ai"]
    if armor_target is not None:
        cmd += ["--armor-target", str(int(armor_target))]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise RuntimeError("build KO : %s" % ((proc.stderr or proc.stdout or "")[-900:]))
    return int(json.loads(state_file.read_text())["runnerId"])


def _view(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)


def _move(sid, rid, uid, col, row):
    return _r(sid, "applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(uid), "to": {"col": int(col), "row": int(row)}}}, 90)


def _place(sid, rid, ids, center):
    """GEOMETRIE DRIVEE (runner.md sec.4) : caster au centre, VICTIM et ALLY colles (ring 1), le
    SECOND ennemi RELEGUE loin. Trois contraintes, toutes exigees par le natif :

    * `sel` doit exister -- c'est aussi la condition de
      `...SorcerousFacadeAbility$$GetDynamicInvalidTargetReason` (le caster doit pouvoir porter son
      attaque normale) ;
    * `sel` doit etre SANS AMBIGUITE. Avec les DEUX ennemis a distance EGALE, le `First(1)` derriere
      le `SortByDistance` ne tranche plus que par l'ORDRE D'ENUMERATION -- residu NOMME de
      `case-287` (le natif enumere `GetPossibleTargetsForOptions` -> `GetUnitsInRange`, le port
      enumere `state.entities`). MESURE en montant les deux ennemis sur le meme ring : le natif
      designe `ultraCalgar`, le port `ultraTitus`. Ce probe ne mesure PAS ce residu-la : il ecarte
      le second ennemi pour que la distance seule decide ;
    * LE CASTER BOUGE EN DERNIER : chaque `applyAction move` fait avancer le tour, et une fois le
      caster passe le natif ne publie plus d'`attackPlans` pour lui -- or c'est de la que le port
      tire `ValidNormalAttackTargets` (`ctx.plans`). Avec l'ordre inverse, `sel` est nul et le
      montage ne mesure RIEN (mesure : `ctx.plans[caster].evals` vide, alors que les positions,
      elles, etaient bien celles voulues). Meme ordre que `probe_27_4e`.

    Les placements sont VERIFIES : un `move` refuse ne leve rien, et le bras degenere alors en
    silence en une geometrie qu'on n'a pas choisie."""
    from engine.entities.pathfinding.board import Board
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    ccol, crow = center
    ring = [board.coord(t) for t in board.neighbours(board.id_at(ccol, crow))]
    if len(ring) < 2:
        raise RuntimeError("centre (%d,%d) trop pauvre en voisins (%d)" % (ccol, crow, len(ring)))
    want = [(ids[VICTIM], ring[0]), (ids[ALLY], ring[1]), (ids[FILLER_A], FAR_TILE),
            (ids[CASTER], (ccol, crow))]
    for uid, (col, row) in want:
        _move(sid, rid, uid, col, row)

    dv = _view(sid, rid)
    got = {int(u["id"]): ((u.get("pos") or {}).get("col"), (u.get("pos") or {}).get("row"))
           for u in (dv.get("units") or []) if u.get("id") is not None}
    bad = [(uid, tuple(p), got.get(uid)) for uid, p in want if got.get(uid) != tuple(p)]
    if bad:
        raise RuntimeError("placement REFUSE -- montage invalide, pas de mesure : %s"
                           % ["u%s voulu=%s obtenu=%s" % b for b in bad])


def _seq_native(sid, rid, cid, tid, main_tid):
    """(sequence des events portes par `main_tid`, compte TOTAL). L'oracle `aiPlaybookPredict`
    invoque DIRECTEMENT `<X>Playbook$$MakeDamagePredictions` : c'est le natif lui-meme, pas le
    preview `GetAllPredictions`."""
    r = _r(sid, "aiPlaybookPredict", {"runnerId": rid, "unitId": int(cid),
                                      "targetId": int(tid), "abilityType": FACADE}, 120)
    evs = (r or {}).get("events") or []
    seq = tuple((e.get("healthDmgMin"), e.get("healthDmgMax"), e.get("appliedHits"))
                for e in evs if e.get("targetId") == int(main_tid))
    return seq, len(evs), [e.get("targetId") for e in evs]


def _seq_port(events, main_tid):
    return tuple((e.prediction.accurate_health_damage.min,
                  e.prediction.accurate_health_damage.max,
                  e.prediction.applied_hits)
                 for e in events if e.target == int(main_tid))


def _ctx(sid, rid, cid):
    from engine import weights as W
    from engine.playbook import scene as _scene
    from engine.ai import context as AICTX
    rpc = lambda m, b, t=60: _r(sid, m, b, t)                       # noqa: E731
    dv = _view(sid, rid)
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 60)
    mov_by_unit = {u.get("unitId"): u for u in ((mov or {}).get("units") or [])}
    return AICTX.build(rpc, rid, dv, mov_by_unit, int(cid), W.load(),
                       _scene.build_predictor(rpc, rid))


def measure(sid, rid, level, armor_target) -> dict:
    import engine.playbook as PB
    from engine.playbook.prediction import abilities as PA

    dv = _view(sid, rid)
    ids = {}
    for v in (CASTER, ALLY, VICTIM, FILLER_A):
        u = next((x for x in (dv.get("units") or [])
                  if x.get("visualId") == v and x.get("alive")), None)
        if u is None:
            return {"error": "unite absente du build : %s" % v}
        ids[v] = int(u["id"])
    _place(sid, rid, ids, CENTER)
    cid, ally, foe = ids[CASTER], ids[ALLY], ids[VICTIM]

    ctx = _ctx(sid, rid, cid)
    pb = PB.REGISTRY.get(FACADE)
    sel = pb._get_target(ctx, ctx.origin)
    if sel is None:
        return {"error": "`sel` est nul -- la regle dynamique de 1100 ne serait pas satisfaite"}

    # A. natif, interroge sur l'ALLIE (la cible LEGALE) et sur l'ENNEMI.
    nat_ally, n_ally, tids_ally = _seq_native(sid, rid, cid, ally, sel)
    nat_foe, n_foe, tids_foe = _seq_native(sid, rid, cid, foe, sel)

    # B. les DEUX chemins du port.
    ev_pb = pb.make_damage_predictions(ctx, ctx.origin, ally, FACADE) or []
    seq_pb = _seq_port(ev_pb, sel)
    ev_gen = PA.make_damage_predictions(ctx.scene, cid, sel, FACADE, FACADE_NAME,
                                        attack_pos=ctx.origin) or []
    seq_gen = _seq_port(ev_gen, sel)

    # C. A/B causal : sans le terme EN TETE, le port retombe a un seul event.
    saved = PA._PREPEND_NORMAL_ATTACK_EVENT
    PA._PREPEND_NORMAL_ATTACK_EVENT = frozenset()
    try:
        seq_noprepend = _seq_port(pb.make_damage_predictions(ctx, ctx.origin, ally, FACADE) or [],
                                  sel)
    finally:
        PA._PREPEND_NORMAL_ATTACK_EVENT = saved

    # D. A/B causal : sans l'override de profil, le 2e event percerait l'armure (profil Psychic).
    saved_prof = PA._PLAYBOOK_PROFILE_OVERRIDE.pop(FACADE, None)
    try:
        seq_noprofile = _seq_port(pb.make_damage_predictions(ctx, ctx.origin, ally, FACADE) or [],
                                  sel)
    finally:
        if saved_prof is not None:
            PA._PLAYBOOK_PROFILE_OVERRIDE[FACADE] = saved_prof

    return {"level": level, "armor_target": armor_target, "sel": sel, "ally": ally, "foe": foe,
            "caster": cid, "playbook": type(pb).__name__,
            "native_from_ally": nat_ally, "native_from_foe": nat_foe,
            "n_events_native_ally": n_ally, "n_events_native_foe": n_foe,
            "native_targets_ally": tids_ally, "native_targets_foe": tids_foe,
            "port_playbook": seq_pb, "port_generic": seq_gen,
            "port_without_prepend": seq_noprepend, "port_without_profile": seq_noprofile}


def _verdicts(arm: dict) -> list:
    """Les invariants d'UN bras. Rend la liste des echecs (vide = conforme).

    Les deux A/B ne sont pas exiges dans le meme bras, et c'est une propriete du MONTAGE, pas une
    concession : sans armure, le percage n'a aucun effet, donc le bras `noarmor` ne peut pas
    discriminer le profil ; avec armure, le plancher a 1 point/coup ecrase la base, donc le bras
    `armor` ne peut pas discriminer l'arrondi. Chaque bras porte l'A/B qu'il est capable d'exercer,
    et l'autre y est explicitement NON EXIGE."""
    f = []
    if arm.get("error"):
        return [arm["error"]]
    nat = arm["native_from_ally"]
    if len(nat) != 2:
        f.append("le natif rend %d event(s) sur `sel`, attendu 2 (`list = [normale]` + `AddRange`) "
                 ": %r" % (len(nat), nat))
    if arm["native_from_foe"] != nat:
        f.append("la cible PASSEE change la prediction native (allie %r vs ennemi %r) -- le "
                 "playbook est cense la remplacer par `sel`"
                 % (nat, arm["native_from_foe"]))
    if arm["port_playbook"] != nat:
        f.append("PLAYBOOK du port %r != natif %r" % (arm["port_playbook"], nat))
    if arm["port_generic"] != nat:
        f.append("chemin GENERIQUE du port %r != natif %r (le fork de port n'est pas ferme)"
                 % (arm["port_generic"], nat))
    # A/B causal 1 : le terme EN TETE. Exigible dans les DEUX bras (l'attaque normale est toujours
    # d'un ordre de grandeur au-dessus du batch, meme sur cible blindee).
    if arm["port_without_prepend"] == nat:
        f.append("sans `_PREPEND_NORMAL_ATTACK_EVENT` le port rend ENCORE %r -- le terme en tete "
                 "n'est pas ce qui produit l'accord" % (arm["port_without_prepend"],))
    if len(arm["port_without_prepend"]) != 1:
        f.append("sans le terme en tete, le port devrait rendre le SEUL batch (1 event), il rend %r"
                 % (arm["port_without_prepend"],))
    # A/B causal 2 : le profil VIDE -- exigible SEULEMENT sur cible BLINDEE (`Psychic` perce 100 ;
    # `armor_target = 0` retire l'etage armure, donc le percage y est sans objet).
    if arm.get("armor_target") == 0:
        if arm["port_without_profile"] != nat:
            f.append("bras SANS armure : retirer le profil ne devrait RIEN changer (percage sans "
                     "objet), or le port passe de %r a %r"
                     % (nat, arm["port_without_profile"]))
    elif arm["port_without_profile"] == nat:
        f.append("sans `_PLAYBOOK_PROFILE_OVERRIDE[1100]` le port rend ENCORE %r -- le profil VIDE "
                 "du 2e batch n'est pas exerce par ce montage" % (arm["port_without_profile"],))
    return f


def _print_arm(arm: dict, label: str) -> None:
    print("\n=== bras %s === niveau %s, armure cible %s"
          % (label, arm.get("level"), arm.get("armor_target")))
    if arm.get("error"):
        print("  ERREUR : %s" % arm["error"])
        return
    print("  `sel` (ennemi le plus proche) = %s | allie = %s | ennemi = %s"
          % (arm["sel"], arm["ally"], arm["foe"]))
    print("  natif  (cible = ALLIE)  : %-40s  (events=%d, cibles=%s)"
          % (str(arm["native_from_ally"]), arm["n_events_native_ally"],
             arm["native_targets_ally"]))
    print("  natif  (cible = ENNEMI) : %-40s  (events=%d, cibles=%s)"
          % (str(arm["native_from_foe"]), arm["n_events_native_foe"], arm["native_targets_foe"]))
    print("  port   PLAYBOOK         : %-40s  %s"
          % (str(arm["port_playbook"]),
             "== NATIF" if arm["port_playbook"] == arm["native_from_ally"] else "!= NATIF"))
    print("  port   GENERIQUE        : %-40s  %s"
          % (str(arm["port_generic"]),
             "== NATIF" if arm["port_generic"] == arm["native_from_ally"] else "!= NATIF"))
    print("  A/B sans terme en tete  : %-40s  (doit DIVERGER)"
          % str(arm["port_without_prepend"]))
    print("  A/B sans profil VIDE    : %-40s  (%s)"
          % (str(arm["port_without_profile"]),
             "non exige ici : sans armure le percage est sans objet"
             if arm.get("armor_target") == 0 else "doit DIVERGER"))


def _one(sid, seed: int, sf: Path, level: int, armor_target) -> dict:
    rid = None
    try:
        rid = _build(sf, seed, level, MULT, armor_target)
        return measure(sid, rid, level, armor_target)
    finally:
        if rid is not None:
            _r(sid, "disposeRunner", {"runnerId": rid}, 30)


def run(seed: int = 35101, state_file=None, level: int = LEVEL, verbose: bool = True) -> dict:
    sid = _resolve_session()
    sf = Path(state_file) if state_file else (PYDIR.parents[1] / "logs" / "p351.json")
    sf.parent.mkdir(parents=True, exist_ok=True)

    arms = {"noarmor": _one(sid, seed, sf, level, 0),
            "armor": _one(sid, seed + 1, sf, level, None)}
    for a in arms.values():
        a["fails"] = _verdicts(a)
    ok = all(not a["fails"] for a in arms.values())

    if verbose:
        print("[351] montage : %s / SorcerousFacade (1100) -> allie %s, ennemi %s (colle), "
              "second ennemi %s relegue en %s, board %s, centre %s, niveau %d"
              % (CASTER, ALLY, VICTIM, FILLER_A, FAR_TILE, BOARD, tuple(CENTER), level))
        for label in ("noarmor", "armor"):
            _print_arm(arms[label], label)
        print("\n=== VERDICT === -> %s" % ("OK" if ok else "ECHEC"))
        for label, a in arms.items():
            for x in a["fails"]:
                print("  FAIL[%s]: %s" % (label, x))
    return {"ok": ok, "arms": arms, "level": level}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=35101)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--level", type=int, default=LEVEL)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    out = run(seed=a.seed, state_file=a.state_file, level=a.level)
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
