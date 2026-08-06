"""LOT « la POSE manque » (#222) — TESTS DE GARDE des 4 maillons cables (#99).

Patron commun du lot : l'EFFET etait deja porte et consomme, mais RIEN ne le posait (code
enregistre-mais-mort, no-op SILENCIEUX). Ces tests gardent le MAILLON DE POSE : si le cablage
regresse (trigger debranche, selecteur casse, gate inverse), la pose redevient muette et
AUCUN autre test ne le verrait -- c'est exactement la classe de bug que le lot corrigeait.

Chaque test confronte le LIVE (oracle natif, `decisionView.effects` / `tileMeta.effects`) au rejeu
OFFLINE depuis la MEME capture d'etat. Aucune constante de duree/niveau en dur : les valeurs
attendues viennent soit du natif, soit de la config (`crescendo_max_level`, `default_amount_of_rounds`).

Maillons + artefacts natifs (build gqfc5mff6c) :
  1. MasterAnnihilator  (`admecDominus`)     IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour
     `On(0x26 NormalAttack) & OwnerIsCaster & AreEnemies` -> `RemoveEffect(OwnerOfEffect(
     EffectsFromUnitSource(Self, 1249)), 1249) + AddEffect(1249, Target())` = la marque MIGRE.
  2. FleshmetalGuns     (`blackObliterator`) IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArchContaminatorAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour
     `On(0x16 TurnStart_Actions) & IsTurnOf(Self)` -> Remove x3 + `If(Modulo(UnitTurnsStarted,3)==
     1/2/0, AddEffect(1067/1212/1221))` = ROTATION.
  3. TerrifyingCrescendo(`emperNoiseMarine`) IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour
     `(On(0 UnitDeath) & TargetIsOverkilled) | (On(0x3d PreEffectAdded) & TriggeringEffectIs(1065))`
     -> `AddEffectOrIncreaseLevel(1424, +1, max=buffMaxLevel)` = ACCUMULATION capee.
  4. AnvilShield        (`spaceRockfist`)    emetteur `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` (branche
     `On(UnitBlocked=0x3c)`) ; `ApplyIce IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger/IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateBehaviour` -> glace la tuile de l'ATTAQUANT bloque.

ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import hexgeo
from engine.entities.effect_type import EffectType
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.components import PositionComponent, OwnerComponent, StatsComponent
from engine.runner.operations.effects import AddEffectOperation, default_amount_of_rounds
from engine.runner.operations.triggers.dispatch.attack import after_hit_normal_attack
from engine.runner.operations.turnflow import StartTurnOperation
from engine.runner.abilities.base import convert_rounds_to_turns

MARK = int(EffectType.MasterAnnihilator_extraHit)      # 1249
CRESC = int(EffectType.TerrifyingCrescendo_ExtraDmg)   # 1424
PINNED = int(EffectType.Pinned)                        # 1065
ICE = int(EffectType.Ice)                              # 17 (0x11)
NORMAL_ATTACK = 69

MA, FG, TC, AS_, EN = ("admecDominus", "blackObliterator", "emperNoiseMarine",
                       "spaceRockfist", "necroWarden")
# PV enormes des DEUX cotes : un mort ne porte plus d'effet -> le datapoint disparait.
TANKY = ["--hp-target", "400000", "--hp-player", "400000"]


# --------------------------------------------------------------------------- helpers live
def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 99, "allAbilities": True}, 150)


def _act(rpc, rid, action):
    return rpc("applyAction", {"runnerId": rid, "action": action, "captureEvents": False}, 150)


def _alive(dec, vis):
    return [u for u in (dec.get("units") or []) if u.get("visualId") == vis and u.get("alive")]


def _by_id(dec, uid):
    return next((u for u in (dec.get("units") or []) if u.get("id") == uid), None)


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _effs(u, effect_type):
    return [e for e in ((u or {}).get("effects") or []) if e.get("effectType") == effect_type]


def _carriers(dec, effect_type, source=None):
    """Ids des unites VIVANTES portant `effect_type` (optionnellement d'une source donnee)."""
    out = set()
    for u in (dec.get("units") or []):
        if not u.get("alive"):
            continue
        for e in _effs(u, effect_type):
            if source is None or e.get("source") == source:
                out.add(u["id"])
    return out


def _movable(rpc, rid, uid):
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])]
    return []


