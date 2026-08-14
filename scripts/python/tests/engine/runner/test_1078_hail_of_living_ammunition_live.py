"""#1078 -- `HailOfLivingAmmunition_ExtraHits` (1042) CONFRONTE au natif.

Montage : cf. `scripts/python/probe_1078_hail_of_living_ammunition.py`, qui a produit les mesures
ci-dessous. Meme forme que le jumeau de famille `test_hungering_swarm_live.py` (#1018), a ceci pres
que le centre du voisinage est l'ATTAQUANT et non la cible, et que le gate est `IsRangedAttack` et
non `IsMeleeAttack` -- les deux ecarts sont LUS au decompile, pas deduits du voisin.

PORTEUR : `tyranNpc3Termagant`, npc, amene par `--explicit-stats tyranNpc3Termagant:45` (le summon
`tyranSmnTermagant` n'a AUCUN invocateur -- balayage exhaustif du gameconfig, cf. la docstring du
probe ; les cinq npc portent le passif eux-memes).

GROUND TRUTH LIVE (build `rnca9r7q6c`, board `MC1_67`, `ultraTitus` cible a armure 0) -- l'arme du
Termagant porte 2 coups a DISTANCE (Bio, r2) et 1 coup en MELEE (Physical) :

    phase   | voisins                        | cible | coups NATIFS | bonus
    --------+--------------------------------+-------+--------------+------
    armed   | 2x tyranNpc3Termagant, d(att)=1 | d = 2 |      4       |  +2
    far     | LES MEMES, d(att) = 2           | d = 2 |      2       |  +0
    melee   | 2x tyranNpc3Termagant, d(att)=1 | d = 1 |      1       |  +0
    kronos  | 2x tyranNpc3TermagantKronos,d=1 | d = 2 |      2       |  +0

Les trois contre-epreuves cassent des rails DIFFERENTS, et aucune ne se deduit d'une autre :
`far` casse la GEOMETRIE a roster constant ; `melee` casse la NATURE DU COUP a geometrie constante
(seule la cible bouge) ; `kronos` casse le FILTRE d'ID a geometrie ET nature constantes.

⚠ `kronos` est la phase qui a TROUVE un bug, et il n'etait pas dans ce port-ci : le natif rend +0
la ou le port rendait +2, parce que `IdunBattle.Entities.UnitExtensions$$GetUnitId` lit l'id de
CONFIG (composant d'identite +0x10) alors que le port comparait la `VisualId` (+0x20), seule des
deux qu'un canal live publie. Le `visualId` du Kronos (`GuildBoss1Npc2TyranTermagantKronos`) EST
dans la constante `unitIds`, son id de config ne l'est pas. Reparation dans le foyer partage
`entities/selectors/units.py::has_unit_id`.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.effects.loki.hail_of_living_ammunition import (
    HailOfLivingAmmunitionExtraHitsEffect, _unit_ids)

#: Ce que ce fichier LIT et qui peut le faire changer de verdict. Volontairement LARGE : le port
#: appelle l'arbre DSL (selecteurs + formules), le canal de coups, le foyer partage `has_unit_id`
#: et les DEUX constructeurs du board -- un declencheur reduit au seul module de l'effet serait un
#: FAUX VERT.
DECLENCHEUR = {
    "chemins": (
        # Le SEUL chemin propre est le probe de montage, qu'aucun import ne revele (le test le
        # CITE, il ne l'importe pas) : s'il change, ce que ce test croit monter n'est plus ce
        # qu'il monte. Le reste (effet, selecteurs, formules, `has_unit_id`) est DANS la cascade
        # derivee du foyer, donc le declarer serait la recopie que #531 proscrit.
        "scripts/python/probe_1078_hail_of_living_ammunition.py",
    ),
    # Pas de lecture du binaire ni de `data/symbols/**` : le montage passe par `rl_duel build`.
    "build": False,
    # Le montage exige un runner vivant, donc ce fichier ne peut PAS etre << toujours >> joue.
    "toujours": False,
    "raison": (
        "Ce fichier prouve que `HailOfLivingAmmunition_ExtraHits` (1042) rend le MEME nombre de "
        "coups que le natif sur quatre configurations, dont trois contrefactuelles independantes "
        "(geometrie / nature du coup / filtre d'id). Il lit le port de l'effet, l'arbre DSL, le "
        "foyer partage `has_unit_id` d'`entities/selectors/units.py` et le canal de coups -- tous "
        "dans la cascade derivee, d'ou `chemins` quasi vide."
    ),
}

ATTACKER = "tyranNpc3Termagant:45"
KRONOS = "tyranNpc3TermagantKronos:45"
TARGET = "ultraTitus"
ATT_POS = (3, 4)
NEAR = [(2, 4), (3, 3)]        # adjacents a l'ATTAQUANT, elevation 3 comme lui
FAR = [(1, 4), (1, 5)]         # d(attaquant) = 2
T_RANGED = (5, 4)              # d(attaquant) = 2 -> arme a distance (2 coups)
T_MELEE = (4, 3)               # d(attaquant) = 1 -> arme de melee (1 coup)
#: coups d'ARME du Termagant : `weapons = [1x Physical (melee), 2x Bio (r2)]` -- la BASE que
#: chaque phase partage, et elle DEPEND de la nature du coup.
WEAPON_HITS = {"armed": 2, "far": 2, "kronos": 2, "melee": 1}


def _phase_args(phase: str) -> list:
    """Les arguments `rl_duel build` d'une phase. UN SEUL montage, quatre configurations."""
    peer = KRONOS if phase == "kronos" else ATTACKER
    spots = FAR if phase == "far" else NEAR
    tpos = T_MELEE if phase == "melee" else T_RANGED
    args = ["--p-units", f"{ATTACKER},{peer},{peer}", "--explicit-stats", ATTACKER,
            "--a-units", TARGET, "--hp-target", "900000", "--armor-target", "0",
            "--crit", "0,0", "--block-target", "0,0",
            "--place", f"{ATTACKER}:{ATT_POS[0]},{ATT_POS[1]}"]
    if phase == "kronos":
        args += ["--explicit-stats", KRONOS]
    args += ["--place", f"{peer}:{spots[0][0]},{spots[0][1]}",
             "--place", f"{peer}:{spots[1][0]},{spots[1][1]}",
             "--a-place", f"{TARGET}:{tpos[0]},{tpos[1]}"]
    return args


