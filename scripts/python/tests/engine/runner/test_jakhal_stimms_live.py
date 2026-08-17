"""JakhalStimms (1131, worldJakhal « Macer », WorldEaters) -- face COMBAT (execute) portee, confrontee au LIVE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1 -- namespace natif
`Abilities.Active.Loki.JakhalStimmsAbility`) =
    aoeSel = op_BitwiseAnd( AdjacentUnits(@0x168=caster, 1, 3),      # A : TOUTES unites adjacentes au caster
                            AdjacentFriends(@0x178=target, 1, 3) )   # B : amis-DE-LA-CIBLE (= ennemis caster) adj cible
    ExecuteAtomic( op_BitwiseAnd(                                    # tag 0x2a
        GetAttackBehaviour(@0x178=target),                          # MAIN : AttackWithAttackDamage(Target())
        GetAttackBehaviour(aoeSel) ) )                              # AOE  : AttackWithAttackDamage(intersection)
    Execute( ChangeStat(@0x160=caster, Position(Health=5, current), mode 3=Subtract,                    # SELF-LOSS
             PercentageOf(StatAmount(@0x160, Health, current), ConfigConst(hpPct=25))) )                #   (Execute SEPARE)

`IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$GetAttackBehaviour` = `AttackWithAttackDamage(actor@0x160, sel, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
Nullable(GetDamageProfile), hits = GetHits)`. `GetHits` = `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` (gshared
dedup) = `GetNumberConstant(nrOfHits=0x2f)`. i2 : « Deals 4x [dmg] Physical Damage to an adjacent enemy and all
other enemies adjacent to both Macer and the target. Then Macer loses 25% of his current Health. Using Jakhal
Stimms does not end Macer's turn. » Attaque MELEE, profil Physical (pierce 1) ; config 1131 : constantes
`nrOfHits` (0x2f) et `hpPct`. `native_factory="attack"` (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage, XREF ExecuteBehaviour/GetAttackBehaviour ;
2 tirages/coup a cc=0, cas rngcrit-1202).

ORACLE DU NOMBRE DE COUPS (#96 / lot A) : `ArmoriumCherubAbility$$GetHits` (corps partage, lit ici la config
JakhalStimms) rend `AbilityConfiguration.GetNumberConstant(cfg, 0x2f)` et le passe TEL QUEL a
`AttackWithAttackDamage` -- valeur BRUTE, aucune formule -> l'oracle est la CONFIG
(`gameconfig.ability("JakhalStimms").constants.nrOfHits`, helper `_cfg_hits`), jamais un litteral. Le nb de
coups REELLEMENT emis, lui, est CALCULE (`attack_hits_with_modifiers`, plancher `max(1, ...)`) -> oracle =
le LIVE (port == natif) ; l'egalite avec la constante CONSTATE l'absence de modificateur de canal ici.
RESIDU ASSUME (hors lot nrOfHits) : la constante `hpPct` du self-loss reste ecrite en dur plus bas.

AoE = intersection `AdjacentUnits(caster) & AdjacentFriends(target)`. Le runner `AdjacentFriends` filtre
team==CASTER (PAS subject-relatif comme le natif) -> le natif `AdjacentFriends(target)` (= ennemis-du-caster
adjacents a la cible) est porte via `AdjacentEnemies(TargetTile())` (convention #122 Harvester). Port =
`And(AdjacentUnits(CasterTile()), AdjacentEnemies(TargetTile()))` = ennemis-du-caster adjacents a la FOIS au
caster ET a la cible ; caster exclu (self exclu de AdjacentUnits) + cible exclue (target exclu de
AdjacentEnemies(TargetTile)) = « all OTHER enemies adjacent to both ». Self-loss = feuille
`SubtractHealthPercent` (ChangeStat mode 3 Subtract sur Health fill-up : `hp = Max(hp - round(hp*25/100), 0)`).

Ce que ces tests PROUVENT :
  (a) CAST LIVE bit-exact (Macer PLEINE VIE) : MAIN + AOE per-coup == le port offline (arbre DSL), sous le meme
      rng seede -> les feuilles appellent le pipeline d'attaque fidele. Pleine vie REQUISE : le passif Skullsmasher
      (+extraDmg x floor(PV%-manquant/10)) est un item SEPARE ([opus]+prerequis) NON porte -> gate OFF a 0% manquant.
  (b) GEOMETRIE AoE (intersection) : l'AoE frappe EXACTEMENT les ennemis adjacents a la fois au caster ET a la
      cible ; un ennemi adjacent-caster-SEUL et un ennemi adjacent-cible-SEUL sont EXCLUS ; la cible hors AoE.
  (c) SELF-LOSS : Macer perd round_half_even(25% de son PV COURANT) (`ChangeStat` Subtract), bit-exact live.
  (d) A/B : arbre == sequences directes `execute_ability_attack(hits=4, Physical, "attack")` (main + aoe) -> le
      port n'introduit AUCUN bug de degat.
  (e) NATIVE_FACTORY : la MAIN live == modele "attack" (2 tirages/coup) != "ability" (1 tirage/coup) -> le choix
      "attack" est le bon (discriminant rngcrit-1202).
  (f) DISCRIMINANT Skullsmasher (offline) : a HP REDUIT, le live = offline + un ADDITIF FLAT CONSTANT sur les
      2 x nrOfHits coups (main+aoe) == le passif non porte (mesure : Macer 2368/9035 -> +1400/coup) ; la
      STRUCTURE reste exacte.

ROSTER reaction-free-damage (necroWarden = DangerZone repair/+move, necroOverlord = rien ; PAS de necroDestroyer
= Overwatch) -> le move final de Macer (adjacent aux ennemis) ne le blesse PAS -> Macer PLEINE VIE -> Skullsmasher
OFF (bit-exact PROPRE). Sequence de drive : ennemis d'ABORD, Macer en DERNIER (la legalite `fromHere` se recalcule
a la position courante -> Macer doit bouger APRES les ennemis pour que la cible soit legale).

Drive les positions (memoire « drive positions »). Lit l'etat LIVE, aucune RVA/tuile hardcodee. ASCII only.
State-file UNIQUE par agent (chemin absolu). Skip propre si pas de session / geometrie / legalite infaisable.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import gameconfig as GC

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _config_oracle import damage_profile_pierce    # noqa: E402

import hexgeo

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
AGENT = "a388f0e726af0c52"                                   # id agent -> state-file unique (coexistence runners)
CASTER_VIS = "worldJakhal"
ABILITY = 1131
# reaction-free-damage : necroWarden (DangerZone = +move/repair) + necroOverlord (rien). PAS de necroDestroyer
# (Overwatch_AutoAttack) -> le move final de Macer adjacent aux ennemis ne le blesse pas -> pleine vie.
A_UNITS = "necroWarden,necroOverlord,necroWarden,necroOverlord"


# ------------------------------------------------------------------ helpers

def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _cfg_hits(key: str = "nrOfHits") -> int:
    """ORACLE du nb de coups = la CONSTANTE de config de JakhalStimms, PAS un litteral.
    `IdunBattleLogic.Entities.Abilities.Active.Loki.JakhalStimmsAbility$$GetAttackBehaviour` passe
    `hits = IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` (corps partage)
    = `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(cfg, 0x2f)` a
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` : valeur BRUTE (aucune formule), donc
    l'oracle est `gameconfig.ability("JakhalStimms").constants[<key>]`."""
    c = (GC.ability("JakhalStimms") or {}).get("constants") or {}
    v = c.get(key)
    assert v is not None, (f"oracle introuvable : constants.{key} absent de gameconfig pour JakhalStimms "
                           f"(GetNumberConstant(0x2f) non resolvable offline)")
    return int(v)


# NEUTRALISATION CRIT/BLOCK SUR LES QUATRE FACES (#506, remede-type de #419-r6-r1 §3.3).
# Ce fichier compare un degat PER-COUP BIT-EXACT, et son montage EXIGE deja explicitement
# `crit_chance == 0` (`pytest.skip(f"crit_chance={cc} != 0 (bit-exact requiert cc=0)")`). Depuis
# `c4be3896` (#419-r6, le defaut passe a << equiper >>), le caster porte `crit_chance = 26` : les
# TROIS tests partaient en skip et le fichier rendait `0 passed / 3 skipped`, soit le garde #455
# (`passed == 0 and skipped > 0`) -- ZERO assertion evaluee, et invisible d'un `rc`.
# On epingle QUATRE SCALAIRES sur CE montage plutot que `--no-bis-items`, qui restituerait le regime
# DEGENERE global. Le skip RESTE en place : il garde toujours la premisse, il n'est simplement plus
# arme -- si un jour le crit revenait par une autre voie, il rougirait de nouveau au garde #455.
_NO_CRIT_BLOCK = ["--crit", "0,0", "--crit-target", "0,0",
                  "--block-player", "0,0", "--block-target", "0,0"]


def _build(seed: str, a_units: str = A_UNITS):
    """Build un runner ISOLE (state-file unique agent+tag, chemin absolu). Renvoie (rid, state_file)."""
    tag = uuid.uuid4().hex[:8]
    state_file = ROOT / "logs" / "runners" / f"jakhal-{AGENT}-{seed}-{tag}.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(state_file),
         "--board", "MC1_67", "--p-units", CASTER_VIS, "--a-units", a_units, "--hp-target", "300000",
         *_NO_CRIT_BLOCK],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not state_file.exists():
        return None, state_file
    return json.loads(state_file.read_text())["runnerId"], state_file


def _cleanup(rpc, rid, state_file):
    if rid:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
    try:
        if state_file is not None:
            state_file.unlink()
    except Exception:
        pass


def _mk_rng(s):
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _mv(rpc, rid, uid, c):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": c[0], "row": c[1]}}}, 60)


def _legal_fromhere(rpc, rid, cid):
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
    a = next((x for x in ((at.get("units") or [{}])[0].get("abilities") or [])
              if x.get("abilityId") == ABILITY), {})
    return set(x.get("targetId") for x in (a.get("fromHere") or []))


def _hp_ob(ob, uid):
    for u in (ob.get("units") or []):
        if u.get("squadId") == uid and not u.get("isDead"):
            return u.get("hp")
    return None


def _live_dmg_by_target(cast):
    live = {}
    for a in (cast.get("actions") or []):
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                live.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return live


def _drive(rpc, rid, board):
    """Place la cible T (>=4 voisins libres), un ennemi AoE E1 sur un voisin COMMUN de C et T, un ennemi E2 sur
    un voisin de C hors T (prune), un ennemi E3 sur un voisin de T hors C (prune), PUIS deplace Macer sur C EN
    DERNIER (legalite `fromHere` recalculee a la position courante). Renvoie (dv, cid, tid, e1, e2, e3) ou (None,..)."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    if me is None:
        return (None,) * 6
    myp = me.get("owner"); cid = me["id"]
    ens = [u for u in (dv.get("units") or []) if u.get("owner") != myp and u.get("alive")]
    if len(ens) < 4:
        return (None,) * 6

    def walk_nbrs(t):
        return [n for n in board.neighbours(t) if board.walkable(n)]
    T = next((t for t in sorted(board.by_id) if board.walkable(t) and len(walk_nbrs(t)) >= 4), None)
    if T is None:
        return (None,) * 6
    tn = walk_nbrs(T)
    C = tn[0]
    cn = walk_nbrs(C)
    shared = [n for n in cn if n in tn]                       # adjacents aux DEUX
    c_only = [n for n in cn if n not in tn and n != T]        # adjacent C seulement
    t_only = [n for n in tn if n not in cn and n != C]        # adjacent T seulement
    if not shared or not c_only or not t_only:
        return (None,) * 6
    tgt, e1, e2, e3 = ens[0], ens[1], ens[2], ens[3]
    # ennemis d'ABORD (target/E1/E2/E3), Macer EN DERNIER
    _mv(rpc, rid, tgt["id"], board.coord(T))
    _mv(rpc, rid, e1["id"], board.coord(shared[0]))
    _mv(rpc, rid, e2["id"], board.coord(c_only[0]))
    _mv(rpc, rid, e3["id"], board.coord(t_only[0]))
    _mv(rpc, rid, cid, board.coord(C))
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    return dv, cid, tgt["id"], e1["id"], e2["id"], e3["id"]


# ------------------------------------------------------------------ (a)+(b)+(c)+(d)+(e) LIVE cast pleine vie

@pytest.mark.parametrize("seed", ["777", "31337"])
def test_jakhal_stimms_live_bitexact(live_session, rpc, seed):
    """(a) MAIN + AOE live per-coup == arbre DSL offline (bit-exact, Macer PLEINE VIE -> Skullsmasher OFF) ;
    (b) AoE = intersection (E1 adjacent-both frappe ; E2/E3 mono-adjacents exclus ; cible hors AoE) ;
    (c) self-loss = 25% PV courant (bit-exact live) ; (d) A/B arbre == sequences directes ; (e) native_factory
    "attack" (2 tirages/coup) != "ability"."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent, HealthComponent
    from engine.runner.abilities.worldeaters import JakhalStimmsAbility
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.operations.damage import AttackDamageOperation

    rid, state_file = _build(seed)
    if rid is None:
        pytest.skip("build runner KO (rl_duel)")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        dv, cid, tid, e1, e2, e3 = _drive(rpc, rid, board)
        if cid is None:
            pytest.skip("drive/position/geometrie infaisable")
        if tid not in _legal_fromhere(rpc, rid, cid):
            pytest.skip("cast non legal fromHere (geometrie)")

        ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap is None or not _ok(s0):
            pytest.skip("combatSnapshot/dumpRng indispo")

        def mkstate():
            st = load_state(dv, ob0, snap, board=Board(bg["tiles"], adjacency="native_sym"))
            return st

        st0 = mkstate()
        ce = st0.get_entity(cid)
        cc = int(getattr(ce.get_component(StatsComponent).ctx, "crit_chance", 0) or 0)
        hc = ce.get_component(HealthComponent)
        if cc != 0:
            pytest.skip(f"crit_chance={cc} != 0 (bit-exact requiert cc=0)")
        if hc.hp != hc.hp_max:
            pytest.skip(f"Macer non pleine vie ({hc.hp}/{hc.hp_max}) -> Skullsmasher ON (voir test discriminant)")
        hp0 = int(hc.hp)

        # --- LIVE cast ---
        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        assert _ok(cast), f"cast JakhalStimms non applique: {str(cast)[:200]}"
        live = _live_dmg_by_target(cast)
        live_main = live.get(tid) or []
        live_aoe = live.get(e1) or []
        if not live_main:
            pytest.skip(f"aucun degat live JakhalStimms (cast no-op ; targets live={sorted(live)})")
        # Oracle CONFIG (nrOfHits est lu tel quel par GetHits) ; le nb EMIS etant calcule, cette egalite
        # CONSTATE en meme temps qu'aucun modificateur de canal de coups n'agit dans ce setup -- condition
        # du bit-exact per-coup indice-par-indice plus bas.
        cfg_hits = _cfg_hits()
        assert len(live_main) == cfg_hits, (
            f"coups main live {len(live_main)} != oracle "
            f"gameconfig.ability('JakhalStimms').constants.nrOfHits={cfg_hits}")
        assert len(live_aoe) == cfg_hits, (
            f"coups aoe live {len(live_aoe)} != oracle constants.nrOfHits={cfg_hits}")
        # DISCRIMINANT (e) : la separation native_factory attack/ability commence au coup 2.
        assert cfg_hits >= 2, (
            f"setup NON discriminant : nrOfHits={cfg_hits} < 2 -> le volet (e) native_factory ne peut "
            f"plus rougir (les deux familles partagent le 1er tirage)")
        # (b) geometrie : E2 (adjacent-C-only) et E3 (adjacent-T-only) EXCLUS ; cible hors AoE
        assert (live.get(e2) or []) == [], f"E2 (adjacent-caster-seul) touche a tort: {live.get(e2)}"
        assert (live.get(e3) or []) == [], f"E3 (adjacent-cible-seul) touche a tort: {live.get(e3)}"
        # (c) self-loss live = 25% PV courant
        hp_after = _hp_ob(rpc("observeBattle", {"runnerId": rid}, 40), cid)
        exp_loss = round(hp0 * 25 / 100)
        assert hp_after is not None and (hp0 - hp_after) == exp_loss, \
            f"self-loss live {hp0}-{hp_after}={hp0 - (hp_after or 0)} != round(25% de {hp0})={exp_loss}"

        # --- port offline (arbre DSL) meme rng ---
        st_tree = mkstate(); st_tree.rng = _mk_rng(s0)
        res = JakhalStimmsAbility().execute_behaviour(st_tree, cid, tid)
        assert res is not None and res.get("dsl") is True, f"port non execute: {res}"
        tree_main = (res.get("main_attack") or {}).get("per_hit") or []
        aoe = res.get("aoe") or []
        aoe_ids = sorted(x["target"] for x in aoe)
        tree_aoe = (aoe[0]["attack"].get("per_hit") if aoe else []) or []

        # (a) bit-exact vs LIVE (main + aoe) ; (b) AoE ids == [E1]
        assert tree_main == live_main, \
            f"arbre MAIN {tree_main} != LIVE {live_main} (bit-exact cc=0 pleine vie, native_factory attack)"
        assert aoe_ids == [e1], f"aoe ids {aoe_ids} != [{e1}] (intersection adjacent-both)"
        assert tree_aoe == live_aoe, f"arbre AOE {tree_aoe} != LIVE {live_aoe} (bit-exact intersection)"
        # (c) self-loss offline == live
        assert (res.get("self_loss") or {}).get("amount") == exp_loss, \
            f"self-loss offline {(res.get('self_loss') or {}).get('amount')} != {exp_loss}"

        # (d) A/B : arbre == sequences directes execute_ability_attack (main puis aoe, meme rng)
        st_dir = mkstate(); st_dir.rng = _mk_rng(s0)
        bmin, bmax, pierce, hh = ability_attack_params(st_dir, cid, "JakhalStimms", "Physical", ranged=False)
        assert hh == cfg_hits, (
            f"ability_attack_params rend nrOfHits={hh} != oracle constants.nrOfHits={cfg_hits} "
            f"(GetHits 0x2f)")
        # PERCAGE = valeur BRUTE (`StaticBattleRules.Damage$$GetPiercingRatio` lit
        # `DamageProfile.PiercingDamageRatio` tel quel) -> oracle = CONFIG, cle nommee.
        pierce_cfg = damage_profile_pierce("Physical")
        assert pierce == pierce_cfg, \
            f"pierce {pierce} != damageProfiles.Physical.PiercingRatio ({pierce_cfg})"
        d_main = (AttackDamageOperation.execute_ability_attack(
            st_dir, cid, tid, bmin, bmax, pierce, hh,
            damage_profile="Physical", is_melee=True, is_attack_damage_op=True) or {}).get("per_hit")
        d_aoe = (AttackDamageOperation.execute_ability_attack(
            st_dir, cid, e1, bmin, bmax, pierce, hh,
            damage_profile="Physical", is_melee=True, is_attack_damage_op=True) or {}).get("per_hit")
        assert tree_main == d_main, f"arbre MAIN {tree_main} != sequence directe {d_main}"
        assert tree_aoe == d_aoe, f"arbre AOE {tree_aoe} != sequence directe {d_aoe}"

        # (e) native_factory discriminant : "ability" (1 tirage/coup) DIVERGE du live des le coup >=2
        st_ab = mkstate(); st_ab.rng = _mk_rng(s0)
        off_ability = (AttackDamageOperation.execute_ability_attack(
            st_ab, cid, tid, bmin, bmax, pierce, hh,
            damage_profile="Physical", is_melee=True, is_attack_damage_op=False) or {}).get("per_hit")
        assert off_ability != live_main, \
            (f"modele 'ability' {off_ability} == LIVE {live_main} : native_factory ne separe pas (attendu desync coup 2)")
        print(f"[jakhal live seed={seed}] MAIN live={live_main}==tree | AOE(E1={e1}) live={live_aoe}==tree | "
              f"self-loss={exp_loss} (hp {hp0}->{hp_after}) | A/B ok | native_factory attack DISCRIMINE")
    finally:
        _cleanup(rpc, rid, state_file)


# ------------------------------------------------------------------ (f) DISCRIMINANT Skullsmasher (offline, HP reduit)

def _drive_overwatch(rpc, rid, board):
    """Comme `_drive` mais place le necroDestroyer (Overwatch) sur le voisin COMMUN de C et T (shared) : il est a
    la fois la cible AoE (adjacent-both) ET l'Overwatch declencheur -> le move final de Macer sur C le fait entrer
    a portee -> overwatch -> Macer BLESSE -> Skullsmasher ON. target=necroWarden@T, E1(AoE)=necroDestroyer@shared.
    Renvoie (dv, cid, tid, e1) ou (None,..)."""
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    me = next((u for u in (dv.get("units") or []) if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
    if me is None:
        return (None,) * 4
    myp = me.get("owner"); cid = me["id"]
    ens = [u for u in (dv.get("units") or []) if u.get("owner") != myp and u.get("alive")]
    dest = next((u for u in ens if u.get("visualId") == "necroDestroyer"), None)
    tgt = next((u for u in ens if u.get("visualId") == "necroWarden"), None)
    if dest is None or tgt is None:
        return (None,) * 4

    def walk_nbrs(t):
        return [n for n in board.neighbours(t) if board.walkable(n)]
    T = next((t for t in sorted(board.by_id) if board.walkable(t) and len(walk_nbrs(t)) >= 4), None)
    if T is None:
        return (None,) * 4
    tn = walk_nbrs(T)
    C = tn[0]
    cn = walk_nbrs(C)
    shared = [n for n in cn if n in tn]
    if not shared:
        return (None,) * 4
    _mv(rpc, rid, tgt["id"], board.coord(T))
    _mv(rpc, rid, dest["id"], board.coord(shared[0]))         # Overwatch adjacent-both -> declenche + cible AoE
    _mv(rpc, rid, cid, board.coord(C))
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    return dv, cid, tgt["id"], dest["id"]


def test_jakhal_stimms_skullsmasher_is_flat_and_separate(live_session, rpc):
    """(f) A HP REDUIT (overwatch d'un necroDestroyer adjacent au move final de Macer), le live per-coup = le
    port offline + un ADDITIF FLAT CONSTANT (identique sur les 2 x nrOfHits coups main+aoe) = le passif
    Skullsmasher (+extraDmg x floor(PV%-manquant/10)), item SEPARE NON porte. Prouve que la STRUCTURE (ordre rng, hit-count,
    geometrie) reste EXACTE et que la seule divergence est ce passif flat. Skip si Macer reste pleine vie."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent, HealthComponent
    from engine.runner.abilities.worldeaters import JakhalStimmsAbility

    rid, state_file = _build("777", a_units="necroWarden,necroOverlord,necroDestroyer,necroWarden")
    if rid is None:
        pytest.skip("build runner KO (rl_duel)")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        dv, cid, tid, e1 = _drive_overwatch(rpc, rid, board)
        if cid is None:
            pytest.skip("drive/position/geometrie infaisable (roster overwatch)")

        ob0 = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if snap is None or not _ok(s0):
            pytest.skip("capture indispo")
        st0 = load_state(dv, ob0, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        ce = st0.get_entity(cid)
        cc = int(getattr(ce.get_component(StatsComponent).ctx, "crit_chance", 0) or 0)
        hc = ce.get_component(HealthComponent)
        if cc != 0:
            pytest.skip(f"crit_chance={cc} != 0")
        if hc.hp == hc.hp_max:
            pytest.skip("Macer pleine vie (overwatch n'a pas fire) -> Skullsmasher OFF (canal flat non exercable)")
        if tid not in _legal_fromhere(rpc, rid, cid):
            pytest.skip("cast non legal fromHere")

        cast = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
            "captureEvents": True}, 120)
        if not _ok(cast):
            pytest.skip("cast non applique")
        live = _live_dmg_by_target(cast)
        live_main = live.get(tid) or []
        live_aoe = live.get(e1) or []
        cfg_hits = _cfg_hits()
        # Le SKIP ne couvre que l'indisponibilite REELLE du scenario (pas de cast, ou pas de cible AoE
        # a cause de la geometrie/overwatch). Un cast qui a bien eu lieu mais avec un nombre de coups
        # different de l'oracle est une DIVERGENCE, pas une indisponibilite : elle doit ROUGIR (les PV
        # sont tunes a 300000, aucun coup ne peut etre absorbe par une mort).
        if not live_main or not live_aoe:
            pytest.skip(f"cast live sans cible exploitable (main={len(live_main)} aoe={len(live_aoe)})")
        assert len(live_main) == cfg_hits and len(live_aoe) == cfg_hits, (
            f"coups live main={len(live_main)} aoe={len(live_aoe)} != oracle "
            f"gameconfig.ability('JakhalStimms').constants.nrOfHits={cfg_hits}")

        st = load_state(dv, ob0, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        st.rng = _mk_rng(s0)
        res = JakhalStimmsAbility().execute_behaviour(st, cid, tid)
        off_main = (res.get("main_attack") or {}).get("per_hit") or []
        aoe = res.get("aoe") or []
        off_aoe = (aoe[0]["attack"].get("per_hit") if aoe else []) or []

        diffs = [lm - om for lm, om in zip(live_main, off_main)] + [la - oa for la, oa in zip(live_aoe, off_aoe)]
        assert len(diffs) == 2 * cfg_hits, \
            f"attendu {2 * cfg_hits} coups (nrOfHits={cfg_hits} main + autant en aoe), obtenu {len(diffs)}"
        flat = diffs[0]
        assert flat > 0, f"additif Skullsmasher {flat} <= 0 (HP reduit attendu -> +extraDmg > 0)"
        assert all(d == flat for d in diffs), \
            (f"diffs live-offline {diffs} NON constants : la divergence n'est PAS un additif flat -> structure "
             f"suspecte (rng/hit-count/geometrie), pas seulement le passif Skullsmasher")
        print(f"[jakhal skullsmasher] HP reduit ({hc.hp}/{hc.hp_max}) -> live = offline + {flat} FLAT sur "
              f"{len(diffs)} coups (main+aoe) = passif Skullsmasher NON porte ; structure EXACTE")
    finally:
        _cleanup(rpc, rid, state_file)
