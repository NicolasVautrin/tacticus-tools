"""Scene — l'état de bataille live consommé par la prédiction (la COUTURE oracle/moteur, forme objet).

Consolide en UN objet les deux sacs de dicts de l'ancien PV (`predictor` statique cold + `sctx` par-pas) :
tables par-unité (UnitContext, armure, bouclier, mult de rareté, niveau d'ability, faction) + état courant
(hp, position, équipe, effets matérialisés) + métadonnées de tuile (élévation). Les fonctions de prédiction
lisent la Scene (`scene.hp(id)`, `scene.effects(id)`, …) au lieu de deux dicts non typés — modèle objet propre.

`from_predictor_sctx` BRIDGE les dicts existants (le seam RPC `build_predictor`/`step_context`/`refresh_shields`
reste le fournisseur ; ré-logeable dans Scene.from_live plus tard sans changer le calcul)."""
from __future__ import annotations

from dataclasses import dataclass, field

import gameconfig as GC
from engine.entities.effects_state import EffectsState
from engine.entities.effects_state import (   # #953 : foyer PARTAGE avec la face COMBAT
    melee_defeats_from_units as _melee_defeats_from_units,
    seed_battle_counters as _seed_battle_counters)
from engine.entities.unit_context import UnitContext
from ..entities.effect_targets import is_effect_target as _iet
from ..entities.effect_type import EffectType
from ..entities.effects.factory import (EffectFactory, EFFECT_CLASSES,
                                            ABILITY_INIT_OWNER_EFFECTS)
from ..runner.components import (StatsComponent, OwnerComponent, PositionComponent,
                                         HealthComponent, UnitComponent, ShieldComponent,
                                         EffectsOwnedComponent, is_machine_of_war,
                                         unit_prevents_overkill, unit_has_moved,
                                         unit_has_teleported, unit_has_used_active_ability,
                                         unit_tiles_moved_this_turn)
from ..runner.components import effects_prevent_overkill
from ..runner.snapshot import active_ability_names_by_unit
from ..runner.snapshot import active_only_rows
from ..runner.snapshot import config_active_ability_names_by_unit
from ..runner.snapshot import passive_ability_names_by_unit
from ..runner.snapshot import triggered_ability_ids_by_unit, triggered_ability_states_by_unit
from engine.entities.pathfinding.board import Board
from engine.entities.stats import StatComponent, ValueModification
from engine.entities.stats import StatType as _ST
from engine.entities.traits.unit_trait import UnitTrait, trait_names_from_ids
from ..entities.pathfinding.board import adjacent_neigh_by_pos
from ..entities.unit_faction import UnitFaction
from ..entities.rarity import assert_rarity_channel      # #999-r3 (canal #1039)
from .. import battle_query as _bq       # #954 : ring-1 STOCKE + porte d'elevation
from . import adjacency as _adj          # foyer PARTAGE multi-tuiles + UnitSelectionType (#954)

#: `UnitFaction.DarkAngels = 0xa` -- le NOM de la valeur d'enum, parce que c'est ce que le natif
#: compare (`System.Enum.ToString(UnitFaction)` puis `String.Equals` sur `FactionComponent+0x30`),
#: et non l'ordinal. Consommateur : `Scene.adjacent_dark_angels_friends` (#932).
_DARK_ANGELS = UnitFaction.DarkAngels.name
#: `UnitFaction.Tyranids = 0xc` -- meme regle de comparaison que `_DARK_ANGELS` ci-dessus.
#: Consommateur : `Scene.synaptic_insight_adjacent_tyranid` (#1073).
_TYRANIDS = UnitFaction.Tyranids.name
#: `UnitTrait.Steppable = 0x1b` et `UnitTrait.Object = 0xd` -- les DEUX traits que
#: `IdunBattleLogic.Entities.DSLSelectors$$NonSteppableOrObjectUnits` retire (`UnitsWithoutTrait`
#: x2, intersectes). `Scene.traits` publie des NOMS (`trait_names_from_ids`), d'ou `.name` : c'est
#: l'ordinal du BUILD qui est la source, jamais un litteral recopie. Consommateur :
#: `Scene._enmity_adjacent` (#948).
_TRAIT_STEPPABLE = UnitTrait.Steppable.name
_TRAIT_OBJECT = UnitTrait.Object.name
#: #1078-r3 -- `UnitsWithTrait(..., UnitTrait.Psyker = 0x3ea, 3)` de `HunterOfSouls_ExtraDamage`.
_TRAIT_PSYKER = UnitTrait.Psyker.name


