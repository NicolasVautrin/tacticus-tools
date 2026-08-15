"""État initial (chargé depuis le LIVE) + forme canonique diffable + diff.

Stratégie tranche 0 (cf. docs/rl/runner-engine.md §2.0) : l'état initial du runner
Python est CHARGÉ depuis un snapshot live du runner fraîchement bâti (vérité-terrain) ;
le runner reproduit ensuite l'ÉVOLUTION (operations). Le port complet BC→Initialize
(indépendance totale) est différé.

  • `load_state(decision, observe)` : snapshot live (decisionView + observeBattle) →
    `State` ECS (entités + composants). Charge les UNITÉS (`decisionView.units`), les
    MACHINES OF WAR (`decisionView.mows`, cf. `_load_machines`) **et les effets portés par
    les TUILES** (`tileMeta.tiles[].effects`, cf. `_load_tile_effects`).
  • `snapshot(state)` : `State` → forme canonique comparable (lue depuis les composants).
  • `snapshot_live(decision, observe)` : MÊME forme canonique, calculée DIRECTEMENT
    depuis les RPC (chemin INDÉPENDANT de load_state → cross-check du loader).
  • `diff(a, b)` : liste lisible des divergences entre deux snapshots.

Jointure des ids : `decisionView.units[].id` == `observeBattle.units[].squadId` =
l'**id d'unité** (référencé par les messages/applyAction). ⚠ ≠ `observeBattle.entityId`
(l'id d'entité ECS interne, p.ex. 79 vs squadId 78) : on clé l'ECS Python par l'id
d'UNITÉ (squadId/decisionView.id), pas l'entityId, pour rester aligné aux messages.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple

from .state import State
from ..services.damage_config import DamageConfiguration
from ..services.victory_config import victory_conditions_from_bc   # #287-r11-r1-r1
from .components import (
    UnitComponent, OwnerComponent, PositionComponent, HealthComponent,
    EffectsOwnedComponent, StatsComponent, ShieldComponent, ShieldInstance,
    TriggeredAbilityComponent, MachineComponent, ActiveAbility, ActiveAbilitiesComponent,
    UnitFlagsComponent,
    set_unit_feet,
    register_defeated_unit,          # #1082 : foyer d'ecriture des deux listes de defaites
)
from ..entities.entity_type import EntityType   # #270-r1-r1-r3
from ..entities.stats import StatType           # #462-r4e-o-r2-r1-r1 (`_load_turn_counts`)
from ..entities.effects.factory import EffectFactory
from ..entities.effects_state import EffectsState
from ..entities.effects.factory import EffectFactory
from ..entities.unit_context import UnitContext
from ..entities.effects.factory import EffectFactory
from ..entities.effects_state import EffectsState, baked_ability_state
from ..entities import effects_state as _effects_state   # FORME B (#962) : `seed_battle_counters`
# FORME B (#1009) : `get_owner_effects_added_on_ability_init`, lu par le re-bake du couple TERTIAIRE.
# Le module est DEJA importe ci-dessus (ligne `EffectFactory`), donc cascade INCHANGEE ; et le
# differe qui vivait au site etait GRATUIT (mesure : charger `engine.entities.effects.factory` seul
# en process FRAIS ne fait PAS atterrir `engine.runner.snapshot` dans `sys.modules`).
from ..entities.effects import factory as _effects_factory
from ..entities.unit_context import UnitContext
from ..entities.active_ability_type import ActiveAbilityType
from ..entities.traits.unit_trait import trait_names_from_ids
from ..entities.rarity import assert_rarity_channel, measured_rarity   # #999-r3/-r2 (canal #1039)
from ..entities.triggered_ability_type import TriggeredAbilityType
from .components import ForcedAttackTargetsComponent
from .operations.aura_stat_mods import attribute_aura_stat_modifiers
from .operations.spawn import (_seed_ability_owner_effects, _seed_trait_owner_effects,
                               _seed_derived_ability_owner_effects,
                               TELEPORT_STRIKE_TELEPORTING_IN)
from ..services.damage_config import DAMAGE_FIELDS


# `EntityType.Machine` — l'enum d'entité du `MatchState` natif, projeté tel quel par les capteurs
# (`frida/hooks/game/match-state.ts` : `Tile:0, Unit:1, Match:2, Effect:3, Player:4, UnitFoot:5,
# Machine:6, MachinePlatform:7`). C'est le DISCRIMINANT exact « cette ligne est une MoW » dans
# `combatSnapshot.units[]` / `statModSources.units[]`, qui remontent les DEUX types depuis `d9d0008`
# (#128 « lot ATELIER VIDE »). ⚠ Le commentaire du hook lui-même dit « Machine INCLUSE (#93) » — #93
# est la tâche SpiritLeech, PAS le commit qui a élargi le filtre. Ne pas recopier cette attribution :
# elle a déjà induit en erreur (`git log -S "EntityType.Machine" -- <le hook>` tranche).
_ENTITY_TYPE_MACHINE = EntityType.Machine


def _hp_by_id(observe: dict,
              snapshot: Optional[dict] = None) -> Dict[int, Tuple[Optional[int], Optional[int]]]:
    """hp/hpMax par id d'UNITÉ (squadId == decisionView.id). PAS entityId.

    ⚠ **`observeBattle.hpMax` est le max INITIAL, `combatSnapshot.healthMax` est le max COURANT** —
    et les deux DIVERGENT dès qu'un stat-mod `HEALTH` a relevé le maximum (#902). Mesuré sur le
    marquage `1224 NanoscarabRepairProtocols` (`AddDynamicStatModifierEffect(1546, stat Health)`) :

        squadId 56 `necroSpyder`  -> observeBattle hp 11696 / hpMax **9037**  (max initial)
                                     combatSnapshot health 11696 / healthMax **11696** (max courant)

    Sans ce correctif l'ECS Python reçoit `hp > hp_max`, donc l'unité passe pour PLEINE : tous les
    gates « a-t-elle des PV manquants » se trompent — `AttackQuery$$EntityCanBeRepaired`,
    `HealableUnitsSelector`, `FillUpStatComponent$$MaxFillUp`. Conséquence MESURÉE : le port de
    `1223 ReanimationBeam` ne réparait AUCUNE des machines marquées (`Repairable` rendait `[]`) là où
    le natif en réparait une de 1457 PV. Le maximum relevé est *la condition d'entrée* de l'ability,
    donc l'écart était structurel, pas accidentel.

    Le snapshot PRIME quand il porte une valeur EXPLOITABLE ; `snapshot=None` (appelant qui ne le
    capture pas) et `healthMax` absent/0 retombent sur `observeBattle` — **jamais** un `0` rendu
    comme une mesure : `healthMax == 0` est ce que publie une entité sans PV (la MoW `necroReanimator`
    le rend, cf. `snapshot.py` §« stats à 0 »), pas un maximum de zéro.

    N'ADRESSE PAS le résidu #572-r1 (le port, quand c'est LUI qui pose le stat-mod HEALTH, ne relève
    toujours pas `hp_max` : `ctx.stats[5]` ne se propage pas à `HealthComponent`). Ici on corrige le
    SEEDING d'un état live, pas la propagation offline — deux étages distincts."""
    out: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
    for u in (observe.get("units") or []):
        uid = u.get("squadId")
        if uid is not None:
            out[uid] = (u.get("hp"), u.get("hpMax"))
    for u in ((snapshot or {}).get("units") or []):
        eid = u.get("entityId")
        hmax = u.get("healthMax")
        if eid is None or eid not in out or not hmax:
            continue
        out[int(eid)] = (out[int(eid)][0], int(hmax))
    return out


def decision_view_seed_body(runner_id: int, **extra) -> dict:
    """Corps du RPC `decisionView` **destiné au SEED d'un `EffectsState`** — la porte NOMMÉE du canal
    `includeInactive`, à passer telle quelle à n'importe quel wrapper RPC
    (`rpc("decisionView", decision_view_seed_body(rid, allAbilities=True))`).

    **LES DEUX FACES PASSENT PAR ICI** (#443-r2-b1). Côté COMBAT c'est le seed de `load_state` ; côté
    DÉCISION c'est le seed de `playbook/scene.py::step_context` — même canal, même porte, un seul
    foyer. La face DÉCISION est restée sur le canal NU de #219 à #443-r2-b1, donc AVEUGLE aux effets
    inertes là où le natif en voit : écart MESURÉ à **-35** points d'utilité de paire (le poids BC
    `SUPPRESSIVEFIRE_TargetWithOverwatch`) sur un overwatch `1009` désarmé par le
    `Triggered(On(TurnStart_EffectActivation) & IsTurnOf(owner) -> DeactivateEffect)` de
    `IdunBattle.Entities.Effects.RangedAutoAttackEffect$$CreateHandleTriggerAbilitiesInternal`.
    Le pendant de ce corps est `active_only_rows` ci-dessous : ce que le canal AJOUTE ne doit
    atteindre que le canal STRUCTURÉ (`EffectsState`, qui porte le flag par instance), jamais les
    lecteurs de la liste BRUTE, qui n'ont pas de flag à consulter.

    POURQUOI une porte plutôt qu'un défaut global : les DEUX canaux du capteur
    `readEffectsByUnit` (`frida/hooks/game/effects.ts`) ont chacun un pendant EXACT côté port, et
    c'est cette correspondance qu'il faut pouvoir lire des deux côtés —

        `decisionView` par DÉFAUT      ≙  `EffectsState.active_effects` (+ `EffectsOwnedComponent`)
        `decisionView includeInactive` ≙  `EffectsState.by_unit`

    Faire de `includeInactive` le défaut du RPC supprimerait le canal ACTIF-ONLY comme référence
    lisible : un test comparant `active_effects` au live comparerait alors silencieusement au mauvais
    canal. La porte garde donc le choix EXPLICITE au site de capture.

    Sans elle, un effet POSÉ mais INERTE (`EffectComponent.IsActive @+0x5c` faux — p.ex. `Pinned`
    1065 sur un porteur `TerminatorArmour`, cf. `docs/rl/case-224-effect-immunity-gate.md`) est
    DROPPÉ par le capteur : l'état chargé n'a AUCUNE entité-effet pour lui, là où le natif en a une.
    `has_effect` rendait donc faux, et les `Triggered()` qui pilotent le flag (`ActivateEffect` /
    `DeactivateEffect` — p.ex. les trois de `RangedAutoAttackEffect$$
    CreateHandleTriggerAbilitiesInternal` pour `Overwatch_AutoAttack` 1009) n'avaient AUCUNE instance
    à ré-activer sur un état seedé. C'est aussi ce trou que la table de compensation
    `factory.ABILITY_INIT_OWNER_EFFECTS` bouche à la main pour trois owner-effects conditionnels
    (`AnvilShield_BlockChanceBelowHealthCap`, `HammerOfWrath_ConditionalDamage`,
    `HypersensoryAbilities_MinimalHealth`) — le seed reste idempotent, la table redevient un filet.

    COÛT MESURÉ (2026-07-28, `probe_219_seed_inactive_effects.py --cost`, runner 5v5 MC1_67) :
    **+909 octets / +3,84 % / +6 entrées** au déploiement, **+435 octets / +2,33 % / +3 entrées**
    après un tour d'IA. Les entrées ajoutées à t0 sont des owner-effects passifs
    (`Overwatch_AutoAttack` ×3, `GrimRetribution_CounterAttack`,
    `CalibaniteGreatswordStrike_Overwatching`, `PlasmaCannon_Visual`)."""
    return {"runnerId": int(runner_id), "includeInactive": True, **extra}


def active_only_effect_rows(rows) -> list:
    """PROJECTION ACTIF-ONLY d'une liste d'entrées d'effet captées — le pendant EXACT du canal
    `decisionView` par DÉFAUT, appliqué à un payload capté par `decision_view_seed_body`.

    Le hook (`frida/hooks/game/effects.ts::readEffectsByUnit`) ne fait qu'UNE chose de plus sans
    `includeInactive` : `if (info && !info.active && !includeInactive) continue`. Le drop des
    `removed` et l'émission de la clé `active` (`active: info?.active ?? true`) sont, eux,
    INCONDITIONNELS. ⇒ le canal `includeInactive` est un SUR-ENSEMBLE STRICT du canal par défaut, et
    cette projection le ramène EXACTEMENT à lui. C'est ce qui rend un lecteur INDÉPENDANT DU CANAL.

    À qui ça sert : un lecteur qui mirroire un prédicat natif ACTIVE-ONLY et qui lit la liste BRUTE
    (au lieu du canal STRUCTURÉ `EffectsState`, qui porte le flag par instance) doit passer par ici,
    sinon basculer le canal de capture change son verdict EN SILENCE. Un lecteur qui mirroire
    `onlyActive = 0` (présence), lui, ne doit PAS passer par ici — il lui faut la liste complète.

    Entrée non-dict (le canal NOMS d'`EffectsOwnedComponent`, `Scene.from_state`) → conservée telle
    quelle : elle ne porte pas de flag, donc rien à filtrer. Clé `active` absente → active par
    construction."""
    return [e for e in (rows or [])
            if not (isinstance(e, dict) and e.get("active") is False)]


def active_only_rows(rows) -> list:
    """Lignes d'entité (`decisionView.units` / `.mows`) dont les effets sont projetés ACTIF-ONLY.

    Copie SUPERFICIELLE, et seulement des lignes qui portent au moins une entrée inerte : sur un
    payload du canal par défaut la fonction rend les lignes d'origine, à l'identité près."""
    out = []
    for u in (rows or []):
        effs = u.get("effects") if isinstance(u, dict) else None
        if effs and any(isinstance(e, dict) and e.get("active") is False for e in effs):
            out.append({**u, "effects": active_only_effect_rows(effs)})
        else:
            out.append(u)
    return out


def _effect_names(u: dict) -> List[str]:
    """Noms d'effets ACTIFS de la ligne — la vue NOMS d'`EffectsOwnedComponent` (diff structurel).

    Le filtre sur `active` (foyer unique : `active_only_effect_rows`) rend cette vue INDÉPENDANTE du
    canal de capture : une ligne venue de `decisionView` par défaut et la même ligne venue de
    `decision_view_seed_body` produisent la MÊME liste. C'est ce qui permet de seeder par le canal
    `includeInactive` sans qu'un `diff(snapshot_live(...), snapshot(state))` dont les deux côtés
    n'ont pas été captés par le même canal ne signale des écarts fantômes. Les inertes ne sont pas
    perdus : ils vivent dans le canal STRUCTURÉ `State.effects.by_unit`, avec leur flag (cf.
    `EffectFactory.create`)."""
    return sorted(n for n in (e.get("name") for e in active_only_effect_rows(u.get("effects")))
                  if n)


def _active_abilities(u: dict) -> List[ActiveAbility]:
    """Entrees `ActiveAbility` d'une unite de `decisionView` (canal `unitAbilityTypes` :
    `{id, name, kind, usable, cooldown, disabled, level, multiplier}`). On ne garde QUE les kinds
    `active`/`granted` -- l'entree `normal` est poussee depuis `AbilityComponent.NormalAttackType`
    SANS objet `ActiveAbility` derriere (elle n'a ni `usable` ni `cooldown`), et le natif l'exclut
    de toute facon de la boucle de reset (`ActiveAbility.IsRegularAttack`)."""
    out: List[ActiveAbility] = []
    for a in (u.get("abilities") or []):
        if a.get("kind") not in ("active", "granted") or a.get("id") is None:
            continue
        out.append(ActiveAbility(
            ability_type=int(a["id"]), kind=str(a.get("kind")),
            can_still_be_used=bool(a.get("usable", True)),
            remaining_cooldown=a.get("cooldown"), disabled=bool(a.get("disabled", False)),
            # `AmmoCost`@0x38 / `HasEnoughAmmo`@0x40 -- 4e terme de `get_CanCurrentlyBeUsed`
            # (mordant sur les MoW seules ; `ammoCost` est null sur toute unite reguliere).
            ammo_cost=a.get("ammoCost"), has_ammo=bool(a.get("hasAmmo", True)),
            level=a.get("level"), multiplier=a.get("multiplier")))
    return out


def _tile_rows(tiles) -> List[dict]:
    """Lignes exploitables de `tileMeta` (RPC `tileMeta`, `rpc-board.ts`). On accepte le
    PAYLOAD COMPLET (`{ok, tileCount, tiles:[...]}`) ou la liste brute — même tolérance que
    `snapshot`/`combatSnapshot` côté unités (les appelants passent le retour RPC tel quel)."""
    if isinstance(tiles, dict):
        tiles = tiles.get("tiles")
    return [t for t in (tiles or []) if isinstance(t, dict)]


def _machine_rows(decision: dict) -> List[dict]:
    """Lignes MoW exploitables de `decisionView.mows` (`projectMowsFull`, ai-step/projection.ts).
    Clé ECS = `casterId` (== `machineId`, l'entité **Machine** Type=6) — c'est l'id que
    `applyAction {kind:"ability", casterId}` et `abilityTargets{unitId}` attendent ; le `id` de la
    ligne est la PLATEFORME (Type=7), qui n'est pas l'acteur."""
    return [m for m in (decision.get("mows") or []) if m.get("casterId") is not None]


def _machine_ability_state(m: dict) -> tuple:
    """(level, multiplier) de la MoW = `AbilityState` PER-ABILITY (`ActiveAbility._abilityState` :
    `Level`@+0 / `VariableMultiplierPercentage`@+4, lu par `readAbilityState` — mirror de
    `IdunBattle.Entities.Components.ActiveAbility$$get_AbilityState`, l'override primant). C'est CE canal qui indexe les variables
    config (minDmg/maxDmg/nrOfHits/summonHp…) des abilities de la MoW — et le SEUL : le capteur
    `unitConfig` rend `{"error": "visualId introuvable"}` sur une ligne Machine (mesuré), parce que
    l'entité porte un `MachineComponent` là où le capteur cherche un `UnitComponent` ; il n'appelle
    donc JAMAIS `BattleQuery.GetUnitConfig` pour une MoW (ce que ce registre répondrait n'est pas
    mesuré — ne pas l'invoquer comme cause). On prend la 1re active portant un état ; défaut
    (0, 100) = neutre. ⚠ Un niveau 0 n'existe pas nativement (`Idun.Shared.Level$$ToZeroBasedIndex`
    LÈVE si `value <= 0`) : c'est une valeur de repli PORT, pas un état natif."""
    for ab in (m.get("abilities") or []):
        if ab.get("level") is not None or ab.get("multiplier") is not None:
            return (int(ab.get("level") or 0), int(ab.get("multiplier") or 100))
    return (0, 100)


