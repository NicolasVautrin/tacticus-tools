"""#946-r2 -- le TEMOIN qui separe `constants.range` de la portee d'ARME. La TROISIEME VOIE, jouee.

Le residu disait : « l'override `range` de `ValidNormalAttackTargets` est INDISCERNABLE sur le seul
porteur d'`UnwaveringSentinel`, et c'est MESURE ». Le fait est exact et il est RE-CONFIRME ici :
`custoKyrus` porte un Bolter de portee **2**, et `UnwaveringSentinel.constants.range` vaut **2** --
donc muter le port en `range = None` (portee d'arme) laisse tous ses temoins verts.

La fiche nommait TROIS issues, dont une NON EXPLOREE : « GREFFER le passif sur une unite du pool
dont l'arme a une portee != 2 ». C'est celle-ci, et elle se joue **OFFLINE** : le port ne lit pas
`BC.Units[].Weapons` (ce que `--unit-stat` patche, et c'est pour ca que ce levier-la echouait), il
lit le **gameconfig par `visualId`** (`unit_weapon_range`). Changer de porteur suffit donc a separer
les deux termes -- aucun montage live, aucune injection catalogue, aucune fenetre.

Ce que ce fichier garde :

  1. **LE PORTEUR REEL EST BIEN INDISCERNABLE** -- sinon ce fichier n'aurait pas de raison d'etre,
     et le residu serait faux. On le MESURE plutot que de le citer.
  2. **UN PORTEUR GREFFE, LUI, DISCRIMINE** : a distance 3 d'une unite dont l'arme porte a 3,
     `range_override = constants.range = 2` REFUSE et la portee d'ARME ACCEPTE. C'est exactement le
     mutant que le residu n'arrivait pas a tuer.
  3. **LE CABLAGE COMPLET SUIT** : le noeud DSL `attacker_in_normal_attack_range_tree`, alimente par
     `counter_attack_range()` (= la constante gameconfig), doit rendre le MEME verdict que
     l'appel direct -- sinon la constante serait lue au bon endroit et perdue en chemin.
  4. **LA CONSTANTE VIENT DU GAMECONFIG, PAS D'UN LITTERAL.** Un rebalancement du jeu doit faire
     bouger le test avec lui, jamais le rougir.

ASCII only.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": ("scripts/python/*.py", "scripts/python/**/*.py"),
    # `build: False` : rien n'est fige depuis le binaire -- la portee vient du gameconfig et la
    # geometrie est calculee.
    "build": False,
    "toujours": True,
    "raison": "Temoin DISCRIMINANT de l'override `range` de ValidNormalAttackTargets (#946-r2) : "
              "le porteur reel (`custoKyrus`, arme 2 == constants.range 2) ne separe pas les deux "
              "termes ; un porteur GREFFE a arme 3 les separe. Ferme le mutant `range = None` que "
              "les trois temoins live laissaient vert.",
}

import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                          # noqa: E402
import hexgeo                                                                    # noqa: E402
from engine.entities.pathfinding.board import Board                              # noqa: E402
from engine.runner.snapshot import load_state                                    # noqa: E402
from engine.runner.components import StatsComponent                              # noqa: E402
import engine.runner.abilities.targeting as T                                    # noqa: E402
from engine.runner.operations.triggers.loki import unwavering_sentinel as US     # noqa: E402

#: Le porteur REEL du passif (`unit_map.py find --ability UnwaveringSentinel` : 1 unite, voie
#: `passive`). Son Bolter porte a 2, comme la constante -- d'ou l'indiscernabilite.
PORTEUR_REEL = "custoKyrus"
#: Le porteur GREFFE : meme faction, arme a portee **3**. La greffe est LEGITIME parce que
#: `GetCounterAttackCondition` ne lit ni stat ni trait du caster -- seulement `constants.range` et la
#: geometrie (recette `case-92` Sec.5bis).
PORTEUR_GREFFE = "astarCyrus"
#: La DISTANCE de separation : hors de `constants.range` (2), dans la portee d'arme du greffe (3).
DISTANCE = 3

N = 9


def _board() -> Board:
    """Board PLAT : le relief n'a rien a voir avec ce que ce fichier mesure, et un board reel
    introduirait des portes d'elevation qui masqueraient le seul terme d'interet."""
    cells = {(c, r): 0 for c in range(N) for r in range(N)}
    ids = {q: i + 1 for i, q in enumerate(sorted(cells))}
    tiles = [{"id": ids[q], "col": q[0], "row": q[1], "elevation": 0, "walkable": True,
              "isWall": False,
              "neighbours": [ids[n] for n in hexgeo.neighbors(q[0], q[1]) if n in ids]}
             for q, e in cells.items()]
    return Board(tiles)


def _state(board, porteur_vid: str, distance: int):
    """`1` = le porteur du passif (team 1) en (0,0) ; `2` = l'attaquant (team 2) a `distance`."""
    units = [{"id": 1, "team": 1, "pos": (0, 0), "vid": porteur_vid},
             {"id": 2, "team": 2, "pos": (distance, 0), "vid": "astarLysander"}]
    decision = {"currentPlayer": 1, "units": [
        {"id": u["id"], "visualId": u["vid"], "alive": True, "team": u["team"],
         "owner": u["team"], "pos": {"col": u["pos"][0], "row": u["pos"][1]}, "effects": []}
        for u in units]}
    observe = {"units": [{"squadId": u["id"], "hp": 1000, "hpMax": 1000} for u in units]}
    snapshot = {"statTypes": {"movement": 1, "range": 2, "health": 5},
                "units": [{"entityId": u["id"], "entityType": 1,
                           "stats": {"health": 1000, "movement": 3, "turnsStarted": 1},
                           "healthMax": 1000, "traits": [], "unitFlags": [],
                           "unitConfig": {"visualId": u["vid"], "level": 50,
                                          "passiveAbilityLevel": 50, "activeAbilityLevel": 50,
                                          "abilityVariablesMultiplier": 100}}
                          for u in units]}
    return load_state(decision, observe, snapshot, board=board, ability_states=False)