@dataclass
class Scene:
    """État live pour la prédiction. Tables par-id + état courant + élévation. Accès via méthodes."""

    ctx_by_id: dict            # {id: UnitContext} (stats/traits/arme normale, cold)
    armor_by_id: dict          # {id: fixedArmor} — DYNAMIQUE (debuffs), refresh par-pas
    shield_by_id: dict         # {id: totalShield} — DYNAMIQUE (accordé/consommé), refresh par-pas
    mult_by_id: dict           # {id: abilityVariablesMultiplier %} (rareté)
    ablvl_by_id: dict          # {id: passiveAbilityLevel}
    vis_by_id: dict            # {id: visualId}
    units: list                # decisionView.units (courant)
    hp_by_id: dict             # {id: hp courant}
    pos_by_id: dict            # {id: (col,row)}
    team_by_id: dict           # {id: team}
    eff_state: object          # EffectsState (effets matérialisés seed)
    hpmax_by_id: dict = field(default_factory=dict)   # {squadId: hpMax} (observeBattle)
    # #419-r1-tr10-r2 -- EMPREINTE par entite : {id: [(col,row), ...]}, mirror de
    # `IdunBattle.Entities.EntityExtensions$$GetTiles` (= la materialisation de l'`IterateTiles`
    # que consomme `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select`). Canal :
    # `decisionView.units[].feet` et `decisionView.mows[].{feet,platformTiles}`.
    # Une entree ABSENTE ou VIDE = canal MUET -> `adjacency.iterate_tiles` retombe sur la MainTile,
    # c.-a-d. le comportement d'avant le capteur, EXACTEMENT. Elle n'est JAMAIS devinee : la seule
    # facon d'y entrer est que le hook l'ait mesuree.
    # ⚠ Les MoW ne sont PAS dans `units` (canal `.mows` separe) : sans cette table, leurs pieds
    # seraient publies et jamais lus.
    feet_by_id: dict = field(default_factory=dict)
    # #1036-r2 -- NATURE D'ENTITE : les ids qui sont des `EntityType.Machine` (= 6), c.-a-d. les
    # `casterId` de `decisionView.mows`. Mirror face DECISION de `components.is_machine_of_war`
    # (presence d'un `MachineComponent`) et du natif
    # `IdunBattle.Entities.EntityExtensions$$IsMachine`, dont le corps entier est
    # `<EntityType de l'entite> == 6` (temoins : `$$IsUnit` compare a `1`, `$$IsMachinePlatform`
    # a `7`). Lu par `IsMachine(Owner)` du `ConditionalSelector` de
    # `CabalOfSorcerers_ExtraDamagePctEffect`.
    # `None` = canal NON MESURE (Scene batie hors `step_context`) -> `is_machine` rend `None` et le
    # lecteur ne prend que la branche du selecteur qui ne depend pas de la reponse. Un `frozenset()`
    # VIDE, lui, est une MESURE (aucune MoW dans cet etat).
    machine_ids: frozenset | None = None
    elev_by_pos: dict | None = None                    # {(col,row): elevation} (tileMeta)
    tile_effects_by_pos: dict | None = None            # {(col,row): [noms d'effets de tuile]} — DYNAMIQUE
    #                                                    # (la glace LordOfTempests s'ACCUMULE en bataille) ->
    #                                                    # fourni FRAIS par décision (tileMeta, cf. context.py) ;
    #                                                    # None = inconnu (bonus position-dépendants inertes)
    board: object | None = None                        # Board (voisins natifs, adjacence hex) — cf.
    #                                                    # engine.entities.pathfinding.board ; None → evenq
    # `MachineOfWarPosition` du joueur COURANT (1=Top, 2=Bottom) — la valeur que compare le predicat
    # `IsPositionMachineForCurrentPlayer` (`BattleQuery$$GetPositionMachineForPlayer`, cascade portee
    # dans `engine.services.machine_of_war_position`). C'est une propriete du PLATEAU, pas d'une MoW
    # deployee. La face DECISION la calcule dans `engine.ai.context` et la depose ICI parce que
    # `make_damage_predictions` ne recoit que la `Scene` : sans ce fil, l'arbre de 1148
    # (`GetTargetAreaTiles` = `If(IsPositionMachineForCurrentPlayer(2), Direct(1), Direct(4))`)
    # prendrait TOUJOURS la branche `else` -- une degradation SILENCIEUSE qui deplace la
    # zone-triangle. `None` = **non mesure** -> le predicat rend False (jamais une valeur devinee).
    machine_of_war_position: int | None = None
    # AbilityState PER-ABILITY (#100) : {uid: {abilityId: {"level","multiplier"}}} — capteur
    # combatSnapshot.abilityStates (entrée ActiveAbility._abilityState @0x4c). C'est le couple que
    # le natif passe au playbook et qui indexe les variables config (TryGetVariableArrayForLevel
    # IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel) ; le canal global (mult_by_id/activeAbilityLevel) est un fallback.
    abstate_by_id: dict = field(default_factory=dict)
    # AbilityState PER-TRIGGERED (#1042-r1) : {uid: {abilityId: (level, multiplier)}} — capteur
    # `unitAbilityStates`, le MEME payload que `_seed_measured_triggered`. C'est ce que relit
    # `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` pour un effet pose par une
    # TRIGGERED, et pour une MYTHIQUE de MoW c'est l'etat **TERTIAIRE** (`1..4 / 100`) -- que
    # `abstate_by_id` ne porte PAS (son capteur ne publie que les ACTIVES). Table vide = canal muet
    # -> l'accesseur rend `None` et le lecteur retombe sur le couple bake de l'instance.
    trigstate_by_id: dict = field(default_factory=dict)
    # TotalAttacksMade PER-UNITE (#106) : {uid: totalAttacksMade} — capteur actorStats
    # (ActorStatisticsComponent +0x20). Indexe le buff MartialInspiration (+33%/tour). Defaut {}
    # -> count=0 (debut de bataille / from_state offline) si non capte.
    actorstats_by_id: dict = field(default_factory=dict)
    # Stat DEFENSE PER-UNITE (#194) : {uid: StatComponent(stat 3)} — mirror du DefenseComponent natif
    # (IdunBattle.Entities.Components.DefenseComponent$$.cctor) lu par `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction+0x436` : ses modifications
    # (ex. tuile Thorns −50) deviennent des entrees %-list (negate=1 → +50 → ×1.5). DYNAMIQUE (la
    # modification suit l'occupation de tuile) → capture combatSnapshot (defense + statDelta.defense),
    # refresh par-pas via `refresh_shields`. Defaut {} → axe inerte (defense non modifiee partout).
    defstat_by_id: dict = field(default_factory=dict)
    # TurnsStarted PER-UNITE (#46) : {uid: turnsStarted} — stat 12 (`UnitComponent.turnsStarted@+0x58`,
    # incr. StartTurn ; `IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate` = GetStat(unit,0xc)). Indexe le
    # gate `ShouldEvaluate(unit)` slot-4 des playbooks « pas au 1er tour » (corps folde IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate :
    # TheQuickening/HeroicFusillade/VigilanceEternal = `GetStat(unit,12) > 1`). DYNAMIQUE (incremente
    # a CHAQUE tour demarre) → capture combatSnapshot, refresh par-pas via `refresh_shields`.
    # Defaut {} → uid absent = non capte (l'accesseur rend None, le gate ne mord pas a l'aveugle).
    turns_started_by_id: dict = field(default_factory=dict)
    # TurnsFinished PER-UNITE (#27-r8) : {uid: turnsFinished} — le compteur `UnitComponent + 0x5c`,
    # incremente par `IdunBattle.Operations.EndTurnOperation$$Execute` et relu par
    # `IdunBattle.Entities.UnitExtensions$$GetTurnsFinished`. Il indexe le gate slot-4
    # `...InstrumentsOfVengeancePlaybook$$GetUseProbability` (Zero a 0, Half a 1, One sinon).
    # ⚠ Ce n'est PAS `turnsStarted` (stat 12) et ce n'est PAS un `StatType` : une unite APPARUE
    # PENDANT le tour de son proprietaire (tout summon) rate le bump de `StartTurn` mais prend celui
    # d'`EndTurn`, donc `turns_finished == turns_started + 1` ensuite (meme mesure que
    # `runner/snapshot.py` §N11). DYNAMIQUE (incremente a chaque tour termine) -> capture
    # `combatSnapshot.units[].turnsFinished`, refresh par-pas via `refresh_shields`.
    # Defaut {} -> uid absent = NON CAPTE (l'accesseur rend None, le gate ne mord pas a l'aveugle).
    turns_finished_by_id: dict = field(default_factory=dict)
    # `receivedDamageThisTurn` PER-UNITE (#487-r1) : {uid: set(DamageProfileType)} -- les CLES du
    # Dictionary `ActorStatisticsComponent + 0x80`, ecrit par
    # `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterReceivedDamage` et lu par
    # `IdunBattle.Entities.UnitExtensions$$HasTakenDamageOfDamageProfileThisTurn` (PRESENCE de cle,
    # jamais un compte). C'est le substrat de l'utilite d'`IdunBattle.AI.Playbook.Loki.
    # HellfyreMissileRackPlaybook$$EvaluateNonComparable`.
    # ⚠ TRI-ETAT, et le defaut est `None` = **PAS MESURE**, pas un dict vide : ce champ n'est publie
    # par AUCUN canal live (ni `decisionView`, ni `combatSnapshot`, ni le hook `actorStats` -- qui ne
    # porte que `+0x20`). Un `{}` servi en live se lirait « aucune unite n'a pris de degat ce tour »,
    # ce qui est une AFFIRMATION, et elle ferait REFUSER l'ability (utilite 0 < MIN_UTILITY 1) :
    # degradation RESTRICTIVE silencieuse. `from_state` (rejeu OFFLINE) le renseigne, parce que le
    # runner TIENT le compteur (`UnitComponent.received_damage_this_turn`, alimente par
    # `runner/operations/damage.py` et vide par `turnflow`) -- meme forme que #266 (flag `Moved`) et
    # #27-r8 (`turnsFinished`) : la face DECISION LIT ce que la face COMBAT TIENT.
    # Point d'ancrage a hooker pour la face LIVE : `ActorStatisticsComponent + 0x80`, cote
    # `frida/hooks/features/ai-step/rpc-snapshot.ts` (meme fenetre de reinject que #545-r1).
    received_damage_profiles_by_id: dict | None = None
    # Stat ATTACK COURANT PER-UNITE (#45-s18) : {uid: GetStat(Attack, Current)} — la lecture EXACTE des
    # noeuds DSL `StatAmount(Self, Attack, Current)` (ex. splash Psyker `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$GetAttackDamage`).
    # DYNAMIQUE : les ValueModifications vont et viennent (aura RitesOfBattle +1298 par ADJACENCE a
    # Calgar — vecu 31337 : 2101 au deploiement, 803 au s18 une fois Njal eloigne) → le cold
    # `ctx_by_id[uid].attack` (fige au build) SURESTIME/SOUS-ESTIME des qu'une aura bouge. Capture
    # combatSnapshot (stats.attack), refresh par-pas via `refresh_shields`. Defaut {} → fallback
    # `ctx.attack` (from_state offline : le UnitContext du State est deja live).
    attack_cur_by_id: dict = field(default_factory=dict)
    # Stat EXTRA_HITS COURANT PER-UNITE (#57a) : {uid: GetStat(ExtraHits=17, Current)} — les effets
    # stat-mod DYNAMIQUES sur les hits (Swarm_HitReduction 1021 : `SwarmAbility.CreateBehaviour
    # IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour` poste EXTRA_HITS = -min(membresInitiaux-?, membresManquants) a chaque membre perdu ;
    # vecu 1357 s15 u135 ripperSwarm : extraHits -2, hits natifs 3 vs 5 offline). Le cold
    # `ctx.stat(EXTRA_HITS)` (fige a l'hydratation — au SPAWN pour un summon #53) devient stale des
    # que des membres meurent. Capture combatSnapshot (stats.extraHits), refresh par-pas.
    extra_hits_cur_by_id: dict = field(default_factory=dict)
    # ChargedUnitIds PER-UNITE (case-r32) : {uid: set(ids charges CE TOUR)} — mirror de
    # `UnitComponent.ChargedUnitIds@+0x190`, le 2e terme de `IdunBattle.Core.Services.BattleQuery$$IsCharging`.
    # Alimente par `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging`, vide par
    # `IdunBattle.Operations.FinishUnitTurnOperation$$Execute`. `from_state` le lit de l'ECS (donc une
    # prediction faite sur un etat que le runner offline a fait EVOLUER voit les charges deja acquises,
    # comme le natif). ⚠ `from_predictor_sctx` / etat rechargé par `load_state` : AUCUN RPC n'expose ce
    # champ -> table VIDE, degradation RESTRICTIVE (le bonus de charge est omis, jamais invente). Gap
    # d'outillage nomme : le point d'ancrage a hooker est `UnitComponent+0x190` cote `combatSnapshot`.
    charged_by_id: dict = field(default_factory=dict)
    # PreventOverkill PER-UNITE (#195) : {uid: `UnitExtensions.HasFlag(u, 0x13)`} — le 5e argument
    # `isPreventOverkill` que le natif passe à `IsOverkill` DEUX FOIS sur la face décision (dans
    # `ApplyTraitDamageLimitsToDamage`, où il lit `HasFlag(defender, 0x13)` juste avant l'appel ; et
    # via `DamagePredictionResult.PreventOverkill@+0xb3` que lisent `WillBeOverkill`/`MightBeOverkill`).
    # Rempli par `from_state` depuis l'ECS (`unit_prevents_overkill` : composant de flags d'abord,
    # effet 1354 ensuite) ET, depuis O5, côté live par `combatSnapshot.unitFlags` — la LECTURE
    # DIRECTE de `UnitFlagsComponent` (`HasFlag` invoqué par valeur d'enum). La dérivation par
    # l'effet reste le REPLI, pour un hook antérieur à O5 : elle porte le même invariant, mais
    # c'est une SECONDE expression d'un fait qui existe tel quel dans l'ECS — et le composant a un
    # `Add` public, donc un futur poseur impératif la rendrait fausse en silence. DYNAMIQUE (les
    # triggers de `FuelledByFury_BlockOverkillEffect` posent et retirent le flag en cours de
    # bataille) -> re-capturé par pas via `refresh_shields`.
    prevent_overkill_by_id: dict = field(default_factory=dict)
    # `UnitFlag.Moved` (=0) et `UnitFlag.Teleported` (=0xc) PER-UNITE (#266) : {uid: HasFlag(u, f)}.
    # MEME canal que `prevent_overkill_by_id` — `combatSnapshot.unitFlags` côté live (invocation de
    # `IdunBattle.Entities.UnitExtensions$$HasFlag` par valeur d'enum), `UnitFlagsComponent` de l'ECS
    # côté `from_state`. C'est le PREMIER des deux termes que la prédiction native voit sous
    # `HasFlag(Self, Moved)` — cf. `prediction.prediction_has_moved` pour le second (la tuile
    # simulée). DYNAMIQUE (posé par le déplacement, purgé à l'entrée de tour par
    # `UnitFlagsComponent$$RemoveTurnFlags`) -> re-capturé par pas via `refresh_shields`.
    moved_by_id: dict = field(default_factory=dict)
    teleported_by_id: dict = field(default_factory=dict)
    # `UnitFlag.ActiveAbilityUsed` (=2) PER-UNITE (#17) : {uid: HasFlag(u, 2)}. MEME canal que
    # `moved_by_id`. C'est le gate d'ENTREE d'`IdunBattle.AI.ActionGenerators.
    # ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` (1re instruction de son
    # etat 0 : `if (HasFlag(unit, 2)) return 0`) -> une unite qui a deja consomme son action ne
    # produit AUCUNE action d'ability (attaque normale COMPRISE) et ne peut plus que se deplacer.
    # DYNAMIQUE (pose au cast, purge a l'entree de tour par `UnitFlagsComponent$$RemoveTurnFlags`)
    # -> re-capture par pas via `refresh_shields`.
    active_ability_used_by_id: dict = field(default_factory=dict)
    # `TilesMovedThisTurn` PER-UNITE (case-322-r2) : {uid: `ActorStatisticsComponent+0xf0`} — le
    # compteur REEL de tuiles parcourues CE TOUR, ecrit par
    # `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved` et remis a zero en FIN de tour par
    # `IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetThisTurn`. C'est le PREMIER des
    # deux termes que `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` rend a la
    # prediction — cf. `prediction.prediction_tiles_moved_this_turn` pour le second (le pas simule).
    # Que ce terme soit le compteur REEL, NON pollue par les simulations precedentes, est LU :
    # `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile` SAUVEGARDE `+0xec` et
    # `+0xf0` avant l'action simulee et les RESTAURE apres (mesure de fermeture : sans cette
    # restauration, 17 tuiles candidates evaluees a la suite auraient accumule leurs chemins).
    # DYNAMIQUE au meme titre que `moved_by_id` (chaque deplacement l'incremente) -> re-capture par
    # pas via `refresh_shields`. Table VIDE = **non mesure** -> l'accesseur rend `None`.
    tiles_moved_by_id: dict = field(default_factory=dict)
    # Lien enfant -> SUMMONER PER-UNITE (#378) : {uid: parentId | None} — mirror de
    # `IdunBattle.Entities.Components.ChildComponent.ParentId` (BEntityId), le champ que lit
    # `IdunBattle.Entities.UnitExtensions$$GetParent` (`TryGetComponent<ChildComponent>` puis
    # `state.GetEntity(ParentId)`), foyer du selecteur
    # `IdunBattle.Entities.Selectors.ParentSelector$$Select` (noeud DSL
    # `IdunBattleLogic.Entities.DSLSelectors$$Parent`).
    # Canal : `combatSnapshot.units[].parentId` cote live (capteur #378, TRI-ETAT), l'ECS
    # (`UnitComponent.parent_id`) cote `from_state`. STATIQUE par unite (pose une fois au spawn,
    # jamais reecrit) mais la POPULATION ne l'est pas : un summon apparait mid-bataille -> la table
    # est re-capturee par pas comme les autres, via `refresh_shields`.
    # Consommateur : le noeud `If( AmountIsGreaterThanZero(Parent(EffectSource)),
    # Parent(EffectSource), EffectSource )` de `IdunBattle.Entities.Effects.Loki.
    # DefenderOfTheGreaterGood_ExtraHitsEffect$$CreateEffectHitsBonusForAttack` (#372).
    # ⚠ TRI-ETAT PAR ENTREE, pas par table : `uid` ABSENT = non mesure (l'accesseur rend `None`,
    # le consommateur retombe sur la source elle-meme = comportement anterieur) ; `uid` PRESENT a
    # `None` = mesure faite, cette unite n'est l'enfant de personne. Table vide = hook anterieur a
    # #378 -> aucune unite mesuree, degradation STRICTEMENT anterieure.
    parent_by_id: dict = field(default_factory=dict)
    # Cache PAR EQUIPE du cardinal `Enemies(Owner, UnitsWithTrait(AllUnits, Psyker))` (#208) —
    # calcule a la demande par `_enemy_psykers_alive`, valable pour TOUTE la duree de vie de la
    # Scene (elle est reconstruite a chaque pas de decision). Table de travail, pas une entree.
    _psykers_by_team: dict = field(default_factory=dict)

    @property
    def neigh_by_pos(self) -> dict | None:
        """`{(col,row): [(col,row), ...]}` — le voisinage NATIF (`boardGraph.neighbours`, la liste
        STOCKEE que rend `IdunBattle.Core.Services.TileQuery$$IterateAdjacentTiles`), DERIVE du
        board plutot que stocke (#433-r4-r1-r4-r2).

        La `Scene` porte deja `board` ; poser un champ de plus obligerait chacun de ses DEUX
        constructeurs (`from_state`, `from_predictor_sctx`) et chaque montage de test a le remplir,
        et le premier qui l'oublierait rouvrirait le trou EN SILENCE — c'est la meme dette que
        `TARGETING_OPTIONS`, et la meme parade que `DslContext.__post_init__` (#433-r4-r1-r4).

        TRI-ETAT (`None` = pas de canal) : le foyer `entities.pathfinding.board.adjacent_neigh_by_pos`
        ne rend jamais `{}`, donc `battle_query.is_adjacent` garde son repli geometrique NOMME au
        lieu de conclure « aucun voisin ». Memoise : le board est STATIQUE pour toute la bataille."""
        cached = getattr(self, "_neigh_by_pos_cache", "?")
        if cached == "?":
            cached = adjacent_neigh_by_pos(self.board)
            object.__setattr__(self, "_neigh_by_pos_cache", cached)
        return cached

    def charged(self, uid) -> set:
        """Ids que `uid` a CHARGES ce tour (vide si non capte)."""
        return self.charged_by_id.get(uid) or set()

    def parent(self, uid):
        """`UnitExtensions.GetParent(uid, state, root=false)` = le SUMMONER direct de `uid`, ou
        `None` (#378). `None` recouvre les deux etats non-parent -- « mesure faite, pas d'enfant »
        et « pas mesure » -- parce que les DEUX consommateurs portes collapsent dessus (le noeud
        `If(AmountIsGreaterThanZero(Parent(src)), Parent(src), src)` retombe sur `src`, et le
        selecteur `Parent` rend une liste vide). `parent_measured` tranche quand un appelant a
        besoin de savoir s'il a lu ou non."""
        return (self.parent_by_id or {}).get(uid)

    def parent_measured(self, uid) -> bool:
        """La mesure du lien parent a-t-elle eu lieu pour `uid` ? (`False` = hook anterieur a #378,
        capteur muet, ou unite absente du snapshot.) A ne PAS confondre avec `parent(uid) is None`,
        qui vaut aussi pour une unite mesuree SANS parent."""
        return uid in (self.parent_by_id or {})

    def prevents_overkill(self, uid) -> bool:
        """`UnitExtensions.HasFlag(uid, 0x13)` = `UnitFlag.PreventOverkill` (=19) — la cible ne peut
        PAS être overkillée (#195). Table renseignée → lecture du composant de flags (ECS offline
        via `from_state`, `combatSnapshot.unitFlags` live depuis O5) ; sinon REPLI sur la dérivation
        depuis les effets ACTIFS de l'unité (hook antérieur à O5)."""
        v = self.prevent_overkill_by_id.get(uid)
        if v is not None:
            return bool(v)
        if self.eff_state is None:
            return False
        return effects_prevent_overkill(self.effects(uid))

    def has_moved(self, uid) -> bool | None:
        """`UnitExtensions.HasFlag(uid, UnitFlag.Moved = 0)` — l'unité a-t-elle DÉJÀ bougé ce tour.
        TRI-ÉTAT : `None` = **non mesuré** (capteur `unitFlags` absent/`null`) -> l'appelant garde son
        repli, `[]` mesuré donne bien `False`. Confondre les deux ré-accorderait le +25% ranged
        d'`HeavyWeapon_ExtraDmg` en silence."""
        return self.moved_by_id.get(uid)

    def has_used_active_ability(self, uid) -> bool | None:
        """`UnitExtensions.HasFlag(uid, UnitFlag.ActiveAbilityUsed = 2)` — l'unite a-t-elle deja
        consomme son ACTION ce tour. Meme tri-etat que `has_moved` : `None` = capteur `unitFlags`
        non mesure -> l'appelant NE COUPE PAS (comportement anterieur), `[]` mesure donne `False`.

        Consommateur unique : `engine.ai.action_generators.ActiveAbilityActionGenerator.
        unit_action_gate`, mirror de la 1re instruction de
        `IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`."""
        return self.active_ability_used_by_id.get(uid)

    def tiles_moved_this_turn(self, uid) -> int | None:
        """`IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` =
        `ActorStatisticsComponent+0xf0` — nb de tuiles que l'unite a DEJA parcourues ce tour
        (case-322-r2). Pendant PREDICTION de `runner.components.unit_tiles_moved_this_turn`.

        TRI-ETAT, meme discipline que `has_moved` : `None` = **non mesure** (voie live, aucun capteur
        ne publie `+0xf0`) -> `prediction_tiles_moved_this_turn` garde le seul terme « pas simule »,
        soit le comportement strictement anterieur ; `0` mesure est un vrai zero. Confondre les deux
        ferait passer un capteur ABSENT pour « n'a pas bouge », et c'est exactement le sous-comptage
        que ce residu decrivait."""
        v = (self.tiles_moved_by_id or {}).get(uid)
        return None if v is None else int(v)

    def has_teleported(self, uid) -> bool | None:
        """`UnitExtensions.HasFlag(uid, UnitFlag.Teleported = 0xc)` — le déplacement de ce tour était
        un TÉLÉPORT, ce qui RÉ-AUTORISE le +25% (`... & (!HasFlag(Moved) | HasFlag(Teleported))`).
        Même tri-état que `has_moved`."""
        return self.teleported_by_id.get(uid)

    @classmethod
    def from_state(cls, state) -> "Scene":
        """Construit la Scene DIRECTEMENT depuis un `State` runner (offline, SANS RPC/combatSnapshot).

        C'est la moitié « prédiction » du bridge `State -> AiDecisionContext` (#65) : le `StatsComponent.ctx`
        d'une unité EST le même `UnitContext` que `build_predictor` cache (via `from_snapshot`) ; `State.effects`
        EST l'`EffectsState` seed ; `State.board` fournit élévation + adjacence hex. Donc `predictor`/`sctx`
        deviennent inutiles (le spine de décision ne lit QUE `ctx.scene`). Armure/bouclier = valeurs LIVE des
        composants (plus fidèle que le cold `refresh_shields` par-pas). Inclut les corpses (comme dv.units) ;
        les tables per-unité ne couvrent que les entités à `StatsComponent`."""
        ctx_by_id, armor_by_id, shield_by_id, mult_by_id, ablvl_by_id, vis_by_id = {}, {}, {}, {}, {}, {}
        hp_by_id, hpmax_by_id, pos_by_id, team_by_id = {}, {}, {}, {}
        defstat_by_id, charged_by_id, prevent_overkill_by_id = {}, {}, {}
        moved_by_id, teleported_by_id, active_ability_used_by_id = {}, {}, {}
        tiles_moved_by_id, parent_by_id = {}, {}
        turns_started_by_id, turns_finished_by_id = {}, {}
        received_damage_profiles_by_id: dict = {}
        units: list = []
        for eid, e in state.entities.items():
            uc = e.get_component(UnitComponent)
            sc = e.get_component(StatsComponent)
            oc = e.get_component(OwnerComponent)
            pc = e.get_component(PositionComponent)
            hc = e.get_component(HealthComponent)
            ec = e.get_component(EffectsOwnedComponent)
            shc = e.get_component(ShieldComponent)
            if uc is None:
                continue
            # MACHINES OF WAR exclues : la Scene mirroir `decisionView.units`, qui est
            # `EntityType.Unit`-only (le natif expose les MoW dans un canal SÉPARÉ `.mows`, et
            # `aiPlaybookPredict` a son propre chemin de résolution de caster Machine, case-172).
            # Depuis que `load_state` matérialise les MoW (débloqueur cast MoW), les faire entrer
            # ici les traiterait comme des unités sans position -> face DÉCISION inchangée.
            if is_machine_of_war(e):
                continue
            vis = uc.visual_id if uc else None
            pos = (pc.col, pc.row) if pc is not None else None
            if sc is not None:                                    # tables prédiction : entités à ctx
                ctx = sc.ctx
                ctx_by_id[eid] = ctx
                armor_by_id[eid] = int(ctx.fixed_armor)
                mult_by_id[eid] = int(ctx.ability_variables_multiplier or 100)
                ablvl_by_id[eid] = int(ctx.passive_ability_level or 0)
                # #197 : StatComponent DEFENSE (stat 3) de l'ECS live -> la prédiction OFFLINE (from_state)
                # folde le stat-mod defense (Thorns ×1.5) comme le COMBAT runner, MEME source (ctx.stats)
                # -> décision offline et combat cohérents. None si le stat n'est pas seedé (axe inerte).
                _ds = ctx.stats.components.get(int(_ST.DEFENSE)) if ctx.stats is not None else None
                if _ds is not None:
                    defstat_by_id[eid] = _ds
                # #46 : TurnsStarted (stat 12) du ctx ECS — le runner offline l'incremente au
                # StartTurn (mirror `StartTurnOperation IdunBattle.Operations.StartTurnOperation$$Execute`, `increment_base`).
                if ctx.stats is not None and int(_ST.TURNS_STARTED) in ctx.stats.components:
                    turns_started_by_id[eid] = ctx.stats.get_stat(int(_ST.TURNS_STARTED))
            shield_by_id[eid] = shc.get_total_shield() if shc is not None else 0
            # case-r32 : `UnitComponent.ChargedUnitIds@+0x190` tel que l'ECS le porte MAINTENANT.
            if getattr(uc, "charged_unit_ids", None):
                charged_by_id[eid] = {int(i) for i in uc.charged_unit_ids}
            # #195 : `HasFlag(u, 0x13)` LU de l'ECS (composant de flags d'abord, effet 1354 ensuite).
            prevent_overkill_by_id[eid] = unit_prevents_overkill(state, eid)
            # #266 : `HasFlag(u, Moved=0)` / `HasFlag(u, Teleported=0xc)` LUS de l'ECS. Le
            # `UnitFlagsComponent` est posé par `set_moved_flag` (voie offline) ET seedé depuis le
            # live par `snapshot._load_unit_flags` — donc renseigné dans les deux régimes.
            moved_by_id[eid] = unit_has_moved(state, eid)
            teleported_by_id[eid] = unit_has_teleported(state, eid)
            # #17 : `HasFlag(u, ActiveAbilityUsed=2)` — MEME composant, MEME regime de seed.
            active_ability_used_by_id[eid] = unit_has_used_active_ability(state, eid)
            # case-322-r2 : `ActorStatisticsComponent+0xf0` LU de l'ECS. Le compteur y est TENU par
            # `runner/operations/movement.py::MoveUnitOperation.execute` depuis #335 (c'est le runner
            # qui applique le deplacement) et remis a zero par `EndTurnOperation` — donc la face
            # DECISION offline lit exactement ce que la face COMBAT a ecrit, au lieu de le
            # reconstruire a zero. MEME forme que #267 (traits) et #266 (flag `Moved`) : une face qui
            # LIT ce que l'autre TIENT, jamais une seconde derivation.
            tiles_moved_by_id[eid] = unit_tiles_moved_this_turn(state, eid)
            # #378 : `ChildComponent.ParentId` LU de l'ECS. Le champ y est TENU par
            # `SpawnUnitOperation` (voie offline) ET seede depuis le live par
            # `snapshot._load_unit_parent` -- donc renseigne dans les deux regimes, comme le flag
            # `Moved` (#266). L'entite est INSCRITE meme quand elle n'a pas de parent : c'est une
            # mesure PLEINE (cf. `Scene.parent_measured`), pas une absence.
            parent_by_id[eid] = getattr(uc, "parent_id", None)
            # #27-r8 : `UnitComponent + 0x5c` LU de l'ECS. Le champ y est TENU par
            # `runner/turnflow.py::_bump_turns_finished` (mirror d'`EndTurnOperation$$Execute`, voie
            # offline) ET seede depuis le live par `snapshot.py` (#N11) -- meme forme que #266
            # (flag `Moved`) et #378 (`parent_id`) : la face DECISION LIT ce que la face COMBAT
            # TIENT, jamais une seconde derivation. L'entite est INSCRITE meme a 0 : c'est une
            # mesure PLEINE (le composant existe des que l'unite existe), pas une absence.
            turns_finished_by_id[eid] = int(getattr(uc, "turns_finished", 0) or 0)
            # #487-r1 : `ActorStatisticsComponent + 0x80` LU de l'ECS (les CLES du Dictionary, pas
            # les valeurs -- `HasTakenDamageOfDamageProfileThisTurn` = `ContainsKey`). Le compteur y
            # est TENU par `runner/operations/damage.py` et vide au boundary de phase par
            # `runner/operations/turnflow.py`. L'entite est INSCRITE meme avec un ensemble VIDE :
            # c'est une mesure PLEINE (le composant existe des que l'unite existe), pas une absence.
            received_damage_profiles_by_id[eid] = {
                int(p) for p in (getattr(uc, "received_damage_this_turn", None) or {})}
            vis_by_id[eid] = vis
            if hc is not None:
                hp_by_id[eid] = hc.hp
                hpmax_by_id[eid] = hc.hp_max
            if pos is not None:
                pos_by_id[eid] = pos
            if oc is not None:
                team_by_id[eid] = oc.team
            # `ctrl` = `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer` — le champ que
            # le hook publie sur la face LIVE (`dv.units[].ctrl`, methode native INVOQUEE). Ici on le
            # reconstitue depuis les DEUX memes lectures que le natif compare
            # (`OwnerComponent.CurrentPlayerEntityId` / `TurnComponent.CurrentPlayerId`). L'une des
            # deux manquante -> `None` (non mesure), et `Scene.is_turn_of` rendra `None`.
            _cur = getattr(state, "current_player_id", None)
            _ctrl = (None if (_cur is None or oc is None or oc.player is None)
                     else int(oc.player) == int(_cur))
            units.append({
                "id": eid, "visualId": vis, "alive": bool(uc.alive),
                "ctrl": _ctrl,
                "team": oc.team if oc is not None else None,
                "pos": {"col": pos[0], "row": pos[1]} if pos is not None else None,
                "hp": hc.hp if hc is not None else None,
                "effects": list(ec.effects) if ec is not None else [],  # noms bruts (EffectsOwnedComponent)
            })
        elev_by_pos = None
        board = state.board
        if board is not None:
            elev_by_pos = {(t.get("col"), t.get("row")): int(t.get("elevation") or 0)
                           for t in board.by_id.values()
                           if t.get("col") is not None and t.get("row") is not None}
        sc = cls(
            ctx_by_id=ctx_by_id, armor_by_id=armor_by_id, shield_by_id=shield_by_id,
            mult_by_id=mult_by_id, ablvl_by_id=ablvl_by_id, vis_by_id=vis_by_id,
            units=units, hp_by_id=hp_by_id, pos_by_id=pos_by_id, team_by_id=team_by_id,
            eff_state=getattr(state, "effects", None), hpmax_by_id=hpmax_by_id,
            elev_by_pos=elev_by_pos, board=board, defstat_by_id=defstat_by_id,
            turns_started_by_id=turns_started_by_id,
            turns_finished_by_id=turns_finished_by_id, charged_by_id=charged_by_id,
            prevent_overkill_by_id=prevent_overkill_by_id,
            moved_by_id=moved_by_id, teleported_by_id=teleported_by_id,
            active_ability_used_by_id=active_ability_used_by_id,
            tiles_moved_by_id=tiles_moved_by_id, parent_by_id=parent_by_id,
            # #1036-r2 -- cf. le champ `machine_ids`. Voie OFFLINE : la nature d'entite se lit
            # directement dans l'ECS (`components.is_machine_of_war`), sur TOUTES les entites --
            # y compris celles que la boucle ci-dessus a ecartees, qui sont precisement les MoW.
            machine_ids=frozenset(eid for eid, e in state.entities.items()
                                  if is_machine_of_war(e)),
            received_damage_profiles_by_id=received_damage_profiles_by_id)
        sc._seed_battle_counters()   # #185 (units offline sans defeatedByMelee -> N=0, inerte)
        return sc

    @classmethod
    def from_predictor_sctx(cls, predictor: dict, sctx: dict, elev_by_pos: dict | None = None,
                            board: object | None = None,
                            tile_effects_by_pos: dict | None = None,
                            machine_of_war_position: int | None = None) -> "Scene":
        """Bridge des dicts de l'ancien PV vers l'objet Scene (mêmes données, forme objet).
        `tile_effects_by_pos` = effets de tuile FRAIS du pas (tileMeta ; dynamique — la glace
        LordOfTempests s'accumule) ; None -> bonus position-dépendants inertes.
        `machine_of_war_position` = `GetPositionMachineForPlayer(joueur courant)` ; None = non mesure
        (le predicat `IsPositionMachineForCurrentPlayer` rend alors False)."""
        sc = cls(
            ctx_by_id=predictor.get("ctx_by_id") or {}, armor_by_id=predictor.get("armor_by_id") or {},
            shield_by_id=predictor.get("shield_by_id") or {}, mult_by_id=predictor.get("mult_by_id") or {},
            ablvl_by_id=predictor.get("ablvl_by_id") or {}, vis_by_id=predictor.get("vis_by_id") or {},
            units=sctx.get("units") or [], hp_by_id=sctx.get("hp_by_id") or {},
            pos_by_id=sctx.get("pos_by_id") or {}, team_by_id=sctx.get("team_by_id") or {},
            # #953-r1 -- `hpmax_by_id` etait STRUCTURELLEMENT VIDE sur cette voie : `step_context`
            # ne le produit pas, et il ne le PEUT pas -- `decisionView.units[]` ne publie aucune
            # cle de PV max (mesure : ses 17 cles sont `abilities, alive, ctrl, defeatedByMelee,
            # effects, feet, hasAction, hp, id, killerId, owner, parentId, parentMeasured, pos,
            # ranged, team, visualId`). `scene.hpmax` rendait donc `None` pour TOUTE unite sur la
            # voie PREDICTION-LIVE, alors que `Scene.from_state` (voie offline/combat) le remplit
            # depuis `HealthComponent.hp_max`. Fork de SUBSTRAT, pas de logique -- et SILENCIEUX,
            # parce que chaque consommateur degrade proprement sur `None`.
            #
            # La source est `predictor["hpmax_eff_by_id"]` = `combatSnapshot.healthMax` =
            # `GetStat(e, 5, part = Maximum)`, c.-a-d. exactement le `Maximum` que lit
            # `StatAmount(Owner@DSLSelectors+0x30, Health, {Missing, Maximum})` dans
            # `IdunBattle.Entities.Effects.Loki.Skullsmasher_ExtraDamageEffect$$GetMissingHealthSteps`
            # -- base + modifications, clampe. `observeBattle.hpMax` (base SEULE) serait le repli
            # historique, moins fidele : on ne le prend pas.
            #
            # MESURE (#953-r1, `worldJakhal` << Macer >> a 9 474 / 20 000 PV, build `rnca9r7q6c`) :
            # 5 paliers de `floor(52,63 % / hpPct = 10)` x `extraDmg = 300` = 1 500 par coup, soit
            # +4 500 sur une tuile a 3 coups et +3 000 sur une tuile a 2 coups. Le natif les
            # publiait, le port rendait EXACTEMENT la prediction du porteur INTACT sur les 5 tuiles
            # candidates. `sctx` reste prioritaire s'il porte un jour la cle.
            eff_state=sctx.get("eff_state"),
            hpmax_by_id=(sctx.get("hpmax_by_id") or predictor.get("hpmax_eff_by_id") or {}),
            feet_by_id=sctx.get("feet_by_id") or {},
            # #1036-r2 -- cf. le champ `machine_ids`. `sctx` le porte des que la Scene vient de
            # `step_context` (canal `decisionView.mows[].casterId`) ; ABSENT -> `None` = non mesure.
            machine_ids=sctx.get("machine_ids"),
            elev_by_pos=elev_by_pos if elev_by_pos is not None else predictor.get("elev_by_pos"),
            tile_effects_by_pos=tile_effects_by_pos,
            machine_of_war_position=machine_of_war_position,
            board=board if board is not None else predictor.get("board"),
            abstate_by_id=predictor.get("abstate_by_id") or {},
            trigstate_by_id=predictor.get("trigstate_by_id") or {},      # #1042-r1
            actorstats_by_id=predictor.get("actorstats_by_id") or {},
            defstat_by_id=predictor.get("defstat_by_id") or {},
            turns_started_by_id=predictor.get("turns_started_by_id") or {},
            turns_finished_by_id=predictor.get("turns_finished_by_id") or {},
            attack_cur_by_id=predictor.get("attack_cur_by_id") or {},
            extra_hits_cur_by_id=predictor.get("extra_hits_cur_by_id") or {},
            # O5 : flags d'unité LUS (`combatSnapshot.unitFlags`). Table vide = hook antérieur à
            # O5 -> l'accesseur retombe sur la dérivation par l'effet 1354, comportement d'avant.
            prevent_overkill_by_id=predictor.get("prevent_overkill_by_id") or {},
            # #266 : `Moved` / `Teleported` du MÊME canal. Table vide = uid absent -> l'accesseur
            # rend `None` (non mesuré) et `prediction_has_moved` garde le seul terme « tuile
            # simulée », donc le comportement strictement antérieur.
            moved_by_id=predictor.get("moved_by_id") or {},
            teleported_by_id=predictor.get("teleported_by_id") or {},
            # #17 : `ActiveAbilityUsed`, MEME canal et MEME tri-etat. Table vide -> l'accesseur rend
            # `None` (non mesure) et le gate du generateur reste OUVERT, comportement anterieur.
            active_ability_used_by_id=predictor.get("active_ability_used_by_id") or {},
            # case-322-r2 : `TilesMovedThisTurn` du capteur `actorStats`. Table vide = le hook ne
            # publie PAS `+0xf0` -> l'accesseur rend `None` (non mesure) et
            # `prediction_tiles_moved_this_turn` garde le seul terme « pas simule », comportement
            # strictement anterieur. Le cablage est pose ICI pour que la voie live se ferme au
            # prochain reinject sans retoucher au port.
            tiles_moved_by_id=predictor.get("tiles_moved_by_id") or {},
            # #378 : lien enfant -> summoner du capteur `combatSnapshot.parentId`. Table vide = le
            # hook ne publie PAS encore le champ -> `Scene.parent(uid)` rend `None` pour tout le
            # monde et le noeud `If(AmountIsGreaterThanZero(Parent(src)), Parent(src), src)`
            # retombe sur `src`, comportement STRICTEMENT anterieur. Le cablage est pose ICI pour
            # que la voie live se ferme au prochain reinject sans retoucher au port.
            parent_by_id=predictor.get("parent_by_id") or {})
        sc._seed_battle_counters()   # #185 BlessingsOfKhorne (melee-defeats -> effets N-scalés)
        return sc

    # ── Compteurs de bataille (#185) ───────────────────────────────────────────────────────────────
    def melee_defeats(self) -> int:
        """Compte de base de `IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee` = `Count(NormalUnits(
        UnitsDefeatedByMeleeAttack(AllUnits)))` : unités NORMALES (kind-1 — `dv.units` = squads hors
        MoW par construction, `IdunBattleLogic.Entities.DSLFactory$$NormalUnits` = `Units(set, kind=1)`) MORTES
        tuées par une attaque de MÊLÉE. Flag = `UnitComponent.DefeatedByMeleeAttack @0x178` (écrit
        par `KillUnitOperation IdunBattle.Operations.KillUnitOperation$$Execute`, capté #185 dans decisionView.units) ; `isDead` requis en
        mirror du sélecteur `IdunBattle.Entities.Selectors.UnitsDefeatedByMeleeAttackSelector$$IsValidUnit` (une unité RESSUSCITÉE ne compte plus). GLOBAL
        (les 2 camps, quel que soit le tueur). Units offline (`from_state`) sans le champ -> 0.

        ⚠ FOYER PARTAGE depuis #953 : le corps vit dans
        `engine.entities.effects_state.melee_defeats_from_units`, que la face COMBAT appelle AUSSI
        (`runner/snapshot.py::_load_battle_counters`). Elle ne le faisait PAS, et le port perdait
        alors tout le `+3 % x N` d'un World Eater sur un etat RECHARGE."""
        return _melee_defeats_from_units(self.units)

    def _seed_battle_counters(self) -> None:
        """Seed les effets dépendants d'un COMPTEUR DE BATAILLE — délègue au foyer PARTAGÉ
        `engine.entities.effects_state.seed_battle_counters` (#185, foyer depuis #953). Scene est
        reconstruite à chaque pas -> compte courant."""
        _seed_battle_counters(self.eff_state, self.units)

    # ── Accesseurs (mirror des lectures dict de PV) ────────────────────────────────────────────────
    def ctx(self, uid):
        return self.ctx_by_id.get(uid)

    def hp(self, uid):
        return self.hp_by_id.get(uid)

    def pos(self, uid):
        return self.pos_by_id.get(uid)

    def team(self, uid):
        return self.team_by_id.get(uid)

    def is_machine(self, uid) -> "bool | None":
        """#1036-r2 -- `IdunBattle.Entities.EntityExtensions$$IsMachine(entity)` = `<EntityType de
        l'entite> == 6`, face DECISION. Pendant exact de `components.is_machine_of_war` cote
        COMBAT (la presence d'un `MachineComponent`).

        TRI-ETAT : `None` = canal NON MESURE (`machine_ids` absent, Scene batie hors
        `step_context`) -- jamais `False`, qui affirmerait << ce n'est pas une machine >> sans
        l'avoir mesure et ouvrirait la branche `ifFalse` du `ConditionalSelector` de
        `CabalOfSorcerers_ExtraDamagePctEffect`."""
        if self.machine_ids is None:
            return None
        return uid in self.machine_ids

    def is_turn_of(self, uid) -> "bool | None":
        """`IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger$$ShouldTrigger` pour un selecteur
        SINGLETON = `OwnerComponent.CurrentPlayerEntityId(unit) == TurnComponent.CurrentPlayerId`,
        c'est-a-dire mot pour mot `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`.

        Face DECISION du canal `att_ctx["is_turn_of_owner"]` (cf. `entities/effects/base.py::
        is_turn_of_owner`) : on LIT `decisionView.units[].ctrl`, que le hook obtient en INVOQUANT la
        methode native (`ai-step/projection.ts`, `isCtrlByCurMi`) -- pas une derivation
        equipe-vs-equipe. `Scene.from_state` pose la MEME cle depuis l'ECS
        (`OwnerComponent.player == State.current_player_id`).

        `None` = non mesure (ligne d'unite absente, ou champ absent d'un flux anterieur) -> le gate
        consommateur se TAIT."""
        for u in (self.units or ()):
            if u.get("id") == uid:
                v = u.get("ctrl")
                return None if v is None else bool(v)
        return None

    def armor(self, uid) -> int:
        return self.armor_by_id.get(uid, 0)

    def shield(self, uid) -> int:
        return self.shield_by_id.get(uid, 0)

    def mult(self, uid) -> int:
        return self.mult_by_id.get(uid, 100)

    def hpmax(self, uid):
        return self.hpmax_by_id.get(uid)

    def _enemy_psykers_alive(self, uid):
        """`Enemies( Owner, UnitsWithTrait(AllUnits, 0x3ea = 1002 Psyker, 3) )` — face PRÉDICTION du
        MÊME sélecteur que `runner.components.enemy_psykers_alive` (un nœud natif, deux substrats :
        l'ECS côté runner, les tables de Scene ici). None si l'équipe du porteur est inconnue ⇒ clé
        ABSENTE du `unit_state` ⇒ prédicat dégradé en VRAI (`_enemy_psyker_on_battlefield`)."""
        team = self.team_by_id.get(uid)
        if team is None:
            return None
        if team in self._psykers_by_team:
            return self._psykers_by_team[team]
        n = 0
        for u in (self.units or ()):
            oid = u.get("id")
            if u.get("team") == team or not u.get("alive"):     # Enemies(owner, …) + vivantes
                continue
            c = self.ctx_by_id.get(oid)
            if c is not None and "Psyker" in (getattr(c, "traits", None) or ()):
                n += 1
        self._psykers_by_team[team] = n
        return n

    def adjacent_taunted_enemies(self, uid) -> "int | None":
        """`Count( Filter( AdjacentEnemies(Owner, unique: 1, selectionType: 3),
                           HasEffect(It, 27 Taunted_OnlySpecificTargets, onlyActive: 0, 6) ) )` --
        face PREDICTION du MEME selecteur que `runner.components.adjacent_taunted_enemies_count`
        (un noeud natif, deux substrats : l'ECS cote runner, les tables de `Scene` ici, #911).

        C'est `IdunBattle.Entities.Effects.Loki.ADaemonicPatronsEffect$$GetNumAdjacentTauntedEnemies`,
        la base commune des deux effets de `1203 DaemonicPatrons` : il sert la
        `CreateActiveCondition` ET les deux magnitudes, donc la face DECISION doit le voir sous peine
        de sous-predire le degat d'Hascule de `extraDmg x n`.

        ⚠ Le substrat impose de recomposer le selecteur ici (`Scene` n'a pas d'`AbilityEntities`
        pour executer l'arbre) -- MEME regime que `_enemy_psykers_alive` et `_camo_cloak_cover_keys`
        ci-dessus, qui sont les deux precedents de cette forme.
        `HasEffect(..., onlyActive: 0)` -> `EffectsState.has_effect`, PAS `active_effects` (le natif
        ne filtre pas sur `IsActive`, et `active_effects` reboucle sur `is_active`).

        ⚠ `AdjacentEnemies` descend sur `AdjacentTiles` -> `TileQuery$$IterateAdjacentTiles`, donc
        sur la liste STOCKEE puis la porte `|dElev| < 2` -- PAS sur la couronne hex (#943-r7). Le
        cablage sur `adjacency.unit_in_adjacent_tiles` (le foyer PARTAGE, #954) **RESORBE** une
        divergence de faces au lieu d'en creer : la face COMBAT
        (`runner.components.adjacent_taunted_enemies_count`) execute l'arbre
        `daemonic_patrons.adjacent_taunted_enemies_selector`, dont l'etage `AdjacentEnemies` passe
        par `dsl/base._within(order='adjacent')` -> `_adjacent_tiles_native` -- elle lit donc DEJA
        la liste stockee. Canaux tri-etat : absents -> degradation SEULE en couronne hex, c.-a-d.
        exactement le comportement d'avant.

        `None` (equipe ou position du porteur inconnue) => cle ABSENTE => condition degradee en VRAI
        et magnitude inerte -- jamais un 0 invente."""
        team = self.team_by_id.get(uid)
        here = self.pos(uid)
        if team is None or here is None:
            return None
        eff = getattr(self, "eff_state", None)
        elev, neigh = self.elev_by_pos, self.neigh_by_pos
        n = 0
        for u in (self.units or ()):
            oid = u.get("id")
            if oid == uid or u.get("team") == team or not u.get("alive"):   # AdjacentEnemies(Owner)
                continue
            if not _adj.unit_in_adjacent_tiles(self, uid, oid, elev, neigh):
                continue
            if eff is not None and eff.has_effect(
                    int(oid), int(EffectType.Taunted_OnlySpecificTargets)):   # 0x1b = 27
                n += 1
        return n

    def adjacent_dark_angels_friends(self, uid) -> "int | None":
        """`Count( UnitsFromFaction( AdjacentFriends(Owner, unique: 1, selectionType: 3),
        UnitFaction.DarkAngels = 0xa, selectionType: 3 ) )` -- face PREDICTION du MEME selecteur que
        `runner.components.adjacent_dark_angels_friends_count` (un noeud natif, deux substrats :
        l'ECS cote runner, les tables de `Scene` ici, #932).

        C'est le SECOND disjoint de `IdunBattle.Entities.Effects.Loki.DeathwingEffect$$
        GetDoubleEffectCondition`, appele par les DEUX faces de degat de l'effet (`isDefense` ne
        change QUE l'entite comparee du premier disjoint, jamais ce compteur) : la face DECISION doit
        le voir sous peine de sous-predire de MOITIE le degat de Baraqiel.

        ⚠ Le substrat impose de recomposer le selecteur ici (`Scene` n'a pas d'`AbilityEntities`
        pour executer l'arbre) -- MEME regime que `adjacent_taunted_enemies` juste au-dessus, dont
        cette methode est le decalque a trois differences LUES : le camp est AMI (et non ennemi),
        le porteur ne se compte PAS lui-meme (`op_Subtraction` d'`AdjacentFriends`), et le filtre
        porte sur la FACTION gameconfig, pas sur un effet.

        ⚠ EVALUE A LA POSITION COURANTE, pas a la TUILE CANDIDATE -- meme contraste assume que
        `adjacent_taunted_enemies` : un plan qui DEPLACE Baraqiel loin de ses freres predit encore
        le doublement. Residu NOMME ; la face COMBAT, elle, mesure la position REELLE au coup.

        ⚠ MEME cablage que `adjacent_taunted_enemies` ci-dessus, et pour la MEME raison (#943-r7) :
        `AdjacentFriends(unit, unique, sel)` = `Friends(unit, Units(AdjacentTiles(unit)) - unit,
        sel)`, donc la liste STOCKEE puis la porte `|dElev| < 2`. La face COMBAT
        (`runner.components.adjacent_dark_angels_friends_count`) execute l'arbre
        `deathwing.adjacent_dark_angels_friends_selector`, dont l'`AdjacentFriends` passe par
        `_within(order='adjacent')` : elle lit DEJA la liste stockee, le cablage RESORBE.

        `None` (equipe ou position du porteur inconnue) => cle ABSENTE => disjoint FERME cote effet
        (degradation RESTRICTIVE) -- jamais un 0 invente."""
        team = self.team_by_id.get(uid)
        here = self.pos(uid)
        if team is None or here is None:
            return None
        elev, neigh = self.elev_by_pos, self.neigh_by_pos
        n = 0
        for u in (self.units or ()):
            oid = u.get("id")
            if oid == uid or u.get("team") != team or not u.get("alive"):   # AdjacentFriends(Owner)
                continue
            if not _adj.unit_in_adjacent_tiles(self, uid, oid, elev, neigh):
                continue
            # `UnitsFromFaction(..., UnitFaction.DarkAngels, 3)` : le natif compare le NOM de la
            # valeur d'enum au `FactionComponent+0x30` ; offline, c'est le `FactionId` gameconfig.
            if (GC.unit(self.vis_by_id.get(oid)) or {}).get("FactionId") == _DARK_ANGELS:
                n += 1
        return n

    def synaptic_insight_adjacent_tyranid(self, owner_uid, target_uid) -> "bool | None":
        """`Any( AdjacentFriends(unit = Owner@<DSLSelectors+0x30>, unitTile = Target@<DSLSelectors
        +0x60>, unique: true), HasFaction(It@<DSLSelectors+0x68>, UnitFaction.Tyranids = 0xc, 3) )`
        -- face PREDICTION du MEME arbre que `runner.components.synaptic_insight_adjacent_tyranid`
        (un noeud natif, deux substrats : l'ECS cote runner, les tables de `Scene` ici, #1073).

        C'est le PREMIER disjoint de `IdunBattle.Entities.Effects.Loki.SynapticInsight_ExtraHits
        Effect$$CreateEffectHitsBonusForAttack` -- la face DECISION doit le voir sous peine de
        SOUS-PREDIRE de 2 coups chaque attaque a distance du porteur.

        ⚠ **L'ANCRE GEOMETRIQUE EST LA CIBLE DU COUP**, la REFERENCE D'EQUIPE est le PORTEUR : c'est
        la variante B d'`AdjacentFriends` (`unit`, `unitTile`, `unique`), tranchee par la CIBLE du
        `call rel32` du corps natif. Elle ancre donc a l'oppose d'`adjacent_dark_angels_friends`
        ci-dessus, dont les deux roles coincident sur le porteur.

        ⚠ Le PORTEUR n'est PAS exclu de l'ensemble : le natif ne soustrait que `unitTile` (la cible),
        et `Friends` n'ecarte pas l'egalite. Un porteur Tyranide adjacent a sa propre cible arme donc
        le disjoint tout seul -- LU dans `DSLSelectors$$AdjacentFriends` (variante B), pas deduit.

        ⚠ Le substrat impose de recomposer le selecteur ici (`Scene` n'a pas d'`AbilityEntities` pour
        executer l'arbre) -- MEME regime qu'`adjacent_dark_angels_friends` juste au-dessus, et MEME
        cablage d'adjacence (`playbook.adjacency`, donc la liste STOCKEE puis la porte `|dElev| < 2`).

        `None` (equipe du porteur ou position de la cible inconnue) => cle a `None` => disjoint FERME
        cote effet (degradation RESTRICTIVE) -- jamais un `False` invente."""
        oteam = self.team_by_id.get(owner_uid)
        if oteam is None or target_uid is None or self.pos(target_uid) is None:
            return None
        elev, neigh = self.elev_by_pos, self.neigh_by_pos
        for u in (self.units or ()):
            oid = u.get("id")
            # `op_Subtraction(Units(AdjacentTiles(unitTile), ...), unitTile)` = la CIBLE, et elle
            # seule, est retiree. Le porteur, lui, reste dans l'ensemble (cf. l'avertissement).
            if oid == target_uid or u.get("team") != oteam or not u.get("alive"):
                continue
            if not _adj.unit_in_adjacent_tiles(self, target_uid, oid, elev, neigh):
                continue
            # `HasFaction(It, UnitFaction.Tyranids, 3)` : le natif compare le NOM de la valeur d'enum
            # au `FactionComponent+0x30` ; offline, c'est le `FactionId` gameconfig.
            if (GC.unit(self.vis_by_id.get(oid)) or {}).get("FactionId") == _TYRANIDS:
                return True
        return False

    def _enmity_adjacent(self, uid, *, dark_angels_friends_only: bool,
                         at_pos=None) -> "int | None":
        """Les DEUX compteurs d'`EnmityForTheUnworthy` (#948) -- face PREDICTION des MEMES arbres que
        `runner.components.enmity_adjacent_units_count` /
        `..enmity_adjacent_dark_angels_friends_count` (un noeud natif, deux substrats : l'ECS cote
        runner, les tables de `Scene` ici) :

            `..._ExtraDamagePctEffect$$AdjacentUnitsAmount` =
                Count( NonSteppableOrObjectUnits( AdjacentUnits(Owner, 1, 3), 3 ) )
            `..._ExtraDamageEffect$$AdjacentFriendlyDarkaUnitsAmount` =
                Count( NonSteppableOrObjectUnits(
                           UnitsFromFaction(AdjacentFriends(Owner, 1, 3), DarkAngels, 3), 3 ) )

        Les deux arbres ne different que par `dark_angels_friends_only` : filtre d'EQUIPE + de
        FACTION quand il est vrai, AUCUN filtre quand il est faux (le natif compte alors les amis ET
        les ennemis). Le porteur ne se compte JAMAIS lui-meme (`op_Subtraction` present dans les
        deux).

        ⚠ L'etage `NonSteppableOrObjectUnits` (retirer `UnitTrait.Steppable` 0x1b et
        `UnitTrait.Object` 0xd) est PROPRE a Enmity -- c'est ce qui l'empeche de reutiliser
        `adjacent_dark_angels_friends` (#932, Deathwing), qui s'arrete a `UnitsFromFaction`.

        ⚠ Le substrat impose de recomposer le selecteur ici (`Scene` n'a pas d'`AbilityEntities`
        pour executer l'arbre) -- MEME regime qu'`adjacent_taunted_enemies` /
        `adjacent_dark_angels_friends` ci-dessus.

        ⚠ EVALUE A LA TUILE CANDIDATE quand l'appelant la threade (`at_pos`), a la position
        COURANTE sinon. #948-r1 a TRANCHE ce que le residu laissait ouvert, par LECTURE :
        `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile` DEPLACE
        REELLEMENT l'unite (slot du processor) avant d'executer l'action de prediction, appelle
        `$$SimulateMoveUnitTriggers` puis `$$RefreshSimulatedEffects`, PUIS invoque l'action, et
        restaure ensuite. `AdjacentUnits(Owner)` -> `EntityExtensions$$IterateTiles(owner)` lit
        donc la tuile CANDIDATE, l'entite y ayant ete posee dans l'etat simule. Le contraste que
        les deux voisins (#911, #932) assument encore n'est donc pas un choix : c'est le meme
        gisement, non ferme pour eux.

        ⚠ MEME cablage que ses deux voisins (#943-r7), sur le foyer partage `playbook.adjacency` : `AdjacentUnits(Owner, 1, 3)` =
        `Units(AdjacentTiles(Owner)) - Owner`, donc la liste STOCKEE puis `|dElev| < 2`. Les DEUX
        faces COMBAT (`runner.components.enmity_adjacent_units_count` et
        `..._dark_angels_friends_count`) executent les arbres d'`enmity_for_the_unworthy`, dont
        l'etage `AdjacentUnits`/`AdjacentFriends` passe par `_within(order='adjacent')` : elles
        lisent DEJA la liste stockee, le cablage RESORBE.

        `None` (position -- et pour la face DA, equipe -- du porteur inconnue) => cle ABSENTE =>
        aucune contribution cote effet (degradation RESTRICTIVE) -- jamais un 0 invente."""
        here = self.pos(uid)
        team = self.team_by_id.get(uid)
        if here is None or (dark_angels_friends_only and team is None):
            return None
        elev, neigh = self.elev_by_pos, self.neigh_by_pos
        # Pieds du porteur REPOSITIONNES sur la tuile candidate (#948-r1). `None` = pieds reels,
        # soit parce qu'aucune tuile n'est threadee, soit parce que le porteur est MULTI-TUILES
        # (degradation nommee dans `subject_tiles_at`).
        sujet = _adj.subject_tiles_at(self, uid, at_pos)
        n = 0
        for u in (self.units or ()):
            oid = u.get("id")
            if oid == uid or not u.get("alive"):        # op_Subtraction(<ring>, origin)
                continue
            if dark_angels_friends_only and u.get("team") != team:   # AdjacentFriends(Owner)
                continue
            if not _adj.unit_in_adjacent_tiles(self, uid, oid, elev, neigh, sujet):
                continue
            if dark_angels_friends_only and \
                    (GC.unit(self.vis_by_id.get(oid)) or {}).get("FactionId") != _DARK_ANGELS:
                continue                               # UnitsFromFaction(..., DarkAngels, 3)
            # `NonSteppableOrObjectUnits(..., 3)`. ⚠ `Scene` n'a PAS de methode `traits` -- ce nom
            # n'existe que sur `_SceneEffectTargetWorld` (la vue passee aux effets), et l'appeler
            # ici levait `AttributeError` DES QU'UNE unite vivante etait hex-adjacente au porteur
            # (rouge de `master` introduit par #947+#948, latent parce que la boucle sort AVANT sur
            # un board ou personne n'est au contact). Le canal est le meme des deux cotes :
            # `ctx_by_id[<uid>].traits`, deja publie en NOMS (`trait_names_from_ids`).
            c = self.ctx(oid)
            tr = (getattr(c, "traits", None) or ()) if c is not None else ()
            if _TRAIT_STEPPABLE in tr or _TRAIT_OBJECT in tr:
                continue
            n += 1
        return n

    def hunter_of_souls_adjacent_psyker_friends(self, uid, at_pos=None) -> "int | None":
        """`Count( UnitsWithTrait( AdjacentFriends(Owner@<DSLSelectors+0x30>, unique: 1, 3),
        UnitTrait.Psyker = 0x3ea, 3 ) )` -- `IdunBattle.Entities.Effects.Loki.
        HunterOfSouls_ExtraDamageEffect$$GetUnits`, face PREDICTION du MEME arbre que
        `runner.components.hunter_of_souls_adjacent_psyker_friends_count` (#1078-r3).

        ⚠ CE N'EST PAS `_enmity_adjacent` : ce compteur filtre par TRAIT (pas par FACTION) et n'a
        AUCUN etage `NonSteppableOrObjectUnits` -- les deux absences sont LUES au decompile. Un ami
        Psyker `Steppable` ou `Object` est COMPTE ici et ECARTE chez Enmity.

        `at_pos` = la TUILE CANDIDATE du plan (meme lecture que `_enmity_adjacent`, #948-r1 :
        `IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile` DEPLACE
        reellement l'unite avant d'invoquer l'action de prediction). Absente -> position courante.

        `None` (equipe ou position du porteur inconnue) => cle ABSENTE => aucune contribution cote
        effet (degradation RESTRICTIVE) -- jamais un 0 invente."""
        here = self.pos(uid)
        team = self.team_by_id.get(uid)
        if here is None or team is None:
            return None
        elev, neigh = self.elev_by_pos, self.neigh_by_pos
        sujet = _adj.subject_tiles_at(self, uid, at_pos)
        n = 0
        for u in (self.units or ()):
            oid = u.get("id")
            if oid == uid or not u.get("alive"):        # op_Subtraction(<ring>, origin)
                continue
            if u.get("team") != team:                   # AdjacentFriends(Owner)
                continue
            if not _adj.unit_in_adjacent_tiles(self, uid, oid, elev, neigh, sujet):
                continue
            c = self.ctx(oid)                           # UnitsWithTrait(..., Psyker, 3)
            tr = (getattr(c, "traits", None) or ()) if c is not None else ()
            if _TRAIT_PSYKER not in tr:
                continue
            n += 1
        return n

    def enmity_adjacent_units(self, uid, at_pos=None) -> "int | None":
        """`..._ExtraDamagePctEffect$$AdjacentUnitsAmount` -- cf. `_enmity_adjacent`.

        `at_pos` = la TUILE CANDIDATE du plan (#948-r1). Absente -> position courante."""
        return self._enmity_adjacent(uid, dark_angels_friends_only=False, at_pos=at_pos)

    def enmity_adjacent_dark_angels_friends(self, uid, at_pos=None) -> "int | None":
        """`..._ExtraDamageEffect$$AdjacentFriendlyDarkaUnitsAmount` -- cf. `_enmity_adjacent`.

        `at_pos` = la TUILE CANDIDATE du plan (#948-r1). Absente -> position courante."""
        return self._enmity_adjacent(uid, dark_angels_friends_only=True, at_pos=at_pos)

    def close_combat_weakness_adjacent_enemies(self, uid, at_pos=None) -> "int | None":
        """`IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies(unit, unitTile,
        includeObjects: false, includeSteppables: false)` SANS son etage terminal
        `AmountIsEqualOrGreater(..., Direct(1))` -- face PREDICTION du MEME arbre que
        `runner.components.close_combat_weakness_adjacent_enemies_count` (un noeud natif, deux
        substrats : l'ECS cote runner, les tables de `Scene` ici). #1015-r1.

            Count( UnitsWithoutTrait( UnitsWithoutTrait(
                       Enemies(of: unit, AdjacentUnits(unitTile, unique: 1, 3), 3),
                       Object = 0xd, 3), Steppable = 0x1b, 3) )

        ⚠ EVALUE A LA TUILE CANDIDATE quand l'appelant la threade (`at_pos`) : meme lecture que
        `_enmity_adjacent` (#948-r1) -- `IdunBattle.Operations.SimulateEffectsOperation$$
        DoActionInSimulatedTile` DEPLACE reellement l'unite avant d'invoquer l'action de prediction,
        donc `AdjacentUnits(CasterTile)` descend sur la tuile SIMULEE.

        `None` (equipe ou position du porteur inconnue) => cle ABSENTE => le gate se FERME cote
        effet (degradation RESTRICTIVE) -- jamais un 0 invente, qui ferait passer un malus reel pour
        son absence."""
        team = self.team_by_id.get(uid)
        here = self.pos(uid)
        if team is None or here is None:
            return None
        elev, neigh = self.elev_by_pos, self.neigh_by_pos
        sujet = _adj.subject_tiles_at(self, uid, at_pos)
        n = 0
        for u in (self.units or ()):
            oid = u.get("id")
            if oid is None or oid == uid or u.get("team") == team:   # `Enemies(of = unit, ...)`
                continue
            if not _adj.unit_matches(self, u):                       # `selectionType = 3`
                continue
            if not _adj.unit_in_adjacent_tiles(self, uid, oid, elev, neigh, sujet):
                continue
            # `UnitsWithoutTrait(..., Object = 0xd, 3)` puis `UnitsWithoutTrait(..., Steppable =
            # 0x1b, 3)`. MEME canal que `_enmity_adjacent` : `ctx_by_id[<uid>].traits`, en NOMS.
            c = self.ctx(oid)
            tr = (getattr(c, "traits", None) or ()) if c is not None else ()
            if _TRAIT_STEPPABLE in tr or _TRAIT_OBJECT in tr:
                continue
            n += 1
        return n

    def adjacent_enemy_ids(self, uid) -> "frozenset | None":
        """`AdjacentEnemies( Owner@DSLSelectors+0x30, unique: true,
        UnitSelectionType.OnlyAliveAndTargetable = 3 )` -- face PREDICTION du `CreateTargetSelector`
        PARTAGE des deux effets d'`ObsessiveAnnunciation` (#954), dont la face COMBAT est
        `runner.components.adjacent_enemy_ids` (un noeud natif, deux substrats).

        Rend les IDS et non un cardinal : les deux canaux qui le consomment interrogent une
        APPARTENANCE (`get_OwnerIsTarget` = << la cible du coup est-elle l'une des cibles de
        l'effet ? >>), la boucle native ecrivant `AbilityEntities+0x18 (Owner) <- CHAQUE CIBLE`.

        L'adjacence passe par le foyer PARTAGE `playbook/adjacency.py` (#419-r1-tr10) et non par
        `hexgeo.distance == 1` : `unit_in_adjacent_tiles` lit la LISTE STOCKEE **avec** la porte
        d'elevation de `TileQuery.IterateAdjacentTiles`, et couvre les entites MULTI-TUILES des deux
        cotes -- c'est le MEME substrat que la face COMBAT, donc les deux faces ne peuvent pas
        diverger sur la geometrie. `unit_matches` porte le `selectionType 3`
        (`UnitExtensions$$MatchesUnitSelectionType` = vivante **et** ciblable).

        `None` (equipe ou position du porteur inconnue) => cle ABSENTE => le gate se FERME cote
        effet (degradation RESTRICTIVE), jamais un ensemble VIDE invente."""
        team = self.team_by_id.get(uid)
        if team is None or self.pos(uid) is None:
            return None
        neigh = None
        out = set()
        for u in (self.units or ()):
            oid = u.get("id")
            if oid is None or oid == uid or u.get("team") == team:   # `Enemies(...)`
                continue
            if not _adj.unit_matches(self, u):                       # `selectionType = 3`
                continue
            if neigh is None:
                neigh = _bq.neigh_map(self)
            if _adj.unit_in_adjacent_tiles(self, uid, oid, self.elev_by_pos, neigh):
                out.add(int(oid))
        return frozenset(out)

    def adjacent_unit_ids(self, uid) -> "frozenset | None":
        """`AdjacentUnits( <uid>, unique: true, UnitSelectionType.OnlyAliveAndTargetable = 3 )` --
        face PREDICTION du noeud d'adjacence partage par les DEUX branches du
        `$$CreateTargetSelector` de `MoreGitzOverEre_ExtraDamagePctEffect` (#1025-r1), dont la face
        COMBAT est `runner.components.adjacent_unit_ids` (un noeud natif, deux substrats).

        Voisin exact d'`adjacent_enemy_ids` ci-dessus, MOINS le filtre d'equipe : `AdjacentUnits`
        n'en porte AUCUN (`op_Subtraction(Units(AdjacentTiles(origin), unique, sel), origin)`), et
        le `Friends(Owner, ...)` que le natif applique ensuite depend du PORTEUR de l'effet -- il
        est donc rejoue par la classe d'effet, qui seule connait `owner_team`.

        L'adjacence passe par le foyer PARTAGE `playbook/adjacency.py` (#419-r1-tr10) et non par
        `hexgeo.distance == 1` : `unit_in_adjacent_tiles` lit la LISTE STOCKEE **avec** la porte
        d'elevation de `TileQuery.IterateAdjacentTiles`, et couvre les entites MULTI-TUILES des
        deux cotes -- MEME substrat que la face COMBAT. `unit_matches` porte le `selectionType 3`.

        `None` (equipe ou position du sujet inconnue) => cle ABSENTE => le gate se FERME cote
        effet, jamais un ensemble VIDE invente."""
        if self.team_by_id.get(uid) is None or self.pos(uid) is None:
            return None
        neigh = None
        out = set()
        for u in (self.units or ()):
            oid = u.get("id")
            if oid is None or oid == uid:                            # op_Subtraction(..., origin)
                continue
            if not _adj.unit_matches(self, u):                       # `selectionType = 3`
                continue
            if neigh is None:
                neigh = _bq.neigh_map(self)
            if _adj.unit_in_adjacent_tiles(self, uid, oid, self.elev_by_pos, neigh):
                out.add(int(oid))
        return frozenset(out)

    def _camo_cloak_cover_keys(self, uid, out: dict) -> None:
        """Les DEUX membres du `op_BitwiseOr` de `IdunBattle.Entities.Effects.Loki.
        CamoCloak_DmgReductionEffect$$HasValidEffectTrigger` — face PRÉDICTION des mêmes nœuds que
        `runner.components.has_effect_of_type` / `..is_target_of_adjacent_friend_aura` (un nœud
        natif, deux substrats : l'ECS côté runner, les tables de `Scene` ici).

        `HasEffect(sel, 1013 LightCover, onlyActive=0, 6)` -> `EffectsState.has_effect` (le natif ne
        filtre PAS sur `IsActive`, et `active_effects` reboucle sur `is_active`).
        `IsEffectTarget(sel, 1026 BigTarget_Adjacent)` -> même sélecteur que
        `BigTargetAdjacentEffect.create_aura_hits_malus_for_defense` : amis ADJACENTS, porteur
        EXCLU. Clé OMISE quand le substrat manque (pas d'`EffectsState` / pas de position) ⇒
        `camo_cloak_cover` dégrade en VRAI, jamais en FAUX.

        ⚠ CE SITE RECOMPOSE `_adjacent_friends`, ET IL DOIT LIRE LE MEME SUBSTRAT QUE LUI (#943-r7).
        `AdjacentFriends` descend sur `TileQuery$$IterateAdjacentTiles` (liste STOCKEE + porte
        `|dElev| < 2`), pas sur la couronne hex. Sa face COMBAT
        (`runner.components.is_target_of_adjacent_friend_aura` -> `is_effect_target` ->
        `entities.effect_targets._adjacent_friends`) est cablee DANS LE MEME COMMIT : les deux
        expressions du meme selecteur natif bougent ENSEMBLE, jamais l'une sans l'autre."""
        if self.eff_state is None:
            return
        out["has_effect_light_cover"] = bool(
            self.eff_state.has_effect(uid, int(EffectType.LightCover)))
        me, team = self.pos_by_id.get(uid), self.team_by_id.get(uid)
        if not me or team is None:
            return
        elev, neigh = self.elev_by_pos, self.neigh_by_pos
        hit = False
        for u in (self.units or ()):
            oid = u.get("id")
            if oid == uid or u.get("team") != team or not u.get("alive"):
                continue
            if not _adj.unit_in_adjacent_tiles(self, uid, oid, elev, neigh):
                continue
            if self.eff_state.has_effect(oid, int(EffectType.BigTarget_AdjacentEffect)):
                hit = True
                break
        out["is_target_of_big_target_adjacent"] = hit

    def is_effect_target(self, uid, effect_type) -> "bool | None":
        """`IdunBattleLogic.Entities.DSLTriggers$$IsEffectTarget(sel, effectType)`, face DÉCISION.

        Même foyer que la face COMBAT (`runner.components.is_effect_target`) : un nœud natif, deux
        substrats — l'ECS côté runner, les tables de `Scene` ici. `None` = géométrie non portée pour
        ce type, ou substrat manquant ⇒ l'appelant dégrade explicitement."""
        if self.eff_state is None or self.pos_by_id.get(uid) is None \
                or self.team_by_id.get(uid) is None:
            return None
        return _iet(_SceneEffectTargetWorld(self), int(uid), int(effect_type))

    def unit_state(self, uid) -> dict:
        """`unit_state` COMPLET de l'unité — le contexte d'évaluation des `CreateActiveCondition`
        (`BaseEffect.is_active`), pendant PRÉDICTION de `runner.components.unit_state_for_effects`.
        MÊMES clés, MÊME sémantique d'absence (clé manquante = donnée inconnue ⇒ dégradation fidèle
        propre à chaque condition). Sans `traits`, une condition de TRAIT (`PinnedEffect` =
        `Not(HasTrait(TerminatorArmour))`) rendrait VRAI et l'effet contribuerait à tort (#208)."""
        out: dict = {"hp": self.hp_by_id.get(uid)}
        mx = self.hpmax_by_id.get(uid)
        if mx is not None:
            out["max_hp"] = mx
        c = self.ctx_by_id.get(uid)
        traits = (getattr(c, "traits", None) or []) if c is not None else []
        if traits:
            out["traits"] = traits
        n = self._enemy_psykers_alive(uid)
        if n is not None:
            out["enemy_psykers_alive"] = n
        # `IsTurnOf(Owner)` (`<DSLTriggers+0x28>`) — face DECISION de la MEME cle que
        # `runner.components.UnitEffectStateView`, servie par `Scene.is_turn_of` (qui LIT
        # `decisionView.units[].ctrl`, ou le hook INVOQUE la methode native). Lue par
        # `MartialSuperiority_VisualEffect$$CreateActiveCondition` (`1255`, case-366-r1). `None` =
        # non mesure -> cle OMISE, la condition degrade en VRAI (jamais une valeur devinee).
        t = self.is_turn_of(uid)
        if t is not None:
            out["is_turn_of_owner"] = bool(t)
        self._camo_cloak_cover_keys(uid, out)     # `1014 CamoCloak_DmgReduction` (case-366-r1)
        # `RoundsStarted(Owner)` = `GetStat(., 0xc = TURNS_STARTED)` — lu par
        # `IdunBattle.Entities.Effects.Loki.ReinforcedHiveNode_ExtraArmorEffect$$CreateActiveCondition`
        # (`AmountIsOdd(Sum(RoundsStarted(Owner), Direct(1)))`, case-366-r1). Le compteur est DÉJÀ
        # matérialisé côté Scene (`turns_started_by_id`, #46) : la clé n'est présente que si le ctx
        # de l'entité le portait (absence = donnée inconnue ⇒ dégradation VRAI, comme le pendant
        # runner `UnitEffectStateView`).
        ts = (self.turns_started_by_id or {}).get(uid)
        if ts is not None:
            out["turns_started"] = int(ts)
        # `GetNumAdjacentTauntedEnemies()` (#911) — lue par
        # `IdunBattle.Entities.Effects.Loki.ADaemonicPatronsEffect$$CreateActiveCondition`
        # (`AmountIsGreaterThanZero(.)`), la base des deux effets de `1203 DaemonicPatrons`. `None` =
        # non mesure -> cle OMISE, la condition degrade en VRAI (jamais une valeur devinee).
        adt = self.adjacent_taunted_enemies(uid)
        if adt is not None:
            out["adjacent_taunted_enemies"] = int(adt)
        return out

    def effects(self, uid) -> list:
        """Effets ACTIFS de l'unité (matérialisés, gate `EffectComponent.IsActive` + condition) —
        `EffectsState.active_effects`, avec le contexte COMPLET (`unit_state`)."""
        return self.eff_state.active_effects(uid, self.unit_state(uid))

    def effect_carrier_ids(self, exclude=None) -> list:
        """#999-r3-r1-r1 -- UNIVERS DES PORTEURS d'un agrégateur d'aura, face DÉCISION.

        Le natif itère une `List<KeyValuePair<entité, List<effet>>>` de l'ÉTAT
        (`IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` et
        son jumeau ATTAQUE) : la boucle est **BOARD-WIDE** et ne lit AUCUNE position pour décider
        qui entre. Les trois boucles de porteurs du port itéraient `scene.pos_by_id`, ce qui
        écartait STRUCTURELLEMENT toute **MACHINE OF WAR** (`step_context` ne verse une MoW dans
        `pos_by_id` que `if m.get("pos")`, `null` par construction — une MoW est hors-plateau, et
        le natif n'a pas de position pour elle non plus). Le filtre était un ARTEFACT du port ; il
        tenait à lui seul les six `PARTIEL` de `kit-coverage.md` (1442, 1443, 1445, 1449, 1494,
        1548). Pendant EXACT de la réparation COMBAT (`damage_model._apply_ally_attack_damage_auras`
        / `defender_modifiers`, mêmes deux agrégateurs).

        L'univers rendu est `pos_by_id` **plus** les entités qui PORTENT un effet matérialisé sans
        y figurer (clés d'`EffectsState.by_unit`). Cet élargissement est donc **borné aux porteurs
        réels** : un état sans MoW porteuse rend exactement la liste d'avant, ce qui est ce qui
        garantit qu'aucun verdict existant ne bouge.

        SANTÉ, en TRI-ÉTAT : les boucles appelantes écartent le porteur mort par
        `(scene.hp(uid) or 0) > 0`. Pour les ids AJOUTÉS on écarte sur `hp <= 0` **mesuré**, et on
        GARDE un `hp` absent -- même discipline que la face COMBAT, où `_load_machines` ne pose
        aucun `HealthComponent` et où le filtre ne mord que `if hc is not None`. Rabattre un `None`
        sur zéro y ré-écarterait toutes les MoW, c'est-à-dire ré-ouvrirait le trou par l'autre bout.
        """
        out = [uid for uid in self.pos_by_id if uid != exclude]
        seen = set(self.pos_by_id)
        by_unit = getattr(self.eff_state, "by_unit", None) or {}
        for uid in by_unit:
            if uid in seen or uid == exclude:
                continue
            hp = self.hp_by_id.get(uid)
            if hp is not None and hp <= 0:
                continue                                   # porteur mort -> aura eteinte
            seen.add(uid)
            out.append(uid)
        return out

    def faction(self, uid):
        c = self.ctx_by_id.get(uid)
        return c.faction if c is not None else None

    def ability_state(self, uid, ability_id) -> dict | None:
        """AbilityState PER-ABILITY {level, multiplier} (capteur #100) ; None si non capturé
        (offline `from_state`, ou entrée absente) → l'appelant retombe sur le canal global."""
        return (self.abstate_by_id.get(uid) or {}).get(ability_id)

    def triggered_ability_state(self, uid, ability_name):
        """`(level, multiplier)` de l'ability DECLENCHEE `ability_name` montee sur `uid` -- face
        DECISION du foyer `runner/operations/triggers/base.py::triggered_ability_state` (#357).

        Mirror de `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` : pour une
        MYTHIQUE de MoW (ou une relique EQUIPEE) c'est l'etat **TERTIAIRE**, `1..4 / 100`, et non
        celui des PASSIFS (`50 / 180` en runner normalise) -- confondre les deux lit le dernier
        palier de la config au lieu du bon (`ToZeroBasedIndex` clampe).

        La table est clee par ORDINAL (`raw[0]` = `TriggeredAbilityType`), l'appelant par NOM : la
        resolution passe par le MIRROR, jamais par un ordinal ecrit ici. Nom hors de l'enum, uid
        absent ou canal muet -> `(None, None)` = NON MESURE, jamais un couple devine."""
        from ..entities.triggered_ability_type import TriggeredAbilityType   # feuille enum (#485-r1-r1)
        par_id = self.trigstate_by_id.get(uid)
        if not par_id:
            return (None, None)
        member = getattr(TriggeredAbilityType, str(ability_name), None)
        if member is None:
            return (None, None)
        return par_id.get(int(member)) or (None, None)

    def defense_stat(self, uid):
        """`StatComponent` DEFENSE (stat 3) de l'unité — mirror du DefenseComponent natif consommé
        par la face défenseur de `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` (#194).
        None si non capturé (from_state offline sans suivi defense, ou unité absente) → axe inerte."""
        return self.defstat_by_id.get(uid)

    def total_attacks_made(self, uid) -> int:
        """`ActorStatisticsComponent.TotalAttacksMade` (+0x20, capteur actorStats) — nb d'attaques
        de l'unité CETTE BATAILLE. Indexe le buff MartialInspiration (+33%/tour, #106). 0 si non
        capté (from_state offline / début de bataille)."""
        return int((self.actorstats_by_id or {}).get(uid, 0) or 0)

    def attack_current(self, uid) -> int:
        """`GetStat(unit, Attack=0, Current)` DU PAS — la lecture des noeuds `StatAmount(Attack)`
        (#45-s18). Fallback `ctx.attack` (cold snapshot / from_state live) si non capturé."""
        v = (self.attack_cur_by_id or {}).get(uid)
        if v is not None:
            return int(v)
        c = self.ctx_by_id.get(uid)
        return int(c.attack) if c is not None else 0

    def extra_hits_current(self, uid) -> int | None:
        """`GetStat(unit, ExtraHits=17, Current)` DU PAS (#57a) — inclut les stat-mods dynamiques
        (Swarm_HitReduction). Fallback `ctx.stat(EXTRA_HITS)` (cold snapshot / from_state live) ;
        None si l'unité est absente des deux tables."""
        v = (self.extra_hits_cur_by_id or {}).get(uid)
        if v is not None:
            return int(v)
        c = self.ctx_by_id.get(uid)
        return int(c.stat(_ST.EXTRA_HITS)) if c is not None else None

    def turns_started(self, uid) -> int | None:
        """`GetStat(unit, 0xc=TurnsStarted)` (`IdunBattle.Entities.Formulas.UnitTurnsStartedFormula$$Calculate`) — nb
        de tours DEMARRES par l'unité cette bataille (incr. StartTurn). Indexe le gate slot-4
        `ShouldEvaluate(unit) = GetStat(unit,12) > 1` (#46, corps foldé IdunBattle.AI.Playbook.Loki.AlphaWarriorPlaybook$$ShouldEvaluate). None si non
        capturé (uid absent des tables) → l'appelant ne gate pas à l'aveugle."""
        v = (self.turns_started_by_id or {}).get(uid)
        return None if v is None else int(v)

    def turns_finished(self, uid) -> int | None:
        """`IdunBattle.Entities.UnitExtensions$$GetTurnsFinished(unit)` (`UnitComponent + 0x5c`) — nb
        de tours que CETTE unite a TERMINES cette bataille (incr. `EndTurnOperation$$Execute`).
        Indexe le gate slot-4 `...InstrumentsOfVengeancePlaybook$$GetUseProbability` (#27-r8).

        None si non capture (uid absent des tables) -> l'appelant ne gate PAS a l'aveugle. C'est la
        meme convention que `turns_started` : un canal muet doit se DIRE muet, jamais se rabattre
        sur 0 -- ici un `0` invente rendrait `Fix64.Zero`, donc un REFUS de l'ability que le natif
        n'a pas prononce (degradation RESTRICTIVE silencieuse)."""
        v = (self.turns_finished_by_id or {}).get(uid)
        return None if v is None else int(v)

    def has_taken_damage_of_profile_this_turn(self, uid, profile_id) -> bool | None:
        """`IdunBattle.Entities.UnitExtensions$$HasTakenDamageOfDamageProfileThisTurn(unit, profile)`
        = `ContainsKey(ActorStatisticsComponent.receivedDamageThisTurn, profile)`.

        PRESENCE d'une cle, jamais un compte -- a ne pas confondre avec
        `...AmountOfTimesTrigger$$ShouldTrigger`, qui exige une EGALITE stricte (le mauvais choix
        change le resultat des le 2e coup du meme profil sur la meme cible, cf. `case-487` §5).

        TRI-ETAT : `None` = **canal non mesure** (regime LIVE -- aucun hook ne publie
        `ActorStatisticsComponent + 0x80`), distinct de `False` = mesure et le profil est absent.
        L'appelant ne doit PAS rabattre `None` sur `False` : ici un `False` invente ferait tomber
        l'utilite d'`HellfyreMissileRack` a 0, sous son `MIN_UTILITY` de 1, donc prononcerait un
        refus que le natif n'a pas prononce."""
        tbl = self.received_damage_profiles_by_id
        if tbl is None:
            return None
        s = tbl.get(uid)
        if s is None:
            return None
        return int(profile_id) in s


