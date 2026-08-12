"""#955 -- confrontation LIVE des deux passifs : `Possession` (`blackPossession`) et
`SummaryExecution` (`astraYarrick`).

Deux volets independants (`--volet possession|summary`), chacun avec un TEMOIN QUI DISCRIMINE.

VOLET `possession` -- DEUX bras qui ne different QUE par la GEOMETRIE :
  * `melee`  : Archimatos ADJACENT (d == 1) a sa victime  -> `unitId`   = `blackSmnBloodletter`
  * `ranged` : Archimatos a d == 2 de sa victime          -> `unitId_2` = `thousSmnBlueHorror`
La geometrie est CALCULEE depuis le `boardGraph` puis ASSERTIONNEE contre les positions reelles ;
un bras qui n'obtient pas sa configuration fait ECHOUER le probe (jamais un skip). Et le probe
REFUSE DE CONCLURE si les deux bras rendent le MEME summon cote NATIF : c'est exactement ce qu'un
port lisant la mauvaise adjacence produirait, donc un temoin non discriminant ne prouve rien.

VOLET `summary` -- l'aura permanente 1043 `SummaryExecution_BaseEffect` :
  Yarrick invoque ses Cadian Guardsmen (`SendInTheNextWave`), qui portent le trait `BattleFatigue`
  et sont donc les CIBLES du selecteur `Friends(Owner, UnitsWithTrait(AllAliveUnits,
  BattleFatigue))`. On lit la MODIFICATION du stat Attack par-source (`statModSources`) sur un
  Guardsman, et on la compare a `extraDmg[niveau de Yarrick] x multiplier`. Le TEMOIN qui
  discrimine est l'ALLIE NON-Guardsman present dans la meme equipe : lui n'a PAS le trait, il ne
  doit RIEN recevoir. Si les deux recoivent la meme chose, le selecteur ne mord pas et le probe
  refuse de conclure.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

from probe_r6_round_materialize import _mkrpc          # foyer partage de la session RPC

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

BOARD = "MC1_67"
SEED = "4321"

ARCHIMATOS = "blackPossession"
YARRICK = "astraYarrick"
SEND_IN_THE_NEXT_WAVE = 1016            # ActiveAbilityType de Yarrick (2 Cadian Guardsmen)
#: L'unitId de CONFIG du summon porteur du trait `BattleFatigue`... et le `visualId` sous lequel
#: `decisionView` le PUBLIE, qui n'est pas le meme (#895 : 429 unites sur 683 ont
#: `visualId != id`, toutes `npc` ou `summons`). Mesure : le cast rend `astraNpc1Guardsman`.
GUARDSMAN = "astraSmnGuardsman"
GUARDSMAN_VIS = ("astraSmnGuardsman", "astraNpc1Guardsman")
BLOODLETTER = "blackSmnBloodletter"     # `unitId`   (constante 0) -- kill MELEE
BLUE_HORROR = "thousSmnBlueHorror"      # `unitId_2` (constante 4) -- kill NON-melee

EFF_BASE = 1043                         # EffectType.SummaryExecution_BaseEffect
EFF_EXEC = 1031                         # EffectType.SummaryExecution_Effect


def _build(p_units, a_units, extra):
    sf = ROOT / "logs" / "runners" / ("p955-%s.json" % uuid.uuid4().hex[:8])
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED, "--state-file", str(sf),
            "--board", BOARD, "--rank", "17",
            "--p-units", ",".join(p_units), "--a-units", ",".join(a_units),
            "--crit", "0,0", "--crit-target", "0,0", "--block-target", "0,0",
            "--block-player", "0,0", "--no-ai", *extra]
    proc = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, None, (proc.stderr or proc.stdout or "")[-1200:]
    return int(json.loads(sf.read_text())["runnerId"]), sf, None


def _view(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "allAbilities": True,
                                "includeInactive": True}, 180)


def _units(dv):
    return list(dv.get("units") or [])


def _by_vis(dv, vis):
    return [u for u in _units(dv) if u.get("visualId") == vis]


def _unit(dv, uid):
    return next((x for x in _units(dv) if int(x.get("id", -1)) == int(uid)), None)


def _pos(dv, uid):
    p = (_unit(dv, uid) or {}).get("pos")
    return None if not p else (int(p["col"]), int(p["row"]))


def _normal_attack_id(dv, uid):
    for a in ((_unit(dv, uid) or {}).get("abilities") or []):
        if a.get("kind") == "normal":
            return int(a.get("id"))
    return None


def _effets(dv, uid):
    return sorted(int(e["effectType"]) for e in ((_unit(dv, uid) or {}).get("effects") or [])
                  if e.get("effectType") is not None)


def _board(rpc, rid):
    from engine.entities.pathfinding.board import Board
    return Board(rpc("boardGraph", {"runnerId": rid})["tiles"], adjacency="native_sym")


# --------------------------------------------------------------------------- volet POSSESSION
def _geometrie_possession(board):
    """CALCULE (jamais espere) un triplet POSABLE : `archi`, `v1` a d == 1, `v2` a d == 2.

    On prefere le CENTRE du board (un montage en coin sous-exercerait le voisinage -- runner.md),
    et on exige que la tuile de CHAQUE victime ait au moins une voisine libre : le natif spawne sur
    `FreeTilesOrAdjacentFreeTiles(Tiles(Target))`, donc une victime sans issue rendrait le bras
    muet pour une raison qui n'a rien a voir avec le passif."""
    import hexgeo
    ids = [t for t in sorted(board.by_id.keys()) if board.walkable(t)]
    coords = {t: board.coord(t) for t in ids}
    coords = {t: c for t, c in coords.items() if c is not None}
    if not coords:
        return None, "boardGraph sans tuile walkable"
    cols = [c for c, _ in coords.values()]
    rows = [r for _, r in coords.values()]
    mid = ((min(cols) + max(cols)) / 2.0, (min(rows) + max(rows)) / 2.0)
    par_centre = sorted(coords.items(),
                        key=lambda kv: abs(kv[1][0] - mid[0]) + abs(kv[1][1] - mid[1]))
    libres = set(coords.values())
    for _t, a in par_centre:
        v1 = sorted(c for c in libres if c != a and hexgeo.distance(a, c) == 1)
        v2 = sorted(c for c in libres if c != a and hexgeo.distance(a, c) == 2)
        for c1 in v1:
            for c2 in v2:
                if c1 == c2:
                    continue
                # une voisine LIBRE (hors les trois occupees) pour chaque victime
                ok = all(any(n in libres and n not in (a, c1, c2)
                             for n in [x for x in libres if hexgeo.distance(v, x) == 1])
                         for v in (c1, c2))
                if not ok:
                    continue
                # un FIGURANT loin de tout : il maintient la bataille en `Running` apres le kill
                # (cf. le commentaire du montage) sans jamais entrer dans la scene mesuree.
                fig = sorted(c for c in libres
                             if c not in (a, c1, c2)
                             and min(hexgeo.distance(c, x) for x in (a, c1, c2)) >= 4)
                if fig:
                    return {"archi": a, "v1": c1, "v2": c2, "figurant": fig[-1]}, None
    return None, "aucune geometrie (archi + victime d=1 + victime d=2 + figurant) sur %s" % BOARD


