"""PHASE 2 de Hailstrike (1214, `darkaStormSpeeder` MoW) — les DEUX maillons, confrontes au LIVE (#123).

Ce que la phase 2 ajoute au cast (qui, lui, ne fait que poser l'effet 1509 — cf. `test_storm_speeder_live`) :

  (a) `IdunBattle.Entities.Effects.Loki.Hailstrike_ExtraPierceEffect$$CreatePiercingBonusForAttack` =
      `ForPiercing(get_OwnerIsCaster & (IsRangedAttack | IsOverwatchAttack), ConfigVar(0x3f =
      extraPierceRatio, GetAbilityState(this)))` -> +extraPierceRatio au RATIO DE PERCAGE des attaques
      RANGED/OVERWATCH du PORTEUR du buff (aucun gate `CurrentAbilityIs` : l'attaque NORMALE compte).
  (b) `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Hailstrike_AttackAbility` (0x5e3 = 1507),
      enregistree sur la MoW par `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.
      ActiveAbility$$GetDerivedTriggeredAbilities` (`0x4be -> [0x5e3]`, LU au decompile) : quand un ALLIE
      porteur du buff finit une attaque ranged/overwatch sur un ennemi VIVANT, la MoW attaque la MEME
      cible (`nrOfHits` coups du profil de la config 1214).

STRATEGIE DE CONFRONTATION (decomposition par etage — on ne fitte aucun scalaire) :

  * `test_hailstrike_attack_trigger_live` — cible a **armure 0** (`--hp-target`). A armure nulle le
    PERCAGE est inerte : tout ecart de degat viendrait donc d'un AUTRE canal. On y exige le bit-exact
    sur (i) le coup de l'allie ET (ii) les `nrOfHits` coups de la MoW, per-coup. Ce test prouve donc a la
    fois le maillon (b) ET que le buff n'ajoute AUCUN degat (c'est bien un canal percage).
    Garde anti-faux-positif : sans le registre `ACTIVE_ABILITY_TRIGGERS`, l'offline perd exactement les
    coups de la MoW -> l'assertion serait aveugle si le trigger etait un no-op.
  * `test_hailstrike_pierce_envelope_live` — cible a **armure INTACTE** et PV enormes (`--unit-stat`,
    qui patche le BC **deja normalise** ; `--hp-target` mettrait l'armure a 0). N tirs sous buff ; on
    encadre les degats live par les bornes que le port calcule AVEC le bonus, et on exige qu'au moins
    un tir SORTE des bornes SANS le bonus. C'est l'identification de la magnitude par ENVELOPPE : le
    bonus est PORTANT et vaut ce que la config dit.

    ⚠ **CE CRITERE N'A DE SENS QUE DANS UN REGIME, ET LE MONTAGE DOIT L'ETABLIR (#914).** Les bornes
    que rend le port (`clean_min`/`clean_max`, `damage_ops/normal.py`) sont explicitement la plage
    **NON-CRIT** (`hit_nc.min/max x hits`), et le montant que le natif reporte (`Amount`) est le degat
    **APPLIQUE**, donc TRONQUE aux PV restants sur un `Attack_WasOverkill`. Deux derives du harnais
    avaient fait sortir un tir de l'enveloppe sur `master`, **sans qu'aucune magnitude ne soit
    fausse** : (i) le patch de `BC.Units[].Health` du SEED BC est INOPERANT -- `buildNormalizedBC`
    RECALCULE `Health` au rank cible, la cible arrivait a ~9539 PV au lieu des 900000 annonces et
    mourait en cours de serie ; (ii) depuis **#419-r6** les items BiS sont EQUIPES par defaut, donc
    `IdunBattle.Core.Services.DamageCalculations$$CouldCrit` (`GetStat(9) > 0 && GetStat(10) > 0`) est
    VRAI -- alors qu'il etait FAUX pour toute unite quand ce test a ete ecrit (#123 : could_crit
    0/106 -> 98/106). Le montage eteint donc les DEUX canaux orthogonaux (`--crit 0,0` cote attaquant,
    `--block-target 0,0` cote defenseur) et le test EXIGE des tags natifs qu'ils le confirment,
    tir par tir. Mesure du regime restaure : les six montants live sont a nouveau `1921, 2422, 2700,
    2015, 2445, 2153` -- la serie de #123 a l'unite pres -- et le port les reproduit **bit-exact 6/6**.
  * `test_hailstrike_pierce_gates_offline` — les gates de l'effet, sans runner (OwnerIsCaster,
    disjonction ranged|overwatch, tri-etat #106, scaling resolu contre la SOURCE et non le porteur).

Lit l'etat LIVE, aucune tuile/RVA hardcodee. Oracles = gameconfig (valeurs BRUTES). ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import gameconfig as GC
import hexgeo
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.damage_profile_type import DamageProfileType
from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.darkangels import HailstrikeExtraPierceEffect
from engine.entities.effects.magnitude import ability_var
from engine.entities.pathfinding.board import Board
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.components import HealthComponent, StatsComponent
from engine.runner.messages import AttackUnitMessage
from engine.runner.operations.triggers.dispatch.registry import ACTIVE_ABILITY_TRIGGERS
from engine.runner.operations.triggers.loki.hailstrike import HailstrikeAttackAbility
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]

MOW = "darkaStormSpeeder"
ALLY = "darkaAzrael"          # arme RANGED Plasma (Range 2, 1 coup) -> attaque normale a distance
SPARE = "ultraApothecary"
FOE = "astraBullgryn"         # armure elevee (le percage y est observable)
BOARD = "MC1_67"
ABILITY = 1214
HAILSTRIKE_ATTACK = int(TriggeredAbilityType.Hailstrike_Attack)   # 1507
#: PV forces a la cible du bras ARMURE, par `--unit-stat` (BC deja normalise) -- cf. `_build`.
TANKY_HP = 900000
#: Les quatre drapeaux que le natif pose sur l'evenement de degat et qui SORTENT le montant de la
#: plage NON-CRIT rendue par le port (`clean_min`/`clean_max`). `Attack_WasOverkill` est le plus
#: perfide : il ne change pas le calcul, il TRONQUE le montant reporte aux PV restants.
FLAGS_HORS_ENVELOPPE = ("Attack_DidCrit", "Attack_DidBlock", "Attack_DidEvade",
                        "Attack_WasOverkill")


# --------------------------------------------------------------------------------------------- #
# Oracles CONFIG (valeurs BRUTES lues par le natif ; jamais de constante en dur dans un assert).
# --------------------------------------------------------------------------------------------- #
def _const(key: str) -> str:
    consts = ((GC.ability("Hailstrike") or {}).get("constants") or {})
    assert key in consts, (f"oracle introuvable : gameconfig.ability('Hailstrike').constants.{key} "
                           f"-- le natif le lit par GetNumberConstant/GetDamageProfile")
    return str(consts[key])


def _profile_pierce(profile: str) -> int:
    dp = GC.damage_profile(profile) or {}
    assert dp.get("PiercingRatio") is not None, f"damageProfiles.{profile}.PiercingRatio absent"
    return int(dp["PiercingRatio"])


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _build(rpc, tag: str, no_armor: bool):
    """Runner avec la MoW deployee. `no_armor` -> `--hp-target` (met FixedArmor a 0 : le percage devient
    inerte) ; sinon on force les PV de l'ennemi par `--unit-stat`, qui patche le BC **deja normalise**
    et garde donc son armure."""
    bc = ROOT / "logs" / "runners" / f"bc-hailstrike-{tag}-{uuid.uuid4().hex[:8]}.json"
    bc.parent.mkdir(parents=True, exist_ok=True)
    inj = subprocess.run([sys.executable, "catalog_inject.py", "--units", MOW, "--out", str(bc)],
                         cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    if not bc.exists():
        pytest.skip(f"catalog_inject KO: {(inj.stderr or inj.stdout or '')[-300:]}")
    _bc = json.loads(bc.read_text(encoding="utf-8"))
    for _pid, _p in ((_bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(_p, dict) and _p.get("PlayerType") != 2:
            _p["MachineOfWarAmmo"] = 5              # meme levier que test_storm_speeder_live (#117)
    bc.write_text(json.dumps(_bc), encoding="utf-8")
    state_file = ROOT / "logs" / "runners" / f"hailstrike-{tag}-{uuid.uuid4().hex[:8]}.json"
    # #914 -- les PV passent par `--unit-stat` et NON par un patch de `BC.Units[].Health` du seed BC :
    # `buildNormalizedBC` RECALCULE `Health` au rank cible, donc le patch amont etait INOPERANT (~9539
    # PV mesures pour 900000 demandes) et la cible mourait en cours de serie -- le dernier montant live
    # devenait un OVERKILL, c.-a-d. les PV RESTANTS. `--crit`/`--block-target` eteignent les deux
    # canaux ORTHOGONAUX au percage (cf. le §REGIME de la docstring de module) ; ce n'est PAS
    # `--no-bis-items`, qui deshabillerait le heros entier.
    extra = (["--hp-target", "900000", "--hp-player", "900000"] if no_armor else
             ["--unit-stat", f"{FOE}:Health={TANKY_HP},RemainingHealth={TANKY_HP}",
              "--crit", "0,0", "--block-target", "0,0"])
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "31337", "--seed-bc", str(bc),
         "--state-file", str(state_file), "--board", BOARD,
         "--p-units", f"{ALLY},{SPARE}", "--a-units", f"{FOE},{FOE}", "--p-mow", MOW, *extra],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        pytest.skip(f"build runner MoW KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    return int(json.loads(state_file.read_text())["runnerId"]), state_file, bc


@pytest.fixture(scope="module")
def hailstrike_noarmor(rpc):
    rid, sf, bc = _build(rpc, "noarm", no_armor=True)
    try:
        yield rid
    finally:
        _dispose(rpc, rid, sf, bc)


@pytest.fixture(scope="module")
def hailstrike_armor(rpc):
    rid, sf, bc = _build(rpc, "arm", no_armor=False)
    try:
        yield rid
    finally:
        _dispose(rpc, rid, sf, bc)


def _dispose(rpc, rid, *paths):
    try:
        rpc("disposeRunner", {"runnerId": rid}, 30)
    except Exception:
        pass
    for p in paths:
        try:
            p.unlink()
        except Exception:
            pass


# --------------------------------------------------------------------------------------------- #
# Helpers live
# --------------------------------------------------------------------------------------------- #
def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)


def _mow(dv):
    return next((m for m in (dv.get("mows") or []) if m.get("visualId") == MOW), None)


def _unit(dv, vis):
    return next((u for u in (dv.get("units") or []) if u.get("visualId") == vis), None)


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _from_here(rpc, rid, unit_id, ability_id):
    """Cibles castables DEPUIS LA POSITION COURANTE — jamais `targets` (gate de ciblage #115)."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": unit_id, "abilityType": ability_id}, 120)
    for u in (at.get("units") or []):
        for a in (u.get("abilities") or []):
            if a.get("abilityId") == ability_id:
                return [t.get("targetId") for t in (a.get("fromHere") or [])
                        if t.get("targetId") is not None]
    return []


def _drive(rpc, rid, vis, goal_id, want_dist, iters=14):
    """DEPLACE l'unite jusqu'a `want_dist` de la cible (doctrine drive-positions : on ne se declare
    jamais bloque par la geometrie de spawn)."""
    for _ in range(iters):
        d = _dv(rpc, rid)
        u = _unit(d, vis)
        g = next((x for x in (d.get("units") or []) if x["id"] == goal_id), None)
        if u is None or g is None or hexgeo.distance(_pos(u), _pos(g)) <= want_dist:
            return d
        mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "all"}, 90)
        mu = next((m for m in (mov.get("units") or []) if m.get("unitId") == u["id"]), None)
        tiles = [(t["col"], t["row"]) for t in (mu or {}).get("tiles") or [] if t.get("col") is not None]
        best = min(tiles, key=lambda t: (hexgeo.distance(t, _pos(g)), t)) if tiles else None
        if best is None or hexgeo.distance(best, _pos(g)) >= hexgeo.distance(_pos(u), _pos(g)):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": u["id"], "to": {"col": best[0], "row": best[1]}}}, 90)
    return _dv(rpc, rid)


