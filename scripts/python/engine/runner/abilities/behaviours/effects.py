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
        `AddEffectOperation.Execute @180e48940` ne la convertit PAS.
      * `duration_rounds` = un noeud `TurnsFromRounds(n)` natif -> `convert_rounds_to_turns(state, n)`
        (`BattleQuery.ConvertRoundsToTurns @181058af0`).
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
    """`DSLFactory.AddBondEffect(0x1b, stateRef, source, target, ..., TurnsFromRounds(1)) @1811e27a0` : pose
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
    (unites OU tuiles) : `MalleusRocketLauncherAbility.ExecuteBehaviour @1811f1d90` et
    `DevastatingRefrainAbility.ExecuteBehaviour @1811d3730` bondent sur des TUILES. Le port itere donc
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
        # `ConvertRoundsToTurns(rounds)` @181058af0 (mirror du noeud `TurnsFromRounds`). `duration_turns`
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
    """`DSLFactory.AddEffect @180de6d20` -> `AddEffectBehaviour.Execute` : pose un effet, `source` =
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
    - tile-domain (`Tiles(Target())` d'OnFireDamage @1811c3a60) -> effet de TUILE (le selecteur rend la
      MainTile de la cible ; `_add_effect_target_id` la convertit en id de tuile). MEME `AddEffectOperation`.

    `duration_rounds` = nb de rounds (`TurnsFromRounds(rounds)`) ; `None` = duree DEFAUT de l'effet
    (`DefaultAmountOfRounds`, mirror de l'arg natif `0` d'`AddEffect` SANS `TurnsFromRounds` — ex. Pinned de
    CrushingClaws) vs explicite (ThunderousAssault Stunned = `TurnsFromRounds(1)`).
    `duration_turns` = duree deja en TOURS (le natif passe un noeud `Direct(n)@0xc0` ou un `Nullable<int>(n)`
    litteral, PAS un `TurnsFromRounds`) — PRIORITAIRE sur `duration_rounds`, cf. `_resolve_duration`.

    `level` = niveau de STACK initial (slot niveau de la struct d'options natives) — utilise par la branche
    AddEffect du lambda `AddEffectOrIncreaseLevel b__0 @180e25540` (la 1re pose demarre au niveau
    = INCREMENT) ; None = pas de niveau porte (tous les autres call-sites).
    `scale_from_source` = le PORT de l'`AbilityStateReference` : l'effet materialise resout ses `ConfigVar`
    contre l'etat d'ability de sa SOURCE (niveau d'ability + multiplier de rarete du caster). Opt-in
    (defaut False = comportement historique) pour les effets dont la MAGNITUDE vient d'un ConfigVar
    (FleshmetalGuns 1067/1212/1221, TerrifyingCrescendo 1424).
    """
    __slots__ = ("effect_type", "name", "target_sel", "duration_rounds", "level", "scale_from_source",
                 "duration_turns")

    def __init__(self, effect_type: int, name: str, target_sel: TargetsSelector, duration_rounds=1,
                 level=None, scale_from_source: bool = False, duration_turns=None):
        self.effect_type, self.name = effect_type, name
        self.target_sel, self.duration_rounds = target_sel, duration_rounds
        self.level, self.scale_from_source = level, scale_from_source
        self.duration_turns = duration_turns

    def execute(self, entities, ectx):
        from ...operations.effects import AddEffectOperation
        state = ectx.state
        src = (entities.caster or {}).get("id")               # AbilityStateReference = caster (source)
        if state is None or src is None:
            return OperationResult.ok()
        # duration_rounds None -> pas d'override = duree DEFAUT (DefaultAmountOfRounds), mirror de l'arg natif
        # `0` d'AddEffect sans TurnsFromRounds (Pinned CrushingClaws) ; sinon `ConvertRoundsToTurns(rounds)`
        # @181058af0. `duration_turns` court-circuite (noeud Direct/Nullable natif, deja en TOURS).
        dur = _resolve_duration(state, self.duration_rounds, self.duration_turns)
        lvl = (self.level.evaluate(entities) if hasattr(self.level, "evaluate")
               else self.level)
        mult, ab_lvl, act_lvl = (_source_scaling(state, src) if self.scale_from_source
                                 else (None, None, None))
        for elem in _add_effect_targets(self.target_sel.evaluate(entities)):  # natif : itere le selecteur
            tgt = _add_effect_target_id(elem, state)          # unit dict->id | (col,row)->tile id | int->tile id
            if tgt is None:
                continue
            eff = AddEffectOperation.execute(state, source=src, target=tgt, effect_type=self.effect_type,
                                             name=self.name, duration_override=dur,
                                             level=(None if lvl is None else int(lvl)),
                                             ability_level=ab_lvl, active_ability_level=act_lvl,
                                             multiplier_pct=mult)
            ectx.emit("AddEffect", source=src, target=tgt, effect_type=self.effect_type,
                      placed=eff is not None, level=(None if lvl is None else int(lvl)))
        return OperationResult.ok()


class IncreaseEffectLevel(AbilityBehaviour):
    """`DSLFactory.IncreaseEffectLevel @180df1d90` -> `IncreaseEffectLevelBehaviour.Execute @180fc7ac0`
    -> `IncreaseEffectLevelOperation.Execute @180e73cb0` : incremente le NIVEAU (`EffectComponent.Level
    @+0x68`) des instances d'effet `effect_type` portees par les cibles du selecteur, avec CAP optionnel.

    Mirror EXACT du clamp natif (@180e73cb0) :
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
                if mx is None or mx < cur or cur + amt <= mx:      # mirror @180e73cb0
                    eff.level = cur + amt
                else:
                    eff.level = mx
                ectx.emit("IncreaseEffectLevel", target=tgt, effect_type=self.effect_type,
                          level=eff.level, amount=amt, max_level=mx)
        return OperationResult.ok()


def add_effect_or_increase_level(effect_type: int, name: str, target_sel: TargetsSelector,
                                 amount, max_level=None, duration_rounds=0,
                                 scale_from_source: bool = True):
    """`DSLFactory.AddEffectOrIncreaseLevel(effectType, stateRef, subject, selector, amount, max)
    @180de6860` — factory COMPOSITE : le natif alloue un `ForeachBehaviour(selector, Func<entity,
    behaviour>)` dont le lambda `b__0 @180e25540` construit, PAR ELEMENT :

        If( HasEffect(elem, effectType),
            IncreaseEffectLevel(elem, effectType, amount, max),      # then
            AddEffect(effectType, stateRef, subject, elem, {level = amount}) )   # else

    On MIRRORE cet arbre (Foreach + If/else + les 2 feuilles) au lieu de le collapser : c'est un noeud de
    la FACTORY, pas une Operation. Call-sites portes : `TerrifyingCrescendoAbility.CreateBehaviour
    @1811a3840` (0x590=1424, amount=Const(1)@0xc0, max=Direct(GetNumberConstant(0x62)=buffMaxLevel)) ;
    `HeadClaimerAbility.CreateBehaviour @181220e30` (0x404/0x405, amount=Const(1), max=NULL).

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
    """`DSLFactory.RemoveEffect @180df9cc0` -> `RemoveEffectBehaviour.Execute` : retire de la cible TOUS les
    effets du type `effect_type` (non consommes) et ANNULE leur StatModification (`<Effect>.RevertInternal`).
    `target` = `target_sel` (ex. `Caster()`/`Self@0x148` pour le reset ActOfFaith @181219eb0). Wrapper au-dessus
    de l'Operation impurative `revert_change_stat` (mirror exact de l'ancien `_reset_act_of_faith`). No-op si
    `state.effects`/cible absents. Emet 'RemoveEffect' PAR CIBLE (removed = nb de stacks retires). Effet PUR
    (stop=False).

    Le natif ITERE son selecteur-cible (`RemoveEffectsBehaviour`, meme mold que `AddEffectBehaviour`) : le port
    itere donc `_units_of(target_sel)` — les call-sites MONO-cible historiques (`Caster()`) rendent une liste
    d'1 element -> chemin bit-IDENTIQUE ; le call-site MULTI-cible est
    `MasterAnnihilatorAbility.CreateBehaviour @18110b940` (`OwnerOfEffect(EffectsFromUnitSource(...))`).

    Frontiere classification (#149) : le NOEUD `RemoveEffect` (declaratif) au-dessus ; `ReverseModification`
    (revert par-source, impuratif) EN DESSOUS. L'effet DECLARE ses StatTypes revertes (`reverted_stats()`, DATA
    cote `entities/`) ; la feuille (runner/) EXECUTE le revert (`revert_change_stat`, couche runner) sur chacun,
    keye par `stat_mod_source`. Un stack SEEDE sans `stat_mod_source` = retire mais non reverte (limitation
    pre-existante : delta inconnu dans le residu opaque)."""
    __slots__ = ("effect_type", "target_sel")

    def __init__(self, effect_type: int, target_sel: TargetsSelector):
        self.effect_type, self.target_sel = int(effect_type), target_sel

    def execute(self, entities, ectx):
        from ...operations.stat_ops import revert_change_stat
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
                src = getattr(eff, "stat_mod_source", None)
                if src is not None:
                    for stat in eff.reverted_stats():
                        revert_change_stat(state, tgt, stat, src)
                eff.consumed = True
                removed += 1
            ectx.emit("RemoveEffect", target=tgt, effect_type=self.effect_type, removed=removed)
        return OperationResult.ok()


class SetOnFire(AbilityBehaviour):
    """`FireOfAbsolutionAbility.SetOnFire` (child `Func<entities,behaviour>` du `Maybe` natif @18121f380) ->
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
    """`DSLFactory.CreateShield @180ded000` -> `CreateShieldBehaviour.Execute @180fc2650` : pour CHAQUE cible
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
