"""Spawn d'unité SUMMON — port de `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` (ability du SUMMONER)
→ `DSLFactory.Spawn` → `AddUnitOperation.Execute`.

GROUND TRUTH (RE ghidra + live, cf. project_summon_team_model) — `ScarabHiveAbility IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` (necroSpyder) :
  - **visualId** = `GetStringConstant(config, 0)` = `gameconfig.ability(ScarabHive).constants["unitId"]`
    = `necroSmnSwarm` ;
  - **count**    = nb d'invocations de l'ability (ScarabHive = `2`, arg du `.ctor AActiveAbility`) ;
  - **placement**= `AdjacentTiles(target@0x178)` → `CanAddUnit` → `SortByDistance(self@0x160)` → `First` =
    tuiles LIBRES adjacentes à la **CIBLE**, la plus proche du caster (cf. `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$GetPossibleSpawnTiles`) ;
  - **owner**    = team ET player du caster (validé live team=1 player=3 ; ≠ PlayerIdGenerator) ;
  - **stats**    = `ability_var(ScarabHive, summonHp/summonDmg/summonArmor/summonCritChance/summonCritDmg,
    casterActiveAbilityLevel, casterMultiplier)` (clés `variablesAffectedByRarityBonus` → ×multiplier) ;
  - **effet posé** = `AddEffect(0x4a3)` = `ScarabHive_OverrideDamageProfileEffect` sur le scarab spawné ;
  - **on-appearance** = `UseNormalAttackIfAble` (attaque normale immédiate — PAS `PerformAIAttack`).

Le scarab spawné (`necroSmnSwarm`) porte SON PROPRE kit — DÉCISIF pour `ai_controlled` (cf. #65) :
  - **trait `Summon`** = « Moves and attacks automatically at the beginning of its turn » → il est joué
    par l'IA au TURN-START de sa team (passe AI-control `run_ai_control_pass`), un chemin SÉPARÉ de
    `PickNextUnit`/`aiStepDryRun`. Le scarab N'EST PAS apparition-only → `ai_controlled=True`.
  - **active `ScarabSummon` IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour** = auto-DÉDOUBLEMENT : `AdjacentTiles(self@0x160)` → `PickRandomly`
    → `CopyOwner` → `Spawn` un AUTRE `necroSmnSwarm` adjacent à SOI, dont l'on-appearance = `PerformAIAttack`
    (« which then immediately takes a turn ») → c'est le DOUBLE qui attaque. Playbook `ScarabSummonPlaybook`
    (`GetUseProbability` = 1.0 ou 1/2 selon un compteur runtime ; `chance` gameconfig = 50).
  - **passive `ReanimationProtocols`** = revive-on-death (chance 35 %, 25 % PV) hors overkill.

VALIDÉ live bit-exact : necroSpyder (activeAbilityLevel=50, mult=200) ScarabHive → 2× necroSmnSwarm
**team=1 player=3 hp=2218 dmg=998** ; `ability_var(ScarabHive, summonHp, 50, 200)=2218`.
"""
from __future__ import annotations

from typing import Optional

import hexgeo

from ..state import State
from ..components import (StatsComponent, OwnerComponent, PositionComponent,
                          HealthComponent, UnitComponent)
from ...entities.effect_type import EffectType
from ...dsl.event_trigger_type import EventTriggerType
from ...entities.effects_state import EffectsState
from ...entities.unit_context import UnitContext
from ...entities.effects.factory import EffectFactory
from ...entities.effects.factory import (get_derived_abilities_for_trait,
                                             get_owner_effects_added_on_ability_init)
from ...entities.effects.factory import (get_owner_effects_added_on_ability_init,
                                             get_effect_to_be_added_to_owner_for_ability)
from ...entities.effects.factory import get_effect_to_be_added_to_owner_for_trait
from ...entities.effects.magnitude import ability_var
from ...entities.stats import UnitStats, StatType, StatPart
from ...utilities.tile import sort_tiles_by_utility
from ..components import UnitFlagsComponent
from engine.battle_query import is_adjacent
from ..components import set_unit_feet
from .aura_stat_mods import refresh_aura_stat_modifiers
# `AddUnitOperation$$KillSteppableUnits` et `MoveUnitOperation$$KillSteppableUnits` sont DEUX
# appelants natifs du MEME crush : le port n'en a qu'UNE implementation, celle du move (#501).
# Import de niveau module : `movement` ne charge PAS `spawn` (verifie en process frais), donc
# aucun cycle a differer.
from .movement import _kill_steppable_units
from engine.entities.pathfinding.board import (adjacent_neigh_by_pos,
                                                           elevations_by_pos)


def build_summon_context(entity_id: int, visual_id: str, summon_ability: str,
                         caster_level: Optional[int], caster_mult: int, key_suffix: str = "",
                         passive_level: Optional[int] = None):
    """`UnitContext` d'un summon, résolu 100% offline depuis gameconfig :
      - stats de combat = `ability_var(summon_ability, summon*, caster_level, caster_mult)` ;
      - arme/traits/profil = gameconfig de l'unité summon (`visual_id`).
    `caster_level` = `activeAbilityLevel` du caster ; `caster_mult` = `abilityVariablesMultiplier`. Une clé
    `summon*` absente → 0 (ex. ScarabHive n'a pas `summonArmor` → armure 0, cohérent i2 « 0 Armour »)."""
    import gameconfig as GC

    def sv(key: str) -> int:
        v = ability_var(summon_ability, key, caster_level, multiplier_pct=caster_mult)
        return int(v) if v is not None else 0

    gu = GC.unit(visual_id) or {}
    weapons = gu.get("weapons") or []
    w = weapons[0] if weapons else None
    prof_name = w.get("DamageProfile") if w else None
    prof_pierce = 0
    ranged = False
    w_hits = 1
    if w:
        dp = GC.damage_profile(prof_name) or {}
        prof_pierce = int(dp.get("PiercingRatio") or 0)
        w_hits = int(w.get("hits") or 1)
        ranged = bool(w.get("Range"))
    # Les 8 stats de base sont des propriétés `get_stat` → on SEEDE `UnitStats` (au lieu de champs plats).
    # Base identité (ni delta ni mod) depuis les variables `summon*` ; les clés absentes (block/hits) = 0.
    # `key_suffix` : certaines abilities nomment leurs vars de stats summon avec un suffixe (ex. CultDemagogue
    # = `summonHp_2`/`summonDmg_2`/`summonArmor_2`, cf. gameconfig) — une clé absente (ex. crit du neophyte) -> 0.
    stats = UnitStats()
    for st, key in ((StatType.ATTACK, "summonDmg"), (StatType.HEALTH, "summonHp"),
                    (StatType.FIXED_ARMOR, "summonArmor"), (StatType.CRIT_CHANCE, "summonCritChance"),
                    (StatType.CRIT_DAMAGE, "summonCritDmg")):
        stats.ensure_seeded(st, sv(key + key_suffix))
    for st in (StatType.BLOCK_CHANCE, StatType.BLOCK_DAMAGE, StatType.EXTRA_HITS):
        stats.ensure_seeded(st, 0)
    # MOVEMENT(1) : stat de la CONFIGURATION de l'unite invoquee, PAS une variable `summon*`.
    # `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$GetStatsToOverride` ne rend qu'une LISTE de
    # `StatModifier` (les deux listes `options+0x20` litterales et `options+0x28` (statType, IAmount)
    # evaluees) : c'est un OVERRIDE PARTIEL pose SUR l'unite deja construite depuis sa
    # `UnitConfiguration` -- aucune ability de summon ne porte de var `summonMovement`, donc le
    # Movement natif du summon est celui de sa config (orksOrkBoys = 3, necroSmnSwarm = 4, ...).
    # Sans ce seed, la stat vaut 0 et `engine.ai.state_bridge._move_range` retombait sur le fallback
    # gameconfig -- correct A VIDE, mais FAUX des qu'un effet modifie MOVEMENT : le modificateur
    # (ex. `Waaagh_ExtraMovement` 1099, +1) rendait `get_stat(MOVEMENT) = 1 > 0`, ce qui COURT-CIRCUITE
    # le fallback et ecrase la portee (1 au lieu de 3+1). MESURE (probe_r21) : les Ork Boyz portes
    # n'avaient que 5 tuiles d'action (l'anneau a 1 hex) et finissaient a dist <= 1 du caster, la ou
    # le natif les envoie a dist 3.
    stats.ensure_seeded(StatType.MOVEMENT, int(gu.get("Movement") or 0))
    # `passive_ability_level` : le niveau sous lequel l'unite POSEE monte ses PROPRES abilities.
    #
    # ⚠ **LE DEFAUT EST `caster_level`, ET C'EST LU (#570-r3) -- pas `0`.**
    # `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$WithStatsFromConfig(config, abilityState,
    # ordinal, abilitiesLevel, variableMultiplierPercentage)` ecrit :
    #
    #     opts.<+0x58> = Nullable<int>(abilityState.level)
    #     if (abilitiesLevel == null)                abilitiesLevel = <box>(abilityState.level)
    #     opts.<+0x30> = abilitiesLevel
    #     if (variableMultiplierPercentage == null)  variableMultiplierPercentage
    #                                                    = <box>(abilityState.mult)
    #     opts.<+0x38> = variableMultiplierPercentage
    #
    # Autrement dit : **aucune branche native ne laisse ce niveau a zero** -- quand l'appelant ne
    # le precise pas, le natif retombe sur le niveau de l'`AbilityState` du SUMMONER, qui est
    # exactement ce que le port appelle `caster_level`. Et le natif n'a QU'UN niveau pour toutes
    # les abilities de l'unite posee : `SpawnUnitOptions` ne distingue pas actif et passif.
    # La surcharge a 4 parametres (celle qu'appelle `GrotTankAbility$$ExecuteBehaviour`) delegue a
    # celle-ci avec `ordinal = 1`, donc la meme regle vaut.
    # Confirmation par une SECONDE voie : `IdunBattle.Operations.AddUnitOperation$$
    # InherentAbilitiesLevelFromParent(parent, unit)` prend le MAX des `AbilityState` des abilities
    # du PARENT et le pose sur celles de l'unite -- la aussi, jamais zero.
    #
    # `passive_level` explicite reste prioritaire : il exprime un `AbilityState` ETRANGER (la mine
    # Haywire posee par un passif), cas ou `abilitiesLevel` N'EST PAS celui du caster.
    # Sans ce defaut, une passive de summon per-niveau lit l'index 0 (= niveau 1) : mode de panne
    # #174, mesure a un facteur ~55 sur la mine Haywire, et cause du residu #570-r3 (le
    # `Ramshackle_DmgReduction` du Grot Tank lisait `dmgReduction[1] = 5`).
    _niveau_abilities = caster_level if passive_level is None else passive_level
    kw = ({} if _niveau_abilities is None
          else {"passive_ability_level": int(_niveau_abilities)})
    return UnitContext(
        entity_id=entity_id, visual_id=visual_id,
        active_ability_level=int(caster_level or 0),   # niveau du caster -> propage aux self-summons (PileIn 2e gen)
        ability_variables_multiplier=caster_mult,
        **kw,
        traits=list(gu.get("traits") or []),
        range=int(w.get("Range") or 0) if w else 0,
        faction=gu.get("FactionId"),
        number_of_members=max(1, int(gu.get("nrOfMembers") or 1)),
        normal_profile=prof_name, normal_profile_pierce=prof_pierce,
        normal_weapon_hits=max(1, w_hits), normal_ranged=ranged,
        stats=stats,
    )


def build_decoy_context(entity_id: int, visual_id: str = "genesSmnDecoy"):
    """`UnitContext` d'un token decoy — `SpawnUnitOptions$$IdunBattle.Entities.Behaviours.SpawnUnitOptions$$ForSteppable` = `Level(1)` +
    `CreateSpawnOptions(state,0,0,0,0)` (aucun override) : PAS de summon-scaling (contrairement à
    `build_summon_context`). Le decoy prend le kit BRUT de sa config `genesDecoy`/`genesSmnDecoy` :
    traits `Steppable`(27)+`Decoy`(1053), AUCUNE arme, AUCUNE stat de combat (config `stats` = juste
    `AbilityLevel:1`). Token inerte (`move=None`, non-ciblable)."""
    import gameconfig as GC
    gu = GC.unit(visual_id) or {}
    stats = UnitStats()
    for st in (StatType.ATTACK, StatType.HEALTH, StatType.FIXED_ARMOR, StatType.CRIT_CHANCE,
               StatType.CRIT_DAMAGE, StatType.BLOCK_CHANCE, StatType.BLOCK_DAMAGE, StatType.EXTRA_HITS):
        stats.ensure_seeded(st, 0)
    return UnitContext(
        entity_id=entity_id, visual_id=visual_id,
        active_ability_level=1, ability_variables_multiplier=100,
        traits=list(gu.get("traits") or []),           # Steppable, Decoy (config brute)
        range=0, faction=gu.get("FactionId"),
        number_of_members=1,
        normal_profile=None, normal_profile_pierce=0,
        normal_weapon_hits=1, normal_ranged=False,
        stats=stats,
    )


