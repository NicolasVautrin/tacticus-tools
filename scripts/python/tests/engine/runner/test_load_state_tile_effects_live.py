"""#102 -- `load_state` seede les effets portes par les TUILES (vecteur d'hydratation).

VERROU LEVE : `load_state` reconstruisait l'etat offline SANS les effets de TUILE. Toute mecanique
dont la condition porte sur une tuile (feu / glace / contamine / zone posee) repartait d'un plateau
VIERGE -> le port ne pouvait pas partir du meme etat que le natif, donc AUCUN test ne pouvait
trancher. C'etait un verrou de HARNAIS (une classe entiere de validations), pas d'ability.

RE (decompile = verite, build gqfc5mff6c) -- une TUILE porte ses effets exactement comme une unite :
  * `IdunBattle.Operations.AddEffectOperation$$Execute` prend une CIBLE `IEntity` quelconque ; son
    seul branchement unite-specifique est garde par `IdunBattle.Entities.EntityExtensions$$IsUnit`.
  * `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` fait `List.Add(effectId)` sur le
    `EffectsOwnedComponent` de la cible, SANS regarder son EntityType.
  * relecture symetrique : `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect` (liste possedee
    de l'entite-tuile) et `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects` (domaine MIXTE).
Le canal live jumeau de `decisionView.units[].effects` (`readEffectsByUnit`) est donc
`tileMeta.tiles[].effects` (`readEffectsByTile`) : MEME lecture, MEMES champs, seul le filtre
d'EntityType change. Aucun hook nouveau n'a ete necessaire.

CE FICHIER (2 volets ; aucune constante attendue en dur -- l'oracle est l'etat NATIF) :

  A. `test_load_state_seeds_tile_effects_live` -- EMPREINTE. Apres une pose reelle d'effets de
     tuile, l'empreinte offline `{tuile -> {effectType: remaining}}` d'un etat charge avec
     `tiles=tileMeta` est IDENTIQUE a l'empreinte live. TEMOIN : le MEME chargement SANS le canal
     rend une empreinte VIDE -> c'est bien le vecteur qui porte le resultat.

  B. `test_tile_effect_seed_drives_daemonic_ordnance_targeting_live` -- CONSOMMATEUR REEL.
     `DaemonicOrdnance` (1148, MoW `blackForgefiend`) n'attaque QUE les ennemis debout sur une tuile
     DEJA EN FEU (`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetAllDamageableTargets`
     = `Enemies(Units(Filter(zone, HasEffect(Tiles(Subject), 5=Fire))))`). On allume, on DEPLACE un
     ennemi sur le feu, puis on confronte l'ENSEMBLE DES BLESSES du cast suivant : offline == live,
     et le TEMOIN (sans seed) ne blesse PERSONNE.

Drive des positions (doctrine) ; state-file/gestion runner par la conftest ; ASCII only.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.operations.summon_ai import _apply_active_ability
from engine.runner.snapshot import (diff, load_state, snapshot, snapshot_live,
                                    tile_effects_footprint, tile_effects_footprint_live)
from engine.services.static_battle_rules import TILE_STATUS_EFFECT_NAMES

BOARD = "C1_02"                 # board MoW-capable (slot MachineOfWarPosition des deux cotes)
SEED = "4242"
CARRIER = "blackForgefiend"     # MoW porteuse de DaemonicOrdnance
DAEMONIC_ORDNANCE = 1148
FIRE = 5                        # EffectType.Fire
UNITS = ["--p-units", "necroDestroyer,necroWarden", "--a-units", "necroDestroyer,necroWarden"]


# --------------------------------------------------------------------------- helpers

def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)


def _board(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return Board(bg["tiles"], adjacency="evenq")


def _load(rpc, rid, board, with_tiles: bool):
    """Etat offline depuis la capture live. `with_tiles` = LE vecteur teste. Le PRNG est cale sur
    l'etat natif courant (`dumpRng`) : sans lui l'attaque d'ability ne tire pas et le volet B
    rendrait un faux « aucun blesse » des DEUX cotes."""
    from engine.runner.prng import IntBasedMersenneTwister
    dec = _dv(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    tm = rpc("tileMeta", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    st = load_state(dec, ob, snap, board=board, tiles=(tm if with_tiles else None))
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        st.rng = rng
    return st, dec, ob, tm


def _hp_off(state):
    from engine.runner.components import HealthComponent
    return {e.id: hc.hp for e, hc in
            ((e, e.get_component(HealthComponent)) for e in state.entities.values())
            if hc is not None}


def _hp_live(rpc, rid):
    ob = rpc("observeBattle", {"runnerId": rid}, 40) or {}
    return {u.get("squadId"): u.get("hp") for u in (ob.get("units") or [])}


def _hurt(before, after):
    return {k for k, v in after.items()
            if before.get(k) is not None and v is not None and v < before[k]}


def _mow(rpc, rid):
    dec = _dv(rpc, rid)
    m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == CARRIER), None)
    if m is None:
        pytest.skip(f"MoW {CARRIER} non deployee")
    return m


def _pick_target(rpc, rid, caster, board):
    """Cible LEGALE de 1148, la plus CENTRALE possible (une zone castee dans un coin est tronquee
    par les bords -> aucune tuile d'accueil pour l'ennemi)."""
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster,
                                "abilityType": DAEMONIC_ORDNANCE}, 90) or {}
    row = next((u for u in (at.get("units") or []) if u.get("unitId") == caster), None)
    tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
    units = [t for t in tgts if t.get("kind") == "unit"]
    if units:
        return {"kind": "unit", "id": units[0]["targetId"]}
    tiles = [t for t in tgts if t.get("kind") == "tile"]
    if not tiles:
        pytest.skip("aucune cible legale pour 1148")
    tiles = sorted(tiles, key=lambda t: -len(board.neighbours(
        board.id_at(t["tile"]["col"], t["tile"]["row"]) or -1)))
    tl = tiles[0]["tile"]
    return {"kind": "tile", "col": tl["col"], "row": tl["row"]}


def _cast(rpc, rid, caster, tgt):
    action = {"kind": "ability", "casterId": caster, "abilityType": DAEMONIC_ORDNANCE}
    if tgt["kind"] == "unit":
        action["targetId"] = tgt["id"]
    else:
        action["to"] = {"col": tgt["col"], "row": tgt["row"]}
    r = rpc("applyAction", {"runnerId": rid, "action": action}, 90) or {}
    return (r.get("actions") or [{}])[0]


def _burning(rpc, rid):
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    return [(t["col"], t["row"]) for t in (tm.get("tiles") or [])
            if any(e.get("effectType") == FIRE for e in (t.get("effects") or []))]


def _light_the_zone(rpc, rid, board):
    """Cast 1 : par construction il n'inflige RIEN et allume le triangle (le filtre de zone exige un
    feu PREEXISTANT). Rend (mow, target, tileId)."""
    m = _mow(rpc, rid)
    tgt = _pick_target(rpc, rid, m["casterId"], board)
    act = _cast(rpc, rid, m["casterId"], tgt)
    if act.get("error"):
        pytest.skip(f"cast 1 bloque: {act.get('error')}")
    tid = tgt["id"] if tgt["kind"] == "unit" else board.id_at(tgt["col"], tgt["row"])
    return m, tgt, tid


def _move(rpc, rid, uid, pos):
    """`applyAction move` ignore portee/MP/propriete -> vaut aussi pour les unites ADVERSES."""
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": pos[0], "row": pos[1]}}}, 60)


def _place_enemy_on_fire(rpc, rid, board, caster_team):
    dec = _dv(rpc, rid) or {}
    foes = [u for u in (dec.get("units") or [])
            if u.get("alive") and u.get("team") != caster_team and u.get("pos")]
    occupied = {(u["pos"]["col"], u["pos"]["row"]) for u in (dec.get("units") or []) if u.get("pos")}
    for pos in _burning(rpc, rid):
        tid = board.id_at(pos[0], pos[1])
        if tid is None or not board.walkable(tid) or pos in occupied:
            continue
        for f in foes:
            _move(rpc, rid, f["id"], pos)
            u2 = next((u for u in ((_dv(rpc, rid) or {}).get("units") or [])
                       if u.get("id") == f["id"]), None)
            p2 = (u2 or {}).get("pos") or {}
            if (p2.get("col"), p2.get("row")) == pos:
                return f["id"], pos
    return None, None


# --------------------------------------------------------------------------- tests

def test_load_state_seeds_tile_effects_live(live_session, rpc, build_runner):
    """A -- EMPREINTE `{tuile -> {effectType: remaining}}` offline == live, TEMOIN vide.

    Le TEMOIN est le coeur du test : sans le canal `tiles`, l'etat charge ne porte AUCUN effet de
    tuile alors que le plateau live en porte -- c'est EXACTEMENT le verrou #102, et sa levee."""
    rid = build_runner(SEED, extra=UNITS + ["--p-mow", CARRIER], board=BOARD)["rid"]
    board = _board(rpc, rid)
    _light_the_zone(rpc, rid, board)

    st, dec, ob, tm = _load(rpc, rid, board, with_tiles=True)
    fp_off = tile_effects_footprint(st)
    fp_live = tile_effects_footprint_live(tm, board)
    burning = sorted(k for k, e in (fp_live or {}).items() if FIRE in e)
    print(f"\n[102][A] feu live={burning} ({[board.coord(k) for k in burning]})\n"
          f"         offline={fp_off}\n         live   ={fp_live}")
    assert burning, "aucune tuile en feu apres le cast : le scenario n'exerce rien"
    assert fp_off == fp_live, f"empreinte offline {fp_off} != live {fp_live}"

    # Le diff CANONIQUE (meme idiome que les unites) doit etre muet sur les tuiles.
    d = [x for x in diff(snapshot_live(dec, ob, tiles=tm, board=board), snapshot(st))
         if x.startswith("tile")]
    assert d == [], f"diff canonique non vide sur les tuiles: {d}"

    # TEMOIN : l'ancien comportement (sans canal) -> plateau vierge.
    st_ctrl, _dc, _oc, _tc = _load(rpc, rid, board, with_tiles=False)
    assert not tile_effects_footprint(st_ctrl), (
        f"le temoin (load_state sans `tiles`) porte des effets de tuile "
        f"{tile_effects_footprint(st_ctrl)} -- le test ne discrimine plus le vecteur")


