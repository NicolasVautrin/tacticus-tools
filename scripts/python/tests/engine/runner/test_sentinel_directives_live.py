"""SentinelDirectives (actif 1139, admecDestroyer « Sy-Gex » AdeptusMechanicus) PORT -> arbre DSL, confronte
au LIVE (case-220 §6.17).

`SentinelDirectivesAbility$$IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour` (DECOMPILE, mirror 1:1 -- cf. `abilities/admec.py`) =
    Execute( op_Addition( op_Addition(
        InformWeapon(GetDamageProfile=Physical),                                          # metadata arme
        AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                               GetDamageProfile=Physical, nrOfHits=ConfigConst(0x2f)=1) ),  # attaque 1x ranged
        AddEffect(0x429=1065 Pinned, source=AbilityStateReference, target@0x178, dureeNode=0) ) )  # Pin cible
plain `Execute` (l'op_Addition passe DIRECTEMENT a `AActiveAbility.Execute`, aucun AtomicGroup). Quasi-clone de
SpiritLeech MOINS le degat conditionnel (GetAttackDamage) et le lifesteal (Heal). `native_factory="attack"`
(la CALLEE de IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`, JAMAIS `AttackWithAbilityDamage`). Mono-coup ->
non concerne par le desync per-hit (tip #2). « Does not end Sy-Gex's turn » = SetsEndTurnFlags/
SetsActiveAbilityUsedFlag=False (1139 dans les frozensets base.py).

Ce que ces tests PROUVENT (lit l'etat LIVE ; drive les positions ; state-file UNIQUE dispose au teardown) :
  (1) EXECUTION REELLE : cast route -> `ported=True` (garde anti-no-op silencieux) + `InformWeapon(Physical)`.
  (2) EFFET PINNED : la cible recoit Pinned (0x429=1065, source=caster) LIVE == materialise offline.
  (3) TURN-FLOW (finesse) : apres le cast, le caster NE finit PAS son tour (flags turn_finished=False +
      ActiveAbilityUsed non pose) -> currentPlayer inchange live (peut re-agir / Overwatch).
  (4) TREE FIDELE : la feuille AttackWithAttackDamage emet la MEME Operation que `execute_ability_attack`
      direct (A/B bit-exact, native_factory attack) -> l'arbre n'introduit AUCUN bug de degat ; la valeur
      brute tiree est dans les bornes config [minDmg,maxDmg][level].
  (5) DEGAT BIT-EXACT live == offline (EGALITE, plus l'ancienne inegalite molle) : les deux passifs
      caster-intrinseques sont portes (cf. plus bas), donc plus aucun confond a absorber.
  (6) FLAG `Moved` LU DU LIVE : le `UnitFlagsComponent` de l'etat offline est seede par
      `combatSnapshot.units[].unitFlags`, et ce que le canal rend concorde avec les deplacements que
      la fixture a REELLEMENT emis ce tour. Garde du canal : un `unitFlags` NON MESURE (`null`) ferait
      retomber `load_state` sur « n'a pas bouge » et rendrait le +25% ranged EN SILENCE.

ORACLES DES PARAMS (#96 -- aucun scalaire de gameplay fige ici). Le decompile TRANCHE : dans
`IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour`, le nb de coups
part de `IdunBattleLogic.Entities.DSLFormulas$$ConfigConst(0x2f)` et le profil de
`IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile`, tous deux passes DIRECTEMENT a
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` -- aucune formule (et
`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant` = `GetStringConstant` +
`System.Int32.Parse`). Valeurs BRUTES -> l'oracle est la CONFIG :
`gameconfig.ability("SentinelDirectives").constants` (`nrOfHits`, `damageProfile`, `range`) et
`gameconfig.damage_profile(<profil>).PiercingRatio`. Cle non ambigue : enum `AbilityConstantType`
0x2f=nrOfHits(47) vs 0x16=range(22) (cf. `engine/entities/formulas.py::ConfigConst`).

PASSIF DU CASTER, DESORMAIS PORTE (l'ancien residu de ce fichier) : le seul porteur de 1139 (Sy-Gex)
porte aussi `HeavyGravCannon` (EffectType 1291) --
`IdunBattle.Entities.Effects.Loki.HeavyGravCannonEffect$$CreateEffectDamageBonusForAttack` =
ForAddition(cond, ConfigVar(8=extraDmg)) et `...$$CreatePiercingBonusForAttack` = ForPiercing(cond,
ConfigVar(0x3f=extraPierceRatio)), avec `...$$DamageCondition` = OwnerIsActor & IsRangedAttack &
(HasTrait(target, 5=Mechanical) | HasTrait(target, 0x3f5=1013 MkXGravis) |
HasTrait(target, 0x40f=1039 TerminatorArmour)). La cible de ce test, `necroOverlord`, EST Mechanical ->
la condition est VRAIE. Le port (`entities/effects/loki/extra_damage.py::HeavyGravCannonEffect`) le rend
maintenant DES DEUX COTES, d'ou l'assertion d'EGALITE BIT-EXACTE plus bas (elle valait `live >= offline`
tant que le flat manquait). MESURE : avant port off 3067 / live 3510 = +443 = `extraDmg[50] x 160%` ;
apres port off == live == 3510. Le canal PERCAGE est INERTE sur CE montage (le percage natif est un
PLANCHER `max(0, d - armure, d x pierce%)` et `d - armure` domine face a l'armure 1909) -- il est
confronte separement, sur une cible a armure haute, par `test_heavy_grav_cannon_live`.

`HeavyWeapon_ExtraDmg` (1008, +25% ranged) N'EST PAS un confond (#101) : son gate natif
`!HasFlag(Moved=0) | HasFlag(Teleported=0xc)` est lu des DEUX cotes sur le MEME store (le
`UnitFlagsComponent`), et l'etat de ce store vient du LIVE -- `combatSnapshot.units[].unitFlags` rend
les ids `UnitFlag` POSES (obtenus en invoquant la fonction NOMMEE
`IdunBattle.Entities.UnitExtensions$$HasFlag(unit, flag)` une fois par valeur d'enum), et
`snapshot._load_unit_flags` les seede sur l'etat charge. L'approche du caster emet des `move` : le
natif pose `Moved`, le canal le remonte, le port le lit -> le bonus est OFF live comme offline, sans
aucune pose manuelle. Le gate lui-meme est valide bit-exact DANS LES DEUX SENS par
`test_heavy_weapon_moved_gate_live` (cible orksNob, non eligible a HeavyGravCannon). Le TREE
SentinelDirectives lui-meme est fidele (A/B bit-exact). ASCII only.
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
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent, unit_has_moved
from engine.runner.abilities.base import (ability_attack_params, ability_pierce_effect_bonus,
                                          sets_end_turn_flags_for,
                                          sets_active_ability_used_flag_for, NO_END_TURN_ABILITY_TYPES,
                                          NO_ABILITY_USED_FLAG_ABILITY_TYPES)
from engine.runner.abilities.admec import SentinelDirectivesAbility
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.operations.damage import AttackDamageOperation

PYDIR = Path(__file__).resolve().parents[3]                 # scripts/python
ROOT = PYDIR.parents[1]                                      # racine repo
CASTER_VIS = "admecDestroyer"
TARGET_VIS = "necroOverlord"        # vanille tanky (survit 1 coup) ; LOS clair depuis le spawn (cast fiable)
ABILITY = 1139
PINNED = 0x429                      # 1065


def _const(key):
    """ORACLE : constante de config d'ability SentinelDirectives (`ConfigConst`/`GetNumberConstant`,
    lecture BRUTE cote natif -- cf. en-tete). Fail explicite si la cle a disparu de la config."""
    v = ((GC.ability("SentinelDirectives") or {}).get("constants") or {}).get(key)
    assert v is not None, (f"oracle introuvable : gameconfig.ability('SentinelDirectives').constants.{key} "
                           f"absent -- le natif le lit en ConfigConst, il DOIT exister")
    return v


def _range():
    """Portee de l'ability = `constants.range` (0x16) : elle pilote le rapprochement du caster, donc un
    litteral la desynchroniserait silencieusement du jeu (cast illegal -> skip, pas d'echec visible)."""
    return int(_const("range"))


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def _cr(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _build(seed, a_units):
    sf = ROOT / "logs" / "runners" / f"sentdir-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", "MC1_67", "--roster", "1", "--p-units", CASTER_VIS, "--a-units", a_units,
         # #933 -- LE COUP PROPRE SE CONSTRUIT (cf. le skip « coup non propre (crit/block/evade) »
         # plus bas). Depuis la bascule #419-r5/-r6 le tirage crit/block est ouvert des deux cotes
         # et ce skip est devenu frequent : 1 passed / 1 skipped au 2026-08-11, rc 0, sans qu'aucun
         # garde ne le signale. Les QUATRE faces (#419-r6 §3.1).
         "--crit", "0,0", "--crit-target", "0,0",
         "--block-player", "0,0", "--block-target", "0,0"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-300:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _approach(rpc, rid, board, target_vis):
    """Avance jusqu'a mon tour ; rapproche le caster a portee `constants.range` de la cible (LOS clair). Renvoie
    (cid, tid, my_player, moves) ou None. `moves` = nb de deplacements emis pour le caster DEPUIS LE
    DEBUT DU TOUR COURANT -- remis a 0 a chaque `endturn`, parce que le natif purge `UnitFlag.Moved` du
    joueur ENTRANT (`IdunBattle.Operations.StartTurnOperation$$Execute` ->
    `IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags`). C'est l'ORACLE INDEPENDANT
    du flag que le live remonte : la fixture SAIT ce qu'elle a emis ce tour, `combatSnapshot.unitFlags`
    DIT ce que le natif a pose -- les deux doivent coincider (assertion dans le test)."""
    from collections import deque

    def tile_of(u):
        cr = _cr(u)
        return board.id_at(cr[0], cr[1]) if cr else None

    def bfs(src):
        dist = {src: 0}; q = deque([src])
        while q:
            x = q.popleft()
            for n in board.neighbours(x):
                if n not in dist and (n == src or board.walkable(n)):
                    dist[n] = dist[x] + 1; q.append(n)
        return dist

    def legal(cid):
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ABILITY}, 90)
        ab = next((a for a in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if a.get("abilityId") == ABILITY), {})
        return [x.get("targetId") for x in (ab.get("fromHere") or ab.get("targets") or [])]

    my = None
    moves = 0
    rng_cfg = _range()                       # portee LUE en config, jamais figee
    for _ in range(25):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        units = dv.get("units") or []
        caster = _find(units, CASTER_VIS)
        tgt = _find(units, target_vis)
        if caster is None or tgt is None:
            return None
        if my is None:
            my = caster.get("owner")
        if dv.get("currentPlayer") != my:
            moves = 0                        # RemoveTurnFlags purgera `Moved` a ma prochaine entree
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60); continue
        cid = caster["id"]
        if hexgeo.distance(_cr(caster), _cr(tgt)) <= rng_cfg and tgt["id"] in legal(cid):
            return cid, tgt["id"], my, moves
        dist = bfs(tile_of(tgt))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist and dist[t] >= 2]
        if not pool:
            moves = 0                        # idem : je finis MON tour, le flag tombera au suivant
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": col, "row": row}}}, 60)
        moves += 1
    return None


