"""GARDE des `TARGETING_OPTIONS` (#115) des actives Necrons / Orks / Votann / GenestealerCults.

Le PROBE (`probe_targeting_masks_lot4.py`) MESURE (confrontation exhaustive cible par cible sur 5
groupes de runners) ; ces tests GARDENT les deux proprietes qu'un port ne doit plus jamais perdre :

  1. STRUCTURE (offline) -- chaque ability de ces 4 fichiers PORTE son masque. Sans masque,
     `get_invalid_target_reason` rend 0 immediatement et l'ability n'est PAS gatee du tout : la
     regression est PERMISSIVE, donc muette en self-play. C'est l'assertion qui ROUGIT si un
     `TARGETING_OPTIONS` est retire.

  2. ACCORD AVEC LE NATIF (live) -- pour chaque porteur present dans le runner, le verdict du port
     est confronte a l'ORACLE natif `abilityReason`
     (`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` +
     `$$GetInvalidCasterReason`), cible par cible. Deux exigences ASYMETRIQUES, calquees sur la
     doctrine du module :
       * le port ne doit JAMAIS refuser ce que le natif ACCEPTE (faux refus = casse des casts
         legitimes en silence) -> FATAL ;
       * le port PEUT accepter ce que le natif refuse (regle non portee : portee, regle dynamique,
         domaine TILE...) -> tolere, c'est la degradation permissive documentee.
     Et le test exige AU MOINS UN refus concordant : sans lui, le masque serait une annotation, pas
     un gate.

Etat live REEL (board + stats du runner), oracle natif, ASCII only.
"""
from __future__ import annotations

import pytest

from engine.entities.pathfinding.board import Board
from engine.runner.abilities.handler import ABILITY_CLASSES
from engine.runner.abilities.targeting import get_invalid_target_reason
from engine.runner.snapshot import load_state

# (ActiveAbilityType, nom, visualId du porteur). Les 13 abilities des 4 fichiers de la tranche.
LOT = [
    (1008, "HarbingerOfDestruction", "necroPlasmancer"),
    (1009, "ResurrectionOrb", "necroOverlord"),
    (1226, "Chronometron", "necroChronomancer"),
    (1006, "MultiThreatEliminator", "necroDestroyer"),
    (1200, "SquigLaunchas", "orksRukkatrukk"),
    (1201, "SquigMine", "orksRukkatrukk"),
    (1219, "IronkinSteeljack", "votanMemnyr"),
    (1221, "AugmentedAssault", "votanBeserk"),
    (1206, "GravitonRifle", "votanIronmaster"),
    (1207, "AncestralFortune", "votanUthar"),
    (1179, "CultDemagogue", "genesPrimus"),
    (1180, "HeroicFusillade", "genesKelermorph"),
    (1202, "VigilanceEternal", "custoKyrus"),
]

# Porteurs directement spawnables (`rl_duel build --list-pool`) -> confrontables par CE test.
POOL_CASES = [(1009, "ResurrectionOrb", "necroOverlord"),
              (1006, "MultiThreatEliminator", "necroDestroyer"),
              (1179, "CultDemagogue", "genesPrimus"),
              (1180, "HeroicFusillade", "genesKelermorph"),
              (1202, "VigilanceEternal", "custoKyrus")]

# Regles que le port n'implemente PAS (inventaire en tete de `engine/runner/abilities/targeting.py`).
# Le natif s'arrete a la PREMIERE regle rompue de SA cascade : quand cette regle-la n'est pas portee,
# un code de refus different cote port n'est pas une divergence de verdict.
UNPORTED = (0x8000000, 0x2, 0x200000000, 0x800000, 0x800, 0x40000000000000)


def _hexi(h):
    try:
        return int(str(h), 16) if h else 0
    except ValueError:
        return 0


# ------------------------------------------------------------------ 1. STRUCTURE (offline)

def test_lot_abilities_all_carry_their_targeting_mask():
    """CHAQUE ability des 4 fichiers porte son `TARGETING_OPTIONS`. ROUGIT si un masque est retire.

    C'est la garde de NON-REGRESSION du CLAUDE.md (« entrer au registre SANS son masque de ciblage
    = regression silencieuse ») appliquee a cette tranche."""
    missing = []
    for ab_id, name, _carrier in LOT:
        klass = ABILITY_CLASSES.get(ab_id)
        if klass is None:
            continue                      # ability retiree du registre : hors perimetre de ce test
        if getattr(klass, "TARGETING_OPTIONS", None) is None:
            missing.append("%s (%d)" % (name, ab_id))
    assert not missing, (
        "abilities SANS TARGETING_OPTIONS -> aucun gate de cible, degradation PERMISSIVE muette: %s"
        % ", ".join(missing))


def test_self_cast_flag_matches_the_three_native_self_cast_abilities():
    """`self_cast` (le byte `options+0x00`) est pose sur EXACTEMENT les 3 abilities dont le ctor
    natif le met a 1 : ResurrectionOrb (1009), AncestralFortune (1207), Chronometron (1226).

    Ce flag n'est PAS cosmetique : il aiguille le cast SUR SOI vers
    `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason` au lieu du filtre statique.
    L'oublier ferait refuser un self-cast par `TargetIsEnemy` -- un FAUX REFUS (mesure : Chronometron
    1226, natif 0x800, port 0x4000 avant le cablage)."""
    got = {ab_id for ab_id, _n, _c in LOT
           if ABILITY_CLASSES.get(ab_id) is not None
           and getattr(getattr(ABILITY_CLASSES[ab_id], "TARGETING_OPTIONS", None),
                       "self_cast", False)}
    assert got == {1009, 1207, 1226}, got


