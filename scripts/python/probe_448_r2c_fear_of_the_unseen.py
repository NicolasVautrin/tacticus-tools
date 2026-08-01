"""#448-r2c -- `1238 FearOfTheUnseen_TeleportingIn` : CONFRONTATION live/port de la tranche 2/4 de
la famille `IdunBattle.Entities.Effects.Loki.ATeleportingEffect`.

RE (decompile = verite ; detail dans
`docs/rl/case-448-r2c-fear-of-the-unseen-teleporting-in.md` et dans
`engine/runner/operations/triggers/loki/teleporting_in.py`) :

    ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal = QUATRE Triggered(), et le vslot
    0x738 (`GetAdditionalRemoveTriggers`) est lu dans les QUATRE, T4 COMPRIS.

    FearOfTheUnseen_TeleportingInEffect$$GetAdditionalRemoveTriggers   <- la SEULE surcharge du build
        = AmountIsEqual( EffectRemainingTurns(<Sel+0x38> = EffectSelf),
                         <DSLFormulas+0x20> = Direct(1) )

    FearOfTheUnseenAbility$$ExecuteBehaviour
        -> AddEffect(0x4d6 = 1238, stateRef, <Sel+0x30> = Self, Sum(TurnsFromRounds(1), Direct(1)))

CE QUE LE PROBE MESURE (le regime est NUMERIQUE, donc chaque volet porte un CHIFFRE) :

  etape 0     INVENTAIRE offline : registre, constantes, et le fait que 1238 est bien la SEULE des
              quatre a surcharger le vslot. Aucune bataille montee.
  V-CAST      Le cast pose 1238 -- et avec QUEL `remaining`. Attendu 3 des deux cotes a deux
              joueurs (`TurnsFromRounds(1)` = 2, `+ Direct(1)`). C'est la borne haute du regime.
  V-SURVIE    **LE DISCRIMINANT.** Apres le cast, le `FinishUnitTurn` du caster puis DEUX `endturn`
              complets. Le natif doit GARDER 1238 tout du long, avec `remaining` 3 -> 2 -> 1. Un
              port qui collapserait le vslot 0x738 a `True` (le corps de BASE) l'aurait retire
              des le premier `FinishUnitTurn`.
  V-RETRAIT   Au tour SUIVANT du porteur (`remaining == 1`), un pas retire 1238 -- et pas avant.
  V-MOVING    Le marqueur transitoire `1241 FearOfTheUnseen_Moving` : pose par T4 au
              `On(0x1f PreUnitMove)`, retire par `TeleportMovingEffect` au `On(0x04)` du MEME pas.
              Cote port en decoupant le pas ; cote natif il n'est par construction PAS observable
              dans un etat (il nait et meurt dans la meme cascade) -- ce qui est DIT, pas masque.

CONTRE-EPREUVE : `--mutate` collapse le vslot 0x738 a `True` (= le port SANS la surcharge, c'est a
dire le comportement des trois soeurs). Un `--mutate` VERT signifie que la mesure ne discrimine
RIEN, pas que le port est bon.

MESURE de cette contre-epreuve (2 couples, 2026-08-01) : c'est **V-CAST** qui mord, avec un chiffre
net -- le port mute rend `remaining = {1239: 3}` la ou le natif rend `{1238: 3, 1239: 3}`. Autrement
dit **1238 n'existe deja plus a la fin du cast qui vient de le poser** : `ActiveAbilityOperation$$
AddFlagsAfterAbilityExecution` enchaine `FinishUnitTurn(caster, false)` dans la MEME transaction,
donc T3 l'efface aussitot. Le Deathleaper ne disparaitrait JAMAIS.
V-SURVIE et V-RETRAIT restent VERTS sous mutation, et c'est ATTENDU : ils rechargent l'etat depuis
le NATIF a chaque etape, donc le port y HERITE d'un 1238 pose par le jeu et se contente de le
decrementer. Ils mesurent la CHRONOLOGIE, pas la survie a la pose -- seul V-CAST rejoue pose et
retrait dans la meme transaction.

Usage (depuis scripts/python) :
    python probe_448_r2c_fear_of_the_unseen.py              # inventaire + confrontation live
    python probe_448_r2c_fear_of_the_unseen.py --offline    # inventaire SEUL (aucun runner)
    python probe_448_r2c_fear_of_the_unseen.py --mutate     # CONTRE-EPREUVE (doit rougir)
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

LOGS = ROOT / "logs" / "probe448r2c"
STATE = LOGS / "state_448_r2c_fear_of_the_unseen.json"   # SORTIE -> logs/ (#349), JAMAIS data/

TELEPORTING_IN = 1238           # EffectType.FearOfTheUnseen_TeleportingIn (0x4d6)
MOVING = 1241                   # EffectType.FearOfTheUnseen_Moving        (0x4d9)
EXTRA_DAMAGE = 1239             # EffectType.FearOfTheUnseen_ExtraDamage   (0x4d7)
FEAR_ABILITY = 1115             # ActiveAbilityType.FearOfTheUnseen        (0x45b)

#: `tyranDeathleaper` = le SEUL hero du pool a porter 1115. Les deux autres p-units ne servent qu'a
#: donner au joueur des unites a jouer apres le cast (le `endturn` reste possible sans, mais un
#: roster a une seule unite rend le tour degenere).
P_UNITS = "tyranDeathleaper,tyranNeurothrope,tyranTyrantGuard"
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
    """⚠ `decisionView` SANS `includeInactive` -- le MEME canal que le reste du harnais (cf. la
    docstring de `capture` dans `probe_448_r2_teleporting_in.py` : l'asymetrie de canal est connue
    et hors perimetre)."""
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
    RECHARGE du natif. `remaining` porte la valeur qui GOUVERNE le regime, pas seulement la
    presence : c'est elle que `EffectRemainingTurns` lit."""
    from engine.runner.components import UnitComponent, get_unit_feet
    e = st.get_entity(int(uid))
    uc = e.get_component(UnitComponent) if e is not None else None
    feet = get_unit_feet(st, int(uid))
    live = [x for x in (st.effects.by_unit.get(int(uid)) or []) if not x.consumed]
    return {"pos": (feet[0] if feet else None), "alive": (uc.alive if uc is not None else None),
            "effects": sorted((getattr(x, "name", None) or str(getattr(x, "effect_type", "?")))
                              for x in live),
            "remaining": {int(getattr(x, "effect_type", -1)): x.remaining_turns
                          for x in live
                          if int(getattr(x, "effect_type", -1)) in (TELEPORTING_IN, MOVING,
                                                                    EXTRA_DAMAGE)}}