class _SceneEffectTargetWorld:
    """Substrat DÉCISION de `entities.effect_targets.EffectTargetWorld` (pendant exact de
    `runner/components.py::_RunnerEffectTargetWorld`). Lit les tables de `Scene`, rien d'autre."""
    __slots__ = ("sc",)

    def __init__(self, scene: "Scene"):
        self.sc = scene

    def unit_ids(self):
        return [u.get("id") for u in (self.sc.units or ()) if u.get("id") is not None]

    def carries(self, uid: int, effect_type: int) -> bool:
        # `onlyActive = 0` : `EffectsState.has_effect` (filtre `consumed` seul), pas `active_effects`.
        es = self.sc.eff_state
        return bool(es.has_effect(int(uid), int(effect_type))) if es is not None else False

    def pos(self, uid: int):
        return self.sc.pos_by_id.get(uid)

    def team(self, uid: int):
        return self.sc.team_by_id.get(uid)

    def alive(self, uid: int) -> bool:
        u = next((x for x in (self.sc.units or ()) if x.get("id") == uid), None)
        return True if u is None else bool(u.get("alive"))

    def traits(self, uid: int):
        c = self.sc.ctx_by_id.get(uid)
        return (getattr(c, "traits", None) or ()) if c is not None else ()

    def neigh_by_pos(self):
        """Canal de VOISINAGE NATIF du protocole (#943-r7) -- la `Scene` le DERIVE deja de son
        board (`adjacent_neigh_by_pos`, memoise). `None` = pas de board -> repli geometrique."""
        return self.sc.neigh_by_pos

    def elev_by_pos(self):
        """Second etage (`|dElev| < 2`) -- table `tileMeta` deja portee par la `Scene`."""
        return self.sc.elev_by_pos