def _replay_possession(cap, board, attaquant, cible, mutate=None):
    """Rejoue L'ATTAQUE offline depuis la MEME capture et le MEME flux RNG, et rend les summons
    que le PORT a poses (visualId + position).

    ⚠ LE MUTANT EST POSE **AVANT** `load_state` : le registre `ABILITY_TRIGGERS` est lu a la
    COLLECTE des triggers, qui se fait au chargement (`collect_triggered_abilities`) -- un `pop`
    fait apres arriverait TROP TARD (forme exacte du faux vert documentee par #932)."""
    from engine.runner.snapshot import load_state
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.components import UnitComponent, PositionComponent
    from engine.runner.operations.triggers.dispatch import registry as REG
    from engine.runner.operations.triggers.loki import possession as POSS

    saved_reg = saved_rng = None
    if mutate == "m_registre":                     # le passif n'est plus inscrit du tout
        saved_reg = REG.ABILITY_TRIGGERS.pop("Possession", None)
        assert saved_reg is not None, "MUTANT INOPERANT : ABILITY_TRIGGERS['Possession']"
    elif mutate == "m_melee":                      # la nature du coup est INVERSEE
        saved_rng = POSS._is_ranged_position
        POSS._is_ranged_position = lambda st, a, b, _o=saved_rng: not _o(st, a, b)
    try:
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
        rng = IntBasedMersenneTwister()
        rng.mt = list(cap["rng"]["mt"])
        rng.mti = cap["rng"]["mti"]
        st.rng = rng
        avant = set(st.entities.keys())
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(int(attaquant), int(cible)))
        out = []
        for eid in sorted(set(st.entities.keys()) - avant):
            e = st.get_entity(eid)
            uc = e.get_component(UnitComponent)
            pc = e.get_component(PositionComponent)
            out.append({"visual_id": None if uc is None else uc.visual_id,
                        "pos": None if pc is None else [pc.col, pc.row]})
        return out
    finally:
        if saved_reg is not None:
            REG.ABILITY_TRIGGERS["Possession"] = saved_reg
        if saved_rng is not None:
            POSS._is_ranged_position = saved_rng


