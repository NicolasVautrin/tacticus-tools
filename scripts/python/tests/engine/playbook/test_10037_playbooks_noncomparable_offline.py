"""#10037 -- CLIQUET des sept lectures de la tranche << playbooks NonComparable >>.

Chaque etage garde UNE lecture du decompile, et chacun a ete VU ROUGE par mutation
(`probe_10037_mutants.py`). Aucun etage ne compare un compte a un seuil : ce sont des
INVARIANTS de forme (une valeur figee, une primitive citee, un ordre derive).

    ETAGE 1  `#433-r4-r2-r3`          -- `EarlyWarningOverridePlaybook` n'a AUCUNE borne
    ETAGE 2  `#433-r4-r1-r4-r2-r2`    -- le gate2 d'`HeroicFusillade` est GEOMETRIQUE
    ETAGE 3  `#971-r4`                -- l'ordre des tuiles de spawn est PAR POSITION, et il est
                                         partage par les TROIS playbooks ring-1
    ETAGE 4  `#1032-r1`               -- les deux faces DECISION neuves et leurs constantes
    ETAGE 5  `#1032-r1`               -- `ABossSummonAbilityPlaybook<T>$$GetUseProbability`
    ETAGE 6  `#456-r2-r1`             -- les QUATRE crans de `$$FilterMovementTiles`
    ETAGE 7  `#585-r2`                -- le palier NON MONOTONE de `WarHowlPlaybook`

100 % offline : aucun runner, aucun RPC. ASCII only.
"""
from __future__ import annotations

import inspect
import os
import sys
import textwrap

import pytest

_PYROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
if _PYROOT not in sys.path:
    sys.path.insert(0, _PYROOT)

import hexgeo                                                             # noqa: E402
from engine.playbook.noncomparable import PLAYBOOKS                       # noqa: E402
from engine.playbook.noncomparable._base import (NCContext,               # noqa: E402
                                                 tiles_in_native_order)
from engine.entities.active_ability_type import ActiveAbilityType         # noqa: E402


# ============================================================================================
#  ETAGE 1 -- `#433-r4-r2-r3` : le Bucket a DEUX arguments n'a pas de `minUtility`
# ============================================================================================

def test_etage1_early_warning_override_sans_borne():
    """`...EarlyWarningOverridePlaybook$$EvaluateNonComparable` construit son `Bucket` par la
    surcharge a DEUX arguments -- donc `minUtility.HasValue == false`, donc `AddAction` accepte
    TOUT. Le `Fix64(1)` de son `.cctor` n'a AUCUN lecteur (la classe ne declare que `.ctor`,
    `EvaluateNonComparable` et `.cctor`, plus un champ PRIVE).

    Un `MIN_UTILITY` positif rejetterait la quasi-totalite des positions -- l'utilite est
    `Somme(+50 par ennemi hors portee) - 10 x Somme(distances)`, donc NEGATIVE des que les ennemis
    sont loin. C'est exactement le no-op silencieux qu'`IronkinSteeljackPlaybook` avait deja."""
    pb = PLAYBOOKS[int(ActiveAbilityType.EarlyWarningOverride)]
    assert pb.MIN_UTILITY == float("-inf"), (
        "1077 n'a AUCUNE borne (ctor de Bucket a DEUX arguments) : `MIN_UTILITY` doit etre `-inf`, "
        "pas %r" % (pb.MIN_UTILITY,))