@pytest.fixture(scope="module")
def hail_runner(rpc, build_runner):
    """Fabrique NOMMEE : `hail_runner(phase)` -> `{"rid", "dv"}`. Un runner par phase, monte a la
    demande et garde le temps du module."""
    made: dict = {}
    seeds = {"armed": "10781", "far": "10782", "melee": "10783", "kronos": "10784"}

    def _get(phase: str):
        if phase not in made:
            made[phase] = build_runner(seeds[phase], extra=_phase_args(phase))["rid"]
        rid = made[phase]
        dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        return {"rid": rid, "dv": dv}
    return _get


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def _roster(dv):
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    tgt = next((u for u in units if u.get("visualId") == TARGET), None)
    assert tgt is not None, f"cible absente du montage : {[u.get('visualId') for u in units]}"
    att = next((u for u in units if u.get("id") != tgt["id"] and _pos(u) == ATT_POS), None)
    assert att is not None, f"aucun attaquant sur {ATT_POS} -- montage rate"
    return units, att, tgt


def _amounts(res, tid, ability_id) -> list:
    """Les montants de degat portes a `tid` = UN PAR COUP (meme extraction que #1018)."""
    out = []
    for a in (res.get("actions") or []) if isinstance(res, dict) else []:
        for e in (a.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == ability_id:
                out.append(int(td["Amount"]))
    return out


def _native_hits(rpc, rid, dv) -> int:
    units, att, tgt = _roster(dv)
    norm = next((ab for ab in (att.get("abilities") or [])
                 if "NormalAttack" in str(ab.get("name") or "")), None)
    assert norm is not None, f"pas d'attaque normale sur u{att['id']}"
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": att["id"], "targetId": tgt["id"],
        "abilityType": norm["id"]}}, 90)
    return len(_amounts(res, tgt["id"], norm["id"]))


