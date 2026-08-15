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
#: Les QUATRE corps dont la RE est faite et le mirror LIVRE, mais qui restent VOLONTAIREMENT hors
#: registre : leur porteur est une MACHINE OF WAR, que le dispatcher ne voit pas. Les inscrire
#: serait le patron #419 (porte mais non cable). Litteral du `.ctor` LU un par un
#: (`<Classe>$$.ctor` -> `..._ctor(this, <lit>, ...)`), jamais deduit du nom.
HORS_REGISTRE_ETAGE = {
    "CabalOfSorcerersPlaybook": (0x5d8, "MOVE"),            # 1496, thousDaemonPrince
    "WisdomOfTheAncientsPlaybook": (0x5ab, "MOVE"),         # 1451, ultraDreadnought
    "MastersOfManoeuvreNonOwnerPlaybook": (0x5e4, "MOVE"),  # 1508, darkaStormSpeeder
    "ShieldOfFaithNonOwnerPlaybook": (0x5ad, "ATTACK"),     # 1453, adeptExorcist
}

#: Le SEUL concret des 28 qui n'a AUCUNE classe portee, et pourquoi -- son porteur est une unite
#: NORMALE (`astraDreir`, relique equipable), donc son blocage n'est PAS celui des quatre ci-dessus.
SANS_CLASSE = {"SabreOfSacrificeNonOwnerPlaybook": (0x5c6, "MOVE", "arbre DSL + visualId du mover")}

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
# LES CLES REELLEMENT PRODUITES par les trois `*_leaf_ctx` -- MESUREES, jamais grepees.
#
# ⚠ CE POINT A ETE PAYE PAR UNE CONTRE-EPREUVE MUETTE. La premiere version de ce fichier cherchait
# la sous-chaine `'"scene"'` dans `inspect.getsource(tile_leaf_ctx)`. Retirer la CLE `"scene"` du
# dict retourne laissait la garde VERTE, parce que la ligne `_scene = getattr(ctx, "scene", None)`
# porte la meme sous-chaine dix lignes plus haut. Un grep de source mesure le TEXTE, pas le
# CONTRAT : on EXECUTE les trois constructeurs et on lit les cles du dict rendu.
# --------------------------------------------------------------------------------------------
class _SceneStub:
    """Duck-type minimal de `Scene` : uniquement ce que les deux jumeaux de prediction lisent."""
    units: list = []
    vis_by_id: dict = {}
    eff_state = None
    board = None
    elev_by_pos: dict = {}
    hpmax_by_id: dict = {}

    def team(self, _uid):
        return 1

    def ctx(self, _uid):
        return None

    def hp(self, _uid):
        return None

    def hpmax(self, _uid):
        return None

    def parent(self, _uid):
        return None

    def pos(self, _uid):
        return (0, 0)


class _DecisionCtxStub:
    """Duck-type minimal d'`AiDecisionContext` pour `tile_leaf_ctx`."""

    def __init__(self):
        self.me = {"visualId": "astraDreir", "pos": {"col": 0, "row": 0}, "hp": 10, "effects": []}
        self.uid = 1
        self.scene = _SceneStub()
        self.fpos = []
        self.units = []
        self.enemies = []
        self.elev_by_pos = {p: 1 for p in POS}
        self.neigh_by_pos = {p: _voisins(p) for p in POS}
        self.walkable_by_pos = {p: True for p in POS}
        self.is_territory_by_pos = None
        self.tile_effect_type_ids_by_pos = None
        self.hpmax_by_id = {}
        self.ctrl = 1


def cles_produites() -> dict[str, set]:
    """`{nom du constructeur: set(cles du dict rendu)}` -- le CONTRAT, execute."""
    from engine.utilities.tile import (runner_tile_leaf_ctx, scene_tile_leaf_ctx, tile_leaf_ctx)
    return {"tile_leaf_ctx": set(tile_leaf_ctx(_DecisionCtxStub())),
            "scene_tile_leaf_ctx": set(scene_tile_leaf_ctx(_SceneStub(), 1)),
            "runner_tile_leaf_ctx": set(runner_tile_leaf_ctx(_etat_avec_machine(), 1, None))}


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


def test_un_seul_concret_sur_28_n_a_AUCUNE_classe_portee():
    """Les DEUX sens comptent. En MOINS = un port a ete livre et cette garde doit etre relue (les
    fiches et les comptes qu'elle porte sont a mettre a jour). En PLUS = un corps a QUITTE un
    registre ET son module, donc un terme d'utilite a disparu sans que rien d'autre ne le dise."""
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
    assert mesure == set(SANS_CLASSE), (
        "concrets sans aucune classe portee : mesure %r, attendu %r"
        % (sorted(mesure), sorted(SANS_CLASSE)))


