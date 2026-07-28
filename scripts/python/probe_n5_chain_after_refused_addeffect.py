#!/usr/bin/env python
"""probe_n5 -- CHUTE (ou non) de la chaine `&` DERRIERE un `AddEffect` REFUSE par le gate d'immunite.

CRITERE (binaire) : lorsque `IdunBattle.Operations.AddEffectOperation$$Execute` ABANDONNE (gate
`EntityIsImmuneToEffect`, cf. case-224), la SUITE de la chaine `op_BitwiseAnd` qui suit la feuille
`AddEffect` s'execute-t-elle ?

Ce probe LEVE le confond laisse ouvert par case-224 §5.2 : la mesure #112 y montrait la branche Chaos
d'`ExemplarOfHate` ENTIEREMENT absente sur `blackAbaddon` (trait `TerminatorArmour`), mais SANS avoir
pu garantir qu'un allie DarkAngels etait a portee -- or, sans attaquant elu, les trois feuilles qui
suivent le `Pinned` (`AddStatOverrideEffect` / `UseActiveAbility` / `RemoveEffect`) sont VIDES DE
TOUTE FACON. Absence de chaine et absence d'attaquant sont alors indiscernables.

MONTAGE DEBIAISE : `darkaHellblaster` (arme RANGED de portee 3) est place a d<=3 de la victime AU
BUILD (positions de deploiement CHOISIES, pas subies), donc `ExemplarOfHateAbility$$GetAttacker`
(`UnitsWhoCanAttack(UnitsFromFaction(Friends(caster), DarkAngels), target)`) a un candidat GARANTI.
L'observable qui DISCRIMINE devient alors :

    Pinned pose ?        -> teste le GATE d'immunite (deja porte, case-224)
    cible ENDOMMAGEE ?   -> teste la CHUTE DE CHAINE (l'attaque libre est la 2e feuille du `&`)

  * chaine qui TOMBE  : pas de Pinned ET pas de degat.
  * chaine qui TIENT  : pas de Pinned MAIS degat (+ groupes override/attaque/retrait).

Le contre-cas `blackPossession` (Chaos SANS le trait) donne Pinned + degat dans les deux lectures.

Troisieme montage (`ally`) : GENERALISATION -- le caster est ECARTE (d=2, arme melee) et l'attaquant
elu est l'ALLIE RANGED. Meme verdict, avec un porteur d'attaque DIFFERENT du caster.

⚠ CORRECTION #208 (2026-07-28) : sur `blackAbaddon`, le `Pinned` n'est PAS refuse -- il est POSE puis
rendu INERTE par `PinnedEffect$$CreateActiveCondition` (`probe_208_pinned_inactive.py` :
`decisionView includeInactive` publie 1065 avec `active=False`). L'observable « Pinned pose ? » lu
ici est en fait « Pinned CONTRIBUE ? » (un effet inactif n'applique rien, donc n'emet aucun groupe).
Le VERDICT DE CE PROBE est intact -- la chaine tient -- et il l'est meme a plus forte raison :
`AddEffectBehaviour$$Execute` jette la valeur de retour de l'operation dans TOUS les cas.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_n5_chain_after_refused_addeffect.py [immune|control|ally|all]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import copy
import json

import hexgeo
import probe_112_darkangels as PR
import rl_collect_batch as R

EXEMPLAR = 1140
PINNED = 1065
EOH_TARGET = 1293
TEMP_STAT_OVERRIDE = 1296

P_UNITS = ["darkaAsmodai", "darkaHellblaster"]
A_UNITS = ["blackAbaddon", "blackPossession"]
IMMUNE_VICTIM, CONTROL_VICTIM = "blackAbaddon", "blackPossession"

# Portee de l'arme ranged du Hellblaster (gameconfig `weapons[1].Range`) -- l'allie elu doit couvrir
# la distance a la cible depuis SA TUILE COURANTE (`UnitsWhoCanAttackTargetSelector$$Select`).
HELLBLASTER_RANGE = 3


def _build(sid, p_units, a_units, anchor=None, occupied=()):
    """Runner isole (seed BC + MC1_67 + rosters explicites).

    `anchor` = position (col,row) autour de laquelle DEPLOYER le camp joueur (couronne croissante).
    None -> placement de contact standard (`PR._contact_placement`). C'est le levier qui rend
    l'election d'attaquant DETERMINISTE au lieu de la subir.
    `occupied` = tuiles REELLEMENT prises par le camp adverse (mesurees par `enemy_layout`) : on
    n'exclut QUE celles-la, pas l'ensemble des spawn points -- sinon toute la couronne R1 de la
    victime est bannie et l'on ne peut PAS mettre le caster melee au contact."""
    seed = R._load_seed_bc()
    board_dump = R._load_board_dump(PR.BOARD)
    template, pool, _mow = R._normalize_and_extract_pool(sid, seed, PR.RANK, board_dump=board_dump)
    miss = [u for u in list(p_units) + list(a_units) if u not in pool]
    if miss:
        raise RuntimeError("hors pool rank %d : %s" % (PR.RANK, miss))
    bc = copy.deepcopy(template)
    R._patch_predefined_units(bc, list(a_units))
    if anchor is None:
        pos = PR._contact_placement(bc, len(p_units))
    else:
        pos = _ring_placement(bc, anchor, len(p_units), occupied)
    player_units = [{"unitId": u, "playerId": R.PLAYER_ID_HUMAN,
                     "col": pos[i][0], "row": pos[i][1]} for i, u in enumerate(p_units)]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": PR.SEED, "playerUnits": player_units}],
                  timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % (resp.get("error") or resp))
    PR._rids.append(rid)
    return rid


