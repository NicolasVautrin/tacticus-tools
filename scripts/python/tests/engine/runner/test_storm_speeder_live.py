"""Storm Speeder (`darkaStormSpeeder`, MACHINE OF WAR DarkAngels) — DeathOnTheWind (1213) et
Hailstrike (1214), face COMBAT, confrontees au LIVE (#117).

Porteur ABSENT du seed BC partage -> `catalog_inject.py` (#92) l'injecte dans les DEUX catalogues
(`BC.Units` ET `BC.Abilities`) avant le build ; sans le second, le cast FAUTE (« system error »).

HAILSTRIKE (1214) — `HailstrikeAbility$$ExecuteBehaviour` = un SEUL `AddEffect(0x5e5 = 1509 Hailstrike,
AbilityStateReference, source = caster@0x160, targets = target@0x178, TurnsFromRounds(nrOfRounds))`
(patron « MoW effect-poser », case-90). Ce que le test garde :
  * la cible LEGALE est un ALLIE (`abilityTargets.fromHere` ne rend que mes unites) ;
  * l'effet pose live == l'effet pose offline : MEME porteur, MEME `EffectType`, MEME SOURCE (la MoW),
    et surtout MEME DUREE — `remainingTurns` live == `convert_rounds_to_turns(nrOfRounds)` offline
    (`ConvertRoundsToTurns` = `count(joueurs non-Environment) * rounds`, #98). Un port qui aurait pris
    `nrOfRounds` pour des TOURS poserait 1 au lieu de 2 : l'assertion le voit.
Oracle de `nrOfRounds` = la CONFIG (`GetNumberConstant(0x45 = nrOfRounds)`, valeur BRUTE).

DEATHONTHEWIND (1213) — attaque de LIGNE + pose d'effet. DEUX gates natifs conditionnent le cast :
  * `munitionsCost = 1` (ressource de bataille) et `initialCooldownTurns = 1` ;
  * `DeathOnTheWindAbility$$GetDynamicInvalidTargetReason` : la cible doit avoir DEJA recu >= 1 attaque
    CE TOUR (`EntityExtensions.GetNumAttacksReceivedThisTurn(unit) != 0`).
Le test fait avancer les tours jusqu'a ce que la MoW ait ses munitions, FRAPPE la cible avec un allie,
puis prend la cible dans `fromHere` (case-111) et confronte le SET frappe + le nb de coups + le profil +
le SET des effets 1257 poses. SKIP EXPLICITE (avec la raison chiffree) si les munitions ne viennent
jamais — un skip n'est PAS un succes, il est rapporte comme non-couverture.

Lit l'etat LIVE, aucune tuile/RVA hardcodee. ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import gameconfig as GC
from engine.entities.damage_profile_type import DamageProfileType
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.abilities.darkangels import DeathOnTheWindAbility, HailstrikeAbility
from engine.runner.abilities.base import convert_rounds_to_turns
from engine.runner.snapshot import load_state

PYDIR = Path(__file__).resolve().parents[3]
ROOT = PYDIR.parents[1]
MOW_VIS = "darkaStormSpeeder"
BOARD = "C1_02"
P_UNITS = "darkaAzrael,ultraApothecary"
A_UNITS = "eldarRanger,eldarRanger,eldarRanger,eldarRanger"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _mut(r):
    return bool((r.get("actions") or [{}])[0].get("mutated")) if isinstance(r, dict) else False


def _const(ability: str, key: str) -> str:
    consts = ((GC.ability(ability) or {}).get("constants") or {})
    assert key in consts, (f"oracle introuvable : gameconfig.ability('{ability}').constants.{key} "
                           f"absent -- le natif le lit par GetNumberConstant, il DOIT exister")
    return str(consts[key])


def _seed_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"])
    r.mti = s["mti"]
    return r


def _live_hits(cast, ability_id):
    out: dict = {}
    for act in (cast.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ability_id:
                out.setdefault(td.get("Target_Id"), []).append(
                    (td.get("Amount"), td.get("DamageProfileType")))
    return out


@pytest.fixture(scope="module")
def speeder_runner(rpc):
    """Runner avec la MoW `darkaStormSpeeder` deployee (catalogue augmente). Dispose au teardown."""
    bc = ROOT / "logs" / "runners" / f"bc-speeder-{uuid.uuid4().hex[:8]}.json"
    bc.parent.mkdir(parents=True, exist_ok=True)
    inj = subprocess.run([sys.executable, "catalog_inject.py", "--units", MOW_VIS, "--out", str(bc)],
                         cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    if not bc.exists():
        pytest.skip(f"catalog_inject KO: {(inj.stderr or inj.stdout or '')[-300:]}")
    # MUNITIONS : `munitionsCost = 1` gate le cast de DeathOnTheWind, et le seed BC part a
    # `BC.Player.Players[*].MachineOfWarAmmo = 0` -> l'ability n'est JAMAIS castable (mesure : 12 tours
    # sans reappro). Aucun flag `rl_duel` ne l'expose : on ETEND le harnais (doctrine « quand aucun
    # levier ne produit ton etat, le defaut est dans l'outil ») en dotant les joueurs de munitions dans
    # le BC injecte -- meme nature qu'un `--hp-target` (parametre de BATAILLE, pas de mecanique).
    _bc = json.loads(bc.read_text(encoding="utf-8"))
    for _pid, _p in ((_bc.get("Player") or {}).get("Players") or {}).items():
        if isinstance(_p, dict) and _p.get("PlayerType") != 2:      # Environment exclu
            _p["MachineOfWarAmmo"] = 5
    bc.write_text(json.dumps(_bc), encoding="utf-8")
    state_file = ROOT / "logs" / "runners" / f"speeder-{uuid.uuid4().hex[:8]}.json"
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", "41172", "--seed-bc", str(bc),
         "--state-file", str(state_file), "--board", BOARD, "--p-units", P_UNITS,
         "--a-units", A_UNITS, "--p-mow", MOW_VIS, "--hp-target", "90000", "--hp-player", "90000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        pytest.skip(f"build runner MoW KO: {(proc.stderr or proc.stdout or '')[-300:]}")
    rid = json.loads(state_file.read_text())["runnerId"]
    try:
        yield rid
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        for p in (state_file, bc):
            try:
                p.unlink()
            except Exception:
                pass


def _mow(dv):
    return next((m for m in (dv.get("mows") or []) if m.get("visualId") == MOW_VIS), None)


def _ability_state(dv, ability_id):
    m = _mow(dv)
    return next((a for a in ((m or {}).get("abilities") or []) if a.get("id") == ability_id), None)


def test_hailstrike_effect_pose_live(rpc, speeder_runner):
    """`HailstrikeAbility$$ExecuteBehaviour` = AddEffect(1509) sur un ALLIE, duree TurnsFromRounds :
    porteur + type + source + DUREE identiques offline / live."""
    rid = speeder_runner
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    m = _mow(dv)
    if m is None:
        pytest.skip("MoW darkaStormSpeeder non deployee")
    cid = m["casterId"]
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": 1214}, 90)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == 1214), {})
    fh = [x.get("targetId") for x in (ab.get("fromHere") or []) if isinstance(x.get("targetId"), int)]
    if not fh:
        pytest.skip("aucune cible LEGALE pour Hailstrike (fromHere vide)")
    mine = {u["id"] for u in (dv.get("units") or []) if u.get("owner") == m.get("owner")}
    # (1) la legalite native ne propose QUE des ALLIES (i2 : « Targets a friendly unit »).
    assert set(fh).issubset(mine), (
        f"cibles legales Hailstrike {sorted(fh)} deborde de mes unites {sorted(mine)} "
        f"-- l'ability cible un ALLIE")
    tgt = fh[0]

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tgt, "abilityType": 1214},
        "captureEvents": True}, 120)
    assert _ok(cast), f"cast Hailstrike refuse: {str(cast)[:250]}"
    dv3 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    holder = next((u for u in (dv3.get("units") or []) if u["id"] == tgt), {})
    live_eff = [e for e in (holder.get("effects") or [])
                if (e.get("name") or "") == EffectType.Hailstrike.name]
    assert live_eff, (f"aucun effet Hailstrike sur u{tgt} apres le cast "
                      f"(effets: {[e.get('name') for e in (holder.get('effects') or [])]})")

    # --- OFFLINE : meme cast, meme etat de depart -----------------------------------------------
    st = load_state(dv2, ob2, snap2, board=board)
    res = HailstrikeAbility().execute_behaviour(st, cid, tgt)
    assert res is not None and res.get("dsl") is True, f"port 1214 non execute: {res}"
    assert res.get("posed") == [tgt], f"effet pose offline sur {res.get('posed')} != cible {tgt}"
    rounds = int(_const("Hailstrike", "nrOfRounds"))
    want_turns = convert_rounds_to_turns(st, rounds)
    assert res.get("turns") == want_turns, (
        f"duree offline {res.get('turns')} != TurnsFromRounds(nrOfRounds={rounds}) = {want_turns}")
    inst = st.effects.by_unit.get(tgt, []) if st.effects is not None else []
    off = [e for e in inst if e.effect_type == int(EffectType.Hailstrike)]
    assert off, f"aucune instance d'effet 1509 posee offline sur u{tgt}"
    assert int(off[-1].source) == int(cid), (
        f"source de l'effet offline {off[-1].source} != la MoW {cid} "
        f"(le natif passe `caster@0x160` en 4e argument d'AddEffect)")
    # (2) DUREE : le live donne la valeur de reference (TurnsFromRounds, #98).
    live_turns = live_eff[0].get("remainingTurns")
    if live_turns is not None:
        assert int(live_turns) == want_turns, (
            f"remainingTurns live {live_turns} != TurnsFromRounds(nrOfRounds={rounds}) = {want_turns} "
            f"-- un port qui prendrait nrOfRounds pour des TOURS poserait {rounds}")


def test_death_on_the_wind_line_live(rpc, speeder_runner):
    """`DeathOnTheWindAbility$$ExecuteBehaviour` : SET frappe / coups / profil / effet 1257 offline == live.
    Gates natifs traverses AVANT le cast : munitions + cooldown initial + « cible deja attaquee ce tour »."""
    rid = speeder_runner
    ability = 1213
    # (a) attendre les munitions + la fin du cooldown initial (ressource de bataille : on fait tourner
    #     les tours ; l'IA adverse n'est jamais jouee -> aucune contamination du scenario).
    got = None
    for _ in range(12):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        st_ab = _ability_state(dv, ability)
        if st_ab and st_ab.get("usable") and st_ab.get("hasAmmo") is not False \
                and not st_ab.get("cooldown"):
            got = st_ab
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    if got is None:
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        pytest.skip(f"DeathOnTheWind indisponible apres 12 tours (etat: {_ability_state(dv, ability)}) "
                    f"-- munitions/cooldown : NON COUVERT, ce n'est pas un succes")
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    m = _mow(dv)
    cid = m["casterId"]
    myplayer = m.get("owner")
    for _ in range(4):                       # rendre la main a mon camp (les endturn du gate munitions)
        if dv.get("currentPlayer") == myplayer:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
    mine = [u for u in (dv.get("units") or []) if u.get("owner") == myplayer and u.get("alive")]
    if not enemies or not mine:
        pytest.skip("pas d'ennemi/allie disponible")
    # (b0) RAPPROCHER les camps (doctrine drive-positions) : les spawns sont aux deux bouts du board,
    #      aucun allie ne peut frapper au tour 1. On amene un ennemi au contact d'un allie, en plusieurs
    #      tours si necessaire (`applyAction move` respecte la portee de deplacement).
    import hexgeo as _hx
    ally0 = mine[0]
    for _ in range(5):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"])
               for u in (dv.get("units") or []) if u.get("alive") and u.get("pos")}
        if ally0["id"] not in pos or enemies[0]["id"] not in pos:
            break
        if _hx.distance(pos[ally0["id"]], pos[enemies[0]["id"]]) <= 1:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        path = _hx.line(pos[enemies[0]["id"]], pos[ally0["id"]])[1:-1] or [pos[ally0["id"]]]
        for p in reversed(path):
            if p in set(pos.values()):
                continue
            r = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": enemies[0]["id"],
                "to": {"col": p[0], "row": p[1]}}}, 60)
            if _ok(r) and _mut(r):
                break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    for _ in range(3):
        if dv.get("currentPlayer") == myplayer:
            break
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    mine = [u for u in (dv.get("units") or []) if u.get("owner") == myplayer and u.get("alive")]
    enemies = [u for u in (dv.get("units") or []) if u.get("owner") != myplayer and u.get("alive")]
    # (b) GATE `GetDynamicInvalidTargetReason` : la cible doit avoir DEJA recu une attaque CE TOUR.
    #     On la frappe avec un allie (attaque NORMALE, id per-unite resolu du decisionView).
    hit = False
    for u in mine:
        nid = next((a.get("id") for a in (u.get("abilities") or []) if a.get("kind") == "normal"), None)
        if nid is None:
            continue
        for e in enemies:
            r = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": u["id"], "targetId": e["id"], "abilityType": nid}}, 120)
            if _ok(r) and _mut(r):
                hit = True
                victim = e["id"]
                break
        if hit:
            break
    if not hit:
        pytest.skip("aucun allie n'a pu frapper un ennemi (gate `deja attaquee ce tour` non arme)")

    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ability}, 90)
    ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
               if a.get("abilityId") == ability), {})
    # DeathOnTheWind cible une TUILE (`kind=tile`, mesure live) : la tuile de l'ennemi DEJA attaque.
    fh = [(x.get("tile") or {}) for x in (ab.get("fromHere") or []) if x.get("kind") == "tile"]
    if not fh:
        dvx = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        pytest.skip(f"aucune cible LEGALE pour DeathOnTheWind (fromHere vide) alors que u{victim} "
                    f"vient d'etre frappee -- ab={json.dumps(ab)[:300]} "
                    f"mow={json.dumps(_mow(dvx))[:300]} cur={dvx.get('currentPlayer')}")
    dvv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    vpos = next(((u["pos"]["col"], u["pos"]["row"]) for u in (dvv.get("units") or [])
                 if u["id"] == victim and u.get("pos")), None)
    # (c) le gate est PORTANT : SEULE la tuile de l'unite DEJA frappee ce tour est legale.
    assert [(t.get("col"), t.get("row")) for t in fh] == [vpos], (
        f"cibles legales {[(t.get('col'), t.get('row')) for t in fh]} != la seule tuile de l'unite "
        f"frappee u{victim} @{vpos} -- gate `GetNumAttacksReceivedThisTurn != 0` mal compris")
    tcol, trow = fh[0]["col"], fh[0]["row"]

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="native_sym") if (bg or {}).get("tiles") else None
    tgt = board.id_at(tcol, trow) if board is not None else None
    dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    rng0 = rpc("dumpRng", {"runnerId": rid}, 30)
    cast = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "to": {"col": tcol, "row": trow},
        "abilityType": ability}, "captureEvents": True}, 120)
    assert _ok(cast) and _mut(cast), (
        f"cast DeathOnTheWind non applique: {str(cast)[:250]} -- ok/mutated=False + groupe 12 == "
        f"REFUS DE CIBLAGE (case-111), pas une ability inerte")
    live = _live_hits(cast, ability)
    assert live, "aucun degat live attribue a DeathOnTheWind"

    st = load_state(dv2, ob2, snap2, board=board)
    if _ok(rng0):
        st.rng = _seed_rng(rng0)
    res = DeathOnTheWindAbility().execute_behaviour(st, cid, tgt)
    assert res is not None and res.get("dsl") is True, f"port 1213 non execute: {res}"
    off = {h["target"] for h in (res.get("hits") or [])}
    assert off == set(live), (
        f"SET frappe offline {sorted(off)} != live {sorted(live)} "
        f"(ligne de {_const('DeathOnTheWind', 'nrOfTiles')} hexes depuis la tuile de u{tgt})")
    want_hits = int(_const("DeathOnTheWind", "nrOfHits"))
    want_prof = int(DamageProfileType[_const("DeathOnTheWind", "damageProfile")])
    for tid_u, phs in live.items():
        assert len(phs) == want_hits, (
            f"cible {tid_u} : {len(phs)} coups LIVE != oracle config nrOfHits={want_hits}")
        assert {p for _a, p in phs} == {want_prof}, (
            f"cible {tid_u} : profils live {[p for _a, p in phs]} != oracle config {want_prof}")
    # effet 1257 sur les SURVIVANTS (`Alive(enemies)` natif)
    dv3 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    live_buffed = {u["id"] for u in (dv3.get("units") or [])
                   if any((e.get("name") or "") == EffectType.DeathOnTheWind_ExtraPctDamage.name
                          for e in (u.get("effects") or []))}
    assert set(res.get("buffed") or []) == live_buffed, (
        f"porteurs de DeathOnTheWind_ExtraPctDamage offline {sorted(res.get('buffed') or [])} "
        f"!= live {sorted(live_buffed)}")