def _snapshot(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 90)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    return (_dv(rpc, rid), rpc("observeBattle", {"runnerId": rid}, 90),
            rpc("combatSnapshot", {"runnerId": rid}, 120),
            rpc("dumpRng", {"runnerId": rid}, 60), board)


def _offline(dv, ob, snap, rng0, board):
    st = load_state(dv, ob, snap, board=board)
    if isinstance(rng0, dict) and rng0.get("mt"):
        r = IntBasedMersenneTwister()
        r.mt = list(rng0["mt"])
        r.mti = rng0["mti"]
        st.rng = r
    return st


def _damage_events(cast):
    """[(attacker, target, amount, profileType, activeAbility, passiveAbility)] dans l'ORDRE live."""
    out = []
    for td in _damage_tags(cast):
        out.append((td.get("Attacker_Id"), td.get("Target_Id"), td.get("Amount"),
                    td.get("DamageProfileType"), td.get("Active_Ability_Type"),
                    td.get("Passive_Ability_Type")))
    return out


def _damage_tags(cast):
    """Les tags DECODES et COMPLETS de chaque evenement de degat, dans l'ORDRE live. `_damage_events`
    n'en garde que six champs ; le REGIME du coup (crit / block / evade / overkill) vit dans les
    autres, et c'est lui qui dit si le montant appartient a la plage que le port encadre."""
    out = []
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else td
            if td and "Amount" in td:
                out.append(td)
    return out


