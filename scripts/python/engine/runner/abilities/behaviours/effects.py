"""Feuilles DSL de POSE/RETRAIT d'effets runner-couplees : `AddBondEffect` (effet BOND source<->target),
`AddEffect` (effet sur unite OU tuile), `IncreaseEffectLevel` (+ la factory composite
`add_effect_or_increase_level`), `RemoveEffect` (retrait + revert StatModification), `SetOnFire`
(effet FEU de tuile), `CreateShield` (bouclier). Wrappers au-dessus de `runner/operations/effects.py` +
`stat_ops.py`. Namespace natif `Entities.Behaviours.*`."""
from __future__ import annotations

from dataclasses import replace          # #448-r6 : lier `ActiveTarget` a la cible COURANTE

from ....dsl.base import TargetsSelector, resolve_unit, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ..base import convert_rounds_to_turns
from ....dsl.base import Const
from ....entities.behaviours import Foreach, If as IfBehaviour
from ....entities.behaviours import If as IfBehaviour, op_and
from ....entities.formulas import CurrentStatModifierAmount
from ....entities.selectors.accessors import Subject
from ....entities.triggers import HasEffect
from ....entities.triggers import Not, AmountIsEqual
from ...components import ShieldComponent
from ...components import StatsComponent
from ...components import unit_state_for_effects
from ...operations.effects import AddEffectOperation
from ...operations.effects import ChangeEffectTurnsOperation
from ...operations.remove_effects import remove_effect_instance
from ...operations.spawn import _materialize_owner_effect
from ...operations.stat_ops import apply_change_stat


def _duration_is_node(duration_turns) -> bool:
    """`duration_turns` est-il un NOEUD `IAmountFormula` (a evaluer) plutot qu'un scalaire ? (#448-r6)"""
    return duration_turns is not None and hasattr(duration_turns, "evaluate")


def _resolve_duration(state, duration_rounds, duration_turns, entities=None):
    """Unite de la duree passee a `AddEffectOperation` (`param_6.NullableA` natif, en TOURS) :

      * `duration_turns` (prioritaire) = duree DEJA en tours -- mirror d'un noeud `Direct(n)@0xc0` ou
        d'un `Nullable<int>(n)` litteral cote natif : le decompile la met telle quelle dans `param_6`,
        `IdunBattle.Operations.AddEffectOperation$$Execute` ne la convertit PAS.
      * `duration_rounds` = un noeud `TurnsFromRounds(n)` natif -> `convert_rounds_to_turns(state, n)`
        (`IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`).
      * `None` des deux -> pas d'override : la duree vient de `DefaultAmountOfRounds`, convertie DANS
        `AddEffectOperation` (mirror de la branche « pas d'override » du decompile).

    #448-r6 -- `duration_turns` accepte desormais un NOEUD (`IAmountFormula`), et pas seulement un
    scalaire. C'est ce qu'EST le champ `AbilityEntities+0x78` cote natif, et l'appelant
    (`AddEffectBehaviour$$Execute`) l'evalue **DANS SA BOUCLE DE CIBLES**, apres avoir ecrit
    l'entite courante dans `AbilityEntities+0x20` -- lu VERBATIM au decompile :

        foreach (unit in <cibles>) {
            if (UnitExtensions.HasFlag(unit, UnitFlag.Dead = 6)) continue;
            processor[+0x20] = unit;                              // <-- AVANT l'evaluation
            turns = (entities+0x78 != null) ? Nullable(<+0x78>.Calculate(processor)) : null;
            ...
        }

    Un `TurnsUntilUnitOwnerTurn(ActiveTarget)` y vaut donc la valeur de LA cible en cours, PAS le
    `Max` du set. `entities` doit alors etre le contexte PAR CIBLE (`replace(entities,
    active_target=<cible>)`) ; l'omettre sur un noeud rendrait `None` plutot qu'une valeur fausse."""
    if _duration_is_node(duration_turns):
        if entities is None:
            return None                              # aucun contexte : on ne DEVINE pas une duree
        v = duration_turns.evaluate(entities)
        return None if v is None else int(v)
    if duration_turns is not None:
        return int(duration_turns)
    if duration_rounds is not None:
        return convert_rounds_to_turns(state, duration_rounds)
    return None


def _source_scaling(state, source_id):
    """Parametres de SCALING (§17.21) de l'unite `source_id` = l'equivalent PORT de l'
    `AbilityStateReference` natif : un effet materialise resout ses `ConfigVar` contre l'etat d'ability
    de SA SOURCE (`GetAbilityState(effect)`), donc contre le niveau d'ability + le multiplier de rarete
    de l'unite qui l'a pose. Rend `(multiplier_pct, ability_level, active_ability_level)` ; (None, None,
    None) si l'unite n'a pas de `StatsComponent` (l'effet retombe alors sur les defauts historiques)."""
    e = state.get_entity(source_id) if (state is not None and source_id is not None) else None
    sc = e.get_component(StatsComponent) if e is not None else None
    ctx = getattr(sc, "ctx", None) if sc is not None else None
    if ctx is None:
        return (None, None, None)
    passive = getattr(ctx, "passive_ability_level", None)
    active = getattr(ctx, "active_ability_level", None)
    return (int(getattr(ctx, "ability_variables_multiplier", 100) or 100),
            passive if passive is not None else active, active)


class AddBondEffect(AbilityBehaviour):
    """`DSLFactory.AddBondEffect(0x1b, stateRef, source, target, ..., TurnsFromRounds(1)) IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$TauntWithNewChildrenWhoDidDamage` : pose
    l'effet BOND `Taunted_OnlySpecificTargets` (0x1b=27, COMPOSITE 25/26/1237) reliant `source` (l'enfant/
    grot) et `target` (`LastUnitAttackedBy` = l'ennemi frappe), duree `TurnsFromRounds(rounds)`. Wrapper
    MINCE au-dessus de `AddEffectOperation.execute` (mirror exact de l'imperatif : source=grot, target=
    ennemi). `source_ref`/`target_ref` = Nodes resolus au dict courant -> ids. No-op si source/target
    absents. Emet 'AddBondEffect'. Effet PUR (stop=False).

    `duration_rounds` = nb de rounds (`TurnsFromRounds(rounds)`) ; `None` = duree DEFAUT de l'effet
    (`DefaultAmountOfRounds`, mirror de l'arg natif duree-node ZERO d'`AddBondEffect` SANS `TurnsFromRounds`
    -- ex. ValkyrieStrike 1022 : arg7 = struct zero-initialise, PAS un `TurnsFromRounds(n)` explicite) vs
    explicite (CrushingClaws Taunt / GetEmRuntz = `TurnsFromRounds(1)`). MEME semantique None que `AddEffect`.
    `duration_turns` = duree deja en TOURS (noeud `Direct(n)`/`Nullable(n)` natif, NON converti) ;
    prioritaire sur `duration_rounds`. Cf. `_resolve_duration` et `AddEffect`.

    Le natif ITERE son selecteur-cible (meme mold qu'`AddEffectBehaviour`) et ses cibles sont des ENTITES
    (unites OU tuiles) : `IdunBattleLogic.Entities.Abilities.Active.Loki.MalleusRocketLauncherAbility$$ExecuteBehaviour` et
    `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour` bondent sur des TUILES. Le port itere donc
    `_add_effect_targets` / `_add_effect_target_id` (les call-sites MONO-unite historiques — `Target()`,
    `LastUnitAttackedBy(child)` — rendent 1 element -> chemin identique).

    `bonded_ref` = le **5e argument natif** d'`IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect`
    (`bondedEntity`, un `ITargetsSelector` que la factory range dans les `AddEffectBehaviourOptions`).
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$GetEffectBuilder` le resout A L'EXECUTION
    (`this+0x70` -> `SelectSingle` -> `EntityId`) et bascule sur
    `…AddEffectBehaviour$$DefaultBondEffectBuilder`, qui ECRIT cet id dans le composant de bond de
    l'entite-effet (`+0x10`) — ce que relit `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`.
    Un id NUL laisse le builder ORDINAIRE (aucun bond). D'ou : `bonded_ref=None` ici = pas de bonded
    porte -> `BaseEffect.bonded` reste None (comportement historique, INCHANGE pour les call-sites qui
    ne le renseignent pas encore).

    `scale_from_source` = le **3e argument natif** `abilityState` d'`IdunBattleLogic.Entities.
    DSLBehaviors$$AddBondEffect`, que la factory transmet tel quel a
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$.ctor` : l'entite-effet BAKE l'etat d'ability
    du POSEUR, et c'est CET etat que relit `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState`
    quand un `ConfigVar` de l'effet materialise doit s'indexer. Semantique et implementation
    STRICTEMENT identiques a l'homonyme d'`AddEffect` (meme `_source_scaling`, meme `#382
    baked_ability_state`) -- ce parametre n'existait pas ici parce qu'aucun call-site porte n'en avait
    besoin. Defaut False = comportement historique, INCHANGE pour les trois call-sites existants
    (`MalleusRocketLauncher`, `TunnelingHorror`, `GetEmRuntz`)."""
    __slots__ = ("effect_type", "name", "source_ref", "target_ref", "duration_rounds", "duration_turns",
                 "bonded_ref", "scale_from_source")

    def __init__(self, effect_type: int, name: str, source_ref: TargetsSelector, target_ref: TargetsSelector,
                 duration_rounds=1, duration_turns=None, bonded_ref: TargetsSelector = None,
                 scale_from_source: bool = False):
        self.effect_type, self.name = effect_type, name
        self.source_ref, self.target_ref = source_ref, target_ref
        self.duration_rounds = duration_rounds
        self.duration_turns = duration_turns
        self.bonded_ref = bonded_ref
        self.scale_from_source = bool(scale_from_source)

    def execute(self, entities, ectx):
        state = ectx.state
        su = resolve_unit(self.source_ref, entities)
        src = su.get("id") if su else None
        if src is None or state is None:
            return OperationResult.ok()
        # duration_rounds None -> pas d'override = duree DEFAUT (DefaultAmountOfRounds), mirror de l'arg natif
        # duree-node ZERO d'AddBondEffect sans TurnsFromRounds (ValkyrieStrike 1022) ; sinon
        # `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns(rounds) (mirror du noeud `TurnsFromRounds`). `duration_turns`
        # (noeud Direct(n)/Nullable(n), deja en TOURS) est prioritaire et N'EST PAS converti.
        dur = _resolve_duration(state, self.duration_rounds, self.duration_turns)
        # `GetEffectBuilder` resout le selecteur `bondedEntity` (options `+0x70`) DANS la boucle des
        # cibles, en `SelectSingle` puis `EntityId`. Le port l'evalue au MEME contexte `entities`.
        # ECART NOMME : le natif a deja ecrit la cible COURANTE dans le slot `Target` du contexte
        # (`param_3[4] = lVar7`) quand il appelle `GetEffectBuilder` ; le port evalue le selecteur au
        # contexte d'entree. Sans effet pour tout `bondedEntity` qui ne depend PAS de la cible courante
        # (`Self@0x148` de `HazeOfCorruption_TargetFinderAbility`, seul call-site renseigne a ce jour).
        bu = resolve_unit(self.bonded_ref, entities) if self.bonded_ref is not None else None
        bonded = bu.get("id") if bu else None
        # `abilityState` (3e argument natif) : l'entite-effet bake l'etat d'ability du POSEUR.
        mult, ab_lvl, act_lvl = (_source_scaling(state, src) if self.scale_from_source
                                 else (None, None, None))
        for elem in _add_effect_targets(self.target_ref.evaluate(entities)):
            tgt = _add_effect_target_id(elem, state)     # unit dict->id | (col,row)/int -> tile id
            if tgt is None:
                continue
            AddEffectOperation.execute(state, source=src, target=tgt, effect_type=self.effect_type,
                                       name=self.name, duration_override=dur, bonded=bonded,
                                       ability_level=ab_lvl, active_ability_level=act_lvl,
                                       multiplier_pct=mult)
            ectx.emit("AddBondEffect", source=src, target=tgt, effect_type=self.effect_type,
                      bonded=bonded)
        return OperationResult.ok()


