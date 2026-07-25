"""État initial (chargé depuis le LIVE) + forme canonique diffable + diff.

Stratégie tranche 0 (cf. docs/rl/runner-engine.md §2.0) : l'état initial du runner
Python est CHARGÉ depuis un snapshot live du runner fraîchement bâti (vérité-terrain) ;
le runner reproduit ensuite l'ÉVOLUTION (operations). Le port complet BC→Initialize
(indépendance totale) est différé.

  • `load_state(decision, observe)` : snapshot live (decisionView + observeBattle) →
    `State` ECS (entités + composants). Charge les UNITÉS (`decisionView.units`) **et les
    MACHINES OF WAR** (`decisionView.mows`, cf. `_load_machines`).
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
    TriggeredAbilityComponent, MachineComponent,
)


def _hp_by_id(observe: dict) -> Dict[int, Tuple[Optional[int], Optional[int]]]:
    """hp/hpMax par id d'UNITÉ (squadId == decisionView.id). PAS entityId."""
    out: Dict[int, Tuple[Optional[int], Optional[int]]] = {}
    for u in (observe.get("units") or []):
        uid = u.get("squadId")
        if uid is not None:
            out[uid] = (u.get("hp"), u.get("hpMax"))
    return out


def _effect_names(u: dict) -> List[str]:
    return sorted(n for n in (e.get("name") for e in (u.get("effects") or [])) if n)


def _machine_rows(decision: dict) -> List[dict]:
    """Lignes MoW exploitables de `decisionView.mows` (`projectMowsFull`, ai-step/projection.ts).
    Clé ECS = `casterId` (== `machineId`, l'entité **Machine** Type=6) — c'est l'id que
    `applyAction {kind:"ability", casterId}` et `abilityTargets{unitId}` attendent ; le `id` de la
    ligne est la PLATEFORME (Type=7), qui n'est pas l'acteur."""
    return [m for m in (decision.get("mows") or []) if m.get("casterId") is not None]


def _machine_ability_state(m: dict) -> tuple:
    """(level, multiplier) de la MoW = `AbilityState` PER-ABILITY (`ActiveAbility._abilityState` :
    `Level`@+0 / `VariableMultiplierPercentage`@+4, lu par `readAbilityState` — mirror de
    `get_AbilityState @180f8fc40`, l'override primant). C'est CE canal qui indexe les variables
    config (minDmg/maxDmg/nrOfHits/summonHp…) des abilities de la MoW ; elle n'a pas d'équivalent
    `BattleQuery.GetUnitConfig` (la clé du registre est une VisualId d'unité).
    On prend la 1re active portant un état ; défaut (0, 100) = neutre."""
    for ab in (m.get("abilities") or []):
        if ab.get("level") is not None or ab.get("multiplier") is not None:
            return (int(ab.get("level") or 0), int(ab.get("multiplier") or 100))
    return (0, 100)


def load_state(decision: dict, observe: dict, snapshot: Optional[dict] = None,
               board=None) -> State:
    """Snapshot live → `State` ECS (entités + composants d'unité).

    `snapshot` (combatSnapshot) optionnel : s'il est fourni, peuple en plus le
    `StatsComponent` (stats RÉSOLUES + arme normale, via `UnitContext`) de chaque unité
    ET `State.effects` (effets STRUCTURÉS matérialisés, `EffectsState`) — le runner peut
    alors calculer la plage de tirage lui-même. Sans `snapshot` : comportement tranche 0
    inchangé (identité/pos/HP/effets-NOMS uniquement).

    `board` (`engine.entities.pathfinding.board.Board`) optionnel : s'il est fourni, il
    est ASSIGNÉ à `state.board` (adjacence hex + élévation + terrain). Point d'injection
    UNIQUE du board — sans lui, les feuilles POSITIONNELLES du combat (bonus d'ELEVATION
    `CalculateElevationBonusModifier @181003ea0`, trench, LightCover, GetStuckIn) sont des
    no-op SILENCIEUX offline (cause racine #63 : un `state.board=` oublié dans un helper de
    replay). Passer le board ICI (au lieu d'un `state.board = board` dispersé après l'appel)
    rend l'omission structurellement impossible à un site donné. On accepte l'OBJET `Board`
    déjà construit (pas le boardGraph brut) car son mode d'adjacence (`evenq`/`native_sym`)
    est CONSOMMÉ par le moteur (`neighbours`/`are_tiles_adjacent`/splash) et varie selon les
    appelants : préserver l'objet exact = préserver le mode = zéro régression. L'assignation
    est faite en TOUTE FIN (après `_load_stats_and_effects`) → strictement équivalente à un
    `state.board = board` post-retour (l'init/seed ne lit jamais `state.board`)."""
    state = State()
    state.current_player_id = decision.get("currentPlayer")
    # #90 — FACTEUR rounds->turns (`BattleQuery.ConvertRoundsToTurns @181058af0` = `count(joueurs du
    # turnOrder, PlayerType != 2) * rounds`). `observeBattle.counts.player` = le nb d'entites Player
    # PROJETEES (EntityType 4) ; le joueur **Environment** (`PlayerType == 2`) est unique et permanent
    # dans toute BC (cf. modele des summons : pas de 3e team, Environment = 0 unite) -> non-Environment
    # = `counts.player - 1`. MESURE (runner MoW C1_02) : counts.player=3 -> 2, et
    # `TurnsFromRounds(1)` d'une ability MoW rend bien `remaining = 2` live.
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
    _load_machines(state, decision)
    if snapshot is not None:
        _load_stats_and_effects(state, decision, snapshot)
    # Board assigné en DERNIER (cf. docstring) : identique à un `state.board = board` que
    # l'appelant aurait posé après le retour de load_state — l'init/seed n'a jamais lu le board.
    if board is not None:
        state.board = board
    return state


