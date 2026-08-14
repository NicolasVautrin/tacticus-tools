"""#1048 -- GARDE OFFLINE de `Hypermorph` (EffectType 0x54d = 1357), passif du summon
`genesSmnAberrant` et du npc `genesNpc1Aberrant`.

Ce que ce fichier FIGE (le probe `probe_1048_hypermorph.py` MESURE, ce test GARDE) :

  1. l'ARITHMETIQUE Fix64 de `IdunBattle.Entities.Effects.Loki.HypermorphEffect$$GetDynamicStat
     ModificationAmount`, valeur par valeur -- y compris les points ou elle DIVERGE de la regle de
     trois. Ces nombres sont MESURES (deux d'entre eux CONTRE LE NATIF : `hp = 2000 -> 299` et
     `hp = 900000 -> 134999`, `combatSnapshot.statDelta.attack` du 2026-08-14), pas derives ;
  2. le CABLAGE des deux registres (`EFFECT_CLASSES`, `ABILITY_INIT_OWNER_EFFECTS`) -- une entree
     qui disparait rend le passif MUET sans lever ;
  3. la chaine COMPLETE `applied_stat_mods(stats_ctx)` sur un `UnitStats` REEL (pas un stub) :
     c'est le canal que `effect_stat_modifications` privilegie (forme OVERRIDE d'`ApplyModification`)
     et celui que `refresh_stat_modifier_effects` re-joue quand les PV bougent.

DECLENCHEUR : ce fichier doit etre rejoue par toute tranche qui touche
`engine/entities/effects/loki/hypermorph.py`, `engine/entities/effects/factory.py`,
`engine/services/fix64.py`, `engine/entities/stats.py` (FillUpStatComponent / StatPart) ou
`engine/entities/effects/magnitude.py` (`ability_var`).
"""
from __future__ import annotations

import pytest

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
#: `chemins` est VIDE et c'est un RESULTAT : `probe_486r15 --proposer` mesure que la fermeture
#: d'imports de ce fichier (668 modules) tient ENTIEREMENT dans la cascade que le foyer derive
#: deja (#531) -- y declarer `engine/entities/effects/{loki/hypermorph,factory,base,magnitude}.py`,
#: `engine/services/fix64.py` ou `engine/entities/stats.py` serait une RECOPIE, pas un ajout.
#: `build: True` : la magnitude lit `GetNumberConstant(0x4f = healthPct)` dans le gameconfig
#: (`data/symbols/<build>/gameconfig.json`), qu'AUCUN import ne revele -- un changement de build
#: peut donc changer le verdict sans qu'aucun module Python ait bouge.
DECLENCHEUR = {
    "chemins": (),
    "build": True,
    "toujours": False,
    "raison": ("Garde la magnitude Fix64 de `HypermorphEffect$$GetDynamicStatModificationAmount` "
               "(valeurs MESUREES contre le natif) et le cablage des deux registres. Tout ce "
               "qu'il lit est soit dans la cascade derivee, soit dans le gameconfig -> `build`."),
}

from engine.entities.effects.factory import ABILITY_INIT_OWNER_EFFECTS, EFFECT_CLASSES
from engine.entities.effects.loki.hypermorph import (HypermorphEffect, hypermorph_extra_damage)
from engine.entities.effects.magnitude import ability_var
from engine.entities.effect_type import EffectType
from engine.entities.stats import FillUpStatComponent, StatType, UnitStats


class _Ctx:
    """Le strict minimum que `applied_stat_mods` consomme : `get_stat(statType, statPart)`.
    Le composant est un `FillUpStatComponent` REEL -- c'est lui que `UnitExtensions$$GetStat`
    interroge pour `StatType.Health`, et sa part 0 (`Current`) est le champ `+0x18`."""

    def __init__(self, hp: int, hp_max: int | None = None):
        self.stats = UnitStats()
        self.stats.set_component(int(StatType.HEALTH),
                                 FillUpStatComponent(current=int(hp),
                                                     maximum=int(hp_max if hp_max is not None
                                                                 else hp)))

    def get_stat(self, stat_type: int, stat_part: int = 0, source=None) -> int:
        return self.stats.get_stat(int(stat_type), int(stat_part), source)


def _effet() -> HypermorphEffect:
    """Instance telle que `load_state` la materialise : `name` = la cle d'`EFFECT_CLASSES`,
    `effect_type` = `EffectType.Hypermorph`."""
    return HypermorphEffect("Hypermorph", effect_type=int(EffectType.Hypermorph))


def test_constante_gameconfig():
    """`GetNumberConstant(0x4f = healthPct)` -- si elle bouge, tous les nombres ci-dessous sont
    a re-mesurer CONTRE LE NATIF, pas a re-deriver."""
    assert int(ability_var("Hypermorph", "healthPct", is_constant=True)) == 15


