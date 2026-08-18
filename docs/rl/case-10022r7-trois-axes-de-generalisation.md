# #10022-r7 — généraliser `ShortestPathToEnemyUtility` : trois axes, trois verdicts distincts

Build `t6dpr4k06g`. La confrontation de #10022-r3 tenait sur **un** couple (board, seed), des unités
**1-hex** et des ennemis **tous ciblables**. Les trois axes sont traités — et **aucun des trois ne
se conclut de la même façon**.

---

## 1. Axe (b) — second couple (board, seed) : VERT, et l'élagage est enfin exercé

Les six géométries étaient **les coordonnées de `MC1_67` écrites en dur**, et rien ne le disait : sur
tout autre board elles désignaient des tuiles quelconques. `geometries_derivees` les tire du
`boardGraph` d'un build SONDE, avec le critère jusque-là implicite rendu **exécutable** (trois
`pathCount` deux à deux distincts, ordre de liste décorrélé de la proximité).

| couple | mesurées | discriminantes | accords | détour max |
|---|---|---|---|---|
| `MC1_67` / `777` (historique) | 6 | 5 | **5** | 1 (sur 3 configs) |
| `C3_06` / `31337` (dérivé) | 6 | 6 | **6** | **2** (sur 1 config) |

Le **détour** (`pathCount - hexDist - 1`) est désormais RAPPORTÉ, et le bilan le dit quand il vaut
`0` : tant qu'il est nul, l'**élagage 1** du natif (`minSteps <= hexDist` → skip) ne se distingue pas
de son absence, donc un vert ne dit rien de cette branche. Il est maintenant exercé **en live**, pas
seulement offline.

`C3_06` n'est pas choisi au flair : balayage des 752 boards non-boss par niveaux d'élévation et
blocs LOS (5 niveaux, 19 blocs — le mieux classé après `C2_20`/`MC2_45`, plus petits).

## 2. Axe (a) — multi-hex : une face NON OBSERVABLE, une face confrontée 4/4