def _cast_live(rpc, rid, cid, tid):
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ABILITY},
        "captureEvents": True}, 120)
    ph, crit, block, evade = [], False, False, False
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
                ph.append(td.get("Amount"))
                crit = crit or bool(td.get("Attack_DidCrit"))
                block = block or bool(td.get("Attack_DidBlock"))
                evade = evade or bool(td.get("Attack_DidEvade"))
    return ph, crit, block, evade, res


# ==================================================================== (1)-(4) live end-to-end

def test_sentinel_directives_live(live_session, rpc):
    """Cast LIVE : ported + InformWeapon + Pinned live==offline + turn-flow (ne finit pas le tour) + A/B
    tree==pipeline (bit-exact) + raw dans les bornes config. State-file UNIQUE -> dispose au teardown."""
    rid, sf, err = _build("777", f"{TARGET_VIS},necroWarden")
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="native_sym")
        placed = _approach(rpc, rid, board, TARGET_VIS)
        if placed is None:
            pytest.skip("caster n'a pas atteint la portee 3 de la cible (LOS)")
        cid, tid, my, moves = placed

        # capture PRE-cast + config
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)

        def mkstate():
            """Etat offline frais. Le fait « le caster a bouge ce tour » vient du LIVE : `load_state`
            -> `snapshot._load_unit_flags` seede le `UnitFlagsComponent` depuis
            `combatSnapshot.units[].unitFlags`. C'est CE store que lit le gate no-move
            d'HeavyWeapon_ExtraDmg (+25% ranged), via `components.unit_has_moved` -- port et natif
            lisent donc le meme fait, sur l'etat REEL de la bataille, sans pose manuelle."""
            return load_state(dv, ob, snap, board=board)

        st = mkstate()
        # GARDE DU CANAL, tri-etat. `unitFlags` vaut `null` quand la mesure n'a PAS pu se faire
        # (`HasFlag` irresolue / enum vide) et `[]` quand elle a eu lieu sans flag pose : les rabattre
        # l'un sur l'autre ferait passer un capteur MORT pour un caster immobile, `load_state`
        # retomberait sur son defaut et le +25% ranged reviendrait EN SILENCE (mesure #101 : off 3834
        # vs live 3510). D'ou l'assertion explicite, puis la CONFRONTATION du flag a l'oracle
        # independant qu'est le compte de deplacements pilotes par la fixture ce tour.
        snap_caster = next((u for u in (snap.get("units") or []) if u.get("entityId") == cid), {})
        flags_live = snap_caster.get("unitFlags")
        assert isinstance(flags_live, list), (
            f"combatSnapshot.units[{cid}].unitFlags = {flags_live!r} : canal NON MESURE -- `None` "
            f"(capteur mort) n'est pas `[]` (lu, aucun flag). Sans lui le gate no-move "
            f"d'HeavyWeapon_ExtraDmg redevient aveugle sur tout etat recharge")
        assert unit_has_moved(st, cid) is (moves > 0), (
            f"desaccord fixture/canal : la fixture a emis {moves} deplacement(s) pour le caster "
            f"depuis le debut de son tour, le flag UnitFlag.Moved seede depuis le live vaut "
            f"{unit_has_moved(st, cid)} (unitFlags live={flags_live})")
        ce = st.get_entity(cid)
        if ce is None or ce.get_component(StatsComponent) is None:
            pytest.skip("caster sans StatsComponent")
        # ORACLE CONFIG : nb de coups + profil lus TELS QUELS dans la config (cf. en-tete).
        want_hits = int(_const("nrOfHits"))
        prof = _const("damageProfile")
        want_pierce = damage_profile_pierce(prof)   # damageProfiles.<prof>.PiercingRatio (echoue si absent)
        bmin, bmax, pierce, hits = ability_attack_params(st, cid, "SentinelDirectives", prof, ranged=True)
        assert hits == want_hits, (
            f"nrOfHits lu {hits} != oracle config {want_hits} (constants.nrOfHits) -- le port ne lit pas la "
            f"CONSTANTE d'ability (0x2f) mais autre chose (variable per-niveau scalee ? mauvaise cle ?)")
        # percage = PiercingRatio du PROFIL + ExtraPierce du caster ; Sy-Gex n'a pas d'ExtraPierce en STAT
        # (son bonus HeavyGravCannon passe par un EFFET, cf. RESIDU en tete) -> l'identite isole l'oracle
        # de profil. Si un patch lui en donnait en stat, ce garde-fou le DIRAIT.
        _ctx = ce.get_component(StatsComponent).ctx
        _xp = int(_ctx.extra_pierce or 0) + int(_ctx.extra_pierce_ranged or 0)
        assert _xp == 0, (f"setup n'isole plus le PiercingRatio du profil : le caster a ExtraPierce={_xp} "
                          f"-> l'oracle attendu devient PiercingRatio + {_xp}")
        assert pierce == want_pierce, (
            f"pierce {pierce} != oracle config {want_pierce} (damageProfiles.{prof}.PiercingRatio)")
        # Pinned NE doit PAS etre present avant le cast (delta -> c'est SentinelDirectives qui le pose)
        t_pre = next((u for u in (dv.get("units") or []) if u.get("id") == tid), {})
        pinned_pre = next((ef for ef in (t_pre.get("effects") or []) if ef.get("effectType") == 1065), None)
        assert pinned_pre is None, f"cible deja Pinned avant le cast: {pinned_pre}"
        s0 = rpc("dumpRng", {"runnerId": rid}, 30)
        if not _ok(s0):
            pytest.skip("dumpRng KO")

        # --- LIVE cast ---
        live_ph, crit, block, evade, res = _cast_live(rpc, rid, cid, tid)
        if not live_ph:
            pytest.skip(f"aucun degat live (LOS/obscurci) cast={str(res)[:160]}")
        if crit or block or evade:
            pytest.skip(f"coup non propre (crit/block/evade): {crit}/{block}/{evade}")
        # CONFRONTATION du nb de coups au LIVE (le nb APPLIQUE est CALCULE : base - reductions, plancher 1).
        # Sans elle, un port qui lirait la mauvaise constante resterait vert : oracle et port lisent la MEME
        # config, seul le natif tranche. (Mesure : perturbation nrOfHits 1 -> 2 non detectee avant ajout.)
        assert len(live_ph) == want_hits, (
            f"{len(live_ph)} coups LIVE (per_hit={live_ph}) != oracle config nrOfHits={want_hits} -- soit "
            f"une reduction de coups joue dans ce setup (le port doit la modeliser), soit le port/l'oracle "
            f"ne lisent pas la constante que le natif passe a AttackWithAttackDamage (ConfigConst 0x2f)")

        # Pinned live sur la cible + turn-flow live (currentPlayer inchange)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        t2 = next((u for u in (dv2.get("units") or []) if u.get("id") == tid), {})
        pinned_live = next((ef for ef in (t2.get("effects") or []) if ef.get("effectType") == 1065), None)
        cur_after = dv2.get("currentPlayer")

        # --- OFFLINE port (arbre DSL via le wiring ability-exec) ---
        stp = mkstate(); stp.rng = _seed_rng(s0)
        runner = Runner(stp).install_default_handlers(20)
        runner.apply(ActiveAbilityMessage(caster_id=cid, target_id=tid, ability_type=ABILITY))
        last = runner.ability_handler.last or {}
        # (1) EXECUTION reelle (garde anti-no-op) + InformWeapon
        assert last.get("ported") is True, (
            f"SentinelDirectives (1139) non execute (no-op) : last={last} ; "
            f"unported={getattr(runner.ability_handler, 'unported', None)}")
        assert last.get("informed_weapon") == prof, (
            f"InformWeapon({prof}) non emis: {last.get('informed_weapon')} -- le profil vient de "
            f"`constants.damageProfile` (GetDamageProfile), pas d'un litteral")
        atk = last.get("attack") or {}
        off_ph = atk.get("per_hit") or []
        # (2) Pinned materialise offline ET live
        off_pinned = stp.effects is not None and stp.effects.has_effect(tid, effect_type=PINNED)
        assert off_pinned, "la cible ne porte pas Pinned(0x429) offline (AddEffect non materialise, source=caster)"
        # LIVE : Pinned APPARU sur la cible (absent AVANT le cast, present APRES = delta) = pose par
        # SentinelDirectives ; remaining>=1. Le champ `source` live est dans l'espace d'id ECS
        # (non mappable au `id` decisionView) -> on ne l'asserte pas ; `off_pinned` prouve source==caster
        # cote offline (id-space coherent).
        assert pinned_live is not None, f"natif n'a PAS pose Pinned (effets cible={t2.get('effects')})"
        assert (pinned_live.get("remaining") or 0) >= 1, f"Pinned live remaining={pinned_live.get('remaining')} < 1"
        # (3) TURN-FLOW : le cast NE finit PAS le tour + ne pose PAS ActiveAbilityUsed (finesse 1139)
        flags = last.get("flags") or {}
        assert flags.get("turn_finished") is False, f"turn_finished={flags.get('turn_finished')} (1139 ne finit pas le tour)"
        assert flags.get("ability_used_flag") is False, f"ability_used_flag={flags.get('ability_used_flag')} (1139 ne pose pas ActiveAbilityUsed)"
        assert cur_after == my, f"currentPlayer {cur_after} != {my} apres cast : le tour a change (1139 devrait NE PAS finir le tour)"

        # --- A/B : arbre == sequence directe execute_ability_attack (attack family, meme rng) ---
        # ⚠ Le PERCAGE de la sequence directe doit inclure `BaseEffect$$PiercingBonusForAttack` (ce que
        # la feuille `AttackWithAttackDamage` fait, cf. abilities/behaviours/combat.py) : Sy-Gex porte
        # `HeavyGravCannon`, dont le canal percage ajoute `extraPierceRatio` contre une cible Mechanical.
        # Sans ce terme l'A/B comparerait DEUX percages differents -- inoffensif tant que la branche
        # armure domine (cas de cette cible), FAUX des que le tirage passe sous le seuil du plancher.
        st_ab = mkstate(); st_ab.rng = _seed_rng(s0)
        _pb = ability_pierce_effect_bonus(st_ab, cid, tid, ABILITY, is_ranged=True)
        _, _, pierce_eff, _ = ability_attack_params(st_ab, cid, "SentinelDirectives", prof,
                                                    ranged=True, pierce_effect_bonus=_pb)
        direct = AttackDamageOperation.execute_ability_attack(
            st_ab, cid, tid, bmin, bmax, pierce_eff, hits, damage_profile=prof, is_melee=False,
            ability_type=ABILITY, is_attack_damage_op=True)
        ab_ph = (direct or {}).get("per_hit") or []
        print(f"\n[SENTDIR] config [{bmin},{bmax}] pierce={pierce} hits={hits}")
        print(f"[SENTDIR] live={live_ph} off={off_ph} A/B={ab_ph} pinned_live_src={pinned_live.get('source')}")
        # (4) TREE FIDELE : l'arbre emet la MEME Operation que le pipeline direct (bit-exact)
        assert len(off_ph) == want_hits and len(ab_ph) == want_hits, \
            f"coups off={off_ph} A/B={ab_ph} != oracle config nrOfHits={want_hits}"
        assert off_ph == ab_ph, f"arbre {off_ph} != sequence directe execute_ability_attack {ab_ph}"
        # raw brut tire dans les bornes config (la valeur pre-reduction est le degat quand armure faible)
        assert bmin <= (atk.get("clean_max") or bmax) , "borne config incoherente"
        # (5) DEGAT BIT-EXACT live == offline. Les DEUX passifs du caster sont desormais portes :
        # HeavyWeapon_ExtraDmg (1008) par le gate no-move lu sur le flag natif (#101) et
        # HeavyGravCannon (1291, ACTIF ici car necroOverlord est Mechanical) par
        # `HeavyGravCannonEffect` -- plus aucun confond caster-intrinseque, donc plus d'inegalite
        # molle : toute divergence est un VRAI ecart de port.
        assert live_ph == off_ph, (
            f"live {live_ph} != offline {off_ph} : un etage du coup diverge. Suspects, dans l'ordre : "
            f"le flat HeavyGravCannon (extraDmg[passiveLvl] x mult), son canal percage "
            f"(extraPierceRatio, inerte tant que la branche armure domine), le gate no-move "
            f"HeavyWeapon (caster_moved={moves > 0}), la materialisation finale du vecteur")
        print(f"[SENTDIR] OK : ported + InformWeapon + Pinned live(src {cid})==offline + turn-flow (ne finit "
              f"pas le tour, cur={cur_after}) + A/B tree==pipeline + degat BIT-EXACT "
              f"(HeavyGravCannon 1291 porte). caster_moved={moves > 0}")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 20)
        except Exception:
            pass
        try:
            sf.unlink()
        except Exception:
            pass