def _load_machines(state: State, decision: dict) -> None:
    """MACHINES OF WAR -> entités ECS — mirror de `AddMachineOperation.Execute @180e4b5e0`.

    Le natif crée la MoW comme une entité de PREMIER PLAN (`EntityType.Machine` = 6, littéral `6`
    passé au factory d'entités @180e4b5e0), puis lie sa/ses `MachinePlatform` (Type=7) via
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
    vient des VARIABLES d'ability (`AActiveAbility.MinMaxDamage @180fb2dc0`), pas d'une stat d'unité.

    On pose donc, à l'identique de la boucle unités MAIS **sans PositionComponent ni
    HealthComponent** :
      • `UnitComponent` — porteur d'identité ; le natif a `MachineComponent`, mais les DEUX dérivent
        de `BaseUnitComponent @180f96380` (VisualId@0x20 valide sur les deux, cf. `projectSquadStats`)
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
        effs = _effect_names(m)
        if effs:
            e.add_component(EffectsOwnedComponent(effects=effs))


def _load_machine_stats(state: State, decision: dict, snapshot: dict,
                        mult_by_id: Dict[int, int]) -> None:
    """`StatsComponent` des MoW. `combatSnapshot` n'expose QUE `EntityType.Unit` (son `allUnits`
    filtre `ty === EntityType.Unit`), donc aucune stat RÉSOLUE de MoW n'est lisible par RPC. On bâtit
    le `UnitContext` par la MÊME chaîne que les unités (`UnitContext.from_snapshot`) avec un
    `snap_unit` SYNTHÉTIQUE sans bloc `stats` : les 8 stats de base sont alors seedées à 0, ce qui est
    la valeur gameconfig RÉELLE d'une MoW (`stats={Health:0,Damage:0,FixedArmor:0}`) — aucune valeur
    inventée. Le canal utile (et le seul que la MoW ait) = `active_ability_level` /
    `ability_variables_multiplier`, lus de l'`AbilityState` per-ability (cf. `_machine_ability_state`).

    RÉSIDU DOCUMENTÉ : une stat-modification de MoW POSÉE EN COURS DE COMBAT (la MoW a bien
    Attack/CritChance/CritDamage/ExtraHits/ExtraPierce*/ExtraMaxDamage) n'est pas captable tant que
    `combatSnapshot`/`statModSources` filtrent `EntityType.Unit` (changement `frida/hooks` requis) ;
    l'effet correspondant reste toutefois matérialisé dans `State.effects` (il vient de
    `decisionView.mows[].effects`), donc sa part déclarée est calculable offline.

    (Pas de `ablvl_by_id` : une MoW n'a AUCUNE passive en gameconfig — `passiveAbilities` absent sur
    les 8 MoW du pool — donc aucun niveau de passive à propager au seed d'effets.)"""
    import gameconfig as GC
    from ..entities import UnitContext, EffectFactory

    for m in _machine_rows(decision):
        mid = int(m["casterId"])
        ent = state.get_entity(mid)
        if ent is None or ent.get_component(StatsComponent) is not None:
            continue
        vis = m.get("visualId") or ""
        level, mult = _machine_ability_state(m)
        effs = EffectFactory.create_many(m.get("effects") or [], mult, None, level)
        ctx = UnitContext.from_snapshot(
            {"entityId": mid, "visualId": vis,
             "unitConfig": {"activeAbilityLevel": level, "abilityVariablesMultiplier": mult}},
            GC.unit(vis), snapshot.get("statTypes"), effs)
        ctx.ability_variables_multiplier = mult
        ctx.active_ability_level = level
        mult_by_id[mid] = mult
        ent.add_component(StatsComponent(ctx=ctx))


def _load_stats_and_effects(state: State, decision: dict, snapshot: dict) -> None:
    """Peuple `StatsComponent` (par unité) + `State.effects` (EffectsState matérialisé)
    depuis `combatSnapshot` + `decisionView`. Jointure : `combatSnapshot.entityId` ==
    `decisionView.id` (== id d'unité ECS, cf. en-tête). Mirror de la chaîne validée
    `predict_validate.build_samples` (UnitContext.from_snapshot + EffectsState.seed)."""
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
    # `InitializeActorAbilitiesOperation.Execute @180e74660` (boucle ABILITIES) : à la création de CHAQUE
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
    return {"currentPlayer": state.current_player_id, "units": units}


def snapshot_live(decision: dict, observe: dict) -> dict:
    """MÊME forme canonique, DIRECTEMENT depuis les RPC (chemin indépendant)."""
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
    return {"currentPlayer": decision.get("currentPlayer"), "units": units}


def diff(a: dict, b: dict) -> List[str]:
    """Divergences lisibles entre deux snapshots (a = attendu/live, b = obtenu/Python)."""
    out: List[str] = []
    if a.get("currentPlayer") != b.get("currentPlayer"):
        out.append(f"currentPlayer: {a.get('currentPlayer')} != {b.get('currentPlayer')}")
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
