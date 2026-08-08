"""#572 -- `UnbreakableDuty` (1061, `templAncient` << Ancient Thoread >>) : NATIF vs PORT.

L'ability etait un NO-OP SILENCIEUX (absente d'`ABILITY_CLASSES`) : 0 effet, 0 soin, 0 degat,
aucune erreur.

LE CRITERE, ENONCE AVANT LE MONTAGE
------------------------------------
Le cast a DEUX regimes, separes par UN gate, et chacun repond a une question BINAIRE distincte :

  * gate FERME (`--step ferme`) -- moins de 2 allies morts portant a la fois `Imperial` et `Hero`.
    Le cast ne doit poser QUE l'aura 1097, et RIEN d'autre : ni 1251, ni 1256, ni soin, ni attaque.
    C'est le bras qui rend le gate ATTRIBUABLE : sans lui, un port qui poserait tout
    inconditionnellement passerait le bras ouvert.
  * gate OUVERT (`--step ouvert`) -- exactement 2 allies `Imperial`+`Hero` TUES avant le cast.
    Les cinq mecaniques doivent mordre : 1097 + 1251 + 1256 + le +extraHp de PV COURANTS + une
    attaque NORMALE gratuite sur un ennemi adjacent.

Le troisieme pas (`--step aura`) confronte l'OBSERVABLE de l'aura, qui n'est PAS la presence de
l'effet mais le DEGAT : un ami a <= `range` hexes du porteur doit encaisser `-dmgReductionPct`%.
Il porte son CONTRE-MODELE (le meme coup, port avec l'instance 1097 consommee) -- sans lui, une
concordance ne serait pas attribuable a la reduction.

⚠ Chaque pas monte SON runner et le dispose. ASCII only.

USAGE
    python probe_572_unbreakable_duty.py --step ferme
    python probe_572_unbreakable_duty.py --step ouvert
    python probe_572_unbreakable_duty.py --step aura
    python probe_572_unbreakable_duty.py --step all
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
import rl_collect_batch as R                                         # noqa: E402
import probe_112_darkangels as PR                                    # noqa: E402
import probe_462_r4b_r1_terminator_commanded_attack as R1            # noqa: E402
from rl_collect_batch import _resolve_session                        # noqa: E402

UNBREAKABLE_DUTY = 1061
UD_DAMAGE_REDUCTION = 1097
UD_HEALTH = 1251
UD_DAMAGE = 1256
UD_FAMILY = (UD_DAMAGE_REDUCTION, UD_HEALTH, UD_DAMAGE)

CASTER = "templAncient"          # porteur de 1061 -- HERO, AU POOL (croise le 2026-08-08)
ALLY_NEAR = "templAggressor"     # ami a distance 1 du porteur -> beneficiaire de l'aura
SACRIFICE_A = "bloodIntercessor"  # Imperial + Hero, patche a 1 PV
SACRIFICE_B = "ultraApothecary"   # Imperial + Hero, patche a 1 PV
FOE = "blackPossession"          # l'ennemi adjacent : cible de l'attaque libre, gros sac a PV
KILLER = "blackTerminator"       # l'executeur du 1er sacrifie (adjacent a lui)
KILLER_B = "worldJakhal"         # l'executeur du 2e (une unite n'agit qu'une fois par tour)


# ------------------------------------------------------------------------------------------------
# lecture des DEUX cotes, meme forme
# ------------------------------------------------------------------------------------------------
def live_family(dv, uid):
    """{effectType: remaining} des effets de la famille `UnbreakableDuty` portes par `uid`."""
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return {int(e.get("effectType") or -1): e.get("remaining")
            for e in ((u or {}).get("effects") or [])
            if int(e.get("effectType") or -1) in UD_FAMILY}


def port_family(st, uid):
    """Le pendant OFFLINE, meme forme : `EffectsState.by_unit` filtre sur la meme famille."""
    eff = getattr(st, "effects", None)
    if eff is None:
        return {}
    return {int(e.effect_type): e.remaining_turns
            for e in eff.by_unit.get(int(uid), [])
            if (not e.consumed) and e.effect_type is not None
            and int(e.effect_type) in UD_FAMILY}


def live_hp(dv, uid):
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), None)
    return None if u is None else (u.get("hp"), u.get("hpMax"))


def expected_vars(st, caster_id):
    """`extraHp` / `extraDmg` / `dmgReductionPct` re-derives de la MEME source que le port."""
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.components import StatsComponent
    e = st.get_entity(int(caster_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = sc.ctx if sc is not None else None
    lvl = getattr(ctx, "active_ability_level", None)
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
    return {"level": lvl, "mult": mult,
            "extraHp": int(ability_var("UnbreakableDuty", "extraHp", lvl, multiplier_pct=mult) or 0),
            "extraDmg": int(ability_var("UnbreakableDuty", "extraDmg", lvl, multiplier_pct=mult) or 0),
            "dmgReductionPct": int(ability_var("UnbreakableDuty", "dmgReductionPct", lvl,
                                               multiplier_pct=mult) or 0),
            "range": int(ability_var("UnbreakableDuty", "range", is_constant=True) or 0)}


# ------------------------------------------------------------------------------------------------
# montage
# ------------------------------------------------------------------------------------------------
def _board_of(bc):
    from board import Board
    return Board(bc)


def _open_tile(board, taken=()):
    """Une tuile jouable a 6 voisins jouables : la seule ou l'on peut poser AUTOUR du porteur un
    ami (beneficiaire) ET un ennemi (cible de l'attaque libre) sans subir la geometrie de spawn."""
    for (c, r), _t in sorted(board.playable_tiles().items()):
        if (c, r) in taken:
            continue
        if len(board.neighbors(c, r)) == 6:
            return (c, r)
    raise RuntimeError("aucune tuile jouable a 6 voisins sur %s" % PR.BOARD)


def _build(sid, p_units, p_pos, a_units, a_pos, unit_patch=None):
    """Runner isole : seed BC + board `MC1_67` + rosters explicites + placement EXACT DES DEUX
    CAMPS (meme geste que `probe_462_r4b_r1_r1_r1_r1_b_bond_range._build`, cf. #477-r5)."""
    seed = R._load_seed_bc()
    board_dump = R._load_board_dump(PR.BOARD)
    template, pool, _mow = R._normalize_and_extract_pool(sid, seed, PR.RANK, board_dump=board_dump)
    miss = [u for u in list(p_units) + list(a_units) if u not in pool]
    if miss:
        raise RuntimeError("hors pool rank %d : %s" % (PR.RANK, miss))
    bc = copy.deepcopy(template)
    R._patch_predefined_units(bc, [])              # tout le camp adverse est pose a la main
    for vis, fields in (unit_patch or {}).items():
        touched = [u for u in bc.get("Units", []) if u.get("VisualId") == vis]
        if not touched:
            raise RuntimeError("unit_patch: VisualId %r absent de BC.Units" % vis)
        for u in touched:
            u.update(fields)
    player_units = [{"unitId": u, "playerId": R.PLAYER_ID_HUMAN,
                     "col": int(p_pos[i][0]), "row": int(p_pos[i][1])}
                    for i, u in enumerate(p_units)]
    player_units += [{"unitId": u, "playerId": R.PLAYER_ID_AI,
                      "col": int(a_pos[i][0]), "row": int(a_pos[i][1])}
                     for i, u in enumerate(a_units)]
    resp = R._rpc(sid, "initAndStart",
                  [{"configJson": json.dumps(bc), "seed": PR.SEED,
                    "playerUnits": player_units}], timeout=60)
    rid = (resp.get("result") or {}).get("runnerId")
    if rid is None:
        raise RuntimeError("initAndStart KO: %s" % (resp.get("error") or resp))
    PR._rids.append(rid)
    return rid, bc


def build_montage(sid, with_sacrifices=True, ally_far=False):
    """Monte le banc et rend `{sid, rid, caster, ally, foe, killer, sacs[]}`.

    GEOMETRIE (choisie, jamais subie) : le porteur occupe une tuile a 6 voisins jouables ; l'ami
    beneficiaire et l'ennemi-cible occupent deux de ses voisins ; les deux sacrifices et leur
    executeur sont poses A L'ECART (>= 3 hexes du porteur) pour que leur mise a mort ne touche ni
    le porteur ni l'ami.

    `ally_far = True` deplace l'ami A `range + 1` hexes du porteur -- le bras de CONTROLE de l'aura
    (le meme banc a une tuile pres : hors de portee, il ne doit RIEN recevoir).
    """
    seed = R._load_seed_bc()
    board_dump = R._load_board_dump(PR.BOARD)
    template, _pool, _mow = R._normalize_and_extract_pool(sid, seed, PR.RANK, board_dump=board_dump)
    board = _board_of(template)
    cpos = _open_tile(board)
    ring = [tuple(p) for p in board.neighbors(*cpos)]
    if ally_far:
        # BRAS DE CONTROLE : l'ami est HORS de `range` du porteur (d = 3 > 2) et l'ennemi est
        # adjacent A LUI (donc loin du porteur) -- le MEME geste, a deux tuiles pres.
        apos = _at_distance(board, cpos, 3, taken={cpos})
        foe_pos = next((p for p in (tuple(q) for q in board.neighbors(*apos))
                        if board.is_playable(*p) and p != cpos
                        and hexgeo.distance(p, cpos) >= 3), None)
        if foe_pos is None:
            raise RuntimeError("aucune tuile pour l'ennemi hors portee du porteur")
    else:
        # BRAS A PORTEE : l'ennemi est adjacent au PORTEUR (cible de l'attaque libre) ET a l'AMI
        # (pour qu'il puisse le frapper en melee au pas `aura`).
        foe_pos = ring[0]
        apos = next((p for p in ring[1:] if hexgeo.distance(p, foe_pos) == 1), None)
        if apos is None:
            raise RuntimeError("aucune tuile de l'anneau adjacente a l'ennemi")
    taken = {cpos, foe_pos, apos}
    # Le camp du sacrifice, a l'ECART (>= 4 hexes du porteur, donc HORS de l'aura et hors du champ
    # de l'attaque libre) : chaque sacrifie a SON executeur adjacent -- une unite n'agit qu'une fois
    # par tour, donc un executeur unique ne pourrait pas en tuer deux.
    sac_a = _at_distance(board, cpos, 4, taken=taken)
    taken.add(sac_a)
    kill_a = _adjacent_free(board, sac_a, taken)
    taken.add(kill_a)
    sac_b = _at_distance(board, cpos, 5, taken=taken)
    taken.add(sac_b)
    kill_b = _adjacent_free(board, sac_b, taken)
    taken.add(kill_b)

    p_units = [CASTER, ALLY_NEAR]
    p_pos = [cpos, apos]
    if with_sacrifices:
        p_units += [SACRIFICE_A, SACRIFICE_B]
        p_pos += [sac_a, sac_b]
    a_units, a_pos = [FOE], [foe_pos]
    if with_sacrifices:
        a_units += [KILLER, KILLER_B]
        a_pos += [kill_a, kill_b]
    patch = {FOE: {"Health": 400000, "RemainingHealth": 400000}}
    if with_sacrifices:
        patch[SACRIFICE_A] = {"Health": 1, "RemainingHealth": 1}
        patch[SACRIFICE_B] = {"Health": 1, "RemainingHealth": 1}
    rid, _bc = _build(sid, p_units, p_pos, a_units, a_pos, unit_patch=patch)
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    bv = PR.units_by_visual(dv)
    for need in p_units + a_units:
        if need not in bv:
            PR.dispose(sid, rid)
            raise RuntimeError("roster incomplet : manque %s (%s)" % (need, sorted(bv)))
    ctx = {"sid": sid, "rid": rid,
           "caster": int(bv[CASTER]["id"]), "ally": int(bv[ALLY_NEAR]["id"]),
           "foe": int(bv[FOE]["id"]),
           "killers": [int(bv[KILLER]["id"]), int(bv[KILLER_B]["id"])] if with_sacrifices else [],
           "sacs": [int(bv[SACRIFICE_A]["id"]), int(bv[SACRIFICE_B]["id"])] if with_sacrifices else [],
           "pos": PR.positions(dv)}
    ctx["d_ally"] = hexgeo.distance(ctx["pos"][ctx["caster"]], ctx["pos"][ctx["ally"]])
    ctx["d_foe"] = hexgeo.distance(ctx["pos"][ctx["caster"]], ctx["pos"][ctx["foe"]])
    return ctx


def _at_distance(board, origin, dist, taken=()):
    for (c, r) in sorted(board.playable_tiles()):
        if (c, r) in taken:
            continue
        if hexgeo.distance(origin, (c, r)) == dist and len(board.neighbors(c, r)) >= 3:
            return (c, r)
    raise RuntimeError("aucune tuile jouable a distance %d de %s" % (dist, origin))


def _adjacent_free(board, origin, taken, also_adjacent_to=None):
    for p in board.neighbors(*origin):
        p = tuple(p)
        if p in taken or not board.is_playable(*p):
            continue
        if also_adjacent_to is not None and hexgeo.distance(p, also_adjacent_to) != 1:
            continue
        return p
    raise RuntimeError("aucune tuile libre adjacente a %s" % (origin,))


def _kill(sid, rid, victim_id, victim_owner, tries=6, verbose=True):
    """Tue `victim_id` avec les unites du camp ADVERSE, sans `endturn` (meme recette que
    `probe_462_r4b_r1_r1_r1_r1_bond_removal._kill_no_endturn` : le `endturn` ferait passer le tour,
    donc declencher des vecteurs qu'on ne veut pas dans l'etat de depart).

    Essaie TOUTES les abilities non-passives de chaque unite adverse, l'attaque normale D'ABORD --
    une ability speciale peut avoir un masque de ciblage qui exclut la victime."""
    for _ in range(tries):
        d = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
        v = next((u for u in (d.get("units") or []) if int(u["id"]) == int(victim_id)), None)
        if v is None or not v.get("alive"):
            return True
        fired = False
        for u in (d.get("units") or []):
            if not u.get("alive") or u.get("owner") == victim_owner:
                continue
            abils = [a for a in (u.get("abilities") or []) if a.get("kind") != "passive"]
            abils.sort(key=lambda a: 0 if a.get("kind") == "normal" else 1)
            for a in abils:
                aid = a.get("id")
                if aid is None:
                    continue
                legal = PR.legal_from_here(sid, rid, int(u["id"]), aid)
                if int(victim_id) not in legal:
                    if verbose:
                        print("   [kill] u%s ability %s (%s) ne peut pas viser u%s (legal=%s)"
                              % (u["id"], aid, a.get("kind"), victim_id, legal))
                    continue
                res = PR.act(sid, rid, {"kind": "ability", "casterId": int(u["id"]),
                                        "targetId": int(victim_id), "abilityType": aid})
                if verbose:
                    print("   [kill] u%s -> u%s via %s : ok=%s"
                          % (u["id"], victim_id, aid, res.get("ok")))
                fired = fired or bool(res.get("ok"))
                break
        if not fired:
            break
    d = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    v = next((u for u in (d.get("units") or []) if int(u["id"]) == int(victim_id)), None)
    return (v is None) or (not v.get("alive"))


def _owner_of(dv, uid):
    u = next((x for x in (dv.get("units") or []) if int(x["id"]) == int(uid)), None)
    return None if u is None else u.get("owner")


def _my_player_ids(dv):
    """`(mon playerId, celui de l'adversaire)` -- l'equipe controlee porte `ctrl`."""
    mine = next((u.get("team") for u in (dv.get("units") or []) if u.get("ctrl")), None)
    return (3, 4) if mine == 1 else (4, 3)


def _pass_turn_to(sid, rid, player_id, tries=4):
    """`endturn` jusqu'a ce que `currentPlayer == player_id`.

    ⚠ NECESSAIRE et non evitable : `legal_from_here` rend une liste VIDE pour toute unite dont ce
    n'est pas le tour -- mesure du 2026-08-08, les trois unites adverses rendaient `legal=[]` sur
    LEUR attaque normale. Faire mourir un ALLIE du porteur exige donc de rendre la main a l'IA."""
    dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    for _ in range(tries):
        if dv.get("currentPlayer") == player_id:
            return dv
        PR.act(sid, rid, {"kind": "endturn"})
        dv = PR.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)
    raise RuntimeError("le tour n'a pas bascule vers %s (currentPlayer=%s)"
                       % (player_id, dv.get("currentPlayer")))


