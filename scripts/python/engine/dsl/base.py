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
from ..entities.pathfinding.board import adjacent_neigh_by_pos
from ..entities.pathfinding.board import elevations_by_pos


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
    # Élévation par tuile (`tile→[0x20]→[0x18]`) — consommée par les selectors gated élévation
    # (`TilesOnSameElevationSelector`, `FilterTilesIfCanAttackTargetTileFrom`). NON fourni →
    # DÉRIVÉ du `board` par `__post_init__` (#433-r4-r1-r4) ; reste None si le board est absent ou
    # sans canal d'élévation, et le filtre dégrade alors en no-op (documenté par nœud).
    elev_by_pos: dict | None = None
    # `{(col,row): [(col,row), …]}` — le VOISINAGE natif (`boardGraph.neighbours`, la liste STOCKÉE
    # du `ConnectivityComponent` que rend `TileQuery$$IterateAdjacentTiles`). C'est le PREMIER étage
    # de `battle_query.is_adjacent`, dont `elev_by_pos` ci-dessus est le second (#433-r4-r1-r4-r2).
    # NON fourni → DÉRIVÉ du `board` par `__post_init__`, même règle et même tri-état.
    neigh_by_pos: dict | None = None
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
    # ÉQUIPE du joueur dont c'est le tour (`TeamComponent.<+0x24>` du joueur courant) — lue par le
    # nœud `CurrentPlayerIsOfTeam`, mirror du triplet `AreEqual(CurrentPlayer, Player(<team>))` de
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets`.
    # ⚠ DISTINCT de `current_player_id` ci-dessus : `IdunBattleLogic.Entities.DSLSelectors$$Player`
    # prend une **team** (son paramètre est nommé `team` au décompilé, transmis à
    # `PlayersByTeamSelector$$.ctor`), pas un numéro de joueur — les deux coïncident sur un duel
    # 1v1 et divergent dès qu'un camp compte plusieurs joueurs. None = **non mesuré** → le nœud
    # rend False (dégradation conservatrice nommée, jamais une équipe devinée).
    current_player_team: int | None = None
    # Nombre de tours DÉMARRÉS par le joueur d'une unité (`TurnComponent+0x38`, le dict PAR JOUEUR
    # que rend `TurnComponent.GetAmountOfTurnsStartedByPlayer`) — lu par le nœud `PlayerTurnsStarted`
    # (`IdunBattleLogic.Entities.DSLFormulas$$PlayerTurnsStarted` →
    # `IdunBattle.Entities.Formulas.UnitsPlayerTurnsStartedFormula$$Calculate`). `player_turns_started
    # (unit) -> int` ; défaut None → 0 (même dégradation que le natif sur `unit == null`). Fourni par
    # la couche runner (`entities_from_state`, lit `State.turn_counts`).
    # ⚠ DISTINCT de `get_stat(unit, 0xc)` (compteur PER-UNITÉ `UnitComponent+0x58`) que lit le nœud
    # `UnitTurnsStarted` : les deux existent, et les confondre décale la phase d'un cycle `Modulo`.
    player_turns_started: object | None = None
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
    # Acces aux INSTANCES d'effet par PORTEUR -- mirror de l'AUTRE surcharge de la meme famille,
    # `IdunBattleLogic.Entities.DSLSelectors$$EffectFromOwner(effectTarget, effectType)` (celle a
    # DEUX arguments : `effectTarget` est un SELECTEUR d'unites, pas l'owner implicite du contexte).
    # `effects_of_units(unit, effectType) -> list[{"effect_type", "owner_id", "level"}]`, une entree
    # par instance PORTEE par `unit`. `level` est le champ que somme
    # `IdunBattle.Entities.Formulas.EffectLevelFormula$$Calculate` (`EffectComponent+0x68`).
    # Defaut None -> selecteur degrade [] (documente au noeud `EffectsOfUnits`). Fourni par la couche
    # runner (`entities_from_state`, lit `state.effects`).
    effects_of_units: object | None = None
    # `SortUnitsByDamageUtilitySelector$$Select` PAR APPEL -- `sort_units_by_damage_utility(
    # candidate_ids, dmin, dmax, owner_id, hits, ability_type) -> list[id]` (les candidats TRIES par
    # utilite Damage DECROISSANTE). Le `$$Select` complet vit dans `runner/operations/damage_utility`
    # (porte et confronte live) ; l'accesseur est ce qui permet au NOEUD DSL de l'appeler sans que
    # `entities/` importe `runner/`. Defaut None -> le noeud rend sa source INTACTE (degradation
    # nommee : sans `State` la prediction native n'est pas evaluable). #889-r5.
    sort_units_by_damage_utility: object | None = None
    # `IBattleQuery` slot **40** `GetMultiHitAttackPrediction` PAR APPEL -- `attack_prediction(
    # attacker_id, defender_id, amount, hits, damage_profile, is_melee) -> dict|None` (les champs de
    # composite : `healthDmgMin/Max`, `kill`, `killSure`). Lu par le noeud VALEUR
    # `entities.formulas.DamagePredictionFormula`, MEME foyer que `sort_units_by_damage_utility`
    # ci-dessus (`runner/operations/attack_prediction`). Defaut None -> le noeud rend 0 APRES avoir
    # consomme son tirage (degradation nommee : sans `State` la prediction native n'est pas
    # evaluable, et l'ordre du tri retombe sur l'ordre SOURCE, ce que la stabilite de l'`OrderBy`
    # natif produit aussi a egalite parfaite). #927.
    attack_prediction: object | None = None
    # Faction (`FactionId` gameconfig) PAR UNITÉ (mirror `DSLFactory.UnitsFromFaction`, qui compare vs
    # `Enum.ToString(UnitFaction)` = le NOM de faction) — hors state standard, comme `has_trait`/`get_stat`.
    # `faction_of(unit)->str|None` défaut None → faction inconnue (UnitsFromFaction rend vide). Fourni par la
    # couche runner (`entities_from_state`) via `_faction(visualId)`.
    faction_of: object | None = None
    # `IdunBattle.Entities.Components.WeaponsComponent$$HasRangedWeapon(minRange = null)` PAR UNITE
    # -- `has_ranged_weapon(unit) -> bool` : l'unite porte-t-elle au moins une arme NON `IsMelee`
    # (seuil `Range >= 2`, cf. `IdunShared.Battle.WeaponProfile$$get_IsMelee`) ? Meme patron
    # d'accesseur que `has_trait`/`faction_of` : le natif lit le `WeaponsComponent` de l'ECS, hors
    # state standard. Lu par le selecteur `UnitsWithoutRangedWeapons`
    # (`IdunBattle.Entities.Selectors.UnitsWithoutWeaponsSelector$$Select`, qui inline la boucle).
    # Defaut None -> le selecteur ne filtre RIEN (polarite de la branche `unit == null` du natif,
    # qui GARDE l'entite) : une non-mesure ne fabrique pas un refus. Fourni par la couche runner
    # (`entities_from_state`) via `engine.services.battle_query.has_ranged_weapon(visualId)`.
    has_ranged_weapon: object | None = None
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
    # Valeur SCALAIRE persistante d'une unite (`IdunBattle.Entities.Components.PersistentDataComponent$$
    # TryGetPersistDatau003C__Il2CppFullySharedGenericStructTypeu003E`) : `persistent_data(unit, key)`
    # -> valeur ou None. Meme cle composite `(GetPersistentDataId(abilityOrEffect), dataKey)` que la
    # variante LISTE ci-dessus -- c'est le MEME `Dictionary` @+0x10 cote natif. Lu par la formule
    # `GetPersistentData` (mirror `IdunBattle.Entities.Triggers.GetPersistentDataFormula$$Calculate`)
    # et ecrit par les feuilles `AddPersistentData` / `ClearPersistentData`. Defaut None -> la formule
    # rend 0, exactement comme le `out` par defaut du `TryGetPersistData` natif sur cle absente.
    persistent_data: object | None = None
    # SOMME des valeurs ENTIERES de TOUTES les dataKeys d'une ability sur une unite, hors une liste
    # de cles exclues (`IdunBattle.Entities.Triggers.GetAllPersistentDataCombined$$SumAbilityData`) :
    # `persistent_data_all(unit, ability_or_effect, excluded_keys)` -> int. MEME `Dictionary` @+0x10
    # et MEME cle composite que les deux canaux ci-dessus. Lu par la formule
    # `GetAllPersistentDataCombined`. Defaut None -> la formule rend 0, comme le natif quand le
    # `TryGetValue(abilityId)` echoue. Le tri-etat ne se distingue pas d'un sac VIDE, et c'est
    # FIDELE : le natif rend 0 dans les deux cas (#965).
    persistent_data_all: object | None = None
    # EMPREINTE PRECEDENTE d'une unite (`PositionComponent+0x88`, ecrite par
    # `IdunBattle.Operations.SetUnitPositionOperation$$SavePreviousPosition`) : `previous_tiles(unit)`
    # -> list[(col,row)]. Lu par le selecteur `PreviousTile` (mirror
    # `IdunBattle.Entities.Selectors.PreviousTileSelector$$Select`). Defaut None -> [] (= le
    # `Nullable` VIDE, dont le natif rend une `List` NEUVE et vide).
    previous_tiles: object | None = None
    # Resolution d'un ID d'entite en unite (`IdunBattle.Core.IBattleState$$GetEntity(id)`, le slot
    # 0x29 qu'appelle `IdunBattle.Entities.Selectors.EntitiesFromPersistentDataListSelector$$Select`
    # pour transformer sa liste d'ids en ENTITES). `entity_by_id(id) -> unit|None` ; l'id inconnu
    # rend None, et le natif le JETTE silencieusement de la liste rendue. Defaut None -> le
    # selecteur rend [] (meme polarite que `persistent_data_list` absent). Fourni par la couche
    # runner (`entities_from_state`).
    entity_by_id: object | None = None
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
    # PENDANT QUANTITATIF du precedent (formule `StatNegativeModification`, mirror
    # `IdunBattle.Entities.Formulas.NegativeStatModificationFormula$$Calculate`) :
    # `negative_stat_modification(unit, statType)->int` = SOMME des VALEURS ABSOLUES des
    # modifications per-source < 0 de CETTE stat (>= 0). Meme dictionnaire per-source que
    # `has_negative_modifier`, mais accumule au lieu de rendre `true` au premier. Defaut None -> 0
    # (degradation RESTRICTIVE : le gate `AmountIsGreater(ratio, seuil)` d'OrbsOfDecay devient faux).
    # Fourni par `entities_from_state` (`UnitStats.negative_stat_modification`).
    negative_stat_modification: object | None = None
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
    # Verdict `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed(caster, target, scope,
    # removeEffects)` -- la surcharge a QUATRE arguments (slot 0x11), celle AVEC caster, consommee par
    # `IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select` (qui resout d'abord son PROPRE
    # selecteur de caster `+0x18`, puis appelle le slot avec `removeEffects = 1` litteral).
    # ⚠ Ce n'est PAS le pendant exact de `entity_can_be_repaired` ci-dessus : la surcharge lue par le
    # selecteur REPAIRABLE est celle a TROIS arguments (caster nul), celle du selecteur HEALABLE est la
    # 4-args. L'accesseur porte donc le caster.
    # `entity_can_be_healed(caster_unit, target_unit, scope, remove_effects) -> bool`. Defaut None
    # (contexte hors runner) -> le selecteur `Healable` rend [] : degradation NOMMEE par le noeud,
    # jamais un « tout passe ». Fourni par `entities_from_state`.
    entity_can_be_healed: object | None = None
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
    # Tri `IdunBattle.Entities.Selectors.SortTilesByUtilitySelector$$Select` :
    # `sort_tiles_by_utility(tiles, unit_id, utility_type) -> list` (ids de tuile, DECROISSANT).
    # Le noeud `SortTilesByUtility` DELEGUE ici parce que le calcul d'utilite a besoin du `State`
    # (feuilles gatees sur l'unite, effets de tuile, elevation...) que le `DslContext` ne porte pas
    # -- foyer UNIQUE `engine/utilities/tile.py::sort_tiles_by_utility`, partage avec les call-sites
    # deja portes qui COLLAPSENT `First(SortTilesByUtility(...))` en un helper.
    # None = contexte sans `State` -> le noeud rend l'ordre SOURCE inchange, ZERO calcul
    # (degradation nommee par le noeud). Fourni par `entities_from_state`.
    sort_tiles_by_utility: object | None = None
    # `AbilityEntities.IsFirstHit` (`IdunBattle.Entities.Abilities.AbilityEntities$$get_IsFirstHit`,
    # champ +0x110 = le `DamageAppliedResult` du coup courant) -> `Nullable<bool>` valant
    # `DamageAppliedResult.get_IsFirstHit` = `hitIndex == 0`. Lu par le SEUL predicat
    # `IdunBattle.Entities.Triggers.IsFirstHitInSeriesTrigger$$ShouldTrigger` (`HasValue ? Value : false`).
    # Defaut None = coup hors serie / index inconnu -> le predicat rend False (mirror du `!HasValue`).
    is_first_hit: bool | None = None
    # `IdunBattle.Entities.UnitExtensions$$HasTriggeredAbility(unit, triggeredAbilityType)` =
    # `unit.GetComponent<TriggeredAbilityComponent>()?.TryGetAbility(type)` -- le SEUL etage du
    # predicat `IdunBattle.Entities.Triggers.ActortHasTriggeredAbilityTrigger$$ShouldTrigger` (#577,
    # la faute de frappe « Actort » est celle du binaire, conservee VERBATIM par la regle de citation).
    # `has_triggered_ability(unit, triggered_ability_type) -> bool`. Defaut None (accesseur non
    # branche = contexte hors runner) -> le noeud rend False : degradation NOMMEE par le noeud, du
    # cote qui n'invente aucun declenchement. Fourni par `entities_from_state`, qui delegue au foyer
    # UNIQUE du substrat `entities/triggered_ability_type.py::entity_triggered_ability_ids` -- le
    # MEME que lit le gate `GetAbilityState` de `IdunBattle.Operations.
    # TriggerTriggeredAbilityOperation$$TriggerAbility` (`behaviours/lifecycle.py`). Deux artefacts
    # natifs distincts, un seul recensement du kit declenche.
    has_triggered_ability: object | None = None
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
    # `has_any_valid_target(unit_dict, ability_type) -> bool | None` : mirror du slot
    # `IBattleQuery.<64 = 0x40> HasValidTargets(unit, position, abilityType)`, le predicat que
    # `IdunBattle.Entities.Selectors.UnitsWithAnyValidTargetSelector$$Select` appelle PAR UNITE.
    # Fourni par `entities_from_state` ; le filtre vit dans `runner/abilities/targeting.py`, seul
    # port de la cascade de ciblage -- surtout pas un 2e filtre cote noeud.
    # TRI-ETAT : `None` (le rendu, pas l'attribut) = le masque de CETTE ability n'a pas ete RE-lu ;
    # attribut `None` = contexte hors runner -> le noeud rend [] et le DIT. Cf.
    # `entities/selectors/valid_targets.py`.
    has_any_valid_target: object | None = None
    # `normal_repair_type(unit_dict) -> int | None` : mirror d'`IdunBattle.Entities.UnitExtensions
    # $$GetRepairType` (`<ActiveAbilityComponent>+0x2c`), consomme par le noeud VALEUR
    # `entities/formulas.UnitNormalRepairType`. Fourni par `entities_from_state` ; la derivation vit
    # dans `runner/abilities/targeting.normal_repair_type_for`, seul port de cette lecture.
    # `None` (l'attribut) = contexte hors runner -> la formule rend le `Nullable` VIDE.
    normal_repair_type: object | None = None
    # `normal_attack_type(unit_dict) -> int | None` : mirror d'`IdunBattle.Entities.UnitExtensions
    # $$GetNormalAttackType`, que `IdunBattle.Entities.Selectors.HasAnyValidTargetSelector$$Select`
    # appelle PAR UNITE (la surcharge SANS ability de `UnitsWithAnyValidTarget`, cf.
    # `entities/selectors/valid_targets.py`). Symetrique exact de `normal_repair_type` ci-dessus :
    # la derivation vit dans `runner/abilities/targeting.normal_attack_type_for`, seul port de cette
    # lecture -- surtout pas une 2e derivation cote noeud.
    # `None` (l'attribut) = contexte hors runner -> le noeud rend [] et le DIT.
    normal_attack_type: object | None = None
    # Canal d'HONNETETE de `UnitsWithAnyValidTarget` : les `ActiveAbilityType` qu'il a ECARTES faute
    # de masque RE-lu. Ce n'est pas du natif -- c'est ce qui distingue « le natif exclut cette
    # unite » de « le port ne sait pas ». Reste VIDE dans le cas nominal ; `None` = personne ne
    # collecte (l'information est alors simplement perdue, jamais transformee en verdict).
    unknown_ability_types: object | None = None
    # `has_taken_damage_of_profile_this_turn(unit, damage_profile_id) -> bool` : mirror de
    # `IdunBattle.Entities.UnitExtensions$$HasTakenDamageOfDamageProfileThisTurn`, dont le corps
    # RELU est un `ContainsKey(ActorStatisticsComponent+0x80, damageProfileType)` -- PRESENCE de la
    # cle, jamais un compte (contraste `HasTakenDamageOfDamageProfileThisTurnAmountOfTimesTrigger$$
    # ShouldTrigger`, qui compare `== times`). C'est le canal du predicat DSL
    # `HasTakenDamageOfDamageProfileThisTurn` (`entities/triggers.py`). Defaut None -> False
    # (degradation fidele : aucun degat enregistre). Fourni par `entities_from_state`, qui lit
    # `UnitComponent.received_damage_this_turn` -- le MEME dict que
    # `runner/operations/triggers/loki/reality_unbound.py` et `.../weaver_of_fate.py`.
    has_taken_damage_of_profile_this_turn: object | None = None
    # #1015-r1 -- LES TROIS CANAUX DU TRAIT `InstinctiveBehaviour`, tous cables sur des foyers DEJA
    # portes (aucune 2e derivation cote noeud) :
    #   * `only_targets(unit_id) -> list[int]` : `IdunBattle.Entities.UnitExtensions$$GetOnlyTargets`
    #     (le `ForcedAttackTargetsComponent`), foyer `runner/abilities/targeting.get_only_targets`.
    #     Canal du selecteur `ForcedAttackTargets` ;
    #   * `is_in_attack_or_ability_range(attacker_id, target_id) -> bool` : la boucle
    #     `IdunBattle.Entities.Triggers.IsInAttackOrAbilityRangeTrigger$$ShouldTrigger` sur les
    #     abilities montees du caster + `IBattleQuery` slot 0x41 `IsValidTarget`, foyer
    #     `runner/abilities/targeting.valid_targets_for` (+ l'attaque NORMALE, que la
    #     `KeyedCollection` native contient et que `ActiveAbilitiesComponent` exclut) ;
    #   * `normal_attack_range(unit_id) -> int | None` : les trois branches d'arme de
    #     `IdunBattle.Core.Services.TargetingQuery$$GetRange`, foyer
    #     `runner/abilities/targeting.unit_weapon_range`. Canal de la formule `NormalAttackRange`.
    # `None` (l'attribut) = contexte hors runner -> chaque noeud degrade dans le sens PERMISSIF et
    # le DIT dans sa docstring.
    only_targets: object | None = None
    is_in_attack_or_ability_range: object | None = None
    normal_attack_range: object | None = None
    # `is_effect_target(unit_id, effect_type) -> bool | None` : `IdunBattleLogic.Entities.
    # DSLTriggers$$IsEffectTarget`, foyer `entities/effect_targets.py` (re-derivation de
    # `EffectComponent.Targets @+0x48` par le `<Effect>$$CreateTargetSelector` du type). TRI-ETAT
    # PRESERVE jusqu'au noeud, qui porte lui-meme la direction de sa degradation.
    is_effect_target: object | None = None

    def __post_init__(self):
        """`elev_by_pos` se DERIVE du `board` des qu'il n'est pas fourni -- le canal d'elevation
        n'est pas une option du contexte, c'est une propriete de la TUILE (#433-r4-r1-r4).

        Cote natif il n'existe aucun contexte « qui a des tuiles mais pas leur elevation » : chaque
        `TileEntity` porte son composant a `+0x20`, et les deux foyers de la porte le deref
        directement -- `TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`
        (`d = |elev(source) - elev(voisin)| ; if (d < 2) yield`, INCONDITIONNEL, apres les filtres
        terrain) et `MovementUtil$$AreTilesAdjacent` (`(|dElev| < 2) & (t1 == t2 || IsNeighbour)`).
        `TileExtensions$$GetElevationDifference` LEVE si le composant manque : l'ignorance n'est pas
        un etat natif.

        Cote port, le canal existait mais restait NON BRANCHE sur 4 des 11 constructeurs de
        `DslContext` -- dont `entities_from_state`, le substrat de TOUT behaviour runner. Les
        primitives `battle_query.is_adjacent` / `.are_entities_adjacent` degradaient alors en no-op
        PERMISSIF : ni erreur ni crash, un moteur qui ACCEPTE des adjacences que le natif refuse.
        Le brancher ICI plutot qu'a chaque call-site est ce qui empeche le prochain constructeur de
        rouvrir le trou en silence.

        `board` absent (arbre purement NUMERIQUE : `_hits_ctx`, `triggered_ability`) -> `None`, et
        la porte reste inerte faute de tuiles a gater. `board` sans canal d'elevation (board bati a
        la main dans un test, `boardGraph` anterieur au capteur) -> `None` AUSSI, jamais une carte
        vide : `elevations_by_pos` rend un TRI-ETAT, et le repli « les deux elevations connues,
        sinon on retient » de `is_adjacent` reste la degradation SURE (un faux NEGATIF d'adjacence
        supprimerait des actions legales -- pire que le trou qu'on ferme).

        `neigh_by_pos` suit EXACTEMENT la meme regle, et pour la meme raison (#433-r4-r1-r4-r2) :
        c'est le PREMIER etage de la primitive (l'enumeration de la liste STOCKEE) la ou
        `elev_by_pos` en est le second (la porte). Le natif n'a pas davantage de contexte « qui a
        des tuiles mais pas leur voisinage » -- `IterateAdjacentTiles` deref le
        `ConnectivityComponent` directement. La couronne hex qui lui servait de repli SUR-ATTEINT la
        liste stockee (mesure : 4 aretes dirigees sur `C1_74`, 38 sur `C3_14`, 0 restrictive), donc
        le laisser non branche etait la MEME degradation permissive."""
        if self.elev_by_pos is None and self.board is not None:
            self.elev_by_pos = elevations_by_pos(self.board)
        if self.neigh_by_pos is None and self.board is not None:
            self.neigh_by_pos = adjacent_neigh_by_pos(self.board)


