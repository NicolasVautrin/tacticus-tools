"""FEUILLES d'effet à EFFET du namespace natif `IdunBattle.Entities.Behaviours.*`, RUNNER-COUPLÉES, +
builder de contexte `entities_from_state` (#149).

Contenu = les `*Behaviour` CONCRETS qui MUTENT l'état en émettant une runner Operation déjà portée :
`Spawn` (`SpawnUnitBehaviour` @180fd5ab0 → `_spawn_config_grot`), `AttackWithAbilityDamage`
(`AttackBehaviour`/`AttackDamageBehaviour` @180fba0e0 → `AttackDamageOperation.execute_ability_attack`),
`AddEffect` (`AddEffectBehaviour` @180f947e0 → `AddEffectOperation`), `AddBondEffect`
(`AddBondEffectBehaviour` → idem), `PerformAIAttack` (`PerformAIAbilityUnitBehaviour` @180fcb940). Couche
MINCE d'orchestration au-dessus des mutateurs ECS.

Ils vivent ICI (et non dans `entities/behaviours.py` avec les COMBINATEURS purs `Seq`/`Maybe`/`Foreach`/
`If`/`AtomicGroup`, MÊME namespace natif `Entities.Behaviours`) parce qu'ils sont RUNNER-COUPLÉS (appellent
des Operations de `runner/`, que `entities/` ne peut importer sans inverser le layering). Le split
entities/runner = layering, PAS le namespace natif.

Ce fichier ne contient QUE des `Entities.Behaviours` :
- Les COMBINATEURS purs → `engine/entities/behaviours.py`.
- Les SÉLECTEURS/FORMULES (`Children`=`AllAliveMachinesSelector`, `LastUnitAttackedBy`=`LastUnitAttackedBy
  Selector`, `TotalAttacksMade`/`UnitTurnsStarted`=`*Formula`) → `entities/selectors.py` + `entities/formulas.py`
  (leur vrai namespace `Entities.Selectors`/`Formulas`).
- Les ARBRES d'ability SPÉCIFIQUES (`thunderous_assault_tree`/`getemruntz_tree`…) → `abilities/loki.py`
  (namespace natif `Abilities.Active.Loki`, avec leur classe d'ability).

`entities_from_state` construit le `DslContext` (= l'`entities` natif lu par les sélecteurs) depuis le
`State` runner. cf. docs/rl/dsl-effect-nodes.md.
"""
from __future__ import annotations

from ...dsl.base import DslContext, TargetsSelector, resolve_unit
from ...dsl.effects import AbilityBehaviour, OperationResult
from ..components import (OwnerComponent, PositionComponent, UnitComponent, StatsComponent,
                          HealthComponent)
from .base import turns_from_rounds, ability_attack_params
from ...entities.traits.unit_trait import UnitTrait, has_trait

def _unit_dict(state, eid: int, entity=None) -> dict | None:
    """Dict d'unite {id, team, player, pos, alive, hp, visualId, _traits} lu du `State` runner — la forme
    `unit` que consomment les selecteurs DSL. `entity` optionnel (evite un `get_entity` redondant)."""
    e = entity if entity is not None else state.get_entity(eid)
    if e is None:
        return None
    oc = e.get_component(OwnerComponent)
    pc = e.get_component(PositionComponent)
    uc = e.get_component(UnitComponent)
    sc = e.get_component(StatsComponent)
    hc = e.get_component(HealthComponent)
    traits = set(getattr(sc.ctx, "traits", None) or ()) if sc is not None else set()
    alive = uc.alive if uc is not None else True
    return {
        "id": eid,
        "team": oc.team if oc is not None else None,
        "player": oc.player if oc is not None else None,
        "pos": {"col": pc.col, "row": pc.row} if pc is not None else None,
        "alive": alive,
        "hp": hc.hp if hc is not None else (1 if alive else 0),
        "visualId": uc.visual_id if uc is not None else None,
        "_traits": traits,
    }