def _hp(dv):
    return {u["id"]: u.get("hp") for u in (dv.get("units") or []) if u.get("hp") is not None}


def _offline_hp(st, ids):
    out = {}
    for uid in ids:
        e = st.get_entity(uid)
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is not None:
            out[uid] = hc.hp
    return out


def _setup_buffed_shot(rpc, rid):
    """Amene l'allie a portee RANGED d'un ennemi, fait poser Hailstrike par la MoW, et rend
    `(mow_id, ally_id, target_id, normal_ability_id)`."""
    d = _dv(rpc, rid)
    m = _mow(d)
    if m is None:
        pytest.skip("MoW darkaStormSpeeder non deployee")
    ally = _unit(d, ALLY)
    foes = [u for u in (d.get("units") or []) if u.get("owner") != m.get("owner") and u.get("alive")]
    if ally is None or not foes:
        pytest.skip("allie/ennemi absent")
    d = _drive(rpc, rid, ALLY, foes[0]["id"], 2)
    ally = _unit(d, ALLY)
    pos = {u["id"]: _pos(u) for u in (d.get("units") or [])}
    tgts = [f["id"] for f in foes if hexgeo.distance(pos[ally["id"]], pos[f["id"]]) == 2]
    if not tgts:
        pytest.skip("aucun ennemi a distance 2 (tir Plasma) apres deplacement")
    fh = _from_here(rpc, rid, m["casterId"], ABILITY)
    assert ally["id"] in fh, (f"l'allie u{ally['id']} n'est pas cible legale de Hailstrike "
                              f"(fromHere={fh}) -- l'ability cible un ALLIE")
    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": m["casterId"], "targetId": ally["id"],
        "abilityType": ABILITY}}, 150)
    assert _ok(cast), f"cast Hailstrike refuse: {str(cast)[:250]}"
    d = _dv(rpc, rid)
    au = next((u for u in (d.get("units") or []) if u["id"] == ally["id"]), {})
    assert any((e.get("name") or "") == EffectType.Hailstrike.name for e in (au.get("effects") or [])), \
        f"effet Hailstrike absent de l'allie apres le cast : {[e.get('name') for e in (au.get('effects') or [])]}"
    nid = next((a.get("id") for a in (au.get("abilities") or []) if a.get("kind") == "normal"), None)
    assert nid is not None, "attaque normale (kind=normal) introuvable sur l'allie"
    return m["casterId"], ally["id"], tgts[0], nid


