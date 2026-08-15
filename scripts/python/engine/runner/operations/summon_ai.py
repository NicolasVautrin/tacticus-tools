"""Couche AI-CONTROL du runner : faire jouer une unite par l'IA HORS de son activation normale.

Deux entrees natives distinctes, portees ici cote a cote :

1. **Passe AUTOMATIQUE du TURN-START** (#65, artefact natif RE-IDENTIFIE par #291) — mirror de
   `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute(player, skipAction)`, appelee par
   `IdunBattle.Operations.StartTurnOperation$$Execute` (slot `IOperationProcessor` 0x71 =
   `PlayAutomaticUnits(player)`) APRES la sequence d'events 0x12..0x16, sous DEUX gates natifs :
   `!IdunBattle.Core.Services.BattleQuery$$get_NoAutomaticUnitTurns` (flag de `BattleConfiguration`)
   et `PlayerComponent.PlayerType` dans {Human(0), Network(3), HumanAI(4)} — un joueur `AI`(1) ne
   passe PAS par ici (toutes ses unites, summons compris, sont jouees par la boucle IA globale).
   Corps natif :
       foreach uid in PlayerComponent.CurrentlyOwnedUnitIds(player):
           u = state[uid]
           if u != null && IsAlive(u) && !HasFlag(u, 3 = TurnFinished) && IsAutomatic(u): auto += u
       foreach u in auto:
           if (!skipAction) for i in 0..4: if HasActionLeft(u): ComputerAction(u, forced: false)
           FinishUnitTurn(u, isTerminated: false)
   `IdunBattle.Entities.UnitExtensions$$IsAutomatic(u)` = `BaseUnitComponent.HasTrait(u, 2 = Summon)
   || HasTrait(u, 13 = Object)` — c'est le trait, PAS un flag de vue. (L'ancienne citation
   `IdunGameViews$$QueueComputerActions` etait FAUSSE : ce chemin-la ne se declenche que si le joueur
   COURANT est entierement AI-controle, et il lance la boucle IA complete, pas les summons.)
   -> `collect_ai_controlled` / `run_ai_control_pass`.
   VERITE-TERRAIN LIVE (#291, probe_291_summon_activation) : au debut du tour suivant de leur team,
   SANS aucune action du joueur, les deux `orksOrkBoys` invoques se deplacent et l'un des ennemis
   perd 2623 PV.

2. **`ComputerActionOperation`** (`IdunBattle.Operations.ComputerActionOperation`, mono IdunBattle.Operations.ComputerActionOperation$$Execute /
   groupe IdunBattle.Operations.ComputerActionOperation$$Execute) — le mutateur ECS derriere `Core.Services.OperationProcessor$$ComputerAction/Core.Services.OperationProcessor$$ComputerAction,
   lui-meme la FEUILLE du behaviour DSL `PerformAIAction` (cf. `abilities/behaviours/ai_control.py`) :
   fait agir une ou plusieurs unites TIERCES **immediatement**, en SAUVEGARDANT puis RESTAURANT leurs
   flags de tour -> l'action supplementaire NE CONSOMME PAS le tour de la cible.

DECISION = le playbook complet porte (`DefaultAiUnitTactic.calculate_next_action` via le bridge offline
`engine.ai.state_bridge.build_from_state`) — la routine de candidats native = `PerformAIAbilityUnitBehaviour
.IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour$$Execute` (enumere cibles -> per-cible move+attaque -> utility-argmax). APPLY = les Operations
runner (move + attaque normale/ability), au niveau `state` (comme `_betrayer_take_turn` du vecteur turn-start).

Ordre intra-team = `PickNextUnit` (utility) cote natif ; ici ordre d'id (1re approx documentee ; raffinement).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import (UnitComponent, OwnerComponent, PositionComponent, UnitFlagsComponent,
                          StatsComponent, unit_is_dead)
from ...entities.ability_variable_type import AbilityVariableType
from ...entities.active_ability_type import ActiveAbilityType
from ..events import EventBus
from ..messages import ActiveAbilityMessage
from .active_ability import is_dead_unit_and_not_allowed_by_ability
from .damage import AttackDamageOperation
from .movement import MoveUnitOperation

NORMAL_ATTACK_ID = int(ActiveAbilityType.NormalAttack)   # 17 — id synthetique du bridge (cf. state_bridge) #158

# `IdunBattle.AI.OperationalDeciders.AnAiGroupOperator$$GetValidUnits` : cap anti-emballement du nb d'actions AI DEJA jouees par
# une unite (`BaseUnitComponent+0x60 < 0x3e9`) — le compteur est incremente par
# `DefaultGroupOperator.<CalculateNextActionForUnitGroup>IdunBattle.AI.OperationalDeciders.DefaultGroupOperator.u003CCalculateNextActionForUnitGroupu003Ed__6$$MoveNext` juste avant de
# demander sa prochaine action a la tactique.
MAX_AI_ACTIONS_PER_UNIT = 0x3e9 - 1                      # 1000


#: `IdunBattle.Entities.Enum.UnitTrait` — les deux traits que teste `UnitExtensions$$IsAutomatic`.
AUTOMATIC_TRAITS = ("Summon", "Object")          # UnitTrait.Summon = 2, UnitTrait.Object = 13


def is_automatic(state: State, uid: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$IsAutomatic(unit)` = `BaseUnitComponent.HasTrait(unit,
    2 = Summon) || BaseUnitComponent.HasTrait(unit, 13 = Object)` — lu verbatim au decompile (deux
    `GetBaseUnitComponent` + `HasTrait`, retour du premier vrai). C'est le SEUL critere de la passe
    automatique native ; le flag offline `UnitComponent.ai_controlled` en est le proxy historique
    (pose main a main au spawn). On accepte les DEUX : le trait quand le `UnitContext` du summon est
    hydrate (chemin nominal), le flag sinon (montages de test qui n'ont pas de ctx). Union stricte —
    aucun porteur ne perd sa passe, et les unites deliberement INERTES restent exclues (le decoy
    porte `Steppable`/`Decoy`, le neophyte de CultDemagogue `Ambush`/`BattleFatigue` : ni l'un ni
    l'autre n'a `Summon`/`Object`, et tous deux ont `ai_controlled=False`)."""
    e = state.get_entity(int(uid))
    if e is None:
        return False
    uc = e.get_component(UnitComponent)
    if uc is not None and getattr(uc, "ai_controlled", False):
        return True
    sc = e.get_component(StatsComponent)
    traits = list(getattr(sc.ctx, "traits", None) or []) if (sc is not None and sc.ctx) else []
    return any(t in traits for t in AUTOMATIC_TRAITS)


