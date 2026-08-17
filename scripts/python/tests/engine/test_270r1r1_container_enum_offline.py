"""#270-r1-r1 + #270-r3 -- GARDE : les litteraux en position ELEMENT DE CONTENEUR sont des
MEMBRES d'enum, et les huit cles restees sous le SEUIL de la couverture de dict aussi.

CE QUI DISTINGUE CETTE TRANCHE DES DEUX VOLETS PRECEDENTS.

Les volets 1 et 2 de #270-r1 portaient sur des CLES DE DICT -- un role que le recenseur visitait,
et pour lequel il existe un discriminant fort : la COUVERTURE du dict (si toutes les cles
appartiennent au meme enum, le dict EST clee par cet enum, quoi que le fichier importe). Ici il
n'y a pas de couverture de cle : un tuple n'a pas de cle. Le discriminant a donc ete, site par
site, le NOM deja ecrit au site (commentaire de fin de ligne, nom du handler, nom de la classe
consommatrice) ou le TYPE DECLARE lu dans `data/symbols/<build>/frida/methods.tsv`.

DEUX ATTRIBUTIONS REPOSENT SUR UNE SIGNATURE LUE, PAS SUR UN NOM :
  * `IdunBattle.Utils.Hex.Edge` -- le type du parametre `direction` d'
    `IdunBattle.Utils.Hex.AxialCoordinate$$NeighbourAt`. C'est ce que portent les VALEURS de
    `_TRIANGLE_SHAPE_DIRECTIONS` et les deux listes de `DevastatingRefrainAbility$$GetShape`.
  * `IdunBattleLogic.Utils.Hex.Corner` -- le type du parametre de
    `BattleQuery$$GetTilesInTriangleShape`, donc de `spawn_tile_shape.DIRECTION_ORDER`.
Les deux ont un HOMONYME dans le build (`UnityEngine.RectTransform.Edge` a 4 valeurs ; cinq
`Corner` Unity/SimpleUI a 3 ou 4) : la cle d'appariement au registre est le nom PLEIN.

SIX ETAGES.

  * ETAGE 1 -- CLIQUET : chaque element est une instance de l'enum LU. Rougit si un ordinal nu
    revient, c.-a-d. si le gisement se rouvre par notre propre cadence.
  * ETAGE 2 -- ANTI-DEPLACEMENT : les couples (position, ordinal) mesures AVANT conversion sont
    toujours la. Pour un `frozenset` on fige l'ENSEMBLE trie ; pour un tuple, l'ORDRE -- il est
    OBSERVABLE (l'ordre des tests de `GetPathfinderTypeForUnit`, l'ordre des `Add` du cctor).
  * ETAGE 3 -- ACCESSEURS PUBLICS : les tables traversees par le chemin REEL des appelants,
    avec l'ordinal ET avec le membre, et avec anti-degenerescence (les reponses doivent
    DISCRIMINER, sans quoi l'egalite tiendrait meme sur une table melangee).
  * ETAGE 4 -- LA GARDE DEPORTEE de `services/static_battle_rules.py`. Ce fichier GARDE ses
    ordinaux : `engine/services/` est la couche que `entities/` et `runner/` importent tous deux,
    et l'import inverse leve un `ImportError` REEL (mesure). La protection est ici, sous forme
    d'egalite aux membres -- et le test TENTE l'import interdit pour que le compromis se
    RETOURNE tout seul le jour ou le cycle disparait.
  * ETAGE 5 -- BALAYAGE STATIQUE sur tout Python SUIVI : aucun site n'ecrit dans ces structures
    par un ordinal nu, et aucun des conteneurs convertis n'est reconstruit ailleurs a partir de
    litteraux. Il existe parce que les etages qui lisent APRES import ne voient jamais un probe
    que la passe ne joue pas (#455-r3).
  * ETAGE 6 -- LE REGISTRE : `Edge` est inscrit au registre de `probe_313`. Ce gisement s'est
    rouvert TROIS fois par notre propre cadence (`PathfinderType` #381-r5, `KillUnitStep`
    #389-r2, `DamageReason` #651) ; un mirror neuf hors registre en sort ORPHELIN.

CE QUI RESTE DELIBEREMENT EN LITTERAL, et c'est un RESULTAT, pas un oubli (l'etage 1 ne porte
donc PAS dessus) : `_CUBE_DIRECTIONS` (des deltas cubiques -- c'est son INDEX qui est un `Edge`),
`SUPPORTED_FEET_COUNTS` (1/3/7 = un COMPTE de tuiles), `NC_PRIORITY_TIERS` (des priorites),
`damage_config.DAMAGE_FIELDS` (des OFFSETS de struct), les slots d'`IAmountFormula` de
`triggered_ability.TRIGGERED_PREDICTION_AVERAGE_FORM`, et tous les `100` de pourcentage. Forcer
un nom sur un entier qui ne designe aucun enum est PIRE que l'ordinal, qui au moins ne ment pas.

100 % OFFLINE : aucun runner, aucune session Frida.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.ai import action_generators as AG  # noqa: E402
from engine.ai import state_bridge as SB  # noqa: E402
from engine.entities.abilities import active_ability as AA  # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.entities.effects import aura_selectors as ASel  # noqa: E402
from engine.entities.effects.loki import hits as HITS  # noqa: E402
from engine.entities.effects.loki import status as STATUS  # noqa: E402
from engine.entities.pathfinding import tile_blocking as TB  # noqa: E402
from engine.entities.pathfinding.pathfinders import PathfinderType  # noqa: E402
from engine.entities.selectors import geometry as GEO  # noqa: E402
from engine.entities import stats as ST  # noqa: E402
from engine.entities.stats import StatPart, StatType  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType  # noqa: E402
from engine.hex_corner import Corner  # noqa: E402
from engine.hex_edge import Edge  # noqa: E402
from engine.playbook.prediction import abilities as PA  # noqa: E402
from engine.runner.abilities import attack_type as AT  # noqa: E402
from engine.runner.abilities import base as RB  # noqa: E402
from engine.runner.abilities import sisterhood as SI  # noqa: E402
from engine.runner import components as RC  # noqa: E402
from engine.runner.operations.triggers.loki import fuelled_by_fury as FBF  # noqa: E402
from engine.services import movement_query as MQ  # noqa: E402
from engine.services import spawn_tile_shape as STS  # noqa: E402
from engine.services import static_battle_rules as SBR  # noqa: E402
from engine.utilities import tile as TU  # noqa: E402
import engine.predict as PR  # noqa: E402


# ─── SNAPSHOTS -- ordinaux mesures AVANT la conversion. `set` = ensemble TRIE ; `tuple` = ORDRE. ──
#
# La conversion a ete verifiee value-preserving par EMPREINTE sha256 des DEUX versions (41
# structures, relation `int(element) -> valeur` canonicalisee EN VALEUR, arbre de base extrait par
# `git archive` : 41/41 identiques). Ces snapshots figent le meme fait, mais DURABLEMENT.

SNAP_SETS = {
    # (structure vivante, enum attendu, ordinaux TRIES)
    "active_ability._A_VIA_GET_DAMAGE_AMOUNT_MAIN": (
        AA._A_VIA_GET_DAMAGE_AMOUNT_MAIN, ActiveAbilityType,
        (1004, 1006, 1008, 1014, 1017, 1022, 1026, 1027, 1035, 1041, 1042, 1056, 1062, 1065,
         1066, 1067, 1105, 1173)),
    "active_ability._A_VIA_STAFF_OF_STARS_GET_DAMAGE": (
        AA._A_VIA_STAFF_OF_STARS_GET_DAMAGE, ActiveAbilityType,
        (1069, 1073, 1074, 1078, 1111, 1132, 1147, 1177, 1204, 1207)),
    "active_ability._A_VIA_OWN_ABILITY_BODY": (
        AA._A_VIA_OWN_ABILITY_BODY, ActiveAbilityType,
        (1093, 1095, 1104, 1137, 1148, 1157)),
    "active_ability._A_INLINE_IN_PLAYBOOK": (
        AA._A_INLINE_IN_PLAYBOOK, ActiveAbilityType, (1044, 1100)),
    "active_ability._PREDICTION_MINMAX_RANDOM_READ": (
        AA._PREDICTION_MINMAX_RANDOM_READ, ActiveAbilityType,
        (1020, 1036, 1103, 1150, 1154, 1165, 1168, 1169, 1170, 1171, 1176, 1196, 1197, 1199,
         1202, 1222, 1225, 1227, 1230)),
    "runner/abilities/base.NO_END_TURN_ABILITY_TYPES": (
        RB.NO_END_TURN_ABILITY_TYPES, ActiveAbilityType,
        (1014, 1063, 1081, 1106, 1118, 1121, 1127, 1131, 1139, 1173, 1189, 1198, 1202, 1210)),
    "runner/abilities/base.NO_ABILITY_USED_FLAG_ABILITY_TYPES": (
        RB.NO_ABILITY_USED_FLAG_ABILITY_TYPES, ActiveAbilityType,
        (1014, 1077, 1081, 1106, 1118, 1127, 1131, 1139, 1173, 1189, 1198, 1202, 1210)),
    "runner/abilities/attack_type.REGULAR_ATTACK_ABILITY_TYPES": (
        AT.REGULAR_ATTACK_ABILITY_TYPES, ActiveAbilityType,
        (17, 69, 1030, 1046, 1076, 1086, 1114, 1120, 1123, 1126, 1128, 1138, 1146, 1162, 1178,
         1182, 1205, 1220)),
    "runner/abilities/attack_type.NOT_ACTIVE_ABILITY_TYPES": (
        AT.NOT_ACTIVE_ABILITY_TYPES, ActiveAbilityType, (18, 28, 1119, 1167, 1212)),
    "ai/state_bridge.HEAL_ABILITY_IDS": (
        SB.HEAL_ABILITY_IDS, ActiveAbilityType, (8, 18, 1167, 1212)),
    "ai/state_bridge.REPAIR_ABILITY_IDS": (
        SB.REPAIR_ABILITY_IDS, ActiveAbilityType, (28, 1119)),
    "entities/pathfinding/tile_blocking.TILE_MOVEMENT_BLOCKING_EFFECT_TYPES": (
        TB.TILE_MOVEMENT_BLOCKING_EFFECT_TYPES, EffectType, (0, 5, 17, 58, 94)),
    # #572-r3 : `20 NumberOfMembers` est la TROISIEME case du switch d'
    # `IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` qui va a
    # `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier` -- elle manquait.
    "entities/stats._FILLUP_STATS": (ST._FILLUP_STATS, StatType, (4, 5, 20)),
    "triggers/loki/fuelled_by_fury.ABILITY_COUNTED_ONCE_PER_BATTLE": (
        FBF.ABILITY_COUNTED_ONCE_PER_BATTLE, ActiveAbilityType, (1118, 1189)),
    "ai/action_generators._COMPARABLE_REPAIR_IDS": (
        AG._COMPARABLE_REPAIR_IDS, ActiveAbilityType, (28,)),
    "predict.CONFIG_HEAL_ABILITY_IDS": (
        PR.CONFIG_HEAL_ABILITY_IDS, ActiveAbilityType, (8,)),
    "utilities/tile.MasterOfTheTutelaries._TRAIT_GATE": (
        TU.MasterOfTheTutelaries_MoveTowardsTargetUtility._TRAIT_GATE, UnitTrait, (1019, 2026)),
}

SNAP_TUPLES = {
    # (structure vivante, enum attendu, ordinaux DANS L'ORDRE)
    "services/movement_query.SPECIAL_MOVEMENT_EFFECT_TYPES": (
        MQ.SPECIAL_MOVEMENT_EFFECT_TYPES, EffectType, (1035, 1140, 1238, 1573)),
    "runner/components._TELEPORT_MOVE_EFFECTS": (
        RC._TELEPORT_MOVE_EFFECTS, EffectType, (1036, 1035, 1241, 1238)),
    # 3 -> 5 : `1061 GeminaeSuperia_JustSummonedEffect` (#1074) et `1044 Untargetable`
    # (#433-r3-r2-r1). ⚠ Le premier des deux etait un ROUGE PREEXISTANT : #1074 a inscrit `1061`
    # au domaine sans mettre a jour CE snapshot, et l'etage 2 rougissait deja sur `master` avant
    # la presente tranche (mesure : meme test joue sur un `git archive` de l'arbre de depart).
    "entities/effects/aura_selectors.UNTARGETABLE_EFFECT_TYPES": (
        ASel.UNTARGETABLE_EFFECT_TYPES, EffectType, (1035, 1140, 1238, 1061, 1044)),
    "services/spawn_tile_shape.DIRECTION_ORDER": (
        STS.DIRECTION_ORDER, Corner, (1, 0, 5, 4, 3, 2)),
    "runner/abilities/sisterhood.SHAPE_DIRECTIONS_MACHINE": (
        SI.SHAPE_DIRECTIONS_MACHINE, Edge, (3, 1, 5)),
    "runner/abilities/sisterhood.SHAPE_DIRECTIONS_OTHER": (
        SI.SHAPE_DIRECTIONS_OTHER, Edge, (0, 2, 4)),
}

#: Les DICTS dont la conversion releve de #270-r3 (cles sous le seuil `>= 3`) ou dont les VALEURS
#: sont des membres (#270-r1-r1). `(dict, enum des CLES, {ordinal: ordinaux des valeurs})`.
SNAP_DICTS = {
    "entities/stats.STAT_CLAMP_MAX": (ST.STAT_CLAMP_MAX, StatType, {7: 100, 9: 100}),
    "entities/stats.STAT_CLAMP_MIN": (ST.STAT_CLAMP_MIN, StatType, {17: None}),
    "entities/effects/loki/status.ContagionsOfNurgle...CTOR_ARGS": (
        STATUS.ContagionsOfNurgleArmorReductionEffect.CTOR_ARGS, EffectType,
        {1071: ("contagionsOfNurgleArmorOneAura", 1, 1),
         1072: ("contagionsOfNurgleArmorTwoOrMoreAuras", 2, 0x7FFFFFFF)}),
    "playbook/prediction/abilities._MAKE_DMG_TARGET_GATE": (
        PA._MAKE_DMG_TARGET_GATE, ActiveAbilityType,
        {1148: "_daemonic_ordnance_target_gate", 1147: "_hades_autocannons_target_gate"}),
    # ⚠ Les VALEURS sont figees ICI, en ordinaux, et pas seulement lues dans la table : une
    # premiere version de l'etage 3 comparait `get_pathfinder_type_for_unit(...)` a la valeur
    # PRISE DANS CETTE MEME TABLE -- un echange walk/fly serait passe VERT. Un attendu qui se lit
    # dans l'objet teste ne teste rien.
    "services/movement_query.SPECIAL_MOVEMENT_PATHFINDER_TYPES": (
        MQ.SPECIAL_MOVEMENT_PATHFINDER_TYPES, EffectType,
        {1035: (6, 7), 1140: (8, 9), 1238: (10, 11), 1573: (12, 13)}),
}


def _en_ordinaux(v):
    """Canonicalise une valeur EN VALEUR : un `IntEnum` EST un `int`, donc `int(x)` est stable
    avant/apres conversion la ou `repr(x)` ne l'est pas. Descend dans les tuples."""
    if isinstance(v, tuple):
        return tuple(_en_ordinaux(x) for x in v)
    if isinstance(v, bool) or not isinstance(v, int):
        return v.__name__ if callable(v) else v
    return int(v)