# ── SEAM live-feed (RPC) — tables cold + état par-pas. `rpc(method, body, timeout) -> result dict`. ──
def _hydrate_static_unit(ctx_by_id, vis_by_id, mult_by_id, ablvl_by_id, abstate_by_id,
                         u, vis_id, stat_types):
    """Entrée STATIQUE d'une unité dans les tables du predictor (bloc per-unit de
    `build_predictor`, partagé avec l'hydratation mid-bataille de `refresh_shields` #53).

    #87 : NE PAS dropper le ctx sur `normalAttack.error`. `readNormalAttack` (frida rpc-view.ts)
    renvoie error="aucune cible atteignable au deploiement (base non capturable)" quand aucun
    ennemi n'est a portee de l'attaque normale DEPUIS LA POSITION COURANTE (il ne teste PAS les
    move-tiles). Or le natif score les attaques depuis les tuiles de MOUVEMENT -> une unite peut
    avoir des attaques rankees (attackPlans/decisionView non vide) alors que sa base normale est
    "non capturable" au deploiement. Dropper le ctx -> scene.ctx()=None -> make_normal_attack_
    predictions renvoie None -> AUCUNE attaque scoree (normale ET specials via _PREDICT_VIA_
    NORMAL_ATTACK), d'ou attack_cands=[] malgre NATIVE ranked non-vide. `from_snapshot` degrade
    deja proprement sur na.error (nh=1, min/max=0) ; la base reelle = get_stat(ATTACK, INITIAL)
    (position-independante) et l'arme est re-resolue par adjacence (select_weapon_pierce). Le port
    ne score de toute facon QUE les abilities deja rankees par le natif (_best_attack itere
    plan.evals) -> aucun risque d'attaque fantome. Build INCONDITIONNEL."""
    eid = u["entityId"]
    u["visualId"] = vis_id
    vis_by_id[eid] = vis_id
    uc = u.get("unitConfig") or {}
    if isinstance(uc, dict) and uc.get("abilityVariablesMultiplier") is not None:
        mult_by_id[eid] = int(uc["abilityVariablesMultiplier"])
        if uc.get("passiveAbilityLevel"):
            ablvl_by_id[eid] = int(uc["passiveAbilityLevel"])
    # AbilityState PER-ABILITY (#100) — capteur combatSnapshot.abilityStates (entrée
    # ActiveAbility._abilityState @0x4c) : {abilityId: {level, multiplier}}.
    sts = {int(a["id"]): {"level": a.get("level"), "multiplier": a.get("multiplier")}
           for a in (u.get("abilityStates") or []) if a.get("id") is not None}
    if sts:
        abstate_by_id[eid] = sts
    ctx_by_id[eid] = UnitContext.from_snapshot(u, GC.unit(vis_id or ""), stat_types)


