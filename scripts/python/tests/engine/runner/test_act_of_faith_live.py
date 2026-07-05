"""VECTEUR MORT — trait ActOfFaith (Adepta Sororitas) : replay-diff LIVE vs moteur.

Valide le vecteur trigger MORT (`OnDeathEvent`/`On(1)`) + l'effet StatModification `ActOfFaithBuffEffect` :
quand un allié **Imperial** TUE un ennemi (ou meurt), chaque Battle Sister vivante (trait `ActOfFaith`,
crit_dmg != 0) gagne un stack de buff crit → `ChangeStat` crit-chance += `actOfFaithExtraCritChance` (=10)
FLAT, crit-damage += `Ceiling(crit_dmg_courant × actOfFaithExtraCritDmgPct% =25%)` (compound).

Fixture = une Sister (`adeptCanoness`, crit forcé 20,200 → gate `crit_dmg != 0` OK, base nette ; ne bouge/
n'attaque PAS → jamais de reset) + un allié Imperial (`admecDestroyer`, AdeptusMechanicus) conduit jusqu'à
TUER un ennemi `--hp-target` (PV bas + armure 0 = kill déterministe). Sur le coup qui tue :
  • LIVE : on confronte la stat crit de la Sister AVANT/APRÈS (combatSnapshot) = +10 cc / +ceil(cd×25%) cd ;
  • MOTEUR : on REJOUE l'attaque tueuse offline (load_state AVANT + RNG calé dumpRng + board evenq) →
    `execute` tue l'ennemi → `_fire_death_if_killed` → `after_death_triggers` → accumulation ActOfFaith →
    on confronte la ctx crit de la Sister du moteur == stat crit live APRÈS. Bit-exact.

⚠ ADJACENCE/PORTÉE = mode **evenq** (cf. test_overwatch_live : la capture native est partielle).
"""
from __future__ import annotations

import math
from collections import deque

from engine.entities.stats import StatType

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import AttackUnitMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent, HealthComponent