#: `IdunBattle.Entities.Enum.UnitTrait` — les deux traits qui EXEMPTENT du finish-turn de spawn.
_TRAIT_STEPPABLE = "Steppable"      # UnitTrait.Steppable = 27 (0x1b)
_TRAIT_HERO = "Hero"                # UnitTrait.Hero      = 16 (0x10)


def trigger_spawned_unit_finish_turn(state: State, unit_id: int) -> Optional[dict]:
    """Mirror de la SECONDE moitie de `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$
    TriggerSpawnedUnitBehaviours` (#291) -- **une unite qui APPARAIT pendant le tour de son
    proprietaire voit son tour immediatement TERMINE**, elle n'obtient donc JAMAIS d'activation
    au tour de son apparition. Lu verbatim au decompile :

        if (options.<on-appearance @+0x18> != null) <behaviour>.Execute(entities{caster = spawned})
        turn = StateExtensions.GetMatchTurn(state)
        if (TurnComponent.get_CurrentPlayerId(turn) == parentPlayerId) {
            v = UnitExtensions.HasTrait(spawned, 0x1b = Steppable) ? false
                                                                  : !HasTrait(spawned, 0x10 = Hero)
            if (options.<Nullable<bool> @+0x48>.HasValue) v = <...>.Value      # override explicite
            if (v) IOperationProcessor.<slot 0x23>(spawned, true)              # FinishUnitTurn(u, isTerminated)
        }

    Le slot 0x23 est identifie SANS AMBIGUITE par `IdunBattle.Entities.Behaviours.
    FinishUnitTurnBehaviour$$Execute`, qui appelle CE MEME slot avec `(unit, false)` ; et
    `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` l'appelle aussi apres avoir joue
    une unite automatique. Cote natif, `FinishUnitTurnOperation$$Execute` termine par le slot 0x76
    = `MarkUnitAsNoActionAvailable(unit)` -> `UnitExtensions$$HasActionLeft` devient faux et le
    summon SORT de la liste « a activer » (`decisionView.toActivate`).

    MESURE LIVE (probe_291, runner arene, `orksWarboss`/`Waaagh` -> 2 `orksOrkBoys`) : chaque summon
    emet, JUSTE APRES son spawn, `UnitStats_TurnFinished=1` puis `UnitStats_ActionsAvailable=0` --
    exactement cette sequence.

    PORTE ICI : les flags de tour (`TURN_FINISHED` + `ARRIVED_AT_FINAL_TILE` + `TURN_FINISHED_FORCED`
    via `FinishUnitTurnOperation.execute(forced=True)`) — et depuis #287-r1 le
    `MarkUnitAsNoActionAvailable` final (flag 4), que `FinishUnitTurnOperation` pose lui-meme en
    queue, comme le natif.

    LA CRAINTE QUI RETENAIT CETTE POSE EST MESUREE, ET ELLE NE MORD PAS. Le raisonnement etait :
    « son unique retrait natif est `VerifyUnitTurnEnded` (slot 0x77), non mirrore, et
    `StartTurnOperation` appelle `RemoveTurnFlags(includeNoAction=0)` -> le flag survit au
    turn-start et FIGE l'unite, puisque `has_action_left` gate `ai_control_execute_for_group` ».
    Ce qu'il manquait : `ai_control_execute_for_group` n'est atteint que par
    `ComputerActionOperation.execute_group`, dont TOUS les call-sites natifs recenses passent
    `resetTurnFlags = 1` -> `RemoveTurnFlags(True, True)` EFFACE le flag juste avant la boucle. Et
    la passe automatique du turn-start (`run_ai_control_pass` -> `collect_ai_controlled`) filtre
    sur `TurnEnded()` (flag 3), pas sur le flag 4. Le flag collant n'a donc AUCUN lecteur effectif
    offline. Cliquet : `test_287r1_no_action_available_offline.py` (etage « le summon reste
    jouable au tour suivant »). Le retrait reste a porter : residu `#287-r1-r1`.

    PLACE DANS LE PORT : le natif tient ce foyer dans `SpawnUnitBehaviour` (au-dessus d'`AddUnit`) ;
    offline on l'appelle depuis les CHOKE POINTS de spawn (`_spawn_config_grot`, `spawn_decoy`, les
    trois constructions manuelles de ce module) parce qu'AUCUN d'eux ne sert au deploiement initial
    ni au drafting -- tous mirrorent un `SpawnUnitBehaviour`. Le gate `currentPlayer == owner` les
    rend de toute facon equivalents.

    Rend le dict de `FinishUnitTurnOperation.execute` quand le finish a lieu, sinon `None` (avec la
    raison) -- diagnostic pour les probes/tests."""
    from .turnflow import FinishUnitTurnOperation
    e = state.get_entity(int(unit_id))
    if e is None:
        return None
    oc = e.get_component(OwnerComponent)
    if oc is None or oc.player is None:
        return None
    # `TurnComponent.get_CurrentPlayerId(turn) == parentPlayerId` — le summon herite du player du
    # parent (`CopyOwner`), donc son propre `OwnerComponent.player` EST `parentPlayerId`.
    if state.current_player_id is None or int(oc.player) != int(state.current_player_id):
        return None
    sc = e.get_component(StatsComponent)
    traits = list(getattr(sc.ctx, "traits", None) or []) if (sc is not None and sc.ctx) else []
    if _TRAIT_STEPPABLE in traits:          # HasTrait(0x1b) -> v = false (decoys, mines, tokens)
        return None
    if _TRAIT_HERO in traits:               # sinon v = !HasTrait(0x10) (clone/revive d'un HEROS)
        return None
    return FinishUnitTurnOperation.execute(state, int(unit_id), forced=True)


def spawn_decoy(state: State, tile, caster_id: int, visual_id: str = "genesSmnDecoy") -> Optional[int]:
    """`DSLFactory$$IdunBattleLogic.IdunBattleLogic.Entities.DSLBehaviors$$Spawn(genesSmnDecoy, ForSteppable)` → `SpawnUnitBehaviour.Execute` →
    `AddUnitOperation.Execute` (MÊME socle que ScarabHive/`SpawnUnitOperation`, options DIFFÉRENTES) : pose UN
    token decoy sur `tile` (id de tuile). Options `SpawnUnitOptions$$IdunBattle.Entities.Behaviours.SpawnUnitOptions$$ForSteppable` :
      - owner = team+player du **caster** (hérité, comme `CopyOwner`) ;
      - stats = kit BRUT `genesDecoy` (level 1, PAS de `ability_var` summon-scaling) ;
      - **`ai_controlled=False`, AUCUNE on-appearance** — le token est INERTE (≠ `SpawnUnitOperation` qui force
        `ai_controlled=True` + attaque à l'apparition). Piège validator #3 : ne PAS réutiliser
        `SpawnUnitOperation.execute` tel quel.
    Renvoie l'entity id (None si `tile` None / non resolvable sur le board / caster introuvable). Appelé par
    les feuilles decoy (G4/G6/G2).
    Fondation G1 : la primitive ; les sélecteurs de tuiles (où poser) sont propres à chaque ability."""
    if tile is None:
        return None
    caster = state.get_entity(caster_id)
    coc = caster.get_component(OwnerComponent) if caster is not None else None
    if coc is None:
        return None
    # case-spawn-requires-tile -- LA TUILE D'ABORD, l'entite ensuite. `SpawnUnitBehaviour$$Execute` n'appelle
    # `AddUnitOperation$$Execute` que DEPUIS une tuile ITEREE : pas de tuile, pas d'appel, donc pas
    # d'entite. Resoudre la tuile APRES `state.add_entity()` laissait un token sans
    # `PositionComponent` -- hors plateau, invisible des selecteurs de tuile, que rien ne ramasse.
    board = state.board
    tinfo = board.by_id.get(tile) if board is not None else None
    if tinfo is None:
        return None
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=False))
    e.add_component(OwnerComponent(team=coc.team, player=coc.player))   # CopyOwner (caster)
    ctx = build_decoy_context(e.id, visual_id)
    e.add_component(StatsComponent(ctx=ctx))
    # HARDCODE (token) : le decoy n'a AUCUN HP de config -> HealthComponent nominal hp=1 pour qu'il OCCUPE la
    # tuile et soit "vivant"/tuable. hp=1 n'est PAS un seuil de dégât réel : un decoy est détruit par step
    # (crush, G1) OU par tout damage (instakill "destroyed if damaged", Decoy trait -> G2). A revoir si la RE
    # G2 révèle un HealthComponent natif spécifique.
    e.add_component(HealthComponent(hp=1, hp_max=1))
    e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
    on_unit_added(state, e.id)          # `On(UnitAdded)` (no-op sur un token sans armure)
    # #291 `TriggerSpawnedUnitBehaviours` : NO-OP ICI par construction — le decoy porte
    # `UnitTrait.Steppable`(27), la branche `HasTrait(0x1b) -> v = false` du natif. On l'appelle
    # quand meme pour que le GATE soit exerce (et testable) sur ce chemin comme sur les autres.
    trigger_spawned_unit_finish_turn(state, e.id)
    return e.id


def _free_tiles_adjacent(state: State, target_id: int, exclude: set,
                         native_order: bool = False) -> list:
    """`CanAddUnit(AdjacentTiles(target))` — tuiles voisines de la cible, marchables et NON
    occupées (par une unité vivante OU une tuile déjà choisie ce spawn). [] si pas de board.

    `native_order=False` (défaut historique) : ids de tuile TRIÉS — approximation déterministe.

    `native_order=True` : **ORDRE D'ÉNUMÉRATION NATIF**.
    `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` accumule dans un `OrderedSet`
    (donc ordre d'INSERTION) ce que rend
    `IdunBattle.Core.Services.BattleQuery$$GetAdjacentTiles(origin, onlyEmptyOrSteppable=false,
    onlyWalkableTiles=true, allowTemporary=true)` → `IdunBattle.Core.Services.BattleQuery$$IterateAdjacentTiles`
    → `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles` (liste d'adjacence stockée sur la
    tuile, + porte d'élévation `|Δelev| < 2`). C'est **exactement** l'itérateur que le capteur
    `boardGraph` sérialise dans le champ BRUT `neighbours` de chaque tuile (cf.
    `entities/pathfinding/board.py`) — d'où la lecture directe de ce champ ici, et **pas**
    `board.neighbours()` (qui trie les ids et symétrise les arêtes).

    Pourquoi ça compte : les tris natifs en aval sont des `OrderBy`/`OrderByDescending` LINQ, donc
    **STABLES**. Dès qu'ils sont à égalité (carte plate, utilités toutes nulles, clé constante),
    c'est l'ordre SOURCE qui décide la tuile — il fait donc partie intégrante du port des quatre
    sites `First(<tri>(…), 1)`. Board construit à la main (tests unitaires, pas de champ brut) →
    repli sur `board.neighbours` (ids triés)."""
    board = state.board
    tgt = state.get_entity(target_id)
    if board is None or tgt is None:
        return []
    tp = tgt.get_component(PositionComponent)
    if tp is None:
        return []
    ttile = board.id_at(tp.col, tp.row)
    if ttile is None:
        return []
    occupied = set(exclude)
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None:
            continue
        if uc is not None and not uc.alive:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            occupied.add(t)
    ring = _adjacent_tiles(board, ttile) if native_order else sorted(board.neighbours(ttile))
    out = [t for t in ring if board.walkable(t) and t not in occupied]
    return out


def _adjacent_tiles(board, tile_id: int) -> list:
    """`IdunBattleLogic.Entities.DSLSelectors$$AdjacentTiles(origin)` — voisins de `tile_id` dans
    l'ORDRE d'itération natif. FOYER UNIQUE = `Board.neighbours_native` (champ brut `neighbours`
    du `boardGraph`, cf. `_free_tiles_adjacent`) ; repli ids triés quand le champ brut manque."""
    return board.neighbours_native(tile_id)


def _pick_randomly_one(state: State, tiles: list):
    """`IdunBattleLogic.Entities.DSLSelectors$$PickRandomly(source, 1)` ->
    `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$Select` (`amount = 1`) : UNE tuile, et
    **UN tirage dès que le pool est non vide** — y compris pool de taille 1 (case-130 SS4 ; loi #130).

    Le décompilé du sélecteur n'a aucun court-circuit « le pool tient dans amount » : sa seule sortie
    anticipée est `candidates.Count < 1`. À `k == 1`,
    `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal(0, 1)` prend la branche
    puissance-de-deux, CONSOMME un `genrand_int32` et retourne 0.

    Appelants (nœud natif LU, un par un — ne PAS l'étendre aux sites `First(...)` ci-dessous, qui ne
    tirent rien) :
      * `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour` :
        `PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1, 0, 0x7fffffff, false)` ;
      * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateSummonBehaviour` :
        `PickRandomly(TilesUnitCanAttackFrom(CanAddUnit(AdjacentTiles(owner@0x148)), owner, unitId_2)
        .Otherwise(possible), 1, 0, 0x7fffffff, false)`.

    Délègue au foyer unique de la loi, `abilities/loki/splash.py::_pick_randomly_n`."""
    from ..abilities.loki.splash import _pick_randomly_n       # lazy : cycle operations <-> abilities
    picked = _pick_randomly_n(state, tiles, 1)                 # PickRandomly(., 1)
    return picked[0] if picked else None


