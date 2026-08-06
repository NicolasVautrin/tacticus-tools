"""`Abilities.Triggered.Loki.ArcaneShieldAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateTrigger) — bouclier de Thaumachus (`thousSorcerer`,
ThousandSons, passive `ArcaneShield`). Cf. `loki/__init__.py` pour le regroupement « Loki »."""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import StatsComponent, OwnerComponent, UnitComponent
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.effects import CreateShield
from .....entities.traits.unit_trait import UnitTrait, has_trait
from .....entities.selectors.accessors import Target
from .....entities.effects.magnitude import ability_var
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from ..base import TriggeredAbility, TriggerEvent, _unit_tile, _hex_dist, _faction_id
from .....entities.effects.loki.dark_angels_passives import _is_targetable
from .....entities.effects.loki.dark_angels_passives import grand_alliance_of
from ....abilities.base import convert_rounds_to_turns

ARCANESHIELD_ID = "ArcaneShield"
ARCANESHIELD_RANGE = 2          # DEFAUT de `ArcaneShield.constants.range` (= 2 dans le gameconfig lu).
ARCANESHIELD_TRAIT_EXCLUDE = UnitTrait.Steppable  # `UnitsWithoutTrait(0x1b=27=Steppable)` : exclus du ciblage.
# ⚠ FIX #135 : etait `0x1b` (int) compare a `ctx.traits` (NOMS gameconfig) -> `27 in [strings]` toujours False
#   (gate mort : les allies Steppable/tokens etaient ciblables a tort). Gate desormais via `has_trait` (#146 :
#   mapping id<->nom centralise dans UnitTrait -> plus de comparaison int-vs-str possible).

# `Multiply(AverageDistance(Caster@0x148, Units(It@0x180)), Get(3))` du terme
# `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$Distance` : la distance pese 3
# par hex dans le score de tri. C'est CE poids qui fait dominer la distance sur la faction (poids 1).
ARCANESHIELD_DISTANCE_WEIGHT = 3
# `Get(range * 3 + 4)` du terme `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$Owner` :
# la penalite du CASTER, calibree pour depasser STRICTEMENT le pire score d'un autre candidat
# (`3*range + 1 + 1`). C'est ainsi que le natif realise le « lastly casting it on himself » — pas par un
# palier de priorite, mais par une constante additive qui le relegue toujours dernier.
ARCANESHIELD_OWNER_PENALTY_OFFSET = 4
# `GrandAllianceId` dont `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` derive le pseudo-trait
# `UnitTrait.Chaos` (0x7ea = 2026) teste par `...ArcaneShieldAbility$$Chaos`.
ARCANESHIELD_CHAOS_ALLIANCE = "Chaos"


def _arcaneshield_range() -> int:
    """`GetNumberConstant(config, 0x16)` = `AbilityConstantType 22 = range` — le rayon de
    `SurroundingFriends`, ET la base de la penalite `Owner` (`range * 3 + 4`)."""
    import gameconfig as GC
    return int(((GC.ability(ARCANESHIELD_ID) or {}).get("constants") or {}).get("range")
               or ARCANESHIELD_RANGE)


