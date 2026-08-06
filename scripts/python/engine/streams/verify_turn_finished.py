"""La face STREAM du SLOT `0x21` d'`Core.Services.IOperationProcessor` -- la QUEUE du
`Group=StartTurn` (#477-r22-r1).

LE SLOT EST RESOLU, PAS DEVINE. `data/symbols/<build>/metadata/interface_slots.tsv` (livre par
`#477-r25`, couvert pour `Core.Services.IOperationProcessor` par `#477-r24-r1`) donne, pour
`Core.Services.IOperationProcessor` :

    IOperationProcessor slot 0x21 = VerifyUnitsTurnFinished       -- param_count 0
    IOperationProcessor slot 0x76 = MarkUnitAsNoActionAvailable   -- param_count 1
    IOperationProcessor slot 0x77 = MarkUnitAsActionAvailable     -- param_count 1

⚠ UN NOM DESIGNE UN ENSEMBLE DE SLOTS -- C'EST LE COUPLE NOM + ARITE QUI IDENTIFIE (mesure de
`#477-r25`). L'ARITE recoupe ici le call-site : `IdunBattle.Operations.StartTurnOperation$$Execute`
invoque le slot `0x21` SANS AUCUN ARGUMENT, juste apres ses cinq `EvaluateAbilities(TurnStart_*)`
et avant `Events.FinishGroup()`. Les deux voisins immediats du meme nom court n'existent pas :
`VerifyAutomaticTurnEnd` est a 2 arguments (slot 32) et `VerifyAndRefreshUnitTurnFinished` a 1
(slot 34), donc l'arite 0 ne laisse qu'un candidat.

LA CHAINE, de bout en bout, chaque maillon NOMME :

    Core.Services.OperationProcessor$$VerifyUnitsTurnFinished          <- slot 0x21, arite 0
      -> IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$Execute
           if (GetMatch(state).<+0x24> != 1) return;            // la bataille n'est pas EN COURS
           turn   = matchEntity.GetComponent<TurnComponent>();
           player = state.GetEntity(TurnComponent.get_CurrentPlayerId(turn))
                         .GetComponent<PlayerComponent>();
           foreach (id in PlayerComponent.get_CurrentlyOwnedUnitIds(player))
               VerifyUnitTurnEnded(state.GetEntity(id));
           VerifyMachineTurnEnded(state.GetEntity(player.<+0x78>));     // INLINE dans Execute
      -> IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded
      -> Core.Services.OperationProcessor$$MarkUnitAsNoActionAvailable  <- slot 0x76 (reverse=0)
         Core.Services.OperationProcessor$$MarkUnitAsActionAvailable    <- slot 0x77 (reverse=1)
      -> IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute   <- L'EMISSION

CE QUE CE MODULE PORTE, ET CE QU'IL NE PORTE PAS
------------------------------------------------
Il porte la FACE STREAM : la mutation du bit `UnitFlag.NoActionAvailable` (qui GATE l'emission)
et l'`Events.Action` qui en sort. Il ne porte NI le pathfinding NI la prediction de degat des
deux predicats `HasTilesToMoveTo` / `HasActionAvailable` : ceux-la vivent deja dans
`engine/runner/operations/turnflow.py` (#287-r1-r1), qui porte la MEME operation sur l'axe ECS
et declare explicitement « events/steps de stream = couche view/process non suivie ». Les deux
faces se rejoignent ici : ce module recoit les quatre predicats RESOLUS et derive l'emission.

⚠ LE BIT VIT DANS CE MODULE, ET C'EST OBLIGATOIRE -- IL EST LE GATE. `UnitFlagsComponent$$Add`
rend `false` si le drapeau etait DEJA la, `$$Remove` rend `false` s'il n'y etait PAS, et
`MarkUnitAsNoActionAvailableOperation$$Execute` RETOURNE sans rien emettre sur ce `false`. Un
port qui emettrait inconditionnellement ajouterait des lignes que le natif n'ecrit pas. La face
STREAM ne dispose d'aucun `State` ECS (c'est la convention de tout `engine/streams/`), donc le
bit est tenu par `NoActionAvailableFlags`, un registre a la seule granularite que la face lit.

CE QUI N'EST PAS PORTE, ET QUI EST NOMME :

  * la garde `GetMatch(state).<+0x24> != 1` (« la bataille est EN COURS »). Meme champ que la
    garde `<+0x24> == 2` de `IdunBattle.Operations.ContinueTurnPhaseOperation$$Execute`, deja
    declaree non portee par `turn_phase.py` : aucun accesseur NOMME du build ne lui donne un
    type, donc l'attribuer a un enum serait une hypothese deguisee en mirror ;
  * la resolution de `PlayerComponent.get_CurrentlyOwnedUnitIds` : l'appelant fournit la liste ;
  * `HasTilesToMoveTo` / `HasActionAvailable` (les deux slots d'`IMovementQuery` /
    `IDamagePredictionQuery` identifies par `#287-r1-r1`), et `UnitFlagsComponent$$TurnEnded` /
    `HealthComponent$$IsDead` : ce sont les QUATRE predicats de `UnitTurnState`, fournis ;
  * `MachineCanAttackAnyUnitWithAnyAbility` (slot `IDamagePredictionQuery` 2), le seul predicat
    de `VerifyMachineTurnEnded` -- fourni de meme.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Set

from ..entities.unit_flag import UnitFlag
from .dispatcher import StreamDispatcher
from .step_type import StepType
from .tag_key import TagKey


class NoActionAvailableFlags:
    """Le bit `UnitFlag.NoActionAvailable` d'`IdunBattle.Entities.Components.UnitFlagsComponent`,
    reduit a ce que la face STREAM en lit : `Has`, `Add`, `Remove`.

    LES TROIS METHODES SONT DES MIRRORS, lus verbatim :

        UnitFlagsComponent$$Has(flag)     -> this.<+0x10>.Contains(flag)
        UnitFlagsComponent$$Add(flag)     -> if (Contains(flag)) return false;
                                             this.<+0x10>.Add(flag);    return true;
        UnitFlagsComponent$$Remove(flag)  -> if (!Contains(flag)) return false;
                                             this.<+0x10>.Remove(flag); return true;

    ⚠ LE BOOLEEN RENDU N'EST PAS DECORATIF : c'est LUI que teste
    `MarkUnitAsNoActionAvailableOperation$$Execute` avant d'emettre. Deux appels consecutifs de
    meme sens n'ecrivent donc QU'UNE ligne.

    ⚠ CE REGISTRE NE PORTE QU'UN SEUL DRAPEAU, ET C'EST DELIBERE. Le composant natif en porte 27
    (`engine/entities/unit_flag.py`) ; l'axe ECS complet est deja tenu par
    `engine/runner/components.py::UnitFlagsComponent`. Dupliquer ici les 27 creerait une seconde
    source de verite pour des drapeaux que la face stream ne lit jamais."""

    __slots__ = ("_marques",)

    def __init__(self, marques: Iterable[int] = ()) -> None:
        self._marques: Set[int] = {int(u) for u in marques}

    def has(self, unit_entity_id: int) -> bool:
        """`UnitFlagsComponent$$Has(UnitFlag.NoActionAvailable)`."""
        return int(unit_entity_id) in self._marques

    def add(self, unit_entity_id: int) -> bool:
        """`UnitFlagsComponent$$Add(UnitFlag.NoActionAvailable)` -- `false` si deja pose."""
        uid = int(unit_entity_id)
        if uid in self._marques:
            return False
        self._marques.add(uid)
        return True

    def remove(self, unit_entity_id: int) -> bool:
        """`UnitFlagsComponent$$Remove(UnitFlag.NoActionAvailable)` -- `false` si absent."""
        uid = int(unit_entity_id)
        if uid not in self._marques:
            return False
        self._marques.discard(uid)
        return True

    def marques(self) -> frozenset:
        """Les unites actuellement marquees -- pour l'instantane, jamais pour decider."""
        return frozenset(self._marques)