def find_vid(st, sub: str):
    from engine.runner.components import UnitComponent
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and sub.lower() in str(uc.visual_id).lower():
            return int(uid)
    return None


def has(view, eff: int) -> bool:
    return int(eff) in view["remaining"]


#: Les effets que CETTE tranche porte, plus l'aine de la famille (1035/1036, tranche 1) qui traverse
#: le preambule d'atterrissage. Tout ecart SUR CES NOMS est un echec de PORT.
FAMILY_NAMES = frozenset((
    "TeleportStrike_TeleportingIn", "TeleportStrike_Moving",
    "FearOfTheUnseen_TeleportingIn", "FearOfTheUnseen_Moving", "FearOfTheUnseen_ExtraDamage"))

#: RESIDU TIERS MESURE, PRE-EXISTANT et hors perimetre : `1079 IgnoreBattleFatigue`. Le natif le
#: pose et le retire au fil des tours sur `tyranDeathleaper` (trait `Terrifying`) ; le port ne
#: connait ni son poseur ni son retrait, il HERITE seulement de ce que la capture lui donne, et
#: diverge donc a chaque transition. Aucun rapport avec `ATeleportingEffect` : l'ecart est present
#: DES le volet ATTERRIR, c'est a dire AVANT que 1238 n'existe. Son unique consommateur natif LU est
#: `IdunBattleLogic.Entities.Abilities.Active.Loki.BattleFatigueAbility$$CreateTrigger`, qui porte
#: `op_LogicalNot(HasEffect(<Sel+0x30>, 0x437, 0, 6))` -- son POSEUR n'est pas identifie ici.
THIRD_PARTY_RESIDUALS = frozenset(("IgnoreBattleFatigue",))