#: `(hp, montant natif)` -- les deux premieres lignes sont des GROUND TRUTH live
#: (`combatSnapshot.statDelta.attack`, 2026-08-14) ; les autres sont le mirror Fix64 sur les memes
#: PV que le probe imprime. La 3e colonne est la regle de trois, pour que la DIVERGENCE soit
#: visible dans le fichier plutot que deduite.
_TABLE = [
    (2000, 299, 300),        # GROUND TRUTH live (u83 et u85, --hp-player 2000)
    (900000, 134999, 135000),  # GROUND TRUTH live (--hp-player 900000)
    (75, 11, 11),            # PV naturels du summon au palier 1
    (4154, 623, 623),        # PV naturels du summon au palier 50
    (877274, 131591, 131591),  # GROUND TRUTH live apres blessure (volet D du probe)
    (20, 2, 3),
    (100, 14, 15),
    (1000, 149, 150),
    (1234, 185, 185),
    (2001, 300, 300),
]


@pytest.mark.parametrize("hp,attendu,naif", _TABLE)
def test_magnitude_fix64(hp, attendu, naif):
    """`(int)(Fix64(hp) * Round(pct/100*100, 0)/100)` -- `op_Explicit` est un FLOOR et `15/100`
    vaut `0.14999999997671694` en Q31.32, donc le natif rend UNE UNITE DE MOINS que la regle de
    trois des que le produit tombe juste."""
    assert hypermorph_extra_damage(hp, 15) == attendu
    assert hp * 15 // 100 == naif


def test_la_divergence_existe_vraiment():
    """Contre-epreuve du parametrage ci-dessus : si le mirror etait remplace par la regle de trois,
    la table serait toujours VERTE sur 7 de ses 10 lignes. On assertionne donc que l'ensemble des
    points de divergence est NON VIDE et qu'il est exactement celui des multiples de 20 (un test
    dont l'ensemble temoin serait vide passerait pour vert)."""
    div = [hp for hp in range(1, 4001) if hypermorph_extra_damage(hp, 15) != hp * 15 // 100]
    assert div, "aucun point de divergence -> ce fichier ne discrimine plus rien"
    assert len(div) == 200
    assert all(hp % 20 == 0 for hp in div)
    # Les lignes de `_TABLE` qui DISCRIMINENT (mirror != regle de trois) -- balayage borne a 4000,
    # d'ou le `900000` teste a part : c'est le SECOND ground truth live, et il diverge aussi.
    assert {t for t in _TABLE if t[1] != t[2] and t[0] <= 4000} == {
        (20, 2, 3), (100, 14, 15), (1000, 149, 150), (2000, 299, 300)}
    assert hypermorph_extra_damage(900000, 15) == 134999 != 900000 * 15 // 100


def test_registres_cables():
    """Le passif n'a AUCUN autre vecteur : sans l'entree `ABILITY_INIT_OWNER_EFFECTS` il n'est
    jamais pose sur un porteur ne offline, sans `EFFECT_CLASSES` l'instance seedee reste un dict
    inerte. Les deux disparaissent SANS erreur -- d'ou cette garde."""
    assert EFFECT_CLASSES.get("Hypermorph") is HypermorphEffect
    assert ABILITY_INIT_OWNER_EFFECTS.get("Hypermorph") == ["Hypermorph"]


def test_applied_stat_mods_chaine_complete():
    """Chaine reelle : `FillUpStatComponent(Health).get_stat_part(Current)` -> `ability_var` ->
    mirror Fix64 -> `(StatType.ATTACK, montant)`. C'est la forme OVERRIDE d'`ApplyModification`."""
    eff = _effet()
    assert eff.applied_stat_mods(_Ctx(2000)) == [(int(StatType.ATTACK), 299)]
    assert eff.applied_stat_mods(_Ctx(4154)) == [(int(StatType.ATTACK), 623)]
    assert eff.get_stat_modification_stat() == int(StatType.ATTACK)
    assert [int(s) for s in eff.reverted_stats()] == [int(StatType.ATTACK)]


def test_les_pv_lus_sont_les_COURANTS_pas_le_MAX():
    """`GetStat(target, 5, 0 = Current)` -- MESURE live : a `healthMax = 2000` et `health = 75`
    le natif rend 11, pas 299. Un port qui lirait `StatPart.MAXIMUM` serait vert sur tout le reste
    de ce fichier."""
    eff = _effet()
    assert eff.applied_stat_mods(_Ctx(75, hp_max=2000)) == [(int(StatType.ATTACK), 11)]


def test_degradation_sans_contexte():
    """`stats_ctx` absent ou PV nuls -> aucune contribution (jamais une magnitude devinee)."""
    eff = _effet()
    assert eff.applied_stat_mods(None) == []
    assert eff.applied_stat_mods(_Ctx(0)) == []
