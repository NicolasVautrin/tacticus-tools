"""`AddTraitOperation` / `RemoveTraitOperation` -- mutateurs ECS des TRAITS accordes en bataille.

Chaine native (MIRROR 1:1, build courant) :

    IdunBattle.Core.Services.OperationProcessor$$AddTrait(target, trait, isTemporary)
      -> IdunBattle.Operations.AddTraitOperation$$Execute :
             comp = UnitExtensions.GetBaseUnitComponent(target)      ; null -> throw
             coll = isTemporary ? comp.<+0x48> : comp.<+0x40>        ; les DEUX collections
             if (!coll.Add(trait))            return                 ; deja present -> rien
             AddTraitOperation.AddDerivedAbilities(target, trait)
             if (isTemporary)                 return                 ; AUCUN evenement diffuse
             Events.Publish(0xc, entityId, { 0x71: trait })

    IdunBattle.Core.Services.OperationProcessor$$RemoveTrait(target, trait, isTemporary)
      -> IdunBattle.Operations.RemoveTraitOperation$$Execute :
             coll = isTemporary ? comp.<+0x48> : comp.<+0x40>
             if (!coll.Remove(trait))         return
             if (!BaseUnitComponent.HasTrait(target, trait))         ; plus present par L'AUTRE voie
                 RemoveTraitOperation.RemoveDerivedAbilities(target, trait)
             if (isTemporary)                 return
             Events.Publish(0x72, ...)

DEUX COLLECTIONS COTE NATIF, UNE COTE PORT -- et c'est LU, pas simplifie a l'aveugle.
`IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` rend la RESULTANTE

    !retires(+0x50).Contains(t) && ( permanents(+0x40).Contains(t) || temporaires(+0x48).Contains(t) )

et c'est cette resultante que le port materialise dans `UnitContext.traits` (l'ensemble de NOMS que
`snapshot._load_unit_traits` seede depuis `combatSnapshot.units[].traits`, lui-meme l'invoke de
`IdunBattle.Entities.UnitExtensions$$HasTrait` par valeur d'enum). `is_temporary` est donc
TRANSPORTE (il documente le call-site lu et sert le contrat des deux operations) mais n'a pas
d'observable distinct cote port -- residu NOMME. Le veto `+0x50` est de toute facon
**structurellement INERTE** (aucun ecrivain dans le binaire, #265).

`AddDerivedAbilities` -- **NO-OP POUR LE SEUL TRAIT QUE CE PORT ACCORDE**, mesure et non supposee.
Le corps lit `StaticBattleRules.Trait$$GetTriggeredAbility(trait)` et `$$GetActiveAbility(trait)`,
deux `TryGetValue` sur les dicts statiques que
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor` remplit.
Transcription des CLES du cctor : le dict TRIGGERED en porte 41 (0x3e8, 0x3f8, 0x22, 0x3eb, 0x3ea,
0x3ef, 0x3f0, 0x3f4, 0x3f6, 0x3f7, 0x3f9, 0x3f3, 0x3fb, 0x7e4, 0x7e5, 0x3f2, 0x3ec, 0x7e8, 0x7e9,
0x7eb, 0x7ec, 0x407, 0x406, 0x425, 0x408, 0x40a, 0x40b, 0x40d, 0x40c, 0x40f, 0x411, 0x413, 0x414,
0x416, 0x417, 0x410, 0x41c, 0x41d, 0x420, 0x422, 0x423) et le dict ACTIVE en porte **deux** (0xa,
0xc) -- `0x412 = UnitTrait.Unstoppable` n'est dans NI L'UN NI L'AUTRE. Le port ne porte donc pas
cet etage : il rougirait sur le premier trait qui en a besoin plutot que d'inventer une derivation
silencieuse (cf. `_derived_abilities_are_a_noop`).

APPELANTS PORTES : la feuille DSL `AddTrait` (`IdunBattleLogic.Entities.DSLBehaviors$$AddTrait` ->
`IdunBattle.Entities.Behaviours.AddTraitBehaviour`, ex. `DutyEternalAbility`) et le canal
`applied_traits` du cycle de vie des effets (`IdunBattle.Entities.Effects.Loki.
WarHowl_ExtraDamage_UnstoppableEffect$$ApplyInternal` / `$$RevertInternal`, qui appellent
l'Operation DIRECTEMENT par les slots 0x26 / 0x27 de l'`IOperationProcessor`, sans passer par
aucun noeud DSL -- exactement comme `AddUnitActiveAbilityModification`).
"""
from __future__ import annotations