SISTER_VIS = "adeptCanoness"        # trait ActOfFaith ; --crit 20,200 → cd != 0 (gate) ; parquée (no reset)
ALLY_VIS = "admecDestroyer"         # allié Imperial (AdeptusMechanicus) heavy ranged = tueur
ENEMY_VIS = "necroDestroyer"        # Xenos, --hp-target → 200 PV / 0 armure (one-shottable)
ENEMY2_VIS = "necroOverlord"        # 2e ennemi : la bataille continue après le 1er kill (snapshot lisible)
ACTOFFAITH_CC = 10                  # actOfFaithExtraCritChance (globalValues)
ACTOFFAITH_CD_PCT = 25             # actOfFaithExtraCritDmgPct (globalValues)
BUILD = ["--roster", "1", "--p-units", f"{SISTER_VIS},{ALLY_VIS}",
         "--a-units", f"{ENEMY_VIS},{ENEMY2_VIS}", "--crit", "20,200", "--hp-target", "200"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _bfs(board, src):
    dist = {src: 0}; q = deque([src])
    while q:
        x = q.popleft()
        for n in board.neighbours(x):
            if n not in dist:
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def _snap_crit(snap, eid):
    """(critChance, critDamage) de l'entité eid dans un combatSnapshot, ou (None, None)."""
    for u in (snap.get("units") or []):
        if u.get("entityId") == eid:
            s = u.get("stats") or {}
            return s.get("critChance"), s.get("critDamage")
    return None, None


def _snap_hp(snap, eid):
    for u in (snap.get("units") or []):
        if u.get("entityId") == eid:
            return (u.get("stats") or {}).get("health")
    return None


def test_act_of_faith_accumulation_bit_exact(live_session, rpc, build_runner):
    """Le kill d'un ennemi par un allié Imperial accorde à la Sister +10 cc / +ceil(cd×25%) cd
    (live), et le moteur reproduit exactement la stat crit résultante (replay de l'attaque tueuse)."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")

    def tof(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    dec0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    if not _ok(dec0):
        pytest.skip("decisionView KO")
    units0 = dec0.get("units") or []
    sister = next((u for u in units0 if u.get("visualId") == SISTER_VIS and u.get("alive")), None)
    ally = next((u for u in units0 if u.get("visualId") == ALLY_VIS and u.get("alive")), None)
    if sister is None or ally is None:
        pytest.skip(f"unite absente (sister={bool(sister)} ally={bool(ally)})")
    my_player = ally.get("owner")
    sister_id, ally_id = sister["id"], ally["id"]

    import gameconfig as GC
    ally_weapons = (GC.unit(ALLY_VIS) or {}).get("weapons") or []
    R = max([int(w.get("Range") or 0) for w in ally_weapons] or [0]) or 1

    killed = None
    for _turn in range(40):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            break
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        us = dec.get("units") or []
        al = next((u for u in us if u["id"] == ally_id and u.get("alive")), None)
        si = next((u for u in us if u["id"] == sister_id and u.get("alive")), None)
        if al is None or si is None:
            pytest.skip("ally/sister disparu pendant l'approche")
        # cibler un ennemi VIVANT en gardant >=1 autre ennemi vivant (la bataille doit continuer
        # apres le kill pour lire la stat de la Sister).
        enemies = [u for u in us if u.get("team") != al.get("team") and u.get("alive") and u.get("pos")]
        if len(enemies) < 2:
            pytest.skip("besoin de >=2 ennemis vivants pour confronter apres le kill")
        target = enemies[0]
        tgt_id = target["id"]
        a_tile, t_tile = tof(al), tof(target)
        if a_tile is None or t_tile is None:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        dgoal = _bfs(board, t_tile)
        in_range = dgoal.get(a_tile, 99) <= R

        if not in_range:
            # s'approcher : tuile atteignable minimisant la distance hex a la cible (sans aller adjacent).
            mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == ally_id), None)
            reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                     for t in ((cmt or {}).get("tiles") or [])}
            pool = [t for t in reach if t in dgoal and dgoal[t] >= 1]
            if not pool:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
            best = min(pool, key=lambda t: dgoal[t]); col, row = reach[best]
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": ally_id, "to": {"col": col, "row": row}}}, 40)
            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            al = next((u for u in (dec.get("units") or []) if u["id"] == ally_id), None)
            a_tile = tof(al) if al else None
            if a_tile is None or dgoal.get(a_tile, 99) > R:
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue

        # === en portee : resoudre l'ability d'attaque (plan ally->target) ===
        ability = None
        for p in (dec.get("attackPlans") or []):
            if p.get("unitId") == ally_id:
                for ev in (p.get("evals") or []):
                    if ev.get("targetId") == tgt_id:
                        ability = ev.get("abilityId"); break
        if ability is None:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue

        # === capture AVANT l'attaque (etat + RNG cale + crit Sister + hp ennemi) ===
        snap_b = rpc("combatSnapshot", {"runnerId": rid}, 60)
        ob_b = rpc("observeBattle", {"runnerId": rid}, 40)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        cc_b, cd_b = _snap_crit(snap_b, sister_id)
        hp_b = _snap_hp(snap_b, tgt_id)
        if cc_b is None or cd_b is None or hp_b is None or not _ok(s0):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue

        # === attaque LIVE ===
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": ally_id, "targetId": tgt_id, "abilityType": ability}}, 60)
        snap_a = rpc("combatSnapshot", {"runnerId": rid}, 60)
        hp_a = _snap_hp(snap_a, tgt_id)
        cc_a, cd_a = _snap_crit(snap_a, sister_id)

        if hp_b > 0 and (hp_a == 0 or hp_a is None):
            # KILL : le coup a tue l'ennemi → confronter
            killed = {"cc_b": cc_b, "cd_b": cd_b, "cc_a": cc_a, "cd_a": cd_a,
                      "tgt_id": tgt_id, "hp_b": hp_b, "hp_a": hp_a,
                      "dec_b": dec, "ob_b": ob_b, "snap_b": snap_b, "rng": s0, "ability": ability}
            break
        # pas de kill (whittle) → fin de tour, on recommence
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    if killed is None:
        pytest.skip("aucun kill par l'allie Imperial en 40 tours (portee/degats)")

    k = killed
    exp_cc = k["cc_b"] + ACTOFFAITH_CC
    exp_cd = k["cd_b"] + math.ceil(k["cd_b"] * ACTOFFAITH_CD_PCT / 100)
    print(f"\n[ACTOFFAITH] Sister crit AVANT cc={k['cc_b']} cd={k['cd_b']} | "
          f"APRES live cc={k['cc_a']} cd={k['cd_a']} | attendu cc={exp_cc} cd={exp_cd}")

    # (1) FORMULE LIVE : le kill d'un allie Imperial accorde EXACTEMENT +10 cc / +ceil(cd_b x 25%) cd.
    assert k["cd_b"] != 0, "base crit_damage nulle (gate ActOfFaith) — --crit non applique a la Sister ?"
    assert k["cc_a"] == exp_cc, f"live crit_chance {k['cc_a']} != attendu {exp_cc} (+{ACTOFFAITH_CC})"
    assert k["cd_a"] == exp_cd, (f"live crit_damage {k['cd_a']} != attendu {exp_cd} "
                                 f"(+ceil({k['cd_b']}x{ACTOFFAITH_CD_PCT}%))")

    # (2) MOTEUR : rejouer l'attaque tueuse offline → l'ennemi meurt → vecteur MORT → accumulation
    #     ActOfFaith. La stat crit de la Sister cote moteur doit == la stat crit live APRES (bit-exact).
    state = load_state(k["dec_b"], k["ob_b"], k["snap_b"])
    state.board = board
    state.rng = _seed_rng(k["rng"])
    si_off = state.get_entity(sister_id)
    en_off = state.get_entity(k["tgt_id"])
    if si_off is None or si_off.get_component(StatsComponent) is None or en_off is None:
        pytest.skip("Sister/ennemi sans composant offline (combatSnapshot ne couvre pas)")
    runner = Runner(state).install_default_handlers(20)
    runner.apply(AttackUnitMessage(ally_id, k["tgt_id"]))

    en_hp_off = en_off.get_component(HealthComponent).hp
    ctx = si_off.get_component(StatsComponent).ctx
    # crit courant lu via le systeme de stats porte (get_stat) : le champ plat ctx.crit_chance n'est plus
    # synchronise depuis le retrait de la synchro ChangeStat (la mutation vit dans UnitStats).
    cc_off, cd_off = ctx.stat(StatType.CRIT_CHANCE), ctx.stat(StatType.CRIT_DAMAGE)
    print(f"[ACTOFFAITH] moteur : ennemi hp={en_hp_off} | Sister crit cc={cc_off} cd={cd_off}")
    assert en_hp_off == 0, f"moteur n'a pas tue l'ennemi (hp={en_hp_off}) → vecteur MORT non declenche"
    assert cc_off == k["cc_a"], f"moteur cc {cc_off} != live {k['cc_a']}"
    assert cd_off == k["cd_a"], f"moteur cd {cd_off} != live {k['cd_a']}"
