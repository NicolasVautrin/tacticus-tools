"""#448-r2d -- `1573 TitanhammerSquad_TeleportingIn`, la QUATRIEME et derniere derivee d'
`IdunBattle.Entities.Effects.Loki.ATeleportingEffect`, et la SEULE a surcharger le vslot 0x748.

RE (decompile = verite ; famille et vslots dans
`docs/rl/case-448-r2-ateleporting-effect-family.md`, port dans
`engine/runner/operations/triggers/loki/teleporting_in.py`) :

    IdunBattle.Entities.Effects.Loki.TitanhammerSquad_TeleportingInEffect$$GetMovingEffectType
        = Nullable<EffectType>(0x626 = 1574 TitanhammerSquad_Moving)
    IdunBattle.Entities.Effects.Loki.TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition
        = Contains(<Sel+0x78>, tgt) op_BitwiseOr IsAdjacentTiles(<Sel+0x78>, tgt)
          avec tgt = EffectTarget( EffectsFromUnitSource( EffectSource(EffectSelf@<Sel+0x38>),
                                                          0x623 = 1571 TitanhammerSquad_TargetTile ) )

`<DSLSelectors+0x78>` = **TargetTiles** (`AbilityEntities+0x190`, cf. `runner/abilities/admec.py`) ;
sur `On(0x1f = PreUnitMove)` `IdunBattle.Operations.MoveUnitOperation$$EvaluatePreMoveTriggers` y
met la tuile d'ARRIVEE. Autrement dit : **le marqueur `1574` n'est pose que si la DESTINATION du pas
EST une tuile marquee `1571`, ou lui est ADJACENTE.**

LE POINT DUR DE CETTE TRANCHE -- ET CE QUE LE PROBE MONTE POUR L'EXERCER
------------------------------------------------------------------------
`1571` n'est pose par PERSONNE cote port : son poseur est l'ACTIVE `1231 TitanhammerSquad`, dont
`IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$ExecuteBehaviour` combine
QUATRE behaviours et n'est PAS portee. Sans montage, le vslot 0x748 serait donc confronte sur une
entree VIDE et rendrait `False` partout : le port aurait l'air de marcher et la condition n'aurait
JAMAIS ete exercee.

Le montage exerce les DEUX bras, et le substrat vient du NATIF :
  1. `astarLysander` (seul porteur de 1231, HERO **hors pool**) est injecte au catalogue
     (`catalog_inject.write_augmented_seed_bc` -- l'assainissement du trait hors-enum
     `ImperialFists` est fait la, cf. #270-d / `probe_270d_lysander_deploy.py`) ;
  2. il CASTE 1231 LIVE sur une tuile choisie -> le natif pose `1571` sur cette tuile et `1573` sur
     lui-meme + les allies `TerminatorArmour` (trait 0x40f = 1039) a portee `range` (2) ;
  3. l'etat du port est RECHARGE depuis le natif (`decisionView` + `combatSnapshot` + **`tileMeta`**,
     qui porte les effets de TUILE, cf. `snapshot._load_tile_effects`) -- le port lit donc le MEME
     substrat `1571` que le natif, sans avoir a porter 1231 ;
  4. TROIS pas depuis cet etat, chacun confronte port/natif :
        ARM-FAR      un pas de MARCHE loin de la marque      -> AUCUN 1574 attendu
        ARM-NEAR-ON  un pas de TELEPORT **sur** la marque    -> 1574 attendu (bras `Contains`)
        ARM-NEAR-ADJ un pas de TELEPORT **a cote** de la marque -> 1574 attendu (bras `IsAdjacentTiles`)

Les trois pas sont possibles parce qu'`IdunBattle.Entities.Pathfinding.ATeleportPathfinder$$
IterateReachableTiles` est un DECORATEUR : le pool est l'UNION « ce que la marche atteint » ET le
pool de teleport (lui, restreint a la zone marquee par `TitanhammerSquadPathfinder$$
IsValidTeleportTile`). Un porteur de 1573 peut donc marcher normalement loin de la marque.

CE QUI EST OBSERVABLE, ET CE QUI NE L'EST PAS
----------------------------------------------
`1574` est TRANSITOIRE : pose par T4 au `On(PreUnitMove)`, retire par
`IdunBattleLogic.Effects.TeleportMovingEffect` au `On(UnitAfterMove)` du MEME pas. Et il n'a
**AUCUN lecteur gameplay** trouve sur ce build : `IdunBattle.Entities.UnitExtensions$$SetMovedFlag`
-- le seul consommateur des marqueurs de la famille -- teste `0x40c`, `0x40b`, `0x4d9` et `0x4d6`
(1036/1035/1241/1238) et **PAS** `0x625`/`0x626`. Le port doit donc reproduire la POSE sans
etendre `_TELEPORT_MOVE_EFFECTS` (etape 0 le verrouille).

Le canal de mesure LIVE est donc la CASCADE d'events du `applyAction` (groupe `Effect_Refresh`
source `TitanhammerSquad_Moving` + `ReceiveEffect` sur le mover), pas un delta numerique. Les pas
sont cites par NOM via `stream_events` (jamais par ordinal, #254b-b).

Usage (depuis scripts/python) :
    python probe_448_r2d_titanhammer_squad.py               # etape 0 + 2 couples live
    python probe_448_r2d_titanhammer_squad.py --offline     # etape 0 SEULE (aucun runner)
    python probe_448_r2d_titanhammer_squad.py --mutate      # CONTRE-EPREUVE (doit rougir)
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parent.parent
sys.path.insert(0, str(PYDIR))

import catalog_inject  # noqa: E402
import stream_events as SE  # noqa: E402
import rl_collect_batch as L  # noqa: E402

LOGS = ROOT / "logs" / "probe448r2d"
STATE = LOGS / "state_448_r2d_titanhammer.json"      # SORTIE -> logs/ (#349), JAMAIS data/

TARGET_TILE = 1571        # EffectType.TitanhammerSquad_TargetTile        (0x623)
TELEPORTING_IN = 1573     # EffectType.TitanhammerSquad_TeleportingIn     (0x625)
MOVING = 1574             # EffectType.TitanhammerSquad_Moving            (0x626)
MOVING_NAME = "TitanhammerSquad_Moving"
ABILITY = 1231            # ActiveAbilityType.TitanhammerSquad

CASTER = "astarLysander"          # seul porteur de 1231 -- HERO HORS POOL (injection catalogue)
FAR_MOVER = "thousTerminator"     # TerminatorArmour SANS TeleportStrike -> son SEUL effet de
ON_MOVER = "deathBlightlord"      # famille est 1573 (pas de 1035 qui brouillerait la lecture)
#: une 4e unite qui N'AGIT PAS : sans elle, le 3e pas epuise `toActivate` et le tour BASCULE --
#: la cascade du dernier bras se retrouve melangee au tour adverse.
FILLER = "astraBullgryn"
P_UNITS = ",".join((CASTER, ON_MOVER, FAR_MOVER, FILLER))
A_UNITS = "orksWarboss,orksNob,necroWarden,eldarRanger"
COUPLES = [("MC1_67", "777"), ("C3_26", "31337")]


# --------------------------------------------------------------------------- transport

def rpc(method, body=None, timeout=120):
    return L._rpc(L._resolve_session(), method, [body if body is not None else {}],
                  timeout=timeout).get("result") or {}


def _duel(args):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


def build(seed_value: str, board_id: str) -> int:
    """Montage : seed BC AUGMENTE d'`astarLysander` puis `rl_duel build --seed-bc`.

    Le seed BC augmente est ecrit dans `logs/` (jamais `data/`, cf. #349) et supprime apres."""
    LOGS.mkdir(parents=True, exist_ok=True)
    if STATE.exists():
        STATE.unlink()
    bc = LOGS / ("seedbc-%s.json" % uuid.uuid4().hex[:8])
    catalog_inject.write_augmented_seed_bc(str(bc), [CASTER])
    try:
        p = _duel(["build", "--seed", seed_value, "--board", board_id, "--rank", "17", "--no-ai",
                   "--seed-bc", str(bc), "--p-units", P_UNITS, "--a-units", A_UNITS,
                   "--state-file", str(STATE)])
        if not STATE.exists():
            raise SystemExit("build KO (MONTAGE, pas une mesure): "
                             + (p.stderr or p.stdout or "")[-900:])
    finally:
        bc.unlink(missing_ok=True)
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


def capture(rid) -> dict:
    """⚠ `tileMeta` est OBLIGATOIRE ici (et pas un confort) : c'est le SEUL canal par lequel
    l'effet `1571`, porte par une TUILE, entre dans `State.effects` (`snapshot._load_tile_effects`).
    Sans lui le vslot 0x748 serait confronte sur une entree vide -- exactement la degradation
    silencieuse que cette tranche doit exclure.
    `decisionView` SANS `includeInactive` : MEME canal que le reste du harnais (cf. la note de
    `probe_448_r2_teleporting_in.py`)."""
    return {"dec": rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 180),
            "ob": rpc("observeBattle", {"runnerId": rid}, 60),
            "snap": rpc("combatSnapshot", {"runnerId": rid}, 90),
            "tm": rpc("tileMeta", {"runnerId": rid}, 90),
            "bg": rpc("boardGraph", {"runnerId": rid}, 90)}