def _first(tiles: list):
    """`IdunBattleLogic.Entities.DSLSelectors$$First(entities, 1, ignoreForcedTargets=false)` — le
    PREMIER élément de la liste résolue par le sélecteur source (None si vide). **ZÉRO tirage** :
    `First` construit un sélecteur de PRISE-EN-TÊTE, pas un `PickRandomAmountSelector`."""
    return tiles[0] if tiles else None


def _first_n(tiles: list, count: int) -> list:
    """`IdunBattleLogic.Entities.DSLSelectors$$First(entities, count, ignoreForcedTargets=false)` —
    le frère à COUNT de `_first`, rendu **min(count, len(source))** éléments en TÊTE. **ZÉRO
    tirage**, exactement pour la même raison (prise-en-tête, pas un `PickRandomAmountSelector`).

    Le nœud du spawn ScarabHive porte ce `count` (`Cache(First(Get(SelectTiles(SortByDistance(
    SortByDistance(CanAddUnit(AdjacentTiles(target@0x178)), caster@0x160), caster@0x160))),
    count), 1)`) et c'est le SEUL endroit où le nombre de summons est décidé, cf.
    `SpawnUnitOperation.execute`.

    ⚠ POURQUOI IL EST NOMMÉ plutôt qu'écrit `[:count]` en ligne (#462-r6). Le site l'écrivait en
    slice anonyme depuis que le tile-sélecteur s'évalue UNE fois (`54c04b59`) : le nœud natif
    n'avait donc plus de nom, et le contre-contrôle de `test_placement_sort_rng_live.py` — qui
    substitue le modèle de placement d'AVANT — s'ancrait sur `_first`, que ce site n'appelait
    plus. Il a cessé de mordre EN SILENCE, et son échec accusait le port. Un mirror nommé est un
    point d'ancrage stable ; une forme d'écriture n'en est pas un. STRICTEMENT NO-OP."""
    return list(tiles[:max(0, int(count))])


def _sort_by_distance(state: State, tiles: list, origin_id: int) -> list:
    """`IdunBattleLogic.Entities.DSLSelectors$$SortByDistance(entities, origin)` →
    `IdunBattle.Entities.Selectors.SortByDistanceSelector$$Select`, remis en C# :

        var list   = this.entities.Select(entities);
        var origin = this.originSelector.SelectSingle(entities);
        if (origin == null) return new List<IEntity>();          // sortie VIDE, pas la liste brute
        dc.originPos = origin.GetComponent<PositionComponent>();
        return list.OrderBy(dc.<Select>b__0).ToList();

    et `<Select>b__0(s)` = `dc.originPos.Distance(state.GetEntity(s.GetMainTileId(state)).Position)`
    (`IdunBattle.Entities.Components.PositionComponent$$Distance` = distance CUBE hex via
    `IdunBattle.Utils.Hex.AxialCoordinate$$ToCubeCoordinate` + `IdunBattle.Utils.Hex.CubeCoordinate$$Distance`).

    → tri ASCENDANT par distance hex à l'origine, `OrderBy` LINQ donc **STABLE** (les ex aequo
    gardent l'ordre source = l'ordre d'énumération natif de `AdjacentTiles`). **ZÉRO tirage.**"""
    org = state.get_entity(origin_id)
    op = org.get_component(PositionComponent) if org is not None else None
    board = state.board
    if op is None or board is None:
        return []                                    # `origin == null` -> List vide (mirror)
    o = (op.col, op.row)
    return sorted(tiles, key=lambda t: hexgeo.distance(o, board.coord(t)))


def _sort_tiles_by_utility_for_summon(state: State, tiles: list, caster_id: int) -> list:
    """`IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtilityForSummon(tiles, utilityType, parent)`
    = `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility(tiles, AllAliveMachinesSelector,
    UtilityDefinition(utilityType), parent)` -> `SortTilesByUtilitySelector$$Select`.

    Délègue au FOYER UNIQUE `engine/utilities/tile.py::sort_tiles_by_utility` (mirror du `Select`,
    tri DÉCROISSANT stable par le composite `Tile(7)`, ZÉRO tirage) — c'est le MÊME sélecteur natif
    que celui des charges/spawns d'ability, donc UN SEUL port (#165). Le sélecteur d'unités diffère,
    et depuis case-165b la distinction n'est PLUS inerte : sur les autres call-sites `dc.unit` est
    le CASTER, il est passé au foyer (`unit_id=`) et il réveille les feuilles gatées sur l'unité.

    ICI, `dc.unit` vaut **`null`** — case-205, tranché au décompilé, et NON « un ENSEMBLE d'unités »
    comme le supposait le résidu #165b §4. `SortTilesByUtilityForSummon` construit bien un
    `IdunBattle.Entities.Selectors.AllAliveMachinesSelector`, mais avec un provider NUL, et
    `IdunBattle.AI.Utilities.UtilityMovementCase` traite explicitement ce cas
    (`get_IsSpawning` = `unit == null && parent != null`, `get_UnitOrParent` = `unit ?? parent`).
    On passe donc `parent_id=caster_id` — le `parent` natif, 3ᵉ argument de
    `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtilityForSummon` — et AUCUN `unit_id` : le foyer
    produit un ctx `{"is_spawning": True}`, que chaque feuille consomme selon SA propre dégradation
    (0 pour `TriggeredAbilities(2)` / `DespoiledGround(29)` / `HeroLikeDoorOpening(31)` ; flag summon
    pour `CapturePoint(25)` / `PowerUp(27)` / `SummonDislikeDoorOpening(30)`).

    ⚠ La réduction est **MESURÉE, pas supposée** : trois scénarios live où le tri et l'ordre source
    DÉSACCORDENT (`probe_130_placement_sort_rng.py`, dont `--discriminate` qui construit exprès la
    géométrie) la valident, et ont au passage forcé la prise en compte du `Swamp ->
    Thorns_DefenseReduction` (-25) — sans lui le modèle posait le summon sur une Swamp élevée que le
    natif évite. Ce qui reste NON couvert : les feuilles gatées sur l'unité (aucun scénario ne les a
    encore réveillées) et les terrains dont on ne connaît pas les abilities hébergées.

    Les effets de la tuile candidate sont lus DANS LE FOYER comme partout ailleurs (#155) : canal
    DYNAMIQUE `state.effects.by_unit[tileId]` = Loop1 de `TileEffectsUtility` (l'entité-tuile porte
    ses effets exactement comme une unité, case-102), puis `terrain_tile_effects(terrain, dynamique)`
    pour Loop2 + le repli statique du Loop1 non hydraté — d'où le passage de `state` (et non du seul
    `board`) au foyer. `caster_id` EST le `parent` natif (case-205) : il ne devient un sujet à AUCUN
    moment, mais sa PRÉSENCE est ce qui arme `IsSpawning`."""
    return sort_tiles_by_utility(state, tiles, parent_id=caster_id)


def _randomize(state: State, tiles: list) -> list:
    """`IdunBattleLogic.Entities.DSLSelectors$$Randomize(entities)` =
    `IdunBattle.Entities.Selectors.PickRandomAmountSelector(state, source, amount = 0x7fffffff, rng,
    allowRepeat = false, maxRepeat = 0x7fffffff, ignoreForcedTargets = false)` — donc **PAS un tri** :
    un MÉLANGE COMPLET, qui consomme **`len(pool)` tirages** aux bornes DÉCROISSANTES
    `len, len-1, … 1` (loi #130). Délègue au foyer unique `abilities/loki/splash.py::_pick_randomly_n`
    — ne PAS ré-écrire la boucle ici."""
    from ..abilities.loki.splash import _pick_randomly_n
    return _pick_randomly_n(state, tiles, 0x7fffffff)


def _sort_by_formula_pilein(state: State, tiles: list) -> list:
    """`IdunBattleLogic.Entities.DSLSelectors$$SortByFormula(entities, formula, ascending = false)` de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour`, avec
    `formula = If(HasTrait(@0x180, 0x1b), Direct(0), Direct(1))` (les deux `Direct` sont les
    constantes partagées `DSLFactory+0xb8`=0 et `+0xc0`=1, cf. `IdunBattleLogic.Entities.DSLFactory$$.ctor`).

    `IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select` : `ascending == false` →
    `OrderByDescending(key)` (LINQ, **STABLE**) ; `key(item)` = la formule évaluée avec `item` posé
    dans le slot SUJET des `AbilityEntities`. **ZÉRO tirage** (le mélange, lui, est en amont).

    → clé = 0 pour un sujet portant `UnitTrait.Steppable` (27 = 0x1b), 1 sinon ; descendant donc
    « Steppable en DERNIER ».

    ⚠ Le sélecteur `DSLFactory+0x180` n'est PAS départageable au décompilé entre « sujet courant »
    (ici une TUILE) et « unité invoquée » (le grot). **Les deux lectures donnent la même clé pour
    toutes les tuiles du pool** — une tuile ne porte pas de `UnitTrait`, et le grot est le même quel
    que soit le candidat — donc le tri est une IDENTITÉ stable et `First` rend la tuile TIRÉE EN
    PREMIER par `Randomize`. C'est ce que le port matérialise ; le jour où une entité-tuile porterait
    un trait, il faudra trancher le sélecteur."""
    def _key(tile) -> int:
        # `HasTrait(subject, Steppable)` : le port n'a pas d'entité-tuile porteuse de traits, et sous
        # la lecture « unité invoquée » la clé est constante sur le pool -> 1 partout (cf. docstring).
        return 1
    return sorted(tiles, key=lambda t: -_key(t))      # OrderByDescending, stable


def _occupied_tiles(state: State) -> set:
    """Ids de tuiles occupées par une unité VIVANTE (ou sans UnitComponent = objet/décor) — pour `CanAddUnit`."""
    board = state.board
    out: set = set()
    if board is None:
        return out
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None:
            continue
        if uc is not None and not uc.alive:
            continue
        t = board.id_at(pc.col, pc.row)
        if t is not None:
            out.add(t)
    return out


def apply_spawn_stat_overrides(ctx, stat_overrides) -> list:
    """Applique au `UnitContext` FRAIS d'un summon les `StatModifier` rendus par
    `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$GetStatsToOverride` — volet FORMULE
    (`SpawnUnitOptions+0x28`), sous la forme `[(statType, statPart, valeur), ...]`.

    Le volet LITTERAL (`options+0x20`) est deja pose par `build_summon_context` ; ceux-ci
    viennent APRES dans la liste native, donc ils GAGNENT sur le meme `StatType`.

    `StatPart.Initial` est le SEUL part porte, et c'est le seul que le natif produise sur ce
    chemin : `SpawnUnitOptions$$SetStatFromConfig` ecrit `StatModifier(statType, 3, valeur)` en
    dur, et l'unique `StatModifierFormula` du binaire (GrotTank) passe `3` lui aussi. Sa
    semantique est LUE dans `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier`
    case 3 : `+0x10` (max de base), `+0x14` (max courant) et `+0x18` (courant) recoivent TOUS la
    valeur -- c'est un ECRASEMENT, pas un delta. Cote port, l'`initial` du `StatComponent` porte
    la meme grandeur, et l'appelant re-lit `ctx.health` juste apres pour seeder le
    `HealthComponent` (donc `hp == hp_max == valeur`).

    Un part AUTRE que `Initial` est IGNORE et RENDU dans la liste des non-appliques : aucun
    call-site natif n'en produit, et l'inventer poserait une semantique non lue. Renvoie la liste
    des `(statType, statPart)` NON appliques (vide = tout applique)."""
    skipped: list = []
    stats = getattr(ctx, "stats", None)
    for st, part, value in (stat_overrides or []):
        if stats is None or int(part) != int(StatPart.INITIAL):
            skipped.append((int(st), int(part)))
            continue
        stats.ensure_seeded(int(st), int(value))     # cree le composant s'il manque
        comp = stats.components.get(int(st))
        if comp is not None:
            comp.initial = int(value)                # ECRASE (case 3 de `ApplyModifier`)
    return skipped


