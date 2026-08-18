"""CLIQUET `#552-r4` (volet livre) -- le gate slot-4 de `1192 NovaBoost` et `1194 NovaShield`.

CE QUE CETTE TRANCHE A TROUVE, ET COMMENT
------------------------------------------
`probe_552r3_slot4_declare.py` lit dans `global-metadata.dat` les methodes qu'un type DECLARE
(immune a la deduplication des corps, contrairement aux tables indexees par ADRESSE). Applique aux
98 playbooks portes, il a montre que `NovaBoostPlaybook` et `NovaShieldPlaybook` DECLARENT
`ShouldEvaluate` alors que le port ne surchargeait RIEN.

Les deux corps, LUS (build `t6dpr4k06g`), sont IDENTIQUES entre eux :

    if (!<IBattleQuery slot 0x1b = 27 = HasMinimumRemainingTurns>(unit, 2))  return false;
    return BasePlaybook$$ShouldEvaluate(unit);

et IDENTIQUES a celui de `NovaChargePlaybook` (1193), deja porte et confronte par `#1032-r1` --
trois abilities du meme kit Riptide. Le slot est RESOLU dans
`data/symbols/<build>/metadata/interface_slots.tsv` (`IBattleQuery 27 HasMinimumRemainingTurns
2 params`), et son ARITE concorde avec les deux arguments du call-site.

⚠ **LA DEGRADATION ETAIT PERMISSIVE, DONC INVISIBLE EN SELF-PLAY** : sans ce gate, le port
proposait 1192/1194 dans le dernier tour, la ou le natif les SAUTE. C'est la signature exacte de
#46 -- un gate AMONT manquant ne produit ni erreur ni crash, seulement un cast de trop.

⚠ **ET LA NOTE QUI VIVAIT DANS `nova_boost.py` ETAIT UNE SUPPOSITION** : elle citait
`query.slot0x1a(unit,2)` << precondition Nova, prob. charge >>. `0x1a` = 26 =
`ShouldPlayerSkipTurn`, qui prend UN parametre -- l'arite l'exclut. Une raison ECRITE mais non
mesuree avait fige un port incomplet, et decourage la verification.

    ETAGE 1  les deux classes SURCHARGENT `should_evaluate` (et pas `use_probability`)
    ETAGE 2  le gate MORD -- BC avec plafond de tours et compteur assez avance -> False
    ETAGE 3  le gate NE MORD PAS a l'aveugle : canal non fourni / BC sans plafond -> True
    ETAGE 4  les TROIS playbooks du kit Riptide partagent le MEME litteral `2`

100 % offline : aucun runner, aucun RPC. ASCII only (cp1252).
"""
from __future__ import annotations

#: Perimetre ETROIT et DERIVE : les fichiers dont une edition peut RENDRE FAUX ce que ce cliquet
#: fige (les trois feuilles, le pont de substrat, et son mirror de corps).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/playbook/noncomparable/nova_boost.py",
        "scripts/python/engine/playbook/noncomparable/nova_shield.py",
        "scripts/python/engine/playbook/noncomparable/nova_charge.py",
        "scripts/python/engine/playbook/noncomparable/_base.py",
        "scripts/python/engine/services/battle_query.py",
        "scripts/python/engine/entities/victory_condition_type.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Ce volet ne lit ni le binaire ni les tables du build : il fige la PRESENCE du gate "
              "sur les trois feuilles et sa POLARITE dans les deux sens, en passant par le pont "
              "de substrat `_base.has_minimum_remaining_turns` et son mirror de corps. Le seul "
              "axe qui les perime est une edition de ces fichiers-la. La verification que la "
              "METADATA declare toujours `ShouldEvaluate` sur ces classes est le travail de "
              "`probe_552r3_slot4_declare`, qui porte `build: True`.",
}

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.victory_condition_type import VictoryConditionType
from engine.playbook.noncomparable import PLAYBOOKS
from engine.playbook.noncomparable._base import NCContext, NonComparablePlaybook

_BOOST = int(ActiveAbilityType.NovaBoost)      # 0x4a8 = 1192
_SHIELD = int(ActiveAbilityType.NovaShield)    # 0x4aa = 1194
_CHARGE = int(ActiveAbilityType.NovaCharge)    # 0x4a9 = 1193
_CLE = VictoryConditionType.MainPlayerRoundLimitation.name


def _ctx(**kw) -> NCContext:
    champs = dict(uid=1, origin=(0, 0), reach_nc=[(0, 0)], epos=[], fpos=[], plan={},
                  hp_cur_by_id={}, ability_targets=None)
    champs.update(kw)
    return NCContext(**champs)


