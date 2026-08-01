"""Retrait d'effets — FOYER IMPERATIF unique (#389-r2).

Deux Operations natives, empilees, et c'est la seconde que `KillUnitOperation` appelle quand une
unite MEURT :

    Core.Services.OperationProcessor$$RemoveEffect (slot 0x11 de l'interface `OperationProcessor`)
      -> IdunBattle.Operations.RemoveEffectOperation$$Execute(effectEntity)      -- UNE entite-effet

    Core.Services.OperationProcessor$$RemoveEffects (slot 0x5a)
      -> IdunBattle.Operations.RemoveEffectsOperation$$Execute(owner, options)   -- TOUS les effets
         d'un PORTEUR, filtres par `options`

`IdunBattle.Operations.KillUnitOperation$$RemoveEffects(killed, step)` n'est qu'un adaptateur :
il emballe le `step` dans un `Nullable<KillUnitStep>`, met le second champ des options a 0, et
appelle le slot 0x5a. `IdunBattle.Operations.DestroyMachineOperation$$RemoveEffects` et
`IdunBattle.Operations.FleeOperation$$RemoveEffects` ont la MEME signature `(killed, step)` --
la sequence de mort n'est donc pas la seule a s'en servir.

## `RemoveEffectsOptions` (12 octets utiles, `classes.tsv` : taille boxee 28, `System.ValueType`)

    +0x00  Nullable<IdunBattle.Operations.KillUnitStep> step
    +0x08  bool  <non nomme>

lus par `RemoveEffectsOperation$$Execute` ainsi (mirror du decompile) :

    foreach (effectId in owner.EffectsComponent.ActiveEffectIds@+0x10) {
        effectEntity = matchState.GetEntity(effectId)                       # slot 0x29
        effectType   = effectEntity.EffectComponent.Type@+0x58
        effectObj    = AOperation.get_EffectsDatabase(this).GetEffect(effectType)
        if (options.step.HasValue && effectObj.<IEffect slot 4> != options.step.Value) continue
        if (options.<+0x08>       && effectObj.<IEffect slot 2>)            continue
        toRemove.Add(effectId)
    }
    foreach (effectId in toRemove) {
        processor.<slot 0x2f>(<Inform>)
        processor.<slot 0x11>(matchState.GetEntity(effectId))               # RemoveEffectOperation
    }

Les DEUX predicats sont des slots de l'interface `IEffect` dont le corps est **DEDUPLIQUE** par
IL2CPP (getteurs constants) : ni `frida/methods.tsv` ni `ghidra/functions.tsv` ne les nomment, et
`IdunBattle.Entities.Effects.IEffect` ne declare aucune methode dans le dump. Ce qui EST lu :

  * l'enum `IdunBattle.Operations.KillUnitStep = {0=PreUnitRemove, 1=AfterUnitRemove,
    2=AfterDeathTrigger}` (`frida/enums.tsv`) et la signature
    `KillUnitOperation.RemoveEffects(killed:IEntity, step:KillUnitStep)` (`frida/methods.tsv`) ;
  * les TROIS valeurs litterales passees par `KillUnitOperation$$Execute` (0, 1, 2) et le second
    champ d'options a 0 aux trois call-sites.
  ⚠ HYPOTHESE NOMMEE : le step par DEFAUT est `PreUnitRemove` (0) -- le corps par defaut de
  `IdunBattle.Entities.Effects.BaseEffect` est un getteur constant, illisible offline. Toute
  surcharge se pose ici en attribut de classe `BaseEffect.remove_on_kill_step`. Consequence NULLE
  sur l'observable de premier ordre (a la sortie de la sequence de mort les trois steps ont tourne,
  donc TOUS les effets sont partis quel que soit leur step) ; elle ne mordrait que sur un
  consommateur de `On(UnitDeath)`/`On(UnitDefeated)` qui LIRAIT un effet du mort -- il n'y en a
  aucun de porte (cf. `damage.py::_kill_unit_operation`).

Le second predicat (`options.<+0x08>`) n'est PAS porte : ses trois call-sites de mort le passent a
0, aucun appelant porte ne l'active, et son slot n'a pas de nom. Le documenter vaut mieux que
l'inventer.

## `RemoveEffectOperation$$Execute` — ce que « retirer » veut dire

    if (effectComponent == null)              throw
    if (effectComponent.IsRemoved@+0x5f)      return          # idempotence
    if (effectComponent.IsRemoving@+0x5e)     return          # anti-reentrance
    owner = matchState.GetEntity(effectComponent.OwnerId@+0x14)
    memset(&entities, 0, 0x128) ; entities.+0x10 = entities.+0x18 = owner
    entities.currentAbilityOrEffect@+0x60 = AbilityOrEffect(effectComponent.Type@+0x58)
    On(PreEffectRemoved = 0x3f)                                       # slot 0x50
    effectComponent.IsRemoving@+0x5e = 1
    if (effectComponent.IsActive@+0x5c) processor.<slot 0x2d>(effect)  # DeactivateEffect -> REVERT
    if (effectComponent.ParentEffect@+0x70) parent.SubEffects@+0x78.Remove(effectId)
    owner.EffectsComponent.ActiveEffectIds@+0x10.Remove(effectId)
    RemoveEffectOperation$$RemoveSubEffects(this, effect, effectComponent)
    matchState.<slot 0x32>(effect, <reason 3>) ; processor.<slot 0x55>(effect, false)
    if (StaticBattleRules.Effect.ShouldRefreshDuringSimulation(type)) matchState.<slot 0x32>(effect, 4)
    effectComponent.IsActive@+0x5c = 0 ; effectComponent.IsRemoved@+0x5f = 1
    On(EffectRemoved = 0x40)                                          # slot 0x50
    processor.<slot 0x2f>(<Inform 4>)
    if (effectObj is <type non nomme>) { On(0x3b = UnitBecameTargetable) ; Inform 5 }

`remove_effect_instance` ci-dessous est le mirror de CE corps, extrait VERBATIM de la feuille DSL
`RemoveEffect` (`abilities/behaviours/effects.py`) qui le portait deja inline -- c'est la frontiere
#149 : le noeud DSL au-dessus, l'Operation imperative en dessous, un SEUL foyer.

RESIDUS NOMMES (inchanges par ce foyer, deja presents avant lui) :
  * `RemoveSubEffects` n'est pas porte ici (la cascade parent->enfants du port vit dans
    `EffectsState.on_turn_end`). Sans objet pour la sequence de mort : le `RemoveEffectsOperation`
    balaye TOUS les effets du porteur, sous-effets compris.
  * `IdunBattle.Operations.RemoveUnitOperation$$RemoveEffects` (le DESPAWN, `remove_unit.py` etape
    14) appelle le MEME slot 0x5a mais garde son retrait BRUT (`consumed = True` sans revert ni
    event) -- ecart preexistant, hors perimetre de #389-r2, laisse tel quel pour ne pas faire fire
    `On(63)`/`On(64)` sur les evictions/clones.
"""
from __future__ import annotations