def test_les_quatre_corps_a_porteur_MoW_sont_PORTES_mais_HORS_REGISTRE():
    """LE CRAN ANTI-#419, dans les DEUX sens.

    * la classe DOIT exister -- sinon la RE de cette tranche a ete perdue et le prochain lecteur
      re-accusera la rarete, comme les trois fiches l'ont fait ;
    * elle NE DOIT PAS etre au registre -- le dispatcher ne verra jamais son porteur (une MoW),
      donc l'inscrire ecrirait du code que rien n'itere. Le jour ou l'univers du dispatcher
      s'elargit, c'est `test_une_entite_SANS_position_...` qui rougit en premier et dit d'inscrire.

    Chaque classe porte AUSSI son `ABILITY_ID` (le litteral du `.ctor`), son `SLOT_4` et sa `FACE` :
    une entree au registre sans ces trois-la serait la meme regression silencieuse que
    `TARGETING_OPTIONS` absent."""
    from engine.playbook import non_owner as NO
    from engine.playbook import non_owner_attack as NOA
    modules = {"MOVE": NO, "ATTACK": NOA}
    registres = {"MOVE": NO.NON_OWNER_MOVE_PLAYBOOKS,
                 "ATTACK": NOA.NON_OWNER_ATTACK_PLAYBOOKS}
    for classe, (aid, face) in sorted(HORS_REGISTRE_ETAGE.items()):
        cls = getattr(modules[face], classe, None)
        assert cls is not None, (
            "la classe `%s` a disparu du port : la RE de #1036-r3 / #433-r4-r3-r1-r1 / #1024-r7 "
            "est perdue, et le prochain lecteur re-accusera la rarete." % classe)
        assert cls.ABILITY_ID == aid, (
            "`%s.ABILITY_ID` = %r, litteral du `.ctor` LU = %r"
            % (classe, cls.ABILITY_ID, aid))
        assert cls.FACE == face, "`%s.FACE` = %r, TSV versionne = %r" % (classe, cls.FACE, face)
        assert cls.SLOT_4 is False, (
            "`%s.SLOT_4` vaut %r ; l'entree versionnee `metadata/non_owner_slot4.tsv` dit "
            "`declare=0 valeur=0`" % (classe, cls.SLOT_4))
        assert aid not in registres[face], (
            "`%s` (id %d) est ENTREE au registre %s. Son porteur est une MACHINE OF WAR, que le "
            "dispatcher ne voit pas : c'est du code que rien n'itere (patron #419). Si l'univers "
            "de porteurs s'est elargi, c'est `test_une_entite_SANS_position_...` qui doit rougir "
            "d'abord -- relire #1036-r3 avant de cabler." % (classe, aid, face))


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
def test_quatre_des_cinq_corps_ont_pour_porteur_une_MACHINE_OF_WAR_et_le_cinquieme_non():
    """La voie `mythicAbilities` designe les mythiques de MoW -- invisibles de toute autre voie
    (`case-323` Sec.2). C'est la moitie du diagnostic que les trois fiches avaient ratee.

    Le CINQUIEME (`SabreOfSacrifice`) doit rendre `non` : c'est ce qui etablit que son blocage est
    d'une AUTRE nature, et donc qu'elargir l'univers du dispatcher ne le debloquera PAS."""
    import probe_1036r3_porteurs_non_owner_restants as P
    from engine.entities.triggered_ability_type import TriggeredAbilityType as T
    attendu = {c: True for c in HORS_REGISTRE_ETAGE}
    attendu.update({c: False for c in SANS_CLASSE})
    mesure = {}
    for classe in attendu:
        aid = (HORS_REGISTRE_ETAGE.get(classe) or SANS_CLASSE[classe])[0]
        voies = P.porteurs_par_voie(T(aid).name)
        assert voies, "aucune voie d'attribution pour %s : le recenseur est muet" % classe
        mesure[classe] = P.VOIE_MOW in voies
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
    from engine.entities.unit_context import UnitContext
    assert "rarity" in getattr(UnitContext, "__dataclass_fields__", {}), (
        "`UnitContext.rarity` a disparu : le canal de rarete est retombe, relire #999-r3")
    cles = cles_produites()
    porteurs = sorted(n for n, k in cles.items() if "scene" in k)
    assert porteurs == ["scene_tile_leaf_ctx", "tile_leaf_ctx"], (
        "les constructeurs qui publient la cle `scene` sont %r (attendu les deux jumeaux de "
        "PREDICTION). En MOINS : la rarete redevient inatteignable depuis la face MOVE, donc le "
        "blocage change de nature. En PLUS : `runner_tile_leaf_ctx` l'a gagnee, et les quatre "
        "corps a porteur MoW deviennent portables sur les DEUX faces -- relire #1036-r3."
        % porteurs)