def mark_unit_as_no_action_available(events: StreamDispatcher, flags: NoActionAvailableFlags,
                                     unit_entity_id: int, reverse: bool) -> bool:
    """`IdunBattle.Operations.MarkUnitAsNoActionAvailableOperation$$Execute(unit, reverse)`
    -- sa SEULE emission. LE DECOMPILE, litteral pour litteral :

        comp = unit.GetComponent<UnitFlagsComponent>();
        if (comp == null) throw;
        if (!reverse) { if (!UnitFlagsComponent.Add(comp,    UnitFlag.NoActionAvailable /*4*/))
                            return; value = 0; }
        else          { if (!UnitFlagsComponent.Remove(comp, UnitFlag.NoActionAvailable /*4*/))
                            return; value = 1; }
        var tags = new Dictionary<TagKey,int>();
        tags.Add(TagKey.UnitStats_ActionsAvailable /*0x6f*/, value);
        Events.Action(StepType.ChangeStats /*0xc*/, <IEntity slot 0>(unit) /*Id*/, tags);

    ⚠ LE SENS DE LA VALEUR EST L'INVERSE DU SENS DU DRAPEAU, et c'est la faute naturelle a cet
    endroit. `reverse = false` = `MarkUnitAsNoActionAvailable` = on POSE le drapeau, et le tag
    ecrit **0** (« plus d'actions disponibles ») ; `reverse = true` =
    `MarkUnitAsActionAvailable` = on le RETIRE, et le tag ecrit **1**. Le port ecrit donc
    `1 if reverse else 0`, jamais `int(<drapeau pose>)`.

    ⚠ L'ENTITE EST CELLE DE L'UNITE, pas celle du match : le natif passe
    `<IEntity slot 0>(unit)` -- l'accesseur d'identifiant d'`IdunBattle.Core.IEntity`, le meme
    helper d'appel a 0 argument que partout ailleurs dans ce dossier. C'est l'inverse de
    `PrepareTurnOperation` / `StartTurnOperation`, qui portent tous deux l'entite de MATCH.

    ⚠ UN SEUL TAG, et le dictionnaire est construit APRES la mutation du drapeau : l'operation
    qui n'a rien change ne construit meme pas le dictionnaire.

    Rend « la ligne a ete emise » -- c'est le booleen que rend `UnitFlagsComponent$$Add`/`Remove`,
    remonte pour que l'appelant puisse le compter, jamais pour qu'il en decide."""
    change = flags.remove(unit_entity_id) if reverse else flags.add(unit_entity_id)
    if not change:
        return False
    events.action(StepType.ChangeStats, int(unit_entity_id),
                  {int(TagKey.UnitStats_ActionsAvailable): 1 if reverse else 0})
    return True


