"""#350 -- l'inventaire des formes de moyenne de prediction est CLOS et TRACABLE.

#344 avait lu 36 abilities (18 par forme) et laisse ~60 NON LUES sur le defaut. #350 boucle
l'inventaire : la moyenne minDmg/maxDmg ne peut naitre QUE de
`IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage{,Average}` -- dont les xrefs sont
enumerees -- ou d'un `IdunBattleLogic.Entities.DSLFormulas$$Half` / `$$Divide` INLINE dans un
playbook, dont les xrefs le sont aussi (deux playbooks seulement). Les registres sont donc
EXHAUSTIFS pour le build `rnca9r7q6c`, et chaque id porte SA voie.

Ce que la garde verrouille :
A. les QUATRE sous-ensembles de la forme (a) sont deux a deux DISJOINTS et leur union est
   exactement `_PREDICTION_MINMAX_AVERAGE` -- la provenance de chaque id reste lisible ;
B. les TROIS tables (moyenne (a), moyenne (b), base qui n'est PAS une moyenne) sont mutuellement
   disjointes, et chaque id resout a une ability `ActiveAbilityType` du gameconfig ;
C. les abilities CONFRONTEES LIVE par #350 relevent bien de (a), et sur un couple `3 mod 4` elles
   MONTENT d'une unite au-dessus du defaut (troncature) -- c'est le cliquet : les retirer du
   registre re-creerait exactement l'ecart mesure sur le natif ;
D. `SorcerousFacade` (1100) est LU (a) et, DEPUIS #351, ACTIF : le port n'ecrase plus le batch de
   l'ability par l'attaque normale, il met celle-ci EN TETE (`_PREPEND_NORMAL_ATTACK_EVENT`) et
   AJOUTE le batch -- comme le natif. Les deux entrees qui rendent le 2e event existant (le terme
   en tete + le profil VIDE) sont gardees ici ; le bras live de #344 sur 1100 n'est plus muet ;
E. la table des bases NON-moyennes distingue ce qui est DEJA corrige en amont (un handler
   `_MAKE_DMG_INPUT_OVERRIDES`) de ce qui reste un residu chiffre ;
F. (#350-r3) `1160 HeavyRailRifle` n'est dans AUCUN des trois registres, et la RAISON est ecrite :
   son playbook evalue une AUTRE ability, la TriggeredAbility `0x4ec = 1260`. L'y inscrire serait une
   erreur de qualification d'enum, pas une correction ;
G. (#350-r3) le gate de SELECTEUR de `1148 DaemonicOrdnance` existe et refuse une cible dont la tuile
   ne porte pas `Fire` -- ce qui etait la sur-prediction muette trouvee en levant le mur MoW.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[2]                 # scripts/python
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                          # noqa: E402
from engine.dsl.base import calculate_average                                    # noqa: E402
from engine.services.min_max_damage import min_max_avg                           # noqa: E402
from engine.entities.abilities.ability_configuration import AbilityConfiguration  # noqa: E402
from engine.entities.abilities.active_ability import (                           # noqa: E402
    AActiveAbility,
    _PREDICTION_MINMAX_AVERAGE, _PREDICTION_MINMAX_RANDOM_READ,
    _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE, _PREDICTION_FORMULA_ON_TRIGGERED_ABILITY,
    _A_VIA_GET_DAMAGE_AMOUNT_MAIN, _A_VIA_STAFF_OF_STARS_GET_DAMAGE,
    _A_VIA_OWN_ABILITY_BODY, _A_INLINE_IN_PLAYBOOK)
from engine.entities.active_ability_type import ActiveAbilityType                # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType          # noqa: E402
from engine.entities.unit_context import UnitContext                             # noqa: E402


_SUBSETS = {
    "a1 GetDamageAmountMain": _A_VIA_GET_DAMAGE_AMOUNT_MAIN,
    "a2 StaffOfStarsAbility$$GetDamage(isPrediction=1)": _A_VIA_STAFF_OF_STARS_GET_DAMAGE,
    "a3 corps propre de l'ability": _A_VIA_OWN_ABILITY_BODY,
    "a4 moyenne INLINE dans le playbook": _A_INLINE_IN_PLAYBOOK,
}

# Les trois abilities CONFRONTEES LIVE par #350 (probe_344_ability_damage_average.py), une par
# sous-chaine atteignable : chacune est passee de la TRONCATURE (defaut d'avant #350) au
# demi-vers-le-pair, et le natif a tranche dans ce sens sur les deux bras de parite.
LIVE_CONFRONTED = {
    1177: "LightOfSanguinius",          # a2 -- bloodDante, niveaux 7/1 : natif (120,180,5) vs trunc (115,175,5)
    1204: "LeadingTheCharge",           # a2 -- astraDreir,  niveaux 2/4 : natif (81,123,3)  vs trunc (78,120,3)
    1104: "SpiritLeech",                # a3 -- tyranNeurothrope, 4/3    : natif (45,67,1)   vs trunc (44,65,1)
}


def _ability(ability_type: int, mn: int, mx: int) -> AActiveAbility:
    cfg = AbilityConfiguration(name="synthetique", variables={"minDmg": [mn], "maxDmg": [mx]},
                               constants={})
    return AActiveAbility(ability_type=ability_type, caster=UnitContext(entity_id=1),
                          config=cfg, ability_state={"level": 1, "multiplier": 100})


def test_the_four_sub_chains_partition_the_average_family():
    """A : chaque id de la forme (a) vient d'UNE voie de lecture identifiee, et d'une seule."""
    names = list(_SUBSETS)
    for i, na in enumerate(names):
        assert _SUBSETS[na], "sous-ensemble vide : %s" % na
        for nb in names[i + 1:]:
            inter = _SUBSETS[na] & _SUBSETS[nb]
            assert not inter, (
                "un id ne peut pas venir de DEUX voies natives a la fois (%s / %s) : %s"
                % (na, nb, sorted(inter)))
    union = set().union(*_SUBSETS.values())
    assert union == set(_PREDICTION_MINMAX_AVERAGE), (
        "l'union des sous-chaines n'est plus le registre (a) : la provenance d'au moins un id "
        "n'est plus tracable -- ecart %s" % sorted(union ^ set(_PREDICTION_MINMAX_AVERAGE)))


def test_the_three_tables_are_disjoint_and_resolve():
    """B : (a), (b) et 'pas une moyenne' sont mutuellement exclusives ; tout id est une ability."""
    a, b, n = set(_PREDICTION_MINMAX_AVERAGE), set(_PREDICTION_MINMAX_RANDOM_READ), \
        set(_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE)
    for lhs, rhs, label in ((a, b, "(a) / (b)"), (a, n, "(a) / non-moyenne"),
                            (b, n, "(b) / non-moyenne")):
        assert not (lhs & rhs), "%s se recouvrent : %s" % (label, sorted(lhs & rhs))
    for aid in sorted(a | b | n):
        name = GC.ability_name(aid)
        assert name, "id %d ne resout a aucune ability (`ActiveAbilityType`)" % aid


def test_live_confronted_abilities_round_half_to_even():
    """C : le cliquet. Sur `3 mod 4` les trois abilities mesurees live MONTENT d'exactement 1
    au-dessus de la troncature -- l'ecart que le natif a tranche en leur faveur."""
    for aid, name in sorted(LIVE_CONFRONTED.items()):
        assert GC.ability_name(aid) == name, "id %d ne resout plus a %s" % (aid, name)
        assert aid in _PREDICTION_MINMAX_AVERAGE, (
            "%s (%d) est sorti du registre (a) : le port lui rendrait de nouveau la TRONCATURE, "
            "que le natif a REFUSEE en live (#350)" % (name, aid))
        for mn, mx in ((29, 38), (35, 48), (20, 27)):
            assert (mn + mx) % 4 == 3
            got = _ability(aid, mn, mx).get_damage()
            assert got == min_max_avg(mn, mx) == calculate_average(mn, mx) + 1, (
                "%s (%d) sur (%d,%d) : %d, attendu %d (demi-vers-le-pair, une unite au-dessus "
                "de la troncature)" % (name, aid, mn, mx, got, min_max_avg(mn, mx)))


