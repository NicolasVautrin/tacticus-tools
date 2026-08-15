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

⚠ CE QUI ETAIT UNE HYPOTHESE NOMMEE EST DESORMAIS **LU** (#1088), et elle etait **FAUSSE**. Le port
posait `BaseEffect.remove_on_kill_step = 0` (`PreUnitRemove`) faute de pouvoir lire le getteur
constant. `probe_1088_remove_on_death_step.py` le derive sur les **465** classes de la fermeture
transitive de `BaseEffect` (declaration lue dans le `global-metadata.dat`, valeur lue aux OCTETS
dans le bloc `methodPointers`, **0 indeterminee**) :

  * le DEFAUT de `IdunBattle.Entities.Effects.BaseEffect` est **1** (`AfterUnitRemove`) ;
  * **quatre** classes surchargent -- trois a `AfterDeathTrigger` (`TauntedEffect`,
    `Loki.ArmourOfShriekingSoulsEffect`, `Active.Loki.RammingSpeed_ExtraExplodeEffect`) et une a
    `PreUnitRemove` (`Loki.AttemptedPossession_PossessedEffect`).

⚠ ET LE FILTRE PAR STEP EST GARDE PAR `HasValue`, ce que le resume << compare le slot 4 a
options.step >> ne montre pas : `if (options.step.HasValue && effect.<slot 4> != options.step.Value)
-> ne pas retirer`. Un appel SANS step retire donc TOUT, quel que soit le slot 4 -- c'est le regime
`step = None` ci-dessous, et il ne doit surtout pas heriter du filtre.

L'ecart n'est PAS sans consequence, contrairement a ce qui etait ecrit ici : a la sortie de la
sequence de mort les trois steps ont bien tourne, mais `KillUnitOperation$$Execute` place
`On(UnitDeath)` et `On(UnitDefeated)` ENTRE le step 1 et le step 2. Un effet a `AfterDeathTrigger`
est donc encore porte quand ces deux events partent -- c'est exactement ce que le natif exige pour
re-armer `DaemonicPatrons` sur un kill de cible TAUNTEE (mesure live #911-r1), et ce que le port
rendait impossible en retirant tout au step 0.

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
    `On(63 = PreEffectRemoved)`/`On(64 = EffectRemoved)` sur les evictions/clones.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
# FEUILLE PURE -- l'enum a DEMENAGE la (#1088) parce qu'il lui fallait un second lecteur,
# `entities/effects/base.py`, que la cascade de CE module traverse.
from ...entities.kill_unit_step import KillUnitStep
from ...entities.effects import effect_stat_mod_key
# Gate de TYPE du 3e event de `RemoveEffectOperation$$Execute` (`is UntargetableEffect`) : le
# domaine vit dans son foyer UNIQUE, il n'est pas re-liste ici. Import de MODULE (forme B) pour que
# le domaine reste substituable par un `monkeypatch.setattr` sur le foyer.
from ...entities.effects import aura_selectors as _aura
from .effects import unregister_name, AddEffectOperation
from .stat_ops import revert_change_stat
from .traits import revert_traits_of_effect


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
      4. `RemoveSubEffects` -- retrait RECURSIF des enfants (cf. `_remove_sub_effects`) ;
      5. `On(EffectRemoved = 0x40)` APRES tout ce qui precede.
    """
    from .ability_modifications import revert_ability_modifications
    from .triggers.dispatch import move_death as _md      # forme B : le foyer reste substituable

    if eff is None or eff.consumed:
        return False                       # gates `+0x5f` / `+0x5e`
    tgt = int(unit_id)
    # `On(PreEffectRemoved = 0x3f = 63)` — publie tout en haut, apres les deux gates d'idempotence
    # et AVANT toute revocation. Ses DEUX canaux d'ability sont asymetriques (#306) :
    # `CurrentAbility` (+0x60) porte l'effet retire, `TriggeringAbility` (+0x98) reste VIDE.
    _md.pre_effect_removed_triggers(state, tgt, eff.effect_type)
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
    # part TRAITS : `OperationProcessor$$RemoveTrait` rejoue pour chaque `AddTrait` que CETTE
    # instance avait REELLEMENT pose (mirror `WarHowl_ExtraDamage_UnstoppableEffect$$RevertInternal`,
    # qui n'est que le slot 0x27 la ou l'apply prend le 0x26). Borne a sa propre liste -> un trait
    # de KIT que l'effet n'avait pas ajoute n'est jamais retire.
    revert_traits_of_effect(state, eff)
    # part OWNER-SWAP de `<Effect>.RevertInternal` (#590) -- MIRROR de
    # `IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect$$RevertInternal`, dont le
    # corps ENTIER est `processor.<IOperationProcessor slot 128 ResetUnitOwner>(target)`. Symetrique
    # exact de `AddEffectOperation._apply_owner_override`. Le gate d'idempotence est DANS
    # l'operation (`!IsOwnerOverridden` -> no-op), donc un double retrait ne fabrique pas d'owner.
    # AXE DISJOINT du precedent : les traits et l'owner sont deux parts INDEPENDANTES du meme
    # `RevertInternal` natif, et aucun effet connu ne porte les deux -- les enchainer est donc
    # sans interaction (#585 x #590, resolu au rebase).
    if eff.overrides_unit_owner():
        from .change_unit_owner import ResetUnitOwnerOperation
        ResetUnitOwnerOperation.execute(state, tgt)
    eff.consumed = True
    # `ActiveEffectIds.Remove(effectId)` -> le canal des NOMS (lu par la couche decision) suit.
    unregister_name(state, tgt, eff.name)
    # `RemoveSubEffects(this, effect, effectComponent)` -- au RANG NATIF : apres le retrait de la
    # liste du porteur, AVANT `On(0x40)`.
    _remove_sub_effects(state, tgt, eff)
    # `On(EffectRemoved = 0x40 = 64)` — MEME `AbilityEntities` que `On(63 = PreEffectRemoved)`.
    _md.effect_removed_triggers(state, tgt, eff.effect_type)
    # `if (EffectsDatabase.GetEffect(type) is UntargetableEffect) { On(0x3b = UnitBecameTargetable) ;
    # Inform(5) }` — la QUEUE du corps natif, apres `On(0x40)` et son `Inform(4)`. Le gate est un
    # test de TYPE sur l'objet-effet ; cote port le domaine equivalent est le foyer UNIQUE
    # `UNTARGETABLE_EFFECT_TYPES` (les feuilles d'`ATeleportingEffect` portees), le meme que lit
    # `aura_selectors.is_targetable`. AJOUTE par #936 : jusque-la le port n'emettait ce vecteur
    # NULLE PART, ce qui rendait inerte tout consommateur d'`On(0x3b)` — cf. la docstring d'
    # `unit_became_targetable_triggers`. `Inform(5)` n'a pas de pendant porte (canal de PRESENTATION).
    if int(eff.effect_type) in {int(t) for t in _aura.UNTARGETABLE_EFFECT_TYPES}:
        _md.unit_became_targetable_triggers(state, tgt, eff.effect_type)
    return True


def _remove_sub_effects(state: State, unit_id: int, parent) -> None:
    """`IdunBattle.Operations.RemoveEffectOperation$$RemoveSubEffects` — MIRROR :

        subs = new List<int>(effectComponent.SubEffects@+0x78)   // COPIE de la liste
        foreach (id in subs) { e = state.GetEntity(id) ; processor.RemoveEffect(e) }

    Donc : retrait RECURSIF (chaque enfant repasse par `RemoveEffectOperation$$Execute`, qui
    retire a son tour SES sous-effets), et sur une COPIE de la liste -- le retrait de l'enfant
    mute celle du parent (branche `+0x70 ParentEffect` du meme `Execute`).

    Le port n'a pas la liste `SubEffects` par instance : il a le lien INVERSE `parent_type`, pose
    par `AddEffectOperation._spawn_sub_effects` et reconstruit a l'hydratation
    (`snapshot._load_effect_parent_links`). C'est le meme lien, lu dans l'autre sens.

    POURQUOI CE FOYER MANQUAIT. La cascade parent -> enfants n'existait que dans
    `EffectsState.on_turn_end` (expiration par le TIMER). Un retrait ANTICIPE -- une feuille
    `RemoveEffect`, un trigger de bond -- laissait donc les enfants DERRIERE lui. Mesure du
    2026-08-05 (#462-r4b-r1-r1-r1-r1-b) : le trigger (b) retirait bien le composite 27, et
    `[25, 26, 1237]` restaient sur la cible alors que le natif rend une liste VIDE.

    ⚠ LES ENFANTS NE VIVENT PAS TOUS SUR LE PORTEUR. La liste native `SubEffects@+0x78` porte des
    ids d'ENTITE-EFFET, sans aucune notion de porteur ; le port, qui lit le lien INVERSE
    `parent_type`, doit donc balayer TOUS les porteurs que les specs du parent designent.
    `IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect$$ApplyInternal` pose trois de ses quatre
    enfants sur l'entite BONDEE (cf. `SubEffectSpec.on_bonded_entity`) : sans ce balayage, retirer
    1091 laisserait derriere lui le `Taunted` du champion, son `HolyDuel_ExtraDmg` et son
    `HolyDuel_DmgReduction` -- exactement le vice que ce foyer ferme, une entite plus loin."""
    specs = parent.sub_effects_on_apply()
    if not specs:
        return
    eff = getattr(state, "effects", None)
    if eff is None:
        return
    et = int(parent.effect_type)
    # Porteurs a balayer, DERIVES des specs (jamais ecrits a la main) : celui du parent, plus
    # l'entite bondee des que le parent declare au moins un enfant `on_bonded_entity`.
    carriers = [int(unit_id)]
    bonded = getattr(parent, "bonded", None)
    if (bonded is not None and int(bonded) != int(unit_id)
            and any(getattr(s, "on_bonded_entity", False) for s in specs)):
        carriers.append(int(bonded))
    # COPIE de la liste avant de muter (mirror du `new List<int>(...)` natif).
    for carrier in carriers:
        children = [e for e in list(eff.by_unit.get(carrier, []))
                    if not e.consumed and e.parent_type is not None and int(e.parent_type) == et]
        for child in children:
            remove_effect_instance(state, carrier, child)


def remove_effects_operation(state: State, owner_id: Optional[int], *,
                             step: Optional[int] = None) -> list:
    """`IdunBattle.Operations.RemoveEffectsOperation$$Execute(owner, options)` — le slot 0x5a de
    `Core.Services.OperationProcessor`, atteint par `KillUnitOperation$$RemoveEffects(killed, step)`.

    `step = None` = `options.step` sans valeur -> AUCUN filtre (tous les effets du porteur).
    `step = KillUnitStep.X` -> ne retire que les effets dont `BaseEffect.remove_on_kill_step` vaut
    `X` (cf. l'hypothese nommee en tete de module).

    Mirror des DEUX boucles natives : la premiere COLLECTE les candidats, la seconde les retire.
    La separation est load-bearing — un consommateur de `On(63 = PreEffectRemoved)`/`On(64 = EffectRemoved)` declenche pendant la
    seconde boucle ne peut pas changer la liste deja arretee.

    Renvoie la liste des `effect_type` effectivement retires (trace)."""
    if owner_id is None or state.effects is None:
        return []
    uid = int(owner_id)
    candidates = []
    for eff in state.effects.by_unit.get(uid, []):
        if eff.consumed:
            continue                       # l'id n'est plus dans `ActiveEffectIds`
        # ⚠ LE DEFAUT DE SECOURS EST CELUI DU NATIF, PAS `0`. Un objet-effet sans l'attribut (stub
        # de test, effet hydrate par un chemin qui ne passe pas par `BaseEffect`) doit se comporter
        # comme `IdunBattle.Entities.Effects.BaseEffect`, dont le getteur rend `AfterUnitRemove`
        # (#1088). Le `0` ecrit ici retirait ces effets au TOUT PREMIER step -- le meme faux defaut
        # que celui du foyer, mais recopie a un endroit qu'aucune surcharge de classe ne corrige.
        defaut = KillUnitStep.AfterUnitRemove
        if step is not None and int(getattr(eff, "remove_on_kill_step", defaut)) != int(step):
            continue                       # `effectObj.<IEffect slot 4> != options.step.Value`
        candidates.append(eff)
    removed = []
    for eff in candidates:
        et = eff.effect_type
        if remove_effect_instance(state, uid, eff):
            removed.append(et)
    return removed