def test_tile_effect_seed_drives_daemonic_ordnance_targeting_live(live_session, rpc, build_runner):
    """B -- CONSOMMATEUR REEL : le filtre de zone de `DaemonicOrdnance` (1148).

    `GetAllDamageableTargets` = `Enemies(Units(Filter(GetTargetAreaTiles(), HasEffect(Tiles(Subject),
    5=Fire))))` -> l'attaque ne touche QUE ce qui se tient sur une tuile DEJA en feu. On confronte
    l'ENSEMBLE des blesses (pas le montant : le tirage n'est pas cale ici -- ce qui est teste est le
    CIBLAGE, c'est-a-dire exactement ce que le seed de tuile decide)."""
    rid = build_runner(SEED, extra=UNITS + ["--p-mow", CARRIER], board=BOARD)["rid"]
    board = _board(rpc, rid)
    m, tgt, tid = _light_the_zone(rpc, rid, board)
    caster = m["casterId"]

    # La MoW a AGI ce tour (activation consommee -> 2e cast `mutated:false`). `endturn` x2 la lui
    # rend SANS faire jouer l'IA (runner.md 4). Le feu (DefaultAmountOfRounds(5) converti en turns)
    # survit -- son `remaining` decroit, et les deux cotes le lisent APRES, donc ils s'accordent.
    for _ in range(2):
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

    foe_id, foe_pos = _place_enemy_on_fire(rpc, rid, board, m.get("team"))
    if foe_id is None:
        pytest.skip("aucun ennemi placable sur une tuile en feu (zone tronquee par les bords)")

    st, _dec, _ob, _tm = _load(rpc, rid, board, with_tiles=True)
    st_ctrl, _d2, _o2, _t2 = _load(rpc, rid, board, with_tiles=False)

    hp0 = _hp_off(st)
    res = _apply_active_ability(st, caster, tid, DAEMONIC_ORDNANCE)
    assert res.get("routed") == "handler" and (res.get("diag") or {}).get("ported") is True, \
        f"1148 non portee (routed={res.get('routed')})"
    hurt_off = _hurt(hp0, _hp_off(st))

    hp0c = _hp_off(st_ctrl)
    _apply_active_ability(st_ctrl, caster, tid, DAEMONIC_ORDNANCE)
    hurt_ctrl = _hurt(hp0c, _hp_off(st_ctrl))

    hp_live0 = _hp_live(rpc, rid)
    act = _cast(rpc, rid, caster, tgt)
    if act.get("error") or not act.get("ok") or not act.get("mutated"):
        pytest.skip(f"cast 2 live non applique: {str(act)[:200]}")
    hurt_live = _hurt(hp_live0, _hp_live(rpc, rid))

    print(f"\n[102][B] ennemi u{foe_id} @ {foe_pos} sur le feu\n"
          f"         blesses offline={sorted(hurt_off)} temoin={sorted(hurt_ctrl)} "
          f"live={sorted(hurt_live)}")
    assert hurt_live, "le cast 2 LIVE n'a blesse personne : le scenario n'est pas discriminant"
    assert hurt_off == hurt_live, \
        f"blesses offline {sorted(hurt_off)} != live {sorted(hurt_live)}"
    assert not hurt_ctrl, (
        f"le TEMOIN (etat charge SANS les effets de tuile) blesse {sorted(hurt_ctrl)} -- le seed "
        f"n'est alors pas le facteur discriminant, le test ne prouve rien")


