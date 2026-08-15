"""ECS — état de bataille (entités + composants).

Port FIDÈLE au niveau SÉMANTIQUE de l'ECS natif (PAS du layout mémoire octet par
octet — inutile pour la fidélité comportementale) :
  • Native : entité = table de composants `entity+0xb0` {typeToken, slot}, count
    `+0x12e`, base `+0x138` ; ajout `Entity$$IdunBattle.Core.Entity$$AddComponent.
  • Python : `Entity` = id + dict {type_de_composant -> instance}.

`Component` = classe de base ; chaque composant concret (UnitFootComponent,
EffectsOwnedComponent, TriggeredAbilityComponent, ActiveAbilityComponent, …) sera
porté avec ses champs exacts RE'd, au fil des tranches.

⚠ TODO (tâche #23) : RE de la struct Entity native + des composants (layout/champs
exacts) avant de figer les composants concrets. Ce fichier ne pose que les
primitives génériques (Entity/Component/State) dont la sémantique est confirmée.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, Optional, TypeVar

if TYPE_CHECKING:
    from ..entities.effects_state import EffectsState
    from .prng import IntBasedMersenneTwister

C = TypeVar("C", bound="Component")


class Component:
    """Base de tout composant ECS. Les composants concrets en héritent avec leurs
    champs exacts (RE'd, VA citée dans chaque sous-classe)."""
    __slots__ = ()


class Entity:
    """Entité ECS = id + composants typés (mirror Entity$$IdunBattle.Core.Entity$$AddComponent)."""
    __slots__ = ("id", "_components")

    def __init__(self, entity_id: int):
        self.id = entity_id
        self._components: dict[type, Component] = {}

    def add_component(self, comp: Component) -> Component:
        """mirror Entity$$IdunBattle.Core.Entity$$AddComponent (1 composant par type)."""
        self._components[type(comp)] = comp
        return comp

    def get_component(self, comp_type: type[C]) -> Optional[C]:
        return self._components.get(comp_type)  # type: ignore[return-value]

    def has_component(self, comp_type: type) -> bool:
        return comp_type in self._components

    def remove_component(self, comp_type: type) -> None:
        self._components.pop(comp_type, None)

    def __repr__(self) -> str:
        names = ",".join(t.__name__ for t in self._components)
        return f"Entity(#{self.id}: {names})"


class State:
    """État de bataille = ensemble d'entités + méta (tour/joueur courant).

    `current_player_id` mirror `StateExtensions.GetCurrentPlayerId(state)` (lu par
    IdunRunner.Apply). Les requêtes riches (par owner, par tuile, vivantes, …) seront
    ajoutées au fil des tranches en miroir de `IdunBattle.Entities.*Extensions`.

    `effects` = état STRUCTURÉ + évoluable des effets actifs (`EffectsState`, instances
    `BaseEffect` par unité), peuplé par `load_state` quand un `combatSnapshot` est fourni
    (sinon None ; l'identité reste en NOMS via `EffectsOwnedComponent` pour le diff).
    Source des modifiers de dégât (couche `engine.entities.effects`).

    `rng` = RNG de combat du runner (`IntBasedMersenneTwister`). Pour un replay-diff
    bit-exact vs live, on le CALE sur l'état MT live (`dumpRng`) avant de rejouer un
    message qui tire (attaque). None tant qu'aucun RNG n'est posé.

    `board` = graphe hex (`engine.entities.pathfinding.board.Board`) optionnel, posé pour
    les mécaniques qui ont besoin de l'ADJACENCE hex (ex. splash Psyker = ennemis adjacents
    à la cible). None = pas d'adjacence dispo → ces mécaniques dégradent en no-op.

    `turn_counts` = nb de tours DÉMARRÉS par joueur (mirror `TurnComponent.turnsStartedByCurrentPlayer`,
    dict @+0x38) ; incrémenté par `turnflow.set_current_player`, mirror de son écrivain natif UNIQUE
    `TurnComponent$$SetCurrentPlayer` — donc par ChangeTurn, PAS par StartTurn, qui ne fait que le
    LIRE (#287-r11-r1-r1-r1-r1). Source de `GetAmountOfTurnsStartedByCurrentPlayer`
    (gate « 1er tour » de certaines mécaniques). Vide tant qu'aucun tour n'a été joué via le runner.

    `turns_ended` = nb de tours TERMINÉS par joueur (mirror `TurnComponent.<Dictionary @+0x40>`,
    `GetAmountOfTurnsEndedByPlayer`) — le JUMEAU du précédent, jamais son synonyme : les deux sont
    écrits par la même fonction native (`TurnComponent$$SetCurrentPlayer`) mais sur deux joueurs
    DIFFÉRENTS (sortant / entrant). Écrivain porté : `turnflow.set_current_player`.

    `pending_deaths` / `draining_deaths` = la FILE DE MORTS de `MatchState` et le verrou de
    ré-entrance de `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` (case-haze-ord) :
    `RecordKillOperation` ENQUEUE, `VerifyDeaths` DRAINE une mort à la fois. Détail au point
    d'initialisation ci-dessous.

    `turn_order_player_count` = nb de joueurs du `BC.Player.TurnOrder` dont `PlayerComponent+0x20 != 2`
    (Environment exclu) — le FACTEUR de `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (`count * rounds`),
    donc l'unité de TOUTE durée d'effet exprimée en ROUNDS. Seedé par `load_state` ; None = inconnu →
    `convert_rounds_to_turns` retombe sur l'identité."""
    __slots__ = ("entities", "current_player_id", "_next_entity_id", "effects", "rng", "board",
                 "turn_counts", "turns_ended", "turn_order_player_count", "triggering_ability",
                 "trigger_ability_type",
                 "pending_deaths", "draining_deaths", "ability_states_seed",
                 "pending_triggered_abilities", "draining_pending_abilities",
                 # #443-r2-b2 -- la file `IMatchState` slot 7 (`GetDamageEvents`) et son garde de
                 # re-entrance. MEME forme que le couple ci-dessus.
                 "pending_damage_events", "draining_damage_events",
                 "enable_obscuring_terrain", "unit_flags_seed",
                 # #999-r3-r2 -- rapport de la passe `snapshot._load_unit_rarity` (compte par
                 # BLOC + etat du canal `unitsNotAlive`). MEME tri-etat que `unit_flags_seed` :
                 # `units_not_alive: None` = canal NON mesure, jamais un zero.
                 "unit_rarity_seed",
                 "damage_spread_percentage", "ignore_damage_spread",
                 # #449-r2-r4-r4 -- les autres champs de `BC.Damage` que le port CONSOMME.
                 # Meme nature et meme canal que les deux ci-dessus : la table `DAMAGE_FIELDS`
                 # de `engine.services.damage_config` porte, pour chacun, l'offset natif et le
                 # symbole du consommateur qui le lit.
                 "elevation_bonus", "trench_reduction_percentage",
                 "ranged_in_melee_reduction_percentage", "knockback_percentage",
                 "armor_percentage", "allow_overkill", "overkill_dmg_pct_of_health",
                 "damaged_machine_destroy_chance_increase",
                 # #287-r11-r1-r1 -- `BC.Victory.VictoryConditions`, le dictionnaire que
                 # `IdunBattle.Core.Services.BattleQuery$$GetMaxRounds` interroge a la cle
                 # `VictoryConditionType.MainPlayerRoundLimitation`.
                 "victory_conditions",
                 # #550-r1 -- la RESERVATION de tuile, `TileContentComponent+0x34`
                 # (`Nullable<int>`). Cf. le commentaire au point d'initialisation.
                 "tile_reservations")

    def __init__(self):
        self.entities: dict[int, Entity] = {}
        self.current_player_id: Optional[int] = None
        self._next_entity_id = 1
        self.effects: Optional["EffectsState"] = None
        self.rng: Optional["IntBasedMersenneTwister"] = None
        self.board = None
        # `IdunBattle.Configuration.TargetingConfiguration.EnableObscuringTerrain` (#444) -- le champ
        # `+0x10` de l'objet `config` que `IdunBattle.Core.Services.TargetingQuery$$Init` range en
        # `this+0x30`, et le TOUT PREMIER gate de
        # `IdunBattle.Core.Services.TargetingQuery$$GetTilesObscuringTerrain` : a faux, la ligne de
        # vue rend un set VIDE et ne refuse jamais rien.
        #
        # AUCUN RPC NE LE PUBLIE -- ce n'est ni un etat dynamique ni un composant d'entite, c'est un
        # champ de la BATTLE CONFIGURATION (`BC.Targeting`). Le defaut `True` n'est donc pas une
        # deduction : c'est la valeur LUE dans `data/seed-bc.json` (`Targeting.EnableObscuringTerrain
        # = true`), la seed dont partent tous les runners `rl_duel build`, et
        # `tests/engine/runner/test_obscured_targeting_live.py` la RE-LIT pour rougir si elle change.
        # `load_state(targeting_config=...)` permet a un appelant qui connait SA BC de la poser.
        self.enable_obscuring_terrain: bool = True
        # `BattleConfiguration.Damage` -- les DEUX champs de la VARIANCE de degat (#449-r2-r4).
        # Natif : `IdunBattle.Runner.IdunRunner$$Initialize` passe `BattleConfiguration.Damage` a
        # `IdunBattle.Core.Services.DamageCalculations$$Init` (range en `DamageCalculations+0x18`),
        # d'ou `$$get_DamageSpreadPercentageFix64` lit `configuration+0x20` et
        # `IdunBattle.Core.Services.DamagePrediction$$get_IgnoreDamageSpread` lit `configuration+0x31`.
        # C'est donc un etat de la BATAILLE, pas une constante -- et le port le codait en dur a 20.
        # `None` = canal non fourni (aucun `load_state(damage_config=...)`) -> le foyer
        # `engine.services.damage_config.resolve_spread_pct` retombe sur le defaut DERIVE de
        # `data/seed-bc.json`. AUCUN chemin ne fabrique un 20 en dur.
        self.damage_spread_percentage: Optional[int] = None
        self.ignore_damage_spread: bool = False
        # #449-r2-r4-r4 -- meme regle pour toute la section : `None` = canal non fourni, et le
        # foyer `damage_config.resolve_damage_field` retombe alors sur le defaut DERIVE de
        # `data/seed-bc.json`. AUCUN chemin ne fabrique ici un litteral (ni 50, ni 20, ni 1).
        self.elevation_bonus: Optional[int] = None
        self.trench_reduction_percentage: Optional[int] = None
        self.ranged_in_melee_reduction_percentage: Optional[int] = None
        self.knockback_percentage: Optional[int] = None
        self.armor_percentage: Optional[int] = None
        self.allow_overkill: Optional[bool] = None
        self.overkill_dmg_pct_of_health: Optional[int] = None
        self.damaged_machine_destroy_chance_increase: Optional[int] = None
        # #287-r11-r1-r1 -- `BattleConfiguration.Victory.VictoryConditions`, MEME nature que
        # `enable_obscuring_terrain` et `BC.Damage` : un champ de la BATTLE CONFIGURATION, qui vit
        # sur DISQUE et qu'AUCUN RPC ne publie. Le natif range la `victoryConfig` en
        # `BattleQuery+0xb0` (14e parametre NOMME de `BattleQuery$$Initialize`) et son dictionnaire
        # `+0x18` est ce que lit `BattleQuery$$GetMaxRounds` a la cle
        # `VictoryConditionType.MainPlayerRoundLimitation`.
        # TRI-ETAT STRICT : `None` = canal NON FOURNI -> le defaut DERIVE de `data/seed-bc.json`
        # s'applique (`engine.services.victory_config`) ; `{}` = la BC a parle et ne pose AUCUNE
        # condition. Les deux ne se confondent pas -- seule la seconde est une MESURE.
        self.victory_conditions: Optional[dict] = None
        # #550-r1 -- RESERVATION de tuile. Le natif la porte SUR LA TUILE
        # (`TileContentComponent.<+0x34> : Nullable<int>` = l'id de l'unite qui a reserve) ; le port
        # n'a pas d'entite-tuile, donc elle vit ici, en `dict[(col,row) -> unit_id]`. L'ABSENCE
        # d'une cle EST le `Nullable` vide -- aucune valeur `None` n'est jamais stockee.
        # Ce n'est PAS derivable de l'occupation : une tuile reservee est libre, et c'est justement
        # ce qui la distingue. Ecrivains/lecteurs portes, tous mirrors nommes :
        # `operations/tile_reservation.py` (les cinq `TileExtensions$$*` + l'agregateur
        # `BattleQuery$$IsTileReservedForAnotherUnit`).
        # `{}` = mesure (aucune reservation), jamais « pas su lire » : le natif part lui aussi d'un
        # `Nullable` vide sur chaque tuile.
        self.tile_reservations: dict = {}
        self.turn_counts: dict[int, int] = {}
        # #287-r11-r1-r1-r1 -- `TurnComponent.<Dictionary @+0x40>`, les tours **TERMINES** par
        # joueur, que rend `IdunBattle.Entities.Components.TurnComponent$$GetAmountOfTurnsEndedByPlayer`.
        # C'est le JUMEAU de `turn_counts` (`+0x38`, tours DEMARRES) et il ne s'y substitue pas :
        # les deux dictionnaires sont ecrits par la MEME fonction
        # (`IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer`, ecrivain UNIQUE des
        # deux) mais sur deux joueurs DIFFERENTS -- `ended[SORTANT] += 1` et `started[ENTRANT] += 1`.
        # Ecrivain porte : `turnflow.set_current_player`. Seed : `snapshot._load_turns_ended`.
        # Lecteur : `engine.services.battle_query.get_amount_of_turns_ended_by_player`, appele par
        # `has_minimum_remaining_turns` (bit 52 `CasterHas2TurnsLeft`).
        # Cle ABSENTE = 0 -- c'est la branche `!ContainsKey` du natif, pas un zero fabrique.
        self.turns_ended: dict[int, int] = {}
        # #101 : le fait "a bouge ce tour" N'EST PLUS un set d'etat ici — il vit ou le natif le met, dans
        # le `UnitFlagsComponent` de l'unite (`UnitFlag.Moved=0`), pose par `set_moved_flag`
        # (`IdunBattle.Entities.UnitExtensions$$SetMovedFlag`, appele par MoveUnitOperation) et purge par
        # `RemoveTurnFlags(new_activation=1)` du StartTurnOperation (PAR JOUEUR ENTRANT). Lecteur unique :
        # `components.unit_has_moved`. (#60 avait introduit un set `moved_this_turn` PARALLELE : jamais
        # seede sur un etat recharge par `load_state`, jamais lu par les autres consommateurs du flag,
        # et reset GLOBALEMENT au lieu de per-joueur.)
        # #90/#98 : nb de joueurs du `BC.Player.TurnOrder` de `PlayerType != 2` (Environment exclu) —
        # le FACTEUR de `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (`count * rounds`). Seede par
        # `load_state` depuis `observeBattle.counts.player` (moins l'unique joueur Environment
        # permanent) ; None = canal absent -> `convert_rounds_to_turns` retombe sur l'identite (etats
        # construits a la main dans les tests unitaires : comportement historique preserve).
        self.turn_order_player_count: Optional[int] = None
        # L'`AbilityOrEffect` de la TRIGGERED-ABILITY en cours d'execution.
        #
        # NOM HISTORIQUE, semantique RELUE (case-292) : ce canal mirror le champ natif
        # **`CurrentAbility`** (`AbilityEntities+0x60`), celui que lit
        # `IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs` -- et NON le champ homonyme
        # `TriggeringAbility` (`AbilityEntities+0x98`, lu par `$$TriggeringAbilityIs`).
        # `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` ecrit
        # `Nullable<AbilityOrEffect>(ability.Id @ability+0x10)` dans les DEUX, mais a des moments
        # differents : `+0x60` **AVANT** l'appel du behaviour (donc herite par tout ce qu'il engendre --
        # attaque, degat, mort) et `+0x98` **APRES**, pour le seul `On(0xd = UnitTriggeredAbility)`.
        # Le port pose/restaure autour d'`execute_behaviour` -> c'est exactement `+0x60`.
        # Foyer UNIQUE de l'ecriture : `triggers/dispatch/core.py::evaluate_trigger_operation`.
        # None = hors triggered-ability (attaque normale, active castee) -> aucun gate de kind ne fire.
        # PORTEE PARTIELLE ASSUMEE : seules les classes qui declarent `TRIGGERED_ABILITY_ID` alimentent
        # ce champ ; les autres le laissent a None (degradation permissive sur un `NOT CurrentAbilityIs`,
        # restrictive sur un gate positif).
        # ⚠ CE CANAL EST VIDE PENDANT TOUT LE VECTEUR MORT (#301) : `IdunBattle.Operations.
        # KillUnitOperation$$Execute` memset son `AbilityEntities` et n'y reecrit QUE `+0x98`, donc
        # `+0x60` reste a zero sur `On(0)/On(1)/On(2)/On(53 = PostUnitKill)/On(54 = UnitDefeated)`. `operations/damage.py::
        # _verify_deaths` force donc `None` ici et pose le `killTrigger` sur `trigger_ability_type`.
        # Le consommateur `FuelledByFury` (`TriggeringAbilityIs(0x400)`) est sur `On(3)`, emis AVANT
        # le drain par `IdunBattle.Operations.RecordKillOperation$$Execute` via la voie universelle
        # `Core.Services.OperationProcessor$$EvaluateAbilities`, qui ecrit `+0x60` ET `+0x98` avec LA
        # MEME ability -> lire l'un ou l'autre y est equivalent (residu nomme, sans consequence).
        # Detail + regimes examines : `docs/rl/case-292-current-vs-triggering-ability.md`.
        # ⚠ LE CHAMP `TriggeringAbility` (+0x98) EXISTE MAINTENANT COTE PORT : c'est
        # `self.trigger_ability_type`, juste en dessous. Une ability qui porte un noeud
        # `TriggeringAbilityIs` / `TriggeringEffectIs` / `TriggeringAbilityIsNone` sur un
        # `On(0xd = UnitTriggeredAbility)` doit lire CELUI-LA, pas celui-ci.
        self.triggering_ability: Optional[int] = None
        # ── SECOND canal (#294) : le champ natif `TriggeringAbility` (`AbilityEntities+0x98`) ─────
        #
        # NE PAS CONFONDRE AVEC LE CANAL CI-DESSUS. Ce sont deux champs natifs DISTINCTS, ecrits par
        # la MEME fonction (`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute`) mais a
        # deux MOMENTS differents, et lus par deux slots `DSLSelectors` differents :
        #
        #   | champ natif        | offset | ecrit                  | slot DSL | predicats                       |
        #   |--------------------|--------|------------------------|----------|---------------------------------|
        #   | `CurrentAbility`   | +0x60  | AVANT le behaviour     | +0x88    | `CurrentAbilityIs`              |
        #   | `TriggeringAbility`| +0x98  | APRES le behaviour     | +0x90    | `TriggeringAbilityIs`,          |
        #   |                    |        |                        |          | `TriggeringEffectIs`,           |
        #   |                    |        |                        |          | `TriggeringAbilityIsNone`,      |
        #   |                    |        |                        |          | `TriggeringAbilityIsNormalAttack`|
        #
        # Lecteurs VERIFIES du +0x98 : `IdunBattleLogic.Entities.AbilityTypeSelector.TriggeringAbilitySelector$$Select`
        # (lit `+0x98/+0xa0/+0xa8/+0xb0`) et `IdunBattle.Entities.Abilities.AbilityEntities$$get_TriggerAbilityType`.
        # D'ou le nom de CE canal : `trigger_ability_type`, celui du getter natif -- deliberement
        # DISSEMBLABLE de `triggering_ability` (le canal +0x60, dont le nom Python est historique).
        #
        # SEMANTIQUE PROPRE (ecrivain 4) : ecrit APRES `execute_behaviour`, il ne couvre QUE
        # l'emission d'`On(0xd = EventTriggerType.UnitTriggeredAbility)` qui suit immediatement. Il
        # n'est donc PAS herite par ce que le behaviour engendre -- c'est exactement ce qui le separe
        # de `CurrentAbility`. Pendant le behaviour d'une triggered B declenchee par cet `On(0xd)` :
        # `+0x60` vaut B (B vient de l'y ecrire) et `+0x98` vaut A (la triggered qui a publie) ->
        # DEUX valeurs NON NULLES DIFFERENTES. Montage : `probe_294_trigger_ability_channels.py`.
        #
        # SECONDE SEMANTIQUE, DEPUIS #301 (ecrivain 2) : le VECTEUR MORT. `IdunBattle.Operations.
        # KillUnitOperation$$Execute` construit son `AbilityEntities` par un memset de 0x128 puis
        # n'y reecrit QUE `+0x00/+0x08` (killer), `+0x10` (killed), `+0x38/+0x48` (tuiles) et le bloc
        # `+0x98..+0xb4` copie de `KillUnitOptions+0x04` -- et publie CETTE MEME struct, non remodifiee,
        # sur `On(1)`, `On(2)`, `On(0)`, `On(54 = UnitDefeated)` puis `On(53 = PostUnitKill)`. Ce canal y porte donc le `killTrigger`
        # de la file de morts pendant tout le drain (`operations/damage.py::_verify_deaths`), et
        # `triggering_ability` (`+0x60`) y est VIDE. Montage :
        # `probe_301_kill_unit_trigger_channels.py`.
        #
        # ⚠⚠ COUVERTURE DU CANAL -- A LIRE AVANT DE S'EN SERVIR. Le natif a QUATRE ecrivains de
        # `+0x98`, et le port n'en modelise QU'UN (le 4e). Les trois autres sont des RESIDUS NOMMES,
        # pas des oublis (RE #294, recoupee au decompile ; detail et priorites dans
        # `docs/rl/case-292-current-vs-triggering-ability.md` §7) :
        #
        #   1. `Core.Services.OperationProcessor$$EvaluateAbilities(actor, caster, target,
        #      [casterTiles, targetTiles,] trigger, ability [, previousResult, wasCrit])` -- LA voie
        #      universelle : elle ecrit `+0x60` ET `+0x98` avec LA MEME `ability`, et `+0x7c` a
        #      `default`. C'est par elle que passe le vecteur MORT-pending (`On(3)`).
        #      NON MODELISE -- sans consequence tant que les deux valent la meme chose.
        #   2. `IdunBattle.Operations.KillUnitOperation$$Execute` -- ecrit `+0x98` DIRECTEMENT
        #      (`KillUnitOptions+0x04`) et laisse `+0x60` a ZERO, pour `On(0)/On(1)/On(2)/On(53 = PostUnitKill)/On(54 = UnitDefeated)`.
        #      **PORTE DEPUIS #301** : `operations/damage.py::_verify_deaths` pose le `killTrigger` de
        #      la file ICI et force `triggering_ability` (+0x60) a `None` le temps du drain. Le port
        #      faisait l'inverse (valeur sur `+0x60`, `+0x98` vide) -- divergence PERMISSIVE fermee.
        #   3. `IdunBattle.Operations.AddEffectOperation$$Execute` -- `+0x60` = `+0x98` =
        #      `AbilityOrEffect(effectType)`, pour `On(61 = PreEffectAdded)/On(62 = EffectAdded)/On(70 = UnitBecameUntargetable)`. NON MODELISE.
        #      (Symetrique NEGATIF, contre-intuitif : `IdunBattle.Operations.RemoveEffectOperation$$Execute`
        #      n'ecrit QUE `+0x60` et laisse `+0x98` a zero -> sur `On(63 = PreEffectRemoved)/On(64 = EffectRemoved)` c'est
        #      `CurrentAbilityIs` qui porte l'effet, pas `TriggeringEffectIs`.)
        #   4. `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` -- LE SEUL PORTE ICI.
        #
        # => Un futur noeud `TriggeringAbilityIs` / `TriggeringEffectIs` sur un evenement AUTRE que
        # `On(0xd)` et que les cinq de la mort ne doit PAS se contenter de lire ce canal : il faut
        # d'abord porter l'ecrivain correspondant (1 ou 3). Sur `On(0xd)` et sur le vecteur MORT, ce
        # canal est exact.
        #
        # DEUX foyers d'ecriture, et deux seulement : `triggers/dispatch/core.py::
        # _publish_unit_triggered_ability` (ecrivain 4, fenetre `On(0xd)`) et
        # `operations/damage.py::_verify_deaths` (ecrivain 2, duree d'un `KillUnitOperation`).
        # None = hors de ces deux fenetres.
        self.trigger_ability_type: Optional[int] = None
        # case-haze-ord -- la FILE DE MORTS du natif. `IdunBattle.Operations.RecordKillOperation$$
        # Execute` n'applique PAS la mort : il pose `UnitFlag.PendingDeath (0xf)`, appelle
        # `IdunBattle.Core.MatchState$$AddDeath(killer, killed, killTrigger, attackTrigger,
        # AttackRangeType)` -- qui ENQUEUE -- puis publie `On(PendingDeathAdded = 3)`. La file n'est
        # DRAINEE que par `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` (`RunPhase(PhaseType.ProcessDeaths /*0xc*/)` ->
        # lambda `<VerifyDeaths>b__0` -> `Core.Services.OperationProcessor$$KillUnit` ->
        # `IdunBattle.Operations.KillUnitOperation$$Execute`), UNE mort a la fois, tant que la file
        # n'est pas vide. Cote port, les deux foyers sont
        # `operations/damage.py::AttackDamageOperation._add_death` / `._verify_deaths`.
        #
        # Chaque entree porte le `killTrigger` LU DANS `KillUnitContext` au moment de l'enqueue
        # (`RecordKillOperation$$Execute` le recopie dans le `AddDeath`) : c'est lui que
        # `KillUnitOperation` rejoue dans le champ `TriggeringAbility` (`AbilityEntities+0x98`) des
        # evenements de mort, donc lui que comparent `TriggeringAbilityIs` / `TriggeringEffectIs`.
        # Cote port il est CAPTURE a l'enqueue depuis `state.triggering_ability` (l'ambiant, cf.
        # l'approximation nommee par case-292) et REPOSE sur `state.trigger_ability_type` le temps du
        # drain -- jamais sur `state.triggering_ability`, que le natif laisse VIDE la (#301).
        self.pending_deaths: list = []
        # Re-entrance de `VerifyDeaths` : une mort ENQUEUEE pendant un drain (nova, riposte, report
        # `HazeOfCorruption`) est traitee par le tour de boucle suivant, jamais AU MILIEU du
        # `KillUnitOperation` en cours -- ni au milieu du behaviour qui l'a causee.
        self.draining_deaths: bool = False
        # #406 -- la FILE DES TRIGGERED-ABILITIES DIFFEREES. STRICTEMENT le pendant de
        # `pending_deaths` ci-dessus, un cran plus haut : `IdunBattle.Entities.Behaviours.
        # TriggerAbilityDelayedBehaviour$$Execute` n'execute RIEN -- il resout son selecteur d'entite
        # puis appelle, PAR ENTITE, le slot 6 de l'interface du `state`
        # (`IdunBattle.Core.MatchState$$AddPendingTriggeredAbility(entity, triggeredAbilityType,
        # entities)`), qui fait un `Queue<T>.Enqueue` sur `MatchState+0x28`.
        #
        # La file n'est DRAINEE que par `IdunBattle.Messages.InputMessageProcessor$$
        # ProcessPendingTriggeredAbilities`, et ses TROIS appelants sont TOUS hors de l'arbre
        # d'operations : deux dans `IdunBattle.Messages.InputMessageProcessor$$RunPhase`, un dans
        # `IdunBattle.Messages.InputMessageProcessor$$VerifyTurnEnd`. Dans `RunPhase`, l'ordre LU est
        #
        #     action()                       <- l'arbre d'operations du message (l'attaque ENTIERE,
        #                                       `IdunBattle.Operations.FinishAttackOperation$$Execute`
        #                                       inclus, donc `On(9)` et `On(10)` deja emis)
        #     VerifyDeaths ; ProcessDamageEvents
        #     ProcessPendingTriggeredAbilities   <- DRAIN
        #     ... puis, si `isInternalPhase == 0`, le bloc de fin de tour (2e drain) et EndPhase
        #
        # => une ability differee s'execute APRES la cloture complete de l'attaque, jamais dedans.
        # C'est CE fait qui rend le deplacement de `HarlequinsPanoply` portable sans faire entrer
        # `On(PreUnitMove)`/`On(UnitAfterMove)` au milieu de la resolution des coups.
        #
        # Chaque entree = `(entity_id, triggered_ability_type, TriggerEvent)` : le natif memorise
        # l'`AbilityEntities` COMPLET (struct de 0x128 copiee dans la Queue) ; le port memorise le
        # `TriggerEvent` d'ou il le reconstruit a l'identique au drain.
        self.pending_triggered_abilities: list = []
        # Re-entrance du drain, meme forme que `draining_deaths` : le natif SNAPSHOTE la file dans une
        # `List<T>` puis `Queue.Clear()` AVANT d'iterer, et chaque item tourne dans un
        # `RunPhase(PhaseType.ProcessPendingTriggeredAbilities /*0xf*/, ..., isInternalPhase: 1)` qui RE-DRAINE la file. Le traitement est donc par
        # VAGUES (une ability enfilee pendant le drain part a la vague suivante), pas en FIFO plat.
        self.draining_pending_abilities: bool = False
        # #443-r2-b2 -- LA FILE DES DAMAGE-EVENTS, mirror de la `Queue<T>` que rend `IMatchState`
        # slot **7** (`GetDamageEvents`). Elle est ALIMENTEE par le slot **8**
        # (`AddDamageEvent(source, caster, target)` -> `IdunBattle.Core.MatchState$$AddDamageEvent`,
        # qui `Enqueue` un struct `{source: AbilityOrEffect@+0x0..+0x1b, casterId@+0x1c,
        # targetId@+0x20}`), et DRAINEE par
        # `IdunBattle.Messages.InputMessageProcessor$$ProcessDamageEvents`.
        # SEUL enfileur natif : `IdunBattle.Operations.ApplyDamageOperation$$Execute` -- balayage
        # LITTERAL du slot 8 d'`IMatchState` dans tout le decompile : **1 site**.
        # Chaque entree = `(source_ability, caster_id, target_id)`.
        self.pending_damage_events: list = []
        # Re-entrance du drain, MEME forme que `draining_pending_abilities` : le natif SNAPSHOTE
        # (`new List<T>(q)`) puis `q.Clear()` AVANT d'iterer, et chaque vague tourne dans un
        # `RunPhase(PhaseType 0xe, ..., isInternalPhase: 1)` qui RE-DRAINE la file.
        self.draining_damage_events: bool = False
        # #363 -- TRACE du canal du seed TERTIAIRE (`snapshot._auto_ability_states`), pose par
        # `load_state` : `{"source": <str>, "seeded": <int|None>}`. `seeded = None` veut dire « le
        # seed n'a PAS tourne », et `source` dit POURQUOI (`refused`, `no-snapshot`, `no-transport`,
        # `no-runner-label`, `unavailable:<msg>`). Sans cette trace, un etat sans relique se lit
        # comme « aucune relique equipee » alors qu'il peut signifier « le canal n'a rien mesure » --
        # c'est la discipline tri-etat de `host_inputs.py`, appliquee a un seed. Reste `None` sur un
        # `State` construit a la main (aucun `load_state` n'est passe).
        self.ability_states_seed: Optional[dict] = None
        # #429-r1-r3-r1-r1 -- TRACE du canal des `UnitFlag` (`snapshot._load_unit_flags`), MEME
        # discipline que `ability_states_seed` juste au-dessus. `None` = la passe n'a pas tourne
        # (aucun `combatSnapshot` fourni). Sinon :
        #   {"units": <int|None>, "units_not_alive": <int|None>, "units_not_alive_channel": <str>}
        # ou `units`/`units_not_alive` = nb de lignes PORTEUSES de flags lues, et
        # `units_not_alive_channel` NOMME l'etat du bloc `combatSnapshot.unitsNotAlive` :
        #   * `"lu"`     -- le bundle Frida le publie (liste, eventuellement vide) ;
        #   * `"muet"`   -- le champ existe mais vaut `null` (capteur non resolu cote hook) ;
        #   * `"absent"` -- le bundle charge est ANTERIEUR au correctif : il n'a pas le champ.
        # POURQUOI CE TROISIEME ETAT EXISTE. Sans lui, `snapshot.get("unitsNotAlive") or []`
        # dit exactement la meme chose pour « aucune unite non vivante » et pour « le capteur
        # n'existe pas » -- et c'est par CE rabattement que `UnitFlag.Fled` n'atteignait pas le
        # port, gate arme, pendant que le port frappait une unite ENFUIE pour 10 375 (mesure du
        # 2026-08-05). Un consommateur qui veut conclure « aucune fuite » DOIT verifier
        # `units_not_alive_channel == "lu"` d'abord.
        self.unit_flags_seed: Optional[dict] = None
        # #999-r3-r2 -- MEME forme, MEME canal, MEME tri-etat que `unit_flags_seed` ci-dessus,
        # pour la passe `snapshot._load_unit_rarity` (`BaseUnitComponent.Rarity` +0x74). `None`
        # ici = `load_state` n'a pas tourne avec un `combatSnapshot`.
        self.unit_rarity_seed: Optional[dict] = None

    def add_entity(self, entity_id: Optional[int] = None) -> Entity:
        if entity_id is None:
            entity_id = self._next_entity_id
            self._next_entity_id += 1
        e = Entity(entity_id)
        self.entities[entity_id] = e
        return e

    def get_entity(self, entity_id: int) -> Optional[Entity]:
        return self.entities.get(entity_id)

    def with_component(self, comp_type: type[C]) -> Iterator[tuple[Entity, C]]:
        """Itère (entité, composant) pour toute entité portant `comp_type`."""
        for e in self.entities.values():
            c = e.get_component(comp_type)
            if c is not None:
                yield e, c  # type: ignore[misc]

    # --- OCCUPATION du plateau (empreinte-aware, #R30) ------------------------------------------ #
    # Nativement une tuile n'est pas « la position d'une unite » : elle porte un
    # `TileContentComponent` dont le contenu est une entite-PIED, et `IdunBattle.Entities.
    # UnitExtensions$$GetUnit(tile, state)` remonte du pied a son unite via `UnitFootComponent.
    # UnitId`. Consequence directe, VALIDEE LIVE (cast `DutyEternal` -> `boardGraph.occupantUnitId`
    # marque les TROIS tuiles 31/32/41 avec le MEME id 107) : **toute tuile sous un pied est
    # occupee, par l'UNITE proprietaire du pied**. Les deux methodes ci-dessous sont la porte
    # unique de cette semantique cote port ; elles lisent l'empreinte, pas la seule main tile.

    def unit_at(self, pos, alive_only: bool = True):
        """`IdunBattle.Entities.UnitExtensions$$GetUnit(tile, state)` — l'entite UNITE dont un pied
        occupe `pos` (col,row), ou None. `alive_only` reflete les appelants qui filtrent les morts
        (une unite morte n'occupe plus sa tuile — cf. `decisionview_keeps_dead`) ; le passer a False
        rend l'occupant brut. Premier trouve dans l'ordre d'insertion des entites (l'ECS natif n'a
        qu'un contenu par tuile : le cas « deux occupants » n'existe pas)."""
        from .components import UnitComponent, get_unit_feet     # lazy : cycle state<->components
        p = (int(pos[0]), int(pos[1]))
        for eid, e in self.entities.items():
            uc = e.get_component(UnitComponent)
            if uc is None or (alive_only and not uc.alive):
                continue
            if p in get_unit_feet(self, e):
                return e
        return None

    def occupied_positions(self, alive_only: bool = True) -> set:
        """Ensemble de TOUTES les tuiles occupees — **tous les pieds de toutes les unites**, pas
        seulement leurs main tiles. C'est ce que consomme le gate de placement
        `IdunBattle.Entities.TileExtensions$$CanAddUnit` (`TileContentComponent.IsEmpty`)."""
        from .components import UnitComponent, get_unit_feet     # lazy : cycle state<->components
        out: set = set()
        for _eid, e in self.entities.items():
            uc = e.get_component(UnitComponent)
            if uc is None or (alive_only and not uc.alive):
                continue
            out.update(get_unit_feet(self, e))
        return out

    def reset_trigger_phases(self) -> None:
        """#140 : `ResetPhase` de tous les `TriggeredAbilityComponent` (remet `times_this_phase` à 0). Le
        natif l'appelle à `EndPhaseOperation` (fin d'ACTIVATION, via `OperationProcessor`) ; le runner offline
        n'a pas d'OperationProcessor → on mappe le boundary sur chaque ACTION top-level appliquée (`Runner.apply`).
        Plus fin que le per-activation natif mais STRICTEMENT SÛR (ne bloque jamais un trigger légitime) et
        inobservable (les compteurs restent << 51/activation) ; borne l'auto-récursion des triggers
        générateurs d'attaque DANS une même cascade d'action (le reset est AVANT la cascade, pas dedans).

        MEME BOUNDARY, MEME BOUCLE que le natif : `IdunBattle.Operations.EndPhaseOperation$$ResetEntityPhase`
        parcourt les entites et, sur CHACUNE, (a) `Clear()` la `List<BEntityId>` @`ActorStatisticsComponent
        + 0x48` (« unites endommagees cette phase ») puis (b) appelle `TriggeredAbilityComponent$$ResetPhase`.
        Le port fait donc les DEUX ici — la liste `UnitComponent.damaged_units_this_phase` alimente le
        selecteur `UnitsDamagedThisPhase` (volet OVERKILL de DoomSiren)."""
        from .components import TriggeredAbilityComponent, UnitComponent   # lazy : cycle state<->components
        for _e, comp in self.with_component(TriggeredAbilityComponent):
            comp.reset_phase()
        for _e, uc in self.with_component(UnitComponent):
            if uc.damaged_units_this_phase:
                uc.damaged_units_this_phase.clear()   # `List.Clear()` @ResetEntityPhase (champ 0x48)