# ------------------------------------------------------------------ 2. ACCORD AVEC LE NATIF (live)

def test_masks_agree_with_native_ability_reason_live(rpc, build_runner):
    """Confronte le port a l'oracle natif `abilityReason`, cible par cible, sur les 5 porteurs du
    lot presents dans le pool. FATAL : un refus du port sur une cible que le natif ACCEPTE."""
    rid = build_runner("777", extra=[
        "--p-units", "necroOverlord,necroDestroyer,genesPrimus,genesKelermorph,custoKyrus",
        "--a-units", "eldarRanger,astraBullgryn,darkaCompanion", "--no-ai"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    st = load_state(dec, ob, snap, board=board)
    units = [u for u in (dec.get("units") or []) if u.get("alive")]
    by_vis = {}
    for u in units:
        by_vis.setdefault(u.get("visualId"), u)

    false_refusals, bit_diffs, concordant = [], [], 0
    for ab_id, name, carrier in POOL_CASES:
        klass = ABILITY_CLASSES.get(ab_id)
        src = by_vis.get(carrier)
        if klass is None or src is None:
            continue
        ability = klass()
        cid = int(src["id"])
        for u in units:
            uid = int(u["id"])
            nat = rpc("abilityReason", {"runnerId": rid, "casterId": cid,
                                        "abilityType": ab_id, "targetId": uid}, 60)
            if not (isinstance(nat, dict) and nat.get("ok")):
                continue
            nt = _hexi((nat.get("targetReason") or {}).get("hex"))
            if nt == 0x1:
                continue                  # `ValidRequest` : le natif a refuse EN AMONT du filtre
            pt = int(get_invalid_target_reason(st, cid, uid, ability) or 0)
            if pt and not nt:
                false_refusals.append((name, cid, uid, hex(pt)))
            elif pt and nt and pt != nt and nt not in UNPORTED:
                bit_diffs.append((name, cid, uid, hex(pt), hex(nt)))
            elif pt and nt:
                concordant += 1
    assert not false_refusals, (
        "FAUX REFUS -- le port refuse une cible que le natif ACCEPTE (casse des casts legitimes, "
        "en silence): %s" % false_refusals)
    assert not bit_diffs, (
        "le port et le natif refusent pour des regles DIFFERENTES (et la regle native est portee): "
        "%s" % bit_diffs)
    assert concordant > 0, (
        "AUCUN refus concordant : les masques n'ont rien gate -- ce serait une annotation, pas un "
        "gate (le test passerait meme masques retires)")


def test_resurrection_orb_is_self_cast_only_live(rpc, build_runner):
    """CAS DE REFUS le plus net du lot : `ResurrectionOrbAbility$$.ctor` pose le bit 39
    (`0x8000000000`, « la cible DOIT etre le caster »). Le natif REFUSE donc tout target != caster
    -- et le port aussi depuis que le masque est pose. AVANT le masque, le port acceptait.

    ROUGIT si `TARGETING_OPTIONS` de 1009 est retire (le port rendrait 0 partout)."""
    klass = ABILITY_CLASSES.get(1009)
    if klass is None:
        pytest.skip("1009 hors ABILITY_CLASSES")
    rid = build_runner("777", extra=["--p-units", "necroOverlord,necroDestroyer",
                                     "--a-units", "eldarRanger,astraBullgryn", "--no-ai"])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="evenq")
    dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    st = load_state(dec, ob, snap, board=board)
    units = [u for u in (dec.get("units") or []) if u.get("alive")]
    caster = next((u for u in units if u.get("visualId") == "necroOverlord"), None)
    if caster is None:
        pytest.skip("necroOverlord absent du runner")
    ability = klass()
    cid = int(caster["id"])

    # (a) SELF : accepte des deux cotes (le self-cast est aiguille vers GetCasterNotAddedReason).
    assert get_invalid_target_reason(st, cid, cid, ability) == 0
    nat_self = rpc("abilityReason", {"runnerId": rid, "casterId": cid,
                                     "abilityType": 1009, "targetId": cid}, 60)
    assert _hexi((nat_self.get("targetReason") or {}).get("hex")) == 0, nat_self

    # (b) TIERS : refuse des deux cotes, AVEC LE MEME CODE (bit 39 TargetIsCaster).
    others = [u for u in units if int(u["id"]) != cid]
    assert others, "il faut au moins une autre unite pour exercer le refus"
    for u in others:
        uid = int(u["id"])
        nat = rpc("abilityReason", {"runnerId": rid, "casterId": cid,
                                    "abilityType": 1009, "targetId": uid}, 60)
        nt = _hexi((nat.get("targetReason") or {}).get("hex"))
        pt = int(get_invalid_target_reason(st, cid, uid, ability) or 0)
        assert pt == 0x8000000000, (
            "cible %d != caster : le port doit rendre TargetIsCaster (bit 39), pas %s" % (uid, hex(pt)))
        assert nt == pt, ("natif=%s port=%s pour la cible %d" % (hex(nt), hex(pt), uid))