# ------------------------------------------------------------------------------------------------
# le cast, les DEUX faces, sur le MEME etat de depart
# ------------------------------------------------------------------------------------------------
def measure_cast(sid, gate_open):
    from engine.runner.abilities.handler import ABILITY_CLASSES, AbilityHandler
    from engine.runner.messages import ActiveAbilityMessage

    print("1061 dans `ABILITY_CLASSES` : %s" % (UNBREAKABLE_DUTY in ABILITY_CLASSES))
    ctx = build_montage(sid, with_sacrifices=gate_open)
    caster, ally, foe = ctx["caster"], ctx["ally"], ctx["foe"]
    try:
        print("placement : porteur %s  ami %s (d=%d)  ennemi %s (d=%d)"
              % (ctx["pos"][caster], ctx["pos"][ally], ctx["d_ally"],
                 ctx["pos"][foe], ctx["d_foe"]))
        dv = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                          "allAbilities": True}, 90)
        killed = []
        if gate_open:
            owner = _owner_of(dv, caster)
            mine, theirs = _my_player_ids(dv)
            _pass_turn_to(sid, ctx["rid"], theirs)        # l'IA seule peut frapper MES unites
            for sac in ctx["sacs"]:
                ok = _kill(sid, ctx["rid"], sac, owner)
                killed.append((sac, ok))
            print("sacrifices : %s" % (killed,))
            if not all(ok for _s, ok in killed):
                raise RuntimeError("montage : les deux sacrifices n'ont pas ete tues (%s)" % killed)
            _pass_turn_to(sid, ctx["rid"], mine)          # la main revient au porteur
        # ETAT DE DEPART COMMUN, capture juste AVANT le cast.
        board, dv0, ob0, cs0 = R1._snapshot(sid, ctx["rid"])
        st = R1._seeded_state(sid, ctx["rid"], board, dv0, ob0, cs0)
        hp0 = live_hp(dv0, caster)
        foe_hp0 = live_hp(dv0, foe)
        # ---- face NATIVE : le porteur se cible LUI-MEME (selfCast, TargetIsFriendly) ----
        legal = PR.legal_from_here(sid, ctx["rid"], caster, UNBREAKABLE_DUTY)
        print("cibles legales du cast : %s (porteur=%s ami=%s)" % (legal, caster, ally))
        tgt = caster if caster in legal else (ally if ally in legal else None)
        if tgt is None:
            raise RuntimeError("montage : aucune cible legale pour 1061 (%s)" % legal)
        res_live = PR.cast(sid, ctx["rid"], caster, tgt, UNBREAKABLE_DUTY)
        if not res_live.get("ok"):
            raise RuntimeError("cast 1061 refuse : %s" % str(res_live)[:300])
        dv1 = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                           "allAbilities": True}, 90)
        nat_caster = live_family(dv1, caster)
        nat_ally = live_family(dv1, ally)
        nat_hp1 = live_hp(dv1, caster)
        nat_foe_hp1 = live_hp(dv1, foe)
        nat_free_dmg = (None if (foe_hp0[0] is None or nat_foe_hp1[0] is None)
                        else foe_hp0[0] - nat_foe_hp1[0])
        print("[NATIF] porteur effets %s  hp %s -> %s" % (sorted(nat_caster.items()), hp0, nat_hp1))
        print("[NATIF] ami     effets %s" % (sorted(nat_ally.items()),))
        print("[NATIF] degat de l'attaque libre sur l'ennemi : %s" % nat_free_dmg)
    finally:
        PR.dispose(sid, ctx["rid"])

    # ---- face PORT, sur l'etat capture AVANT le cast : le CHEMIN REEL (le visiteur de message) --
    p_hp0 = R1._hp(st, caster)
    p_foe0 = R1._hp(st, foe)
    h = AbilityHandler(st)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(
        caster_id=int(caster), target_id=int(tgt), ability_type=UNBREAKABLE_DUTY))
    res = h.last or {}
    port_caster, port_ally = port_family(st, caster), port_family(st, ally)
    p_hp1 = R1._hp(st, caster)
    p_foe1 = R1._hp(st, foe)
    port_free_dmg = None if (p_foe0 is None or p_foe1 is None) else p_foe0 - p_foe1
    exp = expected_vars(st, caster)
    print("[PORT ] retour %s" % ({k: res.get(k) for k in ("ability", "gate_passed", "ported", "dsl")},))
    print("[PORT ] porteur effets %s  hp %s -> %s" % (sorted(port_caster.items()), p_hp0, p_hp1))
    print("[PORT ] ami     effets %s" % (sorted(port_ally.items()),))
    print("[PORT ] degat de l'attaque libre sur l'ennemi : %s" % port_free_dmg)
    print("[PORT ] variables attendues : %s" % (exp,))

    print("")
    print("=" * 96)
    rc = 0
    label = "OUVERT" if gate_open else "FERME"
    attendu = set(UD_FAMILY) if gate_open else {UD_DAMAGE_REDUCTION}
    for lbl, got in (("NATIF", nat_caster), ("PORT ", port_caster)):
        if set(got) != attendu:
            print("  ROUGE [%s] gate %s : effets du porteur = %s, attendu %s"
                  % (lbl, label, sorted(got), sorted(attendu)))
            rc = 1
    # L'aura est portee par le CASTER, jamais materialisee sur l'ami (le natif cible `Owner@+0x30`).
    for lbl, got in (("NATIF", nat_ally), ("PORT ", port_ally)):
        if got:
            print("  ROUGE [%s] l'ami porte des effets de la famille : %s -- l'aura doit rester "
                  "sur le porteur" % (lbl, sorted(got)))
            rc = 1
    # Le SOIN (`ChangeStat` mode Add sur la stat FILL-UP) -- le seul canal ou le port pouvait
    # ecrire dans `ctx.stats` au lieu des PV et perdre le soin SILENCIEUSEMENT.
    nat_gain = None if (hp0[0] is None or nat_hp1[0] is None) else nat_hp1[0] - hp0[0]
    port_gain = None if (p_hp0 is None or p_hp1 is None) else p_hp1 - p_hp0
    attendu_gain = exp["extraHp"] if gate_open else 0
    print("  gain de PV COURANTS : natif=%s port=%s (attendu %s)"
          % (nat_gain, port_gain, attendu_gain))
    if nat_gain != attendu_gain or port_gain != attendu_gain:
        print("  ROUGE : le +extraHp de PV courants ne concorde pas")
        rc = 1
    # L'ATTAQUE LIBRE
    print("  degat de l'attaque libre : natif=%s port=%s" % (nat_free_dmg, port_free_dmg))
    if gate_open:
        if not nat_free_dmg or not port_free_dmg:
            print("  ROUGE : l'attaque libre n'a pas eu lieu d'un des deux cotes")
            rc = 1
        elif int(nat_free_dmg) != int(port_free_dmg):
            print("  ROUGE : degat de l'attaque libre natif=%s port=%s (ecart %d)"
                  % (nat_free_dmg, port_free_dmg, nat_free_dmg - port_free_dmg))
            rc = 1
    else:
        if nat_free_dmg or port_free_dmg:
            print("  ROUGE : une attaque a eu lieu alors que le gate est FERME")
            rc = 1
    if rc == 0:
        print("  => gate %s : les deux faces concordent (effets, PV courants, attaque libre)." % label)
    return {"rc": rc, "gate_open": gate_open, "caster": caster, "ally": ally, "foe": foe,
            "nat_caster": sorted(nat_caster), "port_caster": sorted(port_caster),
            "nat_ally": sorted(nat_ally), "port_ally": sorted(port_ally),
            "nat_caster_rem": nat_caster, "port_caster_rem": port_caster,
            "nat_gain": nat_gain, "port_gain": port_gain,
            "nat_free_dmg": nat_free_dmg, "port_free_dmg": port_free_dmg,
            "expected": exp, "d_ally": ctx["d_ally"], "d_foe": ctx["d_foe"],
            "port_result": {k: res.get(k) for k in ("ability", "gate_passed", "dsl")}}