def test_le_canal_StaysOnTile_de_SabreOfSacrifice_existe_deja():
    """`UtilityMovementCase$$StaysOnTile(case, state)`, corps ENTIER :
    `GetMainTile(case.unit, state) == case.Position.MainTile`. La fiche de #433-r4-r3-r1-r1 le
    citait comme canal manquant ; c'est `tile == ctx["self_pos"]`, et les TROIS `*_leaf_ctx`
    publient `self_pos`. Ce qui manque a 1478 est ailleurs : le `visualId` du MOVER, et
    l'evaluateur DSL."""
    cles = cles_produites()
    sans = sorted(n for n, k in cles.items() if "self_pos" not in k)
    assert not sans, (
        "%r ne publie(nt) plus `self_pos` : le mirror de `StaysOnTile` redevient impossible" % sans)
    # Le manque REEL, fige lui aussi : aucun des trois ne publie le `visualId` du sujet. Le
    # discriminant est la CLE produite -- un nom quelconque qui porterait le visualId du mover
    # ferait tomber cette garde, et c'est voulu : c'est le signal que 1478 devient portable.
    avec_vis = sorted(n for n, k in cles.items()
                      if {"unit_vis", "unit_visual_id", "self_vis"} & k)
    assert not avec_vis, (
        "%r publie(nt) desormais le `visualId` du MOVER : le gate `IsUnitWithVisualId` de "
        "`SabreOfSacrifice` (1478) devient portable -- relire #433-r4-r3-r1-r1." % avec_vis)


# --------------------------------------------------------------------------------------------
# ETAGE 4 -- le RAYON DE SOUFFLE du geste manquant, pour que la tranche suivante parte informee
# --------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------
# ETAGE 5 -- LES QUATRE CORPS LIVRES, EXERCES GATE PAR GATE
#
# Une classe hors registre n'est jouee par AUCUN dispatcher : sans cet etage, les quatre mirrors
# seraient du code que rien n'execute, et une faute de port y dormirait jusqu'au jour du cablage.
# Chaque corps est donc exerce sur un ctx CRAFTE : un scenario POSITIF (tous les gates passent ->
# le poids BC du gameconfig VIVANT, jamais un scalaire ecrit ici) et un scenario par gate, ou UN
# SEUL predicat tombe.
# --------------------------------------------------------------------------------------------
class _UCtx:
    """Duck-type d'`UnitContext` reduit a ce que `_rarity_of` lit."""

    def __init__(self, rarity):
        self.rarity = rarity


class _SceneRarete:
    """`Scene` reduite au canal de rarete : `{uid: Rarity|None}`."""

    def __init__(self, par_uid):
        self._r = par_uid

    def ctx(self, uid):
        return _UCtx(self._r.get(uid)) if uid in self._r else None


def _ctx_move(rarites, mover_traits, friends, uid=1, faction=2):
    from engine.entities.traits.unit_trait import UnitTrait
    return {"is_spawning": False, "uid": uid, "self_pos": (0, 2),
            "unit_traits": tuple(int(UnitTrait[t]) for t in mover_traits),
            "unit_faction": faction, "unit_parent_id": None,
            "elev_by_pos": {p: 1 for p in POS},
            "neigh_by_pos": {p: _voisins(p) for p in POS},
            "walkable_by_pos": {p: True for p in POS},
            "friend_units": friends, "enemy_units": [], "friend_positions": [],
            "scene": _SceneRarete(rarites)}


def _ami(uid, pos, vis="astraDreir", traits=()):
    return {"id": uid, "pos": pos, "vis": vis, "traits": tuple(traits),
            "triggered": (), "active": (), "effects": (), "parent": None}


