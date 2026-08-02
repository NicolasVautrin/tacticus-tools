"""VALIDATION du DEBLOQUEUR « porteur absent du seed BC » (cases #92 / #54).

CE QUI ETAIT BLOQUE. Le seed BC sur disque (`data/seed-bc.json`) est la capture d'UNE bataille :
son catalogue `Units[]` ne porte que les 175 unites du compte a cet instant. 17 heros/MoW du
gameconfig n'y sont PAS (les 4 Votann, thousDaemonPrince, necroReanimator, darkaStormSpeeder, ...)
-> hors pool de `rl_duel build`, donc INCONFRONTABLES.

CE QUI EST PORTE (`scripts/python/catalog_inject.py`) : mirror offline de
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetUnitConfiguration` (l'usine a entrees de
catalogue du jeu, appelee par `...$$AddMainPlayerUnitConfigs` / `$$AddPredefinedUnitConfigs` /
`$$AddSummonUnitConfigs`), plus le SECOND catalogue trop souvent oublie :
`BattleConfiguration.Abilities` (`AbilitiesConfiguration`, keye par NOM). Le lookup d'unite est
`IdunBattle.Core.Services.BattleQuery$$GetUnitConfig` (parcours de BC.Units, egalite sur
`UnitConfiguration.Id`).

POURQUOI LES DEUX : `IdunBattle.Configuration.AbilitiesConfiguration$$GetActive` rend une
`AbilityConfiguration` VIDE quand le nom manque (TryGetValue -> ctor par defaut, pas d'exception),
et `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` LEVE une exception si la
variable est introuvable (`GetNumberConstant` -> `GetStringConstant` -> `Int32.Parse(null)` idem).
Un porteur injecte SANS sa config d'ability se deploie, s'affiche au decisionView... et FAUTE au
cast (exception managee = « system error » cote Frida). Mesure : la faute suit l'ABILITY, pas
l'entree (blackForgefiend, DEJA au catalogue, faute pareil si on lui donne 1208/1209).

TROIS ETATS distincts, verrouilles separement :
  (1) PRESENT : les 17 ids passent `buildNormalizedBC` et apparaissent au pool spawnable ;
  (2) SPAWNE  : le porteur est VIVANT sur le plateau (MoW : deployee dans `decisionView.mows`) ;
  (3) AGIT    : une ability CASTE avec un effet OBSERVABLE (spawn / degat / effet pose).
Plus un CONTROLE : pour une unite deja au catalogue, l'entree SYNTHETISEE est indiscernable de
l'entree CAPTUREE (stats natives, abilities, AbilityState, effets de trait).

Lit l'etat LIVE, drive les positions (le camp joueur est DEPLACE au contact de l'IA), state-files
uniques via la fixture `build_runner` du conftest, ASCII-only.

La FIDELITE du synthetiseur (confrontation offline aux 175 entrees capturees) et la PEREMPTION du
bloc `Units` vivent dans `test_catalog_inject_offline.py` -- fichier separe pour entrer au perimetre
de `probe_457`, cf. le bloc (0) plus bas.
"""
from __future__ import annotations

import copy
import json

import pytest

import catalog_inject as CI
import hexgeo

BOARD_UNITS = "MC1_67"
BOARD_MOW = "C1_02"      # slot MachineOfWarPosition des deux cotes
SEED = 4242
RANK = 17
ENEMY = "ultraTitus"

# Porteurs des deux familles bloquees + un temoin de generalisation hors-famille.
VOTANN = ["votanMemnyr", "votanBeserk", "votanIronmaster", "votanUthar"]   # #54
MOW_92 = ["thousDaemonPrince", "necroReanimator"]                          # #92
OTHER = ["adeptCelestine", "bloodTerminator"]                              # generalisation


# ------------------------------------------------------------------ harnais

