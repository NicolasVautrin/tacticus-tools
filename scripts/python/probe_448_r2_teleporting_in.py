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


def build(seed_value: str, board_id: str, extra=()) -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        STATE.unlink()
    p = _duel(["build", "--seed", seed_value, "--board", board_id, "--rank", "17", "--no-ai",
               "--p-units", P_UNITS, "--a-units", A_UNITS, "--state-file", str(STATE)]
              + list(extra))
    if not STATE.exists():
        raise SystemExit("build KO (MONTAGE, pas une mesure): "
                         + (p.stderr or p.stdout or "")[-800:])
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def capture(rid) -> dict:
    """⚠ `decisionView` SANS `includeInactive` -- le MEME canal que `test_deep_strike_live.py` et que
    la conftest. Avec `includeInactive: True` la capture ramene les owner-effects passifs DEJA
    presents mais inactifs (ici les deux `PathOfCommand_*` de l'autarch en teleport-in), et
    `_seed_ability_owner_effects` n'ajoute alors plus rien a l'atterrissage -> le
    `refresh_aura_stat_modifiers` conditionne a `added` ne tourne pas et l'aura reste inerte cote
    port. Asymetrie de CANAL connue, hors perimetre de cette tranche : on capture comme le reste du
    harnais, et on le DIT."""
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
    """L'Attack MATERIALISEE de l'unite dans l'etat porte. Cote NATIF (etat RECHARGE) elle porte deja
    la contribution de l'aura ; cote PORT elle ne la porte PAS -- l'aura `PathOfCommand_ExtraDmg` est
    lue par le port a la QUERY (`aura_attack_bonus_from_allies`), pas materialisee dans le
    `UnitStats` (`refresh_aura_stat_modifiers` ne couvre que les effets qui DECLARENT l'interface
    `aura_stat_modification_*`, ce que PathOfCommand ne fait pas). Ce canal sert donc a mesurer le
    DELTA NATIF ; la comparaison numerique se fait contre `aura_bonus` ci-dessous."""
    from engine.runner.components import StatsComponent
    from engine.entities.stats import StatType
    e = st.get_entity(int(uid))
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    return None if ctx is None else ctx.stat(StatType.ATTACK)


def aura_bonus(st, att_id: int) -> int:
    """Le bonus d'Attack que le port accorde a `att_id` via les auras de ses allies -- MEME canal que
    `tests/engine/runner/test_deep_strike_live.py` (`aura_attack_bonus_from_allies`). Zero tant que
    le porteur est en teleport-in : `entities/effects/aura_selectors.py` exclut explicitement un
    carrier portant `TeleportStrike_TeleportingIn`."""
    import gameconfig as GC
    from engine.playbook.scene import Scene
    from engine.entities.effects import aura_attack_bonus_from_allies
    scene = Scene.from_state(st)
    agu = GC.unit(scene.vis_by_id.get(att_id)) or {}
    ctx = {"att_id": att_id, "att_pos": scene.pos(att_id), "att_team": scene.team(att_id),
           "att_grand_alliance": agu.get("GrandAllianceId"), "att_faction": agu.get("FactionId"),
           "board": scene.board}
    carriers = [(uid, scene.pos(uid), scene.team(uid), scene.mult(uid), scene.ablvl_by_id.get(uid),
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("GrandAllianceId"),
                 (GC.unit(scene.vis_by_id.get(uid)) or {}).get("FactionId"), scene.effects(uid))
                for uid in scene.pos_by_id if uid != att_id and (scene.hp(uid) or 0) > 0]
    return aura_attack_bonus_from_allies(carriers, ctx)


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
    port_ally = {"effects": unit_view(st, ally)["effects"], "aura": aura_bonus(st, ally)}
    return {"label": label, "before": before, "before_ally_attack": before_ally_att,
            "port": port, "port_ally": port_ally, "st": st, "fails": fails}