class Const(AAmountFormula):
    """`DSLFactory.Direct(value)` : constante littérale (VALEUR)."""
    def __init__(self, value: int):
        self.value = value

    def calculate(self, ctx):
        return self.value


def _pos(u):
    """MAIN TILE d'une entite (`IdunBattle.Entities.EntityExtensions$$GetMainTile`, = la tuile du
    PREMIER pied). ⚠ N'EST PAS l'empreinte : tout noeud dont le natif passe par `GetTiles` /
    `TargetsSelector$$SelectTiles` doit lire `_feet` ci-dessous, pas ceci (#433-r3-r1)."""
    p = u.get("pos") if u else None
    return (p["col"], p["row"]) if p else None


def _feet(u) -> list:
    """EMPREINTE d'une entite = `IdunBattle.Entities.EntityExtensions$$GetTiles(entity, state)`, la
    materialisation en liste de `$$IterateTiles` : les tuiles de TOUS les pieds, dans l'ordre des
    pieds (donc `feet[0]` EST la main tile). C'est ce que rend
    `IdunBattle.DSL.TargetsSelector$$SelectTiles(entities)` pour chaque entite selectionnee :

        sel = Select(entities);
        if (<this est deja un selecteur de TUILES>) return sel;
        foreach (entity in sel) foreach (tile in EntityExtensions.IterateTiles(entity, state))
            out.Add(tile);
        return out;

    -- a ne pas confondre avec `$$SelectTile` (SINGULIER), qui rend `GetMainTile(entity)`.

    SUBSTRAT -- DEUX CANAUX, DEUX FORMES DE TUILE, et c'est LU au producteur, pas suppose :

      * face COMBAT : `runner/abilities/behaviours/context.py::_unit_dict`, alimente par
        `runner.components.get_unit_feet` (#R30/#91) -> des COUPLES `(col, row)` ;
      * face DECISION : `decisionView.units[].feet`, publie par le capteur `#419-r1-tr10-r2`
        (`projection.ts::readEntityFeet` = `EntityExtensions$$GetTiles`) -> des DICTS
        `{"col", "row"}`, la forme de `readTileCoord`.

    ⚠ LA SECONDE FORME A FAIT LEVER CE FOYER (`KeyError: 0`), et le repli documente ci-dessous en
    est la cause : jusqu'au 2026-08-10 la face DECISION n'avait AUCUN canal d'empreinte, donc ce
    `feet` etait toujours absent et la branche COUPLE etait la seule exercee. Le capteur a ouvert le
    canal sans que ce lecteur-ci soit adapte -- `entities/selectors/tiles.py` et
    `playbook/adjacency.py::_as_pos` sont les deux autres lecteurs, et seul le troisieme normalisait.
    On normalise donc ICI, au foyer que les selecteurs DSL consomment.

    Un dict SANS `feet` -- canal MUET (tri-etat `null`), contexte de test -- retombe sur `[_pos(u)]` :
    c'est la MAIN TILE seule, donc une DEGRADATION documentee et non un mirror. Elle est EXACTE pour
    toute unite mono-tuile (le natif rend alors lui aussi un seul pied) et ne peut diverger que sur
    une unite multi-hex, ou elle refuse ce que le natif accorde par un autre pied -- et cote
    DECISION elle etait meme FAUSSE d'un a deux hexes sur une multi-hex, `decisionView.units[].pos`
    etant le DERNIER pied projete et non la main tile (cf. `runner/snapshot.py::_load_feet`).
    Entite sans position du tout -> `[]` (le natif rend une liste vide, et ses consommateurs
    -- `AreTilesAdjacent(IList,IList)`, `GetMinDistance` -- ne bouclent alors sur rien)."""
    if not u:
        return []
    feet = u.get("feet")
    if feet:
        return [_as_tile(f) for f in feet]
    p = _pos(u)
    return [] if p is None else [p]