def _arcaneshield_candidates(state: State, owner_id: int) -> list[tuple[int, int]]:
    """Pool de `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateBehaviour`
    (collapse S), lu verbatim au decompile :

        Randomize( UnitsWithoutTrait(
                     SurroundingFriends(Caster@0x148, GetNumberConstant(0x16 = range),
                                        unique = true, UnitSelectionType.OnlyAliveAndTargetable = 3),
                     trait = 0x1b = 27 = Steppable,
                     UnitSelectionType.OnlyAliveAndTargetable = 3) )
        op_Addition Caster@0x148

    Rend `[(distance_hex, entity_id)]`. Points qui tranchent une lecture fautive :
      - `SurroundingFriends` ne filtre NI sur la faction NI sur le trait Chaos : **un allie non-Chaos
        est un candidat legitime** (il ne porte qu'une penalite de +1 dans le score). C'est la reponse
        au residu N1, qui soutenait l'inverse ;
      - le CASTER n'est PAS dans `SurroundingFriends` (= `SurroundingTiles(range) - Tiles(self)`) : il
        est rajoute a la main par `TargetsSelector.op_Addition`, donc toujours candidat de dernier
        recours, avec `distance = 0` ;
      - `OnlyAliveAndTargetable` : le volet « Targetable » retire les unites en Deep Strike
        (`TeleportStrike_TeleportingIn`) — meme collapse `_is_targetable` que le port LionHelm, ou il
        a ete MESURE live (`entities/effects/loki/dark_angels_passives.py`).

    RESIDU RNG assume : `Randomize` = `PickRandomAmountSelector(amount = 0x7fffffff)` consomme
    `len(pool)` tirages et melange le pool AVANT le tri stable ; les EX AEQUO de score sont donc
    departages au HASARD cote natif. Le port collapse ce melange en ordre d'id CROISSANT (meme choix,
    et meme motif, que `genestealer.py`) : le tri ne departage pas comme le natif sur ex aequo, mais
    aucun tirage parasite n'est injecte dans le flux PRNG partage."""
    board = state.board
    owner = state.get_entity(owner_id)
    if board is None or owner is None:
        return []
    oc = owner.get_component(OwnerComponent)
    ot = _unit_tile(state, board, owner_id)
    if oc is None or ot is None:
        return []
    rng = _arcaneshield_range()
    out: list[tuple[int, int]] = []
    for eid, e in sorted(state.entities.items()):        # collapse deterministe du `Randomize`
        if eid == owner_id:
            continue                                     # `SurroundingTiles(range) - Tiles(self)`
        c = e.get_component(OwnerComponent)
        u = e.get_component(UnitComponent)
        if c is None or c.team != oc.team:               # `Friends` : meme equipe
            continue
        if u is not None and not u.alive:                # `OnlyAlive`
            continue
        if not _is_targetable(state, eid):               # volet `Targetable` d'OnlyAliveAndTargetable
            continue
        sc = e.get_component(StatsComponent)
        if sc is not None and has_trait(sc.ctx.traits, ARCANESHIELD_TRAIT_EXCLUDE):
            continue                                     # `UnitsWithoutTrait(0x1b = Steppable)`
        t = _unit_tile(state, board, eid)
        if t is None:
            continue
        d = _hex_dist(board, ot, t, rng)                 # `SurroundingFriends(., range)`
        if d is None:
            continue
        out.append((d, eid))
    out.append((0, owner_id))                            # `op_Addition Caster@0x148`
    return out


def _arcaneshield_score(state: State, owner_id: int, cand_id: int, dist: int, rng: int) -> int:
    """`Sum(Distance, Faction, Chaos, Owner)` — les QUATRE termes de la formule de tri, chacun expose
    par un symbole natif dedie (mirror 1:1) :

        IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$Distance
            = Multiply( AverageDistance(Caster@0x148, Units(It@0x180, unique, onlyAlive)), Get(3) )
        IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$Faction
            = ConditionalAmount( IsSameFaction(Caster@0x148, It@0x180), Zero, Get(1) )
        IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$Chaos
            = ConditionalAmount( HasTrait(It@0x180, 0x7ea = 2026 = UnitTrait.Chaos), Zero, Get(1) )
        IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$Owner
            = ConditionalAmount( op_LogicalNot(AreEqual(Caster@0x148, Units(It@0x180))),
                                 Zero, Get(range * 3 + 4) )

    `Zero` = `DSLFactory+0xb8`, la premiere des cinq constantes-formules posees par
    `IdunBattleLogic.Entities.DSLFactory$$.ctor` (`+0xb8..+0xd8` = 0, 1, 2, 100, -1).
    `IdunBattle.Entities.Formulas.ConditionalAmount$$Calculate` evalue le trigger `+0x10` puis prend
    `+0x18` (`formulaTrue`) si VRAI, `+0x20` (`formulaFalse`) sinon — d'ou « penalite quand la
    condition est FAUSSE » pour Faction/Chaos, et « penalite quand le candidat EST le caster » pour
    Owner.

    ⚠ C'est un SCORE ADDITIF, pas un ordre lexicographique a paliers : la distance pese 3, la faction
    et le trait Chaos pesent 1 chacun. **Un allie non-Chaos a distance 1 (score 5) passe donc DEVANT
    un ThousandSons a distance 2 (score 6).** Le port historique triait `(palier_faction, distance)`
    et choisissait l'inverse.

    `UnitTrait.Chaos` n'est dans la liste `traits` d'AUCUN kit gameconfig : c'est un pseudo-trait
    DERIVE de la grande alliance (`idun.Idun.Source.Shared.GrandAlliance$$GetTrait` : "Imperial"->26,
    "Xenos"->1006, "Chaos"->2026), injecte dans la `BattleConfiguration` par la couche meta. Un
    `has_trait(ctx.traits, 2026)` naif serait TOUJOURS faux et la branche serait morte -> on passe par
    `grand_alliance_of` (le maillon deja porte, utilise par les passifs Dark Angels)."""
    own_fac = _faction_id(state, owner_id)
    fac = _faction_id(state, cand_id)
    score = ARCANESHIELD_DISTANCE_WEIGHT * int(dist)                       # $$Distance
    if not (own_fac is not None and fac == own_fac):                       # $$Faction
        score += 1
    if grand_alliance_of(state, cand_id) != ARCANESHIELD_CHAOS_ALLIANCE:   # $$Chaos
        score += 1
    if cand_id == owner_id:                                                # $$Owner
        score += rng * ARCANESHIELD_DISTANCE_WEIGHT + ARCANESHIELD_OWNER_PENALTY_OFFSET
    return score