def diff_effects(label, port, native, fails) -> None:
    """Compare la liste ENTIERE des effets, puis VENTILE : ecart sur un effet de la FAMILLE = echec
    de PORT ; ecart sur un residu TIERS deja nomme = imprime, pas fatal. On ne masque rien -- un
    effet inattendu qui ne serait NI famille NI residu nomme reste un ECHEC."""
    only_port = sorted(set(port["effects"]) - set(native["effects"]))
    only_native = sorted(set(native["effects"]) - set(port["effects"]))
    if not only_port and not only_native:
        return
    for side, names in (("port-seul", only_port), ("natif-seul", only_native)):
        for n in names:
            if n in FAMILY_NAMES:
                fails.append("%s effects [%s] %s : ECART DE PORT sur la famille" % (label, side, n))
            elif n in THIRD_PARTY_RESIDUALS:
                print("      [residu tiers, hors tranche] %s %s : %s" % (label, side, n))
            else:
                fails.append("%s effects [%s] %s : effet inattendu, ni famille ni residu nomme"
                             % (label, side, n))


# --------------------------------------------------------------------------- mutation

def mutate() -> None:
    """CONTRE-EPREUVE : collapse le vslot 0x738 a `True` -- exactement le port SANS la surcharge de
    `FearOfTheUnseen_TeleportingInEffect`, c'est a dire le corps de BASE herite par les trois
    soeurs. On patche la METHODE du mixin, donc les QUATRE classes d'un coup."""
    from engine.runner.operations.triggers.loki import teleporting_in as T
    T._FearOfTheUnseenRemainingIsOne._additional_remove_triggers = (
        lambda self, state, ev: True)
    print("[MUTATE] vslot 0x738 collapse a True -- V-SURVIE DOIT rougir\n")


# --------------------------------------------------------------------------- etape 0 : inventaire

def inventaire() -> None:
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effect_type import EffectType
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.services.movement_query import SPECIAL_MOVEMENT_EFFECT_TYPES

    print("=== etape 0 -- 1238 FearOfTheUnseen_TeleportingIn (tranche 2/4) ===")
    by_id = {int(m): m.name for m in EffectType}
    for eff in (TELEPORTING_IN, MOVING, EXTRA_DAMAGE):
        name = by_id.get(eff, "?")
        print("  %-5d %-34s EFFECT_CLASSES=%-20s EFFECT_TRIGGERS=%s"
              % (eff, name, "OUI" if name in EFFECT_CLASSES else "non (BaseEffect nu)",
                 [c.__name__ for c in EFFECT_TRIGGERS.get(eff, [])] or "AUCUN"))
    print("  vslot 0x738 surcharge  : FearOfTheUnseen_TeleportingInEffect SEULE des quatre")
    print("      = AmountIsEqual(EffectRemainingTurns(EffectSelf), Direct(1))")
    print("  vslot 0x748            : NON surcharge -> conjonct neutre herite")
    print("  vslot 0x758 GetMovingEffectType = Nullable<EffectType>(0x4d9) = %d" % MOVING)
    print("  pathfinder             : 0x4d6 dans SPECIAL_MOVEMENT_EFFECT_TYPES = %s"
          % (0x4d6 in SPECIAL_MOVEMENT_EFFECT_TYPES))
    print()


# --------------------------------------------------------------------------- confrontation

def atterrir(rid, caster, fails) -> None:
    """PREAMBULE DE MONTAGE, decouvert a la mesure et NON DEVINE : `tyranDeathleaper` porte le trait
    `TeleportStrike`, donc il ARRIVE en bataille sous `1035 TeleportStrike_TeleportingIn` -- l'aine
    de la MEME famille `ATeleportingEffect`. Or
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FearOfTheUnseenAbility$$
    GetDynamicInvalidCasterReason` = `IsTeleporting(caster) ? 4 : 0` : sous 1035, le natif REFUSE le
    cast (mesure : l'etat natif revient INCHANGE, tandis que le port, lui, executait -- c'est le
    residu PERMISSIF deja nomme dans `runner/abilities/tyranids.py`).

    Il faut donc le faire ATTERRIR d'abord, et **sans le faire bouger** : son masque porte
    `CasterHasNotMoved` (0x10), donc un pas fermerait le cast pour de bon. Le seul geste qui retire
    1035 sans deplacer est T3 (`On(0x28 UnitFinishedTurn) & HasTile(Owner)`, vslot NEUTRE pour
    1035) -- soit `act finish`. Deux `endturn` ramenent ensuite la main au Deathleaper, frais.

    ⚠ Ce preambule fait de la tranche 1 (#448-r2, 1035) une DEPENDANCE de mesure de la tranche 2 :
    sans son T3, le port ne retirerait pas 1035 et divergerait des l'entree."""
    from engine.runner.messages import EndTurnMessage, FinishUnitTurnMessage
    from engine.runner.runner import Runner

    st, _b = offline_state(capture(rid))
    v = unit_view(st, caster)
    if "TeleportStrike_TeleportingIn" not in v["effects"]:
        print("[ATTERRIR] le Deathleaper n'est pas en 1035 -- preambule inutile")
        return
    print("[ATTERRIR] depart : %r" % (v["effects"],))
    for msg, args in ((FinishUnitTurnMessage, (int(caster),)),
                      (EndTurnMessage, ()), (EndTurnMessage, ())):
        stp, _bp = offline_state(capture(rid))
        Runner(stp).install_default_handlers(20).apply(msg(*args))
        port = unit_view(stp, caster)
        cmd = (["act", "finish", "--unit", str(caster)] if msg is FinishUnitTurnMessage
               else ["act", "endturn"])
        r = _duel(cmd + ["--state-file", str(STATE), "--runner", str(rid)])
        if r.returncode != 0:
            raise SystemExit("ATTERRIR : %s REFUSE (MONTAGE): %s"
                             % (cmd[1], (r.stdout or r.stderr)[-800:]))
        st2, _b2 = offline_state(capture(rid))
        native = unit_view(st2, caster)
        diff_effects("ATTERRIR %s" % cmd[1], port, native, fails)
    st3, _b3 = offline_state(capture(rid))
    v3 = unit_view(st3, caster)
    print("[ATTERRIR] apres finish + 2 endturn : %r" % (v3["effects"],))
    if "TeleportStrike_TeleportingIn" in v3["effects"]:
        raise SystemExit("MONTAGE : 1035 n'est pas parti -- le cast restera refuse")


