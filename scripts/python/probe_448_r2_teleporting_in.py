"""#448-r2 -- la famille `IdunBattle.Entities.Effects.Loki.ATeleportingEffect` : INVENTAIRE des
QUATRE derivees + CONFRONTATION live/port de la tranche 1 (`1035 TeleportStrike_TeleportingIn`).

RE (decompile = verite ; detail complet dans
`docs/rl/case-448-r2-ateleporting-effect-family.md` et dans
`engine/runner/operations/triggers/loki/teleporting_in.py`) :

    ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal = QUATRE Triggered()
      T1  On(0x04 UnitAfterMove)    & OwnerIsActor                  & <vslot 0x738> -> RemoveEffect(self)
      T2  On(0x2a PreUnitAbility)   & OwnerIsActor                  & <vslot 0x738> -> RemoveEffect(self)
      T3  On(0x28 UnitFinishedTurn) & OwnerIsActor & HasTile(Owner) & <vslot 0x738> -> RemoveEffect(self)
      T4  On(0x1f PreUnitMove)      & OwnerIsActor & <vslot 0x738>  & <vslot 0x748>
              -> GetMovingEffectType().HasValue ? AddEffect(<ce type>, ..., Owner, turns: 1) : Nothing()
    TeleportMovingEffect$$CreateHandleTriggerAbilitiesInternal = UN Triggered()
          On(0x04 UnitAfterMove) & OwnerIsActor -> RemoveEffect(self)

CE QUE LE PROBE MESURE :

  etape 0  INVENTAIRE offline des QUATRE derivees : `EffectType`, ability SOURCE (avec son enum
           QUALIFIE), `GetMovingEffectType`, porteurs (`unit_map`) et etat du port
           (`EFFECT_CLASSES` / `EFFECT_TRIGGERS`). Aucune bataille montee.
  E1       Etat de depart LIVE : les porteurs `TeleportStrike` arrivent avec 1035 (`remaining` 2 =
           `TurnsFromRounds(1)` a deux joueurs) et SANS leurs passives deferrees.
  CONFRONT-MOVE    T1 + T4 + TeleportMovingEffect. Meme etat de depart, le MEME pas rejoue OFFLINE
                   (voie complete `Runner.apply(MoveUnitMessage)`) puis LIVE ; etats finaux compares
                   TERME A TERME (effets du porteur, effets de l'allie, Attack de l'allie).
  CONFRONT-ABILITY T2. Un cast SANS deplacement prealable.
  CONFRONT-FINISH  T3. `FinishUnitTurn` sans avoir ni bouge ni caste.
  E-MOVING         Le 1036 transitoire : pose au `On(PreUnitMove)`, retire au `On(UnitAfterMove)` du
                   MEME pas -- des deux cotes (natif = cascade d'events, port = etat entre les deux
                   vecteurs).

DISCRIMINANT DE VERDICT : le port d'AVANT #448-r2 faisait atterrir les unites deep-strike dans
`EndTurnOperation` (boucle bespoke). Sur CONFRONT-MOVE il rendait donc, apres le pas, un porteur
encore NON-CIBLABLE et un allie SANS le `+Attack` de `PathOfCommand_ExtraDmg` -- un ecart NUMERIQUE
(400 au rank 17), pas un desaccord de forme.

Usage (depuis scripts/python) :
    python probe_448_r2_teleporting_in.py                 # inventaire + 2 couples live
    python probe_448_r2_teleporting_in.py --offline       # inventaire SEUL (aucun runner)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import rl_collect_batch as L  # noqa: E402

LOGS = ROOT / "logs" / "probe448r2"
STATE = LOGS / "state_448_r2_teleporting_in.json"     # SORTIE -> logs/ (#349), JAMAIS data/

TELEPORTING_IN = 1035                 # EffectType.TeleportStrike_TeleportingIn (0x40b)
MOVING = 1036                         # EffectType.TeleportStrike_Moving        (0x40c)
PATH_OF_COMMAND = "PathOfCommand_ExtraDmg"

# `eldarAutarch` = deep-strike (trait TeleportStrike) ET porteur de l'aura `PathOfCommand` : c'est
# ce couple qui rend l'atterrissage NUMERIQUEMENT observable sur une TIERCE unite.
P_UNITS = "eldarAutarch,adeptCanoness,astraBullgryn"
A_UNITS = "adeptRetributor,blackAbaddon,necroWarden"
COUPLES = [("MC1_67", "777"), ("C3_26", "31337")]

#: La famille, telle que `data/symbols/<build>/frida/classes.tsv` la donne (parent
#: `ATeleportingEffect`), avec le litteral `mov edx, imm32` de chaque `$$.ctor` et la surcharge d'
#: `IdunBattle.Core.AbilityOrEffect$$op_Implicit` qu'il appelle -- DEUX surcharges distinctes, d'ou
#: la qualification d'enum. `moving` = `GetMovingEffectType()` (vslot 0x758).
FAMILY = [
    # (classe, effectType, source (litteral, enum QUALIFIE), moving, surcharges vslot)
    ("TeleportStrike_TeleportingInEffect", 1035, 1037, "TriggeredAbilityType.TeleportStrike",
     1036, ()),
    ("StormboyzStrike_TeleportingInEffect", 1140, 1141, "TriggeredAbilityType.StormboyzStrike",
     None, ()),
    ("FearOfTheUnseen_TeleportingInEffect", 1238, 1115, "ActiveAbilityType.FearOfTheUnseen",
     1241, ("GetAdditionalRemoveTriggers",)),
    ("TitanhammerSquad_TeleportingInEffect", 1573, 1231, "ActiveAbilityType.TitanhammerSquad",
     1574, ("GetCustomMovingEffectCondition",)),
]


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
    return {"dec": rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                        "includeInactive": True}, 90),
            "ob": rpc("observeBattle", {"runnerId": rid}, 40),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 60),
            "tm": rpc("tileMeta", {"runnerId": rid}, 60),
            "bg": rpc("boardGraph", {"runnerId": rid}, 60)}


def offline_state(cap):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"]), board


def unit_view(st, uid: int) -> dict:
    """La forme EXACTE des deux cotes -- un etat OFFLINE des deux, l'un rejoue par le port, l'autre
    RECHARGE du natif. `effects` = les noms d'effet NON consommes, tries (l'ensemble entier : un
    effet qui apparaitrait en trop se verrait)."""
    from engine.runner.components import UnitComponent, get_unit_feet
    from engine.ai.state_bridge import _is_untargetable
    e = st.get_entity(int(uid))
    uc = e.get_component(UnitComponent) if e is not None else None
    feet = get_unit_feet(st, int(uid))
    effs = sorted((getattr(x, "name", None) or str(getattr(x, "effect_type", "?")))
                  for x in (st.effects.by_unit.get(int(uid)) or []) if not x.consumed)
    return {"pos": (feet[0] if feet else None), "alive": (uc.alive if uc is not None else None),
            "effects": effs, "untargetable": bool(_is_untargetable(st, int(uid)))}


def attack_of(st, uid: int):
    """L'Attack COURANTE de l'unite dans l'etat porte -- le canal par lequel l'aura
    `PathOfCommand_ExtraDmg` du porteur qui vient d'atterrir devient NUMERIQUE chez son allie."""
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    e = st.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    return None if ctx is None else ctx.stat(StatType.ATTACK)


