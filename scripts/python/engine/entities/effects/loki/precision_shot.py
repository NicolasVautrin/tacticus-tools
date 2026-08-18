"""`PrecisionShot_Aim` (0x3f7 = 1015 `EffectType`) -- l'effet de VISEE que `1012
PrecisionShot_AimAbility` pose sur son propre caster, et qui ARTICULE tout le triptyque
`PrecisionShot` (#996-r1-r3).

⚠ **L'ORDINAL 1015 DESIGNE DEUX CHOSES**, et les deux vivent dans cette tranche :
`EffectType.PrecisionShot_Aim` (cet effet) et `ActiveAbilityType.PrecisionShot` (l'ability facade).
Les trois `GetDynamicInvalidCasterReason` du triptyque lisent le PREMIER
(`EntityExtensions.HasEffect(caster, state, 0x3f7, onlyActive: 0)`), le
`SetActiveAbilityUsed(Owner, 0x3f7)` de 1012 ecrit le SECOND.

`IdunBattle.Entities.Effects.Loki.PrecisionShot_AimEffect$$.ctor` =
`BaseEffect(AbilityOrEffect(<...>), hasAutomaticActivation: 1)`.

CE QUI EST PORTE -- le SOUS-EFFET
---------------------------------
`IdunBattle.Entities.Effects.Loki.PrecisionShot_AimEffect$$BlockMovement` (MIRROR du decompile) :

    builder = new EffectBuilder(<ctx>, <lambda>);
    return BaseEffect.AddSubEffectWithSameTurns(this, effect, target, builder,
                                                0x3f8 = 1016 PrecisionShot_BlockMovement);

-> MEME forme que `TauntedEffect` (`Taunted_BlockMovement` 25) : un enfant `AddSubEffectWithSameTurns`
sur le PORTEUR, donc `SubEffectSpec(..., turns=SAME_TURNS)`. CONFIRME LIVE (`probe_996r1r3_
precision_shot_port.py` volet [C]) : apres le cast de 1012, `decisionView` publie sur le caster
`PrecisionShot_Aim` (3) **ET** `PrecisionShot_BlockMovement` (3) -- deux effets, meme duree.

⚠ `$$BlockMovement` n'a AUCUNE xref de CODE dans le binaire : ses trois xrefs sont des slots de
VTABLE. C'est un override virtuel de `BaseEffect`, dont la base est un corps trivial que IL2CPP
deduplique (donc absent des tables, cf. « L'ABSENCE d'une methode ne prouve RIEN »). Le rang
d'appel est celui de l'application de l'effet -- exactement ce que le port modelise par
`sub_effects_on_apply`.

CE QUI N'EST PAS PORTE -- les TROIS RETRAITS (residu #996-r1-r3-r1)
------------------------------------------------------------------
`IdunBattle.Entities.Effects.Loki.PrecisionShot_AimEffect$$CreateHandleTriggerAbilitiesInternal`
construit trois `DSLFactory$$Triggered(<cond>, BaseEffect.GetRemoveEffectBehaviour(this), 0)` :

    [1] On(0x12) & <DSLTriggers+0x28> & AmountIsEqualOrGreater(
            Enemies(Owner@+0x30, AdjacentUnits(Owner@+0x30, unique: 1, 3), 3), Direct(1))
    [2] On(0x23) & DSLTriggers.get_OwnerIsTarget
    [3] On(0x0b) & DSLTriggers.get_OwnerIsActor & NOT DSLTriggers.get_OwnerIsTarget

Lecture : la visee tombe quand un ennemi arrive au CONTACT [1], quand le porteur est CIBLE [2], ou
quand il agit sur QUELQU'UN D'AUTRE [3] -- ce dernier est ce qui met fin a la visee au tir
(`1013 PrecisionShot_Attack` sur un ennemi), et il EPARGNE le self-cast de 1015 (`OwnerIsTarget`
y est vrai, donc `!OwnerIsTarget` faux).

Non porte parce que le port n'a pas d'etage de trigger d'EFFET pour ces trois evenements ; l'effet
se comporte donc comme un effet a TIMER pur (3 tours), ce qui est PERMISSIF sur le regime « un
ennemi arrive au contact ». Documente, pas devine.
"""
from __future__ import annotations

from ...effect_type import EffectType
from ..base import SAME_TURNS, BaseEffect, SubEffectSpec


class PrecisionShot_AimEffect(BaseEffect):
    """`PrecisionShot_Aim` (0x3f7 = 1015) -- effet COMPOSITE : il spawne son enfant
    `PrecisionShot_BlockMovement` (0x3f8 = 1016) a l'application, MEME duree que lui."""

    # `IdunBattle.Entities.Effects.Loki.PrecisionShot_AimEffect$$get_KeepOnRevive` (`IEffect` slot 2)
    # SURCHARGE le defaut `True` de `IdunBattle.Entities.Effects.BaseEffect` : corps `xor al,al ; ret`
    # (`32 c0 c3`), DERIVE par `probe_547r13_keep_on_revive.py`, entree versionnee
    # `data/symbols/<build>/metadata/keep_on_revive.tsv`. C'est l'UNE des trois seules classes du
    # binaire a le renverser -- la visee ne survit donc PAS a une resurrection du viseur (#547-r14).
    # ⚠ Lu UNIQUEMENT au revive (`keep_on_revive_gate`) : sur le chemin de MORT ce flag est inerte.
    keep_on_revive = False

    def sub_effects_on_apply(self) -> list[SubEffectSpec]:
        return [
            SubEffectSpec(int(EffectType.PrecisionShot_BlockMovement),          # 0x3f8
                          EffectType.PrecisionShot_BlockMovement.name,
                          turns=SAME_TURNS),                # AddSubEffectWithSameTurns
        ]
