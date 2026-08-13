"""#1018 -- `HungeringSwarm_ExtraHits` (1041) CONFRONTE au natif.

Montage : cf. `scripts/python/probe_1018_hungering_swarm.py`, qui a produit les mesures ci-dessous.
La FIXTURE `swarm_runner` est parametree par la phase, donc reutilisable telle quelle par toute
tranche qui a besoin d'Hormagaunts places autour d'une cible (c'est le meme montage qui sert le
residu `AdrenalGlands`, cf. `docs/rl/case-1018-hungering-swarm.md`).

GROUND TRUTH LIVE (build `rnca9r7q6c`, board `MC1_67`, seed 777, `ultraTitus` cible a armure 0) --
l'arme de `tyranNpc1Hormagaunt` porte 2 coups :

    phase    | geometrie des 2 pairs | unitId des pairs                    | coups NATIFS
    ---------+-----------------------+-------------------------------------+-------------
    armed    | ADJACENTS a la cible  | tyranNpc1Hormagaunt (dans unitIds)  |      4
    far      | d(cible) = 3          | tyranNpc1Hormagaunt (dans unitIds)  |      2
    kronos   | ADJACENTS a la cible  | ...HormagauntKronos (HORS unitIds)  |      2

`far` et `kronos` sont deux contre-epreuves INDEPENDANTES et elles ne rendent PAS le meme nombre
pour la meme raison : `far` casse la GEOMETRIE a roster constant, `kronos` casse le FILTRE
`UnitsWithIds` a GEOMETRIE constante (memes traits, meme nom d'affichage << Hormagaunt >>, memes
deux passifs, memes tuiles). Sans la seconde, << +2 coups >> serait aussi bien explique par
<< 2 allies adjacents, quels qu'ils soient >>.
"""
from __future__ import annotations

import json

import pytest

import hexgeo
from engine.entities.effects.loki.hungering_swarm import (HungeringSwarmExtraHitsEffect,
                                                          _unit_ids)

#: Ce que ce fichier LIT et qui peut le faire changer de verdict. Volontairement LARGE : le port
#: appelle l'arbre DSL (selecteurs + formules), le canal de coups, et les DEUX constructeurs du
#: board -- un declencheur reduit au seul module de l'effet serait un FAUX VERT.
DECLENCHEUR = {
    "chemins": (
        # `probe_486r15 --proposer` rend une fermeture de 647 modules ENTIEREMENT contenue dans la
        # cascade DERIVEE par le foyer (648 chemins) : il n'y a donc RIEN a declarer ici, et le
        # declarer serait une recopie que #531 proscrit. Le SEUL chemin propre est le probe de
        # montage, qu'aucun import ne revele (le test le cite, il ne l'importe pas).
        "scripts/python/probe_1018_hungering_swarm.py",
    ),
    # Pas de lecture du binaire ni de `data/symbols/**` : le montage passe par `rl_duel build`
    # (qui lit `data/seed-bc.json` et `data/boards/**` pour SON compte, hors fermeture de ce test).
    "build": False,
    # Le montage exige un runner vivant, donc ce fichier ne peut PAS etre << toujours >> joue.
    "toujours": False,
    "raison": (
        "Ce fichier prouve que `HungeringSwarm_ExtraHits` (1041) rend le MEME nombre de coups que "
        "le natif sur trois geometries, dont deux contrefactuelles. Il lit le port de l'effet, "
        "l'arbre DSL (selecteurs + formules), la base `_is_alive` de `engine/dsl/base.py` et les "
        "DEUX constructeurs du board de coups -- tous dans la cascade derivee, d'ou `chemins` "
        "quasi vide. Le probe de montage y est ajoute a la main parce qu'il est CITE et non "
        "importe : s'il change, ce que ce test croit monter n'est plus ce qu'il monte."
    ),
}

ATTACKER = "tyranNpc1Hormagaunt"
KRONOS = "tyranNpc1HormagauntKronos"
TARGET = "ultraTitus"
T_POS = (3, 4)
ATT_POS = (2, 4)
NEAR = [(4, 4), (3, 5)]
FAR = [(4, 1), (2, 1)]
#: coups d'ARME de l'Hormagaunt (`weapons: 2x Physical`) -- la BASE que les trois phases partagent.
WEAPON_HITS = 2


def _phase_args(phase: str) -> list:
    """Les arguments `rl_duel build` d'une phase. UN SEUL montage, trois geometries/rosters."""
    peer = KRONOS if phase == "kronos" else ATTACKER
    spots = FAR if phase == "far" else NEAR
    args = ["--p-units", f"{ATTACKER},{peer},{peer}", "--explicit-stats", ATTACKER,
            "--a-units", TARGET, "--hp-target", "900000", "--armor-target", "0",
            "--crit", "0,0", "--block-target", "0,0",
            "--place", f"{ATTACKER}:{ATT_POS[0]},{ATT_POS[1]}"]
    if phase == "kronos":
        args += ["--explicit-stats", KRONOS]
    args += ["--place", f"{peer}:{spots[0][0]},{spots[0][1]}",
             "--place", f"{peer}:{spots[1][0]},{spots[1][1]}",
             "--a-place", f"{TARGET}:{T_POS[0]},{T_POS[1]}"]
    return args


