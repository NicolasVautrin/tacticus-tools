"""Socle DSL GENERIQUE - les 4 BASES DE FAMILLE lazy, `DslContext` et helpers partages (moteur de
NOEUDS, mirror 1:1 du DSL lazy `DSLFactory`/`TargetsSelector` du jeu).

Le DSL natif = 4 familles, bases abstraites de `IdunBattle.DSL`, une methode d'eval chacune (probe
`dslLazyProbe`) : `AbilityBehaviour.Execute` (EFFETS, kind E, cf. effect_nodes.py), `AbilityTrigger.
ShouldTrigger` (PREDICATS, kind T), `TargetsSelector.Select` (SELECTEURS, kind S), `AAmountFormula.
Calculate` (VALEURS, kind V). Ce module porte les 3 bases LAZY (T/S/V, cf. ci-dessous) mirrorees NOM
POUR NOM ; l'effet (E) vit dans effect_nodes.py. Le natif n'a AUCUNE racine commune au-dessus des 4
(parents `[base, System.Object]`, interfaces `[]`) -> PAS de `Node` fourre-tout : 4 familles SOEURS.

Chaque ability compose un arbre evalue par la methode de sa famille (`should_trigger`/`select`/`calculate`)
contre un `DslContext` (etat de bataille). Types de valeur (comme le DSL natif, type) : NUMERIQUE -> int ;
CONDITION -> bool ; POSITION -> (col,row) ; CIBLAGE -> list[unit]. Unite = dict `{id, team, hp, alive,
pos:{col,row}, visualId}`.

Ghidra MISLABEL les ctors de noeuds gshared (le ctor de `IdunBattleLogic.Entities.DSLFactory$$Sum` s'affiche
`HasUsedActiveAbilityThisTurnTrigger$$.ctor`) -> semantique lue via la STRUCTURE (pointeur de classe, args
enfants, arithmetique), JAMAIS via les noms. cf. [[feedback_re_ghidra_not_experiment]].

Modules soeurs (split ~1000 lignes) : arithmetic / predicates / selectors / accessors. `nodes.py` reste un
shim de compat re-exportant tout. cf. docs/rl/dsl-cartography-phase1.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction

import hexgeo


# --- Bases DSL par FAMILLE (mirror 1:1 des bases abstraites natives ; une methode d'eval chacune). La
# methode NOMMEE COMME LE NATIF est le VRAI point de surcharge de chaque noeud ; `evaluate` reste un
# ALIAS GENERIQUE qui delegue -> les combinateurs POLY-FAMILLE (`Cache`, `Filter`, arithmetique, `Count`,
# `_units_of`) evaluent un enfant SANS connaitre sa famille (robustesse : pas de dispatch croise fragile).
# C'est une convenance de PORT (le natif dispatch par contrat type) documentee, pas une classe native.
class AAmountFormula:
    """Base des noeuds VALEUR (numerique -> int). Mirror `IdunBattle.DSL.AAmountFormula.Calculate` (kind V).

    ⚠ `Calculate` n'est PAS le seul point d'entree du noeud : `IAmountFormula` en expose QUATRE, et
    c'est le SLOT que l'appelant invoque qui decide de l'arrondi d'une moyenne (#350-r3b). Les trois
    autres sont portes ci-dessous, mirror du decompile `rnca9r7q6c` :

      * `calculate_min` / `calculate_max` (slots 3 et 4 de la table, `<vtable+0x1e8>`/`<vtable+0x1f8>`)
        -- `IdunBattle.DSL.ASimpleAmountFormula$$CalculateMin` / `$$CalculateMax` retombent tous DEUX
        sur `<vtable+0x1d8>` = `Calculate`. C'est le DEFAUT ici. Seuls les noeuds a PLAGE surchargent
        (dans ce port : `IdunBattle.Entities.Formulas.RandomAmount`).
      * `calculate_average` -- `IdunBattle.DSL.AAmountFormula$$CalculateAverage`, le slot que les
        playbooks invoquent avec l'index 4.

    Le prédicat de court-circuit `<vtable+0x1c8>` du decompile n'est PAS modelise : son corps est
    trivial et DEDUPLIQUE (aucun symbole propre), et il est inobservable ici -- pour tout noeud SIMPLE
    la branche « plage » rend `(v + v) / 2 = v`, identique au court-circuit, quelle que soit sa
    polarite ; et pour `RandomAmount` la branche « plage » est etablie LIVE (#339, `probe_32d_fury`).
    Detail + residu (les 8 autres noeuds a plage, hors perimetre) : `docs/rl/case-350r3b-moyennes-triggered.md`.
    """
    def calculate(self, ctx: DslContext):
        raise NotImplementedError

    def evaluate(self, ctx: DslContext):    # alias generique (cf. en-tete) -> methode native
        return self.calculate(ctx)

    def calculate_min(self, ctx: DslContext):
        """`IdunBattle.DSL.ASimpleAmountFormula$$CalculateMin` = `<vtable+0x1d8>` = `Calculate`."""
        return self.calculate(ctx)

    def calculate_max(self, ctx: DslContext):
        """`IdunBattle.DSL.ASimpleAmountFormula$$CalculateMax` = `<vtable+0x1d8>` = `Calculate`."""
        return self.calculate(ctx)

    def calculate_average(self, ctx: DslContext) -> int:
        """`IdunBattle.DSL.AAmountFormula$$CalculateAverage` -- le slot que le playbook invoque avec
        l'index 4 (`FUN_180025fb0(4, <IAmountFormula>, <noeud>, ...)`). Mirror de la branche « plage »
        du decompile :

            mn = <vtable+0x1e8>(entities, result);     # CalculateMin
            mx = <vtable+0x1f8>(entities, result);     # CalculateMax
            return (mx + mn) / 2;                      # division ENTIERE C -- AUCUN Fix64 ici

        Sur un noeud SIMPLE cela rend `Calculate` a l'identique ; sur `RandomAmount` cela TRONQUE.
        L'arithmetique vit dans la fonction libre `calculate_average` (definie plus bas, #339)."""
        return calculate_average(self.calculate_min(ctx), self.calculate_max(ctx))


class AbilityTrigger:
    """Base des noeuds PREDICAT (-> bool). Mirror `IdunBattle.DSL.AbilityTrigger.ShouldTrigger` (kind T)."""
    def should_trigger(self, ctx: DslContext) -> bool:
        raise NotImplementedError

    def evaluate(self, ctx: DslContext):
        return self.should_trigger(ctx)


class TargetsSelector:
    """Base des noeuds SELECTEUR (-> list/tuile/entite). Mirror `IdunBattle.DSL.TargetsSelector.Select` (kind S)."""
    def select(self, ctx: DslContext):
        raise NotImplementedError

    def evaluate(self, ctx: DslContext):
        return self.select(ctx)


def resolve_unit(node, ctx):
    """Evalue un noeud (souvent `Subject()`/`Target()`) en UN dict d'unite : dict direct, ou 1er dict d'une
    liste. Helper PARTAGE (selecteurs `Entities.Selectors`, formules `Entities.Formulas`, feuilles
    `Entities.Behaviours` runner) -> vit dans la base commune. None si l'eval ne donne aucun dict."""
    v = node.evaluate(ctx)
    if isinstance(v, dict):
        return v
    if isinstance(v, (list, tuple)):
        for x in v:
            if isinstance(x, dict):
                return x
    return None


@dataclass
class DslContext:
    """Contexte d'évaluation d'un arbre DSL (l'« état de bataille » que le nœud interroge).

    `config`/`ability_level` → `ConfigConst` ; `caster`/`target`/`units` → ciblage + positions ;
    `times_attacked` = compteur runtime du caster (`TotalTimesAttackedFormula IdunBattle.Entities.Formulas.TotalTimesAttackedFormula$$Calculate`, composant @+0x34)
    NON capté offline → défaut 0 ; `flags` = ensemble de flags actifs (`HasFlag`). `units`/`caster`/`target`
    ne sont requis que par les nœuds de CIBLAGE (AoE) — un arbre purement numérique (hits) les ignore."""
    units: list = field(default_factory=list)
    caster: dict | None = None
    target: dict | None = None
    config: object | None = None            # AbilityConfiguration
    ability_level: int = 0
    times_attacked: int = 0
    # Compteur runtime de RÉPARATIONS du caster (`DSLFactory.TimesRepaired`, ex. DakkaDakkaDakka
    # IdunBattleLogic.Entities.Abilities.Active.Loki.DakkaDakkaDakkaAbility$$GetNumHits) NON capté offline → défaut 0.
    times_repaired: int = 0
    flags: frozenset = field(default_factory=frozenset)
    # Position VIRTUELLE du caster pour la décision balayée (= la tuile d'attaque post-move,
    # `casterPosition` passé aux selectors par le generator natif). None → position courante.
    caster_pos: tuple | None = None
    # Élévation par tuile (tileMeta) — consommée par les selectors gated élévation
    # (`TilesOnSameElevationSelector`). None → filtre dégradé no-op (documenté par nœud).
    elev_by_pos: dict | None = None
    # Graphe de tuiles (`Board`, entities/pathfinding) — consommé par les SÉLECTEURS DE TUILES
    # (`AdjacentTiles`/`CanAddUnit`, tile_selectors.py) : voisinage natif (`board.neighbours`),
    # walkable, id_at. None → domaine tile dégradé no-op (documenté par nœud).
    board: object | None = None
    # Élément COURANT lié par un `Filter` (mirror du sélecteur-sujet natif `ability+0x180` =
    # OriginalTarget) — lu par le nœud `Subject` et les prédicats évalués sous un Filter. None hors Filter.
    subject: dict | None = None
    # ACCUMULATEUR des enfants SPAWNÉS par le behaviour courant (mirror du champ factory natif `+0x148`
    # que `DSLFactory.Spawn` alimente et que `IdunBattleLogic.Entities.DSLFactory$$Children` (= `AllAliveMachinesSelector`)
    # relit — cf. GetEmRuntz `Foreach(Children, TauntWithNewChildrenWhoDidDamage)`). Liste PARTAGÉE (le
    # `replace(subject=…)` du `Foreach` la partage par référence) : les feuilles `SpawnUnit` y ajoutent le
    # dict de l'unité spawnée, `Children` la retourne. Défaut [] ; hors behaviour de spawn = vide.
    children: list = field(default_factory=list)
    # Facteur de conversion rounds→turns (`TurnsFromRounds`, méthode runtime index 0x1b) : dépend du
    # nb d'équipes/joueurs actifs par round, NON capté offline → défaut 1 (identité, cf. times_attacked).
    turns_per_round: int = 1
    # Rôles distincts de l'AbilityEntities (slots factory +0x148/+0x158) pour les prédicats `OwnerIs*`.
    # Défaut None → retombe sur `caster` (hypothèse standard Owner==Caster==Actor, divergence documentée).
    owner: dict | None = None
    actor: dict | None = None
    # `ActiveTarget` = slot factory `+0x180` (carte des `TargetsSelector` caches du `DSLFactory`,
    # `IdunBattleLogic.Entities.DSLFactory$$InitializeShared` : `0x148 Owner · 0x150 Effect · 0x158 Actor · 0x160 Caster ·
    # 0x168 CasterTile · 0x170 CasterTiles · 0x178 Target · 0x180 ActiveTarget · 0x188
    # PreviousActiveTarget · 0x190 TargetTiles · 0x198 UnitFeetTiles`). C'est l'ELEMENT COURANT du
    # behaviour qui l'a lie : (a) le SUMMON fraichement pose pour un sous-behaviour on-appearance
    # (`SpawnUnitOptions+0x18`, ex. Poxwalkers `PerformAIAttackFromCurrentPosition(ActiveTarget)` /
    # SendInTheNextWave `UseNormalAttackIfAble(ActiveTarget, Target)`), (b) l'element rendu par
    # l'iteration courante d'un `ChainBehaviour` (Incursion : la TUILE de spawn). Defaut None ->
    # le noeud `ActiveTarget` rend None (hors behaviour liant).
    active_target: object | None = None
    # Joueur dont c'est LE TOUR (`TurnComponent.CurrentPlayer`) — lu par le nœud `IsTurnOf`
    # (`IdunBattleLogic.Entities.DSLFactory$$IsTurnOf`, qui referme le `matchState@+0x10` de la
    # factory dans son trigger). None = contexte sans tour courant (prédiction, arbre purement
    # numérique) → `IsTurnOf` rend False (dégradation conservatrice).
    current_player_id: int | None = None
    # Accès trait/stat PAR UNITÉ (mirror `UnitExtensions.HasFlag`/`GetStat`) — hors state standard.
    # `has_trait(unit, traitId)->bool` défaut None → trait absent ; `get_stat(unit, statType, variant,
    # level)->int` défaut None → Health via hp (cf. `_default_get_stat`). Fournis par la couche ability.
    has_trait: object | None = None
    get_stat: object | None = None
    # Contexte d'ATTAQUE courant (Is*Attack) = type de l'ability en cours d'éval. Statique (profil
    # gameconfig), câblé par la couche ability ; défaut None → prédicats d'attaque = False.
    attack_kind: str | None = None           # 'melee' | 'ranged'
    attack_ability_type: int | None = None   # ActiveAbilityType (IsNormalAttack compare vs 1013)
    # Accès effets par unité (HasEffect/HasAnyEffect), mirror `IdunBattle.Entities.EntityExtensions$$HasOneOfEffects` — hors state
    # standard. `has_effect(unit, effectType, source_flag=6, min_level=0)->bool` défaut None → False.
    has_effect: object | None = None
    # Accès effets par TUILE (prédicat de `IdunBattleLogic.Entities.DSLFactory$$UnitsOnTilesWithEffect` : la tuile porte-t-elle un
    # effet ACTIF du type — ex. Ice 0x11 pour Stormcaller #217). `tile_has_effect(tile_id, effectType)
    # ->bool` ; défaut None → sélecteur dégradé [] (documenté par nœud). Fourni par `entities_from_state`
    # (lit `state.effects` keyé tile-id, même clé que la pose `AddEffectOperation`, cf. case-35).
    tile_has_effect: object | None = None
    # Effet COURANT (EffectSource/EffectLevel) — n'existe qu'en application d'effet ; défaut None.
    effect: object | None = None
    # Accès aux INSTANCES d'effet par SOURCE (mirror `IdunBattleLogic.Entities.DSLFactory$$EffectsFromUnitSource` =
    # `EffectWithTypeSelector(source, effectType)`) : `effects_from_source(source_unit, effectType)`
    # -> list[{"effect_type", "source", "owner_id"}] (une entrée par instance d'effet ACTIVE dont le
    # `EffectComponent.SourceUnit` == `source_unit`). Défaut None -> sélecteur dégradé [] (documenté par
    # nœud). Fourni par la couche runner (`entities_from_state`, lit `state.effects`).
    effects_from_source: object | None = None
    # Faction (`FactionId` gameconfig) PAR UNITÉ (mirror `DSLFactory.UnitsFromFaction`, qui compare vs
    # `Enum.ToString(UnitFaction)` = le NOM de faction) — hors state standard, comme `has_trait`/`get_stat`.
    # `faction_of(unit)->str|None` défaut None → faction inconnue (UnitsFromFaction rend vide). Fourni par la
    # couche runner (`entities_from_state`) via `_faction(visualId)`.
    faction_of: object | None = None
    # LISTE persistante d'une unite (`IdunBattle.Entities.Components.PersistentDataComponent$$
    # TryGetPersistDataListu003C__Il2CppFullySharedGenericStructTypeu003E`) : `persistent_data_list(
    # unit, key) -> list` = le `List<T>` range sous la cle composite `(GetPersistentDataId(
    # abilityOrEffect), dataKey)`. Lu par le predicat `IsInPersistentDataList` (mirror
    # `Idun.Source.IdunBattle.Logic.Entities.Triggers.IsInPersistentDataListTrigger$$ShouldTrigger`,
    # dont le corps est `(TryGetPersistDataList(...) ?? new List()).Contains(value)`) et par le
    # selecteur `EntitiesFromPersistentDataList`. Defaut None -> liste VIDE (degradation fidele : le
    # natif materialise lui aussi une liste neuve quand la cle est absente). Fourni par la couche
    # runner (`entities_from_state`, lit le `PersistentDataComponent` de l'ECS).
    persistent_data_list: object | None = None
    # `MachineOfWarPosition` (1=Top, 2=Bottom) du joueur COURANT — lu par le predicat
    # `IsPositionMachineForCurrentPlayer` (mirror
    # `IdunBattle.Entities.Triggers.IsPositionMachineForPlayerTrigger$$ShouldTrigger`, qui interroge
    # `BattleQuery$$GetPositionMachineForPlayer(GetPlayer(turn.CurrentPlayerId))`). ⚠ C'est le slot
    # du GROUPE DE SPAWN du joueur (propriete du PLATEAU), PAS celui d'une machine deployee —
    # cf. `engine.services.machine_of_war_position` (#302 tranche 3). None = **non mesure** ->
    # predicat False. Pose par `entities_from_state` (face COMBAT, via un PROXY documente) et par
    # `engine.playbook.tile_targets.dsl_context_for_tile_target` (face DECISION, source native).
    current_player_machine_position: int | None = None
    # Modifications de stat NEGATIVES par unite (predicat `HasNegativeModifier`, mirror
    # `IdunBattle.Entities.Triggers.HasNegativeModifier$$ShouldTrigger`) : `has_negative_modifier(unit,
    # stat_types)->bool` = l'unite porte >=1 modification per-source <0 sur l'un des StatTypes du filtre.
    # Defaut None -> False (degradation fidele). Fourni par `entities_from_state` (UnitStats.has_negative_modifier).
    has_negative_modifier: object | None = None
    # Portee d'AURA d'EQUIPE (`IsInAuraRangeTrigger`, ex. `IsInTeamContagionsOfNurgleAura`) :
    # `is_in_team_aura(unit, effectType, teamReference)->bool` = mirror de
    # `IdunBattle.Core.Services.BattleQuery$$IsInTeamAuraRange` (case-224 ; le port vit dans
    # `battle_query.get_in_range_aura_amount`, son etage de portee dans `entities/effects/aura.py`).
    # Fourni par `entities_from_state` ; defaut None = False (contexte hors runner).
    is_in_team_aura: object | None = None
    # Compteur runtime d'usages d'une ability ACTIVE par une unite (`DSLFactory.TotalActiveAbilityUsed`) :
    # `total_active_ability_used(unit, abilityType)->int`. NON capte offline (meme regime que
    # `times_attacked`/`times_repaired`) -> defaut None = 0.
    total_active_ability_used: object | None = None
    # Montant COURANT de la modification de stat portee par un effet donne (`CurrentStatModifierAmount`,
    # gate d'idempotence d'`AddOrUpdateStaticStatModifierEffect`) : `stat_modifier_amount(unit, effectType,
    # statType)->int`. Defaut None -> 0 (cf. le noeud).
    stat_modifier_amount: object | None = None
    # Niveau d'ability PAR UNITÉ + slot (`ConfigVar` sur une unité TIERCE, ex. la chance RighteousRepugnance
    # au niveau du killer). `get_ability_level(unit, slot='passive'|'active')->int|None` : lit le
    # `passive_ability_level`/`active_ability_level` capté (StatsComponent.ctx). Défaut None → niveau inconnu
    # (le nœud consommateur dégrade sur le défaut d'`ability_var`). Fourni par `entities_from_state`.
    get_ability_level: object | None = None
    # DRAPEAU d'unite (`IdunBattle.Entities.Components.UnitFlagsComponent$$Has(unit, UnitFlag)`) :
    # `has_unit_flag(unit, flag)->bool`. Lu par `AllDeadOrResurrectedUnits` (mirror
    # `IdunBattle.Entities.Selectors.AllDeadOrResurrectedUnitsSelector$$Select`, qui teste le flag 0xe sur
    # CHAQUE unite du state). Defaut None -> False (degradation fidele : aucun ressuscite). Fourni par
    # `entities_from_state` (lit le `UnitFlagsComponent` de l'ECS runner).
    has_unit_flag: object | None = None
    # --- Les DEUX slots `IAttackQuery` que le DSL invoque depuis un SELECTEUR (#303) --------------
    # Verdict `IdunBattle.Core.Services.AttackQuery$$EntityCanBeRepaired(entity, scope, removeEffects)`
    # -- la surcharge a TROIS arguments (slot 0x13), celle SANS caster, consommee par
    # `IdunBattle.Entities.Selectors.RepairableUnitsSelector$$Select`.
    # `entity_can_be_repaired(unit, scope, remove_effects) -> bool`. Defaut None (accesseur non
    # branche = contexte hors runner) -> le selecteur `Repairable` rend [] : degradation NOMMEE par le
    # noeud, jamais un « tout passe ». Fourni par `entities_from_state`.
    entity_can_be_repaired: object | None = None
    # `IdunBattle.Entities.EntityExtensions$$HasEffectOfType(entity, state, effectsDatabase, category)`
    # -- la CATEGORIE d'effet (1 = negatif) lue dans la DEFINITION de chaque effet porte, consommee par
    # `IdunBattle.Entities.Selectors.UnitsWithEffectsOfTypeSelector$$Select`.
    # `has_effect_of_type(unit, effect_category) -> bool`. Defaut None, et AUCUN substrat ne le
    # branche : le canal de seed n'expose pas la categorie d'un effet (meme trou que
    # `attack_query.has_negative_unit_effect`) -> le selecteur rend []. RESIDU documente par le noeud.
    has_effect_of_type: object | None = None
    # Tirage `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` : `pick_randomly(items,
    # amount, allow_repeat, max_repeats) -> list`. Le noeud `PickRandomly` DELEGUE ici parce que la
    # boucle native CONSOMME le PRNG de bataille, qui n'est pas dans le `DslContext` (mirror unique :
    # `runner/abilities/loki/splash.py::_pick_randomly_n`). None = contexte sans PRNG -> le noeud
    # retombe sur les `amount` premiers elements, ZERO tirage (degradation nommee par le noeud).
    pick_randomly: object | None = None
    # `AbilityEntities.IsFirstHit` (`IdunBattle.Entities.Abilities.AbilityEntities$$get_IsFirstHit`,
    # champ +0x110 = le `DamageAppliedResult` du coup courant) -> `Nullable<bool>` valant
    # `DamageAppliedResult.get_IsFirstHit` = `hitIndex == 0`. Lu par le SEUL predicat
    # `IdunBattle.Entities.Triggers.IsFirstHitInSeriesTrigger$$ShouldTrigger` (`HasValue ? Value : false`).
    # Defaut None = coup hors serie / index inconnu -> le predicat rend False (mirror du `!HasValue`).
    is_first_hit: bool | None = None
    # Verdict `IdunBattle.Core.Services.BattleQuery$$EntityCanHaveActiveAbilityReset(unit, false)` --
    # consomme par le selecteur `UnitsThatCanHaveActiveAbilityReset` (InspiredToGreatness).
    # `can_have_active_ability_reset(unit) -> bool | None` ; None = verdict INCONNU (canal
    # `ActiveAbilitiesComponent` absent) -> le selecteur le propage au lieu d'inventer un False.
    # Defaut None (accesseur non branche) = meme ignorance. Fourni par `entities_from_state`.
    can_have_active_ability_reset: object | None = None
    # Unites qu'un ATTAQUANT a endommagees pendant la PHASE courante (mirror de la `List<BEntityId>`
    # @`ActorStatisticsComponent + 0x48`, lue par
    # `IdunBattle.Entities.Formulas.UnitsDamagedThisPhaseSelector$$Select`) :
    # `units_damaged_this_phase(attacker_unit) -> list[dict d'unite]`. Defaut None -> selecteur degrade []
    # (documente par noeud). Fourni par `entities_from_state` (lit `UnitComponent.damaged_units_this_phase`).
    units_damaged_this_phase: object | None = None
    # Liste des unites que `unit` a CHARGEES ce tour (`UnitComponent + 0x190`, un `List<int>` d'ids
    # alimente par `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` et vide par
    # `IdunBattle.Operations.FinishUnitTurnOperation$$Execute`). C'est la MOITIE runtime du predicat
    # `IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` = `AreEntitiesAdjacent(caster,
    # target) && chargedUnitIds(caster).Contains(target.Id)`. `charged_units(unit) -> set[int]` ;
    # defaut None -> ensemble VIDE (degradation fidele : personne n'a charge). Fourni par
    # `entities_from_state` (lit le `UnitComponent` de l'ECS runner).
    charged_units: object | None = None
    # Cibles LEGALES de l'attaque NORMALE d'une unite (mirror
    # `IdunBattle.Entities.Selectors.ValidNormalAttackTargetsSelector$$Select` ->
    # `TargetingQuery.GetValidTargets(unit, tiles, <options de l'attaque normale>)`) :
    # `valid_normal_attack_targets(caster_unit) -> list[dict d'unite]`. Fourni par
    # `entities_from_state` (le filtre vit dans `runner/abilities/targeting.py`, seul port de la
    # cascade de ciblage). Defaut None -> le selecteur `ValidNormalAttackTargets` rend [] (contexte
    # hors runner : la cascade n'est pas evaluable sans `State`), degradation documentee par noeud.
    valid_normal_attack_targets: object | None = None


class Const(AAmountFormula):
    """`DSLFactory.Direct(value)` : constante littérale (VALEUR)."""
    def __init__(self, value: int):
        self.value = value

    def calculate(self, ctx):
        return self.value


def _pos(u):
    p = u.get("pos") if u else None
    return (p["col"], p["row"]) if p else None


def _tile_enum_rank(board, center, radius, order) -> dict:
    """{(col,row): index} = ORDRE D'ENUMERATION NATIF des tuiles parcourues par le selecteur
    d'occupation (`Units(<selecteur de tuiles>)` -> `IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`,
    qui ITERE le selecteur de tuiles et resout l'occupant de chacune). Deux itérateurs natifs
    DISTINCTS, d'ou le parametre `order` (c'est le SELECTEUR qui tranche, pas le rayon) :

      * `order='adjacent'` — `AdjacentTiles` -> `BattleQuery$$GetAdjacentTiles` ->
        `TileQuery$$IterateAdjacentTiles` = la liste d'adjacence STOCKEE sur la tuile, prise
        telle quelle -> `Board.neighbours_native` (champ brut `boardGraph.neighbours`).
      * `order='surrounding'` — `SurroundingTiles` -> `BattleQuery$$GetSurroundingTiles` ->
        `TileQuery$$IterateSurroundingTiles` = TRIPLE BOUCLE en coordonnees CUBE
        (`for x in [cx-r, cx+r] { for y in [cy-r, cy+r] { for z in [cz-r, cz+r] {
        if (x+y+z == 0) yield GetTileEntityAt(ToAxial(x,y,z)) }}}`, DECOMPILE de
        `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`).
        `hexgeo.disk` enumere EXACTEMENT dans cet ordre (dx croissant puis dy croissant, dz
        contraint) et `hexgeo.to_cube`/`from_cube` == `AxialCoordinate$$ToCubeCoordinate` /
        `CubeCoordinate$$ToAxialCoordinate` (branche offset-parity 0) -> reutilise tel quel.

    `order='adjacent'` avec un rayon != 1 n'a PAS d'homologue natif (`AdjacentTiles` est
    ring-1 par construction ; le rayon est une extension du port) -> repli sur l'ordre cube.

    Pourquoi ca compte : `PickRandomAmountSelector$$Select` tire par `ElementAt(idx)` DANS
    l'ordre du `source.Select(entities).ToList()` — aucun tri n'intervient avant le tirage.
    L'ordre source decide donc QUI est pique des que `|pool| > amount`, et il tranche a egalite
    sous les `OrderBy` natifs, qui sont STABLES (cf. fc23f1e)."""
    if board is None or center is None:
        return {}
    positions: list = []
    if order == "adjacent" and int(radius) == 1:
        tid = board.id_at(center[0], center[1])
        if tid is not None:
            for t in board.neighbours_native(tid):
                c = board.by_id.get(t)
                if c is not None:
                    positions.append((c["col"], c["row"]))
    else:
        positions = list(hexgeo.disk(center[0], center[1], int(radius)))
    rank: dict = {}
    for i, p in enumerate(positions):
        rank.setdefault((p[0], p[1]), i)
    return rank


def _within(units, center, radius, include_center=False, board=None, order=None):
    """Anneau/disque d'unites autour de `center` — cœur des selecteurs d'OCCUPATION (`Units(
    SurroundingTiles/AdjacentTiles(...))`, tous les call-sites). VIVANTS SEULEMENT (#57m) : le natif
    resout les unites PAR TUILE (`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select` : selecteur de tuiles @+0x18
    + mode d'occupation main/steppable @+0x20 -> resolveur board) et un mort n'est plus sur sa tuile
    (KillUnit retire l'unite du board) — un cadavre de `ctx.units` (state garde alive=False) ne doit
    donc jamais sortir d'un selecteur d'occupation. Les selecteurs d'ENSEMBLE font leur propre choix
    (`AllUnits`=alive #202, `UnitsDefeatedByMeleeAttack`=morts expres) : le filtre vit ICI, pas dans
    ctx.units.

    `center` accepte les DEUX domaines (mirror natif : `AdjacentUnits`/`SurroundingUnits` prennent une
    ENTITE et le resolveur de tuiles en lit la `MainTile` — meme dualite que `AdjacentTiles`, deja
    documentee) : une POSITION `(col,row)` **ou** un dict d'unite (-> sa position). Un centre non
    resolvable (unite sans position) -> aucun voisin.

    `board`+`order` = ORDRE D'ENUMERATION NATIF (R28-1). Le natif ne parcourt PAS les entites : il
    ITERE les TUILES du selecteur (`Units(AdjacentTiles/SurroundingTiles(...))`) et resout l'occupant
    de chacune -> l'ordre de sortie est celui des TUILES, pas celui de `ctx.units`. Sans board (tests
    unitaires, contextes offline sans graphe) l'ordre historique `ctx.units` est conserve : c'est une
    DEGRADATION, jamais un mirror. Le tri est STABLE et l'ENSEMBLE est INCHANGE — une unite dont la
    tuile n'apparait pas dans l'enumeration (arete d'adjacence absente du `boardGraph` alors que la
    distance hex vaut 1) reste presente, en fin de liste : le natif, lui, ne la verrait pas du tout
    (porte |delta elevation| < 2 d'`IterateAdjacentTiles`) -> RESIDU distinct, non traite ici."""
    if isinstance(center, dict):                      # entite -> MainTile (mirror UnitsOnTilesSelector)
        center = _pos(center)
    if center is None:
        return []
    out = []
    for u in units:
        if not _is_alive(u):
            continue
        p = _pos(u)
        if p is None:
            continue
        d = hexgeo.distance(p, center)
        if d <= radius and (include_center or d > 0):
            out.append(u)
    if board is None or order is None or len(out) < 2:
        return out
    rank = _tile_enum_rank(board, center, radius, order)
    if not rank:
        return out
    big = len(rank) + 1
    return sorted(out, key=lambda u: rank.get(_pos(u), big))   # STABLE : hors-rang en fin, ordre garde


def _round_fix64(value: Fraction, mode: int) -> int:
    """`IdunBattle.DSL.AAmountFormula$$RoundFix64Result` : arrondit un quotient Fix64 en int selon `mode` (3ᵉ arg des
    factories Divide/Half/PercentageOf) : `1`=Ceiling, `2`=Floor, sinon (`0`)=Round half-to-even
    (`Fix64.Round`). On modélise le Fix64 par un `Fraction` EXACT (précision ≫ Fix64 pour des entrées
    entières) ; `round(Fraction)` = arrondi banquier (half-to-even), fidèle au mode 0."""
    if mode == 1:
        return math.ceil(value)
    if mode == 2:
        return math.floor(value)
    return round(value)


def calculate_average(min_value: int, max_value: int) -> int:
    """`IdunBattle.DSL.AAmountFormula$$CalculateAverage` — la MOYENNE d'un nœud VALEUR *à plage*,
    et elle **TRONQUE**. Mirror du décompilé `rnca9r7q6c`, branche « plage » :

        min = <vtable+0x1e8>(entities)      # CalculateMin
        max = <vtable+0x1f8>(entities)      # CalculateMax
        return (max + min) / 2              # division ENTIÈRE C — AUCUN Fix64 sur cette branche

    ⚠ **Ce n'est ni `IdunBattle.Core.Services.MinMaxDamage$$Avg` ni
    `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamageAverage`**, qui arrondissent tous deux
    demi-vers-le-PAIR (`Fix64.Round(., midpointRounding = 0)` pour le premier ;
    `Half(Sum(…))` → `IdunBattle.Entities.Formulas.DivideAmount$$Calculate` →
    `AAmountFormula$$RoundFix64Result` mode 0 pour le second). Les deux familles divergent dès que
    `min + max` vaut **3 mod 4** : sur `2761 + 2762` le natif de CETTE fonction rend `2761`, les deux
    autres rendent `2762`. Ne jamais substituer l'une à l'autre — c'est le sujet de #339.

    L'autre branche du décompilé (booléen `vtable+0x1c8` vrai → `Calculate()` direct) court-circuite
    la plage ; elle n'est PAS empruntée par un `RandomAmount`, ce que confirme la réconciliation
    live de `probe_32d_fury.py` (un `Calculate()` de `RandomAmount` est un TIRAGE, il ne pourrait pas
    tomber sur la moyenne exacte des deux cibles).

    Consommateur porté : `IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction`
    (slot 4 d'`IAmountFormula` sur le `RandomAmount(minDmg, maxDmg)` rendu par
    `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage`).

    Division C = troncature vers ZÉRO (pas le plancher Python). Le rail de dégât ne produit pas de
    somme négative ; la transcription la couvre quand même plutôt que de la laisser diverger en
    silence."""
    s = int(min_value) + int(max_value)
    return -((-s) // 2) if s < 0 else s // 2


def _c_mod(a: int, b: int) -> int:
    """Modulo ENTIER signé à la C (`%` tronqué vers zéro, signe du dividende) — ≠ `%` Python (plancher).
    Fidèle à `ModuloAbilityTrigger` (`iVar15 % iVar16`, opérandes signées)."""
    r = abs(a) % abs(b)
    return -r if a < 0 else r


def _same_entity(a, b) -> bool:
    """Égalité d'entité (mirror `AreEqual` sur des références d'entité) : même objet ou même id."""
    if a is None or b is None:
        return a is b
    return a is b or a.get("id") == b.get("id")


def _units_of(node, ctx) -> list:
    """Normalise l'évaluation d'un opérande-sujet en list[unit] : un dict → `[dict]` (cas `Subject` sous
    Filter), une liste → telle quelle, None → `[]`. Les prédicats unité appliquent un `any` dessus."""
    v = node.evaluate(ctx)
    if v is None:
        return []
    if isinstance(v, dict):
        return [v]
    return list(v)


def _effect_field(e, field, default):
    """Lit un champ de l'effet courant (`ctx.effect`), dict ou objet."""
    if e is None:
        return default
    if isinstance(e, dict):
        return e.get(field, default)
    return getattr(e, field, default)


def _is_alive(u) -> bool:
    return bool(u.get("alive", True)) and (u.get("hp") or 0) > 0


def _default_get_stat(u, stat_type, variant, level):
    """Défaut dégradé de `ctx.get_stat` : seule la santé est captée offline (le vrai accès stats vient
    de `ctx.get_stat` fourni par la couche ability)."""
    # HARDCODE (degrade) : StatType.Health=5 (dump.cs) -- seul stat lisible dans le state offline
    # {id,team,hp,alive,pos,visualId} ; autres StatType -> 0 tant que ctx.get_stat reel absent.
    # TEMP : variant base/current/max non tranche (validator) -- on rend le hp COURANT (natif lit maxHP).
    if stat_type == 5:
        return u.get("hp") or 0
    return 0