def find_vid(st, sub: str):
    from engine.runner.components import UnitComponent
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and sub.lower() in str(uc.visual_id).lower():
            return int(uid)
    return None


# --------------------------------------------------------------------------- etape 0 : inventaire

def inventaire() -> None:
    import gameconfig as GC  # noqa: F401  (charge le catalogue pour unit_map)
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.entities.effect_type import EffectType

    print("=== etape 0 -- INVENTAIRE de la famille ATeleportingEffect (4 derivees) ===")
    by_id = {int(m): m.name for m in EffectType}
    for cls, eff, src, src_enum, moving, over in FAMILY:
        name = by_id.get(eff, "?")
        trig = [c.__name__ for c in EFFECT_TRIGGERS.get(eff, [])]
        klass = "OUI" if name in EFFECT_CLASSES else "non (BaseEffect nu)"
        mv_trig = [c.__name__ for c in EFFECT_TRIGGERS.get(moving, [])] if moving else []
        print("  %-38s effet=%-5d %-34s" % (cls, eff, name))
        print("      source      = %d (%s)" % (src, src_enum))
        print("      moving      = %s%s" % (moving or "AUCUN (Nullable vide -> Nothing())",
                                            (" " + by_id.get(moving, "?")) if moving else ""))
        print("      surcharges  = %s" % (", ".join(over) or "aucune (les deux vslots = neutres)"))
        print("      EFFECT_CLASSES[%s] = %s" % (name, klass))
        print("      EFFECT_TRIGGERS[%d] = %s" % (eff, trig or "AUCUN -- non porte"))
        if moving:
            print("      EFFECT_TRIGGERS[%d] = %s" % (moving, mv_trig or "AUCUN -- non porte"))
    print()