from typing import Optional

from ...entities.traits.unit_trait import trait_name
from ..components import StatsComponent
from ..state import State


#: Les traits que `AddTraitOperation$$AddDerivedAbilities` fait deriver en ability (cles des deux
#: dicts statiques de `StaticBattleRules.Trait$$.cctor`, transcrites VERBATIM ci-dessus). L'etage
#: n'est PAS porte : ce jeu sert a REFUSER en silence-zero plutot qu'a l'ignorer (cf. le module).
_TRAITS_WITH_DERIVED_ABILITIES: frozenset = frozenset({
    0x3e8, 0x3f8, 0x22, 0x3eb, 0x3ea, 0x3ef, 0x3f0, 0x3f4, 0x3f6, 0x3f7, 0x3f9, 0x3f3, 0x3fb,
    0x7e4, 0x7e5, 0x3f2, 0x3ec, 0x7e8, 0x7e9, 0x7eb, 0x7ec, 0x407, 0x406, 0x425, 0x408, 0x40a,
    0x40b, 0x40d, 0x40c, 0x40f, 0x411, 0x413, 0x414, 0x416, 0x417, 0x410, 0x41c, 0x41d, 0x420,
    0x422, 0x423,                                   # StaticBattleRules.Trait$$GetTriggeredAbility
    0xa, 0xc,                                       # StaticBattleRules.Trait$$GetActiveAbility
})


def derived_abilities_are_a_noop(trait) -> bool:
    """`AddDerivedAbilities(target, trait)` / `RemoveDerivedAbilities` sont-ils SANS EFFET pour ce
    trait ? (= le trait n'est cle d'aucun des deux dicts statiques.) Le port ne porte pas cet etage ;
    ce predicat existe pour que l'appelant le SACHE au lieu de l'ignorer -- residu NOMME."""
    try:
        return int(trait) not in _TRAITS_WITH_DERIVED_ABILITIES
    except (TypeError, ValueError):
        return True


def _traits_of(state: State, unit_id: int):
    """`UnitExtensions$$GetBaseUnitComponent(target)` cote port : le `UnitContext` porteur de
    l'ensemble de NOMS. `(ctx, liste)` ou `(None, None)` si l'entite n'a pas de `StatsComponent`
    (le natif leve alors ; le port DEGRADE en no-op -- une unite sans contexte de stats n'a aucun
    lecteur de traits, donc rien a mettre a jour)."""
    e = state.get_entity(int(unit_id)) if (state is not None and unit_id is not None) else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return None, None
    return ctx, list(getattr(ctx, "traits", None) or [])


class AddTraitOperation:
    """`IdunBattle.Operations.AddTraitOperation$$Execute(target, trait, isTemporary)`."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, target: Optional[int], trait, is_temporary: bool = True) -> bool:
        """Accorde `trait` a `target`. Renvoie `True` si le trait a REELLEMENT ete ajoute (= le
        `coll.Add` natif a rendu `true`), `False` s'il etait deja porte -- c'est ce booleen qui,
        cote natif, decide de la suite (`AddDerivedAbilities` + evenement).

        `trait` est un `UnitTrait` (ou son ordinal) ; `trait_name` LEVE sur un id hors enum
        (louder-on-bug, meme regime que la feuille `AddTrait`)."""
        name = trait_name(trait)
        ctx, traits = _traits_of(state, target)
        if ctx is None:
            return False
        if name in traits:
            return False                       # `coll.Add` a rendu false -> le natif s'arrete la
        traits.append(name)
        ctx.traits = traits
        # `AddDerivedAbilities` : etage NON porte, et NO-OP pour tout trait hors des deux dicts
        # statiques. On ne le simule pas en silence -- l'appelant peut interroger
        # `derived_abilities_are_a_noop` (residu NOMME, cf. l'en-tete du module).
        # `isTemporary` -> aucune publication d'evenement ; le port n'a de toute facon pas de
        # canal d'evenement de vue.
        return True


class RemoveTraitOperation:
    """`IdunBattle.Operations.RemoveTraitOperation$$Execute(target, trait, isTemporary)`."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, target: Optional[int], trait, is_temporary: bool = True) -> bool:
        """Retire `trait` de `target`. Renvoie `True` si le trait a REELLEMENT ete retire (= le
        `coll.Remove` natif a rendu `true`), `False` s'il n'y etait pas.

        ⚠ ASYMETRIE ASSUMEE, et c'est le prix de la fusion des deux collections : le natif retire
        de la SEULE collection designee par `isTemporary`, donc une unite qui porte le trait DE
        BASE (`+0x40`) le CONSERVE quand un effet temporaire (`+0x48`) expire. Cote port l'ensemble
        est unique -> un retrait effacerait le trait de BASE. La garde est donc au niveau du
        CANAL, pas ici : `revert_traits_of_effect` ne retire que ce que `apply_traits_of_effect` a
        REELLEMENT pose (la liste memorisee sur l'instance), exactement comme
        `revert_ability_modifications` nie sa propre liste. MESURE qui rend ce cran obligatoire
        (case-366-r1) : `spaceWulfen` porte deja `Unstoppable` AU KIT, donc la pose de 1222 sur lui
        rend `False` ici et le retrait ne doit rien faire."""
        name = trait_name(trait)
        ctx, traits = _traits_of(state, target)
        if ctx is None or name not in traits:
            return False
        traits.remove(name)
        ctx.traits = traits
        return True


