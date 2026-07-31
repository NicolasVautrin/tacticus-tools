"""`MyWillBeDoneOverlord_ExtraDamage` (`EffectType` 0x62d = 1581) -- le self-buff d'ATTAQUE de la
branche ELSE du passif `MyWillBeDoneOverlord` (`TriggeredAbilityType` 0x614 = 1556) de `necroOverlord`
<< Imotekh >> (Necrons, HERO, dans le pool). Tache #358, residu nomme de #354-r1.

Le VECTEUR de pose vit ailleurs (cite pour le contexte) :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MyWillBeDoneOverlordAbility$$CreateBehaviour`
branche ELSE = `AddDynamicStatModifierEffectToOwner(0x62d, statType = 0 = Attack,
turns = Sum(TurnsFromRounds(1), Direct(1)), isHidden = 0)` -- cf.
`engine/runner/operations/triggers/loki/my_will_be_done_overlord.py` et
`docs/rl/case-354-r1-my-will-be-done-overlord.md`.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) -- OU LA MAGNITUDE EST LUE
================================================================================================

#354-r1 avait laisse 1581 sans classe d'effet parce que sa magnitude n'apparait dans AUCUNE des trois
fonctions de la CLASSE D'ABILITY (`$$CreateTrigger`, `$$CreateBehaviour`, `$$GetTargetFriend`, plus le
helper `$$GetFriendAttackDamage` qui ne sert QUE l'override d'attaque de la branche THEN). C'est exact :
elle n'y est PAS. Le consommateur est dans une AUTRE classe, et il est GENERIQUE.

1. **L'instance d'effet** est construite par une lambda de la base d'effets, pas par une classe dediee :

       IdunBattle.Core.Services.EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_574
         -> new IdunBattle.Entities.Effects.DynamicStatModifierEffect(
                abilityType   = AbilityType.op_Implicit(0x614 = 1556 MyWillBeDoneOverlord),
                variableType  = 8    (`IdunBattle.Configuration.AbilityVariableType` 8 = extraDmg),
                isNegative    = 0,
                canBeImmuneTo = 0 )

   (Les quatre arguments sont LUS AU DESASSEMBLEUR -- `mov edx,0x614` / `mov r8d,8` / `xor r9d,r9d` /
   `mov byte [rsp+0x20],0` -- parce que ghidra perd l'immediat de l'`AbilityType` dans le decompile.
   `DynamicStatModifierEffect$$.ctor` range `variableType` en `this+0x4a0`, `isNegative` en `this+0x4a4`
   et l'`AbilityOrEffect` en `this+0x490`.)

2. **Le lien lambda -> EffectType** se lit dans `IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`,
   au motif d'enregistrement repete 511 fois : `mov [rcx+<off>], rsi` (cache du delegate `<>9__14_N`)
   puis `mov edx, <effectType>` / `call Add`. Les statiques de `<>c` sont `[<>9, <>9__14_0, <>9__14_1, …]`
   -> `off = 8 * (N + 1)`. Le couple `off = 0x11f8 (N = 574)` / `effectType = 0x62d` est donc
   **b__14_574 -> 1581**. Loi VERIFIEE sur les 511 enregistrements (tous les offsets multiples de 8,
   511 indices distincts, et les 14 lambdas qui appellent `DynamicStatModifierEffect$$.ctor` tombent
   chacune sur un `EffectType` distinct -- dont les trois du lot Votann deja portes, cf. `votann.py`).

3. **Le consommateur de la magnitude** est le corps generique
   `IdunBattle.Entities.Effects.DynamicStatModifierEffect$$GetDynamicStatModificationAmount` :

       amount = ConfigVar( <this+0x490 = AbilityOrEffect(1556)>,
                           EffectSource(Get(effect)),
                           <this+0x4a0 = 8 extraDmg> ).Invoke(entities)
       return Nullable( this+0x4a4 /*isNegative*/ ? -amount : amount )

   -> **le SIGNE est un champ de l'effet** (ici `isNegative = 0` -> BONUS), et le NIVEAU vient de
   l'`AbilityState` de la **SOURCE** de l'effet (`EffectSource`), pas du porteur -- ici les deux sont la
   MEME unite (`AddDynamicStatModifierEffectToOwner` met `Owner@0x30` en source ET en cible).

4. **La STAT** ne vient PAS de l'effet mais de l'entite-effet :
   `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` lit le composant de
   l'effet (`+0x10`), que le behaviour a rempli avec son argument `statType` -- ici `0 = Attack`.

5. **La POSE / LE RETRAIT** : `IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification` emet
   `ChangeStat(Entity(target), Stat(stat, part = 5 Modification tant que `this+0x482` isMultiplier est
   faux), Modify, Direct(amount), Entity(effect), …)` et
   `…$$RevertModification` rejoue le MEME appel en `part = 6 ResetModification` avec
   `<DSLFormulas+0x18> = Direct(0)` -- exactement le couple EAGER `applied_stat_mods` / `reverted_stats`
   du port (meme forme que les trois effets Votann, meme classe native).

`IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$RefreshValueInternal` n'est qu'un
`RevertModification` suivi d'un `ApplyModification` sur un trigger PARTAGE mis en cache par
`IdunBattleLogic.Entities.DSLTriggers$$.ctor` (slot `+0x68`) : re-jouer le calcul rend la MEME valeur
(le `ConfigVar` ne depend que du niveau d'ability de la source, invariant en bataille) -> le canal eager
est fidele a l'observable, sans modeliser le refresh.

Magnitude (gameconfig `MyWillBeDoneOverlord`, RE-LU, jamais fitte) : `extraDmg` = tableau 65 niveaux
(9 @L1 … 499 @L50 … 655 @L65) et il est dans `variablesAffectedByRarityBonus` (`["maxDmg", "extraDmg"]`)
-> le multiplier de rarete s'y applique. `ability_var` gate deja l'application sur cette liste.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var

#: `AbilityType.op_Implicit(0x614 = 1556)` de la lambda -- l'ability dont la config est lue.
MY_WILL_BE_DONE_OVERLORD = "MyWillBeDoneOverlord"
#: `IdunBattle.Configuration.AbilityVariableType` 8 = `extraDmg` (argument `variableType` de la lambda).
EXTRA_DMG_KEY = "extraDmg"


def _source_level_mult(effect: BaseEffect, stats_ctx) -> "tuple[int, int]":
    """(niveau d'ability, multiplier de rarete %) qui indexent le `ConfigVar` de l'effet.

    Mirror de `ConfigVar(AbilityOrEffect(1556), EffectSource(Get(effect)), 8)` : le natif resout la
    config contre l'`AbilityState` de la **SOURCE** de l'effet. 1556 etant un `TriggeredAbilityType`
    (un PASSIF), le niveau est le `passiveAbilityLevel` -- c'est celui que
    `runner/abilities/behaviours/effects.py::_source_scaling` seede dans `ability_level` a la pose
    (`passive if passive is not None else active`). Repli sur le `stats_ctx` du PORTEUR uniquement :
    source == porteur ici (`AddDynamicStatModifierEffectToOwner`), donc le repli lit la bonne unite.
    Niveau introuvable -> 0 (premiere entree de la courbe), jamais un niveau invente."""
    lvl = effect.ability_level
    if lvl is None:
        lvl = effect.active_ability_level
    if lvl is None and stats_ctx is not None:
        lvl = getattr(stats_ctx, "passive_ability_level", None)
    lvl = int(lvl) if lvl is not None else 0
    mult = effect.ability_variables_multiplier
    if (mult is None or int(mult) == 100) and stats_ctx is not None:
        mult = getattr(stats_ctx, "ability_variables_multiplier", 100)
    return lvl, int(mult or 100)


class MyWillBeDoneOverlordExtraDamageEffect(BaseEffect):
    """`MyWillBeDoneOverlord_ExtraDamage` (0x62d = 1581) -- stat-mod **Attack(0) POSITIF** sur
    `necroOverlord` lui-meme, pose pour `Sum(TurnsFromRounds(1), Direct(1))` tours quand AUCUN allie
    adjacent n'est eligible a l'attaque libre (branche ELSE du `If(GetTargetFriend, …)`).

    Magnitude = `extraDmg[passiveAbilityLevel de la source] x multiplier de rarete` -- le `ConfigVar`
    du corps generique `DynamicStatModifierEffect$$GetDynamicStatModificationAmount` (cf. l'en-tete du
    module) ; le signe est `+` parce que la lambda d'enregistrement passe `isNegative = 0`."""
    stat_mod_source = None   # cle de source ChangeStat (revert par-source via `RemoveEffect`)

    def applied_stat_mods(self, stats_ctx) -> "list":
        """DATA du `ChangeStat` (`StatPart` 5 = Modification) emis par
        `AStatModifierEffect$$ApplyModification` : Attack += `extraDmg[level source] x mult`.
        Execute par `AddEffectOperation._apply_stat_mods`. Montant nul/absent -> aucun stat-mod
        (degradation fidele « present != applique »)."""
        from ...stats import StatType
        lvl, mult = _source_level_mult(self, stats_ctx)
        amt = ability_var(MY_WILL_BE_DONE_OVERLORD, EXTRA_DMG_KEY, lvl, multiplier_pct=mult)
        if not amt:
            return []
        return [(int(StatType.ATTACK), int(amt))]        # isNegative = 0 -> +amount

    def reverted_stats(self) -> "list":
        """Stats annulees par `AStatModifierEffect$$RevertModification`
        (`Stat(0 = Attack, 6 = ResetModification)`), lu par la feuille `RemoveEffect` et par
        l'expiration du timer (`revert_stat_mods_of_removed_effects`)."""
        from ...stats import StatType
        return [StatType.ATTACK]