def _ring_placement(bc, anchor, n_units, occupied=()):
    """Tuiles de deploiement joueur les plus PROCHES d'`anchor`, hors tuiles OCCUPEES. Une tuile deja
    prise fait SILENCIEUSEMENT echouer le deploiement (cf. `PR._contact_placement`)."""
    taken = set(tuple(p) for p in occupied)
    board = bc.get("Board") or {}
    w, h = int(board.get("Width") or 0), int(board.get("Height") or 0)
    cands = [(c, r) for c, r in hexgeo.disk(anchor[0], anchor[1], 4)
             if (c, r) not in taken and 0 <= c < w and 0 <= r < h]
    cands.sort(key=lambda p: (hexgeo.distance(p, anchor), p))
    if len(cands) < n_units:
        raise RuntimeError("pas assez de tuiles libres autour de %s" % (anchor,))
    return cands[:n_units]


def enemy_layout(sid):
    """Build de RECONNAISSANCE : rend `{visualId: (col,row)}` du camp adverse. Il est place par la BC
    (spawn points), independamment des positions joueur -> a seed et BC egales, REPRODUCTIBLE dans le
    build suivant."""
    rid = _build(sid, P_UNITS, A_UNITS, anchor=None)
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        pos = PR.positions(dv)
        return {u.get("visualId"): pos[u["id"]] for u in (dv.get("units") or [])
                if not u.get("ctrl")}
    finally:
        PR.dispose(sid, rid)


def _groups(action):
    """Groupes d'operation emis par le cast (`kind == group`), dans l'ordre."""
    return [(e.get("group"), e.get("source"), e.get("entity"))
            for e in (action.get("events") or []) if e.get("kind") == "group"]


def run_case(sid, victim_visual, layout):
    anchor = layout[victim_visual]
    rid = _build(sid, P_UNITS, A_UNITS, anchor=anchor, occupied=layout.values())
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        bv = PR.units_by_visual(dv)
        if "darkaAsmodai" not in bv or victim_visual not in bv:
            print("  ABANDON: roster incomplet %s" % sorted(bv))
            return
        asmo, hell = bv["darkaAsmodai"]["id"], bv["darkaHellblaster"]["id"]
        tgt = bv[victim_visual]["id"]
        pos = PR.positions(dv)
        d_hell = hexgeo.distance(pos[hell], pos[tgt])
        d_asmo = hexgeo.distance(pos[asmo], pos[tgt])
        print("[%s] asmodai u%s @%s (d=%s) | hellblaster u%s @%s (d=%s, portee %s) | cible u%s @%s"
              % (victim_visual, asmo, pos[asmo], d_asmo, hell, pos[hell], d_hell,
                 HELLBLASTER_RANGE, tgt, pos[tgt]))
        if d_asmo > 1:
            # Le caster est LUI-MEME candidat (`Friends(caster, AllUnits + caster)`) : l'exiger au
            # CONTACT elimine tout doute residuel sur l'election (LoS/elevation d'un tireur eloigne).
            print("  ABANDON: caster non adjacent (d=%s) -> le confond n'est PAS leve" % d_asmo)
            return
        legal = PR.legal_from_here(sid, rid, asmo, EXEMPLAR)
        if tgt not in legal:
            print("  ABANDON: cible non legale depuis la position courante (legal=%s)" % legal)
            return
        hp0 = PR.hp_of(sid, rid)
        print("  PRE  effects cible :", PR.eff_names(dv, tgt))
        print("  PRE  hp cible      :", hp0.get(tgt))
        res = PR.cast(sid, rid, asmo, tgt, EXEMPLAR)
        print("  applyAction ok=%s mutated=%s" % (res.get("ok"), res.get("mutated")))
        for g in _groups(res):
            print("    GROUP g=%s source=%s entity=%s" % g)
        dv2 = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True})
        hp1 = PR.hp_of(sid, rid)
        print("  POST effects cible :", PR.eff_names(dv2, tgt))
        print("  POST effects hell  :", PR.eff_names(dv2, hell))
        print("  POST effects asmo  :", PR.eff_names(dv2, asmo))
        print("  hp delta           :", {k: (hp0[k][0], hp1[k][0]) for k in hp0
                                         if hp0[k][0] != hp1[k][0]})
        dmg = (hp0.get(tgt) or (0,))[0] != (hp1.get(tgt) or (0,))[0]
        pinned = PINNED in {e[0] for e in PR.eff_names(dv2, tgt)}
        print("  VERDICT: pinned=%s degat_cible=%s -> %s"
              % (pinned, dmg, "chaine TIENT" if dmg else "chaine TOMBE"))
    finally:
        PR.dispose(sid, rid)