def load_state(decision: dict, observe: dict, snapshot: Optional[dict] = None,
               board=None, tiles=None, actor_stats=None, ability_states=None,
               targeting_config=None, damage_config=None, victory_config=None) -> State:
    """Snapshot live → `State` ECS (entités + composants d'unité).

    `damage_config` (#449-r2-r4) : la section `BC.Damage` de la BattleConfiguration, MÊME nature
    que `targeting_config` (elle vit sur DISQUE, aucun RPC ne la publie). Deux champs lus, tous
    deux relus au décompilé : `DamageSpreadPercentage` (`configuration+0x20`, lu par
    `IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64`) et
    `IgnoreDamageSpread` (`configuration+0x31`, lu par
    `IdunBattle.Core.Services.DamagePrediction$$get_IgnoreDamageSpread`). `None` = canal non
    fourni → le défaut DÉRIVÉ de `data/seed-bc.json` s'applique (cf.
    `engine.services.damage_config`). Un champ ABSENT de la section fournie vaut `0`, comme le
    natif — le ctor `IdunBattle.Configuration.DamageConfiguration$$.ctor` n'initialise que
    `DamageProfiles`, donc rien ne fabrique 20 côté jeu non plus.

    `victory_config` (#287-r11-r1-r1) : la section `BC.Victory` de la BattleConfiguration, MÊME
    nature que `targeting_config` / `damage_config` (elle vit sur DISQUE, aucun RPC ne la publie).
    Seul champ lu : `VictoryConditions` → `State.victory_conditions`, le dictionnaire qu'interroge
    `IdunBattle.Core.Services.BattleQuery$$GetMaxRounds` à la clé
    `VictoryConditionType.MainPlayerRoundLimitation`. C'est le seul substrat du bit
    `CasterHas2TurnsLeft` (`IdunBattle.Core.Services.BattleQuery$$HasMinimumRemainingTurns`).
    `None` = canal non fourni → le défaut DÉRIVÉ de `data/seed-bc.json` s'applique (cf.
    `engine.services.victory_config`) ; une section fournie SANS `VictoryConditions` pose `{}`,
    c'est-à-dire « la BC a parlé : aucune condition ».

    `targeting_config` (#444) : la section `BC.Targeting` de la BattleConfiguration, si l'appelant
    la connaît (elle vit sur DISQUE, pas dans un RPC). Seul champ lu :
    `EnableObscuringTerrain` → `State.enable_obscuring_terrain`, le premier gate de la LIGNE DE VUE
    (`IdunBattle.Core.Services.TargetingQuery$$GetTilesObscuringTerrain`). `None` = non fourni →
    le défaut de `State` s'applique (cf. son commentaire : la valeur de `data/seed-bc.json`).

    CANAL DE CAPTURE — `decision` accepte les DEUX canaux du capteur `readEffectsByUnit`. Capté par
    `decision_view_seed_body(rid, …)` (canal `includeInactive`), l'état charge AUSSI les effets POSÉS
    mais INERTES, avec leur flag `EffectComponent.IsActive @+0x5c` : ils entrent dans
    `State.effects.by_unit` (donc `has_effect` les voit, et les `Triggered()` d'activation ont une
    instance à ré-activer) et restent HORS d'`active_effects` (donc ils ne contribuent à aucun
    nombre). Capté par le canal par DÉFAUT, ils sont simplement absents — comportement historique,
    strictement inchangé. La vue NOMS (`EffectsOwnedComponent`) est active-only dans les deux cas
    (cf. `_effect_names`), donc le choix du canal ne déplace AUCUN diff.

    `snapshot` (combatSnapshot) optionnel : s'il est fourni, peuple en plus le
    `StatsComponent` (stats RÉSOLUES + arme normale, via `UnitContext`) de chaque unité
    ET `State.effects` (effets STRUCTURÉS matérialisés, `EffectsState`) — le runner peut
    alors calculer la plage de tirage lui-même. Sans `snapshot` : comportement tranche 0
    inchangé (identité/pos/HP/effets-NOMS uniquement).

    `board` (`engine.entities.pathfinding.board.Board`) optionnel : s'il est fourni, il
    est ASSIGNÉ à `state.board` (adjacence hex + élévation + terrain). Point d'injection
    UNIQUE du board — sans lui, les feuilles POSITIONNELLES du combat (bonus d'ELEVATION
    `IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier`, trench, LightCover, GetStuckIn) sont des
    no-op SILENCIEUX offline (cause racine #63 : un `state.board=` oublié dans un helper de
    replay). Passer le board ICI (au lieu d'un `state.board = board` dispersé après l'appel)
    rend l'omission structurellement impossible à un site donné. On accepte l'OBJET `Board`
    déjà construit (pas le boardGraph brut) car son mode d'adjacence (`evenq`/`native_sym`)
    est CONSOMMÉ par le moteur (`neighbours`/`are_tiles_adjacent`/splash) et varie selon les
    appelants : préserver l'objet exact = préserver le mode = zéro régression. L'assignation
    est faite en TOUTE FIN (après `_load_stats_and_effects`) → strictement équivalente à un
    `state.board = board` post-retour (l'init/seed ne lit jamais `state.board`).

    `tiles` (payload du RPC `tileMeta`) optionnel : les EFFETS PORTÉS PAR LES TUILES (feu, glace,
    contaminé, …). Nativement une tuile est une ENTITÉ comme une autre et porte le MÊME
    `EffectsOwnedComponent` qu'une unité — `IdunBattle.Operations.AddEffectOperation$$Execute`
    prend une cible `IEntity` quelconque et ne gate son contrôle unité-spécifique que derrière
    `IdunBattle.Entities.EntityExtensions$$IsUnit` ; `IdunBattle.Entities.TileExtensions$$HasTileStatusEffect`
    relit cette même liste sur l'entité-tuile. Le canal live jumeau de `decisionView.units[].effects`
    (`readEffectsByUnit`) est `tileMeta.tiles[].effects` (`readEffectsByTile`, MÊME lecture,
    MÊMES champs `{name, effectType, remaining, level, source}`, seul le filtre d'EntityType
    change) — d'où le seed par la MÊME chaîne `EffectFactory`. Sans lui, un état rechargé
    mi-bataille perdait TOUS les effets de tuile (#102) : les consommateurs déjà portés
    (`ctx.tile_has_effect` / `UnitsOnTilesWithEffect` #217, le filtre de zone
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetAllDamageableTargets`,
    le compte `IdunBattle.Entities.Effects.Loki.LordOfTempests_ExtraDamageEffect$$GetHexesIncreasingDamage`)
    partaient d'un plateau VIERGE → toute mécanique tile-driven était INCONFRONTABLE.
    Requiert `board` (le tile-id ECS ne vient que de `boardGraph` ; `tileMeta` ne porte que
    col/row) ; `tiles=None` = canal non fourni → comportement STRICTEMENT inchangé.

    `actor_stats` (payload du RPC `actorStats`) optionnel : les TROIS compteurs de tuiles parcourues
    de l'`ActorStatisticsComponent` (`+0xec` bataille / `+0xf0` ce tour / `+0xf4` tour précédent).
    MÊME nature que `_load_unit_flags` et `_load_unit_turn_state` — une ENTRÉE de gate que rien ne
    peuplait sur un état rechargé : un `State` reconstruit depuis une capture live repartait à
    `tiles_moved_this_turn = 0` alors que l'unité venait de parcourir `k` tuiles, donc
    `ModifiedExoarmour_ExtraDmgEffect` (magnitude `V × n`) y était SILENCIEUSEMENT inerte. C'était le
    résidu `#340-r1`, bloqué non par le port mais par l'absence de capteur ; `actorStats` publie
    désormais les trois champs. `actor_stats=None` = canal non fourni → comportement STRICTEMENT
    inchangé (les compteurs restent à 0, comme un composant natif frais).

    `ability_states` (payload du RPC `unitAbilityStates`) : l'ability TERTIAIRE de chaque unité —
    l'item RELIQUE ÉQUIPÉ (#357). MÊME nature que les trois seeds ci-dessus, et son canal est lui
    aussi un RPC DISTINCT (`unitAbilityStates`). Sans lui, une relique montée en bataille
    (`BC.Units[].TertiaryAbility`, montage #237) est INERTE côté port : le rail COMBAT dérive le kit
    déclenché du gameconfig, qui ne connaît que les reliques câblées EN DUR sur des npc
    (`units.<id>.relicAbilities`) — jamais l'item équipé, qui est un état JOUEUR. Requiert `snapshot`
    (le seed écrit dans `StatsComponent.ctx`, que `_load_stats_and_effects` pose).

    ⚠ C'est le SEUL des quatre seeds qui n'est PAS opt-in — depuis #363 il est **ON PAR DÉFAUT** dès
    qu'un transport RPC est lié (`bind_live_rpc`), et l'argument est un TRI-ÉTAT :

        `ability_states=<payload>`  le payload est utilisé tel quel (l'appelant a déjà fait le RPC) ;
        `ability_states=None`       AUTO — le canal se sert lui-même s'il le peut (cf. `_auto_ability_states`) ;
        `ability_states=False`      REFUS explicite — l'état d'AVANT #357, pour une contre-épreuve.

    Sans transport lié (`State` reconstruit hors harnais live, rejeu d'une capture sur disque), AUTO
    ne pose RIEN et le comportement est strictement celui d'avant. Le pourquoi de cette asymétrie
    avec `tiles=` / `actor_stats=` est au bloc « CANAL AMBIANT » plus bas (§ `bind_live_rpc`).

    ⚠ **La RÉSOLUTION de ce tri-état est jouée AVANT `_load_stats_and_effects` (#570-r5), ses SEEDS
    après.** Les deux ne consomment pas la même chose : les seeds écrivent dans les
    `StatsComponent.ctx` que `_load_stats_and_effects` pose (donc ils suivent), tandis que
    l'`AbilityState` par instance est une ENTRÉE de la MATÉRIALISATION des effets — le natif BAKE
    l'`AbilityStateReference` du poseur dans l'entité-effet, donc l'état doit exister AVANT l'effet.
    Un effet né trop tôt lisait `dmgReduction[1]` au lieu du palier réel, et le gardait."""
    state = State()
    state.current_player_id = decision.get("currentPlayer")
    if isinstance(targeting_config, dict) and "EnableObscuringTerrain" in targeting_config:
        state.enable_obscuring_terrain = bool(targeting_config["EnableObscuringTerrain"])
    # #287-r11-r1-r1 : la section `BC.Victory`. MEME nature que `targeting_config` / `damage_config`
    # (elle vit sur DISQUE, aucun RPC ne la publie). Seul champ lu : `VictoryConditions`, le
    # dictionnaire qu'interroge `IdunBattle.Core.Services.BattleQuery$$GetMaxRounds` a la cle
    # `VictoryConditionType.MainPlayerRoundLimitation` -- le PLAFOND DE ROUNDS, unique substrat du
    # bit `CasterHas2TurnsLeft`. `None` = canal non fourni -> le defaut DERIVE de
    # `data/seed-bc.json` s'applique (cf. `engine.services.victory_config`).
    _vic = victory_conditions_from_bc(victory_config)
    if _vic is not None:
        state.victory_conditions = _vic
    # #449-r2-r4-r1 -- CANAL AMBIANT. `damage_config` n'etait alimente par AUCUN appelant reel
    # (mesure : seuls les deux `probe_449r2r4*` le passent), donc tous les runners retombaient sur
    # le defaut DERIVE de `data/seed-bc.json`. Exact tant qu'ils partent de cette seed, FAUX des
    # qu'un montage passe `--seed-bc` avec une section `Damage` modifiee -- et muet, puisque le
    # port lirait alors la variance d'une AUTRE BC que celle qui court. Le chainon manquant etait
    # que `load_state` ne recoit ni la BC ni le state-file ; elle connait en revanche le RUNNER,
    # et c'est par la que la section voyage (meme patron que le registre de greffes, #448-r3-r1-r1-r1).
    # L'argument EXPLICITE prime toujours : ce canal ne se substitue qu'au `None`.
    if damage_config is None:
        damage_config = _section_bc_du_runner(runner_label(decision, observe, snapshot), "Damage")
    _dmgcfg = DamageConfiguration.from_bc(damage_config)
    if _dmgcfg is not None:
        # #449-r2-r4-r4 : toute la section, pas seulement les deux champs de la variance. La liste
        # est DERIVEE de `DAMAGE_FIELDS` -- un champ qui entre dans la table est pose ici sans
        # qu'on ait a y penser, et ne peut donc pas rester silencieusement non transporte.
        for _name in DAMAGE_FIELDS:
            setattr(state, _name, getattr(_dmgcfg, _name))
    # #90/#98 -- FACTEUR rounds->turns (`IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` = `count(joueurs du
    # `BC.Player.TurnOrder` dont `PlayerComponent+0x20 != 2`) * rounds`). `observeBattle.counts.player`
    # = le nb d'entites Player PROJETEES (EntityType 4) ; le joueur **Environment** est unique et
    # permanent dans toute BC (seed BC : Players 11/12/13 = PlayerType 0/1/2, `TurnOrder=[11,12,13]` ;
    # cf. modele des summons : pas de 3e team, Environment = 0 unite) -> non-Environment =
    # `counts.player - 1`. MESURE PRE-tick (2 unites/camp) : counts.player=3 -> 2, et `TurnsFromRounds(1)`
    # comme `DefaultAmountOfRounds=1` rendent bien `remaining = 2` live.
    _pc = (observe.get("counts") or {}).get("player")
    if _pc is not None and int(_pc) > 1:
        state.turn_order_player_count = int(_pc) - 1
    # `snapshot` PRIME sur `observe` pour le MAXIMUM (max COURANT vs max INITIAL, cf. `_hp_by_id`).
    hp_by_id = _hp_by_id(observe, snapshot)
    for u in (decision.get("units") or []):
        uid = u.get("id")
        if uid is None:
            continue
        e = state.add_entity(uid)
        e.add_component(UnitComponent(visual_id=u.get("visualId"), alive=bool(u.get("alive"))))
        e.add_component(OwnerComponent(team=u.get("team"), player=u.get("owner")))
        # #140 : registre par-unité des compteurs phase-triggers (cap <51). Vide ici ; peuplé
        # paresseusement (try_add idempotent) au 1er passage du gate (evaluate_trigger_operation).
        e.add_component(TriggeredAbilityComponent())
        p = u.get("pos") or {}
        if p.get("col") is not None:
            e.add_component(PositionComponent(col=p["col"], row=p["row"]))
        hp, hp_max = hp_by_id.get(uid, (None, None))
        if hp is not None or hp_max is not None:
            e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
        effs = _effect_names(u)
        if effs:
            e.add_component(EffectsOwnedComponent(effects=effs))
        # `IdunBattle.Entities.Components.ActiveAbilityComponent` — l'ETAT RUNTIME par actif
        # (CanStillBeUsed/RemainingCooldownTurns/IsDisabled/AbilityState). Canal live =
        # `decisionView.units[].abilities` (`unitAbilityTypes` + `readAbilityState`, qui lisent
        # litteralement ces champs). Sans `allAbilities: true` le canal ne porte que l'attaque
        # NORMALE -> aucune entree `active`/`granted` -> composant ABSENT (degradation VISIBLE).
        actives = _active_abilities(u)
        if actives:
            e.add_component(ActiveAbilitiesComponent(abilities=actives))
    _load_machines(state, decision)
    _load_feet(state, observe)
    # Ability TERTIAIRE / kits / `AbilityState` par instance (canal `unitAbilityStates`) : la
    # RESOLUTION du tri-etat est hissee ICI, AVANT `_load_stats_and_effects` (#570-r5). Elle ne
    # depend d'AUCUN composant -- `_auto_ability_states` ne lit que `decision`/`observe`/`snapshot`
    # -- alors que ce qu'elle rapporte, l'`AbilityState` par instance d'ability montee, est une
    # ENTREE de la materialisation des effets : le natif BAKE l'`AbilityStateReference` du poseur
    # dans l'entite-effet (`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder`,
    # cf. `engine.entities.effects_state.baked_ability_state`), donc l'etat doit exister AVANT
    # l'effet. Les SEEDS, eux (`_load_tertiary_abilities` & co), restent en aval : ils ecrivent dans
    # les `StatsComponent.ctx` que `_load_stats_and_effects` pose.
    payload, source = _auto_ability_states(ability_states, decision, observe, snapshot)
    # #448-r3-r1-r1 : un montage qui a GREFFE ne peut PAS se contenter d'un canal muet -- il
    # mesurerait un port ampute et rendrait VERT. Le choke point REFUSE au lieu de se degrader.
    # Le refus vise CET ETAT (les greffes dont le porteur y est), pas le PROCESSUS : cf.
    # `_grafts_concerning`, ou la mesure qui l'impose est ecrite.
    _refuse_if_grafted(source, snapshot, decision)
    if snapshot is not None:
        # #999-r3 -- AVANT tout seed qui LIT `units[].rarity` (`UnitContext.from_snapshot`). Le
        # capteur publie le nom PLEIN de l'enum justement pour qu'un consommateur l'ASSERTIONNE :
        # les cinq enums de rarete du build partagent leurs six membres aux memes ordinaux, donc
        # aucune VALEUR ne trahirait un mauvais appariement. Canal muet (`rarityEnum` absent ou
        # `null`) -> no-op, comportement strictement d'avant.
        assert_rarity_channel(snapshot)
        # AVANT les stats : `UnitFlag.Moved`/`Teleported` sont des entrees de GATE lues par le calcul
        # de degat (`attacker_modifiers` -> `unit_has_moved`), pas des sorties -- cf. `_load_unit_flags`.
        _load_unit_flags(state, snapshot)
        # MEME nature, MEME canal, MEMES DEUX BLOCS que les flags (#999-r3-r2) : la RARETE est
        # portee par `BaseUnitComponent` (+0x74), donc par une entite VIVANTE OU NON. #999-r3 ne
        # la branchait que sur `UnitContext`, bati depuis `units[]` seul -> tout mort en etait
        # prive. Cf. `_load_unit_rarity`.
        state.unit_rarity_seed = _load_unit_rarity(state, snapshot)
        # MEME nature que les flags : trois champs d'ETAT DE TOUR du `UnitComponent` (dont le
        # compteur `turnsFinished` que lit `OwnerHasFinishedMinTurns`), entrees de gate et non
        # sorties -- cf. `_load_unit_turn_state`.
        _load_unit_turn_state(state, snapshot)
        # MEME nature encore : le lien enfant -> summoner (`ChildComponent.ParentId`) est une
        # ENTREE que seule la simulation posait (au spawn) -- cf. `_load_unit_parent`.
        _load_unit_parent(state, snapshot)
        _load_stats_and_effects(state, decision, snapshot, ability_states=payload)
        # APRES `_load_stats_and_effects` : cette passe LIT `state.effects`, que la precedente vient
        # de remplacer par un `EffectsState.seed` frais. MEME nature que `_load_unit_parent` -- une
        # ENTREE de gate que seule la simulation posait, cf. `_load_forced_attack_targets`.
        _load_forced_attack_targets(state)
        # MEME nature, MEME rang (elle lit `state.effects`) : le lien PARENT -> ENFANT entre effets
        # composites, cf. `_load_effect_parent_links`.
        _load_effect_parent_links(state)
        # MEME nature, MEME rang encore (#953) : le COMPTEUR DE BATAILLE `melee_defeats`, que seule
        # la face DECISION posait -- cf. `_load_battle_counters` pour la mesure de ce que son
        # absence supprimait.
        _load_battle_counters(state, decision)
        # APRES les stats : le substrat de traits vit dans `UnitContext.traits`, que
        # `_load_stats_and_effects` vient de construire (unites ET MoW). Meme nature que les deux
        # seeds ci-dessus -- une ENTREE de gate que rien ne peuplait sur un etat recharge, le port
        # la RECONSTRUISANT depuis gameconfig au lieu de lire la source -- cf. `_load_unit_traits`.
        _load_unit_traits(state, snapshot)
        # MEME nature, MEME canal (`decision`) que `_load_battle_counters` (#1082) : le TUEUR de
        # chaque cadavre et le registre des victimes de chaque tueur, que seule la simulation
        # gravait. ⚠ SON RANG EST LOAD-BEARING, et il est APRES `_load_unit_traits` : ce seed
        # rappelle `register_defeated_unit`, donc le gate natif `!IsSteppable(killed)`, qui lit le
        # substrat de traits que la passe precedente vient de poser. Place plus haut, le gate serait
        # muet et inscrirait des `Steppable` que le natif ECARTE. Cf. `_load_death_sources` pour la
        # lecture qui rend l'inversion victime -> tueur exacte.
        _load_death_sources(state, decision)
        # APRES `_load_stats_and_effects` : cette passe LIT la stat 12 (`TURNS_STARTED`) que la
        # precedente vient de seeder. Meme nature que les seeds ci-dessus -- une ENTREE de gate,
        # cf. `_load_turn_counts`.
        _load_turn_counts(state)
        # APRES `_load_turn_counts` : ce seed LIT le dict qu'elle vient de poser (`+0x38`) et le
        # joueur courant, et en DERIVE le dict jumeau `+0x40` par l'identite que fixe l'ecrivain
        # unique `TurnComponent$$SetCurrentPlayer`. Cf. `_load_turns_ended` (#287-r11-r1-r1-r1).
        _load_turns_ended(state)
    # MEME nature que les deux seeds ci-dessus, mais son canal est un RPC DISTINCT (`actorStats`,
    # pas `combatSnapshot`) -> il est gate par son propre argument, jamais par `snapshot`.
    if actor_stats is not None:
        _load_actor_statistics(state, actor_stats)
    # Ability TERTIAIRE (item RELIQUE equipe, #357) : canal RPC distinct (`unitAbilityStates`), donc
    # argument propre. APRES `_load_stats_and_effects`, qui pose les `StatsComponent.ctx` dans
    # lesquels ce seed ecrit. #363 : `None` ne veut plus dire « ne rien poser » mais « AUTO » --
    # `_auto_ability_states` va chercher le payload lui-meme quand un transport est lie. `False` est
    # le refus EXPLICITE (contre-epreuve), et lui seul.
    # (#570-r5 : `payload`/`source` sont RESOLUS plus haut -- cf. le bloc hisse avant
    # `_load_stats_and_effects`. Le seed, lui, reste ICI.)
    if payload is not None:
        seeded = _load_tertiary_abilities(state, payload)
        # MEME payload, MEME composant, hierarchie 2 : les passiveAbilities REELLEMENT montees
        # (#366-r1). Cf. `_load_passive_abilities`.
        seeded_pas = _load_passive_abilities(state, payload)
        # MEME payload, MEME composant, TOUTES hierarchies : l'`AbilitiesComponent` entier, ce que le
        # dispatcher d'utilite itere (#456-r1). Cf. `_load_triggered_abilities`.
        seeded_kit = _load_triggered_abilities(state, payload)
        # MEME payload, AUTRE composant (`ActiveAbilityComponent`) : la SECONDE voie de la cascade
        # d'attaque normale (#419-r1-tr14-r5-r2). Cf. `_load_active_abilities`.
        seeded_act = _load_active_abilities(state, payload)
        # MEME payload encore, mais l'etat PRE-FABRIQUE (`UnitConfiguration.ActiveAbilities`,
        # capteur #466) : le seul substrat sur lequel la garde `FilterNewList` du repli generique
        # ne soit pas tautologique. Cf. `_load_config_active_abilities`.
        seeded_cfg = _load_config_active_abilities(state, payload)
        # MEME payload, MEME composant : le NIVEAU et le MULTIPLICATEUR de chaque active montee
        # (#890). Cf. `_load_active_ability_levels` -- c'est le SEUL canal qui les porte pour une
        # unite dont le `combatSnapshot.unitConfig` est en erreur (un BOSS).
        seeded_lvl = _load_active_ability_levels(state, payload)
        state.ability_states_seed = {"source": source, "seeded": seeded,
                                     "seededPassives": seeded_pas,
                                     "seededTriggeredKits": seeded_kit,
                                     "seededActives": seeded_act,
                                     "seededConfigActives": seeded_cfg,
                                     "seededActiveLevels": seeded_lvl}
        # APRES `_load_tertiary_abilities` -- ET C'EST TOUT L'ENJEU (#1009) : ce re-bake LIT
        # `ctx.tertiary_ability`, que la passe ci-dessus vient d'ecrire. Place dans
        # `_load_stats_and_effects` (donc AVANT), il voyait `None` sur toutes les unites et ne
        # mordait sur RIEN -- mesure, pas hypothese.
        state.ability_states_seed["rebakedTertiaryOwnerEffects"] = \
            _rebake_tertiary_owner_effects(state)
        # MEME cause, AUTRE porte (#1038) : une ability tertiaire dont le behaviour pose sur
        # AUTRUI. La passe ci-dessus est clee par PORTEUR et ne peut, par construction, jamais
        # voir ces instances-la. Cf. `_rebake_tertiary_posed_effects`.
        state.ability_states_seed["rebakedTertiaryPosedEffects"] = \
            _rebake_tertiary_posed_effects(state)
    else:
        state.ability_states_seed = {"source": source, "seeded": None, "seededPassives": None,
                                     "seededTriggeredKits": None, "seededActives": None}
    # Effets de TUILE : APRÈS `_load_stats_and_effects` (qui REMPLACE `state.effects` par un
    # `EffectsState.seed` frais) et APRÈS que les `StatsComponent` des sources soient posés (le
    # niveau/multiplicateur d'un effet de tuile se lit sur son unité SOURCE, cf. `_load_tile_effects`).
    if tiles is not None:
        _load_tile_effects(state, tiles, board)
    # Board assigné en DERNIER (cf. docstring) : identique à un `state.board = board` que
    # l'appelant aurait posé après le retour de load_state — l'init/seed n'a jamais lu le board.
    if board is not None:
        state.board = board
    # AURA stat-mod PROJETEE (`AStatModifierEffect.ApplyModification` sur les cibles-selecteur d'un
    # effet porte par une AUTRE unité, ex. LionHelm +BlockDamage/+BlockChance aux alliés ≤2 hexes
    # d'Azrael) : la part est DÉJÀ dans le `combatSnapshot` de la cible, mais NON attribuée (l'effet
    # vit sur le porteur) → elle dort dans `CAPTURED_SOURCE` et rien ne peut la retirer quand la cible
    # sort du rayon. On la RE-ATTRIBUE sous la clé de l'effet, à somme constante (`GetStat(Current)`
    # inchangé). NO-OP strict tant qu'aucun porteur d'aura stat-mod n'est en jeu.
    attribute_aura_stat_modifiers(state)
    return state


def _load_feet(state: State, observe: dict) -> None:
    """Seed de l'EMPREINTE MULTI-HEX (#R30) depuis `observeBattle` — ORDRE DES PIEDS INCLUS.

    Le canal expose UNE LIGNE PAR PIED : `projectMatchState` « project one entry per visible piece,
    walking UnitFoot -> Tile for pos and UnitFoot -> Unit for HP/Owner » (match-state.ts). Chaque
    ligne porte l'`entityId` du PIED et le `squadId` de l'UNITE. Mesure live (Galatian, 3 pieds) :

        entityId=108 squadId=107 (2,1)   entityId=109 squadId=107 (2,2)   entityId=110 squadId=107 (3,2)

    L'ORDRE se DERIVE de l'`entityId` croissant, et ce n'est pas une convention arbitraire :
    `IdunBattle.Operations.AddUnitOperation$$Execute` cree les pieds DANS la boucle qui les ajoute
    (`id = PlayerIdGenerator.Next(); foot = Blueprints.UnitFoot(id); state.AddEntity(foot);
    unitComponent.AddFoot(foot.Id)`), et le generateur d'ids est monotone -> **entityId croissant ==
    ordre d'`AddFoot` == ordre de `_feet`**, donc `feet[0]` = la vraie main tile
    (`IdunBattle.Entities.EntityExtensions$$GetMainTileId`).

    ⚠ ET C'EST POURQUOI ON NE PART PAS DE `decisionView.units[].pos` : le projecteur emet une ligne
    par PIED et `decisionView` DEDUPLIQUE par unite -> pour Galatian il rend (3,2), c'est-a-dire le
    DERNIER pied, PAS la main tile (2,1). Un port qui prendrait `pos` pour l'ancre se tromperait
    d'un a deux hexes sur toute unite multi-hex. `set_unit_feet` recale donc la
    `PositionComponent` sur `feet[0]`.

    On ne materialise `UnitComponent.feet` que pour les unites qui ont PLUS D'UN pied — une unite a
    1 pied garde `feet = None` et sa `PositionComponent` n'est pas touchee : un etat charge est
    bit-a-bit celui d'avant ce seed."""
    rows: dict = {}
    for u in (observe.get("units") or []):
        uid, eid = u.get("squadId"), u.get("entityId")
        if uid is None or u.get("col") is None or u.get("row") is None:
            continue
        rows.setdefault(int(uid), []).append((eid if eid is not None else 0,
                                              (u["col"], u["row"])))
    for uid, feet in rows.items():
        if len(feet) < 2:
            continue                                  # unite mono-tuile : cas NOMINAL, on ne touche pas
        if state.get_entity(uid) is None:
            continue
        feet.sort(key=lambda x: x[0])                 # entityId croissant == ordre de `_feet`
        set_unit_feet(state, uid, [t for _eid, t in feet])


def _load_machines(state: State, decision: dict) -> None:
    """MACHINES OF WAR -> entités ECS — mirror de `IdunBattle.Operations.AddMachineOperation$$Execute`.

    Le natif crée la MoW comme une entité de PREMIER PLAN (`EntityType.Machine` = 6, littéral `6`
    passé au factory d'entités IdunBattle.Operations.AddMachineOperation$$Execute), puis lie sa/ses `MachinePlatform` (Type=7) via
    `MachinePlatformComponent.MachineId` (Nullable @+0x14/+0x18) et initialise ses abilities
    (`AddMachineOperation.InitializeAbilitiesStatus`). Jeu de composants MESURÉ sur l'entité vivante
    (`dumpEntityComponents`, runner MoW `tauBroadside`) :

        ParentComponent · EffectsOwnedComponent · TriggeredAbilityComponent · OwnerComponent ·
        AttackComponent · CritChanceComponent · CritDamageComponent · ActiveAbilityComponent ·
        UnitFlagsComponent · ExtraHits/ExtraPierce/ExtraPierceRanged/ExtraMaxDamageComponent ·
        MachineComponent · ActorStatisticsComponent

    -> **ni `HealthComponent` ni `PositionComponent`** : une MoW est HORS-PLATEAU (pas de PV, pas de
    tuile ; sa place visuelle vient du slot `MachineComponent.Position` = `MachineOfWarPosition`
    1=Top/2=Bottom, exposé `initialSlot`). Corroboré par gameconfig : les MoW ont
    `stats={Health:0, Damage:0, FixedArmor:0}` et `weapons=[]` (aucune attaque normale) — leur dégât
    vient des VARIABLES d'ability (`IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage`), pas d'une stat d'unité.

    On pose donc, à l'identique de la boucle unités MAIS **sans PositionComponent ni
    HealthComponent** :
      • `UnitComponent` — porteur d'identité ; le natif a `MachineComponent`, mais les DEUX dérivent
        de `BaseUnitComponent IdunBattle.Entities.Components.BaseUnitComponent$$.ctor` (VisualId@0x20 valide sur les deux, cf. `projectSquadStats`)
        et c'est ce rôle-là que porte `UnitComponent` côté port ;
      • `OwnerComponent` (team/player) ; `TriggeredAbilityComponent` (présent nativement) ;
      • `EffectsOwnedComponent` si la MoW porte des effets (elle en porte : `HeavyRailRifle_
        PendingAttack` s'y pose après le cast — mesuré).

    Sans cette matérialisation, `applyAction {casterId=<machineId>}` est exerçable LIVE mais
    INCONFRONTABLE offline (aucune entité caster), ce qui bloquait tout port d'ability MoW."""
    for m in _machine_rows(decision):
        mid = int(m["casterId"])
        if state.get_entity(mid) is not None:      # jamais écraser une unité chargée
            continue
        e = state.add_entity(mid)
        e.add_component(UnitComponent(visual_id=m.get("visualId"),
                                      alive=bool(m.get("alive", not m.get("isDead", False)))))
        e.add_component(OwnerComponent(team=m.get("team"), player=m.get("owner")))
        e.add_component(TriggeredAbilityComponent())
        e.add_component(MachineComponent(slot=m.get("slot")))
        # PAS de PositionComponent (hors-plateau) ; PAS de HealthComponent (aucun HealthComponent
        # natif -> `unit_is_alive` rend True sur hp inconnu, ce qui EST la sémantique MoW).
        # `ActiveAbilityComponent` EST dans le jeu de composants mesuré de l'entité Machine
        # (`dumpEntityComponents`) — c'est lui que le générateur d'action lit
        # (`ActiveAbilityActionGenerator$$GetUnitAbilitiesInOrder(this, activeAbilityComponent)`) et
        # que `AddMachineOperation$$InitializeAbilitiesStatus` peuple. Sans lui, la face DÉCISION MoW
        # n'a AUCUN état runtime d'ability offline (cooldown / munitions) — cf. R14.
        actives = _active_abilities(m)
        if actives:
            e.add_component(ActiveAbilitiesComponent(abilities=actives))
        effs = _effect_names(m)
        if effs:
            e.add_component(EffectsOwnedComponent(effects=effs))


def _load_machine_stats(state: State, decision: dict, snapshot: dict,
                        mult_by_id: Dict[int, int]) -> None:
    """`StatsComponent` des MoW — **le seul** chemin qui donne à une Machine son NIVEAU d'ability.

    DEUX canaux, disjoints, et c'est tout l'enjeu :

    • les STATS RÉSOLUES viennent de la ligne `EntityType.Machine` de `combatSnapshot` — elle EXISTE
      (le capteur remonte `Unit` ET `Machine` depuis `d9d0008`/#128 ; l'affirmation inverse qui vivait dans cet
      en-tête était PÉRIMÉE, et c'est elle qui a laissé passer #174). Mesure sur `deathCrawler` et
      `orksRukkatrukk` : les 19 stats sont à **0**, `statDelta={}`, `shields=[]`, `healthMax=0` —
      cohérent avec gameconfig (`stats={Health:0,Damage:0,FixedArmor:0}`, `weapons=[]`). On la
      consomme quand même : le jour où une stat-modification est posée sur une MoW en cours de combat
      (elle a bien Attack/CritChance/CritDamage/ExtraHits/ExtraPierce*/ExtraMaxDamage), `statDelta`
      la portera et `seed_unit_stats` l'attribuera comme pour une unité. Machine ABSENTE du snapshot
      (morte — le capteur filtre `IsAlive`) → ligne vide, les 8 stats de base retombent à 0, inchangé.

    • le NIVEAU et le MULTIPLICATEUR viennent de l'`AbilityState` per-ability
      (`IdunBattle.Entities.Components.ActiveAbility$$get_AbilityState`, cf. `_machine_ability_state`),
      JAMAIS de `unitConfig` : la ligne Machine rend `{"error": "visualId introuvable"}` parce que
      l'entité porte un `MachineComponent` et non un `UnitComponent` (deux FRÈRES dérivant de
      `IdunBattle.Entities.Components.BaseUnitComponent$$.ctor`) — et le capteur cherche la VisualId
      sur le second. On ÉCRASE donc l'`unitConfig` de la ligne par l'état lu du canal AbilityState.

    C'est ce niveau qui INDEXE les variables : `IdunBattle.Entities.Formulas.ConfigAmount$$Calculate`
    → `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` →
    `IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`, qui prend
    `idx = Math.Max(0, Idun.Shared.Level$$ToZeroBasedIndex(state.Level))` clampé à `len-1`
    (`ToZeroBasedIndex` = `value - 1`, et LÈVE `InvalidOperationException` si `value <= 0` : le
    niveau 0 n'existe pas nativement). Niveau 50 → index 49, jamais index 0.

    (Pas de `ablvl_by_id` : une MoW n'a AUCUNE passive en gameconfig — `passiveAbilities` absent sur
    les 8 MoW du pool — donc aucun niveau de passive à propager au seed d'effets.)"""
    import gameconfig as GC

    snap_rows = {u.get("entityId"): u for u in (snapshot.get("units") or [])
                 if u.get("entityType") == _ENTITY_TYPE_MACHINE}
    for m in _machine_rows(decision):
        mid = int(m["casterId"])
        ent = state.get_entity(mid)
        if ent is None or ent.get_component(StatsComponent) is not None:
            continue
        vis = m.get("visualId") or ""
        level, mult = _machine_ability_state(m)
        effs = EffectFactory.create_many(m.get("effects") or [], mult, None, level)
        ctx = UnitContext.from_snapshot(
            {**(snap_rows.get(mid) or {}), "entityId": mid, "visualId": vis,
             "unitConfig": {"activeAbilityLevel": level, "abilityVariablesMultiplier": mult}},
            GC.unit(vis), snapshot.get("statTypes"), effs)
        ctx.ability_variables_multiplier = mult
        ctx.active_ability_level = level
        mult_by_id[mid] = mult
        ent.add_component(StatsComponent(ctx=ctx))


