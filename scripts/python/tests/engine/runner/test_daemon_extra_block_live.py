"""#221 -- `Daemon_ExtraBlock` (1034) : le jet de block d'une cible Daemon, ETAGE PARTAGE.

QUESTION GARDEE : sur une meme attaque, contre un defenseur portant le trait `Daemon`, le port
consomme-t-il EXACTEMENT les memes tirages RNG que le natif, dans le meme ordre ?

CHAINE NATIVE
  `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$CreateUpdateEffectBehaviour`
    = `If(GetUpdateEffectCondition, RemoveEffect(Self, 0x40a) & AddExtraBlockEffectToOwner(0x40a,
        Direct(GetNumberConstant(0x2d = daemonBlockChance)), GetBlockDamage()))`
  `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$GetBlockDamage`
    = `PercentageOf(StatAmount(Self@0x148, statType 0 = Attack, statPart 0 = Current),
        Direct(GetNumberConstant(0x36 = daemonBlockDamagePercentage)))`
  -> une entree du `MultiValueStatComponent` (stat 7 BLOCK_CHANCE / 8 BLOCK_DAMAGE), lue par
  `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances` (via
  `IdunBattle.Entities.UnitExtensions$$GetMultiValueStat`) et tentee par
  `IdunBattle.Core.Services.DamageCalculations$$ApplyRandomBlockDamage` = **1 `NextBool(chance)`
  par source**, arret a la 1re reussite, `AddFailedBlockId(entityId)` sinon (la source est alors
  EXCLUE des coups suivants par le `Contains(failedBlockIds, entityId)` de `CalculateBlockChances`).

CE QUE CE TEST DISCRIMINE. Avant #221, `AttackDamageOperation._block_sources` appelait
`defender_effect_block_sources(effets, armure)` SANS l'Attack courante du defenseur : l'amount
tombait a 0, `DaemonExtraBlockEffect.create_effect_block_source_for_defense` rendait None, la source
DISPARAISSAIT et le port sautait le jet. Le test le prouve en rejouant la MEME attaque avec l'effet
NEUTRALISE (variante `legacy`) : si cette variante rendait le meme resultat que le port, le scenario
ne discriminerait rien et le test ECHOUE en le disant.

GARDE ANTI-SUR-CORRECTION : une cible NON-Daemon doit rester bit-exacte ET identique a la variante
legacy (le fix ne doit rien deplacer la ou il n'y a pas de source d'effet).
"""
from __future__ import annotations

import json
from collections import deque

import pytest

import gameconfig as GC
from engine.entities.effects.loki.hits import DaemonExtraBlockEffect
from engine.entities.pathfinding.board import Board
from engine.runner.components import StatsComponent
from engine.runner.damage_model import defender_fixed_armor
from engine.runner.messages import AttackUnitMessage
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.runner import Runner
from engine.runner.snapshot import load_state

ATTACKER = "necroDestroyer"       # 6 coups melee, vanille (aucun modificateur de degat)
DAEMON = "blackObliterator"       # trait Daemon, sans Resilient/Terrifying -> geometrie propre
PLAIN = "necroWarden"             # temoin SANS Daemon


def _cr(u):
    p = (u or {}).get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _find(units, vis):
    return next((u for u in (units or []) if u.get("visualId") == vis and u.get("alive")), None)


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"])
    r.mti = s["mti"]
    return r


def _replay(dv, ob, snap, bd, att, tgt, s0):
    """Rejoue l'attaque NORMALE offline depuis l'etat MT live -> per_hit."""
    st = load_state(dv, ob, snap, board=bd)
    st.rng = _seed_rng(s0)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(AttackUnitMessage(att, tgt))
    last = runner.damage_handler.last or {}
    return (last.get("attack") or last).get("per_hit") or [], st


