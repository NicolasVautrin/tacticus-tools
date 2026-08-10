"""#572-r1 (offline) -- UN SEUL RESERVOIR POUR LE MAXIMUM DE PV.

Ce que ces crans figent, et pourquoi chacun peut casser SEUL :

  1. le MIRROR de `IdunBattle.Entities.Components.FillUpStatComponent$$get_CurrentMaximumValue`
     (la formule, y compris ses DEUX bornes, qui ne se devinent pas) ;
  2. le ROUTAGE : `apply_change_stat(StatType.HEALTH)` doit atterrir dans le `HealthComponent`,
     et **pas** dans `UnitStats.components[5]` -- c'est le residu lui-meme, dont le mode de panne
     etait SILENCIEUX (le port ecrivait, rien ne relisait) ;
  3. la VENTILATION DES PARTS : `Maximum` et `Initial` COINCIDENT au deploiement et DIVERGENT des
     qu'une modification est posee. Un test qui ne mesurerait que l'etat de deploiement serait
     vert sur les deux ports, celui d'avant comme celui d'apres ;
  4. le DISPATCH natif est une table de TROIS `StatType`, et le port n'en couvre qu'un -- le cran
     garde le compte pour que l'ecart reste VISIBLE (#572-r3) au lieu d'etre oublie.

Sortie ASCII uniquement.
"""
from __future__ import annotations

# `DECLENCHEUR` (#486-r15) -- ce qui doit changer pour que ce fichier puisse changer de verdict.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        # LE COMPOSANT (le mirror de `FillUpStatComponent`), LE ROUTAGE, LE LECTEUR.
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/operations/stat_ops.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
        # Les mirrors de `ValueModification` / `ValueOverride` / `StatPart` / `StatType`.
        "scripts/python/engine/entities/stats.py",
        # ⚠ ELARGI : la liste ci-dessus dit OU regarder ; les deux globs disent ce qui fait
        # vraiment changer d'avis (le cran bout-en-bout importe `context`, qui tire tout le
        # paquet `runner`). Les DEUX formes sont necessaires : `**/` exige un SEGMENT.
        "scripts/python/*.py", "scripts/python/**/*.py",
    ),
    "build": False,
    "toujours": False,
    "raison": "Le mirror de `FillUpStatComponent$$get_CurrentMaximumValue`, le dispatch de "
              "`UnitExtensions$$ApplyStatModifier` case 5, et le lecteur `ctx.get_stat`. Aucun "
              "runner, aucun canal live -> `build: False`. Le pendant LIVE de ces crans est "
              "`probe_572r1_hpmax_effectif.py`.",
}

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[2]
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from engine.entities.stats import StatPart, StatType, UnitStats, ValueModification  # noqa: E402
from engine.runner.components import HealthComponent, StatsComponent, UnitComponent  # noqa: E402
from engine.runner.operations.stat_ops import (apply_change_stat, apply_stat_override,  # noqa: E402
                                               remove_stat_override, revert_change_stat)
from engine.runner.state import State                                        # noqa: E402

SRC = "UnbreakableDuty_Health#1"
EXTRA_HP = 9970                      # la magnitude MESUREE live (level 50, mult 180 %)


def _unite(st, hp=10038, hp_max=10038):
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id="templAncient", alive=True))
    e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
    return e.id


# ---------------------------------------------------------------------------------------------
# 1. Le MIRROR de `get_CurrentMaximumValue`
# ---------------------------------------------------------------------------------------------

def test_le_maximum_est_base_plus_modification():
    """`Math.Min(int.MaxValue - initial, Math.Max(-initial, modTotal)) + base`. Sans modification
    le composant rend sa base, ce qui est l'etat de deploiement (`Initialize` pose
    `+0x10 = +0x14 = +0x18`)."""
    hc = HealthComponent(hp=300, hp_max=1000)
    assert hc.current_maximum_value() == 1000
    hc.modify_max(SRC, EXTRA_HP)
    assert hc.current_maximum_value() == 1000 + EXTRA_HP, (
        "le maximum ne suit pas la modification : %s" % hc.current_maximum_value())
    hc.reverse_max_modification(SRC)
    assert hc.current_maximum_value() == 1000, "le revert par-source n'a pas retire la contribution"