def test_etage1b_les_sans_borne_sont_un_inventaire_FIGE():
    """INVENTAIRE, pas seuil : la liste des playbooks SANS borne est FIGEE, et chacun l'est pour
    une raison LUE au decompile -- une surcharge de `Bucket<T>$$.ctor` qui ne recoit PAS de
    `Nullable<Fix64>` :

      * `1043 ThunderousAssault` -- surcharge a UN argument (voie
        `NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies`), et la classe n'a AUCUN
        `.cctor` (#977) ;
      * `1077 EarlyWarningOverride` -- surcharge a DEUX arguments ; son `.cctor` ecrit bien un
        `Fix64(1)`, mais AUCUNE methode ne le lit (#433-r4-r2-r3) ;
      * `1219 IronkinSteeljack` -- surcharge a DEUX arguments, aucun `.cctor` (#971).

    Un QUATRIEME qui apparaitrait sans etre relu est une regression : `-inf` est la transcription
    d'une ABSENCE de `Nullable`, pas un moyen commode de desarmer un seuil genant.

    ⚠ Ce cran a MORDU des son premier passage : la premiere ecriture n'en listait que DEUX (elle
    avait recopie la phrase << SEUL playbook du registre sans borne >> du registre, deja perimee
    par #977). C'est le genre exact d'inventaire qu'on ne peut pas ecrire de memoire."""
    sans_borne = sorted(a for a, pb in PLAYBOOKS.items() if pb.MIN_UTILITY == float("-inf"))
    assert sans_borne == [int(ActiveAbilityType.ThunderousAssault),
                          int(ActiveAbilityType.EarlyWarningOverride),
                          int(ActiveAbilityType.IronkinSteeljack)], (
        "les playbooks SANS borne d'utilite sont FIGES a {1043, 1077, 1219} (ctor de Bucket SANS "
        "`Nullable<Fix64>`, LU un par un) ; mesure : %r" % (sans_borne,))


# ============================================================================================
#  ETAGE 2 -- `#433-r4-r1-r4-r2-r2` : `GetSurroundingUnits` est un DISQUE GEOMETRIQUE
# ============================================================================================

def _corps_executable(cls) -> str:
    """Le code EXECUTABLE d'une classe -- docstrings et commentaires RETIRES, par l'AST.

    Un filtre textuel confondrait la PROSE (qui cite volontiers la primitive a NE PAS employer)
    avec le CODE. `ast.unparse` d'un arbre dont on a retire les `Expr(Constant(str))` rend
    exactement le premier."""
    import ast
    arbre = ast.parse(textwrap.dedent(inspect.getsource(cls)))

    class _SansDoc(ast.NodeTransformer):
        def visit_Expr(self, node):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return None
            return node

    return ast.unparse(_SansDoc().visit(arbre))

def test_etage2_heroic_fusillade_ne_cite_pas_la_primitive_d_adjacence():
    """`HeroicFusilladePlaybook` interroge `IBattleQuery` slot 119 = `GetSurroundingUnits`, qui
    descend a `TileQuery.<IterateSurroundingTiles>d__6$$MoveNext` -- triple boucle CUBE, SANS porte
    d'elevation et SANS liste d'adjacence stockee.

    Le residu accusait ce module de << compter des voisins SANS elevation NI voisinage >>. La
    lecture le REFUTE : brancher les deux canaux serait la REGRESSION. Ce cran garde donc
    l'INVERSE de ce que le residu demandait -- et il garde surtout que la primitive CITEE au site
    ne soit pas `count_adjacent` / `is_adjacent`, qui mirrorent `IterateAdjacentTiles`, un AUTRE
    natif. Sans ce cran, un futur lecteur << reparerait >> le site en le cassant.

    ⚠ Le corps EXECUTABLE est extrait par l'AST, pas par un filtre de lignes : la docstring de ce
    playbook CITE `count_adjacent` (pour dire de ne pas l'employer), et un filtre textuel rougirait
    sur sa propre prose. C'est le vice de `migrate_va_to_symbol.py` transpose ici -- un balayage qui
    ne distingue pas le CODE du COMMENTAIRE mesure autre chose que ce qu'il croit."""
    corps = _corps_executable(PLAYBOOKS[int(ActiveAbilityType.HeroicFusillade)].__class__)
    assert "count_adjacent" not in corps and "is_adjacent" not in corps, (
        "le gate2 de 1180 est `GetSurroundingUnits` (disque CUBE geometrique), pas `GetAdjacent*` : "
        "aucune primitive d'adjacence stockee ne doit apparaitre dans le corps")
    assert "hexgeo.distance" in corps, (
        "le disque geometrique doit etre ECRIT explicitement (`hexgeo.distance`), pas obtenu par le "
        "repli d'un helper d'adjacence -- sinon la citation native est fausse")


