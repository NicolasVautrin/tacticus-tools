"""`RelentlessMarch_Effect` (`EffectType` 0x3f3 = 1011) -- le buff +MOUVEMENT du passif
`RelentlessMarch` de `necroWarden` << Makhotep >> (Necrons). #328.

Le VECTEUR de pose vit ailleurs (cite pour le contexte) :
`IdunBattleLogic.Entities.Abilities.Active.Loki.RelentlessMarchAbility$$CreateBehaviour` =
`AddEffect(0x3f3, AbilityStateReference, UnitsWithoutTrait(Friends(AdjacentUnits(Owner)),
0x418 Stationary), turns = Nullable<int>(1))` -- cf.
`engine/runner/operations/triggers/loki/relentless_march.py` et `docs/rl/case-328-relentless-march.md`.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================
`IdunBattle.Entities.Effects.Loki.RelentlessMarchEffect` derive de
`IdunBattle.Entities.Effects.BaseEffect` (`classes.tsv`, taille 1152) et emet elle-meme son
`ChangeStat` : c'est la forme OVERRIDE d'`ApplyModification`, pas le couple declaratif d'
`AStatModifierEffect`. QUATRE corps natifs, DEUX A DEUX IDENTIQUES (folding IL2CPP --
`$$ApplyInternal` == `$$AddStatModifier`, `$$RevertInternal` == `$$RevertStatModifier`) :

    // RelentlessMarchEffect$$ApplyInternal == $$AddStatModifier
    DSLBehaviors.ChangeStat( targets            = DSLSelectors.Entity(target),
                             stat               = Stat(1 = Movement, 5 = Modification),
                             mode               = 4 = ChangeStatMode.Modify,
                             amount             = DSLFormulas.Direct(1),
                             modificationEntity = DSLSelectors.Entity(effect),
                             selectionType      = 3, isModifiable = false,
                             isHiddenModification = false )

    // RelentlessMarchEffect$$RevertInternal == $$RevertStatModifier
    ... stat = Stat(1 = Movement, 6 = ResetModification), amount = <DSLFormulas+0x18> = Direct(0)

⚠ ECART AVEC `CursedPlagueBell_ExtraMoveEffect`, et c'est le piege du cas : la-bas le montant vient
de `AbilityConfiguration.GetNumberConstant(cfg, 0xe = extraMovement)` ; **ICI c'est le LITTERAL 1**
passe a `IdunBattleLogic.Entities.DSLFormulas$$Direct`. L'ability `RelentlessMarch` n'a d'ailleurs
AUCUNE constante au gameconfig (`variables = {hpToRepair}` seulement) -- transposer le patron du
voisin aurait lu un `extraMovement` INEXISTANT, rendu 0, et le +1 Mouvement aurait ete silencieusement
INERTE.

Lectures partagees avec `cursed_plague_bell.py`, non re-derivees ici :
  * l'ordre du struct `Stat` est `(statType, part)` -- le ctor est mislabele
    `UnityEngine.TerrainUtils.TerrainTileCoord$$.ctor` par ghidra, et ses deux litteraux sont `(1, 5)`
    a l'apply / `(1, 6)` au revert (`IdunBattle.Entities.Enum.StatPart` : 5 = `Modification`,
    6 = `ResetModification` ; `StatType` : 1 = `Movement`) ;
  * `<DSLFormulas+0x18>` = `Direct(0)` (le ctor de `DSLFormulas` met en cache 0, 1, 2, 100, -1 aux
    slots +0x18..+0x38) : c'est la `part = ResetModification` qui retire la contribution, pas le
    montant ;
  * `modificationEntity = Entity(effect)` : la contribution est attribuee a l'ENTITE-EFFET, donc UNE
    seule entree `ValueModification.per_source` par instance -- ce qui rend le retrait exact.

FORME DU PORT : canal EAGER `applied_stat_mods` + son symetrique `reverted_stats()`, comme
`CursedPlagueBellExtraMoveEffect`. AUCUN `CreateActiveCondition` n'existe pour cette classe : la duree
de vie est portee par le `turns = 1` du vecteur `AddEffect`.
"""
from __future__ import annotations

from ..base import BaseEffect
from ...stats import StatType

# `DSLFormulas$$Direct(1)` -- LITTERAL du decompile, pas une constante gameconfig (cf. l'en-tete).
RELENTLESS_MARCH_EXTRA_MOVEMENT = 1


class RelentlessMarchExtraMoveEffect(BaseEffect):
    """`RelentlessMarch_Effect` (`EffectType` 0x3f3 = 1011) -- +1 a la stat MOVEMENT du porteur,
    pose pour UN tour sur les allies adjacents NON-`Stationary` de `necroWarden`.

    Mirror de `IdunBattle.Entities.Effects.Loki.RelentlessMarchEffect$$ApplyInternal`
    (== `$$AddStatModifier`) : `ChangeStat(Entity(target), Stat(Movement, Modification), Modify,
    Direct(1), Entity(effect), 3, false, false)`. `reverted_stats` mirror `$$RevertInternal`
    (== `$$RevertStatModifier`), qui rejoue le MEME appel avec `Stat(Movement, ResetModification)`."""

    def applied_stat_mods(self, stats_ctx) -> "list":
        return [(int(StatType.MOVEMENT), RELENTLESS_MARCH_EXTRA_MOVEMENT)]

    def reverted_stats(self) -> "list":
        return [StatType.MOVEMENT]              # Stat(1 = Movement, 6 = ResetModification)
