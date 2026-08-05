"""#448-r3 -- le PAS DE MOUVEMENT est ATOMIQUE, et c'est pour ca que le marqueur transitoire
`1036 TeleportStrike_Moving` n'est observable QUE DE L'INTERIEUR.

POURQUOI CE PROBE EXISTE. La garde `test_448_r2_teleporting_in_live.py` mesurait l'etat
INTERMEDIAIRE du pas en le DECOUPANT en deux appels :

    MoveUnitOperation(uid, dest).execute(st, EventBus())   # cense s'arreter avant le vecteur
    ...    <- on lisait 1036 ICI
    after_move_triggers(st, uid)                           # cense poser la suite

Ce decoupage etait le contrat du port au 2026-08-01. `9767a8e4` (#448-r1-r1-r2-r1, 2026-08-04) a
REPLIE le vecteur after-move DANS `MoveUnitOperation.execute` -- donc le premier appel joue
DESORMAIS le pas ENTIER, 1036 est pose PUIS retire avant qu'on regarde, et la lecture d'apres ne
voit plus que les passives d'atterrissage (`1107 PathOfCommand_ExtraCrit`, `1112
PathOfCommand_ExtraDmg`). La garde rougissait donc en accusant le PORT d'avoir perdu T4, alors que
T4 fire normalement. Pire : le second appel REJOUAIT le vecteur after-move, deja joue.

RE -- LE REPLI EST LE MIRROR, ET C'EST MESURE SUR LE BINAIRE (build `rnca9r7q6c`) :

    IdunBattle.Operations.MoveUnitOperation$$EvaluateAfterMoveTriggers
        -> DEUX call-sites dans tout le binaire, les DEUX dans
           `IdunBattle.Operations.MoveUnitOperation$$Execute`
           (`MoveUnitOperation$$Execute+0x9de` et `MoveUnitOperation$$Execute+0x1111`).
    IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers
        -> ZERO call-site (corps INLINE dans le meme `Execute`).

=> le natif publie `On(0x1f = PreUnitMove)` et `On(0x04 = UnitAfterMove)` DANS LE MEME `Execute`.
Un observateur EXTERIEUR a `Execute` -- c'est-a-dire tout etat natif RECHARGE apres un
`applyAction` -- ne peut STRUCTURELLEMENT jamais voir 1036 : il naquit et mourut a l'interieur.
C'est la raison pour laquelle ce probe ne demande PAS au natif un etat porteur de 1036 : le
reclamer serait exiger un temoin que le natif ne peut pas produire.

    ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal   -- QUATRE `Triggered()`, verbatim :
      T1 On(0x04) & OwnerIsActor & <vslot 0x738>                 -> RemoveEffect(self)
      T2 On(0x2a) & OwnerIsActor & <vslot 0x738>                 -> RemoveEffect(self)
      T3 On(0x28) & OwnerIsActor & HasTile(Owner) & <vslot 0x738>-> RemoveEffect(self)
      T4 On(0x1f) & OwnerIsActor & <vslot 0x738> & <vslot 0x748> -> `GetAddMovingEffectBehaviour`
    ATeleportingEffect$$GetAddMovingEffectBehaviour : `GetMovingEffectType()` (vslot 0x758) ;
      `HasValue == 0` -> `DSLBehaviors$$Nothing()` ; sinon `DSLBehaviors$$AddEffect(<type>,
      GetAbilityState(), targets, Nullable<int>(1))`.
    TeleportStrike_TeleportingInEffect$$GetMovingEffectType : `local_res18[0] = 0x40c` puis le ctor
      du `Nullable` -> **1036**, `HasValue` VRAI.
    TeleportMovingEffect$$CreateHandleTriggerAbilitiesInternal : UN SEUL `Triggered(On(0x04) &
      OwnerIsActor -> GetRemoveEffectBehaviour())`.

CE QUE LE PROBE MESURE (le pas joue UNE SEULE FOIS, comme au natif) :

  E-ATOMIC  `after_move_triggers` est appele EXACTEMENT UNE FOIS, et par `MoveUnitOperation.execute`
            lui-meme -- c'est le fait porte que le decoupage d'avant ignorait.
  E-MOVING  l'etat INTERMEDIAIRE, capte PAR INSTRUMENTATION a l'entree du vecteur after-move (le
            seul point d'observation qui existe encore) : 1035 ET 1036 y sont VIVANTS ensemble.
  E-END     apres le pas : ni 1035 ni 1036, et les passives DEFEREES posees (1107/1112).
  E-NATIF   l'etat natif RECHARGE apres le MEME pas joue LIVE : accord TERME A TERME avec le port,
            et -- c'est le point -- il ne porte pas 1036 NON PLUS. L'absence de 1036 des DEUX cotes
            n'est pas un accord vide : elle est CONTRAINTE par les deux call-sites ci-dessus.

CONTRE-EPREUVE (`--mutate`) : on RETIRE T4 du registre d'effet et on rejoue E-MOVING. Sans T4,
1036 n'est jamais pose -- E-MOVING doit ROUGIR. Une garde qu'on ne sait pas faire echouer ne garde
rien.

Usage (depuis scripts/python) :
    python probe_448_r3_move_step_atomicity.py
    python probe_448_r3_move_step_atomicity.py --mutate      # contre-epreuve
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as L  # noqa: E402

LOGS = ROOT / "logs" / "probe448r3"
STATE = LOGS / "state_448_r3_move_step_atomicity.json"   # SORTIE -> logs/ (#349), JAMAIS data/

TELEPORTING_IN = 1035                 # EffectType.TeleportStrike_TeleportingIn (0x40b)
MOVING = 1036                         # EffectType.TeleportStrike_Moving        (0x40c)

# `eldarAutarch` = deep-strike (trait TeleportStrike) ET porteur de l'aura `PathOfCommand` : c'est
# ce couple qui rend l'atterrissage NUMERIQUEMENT observable sur une TIERCE unite.
P_UNITS = "eldarAutarch,adeptCanoness,spaceRockfist"
A_UNITS = "adeptRetributor,blackAbaddon,necroWarden"
COUPLES = [("MC1_67", "777"), ("C3_26", "31337")]


# --------------------------------------------------------------------------- transport

def rpc(method, body=None, timeout=120):
    return L._rpc(L._resolve_session(), method, [body if body is not None else {}],
                  timeout=timeout).get("result")


def _duel(args):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


def build(seed_value: str, board_id: str) -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        STATE.unlink()
    p = _duel(["build", "--seed", seed_value, "--board", board_id, "--rank", "17", "--no-ai",
               "--p-units", P_UNITS, "--a-units", A_UNITS, "--state-file", str(STATE)])
    if not STATE.exists():
        raise SystemExit("build KO (MONTAGE, pas une mesure): "
                         + (p.stderr or p.stdout or "")[-800:])
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def capture(rid) -> dict:
    return {"dec": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 90),
            "ob": rpc("observeBattle", {"runnerId": rid}, 40),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
            "tm": rpc("tileMeta", {"runnerId": rid}, 60),
            "bg": rpc("boardGraph", {"runnerId": rid}, 60)}


def offline_state(cap):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"]), board


def find_vid(st, sub):
    from engine.runner.components import UnitComponent
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and sub.lower() in str(uc.visual_id).lower():
            return int(uid)
    return None


def live_effects(st, uid) -> list:
    """Les `effect_type` NON consommes, tries -- la MEME forme des deux cotes."""
    return sorted(int(x.effect_type) for x in (st.effects.by_unit.get(int(uid)) or [])
                  if not x.consumed)


# --------------------------------------------------------------------------- la mesure

def play_step_instrumented(st, uid: int, dest) -> dict:
    """Joue le pas UNE SEULE FOIS (comme `MoveUnitOperation$$Execute`) et capte l'etat
    INTERMEDIAIRE par INSTRUMENTATION du vecteur after-move.

    C'est le SEUL point d'observation qui subsiste depuis que le vecteur est replie dans
    l'Operation : a l'entree d'`after_move_triggers`, `On(0x1f = PreUnitMove)` a deja pose 1036 et
    aucun `On(0x04 = UnitAfterMove)` n'a encore retire quoi que ce soit. Le spy DELEGUE au vrai
    vecteur -- il observe, il ne remplace pas : l'etat final reste celui du pas nominal.

    `movement.py` importe `after_move_triggers` DANS le corps d'`execute` (`from .triggers import
    after_move_triggers`), donc l'attribut est resolu A L'APPEL : patcher le module le capte."""
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    import engine.runner.operations.triggers as TRG

    seen: list = []
    real = TRG.after_move_triggers

    def spy(state, unit_id, *a, **kw):
        seen.append({"unit": int(unit_id), "effects": live_effects(state, int(uid))})
        return real(state, unit_id, *a, **kw)

    TRG.after_move_triggers = spy
    try:
        MoveUnitOperation(int(uid), tuple(dest)).execute(st, EventBus())
    finally:
        TRG.after_move_triggers = real
    return {"calls": seen, "end": live_effects(st, int(uid))}


def cascade_effect_spans(evs) -> dict:
    """Le TEMOIN NATIF. Rend `{nom_effet: {"add": [idx], "rem": [idx]}}` en lisant la cascade
    d'events du `applyAction` (`actions[i].events[]` -- PAR ACTION, jamais a la racine).

    Le `source` d'un groupe `Effect_Refresh` EST le nom de l'effet ; les steps qu'il contient disent
    ce qui lui arrive. Les ordinaux sont resolus par `stream_events` depuis
    `data/symbols/<build>/frida/enums.tsv` et JAMAIS ecrits en dur : la renumerotation
    `gqfc5mff6c -> rnca9r7q6c` avait deja inverse add/remove en silence."""
    import stream_events as SE
    s_add = {SE.step_id("ReceiveEffect"), SE.step_id("ActivateEffect")}
    s_rem = {SE.step_id("LoseEffect"), SE.step_id("DeactivateEffect")}
    g_refresh = SE.group_id("Effect_Refresh")
    out: dict = {}
    stack: list = []
    for i, ev in enumerate(evs):
        k = ev.get("kind")
        if k == "group":
            stack.append((ev.get("group"), ev.get("source")))
            continue
        if k == "finish":
            if stack:
                stack.pop()
            continue
        src = next((s for (g, s) in reversed(stack) if g == g_refresh), None)
        if src is None:
            continue
        d = out.setdefault(src, {"add": [], "rem": []})
        if ev.get("step") in s_add:
            d["add"].append(i)
        if ev.get("step") in s_rem:
            d["rem"].append(i)
    return out


def cascade_change_position(evs) -> int | None:
    """Index du `ChangePosition` du mover -- la BORNE qui separe « avant le pas » d'« apres »."""
    import stream_events as SE
    sid = SE.step_id("ChangePosition")
    return next((i for i, ev in enumerate(evs)
                 if ev.get("kind") == "action" and ev.get("step") == sid), None)


def choose_dest(st, board, uid, ally, rid):
    """Destination CHOISIE, pas subie : une tuile **adjacente a l'allie** ET dans le pool LEGAL du
    natif (`aiMovableTiles`). Un `applyAction move` hors pool est un NO-OP SILENCIEUX (H55) -- sans
    ce controle un montage rate se lirait comme un desaccord de PORT."""
    from engine.runner.components import get_unit_feet
    apos = next(iter(get_unit_feet(st, ally)), None)
    mv = (rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}).get("units") or []
    legal = {(t.get("col"), t.get("row")) for u in mv if u.get("unitId") == uid
             for t in (u.get("tiles") or [])}
    return next((board.coord(t) for t in board.neighbours(board.id_at(apos[0], apos[1]))
                 if board.coord(t) in legal), None)


def run_couple(board_id, seed_value, mutate: bool, fails) -> None:
    print("=== couple board=%s seed=%s ===" % (board_id, seed_value))
    rid = build(seed_value, board_id)
    try:
        st, board = offline_state(capture(rid))
        autarch, ally = find_vid(st, "eldarAutarch"), find_vid(st, "adeptCanoness")
        if autarch is None or ally is None:
            raise SystemExit("MONTAGE : autarch/allie non deployes")
        if TELEPORTING_IN not in live_effects(st, autarch):
            raise SystemExit("MONTAGE : l'autarch n'arrive pas en teleport-in")
        dest = choose_dest(st, board, autarch, ally, rid)
        if dest is None:
            raise SystemExit("MONTAGE : aucune tuile LEGALE adjacente a l'allie")

        # ⚠ Le registre est un etat de MODULE, donc GLOBAL au processus : sans restauration, la
        # mutation du premier couple survit au second, qui rapporte alors « T4 introuvable » --
        # un faux constat qui fait douter d'une contre-epreuve pourtant saine (mesure).
        from engine.runner.operations.triggers.dispatch import registry as REG
        saved = list(REG.EFFECT_TRIGGERS[TELEPORTING_IN])
        try:
            if mutate:
                # CONTRE-EPREUVE : on retire T4 du registre d'effet. Sans lui, `On(0x1f)` ne pose
                # plus rien et 1036 doit disparaitre de l'etat intermediaire -> E-MOVING DOIT rougir.
                from engine.runner.operations.triggers.loki.teleporting_in import (
                    TeleportStrikeTeleportingInAddMovingOnPreMove as T4)
                REG.EFFECT_TRIGGERS[TELEPORTING_IN] = [c for c in saved if c is not T4]
                if len(REG.EFFECT_TRIGGERS[TELEPORTING_IN]) == len(saved):
                    fails.append("MUTATION INOPERANTE : T4 introuvable dans le registre -- la "
                                 "contre-epreuve ne discrimine rien")
                print("[MUTATE] T4 retire du registre (%d -> %d triggers)"
                      % (len(saved), len(REG.EFFECT_TRIGGERS[TELEPORTING_IN])))

            r = play_step_instrumented(st, autarch, dest)
        finally:
            REG.EFFECT_TRIGGERS[TELEPORTING_IN] = saved

        # --- E-ATOMIC
        print("[E-ATOMIC] after_move_triggers appele %d fois par execute()" % len(r["calls"]))
        if len(r["calls"]) != 1:
            fails.append("E-ATOMIC : le vecteur after-move a ete joue %d fois pour UN pas "
                         "(attendu 1, joue par MoveUnitOperation.execute)" % len(r["calls"]))

        # --- E-MOVING : l'etat INTERMEDIAIRE, capte de l'interieur.
        mid = r["calls"][0]["effects"] if r["calls"] else []
        print("[E-MOVING] port, a l'entree du vecteur after-move : %r" % (mid,))
        if MOVING not in mid:
            fails.append("E-MOVING : %d absent de l'etat intermediaire -- T4 n'a pas pose" % MOVING)
        if TELEPORTING_IN not in mid:
            fails.append("E-MOVING : %d deja retire dans l'etat intermediaire -- T1 fire trop tot"
                         % TELEPORTING_IN)

        # --- E-END
        print("[E-END] port, apres le pas : %r" % (r["end"],))
        if MOVING in r["end"]:
            fails.append("E-END : %d SURVIT au pas -- TeleportMovingEffect n'a pas retire" % MOVING)
        if TELEPORTING_IN in r["end"]:
            fails.append("E-END : %d SURVIT au pas -- T1 n'a pas retire" % TELEPORTING_IN)

        if mutate:
            return                      # l'etat port est volontairement FAUX : pas de confrontation

        # --- E-NATIF : le MEME pas, joue LIVE, puis etat RECHARGE.
        res = rpc("applyAction", {"runnerId": rid,
                                  "action": {"kind": "move", "unitId": autarch,
                                             "to": {"col": int(dest[0]), "row": int(dest[1])}}},
                  60) or {}
        if (res.get("actions") or [{}])[0].get("mutated") is not True:
            raise SystemExit("MONTAGE : le move live n'a RIEN mute : %r" % (res,))

        # --- E-CASCADE : LE TEMOIN NATIF NON-NUL. L'etat recharge ne peut pas porter 1036, mais la
        # cascade d'events emise PENDANT `Execute`, si -- et c'est la seule fenetre qui existe.
        evs = [e for a in (res.get("actions") or []) for e in (a.get("events") or [])]
        spans = cascade_effect_spans(evs)
        cp = cascade_change_position(evs)
        mv_span = spans.get("TeleportStrike_Moving")
        print("[E-CASCADE] natif, %d events ; groupes Effect_Refresh vus : %r"
              % (len(evs), sorted(spans)))
        if not mv_span:
            fails.append("E-CASCADE : le natif n'a PAS publie de groupe Effect_Refresh "
                         "<<TeleportStrike_Moving>> pendant le pas -- le temoin est VIDE, la "
                         "mesure ne fonde plus l'assertion du port")
        else:
            print("[E-CASCADE] TeleportStrike_Moving : add=%r rem=%r  (ChangePosition a %r)"
                  % (mv_span["add"], mv_span["rem"], cp))
            if not mv_span["add"]:
                fails.append("E-CASCADE : 1036 jamais ACTIVE cote natif")
            if not mv_span["rem"]:
                fails.append("E-CASCADE : 1036 ACTIVE mais jamais RETIRE cote natif -- il ne "
                             "serait pas transitoire")
            # L'ORDRE est le coeur du temoin : T4 pose AVANT le deplacement, `TeleportMovingEffect`
            # retire APRES. C'est ce qui distingue un marqueur transitoire d'un effet quelconque.
            if cp is not None and mv_span["add"] and mv_span["rem"]:
                if not (min(mv_span["add"]) < cp < max(mv_span["rem"])):
                    fails.append("E-CASCADE : 1036 n'ENCADRE pas le ChangePosition "
                                 "(add=%r cp=%d rem=%r)"
                                 % (mv_span["add"], cp, mv_span["rem"]))

        st2, _b2 = offline_state(capture(rid))
        nat = live_effects(st2, autarch)
        print("[E-NATIF] natif, apres le pas : %r" % (nat,))
        if nat != r["end"]:
            fails.append("E-NATIF : port=%r != natif=%r" % (r["end"], nat))
        # Le natif ne PEUT PAS porter 1036 dans un etat recharge (les deux call-sites d'
        # `EvaluateAfterMoveTriggers` sont dans `Execute`) : on l'assertionne pour que la
        # contrainte soit LUE, pas supposee.
        if MOVING in nat:
            fails.append("E-NATIF : le natif publie %d dans un etat RECHARGE -- la RE de "
                         "l'atomicite du pas est fausse" % MOVING)
    finally:
        _duel(["dispose", "--state-file", str(STATE)])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mutate", action="store_true",
                    help="contre-epreuve : retire T4 du registre, E-MOVING DOIT rougir")
    args = ap.parse_args()

    fails: list = []
    for board_id, seed_value in COUPLES:
        run_couple(board_id, seed_value, args.mutate, fails)

    print("")
    if args.mutate:
        # En mode mutation, l'ECHEC est le resultat ATTENDU.
        if not fails:
            print("[VERDICT] MUTATION NON DETECTEE -- la garde ne discrimine PAS. ROUGE.")
            return 1
        print("[VERDICT] mutation DETECTEE (%d constat(s)) -- la garde discrimine :" % len(fails))
        for f in fails:
            print("   - %s" % f)
        return 0
    if fails:
        print("[VERDICT] ROUGE (%d)" % len(fails))
        for f in fails:
            print("   - %s" % f)
        return 1
    print("[VERDICT] VERT -- le pas est atomique, 1036 vit et meurt dedans, accord avec le natif.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
