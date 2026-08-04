# #433-r4-r2-r1-r2 — le SECOND prédicat de `GetPossibleTargetsForOptions` : la LIGNE DE VUE

**Verdict : FERMÉ.** Le prédicat est porté, et le masque le prédit — la contre-épreuve offline
sépare sans une seule réfutation les **douze** abilities déjà mesurées, et quatre confrontations
live neuves (deux boards, trois volets) rendent la partition **EXACTE dans les deux sens**.

Deux résultats de méthode valent autant que le port lui-même : l'étage n'est **gaté par aucun bit**
(contrairement au troisième, ce qui expliquait l'énigme laissée par #568), et il lit une **troisième
géométrie** — ni le `ConnectivityComponent`, ni le champ `neighbours` du `boardGraph`.

## 1. La chaîne, LUE

```
TargetingQuery$$GetPossibleTargetsForOptions(caster, casterTiles, options, range, onlyTiles)
    ...
    RemoveAll(b__0)                                   # ami/ennemi, portée, règles statiques
    RemoveAll(b__1)                                   # <-- CE CAS, SANS AUCUNE GARDE
    if (rules & TargetMatchesDynamicRule) RemoveAll(b__2)      # le gate dynamique (#558)
```

⚠ **`b__1` tourne TOUJOURS.** Les deux bits `AllowObscuredTargetByElevation` (25) / `ByWalls` (26)
ne décident pas *si* il tourne, mais *ce qu'il regarde* — ils sont consommés **à l'intérieur** de
`TargetingQuery$$GetTilesObscuringTerrain`. C'est ce qui résout l'énigme de #568 : `1161
TwinSmartMissileSystem` n'a pas le bit `TargetMatchesDynamicRule` (donc le 3ᵉ prédicat n'est même
pas construit) et montrait pourtant les mêmes 5 refus.

```
TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__1(target)
    if (UnitExtensions.IsFriend(target, ctx.caster, ctx.query.state)) return false;      # GARDE
    return ctx.query.GetTilesObscuringTerrain(caster, casterTiles, target, options).Count > 0;

TargetingQuery$$GetTilesObscuringTerrain(caster, casterTiles, target, options)
    if (!this.<config @+0x30>.<+0x10>)                                    return empty;
    if (UnitExtensions.IsFriendOrHasFriendlyUnitOnIt(target, caster, state)) return empty;
    flags = 0;
    if (!UnitExtensions.HasTrait(caster, 0x3ed)              // IndirectFire
        && (options.Rules & 0x2000000) == 0)  flags = 2;     // AllowObscuredTargetByElevation
    r = flags | 4;                                           // Wall
    if ((options.Rules & 0x4000000) != 0)     r = flags;     // AllowObscuredTargetByWalls
    if (r == 0)                                                           return empty;
    return this.<movement @+0x20>.<slot 0xf>(casterTiles, target, r, 2);
```

Les champs viennent de `TargetingQuery$$Init(this, attackQuery, battleQuery, movementQuery, state,
config)` : `+0x10 attack`, `+0x18 battle`, `+0x20 movement`, `+0x28 state`, `+0x30 config`. Le
drapeau `config+0x10` est **`BC.Targeting.EnableObscuringTerrain`**, présent dans la BC et à `True`
sur le seed courant ; il est PARAMÈTRE du port, jamais codé en dur.

**Trois lectures qui ne se devinent pas :**

* le trait `0x3ed` = **1005 `IndirectFire`** (qualifié contre l'enum `IdunBattle.Entities.Enum.UnitTrait`).
  Il n'exempte **que** l'élévation — `r = flags | 4` garde les murs. Le rabattre sur « aucune
  obstruction » supprimerait tout le volet MURS pour ses porteurs ;
* les deux volets sont **INDÉPENDANTS**. `r == 0` exige les DEUX bits ;
* le `2` littéral du call-site est le `blockingElevationDifference`, et `r` un
  `idun.meta.ObscuringType` (`None=0, Elevation=2, Wall=4, All=6`).

## 2. La GÉOMÉTRIE — la question était piégée, et la réponse est « ni l'une ni l'autre »

`MovementQuery$$GetTilesObscuringTerrain` n'interroge **NI** le `ConnectivityComponent`, **NI** le
champ `neighbours` du `boardGraph` (celui que la porte `|srcElev - Elevation| < 2` de
`TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` ampute de 18 arêtes sur `MC1_67`). Il
**TRACE deux lignes de COORDONNÉES** puis interroge chacune par
`IdunBattle.Entities.StateExtensions$$GetTileAt`. **Aucune ARÊTE n'est lue** — seulement des
coordonnées, l'élévation de la tuile qui s'y trouve, et son drapeau `IsWall`. Le graphe d'adjacence
est donc hors sujet ici, dans ses deux versions.

```
GetLinesBetweenTiles -> MovementUtil$$DrawLineBetweenCoordinates(line, from, to, nudge)
    axial -> cube (AxialCoordinate$$ToCubeCoordinate : x = col, z = row - (col + (col&1))/2)
    N = CubeCoordinate.Distance ; pour i dans 0..N :
        p = Lerp(a, b, Fix64(1)/Fix64(N)*Fix64(i))  ;  p = (nudge == 1) ? p - EPS : p + EPS
        line.Add(MovementUtil$$RoundFloatCubeCoordinates(p))   -> cube -> axial
```

`EPS` est écrit par `MovementUtil$$.cctor` : `FloatCubeCoordinate(1e-6, 2e-6, -3e-6)` — la valeur
canonique « Red Blob », quatre ordres de grandeur au-dessus de la résolution `Fix64` (2⁻³²), donc
un port en float64 rend les mêmes tuiles. Les deux signes donnent les deux candidates du trajet
« diagonal ».

**Ce que le port ne pouvait pas deviner, et qui est le cœur du prédicat :**

* `FirstOrFallbackIfOutsidePlayableArea` : une ligne dont **une seule** coordonnée sort du
  rectangle (`BoardComponent$$IsPositionInside` = `0 <= row < Height && 0 <= col < Width`) est
  REMPLACÉE par l'autre. Appelé deux fois, en cascade ;
* **ÉLÉVATION : seulement DEUX positions de la ligne sont testées**, l'indice `1` (contre
  l'élévation du DÉPART) et l'indice `Count - 2` (contre celle de l'ARRIVÉE). Une tuile haute au
  MILIEU d'une longue ligne ne bloque rien. Un modèle « une tuile haute quelque part sur la ligne »
  serait faux — et c'est exactement ce qu'on aurait inventé ;
* le seuil est **SIGNÉ et à sens unique** : `elev(mid) - elevRef >= 2`. Une tuile plus BASSE
  n'obscurcit jamais ;
* **FAT-LINE** : quand les deux lignes diffèrent à cet indice, il faut que **les DEUX** candidates
  passent le seuil (`blkA && blkB`) ; quand elles coïncident, une seule suffit ;
* **MURS : toute la ligne, bornes comprises** — contraste total avec l'élévation ;
* **distance 1 : JAMAIS obscurci** (`2 < lineA.Count` est faux), pas même par un mur. Structurel ;
* caster MULTI-PIEDS : la surcharge LISTE **intersecte** les ensembles par pied.

Ce dernier étage était **déjà porté** (`engine.services.movement_query`, #444). Il a été
re-dérivé du décompilé indépendamment pour ce cas et **il concorde** ; aucun second corps n'a été
écrit.

## 3. La contre-épreuve OFFLINE — le masque prédit toutes les mesures du dossier

`probe_433_r4_r2_r1_r2_line_of_sight.py --step read` confronte `obscuring_type_for(rules)` aux
**douze** abilities déjà mesurées live (#568 + #558), sans monter un runner. C'est falsifiable :
une seule à `r == 0` mesurée en dessous de 40/40, ou une seule à `r == 6` mesurée sans écart, le
réfute.

| `ObscuringType` prédit | abilities | mesure live du natif |
|---|---|---|
| **0** | `1025 SkyStrike`, `1140 ExemplarOfHate`, `1145 SporeMineLauncher`, `1147 HadesAutocannons`, `1201 SquigMine` | **40/40**, port déjà EXACT |
| **6** | `1011 TunnelingHorror`, `1161 TwinSmartMissileSystem` | 35/40, port **5 FP** |
| **6** | `1168 EntropyCannons`, `1200 SquigLaunchas`, `1213 DeathOnTheWind` | 34/40, port **6 FP** (5 + la tuile occupée) |
| — | `1100 SorcerousFacade`, `1143 ForwardSpotter` | zone VIDE en amont, non discriminantes |

**Zéro réfutation.** `1153 HammerOfWrath` (`AllowObscuredTargetByElevation` seul → `r = 4`) est
cohérente : aucun mur sur ses lignes.

## 4. Ce qui est porté

* **`engine/services/targeting_query.py`** (neuf) — `obscuring_type_for`,
  `get_tiles_obscuring_terrain`, `target_is_obscured` : l'étage `TargetingQuery` seul (masque,
  trait, drapeau de BC, gardes « ami »). La géométrie est déléguée à `movement_query`.
* **`engine/services/movement_query.PositionBoard`** — l'adaptateur qui donne au mirror #444 le
  substrat de la face DÉCISION (`elev_by_pos` + `is_wall_by_pos`) au lieu du `Board` de
  pathfinding. L'identité de tuile y est la POSITION : le natif compare des entités-tuile, et deux
  coordonnées égales désignent la même — la substitution est exacte.
* **`engine/services/ability_range.py`** — le prédicat entre dans `_ability_covers_tile` **et** sur
  la branche `unit_weapon_range` : l'attaque NORMALE passe par le même
  `GetPossibleTargetsForOptions`, et son preset (`0x4002`) ne porte aucun `AllowObscuredTarget*`.
  C'est le vrai rayon de souffle — toute unité à distance du jeu, pas un greffon.
* **Canal `is_wall_by_pos`** (`boardGraph.isWall` = `TileComponent+0x41`) : `context.py` (live) et
  `state_bridge.py` (offline) le publient, `NCContext`/`AiDecisionContext` le portent,
  `early_warning_override` le transmet. **Aucune réinjection** — le champ était déjà remonté par
  `rpc-board.ts` et jeté par le port.
  ⚠ Il ne se déduit PAS de `walkable` : `TileExtensions.IsWalkable` agrège le mur ET le terrain
  infranchissable, là où le prédicat lit le seul drapeau `IsWall`.

## 5. Confrontation LIVE

Isolant : branche A d'`EarlyWarningOverridePlaybook` (`bonus = util + 10·Σ_E d(P,E)` vaut `0` en
zone, `50` hors zone), **exactement un ennemi vivant**, garde anti-dégénérescence.

| montage | volet exercé | natif | port | contrefactuel |
|---|---|---|---|---|
| `1161` greffée, `MC1_67` | zone whole-board, `OT = 6` | 35/40 | **EXACT** | 5 FP avant la tranche |
| `1147` greffée, `MC1_67` | `OT = 0` | 40/40 | **EXACT** | non-régression : rien retiré |
| `necroWarden` natif, `MC1_67` | ÉLÉVATION, **attaque normale** | 15/61 | **EXACT** | sans le prédicat **+9 FP** |
| `astraOrdnance` natif, `MC1_67` | trait `IndirectFire` | 39/39 | **EXACT** | trait ignoré **−3 FN** |
| `astraOrdnance` natif, `C6_17` | **MURS seuls** (le trait tue l'élévation) | 45/54 | **EXACT** | sans le prédicat **+9**, sans la carte `isWall` **+9** |

**Chaque accord est payé par son contrefactuel** — la mesure de ce que le port rendrait sans le
volet testé. Sans eux, `1147` et `astraOrdnance/MC1_67` seraient des accords en régime DÉGÉNÉRÉ
(les deux côtés disant « tout »). `astraOrdnance` sur `C6_17` est le montage le plus pur : avec
`IndirectFire`, `ObscuringType == 4`, donc **seul un mur peut encore bloquer** — les 9 refus lui
sont attribuables sans partage, et ce sont EXACTEMENT ceux que la carte des murs retire.

**Les montages sont FORCÉS, pas subis** (`_pick_discriminant` déplace les unités vers la paire qui
maximise les obstructions) : avec la première paire walkable venue, `C6_17` rendait **zéro**
obstruction sur 36 positions, et `MC1_67` une seule.

## 6. Ce que le lot #568 devient

| ability | avant | après |
|---|---|---|
| `1011 TunnelingHorror` | 5 FP | **0 / 0** |
| `1161 TwinSmartMissileSystem` | 5 FP | **0 / 0** |
| `1168`, `1200`, `1213` | 6 FP | **1 FP** — la tuile OCCUPÉE du caster (`-r1-r1-a-r1`, hors périmètre) |
| `1025`, `1145`, `1147`, `1201`, `1140` | 0 / 0 | **0 / 0** (inchangé, `ObscuringType == 0`) |

## 7. Une RÉFUTATION que le harnais a produite

Un résidu « le volet MURS n'a pas de substrat confrontable » a été écrit, puis **réfuté par son
propre test de garde**. Le balayage offline qui le « prouvait » — « les 17 boards à murs sont tous
des Space Hulk à salles » — était une **tautologie** : il comparait une `list` triée à un `set`
(`sorted(rooms) != {-1}` est toujours vrai). Le test, qui refaisait le calcul proprement, a nommé
`C6_11` et `C6_17` : murs, **aucune salle**, deux équipes spawnées, zéro brouillard. Le volet est
donc mesuré, et le résidu n'existe pas.

La leçon opératoire : un garde-fou n'a de valeur que si l'on vérifie qu'il **peut** rougir sur son
propre gisement — ici c'est le passage du script jetable au test qui l'a fait.

## 8. Validation

* **OFFLINE** — `tests/engine/test_433_r4_r2_r1_r2_line_of_sight_offline.py` : **22 passed**
  (table de vérité du `ObscuringType`, les deux positions de bout de ligne, seuil signé, murs sur
  toute la ligne, `IndirectFire` ne traverse pas un mur, gardes ami/config, `PositionBoard`,
  dégradations, et le câblage des deux termes de l'union).
* **LIVE** — `tests/engine/test_433_r4_r2_r1_r2_line_of_sight_live.py` : **7 passed**.
* **NON-RÉGRESSION** — `test_356_noncomparable_oracle_live.py` **14 passed**,
  `test_433_r4_r2_r1_r1_a_whole_board_gates_live.py` **3 passed** (re-étalonné, cf. §9),
  `test_433_r4_r2_r1_ability_range_live.py` **6 passed**,
  `test_433_r4_r2_adjacency_foyer_live.py` **7 passed**, et **78 passed** offline sur les cinq
  fichiers de la lignée.
* **BANQUE** — `scripts/ratchets.ps1 -Since origin/master` : **40 cliquets verts**, attestation
  `probe_462` régénérée.

## 9. Un test RE-ÉTALONNÉ, et pourquoi c'est le bon signal

`test_the_residual_gap_belongs_to_the_obscuring_stage_not_to_the_gate` (#568) assertait
`faux_positifs` **NON VIDE** sur `1161`. Il avait raison à l'époque, et sa propre docstring
prescrivait de le relire le jour où l'étage cesserait de mordre. Il asserte désormais l'EXACTITUDE,
et conserve ce qui reste vrai : l'ATTRIBUTION — l'écart de `1168` moins celui de `1161` vaut
exactement la tuile occupée par le caster.

## 10. Résidus

* **`#433-r4-r2-r1-r1-a-r1` (la tuile OCCUPÉE)** — inchangé, toujours chiffré à **1/40**, et c'est
  désormais le SEUL écart qui subsiste sur `1168`/`1200`/`1213`. Il se rattache à
  `#433-r4-r2-r1-r1-b` (même canal manquant : l'occupation par tuile).
* **`#433-r4-r2-r1-r2-r1` — le masque n'est lu que pour les abilities du REGISTRE.**
  `TARGETING_RANGE_BY_ABILITY` ne porte que le volet portée ; sans masque, `obscuring_type_for`
  rend `NONE` et le port ne retire rien. L'écart ne peut qu'ÉLARGIR, même arbitrage que
  `GATE_NOT_READ`. **Ce qu'il faudrait** : lire le `rules` des 32 entrées, ability par ability —
  ~15 seulement portent au-delà de `d = 1` et sont donc concernées (à `d = 1` le prédicat est
  structurellement muet).
* **`#433-r4-r2-r1-r2-r2` — les gardes « ami » ne sont pas alimentées.** `IsFriend(target, caster)`
  et `IsFriendOrHasFriendlyUnitOnIt` sont des PARAMÈTRES du mirror, et l'appelant
  `is_tile_in_range_of_any_ability` passe les défauts « tuile libre » — le régime réel de son
  consommateur (des tuiles CANDIDATES de déplacement). Sur une tuile portant un allié du caster, le
  natif ne retire pas et le port retire : écart **restrictif**, le seul de ce cas. Même canal
  manquant que `-r1-r1-a-r1`.
* **`#433-r4-r2-r1-r2-r3` — `EnableObscuringTerrain` n'est pas lu du runner.** Le port prend `True`
  par défaut, valeur du seed courant (`data/seed-bc.json` → `Targeting.EnableObscuringTerrain`).
  Aucun RPC ne publie la section `Targeting` de la BC d'un runner. Une BC qui le poserait à `False`
  ferait sur-retirer le port sur tout le plateau. **Point d'ancrage** : remonter
  `BC.Targeting` dans le canal qui porte déjà `BC.Utilities` (les poids IA).
* **NON COUVERT** : le caster MULTI-PIEDS (l'intersection par pied, `#444-r2` — inerte pour tout
  caster à un pied, ce qui est la quasi-totalité du registre) ; le régime
  `EnableObscuringTerrain = False`.
