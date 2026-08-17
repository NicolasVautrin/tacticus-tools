"""GauntletsOfUltramarPlaybook — AoE arc NonComparable (utilite = ring1(T) UNION disque-2 REEL)."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first


class GauntletsOfUltramarPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.GauntletsOfUltramarPlaybook$$EvaluateNonComparable` (id 0x3e8=1000, ultraCalgar). AoE
    dégât sur l'arc — mais NonComparable : l'utilité est une heuristique de COMPTE d'ennemis (aucun
    `ProbableDamageEvent` -> exclu de la prédiction de dégât, cf. #109). Le caster BOUGE vers la tuile
    qui maximise le compte.

    - utilité(T) = `SelectUniqueUnits(GetAllTargetsSelector, ctx(T), 3).Count` NON cappée, avec
      **DEUX ANCRAGES DIFFÉRENTS** (case-49x, décompilé + prouvé live — c'est la clé qui a réconcilié
      les mesures contradictoires E1/E2/E3 de case-49) :
        · `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$GetAdjacentTargetsSelector` = `Unique(Enemies(Caster@+0x160,
          AdjacentTiles(CasterTile@+0x168), 3))` — **CasterTile = tuile du CONTEXTE** (`AbilityEntities`
          reçoit `MainTile(position balayée)` dans EvaluateNonComparable ; `IdunBattle.Entities.Selectors.CasterTileSelector$$Select` lit ctx.tiles ?? ctx.tile avant le fallback entité) -> **ring-1 autour de T**
          (porte élévation |Δelev|<2 d'IterateAdjacentTiles) = `bq.is_adjacent`.
        · `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$GetSurroundingTargetsSelector` = `Unobscured(SurroundingEnemies(Caster@+0x160,
          r=2) − Adjacent)` — **Caster = ENTITÉ** (`IdunBattle.Entities.Selectors.CasterSelector$$Select` -> ctx.casterEntity ;
          `IdunBattle.Entities.Selectors.SurroundingTilesSelector$$Select` prend `GetMainTile(entité)` = tuile RÉELLE dans
          l'état ECS, PAS la tuile balayée) -> **disque dist<=2 autour de la position RÉELLE**,
          T-indépendant = `bq.surrounding_enemies` (tuiles occupées INCLUSES : flag
          requireEmptyOrSteppable=0 mesuré au IdunBattle.Entities.Selectors.SurroundingTilesSelector$$.ctor ; Unobscured depuis la tuile réelle).
      => util(T) = |ring1(T) ∪ surrounding(RÉEL)| (dédup `IdunBattle.DSL.TargetsSelector$$SelectUniqueUnits` ; le « 3 » =
      UnitSelectionType via `IdunBattle.DSL.TargetsSelector$$SelectUnit` -> MatchesUnitSelectionType, PAS un cap).
      Le port de case-49 (« ring-1 seul, ring-2 structurellement mort ») était un OVERFIT : vrai
      quand disque(réel)=∅ (31337 s14 : ennemis à dist 3-5 du réel), falsifié par E1/C1_25
      (caster immobile : disque(réel)=2 -> util=2 ADMIS) — cf. docs/rl/case-49-gauntlets-unobscured.md.
    - GATE d'ÉLIGIBILITÉ par-position (prouvé live probe_49x phase B, 23/23) : le natif boucle sur
      `IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable(caster, MainTile(T))` et ne génère une action QUE s'il
      existe une cible dans l'ARC de T (dist<=2 de T) -> position sans cible = bucket vide MÊME si
      util >= floor (E1-repro : 6 positions vides = exactement celles à d>2 des 2 ennemis).
    - ADMISSION bucket (case-49, décompilé + confirmé live 49c) : `util >= Min(Fix64(3),
      Fix64(#ennemis TOTAUX))` — LOOSE (`op_GreaterThanOrEqual`, porte @18004cc80 appelée par
      IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction ; util 3 == seed 3 ADMIS, mesuré). Le `op_GreaterThan` STRICT de AddAction
      ne sert qu'au remplacement ENTRE actions déjà admises (keep-first #117). La const 3 vient du
      IdunBattle.AI.Playbook.Loki.GauntletsOfUltramarPlaybook$$.cctor ; le compte total = `Enemies(Entity(unit), AllAliveMachines@+0x80, 2)`
      board-WIDE. => Gauntlets ne caste QUE si son compte atteint `min(3, #ennemis restants)`.
    - IdunBattle.AI.Playbook.Loki.GauntletsOfUltramarPlaybook$$.ctor = `NonComparablePlaybook(1000)` : 1er arg = ABILITY_ID (PAS priorité) ; aucun
      `get_Priority` override -> PRIORITY=0 (défaut `AbilityPriority.Normal` ; 1000 est hors
      `NATIVE_PRIORITY`, sweep exhaustif #170 — le ctor ne porte JAMAIS la priorité, seul un override
      du getter la change).
    - POSITION (#117) : sweep ORIGINE D'ABORD (`_sweep_origin_first`) + remplacement STRICT `>`
      (Bucket.AddAction keep-first IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction, NullPosition toujours évaluée) => à ÉGALITÉ d'arc le caster
      CASTE EN PLACE (origine), ne BOUGE que sur gain STRICT. Mirror #76/#80. VALIDÉ LIVE (natif (3,5)=(4,5)
      arc 5 -> caste @origine (3,5), pas le move tile).
    - CIBLE EXACTE (#117) : le natif boucle sur `GetEligibleTargetsSelectable(caster, MainTile)` et
      `GenerateAction(position, eligible_target, Fix64(count))` (local_1a8 = eligible target, un ENNEMI ;
      1 action/eligible target, MÊME utilité -> bucket keep-first). L'énumération est INVERSÉE
      (`DSLFactory.Tiles`=`SortReverseSelector IdunBattleLogic.Entities.DSLSelectors$$Tiles`) => cible = 1er ennemi ring-1 dans l'ordre
      `boardGraph.neighbours` (GetAdjacentTiles natif) **INVERSÉ**, sinon ring-2 (`bq.gauntlets_target`).
      VALIDÉ LIVE BIT-EXACT (#117 : natif tgt=118 = ultraCalgar @(3,5) ring-1 [80,114,78,118]_fwd inversé).
      PAS la MainTile ni None.
    VALIDATION case-49x (probe_49x_realanchor.py, 2026-07-21, session 58) : craft-P MC1_67 plat
    (non-vide EXACTEMENT à (5,8) util=3 = 1 ring1(T) + 2 disque-réel — les règles rivales ring-1-seul
    et arc(T) prédisaient vide) ; craft-N plat (vide partout — arc(T) prédisait 3 à (1,7) ; sur plat,
    aucune échappatoire « obscured ») ; E1-repro C1_25 (23/23 : 17 positions util=2, 6 vides = gate
    d'éligibilité).
    v1 FLAGS (résiduels) : ordre EXACT ring-2 de la cible (fallback dernier) ; Unobscured de
    l'ÉLIGIBILITÉ (arc de T) passe-tout ; murs non modélisés dans `is_target_tile_obscured`."""
    ABILITY_ID = int(ActiveAbilityType.GauntletsOfUltramar)  # 1000
    MIN_UTILITY = 1.0     # plancher structurel (>=1 ennemi éligible) ; vrai gate = min(3, #ennemis totaux)
    PRIORITY = 0
    _FLOOR_CONST = 3      # const Fix64(3) du IdunBattle.AI.Playbook.Loki.GauntletsOfUltramarPlaybook$$.cctor (seed bucket) — PAS un cap d'utilité (case-49)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        floor = min(self._FLOOR_CONST, len(ctx.epos or []))   # Min(3, #ennemis TOTAUX) = seed du bucket natif
        # Terme « surrounding » ANCRÉ À LA POSITION RÉELLE (T-indépendant, calculé UNE fois) :
        # Unobscured(SurroundingEnemies(Caster ENTITÉ, r=2)) — cf. bq.surrounding_enemies (case-49x).
        surround_real = bq.surrounding_enemies(ctx.origin, ctx.epos, ctx.elev_by_pos)
        best_t, best_u = None, None
        # ORIGINE D'ABORD + remplacement STRICT `>` (Bucket.AddAction keep-first IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction, NullPosition
        # toujours evaluee) -> le caster CASTE EN PLACE a egalite, ne BOUGE que sur gain STRICT
        # (#117 : natif (3,5)=(4,5) arc 5 -> caste @origine (3,5)). Mirror #76/#80.
        for T in _sweep_origin_first(ctx):
            # GATE éligibilité : sans cible à dist<=2 de T (SANS porte d'élévation — prouvé live
            # (0,2) E1-repro), AUCUNE action générée à T (GetEligibleTargetsSelectable(unit, T)
            # vide -> boucle GenerateAction jamais entrée).
            if bq.eligible_targets_count(T, ctx.epos, ctx.elev_by_pos) == 0:
                continue
            ring1 = {(p[0], p[1]) for p in (ctx.epos or [])
                     if bq.is_adjacent(T, p, ctx.elev_by_pos, bq.neigh_map(ctx))}
            u_ = float(len(ring1 | surround_real))            # SelectUniqueUnits : union dédupliquée
            if best_u is None or u_ > best_u:    # strict > : origine gagne le tie (elle est en tete)
                best_t, best_u = T, u_
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] Gauntlets floor(min3,total)={floor} "
                  f"surround_real={sorted(surround_real)} best={best_t} u={best_u}",
                  file=sys.stderr)
        if best_u is None or best_u < max(self.MIN_UTILITY, float(floor)):   # bucket gate: util >= Min(3,total)
            return []
        # CIBLE = eligible target EXACT du natif (GenerateAction(pos, eligible_target, util) IdunBattle.AI.Playbook.Loki.GauntletsOfUltramarPlaybook$$EvaluateNonComparable) =
        # 1er ennemi ring-1 dans l'ordre voisins natif INVERSÉ (SortReverse + bucket keep-first), sinon
        # ring-2. VALIDÉ LIVE #117 (natif tgt=118). Fallback ordre-arc si neigh_by_pos absent (offline pur).
        target = bq.gauntlets_target(best_t, ctx.enemies, ctx.neigh_by_pos, ctx.elev_by_pos)
        return [{"target": target, "ability": self.ABILITY_ID,
                 "to": (best_t if best_t != ctx.origin else None), "pred": best_u}]