def _spawn_config_grot(state: State, visual_id: str, tile, summon_ability: str,
                       level, mult: int, team, player, ai_controlled: bool = True,
                       key_suffix: str = "", parent_id: Optional[int] = None,
                       feet_tiles: Optional[list] = None,
                       finish_turn_on_spawn: bool = True,
                       passive_level: Optional[int] = None,
                       stat_overrides: Optional[list] = None) -> Optional[int]:
    """Spawn UNE unité `visual_id` sur `tile` (id de tuile), stats `WithStatsFromConfig(summon_ability)` =
    `ability_var(summon_ability, summon*[key_suffix], level, mult)`, owner = team+player, `active_ability_level
    = level` (propagé → lève le GAP PileIn 2e-gen). Renvoie l'entity id (None si `tile` None). Partagé par
    GetEmRuntz/SquigHound (WithStatsFromConfig, PAS clone) et par CultDemagogue (neophyte).
    `ai_controlled` = summon auto-joué au turn-start (grots/swarms) vs unité normale jouée au tour de sa team
    (neophyte = trait Ambush+BattleFatigue, PAS Summon → `False`). `key_suffix` = suffixe des clés de stats
    (ex. `_2` pour CultDemagogue).

    `parent_id` = le CASTER (mirror `Unit_Parent_Id` emis nativement au spawn d'un summon ; ground truth
    live SupremeCommander : `Step#10 e=<summon> Unit_Parent_Id=<casterId>`). Alimente `Parent(Self)`
    (`ListenUpMaggotsEffect.CreateTargetSelector`) et `Children(caster)`. None = lien non pose.

    `feet_tiles` (#91, MULTI-HEX) = la LISTE d'ids de tuiles que `IdunBattle.Operations.
    AddUnitOperation$$Execute` recoit quand `SpawnUnitOptions+0x60 != 0` : elle pose l'unite sur N
    tuiles (`ClearFeet` puis un `AddFoot` PAR tuile, DANS L'ORDRE), et `feet[0]` devient la MAIN TILE.
    `tile` reste l'ancre (== `feet_tiles[0]`, cf. l'ordre `[ancre, t1, t2]` de
    `BattleQuery$$GetTilesInTriangleShape`). None (defaut) = le cas NOMINAL mono-pied, inchange :
    l'unite garde `UnitComponent.feet = None` et sa seule `PositionComponent`.

    case-spawn-requires-tile -- **AUCUNE entite n'est creee sans tuile**. `IdunBattle.Entities.Behaviours.
    SpawnUnitBehaviour$$Execute` n'atteint `AddUnitOperation$$Execute` que DEPUIS une tuile (branche
    `+0x60 == 0` : `foreach (tile in tiles)` ; branche multi-hex : `GetTileIds(tiles)` fourni par le
    MEME selecteur). L'appelant qui n'a pas de tuile n'appelle donc rien : `tile is None` -- ou un id
    que le board ne resout pas -- rend `None`, AVANT le `state.add_entity()`."""
    if tile is None:
        return None
    board = state.board
    tinfo = board.by_id.get(tile) if board is not None else None
    if tinfo is None:
        return None
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=ai_controlled,
                                  parent_id=parent_id))
    e.add_component(OwnerComponent(team=team, player=player))
    ctx = build_summon_context(e.id, visual_id, summon_ability, level, mult, key_suffix=key_suffix,
                               passive_level=passive_level)
    # `SpawnUnitBehaviour$$GetStatsToOverride`, volet FORMULE (`SpawnUnitOptions+0x28`) : il vient
    # APRES le volet litteral dans la liste native, donc il ECRASE sur un meme StatType. C'est ce
    # qui donne au Grot Tank ses PV `summonHp + RoundsStarted(Caster) x extraHp` par-dessus le
    # `summonHp` seul que `build_summon_context` vient de poser. `None` -> aucun override.
    if stat_overrides:
        apply_spawn_stat_overrides(ctx, stat_overrides)
    e.add_component(StatsComponent(ctx=ctx))
    # `ctx.health` est RE-LU ici : sur un override `StatPart.Initial` de `HEALTH`, `ApplyModifier`
    # case 3 ecrit courant ET maximum -> `hp == hp_max == valeur de la formule`.
    e.add_component(HealthComponent(hp=ctx.health, hp_max=ctx.health))
    _seed_trait_owner_effects(state, e.id, ctx.traits, mult)
    _seed_derived_ability_owner_effects(state, e.id, ctx.traits, mult)
    # La TROISIEME source de la boucle ABILITIES d'`IdunBattle.Operations.
    # InitializeActorAbilitiesOperation$$Execute` : les owner-effects que les ABILITIES de l'unite
    # posent a son init. Le natif n'a qu'UNE Operation d'initialisation et elle vaut pour TOUT
    # acteur cree, summon compris -- l'omettre ici privait chaque invocation des passifs de son
    # propre kit (#570-r1 : le Grot Tank arrivait sans `Ramshackle_DmgReduction`, ecart PERMISSIF
    # et SILENCIEUX). `passive_level` indexe les variables per-niveau de l'owner-effect pose.
    # RAYON DE SOUFFLE MESURE avant l'ajout : sur les 669 kits du gameconfig, **0** unite
    # non-`lineup` avait une ability inscrite dans `ABILITY_INIT_OWNER_EFFECTS` /
    # `ABILITY_OWNER_EFFECTS` -- ce call-site ne change donc RIEN d'autre que ce que la meme
    # tranche y inscrit, et toute entree future sera vue par ce chemin.
    # ⚠ #570-r3 : MEME defaut que `build_summon_context` (`abilitiesLevel ?? abilityState.level`
    # de `SpawnUnitOptions$$WithStatsFromConfig`) -- l'owner-effect d'une ability de l'unite posee
    # s'indexe sous le MEME niveau que le reste de ses abilities. Un `None` ici faisait lire
    # `variables[1]` (`Ramshackle_DmgReduction` = 5 au lieu du palier du summoner).
    _seed_ability_owner_effects(state, e.id, visual_id, mult,
                                ability_level=(level if passive_level is None else passive_level))
    _maybe_seed_ignore_battle_fatigue(state, e.id, team, mult)   # aura SquigHound -> grots amis immunisés
    e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
    # ── LA FENETRE D'INTOUCHABILITE DU SPAWN (#433-r3-r2-r1-r1) ──────────────────────────────────
    # `IdunBattle.Operations.AddUnitOperation$$Execute` encadre son propre corps d'un
    # `UnitFlagsComponent$$Add(0x11)` ... `$$Remove(0x11)`, HORS de tout effet -- MEME structure que
    # `ResurrectUnitOperation$$Execute` (cf. `operations/resurrect.py`). Le bloc encadre a ete lu
    # sur `t6dpr4k06g` par extraction des appels entre les deux instructions : `HasTrait(0x1b)` +
    # log, `UnitComponent$$ClearFeet`, la boucle `MatchComponent$$NextId` / `Blueprints$$UnitFoot` /
    # `UnitComponent$$AddFoot`, `StateExtensions$$GetMatch`,
    # **`AddUnitOperation$$KillSteppableUnits`**, puis `get_StreamHelper` /
    # `RemoveTraitsThatAreNotInheritedWhenCloned` / `GetFullStateUpdateTags`.
    # C'est donc la MEME nature de fenetre que la resurrection, et elle n'est pas morte :
    # `KillSteppableUnits` passe par `KillUnitOperation$$Execute` en entier (cinq evenements de
    # mort, trois `RemoveEffects`), donc du code de jeu s'execute dedans.
    # PORTEE BORNEE A CE QUI EST PROUVE : la pose ouvre avant l'ecriture des pieds, le retrait ferme
    # apres le crush et AVANT `on_unit_added` -- le decompile ne montre aucune emission d'evenement
    # entre le crush et le `Remove(0x11)`, et rien n'autorise a etendre la fenetre au vecteur
    # `On(UnitAdded)` sans l'avoir lu.
    _fl = e.get_component(UnitFlagsComponent)
    if _fl is None:
        _fl = UnitFlagsComponent()
        e.add_component(_fl)
    _fl.add(UnitFlagsComponent.UNTARGETABLE)                # `flags.Add(0x11)`
    if feet_tiles and board is not None:
        # `AddUnitOperation$$Execute` : `ClearFeet` puis un `AddFoot` PAR tuile recue, dans l'ordre.
        # `set_unit_feet` est l'ECRIVAIN UNIQUE de l'empreinte (il recale la `PositionComponent` sur
        # `feet[0]` = la main tile) ; une liste d'UN element repose `feet = None` -> mono-pied nominal.
        coords = [(bt["col"], bt["row"]) for bt in
                  (board.by_id.get(t) for t in feet_tiles) if bt is not None]
        if coords:
            set_unit_feet(state, e.id, coords)
    # `IdunBattle.Operations.AddUnitOperation$$KillSteppableUnits(killer, steppableUnits)` — LU au
    # decompile, appele par `AddUnitOperation$$Execute` (xref UNIQUE) : poser une unite sur une
    # tuile qu'occupe un `Steppable` (0x1b) le DETRUIT, exactement comme un MOVE dessus. Le foyer
    # est le MEME que celui du move (`movement.py::_kill_steppable_units`, deja mirror complet de
    # la sequence de mort `KillUnitOperation$$Execute`) -- une seule Operation portee, deux
    # appelants natifs.
    #
    # `killer` = l'unite QUI VIENT D'ETRE POSEE, pas le summoner. Le discriminant est MESURE, pas
    # deduit : le Patermine porte `CosmicHorror_OnMoveAbility` (« se soigne des qu'il est le TUEUR
    # d'un decoy ami »), et sur le cast #501 qui crushe un decoy son delta HP live vaut **0** --
    # donc `OwnerIsActor` echoue, donc le tueur n'est pas lui.
    #
    # RAYON DE SOUFFLE (mesure) : ce crush ne mord que si la tuile de spawn porte un `Steppable`
    # VIVANT. Tous les call-sites qui choisissent leurs tuiles par `CanAddUnit` (GetEmRuntz,
    # SupremeCommander, CultDemagogue, Incursion, ...) en sont exclus PAR CONSTRUCTION :
    # `TileExtensions$$IsFreeTile` a `allowSteppable = 0` exige `content.IsEmpty()`. Le seul
    # call-site porte qui pose SUR un occupant est `MightFromBelow` (#501), dont le selecteur est
    # `Tiles(<decoys adjacents>)` sans aucun `CanAddUnit`.
    try:
        _kill_steppable_units(state, (tinfo["col"], tinfo["row"]), e.id)
    finally:
        # `flags.Remove(0x11)` -- cf. le bloc « FENETRE D'INTOUCHABILITE DU SPAWN » ci-dessus. Le
        # `finally` n'est pas un ornement : sans lui, une exception dans la sequence de mort du
        # steppable laisserait l'unite POSEE non ciblable pour le reste de la bataille.
        _fl.remove(UnitFlagsComponent.UNTARGETABLE)
    # `On(UnitAdded)` — APRES la pose ET apres le recalage multi-hex (`set_unit_feet` deplace la
    # `PositionComponent` sur la main tile, et les gates de PORTEE du vecteur la lisent).
    on_unit_added(state, e.id)
    # #291 `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` : le tour de l'unite qui vient
    # d'apparaitre PENDANT le tour de son proprietaire est immediatement TERMINE (sauf Steppable /
    # Hero / override d'options). Elle n'obtient donc jamais d'activation ce tour-la ; elle agit,
    # quand elle agit, par un `ComputerAction` FORCE (noeud DSL `PerformAIAction` de l'ability du
    # summoner) ou par `PlayAutomaticUnits` au turn-start suivant. Cf. la docstring du foyer.
    # `finish_turn_on_spawn=False` : l'appelant a un SOUS-BEHAVIOUR on-appearance (`SpawnUnitOptions
    # +0x18`) et doit donc appeler le foyer LUI-MEME **apres** l'avoir execute — c'est l'ordre du
    # corps natif (on-appearance d'abord, FinishUnitTurn ensuite).
    if finish_turn_on_spawn:
        trigger_spawned_unit_finish_turn(state, e.id)
    return e.id


#: Les stats que `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner` recopie du parent --
#: LUES au decompile (#1049) : le corps empile CINQ `StatModifierFormula(StatAmount(
#: Owner@<DSLSelectors+0x30>, <StatType>, StatPart.Current = 3))` dans la liste
#: `SpawnUnitOptions+0x28`, DANS CET ORDRE : `5 = Health`, `0x10 = FixedArmor`, `0 = Attack`,
#: `1 = Movement`, `0x14 = **NumberOfMembers**`.
#: ⚠ Le cinquieme etait ecrit `20` sans nom dans la docstring d'`execute_self_replica` ; il est
#: NOMME ici. Il n'est PAS dans la liste ci-dessous, et c'est SANS EFFET : `number_of_members` est
#: un CHAMP PLAT d'`entities/unit_context.py::UnitContext` (l. 42), donc le `dataclasses.replace`
#: du clone le recopie deja. L'ajouter a la liste ne changerait qu'une representation.
#: Les stats NON recopiees par le natif (crit/block/percage) viennent de la config de base ; comme
#: le clone porte le MEME `visualId` que son parent, elles sont identiques -> le port clone le
#: `UnitContext` entier et n'a pas a distinguer. Les sept cles supplementaires ci-dessous sont donc
#: SANS EFFET sur le resultat, et elles sont conservees telles quelles depuis #366-r1 (le percage,
#: notamment, est devenu une propriete adossee a `stats` : sans clonage explicite le clone le
#: PERDRAIT).
_COPY_OWNER_STATS = (StatType.ATTACK, StatType.MOVEMENT, StatType.HEALTH, StatType.FIXED_ARMOR,
                     StatType.CRIT_CHANCE, StatType.CRIT_DAMAGE, StatType.BLOCK_CHANCE,
                     StatType.BLOCK_DAMAGE, StatType.EXTRA_HITS,
                     StatType.EXTRA_PIERCE, StatType.EXTRA_PIERCE_MELEE,
                     StatType.EXTRA_PIERCE_RANGED)