# --------------------------------------------------------------------------------------------- #
# (b) L'ATTAQUE DECLENCHEE DE LA MACHINE — bit-exact, cible a ARMURE 0
# --------------------------------------------------------------------------------------------- #
def test_hailstrike_attack_trigger_live(rpc, hailstrike_noarmor):
    """`Hailstrike_AttackAbility` (1507) : la MoW attaque la MEME cible que l'allie buffe.
    Cible a armure 0 -> le percage est INERTE, donc l'egalite offline==live sur le coup de l'ALLIE
    prouve en plus que le buff n'ajoute AUCUN degat (c'est bien un canal percage)."""
    rid = hailstrike_noarmor
    mow_id, ally_id, tgt, nid = _setup_buffed_shot(rpc, rid)

    dv, ob, snap, rng0, board = _snapshot(rpc, rid)
    hp0 = _hp(dv)
    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": ally_id, "targetId": tgt, "abilityType": nid},
        "captureEvents": True}, 150)
    assert _ok(cast), f"attaque de l'allie refusee: {str(cast)[:250]}"
    ev = _damage_events(cast)
    live_ally = [e for e in ev if e[0] == ally_id]
    live_mow = [e for e in ev if e[0] == mow_id]
    assert live_ally, f"aucun degat live attribue a l'allie u{ally_id} : {ev}"

    # (1) LE TRIGGER A FIRE, et il est IDENTIFIE : attaquant = la MoW, AbilityOrEffect = 1507.
    want_hits = int(_const("nrOfHits"))
    want_prof = int(DamageProfileType[_const("damageProfile")])
    assert len(live_mow) == want_hits, (
        f"{len(live_mow)} coup(s) de la MoW live != oracle config nrOfHits={want_hits} : {live_mow}")
    assert {e[5] for e in live_mow} == {HAILSTRIKE_ATTACK}, (
        f"AbilityOrEffect des coups de la MoW {[e[5] for e in live_mow]} != 1507 Hailstrike_Attack")
    assert {e[3] for e in live_mow} == {want_prof}, (
        f"profils des coups de la MoW {[e[3] for e in live_mow]} != oracle config {want_prof} "
        f"(piege : `GetDamageProfileOrDefault(0x14)` -- 0x14 est le DEFAUT, pas le profil)")
    assert {e[1] for e in live_mow} == {tgt}, (
        f"la MoW frappe {[e[1] for e in live_mow]} au lieu de la cible de l'allie u{tgt} "
        f"(`AttackWithAbilityDamage(owner@0x148, target@0x178, ...)`)")
    assert ev.index(live_mow[0]) > ev.index(live_ally[0]), (
        "les coups de la MoW precedent celui de l'allie -- le trigger est un `On(9)` de FIN d'attaque")

    # (2) OFFLINE == LIVE, per-coup. Chemin de PRODUCTION = `Runner.apply(AttackUnitMessage)` (c'est le
    #     handler qui emet le vecteur `On(9)`; appeler l'Operation seule le SAUTE).
    st = _offline(dv, ob, snap, rng0, board)
    rr = Runner(st).install_default_handlers(20)
    rr.apply(AttackUnitMessage(attacker_id=ally_id, target_id=tgt))
    off = rr.damage_handler.last or {}
    trig = [t for t in (rr.damage_handler.after_hit or []) if t.get("ability") == "Hailstrike_Attack"]
    assert trig, (f"le trigger 1507 n'a PAS fire offline (after_hit={rr.damage_handler.after_hit}) "
                  f"-- registre ACTIVE_ABILITY_TRIGGERS / gates du `CreateTrigger`")
    assert off.get("total") == live_ally[0][2], (
        f"coup de l'ALLIE offline {off.get('total')} != live {live_ally[0][2]} "
        f"(cible a armure 0 : le percage est inerte, tout ecart serait un AUTRE canal)")
    off_hits = ((trig[0].get("result") or {}).get("per_hit")) or []
    assert off_hits == [e[2] for e in live_mow], (
        f"coups de la MoW offline {off_hits} != live {[e[2] for e in live_mow]}")

    # (3) BILAN VITAL : la somme appliquee est la meme des deux cotes.
    dv3 = _dv(rpc, rid)
    hp1 = _hp(dv3)
    live_delta = {u: hp0[u] - hp1[u] for u in hp0 if u in hp1 and hp0[u] != hp1[u]}
    ohp = _offline_hp(st, list(hp0))
    off_delta = {u: hp0[u] - ohp[u] for u in hp0 if u in ohp and hp0[u] != ohp[u]}
    assert live_delta == off_delta, f"delta PV live {live_delta} != offline {off_delta}"

    # (4) GARDE ANTI-FAUX-POSITIF (mutation) : sans le registre, l'offline PERD exactement les coups de
    #     la MoW. Une assertion qui passerait aussi sans le port serait aveugle.
    st2 = _offline(dv, ob, snap, rng0, board)
    saved = ACTIVE_ABILITY_TRIGGERS.pop("Hailstrike", None)
    try:
        rr2 = Runner(st2).install_default_handlers(20)
        rr2.apply(AttackUnitMessage(attacker_id=ally_id, target_id=tgt))
        muted = [t for t in (rr2.damage_handler.after_hit or [])
                 if t.get("ability") == "Hailstrike_Attack"]
    finally:
        if saved is not None:
            ACTIVE_ABILITY_TRIGGERS["Hailstrike"] = saved
    assert not muted, "mutation-test invalide : le trigger fire encore sans son registre"
    ohp2 = _offline_hp(st2, list(hp0))
    off2_delta = {u: hp0[u] - ohp2[u] for u in hp0 if u in ohp2 and hp0[u] != ohp2[u]}
    assert off2_delta != off_delta, (
        "le port du trigger n'est PAS portant : le delta PV est identique avec et sans lui")