def test_la_borne_BASSE_du_clamp_est_moins_initial_pas_zero():
    """`Math.Max(-initial, modTotal)` -- la borne est `-initial`, PAS `0`. Une modification plus
    NEGATIVE que la base fait donc tomber le maximum a `base - initial` (= 0 au deploiement), et
    non a `base`. Ecrire `max(0, modTotal)` rendrait 1000 la ou le natif rend 0."""
    hc = HealthComponent(hp=300, hp_max=1000)
    hc.modify_max(SRC, -5000)                        # bien au-dela de `-initial`
    assert hc.current_maximum_value() == 0, (
        "clamp bas faux : %s (attendu 0 = base 1000 + max(-1000, -5000))"
        % hc.current_maximum_value())


def test_la_borne_HAUTE_est_int_max_moins_initial():
    """`Math.Min(int.MaxValue - initial, ...)`. Elle borne la MODIFICATION, pas le resultat : le
    maximum rendu vaut donc `int.MaxValue - initial + base`, et vaut `int.MaxValue` quand
    `base == initial` -- ce qui est le cas de tout composant deploye."""
    hc = HealthComponent(hp=1, hp_max=1000)
    hc.modify_max(SRC, 2 ** 40)
    assert hc.current_maximum_value() == 0x7fffffff, (
        "clamp haut faux : %s" % hc.current_maximum_value())


def test_l_override_DOMINE_et_absorbe_la_modification():
    """`ValueOverride.GetOverrideValueWithModification(modTotal)` = `override + modTotal` quand
    l'override est modifiable, et court-circuite entierement la formule base+modification."""
    hc = HealthComponent(hp=300, hp_max=1000)
    hc.modify_max(SRC, 500)
    hc.override_max(7000, is_modifiable=True)
    assert hc.current_maximum_value() == 7500, hc.current_maximum_value()
    hc.override_max(7000, is_modifiable=False)
    assert hc.current_maximum_value() == 7000, hc.current_maximum_value()
    hc.remove_max_override()
    assert hc.current_maximum_value() == 1500, hc.current_maximum_value()


def test_le_tri_etat_None_survit():
    """`hp_max is None` = le composant natif n'a pas ete capte. Il ne doit ni lever ni se
    rabattre sur 0 -- meme regle que `hp`."""
    hc = HealthComponent(hp=None, hp_max=None)
    assert hc.current_maximum_value() is None and hc.hp_max is None
    assert hc.fill_up(10) == 0 and hc.missing() == 0 and hc.max_fill_up(10) == 0


# ---------------------------------------------------------------------------------------------
# 2. Le ROUTAGE -- LE residu
# ---------------------------------------------------------------------------------------------

def test_un_stat_mod_HEALTH_va_dans_le_HealthComponent_et_PAS_dans_UnitStats():
    """LE cran de #572-r1. `IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` **case 5** route
    `StatType.Health` vers `FillUpStatComponent$$ApplyModifier` : le natif n'a AUCUN
    `StatComponent` pour la sante. Le port ecrivait dans `UnitStats.components[5]`, que rien ne
    relit pour les PV -- panne SILENCIEUSE (natif +9970 de maximum, port +0)."""
    st = State()
    uid = _unite(st)
    e = st.get_entity(uid)
    e.add_component(StatsComponent(ctx=type("C", (), {"stats": UnitStats()})()))
    hc = e.get_component(HealthComponent)

    avant = hc.hp_max
    apply_change_stat(st, uid, int(StatType.HEALTH), SRC, EXTRA_HP)
    assert hc.hp_max == avant + EXTRA_HP, (
        "le maximum n'a pas bouge (%s -> %s) : le stat-mod HEALTH est parti dans un autre "
        "reservoir" % (avant, hc.hp_max))
    us = e.get_component(StatsComponent).ctx.stats
    assert int(StatType.HEALTH) not in us.components, (
        "un composant HEALTH a ete cree dans `UnitStats` : le natif n'en a AUCUN, et deux "
        "reservoirs pour une meme grandeur sont exactement le residu")

    revert_change_stat(st, uid, int(StatType.HEALTH), SRC)
    assert hc.hp_max == avant, "le revert n'a pas retire la contribution du composant fill-up"


def test_les_PV_COURANTS_ne_bougent_PAS_sur_un_stat_mod_de_maximum():
    """Le natif ne touche `+0x18` dans AUCUNE branche de modification : c'est le maximum qui monte.
    Le `+extraHp` de PV COURANTS qui accompagne `1061` vient d'un `ChangeStat(Current, mode Add)`
    SEPARE. Confondre les deux doublerait le soin."""
    st = State()
    uid = _unite(st, hp=300, hp_max=1000)
    hc = st.get_entity(uid).get_component(HealthComponent)
    apply_change_stat(st, uid, int(StatType.HEALTH), SRC, EXTRA_HP)
    assert hc.hp == 300, "les PV courants ont bouge sur une modification de MAXIMUM : %s" % hc.hp


