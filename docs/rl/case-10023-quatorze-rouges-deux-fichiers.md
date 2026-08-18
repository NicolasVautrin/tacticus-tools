# #10023 — quatorze rouges, deux fichiers : les DEUX prémisses avaient expiré

`master` à `d8639cb5` : `test_1030_the_lantern_offline.py` 7 FAILED,
`test_enum_ordinal_ratchet_offline.py` 7 FAILED. Aucun des quatorze n'accusait un moteur faux au
sens où il le disait ; les deux fichiers avaient été **invalidés par ce qui a été livré après eux**.
L'un l'a dit correctement (ses cliquets assertionnent leur propre non-vide), l'autre par un mode
d'échec trompeur (`IndexError` sur une liste vide, qui accuse la LECTURE).

## 1. `test_enum_ordinal_ratchet_offline.py` — le détecteur avait perdu sa mémoire

`probe_283` prenait `olds` (les ordinaux ARCHIVÉS) dans la table du **seul** `previous_build()`.

| | couples DÉCALÉS visibles |
|---|---|
| `previous_build()` seul (= `rnca9r7q6c`) | **0** |
| UNION des archives portant `frida/enums.tsv` | **171** (36 + 73 + 55 + 7) |

`t6dpr4k06g` (courant) est **identique** à `rnca9r7q6c` sur les quatre enums — `--step diff` rend
`0 ordinaux divergents`. Le seul renumérotage jamais mesuré est `gqfc5mff6c -> rnca9r7q6c`. Au
versionnement de `t6dpr4k06g`, « le build précédent » a avancé d'un cran et le détecteur a **oublié**
le renumérotage, alors que les citations figées dans le dépôt, elles, n'ont pas bougé.

Effet : `_compile_larges` rendait `None`, `annotation_de_ligne` ne pouvait plus rendre `perimee`,
l'origine d'une citation retombait sur `inconnu`. **Cinq tests de discrimination** l'ont dit en
rouge, plus le test du diff (`PreUnitAbility == 43`, l'ordinal de `gqfc5mff6c`).

**Correctif** : `memoire_archivee(fq)` = `{MEMBRE: frozenset(ordinaux sur AU MOINS UNE archive)}`.
L'union est **monotone** — archiver une table de plus ne peut qu'ajouter de la mémoire.
`previous_build()` reste, pour le DIFF (étape 0) seul.

Le 7ᵉ rouge était **réel** : 3 sites de dépôt portaient un ordinal en dur (`ATTACK_IN_ATOMIC_GROUP
= 0x4a` en `assign`, deux `UTILITY_TYPE == 62/63` sans membre). Réécrits en forme **confrontée**
(littéral ET membre dans la même chaîne de comparaison), la seule qui fige ET rougisse au
renumérotage.

⚠ Le fichier de tests **reconstruisait** `olds` lui-même à partir de `previous_build()` : il
dupliquait le câblage au lieu de le lire, donc corriger le probe ne l'a pas rendu vert. Il lit
maintenant `SW.memoire_archivee_par_enum()`, et ses fixtures sont **dérivées** (`_temoins()`) au
lieu d'être figées sur `PreUnitAbility`/`0x2b` — un littéral qui suit un build est un cliquet qui se
re-casse.

## 2. `test_1030_the_lantern_offline.py` — Mortarion a SEPT pieds

Le montage posait un caster **mono-hex**. `1094 TheLantern` porte `CasterHas7Tiles` (bit 37), et
#895-r2 a porté les trois filtres de `GetFeetCount` dans
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` **après** l'écriture du fichier
(le test est ancêtre du gate ; le rouge est né au merge). Le cast repartait en
`invalid_target = 0x2000000000`, sans un effet posé et sans erreur.

Source de l'empreinte — **le board, pas l'unité** : `data/boards/global/GB_Mortarion_05.json` porte
`board.BossPlatforms = [{"Size": 7, "Tiles": [(4,8), (3,9), (4,9), (5,9), (5,8), (4,7), (3,8)]}]`,
centre en tête, passée au spawn par `IdunBattle.Operations.SetupGameOperation$$AddBossUnit`. Aucun
champ de gameconfig ne porte la taille d'une unité.

Le board est passé à 13×13 centré : à 9×9, le bord tronquait deux des six directions de
`...TheLanternAbility$$GetDynamicInvalidTargetReason`, et une cible à distance 2 était refusée
(`0x2`). Un **étage 0** re-dérive désormais le montage du gate au lieu de le figer.

⚠ **La piste « le canal d'événement a changé » est RÉFUTÉE.** `AbilityHandler` fait
`self.last = {"ability_type": …, "ported": True, …, **diag}` où `**diag` est le retour
d'`execute_behaviour` : `dsl` et `ability` sont là **dès que le cast a lieu**. Le dict court sans
eux est la forme d'un cast REFUSÉ. Les sept rouges ont donc **une seule** cause.

## 3. Ce que la réparation a trouvé : les deux faces divergeaient d'UNE tuile

Une fois le caster à sept pieds, l'étage 6 (zone COMBAT vs zone DECISION) a montré `(6,5)` — un
pied secondaire — d'un seul côté. Le décompilé tranche pour la face DECISION :

```
DSLSelectors$$SurroundingTiles, includeCenter == 0 :
    SurroundingTiles(origin, includeCenter: 1, …) op_Subtraction Tiles(origin)
UnitsMainTilesSelector$$Select : slot 3 de l'inner (SelectAllUnits) puis GetMainTile par élément
TargetsSelector$$SelectUnit   : if (IsUnitFoot(e) || IsTile(e)) e = UnitExtensions$$GetUnit(e, state)
```

Les sept entités-tuile résolvent **toutes** vers Mortarion ⇒ `Tiles(CasterTiles)` = une main tile.
Le port COMBAT évaluait l'exclusion **dans** la boucle sur les origines, donc chaque élément était
sa propre main tile et les sept sortaient. Corrigé : l'exclusion s'évalue sur l'origine **entière**.

Rayon mesuré : 10 call-sites `SurroundingTiles` dans `engine/**`, 9 avec exclusion armée ; le
changement est **inerte** sur toute origine à un élément (8 d'entre eux). 480 tests offline du rayon
rejoués, tous verts.

## Résidus

- `#10023-r1` — `Tiles(origin)` sur une TUILE VIDE (le natif ne retranche rien) et `_main_tile`
  appelé sans `board` dans `dsl/base.py`.
- `#10023-r2` — `archived_builds()` trie par NOM ; l'ordre chronologique n'est qu'une coïncidence.
