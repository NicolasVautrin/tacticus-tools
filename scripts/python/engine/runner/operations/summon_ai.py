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
from ...entities.active_ability_type import ActiveAbilityType

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
        CINQ actions par unite automatique), le port n'en joue qu'UNE. Porter le cap exigerait de
        poser `NoActionAvailable`(4) apres chaque action pour que la boucle TERMINE -- or son seul
        retrait natif est `VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded` (slot 0x77), non
        mirrore : le flag survivrait au `RemoveTurnFlags(includeNoAction=0)` du turn-start et figerait
        l'unite pour toujours. Debloqueur = porter `VerifyUnitTurnEnded`.
      * le `FinishUnitTurn(u, isTerminated: false)` final (meme raison : il porte le
        `MarkUnitAsNoActionAvailable`) ;
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
    from ..events import EventBus
    from .movement import MoveUnitOperation
    from .damage import AttackDamageOperation
    from .triggers import after_move_triggers, after_hit_normal_attack

    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    origin = (pc.col, pc.row) if pc is not None else None
    to = action.get("to")
    res: dict = {"uid": uid, "kind": action.get("kind"), "to": to,
                 "target": action.get("target"), "ability": action.get("ability"),
                 "moved": None, "attack": None}
    # 1. composante MOVE
    if to is not None and tuple(to) != origin:
        MoveUnitOperation(uid, tuple(to)).execute(state, EventBus())
        res["moved"] = tuple(to)
        res["after_move"] = after_move_triggers(state, uid)
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
                _profs = {r.get("profile")} - {None}   # #202-C : set arme + bonus-hits #179
                _profs |= set((r.get("additional_hits") or {}).get("profiles") or [])
                res["after_hit"] = after_hit_normal_attack(
                    state, uid, target, bool(r.get("ranged")), r.get("profile"),
                    is_crit=bool(r.get("did_crit")), profiles=_profs,
                    did_block=bool(r.get("did_block")))
        elif ability is not None:
            res["attack"] = _apply_active_ability(state, uid, target, ability)
    return res


def _apply_active_ability(state: State, uid: int, target: Optional[int], ability: int) -> dict:
    """Apply d'une ability ACTIVE décidée (SLICE 2). Ordre : (1) port DÉDIÉ via le `AbilityHandler`
    (CrushingClaws splash 1105, ScarabHive spawn 1007, ThunderousAssault 1043 — sa behaviour propre
    prime) ; sinon (2) attaque active SANS port dédié -> chemin GÉNÉRIQUE déjà porté
    `execute_ability_attack` (mirror `AttackWithAttackDamage`), config résolue par `ability_attack_params` ;
    sinon (3) no-op (ability non-attaque non portée -> DÉCISION produite, EXÉCUTION offline manquante)."""
    from ..abilities.handler import AbilityHandler
    from ..messages import ActiveAbilityMessage
    from ..abilities.base import ability_attack_params
    from .damage import AttackDamageOperation
    h = AbilityHandler(state)
    h.visit_ActiveAbilityMessage(ActiveAbilityMessage(uid, target, ability))
    if h.last and h.last.get("ported"):
        return {"ability": ability, "target": target, "routed": "handler", "diag": h.last}
    if target is not None and _is_active_attack_ability(ability):
        from engine.ai.state_bridge import _resolve_ability
        _name, cfg = _resolve_ability(ability)
        profile = (cfg.get("constants") or {}).get("damageProfile")
        ranged = (cfg.get("attackRangeType") == "Ranged")
        bmin, bmax, pierce, hits = ability_attack_params(state, uid, _name, profile, ranged=ranged)
        r = AttackDamageOperation.execute_ability_attack(state, uid, target, bmin, bmax, pierce, hits,
                                                         damage_profile=profile, is_melee=not ranged)
        return {"ability": ability, "target": target, "routed": "generic_attack", "result": r}
    return {"ability": ability, "target": target, "routed": "noop"}


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
            e = state.get_entity(uid)                    # l'unite a joue -> plus d'action disponible
            if e is not None:
                fl = e.get_component(UnitFlagsComponent)
                if fl is None:
                    fl = UnitFlagsComponent()
                    e.add_component(fl)
                fl.add(UnitFlagsComponent.NO_ACTION_AVAILABLE)


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