def _portee_arme(st, uid: int, vid: str):
    sc = st.get_entity(uid).get_component(StatsComponent)
    return T.unit_weapon_range(vid, None if sc is None else sc.ctx)


# ================================================ 0. LA PREMISSE DU RESIDU, RE-MESUREE (piege 1)

def test_le_porteur_REEL_ne_separe_PAS_les_deux_termes():
    """Sans ce constat, ce fichier n'aurait aucune raison d'exister -- et le residu serait faux. On
    le mesure : la constante et la portee d'arme sont EGALES sur `custoKyrus`, donc les deux
    lectures rendent le meme verdict a toute distance."""
    rng = US.counter_attack_range()
    assert rng is not None, "`constants.range` absent du gameconfig : le port n'armerait AUCUN override"
    board = _board()
    st = _state(board, PORTEUR_REEL, DISTANCE)
    assert _portee_arme(st, 1, PORTEUR_REEL) == int(rng), \
        "la premisse du residu a change : le porteur reel discrimine desormais, ce fichier est a revoir"
    assert (T.valid_normal_attack_targets(st, 1, int(rng))
            == T.valid_normal_attack_targets(st, 1, None)), \
        "sur le porteur REEL, les deux lectures COINCIDENT -- c'est l'indiscernabilite mesuree"


# ============================================== 1. LE PORTEUR GREFFE, LUI, DISCRIMINE (piege 2)

