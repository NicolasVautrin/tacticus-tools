# Case #49 — Gauntlets(1000) overfire 31337 s14 + RE complet de la chaîne « Unobscured »

**Symptôme** : 31337 s14, u87 (ultraCalgar @(2,2)) — natif joue move (3,4) + attaque normale
69→81 ; notre moteur émet 1000→79 depuis (5,4). Seul miss ability du batch (34/35).

## ⚡⚡ RÉSOLUTION FINALE (2026-07-21, case-49x / tâche #10) — la règle « ring-1 seul » était un OVERFIT

**La vraie utilité Gauntlets a DEUX ANCRAGES différents** (décompilé `EvaluateNonComparable
@18113e5a0` + `GetAdjacentTargetsSelector @1811e2010` + `GetSurroundingTargetsSelector @1811e20d0`,
prouvé live par 4 crafts + repro E1, probe committée `probe_49x_realanchor.py`) :

```
util(T) = | ring1(T)  UNION  Unobscured(disque r<=2 de la TUILE RÉELLE du caster) |
bucket(T) non-vide  <=>  util(T) >= min(3, #ennemis vivants)  ET  eligible(T) != vide
eligible(T) = ennemis à dist <= 2 de T (SANS porte d'élévation au ring-1)
```

- **ring-1 = ancré à la position BALAYÉE T** : `AdjacentTiles(CasterTile@+0x168)` — `CasterTileSelector
  .Select @180ee49b0` lit la tuile du CONTEXTE `AbilityEntities` (= `MainTile(position)` passée par
  EvaluateNonComparable). Porte élévation |Δelev|<2 (IterateAdjacentTiles).
- **surrounding = ancré à la position RÉELLE de l'ENTITÉ** : `SurroundingEnemies(Caster@+0x160, r=2)`
  — `CasterSelector.Select @180ee47d0` rend l'ENTITÉ ; `SurroundingTilesSelector.Select @180ef6100`
  prend `GetMainTile(entité)` = la tuile réelle dans l'état ECS, PAS celle du contexte. Cube-loop
  disque dist<=2 (pas le ring exact), **tuiles occupées INCLUSES** (flag requireEmptyOrSteppable=0
  au call-site, ctor @180ef65c0), filtre `TileUtil.IsTileValidForList(tile,src,1,0) @1810c0660` =
  non-mur + walkable SANS élévation ni occupation, `Unobscured` depuis la tuile réelle
  (élévation : `MovementQuery.GetTilesObscuringTerrain @18109bad0`, dist-1 jamais obscurci).