def test_override_et_remove_override_routent_AUSSI():
    """Les parts 7 / 8 (`OverrideMax` / `RemoveMaxOverride`) passent par le MEME dispatch natif que
    la part 5 -- les router a moitie laisserait un override HEALTH dans `UnitStats`."""
    st = State()
    uid = _unite(st, hp=300, hp_max=1000)
    hc = st.get_entity(uid).get_component(HealthComponent)
    apply_stat_override(st, uid, int(StatType.HEALTH), 4242, is_modifiable=True)
    assert hc.hp_max == 4242, hc.hp_max
    remove_stat_override(st, uid, int(StatType.HEALTH))
    assert hc.hp_max == 1000, hc.hp_max


def test_une_stat_NON_fillup_reste_dans_UnitStats():
    """Contre-epreuve du routage : `StatType.Attack` n'est PAS une case fill-up du switch natif,
    elle doit rester dans `UnitStats`. Sans ce cran, un routage trop large passerait inapercu."""
    st = State()
    uid = _unite(st)
    e = st.get_entity(uid)
    e.add_component(StatsComponent(ctx=type("C", (), {"stats": UnitStats()})()))
    apply_change_stat(st, uid, int(StatType.ATTACK), SRC, 1996)
    us = e.get_component(StatsComponent).ctx.stats
    assert us.get_stat(int(StatType.ATTACK), StatPart.MODIFICATION) == 1996


# ---------------------------------------------------------------------------------------------
# 3. La VENTILATION DES PARTS
# ---------------------------------------------------------------------------------------------

def test_Maximum_et_Initial_COINCIDENT_au_deploiement_et_DIVERGENT_ensuite():
    """⚠ LE PIEGE DE MESURE. `FillUpStatComponent$$Initialize` pose `+0x10 = +0x14`, donc au
    deploiement `StatPart.Maximum` et `StatPart.Initial` rendent la MEME valeur -- un banc pris la
    ne distingue AUCUN des deux ports. Ils se separent des qu'une modification existe : `Maximum`
    = `get_CurrentMaximumValue()`, `Initial` = le champ BRUT `+0x10`.

    C'est exactement pourquoi `context.py::_get_stat` ne peut plus ecrire `if p in (2, 3)`.

    Valeurs MESUREES live (`probe_572r1_hpmax_effectif.py`, gate ouvert de 1061) : avant
    10038/10038/10038, apres 20008/20008/10038 pour current/maximum/initial."""
    hc = HealthComponent(hp=10038, hp_max=10038)
    assert (hc.get_stat_part(StatPart.MAXIMUM), hc.get_stat_part(StatPart.INITIAL)) == (10038, 10038)
    hc.modify_max(SRC, EXTRA_HP)
    assert hc.get_stat_part(StatPart.MAXIMUM) == 20008, hc.get_stat_part(StatPart.MAXIMUM)
    assert hc.get_stat_part(StatPart.INITIAL) == 10038, (
        "`Initial` a suivi la modification : il doit rendre le champ BRUT +0x10 (%s)"
        % hc.get_stat_part(StatPart.INITIAL))
    assert hc.get_stat_part(StatPart.MODIFICATION) == EXTRA_HP
    assert hc.get_stat_part(StatPart.MISSING) == 20008 - 10038


def test_la_part_OVERRIDE_retombe_sur_le_champ_BRUT_pas_sur_le_maximum_effectif():
    """`GetStatPart` case 7 : `override ?? +0x14`. Le repli est la BASE, pas
    `get_CurrentMaximumValue()` -- lu, pas deduit."""
    hc = HealthComponent(hp=1, hp_max=1000)
    hc.modify_max(SRC, 500)
    assert hc.get_stat_part(StatPart.OVERRIDE) == 1000, hc.get_stat_part(StatPart.OVERRIDE)