def apply_traits_of_effect(state: State, target: int, eff) -> list:
    """`<Effect>.ApplyInternal` (part TRAITS) : rejoue les `AddTrait(target, trait, isTemporary)`
    declares par la classe d'effet (`BaseEffect.applied_traits`), DANS L'ORDRE du decompile.

    MEMORISE sur l'instance (`applied_trait_grants`) la liste de ceux qui ont REELLEMENT ete
    ajoutes -- c'est elle que le revert nie. Un trait DEJA porte (kit, autre effet) n'y entre pas,
    donc son retrait n'effacera rien : c'est le mirror du `if (!coll.Add(trait)) return` natif,
    transporte jusqu'au revert. No-op si l'effet ne declare aucun trait."""
    grants = eff.applied_traits() or []
    if not grants:
        return []
    applied = []
    for trait, is_temporary in grants:
        if AddTraitOperation.execute(state, target, trait, bool(is_temporary)):
            applied.append((int(target), trait, bool(is_temporary)))
    eff.applied_trait_grants = applied
    return applied


def revert_traits_of_effect(state: State, eff) -> list:
    """`<Effect>.RevertInternal` (part TRAITS) : rejoue les MEMES appels en RETRAIT
    (`WarHowl_ExtraDamage_UnstoppableEffect$$RevertInternal` = strictement `ApplyInternal` avec le
    slot `0x27` au lieu du `0x26`). Consomme la liste memorisee a l'apply -> idempotent, et
    strictement borne a ce que CETTE instance avait pose. No-op si elle n'avait rien pose."""
    applied = list(getattr(eff, "applied_trait_grants", None) or [])
    if not applied:
        return []
    for tid, trait, is_temporary in applied:
        RemoveTraitOperation.execute(state, tid, trait, bool(is_temporary))
    eff.applied_trait_grants = []
    return applied


def revert_traits_of_removed_effects(state: State) -> list:
    """Pendant TRAITS de `revert_stat_mods_of_removed_effects` : un effet que le tick de fin de tour
    vient de faire EXPIRER doit RETIRER les traits qu'il avait accordes.

    Cote natif c'est le MEME chemin que la revocation de stat-mod --
    `IdunBattle.Operations.RemoveEffectOperation$$Execute` ->
    `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` ->
    `$$RevertEffectsForTargets` -> le virtuel `RevertInternal` de l'effet, qui pour
    `WarHowl_ExtraDamage_UnstoppableEffect` EST le `RemoveTrait`. Foyer SEPARE cote port parce que
    le gate d'idempotence de l'autre est specifique aux stat-mods (`effect_stat_mod_key`, qui
    `continue` sur `None` -- un effet a trait SANS stat-mod n'y arriverait jamais).

    Gate d'entree IDENTIQUE (`consumed OR expired`) et idempotence par la liste memorisee, qui est
    VIDEE au premier passage. Renvoie la liste `(unit, effect_type, trait)` retiree -- diagnostic."""
    out: list = []
    if state.effects is None:
        return out
    for uid, effs in state.effects.by_unit.items():
        for e in effs:
            if not (e.consumed or e.expired):
                continue
            for tid, trait, _tmp in revert_traits_of_effect(state, e):
                out.append((int(tid), e.effect_type, trait))
    return out