def _load_unit_flags(state: State, snapshot: dict) -> None:
    """Seede le `UnitFlagsComponent` de CHAQUE entite depuis `combatSnapshot.units[].unitFlags`.

    MIRROR : `IdunBattle.Entities.Components.UnitFlagsComponent` (un `OrderedSet<UnitFlag>` @+0x10).
    Le capteur (`rpc-snapshot.ts`, section O5) ne lit PAS ce set en memoire — il invoque la fonction
    NOMMEE `IdunBattle.Entities.UnitExtensions$$HasFlag(unit, flag)` une fois par valeur d'enum, et
    rend la LISTE des ids poses ; `combatSnapshot.unitFlagTypes` donne le mapping nom -> id lu au
    RUNTIME (`dumpEnum`), donc `Moved` reste juste apres une renumerotation.

    POURQUOI (case-o10 SS 6, residu `blackObliterator`). `components.unit_has_moved` est le LECTEUR
    UNIQUE de `HasFlag(unit, UnitFlag.Moved)`, et jusqu'ici RIEN ne le peuplait sur un etat recharge :
    `set_moved_flag` n'est appele que par `MoveUnitOperation` (voie self-play/rollout OFFLINE). Dans un
    REPLAY-DIFF monte depuis un snapshot LIVE, toute unite ayant DEJA bouge etait donc vue
    « n'a pas bouge » — le gate no-move de
    `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier`
    (`... & (!HasFlag(Self, 0 = Moved) | HasFlag(Self, 0xc = Teleported))`) ne mordait JAMAIS et le
    +25% ranged etait accorde a chaque coup.

    MESURE (`probe_o10_volk_stage_split.py`, seed 777, board MC1_67, `blackObliterator` vs
    `necroWarden`, meme etat MT) : Volk DEPLACE puis tirant -> live 5868 / offline 7096 (l'offline
    rendait EXACTEMENT la meme valeur que sans deplacement, signature d'un gate aveugle) ; Volk NON
    deplace -> live 7096 == offline 7096. Meme sequence de coups et `mt_same=True` dans les deux cas :
    l'ecart n'etait ni un compte de coups ni une conso RNG, mais ce seul flag.

    Portee : TOUTES les lignes du snapshot (`EntityType.Unit` ET `EntityType.Machine` — une MoW porte
    un `UnitFlagsComponent`, cf. `dumpEntityComponents`).

    #545 -- LE COMPOSANT EST MATERIALISE SUR TOUTE LIGNE **MESUREE**, LISTE VIDE COMPRISE.
    `IdunBattle.Entities.Components.UnitFlagsComponent$$.ctor` construit un `OrderedSet` **VIDE** et
    `IdunBattle.Entities.Factories.UnitFactory` le monte sur **CHAQUE** unite : natif, « composant
    absent » n'existe pas. Ce module ne posait le composant que sur une liste **NON VIDE** (`not
    flags` -> `continue`), donc toute unite sans aucun flag n'en avait pas -- et chaque site qui
    fait `if fc is None: return` avant de POSER un flag devenait un **no-op silencieux**.
    MESURE (#498-r4-r1, `orksNob` sur `MC1_67`) : apres le cast de `1152`, le natif rend
    `unitFlags = [1, 2, 3, 4, 25]` et le port ne posait RIEN -- l'ecart que cette tranche-la visait
    etait INOBSERVABLE, masque par celui-ci. Il avait ete repare LOCALEMENT
    (`abilities/loki/momentum.py::_set_charge_flag`) ; c'est ici le FOYER.

    TRI-ETAT (meme discipline que `host_inputs.py`) : `unitFlags` **absent** ou **`null`** = le canal
    n'a PAS ete mesure -> on ne touche a RIEN (comportement anterieur, capteur plus ancien). Une
    LISTE (meme vide) = mesure -> composant materialise.

    RAYON DE SOUFFLE, mesure AVANT l'edition (`probe_545_unit_flags_component_vide.py` etape 1 --
    recensement AST des 40 sites `get_component(UnitFlagsComponent)` d'`engine/**`) : un composant
    VIDE et un composant ABSENT sont indiscernables de **38** d'entre eux (les lecteurs ecrivent
    tous `fl is not None and fl.has(X)` / `fl is None or not fl.has(X)`, et les ecrivains creent
    deja le composant absent). Les **2** qui les distinguent sont les deux abstentions de
    `operations/turnflow.py` -- `MarkUnitAsNoActionAvailableOperation.execute` et
    `VerifyUnitsTurnFinishedOperation.verify_unit_turn_ended` -- qui rendaient `found: False` sur
    composant absent. Elles deviennent ACTIVES, ce qui est **le comportement natif** : le natif y
    fait respectivement `TryGetComponent` sur une unite qui en porte TOUJOURS un, et
    `GetComponent` (qui LEVE). Aucun des deux ne peut plus s'abstenir sur une unite MESUREE.

    #429-r1-r3-r1 -- LES UNITES NON VIVANTES, ET POURQUOI IL A FALLU UN SECOND BLOC. Le capteur
    n'enumerait QUE les unites vivantes (`if (!invokeBool(isAliveMi, [e, statePtr])) return;`), ce
    qui rendait ce canal STRUCTURELLEMENT aveugle a `UnitFlag.Fled` (9) : une unite qui a FUI garde
    ses PV PLEINS mais `IdunBattle.Entities.UnitExtensions$$IsAlive` rend faux pour elle. MESURE du
    2026-08-05 (`probe_429r1r3r1_message_gate_perimeter.py --volet fled`) : garde `astraSmnGuardsman`
    hp 1000/1000, enfui -> le natif refuse le message (0 evenement, temoin a 2), le port la
    reconstruisait en unite VIVANTE INTACTE et la frappait pour 10375. `unitsNotAlive` porte
    desormais `entityId` + `unitFlags` pour ces entites-la.

    #429-r1-r3-r1-r1 -- LE TRI-ETAT EST ECRIT, PAS SOUS-ENTENDU. `snapshot.get("unitsNotAlive")
    or []` rend la MEME chose pour « lu, aucune entite non vivante » et pour « le bundle Frida
    charge est anterieur au correctif » : c'est exactement le rabattement `null -> []` qui a laisse
    `UnitFlag.Fled` hors d'atteinte du port pendant que son gate etait pourtant arme. La passe
    ECRIT donc son etat dans `state.unit_flags_seed` (`units_not_alive_channel` = `"lu"` / `"muet"`
    / `"absent"`), et tout consommateur qui veut conclure « aucune fuite » doit lire ce champ
    d'abord. Le comportement, lui, reste retro-compatible : champ absent -> on ne pose rien."""
    rows = list(snapshot.get("units") or [])
    _ABSENT = object()
    na = snapshot.get("unitsNotAlive", _ABSENT)
    if na is _ABSENT:
        canal, na_rows = "absent", []
    elif na is None:
        canal, na_rows = "muet", []
    else:
        canal, na_rows = "lu", list(na)
    poses_units = poses_na = vides = 0
    for idx, su in enumerate(rows + na_rows):
        eid = su.get("entityId")
        flags = su.get("unitFlags")
        # TRI-ETAT (#545) : une LISTE -- meme VIDE -- est une MESURE, donc le composant est
        # materialise ; `unitFlags` absent ou `null` = canal non mesure -> on ne touche a rien.
        if eid is None or not isinstance(flags, list):
            continue
        ent = state.get_entity(eid)
        if ent is None:
            continue
        fl = ent.get_component(UnitFlagsComponent)
        if fl is None:
            fl = ent.add_component(UnitFlagsComponent())   # #545 : VIDE compris
        for f in flags:
            try:
                fl.add(int(f))
            except (TypeError, ValueError):
                continue
        if not flags:
            vides += 1
        if idx < len(rows):
            poses_units += 1
        else:
            poses_na += 1
    state.unit_flags_seed = {
        # #545 : compte des lignes MATERIALISEES (liste vide comprise), pas des lignes « qui ont
        # pose au moins un flag ». Le canal est le meme ; c'est la portee du composant qui change.
        "units": poses_units,
        # `None` (jamais `0`) des que le canal n'a PAS ete mesure -- meme regle que `host_inputs.py`.
        "units_not_alive": poses_na if canal == "lu" else None,
        "units_not_alive_channel": canal,
        # Combien de ces lignes portaient une liste VIDE -- exactement les entites que le port
        # laissait SANS composant avant #545. Rendu pour que l'amplitude soit lisible, pas devinee.
        "vides": vides,
    }


def _load_unit_rarity(state: State, snapshot: dict) -> Optional[dict]:
    """Seede `UnitComponent.rarity` depuis les DEUX blocs de `combatSnapshot` -- `units[]` ET
    `unitsNotAlive[]` (#999-r3-r2).

    MIRROR : `BaseUnitComponent.Rarity` (`+0x74`), lu par
    `IdunBattle.Entities.UnitExtensions$$HasRarity` et
    `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select` apres
    `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent(e)`. Ce composant est la base
    COMMUNE de `UnitComponent` et `MachineComponent` : il n'est PAS conditionne a l'etat de vie.

    POURQUOI (residu #999-r3-r2). #999-r3 avait branche la rarete sur `UnitContext.rarity`, que
    `_load_stats_and_effects` ne construit que depuis `combatSnapshot.units[]` -- un canal
    ALIVE-ONLY. Une unite MORTE ou en FUITE n'avait donc AUCUNE rarete cote port : `HasRarity`
    rendait FAUX et `UnitsWithRarity(AllDeadUnits(...))` / `AllDeadOrResurrectedUnits` excluait la
    TOTALITE des morts. Degradation RESTRICTIVE, silencieuse, et le canal la portait deja :
    #1039 pose `rarity` sur `unitsNotAlive[]` EXACTEMENT pour la raison de `#429-r1-r3-r1` (une
    unite qui a FUI garde sa rarete). Meme forme que le repli gameconfig des traits d'un cadavre
    (#226, Foehammer), a ceci pres qu'ici il n'y a AUCUN repli a inventer : c'est une MESURE.

    TRI-ETAT, meme discipline que `_load_unit_flags` et `entities/rarity.py::measured_rarity` :
    `rarity` absent ou `null` = canal non mesure -> on ne pose RIEN (le champ garde son `None` de
    construction, comportement strictement anterieur, y compris sur un bundle Frida plus ancien
    que #1039). Un ordinal HORS de l'enum LEVE (via `measured_rarity`) : il ne peut vouloir dire
    qu'une chose -- le build a bouge sous le mirror.

    PORTEE : les DEUX blocs, et les DEUX `entityType`. Une MoW porte elle aussi un
    `BaseUnitComponent` (cf. `case-1039` Sec.4) et le port lui pose un `UnitComponent`
    (`_load_machines`) -- elle est donc seedee comme une unite. Le seed est IDEMPOTENT et ne
    DEPLACE rien pour les unites vivantes : `_unit_dict` continue de lire `ctx.rarity` en premier,
    et les deux viennent de la MEME ligne de capture.

    Rend le compte par bloc (ou `None` pour `unitsNotAlive` quand ce canal n'a pas ete mesure --
    jamais `0`, meme regle que `state.unit_flags_seed`)."""
    _ABSENT = object()
    na = snapshot.get("unitsNotAlive", _ABSENT)
    canal = "absent" if na is _ABSENT else ("muet" if na is None else "lu")
    na_rows = list(na) if canal == "lu" else []
    rows = list(snapshot.get("units") or [])
    poses_units = poses_na = 0
    for idx, su in enumerate(rows + na_rows):
        eid = su.get("entityId")
        if eid is None:
            continue
        r = measured_rarity(su)              # TRI-ETAT + refus d'un ordinal hors mirror
        if r is None:
            continue
        ent = state.get_entity(eid)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None:
            continue
        uc.rarity = r
        if idx < len(rows):
            poses_units += 1
        else:
            poses_na += 1
    return {"units": poses_units,
            "units_not_alive": poses_na if canal == "lu" else None,
            "units_not_alive_channel": canal}


def _load_unit_turn_state(state: State, snapshot: dict) -> None:
    """Seede les TROIS champs d'ETAT DE TOUR du `UnitComponent` depuis `combatSnapshot.units[]` :
    `turnsFinished` (@+0x5c), `currentTurnStartTile` (@+0x18c) et `chargedUnitIds` (@+0x190).

    Canal live : les capteurs `readUnitTurnState` (lecture MEMOIRE PURE des deux derniers champs) et
    l'invoke de `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished` de
    `frida/hooks/features/ai-step/rpc-snapshot.ts`. Pendant EXACT de
    `_load_unit_flags` : ce sont des ENTREES de gate, pas des sorties, et jusqu'ici RIEN ne les
    peuplait sur un etat recharge -- seules les operations OFFLINE les ecrivaient
    (`StartTurnOperation.execute` / `EndTurnOperation.execute` / `components.update_charging`).

    * **`turns_finished`** (#N11) -- compteur PER-UNITE des tours que CETTE unite a TERMINES, ECRIT
      par `IdunBattle.Operations.EndTurnOperation$$Execute` (`*(int *)(unitComponent + 0x5c) += 1`
      sur chaque id de `PlayerComponent.CurrentlyOwnedUnitIds` du joueur finissant, puis sur sa
      Machine of War) et RELU par `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished`. Ses
      consommateurs sont des GATES : `IdunBattle.Entities.Triggers.UnitHasFinishedMinTurnsAbilityTrigger$$ShouldTrigger`
      (le noeud `IdunBattleLogic.Entities.DSLFactory$$OwnerHasFinishedMinTurns`, gate de PileIn ->
      porte dans `operations/triggers/dispatch/turn.py`), plus
      `IdunBattle.AI.Playbook.Loki.DutyEternalPlaybook$$GetUseProbability` et
      `IdunBattle.AI.Playbook.Loki.InstrumentsOfVengeancePlaybook$$GetUseProbability`. Sans ce seed,
      TOUTE unite d'un etat recharge valait `turns_finished == 0` -- le gate
      `OwnerHasFinishedMinTurns(2)` rendait donc FAUX sur une unite qui a pourtant fini N>=2 tours
      cote natif : degradation RESTRICTIVE et silencieuse (le trigger ne fire jamais offline).
      ⚠ Ce n'est PAS un `StatType` : ni `combatSnapshot.stats` ni `GetStat` ne l'atteignent, d'ou
      l'accesseur dedie cote capteur. Et il n'est PAS derivable de `turnsStarted` (stat 12) -- une
      unite APPARUE PENDANT le tour de son proprietaire (tout summon) rate le bump de `StartTurn`
      mais prend celui d'`EndTurn`, et garde `turns_finished == turns_started + 1` ensuite.
      Portee : les lignes `EntityType.Unit` ET `EntityType.Machine` -- le natif a bien DEUX sites
      `+0x5c += 1` (unites puis MoW, meme offset, `GetTurnsFinished` a les deux branches d'EntityType)
      et le port materialise la MoW avec un `UnitComponent` (`_load_machines`), donc la meme boucle
      couvre les deux. `_load_machines` tourne AVANT cet appel, l'entite existe deja.

    * **`current_turn_start_tile`** -- ECRIT par `IdunBattle.Operations.StartTurnOperation$$Execute`
      (`mainTile = EntityExtensions.GetMainTile(unit) ; comp[0x18c] = mainTile?.Id ?? 0`), RELU par
      `IdunBattle.Entities.Selectors.CurrentTurnStartTileSelector$$Select` qui rend une liste VIDE
      quand le champ vaut 0. L'id emis est celui de l'ENTITE-TUILE natif, c.-a-d. exactement la cle
      de `Board.by_id` (le `boardGraph` projette les memes ids) : aucune conversion. Consommateur
      porte : le time-ghost de `thousTerminator`
      (`triggers/loki/ghost_revive.py`, `TimeFluxReviveAbility` -> `AddEffect(1186, targets=tile)`),
      qui rendait `None` -> branche `Nothing()` sur tout etat recharge, tant qu'un
      `StartTurnOperation` offline n'avait pas tourne.

    * **`charged_unit_ids`** -- second conjoint de `IdunBattle.Core.Services.BattleQuery$$IsCharging`
      (`AreEntitiesAdjacent(caster, target) && ChargedUnitIds.Contains(target.Id)`). Rempli par
      `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` (les unites NOUVELLEMENT adjacentes)
      et VIDE par `IdunBattle.Operations.FinishUnitTurnOperation$$Execute`. Sa duree de vie est donc
      **l'ACTIVATION** : un `combatSnapshot` pris ENTRE deux tours le voit toujours vide, et c'est
      CORRECT (mesure 2026-07-29 : `[]` partout apres 4 tours d'IA ; puis, apres un `act move`
      amenant u87 au contact SANS finir le tour, `charged=[77,79]` = exactement les deux ennemis
      devenus adjacents). Sans ce seed, la face PREDICTION sur etat recharge ignorait les charges
      DEJA acquises et OMETTAIT le bonus -- degradation RESTRICTIVE (`case-r32` SS 7).

    Ids : les elements de la liste native sont des ids d'ENTITE-UNITE, soit exactement la cle ECS du
    port (`combatSnapshot.entityId` == `decisionView.id`, cf. en-tete du module) -- aucune
    traduction.

    TRI-ETAT, meme discipline que `_load_unit_flags` : champ ABSENT ou `null` = **non mesure**
    (capteur anterieur a `f790ff4`, ou composant/classe/methode introuvable) -> on ne TOUCHE PAS au
    defaut du port, donc comportement STRICTEMENT anterieur. `[]` / un id de tuile / un entier =
    mesure, on ecrit. Le `null` de `currentTurnStartTile` recouvre les DEUX sens (« non mesure » et
    « le natif porte 0 »), mais les deux collapsent sur le MEME defaut de port (`None`), donc
    l'ambiguite est sans effet. Pour `turnsFinished` en revanche le tri-etat n'est PAS une
    precaution de style : le capteur rend `null` quand `GetTurnsFinished` est irresolue, et `0`
    quand l'unite a REELLEMENT fini zero tour -- confondre les deux ecraserait un defaut de port
    par une non-mesure (ici les deux valent 0, mais un `int(None)` leverait, et la distinction
    reste la seule lecture correcte du canal)."""
    for su in (snapshot.get("units") or []):
        eid = su.get("entityId")
        if eid is None:
            continue
        ent = state.get_entity(eid)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None:
            continue
        # `turnsFinished` = `UnitComponent + 0x5c` (invoke de `UnitExtensions$$GetTurnsFinished`).
        # `None` = non mesure -> on laisse le defaut du port (0) ; un entier = mesure, on ecrit.
        turns_finished = su.get("turnsFinished")
        if turns_finished is not None:
            uc.turns_finished = int(turns_finished)
        tile = su.get("currentTurnStartTile")
        if tile is not None:
            uc.current_turn_start_tile = int(tile)
        charged = su.get("chargedUnitIds")
        if isinstance(charged, list):
            uc.charged_unit_ids = [int(i) for i in charged]


def _load_turn_counts(state: State) -> None:
    """Seede `State.turn_counts` -- le dict PAR JOUEUR `TurnComponent+0x38`, que rend
    `IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsStartedByPlayer` -- DERIVE du
    compteur PER-UNITE deja capte (stat 12 = `TURNS_STARTED`, `UnitComponent+0x58`).

    POURQUOI UNE DERIVATION ET PAS UNE LECTURE : le dict natif n'est expose par AUCUN RPC. Le
    capteur `readTurnInfo` (`frida/hooks/game/match-state.ts`) l'invoque bien, mais seulement pour
    le joueur COURANT et seulement vers `recorder`/`cheat`/`move-options` -- ni `decisionView` ni
    `combatSnapshot` ne le publient. Le brancher exigerait un reinject.

    LA DERIVATION EST EXACTE, ET SA DIRECTION EST CONNUE. `IdunBattle.Operations.StartTurnOperation
    $$Execute` incremente `turnsStarted@+0x58` de CHAQUE unite VIVANTE de
    `PlayerComponent.CurrentlyOwnedUnitIds` a CHAQUE demarrage de tour -- le MEME EVENEMENT que
    l'ecriture de `TurnComponent+0x38[player]`, sans en etre la meme FONCTION : `+0x38` est ecrit
    par `TurnComponent$$SetCurrentPlayer` (ChangeTurn), `+0x58` par `StartTurnOperation`, et
    `EndTurnOperation$$Execute` enchaine les deux (mirror porte : `set_current_player` puis
    `_bump_turns_started`). Donc :

      * aucune unite ne peut porter PLUS de bumps que le nombre de tours demarres par son joueur
        -> `max(...)` ne SUR-ESTIME jamais ;
      * une unite presente et vivante depuis le 1er tour en porte EXACTEMENT autant
        -> `max(...)` est EXACT des qu'il en existe une.

    ⚠ UNE EXCEPTION, LUE ET NOMMEE (#287-r11-r1-r1-r1-r1-r1) : le regime NO-OP DECOUPLE les deux
    compteurs, cote NATIF. Quand `FindNextPlayer` rend le joueur COURANT (seul joueur encore
    jouable), `SetCurrentPlayer` sort AVANT ses deux bumps -- `+0x38` ne bouge pas -- mais
    `StartTurnOperation` est enfile SEPAREMENT par `EndTurnOperation$$Execute` et joue quand meme,
    donc `+0x58` per-unite avance. Sur N tours consecutifs dans ce regime, `max(stat 12)` SUR-estime
    `+0x38` de N. Le premier point ci-dessus vaut donc « hors NO-OP ». Ce n'est pas un ecart de
    port : la sur-estimation porte sur une mesure PRISE SUR LE NATIF, et le port produit exactement
    le meme decouplage depuis que `turn_counts` est ecrit a sa place native.

    Il ne SOUS-ESTIME que si toutes les unites du joueur sont apparues apres le debut (summons) ou
    ont manque des tours en etant mortes. Les unites MORTES sont exclues (le natif les retire de
    `CurrentlyOwnedUnitIds` par le `RemoveAll` de `PlayerComponent$$get_CurrentlyOwnedUnitIds`,
    donc leur compteur est GELE et fausserait le max vers le bas s'il etait le seul).

    LECTEURS DU CHAMP, et pourquoi le zero d'avant etait faux : le noeud DSL `PlayerTurnsStarted`
    (`IdunBattle.Entities.Formulas.UnitsPlayerTurnsStartedFormula$$Calculate`), qui indexe le cycle
    a 3 temps de `SereneUnifierAbility` -- un `turn_counts` vide y rendait `0 % 3 == 0` pour tout le
    monde, donc la phase `StormOfFire` a chaque rejeu, quel que soit le vrai round ; et le gate
    `AmountIsEqual(Difference(CurrentPlayerTurnsStarted, TurnDefeated(u)), 1)` d'`EnvAmbushResurrect`
    (celui-la etait deja juste par COMPENSATION -- `turn_defeated` est pose depuis le MEME dict, donc
    la DIFFERENCE etait bonne meme avec deux zeros).

    Tri-etat : un joueur sans aucune unite vivante portant la stat n'entre PAS au dict (on ne
    fabrique pas un `0` qui se lirait comme une mesure)."""
    per_player: dict[int, int] = {}
    for e in state.entities.values():
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.player is None:
            continue
        uc = e.get_component(UnitComponent)
        if uc is not None and not uc.alive:        # `RemoveAll(<defait>)` de CurrentlyOwnedUnitIds
            continue
        sc = e.get_component(StatsComponent)
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        if us is None:
            continue
        n = us.get_stat(int(StatType.TURNS_STARTED), 0)
        if n is None:
            continue
        p = int(oc.player)
        per_player[p] = max(per_player.get(p, 0), int(n))
    for p, n in per_player.items():
        state.turn_counts[p] = n


def _load_turns_ended(state: State) -> None:
    """Seede `State.turns_ended` -- le dict PAR JOUEUR `TurnComponent.<Dictionary @+0x40>`, que rend
    `IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEndedByPlayer` -- par l'IDENTITE
    que fixe son ECRIVAIN UNIQUE.

    L'IDENTITE, ET CE QUI L'ETABLIT. `IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer`
    est le SEUL ecrivain des deux dictionnaires (verifie sur les 19 methodes de `TurnComponent` :
    `.ctor` les cree vides, `Copy` les clone, aucune autre ne les touche), et son SEUL appelant est
    `IdunBattle.Operations.ChangeTurnOperation$$Execute`. Chaque appel MUTANT fait exactement, dans
    cet ordre : `ended[SORTANT] += 1` (si le sortant n'est pas 0) et `started[ENTRANT] += 1` ; un
    appel ou `cur == next` retourne AVANT les deux. Donc, a tout instant :

        ended[p] == started[p] - (p == CurrentPlayerId ? 1 : 0)

    -- le joueur COURANT a un tour demarre de plus que termine, tous les autres sont a egalite. Elle
    tient aussi sous joueur TEMPORAIRE (`+0x28`), ou `get_CurrentPlayerId` rend le temp : les deux
    bumps portent alors sur LUI, donc l'ecart reste 1.

    CE N'EST DONC PAS UN AJUSTEMENT, et surtout pas un des deux rabattements que le residu
    `#287-r11-r1-r1-r1` interdisait : `decisionView.turnsEnded` publie `Sum(dict.Values)` (la SOMME
    sur tous les joueurs) et `State.turn_counts` est l'AUTRE dictionnaire. Ici on ne substitue rien --
    on RECONSTRUIT la ventilation depuis la ventilation jumelle et le joueur courant.

    PORTEE DE LA MESURE, honnetement bornee : `turns_ended` est EXACT **par rapport a**
    `turn_counts`, qui est lui-meme DERIVE (`_load_turn_counts` prend le `max` de la stat 12
    per-unite). Les modes de sous-estimation de `turn_counts` sont donc herites tels quels -- un
    joueur dont TOUTES les unites sont apparues apres le debut, ou ont manque des tours en etant
    mortes. Direction de l'ecart : `ended` SOUS-estime -> `limit - ended` SUR-estime ->
    `has_minimum_remaining_turns` est PERMISSIF. Le supprimer demanderait un capteur qui publie les
    deux dictionnaires (aucun RPC ne le fait : `readTurnInfo` de `frida/hooks/game/match-state.ts`
    n'invoque `GetAmountOfTurnsStartedByPlayer` que pour le joueur COURANT, et vers
    `recorder`/`cheat`/`move-options`, jamais vers `decisionView`/`combatSnapshot`).

    Tri-etat : un joueur ABSENT de `turn_counts` reste ABSENT ici (on ne fabrique pas un `0` qui se
    lirait comme une mesure) -- et la LECTURE de ce dict, `battle_query.get_amount_of_turns_ended_by
    _player`, rend `0` sur cle absente parce que c'est ce que rend le natif (`!ContainsKey`)."""
    cur = state.current_player_id
    for p, started in state.turn_counts.items():
        ended = int(started) - (1 if (cur is not None and int(cur) == int(p)) else 0)
        state.turns_ended[int(p)] = max(0, ended)      # `started == 0` ne peut pas rendre `ended < 0`