def entities_from_state(state, caster_id: int, target_id: int | None = None) -> DslContext:
    """Construit l'`AbilityEntities` (= `DslContext`) lu par les selecteurs d'un behaviour, depuis le
    `State` runner : `units` = dicts (cf. `_unit_dict`), `caster`, `target` (cible principale du cast =
    `factory+0x178`, lu par `Target()` — None si l'ability est sans cible), `board` (= `state.board`),
    `has_trait(unit, traitId)` (mirror `UnitExtensions.HasFlag`, via l'enum `UnitTrait` + le set de noms
    `ctx.traits`). `children=[]` = accumulateur de spawn FRAIS pour CE cast (mirror factory+0x148)."""
    units: list = []
    caster = None
    target = None
    for eid, e in state.entities.items():
        u = _unit_dict(state, eid, e)
        units.append(u)
        if eid == caster_id:
            caster = u
        if target_id is not None and eid == target_id:
            target = u

    def _has_trait(unit, trait_id):
        try:
            enum = UnitTrait(int(trait_id))
        except ValueError:
            return False
        return has_trait(unit.get("_traits") or set(), enum)

    # `ctx.faction_of` (mirror `UnitsFromFaction`) — FactionId gameconfig par visualId (`_faction` caché).
    # Lazy import (garde anti-circulaire, comme les Operations importées dans les feuilles).
    from ...ai.action_generators import _faction

    def _faction_of(unit):
        return _faction((unit or {}).get("visualId"))

    return DslContext(units=units, caster=caster, target=target, board=state.board,
                      has_trait=_has_trait, faction_of=_faction_of, children=[])


class Spawn(AbilityBehaviour):
    """`DSLFactory.Spawn @180dfbd50` -> `SpawnUnitBehaviour.Execute @180fd3d80` : itere son TILE-SELECTEUR
    EN INTERNE (mirror natif -- le `Spawn` n'est PAS un `Foreach(tiles, SpawnUnit)` externe, il enumere ses
    tuiles lui-meme) et spawn UNE unite par tuile, stats `WithStatsFromConfig(summon_ability)`, owner =
    team+player du caster. Wrapper au-dessus de l'Operation portee `_spawn_config_grot` (mirror de l'inline natif
    `GetEmRuntzAbility.ExecuteBehaviour @1811e2210`) : level/mult lus du `StatsComponent` du caster dans `ectx.state`. Chaque enfant
    est AJOUTE a `entities.children` (accumulateur factory+0x148, relu par `Children` pour le Taunt), annote
    pour le Taunt (`_new_child`/`_turns_started`/`_attacks_made`/`_last_attacked`). L'ordre d'enumeration =
    l'ordre du tile-selecteur (le `Cache` partage) -> `children` en ordre de TUILE (== l'ordre que
    `PerformAIAttack` reparcourt). Effet PUR (`stop=False`) ; journalise chaque spawn."""
    __slots__ = ("tile_selector", "summon_ability")

    def __init__(self, tile_selector: TargetsSelector, summon_ability: str):
        self.tile_selector, self.summon_ability = tile_selector, summon_ability

    def execute(self, entities, ectx):
        import gameconfig as GC
        from ..operations.spawn import _spawn_config_grot
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        ce = state.get_entity(caster_id) if (state is not None and caster_id is not None) else None
        if ce is None:
            return OperationResult.ok()
        oc = ce.get_component(OwnerComponent)
        sc = ce.get_component(StatsComponent)
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        vid = ((GC.ability(self.summon_ability) or {}).get("constants") or {}).get("unitId")
        for tile in (self.tile_selector.evaluate(entities) or []):   # itere les tuiles EN INTERNE (natif)
            gid = _spawn_config_grot(state, vid, tile, self.summon_ability, level, mult,
                                     oc.team if oc is not None else None,
                                     oc.player if oc is not None else None)
            if gid is not None:
                child = _unit_dict(state, gid) or {"id": gid}
                child.update({"_new_child": True, "_turns_started": 0, "_attacks_made": 0,
                              "_last_attacked": None})
                entities.children.append(child)       # accumulateur factory+0x148 (relu par Children)
                ectx.emit("SpawnUnit", tile=tile, unit=gid)
        return OperationResult.ok()


