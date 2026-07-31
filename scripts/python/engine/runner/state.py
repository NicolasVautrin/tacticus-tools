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
    from ..entities import EffectsState
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
    dict @+0x38) ; incrémenté par `StartTurnOperation`. Source de `GetAmountOfTurnsStartedByCurrentPlayer`
    (gate « 1er tour » de certaines mécaniques). Vide tant qu'aucun tour n'a été joué via le runner.

    `pending_deaths` / `draining_deaths` = la FILE DE MORTS de `MatchState` et le verrou de
    ré-entrance de `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` (case-haze-ord) :
    `RecordKillOperation` ENQUEUE, `VerifyDeaths` DRAINE une mort à la fois. Détail au point
    d'initialisation ci-dessous.

    `turn_order_player_count` = nb de joueurs du `BC.Player.TurnOrder` dont `PlayerComponent+0x20 != 2`
    (Environment exclu) — le FACTEUR de `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (`count * rounds`),
    donc l'unité de TOUTE durée d'effet exprimée en ROUNDS. Seedé par `load_state` ; None = inconnu →
    `convert_rounds_to_turns` retombe sur l'identité."""
    __slots__ = ("entities", "current_player_id", "_next_entity_id", "effects", "rng", "board",
                 "turn_counts", "turn_order_player_count", "triggering_ability",
                 "trigger_ability_type",
                 "pending_deaths", "draining_deaths", "ability_states_seed")

    def __init__(self):
        self.entities: dict[int, Entity] = {}
        self.current_player_id: Optional[int] = None
        self._next_entity_id = 1
        self.effects: Optional["EffectsState"] = None
        self.rng: Optional["IntBasedMersenneTwister"] = None
        self.board = None
        self.turn_counts: dict[int, int] = {}
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
        # `+0x60` reste a zero sur `On(0)/On(1)/On(2)/On(53)/On(54)`. `operations/damage.py::
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
        # sur `On(1)`, `On(2)`, `On(0)`, `On(54)` puis `On(53)`. Ce canal y porte donc le `killTrigger`
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
        #      (`KillUnitOptions+0x04`) et laisse `+0x60` a ZERO, pour `On(0)/On(1)/On(2)/On(53)/On(54)`.
        #      **PORTE DEPUIS #301** : `operations/damage.py::_verify_deaths` pose le `killTrigger` de
        #      la file ICI et force `triggering_ability` (+0x60) a `None` le temps du drain. Le port
        #      faisait l'inverse (valeur sur `+0x60`, `+0x98` vide) -- divergence PERMISSIVE fermee.
        #   3. `IdunBattle.Operations.AddEffectOperation$$Execute` -- `+0x60` = `+0x98` =
        #      `AbilityOrEffect(effectType)`, pour `On(61)/On(62)/On(70)`. NON MODELISE.
        #      (Symetrique NEGATIF, contre-intuitif : `IdunBattle.Operations.RemoveEffectOperation$$Execute`
        #      n'ecrit QUE `+0x60` et laisse `+0x98` a zero -> sur `On(63)/On(64)` c'est
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
        # DRAINEE que par `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` (`RunPhase(0xc)` ->
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
        # #363 -- TRACE du canal du seed TERTIAIRE (`snapshot._auto_ability_states`), pose par
        # `load_state` : `{"source": <str>, "seeded": <int|None>}`. `seeded = None` veut dire « le
        # seed n'a PAS tourne », et `source` dit POURQUOI (`refused`, `no-snapshot`, `no-transport`,
        # `no-runner-label`, `unavailable:<msg>`). Sans cette trace, un etat sans relique se lit
        # comme « aucune relique equipee » alors qu'il peut signifier « le canal n'a rien mesure » --
        # c'est la discipline tri-etat de `host_inputs.py`, appliquee a un seed. Reste `None` sur un
        # `State` construit a la main (aucun `load_state` n'est passe).
        self.ability_states_seed: Optional[dict] = None

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