def test_etage1_les_deux_classes_surchargent_le_slot_4():
    """La metadata DECLARE `ShouldEvaluate` sur ces classes ; le port doit donc surcharger
    `should_evaluate` -- et PAS `use_probability`, que le natif ne surcharge pas ici.

    ⚠ Le foyer `NonComparablePlaybook.should_evaluate` prescrit expressement l'inverse pour une
    PROBABILITE (<< surcharger `use_probability` >>) : cette surcharge-ci est legitime PARCE QUE la
    vtable remplace `BasePlaybook$$ShouldEvaluate` lui-meme, ce qui est LU, pas suppose.

    ⚠ **ET LES TROIS NE SONT PAS INTERCHANGEABLES SUR LE SECOND ETAGE** -- ce cran a MORDU a son
    premier passage, sur une assertion ecrite trop vite : la metadata declare `GetUseProbability`
    sur `NovaChargePlaybook` SEUL (son `p` vaut `Half` ou `One` selon que `NovaShield` est encore
    lancable, #1032-r1), et PAS sur `NovaBoost`/`NovaShield`, dont le second etage reste le defaut
    `Fix64(1)`. Le figer dans les deux sens est ce qui empeche de recopier un etage d'une soeur a
    l'autre."""
    for aid in (_BOOST, _SHIELD, _CHARGE):
        pb = PLAYBOOKS[aid]
        assert type(pb).should_evaluate is not NonComparablePlaybook.should_evaluate, (
            "%d DECLARE `ShouldEvaluate` cote natif : le port doit le surcharger" % aid)
    for aid in (_BOOST, _SHIELD):
        assert type(PLAYBOOKS[aid]).use_probability is NonComparablePlaybook.use_probability, (
            "%d ne DECLARE PAS `GetUseProbability` cote natif -- le port ne doit pas surcharger "
            "(le second etage reste le defaut `Fix64(1)`)" % aid)
    assert type(PLAYBOOKS[_CHARGE]).use_probability is not NonComparablePlaybook.use_probability, (
        "1193 DECLARE `GetUseProbability` cote natif (Half ou One selon 1194) : le port le "
        "surcharge, et c'est ce qui le SEPARE de ses deux soeurs")


def test_etage2_le_gate_MORD_quand_le_plafond_de_tours_existe():
    """`HasMinimumRemainingTurns(unit, 2)` = `2 <= maxRounds - turnsEndedByFirstPlayer`.

    BC AVEC plafond `3` et 2 tours deja termines -> `2 <= 1` est FAUX -> le natif SAUTE l'ability.
    C'est le seul bras qui puisse refuser, et c'est celui qui n'etait pas porte."""
    ctx = _ctx(victory_conditions={_CLE: 3}, turns_ended_by_first_player=2)
    for aid in (_BOOST, _SHIELD, _CHARGE):
        assert PLAYBOOKS[aid].should_evaluate(ctx) is False, (
            "%d : plafond 3, 2 tours termines -> le gate natif REFUSE" % aid)
    # La borne EXACTE, dans l'autre sens : `2 <= 3 - 1` est VRAI.
    tot = _ctx(victory_conditions={_CLE: 3}, turns_ended_by_first_player=1)
    for aid in (_BOOST, _SHIELD, _CHARGE):
        assert PLAYBOOKS[aid].should_evaluate(tot) is True, (
            "%d : plafond 3, 1 tour termine -> `2 <= 2` est VRAI, le gate ACCEPTE" % aid)


def test_etage3_le_gate_ne_refuse_pas_a_l_aveugle():
    """Deux regimes NON REFUSANTS, et ils n'ont pas la meme nature :

      * canal NON FOURNI -> le foyer retombe sur son defaut DERIVE de `data/seed-bc.json` (ou la
        cle `MainPlayerRoundLimitation` est ABSENTE) : c'est deja une LECTURE, pas une convention ;
      * BC MESUREE et SANS plafond -> `Nullable` vide -> `true` par le bras 1, sans rien lire
        d'autre.

    Un `False` fabrique dans l'un des deux RETIRERAIT un cast que le natif fait."""
    for ctx in (_ctx(), _ctx(victory_conditions={})):
        for aid in (_BOOST, _SHIELD, _CHARGE):
            assert PLAYBOOKS[aid].should_evaluate(ctx) is True, (
                "%d : regime non refusant -- le gate ne doit pas gater a l'aveugle" % aid)


def test_etage4_le_litteral_2_est_partage_par_les_trois():
    """Les trois call-sites passent le MEME litteral. Le figer empeche qu'un port futur << arrondisse >>
    l'un des trois : la valeur est LUE au decompile, pas choisie."""
    import engine.playbook.noncomparable.nova_boost as NB
    import engine.playbook.noncomparable.nova_shield as NS
    import engine.playbook.noncomparable.nova_charge as NC
    assert NB._MIN_REMAINING_TURNS == NS._MIN_REMAINING_TURNS == NC._MIN_REMAINING_TURNS == 2