def test_etage1_les_elements_sont_des_membres():
    """ETAGE 1 -- CLIQUET. Aucun ordinal nu ne subsiste, et aucun ne peut revenir.

    ROUGE si une entree est ajoutee plus tard sous forme d'entier (`1234,` au lieu de
    `ActiveAbilityType.X,`) : ce serait la reouverture du gisement, par notre propre cadence.
    C'est la meme forme de cliquet que `probe_181` pour les masques de ciblage.
    """
    fautives = {}
    for nom, (vivant, enum_attendu, _snap) in {**SNAP_SETS, **SNAP_TUPLES}.items():
        hors = [x for x in vivant if not isinstance(x, enum_attendu)]
        if hors:
            fautives[nom] = [(repr(x), type(x).__name__) for x in hors]
    for nom, (vivant, enum_cles, _snap) in SNAP_DICTS.items():
        hors = [k for k in vivant if not isinstance(k, enum_cles)]
        if hors:
            fautives[nom + " (cles)"] = [(repr(k), type(k).__name__) for k in hors]
    assert fautives == {}, (
        "ces elements ne sont pas des membres de leur enum -- un ordinal juste aujourd'hui "
        "devient FAUX au changement de build, en silence (regle CLAUDE.md) : %r" % fautives)


def test_etage1b_les_valeurs_typees_sont_des_membres():
    """ETAGE 1 (suite) -- les VALEURS converties, la ou elles designent au lieu de compter.

    Trois sites portent un enum en position de VALEUR, et deux d'entre eux portent un enum
    DIFFERENT de celui de leur cle -- c'est exactement ce que ces tables existent pour dire :

      * `_PREDICTION_FORMULA_ON_TRIGGERED_ABILITY` : cle `ActiveAbilityType`, valeur[1]
        `TriggeredAbilityType`. L'ordinal 1260 n'existe MEME PAS dans `ActiveAbilityType` ;
      * `SPECIAL_MOVEMENT_PATHFINDER_TYPES` : cle `EffectType`, valeurs `PathfinderType` ;
      * `_TRIANGLE_SHAPE_DIRECTIONS` : cle `Corner` (volet 2), valeurs `Edge` (ce volet-ci).
    """
    for cle, (_playbook, trig, _chaine) in AA._PREDICTION_FORMULA_ON_TRIGGERED_ABILITY.items():
        assert isinstance(cle, ActiveAbilityType), (
            "la cle de `_PREDICTION_FORMULA_ON_TRIGGERED_ABILITY` doit etre un ActiveAbilityType")
        assert isinstance(trig, TriggeredAbilityType), (
            "la valeur EVALUEE est un TriggeredAbilityType, pas un entier : %r" % (trig,))
    assert AA._PREDICTION_FORMULA_ON_TRIGGERED_ABILITY[ActiveAbilityType.HeavyRailRifle][1] \
        is TriggeredAbilityType.HeavyRailRifle_Attack
    # 1260 n'est PAS un ActiveAbilityType : c'est ce qui rend l'attribution non ambigue.
    try:
        ActiveAbilityType(1260)
        raise AssertionError("1260 est devenu un ActiveAbilityType -- relire l'attribution")
    except ValueError:
        pass

    for _eff, paire in MQ.SPECIAL_MOVEMENT_PATHFINDER_TYPES.items():
        assert all(isinstance(p, PathfinderType) for p in paire), (
            "les valeurs de SPECIAL_MOVEMENT_PATHFINDER_TYPES sont des PathfinderType : %r" % (paire,))
    for _coin, couple in GEO._TRIANGLE_SHAPE_DIRECTIONS.items():
        assert all(isinstance(e, Edge) for e in couple), (
            "les valeurs de _TRIANGLE_SHAPE_DIRECTIONS sont des Edge : %r" % (couple,))

    # Les deux cles composites de `hits` : un membre en position d'ELEMENT DE TUPLE.
    assert HITS.LET_THE_GALAXY_BURN_PERSISTENT_KEY[0] is TriggeredAbilityType.LetTheGalaxyBurn
    assert HITS.SWARM_HIT_REDUCTION_SOURCE[1] is EffectType.Swarm_HitReduction
    # ⚠ 1482 nomme AUTRE CHOSE en `EffectType` : l'ordinal ne tranchait pas, le nom si.
    assert int(EffectType(1482)) == 1482 and EffectType(1482).name != "LetTheGalaxyBurn"


