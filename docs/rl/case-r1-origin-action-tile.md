# Case R1 — la tuile d'ORIGINE dans les positions candidates d'action

**Verdict : la prémisse de R1 est RÉFUTÉE.** L'origine EST une position candidate du natif, et elle
y est la **PREMIÈRE**. Ce n'est pas un ajout d'outillage. Ce qui divergeait réellement, c'est
l'**ORDRE** du sweep de positions côté port — corrigé ici, mesuré avant/après sur 4 couples
(board, seed).

---

## 1. Ce que R1 affirmait, et pourquoi c'était faux

Formulation d'origine (`case-128-tile-elevation-utility` §5, reprise par `backlog.md` et
`port-residuals-inventory.md`) :

> `ABaseAiUnitTactic$$GenerateActionTiles` = `IBattleQuery.slot+0xe` (tuiles de MOUVEMENT,
> `GetMovableTilesFor` **exclut** la tuile courante) ; `ActiveAbilityActionGenerator.<GenerateActions>d__7`
> ne tire la branche `NullPosition` (= sur place) **que si la liste est vide**. Notre hook, lui,
> ajoute EXPRÈS l'origine à `attackPlans.ranked`.

Les deux moitiés de droite sont vraies. **L'identification du slot +0xe est fausse**, et c'est elle
qui portait toute la conclusion.

### 1.1 Le slot +0xe est `GetCurrentAndMovablePositionsFor`

`IdunBattle.AI.Tactics.ABaseAiUnitTactic$$GenerateActionTiles` appelle `IBattleQuery` slot +0xe avec
`(unit, false, 0)` — **le 3e argument vaut littéralement 0**. Ce seul fait tranche l'ambiguïté entre
les candidats de `BattleQuery` :

| candidat | 3e paramètre | verdict |
|---|---|---|
| `IdunBattle.Core.Services.BattleQuery$$GetMovableTilesFor` | `MovementOptions*` **déréférencé** (`local_38 = *param_4`, 0x30 octets copiés) | `0` ⇒ null-deref, impossible |
| `IdunBattle.Core.Services.BattleQuery$$GetMovablePositionsFor` | idem, déréférencé | impossible |
| `IdunBattle.Core.Services.BattleQuery$$GetCurrentAndMovablePositionsFor` | copié **par valeur** dans un local (`uStack_44/uStack_40 = param_4`), jamais déréférencé | **seul compatible** |

Second discriminant, indépendant : le type d'élément. La liste rendue est consommée par
`IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$FilterMovementTilesForMaxMovement`,
qui énumère des **`UnitPosition`** (`IdunBattle.Core.UnitPosition$$get_MainTile` sur chaque élément).
`GetMovableTilesFor` rend des **tuiles** ; seul `GetCurrentAndMovablePositionsFor` rend des positions.

Corps de la fonction (décompilé `gqfc5mff6c`) :

```csharp
var set = new OrderedSet<UnitPosition>( EntityExtensions.GetUnitPosition(unit, _state) );  // COURANTE
set.UnionWith( _movementQuery.GetMovablePositionsFor(unit, flag, default) );                // + movable
return set;
```

`OrderedSet` préserve l'ordre d'insertion ⇒ **la position courante est candidate, et elle est la
première de la liste**. Le `GetMovableTilesFor` sous-jacent exclut bien la tuile courante (mesuré :
`aiMovableTiles` ne la contient jamais) — c'est l'union qui la remet.

Le hook de playbook (`GenerateActionTiles` -> `PlaybookDatabase.LoadPlaybook` -> slot 1 =
`FilterMovementTiles`) ne peut que **restreindre** : le seul corps existant
(`FilterMovementTilesForMaxMovement`, utilisé par RunsAround / RunsAway / SaviorProtocols) re-remplit
un `OrderedSet` à partir des positions déjà présentes. Aucun playbook n'ajoute de position.

### 1.2 Réfutation LIVE, indépendante du décompilé