def collect_ai_controlled(state: State, player: int) -> list:
    """Mirror de la PREMIERE boucle de `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` :
    parmi `PlayerComponent.CurrentlyOwnedUnitIds(player)`, retient `u != null && IsAlive(u) &&
    !HasFlag(u, 3 = TurnFinished) && IsAutomatic(u)`.

    Le gate `!TurnFinished` compte, et c'est #291 qui lui donne son sens : une unite APPARUE pendant
    le tour de son proprietaire a ete `FinishUnitTurn(spawned, isTerminated: true)`-ee par
    `SpawnUnitBehaviour$$TriggerSpawnedUnitBehaviours`. Au turn-start SUIVANT,
    `StartTurnOperation` a deja appele `RemoveTurnFlags` sur les unites du joueur entrant (le flag
    est donc tombe) -> le summon passe le gate et JOUE. Dans le meme tour que son apparition, en
    revanche, il ne joue QUE par un `ComputerAction` force (noeud DSL `PerformAIAction`).

    Triees par id (ordre `PickNextUnit` = raffinement documente). `player` = OwnerComponent.player
    (3/4), pas la team."""
    out: list = []
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        oc = e.get_component(OwnerComponent)
        if uc is None or oc is None:
            continue
        if not uc.alive or not is_automatic(state, eid):
            continue
        if oc.player != player:
            continue
        fl = e.get_component(UnitFlagsComponent)
        if fl is not None and fl.turn_ended():     # `!HasFlag(u, 3 = TurnFinished)`
            continue
        out.append(eid)
    return sorted(out)


def run_ai_control_pass(state: State, player: int) -> list:
    """Mirror de la SECONDE boucle de `IdunBattle.Operations.PlayAutomaticUnitsOperation$$Execute` :
    joue chaque unite AUTOMATIQUE du `player` (decision playbook -> apply). Renvoie la liste des
    resultats (diagnostic). No-op (liste vide) si la team n'a aucun summon (cas normal des batailles
    sans invocation) -> aucune regression sur le turn-flow existant.

    RESIDUS NOMMES (non portes, avec leur debloqueur exact) :
      * la boucle native est `for i in 0..4: if HasActionLeft(u) -> ComputerAction(u, false)` (jusqu'a
        CINQ actions par unite automatique), le port n'en joue qu'UNE. La pose de
        `NoActionAvailable`(4) qu'elle exige pour TERMINER est portee depuis #287-r1
        (`MarkUnitAsNoActionAvailableOperation`, branchee en queue de `FinishUnitTurnOperation`) ;
        ce qui manque encore est le RETRAIT
        (`VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded`, slot 0x77), sans lequel le flag
        survit au `RemoveTurnFlags(includeNoAction=0)` du turn-start. Residu `#287-r1-r1`.
      * le `FinishUnitTurn(u, isTerminated: false)` final ;
      * les deux gates d'ENTREE, cote `StartTurnOperation` : `!BattleQuery.NoAutomaticUnitTurns` et
        `PlayerType in {Human, Network, HumanAI}`. Ni le flag de BC ni le `PlayerType` ne sont suivis
        par le `State` offline. Impact NUL sur l'arene (seed BC mesuree : `NoAutomaticUnitTurns=false`,
        player 11 = `Human`) ; il faudrait les suivre pour un montage ou la team automatique
        appartiendrait a un joueur `AI`(1)."""
    results: list = []
    for uid in collect_ai_controlled(state, player):
        e = state.get_entity(uid)                      # re-check : une action precedente (overwatch) a pu tuer
        uc = e.get_component(UnitComponent) if e is not None else None
        if uc is None or not uc.alive:
            continue
        results.append(decide_and_apply(state, uid))
    return results


def decide_and_apply(state: State, uid: int) -> dict:
    """Bridge `State -> AiDecisionContext` (offline) -> decision playbook -> apply. Capture les exceptions du
    bridge/spine en un resultat diagnostic (ne casse pas le turn-flow)."""
    from engine.ai.state_bridge import build_from_state
    from engine.ai.tactic import DefaultAiUnitTactic
    try:
        ctx = build_from_state(state, uid)
        action = DefaultAiUnitTactic().calculate_next_action(ctx)
    except Exception as ex:                             # pragma: no cover (diagnostic)
        return {"uid": uid, "error": repr(ex)}
    return apply_action(state, uid, action)


