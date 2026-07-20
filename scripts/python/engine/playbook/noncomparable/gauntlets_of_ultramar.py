"""GauntletsOfUltramarPlaybook — AoE arc NonComparable (utilite = # ennemis a portee <=2)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first


class GauntletsOfUltramarPlaybook(NonComparablePlaybook):
    """`GauntletsOfUltramarPlaybook.EvaluateNonComparable @18113e5a0` (id 0x3e8=1000, ultraCalgar). AoE
    dégât sur l'arc (ring1+ring2) — mais NonComparable : l'utilité est une heuristique de COMPTE d'ennemis
    à portée (aucun `ProbableDamageEvent` -> exclu de la prédiction de dégât, cf. #109). Le caster BOUGE
    vers la tuile qui maximise le nombre d'ennemis touchés.

    - utilité(T) = COMPTE NON CAPPÉ des ennemis ADJACENTS (ring-1, porte élévation |Δelev|<2) à T.
      RE case-49 (docs/rl/case-49-gauntlets-unobscured.md) : le sélecteur natif `GetAllTargetsSelector
      @1811e2090` = ring1 (`Enemies(AdjacentTiles)`) + ring2 (`Unobscured(SurroundingEnemies(r=2) -
      Adjacent)`), MAIS le terme ring-2 contribue TOUJOURS 0 — prouvé LIVE (probes 49b/49c s14 31337 :
      ennemi VISIBLE terrain à dist 2, chemin 2-pas LIBRE -> bucket vide ; 3 ennemis déplacés sur les
      voisins de (5,4) -> util=3 EXACTEMENT = ring-1 seul ; mécanisme décompilé en cours de preuve,
      piste : SurroundingTilesSelector @180ef6100 / portée slot 0x65 exclut les tuiles occupées).
      `SelectUniqueUnits @1810108b0` : le « 3 » = UnitSelectionType (filtre PAR-unité via
      `SelectUnit @181010de0` -> MatchesUnitSelectionType), PAS un cap de compte -> util NON plafonnée.
      `GenerateAction(MainTile(T), Fix64(count))` + `Bucket.AddAction`.
    - ADMISSION bucket (case-49, décompilé + confirmé live 49c) : `util >= Min(Fix64(3),
      Fix64(#ennemis TOTAUX))` — LOOSE (`op_GreaterThanOrEqual`, porte @18004cc80 appelée par
      AddAction @1813fbcc0 ; util 3 == seed 3 ADMIS, mesuré). Le `op_GreaterThan` STRICT de AddAction
      ne sert qu'au remplacement ENTRE actions déjà admises (keep-first #117). La const 3 vient du
      cctor @18113ed50 ; le compte total de `Enemies(query, Entity(caster), AllTiles, 2)` ->
      `UnitsByTeamSelector` board-WIDE @180deedd0. => Gauntlets ne caste QUE si son compte
      d'ADJACENTS atteint `min(3, #ennemis restants)`.
    - ctor @18113edc0 = `NonComparablePlaybook(1000)` : 1er arg = ABILITY_ID (PAS priorité) ; aucun
      `get_Priority` override -> PRIORITY=0 (défaut). [#115 : 1er arg ctor = ability_id, confirmé ici.]
    - POSITION (#117) : sweep ORIGINE D'ABORD (`_sweep_origin_first`) + remplacement STRICT `>`
      (Bucket.AddAction keep-first @1813fbcc0, NullPosition toujours évaluée) => à ÉGALITÉ d'arc le caster
      CASTE EN PLACE (origine), ne BOUGE que sur gain STRICT. Mirror #76/#80. VALIDÉ LIVE (natif (3,5)=(4,5)
      arc 5 -> caste @origine (3,5), pas le move tile).
    - CIBLE EXACTE (#117) : le natif boucle sur `GetEligibleTargetsSelectable(caster, MainTile)` et
      `GenerateAction(position, eligible_target, Fix64(count))` (local_1a8 = eligible target, un ENNEMI ;
      1 action/eligible target, MÊME utilité -> bucket keep-first). L'énumération est INVERSÉE
      (`DSLFactory.Tiles`=`SortReverseSelector @180dfdc60`) => cible = 1er ennemi ring-1 dans l'ordre
      `boardGraph.neighbours` (GetAdjacentTiles natif) **INVERSÉ**, sinon ring-2 (`bq.gauntlets_target`).
      VALIDÉ LIVE BIT-EXACT (#117 : natif tgt=118 = ultraCalgar @(3,5) ring-1 [80,114,78,118]_fwd inversé).
      PAS la MainTile ni None.
    v1 FLAG (résiduel) : ordre EXACT ring-2 (cible) non validé (fallback dernier) -- ring-1 = cas commun
    validé ; la CIBLE garde l'arc ring1+ring2 (sélecteur eligible-targets distinct de l'utilité)."""
    ABILITY_ID = int(ActiveAbilityType.GauntletsOfUltramar)  # 1000
    MIN_UTILITY = 1.0     # plancher structurel (>=1 ennemi éligible) ; vrai gate = min(3, #ennemis totaux)
    PRIORITY = 0
    _FLOOR_CONST = 3      # const Fix64(3) du cctor @18113ed50 (seed bucket) — PAS un cap d'utilité (case-49)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        floor = min(self._FLOOR_CONST, len(ctx.epos or []))   # Min(3, #ennemis TOTAUX) = seed du bucket natif
        best_t, best_u = None, None
        # ORIGINE D'ABORD + remplacement STRICT `>` (Bucket.AddAction keep-first @1813fbcc0, NullPosition
        # toujours evaluee) -> le caster CASTE EN PLACE a egalite d'arc, ne BOUGE que sur gain STRICT
        # (#117 : natif (3,5)=(4,5) arc 5 -> caste @origine (3,5) ; le port balayait reach_nc=[moves,origine]
        # -> gardait un move au tie -> best_t faux -> cible fausse car cible suit best_t). Mirror #76/#80.
        for T in _sweep_origin_first(ctx):
            # ring-1 SEUL, NON cappé (case-49 : terme ring-2 natif structurellement 0, probes 49b/49c)
            u_ = float(bq.count_adjacent(T, ctx.epos, ctx.elev_by_pos))
            if best_u is None or u_ > best_u:    # strict > : origine gagne le tie (elle est en tete)
                best_t, best_u = T, u_
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] Gauntlets floor(min3,total)={floor} best={best_t} u={best_u}",
                  file=sys.stderr)
        if best_u is None or best_u < max(self.MIN_UTILITY, float(floor)):   # bucket gate: util >= Min(3,total)
            return []
        # CIBLE = eligible target EXACT du natif (GenerateAction(pos, eligible_target, util) @18113e5a0) =
        # 1er ennemi ring-1 dans l'ordre voisins natif INVERSÉ (SortReverse + bucket keep-first), sinon
        # ring-2. VALIDÉ LIVE #117 (natif tgt=118). Fallback ordre-arc si neigh_by_pos absent (offline pur).
        target = bq.gauntlets_target(best_t, ctx.enemies, ctx.neigh_by_pos, ctx.elev_by_pos)
        return [{"target": target, "ability": self.ABILITY_ID,
                 "to": (best_t if best_t != ctx.origin else None), "pred": best_u}]