def _libres_autour(dv, p):
    """Les tuiles hex-adjacentes a `p` qu'AUCUNE unite vivante n'occupe -- le pool de repli de
    `FreeTilesOrAdjacentFreeTiles` quand la tuile de la victime est prise."""
    import hexgeo
    occ = {_pos(dv, int(u["id"])) for u in _units(dv)
           if not u.get("isDead") and (u.get("hp") or 0) > 0}
    return sorted(c for c in hexgeo.disk(p[0], p[1], 1) if c != tuple(p) and c not in occ)


def _tue(rpc, rid, cid, tid, ab):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": int(cid), "targetId": int(tid),
        "abilityType": int(ab)}, "captureEvents": True}, 180)


def volet_possession(rpc, cible):
    out = {"volet": "possession"}
    rid0, sf0, err = _build([ARCHIMATOS], [cible], [])
    if rid0 is None:
        return {**out, "erreur": "build sonde KO : %s" % err}
    try:
        board = _board(rpc, rid0)
    finally:
        rpc("disposeRunner", {"runnerId": rid0}, 60)
    geo, why = _geometrie_possession(board)
    if geo is None:
        return {**out, "erreur": why}
    out["geometrie"] = {k: list(v) for k, v in geo.items()}

    # UN BUILD PAR BRAS. Les jouer dans la MEME bataille est mesure IMPOSSIBLE : le Bloodletter
    # invoque au 1er bras est `ai_controlled` (trait `Summon`), donc `PlayAutomaticUnits` le fait
    # jouer au turn-start suivant et il ACHEVE la seconde victime -- la bataille passe en
    # `stage Finished` et le 2e bras rend un vide qui se lirait, a tort, comme « le passif n'a pas
    # fire ». Mesure : `applyAction` -> `{"ok": false, "error": "stage Finished (need Running)"}`.
    bras = {}
    for nom, d in (("melee", 1), ("ranged", 2)):
        v = geo["v1"] if d == 1 else geo["v2"]
        # UN SEUL ennemi ne suffit PAS : le tuer finit la bataille (`stage Finished`) et le
        # `decisionView` d'apres ne publie plus aucun summon -- mesure : les deux bras rendaient
        # `summons: []` alors que le meme bras melee, joue avec un SECOND ennemi vivant, rend bien
        # `blackSmnBloodletter`. Le figurant reste donc EN VIE, loin de la scene.
        rid, sf, err = _build(
            [ARCHIMATOS], [cible, cible],
            ["--hp-target", "300", "--dmg-target", "1",
             "--place", "%s:%d,%d" % (ARCHIMATOS, geo["archi"][0], geo["archi"][1]),
             "--a-place", "%s:%d,%d" % (cible, v[0], v[1]),
             "--a-place", "%s:%d,%d" % (cible, geo["figurant"][0], geo["figurant"][1])])
        if rid is None:
            return {**out, "erreur": "build KO (%s) : %s" % (nom, err)}
        try:
            dv = _view(rpc, rid)
            archi = _by_vis(dv, ARCHIMATOS)
            ennemis = [u for u in _units(dv) if u.get("visualId") == cible]
            if not archi or not ennemis:
                return {**out, "erreur": "montage %s incomplet" % nom}
            aid = int(archi[0]["id"])
            import hexgeo
            # la VICTIME est celle qui est A LA BONNE DISTANCE ; le figurant, lui, est a >= 4.
            ap = _pos(dv, aid)
            cands = sorted((hexgeo.distance(ap, _pos(dv, int(u["id"]))), int(u["id"]))
                           for u in ennemis)
            vid = cands[0][1]
            # ASSERTION de geometrie contre les positions REELLES, pas les positions demandees.
            d_reel = hexgeo.distance(_pos(dv, aid), _pos(dv, vid))
            if d_reel != d:
                return {**out, "erreur": "bras %s : d reel = %d, attendu %d" % (nom, d_reel, d)}
            ab = _normal_attack_id(dv, aid)
            avant = {int(u["id"]) for u in _units(dv)}
            cap = {"dec": dv, "ob": rpc("observeBattle", {"runnerId": rid}, 60),
                   "snap": rpc("combatSnapshot", {"runnerId": rid}, 150),
                   "rng": rpc("dumpRng", {"runnerId": rid}, 30)}
            res = _tue(rpc, rid, aid, vid, ab)
            dv2 = _view(rpc, rid)
            victime = _unit(dv2, vid)
            neufs = [u for u in _units(dv2) if int(u["id"]) not in avant]
            bras[nom] = {
                "runner": rid, "victime": vid, "d": d_reel, "normal_attack": ab,
                "victime_morte": bool(victime is None or victime.get("isDead")
                                      or (victime.get("hp") or 0) <= 0),
                "summons": sorted(u.get("visualId") for u in neufs),
                "summon_pos": sorted([list(_pos(dv2, int(u["id"])) or ()) for u in neufs]),
                "victime_pos": list(v),
                "ok_rpc": bool(res.get("ok", True)),
                "rpc_error": res.get("error"),
            }
            for m in (None, "m_registre", "m_melee"):
                try:
                    port = _replay_possession(cap, board, aid, vid, mutate=m)
                except Exception as exc:              # une exception est un RESULTAT, pas un skip
                    port = [{"exception": "%s: %s" % (type(exc).__name__, exc)}]
                bras[nom]["port" if m is None else ("port_%s" % m)] = port
        finally:
            try:
                rpc("disposeRunner", {"runnerId": rid}, 60)
            except Exception:
                pass
    out["bras"] = bras
    m, r = bras["melee"], bras["ranged"]
    if not (m["victime_morte"] and r["victime_morte"]):
        return {**out, "erreur": "une victime au moins n'est pas morte -- rien a conclure"}
    out["discrimine"] = bool(m["summons"] and r["summons"] and m["summons"] != r["summons"])
    out["verdict_natif"] = {
        "melee_attendu": BLOODLETTER, "melee_obtenu": m["summons"],
        "ranged_attendu": BLUE_HORROR, "ranged_obtenu": r["summons"],
        "conforme": (m["summons"] == [BLOODLETTER] and r["summons"] == [BLUE_HORROR]),
    }
    out["verdict_port"] = {
        nom: {
            "natif": b["summons"],
            "port": sorted(x.get("visual_id") for x in b["port"]),
            "egal": sorted(x.get("visual_id") for x in b["port"]) == b["summons"],
            "meme_tuile": sorted([x.get("pos") for x in b["port"]]) == b["summon_pos"],
            "mutant_registre_mord": sorted(x.get("visual_id") for x in b["port_m_registre"]) != b["summons"],
            "mutant_melee_mord": sorted(x.get("visual_id") for x in b["port_m_melee"]) != b["summons"],
        } for nom, b in bras.items()
    }
    return out


