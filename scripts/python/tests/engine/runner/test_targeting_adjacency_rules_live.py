"""#243 -- GARDE du volet ADJACENCE du filtre statique de ciblage, confronte au NATIF.

CE QUE CE FICHIER PROUVE, ET POURQUOI IL EXISTE
-----------------------------------------------
Quatre regles de `IdunBattle.Core.Services.TargetingRule` etaient DECLAREES par des masques poses au
registre et n'etaient PAS portees par la cascade (`engine/runner/abilities/targeting.py`), donc ne
refusaient JAMAIS rien offline :

    bit  5  0x20            TargetHasFreeAdjacentTile   battleQuery slot 0x51 (GetFreeAdjacentTiles)
    bit 12  0x1000          TargetTileIsFree            TileExtensions$$CanAddUnit(t, state, 1, 0, 0)
    bit 32  0x100000000     TargetIsNotAdjacent         battleQuery slot 0x61 (AreEntitiesAdjacent)
    bit 42  0x40000000000   TargetIsNotAdjacentToEnemy  battleQuery slot 0x7f (GetAdjacentEnemies)

plus la BRANCHE `TargetIsTile` du DEBUT du filtre (tuile-cible non marchable -> le natif rend le
litteral `1`, c'est-a-dire `ValidRequest`, sauf sous `AllowUnwalkableTargetTile`).

Les bits 32 et 42 sont la CIBLE de la tranche ; les trois autres maillons y entrent parce qu'ils les
PRECEDENT dans la cascade native et que, sans eux, le port refusait pour la MAUVAISE raison (mesure
ci-dessous). L'ordre n'est pas cosmetique : le natif s'arrete a la PREMIERE regle rompue.

Quatre assertions, dans cet ordre :

  1. `test_le_natif_refuse_bien_ce_cas`   -- PRECONDITION lue sur l'oracle `abilityReason` (masque
     `TargetingRule` natif). Sans elle, les suivantes garderaient du vide.
  2. `test_avant_le_moteur_acceptait`     -- LE ROUGE AVANT, MESURE : la MEME ability privee des
     quatre bits (= son etat sur `master`) rend 0 = CAST ACCEPTE sur un cast que le natif REFUSE.
  3. `test_le_moteur_refuse_pour_la_meme_raison` -- le port refuse, avec le MEME code que le natif
     (pas seulement « refuse » : c'est la RAISON qui distingue un port juste d'un port faux).
  4. les deux proprietes de CONTRAT sur TOUS les couples mesures (cf. `case-115` §3) :

        natif == 0   =>  port == 0                          (le port n'invente aucun refus)
        natif != 0   =>  port == natif  (regle PORTEE)  ou  port == 0  (regle NON PORTEE, permissif)
        jamais       :   port != 0 et port != natif

PORTEURS (gate de confrontabilite) :
  * bit 32 -- trois HERO du pool (`rl_duel.py build --list-pool`) : `orksWarboss` (1058 Waaagh),
    `bloodIntercessor` (1153 HammerOfWrath), `admecDestroyer` (1139 SentinelDirectives).
  * bits 12/42 -- `tyranBiovore` (1145 SporeMineLauncher), MACHINE OF WAR du pool MoW, castee depuis
    hors-plateau sur une TUILE.

MESURE DE REFERENCE (runner MC1_67 / seed 777, cf. `probe_243_not_adjacent.py`) :
  1058 @d=1 natif `TargetIsNotAdjacent`, AVANT le port rendait `TargetIsInRange` (mauvaise raison) ;
  1153 @d=1 natif `TargetIsNotAdjacent`, AVANT 0 ; 1139 @d=1 idem, AVANT 0 ;
  1145 tuile voisine d'un ennemi natif `TargetIsNotAdjacentToEnemy`, AVANT 0 ;
  1145 tuile OCCUPEE voisine d'un ennemi natif `TargetTileIsFree` (bit 12, qui PRECEDE le bit 42),
  AVANT 0 ; 1153 cible encerclee natif `TargetHasFreeAdjacentTile` (bit 5, qui PRECEDE le bit 32).

ASCII only. Le harnais indisponible = ECHEC (conftest), jamais un skip vert.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from _not_adjacent_stage import build_stage, pick                # noqa: E402

from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402

WAAAGH = 1058
HAMMER = 1153
SENTINEL = 1139
SPORE = 1145


@pytest.fixture(scope="module")
def adjacency243():
    """Portee MODULE : une seule bataille pour tout le fichier (les mesures sont figees sur le MEME
    etat, chaque scenario n'est qu'une lecture de plus)."""
    return build_stage()


# --- les cas d'unite, resolus SUR LA MESURE : (id, ability, regle NATIVE attendue).
UNIT_CAS = [
    ("NOTADJ_1058", WAAAGH, TR.TargetIsNotAdjacent),
    ("NOTADJ_1153", HAMMER, TR.TargetIsNotAdjacent),
    ("NOTADJ_1139", SENTINEL, TR.TargetIsNotAdjacent),
    ("FREEADJ_1153", HAMMER, TR.TargetHasFreeAdjacentTile),
]
UNIT_IDS = [c[0] for c in UNIT_CAS]
TILE_CAS = [("NEAR_1145", "near", TR.TargetIsNotAdjacentToEnemy),
            ("OCCUPIED_1145", "occupied", TR.TargetTileIsFree),
            ("FAR_1145", "far", 0)]
TILE_IDS = [c[0] for c in TILE_CAS]


def _unit_row(stage, cas_id):
    _, at, rule = next(c for c in UNIT_CAS if c[0] == cas_id)
    r = pick(stage, at, rule)
    if r is None:
        pytest.fail(
            "%s : AUCUN couple (caster, cible) que le natif refuse pour %s dans cette geometrie -- "
            "le montage n'a pas amene le hero au contact, rien n'a ete confronte "
            "(pairing=%s)" % (cas_id, TR(int(rule)).name, stage["pairing"]), pytrace=False)
    return r


def _tile_row(stage, cas_id):
    _, label, _rule = next(c for c in TILE_CAS if c[0] == cas_id)
    t = (stage["tiles42"] or {}).get(label)
    if t is None:
        pytest.fail("%s : le board n'offre pas de tuile '%s' (MoW absente, ou geometrie) -- rien "
                    "n'a ete confronte" % (cas_id, label), pytrace=False)
    return t


# ================================================================================================ #
# 1. PRECONDITION -- le natif refuse, et pour la raison qu'on croit
# ================================================================================================ #

@pytest.mark.parametrize("cas_id", UNIT_IDS)
def test_le_natif_refuse_bien_ce_cas_unite(adjacency243, cas_id):
    _, _at, rule = next(c for c in UNIT_CAS if c[0] == cas_id)
    r = _unit_row(adjacency243, cas_id)
    assert r["native"]["target_hex"] == int(rule)
    assert r["native"]["caster_hex"] == 0, (
        "%s : le volet CASTER refuse deja (%s) -- le filtre de CIBLE ne serait pas ce qu'on mesure. "
        "Le montage doit purger le flag `Moved` par un double `endturn` apres avoir deplace le hero."
        % (cas_id, r["native"]["caster_names"]))


@pytest.mark.parametrize("cas_id", TILE_IDS)
def test_le_natif_refuse_bien_ce_cas_tuile(adjacency243, cas_id):
    _, _label, rule = next(c for c in TILE_CAS if c[0] == cas_id)
    t = _tile_row(adjacency243, cas_id)
    assert t["native"]["target_hex"] == int(rule), (
        "%s : natif attendu %#x, lu %#x %s (tuile %s %s)"
        % (cas_id, int(rule), t["native"]["target_hex"], t["native"]["target_names"],
           t["tile_id"], t["coord"]))


# ================================================================================================ #
# 2. LE ROUGE AVANT -- ce que la tranche corrige, MESURE et non affirme
# ================================================================================================ #

@pytest.mark.parametrize("cas_id", ["NOTADJ_1153", "NOTADJ_1139"])
def test_avant_le_moteur_acceptait_un_cast_que_le_natif_refuse(adjacency243, cas_id):
    """Privee des quatre bits (l'etat de `master`), l'ability rend 0 sur un cast que le natif
    REFUSE : ni erreur ni crash, la behaviour se serait executee integralement. C'est le trou exact
    qu'un entrainement irait exploiter, et il est invisible en self-play."""
    r = _unit_row(adjacency243, cas_id)
    assert r["before"] == 0, (
        "%s : sans les bits d'adjacence le port devrait ACCEPTER (0) -- il rend %#x. Le refus vient "
        "donc d'ailleurs, et ce test ne prouve plus ce qu'il annonce." % (cas_id, r["before"]))


@pytest.mark.parametrize("cas_id", ["NEAR_1145", "OCCUPIED_1145"])
def test_avant_le_moteur_acceptait_cette_tuile(adjacency243, cas_id):
    t = _tile_row(adjacency243, cas_id)
    assert t["before"] == 0, (
        "%s : sans les bits d'adjacence le port devrait ACCEPTER cette tuile (0) -- il rend %#x"
        % (cas_id, t["before"]))


def test_avant_waaagh_refusait_pour_la_mauvaise_raison(adjacency243):
    """Cas DISTINCT des precedents, et le plus instructif : pour une cible AU CONTACT, `master` ne
    laissait pas passer -- il refusait avec le code de la regle DYNAMIQUE de Waaagh
    (`TargetIsInRange`), la ou le natif rend `TargetIsNotAdjacent`. C'etait donc deja une violation
    du contrat §3 (`port != 0 et port != natif`), latente parce qu'aucune geometrie de test
    n'amenait un ennemi a d=1 du Warboss."""
    r = _unit_row(adjacency243, "NOTADJ_1058")
    assert r["before"] not in (0, r["native"]["target_hex"]), (
        "l'etat AVANT ne montre plus la divergence de raison sur Waaagh (avant=%#x, natif=%#x) : "
        "le cas n'est plus discriminant" % (r["before"], r["native"]["target_hex"]))


# ================================================================================================ #
# 3. APRES -- le port refuse, et avec le MEME code que le natif
# ================================================================================================ #

@pytest.mark.parametrize("cas_id", UNIT_IDS)
def test_le_moteur_refuse_pour_la_meme_raison_unite(adjacency243, cas_id):
    r = _unit_row(adjacency243, cas_id)
    assert r["port"] == r["native"]["target_hex"], (
        "%s : le port rend %#x, le natif %#x %s (caster %s -> cible %s, d=%s)"
        % (cas_id, r["port"], r["native"]["target_hex"], r["native"]["target_names"],
           r["caster_vis"], r["target_vis"], r["dist"]))


@pytest.mark.parametrize("cas_id", TILE_IDS)
def test_le_moteur_rend_le_meme_verdict_sur_la_tuile(adjacency243, cas_id):
    t = _tile_row(adjacency243, cas_id)
    assert t["port"] == t["native"]["target_hex"], (
        "%s : le port rend %#x, le natif %#x %s (tuile %s %s)"
        % (cas_id, t["port"], t["native"]["target_hex"], t["native"]["target_names"],
           t["tile_id"], t["coord"]))


# ================================================================================================ #
# 4. CONTRAT DE FIDELITE -- sur TOUS les couples mesures
# ================================================================================================ #

def test_le_port_ne_refuse_jamais_ce_que_le_natif_accepte(adjacency243):
    """Propriete « zero regression » : une regle non portee est permissive, donc un maillon juste ne
    peut pas produire de refus la ou le natif accepte. C'est le sens qui casse en premier quand une
    regle nouvellement portee est trop stricte (ex. un `CanAddUnit` qui refuserait une tuile
    placable)."""
    bad = [(r["ability"], r["caster_vis"], r["target_vis"], hex(r["port"]))
           for r in adjacency243["rows"]
           if r["native"]["target_hex"] == 0 and r["port"] != 0]
    bad += [(SPORE, "tyranBiovore", label, hex(t["port"]))
            for label, t in (adjacency243["tiles42"] or {}).items()
            if t["native"]["target_hex"] == 0 and t["port"] != 0]
    assert not bad, ("le port refuse ce que le natif ACCEPTE "
                     "(ability, caster, cible, raison portee) : %s" % bad)


def test_aucun_refus_pour_la_mauvaise_raison(adjacency243):
    """Contrat §3 dans son autre sens : quand le natif refuse, le port rend soit EXACTEMENT sa
    raison, soit 0. Une troisieme valeur = maillon faux -- et c'est exactement ce que la tranche a
    trouve puis corrige sur Waaagh et sur HammerOfWrath (bits 5 et 12 ajoutes pour l'ORDRE)."""
    wrong, exact = [], []
    rows = [(r["ability"], r["caster_vis"], r["target_vis"], r["native"], r["port"])
            for r in adjacency243["rows"]]
    rows += [(SPORE, "tyranBiovore", label, t["native"], t["port"])
             for label, t in (adjacency243["tiles42"] or {}).items()]
    for at, cv, tv, nat, port in rows:
        if nat["target_hex"] == 0:
            continue
        if port == nat["target_hex"]:
            exact.append((at, tv, hex(port)))
        elif port != 0:
            wrong.append((at, cv, tv, hex(port), hex(nat["target_hex"]), nat["target_names"]))
    assert not wrong, ("refus pour une raison DIFFERENTE du natif "
                       "(ability, caster, cible, port, natif, noms) : %s" % wrong)
    assert exact, "aucun refus natif reproduit a l'identique : test non discriminant"


# ================================================================================================ #
# 5. GENERALISATION -- AUTRE board, AUTRE seed, AUTRES porteurs
# ================================================================================================ #

@pytest.fixture(scope="module")
def generalise243():
    """SECOND montage : board `C3_30` (au lieu de MC1_67), seed 31337 (au lieu de 777), et les
    porteurs des deux regles que la tranche a du porter pour l'ORDRE mais qui ne portent PAS les bits
    32/42 -- `necroOverlord` (1009, bit 5), `ultraInceptorSgt` (1003, bit 5), `tyranWingedPrime`
    (1112, bit 12) et la MoW `orksRukkatrukk` (1201, bit 12). C'est la mesure du RAYON D'IMPACT."""
    import probe_243_not_adjacent as P
    try:
        return P.run_generalise()
    except RuntimeError as exc:
        pytest.fail("build runner KO / harnais indisponible : %s" % exc, pytrace=False)


def test_generalisation_contrat_sur_les_autres_porteurs(generalise243):
    """Sur un AUTRE board, un AUTRE seed et quatre AUTRES abilities (unites ET tuiles), le contrat
    tient dans ses deux sens : aucun refus invente, aucune raison divergente.

    Le filtre `in_contract` n'ecarte que les couples dont la raison native est CONSTANTE sur toutes
    les cibles du caster (ability indisponible) -- ecarter `0x1` a l'aveugle masquerait la branche
    `TargetIsTile` du filtre, qui rend le MEME code pour une tuile non marchable."""
    import probe_243_not_adjacent as P
    rows = P.in_contract(generalise243["rows"])
    assert rows, "aucun couple dans le contrat : montage non discriminant"
    invented = [(r["ability"], r["caster_vis"], r["target_id"], hex(r["port"]))
                for r in rows if r["native"]["target_hex"] == 0 and r["port"] != 0]
    assert not invented, "refus INVENTES (le natif accepte) : %s" % invented
    wrong = [(r["ability"], r["caster_vis"], r["target_id"], hex(r["port"]),
              hex(r["native"]["target_hex"]), r["native"]["target_names"])
             for r in rows
             if r["native"]["target_hex"] and r["port"] not in (0, r["native"]["target_hex"])]
    assert not wrong, "refus pour une raison DIFFERENTE du natif : %s" % wrong
    exact = [r for r in rows
             if r["native"]["target_hex"] and r["port"] == r["native"]["target_hex"]]
    assert exact, "aucun refus natif reproduit a l'identique : test non discriminant"
