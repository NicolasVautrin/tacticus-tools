#!/usr/bin/env python
"""#448-r2b -- `1140 StormboyzStrike_TeleportingIn`, tranche 2/4 de la famille
`IdunBattle.Entities.Effects.Loki.ATeleportingEffect`.

CE QUE CETTE TRANCHE A DE PARTICULIER (et pourquoi elle n'est pas un copier-coller de la 1/4) :

  * elle est la SEULE des quatre dont `GetMovingEffectType()` rend un `Nullable` VIDE -> T4 prend
    la branche `Nothing()`. Ce n'est PAS deduit d'une absence de symbole : la surcharge EXISTE
    (`resolveMethodPtr` la trouve a la profondeur 0 de la chaine de parents), son corps est
    DEDUPLIQUE avec `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`, et les octets a
    cette entree sont `33 c0 c3` = `xor eax, eax ; ret` -- `Nullable<EffectType>` (int32 + bool,
    8 octets) revient dans RAX, donc `hasValue = 0`. Recoupe par DEUX sources independantes :
    l'`EffectType` du build n'a que TROIS `*_Moving` (1036/1241/1574) et
    `IdunBattleLogic.Effects.TeleportMovingEffect$$.ctor` n'a que TROIS appelants.
  * elle est la SEULE dont le poseur retire l'unite du plateau
    (`...StormboyzStrike_TeleportAbility$$CreateBehaviour` -> `RemoveUnitFromItsTiles`), donc la
    SEULE qui exerce le gate `HasTile(Owner)` de T3 par son bras FAUX : sous 1140 l'unite est hors
    plateau, T3 ne fire pas, et l'effet SURVIT a la fin de son tour.

CE QUE LE PROBE MESURE (montage = GREFFE du passif, `case-92` §5bis, deja outillee par #366-r1) :

  A            OFFLINE. Re-derive les quatre points ci-dessus depuis la table VERSIONNEE du build
               (`frida/enums.tsv`) et l'etat du registre du port. Aucun runner.
  E1           Etat de depart LIVE : le porteur greffe arrive HORS PLATEAU (`pos = None`,
               empreinte vide) avec `1140` a `remaining = 2`.
  T2-VIDE      `abilityTargets` du porteur sous 1140 : `fromHere` VIDE des deux cotes -> T2 n'est
               pas exercable par un geste. Le dire est la mesure.
  CONFRONT-MOVE  T1 + la branche `Nothing()` de T4. Meme etat de depart, meme pas rejoue OFFLINE
               (voie complete `Runner.apply(MoveUnitMessage)`) puis LIVE ; etats finaux compares
               TERME A TERME. La cascade d'events NATIVE est scannee : AUCUN groupe `*_Moving` ne
               doit y apparaitre -- c'est la preuve LIVE de la branche `Nothing()`.
               ⚠ ETAGE MANQUANT, NOMME : `...StormboyzStrike_MissAbility` (non portee, residu de
               `case-448-r1`) ecoute le MEME `On(0x1f)` et fait `RemoveEffect(Caster, 0x474)`
               INCONDITIONNELLEMENT -- cote natif c'est ELLE qui retire 1140, cote port c'est T1.
               Meme etat final, etage different, et le probe le DIT. Elle porte aussi 20 % de
               deviation de destination : le probe compare la destination obtenue et signale le
               MISS au lieu de le lire comme un desaccord de port.
  CONFRONT-FINISH  T3, PAR ETAGES -- c'est le coeur de la tranche.
               (a) port : `FinishUnitTurnOperation` sur le porteur HORS PLATEAU -> `HasTile` FAUX
                   -> 1140 SURVIT, l'unite reste hors plateau ;
               (b) natif : `applyAction finish` -> `...StormboyzStrike_FallbackAbility` (non
                   portee, MEME `On(0x28)`) REPOSE l'unite, puis T3 retire ;
               (c) le probe INJECTE la sortie de l'etage (b) dans l'etat du port (l'unite est
                   posee sur la tuile que le NATIF a choisie) et re-emet `On(0x28)` -> T3 doit
                   alors retirer, et les etats doivent coincider TERME A TERME.
               La divergence de (a) est donc IMPUTEE a un etage nomme, pas laissee en « desaccord ».
  E1b          OBSERVATION (montage `replace=False`, le porteur GARDE ses passifs) : le porteur
               sous 1140 a-t-il DEJA ses owner-effects passifs cote natif ? Si oui, le regime
               « passives DEFERREES » de 1035 n'existe PAS pour 1140 -> pas de
               `_TeleportStrikeLandingMixin` sur cette tranche.

CONTRE-EPREUVES (VERT est le resultat SUSPECT) :
    --mutate           VIDE `EFFECT_TRIGGERS[1140]` (= le port d'avant cette tranche)
    --mutate-hastile   NEUTRALISE le gate `HasTile` de T3 (rend `True`)

ASCII only. Usage (depuis scripts/python) :
    python probe_448_r2b_stormboyz_teleporting_in.py
    python probe_448_r2b_stormboyz_teleporting_in.py --offline
    python probe_448_r2b_stormboyz_teleporting_in.py --mutate
    python probe_448_r2b_stormboyz_teleporting_in.py --mutate-hastile
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

import catalog_inject as CI                                              # noqa: E402
import stream_events                                                     # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                      # noqa: E402

ABILITY = "StormboyzStrike"
TELEPORTING_IN = 1140                 # 0x474 EffectType.StormboyzStrike_TeleportingIn
LOGS = ROOT / "logs" / "probe448r2b"

#: `(board, seed, greffon, adversaires)` -- les DEUX montages de #366-r1 qui ont deja produit un
#: porteur hors plateau sous 1140, l'un sur base WALK, l'autre sur base FLY (le VRAI porteur
#: `orksNpc6Stormboy` a le trait `Flying`).
PLAN = [("MC1_67", 777, "orksNob", ["ultraTitus"]),
        ("C3_26", 31337, "thousTzaangor", ["ultraTitus"])]


# --------------------------------------------------------------------------- transport

def rpc(sid, m, args, t=120):
    r = _rpc(sid, m, [args], timeout=t)
    return (r.get("result") if isinstance(r, dict) and "result" in r else r) or {}


def build(seed: int, board: str, graft: str, foes, seed_bc: str, state_file: Path) -> int:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--rank", "17",
           "--board", board, "--p-units", graft, "--a-units", ",".join(foes), "--no-ai",
           "--seed-bc", seed_bc, "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        raise SystemExit("build KO (MONTAGE, pas une mesure) board=%s graft=%s rc=%s : %s"
                         % (board, graft, p.returncode,
                            ((p.stdout or "") + (p.stderr or ""))[-2000:] or "<<aucune sortie>>"))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def capture(sid, rid) -> dict:
    return {"dec": rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 150),
            "ob": rpc(sid, "observeBattle", {"runnerId": rid}, 60),
            "snap": rpc(sid, "combatSnapshot", {"runnerId": rid}, 90),
            "bg": rpc(sid, "boardGraph", {"runnerId": rid}, 90)}


def offline_state(cap):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board), board


def carrier_id(state, foes):
    """L'id du GREFFON. ⚠ On ne peut PAS le retrouver par `visualId` : une unite SANS TUILE sort
    d'`observeBattle` et arrive dans `decisionView` avec `visualId = pos = team = null` (#366-r1).
    On l'identifie en NEGATIF : l'unite qui n'est aucun des adversaires."""
    from engine.runner.components import StatsComponent
    out = []
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        vid = getattr(getattr(sc, "ctx", None), "visual_id", None)
        if vid not in set(foes):
            out.append(int(eid))
    return out[0] if len(out) == 1 else None