def test_etage2_anti_deplacement():
    """ETAGE 2 -- chaque ordinal mesure avant la conversion est toujours la, a sa place.

    C'est ce test qui attrape « le bon nom en face du mauvais ordinal » -- le seul mode d'echec
    propre a une conversion de masse : il ne casse aucun import et ne leve rien.

    Sur-ensemble pour les SETS (une entree ajoutee plus tard passe sans re-figer le snapshot),
    EGALITE STRICTE pour les tuples : leur ordre EST la donnee (ordre des tests natifs, ordre des
    `List.Add` du cctor), donc un ajout doit faire relire le snapshot.
    """
    ecarts = {}
    for nom, (vivant, _enum, snap) in SNAP_SETS.items():
        actuel = tuple(sorted(int(x) for x in vivant))
        manquants = tuple(o for o in snap if o not in actuel)
        if manquants:
            ecarts[nom] = {"disparus": manquants, "actuel": actuel}
    for nom, (vivant, _enum, snap) in SNAP_TUPLES.items():
        actuel = tuple(int(x) for x in vivant)
        if actuel != snap:
            ecarts[nom] = {"attendu (ORDRE)": snap, "actuel": actuel}
    for nom, (vivant, _enum, snap) in SNAP_DICTS.items():
        actuel = {int(k): v for k, v in vivant.items()}
        for ordinal, attendu in snap.items():
            if ordinal not in actuel:
                ecarts.setdefault(nom, {})["cle disparue"] = ordinal
                continue
            obtenu = _en_ordinaux(actuel[ordinal])
            if obtenu != attendu:
                ecarts.setdefault(nom, {})[ordinal] = (attendu, obtenu)
    assert ecarts == {}, (
        "la conversion en membres d'enum n'est PAS value-preserving : %r" % ecarts)