def _load_unit_parent(state: State, snapshot: dict) -> None:
    """Seede `UnitComponent.parent_id` depuis `combatSnapshot.units[]` (`parentId` +
    `parentMeasured`, capteur #378).

    MIRROR : `IdunBattle.Entities.Components.ChildComponent`, champ `ParentId` (`BEntityId` =
    int32). C'est le champ que lit `IdunBattle.Entities.UnitExtensions$$GetParent` --
    `TryGetComponent<ChildComponent>(child)` puis `state.GetEntity(comp.ParentId)` -- foyer du
    selecteur `IdunBattle.Entities.Selectors.ParentSelector$$Select` (noeud DSL
    `IdunBattleLogic.Entities.DSLSelectors$$Parent`).
    ⚠ Ce n'est PAS `ParentComponent`, dont le `+0x10` est `ChildrenIds` (sens parent -> enfants) :
    l'ancrage nomme par le residu de #372 designait l'autre bout du lien.

    POURQUOI. Pendant EXACT de `_load_unit_flags` / `_load_unit_turn_state` : une ENTREE de gate que
    RIEN ne peuplait sur un etat recharge. Seule la voie OFFLINE l'ecrivait
    (`SpawnUnitOperation` -> `UnitComponent(parent_id=caster_id)`), donc le lien n'existait que si
    le summon avait ete invoque DANS le rejeu. Un etat hydrate d'une capture prise APRES le spawn
    repartait a `parent_id = None`, et les DEUX lecteurs portes du lien devenaient aveugles :

      * `runner/damage_model.py::build_hits_board` -> `parent_by_id`, consomme par le noeud
        `If( AmountIsGreaterThanZero(Parent(EffectSource)), Parent(EffectSource), EffectSource )`
        de `IdunBattle.Entities.Effects.Loki.DefenderOfTheGreaterGood_ExtraHitsEffect$$
        CreateEffectHitsBonusForAttack`. Le jumeau DRONE (`1307`) y lisait SES tours au lieu de
        ceux de Shadowsun -- chance SOUS-ESTIMEE (degradation restrictive, cf. case-372 SS 7) ;
      * `entities/selectors/tiles.py::Parent`, le selecteur lui-meme
        (`ListenUpMaggotsEffect$$CreateTargetSelector` = `Parent(Self)`,
        `SwornProtector_ProtectAbility$$CreateBehaviour` = `SwitchPosition(Self, Parent(Self))`).

    TRI-ETAT -- et ici il est LOAD-BEARING, pas une precaution de style. Le capteur rend DEUX
    champs : `parentMeasured` (la mesure a-t-elle eu lieu ?) et `parentId` (son resultat). On
    n'ecrit QUE si `parentMeasured is True`. Sinon on ne TOUCHE A RIEN -- car ecrire le `None`
    d'une non-mesure EFFACERAIT un `parent_id` que la simulation offline avait, lui, correctement
    pose au spawn : un capteur muet (hook anterieur a #378, classe `ChildComponent` irresolue)
    deviendrait ainsi une REGRESSION de la voie qui marchait deja. `parentMeasured=True` +
    `parentId=None` est en revanche une mesure PLEINE (« cette unite n'est l'enfant de personne »,
    la sortie `TryGetComponent == false` du natif) : on l'ecrit, elle EFFACE legitimement.

    Portee : toutes les lignes du snapshot (`EntityType.Unit` ET `EntityType.Machine` -- le port
    materialise la MoW avec un `UnitComponent` via `_load_machines`, qui tourne AVANT).
    Ids : `combatSnapshot.entityId` == cle ECS du port, aucune traduction (cf. en-tete du module)."""
    for su in (snapshot.get("units") or []):
        eid = su.get("entityId")
        if eid is None:
            continue
        ent = state.get_entity(eid)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None:
            continue
        if su.get("parentMeasured") is not True:
            continue                      # capteur muet -> on garde ce que la simulation a pose
        pid = su.get("parentId")
        uc.parent_id = None if pid is None else int(pid)


def _load_forced_attack_targets(state: State) -> None:
    """Seede `ForcedAttackTargetsComponent` depuis les effets DEJA materialises dans `state.effects`
    (canal `bondedEntityId` + `bondMeasured` de la vue d'effet, capteur #436-r1).

    MIRROR de `IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal`, queue de la fonction :

        comp = target.GetComponent<ForcedAttackTargetsComponent>();
        list = new List<int>(); list.Add(ABondEffect.BondedEntityId(this, effect));
        comp.<+0x50> = list;                          // REMPLACE la liste

    C'est exactement ce que fait `AddEffectOperation._apply_forced_attack_targets` sur la voie de
    POSE ; ici on rejoue la MEME ecriture pour un effet 27 arrive par HYDRATATION.

    POURQUOI. Pendant EXACT de `_load_unit_parent` (#378) : une ENTREE de gate que RIEN ne peuplait
    sur un etat recharge. Seule la voie OFFLINE l'ecrivait -- le port ne voyait donc la restriction
    `TargetIsAllowedForCaster` (bit 23, `engine/runner/abilities/targeting.py::get_only_targets`)
    que quand c'etait LUI qui avait pose l'effet. Un etat reconstruit d'une capture prise APRES un
    taunt du jeu repartait `GetOnlyTargets == []`, et la regle -- dont le natif ne l'arme QUE si la
    liste est non vide -- ne refusait plus rien. Degradation PERMISSIVE : ni erreur ni crash, donc
    invisible en self-play, et c'est le trou qu'un entrainement irait exploiter.

    TRI-ETAT : la selection porte sur `eff.bonded is not None`, que `EffectFactory.create` n'ecrit
    QUE sous `bondMeasured is True` (cf. son commentaire). Un capteur MUET -- hook anterieur a
    #436-r1, classe `BondComponent` irresolue -- laisse donc `bonded = None` sur tous les effets, et
    cette passe ne pose RIEN : comportement STRICTEMENT anterieur, jamais une liste inventee.
    ⚠ Ne PAS retomber sur `eff.source` en repli : pour les quatre producteurs lus,
    `bondedEntityId == source de l'effet`, mais hydrater par `source` serait une DEDUCTION, pas une
    lecture -- et une liste fausse ici fait REFUSER un cast que le natif accepte (degradation
    RESTRICTIVE, l'inverse de la convention permissive de tout ce module).

    Le gate de CLASSE est `BaseEffect.writes_forced_attack_targets()` -- la meme part DATA que la
    voie de pose, donc aucune duplication de la regle : seul `TauntedEffect` (27
    `Taunted_OnlySpecificTargets`) la pose. Un effet BONDE qui n'ecrit pas de cible forcee
    (`TunnelingHorror_PendingSummon`, `HazeOfCorruption_DamageTransfer`) est ignore ici, et c'est
    correct : son bonded sert ailleurs.

    Le composant est CREE a la demande, comme sur la voie de pose (le natif l'a par blueprint sur
    toute unite ; offline il n'existe que la ou une ecriture a eu lieu -- `get_only_targets` traite
    son absence comme la liste vide, exactement comme le `TryGetComponent` faux du natif)."""
    effects = getattr(state, "effects", None)
    if effects is None:
        return
    for uid, effs in (getattr(effects, "by_unit", None) or {}).items():
        for eff in (effs or []):
            if not eff.writes_forced_attack_targets():
                continue
            bonded = getattr(eff, "bonded", None)
            if bonded is None:
                continue                  # capteur muet OU effet sans lien -> on n'ecrit RIEN
            ent = state.get_entity(int(uid))
            if ent is None:
                continue
            comp = ent.get_component(ForcedAttackTargetsComponent)
            if comp is None:
                comp = ForcedAttackTargetsComponent()
                ent.add_component(comp)
            comp.set_from_effect(eff, [int(bonded)])


def _load_battle_counters(state: State, decision: dict) -> None:
    """Pousse le COMPTEUR DE BATAILLE `melee_defeats` sur les effets qui le declarent -- foyer
    PARTAGE `engine.entities.effects_state.seed_battle_counters`, le MEME que la face DECISION
    (`playbook/scene.py::_seed_battle_counters`).

    POURQUOI, et ce que son absence a coute (#953). Pendant EXACT de `_load_forced_attack_targets`
    et de `_load_effect_parent_links` : une ENTREE de gate que **seule la face DECISION** posait.
    Sur un etat RECHARGE, `BlessingsOfKhorneModifiersEffect.melee_defeats` restait donc `None` ->
    `N = 0` -> le `+3 % x N` que ce trait verse sur TOUT le degat sortant d'un World Eater
    DISPARAISSAIT des le premier kill de melee -- silencieusement, et hors de portee de tout test
    (le regime exige un kill de MELEE avant la mesure).

    MESURE (`probe_953_954_skullsmasher_obsessive_annunciation.py`, bras `sk_stun`, `worldJakhal`
    apres UN kill de melee) : natif `[1210, 1204, 503]` = 2917, port `[791, 607, 1089]` = 2487 ; en
    forcant `melee_defeats = 1` sur l'instance, le port rend **exactement** `[1210, 1204, 503]`.
    L'ecart n'est PAS un facteur de 3 % lisible : le bonus deplace `min`/`max`, donc chaque tirage
    tombe sur un autre entier.

    Le canal EXISTE et etait deja publie : `decisionView.units[].defeatedByMelee` (mesure :
    `True` sur l'unite morte en melee, `False` sur les vivantes). Rien a capter, juste a LIRE."""
    _effects_state.seed_battle_counters(state.effects, (decision or {}).get("units") or [])


def _load_death_sources(state: State, decision: dict) -> int:
    """Seede les DEUX substrats de la MORT que seule la simulation posait -- le tueur de chaque
    cadavre, et le registre des victimes de chaque tueur. Ferme #1033-r3 et #951-r3.

    ## Le canal etait la, et il publie plus qu'on ne lui demandait

    `decisionView.units[]` porte depuis #185 DEUX champs par unite, lus sur le SQUAD (donc valides
    sur les CORPSES) par `frida/hooks/game/match-state.ts::readUnitDeathMeta` :

      * `killerId`        = `DamageSource.get_KillerId` du `Nullable<DamageSource>` @+0x108,
                            `null` des que le getter rend `<= 0` ou que le `Nullable` est vide ;
      * `defeatedByMelee` = le byte `UnitComponent.DefeatedByMeleeAttack` @+0x178.

    ## Pourquoi ces deux champs suffisent a reconstruire le registre du TUEUR

    C'est le fait central, et il se LIT dans `IdunBattle.Operations.KillUnitOperation$$Execute` :
    la fonction ecrit `local_378[0]` dans `UnitComponent+0x178` de la VICTIME, puis passe **ce meme
    `local_378[0]`** en troisieme argument de `RegisterDefeatedUnit(stats_du_tueur, id_victime,
    inMelee)`. Le booleen qui choisit entre `@+0xa8` (melee) et `@+0xb0` (autres) sur le TUEUR est
    donc, octet pour octet, celui qu'on lit sur la VICTIME. L'inversion `victime -> tueur` est
    exacte, et c'est ce qui REFUTE la premisse << aucun canal ne publie ce compteur >> de #951-r3 :
    aucun capteur neuf n'etait requis, seulement la lecture du canal dans l'autre sens.

    Les DEUX gates natifs de l'inscription sont mirrores par `register_defeated_unit` lui-meme
    (`IsActor(killer)`, `!IsSteppable(killed)`), qu'on rappelle ici plutot que de pousser dans les
    listes -- un seul foyer d'ecriture.

    ## Ce qui N'EST PAS seede, et pourquoi ce n'est pas une omission

    `death_source` (le tuple complet) reste INTACT. Le canal ne mesure QUE le `KillerId` ; les deux
    autres composantes de la `DamageSource` (`DamageReason` @+0x14, `Nullable<AbilityOrEffect>`
    @+0x18) n'ont aucun canal, et DEUX lecteurs portes les consomment vraiment --
    `operations/triggers/loki/reactivate_overwatch.py` lit les deux, `...loki/empyric_ambush.py` le
    second. Fabriquer un tuple a composantes inventees leur ferait rendre un FAUX au lieu d'un
    << inconnu >> : c'est exactement la degradation que le tri-etat existe pour empecher. Le seed
    ecrit donc `death_killer_id`, et `components.death_killer_id()` compose les deux sources.

    IDEMPOTENT : n'ecrase jamais une valeur deja posee par le run (etat mixte capture + simulation).
    Rend le nombre de cadavres dont le tueur a ete seede."""
    n = 0
    for u in ((decision or {}).get("units") or []):
        if not isinstance(u, Mapping) or u.get("alive"):
            continue                       # `IsDead(unit)` -- un vivant n'a pas de `DeathReason`
        kid = u.get("killerId")
        if kid is None:
            continue                       # tueur non imputable -> le natif ne compte rien non plus
        uid = u.get("id")
        if uid is None:
            continue
        ent = state.get_entity(int(uid))
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None:
            continue
        if uc.death_killer_id is None and getattr(uc, "death_source", None) is None:
            uc.death_killer_id = int(kid)
            n += 1
        # Le registre du TUEUR, par le meme booleen que le natif : cf. la section ci-dessus.
        register_defeated_unit(state, int(kid), int(uid),
                               in_melee=bool(u.get("defeatedByMelee")))
    return n


def _load_effect_parent_links(state: State) -> None:
    """Reconstruit `BaseEffect.parent_type` (lien `EffectComponent.ParentEffect@+0x70`) sur un etat
    HYDRATE, depuis les instances deja materialisees dans `state.effects`.

    POURQUOI. Pendant EXACT de `_load_forced_attack_targets` : seule la voie OFFLINE ecrivait ce
    lien (`AddEffectOperation._spawn_sub_effects`). Sur un etat reconstruit d'une capture prise
    APRES la pose d'un composite, les enfants arrivaient ORPHELINS -- et les DEUX consommateurs du
    lien devenaient muets : la cascade d'expiration (`EffectsState.on_turn_end`) et le mirror de
    `IdunBattle.Operations.RemoveEffectOperation$$RemoveSubEffects`
    (`operations/remove_effects._remove_sub_effects`). Symptome MESURE le 2026-08-05 : le trigger
    (b) d'`ABondEffect` retirait bien le composite 27 sur un etat capture, et `[25, 26, 1237]`
    restaient sur la cible -- la ou le natif rend une liste VIDE.

    RECONSTRUCTION, et non lecture : le canal natif est la liste `SubEffects@+0x78`, qu'aucun RPC
    n'expose. La source du port est la meme part DATA que la voie de pose --
    `BaseEffect.sub_effects_on_apply()`, mirror de `<Effect>.ApplyInternal`. L'attribution est
    UNIQUE parce qu'`AddEffectOperation` garantit au plus UNE instance non consommee d'un
    `effect_type` par unite : si le porteur a le parent ET un type que ce parent declare, cette
    instance EST son enfant. Les deux composites du port (`Stunned` 1162 -> 1165/1166/1167,
    `Taunted` 27 -> 25/26/1237) ont d'ailleurs des types d'enfant qu'aucune autre voie ne pose.

    N'ECRASE JAMAIS un `parent_type` deja pose (etat mixte capture + simulation).

    ⚠ UN ENFANT PEUT VIVRE SUR L'ENTITE BONDEE, pas sur le porteur du parent
    (`SubEffectSpec.on_bonded_entity` -- `IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect$$
    ApplyInternal` pose trois de ses quatre enfants sur le CHAMPION alors que 1091 vit sur
    l'ennemi). L'appariement se fait donc dans la liste du porteur DESIGNE PAR LA SPEC, exactement
    comme la voie de pose."""
    effects = getattr(state, "effects", None)
    if effects is None:
        return
    by_unit = getattr(effects, "by_unit", None) or {}

    def _live_by_type(carrier):
        out = {}
        for e in (by_unit.get(int(carrier)) or ()):
            if not e.consumed and e.effect_type is not None:
                out.setdefault(int(e.effect_type), e)
        return out

    for uid, effs in by_unit.items():
        live = [e for e in (effs or []) if not e.consumed]
        if not live:
            continue
        by_type = _live_by_type(uid)
        for parent in live:
            for spec in parent.sub_effects_on_apply():
                if getattr(spec, "on_bonded_entity", False):
                    bonded = getattr(parent, "bonded", None)
                    if bonded is None or int(bonded) == int(uid):
                        continue
                    child = _live_by_type(bonded).get(int(spec.effect_type))
                else:
                    child = by_type.get(int(spec.effect_type))
                if child is not None and child is not parent and child.parent_type is None:
                    child.parent_type = int(parent.effect_type)
                    # #524-r1 : le BOND descend du parent, ici aussi. Le capteur publie bien
                    # `bondedEntityId` par entite-effet (`bondMeasured` vrai sur les trois enfants
                    # d'un `Taunted`), mais `EffectFactory.create` ne le lit que pour l'effet qu'on
                    # lui donne : un enfant RECONSTRUIT arrivait sans bond, la ou la POSE le lui
                    # donne (`AddEffectOperation._spawn_sub_effects`). Deux foyers, un seul
                    # invariant -- et c'est le foyer que les tests LIVE traversent, puisqu'ils
                    # chargent leur `State` d'une capture.
                    # ⚠ Le bond de l'enfant bascule AVEC son porteur : `b__0` (enfant sur le
                    # porteur du parent) recoit `ctx.<+0x18>` = le bonde du parent, `b__1..b__3`
                    # (enfants sur le bonde) recoivent `ctx.<+0x20>.Id` = le porteur du parent.
                    # MEME derivation que la voie de pose (`_spawn_sub_effects`).
                    # N'ECRASE JAMAIS un bond deja pose (meme regle que `parent_type` ci-dessus).
                    if getattr(child, "bonded", None) is None:
                        child.bonded = (int(uid) if getattr(spec, "on_bonded_entity", False)
                                        else getattr(parent, "bonded", None))


def _load_actor_statistics(state: State, actor_stats: dict) -> None:
    """Seede les TROIS compteurs de tuiles parcourues du `UnitComponent` depuis le RPC `actorStats`
    (`#340-r1`), plus `TotalTurnsWithAttacksMade` (`#509`).

    MIRROR : `IdunBattle.Entities.Components.ActorStatisticsComponent @+0xec` (cumul BATAILLE),
    `@+0xf0` (cumul CE TOUR) et `@+0xf4` (tour PRECEDENT) -- les trois champs contigus qu'ecrit
    `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` (`+=` sur les deux premiers, garde
    `< 1`) et que roule `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn`
    en FIN de tour (`+0xf4 = +0xf0` si `wasOwnTurn`, puis `+0xf0 = 0` INCONDITIONNEL).
    `+0xf0` est ce que rend `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate`.

    POURQUOI. Pendant EXACT de `_load_unit_flags` (#210) et `_load_unit_turn_state` : ce sont des
    ENTREES de gate, pas des sorties, et jusqu'ici RIEN ne les peuplait sur un etat recharge --
    seules les operations OFFLINE les ecrivaient (`components.record_tiles_moved`, appele par
    `MoveUnitOperation`, et `reset_tiles_moved_this_turn` par `EndTurnOperation`, tous deux #335).
    Un `State` reconstruit d'une capture live prise APRES un deplacement repartait donc a zero, et
    `ModifiedExoarmour_ExtraDmgEffect` -- dont la magnitude est `V x n` -- y devenait inerte SANS
    la moindre erreur. Le rejeu offline d'un `MoveUnitMessage` (voie `probe_335.offline_state`)
    masquait le trou : c'est le moteur qui reposait le compteur.

    TRI-ETAT, meme discipline que les seeds voisins : une unite n'est seedee QUE si le champ est
    PRESENT et non `null`. Sur un hook qui ne publie pas encore `+0xf0` (avant le deploiement du
    capteur) la boucle ne pose RIEN et les compteurs gardent leur 0 de construction -- le
    comportement d'avant, a l'identique. Un `0` publie est un vrai zero (l'unite n'a pas bouge).

    ⚠ GARDE `< 0` -- ce n'est PAS de la defense de principe, c'est un invariant NATIF.
    Les trois champs sont des compteurs a increments `>= 1` (`RecordTilesMoved` sort sur
    `if ((int)tiles < 1) return;`), remis a `0` ou copies l'un dans l'autre par `ResetThisTurn` :
    aucune ecriture native ne peut les rendre negatifs. Une valeur `< 0` denonce donc une LECTURE
    invalide, jamais un etat de jeu -- et on refuse de l'ingerer plutot que de propager du faux
    dans l'ECS. MESURE qui a impose ce garde (2026-07-31, `probe_340_r1_actorstats_live.py`) :
    `tilesMovedThisBattle` et `tilesMovedLastTurn` rendaient tous deux **-1201836032**, la MEME
    valeur, parce que `getFieldOffset` rend **-1** sur un nom absent et que le hook les resolvait
    par `getFieldOffset(...) || 0xec` -- or `-1` est *truthy* en JS, donc le fallback decompile
    n'etait jamais pris et les deux champs lisaient `comp - 1`, la MEME adresse. Le correctif du
    hook est livre mais EXIGE UNE REINJECTION ; en attendant, ce garde laisse ces deux champs a
    leur 0 de construction (aucun lecteur porte pour `+0xec` ; `+0xf4` n'en a pas non plus) tandis
    que `+0xf0`, dont le nom EXISTE et qui est mesure exact, passe normalement.

    ⚠ `attacksMadeThisTurn` (`+0x24`, #545-r1) ET `attacksReceivedThisTurn` (`+0x38`, #287-r5-r2)
    SONT EN VOL depuis la fenetre du 2026-08-15 -- MESURE, pas suppose : l'appel `actorStats` de
    la session 93 rend les neuf cles `attacksMadeThisTurn, attacksReceivedThisTurn, entityId,
    movement, tilesMovedLastTurn, tilesMovedThisBattle, tilesMovedThisTurn, totalAttacksMade,
    totalTurnsWithAttacksMade`. La redaction precedente de ce bloc annoncait qu'ils << ne seront
    PUBLIES qu'une fois le bundle re-injecte >> : elle est PERIMEE, et c'est exactement la forme
    de peremption qui fait re-ouvrir un residu deja resolu.

    ⚠ HUITIEME CHAMP, ET IL N'EST PAS UN SCALAIRE (#487-r2) : `receiveDamageTypeThisTurn`
    (`ActorStatisticsComponent+0x80`) est un `Dictionary<DamageProfileType, int>`, pas un compteur.
    Il ne peut donc PAS entrer dans la boucle des sept ci-dessous, et son seed vit dans
    `_load_received_damage_types`. Le champ IL2CPP s'appelle `ReceiveDamageTypeThisTurn` -- et
    NON `ReceivedDamageThisTurn`, que nommait la fiche."""
    for su in ((actor_stats or {}).get("units") or []):
        uid = su.get("entityId")
        if uid is None:
            continue
        ent = state.get_entity(uid)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None:
            continue
        # #509 : `TotalTurnsWithAttacksMade` (`ActorStatisticsComponent @+0x30`) rejoint la boucle.
        # MEME canal, MEME hook (`rpc-snapshot.ts` le publie DEJA sous
        # `totalTurnsWithAttacksMade`, resolu par `fieldOffsetOr(asClass, "TotalTurnsWith
        # AttacksMade", 0x30)`), MEME tri-etat et MEME garde `< 0` -- il n'y avait simplement
        # aucun lecteur porte avant que `MartialInspiration_ExtraDamageEffect` n'en devienne un.
        # C'est aussi un compteur a increments `>= 1` : `...$$RegisterAttackMade` fait `+0x30 += 1`
        # sous `Count(+0x40) == 0`, et RIEN ne le remet a zero (seul le SET `+0x40` est vide, par
        # `ResetUnitsAttackedThisTurn`) -> une valeur negative denonce une lecture invalide.
        # #926 : `TotalAttacksMade` (`+0x20`) rejoint la boucle -- MEME canal, MEME hook
        # (`rpc-snapshot.ts` publie DEJA `totalAttacksMade`, lu depuis toujours par la face
        # PREDICTION via `playbook/scene.py::actorstats_by_id`), MEME tri-etat et MEME garde `< 0`.
        # Il n'y avait aucun consommateur du `State` avant que `FirstAmongTraitors_ExtraDmgEffect`
        # n'en devienne un ; le seeder est ce qui evite qu'un runner monte SUR UNE BATAILLE EN
        # COURS reparte d'un compteur a 0 la ou la prediction, elle, voit la vraie valeur.
        # C'est aussi un compteur a increments `>= 1` que RIEN ne remet a zero (cf.
        # `components.register_attack_made`) -> une valeur negative denonce une lecture invalide.
        # #545-r1 -- `TotalAttacksMadeThisTurn` (`+0x24`) rejoint la boucle. MEME canal, MEME hook,
        # MEME tri-etat, MEME garde `< 0`. Le champ etait le SEUL des compteurs d'attaque a n'avoir
        # aucun canal de seed alors que le port l'ecrit (`register_attack_made`), le remet a zero
        # (`reset_units_attacked_this_turn`, `*(long long*)(this + 0x24) = 0`) et le LIT par
        # `components.unit_attacks_made_this_turn` = `IdunBattle.Entities.Formulas.
        # AmountOfAttacksMadeThisTurnFormula$$Calculate` dans son regime `Nullable` VIDE.
        # ⚠ L'enonce d'origine du residu (<< INERTE pour le seul consommateur porte >>) est PERIME :
        # les consommateurs sont TROIS, et DEUX lisent la valeur ABSOLUE, pas une variation --
        # `IconOfObstinacy_AddArmourBuffTrigger.matches` (`AmountIsZero(...)`, donc `== 0`) et
        # `LegacyOfCombatTrigger.matches` (`AmountIsEqual(..., Direct(1))`). Sur un etat recharge
        # apres qu'une unite a deja frappe ce tour-la, le port rendait 0 et ACCORDAIT le buff que
        # le natif refuse. Seul `LeadingTheCharge` compare le compteur a lui-meme.
        # C'est aussi un compteur a increments `>= 1`, remis a `0` -- une valeur negative denonce
        # une lecture invalide.
        #
        # #287-r5-r2 -- `NumAttacksReceivedThisTurn` (`+0x38`) rejoint la boucle POUR LA MEME
        # RAISON et par le MEME canal. `IdunBattle.Entities.EntityExtensions$$
        # GetNumAttacksReceivedThisTurn` le lit ; le port l'a sous le nom `times_attacked_this_turn`
        # (⚠ a ne pas confondre avec `total_times_attacked`, `+0x34`, le cumul de BATAILLE) et le
        # remet a zero au turn-start (`operations/minimal_health.reset_times_attacked`, mirror de
        # `...$$ResetAttacksReceivedThisTurn`). Sans seed, un etat charge APRES une attaque rendait
        # 0 la ou le natif rend `>= 1` -- degradation PERMISSIVE-INVERSEE : le gate HP-floor de
        # `MinimalHealth` et le cap `HYPERSENSORY_ATTACK_CAP` de `1213 DeathOnTheWind` ACCEPTAIENT
        # des cibles que le natif REFUSE.
        for key, attr in (("tilesMovedThisBattle", "tiles_moved_this_battle"),
                          ("tilesMovedThisTurn", "tiles_moved_this_turn"),
                          ("tilesMovedLastTurn", "tiles_moved_last_turn"),
                          ("totalTurnsWithAttacksMade", "turns_with_attacks_made"),
                          ("totalAttacksMade", "total_attacks_made"),
                          ("attacksMadeThisTurn", "attacks_made_this_turn"),
                          ("attacksReceivedThisTurn", "times_attacked_this_turn")):
            v = su.get(key)
            if v is None or int(v) < 0:
                continue
            setattr(uc, attr, int(v))
        # #1082 (ferme `#462-r4b-r1-r1-r1-r1-c-r3-r1-r5-r1`) -- LES DEUX POSITIONS PRECEDENTES,
        # publiees par le MEME RPC, sur le MEME appel, depuis #347-r1 : `readMovementPositions` rend
        # `movement.previousPosition` (`<+0x88>`) et `movement.previousPositionThisTurn` (`<+0x98>`).
        #
        # ⚠ LA PREMISSE << aucun RPC ne les publie >> ETAIT FAUSSE : le capteur existe, il est garde
        # par `probe_546_capteurs_fenetre_offline.py`, et sa mesure de fenetre (2026-08-08) montre la
        # transition nette `null -> non-null` au premier pas. Ce qui manquait etait le CONSOMMATEUR.
        # Sans lui, un `load_state` pris APRES un deplacement repartait `previous` VIDE, donc
        # `AmountIsGreaterThanZero(PreviousTile)` faux, et `HaywireMineAbility` basculait sur sa
        # branche ADJACENTE au lieu de poser sur la tuile QUITTEE.
        #
        # TRI-ETAT, et il est PAR CHAMP : le capteur publie `decode` pour chacun. `null` = mesure
        # faite, `Nullable` VIDE ; `decode != "ok"` = mesure NON FAITE (offsets non derives, lecture
        # en erreur, `ToTileList` irresolu). On n'ecrit QUE sur `decode == "ok"` -- ecraser sur une
        # mesure absente EFFACERAIT une position que la simulation vient de graver.
        mv = su.get("movement")
        if isinstance(mv, Mapping):
            tuiles = _tiles_of(mv.get("previousPositionThisTurn"))     # `<+0x98>`
            if tuiles is not None:
                uc.previous_position_this_turn = tuiles or None
            tuiles = _tiles_of(mv.get("previousPosition"))             # `<+0x88>`
            if tuiles is not None:
                pc = ent.get_component(PositionComponent)
                if pc is not None:
                    pc.previous = tuiles or None
        _seed_received_damage_types(uc, su.get("receiveDamageTypeThisTurn"))