def _arcaneshield_target(state: State, owner_id: int) -> int:
    """`First( SortByFormula(pool, Sum(Distance, Faction, Chaos, Owner), ascending = true), 1 )`.

    `IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select` : champ `+0x28` (`ascending`) == 0 ->
    `Enumerable.OrderByDescending`, sinon `Enumerable.OrderBy` — le call-site passe `1`, donc tri
    ASCENDANT (le plus PETIT score gagne) et STABLE (les ex aequo gardent l'ordre SOURCE). Le tri
    Python `sorted` est stable lui aussi : la cle est le SCORE SEUL, l'ordre source venant de
    `_arcaneshield_candidates`.

    Sans board (pas d'adjacence) -> soi, comme le pool reduit au seul `op_Addition Caster`."""
    cands = _arcaneshield_candidates(state, owner_id)
    if not cands:
        return owner_id
    rng = _arcaneshield_range()
    best = sorted(cands, key=lambda c: _arcaneshield_score(state, owner_id, c[1], c[0], rng))
    return best[0][1]


def _arcaneshield_grant(state: State, owner_id: int) -> Optional[dict]:
    """Behaviour ArcaneShield (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateBehaviour), MIGRÉ en ARBRE DSL (#149 slice-23) :
    `CreateShield(<best>, ConfigVar(0x27=shieldHp), self.Id, TurnsFromRounds(1))`. Le montant
    `shieldHp[passive_level] × mult%` (formule V `ConfigVar`) est calculé IMPÉRATIVEMENT (`ability_var`)
    et passé comme scalaire ; le sélecteur AI-target LOURD (S) reste `_arcaneshield_target`, COLLAPSÉ en
    `Target()` (== FinalJustice, doctrine slice-18/19). Bit-exact vs l'ancien corps impératif BY
    CONSTRUCTION : la feuille `CreateShield` appelle le MÊME `ShieldComponent.add_or_update_shield(amount,
    "ArcaneShield", remaining=1)`. No-op si amount<=0 (stats/config absents)."""
    owner = state.get_entity(owner_id)
    sc = owner.get_component(StatsComponent) if owner is not None else None
    if sc is None:
        return None
    ctx = sc.ctx
    amount = int(ability_var(ARCANESHIELD_ID, "shieldHp",
                             int(getattr(ctx, "passive_ability_level", 0) or 0),
                             multiplier_pct=int(getattr(ctx, "ability_variables_multiplier", 100) or 100)) or 0)
    if amount <= 0:
        return None
    target = _arcaneshield_target(state, owner_id)
    if state.get_entity(target) is None:
        return None
    ectx = ExecutionContext(state=state, rng=state.rng)
    # #98 : le 4e arg natif est `TurnsFromRounds(1)` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateBehaviour) -> la duree du
    # BOUCLIER passe elle aussi par `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns`. Le decay est
    # `IdunBattle.Operations.EndTurnOperation$$RemoveOneTurnOnShields` (1 par EndTurn) = MEME cadence que le tick d'effets.
    dur = convert_rounds_to_turns(state, 1)
    CreateShield(Target(), amount, duration=dur, source=ARCANESHIELD_ID).execute(  # TurnsFromRounds(1)
        entities_from_state(state, owner_id, target), ectx)
    p = next((p for (n, p) in ectx.emitted if n == "CreateShield"), None)
    if p is None:
        return None
    return {"ability": ARCANESHIELD_ID, "owner": owner_id, "target": target, "amount": amount,
            "remaining": dur, "shield_total": p.get("shield_total")}


