"""GARDE #271-r3 -- le regime SPAWN de la feuille `TriggeredAbilitiesNonOwner(4)`.

CE QUE CETTE GARDE PROTEGE
---------------------------
Le dispatcher court-circuitait sur `is_spawning`, et la fiche disait « le ctx de spawn ne porte
aucune cle d'unite => la feuille rend 0 ». Les DEUX moities etaient fausses :

  * le natif N'ARRETE PAS. `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.u003CEvaluateMovementInStepsu003Ed__0$$MoveNext`
    ne rend `Fix64.Zero` que si `case.unit` **ET** `case.parent` sont nuls ; et
    `...u003CIterateAbilitiesu003Ed__3$$MoveNext` prend alors le PARENT pour sujet
    (`subject = case.unit ?? case.parent`) en DESARMANT l'exclusion de self -- son `continue` est
    garde par `case.unit != null` ;
  * TROIS corps du registre yieldent dans ce regime, parce qu'ils ne lisent JAMAIS `case.unit` :
    `PsychicFortress` (20), `BookOfFate` (5) et la BRANCHE SPAWN de `MawClawsOfThyrax` (5, la seule
    des deux branches qui n'a PAS le gate `Summon`).

L'ecart etait donc CHIFFRE et SILENCIEUX : chaque tuile de spawn adjacente a un porteur ami valait
jusqu'a 30 points de moins cote port que cote natif, sur la decision qui choisit OU un summon
apparait (`IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtilityForSummon`).

DEUX FAUTES SYMETRIQUES SONT GARDEES ICI, et la seconde est la plus vicieuse
-----------------------------------------------------------------------------
  (a) rendre 0 la ou le natif verse -- l'etat d'avant ;
  (b) VERSER la ou le natif rend 0. En ouvrant le regime, le gate `is_spawning` de chaque playbook
      cesse d'etre decoratif et devient LOAD-BEARING. DEUX classes ne l'avaient pas :
      `KustomForceFieldReworkedNonOwnerPlaybook` (son corps natif est ENTIEREMENT garde par
      `if (case+0x10 != 0)`, relu au desassembleur) aurait verse un `+10` fantome -- `is_friend` est
      calcule sur le PARENT en regime SPAWN, donc vrai ; et `ECogSupportPlaybookNonOwnerPlaybook`,
      dont le gate n'etait qu'IMPLICITE (il tombait par l'absence de `unit_traits`).

ASCII only.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

#: Ce qui doit changer pour que cette garde puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE SUBSTRAT du regime SPAWN et le dispatcher de la feuille 4 -- l'objet meme du fichier.
        "scripts/python/engine/utilities/tile.py",
        # LES CORPS : les trois qui yieldent en SPAWN, les deux gates load-bearing, le registre.
        "scripts/python/engine/playbook/non_owner.py",
        # L'ADJACENCE (`MovementUtil$$AreTilesAdjacent`, porte d'elevation + court-circuit
        # d'identite) : c'est elle qui decide quelles tuiles de spawn recoivent le terme.
        "scripts/python/engine/battle_query.py",
        # LES POIDS BC : la somme attendue est DERIVEE de trois cles, jamais ecrite en dur.
        "scripts/python/engine/weights.py",
        # LA COMPOSITION du composite `Tile(7)`, dont l'etage RAYON DE SOUFFLE derive son perimetre.
        "scripts/python/engine/utilities/utility_type.py",
        # ⚠ LARGE ET ASSUME : importer `engine.utilities.tile` tire la cascade du paquet `engine`
        # (playbooks, pathfinding, entites). Une liste feuille-a-feuille ne peut pas montrer le
        # module qu'elle a oublie -- les chemins NOMMES ci-dessus disent OU regarder, les deux
        # globs disent ce qui FAIT changer d'avis. Les DEUX formes sont necessaires : `**/` exige
        # un SEGMENT, donc `scripts/python/**/*.py` ne voit PAS `scripts/python/gameconfig.py`.
        "scripts/python/*.py", "scripts/python/**/*.py",
        # ⚠ HORS de `scripts/python/` -- aucun des deux globs ne les couvre. Les entrees
        # VERSIONNEES que la cascade lit (seed BC, gameconfig, boards) et la table des noms
        # d'ability, qui vit dans le bundle Frida. Mesure : `dirs = ['data', 'frida/hooks/data']`.
        "data/**", "frida/hooks/data/ability-names.ts",
    ),
    # Les trois poids (`PSYCHICFORTRESS_AdjacentFriendly`, `BookOfFate_AdjacentSummons`,
    # `MawClawsOfThyrax_AdjacentSummons`) sont LUS dans le gameconfig du build : un re-dump peut les
    # faire bouger, et l'etage 2 doit alors rougir plutot que de figer une valeur perimee.
    "build": True,
    "toujours": False,
    "raison": (
        "Le regime SPAWN est un mirror de deux corps natifs (`<EvaluateMovementInSteps>d__0` et "
        "`<IterateAbilities>d__3`) plus les corps des playbooks : il ne peut changer de verdict "
        "que si le substrat (`_spawn_leaf_ctx`), le dispatcher, un corps de `non_owner.py`, "
        "l'adjacence portee ou les poids BC du build changent."),
}

#: Les classes du registre qui YIELDENT en regime SPAWN -- LU au decompile, corps par corps
#: (`<CalculateMovementUtilityInSteps>d__2$$MoveNext` de chacune). C'est l'attendu FIGE : le
#: balayage ci-dessous DERIVE l'ensemble reel et le confronte a celui-ci, dans les DEUX sens.
YIELDENT_EN_SPAWN = {
    "PsychicFortressNonOwnerPlaybook",       # aucun `case.unit` lu du tout
    "BookOfFateNonOwnerPlaybook",            # aucun `case.unit` lu du tout
    "MawClawsOfThyraxNonOwnerPlaybook",      # branche SPAWN explicite, sans le gate `Summon`
}

#: Les cles que le ctx de SPAWN ne doit JAMAIS porter : il n'y a PAS de sujet (`case.unit == null`),
#: et les fabriquer depuis le parent ferait mordre des gates que le natif laisse tomber.
CLES_DE_SUJET = ("uid", "self_pos", "unit_traits", "unit_faction", "unit_triggered_abilities",
                 "unit_active_abilities", "unit_parent_id")

POS = [(c, r) for c in range(3) for r in range(3)]


def _voisins(p):
    c, r = p
    return [q for q in POS if q != p and abs(q[0] - c) <= 1 and abs(q[1] - r) <= 1]


class _Board:
    """Stub minimal : `_board_maps` ne lit que `by_id`, `coord` et `neighbours_native`."""

    def __init__(self):
        self.by_id = {i: {"col": p[0], "row": p[1], "elevation": 1, "walkable": True}
                      for i, p in enumerate(POS)}

    def coord(self, tid):
        t = self.by_id[tid]
        return (t["col"], t["row"])

    def neighbours_native(self, tid):
        v = set(_voisins(self.coord(tid)))
        return [i for i, t in self.by_id.items() if (t["col"], t["row"]) in v]


class _Entity:
    def __init__(self, comps):
        self._c = {type(c): c for c in comps}

    def get_component(self, cls):
        return self._c.get(cls)


class _State:
    def __init__(self, entities):
        self.entities = entities
        self.board = _Board()
        self.effects = None

    def get_entity(self, uid):
        return self.entities.get(uid)


def _etat():
    """Parent (team 1) + un allie PORTEUR (team 1) + un ennemi (team 2), tous positionnes.

    Le porteur est `ultraTigurius` : son kit gameconfig porte `PsychicFortress` NATIVEMENT, donc
    `_unit_record` le trouve par le repli visualId sans qu'aucun `StatsComponent` soit monte."""
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    ent = {
        1: _Entity([PositionComponent(0, 0), OwnerComponent(1, 3),
                    UnitComponent("admecMarshall", True)]),
        2: _Entity([PositionComponent(1, 1), OwnerComponent(1, 3),
                    UnitComponent("ultraTigurius", True)]),
        3: _Entity([PositionComponent(2, 2), OwnerComponent(2, 4),
                    UnitComponent("worldKharn", True)]),
    }
    return _State(ent)