@pytest.fixture(scope="module")
def swarm_runner(rpc, build_runner):
    """Fabrique NOMMEE : `swarm_runner(phase)` -> `{"rid", "dv"}`. Un runner par phase, monte a la
    demande et garde le temps du module (les trois phases sont jouees dans le meme fichier)."""
    made: dict = {}
    #: `build_runner(seed, ...)` attend un SEED (entier) -- un seed distinct par phase evite qu'un
    #: state-file partage fasse retomber deux phases sur le meme runner.
    seeds = {"armed": "10181", "far": "10182", "kronos": "10183"}

    def _get(phase: str):
        if phase not in made:
            rid = build_runner(seeds[phase], extra=_phase_args(phase))["rid"]
            made[phase] = rid
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
    att = next((u for u in units if u.get("visualId") == ATTACKER
                and hexgeo.distance(_pos(u), _pos(tgt)) == 1), None)
    assert att is not None, "aucun attaquant `tyranNpc1Hormagaunt` adjacent a la cible"
    return units, att, tgt


def _amounts(res, tid, ability_id) -> list:
    """Les montants de degat portes a `tid` = UN PAR COUP (meme extraction que le test #204)."""
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
    """Le bonus que le PORT calcule, sur un board monte depuis le MEME `decisionView`."""
    units, att, tgt = _roster(dv)
    board = {"att_id": att["id"], "tgt_id": tgt["id"],
             "attack_pos": _pos(att), "t_pos": _pos(tgt), "is_melee": True,
             "pos_by_id": {u["id"]: _pos(u) for u in units},
             "team_by_id": {u["id"]: u.get("team") for u in units},
             "vid_by_id": {u["id"]: u.get("visualId") for u in units},
             "hp_by_id": {u["id"]: u.get("hp") for u in units},
             "hpmax_by_id": {u["id"]: u.get("hpMax") for u in units}}
    eff = HungeringSwarmExtraHitsEffect("HungeringSwarm_ExtraHits")
    bonus = eff.create_effect_hits_bonus_for_attack(True, board)
    return 0 if bonus is None else int(bonus.value)


@pytest.mark.parametrize("phase,expected_bonus", [("armed", 2), ("far", 0), ("kronos", 0)])
def test_hungering_swarm_hits_match_native(rpc, swarm_runner, phase, expected_bonus):
    """Le nombre de coups NATIFS vaut `2 (arme) + bonus`, et le PORT rend le meme bonus.

    Les deux faces sont assertionnees SEPAREMENT : un port qui rendrait le bon total pour une
    mauvaise raison (bonus faux compense par une base fausse) ne passerait pas."""
    st = swarm_runner(phase)
    port = _port_bonus(st["dv"])
    native = _native_hits(rpc, st["rid"], st["dv"])
    assert port == expected_bonus, \
        f"[{phase}] le PORT rend +{port}, attendu +{expected_bonus}"
    assert native == WEAPON_HITS + expected_bonus, \
        (f"[{phase}] le NATIF rend {native} coup(s), attendu "
         f"{WEAPON_HITS} (arme) + {expected_bonus} (HungeringSwarm)")


def test_unit_ids_constant_excludes_the_kronos_variant():
    """La constante `unitIds` ne couvre PAS les variantes -- c'est ce que la phase `kronos` mesure,
    et c'est LU : `idun.shared.UnitNamingConventions$$GetUnitIdWithoutRarity` est
    `configUnitId.Split(':')[0]`, il ne normalise aucun suffixe de variante.

    Ce test garde le GATE du contrefactuel : si un jour la constante listait les Kronos, la phase
    `kronos` cesserait d'etre discriminante et rendrait 4 -- il faut alors changer le montage, pas
    l'assertion."""
    ids = _unit_ids()
    assert ids, "la constante `unitIds` de HungeringSwarm est vide -> le montage ne prouve rien"
    assert set(ids) == {"tyranNpc1Hormagaunt", "tyranNpc2RipperSwarm",
                        "tyranSmnHormagaunt", "tyranSmnRipperSwarm"}, \
        f"la constante `unitIds` a change : {ids}"
    assert KRONOS not in ids and "GuildBoss1Npc5TyranHormagauntKronos" not in ids, \
        "le Kronos est entre dans `unitIds` -> la phase `kronos` n'est plus un contrefactuel"