# ==================================================================== (5) turn-flow table (offline pur)

def test_sentinel_directives_no_end_turn_table():
    """Finesse « does not end Sy-Gex's turn » = 1139 dans les DEUX frozensets d'override (SetsEndTurnFlags
    ET SetsActiveAbilityUsedFlag = False), et route vers la classe portee. Pur offline (aucune session)."""
    from engine.runner.state import State
    from engine.runner.components import UnitComponent, OwnerComponent, PositionComponent
    assert 1139 in NO_END_TURN_ABILITY_TYPES
    assert 1139 in NO_ABILITY_USED_FLAG_ABILITY_TYPES
    assert ABILITY_CLASSES.get(1139) is SentinelDirectivesAbility
    assert SentinelDirectivesAbility.ABILITY_TYPE == 1139
    st = State(); st.current_player_id = 3
    e = st.add_entity(1)
    e.add_component(UnitComponent("syGex", True))
    e.add_component(OwnerComponent(team=1, player=3))
    e.add_component(PositionComponent(3, 3))
    # 1139 ne pose NI le flag fin-de-tour NI ActiveAbilityUsed (defaut base = True pour les autres).
    assert sets_end_turn_flags_for(1139, st, 1) is False
    assert sets_active_ability_used_flag_for(1139, st, 1) is False