def _build(host, sid, extra_ids, p_units, a_units=(ENEMY,), p_mow=None,
           board=BOARD_UNITS, near_enemy=False):
    """Runner isole depuis le seed BC AUGMENTE (units + configs d'ability)."""
    bc0, _added, _ab, _marker = CI.augment(host._load_seed_bc(), extra_ids, rank=RANK)
    dump = host._load_board_dump(board)
    template, pool, pool_mow = host._normalize_and_extract_pool(sid, bc0, RANK, board_dump=dump)
    bc = copy.deepcopy(template)
    host._patch_predefined_units(bc, list(a_units))
    host._patch_predefined_machines(bc, p_mow, None)
    spawns = host._spawn_points_by_twpi(bc)
    if near_enemy:
        epts = [tuple(p) for p in (spawns.get(1) or [])]
        board_cfg = bc.get("Board") or {}
        w, h = int(board_cfg.get("Width") or 0), int(board_cfg.get("Height") or 0)
        cands = [(c, r) for c, r in hexgeo.disk(epts[0][0], epts[0][1], 3)
                 if (c, r) != epts[0] and 0 <= c < w and 0 <= r < h]
        cands.sort(key=lambda p: hexgeo.distance(p, epts[0]))
        pos = cands[:len(p_units)]
    else:
        pts = spawns.get(0) or []
        pos = [(int(pts[i][0]), int(pts[i][1])) for i in range(len(p_units))]
    pu = [{"unitId": u, "playerId": host.PLAYER_ID_HUMAN, "col": pos[i][0], "row": pos[i][1]}
          for i, u in enumerate(p_units)]
    resp = host._rpc(sid, "initAndStart",
                     [{"configJson": json.dumps(bc), "seed": SEED, "playerUnits": pu}], timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        return None, pool, pool_mow, f"initAndStart KO: {resp.get('error') or resp}"
    return rid, pool, pool_mow, None


def _rpc(host, sid):
    def call(method, body, timeout=90):
        r = host._rpc(sid, method, [body], timeout=timeout)
        return r.get("result") if isinstance(r, dict) and "result" in r else r
    return call


def _footprint(call, rid):
    """{unites vivantes -> (visualId, hp, mort)} + {entite -> effets} + {tuile -> effets}.

    `decisionView` est AVEUGLE aux effets de TUILE : seul `tileMeta` (`readEffectsByTile`) les
    expose. Sans eux, une ability qui pose une zone (InfernalCannon -> Fire) se lirait « cast ok,
    aucun effet observable » — faux negatif mesure sur 1209.
    """
    dec = call("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
    ob = call("observeBattle", {"runnerId": rid}, 40)
    tm = call("tileMeta", {"runnerId": rid}, 60) or {}
    units = {u.get("squadId"): (u.get("visualId"), u.get("hp"), bool(u.get("isDead")))
             for u in (ob.get("units") or [])}
    effs = {}
    rows = [(u.get("id"), u) for u in (dec.get("units") or [])]
    rows += [(m.get("casterId"), m) for m in (dec.get("mows") or [])]
    for key, u in rows:
        if key is None:
            continue
        e = {int(x["effectType"]) for x in (u.get("effects") or [])
             if x.get("effectType") is not None}
        if e:
            effs[int(key)] = e
    tiles = {}
    for t in (tm.get("tiles") or []):
        e = {int(x["effectType"]) for x in (t.get("effects") or [])
             if x.get("effectType") is not None}
        if e:
            tiles[f"tile:{t.get('col')},{t.get('row')}"] = e
    return {"units": units, "effects": effs, "tiles": tiles}


def _observable(before, after) -> dict:
    """Ce que le cast a CHANGE : nouvelles unites, hp, morts, effets d'entite, effets de tuile."""
    new_units = {k: v[0] for k, v in after["units"].items() if k not in before["units"]}
    hp = {k: (before["units"][k][1], v[1]) for k, v in after["units"].items()
          if k in before["units"] and before["units"][k][1] != v[1]}
    deaths = {k: v[0] for k, v in after["units"].items()
              if k in before["units"] and v[2] and not before["units"][k][2]}
    new_eff = {k: sorted(e - (before["effects"].get(k) or set()))
               for k, e in after["effects"].items()
               if e - (before["effects"].get(k) or set())}
    new_tiles = {k: sorted(e - (before["tiles"].get(k) or set()))
                 for k, e in after["tiles"].items()
                 if e - (before["tiles"].get(k) or set())}
    return {"newUnits": new_units, "hpDelta": hp, "deaths": deaths,
            "newEffects": new_eff, "newTileEffects": new_tiles}


def _pick_target(tgts, caster_pos):
    """Cible LEGALE. Pour une ability TILE-target, `abilityTargets` rend TOUT l'ensemble castable
    alors qu'un behaviour de SUMMON exige une tuile ADJACENTE au caster : prendre la premiere
    donne `ok:true` / `spawned:0` -- un faux negatif « le summon ne marche pas en headless »."""
    units = [t for t in tgts if t.get("kind") == "unit"]
    if units:
        return units[0]
    tiles = [t for t in tgts if t.get("kind") == "tile"]
    if tiles and caster_pos:
        cp = (caster_pos.get("col"), caster_pos.get("row"))
        adj = [t for t in tiles
               if hexgeo.distance((t["tile"]["col"], t["tile"]["row"]), cp) == 1]
        if adj:
            return adj[0]
    return tgts[0] if tgts else None


def _cast_first_active(call, rid, caster_row):
    """Caste les abilities du porteur (actives d'abord) ; rend (abilityId, delta) au 1er effet
    OBSERVABLE, sinon (None, diagnostic)."""
    cid = caster_row.get("casterId") or caster_row.get("id")
    rows = sorted(caster_row.get("abilities") or [],
                  key=lambda a: 0 if a.get("kind") == "active" else 1)
    tried = []
    for a in rows:
        ab = a.get("id") if a.get("id") is not None else a.get("abilityType")
        if ab is None:
            continue
        at = call("abilityTargets", {"runnerId": rid, "unitId": cid, "abilityType": ab}, 90) or {}
        row = next((u for u in (at.get("units") or []) if u.get("unitId") == cid), None)
        tgts = ((row.get("abilities") or [{}])[0].get("targets") or []) if row else []
        if not tgts:
            tried.append((ab, "0 cible"))
            continue
        t = _pick_target(tgts, caster_row.get("pos"))
        action = {"kind": "ability", "casterId": cid, "abilityType": ab}
        if t.get("kind") == "unit":
            action["targetId"] = t["targetId"]
        else:
            action["to"] = {"col": t["tile"]["col"], "row": t["tile"]["row"]}
        before = _footprint(call, rid)
        res = call("applyAction", {"runnerId": rid, "action": action}, 90) or {}
        act0 = (res.get("actions") or [{}])[0]
        delta = _observable(before, _footprint(call, rid))
        if any(delta.values()):
            return ab, delta
        tried.append((ab, f"ok={act0.get('ok')} err={act0.get('error')}"))
    return None, tried


# ------------------------------------------------------------------ (0) offline
#
# LE VOLET OFFLINE A DEMENAGE dans `test_catalog_inject_offline.py` (#457). Il ne montait aucun
# runner, mais il vivait ici -- donc dans un fichier `_live.py`, hors du perimetre de `probe_457`,
# le seul cliquet qui voie un test offline ROUGE EN PERMANENCE. Son rouge (bloc `Units` du seed BC
# perime, #254-bc) a tenu quatre jours sans que rien ne le signale. Dans un fichier non-`_live`, il
# entre au cliquet TOUT SEUL. Ne pas re-deposer de test offline ici.


# ------------------------------------------------------------------ (1) PRESENT

def test_1_present_les_17_porteurs_hors_catalogue(host, live_session):
    """Les 17 unites `units.lineup` absentes du seed BC passent la normalisation NATIVE
    (`buildNormalizedBC` = `IStatsFormula.StatsUsingProgressionIndexFor`) et atterrissent
    dans le pool spawnable — MoW comprises (detectees par le trait MachineOfWar)."""
    seed = host._load_seed_bc()
    missing = CI.missing_from_seed_bc(seed)
    assert missing, "aucune unite manquante : seed BC change, ce test n'a plus d'objet"
    bc0, _a, _b, _c = CI.augment(seed, missing, rank=RANK)
    dump = host._load_board_dump(BOARD_UNITS)
    _t, pool, pool_mow = host._normalize_and_extract_pool(live_session, bc0, RANK, board_dump=dump)
    absent = [u for u in missing if u not in pool and u not in pool_mow]
    print(f"\n[catalog/1] {len(missing) - len(absent)}/{len(missing)} au pool "
          f"(MoW: {[u for u in missing if u in pool_mow]})")
    assert not absent, f"injectees mais hors pool: {absent}"


# ------------------------------------------------------------------ CONTROLE

def test_controle_entree_synthetisee_indiscernable(host, live_session):
    """Pour une unite DEJA au catalogue, remplacer l'entree CAPTUREE par l'entree SYNTHETISEE
    ne change RIEN de ce que le jeu expose : stats recalculees, abilities + AbilityState,
    effets poses au deploiement (sonde des traits : `Ambush` -> Ambush_CanResurrect)."""
    carrier = "genesBiophagus"
    seed = host._load_seed_bc()
    patched = copy.deepcopy(seed)
    i = next((k for k, u in enumerate(patched["Units"]) if u.get("Id") == carrier), None)
    if i is None:
        pytest.skip(f"{carrier} absent du seed BC capture")
    synth = CI.synthesize(carrier, rank=RANK)
    # on garde le multiplicateur capture : il releve de la progression JOUEUR, pas du catalogue
    synth["AbilityVariablesMultiplierPercentage"] = \
        patched["Units"][i]["AbilityVariablesMultiplierPercentage"]
    patched["Units"][i] = synth

    call = _rpc(host, live_session)
    profiles = {}
    for tag, src in (("capture", seed), ("synth", patched)):
        dump = host._load_board_dump(BOARD_UNITS)
        template, _pool, _pm = host._normalize_and_extract_pool(
            live_session, src, RANK, board_dump=dump)
        bc = copy.deepcopy(template)
        host._patch_predefined_units(bc, [ENEMY])
        host._patch_predefined_machines(bc, None, None)
        pts = host._spawn_points_by_twpi(bc).get(0) or []
        resp = host._rpc(live_session, "initAndStart",
                         [{"configJson": json.dumps(bc), "seed": SEED,
                           "playerUnits": [{"unitId": carrier, "playerId": host.PLAYER_ID_HUMAN,
                                            "col": int(pts[0][0]), "row": int(pts[0][1])}]}],
                         timeout=60)
        rid = (resp.get("result") or {}).get("runnerId")
        if rid is None:
            pytest.skip(f"build {tag} KO: {resp.get('error')}")
        try:
            dec = call("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
            cs = call("combatSnapshot", {"runnerId": rid}, 60)
            du = next((u for u in (dec.get("units") or [])
                       if u.get("visualId") == carrier), None)
            cu = next((u for u in (cs.get("units") or [])
                       if (u.get("unitConfig") or {}).get("visualId") == carrier), None)
            assert du is not None and cu is not None, f"{carrier} introuvable ({tag})"
            profiles[tag] = {
                "stats": cu.get("stats"), "healthMax": cu.get("healthMax"),
                "unitConfig": cu.get("unitConfig"),
                "abilityStates": sorted(json.dumps(a, sort_keys=True)
                                        for a in (cu.get("abilityStates") or [])),
                "abilities": sorted(json.dumps(a, sort_keys=True)
                                    for a in (du.get("abilities") or [])),
                "effects": sorted(json.dumps({k: v for k, v in e.items() if k != "effectId"},
                                             sort_keys=True) for e in (du.get("effects") or [])),
            }
        finally:
            host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
    print(f"\n[catalog/controle] attack={profiles['synth']['stats']['attack']} "
          f"hp={profiles['synth']['healthMax']} "
          f"abilities={len(profiles['synth']['abilityStates'])}")
    assert profiles["capture"] == profiles["synth"], (
        "l'entree synthetisee decrit une autre unite que l'entree capturee:\n"
        f"  capture={json.dumps(profiles['capture'])[:600]}\n"
        f"  synth  ={json.dumps(profiles['synth'])[:600]}")


# ------------------------------------------------------------------ (2)+(3) heros

@pytest.mark.parametrize("carrier", VOTANN + OTHER)
def test_2_3_porteur_injecte_spawne_et_agit(host, live_session, carrier):
    """(2) le porteur injecte est VIVANT sur le plateau avec son kit complet (abilities au bon
    niveau, effets de passif poses au deploiement), et (3) il CASTE avec un effet observable."""
    call = _rpc(host, live_session)
    rid, pool, _pm, err = _build(host, live_session, [carrier], [carrier], near_enemy=True)
    if rid is None:
        pytest.fail(f"{carrier}: {err}")
    try:
        dec = call("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        ob = call("observeBattle", {"runnerId": rid}, 40)
        alive = {u.get("visualId") for u in (ob.get("units") or []) if not u.get("isDead")}
        row = next((u for u in (dec.get("units") or []) if u.get("visualId") == carrier), None)
        assert carrier in alive and row is not None, \
            f"(2) {carrier} non spawne (alive={carrier in alive})"
        actives = [a for a in (row.get("abilities") or []) if a.get("kind") == "active"]
        assert actives, f"(2) {carrier} spawne SANS ability active: {row.get('abilities')}"
        print(f"\n[catalog/2] {carrier} hp={row.get('hp')} "
              f"abilities={[(a.get('id'), a.get('level'), a.get('multiplier')) for a in actives]} "
              f"effets={[e.get('name') for e in (row.get('effects') or [])]}")
        ab, delta = _cast_first_active(call, rid, row)
        assert ab is not None, f"(3) {carrier}: aucun cast observable ({delta})"
        print(f"[catalog/3] {carrier} ability={ab} delta={json.dumps(delta)[:300]}")
    finally:
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)


# ------------------------------------------------------------------ (2)+(3) MoW

@pytest.mark.parametrize("mow", MOW_92)
def test_2_3_mow_injectee_se_deploie_et_caste(host, live_session, mow):
    """#92 : les deux MoW absentes du seed BC se DEPLOIENT (`decisionView.mows`) et CASTENT.
    Le deploiement passe par `BC.PredefinedMachines` -> `AddMachineMessage`, donc par le meme
    lookup `BattleQuery$$GetUnitConfig` que les unites."""
    call = _rpc(host, live_session)
    rid, _pool, pool_mow, err = _build(host, live_session, [mow],
                                       ["necroDestroyer", "necroWarden"],
                                       a_units=("necroDestroyer", "necroWarden"),
                                       p_mow=mow, board=BOARD_MOW)
    if rid is None:
        pytest.fail(f"{mow}: {err}")
    try:
        assert mow in pool_mow, f"(1) {mow} hors pool MoW: {pool_mow}"
        dec = call("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        m = next((x for x in (dec.get("mows") or []) if x.get("visualId") == mow), None)
        assert m is not None, (f"(2) {mow} non deployee "
                               f"(mows={[x.get('visualId') for x in (dec.get('mows') or [])]})")
        print(f"\n[catalog/2] MoW {mow} casterId={m.get('casterId')} "
              f"abilities={[(a.get('id') or a.get('abilityType'), a.get('level'), a.get('multiplier')) for a in (m.get('abilities') or [])]}")
        ab, delta = _cast_first_active(call, rid, m)
        assert ab is not None, f"(3) {mow}: aucun cast observable ({delta})"
        print(f"[catalog/3] MoW {mow} ability={ab} delta={json.dumps(delta)[:300]}")
    finally:
        host._rpc(live_session, "disposeRunner", [{"runnerId": rid}], timeout=20)
