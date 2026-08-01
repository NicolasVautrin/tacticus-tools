"""#366-r1 -- EffectType 0x459 = 1113 `TunnelingHorror_PendingSummon` : MESURE live de bout en bout.

RE (decompile = verite, cf. `docs/rl/case-366-r1-tunneling-horror-pending-summon.md`) :

  * `IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect` derive d'`ABondEffect`
    (le corps de `$$.ctor` que Ghidra attribue a `IdunBattle.Entities.Effects.BaseEffect$$.ctor` est
    DEDUPLIQUE ; le parent REEL se lit dans `data/symbols/<build>/frida/classes.tsv`).
    `.ctor()` = `ABondEffect(hasAutomaticActivation: true, unitEffectType: 0,
    sourceAbility: AbilityOrEffect(ActiveAbilityType.TunnelingHorror = 1011))`.
  * Elle surcharge TROIS getters, tous a corps trivial : `get_Adjacent -> false`,
    `get_Range -> Nullable<int> vide`, `get_RemoveOnBondedEntityDeath -> false`. Ce sont les SEULS
    parametres lus par `IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal`
    => l'`ArraySet` des triggers de retrait automatique est VIDE.
  * POSE : `IdunBattleLogic.Entities.Abilities.Active.Loki.TunnelingHorrorAbility$$ExecuteBehaviour`
    (active 1011) = `RemoveUnitFromItsTiles(Caster, true)` + `RemoveAllForcedAttackTargets(Caster)`
    + `AddBondEffect(0x459, AbilityStateReference, source: Caster, targets: TargetTiles,
    bondedEntity: Caster, <options SANS TurnsFromRounds>)`.
  * LECTURE : `...TunnelingHorrorAbility$$GetDynamicInvalidTargetReason` = `HasEffect(Get(target),
    0x459, ...)` -> une tuile DEJA marquee est une cible INVALIDE (`TargetingRule` 2 =
    `TargetMatchesDynamicRule`, bit present dans le masque `0x8000000001042` du `$$.ctor`).
  * RETRAIT : `...TunnelingHorror_AppearAbility$$ExecuteBehaviour` (active 1060) =
    `First(EffectTarget(BondEffects(all, 0x459, bondedEntity: Owner)), 1)` -> `MoveUnit` -> puis
    `RemoveEffect(EffectSelf, 0x459)`.

MONTAGE. Le porteur `necroSmnDestroyer` est un SUMMON **sans invocateur d'unite** : le balayage du
gameconfig ne trouve `necroSmnDestroyer` que dans `abilities["EnvFactionSummons:Necrons"].constants
.unitId`, une ability d'ENVIRONNEMENT que AUCUNE unite ne porte. Recours 3 de
`docs/rl/case-92-catalog-injection.md` §5bis : GREFFE de l'ability 1011 sur des heros DU POOL
(`necroDestroyer`, `necroOverlord`) dans une COPIE du seed BC. Legitime ici : `TunnelingHorror` n'a
AUCUNE variable au gameconfig et son behaviour ne lit ni stat, ni trait, ni arme du caster.

CONFRONTATION (#366-r1, volet PORT). Depuis que le VECTEUR DE POSE est porte (l'ability 1011 est au
registre `ABILITY_CLASSES`), le probe ne se contente plus d'observer le natif : il rejoue le MEME
cast OFFLINE, par la voie COMPLETE (`Runner.apply(ActiveAbilityMessage)`), sur l'etat capture JUSTE
AVANT le cast live, puis compare les DEUX etats finaux terme a terme -- position, empreinte, vivant,
tuiles marquees (`confront`). Avant ce foyer, le cote PORT rendait la position INCHANGEE et aucune
tuile marquee : le cast etait un no-op silencieux.

Usage (depuis scripts/python) :
    python probe_366_r1_tunneling_horror.py [--keep]
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

LOGS = ROOT / "logs" / "probe366r1"
STATE = LOGS / "state_366_r1_tunneling.json"      # SORTIE -> logs/ (#349), JAMAIS data/
SEED_BC = LOGS / "seed_bc_366_r1_tunneling.json"  # copie greffee, JAMAIS le seed BC partage

TUNNELING = 1011          # ActiveAbilityType.TunnelingHorror
APPEAR = 1060             # ActiveAbilityType.TunnelingHorror_Appear
PENDING = 1113            # EffectType.TunnelingHorror_PendingSummon
GRAFT_A = "necroDestroyer"
GRAFT_B = "necroOverlord"
BOARD = "MC1_67"
SEED = "777"
P_UNITS = GRAFT_A + "," + GRAFT_B
A_UNITS = "ultraTitus,ultraInceptorSgt"


# --------------------------------------------------------------------------- transport

def rpc(method, body=None, timeout=120):
    return L._rpc(L._resolve_session(), method, [body if body is not None else {}],
                  timeout=timeout).get("result")


def _duel(args):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=str(PYDIR),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False)


# --------------------------------------------------------------------------- montage

def write_graft_seed_bc() -> None:
    """Copie du seed BC PARTAGE avec `ActiveAbilities = [1011]` sur les DEUX greffons."""
    bc = L._load_seed_bc(None)
    n = 0
    for u in bc.get("Units") or []:
        if u.get("Id") in (GRAFT_A, GRAFT_B):
            u["ActiveAbilities"] = [TUNNELING]
            n += 1
    if n != 2:
        raise SystemExit("MONTAGE INVALIDE : %d entree(s) greffee(s) au lieu de 2" % n)
    LOGS.mkdir(parents=True, exist_ok=True)
    SEED_BC.write_text(json.dumps(bc), encoding="utf-8")
    print("[366-r1] greffe ActiveAbilities=[%d] sur %s et %s" % (TUNNELING, GRAFT_A, GRAFT_B))


def build(seed_value: str = SEED, board_id: str = BOARD) -> int:
    write_graft_seed_bc()
    if STATE.exists():
        STATE.unlink()
    p = _duel(["build", "--seed", seed_value, "--board", board_id, "--rank", "17",
               "--seed-bc", str(SEED_BC), "--p-units", P_UNITS, "--a-units", A_UNITS,
               "--state-file", str(STATE)])
    if not STATE.exists():
        raise SystemExit("build KO (MONTAGE, pas une mesure): "
                         + (p.stderr or p.stdout or "")[-800:])
    return int(json.loads(STATE.read_text(encoding="utf-8"))["runnerId"])


# --------------------------------------------------------------------------- lectures

def dv(rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": True}, 90)


def units_by_vid(rid):
    out = {}
    for u in (dv(rid).get("units") or []):
        p = u.get("pos") or {}
        out[u.get("id")] = {"vid": u.get("visualId"), "ctrl": u.get("ctrl"),
                            "pos": (p.get("col"), p.get("row")), "alive": u.get("alive"),
                            "hasAction": u.get("hasAction")}
    return out


def pending_tiles(rid):
    """Les tuiles portant 1113, telles que le canal `tileMeta` (`readEffectsByTile`) les publie.
    `decisionView` est AVEUGLE aux effets de TUILE (case-92) : lire ce canal-la, pas l'autre."""
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    return {(t.get("col"), t.get("row")): e
            for t in (tm.get("tiles") or [])
            for e in (t.get("effects") or []) if e.get("effectType") == PENDING}, tm


