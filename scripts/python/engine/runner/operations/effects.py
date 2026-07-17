"""Matérialisation des effets — `IdunBattle.Operations.AddEffectOperation` (gqfc5mff6c).

C'est le CŒUR de la matérialisation : l'opération atomique dans laquelle TOUS les vecteurs de
pose d'effet (à l'ATTAQUE via after-hit trigger, au MOVE via after-move trigger, au CAST d'active,
en début de tour, à la mort) finissent par converger. On porte d'abord cette FEUILLE (RE-first :
porter la feuille propre avant le caller), puis on branchera les vecteurs dessus.

Chaîne native RE'd (VA citées) :

    AddEffectOperation.Execute        @180e48940   (op, source, target, builder, effectType, valuePtr)
      → get_EffectsDatabase → query def par effectType            (record msg 0x3e = pre-add)
      → GATES :
          • target == 0                         → log + abandon
          • déjà-présent (query 0x28 def↔cible) → return (pas de re-pose)
          • IsUnit(target) && HasFlag(target,6) → immunité → log + abandon
      → durée = override (valuePtr/param_6) sinon `StaticBattleRules.Effect.DefaultAmountOfRounds`
        @181559ff0 (sinon fallback 1)
      → UpdateExistingEffect @180e49d60 : refresh d'un même-type existant → si oui, FIN
        sinon NOUVEAU :
          PlayerIdGenerator.Next → builder(param_4) crée l'entité-effet
          → EffectComponent.Type     @+0x58 = effectType
          → EffectComponent.Duration @+0x68 = durée
          → (parent @+0x70 + liste enfants @+0x78 si effet chaîné)
          → RemoveExistingEffect → AddNewEffect @180e484d0 :
              EffectComponent.SourceUnit @+0x10 = source
              EffectComponent.Target     @+0x14 = target
              EffectComponent.Active     @+0x6c = 1
              EffectComponent.Value      @+0x60/+0x64 (flag @+0x5d) = valeur (si portée)
              + ajout de l'entité-effet à la liste portée de la cible (EffectsOwnedComponent)
          → record msgs 0x30 (added) / 0x3f
      → record msgs 0x47 / 0x2f (applied)

⚠ PORTAGE STRUCTUREL (pas encore validé live) : le chemin NOUVEAU (effet absent → matérialisé)
est porté fidèlement (champs/durée/registre). Détails marqués TODO car non sourçables offline pour
l'instant : (1) l'immunité `HasFlag(target,6)` (les flags d'unité ne sont pas exposés par l'ECS) ;
(2) le refresh de stack `UpdateExistingEffect` (règles d'empilement par EffectType) ; (3) la valeur
exacte (param_6) qui dépend du builder du vecteur appelant. La VALIDATION live (replay-diff de
l'effet matérialisé sur la cible) vient avec le wiring du vecteur attaque (after-hit trigger).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import EffectsOwnedComponent, StatsComponent
from ...entities.effects import BaseEffect, EffectFactory, SAME_TURNS


# Table `StaticBattleRules.Effect.DefaultAmountOfRounds` @181559ff0 (port 1:1 du switch décompilé).
# EffectType (int) → nb de rounds par défaut ; absent = None (Nullable null natif : la durée doit
# alors venir d'un override, sinon fallback 1 dans Execute).
_DEFAULT_ROUNDS: dict[int, int] = {
    0x4f: 3,                                  # 79
    0x429: 1, 0x48a: 1,                       # 1065 / 1162
    # 0x4dc=1244 Contaminated : le switch natif @181559ff0 renvoie 2 pour 0x4dc (verifie : 0x4dc>=0x42a &
    # !=0x48a & ==0x4dc -> LAB local_res8=2), PAS 1 (bug de transcription corrige 2026-07-12, cf. #132).
    0x05: 2, 0x11: 2, 0x12: 2, 0x3a: 2, 0x4dc: 2, 0x5c4: 2,  # 5 / 17 / 18 / 58 / 1244 / 1476
}


def default_amount_of_rounds(effect_type: int) -> Optional[int]:
    """`StaticBattleRules.Effect.DefaultAmountOfRounds` @181559ff0 — durée par défaut (rounds) d'un
    EffectType, ou None si le natif renvoie un Nullable null (la durée vient alors d'un override)."""
    return _DEFAULT_ROUNDS.get(int(effect_type))


class AddEffectOperation:
    """`IdunBattle.Operations.AddEffectOperation` @180e48940 — matérialise un effet sur une cible.

    Feuille partagée par tous les vecteurs de pose. Ici on porte le chemin NOUVEAU (effet absent)
    fidèlement ; gates/refresh/immunité = structure portée + TODO (cf. en-tête de module)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, source: Optional[int], target: Optional[int], effect_type: int,
                *, name: Optional[str] = None, duration_override: Optional[int] = None,
                value: Optional[int] = None) -> Optional[BaseEffect]:
        """Pose l'effet `effect_type` sur `target` (posé par `source`). Renvoie l'effet matérialisé
        (`BaseEffect`) ou None si la pose est abandonnée (pas de cible / déjà présent / pas d'EffectsState).

        `name` = nom d'EffectType (`decisionView.effects[].name`) pour l'enregistrement diffable ;
        `duration_override`/`value` = paramètres du builder du vecteur appelant (param_6 natif)."""
        # GATE : pas de cible → abandon (Execute log "couldn't apply, no target" puis return 0).
        if target is None:
            return None
        if state.effects is None:
            # Pas d'EffectsState matérialisé (snapshot sans combatSnapshot) → on ne peut pas poser
            # l'effet structuré. Le diff de NOMS (EffectsOwnedComponent) reste possible si présent.
            return None
        # GATE immunité : IsUnit(target) && HasFlag(target,6). Non sourçable offline (flags d'unité non
        # exposés par l'ECS) → TODO ; structure conservée pour quand les flags seront portés.
        # DURÉE : override (builder) sinon DefaultAmountOfRounds(type) sinon fallback 1 (cf. Execute).
        duration = duration_override
        if duration is None:
            duration = default_amount_of_rounds(effect_type)
        if duration is None:
            duration = 1
        # NOUVEL effet : entité-effet via le builder natif (PlayerIdGenerator.Next). Côté Python on
        # matérialise l'instance BaseEffect (via la factory, sous-classe 1:1 si portée). Champs =
        # EffectComponent : Type/Duration/SourceUnit/Target/Value/Active (Active implicite = présent).
        # On la crée AVANT le gate « déjà-présent » pour interroger sa classe (`stacks_stat_mod_on_add`).
        captured = {"name": name or _effect_name(effect_type), "effectType": int(effect_type),
                    "level": None, "remaining": duration, "source": source}
        eff = EffectFactory.create(captured)
        eff.target = target
        eff.value = value
        # GATE : déjà-présent (query 0x28 def↔cible) — pas de re-pose d'un même type non consommé.
        # ⚠ Le refresh de stack `UpdateExistingEffect` (RE slice-20 Q3 : gate `IsUpdatable(type)` + match
        # effectType+SOURCE) n'est PAS porté ; ici un même-type déjà présent = simple no-op (return None) =
        # refresh-équivalent (mirror suffisant pour les effets UPDATABLE Fire/Pinned/Stunned). EXCEPTION :
        # un effet `stacks_stat_mod_on_add` (ActOfFaith) applique un stat-mod FRAIS à chaque pose → on SKIP
        # le no-op et on matérialise une NOUVELLE instance (reproduit l'observable additif live-validé).
        if not eff.stacks_stat_mod_on_add and state.effects.has_effect(
                target, effect_type=effect_type, name=name):
            return None
        # AddNewEffect : enregistrement sur la cible (liste structurée + liste de NOMS diffable).
        state.effects.add_effect(target, eff)
        _register_name(state, target, eff.name)
        # `AStatModifierEffect.ApplyInternal → ApplyModification` (vtable 0x728, RE slice-20 Q4) : applique
        # les ChangeStat déclarés par l'effet (part DATA `applied_stat_mods`). Séparé d'`AddNewEffect` (pure
        # matérialisation ECS) côté natif → séparé ici aussi (frontière déclaratif feuille / impératif op).
        AddEffectOperation._apply_stat_mods(state, target, eff)
        # Effet COMPOSITE : `<Effect>.ApplyInternal` spawne ses SOUS-effets (enfants) juste après le
        # parent (ex. Stunned 1162 → 1165/1166/1167). Effet-driven : la liste vient de la classe d'effet.
        AddEffectOperation._spawn_sub_effects(state, source, target, eff)
        return eff

    @staticmethod
    def _apply_stat_mods(state: State, target: int, eff: BaseEffect) -> None:
        """Mirror `AStatModifierEffect.ApplyInternal → ApplyModification` (vtable 0x728) : EXÉCUTE les
        `(StatType, montant)` déclarés par l'effet (`applied_stat_mods`, DATA côté `entities/`) via l'op
        runner `apply_change_stat`, keyés par une source UNIQUE par instance (revert par-source exact via la
        feuille `RemoveEffect`, symétrique de `reverted_stats()`). No-op si l'effet ne déclare aucun stat-mod
        (effet non StatModifier) ou si la cible n'a pas de `StatsComponent`. Stocke `stat_mod_source` sur
        l'effet (clé du revert). La source unique = `(effectType, target, nb de stacks actifs du même type)`
        → chaque instance revert exactement SON delta."""
        ent = state.get_entity(target)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        if sc is None:
            return
        mods = eff.applied_stat_mods(sc.ctx) or []
        if not mods:
            return
        from .stat_ops import apply_change_stat
        # source unique par instance : indexée par le nb de stacks du même type DÉJÀ actifs (hors `eff`
        # lui-même, déjà ajouté à la liste) → une clé distincte par stack pour un revert par-source exact.
        stack_n = sum(1 for e in state.effects.by_unit.get(int(target), [])
                      if (not e.consumed) and e.effect_type == eff.effect_type and e is not eff)
        src = (int(eff.effect_type), int(target), stack_n)
        for stat, amount in mods:
            apply_change_stat(state, target, int(stat), src, int(amount))
        eff.stat_mod_source = src

    @staticmethod
    def _spawn_sub_effects(state: State, source: Optional[int], target: int,
                           parent: BaseEffect) -> None:
        """Matérialise les sous-effets déclarés par `parent.sub_effects_on_apply()` (mirror des
        `Add*SubEffect`/`AddEffect` de `ApplyInternal`). Durée : SAME_TURNS → durée du parent ;
        0/None → permanent (lié au parent, rem=0 natif) ; N>0 → N. Chaque enfant porte
        `parent_type` (lien `ParentEffect@+0x70`). Enfants déjà présents = skip (idempotent)."""
        for spec in parent.sub_effects_on_apply():
            if state.effects.has_effect(target, effect_type=spec.effect_type, name=spec.name):
                continue
            if spec.turns == SAME_TURNS:
                rem = parent.remaining_turns
            elif spec.turns and int(spec.turns) > 0:
                rem = int(spec.turns)
            else:
                rem = None          # 0/None natif = permanent, lié au cycle de vie du parent
            child = EffectFactory.create({"name": spec.name, "effectType": int(spec.effect_type),
                                          "level": None, "remaining": rem, "source": source})
            child.target = target
            child.parent_type = parent.effect_type
            state.effects.add_effect(target, child)
            _register_name(state, target, child.name)


def _effect_name(effect_type: int) -> str:
    """Nom lisible de repli quand le vecteur appelant ne fournit pas le nom d'EffectType (la table
    enum int→nom vit côté hooks `ability-names`/`effect-names` ; offline on garde le type brut)."""
    return f"Effect_{int(effect_type)}"


def _register_name(state: State, target: int, name: Optional[str]) -> None:
    """Ajoute `name` à l'`EffectsOwnedComponent` de la cible (liste de NOMS triée, base du diff
    structurel d'effets). Crée le composant s'il manque. No-op si pas d'entité/nom."""
    if not name:
        return
    ent = state.get_entity(target)
    if ent is None:
        return
    comp = ent.get_component(EffectsOwnedComponent)
    if comp is None:
        comp = ent.add_component(EffectsOwnedComponent(effects=[]))
    if name not in comp.effects:
        comp.effects.append(name)
        comp.effects.sort()