def test_etage2b_cardinalites():
    """Le compte de la tranche : 23 conteneurs + 5 dicts, et personne n'a PERDU d'entree."""
    assert len(SNAP_SETS) == 17 and len(SNAP_TUPLES) == 6 and len(SNAP_DICTS) == 5
    total = sum(len(s) for _v, _e, s in SNAP_SETS.values()) \
        + sum(len(s) for _v, _e, s in SNAP_TUPLES.values()) \
        + sum(len(s) for _v, _e, s in SNAP_DICTS.values())
    # 157 -> 158 : `UNTARGETABLE_EFFECT_TYPES` gagne `1238 FearOfTheUnseen_TeleportingIn`
    # (#448-r2b-r1). 158 -> 159 : `_FILLUP_STATS` gagne `20 NumberOfMembers` (#572-r3, case LUE
    # dans le switch d'`ApplyStatModifier`). 159 -> 161 : le MEME conteneur gagne `1061` (#1074,
    # snapshot non mis a jour a l'epoque -- rouge PREEXISTANT) et `1044` (#433-r3-r2-r1). Le compte
    # MONTE quand une inscription est confrontee ; il ne doit jamais baisser en silence.
    assert total == 161, "le perimetre de la tranche a change de taille : %d" % total
    for nom, (vivant, _e, snap) in {**SNAP_SETS, **SNAP_TUPLES}.items():
        assert len(vivant) >= len(snap), (
            "%s a PERDU des entrees : %d vivantes pour %d au snapshot"
            % (nom, len(vivant), len(snap)))


