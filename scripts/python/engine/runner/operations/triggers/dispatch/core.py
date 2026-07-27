"""Coeur du dispatch : collecte des triggers portes et evaluation d'un `TriggerEvent`,
extraits de `triggers/dispatch.py` (scission du module >1000 lignes, tache #169 --
deplacement VERBATIM, zero changement de comportement).

  - `collect_triggered_abilities` / `collect_effect_triggers` : mirror du registre
    `AbilityAndEffectCache` (volets ability-trigger et effet-trigger) ;
  - `evaluate_trigger_operation` : le point de passage de TOUS les vecteurs d'event ;
  - `_trigger_phase_component` : le composant de phase du porteur."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, UnitComponent, TriggeredAbilityComponent
from ..base import TriggerEvent, TriggeredAbility, EffectTrigger, PHASE_TRIGGER_CAP
from .registry import (TRAIT_TRIGGERS, ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS,
                       EFFECT_TRIGGERS)


def collect_triggered_abilities(state: State) -> list[TriggeredAbility]:
    """Mirror du registre `AbilityAndEffectCache` (volet ability-trigger) : itère TOUTES les entités et,
    pour chaque trait à trigger porté, instancie l'ability correspondante (owner = l'entité). (Le volet
    effet-trigger — Overwatch, on-hit — n'est pas encore collecté ici.)"""
    import gameconfig as GC
    from ...behaviour import BEHAVIOUR_TRAIT_TRIGGERS            # lazy : evite circular import behaviour<->triggers
    out: list[TriggeredAbility] = []
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None:
            continue
        for trait in (sc.ctx.traits or []):
            for cls in TRAIT_TRIGGERS.get(trait, ()):            # un trait peut accorder >1 trigger
                out.append(cls(eid))
            for cls in BEHAVIOUR_TRAIT_TRIGGERS.get(trait, ()):  # mecaniques de comportement (Battle Fatigue)
                out.append(cls(eid))
        # passiveAbilities (TheBetrayer…) — résolues via gameconfig par visualId.
        vid = getattr(sc.ctx, "visual_id", None)
        if vid:
            gu = GC.unit(vid) or {}
            for pa in (gu.get("passiveAbilities") or []):
                for cls in ABILITY_TRIGGERS.get(pa, ()):
                    out.append(cls(eid))
            # activeAbilities -> triggered-abilities DERIVEES (`StaticBattleRules.ActiveAbility$$
            # GetDerivedTriggeredAbilities`) : porté dès l'init de l'unité, sans cast préalable.
            for aa in (gu.get("activeAbilities") or []):
                for cls in ACTIVE_ABILITY_TRIGGERS.get(aa, ()):
                    out.append(cls(eid))
    return out


def collect_effect_triggers(state: State) -> list[EffectTrigger]:
    """Mirror du registre `AbilityAndEffectCache` (volet effet-trigger) : itère les effets ACTIFS portés
    par chaque unité (via `state.effects`) et, pour chaque effet d'un type enregistré, instancie son
    effet-trigger (owner = le porteur). No-op si `state.effects` absent."""
    out: list[EffectTrigger] = []
    eff = getattr(state, "effects", None)
    if eff is None:
        return out
    for uid, effs in eff.by_unit.items():
        for e in effs:
            if e.consumed:
                continue
            for cls in EFFECT_TRIGGERS.get(e.effect_type, ()):   # ArraySet natif : N triggers par effet
                out.append(cls(int(uid)))
    return out


def evaluate_trigger_operation(state: State, ev: TriggerEvent) -> list[dict]:
    """Mirror COLLAPSÉ du PUMP FIFO natif (#201) — `IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal`
    (dispatch) + `IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities` (drain) + `IdunBattle.Messages.InputMessageProcessor$$RunPhase(0xf)`
    (item) + `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` (retrait-des-morts entre items), fondus en UNE boucle.

    Structure native (RE) :
      1. `ExecuteInternal` : itère le registre GLOBAL `AbilityAndEffectCache` (composant #3 = triggers de
         CET event) → `EvaluateAbilityOrEffectTrigger` par entrée → **ENFILE** un pending triggered-ability
         (file #5) — il n'EXÉCUTE PAS inline.
      2. `ProcessPendingTriggeredAbilities` : **SNAPSHOT** la file #5 dans une List + **`Queue.Clear`**, puis
         `foreach` item → `RunPhase(0xf, item)`. Chaque `RunPhase` = callback (le behaviour de l'item) PUIS
         `VerifyDeaths` PUIS `ProcessDamageEvents` PUIS `ProcessPendingTriggeredAbilities` (cascade imbriquée).
         => les morts causées par l'item N sont RETIRÉES avant l'item N+1.

    Collapse du port (équivalent observable, sans machinerie de file) :
      - `registry` = liste MATÉRIALISÉE une fois = le SNAPSHOT (mirror du snapshot+Clear : les effets/traits
        ajoutés PENDANT le drain n'entrent pas dans CE registre).
      - la boucle draine le snapshot en ordre FIFO ; le **re-appel de `matches` par item** (contre l'état
        COURANT) = la re-validation de cible du `RunPhase(0xf)` (un item tué par un item antérieur ne matche
        plus — cf. la leg target-validity `OverwatchAutoAttack.matches`, alive du mover).
      - les morts sont appliquées **INLINE** par `_fire_death_if_killed` (alive=False + `after_death_triggers`
        LIFO) DANS `execute_behaviour` = le `VerifyDeaths`-entre-items (la victime est morte avant l'entrée
        suivante). Équivalent au pump pour la cascade prouvée #201 (overwatch kill-cancel) ; une vraie file
        pending explicite (ordre snapshot-clear multi-rounds) n'ajoute AUCUN effet observable ici → non portée
        (blast-radius/ordre RNG) tant qu'aucune divergence ne l'exige.

    Gates par entrée : `event_id` écouté → `CanGet*Trigger` (owner VIVANT sauf fire-on-death ;
    triggers-disabled non porté) → cap-phase (`<0x33`, ability-triggers) → `matches` → behaviour.
    Renvoie la liste des résultats (diagnostic)."""
    out: list[dict] = []
    registry = collect_triggered_abilities(state) + collect_effect_triggers(state)
    for entry in registry:
        # Un tile-effect écoute souvent PLUSIEURS events (`event_ids`) ; sinon `event_id` unique.
        if entry.event_id != ev.event_id and ev.event_id not in getattr(entry, "event_ids", ()):
            continue
        if getattr(entry, "owner_is_tile", False):
            pass                                           # owner = TUILE : pas de gate unit-entity/alive
        else:
            owner = state.get_entity(entry.owner_id)
            if owner is None:
                continue
            uc = owner.get_component(UnitComponent)        # CanGet*Trigger : owner unit vivant
            if uc is not None and not uc.alive and not getattr(entry, "fire_on_death", False):
                continue                                   # sauf ability fire-on-death (ex. FinalJustice)
        if not entry.matches(state, ev):
            continue
        # #140 : CAP phase-triggers (mirror IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger : GetTimesTriggeredThisPhase
        # < 0x33). S'applique aux ability-triggers (TriggeredAbility) — les effet-triggers passent par
        # EvaluateEffectTrigger (sans ce cap). Borne l'auto-récursion (splash Psyker qui re-déclenche le
        # splash Psyker via le vecteur after-hit). Clé = type d'ability-trigger (1 par trait-trigger).
        # `mark_as_triggered` AVANT le behaviour → la récursion voit le compteur incrémenté.
        if isinstance(entry, TriggeredAbility) and not getattr(entry, "owner_is_tile", False):
            tac = _trigger_phase_component(state, entry.owner_id)
            if tac is not None:
                pkey = type(entry).__name__
                tac.try_add(pkey)                                       # peuplement paresseux (idempotent)
                if tac.get_times_triggered_this_phase(pkey) >= PHASE_TRIGGER_CAP:
                    continue                                           # cap atteint cette phase → skip
                tac.mark_as_triggered(pkey)
        r = entry.execute_behaviour(state, ev)
        if r is not None:
            out.append(r)
    return out


def _trigger_phase_component(state: State, owner_id: int) -> Optional[TriggeredAbilityComponent]:
    """Get-or-create le `TriggeredAbilityComponent` de l'unité `owner_id` (mirror du composant natif ;
    absent d'une unité spawnée avant #140 → créé paresseusement). None si l'entité n'existe pas."""
    e = state.get_entity(owner_id)
    if e is None:
        return None
    c = e.get_component(TriggeredAbilityComponent)
    if c is None:
        c = TriggeredAbilityComponent()
        e.add_component(c)
    return c