`probe_r1_origin_action_tile.py` marche une trajectoire native et compte les chunks où le natif
**caste sans émettre de `MoveUnitMessage`**, en regardant `aiMovableTiles` de l'unité au même
instant. Si la prémisse R1 était vraie, ce compte serait 0 dès que le movable est non vide.

| couple | chunks « ability sans move » | dont movable NON vide |
|---|---|---|
| `MC1_67` / 777 | 4 | **4** (nMov = 13, 5, 22, 18) |
| `C3_01` / 31337 | 2 | **2** (nMov = 10, 12) |
| `C4_09` / 999 | 5 | **4** (nMov = 22, 15, 31, 7) |

10 contre-exemples. La prémisse est morte. En revanche l'invariant du modèle CORRIGÉ tient :
sur les 58 chunks comparés, **la destination native est toujours dans `{origine} ∪ aiMovableTiles`**
(0 violation), et `aiMovableTiles` ne contient jamais l'origine (0/69).

### 1.3 Ce que devient la mesure S3 de `case-128`

`case-128` §5 concluait : « l'argmax du port en retirant le seul candidat *tuile d'origine* = exactement
l'action native ». La coïncidence numérique est réelle, **le mécanisme invoqué ne l'est pas** : le
natif n'exclut pas l'origine. La divergence S3 (`C4_02`, `emperNoiseMarine`, natif `69 tgt=77 to=(3,3)`
u=39.961 contre port `69 tgt=79 to=(2,2)` u=41.886) n'est PAS un tie — l'écart est de 1.925 — donc
l'ordre de sweep ne l'explique pas non plus. **Elle reste OUVERTE**, et son étage suspect est nommé
au §5 ci-dessous.

---

## 2. Le vrai défaut du port : l'ORDRE, pas l'appartenance

`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` seede le
premier ajouté et ne remplace que sur `>` **STRICT** (keep-first au tie). Comme la position courante
est énumérée **en tête**, **à utilité ÉGALE le natif reste sur place** ; il ne bouge que sur un gain
strict.

Le port balayait ses positions dans deux ordres, tous deux faux sur ce point :

| consommateur | ordre AVANT | conséquence |
|---|---|---|
| `engine/ai/context.py::build` -> `reach_nc` (toute la couche NonComparable) | tuiles de move **puis** origine | à utilité égale, le port **bouge** là où le natif reste |
| `engine/ai/state_bridge.py::_plans_for_unit` (offline) | idem (origine appendée en dernier) | idem, côté 100 % offline |
| `engine/ai/action_generators.py::_best_attack` | ordre `ranked` du plan (`GetBestTileToAttackFrom`) | rang de l'origine **arbitraire** — on gagnait/perdait « attaquer sans bouger » par chance |

C'est exactement ce que `noncomparable._base._sweep_origin_first` observait live (#76, deathRotbone
`RevitalizingMalignancy`) et corrigeait **localement** pour les self-cast. Le décompilé montre que ce
n'était pas une exception self-cast : c'est l'ordre natif, pour tout le monde.

### Contre-exemple mesuré (le plus net)

`C3_01` / seed 31337, pas 11, `spaceStormcaller` u89 en (2,3), 10 tuiles de move :
`StormcallerPlaybook` a une utilité **position-INDÉPENDANTE** (elle compte les unités dans la zone de
glace autour de la CIBLE), donc toutes ses positions légales sont à égalité et seul l'ordre tranche.

- natif : `1113 tgt=79`, **sans bouger** (reste en (2,3)) ;
- port AVANT : `1113 tgt=79`, mais **déplacement vers (2,4)** = la 1re tuile de move.

L'`ability` matchait — le miss était invisible dans la métrique historique.

---

## 3. Ce qui a été porté

1. **`engine/ai/context.py::action_tiles_for`** — mirror nommé de la liste `tiles` du tactic :
   `[origine] + tuiles de move` (origine en tête ; `[]` sans position, cas Machine of War où
   `DefaultMachineTactic` passe `NullPosition()` + `new OrderedSet()`). Docstring = la chaîne native
   complète et les deux discriminants du §1.1.