def _seed_measured_passives(ctx_by_id, ability_states) -> int:
    """Seede `UnitContext.passive_abilities` des tables de PREDICTION depuis le RPC
    `unitAbilityStates` (#419-r1-tr14-r5) — le PENDANT EXACT, sur ce seam-ci, de
    `snapshot._load_passive_abilities` (#366-r1) cote COMBAT. Rend le nombre d'unites seedees.

    MIRROR. Le natif n'a pas de substrat de passifs separe pour la prediction : le dispatch de
    l'attaque normale est fait UNE fois par
    `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, qui lit
    `UnitConfiguration.PassiveAbilities` via
    `IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromPassive` et ecrit
    `ActiveAbilityComponent.NormalAttackType@0x28`. Les DEUX faces du port doivent donc lire la
    MEME liste — d'ou le parsing PARTAGE (`snapshot.passive_ability_names_by_unit`) et le predicat
    PARTAGE (`engine.services.custom_normal_attack.substitutes_normal_attack`).

    POURQUOI ICI. Sans ce seed, `scene.ctx(uid).passive_abilities` vaut `None` en live et le
    predicat retombe sur le KIT gameconfig — exactement le fork mesure par #419-r1-tr14-r5 : sur un
    bras `replace=True`, le natif ramene l'attaque normale de `tauMarksman` a `69` pendant que le
    port continuait de prendre le chemin drone `1076`, pour `+5.458908` / `+16.056789` d'utilite de
    paire.

    RANG. Les passifs de CONFIGURATION sont figes au spawn (la fabrique ne tourne qu'une fois par
    entite), donc le COLD suffit — contrairement aux traits (#267), qu'`AddTraitOperation` accorde
    en cours de bataille. `refresh_shields` ne le rappelle donc que pour les ARRIVANTS.

    TRI-ETAT : canal muet (RPC absent/KO) -> rien n'est pose, `passive_abilities` reste `None` et le
    predicat retombe sur le kit, STRICTEMENT comme avant."""
    seeded = 0
    for uid, names in passive_ability_names_by_unit(ability_states).items():
        c = ctx_by_id.get(uid)
        if c is None:
            continue
        c.passive_abilities = names
        seeded += 1
    return seeded