def cast_live(rid, caster, fails) -> None:
    """Le cast, LIVE puis rejoue par le PORT depuis la MEME capture -- et compare terme a terme.
    `FearOfTheUnseen` est self-castante (`isSelfCasting = 1`, `range = RANGE_SELF`)."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    pre = capture(rid)
    st, _b = offline_state(pre)
    before = unit_view(st, caster)
    print("[V-CAST] avant  = %r" % (before,))
    if has(before, TELEPORTING_IN):
        raise SystemExit("MONTAGE : le Deathleaper porte DEJA 1238 avant le cast")

    Runner(st).install_default_handlers(20).apply(
        ActiveAbilityMessage(caster_id=int(caster), target_id=int(caster),
                             ability_type=FEAR_ABILITY))
    port = unit_view(st, caster)

    r = _duel(["act", "ability", "--caster", str(caster), "--ability", str(FEAR_ABILITY),
               "--target", str(caster), "--state-file", str(STATE), "--runner", str(rid)])
    if r.returncode != 0:
        raise SystemExit("V-CAST : cast live REFUSE (MONTAGE): %s" % (r.stdout or r.stderr)[-800:])
    st2, _b2 = offline_state(capture(rid))
    native = unit_view(st2, caster)
    print("[V-CAST] port   = %r" % (port,))
    print("[V-CAST] natif  = %r" % (native,))

    if not has(native, TELEPORTING_IN):
        raise SystemExit("MONTAGE : le cast live n'a PAS pose 1238 -- rien a confronter")
    diff_effects("V-CAST", port, native, fails)
    if port["remaining"] != native["remaining"]:
        fails.append("V-CAST remaining : port=%r != natif=%r"
                     % (port["remaining"], native["remaining"]))
    # LE CHIFFRE : `Sum(TurnsFromRounds(1), Direct(1))` = 3 a deux joueurs. C'est la BORNE HAUTE du
    # regime -- si le natif posait 1 tour, la surcharge du vslot serait vraie tout de suite et la
    # mesure ne separerait plus rien.
    if native["remaining"].get(TELEPORTING_IN) != 3:
        fails.append("V-CAST : remaining natif de 1238 = %r (attendu 3 = TurnsFromRounds(1) + 1 a "
                     "deux joueurs) -- le regime mesure n'est plus celui qu'on croit"
                     % native["remaining"].get(TELEPORTING_IN))


def survie_live(rid, caster, fails) -> list:
    """LE DISCRIMINANT. Apres le cast, le natif a DEJA fait firer `On(0x28 UnitFinishedTurn)` sur le
    caster (`ActiveAbilityOperation$$AddFlagsAfterAbilityExecution` -> `FinishUnitTurn(caster,
    false)`). Avec le vslot collapse a `True`, 1238 serait DEJA parti a l'entree de cette fonction.

    Puis DEUX `endturn` complets, en verifiant `remaining` a chaque etape des DEUX cotes."""
    from engine.runner.messages import EndTurnMessage
    from engine.runner.runner import Runner

    trace = []
    st, _b = offline_state(capture(rid))
    v = unit_view(st, caster)
    trace.append(("apres-cast", v["remaining"].get(TELEPORTING_IN)))
    print("[V-SURVIE] apres le cast (et le FinishUnitTurn implicite) : %r" % (v["remaining"],))
    if not has(v, TELEPORTING_IN):
        fails.append("V-SURVIE : le natif a RETIRE 1238 des le FinishUnitTurn qui suit le cast -- "
                     "c'est ce que ferait un vslot 0x738 collapse a True")
        return trace

    for i in (1, 2):
        pre = capture(rid)
        stp, _bp = offline_state(pre)
        Runner(stp).install_default_handlers(20).apply(EndTurnMessage())
        port = unit_view(stp, caster)

        r = _duel(["act", "endturn", "--state-file", str(STATE), "--runner", str(rid)])
        if r.returncode != 0:
            raise SystemExit("V-SURVIE : endturn %d REFUSE (MONTAGE): %s"
                             % (i, (r.stdout or r.stderr)[-800:]))
        st2, _b2 = offline_state(capture(rid))
        native = unit_view(st2, caster)
        trace.append(("endturn-%d" % i, native["remaining"].get(TELEPORTING_IN)))
        print("[V-SURVIE] endturn %d : port=%r  natif=%r"
              % (i, port["remaining"], native["remaining"]))
        if port["remaining"] != native["remaining"]:
            fails.append("V-SURVIE endturn %d : remaining port=%r != natif=%r"
                         % (i, port["remaining"], native["remaining"]))
        diff_effects("V-SURVIE endturn %d" % i, port, native, fails)
        if not has(native, TELEPORTING_IN):
            fails.append("V-SURVIE : le natif a perdu 1238 apres %d endturn -- attendu VIVANT "
                         "jusqu'au tour ou remaining vaut 1" % i)
            return trace
    # Le natif doit etre arrive EXACTEMENT a 1 : c'est la seule valeur qui ouvre le regime.
    rem = trace[-1][1]
    if rem != 1:
        fails.append("V-SURVIE : apres 2 endturn le natif est a remaining=%r (attendu 1) -- la "
                     "suite ne mesurerait plus le regime d'ouverture" % rem)
    return trace


def retrait_live(rid, caster, board, fails) -> None:
    """`remaining == 1` : le regime s'OUVRE. Un pas doit retirer 1238 des DEUX cotes.

    La destination est CHOISIE dans `aiMovableTiles` : un `applyAction move` hors pool est un NO-OP
    SILENCIEUX (H55), et un montage rate se lirait comme un desaccord de PORT."""
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.runner import Runner

    pre = capture(rid)
    st, _b = offline_state(pre)
    before = unit_view(st, caster)
    print("[V-RETRAIT] avant le pas = %r" % (before,))
    if before["remaining"].get(TELEPORTING_IN) != 1:
        fails.append("V-RETRAIT : remaining=%r a l'entree (attendu 1) -- volet non discriminant"
                     % before["remaining"].get(TELEPORTING_IN))
        return

    mv = (rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}).get("units") or []
    legal = [(t.get("col"), t.get("row")) for u in mv if u.get("unitId") == caster
             for t in (u.get("tiles") or [])]
    dest = next((c for c in legal if c != before["pos"]), None)
    if dest is None:
        raise SystemExit("MONTAGE : aucune tuile LEGALE pour le Deathleaper (pool=%d)" % len(legal))

    Runner(st).install_default_handlers(20).apply(MoveUnitMessage(int(caster), tuple(dest)))
    port = unit_view(st, caster)

    r = _duel(["act", "move", "--unit", str(caster), "--to", "%d,%d" % tuple(dest),
               "--state-file", str(STATE), "--runner", str(rid)])
    if r.returncode != 0:
        raise SystemExit("V-RETRAIT : move live REFUSE (MONTAGE): %s"
                         % (r.stdout or r.stderr)[-800:])
    st2, _b2 = offline_state(capture(rid))
    native = unit_view(st2, caster)
    print("[V-RETRAIT] port  = %r" % (port,))
    print("[V-RETRAIT] natif = %r" % (native,))
    if native["pos"] == before["pos"]:
        raise SystemExit("V-RETRAIT : le natif n'a PAS bouge (NO-OP silencieux) -- MONTAGE nul")
    diff_effects("V-RETRAIT", port, native, fails)
    for k in ("pos", "alive", "remaining"):
        if port[k] != native[k]:
            fails.append("V-RETRAIT %s : port=%r != natif=%r" % (k, port[k], native[k]))
    if has(native, TELEPORTING_IN):
        fails.append("V-RETRAIT : le natif GARDE 1238 apres le pas a remaining=1 -- la lecture du "
                     "vslot serait FAUSSE")
    if has(native, MOVING):
        fails.append("V-RETRAIT : le natif GARDE 1241 apres le pas -- TeleportMovingEffect ne "
                     "l'aurait pas retire")


def e_moving(rid, caster, board, fails) -> None:
    """Le marqueur TRANSITOIRE 1241, cote PORT, en decoupant le pas (Operation puis vecteur
    after-move). Cote NATIF il n'est PAS observable dans un etat : il nait et meurt dans la MEME
    cascade d'events du `applyAction`. On le DIT plutot que de fabriquer un accord vide."""
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.triggers import after_move_triggers

    st, _b = offline_state(capture(rid))
    v = unit_view(st, caster)
    if v["remaining"].get(TELEPORTING_IN) != 1:
        fails.append("E-MOVING : remaining=%r a l'entree (attendu 1)"
                     % v["remaining"].get(TELEPORTING_IN))
        return
    mv = (rpc("aiMovableTiles", {"runnerId": rid}, 60) or {}).get("units") or []
    legal = [(t.get("col"), t.get("row")) for u in mv if u.get("unitId") == caster
             for t in (u.get("tiles") or [])]
    dest = next((c for c in legal if c != v["pos"]), None)
    if dest is None:
        raise SystemExit("MONTAGE : aucune tuile LEGALE pour E-MOVING")

    MoveUnitOperation(int(caster), tuple(dest)).execute(st, EventBus())
    mid = sorted(int(getattr(x, "effect_type", -1))
                 for x in (st.effects.by_unit.get(int(caster)) or []) if not x.consumed)
    after_move_triggers(st, int(caster))
    end = sorted(int(getattr(x, "effect_type", -1))
                 for x in (st.effects.by_unit.get(int(caster)) or []) if not x.consumed)
    print("[E-MOVING] port : PENDANT le pas=%r  APRES le vecteur after-move=%r" % (mid, end))
    if MOVING not in mid:
        fails.append("E-MOVING : %d absent PENDANT le pas -- T4 n'a pas pose" % MOVING)
    if TELEPORTING_IN not in mid:
        fails.append("E-MOVING : %d deja retire PENDANT le pas -- T1 fire trop tot" % TELEPORTING_IN)
    if MOVING in end:
        fails.append("E-MOVING : %d SURVIT au pas -- TeleportMovingEffect non retire" % MOVING)
    if TELEPORTING_IN in end:
        fails.append("E-MOVING : %d SURVIT au pas -- T1 n'a pas retire" % TELEPORTING_IN)


