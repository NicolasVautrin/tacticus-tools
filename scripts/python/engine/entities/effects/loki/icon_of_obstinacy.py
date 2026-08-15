"""Les DEUX effets du passif `IconOfObstinacy` (`TriggeredAbilityType` 0x610 = 1552) d'`astarLysander`.

Tache #919, face COMBAT. La face DECISION vit ailleurs et etait DEJA portee pour moitie :
`playbook/non_owner.py::IconOfObstinacyNonOwnerPlaybook` (#433-r4-r3-r1) et, depuis #919,
`playbook/adjacent_unit_preference.py::IconOfObstinacyPlaybook`.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================

Le passif est UNE entree de gameconfig mais **DEUX classes natives d'ability**, toutes deux
derivees d'`IdunBattleLogic.Entities.Abilities.Triggered.Loki.AIconOfObstinacyAbility` (parente LUE
dans `data/symbols/<build>/frida/classes.tsv`, jamais deduite d'un nom) :

  * `IconOfObstinacy_AddDamageBuffAbility` -> pose l'effet-AURA `IconOfObstinacy_ExtraDmg` (0x627)
    sur le PORTEUR, a l'init de l'ability ;
  * `IconOfObstinacy_AddArmourBuffAbility` -> pose l'effet `IconOfObstinacy_ExtraArmor` (0x628) sur
    l'unite qui vient de CLORE son tour sans avoir attaque, pour 1 round.

## 0. LE SELECTEUR PARTAGE -- `AIconOfObstinacyAbility$$GetAffectedUnits(dsl)`

    left = Owner@DSLSelectors+0x30
    return left + UnitsWithTrait( AdjacentFriends(left, unique = 1, selectionType = 3),
                                  0x40f, selectionType = 3 )

`0x40f` = 1039 = `UnitTrait`.TerminatorArmour (enum QUALIFIE ; les homonymes `EffectType` /
`ActiveAbilityType` a valeur egale n'ont rien a voir). `selectionType = 3` =
`OnlyAliveAndTargetable`.

⚠ **`Owner` est dans le set SANS condition de trait** -- `op_Addition` unit `left` au resultat
filtre, il ne le filtre pas. Le porteur beneficie donc de son propre passif meme s'il perdait
`TerminatorArmour`. C'est la difference structurelle avec `SurroundingFriends` (LionHelm), qui EXCLUT
la source : voir §2 pour la consequence sur le CANAL de port.

`AdjacentFriends(unit, unique, selectionType)` (surcharge a 3 arguments, tranchee par l'ARITE du
call-site) = `Friends(unit, Units(AdjacentTiles(unit), unique, selType) - unit, selType)` :
distance hex 1, meme equipe, la source retiree.

## 1. `IconOfObstinacy_ExtraArmourEffect` (EffectType 0x628 = 1576)

`.ctor` = `AStatModifierEffect( sourceAbility = AbilityOrEffect(TriggeredAbilityType 1552),
unitEffectType = null, canBeImmuneTo = 0, keepOnRevive = 1, ... )` ; parent LU dans `classes.tsv` :
`IdunBattle.Entities.Effects.ADynamicStatModifierEffect`.

Ce que la classe DECLARE (LU dans `global-metadata.dat` via `il2cpp_metadata.type_methods` -- deux
de ces corps sont FONDUS par l'ICF et donc INVISIBLES a `search_symbols_by_name`) :

    [.ctor, CreateActiveCondition (62), CreateTargetSelector (64), CreateRefreshValueTrigger (101),
     GetDynamicStatModificationAmount (102), GetCurrentExtraArmour, GetLocalizationDataInternal (77)]

Le bloc `methodPointers` du PE ancre sur le `.ctor` donne, dans ce MEME ordre, les deux corps
fondus :
  * `CreateActiveCondition` = corps partage avec
    `IdunBattle.Entities.Effects.Loki.WisdomOfTheAncients_DamageReductionEffect$$CreateActiveCondition`
    = `return <DSLTriggers+0x70>` -- le trigger CONSTANT du cache de `DSLTriggers$$.ctor`, aucune
    condition propre ;
  * `CreateTargetSelector` = corps partage avec
    `IdunBattle.Entities.Effects.Loki.WhisperingWebEffect$$CreateTargetSelector`
    = `return <DSLSelectors+0x30>` = **`Owner`**, c'est-a-dire l'unite QUI PORTE l'effet. Ce n'est
    donc PAS une aura : la stat est modifiee chez le porteur de l'instance.

`IdunBattle.Entities.Effects.Loki.IconOfObstinacy_ExtraArmourEffect$$GetDynamicStatModificationAmount(owner, target, effect)`
= `Nullable<int>( GetCurrentExtraArmour(target, effect) )`.

`IdunBattle.Entities.Effects.Loki.IconOfObstinacy_ExtraArmourEffect$$GetCurrentExtraArmour(target, effect)` :

    flat = AbilityConfiguration.GetVariableForLevel( config@0x60, 0x1b = extraArmor,
                                                     GetAbilityState(this), fallback = 0 )
    pct  = AbilityConfiguration.GetVariableForLevel( config@0x60, 0x3a = chance,
                                                     GetAbilityState(this), fallback = 0 )
    stat = UnitExtensions.GetStat( target, 0x8 = StatType.BlockDamage, 0x0 = StatPart.Current, null )
    node = DSLFormulas.PercentageOf( Get(stat), Get(pct), roundingRule = 0 )
    return <Calculate(node)> + flat

Le `statType` ECRIT est celui de la feuille de pose : `0x10` = `StatType.FixedArmor` (cf. §3).

`IdunBattle.Entities.Effects.Loki.IconOfObstinacy_ExtraArmourEffect$$CreateRefreshValueTrigger` :

    On( 0x38 = EventTriggerType.BlockDamageChanged ) & get_OwnerIsActor

-- la magnitude etant une fonction du `BlockDamage` COURANT de la cible, le natif re-calcule la
valeur quand ce stat bouge. RESIDU NOMME : ce vecteur de rafraichissement n'est PAS porte
(`On(0x38)` n'est emis par aucun site du port) ; la magnitude est donc figee a la POSE. Direction
de l'ecart : la valeur reste celle du `BlockDamage` a la fin du tour de la cible.

## 2. `IconOfObstinacy_ExtraDamageEffect` (EffectType 0x627 = 1575)

`.ctor` = `BaseEffect( AbilityOrEffect(TriggeredAbilityType 1552), hasAutomaticActivation = 1 )` ;
parent LU dans `classes.tsv` : `IdunBattle.Entities.Effects.BaseEffect`.

Methodes DECLAREES (metadata) :

    [.ctor, CreateActiveCondition (62), CreateTargetSelector (64),
     CreateEffectDamageBonusForAttack (78), GetCurrentExtraDamage, GetLocalizationDataInternal (77)]

`IdunBattle.Entities.Effects.Loki.IconOfObstinacy_ExtraDamageEffect$$CreateTargetSelector` =
`AIconOfObstinacyAbility$$GetAffectedUnits(this.dsl@0x48)` -- **le selecteur du §0**. L'effet vit
sur le porteur et RAYONNE : c'est une AURA, et son set contient le porteur LUI-MEME.

`IdunBattle.Entities.Effects.Loki.IconOfObstinacy_ExtraDamageEffect$$CreateEffectDamageBonusForAttack` :

    return EffectBonus.ForAddition( get_OwnerIsCaster, GetCurrentExtraDamage(),
                                    source = AbilityOrEffect(TriggeredAbilityType 1552) )

`IdunBattle.Entities.Effects.Loki.IconOfObstinacy_ExtraDamageEffect$$GetCurrentExtraDamage` :

    a   = DSLFormulas.ConfigVar( 0x8 = extraDmg, GetAbilityState(this), config@0x60 )
    b   = DSLFormulas.ConfigVar( 0x3a = chance,  GetAbilityState(this), config@0x60 )
    amt = DSLFormulas.StatAmount( Owner@DSLSelectors+0x30, 0x8 = StatType.BlockDamage,
                                  0x0 = StatPart.Current, modificationEntity = null, selType = 0 )
    return DSLFormulas.Sum( a, PercentageOf(amt, b, roundingRule = 0) )

⚠ **Le `StatAmount` porte sur `Owner`, pas sur le beneficiaire** : le `%` est pris sur le
`BlockDamage` de LYSANDER, meme quand c'est un ami Terminator qui frappe. La magnitude est donc
IDENTIQUE pour tous les beneficiaires -- c'est ce qui la rend calculable depuis le seul porteur.

⚠ **DEUX CANAUX de port, et ils sont DISJOINTS** (cf. l'avertissement de
`entities/effects/__init__.py::aura_attack_damage_bonus_from_allies`) : les agregateurs d'aura
EXCLUENT le beneficiaire lui-meme (`uid == att_id`), parce que `AdjacentFriends`/`SurroundingFriends`
excluent la source. Ici le selecteur ADDITIONNE `Owner`, donc la patte SELF passe par
`create_effect_damage_bonus_for_attack` (l'effet est sur l'attaquant) et la patte ALLIES par
`create_aura_attack_damage_bonus_for_ally`. Ni trou, ni double-compte : les deux canaux ne voient
jamais la meme unite.

## 3. LES DEUX POSEURS

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.IconOfObstinacy_AddDamageBuffAbility$$CreateTrigger`
(corps FONDU, partage avec
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WayOfTheShortBlade_InitAbility$$CreateTrigger`) :

    return DSLTriggers.OnOwnerSpecificAbilityInit( this.AbilityType@BaseTriggeredAbility+0x10 )
         = On(0x31 = SpecificAbilityInit) & <DSLTriggers+0x70> & get_OwnerIsActor
           & TriggeringAbilityIs(AbilityOrEffect(<type>))

`...IconOfObstinacy_AddDamageBuffAbility$$CreateBehaviour` :

    return DSLBehaviors.AddEffect( 0x627, abilityState = AbilityStateReference,
                                   source = Owner@0x30, targets = Owner@0x30, options = default )

-> owner-effect POSE A L'INIT, exactement le patron `PathOfCommand` : registre
`effects.factory.ABILITY_INIT_OWNER_EFFECTS`.

`...IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger` / `$$CreateBehaviour` : cf.
`runner/operations/triggers/loki/icon_of_obstinacy.py`, qui les porte.
"""
from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction

from ..base import BaseEffect
from ..magnitude import ability_var
from ....dsl.base import _round_fix64
from ...stats import StatPart, StatType
from ....services.effect_bonus import EffectBonus
from ...traits.unit_trait import UnitTrait
# #943-r7 -- les deux canaux du substrat d'adjacence NATIF, en FORME B (#485-r1-r1). Le ctx de
# `aura_attack_damage_bonus_from_allies` porte DEJA `board` sur ses DEUX faces (COMBAT
# `damage_model._apply_ally_attack_damage_auras`, PREDICTION `_shared._apply_ally_attack_dmg_bonus`)
# -- aucun seeding neuf. `pathfinding.board` n'importe RIEN de `engine`, `engine.battle_query`
# n'importe que `hexgeo` + `.hex_corner`.
from ...pathfinding import board as _board
from .... import battle_query as _bq

#: La cle gameconfig du passif -- `ability_var` l'utilise pour indexer `variables` par niveau et
#: pour appliquer (ou non) le multiplicateur de rarete. Le gameconfig `IconOfObstinacy` porte
#: `variablesAffectedByRarityBonus = ["extraDmg", "extraArmor"]` : `chance` en est EXCLUE, et c'est
#: `ability_var` qui porte ce gate -- on ne le re-implemente pas ici.
ICON_OF_OBSTINACY = "IconOfObstinacy"