2. **`AiDecisionContext.action_tiles`** (nouveau champ) posé par `context.build`,
   `context.build_machine` et `state_bridge.build_from_state`. **`reach_nc` en devient l'ALIAS**
   (c'est le même objet natif) — l'ordre des tuiles de move est INCHANGÉ, seule l'origine passe en
   tête.
3. **`state_bridge._plans_for_unit`** — origine en tête de `cand_tiles`. Elle **reste** dans le plan :
   `plans` sert aussi d'oracle géométrique (« d'où l'attaque est-elle légale ») à
   `_get_num_attack_targets_in_position` (TheQuickening), `hammer_of_wrath`, `holy_duel`, et la couture
   LIVE fait pareil (`projection.ts::computeAttackPlans` ajoute la `mainTile` au set avant de ranker).
   L'en retirer aurait été le fork symétrique.
4. **`action_generators.ComparableAbilityGenerator._best_attack`** — sweep de position = **origine
   d'abord (si l'attaque y est légale), puis les tuiles `ranked` dans leur ordre**. `ctx.action_tiles`
   n'est PAS consommé ici : seul le rang de l'origine est imposé (cf. « portée limitée » ci-dessous).
5. **`engine_validate.run_agreement`** — nouveau compteur **`stay`** : quand le natif agit SANS
   bouger, le moteur propose-t-il un déplacement ? Cf. §4.
6. Commentaires REFAITS là où ils portaient le mécanisme réfuté :
   `noncomparable/_base.py` (`_sweep_origin_first` devient l'identité, `_PlanTargetPlaybook`),
   `noncomparable/nova_shield.py` (la note `[UNVERIFIED]` « TILE-target ⇒ origine-LAST » est retirée).

### Portée volontairement limitée à ce qui est PROUVÉ

L'ordre **relatif des tuiles de move** n'est PAS porté. Le natif les tire de
`MovementQuery$$GetMovablePositionsFor` -> `GetMovableTilesFor` -> `ExceptWith(IterateTiles(unit))` ->
`GetMovablePositionsFromTiles(tiles, feetCount)` : rien ne garantit que ce soit l'ordre de
`aiMovableTiles`. **L'imposer a été mesuré RÉGRESSIF** (`C4_09`/999 : pos exact 15/20 -> 14/20 ;
pas 14, tie 192.851 entre deux tuiles de move, le natif prend (4,4) = la 1re **rankée**). Résidu R1-b,
§5.

---

### Mesure AVANT / APRÈS (4 couples, `probe_r1_agreement_matrix.py`)

Même harnais des deux côtés (`run_agreement`), fix STASHÉ pour la ligne AVANT.

| board / seed | pos exact | pos <=1hex | ability | **stay** |
|---|---|---|---|---|
| `MC1_67` / 777 | 20/20 -> 20/20 | 20/20 -> 20/20 | 20/20 -> 20/20 | 4/4 -> 4/4 |
| `C3_01` / 31337 | 17/18 -> 17/18 | 18/18 -> 18/18 | 11/14 -> 11/14 | **1/2 -> 2/2** |
| `C4_09` / 999 | 15/20 -> 15/20 | 17/20 -> 17/20 | 14/20 -> 14/20 | 4/5 -> 4/5 (miss = WarHowl, §5) |
| `MC1_67` / 2468 | 17/19 -> 17/19 | 18/19 -> 18/19 | 14/15 -> 14/15 | 3/3 -> 3/3 |

**+1 `stay`, 0 régression sur 77 chunks comparés.** L'état intermédiaire qui imposait AUSSI l'ordre
des tuiles de move (§3, « portée limitée ») donnait, lui, `C4_09`/999 pos 15/20 -> **14/20** : c'est
cette mesure qui a fait rétrécir le périmètre.

### Scénario de GÉNÉRALISATION crafté (board + roster différents des cas qui ont motivé le fix)

