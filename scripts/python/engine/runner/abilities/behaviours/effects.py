"""Feuilles DSL de POSE/RETRAIT d'effets runner-couplees : `AddBondEffect` (effet BOND source<->target),
`AddEffect` (effet sur unite OU tuile), `RemoveEffect` (retrait + revert StatModification), `SetOnFire`
(effet FEU de tuile), `CreateShield` (bouclier). Wrappers au-dessus de `runner/operations/effects.py` +
`stat_ops.py`. Namespace natif `Entities.Behaviours.*`."""
from __future__ import annotations

from ....dsl.base import TargetsSelector, resolve_unit, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ..base import turns_from_rounds


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
    explicite (CrushingClaws Taunt / GetEmRuntz = `TurnsFromRounds(1)`). MEME semantique None que `AddEffect`."""
    __slots__ = ("effect_type", "name", "source_ref", "target_ref", "duration_rounds")

    def __init__(self, effect_type: int, name: str, source_ref: TargetsSelector, target_ref: TargetsSelector,
                 duration_rounds=1):
        self.effect_type, self.name = effect_type, name
        self.source_ref, self.target_ref = source_ref, target_ref
        self.duration_rounds = duration_rounds

    def execute(self, entities, ectx):
        from ...operations.effects import AddEffectOperation
        su = resolve_unit(self.source_ref, entities)
        tu = resolve_unit(self.target_ref, entities)
        src = su.get("id") if su else None
        tgt = tu.get("id") if tu else None
        if src is None or tgt is None or ectx.state is None:
            return OperationResult.ok()
        # duration_rounds None -> pas d'override = duree DEFAUT (DefaultAmountOfRounds), mirror de l'arg natif
        # duree-node ZERO d'AddBondEffect sans TurnsFromRounds (ValkyrieStrike 1022) ; sinon TurnsFromRounds(rounds).
        dur = turns_from_rounds(self.duration_rounds) if self.duration_rounds is not None else None
        AddEffectOperation.execute(ectx.state, source=src, target=tgt, effect_type=self.effect_type,
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
    CrushingClaws) vs explicite (ThunderousAssault Stunned = `TurnsFromRounds(1)`)."""
    __slots__ = ("effect_type", "name", "target_sel", "duration_rounds")

    def __init__(self, effect_type: int, name: str, target_sel: TargetsSelector, duration_rounds=1):
        self.effect_type, self.name = effect_type, name
        self.target_sel, self.duration_rounds = target_sel, duration_rounds

    def execute(self, entities, ectx):
        from ...operations.effects import AddEffectOperation
        state = ectx.state
        src = (entities.caster or {}).get("id")               # AbilityStateReference = caster (source)
        if state is None or src is None:
            return OperationResult.ok()
        # duration_rounds None -> pas d'override = duree DEFAUT (DefaultAmountOfRounds), mirror de l'arg natif
        # `0` d'AddEffect sans TurnsFromRounds (Pinned CrushingClaws) ; sinon TurnsFromRounds(rounds).
        dur = turns_from_rounds(self.duration_rounds) if self.duration_rounds is not None else None
        for elem in _add_effect_targets(self.target_sel.evaluate(entities)):  # natif : itere le selecteur
            tgt = _add_effect_target_id(elem, state)          # unit dict->id | (col,row)->tile id | int->tile id
            if tgt is None:
                continue
            eff = AddEffectOperation.execute(state, source=src, target=tgt, effect_type=self.effect_type,
                                             name=self.name, duration_override=dur)
            ectx.emit("AddEffect", source=src, target=tgt, effect_type=self.effect_type,
                      placed=eff is not None)
        return OperationResult.ok()


class RemoveEffect(AbilityBehaviour):
    """`DSLFactory.RemoveEffect @180df9cc0` -> `RemoveEffectBehaviour.Execute` : retire de la cible TOUS les
    effets du type `effect_type` (non consommes) et ANNULE leur StatModification (`<Effect>.RevertInternal`).
    `target` = `target_sel` (ex. `Caster()`/`Self@0x148` pour le reset ActOfFaith @181219eb0). Wrapper au-dessus
    de l'Operation impurative `revert_change_stat` (mirror exact de l'ancien `_reset_act_of_faith`). No-op si
    `state.effects`/cible absents. Emet 'RemoveEffect' (removed = nb de stacks retires). Effet PUR (stop=False).

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
        tu = resolve_unit(self.target_sel, entities)
        tgt = tu.get("id") if tu else None
        if tgt is None:
            return OperationResult.ok()
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
