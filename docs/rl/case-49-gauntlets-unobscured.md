# Case #49 — Gauntlets(1000) overfire 31337 s14 + RE complet de la chaîne « Unobscured »

**Symptôme** : 31337 s14, u87 (ultraCalgar @(2,2)) — natif joue move (3,4) + attaque normale
69→81 ; notre moteur émet 1000→79 depuis (5,4). Seul miss ability du batch (34/35).

## ⚡ RÉSOLUTION (2026-07-20) — overfire CORRIGÉ ; mécanisme prouvé décompilé + live

**Utilité Gauntlets = compte d'ennemis RING-1 (adjacents) SEUL, NON cappé ; admission bucket
`>=` (loose).** Trois hypothèses réfutées en cascade (§1), mécanisme final prouvé (§2bis).
Fix : `gauntlets_of_ultramar.py` → `bq.count_adjacent` (ring-1, élévation-gatée, non cappée),
`_CAP` renommé `_FLOOR_CONST` (le « 3 » de SelectUniqueUnits = UnitSelectionType, PAS un cap).
Batch 3 seeds post-fix : préd 26/26, util 26/26, ability 34/35, move 47/51 — zéro régression,
s14 n'émet PLUS 1000 (le moteur attaque normale comme le natif).

**Miss résiduel s14 (cible 79 vs 81) — RÉSOLU en deux couches supplémentaires** :
1. **`RitesOfBattlePlaybook` porté** (famille AdjacentUnitPreference, case-36) : ctor
   @181187dd0 = `AdjacentToOwnerNonOwnerPlaybook(0x3f6=1014)`, `GetAdjacentFriendUtility
   @181187d70` = TriggeredAbilities["RITESOFBATTLE_AdjacentFriend"] (=10 BC). Ferme le miss
   move-formula s3 (u87, L3 suspect direct).
2. **`tile_utility` (chemin ATTAQUE) alignait PAS le leaf_ctx** : `playbook/base.py` passait
   `leaf_ctx={}` à `tile_composite` → la feuille TriggeredAbilities(2) face MOVE (kit + fpos)
   était MUETTE dans le terme Tile(7) du sweep d'attaque, alors que le natif émet **LA MÊME
   `ComposedUtility`** sous le playbook d'attaque (preuve L3 probe 49g, s14 : parent
   `ComposedUtility#179`, playbook `Loki_NormalAttackPlaybook` ; (3,4)=25 = 30 élév − 25
   TileEffects + **20 TrigAb** ; (4,3)=40 = 30 + **10 TrigAb**). Natif full : 28.86+25=53.86
   > 12.51+40=52.51 → 81 gagne de 1.35. Notre Tile7 (5.0/30.0, TrigAb=0/0) flippait l'argmax.
   Fix : `tile_utility` construit meta (élévation board, effets dynamiques + covers terrain)
   et `leaf_ctx = tile_leaf_ctx(ctx)` en MIRROIR de `engine.move` ; `tile_leaf_ctx` déplacé
   dans `engine/utilities/tile.py` (consommé par les DEUX chemins ; ctx polymorphe
   AiDecisionContext/NCContext toléré).

**BATCH FINAL 3 seeds (777/909/31337)** : prédiction 26/26 (100 %), utilité 26/26 (100 %),
**ability 35/35 (100 % — ÉTAGE FERMÉ)**, move 48/51 (94 % — plus AUCUN move-formula, les 3
restants = pos-downstream-of-ability : s5/s15 31337 + 1). Chaîne des probes conservée :
probe_49_gauntlets (dispo ability), 49b/49c (falsification ring-2), 49d (paires natives),
49e (plan énuméré), 49f (sweep debug), 49g (L3 par-feuille tuiles).

## 1. Hypothèses RÉFUTÉES (ne pas re-suspecter)

- **Unobscured ring-2 (hypothèse initiale de la tâche #8) — RÉFUTÉE** (re-expert 2026-07-20).
  Élévations réelles MC1_67 : (5,4)=3, (6,5)=2, (4,4)=2, (3,5)=2, (6,4)=3, (5,5)=2.
  Prédicat natif fidèle exécuté offline : `(5,4)→(3,5)` VISIBLE (mid (4,4) elev 2, deltas < 2) ;
  `(5,4)→(6,5)` VISIBLE (fat-line {(6,4)=3,(5,5)=2} vs elev(to)=2 : il faudrait LES DEUX ≥ 4).
  Contrôle synthétique positif (mid forcé à 5 → OBSCURED) : le prédicat se déclenche bien.
  **Arc natif à (5,4) = 3 = notre `count_enemies_in_arc`** — un port Unobscured ne change RIEN
  à ce cas. MC1_67 n'a aucun mur. Le set ring-2 est géométrique (slot 0x65 « surrounding »,
  `BattleQuery.GetTilesAtDistance @181069760` filtre distance hex == R), PAS un BFS mouvement
  (slot 0xc) → 81 est bien dans le set.
