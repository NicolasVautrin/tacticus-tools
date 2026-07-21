"""`IdunBattle.AI.Playbook.Loki.AggressiveOnslaughtPlaybook` — face ATTACK du triggered
AggressiveOnslaught (1248, Mataneo bloodIntercessor). Feuille `TriggeredAbilitiesUtility(2)` du
composite Damage(34), meme dispatcher que Psyker (`tile.py:evaluate_attack_in_steps`, vslot 3).

Chaine native mirroree (VAs base 0x180000000) :
  - `CalculateAttackUtilityInStepsInternal @1811638d0` : monte la SM d__3 (param_1=this @0x28,
    param_2=case @0x20, **param_3=delegue scorer @0x30**). Le delegue est fourni par l'APPELANT :
    `TriggeredAbilitiesUtility.<EvaluateAttackInStepsInternal>d__3.MoveNext @1810f64b0` appelle
    `playbook.CalculateAttackUtilityInSteps(case, delegate=this+0x58)`. Ce delegue (champ +0x58 de
    l'utility, cable au montage de l'arbre `UtilitiesDatabase.InitializeUtilities`) =
    `TriggeredAbilityPlaybook.GetUtilityValue @181510570` = lookup `Dict<string,int>` config plat
    (TryGetValue(dict, key) -> int, defaut 0). Psyker (d__2) IGNORE ce delegue et calcule ses damage
    events lui-meme ; AggressiveOnslaught (d__3) l'UTILISE une fois par summon avec une cle constante.

  - `<CalculateAttackUtilityInStepsInternal>d__3.MoveNext @181173e70` (corps, mirror ci-dessous) :
      1. casterTile = `UtilityAttackCase.get_CasterTile(case)` (= attack_tile) ;
         targetTiles = `EntityExtensions.GetTiles(case.target@0x20)`.
         GATE 1 : `TileExtensions.IsAdjacentTo(casterTile, targetTiles)` -> sinon 0.
      2. GATE 2 : `BattleQuery.IsTargetInAttackRangeForSummon @1810700d0` (slot itf 0xcc sur
         IBattleQuery, args caster@0x10 / casterTile / target@0x20) -> bool. Le natif : target
         `IsTargetable` + la portee d'attaque du SUMMON (GetUnitConfig -> weapon range, RangedInMelee,
         CanMeleeAttackOverElevationDifference) couvre la cible depuis une tuile adjacente.
         [PORTE PARTIEL : target vivant/targetable ; la portee summon melee (bloodSmnIntercessor,
          jump-pack, place ADJACENT a la cible) est trivialement satisfaite sur board sans elevation
          -> non modelisee ici. Cf. residus du rapport.]
      3. tiles = `BattleQuery.GetFreeAdjacentTiles(target) @181061570` (slot itf 0x51 =
         `GetAdjacentTiles(target,1,1,0)` + FilterInPlace) ; pour chaque tuile :
         `TileExtensions.CanAddUnit(tile, summonUnitType, ...)`. => tuiles LIBRES placables ring-1 de
         la cible = `battle_query.adjacent_addable_count(target_pos)` (MEME primitive que ScarabHive,
         GetAdjacentTiles + CanAddUnit).
      4. Boucle : chaque tuile libre trouvee -> count++ ; SI `GetMaxSummon <= count` -> break (SANS
         scorer cette tuile) ; sinon `delegate() += weight`. => summons scores = min(free, maxSummon-1).
      5. u = `Fix64.FromInt(summons_scores * weight)`.

  - `AggressiveOnslaught_SummonAbility.GetMaxSummon @180e156c0` = `AbilityConfiguration.
    GetNumberConstant(config, 0x10)` = `constants.nrOfSummons` (gameconfig 1248 : nrOfSummons=2).

=> **value = min(free_placeable_adjacent(target), nrOfSummons - 1) x weight**, avec
   weight = `Utilities.Default.TriggeredAbilities.AggressiveOnslaught_PerFreeTileAfterCharge` (= 40,
   MESURE ET config-derive — le 40 EMERGE du BC, jamais code en dur), nrOfSummons = config.
   Pour 1248 (maxSummon=2) : cap=1 -> value = 40 des qu'au moins une tuile libre est adjacente a la
   cible (et gates OK), sinon 0. Delta case-52 §#54B (u81 : +40 = 1x40).
"""
from __future__ import annotations