# --------------------------------------------------------------------------- confrontations

def _confront(label, rid, uid, ally, replay, fails) -> dict:
    """Patron COMMUN : capture AVANT, rejeu OFFLINE par la voie complete, puis LIVE, puis
    rechargement -- et comparaison TERME A TERME. `replay(st)` = le geste offline."""
    pre = capture(rid)
    st, _b = offline_state(pre)
    before = unit_view(st, uid)
    before_ally_att = attack_of(st, ally)
    replay(st)
    port = unit_view(st, uid)
    port_ally = {"effects": unit_view(st, ally)["effects"], "attack": attack_of(st, ally)}
    return {"label": label, "before": before, "before_ally_attack": before_ally_att,
            "port": port, "port_ally": port_ally, "st": st, "fails": fails}


def _finish_confront(res, rid, uid, ally, fails) -> None:
    st2, _b2 = offline_state(capture(rid))
    native = unit_view(st2, uid)
    native_ally = {"effects": unit_view(st2, ally)["effects"], "attack": attack_of(st2, ally)}
    lbl = res["label"]
    for k in ("pos", "alive", "effects", "untargetable"):
        if res["port"][k] != native[k]:
            fails.append("%s %s : port=%r != natif=%r" % (lbl, k, res["port"][k], native[k]))
    for k in ("effects", "attack"):
        if res["port_ally"][k] != native_ally[k]:
            fails.append("%s allie.%s : port=%r != natif=%r"
                         % (lbl, k, res["port_ally"][k], native_ally[k]))
    if "TeleportStrike_TeleportingIn" in native["effects"]:
        fails.append("%s : le natif GARDE 1035 apres le geste -- la mesure ne discrimine RIEN" % lbl)
    print("[%s] avant  = %r  (allie Attack=%r)" % (lbl, res["before"], res["before_ally_attack"]))
    print("[%s] port   = %r  allie=%r" % (lbl, res["port"], res["port_ally"]))
    print("[%s] natif  = %r  allie=%r" % (lbl, native, native_ally))


def confront_move(rid, uid, ally, dest, fails) -> None:
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.runner import Runner

    def replay(st):
        Runner(st).install_default_handlers(20).apply(MoveUnitMessage(int(uid), tuple(dest)))

    res = _confront("CONFRONT-MOVE", rid, uid, ally, replay, fails)
    r = _duel(["act", "move", "--unit", str(uid), "--to", "%d,%d" % tuple(dest),
               "--state-file", str(STATE), "--runner", str(rid)])
    if r.returncode != 0:
        raise SystemExit("CONFRONT-MOVE : move live REFUSE (montage): %s"
                         % (r.stdout or r.stderr)[-800:])
    _finish_confront(res, rid, uid, ally, fails)
    if PATH_OF_COMMAND not in res["port_ally"]["effects"]:
        fails.append("CONFRONT-MOVE : l'allie n'a PAS recu %s cote port apres l'atterrissage"
                     % PATH_OF_COMMAND)
    d = ((res["port_ally"]["attack"] or 0) - (res["before_ally_attack"] or 0))
    if d <= 0:
        fails.append("CONFRONT-MOVE : delta Attack de l'allie = %r (<=0) -- l'aura n'a pas mordu, "
                     "la mesure n'est pas discriminante" % d)
    print("[CONFRONT-MOVE] delta Attack de l'allie = %r (aura PathOfCommand a l'atterrissage)" % d)


