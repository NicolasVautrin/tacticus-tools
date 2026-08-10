"""#572-r3 -- `StatType.NumberOfMembers` est un FILL-UP, pas un `StatComponent`.

GARDE de la tranche. Ce que la mesure live a etabli (`probe_572r3_membres_et_armure.py`, board
MC1_67 / seed 777, deux swarms a 5 membres, 14 tours) :

    membres  13 entites vues, 13 non nulles, 14 observations ou le NATIF SEPARE Current/Maximum
             -> 14 ecarts, TOUS sur `maximum` (natif 5, port 1..4 = les membres RESTANTS)
    armure   13 entites vues, 0 non nulle -> REGIME VIDE, rien a discriminer

Le natif separe les deux parts SANS aucune stat-modification, parce que son champ courant est
ENTRETENU : `IdunBattle.Operations.UpdateUnitMembersOperation$$Execute` pose
`NumberOfMembersComponent+0x18 = IBattleQuery.<slot 184 GetGroupUnitRemainingMemberCount>(unit,
null)`, appele apres chaque degat par `IdunBattle.Operations.ApplyDamageOperation$$
UpdateNumberOfMembersStat` (qui en rend `avant - apres` = les membres morts).

⚠ Ce fichier est OFFLINE : il rejoue le regime discriminant a partir des VALEURS mesurees, sans
runner. Le banc live est le probe.
"""
from __future__ import annotations

import pytest

from engine.entities.stats import (FillUpStatComponent, StatComponent, StatPart, StatType,
                                   UnitStats, compare_unit_stats, seed_unit_stats)
from engine.services.trait_damage_limits import group_unit_stat_part

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    # Ses DEUX foyers -- `engine/entities/stats.py` (le mirror `FillUpStatComponent`, le seed du
    # stat 20, l'agrement `compare_unit_stats`) et `engine/services/trait_damage_limits.py` (la
    # resolution DSL des parts) -- sont DEJA dans la cascade derivee par le foyer (#531), donc
    # les redeclarer serait du bruit.
    "chemins": (),
    "build": False,     # aucun acces au binaire ni a `data/symbols/**`
    "toujours": False,
    "raison": ("le fichier est purement OFFLINE et n'exerce que ces deux modules : il seede un "
               "`UnitStats` a partir des VALEURS mesurees en live (swarm 5 membres tombe a 1) "
               "puis lit ses parts. Il ne monte aucun runner, ne touche aucun etat ECS et ne lit "
               "aucune entree de `data/` -- sa fermeture d'imports tient entierement dans la "
               "cascade, ce que la proposition de `probe_486r15` confirme."),
}

#: La table `nom -> StatType` que publie `combatSnapshot.statTypes` (extrait utile).
STAT_IDS = {"numberOfMembers": int(StatType.NUMBER_OF_MEMBERS), "health": int(StatType.HEALTH)}

#: Le REGIME MESURE : un swarm de 5 membres tombe a 1 restant. `statDelta` du hook =
#: `GetStat(Current) - GetStat(Initial)` = restants - nrOfMembers = -(morts).
MEMBRES_TOTAL = 5
MEMBRES_RESTANTS = 1


def _seed(restants: int = MEMBRES_RESTANTS, total: int = MEMBRES_TOTAL) -> UnitStats:
    return seed_unit_stats({"numberOfMembers": restants},
                           {"numberOfMembers": restants - total}, STAT_IDS)


# ---------------------------------------------------------------------------------------------
# 1. Le REGIME DISCRIMINANT -- celui que la mesure live a produit
# ---------------------------------------------------------------------------------------------

def test_le_maximum_est_nrOfMembers_pas_les_membres_RESTANTS():
    """LE cran de la tranche. Avant #572-r3 le port rendait `1` ici (la valeur COURANTE), parce
    que `StatComponent$$GetStatPart` rend `get_CurrentValue()` pour les parts 0 ET 2."""
    us = _seed()
    assert us.get_stat(int(StatType.NUMBER_OF_MEMBERS), StatPart.CURRENT) == MEMBRES_RESTANTS
    assert us.get_stat(int(StatType.NUMBER_OF_MEMBERS), StatPart.MAXIMUM) == MEMBRES_TOTAL, (
        "le MAXIMUM rend les membres restants -- c'est l'ecart mesure 14 fois sur 14 en live")
    assert us.get_stat(int(StatType.NUMBER_OF_MEMBERS), StatPart.INITIAL) == MEMBRES_TOTAL
    # ANTI-DEGENERESCENCE : sans cette ligne, un port qui rendrait `Current` partout passerait
    # les deux assertions ci-dessus si le swarm etait intact.
    assert MEMBRES_RESTANTS != MEMBRES_TOTAL


def test_le_composant_seede_est_un_FILLUP_pas_un_StatComponent():
    """Le dispatch natif range `NumberOfMembers` sous `IdunBattle.Entities.Components.
    NumberOfMembersComponent`, qui herite de `FillUpStatComponent` (LU dans `classes.tsv`)."""
    comp = _seed().components[int(StatType.NUMBER_OF_MEMBERS)]
    assert isinstance(comp, FillUpStatComponent), type(comp).__name__
    assert not isinstance(comp, StatComponent)


