"""Feuilles DSL de SPAWN/invocation : `Spawn` (`SpawnUnitBehaviour`), `PerformAIAttack`
(`PerformAIAbilityUnitBehaviour`), `SpawnSummon` (ScarabHive), `SpawnReplica` (ScarabSummon). Wrappers
MINCES au-dessus des Operations `runner/operations/spawn.py` + `damage.py`. Namespace natif
`Entities.Behaviours.*`. cf. docstring du package (`__init__.py`).

Toute attaque d'IA declenchee par ces feuilles passe par le CORPS UNIQUE
`../loki/summon.py::perform_ai_ability_unit_behaviour` (port de
`IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute`), atteint par l'un des deux
constructeurs homonymes de ses noeuds `DSLFactory` : `perform_ai_attack_from_current_position`
(`+0x70=0`, `+0x78=Direct(0)`) ou `perform_ai_attack` (`+0x70`/`+0x78` fournis par l'appelant). Aucune
feuille ne recable cible/gate/attaque a la main."""
from __future__ import annotations

from dataclasses import replace

from ....dsl.base import TargetsSelector, resolve_unit
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...components import OwnerComponent, StatsComponent
from .context import _unit_dict, LiveUnit


class Spawn(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$Spawn` -> `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` : itere son TILE-SELECTEUR
    EN INTERNE (mirror natif -- le `Spawn` n'est PAS un `Foreach(tiles, SpawnUnit)` externe, il enumere ses
    tuiles lui-meme) et spawn UNE unite par tuile, stats `WithStatsFromConfig(summon_ability)`, owner =
    team+player du caster. Wrapper au-dessus de l'Operation portee `_spawn_config_grot` (mirror de l'inline natif
    `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$ExecuteBehaviour`) : level/mult lus du `StatsComponent` du caster dans `ectx.state`. Chaque enfant
    est AJOUTE a `entities.children` (accumulateur factory+0x148, relu par `Children` pour le Taunt), annote
    pour le Taunt (`_new_child`/`_turns_started`/`_attacks_made`/`_last_attacked`). L'ordre d'enumeration =
    l'ordre du tile-selecteur (le `Cache` partage) -> `children` en ordre de TUILE (== l'ordre que
    `PerformAIAttack` reparcourt). Effet PUR (`stop=False`) ; journalise chaque spawn.

    `pick_n` = FOLD du `IdunBattleLogic.Entities.DSLFactory$$PickRandomly(tileSelector, n)` (`PickRandomAmountSelector`) quand le
    natif ENVELOPPE le tile-selecteur du Spawn -- meme convention que le `pick_n` des feuilles d'attaque
    (`AttackWithAttackDamage`) : le tirage vit dans la feuille, qui seule voit `ectx.state.rng`.
    Consommateur : `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour` =
    `Spawn(PickRandomly(CanAddUnit(AdjacentTiles(caster)), nrOfSummons), unitId, WithStatsFromConfig)`.
    None (defaut) = pas de PickRandomly natif (GetEmRuntz : toutes les tuiles du `Cache`).

    `on_appearance` = le SOUS-BEHAVIOUR EMBARQUE dans les options de spawn (`SpawnUnitOptions+0x18`), fire
    PAR SUMMON par `TriggerSpawnedUnitBehaviours` juste apres la pose. Le natif le construit AVANT le
    `Spawn` puis l'accroche (`*(opts+0x18) = <behaviour>`), et son selecteur d'acteur est
    **`ActiveTarget@0x180`** = le summon fraichement pose. Le port l'execute donc UNE FOIS PAR SUMMON avec
    `active_target` LIE a l'enfant (mirror exact). Consommateurs lus :
      * `IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour` -> `PerformAIAttackFromCurrentPosition(@0x180)` ;
      * `IdunBattleLogic.Entities.Abilities.Active.Loki.SendInTheNextWaveAbility$$ExecuteBehaviour` -> `UseNormalAttackIfAble(@0x180, Target@0x178)` ;
      * `IdunBattleLogic.Entities.Abilities.Active.Loki.IncursionAbility$$ExecuteBehaviour`        -> `UseNormalAttackIfAble(@0x180, Entity(cible))`.
    None (defaut) = options sans sous-behaviour (SupremeCommander/Waaagh/GetEmRuntz).

    FRAICHEUR DU CONTEXTE (piege du no-op silencieux) : l'`AbilityEntities` natif porte une REF d'etat --
    tout selecteur EVALUE APRES le spawn (dans le MEME arbre) VOIT les summons. Le `DslContext` du port
    fige sa liste `units` a la construction (`entities_from_state`) ; la feuille pousse donc chaque enfant
    DANS `entities.units` (liste PARTAGEE par reference a travers les `replace()` du walker) en plus de
    `entities.children`. Sans ca, un etage AVAL du meme arbre (ex. le `PerformAIAction(UnitsWithId(...))`
    de CultDemagogue IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour, 3e terme d'un UNIQUE `op_Addition`) ne verrait AUCUN summon = NO-OP
    SILENCIEUX. L'enfant est une `LiveUnit` (pos/hp/alive re-lus du state) -> les gardes `AllUnits`/`Alive`
    en aval lisent l'etat courant, comme le natif.

    `spawn_as_single_unit` = le champ `SpawnUnitOptions+0x60`, le bit qui fait BASCULER
    `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` sur son AUTRE branche. Lu verbatim
    au decompile :

        if (options.<+0x60> == 0)                        // branche par DEFAUT
            foreach (tile in tiles) AddUnit(unitConfig, [tile], player, 2, options);   // N unites
        else
            AddUnit(unitConfig, GetTileIds(tiles), player, 2, options);                // UNE unite

    `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$GetTileIds` aplatit TOUTE la collection de
    tuiles en UNE liste d'ids, que `AddUnitOperation$$Execute` consomme par `ClearFeet` + un
    `AddFoot` PAR tuile -> **UNE unite a N pieds**. C'est le SEUL producteur d'empreinte multi-hex
    du binaire, et son seul consommateur dans `gqfc5mff6c` est `DutyEternalAbility$$
    ExecuteBehaviour` (`*(opts + 0x60) = 1`). `False` (defaut) = branche par defaut, strictement
    inchangee pour les call-sites anterieurs."""
    __slots__ = ("tile_selector", "summon_ability", "pick_n", "on_appearance",
                 "spawn_as_single_unit")

    def __init__(self, tile_selector: TargetsSelector, summon_ability: str, pick_n: int | None = None,
                 on_appearance: AbilityBehaviour | None = None,
                 spawn_as_single_unit: bool = False):
        self.tile_selector, self.summon_ability = tile_selector, summon_ability
        self.pick_n = pick_n
        self.on_appearance = on_appearance
        self.spawn_as_single_unit = bool(spawn_as_single_unit)   # `SpawnUnitOptions+0x60`

    def execute(self, entities, ectx):
        import gameconfig as GC
        from ...operations.spawn import _spawn_config_grot
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
        tiles = self.tile_selector.evaluate(entities) or []
        if self.pick_n is not None:                       # fold `IdunBattleLogic.Entities.DSLFactory$$PickRandomly(tiles, n)
            from ..loki.splash import _pick_randomly_n
            tiles = _pick_randomly_n(state, tiles, int(self.pick_n))
        from ...operations.triggers.dispatch import ability_init_triggers   # lazy : cycle spawn<->triggers
        # `SpawnUnitBehaviour$$Execute` branche `options+0x60` : soit une unite PAR tuile (defaut),
        # soit UNE unite sur `GetTileIds(tiles)` (toutes les tuiles = ses PIEDS). Le port exprime les
        # deux par la MEME boucle : la 2e branche n'a qu'UNE iteration, dont l'ancre est `tiles[0]`
        # (== la main tile) et dont `feet_tiles` porte l'empreinte COMPLETE, dans l'ordre.
        spawns = ([(tiles[0], list(tiles))] if (self.spawn_as_single_unit and tiles)
                  else [(t, None) for t in tiles])
        for tile, feet in spawns:                         # itere les tuiles EN INTERNE (natif)
            gid = _spawn_config_grot(state, vid, tile, self.summon_ability, level, mult,
                                     oc.team if oc is not None else None,
                                     oc.player if oc is not None else None,
                                     parent_id=caster_id,     # `Unit_Parent_Id` (mirror live)
                                     feet_tiles=feet)
            if gid is not None:
                child = LiveUnit(state, gid)              # vue LIVE (mirror de la ref d'etat native)
                child.update({"_new_child": True, "_turns_started": 0, "_attacks_made": 0,
                              "_last_attacked": None})
                entities.children.append(child)       # accumulateur des enfants (relu par Children)
                entities.units.append(child)          # ref d'etat : les selecteurs AVAL voient le summon
                ectx.emit("SpawnUnit", tile=tile, unit=gid)
                # `IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` : les abilities de
                # l'unite fraichement creee s'INITIALISENT -> event `On(AbilityInit=0x21)`. C'est ce
                # vecteur que consomme `ListenUpMaggotsAbility` (df@0xa8 = On(0x21) & OwnerIsActor).
                ability_init_triggers(state, gid)
                if self.on_appearance is not None:    # SpawnUnitOptions+0x18 (TriggerSpawnedUnitBehaviours)
                    self.on_appearance.execute(replace(entities, active_target=child), ectx)
        return OperationResult.ok()


class PerformAIAttack(AbilityBehaviour):
    """Feuille des DEUX noeuds `DSLFactory` qui construisent un `PerformAIAbilityUnitBehaviour` — ils ne
    different que par les champs `+0x70 allowMoveAction` et `+0x78 moveAmount`, que la feuille PORTE
    explicitement (defauts = ceux de `...FromCurrentPosition`, cf.
    `../loki/summon.py::perform_ai_ability_unit_behaviour`) :
      * `PerformAIAttack(<sel>)`                        -> `...FromCurrentPosition` (`0` / `Direct(0)`) :
        GetEmRuntz 1045, SpawnPoxwalkers 1040, drones Tau ;
      * `PerformAIAttack(<sel>, True, None)`            -> `DSLFactory$$PerformAIAttack` (`1` / `null`) :
        `ForwardSpotterAbility$$ExecuteBehaviour` (`PerformAIAttack(ActiveTarget@0x180, 1, 0, 0, 0)`),
        i2 « The Cadian Guardsman immediately **takes a turn** ».
    Aujourd'hui les deux branches produisent le MEME observable (le port ne mirrore ni
    `ABaseAiUnitTactic$$GenerateActionTiles` ni le `MovementActionGenerator` -> l'acteur n'approche pas) ;
    les champs sont threades pour que ce residu reste dans le corps unique et que le call-site dise QUEL
    noeud natif il mirrore.

    `IdunBattleLogic.Entities.DSLFactory$$PerformAIAttackFromCurrentPosition(Cache(GetSpawnTileSelector))` ->
    `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute` : chaque unite SUR les tuiles du SELECTEUR (le natif
    reutilise le MEME `Cache(GetSpawnTileSelector)` que le `Spawn` -> les grots tout juste spawnes) execute
    une attaque AI depuis SA position COURANTE (sans bouger). Port : `tile_selector` = le `Cache` PARTAGE
    (memoise -> memes tuiles PRE-spawn que le Spawn, sinon `CanAddUnit` recalcule les exclurait car
    occupees) ; on parcourt ses tuiles DANS L'ORDRE, on mappe chacune au grot pose dessus (`entities.children`,
    populate par le `Spawn` en ORDRE DE TUILE -> l'ordre d'attaque == l'ordre natif == l'ordre RNG), et il
    attaque l'ennemi le plus proche via `AttackDamageOperation.execute` (approx du choix AI natif,
    confront live #200 tracer-v2 DSLFactory). Annote le dict enfant (`_attacks_made`,
    `_last_attacked` = dict FRAIS post-attaque) pour les predicats du Taunt. Emet 'PerformAIAttack'. PUR.

    Le selecteur natif est un `TargetsSelector` GENERIQUE ; les deux call-sites portes le nourrissent
    differemment -> la feuille NORMALISE (un seul port, pas de fork) :
      * DOMAINE TUILE (`GetEmRuntzAbility` : `Cache(GetSpawnTileSelector)`) -> ids de tuile, mappes au grot
        pose dessus via `entities.children` ;
      * DOMAINE UNITE (`IdunBattleLogic.Entities.Abilities.Active.Loki.SpawnPoxwalkersAbility$$ExecuteBehaviour` :
        `PerformAIAttackFromCurrentPosition(ActiveTarget@0x180)` = le summon fraichement pose, lie par le
        sous-behaviour on-appearance du `Spawn`) -> le dict d'unite est utilise TEL QUEL.

    ACTION PAR ACTEUR : la feuille ne fait que RESOUDRE LE DOMAINE puis delegue a l'UNIQUE corps,
    `perform_ai_ability_unit_behaviour` (`../loki/summon.py` — cible `_nearest_enemy`, gate de portee
    `_in_attack_range` mirror `IdunBattle.Core.Services.TargetingQuery$$GetRange` clamp `ForcedInMelee`
    inclus, attaque normale COMPLETE, puis dispatch after-hit `On(0x26)`/`On(8)`/`On(9)`). Il n'existe
    donc plus qu'UN corps pour ce noeud (de-fork : la feuille dupliquait auparavant cible+gate+attaque
    SANS le vecteur after-hit -> les grots/Poxwalkers/Cadians ne pompaient aucun trigger post-attaque,
    alors que le natif execute une VRAIE ability d'attaque via l'IA).

    GATE DE PORTEE (#114) : le natif est une routine IA « depuis la position COURANTE » -- l'acteur
    n'attaque QUE s'il a une cible ATTEIGNABLE sans bouger (`PerformAIAbilityUnitBehaviour.Execute`
    delegue le choix d'attaque a ses Func AI, qui n'en produisent aucune si rien n'est a portee ; i2
    EarlyWarningOverride : « can immediately attack an enemy in melee »). Sans ce gate, un drone spawne
    a 9 hex de l'ennemi le plus proche frappait quand meme. Les call-sites anterieurs spawnent AU CONTACT
    (ForwardSpotter/SendInTheNextWave/Incursion : tuiles adjacentes a la CIBLE ; GetEmRuntz : tuiles
    adjacentes aux ennemis) -> gate inerte pour eux (0 regression)."""
    __slots__ = ("tile_selector", "allow_move_action", "move_amount")

    def __init__(self, tile_selector: TargetsSelector, allow_move_action: bool = False,
                 move_amount: int | None = 0):
        self.tile_selector = tile_selector
        self.allow_move_action = bool(allow_move_action)   # `+0x70` (defaut = ...FromCurrentPosition)
        self.move_amount = move_amount                     # `+0x78` (defaut = `factory+0xb8` = Direct(0))

    def execute(self, entities, ectx):
        from ..loki import perform_ai_ability_unit_behaviour
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

        elems = self.tile_selector.evaluate(entities) or []
        if isinstance(elems, dict):                       # selecteur mono-unite (ActiveTarget d'un summon)
            elems = [elems]
        attacks: list = []
        for tid in elems:                                 # tuiles du Cache (ORDRE natif = spawn) OU unites
            child = tid if isinstance(tid, dict) else _child_on_tile(tid)
            if child is None:
                continue
            cid = child.get("id")
            r = perform_ai_ability_unit_behaviour(state, cid, self.allow_move_action,
                                                  self.move_amount)   # <- LE corps unique
            if r is None:
                continue
            tgt = r["target"]
            child["_attacks_made"] = int(child.get("_attacks_made", 0) or 0) + 1
            child["_last_attacked"] = _unit_dict(state, tgt)   # etat POST-attaque (alive/hp courants)
            attacks.append({"child": cid, "target": tgt, "total": r.get("total")})
        ectx.emit("PerformAIAttack", attacks=attacks)
        return OperationResult.ok()


class SpawnSummon(AbilityBehaviour):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` = un noeud natif UNIQUE `Execute(Spawn(...))` (plain
    `AActiveAbility.Execute`, PAS `ExecuteAtomic`) ou `Spawn(caster@0x160, tileSel, unitId, SpawnUnitOptions)`
    avec `SpawnUnitOptions.WithStatsFromConfig(config)` portant DEUX sous-behaviours EMBARQUES :
      +0x10 = `AddEffect(0x4a3 = ScarabHive_OverrideDamageProfile = 1187)` sur chaque summon ;
      +0x18 = `UseNormalAttackIfAble(target@0x178)` = attaque normale immediate (profil override Piercing).
    `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` spawn `count` summons -- count-2, placement et
    `WithStatsFromConfig` vivent DANS SpawnUnitBehaviour (via `GetUnitToSpawn`/`GetTileIds`/`GetStatsToOverride`),
    HORS des DSL-selecteurs : le tile-selecteur natif `First(SortByDistance(CanAddUnit(AdjacentTiles(target)),
    caster), i)` = `PickAtIndexSelector` (UN element, IdunBattle.Entities.Selectors.PickAtIndexSelector$$Select), le `count` vient des options -- puis
    `TriggerSpawnedUnitBehaviours` fire les 2 sous-behaviours embarques PAR summon.

    Port : delegue le SPAWN a l'Operation VALIDEE LIVE-BIT-EXACT `SpawnUnitOperation.execute` (count/stats
    `ability_var`/owner `CopyOwner`/placement adjacent-cible ; cf. test_summon_spawn_live) -- on ne re-derive
    PAS la selection de tuile via des DSL-selecteurs (le count-2 n'est PAS exprimable par `First`=PickAtIndex
    sans RE de `GetTileIds`/`GetUnitToSpawn`, et sans gain : l'outcome est deja valide). ON-APPEARANCE =
    `_summon_on_appearance_attack(summon, target, unitDamageProfile)` (mirror `UseNormalAttackIfAble`, profil
    Piercing en override de l'arme Energy). L'effet PERSISTANT 0x4a3 (OverrideDamageProfile pour les attaques
    des TOURS SUIVANTS du summon) n'est PAS materialise ici -- le pipeline d'attaque ne le LIT pas encore
    (gap flagge en tache) ; l'attaque immediate porte deja le profil override via `prof`. Emet
    'SpawnUnit'/'SummonOnAppearance'. Effet PUR (stop=False)."""
    __slots__ = ("summon_ability", "count", "target_ref")

    def __init__(self, summon_ability: str, count: int, target_ref: TargetsSelector):
        self.summon_ability, self.count, self.target_ref = summon_ability, int(count), target_ref

    def execute(self, entities, ectx):
        import gameconfig as GC
        from ...operations.spawn import SpawnUnitOperation
        from ..loki import _summon_on_appearance_attack
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        tu = resolve_unit(self.target_ref, entities)        # Target()@0x178 -> dict d'unite
        target_id = tu.get("id") if tu else None
        if state is None or caster_id is None or target_id is None:
            return OperationResult.ok()
        consts = (GC.ability(self.summon_ability) or {}).get("constants") or {}
        vid = consts.get("unitId")
        if vid is None:
            return OperationResult.ok()
        prof = consts.get("unitDamageProfile")              # profil override de l'attaque on-appearance (Piercing)
        # [Spawn / WithStatsFromConfig / CopyOwner / placement] -> Operation validee (count/stats/owner/tuiles)
        spawned = SpawnUnitOperation.execute(state, caster_id, target_id, self.summon_ability, vid, self.count)
        for sid in spawned:
            ectx.emit("SpawnUnit", unit=sid)
        # [on-appearance] UseNormalAttackIfAble : chaque summon attaque la CIBLE (profil override immediat).
        for sid in spawned:
            res = _summon_on_appearance_attack(state, sid, target_id, prof)
            if res is not None:
                ectx.emit("SummonOnAppearance", summon=sid, total=res.get("total"))
        return OperationResult.ok()


class SpawnReplica(AbilityBehaviour):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour` (id 1047, necroSmnSwarm -- auto-DEDOUBLEMENT) = un
    noeud natif UNIQUE `Execute(Spawn(...))` (plain `AActiveAbility.Execute`, PAS `ExecuteAtomic`), DISTINCT
    du noeud ScarabHive (`SpawnSummon`) : `Spawn(self@0x160, tileSel, unitId=GetStringConstant(config,0)=
    necroSmnSwarm, SpawnUnitOptions.CopyOwner(caster))` ou les options portent UN sous-behaviour EMBARQUE :
      +0x18 = `PerformAIAttack(Spawned@0x180, 1, 0, 0, 0)` = le double joue un TOUR d'IA immediatement --
      PAS de +0x10 AddEffect (ScarabSummon n'a PAS l'effet persistant 0x4a3 de ScarabHive) ;
    tile-selecteur natif = `PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1, ..., 0x7fffffff)` (UNE tuile
    LIBRE adjacente a SOI). `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` spawn `count` clones -- count/placement/
    CopyOwner vivent DANS SpawnUnitBehaviour, HORS des DSL-selecteurs -- puis `TriggerSpawnedUnitBehaviours`
    fire le sous-behaviour on-appearance PAR summon (AVANT de poser le flag « cannot move », lu au decompile
    de `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` : le flag 0x23 est
    applique APRES l'on-appearance, il ne le gate donc pas).

    Port : delegue le SPAWN a l'Operation VALIDEE `SpawnUnitOperation.execute_self_replica` (`IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner` = clone owner+stats du parent, count-1, tuiles libres adjacentes au caster ; cf.
    test_summon_spawn_live) -- MEME carve-out que `SpawnSummon` (on ne re-derive PAS le count/placement via
    des DSL-selecteurs : ils vivent dans SpawnUnitBehaviour et l'outcome est deja valide). ON-APPEARANCE =
    l'UNIQUE port du noeud, `perform_ai_attack(state, sid, allow_move_action=True, move_amount=None)`
    (`../loki/summon.py`) : MEME corps `perform_ai_ability_unit_behaviour` que toutes les autres attaques
    d'IA -- gate de portee `_in_attack_range` (mirror `IdunBattle.Core.Services.TargetingQuery$$GetRange`,
    clamp `ForcedInMelee` inclus), attaque normale COMPLETE, puis dispatch after-hit `On(0x26)`/`On(8)`/`On(9)`.
    `allow_move_action=True` / `move_amount=None` sont les DEUX champs (`+0x70`, `+0x78`) par lesquels ce noeud
    differe de `...FromCurrentPosition` : ils sont threades explicitement, jamais re-inventes ici.

    AVANT (fork residuel laisse par la de-forkification `7f47c29`) : cette feuille recablait `_nearest_enemy` +
    `AttackDamageOperation.execute` A LA MAIN -- SANS gate de portee (le double frappait l'ennemi le plus proche
    quelle que soit la distance, arme de melee comprise) et SANS dispatch after-hit (aucun trigger post-attaque
    ne partait du double). Emet 'SpawnUnit'/'ReplicaOnAppearance'. Effet PUR (stop=False).

    GAPS (inchanges) : le cap de duplication (`UnitDuplicationLimitSelector`/`LimitUnitDuplications`) n'est pas
    porte -> recurrence non bornee offline ; le DEPLACEMENT du double avant son attaque (`move_amount=None` ->
    `GenerateActionTiles` / `MovementActionGenerator` non portes) non plus -> residu documente sur
    `perform_ai_ability_unit_behaviour`."""
    __slots__ = ("summon_ability", "count")

    def __init__(self, summon_ability: str, count: int):
        self.summon_ability, self.count = summon_ability, int(count)

    def execute(self, entities, ectx):
        import gameconfig as GC
        from ...operations.spawn import SpawnUnitOperation
        from ..loki import perform_ai_attack
        state = ectx.state
        caster_id = (entities.caster or {}).get("id")
        if state is None or caster_id is None:
            return OperationResult.ok()
        vid = ((GC.ability(self.summon_ability) or {}).get("constants") or {}).get("unitId")
        if vid is None:
            return OperationResult.ok()
        # [Spawn / CopyOwner / placement adjacent-self] -> Operation validee (clone owner+stats du parent)
        spawned = SpawnUnitOperation.execute_self_replica(state, caster_id, vid, self.count)
        for sid in spawned:
            ectx.emit("SpawnUnit", unit=sid)
        # [on-appearance] `PerformAIAttack(Spawned@0x180, 1, 0, 0, 0)` -> LE noeud (corps unique) : les deux
        # champs qui le distinguent de `...FromCurrentPosition` sont passes tels que lus au decompile
        # (`+0x70 allowMoveAction = 1`, `+0x78 moveAmount = null`).
        for sid in spawned:
            r = perform_ai_attack(state, sid, allow_move_action=True, move_amount=None)
            if r is not None:
                ectx.emit("ReplicaOnAppearance", summon=sid, target=r["target"],
                          total=r.get("total"), after_hit=r.get("after_hit"))
        return OperationResult.ok()