def _add_effect_targets(raw):
    """Normalise la sortie du selecteur-cible d'`AddEffect` en LISTE d'elements a poser (mirror de
    l'iteration native du selecteur par `AddEffectBehaviour`) : un dict d'unite / une position (col,row)
    NUE -> `[elem]` ; une liste (d'unites ou de tuiles) -> telle quelle ; None -> `[]`."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [raw]
    if (isinstance(raw, tuple) and len(raw) == 2
            and all(isinstance(x, int) and not isinstance(x, bool) for x in raw)):
        return [raw]                      # position (col,row) NUE (ex. TargetTile / Tiles scalaire)
    return list(raw)


def _add_effect_target_id(elem, state):
    """Resout UN element du selecteur-cible en id-cible ECS pour `AddEffectOperation` : dict d'unite -> son
    id (unit-effect) ; position (col,row) -> l'id de TUILE via `board.id_at` (tile-effect, ex. `Tiles(target)`
    d'OnFireDamage) ; int -> deja un id de tuile (domaine `AdjacentTiles`). None si non resolvable. Mirror du
    natif `AddEffectBehaviour.Execute` : le selecteur rend des ENTITES ECS (unites OU tuiles)."""
    if isinstance(elem, dict):
        return elem.get("id")
    if isinstance(elem, bool):            # garde: bool est un int en Python
        return None
    if isinstance(elem, int):
        return elem                       # id de tuile deja resolu
    if (isinstance(elem, (tuple, list)) and len(elem) == 2
            and all(isinstance(x, int) and not isinstance(x, bool) for x in elem)):
        board = getattr(state, "board", None)          # position (col,row) -> id de tuile
        return board.id_at(elem[0], elem[1]) if board is not None else None
    return None


def _placed_effect_is_active(state, target_id, eff) -> bool:
    """L'instance qui vient d'etre posee CONTRIBUE-t-elle, a CET instant ? (`placed` ne le dit pas.)

    Predicat = celui d'`EffectsState.active_effects` : le FLAG `EffectComponent.IsActive @+0x5c`
    ET la `CreateActiveCondition` de la classe (`<Effect>$$CreateActiveCondition`), evaluee contre
    `unit_state_for_effects` -- le foyer unique du contexte, #208. Les deux conjoints sont ceux
    qu'evalue `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` avant que
    `UpdateEffectTargets` -> `ApplyEffectsForTargets` ne joue le `<Effect>.ApplyInternal` : un effet
    dont la condition est fausse est materialise mais n'APPLIQUE RIEN.

    POURQUOI CE CHAMP EXISTE (#462-r4b) : le canal LIVE d'un cast publie un GROUPE d'evenement par
    effet qui APPLIQUE quelque chose (`applyAction.events[kind == group].source`). Un effet pose
    INERTE n'emet aucun groupe -- l'observable live est donc « pose ET contribuant », pris A
    L'INSTANT DE LA POSE. Cote port, le seul pendant lisible etait `EffectsState.active_effects` sur
    l'etat FINAL, qui n'est PAS le meme observable des que l'effet disparait avant la fin de la
    chaine. MESURE (`probe_462r4b_pinned_active_after_chain.py`, `ExemplarOfHate` sur
    `blackPossession`) : l'attaque libre de la chaine TUE la cible des DEUX cotes (live
    8034 -> 0 `isDead`, port 8034 -> 0 `alive=False`), et la sequence de mort
    (`IdunBattle.Operations.KillUnitOperation$$RemoveEffects` -> `RemoveEffectsOperation$$Execute`)
    retire TOUS les effets du mort -- live `decisionView.effects` post-cast = `[]`, port `consumed`.
    Les deux moteurs sont d'ACCORD ; c'etait la LECTURE qui comparait deux canaux non homologues.

    `eff is None` (cible nulle, gate d'immunite, effet deja present) -> False : rien n'a ete
    materialise, donc rien n'applique."""
    if eff is None or state is None or target_id is None:
        return False
    return bool(eff.active) and bool(eff.is_active(unit_state_for_effects(state, int(target_id))))


class AddEffect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$AddEffect` -> `AddEffectBehaviour.Execute` : pose un effet, `source` =
    `AbilityStateReference` (= le caster), sur CHAQUE cible du selecteur `target_sel`, duree
    `TurnsFromRounds(rounds)`. Wrapper MINCE au-dessus de `AddEffectOperation.execute` (mirror exact de
    l'imperatif). DIFFERE de `AddBondEffect` (qui LIE source+target = deux unites distinctes) : ici la source
    EST le caster. Emet 'AddEffect' par cible (payload `placed` = l'effet a-t-il ete REELLEMENT pose, i.e.
    `AddEffectOperation` non-None : False si deja present / cible nulle -> laisse l'appelant distinguer la
    re-pose no-op, cf. OnFireDamage ; payload `active` = l'instance posee CONTRIBUE-t-elle a cet instant,
    cf. `_placed_effect_is_active` -- c'est le pendant EXACT du groupe d'evenement live, `placed` seul ne
    distinguant pas une pose INERTE d'une pose contribuante). Effet PUR (stop=False).

    Le natif `AddEffectBehaviour` ITERE son selecteur-cible, qui rend des ENTITES ECS (UNITES ou TUILES) :
    - unit-domain (`Target()`/`Subject()`) -> effet sur l'unite (Stunned/Pinned de ThunderousAssault/
      CrushingClaws/SpiritLeech ; selecteurs mono-cible = 1 element -> chemin bit-IDENTIQUE a l'ancien
      `resolve_unit`) ;
    - tile-domain (`Tiles(Target())` d'OnFireDamage IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateBehaviour) -> effet de TUILE (le selecteur rend la
      MainTile de la cible ; `_add_effect_target_id` la convertit en id de tuile). MEME `AddEffectOperation`.

    `duration_rounds` = nb de rounds (`TurnsFromRounds(rounds)`) ; `None` = duree DEFAUT de l'effet
    (`DefaultAmountOfRounds`, mirror de l'arg natif `0` d'`AddEffect` SANS `TurnsFromRounds` — ex. Pinned de
    CrushingClaws) vs explicite (ThunderousAssault Stunned = `TurnsFromRounds(1)`).
    `duration_turns` = duree deja en TOURS (le natif passe un noeud `Direct(n)@0xc0` ou un `Nullable<int>(n)`
    litteral, PAS un `TurnsFromRounds`) — PRIORITAIRE sur `duration_rounds`, cf. `_resolve_duration`.

    `level` = niveau de STACK initial (slot niveau de la struct d'options natives) — utilise par la branche
    AddEffect du lambda `AddEffectOrIncreaseLevel b__0 IdunBattleLogic.Entities.DSLFactory.u003Cu003Ec__DisplayClass569_0$$u003CAddEffectOrIncreaseLevelu003Eb__0` (la 1re pose demarre au niveau
    = INCREMENT) ; None = pas de niveau porte (tous les autres call-sites).
    `scale_from_source` = le PORT de l'`AbilityStateReference` : l'effet materialise resout ses `ConfigVar`
    contre l'etat d'ability de sa SOURCE (niveau d'ability + multiplier de rarete du caster). Opt-in
    (defaut False = comportement historique) pour les effets dont la MAGNITUDE vient d'un ConfigVar
    (FleshmetalGuns 1067/1212/1221, TerrifyingCrescendo 1424).
    """
    __slots__ = ("effect_type", "name", "target_sel", "duration_rounds", "level", "scale_from_source",
                 "duration_turns", "source_ref", "source_from_target", "ability_state")

    def __init__(self, effect_type: int, name: str, target_sel: TargetsSelector, duration_rounds=1,
                 level=None, scale_from_source: bool = False, duration_turns=None, source_ref=None,
                 source_from_target: bool = False, ability_state=None):
        self.effect_type, self.name = effect_type, name
        self.target_sel, self.duration_rounds = target_sel, duration_rounds
        self.level, self.scale_from_source = level, scale_from_source
        self.duration_turns = duration_turns
        # `ability_state` = le 2e argument NATIF d'`AddEffectBehaviour..ctor` (`abilityState`), passe
        # EXPLICITEMENT sous la forme d'un couple deja resolu `(ability_level, multiplier_pct)`.
        #
        # POURQUOI IL NE SE DEDUIT PAS DE `scale_from_source` (#999-r1). Ce dernier lit
        # `_source_scaling`, qui rend le couple des **PASSIFS** de la source (`passive_ability_level`,
        # `ability_variables_multiplier`). C'est exact tant que l'ability qui POSE est un passif ou
        # une active du porteur. Ca ne l'est PAS quand elle est **TERTIAIRE** (relique, ou mythique de
        # MoW) : `IdunBattle.Entities.Factories.UnitFactory$$Build` fabrique alors un TROISIEME
        # `AbilityState` -- `(config+0xc0 TertiaryAbilityLevel, config+0x78)`, soit `level 1..4 /
        # mult 100` -- que `AddConfiguredAbilities` distribue a la hierarchie 3, et c'est CELUI-LA que
        # `get_AbilityStateReference(this)` rend. Le couple passif d'un runner normalise vaut
        # `50 / 180` : `Idun.Shared.Level$$ToZeroBasedIndex(50)` clampe au DERNIER palier, donc un
        # `ConfigVar` a quatre paliers y lirait toujours le maximum. MEME cause que #1005 / #1009, et
        # MEME couple que `triggers/base.py::triggered_ability_state`, qui est la voie recommandee
        # pour le calculer au site d'appel.
        #
        # ⚠ Il l'emporte sur `scale_from_source` quand les deux sont donnes -- l'explicite prime sur
        # le derive. `None` (defaut) = comportement STRICTEMENT inchange pour tous les call-sites
        # anterieurs, qui n'en passent aucun.
        self.ability_state = ability_state
        # `source_ref` = le 4e argument NATIF d'`IdunBattleLogic.Entities.DSLFactory$$AddEffect` (le noeud
        # SOURCE, `AddEffectBehaviour..ctor` param_4) : `caster@0x160` / `Owner@0x148` sur la quasi-totalite
        # des call-sites -> defaut None = le caster (comportement historique INCHANGE).
        # `IdunBattleLogic.Entities.Abilities.Active.PlagueburstMortarAbility$$ExecuteBehaviour` passe
        # `target@0x178` comme source de son effet de TUILE Contaminated -> d'ou le parametre.
        self.source_ref = source_ref
        # `source_from_target` = mirror du FALLBACK natif quand le selecteur SOURCE est NULL. Lu dans
        # `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` : `+0x60` (source) et `+0x68`
        # (cibles) sont deux selecteurs ; la boucle sur les cibles fait
        #     `lVar14 = <cible courante>; if (<resultat du selecteur source> != 0) lVar14 = <ce resultat>;`
        # puis passe `lVar14` en SOURCE a l'operation. Autrement dit : **selecteur source absent =>
        # la source EST la cible**, PAS le caster.
        # Le declenche : la surcharge 4-args `IdunBattleLogic.Entities.DSLFactory$$AddEffect(effectType,
        # stateRef, targets)`, qui passe litteralement `0` en `+0x60` (les surcharges 6-args, elles,
        # posent une source explicite). Call-sites portes : le FEU de
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour`
        # (`AddEffect(5 Fire, stateRef, TargetTiles@0x190)`) et le CONTAMINATED de
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$ExecuteBehaviour`
        # (`AddEffect(0x4dc, stateRef, GetAffectedTiles())`) -> chaque TUILE est sa propre source.
        # Defaut False = comportement historique (source = caster), INCHANGE pour tous les autres.
        self.source_from_target = bool(source_from_target)

    def execute(self, entities, ectx):
        state = ectx.state
        if self.source_ref is not None:                       # noeud SOURCE natif explicite (param_4)
            # Domaine MIXTE : le natif stocke une ENTITE dans `EffectComponent.SourceUnit @+0x10` --
            # unite OU tuile (PlagueburstMortar passe `target@0x178` = la TUILE ciblee).
            raw = self.source_ref.evaluate(entities)
            src = _add_effect_target_id(
                (raw[0] if isinstance(raw, (list, tuple)) and raw and not (
                    len(raw) == 2 and all(isinstance(x, int) and not isinstance(x, bool) for x in raw))
                 else raw), state)
        elif self.source_from_target:
            src = None                                        # resolue PAR CIBLE dans la boucle (fallback natif)
        else:
            src = (entities.caster or {}).get("id")           # AbilityStateReference = caster (source)
        if state is None or (src is None and not self.source_from_target):
            return OperationResult.ok()
        # duration_rounds None -> pas d'override = duree DEFAUT (DefaultAmountOfRounds), mirror de l'arg natif
        # `0` d'AddEffect sans TurnsFromRounds (Pinned CrushingClaws) ; sinon `ConvertRoundsToTurns(rounds)`
        # IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns. `duration_turns` court-circuite (noeud Direct/Nullable natif, deja en TOURS).
        # #448-r6 : un `duration_turns` NOEUD est evalue PAR CIBLE dans la boucle ci-dessous (le
        # natif ecrit `processor[+0x20] = unit` AVANT d'evaluer `entities+0x78`) ; un scalaire, lui,
        # se resout une fois. `_duration_is_node` sépare les deux régimes.
        _dur_node = _duration_is_node(self.duration_turns)
        dur = (None if _dur_node
               else _resolve_duration(state, self.duration_rounds, self.duration_turns))
        lvl = (self.level.evaluate(entities) if hasattr(self.level, "evaluate")
               else self.level)
        # `scale_from_source` porte le 3e argument natif d'`AddEffectBehaviour..ctor`
        # (`abilityState`), qui est un objet **DISTINCT** du 4e (`source`) que `src` porte -- et
        # les deux ne coincident pas toujours. Sur tous les call-sites d'avant #906 ils
        # coincidaient (`source_ref = Caster()`, ou le defaut `src = caster`), donc lire le scaling
        # sur `src` etait exact. La surcharge 4-args
        # `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(effectType, abilityState, targets,
        # turns)` les DISSOCIE : son corps passe litteralement `0` en `source` (d'ou
        # `source_from_target`) tout en transmettant l'`abilityState` recu -- et
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfMorkaiAbility$$ExecuteBehaviour` y
        # passe `AActiveAbility$$get_AbilityStateReference` =
        # `DSLSelectors$$AbilityState(Caster@DSLSelectors+0x48, <l'active courante>)`, donc l'etat
        # d'ability du **CASTER**. Lire le scaling sur la cible y donnerait le niveau et le
        # multiplicateur de rarete du BUFFE : mesure du 2026-08-11 sur la config `RitesOfMorkai`,
        # `extraDmg` et `hp` sont TOUS DEUX dans `variablesAffectedByRarityBonus`, et les
        # multiplicateurs different d'une unite a l'autre (mesure #585 : 200 vs 180) -- l'ecart
        # serait donc numerique et SILENCIEUX.
        scale_src = (entities.caster or {}).get("id") if self.source_from_target else src
        mult, ab_lvl, act_lvl = (_source_scaling(state, scale_src) if self.scale_from_source
                                 else (None, None, None))
        # `abilityState` EXPLICITE (2e argument natif) -- il PRIME sur le derive ci-dessus. Cf. la
        # docstring du parametre : c'est la seule ecriture correcte quand l'ability qui pose est
        # TERTIAIRE, dont l'`AbilityState` (`level 1..4 / mult 100`) n'est celui d'AUCUN passif.
        if self.ability_state is not None:
            ab_lvl, mult = self.ability_state
        for elem in _add_effect_targets(self.target_sel.evaluate(entities)):  # natif : itere le selecteur
            tgt = _add_effect_target_id(elem, state)          # unit dict->id | (col,row)->tile id | int->tile id
            if tgt is None:
                continue
            if self.source_from_target:                       # selecteur SOURCE natif NULL -> source = cible
                src = tgt
            if _dur_node:
                # `processor[+0x20] = unit` PUIS `<+0x78>.Calculate(processor)` -- l'ordre est LU.
                dur = _resolve_duration(state, self.duration_rounds, self.duration_turns,
                                        replace(entities, active_target=elem))
            eff = AddEffectOperation.execute(state, source=src, target=tgt, effect_type=self.effect_type,
                                             name=self.name, duration_override=dur,
                                             level=(None if lvl is None else int(lvl)),
                                             ability_level=ab_lvl, active_ability_level=act_lvl,
                                             multiplier_pct=mult)
            ectx.emit("AddEffect", source=src, target=tgt, effect_type=self.effect_type,
                      placed=eff is not None, active=_placed_effect_is_active(state, tgt, eff),
                      level=(None if lvl is None else int(lvl)))
        # `stop` JAMAIS pose, quel que soit le sort de l'operation (refus d'immunite, cible morte,
        # cible nulle, effet deja present) : `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute`
        # ZERO-INITIALISE son `OperationResult` de retour et ne le reecrit jamais -- la valeur rendue par
        # `IdunBattle.Operations.AddEffectOperation$$Execute` (l'entite-effet, `0` sur chaque gate) est
        # appelee via le slot 0x10 du processeur et JETEE. Cf. `Seq` (entities/behaviours.py) et N5.
        return OperationResult.ok()


class IncreaseEffectLevel(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$IncreaseEffectLevel` -> `IdunBattle.Entities.Behaviours.IncreaseEffectLevelBehaviour$$Execute`
    -> `IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute` : incremente le NIVEAU (`EffectComponent.Level
    @+0x68`) des instances d'effet `effect_type` portees par les cibles du selecteur, avec CAP optionnel.

    Mirror EXACT du clamp natif (IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute) :
    ```
    if (!max.HasValue || max.Value < cur || cur + amount <= max.Value)  level = cur + amount
    else                                                               level = max.Value
    ```
    (quirk natif conserve : un niveau DEJA au-dessus du cap continue d'etre incremente -- branche
    `max.Value < cur`). Gate natif `StaticBattleRules.Effect.HasLevel(effectType)` = l'effet supporte un
    niveau ; offline on l'assure par la presence d'une instance materialisee du type.
    `amount`/`max_level` = scalaires ou noeuds VALEUR (`.evaluate`). Emet 'IncreaseEffectLevel' par cible.
    Effet PUR (stop=False)."""
    __slots__ = ("effect_type", "target_sel", "amount", "max_level")

    def __init__(self, effect_type: int, target_sel: TargetsSelector, amount, max_level=None):
        self.effect_type, self.target_sel = int(effect_type), target_sel
        self.amount, self.max_level = amount, max_level

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None or state.effects is None:
            return OperationResult.ok()
        amt = int(self.amount.evaluate(entities) if hasattr(self.amount, "evaluate") else self.amount)
        mx = self.max_level
        if mx is not None:
            mx = int(mx.evaluate(entities) if hasattr(mx, "evaluate") else mx)
        for tu in _units_of(self.target_sel, entities):
            tgt = tu.get("id") if isinstance(tu, dict) else None
            if tgt is None:
                continue
            for eff in state.effects.by_unit.get(int(tgt), []):
                if eff.consumed or eff.effect_type != self.effect_type:
                    continue
                cur = int(eff.level or 0)
                if mx is None or mx < cur or cur + amt <= mx:      # mirror IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute
                    eff.level = cur + amt
                else:
                    eff.level = mx
                ectx.emit("IncreaseEffectLevel", target=tgt, effect_type=self.effect_type,
                          level=eff.level, amount=amt, max_level=mx)
        return OperationResult.ok()


def add_effect_or_increase_level(effect_type: int, name: str, target_sel: TargetsSelector,
                                 amount, max_level=None, duration_rounds=0,
                                 scale_from_source: bool = True):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddEffectOrIncreaseLevel(effectType, stateRef, subject, selector, amount, max)` — factory COMPOSITE : le natif alloue un `ForeachBehaviour(selector, Func<entity,
    behaviour>)` dont le lambda `b__0 IdunBattleLogic.Entities.DSLFactory.u003Cu003Ec__DisplayClass569_0$$u003CAddEffectOrIncreaseLevelu003Eb__0` construit, PAR ELEMENT :

        If( HasEffect(elem, effectType),
            IncreaseEffectLevel(elem, effectType, amount, max),      # then
            AddEffect(effectType, stateRef, subject, elem, {level = amount}) )   # else

    On MIRRORE cet arbre (Foreach + If/else + les 2 feuilles) au lieu de le collapser : c'est un noeud de
    la FACTORY, pas une Operation. Call-sites portes : `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrifyingCrescendoAbility$$CreateBehaviour` (0x590=1424, amount=Const(1)@0xc0, max=Direct(GetNumberConstant(0x62)=buffMaxLevel)) ;
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HeadClaimerAbility$$CreateBehaviour` (0x404/0x405, amount=Const(1), max=NULL).

    `duration_rounds=0` = la duree ZERO du natif (l'options-struct ne porte pas de `TurnsFromRounds`) ->
    `remaining=0` = PERMANENT cote port (`EffectFactory.create` mappe rem<=0 -> None), conforme au live
    (`TerrifyingCrescendo` rem=0, buff cumulatif sur la bataille)."""
    return Foreach(target_sel, lambda _sub: IfBehaviour(
        HasEffect(Subject(), int(effect_type)),
        IncreaseEffectLevel(effect_type, Subject(), amount, max_level),
        AddEffect(effect_type, name, Subject(), duration_rounds=duration_rounds,
                  level=amount, scale_from_source=scale_from_source)))


class RemoveEffect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$RemoveEffect` -> `RemoveEffectBehaviour.Execute` : retire de la cible TOUS les
    effets du type `effect_type` (non consommes), ANNULE leur StatModification (`<Effect>.RevertInternal`)
    et DE-ENREGISTRE leur nom de l'`EffectsOwnedComponent` (mirror `IdunBattle.Operations.
    RemoveEffectOperation$$Execute`, qui retire l'id de l'entite-effet d'`ActiveEffectIds`) des qu'aucune
    instance non consommee du meme nom ne reste — sans quoi un couple pose/retire dans le MEME cast
    (`AddStatOverrideEffect(0x510)`/`RemoveEffect(0x510)`, `AddEffect(0x529)`/`RemoveEffect(0x529)` de
    TheQuickening, reset ActOfFaith...) laissait son NOM colle sur l'unite, visible de la couche decision.
    `target` = `target_sel` (ex. `Caster()`/`Self@0x148` pour le reset ActOfFaith IdunBattleLogic.Entities.Abilities.Active.Loki.ActOfFaith_RemoveEffectAbility$$CreateBehaviour). Wrapper au-dessus
    de l'Operation impurative `revert_change_stat` (mirror exact de l'ancien `_reset_act_of_faith`). No-op si
    `state.effects`/cible absents. Emet 'RemoveEffect' PAR CIBLE (removed = nb de stacks retires). Effet PUR
    (stop=False).

    Le natif ITERE son selecteur-cible (`RemoveEffectsBehaviour`, meme mold que `AddEffectBehaviour`) : le port
    itere donc `_units_of(target_sel)` — les call-sites MONO-cible historiques (`Caster()`) rendent une liste
    d'1 element -> chemin bit-IDENTIQUE ; le call-site MULTI-cible est
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.MasterAnnihilatorAbility$$CreateBehaviour` (`OwnerOfEffect(EffectsFromUnitSource(...))`).

    Frontiere classification (#149) : le NOEUD `RemoveEffect` (declaratif) au-dessus ; `ReverseModification`
    (revert par-source, impuratif) EN DESSOUS. L'effet DECLARE ses StatTypes revertes (`reverted_stats()`, DATA
    cote `entities/`) ; la feuille (runner/) EXECUTE le revert (`revert_change_stat`, couche runner) sur chacun,
    keye par `effect_stat_mod_key(eff)` = la cle de POSE si elle existe, sinon la cle DERIVEE
    `statmod_source_key` sous laquelle l'ATTRIBUTION DU SEED a ecrit la contribution (#118 : un stack SEEDE
    etait retire mais NON reverte, sa contribution restait dans le `UnitStats`)."""
    __slots__ = ("effect_type", "target_sel")

    def __init__(self, effect_type: int, target_sel: TargetsSelector):
        self.effect_type, self.target_sel = int(effect_type), target_sel

    def execute(self, entities, ectx):
        # #389-r2 : le corps `RemoveEffectOperation$$Execute` (les deux events `On(0x3f = PreEffectRemoved)`/`On(0x40 = EffectRemoved)`
        # encadrant les trois reverts, puis `ActiveEffectIds.Remove`) vit desormais dans
        # `operations/remove_effects.py::remove_effect_instance` -- foyer PARTAGE avec le
        # `RemoveEffects` de la sequence de mort (`KillUnitOperation`), qui appelle le MEME slot
        # natif 0x11 de `Core.Services.OperationProcessor`. Frontiere #149 : le noeud DSL ici,
        # l'Operation imperative la-bas. Comportement de cette feuille INCHANGE.
        state = ectx.state
        if state is None or state.effects is None:
            return OperationResult.ok()
        # DOMAINE MIXTE (#1005) : le natif itere des `IEntity` INDIFFERENCIEES, exactement comme
        # `AddEffectBehaviour` -- une UNITE (dict) ou une TUILE. Le port ne routait que les unites,
        # donc `RemoveEffect(Fire, Tiles(Target()))` -- le disjoint « on ETEINT » de
        # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.VitarusAbility$$CreateBehaviour` --
        # etait un NO-OP SILENCIEUX. Meme normalisation et MEME resolveur d'id que l'`AddEffect`
        # d'en face (`_add_effect_targets` / `_add_effect_target_id`), pour que la pose et le
        # retrait ne puissent pas diverger de cle.
        for tu in _add_effect_targets(self.target_sel.evaluate(entities)):
            tgt = _add_effect_target_id(tu, state)
            if tgt is None:
                continue
            removed = 0
            for eff in state.effects.by_unit.get(int(tgt), []):
                if eff.consumed or eff.effect_type != self.effect_type:
                    continue
                if remove_effect_instance(state, int(tgt), eff):
                    removed += 1
            ectx.emit("RemoveEffect", target=tgt, effect_type=self.effect_type, removed=removed)
        return OperationResult.ok()


class ActivateEffect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$ActivateEffect(effectSelector)` ->
    `IdunBattle.Entities.Behaviours.ActivateEffectBehaviour$$Execute` -- MIRROR du DECOMPILE (3 branches
    mutuellement exclusives, on porte celle du SEUL call-site vise) :

        if (this+0x58 != 0)   foreach effect in (this+0x58).Select(entities) : proc.<slot 0x2c>(effect)
        elif (this+0x68 != 0) proc.<slot 0x2c>(this+0x68)                       # entite-effet DIRECTE
        else                  foreach unit in (this+0x50).Select(entities) :    # via les effets de l'unite
                                  if unit.EffectComponent.Type@+0x58 == this+0x60 : proc.<slot 0x2c>(unit)

    `FightingRetreatAbility$$ExecuteBehaviour` prend la 1re branche :
    `ActivateEffect( EffectFromOwner(subject@0x180, 0x5eb = RangedSpecialist) )`.
    Le slot 0x2c du processeur ECRIT `EffectComponent.IsActive @+0x5c = 1` (le champ que
    `IdunBattleLogic.Entities.Abilities.Active.Loki.FightingRetreatAbility$$HasDeactivatedRangedSpecialist`
    LIT : `GetOwnedEffect(unit, .., 0x5eb) != null && effect.IsActive == 0`).

    PORT -- le modele `IsActive` du moteur est la PRESENCE de l'instance (case-160, PROUVE live) : le canal
    de seed (`decisionView.units[].effects` via `readEffectsByUnit`) **DROPPE** les effets `IsActive == 0`
    (`if (!info.active || info.removed) continue`). Un `RangedSpecialist` desactive (porteur parti adjacent
    a un ennemi au turn-start, `RangedSpecialistEffect$$CreateHandleTriggerAbilitiesInternal` :
    `If(HasAdjacentEnemies, DeactivateEffect, ActivateEffect)` sur `On(0x12)`) est donc ABSENT de l'etat
    offline. `ActivateEffect` = rendre l'effet PRESENT **et** poser son flag :
      * absente -> MATERIALISATION de l'owner-effect (`_materialize_owner_effect`, la MEME primitive qui
        seede les owner-effects de trait d'un summon spawne : `StaticBattleRules.Trait$$
        GetEffectToBeAddedToOwnerForTrait` -- nativement l'entite-effet EXISTE en permanence sur le
        porteur, seul son flag bascule) ;
      * presente -> `BaseEffect.active = True` (le champ par instance porte depuis #127, mirror de
        `EffectComponent.IsActive @+0x5c`). C'est CE volet qui rend la feuille utile a un call-site dont
        l'instance est presente mais DESACTIVEE -- `AReactivateOverwatchEffect$$
        GetReactivateOverwatchBehaviour` = `ActivateEffect(Owner@0x148, 0x3f1)` re-arme un overwatch que
        `RangedAutoAttackDeactivateOnAttack` (le << un seul tir par activation >> de #127) vient de
        consommer. Avant #127 le flag n'existait pas cote port et ce volet etait vide.
    Le multiplier/niveau materialises sont ceux du PORTEUR (l'owner-effect natif est pose a la creation de
    l'unite depuis SON etat d'ability -- meme convention que `_seed_trait_owner_effects`).

    Emet 'ActivateEffect' par proprietaire (`created` = l'instance a-t-elle du etre materialisee ;
    `activated` = un flag `active` a-t-il change). PUR (stop=False)."""
    __slots__ = ("owner_sel", "effect_type", "name")

    def __init__(self, owner_sel: TargetsSelector, effect_type: int, name: str):
        self.owner_sel, self.effect_type, self.name = owner_sel, int(effect_type), name

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.owner_sel, entities):        # `EffectFromOwner` = les effets DE ce porteur
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            present = (state.effects is not None
                       and state.effects.has_effect(int(uid), effect_type=self.effect_type))
            created = activated = False
            if not present:
                e = state.get_entity(int(uid))
                sc = e.get_component(StatsComponent) if e is not None else None
                mult = int(getattr(sc.ctx, "ability_variables_multiplier", 100) or 100) if sc else 100
                lvl = getattr(sc.ctx, "passive_ability_level", None) if sc is not None else None
                created = _materialize_owner_effect(state, int(uid), self.name, mult, ability_level=lvl)
            # `proc.<slot 0x2c>(effect)` = `RefreshEffectsOperation$$ActivateEffect` : `+0x5c = 1` sur
            # CHAQUE instance selectionnee. No-op si le flag est deja pose (comme le natif).
            for eff in (state.effects.by_unit.get(int(uid), []) if state.effects is not None else []):
                if eff.consumed or int(eff.effect_type) != self.effect_type or eff.active:
                    continue
                eff.active = True
                activated = True
            ectx.emit("ActivateEffect", owner=int(uid), effect_type=self.effect_type,
                      created=created, activated=activated)
        return OperationResult.ok()


class DeactivateEffect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$DeactivateEffect(selector, effectType)` ->
    `IdunBattle.Entities.Behaviours.DeactivateEffectBehaviour$$Execute` -- le JUMEAU EXACT
    d'`ActivateEffectBehaviour$$Execute` ci-dessus : corps identique instruction pour instruction,
    seul l'index de slot du processeur differe (`0x2d` = 45 au lieu de `0x2c` = 44). Memes trois
    branches ; on porte la MEME que sa jumelle -- la 3e (selecteur d'UNITES + filtre par type),
    celle du call-site `TheArdentBlade_TriggerAbility$$CreateBehaviour` (#1013-r2).

    CE QU'IL FAIT, ET CE QU'IL NE FAIT PAS. Le slot 45 mene a
    `IdunBattle.Operations.DeactivateEffectOperation$$Execute`, qui pousse une demande TYPEE au slot
    47 (`RefreshEffects`) ; l'ecriture reelle est
    `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` :

        if (effectComponent->+0x5c == 0)  -> NO-OP (il sort sans rien faire)
        else
            effectComponent->+0x5c = 0                       # `IsActive`
            UpdateEffectTargets(this, desiredTargets = <List VIDE>, ...)

    ⚠ **Il DESACTIVE, il ne RETIRE PAS**, et c'est structurel : `RemoveEffect` est un slot DISTINCT
    (17) de `IdunBattle.Core.Services.IOperationProcessor`, jamais emprunte ici. L'entite-effet
    SURVIT -- seul le flag bascule, et le retargetting vers l'ensemble VIDE fait jouer les
    `ReverseModification` sur les cibles courantes. C'est ce qui permet au cycle
    `AddEffect`/`ActivateEffect` ... `HasEffect(onlyActive = true)` ... `DeactivateEffect` de servir
    de JETON A UN COUP par pose, au lieu d'un effet qu'il faudrait re-creer.

    ASYMETRIE avec sa jumelle, LUE : `ActivateEffect` ne fait QUE poser le bit ; `DeactivateEffect`
    pose le bit **et** vide les cibles. Cote port, les modificateurs sont derives des effets
    `active` a la lecture (cf. `BaseEffect.active`, mirror de `EffectComponent+0x5c`), donc eteindre
    le flag EST le retargetting -- il n'y a pas de liste de cibles materialisee a purger.

    ⚠ IL NE MATERIALISE RIEN, la ou sa jumelle le fait. `ActivateEffect` doit materialiser une
    instance absente (le canal de seed `decisionView` DROPPE les effets `IsActive == 0`, donc
    « absente » y signifie « desactivee »). Le sens inverse n'a pas cette ambiguite : une instance
    absente cote port est un effet qui n'existe pas, et le natif sort alors en NO-OP de toute facon
    (`+0x5c == 0` deja). Materialiser pour eteindre serait inventer une entite.

    Emet 'DeactivateEffect' par proprietaire (`deactivated` = un flag a-t-il change). PUR
    (stop=False)."""
    __slots__ = ("owner_sel", "effect_type")

    def __init__(self, owner_sel: TargetsSelector, effect_type: int):
        self.owner_sel, self.effect_type = owner_sel, int(effect_type)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        for u in _units_of(self.owner_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            deactivated = False
            # `proc.<slot 0x2d>(effect)` sur CHAQUE instance selectionnee dont le type matche
            # (`unit.EffectComponent.Type@+0x58 == this+0x60`). No-op sur un flag deja tombe,
            # comme le natif (`if (+0x5c == 0) return`).
            for eff in (state.effects.by_unit.get(int(uid), []) if state.effects is not None else []):
                if eff.consumed or int(eff.effect_type) != self.effect_type or not eff.active:
                    continue
                eff.active = False
                deactivated = True
            ectx.emit("DeactivateEffect", owner=int(uid), effect_type=self.effect_type,
                      deactivated=deactivated)
        return OperationResult.ok()


class ChangeEffectTurns(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$ChangeEffectTurns(owner, effectType, turnsNode, changeType)` ->
    `IdunBattle.Entities.Behaviours.ChangeEffectTurnsBehaviour$$Execute` — MIRROR du DECOMPILE :

        this+0x50 = EffectFromOwner(owner, effectType)   # selecteur d'ENTITES-EFFET
        this+0x58 = turnsNode                            # formule (V), evaluee UNE fois
        this+0x60 = changeType                           # IdunBattle.Entities.Enum.ChangeType
        Execute : amount = turnsNode.Calculate(entities)
                  foreach effect in (this+0x50).Select(entities) :
                      ChangeEffectTurnsOperation.Execute(effect, amount, changeType)

    Le natif ne touche QUE la duree d'instances d'effet DEJA presentes (aucune pose). Frontiere #149 :
    feuille DECLARATIVE ici, `ChangeEffectTurnsOperation` (mutateur `EffectComponent.Duration`) en dessous.

    Port : `EffectFromOwner` n'est pas materialisable comme selecteur offline (il rend `[]`, cf.
    `entities/selectors.py`) -> la feuille resout elle-meme les instances via `state.effects.by_unit[owner]`
    filtrees sur `effect_type` (MEME cle que la pose `AddEffectOperation`) — c'est litteralement ce que le
    selecteur natif rend. `owner_sel` = le 2e argument natif (`target@0x178` pour TwinSmartMissileSystem).
    `turns` = int OU noeud-formule, DEJA EN TOURS (mirror d'un noeud `Direct(n)`/`Nullable<int>(n)` natif) ;
    `turns_rounds` = le meme argument exprime en ROUNDS parce que le natif y branche un noeud
    `TurnsFromRounds(n)` (ThrillSeekers : `ChangeEffectTurns(Owner, 0x59a, TurnsFromRounds(nrOfRounds), Set)`)
    -> converti a l'execution par `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`, MEME
    semantique et MEME helper `_resolve_duration` que `duration_rounds` d'`AddEffect` (prioritaire :
    `turns` s'il est fourni). `change_type` = 0 Add (TwinSmartMissileSystem) / 1 Set (ThrillSeekers).
    Emet 'ChangeEffectTurns' par instance touchee. Effet PUR (stop=False)."""
    __slots__ = ("owner_sel", "effect_type", "turns", "change_type", "turns_rounds")

    def __init__(self, owner_sel: TargetsSelector, effect_type: int, turns=None, change_type: int = 0,
                 turns_rounds=None):
        self.owner_sel, self.effect_type = owner_sel, int(effect_type)
        self.turns, self.change_type = turns, int(change_type)
        self.turns_rounds = turns_rounds

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None or state.effects is None:
            return OperationResult.ok()
        if self.turns is not None:
            amount = int(self.turns.evaluate(entities) if hasattr(self.turns, "evaluate") else self.turns)
        else:                                    # noeud `TurnsFromRounds(n)` natif -> ConvertRoundsToTurns
            _r = (self.turns_rounds.evaluate(entities) if hasattr(self.turns_rounds, "evaluate")
                  else self.turns_rounds)
            amount = int(_resolve_duration(state, _r, None) or 0)
        for ou in _units_of(self.owner_sel, entities):
            oid = ou.get("id") if isinstance(ou, dict) else None
            if oid is None:
                continue
            for eff in state.effects.by_unit.get(int(oid), []):    # == EffectFromOwner(owner, type)
                if eff.consumed or eff.effect_type != self.effect_type:
                    continue
                new = ChangeEffectTurnsOperation.execute(state, eff, amount, self.change_type)
                ectx.emit("ChangeEffectTurns", owner=oid, effect_type=self.effect_type,
                          amount=amount, change_type=self.change_type, remaining=new)
        return OperationResult.ok()


class AddStaticStatModifierEffect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect(unit, effectType, statType, amountNode,
    turnsNode, flag)` : pose sur `unit` un effet `effectType` porteur d'une modification de stat STATIQUE
    (montant fige a la pose, != un modifier dynamique re-calcule). Wrapper MINCE au-dessus des DEUX
    operations deja portees : `AddEffectOperation` (materialisation de l'entite-effet) puis
    `apply_change_stat` (la `ValueModification` per-source, cle = l'instance d'effet) — frontiere #149
    respectee (feuille declarative / Operations imperatives).

    DUREE (`duration_rounds`/`duration_turns`, #ThrillSeekers) = le **5e argument natif**, prouve au
    decompile : `DSLFactory.AddStaticStatModifierEffect` construit
    `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$.ctor` avec `param_9 -> champ +0x78`,
    et `...$$Execute` evalue ce champ (`+0x78`) en `Nullable<int>` passe a l'`EffectBuilder` = la DUREE de
    l'entite-effet (le champ +0x70 voisin est, lui, le montant). Sans ce parametre le port forcait
    `duration_override=None` -> `DefaultAmountOfRounds(type)` -> absent de la table -> effet PERMANENT.
    MEME semantique/`_resolve_duration` que `AddEffect` : `duration_rounds` = noeud `TurnsFromRounds(n)`
    natif (converti par `ConvertRoundsToTurns`), `duration_turns` = noeud `Direct(n)` deja en TOURS
    (prioritaire), les deux None = pas d'override (comportement historique des call-sites permanents).

    `stat_mod_source` est pose sur l'instance pour que `RemoveEffect` (qui lit `reverted_stats()` +
    `stat_mod_source`) sache annuler EXACTEMENT cette contribution : c'est la mecanique de rafraichissement
    d'`AddOrUpdateStaticStatModifierEffect` (remove-puis-add). L'effet materialise n'ayant pas forcement de
    classe dediee, on force `reverted_stats` sur l'instance (attribut d'instance, prioritaire sur la methode
    de classe seulement si l'appelant lit la LISTE -- ici `RemoveEffect` appelle `eff.reverted_stats()`, donc
    on installe un callable). L'EXPIRATION du timer passe, elle, par
    `revert_stat_mods_of_removed_effects` (mirror `AStatModifierEffect$$RevertModification`, cf.
    `runner/operations/effects.py`). Emet 'AddStaticStatModifierEffect'. PUR.

    SOURCE DE L'ENTITE-EFFET = **LA CIBLE**, pas le caster (#890-r2). Lu au decompile, en deux
    temps -- c'est le meme couple `+0x58 SOURCE` / `+0x60 TARGETS` que documente deja
    `AddDynamicStatModifierEffect` ci-dessous, sauf que la voie STATIQUE ne le remplit pas :

      * `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute` fait
        `src = <sel@+0x58>.SelectSingle(entities)` puis, PAR CIBLE,
        `source = (src != null) ? src : <la cible courante>` avant l'appel a l'Operation ;
      * `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect(targets, effectType,
        statType, amount, turns, isHidden)` construit le behaviour avec
        `.ctor(logger, isDynamic = 0, source = NULL, targets, ...)` -- le 3e argument du ctor est un
        **litteral nul**. Donc `+0x58 == null` pour TOUT call-site de cette factory, et la source
        retenue est LA CIBLE.
      * `...$$AddStaticStatModifierEffectToOwner` passe, lui, `source = targets = DSLSelectors+0x30`
        (Owner) -- meme entite des deux cotes, donc meme resultat.

    Le port passait `entities.caster`. INOBSERVABLE sur les call-sites dont la magnitude est figee
    par un noeud `DSLFormulas$$Direct` (aucun `scale_from_source`), mais le champ est LU par
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityState` : un effet a magnitude `ConfigVar`
    resolue contre la SOURCE lirait le mauvais `AbilityState`.

    ⚠ `abilityState` (`+0x88`) est lui aussi un **litteral nul** sur cette voie -- le port ne le
    modelise pas, et il n'y a donc rien a y propager.

    LA POSE MATERIALISE ; SEUL LE REFRESH APPLIQUE (#576-r2). La feuille appelait
    `apply_change_stat` INCONDITIONNELLEMENT apres `AddEffectOperation`. Le natif ne le fait pas, et
    la chaine est LUE de bout en bout sur `t6dpr4k06g` :

      * `IdunBattle.Operations.AddEffectOperation$$Execute` materialise l'entite-effet, ecrit
        `EffectComponent.Type @+0x58` / `Level @+0x68`, puis appelle
        `...$$AddNewEffect`, dont le premier geste est le slot **46** (`RefreshEffects`) de
        `IdunBattle.Core.Services.IOperationProcessor` -- table versionnee
        `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv` ;
      * `Core.Services.OperationProcessor$$RefreshEffects` appelle DIRECTEMENT
        `IdunBattle.Operations.RefreshEffectsOperation$$Execute` : **aucune file d'attente**, le
        refresh est SYNCHRONE dans la chaine de pose ;
      * `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect`, lu VERBATIM :

            active = ShouldBeActive(trigger, type, effect, comp, owner, activePlayer, effectEntity)
            if (!active)  DeactivateEffect(this, comp, effect, effectEntity, owner)
            else       {  comp->+0x5c = 1
                          if (effect.<slot 0xc>(trigger))                 // ShouldRefreshForTrigger
                              UpdateEffectTargets(GetDesiredEffectTargets(...), ...) }

        et `...$$ApplyEffectsForTargets` (le SEUL appelant du slot `IEffect+0xe` =
        `ApplyModification`, #576-r1) n'est atteint QUE par cette branche `else` ;
      * `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive`, branche `refreshType == 0`
        (`Automatically`) -- celle de la pose :

            if (comp->+0x5e)                        return false
            if (!effect.<slot 0xc>(refreshTrigger)) return comp->+0x5c      // le flag COURANT
            return effect.<slot 0xb>(entities)                              // CreateActiveCondition

    Un composant NEUF porte `+0x5c == 0` : quand la `CreateActiveCondition` rend faux a la pose,
    l'effet est materialise, `DeactivateEffect` le laisse a `IsActive == 0`, et **sa modification
    n'est JAMAIS appliquee** -- pas << appliquee puis retiree au refresh suivant >>.

    D'ou le gate ci-dessous, mirror de cette branche. `_placed_effect_is_active` est le bon
    predicat SANS le discriminant `_active_condition_is_ported` du driver, et la raison est
    dissymetrique : `BaseEffect.is_active` rend `True` par DEFAUT, or ici le defaut `True`
    **coincide** avec le comportement historique (on applique). Le driver, lui, ECRIT le flag --
    y ecrire ce meme defaut ECRASERAIT une mesure (regression #366-r1b). Une valeur par defaut
    qu'on ne fait que LIRE est inoffensive ; ecrite, elle ne l'est pas.

    ⚠ `stat_mod_source` et `reverted_stats` restent poses meme quand le gate ferme, et ce n'est pas
    un oubli : le natif ECRIT bien le `StatModifierComponent` de l'entite-effet (la MATERIALISATION
    a lieu), seule l'APPLICATION est gatee. C'est aussi ce qui laisse au driver
    `runner/operations/refresh_effects.py::refresh_stat_modifier_effects` de quoi APPLIQUER cette
    instance si sa condition devient vraie plus tard -- le natif la re-evalue a chaque refresh."""
    __slots__ = ("unit_sel", "effect_type", "stat_type", "amount", "name",
                 "duration_rounds", "duration_turns")

    def __init__(self, unit_sel: TargetsSelector, effect_type: int, stat_type: int, amount,
                 name: str | None = None, duration_rounds=None, duration_turns=None):
        self.unit_sel, self.effect_type = unit_sel, int(effect_type)
        self.stat_type, self.amount, self.name = int(stat_type), amount, name
        self.duration_rounds, self.duration_turns = duration_rounds, duration_turns

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None or state.effects is None:
            return OperationResult.ok()
        amt = int(self.amount.evaluate(entities) if hasattr(self.amount, "evaluate") else self.amount)
        _dr = (self.duration_rounds.evaluate(entities) if hasattr(self.duration_rounds, "evaluate")
               else self.duration_rounds)
        dur = _resolve_duration(state, _dr, self.duration_turns)   # champ +0x78 (turnsNode) natif
        for u in _units_of(self.unit_sel, entities):
            uid = u.get("id") if isinstance(u, dict) else None
            if uid is None:
                continue
            # `source = (<sel@+0x58>.SelectSingle(...) != null) ? ... : LA CIBLE` -- et le selecteur
            # `+0x58` est un litteral NUL sur cette voie (#890-r2). Ce n'est donc pas << faute de
            # mieux >> : c'est la branche que le natif prend, toujours.
            eff = AddEffectOperation.execute(state, source=uid, target=uid,
                                             effect_type=self.effect_type, name=self.name,
                                             duration_override=dur, value=amt)
            if eff is None:                          # deja present (gate `deja-present` de l'operation)
                continue
            key = f"eff:{self.effect_type}:{uid}:{id(eff)}"
            eff.stat_mod_source = key
            eff.reverted_stats = (lambda st=self.stat_type: [st])
            # #576-r2 -- LE GATE DE LA POSE. `AddEffectOperation` -> `AddNewEffect` -> slot 46
            # `RefreshEffects` (SYNCHRONE) -> `RefreshEffectsOperation$$RefreshEffect` : la
            # `ValueModification` n'est appliquee que par la branche `ShouldBeActive == true`
            # (`ApplyEffectsForTargets`, seul appelant du slot `IEffect+0xe`). Cf. la docstring.
            active = _placed_effect_is_active(state, uid, eff)
            if active:
                apply_change_stat(state, uid, self.stat_type, key, amt)
            ectx.emit("AddStaticStatModifierEffect", unit=uid, effect_type=self.effect_type,
                      stat=self.stat_type, amount=amt, active=active)
        return OperationResult.ok()


class AddOrUpdateStaticStatModifierEffect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddOrUpdateStaticStatModifierEffect(targets,
    effectType, statType, amount, turns, isHidden)` -- MIRROR du decompile (#965) :

        cur  = CurrentStatModifierAmountFormula(state, targets, effectType, statType)
        cond = op_LogicalNot( AmountIsEqual(amount, cur) )
        body = RemoveEffect(targets, Nullable(effectType))
             & AddStaticStatModifierEffect(targets, effectType, statType, amount, turns, isHidden)
        return If(cond, body, null)

    DEUX traits LUS, qui ne se devinent pas :
      * ce n'est PAS un `Add` inconditionnel : le noeud est un **`If` GARDE par un ecart de
        montant**. Quand le montant recalcule EGALE celui deja en place, le natif ne fait RIEN --
        pas de remove/add, donc pas de churn d'entite-effet ni de re-declenchement de ce qui
        observe la pose. C'est l'idempotence qui donne son nom au noeud (`OrUpdate`) ;
      * le rafraichissement est un **remove-PUIS-add**, pas une mutation en place. C'est ce qui
        rend le montant correct quand il CHANGE : `AddStaticStatModifierEffect` seul serait un
        no-op (son `AddEffectOperation` rend `None` sur effet deja present), et la stat resterait
        figee a la premiere valeur.

    ⚠ Le ctor du noeud conditionnel est etiquete `IdunBattle.Entities.Behaviours.
    PerformAIMovementBehaviour$$.ctor` par ghidra : c'est un corps DEDUPLIQUE par ICF (ctor a trois
    champs `cond/then/else`), le nom designe un proprietaire ARBITRAIRE. La nature `If` est etablie
    par la FORME de l'appel (un trigger + deux behaviours dont le dernier nul), pas par ce nom.

    Se compose sur les DEUX operations deja portees en reutilisant les feuilles `RemoveEffect` et
    `AddStaticStatModifierEffect` -- aucune logique recablee ici (frontiere #149).

    Emet 'AddOrUpdateStaticStatModifierEffect' (`changed` = False quand la garde d'idempotence a
    ferme). PUR."""
    __slots__ = ("unit_sel", "effect_type", "stat_type", "amount", "name",
                 "duration_rounds", "duration_turns")

    def __init__(self, unit_sel: TargetsSelector, effect_type: int, stat_type: int, amount,
                 name: str | None = None, duration_rounds=None, duration_turns=None):
        self.unit_sel, self.effect_type = unit_sel, int(effect_type)
        self.stat_type, self.amount, self.name = int(stat_type), amount, name
        self.duration_rounds, self.duration_turns = duration_rounds, duration_turns

    def execute(self, entities, ectx):
        if ectx.state is None:
            return OperationResult.ok()
        amt = int(self.amount.evaluate(entities) if hasattr(self.amount, "evaluate") else self.amount)
        # `AmountIsEqual(amount, CurrentStatModifierAmount(targets, effectType, statType))` : la
        # formule est deja portee, on la REUTILISE plutot que de relire le sac a la main.
        cur = CurrentStatModifierAmount(self.unit_sel, self.effect_type,
                                        self.stat_type).evaluate(entities)
        if cur is not None and int(cur) == amt:
            ectx.emit("AddOrUpdateStaticStatModifierEffect", effect_type=self.effect_type,
                      stat=self.stat_type, amount=amt, changed=False)
            return OperationResult.ok()                 # `If` FERME -> aucun effet de bord
        RemoveEffect(self.effect_type, self.unit_sel).execute(entities, ectx)
        AddStaticStatModifierEffect(self.unit_sel, self.effect_type, self.stat_type, amt,
                                    name=self.name, duration_rounds=self.duration_rounds,
                                    duration_turns=self.duration_turns).execute(entities, ectx)
        ectx.emit("AddOrUpdateStaticStatModifierEffect", effect_type=self.effect_type,
                  stat=self.stat_type, amount=amt, changed=True)
        return OperationResult.ok()


class AddDynamicStatModifierEffect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffect(targets, source, effectType,
    statType, abilityStateRef, durationNode, …)` — et son jumeau
    `IdunBattleLogic.Entities.DSLBehaviors$$AddDynamicStatModifierEffectToOwner(effectType, statType,
    durationNode, …)` qui n'est que le MEME appel avec `self@0x148` dans les DEUX slots.

    Les deux allouent un `IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour` dont le ctor
    (`…$$.ctor`, lu au decompile) range :
        +0x50 isDynamic(=1) · **+0x58 SOURCE** · **+0x60 TARGETS** · +0x68 effectType · +0x6c statType
        · +0x70 amountNode(null si dynamique) · +0x78 durationNode · +0x88 abilityStateRef
    et son `…$$Execute` **ITERE le selecteur +0x60** (une instance d'effet par element) en attribuant la
    `ValueModification` a l'entite resolue par **+0x58** (`lVar17 = local_298 (source) sinon la cible`).
    C'est CE couple qui tranche « self-buff vs debuff sur la cible » — pas le nom de l'effet.

    Port : wrapper MINCE au-dessus des DEUX operations deja portees — `AddEffectOperation`
    (materialisation ECS + `_apply_stat_mods` = le `AStatModifierEffect$$ApplyModification` natif) ;
    la MAGNITUDE et le SIGNE vivent dans la CLASSE D'EFFET (`applied_stat_mods`, part DATA cote
    `entities/`), exactement comme le natif les tient dans
    `DynamicStatModifierEffect$$GetDynamicStatModificationAmount` (`ConfigVar(abilityId, EffectSource,
    varKey)` + champ `isNegative`). Frontiere #149 respectee : feuille declarative ici, Operation en
    dessous ; AUCUN `apply_change_stat` recable a la main.

    `stat_type` = l'argument natif +0x6c, conserve pour la tracabilite/diagnostic (`emit`) ; la valeur
    EFFECTIVE appliquee vient de la classe d'effet (les deux coincident par construction — verifie au
    decompile pour les trois effets du lot Votann). Effet non porte (`BaseEffect` nu) -> effet PRESENT
    mais sans stat-mod = degradation fidele (§17.4).

    `duration_rounds` / `duration_turns` : meme semantique que `AddEffect` (None des deux = pas
    d'override -> `DefaultAmountOfRounds`, sinon PERMANENT). Emet 'AddDynamicStatModifierEffect' par
    cible. Effet PUR (stop=False)."""
    __slots__ = ("target_sel", "source_sel", "effect_type", "stat_type", "name",
                 "duration_rounds", "duration_turns")

    def __init__(self, target_sel: TargetsSelector, source_sel: TargetsSelector, effect_type: int,
                 stat_type: int, name: str | None = None, duration_rounds=None, duration_turns=None):
        self.target_sel, self.source_sel = target_sel, source_sel
        self.effect_type, self.stat_type = int(effect_type), int(stat_type)
        self.name = name
        self.duration_rounds, self.duration_turns = duration_rounds, duration_turns

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        su = resolve_unit(self.source_sel, entities)            # selecteur +0x58 (SOURCE de la modif)
        src = su.get("id") if isinstance(su, dict) else None
        if src is None:
            return OperationResult.ok()
        # #448-r6 -- MEME regime que `AddEffect` : un `duration_turns` NOEUD s'evalue PAR CIBLE.
        _dur_node = _duration_is_node(self.duration_turns)
        dur = (None if _dur_node
               else _resolve_duration(state, self.duration_rounds, self.duration_turns))
        # `AbilityStateReference` (+0x88) : l'effet resout ses `ConfigVar` contre l'etat d'ability de sa
        # SOURCE -> on propage niveau/multiplier du poseur (== `scale_from_source` d'`AddEffect`).
        mult, ab_lvl, act_lvl = _source_scaling(state, src)
        for elem in _add_effect_targets(self.target_sel.evaluate(entities)):   # ITERE +0x60
            tgt = _add_effect_target_id(elem, state)
            if tgt is None:
                continue
            if _dur_node:
                dur = _resolve_duration(state, self.duration_rounds, self.duration_turns,
                                        replace(entities, active_target=elem))
            eff = AddEffectOperation.execute(state, source=src, target=tgt,
                                             effect_type=self.effect_type, name=self.name,
                                             duration_override=dur, ability_level=ab_lvl,
                                             active_ability_level=act_lvl, multiplier_pct=mult)
            ectx.emit("AddDynamicStatModifierEffect", source=src, target=tgt,
                      effect_type=self.effect_type, stat=self.stat_type, placed=eff is not None)
        return OperationResult.ok()
# `AddStatOverrideEffect` a VECU ICI jusqu'a l'integration de #112 : deux agents en parallele
# (#112 DarkAngels et #114 Tau) avaient porte le MEME noeud natif
# `IdunBattleLogic.Entities.DSLBehaviors$$AddStatOverrideEffect` chacun de son cote, dans deux modules
# differents. Les DEUX consommateurs important depuis le paquet `behaviours`, le second import
# aurait MASQUE le premier -- silencieusement, et le test de chaque lot serait passe par chance
# selon l'ordre des imports. Les deux implementations ont donc ete FUSIONNEES dans
# `behaviours/stats.py` (mirror structurel le plus fidele : liaison du SUJET par unite avant
# d'evaluer le noeud montant, duree, flag `is_modifiable`, revert par `stat_override_stats`),
# augmentee de la specialisation `ACTIVE_ABILITY_LEVEL` qui vivait ici. Un seul foyer, cf. #120.

def add_or_update_static_stat_modifier_effect(unit_sel: TargetsSelector, effect_type: int,
                                              stat_type: int, amount, name: str | None = None):
    """`IdunBattleLogic.Entities.DSLBehaviors$$AddOrUpdateStaticStatModifierEffect(unit, effectType, statType,
    amountNode, ...)` — FACTORY COMPOSITE, mirror 1:1 du decompile (elle n'alloue PAS de behaviour dedie) :

        cur  = CurrentStatModifierAmountFormula(dslFactory+0x38, unit, effectType, statType)
        cond = NOT( AmountIsEqual(amountNode, cur) )
        body = RemoveEffect(unit, Nullable(effectType))  op_BitwiseAnd  AddStaticStatModifierEffect(
                   unit, effectType, statType, amountNode, ...)
        return ForeachBehaviour(cond, body, null)        # == `If(cond, body)`

    -> « si le modificateur COURANT de `statType` porte par l'effet `effectType` differe du nouveau montant,
    on retire l'effet et on le re-pose au bon montant » (idempotent : montant identique = no-op).

    Port : `CurrentStatModifierAmountFormula` est modelise par `_current_stat_modifier_amount` (lit la
    contribution `stat_mod_source` de l'instance d'effet portee ; 0 si absente)."""
    amt_node = amount if hasattr(amount, "evaluate") else Const(int(amount))
    cond = Not(AmountIsEqual(amt_node, CurrentStatModifierAmount(unit_sel, effect_type, stat_type)))
    body = op_and(RemoveEffect(effect_type, unit_sel),
                  AddStaticStatModifierEffect(unit_sel, effect_type, stat_type, amt_node, name=name))
    return IfBehaviour(cond, body)


class SetOnFire(AbilityBehaviour):
    """`FireOfAbsolutionAbility.SetOnFire` (child `Func<entities,behaviour>` du `Maybe` natif IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour) ->
    pose l'effet FEU DE TUILE (`EnvFireTile`) sur la TUILE COURANTE. Le `Maybe(child, AdjacentTiles(target),
    30)` natif itere ses tuiles et lie la tuile courante en sujet (== `Foreach(tiles, Maybe(30, SetOnFire))`
    cote port) : `SetOnFire` lit `entities.subject` = l'id de TUILE (int, PAS une unite — le `Foreach`
    tile-domain y pose l'element courant). Wrapper MINCE au-dessus de `AddEffectOperation.execute` (target =
    tile id, source = caster). N'emet 'SetOnFire' que si l'effet est REELLEMENT pose (AddEffect non-None :
    no-op si la tuile est deja en feu — == l'ancien imperatif `if AddEffectOperation.execute(...) is not None`).
    Effet PUR (stop=False)."""
    __slots__ = ("effect_type", "name")

    def __init__(self, effect_type: int, name: str = "Fire"):
        self.effect_type, self.name = int(effect_type), name

    def execute(self, entities, ectx):
        state = ectx.state
        tile = entities.subject                          # tuile COURANTE (id) posee par le Foreach tile-domain
        src = (entities.caster or {}).get("id")
        if state is None or tile is None:
            return OperationResult.ok()
        if AddEffectOperation.execute(state, source=src, target=tile,
                                      effect_type=self.effect_type, name=self.name) is not None:
            ectx.emit("SetOnFire", tile=tile, source=src)
        return OperationResult.ok()


class CreateShield(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$CreateShield` -> `IdunBattle.Entities.Behaviours.CreateShieldBehaviour$$Execute` : pour CHAQUE cible
    du selecteur `target_sel` (+0x50), accorde/rafraichit un bouclier de `amount` (formule +0x58, scalaire)
    duree `duration` rounds via `ShieldComponent.add_or_update_shield` (cumule meme-source/meme-duree, sinon
    nouvelle instance ; no-op si amount<=0). Options +0x60..+0x88 (2e amount Nullable +0x78, flags) non
    portees (aucun usage Groupe 3). `source` = `AbilityOrEffect(self.Id)` natif (attribution / stack same-source).

    Seul usage porte (Groupe 3) : ArcaneShield `CreateShield(Cache(First(SortByFormula(Randomize(Units
    WithoutTrait(SurroundingFriends(self,range),0x1b)) op_Addition self, Sum(3*dist,faction,chaos,is-self),
    asc))), ConfigVar(0x27=shieldHp), self.Id, TurnsFromRounds(1))` = Thaumachus accorde un bouclier 1 round
    a l'ami de MEILLEUR SCORE, le caster restant dernier recours. ⚠ le classement est un score ADDITIF ou
    la DISTANCE DOMINE (poids 3 contre 1 pour faction et pour le trait Chaos), PAS un ordre lexicographique
    « faction puis distance » — cf. `triggers/loki/arcane_shield.py::_arcaneshield_score`. Le selecteur
    AI-target LOURD (kind S :
    SurroundingFriends -> UnitsWithoutTrait -> Randomize -> SortByFormula -> First) reste IMPERATIF
    (`_arcaneshield_target`) et est COLLAPSE en `Target()` ; le montant `ConfigVar(0x27)` (formule V,
    `shieldHp[level] x mult%`) est calcule IMPERATIVEMENT (`ability_var`) et passe comme SCALAIRE -- meme
    collapse que FinalJustice (doctrine slice-18/19). DSL-ification du selecteur AI + de la formule ConfigVar
    = taches S/V (flaggees).

    `amount` = scalaire (int) OU noeud-formule (`.evaluate(entities)`). `duration` = rounds restants
    (ArcaneShield=1 ; None=permanent). `source` = etiquette de source (stack same-source). Itere les cibles
    triees par id (ordre de lecture natif). Emet 'CreateShield' par cible. PUR (non court-circuitant)."""
    __slots__ = ("target_sel", "amount", "duration", "source")

    def __init__(self, target_sel: TargetsSelector, amount, duration=None, source=None):
        self.target_sel = target_sel
        self.amount = amount
        self.duration = duration
        self.source = source

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        amt = int(self.amount.evaluate(entities)) if hasattr(self.amount, "evaluate") else int(self.amount)
        if amt <= 0:                                     # no-op (mirror add_or_update_shield amount<=0)
            return OperationResult.ok()
        targets = [u for u in _units_of(self.target_sel, entities)
                   if isinstance(u, dict) and u.get("id") is not None]
        for tu in sorted(targets, key=lambda x: x["id"]):    # ordre de lecture = id
            tid = tu["id"]
            te = state.get_entity(tid)
            if te is None:
                continue
            shc = te.get_component(ShieldComponent)
            if shc is None:
                shc = ShieldComponent()
                te.add_component(shc)
            shc.add_or_update_shield(amt, source=self.source, remaining=self.duration)
            ectx.emit("CreateShield", target=tid, amount=amt, remaining=self.duration,
                      shield_total=shc.get_total_shield())
        return OperationResult.ok()