# --------------------------------------------------------------------------------------------- #
# (a) LE BONUS DE PERCAGE — identification par ENVELOPPE, cible a ARMURE INTACTE
# --------------------------------------------------------------------------------------------- #
def test_hailstrike_pierce_envelope_live(rpc, hailstrike_armor):
    """Le bonus `extraPierceRatio` est PORTANT et vaut ce que la config dit : sur N tirs sous buff
    contre une cible a armure 3513, tous les degats live tiennent dans les bornes que le port calcule
    AVEC le bonus, et au moins un SORT des bornes calculees SANS lui."""
    rid = hailstrike_armor
    mow_id, ally_id, tgt0, nid = _setup_buffed_shot(rpc, rid)
    d = _dv(rpc, rid)
    m = _mow(d)
    ally = next((u for u in (d.get("units") or []) if u["id"] == ally_id), {})
    pos = {u["id"]: _pos(u) for u in (d.get("units") or [])}
    tgts = [u["id"] for u in (d.get("units") or [])
            if u.get("owner") != m.get("owner") and u.get("alive")
            and hexgeo.distance(pos[ally_id], pos[u["id"]]) == 2]
    assert tgts, "aucune cible a portee 2"

    shots = []            # (live_amount, bornes AVEC bonus, bornes SANS bonus)
    for n in range(6):
        dd = _dv(rpc, rid)
        au = next((u for u in (dd.get("units") or []) if u["id"] == ally_id), {})
        if dd.get("currentPlayer") != m.get("owner") or not au.get("hasAction"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
            dd = _dv(rpc, rid)
            au = next((u for u in (dd.get("units") or []) if u["id"] == ally_id), {})
            if not au.get("hasAction"):
                break
        if not any((e.get("name") or "") == EffectType.Hailstrike.name
                   for e in (au.get("effects") or [])):
            fh = _from_here(rpc, rid, mow_id, ABILITY)
            if ally_id in fh:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": mow_id, "targetId": ally_id,
                    "abilityType": ABILITY}}, 150)
            else:
                break
        tgt = tgts[n % len(tgts)]
        dv, ob, snap, rng0, board = _snapshot(rpc, rid)
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ally_id, "targetId": tgt, "abilityType": nid},
            "captureEvents": True}, 150)
        live = [t for t in _damage_tags(cast) if t.get("Attacker_Id") == ally_id]
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        if not live:
            continue
        with_bonus = _bounds(dv, ob, snap, rng0, board, ally_id, tgt, mute=False)
        without = _bounds(dv, ob, snap, rng0, board, ally_id, tgt, mute=True)
        if with_bonus is None or without is None:
            continue
        shots.append((live[0].get("Amount"), live[0], with_bonus, without))
    if len(shots) < 3:
        pytest.skip(f"seulement {len(shots)} tir(s) buffe(s) exploitable(s) -- NON COUVERT, pas un succes")

    # (0) LE REGIME, avant toute comparaison de magnitude (#914). Le montage l'ETABLIT (`--crit 0,0`,
    #     `--block-target 0,0`, PV forces) ; ici on exige que le NATIF le confirme, coup par coup.
    #     Sans ce cran, un crit ou un overkill fait rougir (1) en accusant « la magnitude portee est
    #     fausse » -- c'est exactement le faux diagnostic qu'un tir a produit sur `master`.
    for amt, tg, _w, _s in shots:
        arme = [k for k in FLAGS_HORS_ENVELOPPE if tg.get(k)]
        assert not arme, (
            f"tir HORS du regime encadre ({', '.join(arme)}) : le montant live {amt} n'est PAS "
            f"comparable a [clean_min, clean_max], qui est la plage NON-CRIT du port -- et sur un "
            f"`Attack_WasOverkill` c'est meme les PV RESTANTS, pas le degat calcule. Le montage "
            f"eteint ces canaux : si ce rouge apparait, c'est le LEVIER qui ne mord plus "
            f"(`--crit 0,0` / `--block-target 0,0` / `--unit-stat Health`), pas le port du percage.")
    # (1) le port encadre TOUS les degats live avec le bonus.
    for amt, _tg, (lo, hi), _ in shots:
        assert lo <= amt <= hi, (
            f"degat live {amt} hors des bornes du port AVEC le bonus [{lo}, {hi}] "
            f"-- la magnitude du percage portee est fausse")
    # (2) le bonus est PORTANT : sans lui, au moins un tir live sort des bornes.
    out = [amt for amt, _tg, _w, (lo, hi) in shots if not (lo <= amt <= hi)]
    assert out, (f"aucun des {len(shots)} tirs live ne sort des bornes SANS le bonus "
                 f"({[s[2] for s in shots]}) -- le scenario ne DISCRIMINE pas, la garde serait aveugle")
    # (3) l'oracle de magnitude est la CONFIG, pas un chiffre en dur.
    lvl, mult = _ally_scaling_from_source(rpc, rid, mow_id)
    want = int(ability_var("Hailstrike", "extraPierceRatio", lvl, multiplier_pct=mult) or 0)
    assert want > 0, "extraPierceRatio nul dans la config : le scenario ne teste rien"
    base = _profile_pierce("Plasma")
    assert base + want <= 100, "percage sature a 100 : l'enveloppe ne discriminerait pas"