Le seul porteur d'empreinte du jeu est un **BOSS**, et son empreinte vient du **BOARD**
(`BossPlatforms`), pas de l'unité — `AddPredefinedUnits` ne pose qu'UNE tuile (#10018-r1). Le boss
entre donc côté JOUEUR, comme **CIBLE** des clones IA : le mettre côté IA casserait la neutralisation
des buckets (`bucket 1 = PreferNonBoss` trancherait avant le 6).

### (a1) MAIN TILE vs FOOTPRINT — indiscriminable, et c'est de l'ARITHMÉTIQUE

C'est pourtant ce qui sépare cette utilité de `MinDistanceToClosestEnemyUtility` (17). Mesure de
l'écart `pathCount(main) − min_f pathCount(f)` sur l'empreinte réellement montée :

| porteur | empreinte | histogramme de l'écart |
|---|---|---|
| `deathBossMortarion` | 7-hex (centre + 6 voisins) | `{0: 1, 1: 63}` |
| `admecBossBelisarius` | 3-hex (triangle) | `{0: 46, 1: 7}` |

L'écart ne vaut que **0 ou 1**, et c'est structurel : la main tile est adjacente à tout pied de coût
minimal sur **toutes** les empreintes du jeu (11 `BossPlatforms`, tailles 1/3/7). Or un basculement
**strict** de l'argmax exigerait `d(B) − 1 < d(A) < d(B)` — impossible en entiers.

⇒ **La distinction MAIN TILE / FOOTPRINT n'est pas observable par l'ORDRE D'ACTIVATION.** Ce n'est
pas un manque de montage : aucun montage ne peut la montrer par cet oracle. Résidu **`#10022-r8`**
pour l'observable qui le pourrait.

### (a2) MAIN TILE vs `decisionView.pos` — observable, et le harnais avait tort

`pos` est le **DERNIER pied projeté**, pas la main tile (`snapshot.py::_load_feet` le documente ;
mesuré : `feet[0] = (4,8)`, `pos = (3,8)`). L'écart peut donc atteindre 2, et l'argmax basculer.
`positions_et_teams` lisait `pos` — invisible tant qu'aucune unité multi-hex n'entrait.

Corrigé (`feet[0]`, repli `pos` en mono-hex) et **CONFRONTÉ** : `admecBossBelisarius` 3-hex sur
`GB_Belisarius_01`, **4 configurations discriminantes, 4 accords**.

## 3. Axe (c) — ennemi non ciblable : le filtre `Steppable` CONFRONTÉ

`StateExtensions$$GetAllEnemyUnitsOfPlayer` retient une entité sous **deux** conditions et deux
seulement : `TeamId` différent **et** `!HasTrait(0x1b = UnitTrait.Steppable)`. **Aucun filtre de
ciblabilité**, aucun filtre `alive` — contrairement à `FindClosestEnemy`. (Le paramètre `onlyHeroes`
n'est lu **nulle part** dans le corps.)

Porteurs `Steppable` du gameconfig : `powup*` et `LootObj_*` (npc, montables par
`--explicit-stats`), plus `genesSmnDecoy` et `astarSmnHaywireMine` (summons).

Montage : `powupArmor` posé **dans mon camp**, à portée d'un clone. Les deux prédictions divergent
**par construction** :

| clone | `pathCount` au vrai ennemi | au `powupArmor` | prédiction |
|---|---|---|---|
| A `(0,2)` | **3** | 10 | FILTRÉE → A |
| B `(5,8)` | 11 | **2** | NAÏVE → B |

Le natif active **A**. `MC1_67`/`777`, configuration DISCRIMINANTE (prédit ≠ `ECS[0]`).
⇒ le filtre est **mesuré**, plus seulement lu. Le harnais, lui, ne filtrait rien : `est_steppable`
lit les traits au **gameconfig** (le `decisionView` ne les publie pas) et répond NON sans `visualId`
— dégradation permissive, jamais un filtre inventé.

## 4. Trois FAUX ROUGES, trois gardes — et c'est le vrai gain de la tranche

Chacun a d'abord ressemblé à un désaccord du port :

1. **L'argmax se prend sur l'ENTRÉE DU PICKER** (`AnAiGroupOperator$$GetValidUnits`), pas sur toute
   la team. Un clone tué au montage par l'aura `ContagionsOfNurgle` de Mortarion gardait une position
   — donc une utilité, donc l'argmax — pendant que le picker ne le voyait pas : **3 désaccords, zéro
   faute du port**. Le rapport imprime désormais `hors_picker`.
2. **Un CANDIDAT doit être vivant, un ENNEMI n'a pas à l'être.** Les deux rôles n'ont pas le même
   filtre, et c'est LU : `par_id` garde les cadavres (ils comptent comme cibles), `vivants_dv`
   restreint les candidats.
3. **`team_ia` n'est pas la team MAJORITAIRE.** Ce critère supposait un roster d'une seule unité de
   mon côté ; il devient **indéterminé à effectifs égaux** — exactement le montage 2 contre 2 de
   l'axe (c), où il désignait MA team. Dérivé de `currentPlayer`, repli majoritaire NOMMÉ.

## 5. Ce que la tranche NE couvre PAS

- **(a1) reste ouvert** — `#10022-r8`. L'ordre d'activation ne peut pas le trancher ; il faudrait
  lire l'utilité elle-même (capteur `aiUtilityTrace*`, **exclusif**, donc hors d'atteinte tant que
  d'autres agents partagent le pump) ou passer par le canal MOUVEMENT.
- **Les buckets 0 à 5** ne sont toujours pas portés (`#10022-r2`, `-r4`, `-r5`) : le montage les
  neutralise par construction, il ne les valide pas.
- **Seule la PREMIÈRE activation** est confrontée, sur les trois axes.
- **L'exception TÉLÉPORTEURS** d'`IgnoreTerrainPathfinder$$IsValidPathNode` n'est pas portée en
  amont, donc pas exercée. Aucun board de `data/boards/` n'en porte.
- **L'axe (c) tient sur UNE configuration** (le couple discriminant est rare : il faut que le
  porteur `Steppable` soit strictement plus proche d'un clone que le vrai ennemi ne l'est de
  l'autre). La contre-épreuve est acquise par construction — la prédiction naïve désignait une
  autre unité — mais elle n'est pas répétée.