def _spawn_copy_owner_at_tile(state: State, parent_id: int, tile, visual_id: str,
                              link_parent: bool = False) -> Optional[int]:
    """FOYER UNIQUE de `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner(dsl, abilityState)`
    -- pose UNE unite `visual_id` sur `tile` (id de tuile) avec l'OWNER et les STATS du parent.

    `CopyOwner`, lu verbatim : cinq `StatModifierFormula(StatAmount(Owner@<DSLSelectors+0x30>,
    <StatType>, StatPart.Current = 3))` (cf. `_COPY_OWNER_STATS`) puis
    `CreateSpawnOptions(abilityState, null, null, null)` -- **PAS de `WithStatsFromConfig`**, donc
    aucune variable `summon*` n'est lue : c'est ce qui distingue ce chemin de `_spawn_config_grot`.
    Une ability sans constantes `summon*` (`CursedOfTheWalkingPox` n'a NI constante NI variable dans
    le gameconfig) ne peut passer QUE par ici.

    case-spawn-requires-tile -- **AUCUNE entite n'est creee sans tuile** : `SpawnUnitBehaviour$$
    Execute` n'atteint `AddUnitOperation$$Execute` que DEPUIS une tuile iteree. `tile is None`, ou un
    id que le board ne resout pas, rend `None` AVANT le `state.add_entity()`.

    `link_parent` = le 1er argument natif de `IdunBattleLogic.Entities.DSLBehaviors$$Spawn`, qui est
    le PARENT du summon (`Unit_Parent_Id`, ce que lisent `Parent(Self)` et `Children(caster)`).
    ⚠ **`execute_self_replica` le laisse a `False`, et c'est un ECART PREEXISTANT, pas un choix de
    cette tranche** : le natif y passe `self@0x160` en parent tout comme ici. Le corriger changerait
    ce que `Children`/`Parent` rendent pour `necroSmnSwarm` -- hors perimetre, nomme ici.

    ⚠ **PAS de `_seed_ability_owner_effects` ni de `_kill_steppable_units`** : ce foyer reproduit
    EXACTEMENT ce que faisait `execute_self_replica` avant l'extraction, pour que le refactor soit
    value-preserving. Les deux manques sont donc PREEXISTANTS et partages par les deux call-sites ;
    le second est inerte quand la tuile vient d'un `CanAddUnit` (une tuile occupee par un
    `Steppable` VIVANT n'y est pas libre, `allowSteppable` etant faux au call-site de
    `CursedOfTheWalkingPox`)."""
    from dataclasses import replace as _dc_replace
    parent = state.get_entity(parent_id)
    if parent is None:
        return None
    coc = parent.get_component(OwnerComponent)
    csc = parent.get_component(StatsComponent)
    c_ctx = csc.ctx if csc is not None else None
    if coc is None or c_ctx is None:
        return None
    board = state.board
    tinfo = board.by_id.get(tile) if (tile is not None and board is not None) else None
    if tinfo is None:
        return None                  # (case-spawn-requires-tile)
    mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
    e = state.add_entity()
    e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=True,
                                  parent_id=(int(parent_id) if link_parent else None)))
    e.add_component(OwnerComponent(team=coc.team, player=coc.player))       # CopyOwner (owner)
    rep_stats = UnitStats()                          # CopyOwner (stats) : clone identite du parent
    for st in _COPY_OWNER_STATS:
        rep_stats.ensure_seeded(int(st), c_ctx.get_stat(int(st), 0))
    ctx = _dc_replace(c_ctx, entity_id=e.id, stats=rep_stats)
    e.add_component(StatsComponent(ctx=ctx))
    e.add_component(HealthComponent(hp=ctx.health, hp_max=ctx.health))
    _seed_trait_owner_effects(state, e.id, ctx.traits, mult)
    _seed_derived_ability_owner_effects(state, e.id, ctx.traits, mult)
    e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
    on_unit_added(state, e.id)       # `On(UnitAdded)` — APRES la pose
    # #291 `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours` : FinishUnitTurn(spawned, terminated),
    # sauf `Steppable`/`Hero`. ⚠ Le champ `SpawnUnitOptions+0x48` (`Nullable<bool>`) OVERRIDE ce
    # calcul quand il a une valeur -- `CursedOfTheWalkingPoxAbility$$CreateBehaviour` y pose
    # explicitement `true`. Le foyer n'expose pas cet override et n'en a PAS besoin ici : le
    # Poxwalker n'est ni `Steppable` ni `Hero`, donc le calcul par defaut rend deja `true`.
    trigger_spawned_unit_finish_turn(state, e.id)
    return e.id


def on_unit_added(state: State, unit_id: Optional[int]) -> list:
    """VECTEUR `On(UnitAdded = 0x32)` — mirror du point d'emission natif (`AddUnitOperation`) : une
    unite vient d'ENTRER en bataille, les triggers qui ecoutent cet evenement s'executent MAINTENANT,
    avec l'unite deja POSEE (position incluse — les gates de portee en dependent).

    Le port n'a pas de bus d'evenements pour ce vecteur : ce foyer TIENT LIEU de dispatch et doit
    etre appele par TOUT site qui cree une unite (a la fin, une fois la position posee). Un seul
    consommateur porte a ce jour :
      * `ContagionsOfNurgle_AddEffectToNewUnit_Ability` (case-dpw) — le debuff d'armure de l'aura
        Contagion se pose sur l'unite qui apparait DEDANS. MESURE : `astraSmnKell`, invoque par
        `SwornProtector` au contact de `deathPutrifier`, a `FixedArmor` 1496 -> **1197** live.
      * (#213) le 2e des cinq retraits de `GhostEffect` — `On(0x32 = UnitAdded) & NOT AreEqual(caster,
        EffectSource) & Contains(TargetTiles@0x190, Owner@0x148) & NOT HasTrait(caster, 0x1b =
        Steppable)` : une unite qui APPARAIT sur la tuile d'un time-ghost le dissipe, sauf si elle est
        Steppable (un decoy/spore-mine posé là ne compte pas). Ce consommateur-la passe par le
        DISPATCH GENERIQUE ajoute ci-dessous (c'est un effet-trigger du registre `EFFECT_TRIGGERS`,
        pas une fonction bespoke).
    Renvoie la liste des retours de vecteur (vide = no-op). None-safe."""
    if unit_id is None:
        return []
    from .triggers.loki.contagions_of_nurgle import apply_on_unit_added
    out = []
    r = apply_on_unit_added(state, int(unit_id))
    if r is not None:
        out.append(r)
    # DISPATCH GENERIQUE `On(UnitAdded = 0x32 = 50)` : `AbilityEntities.ctor(added, added, added)`
    # -> actor = caster = target = l'unite qui vient d'apparaitre.
    from .triggers.base import TriggerEvent
    from .triggers.dispatch.core import evaluate_trigger_operation
    out += evaluate_trigger_operation(
        state, TriggerEvent(EventTriggerType.UnitAdded, int(unit_id), int(unit_id),
                            ranged=False, profile=None))
    return out


IGNORE_BATTLE_FATIGUE = int(EffectType.IgnoreBattleFatigue)  # 1079 — vérifié par BattleFatigueAbility (behaviour.py, meme const, #158)


def _team_has_squighound(state: State, team) -> bool:
    """La team a-t-elle un porteur VIVANT du passif `SquigHound` (Snotflogga) ? = source de l'aura."""
    import gameconfig as GC
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None or not uc.alive or oc.team != team:
            continue
        if "SquigHound" in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
            return True
    return False


def _maybe_seed_ignore_battle_fatigue(state: State, unit_id: int, team, mult: int) -> bool:
    """`SquigHound_IgnoreBattleFatigueEffect IdunBattle.Entities.Effects.Loki.SquigHound_IgnoreBattleFatigueEffect$$CreateTargetSelector` (aura de Snotflogga sur les grots amis) : si la team
    a un porteur `SquigHound` VIVANT, pose l'effet `IgnoreBattleFatigue`(1079=0x437) sur l'unité → immunisée
    du flee `BattleFatigue` (gate déjà porté `behaviour.py:121` : `NOT HasEffect(self, 1079)`). Idempotent.
    ⚠ Snapshot au spawn : le retrait de l'aura si Snotflogga meurt N'EST PAS modélisé (grot garde l'immunité)."""
    if not _team_has_squighound(state, team):
        return False
    if state.effects is None:
        state.effects = EffectsState.seed({})
    if state.effects.has_effect(unit_id, effect_type=IGNORE_BATTLE_FATIGUE):
        return False
    eff = EffectFactory.create({"name": "IgnoreBattleFatigue", "effectType": IGNORE_BATTLE_FATIGUE,
                                "remaining": 0}, ability_variables_multiplier=int(mult or 100))
    eff.target = unit_id
    state.effects.add_effect(unit_id, eff)
    return True


def _materialize_owner_effect(state: State, unit_id: int, name: str, mult: int,
                              ability_level: Optional[int] = None,
                              bonded: Optional[int] = None,
                              source: Optional[int] = None) -> bool:
    """Matérialise UN owner-effect (par nom) sur l'unité dans `EffectsState`, PERMANENT (rem=None), comme les
    unités initiales seedées depuis capture — pour que `attacker_modifiers`/`defender_modifiers` (qui lisent
    `state.effects`) le voient. Idempotent (gate `has_effect`). Renvoie True si ajouté.

    `ability_level` = niveau de l'ability SOURCE de l'owner-effect (indexe ses variables per-niveau ; ex.
    HypersensoryAbilities.hpPct[level] = 30..50). Threadé par `_seed_ability_owner_effects` depuis
    `ctx.passive_ability_level` ; None = fallback stack level dans l'effet.

    `bonded` = l'ENTITE BONDEE (`BaseEffect.bonded`), c.-a-d. le 5e argument natif `bondedEntity`
    d'`IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect`, deja RESOLU en id par l'appelant --
    exactement comme `AddEffectOperation.execute` le recoit sur le chemin de COMBAT. C'est ce champ
    (`+0x34` de l'objet que fabrique
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$GetEffectBuilder`) qui fait basculer le natif
    du builder ORDINAIRE au builder de BOND ; `None` / `0` = builder ordinaire, effet pose SANS lien,
    ce qui est la degradation NATIVE et non un refus de poser. #963-r5.

    `source` = `EffectComponent.SourceUnit @+0x10`, le 3e argument natif (`source`). Il valait
    implicitement `None` pour tous les owner-effects seedes -- ce qui est exact pour le canal
    ORDINAIRE, ou le natif passe `Owner` en source ET en cible et ou les consommateurs port
    retombent sur `target`. Un BOND, lui, distingue les TROIS (source / target / bonded), d'ou le
    parametre. `None` = comportement historique, strictement inchange."""
    if state.effects is None:
        state.effects = EffectsState.seed({})
    if state.effects.has_effect(unit_id, name=name):
        return False                                         # déjà présent
    # effectType depuis l'enum (l'entité-effet native porte un EffectType @+0x58) : le nom d'owner-effect ==
    # nom de membre `EffectType` -> resout l'id (ex. HypersensoryAbilities_MinimalHealth=1380). None si le nom
    # n'est pas un membre (fidélité-safe ; sans ça un effet materialise a effect_type=None -> casse les
    # consommateurs qui font `int(effect_type)`, ex. filtre chainage G2).
    etype = EffectType.__members__.get(name)
    eff = EffectFactory.create({"name": name, "effectType": (int(etype) if etype is not None else None),
                                "remaining": 0,                # rem 0 -> permanent
                                "source": source},
                               ability_variables_multiplier=int(mult or 100),
                               ability_level=ability_level)
    eff.target = unit_id
    # `DefaultBondEffectBuilder(id, abilityState, bondedEntityId)` -- le champ `+0x10` du composant de
    # bond de l'entite-effet, que relit `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`.
    # Ecrit ICI, a la creation de l'entite-effet, exactement comme le fait le vecteur de COMBAT
    # (`AddEffectOperation.execute`) : le builder EST ce qui construit l'entite. `None` => builder
    # ordinaire, champ absent -- et le lien reste `None`, jamais un `0` qui se lirait « entite 0 ».
    if bonded is not None:
        eff.bonded = int(bonded)
    state.effects.add_effect(unit_id, eff)
    return True


def _seed_trait_owner_effects(state: State, unit_id: int, traits, mult: int) -> list:
    """`IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute (boucle TRAITS) : à la création d'unité, CHAQUE
    trait ajoute à son PORTEUR les owner-effects de `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetEffectToBeAddedToOwnerForTrait (dict `Trait..idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor +0x30). Sans ce seed, un summon SPAWNÉ n'a AUCUN effet -> ses
    traits de dégât (HeavyWeapon +25% ranged, RangedSpecialist +33% ranged, ...) ne s'appliquent PAS à ses
    attaques (gap corrigé)."""
    return [name for tr in (traits or [])
            for name in get_effect_to_be_added_to_owner_for_trait(tr)
            if _materialize_owner_effect(state, unit_id, name, mult)]