# ---------------------------------------------------------------------------------------------
# ETAGE 1 -- le SUBSTRAT : ce que le regime SPAWN publie, et ce qu'il refuse de publier
# ---------------------------------------------------------------------------------------------
def test_le_ctx_de_spawn_n_exclut_PAS_le_parent_la_ou_le_ctx_a_sujet_exclut_le_sujet():
    """LA difference de forme entre les deux regimes, et elle est LOAD-BEARING.

    Le natif ne saute le porteur que `if (case.unit != null && case.unit == ta.Owner)`. En SPAWN
    `case.unit` est nul : le PARENT est donc lui-meme un porteur candidat, et si son kit porte une
    ability du registre, ses tuiles adjacentes en recoivent le terme. Self-exclure le parent
    retirerait un terme que le natif verse -- sans erreur, sans test rouge."""
    from engine.utilities.tile import runner_tile_leaf_ctx
    st = _etat()
    spawn = runner_tile_leaf_ctx(st, None, 1)
    ids_spawn = {u["id"] for u in spawn["friend_units"]} | {u["id"] for u in spawn["enemy_units"]}
    assert ids_spawn == {1, 2, 3}, (
        "le ctx de SPAWN publie %r : le PARENT (1) doit y figurer, l'exclusion de self est "
        "desarmee quand `case.unit == null`" % sorted(ids_spawn)
    )
    sujet = runner_tile_leaf_ctx(st, 1, None)
    ids_sujet = {u["id"] for u in sujet["friend_units"]} | {u["id"] for u in sujet["enemy_units"]}
    assert ids_sujet == {2, 3}, (
        "le ctx a SUJET publie %r : le sujet (1) doit en etre EXCLU (`case.unit == ta.Owner "
        "=> continue`)" % sorted(ids_sujet))


