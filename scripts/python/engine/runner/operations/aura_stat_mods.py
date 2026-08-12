"""`AStatModifierEffect` PROJETE — volet AURA de `IdunBattle.Operations.RefreshEffectsOperation`.

`runner/operations/refresh_effects.py` couvre les stat-mods d'un effet sur SON PORTEUR (le selecteur
natif est le corps DEFAUT). Ce module couvre la famille SOEUR : un `ADynamicStatModifierEffect` dont le
`CreateTargetSelector` designe D'AUTRES unites, et dont
`IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification(owner, target, effect)` ecrit donc
une `ValueModification` sur le `UnitStats` de CHAQUE cible-selecteur (source = l'ENTITE-EFFET, une seule
entree `per_source` quelle que soit la cible).

Cette projection est **DYNAMIQUE** cote natif : `UpdateEffectTargets` re-evalue le selecteur et
`ApplyModification`/`RevertModification` suivent. GROUND TRUTH live (runner MC1_67, `statModSources`,
porteur `darkaAzrael` / LionHelm) :

    allie a dist 1                -> blockDamage +797 (source = l'entite-effet 98)
    le MEME allie deplace en (4,4) -> blockDamage 0     (RevertModification)
    ramene a dist 1                -> blockDamage +797 (ApplyModification)

D'ou les DEUX points de cablage :
  * `snapshot.load_state` (SEED)  -> `attribute_aura_stat_modifiers` : la capture `combatSnapshot`
    contient DEJA la modification (elle est dans `GetStat`), mais sans attribution — elle atterrit dans
    le residu opaque `CAPTURED_SOURCE` et devient donc IRRETIRABLE. On la RE-ATTRIBUE sous la cle de
    l'effet et on DEFALQUE d'autant le residu -> `get_stat(Current)` est INCHANGE au seed (zero
    regression) mais la contribution devient droppable.
  * `MoveUnitOperation.execute` (MOUVEMENT) -> `refresh_aura_stat_modifiers` : re-evaluation complete
    (le selecteur est purement geometrique).

INTERFACE (duck-typed, `getattr` — seuls les effets concernes la portent, meme regime que
`TARGETING_OPTIONS`) :
  * `aura_stat_modification_stat()   -> int`
  * `aura_stat_modification_amount() -> int | None`
  * `aura_stat_modification_targets(state, owner_id) -> list[entity_id]`
Aucun effet preexistant ne la porte -> ces deux points de cablage sont des NO-OP stricts hors porteur.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import StatsComponent, unit_state_for_effects
from ...entities.stats import CAPTURED_SOURCE


def aura_stat_mod_key(owner_id: int, eff) -> tuple:
    """Cle de la `ValueModification` projetee — UNE par (entite-effet), mirror du natif ou la source du
    `ChangeStat` EST l'entite-effet (donc la MEME cle sur toutes les cibles du selecteur). Distincte de
    `statmod_source_key` (stat-mod SELF) : les deux familles ne se marchent jamais dessus."""
    return ("aura_statmod", getattr(eff, "effect_type", None), int(owner_id),
            getattr(eff, "name", None))


def _aura_carriers(state: State):
    """(owner_id, effet, stat, amount, key) de chaque effet ACTIF qui declare la projection.

    ⚠ DEUX lectures de l'activite, et il en faut DEUX (#959) : le FLAG capte (`e.active`, ce que
    `EffectComponent.IsActive @+0x5c` valait a la capture) ET la `CreateActiveCondition` PORTEE
    (`is_active`), quand la classe la surcharge. Le natif ne connait qu'une activite -- il la
    RECALCULE (`IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` reecrit le flag a
    chaque refresh) ; le port, lui, herite d'un flag FIGE au seed. Une instance materialisee par
    `ABILITY_INIT_OWNER_EFFECTS` arrive `active = True` PAR DEFAUT : sans la seconde lecture, les
    DEUX auras de `GrimEfficiency` (qui partitionnent les stances de `PrioritisedEfficiency`)
    s'appliqueraient ENSEMBLE, un facteur 2 silencieux.

    NO-OP STRICT pour les porteurs preexistants : `is_active` n'est surchargee par AUCUN des effets
    qui declarent cette projection (`LionHelm_ExtraBlock*`, `PathOfCommand_ExtraCrit`,
    `KustomForceFieldReworked[_Orks]`) -- pour eux `BaseEffect.is_active` rend `True`
    inconditionnellement, exactement comme avant."""
    if state.effects is None:
        return
    for owner_id, effs in list(state.effects.by_unit.items()):
        for e in (effs or []):
            if e.consumed or e.expired or not e.active:
                continue
            stat_fn = getattr(e, "aura_stat_modification_stat", None)
            if stat_fn is None:
                continue
            stat = stat_fn()
            if stat is None:
                continue
            # APRES le filtre de projection, jamais avant : `unit_state_for_effects` construit une
            # vue par PORTEUR, et la poser pour les effets qui ne projettent RIEN serait du travail
            # pur (la vue est paresseuse mais son instanciation ne l'est pas).
            if not e.is_active(unit_state_for_effects(state, owner_id)):
                continue                                 # `CreateActiveCondition` PORTEE (#959)
            amt = e.aura_stat_modification_amount()
            if not amt:
                continue
            yield int(owner_id), e, int(stat), int(amt), aura_stat_mod_key(owner_id, e)


def _unit_stats(state: State, unit_id: int):
    ent = state.get_entity(unit_id)
    sc = ent.get_component(StatsComponent) if ent is not None else None
    return getattr(sc.ctx, "stats", None) if sc is not None else None


def refresh_aura_stat_modifiers(state: State, unit_id: Optional[int] = None) -> list:
    """Mirror `RefreshEffectsOperation` / `UpdateEffectTargets` (volet PROJETE) : re-evalue le selecteur
    de chaque effet-aura a stat-mod et pose (`ApplyModification`) / retire (`RevertModification`) sa
    contribution sur les unites concernees.

    `unit_id` (optionnel) = ne re-evaluer que ce qui peut avoir change pour CETTE unite (un mover) —
    la contribution des autres cibles est de toute facon idempotente (`Modify` = replace par-source).
    Renvoie la liste des `(unit, stat, amount|None)` ecrits (diagnostic)."""
    out: list = []
    for owner_id, eff, stat, amt, key in _aura_carriers(state):
        targets = set(eff.aura_stat_modification_targets(state, owner_id))
        scope = [int(unit_id)] if unit_id is not None else list(state.entities.keys())
        for uid in scope:
            us = _unit_stats(state, uid)
            if us is None:
                continue
            if uid in targets:
                us.change_stat(stat, key, amt)               # ApplyModification (part 5)
                out.append((int(uid), stat, amt))
            else:
                comp = us.components.get(int(stat))
                if comp is not None and key in getattr(comp, "modification").per_source:
                    us.revert_stat(stat, key)                # RevertModification (part 6)
                    out.append((int(uid), stat, None))
    return out


def attribute_aura_stat_modifiers(state: State) -> list:
    """SEED — re-attribue la part deja CAPTUREE de chaque aura stat-mod, sans changer `GetStat(Current)`.

    Le `combatSnapshot` d'une cible a portee porte deja la modification (`statDelta`), mais
    `UnitContext.from_snapshot` ne sait l'attribuer qu'aux effets PORTES PAR CETTE UNITE — or l'effet
    vit sur le PORTEUR DE L'AURA. La part atterrit donc dans `CAPTURED_SOURCE` et rien ne peut plus la
    retirer quand la cible sort du rayon. On la deplace ici : `+amount` sous la cle de l'effet,
    `-amount` sur le residu opaque. Somme inchangee => aucun impact sur un etat qui ne bouge pas ;
    seule la MOBILITE devient fidele.

    ⚠ Ne s'applique QU'AUX cibles actuellement selectionnees (celles qui portent effectivement la part
    capturee). Une cible hors rayon n'a rien a re-attribuer."""
    out: list = []
    for owner_id, eff, stat, amt, key in _aura_carriers(state):
        for uid in eff.aura_stat_modification_targets(state, owner_id):
            us = _unit_stats(state, uid)
            if us is None:
                continue
            comp = us.components.get(int(stat))
            if comp is None:
                continue
            mod = comp.modification
            if key in mod.per_source:                       # deja attribue (double appel) -> no-op
                continue
            residual = mod.get_modification_from_entity(CAPTURED_SOURCE)
            mod.modify(key, amt)
            new_residual = residual - amt
            if new_residual:
                mod.modify(CAPTURED_SOURCE, new_residual)
            else:
                mod.reverse_modification(CAPTURED_SOURCE)
            out.append((int(uid), int(stat), int(amt)))
    return out