def test_etage2b_le_rayon_est_le_litteral_du_call_site():
    pb = PLAYBOOKS[int(ActiveAbilityType.HeroicFusillade)]
    assert pb._SPLASH_RADIUS == 1, (
        "`GetSurroundingUnits(<cible>, 1, includeCenter: 0)` -- le rayon est le litteral `1`")


# ============================================================================================
#  ETAGE 3 -- `#971-r4` : l'ordre des tuiles de spawn est PAR POSITION
# ============================================================================================

#: Les TROIS playbooks de spawn ring-1 dont les ctors d'ability sont IDENTIQUES OCTET POUR OCTET
#: (`TargetingOptions..ctor(&opts, 0, <TargetingRange statics>+0x30, 1, 0x1040, 0, 0)`, relus le
#: 2026-08-18) -- donc MEME chaine d'enumeration, donc MEME foyer d'ordre.
_RING1 = (int(ActiveAbilityType.GrotTank),
          int(ActiveAbilityType.MasterOfTheTutelaries),
          int(ActiveAbilityType.IronkinSteeljack))


def test_etage3_les_trois_ring1_passent_par_le_foyer_partage():
    """Les trois DOIVENT appeler `_base.tiles_in_native_order`. Recopier l'ordre au lieu de le
    partager est exactement ce qui a laisse `#971-r4` ouvert apres `#971` : la reparation avait
    ete faite sur UN seul des trois."""
    manquants = []
    for aid in _RING1:
        # corps EXECUTABLE : une simple MENTION en docstring ne doit pas rendre ce cran vert.
        if "tiles_in_native_order" not in _corps_executable(PLAYBOOKS[aid].__class__):
            manquants.append(aid)
    assert not manquants, (
        "ces playbooks ring-1 n'empruntent pas le foyer d'ordre `_base.tiles_in_native_order` : "
        "%r -- l'ordre de l'UNION du RPC n'est celui d'AUCUNE position, et a utilite EGALE "
        "`Bucket$$AddAction` est keep-first, donc l'ORDRE **est** la decision" % (manquants,))


def _ctx_ordre(neigh=None) -> NCContext:
    """Montage MINIMAL du foyer d'ordre : une origine, une position de move, et un voisinage
    STOCKE dont l'ordre DIFFERE de celui de l'union."""
    return NCContext(uid=1, origin=(0, 0), reach_nc=[(0, 0), (5, 5)], epos=[], fpos=[], plan={},
                     hp_cur_by_id={}, neigh_by_pos=(neigh if neigh is not None else {}))


def test_etage3b_le_montage_est_discriminant():
    """Sans ce cran, les deux suivants pourraient etre verts pour la mauvaise raison : il FAUT que
    l'ordre de l'union et celui du voisinage stocke soient REELLEMENT differents."""
    union = [(1, 1), (2, 2), (3, 3)]
    ring = [(3, 3), (1, 1), (2, 2)]
    assert union != ring and set(union) == set(ring), \
        "le montage doit opposer DEUX ORDRES du MEME ensemble, sinon il ne mesure rien"


def test_etage3c_a_l_origine_c_est_fromhere():
    """A l'ORIGINE, `fromHere` EST la reponse PAR POSITION du RPC : rien a deriver."""
    from_here, union = [(2, 2), (1, 1)], [(1, 1), (2, 2), (3, 3)]
    ctx = _ctx_ordre({(0, 0): [(3, 3), (1, 1), (2, 2)]})
    assert tiles_in_native_order(ctx, (0, 0), from_here, union, set(union)) == from_here, \
        "a l'origine le foyer doit rendre `fromHere` TEL QUEL, sans le re-trier"


def test_etage3d_ailleurs_c_est_le_voisinage_stocke():
    """Sur une position de MOVE, l'ordre vient de la liste d'adjacence STOCKEE
    (`ctx.neigh_by_pos[T]`), restreinte aux tuiles que le RPC declare eligibles."""
    from_here, union = [(2, 2)], [(1, 1), (2, 2), (3, 3)]
    ctx = _ctx_ordre({(5, 5): [(3, 3), (9, 9), (1, 1), (2, 2)]})
    got = tiles_in_native_order(ctx, (5, 5), from_here, union, set(union))
    assert got == [(3, 3), (1, 1), (2, 2)], (
        "hors origine, l'ordre doit etre celui du voisinage STOCKE (les tuiles hors-eligibles "
        "ecartees), obtenu %r" % (got,))