def _seed_measured_actives(ctx_by_id, ability_states) -> int:
    """Seede `UnitContext.active_abilities` des tables de PREDICTION depuis le RPC
    `unitAbilityStates` (#419-r1-tr14-r5-r2) — le PENDANT EXACT, sur ce seam-ci, de
    `snapshot._load_active_abilities` cote COMBAT. Rend le nombre d'unites seedees.

    MEME raison d'etre que `_seed_measured_passives` juste au-dessus, sur la SECONDE voie de la
    cascade : le dispatch d'attaque normale est fait UNE fois par
    `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, qui consulte
    `GetCustomNormalAttackTypeFromPassive` PUIS, si elle rend `null`,
    `GetCustomNormalAttackTypeFromActive`. Les DEUX faces du port doivent lire les DEUX listes —
    d'ou le parsing PARTAGE (`snapshot.active_ability_names_by_unit`) et le predicat PARTAGE
    (`engine.services.custom_normal_attack.substitutes_normal_attack`).

    RANG : identique aux passifs — les actives de CONFIGURATION sont figees au spawn, donc le COLD
    suffit et `refresh_shields` ne les re-seede que pour les ARRIVANTS.

    COUT : NUL. Le payload est celui que `_seed_measured_passives` vient de consommer, aucun RPC
    supplementaire n'est emis.

    TRI-ETAT : canal muet -> rien n'est pose, `active_abilities` reste `None`, la voie active du
    predicat retombe sur le kit, STRICTEMENT comme avant."""
    seeded = 0
    for uid, names in active_ability_names_by_unit(ability_states).items():
        c = ctx_by_id.get(uid)
        if c is None:
            continue
        c.active_abilities = names
        seeded += 1
    return seeded


def _seed_measured_config_actives(ctx_by_id, ability_states) -> int:
    """Seede `UnitContext.config_active_abilities` des tables de PREDICTION depuis le RPC
    `unitAbilityStates` (#419-r1-tr14-r5-r2-r2-r1) — le PENDANT EXACT, sur ce seam-ci, de
    `snapshot._load_config_active_abilities` cote COMBAT. Rend le nombre d'unites seedees.

    POURQUOI CE CANAL EN PLUS DE `_seed_measured_actives`. Celui-la lit l'`ActiveAbilityComponent`
    (etat APRES la fabrique) ; celui-ci lit `UnitConfiguration.ActiveAbilities` (etat AVANT), et
    c'est ce que teste la garde `FilterNewList` de
    `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`. Les deux ne sont PAS
    interchangeables : sur le canal POST la garde repond juste meme les trois voies amont coupees,
    donc elle ne peut rien falsifier.

    RANG : identique aux seeds voisins — la CONFIGURATION est figee (elle vient de la BC), donc le
    COLD suffit et `refresh_shields` ne la re-seede que pour les ARRIVANTS.

    COUT : NUL. Meme payload que `_seed_measured_passives`, aucun RPC supplementaire.

    TRI-ETAT : cle absente = canal muet -> rien n'est pose et la garde ne gate pas ; valeur `None`
    = mesure « pas joint » ; liste (fut-elle vide) = mesure."""
    seeded = 0
    for uid, names in config_active_ability_names_by_unit(ability_states).items():
        c = ctx_by_id.get(uid)
        if c is None:
            continue
        c.config_active_abilities = names
        seeded += 1
    return seeded


def _seed_measured_triggered(ctx_by_id, ability_states) -> int:
    """Seede `UnitContext.triggered_abilities` des tables de PREDICTION depuis le RPC
    `unitAbilityStates` (#419-r1-tr14-r5-r2-r1-r1) — le PENDANT EXACT, sur ce seam-ci, de
    `snapshot._load_triggered_abilities` (#456-r1) cote COMBAT. Rend le nombre d'unites seedees.

    POURQUOI ICI, et pourquoi c'etait un TROU. `scene_tile_leaf_ctx` lit deja ce champ par le foyer
    `entities.triggered_ability_type.entity_triggered_ability_ids` — mais il n'etait seede QUE par
    la face COMBAT (`Scene.from_state`). Sur le chemin LIVE de la decision
    (`Scene.from_predictor_sctx` / `build_predictor`) il restait `None`, donc le foyer retombait
    silencieusement sur le KIT gameconfig par `visualId`, c'est-a-dire exactement la reconstruction
    que #456-r1 a mesuree FAUSSE DANS LES DEUX SENS cote combat (`tauDarkstrider` natif
    `[1143, 1051, 1044]` contre kit `[1143]` ; `tauCrisis` greffe natif `[1120, 1030]` contre kit
    `[1133]`). Le gate `ShouldExecute` de l'attaque normale lit ce meme substrat sur la CIBLE
    (`IdunBattle.Entities.UnitExtensions$$HasTriggeredAbility(target, 0x48)`) : sans ce seed, un
    passif GREFFE sur la cible est monte LIVE et INVISIBLE cote port.

    RANG : identique aux deux seeds voisins — le `TriggeredAbilityComponent` de CONFIGURATION est
    fige au spawn (la fabrique ne tourne qu'une fois par entite), donc le COLD suffit et
    `refresh_shields` ne le re-seede que pour les ARRIVANTS.

    COUT : NUL. Le payload est celui que `_seed_measured_passives` vient de consommer, aucun RPC
    supplementaire n'est emis.

    TRI-ETAT : canal muet -> rien n'est pose, `triggered_abilities` reste `None` et les foyers
    retombent sur le kit, STRICTEMENT comme avant."""
    seeded = 0
    for uid, ids in triggered_ability_ids_by_unit(ability_states).items():
        c = ctx_by_id.get(uid)
        if c is None:
            continue
        c.triggered_abilities = ids
        seeded += 1
    return seeded


def _seed_measured_traits(ctx_by_id, snap) -> int:
    """Seede `UnitContext.traits` des tables de PRÉDICTION depuis `combatSnapshot.units[].traits`
    (#267) — le PENDANT EXACT, sur ce seam-ci, de `snapshot._load_unit_traits` (#264) côté COMBAT.

    MIRROR. Le natif n'a pas de substrat de traits séparé pour la prédiction :
    `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` (appelée deux fois,
    sur les deux bornes, par `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage`)
    teste le défenseur par `IdunBattle.Entities.UnitExtensions$$HasTrait(defender, 0x3f1)` — LA MÊME
    fonction que la face combat, qui délègue à `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait` :

        HasTrait(t) == !retirés(+0x50).Contains(t)
                       && ( permanents(+0x40).Contains(t) || temporaires(+0x48).Contains(t) )

    Le canal `combatSnapshot.units[].traits` (#233) est l'invocation de cette fonction par valeur
    d'enum : il rend l'ensemble EFFECTIF. `_hydrate_static_unit` posait jusqu'ici
    `traits = gameconfig.unit(vis).traits` (via `UnitContext.from_snapshot`) et laissait
    `traits_measured` à faux, si bien qu'`entity_trait_names` re-dérivait par-dessus le pseudo-trait
    de grande-alliance : une RECONSTRUCTION du substrat à partir d'une AUTRE source, alors que #264
    la remplaçait déjà par la lecture côté combat. Une face qui lit et l'autre qui reconstruit, c'est
    le fork « ce que le moteur fait != ce que la prédiction annonce » — et il était OBSERVABLE :
    `necroOverlord` porte `Resilient` au gameconfig et PAS en bataille (mesuré, cf.
    `snapshot._load_unit_traits`), donc `_target_damage_limits` rendait `target_has_resilient=True`
    et la prédiction annonçait un dégât capé à `HP-1` là où le natif tue.

    PORTÉE : toutes les lignes du snapshot qui ont un ctx dans les tables, `EntityType.Unit` ET
    `EntityType.Machine` (`build_predictor` hydrate les deux : une MoW porte un `MachineComponent`,
    frère du `UnitComponent` issu du même `BaseUnitComponent$$.ctor`, donc `HasTrait` y répond —
    mesuré : `ultraDreadnought` rend `MachineOfWar`+`Imperial`, que la reconstruction ratait
    intégralement faute de `visualId` sur cette ligne).

    TRI-ÉTAT, même discipline que `_unit_flag_from_snapshot` : champ ABSENT ou `null` = **non
    mesuré** (hook antérieur à `0231573`) -> on ne TOUCHE PAS `ctx.traits`, donc reconstruction
    strictement antérieure ; une LISTE, `[]` comprise = mesure, on écrit. Confondre les deux ferait
    passer un capteur MORT pour une unité sans aucun trait. Rend le nombre de ctx seedés."""
    n = 0
    for u in (snap.get("units") or []):
        eid = u.get("entityId")
        traits = u.get("traits")
        if eid is None or not isinstance(traits, list):
            continue                                  # absent / `null` = NON MESURÉ -> défaut du port
        ctx = (ctx_by_id or {}).get(eid)
        if ctx is None:
            continue
        ctx.traits = sorted(trait_names_from_ids(traits))
        ctx.traits_measured = True
        n += 1
    return n