# --------------------------------------------------------------------------- volet SUMMARY
def _geometrie_summary(board):
    """`yarrick` au centre, `allie` temoin ADJACENT (il doit etre a portee de tout selecteur qu'on
    voudrait accuser de geometrie -- le selecteur de `SummaryExecution` n'en a AUCUNE, et c'est
    justement ce qu'on veut pouvoir affirmer), `cible` a d == 2 (portee de `SendInTheNextWave`),
    `figurant` loin (maintient la bataille en `Running`). Les tuiles ou les Guardsmen se poseront
    (rayon 2 autour de la cible) doivent laisser >= 2 places libres."""
    import hexgeo
    ids = [t for t in sorted(board.by_id.keys()) if board.walkable(t)]
    coords = {t: board.coord(t) for t in ids}
    coords = {t: c for t, c in coords.items() if c is not None}
    if not coords:
        return None, "boardGraph sans tuile walkable"
    cols = [c for c, _ in coords.values()]
    rows = [r for _, r in coords.values()]
    mid = ((min(cols) + max(cols)) / 2.0, (min(rows) + max(rows)) / 2.0)
    par_centre = sorted(coords.items(),
                        key=lambda kv: abs(kv[1][0] - mid[0]) + abs(kv[1][1] - mid[1]))
    libres = set(coords.values())
    for _t, y in par_centre:
        adj = sorted(c for c in libres if hexgeo.distance(y, c) == 1)
        d2 = sorted(c for c in libres if hexgeo.distance(y, c) == 2)
        if not adj or not d2:
            continue
        allie, cible = adj[0], d2[0]
        libre_pres_cible = [c for c in libres
                            if c not in (y, allie, cible) and hexgeo.distance(cible, c) <= 2]
        if len(libre_pres_cible) < 2:
            continue
        fig = sorted(c for c in libres
                     if c not in (y, allie, cible)
                     and min(hexgeo.distance(c, x) for x in (y, allie, cible)) >= 5)
        if fig:
            return {"yarrick": y, "allie": allie, "cible": cible, "figurant": fig[-1]}, None
    return None, "aucune geometrie (yarrick + allie d=1 + cible d=2 + figurant) sur %s" % BOARD


