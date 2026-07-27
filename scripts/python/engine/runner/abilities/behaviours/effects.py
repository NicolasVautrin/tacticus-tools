"""Feuilles DSL de POSE/RETRAIT d'effets runner-couplees : `AddBondEffect` (effet BOND source<->target),
`AddEffect` (effet sur unite OU tuile), `IncreaseEffectLevel` (+ la factory composite
`add_effect_or_increase_level`), `RemoveEffect` (retrait + revert StatModification), `SetOnFire`
(effet FEU de tuile), `CreateShield` (bouclier). Wrappers au-dessus de `runner/operations/effects.py` +
`stat_ops.py`. Namespace natif `Entities.Behaviours.*`."""
from __future__ import annotations

from ....dsl.base import TargetsSelector, resolve_unit, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ..base import convert_rounds_to_turns


def _resolve_duration(state, duration_rounds, duration_turns):
    """Unite de la duree passee a `AddEffectOperation` (`param_6.NullableA` natif, en TOURS) :

      * `duration_turns` (prioritaire) = duree DEJA en tours -- mirror d'un noeud `Direct(n)@0xc0` ou
        d'un `Nullable<int>(n)` litteral cote natif : le decompile la met telle quelle dans `param_6`,
        `IdunBattle.Operations.AddEffectOperation$$Execute` ne la convertit PAS.
      * `duration_rounds` = un noeud `TurnsFromRounds(n)` natif -> `convert_rounds_to_turns(state, n)`
        (`IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`).
      * `None` des deux -> pas d'override : la duree vient de `DefaultAmountOfRounds`, convertie DANS
        `AddEffectOperation` (mirror de la branche « pas d'override » du decompile).
    """
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
    from ...components import StatsComponent
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
    `LastUnitAttackedBy(child)` — rendent 1 element -> chemin identique)."""
    __slots__ = ("effect_type", "name", "source_ref", "target_ref", "duration_rounds", "duration_turns")

    def __init__(self, effect_type: int, name: str, source_ref: TargetsSelector, target_ref: TargetsSelector,
                 duration_rounds=1, duration_turns=None):
        self.effect_type, self.name = effect_type, name
        self.source_ref, self.target_ref = source_ref, target_ref
        self.duration_rounds = duration_rounds
        self.duration_turns = duration_turns

    def execute(self, entities, ectx):
        from ...operations.effects import AddEffectOperation
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
        for elem in _add_effect_targets(self.target_ref.evaluate(entities)):
            tgt = _add_effect_target_id(elem, state)     # unit dict->id | (col,row)/int -> tile id
            if tgt is None:
                continue
            AddEffectOperation.execute(state, source=src, target=tgt, effect_type=self.effect_type,
                                       name=self.name, duration_override=dur)
            ectx.emit("AddBondEffect", source=src, target=tgt, effect_type=self.effect_type)
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


class AddEffect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$AddEffect` -> `AddEffectBehaviour.Execute` : pose un effet, `source` =
    `AbilityStateReference` (= le caster), sur CHAQUE cible du selecteur `target_sel`, duree
    `TurnsFromRounds(rounds)`. Wrapper MINCE au-dessus de `AddEffectOperation.execute` (mirror exact de
    l'imperatif). DIFFERE de `AddBondEffect` (qui LIE source+target = deux unites distinctes) : ici la source
    EST le caster. Emet 'AddEffect' par cible (payload `placed` = l'effet a-t-il ete REELLEMENT pose, i.e.
    `AddEffectOperation` non-None : False si deja present / cible nulle -> laisse l'appelant distinguer la
    re-pose no-op, cf. OnFireDamage). Effet PUR (stop=False).

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
                 "duration_turns", "source_ref", "source_from_target")

    def __init__(self, effect_type: int, name: str, target_sel: TargetsSelector, duration_rounds=1,
                 level=None, scale_from_source: bool = False, duration_turns=None, source_ref=None,
                 source_from_target: bool = False):
        self.effect_type, self.name = effect_type, name
        self.target_sel, self.duration_rounds = target_sel, duration_rounds
        self.level, self.scale_from_source = level, scale_from_source
        self.duration_turns = duration_turns
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
        from ...operations.effects import AddEffectOperation
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
        dur = _resolve_duration(state, self.duration_rounds, self.duration_turns)
        lvl = (self.level.evaluate(entities) if hasattr(self.level, "evaluate")
               else self.level)
        mult, ab_lvl, act_lvl = (_source_scaling(state, src) if self.scale_from_source
                                 else (None, None, None))
        for elem in _add_effect_targets(self.target_sel.evaluate(entities)):  # natif : itere le selecteur
            tgt = _add_effect_target_id(elem, state)          # unit dict->id | (col,row)->tile id | int->tile id
            if tgt is None:
                continue
            if self.source_from_target:                       # selecteur SOURCE natif NULL -> source = cible
                src = tgt
            eff = AddEffectOperation.execute(state, source=src, target=tgt, effect_type=self.effect_type,
                                             name=self.name, duration_override=dur,
                                             level=(None if lvl is None else int(lvl)),
                                             ability_level=ab_lvl, active_ability_level=act_lvl,
                                             multiplier_pct=mult)
            ectx.emit("AddEffect", source=src, target=tgt, effect_type=self.effect_type,
                      placed=eff is not None, level=(None if lvl is None else int(lvl)))
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
    """`IdunBattleLogic.Entities.DSLFactory$$AddEffectOrIncreaseLevel(effectType, stateRef, subject, selector, amount, max)` — factory COMPOSITE : le natif alloue un `ForeachBehaviour(selector, Func<entity,
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
    from ....entities.behaviours import Foreach, If as IfBehaviour
    from ....entities.selectors import Subject
    from ....entities.triggers import HasEffect
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
        from ....entities.effects import effect_stat_mod_key
        from ...operations.stat_ops import revert_change_stat
        from ...operations.ability_modifications import revert_ability_modifications
        from ...operations.effects import unregister_name
        state = ectx.state
        if state is None or state.effects is None:
            return OperationResult.ok()
        for tu in _units_of(self.target_sel, entities):     # natif : ITERE le selecteur-cible
            tgt = tu.get("id") if isinstance(tu, dict) else None
            if tgt is None:
                continue
            removed = 0
            for eff in state.effects.by_unit.get(int(tgt), []):
                if eff.consumed or eff.effect_type != self.effect_type:
                    continue
                # revert par SOURCE (ReverseModification) : la valeur se re-clampe au read, sans delta stocke.
                src = None if eff.stat_mod_reverted else effect_stat_mod_key(eff)
                if src is not None:
                    for stat in eff.reverted_stats():
                        revert_change_stat(state, tgt, stat, src)
                    eff.stat_mod_source = None
                    eff.stat_mod_reverted = True
                # `<Effect>.RevertInternal` part OVERRIDE (`ResetStat` xN = `ChangeStat` mode 4 /
                # `Position(statType, part 8 = REMOVE_OVERRIDE)`) : symetrique de la part `ApplyInternal`
                # override deja portee (`AddEffectOperation._apply_stat_overrides`). Jusqu'ici SEUL le
                # vecteur MV71 (consommation par trigger) appelait `revert_stat_overrides` -> un effet a
                # override retire par la feuille `RemoveEffect` (le couple `AddStatOverrideEffect(0x510)`
                # / `RemoveEffect(0x510)` d'ExemplarOfHate et SternguardFocus, #112) laissait l'override
                # COLLE. NO-OP STRICT pour tout effet sans `stat_override_stats` (= tous les effets
                # anterieurs, qui n'en posent aucun par cette voie) -> zero regression.
                if getattr(eff, "stat_override_stats", None):
                    from ...operations.effects import AddEffectOperation
                    AddEffectOperation.revert_stat_overrides(state, tgt, eff)
                # `<Effect>.RevertInternal` part MODIFICATIONS D'ABILITY : rejoue les
                # `AddUnitActiveAbilityModification` en `-delta` (cf. operations/ability_modifications.py).
                revert_ability_modifications(state, eff)
                eff.consumed = True
                # `RemoveEffectOperation` retire aussi l'entite-effet de `EffectsOwnedComponent.
                # ActiveEffectIds` -> le canal des NOMS (lu par la couche decision) doit suivre,
                # sinon un couple pose/retire dans le MEME cast laisse son nom colle.
                unregister_name(state, tgt, eff.name)
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
        from ...components import StatsComponent
        from ...operations.spawn import _materialize_owner_effect
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
        from ...operations.effects import ChangeEffectTurnsOperation
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
    """`IdunBattleLogic.Entities.DSLFactory$$AddStaticStatModifierEffect(unit, effectType, statType, amountNode,
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
    `runner/operations/effects.py`). Emet 'AddStaticStatModifierEffect'. PUR."""
    __slots__ = ("unit_sel", "effect_type", "stat_type", "amount", "name",
                 "duration_rounds", "duration_turns")

    def __init__(self, unit_sel: TargetsSelector, effect_type: int, stat_type: int, amount,
                 name: str | None = None, duration_rounds=None, duration_turns=None):
        self.unit_sel, self.effect_type = unit_sel, int(effect_type)
        self.stat_type, self.amount, self.name = int(stat_type), amount, name
        self.duration_rounds, self.duration_turns = duration_rounds, duration_turns

    def execute(self, entities, ectx):
        from ...operations.effects import AddEffectOperation
        from ...operations.stat_ops import apply_change_stat
        state = ectx.state
        src = (entities.caster or {}).get("id")
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
            eff = AddEffectOperation.execute(state, source=src, target=uid,
                                             effect_type=self.effect_type, name=self.name,
                                             duration_override=dur, value=amt)
            if eff is None:                          # deja present (gate `deja-present` de l'operation)
                continue
            key = f"eff:{self.effect_type}:{uid}:{id(eff)}"
            eff.stat_mod_source = key
            eff.reverted_stats = (lambda st=self.stat_type: [st])
            apply_change_stat(state, uid, self.stat_type, key, amt)
            ectx.emit("AddStaticStatModifierEffect", unit=uid, effect_type=self.effect_type,
                      stat=self.stat_type, amount=amt)
        return OperationResult.ok()