def build_predictor(rpc, rid):
    """Tables STATIQUES (cold, 1×/runner) : `combatSnapshot` (dégât d'arme + stats + unitConfig
    mult/level + boucliers) + `decisionView` (visualId). None si combatSnapshot KO. (Ex-`PV.build_predictor`.)"""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not snap.get("ok"):
        return None
    # #999-r3 -- PENDANT EXACT, sur ce seam-ci, du garde pose par `snapshot.load_state` cote COMBAT.
    # `_hydrate_static_unit` va lire `units[].rarity` via `UnitContext.from_snapshot` : on confronte
    # d'abord le nom PLEIN de l'enum publie par le capteur (`rarityEnum`), seul discriminant d'une
    # confusion entre les cinq enums de rarete du build. Canal muet -> no-op.
    assert_rarity_channel(snap)
    dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
    vis_by_id = {u["id"]: u.get("visualId") for u in (dv0.get("units") or [])}
    ctx_by_id, armor_by_id, mult_by_id, ablvl_by_id, shield_by_id = {}, {}, {}, {}, {}
    abstate_by_id = {}
    for u in (snap.get("units") or []):
        eid = u["entityId"]
        armor_by_id[eid] = int((u.get("stats") or {}).get("fixedArmor") or 0)
        shield_by_id[eid] = sum(int(s.get("amount") or 0)
                                for s in (u.get("shields") or []) if (s.get("amount") or 0) > 0)
        _hydrate_static_unit(ctx_by_id, vis_by_id, mult_by_id, ablvl_by_id, abstate_by_id,
                             u, vis_by_id.get(eid), snap.get("statTypes"))
    # #267 : les TRAITS des ctx viennent de la MESURE (`combatSnapshot.units[].traits`), pas d'une
    # relecture du kit gameconfig par visualId — pendant de `snapshot._load_unit_traits` (#264) sur
    # le seam de PRÉDICTION. DYNAMIQUE (`IdunBattle.Operations.AddTraitOperation$$Execute` accorde
    # en bataille) -> re-seedé par pas dans `refresh_shields`, comme les autres axes vivants.
    _seed_measured_traits(ctx_by_id, snap)
    # #419-r1-tr14-r5 : les PASSIFS de configuration (`UnitConfiguration.PassiveAbilities`) — la clé
    # de dispatch de l'attaque normale CONCRÈTE. MÊME capteur et MÊME parsing que la face COMBAT
    # (`snapshot._load_passive_abilities`). FIGÉS au spawn -> cold suffit ; `refresh_shields` ne les
    # re-seede que pour les ARRIVANTS. Canal KO -> rien posé (repli kit, comportement d'avant).
    try:
        _abst = rpc("unitAbilityStates", {"runnerId": rid}, 60)
    except Exception:
        _abst = None
    _seed_measured_passives(ctx_by_id, _abst)
    # #419-r1-tr14-r5-r2 : la SECONDE voie de la meme cascade (`UnitConfiguration.ActiveAbilities`),
    # sur le MEME payload -- aucun RPC de plus.
    _seed_measured_actives(ctx_by_id, _abst)
    # #419-r1-tr14-r5-r2-r2-r1 : l'etat PRE-FABRIQUE de la MEME liste (capteur #466), toujours sur
    # le meme payload. C'est le substrat de la garde du repli generique.
    _seed_measured_config_actives(ctx_by_id, _abst)
    # #419-r1-tr14-r5-r2-r1-r1 : le `TriggeredAbilityComponent` ENTIER, sur le MEME payload encore.
    # C'est ce que lit `IdunBattle.Entities.UnitExtensions$$HasTriggeredAbility`, donc le substrat du
    # gate `ShouldExecute` de l'attaque normale (sur la CIBLE) et du dispatcher d'utilite
    # `TriggeredAbilitiesUtility(2)` -- que `scene_tile_leaf_ctx` interrogeait deja sans que rien ne
    # le seede sur ce chemin.
    _seed_measured_triggered(ctx_by_id, _abst)
    # #1042-r1 : l'`AbilityState` PER-TRIGGERED du MEME payload -- `{uid: {abilityId: (lvl, mult)}}`.
    # C'est ce que `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` relit pour
    # tout effet pose par une TRIGGERED, et pour une MYTHIQUE de MoW c'est l'etat **TERTIAIRE**
    # (`1..4 / 100`). `abstate_by_id` (capteur `combatSnapshot.abilityStates`) ne publie que les
    # ACTIVES -> sans cette table, la face DECISION n'avait AUCUN canal et les deux auras 1443/1445
    # restaient INERTES. COUT NUL (meme payload, aucun RPC de plus).
    trigstate_by_id = triggered_ability_states_by_unit(_abst)
    # TotalAttacksMade PER-UNITE (#106) — capteur actorStats (ActorStatisticsComponent +0x20). Capture
    # au BUILD (point-in-time = count au pas 0). DYNAMIQUE (incremente a chaque attaque) -> RE-CAPTUREE
    # PAR-PAS par `refresh_shields` (#33 : sans ce refresh, une prediction mid-bataille indexee par ce
    # compteur SOUS-ESTIME -- MartialInspiration ; staleness prouvee 31337 s16). Degrade proprement a
    # {} (count=0) si le RPC manque/echoue.
    try:
        _ast = rpc("actorStats", {"runnerId": rid}, 40)
    except Exception:
        _ast = None
    actorstats_by_id = {u["entityId"]: int(u.get("totalAttacksMade") or 0)
                        for u in ((_ast or {}).get("units") or []) if u.get("entityId") is not None}
    # case-322-r2 : `TilesMovedThisTurn` (+0xf0) du MEME capteur. AUSSI dynamique que `Moved` (chaque
    # deplacement l'incremente, `ActorStatisticsComponent$$ResetThisTurn` le remet a zero en FIN de
    # tour) -> re-capture par pas dans `refresh_shields`.
    tiles_moved_by_id = _tiles_moved_from_actor_stats(_ast)
    # BOARD STATIQUE (#183) : mirror offline des Tile objects natifs. Le natif ne passe PAS de "board" a la
    # prediction -- l'attackerTile (tuile candidate, `local_588` de CalculateAttackerModifiersForPrediction
    # IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction) PORTE lui-meme son terrain (tileDefId -> IdunBattle.Entities.TileExtensions$$IsTrench = IsTileWithId) et son graphe
    # de voisins STOCKE (ConnectivityComponent.IsNeighbour, consulte par IdunBattle.Entities.TileExtensions$$IsNeighbourOf ET par
    # IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent = (|rowD|<2) & IsNeighbour). Le Board `native_sym` reproduit
    # ce graphe (capture GetAdjacentTiles(false,false,true) = topologie complete #148) + le terrain. Point de
    # couture = build_predictor (tables statiques cold 1x/runner = l'analogue du graphe de tuiles natif bati
    # une fois au battle-init). Threade dans le dict -> from_predictor_sctx le lit en fallback pour les 3
    # call-sites (context live, predict_samples, predict_sweep). ELEVATION derivee du MEME board (source
    # unique, un seul fetch boardGraph), comme Scene.from_state.
    board = build_board(rpc, rid)
    elev_by_pos = ({(t["col"], t["row"]): int(t.get("elevation") or 0) for t in board.by_id.values()}
                   if board is not None else None)
    return {"ctx_by_id": ctx_by_id, "armor_by_id": armor_by_id, "shield_by_id": shield_by_id,
            "mult_by_id": mult_by_id, "ablvl_by_id": ablvl_by_id, "vis_by_id": vis_by_id,
            "abstate_by_id": abstate_by_id, "actorstats_by_id": actorstats_by_id,
            "trigstate_by_id": trigstate_by_id,          # #1042-r1, cf. son seed ci-dessus
            "tiles_moved_by_id": tiles_moved_by_id,
            # #46 : TurnsStarted (stat 12) — gate slot-4 « pas au 1er tour ». DYNAMIQUE ->
            # re-capturé par-pas via `refresh_shields` (le cold seul serait figé au pas 0).
            "turns_started_by_id": {
                u["entityId"]: int((u.get("stats") or {}).get("turnsStarted") or 0)
                for u in (snap.get("units") or [])
                if (u.get("stats") or {}).get("turnsStarted") is not None},
            # #27-r8 : TurnsFinished (`UnitComponent + 0x5c`) — gate slot-4 de 1215. Le champ est
            # au NIVEAU DE L'UNITE (pas sous `stats` : ce n'est pas un `StatType`, cf. §N11), publie
            # par `frida/hooks/features/ai-step/rpc-snapshot.ts` via `getTurnsFinishedMi`. DYNAMIQUE
            # (incremente a chaque fin de tour) -> re-capture par-pas dans `refresh_shields`.
            "turns_finished_by_id": {
                u["entityId"]: int(u.get("turnsFinished") or 0)
                for u in (snap.get("units") or [])
                if u.get("turnsFinished") is not None},
            # #378 : lien enfant -> summoner (`ChildComponent.ParentId`). STATIQUE par unite (pose
            # au spawn, jamais reecrit) mais la POPULATION ne l'est pas -> re-capture par-pas via
            # `refresh_shields`, sinon un summon apparu apres le pas 0 resterait sans parent.
            "parent_by_id": _parent_from_snapshot(snap),
            "board": board, "elev_by_pos": elev_by_pos,
            # #194 : vue DefenseComponent (stat 3 + modifications). Capture au BUILD ; DYNAMIQUE
            # (suit l'occupation de tuile) -> re-capturee par-pas via refresh_shields.
            "defstat_by_id": _defense_stats_from_snapshot(snap.get("units")),
            # #45b' : MaxHealth EFFECTIF (capteur combatSnapshot.healthMax = GetStat(e,5,part=2),
            # la lecture EXACTE de DamageUtility IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext pour combinedMax — base+modifs,
            # clamp cape). DYNAMIQUE (bump TwistedScience mid-bataille) -> refresh par-pas.
            # Vieux hooks sans le champ -> {} (fallback obs.hpMax base, etat anterieur).
            "hpmax_eff_by_id": _hpmax_eff_from_snapshot(snap.get("units")),
            # #45-s18 : Attack COURANT (GetStat(0, Current)) — lecture des noeuds StatAmount(Attack)
            # (splash Psyker). DYNAMIQUE (aura RitesOfBattle par adjacence) -> refresh par-pas.
            "attack_cur_by_id": {
                u["entityId"]: int((u.get("stats") or {}).get("attack") or 0)
                for u in (snap.get("units") or [])
                if (u.get("stats") or {}).get("attack") is not None},
            # #57a : ExtraHits COURANT (GetStat(17, Current)) — stat-mods hits dynamiques
            # (Swarm_HitReduction IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour). DYNAMIQUE -> refresh par-pas.
            "extra_hits_cur_by_id": {
                u["entityId"]: int((u.get("stats") or {}).get("extraHits") or 0)
                for u in (snap.get("units") or [])
                if (u.get("stats") or {}).get("extraHits") is not None},
            # O5 : `UnitFlag.PreventOverkill` LU du composant de flags. DYNAMIQUE (les triggers de
            # `FuelledByFury_BlockOverkillEffect` le posent/retirent en bataille) -> re-capturé
            # par pas via `refresh_shields`, comme les autres axes vivants ci-dessus.
            "prevent_overkill_by_id": _unit_flag_from_snapshot(snap, "PreventOverkill"),
            # #266 : `UnitFlag.Moved` / `UnitFlag.Teleported`, MÊME canal. DYNAMIQUE au plus haut
            # point (posés par chaque déplacement, purgés à l'entrée de tour du joueur par
            # `UnitFlagsComponent$$RemoveTurnFlags`) -> re-capturés par pas via `refresh_shields`.
            "moved_by_id": _unit_flag_from_snapshot(snap, "Moved"),
            "teleported_by_id": _unit_flag_from_snapshot(snap, "Teleported"),
            # #17 : `UnitFlag.ActiveAbilityUsed` — gate d'entree du generateur d'abilities. AUSSI
            # dynamique que `Moved` (pose au cast, purge a l'entree de tour) -> refresh par pas.
            "active_ability_used_by_id": _unit_flag_from_snapshot(snap, "ActiveAbilityUsed")}


def build_board(rpc, rid):
    """Board STATIQUE (graphe de connectivite + terrain) depuis le RPC `boardGraph` (STATIQUE, 1x/runner).
    Mirror offline des Tile objects natifs : `native_sym` = graphe complet symetrise (capture
    `GetAdjacentTiles(false,false,true)`, #148) = `ConnectivityComponent.IsNeighbour` ; `terrain_at`=tileDefId
    = `IsTrench`/`IsTileWithId`. Alimente les gates POSITIONNELS de la prediction : reduction Trench
    (IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction, sous-branche IsTrench(attackerTile)+IsNeighbourOf) + adjacence
    (select_weapon melee/ranged) + elevation. None si `boardGraph` KO -> gates positionnels no-op (etat
    anterieur, pas de crash)."""
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
    except Exception:
        return None
    tiles = (bg or {}).get("tiles") if isinstance(bg, dict) else None
    if not tiles:
        return None
    return Board(tiles, adjacency="native_sym")


def _hpmax_eff_from_snapshot(units) -> dict:
    """{uid: MaxHealth EFFECTIF} depuis `combatSnapshot.healthMax` (#45b') = GetStat(e, Health=5,
    StatPart=2) — l'agrégat base+modifications (clamp cape inclus) que `DamageUtility
    IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` lit pour combinedMax. {} si le capteur manque (vieux hooks)."""
    return {u["entityId"]: int(u["healthMax"]) for u in (units or [])
            if u.get("healthMax") is not None}


def _unit_flag_from_snapshot(snap, flag_name: str) -> dict:
    """{uid: `UnitExtensions.HasFlag(u, <flag_name>)`} depuis `combatSnapshot.unitFlags` (O5) — la
    lecture DIRECTE de `UnitFlagsComponent`, là où le port devait jusqu'ici DÉRIVER le fait d'un
    effet (PreventOverkill <- effet 1354) ou l'IGNORER (Moved / Teleported, #266).

    L'id du flag est pris dans `unitFlagTypes`, que le hook rend AU RUNTIME (littéraux de l'enum
    `IdunBattle.Entities.Enum.UnitFlag`), et n'est PAS écrit en dur ici : une renumérotation au
    prochain build se propage seule, au lieu de rendre cette lecture fausse en silence.

    Une unité n'entre dans la table QUE si sa mesure a eu lieu (`unitFlags` non `None`). Sur un hook
    antérieur à O5 la table reste donc VIDE et chaque accesseur garde son repli — le comportement
    d'avant, à l'identique. `[]` (lu, aucun flag posé) donne bien `False` : c'est exactement la
    distinction `null`/`[]` que le hook maintient exprès."""
    fid = (snap.get("unitFlagTypes") or {}).get(flag_name)
    if fid is None:
        return {}
    return {u["entityId"]: (int(fid) in u["unitFlags"])
            for u in (snap.get("units") or [])
            if u.get("entityId") is not None and u.get("unitFlags") is not None}


def _parent_from_snapshot(snap) -> dict:
    """{uid: parentId | None} depuis `combatSnapshot.units[]` (#378) -- mirror de
    `IdunBattle.Entities.Components.ChildComponent.ParentId`, le champ que
    `IdunBattle.Entities.UnitExtensions$$GetParent` lit pour resoudre le SUMMONER d'un summon.

    TRI-ETAT, et la distinction est PORTEE PAR LE CAPTEUR, pas devinee ici : une unite n'entre dans
    la table QUE si `parentMeasured is True`. Sur un hook anterieur a #378 le champ est absent, la
    table reste VIDE, `Scene.parent(uid)` rend `None` partout et le consommateur garde le
    comportement d'avant. Une unite mesuree SANS parent entre bien dans la table, a `None` : c'est
    un FAIT (`TryGetComponent<ChildComponent> == false` cote natif), pas une absence de mesure --
    et `Scene.parent_measured` sait les distinguer."""
    return {u["entityId"]: (None if u.get("parentId") is None else int(u["parentId"]))
            for u in ((snap or {}).get("units") or [])
            if u.get("entityId") is not None and u.get("parentMeasured") is True}


def _tiles_moved_from_actor_stats(ast) -> dict:
    """{uid: `ActorStatisticsComponent+0xf0`} depuis le capteur `actorStats` (case-322-r2) — le
    compteur que `IdunBattle.Entities.Formulas.TilesMovedThisTurnFormula$$Calculate` rend, et qui est
    le terme REEL de `prediction.prediction_tiles_moved_this_turn`.

    MEME discipline TRI-ETAT que `_unit_flag_from_snapshot` : une unite n'entre dans la table QUE si
    le champ est PRESENT et non `null`. Sur un hook qui ne publie pas encore `+0xf0` la table reste
    donc VIDE, l'accesseur rend `None`, et le port garde le seul terme « pas simule » — le
    comportement d'avant, a l'identique. `0` publie est un vrai zero (l'unite n'a pas bouge)."""
    return {u["entityId"]: int(u["tilesMovedThisTurn"])
            for u in ((ast or {}).get("units") or [])
            if u.get("entityId") is not None and u.get("tilesMovedThisTurn") is not None}


def _defense_stats_from_snapshot(units) -> dict:
    """{uid: StatComponent(DEFENSE)} depuis un `combatSnapshot` (#194). Reconstruit la vue
    `DefenseComponent` (stat 3) que la face défenseur de `IdunBattle.Core.Services.DamageCalculations$$CalculateModifiersFromStatModifications` lit : `initial` = defense résolue − statDelta.defense (base, 100 chez les unités
    mesurées), `modification` = UNE entrée pseudo-source « live » portant le TOTAL des modifications
    (statDelta). ⚠ Limitation documentée : le natif folde CHAQUE source séparément (produit de
    (1±vᵢ/100)) ; le capteur statDelta ne donne que le total → exact à 1 source (le cas tuile
    Thorns/SpiderWeb/DryBush), approximation si ≥2 sources defense simultanées (rare — un
    `statModSources` par unité donnerait le per-source au prix d'un scan entités par pas)."""
    out = {}
    for u in (units or []):
        stats = u.get("stats") or {}
        cur = stats.get("defense")
        if cur is None:
            continue
        delta = int((u.get("statDelta") or {}).get("defense") or 0)
        mod = ValueModification(total=delta, per_source={"live": delta} if delta else {})
        out[u["entityId"]] = StatComponent(initial=int(cur) - delta, modification=mod)
    return out


def refresh_shields(predictor, rpc, rid):
    """Rafraîchit l'état DYNAMIQUE par pas comparé (appeler 1×/pas) — deux sources FRAÎCHES :
    - `combatSnapshot` : boucliers accordés/consommés + armure débuffée + stat DEFENSE modifiée (#194) ;
    - `actorStats` : `TotalAttacksMade` par unité (#33/#106) — DYNAMIQUE (incrémente à CHAQUE attaque)
      donc le cold de `build_predictor` (capté au pas 0 = 0) SOUS-ESTIME toute prédiction mid-bataille
      indexée par ce compteur (MartialInspiration +33 %/attaque). Staleness FEED prouvée 31337 s16 :
      l'attaquant u79 avait fait 2 attaques → cold 598-898 vs natif 994-1976 == fresh (2 stacks).
    (Ex-`PV.refresh_shields`.)"""
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    if not snap.get("ok"):
        return
    predictor["shield_by_id"] = {
        u["entityId"]: sum(int(s.get("amount") or 0)
                           for s in (u.get("shields") or []) if (s.get("amount") or 0) > 0)
        for u in (snap.get("units") or [])}
    predictor["armor_by_id"] = {
        u["entityId"]: int((u.get("stats") or {}).get("fixedArmor") or 0)
        for u in (snap.get("units") or [])}
    predictor["defstat_by_id"] = _defense_stats_from_snapshot(snap.get("units"))
    # O5 : re-capture des flags d'unité (`UnitFlag.PreventOverkill`). DYNAMIQUE — les triggers de
    # `FuelledByFury_BlockOverkillEffect` (`On(0x21)&OwnerIsActor`, `On(0x12)` -> ActivateEffect ;
    # `On(0x2d = UnitRevived)&OwnerIsTarget` -> DeactivateEffect) posent et retirent le flag EN COURS de bataille.
    predictor["prevent_overkill_by_id"] = _unit_flag_from_snapshot(snap, "PreventOverkill")
    # #266 : re-capture de `Moved`/`Teleported`. Ce sont les flags les plus volatils du composant —
    # posés par `MoveUnitOperation$$Execute` -> `UnitExtensions$$SetMovedFlag` et purgés a chaque
    # entree de tour du joueur (`StartTurnOperation$$Execute` -> `RemoveTurnFlags`). Un cold figé au
    # pas 0 rendrait « n'a pas bougé » pour toute la bataille, soit exactement le +25% fantôme.
    predictor["moved_by_id"] = _unit_flag_from_snapshot(snap, "Moved")
    predictor["teleported_by_id"] = _unit_flag_from_snapshot(snap, "Teleported")
    # #17 : re-capture d'`ActiveAbilityUsed` (=2). MEME volatilite que `Moved` (pose par le cast,
    # purge a l'entree de tour) ; un cold fige au pas 0 rendrait « n'a pas encore agi » pour toute
    # la bataille, soit exactement l'over-fire mesure a 1357 s6 (le natif ne peut plus que bouger,
    # le port re-attaque).
    predictor["active_ability_used_by_id"] = _unit_flag_from_snapshot(snap, "ActiveAbilityUsed")
    # #45b' : re-capture MaxHealth EFFECTIF (part 2) — DYNAMIQUE (bump TwistedScience
    # mid-bataille : u87 777 s15 base 11044 -> 14036 apres le cast 1167 du pas 1).
    predictor["hpmax_eff_by_id"] = _hpmax_eff_from_snapshot(snap.get("units"))
    # #45-s18 : re-capture Attack COURANT (StatAmount(Attack) du pas) — DYNAMIQUE (aura
    # RitesOfBattle +1298 par ADJACENCE : 2101 au deploiement vs 803 au s18, 31337 u89).
    predictor["attack_cur_by_id"] = {
        u["entityId"]: int((u.get("stats") or {}).get("attack") or 0)
        for u in (snap.get("units") or [])
        if (u.get("stats") or {}).get("attack") is not None}
    # #57a : re-capture ExtraHits COURANT — stat-mods hits dynamiques (Swarm_HitReduction :
    # -1 hit par membre de swarm perdu, maintenu par le behaviour DSL IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateBehaviour). Le cold
    # (hydratation au build/spawn) SURESTIME les hits des qu'un membre meurt (1357 s15 u135 :
    # extraHits -2, natif 3 hits vs 5 offline).
    predictor["extra_hits_cur_by_id"] = {
        u["entityId"]: int((u.get("stats") or {}).get("extraHits") or 0)
        for u in (snap.get("units") or [])
        if (u.get("stats") or {}).get("extraHits") is not None}
    # #46 : re-capture TurnsStarted (stat 12, incrémente à chaque tour démarré) — même raison
    # que TotalAttacksMade (#33) : le cold du build (pas 0) sous-estime tout gate mid-bataille.
    predictor["turns_started_by_id"] = {
        u["entityId"]: int((u.get("stats") or {}).get("turnsStarted") or 0)
        for u in (snap.get("units") or [])
        if (u.get("stats") or {}).get("turnsStarted") is not None}
    # #27-r8 : re-capture TurnsFinished (`UnitComponent + 0x5c`, incremente a chaque tour TERMINE).
    # C'est le canal du gate slot-4 de 1215, et il est aussi volatil que TurnsStarted : le cold du
    # build vaut 0 pour toute la bataille, donc un gate cale dessus refuserait 1215 A JAMAIS.
    predictor["turns_finished_by_id"] = {
        u["entityId"]: int(u.get("turnsFinished") or 0)
        for u in (snap.get("units") or [])
        if u.get("turnsFinished") is not None}
    # #378 : re-capture du lien enfant -> summoner. La VALEUR est figee au spawn, mais la
    # POPULATION croit en cours de bataille -- un cold pris au pas 0 ignorerait tout summon apparu
    # depuis, c'est-a-dire precisement le cas d'usage (le drone `tauSmnDroneCommandLink` du jumeau
    # `1307 DefenderOfTheGreaterGood_ExtraHitsDrone` n'existe pas au deploiement).
    predictor["parent_by_id"] = _parent_from_snapshot(snap)
    # #33 : re-capture TotalAttacksMade (mirror du refresh de build_predictor). On n'écrase QUE si
    # le RPC a répondu (units présent) — sinon on garde le cold en fallback (RPC KO -> _r renvoie {},
    # .get("units") is None). Un `actorStats` valide sans attaque = {units:[…, totalAttacksMade:0]}.
    _ast = rpc("actorStats", {"runnerId": rid}, 40)
    if _ast.get("units") is not None:
        predictor["actorstats_by_id"] = {
            u["entityId"]: int(u.get("totalAttacksMade") or 0)
            for u in _ast["units"] if u.get("entityId") is not None}
        # case-322-r2 : re-capture de `TilesMovedThisTurn` (+0xf0). Le compteur est remis a zero a
        # CHAQUE fin de tour (`ActorStatisticsComponent$$ResetThisTurn`) et incremente a chaque
        # deplacement : un cold fige au pas 0 rendrait « n'a jamais bouge » pour toute la bataille,
        # soit exactement le sous-comptage que ce residu decrivait.
        predictor["tiles_moved_by_id"] = _tiles_moved_from_actor_stats(_ast)
    # #53 : hydrate les unités APPARUES mid-bataille (summons) dans les tables STATIQUES —
    # `build_predictor` est cold (pas 0), donc un summon spawné ensuite n'a NI ctx NI visualId :
    # scene.ctx(summon)=None -> make_normal_attack_predictions=None -> toutes tuiles refusées
    # ("gated") -> le moteur bouge au lieu d'attaquer (batch #52 : 5 misses, probe_53_summon).
    # Le natif lit l'ECS live par décision — l'hydratation par-pas retire la staleness de NOTRE
    # seam, elle n'invente rien. decisionView LAZY (1 RPC uniquement quand un entityId inconnu
    # apparaît dans le snapshot frais — rare).
    new_units = [u for u in (snap.get("units") or [])
                 if u.get("entityId") is not None and u["entityId"] not in predictor["ctx_by_id"]]
    if new_units:
        dv0 = rpc("decisionView", {"runnerId": rid, "maxRank": 1}, 60)
        vis = {x["id"]: x.get("visualId") for x in (dv0.get("units") or [])}
        for u in new_units:
            _hydrate_static_unit(predictor["ctx_by_id"], predictor["vis_by_id"],
                                 predictor["mult_by_id"], predictor["ablvl_by_id"],
                                 predictor["abstate_by_id"], u, vis.get(u["entityId"]),
                                 snap.get("statTypes"))
        # #419-r1-tr14-r5 : les PASSIFS des ARRIVANTS. Ils sont figés au spawn (la fabrique ne
        # tourne qu'une fois), donc ce re-seed est gaté sur `new_units` — pas un refresh par pas.
        # Sans lui, un summon dont l'attaque normale est substituée par un passif retomberait sur
        # le KIT pour toute la bataille.
        try:
            _abst = rpc("unitAbilityStates", {"runnerId": rid}, 60)
        except Exception:
            _abst = None
        _seed_measured_passives(predictor["ctx_by_id"], _abst)
        # #419-r1-tr14-r5-r2 : les ACTIVES des ARRIVANTS, meme rang et meme payload que les passifs.
        _seed_measured_actives(predictor["ctx_by_id"], _abst)
        # #419-r1-tr14-r5-r2-r2-r1 : l'etat PRE-FABRIQUE des ARRIVANTS. MESURE : un invoque
        # (`orksGrot`) a bien une `UnitConfiguration` dans `BC.Units` et rend `[]` -- une MESURE,
        # pas un « pas joint ». Sans ce re-seed, sa garde retomberait sur « canal muet ».
        _seed_measured_config_actives(predictor["ctx_by_id"], _abst)
        # #419-r1-tr14-r5-r2-r1-r1 : le `TriggeredAbilityComponent` des ARRIVANTS, meme rang et meme
        # payload. Sans lui, le gate `ShouldExecute` de l'attaque normale lirait le KIT pour tout
        # summon apparu en cours de bataille.
        _seed_measured_triggered(predictor["ctx_by_id"], _abst)
    # #267 : re-seed des TRAITS mesurés, APRÈS l'hydratation des arrivants (sinon un summon frais
    # garderait la reconstruction du kit). Les traits sont DYNAMIQUES : `AddTraitOperation$$Execute`
    # écrit `BaseUnitComponent+0x40`/`+0x48` en cours de bataille (ex. `Stationary` posé à
    # l'apparition par `DutyEternalAbility`) et `RemoveTraitOperation$$RemoveTrait` en retire. Le
    # cold de `build_predictor` (pas 0) ne peut pas les connaître : sans cette re-capture, un trait
    # accordé après le déploiement resterait invisible à la prédiction pour TOUTE la bataille.
    _seed_measured_traits(predictor["ctx_by_id"], snap)