class PerformAIAttack(AbilityBehaviour):
    """`DSLFactory.PerformAIAttackFromCurrentPosition(Cache(GetSpawnTileSelector)) @180df8a10` ->
    `PerformAIAbilityUnitBehaviour.Execute @180fcb070` : chaque unite SUR les tuiles du SELECTEUR (le natif
    reutilise le MEME `Cache(GetSpawnTileSelector)` que le `Spawn` -> les grots tout juste spawnes) execute
    une attaque AI depuis SA position COURANTE (sans bouger). Port : `tile_selector` = le `Cache` PARTAGE
    (memoise -> memes tuiles PRE-spawn que le Spawn, sinon `CanAddUnit` recalcule les exclurait car
    occupees) ; on parcourt ses tuiles DANS L'ORDRE, on mappe chacune au grot pose dessus (`entities.children`,
    populate par le `Spawn` en ORDRE DE TUILE -> l'ordre d'attaque == l'ordre natif == l'ordre RNG), et il
    attaque l'ennemi le plus proche via `AttackDamageOperation.execute` (approx du choix AI natif,
    confront live #200 tracer-v2 DSLFactory). Annote le dict enfant (`_attacks_made`,
    `_last_attacked` = dict FRAIS post-attaque) pour les predicats du Taunt. Emet 'PerformAIAttack'. PUR."""
    __slots__ = ("tile_selector",)

    def __init__(self, tile_selector: TargetsSelector):
        self.tile_selector = tile_selector

    def execute(self, entities, ectx):
        from .loki import _nearest_enemy
        from ..operations.damage import AttackDamageOperation
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        board = getattr(state, "board", None)

        def _child_on_tile(tid):                       # grot pose sur la tuile (via sa pos capturee au spawn)
            for c in (entities.children or []):
                p = c.get("pos")
                if p and board is not None and board.id_at(p["col"], p["row"]) == tid:
                    return c
            return None

        attacks: list = []
        for tid in (self.tile_selector.evaluate(entities) or []):   # tuiles du Cache, ORDRE natif (= spawn)
            child = _child_on_tile(tid)
            if child is None:
                continue
            cid = child.get("id")
            tgt = _nearest_enemy(state, cid)
            if tgt is None:
                continue
            r = AttackDamageOperation.execute(state, cid, tgt)
            if r is None:
                continue
            child["_attacks_made"] = int(child.get("_attacks_made", 0) or 0) + 1
            child["_last_attacked"] = _unit_dict(state, tgt)   # etat POST-attaque (alive/hp courants)
            attacks.append({"child": cid, "target": tgt, "total": r.get("total")})
        ectx.emit("PerformAIAttack", attacks=attacks)
        return OperationResult.ok()


class AddBondEffect(AbilityBehaviour):
    """`DSLFactory.AddBondEffect(0x1b, stateRef, source, target, ..., TurnsFromRounds(1)) @1811e27a0` : pose
    l'effet BOND `Taunted_OnlySpecificTargets` (0x1b=27, COMPOSITE 25/26/1237) reliant `source` (l'enfant/
    grot) et `target` (`LastUnitAttackedBy` = l'ennemi frappe), duree `TurnsFromRounds(rounds)`. Wrapper
    MINCE au-dessus de `AddEffectOperation.execute` (mirror exact de l'imperatif : source=grot, target=
    ennemi). `source_ref`/`target_ref` = Nodes resolus au dict courant -> ids. No-op si source/target
    absents. Emet 'AddBondEffect'. Effet PUR (stop=False)."""
    __slots__ = ("effect_type", "name", "source_ref", "target_ref", "duration_rounds")

    def __init__(self, effect_type: int, name: str, source_ref: TargetsSelector, target_ref: TargetsSelector,
                 duration_rounds: int = 1):
        self.effect_type, self.name = effect_type, name
        self.source_ref, self.target_ref = source_ref, target_ref
        self.duration_rounds = duration_rounds

    def execute(self, entities, ectx):
        from ..operations.effects import AddEffectOperation
        su = resolve_unit(self.source_ref, entities)
        tu = resolve_unit(self.target_ref, entities)
        src = su.get("id") if su else None
        tgt = tu.get("id") if tu else None
        if src is None or tgt is None or ectx.state is None:
            return OperationResult.ok()
        AddEffectOperation.execute(ectx.state, source=src, target=tgt, effect_type=self.effect_type,
                                   name=self.name, duration_override=turns_from_rounds(self.duration_rounds))
        ectx.emit("AddBondEffect", source=src, target=tgt, effect_type=self.effect_type)
        return OperationResult.ok()