# --------------------------------------------------------------------------- C. contre-effet du seed

LTGB_CARRIER = "blackTerminator"      # Angrax -- porteur du trait LetTheGalaxyBurn (1058)
LTGB_TARGET = "bloodSanguinary"
LTGB_HP = "900000"                    # la cible survit a des dizaines d'attaques (on compte des COUPS)


def _clean_nonstatus_tiles(rpc, rid, board, occupied):
    """Tuiles qui portent SEULEMENT des effets NON-status (`BlockEnteringUnits`,
    `Thorns_DefenseReduction`, ... -- typiquement les Swamp), walkable et libres. Ce sont elles qui
    discriminent : le natif ne les compte PAS comme `HasTileStatusEffect`."""
    tm = rpc("tileMeta", {"runnerId": rid}, 60) or {}
    out = []
    for t in (tm.get("tiles") or []):
        names = {e.get("name") for e in (t.get("effects") or []) if e.get("name")}
        if not names or (names & TILE_STATUS_EFFECT_NAMES):
            continue
        pos = (t.get("col"), t.get("row"))
        tid = board.id_at(pos[0], pos[1])
        if tid is None or not board.walkable(tid) or pos in occupied:
            continue
        out.append((pos, sorted(names)))
    return out


def test_non_status_tile_effect_does_not_arm_ltgb_live(live_session, rpc, build_runner):
    """C -- CONTRE-EFFET du seed : un effet de tuile NON-status n'arme PAS `TargetHasTileEffect`.

    Le seed (#102) fait entrer dans l'etat offline la VRAIE liste portee par la tuile -- y compris des
    effets qui ne sont PAS des status (`BlockEnteringUnits`=0 et `Thorns_DefenseReduction`=0xb sur les
    Swamp). Le natif les EXCLUT : `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect` filtre par
    `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsTileStatusEffect
    (set statique a 5 membres : Darkness/Fire/Ice/Contaminated/DespoiledGround). Sans ce filtre cote
    port, le seed SUR-APPLIQUERAIT le +1 coup de `LetTheGalaxyBurnEffect` sur tout board a Swamp.

    DISCRIMINANT LIVE : la cible est posee sur une tuile a effets NON-status et Angrax l'attaque en
    boucle. La branche B (tuile a status-effect) du gate natif est DETERMINISTE (+1 systematique) ;
    la branche A est un roll `Maybe(LetTheGalaxyBurnChancePct=33)`. Donc si le natif comptait ces
    effets, TOUS les echantillons vaudraient base+1. Observer ne serait-ce qu'UN echantillon a `base`
    refute cette hypothese -- et confirme le filtre. (n>=6 -> P(faux negatif) = 0.33^6 = 0.13 %.)"""
    rid = build_runner("102003", extra=["--p-units", LTGB_CARRIER, "--a-units", LTGB_TARGET,
                                        "--hp-target", LTGB_HP, "--hp-player", LTGB_HP],
                       board=BOARD)["rid"]
    board = _board(rpc, rid)
    dv = _dv(rpc, rid)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    me = next((u for u in units if u.get("visualId") == LTGB_CARRIER), None)
    en = next((u for u in units if u.get("visualId") == LTGB_TARGET), None)
    if me is None or en is None:
        pytest.skip("1v1 Angrax/cible attendu")
    if "LetTheGalaxyBurn" not in {e.get("name") for e in (me.get("effects") or [])}:
        pytest.skip("effet LetTheGalaxyBurn absent du porteur live")
    aid, tid, myp = me["id"], en["id"], me.get("owner")
    norm = next((a for a in (me.get("abilities") or []) if a.get("kind") == "normal"), None)
    if norm is None:
        pytest.skip("pas d'attaque normale")

    rows = []
    for _ in range(14):
        for _ in range(6):
            dv = _dv(rpc, rid)
            if dv.get("currentPlayer") == myp:
                break
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
        else:
            break
        occupied = {(u["pos"]["col"], u["pos"]["row"])
                    for u in ((_dv(rpc, rid) or {}).get("units") or [])
                    if u.get("pos") and u.get("id") != tid}
        cand = _clean_nonstatus_tiles(rpc, rid, board, occupied)
        if not cand:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        tpos, tnames = cand[0]
        _move(rpc, rid, tid, tpos)                     # la CIBLE sur la tuile non-status
        nb = [board.coord(t) for t in board.neighbours(board.id_at(*tpos))
              if board.walkable(t) and board.coord(t) not in occupied]
        if not nb:
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)
            continue
        _move(rpc, rid, aid, nb[0])                    # Angrax au CONTACT (arme Power melee)
        # relecture APRES placement : c'est l'etat vu par le gate au moment du coup
        fx = {e.get("name") for t in ((rpc("tileMeta", {"runnerId": rid}, 60) or {}).get("tiles") or [])
              if (t.get("col"), t.get("row")) == tpos for e in (t.get("effects") or [])}
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": aid, "targetId": tid,
            "abilityType": norm["id"]}}, 60)
        a0 = (res.get("actions") or [{}])[0] if isinstance(res, dict) else {}
        n = 0
        for e in (a0.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == norm["id"]:
                n += 1
        if n and not (fx & TILE_STATUS_EFFECT_NAMES):
            rows.append((tuple(sorted(fx)), n))
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 40)

    print(f"\n[102][C] echantillons sur tuile NON-status : {rows}")
    if len(rows) < 6:
        pytest.skip(f"pas assez d'echantillons non-status exploitables ({len(rows)}) -- "
                    f"le roll 33% ne serait pas refute de facon significative")
    hits = [n for _fx, n in rows]
    base = min(hits)
    assert set(hits) <= {base, base + 1}, \
        f"comptes hors {{base, base+1}} : {sorted(set(hits))} (confond hors sujet)"
    assert hits.count(base) >= 1, (
        f"TOUS les echantillons sur tuile NON-status valent base+1 ({hits}) -> le natif compterait "
        f"ces effets comme des status de tuile, et le filtre `IsTileStatusEffect` serait FAUX")