def apply_action(state: State, uid: int, action: dict) -> dict:
    """Applique l'action decidee (`{kind, to, target, ability}`) via les Operations runner, au niveau `state` :
      1. si `to` != origine -> `MoveUnitOperation` + vecteur after-move (overwatch sur le move du summon) ;
      2. attaque normale (ability == 17) -> `AttackDamageOperation.execute` + vecteur after-hit (mirror
         exact du handler `visit_AttackUnitMessage`) ; ability ACTIVE -> handler (SLICE 2 ; 4 abilities portees).
    Re-check `alive` apres le move (l'overwatch peut tuer le summon avant qu'il n'attaque)."""
    from .triggers.dispatch.attack import after_hit_normal_attack

    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    origin = (pc.col, pc.row) if pc is not None else None
    to = action.get("to")
    res: dict = {"uid": uid, "kind": action.get("kind"), "to": to,
                 "target": action.get("target"), "ability": action.get("ability"),
                 "moved": None, "attack": None}
    # 1. composante MOVE
    if to is not None and tuple(to) != origin:
        # Le vecteur after-move (et le 2e `RefreshEffects({7, null})` qui l'encadre) est joue PAR
        # L'OPERATION depuis #448-r1-r1-r2-r1 -- au rang natif, dans `MoveUnitOperation$$Execute`.
        # Le summon bouge par le MEME chemin que le mouvement joueur (`MoveUnitMessage`), donc
        # options nulles = tous les defauts du ctor. GAIN de fidelite au passage : `movement_steps`
        # est desormais RENSEIGNE (il etait `None` quand cet appelant jouait le vecteur lui-meme).
        op = MoveUnitOperation(uid, tuple(to))
        op.execute(state, EventBus())
        res["moved"] = tuple(to)
        res["after_move"] = op.last_after_move
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or not uc.alive:                     # tue par l'overwatch pendant le move
        return res
    # 2. composante ATTAQUE / ABILITY
    if action.get("kind") == "ability":
        ability = action.get("ability")
        target = action.get("target")
        if ability == NORMAL_ATTACK_ID and target is not None:
            r = AttackDamageOperation.execute(state, uid, target)
            res["attack"] = r
            if r is not None:                          # vecteur after-hit (mirror visit_AttackUnitMessage)
                # #437 : `profiles` n'est plus threade ici -- il appartenait au seul `On(9)`, emis
                # desormais a la SORTIE de `AttackDamageOperation.execute` (foyer natif), donc DEJA
                # parti quand ce vecteur-ci s'execute. Ses resultats reviennent par `finish_attack`
                # et sont remis EN TETE (ordre natif), pour que le canal reste observable.
                res["after_hit"] = (r.get("finish_attack") or []) + after_hit_normal_attack(
                    state, uid, target, bool(r.get("ranged")), r.get("profile"),
                    is_crit=bool(r.get("did_crit")),
                    did_block=bool(r.get("did_block")))
        elif ability is not None:
            res["attack"] = _apply_active_ability(state, uid, target, ability)
    return res


def _apply_active_ability(state: State, uid: int, target: Optional[int], ability: int) -> dict:
    """Apply d'une ability ACTIVE décidée (SLICE 2). Ordre : (1) port DÉDIÉ via le `AbilityHandler`
    (CrushingClaws splash 1105, ScarabHive spawn 1007, ThunderousAssault 1043 — sa behaviour propre
    prime) ; sinon (2) attaque active SANS port dédié -> chemin GÉNÉRIQUE déjà porté
    `execute_ability_attack` (mirror `AttackWithAttackDamage`), config résolue par `ability_attack_params` ;
    sinon (3) no-op (ability non-attaque non portée -> DÉCISION produite, EXÉCUTION offline manquante).

    #429-r1-r1-r1 GATE CIBLE-MORTE sur la voie (2). Ce repli EMULE un cast d'ability ACTIVE : il
    remplace, pour une ability sans port dédié, ce que le natif fait en traversant
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal`. Or ce site natif est le SEUL
    d'où une ability active s'exécute -- mesuré par XREFS sur ce build :
    `ActiveAbilityOperation$$Execute` n'a que DEUX appelants CODE
    (`Core.Services.OperationProcessor$$ActiveAbility` et la ré-entrée
    `ActiveAbilityOperation$$ExecuteForReplacedTarget`), et `ExecuteInternal` un SEUL (`$$Execute`).
    Un summon qui joue une ability y passe donc exactement comme un cast commandé, et y rencontre
    `IsDeadUnitAndNotAllowedByAbility` en PREMIER gate.
    C'est ce qui SEPARE cette voie des ~9 autres call-sites d'`execute_ability_attack` : eux
    mirrorent un noeud DSL d'attaque (`AttackWithAttackDamage`/`AttackWithAbilityDamage`/
    `ChainLeftOverHitsAttackDamage`/`AttackDamage`), INTERNE a une behaviour, dont l'étage natif
    (`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` ->
    `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` ->
    `Core.Services.OperationProcessor$$AttackDamage` -> `IdunBattle.Operations.AttackDamageOperation$$Execute`)
    ne re-gate RIEN -- `IsDeadUnitAndNotAllowedByAbility` n'a AUCUN appelant sur ce trajet (mesure
    d'xrefs : ses deux seuls appelants sont `ExecuteInternal` et `ExecuteForReplacedTarget`). Gater
    le foyer `execute_ability_attack` serait donc un FORK du natif, et casserait notamment
    `HazeCorruption_BonusHitAbility`, dont le trigger est `IsDead(Target@0x178)` : le natif frappe
    BEL ET BIEN le cadavre, pour que le coup déborde en `LeftOverDamage`.
    La voie (1) est déjà gatée en amont par #429-r1 (dans `visit_ActiveAbilityMessage`) et la voie
    attaque-normale de `apply_ai_action` par #429-r1-r1 (tête d'`AttackDamageOperation.execute`) ;
    cette pose ferme la TROISIEME et dernière porte de ce module.
    `ability_class` = `ABILITY_CLASSES.get(ability)` : la branche n'est atteinte que lorsqu'il vaut
    `None` (sinon la voie (1) a déjà rendu), et `None` -> refuse, ce qui est le comportement natif de
    TOUTE ability sauf `GreatFrostAxe` (1089) -- seule à poser le bit 38 `AllowDeadTarget` du masque
    de CONTINUE. On le relit quand même du registre plutôt que de câbler `None` en dur, pour que la
    dérogation reste portée si l'ordre des voies change."""
    from ..abilities.handler import AbilityHandler, ABILITY_CLASSES
    from ..abilities.base import ability_attack_params
    h = AbilityHandler(state)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(uid, target, ability))
    if h.last and h.last.get("ported"):
        return {"ability": ability, "target": target, "routed": "handler", "diag": h.last}
    if is_dead_unit_and_not_allowed_by_ability(state, ABILITY_CLASSES.get(int(ability)), target):
        return {"ability": ability, "target": target, "routed": "dead_target_not_allowed"}
    if target is not None and _is_active_attack_ability(ability):
        from engine.ai.state_bridge import _resolve_ability
        _name, cfg = _resolve_ability(ability)
        profile = (cfg.get("constants") or {}).get("damageProfile")
        ranged = (cfg.get("attackRangeType") == "Ranged")
        # #429-r1-r1-r1-r1 : les cles de degat sont DERIVEES de la config, pas figees a
        # `minDmg`/`maxDmg`. Le natif choisit AU SITE entre `AActiveAbility$$MinMaxDamage` (0xc/0xd)
        # et `AActiveAbility$$DmgDamage` (0xb) ; le port ne mirrorait que le premier, donc une
        # ability a `dmg` rendait `(0, 0)` et frappait pour 0 SANS RIEN DIRE.
        _cles = repli_variables_de_degat(cfg)
        if _cles is None:
            # AUCUN des deux helpers natifs ne s'applique : le repli n'a pas de base de degat. On
            # le DIT (le no-op reste un no-op) plutot que de tirer une attaque a bornes nulles,
            # qui se lit comme un coup porte pour 0.
            return {"ability": ability, "target": target, "routed": "no_damage_variable",
                    "variables": sorted((cfg.get("variables") or {}).keys())}
        _min_key, _max_key = _cles
        bmin, bmax, pierce, hits = ability_attack_params(state, uid, _name, profile, ranged=ranged,
                                                        min_key=_min_key, max_key=_max_key)
        r = AttackDamageOperation.execute_ability_attack(state, uid, target, bmin, bmax, pierce, hits,
                                                         damage_profile=profile, is_melee=not ranged)
        return {"ability": ability, "target": target, "routed": "generic_attack",
                "damage_variables": [_min_key, _max_key], "result": r}
    return {"ability": ability, "target": target, "routed": "noop"}