def _seed_derived_ability_owner_effects(state: State, unit_id: int, traits, mult: int) -> list:
    """Chemin trait -> ability DÉRIVÉE -> owner-effect posé à l'INIT de l'ability (mécanisme DISTINCT des 2
    dicts owner-effect directs). Mirror `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` (trait -> ability,
    dict Trait +0x0/+0x8) puis `<Ability>.CreateBehaviour` (DSL `AddEffect(owner)` à l'init de l'ability).

    Cas porté : trait **BigTarget** -> ability `BigTarget` (0x406) -> `IdunBattleLogic.Entities.Abilities.Active.Loki.BigTargetAbility$$CreateBehaviour` = `AddEffect(BigTarget_AdjacentEffect)` (aura -1 hit ranged aux alliés ring-1, source-side).
    Les autres traits summon dérivent aussi une ability mais leur owner-effect à l'init n'est pas encore LU
    (cf. `factory.ABILITY_INIT_OWNER_EFFECTS`) -> non seedés (fidélité-safe)."""
    added: list = []
    for tr in (traits or []):
        for ab in get_derived_abilities_for_trait(tr):
            for name in get_owner_effects_added_on_ability_init(ab):
                if _materialize_owner_effect(state, unit_id, name, mult):
                    added.append(name)
    return added


TELEPORT_STRIKE_TELEPORTING_IN = int(EffectType.TeleportStrike_TeleportingIn)  # 1035 — etat deep-strike (#158 ; 1035=effet, PAS UnitTrait.CloseCombatWeakness)


def _seed_ability_owner_effects(state: State, unit_id: int, vid: str, mult: int,
                                ability_level: Optional[int] = None) -> list:
    """`IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute` (boucle ABILITIES) : pour chaque ability de
    l'unite, l'owner-effect pose par son `CreateBehaviour` a l'init (DSL `AddEffect(owner)`). Ex. passive
    `PathOfCommand` -> `PathOfCommand_ExtraDmg` (aura +Attack) ; passive `HypersensoryAbilities` ->
    `HypersensoryAbilities_MinimalHealth` (HP-floor). Abilities lues de gameconfig (active+passive).
    `ability_level` (= `ctx.passive_ability_level`) indexe les variables per-niveau de l'owner-effect posé.

    DEUX sources natives dans CETTE boucle (dicts DISTINCTS, tous deux portés) :
      * `<Ability>.CreateBehaviour` -> `AddEffect(owner)` (`ABILITY_INIT_OWNER_EFFECTS`) ;
      * `StaticBattleRules.ActiveAbility$$GetEffectToBeAddedToOwnerForAbility` (dict `ActiveAbility` +0x50,
        `ABILITY_OWNER_EFFECTS`) — chemin DIRECT, ex. GravitonRifle -> GravitonRifle_ExtraPierce (#113)."""
    import gameconfig as GC
    from ...entities.effects.factory import (BOND_PARENT_OF_OWNER,
                                             get_owner_bond_effects_added_on_ability_init,
                                             get_owner_flags_added_on_ability_init)
    from ..components import parent_of
    gu = GC.unit(vid) or {}
    abilities = list(gu.get("activeAbilities") or []) + list(gu.get("passiveAbilities") or [])
    # QUATRIEME source de la MEME boucle native (#1005) : l'ability TERTIAIRE, c.-a-d. l'item
    # RELIQUE EQUIPE. `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` la monte
    # par `TriggeredAbilityComponent$$TryAdd(id, tertiaryState, 3)` -- elle est donc DANS la boucle
    # d'`InitializeActorAbilitiesOperation$$Execute` au meme titre que les deux autres, et son
    # `<X>_InitAbility` pose son owner-effect comme n'importe quel passif (`Vitarus` -> 1466).
    # La lire dans le gameconfig par `visualId` serait FAUX : une relique n'est PAS dans le kit,
    # elle vit dans `BC.Units[].TertiaryAbility` -> `ctx.tertiary_ability` (canal
    # `unitAbilityStates`, #357). `None` = aucune relique -> rien a ajouter.
    _e = state.get_entity(int(unit_id))
    _sc = _e.get_component(StatsComponent) if _e is not None else None
    _ctx = getattr(_sc, "ctx", None)
    _tertiary = getattr(_ctx, "tertiary_ability", None)
    if _tertiary:
        abilities.append(str(_tertiary))
    # TROISIEME source de la MEME boucle native (#964-r1) : `<Ability>_InitAbility.CreateBehaviour`
    # -> `DSLBehaviors$$AddFlag(Owner@+0x30, <UnitFlag>)`. Meme trigger `OnOwnerSpecificAbilityInit`
    # que les owner-effects ci-dessous, autre mutation. Cf. `ABILITY_INIT_OWNER_FLAGS`.
    for ab in abilities:
        for flag in get_owner_flags_added_on_ability_init(ab):
            _add_owner_flag_on_ability_init(state, unit_id, int(flag))
    # ⚠ LE COUPLE (niveau, multiplicateur) D'UNE RELIQUE N'EST PAS CELUI DES PASSIFS, et c'est
    # MESURE (#1005, RPC `unitAbilityStates` sur `bloodMephiston` porteur de `Vitarus`) : son
    # `TriggeredAbilityComponent` porte `raw = [1470, .., level = 1, mult = 100, .., hierarchie = 3,
    # ..]` la ou ses passifs portent `level = 50, mult = 180`. Le natif resout le `ConfigVar` de
    # l'owner-effet contre l'`AbilityState` que l'`AddEffect` lui a passe -- `AbilityState(Owner,
    # <l'ability courante>)`, donc l'etat TERTIAIRE. `Vitarus.extraDmg[1] = 490` contre
    # `extraDmg[10] = 728` apres clamp : passer le couple passif sur-appliquerait +238 par coup,
    # en silence. MEME lecture que `triggers/base.py::triggered_ability_state`.
    def _couple(ab: str):
        if _tertiary and str(ab) == str(_tertiary):
            return (int(getattr(_ctx, "tertiary_ability_variables_multiplier", 100) or 100),
                    getattr(_ctx, "tertiary_ability_level", None))
        return (mult, ability_level)
    added = [name for ab in abilities
             for name in (get_owner_effects_added_on_ability_init(ab)
                          + get_effect_to_be_added_to_owner_for_ability(ab))
             if _materialize_owner_effect(state, unit_id, name, _couple(ab)[0],
                                          ability_level=_couple(ab)[1])]
    # CINQUIEME source de la MEME boucle native (#963-r5) : les owner-effects de type BOND, poses
    # par `DSLBehaviors$$AddBondEffect(effectType, abilityState, source, targets, bondedEntity, ...)`
    # sous le meme trigger d'INIT. Ils vivent dans un registre SEPARE parce qu'ils portent une
    # donnee de plus -- le selecteur du 5e argument --, que `_materialize_owner_effect` ne savait
    # pas ecrire : c'etait l'etage NOMME de #963-r5.
    #
    # Le selecteur est RESOLU ICI, par le foyer deja porte du noeud correspondant : `parent_of` est
    # le mirror d'`IdunBattle.Entities.UnitExtensions$$GetParent(u, state, root = false)`, celui-la
    # meme qu'appelle `IdunBattle.Entities.Selectors.ParentSelector$$Select`. Un selecteur INCONNU
    # du registre ne fait pas deviner : `bonded` reste `None`, donc builder ORDINAIRE.
    #
    # ⚠ ORDRE : `UnitComponent(parent_id=...)` est pose par `spawn_unit` AVANT cet appel, donc le
    # parent est deja lisible au moment ou l'on seede. Sur le chemin CAPTURE, l'instance est deja
    # la (avec son `bondedEntityId` publie par `readBondLink`) et le gate `has_effect` rend un no-op
    # exact -- ce seed ne peut donc pas ecraser une mesure.
    for ab in abilities:
        for name, selector in get_owner_bond_effects_added_on_ability_init(ab):
            bonded = None
            if selector == BOND_PARENT_OF_OWNER:
                p = parent_of(state, int(unit_id))
                bonded = p.id if p is not None else None
            if _materialize_owner_effect(state, unit_id, name, _couple(ab)[0],
                                         ability_level=_couple(ab)[1],
                                         bonded=bonded, source=int(unit_id)):
                added.append(name)
    return added


def _add_owner_flag_on_ability_init(state: State, unit_id: int, flag: int) -> bool:
    """`IdunBattle.Entities.Behaviours.AddFlagBehaviour$$Execute` -> `UnitFlagsComponent$$Add(flag)`.

    Le `OrderedSet` natif rend l'operation IDEMPOTENTE : re-seeder la meme unite (atterrissage
    deep-strike, re-chargement d'etat) ne pose pas deux fois le drapeau. Le composant est cree s'il
    manque -- le natif en a un d'office sur toute entite-unite."""
    from ..components import UnitFlagsComponent
    e = state.get_entity(int(unit_id))
    if e is None:
        return False
    c = e.get_component(UnitFlagsComponent)
    if c is None:
        c = UnitFlagsComponent()
        e.add_component(c)
    c.add(int(flag))
    return True


def initialize_deferred_actor_abilities(state: State, unit_id: int) -> list:
    """Le volet PASSIVES DEFERREES de l'atterrissage : `IdunBattle.Operations.
    InitializeActorAbilitiesOperation$$Execute` rejoue pour une unite qui vient de perdre son etat
    « je descends du ciel » -- owner-effects des abilities et des traits (ex. aura
    `PathOfCommand_ExtraDmg` d'`eldarAutarch`), puis refresh des stat-mods projetes.

    SEPARE de `land_deep_strike` depuis #448-r2 : le RETRAIT de l'effet est desormais un noeud DSL
    (`RemoveEffect(EffectSelf)`) porte par les triggers PROPRES d'`ATeleportingEffect`
    (`runner/operations/triggers/loki/teleporting_in.py`) ; ce qui reste ici est la couche
    IMPERATIVE que le natif enchaine derriere. GROUND TRUTH LIVE de l'enchainement (2026-08-01,
    cascade d'un `act move` sur `eldarAutarch`) : dans le MEME `User_MoveUnit`, apres
    `ChangePosition`, on lit `LoseEffect TeleportStrike_TeleportingIn` PUIS
    `ActivateEffect PathOfCommand_ExtraDmg` + `ChangeStats <allie> Attack_Modification=400`."""
    ent = state.get_entity(unit_id)
    uc = ent.get_component(UnitComponent) if ent is not None else None
    sc = ent.get_component(StatsComponent) if ent is not None else None
    ctx = sc.ctx if sc is not None else None
    vid = uc.visual_id if uc is not None else ""
    mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100) if ctx is not None else 100
    traits = list(getattr(ctx, "traits", None) or [])
    added = _seed_ability_owner_effects(state, unit_id, vid, mult,
                                        ability_level=getattr(ctx, "passive_ability_level", None))   # PathOfCommand aura / HP-floor
    added += _seed_trait_owner_effects(state, unit_id, traits, mult)    # owner-effects des traits (idempotent)
    added += _seed_derived_ability_owner_effects(state, unit_id, traits, mult)
    if added:
        # `ActivateEffect` -> `UpdateEffectTargets` -> `AStatModifierEffect$$ApplyModification` : un
        # owner-effect a stat-mod PROJETE ecrit sa `ValueModification` chez ses cibles-selecteur DES
        # sa pose. GROUND TRUTH LIVE de l'atterrissage (#373, eldarAutarch) : l'event stream porte,
        # dans le MEME `Effect_Refresh`, `ActivateEffect e=<autarch>` PUIS `ChangeStats e=<allie>
        # UnitStats_CritChance_Modification_Change=20`. Sans ce refresh la pose etait INERTE cote
        # stats (l'effet apparaissait chez le porteur, la cible ne gagnait rien) -- le volet
        # `create_aura_*` du jumeau ATTACK, lui, est un canal de LECTURE, donc il ne le voyait pas.
        refresh_aura_stat_modifiers(state)
    return added


def land_deep_strike(state: State, unit_id: int) -> Optional[dict]:
    """ATTERRISSAGE d'une unite TeleportStrike (deep-strike), forme IMPERATIVE COMPLETE (retrait de
    l'effet + passives deferrees). Ground truth live : l'unite passe de « teleporting-in » (effet
    1035, non-ciblable, passives NON initialisees) a « posee » -> TeleportStrike_TeleportingIn
    RETIRE + `InitializeActorAbilities` -> ciblable + auras projettent. No-op si l'unite n'est pas
    teleporting-in.

    ⚠ CE N'EST PLUS LE CHEMIN DE PRODUCTION (#448-r2). Le QUAND est desormais porte par les trois
    triggers de retrait d'`IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$
    CreateHandleTriggerAbilitiesInternal` (`On(4 UnitAfterMove)`, `On(0x2a PreUnitAbility)`,
    `On(0x28 UnitFinishedTurn) & HasTile`), pas par une boucle d'`EndTurnOperation`. La fonction
    reste comme forme imperative utilisable par un test/probe qui veut FORCER l'atterrissage sans
    passer par un vecteur d'evenement."""
    if state.effects is None or not state.effects.has_effect(
            unit_id, effect_type=TELEPORT_STRIKE_TELEPORTING_IN):
        return None
    for e in state.effects.by_unit.get(int(unit_id), []):     # retire TeleportingIn (consomme l'instance)
        if not e.consumed and e.effect_type == TELEPORT_STRIKE_TELEPORTING_IN:
            e.consumed = True
    return {"landed": unit_id,
            "owner_effects_added": initialize_deferred_actor_abilities(state, unit_id)}