def test_etage3_lookup_par_int_brut_et_accesseurs_publics():
    """ETAGE 3 -- la conversion traversee par le chemin REEL des appelants.

    `IntEnum` herite `__hash__`/`__eq__` d'`int`, donc `1230 in frozenset({ActiveAbilityType
    .SavageEchoes})` est VRAI. C'est ce qui rend la conversion transparente pour les ~40 sites qui
    interrogent ces tables avec un `int` brut -- on l'ATTESTE sur chaque element plutot que de le
    supposer, puis on passe par les accesseurs publics quand il en existe un.
    """
    for nom, (vivant, _enum, snap) in {**SNAP_SETS, **SNAP_TUPLES}.items():
        for ordinal in snap:
            assert ordinal in [int(x) for x in vivant] and ordinal in tuple(vivant), (
                "%s : `%d in <conteneur>` est faux apres conversion" % (nom, ordinal))

    # -- `attack_type` : les DEUX predicats natifs, avec l'ordinal ET le membre.
    for ordinal in SNAP_SETS["runner/abilities/attack_type.REGULAR_ATTACK_ABILITY_TYPES"][2]:
        assert AT.is_regular_attack(ordinal) is True
        assert AT.is_regular_attack(ActiveAbilityType(ordinal)) is True
        assert AT.is_active_ability(ordinal) is False, (
            "%d : une attaque REGULIERE ne peut pas etre une active ability" % ordinal)
    for ordinal in SNAP_SETS["runner/abilities/attack_type.NOT_ACTIVE_ABILITY_TYPES"][2]:
        assert AT.is_active_ability(ordinal) is False
        assert AT.is_active_ability(ActiveAbilityType(ordinal)) is False
    # anti-degenerescence : un accesseur qui rendrait toujours False passerait les lignes ci-dessus
    assert AT.is_active_ability(int(ActiveAbilityType.PlagueWind)) is True
    assert AT.is_regular_attack(int(ActiveAbilityType.PlagueWind)) is False

    # -- `movement_query.get_pathfinder_type_for_unit` : le FOYER unique du dispatch. On lui
    #    fabrique un `has_effect` par effet special et on verifie la valeur RENDUE, membre par
    #    membre, sur les deux branches (marche / vol).
    #    ⚠ L'attendu est le SNAPSHOT, jamais la table elle-meme (cf. la note sur SNAP_DICTS).
    attendu_pf = SNAP_DICTS["services/movement_query.SPECIAL_MOVEMENT_PATHFINDER_TYPES"][2]
    for eff, (walk, fly) in ((EffectType(o), p) for o, p in attendu_pf.items()):
        porte = (lambda cible: (lambda e: int(e) == int(cible)))(eff)
        assert MQ.get_pathfinder_type_for_unit(porte, []) == int(walk), (
            "%r : la branche MARCHE ne rend plus %d" % (eff, walk))
        assert MQ.get_pathfinder_type_for_unit(porte, ["Flying"]) == int(fly), (
            "%r : la branche VOL ne rend plus %d" % (eff, fly))
        # ignoreSpecialMovement -> retour au couple de base, jamais au pathfinder special
        assert MQ.get_pathfinder_type_for_unit(porte, [], True) == int(PathfinderType.Walk)
    assert MQ.get_pathfinder_type_for_unit(lambda e: False, []) == int(PathfinderType.Walk)
    assert MQ.get_pathfinder_type_for_unit(lambda e: False, ["Flying"]) == int(PathfinderType.Fly)
    # anti-degenerescence : les huit valeurs speciales sont DISTINCTES
    rendus = {int(x) for paire in MQ.SPECIAL_MOVEMENT_PATHFINDER_TYPES.values() for x in paire}
    assert len(rendus) == 8, "les 8 PathfinderType speciaux ne sont plus distincts : %r" % rendus

    # -- `tile_blocking.tile_blocks_entering` : le set converti est le gate de blocage. On pose un
    #    effet par type et on exige le blocage ; un type HORS set ne doit PAS bloquer.
    class _Eff:
        def __init__(self, et):
            self.effect_type, self.source, self.consumed = et, None, False

    class _Etat:
        def __init__(self, effets):
            self.by_unit = {77: effets}

    for eff in TB.TILE_MOVEMENT_BLOCKING_EFFECT_TYPES:
        assert TB.tile_blocks_entering(_Etat([_Eff(int(eff))]), 77) is True, (
            "%r ne bloque plus" % (eff,))
    assert TB.tile_blocks_entering(
        _Etat([_Eff(int(EffectType.Markerlight_Visual))]), 77) is False, (
        "un effet HORS du set bloque -- le gate ne discrimine plus")
    # l'exemption reste branchee : Mounted traverse Fire/Ice/BlockEnteringUnits, pas la LandMine
    assert TB.tile_blocks_entering(_Etat([_Eff(int(EffectType.Fire))]), 77, ["Mounted"]) is False
    assert TB.tile_blocks_entering(
        _Etat([_Eff(int(EffectType.LandMine_BlockTileMovement))]), 77, ["Mounted"]) is True

    # -- `static_battle_rules.is_tile_status_effect` (le set NON converti, cf. etage 4)
    for eff in (EffectType.Darkness, EffectType.Fire, EffectType.Ice,
                EffectType.Contaminated, EffectType.DespoiledGround):
        assert SBR.is_tile_status_effect(int(eff)) is True
        assert SBR.is_tile_status_effect(eff) is True
    assert SBR.is_tile_status_effect(int(EffectType.Markerlight_Visual)) is False

    # -- `spawn_tile_shape.DIRECTION_ORDER` : les six coins sont DISTINCTS et couvrent l'enum.
    assert set(map(int, STS.DIRECTION_ORDER)) == set(map(int, Corner))

    # -- `sisterhood` : les deux listes de directions PARTITIONNENT les six aretes (le natif
    #    bombarde trois hexes d'un cote, trois de l'autre -- aucun recouvrement).
    m, o = set(map(int, SI.SHAPE_DIRECTIONS_MACHINE)), set(map(int, SI.SHAPE_DIRECTIONS_OTHER))
    assert m & o == set() and m | o == set(map(int, Edge))

    # -- `_TRIANGLE_SHAPE_DIRECTIONS` : chaque coin est encadre par SES deux aretes, et le couple
    #    est celui du switch natif. C'est la 3e source (geometrique) de l'attribution `Edge`.
    attendu = {Corner.NorthWest: (Edge.North_West, Edge.North),
               Corner.NorthEast: (Edge.North, Edge.North_East),
               Corner.West: (Edge.North_West, Edge.South_West),
               Corner.East: (Edge.North_East, Edge.South_East),
               Corner.SouthWest: (Edge.South_West, Edge.South),
               Corner.SouthEast: (Edge.South, Edge.South_East)}
    assert GEO._TRIANGLE_SHAPE_DIRECTIONS == attendu
    # chaque arete apparait exactement DEUX fois (chaque arete separe deux coins)
    from collections import Counter
    compte = Counter(e for couple in GEO._TRIANGLE_SHAPE_DIRECTIONS.values() for e in couple)
    assert set(compte.values()) == {2}, "l'appariement coin/aretes n'est plus une partition : %r" % compte

    # -- `stats` : les deux `StatPart` du tuple converti sont bien la voie « total des mods ».
    sc = ST.StatComponent(initial=10)
    sc.modification.modify("s", 7)
    assert sc.get_stat_part(int(StatPart.MODIFICATION)) == 7
    assert sc.get_stat_part(StatPart.MULTIPLIER_MODIFICATION) == 7
    assert sc.get_stat_part(int(StatPart.INITIAL)) == 10, "la branche INITIAL a change de sens"
    # anti-degenerescence : la branche « total des mods » DIFFERE des autres parts
    assert sc.get_stat_part(int(StatPart.CURRENT)) == 17
    # contribution PAR SOURCE, l'autre voie du meme tuple de `StatPart`
    assert sc.get_stat_part(StatPart.MODIFICATION, source="s") == 7
    assert sc.get_stat_part(StatPart.MULTIPLIER_MODIFICATION, source="autre") == 0

    # -- `stats` : les clamps convertis sont EFFECTIVEMENT appliques (cle = membre, lue par int).
    assert ST.STAT_CLAMP_MAX[int(StatType.BLOCK_CHANCE)] == 100
    assert ST._stat_min(int(StatType.EXTRA_HITS)) is None, (
        "EXTRA_HITS doit rester SANS plancher (#60) -- la cle convertie n'est plus lue")
    assert ST._stat_min(int(StatType.ATTACK)) == 0

    # -- `status` : la FENETRE d'aura resolue par le type d'effet converti.
    _CN = STATUS.ContagionsOfNurgleArmorReductionEffect
    fenetres = set()
    for eff, (_cst, mini, maxi) in _CN.CTOR_ARGS.items():
        e = _CN(name="ContagionsOfNurgle_ArmorReduction", effect_type=int(eff))
        assert e.aura_amount_window() == (mini, maxi), (
            "%r : la fenetre d'aura n'est plus resolue par le type converti" % (eff,))
        fenetres.add((mini, maxi))
    assert len(fenetres) == 2, "les deux fenetres doivent DIFFERER : %r" % fenetres
    hors = _CN(name="x", effect_type=int(EffectType.Fire))
    assert hors.aura_amount_window() is None, "un type hors table doit rendre None"