def test_le_ctx_de_spawn_ne_porte_AUCUNE_cle_de_sujet():
    """`case.unit == null` : il n'y a pas de sujet. Fabriquer ses cles depuis le parent ferait
    mordre des gates (`HasTrait`, `HasFaction`, `GetParent`) que le natif laisse tomber -- et le
    ferait SILENCIEUSEMENT, puisque chaque gate rendrait simplement `True` au lieu de `False`."""
    from engine.utilities.tile import runner_tile_leaf_ctx
    spawn = runner_tile_leaf_ctx(_etat(), None, 1)
    presentes = [k for k in CLES_DE_SUJET if k in spawn]
    assert not presentes, (
        "le ctx de SPAWN porte des cles de sujet : %r. Il n'y a PAS de sujet dans ce regime" % presentes)
    assert spawn.get("is_spawning") is True
    for k in ("friend_units", "enemy_units", "elev_by_pos", "neigh_by_pos"):
        assert k in spawn, "le substrat du regime SPAWN ne porte pas `%s`" % k


def test_sans_parent_le_ctx_reste_VIDE():
    """`get_IsSpawning` = `unit == null && parent != null`. Ni sujet ni parent =>
    `EvaluateMovementInSteps` yielde `Fix64.Zero` : aucune feuille ne peut rien rendre."""
    from engine.utilities.tile import runner_tile_leaf_ctx
    assert runner_tile_leaf_ctx(_etat(), None, None) == {}


# ---------------------------------------------------------------------------------------------
# ETAGE 2 -- QUELLES classes yieldent, DERIVE puis confronte au decompile
# ---------------------------------------------------------------------------------------------
def _ctx_spawn(**over):
    base = {"is_spawning": True,
            "elev_by_pos": {p: 1 for p in POS},
            "neigh_by_pos": {p: _voisins(p) for p in POS},
            "walkable_by_pos": {p: True for p in POS}}
    base.update(over)
    return base


def test_les_classes_qui_yieldent_en_SPAWN_sont_EXACTEMENT_les_trois_lues_au_decompile():
    """Balayage DERIVE du registre : on n'ecrit pas la liste, on la MESURE puis on la confronte.

    Les deux sens comptent. Une classe de plus = un terme verse la ou le natif rend 0 (faute (b) de
    l'en-tete) ; une de moins = le terme perdu que ce cas repare (faute (a))."""
    from engine import weights as W
    from engine.playbook.non_owner import NON_OWNER_MOVE_PLAYBOOKS as REG
    wt = W.load()
    porteur = {"pos": (1, 1), "vis": "porteur", "id": 2, "triggered": tuple(sorted(REG)),
               "active": (), "traits": ("Hero",), "effects": ()}
    ctx = _ctx_spawn(friend_units=[porteur], enemy_units=[], friend_positions=[(1, 1)])
    vus = {type(pb).__name__ for pb in REG.values()
           if pb.calculate_movement_utility_in_steps((1, 0), porteur, True, ctx, wt)}
    assert vus == YIELDENT_EN_SPAWN, (
        "les classes qui yieldent en regime SPAWN ont change : mesure %r, decompile %r. En PLUS = "
        "un terme verse la ou le natif rend 0 ; en MOINS = un terme perdu sur la decision de spawn"
        % (sorted(vus), sorted(YIELDENT_EN_SPAWN)))