def repli_variables_de_degat(cfg: dict):
    """QUEL helper de degat de `AActiveAbility` ce repli mirrore-t-il ? (#429-r1-r1-r1-r1)

    Le natif n'a PAS de « repli generique » : chaque `<X>Ability$$ExecuteBehaviour` appelle UN
    helper NOMME de `IdunBattle.Entities.Abilities.AActiveAbility` pour construire le noeud de
    degat qu'il passe en 4e argument de `IdunBattleLogic.Entities.DSLBehaviors$$
    AttackWithAttackDamage`. DEUX de ces helpers portent le volet PRINCIPAL, et ils lisent des
    variables DIFFERENTES -- corps LUS, pas devines :

      * `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(abilityState, isPrediction)` :
            min = GetVariableForLevel(config, 0xc, abilityState)     # AbilityVariableType.minDmg
            max = GetVariableForLevel(config, 0xd, abilityState)     # AbilityVariableType.maxDmg
            isPrediction == 0 -> DSLFormulas$$RandomAmount(min, max)          # EXECUTION
            isPrediction != 0 -> DSLFormulas$$Half(Sum(Direct(min), Direct(max)))   # PREDICTION
      * `IdunBattle.Entities.Abilities.AActiveAbility$$DmgDamage(abilityState)` :
            v = GetVariableForLevel(config, 0xb, abilityState)       # AbilityVariableType.dmg
            -> DSLFormulas$$Direct(v)                                # AUCUN tirage

    Le port n'en mirrorait qu'UN (`minDmg`/`maxDmg`, les cles PAR DEFAUT d'
    `ability_attack_params`) : une ability dont la config nomme `dmg` rendait donc `(0, 0)` et le
    repli infligeait **0 SILENCIEUSEMENT**. C'est le residu, et il ne portait sur aucun DEFAUT du
    gate #429-r1-r1-r1 -- sur le repli lui-meme.

    `Direct(v)` est rendu par `bmin == bmax == v`, et c'est EXACT, pas une approximation :
    `HitDamage$$GetDamage` gate `min == max` (cf. `damage_ops/ability.py`), donc ce couple ne
    consomme AUCUN tirage sur le montant -- comme `Direct`. Passer `RandomAmount(v, v)` a la place
    de `Direct(v)` serait donc observationnellement identique cote RNG.

    Rend `(min_key, max_key)` ou `None` quand AUCUN des deux helpers ne s'applique -- et ce `None`
    est le point du correctif : le repli DIT alors qu'il n'a pas de base de degat au lieu d'en
    fabriquer une nulle.

    MESURE DU GISEMENT (2026-08-15, build `t6dpr4k06g`) : sur les **17** abilities qui atteignent
    reellement ce repli (hors `ABILITY_CLASSES` + classees attaque active), **17 portent
    `minDmg`/`maxDmg`** et **0** est dans le cas `dmg` -- l'assiette du residu vaut donc ZERO
    aujourd'hui, et son exemple motivant (`1015 PrecisionShot`) est ENTRE au registre depuis. Le
    correctif est un CLIQUET, pas une reparation d'un ecart vivant : les DEUX abilities du build
    qui nomment `dmg` (`1015 PrecisionShot`, `1091 SlashingDive`) sont au registre, donc a une
    tranche de portage pres de retomber ici. Cliquet executable :
    `probe_429r1r1r1r1_repli_variables_degat.py`."""
    variables = (cfg.get("variables") or {}) if isinstance(cfg, dict) else {}
    _min = AbilityVariableType.minDmg.name
    _max = AbilityVariableType.maxDmg.name
    if _min in variables or _max in variables:
        return _min, _max                       # `AActiveAbility$$MinMaxDamage` (0xc / 0xd)
    _dmg = AbilityVariableType.dmg.name
    if _dmg in variables:
        return _dmg, _dmg                       # `AActiveAbility$$DmgDamage` (0xb) -> `Direct(v)`
    return None