def control_owner(sid, board_id, seed, graft, foes, tag):
    """RECONSTITUTION DE L'ENTREE, pas un correctif de port. Une unite SANS TUILE sort
    d'`observeBattle` et arrive dans `decisionView` avec `visualId = pos = hp = owner = team =
    null` (mesure #366-r1) : le porteur sous 1140 arrive donc cote port avec un `OwnerComponent`
    a `team = player = None`, et le PREMIER etage qui les lit (`refresh_stat_modifier_effects` ->
    `UnitEffectStateView.is_turn_of_owner`) LEVE. On lit donc (team, player) sur un runner TEMOIN
    -- MEME seed, MEME board, MEMES unites, seed BC passe par le MEME pipeline mais SANS greffe --
    ou le porteur est sur le plateau et donc pleinement publie. Les ids d'entite coincident entre
    les deux runners (verifie a chaque run)."""
    from engine.runner.components import OwnerComponent
    bc_ctrl = LOGS / ("bc_ctrl_%s.json" % tag)
    CI.write_grafted_seed_bc(str(bc_ctrl), [])
    sf = LOGS / ("state_ctrl_%s.json" % tag)
    rid = build(seed, board_id, graft, foes, str(bc_ctrl), sf)
    try:
        st, _b = offline_state(capture(sid, rid))
        uid = carrier_id(st, foes)
        if uid is None:
            raise SystemExit("MONTAGE : porteur introuvable dans le runner TEMOIN")
        oc = st.get_entity(uid).get_component(OwnerComponent)
        return int(uid), (None if oc is None else oc.team), (None if oc is None else oc.player)
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 45)
        sf.unlink(missing_ok=True)


