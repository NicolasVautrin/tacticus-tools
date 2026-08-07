# #287-r11-r2-r1 — la ligne de vue du gate de `1076`, et le slot qui n'était pas sur l'interface qu'on croyait

Le gate de ciblage de `1076 MV71SniperDroneSquadAttack` héritait du COLLAPSE de
`IdunBattle.Core.Services.BattleQuery$$IsTargetInAttackRangeForSummon` (`IBattleQuery` slot 196) :
`_pick_tile` réduisait ce troisième filtre de `PickTile` à `1 <= distance(tuile, cible) <= portée`.
Tant que `PickTile` ne servait qu'à l'EXÉCUTION, l'écart coûtait une tuile de spawn parfois
différente ; depuis #287-r11-r2 il décide de la **LÉGALITÉ D'UN CAST**, donc chaque condition non
portée ACCEPTAIT une cible que le natif REFUSE.

**Mesuré live, et le SOUS-refus était réel** : sur `C3_47`, un caster `tauMarksman` face à une cible
dont les **10** tuiles libres du disque r=4 sont masquées par un mur de roche — natif
`0x1 ValidRequest`, port d'avant `0x0`. **2 SOUS-refus** (les deux porteurs), fermés par cette
tranche.

## 1. Le corps natif, verbatim

`BattleQuery$$IsTargetInAttackRangeForSummon(parent, unitId, tile, target)` :

    if (target == null || !UnitExtensions.IsTargetable(target)) return false;
    range = 0; foreach (w in GetUnitConfig(unitId).Weapons)
                   range = Math.Max(range, w.Range.HasValue ? w.Range.Value : 1);
    if (DamageCalculations.ShouldApplyRangedInMelee(parent, [tile], state, true)) {
        range = 1; if (!TileExtensions.IsAdjacentTo(tile, GetTiles(target)))       return false;
    } else if (range == 1 && !TileExtensions.IsAdjacentTo(tile, GetTiles(target))) return false;
    if (BattleQuery.GetDistance(tile, target) > range)                             return false;
    foreach (t in GetTiles(target))
        if (!<IMovementQuery slot 16>(tile, t, 6, 2).IsNullOrEmpty())              return false;
    if (range == 1)
        return DamageCalculations.CanMeleeAttackOverElevationDifference(
                   tile, EntityExtensions.GetMainTile(target));
    return true;

Quatre lectures que la conversion oblige à faire.

### 1.1 Le `<slot 0x10>` est celui d'`IMovementQuery`, PAS d'`IBattleQuery`

La fiche #287-r11-r2 §8 l'écrivait `<IBattleQuery slot 0x10>`. C'est **faux**, et le confondre aurait
lu `IBattleQuery 16 = GetChainedUnits/3` — trois paramètres pour un appel qui en passe quatre.

Ce qui tranche est **mesuré, pas contextuel** : le service interrogé est `this+0x10`, et
`IdunBattle.Core.Services.BattleQuery$$GetDistance(tileA, tileB)` appelle le slot **9** du **MÊME
champ**, que `data/symbols/<build>/metadata/interface_slots.tsv` nomme `IMovementQuery 9
GetDistance/2`. Donc `this+0x10` = `IMovementQuery`, et le slot 16 y est
`GetTilesObscuringTerrain/4`.

**Quelle SURCHARGE** — la table en donne deux (`IMovementQuery 15` et `16`, quatre paramètres
chacune), et le port mirrore les deux. Le discriminant est également mesuré :
`TargetingQuery$$GetTilesObscuringTerrain(caster, casterTiles, target, options)` appelle le slot
**15** avec une LISTE, et `TargetingQuery$$IsTargetTileObscured(from, target, onlyWalls)` le slot
**16** avec une tuile. Le slot 16 est donc la surcharge **ENTITÉ** —
`MovementQuery$$GetTilesObscuringTerrain` @ la surcharge qui trace les deux lignes, celle que le
port a déjà sous `services.movement_query.get_tiles_obscuring_terrain` (#444).

### 1.2 Même fonction que `TargetIsUnobscured`, mais PAS le même chemin d'entrée

Le brief demandait de confronter les deux corps avant tout réemploi. Résultat de la confrontation :
c'est **littéralement la même fonction native** (la cascade de ciblage y arrive par le slot 15,
qui court-circuite sur `from.Count == 1` vers le slot 16). Le réemploi de la géométrie est donc
justifié par une mesure, pas par une ressemblance de nom.