def capture(rid) -> dict:
    """Les CINQ canaux dont `load_state` a besoin pour materialiser l'etat offline (dont `tileMeta`,
    seul canal des effets de TUILE -- `decisionView` y est AVEUGLE, cf. case-92)."""
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


def offline_view(st, board, uid: int) -> dict:
    """Ce que l'ETAT PORTE dit de l'unite `uid` et des tuiles marquees -- la forme EXACTE que le
    canal live rend, pour que la comparaison soit terme a terme."""
    from engine.runner.components import UnitComponent, get_unit_feet
    e = st.get_entity(int(uid))
    uc = e.get_component(UnitComponent) if e is not None else None
    feet = get_unit_feet(st, int(uid))
    marked = sorted(board.coord(tid)
                    for tid, effs in ((t, st.effects.by_unit.get(t) or [])
                                      for t in list(st.effects.by_unit))
                    if any(int(getattr(x, "effect_type", -1)) == PENDING and not x.consumed
                           for x in effs)
                    if board.by_id.get(tid) is not None)
    return {"pos": (feet[0] if feet else None), "feet": feet,
            "alive": (uc.alive if uc is not None else None), "marked": marked}


def legal_tiles(rid, caster, ability):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster, "abilityType": ability}, 90) or {}
    for u in (at.get("units") or []):
        if u.get("unitId") != caster:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != ability:
                continue
            return {(t["tile"]["col"], t["tile"]["row"])
                    for t in (a.get("fromHere") or []) if t.get("kind") == "tile"}
    return set()


# --------------------------------------------------------------------------- etapes