def test_etage3e_canal_muet_repli_nomme_sur_l_union():
    """Canal `neigh_by_pos` absent -> repli sur l'ordre de l'UNION, et le port le DIT plutot que
    de fabriquer un ordre. Degradation NOMMEE, jamais un ensemble vide."""
    union = [(1, 1), (2, 2), (3, 3)]
    ctx = _ctx_ordre({})
    assert tiles_in_native_order(ctx, (5, 5), [], union, set(union)) == union


def test_etage3f_une_tuile_eligible_hors_liste_stockee_part_en_QUEUE():
    """Elle ne DISPARAIT pas : le natif ne l'aurait pas vue, mais une perte silencieuse serait
    pire qu'un ordre de queue explicite."""
    union = [(1, 1), (7, 7)]
    ctx = _ctx_ordre({(5, 5): [(1, 1)]})
    assert tiles_in_native_order(ctx, (5, 5), [], union, set(union)) == [(1, 1), (7, 7)]


# ============================================================================================
#  ETAGE 4 -- `#1032-r1` : les deux faces DECISION neuves
# ============================================================================================

def test_etage4_les_deux_faces_decision_sont_au_registre():
    for aid in (int(ActiveAbilityType.CallRipperSwarms), int(ActiveAbilityType.NovaCharge)):
        assert aid in PLAYBOOKS, "%d doit etre au registre `PLAYBOOKS`" % aid


def test_etage4b_les_deux_soeurs_de_callripperswarms_restent_HORS_registre():
    """`...CallRipperSwarmsPlaybook$$.ctor` prend son id EN PARAMETRE, et le natif monte CETTE
    MEME classe pour 1052, 1054 et 1055. Le port n'inscrit QUE 1052 : les deux autres n'ont aucune
    face COMBAT (`ABILITY_CLASSES`), donc les proposer serait le no-op silencieux de #996 --
    la DECISION choisirait une ability que l'EXECUTION ignore."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    for aid in (1054, 1055):
        assert aid not in PLAYBOOKS, (
            "%d n'a pas de face COMBAT -- l'inscrire cote DECISION rouvrirait #996" % aid)
        assert aid not in ABILITY_CLASSES, (
            "premisse de ce cran : %d n'est PAS dans `ABILITY_CLASSES`. Si elle y entre, ce test "
            "doit etre RE-ETALONNE (et 1054/1055 peuvent alors entrer au registre NC)" % aid)


def test_etage4c_les_constantes_lues_au_decompile():
    crs = PLAYBOOKS[int(ActiveAbilityType.CallRipperSwarms)]
    nc = PLAYBOOKS[int(ActiveAbilityType.NovaCharge)]
    # Les deux `.cctor` ecrivent `Fix64.op_Implicit(1)`, passe au ctor du Bucket a QUATRE arguments.
    assert (crs.MIN_UTILITY, nc.MIN_UTILITY) == (1.0, 1.0)
    # Ni 1052 ni 1193 ne figurent dans `NATIVE_PRIORITY` (sweep exhaustif #170).
    assert (crs.PRIORITY, nc.PRIORITY) == (0, 0)
    # `Fix64.op_Implicit(e * 100 + n)` -- le `100` LITTERAL du corps de 1193.
    assert nc._ENEMY_WEIGHT == 100.0
    # `CanCurrentlyUseAbility(unit, 0x4aa)` : l'ability SOEUR, pas celle du playbook.
    assert nc._SISTER_ABILITY == int(ActiveAbilityType.NovaShield) == 1194
    assert nc._SISTER_ABILITY != nc.ABILITY_ID
    # `GetNumberConstant(config, 0x10 = nrOfSummons)` LU sur le gameconfig de 1052.
    assert crs._max_summons() == 4


def test_etage4d_la_geometrie_de_1193_est_le_foyer_de_la_face_combat():
    """`nova_charge_line_tiles` doit rester PARAMETRABLE et etre appelee par les DEUX faces. Un
    second mirror ferait diverger la face DECISION et la face COMBAT sur les trois lignes, EN
    SILENCE -- c'est le fork de foyer que #1066 a evite pour `MacroPlasmaIncinerator`."""
    from engine.runner.abilities import tau
    sig = inspect.signature(tau.nova_charge_line_tiles)
    assert "target_sel" in sig.parameters, \
        "`nova_charge_line_tiles` doit accepter le vehicule de collapse du role `Target`"
    corps = _corps_executable(PLAYBOOKS[int(ActiveAbilityType.NovaCharge)].__class__)
    assert "nova_charge_line_tiles" in corps, \
        "la face DECISION de 1193 doit APPELER le foyer de la face COMBAT, pas le recopier"
    # Et le defaut reste le slot `Target@+0x60` : la face COMBAT est INCHANGEE.
    assert sig.parameters["target_sel"].default is None


