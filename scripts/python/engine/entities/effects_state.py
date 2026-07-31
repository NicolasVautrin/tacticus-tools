"""Matérialisation OFFLINE des effets actifs — **seed one-shot + évolution** (directive user 2026-06-27).

Pour rester 100% offline, l'engine ne lit PAS `decisionView.effects` à chaque décision : il capte
l'ensemble des effets actifs **une seule fois** (snapshot one-shot au chargement) puis l'**ÉVOLUE
offline** via le cycle de vie de chaque effet. Le cycle de vie est porté en **méthodes sur les classes
d'effet** (`engine.entities.effects` : BaseEffect + sous-classes + factory), pas en table de données :
chaque effet capté devient une instance `BaseEffect` (via `EffectFactory`), et l'évolution interroge
ses méthodes (`is_active`/`removed_after_attack`/`one_shot`/`expired`). cf. playbook-engine.md §17.13.

⚠ La capture one-shot des effets (côté hook) reste à brancher dans `combatSnapshot` (extension à venir) ;
en attendant, le harnais peut seeder depuis un `decisionView` (oracle). L'API ici est indépendante de
la source de seed.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .effects import BaseEffect, EffectFactory

#: `(multiplier %, abilityLevel, activeAbilityLevel)` — l'`AbilityState` applique a UN effet.
AbilityStateTriple = tuple


def baked_ability_state(captured: Mapping, carrier_id: int,
                        carrier_state: tuple,
                        ability_state_by_unit: Mapping | None) -> tuple:
    """`(multiplier, abilityLevel, activeAbilityLevel)` d'UN effet capte -- celui de sa **SOURCE**,
    pas celui de son PORTEUR. Foyer UNIQUE : `EffectsState.seed` et
    `runner/snapshot.py::_load_stats_and_effects` passent tous les deux par ici.

    MIRROR de la **POSE**, pas de la lecture -- le natif *bake*.
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder(id, abilityState)`
    construit l'entite-effet (`IdunBattle.Entities.Blueprints$$Effect`), prend son `EffectComponent`
    et y **COPIE les 0x24 octets** de l'`AbilityStateReference` recue, a `+0x18`..`+0x38`. Cette
    reference vient du noeud DSL `AddEffect(<type>, <abilityStateReference>, source, targets, turns)`,
    ou elle est evaluee sur l'ability QUI POSE
    (`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$get_AbilityStateReference` ->
    `IdunBattleLogic.Entities.DSLSelectors$$AbilityState(entities, owner, abilityType)`, owner =
    `AbilityEntities.Owner`) -- donc sur le CASTER. A la lecture,
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` /
    `IdunBattle.DSL.AbilityStateFromEffectSelector$$Select` relisent ce MEME `EffectComponent+0x18`
    et rien d'autre : **l'effet ne consulte JAMAIS son porteur**.

    Porteur == source uniquement pour un owner-effect. Des que le behaviour pose sur AUTRUI
    (`SagaOfTheWarriorBorn_OtherSpaceWolves` 1224 :
    `targets = UnitsFromFaction(Friends(Owner, <pool>, OnlyAlive) - Owner, ...)`), les deux different
    PAR CONSTRUCTION. `buildNormalizedBC` MASQUE la moitie de l'ecart -- il ecrit le MEME
    `targetAbilityLevel` dans `ActiveAbilityLevel` et `PassiveAbilityLevel` de toutes les unites
    (`normalize-bc/json-build.ts`) -- mais PAS le multiplicateur de rarete, qui reste per-unite.

    `captured["source"]` = `EffectComponent.SourceUnitId @+0x10`, ecrit par
    `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` depuis le meme `source` que le noeud DSL.
    C'est le seul canal de la capture qui designe l'entite-poseuse.

    REPLI = le PORTEUR (`carrier_state`), **jamais un neutre** : source absente de la capture
    (`None`), non entiere, ou non chargee (posee par une entite hors snapshot). C'est le
    comportement anterieur, conserve a l'identique -- le changement ne mord QUE quand la source est
    RESOLVABLE et DIFFERENTE du porteur. (Une TUILE n'a, elle, aucun porteur a qui se replier : sa
    voie est `runner/snapshot.py::_source_ability_state`, dont le repli est neutre.)"""
    if ability_state_by_unit is None or not isinstance(captured, Mapping):
        return carrier_state
    src = captured.get("source")
    if src is None:
        return carrier_state
    try:
        src = int(src)
    except (TypeError, ValueError):
        return carrier_state
    if src == int(carrier_id):
        return carrier_state
    st = ability_state_by_unit.get(src)
    if st is None:
        return carrier_state
    return (int(st[0] or 100), st[1], st[2])


@dataclass
class EffectsState:
    """État matérialisé des effets actifs (par unité) = instances `BaseEffect`, seedées une fois puis
    évoluées offline. Source de seed = capture one-shot `{unit_id: [{name, effectType, level, remaining,
    source}]}`. `active_effects(uid, state)` = ce que l'engine consomme à chaque décision (au lieu d'une
    relecture live)."""
    by_unit: dict[int, list[BaseEffect]] = field(default_factory=dict)

    @classmethod
    def seed(cls, effects_by_unit: Mapping | None, mult_by_unit: Mapping | None = None,
             ability_level_by_unit: Mapping | None = None,
             ability_state_by_unit: Mapping | None = None) -> "EffectsState":
        """`mult_by_unit` = {unit_id: AbilityVariablesMultiplierPercentage} (BC, défaut 100) ;
        `ability_level_by_unit` = {unit_id: niveau d'ability source} (indexe les `variables[level]`,
        ≠ stack level capté) — tous deux propagés aux effets matérialisés (§17.21). Ces deux tables
        sont clées par PORTEUR : elles décrivent le REPLI.

        `ability_state_by_unit` = {unit_id: (multiplier, abilityLevel, activeAbilityLevel)} — l'état
        d'ability de CHAQUE entité, consulté **par la SOURCE de l'effet** (`captured["source"]`).
        C'est le mirror du bake natif : cf. `baked_ability_state`. Absent (défaut) → comportement
        strictement antérieur, l'état du PORTEUR pour tous ses effets."""
        bu: dict[int, list[BaseEffect]] = {}
        for uid, effs in (effects_by_unit or {}).items():
            uid = int(uid)
            # REPLI = le porteur, à l'identique de l'ancien code (`active_ability_level` reste None :
            # `seed` ne l'a jamais propagé pour le porteur, et l'élargir ici déborderait du cas).
            carrier = (int((mult_by_unit or {}).get(uid, 100) or 100),
                       (ability_level_by_unit or {}).get(uid), None)
            out: list[BaseEffect] = []
            for c in (effs or []):
                if not (isinstance(c, Mapping) and c.get("name")):
                    continue
                mult, albl, actl = baked_ability_state(c, uid, carrier, ability_state_by_unit)
                out.append(EffectFactory.create(c, mult, albl, actl))
            bu[uid] = out
        return cls(by_unit=bu)

    def active_effects(self, unit_id: int, unit_state: Mapping | None = None) -> list[BaseEffect]:
        """Effets ACTIFS de l'unité = non consommés, non expirés, flag `EffectComponent.IsActive @+0x5c`
        (`e.active`) posé, ET `is_active(state)` (la `CreateActiveCondition`) vraie. Renvoie des
        instances `BaseEffect` (consommées par `build_attacker_modifiers_from_effects` / `hits_bonus_from_effects`).

        Les DEUX conjoints sont natifs et distincts : le FLAG est ce qu'ecrivent les feuilles DSL
        `ActivateEffect`/`DeactivateEffect` (et ce que lit `EntityExtensions$$IsOwnerOfEffect` en mode
        `activeOnly`) ; la CONDITION est reevaluee a la lecture (mirror de `CreateActiveCondition`, cf.
        `runner/operations/refresh_effects.py`). Un effet desactive par une feuille ne contribue plus —
        exactement comme il disparait de `decisionView.units[].effects` cote live.

        EXCEPTION NOMMEE (case-322) : `BaseEffect.active_condition_ported`. Le flag capte decrit
        l'etat REEL au moment de la capture ; pour un effet dont la `CreateActiveCondition` porte sur
        l'etat SIMULE (tuile candidate), le natif le RECALCULE avant d'evaluer
        (`RefreshEffectsOperation$$RefreshEffect` sur `RefreshTrigger.Simulation`), donc le flag
        capte n'est PAS la reponse. Pour ces classes SEULES, la condition portee fait foi. Blast
        radius nul ailleurs : le defaut de l'attribut est `False`."""
        return [e for e in self.by_unit.get(int(unit_id), [])
                if not e.consumed and not e.expired
                and (e.active or getattr(e, "active_condition_ported", False))
                and e.is_active(unit_state)]

    def has_effect(self, unit_id: int, effect_type: int | None = None,
                   name: str | None = None) -> bool:
        """L'unité porte-t-elle DÉJÀ un effet (non consommé) de ce type/nom ? Gate « déjà-présent »
        de la matérialisation (cf. `AddEffectOperation` : query 0x28 sur la def vs cible, + base de
        `UpdateExistingEffect`). Match par `effect_type` si fourni, sinon par `name`."""
        for e in self.by_unit.get(int(unit_id), []):
            if e.consumed:
                continue
            if effect_type is not None and e.effect_type == effect_type:
                return True
            if name is not None and e.name == name:
                return True
        return False

    def add_effect(self, unit_id: int, effect: BaseEffect) -> BaseEffect:
        """Enregistre un effet matérialisé sur l'unité (`AddNewEffect` : ajout à la liste portée de la
        cible). `effect.target` doit être l'unité porteuse. Mirror de l'ajout à
        `EffectsOwnedComponent` côté entité-effet (la liste structurée ici)."""
        self.by_unit.setdefault(int(unit_id), []).append(effect)
        return effect

    def on_attack(self, unit_id: int) -> None:
        """L'unité attaque → consomme les effets one-shot stricts."""
        for e in self.by_unit.get(int(unit_id), []):
            if e.one_shot:
                e.consumed = True

    def on_turn_end(self, unit_id: int, attacked: bool) -> None:
        """Fin de tour de l'ENTITÉ PORTEUSE (unité **ou tuile** — cf. ci-dessous) : retrait des effets
        « removed-after-attack » si elle a attaqué, puis décrément des timers, puis RETRAIT des instances
        arrivées à 0, puis CASCADE composite : un effet PARENT disparu (expiré/consommé) retire ses
        ENFANTS (lien `parent_type`).

        DOMAINE — `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` n'itère PAS les unités : il
        énumère **TOUTES les entités-EFFET du state** (la MÊME collection générique que consomme
        `IdunBattle.Entities.EntityExtensions$$GetEffectsBySourceUnit`, et dont il lit directement
        l'`EffectComponent`). Il n'y a donc AUCUNE distinction porteur-unité / porteur-tuile dans le tick
        de durée. L'appelant (`EndTurnOperation.execute`, `runner/operations/turnflow.py`) balaye pour
        cette raison TOUTES les clés de `by_unit`, ids d'entité-tuile compris (#102).

        DÉCRÉMENT — `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` =
        `if (0 < Duration@+0x64) Duration -= 1` : le compteur est **CLAMPÉ à 0**, il ne descend jamais
        sous zéro. Le gate d'entrée du natif est `!Removed@+0x5f && HasTurns@+0x5d` — une instance déjà
        retirée ne tick plus, une instance permanente (`HasTurns` faux, ici `remaining_turns is None`)
        non plus.

        RETRAIT — `IdunBattle.Entities.Components.EffectComponent$$ShouldBeRemoved` =
        `HasTurns && Duration == 0`. C'est le prédicat que teste
        `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` (enfilée par la fin de
        `EndTurnOperation$$RefreshEffects`) pour prendre la branche `DeactivateEffect` + retrait de
        l'entité-effet : à 0, l'effet **N'EXISTE PLUS**, il ne peut donc plus ni être vu par un gate de
        présence, ni déclencher ses triggers. Offline, la marque de retrait est `consumed` — la SEULE
        que TOUS les lecteurs honorent (`has_effect`, `collect_effect_triggers`, `active_effects`) ;
        `expired` n'est lu que par `active_effects`/`refresh_stat_modifier_effects`, d'où le trou
        MESURÉ (résidu O3) : un effet à timer arrivé à échéance restait visible de `has_effect` et
        continuait d'être collecté comme effet-trigger — pour une tuile, dont c'est le SEUL chemin de
        lecture, le feu (`FireEffect` 5) brûlait pour toujours et re-tickait son DoT à chaque tour.

        Mirror du cycle de vie natif d'un effet composite (ex. Stunned 1162) : à l'expiration du parent,
        `<Effect>.RevertInternal` (IdunBattle.Entities.Effects.Loki.StunnedEffect$$RevertInternal) fait `RemoveEffect` de ses enfants permanents (1166/1167)
        et l'enfant same-turns (1165) expire sur son propre timer synchronisé — NET : toute la famille
        part ensemble. La cascade `parent_type` reproduit ce NET (et couvre le retrait anticipé du parent)."""
        lst = self.by_unit.get(int(unit_id), [])
        for e in lst:
            if e.removed_after_attack and attacked:
                e.consumed = True
            if e.remaining_turns is None or e.consumed:
                continue                       # gate natif `!Removed && HasTurns`
            if e.remaining_turns > 0:          # `RemoveOneTurn` : décrément CLAMPÉ à 0
                e.remaining_turns -= 1
            if e.remaining_turns <= 0:         # `ShouldBeRemoved` -> DeactivateEffect + retrait
                e.consumed = True
        # cascade : tant qu'un parent vient de disparaître, consommer ses enfants (point fixe — gère un
        # éventuel chaînage parent->enfant->petit-enfant ; aujourd'hui 1 niveau pour Stunned).
        while True:
            gone = {e.effect_type for e in lst
                    if (e.consumed or e.expired) and e.effect_type is not None}
            changed = False
            for e in lst:
                if not e.consumed and e.parent_type in gone:
                    e.consumed = True
                    changed = True
            if not changed:
                break
