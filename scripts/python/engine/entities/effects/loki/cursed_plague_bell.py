"""`CursedPlagueBell_ExtraMove` (EffectType 0x431 = 1073) -- le buff +MOUVEMENT de l'aura de
`deathBlightbringer` (<< Corrodius >>, Death Guard). Module dedie : contrairement aux deux autres
+MOVEMENT deja portes (`BlackRage_ExtraMove` 1342, `Waaagh_ExtraMovement` 1099, tous deux poses par
la feuille GENERIQUE `AddStaticStatModifierEffect`), celui-ci a une **classe d'effet NATIVE bespoke**
qui emet son `ChangeStat` elle-meme -- c'est la forme OVERRIDE d'`ApplyModification`.

i2 `Abilities/CursedPlagueBell_CurrentLevelDescription` : « Friendly Chaos units starting their turn
within Corrodius' Contagion aura gain +{[extraMovement]} Movement for this turn. »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- decompile = verite
================================================================================================

## Le VECTEUR de pose (hors perimetre de ce module, cite pour le contexte)

`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellMovementAbility$$CreateBehaviour` :

    AddEffect( 0x431 = 1073 CursedPlagueBell_ExtraMove,
               GetAbilityStateReference(this),
               UnitsWithoutTrait(
                   UnitsWithTrait(
                       SurroundingFriends( Caster@dsl+0x30,
                                           range  = ContagionsOfNurgleRange(Caster, 0, false),
                                           unique = true, unitSelectionType = 3 ),
                       0x7ea = 2026 Chaos, 3 ),
                   0x418 = 1048 Stationary, 3 ),
               turns = Nullable<int>(1) )

(`SurroundingFriends(unit, range, unique, unitSelectionType)` = `Friends(Units(SurroundingTiles(unit,
r) - Tiles(unit)))` -> le PORTEUR de l'aura est EXCLU de sa propre selection ; le 3e argument est
`unique`, PAS un « includeSelf ».)

(le meme selecteur est reutilise tel quel par
`IdunBattle.Entities.Effects.Loki.CursedPlagueBell_DangerZoneEffect$$CreateTargetSelector`, qui
rappelle `CursedPlagueBellMovementAbility$$GetTargetsSelector(dsl, isDangerZone = 1)`.)

## La CLASSE D'EFFET -- ce que ce module porte

`IdunBattle.Entities.Effects.Loki.CursedPlagueBell_ExtraMoveEffect` derive directement de
`IdunBattle.Entities.Effects.BaseEffect` (classes.tsv, taille 1152) et emet elle-meme son
`ChangeStat`. QUATRE corps natifs, DEUX a DEUX IDENTIQUES (folding IL2CPP -- `ApplyInternal`
delegue a `AddStatModifier`, `RevertInternal` a `RevertStatModifier`) :

    // CursedPlagueBell_ExtraMoveEffect$$ApplyInternal == $$AddStatModifier
    DSLBehaviors.ChangeStat( targets              = DSLSelectors.Entity(target),
                             stat                 = Stat(1 = Movement, 5 = Modification),
                             mode                 = 4 = ChangeStatMode.Modify,
                             amount               = DSLFormulas.Direct(
                                                        AbilityConfiguration.GetNumberConstant(
                                                            cfg@this+0x60, 0xe = extraMovement) ),
                             modificationEntity   = DSLSelectors.Entity(effect),
                             selectionType        = 1 = UnitSelectionType.OnlyAlive,
                             isModifiable         = false,
                             isHiddenModification = false )

    // CursedPlagueBell_ExtraMoveEffect$$RevertInternal == $$RevertStatModifier
    DSLBehaviors.ChangeStat( targets              = DSLSelectors.Entity(target),
                             stat                 = Stat(1 = Movement, 6 = ResetModification),
                             mode                 = 4 = ChangeStatMode.Modify,
                             amount               = <DSLFormulas+0x18> = Direct(0),
                             modificationEntity   = DSLSelectors.Entity(effect),
                             ... idem )

Lectures qui ne se devinent pas, et d'ou elles viennent :

* **L'ordre du struct `Stat`.** Le ctor est mislabele `UnityEngine.TerrainUtils.TerrainTileCoord$$.ctor`
  par ghidra ; ses deux litteraux sont `(1, 5)` a l'apply et `(1, 6)` au revert. C'est donc
  `(statType, part)` et non l'inverse : `IdunBattle.Entities.Enum.StatPart` vaut `5 = Modification` /
  `6 = ResetModification`, exactement la paire apply/revert que decrit deja
  `effects/__init__.py::effect_stat_mod_key` (« seule la `part` change, 5|9 a l'apply, 6 au revert »).
  Lu comme `(part, statType)` on obtiendrait `Health -> Shield` entre l'apply et le revert, ce qui
  n'a aucun sens. `IdunBattle.Entities.Enum.StatType` : `1 = Movement`.
* **`DSLFormulas+0x18` = `Direct(0)`.** `IdunBattleLogic.Entities.DSLFormulas$$.ctor` met en cache
  cinq `Direct` constants aux slots `+0x18 .. +0x38` : `0, 1, 2, 100, -1`. Le revert passe donc un
  montant NUL -- c'est la `part = ResetModification` qui retire la contribution, pas le montant.
* **La constante lue est `0xe = extraMovement`** (`IdunBattle.Configuration.AbilityConstantType`),
  = `"1"` au gameconfig de l'ability `CursedPlagueBell`. La MEME constante est relue par
  `IdunBattle.Entities.Effects.Loki.CursedPlagueBell_DangerZoneEffect$$GetExtraMovementAmount` et par
  `...$$CreateRangeBonusForDangerZone` (le pendant PREDICTION de la zone de danger, non porte ici).
* **`modificationEntity = Entity(effect)`** : la contribution est attribuee a l'ENTITE-EFFET, donc
  UNE seule entree `ValueModification.per_source` par instance -- exactement l'invariant que decrit
  `effects/__init__.py::effect_stat_mod_key`, et ce qui rend le retrait exact.

================================================================================================
FORME DU PORT
================================================================================================
Canal EAGER `applied_stat_mods` (forme OVERRIDE d'`ApplyModification`), PAS le couple declaratif
`get_stat_modification_stat`/`_amount` (forme mono-stat de `AStatModifierEffect`) : le natif ne
passe justement PAS par la base -- il override, comme `BlackRage_ExtraMove` / `Waaagh_ExtraMovement`
et comme `ActOfFaithBuffEffect`. `reverted_stats()` en est le symetrique exact (le
`Stat(Movement, ResetModification)` ci-dessus) : c'est LUI qui fait sortir la contribution du residu
opaque `CAPTURED_SOURCE` au seed (`UnitContext.from_snapshot` PASSE 2) et la rend RETIRABLE a
l'expiration du tour (`RemoveEffect` -> `revert_change_stat`, cle `statmod_source_key`).

AUCUN `CreateActiveCondition` n'existe cote natif pour cette classe (contrairement a
`DestroyTheWitch_ExtraMove`, qui en a un et passe donc par le canal declaratif) : la duree de vie de
l'effet est portee par le `turns = 1` du vecteur `AddEffect`, pas par une condition d'activite.

Ce n'est PAS l'argument « absent de la table » (qui ne prouve rien, cf. CLAUDE.md) : le bloc de code
des deux classes `CursedPlagueBell_*Effect` est CONTIGU et SANS TROU dans
`data/symbols/<build>/ghidra/functions.tsv`, encadre par `CrushingStrikeEffect$$.ctor` avant et
`SynapseEffect$$ApplyInternal` apres — `CreateRangeBonusForDangerZone`, `CreateTargetSelector`,
`GetExtraMovementAmount`, `.ctor` (DangerZone) puis les QUATRE corps d'ExtraMove. Les voisins
montrent qu'une classe d'effet emet toutes ses methodes d'affilee, et `DangerZoneEffect` y a bien son
`CreateTargetSelector` la ou `ExtraMoveEffect` n'en a pas. Cette classe ne surcharge donc que ces
quatre corps : aucune contribution aux canaux degat / coups / percage non plus.

NON PORTE ICI, explicitement : `CursedPlagueBell_DangerZoneEffect` (1084) et son
`CreateRangeBonusForDangerZone` -- meme constante `extraMovement`, mais c'est l'axe PREDICTION de
zone de danger de l'IA, un autre canal (`RangeBonusForDangerZone`), pas un stat-mod.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var

CURSED_PLAGUE_BELL = "CursedPlagueBell"
CONST_EXTRA_MOVEMENT = 0xe          # AbilityConstantType.extraMovement (GetNumberConstant(cfg, 0xe))


class CursedPlagueBellExtraMoveEffect(BaseEffect):
    """`CursedPlagueBell_ExtraMove` (EffectType 0x431 = 1073) -- +`extraMovement` (= 1) a la stat
    MOVEMENT du porteur, pose pour UN tour sur les amis **Chaos** non-`Stationary` dans l'aura
    `ContagionsOfNurgle` de `deathBlightbringer`.

    Mirror de `IdunBattle.Entities.Effects.Loki.CursedPlagueBell_ExtraMoveEffect$$ApplyInternal`
    (== `$$AddStatModifier`) : `ChangeStat(Entity(target), Stat(Movement, Modification), Modify,
    Direct(GetNumberConstant(0xe)), Entity(effect), OnlyAlive, false, false)`.
    `reverted_stats` mirror `$$RevertInternal` (== `$$RevertStatModifier`), qui rejoue le MEME appel
    avec `Stat(Movement, ResetModification)` et la MEME `Entity(effect)` en source."""

    def applied_stat_mods(self, stats_ctx) -> "list":
        from ...stats import StatType
        # `Direct(AbilityConfiguration.GetNumberConstant(cfg, 0xe))` = constante gameconfig
        # `extraMovement` de l'ability `CursedPlagueBell` (= 1). CONSTANTE : hors
        # `variablesAffectedByRarityBonus`, donc ni niveau ni multiplier de rarete.
        amt = ability_var(CURSED_PLAGUE_BELL, "extraMovement", is_constant=True)
        return [(int(StatType.MOVEMENT), int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        from ...stats import StatType
        return [StatType.MOVEMENT]                      # Stat(1 = Movement, 6 = ResetModification)