Board `C4_02` (marche d'élévation), seed 4242, roster EXPLICITE
`--p-units spaceStormcaller,eldarRanger --a-units astraBullgryn,eldarRanger,necroWarden
--hp-target 90000` (bataille longue -> Njal caste plusieurs fois), 30 pas.

| | pos exact | pos <=1hex | ability | **stay** |
|---|---|---|---|---|
| AVANT | 16/21 | 19/21 | 21/24 | **8/9** (miss pas 6 : natif `1113` en place en (2,2), port -> (3,3)) |
| APRÈS | 16/21 | 19/21 | 21/24 | **9/9** |

**9 chunks « agit sans bouger »** dont **8 avec un movable NON vide** (11, 19, 9, 1, 8, 9, 5, 10
tuiles) : la branche est massivement exercée, et le port la suit intégralement.

## 4. `stay` — l'angle mort que la métrique d'agreement ne voyait pas

`run_agreement` ne comparait la POSITION que si le natif avait émis un `MoveUnitMessage`
(`if nat["move"]:`). Un port qui déplace une unité que le natif laissait sur place ne comptait donc
**nulle part** : son `ability` matchait, et `pos` n'incrémentait rien. Le compteur `stay`
(`{n, match}` + records `kind == "stay"`) ferme ce trou ; `test_stay_in_place_live.py` l'assertit.

---

## 5. Résidus (ouverts, avec leur point d'ancrage)

- **R1-b — ordre relatif des tuiles de move.** Non porté (mesure régressive ci-dessus). À trancher en
  lisant `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFromTiles` (slot 4 de
  `IMovementQuery`) et l'`ExceptWith` de `GetMovablePositionsFor` : quel ordre l'`OrderedSet` porte-t-il
  réellement, et comment se compare-t-il à `GetBestTileToAttackFrom` ? Symptôme chiffré disponible :
  `C4_09`/999 pas 14 (tie 192.851, natif -> (4,4), ordre `aiMovableTiles` -> (6,4)).
- **case-128 S3 toujours ouverte.** Son explication §5 est réfutée (cf. §1.3). Piste NON explorée,
  déjà notée par `case-128` §7 : le dégât natif prédit depuis la tuile d'ORIGINE vaut
  systématiquement **×1.25** celui des autres tuiles pour la même paire (ex. (5448, 8166) contre
  (4356, 6534)) ; le port reproduit ce ×1.25 **exactement**, mais si le natif ne le paie pas dans son
  utilité d'ACTION (préview `GetAllPredictions` ≠ `MakeDamagePredictions` du playbook à cette
  position), le port sur-value l'origine — ce qui est précisément la forme de la divergence S3.
- **`WarHowl` (1106, Ragnar) — face DÉCISION non portée.** `C4_09`/999 pas 10 : le natif caste 1106
  sur lui-même sans bouger ; le moteur, faute de playbook, retombe sur une attaque depuis une tuile de
  move. `stay` 4/5 sur ce couple, **avant comme après** — indépendant de R1.
- Les misses d'ability pré-existants de `C3_01`/31337 (pas 6 `1027`, 10 `1064`, 12 `1000`) et de
  `C4_09`/999 : inchangés, hors périmètre.

---

## 6. Reproduire

```
cd scripts/python
python probe_r1_origin_action_tile.py --seed 31337 --board C3_01 --steps 26
python probe_r1_agreement_matrix.py --couples MC1_67:777:24 C3_01:31337:26 C4_09:999:26 MC1_67:2468:24
python -m pytest tests/engine/test_stay_in_place_live.py tests/engine/test_playbook_live.py
```

`probe_r1_origin_action_tile` imprime, PAR ÉTAGE : (A) l'invariant natif et sa réfutation chiffrée,
(B) l'argmax d'attaque recalculé sous 3 ordres de position (`origin_first` / `origin_last` /
`rank_order`) — c'est cette section qui isole l'effet de l'ordre du reste —, (C) le critère R1
(« natif sur place, port aussi ? ») et (D) l'agreement.