def _replay_summary(cap, board, sujets, mutate=None):
    """Charge l'etat offline et lit la MODIFICATION du stat Attack par-source sur chaque sujet.

    `load_state` appelle `attribute_aura_stat_modifiers` au SEED : la part deja CAPTUREE est
    re-attribuee sous la cle de l'effet (somme inchangee, mais DROPPABLE). On lit donc la
    contribution sous la cle d'aura de l'effet 1043, pas le total (qui contiendrait aussi le
    residu opaque d'une capture non attribuee).

    ⚠ LE MUTANT EST POSE **AVANT** `load_state` (meme raison que le volet possession)."""
    from engine.runner.snapshot import load_state
    from engine.runner.components import StatsComponent
    from engine.entities.effects.factory import EFFECT_CLASSES
    from engine.entities.effects.loki import summary_execution as SE
    from engine.entities.stats import StatType

    saved_eff = saved_sel = None
    if mutate == "m_effet":                        # 1043 n'est plus une classe portee
        saved_eff = EFFECT_CLASSES.pop("SummaryExecution_BaseEffect", None)
        assert saved_eff is not None, "MUTANT INOPERANT : EFFECT_CLASSES['SummaryExecution_BaseEffect']"
    elif mutate == "m_trait":                      # le gate de trait est retire du selecteur
        saved_sel = SE._ASummaryExecutionAuraEffect.aura_stat_modification_targets
        SE._ASummaryExecutionAuraEffect.aura_stat_modification_targets = \
            lambda self, state, owner_id: [int(u) for u in state.entities.keys()]
    try:
        st = load_state(cap["dec"], cap["ob"], cap["snap"], board=board)
        out = {"total": {}, "sous_cle_aura": {}}
        for quoi, uid in sujets.items():
            e = st.get_entity(int(uid))
            sc = e.get_component(StatsComponent) if e is not None else None
            us = getattr(sc.ctx, "stats", None) if (sc is not None and sc.ctx is not None) else None
            if us is None:
                out["total"][quoi] = out["sous_cle_aura"][quoi] = None
                continue
            comp = us.components.get(int(StatType.ATTACK))
            mod = getattr(comp, "modification", None) if comp is not None else None
            if mod is None:
                out["total"][quoi] = out["sous_cle_aura"][quoi] = 0
                continue
            out["total"][quoi] = int(sum(mod.per_source.values()))
            # ⚠ LE TOTAL NE DISCRIMINE RIEN : `load_state` seede la modification depuis
            # `combatSnapshot`, donc la part CAPTUREE y est de toute facon -- sous la cle opaque
            # `CAPTURED_SOURCE` si rien ne l'attribue. Mesure : les deux mutants laissaient le
            # total a 400. Ce qui mesure MON port, c'est la part portee par la cle d'AURA, celle
            # que `attribute_aura_stat_modifiers` (appele au SEED) ne pose QUE si l'effet declare
            # l'interface `aura_stat_modification_*` ET selectionne cette unite.
            out["sous_cle_aura"][quoi] = int(sum(
                v for k, v in mod.per_source.items()
                if isinstance(k, tuple) and k and k[0] == "aura_statmod"))
        return out
    finally:
        if saved_eff is not None:
            EFFECT_CLASSES["SummaryExecution_BaseEffect"] = saved_eff
        if saved_sel is not None:
            SE._ASummaryExecutionAuraEffect.aura_stat_modification_targets = saved_sel