# ============================================================================================
#  ETAGE 5 -- `#1032-r1` : `ABossSummonAbilityPlaybook<T>$$GetUseProbability`
# ============================================================================================

class _Scene:
    def __init__(self, ts):
        self._ts = ts

    def turns_started(self, uid):
        return self._ts


def _ctx_crs(ts, units) -> NCContext:
    return NCContext(uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                     hp_cur_by_id={}, units=units, scene=_Scene(ts))


def test_etage5_premier_tour_rend_la_moitie():
    """`if (BaseUnitComponent.StartedTurns < 2) return FIRST_TURN_PROBABILITY;` -- le statique du
    `.cctor` de la base vaut `Fix64.FromIntFraction(1, 2)`."""
    pb = PLAYBOOKS[int(ActiveAbilityType.CallRipperSwarms)]
    assert pb.use_probability(_ctx_crs(1, [])) == 0.5


def test_etage5b_la_penalite_est_lineaire_en_enfants_vivants():
    """`1 - (0.8 x |enfants VIVANTS|) / GetMaxSummons()`, avec `GetMaxSummons() = 4`.

    Le filtre `IsAlive` est le discriminant : `GetChildren` prend un predicat, contrairement a
    `GetChildrenCount` (predicat NUL, liste append-only) que `DoctrinaImperatives` mirrore."""
    pb = PLAYBOOKS[int(ActiveAbilityType.CallRipperSwarms)]
    vivant = {"id": 2, "parentMeasured": True, "parentId": 1, "alive": True}
    mort = {"id": 3, "parentMeasured": True, "parentId": 1, "alive": False}
    autre = {"id": 4, "parentMeasured": True, "parentId": 9, "alive": True}
    assert pb.use_probability(_ctx_crs(3, [vivant, mort, autre])) == pytest.approx(1.0 - 0.8 / 4)
    assert pb.use_probability(_ctx_crs(3, [mort, autre])) == pytest.approx(1.0)


def test_etage5c_tri_etat_strict_sur_les_deux_substrats():
    """`None` = PAS MESURE, jamais un `0` invente. Un `0` d'enfants sur un canal MUET rendrait la
    probabilite MAXIMALE -- la valeur la plus permissive, FABRIQUEE."""
    pb = PLAYBOOKS[int(ActiveAbilityType.CallRipperSwarms)]
    assert pb.use_probability(_ctx_crs(None, [])) is None          # compteur de tours muet
    assert pb.use_probability(_ctx_crs(3, [{"id": 2, "alive": True}])) is None   # canal parent muet


def test_etage5d_la_probabilite_n_est_JAMAIS_un_refus():
    """`0.8 x n / max <= 0.8` tant que `n <= max`, donc `p >= 0.2` : aucune branche de ce
    `GetUseProbability` ne peut faire rendre `False` a `BasePlaybook$$ShouldEvaluate`. C'est
    pourquoi ce mirror ne deplace AUCUN verdict -- et pourquoi il est porte quand meme (la `prob`
    est confrontable au capteur `shouldEvaluateTrace`)."""
    pb = PLAYBOOKS[int(ActiveAbilityType.CallRipperSwarms)]
    for n in range(0, 5):
        units = [{"id": 10 + i, "parentMeasured": True, "parentId": 1, "alive": True}
                 for i in range(n)] or [{"id": 99, "parentMeasured": True, "parentId": 7,
                                         "alive": True}]
        p = pb.use_probability(_ctx_crs(3, units))
        assert p is not None and p > 0.0, "n=%d -> p=%r (le natif ne rend jamais <= 0)" % (n, p)