def test_sorcerous_facade_is_read_and_now_ACTIVE_in_the_port():
    """D : 1100 est LU (a) -- son playbook inline `Half(Sum(Get(mn), Get(mx)), 0)` -- et depuis #351
    l'inscription est ACTIVE, plus inerte.

    #350 avait ecrit ici « le port delegue sa prediction ENTIERE a l'attaque normale, donc
    `get_damage` ne le voit pas », et le bras live du probe #344 en etait MUET. La cause etait un
    bug de port, pas une propriete du natif : `...SorcerousFacadePlaybook$$MakeDamagePredictions`
    fait `list = [normale]` PUIS `list.AddRange(batch)` -- il AJOUTE. Le port SUBSTITUAIT.

    Les deux entrees ci-dessous sont ce qui rend le 2e event EXISTANT, donc la moyenne (a4)
    OBSERVABLE. Les retirer re-cree exactement le bras muet -- et le probe #344 le rougit
    desormais (mesure #351 : sans le terme en tete, le port rend UN event au lieu de deux)."""
    import engine.playbook.prediction.abilities as PA
    assert 1100 in _A_INLINE_IN_PLAYBOOK and 1100 in _PREDICTION_MINMAX_AVERAGE
    assert "SorcerousFacade" in PA._PREPEND_NORMAL_ATTACK_EVENT, (
        "1100 n'emet plus l'attaque normale EN TETE : le natif la met la (`list = [normale]` avant "
        "l'`AddRange`), et sans elle le port rend un seul event")
    assert PA._PLAYBOOK_PROFILE_OVERRIDE.get(1100) == "None", (
        "le profil du 2e batch de 1100 est VIDE au call-site (`param_8` nul) : sans cette entree "
        "le port percerait l'armure avec `Psychic` (pierce 100) -- mesure #351 sur cible blindee, "
        "natif (1,1,1) contre (30,46,1)")