def _engage(rpc, rid, bd, attacker_vis, target_vis):
    """DEPLACE l'attaquant jusqu'a pouvoir frapper la cible (jamais « bloque par le spawn »).
    Renvoie (casterId, targetId, ability normale)."""
    my = None
    for _ in range(30):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        att_u, tgt_u = _find(dv["units"], attacker_vis), _find(dv["units"], target_vis)
        assert att_u is not None and tgt_u is not None, (
            f"{attacker_vis}/{target_vis} absent(s) du build -- roster a revoir")
        my = my if my is not None else att_u.get("owner")
        if dv.get("currentPlayer") != my:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        cid, tid = att_u["id"], tgt_u["id"]
        norm = next((ab for ab in (att_u.get("abilities") or []) if ab.get("kind") == "normal"), None)
        assert norm is not None, f"{attacker_vis} n'expose pas d'attaque normale"
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid,
                                    "abilityType": norm["id"]}, 90)
        ab = next((x for x in ((at.get("units") or [{}])[0].get("abilities") or [])
                   if x.get("abilityId") == norm["id"]), {})
        if tid in [x.get("targetId") for x in (ab.get("fromHere") or [])]:
            return cid, tid, norm
        dist, q = {bd.id_at(*_cr(tgt_u)): 0}, deque([bd.id_at(*_cr(tgt_u))])
        while q:
            x = q.popleft()
            for n in bd.neighbours(x):
                if n not in dist and bd.walkable(n):
                    dist[n] = dist[x] + 1
                    q.append(n)
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == cid), None)
        reach = {bd.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        c, r = reach[min(pool, key=lambda t: dist[t])]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": cid, "to": {"col": c, "row": r}}}, 60)
    pytest.fail(f"{attacker_vis} n'a pas pu engager {target_vis} en 30 tours")


def _case(rpc, build_runner, target_vis, seed="777"):
    """Monte le duel, engage, capture l'etat MT, joue l'attaque LIVE et rejoue OFFLINE."""
    rid = build_runner(seed, extra=["--roster", "1", "--p-units", ATTACKER,
                                    "--a-units", target_vis])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    assert isinstance(bg, dict) and bg.get("tiles"), "boardGraph indisponible"
    bd = Board(bg["tiles"], adjacency="native_sym")
    cid, tid, norm = _engage(rpc, rid, bd, ATTACKER, target_vis)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    assert isinstance(s0, dict) and s0.get("mt"), "dumpRng indisponible"

    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid,
        "abilityType": norm["id"]}, "captureEvents": True}, 150)
    live = []
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            td = json.loads(td) if isinstance(td, str) else (td or {})
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == norm["id"]:
                live.append(td["Amount"])
    assert live, "aucun event de degat capture -- le scenario ne confronte rien"

    off, st = _replay(dv, ob, snap, bd, cid, tid, s0)
    _orig = DaemonExtraBlockEffect.create_effect_block_source_for_defense
    DaemonExtraBlockEffect.create_effect_block_source_for_defense = (
        # #1015-r1 -- la signature du hook porte un TROISIEME substrat (`defender_max_health`,
        # `GetStat(Health, Maximum)`, consomme par `BeastSnagga_ExtraBlock`). Ce stub la RECOPIE :
        # un `**_` la masquerait, et le jour ou l'agregateur cesserait de la passer, le test
        # resterait vert. Meme raison qu'ecrire `defender_attack=0` plutot que `*args`.
        lambda self, defender_fixed_armor=0, defender_attack=0, defender_max_health=0: None)
    try:
        legacy, _ = _replay(dv, ob, snap, bd, cid, tid, s0)
    finally:
        DaemonExtraBlockEffect.create_effect_block_source_for_defense = _orig
    return {"rid": rid, "tid": tid, "live": live, "off": off, "legacy": legacy, "st": st}


def test_daemon_defender_block_roll_live(rpc, build_runner):
    """Cible DAEMON : la source `Daemon_ExtraBlock` existe cote port, avec la chance et le montant
    de l'oracle gameconfig, et l'attaque entiere est bit-exacte contre le live."""
    assert "Daemon" in ((GC.unit(DAEMON) or {}).get("traits") or []), \
        f"{DAEMON} n'a plus le trait Daemon -- geometrie non discriminante"
    c = _case(rpc, build_runner, DAEMON)
    st, tid = c["st"], c["tid"]
    tgt = st.get_entity(tid)
    sc = tgt.get_component(StatsComponent)
    effs = st.effects.active_effects(tid) if st.effects is not None else []
    srcs = AttackDamageOperation._block_sources(sc, effs, defender_fixed_armor(st, tid)) or []

    # ORACLE gameconfig (jamais un litteral recopie) : chance = daemonBlockChance,
    # amount = daemonBlockDamagePercentage % de l'Attack COURANTE (StatAmount(Self, 0, Current)).
    dvars = (GC.trait("Daemon") or {}).get("variables") or {}
    chance = int(dvars.get("daemonBlockChance") or 0)
    pct = int(dvars.get("daemonBlockDamagePercentage") or 0)
    assert chance > 0 and pct > 0, "constantes daemonBlock* absentes de gameconfig"
    want_amount = int(int(sc.ctx.attack) * pct // 100)
    daemon_src = [s for s in srcs if int(s.chance) == chance]
    assert daemon_src, (
        f"aucune source de block de chance {chance} pour la cible Daemon u{tid} "
        f"(sources={srcs}) -- `_block_sources` ne thread pas l'Attack du defenseur, "
        f"le port SAUTE le jet que le natif roule")
    assert int(daemon_src[0].amount) == want_amount, (
        f"amount {daemon_src[0].amount} != oracle {want_amount} "
        f"(= Attack {sc.ctx.attack} x {pct}%) -- DaemonAbility$$GetBlockDamage mal porte")

    assert c["off"] == c["live"], (
        f"per-coup offline {c['off']} != live {c['live']} : la consommation RNG diverge "
        f"(un jet de block en trop ou en moins decale TOUT l'aval de l'attaque)")
    # ANTI-FAUX-POSITIF : le scenario DOIT exercer la branche. Si neutraliser la source
    # `Daemon_ExtraBlock` ne change rien, c'est que le block n'a pas ete roule ici.
    assert c["legacy"] != c["live"], (
        f"la variante SANS `Daemon_ExtraBlock` rend le meme resultat ({c['legacy']}) : "
        f"le jet de block n'a pas ete exerce, ce test ne discrimine rien")


def test_non_daemon_defender_unchanged_live(rpc, build_runner):
    """GARDE anti-sur-correction : cible SANS Daemon -> bit-exact ET strictement identique a la
    variante legacy (le fix ne doit rien deplacer hors des porteurs de source d'effet)."""
    assert "Daemon" not in ((GC.unit(PLAIN) or {}).get("traits") or []), \
        f"{PLAIN} porte Daemon -- le temoin n'en est plus un"
    c = _case(rpc, build_runner, PLAIN)
    assert c["off"] == c["live"], (
        f"per-coup offline {c['off']} != live {c['live']} sur une cible SANS source de block "
        f"d'effet : le fix #221 a deplace la consommation RNG hors de son perimetre")
    assert c["legacy"] == c["off"], (
        f"la variante legacy ({c['legacy']}) differe du port ({c['off']}) sur une cible NON-Daemon : "
        f"`DaemonExtraBlockEffect` s'applique a une cible qui ne porte pas le trait")