def test_etage4_static_battle_rules_membres_et_place_des_imports():
    """ETAGE 4 -- `services/static_battle_rules.py` : les membres sont ECRITS AU SITE, et la
    contrainte de PLACEMENT qui l'imposait A DISPARU -- l'etage s'est RETOURNE, comme prevu.

    CE QU'IL GARDAIT (#270-r4-r2). La boucle
        services.static_battle_rules -> engine.entities (init) -> effects_state -> effects
        -> factory -> effects.loki -> hits.py -> `from ....services.static_battle_rules import
           TILE_STATUS_EFFECT_NAMES`
    ne lisait QU'UN symbole de ce module ; il suffisait que les deux imports d'enum soient
    places APRES sa definition. Cet etage gardait cette place en MUTANT une copie du module
    (imports remontes en tete) et en exigeant l'`ImportError`.

    CE QUI L'A RETOURNE (#485-r1-r1) -- et la mesure, pas la supposition :
        `import engine.entities` charge  94 modules `engine.*` sur `origin/master`
                                          2 apres la vidange des barils
        `engine.entities.effects.loki.hits` charge : VRAI avant, FAUX apres
    La vidange a retire de l'`__init__` du paquet les re-exports qui tiraient tout l'arbre des
    effets : la boucle n'existe plus. Les deux imports sont donc REMONTES en tete du module, et
    l'etage mesure DESORMAIS L'INVERSE.

    ⚠ IL RESTE UN CRAN, ET C'EST LUI QUI COMPTE : un etage qui n'affirmerait plus rien serait
    du bruit. La contre-epreuve est CONSERVEE, retournee -- la copie mutee (imports en tete)
    doit s'importer SANS ERREUR, et la cascade du paquet doit rester COURTE. Le jour ou un
    `__init__` re-tirerait l'arbre des effets, cet etage rougirait a nouveau et la prescription
    de placement serait a retablir. Un acquis se garde ; il ne se declare pas.

    Le test garde donc TROIS choses :
      * les valeurs sont des MEMBRES (un renumerotage du build fait rougir) ;
      * les deux imports sont EN TETE (ecrits juste apres le preambule) ;
      * la copie mutee s'importe, et `import engine.entities` ne traine pas l'arbre des effets.
    """
    assert SBR.TILE_STATUS_EFFECT_TYPES == {EffectType.Darkness, EffectType.Fire,
                                            EffectType.Ice, EffectType.Contaminated,
                                            EffectType.DespoiledGround}
    assert SBR._MOVEMENT_BLOCKING_EFFECT_TYPES == {EffectType.BlockEnteringUnits,
                                                   EffectType.Fire, EffectType.Ice}
    assert SBR.BLOCK_ENTERING_UNITS_EFFECT_TYPE == EffectType.BlockEnteringUnits
    assert SBR._MOVEMENT_EXEMPT_TRAIT_IDS == (UnitTrait.Mounted, UnitTrait.Vehicle,
                                              UnitTrait.Unstoppable)
    assert SBR._DARKNESS_EXEMPT_TRAIT_IDS == (UnitTrait.NightVision,)
    # ⚠ ce sont bien des MEMBRES, pas des ints : `int == IntEnum` serait vrai des deux facons.
    for nom, lot in (("TILE_STATUS_EFFECT_TYPES", SBR.TILE_STATUS_EFFECT_TYPES),
                     ("_MOVEMENT_BLOCKING_EFFECT_TYPES", SBR._MOVEMENT_BLOCKING_EFFECT_TYPES)):
        assert lot, "%s est VIDE -- une assertion sur un ensemble vide passerait toute seule" % nom
        for v in lot:
            assert isinstance(v, EffectType), "%s porte un ordinal nu : %r" % (nom, v)
    for nom, lot in (("_MOVEMENT_EXEMPT_TRAIT_IDS", SBR._MOVEMENT_EXEMPT_TRAIT_IDS),
                     ("_DARKNESS_EXEMPT_TRAIT_IDS", SBR._DARKNESS_EXEMPT_TRAIT_IDS)):
        assert lot, "%s est VIDE" % nom
        for v in lot:
            assert isinstance(v, UnitTrait), "%s porte un ordinal nu : %r" % (nom, v)
    assert isinstance(SBR.BLOCK_ENTERING_UNITS_EFFECT_TYPE, EffectType)

    # le predicat rend bien ces traits-la, pour les types annonces
    assert SBR.not_blocking_movement_of_traits(int(EffectType.Fire)) \
        == SBR._MOVEMENT_EXEMPT_TRAIT_IDS
    assert SBR.not_blocking_movement_of_traits(int(EffectType.Darkness)) \
        == SBR._DARKNESS_EXEMPT_TRAIT_IDS
    assert SBR.not_blocking_movement_of_traits(int(EffectType.Markerlight_Visual)) == ()

    # ── LES DEUX IMPORTS SONT EN TETE, et la mutation qui les y remonte est un NO-OP ──────────
    # C'est le retournement de #485-r1-r1 : on MUTE toujours une copie (imports remontes juste
    # apres `from __future__`), mais on exige desormais que l'import PASSE. Si la boucle
    # revenait, cette copie mutee re-echouerait -- et l'etage redeviendrait la garde de
    # placement qu'il etait.
    import subprocess, shutil, tempfile, ast, os
    src = (PYDIR / "engine/services/static_battle_rules.py").read_text(encoding="utf-8")
    lignes = src.splitlines(keepends=True)
    a_deplacer = [l for l in lignes
                  if l.startswith("from ..entities.effect_type import")
                  or l.startswith("from ..entities.traits.unit_trait import")]
    assert len(a_deplacer) == 2, (
        "les deux imports d'enum ne sont plus ecrits au niveau module dans "
        "`static_battle_rules.py` -- la contre-epreuve ne mesure plus rien : %r" % a_deplacer)
    #: LA PLACE ELLE-MEME : ils doivent etre dans le PREAMBULE, avant toute definition. Sans ce
    #: cran, redescendre les imports sous `TILE_STATUS_EFFECT_NAMES` laisserait l'etage vert.
    i_prem_def = next(i for i, l in enumerate(lignes)
                      if l.startswith(("TILE_STATUS_EFFECT_NAMES", "W_LASCANNON_PIERCE_BONUS")))
    assert all(lignes.index(l) < i_prem_def for l in a_deplacer), (
        "les deux imports d'enum ne sont plus en TETE : la boucle d'import est-elle revenue ? "
        "Si oui, retablir la prescription de placement (#270-r4-r2) plutot que ce cran.")
    reste = [l for l in lignes if l not in a_deplacer]
    i_fut = next(i for i, l in enumerate(reste) if l.startswith("from __future__"))
    mute = "".join(reste[:i_fut + 1] + ["\n"] + a_deplacer + reste[i_fut + 1:])
    assert mute != src, "la mutation n'a pas mordu"

    with tempfile.TemporaryDirectory() as tmp:
        arbre = Path(tmp) / "arbre"
        shutil.copytree(PYDIR / "engine", arbre / "engine",
                        ignore=shutil.ignore_patterns("__pycache__"))
        for f in ("gameconfig.py", "hexgeo.py"):
            if (PYDIR / f).exists():
                shutil.copy2(PYDIR / f, arbre / f)
        (arbre / "engine/services/static_battle_rules.py").write_text(mute, encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(arbre) + os.pathsep + str(PYDIR))
        r = subprocess.run([sys.executable, "-c", "import engine.services.static_battle_rules"],
                           capture_output=True, text=True, cwd=str(arbre), env=env)
        #: LA CAUSE de la disparition, mesuree et non supposee : l'`__init__` du paquet ne tire
        #: plus l'arbre des effets. C'est CE fait qui a libere la place des imports -- le garder
        #: ici, c'est garder la RAISON, pas seulement son effet.
        r2 = subprocess.run(
            [sys.executable, "-c", "import sys, engine.entities; "
             "print(len([m for m in sys.modules if m.startswith('engine')])); "
             "print('engine.entities.effects.loki.hits' in sys.modules)"],
            capture_output=True, text=True, cwd=str(arbre), env=env)
    assert r.returncode == 0, (
        "LA CONTRAINTE DE PLACEMENT EST REVENUE : remonter les deux imports en tete casse a "
        "nouveau. Retablir la prescription de #270-r4-r2 (imports sous "
        "`TILE_STATUS_EFFECT_NAMES`) et re-retourner cet etage. stderr=%r" % r.stderr[-600:])
    assert r2.returncode == 0, "la sonde de cascade n'a pas abouti : %r" % r2.stderr[-400:]
    n_modules, hits_charge = r2.stdout.split()
    assert hits_charge == "False", (
        "`import engine.entities` re-tire `effects/loki/hits.py` -- la boucle qui imposait la "
        "place des imports est de retour (94 modules sur origin/master, 2 apres la vidange).")
    assert int(n_modules) < 20, (
        "`import engine.entities` charge %s modules `engine.*` : la cascade du paquet a "
        "re-enfle (2 a la vidange de #485-r1-r1, 94 avant). C'est le terrain sur lequel les "
        "cycles repoussent." % n_modules)