def offline_state(cap):
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    board = Board(cap["bg"]["tiles"], adjacency="evenq")
    return load_state(cap["dec"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"]), board


def find_vid(st, vis: str):
    from engine.runner.components import UnitComponent
    for uid, e in st.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and str(uc.visual_id) == vis:
            return int(uid)
    return None


def unit_view(st, uid: int) -> dict:
    """La forme EXACTE des deux cotes -- un etat OFFLINE des deux, l'un rejoue par le port, l'autre
    RECHARGE du natif. `flags` inclus : c'est ce qui verrouille que `SetMovedFlag` ne pose PAS
    `Teleported` pour cette famille-ci (0x625/0x626 absents de son test)."""
    from engine.runner.components import UnitComponent, UnitFlagsComponent, get_unit_feet
    from engine.ai.state_bridge import _is_untargetable
    e = st.get_entity(int(uid))
    uc = e.get_component(UnitComponent) if e is not None else None
    fl = e.get_component(UnitFlagsComponent) if e is not None else None
    feet = get_unit_feet(st, int(uid))
    effs = sorted((getattr(x, "name", None) or str(getattr(x, "effect_type", "?")))
                  for x in (st.effects.by_unit.get(int(uid)) or []) if not x.consumed)
    return {"pos": (feet[0] if feet else None), "alive": (uc.alive if uc is not None else None),
            "effects": effs, "untargetable": bool(_is_untargetable(st, int(uid))),
            "teleported": bool(fl is not None and fl.has(UnitFlagsComponent.TELEPORTED))}


def marked_tiles(st, board, src: int) -> list:
    """Les tuiles qui portent `1571` posee par `src` -- la MEME lecture que
    `_TitanhammerSquadTargetTileCondition._target_tiles`, mais ecrite ICI independamment (on ne
    valide pas le port avec le port). Rend des `(col, row)` tries."""
    out = []
    for carrier, effs in (st.effects.by_unit or {}).items():
        if int(carrier) not in board.by_id:
            continue
        for e in (effs or []):
            if (not e.consumed and int(getattr(e, "effect_type", -1)) == TARGET_TILE
                    and e.source is not None and int(e.source) == int(src)):
                out.append(board.coord(int(carrier)))
                break
    return sorted(out)


# --------------------------------------------------------------------------- cascade LIVE

def cascade(res) -> list:
    evs = list(res.get("cascade") or [])
    for a in (res.get("actions") or []):
        evs += list(a.get("events") or [])
    return evs


def moving_marker_live(evs, mover: int) -> dict:
    """Le `1574` dans la cascade NATIVE. Les pas sont resolus PAR NOM (`stream_events`), jamais par
    ordinal : `StepType` est implicitement numerote et une MAJ le decale (cf. #254b-b).

    Forme mesuree : un groupe `Effect_Refresh` dont la `source` est le NOM de l'effet et dont
    l'`entity` est l'id de l'ENTITE-EFFET, suivi d'actions `ActivateEffect`/`ReceiveEffect` portant
    ce meme `Effect_Id` sur le MOVER."""
    recv = SE.step_id("ReceiveEffect")
    lose = SE.step_id("LoseEffect")
    ids = {int(e.get("entity")) for e in evs
           if e.get("kind") == "group" and e.get("source") == MOVING_NAME
           and e.get("entity") is not None}
    got = {"effect_ids": sorted(ids), "received": [], "lost": []}
    for e in evs:
        if e.get("kind") != "action" or int(e.get("entity") or -1) != int(mover):
            continue
        try:
            tags = json.loads(e.get("tags") or "{}")
        except (TypeError, ValueError):
            continue
        if int(tags.get("Effect_Id", -1)) not in ids:
            continue
        if int(e.get("step", -1)) == recv:
            got["received"].append(tags)
        elif int(e.get("step", -1)) == lose:
            got["lost"].append(tags)
    return got


# --------------------------------------------------------------------------- etape 0

def etape0(fails: list) -> None:
    """OFFLINE PUR. Ce que l'etape verrouille, et pourquoi chaque point peut regresser en silence :
    l'inscription des CINQ classes au registre (sans elles, aucune erreur -- juste un marqueur
    jamais pose), la surcharge EFFECTIVE du vslot 0x748 par la seule `TitanhammerSquad`, et
    l'ABSENCE de 1573/1574 du test de `SetMovedFlag` (les y ajouter poserait `UnitFlag.Teleported`
    sur un teleport que le natif ne compte pas -- degradation PERMISSIVE)."""
    from engine.runner.components import _TELEPORT_MOVE_EFFECTS
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    from engine.runner.operations.triggers.loki import teleporting_in as T

    print("=== etape 0 -- inscription et specialisation (offline) ===")
    got = [c.__name__ for c in EFFECT_TRIGGERS.get(TELEPORTING_IN, [])]
    want = ["TitanhammerSquadTeleportingInRemoveOnAfterMove",
            "TitanhammerSquadTeleportingInRemoveOnPreUnitAbility",
            "TitanhammerSquadTeleportingInRemoveOnUnitFinishedTurn",
            "TitanhammerSquadTeleportingInAddMovingOnPreMove"]
    print("  EFFECT_TRIGGERS[%d] = %s" % (TELEPORTING_IN, got))
    if got != want:
        fails.append("etape0 : EFFECT_TRIGGERS[%d] = %r != %r" % (TELEPORTING_IN, got, want))
    gotm = [c.__name__ for c in EFFECT_TRIGGERS.get(MOVING, [])]
    print("  EFFECT_TRIGGERS[%d] = %s" % (MOVING, gotm))
    if gotm != ["TitanhammerSquadMovingRemoveOnAfterMove"]:
        fails.append("etape0 : EFFECT_TRIGGERS[%d] = %r" % (MOVING, gotm))
    t4 = T.TitanhammerSquadTeleportingInAddMovingOnPreMove
    print("  MOVING_EFFECT_TYPE = %r  (Nullable<EffectType>(0x626))" % t4.MOVING_EFFECT_TYPE)
    if t4.MOVING_EFFECT_TYPE != MOVING:
        fails.append("etape0 : MOVING_EFFECT_TYPE = %r != %d" % (t4.MOVING_EFFECT_TYPE, MOVING))
    base = T.ATeleportingAddMovingOnPreMove._custom_moving_condition
    if t4._custom_moving_condition is base:
        fails.append("etape0 : le vslot 0x748 n'est PAS surcharge -- le port collapse a True")
    for cls in (T.TeleportStrikeTeleportingInAddMovingOnPreMove,):
        if cls._custom_moving_condition is not base:
            fails.append("etape0 : %s surcharge le vslot 0x748 -- seule TitanhammerSquad le fait"
                         % cls.__name__)
    print("  _TELEPORT_MOVE_EFFECTS = %s" % sorted(_TELEPORT_MOVE_EFFECTS))
    if {TELEPORTING_IN, MOVING} & set(int(x) for x in _TELEPORT_MOVE_EFFECTS):
        fails.append("etape0 : 1573/1574 dans _TELEPORT_MOVE_EFFECTS -- `SetMovedFlag` ne teste "
                     "que 0x40c/0x40b/0x4d9/0x4d6, pas cette famille-ci")
    print()


# --------------------------------------------------------------------------- confrontation

def confront_arm(label, rid, mover, dest, expect_moving, fails) -> None:
    """UN pas, confronte des deux cotes.

    PORT : le pas est DECOUPE (`MoveUnitOperation` puis le vecteur after-move) pour observer le
    marqueur TRANSITOIRE entre les deux. NATIF : la cascade du `applyAction`. Puis l'etat final est
    compare TERME A TERME (l'etat natif est RECHARGE par le meme `load_state`)."""
    from engine.runner.events import EventBus
    from engine.runner.operations.movement import MoveUnitOperation
    from engine.runner.operations.triggers import after_move_triggers

    st, _b = offline_state(capture(rid))
    before = unit_view(st, mover)
    MoveUnitOperation(int(mover), tuple(dest)).execute(st, EventBus())
    mid = sorted(int(getattr(x, "effect_type", -1))
                 for x in (st.effects.by_unit.get(int(mover)) or []) if not x.consumed)
    after_move_triggers(st, int(mover))
    port = unit_view(st, mover)
    port_end = sorted(int(getattr(x, "effect_type", -1))
                      for x in (st.effects.by_unit.get(int(mover)) or []) if not x.consumed)

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": int(mover), "to": {"col": int(dest[0]), "row": int(dest[1])}}}, 180)
    acts = res.get("actions") or []
    if not acts or not acts[0].get("ok"):
        raise SystemExit("%s : move live REFUSE (MONTAGE, pas une mesure) : %r"
                         % (label, json.dumps(res)[:500]))
    evs = cascade(res)
    live = moving_marker_live(evs, mover)
    #: le mover a-t-il ENCAISSE pendant le pas (step `UnitDamaged`) ? C'est ce qui explique --
    #: par la MESURE, pas par hypothese -- la desactivation native de `TerminatorArmour_*`.
    dmg_step = SE.step_id("UnitDamaged")
    damaged = any(e.get("kind") == "action" and int(e.get("step", -1)) == dmg_step
                  and int(e.get("entity") or -1) == int(mover) for e in evs)

    st2, _b2 = offline_state(capture(rid))
    native = unit_view(st2, mover)

    print("[%s] dest=%r" % (label, tuple(dest)))
    print("  avant  : %r" % (before,))
    print("  port   : PENDANT le pas=%r  fin=%r  %r" % (mid, port_end, port))
    print("  natif  : 1574 cascade=%r  fin=%r" % (live, native))

    port_moving = MOVING in mid
    live_moving = bool(live["received"])
    if port_moving != expect_moving:
        fails.append("%s : port pose 1574 = %s (attendu %s)" % (label, port_moving, expect_moving))
    if live_moving != expect_moving:
        fails.append("%s : natif pose 1574 = %s (attendu %s) -- cascade=%r"
                     % (label, live_moving, expect_moving, live))
    if port_moving != live_moving:
        fails.append("%s : DESACCORD sur 1574 -- port=%s natif=%s"
                     % (label, port_moving, live_moving))
    if expect_moving:
        if TELEPORTING_IN not in mid:
            fails.append("%s : 1573 deja retire PENDANT le pas cote port -- T1 fire trop tot" % label)
        for tags in live["received"]:
            if int(tags.get("Effect_RemainingTurns", -1)) != 1:
                fails.append("%s : natif Effect_RemainingTurns=%r (attendu 1 TOUR)"
                             % (label, tags.get("Effect_RemainingTurns")))
            if int(tags.get("Effect_SourceActiveAbility", -1)) != ABILITY:
                fails.append("%s : natif Effect_SourceActiveAbility=%r (attendu %d)"
                             % (label, tags.get("Effect_SourceActiveAbility"), ABILITY))
    if MOVING in port_end:
        fails.append("%s : 1574 SURVIT au pas cote port -- TeleportMovingEffect non retire" % label)
    if TELEPORTING_IN in port_end:
        fails.append("%s : 1573 SURVIT au pas cote port -- T1 n'a pas retire" % label)
    for k in ("pos", "alive", "untargetable", "teleported"):
        if port[k] != native[k]:
            fails.append("%s %s : port=%r != natif=%r" % (label, k, port[k], native[k]))
    if native["teleported"]:
        fails.append("%s : le natif pose UnitFlag.Teleported -- `SetMovedFlag` ne teste pourtant "
                     "ni 0x625 ni 0x626" % label)

    # LES EFFETS : `natif SOUS-ENSEMBLE DE port`, pas l'egalite -- et c'est la seule comparaison
    # HONNETE entre ces deux canaux. `decisionView` (sans `includeInactive`) ne publie que les
    # effets ACTIFS, alors que `EffectsState.by_unit` garde l'instance et evalue la condition A LA
    # LECTURE. Un effet MANQUANT cote port reste donc une vraie regression (`missing` -> ECHEC) ;
    # un effet EN TROP est soit cette asymetrie de canal, soit un `DeactivateEffect` natif non
    # porte. Les DEUX sources ont ete MESUREES par ce probe, et sont NOMMEES :
    #   * `CrushingStrike` -- `IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$
    #     CreateActiveCondition` = `NOT HasFlag(Moved)` : le pas la desactive cote natif, le port
    #     la garde et gate le bonus a la lecture (`create_effect_damage_bonus_for_attack`) ;
    #   * `TerminatorArmour_ReduceDmg` / `_Visual` -- `IdunBattle.Entities.Effects.Loki.
    #     TerminatorArmour_ReduceDmg_Effect$$CreateTargetTrigger` = `On(9 = Attack) &
    #     AreEqual(Units(Target), Owner) & CurrentAttackDamageProfilesContainOtherThan(<exclus>) &
    #     AmountIsZero(CurrentShieldAmount(Target)) & (AmountIsGreaterThanZero(HealthDamageFromEvent)
    #     | WasBlock)` -> `CreateTargetTriggerBehaviour` = `DeactivateEffect(self)`, re-activee par
    #     son `CreateHandleTriggerAbilitiesInternal` sur `On(0x3e = EffectAdded)`. C'est une reduction UNE FOIS
    #     PAR ATTAQUE, et `EFFECT_TRIGGERS[1147]`/`[1375]` sont VIDES cote port -> RESIDU NOMME,
    #     hors perimetre de cette tranche. Le probe le rend MESURE et non suppose en publiant
    #     `damaged` (le mover a-t-il encaisse pendant le pas -- typiquement un overwatch a
    #     l'atterrissage).
    missing = sorted(set(native["effects"]) - set(port["effects"]))
    extra = sorted(set(port["effects"]) - set(native["effects"]))
    fam = {"TitanhammerSquad_TargetTile", "TitanhammerSquad_TeleportingIn", MOVING_NAME}
    print("  effets : natif\\port(MANQUANTS)=%r   port\\natif(en trop)=%r   damaged=%s"
          % (missing, extra, damaged))
    if missing:
        fails.append("%s effects : le port a PERDU %r que le natif garde" % (label, missing))
    if set(extra) & fam:
        fails.append("%s effects : le port garde %r de la famille ATeleportingEffect que le natif "
                     "a retire" % (label, sorted(set(extra) & fam)))


# --------------------------------------------------------------------------- montage d'un couple

def _hex_dist(board, a, b) -> int:
    from engine.runner.operations.triggers.base import _hex_dist as hd
    d = hd(board, board.id_at(a[0], a[1]), board.id_at(b[0], b[1]), 99)
    return 99 if d is None else d


def run_couple(board_id, seed_value, fails) -> None:
    print("=== couple board=%s seed=%s ===" % (board_id, seed_value))
    rid = build(seed_value, board_id)
    try:
        st, board = offline_state(capture(rid))
        caster = find_vid(st, CASTER)
        on_mover = find_vid(st, ON_MOVER)
        far_mover = find_vid(st, FAR_MOVER)
        if caster is None or on_mover is None or far_mover is None:
            raise SystemExit("MONTAGE : %s / %s / %s non deployes (%r/%r/%r)"
                             % (CASTER, ON_MOVER, FAR_MOVER, caster, on_mover, far_mover))

        # --- la CIBLE du cast : une tuile LEGALE (`fromHere` du natif -- un cast hors domaine est
        # un NO-OP SILENCIEUX), choisie la PLUS LOIN possible des deux movers pour qu'un pas de
        # MARCHE existe qui n'approche NI la marque NI ses voisines (sans quoi ARM-FAR serait
        # inexistant et la mesure ne discriminerait rien).
        ab = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ABILITY}, 180)
        tiles = [(t["tile"]["col"], t["tile"]["row"]) for u in (ab.get("units") or [])
                 for a in (u.get("abilities") or []) for t in (a.get("fromHere") or [])
                 if t.get("kind") == "tile"]
        if not tiles:
            raise SystemExit("MONTAGE : %d n'a AUCUNE tuile-cible `fromHere` (cast impossible)"
                             % ABILITY)
        far = unit_view(st, far_mover)["pos"]
        target = max(tiles, key=lambda t: _hex_dist(board, t, far))
        r = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": caster, "to": {"col": target[0], "row": target[1]},
            "abilityType": ABILITY}}, 180)
        if not ((r.get("actions") or [{}])[0].get("ok")):
            raise SystemExit("MONTAGE : le cast de %d a ECHOUE : %s" % (ABILITY, json.dumps(r)[:500]))
        print("[MONTAGE] %s caste %d sur %r" % (CASTER, ABILITY, target))

        # --- le SUBSTRAT est-il la ? (sinon le vslot 0x748 serait confronte sur du vide)
        st, board = offline_state(capture(rid))
        marks = marked_tiles(st, board, caster)
        print("[MONTAGE] tuiles marquees %d (source=%s) : %r" % (TARGET_TILE, caster, marks))
        if marks != [tuple(target)]:
            fails.append("MONTAGE : tuiles marquees %r != [%r] -- le substrat du vslot 0x748 "
                         "n'est pas celui qu'on croit" % (marks, tuple(target)))
        if len(marks) != 1:
            # L'asymetrie `Contains` (Y reduite a UNE entite) / `IsAdjacentTiles` (toutes) n'est
            # observable qu'a partir de DEUX tuiles marquees : on DIT la cardinalite mesuree.
            print("[MONTAGE] /!\\ cardinalite %d != 1 : l'ordre d'enumeration devient observable"
                  % len(marks))
        for uid in (caster, on_mover, far_mover):
            v = unit_view(st, uid)
            src = next((int(e.source) for e in (st.effects.by_unit.get(uid) or [])
                        if not e.consumed and int(getattr(e, "effect_type", -1)) == TELEPORTING_IN
                        and e.source is not None), None)
            print("[MONTAGE] u%d %r  source(1573)=%r" % (uid, v, src))
            if "TitanhammerSquad_TeleportingIn" not in v["effects"]:
                raise SystemExit("MONTAGE : u%d ne porte pas 1573 apres le cast" % uid)
            if src != caster:
                fails.append("MONTAGE : source de 1573 sur u%d = %r != %r" % (uid, src, caster))

        # --- les TROIS destinations, prises dans le pool LEGAL du natif (`aiMovableTiles`) : un
        # `applyAction move` hors pool est un NO-OP SILENCIEUX (H55) et se lirait comme un desaccord.
        mv = rpc("aiMovableTiles", {"runnerId": rid}, 120)
        pool = {int(u.get("unitId")): {(t.get("col"), t.get("row")) for t in (u.get("tiles") or [])}
                for u in (mv.get("units") or [])}
        tgt_id = board.id_at(target[0], target[1])
        near = {board.coord(t) for t in board.neighbours_native(tgt_id)} | {tuple(target)}
        far_dest = next((t for t in sorted(pool.get(far_mover, set())) if t not in near), None)
        on_dest = tuple(target) if tuple(target) in pool.get(on_mover, set()) else None
        if far_dest is None or on_dest is None:
            raise SystemExit("MONTAGE : destination absente du pool natif (far=%r on=%r ; "
                             "pool far=%r pool on=%r)"
                             % (far_dest, on_dest, sorted(pool.get(far_mover, ())),
                                sorted(pool.get(on_mover, ()))))

        # ARM-FAR d'abord : elle laisse la marque LIBRE pour ARM-NEAR-ON.
        confront_arm("ARM-FAR", rid, far_mover, far_dest, False, fails)
        confront_arm("ARM-NEAR-ON", rid, on_mover, on_dest, True, fails)

        # ARM-NEAR-ADJ : le CASTER lui-meme, sur une voisine LIBRE de la marque (le bras
        # `IsAdjacentTiles`, que `Contains` seul ne couvrirait pas).
        mv = rpc("aiMovableTiles", {"runnerId": rid}, 120)
        cpool = {(t.get("col"), t.get("row")) for u in (mv.get("units") or [])
                 if int(u.get("unitId")) == caster for t in (u.get("tiles") or [])}
        adj = next((t for t in sorted(cpool & near) if t != tuple(target)), None)
        if adj is None:
            fails.append("ARM-NEAR-ADJ : aucune voisine LIBRE de la marque dans le pool du caster "
                         "(pool=%r near=%r) -- le bras IsAdjacentTiles n'est PAS exerce"
                         % (sorted(cpool), sorted(near)))
        else:
            confront_arm("ARM-NEAR-ADJ", rid, caster, adj, True, fails)
    finally:
        _duel(["dispose", "--state-file", str(STATE)])