def case_ally(sid, victim_visual, layout):
    """GENERALISATION du critere : le caster est ECARTE (d=2, arme melee) et l'attaquant elu est
    l'ALLIE RANGED (`darkaHellblaster`, portee 3). Si la chaine tombait derriere le `Pinned` refuse,
    ni l'override ni l'attaque de CET allie n'auraient lieu. On imprime aussi l'election du COLLAPSE
    de port (`_exemplar_of_hate_attackers`) pour la confronter a celle du natif."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.darkangels import (_exemplar_capped_attack_vars,
                                                    _exemplar_of_hate_attackers)
    from engine.runner.snapshot import load_state
    anchor = layout[victim_visual]
    blocked = set(layout.values()) | set(hexgeo.ring(anchor[0], anchor[1], 1))
    rid = _build(sid, P_UNITS, A_UNITS, anchor=anchor, occupied=blocked)
    try:
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True})
        bv = PR.units_by_visual(dv)
        asmo, hell = bv["darkaAsmodai"]["id"], bv["darkaHellblaster"]["id"]
        tgt = bv[victim_visual]["id"]
        pos = PR.positions(dv)
        print("[far %s] asmodai d=%s | hellblaster d=%s (portee %s)"
              % (victim_visual, hexgeo.distance(pos[asmo], pos[tgt]),
                 hexgeo.distance(pos[hell], pos[tgt]), HELLBLASTER_RANGE))
        ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 40)
        cs = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
        st = load_state(dv, ob, cs, board=Board(bg["tiles"], adjacency="native_sym"))
        cap, pct = _exemplar_capped_attack_vars(st, asmo)
        print("  PORT elit :", _exemplar_of_hate_attackers(st, asmo, tgt, cap, pct)[:1],
              "(asmodai=%s hellblaster=%s)" % (asmo, hell))
        if tgt not in PR.legal_from_here(sid, rid, asmo, EXEMPLAR):
            print("  ABANDON: cible non legale")
            return
        res = PR.cast(sid, rid, asmo, tgt, EXEMPLAR)
        srcs = [s for _g, s, _e in _groups(res)]
        print("  NATIF groupes :", srcs)
        print("  VERDICT: pinned=%s override=%s attaque=%s -> %s"
              % ("Pinned" in srcs, "TemporaryStatOverride" in srcs,
                 any(s and "NormalAttack" in s for s in srcs),
                 "chaine TIENT" if "TemporaryStatOverride" in srcs else "chaine TOMBE"))
    finally:
        PR.dispose(sid, rid)


def main():
    import sys
    sid = R._resolve_session()
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    try:
        layout = enemy_layout(sid)
        print("layout adverse:", layout)
        if only in ("immune", "all"):
            run_case(sid, IMMUNE_VICTIM, layout)
        if only in ("control", "all"):
            run_case(sid, CONTROL_VICTIM, layout)
        if only in ("ally", "all"):
            case_ally(sid, IMMUNE_VICTIM, layout)
    finally:
        for rid in list(PR._rids):
            PR.dispose(sid, rid)


if __name__ == "__main__":
    main()