@dataclass(frozen=True)
class UnitTurnState:
    """LES QUATRE PREDICATS ECS que lit
    `IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded`, et RIEN
    d'autre. Le cinquieme -- `UnitFlagsComponent$$Has(UnitFlag.NoActionAvailable)` -- n'est PAS
    ici : il vient du registre `NoActionAvailableFlags`, que ce module MUTE.

    Chacun est nomme par sa fonction native :

        turn_ended            `UnitFlagsComponent$$TurnEnded()` = `Has(UnitFlag.TurnFinished /*3*/)`
        is_dead               `HealthComponent$$IsDead()`, sous `TryGetComponent<HealthComponent>`
        has_tiles_to_move_to  `VerifyUnitsTurnFinishedOperation$$HasTilesToMoveTo`
                              -> `IdunBattle.Core.Services.MovementQuery$$HasAnyMovablePositionsFor`
        has_action_available  `VerifyUnitsTurnFinishedOperation$$HasActionAvailable`
                              -> `MovementQuery$$GetMovableTilesFor` + `GetMainTile`
                                 + `DamagePredictionQuery$$CanAttackAnyUnitFromTilesWithAnyAbility`

    ⚠ `has_health_component` EXISTE PARCE QUE LE NATIF FAIT UN `TryGetComponent`, pas un
    `GetComponent` : la mort n'est testee QUE si le composant est la. Le distinguer d'`is_dead`
    est ce qui interdit de lire « pas de composant » comme « vivante » par accident."""

    entity_id: int
    turn_ended: bool
    is_dead: bool
    has_tiles_to_move_to: bool
    has_action_available: bool
    has_health_component: bool = True


def verify_unit_turn_ended(events: StreamDispatcher, flags: NoActionAvailableFlags,
                           unit: UnitTurnState) -> bool:
    """`IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded(unit)`,
    MIRROR du decompile :

        comp = unit.GetComponent<UnitFlagsComponent>();          // null -> throw
        if (UnitFlagsComponent.TurnEnded(comp))                       return;
        if (unit.TryGetComponent<HealthComponent>(out hp) && hp.IsDead())  return;
        if (!UnitFlagsComponent.Has(comp, UnitFlag.NoActionAvailable)) {
            if (HasTilesToMoveTo(unit))                               return;
            if (HasActionAvailable(unit))                             return;
            <IOperationProcessor slot 0x76>(unit);          // MarkUnitAsNoActionAvailable -> POSE
        } else {
            if (!HasTilesToMoveTo(unit) && !HasActionAvailable(unit)) return;
            <IOperationProcessor slot 0x77>(unit);          // MarkUnitAsActionAvailable  -> RETRAIT
        }

    ⚠ LES DEUX BRANCHES EVALUENT `HasTilesToMoveTo` EN PREMIER, ET LE `OU` COURT-CIRCUITE. Le
    detail n'est pas cosmetique cote ECS (`case-287-r1-r1` §3 en fait dependre l'exactitude du
    port) ; cote STREAM il ne change pas le texte emis, et c'est ecrit ici pour que la structure
    reste celle du natif plutot que d'etre « simplifiee » en un `or`.

    ⚠ LA BRANCHE EST CHOISIE PAR LE DRAPEAU, ET LE DRAPEAU CHOISIT LA VALEUR. C'est la seule
    chose que ce module DERIVE : la meme unite, avec les memes quatre predicats, emet `0` si le
    drapeau etait absent et `1` s'il etait present -- ou rien du tout.

    Rend « une ligne a ete emise »."""
    if unit.turn_ended:
        return False
    if unit.has_health_component and unit.is_dead:
        return False
    if not flags.has(unit.entity_id):
        if unit.has_tiles_to_move_to:
            return False
        if unit.has_action_available:
            return False
        return mark_unit_as_no_action_available(events, flags, unit.entity_id, reverse=False)
    if not unit.has_tiles_to_move_to and not unit.has_action_available:
        return False
    return mark_unit_as_no_action_available(events, flags, unit.entity_id, reverse=True)