# --------------------------------------------------------------------------- main

def main() -> int:
    fails: list = []
    mutated = "--mutate" in sys.argv
    if mutated:
        # CONTRE-EPREUVE : on RETIRE la surcharge du vslot 0x748 -- c'est-a-dire exactement le port
        # qu'on obtiendrait en inscrivant 1573 au registre SANS lire
        # `TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition`. ARM-FAR DOIT alors
        # rougir (le port poserait 1574 sur un pas de marche quelconque). Si le probe reste VERT,
        # c'est qu'il ne mesure rien -- VERT est le resultat SUSPECT sur une contre-epreuve.
        from engine.runner.operations.triggers.loki import teleporting_in as T
        T.TitanhammerSquadTeleportingInAddMovingOnPreMove._custom_moving_condition = \
            T.ATeleportingAddMovingOnPreMove._custom_moving_condition
        print("[MUTATE] vslot 0x748 RENDU NEUTRE (True) -- ARM-FAR DOIT rougir\n")
    etape0([] if mutated else fails)
    if "--offline" in sys.argv:
        if fails:
            print("=== %d ECHEC(S) ===" % len(fails))
            for f in fails:
                print("  - " + f)
            return 1
        print("OK (etape 0 seule)")
        return 0
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
    print("=== OK -- 1573/1574 confrontes, vslot 0x748 exerce sur SES DEUX BRAS ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