def confront_ability(rid, uid, ally, target, ability, fails) -> None:
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    def replay(st):
        Runner(st).install_default_handlers(20).apply(
            ActiveAbilityMessage(caster_id=int(uid), target_id=int(target),
                                 ability_type=int(ability)))

    res = _confront("CONFRONT-ABILITY", rid, uid, ally, replay, fails)
    if res["before"]["pos"] is None:
        fails.append("CONFRONT-ABILITY : le caster n'a pas de position AVANT -- montage nul")
    r = _duel(["act", "ability", "--caster", str(uid), "--ability", str(ability),
               "--target", str(target), "--state-file", str(STATE), "--runner", str(rid)])
    if r.returncode != 0:
        raise SystemExit("CONFRONT-ABILITY : cast live REFUSE (montage): %s"
                         % (r.stdout or r.stderr)[-800:])
    _finish_confront(res, rid, uid, ally, fails)
    if res["port"]["pos"] != res["before"]["pos"]:
        fails.append("CONFRONT-ABILITY : le caster a BOUGE -- T1 pourrait expliquer le retrait, "
                     "la mesure ne separe plus T2 de T1")


def confront_finish(rid, uid, ally, fails) -> None:
    from engine.runner.operations.turnflow import FinishUnitTurnOperation

    def replay(st):
        FinishUnitTurnOperation.execute(st, int(uid))

    res = _confront("CONFRONT-FINISH", rid, uid, ally, replay, fails)
    r = _duel(["act", "finish", "--unit", str(uid),
               "--state-file", str(STATE), "--runner", str(rid)])
    if r.returncode != 0:
        raise SystemExit("CONFRONT-FINISH : finish live REFUSE (montage): %s"
                         % (r.stdout or r.stderr)[-800:])
    _finish_confront(res, rid, uid, ally, fails)


def e_moving(rid, uid, dest, fails) -> None:
    """Le marqueur TRANSITOIRE `1036 TeleportStrike_Moving` : T4 le pose au `On(PreUnitMove)`,
    `TeleportMovingEffect` le retire au `On(UnitAfterMove)` du MEME pas. On l'observe des deux
    cotes : cote PORT en decoupant le pas (Operation puis vecteur after-move), cote NATIF dans la
    cascade d'events du `applyAction`."""
    from engine.runner.event_bus import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.triggers import after_move_triggers

    st, _b = offline_state(capture(rid))
    MoveUnitOperation(int(uid), tuple(dest)).execute(st, EventBus())
    mid = sorted(int(getattr(x, "effect_type", -1))
                 for x in (st.effects.by_unit.get(int(uid)) or []) if not x.consumed)
    after_move_triggers(st, int(uid))
    end = sorted(int(getattr(x, "effect_type", -1))
                 for x in (st.effects.by_unit.get(int(uid)) or []) if not x.consumed)
    print("[E-MOVING] port : PENDANT le pas=%r  APRES le vecteur after-move=%r" % (mid, end))
    if MOVING not in mid:
        fails.append("E-MOVING : %d absent PENDANT le pas cote port -- T4 n'a pas pose" % MOVING)
    if TELEPORTING_IN not in mid:
        fails.append("E-MOVING : %d deja retire PENDANT le pas -- T1 fire trop tot" % TELEPORTING_IN)
    if MOVING in end:
        fails.append("E-MOVING : %d SURVIT au pas cote port -- TeleportMovingEffect non retire"
                     % MOVING)
    if TELEPORTING_IN in end:
        fails.append("E-MOVING : %d SURVIT au pas cote port -- T1 n'a pas retire" % TELEPORTING_IN)


# --------------------------------------------------------------------------- main