def test_le_lecteur_DSL_voit_le_maximum_effectif():
    """Bout en bout : `ctx.get_stat` (le mirror d'`UnitExtensions$$GetStat` que lit le noeud
    `StatAmount`) doit rendre le maximum EFFECTIF. C'est ce que consomment `DeathNova`,
    `DespoiledGround`, `RammingSpeed` et le DoT de tuile via
    `StatAmount(..., StatType.HEALTH, StatPart.MAXIMUM)`."""
    from engine.runner.abilities.behaviours.context import entities_from_state
    st = State()
    uid = _unite(st, hp=10038, hp_max=10038)
    ent = entities_from_state(st, uid, uid)
    u = {"id": uid}
    assert ent.get_stat(u, int(StatType.HEALTH), int(StatPart.MAXIMUM)) == 10038
    st.get_entity(uid).get_component(HealthComponent).modify_max(SRC, EXTRA_HP)
    assert ent.get_stat(u, int(StatType.HEALTH), int(StatPart.MAXIMUM)) == 20008, (
        "le lecteur DSL ne voit pas la modification de maximum")
    assert ent.get_stat(u, int(StatType.HEALTH), int(StatPart.INITIAL)) == 10038, (
        "le lecteur DSL confond `Initial` et `Maximum`")


# ---------------------------------------------------------------------------------------------
# 4. Le DISPATCH natif -- TROIS stats, une seule couverte
# ---------------------------------------------------------------------------------------------

def test_le_dispatch_fillup_declare_ce_qu_il_ne_couvre_PAS():
    """`UnitExtensions$$ApplyStatModifier` a TROIS cases qui vont a
    `FillUpStatComponent$$ApplyModifier` : Armor(4), Health(5), NumberOfMembers(20).

    Etat depuis #572-r3 : HEALTH (composant ECS dedie) et NUMBER_OF_MEMBERS (`FillUpStatComponent`
    dans `UnitStats`) sont couvertes ; **ARMOR ne l'est pas, et c'est un VERDICT** -- mesure live
    (`probe_572r3_membres_et_armure.py`, 13 entites x 14 tours) : `observeBattle.armor` et
    `combatSnapshot.armorMax` valent 0 sur TOUTES, et aucune des configurations `lineup`/`npc`/
    `summons` du gameconfig ne porte de stat `Armor` (seulement `FixedArmor`). Router une stat dont
    le regime est vide serait un port SPECULATIF.

    ⚠ CE CRAN A DEJA ETE AVEUGLE UNE FOIS, et c'est pourquoi il derive desormais sa couverture au
    lieu de lire UNE table : #572-r3 a couvert NUMBER_OF_MEMBERS par une SECONDE voie
    (`_FILLUP_DANS_UNIT_STATS`), et la version precedente -- qui n'assertionnait que
    `_FILLUP_STAT_COMPONENTS` -- serait restee VERTE en le declarant toujours non couvert."""
    from engine.runner.operations.stat_ops import (_FILLUP_DANS_UNIT_STATS,
                                                   _FILLUP_STAT_COMPONENTS)
    from engine.entities.stats import _FILLUP_STATS
    assert {int(x) for x in _FILLUP_STATS} == {int(StatType.ARMOR), int(StatType.HEALTH),
                                               int(StatType.NUMBER_OF_MEMBERS)}, (
        "les TROIS cases fill-up du switch natif ont change : %s" % sorted(_FILLUP_STATS))
    couvertes = {int(x) for x in _FILLUP_STAT_COMPONENTS} | {int(x) for x in _FILLUP_DANS_UNIT_STATS}
    assert couvertes == {int(StatType.HEALTH), int(StatType.NUMBER_OF_MEMBERS)}, (
        "la couverture fill-up a change : %s -- si une stat a ete ajoutee ou perdue, mettre a "
        "jour #572-r3 et sa case-doc" % sorted(couvertes))
    assert int(StatType.ARMOR) not in couvertes, (
        "ARMOR est desormais routee : le verdict `regime vide` de #572-r3 doit etre re-mesure "
        "(un porteur a-t-il ete trouve ?) avant de porter quoi que ce soit")


def test_la_ValueModification_est_bien_attribuee_par_SOURCE():
    """Deux sources distinctes s'additionnent et se retirent INDEPENDAMMENT (`ValueModification`
    est un `Dictionary<sourceEntity, Modifier>`, pas un scalaire cumule)."""
    hc = HealthComponent(hp=1, hp_max=1000)
    hc.modify_max("a", 100)
    hc.modify_max("b", 250)
    assert hc.hp_max == 1350
    hc.reverse_max_modification("a")
    assert hc.hp_max == 1250
    assert hc.max_modification.get_modification_from_entity("b") == 250
    assert isinstance(hc.max_modification, ValueModification)
