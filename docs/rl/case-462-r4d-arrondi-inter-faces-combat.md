# #462-r4d — `test_nightshroud_combat_live.py` : verdict **PORT**, et le trou B a enfin un coupable

**Le rouge est FERMÉ, mais pas par ce dossier.** #462-r4a (`case-462-r4a-canal-du-multiplicateur.md`),
livré en parallèle sur le même foyer, l'a fermé en réparant la même cause. Ce qui reste ici et qui
n'est nulle part ailleurs : **l'attribution** du rot par bissection, **l'instrument** qui a permis de
lire l'écart, le **cran offline** sur ce régime-là, et une leçon d'orchestration.

## 1. Le verdict, et la mesure qui le porte

La case-doc #462 classait ce fichier « PORT **ou** MONTAGE, à TRANCHER ». C'est **PORT** — et **ni
l'un ni l'autre** des deux refactors de masse soupçonnés (`5fa788b7`, `6c112458`).

| commit | date | `test_nightshroud_combat_live.py` |
|---|---|---|
| `0ad4b9e8~1` | 2026-08-02 | **2 passed** |
| `0ad4b9e8` (#446-r2) | 2026-08-02 | **1 failed** — valeurs IDENTIQUES à celles du balayage |

Le rot vient d'un commit qui **ne touchait pas ce fichier**. C'est le **trou B** de #462, et c'est la
première fois qu'il est attribué : le fichier a bien pourri sous un tiers, et le tiers est nommé.

## 2. Pourquoi l'écart n'avait « aucune forme » — et pourquoi ça se mesure

```
off =[180, 180, 112, 158, 240, 183]
live=[250, 212, 168, 122, 220, 221]
```

Ni constant, ni multiplicatif, changeant de signe au 4e coup. Il n'y avait pas de forme à chercher :
ce n'est pas la VALEUR qui diverge, c'est la **borne basse de la cellule tirée**. Le coup est un
`next_internal(lo, hi+1)`, un **modulo** — donc `lo` décalé de 1 change la largeur du modulo et
diffracte les six coups.

⚠ **Le décalage de bornes ne se lit PAS par soustraction ici.** `probe_462_r4a_terrifying_rounding.py`
peut le faire sur son propre cas parce que l'écart y est CONSTANT sur les six coups (`live - off = 1`),
et il explicite cette inférence. Sur un écart diffracté, la soustraction ne mesure rien.

D'où `solve_bounds` (`probe_462d_nightshroud_stage_diff.py`), qui **n'infère rien** : à `rng0` connu
(`dumpRng` avant le cast), la suite des `genrand` est entièrement déterminée ; pour chaque largeur
candidate `R` on calcule les N offsets, `lo` se déduit du premier coup, et on exige les N égalités.
Une seule paire survit.

```
bornes OFFLINE : [109, 282]
bornes NATIVES : [108, 282]
```

Mesuré au passage, et c'est ce qui a **écarté la piste RNG** d'emblée : natif et port consomment
**6 tirages chacun**. Le flux n'était pas désynchronisé — seule la largeur du modulo différait.

## 3. Le jeu de mesures : 8 cellules, dont 4 seulement discriminantes

Le cas nominal seul ne sépare rien (plusieurs modèles y rendent 108). Le levier est de **déplacer la
partie fractionnaire du perçage** en forçant la stat DAMAGE de l'attaquant (`--sweep`), puis
d'inverser les bornes natives à chaque base.

Montage : `necroDestroyer` (mêlée, 6 coups, perçage 60) → `custoTrajann` (armure 2510), porteur de
`MartialKatah` (`EffectBonus.ForPercentDecrease(20)`, gate `IsNormalAttack`) ; l'aura `Nightshroud`
d'`astraPrimarisPsy` ajoute `ForSubtraction` 499. Board `MC1_67`, seed 777.

| base | perçage (Fix64) min/max | NATIF | port du 2026-08-02 |
|---|---|---|---|
| 906 | 135.6 / 352.8 | **(108, 282)** | (109, 282) |
| 907 | 136.2 / 353.4 | **(109, 283)** | (109, 282) |
| 911 | 138.0 / 356.4 | **(110, 285)** | (110, 285) — **témoin** |
| 1000 | 180.6 / 420.6 | **(144, 336)** | (145, 337) |

La base 911 est le **témoin non discriminant** : sans lui, on ne saurait pas qu'un accord peut venir
du RÉGIME et non du modèle.

## 4. La cause, et qui l'a fermée

#446-r2 avait correctement établi qu'un `Round` inconditionnel existe à l'étage MULTIPLICATEUR
(`CalculateBaseDamageWithModifiers`) — il l'avait mesuré sur les BORNES. Mais il l'a posé dans
`apply_pierce_and_modifiers`, **foyer partagé**, en ne migrant vers `pct_list_defender` que la face
PRÉDICTION. Les vecteurs COMBAT, qui gardaient leur face défenseur dans un `apply_all_modifiers`
**postérieur**, ont donc hérité d'un `Round` intercalé entre les deux faces :

```
port (2026-08-02) : perçage 135.6 -> Round = 136 -> x0.8 -> Round = 109
natif             : perçage 135.6 ---------------> x0.8 -> Round = 108
```

**#462-r4a a fermé cette cause** en rendant la chaîne UNIQUE : `_apply_defender_flat_reductions`
**déplace** désormais `def_mods.pct_list` dans `mods.pct_list_defender` (et vide la source), et
l'étage multiplicateur n'est appelé **que si le multiplicateur diffère de 1.0** — donc plus de
`Round` surnuméraire à multiplicateur neutre. Vérifié : `origin/master` rend **4/4 bases
bit-exactes** sur le jeu de cellules ci-dessus, et les deux tests live sont verts.

### La piste que j'ai suivie, et pourquoi elle ne devait pas être livrée

Une RE indépendante (lecture de `CalculateBaseDamageWithAllModifiers` et de ses **trois** sites
d'appel) donne un autre mécanisme pour le même écart : `CalculateAbilityDamage` — le DÉGÂT EFFECTIF —
passe `attackModifiers` **NULL** (buffer de 0x41 octets memset à 0, jamais construit), là où
`PredictAttackRaw` — les BORNES — l'emballe toujours dans un `Nullable..ctor`. Les étapes 1 et 3
étant gatées par `HasValue`, l'arrondi de l'étape 3 n'existerait pas sur le chemin combat.

Un correctif bâti là-dessus (paramètre `attack_modifiers_present`, `False` sur les quatre vecteurs
combat) rend lui aussi **8/8** sur ces cellules et laisse `test_446_r2_inter_face_rounding_live`
vert. **Les deux modèles coïncident partout où j'ai su mesurer** — y compris sur le régime « deux
faces non neutres », où ils prédisent la même chose. Il a donc été **écarté** : il n'apportait aucune
différence observable et aurait défait le travail de #462-r4a sur les mêmes lignes.

⚠ Les deux lectures du décompilé s'opposent pourtant sur le routage d'un `EffectBonus` pourcentage
(`Multiplier@0x30` pour l'une, liste `@0x18` pour l'autre). **Ce désaccord n'est pas tranché** ; il
n'a simplement pas de conséquence observable aujourd'hui. Résidu `#462-r4d-r1`.

## 5. Ce qui est livré

* **`probe_462d_nightshroud_stage_diff.py`** — décomposition par étage + `solve_bounds` (inversion
  des bornes natives **sans inférence**, applicable quand l'écart n'est PAS constant) + `--sweep`
  (déplacement de la fraction du perçage, qui fabrique les cas discriminants). Rend `VERDICT: 4/4`
  sur `master`.
* **`tests/engine/runner/test_462_r4d_nightshroud_cells_offline.py`** — 11 passed, 1 skipped (le
  témoin). Verrouille les 8 cellules natives sur un régime qu'aucune autre garde n'exerce : face
  défenseur = **EFFET** (donc `%-list`) **plus** une soustraction PLATE, sur un perçage fractionnaire.
  `test_446_r2_inter_face_rounding_offline.py`, lui, exerce une modification de **STAT**
  (`Multiplier@0x30`). Le cran **nomme** la régression qu'il garde et rejoue en 1,6 s ce qui coûtait
  un runner.

  ⚠ Sa première version **simulait** le pont entre les deux faces (elle recopiait le merge de #120)
  et rendait `(109, 282)` là où le moteur rend `(108, 282)` : une garde de FICTION, verte ou rouge
  pour de mauvaises raisons. Elle **APPELLE** désormais
  `AttackDamageOperation._apply_defender_flat_reductions`. Contre-épreuve : le déplacement de
  #462-r4a retiré → **6 failed** ; restauré → 11 passed.

## 6. La leçon d'orchestration : deux tâches, une cause

`test_terrifying_defense_live.py` et `test_nightshroud_combat_live.py` étaient **deux entrées** de la
ventilation #462, dispatchées comme **deux tâches**. Ils n'avaient qu'**une** cause. Rien dans les
symptômes ne le disait : régimes sans rapport (`-30 %` `Terrifying_ExtraDefense` contre `-20 %`
`MartialKatah`), écarts de signes **opposés**, l'un constant et l'autre diffracté.

Coût : deux solveurs ont instruit le même foyer en parallèle, et le second est arrivé après la
bataille. Un inventaire compte des **symptômes** ; le nombre de causes ne se découvre qu'en les
réparant. Quand deux rouges tombent sur le même étage nommé — ici `CalculateBaseDamageWithModifiers`,
que la ventilation #462 désignait **déjà** pour les deux — les traiter comme un seul cas est le pari
le moins cher.

## 7. Ce qui n'est PAS couvert

* ~~**Le régime DEUX canaux défenseur simultanés**~~ — **FERMÉ par #462-r4d-r3**
  (`case-462-r4d-r3-deux-canaux-meme-cote.md`) : régime monté, **port bit-exact et SEUL** des cinq
  compositions à reproduire le natif (4 bases discriminantes + 2 témoins + un cas à trois entrées).
  ⚠ Le montage `--thorns` ne butait PAS sur la géométrie : `tileMeta.tiles[].effects` est une liste
  de **dicts**, le prédicat `"Thorns_DefenseReduction" in effects` était donc toujours faux et
  rendait un `want` vide. Corrigé ; les 4 Swamp de `MC1_67` sont atteintes du premier coup.
* **Le multiplicateur ATTAQUANT en COMBAT** (élévation, tranchée) : l'attaquant est neutre dans ce
  montage.
* La **contradiction de RE** du §4 : non tranchée, sans conséquence observable connue.

## 8. Résidus

* **`#462-r4d-r1`** — deux lectures du décompilé s'opposent sur le slot d'un `EffectBonus`
  pourcentage : `Multiplier@0x30` (via `DamageBonus+0x20` → `GetFloatMultiplierFromPercentage`) ou
  liste `@0x18`. Elles prédisent la même chose sur tout ce qui a été mesuré. Ce qui les séparerait :
  un régime où la face attaquant porte un multiplicateur **non neutre** ET la face défenseur un
  `EffectBonus %`, **en COMBAT**, sur un perçage fractionnaire.
* **`#462-r4d-r3`** — le régime « deux canaux du même côté » (§7), montage écrit mais non installé.