def _drive_to(rpc, rid, uid, anchor, want):
    """DRIVE des DEUX camps : place `uid` a la distance hex `want` de `anchor` (runner.md §4 :
    `applyAction` ne verifie pas la propriete de l'unite). On ne SUBIT jamais les spawns."""
    tiles = _movable(rpc, rid, uid)
    if not tiles:
        return None
    best = min(tiles, key=lambda t: abs(hexgeo.distance(t, anchor) - want))
    _act(rpc, rid, {"kind": "move", "unitId": uid, "to": {"col": best[0], "row": best[1]}})
    return hexgeo.distance(best, anchor)


def _my_turn(rpc, rid, owner, maxit=8):
    for _ in range(maxit):
        dec = _dv(rpc, rid)
        if dec.get("currentPlayer") == owner:
            return dec
        _act(rpc, rid, {"kind": "endturn"})
    return _dv(rpc, rid)


def _bring_in_range(rpc, rid, caster_vis, enemy_vis, want, rounds=30):
    """Amene `caster_vis` a portee `want` d'un `enemy_vis`, en pilotant les deux camps."""
    for _ in range(rounds):
        dec = _dv(rpc, rid)
        me = _alive(dec, caster_vis)
        ens = [u for u in _alive(dec, enemy_vis) if _pos(u)[0] is not None]
        if not me or not ens:
            # deep-strike (TeleportStrike) : l'unite n'a pas encore atterri -> on laisse passer un tour
            _act(rpc, rid, {"kind": "endturn"})
            continue
        caster = me[0]
        if dec.get("currentPlayer") != caster.get("owner"):
            _drive_to(rpc, rid, ens[0]["id"], _pos(caster), want)
            # PIEGE : si le camp adverse n'a qu'UNE unite, son move clot deja son tour -> un `endturn`
            # de plus rendrait la main a l'adversaire (boucle infinie observee). On relit avant d'agir.
            if _dv(rpc, rid).get("currentPlayer") != caster.get("owner"):
                _act(rpc, rid, {"kind": "endturn"})
            continue
        cand = [e for e in ens if hexgeo.distance(_pos(e), _pos(caster)) <= want]
        if cand:
            return dec, caster, min(cand, key=lambda e: hexgeo.distance(_pos(e), _pos(caster)))
        tgt = min(ens, key=lambda e: hexgeo.distance(_pos(e), _pos(caster)))
        if _drive_to(rpc, rid, caster["id"], _pos(tgt), want) is None:
            _act(rpc, rid, {"kind": "endturn"})
            continue
        dec = _dv(rpc, rid)
        me = _alive(dec, caster_vis)
        tgt = _by_id(dec, tgt["id"])
        if not me or tgt is None:
            return None, None, None
        if hexgeo.distance(_pos(tgt), _pos(me[0])) <= want:
            return dec, me[0], tgt
        if dec.get("currentPlayer") == caster.get("owner"):
            _act(rpc, rid, {"kind": "endturn"})
    return None, None, None