def _seed_condition_gated_owner_effects(eff_state, units, predictor) -> None:
    """Complète le seed PRÉDICTION des owner-effects posés à l'INIT d'un passif **et laissés INACTIFS
    par leur `CreateActiveCondition`** — donc invisibles du canal `decisionView` par DÉFAUT, qui ne
    publie que les effets à `EffectComponent.IsActive` vrai (`readEffectsByUnit`,
    `frida/hooks/game/effects.ts`). case-322.

    Mirror de la boucle ABILITIES d'`IdunBattle.Operations.InitializeActorAbilitiesOperation$$Execute`
    -> `<Ability>.CreateBehaviour` -> `AddEffect(owner)` (table
    `effects.factory.ABILITY_INIT_OWNER_EFFECTS`, déjà consommée côté COMBAT par
    `runner/operations/spawn.py::_owner_effects_from_abilities`). C'est ici son pendant DÉCISION, qui
    manquait : la Scene de prédiction re-seede son `EffectsState` à CHAQUE pas depuis `dv`, sans
    passer par le spawn.

    DEUX GARDES, et la seconde a été posée par une RÉGRESSION MESURÉE :

    * `active_condition_ported` — **seules** ces classes sont matérialisées. Pour toutes les autres,
      l'absence du canal par défaut et le flag capté disent la MÊME chose (l'effet ne contribue pas),
      et les faire entrer changerait `EffectsState.has_effect` sans qu'aucune mesure ne l'ait
      demandé. Les trois autres entrées conditionnelles de la table
      (`AnvilShield_BlockChanceBelowHealthCap`, `HammerOfWrath_ConditionalDamage`,
      `HypersensoryAbilities_MinimalHealth`) restent donc HORS de ce chemin.
    * `seed_witness_effect` — le porteur doit porter le TÉMOIN, c'est-à-dire l'effet FRÈRE posé par
      la MÊME expression `CreateBehaviour` et inconditionnel. C'est le substrat d'**ENTITÉ**.
      La première version lisait `GC.unit(vid).passiveAbilities` — le KIT — et le contre-bras de
      #312 (seed BC avec `PassiveAbilities: []`) l'a prise en faute : le port accordait le bonus à
      une Kimm qui N'A PAS le passif en bataille (sur-prédiction mesurée jusqu'à **+2806** sur la
      tuile (4,0), là où natif == port avant le portage). Même piège que #264 côté traits.

    Idempotent : `has_effect` skippe ce que le canal a déjà publié (l'unité a bougé -> l'effet est
    actif -> capté -> aucune 2e instance)."""
    seedable = [(n, k) for names in ABILITY_INIT_OWNER_EFFECTS.values() for n in names
                for k in (EFFECT_CLASSES.get(n),)
                if k is not None and getattr(k, "active_condition_ported", False)
                and getattr(k, "seed_witness_effect", None)]
    if not seedable:
        return
    # case-366-r1 : le MEME triple `(mult, passif, ACTIF)` que `EffectsState.seed` consomme --
    # calcule UNE fois, pas par unite.
    states = _effect_source_ability_states(predictor)
    for u in units:
        uid = u.get("id")
        for name, klass in seedable:
            if not eff_state.has_effect(uid, name=klass.seed_witness_effect):
                continue                                      # l'ENTITE n'a pas le passif
            if eff_state.has_effect(uid, name=name):
                continue                                      # deja publie par le canal
            etype = EffectType.__members__.get(name)          # l'entite-effet native porte @+0x58
            eff = EffectFactory.create(
                {"name": name, "effectType": (int(etype) if etype is not None else None),
                 "remaining": 0, "source": uid},              # rem 0 -> permanent (owner-effect)
                ability_variables_multiplier=int(predictor["mult_by_id"].get(uid, 100) or 100),
                ability_level=predictor["ablvl_by_id"].get(uid),
                # case-366-r1 : le niveau de l'ACTIVE, LU du meme triple que `EffectsState.seed`
                # -- un owner-effect est pose par SON porteur, donc c'est bien l'etat de `uid`.
                active_ability_level=(states.get(uid) or (None, None, None))[2])
            eff.target = uid
            eff_state.add_effect(uid, eff)


def _effect_source_ability_states(predictor) -> dict:
    """`{entity_id: (multiplier, passiveAbilityLevel, activeAbilityLevel)}` pour
    `EffectsState.seed` — l'état d'ability consulté par la **SOURCE** de chaque effet, pas par son
    porteur (le natif BAKE l'`AbilityStateReference` du caster dans l'entité-effet à la pose ; cf.
    `engine.entities.effects_state.baked_ability_state`). PENDANT EXACT, sur le seam de PRÉDICTION,
    de la passe 1 de `runner/snapshot.py::_load_stats_and_effects` sur le seam COMBAT.

    Domaine = les entités dont le `unitConfig` a réellement été lu (`mult_by_id`), donc les
    `EntityType.Unit`. Une MACHINE en est ABSENTE volontairement : son `unitConfig` est en erreur
    (`{"error": "visualId introuvable"}`), son état vit dans `abstate_by_id` PAR ABILITY, et rien
    ici ne dit QUELLE ability a posé l'effet — l'inclure avec le neutre `(100, None, None)` serait
    PIRE que le repli. Une MoW-source retombe donc sur le porteur, à l'identique d'avant."""
    ctx_by_id = predictor.get("ctx_by_id") or {}
    ablvl = predictor.get("ablvl_by_id") or {}
    out = {}
    for eid, mult in (predictor.get("mult_by_id") or {}).items():
        c = ctx_by_id.get(eid)
        actl = int(getattr(c, "active_ability_level", 0) or 0) if c is not None else 0
        out[int(eid)] = (int(mult or 100), ablvl.get(eid) or None, actl or None)
    return out


def step_context(predictor, dv):
    """État COURANT du pas (hp/pos/team + effets matérialisés seed) — reconstruit à chaque pas car
    l'état mute. (Ex-`PV.step_context`.)

    #360 — les tables PAR ID couvrent AUSSI les MACHINES OF WAR (`dv.mows`). `decisionView.units`
    ne contient jamais de Machine (canal `.mows` séparé, mirror de `EntityExtensions$$IsMachine`),
    si bien que `scene.team(<MoW>)` rendait `None` pour TOUT caster MoW — et un sélecteur porté qui
    commence par `if scene.team(caster) is None: return False` se dégradait alors en NÉGATIF.

    MESURÉ (`probe_360_mow_caster_oracle.py --step c`, `blackForgefiend` / `1148 DaemonicOrdnance`,
    zone EN FEU après un cast de la MoW elle-même) : natif `(3, 3, 3)` contre port `aucun event`.
    Sous-prédiction MUETTE — ni erreur ni crash — symétrique de la sur-prédiction que `#350-r3`
    avait fermée sur le même sélecteur, et invisible tant que l'ability était mesurée par GREFFE
    sur une unité (qui, elle, a une équipe).

    Purement ADDITIF : aucune clé existante n'est réécrite (les ids de Machine sont disjoints de
    ceux de `.units`), et `units` reste `dv.units` — les consommateurs qui COMPTENT des unités
    (ex. `_enemy_psykers_alive`) ne voient donc aucun changement. `pos` n'est versée que si la
    ligne en porte une : une MoW est off-board et n'a pas de `PositionComponent`.

    #443-r2-b1 — LE CANAL DE SEED. `dv` accepte les DEUX canaux de `readEffectsByUnit`, exactement
    comme `runner/snapshot.py::load_state` côté COMBAT, et la porte est la MÊME
    (`snapshot.decision_view_seed_body`). Capté par elle, `EffectsState` reçoit AUSSI les effets
    POSÉS mais INERTES avec leur flag : `has_effect` les voit (mirror des call-sites
    `HasEffect(..., onlyActive = 0)`) et ils restent HORS d'`active_effects`, donc ils ne
    contribuent à aucun nombre. Capté par le canal NU, ils sont simplement absents — comportement
    d'avant #443-r2-b1, où la face DÉCISION perdait **35** points d'utilité de paire sur un
    overwatch `1009` désarmé (le poids BC `SUPPRESSIVEFIRE_TargetWithOverwatch`).

    La clé `units` rendue est, elle, PROJETÉE ACTIF-ONLY (`snapshot.active_only_rows`) : c'est le
    substrat des lecteurs de la liste BRUTE (`Scene.units[].effects`), qui n'ont pas de flag à
    consulter. Ils restent donc INDÉPENDANTS DU CANAL — même discipline que `snapshot._effect_names`
    sur la face COMBAT. Sur un `dv` du canal nu la projection est l'IDENTITÉ (aux lignes près, qui
    ne sont même pas copiées)."""
    units = dv.get("units") or []
    mows = dv.get("mows") or []
    # #999-r3-r1-r1 -- LES EFFETS DES MACHINES OF WAR ENTRENT DANS LE SEED. Le canal EXISTE et il
    # est publie : `frida/hooks/features/ai-step/rpc-decision.ts` assemble
    # `mows: mows.map((m) => ({ ...m, effects: effectsByUnit.get(m.casterId) ?? [] }))` -- c'est le
    # MEME `readEffectsByUnit(statePtr, { includeInactive })` que pour `units`, keye par
    # `casterId = machineId`. (⚠ `projectMowsFull` seul ne porte AUCUN champ `effects` : le
    # rattachement se fait au site d'ASSEMBLAGE du RPC. Conclure du projecteur que le canal n'existe
    # pas serait un faux negatif -- verifie.)
    # Le port, lui, seedait `{u["id"]: u.get("effects")}` sur `units` SEULEMENT, si bien qu'un
    # owner-effet d'AURA porte par une MoW (1442 `BlightedLand`, 1443 `ContemptuousDisregard`,
    # 1445 `WisdomOfTheAncients`, 1449 `MoreGitzOverEre`, 1494 `CabalOfSorcerers`,
    # 1548 `GuardianConstruct`) n'existait PAS cote DECISION -- degradation MUETTE, symetrique
    # exacte du filtre positionnel de la face COMBAT.
    # Purement ADDITIF : les ids de Machine sont DISJOINTS de ceux de `.units` (meme fait que #360
    # exploite deja pour `hp_by_id` / `team_by_id` juste en dessous), donc aucune cle existante
    # n'est reecrite.
    _effects_by_id = {u["id"]: (u.get("effects") or []) for u in units}
    for _m in mows:
        _mid = _m.get("casterId")
        if _mid is not None and _mid not in _effects_by_id:
            _effects_by_id[_mid] = _m.get("effects") or []
    eff_state = EffectsState.seed(
        _effects_by_id,
        predictor["mult_by_id"], predictor["ablvl_by_id"],
        # Le triple porte AUSSI `activeAbilityLevel` (lu du `ctx`), et `EffectsState.seed` s'en sert
        # desormais pour le PORTEUR en repli, pas seulement pour la SOURCE (case-366-r1) : c'est le
        # MEME canal que la face COMBAT (`snapshot.abstate_by_id`), donc pas de fork.
        _effect_source_ability_states(predictor))
    _seed_condition_gated_owner_effects(eff_state, units, predictor)
    hp_by_id = {u["id"]: u.get("hp") for u in units}
    pos_by_id = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in units if u.get("pos")}
    team_by_id = {u["id"]: u.get("team") for u in units}
    for m in mows:
        # `casterId` = `machineId` = l'`EntityType.Machine` (cf. `projectMowsFull`) : la MÊME clé
        # que `context.machine_row` et que les RPC de prédiction.
        mid = m.get("casterId")
        if mid is None:
            continue
        hp_by_id[mid] = m.get("hp")
        team_by_id[mid] = m.get("team")
        if m.get("pos"):
            pos_by_id[mid] = (m["pos"]["col"], m["pos"]["row"])
    return {
        "units": active_only_rows(units),
        "hp_by_id": hp_by_id,
        "pos_by_id": pos_by_id,
        "team_by_id": team_by_id,
        "eff_state": eff_state,
        "feet_by_id": _feet_by_id(units, mows),
        # #1036-r2 -- NATURE D'ENTITE (cf. `Scene.machine_ids`). Le canal `.mows` est SEPARE de
        # `.units` par construction native (`decisionView.units` ne contient jamais d'
        # `EntityType.Machine`), donc l'appartenance a `.mows` EST la mesure d'`IsMachine`. Un
        # `frozenset()` vide est une MESURE (etat sans MoW), pas une absence de canal.
        "machine_ids": frozenset(m["casterId"] for m in mows if m.get("casterId") is not None),
    }


def _feet_by_id(units, mows) -> dict:
    """{id: [(col,row), ...]} depuis `decisionView` -- capteur `#419-r1-tr10-r2`.

    UNITES : la cle `feet`, mirror d'`IdunBattle.Entities.EntityExtensions$$GetTiles(entity,
    state)`. TRI-ETAT cote hook (`null` = capteur muet, `[]` = mesure vide) ; ici les deux mènent
    au MEME repli (aucune entree posee), donc `iterate_tiles` retombe sur la MainTile.

    MACHINES OF WAR : `EntityExtensions.<IterateTiles>d__17$$MoveNext` teste TROIS types d'entite
    (pied -> sa tuile ; tuile -> elle-meme ; unite -> ses pieds) et sort FAUX pour tout le reste --
    une `EntityType.Machine` n'est aucun des trois, donc `feet` peut valoir `[]` sans que rien
    n'ait echoue. L'empreinte reelle d'une MoW est l'ensemble des `MachinePlatform` qui la portent,
    que le hook publie sous `platformTiles`. On prend `feet` s'il est non vide, `platformTiles`
    sinon -- jamais l'inverse : la mesure native prime sur la derivation.

    La cle est `casterId` (== `machineId`, l'`EntityType.Machine`), la MEME que `pos_by_id` et que
    tous les RPC de prediction -- pas `id`, qui est la PLATEFORME d'ancrage."""
    out: dict = {}
    for u in (units or []):
        uid = u.get("id")
        feet = u.get("feet")
        if uid is None or not feet:
            continue
        out[int(uid)] = [(int(f["col"]), int(f["row"])) for f in feet if isinstance(f, dict)]
    for m in (mows or []):
        mid = m.get("casterId")
        if mid is None:
            continue
        tiles = m.get("feet") or m.get("platformTiles")
        if not tiles:
            continue
        out[int(mid)] = [(int(t["col"]), int(t["row"])) for t in tiles if isinstance(t, dict)]
    return {k: v for k, v in out.items() if v}