def test_CabalOfSorcerers_1496_verse_son_poids_et_chaque_gate_le_coupe():
    """`Mythic ET Psyker` sur le mover ; `Mythic ET Hero ET Psyker` sur un ami ADJACENT a la tuile
    candidate -- ou, a defaut, l'ami EST le porteur. Le poids est LU au gameconfig vivant."""
    from engine import weights as W
    from engine.entities.rarity import Rarity
    from engine.playbook.non_owner import CabalOfSorcerersPlaybook
    wt, pb = W.load(), CabalOfSorcerersPlaybook()
    attendu = float(wt.sub("TriggeredAbilitiesNonOwner", pb.KEY))
    assert attendu > 0, "le poids BC vaut 0 : la mesure ne pourrait rien contredire"
    owner = _ami(9, (2, 2))
    ok = _ctx_move({1: Rarity.Mythic, 2: Rarity.Mythic}, ("Psyker",),
                   [_ami(2, (1, 1), traits=("Hero", "Psyker"))])
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, ok, wt) == attendu
    # -- un gate a la fois, et un seul --------------------------------------------------------
    ko_mover_rarete = _ctx_move({1: Rarity.Legendary, 2: Rarity.Mythic}, ("Psyker",),
                                [_ami(2, (1, 1), traits=("Hero", "Psyker"))])
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, ko_mover_rarete, wt) == 0.0
    ko_mover_psyker = _ctx_move({1: Rarity.Mythic, 2: Rarity.Mythic}, ("Hero",),
                                [_ami(2, (1, 1), traits=("Hero", "Psyker"))])
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, ko_mover_psyker, wt) == 0.0
    ko_voisin_hero = _ctx_move({1: Rarity.Mythic, 2: Rarity.Mythic}, ("Psyker",),
                               [_ami(2, (1, 1), traits=("Psyker",))])
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, ko_voisin_hero, wt) == 0.0
    ko_voisin_rarete = _ctx_move({1: Rarity.Mythic, 2: Rarity.Common}, ("Psyker",),
                                 [_ami(2, (1, 1), traits=("Hero", "Psyker"))])
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, ko_voisin_rarete, wt) == 0.0
    # ADJACENCE : le meme ami pose HORS du voisinage de la tuile candidate (0,0) ne compte pas.
    ko_loin = _ctx_move({1: Rarity.Mythic, 2: Rarity.Mythic}, ("Psyker",),
                        [_ami(2, (2, 2), traits=("Hero", "Psyker"))])
    assert pb.calculate_movement_utility_in_steps((0, 0), owner, True, ko_loin, wt) == 0.0
    # CANAL MUET (`runner_tile_leaf_ctx`, qui ne publie pas `scene`) : le gate se TAIT.
    muet = dict(ok)
    muet.pop("scene")
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, muet, wt) == 0.0
    # SECONDE BRANCHE : un ami quelconque QUI EST LE PORTEUR suffit (`u == owner`).
    via_owner = _ctx_move({1: Rarity.Mythic, 9: Rarity.Common}, ("Psyker",),
                          [_ami(9, (1, 1))])
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, via_owner, wt) == attendu
    # SPAWN : `case.unit == null` -> yield break, quels que soient les voisins.
    spawn = dict(ok)
    spawn["is_spawning"] = True
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, spawn, wt) == 0.0


def test_WisdomOfTheAncients_1451_est_le_jumeau_de_1496_SANS_les_deux_gates_Psyker():
    """C'est la SEULE difference entre les deux corps, et transposer l'un depuis l'autre aurait
    ajoute deux filtres que le natif n'a pas. Le test le rend observable : le MEME montage sans
    aucun `Psyker` verse ici et rend 0 chez `CabalOfSorcerers`."""
    from engine import weights as W
    from engine.entities.rarity import Rarity
    from engine.playbook.non_owner import (CabalOfSorcerersPlaybook, WisdomOfTheAncientsPlaybook)
    wt = W.load()
    pb, jumeau = WisdomOfTheAncientsPlaybook(), CabalOfSorcerersPlaybook()
    attendu = float(wt.sub("TriggeredAbilitiesNonOwner", pb.KEY))
    assert attendu > 0, "le poids BC vaut 0 : la mesure ne pourrait rien contredire"
    owner = _ami(9, (2, 2))
    sans_psyker = _ctx_move({1: Rarity.Mythic, 2: Rarity.Mythic}, (),
                            [_ami(2, (1, 1), traits=("Hero",))])
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, sans_psyker, wt) == attendu
    assert jumeau.calculate_movement_utility_in_steps((1, 0), owner, True, sans_psyker, wt) == 0.0, (
        "`CabalOfSorcerersPlaybook` verse sur un montage SANS Psyker : ses deux gates `0x3ea` ont "
        "disparu, ou les deux corps ont ete transposes l'un depuis l'autre")
    ko_voisin_hero = _ctx_move({1: Rarity.Mythic, 2: Rarity.Mythic}, (),
                               [_ami(2, (1, 1))])
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, ko_voisin_hero, wt) == 0.0
    ko_mover = _ctx_move({1: Rarity.Common, 2: Rarity.Mythic}, (),
                         [_ami(2, (1, 1), traits=("Hero",))])
    assert pb.calculate_movement_utility_in_steps((1, 0), owner, True, ko_mover, wt) == 0.0