def repair_owner(st, uid: int, team, player) -> None:
    """Repose (team, player) du porteur hors plateau depuis le runner TEMOIN. N'ECRASE RIEN : ne
    remplit que ce que le canal a laisse a `None`."""
    from engine.runner.components import OwnerComponent
    e = st.get_entity(int(uid))
    oc = e.get_component(OwnerComponent) if e is not None else None
    if oc is None:
        e.add_component(OwnerComponent(team, player))
        return
    if oc.team is None:
        oc.team = team
    if oc.player is None:
        oc.player = player


def terms(st, uid: int) -> dict:
    """Les TERMES compares des deux cotes. `effects` = l'ensemble ENTIER des effets non consommes
    (type + remaining) : un effet qui apparaitrait EN TROP -- p.ex. un `*_Moving` qu'un port fautif
    poserait -- se verrait."""
    from engine.ai.state_bridge import _is_untargetable
    from engine.runner.components import PositionComponent, UnitComponent, get_unit_feet
    e = st.get_entity(int(uid))
    pc = e.get_component(PositionComponent) if e is not None else None
    uc = e.get_component(UnitComponent) if e is not None else None
    eff = getattr(st, "effects", None)
    rows = [] if eff is None else sorted(
        (int(x.effect_type), getattr(x, "remaining_turns", None))
        for x in (eff.by_unit.get(int(uid)) or []) if not x.consumed)
    return {"pos": None if pc is None else (pc.col, pc.row),
            "feet": sorted(get_unit_feet(st, int(uid)) or []),
            "alive": None if uc is None else bool(uc.alive),
            "effects": [list(r) for r in rows],
            "untargetable": bool(_is_untargetable(st, int(uid)))}


def cmp_terms(label, port, native, fails, keys=("pos", "feet", "alive", "effects", "untargetable")):
    for k in keys:
        if port[k] != native[k]:
            fails.append("%s %s : port=%r != natif=%r" % (label, k, port[k], native[k]))


# --------------------------------------------------------------------------- volet A (offline)