def _as_tile(f) -> tuple:
    """Normalise UNE tuile venue de l'un ou l'autre canal -> `(col, row)`.

    Pendant exact de `playbook/adjacency.py::_as_pos`, qui porte la meme normalisation pour le
    mirror d'adjacence. Aucune supposition sur le canal appelant."""
    if isinstance(f, dict):
        return (int(f["col"]), int(f["row"]))
    return (int(f[0]), int(f[1]))


def _origin_tiles(origin, board=None) -> list:
    """Les TUILES d'une ORIGINE de geometrie -- mirror de la boucle qui OUVRE les deux iterateurs
    natifs de voisinage :

        // IdunBattle.Core.Services.BattleQuery.u003CIterateAdjacentTilesu003Ed__95$$MoveNext
        // IdunBattle.Core.Services.BattleQuery.u003CIterateSurroundingTilesu003Ed__117$$MoveNext
        foreach (tile in EntityExtensions.IterateTiles(entity, state))
            foreach (t in tileQuery.Iterate<Adjacent|Surrounding>Tiles(tile, ...)) yield t;

    Donc `AdjacentTiles(origin)` / `SurroundingTiles(origin, r)` d'une entite MULTI-HEX unionnent le
    voisinage de TOUS ses pieds -- ce n'est PAS l'anneau de sa seule main tile (#433-r3-r1a).
    `BattleQuery$$GetAdjacentTiles` et `$$GetSurroundingTiles` collectent dans un `OrderedSet` :
    l'union est DEDOUBLONNEE et l'ordre est celui de la premiere apparition.

    DOMAINE MIXTE, comme le natif (qui manipule des ENTITES ECS) : dict d'unite -> son empreinte
    (`_feet`) ; position `(col,row)` -> `[pos]` ; LISTE de positions -> elles-memes ; id de tuile
    (int) -> `board.coord`.

    C'est le mirror de `IdunBattle.DSL.TargetsSelector$$SelectTiles` (le PLURIEL) :

        list = this.Select(entities);
        if (this.<IsTileSelector>) return list;            // deja des tuiles -> telles quelles
        foreach (e in list) foreach (t in EntityExtensions.IterateTiles(e, state)) result.Add(t);

    -- une entite y est DEPLIEE en son empreinte, une tuile passe telle quelle. Depuis #459 les
    accesseurs `CasterTile`/`TargetTile`/`OwnerTile` rendent eux aussi une LISTE (l'empreinte), donc
    l'origine n'est plus collapsee en amont ; le pendant SINGULIER est `_select_tile` ci-dessous."""
    if origin is None:
        return []
    if isinstance(origin, dict):
        return _feet(origin)
    if isinstance(origin, bool):
        return []
    if isinstance(origin, tuple) and len(origin) == 2 and all(
            isinstance(x, int) for x in origin):
        return [(int(origin[0]), int(origin[1]))]
    if isinstance(origin, int):
        c = board.coord(origin) if (board is not None and origin in getattr(board, "by_id", {})) \
            else None
        return [] if c is None else [(int(c[0]), int(c[1]))]
    if isinstance(origin, (list, tuple)):
        out: list = []
        for it in origin:
            for p in _origin_tiles(it, board):
                if p not in out:
                    out.append(p)
        return out
    return []