def test_MastersOfManoeuvre_1508_gate_sur_DarkAngels_ET_Mythic_et_ne_lit_JAMAIS_le_porteur():
    """Le corps natif n'ecrit meme pas `owner` dans sa state machine. Le test l'exerce donc avec
    un `owner` VIDE : si le port s'etait mis a le lire, il rendrait 0 ou leverait."""
    from engine import weights as W
    from engine.entities.rarity import Rarity
    from engine.playbook.non_owner import MastersOfManoeuvreNonOwnerPlaybook
    wt, pb = W.load(), MastersOfManoeuvreNonOwnerPlaybook()
    attendu = float(wt.sub("TriggeredAbilitiesNonOwner", pb.KEY))
    assert attendu > 0, "le poids BC vaut 0 : la mesure ne pourrait rien contredire"
    from engine.entities.unit_faction import faction_value
    assert faction_value("darkaBossLion") == int(pb.FACTION), (
        "`darkaBossLion` n'est plus DarkAngels au gameconfig : le montage a perdu son levier")
    da = _ami(2, (1, 1), vis="darkaBossLion")
    ok = _ctx_move({1: Rarity.Mythic, 2: Rarity.Mythic}, (), [da])
    # `owner` VIDE -- le corps natif ne le lit jamais.
    assert pb.calculate_movement_utility_in_steps((1, 0), {}, True, ok, wt) == attendu
    ko_faction = _ctx_move({1: Rarity.Mythic, 2: Rarity.Mythic}, (),
                           [_ami(2, (1, 1), vis="astraDreir")])
    assert pb.calculate_movement_utility_in_steps((1, 0), {}, True, ko_faction, wt) == 0.0
    ko_rarete_voisin = _ctx_move({1: Rarity.Mythic, 2: Rarity.Epic}, (), [da])
    assert pb.calculate_movement_utility_in_steps((1, 0), {}, True, ko_rarete_voisin, wt) == 0.0
    ko_rarete_mover = _ctx_move({1: Rarity.Epic, 2: Rarity.Mythic}, (), [da])
    assert pb.calculate_movement_utility_in_steps((1, 0), {}, True, ko_rarete_mover, wt) == 0.0


def test_ShieldOfFaith_1453_gate_sur_la_rarete_du_CASTER_et_le_FEU_sur_la_tuile_de_la_CIBLE():
    """Les deux gates du corps ATTACK, plus le tri-etat : `TryGetComponent` en echec -> le natif
    CONTINUE (la comparaison de rarete est gardee par le succes de la resolution)."""
    from engine import weights as W
    from engine.entities.effect_type import EffectType
    from engine.entities.rarity import Rarity
    from engine.playbook.non_owner_attack import ShieldOfFaithNonOwnerPlaybook

    class _Sc(_SceneRarete):
        def __init__(self, rar, feu_en):
            super().__init__(rar)
            self.tile_effects_owned_by_pos = {(1, 1): [EffectType.Fire.name]} if feu_en else {}

        def pos(self, uid):
            return (1, 1) if uid == 7 else (0, 0)

    class _Ctx:
        def __init__(self, sc):
            self.scene = sc

    wt, pb = W.load(), ShieldOfFaithNonOwnerPlaybook()
    attendu = float(wt.sub("TriggeredAbilitiesNonOwner", pb.KEY))
    assert attendu > 0, "le poids BC vaut 0 : la mesure ne pourrait rien contredire"
    ok = _Ctx(_Sc({1: Rarity.Mythic}, True))
    assert pb.calculate_attack_utility_in_steps(ok, 1, (0, 0), 7, 9, False, wt) == attendu
    sans_feu = _Ctx(_Sc({1: Rarity.Mythic}, False))
    assert pb.calculate_attack_utility_in_steps(sans_feu, 1, (0, 0), 7, 9, False, wt) == 0.0
    caster_non_mythic = _Ctx(_Sc({1: Rarity.Legendary}, True))
    assert pb.calculate_attack_utility_in_steps(caster_non_mythic, 1, (0, 0), 7, 9, False, wt) == 0.0
    # `TryGetComponent` en ECHEC (aucun ctx pour ce caster) : le natif ne coupe PAS.
    canal_muet = _Ctx(_Sc({}, True))
    assert pb.calculate_attack_utility_in_steps(canal_muet, 1, (0, 0), 7, 9, False, wt) == attendu, (
        "le port coupe quand la rarete du caster n'est pas mesuree ; le natif, lui, garde le "
        "chemin (`if (TryGetComponent(..) && buc.Rarity != 5) yield break`)")


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