# --------------------------------------------------------------------------- main

def run_couple(board_id, seed_value, fails) -> None:
    print("=== couple board=%s seed=%s ===" % (board_id, seed_value))
    rid = build(seed_value, board_id)
    try:
        st, board = offline_state(capture(rid))
        caster = find_vid(st, "tyranDeathleaper")
        if caster is None:
            raise SystemExit("MONTAGE : tyranDeathleaper non deploye")
        atterrir(rid, caster, fails)
        cast_live(rid, caster, fails)
        trace = survie_live(rid, caster, fails)
        print("[V-SURVIE] trace remaining = %r" % (trace,))
        if trace and trace[-1][1] == 1:
            e_moving(rid, caster, board, fails)
            retrait_live(rid, caster, board, fails)
        else:
            print("[V-RETRAIT] NON JOUE : le regime d'ouverture n'a pas ete atteint")
    finally:
        _duel(["dispose", "--state-file", str(STATE)])
    print()


def main() -> int:
    offline_only = "--offline" in sys.argv
    inventaire()
    if offline_only:
        return 0
    if "--mutate" in sys.argv:
        mutate()
    fails: list = []
    for board_id, seed_value in COUPLES:
        run_couple(board_id, seed_value, fails)
    print("=== VERDICT ===")
    if fails:
        for f in fails:
            print("  ECHEC %s" % f)
        print("  -> %d ecart(s)" % len(fails))
        return 1
    print("  OK -- natif == port sur les %d couples" % len(COUPLES))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
