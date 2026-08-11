"""Les TROIS owner-effects PROJETES du passif de kit `PropheticSentinel` (`thousSekhetar`
<< Sekhetar Robot >>, `TriggeredAbilityType` 0x607 = 1543) -- 1558 / 1559 / 1560.

Ce sont des **AURAS**, pas des self-buffs : l'entite-effet vit sur le PORTEUR (`decisionView.effects`
la liste chez lui) mais la MODIFICATION DE STAT est ecrite chez les unites de son
`CreateTargetSelector`. Meme patron que `LionHelm` (`dark_angels_passives.py`) et
`UnbreakableDuty_DamageReduction` -- et c'est le piege du kit : le `CreateBehaviour` dit
`AddStaticStatModifierEffect**ToOwner**`, ce qui se lit comme un self-buff, alors que la projection
vit UN ETAGE PLUS BAS, dans la classe d'effet.

ARTEFACT NATIF (decompile ghidra, build `rnca9r7q6c`) --
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.PropheticSentinel_AddBuffAbility$$CreateBehaviour`
(MIRROR 1:1, les trois volets joints par `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd`) :

    AddStaticStatModifierEffectToOwner( 0x616 = 1558 PropheticSentinel_ExtraArmor,
                                        stat = 0x10 = FixedArmor,
                                        Direct( GetVariableForLevel(0x1b = extraArmor) ),
                                        turns = NULL, isHidden = false )
  & AddStaticStatModifierEffectToOwner( 0x617 = 1559 PropheticSentinel_ExtraBlockChance,
                                        stat = 0x7  = BlockChance,
                                        Direct( GetVariableForLevel(0x15 = blockChance) ),
                                        turns = NULL, isHidden = false )
  & AddStaticStatModifierEffectToOwner( 0x618 = 1560 PropheticSentinel_ExtraBlockDamage,
                                        stat = 0x8  = BlockDamage,
                                        Direct( GetVariableForLevel(0x14 = blockDmg) ),
                                        turns = NULL, isHidden = false )

`turns = NULL` => PERMANENTS. Le TRIGGER de ce behaviour est le corps HERITE
`<DSLTriggers+0x30>` = `On(0x21 = AbilityInit) & <conjoint @+0x70> & get_OwnerIsActor` -- le corps de
`PropheticSentinel_AddBuffAbility$$CreateTrigger` est un fold ICF vers
`IdunBattleLogic.Entities.Abilities.Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`
(`return <+0x30>`), depart LU dans la table des pointeurs de methodes, pas suppose. C'est la MEME
constante que `LionHelmAbility` / `AnvilShieldAbility` / `ListenUpMaggotsAbility`.
=> canal de pose = `ABILITY_INIT_OWNER_EFFECTS`, jamais `ABILITY_TRIGGERS`.

## LES DEUX SELECTEURS -- et ils DIFFERENT (c'est tout l'interet du kit)

Le build porte DEUX classes d'effet pour ce passif, chacune avec son `CreateTargetSelector` :

    IdunBattle.Entities.Effects.Idun.PropheticSentinel_PsykerEffect$$CreateTargetSelector
        UnitsWithTrait( AdjacentFriends(Owner@DSLSelectors+0x30, unique = 1, selectionType = 3),
                        0x3ea = UnitTrait.Psyker, 3 )
    IdunBattle.Entities.Effects.Idun.PropheticSentinel_ChaosEffect$$CreateTargetSelector
        UnitsWithTrait( AdjacentFriends(Owner@+0x30, 1, 3), 0x7ea = UnitTrait.Chaos, 3 )
        -- corps DEDUPLIQUE (ICF) avec
        `IdunBattle.Entities.Effects.Loki.ExplosiveMaladies_ExtraMeleeAttackEffect$$CreateTargetSelector`,
        d'ou son absence sous ce nom dans `frida/methods.tsv`.

L'APPARIEMENT effectType -> selecteur n'est PAS lisible offline (`AStatModifierEffect$$.ctor` ne
porte pas l'effectType ; deux classes pour trois ids). Il est **MESURE LIVE**, en regime
DISCRIMINANT -- quatre voisins tous ADJACENTS au porteur, `statModSources` (runner MC1_67, seed 915,
placement force, porteur ablvl 50 / multiplier 180) :

    voisin                        traits                    fixedArmor  blockChance  blockDamage
    thousAhriman        (2,1)     Psyker + Chaos                   898           25          898
    deathBlightbringer  (1,2)     Chaos, NON-Psyker                898            -            -
    astraPrimarisPsy    (3,2)     Psyker, Imperial (non-Chaos)       -           25          898
    adeptCanoness       (2,3)     ni Psyker ni Chaos                 -            -            -
    thousSekhetar       (2,2)     LE PORTEUR                         -            -            -

=> `1558 ExtraArmor` porte le selecteur **CHAOS** ; `1559 ExtraBlockChance` et `1560
ExtraBlockDamage` portent le selecteur **PSYKER**. Le porteur ne recoit RIEN (`AdjacentFriends`
retire sa propre tuile). Les quatre regimes sont NON DEGENERES : chaque colonne a un temoin positif
ET un temoin negatif, et aucune ligne n'est vide-partout.

⚠ NE PAS transposer le predicat de la face DECISION : `PropheticSentinelNonOwnerPlaybook` CUMULE
Psyker (20) et Chaos (20) sur la MEME unite, et `PropheticSentinelPlaybook` (face owner) ne connait
que Psyker. Trois predicats coexistent dans ce kit, deux a deux differents.

## MAGNITUDES

`GetVariableForLevel` => VARIABLES per-niveau de `PropheticSentinel.variables` : `extraArmor`
(9..655), `blockChance` (15/20/25, plateau), `blockDmg` (9..655).
`variablesAffectedByRarityBonus = ['extraArmor', 'blockDmg']` => ces DEUX-LA sont scalees par
l'`AbilityVariablesMultiplierPercentage` du PORTEUR ; `blockChance` ne l'est PAS. La mesure le
confirme : a ablvl 50 / mult 180, `extraArmor` 499 -> **898** et `blockDmg` 499 -> **898**, tandis
que `blockChance` reste **25** (la valeur brute du tableau).

`PropheticSentinel` est un PASSIF => le niveau qui indexe `variables[level]` est `ability_level` de
l'instance d'effet (qui vit sur le porteur), jamais celui du buffe -- meme regime que LionHelm, dont
le `GetDynamicStatModificationAmount` lit `ConfigVar(..., EffectSource(Get(effect)), ...)`.

## Qualification des enums (le meme id nomme autre chose ailleurs)

    EffectType 1558/1559/1560 PropheticSentinel_ExtraArmor / _ExtraBlockChance / _ExtraBlockDamage
        != TriggeredAbilityType 1558 Helspear
    TriggeredAbilityType 1543 PropheticSentinel != EffectType 1543 ModifiedExoarmour_PierceReduction
    StatType 0x10 = FixedArmor · 0x7 = BlockChance · 0x8 = BlockDamage
    AbilityVariableType 0x1b = extraArmor · 0x15 = blockChance · 0x14 = blockDmg
    UnitTrait 0x3ea = 1002 Psyker  (!= EffectType 1002 CombatRestoratives)
    UnitTrait 0x7ea = 2026 Chaos   -- le trait de GRANDE ALLIANCE
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
from ....entities.stats import StatType
from ....entities.traits.unit_trait import UnitTrait

_ABILITY_ID = "PropheticSentinel"                 # TriggeredAbilityType 0x607 = 1543
#: `unitSelectionType` LU au dernier argument des DEUX `DSLSelectors$$*` des selecteurs natifs.
_SELECTION = 3                                    # UnitSelectionType.OnlyAliveAndTargetable


def adjacent_friends_with_trait(state, owner_id: int, trait: int) -> list:
    """`UnitsWithTrait( AdjacentFriends(Owner@+0x30, unique = 1, selectionType = 3), <trait>, 3 )`
    evalue contre l'ECS -- FOYER PARTAGE des trois effets (le natif partage lui aussi le noeud de
    tete entre ses deux classes, seul le trait change).

    Doctrine #149 : l'artefact natif est un SELECTEUR, donc le port EVALUE L'ARBRE plutot que de
    recabler une boucle. L'arbre passe par `dsl/base._within(order='adjacent')`, c.-a-d. la LISTE
    D'ADJACENCE STOCKEE du board -- le meme substrat que
    `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`, et non un
    `hexgeo.distance <= 1` qui sur-compterait (#589-r1-r1-r2-r1-r8).

    ⚠ C'est aussi pourquoi ce module n'utilise PAS `aura_selectors.surrounding_friends` (le foyer de
    LionHelm) : celui-la mirrore `SurroundingFriends`, un DISQUE `IterateSurroundingTiles` a rayon
    parametrable ; ici le natif appelle `AdjacentFriends`, une primitive DIFFERENTE. Les deux
    coincident sur un plateau plat, pas sur une porte d'elevation.

    Imports DIFFERES -- PORTEURS : `entities/selectors` et `runner/abilities/behaviours/context`
    sont assembles APRES le paquet `entities/effects` (charger `context` au niveau module ferme le
    cycle `effects -> runner -> effects`). Meme convention que
    `effects/loki/amulet_of_the_voidwyrm.py::adjacent_friendly_summons_and_decoys_selector`."""
    from ...selectors.accessors import Owner
    from ...selectors.units import AdjacentFriends, UnitsWithTrait
    from ....dsl.base import Const
    from ....runner.abilities.behaviours.context import entities_from_state
    sel = UnitsWithTrait(
        AdjacentFriends(Owner(), Const(1), Owner(), selection_type=_SELECTION),
        int(trait), selection_type=_SELECTION)
    ents = entities_from_state(state, int(owner_id))
    out: list = []
    for u in (sel.select(ents) or ()):
        uid = u.get("id") if isinstance(u, dict) else None
        if uid is not None:
            out.append(int(uid))
    return out


class _PropheticSentinelAuraStatModEffect(BaseEffect):
    """Socle des TROIS `StaticStatModifierEffect` PROJETES de `PropheticSentinel`.

    INTERFACE PORT (duck-typed, consommee par `runner/operations/aura_stat_mods.py` --
    `attribute_aura_stat_modifiers` au SEED et `refresh_aura_stat_modifiers` a chaque
    `MoveUnitOperation`, exactement comme LionHelm) :
      * `aura_stat_modification_stat()`   -> le `StatType` ecrit chez la cible ;
      * `aura_stat_modification_amount()` -> la magnitude, indexee sur l'`AbilityState` de la SOURCE ;
      * `aura_stat_modification_targets(state, owner_id)` -> les entity-ids selectionnes.

    Elle est VOLONTAIREMENT hors de `BaseEffect` (interrogation par `getattr`, meme regime que
    `TARGETING_OPTIONS`). PAS de `get_stat_modification_stat/amount` ici : ce couple-la ecrit sur le
    PORTEUR, et la mesure live etablit qu'il ne recoit RIEN -- le declarer donnerait au Sekhetar un
    bonus que le natif n'accorde pas, et ce serait un ecart SILENCIEUX (aucune erreur, juste une
    armure trop haute)."""

    _VAR = ""                    # cle gameconfig de la magnitude
    _STAT = 0                    # StatType ecrit chez la cible
    _TRAIT = 0                   # trait du `UnitsWithTrait` de CE selecteur

    def aura_stat_modification_stat(self) -> int:
        return int(self._STAT)

    def aura_stat_modification_amount(self) -> "int | None":
        if self.ability_level is None:
            return None                            # ConfigVar sans AbilityState -> pas de magnitude
        return ability_var(_ABILITY_ID, self._VAR, self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)

    def aura_stat_modification_targets(self, state, owner_id: int) -> list:
        return adjacent_friends_with_trait(state, owner_id, self._TRAIT)


class PropheticSentinelExtraArmorEffect(_PropheticSentinelAuraStatModEffect):
    """`PropheticSentinel_ExtraArmor` (0x616 = 1558) -- +`extraArmor` sur `FixedArmor` des amis
    ADJACENTS a trait **CHAOS**.

    Selecteur = celui de `PropheticSentinel_ChaosEffect` (`UnitsWithTrait(AdjacentFriends(Owner),
    0x7ea = Chaos, 3)`), APPARIE PAR LA MESURE : `deathBlightbringer` (Chaos non-Psyker, adjacent)
    recoit +898 fixedArmor et RIEN d'autre ; `astraPrimarisPsy` (Psyker non-Chaos, adjacent) ne
    recoit PAS de fixedArmor. `extraArmor` est dans `variablesAffectedByRarityBonus` -> scalee."""

    _VAR = "extraArmor"
    _STAT = StatType.FIXED_ARMOR                                  # StatType 0x10
    _TRAIT = UnitTrait.Chaos                                      # 0x7ea = 2026


class PropheticSentinelExtraBlockChanceEffect(_PropheticSentinelAuraStatModEffect):
    """`PropheticSentinel_ExtraBlockChance` (0x617 = 1559) -- +`blockChance` sur `BlockChance` des
    amis ADJACENTS a trait **PSYKER**.

    ⚠ `blockChance` est HORS `variablesAffectedByRarityBonus` -> le multiplicateur est INERTE ; il
    est passe pour la forme (meme convention que `VexillaMagnifica`/`SereneUnifier`), et la mesure
    live le CONFIRME (25 a mult 180, pas 45)."""

    _VAR = "blockChance"
    _STAT = StatType.BLOCK_CHANCE                                 # StatType 0x7
    _TRAIT = UnitTrait.Psyker                                     # 0x3ea = 1002


class PropheticSentinelExtraBlockDamageEffect(_PropheticSentinelAuraStatModEffect):
    """`PropheticSentinel_ExtraBlockDamage` (0x618 = 1560) -- +`blockDmg` sur `BlockDamage` des amis
    ADJACENTS a trait **PSYKER**.

    ⚠ `blockDmg` (0x14) et `blockChance` (0x15) sont ADJACENTS dans `AbilityVariableType` et leurs
    deux tableaux gameconfig ont la MEME longueur : les intervertir ne leverait AUCUNE erreur et
    donnerait +25 de degat de blocage la ou le natif met +898. Les deux index sont LUS au decompile
    (`GetVariableForLevel(.., 0x15, ..)` precede `0x14` dans le corps), pas deduits du nom -- et la
    mesure live les separe (25 vs 898 sur la MEME unite)."""

    _VAR = "blockDmg"
    _STAT = StatType.BLOCK_DAMAGE                                 # StatType 0x8
    _TRAIT = UnitTrait.Psyker                                     # 0x3ea = 1002