class AddDynamicStatModifierEffect(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$AddDynamicStatModifierEffect(targets, source, effectType,
    statType, abilityStateRef, durationNode, …)` — et son jumeau
    `IdunBattleLogic.Entities.DSLFactory$$AddDynamicStatModifierEffectToOwner(effectType, statType,
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
        from ...operations.effects import AddEffectOperation
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        su = resolve_unit(self.source_sel, entities)            # selecteur +0x58 (SOURCE de la modif)
        src = su.get("id") if isinstance(su, dict) else None
        if src is None:
            return OperationResult.ok()
        dur = _resolve_duration(state, self.duration_rounds, self.duration_turns)
        # `AbilityStateReference` (+0x88) : l'effet resout ses `ConfigVar` contre l'etat d'ability de sa
        # SOURCE -> on propage niveau/multiplier du poseur (== `scale_from_source` d'`AddEffect`).
        mult, ab_lvl, act_lvl = _source_scaling(state, src)
        for elem in _add_effect_targets(self.target_sel.evaluate(entities)):   # ITERE +0x60
            tgt = _add_effect_target_id(elem, state)
            if tgt is None:
                continue
            eff = AddEffectOperation.execute(state, source=src, target=tgt,
                                             effect_type=self.effect_type, name=self.name,
                                             duration_override=dur, ability_level=ab_lvl,
                                             active_ability_level=act_lvl, multiplier_pct=mult)
            ectx.emit("AddDynamicStatModifierEffect", source=src, target=tgt,
                      effect_type=self.effect_type, stat=self.stat_type, placed=eff is not None)
        return OperationResult.ok()
# `AddStatOverrideEffect` a VECU ICI jusqu'a l'integration de #112 : deux agents en parallele
# (#112 DarkAngels et #114 Tau) avaient porte le MEME noeud natif
# `IdunBattleLogic.Entities.DSLFactory$$AddStatOverrideEffect` chacun de son cote, dans deux modules
# differents. Les DEUX consommateurs important depuis le paquet `behaviours`, le second import
# aurait MASQUE le premier -- silencieusement, et le test de chaque lot serait passe par chance
# selon l'ordre des imports. Les deux implementations ont donc ete FUSIONNEES dans
# `behaviours/stats.py` (mirror structurel le plus fidele : liaison du SUJET par unite avant
# d'evaluer le noeud montant, duree, flag `is_modifiable`, revert par `stat_override_stats`),
# augmentee de la specialisation `ACTIVE_ABILITY_LEVEL` qui vivait ici. Un seul foyer, cf. #120.

def add_or_update_static_stat_modifier_effect(unit_sel: TargetsSelector, effect_type: int,
                                              stat_type: int, amount, name: str | None = None):
    """`IdunBattleLogic.Entities.DSLFactory$$AddOrUpdateStaticStatModifierEffect(unit, effectType, statType,
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
    from ....entities.behaviours import If as IfBehaviour, op_and
    from ....entities.triggers import Not, AmountIsEqual
    from ....entities.formulas import CurrentStatModifierAmount
    from ....dsl.base import Const
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
        from ...operations.effects import AddEffectOperation
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
    WithoutTrait(SurroundingFriends(self,range),0x1b)) .Otherwise self, Sum(dist,faction,chaos,not-self),
    asc))), ConfigVar(0x27=shieldHp), self.Id, TurnsFromRounds(1))` = Thaumachus accorde un bouclier 1 round
    a l'ami prefere (faction > distance > pas-soi) sinon soi. Le selecteur AI-target LOURD (kind S :
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
        from ...components import ShieldComponent
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