def volet_a(fails) -> None:
    from engine.entities.effect_type import EffectType
    from engine.entities.effects.aura_selectors import UNTARGETABLE_EFFECT_TYPES
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.dsl.event_trigger_type import EventTriggerType

    print("=== A -- OFFLINE : les quatre points de RE, re-derives ===")

    # A1. la table VERSIONNEE du build : combien de `*_Moving`, et lesquels ?
    build_id = (ROOT / "data" / "symbols" / "CURRENT").read_text(encoding="utf-8").strip()
    enums = ROOT / "data" / "symbols" / build_id / "frida" / "enums.tsv"
    moving, stormboyz, telein = [], [], []
    for line in enums.read_text(encoding="utf-8").splitlines():
        f = line.split("\t")
        if f[0] != "IdunBattle.Entities.Enum.EffectType" or len(f) < 2:
            continue
        vals = f[1].split(",")
        moving = [v for v in vals if "_Moving" in v]
        stormboyz = [v for v in vals if "Stormboyz" in v]
        telein = [v for v in vals if "TeleportingIn" in v]
        break
    print("  A1 build=%s  EffectType._Moving      = %s" % (build_id, moving))
    print("     EffectType.*TeleportingIn = %s" % (telein,))
    print("     EffectType.Stormboyz*     = %s" % (stormboyz,))
    if len(moving) != 3 or any("Stormboyz" in v for v in moving):
        fails.append("A1 : la table du build ne donne plus EXACTEMENT trois `*_Moving` sans "
                     "Stormboyz -> %r" % (moving,))
    if len(telein) != 4:
        fails.append("A1 : la famille TeleportingIn n'a plus 4 membres -> %r" % (telein,))

    # A2. le registre du port : les QUATRE triggers, leurs events, et AUCUN `*_Moving` Stormboyz
    got = EFFECT_TRIGGERS.get(TELEPORTING_IN) or []
    names = [c.__name__ for c in got]
    events = [c.event_id for c in got]
    print("  A2 EFFECT_TRIGGERS[%d] = %s" % (TELEPORTING_IN, names))
    print("     events                = %s (attendu %s)"
          % (events, [int(EventTriggerType.UnitAfterMove), int(EventTriggerType.PreUnitAbility),
                      int(EventTriggerType.UnitFinishedTurn), int(EventTriggerType.PreUnitMove)]))
    if events != [int(EventTriggerType.UnitAfterMove), int(EventTriggerType.PreUnitAbility),
                  int(EventTriggerType.UnitFinishedTurn), int(EventTriggerType.PreUnitMove)]:
        fails.append("A2 : les quatre `Triggered()` de la base ne sont pas au registre -> %r"
                     % (events,))

    # A3. la branche `Nothing()` : `MOVING_EFFECT_TYPE` de la specialisation
    t4 = [c for c in got if c.event_id == int(EventTriggerType.PreUnitMove)]
    mv = getattr(t4[0], "MOVING_EFFECT_TYPE", "?") if t4 else "?"
    print("  A3 T4.MOVING_EFFECT_TYPE = %r (attendu None -> branche Nothing())" % (mv,))
    if mv is not None:
        fails.append("A3 : T4 de 1140 declare un `*_Moving` (%r) -- le corps natif est "
                     "`xor eax,eax ; ret` = Nullable VIDE" % (mv,))

    # A4. le domaine de non-ciblabilite (UntargetableEffect)
    print("  A4 UNTARGETABLE_EFFECT_TYPES = %r" % (UNTARGETABLE_EFFECT_TYPES,))
    if TELEPORTING_IN not in UNTARGETABLE_EFFECT_TYPES:
        fails.append("A4 : 1140 absent du domaine `UntargetableEffect` alors que la classe native "
                     "en derive (`ApplyInternal` -> UnitFlagsComponent.Add(0x11))")
    for other in (int(EffectType.FearOfTheUnseen_TeleportingIn),
                  int(EffectType.TitanhammerSquad_TeleportingIn)):
        if other in UNTARGETABLE_EFFECT_TYPES:
            fails.append("A4 : %d inscrit au domaine sans sa tranche (#448-r2c/d)" % other)
    print()


# --------------------------------------------------------------------------- volets LIVE

def native_movable(sid, rid, uid):
    r = rpc(sid, "aiMovableTiles", {"runnerId": rid, "unitId": uid}, 120)
    for u in (r.get("units") or []):
        if int(u.get("unitId")) == int(uid):
            return [(int(t["col"]), int(t["row"])) for t in (u.get("tiles") or [])
                    if t.get("col") is not None]
    return [(int(t["col"]), int(t["row"])) for t in (r.get("unionTiles") or [])
            if t.get("col") is not None]


def cascade(sid, rid, action, t=180):
    """`applyAction` + la cascade d'events DECODEE (lignes lisibles).

    ⚠ Les events sont PAR ACTION (`result.actions[i].events`, cf.
    `frida/hooks/features/ai-step/internals.ts` -- la frame de capture est poussee autour de
    l'`invoke` d'`ApplyAiMessage`), PAS a la racine du resultat. Lire `r["events"]` rend
    silencieusement `[]` : un scan de cascade y serait VIDE, donc VERT sans rien mesurer."""
    r = rpc(sid, "applyAction", {"runnerId": rid, "action": action}, t)
    evs = []
    for a in (r.get("actions") or []):
        evs.extend(a.get("events") or [])
    try:
        lines = stream_events.decode_lines(evs, max_lines=600)
    except Exception as e:                                   # table d'enums indisponible
        lines = ["<<decodage impossible: %s: %s>>" % (type(e).__name__, e)]
    return r, evs, lines