def _is_active_attack_ability(ability_id: int) -> bool:
    """ATTAQUE active (a un `damageProfile`, non-NonComparable, et dont le masque natif n'INTERDIT pas
    la cible ennemie) — délègue au classifieur partagé du bridge (source unique, pas de duplication de
    la classification gameconfig).

    Le veto de masque compte AUSSI ici, et pas seulement pour la décision : ce chemin est le repli
    « attaque générique » (`AttackWithAttackDamage`) d'une ability SANS port dédié. Sans le veto, une
    ability dont la cible native est un ALLIÉ (`TargetIsFriendly`, ex. 1100 SorcerousFacade) faisait
    frapper cet allié par le générique. Avec, elle retombe sur `routed: noop` — le no-op documenté des
    abilities non portées."""
    from engine.ai.state_bridge import _resolve_ability, _is_attack_ability
    _n, cfg = _resolve_ability(ability_id)
    return _is_attack_ability(ability_id, cfg)


# ============================================================================================== #
# `IdunBattle.Core.Services.AiControl` — le service qui fait JOUER une unite par l'IA.
# ============================================================================================== #

def has_action_left(state: State, uid: int) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasActionLeft` = `entityType in {Unit(1),
    Machine(6)} && !UnitFlagsComponent.Has(NoActionAvailable=4)`. Offline toutes les entites du `state`
    portant un `UnitComponent` sont des unites -> seul le flag est teste ; composant absent -> AUCUN flag
    -> action disponible (== natif sur un `UnitFlagsComponent` vide)."""
    e = state.get_entity(uid)
    if e is None or e.get_component(UnitComponent) is None:
        return False
    fl = e.get_component(UnitFlagsComponent)
    return not (fl is not None and fl.has(UnitFlagsComponent.NO_ACTION_AVAILABLE))


def ai_control_execute_for(state: State, uid: int) -> dict:
    """`IdunBattle.Core.Services.AiControl$$ExecuteFor(unit) : UNE passe
    `IdunBattle.AI.DefaultPlayerStrategy$$CalculateNextActionForUnit` (-> `<...>IdunBattle.AI.DefaultPlayerStrategy.u003CCalculateNextActionForUnitu003Ed__7$$MoveNext` ->
    `GetUnitTactic(unit)` puis `tactic.CalculateNextActionForUnit(unit)`) drainee jusqu'au bout, puis
    `IdunBattle.Core.Services.AiControl$$ApplyAiMessages`. **PAS de boucle exterieure** (contraste avec la surcharge groupe).

    Port : `decide_and_apply` = decision playbook (`DefaultAiUnitTactic`) + apply des Operations runner =
    l'equivalent d'UNE passe messages-appliques. Le journal `AIActions`/`DateTime.Now` du natif (pur
    logging) n'est pas porte."""
    return decide_and_apply(state, uid)


def ai_control_execute_movement_for(state: State, uid: int, override_range=None,
                                    override_tile_utility=None) -> dict:
    """`IdunBattle.Core.Services.AiControl$$ExecuteMovementFor(unit, overrideRange,
    overrideTileUtility)` -- corps natif :

        var tactic = this.<+0x10 : IPlayerStrategy>.GetUnitTactic(unit);      // iface
        var it = tactic.CalculateMovementForUnit(unit, overrideRange, overrideTileUtility); // slot 3
        while (it.MoveNext()) { }                                            // drainee
        return this.ApplyAiMessages(it.<messages>);

    et le corps de la coroutine, `IdunBattle.AI.Tactics.DefaultAiUnitTactic.<CalculateMovementForUnit>
    d__8$$MoveNext`, transcrit :

        if (state == null || !UnitExtensions.IsAlive(unit, query)) { yield return new List<>(); }
        else {
            tiles    = ABaseAiUnitTactic$$GenerateActionTiles(this, unit, onlyMove: true, overrideRange);
            mainTile = EntityExtensions$$GetMainTile(unit, query);
            pos      = EntityExtensions$$GetUnitPosition(unit, query);
            action   = this.<+0x58 : MovementActionGenerator>.GenerateActions(unit, pos, tiles,
                                                                              overrideTileUtility);
            if (action != null)
                yield return InputBuilder$$GenerateInputMessagesFromUnitAction(action, unit,
                                                                new UnitPosition(mainTile), flags);
        }

    Port, etage par etage : le gate `IsAlive` ; `GenerateActionTiles(onlyMove: true, overrideRange)`
    = `state_bridge.build_from_state(..., max_distance=override_range)` (son `max_distance` EST le
    3e argument natif, cf. sa docstring) ; le generateur = `action_generators.
    movement_action_with_override` ; l'apply = `apply_action`, qui n'emet un `MoveUnitOperation` que
    si `to != origin` -- c'est le mirror du `if (action != null)` PUIS du fait qu'`InputBuilder`
    n'emet aucun `MoveUnitMessage` pour un deplacement nul (cf. `engine.ai.tactic.
    input_messages_from_unit_action`).

    ⚠ **CE N'EST PAS `ExecuteFor`** : aucune composante ATTAQUE n'est decidee ici (le natif appelle
    le seul `MovementActionGenerator`, pas la liste complete des generateurs). `apply_action` recoit
    donc une action `{"kind": "move"}` sans `ability`, et sa branche attaque ne s'arme pas.

    ⚠ **AUCUN reset/restore de flags de tour**, a la difference de `ComputerActionOperation.execute`
    : `Core.Services.OperationProcessor$$ComputerMovementAction` (slot `IOperationProcessor` **54**,
    3 arguments, LU dans `metadata/ioperationprocessor_slots.tsv`) appelle
    `ComputerActionOperation$$ExecuteMovementFor` DIRECTEMENT, sans le cycle
    `RemoveTurnFlags`/`SetUnitTurnsFlags` que la surcharge `ComputerAction` porte. Ajouter le cycle
    ici ferait bouger des unites qui ont fini leur tour. (#939)"""
    e = state.get_entity(int(uid))
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or not uc.alive:            # `!IsAlive(unit)` -> la coroutine rend une liste VIDE
        return {"uid": int(uid), "skipped": "not-alive"}
    from engine.ai.state_bridge import build_from_state
    from engine.ai.action_generators import movement_action_with_override
    try:
        ctx = build_from_state(state, int(uid), max_distance=override_range)
        action = movement_action_with_override(ctx, override_tile_utility)
    except Exception as ex:                             # pragma: no cover (diagnostic)
        return {"uid": int(uid), "error": repr(ex)}
    return apply_action(state, int(uid), action)