def _offline(rpc, rid, dec=None):
    """`State` OFFLINE (board + effets) reconstruit depuis la capture LIVE courante."""
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    board = Board(bg["tiles"], adjacency="evenq") if bg.get("tiles") else None
    dec = dec or _dv(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    return load_state(dec, ob, snap, board=board), dec, board


def _off_carriers(state, effect_type, source=None):
    out = set()
    if state.effects is None:
        return out
    for uid, lst in state.effects.by_unit.items():
        for e in lst:
            if e.consumed or e.effect_type != effect_type:
                continue
            if source is None or e.source == source:
                out.add(int(uid))
    return out


# --------------------------------------------------------------------------- 1. MasterAnnihilator
def test_master_annihilator_mark_migrates_live(live_session, rpc, build_runner):
    """La marque 1249 SE DEPLACE d'une cible a l'autre au fil des attaques de Vitruvius et n'existe
    JAMAIS en double (`RemoveEffect(OwnerOfEffect(EffectsFromUnitSource(Self, 1249)))` IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour).

    Ce que ca garderait : un debranchement du vecteur `On(0x26)` (plus AUCUNE marque = no-op muet),
    ou une `RemoveEffect` rendue mono-cible / non filtree par source (marque qui s'accumule, ou qui
    efface les marques d'AUTRES poseurs). Le controle negatif de source est verifie OFFLINE.
    """
    rid = build_runner("92201", extra=["--p-units", f"{MA},{FG}",
                                       "--a-units", f"{EN},{EN},{EN}"] + TANKY)["rid"]
    dec, vit, t1 = _bring_in_range(rpc, rid, MA, EN, 2)
    if vit is None:
        pytest.skip("Vitruvius injoignable (roster/geometrie)")
    assert not _carriers(dec, MARK), f"marque 1249 deja presente avant la 1re attaque: {_carriers(dec, MARK)}"

    state0, dec0, board = _offline(rpc, rid, dec)
    r1 = _act(rpc, rid, {"kind": "ability", "casterId": vit["id"], "targetId": t1["id"],
                         "abilityType": NORMAL_ATTACK})
    if not (isinstance(r1, dict) and r1.get("ok")):
        pytest.skip(f"attaque #1 KO: {str(r1)[:150]}")
    dec1 = _dv(rpc, rid)
    live1 = _carriers(dec1, MARK, source=vit["id"])
    assert live1 == {t1["id"]}, (
        f"apres attaque #1 : porteurs de la marque de Vitruvius={live1}, attendu {{{t1['id']}}} "
        "(le maillon de POSE est muet ou vise la mauvaise cible)")

    # 2e attaque, sur une AUTRE cible -> la marque doit MIGRER (et rester unique).
    # DRIVE de l'ADVERSAIRE : le movable set n'est calcule QUE pour le joueur courant -> on rend la
    # main, on place NOUS-MEMES la 2e cible au contact de Vitruvius, puis on reprend le tour.
    dec1b = _dv(rpc, rid)
    vit1b = (_alive(dec1b, MA) or [None])[0]
    others = [e for e in _alive(dec1b, EN) if e["id"] != t1["id"]]
    if vit1b is None or not others:
        pytest.skip("2e cible indisponible")
    t2 = min(others, key=lambda e: hexgeo.distance(_pos(e), _pos(vit1b)))
    for _ in range(4):
        _act(rpc, rid, {"kind": "endturn"})                       # -> tour ADVERSE
        dec_e = _dv(rpc, rid)
        v = (_alive(dec_e, MA) or [None])[0]
        if v is None:
            pytest.skip("Vitruvius perdu")
        if dec_e.get("currentPlayer") != vit.get("owner"):
            _drive_to(rpc, rid, t2["id"], _pos(v), 1)
        dec2 = _dv(rpc, rid)
        if dec2.get("currentPlayer") == vit.get("owner"):
            break
    dec2 = _my_turn(rpc, rid, vit.get("owner"))
    vit2 = (_alive(dec2, MA) or [None])[0]
    t2 = _by_id(dec2, t2["id"])
    if vit2 is None or t2 is None or not t2.get("alive"):
        pytest.skip("2e cible perdue")
    if hexgeo.distance(_pos(t2), _pos(vit2)) > 2:
        _drive_to(rpc, rid, vit2["id"], _pos(t2), 1)              # sinon on rapproche Vitruvius
        dec2 = _dv(rpc, rid)
        vit2 = (_alive(dec2, MA) or [None])[0]
        t2 = _by_id(dec2, t2["id"])
        if vit2 is None or t2 is None or hexgeo.distance(_pos(t2), _pos(vit2)) > 2:
            pytest.skip("2e cible non amenable a portee")
    r2 = _act(rpc, rid, {"kind": "ability", "casterId": vit2["id"], "targetId": t2["id"],
                         "abilityType": NORMAL_ATTACK})
    if not (isinstance(r2, dict) and r2.get("ok")):
        pytest.skip(f"attaque #2 KO: {str(r2)[:150]}")
    dec3 = _dv(rpc, rid)
    live2 = _carriers(dec3, MARK, source=vit["id"])
    assert live2 == {t2["id"]}, (
        f"apres attaque #2 : porteurs={live2}, attendu {{{t2['id']}}} — la marque doit MIGRER "
        "(remove-by-source) et ne JAMAIS exister en double")

    # OFFLINE : le MEME vecteur, rejoue depuis la capture initiale, doit produire le MEME ensemble.
    other_src = (_alive(dec0, FG) or [None])[0]
    if other_src is not None and state0.effects is not None:
        # CONTROLE NEGATIF : une marque posee par une AUTRE source ne doit PAS etre retiree.
        third = next((e["id"] for e in _alive(dec0, EN)
                      if e["id"] not in (t1["id"], t2["id"])), None)
        if third is not None:
            AddEffectOperation.execute(state0, source=other_src["id"], target=third,
                                       effect_type=MARK, name="MasterAnnihilator_extraHit")
    after_hit_normal_attack(state0, vit["id"], t1["id"], ranged=False, profile="Physical")
    off1 = _off_carriers(state0, MARK, source=vit["id"])
    assert off1 == live1, f"offline apres attaque #1 : {off1} != live {live1}"
    after_hit_normal_attack(state0, vit["id"], t2["id"], ranged=False, profile="Physical")
    off2 = _off_carriers(state0, MARK, source=vit["id"])
    assert off2 == live2, f"offline apres attaque #2 : {off2} != live {live2}"
    if other_src is not None and third is not None:
        assert third in _off_carriers(state0, MARK, source=other_src["id"]), (
            "CONTROLE NEGATIF : la marque d'une AUTRE source a ete retiree — le selecteur "
            "`EffectsFromUnitSource(Self, 1249)` n'est plus filtre par source")
    print(f"\n[MasterAnnihilator] live u{t1['id']} -> u{t2['id']} (jamais double) == offline")


# --------------------------------------------------------------------------- 2. FleshmetalGuns
def test_fleshmetal_guns_rotation_live(live_session, rpc, build_runner):
    """La ROTATION `Modulo(UnitTurnsStarted(Self), 3)` change l'effet de Volk a CHAQUE tour
    (IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGunsAbility$$CreateBehaviour). Trois tours consecutifs = trois effets DISTINCTS, et l'offline (rejeu de
    `StartTurnOperation`) doit rendre la MEME sequence que le natif.

    Ce que ca garderait : la rotation figee (toujours le meme effet = `UnitTurnsStarted` non lu),
    ou le vecteur turn-start debranche (aucun effet FleshmetalGuns du tout).
    """
    rid = build_runner("92201", extra=["--p-units", f"{FG},{MA}", "--a-units", EN] + TANKY)["rid"]
    dec = _dv(rpc, rid)
    volk = (_alive(dec, FG) or [None])[0]
    if volk is None:
        pytest.skip("Volk absent")
    owner = volk.get("owner")

    def _fg_names(d):
        u = next((x for x in (d.get("units") or []) if x["id"] == volk["id"]), None)
        return sorted(str(e.get("name")) for e in ((u or {}).get("effects") or [])
                      if str(e.get("name")).startswith("FleshmetalGuns"))

    # Capture au tour COURANT de Volk : l'etat porte deja l'effet du tour N (le natif l'a pose a son
    # StartTurn). Les `StartTurnOperation` offline simulent donc N+1, N+2, N+3 -> on confronte a
    # `live_seq[1:]` (decalage de PROTOCOLE, pas de comportement).
    dec = _my_turn(rpc, rid, owner)
    state, _, _ = _offline(rpc, rid, dec)
    live_seq = [_fg_names(dec)]
    for _ in range(3):
        _act(rpc, rid, {"kind": "endturn"})            # rend la main -> prochain tour de Volk
        dec = _my_turn(rpc, rid, owner)
        live_seq.append(_fg_names(dec))
    off_seq = []
    for _ in range(3):
        StartTurnOperation.execute(state, owner)
        off_seq.append(sorted(str(e.name) for e in state.effects.by_unit.get(volk["id"], [])
                              if not e.consumed and str(e.name).startswith("FleshmetalGuns")))

    assert all(s for s in live_seq), (
        f"le natif n'expose AUCUN effet FleshmetalGuns sur un tour de Volk: {live_seq}")
    assert len({tuple(s) for s in live_seq[:3]}) == 3, (
        f"la rotation native ne change pas d'effet sur 3 tours: {live_seq}")
    assert off_seq == live_seq[1:], (
        f"rotation offline {off_seq} != rotation live {live_seq[1:]} "
        "(le port ne suit plus `Modulo(UnitTurnsStarted, 3)`)")
    print(f"\n[FleshmetalGuns] rotation live == offline : {live_seq}")


# --------------------------------------------------------------------------- 3. TerrifyingCrescendo
def test_terrifying_crescendo_stacks_and_caps_live(live_session, rpc, build_runner):
    """Le stack 1424 MONTE d'un cran a chaque tir suppress de Shiron et PLAFONNE a `buffMaxLevel`
    (IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour : `AddEffectOrIncreaseLevel(1424, +1, max)`), y compris quand la cible est DEJA
    Pinned -- preuve que le vecteur est `On(0x3d PreEffectAdded)`, EMIS AVANT le gate « deja
    present » d'`IdunBattle.Operations.AddEffectOperation$$Execute` (semantique « would have Suppressed »).

    Ce que ca garderait : un vecteur recable sur `On(EffectAdded)` (le stack cesserait de monter
    des le 2e tir sur une cible deja Pinned = LE bug d'origine), un clamp perdu, ou la pose muette.
    """
    from engine.runner.operations.triggers.loki.terrifying_crescendo import crescendo_max_level
    rid = build_runner("92201", extra=["--p-units", f"{TC},{MA}",
                                       "--a-units", f"{EN},{EN}"] + TANKY)["rid"]
    cap = crescendo_max_level()
    assert cap and cap > 1, f"buffMaxLevel illisible ({cap}) — le test ne peut rien garder"

    dec, shiron, tgt = _bring_in_range(rpc, rid, TC, EN, 3)
    if shiron is None:
        pytest.skip("Shiron injoignable")
    owner = shiron.get("owner")
    state, _, _ = _offline(rpc, rid, dec)

    def _level(d):
        u = next((x for x in (d.get("units") or []) if x["id"] == shiron["id"]), None)
        lv = [e.get("level") for e in _effs(u, CRESC)]
        return lv[0] if lv else 0

    live_levels, shots = [], 0
    for _ in range(cap + 3):
        dec = _my_turn(rpc, rid, owner)
        sh = (_alive(dec, TC) or [None])[0]
        if sh is None:
            break
        cand = [e for e in _alive(dec, EN) if hexgeo.distance(_pos(e), _pos(sh)) >= 2]
        if not cand:
            _act(rpc, rid, {"kind": "endturn"})
            continue
        t = min(cand, key=lambda e: hexgeo.distance(_pos(e), _pos(sh)))
        r = _act(rpc, rid, {"kind": "ability", "casterId": sh["id"], "targetId": t["id"],
                            "abilityType": NORMAL_ATTACK})
        if isinstance(r, dict) and r.get("ok"):
            shots += 1
            live_levels.append(_level(_dv(rpc, rid)))
        _act(rpc, rid, {"kind": "endturn"})
    if shots < cap + 1:
        pytest.skip(f"seulement {shots} tirs ranged realises (< cap+1={cap + 1})")

    assert live_levels[0] == 1, f"1er tir : stack natif={live_levels[0]}, attendu 1"
    assert live_levels == sorted(live_levels), f"le stack natif n'est pas monotone: {live_levels}"
    assert max(live_levels) == cap, (
        f"plafond natif={max(live_levels)} != buffMaxLevel={cap}")
    assert live_levels[cap - 1] == cap and live_levels[-1] == cap, (
        f"le clamp natif n'est pas atteint/tenu: {live_levels} (cap={cap})")

    # OFFLINE : le MEME chemin (Shiron pose Pinned -> On(PreEffectAdded) -> +1) sur le meme nb de tirs.
    off_levels = []
    ens_off = [u["id"] for u in _alive(dec, EN)]
    for k in range(len(live_levels)):
        AddEffectOperation.execute(state, source=shiron["id"], target=ens_off[k % len(ens_off)],
                                   effect_type=PINNED, name="Pinned")
        cur = [e.level for e in state.effects.by_unit.get(shiron["id"], [])
               if e.effect_type == CRESC and not e.consumed]
        off_levels.append(cur[0] if cur else 0)
    assert off_levels == live_levels, (
        f"stack offline {off_levels} != natif {live_levels} (cap={cap})")
    print(f"\n[TerrifyingCrescendo] stack natif == offline : {live_levels} (cap={cap})")


# --------------------------------------------------------------------------- 4. AnvilShield
def test_anvil_shield_ices_blocked_attacker_tile_live(live_session, rpc, build_runner):
    """Un BLOCAGE d'Arjac glace la TUILE DE L'ATTAQUANT : vecteur `On(UnitBlocked=0x3c)` emis par
    `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` -> `ApplyIce IdunBattleLogic.Entities.Abilities.Triggered.Loki.AnvilShieldAbility_ApplyIce$$CreateTrigger`.

    `--block-target 100,500` met Arjac (cote adverse) a 100 % de blocage : le blocage est CRAFTE,
    pas espere. Deux gardes en une : (a) la cascade de POSE ; (b) la DUREE de l'Ice, qui n'a aucun
    noeud `TurnsFromRounds` -> `ConvertRoundsToTurns(DefaultAmountOfRounds(17) = 2 rounds)` (#98,
    generalisation sur une AUTRE duree par defaut que celle qui a servi au diagnostic).
    CONTROLE NEGATIF offline : une attaque NON bloquee ne glace rien.
    """
    # 2 unites cote joueur : sans la 2e, l'attaque est l'action de la SEULE unite du camp -> le moteur
    # clot le tour et `RefreshEffects` decremente l'Ice AVANT la lecture (on mesurerait 3 au lieu de 4).
    rid = build_runner("92201", extra=["--p-units", f"templSwordBrother,{MA}", "--a-units", AS_,
                                       "--block-target", "100,500"] + TANKY)["rid"]

    def _iced_tiles():
        """Toutes les tuiles glacees : {(col,row): [effets Ice]} — l'ORACLE natif du maillon."""
        tm = rpc("tileMeta", {"runnerId": rid}, 90)
        out = {}
        for t in (tm.get("tiles") or []):
            ic = [e for e in (t.get("effects") or []) if e.get("effectType") == ICE]
            if ic:
                out[(t.get("col"), t.get("row"))] = ic
        return out

    # (0) AU BUILD : le plateau ne porte AUCUNE Ice -> toute Ice observee ensuite est CAUSEE par le
    # maillon (aucune autre source d'Ice dans ce roster). C'est ce qui rend l'observation causale.
    assert not _iced_tiles(), "le plateau porte deja de l'Ice au build : l'observation ne serait pas causale"

    dec, att, arjac = _bring_in_range(rpc, rid, "templSwordBrother", AS_, 1)
    if att is None:
        pytest.skip("attaquant/Arjac injoignables")
    state, dec0, board = _offline(rpc, rid, dec)

    r = _act(rpc, rid, {"kind": "ability", "casterId": att["id"], "targetId": arjac["id"],
                        "abilityType": NORMAL_ATTACK})
    if not (isinstance(r, dict) and r.get("ok")):
        pytest.skip(f"attaque KO: {str(r)[:150]}")
    dec2 = _dv(rpc, rid)
    att2 = (_alive(dec2, "templSwordBrother") or [None])[0]
    if att2 is None:
        pytest.skip("attaquant mort (riposte)")
    assert dec2.get("currentPlayer") == dec.get("currentPlayer"), (
        "le tour a bascule pendant l'attaque -> lecture POST-tick (RefreshEffects), duree non comparable")

    iced = _iced_tiles()
    assert iced, ("aucune Ice sur le plateau apres une attaque bloquee a 100% "
                  "-> le vecteur On(UnitBlocked) est MUET (maillon de pose debranche)")
    # (a) CAUSALITE : toute Ice a pour source le PORTEUR d'AnvilShield, et la tuile de l'attaquant
    #     au moment de son attaque en fait partie.
    srcs = {e.get("source") for ic in iced.values() for e in ic}
    assert srcs == {arjac["id"]}, (
        f"sources d'Ice={srcs}, attendu {{{arjac['id']}}} (le porteur d'AnvilShield)")
    assert _pos(att2) in iced, (
        f"la tuile de l'attaquant {_pos(att2)} n'est pas glacee (tuiles glacees: {sorted(iced)})")
    # (b) DUREE (#98) : une Ice FRAICHE (posee ce tour, pas encore tickee) porte la duree native
    #     pleine ; les plus anciennes ont deja decru -> le MAX est la valeur POSEE, robuste au tick.
    live_rem = max(e.get("remaining") or 0 for ic in iced.values() for e in ic)
    expected = convert_rounds_to_turns(state, default_amount_of_rounds(ICE))
    assert live_rem == expected, (
        f"duree Ice live={live_rem} != ConvertRoundsToTurns(DefaultAmountOfRounds(17)="
        f"{default_amount_of_rounds(ICE)})={expected} (facteur={state.turn_order_player_count})")

    # (c) OFFLINE : meme cascade + CONTROLE NEGATIF (sans block, rien du tout).
    if board is None:
        pytest.skip("boardGraph indispo (rejeu offline impossible)")
    apc = state.get_entity(att["id"]).get_component(PositionComponent)
    tile = board.id_at(apc.col, apc.row)
    before_off = _off_carriers(state, ICE)
    after_hit_normal_attack(state, att["id"], arjac["id"], ranged=False, profile="Physical",
                            did_block=False)
    assert _off_carriers(state, ICE) == before_off, (
        "CONTROLE NEGATIF : une attaque NON bloquee a glace une tuile (gate On(UnitBlocked) perdu)")
    after_hit_normal_attack(state, att["id"], arjac["id"], ranged=False, profile="Physical",
                            did_block=True)
    off_ice = [e for e in state.effects.by_unit.get(tile, [])
               if e.effect_type == ICE and not e.consumed]
    assert off_ice, "offline : aucune Ice posee sur la tuile de l'attaquant bloque"
    assert max(e.remaining_turns or 0 for e in off_ice) == live_rem, (
        f"duree Ice offline={[e.remaining_turns for e in off_ice]} != live={live_rem}")
    print(f"\n[AnvilShield] Ice (source=Arjac u{arjac['id']}) sur la tuile de l'attaquant "
          f"{_pos(att2)} : live rem={live_rem} == offline "
          f"(DefaultAmountOfRounds(17)={default_amount_of_rounds(ICE)} rounds x facteur "
          f"{state.turn_order_player_count})")