#: Les structures de cette tranche, par leur NOM tel qu'il s'ecrirait a un site de mutation.
_STRUCTURES = (
    "_A_VIA_GET_DAMAGE_AMOUNT_MAIN", "_A_VIA_STAFF_OF_STARS_GET_DAMAGE", "_A_VIA_OWN_ABILITY_BODY",
    "_A_INLINE_IN_PLAYBOOK", "_PREDICTION_MINMAX_RANDOM_READ",
    "_PREDICTION_FORMULA_ON_TRIGGERED_ABILITY",
    "NO_END_TURN_ABILITY_TYPES", "NO_ABILITY_USED_FLAG_ABILITY_TYPES",
    "REGULAR_ATTACK_ABILITY_TYPES", "NOT_ACTIVE_ABILITY_TYPES",
    "SPECIAL_MOVEMENT_EFFECT_TYPES", "SPECIAL_MOVEMENT_PATHFINDER_TYPES",
    "HEAL_ABILITY_IDS", "REPAIR_ABILITY_IDS", "TILE_MOVEMENT_BLOCKING_EFFECT_TYPES",
    "_FILLUP_STATS", "STAT_CLAMP_MAX", "STAT_CLAMP_MIN", "_TELEPORT_MOVE_EFFECTS",
    "UNTARGETABLE_EFFECT_TYPES", "ABILITY_COUNTED_ONCE_PER_BATTLE", "DIRECTION_ORDER",
    "SHAPE_DIRECTIONS_MACHINE", "SHAPE_DIRECTIONS_OTHER", "_COMPARABLE_REPAIR_IDS",
    "CONFIG_HEAL_ABILITY_IDS", "_TRAIT_GATE", "CTOR_ARGS", "_MAKE_DMG_TARGET_GATE",
    "LET_THE_GALAXY_BURN_PERSISTENT_KEY", "SWARM_HIT_REDUCTION_SOURCE",
)


def _designe_un_membre(noeud) -> bool:
    """L'expression designe-t-elle un MEMBRE d'enum plutot qu'un ordinal nu ?

    Refuse un litteral entier et `int(<Enum>.<Membre>)` -- `int()` DEGRADE le membre en ordinal.
    """
    import ast as _ast
    if isinstance(noeud, _ast.Constant):
        return not (isinstance(noeud.value, int) and not isinstance(noeud.value, bool))
    if isinstance(noeud, _ast.Call):
        f = noeud.func
        return not (isinstance(f, _ast.Name) and f.id == "int")
    if isinstance(noeud, _ast.UnaryOp):
        return _designe_un_membre(noeud.operand)
    return True