def volet_summary(rpc, allie, cible):
    """Yarrick + un ALLIE temoin (sans `BattleFatigue`) ; Yarrick invoque ses Guardsmen, qui
    PORTENT le trait. On lit la modification du stat Attack PAR SOURCE sur un Guardsman et sur
    l'allie temoin : seul le Guardsman doit recevoir quelque chose."""
    out = {"volet": "summary"}
    # La geometrie est POSEE AU BUILD (`--place`/`--a-place`), jamais atteinte par des tours de
    # marche : `SendInTheNextWave` exige la cible a <= 2 hexes, et un rapprochement pas-a-pas
    # depend d'un RPC de mouvement dont la forme n'est pas garantie.
    rid0, _sf0, err = _build([YARRICK], [cible], [])
    if rid0 is None:
        return {**out, "erreur": "build sonde KO : %s" % err}
    try:
        board = _board(rpc, rid0)
    finally:
        rpc("disposeRunner", {"runnerId": rid0}, 60)
    geo, why = _geometrie_summary(board)
    if geo is None:
        return {**out, "erreur": why}
    out["geometrie"] = {k: list(v) for k, v in geo.items()}
    rid, sf, err = _build(
        [YARRICK, allie], [cible, cible],
        ["--hp-target", "20000", "--dmg-target", "1",
         "--place", "%s:%d,%d" % (YARRICK, geo["yarrick"][0], geo["yarrick"][1]),
         "--place", "%s:%d,%d" % (allie, geo["allie"][0], geo["allie"][1]),
         "--a-place", "%s:%d,%d" % (cible, geo["cible"][0], geo["cible"][1]),
         "--a-place", "%s:%d,%d" % (cible, geo["figurant"][0], geo["figurant"][1])])
    if rid is None:
        return {**out, "erreur": "build KO : %s" % err}
    out["runner"] = rid
    try:
        import hexgeo
        dv = _view(rpc, rid)
        y = _by_vis(dv, YARRICK)
        a = _by_vis(dv, allie)
        if not y or not a:
            return {**out, "erreur": "Yarrick (%d) ou allie (%d) absent" % (len(y), len(a))}
        yid, aid = int(y[0]["id"]), int(a[0]["id"])
        out["yarrick"] = yid
        out["allie_temoin"] = aid
        out["effets_yarrick_avant"] = _effets(dv, yid)
        enn = sorted((hexgeo.distance(_pos(dv, yid), _pos(dv, int(u["id"]))), int(u["id"]))
                     for u in _units(dv) if u.get("visualId") == cible)
        if not enn:
            return {**out, "erreur": "aucun ennemi monte"}
        cible_id = enn[0][1]
        out["distance_cast"] = hexgeo.distance(_pos(dv, yid), _pos(dv, cible_id))
        res = rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "ability", "casterId": yid, "targetId": cible_id,
            "abilityType": SEND_IN_THE_NEXT_WAVE}, "captureEvents": True}, 220)
        out["cast_ok"] = bool(res.get("ok", True))
        out["cast_rpc"] = {k: v for k, v in res.items() if k != "actions"}
        out["abilites_yarrick"] = [(a.get("id"), a.get("kind"), a.get("state"))
                                   for a in ((_unit(dv, yid) or {}).get("abilities") or [])]
        dv = _view(rpc, rid)
        out["units_apres"] = sorted((int(u["id"]), u.get("visualId")) for u in _units(dv))
        gardes = [int(u["id"]) for u in _units(dv) if u.get("visualId") in GUARDSMAN_VIS]
        out["guardsmen"] = gardes
        out["effets_yarrick_apres"] = _effets(dv, yid)
        if not gardes:
            return {**out, "erreur": "aucun Guardsman invoque (cast refuse ?)"}
        sujets = {"guardsman": gardes[0], "allie_temoin": aid, "yarrick": yid}
        natif = {}
        for quoi, uid in sujets.items():
            try:
                sm = rpc("statModSources", {"runnerId": rid, "unitId": uid}, 150)
                u = next((x for x in (sm.get("units") or [])
                          if int(x.get("entityId", -1)) == int(uid)), {})
                natif[quoi] = int(((u.get("mods") or {}).get("attack") or {}).get("total") or 0)
            except Exception as exc:
                natif[quoi] = "ERREUR %s" % type(exc).__name__
        out["attack_mod_natif"] = natif
        # TEMOIN QUI DISCRIMINE : l'allie SANS le trait ne doit RIEN recevoir. S'il recoit la meme
        # chose que le Guardsman, le selecteur ne mord pas et la mesure ne prouve rien.
        out["discrimine"] = bool(natif.get("guardsman") and not natif.get("allie_temoin"))
        cap = {"dec": _view(rpc, rid), "ob": rpc("observeBattle", {"runnerId": rid}, 60),
               "snap": rpc("combatSnapshot", {"runnerId": rid}, 150)}
        for m in (None, "m_effet", "m_trait"):
            try:
                port = _replay_summary(cap, board, sujets, mutate=m)
            except Exception as exc:
                port = {"exception": "%s: %s" % (type(exc).__name__, exc)}
            out["attack_mod_port" if m is None else ("attack_mod_port_%s" % m)] = port
        p, pe, pt = (out["attack_mod_port"], out["attack_mod_port_m_effet"],
                     out["attack_mod_port_m_trait"])
        out["verdict_port"] = {
            "total_egal_natif": p.get("total") == natif,
            # LA mesure de MON port : la part sous la cle d'aura, que seuls MES effets posent.
            "aura_attribuee": p.get("sous_cle_aura"),
            "aura_discrimine": bool((p.get("sous_cle_aura") or {}).get("guardsman")
                                    and not (p.get("sous_cle_aura") or {}).get("allie_temoin")),
            "mutant_effet_mord": pe.get("sous_cle_aura") != p.get("sous_cle_aura"),
            "mutant_trait_mord": pt.get("sous_cle_aura") != p.get("sous_cle_aura"),
        }
        return out
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--volet", choices=("possession", "summary"), required=True)
    ap.add_argument("--cible", default="eldarRanger")
    ap.add_argument("--allie", default="tauCrisis")
    a = ap.parse_args()
    rpc = _mkrpc()
    res = (volet_possession(rpc, a.cible) if a.volet == "possession"
           else volet_summary(rpc, a.allie, a.cible))
    print(json.dumps(res, indent=1, ensure_ascii=True))


if __name__ == "__main__":
    main()