def e0_offline(fails):
    """E0 -- structure du port (aucun live) : registre, absence MESUREE de trigger, knobs."""
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki import TunnelingHorrorPendingSummonEffect as T
    from engine.runner.operations.triggers import EFFECT_TRIGGERS

    cls = EFFECT_CLASSES.get("TunnelingHorror_PendingSummon")
    if cls is not T:
        fails.append("E0 registre: EFFECT_CLASSES['TunnelingHorror_PendingSummon'] = %r" % cls)
    if EFFECT_TRIGGERS.get(PENDING):
        fails.append("E0 EFFECT_TRIGGERS[%d] non vide = %r"
                     % (PENDING, EFFECT_TRIGGERS.get(PENDING)))
    knobs = (T.BOND_ADJACENT, T.BOND_RANGE, T.BOND_REMOVE_ON_BONDED_ENTITY_DEATH,
             T.HAS_AUTOMATIC_ACTIVATION)
    if knobs != (False, None, False, True):
        fails.append("E0 knobs ABondEffect = %r (attendu (False, None, False, True))" % (knobs,))
    inst = T(effect_type=PENDING, name="TunnelingHorror_PendingSummon")
    if inst.applied_stat_mods(None) or inst.create_effect_damage_bonus_for_attack() is not None:
        fails.append("E0 contribution non nulle: %r" % (inst.applied_stat_mods(None),))
    print("[E0] registre OK | EFFECT_TRIGGERS[%d] vide | knobs %r" % (PENDING, (knobs,)))


def e2_offline_seed(rid, target, fails):
    """E2 -- le canal de CHARGEMENT materialise l'effet avec la CLASSE du registre."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.entities.effects.loki import TunnelingHorrorPendingSummonEffect as T

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    st = load_state(dec, ob, snap, board=board, tiles=tm)
    tid = board.id_at(target[0], target[1])
    got = [e for e in (st.effects.by_unit.get(tid) or []) if e.effect_type == PENDING]
    if len(got) != 1:
        fails.append("E2 %d instance(s) de 1113 sur la tuile-entite %r (attendu 1)" % (len(got), tid))
        return
    e = got[0]
    if not isinstance(e, T):
        fails.append("E2 classe materialisee = %s (attendu %s)" % (type(e).__name__, T.__name__))
    # LIMITE DE CANAL, ecrite pour qu'un futur lecteur ne la prenne pas pour un bug de port :
    # `tileMeta` publie {name, effectType, source, remaining, level} et PAS le `BondEffect_BondedId`
    # (le flux d'EVENTS, lui, le porte). Une instance SEEDEE a donc `bonded = None`.
    print("[E2] offline: tuile-entite %r porte %s (source=%r, bonded=%r <- canal tileMeta sans bond)"
          % (tid, type(e).__name__, e.source, e.bonded))


def e3_marker_read(rid, caster_b, target, witness, fails):
    """E3 -- DISCRIMINANT : la tuile marquee sort des cibles legales du SECOND porteur de 1011
    (`GetDynamicInvalidTargetReason` = `HasEffect(target, 0x459)`). Le temoin, lui, reste legal."""
    legal = legal_tiles(rid, caster_b, TUNNELING)
    if not legal:
        fails.append("E3 aucun target legal pour u%d/1011 : montage invalide" % caster_b)
        return
    if target in legal:
        fails.append("E3 la tuile MARQUEE %r reste une cible legale de u%d : l'effet n'est pas LU"
                     % (target, caster_b))
    if witness not in legal:
        fails.append("E3 le temoin %r n'est pas legal (%d cibles) : le refus de E3 ne discrimine "
                     "rien" % (witness, len(legal)))
    print("[E3] cibles legales de u%d: %d | marquee %r exclue=%s | temoin %r inclus=%s"
          % (caster_b, len(legal), target, target not in legal, witness, witness in legal))


def e4_persist(rid, target, fails):
    """E4 -- ni portee ni adjacence ne le retirent : `get_Range`/`get_Adjacent` sont eteints, et le
    porteur du bond est HORS PLATEAU (distance indefinie) -- l'effet survit a un tour complet."""
    _duel(["act", "endturn", "--state-file", str(STATE), "--runner", str(rid)])
    _duel(["aiturn", "--state-file", str(STATE), "--runner", str(rid)])
    after, _ = pending_tiles(rid)
    if target not in after:
        fails.append("E4 1113 a disparu de %r apres un tour complet (tuiles=%r)"
                     % (target, sorted(after)))
    print("[E4] apres endturn+aiturn : 1113 sur %r -> %s" % (target, json.dumps(after.get(target))))