# ------------------------------------------------------------------------------------------------
# --step aura : l'OBSERVABLE de la reduction, sur un AMI a portee, avec son contre-modele
# ------------------------------------------------------------------------------------------------
def measure_aura(sid, ally_far=False):
    """Le porteur caste (gate FERME : seule l'aura est posee), puis l'ennemi frappe l'AMI.

    Les DEUX faces partent du MEME etat, capture APRES le cast, avec le MEME flux `state.rng`
    (`dumpRng`), donc le tirage du coup est identique des deux cotes. Le CONTRE-MODELE est le meme
    coup, cote port, avec l'instance 1097 CONSOMMEE."""
    from engine.runner.abilities.handler import AbilityHandler
    from engine.runner.messages import ActiveAbilityMessage

    ctx = build_montage(sid, with_sacrifices=False, ally_far=ally_far)
    caster, ally, foe = ctx["caster"], ctx["ally"], ctx["foe"]
    try:
        print("[aura/%s] porteur %s  ami %s (d=%d)  ennemi %s"
              % ("LOIN" if ally_far else "PORTEE", ctx["pos"][caster], ctx["pos"][ally],
                 ctx["d_ally"], ctx["pos"][foe]))
        legal = PR.legal_from_here(sid, ctx["rid"], caster, UNBREAKABLE_DUTY)
        tgt = caster if caster in legal else (ally if ally in legal else None)
        if tgt is None:
            raise RuntimeError("montage : aucune cible legale pour 1061 (%s)" % legal)
        res = PR.cast(sid, ctx["rid"], caster, tgt, UNBREAKABLE_DUTY)
        if not res.get("ok"):
            raise RuntimeError("cast 1061 refuse : %s" % str(res)[:300])
        dv = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                          "allAbilities": True}, 90)
        if UD_DAMAGE_REDUCTION not in live_family(dv, caster):
            raise RuntimeError("montage : 1097 n'est pas sur le porteur (%s)"
                               % sorted(live_family(dv, caster)))
        # Le tour passe a l'IA : c'est ELLE qui frappe l'ami (`legal_from_here` rend vide pour toute
        # unite dont ce n'est pas le tour). L'aura dure `TurnsFromRounds(1)` = 2 tours -> elle est
        # ENCORE la au tour adverse, ce que la garde ci-dessous VERIFIE au lieu de le supposer.
        _mine, theirs = _my_player_ids(dv)
        dv = _pass_turn_to(sid, ctx["rid"], theirs)
        rem = live_family(dv, caster).get(UD_DAMAGE_REDUCTION)
        if rem is None:
            raise RuntimeError("montage : 1097 a expire avant le coup (%s)"
                               % sorted(live_family(dv, caster)))
        print("[aura] 1097 encore sur le porteur au tour adverse (remaining=%s)" % rem)
        nid = next((a.get("id") for a in
                    (next(u for u in dv["units"] if int(u["id"]) == foe).get("abilities") or [])
                    if a.get("kind") == "normal"), None)
        if nid is None:
            nid = next((a.get("id") for a in
                        (next(u for u in dv["units"] if int(u["id"]) == foe).get("abilities") or [])
                        if a.get("kind") != "passive"), None)
        if nid is None or ally not in PR.legal_from_here(sid, ctx["rid"], foe, nid):
            raise RuntimeError("montage : l'ennemi ne peut pas frapper l'ami (ability=%s, legal=%s)"
                               % (nid, PR.legal_from_here(sid, ctx["rid"], foe, nid)
                                  if nid else None))
        board, dv0, ob0, cs0 = R1._snapshot(sid, ctx["rid"])
        hp0 = live_hp(dv0, ally)
        st = R1._seeded_state(sid, ctx["rid"], board, dv0, ob0, cs0)
        st2 = R1._seeded_state(sid, ctx["rid"], board, dv0, ob0, cs0)
        port_dmg = _replay_normal(st, foe, ally)
        for e in st2.effects.by_unit.get(int(caster), []):
            if e.effect_type is not None and int(e.effect_type) == UD_DAMAGE_REDUCTION:
                e.consumed = True                    # CONTRE-MODELE ECRIT : le meme coup, sans aura
        port_sans = _replay_normal(st2, foe, ally)
        act = PR.act(sid, ctx["rid"], {"kind": "ability", "casterId": foe,
                                       "targetId": ally, "abilityType": nid})
        if not act.get("ok"):
            raise RuntimeError("attaque native refusee : %s" % str(act)[:300])
        dv1 = PR.rpc(sid, "decisionView", {"runnerId": ctx["rid"], "maxRank": 1,
                                           "allAbilities": True}, 90)
        hp1 = live_hp(dv1, ally)
        nat_dmg = None if (hp0[0] is None or hp1[0] is None) else hp0[0] - hp1[0]
    finally:
        PR.dispose(sid, ctx["rid"])
    exp = expected_vars(st, caster)
    print("[aura] degat RECU par l'ami : natif=%s  port=%s  port SANS 1097=%s  (pct=%s%%)"
          % (nat_dmg, port_dmg, port_sans, exp["dmgReductionPct"]))
    return {"ally_far": ally_far, "d_ally": ctx["d_ally"], "nat_dmg": nat_dmg,
            "port_dmg": port_dmg, "port_sans": port_sans, "expected": exp}