from enum import IntEnum
from typing import Optional

from ..state import State


class KillUnitStep(IntEnum):
    """`IdunBattle.Operations.KillUnitStep` — VERBATIM du dump d'enums (`frida/enums.tsv`,
    build `rnca9r7q6c`) : `0=PreUnitRemove,1=AfterUnitRemove,2=AfterDeathTrigger`.

    Les trois valeurs sont les trois call-sites de
    `IdunBattle.Operations.KillUnitOperation$$RemoveEffects` dans
    `IdunBattle.Operations.KillUnitOperation$$Execute` -- cf. `damage.py::_kill_unit_operation`
    pour leur placement exact dans la sequence de mort.

    Les noms sont ceux DU JEU, caractere pour caractere (#427). Le port les avait d'abord ecrits
    en UPPER_SNAKE (`PRE_UNIT_REMOVE`) : `probe_313` n'aurait alors pu le garder qu'en
    `strict=False`, mode qui relache les NOMS pour TOUT le mirror et rend muet le sens
    RENUMEROTE -- le pire des trois (il resout, pointe ailleurs, rien ne proteste). Une
    exception de confort n'est pas payee par le membre qui la demande, elle est payee par les
    autres membres du meme mirror."""
    PreUnitRemove = 0
    AfterUnitRemove = 1
    AfterDeathTrigger = 2