class ComputerMovementActionOperation:
    """`IdunBattle.Operations.ComputerActionOperation$$ExecuteMovementFor(unit, overrideRange,
    overrideTileUtility)` -- le mutateur ECS derriere le slot `IOperationProcessor` **54**
    (`ComputerMovementAction`, 3 arguments), lui-meme la feuille du behaviour DSL
    `PerformAIMovement` (`IdunBattle.Entities.Behaviours.PerformAIMovementBehaviour$$Execute`).

    Le corps natif ne fait QUE deleguer -- `IAiControl.<slot 2>(unit, overrideRange,
    overrideTileUtility)` -> `AiControl$$ExecuteMovementFor` -- d'ou cette classe MINCE, symetrique
    de `ComputerActionOperation` ci-dessous, qui existe pour que le call-site du behaviour cite une
    Operation et non le service. (#939)"""
    __slots__ = ()

    @staticmethod
    def execute(state: State, uid: int, override_range=None, override_tile_utility=None) -> dict:
        return ai_control_execute_movement_for(state, uid, override_range, override_tile_utility)


def ai_control_execute_ability_action_for(state: State, uid: int, ability_id: int,
                                          allow_only_move: bool = False,
                                          move_amount: Optional[int] = None,
                                          custom_utility=None,
                                          range_gate=None) -> Optional[dict]:
    """`IdunBattle.Core.Services.AiControl$$ExecuteAbilityActionFor(unit, abilityType, options)` — la
    SURCHARGE `options` (celle qui prend une struct `{allowOnlyMove, skipAtomicCheck, true,
    Nullable<int> moveAmount, customUtility}`), a ne pas confondre avec la surcharge `movementTiles`
    qui la jouxte au binaire. Corps natif :

        var tactic = this._tactics.GetUnitTacticForUnit(unit);      // this+0x10
        if (tactic == null) return;
        var e = tactic.<slot+1 = CalculateAbilityActionForUnit>(unit, abilityType, options)
                      .GetEnumerator();
        while (e.MoveNext()) { }                                    // draine
        ApplyAiMessages(this, e.Current);

    DIFFERENCE avec `ai_control_execute_for` (= `AiControl$$ExecuteFor`) : l'ability est IMPOSEE par
    l'appelant, la decision passe donc par `CalculateAbilityActionForUnit` (`d__6`) et non par
    `CalculateNextActionForUnit` (`d__5`) — un seul generateur, sur un set d'UNE ability.

    Ce port rend la DECISION (l'action choisie) au lieu de l'appliquer : son unique appelant,
    `PerformAIAbilityUnitBehaviour$$Execute` (`abilities/loki/summon.py`), porte deja l'apply
    (`AttackDamageOperation.execute` + vecteur after-hit) — c'est le meme couple d'Operations que
    `apply_action`, mais avec le diag attendu par ses huit consommateurs.

    `move_amount` = `behaviour+0x78` evalue : `0` (`Direct(0)`, noeud `PerformAIAttackFromCurrentPosition`)
    ou `None` (noeud `PerformAIAttack`). Il est passe TEL QUEL a `GenerateActionTiles` via
    `build_from_state(max_distance=...)` — c'est le 3e argument d'
    `IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles(unit, ignoreFlags: true, overrideRange)`,
    lu VERBATIM au decompile de `...DefaultAiUnitTactic.u003CCalculateAbilityActionForUnitu003Ed__6$$MoveNext`
    (`GenerateActionTiles(tactic, unit, 1, *(d__6+0x34))`) : `0` => la tuile COURANTE seule, `null` => la
    plage de deplacement NORMALE (l'acteur peut s'APPROCHER). #348 l'ouvre ; l'apply du `MoveUnitMessage`
    qu'elle rend indispensable vit chez l'appelant (`perform_ai_ability_unit_behaviour`), et il a ete
    porte AVANT (sans lui, l'attaque serait calculee depuis une tuile ou l'unite n'est pas).

    `range_gate(target_id, tile) -> bool` = la PORTEE EFFECTIVE de l'acteur DEPUIS `tile` (une tuile
    candidate `(col,row)`). Le natif l'applique DANS l'enumeration des cibles eligibles
    (`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsForNormalAttack`
    -> `IdunBattle.Core.Services.TargetingQuery$$GetRange`, qui clampe `Math.Min(1, range)` si l'acteur
    porte `ForcedInMelee (0x529)`), donc AVANT tout argmax d'utilite -- et `EvaluateInternal(unit,
    position, ctx)` le refait POUR CHAQUE position candidate, d'ou l'argument `tile`. Le bridge offline,
    lui, borne les `ranked` par `_max_attack_range` (gameconfig) SANS ce clamp : sans ce gate, le moteur
    pourrait elire une cible que l'acteur ne peut pas frapper, et l'appelant n'aurait plus qu'a ne rien
    faire -- alors que le natif aurait elu la meilleure cible PARMI les atteignables. `None` -> aucun
    filtre. Le filtre porte sur les TUILES de chaque `eval` (et non sur l'eval entier) : un ennemi
    inatteignable depuis l'origine mais atteignable APRES deplacement doit rester candidat.

    AUCUN `try/except` ici, et c'est DELIBERE : un echec du bridge RENDU en « pas d'attaque » se
    lirait comme une mesure (« le natif non plus ne frappe pas »), silencieusement, sur les huit
    consommateurs du corps. On LEVE.

    Rend l'action (`{kind, target, ability, to, util}`) ou `None` (aucun message emis)."""
    from engine.ai.state_bridge import build_from_state
    from engine.ai.tactic import calculate_ability_action_for_unit
    ctx = build_from_state(state, int(uid), max_distance=move_amount)
    if range_gate is not None:
        # `GetEligibleTargetsForNormalAttack` : les cibles hors PORTEE EFFECTIVE ne sont jamais
        # soumises a l'utilite. On elague les TUILES de chaque `eval` (le seul canal de cibles
        # d'attaque) ; un `eval` vide de toute tuile legale disparait.
        plan = ctx.plans.get(int(uid)) or {}
        kept: list = []
        for ev in (plan.get("evals") or []):
            tid = ev.get("targetId")
            ranked = [rk for rk in (ev.get("ranked") or [])
                      if range_gate(tid, (rk.get("col"), rk.get("row")))]
            if not ranked:
                continue
            ev = dict(ev)
            ev["ranked"] = ranked
            ev["rankCount"] = len(ranked)
            kept.append(ev)
        plan["evals"] = kept
    return calculate_ability_action_for_unit(ctx, int(ability_id),
                                             allow_only_move=bool(allow_only_move),
                                             custom_utility=custom_utility)