@dataclass(frozen=True)
class MachineTurnState:
    """Les DEUX predicats que lit
    `IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyMachineTurnEnded` -- et ils ne
    sont PAS ceux d'une unite : la machine n'a ni `HasTilesToMoveTo` ni `HasActionAvailable`,
    seulement `<IDamagePredictionQuery slot 2>` =
    `MachineCanAttackAnyUnitWithAnyAbility(machine)` (attribution de `case-287-r1-r1` §2)."""

    entity_id: int
    turn_ended: bool
    can_attack_any_unit: bool


def verify_machine_turn_ended(events: StreamDispatcher, flags: NoActionAvailableFlags,
                              machine: MachineTurnState) -> bool:
    """`IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$VerifyMachineTurnEnded(machine)`,
    MIRROR :

        comp = machine.GetComponent<UnitFlagsComponent>();
        if (UnitFlagsComponent.TurnEnded(comp))                       return;
        if (!UnitFlagsComponent.Has(comp, UnitFlag.NoActionAvailable)) {
            if (<IDamagePredictionQuery slot 2>(machine))             return;
            <IOperationProcessor slot 0x76>(machine);
        } else {
            if (!<IDamagePredictionQuery slot 2>(machine))            return;
            <IOperationProcessor slot 0x77>(machine);
        }

    ⚠ IL N'Y A PAS DE TEST DE MORT ICI, la ou `VerifyUnitTurnEnded` en fait un. La difference est
    LUE, pas simplifiee : le corps de la machine ne touche jamais `HealthComponent`.

    ⚠ CE CORPS EST INLINE DANS `$$Execute` (le compilateur l'y a recopie a l'identique, sur
    l'entite `player.<+0x78>`), et il est ecrit ici comme une fonction pour que la difference de
    predicat reste visible. NON EXERCE par le corpus confronte -- aucun de nos montages n'amene
    de Machine of War."""
    if machine.turn_ended:
        return False
    if not flags.has(machine.entity_id):
        if machine.can_attack_any_unit:
            return False
        return mark_unit_as_no_action_available(events, flags, machine.entity_id, reverse=False)
    if not machine.can_attack_any_unit:
        return False
    return mark_unit_as_no_action_available(events, flags, machine.entity_id, reverse=True)


def verify_units_turn_finished(events: StreamDispatcher, flags: NoActionAvailableFlags,
                               unites: Iterable[UnitTurnState],
                               machine: Optional[MachineTurnState] = None) -> List[int]:
    """`IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$Execute` -- sa face STREAM.

    L'ORDRE EST CELUI DE `PlayerComponent$$get_CurrentlyOwnedUnitIds`, et la MACHINE VIENT APRES
    LA BOUCLE : le natif itere la liste des unites du joueur COURANT, puis traite l'entite
    `player.<+0x78>`. Le port ne trie rien -- il suit la sequence recue, et c'est ce qui rend
    l'ordre du flux confrontable.

    ⚠ LA GARDE D'ENTREE N'EST PAS PORTEE (cf. docstring du module) : `GetMatch(state).<+0x24>
    != 1`. Un appelant qui la connaitrait doit s'abstenir d'appeler, et non passer une liste
    vide -- la difference se verrait si le natif emettait autre chose sur ce chemin, ce qu'il ne
    fait pas.

    Rend la liste des entites pour lesquelles une ligne a ete emise, dans l'ordre d'emission."""
    emises: List[int] = []
    for unite in unites:
        if verify_unit_turn_ended(events, flags, unite):
            emises.append(int(unite.entity_id))
    if machine is not None and verify_machine_turn_ended(events, flags, machine):
        emises.append(int(machine.entity_id))
    return emises


#: LE DRAPEAU QUE CE MODULE MUTE, nomme. Il sert aux tests et aux probes a citer le membre
#: plutot que l'ordinal `4` -- meme regle que partout ailleurs.
FLAG = UnitFlag.NoActionAvailable