def run_couple(board_id, seed_value, fails) -> None:
    print("=== couple board=%s seed=%s ===" % (board_id, seed_value))
    rid = build(seed_value, board_id)
    try:
        st, board = offline_state(capture(rid))
        autarch = find_vid(st, "eldarAutarch")
        ally = find_vid(st, "adeptCanoness")
        if autarch is None or ally is None:
            raise SystemExit("MONTAGE : autarch/allie non deployes")
        v = unit_view(st, autarch)
        print("[E1] etat de depart : %r" % (v,))
        if "TeleportStrike_TeleportingIn" not in v["effects"]:
            raise SystemExit("MONTAGE : l'autarch n'arrive pas en teleport-in")
        if PATH_OF_COMMAND in unit_view(st, ally)["effects"]:
            fails.append("E1 : l'allie a DEJA %s avant l'atterrissage" % PATH_OF_COMMAND)

        # une destination LIBRE et distincte -- pool board-wide, donc n'importe quelle tuile vide
        occupied = {unit_view(st, u)["pos"] for u in st.entities}
        dest = None
        for tid in sorted(board.by_id):
            c = board.coord(int(tid))
            if c not in occupied:
                dest = c
                break
        if dest is None:
            raise SystemExit("MONTAGE : aucune tuile libre")

        e_moving(rid, autarch, dest, fails)
        confront_move(rid, autarch, ally, dest, fails)
    finally:
        _duel(["dispose", "--state-file", str(STATE)])

    # deuxieme runner : T2 -- un cast SANS deplacement prealable du caster. On amene un ENNEMI au
    # contact (`applyAction` ne verifie pas la propriete du `unitId`, cf. runner.md §4) pour que
    # l'attaque normale de l'autarch soit legale DEPUIS SA TUILE.
    rid = build(seed_value, board_id)
    try:
        cap = capture(rid)
        st, brd = offline_state(cap)
        autarch = find_vid(st, "eldarAutarch")
        ally = find_vid(st, "adeptCanoness")
        from engine.runner.components import OwnerComponent
        mine = st.get_entity(autarch).get_component(OwnerComponent).team
        foe = next((int(u) for u, e in st.entities.items()
                    if (e.get_component(OwnerComponent) or None) is not None
                    and e.get_component(OwnerComponent).team != mine), None)
        pos = unit_view(st, autarch)["pos"]
        taken = {unit_view(st, u)["pos"] for u in st.entities}
        free = [brd.coord(t) for t in brd.neighbours(brd.id_at(pos[0], pos[1]))
                if brd.coord(t) not in taken]
        if foe is None or not free:
            raise SystemExit("MONTAGE : pas d'ennemi / pas de tuile libre adjacente a l'autarch")
        r = _duel(["act", "move", "--unit", str(foe), "--to", "%d,%d" % tuple(free[0]),
                   "--state-file", str(STATE), "--runner", str(rid)])
        if r.returncode != 0:
            raise SystemExit("MONTAGE : impossible d'amener un ennemi au contact : %s"
                             % (r.stdout or r.stderr)[-400:])
        norm = None
        for u in (capture(rid)["dec"].get("units") or []):
            if u.get("id") == autarch:
                for a in (u.get("abilities") or []):
                    if a.get("kind") == "normal" or a.get("isNormalAttack"):
                        norm = a.get("type") or a.get("abilityType")
        if norm is None:
            raise SystemExit("MONTAGE : attaque normale de l'autarch introuvable")
        confront_ability(rid, autarch, ally, foe, norm, fails)
    finally:
        _duel(["dispose", "--state-file", str(STATE)])

    # troisieme runner : T3 -- l'autarch clot son tour sans avoir ni bouge ni caste.
    rid = build(seed_value, board_id)
    try:
        st, _b = offline_state(capture(rid))
        autarch = find_vid(st, "eldarAutarch")
        ally = find_vid(st, "adeptCanoness")
        confront_finish(rid, autarch, ally, fails)
    finally:
        _duel(["dispose", "--state-file", str(STATE)])


def main() -> int:
    fails: list = []
    inventaire()
    if "--offline" in sys.argv:
        print("OK (inventaire seul)")
        return 0
    for board_id, seed_value in COUPLES:
        run_couple(board_id, seed_value, fails)
    print()
    if fails:
        print("=== %d ECHEC(S) ===" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("=== OK -- les 4 triggers d'ATeleportingEffect + TeleportMovingEffect confrontes ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