- **Gate d'éligibilité par-position** : le natif boucle `GetEligibleTargetsSelectable(caster,
  MainTile(T)) @18111ed80` — set ancré à T ; vide => AUCUNE action générée à T même si util >= floor
  (prouvé 23/23 positions E1-repro C1_25, dont (0,2) : ennemi adjacent |Δelev|=2 QUAND MÊME éligible
  => pas de porte d'élévation dans l'éligibilité).

**Pourquoi le flip-flop** : chaque mesure antérieure ne voyait qu'UN régime. Quand disque(réel)=∅
(s14 : ennemis à dist 3-5 de la tuile réelle (2,2)) la règle dégénère en « ring-1 seul » (fix
2026-07-20, batch 35/35 — vrai sur CE board) ; quand réel==balayé (E1 validator C1_25 : caster
immobile) elle dégénère en « arc(T) » (port d'origine). Les deux « validations » étaient des
projections d'une même règle à deux ancrages — cf. l'entrée #49x de `docs/rl/solving-playbook.md`.

**Fix final** : `gauntlets_of_ultramar.py` (util = union deux-ancrages + gate éligibilité) +
`battle_query.py` (`surrounding_enemies`, `eligible_targets_count`, `is_target_tile_obscured`).
**Validation** : batch 3 seeds préd 26/26 · util 26/26 · **ability 35/35** · move 48/51 (3 misses
= pos-downstream-of-ability, tâche #32) ; crafts discriminants NOUVEAUX tous PASS position-par-
position (probe_49x) : craft-P (zone PLATE MC1_67 : disque-réel compte -> non-vide EXACTEMENT à
(5,8) util 3 quand ring-1-seul ET arc(T) prédisaient vide), craft-N (plat : dist-2-de-T ne compte
PAS -> vide partout quand arc(T) prédisait 3), craft-O (ennemi dist-2 du réel DERRIÈRE crête elev 4
-> EXCLU : vide partout ; valide le prédicat obscured positivement), craft-O2 (même layout, ennemi
déplacé visible -> non-vide (5,2)=3 : contrôle), E1-repro (23/23 : 17 positions util=2 uniformes =
signature de l'ancre réelle, 6 vides = gate d'éligibilité).

**⚠ Sections historiques ci-dessous** : la résolution 2026-07-20 et §1/§2bis sont CONSERVÉES comme
trace mais **partiellement FALSIFIÉES** — annotations inline. Ne pas réutiliser §2bis.

## ~~⚡ RÉSOLUTION (2026-07-20)~~ [DÉPASSÉE par case-49x — overfit board-dépendant]

**Utilité Gauntlets = compte d'ennemis RING-1 (adjacents) SEUL, NON cappé ; admission bucket
`>=` (loose).** [FALSIFIÉ 2026-07-21 : vrai seulement quand disque(réel)=∅ — cf. résolution finale.]
Fix : `gauntlets_of_ultramar.py` → `bq.count_adjacent` (ring-1, élévation-gatée, non cappée),
`_CAP` renommé `_FLOOR_CONST` (le « 3 » de SelectUniqueUnits = UnitSelectionType, PAS un cap)
[toujours VRAI]. Batch 3 seeds post-fix : préd 26/26, util 26/26, ability 34/35, move 47/51 —
zéro régression, s14 n'émet PLUS 1000 (le moteur attaque normale comme le natif).

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
49e (plan énuméré), 49f (sweep debug), 49g (L3 par-feuille tuiles), **49x (discriminateur
final ancre-réelle : crafts P/N/O/O2 + E1-repro — cf. Résolution finale)**.

## 1. Hypothèses RÉFUTÉES [⚠ annoté case-49x : les MESURES restent bonnes, deux INTERPRÉTATIONS étaient fausses]

- **Unobscured ring-2 (hypothèse initiale de la tâche #8) — RÉFUTÉE** *sur CE cas* (re-expert
  2026-07-20). [Case-49x : l'analyse de visibilité ci-dessous est CORRECTE mais hors-sujet — le
  terme surrounding natif est ancré à la tuile RÉELLE (2,2), pas à la balayée (5,4) ; les ennemis
  étaient à dist 3-5 du réel, d'où le vide. Le prédicat Unobscured existe bel et bien et a depuis
  été validé live (craft-O/O2 probe_49x : crête elev 4 -> ennemi dist-2 du réel EXCLU).]
  Élévations réelles MC1_67 : (5,4)=3, (6,5)=2, (4,4)=2, (3,5)=2, (6,4)=3, (5,5)=2.
  Prédicat natif fidèle exécuté offline : `(5,4)→(3,5)` VISIBLE (mid (4,4) elev 2, deltas < 2) ;
  `(5,4)→(6,5)` VISIBLE (fat-line {(6,4)=3,(5,5)=2} vs elev(to)=2 : il faudrait LES DEUX ≥ 4).
  Contrôle synthétique positif (mid forcé à 5 → OBSCURED) : le prédicat se déclenche bien.
  **Arc natif à (5,4) = 3 = notre `count_enemies_in_arc`** — un port Unobscured ne change RIEN
  à ce cas. MC1_67 n'a aucun mur. Le set ring-2 est géométrique (slot 0x65 =
  `IdunBattle.Core.Services.BattleQuery$$GetSurroundingTiles`, le « surrounding » natif ; le
  filtre « distance hex == R » est celui de
  `IdunBattle.Core.Services.BattleQuery$$GetTilesAtDistance`) ; PAS un BFS mouvement
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

## ~~2bis. MÉCANISME FINAL — le terme ring-2 rend TOUJOURS 0~~ [**FAUX** — falsifié case-49x, NE PAS RÉUTILISER]

[La chaîne de sélecteurs listée ici (VAs) est correcte, mais la conclusion était FAUSSE :]

~~**`SurroundingTiles` est la primitive de portée type MOUVEMENT/PLACEMENT : elle ne rend que
des tuiles vides (ou steppables) — JAMAIS la tuile occupée par un ennemi normal.»**~~
**FALSIFIÉ (case-49x, décompilé + live E1/C1_25 + craft-P)** : la lecture « empty-only » avait
confondu flag=0 avec filtre actif. Le décompilé de `TileQuery.<IterateSurroundingTiles>d__6
.MoveNext @1810ae1b0` montre que le filtre `IsEmptyOrSteppable` est CONDITIONNEL au flag
requireEmptyOrSteppable — et le call-site Gauntlets passe **0 (OFF)** (`SurroundingTiles(query,
caster, 1, r=2, 0, 0)` -> ctor @180ef65c0 -> slot 0x65 args `(tile, r, 0, 1, 0, 1)`). Les tuiles
occupées PASSENT ; le seul filtre par-tuile restant = `TileUtil.IsTileValidForList @1810c0660`
(non-mur + walkable, sans élévation ni occupation). Le vrai mécanisme du vide s14/49b/49c :
**l'ancrage à la tuile RÉELLE** (cf. Résolution finale en tête) — les ennemis étaient à dist 3-5
de (2,2). La « grille complète satisfaite » ci-dessus était une coïncidence de configs où
disque(réel)=∅ : c'est le piège de la sous-détermination (plusieurs règles compatibles avec les
mêmes mesures tant qu'on ne CRAFTE pas le cas qui les sépare — fait par probe_49x craft-P/N).

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

### Spec de port — PORTÉ (case-49x) pour le cas dist-2 : `bq.is_target_tile_obscured`

Port dist-2 (le seul cas exercé par le playbook NC Gauntlets) dans `engine/battle_query.py`
(`is_target_tile_obscured`, consommé par `surrounding_enemies`) : mids = voisins communs
hexgeo (dist-2 : trajet droit -> 1 mid ; diagonal -> midpoint exactement sur l'arête -> les
lignes A/B ±eps départagent les 2 candidates -> fat-line = ET) ; bit 2 : bloque si
`elev(mid) − elev(from) >= 2` OU `elev(mid) − elev(to) >= 2` (fat : ET des 2 candidates par
réf). **VALIDÉ LIVE positif+négatif** (probe_49x craft-O/O2 : (2,2)->(1,4) mids (1,3)/(2,3)
elev 4 -> EXCLU ; (2,2)->(3,3) visible -> compté). RESTE v1 : murs (bit 4, `wall_by_pos` À
PLUMBER — aucun board d'agreement n'a de mur en zone jouable) ; mask 4 IndirectFire (aucun
caster NC concerné) ; dist >= 3 (hors périmètre Gauntlets) ; nudge eps exact (FloatCube
readonly @DAT_1832593f8+0xb8, non lu statiquement) supposé départager les candidates du cas
diagonal — si A/B tombaient sur la MÊME candidate, le natif bloquerait sur elle seule.
