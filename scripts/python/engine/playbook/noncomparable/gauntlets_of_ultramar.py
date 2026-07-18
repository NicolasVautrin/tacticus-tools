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

    - utilité(T) = `SelectUniqueUnits(GetAllTargetsSelector(caster@T), 3).Count` = # ennemis DISTINCTS dans
      l'arc(dist<=2) depuis T, PLAFONNÉ à 3. `GetAllTargetsSelector @1811e2090` = ring1 (`Enemies(
      AdjacentTiles)`, élévation-gaté) + ring2 (`Unobscured(SurroundingEnemies(r=2) - Adjacent)`, dist-2).
      `GenerateAction(MainTile(T), Fix64(count))` + `Bucket.AddAction`.
    - MIN_UTILITY (bucket, DYNAMIQUE) = `Min(Fix64(3), Fix64(#ennemis TOTAUX du caster))` : la const 3 vient
      du cctor @18113ed50 ; le compte vient de `Enemies(query, Entity(caster), AllTiles=*(query+0x80), 2)`
      -> `UnitsByTeamSelector` board-WIDE (PAS l'arc) @180deedd0. => Gauntlets ne caste QUE s'il peut
      atteindre `min(3, #ennemis restants)` ennemis dans son arc (sinon il attend d'en avoir assez à portée).
      util(origine) == floor par construction (les deux plafonnés à 3) -> best>=floor toujours vrai ; le
      gate BINDANT est `best >= min(3, #ennemis totaux)` VS l'arc atteignable.
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
    v1 FLAG : `Unobscured` (LoS ring2) passe-tout (donnée LoS absente offline) -> peut sur-compter ring-2 ;
    l'arc ring2 n'applique PAS la porte d'élévation (SurroundingEnemies != IterateAdjacentTiles) ; ordre
    EXACT ring-2 (cible) non validé (fallback dernier) -- ring-1 = cas commun validé."""
    ABILITY_ID = int(ActiveAbilityType.GauntletsOfUltramar)  # 1000
    MIN_UTILITY = 1.0     # plancher structurel (>=1 ennemi éligible) ; vrai gate = min(3, #ennemis totaux)
    PRIORITY = 0
    _CAP = 3              # SelectUniqueUnits(3) : l'ability touche au plus 3 unités -> utilité plafonnée à 3

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        floor = min(self._CAP, len(ctx.epos or []))   # Min(3, #ennemis TOTAUX) = seed du bucket natif
        best_t, best_u = None, None
        # ORIGINE D'ABORD + remplacement STRICT `>` (Bucket.AddAction keep-first @1813fbcc0, NullPosition
        # toujours evaluee) -> le caster CASTE EN PLACE a egalite d'arc, ne BOUGE que sur gain STRICT
        # (#117 : natif (3,5)=(4,5) arc 5 -> caste @origine (3,5) ; le port balayait reach_nc=[moves,origine]
        # -> gardait un move au tie -> best_t faux -> cible fausse car cible suit best_t). Mirror #76/#80.
        for T in _sweep_origin_first(ctx):
            u_ = float(min(self._CAP, bq.count_enemies_in_arc(T, ctx.epos, ctx.elev_by_pos)))
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