import hexgeo
import gameconfig as GC

from engine import battle_query as bq
from ..entities.triggered_ability_type import TriggeredAbilityType

# Nom config de l'ability 1248 (l'enum membre == la cle gameconfig).
_ABILITY_NAME = TriggeredAbilityType.AggressiveOnslaught.name   # "AggressiveOnslaught"
# Cle du poids plat `Utilities.Default.TriggeredAbilities` lue par le delegue GetUtilityValue @181510570.
_WEIGHT_KEY = "AggressiveOnslaught_PerFreeTileAfterCharge"


class AggressiveOnslaughtPlaybook:
    """`AggressiveOnslaughtPlaybook` (`IdunBattle.AI.Playbook.Loki`, ability 1248). Seule la face
    ATTACK est portee (la face MOVE `CalculateMovementUtilityInStepsInternal @181163950` = 0 de base)."""

    ability_id: int = int(TriggeredAbilityType.AggressiveOnslaught)   # 1248

    def _max_summon(self) -> int:
        """`GetMaxSummon @180e156c0` = `GetNumberConstant(abilityConfig, 0x10)` = constants.nrOfSummons."""
        a = GC.ability(_ABILITY_NAME) or {}
        try:
            return int((a.get("constants") or {}).get("nrOfSummons") or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _free_placeable_adjacent(scene, target_pos) -> int:
        """slot 0x51 `GetFreeAdjacentTiles(target)` @181061570 + CanAddUnit -> #tuiles LIBRES placables
        ring-1 de la cible, sur le board COURANT (le natif lit l'ECS live, caster a son origine).
        = `adjacent_addable_count` (GetAdjacentTiles + CanAddUnit ; porte |dElev|<2)."""
        board = getattr(scene, "board", None)
        if board is None or target_pos is None:
            return 0
        from ..ai.state_bridge import _board_topology_maps   # lazy : evite tout cycle d'import
        _tid, neigh_by_pos, walkable_by_pos, _terr = _board_topology_maps(board)
        # occupied = positions de TOUTES les unites VIVANTES (CanAddUnit = tuile vide sur l'ECS live).
        occupied = {(u["pos"]["col"], u["pos"]["row"]) for u in (scene.units or [])
                    if u.get("alive") and u.get("pos") and u["pos"].get("col") is not None}
        return bq.adjacent_addable_count(target_pos, neigh_by_pos, walkable_by_pos,
                                         occupied, getattr(scene, "elev_by_pos", None))

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile) -> float:
        """Mirror `<CalculateAttackUtilityInStepsInternal>d__3.MoveNext @181173e70` (gates ->
        free-tiles -> boucle bornee maxSummon-1 -> Fix64.FromInt(count x weight))."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None:
            return 0.0
        tpos = sc.pos(case_tgt_id)
        if tpos is None:
            return 0.0
        # GATE 1 : casterTile (attack_tile) adjacent a la cible (IsAdjacentTo, board + porte elevation).
        if not bq.is_adjacent(attack_tile, tpos, getattr(sc, "elev_by_pos", None)):
            return 0.0
        # GATE 2 : IsTargetInAttackRangeForSummon (partiel : cible vivante/targetable ; portee summon
        # melee adjacente triviale sur board plat -> non modelisee au-dela du "vivant").
        tgt = next((u for u in (sc.units or []) if u.get("id") == case_tgt_id), None)
        if tgt is None or not tgt.get("alive"):
            return 0.0
        # GetMaxSummon = nrOfSummons (config). maxSummon<=1 -> aucune tuile scoree (cap = maxSummon-1).
        max_summon = self._max_summon()
        if max_summon <= 1:
            return 0.0
        free = self._free_placeable_adjacent(sc, tpos)
        summons_scored = min(free, max_summon - 1)
        if summons_scored <= 0:
            return 0.0
        # delegate() = GetUtilityValue(Utilities.Default.TriggeredAbilities[<cle>]) -> weight (40, config).
        weight = ctx.wt.triggered(_WEIGHT_KEY)
        return float(summons_scored * weight)
