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
  CONFRONT-MOVE  T1, T4 et l'ETAGE QUI RETIRE 1140. Meme etat de depart, meme pas rejoue OFFLINE
               (voie complete `MoveUnitOperation.execute`, PRNG aligne sur le natif) puis LIVE ;
               etats finaux compares TERME A TERME. La cascade d'events NATIVE est scannee : AUCUN
               groupe `*_Moving` ne doit y apparaitre -- c'est la preuve LIVE de la branche
               `Nothing()`.
  CONFRONT-FINISH  T3, PAR ETAGES -- c'est le coeur de la tranche. PRNG aligne.
               (a) port : `FinishUnitTurnOperation` sur le porteur HORS PLATEAU -> le Fallback
                   REPOSE l'unite, puis T3 (`HasTile` devenu VRAI) retire 1140 ;
               (b) natif : `applyAction finish` -> le MEME enchainement ;
               (c) les deux etats sont compares TERME A TERME (le PRNG aligne rend la tuile
                   d'atterrissage DETERMINISTE des deux cotes, deviation du Miss comprise).
  T3-GATE      le bras FAUX du gate `HasTile(Owner)`, EXERCE -- et il ne l'est plus par un geste
               depuis que le Fallback est porte (c'est lui qui repose l'unite AVANT que T3 soit
               evalue). On le rend mesurable en RETIRANT `StormboyzStrike_FallbackAbility` du
               registre le temps du volet : le vecteur `On(0x28)` est alors joue sur une unite qui
               reste HORS PLATEAU, et 1140 doit SURVIVRE. Volet PORT-SEUL, et c'est dit : le natif
               ne peut pas produire ce regime, le Fallback y est toujours la.
  T3-POSITIF   le bras VRAI du meme gate, et le SEUL regime ou T3 decide encore SEUL : l'unite
               POSEE (la ou le NATIF l'a posee) et AUCUN mouvement dans le vecteur, donc pas de
               `On(0x1f)` et pas de Miss -> T3 doit retirer. Sans ce bras, vider
               `EFFECT_TRIGGERS[1140]` laisse le probe ENTIEREMENT VERT (mesure #448-r3-r1) : les
               quatre `Triggered()` propres de 1140 sont OBSERVATIONNELLEMENT INERTES sur le geste
               nominal, masques par le kit qui les entoure.
  E1b          OBSERVATION (montage `replace=False`, le porteur GARDE ses passifs) : le porteur
               sous 1140 a-t-il DEJA ses owner-effects passifs cote natif ? Si oui, le regime
               « passives DEFERREES » de 1035 n'existe PAS pour 1140 -> pas de
               `_TeleportStrikeLandingMixin` sur cette tranche.

⚠ CE QUI A CHANGE DEPUIS LA REDACTION DE 2026-08-01 (#448-r3-r1). Ce probe decrivait
`...StormboyzStrike_MissAbility` et `...StormboyzStrike_FallbackAbility` comme NON PORTEES et
assertionnait le port SANS elles. `9fc0deca` (#448-r1, 2026-08-03) les a PORTEES toutes les deux :

  * le Miss ecoute `On(0x1f = PreUnitMove)` et fait `RemoveEffect(Caster, 0x474)` **HORS du `If`**
    -> 1140 part AVANT le vecteur `On(0x04)`, donc T1 n'a plus rien a retirer ;
  * le Fallback ecoute `On(0x28 = UnitFinishedTurn)` et REPOSE l'unite (`MoveUnitBehaviour`)
    -> quand T3 est evalue (les abilities passent avant les effets dans
    `dispatch/core.py::evaluate_trigger_operation`), `HasTile(Owner)` est deja VRAI et T3 retire.

Les trois assertions qui rougissaient decrivaient donc le port d'AVANT. Le natif, lui, n'a pas
bouge : c'est exactement ce que ce probe ecrivait deja de LUI.

⚠ ET LE PROBE LUI-MEME NE MESURAIT RIEN EN CLI. `UnitContext.passive_abilities` n'est seede que si
le TRANSPORT RPC AMBIANT est lie (`snapshot.bind_live_rpc`, #363) ; sans lui,
`collect_triggered_abilities` retombe sur `gameconfig.unit(<greffon>).passiveAbilities`, qui ne
porte evidemment PAS l'ability GREFFEE -- aucune des trois classes de `StormboyzStrike` n'etait
montee cote port, et le probe rendait VERT en comparant un port AMPUTE au natif. La suite pytest,
elle, lie l'ambiant (`tests/conftest.py::live_session`), d'ou l'ecart CLI/pytest. Le probe lie
desormais le transport lui-meme.

CONTRE-EPREUVES (VERT est le resultat SUSPECT) :
    --mutate           VIDE `EFFECT_TRIGGERS[1140]` (= le port d'avant cette tranche) -- ne mord
                       QUE par `T3-POSITIF` : sur le geste nominal les quatre triggers propres sont
                       masques par le kit (cf. ce volet)
    --mutate-hastile   NEUTRALISE le gate `HasTile` de T3 (rend `True`) -- mord sur T3-GATE
    --mutate-nograft   DELIE le transport ambiant (= le probe d'avant #448-r3-r1) : la greffe
                       n'est plus montee cote port, et le volet E-PORTED doit rougir

ASCII only. Usage (depuis scripts/python) :
    python probe_448_r2b_stormboyz_teleporting_in.py
    python probe_448_r2b_stormboyz_teleporting_in.py --offline
    python probe_448_r2b_stormboyz_teleporting_in.py --mutate
    python probe_448_r2b_stormboyz_teleporting_in.py --mutate-hastile
    python probe_448_r2b_stormboyz_teleporting_in.py --mutate-nograft
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from contextlib import contextmanager
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


def bind_ambient(sid):
    """LIE LE TRANSPORT RPC AMBIANT (`snapshot.bind_live_rpc`, #363) pour la duree du probe.

    SANS LUI CE PROBE NE MESURE RIEN, et c'est mesure (#448-r3-r1) : `load_state` ne seede
    `UnitContext.passive_abilities` (canal `unitAbilityStates`) que si un transport est lie ; a
    defaut, `dispatch/core.py::collect_triggered_abilities` retombe sur
    `gameconfig.unit(<greffon>).passiveAbilities` -- qui ne porte PAS l'ability GREFFEE. Les TROIS
    classes de `StormboyzStrike` ne sont alors pas montees cote port, et le probe compare un port
    AMPUTE au natif : VERT sans rien exercer. La suite pytest lie l'ambiant par
    `tests/conftest.py::live_session`, d'ou l'ecart CLI/pytest qui a masque trois assertions
    perimees.

    Signature attendue par le foyer : `rpc(method, body=None, timeout=...)` -> resultat DEBALLE."""
    from engine.runner.snapshot import bind_live_rpc

    def _ambient(method: str, body=None, timeout: float = 60):
        return rpc(sid, method, body if body is not None else {}, timeout)
    return bind_live_rpc(_ambient)


def align_rng(sid, rid, st) -> dict:
    """Pose sur l'etat OFFLINE le flux Mersenne Twister que le natif s'apprete a consommer
    (`dumpRng`), exactement comme `tests/.../test_448_r1_stormboyz_port_live.py`.

    POURQUOI C'EST OBLIGATOIRE ICI. `...StormboyzStrike_MissAbility` tire `Maybe(chance = 20)` a
    CHAQUE mouvement du porteur sous 1140, et devie alors la destination d'un hex
    (`PickRandomly(CanAddUnit(AdjacentTiles(<dest>)), 1)`, un tirage de plus). Sans alignement, une
    tuile d'arrivee differente est INDISCERNABLE d'un desaccord de port -- et c'est exactement le
    seuil mou (<< distance 0 ou 1 >>) que ce probe portait avant #448-r3-r1. Avec alignement, la
    position est DETERMINISTE des deux cotes et se compare a l'identique."""
    from engine.runner.prng import IntBasedMersenneTwister
    mt = rpc(sid, "dumpRng", {"runnerId": rid}, 30) or {}
    if not mt.get("mt"):
        raise SystemExit("MONTAGE : `dumpRng` indisponible -- sans alignement PRNG la deviation du "
                         "`_MissAbility` rendrait toute comparaison de position ininterpretable")
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(mt["mt"]), int(mt["mti"])
    st.rng = rng
    return mt


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
    from engine.runner.abilities.targeting import is_targetable as _flag_targetable
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
            "untargetable": bool(_is_untargetable(st, int(uid))),
            # #433-r3-r2-r1 -- LE CANAL FLAG, et c'est la SEULE confrontation directe du fix.
            # Cote NATIF cet etat est RECONSTRUIT d'une capture, donc son `UnitFlagsComponent` est
            # SEEDE par `combatSnapshot.units[].unitFlags` -- c'est-a-dire par le jeu lui-meme.
            # Cote PORT il est pose par `AddEffectOperation._apply_untargetable_flag`. Comparer les
            # deux, c'est donc confronter MON `UnitFlagsComponent$$Add(0x11)` a celui du natif, la
            # ou la cle `untargetable` ci-dessus n'interroge que les EFFETS des deux cotes.
            "flagUntargetable": (None if e is None else not _flag_targetable(st, int(uid)))}


def cmp_terms(label, port, native, fails,
              keys=("pos", "feet", "alive", "effects", "untargetable", "flagUntargetable")):
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


def ported_stormboyz_classes(state, uid: int) -> list:
    """Les classes de triggered-ability que le PORT a REELLEMENT montees sur le porteur.

    C'est l'ANTI-TAUTOLOGIE du probe (#448-r3-r1) : toutes les assertions ci-dessous sont des
    NEGATIFS (<< 1140 n'est plus la >>, << aucun `*_Moving` >>) et un port qui n'aurait monte AUCUNE
    des trois classes de `StormboyzStrike` les rendrait TOUTES vertes. On exige donc d'abord que le
    registre ait mordu, en le lisant sur l'etat CHARGE et non sur le gameconfig."""
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    want = int(TriggeredAbilityType.StormboyzStrike)
    return sorted({type(t).__name__ for t in collect_triggered_abilities(state)
                   if int(getattr(t, "owner_id", -1) or -1) == int(uid)
                   and getattr(t, "TRIGGERED_ABILITY_ID", None) == want})


def t3_matches_off_board(state, uid: int) -> bool:
    """`matches()` de T3 (`StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn`) sur l'etat HORS
    PLATEAU -- l'ETAGE SEUL, sans passer par un vecteur.

    C'est la lecture la plus directe du gate `IdunBattleLogic.Entities.DSLTriggers$$HasTile(Owner)`
    du 3e `Triggered()` d'`ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` : l'unite sous
    1140 n'occupe aucune tuile (`...StormboyzStrike_TeleportAbility$$CreateBehaviour` a appele
    `RemoveUnitFromItsTiles`), donc le conjoint est FAUX et le trigger ne doit PAS matcher."""
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.loki.teleporting_in import (
        StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn as T3)
    from engine.dsl.event_trigger_type import EventTriggerType
    ev = TriggerEvent(EventTriggerType.UnitFinishedTurn, int(uid), int(uid),
                      ranged=False, profile=None)
    return bool(T3(int(uid)).matches(state, ev))


@contextmanager
def without_fallback():
    """Retire `...StormboyzStrike_FallbackAbility` du registre le temps du bloc.

    Le registre `ABILITY_TRIGGERS["StormboyzStrike"]` est un etat de MODULE, donc GLOBAL au
    processus : il est restaure en sortie, sans quoi la mutation survivrait au montage suivant (la
    meme faute que #448-r3 a mesuree sur `EFFECT_TRIGGERS`).

    CE QUE CE RETRAIT ISOLE. Le Fallback est la seule chose qui redonne une tuile au porteur pendant
    le vecteur `On(0x28)` -- et son `MoveUnitBehaviour` re-emet `On(0x1f)`, donc il fait AUSSI firer
    `...StormboyzStrike_MissAbility`, qui retire 1140 par un canal REDONDANT avec T3. Sans lui, les
    deux bras du gate `HasTile(Owner)` redeviennent observables : FAUX si l'unite est hors plateau,
    VRAI si on l'y a posee."""
    from engine.runner.operations.triggers.dispatch import registry as REG
    from engine.runner.operations.triggers.loki.stormboyz_strike import (
        StormboyzStrikeFallbackAbility as FB)
    saved = list(REG.ABILITY_TRIGGERS.get("StormboyzStrike") or ())
    kept = [c for c in saved if c is not FB]
    if len(kept) == len(saved):
        raise SystemExit("T3-GATE : `StormboyzStrikeFallbackAbility` absente du registre -- le "
                         "volet n'isolerait rien")
    REG.ABILITY_TRIGGERS["StormboyzStrike"] = kept
    try:
        yield
    finally:
        REG.ABILITY_TRIGGERS["StormboyzStrike"] = saved


def play_finish_without_fallback(state, uid: int) -> dict:
    """Le vecteur `On(0x28 = UnitFinishedTurn)` joue SANS le Fallback, sur l'unite HORS PLATEAU."""
    from engine.runner.operations.turnflow import FinishUnitTurnOperation
    with without_fallback():
        FinishUnitTurnOperation.execute(state, int(uid))
    return terms(state, int(uid))


#: Ce que la GREFFE monte, cote port. Le builder natif
#: `AbilitiesDatabase.u003Cu003Ec$$u003CInitializeTriggeredAbilitiesu003Eb__28_134` construit une
#: `List` de TROIS instances pour le seul `TriggeredAbilityType.StormboyzStrike` (0x475) -- greffer
#: le passif les monte donc toutes les trois d'un coup (case-448-r1 §1).
STORMBOYZ_PORTED = ["StormboyzStrikeFallbackAbility", "StormboyzStrikeMissAbility",
                    "StormboyzStrikeTeleportAbility"]


def run_montage(sid, board_id, seed, graft, foes, fails, mutate_hastile=False) -> dict:
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.dispatch.turn import unit_finished_turn_triggers
    from engine.runner.operations.turnflow import FinishUnitTurnOperation
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

        # -------- E-PORTED : le registre a-t-il MORDU ? (anti-tautologie, cf. la fabrique)
        ported = ported_stormboyz_classes(st, uid)
        print("  [E-PORTED] classes StormboyzStrike montees cote PORT = %r" % (ported,))
        out["ported"] = ported
        if ported != STORMBOYZ_PORTED:
            fails.append("E-PORTED : le port n'a monte que %r au lieu de %r -- les assertions "
                         "NEGATIVES qui suivent passeraient sans rien exercer (transport ambiant "
                         "non lie ? cf. `bind_ambient`)" % (ported, STORMBOYZ_PORTED))

        # -------- CONFRONT-MOVE : T4 (branche Nothing()) et l'ETAGE qui retire 1140
        legal = native_movable(sid, rid, uid)
        if not legal:
            raise SystemExit("MONTAGE : `aiMovableTiles` VIDE pour le porteur hors plateau")
        dest = sorted(legal)[len(legal) // 2]
        print("  [CONFRONT-MOVE] pool natif=%d tuiles, destination choisie=%r" % (len(legal), dest))
        out["poolSize"], out["dest"] = len(legal), tuple(dest)

        # (a) PORT -- le pas joue UNE SEULE FOIS, les DEUX etats intermediaires captes PAR
        #     INSTRUMENTATION (foyer #448-r3). PRNG aligne : le `Maybe(20)` du Miss et son
        #     `PickRandomly` doivent tomber comme au natif, sinon la position n'est pas comparable.
        #     ⚠ #448-r3 : le decoupage d'avant (`Operation` puis vecteur) ne montrait plus rien --
        #     `9767a8e4` a replie le vecteur DANS l'Operation, donc `mid` etait pris APRES un pas
        #     deja complet. Le controle NEGATIF ci-dessous (aucun `*_Moving` pose, branche
        #     `Nothing()` de T4) en devenait INERTE : il aurait passe meme si T4 posait.
        import probe_448_r3_move_step_atomicity as R3
        st_port, _b2 = offline_state(capture(sid, rid))
        repair_owner(st_port, uid, team, player)
        align_rng(sid, rid, st_port)
        r_step = R3.play_step_instrumented(st_port, int(uid), dest)
        if len(r_step["calls"]) != 1:
            fails.append("E-MOVING : le vecteur after-move a ete joue %d fois pour UN pas "
                         "(attendu 1)" % len(r_step["calls"]))
        if len(r_step["pre"]) != 1:
            fails.append("E-PREMOVE : le vecteur pre-move a ete joue %d fois pour UN pas "
                         "(attendu 1 -- la relance apres deviation porte `skipPreMoveTriggers`)"
                         % len(r_step["pre"]))
        pre = r_step["pre"][0] if r_step["pre"] else {"effects": [], "after": [], "out": []}
        mid = r_step["calls"][0]["effects"] if r_step["calls"] else []
        end = r_step["end"]
        miss = [o for o in (pre.get("out") or []) if isinstance(o, dict) and o.get("class") == "Miss"]
        print("  [E-PREMOVE] port : AVANT On(0x1f)=%r  APRES On(0x1f)=%r  Miss=%r"
              % (pre["effects"], pre["after"], miss))
        print("  [E-MOVING] port : a l'entree du vecteur after-move=%r  APRES le pas=%r"
              % (mid, end))
        out["moveMid"], out["moveEnd"] = mid, end
        out["premoveBefore"], out["premoveAfter"] = pre["effects"], pre["after"]
        out["missResult"] = miss[0] if miss else None
        # L'ETAGE, pas seulement l'etat final : 1140 est LA a l'entree d'`On(0x1f)` et PARTI a sa
        # sortie -- c'est `...StormboyzStrike_MissAbility` (`RemoveEffect(Caster, 0x474)`, HORS du
        # `If`) qui le retire, et T1 n'a plus rien a retirer au vecteur `On(0x04)`.
        if TELEPORTING_IN not in pre["effects"]:
            fails.append("E-PREMOVE : 1140 absent AVANT le vecteur `On(0x1f)` -- le montage ne pose "
                         "pas l'etat de depart, rien n'est mesure")
        if TELEPORTING_IN in pre["after"]:
            fails.append("E-PREMOVE : 1140 SURVIT au vecteur `On(0x1f)` -- le `RemoveEffect(Caster, "
                         "0x474)` de `...StormboyzStrike_MissAbility` n'a pas joue")
        if not miss:
            fails.append("E-PREMOVE : `...StormboyzStrike_MissAbility` n'a rien RENDU sur `On(0x1f)` "
                         "-- le retrait de 1140 n'est attribuable a aucun etage")
        if TELEPORTING_IN in mid:
            fails.append("E-MOVING : 1140 encore la a l'entree du vecteur after-move -- il aurait "
                         "du partir au `On(0x1f)`")
        if [e for e in mid if e in (1036, 1241, 1574)]:
            fails.append("E-MOVING : un `*_Moving` a ete pose PENDANT le pas (%r) -- la branche "
                         "`Nothing()` de T4 n'est pas prise" % (mid,))
        if TELEPORTING_IN in end:
            fails.append("E-MOVING : 1140 SURVIT au pas cote port")
        p_move = terms(st_port, uid)

        # (b) NATIF -- le MEME pas, et sa cascade
        act, evs, lines = cascade(sid, rid, {"kind": "move", "unitId": int(uid),
                                             "to": {"col": int(dest[0]), "row": int(dest[1])}})
        st_nat, _b3 = offline_state(capture(sid, rid))
        repair_owner(st_nat, uid, team, player)
        n_move = terms(st_nat, uid)
        print("  [CONFRONT-MOVE] port  = %s" % json.dumps(p_move))
        print("  [CONFRONT-MOVE] natif = %s" % json.dumps(n_move))
        # (c) LE TEMOIN NATIF D'ETAGE : le retrait de 1140 precede-t-il le `ChangePosition` ? C'est
        # la signature d'un retrait au `On(0x1f = PreUnitMove)` (le Miss) et non au `On(0x04)` (T1).
        spans = R3.cascade_effect_spans(evs)
        cp = R3.cascade_change_position(evs)
        span = spans.get("StormboyzStrike_TeleportingIn")
        out["nativeRemoveIdx"] = (None if not (span and span["rem"]) else min(span["rem"]))
        out["nativeChangePosIdx"] = cp
        print("  [CONFRONT-MOVE] cascade natif : retrait de 1140 aux index %r, ChangePosition a %r"
              % ((span or {}).get("rem"), cp))
        if not (span and span["rem"]):
            fails.append("CONFRONT-MOVE : la cascade NATIVE ne porte AUCUN retrait de 1140 -- "
                         "l'etage natif n'est pas identifie")
        elif cp is not None and min(span["rem"]) > cp:
            fails.append("CONFRONT-MOVE : le natif retire 1140 APRES le ChangePosition (rem=%r, "
                         "cp=%d) -- ce serait T1 (`On(0x04)`) et non le `_MissAbility` (`On(0x1f)`)"
                         % (span["rem"], cp))
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
        # LE TERME POSITION SE COMPARE A L'IDENTIQUE, ET C'EST L'ALIGNEMENT PRNG QUI LE PERMET.
        # `...StormboyzStrike_MissAbility` (PORTEE depuis #448-r1) tire `Maybe(chance = 20)` et, si
        # le hex est rate, `PickRandomly(CanAddUnit(AdjacentTiles(<dest>)), 1)`. Les deux cotes
        # partant du MEME etat MT, la deviation tombe des DEUX cotes ou d'AUCUN -- le seuil mou
        # << distance 0 ou 1 >> que ce probe portait avant #448-r3-r1 acceptait, lui, un vrai
        # desaccord de port du moment qu'il restait adjacent.
        import hexgeo
        d = (None if n_move["pos"] is None
             else hexgeo.distance(tuple(n_move["pos"]), tuple(dest)))
        out["missDistance"] = d
        if d:
            print("  [CONFRONT-MOVE] le natif a ete DEVIE de %r hex (signature `_MissAbility`) -- "
                  "le port, aligne sur le meme flux MT, doit l'avoir ete pareil" % (d,))
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

        # -------- T3-GATE : le bras FAUX du gate `HasTile(Owner)`, EXERCE.
        # Il ne l'est PLUS par un geste depuis que `...StormboyzStrike_FallbackAbility` est portee
        # (#448-r1) : elle ecoute le MEME `On(0x28)`, elle est une ABILITY donc elle passe AVANT les
        # effets dans `dispatch/core.py::evaluate_trigger_operation`, et son `MoveUnitBehaviour`
        # repose l'unite -- si bien que T3 voit toujours `HasTile` VRAI. On rend donc le bras faux
        # mesurable en RETIRANT le Fallback du registre le temps de ce volet.
        # VOLET PORT-SEUL, et c'est dit : le natif ne peut pas produire ce regime (le Fallback y est
        # toujours la). C'est une garde de NON-REGRESSION du gate, pas une confrontation.
        # DEUX lectures, pas une : (i) `matches()` de T3 sur l'etat hors plateau doit rendre FAUX --
        # l'etage SEUL, sans vecteur ; (ii) le vecteur `On(0x28)` prive de Fallback doit laisser
        # 1140 EN PLACE et l'unite HORS PLATEAU.
        if mutate_hastile:
            from engine.runner.operations.triggers.loki import teleporting_in as TI
            TI.ATeleportingRemoveOnUnitFinishedTurn._event_gate = (
                lambda self, state, ev: True)                # NEUTRALISE le gate HasTile
        st_gate, _bg = offline_state(capture(sid, rid))
        repair_owner(st_gate, uid, team, player)
        gate_ok = t3_matches_off_board(st_gate, int(uid))
        print("  [T3-GATE] T3.matches() sur le porteur HORS PLATEAU = %r (attendu False)" % gate_ok)
        out["t3MatchesOffBoard"] = gate_ok
        if gate_ok:
            fails.append("T3-GATE : `matches()` de T3 rend VRAI sur une unite HORS PLATEAU -- le "
                         "gate `HasTile(Owner)` est perdu (degradation PERMISSIVE)")
        g_after = play_finish_without_fallback(st_gate, int(uid))
        print("  [T3-GATE] vecteur On(0x%x) SANS le Fallback = %s"
              % (int(EventTriggerType.UnitFinishedTurn), json.dumps(g_after)))
        out["finishNoFallback"] = g_after
        if not any(r[0] == TELEPORTING_IN for r in g_after["effects"]):
            fails.append("T3-GATE : sans le Fallback, le port RETIRE quand meme 1140 sur une unite "
                         "HORS PLATEAU -- le gate `HasTile(Owner)` de T3 est perdu")
        if g_after["pos"] is not None:
            fails.append("T3-GATE : sans le Fallback, l'unite a ete REPOSEE -- un autre etage que "
                         "celui qu'on croit lui rend une tuile, la lecture du gate ne tient plus")

        # (a) PORT -- le vecteur `On(0x28)` NOMINAL : Fallback (repose) PUIS T3 (retire).
        #     PRNG aligne : le Fallback declenche un `MoveUnit`, donc `On(0x1f)`, donc le Miss et ses
        #     tirages -- sans alignement la tuile d'atterrissage n'est pas comparable.
        st_port, _b = offline_state(capture(sid, rid))
        repair_owner(st_port, uid, team, player)
        align_rng(sid, rid, st_port)
        FinishUnitTurnOperation.execute(st_port, int(uid))
        p_a = terms(st_port, uid)
        print("  [FINISH-a] port (Fallback puis T3) = %s" % json.dumps(p_a))
        out["finishBefore"], out["finishPortA"] = before, p_a
        if any(r[0] == TELEPORTING_IN for r in p_a["effects"]):
            fails.append("FINISH-a : le port GARDE 1140 apres le finish -- soit le Fallback n'a pas "
                         "repose l'unite, soit T3 n'a pas retire derriere lui")
        if p_a["pos"] is None:
            fails.append("FINISH-a : le port a LAISSE l'unite hors plateau -- le `MoveUnitBehaviour` "
                         "de `...StormboyzStrike_FallbackAbility` n'a pas joue")

        # (b) NATIF -- le meme geste : Fallback puis T3, exactement de meme.
        _act, _evs, _lines = cascade(sid, rid, {"kind": "finish", "unitId": int(uid)})
        st_nat, _b2 = offline_state(capture(sid, rid))
        repair_owner(st_nat, uid, team, player)
        n_fin = terms(st_nat, uid)
        print("  [FINISH-b] natif = %s" % json.dumps(n_fin))
        out["finishNative"] = n_fin
        if n_fin["pos"] is None:
            fails.append("FINISH-b : le natif a LAISSE l'unite hors plateau -- le Fallback n'a pas "
                         "fire, le volet ne confronte rien")
        if any(r[0] == TELEPORTING_IN for r in n_fin["effects"]):
            fails.append("FINISH-b : le natif GARDE 1140 apres le finish -- la lecture de T3 "
                         "(HasTile redevenu vrai) tombe")

        # (c) LES DEUX ETATS, TERME A TERME. Le PRNG etant aligne, la tuile d'atterrissage est
        #     deterministe des deux cotes -- deviation du `_MissAbility` comprise.
        cmp_terms("FINISH-c", p_a, n_fin, fails)

        # -------- T3-POSITIF : le bras VRAI du gate, et le SEUL regime ou T3 decide encore SEUL.
        # POURQUOI CE BRAS EXISTE (#448-r3-r1) : sur le geste NOMINAL, les quatre `Triggered()`
        # propres de 1140 sont devenus OBSERVATIONNELLEMENT INERTES, masques par le kit qui les
        # entoure -- T1 parce que `...StormboyzStrike_MissAbility` a deja retire l'effet au
        # `On(0x1f)` ; T2 parce qu'aucun cast n'est legal hors plateau ; T3 parce que le
        # `MoveUnitBehaviour` du Fallback re-emet `On(0x1f)`, donc le Miss retire la AUSSI ; T4
        # parce que sa branche est `Nothing()`. MESURE : vider `EFFECT_TRIGGERS[1140]` laissait le
        # probe ENTIEREMENT VERT -- une contre-epreuve PERIMEE PAR UN CANAL REDONDANT.
        # Le regime qui rend la main a T3 : l'unite POSEE (le `HasTile` vrai) et AUCUN mouvement
        # dans le vecteur, donc pas de `On(0x1f)` et pas de Miss. On reprend l'etat de T3-GATE (ou
        # l'unite est restee hors plateau avec son 1140) et on la pose la ou le NATIF l'a posee --
        # la sortie OBSERVEE du Fallback, pas une position inventee.
        if n_fin["pos"] is not None:
            from engine.runner.components import set_unit_feet
            set_unit_feet(st_gate, int(uid), [tuple(n_fin["pos"])])
            # SANS le Fallback ici AUSSI, et c'est LOAD-BEARING : son `MoveUnitBehaviour` re-emet
            # `On(0x1f)`, donc le Miss retirerait 1140 par un canal REDONDANT et le bras ne
            # mesurerait plus T3. Mesure : avec le Fallback, la contre-epreuve `--mutate` restait
            # VERTE et l'unite finissait meme sur une AUTRE tuile que celle qu'on venait de poser.
            with without_fallback():
                unit_finished_turn_triggers(st_gate, int(uid))
            p_pos = terms(st_gate, uid)
            print("  [T3-POSITIF] port, unite POSEE puis On(0x%x) re-emis = %s"
                  % (int(EventTriggerType.UnitFinishedTurn), json.dumps(p_pos)))
            out["finishT3Positive"] = p_pos
            if any(r[0] == TELEPORTING_IN for r in p_pos["effects"]):
                fails.append("T3-POSITIF : l'unite est POSEE (`HasTile` vrai) et aucun mouvement "
                             "n'a eu lieu, mais 1140 SURVIT -- T3 n'a pas retire")
    finally:
        rpc(sid, "disposeRunner", {"runnerId": rid}, 45)
        sf.unlink(missing_ok=True)
    return out


#: Le sous-ensemble du PLAN que la GARDE pytest rejoue : les DEUX montages (base WALK et base FLY).
#: 6 runners au total -- un TEMOIN, un pour le MOUVEMENT et un pour le FINISH, par montage.
TEST_PLAN = list(PLAN)


def run(board_id: str, seed: int, graft: str, foes) -> dict:
    """UN montage complet, runners disposes en sortie. Porte d'entree des tests -- ils ne
    re-derivent RIEN, le montage est la source unique. `out["fails"]` porte les desaccords.

    Le transport ambiant est deja lie par `tests/conftest.py::live_session` quand on vient de
    pytest ; `bind_ambient` est idempotent (il rend le precedent et on le restaure), donc l'appeler
    ici ne change rien pour la suite et rend le probe autonome hors harnais."""
    from engine.runner.snapshot import bind_live_rpc
    sid = _resolve_session()
    prev = bind_ambient(sid)
    try:
        return run_montage(sid, board_id, int(seed), graft, list(foes), [])
    finally:
        bind_live_rpc(prev)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--mutate", action="store_true")
    ap.add_argument("--mutate-hastile", action="store_true")
    ap.add_argument("--mutate-nograft", action="store_true",
                    help="ne LIE PAS le transport ambiant (= le probe d'avant #448-r3-r1) : la "
                         "greffe n'est plus montee cote port, E-PORTED DOIT rougir")
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
    if a.mutate or a.mutate_hastile or a.mutate_nograft:
        plan = plan[:1]
    sid = _resolve_session()
    # LE TRANSPORT AMBIANT EST CE QUI FAIT MONTER LA GREFFE COTE PORT (cf. `bind_ambient`). Sans
    # lui le probe compare un port AMPUTE au natif et rend VERT -- c'est le regime que
    # `--mutate-nograft` reproduit VOLONTAIREMENT pour montrer qu'`E-PORTED` le voit.
    from engine.runner.snapshot import bind_live_rpc
    prev = None if a.mutate_nograft else bind_ambient(sid)
    if a.mutate_nograft:
        print("[MUTATE] transport ambiant NON LIE (= le probe d'AVANT #448-r3-r1) -- DOIT rougir")
    try:
        for board_id, seed, graft, foes in plan:
            run_montage(sid, board_id, seed, graft, foes, fails,
                        mutate_hastile=a.mutate_hastile)
    finally:
        if not a.mutate_nograft:
            bind_live_rpc(prev)

    print()
    mutated = a.mutate or a.mutate_hastile or a.mutate_nograft
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