def remove_effect_instance(state: State, unit_id: int, eff) -> bool:
    """`IdunBattle.Operations.RemoveEffectOperation$$Execute` — retrait d'UNE instance d'effet portee
    par `unit_id`, avec ses deux evenements et la revocation de toutes ses modifications.

    Renvoie `True` si l'instance a ete retiree, `False` si un gate d'idempotence l'a refusee
    (`EffectComponent.IsRemoved@+0x5f` / `IsRemoving@+0x5e` -> `eff.consumed` cote port).

    Ordre LOAD-BEARING, mirror du decompile :
      1. `On(PreEffectRemoved = 0x3f)` AVANT toute revocation (l'effet est encore actif quand il
         part) ;
      2. `DeactivateEffect` -> `<Effect>.RevertInternal` : stat-mods par SOURCE
         (`ValueModification$$ReverseModification`), stat-OVERRIDES, puis modifications d'ability
         (`AddUnitActiveAbilityModification` rejouees en `-delta`) ;
      3. retrait de la liste du porteur (`ActiveEffectIds.Remove`) -> `consumed` + `unregister_name` ;
      4. `On(EffectRemoved = 0x40)` APRES tout ce qui precede.
    """
    from ...entities.effects import effect_stat_mod_key
    from .stat_ops import revert_change_stat
    from .ability_modifications import revert_ability_modifications
    from .effects import unregister_name, AddEffectOperation
    from .triggers import pre_effect_removed_triggers, effect_removed_triggers

    if eff is None or eff.consumed:
        return False                       # gates `+0x5f` / `+0x5e`
    tgt = int(unit_id)
    # `On(PreEffectRemoved = 0x3f = 63)` — publie tout en haut, apres les deux gates d'idempotence
    # et AVANT toute revocation. Ses DEUX canaux d'ability sont asymetriques (#306) :
    # `CurrentAbility` (+0x60) porte l'effet retire, `TriggeringAbility` (+0x98) reste VIDE.
    pre_effect_removed_triggers(state, tgt, eff.effect_type)
    # revert par SOURCE (`ReverseModification`) : la valeur se re-clampe au read, sans delta stocke.
    src = None if eff.stat_mod_reverted else effect_stat_mod_key(eff)
    if src is not None:
        for stat in eff.reverted_stats():
            revert_change_stat(state, tgt, stat, src)
        eff.stat_mod_source = None
        eff.stat_mod_reverted = True
    # part OVERRIDE de `<Effect>.RevertInternal` (`ResetStat` = `ChangeStat` mode 4).
    if getattr(eff, "stat_override_stats", None):
        AddEffectOperation.revert_stat_overrides(state, tgt, eff)
    # part MODIFICATIONS D'ABILITY : `AddUnitActiveAbilityModification` rejouees en `-delta`.
    revert_ability_modifications(state, eff)
    eff.consumed = True
    # `ActiveEffectIds.Remove(effectId)` -> le canal des NOMS (lu par la couche decision) suit.
    unregister_name(state, tgt, eff.name)
    # `On(EffectRemoved = 0x40 = 64)` — MEME `AbilityEntities` que `On(63)`.
    effect_removed_triggers(state, tgt, eff.effect_type)
    return True


def remove_effects_operation(state: State, owner_id: Optional[int], *,
                             step: Optional[int] = None) -> list:
    """`IdunBattle.Operations.RemoveEffectsOperation$$Execute(owner, options)` — le slot 0x5a de
    `Core.Services.OperationProcessor`, atteint par `KillUnitOperation$$RemoveEffects(killed, step)`.

    `step = None` = `options.step` sans valeur -> AUCUN filtre (tous les effets du porteur).
    `step = KillUnitStep.X` -> ne retire que les effets dont `BaseEffect.remove_on_kill_step` vaut
    `X` (cf. l'hypothese nommee en tete de module).

    Mirror des DEUX boucles natives : la premiere COLLECTE les candidats, la seconde les retire.
    La separation est load-bearing — un consommateur de `On(63)`/`On(64)` declenche pendant la
    seconde boucle ne peut pas changer la liste deja arretee.

    Renvoie la liste des `effect_type` effectivement retires (trace)."""
    if owner_id is None or state.effects is None:
        return []
    uid = int(owner_id)
    candidates = []
    for eff in state.effects.by_unit.get(uid, []):
        if eff.consumed:
            continue                       # l'id n'est plus dans `ActiveEffectIds`
        if step is not None and int(getattr(eff, "remove_on_kill_step", 0)) != int(step):
            continue                       # `effectObj.<IEffect slot 4> != options.step.Value`
        candidates.append(eff)
    removed = []
    for eff in candidates:
        et = eff.effect_type
        if remove_effect_instance(state, uid, eff):
            removed.append(et)
    return removed