def e5_appear(rid, caster_a, target, fails):
    """E5 -- RETRAIT : `TunnelingHorror_Appear` (1060) ramene l'unite SUR la tuile bondee et
    `RemoveEffect(0x459)` nettoie le marqueur."""
    r = _duel(["act", "ability", "--caster", str(caster_a), "--ability", str(APPEAR),
               "--target", str(caster_a), "--state-file", str(STATE), "--runner", str(rid)])
    if r.returncode != 0:
        raise SystemExit("E5 cast 1060 REFUSE (montage): %s" % (r.stdout or r.stderr)[-600:])
    after, _ = pending_tiles(rid)
    if after:
        fails.append("E5 1113 subsiste apres Appear: %r" % (sorted(after),))
    u = units_by_vid(rid).get(caster_a) or {}
    if u.get("pos") != target:
        fails.append("E5 le caster est en %r au lieu de la tuile bondee %r" % (u.get("pos"), target))
    print("[E5] apres Appear : tuiles marquees=%r | caster pos=%r" % (sorted(after), u.get("pos")))


# ------------------------------------------------------------- CONFRONTATION port <-> natif (#366-r1)

def pick_target(rid, caster_a, caster_b):
    """Cible = la tuile legale COMMUNE aux deux porteurs la plus ELOIGNEE des deux (le bond doit
    tenir sans aucune proximite -- c'est ce qui rend E4 discriminant vis-a-vis d'`Adjacent`/`Range`) ;
    temoin = la suivante. Rend `(us, caster_a_pos, target, witness)`."""
    us = units_by_vid(rid)
    legal_a = legal_tiles(rid, caster_a, TUNNELING)
    legal_b = legal_tiles(rid, caster_b, TUNNELING)
    common = sorted(legal_a & legal_b)
    if len(common) < 2:
        raise SystemExit("MONTAGE : %d tuile(s) legale(s) commune(s), il en faut 2 (cible + temoin)"
                         % len(common))
    pa, pb = us[caster_a]["pos"], us[caster_b]["pos"]

    def far(t):
        return min(abs(t[0] - pa[0]) + abs(t[1] - pa[1]),
                   abs(t[0] - pb[0]) + abs(t[1] - pb[1]))
    target = max(common, key=far)
    witness = max([t for t in common if t != target], key=far)
    return us, pa, pb, target, witness