def test_non_average_bases_are_named_and_their_fix_state_is_true():
    """E : la table des bases NON-moyennes dit la verite sur ce qui est deja corrige. Un id marque
    'corrige' doit avoir son handler d'entrees ; un id marque 'residu' ne doit pas en avoir (sinon
    la table sur-declare le reste a faire)."""
    import engine.playbook.prediction.abilities as PA
    assert _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE
    for aid, (symbol, formula, fixed) in sorted(_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE.items()):
        assert symbol and formula, "id %d : entree incomplete" % aid
        has_handler = aid in PA._MAKE_DMG_INPUT_OVERRIDES
        assert has_handler == bool(fixed), (
            "id %d (%s) : la table annonce corrige=%s mais _MAKE_DMG_INPUT_OVERRIDES dit %s"
            % (aid, GC.ability_name(aid), fixed, has_handler))


def test_1160_formula_belongs_to_a_triggered_ability_not_to_1160():
    """F (#350-r3 volet c) : `HeavyRailRiflePlaybook$$EvaluateNonComparable` n'evalue PAS 1160.

    Il appelle `Playbook<T>$$GetAbility<T>(this, 0x4ec, ...)` -- soit `TriggeredAbilityType
    .HeavyRailRifle_Attack = 1260`, la MEME valeur que rend `HeavyRailRifle_PendingAttackEffect
    $$GetTriggeredAbilityType`. Sur cet objet il lit `BaseTriggeredAbility$$GetDamageProfileOrDefault`,
    `VisionsOfHeresy_AttackAbility$$GetAttackHits` puis `MassiveScythingTalonsAbility$$GetDamage`
    (-> `BaseTriggeredAbility$$MinMaxDamage`, config a `+0x20`).

    L'ability ACTIVE 1160 ne fait que POSER deux effets : `HeavyRailRifleAbility$$ExecuteBehaviour`
    = `AddEffect(0x536 = 1334 PendingTarget) & AddEffect(0x535 = 1333 PendingAttack)`. Aucun degat.

    Inscrire 1160 a l'un des registres serait donc FAUX sur deux axes a la fois : mauvais enum
    (`ActiveAbilityType` au lieu de `TriggeredAbilityType`) et mauvais objet. Cette garde interdit
    l'inscription et conserve la raison."""
    assert int(ActiveAbilityType.HeavyRailRifle) == 1160
    assert int(TriggeredAbilityType.HeavyRailRifle_Attack) == 1260 == 0x4ec
    for reg, label in ((_PREDICTION_MINMAX_AVERAGE, "(a) MinMaxDamageAverage"),
                       (_PREDICTION_MINMAX_RANDOM_READ, "(b) RandomAmount"),
                       (_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE, "base non-moyenne")):
        assert 1160 not in reg, (
            "1160 inscrite au registre %s : ces registres sont indexes par `ActiveAbilityType` et "
            "lus par `AActiveAbility.get_damage`, chemin que l'objet evalue (une "
            "`BaseTriggeredAbility`) n'emprunte pas" % label)
    assert 1160 in _PREDICTION_FORMULA_ON_TRIGGERED_ABILITY
    _pb, trig, _chain = _PREDICTION_FORMULA_ON_TRIGGERED_ABILITY[1160]
    assert trig == int(TriggeredAbilityType.HeavyRailRifle_Attack)
    # La table documentaire ne doit JAMAIS recouvrir les registres : une entree presente des deux
    # cotes serait exactement la qualification d'enum fausse qu'elle existe pour empecher.
    keys = set(_PREDICTION_FORMULA_ON_TRIGGERED_ABILITY)
    for reg in (_PREDICTION_MINMAX_AVERAGE, _PREDICTION_MINMAX_RANDOM_READ,
                _PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE):
        assert not (keys & set(reg)), sorted(keys & set(reg))