EXTRA_ARMOR_VAR = "extraArmor"      # `AbilityVariableType` 0x1b = 27
EXTRA_DMG_VAR = "extraDmg"          # `AbilityVariableType` 0x08 = 8
CHANCE_VAR = "chance"               # `AbilityVariableType` 0x3a = 58

#: `UnitsWithTrait(AdjacentFriends(Owner), 0x40f, 3)` du selecteur partage (§0).
TERMINATOR_TRAIT = UnitTrait.TerminatorArmour       # 0x40f = 1039


def _percentage_of(base: int, pct: int) -> int:
    """`IdunBattle.Entities.Formulas.PercentageOf$$CalculateInternal` avec `roundingRule = 0`.

    Meme foyer de calcul que `ReinforcedHiveNodeExtraArmorEffect` : `Fraction` EXACTE (les deux
    arrondis intermediaires du natif sont exacts des que `pct` est entier, ce qu'est toute variable
    de gameconfig) puis `Fix64.Round` demi-vers-le-PAIR (`_round_fix64` mode 0)."""
    if not base or not pct:
        return 0
    return int(_round_fix64(Fraction(int(base) * int(pct), 100), 0))


class IconOfObstinacyExtraArmorEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.IconOfObstinacy_ExtraArmourEffect` (EffectType 0x628 = 1576).

    `ADynamicStatModifierEffect` a magnitude CONTEXTUELLE, pose sur l'unite qui vient de clore son
    tour sans avoir attaque (cf. le trigger, `runner/operations/triggers/loki/icon_of_obstinacy.py`),
    pour `TurnsFromRounds(1)`. Cf. §1 de l'en-tete du module.

    Canal de port : `applied_stat_mods(stats_ctx)` -- la forme OVERRIDE d'`ApplyModification`, parce
    que la magnitude lit une STAT DU PORTEUR (`GetStat(target, BlockDamage, Current)`) que
    `get_stat_modification_amount()` ne peut pas voir. `stats_ctx` EST le `StatsComponent.ctx` du
    porteur de l'instance, et le `target` du natif EST ce meme porteur (`CreateTargetSelector` =
    `Owner`, §1) : les deux substrats coincident, ce n'est pas une approximation."""

    def get_stat_modification_stat(self) -> "int | None":
        """`statType` de la feuille de pose : `0x10` = `StatType.FixedArmor` (LU au call-site
        `AddDynamicStatModifierEffect(..., 0x628, 0x10, ...)`, pas deduit du nom de l'effet).

        Declare meme sous la forme OVERRIDE : c'est lui que `refresh_stat_modifier_effects` lit pour
        savoir QUEL stat reverter."""
        return int(StatType.FIXED_ARMOR)

    def applied_stat_mods(self, stats_ctx) -> "list":
        """`GetCurrentExtraArmour(target, effect)` (§1) :

            flat + PercentageOf( GetStat(target, BlockDamage, Current), chance, roundingRule = 0 )

        Les DEUX variables sont indexees par l'`AbilityState` de la SOURCE (Lysander) -- c'est ce que
        `AddDynamicStatModifierEffect` propage dans `self.ability_level` /
        `self.ability_variables_multiplier` via son `AbilityStateReference` (+0x88).

        Niveau d'ability absent -> `[]` : la magnitude n'est PAS devinee (degradation fidele)."""
        if self.ability_level is None:
            return []
        mult = self.ability_variables_multiplier
        flat = int(ability_var(ICON_OF_OBSTINACY, EXTRA_ARMOR_VAR, self.ability_level,
                               multiplier_pct=mult) or 0)
        pct = int(ability_var(ICON_OF_OBSTINACY, CHANCE_VAR, self.ability_level,
                              multiplier_pct=mult) or 0)
        base = 0
        if stats_ctx is not None:
            # `UnitExtensions.GetStat(target, 0x8 = BlockDamage, 0x0 = Current, null)`
            base = int(stats_ctx.get_stat(int(StatType.BLOCK_DAMAGE), int(StatPart.CURRENT)) or 0)
        amt = flat + _percentage_of(base, pct)
        return [(int(StatType.FIXED_ARMOR), int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        """`AStatModifierEffect$$RevertModification` -- meme stat que l'apply."""
        return [int(StatType.FIXED_ARMOR)]


class IconOfObstinacyExtraDmgEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.IconOfObstinacy_ExtraDamageEffect` (EffectType 0x627 = 1575).

    AURA cote SOURCE : l'effet vit sur `astarLysander` (pose a l'init de l'ability, §3) et accorde
    un bonus de degat ADDITIF PAR COUP a `Owner + AdjacentFriends(Owner).WithTrait(TerminatorArmour)`
    (§0). Cf. §2 de l'en-tete pour les DEUX canaux, et pourquoi ils sont disjoints.

    ⚠ La magnitude ne depend QUE du porteur (`StatAmount(Owner@0x30, BlockDamage)`), jamais du
    beneficiaire : les deux canaux rendent donc la MEME valeur, calculee par `_current_extra_damage`."""

    def _current_extra_damage(self, owner_block_damage: "int | None") -> "int | None":
        """`GetCurrentExtraDamage` (§2) :

            ConfigVar(extraDmg) + PercentageOf( StatAmount(Owner, BlockDamage, Current), chance )

        `owner_block_damage is None` = le canal n'a pas publie le stat du porteur -> on rend le seul
        terme LISIBLE (`extraDmg`), jamais un `%` devine. C'est une degradation NOMMEE, pas un
        silence : le terme `%` manque, il n'est pas remplace."""
        if self.ability_level is None:                 # ConfigVar sans AbilityState -> pas de magnitude
            return None
        mult = self.ability_variables_multiplier
        flat = int(ability_var(ICON_OF_OBSTINACY, EXTRA_DMG_VAR, self.ability_level,
                               multiplier_pct=mult) or 0)
        pct = int(ability_var(ICON_OF_OBSTINACY, CHANCE_VAR, self.ability_level,
                              multiplier_pct=mult) or 0)
        amt = flat + _percentage_of(int(owner_block_damage or 0), pct)
        return amt or None

    def create_effect_damage_bonus_for_attack(self, is_ranged=None, has_moved=None,
                                              target_traits=None, is_prediction: bool = False,
                                              is_normal_attack=None, target_armor_reduced=None,
                                              att_ctx=None) -> "EffectBonus | None":
        """PATTE **SELF** : `Owner` est dans le set du selecteur (§0), et les agregateurs d'aura
        excluent le beneficiaire -- c'est donc ICI que le porteur touche son propre bonus.

        `get_OwnerIsCaster` est STRUCTURELLEMENT satisfait : ce canal n'est interroge que pour les
        effets portes par l'ATTAQUANT du coup courant. Aucun autre gate au decompile (ni
        `IsMeleeAttack`, ni `IsNormalAttack`, ni `CurrentAbilityIs`) -> le bonus s'applique a TOUTES
        ses attaques.

        `att_ctx["owner_block_damage"]` = le `BlockDamage` courant du PORTEUR de l'effet, qui EST
        l'attaquant sur ce canal. Cle ABSENTE -> seul le terme `extraDmg` est rendu (le `%` n'est pas
        devine) ; c'est la meme degradation NOMMEE que sur le canal aura."""
        amt = self._current_extra_damage((att_ctx or {}).get("owner_block_damage"))
        return EffectBonus("Addition", int(amt), True) if amt else None

    def create_aura_attack_damage_bonus_for_ally(self, ctx: Mapping | None = None) -> "EffectBonus | None":
        """PATTE **ALLIES** : `AdjacentFriends(Owner, unique, OnlyAliveAndTargetable)` filtre
        `UnitsWithTrait(TerminatorArmour)` (§0), evalue contre le ctx de l'agregateur.

        Le ctx porte `owner_*` (le PORTEUR de l'effet) et `att_*` (le beneficiaire qui attaque).
        `att_traits` est le substrat d'ENTITE (traits accordes en bataille compris), pas le kit --
        c'est bien ce qu'interroge `UnitExtensions$$HasTrait`.

        ⚠ L'adjacence passe par le FOYER `engine.battle_query.is_adjacent` depuis #943-r7 : la
        couronne hex nue qui vivait ici SUR-ATTEIGNAIT la liste stockee du `ConnectivityComponent`
        qu'enumere `AdjacentTiles`, et elle ignorait la porte `|elev(a) - elev(b)| < 2` de
        `TileQuery$$IterateAdjacentTiles` (#271). Le cablage est fait DANS LE MEME COMMIT que celui
        de l'AUTRE expression du meme `AIconOfObstinacyAbility$$GetAffectedUnits`
        (`runner/operations/triggers/loki/icon_of_obstinacy.py::icon_of_obstinacy_affected_units`) :
        les cabler separement aurait fait diverger le buff d'ARMURE du bonus de DEGAT, que le natif
        fait coincider par construction (c'est UN selecteur, pas deux)."""
        c = ctx or {}
        if c.get("owner_team") is None or c.get("owner_team") != c.get("att_team"):
            return None                                # `Friends` = meme equipe que le porteur
        opos, apos = c.get("owner_pos"), c.get("att_pos")
        if not opos or not apos:
            return None
        # `AdjacentFriends(Owner, unique, 3)` = `Friends(Owner, Units(AdjacentTiles(Owner)) - Owner,
        # 3)` -- l'ENUMERATION part du PORTEUR : `is_adjacent(owner, att)`, pas l'inverse.
        elev_by_pos, neigh_by_pos = _board.adjacency_channels(c.get("board"))
        if not _bq.is_adjacent(tuple(opos), tuple(apos), elev_by_pos, neigh_by_pos):
            return None
        if TERMINATOR_TRAIT.name not in (c.get("att_traits") or ()):   # `UnitsWithTrait(0x40f)`
            return None
        # `StatAmount(Owner@0x30, BlockDamage, Current)` -- la map est publiee PAR PORTEUR par le
        # site d'agregation, et `owner_id` est pose par `aura_attack_damage_bonus_from_allies` dans
        # le ctx par-carrier. Cle absente -> `None` -> seul `extraDmg` est rendu (cf.
        # `_current_extra_damage`), jamais un `%` devine.
        amt = self._current_extra_damage(
            (c.get("owner_stat_block_damage") or {}).get(c.get("owner_id")))
        return EffectBonus("Addition", int(amt), True) if amt else None