def _port_bonus(dv) -> int:
    """Le bonus que le PORT calcule, sur un board monte depuis le MEME `decisionView`.
    `is_melee` est DERIVE de la distance mesuree (d == 1 -> melee), jamais suppose."""
    units, att, tgt = _roster(dv)
    tp = _pos(tgt)
    board = {"att_id": att["id"], "tgt_id": tgt["id"],
             "attack_pos": ATT_POS, "t_pos": tp,
             "is_melee": hexgeo.distance(ATT_POS, tp) == 1,
             "pos_by_id": {u["id"]: _pos(u) for u in units},
             "team_by_id": {u["id"]: u.get("team") for u in units},
             "vid_by_id": {u["id"]: u.get("visualId") for u in units},
             "hp_by_id": {u["id"]: u.get("hp") for u in units},
             "hpmax_by_id": {u["id"]: u.get("hpMax") for u in units}}
    eff = HailOfLivingAmmunitionExtraHitsEffect("HailOfLivingAmmunition_ExtraHits")
    bonus = eff.create_effect_hits_bonus_for_attack(True, board)
    return 0 if bonus is None else int(bonus.value)


@pytest.mark.parametrize("phase,expected_bonus",
                         [("armed", 2), ("far", 0), ("melee", 0), ("kronos", 0)])
def test_hail_of_living_ammunition_hits_match_native(rpc, hail_runner, phase, expected_bonus):
    """Le nombre de coups NATIFS vaut `<coups d'arme de la phase> + bonus`, et le PORT rend le meme
    bonus. Les deux faces sont assertionnees SEPAREMENT : un port qui rendrait le bon total pour
    une mauvaise raison (bonus faux compense par une base fausse) ne passerait pas."""
    st = hail_runner(phase)
    port = _port_bonus(st["dv"])
    native = _native_hits(rpc, st["rid"], st["dv"])
    assert port == expected_bonus, f"[{phase}] le PORT rend +{port}, attendu +{expected_bonus}"
    assert native == WEAPON_HITS[phase] + expected_bonus, \
        (f"[{phase}] le NATIF rend {native} coup(s), attendu {WEAPON_HITS[phase]} (arme) + "
         f"{expected_bonus} (HailOfLivingAmmunition)")


def test_le_temoin_separe_les_deux_regimes():
    """Le montage SEPARE bien les regimes -- un jeu d'attendus ou toutes les phases predisent le
    MEME total natif << passerait >> sans rien prouver (accord en regime DEGENERE).

    C'est un cran sur les ATTENDUS, pas une seconde mesure : la mesure vit dans le test
    parametre ci-dessus, qui assertionne `4 / 2 / 1 / 2` coups natifs. Le rejouer ici est
    impossible -- l'attaque normale du tour est deja CONSOMMEE sur chacun de ces runners."""
    totaux = {ph: WEAPON_HITS[ph] + b
              for ph, b in (("armed", 2), ("far", 0), ("melee", 0), ("kronos", 0))}
    assert totaux["armed"] != totaux["far"], \
        f"phases DEGENEREES sur l'axe GEOMETRIE : {totaux}"
    assert totaux["armed"] != totaux["kronos"], \
        f"phases DEGENEREES sur l'axe FILTRE D'ID : {totaux}"
    assert totaux["armed"] != totaux["melee"], \
        f"phases DEGENEREES sur l'axe NATURE DU COUP : {totaux}"


def test_la_phase_kronos_reste_un_contrefactuel():
    """Elle ne l'est que tant que le `visualId` du Kronos est dans `unitIds` ET que son id de
    CONFIG n'y est pas -- c'est CE couple qui rend la phase discriminante. Si le gameconfig
    changeait l'un ou l'autre, il faut changer le MONTAGE, pas l'assertion."""
    import gameconfig as GC
    ids = _unit_ids()
    assert ids, "la constante `unitIds` est vide -> le montage ne prouve rien"
    assert set(ids) == {"tyranNpc3Termagant", "tyranSmnTermagant",
                        "GuildBoss1Npc1TyranTermagantLeviathan",
                        "GuildBoss1Npc2TyranTermagantKronos",
                        "GuildBoss1Npc3TyranTermagantGorgon"}, \
        f"la constante `unitIds` a change : {ids}"
    kronos = GC.unit("tyranNpc3TermagantKronos") or {}
    assert kronos.get("visualId") == "GuildBoss1Npc2TyranTermagantKronos", \
        "le `visualId` du Kronos a change -> la phase ne mesure plus le meme ecart"
    assert "tyranNpc3TermagantKronos" not in set(ids), \
        "l'id de CONFIG du Kronos est entre dans `unitIds` -> la phase n'est plus un contrefactuel"
    assert kronos.get("visualId") in set(ids), \
        "le `visualId` du Kronos est sorti d'`unitIds` -> les deux lectures ne divergent plus"