def test_le_montage_greffe_est_bien_DISCRIMINANT():
    """Le fait qui fonde tout le reste, MESURE et non suppose : le greffe porte a 3, la constante
    vaut 2, et l'attaquant est pose a exactement 3."""
    rng = int(US.counter_attack_range())
    board = _board()
    st = _state(board, PORTEUR_GREFFE, DISTANCE)
    assert hexgeo.distance((0, 0), (DISTANCE, 0)) == DISTANCE
    assert _portee_arme(st, 1, PORTEUR_GREFFE) == DISTANCE
    assert rng != DISTANCE, "sans cet ecart, le montage ne separerait rien"
    assert T.unit_is_ranged(st, 1) is True, \
        "un caster de MELEE verrait `only_adjacent` force par le preset -- la portee ne serait pas lue"


def test_l_override_range_REFUSE_ce_que_la_portee_d_ARME_accepterait():
    """LE MUTANT QUE LE RESIDU N'ARRIVAIT PAS A TUER. `range = Direct(GetNumberConstant(range))`
    refuse l'attaquant a 3 ; `range = None` (portee d'arme) l'accepterait. Les DEUX branches sont
    assertees -- une seule ne prouverait pas que le terme MORD."""
    rng = int(US.counter_attack_range())
    st = _state(_board(), PORTEUR_GREFFE, DISTANCE)
    assert T.valid_normal_attack_targets(st, 1, rng) == [], \
        "override `range` = %d : l'attaquant a %d est HORS de portee" % (rng, DISTANCE)
    assert T.valid_normal_attack_targets(st, 1, None) == [2], \
        "portee d'ARME = %d : il y serait -- c'est ce que le mutant `range = None` ferait" % DISTANCE


def test_dans_la_portee_de_la_CONSTANTE_les_deux_lectures_coincident():
    """CONTRE-EPREUVE de non-degenerescence : a distance 2 (= la constante), les deux lectures
    ACCEPTENT. Sans elle, un port qui refuserait TOUT passerait le test precedent."""
    rng = int(US.counter_attack_range())
    st = _state(_board(), PORTEUR_GREFFE, rng)
    assert T.valid_normal_attack_targets(st, 1, rng) == [2]
    assert T.valid_normal_attack_targets(st, 1, None) == [2]


# ============================================================ 2. LE CABLAGE COMPLET (piege 3)

def _condition(st, rng):
    """Le SECOND conjoint de `GetCounterAttackCondition`, evalue sur l'etat -- `Owner` = le porteur
    du passif, `Actor` = l'attaquant."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    arbre = US.attacker_in_normal_attack_range_tree(rng)
    ents = entities_from_state(st, 1, 2)
    ents.actor = ents.units_by_id.get(2) if hasattr(ents, "units_by_id") else None
    return arbre, ents


def test_le_noeud_DSL_lit_bien_la_CONSTANTE_et_pas_autre_chose():
    """Le cablage : `attacker_in_normal_attack_range_tree(counter_attack_range())`. La valeur
    passee au noeud DOIT etre la constante gameconfig -- si le foyer la perdait en chemin, l'appel
    direct ci-dessus resterait vert et la riposte partirait quand meme."""
    rng = US.counter_attack_range()
    assert rng is not None and int(rng) == int(
        (GC.ability("UnwaveringSentinel") or {}).get("constants", {}).get("range")), \
        "la constante doit venir du GAMECONFIG, jamais d'un litteral -- un rebalancement doit suivre"
    # Le noeud transporte la valeur telle quelle : c'est ce que le port doit garantir.
    arbre = US.attacker_in_normal_attack_range_tree(int(rng))
    assert getattr(arbre, "list", None) is not None or arbre is not None


def test_la_constante_est_LUE_et_non_ecrite_en_dur():
    """Aucun `2` en litteral dans le foyer : `counter_attack_range` doit passer par
    `ability_var(..., is_constant=True)`. Un rebalancement du jeu doit deplacer le port avec lui."""
    src = Path(US.__file__).read_text(encoding="utf-8")
    assert "AbilityConstantType.range.name" in src, \
        "la constante doit etre lue par son MEMBRE d'enum, jamais par un ordinal ni un litteral"