def ai_control_execute_for_group(state: State, uids: list) -> list:
    """`IdunBattle.Core.Services.AiControl$$ExecuteFor(IEnumerable<Unit> group) : BOUCLE
    `while (messages = DefaultPlayerStrategy.CalculateNextActionForUnitGroup(group)) != empty:
    ApplyAiMessages(messages)`. Le groupe rend UNE unite a la fois via
    `DefaultGroupOperator.<CalculateNextActionForUnitGroup>IdunBattle.AI.OperationalDeciders.DefaultGroupOperator.u003CCalculateNextActionForUnitGroupu003Ed__6$$MoveNext` :
      `u = PickNextUnit(group)` (IdunBattle.AI.OperationalDeciders.DefaultGroupOperator$$PickNextUnit -> `IdunBattle.AI.OperationalDeciders.AnAiGroupOperator$$GetValidUnits` puis le
      picker d'utilite, iface slot 1) ; `if IsDead(u) -> messages vides -> FIN` ; sinon
      `BaseUnitComponent.aiActions@+0x60 += 1` puis `GetUnitTactic(u).CalculateNextActionForUnit(u)`.
    `GetValidUnits` = `HasActionLeft(u) && !IsDead(u) && aiActions < 0x3e9` -> la boucle TERMINE parce
    qu'une unite qui vient de jouer n'a plus d'action disponible.

    Port : meme boucle (validite RE-EVALUEE a chaque tour -> une unite tuee par l'overwatch pendant la
    passe d'une autre est ecartee), une passe `decide_and_apply` par unite, puis on pose
    `NoActionAvailable(4)` (= ce que lit `HasActionLeft`) pour sortir de la boucle -- fidele a l'observe
    live (`UnitStats_ActionsAvailable=0` emis par unite juste apres son action, cascade du cast
    SupremeCommander). Compteur `aiActions` mirroré + cap natif.

    ⚠ RESIDU (documente) : l'ORDRE rendu par le picker natif est un argmax d'UTILITE (iface slot 1,
    poids `operator+0x30`) ; le port garde l'ORDRE DU SELECTEUR. Observe live sur SupremeCommander :
    les 2 gardes agissent dans l'ordre INVERSE de leur spawn -> divergence d'ordre possible (sans
    incidence quand les unites du groupe sont interchangeables, cas des gardes clones)."""
    ai_actions: dict = {}
    results: list = []
    order = [int(u) for u in (uids or [])]
    while True:
        valid = [u for u in order
                 if has_action_left(state, u)
                 and not unit_is_dead(state.get_entity(u))
                 and ai_actions.get(u, 0) < MAX_AI_ACTIONS_PER_UNIT]
        if not valid:
            return results
        uid = valid[0]                                   # PickNextUnit (utilite natif -> ordre selecteur)
        ai_actions[uid] = ai_actions.get(uid, 0) + 1     # BaseUnitComponent+0x60 += 1 (IdunBattle.AI.OperationalDeciders.DefaultGroupOperator.u003CCalculateNextActionForUnitGroupu003Ed__6$$MoveNext)
        try:
            results.append(ai_control_execute_for(state, uid))
        finally:
            # L'unite a joue -> plus d'action disponible. #287-r1 : cette pose passe desormais par
            # le FOYER porte (`MarkUnitAsNoActionAvailableOperation` = le slot 0x76 natif) au lieu
            # d'ecrire le flag a la main -- deux ecritures directes du meme flag seraient deux
            # sources de verite qui divergeraient en silence.
            # Elle reste NECESSAIRE et n'est pas un doublon du branchement de
            # `FinishUnitTurnOperation` : le natif arrive au flag par
            # `AiControl$$ApplyAiMessages` -> `FinishUnitTurn`, chaine que `decide_and_apply` ne
            # joue PAS (il applique directement `MoveUnitOperation`/`AttackDamageOperation`). Sans
            # elle, `GetValidUnits` ne terminerait jamais. Le `get-or-create` d'avant est conserve
            # ici (un summon frais peut n'avoir aucun `UnitFlagsComponent`), la ou l'Operation
            # mirrore le `TryGetComponent` STRICT du natif.
            e = state.get_entity(uid)
            if e is not None:
                if e.get_component(UnitFlagsComponent) is None:
                    e.add_component(UnitFlagsComponent())
                from .turnflow import MarkUnitAsNoActionAvailableOperation
                MarkUnitAsNoActionAvailableOperation.execute(state, uid)