def run_montage(sid, board_id, seed, graft, foes, fails, mutate_hastile=False) -> dict:
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.components import set_unit_feet
    from engine.runner.messages import MoveUnitMessage
    from engine.runner.operations.triggers.dispatch.turn import unit_finished_turn_triggers
    from engine.runner.operations.turnflow import FinishUnitTurnOperation
    from engine.runner.runner import Runner
    from engine.runner.snapshot import clear_ability_states_cache

    tag = "%s_%s" % (graft, board_id)
    out: dict = {"board": board_id, "seed": seed, "graft": graft, "foes": list(foes),
                 "fails": fails}
    print("=== montage board=%s seed=%s greffon=%s ===" % (board_id, seed, graft))
    LOGS.mkdir(parents=True, exist_ok=True)
    bc = LOGS / ("bc_%s.json" % tag)
    _p, reports = CI.write_grafted_seed_bc(str(bc), ["%s:%s" % (graft, ABILITY)])
    print("  [graft] %s" % json.dumps(reports[0]))
    out["graftReport"] = reports[0]
    ctrl_uid, team, player = control_owner(sid, board_id, seed, graft, foes, tag)
    print("  [TEMOIN] porteur u%s team=%r player=%r (canal de repli de l'unite hors plateau)"
          % (ctrl_uid, team, player))

    # ---------------- runner 1 : E1 + T2-VIDE + CONFRONT-MOVE ----------------
    sf = LOGS / ("state_%s_move.json" % tag)
    rid = build(seed, board_id, graft, foes, str(bc), sf)
    try:
        clear_ability_states_cache()
        st, board = offline_state(capture(sid, rid))
        uid = carrier_id(st, foes)
        if uid is None:
            raise SystemExit("MONTAGE : greffon introuvable dans l'etat charge")
        if uid != ctrl_uid:
            fails.append("MONTAGE : id d'entite DIFFERENT entre temoin (%s) et greffe (%s) -- "
                         "le repli (team, player) ne porte plus sur la meme unite"
                         % (ctrl_uid, uid))
        repair_owner(st, uid, team, player)
        t0 = terms(st, uid)
        print("  [E1] porteur u%d : %s" % (uid, json.dumps(t0)))
        if t0["pos"] is not None or t0["feet"]:
            raise SystemExit("MONTAGE : le porteur n'est PAS hors plateau -- la greffe n'a pas "
                             "mordu (ou un effet de rang superieur gagne l'ordre des tests)")
        if [TELEPORTING_IN, 2] not in t0["effects"]:
            raise SystemExit("MONTAGE : 1140 absent ou `remaining` != 2 -> %r" % (t0["effects"],))
        if not t0["untargetable"]:
            fails.append("E1 : le porteur sous 1140 est CIBLABLE cote port "
                         "(UntargetableEffect$$ApplyInternal pose UnitFlag 0x11)")
        # E1b -- OBSERVATION (pas une assertion) : le porteur sous 1140 porte-t-il DEJA ses
        # owner-effects ? Ils ne peuvent venir que de la CAPTURE NATIVE (`decisionView.effects`) :
        # `snapshot.load_state` ne seede que les owner-effects d'ABILITY, et
        # `_seed_trait_owner_effects` n'est appele que par `initialize_deferred_actor_abilities`,
        # que cette tranche n'accroche PAS. Si la liste porte autre chose que 1140, le regime
        # << passives DEFERREES >> de 1035 n'existe pas pour 1140 -> pas de mixin d'atterrissage.
        others = [r for r in t0["effects"] if r[0] != TELEPORTING_IN]
        print("  [E1b] owner-effects DEJA presents sur le porteur sous 1140 (canal NATIF) = %r "
              "-> regime << passives deferrees >> %s" % (others, "ABSENT" if others else "indecis"))
        out["carrier"], out["start"], out["startOthers"] = int(uid), t0, others

        # -------- T2-VIDE : aucun cast n'est legal depuis « nulle part »
        tg = rpc(sid, "abilityTargets", {"runnerId": rid, "unitId": uid}, 90) or {}
        here = [t.get("targetId") for u in (tg.get("units") or [])
                for a in (u.get("abilities") or []) for t in (a.get("fromHere") or [])]
        print("  [T2-VIDE] abilityTargets.fromHere du porteur hors plateau = %r" % (here,))
        out["fromHere"] = here
        if here:
            fails.append("T2-VIDE : le natif propose %d cible(s) a une unite hors plateau -- la "
                         "lecture << T2 non exercable >> tombe, il faut confronter T2" % len(here))

        # -------- CONFRONT-MOVE : T1 + la branche Nothing() de T4
        legal = native_movable(sid, rid, uid)
        if not legal:
            raise SystemExit("MONTAGE : `aiMovableTiles` VIDE pour le porteur hors plateau")
        dest = sorted(legal)[len(legal) // 2]
        print("  [CONFRONT-MOVE] pool natif=%d tuiles, destination choisie=%r" % (len(legal), dest))
        out["poolSize"], out["dest"] = len(legal), tuple(dest)

        # (a) PORT -- le pas decoupe : Operation puis vecteur after-move. C'est la seule fenetre ou
        #     un `*_Moving` pose par T4 serait visible (son propre trigger le retire au vecteur).
        from engine.runner.events import EventBus
        from engine.runner.operations.movement import MoveUnitOperation
        from engine.runner.operations.triggers import after_move_triggers
        st_split, _b = offline_state(capture(sid, rid))
        repair_owner(st_split, uid, team, player)
        MoveUnitOperation(int(uid), tuple(dest)).execute(st_split, EventBus())
        mid = sorted(int(x.effect_type) for x in (st_split.effects.by_unit.get(int(uid)) or [])
                     if not x.consumed)
        after_move_triggers(st_split, int(uid))
        end = sorted(int(x.effect_type) for x in (st_split.effects.by_unit.get(int(uid)) or [])
                     if not x.consumed)
        print("  [E-MOVING] port : PENDANT le pas=%r  APRES le vecteur after-move=%r" % (mid, end))
        out["moveMid"], out["moveEnd"] = mid, end
        if TELEPORTING_IN not in mid:
            fails.append("E-MOVING : 1140 deja retire PENDANT le pas -- T1 fire trop tot")
        if any(e not in (TELEPORTING_IN,) for e in mid if e in (1036, 1241, 1574)):
            fails.append("E-MOVING : un `*_Moving` a ete pose PENDANT le pas (%r) -- la branche "
                         "`Nothing()` de T4 n'est pas prise" % (mid,))
        if TELEPORTING_IN in end:
            fails.append("E-MOVING : 1140 SURVIT au pas cote port -- T1 n'a pas retire")

        # (b) PORT -- le pas COMPLET par la voie `Runner.apply`
        st_port, _b2 = offline_state(capture(sid, rid))
        repair_owner(st_port, uid, team, player)
        Runner(st_port).install_default_handlers(20).apply(MoveUnitMessage(int(uid), tuple(dest)))
        p_move = terms(st_port, uid)

        # (c) NATIF -- le MEME pas, et sa cascade
        act, evs, lines = cascade(sid, rid, {"kind": "move", "unitId": int(uid),
                                             "to": {"col": int(dest[0]), "row": int(dest[1])}})
        st_nat, _b3 = offline_state(capture(sid, rid))
        repair_owner(st_nat, uid, team, player)
        n_move = terms(st_nat, uid)
        print("  [CONFRONT-MOVE] port  = %s" % json.dumps(p_move))
        print("  [CONFRONT-MOVE] natif = %s" % json.dumps(n_move))
        # LA PREUVE LIVE de la branche `Nothing()` : la cascade du pas NATIF ne doit porter AUCUN
        # groupe `Effect_Refresh <<*_Moving>>`. Le TEMOIN POSITIF est la tranche 1 (mesure #448-r2,
        # `eldarAutarch`) : le MEME scan y remonte deux `<<TeleportStrike_Moving>>` encadrant le
        # `ChangePosition`. Une cascade VIDE ne prouverait rien -> on l'exige non vide.
        moving_hits = [ln for ln in lines if "Moving" in ln]
        refresh_hits = [ln for ln in lines if "Effect_Refresh" in ln]
        print("  [CONFRONT-MOVE] cascade natif : %d events, %d Effect_Refresh, lignes 'Moving'=%r"
              % (len(evs), len(refresh_hits), moving_hits))
        for ln in refresh_hits:
            print("  [CONFRONT-MOVE]   %s" % ln.strip())
        if not evs:
            fails.append("CONFRONT-MOVE : cascade NATIVE VIDE -- le scan `*_Moving` ne mesure "
                         "RIEN (canal `actions[].events`)")
        if moving_hits:
            fails.append("CONFRONT-MOVE : la cascade NATIVE porte un `*_Moving` (%r) -- la branche "
                         "`Nothing()` de T4 serait FAUSSE" % (moving_hits,))
        out["portMove"], out["nativeMove"] = p_move, n_move
        out["cascadeCount"], out["movingHits"] = len(evs), moving_hits
        out["refreshLines"] = [ln.strip() for ln in refresh_hits]
        out["moveMutated"] = bool((act.get("actions") or [{}])[0].get("mutated"))
        if not act.get("ok"):
            fails.append("CONFRONT-MOVE : `applyAction move` REFUSE (montage) : %r" % (act,))
        if not out["moveMutated"]:
            fails.append("CONFRONT-MOVE : le move live n'a RIEN mute (H55, no-op silencieux) -- "
                         "montage, pas mesure : %r" % (act,))
        if n_move["pos"] != tuple(dest):
            # `...StormboyzStrike_MissAbility` (NON PORTEE, residu case-448-r1) : 20 % de chance de
            # `OverrideUnitMovementTarget(Owner, PickRandomly(CanAddUnit(AdjacentTiles(<dest>)),1))`.
            # On ne SAUTE pas le terme POSITION -- on l'evalue sous la forme NATIVE : une deviation
            # doit etre ADJACENTE a la destination demandee. Autre chose = pas le Miss.
            import hexgeo
            d = (None if n_move["pos"] is None
                 else hexgeo.distance(tuple(n_move["pos"]), tuple(dest)))
            out["missDistance"] = d
            print("  [CONFRONT-MOVE] /!\\ natif en %r au lieu de %r (distance=%r) -- signature du "
                  "`_MissAbility` (20 %%, NON PORTE). Les autres termes restent compares."
                  % (n_move["pos"], tuple(dest), d))
            if d != 1:
                fails.append("CONFRONT-MOVE : le natif a atterri en %r, a distance %r de la "
                             "destination %r -- ce n'est PAS la signature du `_MissAbility` "
                             "(AdjacentTiles), c'est un desaccord de port"
                             % (n_move["pos"], d, tuple(dest)))
            cmp_terms("CONFRONT-MOVE", p_move, n_move, fails, keys=("alive", "effects",
                                                                    "untargetable"))
        else:
            out["missDistance"] = 0
            cmp_terms("CONFRONT-MOVE", p_move, n_move, fails)
        if any(r[0] == TELEPORTING_IN for r in n_move["effects"]):
            fails.append("CONFRONT-MOVE : le NATIF garde 1140 apres le pas -- la mesure ne "
                         "discrimine RIEN")
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 45)
        sf.unlink(missing_ok=True)

    # ---------------- runner 2 : CONFRONT-FINISH, PAR ETAGES ----------------
    sf = LOGS / ("state_%s_finish.json" % tag)
    rid = build(seed, board_id, graft, foes, str(bc), sf)
    try:
        clear_ability_states_cache()
        st, board = offline_state(capture(sid, rid))
        uid = carrier_id(st, foes)
        if uid is None:
            raise SystemExit("MONTAGE : greffon introuvable (finish)")
        repair_owner(st, uid, team, player)
        before = terms(st, uid)
        if before["pos"] is not None:
            raise SystemExit("MONTAGE : le porteur n'est pas hors plateau (finish)")

        # (a) PORT -- l'etage T3 SEUL, sur l'etat que le natif produit vraiment
        if mutate_hastile:
            from engine.runner.operations.triggers.loki import teleporting_in as TI
            TI.ATeleportingRemoveOnUnitFinishedTurn._event_gate = (
                lambda self, state, ev: True)                # NEUTRALISE le gate HasTile
        st_port, _b = offline_state(capture(sid, rid))
        repair_owner(st_port, uid, team, player)
        FinishUnitTurnOperation.execute(st_port, int(uid))
        p_a = terms(st_port, uid)
        print("  [FINISH-a] port (T3 seul, hors plateau) = %s" % json.dumps(p_a))
        out["finishBefore"], out["finishPortA"] = before, p_a
        if not any(r[0] == TELEPORTING_IN for r in p_a["effects"]):
            fails.append("FINISH-a : le port a RETIRE 1140 sur une unite HORS PLATEAU -- le gate "
                         "`HasTile(Owner)` de T3 est perdu (degradation PERMISSIVE)")
        if p_a["pos"] is not None:
            fails.append("FINISH-a : le port a repose l'unite -- il n'a pourtant PAS le Fallback")

        # (b) NATIF -- le meme geste ; le Fallback (NON PORTE) repose l'unite, puis T3 retire
        _act, _evs, _lines = cascade(sid, rid, {"kind": "finish", "unitId": int(uid)})
        st_nat, _b2 = offline_state(capture(sid, rid))
        repair_owner(st_nat, uid, team, player)
        n_fin = terms(st_nat, uid)
        print("  [FINISH-b] natif = %s" % json.dumps(n_fin))
        out["finishNative"] = n_fin
        if n_fin["pos"] is None:
            fails.append("FINISH-b : le natif a LAISSE l'unite hors plateau -- le Fallback n'a pas "
                         "fire, l'etage (c) n'a pas de sortie a injecter")
        if any(r[0] == TELEPORTING_IN for r in n_fin["effects"]):
            fails.append("FINISH-b : le natif GARDE 1140 apres le finish -- la lecture de T3 "
                         "(HasTile redevenu vrai) tombe")
        print("  [FINISH-b] ecart (a) vs (b) IMPUTE a `StormboyzStrike_FallbackAbility`, NON "
              "PORTEE (MEME `On(0x28)`, residu nomme -- case-448-r1 6)")

        # (c) l'ETAGE MANQUANT INJECTE : on continue l'etat du port en posant l'unite exactement ou
        #     le NATIF l'a posee (= la sortie observee du Fallback), puis on RE-EMET `On(0x28)`.
        #     `HasTile(Owner)` devient vrai -> T3 doit retirer, et les deux etats doivent coincider.
        if n_fin["pos"] is not None:
            set_unit_feet(st_port, int(uid), [tuple(n_fin["pos"])])
            unit_finished_turn_triggers(st_port, int(uid))
            p_c = terms(st_port, uid)
            print("  [FINISH-c] port apres injection du Fallback + On(0x%x) = %s"
                  % (int(EventTriggerType.UnitFinishedTurn), json.dumps(p_c)))
            out["finishPortC"] = p_c
            cmp_terms("FINISH-c", p_c, n_fin, fails)
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 45)
        sf.unlink(missing_ok=True)
    return out


