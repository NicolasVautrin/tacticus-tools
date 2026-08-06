"""VECTEUR ATTAQUE — dégât d'ABILITY (param-ability) : replay-diff LIVE vs moteur porté.

Valide `AttackDamageOperation.execute_ability_attack` (base = config minDmg/maxDmg[level] de l'ability,
profile pierce, nrOfHits — PAS `Attack ± spread%`) en rejouant la MÊME ability que le live. Fixture =
templSwordBrother / ThunderousAssault (id 1043, 1 coup Power adjacent) sur une cible VANILLE
(eldarFarseer : aucune réduction de dégât d'effet → per-coup propre, comme les tests d'attaque normale).

Le pipeline par-coup (réduction perçage/armure/modifiers → tirage dans la plage réduite → crit → block)
est PARTAGÉ avec l'attaque normale (déjà bit-exact) ; ce test cible le SOURCING param-ability (min/max via
`ability_var(level)`, pierce profil, hits) + le bon enchaînement RNG (le tirage de dégât = 1er conso, comme
l'attaque normale ; le Stun est déterministe). On confronte le per-coup ET les PV cible.

⚠ LES DEUX ASSERTIONS NE MESURENT PAS LA MÊME CHOSE, et #419-r6 l'a établi par la mesure. Le
per-coup ne voit que les paquets estampillés `Active_Ability_Type == 1043` ; les PV, eux, voient
TOUT ce que le cast retire. Sur ce montage le natif en retire DEUX : le coup de l'ability, puis le
KNOCKBACK du push bloqué (`DisplaceUnitOperation$$ApplyKnockbackTo` =
`ceil(maxHealth × BC.Damage.KnockbackPercentage/100)` = 1808 ici — ThunderousAssault pousse la
cible, et elle est contre un obstacle). Ce second paquet est PORTÉ, mais il exige que `state.board`
soit peuplé : `load_state(..., board=board)` est donc LOAD-BEARING, et son absence était SILENCIEUSE
(le port rendait 2086 PV au lieu de 278). Même vice que le bonus d'ÉLÉVATION de #63.

⚠ ET L'ORACLE DES PV EST PRIS AVANT LA BASCULE DE TOUR. Le roster est 1v1, donc le cast termine le
tour du joueur et `applyAction` rend un état qui a déjà traversé le turn-start adverse — où le trait
`LivingMetal` de la cible régénère 10 % de ses PV max (+904, mesuré). On lit donc les PV dans les
tags du dernier paquet de dégât (`UnitStats_RemainingHealth`), pas dans `res.units[].hp`.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from engine.runner.snapshot import load_state
from engine.runner.runner import Runner
from engine.runner.messages import ActiveAbilityMessage
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import HealthComponent, StatsComponent

CASTER_VIS = "templSwordBrother"
TARGET_VIS = "necroOverlord"         # cible tanky sans reduction de degat ni block (elle SURVIT au coup)
ABILITY = 1043                       # ThunderousAssault

# Confonds NEUTRALISES AU BUILD (#419-r6). Ce fichier mesure le SOURCING param-ability et
# l'enchainement RNG : il ne retient qu'un coup « propre » et skippe des que le live crite ou
# bloque. Il trouvait ce coup SANS RIEN DEMANDER tant que le canal crit/block etait globalement
# muet (les 4 stats a 0 sur TOUTE unite, faute d'items a la normalisation). Une fois le defaut
# bascule a « equiper », `templSwordBrother` porte `CritChance = 26` : le fichier partirait en
# skip environ un run sur quatre, donc `0 passed / 1 skipped` -- le fichier INERTE que le garde
# #455 refuse. On rend donc le regime EXPLICITE, sur les QUATRE faces (`--crit`/`--block-player`
# n'epinglent que les p-units, `--crit-target`/`--block-target` que les a-units). L'axe CRIT a
# son fichier dedie (`test_damage_crit_live.py`) ; il n'est pas perdu, il est ailleurs.
_NO_NOISE = ["--crit", "0,0", "--crit-target", "0,0",
             "--block-target", "0,0", "--block-player", "0,0"]
BUILD = ["--roster", "1", "--p-units", CASTER_VIS, "--a-units", TARGET_VIS, *_NO_NOISE]


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
            if n not in dist and (n == src or board.walkable(n)):
                dist[n] = dist[x] + 1; q.append(n)
    return dist


def test_thunderous_assault_ability_damage_bit_exact(live_session, rpc, build_runner):
    """Le dégât de ThunderousAssault (param-ability) est reproduit per-coup bit-exact offline."""
    from engine.entities.pathfinding.board import Board
    rid = build_runner("777", extra=BUILD)["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")

    def tile_of(u):
        p = u.get("pos") or {}
        return board.id_at(p.get("col"), p.get("row")) if p.get("col") is not None else None

    my_player = None
    caster = tgt = None
    for _turn in range(25):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        if not _ok(dec):
            pytest.skip("decisionView KO")
        units = dec.get("units") or []
        caster = next((u for u in units if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
        tgt = next((u for u in units if u.get("visualId") == TARGET_VIS and u.get("alive")), None)
        if caster is None or tgt is None:
            pytest.skip(f"unite manquante (caster={bool(caster)} tgt={bool(tgt)})")
        if my_player is None:
            my_player = caster.get("owner")
        if dec.get("currentPlayer") != my_player:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        if tile_of(caster) in board.neighbours(tile_of(tgt)):
            break
        dist = _bfs(board, tile_of(tgt))
        mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        cmt = next((x for x in (mt.get("units") or []) if x.get("unitId") == caster["id"]), None)
        reach = {board.id_at(t["col"], t["row"]): (t["col"], t["row"])
                 for t in ((cmt or {}).get("tiles") or [])}
        pool = [t for t in reach if t in dist]
        if not pool:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40); continue
        best = min(pool, key=lambda t: dist[t]); col, row = reach[best]
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": caster["id"], "to": {"col": col, "row": row}}}, 40)
    else:
        pytest.skip("caster n'a pas atteint la cible en 25 tours")

    att, tid = caster["id"], tgt["id"]
    # capture AVANT + seed rng (replay de dégât) :
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    # `board=` est LOAD-BEARING (#419-r6), et son absence etait SILENCIEUSE. ThunderousAssault
    # POUSSE la cible d'un hex puis charge le caster dans la case liberee ; sans board, les
    # feuilles geometriques de l'arbre DSL (`PushUnit`, `MoveUnit`) sont des no-op cote port,
    # donc le KNOCKBACK du push BLOQUE (`DisplaceUnitOperation$$ApplyKnockbackTo`,
    # `ceil(maxHealth x BC.Damage.KnockbackPercentage/100)`) ne s'appliquait pas non plus.
    # MESURE : sur ce montage le natif pousse contre un obstacle -> knockback de 1808 ; le port
    # rendait 2086 PV au lieu de 278, et l'assertion PV ne le voyait que par accident. Meme vice
    # et meme parade que le bonus d'ELEVATION de #63 (cf. `_combat_replay._do_replay`).
    state = load_state(dv, ob, snap, board=board)
    ae = state.get_entity(att)
    if ae is None or ae.get_component(StatsComponent) is None:
        pytest.skip("attaquant sans StatsComponent (stats non chargees)")
    te = state.get_entity(tid)
    thc = te.get_component(HealthComponent) if te is not None else None
    if thc is None or thc.hp is None:
        pytest.skip("cible introuvable offline")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    state.rng = _seed_rng(s0)

    # cast LIVE :
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att, "targetId": tid, "abilityType": ABILITY}}, 60)
    a0 = (res.get("actions") or [{}])[0]
    if not (_ok(res) and a0.get("ok")):
        pytest.skip(f"cast KO: {str(res)[:160]}")
    live_ph, dc, db, de = [], False, False, False
    live_hp_post_cast = None
    for e in (a0.get("events") or []):
        td = e.get("tags")
        if not td:
            continue
        td = json.loads(td) if isinstance(td, str) else td
        if td.get("Target_Id") == tid and "Amount" in td:
            # PV de la cible APRES ce paquet de degat, publies par le natif lui-meme. On les
            # retient pour TOUT degat subi par la cible pendant le cast — pas seulement ceux de
            # l'ability : c'est justement ce que le filtre `Active_Ability_Type` ci-dessous
            # ecarte, et le knockback du push en fait partie.
            if td.get("UnitStats_RemainingHealth") is not None:
                live_hp_post_cast = td.get("UnitStats_RemainingHealth")
        if td.get("Target_Id") == tid and "Amount" in td and td.get("Active_Ability_Type") == ABILITY:
            live_ph.append(td.get("Amount"))
            dc = dc or bool(td.get("Attack_DidCrit"))
            db = db or bool(td.get("Attack_DidBlock"))
            de = de or bool(td.get("Attack_DidEvade"))
    if dc or db or de:
        pytest.skip(f"coup non propre (crit/block/evade live) hors axe param-ability: c={dc} b={db} e={de}")
    if not live_ph:
        pytest.skip("aucun event de degat live (cible hors portee / ability sans degat capte)")
    # ⚠ ORACLE DES PV : `live_hp_post_cast` (tags du DERNIER degat subi), PAS `res.units[].hp`.
    # Les deux ne sont PAS pris au meme instant, et l'ecart est MESURE (#419-r6) : le roster est
    # 1v1, donc le cast TERMINE le tour du joueur et `applyAction` rend un etat qui a DEJA
    # traverse le turn-start adverse. Le trait `LivingMetal` de `necroOverlord`
    # (`livingMetalHp = 10`) y regenere 10 % des PV max — mesure : 278 -> 1182, soit +904 sur un
    # `Health` normalise de 9037. Ce soin est HORS AXE (le fichier mesure UN cast), et le
    # comparer a un port qui n'a simule aucun tour serait comparer deux instants differents.
    live_after = live_hp_post_cast

    # OFFLINE via le wiring ability-exec (l'engine dérive l'attaque param-ability) :
    runner = Runner(state).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=att, target_id=tid, ability_type=ABILITY))
    atk = (runner.ability_handler.last or {}).get("attack")
    assert atk is not None, f"pas de resultat d'attaque d'ability offline: {runner.ability_handler.last}"
    off_ph = atk["per_hit"]
    off_after = state.get_entity(tid).get_component(HealthComponent).hp
    print(f"\n[ABILITY dmg] ThunderousAssault hits={atk['hits']} base=[{atk['base_min']},{atk['base_max']}] "
          f"pierce={atk['pierce']} armor={atk['armor']} live_ph={live_ph} off_ph={off_ph} "
          f"live_after={live_after} off_after={off_after} (PV post-cast, hors turn-start)")
    assert off_ph == live_ph, f"per-coup offline {off_ph} != live {live_ph}"
    # PV cible : confronté SEULEMENT si la cible a survécu (live_after>0). Si elle meurt, le `Amount`
    # event reste le dégât NON capé (= per-coup, déjà confronté), mais `live_after` est capé à 0 et la
    # dérive multi-tours (tuiles hazard pendant l'approche) peut désaligner les PV de départ → on
    # n'asserte pas les PV sur une cible morte (le per-coup bit-exact est la validation).
    #
    # Cette assertion n'est PAS un doublon du per-coup : elle confronte TOUT ce que le cast retire
    # à la cible, alors que `live_ph` ne retient que les paquets estampillés `Active_Ability_Type
    # == ABILITY`. C'est elle, et elle seule, qui garde le KNOCKBACK du push bloqué (#419-r6).
    if live_after is not None and live_after > 0:
        assert off_after == live_after, (
            f"PV cible offline {off_after} != live {live_after} (post-cast, avant tout turn-start) "
            f"-- le per-coup de l'ability est pourtant identique ({off_ph}), donc l'ecart porte sur "
            f"un paquet de degat HORS `Active_Ability_Type` : le knockback du push bloque "
            f"(`DisplaceUnitOperation$$ApplyKnockbackTo`) est le premier suspect, et il exige que "
            f"`state.board` soit peuple.")