def _main_tile(origin) -> tuple | None:
    """La MAIN TILE d'une origine -- mirror `IdunBattle.Entities.EntityExtensions$$GetMainTile`, et
    c'est EXACTEMENT ce que soustrait le natif quand `includeCenter == 0` :

        // IdunBattleLogic.Entities.DSLSelectors$$SurroundingTiles, branche includeCenter == 0
        SurroundingTiles(origin, includeCenter: 1, ...) op_Subtraction Tiles(origin)

    et `Tiles` = `IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select` = `GetMainTile` PAR
    ENTITE. Donc l'exclusion du centre retire UNE SEULE tuile : les pieds SECONDAIRES d'une origine
    multi-hex RESTENT dans l'anneau, et l'origine peut donc se selectionner elle-meme. Retrancher
    toute l'empreinte serait une SECONDE erreur, pas une correction."""
    ts = _origin_tiles(origin)
    return ts[0] if ts else None


def _select_tile(origin, board=None) -> tuple | None:
    """UNE tuile depuis une origine de domaine MIXTE -- mirror 1:1 de
    `IdunBattle.DSL.TargetsSelector$$SelectTile` (le SINGULIER, vslot 0xc) :

        foreach (e in this.Select(entities)) {
            if (e == null) continue;
            if (EntityExtensions.IsTile(e)) return e;                       // une TUILE : telle quelle
            if (IsUnit(e) || IsUnitFoot(e)) { t = GetMainTile(e, state); if (t != null) return t; }
        }
        return null;

    C'est le contrat que lisent les consommateurs SCALAIRES du natif, tous verifies au decompile :
    `IdunBattle.Entities.Selectors.MovableTilesInRangeSelector$$Select` (son `unitTileSelector`
    @+0x28, qui remplace le `GetMainTile(unit)` par defaut), `IdunBattle.Entities.Selectors.
    TilesBehindInLineSelector$$Select` (origin @+0x18 ET direction @+0x20) et le referent de
    `IdunBattle.Entities.Selectors.SortByDistanceSelector$$Select` (dont le comparateur ferme sur UN
    `PositionComponent`). Sur une origine MONO-hex il rend exactement ce que rendait l'accesseur
    scalaire d'avant #459 -- la premiere tuile de l'empreinte EST la main tile."""
    ts = _origin_tiles(origin, board)
    return ts[0] if ts else None