def test_etage5_balayage_statique_des_sites_de_mutation():
    """ETAGE 5 -- BALAYAGE STATIQUE : personne n'ecrit dans ces structures par un ordinal nu.

    POURQUOI IL EXISTE. Les quatre etages precedents lisent les structures APRES import ; un
    probe que la passe ne joue pas ne les touche jamais, donc une mutation qui vit dans un tel
    fichier reste VERTE. C'est mot pour mot #455-r3 : le runtime ne voit que ce qu'une passe JOUE.
    A #652 ce meme etage avait trouve DEUX sites de mutation (`TABLE[X] = ...`) que le grep avait
    manques.

    Il rougit sur `<STRUCTURE>[<litteral>] = ...`, sur `<STRUCTURE>.pop/.setdefault(<litteral>)`,
    et sur `<STRUCTURE> = frozenset({<litteral>, ...})` / `= (<litteral>, ...)` REDEFINI ailleurs
    que dans son fichier d'origine (le cas « quelqu'un a recopie la table »).

    NE COUVRE PAS -- dit plutot que maquille : `update(<dict construit ailleurs>)` et les
    constructions dont les elements ne sont pas des litteraux au site.
    """
    import ast
    import subprocess

    r = subprocess.run(["git", "ls-files", "scripts/python"],
                       cwd=str(PYDIR.parents[1]), capture_output=True, text=True)
    assert r.returncode == 0, "git ls-files a echoue : le balayage ne mesurerait RIEN"
    fichiers = [f for f in r.stdout.split() if f.endswith(".py")]
    assert len(fichiers) > 300, "perimetre suspect (%d fichiers) -- un zero rassurant" % len(fichiers)

    #: fichier d'ORIGINE de chaque structure -- une (re)definition ailleurs est le signal.
    origines = {
        "_A_VIA_GET_DAMAGE_AMOUNT_MAIN": "active_ability.py",
        "_A_VIA_STAFF_OF_STARS_GET_DAMAGE": "active_ability.py",
        "_A_VIA_OWN_ABILITY_BODY": "active_ability.py",
        "_A_INLINE_IN_PLAYBOOK": "active_ability.py",
        "_PREDICTION_MINMAX_RANDOM_READ": "active_ability.py",
        "_PREDICTION_FORMULA_ON_TRIGGERED_ABILITY": "active_ability.py",
        "NO_END_TURN_ABILITY_TYPES": "base.py", "NO_ABILITY_USED_FLAG_ABILITY_TYPES": "base.py",
        "REGULAR_ATTACK_ABILITY_TYPES": "attack_type.py", "NOT_ACTIVE_ABILITY_TYPES": "attack_type.py",
        "SPECIAL_MOVEMENT_EFFECT_TYPES": "movement_query.py",
        "SPECIAL_MOVEMENT_PATHFINDER_TYPES": "movement_query.py",
        "HEAL_ABILITY_IDS": "state_bridge.py", "REPAIR_ABILITY_IDS": "state_bridge.py",
        "TILE_MOVEMENT_BLOCKING_EFFECT_TYPES": "tile_blocking.py",
        "_FILLUP_STATS": "stats.py", "STAT_CLAMP_MAX": "stats.py", "STAT_CLAMP_MIN": "stats.py",
        "_TELEPORT_MOVE_EFFECTS": "components.py",
        "UNTARGETABLE_EFFECT_TYPES": "aura_selectors.py",
        "ABILITY_COUNTED_ONCE_PER_BATTLE": "fuelled_by_fury.py",
        "DIRECTION_ORDER": "spawn_tile_shape.py",
        "SHAPE_DIRECTIONS_MACHINE": "sisterhood.py", "SHAPE_DIRECTIONS_OTHER": "sisterhood.py",
        "_COMPARABLE_REPAIR_IDS": "action_generators.py",
        "CONFIG_HEAL_ABILITY_IDS": "predict.py", "_TRAIT_GATE": "tile.py",
        "CTOR_ARGS": "status.py", "_MAKE_DMG_TARGET_GATE": "abilities.py",
        "LET_THE_GALAXY_BURN_PERSISTENT_KEY": "hits.py",
        "SWARM_HIT_REDUCTION_SOURCE": "hits.py",
    }

    fautifs = []
    for rel in fichiers:
        p = PYDIR.parents[1] / rel
        try:
            src = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not any(t in src for t in _STRUCTURES):
            continue
        try:
            arbre = ast.parse(src, filename=rel)
        except SyntaxError:
            continue

        def _nom(noeud):
            if isinstance(noeud, ast.Name) and noeud.id in _STRUCTURES:
                return noeud.id
            if isinstance(noeud, ast.Attribute) and noeud.attr in _STRUCTURES:
                return noeud.attr
            return None

        for n in ast.walk(arbre):
            if isinstance(n, ast.Assign):
                for cible in n.targets:
                    # <STRUCTURE>[idx] = ...
                    if isinstance(cible, ast.Subscript):
                        t = _nom(cible.value)
                        if t and not _designe_un_membre(cible.slice):
                            fautifs.append((rel, n.lineno, t, "ecriture par ordinal nu"))
                    # <STRUCTURE> = <collection de litteraux>, HORS de son fichier d'origine
                    t = _nom(cible)
                    if t and not rel.endswith(origines.get(t, "\0")):
                        elts = []
                        v = n.value
                        if isinstance(v, ast.Call) and v.args:
                            v = v.args[0]
                        if isinstance(v, (ast.Tuple, ast.List, ast.Set)):
                            elts = v.elts
                        elif isinstance(v, ast.Dict):
                            elts = [k for k in v.keys if k is not None]
                        if elts and not all(_designe_un_membre(e) for e in elts):
                            fautifs.append((rel, n.lineno, t, "REDEFINITION en ordinaux nus"))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr in ("pop", "setdefault", "add", "discard", "remove") and n.args:
                t = _nom(n.func.value)
                if t and not _designe_un_membre(n.args[0]):
                    fautifs.append((rel, n.lineno, t, "mutation par ordinal nu"))

    assert fautifs == [], (
        "ces sites ecrivent/mutent une structure de la tranche par un ordinal NU -- apres passage "
        "la structure porterait un element non type, et le cliquet (etage 1) rougirait SELON "
        "L'ORDRE DES TESTS : %r" % fautifs)


def test_etage6_edge_et_corner_sont_au_registre_de_probe_313():
    """ETAGE 6 -- un mirror NEUF entre au registre DANS LE MEME COMMIT.

    Ce gisement s'est rouvert TROIS fois par notre propre cadence -- `PathfinderType` (#381-r5),
    `KillUnitStep` (#389-r2), `DamageReason` (#651, qui rendait `master` ROUGE). L'etape 1 de
    `probe_313` DECOUVRE toute `IntEnum` sous `engine/`, donc un mirror hors registre en sort
    ORPHELIN : ce test le rend explicite plutot que de compter sur la lecture du rapport.

    ⚠ La cle est le nom PLEIN : le build porte `UnityEngine.RectTransform.Edge` (4 valeurs) et
    cinq `Corner` Unity/SimpleUI. Un appariement par nom COURT designerait le mauvais enum.
    """
    sys.path.insert(0, str(PYDIR))
    import probe_313_enum_mirror_bijection as P313

    par_nom = {m.cls: m for m in P313.REGISTRE}
    for nom, cle_attendue, cardinal in (("Edge", "IdunBattle.Utils.Hex.Edge", 6),
                                        ("Corner", "IdunBattleLogic.Utils.Hex.Corner", 6)):
        assert nom in par_nom, (
            "`%s` a un mirror sous `engine/` mais n'est PAS au registre de probe_313 : il en "
            "sortirait ORPHELIN, et sa derive au prochain build serait SILENCIEUSE" % nom)
        m = par_nom[nom]
        assert m.cle == cle_attendue, (
            "`%s` est apparie a %r au lieu du nom PLEIN %r -- le nom court apparie un HOMONYME "
            "(UnityEngine/SimpleUI)" % (nom, m.cle, cle_attendue))
        assert m.garde and m.dette is None, "`%s` doit etre SOUS GARDE, sans dette" % nom
    assert len(Edge) == 6 and len(Corner) == 6
    # les six aretes du port sont bien celles du build, valeur par valeur
    assert {int(e): e.name for e in Edge} == {0: "North", 1: "North_East", 2: "South_East",
                                             3: "South", 4: "South_West", 5: "North_West"}