⚠ **Mais l'ENTRÉE diffère, et c'est ce qui interdit de réemployer le wrapper.**
`TargetingQuery$$GetTilesObscuringTerrain` gate sur `TargetingConfiguration.EnableObscuringTerrain
(+0x10)`, sur `IsFriendOrHasFriendlyUnitOnIt`, et **compose** son `ObscuringType` à partir des bits
25/26 du masque et du trait `IndirectFire`. `IsTargetInAttackRangeForSummon`, lui, appelle
`IMovementQuery` **directement**, avec les littéraux `(6 = ObscuringType.All, 2)`. Un port qui aurait
réutilisé `services.targeting_query.target_is_obscured` rendrait « non obscurci » dès qu'une BC pose
`EnableObscuringTerrain` à faux — et **accepterait alors une cible que le natif refuse**. Le port
appelle donc `services.movement_query` (la géométrie) et **jamais** `services.targeting_query` (les
gardes de la cascade). Étage 3 de la garde.

### 1.3 `ShouldApplyRangedInMelee` est évalué DEPUIS LA TUILE CANDIDATE

`DamageCalculations$$ShouldApplyRangedInMelee(parent, attackerTiles, state, ignoreTrait)` reçoit ici
`attackerTiles = TExtensions.ToList(tile)` — **la candidate**, pas les tuiles du caster. C'est donc
« un ennemi du caster est-il au contact de la tuile où le DRONE serait posé », et le mirror existant
(`targeting.should_apply_ranged_in_melee`, lié au caster) ne pouvait pas répondre à cette
question-là. D'où un second mirror, `_should_apply_ranged_in_melee_from_tile`, paramétré par la
tuile. `ignoreTrait = 1` est le littéral du call-site : le gate `HasTrait(0xb Ranged)` est
court-circuité.

C'est **l'étage qui ARME** `CanMeleeAttackOverElevationDifference` : `tauSmnDroneSniper` a une arme
de portée 4, donc `range == 1` n'est atteignable que par ce clamp. La question du brief
(« `CanMeleeAttackOverElevationDifference` mord-il sur ce gate ? ») se répond donc **oui, mais par
le clamp** — porter l'un sans l'autre aurait laissé du code mort.

### 1.4 `CanMeleeAttackOverElevationDifference` est IMPLIQUÉ sur une cible à UN PIED

Quand `range == 1`, le natif exige d'abord `TileExtensions$$IsAdjacentTo(tile, GetTiles(target))`,
qui délègue (décompilé LU) à `MovementUtil$$AreTilesAdjacent` — laquelle porte **déjà** la porte
`|dElev| < 2`. Sur une cible à un pied, `GetMainTile(target)` **EST** cette tuile-là : la clause
finale ne peut jamais changer le verdict.

Elle ne discrimine que sur une cible **MULTI-PIEDS** : `IsAdjacentTo` regarde **tous** les pieds,
l'élévation la **MAIN TILE seule**. Une candidate adjacente à un pied plat, dont la main tile est à
2 crans, passe la première et échoue la seconde. Étage 5 de la garde (les deux bras, avec
contre-épreuve).

## 2. Ce que le port fait maintenant

`engine/runner/abilities/loki/mv71.py` :

