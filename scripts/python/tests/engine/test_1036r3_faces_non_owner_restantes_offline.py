"""GARDE #1036-r3 / #433-r4-r3-r1-r1 / #433-r4-r3-r1-r2 -- les DERNIERS corps de la famille
`TriggeredAbilityNonOwnerPlaybook<T>`, leur COMPTE et la CAUSE REELLE de leur absence.

POURQUOI CE FICHIER EXISTE : LES TROIS FICHES DISAIENT FAUX
------------------------------------------------------------
  * `#433-r4-r3-r1-r1` annoncait **11** faces MOVE derivees DIRECTES non portees. Il en reste
    **QUATRE** : sept ont ete portees depuis (1457/1461/1495 par #477-r33, 1469/1526/1531 par
    #477-r35, 1064 par #477-r37) et personne n'a re-compte.
  * `#433-r4-r3-r1-r2` annoncait **3 faces ATTACK + 1 face REPAIR jamais portees**, et concluait
    << le port n'a donc pas de foyer pour eux : c'est un cablage a creer, pas une entree a
    ajouter >>. Le cablage EXISTE depuis #271-r4 et #271-r7 : les TROIS dispatchers sont portes et
    les TROIS registres aussi. Il reste **UN** corps ATTACK et **ZERO** corps REPAIR.
  * Le bloc de commentaire de `NON_OWNER_MOVE_PLAYBOOKS` accusait la **RARETE** (<< AUCUN canal
    `rarity` n'existe cote port ; le verrou est un CAPTEUR MANQUANT >>). Le canal existe depuis
    #1039 / #999-r3 (`UnitContext.rarity`) et il est ATTEIGNABLE depuis la face MOVE, dont deux des
    trois `*_leaf_ctx` publient `ctx["scene"]`.

LA CAUSE REELLE, MESUREE (`probe_1036r3_porteurs_non_owner_restants.py`)
-------------------------------------------------------------------------
QUATRE des cinq corps restants ont pour PORTEUR une **MACHINE OF WAR** (voie `mythicAbilities`) :
`CabalOfSorcerers` 1496 (`thousDaemonPrince`), `WisdomOfTheAncients` 1451 (`ultraDreadnought`),
`MastersOfManoeuvre` 1508 (`darkaStormSpeeder`), `ShieldOfFaith` 1453 (`adeptExorcist`).

Or l'univers de porteurs des dispatchers portes est bati sur des entites POSITIONNEES -- les trois
`*_leaf_ctx` exigent une position pour entrer une unite dans `friend_units`/`enemy_units`, et les
faces ATTACK/REPAIR iterent `Scene.units`, d'ou `decisionView` exclut les Machines par construction
(canal `.mows` SEPARE). Une MoW n'a AUCUNE tuile. Le natif, lui, itere
`abilityAndEffectCache.<slot 5>()`, c'est-a-dire TOUTES les `TriggeredAbility` de la bataille.

⚠ ET LES CORPS N'EXIGENT PAS LA POSITION DU PORTEUR -- c'est ce qui rend le diagnostic non trivial
et ce qui a fait accuser la rarete pendant trois tranches. `MastersOfManoeuvreNonOwnerPlaybook` ne
lit meme PAS `owner` (sa methode-usine ecrit `case @+0x20, playbook @+0x28` et laisse `+0x30` a
l'enumerateur) ; `CabalOfSorcersPlaybook` et `WisdomOfTheAncientsPlaybook` ne s'en servent que pour
un test d'IDENTITE (`u == owner`) A L'INTERIEUR de `GetAdjacentFriends(tile, case.unit)`, branche
de toute facon inatteignable pour un porteur sans tuile. Le blocage est donc **au-dessus** des
corps : c'est `engine/utilities/tile.py`, pas `engine/playbook/non_owner*.py`.

Le cinquieme, `SabreOfSacrifice` 1478, a un porteur NORMAL (`astraDreir`, relique equipable) et un
blocage DIFFERENT, lui aussi mal decrit par sa fiche : son gate est l'arbre DSL
`AreEqual(Parent(u), Owner) & IsUnitWithVisualId(u, GetStringConstant(unitId))` (#149), et le
`visualId` du MOVER n'est publie par AUCUN des trois `*_leaf_ctx`. En revanche
`UtilityMovementCase$$StaysOnTile`, que la fiche citait comme canal manquant, EST disponible :
son corps entier est `GetMainTile(case.unit) == case.Position.MainTile`, soit
`tile == ctx["self_pos"]`.

CE QUE CE FICHIER GARDE, ET SURTOUT QUAND IL ROUGIT
----------------------------------------------------
Il fige les comptes RE-DERIVES (jamais recopies) et il ROUGIT le jour ou l'etage tombe -- le jour
ou une entite sans position entre dans l'univers de porteurs du dispatcher. C'est CE jour-la qu'il
faut relire ces trois residus, et personne ne s'en souviendrait : le champ `BLOCAGE` d'une ligne de
backlog n'est jamais re-mesure.

ASCII only.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

#: Ce qui doit changer pour que cette garde puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # SOCLE COMMUN a tout fichier de test : la cascade des deux `conftest.py` et sa fermeture.
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # L'ETAGE ACCUSE : l'univers de porteurs des trois dispatchers, et les trois `*_leaf_ctx`.
        "scripts/python/engine/utilities/tile.py",
        # LES TROIS REGISTRES : un port livre demain doit faire bouger les comptes d'ici.
        "scripts/python/engine/playbook/non_owner.py",
        "scripts/python/engine/playbook/non_owner_attack.py",
        "scripts/python/engine/playbook/non_owner_repair.py",
        # LA SCENE : c'est elle qui separe `units` de `mows`, et elle qui porte `ctx(uid).rarity`.
        "scripts/python/engine/playbook/scene.py",
        "scripts/python/engine/entities/unit_context.py",
        # LE RECENSEUR de voies d'attribution : c'est lui qui dit « porteur MACHINE OF WAR ».
        "scripts/python/unit_map.py",
        # LE PROBE dont ce fichier fige les mesures.
        "scripts/python/probe_1036r3_porteurs_non_owner_restants.py",
        # ⚠ LARGE ET ASSUME : importer `engine.utilities.tile` tire la cascade du paquet `engine`.
        # Une liste feuille-a-feuille ne peut pas montrer le module qu'elle a oublie. Les DEUX
        # formes sont necessaires : `**/` exige un SEGMENT, donc `scripts/python/**/*.py` ne voit
        # PAS `scripts/python/gameconfig.py`.
        "scripts/python/*.py", "scripts/python/**/*.py",
        # HORS de `scripts/python/` : l'entree VERSIONNEE qui porte la ventilation par face, plus
        # le gameconfig d'ou sortent les voies d'attribution.
        "data/**", "frida/hooks/data/ability-names.ts",
    ),
    # La ventilation 24/3/1 et les voies d'attribution sont LUES dans les entrees du build : un
    # re-dump doit faire rougir cette garde plutot que la laisser figer un compte perime.
    "build": True,
    "toujours": False,
    "raison": (
        "Ce fichier fige un COMPTE (les corps de la famille non portes) et une CAUSE (le porteur "
        "est une MoW, hors de l'univers du dispatcher). Il ne peut changer de verdict que si un "
        "registre gagne une entree, si l'univers de porteurs de `utilities/tile.py` s'elargit, ou "
        "si le build re-dumpe change la ventilation par face ou les voies d'attribution."),
}

# --------------------------------------------------------------------------------------------
# L'ATTENDU, LU au decompile -- corps par corps, jamais deduit du nom de la classe.
# --------------------------------------------------------------------------------------------
#: Les cinq corps concrets de la famille qui ne sont dans AUCUN des trois registres, avec le
#: litteral que leur `.ctor` passe a sa base (LU : `<Classe>$$.ctor` -> `..._ctor(this, <lit>, ..)`)
#: et la CAUSE mesuree de leur absence.
RESTANTS = {
    # face MOVE
    "CabalOfSorcerersPlaybook": (0x5d8, "MOVE", "porteur MoW"),            # 1496
    "WisdomOfTheAncientsPlaybook": (0x5ab, "MOVE", "porteur MoW"),         # 1451
    "MastersOfManoeuvreNonOwnerPlaybook": (0x5e4, "MOVE", "porteur MoW"),  # 1508
    "SabreOfSacrificeNonOwnerPlaybook": (0x5c6, "MOVE", "arbre DSL + visualId du mover"),  # 1478
    # face ATTACK
    "ShieldOfFaithNonOwnerPlaybook": (0x5ad, "ATTACK", "porteur MoW"),     # 1453
}

#: La ventilation par FACE des 28 concrets. RE-DERIVEE du TSV versionne par les tests ; ecrite ici
#: pour que le TSV et le port ne puissent pas glisser ENSEMBLE sans que rien ne rougisse.
VENTILATION = {"MOVE": 24, "ATTACK": 3, "REPAIR": 1}

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


def _etat_avec_machine():
    """Un mover positionne, un allie positionne, et une MACHINE **sans `PositionComponent`**.

    C'est exactement ce que produit `snapshot._load_machines` : le natif
    (`AddMachineOperation$$Execute`) ne donne pas de position a une MoW, et le port non plus."""
    from engine.runner.components import OwnerComponent, PositionComponent, UnitComponent
    return _State({
        1: _Entity([PositionComponent(0, 0), OwnerComponent(1, 3),
                    UnitComponent("astraDreir", True)]),
        2: _Entity([PositionComponent(1, 1), OwnerComponent(1, 3),
                    UnitComponent("ultraTigurius", True)]),
        9: _Entity([OwnerComponent(1, 3), UnitComponent("thousDaemonPrince", True)]),
    })


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- le COMPTE, re-derive dans les DEUX sens
# --------------------------------------------------------------------------------------------
def test_la_ventilation_par_face_des_28_concrets_est_celle_de_l_entree_versionnee():
    """24 MOVE / 3 ATTACK / 1 REPAIR. Un re-dump qui deplacerait un corps d'une face a l'autre
    l'enverrait dans le mauvais COMPOSITE (`Tile(7)` / `Damage(35)` / `Repair(47)`) : c'est une
    faute silencieuse, jamais une erreur."""
    import probe_1036r3_porteurs_non_owner_restants as P
    tsv = P.lire_slot4_tsv()
    assert len(tsv) == 28, "la famille compte %d concrets au TSV, pas 28" % len(tsv)
    mesure = {}
    for r in tsv:
        mesure[r["face"]] = mesure.get(r["face"], 0) + 1
    assert mesure == VENTILATION, (
        "ventilation mesuree %r != %r. Un corps a change de FACE : il partirait dans le mauvais "
        "composite, sans erreur." % (mesure, VENTILATION))


def test_les_corps_non_portes_sont_EXACTEMENT_les_cinq_lus_au_decompile():
    """Les DEUX sens comptent. En MOINS = un port a ete livre et cette garde doit etre relue (les
    fiches et les comptes qu'elle porte sont a mettre a jour). En PLUS = un corps a QUITTE un
    registre, donc un terme d'utilite a disparu sans que rien d'autre ne le dise."""
    import probe_1036r3_porteurs_non_owner_restants as P
    par_face = {}
    for r in P.lire_slot4_tsv():
        par_face.setdefault(r["face"], set()).add(r["classe"])
    portees = P.classes_portees()
    hors_reg = {P.noyau(n) for n in P.PORTEES_HORS_REGISTRE}
    mesure = set()
    for face, classes in par_face.items():
        for c in classes:
            if P.noyau(c) not in (portees[face] | hors_reg):
                mesure.add(c)
    assert mesure, "aucun corps restant mesure : le balayage ne peut rien contredire"
    assert mesure == set(RESTANTS), (
        "corps non portes : mesure %r, attendu %r" % (sorted(mesure), sorted(RESTANTS)))


def test_les_faces_ATTACK_et_REPAIR_ont_bien_un_foyer_contrairement_a_ce_que_disait_la_fiche():
    """`#433-r4-r3-r1-r2` : << le port n'a pas de foyer pour eux : c'est un cablage a creer >>.
    REFUTE, et ce test le fige : les TROIS dispatchers ET les TROIS registres existent."""
    from engine.playbook import non_owner_attack as NOA
    from engine.playbook import non_owner_repair as NOR
    from engine.utilities.tile import TriggeredAbilitiesNonOwnerUtility as U
    for nom in ("evaluate", "evaluate_attack_in_steps", "evaluate_repair_in_steps"):
        assert callable(getattr(U, nom, None)), "le dispatcher n'a pas de face `%s`" % nom
    assert len(NOA.NON_OWNER_ATTACK_PLAYBOOKS) == 2, (
        "face ATTACK : %d entrees au registre (2 attendues : NoHidingFromTheWatchers, "
        "WayOfTheShortBlade)" % len(NOA.NON_OWNER_ATTACK_PLAYBOOKS))
    assert len(NOR.NON_OWNER_REPAIR_PLAYBOOKS) == 1, (
        "face REPAIR : %d entrees au registre (1 attendue : VoltagheistField)"
        % len(NOR.NON_OWNER_REPAIR_PLAYBOOKS))


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- la CAUSE : le porteur est une MoW, et la MoW n'entre pas dans l'univers
# --------------------------------------------------------------------------------------------
def test_quatre_des_cinq_corps_restants_ont_pour_porteur_une_MACHINE_OF_WAR():
    """La voie `mythicAbilities` designe les mythiques de MoW -- invisibles de toute autre voie
    (`case-323` Sec.2). C'est la moitie du diagnostic que les trois fiches avaient ratee."""
    import probe_1036r3_porteurs_non_owner_restants as P
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    mesure = {}
    for classe, (aid, _face, _cause) in RESTANTS.items():
        voies = P.porteurs_par_voie(T(aid).name)
        assert voies, "aucune voie d'attribution pour %s : le recenseur est muet" % classe
        mesure[classe] = P.VOIE_MOW in voies
    attendu = {c: (cause == "porteur MoW") for c, (_a, _f, cause) in RESTANTS.items()}
    assert mesure == attendu, (
        "nature du porteur : mesure %r, attendu %r" % (mesure, attendu))
    assert sum(mesure.values()) == 4, "attendu 4 porteurs MoW, mesure %d" % sum(mesure.values())


def test_une_entite_SANS_position_n_entre_PAS_dans_l_univers_de_porteurs_du_dispatcher():
    """LE CRAN. Ce test ROUGIT le jour ou l'etage tombe -- c'est-a-dire le jour ou les trois
    residus qu'il porte redeviennent traitables.

    Il n'asserte pas << c'est bien ainsi >> : il asserte << c'est ainsi AUJOURD'HUI >>. Quand
    quelqu'un elargira l'univers de porteurs (le pendant exact de ce que #999-r3-r1-r1 a fait pour
    les deux agregateurs d'aura), ce test tombera, et c'est le signal de relire #1036-r3,
    #433-r4-r3-r1-r1 et #1024-r7 -- pas de « reparer » ce test."""
    from engine.utilities.tile import runner_tile_leaf_ctx
    ctx = runner_tile_leaf_ctx(_etat_avec_machine(), 1, None)
    univers = ({u["id"] for u in ctx["friend_units"]}
               | {u["id"] for u in ctx["enemy_units"]})
    assert univers, "l'univers mesure est VIDE : le montage ne peut rien contredire"
    assert 2 in univers, "l'allie POSITIONNE (2) doit y figurer -- sinon c'est le montage qui casse"
    assert 9 not in univers, (
        "une entite SANS `PositionComponent` (id 9, la MACHINE) est entree dans l'univers de "
        "porteurs du dispatcher NonOwner. C'est le blocage `etage` de #1036-r3 / "
        "#433-r4-r3-r1-r1 / #1024-r7 qui TOMBE : relire ces trois residus et porter les quatre "
        "corps a porteur MoW, ne PAS relacher cette assertion.")


def test_les_faces_ATTACK_et_REPAIR_iterent_Scene_units_qui_exclut_les_Machines():
    """Meme cran, sur l'autre axe : `decisionView.units` ne contient JAMAIS de Machine (canal
    `.mows` separe, mirror d'`EntityExtensions$$IsMachine`). Les deux dispatchers scalaires
    iterent `sc.units` : une MoW porteuse n'y est donc jamais vue."""
    import inspect

    from engine.utilities.tile import TriggeredAbilitiesNonOwnerUtility as U
    for nom in ("evaluate_attack_in_steps", "evaluate_repair_in_steps"):
        src = inspect.getsource(getattr(U, nom))
        assert "sc.units" in src, (
            "`%s` n'itere plus `sc.units` : l'univers de porteurs de la face a change, donc le "
            "blocage `etage` de `ShieldOfFaith` (#1024-r7) est peut-etre tombe -- relire." % nom)


# --------------------------------------------------------------------------------------------
# ETAGE 3 -- ce que la fiche accusait A TORT : la RARETE, et le canal `StaysOnTile`
# --------------------------------------------------------------------------------------------
def test_le_canal_de_RARETE_existe_et_n_est_donc_PAS_le_blocage():
    """Le bloc de commentaire du registre disait << AUCUN canal `rarity` n'existe cote port [...]
    le verrou est un CAPTEUR MANQUANT >>. Il existe depuis #1039 / #999-r3, et deux des trois
    `*_leaf_ctx` publient `ctx["scene"]`, donc `scene.ctx(uid).rarity` est atteignable depuis la
    face MOVE. Re-accuser la rarete ferait chercher une fenetre de reinject pour rien."""
    import inspect

    from engine.entities.unit_context import UnitContext
    from engine.utilities import tile as TL
    assert "rarity" in getattr(UnitContext, "__dataclass_fields__", {}), (
        "`UnitContext.rarity` a disparu : le canal de rarete est retombe, relire #999-r3")
    porteurs_de_scene = [nom for nom, fn in (("tile_leaf_ctx", TL.tile_leaf_ctx),
                                             ("scene_tile_leaf_ctx", TL.scene_tile_leaf_ctx))
                         if '"scene"' in inspect.getsource(fn)]
    assert len(porteurs_de_scene) == 2, (
        "seuls %r publient `ctx['scene']` : la rarete redevient inatteignable depuis la face MOVE"
        % porteurs_de_scene)


def test_le_canal_StaysOnTile_de_SabreOfSacrifice_existe_deja():
    """`UtilityMovementCase$$StaysOnTile(case, state)`, corps ENTIER :
    `GetMainTile(case.unit, state) == case.Position.MainTile`. La fiche de #433-r4-r3-r1-r1 le
    citait comme canal manquant ; c'est `tile == ctx["self_pos"]`, et les TROIS `*_leaf_ctx`
    publient `self_pos`. Ce qui manque a 1478 est ailleurs : le `visualId` du MOVER, et
    l'evaluateur DSL."""
    import inspect

    from engine.utilities import tile as TL
    for nom, fn in (("tile_leaf_ctx", TL.tile_leaf_ctx),
                    ("scene_tile_leaf_ctx", TL.scene_tile_leaf_ctx),
                    ("runner_tile_leaf_ctx", TL.runner_tile_leaf_ctx)):
        assert '"self_pos"' in inspect.getsource(fn), (
            "`%s` ne publie plus `self_pos` : le mirror de `StaysOnTile` redevient impossible" % nom)
    # Le manque REEL, fige lui aussi : aucun des trois ne publie le `visualId` du sujet.
    manquant = [nom for nom, fn in (("tile_leaf_ctx", TL.tile_leaf_ctx),
                                    ("scene_tile_leaf_ctx", TL.scene_tile_leaf_ctx),
                                    ("runner_tile_leaf_ctx", TL.runner_tile_leaf_ctx))
                if '"unit_vis"' in inspect.getsource(fn)]
    assert not manquant, (
        "%r publie(nt) desormais le `visualId` du MOVER : le gate `IsUnitWithVisualId` de "
        "`SabreOfSacrifice` (1478) devient portable -- relire #433-r4-r3-r1-r1." % manquant)


# --------------------------------------------------------------------------------------------
# ETAGE 4 -- le RAYON DE SOUFFLE du geste manquant, pour que la tranche suivante parte informee
# --------------------------------------------------------------------------------------------
def test_un_seul_corps_deja_porte_reagit_a_un_porteur_SANS_position():
    """Elargir l'univers aux MoW ne peut REDISTRIBUER un terme existant que si un corps deja porte
    verse sur un porteur sans position. Mesure : **1 sur 19**, `NornCrownNonOwnerPlaybook` -- et
    c'est CORRECT, c'est le seul corps de la famille dont la methode-usine n'ecrit meme pas
    `owner` (il ne pese que le voisinage du MOVER). Son rayon REEL est nul : aucune MoW ne porte
    1495, qui est une relique de `tyranNeurothrope`.

    Ce test existe pour que la tranche qui fera le geste sache d'avance ce qu'elle deplace."""
    from engine import weights as W
    from engine.playbook import non_owner as NO
    wt = W.load()
    ctx = {"is_spawning": False, "uid": 1, "self_pos": (0, 0),
           "unit_traits": tuple(range(0, 3000)), "unit_faction": 10, "unit_parent_id": 2,
           "elev_by_pos": {p: 1 for p in POS},
           "neigh_by_pos": {p: _voisins(p) for p in POS},
           "walkable_by_pos": {p: True for p in POS},
           "friend_units": [], "enemy_units": [], "friend_positions": []}
    owner = {"id": 2, "vis": "thousDaemonPrince", "triggered": (), "active": (),
             "traits": (), "effects": (), "parent": None}
    bavards = set()
    for pb in NO.NON_OWNER_MOVE_PLAYBOOKS.values():
        if pb.calculate_movement_utility_in_steps((1, 0), owner, True, ctx, wt):
            bavards.add(type(pb).__name__)
    assert len(NO.NON_OWNER_MOVE_PLAYBOOKS) >= 19, (
        "le registre MOVE est tombe a %d entrees" % len(NO.NON_OWNER_MOVE_PLAYBOOKS))
    assert bavards == {"NornCrownNonOwnerPlaybook"}, (
        "les corps qui versent sur un porteur SANS position ont change : %r. Chacun d'eux est un "
        "terme que l'elargissement de l'univers redistribuerait -- relire le rayon de souffle "
        "avant de faire le geste." % sorted(bavards))