def _bounds(dv, ob, snap, rng0, board, ally_id, tgt, mute: bool):
    """Bornes REDUITES du coup, calculees par le port lui-meme (`clean_min`/`clean_max`), avec ou sans
    le bonus de percage de Hailstrike."""
    st = _offline(dv, ob, snap, rng0, board)
    if mute:
        for e in (st.effects.by_unit.get(ally_id) or []):
            if isinstance(e, HailstrikeExtraPierceEffect):
                e.create_effect_piercing_bonus_for_attack = lambda ctx=None: None
    rr = Runner(st).install_default_handlers(20)
    rr.apply(AttackUnitMessage(attacker_id=ally_id, target_id=tgt))
    r = rr.damage_handler.last or {}
    lo, hi = r.get("clean_min"), r.get("clean_max")
    return (int(lo), int(hi)) if (lo is not None and hi is not None) else None


def _ally_scaling_from_source(rpc, rid, mow_id):
    """(niveau d'ability ACTIVE, multiplier) de la SOURCE de l'effet -- c'est ce que
    `BaseEffect$$GetAbilityState` resout, PAS l'etat du porteur."""
    dv = _dv(rpc, rid)
    m = _mow(dv)
    ab = next((a for a in ((m or {}).get("abilities") or []) if a.get("id") == ABILITY), {})
    return int(ab.get("level") or 0), int(ab.get("multiplier") or 100)