#: Le sous-ensemble du PLAN que la GARDE pytest rejoue : les DEUX montages (base WALK et base FLY).
#: 6 runners au total -- un TEMOIN, un pour le MOUVEMENT et un pour le FINISH, par montage.
TEST_PLAN = list(PLAN)


def run(board_id: str, seed: int, graft: str, foes) -> dict:
    """UN montage complet, runners disposes en sortie. Porte d'entree des tests -- ils ne
    re-derivent RIEN, le montage est la source unique. `out["fails"]` porte les desaccords."""
    sid = _resolve_session()
    return run_montage(sid, board_id, int(seed), graft, list(foes), [])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--mutate-hastile", action="store_true")
    ap.add_argument("--board", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--graft", default=None)
    a = ap.parse_args()

    fails: list = []
    volet_a(fails)
    if a.offline:
        if fails:
            for f in fails:
                print("  - " + f)
            return 1
        print("OK (volet A seul)")
        return 0

    if a.mutate:
        from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
        EFFECT_TRIGGERS[TELEPORTING_IN] = []
        print("[MUTATE] EFFECT_TRIGGERS[%d] VIDE (= le port d'AVANT #448-r2b) -- DOIT rougir"
              % TELEPORTING_IN)

    plan = list(PLAN)
    if a.board or a.graft or a.seed:
        plan = [(a.board or "MC1_67", a.seed or 777, a.graft or "orksNob", ["ultraTitus"])]
    if a.mutate or a.mutate_hastile:
        plan = plan[:1]
    sid = _resolve_session()
    for board_id, seed, graft, foes in plan:
        run_montage(sid, board_id, seed, graft, foes, fails, mutate_hastile=a.mutate_hastile)

    print()
    mutated = a.mutate or a.mutate_hastile
    if fails:
        print("=== %d ECHEC(S) ===" % len(fails))
        for f in fails:
            print("  - " + f)
        return 0 if mutated else 1
    if mutated:
        print("=== CONTRE-EPREUVE VERTE = LE PROBE NE MESURE RIEN ===")
        return 1
    print("=== OK -- 1140 : les 4 triggers, la branche Nothing() et le gate HasTile confrontes ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