def _replay_normal(st, attacker, target):
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.runner import Runner
    before = R1._hp(st, target)
    Runner(st).install_default_handlers(20).apply(AttackUnitMessage(int(attacker), int(target)))
    after = R1._hp(st, target)
    return None if (before is None or after is None) else (before - after)


def step_aura(sid):
    m = measure_aura(sid, ally_far=False)
    c = measure_aura(sid, ally_far=True)
    print("")
    print("=" * 96)
    rc = 0
    if m["nat_dmg"] is None or m["port_dmg"] is None:
        print("  INCONCLUSIF : degat non lisible (bras A PORTEE)")
        return 1
    if int(m["nat_dmg"]) != int(m["port_dmg"]):
        print("  ROUGE [A PORTEE] degat RECU natif=%s port=%s (ecart %d)"
              % (m["nat_dmg"], m["port_dmg"], m["nat_dmg"] - m["port_dmg"]))
        rc = 1
    if m["port_sans"] is not None and int(m["port_sans"]) == int(m["port_dmg"]):
        print("  CONTROLE ROUGE : le port rend la MEME valeur SANS 1097 -- la concordance ne "
              "serait pas attribuable a l'aura (%s)" % m["port_sans"])
        rc = 1
    if c["nat_dmg"] is not None and c["port_dmg"] is not None:
        if int(c["nat_dmg"]) != int(c["port_dmg"]):
            print("  ROUGE [HORS PORTEE] degat RECU natif=%s port=%s"
                  % (c["nat_dmg"], c["port_dmg"]))
            rc = 1
        if c["port_sans"] is not None and int(c["port_sans"]) != int(c["port_dmg"]):
            print("  ROUGE [HORS PORTEE] l'aura mord alors que l'ami est a %d hexes (sans=%s "
                  "avec=%s)" % (c["d_ally"], c["port_sans"], c["port_dmg"]))
            rc = 1
    else:
        print("  INCONCLUSIF : bras HORS PORTEE non lisible")
        rc = 1
    if rc == 0:
        print("  => l'ami a %d hexes encaisse -%d%% des deux cotes (%s), et l'ami a %d hexes n'a "
              "AUCUNE reduction." % (m["d_ally"], m["expected"]["dmgReductionPct"], m["nat_dmg"],
                                     c["d_ally"]))
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", default="all", choices=["ferme", "ouvert", "aura", "all"])
    args = ap.parse_args()
    sid = _resolve_session()
    rc = 0
    if args.step in ("ferme", "all"):
        rc |= measure_cast(sid, gate_open=False)["rc"]
    if args.step in ("ouvert", "all"):
        rc |= measure_cast(sid, gate_open=True)["rc"]
    if args.step in ("aura", "all"):
        rc |= step_aura(sid)
    return rc


if __name__ == "__main__":
    sys.exit(main())