def test_la_feuille_4_verse_la_SOMME_des_trois_et_les_valeurs_viennent_du_gameconfig():
    """La somme est DERIVEE des trois cles BC, jamais ecrite en dur : un poids qui bouge doit
    changer l'attendu, pas faire rougir la garde pour la mauvaise raison."""
    from engine import weights as W
    from engine.playbook.non_owner import NON_OWNER_MOVE_PLAYBOOKS as REG
    from engine.utilities.tile import TILE_LEAVES
    from engine.utilities.utility_type import UtilityType as U
    wt = W.load()
    attendu = sum(float(wt.sub("TriggeredAbilitiesNonOwner", k)) for k in (
        "PSYCHICFORTRESS_AdjacentFriendly", "BookOfFate_AdjacentSummons",
        "MawClawsOfThyrax_AdjacentSummons"))
    assert attendu > 0, "les trois poids BC valent 0 : la mesure ne pourrait rien contredire"
    porteur = {"pos": (1, 1), "vis": "porteur", "id": 2, "triggered": tuple(sorted(REG)),
               "active": (), "traits": ("Hero",), "effects": ()}
    leaf = TILE_LEAVES[int(U.TriggeredAbilitiesNonOwner)][1]
    meta = {"elevation": 1, "elevation_max": 1, "elevation_min": 1, "effects": []}
    ami = _ctx_spawn(friend_units=[porteur], enemy_units=[], friend_positions=[(1, 1)])
    assert leaf.evaluate((1, 0), meta, ami, wt) == pytest.approx(attendu)
    # tuile NON adjacente au porteur -> 0 (`IsAdjacentTo` / `AreEntitiesAdjacent`)
    loin = _ctx_spawn(friend_units=[porteur], enemy_units=[], friend_positions=[(1, 1)],
                      neigh_by_pos={p: [] for p in POS})
    assert leaf.evaluate((1, 0), meta, loin, wt) == 0.0
    # porteur ENNEMI du PARENT -> le pre-gate `<slot 4> || IsFriend` l'ecarte (les 3 ont slot4=false)
    enn = _ctx_spawn(friend_units=[], enemy_units=[porteur], friend_positions=[])
    assert leaf.evaluate((1, 0), meta, enn, wt) == 0.0, (
        "un porteur ENNEMI du parent verse son terme : le pre-gate `IsFriend` n'est pas applique "
        "au PARENT en regime SPAWN")


# ---------------------------------------------------------------------------------------------
# ETAGE 3 -- `MawClawsOfThyrax` : la seule classe a DEUX branches
# ---------------------------------------------------------------------------------------------
def test_mawclaws_la_branche_SPAWN_n_a_PAS_le_gate_Summon_mais_A_le_gate_ami():
    """Le natif :
        if (case.unit != null) { adjacent && HasTrait(case.unit, Summon) && AreFriends(...) }
        else { case.parent != null && adjacent && AreFriends(case.parent, owner, 0) }
    Recopier le gate `Summon` dans la branche SPAWN retirerait le terme (le ctx de spawn n'a AUCUN
    trait) ; l'oublier des DEUX cotes le verserait a des movers non-Summon."""
    from engine import weights as W
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.playbook.non_owner import MawClawsOfThyraxNonOwnerPlaybook as MC
    wt = W.load()
    pb, w = MC(), float(W.load().sub("TriggeredAbilitiesNonOwner", MC.KEY))
    owner = {"pos": (1, 1), "id": 2}
    spawn = _ctx_spawn()
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, spawn, wt) == pytest.approx(w), (
        "la branche SPAWN ne verse rien : elle n'a PAS le gate `Summon` du natif")
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, False, spawn, wt) == 0.0, (
        "la branche SPAWN verse a un porteur non ami : son `AreFriends(case.parent, owner)` manque")
    sujet = dict(spawn, is_spawning=False, unit_traits=())
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, sujet, wt) == 0.0, (
        "la branche SUJET verse a un mover NON `Summon` : son `HasTrait(case.unit, 0x2)` manque")
    sujet_smn = dict(spawn, is_spawning=False, unit_traits=(int(UnitTrait.Summon),))
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, sujet_smn,
                                                  wt) == pytest.approx(w)