| symbole | mirror de |
|---|---|
| `_is_target_in_attack_range_for_summon` | `BattleQuery$$IsTargetInAttackRangeForSummon` (slot 196) |
| `_should_apply_ranged_in_melee_from_tile` | `DamageCalculations$$ShouldApplyRangedInMelee`, depuis la candidate |
| `_is_obscured_from_tiles` | `UnobscuredTilesSelector$$IsObscured` (le maillon LoS du REPLI) |
| `_occupants_by_tile` | le substrat `{tuile: (team, steppable, targetable)}` |

Les **DEUX faces** consomment le même foyer — `_pick_tile` (runner : gate ET exécution) et
`pick_tile_scene` (prédiction). Le natif appelle le même `PickTile` des deux côtés ; un fork y
aurait fait diverger la légalité et la prédiction.

⚠ **Le REPLI a son propre maillon de ligne de vue, et ce n'est PAS le slot 196.** `PickTile`
enchaîne `sel = UnobscuredTiles(Tiles(Target@0x60), sel)` — `DSLSelectors$$UnobscuredTiles(fromAny
Tiles, toTiles)` pose `+0x20 = fromAnyTiles` et `+0x18 = toTiles`, et `Select` garde de `+0x18` ce
qui n'est pas obscurci depuis `+0x20`. Le sens de la ligne est donc **CIBLE → candidate**, et le
prédicat est un **OU** (une seule source dégagée suffit), à l'inverse du **ET** de la boucle du slot
196 (refus dès qu'UNE tuile de la cible est masquée). Sa liste source VIDE rend `true` (obscurci) —
un `return false` par symétrie aurait gardé une tuile que le natif retire.

Placement du foyer : **dans `mv71.py`**, et c'est une mesure. `engine/services/battle_query.py`
serait l'homonyme naturel, mais `movement_query` charge déjà `services.battle_query` en process
frais (vérifié) — l'import y serait un cycle, donc un différé, que la doctrine met en dernier
recours. Le second consommateur natif de ce slot (`AggressiveOnslaughtPlaybook`, cf. résidu
`#287-r11-r2-r1-r3`) hissera le foyer quand sa tranche viendra.

## 3. Confrontation LIVE, avec attribution

`probe_287r11r2r1_los_summon_live.py` — géométrie **PLACÉE**, board **CHOISI** par balayage des
**779** boards versionnés, attribution par **désarmement CIBLÉ sur cette tranche** (le témoin
substitue `_is_target_in_attack_range_for_summon` par le collapse d'avant, pas la règle entière).

`C3_47` porte deux tuiles `Block` d'élévation **3** en `(1,1)` et `(1,2)`. Depuis `(0,1)` (Grass,
élévation 0), le disque r=4 se coupe en deux : **4** tuiles marchables CLAIRES — `(0,2) (0,3) (1,4)
(2,4)` — et **10** MASQUÉES. Occuper les quatre (le caster en est une) suffit : quatre unités au
lieu des soixante d'un disque r=4 ordinaire.

| montage | libres clairs / masqués | natif (cible clé) | port | sur-refus | SOUS-refus | vue rouge |
|---|---|---|---|---|---|---|
| `masque` | 0 / 10 | `0x1 ValidRequest` | `0x1` ×2 | 0 | 0 | **2 SOUS-refus** |
| `degage` | 1 / 10 | `0x0` | `0x0` ×2 | 0 | 0 | 0 |
| `melee-candidate` | 1 / 10 | `0x1 ValidRequest` | `0x1` ×2 | 0 | 0 | **2 SOUS-refus** |

**4 cibles confrontées, 0 sur-refus, 0 sous-refus.** Non-dégénérescence : `{0x1: 2, 0x0: 2}`.

### Les deux bascules ne changent qu'UNE variable, et ce ne sont pas les mêmes

* `masque` → `degage` : l'allié de `(1,4)` part en `(5,5)`, hors du disque. **Le compte de libres
  passe de 10 à 11** et le natif bascule `0x1 → 0x0` : le décideur n'est donc **pas** le compte du
  disque (c'était celui de #287-r11-r2), c'est la **ligne de vue** — dix tuiles libres et un refus.
* `degage` → `melee-candidate` : **MÊMES tuiles occupées, MÊME ensemble libre, MÊME ligne de vue**.
  Seule l'**ÉQUIPE** de l'occupant de `(2,4)` change (allié → ennemi). `(2,4)` est adjacente à la
  seule libre claire `(1,4)`, donc `ShouldApplyRangedInMelee` depuis la candidate devient vrai, la
  portée tombe à 1, et `(1,4)` (d=3) n'est plus adjacente à la cible. Le natif rebascule `0x0 → 0x1`.

### `(2,3)` ne convient PAS, et c'est le `ConnectivityComponent` qui le dit

Premier jet du montage `melee-candidate` : ennemi en `(2,3)`, voisine **HEX** de `(1,4)`. Natif
`0x0`, port `0x0` — **accord, et prédiction de la RE réfutée**. Mesure : le
`ConnectivityComponent` LIVE de `(1,4)` porte **5** arêtes, et celle vers `(2,3)` n'y est pas
(élévations 2 et 3, donc ce n'est pas la porte `|dElev| < 2` qui l'ampute). Le port lit
`board.neighbours`, le natif lit ce composant : ils sont d'accord, et c'est **la géométrie hex
supposée** qui était fausse. Le probe garde ce fait en commentaire, et son étage
`PREDICTION DE LA RE NON CONFIRMEE` est ce qui l'a rendu visible plutôt que noyé dans un accord.

### Aucun ennemi adjacent au caster, et c'est délibéré

Même raison qu'en #287-r11-r2 : `forceMeleeTarget = RangedBool.IfRangedCaster` ferait clamper la
portée du CASTER et la cible à d=2 serait refusée par `TargetIsInRange` — un AUTRE bit, qui
masquerait la règle. Le caster est en `(0,3)`, et le seul ennemi du montage `masque`/`degage` EST
la cible, à d=2. Dans `melee-candidate`, le second ennemi est en `(2,4)`, à d=2 du caster : mesuré
`should_apply_ranged_in_melee(state, caster) is False` (étage 4 de la garde).

## 4. La garde

`tests/engine/test_287r11r2r1_los_summon_offline.py`, **18 tests / huit étages** : les slots lus
dans la table du build (dont « `IBattleQuery 16` ne désigne PAS `GetTilesObscuringTerrain` ») ; les
littéraux `(6, 2)` confrontés **par `ast`** aux constantes nommées (un critère textuel rougirait sur
le décompilé CITÉ, qui doit rester verbatim) ; la bascule sous la seule élévation d'un rocher, à
occupation et distance invariantes ; **`EnableObscuringTerrain` ne désarme PAS ce call-site**, avec
contre-épreuve sur le foyer de la cascade, qui l'honore ; les quatre conjonctions du clamp mêlée
(équipe, élévation, `Steppable`, `Targetable`) ; les deux bras de la clause d'élévation finale ; le
maillon `UnobscuredTiles` du repli (liste vide → obscurci, un OU et non un ET) ; les mutants en
delta.

Vue rouge sur l'arbre témoin (`git archive` de `36eb3690`, arbre **complet**) : **15 failed /
3 passed** ; **18 passed** après. Les 3 verts du témoin sont nommés : la géométrie du substrat, la
table de slots du build (acquis antérieurs), et la géométrie `#444` de `MovementQuery`, qui existait
déjà — c'est son **branchement** qui manquait.

⚠ Les symboles neufs sont importés **DANS** leurs tests, pas en tête : sinon la COLLECTE échoue sur
le témoin et la vue rouge se réduit à une ligne.

## 5. Ce qui n'est PAS couvert

* **La clause d'élévation finale n'est exercée qu'OFFLINE**, et sur un substrat **fabriqué**
  (`target_tiles` à deux pieds passé directement au mirror). Aucune unité multi-pieds n'a été montée
  en bataille : `_pick_tile` lit pourtant `get_unit_feet(state, target_id)`, donc le chemin est
  branché — mais **non confronté** sur une vraie MoW.
* **Le repli `HasTooManySummons`** (au cap de 3 drones) n'est exercé qu'offline. Son maillon
  `UnobscuredTiles` a désormais sa bascule (étage 7), mais aucun montage live n'atteint le cap.
* **`IsTargetable(target)`** est INERTE : aucun chemin du port ne pose `UnitFlag.Untargetable`. Le
  mirror est écrit pour que la règle s'active d'elle-même le jour où le drapeau sera posé.
* **La face PRÉDICTION** (`pick_tile_scene`) consomme le même foyer, et
  `test_mv71_prediction_live_offline_agreement` reste vert — mais aucun montage de prédiction
  **avec élévation obscurcissante** n'a été joué : sur un board plat, l'étage neuf est inerte des
  deux côtés.
* **Deux rouges PRÉ-EXISTANTS**, reproduits à l'identique sur `36eb3690`, donc hors de cette
  tranche : `test_loki_solo_targeting_live.py::test_1151_the_quickening_targeting` (re-joué SUR LE
  TÉMOIN, même échec) et `probe_486r15` sur `test_524r1_bond_sous_effets_offline.py`.

## 6. Résidus

* ~~**`#287-r11-r2-r1-r1` — `_drone_attack_range` rend `1` là où `GetUnitMaxRange` rend `0`.**~~
  **FERMÉ.** `_drone_attack_range` DÉLÈGUE désormais à `services.battle_query.get_unit_max_range`
  (forme B, morsure gardée). Le régime **est** atteignable, contrairement à ce que ce résidu
  supposait : `BattleQuery$$GetUnitConfig` lit `BC.Units[]`, donc un seed BC dont
  `tauSmnDroneSniper.Weapons` est vide fait rendre `0` au natif — mesuré, il **refuse** alors le
  cast (`0x1 ValidRequest`) là où le port d'avant l'acceptait : **2 SOUS-refus** au témoin. Détail :
  `case-287r11r2r1r1-portee-nulle-du-drone.md`.
* **`#287-r11-r2-r1-r2` — le gate `!HasFlag(attacker, 0x1c IngoreRangedInMelee)` (typo native) est
  absent des DEUX mirrors de `ShouldApplyRangedInMelee`** (`targeting.should_apply_ranged_in_melee`
  l'omettait déjà, son docstring ne le cite pas). INERTE offline (aucun `UnitFlagsComponent` ne pose
  `28`), mais le canal `combatSnapshot.unitFlags` existe. S'y ajoute que la face PRÉDICTION lit
  `Steppable` sur la borne **STATIQUE** `entity_trait_names(None, visualId)` — la `Scene` est
  hydratée par `vis_by_id`, donc un trait ACCORDÉ EN BATAILLE y est invisible, là où le runner passe
  par `has_steppable_unit`.
* **`#287-r11-r2-r1-r3` — `UnobscuredTiles` est une DÉCISION portée, pas un nœud DSL**, alors que
  son voisin immédiat dans la même chaîne de repli (`FilterTilesIfCanAttackTargetTileFrom`) EST un
  nœud (`entities/selectors/tiles.py`, #433-r4-r1). Doctrine #149 : l'artefact natif est un
  `DSLSelectors`, donc l'arbre devrait le porter. S'y ajoute le second consommateur du slot 196 —
  `engine/playbook/aggressive_onslaught.py` déclare son gate 2 « PORTÉ PARTIEL » (target
  vivant/targetable seulement) alors qu'un foyer complet existe désormais dans `mv71.py` ; le
  brancher demande de le hisser hors de `mv71`, donc de trancher le cycle
  `services.battle_query ↔ movement_query` (levier 1 ou 2 de la doctrine, pas un différé).