class AttackWithAbilityDamage(AbilityBehaviour):
    """`DSLFactory.AttackWithAttackDamage @180de9fb0` -> `AttackDamageBehaviour`+`AttackBehaviour.Execute` :
    l'attaque d'une ability (bornes `MinMaxDamage(minDmg/maxDmg[level])`, profil `GetDamageProfile`, nb de
    coups `GetNumberConstant(0x2f)=nrOfHits`) portee sur la cible. Wrapper MINCE au-dessus de l'Operation
    DEJA bit-exact `AttackDamageOperation.execute_ability_attack` (meme pipeline reduce/crit/block/after-hit
    que l'imperatif) : `caster` = `ctx.caster`, `target` = `target_sel` (dict d'unite), et
    `(base_min,base_max,pierce,hits)` via `ability_attack_params(ability_id, profile)` — MEME source que
    l'imperatif -> bit-exact BY CONSTRUCTION (memes args, meme `state.rng`).

    ⚠ Le ciblage natif complet = `Units(Cache(First(Nearest(Tiles(target_ctx), casterPos))))` : pour une
    ability MONO-cible melee (ThunderousAssault) il COLLAPSE en la cible du message (`ctx.target`) — que
    l'IA/caller a deja choisie (== l'imperatif live-valide). La chaine Tiles->Nearest->First->Cache->Units
    n'est materialisee que si une ability re-derive sa cible (differe). Emet 'AttackWithAbilityDamage'. PUR.

    `min_key`/`max_key`/`hits_key` = cles config du volet de degat (defaut `minDmg`/`maxDmg`/`nrOfHits` =
    `MinMaxDamage`/`GetDamageProfile`/`GetNumberConstant(0x2f)`) ; une ability a DEUX volets (ex. CrushingClaws
    principal vs splash) passe le 2e jeu (`minDmg_2`/`maxDmg_2`/`nrOfHits_2` = `MinMaxDamage2`/`GetDamageProfile2`
    /`GetNumberConstant(0x32)`).

    `damage_override` = callable `(state, caster, target, bmin, bmax) -> (bmin, bmax)` mirror d'un
    `AActiveAbility.GetAttackDamage` SURCHARGE par-ability (le natif passe la node de degat calculee a
    `AttackWithAbilityDamage` — cf. `SpiritLeech.GetAttackDamage @181209dd0` = ConditionalAmount(cible Pinned
    -> +extraDmg)). Defaut None = degat generique `MinMaxDamage` (bornes config brutes) ; sinon le callable
    ajuste (bmin,bmax) APRES `ability_attack_params`, AVANT le tirage per-coup."""
    __slots__ = ("target_sel", "ability_id", "profile", "is_melee", "min_key", "max_key", "hits_key",
                 "damage_override")

    def __init__(self, target_sel: TargetsSelector, ability_id: str, profile: str, is_melee: bool = True,
                 min_key: str = "minDmg", max_key: str = "maxDmg", hits_key: str = "nrOfHits",
                 damage_override=None):
        self.target_sel, self.ability_id, self.profile, self.is_melee = target_sel, ability_id, profile, is_melee
        self.min_key, self.max_key, self.hits_key = min_key, max_key, hits_key
        self.damage_override = damage_override

    def execute(self, entities, ectx):
        from ..operations.damage import AttackDamageOperation
        state = ectx.state
        caster = (entities.caster or {}).get("id")
        tu = resolve_unit(self.target_sel, entities)
        tgt = tu.get("id") if tu else None
        if state is None or caster is None or tgt is None:
            return OperationResult.ok()
        bmin, bmax, pierce, hits = ability_attack_params(
            state, caster, self.ability_id, self.profile, ranged=not self.is_melee,
            min_key=self.min_key, max_key=self.max_key, hits_key=self.hits_key)
        if self.damage_override is not None:               # GetAttackDamage surchargee (ex. SpiritLeech +extraDmg)
            bmin, bmax = self.damage_override(state, caster, tgt, bmin, bmax)
        atk = AttackDamageOperation.execute_ability_attack(
            state, caster, tgt, bmin, bmax, pierce, hits,
            damage_profile=self.profile, is_melee=self.is_melee)
        ectx.emit("AttackWithAbilityDamage", caster=caster, target=tgt,
                  total=(atk or {}).get("total"), attack=atk)
        return OperationResult.ok()