def test_les_deux_gates_LOAD_BEARING_coupent_bien_en_SPAWN():
    """`KustomForceFieldReworked` et `ECogSupport` : leurs corps natifs sont gardes par
    `case.unit != null`. Le premier aurait verse un `+10` FANTOME (son `is_friend` est calcule sur
    le PARENT, donc vrai) ; le second tombait par ACCIDENT (absence de `unit_traits`)."""
    from engine import weights as W
    from engine.playbook.non_owner import (ECogSupportPlaybookNonOwnerPlaybook as EC,
                                           KustomForceFieldReworkedNonOwnerPlaybook as KFF)
    wt = W.load()
    owner = {"pos": (1, 1), "id": 2}
    spawn = _ctx_spawn()
    assert KFF().calculate_movement_utility_in_steps((1, 0), owner, True, spawn, wt) == 0.0
    assert EC().calculate_movement_utility_in_steps((1, 0), owner, True, spawn, wt) == 0.0
    # CONTRE-EPREUVE : hors SPAWN, les deux savent verser -- sinon le zero ci-dessus n'accuserait
    # pas le gate mais un corps inerte.
    hors = dict(spawn, is_spawning=False)
    assert KFF().calculate_movement_utility_in_steps((1, 0), owner, True, hors, wt) > 0, (
        "hors SPAWN `KustomForceFieldReworked` rend 0 : le zero du regime SPAWN n'accuse pas son "
        "gate, il accuse un corps qui ne verse jamais")


# ---------------------------------------------------------------------------------------------
# ETAGE 4 -- RAYON DE SOUFFLE : peupler le ctx de spawn ne reveille QUE la feuille 4
# ---------------------------------------------------------------------------------------------
def test_peupler_le_ctx_de_spawn_ne_change_QUE_la_feuille_4():
    """La decision qui autorise ce port. Le ctx de spawn est un foyer PARTAGE par les 29 feuilles
    de `Tile(7)` ; y ajouter des cles pourrait en reveiller d'autres, dans un regime dont personne
    n'a lu le corps natif. Mesure : sur toutes les feuilles portees x toutes les tuiles, une seule
    bouge. Si une autre se met a bouger, c'est qu'elle lit desormais ce substrat -- et il faut
    alors lire SON corps natif en regime SPAWN avant de la laisser faire."""
    from engine import weights as W
    from engine.utilities.tile import TILE_LEAVES, TILE_LEAF_IDS
    from engine.utilities.utility_type import UtilityType as U
    wt = W.load()
    porteur = {"pos": (1, 1), "vis": "ultraTigurius", "id": 2,
               "triggered": (1000, 1461, 1469), "active": (),
               "traits": ("Hero", "Psyker", "Mechanical", "Summon", "Steppable"), "effects": ()}
    avant = {"is_spawning": True}
    apres = _ctx_spawn(friend_units=[porteur], enemy_units=[], friend_positions=[(1, 1)])
    bougent, evaluees = set(), 0
    for uid in TILE_LEAF_IDS:
        nom, leaf = TILE_LEAVES[uid]
        if leaf is None:
            continue
        evaluees += 1
        for p in POS:
            meta = {"elevation": 1, "elevation_max": 1, "elevation_min": 1, "effects": [],
                    "is_territory": True}
            if leaf.evaluate(p, meta, dict(avant), wt) != leaf.evaluate(p, meta, dict(apres), wt):
                bougent.add(nom)
    assert evaluees >= 25, (
        "%d feuilles seulement evaluees : le balayage ne couvre plus le composite, et un rayon "
        "de souffle mesure sur trois feuilles ne prouve rien" % evaluees)
    assert bougent == {TILE_LEAVES[int(U.TriggeredAbilitiesNonOwner)][0]}, (
        "le substrat du regime SPAWN reveille %r. Seule la feuille 4 doit bouger : toute autre "
        "feuille qui change agit dans un regime dont le corps natif n'a pas ete lu" % sorted(bougent))