def _occupants_by_tile(units) -> dict:
    """Index `{(col,row) -> unite}` = mirror de la resolution d'occupant NATIVE, dont le foyer unique
    est `IdunBattle.DSL.TargetsSelector$$SelectUnit(entity, selectionType)` (surcharge ENTITE) :

        if (EntityExtensions.IsUnitFoot(e) || EntityExtensions.IsTile(e))
            e = UnitExtensions.GetUnit(e, state);
        return (e != null && IsUnit(e) && MatchesUnitSelectionType(e, selectionType, state)) ? e : null;

    et `IdunBattle.Entities.UnitExtensions$$GetUnit` sur une TUILE lit son `TileContentComponent`
    (`IsFilled` -> `state.GetEntity(content)`), puis BOUCLE : le contenu d'une tuile est l'entite-PIED
    (`IdunBattle.Entities.Blueprints$$UnitFoot` -> `IdunBattle.Core.FootEntity`), que la surcharge
    PIED re-resout en son unite proprietaire. ⇒ **N'IMPORTE QUEL pied d'une unite multi-hex resout
    en cette unite** ; le port indexait par `_pos` (main tile) et voyait donc VIDE une tuile occupee
    par un pied secondaire (#433-r3-r1a).

    VIVANTS SEULEMENT (#57m) : un mort n'est plus sur sa tuile (`KillUnit` la libere), donc son
    `TileContentComponent` est vide -- meme filtre que les autres consommateurs d'occupation.

    ⚠ `MatchesUnitSelectionType` (`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType` :
    `0`=tout, `1`=vivant, `2`=non-`HasFlag(0x11)`, `3`=vivant ET non-`HasFlag(0x11)`) n'est PAS porte
    ici -- c'est le residu `#433-r3-r2`, qui demande de relever le `selectionType` a chaque call-site.

    Premiere occurrence gagnante dans l'ordre de `units` : le natif n'a qu'UN occupant par tuile
    (`TileContentComponent` est un slot unique), donc la collision n'existe pas cote natif ; c'est une
    tie-break de port pour un state incoherent."""
    occ: dict = {}
    for u in units:
        if not _is_alive(u):
            continue
        for p in _feet(u):
            occ.setdefault((int(p[0]), int(p[1])), u)
    return occ