- **Cooldown / munitions / effet bloquant — RÉFUTÉE** (probe live `probe_49_gauntlets.py`,
  walk 31337 → s14) : dv u87 abilities → `{id:1000, usable:true, cooldown:null, disabled:false,
  ammoCost:null, hasAmmo:true, level:50, multiplier:180}` ; effets actifs = RitesOfBattle_
  ExtraDmgBasic/Imperial + CrushingStrike (aucun `_CantUseAbility`). L'ability est DISPONIBLE.
- Rappel (investigation tâche #8, live 2026-07-20) : les gates du générateur passent
  (ShouldEvaluate slot 4 = base @18111fb70 ; GetUseProbability = Fix64(1)) et pourtant
  **ncEvaluate(u87, 1000) → bucket VIDE sur les 25 positions balayées**.

## 2. Verdicts décompilé (re-expert, 2ᵉ/3ᵉ passes) + probes live 49b/49c

- **(a) Utilité NON cappée** : `util = SelectUniqueUnits(GetAllTargetsSelector, query,
  3).get_Count()` ; `SelectUniqueUnits @1810108b0` itère SANS limite de compte, le « 3 » =
  **UnitSelectionType** passé à `SelectUnit @181010de0` → `MatchesUnitSelectionType(unit, 3)`
  (filtre PAR-unité). Notre ancien `_CAP=3` était une fausse hypothèse.
- **(b) Admission = `>=` (LOOSE)** : `Bucket.AddAction @1813fbcc0` → porte `@18004cc80` =
  `op_GreaterThanOrEqual(action.utility, seed)`. Le `op_GreaterThan` STRICT ne sert qu'au
  remplacement ENTRE actions admises (keep-first #117). Seed = `Min(Fix64(3) [cctor
  @18113ed50], EnemiesBoardWide.Count [slot 0x18])`. Mon hypothèse « strict > » : RÉFUTÉE.
  CONFIRMÉ LIVE (49c config A) : 3 ennemis déplacés sur les voisins de (5,4) → bucket
  non-vide à (5,4) EXACTEMENT, **util=3 == seed 3 ADMIS**.
- **(c) Hypothèse « occupancy-BFS ring-2 » (3ᵉ suspect) : RÉFUTÉE LIVE** (probe 49b : u79
  déplacé hors (4,4) → chemin 2-pas libre vers u81 → bucket TOUJOURS vide ; 49c config B :
  2 adjacents + 1 ennemi dist-2 chemin libre → vide).

## 2bis. MÉCANISME FINAL (prouvé structurellement) — le terme ring-2 rend TOUJOURS 0

Chaîne : `GetSurroundingTargetsSelector @1811e20d0` = `Unobscured(SurroundingEnemies(caster,
r=2) − AdjacentTargets)` ; `SurroundingEnemies @180dfc570` = `Enemies(Units(SurroundingTiles(
caster, r=2) − Tiles(caster)))` avec `Units @180e01340` → `UnitsOnTilesSelector.Select
@180f02450` (mappe tuile → unité qui l'OCCUPE) et `SurroundingTiles @180dfca70` →
`SurroundingTilesSelector.Select @180ef6100` (portée slot 0x65 du board-query, args Gauntlets
radius=2, flag1=0, flag2=0 via ctor @180ef65c0).

**`SurroundingTiles` est la primitive de portée type MOUVEMENT/PLACEMENT : elle ne rend que
des tuiles vides (ou steppables) — JAMAIS la tuile occupée par un ennemi normal.** Donc
`Units(...)` n'y trouve aucune unité → le terme ring-2 = ∅ STRUCTURELLEMENT (peu importe
distance/visibilité/chemin). Ring-1 (`AdjacentTiles`→`IterateAdjacentTiles`) n'a PAS ce
filtre (inclut les tuiles occupées, porte |Δelev|<2 seule) → seuls les ADJACENTS comptent.
Grille complète satisfaite : #117 (≥4 ring-1 → caste), s14 (ring-1 1 → vide), 49b (<3 →
vide), 49c B (2 → vide), 49c A (3 → non-vide util=3).

**Résidu ouvert (edge case, flaggé)** : le prédicat exact du slot 0x65 (empty-only vs
empty-OR-steppable, flag-dépendant ou systématique) est enfoui sous 3 couches de dispatch
d'interface. Test falsifiable si besoin : ennemi STEPPABLE (spore mine) à dist 2 chemin
libre → compté = « empty-or-steppable », pas compté = « empty-only ». Aucun seed
d'agreement n'exerce ce cas.

**Corollaire multi-abilities** : `SurroundingEnemies` (4 surcharges, refcount ~40) est
potentiellement inerte PARTOUT où il compte des ennemis normaux à portée ≥2 (quirk natif) ;
`SurroundingTiles` direct (enrobe des TUILES, refcount 58) reste pleinement vivant
(AoE/placement). À garder en tête pour tout futur port d'ability « surrounding ».

## 3. RE complet « Unobscured » (VÉRITÉ décompilé — levier 12 abilities, port futur)

Chaîne (build gqfc5mff6c) :
- `DSLFactory.Unobscured @180e01540` → `UnobscuredEntitiesSelector` (classe DAT_1831d2f10 ;
  ctor de base gshared étiqueté `CanAddUnitTileSelector..ctor @180ee46a0` — pas un vrai lien).
  `Select @180f06d30` : garde les candidats dont `IsObscured == 0` (slot 7 itf DAT_1831e6ed8,
  impl `TargetingQuery`).
- `TargetingQuery.IsTargetUnitObscured @1810bf680` : itère les tiles de la cible
  (multi-tile : unité obscurcie ⟺ **TOUTES** ses tiles obscurcies ; visible dès qu'UNE l'est).
- `TargetingQuery.IsTargetTileObscured @1810bf5a0` : slot 0x10 de l'itf board-query
  (DAT_1831ce2f0) sur this+0x20, args `(fromTile, toTile, mask, 2)`, Count>0 ⇒ obscuré.
  **mask = (flag^1)*2 + 4** avec `flag = HasTrait(caster, 0x3ed=1005=IndirectFire)` :
  IndirectFire ⇒ 4 (murs seuls, ignore l'élévation) ; sinon **6** (élévation bit 2 + murs
  bit 4). (`UnobscuredTilesSelector.IsObscured @180f071e0` hardcode 6.) Corrobore
  targeting-rule-names.ts : 24=TargetIsUnobscured, 25=AllowObscuredTargetByElevation,
  26=AllowObscuredTargetByWalls.
- Slot 0x10 = **`MovementQuery.GetTilesObscuringTerrain @18109bad0` — TERRAIN UNIQUEMENT,
  AUCUN blocage par unité.**
  - Ligne : `GetLinesBetweenTiles @181099cb0` → `DrawLineBetweenCoordinates @18109ded0`
    DEUX FOIS : A=(from→to, +eps), B=(to→from, −eps). Line-draw cube classique
    (`t=i/dist`, Lerp FloatCube, nudge ±eps, `RoundFloatCubeCoordinates @18109e590`),
    endpoints inclus (dist+1 tiles). Nos primitives hexgeo sont **bit-exactes** avec la
    math native (`AxialCoordinate.ToCubeCoordinate @180e2c320` = `to_cube` ;
    `RoundFloatCubeCoordinates` = `_cube_round` ; `CubeCoordinate.Distance @180e30720`
    = `distance`).
  - Élévation (bit 2) — `DetermineBlockingTiles @18109d090`, seuil param 2 : teste
    UNIQUEMENT idx=1 (adjacente au from, vs elev(from)) et idx=count−2 (adjacente au to,
    vs elev(to)). Bloque si `elev(tile) − elevRef >= 2`. Fat-line (A[idx] ≠ B[idx]) :
    les DEUX candidates doivent être hautes.
  - Murs (bit 4) — `DetermineBlockingWalls @18109d2a0` : toute la ligne ; bloque si
    A[idx] ET B[idx] sont murs (`TileComponent+0x41 isWall` ; elev = `+0x18`).
  - **Distance 1 : jamais obscurci** (count 2 → ni élévation ni murs testables) — le
    filtre ne mord qu'à dist ≥ 2, aucun gate d'adjacence à ajouter.
- **Consommateurs `DSLFactory.Unobscured` (21 refs → 12 abilities)** : Boltstorm, LightImUp,
  ParagonSpear, Doombolt, HarbingerOfDestruction, DakkaDakkaDakka, HeroicFusillade,
  KillMaimBurn, MultiThreatEliminator, TheWailingDoomSweeps, GauntletsOfUltramar,
  SanctorumMissile.

### Spec de port (si/quand implémenté — PAS pour #49)

`engine/battle_query.py`, ring-2 de `in_arc` : `distance==2 and not is_tile_obscured(...)`.
mask = 4 si caster IndirectFire sinon 6 ; ligne A/B avec nudge ±eps (epsilon exact natif =
FloatCube readonly @DAT_1832593f8+0xb8, non lu statiquement — le nudge asymétrique
`(1,2,-3)e-6` du script de vérif reproduit le comportement, à valider live sur high-ground) ;
bit 2 sur idx∈{1, count−2} vs elev(from/to), seuil >= 2, fat-line = ET des deux candidates ;
bit 4 murs sur toute la ligne (A ET B). Données offline : `elev_by_pos` (présent) +
`wall_by_pos` (À PLUMBER — aucun board d'agreement actuel n'a de mur). Script de référence :
scratchpad re-expert `obscure_check.py` (perdu au cleanup worktree — re-dériver de ce doc).