def test_le_statDelta_d_un_fillup_ne_part_PAS_dans_la_ValueModification():
    """`+0x18 - +0x10` n'est pas `+0x28`. Le natif rendrait `GetStat(part 5) == 0` ici (aucune
    stat-modification n'a ete posee) ; le port le rendait a `-4`."""
    comp = _seed().components[int(StatType.NUMBER_OF_MEMBERS)]
    assert comp.get_stat_part(StatPart.MODIFICATION) == 0
    assert comp.modification.total == 0


def test_compare_unit_stats_n_exige_plus_la_part_modification_sur_un_fillup():
    """Corollaire du precedent : l'agrement `compare_unit_stats` compare `modification` au
    `statDelta` du hook, identite qui n'est vraie que pour `StatComponent$$get_CurrentValue`.
    Sur un fill-up elle est FAUSSE -- il ne doit donc pas la reclamer, mais il doit toujours
    comparer `current` et `initial`."""
    us = _seed()
    stats, delta = {"numberOfMembers": MEMBRES_RESTANTS}, {"numberOfMembers": -4}
    assert compare_unit_stats(us, stats, delta, STAT_IDS) == []
    # ... et il rougit toujours si le CURRENT diverge (le garde n'est pas devenu muet).
    us.components[int(StatType.NUMBER_OF_MEMBERS)].current = 3
    assert compare_unit_stats(us, stats, delta, STAT_IDS), (
        "compare_unit_stats est devenu aveugle au `current` d'un fill-up")


# ---------------------------------------------------------------------------------------------
# 2. Le mirror `FillUpStatComponent$$GetStatPart`, part par part
# ---------------------------------------------------------------------------------------------

def test_get_stat_part_mirror_les_sept_branches():
    """`current`=30, `base`=`initial`=100, puis une modification de +40 : les parts se SEPARENT."""
    f = FillUpStatComponent(current=30, maximum=100)
    assert f.get_stat_part(StatPart.CURRENT) == 30
    assert f.get_stat_part(StatPart.MAXIMUM) == 100
    assert f.get_stat_part(StatPart.INITIAL) == 100
    assert f.get_stat_part(StatPart.MISSING) == 70
    assert f.get_stat_part(StatPart.CURRENT_PCT) == 30
    assert f.get_stat_part(StatPart.OVERRIDE) == 100      # `override ?? +0x14`, PAS 0
    f.modify_max("src", 40)
    assert f.get_stat_part(StatPart.MAXIMUM) == 140, "la modification ne releve pas le maximum"
    assert f.get_stat_part(StatPart.INITIAL) == 100, "`Initial` a suivi la modification"
    assert f.get_stat_part(StatPart.CURRENT) == 30, "la modification a bouge la valeur COURANTE"
    assert f.get_stat_part(StatPart.MISSING) == 110
    assert f.get_stat_part(StatPart.MODIFICATION) == 40
    f.reverse_max_modification("src")
    assert f.get_stat_part(StatPart.MAXIMUM) == 100


def test_le_clamp_bas_de_get_CurrentMaximumValue():
    """`Math.Max(-initial, modTotal)` : une modification plus negative que l'initial est bornee."""
    f = FillUpStatComponent(current=5, maximum=100)
    f.modify_max("src", -500)
    assert f.get_current_maximum_value() == 0, f.get_current_maximum_value()


def test_l_override_prime_et_reste_modifiable():
    f = FillUpStatComponent(current=5, maximum=100)
    f.modify_max("src", 30)
    f.override_max(7, is_modifiable=True)
    assert f.get_stat_part(StatPart.MAXIMUM) == 37
    assert f.get_stat_part(StatPart.OVERRIDE) == 7
    f.remove_max_override()
    assert f.get_stat_part(StatPart.MAXIMUM) == 130


# ---------------------------------------------------------------------------------------------
# 3. `group_unit_stat_part` -- la resolution DSL, parts 2 et 3 SEPAREES
# ---------------------------------------------------------------------------------------------

def test_group_unit_stat_part_separe_maximum_et_initial():
    """Avant #572-r3 : `if p in (2, 3): return n` -- le piege de #873, transpose."""
    # 4 membres, 100 PV au total, 50 restants -> 2 membres restants.
    assert group_unit_stat_part(StatPart.CURRENT, 100, 4, 50) == 2
    assert group_unit_stat_part(StatPart.INITIAL, 100, 4, 50) == 4
    assert group_unit_stat_part(StatPart.MAXIMUM, 100, 4, 50) == 4          # sans maximum capte
    assert group_unit_stat_part(StatPart.MAXIMUM, 100, 4, 50, member_maximum=6) == 6
    assert group_unit_stat_part(StatPart.INITIAL, 100, 4, 50, member_maximum=6) == 4, (
        "`Initial` a suivi le maximum -- ce sont deux champs distincts (+0x10 vs +0x14/+0x28)")
    # `Missing` = max - current (et non n - current) : c'est ce que rend le natif.
    assert group_unit_stat_part(StatPart.MISSING, 100, 4, 50, member_maximum=6) == 4


def test_group_unit_stat_part_refuse_une_part_non_portee():
    with pytest.raises(ValueError):
        group_unit_stat_part(99, 100, 4, 50)