def _adjacent_tiles_native(board, centers) -> "list | None":
    """`IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` -- LES TUILES, en TRI-ETAT.
    FOYER UNIQUE de l'etage `adjacent` : `_tile_enum_rank` en tire l'ORDRE et `_within`
    l'ENSEMBLE, et les deux doivent etre la MEME liste (#515, residu `#497-r1`).

    Rend la CONCATENATION, dans l'ordre des pieds, des voisinages natifs de chaque tuile de
    `centers` -- l'`OrderedSet` que le natif remplit. Tri-etat, et c'est ce qui fait toute la
    difference :

      * `None` = **aucun centre resolvable sur ce board** (board absent, ou tuile hors capture)
        -> l'appelant DOIT replier sur la geometrie. Degradation PERMISSIVE et nommee, jamais un
        voisinage vide (meme contrat que `battle_query.is_adjacent` / `neigh_map`).
      * `[]` = centre resolu, **zero voisin**, et c'est un resultat EXACT. Un board reel le
        produit : `TileQuery$$IterateAdjacentTiles` porte une porte `|dElev| < 2`
        INCONDITIONNELLE, donc une tuile dont tous les voisins stockes sont a 2 niveaux ou plus
        ressort a vide -- mesure `C1_74`, les deux `Water` `(2,5)`/`(4,5)` a elevation 1
        entourees de 3 et 4. Confondre les deux cas est le vice exact de `#381-r3` (il
        INVENTAIT six voisins la ou le natif n'en a aucun), et le rejouer ici rendrait la
        reparation inerte precisement sur les tuiles qu'elle vise.

    LE SUBSTRAT PORTE DEJA LES DEUX ETAGES. `Board.neighbours_native` lit le champ
    `boardGraph.neighbours`, capte par `BattleQuery$$GetAdjacentTiles(t, false, false, true)` --
    donc par CE MEME iterateur, filtres de terrain OFF et porte d'elevation ON. Identite LUE :
    `neighbours == connectivity INTERSECTE {aretes de |dElev| < 2}` (cf.
    `Board.base_add_neighbours`). Rejouer la porte ici serait redondant, pas plus fidele."""
    if board is None or not centers:
        return None
    positions: list = []
    resolu = False
    for c in centers:
        if c is None:
            continue
        tid = board.id_at(c[0], c[1])
        if tid is None:
            continue                     # cette tuile-la n'est pas sur le board capte
        resolu = True
        for t in board.neighbours_native(tid):
            xy = board.by_id.get(t)
            if xy is not None:
                positions.append((xy["col"], xy["row"]))
    return positions if resolu else None


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
    sous les `OrderBy` natifs, qui sont STABLES (cf. fc23f1e).

    `center` accepte UNE position **ou** la LISTE des tuiles de l'origine (son empreinte, #433-r3-r1a) :
    le natif enumere `foreach tile in IterateTiles(origin)` puis le voisinage de chaque tuile, et
    collecte dans un `OrderedSet` -> concatenation dans l'ordre des PIEDS, dedoublonnee, premiere
    apparition gagnante."""
    if board is None or center is None:
        return {}
    centers = (list(center) if isinstance(center, list)
               else [center] if isinstance(center, tuple) and len(center) == 2 else [])
    positions: list = []
    if order == "adjacent" and int(radius) == 1:
        # meme liste que celle dont `_within` tire l'ENSEMBLE (#515) : l'ordre et l'appartenance
        # ne peuvent pas venir de deux sources. `None` (aucun centre resolvable) -> aucun ordre
        # impose, exactement comme avant.
        positions = _adjacent_tiles_native(board, centers) or []
    else:
        for c in centers:
            if c is None:
                continue
            positions.extend(hexgeo.disk(c[0], c[1], int(radius)))
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
    ENTITE, que `BattleQuery$$Iterate<Adjacent|Surrounding>Tiles` ouvre en son EMPREINTE) : une
    POSITION `(col,row)`, une LISTE de positions, **ou** un dict d'unite (-> ses pieds). Un centre non
    resolvable (unite sans position) -> aucun voisin.

    `board`+`order` = ENUMERATION NATIVE DES TUILES (R28-1). Le natif ne parcourt PAS les entites :
    il ITERE les TUILES du selecteur (`Units(AdjacentTiles/SurroundingTiles(...))`) et resout
    l'occupant de chacune -> l'ordre de sortie est celui des TUILES, pas celui de `ctx.units`.

    ⚠ ET L'ENUMERATION DECIDE AUSSI DE L'APPARTENANCE, pas seulement de l'ORDRE (#515, residu
    `#497-r1`) -- c'est ce que cette fonction se trompait de faire. Les deux `order` ont des
    iterateurs natifs DISTINCTS, et un seul des deux est une couronne geometrique :

      * `order='adjacent'` (rayon 1) -- `IdunBattle.Core.Services.TileQuery.u003C
        IterateAdjacentTilesu003Ed__8$$MoveNext` enumere la liste STOCKEE
        (`tile.ConnectivityComponent.Neighbours`) puis applique une porte `|dElev| < 2`
        INCONDITIONNELLE. **Ce n'est PAS `hexgeo.distance <= 1`** : la couronne hex SUR-ATTEINT
        des que le terrain saute une marche. Substrat : `_adjacent_tiles_native`, qui porte les
        deux etages (le champ `boardGraph.neighbours` est capte a travers ce meme iterateur).
        Sans centre resolvable sur le board -> repli GEOMETRIQUE nomme (permissif), jamais un
        voisinage vide.
      * `order='surrounding'` (rayon quelconque) -- `IdunBattle.Core.Services.TileQuery.u003C
        IterateSurroundingTilesu003Ed__6$$MoveNext` est une TRIPLE BOUCLE en coordonnees CUBE
        resolue par `StateExtensions$$GetTileAt` : **aucune liste stockee, AUCUNE porte
        d'elevation**. La distance hex y est le mirror EXACT -- brancher les deux `order` sur la
        meme primitive serait un bug, pas une unification.

    Sans board (tests unitaires, contextes offline sans graphe) : ensemble geometrique et ordre
    historique `ctx.units`. C'est une DEGRADATION, jamais un mirror.

    AMPLITUDE MESUREE (`probe_515_adjacence_rayon_de_souffle.py`, 675 boards) : la porte refuse
    **17 204** aretes de couronne sur **196 454** (8,76 %), et MORD sur **586 boards / 675**
    (86,8 %). Sur `MC1_67` : 18 aretes dirigees, 11 tuiles -- exactement ce que la mesure LIVE de
    #497 avait trouve. La reparation est MONOTONE (0 violation d'inclusion sur les 675 boards) :
    elle ne peut que RETIRER des unites, jamais en ajouter.

    EMPREINTES (#433-r3-r1a) -- les DEUX bouts de la relation lisent desormais les pieds :
      * le CENTRE, par `_origin_tiles` (mirror du `foreach tile in IterateTiles(entity)` qui ouvre
        `BattleQuery$$IterateAdjacentTiles` / `$$IterateSurroundingTiles`) : le voisinage d'une
        entite multi-hex est l'UNION du voisinage de ses pieds ;
      * l'OCCUPANT, par `_feet` (mirror `TargetsSelector$$SelectUnit` -> `UnitExtensions$$GetUnit`
        -> `TileContentComponent`) : une unite est prise des qu'UN de ses pieds tombe dans l'anneau.

    L'EXCLUSION DU CENTRE N'EST PAS LA MEME DES DEUX COTES (#459), et les deux formes ne se
    distinguent que sur une origine MULTI-HEX -- c'est `order` qui tranche, parce que c'est le
    SELECTEUR natif qui porte l'exclusion, pas le rayon :

      * `order='adjacent'` -- l'exclusion est INTERNE a
        `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select`, qui resout son origine par
        `TargetsSelector$$SelectTiles` (donc l'EMPREINTE) puis n'ajoute une voisine que
        `if (!tiles.Contains(a))`. On retranche donc TOUTES les tuiles du centre. Le
        `op_Subtraction(units, origin)` que `DSLSelectors$$AdjacentUnits`/`$$AdjacentEnemies`
        appliquent par-dessus est alors redondant sur ce chemin (il retire l'ENTITE origine, deja
        absente puisque tous ses pieds sont hors anneau).
      * `order='surrounding'` -- l'exclusion est EXTERNE :
        `DSLSelectors$$SurroundingTiles(origin, includeCenter: 0, ...)` vaut
        `SurroundingTiles(origin, includeCenter: 1, ...) op_Subtraction Tiles(origin)`, et
        `Tiles` = `IdunBattle.Entities.Selectors.UnitsMainTilesSelector$$Select` = `GetMainTile`
        par ENTITE. On ne retranche donc QU'UNE tuile, et une origine multi-hex peut se selectionner
        elle-meme par un pied secondaire. Retrancher toute l'empreinte y serait une seconde erreur.

    Sur des unites MONO-tuile les deux formes coincident et se reduisent terme a terme a l'ancienne
    (`d <= radius and (include_center or d > 0)`) -- aucune variation possible hors multi-hex."""
    centers = _origin_tiles(center, board)
    if not centers:
        return []
    if include_center:
        excluded: tuple = ()
    elif order == "adjacent":
        excluded = tuple(centers)                     # `AdjacentTilesSelector` : !tiles.Contains(a)
    else:
        m = _main_tile(center)                        # `op_Subtraction Tiles(origin)` : UNE tuile
        excluded = () if m is None else (m,)
    r = int(radius)
    # L'ENSEMBLE vient de l'enumeration native des que l'iterateur natif en est une (#515).
    # `None` = aucun centre resolvable -> repli geometrique nomme ; `[]` = zero voisin, EXACT.
    enumeres = (_adjacent_tiles_native(board, centers)
                if (order == "adjacent" and r == 1) else None)
    tuiles = None if enumeres is None else {(p[0], p[1]) for p in enumeres}
    out = []
    for u in units:
        if not _is_alive(u):
            continue
        for f in _feet(u):
            if f in excluded:
                continue
            if (f in tuiles) if tuiles is not None else any(hexgeo.distance(f, c) <= r
                                                            for c in centers):
                out.append(u)
                break
    if board is None or order is None or len(out) < 2:
        return out
    rank = _tile_enum_rank(board, centers, radius, order)
    if not rank:
        return out
    big = len(rank) + 1
    # rang d'une unite = celui du PREMIER de ses pieds atteint par l'enumeration des tuiles (le natif
    # itere les TUILES et resout l'occupant de chacune : la premiere occurrence fixe la position).
    return sorted(out, key=lambda u: min([rank.get(f, big) for f in _feet(u)] or [big]))


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
    """LIVENESS d'un dict d'unite pour les selecteurs -- `bool(alive)` (le pool `AliveUnits` de
    `IdunBattle.Entities.UnitExtensions$$IsAlive`) ET
    `IdunBattle.Entities.Components.HealthComponent$$IsAlive`, dont les branches sont :

        if (RemainingValue@+0x18 >= 1)         return true;    // PV > 0 -> VIVANT
        if (get_CurrentMaximumValue() > 0)     return false;   // PV <= 0 mais un MAX -> MORT
        if (<+0x1c> HasValue)                  return Value != -1;
        return true;                                           // PV <= 0 ET max <= 0 -> VIVANT

    ⚠ La 3e branche EST exercee : mesure #589-r1-r1-r2-r1-r8, `genesSmnDecoy` (`C3_14`, seed 777)
    porte `hp = 0` ET `hpMax = 0` avec `alive = true`, et le natif la COMPTE (compteur
    d'`AmuletOfTheVoidwyrm_CritDamageReduction` lu du DEGAT = 1). Le `hp > 0` seul la retirait de
    `_within`, donc de TOUT selecteur d'occupation -- sans erreur.

    DEUX degradations NOMMEES, toutes deux conservatrices (elles gardent le verdict d'avant) :
      * `hpMax` ABSENT du dict (face DECISION, dicts de test, entite-TUILE de `_tile_entity`) ->
        MORT, comme avant. Etendre << sans sante >> a tout ce qui ne publie pas son maximum ferait
        entrer les TUILES dans les selecteurs d'occupation ;
      * le plancher `+0x1c` n'est pas dans le dict -> la branche `Value != -1` n'est pas portee.
        Elle ne mord que sur une unite a `hp <= 0`, `max <= 0` ET plancher pose : regime non
        mesure. Le foyer ENTITE, lui, la porte (`runner/components.py::unit_is_alive`)."""
    if not bool(u.get("alive", True)):
        return False
    if (u.get("hp") or 0) > 0:
        return True
    hp_max = u.get("hpMax")
    return hp_max is not None and int(hp_max) <= 0