# ============================================================================================== #
# `IdunBattle.Operations.ComputerActionOperation` — l'Operation ECS (mutateur) de l'action AI forcee.
# ============================================================================================== #

class ComputerActionOperation:
    """`IdunBattle.Operations.ComputerActionOperation` — appelee par `Core.Services.OperationProcessor.
    Core.Services.OperationProcessor$$ComputerAction (mono) / Core.Services.OperationProcessor$$ComputerAction (groupe), elle-meme la feuille du behaviour DSL
    `PerformAIAction` (`IdunBattle.Entities.Behaviours.PerformAIActionBehaviour$$Execute`).

    SEMANTIQUE CLE (le detail qui rend le port faux si on le devine) : quand `reset_turn_flags` est vrai,
    l'Operation **retire les flags de tour de la cible AVANT** de la faire jouer, puis les **RESTAURE
    apres** (`IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags(flags, true, true) -> struct sauvegardee ->
    `IdunBattle.Operations.ComputerActionOperation$$SetUnitTurnsFlags). Consequence : l'unite agit MEME si elle avait deja fini son tour, et
    son etat de tour est rendu INCHANGE -> **l'action supplementaire ne consomme pas le tour de la cible**.
    C'est aussi ce qui rend l'action possible : `HasActionLeft` (lu par `GetValidUnits`) teste le flag
    `NoActionAvailable(4)` que le reset vient d'effacer."""
    __slots__ = ()

    @staticmethod
    def _flags(state: State, uid: int) -> Optional[UnitFlagsComponent]:
        """`unit.GetComponent<UnitFlagsComponent>()` — get-or-create : le natif LEVE si le composant
        manque (toute unite native en a un), alors que le spawn offline (`_spawn_config_grot`) n'en pose
        pas ; on le cree pour que le cycle sauvegarde/restauration soit REEL sur les unites deja seedees
        comme sur les summons frais."""
        e = state.get_entity(uid)
        if e is None or e.get_component(UnitComponent) is None:
            return None
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = UnitFlagsComponent()
            e.add_component(fl)
        return fl

    @staticmethod
    def execute(state: State, uid: int, reset_turn_flags: bool) -> dict:
        """`IdunBattle.Operations.ComputerActionOperation$$Execute(Unit, bool) :
            `saved = resetTurnFlags ? RemoveTurnFlags(unit.flags, true, true) : null`
            `IAiControl.ExecuteFor(unit)`                       (iface slot 5)
            `if (resetTurnFlags && saved.HasValue) SetUnitTurnsFlags(unit, saved)`."""
        saved: set = set()
        if reset_turn_flags:
            fl = ComputerActionOperation._flags(state, uid)
            if fl is None:
                return {"uid": uid, "skipped": "no-unit"}
            saved = fl.remove_turn_flags(True, True)     # RemoveTurnFlags(flags, true, true)
        res = ai_control_execute_for(state, uid)
        if reset_turn_flags:
            ComputerActionOperation.set_unit_turns_flags(state, uid, saved)
        return res

    @staticmethod
    def execute_group(state: State, uids: list, reset_turn_flags: bool) -> list:
        """`IdunBattle.Operations.ComputerActionOperation$$Execute(IReadOnlyList<Unit>, bool) : MEME cycle, mais les
        flags de TOUTES les unites sont retires D'ABORD (liste de structs sauvegardees, une par unite,
        indexee par position), PUIS `IAiControl.ExecuteFor(group)` (iface slot 6) joue le groupe entier,
        PUIS chaque unite recoit ses flags d'origine (`SetUnitTurnsFlags(units[i], saved[i])`).
        L'ordre reset-tout / jouer / restaurer-tout est essentiel : pendant que la 1re unite joue, les
        suivantes ont deja leurs flags effaces (elles restent `valid` pour le group operator)."""
        uids = [int(u) for u in (uids or [])]
        saved: list = []
        if reset_turn_flags:
            for uid in uids:
                fl = ComputerActionOperation._flags(state, uid)
                if fl is None:
                    break                                # natif : NRE -> on arrete la collecte
                saved.append((uid, fl.remove_turn_flags(True, True)))
        res = ai_control_execute_for_group(state, uids)
        if reset_turn_flags:
            for uid, flags in saved:
                ComputerActionOperation.set_unit_turns_flags(state, uid, flags)
        return res

    @staticmethod
    def set_unit_turns_flags(state: State, uid: int, flags) -> None:
        """`IdunBattle.Operations.ComputerActionOperation$$SetUnitTurnsFlags : re-`Add` un a un les flags que
        `RemoveTurnFlags` avait effectivement retires (Moved(0), Teleported(0xc), ArrivedAtFinalTile(1),
        NoActionAvailable(4), ActiveAbilityUsed(2), TurnFinished(3), TurnFinishedForced(0x1b))."""
        if not flags:
            return
        fl = ComputerActionOperation._flags(state, uid)
        if fl is None:
            return
        for f in flags:
            fl.add(f)