def test_etage5e_novacharge_lit_l_ability_soeur_pas_la_sienne():
    """`CanCurrentlyUseAbility(unit, 0x4aa = 1194 NovaShield)` : `Half` si elle est encore
    lancable, `One` sinon. Les deux statiques sont LUS dans `FixMath.NET.Fix64$$.cctor`
    (`+0x30` = `op_Division(1,2)`, `+0x20` = `0x100000000`)."""
    pb = PLAYBOOKS[int(ActiveAbilityType.NovaCharge)]

    def _c(abis):
        return NCContext(uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                         hp_cur_by_id={}, units=[{"id": 1, "abilities": abis}])

    assert pb.use_probability(_c([{"abilityId": 1194, "usable": True}])) == 0.5
    assert pb.use_probability(_c([{"abilityId": 1194, "usable": False}])) == 1.0
    # `GetActive(0x4aa) == null` -> `false` : une MESURE, donc la probabilite MAXIMALE.
    assert pb.use_probability(_c([{"abilityId": 1193, "usable": True}])) == 1.0
    # caster absent du canal -> NON MESURE
    assert pb.use_probability(_c([])) is None


# ============================================================================================
#  ETAGE 6 -- `#456-r2-r1` : les QUATRE crans de `$$FilterMovementTiles`
# ============================================================================================

def _sp():
    from engine.playbook.savior_protocols import SaviorProtocolsPlaybook
    return SaviorProtocolsPlaybook()


def _ctx_sp(units):
    return {"uid": 1, "friend_units": units, "enemy_units": []}


#: Un allie T'au VALIDE au sens de `TargetIsValidTrigger` (ami, faction 9, sans 1120, != mover).
_PROTEGEABLE = {"id": 2, "pos": (5, 5), "vis": "tauCrisis", "triggered": []}


def test_etage6_le_montage_est_discriminant():
    """`tauCrisis` doit REELLEMENT passer les quatre noeuds du trigger, sinon tout l'etage est
    vert pour la mauvaise raison."""
    from engine.playbook.savior_protocols import _target_is_valid_trigger
    assert _target_is_valid_trigger(_PROTEGEABLE, True, 1) is True


def test_etage6b_cran1_hasrangedweapon_court_circuite_TOUT():
    """`if (UnitExtensions.HasRangedWeapon(unit, null)) return;` -- le natif SORT sans rien
    retirer. `tauCrisis` porte une arme a distance."""
    tiles = [(0, 0), (5, 4), (9, 9)]
    assert _sp().filter_movement_tiles(tiles, _ctx_sp([_PROTEGEABLE]), "tauCrisis") == tiles


def test_etage6c_cran2_le_disque_est_GEOMETRIQUE_de_rayon_2():
    """`GetSurroundingUnits(tile, 2, includeCenter: 0)` -> `IterateSurroundingTiles`, triple boucle
    CUBE. Une tuile a distance 2 du protegeable est GARDEE, une a distance 3 est RETIREE."""
    sp = _sp()
    a_2 = next(p for p in _voisinage((5, 5), 2) if hexgeo.distance(p, (5, 5)) == 2)
    a_3 = next(p for p in _voisinage((5, 5), 3) if hexgeo.distance(p, (5, 5)) == 3)
    got = sp.filter_movement_tiles([a_2, a_3], _ctx_sp([_PROTEGEABLE]), None)
    assert got == [a_2], (
        "rayon 2 GEOMETRIQUE : %r (d=2) gardee, %r (d=3) retiree ; obtenu %r" % (a_2, a_3, got))


def test_etage6d_cran3_includecenter_zero_exclut_la_tuile_elle_meme():
    """La tuile OCCUPEE par le protegeable ne se protege pas elle-meme (`includeCenter = 0`)."""
    sp = _sp()
    voisine = next(p for p in _voisinage((5, 5), 1) if hexgeo.distance(p, (5, 5)) == 1)
    got = sp.filter_movement_tiles([(5, 5), voisine], _ctx_sp([_PROTEGEABLE]), None)
    assert got == [voisine], "la tuile du protegeable (d=0) doit etre EXCLUE ; obtenu %r" % (got,)