# --------------------------------------------------------------------------------------------- #
# Gates de l'effet — OFFLINE pur (aucun runner) : mirror des trois predicats natifs.
# --------------------------------------------------------------------------------------------- #
def test_hailstrike_pierce_gates_offline():
    """`ForPiercing(get_OwnerIsCaster & (IsRangedAttack | IsOverwatchAttack), ConfigVar(0x3f))` :
    chaque gate est PORTANT, et le scaling se resout contre la SOURCE (porteur != source)."""
    eff = HailstrikeExtraPierceEffect(name=EffectType.Hailstrike.name,
                                      effect_type=int(EffectType.Hailstrike), source=7)

    class _Src:                       # UnitContext minimal de la SOURCE (la MoW)
        active_ability_level = 50
        ability_variables_multiplier = 100
    ctx = dict(owner_id=3, att_id=3, is_ranged=True, is_overwatch=False,
               unit_ctx_of=lambda uid: _Src() if uid == 7 else None)
    want = int(ability_var("Hailstrike", "extraPierceRatio", 50, multiplier_pct=100) or 0)
    assert want > 0, "oracle extraPierceRatio nul"

    assert eff.create_effect_piercing_bonus_for_attack(ctx) == want, "ranged : bonus attendu"
    assert eff.create_effect_piercing_bonus_for_attack(dict(ctx, is_ranged=False)) is None, \
        "IsRangedAttack faux et pas overwatch -> AUCUN bonus"
    assert eff.create_effect_piercing_bonus_for_attack(
        dict(ctx, is_ranged=False, is_overwatch=True)) == want, \
        "IsOverwatchAttack est l'AUTRE branche de la disjonction -> bonus meme en melee"
    assert eff.create_effect_piercing_bonus_for_attack(dict(ctx, is_ranged=None)) is None, \
        "nature du coup NON threadee (#106) -> les deux gates se TAISENT"
    assert eff.create_effect_piercing_bonus_for_attack(dict(ctx, att_id=4)) is None, \
        "get_OwnerIsCaster : le porteur du buff doit etre l'ATTAQUANT"

    # SCALING : c'est la SOURCE qui indexe le ConfigVar, pas le porteur (courbe 10/12/15).
    class _Low:
        active_ability_level = 1
        ability_variables_multiplier = 100
    low = int(ability_var("Hailstrike", "extraPierceRatio", 1, multiplier_pct=100) or 0)
    assert eff.create_effect_piercing_bonus_for_attack(
        dict(ctx, unit_ctx_of=lambda uid: _Low())) == low != want, \
        "le niveau de la SOURCE doit changer la magnitude (sinon le resolveur est inerte)"


def test_hailstrike_trigger_registered_offline():
    """Le registre `ACTIVE_ABILITY_TRIGGERS` mirror `GetDerivedTriggeredAbilities` : `Hailstrike` (l'active
    1214) accorde la triggered `Hailstrike_Attack` (1507), et l'ecoute est bien `On(9=Attack)`."""
    assert ACTIVE_ABILITY_TRIGGERS.get("Hailstrike") == [HailstrikeAttackAbility]
    assert HailstrikeAttackAbility.event_id == int(EventTriggerType.Attack)
    assert "Hailstrike" in ((GC.unit(MOW) or {}).get("activeAbilities") or []), \
        f"{MOW} ne porte plus l'ability active Hailstrike dans gameconfig"