def _finish_confront(res, rid, uid, ally, fails) -> dict:
    st2, _b2 = offline_state(capture(rid))
    native = unit_view(st2, uid)
    native_ally = {"effects": unit_view(st2, ally)["effects"], "attack": attack_of(st2, ally)}
    lbl = res["label"]
    for k in ("pos", "alive", "effects", "untargetable"):
        if res["port"][k] != native[k]:
            fails.append("%s %s : port=%r != natif=%r" % (lbl, k, res["port"][k], native[k]))
    if res["port_ally"]["effects"] != native_ally["effects"]:
        fails.append("%s allie.effects : port=%r != natif=%r"
                     % (lbl, res["port_ally"]["effects"], native_ally["effects"]))
    if "TeleportStrike_TeleportingIn" in native["effects"]:
        fails.append("%s : le natif GARDE 1035 apres le geste -- la mesure ne discrimine RIEN" % lbl)
    print("[%s] avant  = %r  (allie Attack=%r)" % (lbl, res["before"], res["before_ally_attack"]))
    print("[%s] port   = %r  allie=%r" % (lbl, res["port"], res["port_ally"]))
    print("[%s] natif  = %r  allie=%r" % (lbl, native, native_ally))
    return native_ally


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
    native_ally = _finish_confront(res, rid, uid, ally, fails)
    if PATH_OF_COMMAND not in res["port"]["effects"]:
        fails.append("CONFRONT-MOVE : le porteur n'a PAS repris %s cote port apres l'atterrissage"
                     % PATH_OF_COMMAND)
    # LE CHIFFRE : le bonus d'aura que le port accorde a l'allie APRES l'atterrissage, contre le
    # DELTA d'Attack que le natif lui a reellement donne en travers du MEME pas.
    live_delta = ((native_ally["attack"] or 0) - (res["before_ally_attack"] or 0))
    port_aura = res["port_ally"]["aura"]
    print("[CONFRONT-MOVE] aura port = %r   delta Attack natif = %r" % (port_aura, live_delta))
    if live_delta <= 0:
        fails.append("CONFRONT-MOVE : delta Attack natif = %r (<=0) -- l'aura n'a pas mordu LIVE, "
                     "la mesure n'est pas discriminante" % live_delta)
    elif port_aura != live_delta:
        fails.append("CONFRONT-MOVE : aura port %r != delta Attack natif %r"
                     % (port_aura, live_delta))


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
    from engine.runner.events import EventBus
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

        # DESTINATION CHOISIE, pas subie : une tuile **adjacente a l'allie** ET dans le pool
        # LEGAL du natif (`aiMovableTiles` -- le pool est board-wide sous 1035, mais toutes les
        # tuiles ne sont pas jouables : un `applyAction move` hors pool est un NO-OP SILENCIEUX,
        # H55). C'est ce qui rend l'atterrissage NUMERIQUE : l'aura `PathOfCommand` doit avoir une
        # cible en portee, sinon les deux cotes rendent 0 -- accord PARFAIT et entierement VIDE.
        mv = (rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}).get("units") or []
        legal = {(t.get("col"), t.get("row")) for u in mv if u.get("unitId") == autarch
                 for t in (u.get("tiles") or [])}
        apos = unit_view(st, ally)["pos"]
        dest = next((board.coord(t) for t in board.neighbours(board.id_at(apos[0], apos[1]))
                     if board.coord(t) in legal), None)
        if dest is None:
            raise SystemExit("MONTAGE : aucune tuile LEGALE adjacente a l'allie (pool=%d)"
                             % len(legal))

        e_moving(rid, autarch, dest, fails)
        confront_move(rid, autarch, ally, dest, fails)
    finally:
        _duel(["dispose", "--state-file", str(STATE)])

    # deuxieme runner : T2 -- un cast SANS deplacement prealable du caster. On amene un ENNEMI au
    # contact (`applyAction` ne verifie pas la propriete du `unitId`, cf. runner.md §4) pour que
    # l'attaque normale de l'autarch soit legale DEPUIS SA TUILE. `--unit-stat Movement=20` sur les
    # trois a-units : sans lui l'ennemi n'atteint pas l'autarch en UN pas sur un board large (C3_26),
    # et le `applyAction move` hors portee est un NO-OP SILENCIEUX -> le cast d'apres ne mordrait
    # pas et la mesure serait VIDE en se lisant comme un desaccord.
    rid = build(seed_value, board_id,
                extra=["--unit-stat", ";".join("%s:Movement=20" % v for v in A_UNITS.split(","))])
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
        # `NormalAttackType` est PER-UNITE (l'id 69 n'est pas universel, cf. `_normal_ability_map`).
        norm = None
        for u in (capture(rid)["dec"].get("units") or []):
            if u.get("id") == autarch:
                for a in (u.get("abilities") or []):
                    if a.get("kind") == "normal":
                        norm = a.get("id")
        if norm is None or foe is None:
            raise SystemExit("MONTAGE : attaque normale de l'autarch / ennemi introuvable")
        pos = unit_view(st, autarch)["pos"]
        taken = {unit_view(st, u)["pos"] for u in st.entities}
        free = [brd.coord(t) for t in brd.neighbours(brd.id_at(pos[0], pos[1]))
                if brd.coord(t) not in taken and brd.walkable(t)]
        # ⚠ On EXIGE que la cible soit dans `fromHere` (castable SANS bouger) : un cast hors portee
        # est accepte par la CLI et ne mute RIEN cote natif -- le port, lui, executerait. Sans ce
        # controle un montage rate se lit comme un desaccord de PORT. Et un `applyAction move` hors
        # pool est lui aussi un NO-OP SILENCIEUX (H55) -> on ESSAIE les tuiles adjacentes libres une
        # par une jusqu'a ce que le natif reconnaisse une cible.
        here = []
        for cand in free:
            _duel(["act", "move", "--unit", str(foe), "--to", "%d,%d" % tuple(cand),
                   "--state-file", str(STATE), "--runner", str(rid)])
            tg = rpc("abilityTargets", {"runnerId": rid, "unitId": autarch,
                                        "abilityType": norm}, 60) or {}
            here = [t.get("targetId") for u in (tg.get("units") or [])
                    for a in (u.get("abilities") or []) if a.get("abilityId") == norm
                    for t in (a.get("fromHere") or [])]
            if here:
                break
        if not here:
            raise SystemExit("MONTAGE : AUCUNE cible de l'autarch SANS bouger apres %d tentatives "
                             "d'approche (norm=%r)" % (len(free), norm))
        confront_ability(rid, autarch, ally, int(here[0]), norm, fails)
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
    # CONTRE-EPREUVE (`--mutate no-triggers`) : on VIDE les deux entrees du registre -- c'est-a-dire
    # exactement le port d'AVANT #448-r2 sur le chemin MOUVEMENT/CAST. Le probe DOIT alors rougir ;
    # s'il reste vert, c'est qu'il ne mesure rien (VERT est le resultat SUSPECT sur une
    # contre-epreuve).
    mutated = "--mutate" in sys.argv
    if mutated:
        from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
        EFFECT_TRIGGERS[TELEPORTING_IN] = []
        EFFECT_TRIGGERS[MOVING] = []
        print("[MUTATE] EFFECT_TRIGGERS[%d] et [%d] VIDES -- le probe DOIT rougir"
              % (TELEPORTING_IN, MOVING))
    for board_id, seed_value in COUPLES:
        try:
            run_couple(board_id, seed_value, fails)
        except SystemExit as e:
            if not mutated:
                raise
            fails.append("MUTATE : %s" % e)
        if mutated:
            break                       # un seul couple suffit a la contre-epreuve
    print()
    if fails:
        print("=== %d ECHEC(S) ===" % len(fails))
        for f in fails:
            print("  - " + f)
        return 0 if mutated else 1
    if mutated:
        print("=== CONTRE-EPREUVE VERTE = LE PROBE NE MESURE RIEN ===")
        return 1
    print("=== OK -- les 4 triggers d'ATeleportingEffect + TeleportMovingEffect confrontes ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
