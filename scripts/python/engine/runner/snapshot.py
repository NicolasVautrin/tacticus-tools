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

from typing import Dict, List, Optional, Tuple

from .state import State
from .components import (
    UnitComponent, OwnerComponent, PositionComponent, HealthComponent,
    EffectsOwnedComponent, StatsComponent, ShieldComponent, ShieldInstance,
    TriggeredAbilityComponent, MachineComponent, ActiveAbility, ActiveAbilitiesComponent,
    UnitFlagsComponent,
    set_unit_feet,
)


# `EntityType.Machine` — l'enum d'entité du `MatchState` natif, projeté tel quel par les capteurs
# (`frida/hooks/game/match-state.ts` : `Tile:0, Unit:1, Match:2, Effect:3, Player:4, UnitFoot:5,
# Machine:6, MachinePlatform:7`). C'est le DISCRIMINANT exact « cette ligne est une MoW » dans
# `combatSnapshot.units[]` / `statModSources.units[]`, qui remontent les DEUX types depuis `d9d0008`
# (#128 « lot ATELIER VIDE »). ⚠ Le commentaire du hook lui-même dit « Machine INCLUSE (#93) » — #93
# est la tâche SpiritLeech, PAS le commit qui a élargi le filtre. Ne pas recopier cette attribution :
# elle a déjà induit en erreur (`git log -S "EntityType.Machine" -- <le hook>` tranche).
_ENTITY_TYPE_MACHINE = 6


def _hp_by_id(observe: dict) -> Dict[int, Tuple[Optional[int], Optional[int]]]:
    """hp/hpMax par id d'UNITÉ (squadId == decisionView.id). PAS entityId."""
    out: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
    for u in (observe.get("units") or []):
        uid = u.get("squadId")
        if uid is not None:
            out[uid] = (u.get("hp"), u.get("hpMax"))
    return out