# ── #270-r4-r2 : cet import est MODULE-LEVEL, et sa PLACE EN FIN DE FICHIER est fonctionnelle ──
#
# Il etait DIFFERE (dans le corps de `_default_get_stat`), donc invisible a l'import et paye a
# chaque appel. Le hisser EN TETE leve un vrai `ImportError`, MESURE, pas redoute :
#     engine.dsl.base -> engine.entities (init du PAQUET, inevitable) -> effects_state
#     -> effects -> factory -> effects.loki -> ability_modifications -> entities.selectors
#     -> selectors._shared -> `from ...dsl.base import TargetsSelector`  <- pas encore defini
# `TargetsSelector` est defini plus haut dans CE fichier (classe unique lue par ce chemin) : place
# ICI, l'import trouve un module deja complet pour ce dont la boucle a besoin, et l'echec eventuel
# redevient DETERMINISTE (a l'import) au lieu de dependre du chemin d'execution.
# Le remonter fait rougir `probe_270r4r2_import_en_premier.py`. La coupe qui rendrait cette place
# indifferente est de sortir l'arbre des effets de `engine/entities/__init__.py` -- rayon mesure :
# 41 fichiers lisent 9 symboles de ce paquet. Residu ouvert, cf. la fiche #270-r4-r2.
from ..entities.stats import StatType   # noqa: E402


def _default_get_stat(u, stat_type, variant, level):
    """Défaut dégradé de `ctx.get_stat` : seule la santé est captée offline (le vrai accès stats vient
    de `ctx.get_stat` fourni par la couche ability)."""
    # HARDCODE (degrade) : seul stat lisible dans le state offline {id,team,hp,alive,pos,visualId} ;
    # autres StatType -> 0 tant que ctx.get_stat reel absent.
    # TEMP : variant base/current/max non tranche (validator) -- on rend le hp COURANT (natif lit maxHP).
    if stat_type == StatType.HEALTH:               # 5
        return u.get("hp") or 0
    return 0