def confront(rid, caster_a, target, fails) -> dict:
    """LE CRITERE DU RESIDU, en une question binaire : **apres un cast de 1011, le caster est-il
    encore sur le plateau ?** -- posee au NATIF et au PORT sur le MEME etat de depart.

    On capture l'etat AVANT le cast, on rejoue le cast OFFLINE par la voie COMPLETE (`Runner.apply(
    ActiveAbilityMessage)` : gates de ciblage, `On(0x2a = PreUnitAbility)`, behaviour, flags de tour), puis on joue le
    cast LIVE et on RECHARGE l'etat natif d'apres. Les deux etats finaux sont compares terme a terme
    (position, empreinte, vivant, tuiles marquees). Avant ce foyer, le cote PORT rendait
    `pos = (col,row)` INCHANGEE et `marked = []` : le no-op silencieux."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner

    pre = capture(rid)
    st, board = offline_state(pre)
    tile_id = board.id_at(target[0], target[1])
    before = offline_view(st, board, caster_a)
    # --- PORT : la voie COMPLETE (le gate de cible en fait partie -- un refus se verrait ici).
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_a), target_id=int(tile_id),
                                      ability_type=TUNNELING))
    last = runner.ability_handler.last or {}
    port = offline_view(st, board, caster_a)
    # --- NATIF : le meme cast, en live, puis rechargement de l'etat d'apres.
    r = _duel(["act", "ability", "--caster", str(caster_a), "--ability", str(TUNNELING),
               "--to", "%d,%d" % target, "--state-file", str(STATE), "--runner", str(rid)])
    if r.returncode != 0:
        raise SystemExit("CONFRONTATION : cast live REFUSE (montage): %s"
                         % (r.stdout or r.stderr)[-600:])
    st2, board2 = offline_state(capture(rid))
    native = offline_view(st2, board2, caster_a)

    if last.get("ported") is not True:
        fails.append("CONFRONT: l'ability 1011 n'est pas EXECUTEE cote port (last=%r)" % (last,))
    for k in ("pos", "feet", "alive", "marked"):
        if port[k] != native[k]:
            fails.append("CONFRONT %s : port=%r != natif=%r" % (k, port[k], native[k]))
    if native["pos"] is not None:
        fails.append("CONFRONT: le caster natif garde une position %r apres 1011" % (native["pos"],))
    if native["marked"] != [target]:
        fails.append("CONFRONT: tuiles marquees cote natif = %r (attendu [%r])"
                     % (native["marked"], target))
    if native["alive"] is not True:
        fails.append("CONFRONT: le caster natif n'est plus vivant -- il est HORS PLATEAU, pas mort")
    print("[CONFRONT] avant=%r | port=%r | natif=%r" % (before, port, native))
    return {"before": before, "port": port, "native": native, "last": last,
            "target": target, "tile_id": tile_id}


def run(seed: str = SEED, board_id: str = BOARD, keep: bool = False) -> dict:
    """MONTAGE NOMME de la confrontation, reutilisable depuis pytest (cf.
    `tests/engine/runner/test_366_r1_tunneling_horror_live.py`). Build + greffe + choix de la cible
    + `confront` + dispose. Rend le dict de mesure ; `fails` y est la liste des ECARTS."""
    fails: list = []
    rid = build(seed_value=seed, board_id=board_id)
    try:
        us = units_by_vid(rid)
        caster_a = next(i for i, u in us.items() if u["vid"] == GRAFT_A)
        caster_b = next(i for i, u in us.items() if u["vid"] == GRAFT_B)
        _us, pa, pb, target, witness = pick_target(rid, caster_a, caster_b)
        out = confront(rid, caster_a, target, fails)
        e3_marker_read(rid, caster_b, target, witness, fails)
        out.update({"rid": rid, "caster_a": caster_a, "caster_b": caster_b,
                    "witness": witness, "fails": fails})
        return out
    finally:
        if not keep:
            _duel(["dispose", "--state-file", str(STATE), "--runner", str(rid)])


# --------------------------------------------------------------------------- main

def main() -> int:
    keep = "--keep" in sys.argv
    fails: list = []
    e0_offline(fails)
    rid = build()
    print("[366-r1] runner %d board=%s seed=%s" % (rid, BOARD, SEED))
    try:
        us = units_by_vid(rid)
        caster_a = next(i for i, u in us.items() if u["vid"] == GRAFT_A)
        caster_b = next(i for i, u in us.items() if u["vid"] == GRAFT_B)
        _us, pa, pb, target, witness = pick_target(rid, caster_a, caster_b)
        print("[366-r1] u%d(%s)@%r u%d(%s)@%r | cible=%r temoin=%r"
              % (caster_a, GRAFT_A, pa, caster_b, GRAFT_B, pb, target, witness))

        # E1 = les assertions de POSE cote natif ; E1b = la CONFRONTATION port <-> natif du MEME
        # cast. E1b joue le cast, E1 en verifie l'observable natif -> E1 ne le rejoue PAS.
        pre_marked, _ = pending_tiles(rid)
        if pre_marked:
            fails.append("E1 pre-etat pollue: 1113 deja present sur %r" % (sorted(pre_marked),))
        conf = confront(rid, caster_a, target, fails)
        after, _ = pending_tiles(rid)
        eff = after.get(target) or {}
        if set(after) != {target}:
            fails.append("E1 tuiles marquees = %r (attendu {%r})" % (sorted(after), target))
        if eff.get("source") != caster_a:
            fails.append("E1 source = %r (attendu le caster %d)" % (eff.get("source"), caster_a))
        if eff.get("remaining") not in (0, None):
            fails.append("E1 remaining = %r : l'effet devrait etre PERMANENT (AddBondEffect sans "
                         "TurnsFromRounds)" % eff.get("remaining"))
        print("[E1] 1113 sur %r : %s | caster natif pos=%r alive=%r"
              % (target, json.dumps(eff), conf["native"]["pos"], conf["native"]["alive"]))
        e2_offline_seed(rid, target, fails)
        e3_marker_read(rid, caster_b, target, witness, fails)
        e4_persist(rid, target, fails)
        e5_appear(rid, caster_a, target, fails)
    finally:
        if not keep:
            _duel(["dispose", "--state-file", str(STATE), "--runner", str(rid)])
    print()
    if fails:
        print("[366-r1] %d ECHEC(S) :" % len(fails))
        for f in fails:
            print("   - " + f)
        return 1
    print("[366-r1] OK -- CONFRONTATION port<->natif du cast, pose sur tuile, seed offline, "
          "lecture par le gate de ciblage, persistance, retrait par Appear")
    print("[366-r1] NON COUVERT : `get_RemoveOnBondedEntityDeath = false` -- la seule fenetre ou le "
          "bond existe est celle ou l'unite bondee est HORS PLATEAU, donc inatteignable par une "
          "attaque ; seul un DoT pose AVANT le tunnel pourrait la tuer sous le bond.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