def decision_view_seed_body(runner_id: int, **extra) -> dict:
    """Corps du RPC `decisionView` **destiné au SEED** de `load_state` — la porte NOMMÉE du canal
    `includeInactive`, à passer telle quelle à n'importe quel wrapper RPC
    (`rpc("decisionView", decision_view_seed_body(rid, allAbilities=True))`).

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


def _effect_names(u: dict) -> List[str]:
    """Noms d'effets ACTIFS de la ligne — la vue NOMS d'`EffectsOwnedComponent` (diff structurel).

    Le filtre sur `active` rend cette vue INDÉPENDANTE du canal de capture : une ligne venue de
    `decisionView` par défaut et la même ligne venue de `decision_view_seed_body` produisent la MÊME
    liste. C'est ce qui permet de seeder par le canal `includeInactive` sans qu'un
    `diff(snapshot_live(...), snapshot(state))` dont les deux côtés n'ont pas été captés par le même
    canal ne signale des écarts fantômes. Les inertes ne sont pas perdus : ils vivent dans le canal
    STRUCTURÉ `State.effects.by_unit`, avec leur flag (cf. `EffectFactory.create`).
    Clé `active` absente (canal par défaut) → l'entrée est active par construction."""
    return sorted(n for n in (e.get("name") for e in (u.get("effects") or [])
                              if e.get("active") is not False) if n)


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
               board=None, tiles=None, actor_stats=None) -> State:
    """Snapshot live → `State` ECS (entités + composants d'unité).

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
    inchangé (les compteurs restent à 0, comme un composant natif frais)."""
    state = State()
    state.current_player_id = decision.get("currentPlayer")
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
    hp_by_id = _hp_by_id(observe)
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
    if snapshot is not None:
        # AVANT les stats : `UnitFlag.Moved`/`Teleported` sont des entrees de GATE lues par le calcul
        # de degat (`attacker_modifiers` -> `unit_has_moved`), pas des sorties -- cf. `_load_unit_flags`.
        _load_unit_flags(state, snapshot)
        # MEME nature que les flags : trois champs d'ETAT DE TOUR du `UnitComponent` (dont le
        # compteur `turnsFinished` que lit `OwnerHasFinishedMinTurns`), entrees de gate et non
        # sorties -- cf. `_load_unit_turn_state`.
        _load_unit_turn_state(state, snapshot)
        _load_stats_and_effects(state, decision, snapshot)
        # APRES les stats : le substrat de traits vit dans `UnitContext.traits`, que
        # `_load_stats_and_effects` vient de construire (unites ET MoW). Meme nature que les deux
        # seeds ci-dessus -- une ENTREE de gate que rien ne peuplait sur un etat recharge, le port
        # la RECONSTRUISANT depuis gameconfig au lieu de lire la source -- cf. `_load_unit_traits`.
        _load_unit_traits(state, snapshot)
    # MEME nature que les deux seeds ci-dessus, mais son canal est un RPC DISTINCT (`actorStats`,
    # pas `combatSnapshot`) -> il est gate par son propre argument, jamais par `snapshot`.
    if actor_stats is not None:
        _load_actor_statistics(state, actor_stats)
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
    from .operations.aura_stat_mods import attribute_aura_stat_modifiers
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
    from ..entities import UnitContext, EffectFactory

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
    un `UnitFlagsComponent`, cf. `dumpEntityComponents`). Champ absent (capteur plus ancien) ou liste
    vide -> AUCUN composant pose = flag absent = « n'a pas bouge », soit exactement le comportement
    anterieur : la degradation reste retro-compatible."""
    for su in (snapshot.get("units") or []):
        eid = su.get("entityId")
        flags = su.get("unitFlags")
        if eid is None or not isinstance(flags, list) or not flags:
            continue
        ent = state.get_entity(eid)
        if ent is None:
            continue
        fl = ent.get_component(UnitFlagsComponent)
        if fl is None:
            fl = ent.add_component(UnitFlagsComponent())
        for f in flags:
            try:
                fl.add(int(f))
            except (TypeError, ValueError):
                continue


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


def _load_actor_statistics(state: State, actor_stats: dict) -> None:
    """Seede les TROIS compteurs de tuiles parcourues du `UnitComponent` depuis le RPC `actorStats`
    (`#340-r1`).

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
    comportement d'avant, a l'identique. Un `0` publie est un vrai zero (l'unite n'a pas bouge)."""
    for su in ((actor_stats or {}).get("units") or []):
        uid = su.get("entityId")
        if uid is None:
            continue
        ent = state.get_entity(uid)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None:
            continue
        for key, attr in (("tilesMovedThisBattle", "tiles_moved_this_battle"),
                          ("tilesMovedThisTurn", "tiles_moved_this_turn"),
                          ("tilesMovedLastTurn", "tiles_moved_last_turn")):
            v = su.get(key)
            if v is not None:
                setattr(uc, attr, int(v))


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
    from ..entities.traits.unit_trait import trait_names_from_ids

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


def _load_stats_and_effects(state: State, decision: dict, snapshot: dict) -> None:
    """Peuple `StatsComponent` (par unité) + `State.effects` (EffectsState matérialisé)
    depuis `combatSnapshot` + `decisionView`. Jointure : `combatSnapshot.entityId` ==
    `decisionView.id` (== id d'unité ECS, cf. en-tête). Mirror de la chaîne validée
    `predict_validate.build_samples` (UnitContext.from_snapshot + EffectsState.seed).

    ⚠ `combatSnapshot.units[]` porte DEUX `entityType` (`d9d0008`/#128) : les `Unit` (jointes à
    `decisionView.units[].id`) et les `Machine` (jointes à `decisionView.mows[].casterId`). La boucle
    ci-dessous ne traite QUE les premières ; les MoW sont déléguées à `_load_machine_stats` — elles
    n'ont ni `unitConfig` ni VisualId sur cette ligne, et leur niveau vit ailleurs (#174)."""
    import gameconfig as GC                      # données offline (traits/arme/profil)
    from ..entities import UnitContext, EffectsState, EffectFactory

    vis_by_id = {u.get("id"): u.get("visualId") for u in (decision.get("units") or [])}
    effects_by_id = {u.get("id"): (u.get("effects") or []) for u in (decision.get("units") or [])}
    # Les MoW portent des effets (`EffectsOwnedComponent` natif — mesuré : `HeavyRailRifle_
    # PendingAttack` se pose sur l'entité Machine) -> elles entrent dans le seed `EffectsState`
    # au même titre que les unités.
    for _m in _machine_rows(decision):
        effects_by_id[int(_m["casterId"])] = _m.get("effects") or []
    mult_by_id: Dict[int, int] = {}
    ablvl_by_id: Dict[int, Optional[int]] = {}
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
        # mult/ablvl captés EARLY. ⚠ Pour un buff CROSS-UNITÉ (ex. RitesOfBattle), le niveau exact
        # est celui du SOURCE, absent de la capture → on utilise l'ablvl de l'unité PORTEUSE ; le
        # RÉSIDU opaque absorbe l'écart, `get_stat(Current)` reste EXACT (zéro régression).
        _has_mult = isinstance(uc, dict) and uc.get("abilityVariablesMultiplier") is not None
        _emult = int(uc["abilityVariablesMultiplier"]) if _has_mult else 100
        _eablvl = int(uc["passiveAbilityLevel"]) if (_has_mult and uc.get("passiveAbilityLevel")) else None
        _eactive = int(uc["activeAbilityLevel"]) if (_has_mult and uc.get("activeAbilityLevel")) else None
        _effs = EffectFactory.create_many(effects_by_id.get(eid) or [], _emult, _eablvl, _eactive)
        ctx = UnitContext.from_snapshot(su, GC.unit(vis or ""), snapshot.get("statTypes"), _effs)
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
    state.effects = EffectsState.seed(effects_by_id, mult_by_id, ablvl_by_id)
    # `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` (boucle ABILITIES) : à la création de CHAQUE
    # unité, l'owner-effect posé par le `CreateBehaviour` de ses abilities (DSL `AddEffect(owner)`). Le
    # SEED live (decisionView.effects) ne capte QUE les effets ACTIFS à l'instant T -> il RATE les
    # owner-effects passifs INACTIFS au capture (ex. HP-floor `HypersensoryAbilities_MinimalHealth` de Judh,
    # actif seulement au tour ENNEMI via son ActiveCondition). On les pose ici (idempotent : les effets déjà
    # captés live sont skippés). Gate TeleportingIn (1035) : passives DIFFÉRÉES jusqu'à l'atterrissage
    # (`land_deep_strike`), pas initialisées au capture. #G6a.
    from .operations.spawn import _seed_ability_owner_effects, TELEPORT_STRIKE_TELEPORTING_IN
    for eid in list(state.entities.keys()):
        if state.effects.has_effect(eid, effect_type=TELEPORT_STRIKE_TELEPORTING_IN):
            continue
        ent = state.get_entity(eid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if sc is None or uc is None or not uc.visual_id:
            continue
        _seed_ability_owner_effects(state, eid, uc.visual_id,
                                    int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100),
                                    ability_level=getattr(sc.ctx, "passive_ability_level", None))


def _source_ability_state(state: State, source_id) -> Tuple[int, Optional[int], Optional[int]]:
    """`(multiplier, passiveAbilityLevel, activeAbilityLevel)` de l'unité SOURCE d'un effet.

    Le natif BAKE l'`AbilityStateReference` (`EffectComponent.AbilityState`) à la CRÉATION de
    l'effet, depuis l'ability qui le pose — donc depuis la SOURCE, pas depuis le porteur. Pour
    un effet d'UNITÉ le port approxime avec le `unitConfig` du PORTEUR (résidu documenté dans
    `_load_stats_and_effects`) ; une TUILE n'a AUCUN `unitConfig`, donc il n'y a rien à
    approximer : on lit le canal exact, le `StatsComponent.ctx` de la source
    (`EffectComponent.SourceUnitId` = le champ `source` du capteur). Source inconnue/non chargée
    (posée par une unité morte et retirée de la capture, ou par l'environnement) → neutre
    (100, None, None), MÊME défaut que `EffectFactory.create`."""
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
    from ..entities import EffectsState, EffectFactory

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