def test_1148_target_gate_mirrors_the_native_selector():
    """G (#350-r3 volet b) : `DaemonicOrdnancePlaybook$$MakeDamagePredictions` boucle sur
    `GetAllDamageableTargets` = `Enemies(caster, Units(Filter(GetTargetAreaTiles(),
    HasEffect(Tiles(Subject), 5 = Fire))), 3)` -- les ennemis debout sur une tuile DEJA EN FEU.

    Le port n'avait pas ce selecteur et emettait un event GENERIQUE par cible demandee. Mesure
    #350-r3 (board sans feu) : natif `count = 0`, port `(81, 123, 3)`. Sur-prediction muette.

    Cette garde tient les trois branches de `_daemonic_ordnance_target_gate` sur une scene
    SYNTHETIQUE (aucun runner) : ami refuse, tuile froide refusee, tuile en feu acceptee."""
    import engine.playbook.prediction.abilities as PA
    gate = PA._MAKE_DMG_TARGET_GATE.get(1148)
    assert gate is not None, "1148 n'a plus son gate de selecteur : le port re-invente des events"

    class _S:
        def __init__(self, fx):
            self._fx = fx
        def team(self, uid):                                        # noqa: D102
            return {1: 1, 2: 2, 3: 1}.get(uid)
        def pos(self, uid):                                         # noqa: D102
            return {1: (3, 4), 2: (4, 4), 3: (5, 4)}.get(uid)
        tile_effects_by_pos = property(lambda self: self._fx)

    burning = _S({(4, 4): ["Fire"]})
    assert gate(burning, 1, 2) is True, "ennemi sur une tuile EN FEU : le natif l'attaque"
    assert gate(burning, 1, 3) is False, "tuile de la cible sans `Fire` : `Filter` la rejette"
    assert gate(_S({(4, 4): ["Fire"]}), 1, 1) is False, "le caster est son propre ami (`Enemies`)"
    assert gate(_S({}), 1, 2) is False, "aucun effet de tuile connu : regime du board frais"
    assert gate(_S(None), 1, 2) is False, "`tileMeta` non charge -> feu INCONNU, pas suppose"