class SpawnUnitOperation:
    """Crée `count` unités summon de type `visual_id`, owner = caster (team+player), placées sur des tuiles
    libres adjacentes à la cible, stats résolues depuis `summon_ability`. Renvoie la liste des entityId
    spawnés. Marque chaque summon `acts_on_appearance` (attaque immédiate, exécutée ailleurs)."""

    @staticmethod
    def execute(state: State, caster_id: int, target_id: int, summon_ability: str,
                visual_id: str, count: int) -> list:
        caster = state.get_entity(caster_id)
        if caster is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        if coc is None:
            return []
        c_ctx = csc.ctx if csc is not None else None
        level = getattr(c_ctx, "active_ability_level", None) if c_ctx else None
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100) if c_ctx else 100
        spawned: list = []
        board = state.board
        # === 1. LE TILE-SELECTEUR, EVALUE UNE SEULE FOIS ===
        # ScarabHive `IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabHiveAbility$$ExecuteBehaviour` :
        #   Cache(First(Get(SelectTiles(SortByDistance(SortByDistance(
        #     CanAddUnit(AdjacentTiles(target@0x178)), caster@0x160), caster@0x160))), count), 1)
        # -> DEUX SortByDistance sur la MEME origine (mirrore tel quel ; `OrderBy` LINQ etant
        # STABLE le second est idempotent) puis prise en tete. **AUCUN tirage** — surtout PAS
        # `_pick_randomly_one`.
        # `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` fait `tiles =
        # tileSelector.Select(ctx)` UNE fois (`*(entities+0x58)`), PUIS itere cette liste : la
        # resolution est un SNAPSHOT pris avant le premier `AddUnitOperation$$Execute`. On mirrore
        # cette structure -- un seul `_free_tiles_adjacent` + un seul tri + `[:count]` -- au lieu de
        # re-tirer la tete a chaque tour en excluant les tuiles deja prises. Les deux suites
        # COINCIDENT (retirer la tete ne change pas l'ordre relatif du reste, et les `OrderBy` LINQ
        # sont stables), mais seule celle-ci a la forme du natif : un etat qui changerait ENTRE deux
        # spawns (un `On(UnitAdded)` qui tuerait une unite et libererait une tuile) les ferait
        # diverger, et c'est le natif qui a raison.
        # `First(source, count)` rend **min(count, len(source))** elements : une cible dont les
        # voisines LIBRES sont moins nombreuses que `count` en rend MOINS -- c'est le seul endroit
        # ou le nombre de summons est decide.
        free = _free_tiles_adjacent(state, target_id, set(), native_order=True)
        picked = _first_n(_sort_by_distance(state, _sort_by_distance(state, free, caster_id),
                                            caster_id), count)
        tiles = [(t, board.by_id[t]) for t in picked] if board is not None else []
        # === 2. UNE ENTITE PAR TUILE ITEREE (case-spawn-requires-tile) ===
        # `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute`, branche `SpawnUnitOptions+0x60
        # == 0`, est un `foreach (tile in tiles) { AddUnitOperation.Execute(unit, [tile.Id], ...) }` :
        # l'entite NAIT DE L'ITERATION. Zero tuile => zero appel => **zero entite, zero evenement**
        # (ni `On(UnitAdded)`, ni `TriggerSpawnedUnitBehaviours`). La boucle `range(count)` d'avant
        # creait l'unite PUIS lui cherchait une place : quand la cible etait encerclee, elle laissait
        # un summon FANTOME sans `PositionComponent` (mesure #251 : `spawned = [1, 2]`, un des deux
        # hors plateau) que rien ne ramassait ensuite.
        for tile, tinfo in tiles:
            e = state.add_entity()                           # id auto (≠ live ; confront par vis/team/pos)
            # ai_controlled : le summon (trait `Summon` = « moves and attacks automatically at the beginning
            # of its turn ») est joué par l'IA au TURN-START de sa team via `run_ai_control_pass` (#65) —
            # mirroir du flag runtime `IdunBattle.View.Game.IdunGameViews$$IsPlayerAiControlled. TOUS les summons d'ability sont
            # ai_controlled : le scarab s'auto-dédouble (`ScarabSummon` IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour) + attaque, jamais inerte
            # (cf. docstring module). PAS de gate apparition-only (le « 0 action » via aiStepDryRun etait un
            # artefact de sonde : ce chemin ne DRIVE PAS la passe AI-control turn-start).
            e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=True))
            e.add_component(OwnerComponent(team=coc.team, player=coc.player))   # CopyOwner
            ctx = build_summon_context(e.id, visual_id, summon_ability, level, mult)
            e.add_component(StatsComponent(ctx=ctx))
            e.add_component(HealthComponent(hp=ctx.health, hp_max=ctx.health))
            # [InitializeActorAbilitiesOperation boucle TRAITS] owner-effects des traits du summon dans
            # EffectsState (sinon ses traits de dégât ne s'appliquent pas à ses attaques — gap corrigé).
            _seed_trait_owner_effects(state, e.id, ctx.traits, mult)
            # [trait -> ability dérivée -> AddEffect(owner) à l'init] ex. BigTarget -> BigTarget_AdjacentEffect.
            _seed_derived_ability_owner_effects(state, e.id, ctx.traits, mult)
            e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
            on_unit_added(state, e.id)   # `On(UnitAdded)` — APRES la pose
            trigger_spawned_unit_finish_turn(state, e.id)   # #291 FinishUnitTurn(spawned, terminated)
            spawned.append(e.id)
        # NB on-appearance (`UseNormalAttackIfAble`) = tranche ultérieure (les ids spawnés sont renvoyés ;
        # `Entity`/`State` ont __slots__ → pas de marqueur posé ici).
        return spawned

    @staticmethod
    def execute_self_replica(state: State, caster_id: int, visual_id: str, count: int = 1) -> list:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$ExecuteBehaviour` (auto-DÉDOUBLEMENT) : le summon s'invoque
        LUI-MÊME. Spawn `count` clones sur des tuiles LIBRES adjacentes au **CASTER** (self@0x160), owner+
        stats = `IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner(caster)` (owner du caster + STATS clonées du parent).

        CopyOwner (RE IdunBattle.Entities.Behaviours.SpawnUnitOptions$$CopyOwner) copie les StatType `{0=Attack, 1=Movement, 5=Health, 16=Armor, 20}` du
        caster (`StatAmount(..., StatPart=3)`) puis `CreateSpawnOptions(owner)` — PAS de WithStatsFromConfig.
        Les stats NON copiées (crit/block/hits) viennent de la config de base ; comme le parent EST un
        `necroSmnSwarm` (même type que le clone), elles sont identiques → on clone le ctx entier du parent.
        Distinct de `execute` (ScarabHive : adjacent-CIBLE + stats `ability_var` summoner-scaled).

        case-spawn-requires-tile -- MEME regle que `execute` : `SpawnUnitBehaviour$$Execute` itere son tile-selecteur et ne
        cree une entite QUE depuis une tuile iteree. Un scarab entoure (aucune tuile libre au contact)
        ne se dedouble PAS -- il ne produit pas un clone hors plateau. `_pick_randomly_one` sur un pool
        VIDE consomme **zero tirage** (`PickRandomAmountSelector$$Select` sort sur `candidates.Count <
        1`, cf. sa docstring), donc s'arreter la ne decale AUCUN flux RNG."""
        caster = state.get_entity(caster_id)
        if caster is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        if coc is None or (csc.ctx if csc is not None else None) is None:
            return []
        spawned: list = []
        chosen: set = set()
        for _ in range(max(0, int(count))):
            tiles = _free_tiles_adjacent(state, caster_id, chosen)   # adjacent au CASTER (self@0x160)
            # `PickRandomly(CanAddUnit(AdjacentTiles(self@0x160)), 1, …)` : 1 tirage MEME a pool=1.
            tile = _pick_randomly_one(state, tiles)
            gid = _spawn_copy_owner_at_tile(state, caster_id, tile, visual_id)
            if gid is None:
                break                    # (case-spawn-requires-tile) pas de tuile iteree -> pas d'entite, pas d'evenement
            chosen.add(tile)
            spawned.append(gid)
        return spawned

    @staticmethod
    def execute_copy_owner_on_tiles(state: State, owner_id: int, tiles, visual_id: str) -> list:
        """`IdunBattleLogic.Entities.DSLBehaviors$$Spawn(parent, tiles, unitId, options)` avec
        `options = SpawnUnitOptions$$CopyOwner(dsl, abilityState)` et un TILE-SELECTEUR fourni par
        l'APPELANT (deja evalue) -- la branche `SpawnUnitOptions+0x60 == 0` de
        `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` : **UNE unite PAR tuile iteree**.

        Distinct d'`execute_self_replica` juste au-dessus par le seul TILE-SELECTEUR : celui-la
        l'inline (`PickRandomly(CanAddUnit(AdjacentTiles(self)))`, avec son tirage RNG), celui-ci le
        recoit. Les DEUX partagent le foyer `_spawn_copy_owner_at_tile` (= `CopyOwner`), donc le
        clone d'owner et de stats est ecrit UNE fois.

        Consommateur : `IdunBattleLogic.Entities.Abilities.Active.Loki.
        CursedOfTheWalkingPoxAbility$$CreateBehaviour` (`triggers/loki/cursed_of_the_walking_pox.py`),
        dont le selecteur est `First(CanAddUnit(TargetTiles@<DSLSelectors+0x78>), 1)` -- **aucun
        tirage aleatoire**, donc aucun flux RNG consomme ici.

        `link_parent=True` : le 1er argument natif de `Spawn` est `Owner@<DSLSelectors+0x30>`, le
        PARENT du summon (`Unit_Parent_Id`). Cf. la note d'`_spawn_copy_owner_at_tile`."""
        return [gid for gid in
                (_spawn_copy_owner_at_tile(state, owner_id, t, visual_id, link_parent=True)
                 for t in (tiles or []))
                if gid is not None]

    @staticmethod
    def execute_pilein_replica(state: State, parent_id: int) -> list:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.PileInAbility$$CreateBehaviour` — auto-DÉDOUBLEMENT du grot (PASSIF fin-de-tour).
        Spawn UN grot sur une tuile LIBRE ring-1 adjacente au parent, **stats = `WithStatsFromConfig(PileIn)`**
        = `ability_var(PileIn, summon*, level, mult)` — PAS un clone (le grot PileIn = ~0.606× le grot
        GetEmRuntz : 2910 vs 4802 PV @lvl65/mult100). Renvoie [id] ou [].

        `level`/`mult` = ceux du parent (`active_ability_level`/`ability_variables_multiplier`, propagés depuis
        le summoner). ⚠ GAP : un grot SEEDÉ depuis un combatSnapshot live n'a PAS de `active_ability_level`
        (level=0) → stats PileIn fausses ; il faut un GetEmRuntz porté (ou le level capté) pour résoudre.
        Placement natif = `First(SortByFormula(Randomize(CanAddUnit(AdjacentTiles(self@0x148))),
        If(HasTrait(@0x180, 0x1b), Direct(0), Direct(1)), ascending=false), 1)` — PORTÉ (case-130 SS5) :
        `Randomize` = `PickRandomAmountSelector(amount = 0x7fffffff)` consomme **`len(pool)` tirages**
        (bornes décroissantes) puis le tri stable à clé constante laisse la tuile TIRÉE EN PREMIER.
        Cf. `_randomize` / `_sort_by_formula_pilein`."""
        import gameconfig as GC
        parent = state.get_entity(parent_id)
        if parent is None:
            return []
        coc = parent.get_component(OwnerComponent)
        csc = parent.get_component(StatsComponent)
        p_ctx = csc.ctx if csc is not None else None
        if coc is None or p_ctx is None:
            return []
        visual_id = ((GC.ability("PileIn") or {}).get("constants") or {}).get("summonId")   # orksGrot
        if visual_id is None:
            return []
        level = getattr(p_ctx, "active_ability_level", None)
        mult = int(getattr(p_ctx, "ability_variables_multiplier", 100) or 100)
        tiles = _free_tiles_adjacent(state, parent_id, set(), native_order=True)
        # `First(SortByFormula(Randomize(CanAddUnit(AdjacentTiles(self@0x148))),
        #        If(HasTrait(@0x180, 0x1b), Direct(0), Direct(1)), ascending=false), 1)`
        # `Randomize` = `PickRandomAmountSelector(amount = 0x7fffffff)` = MELANGE COMPLET ->
        # **`len(pool)` tirages**, bornes DECROISSANTES ; le tri qui suit est stable et sa cle est
        # constante sur le pool -> la tuile rendue est celle TIREE EN PREMIER.
        tile = _first(_sort_by_formula_pilein(state, _randomize(state, tiles)))
        # case-spawn-requires-tile -- LA TUILE D'ABORD, l'entite ensuite (meme regle que les quatre
        # autres sites). `IdunBattle.Entities.Behaviours.SpawnUnitBehaviour$$Execute` n'atteint
        # `AddUnitOperation$$Execute` que DEPUIS une tuile ITEREE : pas de tuile RESOLUE, pas
        # d'appel, donc pas d'entite. Le `tile is None` seul laissait passer le cas « id de tuile
        # non resolvable sur le board » -> `state.add_entity()` puis pose CONDITIONNELLE de la
        # position, c.-a-d. exactement le fantome hors plateau du cas.
        board = state.board
        tinfo = board.by_id.get(tile) if (tile is not None and board is not None) else None
        if tinfo is None:
            return []                                        # aucune tuile ring-1 libre -> pas de spawn
        e = state.add_entity()
        e.add_component(UnitComponent(visual_id=visual_id, alive=True, ai_controlled=True))
        e.add_component(OwnerComponent(team=coc.team, player=coc.player))
        ctx = build_summon_context(e.id, visual_id, "PileIn", level, mult)   # WithStatsFromConfig(PileIn)
        e.add_component(StatsComponent(ctx=ctx))
        e.add_component(HealthComponent(hp=ctx.health, hp_max=ctx.health))
        _seed_trait_owner_effects(state, e.id, ctx.traits, mult)
        _seed_derived_ability_owner_effects(state, e.id, ctx.traits, mult)
        _maybe_seed_ignore_battle_fatigue(state, e.id, coc.team, mult)   # aura SquigHound -> grot immunisé
        e.add_component(PositionComponent(col=tinfo["col"], row=tinfo["row"]))
        on_unit_added(state, e.id)      # `On(UnitAdded)` — APRES la pose
        trigger_spawned_unit_finish_turn(state, e.id)       # #291 FinishUnitTurn(spawned, terminated)
        return [e.id]

    @staticmethod
    def execute_squighound_summon(state: State, caster_id: int, target_id: int) -> list:
        """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SquigHoundSummonUnitAbility$$CreateBehaviour` (passif triggé, orksRuntherd). APRÈS une
        attaque du caster (trigger `On(0x26)` — cf. wiring after-hit), si **< maxSummons(5)** grots amis, spawn
        1 grot sur la MEILLEURE tuile LIBRE adjacente à la CIBLE (`First(SortTilesByUtilityForSummon(
        CanAddUnit(AdjacentTiles(target@0x178)), 7 = UtilityType.Tile, caster@0x160), 1)` = **0 tirage**,
        PORTÉ case-130 SS5 via `_sort_tiles_by_utility_for_summon`),
        stats `WithStatsFromConfig(SquigHound)` (4802 PV @lvl65), `active_ability_level = casterLevel`
        (→ lève le GAP PileIn). On-appearance `PerformAIAttack` = FLAGGÉ non porté. Renvoie [id] ou []."""
        import gameconfig as GC
        caster = state.get_entity(caster_id)
        board = state.board
        if caster is None or board is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        c_ctx = csc.ctx if csc is not None else None
        if coc is None or c_ctx is None:
            return []
        consts = (GC.ability("SquigHound") or {}).get("constants") or {}
        vid = consts.get("unitId")
        max_summons = int(consts.get("maxSummons") or 5)
        if vid is None:
            return []
        # condition : NOT (grots amis >= maxSummons)  ->  strictement < maxSummons
        n_grots = sum(1 for e in state.entities.values()
                      if (u := e.get_component(UnitComponent)) is not None and u.alive and u.visual_id == vid
                      and (o := e.get_component(OwnerComponent)) is not None and o.team == coc.team)
        if n_grots >= max_summons:
            return []
        # `First(SortTilesByUtilityForSummon(CanAddUnit(AdjacentTiles(target@0x178)), 7 = UtilityType
        # .Tile, caster@0x160), 1)` : tri DESCENDANT par utilite de tuile, **0 tirage**.
        cands = _free_tiles_adjacent(state, target_id, set(), native_order=True)
        tile = _first(_sort_tiles_by_utility_for_summon(state, cands, caster_id))
        level = getattr(c_ctx, "active_ability_level", None)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        gid = _spawn_config_grot(state, vid, tile, "SquigHound", level, mult, coc.team, coc.player)
        return [gid] if gid is not None else []

    @staticmethod
    def execute_control_edict_summon(state: State, caster_id: int) -> list:
        """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ControlEdictAbility$$SummonMinion` (branche PROTECTOR, passif de Tan Gi'da). Apres une
        attaque NORMALE du caster (trigger `On(0x26)`), si **< maxSummons[level]** Skitarii Vanguards amis
        vivants, spawn 1 `admecSmnVanguard` sur une tuile LIBRE ADJACENTE AU **CASTER** (Tan), stats
        `WithStatsFromConfig(ControlEdict)` (`summonHp/summonDmg/summonArmor[level]`), `active_ability_level =
        casterLevel` (propage -> le Skitarii joue son tour via run_ai_control_pass). Renvoie [id] ou [].

        DIFFERENCES vs `execute_squighound_summon` (mirror natif distinct) :
          - hex libre adjacent au **CASTER** (`AdjacentTiles(caster)`), PAS a la cible ;
          - cap = `ability_var("ControlEdict","maxSummons", level)` = **PER-NIVEAU (3/4/5)**, PAS une constante ;
          - **AUCUNE on-appearance** (le Skitarii ne joue pas a l'apparition -- il agit a SON tour ; la branche
            Conqueror d'un cast ULTERIEUR le fait attaquer). Cf. verdict RE ControlEdict.
        `If(NOT AmountIsEqualOrGreater(Children INTER UnitsWithId(admecSmnVanguard), maxSummons)) -> Spawn` :
        no-op au cap (pas de remplacement). Placement natif = `First(SortTilesByUtilityForSummon(CanAddUnit(
        AdjacentTiles(caster@0x148)), 7 = UtilityType.Tile, @0x160), 1)` = **0 tirage**, PORTE (case-130 SS5,
        `_sort_tiles_by_utility_for_summon` -- meme noeud que SquigHound ; surtout PAS un `PickRandomly`)."""
        import gameconfig as GC
        caster = state.get_entity(caster_id)
        board = state.board
        if caster is None or board is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        c_ctx = csc.ctx if csc is not None else None
        if coc is None or c_ctx is None:
            return []
        consts = (GC.ability("ControlEdict") or {}).get("constants") or {}
        vid = consts.get("unitId")                        # admecSmnVanguard
        if vid is None:
            return []
        level = getattr(c_ctx, "active_ability_level", None)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        max_summons = int(ability_var("ControlEdict", "maxSummons", level) or 5)   # PER-NIVEAU (pas constante)
        # cap : `Children INTER UnitsWithId(admecSmnVanguard)` = Skitarii amis vivants (approx par team+visualId).
        n = sum(1 for e in state.entities.values()
                if (u := e.get_component(UnitComponent)) is not None and u.alive and u.visual_id == vid
                and (o := e.get_component(OwnerComponent)) is not None and o.team == coc.team)
        if n >= max_summons:                              # NOT AmountIsEqualOrGreater(count, max) False -> no-op
            return []
        # CanAddUnit(AdjacentTiles(CASTER@0x148)) puis `First(SortTilesByUtilityForSummon(., 7 =
        # UtilityType.Tile, @0x160), 1)` : tri DESCENDANT par utilite de tuile, **0 tirage**.
        tiles = _free_tiles_adjacent(state, caster_id, set(), native_order=True)
        tile = _first(_sort_tiles_by_utility_for_summon(state, tiles, caster_id))
        gid = _spawn_config_grot(state, vid, tile, "ControlEdict", level, mult, coc.team, coc.player)
        return [gid] if gid is not None else []

    @staticmethod
    def execute_master_of_tutelaries_screamer(state: State, owner_id: int) -> list:
        """`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$CreateSummonBehaviour` (triggered 1173,
        armee par l'effet 1197 sur Abraxas — #202-C). Spawn UN `thousSmnScreamer` :

          RemoveEffect(EntitiesWithAnyEffect(@0x80, 0x425=1061 GeminaeSuperia_JustSummonedEffect))
          & Spawn( owner@0x148,
                   PickRandomly( TilesUnitCanAttackFrom( CanAddUnit(AdjacentTiles(owner@0x148)),
                                                         owner, unitId_2="thousSmnScreamer" )
                                 .Otherwise(possible), 1 ),
                   unitId_2, WithStatsFromConfig2(config 1096) + onAppearance=PerformAIAttackFromCurrentPosition )

        - possible = tuiles LIBRES adjacentes au PORTEUR (== `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$GetPossibleSummonTiles`) ;
        - preferred = celles d'ou le Screamer (MELEE, Power 3 hits) peut attaquer = >=1 ennemi VIVANT
          adjacent (porte d'elevation `is_adjacent`) (== `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterOfTheTutelaries_SummonAbility$$GetPreferredSummonTiles` :
          `TilesUnitCanAttackFrom(...).Otherwise(possible)`) ;
        - stats `WithStatsFromConfig2(config 1096)` = summonHp/summonDmg de MasterOfTheTutelaries au
          niveau ACTIF du porteur (la variante `2` derive le niveau de l'ability-state propage par
          l'effet 1197 = celui de l'active 1096 — meme valeur que le Horror) ;
        - le RemoveEffect(1061) préalable est mirrore par consommation des instances 1061 (marqueur
          `GeminaeSuperia_JustSummonedEffect`) — NO-OP offline tant qu'aucun poseur de 1061 n'est
          porte (aucun AddEffect(1061) dans ce kit ; poseur natif hors perimetre, residu case-202 §8).
        L'ON-APPEARANCE (`PerformAIAttackFromCurrentPosition`) est execute par l'APPELANT (le trigger),
        comme SquigHound/ControlEdict. Renvoie [id] ou []."""
        import gameconfig as GC
        caster = state.get_entity(owner_id)
        board = state.board
        if caster is None or board is None:
            return []
        coc = caster.get_component(OwnerComponent)
        csc = caster.get_component(StatsComponent)
        c_ctx = csc.ctx if csc is not None else None
        if coc is None or c_ctx is None:
            return []
        consts = (GC.ability("MasterOfTheTutelaries") or {}).get("constants") or {}
        vid = consts.get("unitId_2")                      # thousSmnScreamer (GetStringConstant(config, 4))
        if vid is None:
            return []
        # RemoveEffect(1061) sur tous les porteurs — mirror structurel, no-op offline (cf. docstring).
        eff = getattr(state, "effects", None)
        if eff is not None:
            for _uid, _effs in eff.by_unit.items():
                for _e in _effs:
                    if not _e.consumed and \
                            _e.effect_type == int(EffectType.GeminaeSuperia_JustSummonedEffect):
                        _e.consumed = True
        possible = _free_tiles_adjacent(state, owner_id, set())  # CanAddUnit(AdjacentTiles(owner))
        # TilesUnitCanAttackFrom(possible, owner, "thousSmnScreamer") : Screamer = MELEE -> tuiles avec
        # >=1 ennemi VIVANT hex-adjacent (porte d'elevation |dElev|<2, `is_adjacent` maison).
        elev = {}
        neigh = None      # tri-etat : `None` = pas de canal -> repli geometrique NOMME d'`is_adjacent`
        epos = []
        for eid2, e2 in state.entities.items():
            oc2 = e2.get_component(OwnerComponent)
            uc2 = e2.get_component(UnitComponent)
            pc2 = e2.get_component(PositionComponent)
            if oc2 is None or pc2 is None or oc2.team == coc.team:
                continue
            if uc2 is not None and not uc2.alive:
                continue
            epos.append((pc2.col, pc2.row))
        if board is not None:
            # FOYER UNIQUE du canal d'elevation (#433-r4-r1-r4) -- meme carte, memes clefs
            # OMISES quand l'elevation n'est pas captee, que celle derivee pour le `DslContext`.
            # #433-r4-r1-r4-r2-r1 : le voisinage NATIF (liste STOCKEE) est le PREMIER etage
            # d'`IterateAdjacentTiles`, l'elevation le second -- n'en deriver qu'un laisse le
            # predicat plus PERMISSIF que le natif sur toute arete que la connectivite refuse.
            elev = elevations_by_pos(board) or {}
            neigh = adjacent_neigh_by_pos(board)
        def _can_attack_from(tid) -> bool:
            ti = board.by_id.get(tid)
            if ti is None:
                return False
            return any(is_adjacent((ti["col"], ti["row"]), p, elev, neigh) for p in epos)
        preferred = [t for t in possible if _can_attack_from(t)]
        sel = preferred if preferred else possible        # .Otherwise(possible)
        tile = _pick_randomly_one(state, sel)             # PickRandomly(sel, 1) : 1 tirage MEME a pool=1
        level = getattr(c_ctx, "active_ability_level", None)
        mult = int(getattr(c_ctx, "ability_variables_multiplier", 100) or 100)
        # MESURE LIVE (diag 202c, runner 183) : Screamer MaxHealth 4487 = summonHp_2[50] x 180%
        # (2493*1.8) -> les stats du Screamer = variables suffixees `_2` (summonHp_2/summonDmg_2,
        # meme convention que CultDemagogue), PAS summonHp/summonDmg (le Horror).
        gid = _spawn_config_grot(state, vid, tile, "MasterOfTheTutelaries", level, mult,
                                 coc.team, coc.player, key_suffix="_2")
        return [gid] if gid is not None else []