def test_etage6e_cran4_anti_vidage():
    """`if (toRemove.Count == allMovementTiles.Count) return;` -- si TOUTES les tuiles tomberaient,
    le natif n'en retire AUCUNE. Sans ce cran le mover serait IMMOBILISE."""
    tiles = [(0, 0), (1, 0)]
    assert _sp().filter_movement_tiles(tiles, _ctx_sp([_PROTEGEABLE]), None) == tiles


def test_etage6f_un_protegeable_INVALIDE_ne_garde_rien():
    """C'est la condition de PLUS que `case-443-r1` §5 n'avait pas : un voisin dans le rayon ne
    suffit pas, il doit passer `TargetIsValidTrigger`. Ici il porte DEJA 1120 -- il se protege
    seul, donc `!ActorHasTriggeredAbility` le rejette."""
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    porteur = dict(_PROTEGEABLE, triggered=[int(TriggeredAbilityType.SaviorProtocols)])
    voisine = next(p for p in _voisinage((5, 5), 1) if hexgeo.distance(p, (5, 5)) == 1)
    loin = (0, 0)
    got = _sp().filter_movement_tiles([voisine, loin], _ctx_sp([porteur]), None)
    assert got == [voisine, loin], (
        "aucune tuile ne passe -> ANTI-VIDAGE -> liste INCHANGEE ; obtenu %r" % (got,))


def _voisinage(centre, rayon):
    """Toutes les tuiles a distance <= `rayon` du centre, ordre stable."""
    return [(c, r)
            for c in range(centre[0] - rayon - 1, centre[0] + rayon + 2)
            for r in range(centre[1] - rayon - 1, centre[1] + rayon + 2)
            if hexgeo.distance((c, r), centre) <= rayon + 1]


# ============================================================================================
#  ETAGE 7 -- `#585-r2` : le palier de `WarHowlPlaybook` est NON MONOTONE, et il est PORTE
# ============================================================================================

def test_etage7_le_palier_de_warhowl_est_non_monotone():
    """`...WarHowlPlaybook$$GetUseProbability`, LU verbatim :

        if (n < 3) { u = (n == 1) ? 0x4b : 0x32; } else { u = 100; }

    donc `n = 0 -> 50`, `n = 1 -> 75`, `n = 2 -> 50`, `n >= 3 -> 100`. `2` vaut MOINS que `1` :
    c'est ce que le binaire dit, et le port ne le << corrige >> pas. Ce cran fige les QUATRE
    valeurs, y compris le creux -- une interpolation << reparerait >> le palier en silence.

    `#585-r2` demandait de porter cette face : elle l'ETAIT DEJA (#969 / #969-r1). Ce test est ce
    qui garde le port, a la place de la fiche."""
    from engine.playbook.noncomparable import war_howl as WH
    assert (WH._PCT_AUTRE, WH._PCT_UN_SEUL, WH._PCT_TROIS_OU_PLUS) == (50, 75, 100)
    palier = {n: (WH._PCT_TROIS_OU_PLUS if n >= 3
                  else (WH._PCT_UN_SEUL if n == 1 else WH._PCT_AUTRE)) for n in range(6)}
    assert palier == {0: 50, 1: 75, 2: 50, 3: 100, 4: 100, 5: 100}, \
        "le palier est NON MONOTONE (n=2 vaut 50, moins que n=1) ; mesure : %r" % (palier,)
    assert palier[2] < palier[1], "le creux en n=2 est la lecture -- ne pas l'interpoler"


def test_etage7b_la_face_decision_de_1106_est_au_registre():
    """La premisse de `#585-r2` (<< `WarHowlPlaybook` existe et n'est pas porte >>) est PERIMEE."""
    pb = PLAYBOOKS.get(int(ActiveAbilityType.WarHowl))
    assert pb is not None and pb.__class__.__name__ == "WarHowlPlaybook"
    assert pb.MIN_UTILITY == 1.0        # `...WarHowlPlaybook$$.cctor` = Fix64(1)