class AddEffect(AbilityBehaviour):
    """`DSLFactory.AddEffect @180de6d20` -> `AddEffectBehaviour.Execute` : pose un effet sur la cible, avec
    `source` = `AbilityStateReference` (= le caster comme source de l'effet), `target` = `target_sel`, duree
    `TurnsFromRounds(rounds)`. Wrapper MINCE au-dessus de `AddEffectOperation.execute` (mirror exact de
    l'imperatif). DIFFERE de `AddBondEffect` (qui LIE source+target = deux unites distinctes) : ici la source
    EST le caster. No-op si caster/target absents. Emet 'AddEffect'. Effet PUR (stop=False).

    `duration_rounds` = nb de rounds (`TurnsFromRounds(rounds)`) ; `None` = duree DEFAUT de l'effet
    (`DefaultAmountOfRounds`, mirror de l'arg natif `0` d'`AddEffect` SANS `TurnsFromRounds` — ex. Pinned de
    CrushingClaws) vs explicite (ThunderousAssault Stunned = `TurnsFromRounds(1)`)."""
    __slots__ = ("effect_type", "name", "target_sel", "duration_rounds")

    def __init__(self, effect_type: int, name: str, target_sel: TargetsSelector, duration_rounds=1):
        self.effect_type, self.name = effect_type, name
        self.target_sel, self.duration_rounds = target_sel, duration_rounds

    def execute(self, entities, ectx):
        from ..operations.effects import AddEffectOperation
        state = ectx.state
        src = (entities.caster or {}).get("id")               # AbilityStateReference = caster (source)
        tu = resolve_unit(self.target_sel, entities)
        tgt = tu.get("id") if tu else None
        if state is None or src is None or tgt is None:
            return OperationResult.ok()
        # duration_rounds None -> pas d'override = duree DEFAUT (DefaultAmountOfRounds), mirror de l'arg natif
        # `0` d'AddEffect sans TurnsFromRounds (Pinned CrushingClaws) ; sinon TurnsFromRounds(rounds).
        dur = turns_from_rounds(self.duration_rounds) if self.duration_rounds is not None else None
        AddEffectOperation.execute(state, source=src, target=tgt, effect_type=self.effect_type,
                                   name=self.name, duration_override=dur)
        ectx.emit("AddEffect", source=src, target=tgt, effect_type=self.effect_type)
        return OperationResult.ok()


class Heal(AbilityBehaviour):
    """`DSLFactory.Heal(source, targets, amount) @...` -> `HealBehaviour.Execute` : soigne CHAQUE unite du
    selecteur `targets_sel` de `amount_fn(entities, ectx)` PV, via l'Operation portee `HealUnitOperation.
    execute` (mutation PV, plafond `hp_max`, gate `Cursed`). Wrapper MINCE au-dessus du mutateur ECS (mirror
    du 3e volet de `SpiritLeech.ExecuteBehaviour` = lifesteal). Le montant est calcule UNE fois par
    `amount_fn` = FOLD du `SetCache(PercentageOf(LastAttackDamageMade, ...))` natif (le Heal natif lit un
    montant CACHE derive de la derniere attaque ; l'`amount_fn` nommee (mirror `GetHealAmountForExecution`)
    le recompute en lisant le total de la derniere `AttackWithAbilityDamage` dans `ectx.emitted`). `source`
    de soin = `ctx.caster`. No-op si montant <= 0. Emet 'Heal' (amount + heals=[{target, healed}]). PUR."""
    __slots__ = ("targets_sel", "amount_fn")

    def __init__(self, targets_sel: TargetsSelector, amount_fn):
        self.targets_sel, self.amount_fn = targets_sel, amount_fn

    def execute(self, entities, ectx):
        from ..operations.heal import HealUnitOperation
        state = ectx.state
        amount = int(self.amount_fn(entities, ectx) or 0)
        heals: list = []
        if state is not None and amount > 0:
            src = (entities.caster or {}).get("id")
            for u in (self.targets_sel.evaluate(entities) or []):
                tid = u.get("id") if isinstance(u, dict) else None
                if tid is None:
                    continue
                healed = HealUnitOperation.execute(state, tid, amount, source_id=src)
                heals.append({"target": tid, "healed": healed})
        ectx.emit("Heal", amount=amount, heals=heals)
        return OperationResult.ok()