class ArcaneShieldAbility(TriggeredAbility):
    """`ArcaneShieldAbility` (IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateTrigger CreateTrigger / IdunBattleLogic.Entities.Abilities.Triggered.Loki.ArcaneShieldAbility$$CreateBehaviour CreateBehaviour) — bouclier de
    Thaumachus (`thousSorcerer`, ThousandSons, passive `ArcaneShield`).

    TRIGGER natif, lu verbatim :

        On(0x1c, ownerNeedsToBeAlive = 1)
          op_BitwiseAnd get_OwnerIsActor
          op_BitwiseAnd get_OwnerIsCaster

    `0x1c = 28 = EventTriggerType.ArrivedAtFinalTile` = « l'unite a TERMINE son activation ». Il n'y a
    AUCUNE branche `On(4 = UnitAfterMove)` cote natif — le port l'approximait ainsi, ce qui privait
    Thaumachus de son bouclier quand il finissait son tour SANS bouger. Les deux emetteurs natifs de
    `On(0x1c)` (tous deux gardes par le MEME flag `UnitFlag.ArrivedAtFinalTile`, donc AU PLUS UN fire
    par activation — pas de double pose quand l'unite bouge PUIS finit son tour) :

      * `IdunBattle.Operations.MoveUnitOperation$$Execute` : `Add(1)` puis, APRES
        `EvaluateAfterMoveTriggers`, publie `On(0x1c)` SSI le flag venait d'etre AJOUTE ;
      * `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` : `Add(1)` puis publie `On(0x1c)`
        SSI le flag venait d'etre ajoute ET `!forced` — la cloture de tour d'une unite qui n'a PAS
        bouge.

    Cote port, le vecteur `arrived_at_final_tile_triggers` (`triggers/dispatch/move_death.py`, apporte
    par `SpiritualLeader`) porte deja ces deux points d'emission et le gate par flag.

    `get_OwnerIsCaster` : sur CE vecteur, l'event est publie avec `actor == target == l'unite qui
    termine son activation` et il n'existe pas de caster distinct -> la clause coincide avec
    `get_OwnerIsActor`, deja materialisee par `matches`. (Meme lecture que `SpiritualLeaderAbility`,
    qui n'a que `get_OwnerIsActor` sur le meme event.)

    BEHAVIOUR : accorde un bouclier `shieldHp` (variable rarete -> `x AbilityVariablesMultiplier`)
    duree `TurnsFromRounds(1)` a l'ami de MEILLEUR score dans le rayon (`range` = 2 ;
    `UnitsWithoutTrait(Steppable)` ; `OnlyAliveAndTargetable`), le caster restant le dernier recours.
    Le classement est un SCORE ADDITIF `3*distance + faction + chaos + owner` — cf.
    `_arcaneshield_score` : **la distance domine la faction**."""
    event_id = EventTriggerType.ArrivedAtFinalTile

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id != self.owner_id:                 # get_OwnerIsActor (== get_OwnerIsCaster ici)
            return False
        owner = state.get_entity(self.owner_id)
        uc = owner.get_component(UnitComponent) if owner is not None else None
        if uc is not None and not uc.alive:
            return False
        return True

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _arcaneshield_grant(state, self.owner_id)