def _seed_received_damage_types(uc, champ) -> None:
    """Seede `UnitComponent.received_damage_this_turn` depuis `actorStats` (#487-r2).

    MIRROR : le `Dictionary<DamageProfileType, int>` de
    `IdunBattle.Entities.Components.ActorStatisticsComponent @+0x80` -- ECRIT par
    `...$$RegisterReceivedDamage` (`TryAdd(profil, 1)` sinon `+1`), VIDE par
    `...$$ResetReceivedDamageThisTurn` (`Clear()`), c'est-a-dire un COMPTE D'INSTANCES PAR PROFIL,
    jamais une somme de degats.

    POURQUOI. Le lecteur porte existe depuis #202 (`engine/dsl/base.py`, le selecteur
    `UnitsThatTakenDamageThisTurn` = `ContainsKey(profil)`), et #487-r1 en a fait le substrat de
    la face DECISION de `1088 HellfyreMissileRack`
    (`engine/playbook/scene.py::received_damage_profiles_by_id`). Mais AUCUN canal ne le seedait :
    sur un etat RECHARGE, le rejeu offline voyait `{}` alors que le runner, lui, tient le vrai
    compteur -- et le playbook s'abstenait en le DISANT (`None` = non mesure), ce qui est correct
    mais rend la face live INCONFRONTABLE.

    TRI-ETAT, comme les sept compteurs voisins et pour la meme raison, mais l'enjeu y est PLUS
    GLISSANT : ici `{}` (mesure : rien recu ce tour) est l'etat MAJORITAIRE. Les confondre avec
    `null` (pas mesure) ferait ecrire un dictionnaire VIDE la ou le capteur n'a rien lu, donc
    ETEINDRE un gate au lieu de s'abstenir. On n'ecrit donc QUE si `profiles` est un Mapping ;
    `null` laisse le champ tel quel.

    ⚠ Les cles arrivent en CHAINES (JSON n'a pas de cle entiere) et les ordinaux de
    `IdunBattle.Entities.Enum.DamageProfileType` ne sont NI contigus NI tous positifs
    (`None = -1`, puis 0,1,3,4,...,25 -- lus dans `data/symbols/<build>/frida/enums.tsv`). On
    convertit donc par `int()` sans jamais supposer une plage, et une cle non convertible est
    SAUTEE plutot que d'empoisonner le dict d'un lecteur qui l'indexe par entier."""
    if not isinstance(champ, Mapping):
        return
    profils = champ.get("profiles")
    if not isinstance(profils, Mapping):
        return                                   # `null` = PAS MESURE -> on ne touche a rien
    recu = {}
    for cle, valeur in profils.items():
        try:
            k, v = int(cle), int(valeur)
        except (TypeError, ValueError):
            continue                             # cle/valeur illisible : sautee, jamais devinee
        if v < 0:
            continue                             # compteur a increments `>= 1` : `< 0` = lecture invalide
        recu[k] = v
    uc.received_damage_this_turn = recu


def _tiles_of(champ):
    """Normalise un champ de position du capteur en liste de `(col, row)`, ou `None` si la mesure
    N'A PAS ETE FAITE. Les deux sont distincts et le distinguo est tout l'objet de cette fonction.

    Le hook publie chaque position sous l'une de DEUX formes (`rpc-snapshot.ts::readMovement
    Positions`) : `null` = `hasValue == 0`, donc MESURE et VIDE -> on rend `[]` ; sinon un objet
    `{ raw, tiles, decode }` ou seul `decode == "ok"` atteste que `IdunBattle.Core.UnitPositionId
    Extensions$$ToTileList` a bien ete INVOQUE (le natif fait exactement cet appel pour
    materialiser une position). Les quatre autres `decode` (`layout-not-derived`,
    `hasValue-unreadable`, `no-ToTileList`, `threw`) sont des PANNES DE CAPTEUR -> `None`.

    Une `UnitPositionId` porte l'EMPREINTE entiere, d'ou une LISTE et non un couple : une unite
    multi-hex en occupe plusieurs. Jamais de couple invente."""
    if champ is None:
        return []                                     # `hasValue == 0` : mesure faite, position vide
    if not isinstance(champ, Mapping) or champ.get("decode") != "ok":
        return None                                   # panne de capteur : NON MESURE
    out = []
    for t in (champ.get("tiles") or ()):
        if isinstance(t, Mapping) and t.get("col") is not None and t.get("row") is not None:
            out.append((int(t["col"]), int(t["row"])))
    return out


# ═══ CANAL AMBIANT du seed TERTIAIRE (#363) ═══════════════════════════════════════════════════════
#
# POURQUOI CE CANAL EST LE SEUL DES QUATRE A NE PAS ETRE OPT-IN.
# `tiles=` (#102) et `actor_stats=` (#340-r1) decrivent un ETAT QUI BOUGE (effets de tuile poses en
# cours de bataille, compteur de tuiles parcourues remis a zero chaque tour) : les fournir change ce
# que le port CALCULE, donc les activer partout serait un changement de comportement a evaluer
# scenario par scenario. L'ability TERTIAIRE, elle, est FIGEE AU MONTAGE DE L'UNITE
# (`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`, appele par
# `UnitFactory$$Build`) : c'est une donnee d'IDENTITE, du meme ordre que le visualId ou les traits.
# Ne pas la poser n'est donc pas « un canal en moins », c'est une unite DECRITE FAUX -- et le defaut
# le plus fidele est de la poser.
#
# LE COUT, MESURE AVANT DE BRANCHER (`probe_363_ability_states_cost.py`, build `rnca9r7q6c`,
# board MC1_67, seed 777, medianes sur 12-15 appels, 1er appel exclu) :
#
#   roster   unites   dv+ob+snap+bg (la capture DEJA faite)   unitAbilityStates   part ajoutee
#   2v2         4                              312.2 ms             33.4 ms           +10.7 %
#   5v5        10                             1347.3 ms             33.4 ms            +2.5 %
#
# Le RPC est le MOINS cher des cinq (33 ms contre 178 a 1175 ms pour `decisionView`) et, surtout, il
# NE SCALE PAS avec l'effectif la ou `decisionView` explose -- donc sa part RECULE quand la bataille
# grossit. Le seed Python lui-meme est dans le bruit (< 0.3 ms). Cout sur un batch : NUL --
# `rl_collect_batch` et `engine_validate` n'appellent JAMAIS `load_state` (verifie : les seules
# occurrences dans `engine/` sont des commentaires ; la face DECISION lit son kit declenche par
# `engine/ai/context.py::live_triggered_ability_ids`, deja sur ce meme RPC).
#
# LE CACHE N'EST PAS UNE OPTIMISATION, C'EST UNE CONDITION DE DETERMINISME. Un probe rejoue
# couramment la MEME capture plusieurs fois (`probe_357` la rejoue trois fois pour contraster ses
# bras). Si le canal repartait au live a chaque `load_state`, deux rejeux de la meme capture
# pourraient lire deux etats differents -- le rejeu offline cesserait d'etre reproductible. On
# capture donc UNE FOIS PAR RUNNER. C'est fidele : l'entree tertiaire ne bouge pas en cours de
# bataille (aucune Operation ne la reecrit ; les seules unites qui APPARAISSENT ensuite sont des
# summons, qui n'ont pas d'etat JOUEUR donc pas de relique equipee).
_LIVE_RPC = None
_ABILITY_STATES_CACHE: dict = {}     # {label runner: payload `unitAbilityStates`} -- 1 RPC/bataille


def bind_live_rpc(rpc):
    """Lie le transport RPC AMBIANT dont `load_state` se sert pour les canaux qu'elle sait tirer
    elle-meme (aujourd'hui : `unitAbilityStates`). Rend le transport PRECEDENT, pour restauration.

    `rpc` a la signature du dépôt : `rpc(method, body=None, timeout=…)` -> resultat DEBALLE (sans
    l'enveloppe `{result: …}`) -- exactement la fixture `rpc` de `tests/conftest.py` et le `rpc`
    local que chaque probe se fabrique.

    POURQUOI UN AMBIANT ET PAS UN ARGUMENT DE PLUS. `load_state` recoit des PAYLOADS, jamais un
    transport : elle ne peut pas aller chercher ce qui lui manque. Faire remonter le besoin jusqu'aux
    appelants voudrait dire editer les ~620 call-sites (379 fichiers) -- et surtout, chaque nouveau
    montage devrait y REPENSER, ce qui est exactement la dette que #357-r1 constate. Un transport lie
    UNE FOIS par harnais (la fixture `rpc` couvre toute la suite de tests) rend le canal disponible
    partout sans toucher un seul call-site."""
    global _LIVE_RPC
    prev, _LIVE_RPC = _LIVE_RPC, rpc
    return prev


def unbind_live_rpc():
    """Delie le transport ambiant (et rend le precedent). Le cache SURVIT : il indexe des payloads
    de runners, pas le transport."""
    global _LIVE_RPC
    prev, _LIVE_RPC = _LIVE_RPC, None
    return prev


@contextmanager
def live_rpc(rpc):
    """`with live_rpc(rpc): …` -- lie le transport pour la duree du bloc, restaure ensuite."""
    prev = bind_live_rpc(rpc)
    try:
        yield rpc
    finally:
        bind_live_rpc(prev)


def clear_ability_states_cache(label: Optional[str] = None) -> None:
    """Purge le cache par runner. Sans argument : tout. A appeler quand un runner est DISPOSE et que
    son id peut etre recycle par un build ulterieur (les tests le font au teardown)."""
    if label is None:
        _ABILITY_STATES_CACHE.clear()
    else:
        _ABILITY_STATES_CACHE.pop(label, None)


def runner_label(*payloads) -> Optional[str]:
    """Le label de runner que TOUT payload de capture porte (`decisionView`/`observeBattle`/
    `combatSnapshot`/`boardGraph` rendent `runner: label`) : `"build#<id>"` pour un runner isole,
    `"live"` pour la bataille du jeu. `None` si aucun payload n'en porte -- capture fabriquee a la
    main, ou payload tronque : dans ce cas le canal AUTO ne se declenche pas."""
    for p in payloads:
        if isinstance(p, dict):
            lab = p.get("runner")
            if isinstance(lab, str) and lab:
                return lab
    return None


def _runner_body(label: str) -> dict:
    """Corps RPC vise par un label. `"build#37"` -> `{"runnerId": 37}` ; `"live"` -> `{}`, que le
    capteur resout sur `state.liveRunner` (`rpc-snapshot.ts` : `typeof body?.runnerId === "number"`
    sinon repli live)."""
    if label.startswith("build#"):
        try:
            return {"runnerId": int(label[len("build#"):])}
        except ValueError:
            return {}
    return {}


def capture_ability_states(rpc, label: str, use_cache: bool = True) -> dict:
    """Payload `unitAbilityStates` du runner `label`, capture UNE FOIS puis servi du cache.

    Rend `{"units": [...]}` ou `{"error": …}` -- le capteur RENVOIE ses echecs, il ne les tait pas.
    Une reponse en erreur n'est PAS mise en cache (un runner momentanement indisponible ne doit pas
    figer un trou pour toute la session)."""
    if use_cache and label in _ABILITY_STATES_CACHE:
        return _ABILITY_STATES_CACHE[label]
    res = rpc("unitAbilityStates", _runner_body(label), 60)
    if isinstance(res, dict) and "result" in res:          # transport non deballe -> on deballe
        res = res["result"]
    if not isinstance(res, dict):
        return {"error": "reponse non-dict : %r" % (type(res).__name__,)}
    if res.get("units") is None:
        return {"error": res.get("error") or "payload sans `units`"}
    if use_cache:
        _ABILITY_STATES_CACHE[label] = res
    return res


def _auto_ability_states(ability_states, decision, observe, snapshot) -> tuple:
    """Resout le TRI-ETAT de `load_state(ability_states=…)`. Rend `(payload|None, source)`.

    `source` est TRACE dans `State.ability_states_seed` -- c'est la discipline tri-etat du depot
    (`host_inputs.py`) : on distingue « pas mesure » de « mesure et vide », pour qu'un canal muet ne
    se lise jamais comme une mesure.

      `given`             l'appelant a fourni le payload ;
      `auto`              le canal s'est servi (transport lie + label lisible + snapshot present) ;
      `refused`           `ability_states=False` -- contre-epreuve explicite ;
      `no-snapshot`       pas de `combatSnapshot` -> aucun `StatsComponent.ctx` ou ecrire : le seed
                          serait un no-op, on ne paie pas le RPC ;
      `no-transport`      aucun `bind_live_rpc` -> etat reconstruit hors harnais live (comportement
                          strictement d'avant #363) ;
      `no-runner-label`   payloads sans `runner` (capture fabriquee a la main) ;
      `unavailable:<msg>` transport lie mais le capteur a RENDU une erreur. On ne LEVE pas -- un
                          runner dispose entre la capture et le rejeu est un cas legitime -- mais on
                          l'ECRIT, pour qu'un zero se lise comme une panne et non comme « aucune
                          relique »."""
    if ability_states is False:
        return (None, "refused")
    if ability_states is not None:
        return (ability_states, "given")
    if snapshot is None:
        return (None, "no-snapshot")
    if _LIVE_RPC is None:
        return (None, "no-transport")
    label = runner_label(decision, observe, snapshot)
    if label is None:
        return (None, "no-runner-label")
    res = capture_ability_states(_LIVE_RPC, label)
    if res.get("error"):
        return (None, "unavailable:%s" % (res["error"],))
    return (res, "auto")


class GraftedStateWithoutChannel(RuntimeError):
    """Un montage a GREFFE, et le canal `unitAbilityStates` est muet -- le port serait AMPUTE."""


#: Regimes de `_auto_ability_states` ou le canal est muet PAR ACCIDENT (le montage voulait la
#: mesure et ne l'a pas eue). `refused` en est ABSENT : c'est le refus EXPLICITE, la contre-epreuve
#: assumee. `no-snapshot` aussi : sans `combatSnapshot` il n'y a AUCUN `StatsComponent`, donc
#: `collect_triggered_abilities` ne derive rien du gameconfig non plus -- pas de degradation
#: permissive a fermer, le seed serait un no-op.
_MUTE_BY_ACCIDENT = ("no-transport", "no-runner-label", "unavailable:")


def _fichier_runner(label: Optional[str], dossier: str) -> Optional["object"]:
    """Chemin d'un sidecar PAR RUNNER, ou `None` si le label est absent.

    `engine/` LIT ces fichiers, il n'en ecrit aucun : ils sont publies par le montage
    (`rl_duel build`). C'est la seule voie par laquelle un fait connu du BUILD atteint
    `load_state`, qui ne recoit ni la BC ni le state-file."""
    if not label:
        return None
    from pathlib import Path
    racine = Path(__file__).resolve().parents[4]     # scripts/python/engine/runner/ -> checkout
    return (racine / "logs" / "runners" / dossier
            / (str(label).replace("#", "-").replace("/", "_") + ".json"))


def _section_bc_du_runner(label: Optional[str], section: str):
    """La section de `BattleConfiguration` publiee pour ce runner, ou `None` (#449-r2-r4-r1).

    TRI-ETAT STRICT, et c'est tout l'interet : `None` = « pas mesure » -> l'appelant retombe sur
    le defaut derive de la seed versionnee, comme avant. Un dict VIDE resterait un dict -- la BC a
    parle et elle dit zero, ce que `DamageConfiguration.from_bc` distingue deja explicitement.
    On ne fabrique donc jamais de section, et une lecture impossible se comporte exactement comme
    l'absence de canal."""
    p = _fichier_runner(label, "bc-sections")
    if p is None:
        return None
    import json
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    val = data.get(section)
    return val if isinstance(val, dict) else None


def _grafts_du_runner(label: Optional[str]) -> list:
    """Les greffes publiees sur DISQUE pour ce label de runner (#448-r3-r1-r1-r1).

    SECONDE SOURCE du refus, et elle couvre le regime que la premiere ne peut pas voir : un seed BC
    greffe par un AUTRE PROCESSUS puis passe par `--seed-bc`. Le registre de `catalog_inject` est un
    fait de PROCESSUS -- cote consommateur il est VIDE, donc muet, alors que c'est exactement le
    regime ou le port serait ampute. Le RUNNER est le seul identifiant que les deux cotes
    partagent, et `load_state` le connait toujours (`runner_label`) alors qu'elle ne recoit ni la
    BC ni le state-file.

    Gisement mesure : **15** fichiers de `scripts/python/**` exposent `--seed-bc` en option CLI,
    dont **13** ne portent aucune primitive de greffe.

    ⚠ On relit un FICHIER, on n'importe PAS `catalog_inject` : `engine/` ne gagne aucune dependance
    vers un module de montage (meme raison que la lecture par `sys.modules` ci-dessous). Toute
    lecture impossible rend `[]` -- ce garde-fou ne doit jamais faire echouer un chargement par
    lui-meme, et un registre absent signifie exactement « ce runner n'a rien publie »."""
    if not label:
        return []
    # Imports LOCAUX, comme le `sys` de `_declared_grafts` : ce module ne porte au niveau global
    # que ses dependances de moteur, et ce garde-fou est le seul consommateur de ces deux-la.
    import json
    from pathlib import Path
    racine = Path(__file__).resolve().parents[4]     # scripts/python/engine/runner/ -> checkout
    p = (racine / "logs" / "runners" / "grafts"
         / (str(label).replace("#", "-").replace("/", "_") + ".json"))
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [g for g in items if isinstance(g, dict)] if isinstance(items, list) else []


def _declared_grafts(label: Optional[str] = None) -> list:
    """Les greffes connues pour cet etat : celles de CE processus, PLUS celles publiees par le
    processus qui a construit le runner (`catalog_inject.declare_graft`, #448-r3-r1-r1 puis -r1).

    ⚠ On lit `sys.modules`, on n'IMPORTE PAS `catalog_inject` : si le module n'a jamais ete
    importe, aucune greffe n'a pu etre faite -- le test est donc exact, et `engine/` ne gagne
    aucune dependance vers un module de montage.

    Les deux sources sont FUSIONNEES sans doublon : le greffeur qui charge lui-meme son etat est
    present des DEUX cotes, et le compter deux fois gonflerait le message du refus sans rien
    apporter."""
    import sys
    mod = sys.modules.get("catalog_inject")
    fn = getattr(mod, "declared_grafts", None) if mod is not None else None
    try:
        out = list(fn()) if callable(fn) else []
    except Exception:
        out = []
    vus = {(g.get("kind"), g.get("unitId"), g.get("what")) for g in out if isinstance(g, dict)}
    for g in _grafts_du_runner(label):
        cle = (g.get("kind"), g.get("unitId"), g.get("what"))
        if cle not in vus:
            vus.add(cle)
            out.append(g)
    return out


def _grafts_concerning(decision: dict, grafts: list) -> tuple:
    """Les greffes du processus qui concernent CET etat-ci. Rend `(concernees, indecidable)`.

    ⚠ POURQUOI LE REFUS NE PEUT PAS ETRE GLOBAL AU PROCESSUS -- mesure du 2026-08-05. Le registre
    de `catalog_inject` est un etat de PROCESSUS : une passe pytest sur un fichier greffeur le
    laisse plein (**3 entrees** apres `test_366_r1_stormboyz_strike_live.py`), et TOUT `load_state`
    ulterieur a canal muet levait -- y compris sur un etat qui n'a rien a voir avec la greffe. Ce
    n'est pas theorique : c'est exactement ce qui a fait rougir deux tests de cette tranche meme,
    et le regime coupable n'etait meme pas `no-transport` mais `unavailable:` (le transport ETAIT
    lie, le runner visé n'existait plus).

    Le critere exact serait « une unite de cet etat porte une greffe invisible du gameconfig » --
    circulaire, puisqu'il faudrait le canal pour le savoir. Le critere RETENU est le porteur :
    l'`unitId` de la greffe apparait-il parmi les `visualId` de l'etat ? Le suffixe d'instance
    (`orksNob:2`) est retire des deux cotes.

    TRI-ETAT, et le troisieme etat est CONSERVATEUR. Une unite SANS TUILE arrive dans
    `decisionView` avec `visualId = null` (mesure #366-r1, citee par `probe_366_r1.carrier_id`) :
    on ne peut alors NI confirmer NI exclure qu'elle porte la greffe -- on leve, en le disant."""
    vis = set()
    indecidable = False
    for u in (decision.get("units") or []):
        v = u.get("visualId")
        if v is None:
            indecidable = True
        else:
            vis.add(str(v).split(":")[0])
    concernees = [g for g in grafts if str(g.get("unitId", "")).split(":")[0] in vis]
    return (concernees, indecidable and bool(grafts))


def _refuse_if_grafted(source: str, snapshot, decision: dict) -> None:
    """LEVE si une greffe de ce processus concerne CET etat et que le canal est muet par accident.

    POURQUOI UN REFUS ET PAS UN AVERTISSEMENT. La degradation que ceci ferme ne RATE pas, elle
    MENT : sans canal, `collect_triggered_abilities` retombe sur `gameconfig.unit(<greffon>)`,
    aucune classe greffee n'est montee, et toute assertion NEGATIVE du montage (« l'effet n'est
    plus la ») passe A VIDE, EN VERT. Mesure (#448-r3-r1) : le meme probe rendait 0 echec en CLI
    et 3 sous pytest, le seul ecart etant le transport ambiant.

    PORTEE -- cf. `_grafts_concerning` : le refus vise l'ETAT, pas le PROCESSUS. Un registre
    global fait lever des `load_state` legitimes qui n'ont aucun rapport avec la greffe, et c'est
    MESURE, pas redoute.

    TROIS SORTIES, toutes explicites -- aucune ne consiste a se taire :
      * lier le transport ambiant (`snapshot.bind_live_rpc(rpc)`), ce que fait `tests/conftest.py` ;
      * passer le payload (`load_state(..., ability_states=rpc("unitAbilityStates", …))`) ;
      * `ability_states=False` -- le refus EXPLICITE, quand l'etat charge n'a DELIBEREMENT pas de
        greffe (contre-bras de controle) ; ou `catalog_inject.clear_declared_grafts()`."""
    if snapshot is None:
        return
    if not any(source.startswith(p) for p in _MUTE_BY_ACCIDENT):
        return
    # Le label est ce qui ouvre la SECONDE source (#448-r3-r1-r1-r1) : les greffes publiees par le
    # processus qui a construit CE runner, que le registre de processus ne peut pas voir.
    grafts = _declared_grafts(runner_label(decision, snapshot))
    if not grafts:
        return
    concernees, indecidable = _grafts_concerning(decision, grafts)
    if not concernees and not indecidable:
        return
    montrees = concernees or grafts
    apercu = ", ".join("%s %s <- %s" % (g["kind"], g["unitId"], g["what"]) for g in montrees[:4])
    # NOMMER L'ORIGINE. Depuis #448-r3-r1-r1-r1 une greffe peut venir du PROCESSUS courant ou du
    # registre publie par celui qui a CONSTRUIT le runner. Dire « declarees par ce processus »
    # dans le second cas envoie le lecteur chercher dans le mauvais fichier -- et c'est justement
    # le regime ou le greffeur est ailleurs, donc le plus dur a retrouver.
    du_disque = _grafts_du_runner(runner_label(decision, snapshot))
    cles_disque = {(g.get("kind"), g.get("unitId"), g.get("what")) for g in du_disque}
    cles_vues = {(g.get("kind"), g.get("unitId"), g.get("what")) for g in montrees}
    if cles_vues and cles_vues <= cles_disque:
        origine = "par le processus qui a CONSTRUIT ce runner (registre publie sur disque)"
    elif cles_vues & cles_disque:
        origine = "par ce processus ET par celui qui a construit ce runner"
    else:
        origine = "par ce processus"
    raise GraftedStateWithoutChannel(
        "load_state : %s (%s%s) et le canal `unitAbilityStates` est MUET (source=%r). Le port "
        "serait AMPUTE -- les classes greffees ne seraient pas montees et les assertions negatives "
        "passeraient a vide, en vert (#448-r3-r1-r1). "
        "Sorties : `snapshot.bind_live_rpc(rpc)` ; ou `load_state(..., ability_states=<payload>)` ; "
        "ou `ability_states=False` / `catalog_inject.clear_declared_grafts()` si l'etat charge n'a "
        "deliberement pas de greffe."
        % ("cet etat porte %d greffe(s) declaree(s) %s" % (len(concernees), origine)
           if concernees else
           "cet etat porte une unite SANS `visualId` (hors plateau) et %d greffe(s) sont "
           "declaree(s) %s -- indecidable, on refuse plutot que de mesurer un port peut-etre "
           "ampute" % (len(grafts), origine),
           apercu, " ..." if len(montrees) > 4 else "", source))


TERTIARY_HIERARCHY = 3
"""`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` monte l'ability TERTIAIRE par
`IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, tertiaryState, 3)` : le `3` est
la hierarchie `Tertiary`. Les passives du kit entrent avec `2`, les derivees de trait avec d'autres
valeurs -- c'est donc LE discriminant « cette entree est une RELIQUE EQUIPEE » dans le composant."""


def _load_tertiary_abilities(state: State, ability_states: dict) -> int:
    """Seede `UnitContext.tertiary_ability{,_level,_variables_multiplier}` depuis le RPC
    `unitAbilityStates` (#357). Rend le nombre d'unites seedees.

    MIRROR -- ce qu'on lit est le RESULTAT de la branche TERTIAIRE d'
    `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` :

        si `config+0xb0` (`Nullable<TriggeredAbilityType> TertiaryAbility`) a une valeur
          -> `TriggeredAbilityComponent$$TryAdd(id, tertiaryAbilityState, 3)`

    ou `tertiaryAbilityState` est l'`AbilityState` que `UnitFactory$$Build` a fabrique depuis
    `config+0xc0` (`TertiaryAbilityLevel`) et `config+0x78`
    (`TertiaryAbilityVariablesMultiplierPercentage`) -- PAS `+0x74`, qui sert a l'actif et au passif.
    Le capteur (`rpc-snapshot.ts`, `unitAbilityStates`) dumpe le `TriggeredAbilityComponent+0x18`
    instance par instance : `raw` = 12 x int32 depuis `+0x10`, donc `raw[0]` = `AbilityName`,
    `raw[10]` = hierarchie ; `level`/`mult` sont exposes separement depuis `+0x20`/`+0x24`.

    POURQUOI CE CANAL, ET PAS `combatSnapshot.unitConfig`. Le capteur `unitConfig` publie bien
    `tertiaryAbilityVariablesMultiplier` (+0x78) mais NI `TertiaryAbility` (+0xb0) NI
    `TertiaryAbilityLevel` (+0xc0) -- les ajouter demanderait une reinjection. `unitAbilityStates`,
    lui, porte deja les TROIS informations, et il les porte a l'endroit ou le natif les a REELLEMENT
    posees (l'`AbilityState` monte), pas a l'endroit ou elles sont declarees. C'est donc a la fois le
    canal disponible et le plus fidele. Le `tertiaryAbilityVariablesMultiplier` de `unitConfig` reste
    son JUMEAU cote config -- `probe_357_relic_rail.py` mesure les deux et verifie qu'ils coincident.

    POURQUOI. Pendant EXACT de `_load_unit_flags` / `_load_unit_turn_state` / `_load_actor_statistics`
    : une ENTREE que RIEN ne peuplait. Le rail COMBAT
    (`triggers/dispatch/core.py::collect_triggered_abilities`) derivait le kit declenche du
    gameconfig, qui ignore par construction l'item relique EQUIPE -- etat JOUEUR, pas donnee de kit.
    Une relique montee en bataille (#237) etait donc INERTE cote port, SANS erreur ni trace : le
    trigger n'etait simplement jamais inscrit.

    TRI-ETAT, meme discipline que les seeds voisins : `ability_states=None` (canal non fourni) ne
    pose RIEN et le comportement est STRICTEMENT celui d'avant ; une unite sans entree de hierarchie
    3 garde `tertiary_ability = None` (= le `Nullable` natif sans valeur, cas des 171 unites du seed
    BC qui n'equipent aucune relique).

    ⚠ GARDE `level < 1` -- invariant NATIF, pas de la defense de principe : `Idun.Shared.Level$$
    ToZeroBasedIndex` LEVE `InvalidOperationException` sur `<= 0`, et `0` signifie « verrouille /
    non debloque » (`Idun.Shared.Level$$CreateValidOrLockedLevel` le laisse passer explicitement).
    Une entree de hierarchie 3 a niveau 0 ne peut donc PAS venir d'une bataille jouable -- elle
    denonce un montage incomplet (relique posee sans son niveau, cf. `docs/rl/case-237-relique-
    forcee.md` §4). On refuse de l'ingerer plutot que d'indexer `arr[-1]` cote port la ou le natif
    faute."""
    seeded = 0
    for su in ((ability_states or {}).get("units") or []):
        uid = su.get("entityId")
        if uid is None:
            continue
        ent = state.get_entity(uid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        if sc is None or getattr(sc, "ctx", None) is None:
            continue
        for t in (su.get("triggered") or []):
            raw = t.get("raw") or []
            if len(raw) <= 10 or raw[10] != TERTIARY_HIERARCHY:
                continue
            aid, lvl = raw[0], t.get("level")
            if lvl is None or int(lvl) < 1:
                continue
            try:
                name = TriggeredAbilityType(int(aid)).name
            except ValueError:
                continue                      # id hors enum du build -> non ingerable, non devinable
            sc.ctx.tertiary_ability = name
            sc.ctx.tertiary_ability_level = int(lvl)
            # `mult` = `AbilityState.VariableMultiplierPercentage` (`+0x24`), lu SANS garde de
            # valeur : contrairement au niveau, aucun invariant natif n'en exclut de plage, et un
            # `0` publie serait un vrai zero. Absent (`None`) = champ non expose -> on garde le
            # defaut neutre 100. Si `level` est lisible, `+0x24` l'est aussi (meme instance) : un
            # walk partiel aurait deja fait sortir la boucle sur `len(raw) <= 10`.
            mult = t.get("mult")
            if mult is not None:
                sc.ctx.tertiary_ability_variables_multiplier = int(mult)
            seeded += 1
            break                             # `TertiaryAbility` est un Nullable SIMPLE : une au plus
    return seeded


PASSIVE_HIERARCHY = 2
"""Hierarchie `Passive` du `TriggeredAbilityComponent`. LUE dans
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`, qui enumere
`config+0xa8` (= `UnitConfiguration.PassiveAbilities`) et appelle
`IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, passiveAbilityState, 2)`.
La branche TERTIAIRE (relique) juste apres passe `3` ; les ACTIVES ne passent pas par la du tout
(`UnitFactory$$AddActiveAbility`). C'est donc LE discriminant « cette entree est un passif de
configuration »."""


def passive_ability_names_by_unit(ability_states: dict) -> dict:
    """`{entityId: [noms de TriggeredAbilityType de HIERARCHIE 2]}` depuis le payload du RPC
    `unitAbilityStates`.

    FOYER UNIQUE du parsing. `_load_passive_abilities` (face COMBAT) et
    `engine.playbook.scene._seed_measured_passives` (face DECISION) l'appellent toutes les deux :
    le dispatch d'attaque normale (`engine.services.custom_normal_attack`) consomme ce champ des
    DEUX cotes, et deux parsings distincts feraient exactement le fork « ce que la prediction
    annonce != ce que le moteur fait » que le port proscrit.

    Une unite PRESENTE dans le payload mais sans aucune entree de hierarchie 2 recoit `[]` -- une
    MESURE (unite sans passif), a distinguer d'un canal muet, qui lui n'a aucune cle."""
    out: dict = {}
    for su in ((ability_states or {}).get("units") or []):
        uid = su.get("entityId")
        if uid is None:
            continue
        names: list[str] = []
        for t in (su.get("triggered") or []):
            raw = t.get("raw") or []
            if len(raw) <= 10 or raw[10] != PASSIVE_HIERARCHY:
                continue
            try:
                name = TriggeredAbilityType(int(raw[0])).name
            except ValueError:
                continue                      # id hors enum du build -> non ingerable, non devinable
            if name not in names:             # `TryAdd` sur une KeyedCollection : une entree par id
                names.append(name)
        out[uid] = names
    return out


def active_ability_names_by_unit(ability_states: dict) -> dict:
    """`{entityId: [noms d'ActiveAbilityType montes]}` depuis le payload du RPC `unitAbilityStates`.

    FOYER UNIQUE du parsing, exactement comme `passive_ability_names_by_unit` sur l'autre voie :
    `_load_active_abilities` (face COMBAT) et `engine.playbook.scene._seed_measured_actives` (face
    DECISION) l'appellent toutes les deux, pour que le dispatch d'attaque normale
    (`engine.services.custom_normal_attack`) lise LA MEME liste des deux cotes.

    ⚠ SUR-ENSEMBLE ASSUME. Le natif dispatche sur `UnitConfiguration.ActiveAbilities`
    (`config@+0xa0`) ; ce qu'on lit est l'`ActiveAbilityComponent`, qui porte EN PLUS l'attaque
    normale que la fabrique vient d'y ecrire et les abilities de `UnitFactory$$AddDerivedAbilities`.
    C'est le seul canal disponible sans capteur neuf, et il est SUR pour la table portee : cf. le
    controle mesure documente sur `UnitContext.active_abilities`.

    L'ORDRE est celui du composant, et il compte (la boucle native rend au PREMIER actif gagnant).
    Une unite PRESENTE dans le payload mais sans aucune active recoit `[]` -- une MESURE, a
    distinguer d'un canal muet, qui lui n'a aucune cle."""
    out: dict = {}
    for su in ((ability_states or {}).get("units") or []):
        uid = su.get("entityId")
        if uid is None:
            continue
        names: list[str] = []
        for a in (su.get("actives") or []):
            raw = a.get("type")
            if raw is None:
                continue
            try:
                name = ActiveAbilityType(int(raw)).name
            except ValueError:
                continue                      # id hors enum du build -> non ingerable, non devinable
            if name not in names:
                names.append(name)
        out[uid] = names
    return out


def config_active_ability_names_by_unit(ability_states: dict) -> dict:
    """`{entityId: [noms d'ActiveAbilityType de la CONFIGURATION] | None}` depuis le payload du RPC
    `unitAbilityStates` (capteur #466, champ `configActives`).

    FOYER UNIQUE du parsing, comme ses trois voisins : `_load_config_active_abilities` (face
    COMBAT) et `engine.playbook.scene._seed_measured_config_actives` (face DECISION) l'appellent
    toutes les deux.

    ⚠ CE N'EST PAS `active_ability_names_by_unit`, et c'est tout l'interet. Celui-la lit
    l'`ActiveAbilityComponent` (etat APRES la fabrique, donc un SUR-ENSEMBLE qui porte deja
    l'attaque normale) ; celui-ci lit `UnitConfiguration.ActiveAbilities` (`config@+0xa0`), l'etat
    AVANT -- exactement ce que teste la garde `FilterNewList` de
    `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`.

    MESURE (2026-08-04, `rnca9r7q6c`, 6 unites) : POST = PRE + l'attaque normale que la fabrique
    vient d'ecrire, 6/6, rien de manquant -- et sur une MACHINE (`ultraDreadnought`) PRE == POST
    exactement, parce que `MachineFactory$$Build` n'appelle jamais `AddNormalAttackAbility`.

    TRI-ETAT STRICT, et il porte du sens : la VALEUR `None` (distincte d'une cle absente) signifie
    « le capteur a regarde et n'a pas pu joindre » -- pas « la configuration est vide ». Une cle
    ABSENTE signifie « canal muet » (capteur anterieur a #466, ou unite hors payload)."""
    out: dict = {}
    for su in ((ability_states or {}).get("units") or []):
        uid = su.get("entityId")
        if uid is None or "configActives" not in su:
            continue                      # cle absente = capteur anterieur -> canal MUET
        raw = su.get("configActives")
        if raw is None:
            out[uid] = None               # mesure : « pas joint » (jamais rabattu sur `[]`)
            continue
        names: list[str] = []
        for c in raw:
            t = c.get("type") if isinstance(c, dict) else c
            if t is None:
                continue
            try:
                name = ActiveAbilityType(int(t)).name
            except ValueError:
                continue                  # id hors enum du build -> non ingerable, non devinable
            if name not in names:
                names.append(name)
        out[uid] = names
    return out


def _load_config_active_abilities(state: State, ability_states: dict) -> int:
    """Seede `UnitContext.config_active_abilities` depuis le RPC `unitAbilityStates`
    (#419-r1-tr14-r5-r2-r2-r1). Rend le nombre d'unites seedees.

    MEME payload et MEME instance que `_load_active_abilities` juste en dessous : seul le champ lu
    change (`configActives` au lieu de `actives`), et c'est la difference PRE/POST fabrique.

    Le PARSING vit dans `config_active_ability_names_by_unit` (foyer partage avec la face
    DECISION)."""
    seeded = 0
    for uid, names in config_active_ability_names_by_unit(ability_states).items():
        ent = state.get_entity(uid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        if sc is None or getattr(sc, "ctx", None) is None:
            continue
        sc.ctx.config_active_abilities = names
        seeded += 1
    return seeded


def _load_active_abilities(state: State, ability_states: dict) -> int:
    """Seede `UnitContext.active_abilities` depuis le RPC `unitAbilityStates`
    (#419-r1-tr14-r5-r2). Rend le nombre d'unites seedees.

    MEME payload, MEME instance et MEME nature que `_load_passive_abilities` : seul le champ lu
    change (`actives` au lieu de `triggered`). C'est la SECONDE voie de la cascade de
    `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, celle que
    `UnitFactory$$GetCustomNormalAttackTypeFromActive` consulte quand la voie passive rend `null`.

    TRI-ETAT, meme discipline que les seeds voisins : sans canal, rien n'est pose et la voie active
    du predicat retombe sur le kit gameconfig, STRICTEMENT comme avant.

    Le PARSING vit dans `active_ability_names_by_unit` (foyer partage avec la face DECISION)."""
    seeded = 0
    for uid, names in active_ability_names_by_unit(ability_states).items():
        ent = state.get_entity(uid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        if sc is None or getattr(sc, "ctx", None) is None:
            continue
        sc.ctx.active_abilities = names
        seeded += 1
    return seeded


def _load_active_ability_levels(state: State, ability_states: dict) -> int:
    """Seede le NIVEAU et le MULTIPLICATEUR des abilities ACTIVES depuis `unitAbilityStates`
    (#890). Rend le nombre d'unites COMBLEES (pas le nombre d'unites visitees).

    DEUX ecritures, et la seconde est un COMBLEMENT au sens strict :

    1. `UnitContext.active_ability_levels` = `{ActiveAbilityType: (level, mult)}` -- l'`AbilityState`
       PAR ABILITY, tel que `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` le
       consomme (le natif resout chaque variable contre l'`AbilityState` de l'ability CASTEE, pas
       contre un niveau global d'unite). Ecriture ADDITIVE : personne n'est oblige de la lire.
    2. `ctx.active_ability_level` / `ctx.ability_variables_multiplier` -- ECRITS **UNIQUEMENT SI LE
       TROU EXISTE** (scalaire absent ou nul). Meme regle que `_load_passive_abilities` : on n'ecrit
       jamais par-dessus une valeur mesuree.

    POURQUOI ce comblement existe -- mesure, pas redoute. `combatSnapshot.units[].unitConfig` rend
    `{"error": "config null"}` pour un BOSS monte par `--explicit-stats` : le scalaire retombe alors
    a `0`, donc `ability_var(..., level=0)` lit l'INDEX 0, c'est-a-dire le NIVEAU 1. Mesure sur
    `tyranBossHiveTyrantLeviathan:4` (`Catalyst`) : `extraArmor` 10 au lieu de 1190, `blockDmg` 15 au
    lieu de 1786 -- deux ordres de grandeur, en silence. Le canal `unitAbilityStates`, lui, porte
    `level = 55` et `mult = 200` pour les QUATRE actives du boss.

    LA REGLE DU COMBLEMENT EST VERIFIABLE, et c'est ce qui la rend non arbitraire : on prend le
    **MAXIMUM** des niveaux d'actives (avec le `mult` de CETTE entree). Sur les unites qui portent
    DEJA leur scalaire, cette regle le REPRODUIT -- `ultraCalgar` porte `1000@50` et `69@1`
    (l'attaque normale a son propre niveau 1) et son `unitConfig.activeAbilityLevel` vaut `50` ;
    `tyranTyrantGuard` porte `1105@50` et `69@1` pour un scalaire `50`. C'est ce que
    `test_890_hive_tyrant_live.py` assertionne : la regle est confrontee la ou la verite est connue,
    puis appliquee la ou elle manque.

    TRI-ETAT, meme discipline que les seeds voisins : sans canal, rien n'est pose."""
    seeded = 0
    for row in ((ability_states or {}).get("units") or []):
        uid = row.get("entityId")
        actives = [a for a in (row.get("actives") or []) if a.get("level") is not None]
        if uid is None or not actives:
            continue
        ent = state.get_entity(uid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        if ctx is None:
            continue
        ctx.active_ability_levels = {int(a["type"]): (int(a["level"]),
                                                      int(a.get("mult") or 100))
                                     for a in actives if a.get("type") is not None}
        if getattr(ctx, "active_ability_level", None):
            continue                       # deja mesure -> on n'ecrit JAMAIS par-dessus
        best = max(actives, key=lambda a: int(a["level"]))
        ctx.active_ability_level = int(best["level"])
        ctx.ability_variables_multiplier = int(best.get("mult") or 100)
        seeded += 1
    return seeded


def _load_passive_abilities(state: State, ability_states: dict) -> int:
    """Seede `UnitContext.passive_abilities` depuis le RPC `unitAbilityStates` (#366-r1).
    Rend le nombre d'unites seedees.

    MIRROR -- ce qu'on lit est le RESULTAT de la PREMIERE boucle d'
    `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` (cf. `PASSIVE_HIERARCHY`).
    Meme capteur, meme instance, meme `raw` que `_load_tertiary_abilities` : seule la valeur de
    `raw[10]` change.

    POURQUOI. `triggers/dispatch/core.py::collect_triggered_abilities` derivait les passiveAbilities
    du **gameconfig par `visualId`**. Or le natif ne lit pas le gameconfig : il monte
    `BattleConfiguration.Units[].PassiveAbilities`. Tant que les deux coincident la reconstruction
    passe inapercue -- mais elle rend INERTE, sans erreur ni trace, tout passif que le BC porte et
    que le kit gameconfig ignore. C'est exactement la faute que #264 a corrigee sur l'axe TRAITS
    (`traits_measured`), ou la reconstruction se trompait DANS LES DEUX SENS.

    Cas qui l'a rendue mesurable : la GREFFE d'un passif sur une unite du pool
    (`catalog_inject.graft_passive_ability`), seul chemin de confrontation d'une ability dont
    l'unique porteur est un **npc** -- `buildNormalizedBC` refusant structurellement tout npc.

    TRI-ETAT, meme discipline que les seeds voisins : sans canal (`ability_states=None` et aucun
    transport lie), rien n'est pose et `collect_triggered_abilities` retombe sur le gameconfig,
    STRICTEMENT comme avant. Une unite PRESENTE dans le payload mais sans aucune entree de
    hierarchie 2 recoit `[]` -- une mesure, pas une absence de mesure : c'est le cas legitime d'une
    unite sans passif, et il doit se distinguer de « canal muet ».

    Le PARSING vit dans `passive_ability_names_by_unit` (foyer partage avec la face DECISION).

    ⚠ IL SEEDE AUSSI L'`AbilityState` DES PASSIFS, ET **SEULEMENT QUAND LE TROU EXISTE**
    (#462-r4b-r1-r1-r1-r1-c-r3-r1-r3). Une unite INVOQUEE n'a **aucune** `UnitConfiguration` cote
    natif (`SpawnUnitOperation` la fabrique par `SpawnUnitOptions$$WithStatsFromConfig`, pas depuis
    un `UnitConfiguration`), donc le capteur `combatSnapshot.unitConfig` rend litteralement
    `{"error": "config null"}` pour elle -- MESURE sur `astarSmnHaywireMine` -- et
    `_load_unit_stats` laisse `passive_ability_level` a son defaut `0` / le multiplicateur a `100`.
    Toute variable per-niveau d'un passif de SUMMON etait alors lue a l'INDEX 0 (= niveau 1) :
    mesure sur `HaywireMineSteppable`, `minDmg[0] = 50` au lieu de `minDmg[49] x 180 % = 4986`,
    soit un facteur ~55 -- exactement le mode de panne de #174 sur les Machines of War.
    Le canal qui, LUI, porte l'information est `unitAbilityStates` : l'`AbilityState` est dumpe
    PAR INSTANCE d'ability montee (`level` @+0x20, `mult` @+0x24), et c'est d'ailleurs celui que
    `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel` consomme reellement --
    le `passive_ability_level` par UNITE du port est un collapse, exact tant que l'unite a une
    config, faux des qu'elle n'en a pas.
    GARDE : on n'ecrit QUE si `passive_ability_level` est absent/0, donc jamais par-dessus une
    valeur mesuree ; sur une unite configuree les deux canaux coincident (verifie : `necroWarden`
    -> `unitConfig.passiveAbilityLevel = 50` / `mult = 180` et l'`AbilityState` de hierarchie 2
    porte `level = 50` / `mult = 180`)."""
    seeded = 0
    states = passive_ability_state_by_unit(ability_states)
    for uid, names in passive_ability_names_by_unit(ability_states).items():
        ent = state.get_entity(uid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        if sc is None or getattr(sc, "ctx", None) is None:
            continue
        sc.ctx.passive_abilities = names
        st = states.get(uid)
        if st is not None and not getattr(sc.ctx, "passive_ability_level", None):
            lvl, mult = st
            sc.ctx.passive_ability_level = int(lvl)
            if mult is not None:
                sc.ctx.ability_variables_multiplier = int(mult)
        seeded += 1
    return seeded


def passive_ability_state_by_unit(ability_states: dict) -> dict:
    """`{entityId: (level, mult|None)}` de l'`AbilityState` des entrees de HIERARCHIE 2 du
    `TriggeredAbilityComponent` (payload `unitAbilityStates`).

    `UnitFactory$$Build` fabrique UN SEUL `passiveAbilityState` par unite et le passe a TOUS les
    `TryAdd(..., 2)` : les entrees d'une meme unite portent donc necessairement le meme couple, et
    on retient la premiere lisible. `level < 1` est REFUSE, meme invariant que
    `_load_tertiary_abilities` (`Idun.Shared.Level$$ToZeroBasedIndex` LEVE sur `<= 0`) : un `0` veut
    dire << pas de niveau publie >>, pas << niveau zero >>. Une unite sans entree de hierarchie 2
    n'a pas de cle -- tri-etat, comme les autres parsings de ce canal."""
    out: dict = {}
    for su in ((ability_states or {}).get("units") or []):
        uid = su.get("entityId")
        if uid is None or uid in out:
            continue
        for t in (su.get("triggered") or []):
            raw = t.get("raw") or []
            if len(raw) <= 10 or raw[10] != PASSIVE_HIERARCHY:
                continue
            lvl = t.get("level")
            if lvl is None or int(lvl) < 1:
                continue
            mult = t.get("mult")
            out[uid] = (int(lvl), None if mult is None else int(mult))
            break
    return out


def triggered_ability_ids_by_unit(ability_states: dict) -> dict:
    """`{entityId: [ids du TriggeredAbilityComponent, TOUTES hierarchies]}` depuis le payload du RPC
    `unitAbilityStates`.

    FOYER UNIQUE du parsing, exactement comme `passive_ability_names_by_unit` (hierarchie 2) et
    `active_ability_names_by_unit` (l'`ActiveAbilityComponent`) : `_load_triggered_abilities` (face
    COMBAT) et `engine.playbook.scene._seed_measured_triggered` (face DECISION) l'appellent toutes
    les deux. C'est ce que lit `IdunBattle.Entities.UnitExtensions$$HasTriggeredAbility`
    (-> `IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryGetAbility`), donc le substrat
    du gate `ShouldExecute` de l'attaque normale (#419-r1-tr14-r5-r2-r1-r1) comme du dispatcher
    d'utilite `TriggeredAbilitiesUtility(2)`.

    `raw[0]` = `TriggeredAbility.AbilityName`. AUCUN filtre de hierarchie : le natif n'en fait pas.
    Un id hors de l'enum du mirror est garde TEL QUEL (le natif le presente a
    `PlaybookDatabase$$LoadPlaybook`, qui rend `null` et le skippe) -- choix INVERSE de
    `passive_ability_names_by_unit`, qui porte des NOMS et doit ignorer l'inconnu.

    Une unite PRESENTE dans le payload mais sans aucune entree declenchee recoit `[]` -- une MESURE,
    a distinguer d'un canal muet, qui lui n'a aucune cle."""
    out: dict = {}
    for su in ((ability_states or {}).get("units") or []):
        uid = su.get("entityId")
        if uid is None:
            continue
        ids: list[int] = []
        for t in (su.get("triggered") or []):
            raw = (t or {}).get("raw") or []
            v = raw[0] if raw else None
            if isinstance(v, int) and v > 0 and v not in ids:   # `TryAdd` : une entree par id
                ids.append(v)
        out[uid] = ids
    return out


def triggered_ability_states_by_unit(ability_states: dict) -> dict:
    """`{entityId: {abilityId: (level, multiplier)}}` depuis le MEME payload `unitAbilityStates`
    que `triggered_ability_ids_by_unit` ci-dessus -- l'`AbilityState` sous lequel CHAQUE ability
    declenchee est MONTEE, toutes hierarchies (#1042-r1).

    C'est le substrat de `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` pour
    tout effet pose par une TRIGGERED : le couple `(level, mult)` que la fabrique a BAKE dans
    `EffectComponent+0x18`. Pour une MYTHIQUE de MACHINE OF WAR, c'est l'etat **TERTIAIRE**
    (`level 1..4 / mult 100`) -- MESURE : `unitAbilityStates` sur la MoW `ultraDreadnought` equipee
    de `WisdomOfTheAncients:4` rend `raw = [1451, 0, 0, 0, 4, 100, ...]` avec `level = 4,
    mult = 100`, tandis que ses PASSIFS portent `50 / 180` en runner normalise.

    POURQUOI CE FOYER EXISTE, et pourquoi il n'y a pas de RPC de plus : la face COMBAT lit ce
    couple par `runner/operations/triggers/base.py::triggered_ability_state` (#357), qui passe par
    `UnitContext.tertiary_ability` ; la face DECISION n'avait AUCUN canal -- `combatSnapshot
    .abilityStates` ne publie que les ACTIVES (`kind: active`), donc `Scene.ability_state(uid,
    1451)` rendait `None`. Le payload, lui, etait deja fetche par `build_predictor` et servait
    quatre autres seeds ; celui-ci est le cinquieme, sur le meme.

    `raw[0]` = `TriggeredAbility.AbilityName` (un `TriggeredAbilityType`) ; `level` / `mult` sont
    les champs deja projetes par le capteur. PREMIERE entree gagnante par id (`TryAdd`, meme regle
    que le foyer voisin). Une unite presente mais sans entree declenchee recoit `{}` -- une MESURE,
    a distinguer d'un canal muet, qui n'a aucune cle."""
    out: dict = {}
    for su in ((ability_states or {}).get("units") or []):
        uid = su.get("entityId")
        if uid is None:
            continue
        par_id: dict = {}
        for t in (su.get("triggered") or []):
            raw = (t or {}).get("raw") or []
            v = raw[0] if raw else None
            if not isinstance(v, int) or v <= 0 or v in par_id:
                continue                                   # `TryAdd` : une entree par id
            lvl, mult = (t or {}).get("level"), (t or {}).get("mult")
            if lvl is None:
                continue                                   # niveau NON MESURE -> pas d'entree
            par_id[v] = (int(lvl), int(mult if mult is not None else 100))
        out[uid] = par_id
    return out


def _load_triggered_abilities(state: State, ability_states: dict) -> int:
    """Seede `UnitContext.triggered_abilities` depuis le RPC `unitAbilityStates` (#456-r1).
    Rend le nombre d'unites seedees.

    MIRROR -- ce qu'on lit est la collection COMPLETE du `TriggeredAbilityComponent`, celle que
    `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
    enumere : `case.unit@+0x10` -> GetComponent -> `+0x18` -> `GetEnumerator`, SANS aucun filtre de
    hierarchie. C'est la difference avec `_load_passive_abilities` (hierarchie 2 seule) et
    `_load_tertiary_abilities` (hierarchie 3 seule), qui lisent le MEME payload pour d'autres
    consommateurs : ici on ne filtre pas, parce que le natif ne filtre pas.

    POURQUOI. Les trois producteurs du `ctx` tile-leaf derivaient ce kit du gameconfig par
    `visualId`. La face DECISION a ete recablee sur le canal live par #304 ; les deux autres
    (`runner_tile_leaf_ctx`, `scene_tile_leaf_ctx`) ne l'ont jamais ete. Mesure #456-r1
    (`MC1_67`/777, 4 unites confrontees, `probe_456r1_move_kit_vs_playbook.py`) : le kit gameconfig
    diverge de l'`AbilitiesComponent` sur **3 des 4** unites, et il diverge DANS LES DEUX SENS --
    `tauDarkstrider` natif `[1143, 1051, 1044]` contre port `[1143]`, et `tauCrisis` greffe natif
    `[1120, 1030]` contre port `[1133]`, c.-a-d. un id que le port ITERAIT et que la bataille n'a
    PAS monte. C'est la meme faute que #264 sur l'axe TRAITS : une RECONSTRUCTION a partir d'une
    autre source, fausse dans les deux sens.

    `raw[0]` = `TriggeredAbility.AbilityName` (le capteur dumpe 12 x int32 depuis `+0x10` ; base
    verifiee par recoupement `level`/`mult` = `raw[4]`/`raw[5]`, cf. `_load_tertiary_abilities`).
    Un id est garde TEL QUEL meme s'il est hors de l'enum du mirror : le dispatcher natif le
    presente a `PlaybookDatabase$$LoadPlaybook`, qui rend `null` et le skippe -- le port doit
    reproduire ce skip, pas faire disparaitre l'entree (c'est le choix INVERSE de
    `_load_passive_abilities`, qui porte des NOMS et n'a donc pas d'autre issue que d'ignorer un id
    hors enum).

    TRI-ETAT, meme discipline que les seeds voisins : sans canal, rien n'est pose et les foyers
    retombent sur le kit gameconfig. Une unite PRESENTE dans le payload mais sans aucune entree
    declenchee recoit `[]` -- une MESURE (« cette unite n'a aucun passif monte »), qui doit se
    distinguer d'un canal muet.

    Le PARSING vit dans `triggered_ability_ids_by_unit` (foyer partage avec la face DECISION)."""
    seeded = 0
    for uid, ids in triggered_ability_ids_by_unit(ability_states).items():
        ent = state.get_entity(uid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        if sc is None or getattr(sc, "ctx", None) is None:
            continue
        sc.ctx.triggered_abilities = ids
        seeded += 1
    return seeded


def _load_unit_traits(state: State, snapshot: dict) -> None:
    """Seede `UnitContext.traits` de CHAQUE entite depuis `combatSnapshot.units[].traits` (#264).

    MIRROR. Le capteur (`rpc-snapshot.ts`, bloc `readUnitTraits`, #233) ne lit AUCUNE collection en
    memoire -- il invoque la fonction NOMMEE que le jeu appelle lui-meme,
    `IdunBattle.Entities.UnitExtensions$$HasTrait(unit, trait)`, une fois par valeur d'enum
    `UnitTrait`, et rend la liste des ids VRAIS. Cette fonction delegue a
    `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`, qui interroge TROIS collections du
    composant -- la premiere etant un VETO :

        HasTrait(t) == !retires(+0x50).Contains(t)
                       && ( permanents(+0x40).Contains(t) || temporaires(+0x48).Contains(t) )

    Le canal rend donc l'ensemble EFFECTIF, veto compris : exactement ce que lisent les gates de
    trait du jeu. (`IdunBattle.Operations.AddTraitOperation$$Execute` ecrit `+0x40` quand
    `isTemporary == 0`, `+0x48` sinon ; `IdunBattle.Operations.RemoveTraitOperation$$RemoveTrait`
    RETIRE de `+0x40`/`+0x48` au lieu de remplir `+0x50`. Le veto lui-meme est **structurellement
    INERTE** -- `+0x50` = `DisabledTraits`, sans AUCUN ecrivain dans le binaire, mesure par #265,
    cf. `docs/rl/case-265-disabled-traits-aucun-ecrivain.md`. Sans consequence ici de toute facon :
    on lit la RESULTANTE, pas les collections.)

    POURQUOI. Jusqu'ici le port RECONSTRUISAIT ce substrat : `UnitContext.from_snapshot` posait
    `traits = gameconfig.unit(vis).traits`, et `entity_trait_names` y ajoutait le pseudo-trait de
    GRANDE-ALLIANCE derive du `GrandAllianceId`. Or le natif ne lit PAS le gameconfig : les traits de
    depart d'une unite viennent de `BattleConfiguration.Units[].Traits` -- et ce bloc N'EST PAS le kit
    gameconfig (les DEUX sens d'ecart sont mesures ci-dessous). C'est une reconstruction de la source
    a partir d'une autre source, pas une lecture.

    ECART MESURE (2026-07-30, `data/seed-bc.json`, 175 unites, comparaison offline `BC.Units[].Traits`
    vs `unit_trait_names(vis)`) : **5 unites ont MOINS que leur kit** -- `necroOverlord` sans
    `Resilient` (CONFIRME LIVE : la mesure rend `Hero/LivingMetal/Mechanical/Xenos`, le port en
    reconstruisait 5), `blackSmnBloodletter` sans `BlessingsOfKhorne`/`Summon`,
    `necroSmnSwarm`/`thousSmnBlueHorror` sans `Summon`, `deathNpc3Nurglings` sans `TeleportStrike` --
    et **48 en ont PLUS** (`custoAtlacoya` +`SistersSilence`, `astraDreir` +`DeathKorpsKrieg`, les npc
    +`Summon`/`NPC`). La reconstruction se trompait donc DANS LES DEUX SENS, en silence : un trait
    reconstruit EN TROP est une degradation PERMISSIVE (le port accorde un bonus que le natif refuse),
    un trait MANQUANT une degradation RESTRICTIVE (gate mort offline).
    ⚠ On ne DIT PAS pourquoi les deux blocs different -- une CAUSE au moins est deja documentee et
    n'a rien d'une regle generale : le seed BC est une CAPTURE (`#254-bc` au backlog : son bloc
    `Units` date de `gqfc5mff6c` et cite justement `necroOverlord` sans `Resilient`). Que l'ecart
    vienne d'une capture perimee, de la progression du joueur ou d'autre chose ne change RIEN au
    remede : on lit la source de la bataille COURANTE au lieu de la deviner depuis une autre.
    S'y ajoute ce que le kit ne peut PAS porter par construction : les traits ACCORDES EN BATAILLE
    (`AddTrait`, ex. `Stationary` sur le dreadnought de `DutyEternalAbility`), qu'un etat RECHARGE
    perdait integralement tant qu'aucune operation offline ne les avait rejoues.

    PORTEE : toutes les lignes du snapshot, `EntityType.Unit` ET `EntityType.Machine` -- une MoW
    porte un `MachineComponent`, frere du `UnitComponent` issu du meme
    `IdunBattle.Entities.Components.BaseUnitComponent$$.ctor`, donc `UnitExtensions$$HasTrait` y
    repond (mesure : `ultraDreadnought` rend `MachineOfWar`+`Imperial`). `_load_machine_stats` tourne
    a la fin de `_load_stats_and_effects`, donc le `StatsComponent` des DEUX types existe deja ici.
    Une entite SANS `StatsComponent` (cadavre : `combatSnapshot` filtre les morts, donc aucune ligne)
    n'est pas touchee -- ses lecteurs gardent le repli gameconfig de `_config_traits`/`_unit_dict`.

    TRI-ETAT, meme discipline que `_load_unit_flags` / `_load_unit_turn_state` : champ ABSENT ou
    `null` = **non mesure** (capteur anterieur a `0231573`, ou `UnitExtensions$$HasTrait` irresolue)
    -> on ne TOUCHE PAS `ctx.traits`, donc reconstruction STRICTEMENT anterieure ; une LISTE, `[]`
    comprise = mesure, on ecrit. Ici la distinction est CAPITALE et non theorique : `[]` ecrase le
    kit gameconfig par « aucun trait », et le capteur rend justement `null` (jamais `[]`) quand il
    n'a pas pu invoquer -- les confondre ferait passer un capteur MORT pour une unite sans trait.

    `traits_measured` marque le ctx : `entity_trait_names` cesse alors de re-deriver l'alliance
    par-dessus (elle est DANS la mesure -- `BC.Units[].Traits` la porte explicitement, verifie sur
    `necroOverlord` : `Xenos` y figure)."""

    for su in (snapshot.get("units") or []):
        eid = su.get("entityId")
        traits = su.get("traits")
        if eid is None or not isinstance(traits, list):
            continue                                  # absent / `null` = NON MESURE -> defaut du port
        ent = state.get_entity(eid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        if sc is None or getattr(sc, "ctx", None) is None:
            continue
        sc.ctx.traits = sorted(trait_names_from_ids(traits))
        sc.ctx.traits_measured = True


def _ability_state_from_config(uc) -> tuple:
    """`(multiplier, passiveAbilityLevel, activeAbilityLevel)` lus dans le `unitConfig` d'une ligne
    `combatSnapshot` — l'`AbilityState` de CETTE unité (`UnitConfiguration` : mult@0x74,
    ActiveAbilityLevel@0xB8, PassiveAbilityLevel@0xBC, cf. `rpc-snapshot.ts`).

    Le gate est le MULTIPLICATEUR : sur une ligne sans `unitConfig` exploitable (MoW — le capteur
    rend `{"error": "visualId introuvable"}`), on rend le neutre `(100, None, None)`. C'est
    exactement le triplet que la boucle de `_load_stats_and_effects` calculait en ligne ; il est
    extrait ici parce que la PASSE 1 (table par entité, pour résoudre la SOURCE d'un effet) et la
    boucle de matérialisation doivent en donner la MÊME lecture."""
    if not isinstance(uc, dict) or uc.get("abilityVariablesMultiplier") is None:
        return (100, None, None)
    return (int(uc["abilityVariablesMultiplier"]),
            int(uc["passiveAbilityLevel"]) if uc.get("passiveAbilityLevel") else None,
            int(uc["activeAbilityLevel"]) if uc.get("activeAbilityLevel") else None)


def _ability_state_from_rows(su) -> tuple:
    """`(multiplier, passiveAbilityLevel, activeAbilityLevel)` lus dans `combatSnapshot.units[]
    .abilityStates` -- l'`AbilityState` PER-ABILITY (`ActiveAbility._abilityState` @0x4c : `Level`@+0,
    `VariableMultiplierPercentage`@+4), le canal que la face DECISION consomme deja
    (`playbook/scene.py`) et que le COMBAT ignorait.

    POURQUOI CE TROISIEME CANAL (#888). Un **GUILD BOSS** (`gameconfig.units[].kind == "npc"`, ex.
    `deathBossMortarion`) n'a AUCUNE `UnitConfiguration` cote natif : `combatSnapshot.unitConfig`
    rend litteralement `{"error": "config null"}` -- MESURE, pas suppose. `_ability_state_from_config`
    y rend donc le neutre `(100, None, None)` et le ctx sortait avec `active_ability_level = None`,
    c.-a-d. l'INDEX 0 de chaque tableau de variables : le niveau **1** a la place du **55** que
    l'entite porte. C'est le gisement de #174 (MoW) et de #570-r5 (unites invoquees), sur un
    TROISIEME porteur ; les trois partagent la meme cause -- un canal `unitConfig` absent -- et la
    meme parade : lire l'`AbilityState`, qui est de toute facon ce que
    `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(config, var, abilityState, 0)`
    consomme REELLEMENT.
    MESURE (`deathBossMortarion` palier 4, board `GB_Mortarion_05`) : les trois vagues de
    `1093 MortarionsPlagueWind` sortaient a **45 / 65 / 120** contre **3080 / 4448 / 8211** live --
    l'ecart EST cet index.

    ⚠ **RIEN N'EST DEVINE, et le desaccord rend `None`.** Le port ne dispose que d'UN
    `active_ability_level` par unite, la ou le natif porte un `AbilityState` par ABILITY : cette
    fonction ne peut donc rendre un scalaire que si toutes les entrees concernees s'ACCORDENT. Si
    deux actives de la meme unite portaient des niveaux differents, on rend `None` (non mesure) --
    jamais l'une des deux. Meme regle pour le multiplicateur, et meme regle sur l'axe PASSIF.
    Sur le porteur mesure, les trois actives portent `(55, 200)` a l'identique."""
    rows = [a for a in ((su or {}).get("abilityStates") or []) if isinstance(a, dict)]
    if not rows:
        return (None, None, None)

    def _uniq(vals):
        """La valeur COMMUNE d'un axe, ou `None` des qu'il y a desaccord ou aucune mesure."""
        s = {int(v) for v in vals if v is not None}
        return s.pop() if len(s) == 1 else None

    actives = [a for a in rows if a.get("kind") == "active"]
    passives = [a for a in rows if a.get("kind") in ("passive", "triggered")]
    return (_uniq(a.get("multiplier") for a in rows),
            _uniq(a.get("level") for a in passives),
            _uniq(a.get("level") for a in actives))


def _ability_state_with_rows(from_config: tuple, su) -> tuple:
    """`from_config` (le PROXY `unitConfig`) SURCHARGE, champ par champ, par
    `_ability_state_from_rows` (l'`AbilityState` de l'INSTANCE) partout ou celui-ci a MESURE.

    ⚠ **CE N'EST PLUS UN COMBLEMENT DE TROU, ET C'EST LE POINT (#1049-r1).** Les deux canaux ne
    sont pas de meme rang, et les traiter comme deux vues d'une meme mesure -- ce que faisait la
    garde « on n'ecrit QUE si le trou existe » -- laisse gagner le proxy quand il ment. Ce qui
    tranche est LU (`rnca9r7q6c`), pas arbitre :

      * `IdunBattle.Entities.Factories.UnitFactory$$Build` construit les TROIS `AbilityState` de
        l'unite depuis la configuration du Build, champ par champ --
        `AbilityState..ctor(&passive,  config+0xBC, config+0x74)`,
        `AbilityState..ctor(&active,   config+0xB8, config+0x74)`,
        `AbilityState..ctor(&tertiary, config+0xC0, config+0x78)` -- puis les passe a
        `$$AddConfiguredAbilities` / `$$AddNormalAttackAbility` / `$$AddDerivedAbilities`, qui les
        BAKENT dans chaque instance montee. C'est cet objet, et non la configuration, que
        `IdunBattle.Configuration.AbilityConfiguration$$GetVariableForLevel(config, var,
        abilityState, 0)` consomme.
      * Le capteur, lui, ne lit PAS la configuration du Build : `readUnitConfig`
        (`frida/hooks/features/ai-step/rpc-snapshot.ts`) la RE-RESOUT par
        `IdunBattle.Core.Services.BattleQuery$$GetUnitConfig(VisualId)`, dont le corps est une
        recherche LINEAIRE sur `BC.Units[]` comparant `+0x10` puis
        `IdunBattle.Configuration.UnitConfiguration$$get_ConfigId`. Jointure **N->1** : rien ne
        garantit qu'elle retombe sur l'entree qui a monte CETTE entite.

    ⇒ l'`AbilityState` de l'instance est la SOURCE, `unitConfig` n'en est qu'un PROXY -- exact tant
    que la jointure vise juste, faux en silence sinon. Le capteur le disait deja sur l'axe ACTIF
    (« le global unitConfig est un AUTRE canal -- u80 : 65x120 vs 50x180 »), sans que le seed en
    tire la consequence.

    MESURE (`probe_1049r1_autorite_ability_state.py`, MC1_67/777) : `bloodNpc1Intercessor:45` monte
    par `--explicit-stats` porte `visualId = "bloodSmnIntercessor"` (son jumeau SUMMON), donc la
    jointure rend la config du summon -- `unitConfig = (mult 100, passif 1, actif 1)` la ou
    l'instance porte `(65, 200)`. Sur 8 heros ORDINAIRES du pool, les trois canaux concordent
    **8/8** : renverser la priorite ne change RIEN hors du regime ou le proxy ment.

    TRI-ETAT PRESERVE, et c'est ce qui borne le changement : un `None` de `_ability_state_from_rows`
    (axe non mesure, ou DESACCORD entre instances -- cf. son `_uniq`) ne peut jamais ecraser une
    valeur du proxy. On ne substitue que de la MESURE a de la MESURE."""
    mult, passive_level, active_level = from_config
    r_mult, r_passive, r_active = _ability_state_from_rows(su)
    return (mult if r_mult is None else r_mult,
            passive_level if r_passive is None else r_passive,
            active_level if r_active is None else r_active)


def _ability_state_with_channel(from_config: tuple, from_channel) -> tuple:
    """`(multiplier, passiveAbilityLevel, activeAbilityLevel)`, ou l'`AbilityState` PAR INSTANCE du
    canal `unitAbilityStates` PRIME sur le `unitConfig`.

    MEME BASCULE ET MEME RAISON que `_ability_state_with_rows` ci-dessus (#1049-r1) : le canal lit
    l'objet que le natif consomme, `unitConfig` lit une configuration RE-RESOLUE par une jointure
    `VisualId` N->1. La garde d'origine (« on n'ecrit QUE si le trou existe ») supposait deux vues
    d'une meme mesure ; elle laissait donc gagner un `passive_level = 1` qui n'est pas le niveau de
    l'entite mais celui d'une AUTRE entree de `BC.Units[]`.

    LE REGIME DU VRAI SUMMON EST INCHANGE : une unite INVOQUEE n'a AUCUNE `UnitConfiguration` cote
    natif (`IdunBattle.Operations.SpawnUnitOperation` fabrique ses stats par
    `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig`), `combatSnapshot
    .unitConfig` rend `{"error": "config null"}` et `_ability_state_from_config` le neutre
    `(100, None, None)` -- le canal gagnait deja, il gagne toujours.

    L'`activeAbilityLevel` n'est PAS invente : le canal des entrees de hierarchie 2 ne porte que le
    niveau des PASSIFS, donc il reste celui d'amont. C'est une BORNE CONNUE -- sur une entite dont
    le proxy ment, l'axe ACTIF reste faux ici ; il est seede separement, depuis le MEME canal, par
    `_load_active_ability_state`. `None` = non mesure, jamais un niveau devine."""
    mult, passive_level, active_level = from_config
    if from_channel is None:
        return from_config
    lvl, chan_mult = from_channel
    return (int(chan_mult) if chan_mult is not None else mult, int(lvl), active_level)


def _gameconfig_entry(GC, visual_id, snap_unit):
    """L'entree gameconfig d'une ligne de `combatSnapshot` -- par le `visualId`, et A DEFAUT par
    `BaseUnitComponent.Id` (#987-r1 / #889-r5-r3).

    POURQUOI DEUX CLES. `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` ecrit DEUX
    champs DISTINCTS sur le composant : `<Id @+0x10> = config.<Id @+0x10>` et `<VisualId @+0x20>`
    depuis `config+0x18`. Sur une unite ORDINAIRE ils coincident, donc la lecture par `visualId`
    suffit -- et c'est le chemin d'origine, INCHANGE. Sur un porteur monte par `--explicit-stats`
    ils DIVERGENT, et c'est mesure (2026-08-14, `darkaBossLion:4` sur `CE6_boss`) :

        decisionView.units[].visualId   = "GuildBoss12Boss1DarkaLion"   <- ABSENT du gameconfig
        combatSnapshot.units[].configId = "darkaBossLion:4"             <- la cle, suffixe compris
        gameconfig.unit("darkaBossLion") = { weapons: [{hits: 4, DamageProfile: "Power"}], ... }

    Sans cette seconde cle, `UnitContext.from_snapshot` lit `cfg.get("weapons") or []` -> `w = None`
    -> ni profil de degat, ni percage, ni nombre de coups, et le rejeu offline rend **zero coup**,
    SANS ERREUR. Le natif, lui, en jouait QUATRE (mesure #987). C'etait le residu #987-r1, et le
    volet (a) de `#889-r5-r3` (`sc.ctx.weapons` VIDE, donc `AttackDamageOperation.execute` rend
    `None` et l'attaque normale enchainee ne part pas).

    LE SUFFIXE DE PALIER est retire EN DERNIER RECOURS SEULEMENT, et l'ordre est load-bearing :
    des `unitId` npc portent un `:` DANS leur nom gameconfig (`thousNpc2Screamer:45`, cf.
    `rl_duel._parse_place`), donc couper d'abord ferait manquer leur entree. On essaie donc l'id
    PLEIN, puis la partie avant le DERNIER `:` (`rpartition`, comme `_parse_place`).

    TRI-ETAT : `configId` absent ou `null` = canal non mesure (bundle anterieur a cette tranche)
    -> on rend exactement ce que rendait le chemin d'origine. Aucun repli n'est INVENTE : on ne
    devine jamais l'unite par ses traits ou ses stats."""
    ent = GC.unit(visual_id or "")
    if ent is not None:
        return ent
    cid = (snap_unit or {}).get("configId")
    if not cid:
        return ent                                   # canal muet -> comportement d'avant
    ent = GC.unit(str(cid))
    if ent is not None:
        return ent
    base = str(cid).rpartition(":")[0]                # PALIER retire en DERNIER recours
    return GC.unit(base) if base else None


def _load_stats_and_effects(state: State, decision: dict, snapshot: dict,
                            ability_states=None) -> None:
    """Peuple `StatsComponent` (par unité) + `State.effects` (EffectsState matérialisé)
    depuis `combatSnapshot` + `decisionView`. Jointure : `combatSnapshot.entityId` ==
    `decisionView.id` (== id d'unité ECS, cf. en-tête). Mirror de la chaîne validée
    `predict_validate.build_samples` (UnitContext.from_snapshot + EffectsState.seed).

    ⚠ `combatSnapshot.units[]` porte DEUX `entityType` (`d9d0008`/#128) : les `Unit` (jointes à
    `decisionView.units[].id`) et les `Machine` (jointes à `decisionView.mows[].casterId`). La boucle
    ci-dessous ne traite QUE les premières ; les MoW sont déléguées à `_load_machine_stats` — elles
    n'ont ni `unitConfig` ni VisualId sur cette ligne, et leur niveau vit ailleurs (#174).

    `ability_states` (#570-r5) : le payload DEJA RESOLU du canal `unitAbilityStates`, passé par
    `load_state`. Il ne sert ICI qu'à une chose — COMBLER l'`AbilityState` des unités que
    `combatSnapshot.unitConfig` ne décrit pas (les INVOQUÉES), **avant** que leurs effets ne soient
    matérialisés. Le natif BAKE l'`AbilityStateReference` du poseur dans l'entité-effet, donc un
    effet né avant l'état de son owner lit un niveau faux et le garde. `None` = canal non fourni →
    comportement STRICTEMENT antérieur. Les SEEDS de ce canal (noms d'abilities, relique) restent
    dans `load_state`, en aval : eux écrivent dans les ctx que cette fonction pose."""
    import gameconfig as GC                      # données offline (traits/arme/profil)

    vis_by_id = {u.get("id"): u.get("visualId") for u in (decision.get("units") or [])}
    effects_by_id = {u.get("id"): (u.get("effects") or []) for u in (decision.get("units") or [])}
    # Les MoW portent des effets (`EffectsOwnedComponent` natif — mesuré : `HeavyRailRifle_
    # PendingAttack` se pose sur l'entité Machine) -> elles entrent dans le seed `EffectsState`
    # au même titre que les unités.
    for _m in _machine_rows(decision):
        effects_by_id[int(_m["casterId"])] = _m.get("effects") or []
    mult_by_id: Dict[int, int] = {}
    ablvl_by_id: Dict[int, Optional[int]] = {}
    # PASSE 1 — l'`AbilityState` de CHAQUE entité, AVANT toute matérialisation d'effet.
    # Un effet est baké avec l'état de sa SOURCE (`AddEffectBehaviour$$DefaultEffectBuilder` copie
    # l'`AbilityStateReference` dans `EffectComponent+0x18` À LA POSE, cf. `baked_ability_state`) :
    # matérialiser les effets du porteur A exige donc l'état du porteur B qui les a posés. Cette
    # table est PURE DONNÉE (`unitConfig` / `AbilityState` per-ability des MoW) : elle ne dépend
    # d'aucun `StatsComponent`, donc elle peut être construite avant la boucle qui les pose.
    abstate_by_id: Dict[int, tuple] = {}
    # #570-r5 -- l'`AbilityState` PAR INSTANCE (canal `unitAbilityStates`), lu ICI et pas plus tard.
    # `passive_ability_state_by_unit` est du PARSING PUR (il ne lit que le payload), donc il a sa
    # place dans cette passe « PURE DONNEE » ; ce qu'il comble est ce dont la materialisation des
    # effets a besoin. Sans canal -> `{}` -> comportement strictement anterieur.
    chan_abstate = passive_ability_state_by_unit(ability_states) if ability_states else {}
    for su in (snapshot.get("units") or []):
        if su.get("entityId") is None or su.get("entityType") == _ENTITY_TYPE_MACHINE:
            continue
        _eid = int(su["entityId"])
        # #888 : `_ability_state_with_rows` d'ABORD (l'`AbilityState` per-ability de CETTE ligne de
        # snapshot, seul canal d'un GUILD BOSS), puis le comblement `unitAbilityStates` qui, lui, ne
        # porte que l'axe PASSIF. Les deux ne s'ecrivent que dans un TROU -- l'ordre n'est donc pas
        # un arbitrage, mais il place la source la plus SPECIFIQUE (per-ability) en premier.
        abstate_by_id[_eid] = _ability_state_with_channel(
            _ability_state_with_rows(_ability_state_from_config(su.get("unitConfig")), su),
            chan_abstate.get(_eid))
    for _m in _machine_rows(decision):
        # MoW : `unitConfig` est en erreur sur une ligne Machine — le SEUL canal est l'`AbilityState`
        # per-ability (cf. `_machine_ability_state`). Une MoW POSE des effets sur des unités
        # (`HeavyRailRifle_PendingAttack`), elle doit donc être résolvable comme source.
        _lvl, _mlt = _machine_ability_state(_m)
        abstate_by_id[int(_m["casterId"])] = (int(_mlt or 100), None, _lvl or None)
    for su in (snapshot.get("units") or []):
        eid = su.get("entityId")
        if eid is None:
            continue
        # MACHINES OF WAR — on SAUTE la ligne ici, `_load_machine_stats` (fin de fonction) la reprend.
        # `combatSnapshot` remonte `EntityType.Unit` ET `EntityType.Machine` (`d9d0008`/#128), mais l'entité
        # Machine porte un `MachineComponent`, PAS un `UnitComponent` (les deux sont des frères issus
        # de `IdunBattle.Entities.Components.BaseUnitComponent$$.ctor`) : le capteur cherche la VisualId
        # sur `UnitComponent` et rend `unitConfig = {"error": "visualId introuvable"}` (mesuré). Bâtir
        # le ctx ICI donne donc `active_ability_level = 0` / `ability_variables_multiplier = 100` — ET
        # prive `_load_machine_stats` de son tour (il ne pose rien si un `StatsComponent` existe déjà).
        # Toutes les variables per-niveau de la MoW se lisaient alors à l'INDEX 0, c.-à-d. au niveau 1
        # (#174 : `SquigMine.nrOfTiles` 2 au lieu de 4, `EntropyCannons.minDmg` 28 au lieu de 2249).
        # Le seul canal portant le niveau d'une Machine est son `AbilityState` per-ability
        # (`IdunBattle.Entities.Components.ActiveAbility$$get_AbilityState`), cf. `_machine_ability_state`.
        if su.get("entityType") == _ENTITY_TYPE_MACHINE:
            continue
        vis = vis_by_id.get(eid)
        su = {**su, "visualId": vis}
        # On construit le ctx MÊME si la prédiction `normalAttack` a erré (cible hors portée au moment
        # de la capture, ex. déploiement) : les STATS (`su["stats"]`) sont valides, et le COMBAT
        # (`AttackDamageOperation.execute`) re-sélectionne arme/hits/perçage depuis **gameconfig** (pas la
        # prédiction snapshot) ⇒ un ctx stat-based suffit. (Avant on SAUTAIT ces unités → un overwatcher
        # ou une cible hors portée à la capture n'avait pas de StatsComponent → vecteur after-move/hit KO.)
        uc = su.get("unitConfig") or {}
        # Effets matérialisés de l'unité → attribution stat-mod dans ctx.stats (via from_snapshot).
        # L'état d'ability est pris sur la SOURCE de CHAQUE effet (`EffectComponent.SourceUnitId`,
        # publié par le capteur), pas sur le porteur : le natif BAKE l'`AbilityStateReference` du
        # caster dans l'entité-effet à la pose. Repli = le porteur (source absente/non chargée).
        # cf. `engine.entities.effects_state.baked_ability_state` pour la chaîne native complète.
        # #570-r5 : le triple du PORTEUR est celui de la PASSE 1, pas un second calcul -- il porte
        # donc le comblement `unitAbilityStates`. Les deux lectures DOIVENT etre la meme (c'est deja
        # la raison d'etre de `_ability_state_from_config`), et desormais le comblement aussi.
        _carrier = abstate_by_id.get(eid) or _ability_state_from_config(uc)
        _emult, _eablvl, _eactive = _carrier
        _effs = [EffectFactory.create(c, *baked_ability_state(c, eid, _carrier, abstate_by_id))
                 for c in (effects_by_id.get(eid) or [])
                 if isinstance(c, dict) and c.get("name")]
        ctx = UnitContext.from_snapshot(su, _gameconfig_entry(GC, vis, su),
                                        snapshot.get("statTypes"), _effs)
        if isinstance(uc, dict) and uc.get("abilityVariablesMultiplier") is not None:
            ctx.ability_variables_multiplier = int(uc["abilityVariablesMultiplier"])
            mult_by_id[eid] = ctx.ability_variables_multiplier
            if uc.get("passiveAbilityLevel"):
                ablvl_by_id[eid] = int(uc["passiveAbilityLevel"])
            # NIVEAU d'ability ACTIVE = `unitConfig.activeAbilityLevel` (le stat `activeAbilityLevel` du
            # combatSnapshot est None) — indexe minDmg/maxDmg[level] des abilities actives (cf.
            # AActiveAbility.MinMaxDamage / ability_attack_params). Sans ça, niveau=0 → dégât d'ability faux.
            if uc.get("activeAbilityLevel"):
                ctx.active_ability_level = int(uc["activeAbilityLevel"])
            # niveau des PASSIVES (indexe leurs variables, ex. ArcaneShield.shieldHp[level]).
            if uc.get("passiveAbilityLevel"):
                ctx.passive_ability_level = int(uc["passiveAbilityLevel"])
        # #570-r5 -- LE MEME COMBLEMENT, SUR LE CTX, ET **AVANT** `_seed_ability_owner_effects`.
        # `_load_passive_abilities` fait deja cette ecriture, mais en AVAL de la materialisation :
        # l'owner-effect pose plus bas (boucle ABILITIES d'`IdunBattle.Operations.
        # InitializeActorAbilitiesOperation$$Execute`) naissait alors avec le niveau/multiplicateur
        # d'AVANT. MESURE (#570-r5, `orksGrotTank` invoque par `orksBigMek` rank 17) : le ctx du
        # tank portait bien `(50, 180)` a la fin de `load_state`, et son instance
        # `Ramshackle_DmgReduction` `ability_level = None` / `mult = 100` -> `dmgReduction[1] = 5`
        # au lieu de `dmgReduction[50] x 180 %`.
        # Le seed d'aval reste en place et devient un NO-OP sur cet axe (sa garde est la meme :
        # « seulement si `passive_ability_level` est absent/0 ») -- pas une double ecriture.
        # ⚠ ON RELIT `_carrier`, PAS LE CANAL : le ctx et `abstate_by_id` sont DEUX tables, et une
        # garde posee sur une seule laisserait l'autre diverger -- c'est `abstate_by_id` qui bake
        # l'`AbilityState` dans les effets, donc l'ecart y serait SILENCIEUX. Partir du meme triple
        # rend la divergence structurellement impossible.
        # ⚠ #1049-r1 -- CE N'EST PLUS UN COMBLEMENT, C'EST UNE SURCHARGE, et c'est ce qui remet les
        # deux tables d'accord. `_carrier` EST le triple d'AUTORITE de la passe 1 : le `unitConfig`
        # deja surcharge par l'`AbilityState` de l'INSTANCE (`_ability_state_with_rows`, puis
        # `_ability_state_with_channel`). Le bloc `uc` ci-dessus, lui, ecrit le PROXY. Tant que la
        # pose d'ici ne faisait que COMBLER, le proxy gagnait sur le ctx alors que `abstate_by_id`
        # suivait l'instance : les deux tables que ce commentaire disait vouloir garder identiques
        # divergeaient donc exactement dans le regime ou le proxy ment.
        # Substitution de MESURE a MESURE seulement : `_eablvl` faux (non mesure) ne touche rien.
        if _eablvl:
            ctx.passive_ability_level = int(_eablvl)
            ctx.ability_variables_multiplier = int(_emult)
        # #888 -- LE MEME COMBLEMENT, SUR L'AXE **ACTIF**. Le bloc `unitConfig` ci-dessus ne s'ouvre
        # que si `abilityVariablesMultiplier` existe ; un GUILD BOSS n'a AUCUN `unitConfig`
        # (`{"error": "config null"}`, mesure) et repartait donc avec `active_ability_level = None`
        # = index 0 = niveau 1. `_carrier` porte desormais l'`AbilityState` per-ability de la ligne
        # de snapshot (`_ability_state_with_rows`) : on le pose ICI, sous la MEME garde que ses deux
        # jumeaux -- « seulement si le trou existe », donc jamais par-dessus une valeur mesuree.
        # ⚠ On relit `_carrier`, PAS le canal (meme raison que le bloc ci-dessus : `abstate_by_id`
        # bake l'`AbilityState` dans les effets, un ecart entre les deux serait SILENCIEUX).
        # #1049-r1 : SURCHARGE ici aussi, meme raison -- `_carrier` porte l'`AbilityState` de
        # l'instance, `uc` un proxy re-resolu par une jointure `VisualId` N->1.
        if _eactive:
            ctx.active_ability_level = int(_eactive)
        if _emult:
            ctx.ability_variables_multiplier = int(_emult)
        ent = state.get_entity(eid)
        if ent is not None:
            ent.add_component(StatsComponent(ctx=ctx))
            # BOUCLIER : instances captées (combatSnapshot.shields) → ShieldComponent (absorption +
            # décay EndTurn). `remaining` None = permanent. Absent/[] → pas de composant (cible sans bouclier).
            shields = su.get("shields")
            if isinstance(shields, list) and shields:
                insts = [ShieldInstance(int(sh.get("id") or 0), int(sh.get("amount") or 0),
                                        sh.get("remaining"))
                         for sh in shields if (sh.get("amount") or 0) > 0]
                if insts:
                    ent.add_component(ShieldComponent(shields=insts))
    _load_machine_stats(state, decision, snapshot, mult_by_id)
    # effets ACTIFS structurés (decisionView.effects), matérialisés + propagés mult/level.
    # `abstate_by_id` : l'état d'ability de chaque entité, consulté par la SOURCE de chaque effet
    # (mirror du bake natif) ET, depuis case-366-r1, par le PORTEUR en repli — c'est le seul canal
    # qui porte son `activeAbilityLevel`. Les deux tables par PORTEUR restent le repli du repli.
    state.effects = EffectsState.seed(effects_by_id, mult_by_id, ablvl_by_id, abstate_by_id)
    # `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` (boucle ABILITIES) : à la création de CHAQUE
    # unité, l'owner-effect posé par le `CreateBehaviour` de ses abilities (DSL `AddEffect(owner)`). Le
    # SEED live (decisionView.effects) ne capte QUE les effets ACTIFS à l'instant T -> il RATE les
    # owner-effects passifs INACTIFS au capture (ex. HP-floor `HypersensoryAbilities_MinimalHealth` de Judh,
    # actif seulement au tour ENNEMI via son ActiveCondition). On les pose ici (idempotent : les effets déjà
    # captés live sont skippés). Gate TeleportingIn (1035) : passives DIFFÉRÉES jusqu'à l'atterrissage
    # (`land_deep_strike`), pas initialisées au capture. #G6a.
    for eid in list(state.entities.keys()):
        if state.effects.has_effect(eid, effect_type=TELEPORT_STRIKE_TELEPORTING_IN):
            continue
        ent = state.get_entity(eid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if sc is None or uc is None or not uc.visual_id:
            continue
        _mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100)
        _seed_ability_owner_effects(state, eid, uc.visual_id, _mult,
                                    ability_level=getattr(sc.ctx, "passive_ability_level", None))
        # #1015-r1 -- LA BOUCLE **TRAITS** DE LA MEME OPERATION NATIVE, ET ELLE MANQUAIT ICI.
        # `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` en a DEUX : la boucle
        # ABILITIES ci-dessus, et une boucle TRAITS (`Trait$$GetEffectToBeAddedToOwnerForTrait`
        # + `AddTraitOperation$$AddDerivedAbilities` -> l'owner-effect pose a l'init de l'ability
        # derivee). `runner/operations/spawn.py` appelle bien les DEUX ; ce chemin-ci, celui de la
        # capture, n'appelait que la premiere -- donc une unite DEJA sur le plateau au capture
        # n'avait jamais ses owner-effects de TRAIT.
        #
        # C'EST RESTE INVISIBLE tant que tous les owner-effects de trait portes etaient
        # INCONDITIONNELS (`BigTarget`, `Daemon`, `Terrifying`, `Diminutive`, `ShadowInTheWarp`,
        # `HeavyWeapon`, `MartialKatah`, `RangedSpecialist`) : le natif les a des la creation, donc
        # `decisionView.effects` les publie, donc `EffectsState.seed` les avait deja et les deux
        # `_materialize_owner_effect` sont des no-op (ils sont IDEMPOTENTS, gate `has_effect`).
        # `1235 InstinctiveBehaviour_BlockMovement` est le premier owner-effect de trait dont la
        # `CreateActiveCondition` soit CONDITIONNELLE : le canal actif-only ne le publie pas, et
        # sans cette ligne il n'existait sur AUCUN porteur charge depuis une capture.
        _traits = getattr(sc.ctx, "traits", None) or ()
        _seed_trait_owner_effects(state, eid, _traits, _mult)
        _seed_derived_ability_owner_effects(state, eid, _traits, _mult)


def _rebake_tertiary_owner_effects(state: State) -> int:
    """RE-BAKE du couple `(niveau, multiplicateur)` des owner-effects d'une relique EQUIPEE (#1009).

    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder(id, abilityState)`
    **BAKE** l'`AbilityStateReference` de l'ability QUI POSE dans `EffectComponent+0x18`, et
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` relit ce champ et RIEN
    d'autre. Pour un owner-effect pose par une ability TERTIAIRE (une relique equipee), cet etat
    est celui que `IdunBattle.Entities.Factories.UnitFactory$$Build` a fabrique depuis
    `config+0xc0 TertiaryAbilityLevel` / `config+0x78` -- MESURE `level 1..10 / mult 100`, la ou
    les passifs du MEME porteur portent `50 / 180` (#1005).

    LE PORT DIVERGEAIT DE LUI-MEME, et c'est ce qui rend cette passe necessaire :
      * la voie OFFLINE (`runner/operations/spawn.py::_seed_ability_owner_effects`) passe deja le
        couple TERTIAIRE quand l'ability est `ctx.tertiary_ability` (#1005/#1007) ;
      * la voie LIVE (`decisionView.effects` -> `EffectsState.seed`) est clee par PORTEUR et ne
        connait que le couple PASSIF -- or c'est ELLE qui gagne, parce que `_materialize_owner_effect`
        est idempotent (`has_effect` -> no-op des que l'effet est deja capte).
    Sur un runner live, un owner-effect de relique arrivait donc TOUJOURS avec le niveau des
    passifs, c.-a-d. le dernier palier apres clamp (`ToZeroBasedIndex` clampe `idx >= len`) :
    mesure #1009 -- `MonsterSlayerOfCaliban.extraDmg[3] = 543` lu **728**, et
    `blockDmg[3] = 1629` lu **2184**.

    PORTEE STRICTE, et c'est ce qui borne le rayon : la passe ne touche QUE les effets dont le NOM
    figure dans `ABILITY_INIT_OWNER_EFFECTS[<ability TERTIAIRE de CETTE unite>]`. Une unite sans
    relique equipee (`tertiary_ability` nul, ou `tertiary_ability_level <= 0`) n'est pas visitee ;
    un effet pose par un passif ou par un tiers n'est jamais reecrit. Elle est donc INERTE partout
    ou le canal `unitAbilityStates` (#357/#363) n'est pas lie.

    Rend le nombre d'instances re-bakees (0 = aucune relique equipee dans la capture)."""
    if state.effects is None:
        return 0
    n = 0
    for uid, ent in state.entities.items():
        sc = ent.get_component(StatsComponent)
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        tert = getattr(ctx, "tertiary_ability", None) if ctx is not None else None
        if not tert:
            continue
        lvl = int(getattr(ctx, "tertiary_ability_level", 0) or 0)
        if lvl <= 0:                       # `0` = verrouille (`Level$$CreateValidOrLockedLevel`)
            continue
        noms = set(_effects_factory.get_owner_effects_added_on_ability_init(str(tert)) or ())
        if not noms:
            continue
        mult = int(getattr(ctx, "tertiary_ability_variables_multiplier", 100) or 100)
        for eff in (state.effects.by_unit.get(uid) or ()):
            if getattr(eff, "name", None) in noms:
                eff.ability_level = lvl
                eff.ability_variables_multiplier = mult
                n += 1
    return n


def _rebake_tertiary_posed_effects(state: State) -> int:
    """RE-BAKE du couple `(niveau, multiplicateur)` des effets qu'une ability TERTIAIRE pose sur
    AUTRUI (#1038). MEME cause que `_rebake_tertiary_owner_effects` ci-dessus, AUTRE porte.

    CE QUE LA PASSE PRECEDENTE NE PEUT PAS VOIR, ET POURQUOI. Elle est clee par PORTEUR : elle
    visite `state.effects.by_unit[<unite qui porte la tertiaire>]`. Or deux behaviours de mythique
    de MoW posent AILLEURS que sur leur owner :
      * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MastersOfManoeuvreAbility$$CreateBehaviour`
        = `AddEffect(0x5e6, get_AbilityStateReference(this), source = Owner@<DSLSelectors+0x30>,
          targets = **Actor@<DSLSelectors+0x40>**, TurnsFromRounds(nrOfRounds))` -- l'effet vit sur
        l'ami qui vient de bouger, jamais sur la MoW ;
      * l'AURA de `ContemptuousDisregard_DamageReductionEffect$$CreateTargetSelector`, qui
        MATERIALISE l'effet sur chaque beneficiaire (patron `GuardianOrganism`, #89).
    Dans les deux cas `source == la MoW` et `porteur == quelqu'un d'autre`.

    LE NATIF, LUI, NE FAIT AUCUNE DIFFERENCE :
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder(id, abilityState)`
    COPIE l'`AbilityStateReference` recue dans `EffectComponent+0x18`, et
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` relit ce champ et RIEN
    d'autre -- **l'effet ne consulte jamais son porteur**. Cette reference vient de l'ability QUI
    POSE, donc de la TERTIAIRE : `level 1..4 / mult 100` (fabriquee par
    `IdunBattle.Entities.Factories.UnitFactory$$Build` depuis `config+0xc0 TertiaryAbilityLevel`),
    la ou les passifs de la MEME unite portent `50 / 180` en runner normalise.

    MESURE (#1038, `darkaStormSpeeder` + `MastersOfManoeuvre` niveau 1, board `MC1_67`) : sans
    cette passe, l'instance captee sur l'ami arrivait avec `ability_level = None` et `mult = 160`
    (le repli sur le porteur, `effects_state.baked_ability_state`) -> `ConfigVar(0x46)` ne trouvait
    AUCUN `AbilityState` et la classe d'effet rendait `None` : la reduction etait **entierement
    INERTE**. Avec, elle lit `dmgReductionPct[1]`.

    PORTEE STRICTE, et c'est ce qui borne le rayon : la passe ne reecrit QUE les instances dont la
    **SOURCE** porte une tertiaire DEBLOQUEE (`tertiary_ability_level > 0`) ET dont le NOM figure
    dans `factory.TERTIARY_ABILITY_POSED_EFFECTS[<cette tertiaire>]`. Un effet homonyme pose par un
    passif d'une AUTRE unite n'est jamais touche (la source ne porte pas la tertiaire) ; une unite
    sans tertiaire n'est pas visitee. Elle est donc INERTE partout ou le canal `unitAbilityStates`
    (#357/#363) n'est pas lie.

    Rend le nombre d'instances re-bakees (0 = aucune mythique/relique de ce genre en jeu)."""
    if state.effects is None:
        return 0
    etats: dict = {}          # {source_id: (niveau tertiaire, multiplicateur tertiaire)}
    noms_par_source: dict = {}
    for uid, ent in state.entities.items():
        sc = ent.get_component(StatsComponent)
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        tert = getattr(ctx, "tertiary_ability", None) if ctx is not None else None
        if not tert:
            continue
        lvl = int(getattr(ctx, "tertiary_ability_level", 0) or 0)
        if lvl <= 0:                       # `0` = verrouille (`Level$$CreateValidOrLockedLevel`)
            continue
        noms = set(_effects_factory.get_effects_posed_by_tertiary_ability(str(tert)) or ())
        if not noms:
            continue
        etats[int(uid)] = (lvl, int(getattr(ctx, "tertiary_ability_variables_multiplier", 100) or 100))
        noms_par_source[int(uid)] = noms
    if not etats:
        return 0
    n = 0
    for effs in (state.effects.by_unit or {}).values():
        for eff in (effs or ()):
            src = getattr(eff, "source", None)
            if src is None:
                continue
            try:
                src = int(src)
            except (TypeError, ValueError):
                continue
            couple = etats.get(src)
            if couple is None or getattr(eff, "name", None) not in noms_par_source[src]:
                continue
            eff.ability_level, eff.ability_variables_multiplier = couple
            n += 1
    return n


def _source_ability_state(state: State, source_id) -> Tuple[int, Optional[int], Optional[int]]:
    """`(multiplier, passiveAbilityLevel, activeAbilityLevel)` de l'unité SOURCE d'un effet.

    Le natif BAKE l'`AbilityStateReference` (`EffectComponent.AbilityState @+0x18`) à la CRÉATION de
    l'effet (`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder`), depuis
    l'ability qui le pose — donc depuis la SOURCE, pas depuis le porteur. On lit ici le canal exact,
    le `StatsComponent.ctx` de la source (`EffectComponent.SourceUnitId` = le champ `source` du
    capteur).

    DIFFÉRENCE avec la voie des UNITÉS (`engine.entities.effects_state.baked_ability_state`, #382),
    et elle tient au REPLI, pas à la lecture : une TUILE n'a AUCUN `unitConfig`, donc rien à quoi se
    replier — source inconnue/non chargée (posée par une unité morte et retirée de la capture, ou
    par l'environnement) → neutre (100, None, None), MÊME défaut que `EffectFactory.create`. Un
    effet d'UNITÉ, lui, se replie sur son PORTEUR."""
    if source_id is None:
        return (100, None, None)
    ent = state.get_entity(int(source_id))
    sc = ent.get_component(StatsComponent) if ent is not None else None
    if sc is None:
        return (100, None, None)
    ctx = sc.ctx
    mult = getattr(ctx, "ability_variables_multiplier", 100)
    return (int(mult or 100),
            getattr(ctx, "passive_ability_level", None),
            getattr(ctx, "active_ability_level", None))


def _load_tile_effects(state: State, tiles, board) -> int:
    """Effets portés par les TUILES (`tileMeta.tiles[].effects`) → `State.effects`, clé =
    l'ENTITÉ-TUILE (id `boardGraph`). Rend le nombre d'effets matérialisés.

    MIRROR de l'append natif : `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` ajoute
    l'id de l'entité-effet à `EffectsOwnedComponent.ActiveEffectIds` de la CIBLE, sans jamais
    regarder son EntityType (le seul branchement unité-spécifique d'`AddEffectOperation$$Execute`
    est gardé par `IdunBattle.Entities.EntityExtensions$$IsUnit`). Côté port, l'homonyme de cet
    append est `EffectsState.add_effect(carrier_id, effect)` — c'est déjà par là que passe la POSE
    en combat (`AddEffectOperation` du runner : la glace de LordOfTempests vit dans
    `by_unit[tile_id]`). Le LOAD emprunte donc EXACTEMENT le même chemin que la pose ; il n'y a
    pas deux modèles d'effet de tuile, il y en a un seul, alimenté par deux bouts.

    Pourquoi pas `EffectsState.seed` (la voie des unités) : son `mult_by_unit`/`ability_level_by_unit`
    sont keyés PAR PORTEUR, ce qui n'a pas de sens pour une tuile (elle n'a pas de config propre et
    peut porter des effets de sources DIFFÉRENTES — p.ex. deux feux posés par deux MoW). On
    matérialise donc effet PAR effet avec l'état de SA source (`_source_ability_state`), ce qui est
    strictement plus fidèle que la clé par porteur.

    `board` est indispensable : `tileMeta` ne rend que (col,row), l'ID d'entité-tuile (celui que
    `state.effects` et `AddEffectOperation` utilisent) ne vient que de `boardGraph`. Sans board →
    aucun seed (dégradation silencieuse impossible à confondre : l'appelant qui veut les effets de
    tuile passe forcément le board, seul point d'injection du plateau)."""

    rows = _tile_rows(tiles)
    if board is None or not rows:
        return 0
    if state.effects is None:
        state.effects = EffectsState()
    n = 0
    for t in rows:
        captured = [e for e in (t.get("effects") or []) if isinstance(e, dict) and e.get("name")]
        if not captured:
            continue
        col, row = t.get("col"), t.get("row")
        tid = board.id_at(col, row) if (col is not None and row is not None) else None
        if tid is None:
            continue
        for cap in captured:
            mult, ablvl, actlvl = _source_ability_state(state, cap.get("source"))
            state.effects.add_effect(int(tid),
                                     EffectFactory.create(cap, mult, ablvl, actlvl))
            n += 1
    return n


def tile_effects_footprint(state: State) -> Optional[dict]:
    """Empreinte OFFLINE des effets de tuile : `{tile_id: {effectType: remaining}}`.

    `remaining` None (effet sans compte-à-rebours) → 0, comme le capteur live qui rend 0 quand
    `EffectComponent.HasTurns` est faux. None si l'état n'a ni effets ni board (canal absent —
    rien à confronter). Les ids d'entité sont GLOBAUX côté natif (unités et tuiles dans le même
    espace) : l'appartenance au board (`board.by_id`) est donc le discriminant exact « c'est une
    tuile »."""
    if state.effects is None or state.board is None:
        return None
    out: Dict[int, dict] = {}
    for key, effs in state.effects.by_unit.items():
        if int(key) not in state.board.by_id:
            continue
        cur = {int(e.effect_type): (0 if e.remaining_turns is None else int(e.remaining_turns))
               for e in effs if not e.consumed and e.effect_type is not None}
        if cur:
            out[int(key)] = cur
    return out


def tile_effects_footprint_live(tiles, board) -> Optional[dict]:
    """MÊME empreinte, calculée DIRECTEMENT depuis `tileMeta` + `boardGraph` (chemin INDÉPENDANT
    de `load_state` → cross-check du seed, comme `snapshot_live` l'est de `snapshot`)."""
    if tiles is None or board is None:
        return None
    out: Dict[int, dict] = {}
    for t in _tile_rows(tiles):
        cur = {int(e["effectType"]): int(e.get("remaining") or 0)
               for e in (t.get("effects") or [])
               if isinstance(e, dict) and e.get("effectType") is not None}
        if not cur:
            continue
        col, row = t.get("col"), t.get("row")
        tid = board.id_at(col, row) if (col is not None and row is not None) else None
        if tid is not None:
            out[int(tid)] = cur
    return out


def snapshot(state: State) -> dict:
    """`State` → forme canonique comparable (lue depuis les composants)."""
    units: Dict[int, dict] = {}
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        pc = e.get_component(PositionComponent)
        hc = e.get_component(HealthComponent)
        ec = e.get_component(EffectsOwnedComponent)
        units[eid] = {
            "visualId": uc.visual_id if uc else None,
            "alive": uc.alive if uc else None,
            "team": oc.team if oc else None,
            "pos": [pc.col, pc.row] if pc else None,
            "hp": hc.hp if hc else None,
            "hpMax": hc.hp_max if hc else None,
            "effects": list(ec.effects) if ec else [],
        }
    return {"currentPlayer": state.current_player_id, "units": units,
            # `tiles` = empreinte des effets PORTÉS PAR LES TUILES (#102). None = canal absent
            # (pas de board / pas d'EffectsState) -> `diff` ne le confronte pas.
            "tiles": tile_effects_footprint(state)}


def snapshot_live(decision: dict, observe: dict, tiles=None, board=None) -> dict:
    """MÊME forme canonique, DIRECTEMENT depuis les RPC (chemin indépendant).

    `tiles` (payload `tileMeta`) + `board` : ajoutent l'empreinte des effets de TUILE — le pendant
    live de `snapshot(state)["tiles"]`. Omis -> None, et `diff` n'en confronte AUCUN côté (les
    appelants historiques `snapshot_live(dec, ob)` gardent donc exactement leur sémantique)."""
    hp_by_id = _hp_by_id(observe)
    units: Dict[int, dict] = {}
    for u in (decision.get("units") or []):
        uid = u.get("id")
        if uid is None:
            continue
        p = u.get("pos") or {}
        hp, hp_max = hp_by_id.get(uid, (None, None))
        units[uid] = {
            "visualId": u.get("visualId"),
            "alive": bool(u.get("alive")),
            "team": u.get("team"),
            "pos": [p["col"], p["row"]] if p.get("col") is not None else None,
            "hp": hp,
            "hpMax": hp_max,
            "effects": _effect_names(u),
        }
    # MoW : mêmes clés (l'entité Machine EST dans `state.entities` depuis `_load_machines`) —
    # pos/hp/hpMax restent None (hors-plateau, pas de HealthComponent natif). Sans cette symétrie,
    # `diff(snapshot_live, snapshot(state))` signalerait chaque MoW « absente à gauche ».
    for m in _machine_rows(decision):
        mid = int(m["casterId"])
        mp = m.get("pos") or {}
        units[mid] = {
            "visualId": m.get("visualId"),
            "alive": bool(m.get("alive", not m.get("isDead", False))),
            "team": m.get("team"),
            "pos": [mp["col"], mp["row"]] if mp.get("col") is not None else None,
            "hp": m.get("hp"),
            "hpMax": m.get("maxHp"),
            "effects": _effect_names(m),
        }
    return {"currentPlayer": decision.get("currentPlayer"), "units": units,
            "tiles": tile_effects_footprint_live(tiles, board)}


def diff(a: dict, b: dict) -> List[str]:
    """Divergences lisibles entre deux snapshots (a = attendu/live, b = obtenu/Python)."""
    out: List[str] = []
    if a.get("currentPlayer") != b.get("currentPlayer"):
        out.append(f"currentPlayer: {a.get('currentPlayer')} != {b.get('currentPlayer')}")
    ta, tb = a.get("tiles"), b.get("tiles")
    if ta is not None and tb is not None:          # canal tuile fourni des DEUX côtés seulement
        for tid in sorted(set(ta) | set(tb)):
            if ta.get(tid) != tb.get(tid):
                out.append(f"tile{tid}.effects: {ta.get(tid)} != {tb.get(tid)}")
    ua, ub = a.get("units") or {}, b.get("units") or {}
    for uid in sorted(set(ua) | set(ub)):
        ca, cb = ua.get(uid), ub.get(uid)
        if ca is None:
            out.append(f"u{uid}: absente à gauche"); continue
        if cb is None:
            out.append(f"u{uid}: absente à droite"); continue
        for k in ("visualId", "alive", "team", "pos", "hp", "hpMax", "effects"):
            if ca.get(k) != cb.get(k):
                out.append(f"u{uid}.{k}: {ca.get(k)} != {cb.get(k)}")
    return out
