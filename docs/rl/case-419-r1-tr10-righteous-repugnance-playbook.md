# #419-r1-tr10 — `RighteousRepugnancePlaybook` (1107), tête du filon ATTACK

Dixième tranche des résidus ATTACK de `#419-r1`, et tête de liste par nombre de porteurs.
Porteur naturel : **`adeptMorvenn` « Morvenn Vahl », HERO AU POOL** — vérifié par
`rl_duel build --list-pool` (97 unités régulières, rank 17), pas par `kind == lineup`. Aucune
injection de catalogue, aucune greffe, aucun montage de relique.

## 1. L'inventaire des artefacts — `1107` en recouvre PLUSIEURS, et deux vivent sous `1182`

C'est le piège récurrent de ce filon, établi avant toute lecture de corps :

| enum QUALIFIÉ | artefact natif | statut |
|---|---|---|
| `TriggeredAbilityType.RighteousRepugnance = 1107` | `IdunBattle.AI.Playbook.Loki.RighteousRepugnancePlaybook` + `IdunBattleLogic.Entities.Abilities.Triggered.Loki.RighteousRepugnanceAbility` | **CETTE tranche** |
| `ActiveAbilityType.Reveal = 1107` | sans rapport | — |
| `EffectType.PathOfCommand_ExtraCrit = 1107` | axe CRIT d'un effet | traité ailleurs |
| `ActiveAbilityType.RighteousRepugnance_NormalAttack = **1182**` | `RighteousRepugnance_NormalAttackAbility$$PredictAttack` / `$$GetAdditionalDamagePrediction` (le **mold** d'attaque normale) | porté #446-r3, corrigé #509 |
| — (même 1182) | `IdunBattle.AI.Playbook.Loki.RighteousRepugnance_NormalAttackPlaybook` | le playbook de l'ability ACTIVE, **non** celui-ci |
| `TriggeredAbilityType.SagaOfTheWarriorBorn = 1182` | homonyme inverse du couple ci-dessus | — |

Le mold `1182` et ce playbook `1107` sont **deux artefacts que rien ne partage** : le premier
ajoute du dégât à la prédiction de l'attaque normale contre la cible ; le second chiffre, pour
l'IA, **combien d'unités supplémentaires** cette attaque va toucher.

## 2. Le corps natif

`RighteousRepugnancePlaybook$$CalculateAttackUtilityInStepsInternal` monte la SM `d__3` — sa
disposition est **LUE dans ce wrapper**, et elle est l'**INVERSE** de celle de `CosmicHorror` /
`Boltstorm` sur les deux premiers champs : `sm@+0x20 = this` (le PLAYBOOK), `sm@+0x28 = case`,
`sm@+0x30 = getUtilityVal`. Corps
`RighteousRepugnancePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`,
**UN SEUL** `yield` :

```csharp
var sel = RighteousRepugnanceAbility.GetAdditionalTargets(this.<DSL>);
var entities = new AbilityEntities { Caster = case.Caster,     // memset 0x128 a 0 d'abord
                                     Target = case.Target };   // Actor ET Owner restent NULS
yield return Fix64.op_Implicit(GetUtilityValue("RIGHTEOUSREPUGNANCE_AdjacentEnemy")
                               * sel.SelectUniqueUnits(entities, (UnitSelectionType)3).Count);
```

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RighteousRepugnanceAbility$$GetAdditionalTargets` :

```
  AdjacentEnemies(dsl.Selectors, Caster@0x48, unique: 1, selectionType: 3)
& AdjacentUnits  (dsl.Selectors, Target@0x60, unique: 1, selectionType: 3)
```

et, en développant les deux primitives `IdunBattleLogic.Entities.DSLSelectors` (lues aussi) :

```
AdjacentEnemies(u) = Enemies(u, Units(AdjacentTiles(u), ...) - u, sel)
AdjacentUnits(o)   =           Units(AdjacentTiles(o), ...) - o
```

soit : **les ennemis du caster, adjacents À LA FOIS au caster et à la cible** — littéralement le
texte i2 du passif (« all enemy units adjacent to both the target and to Morvenn Vahl »).

## 3. Six lectures qui ne se devinent pas

1. **Même FORME que `Boltstorm` (produit poids × cardinal), PAS le même cardinal.** L'arbre d'ici
   n'a **aucun `op_Addition` avec `Target@0x60`** : la cible principale n'est jamais comptée, et
   une cible isolée vaut **0**. Chez `Boltstorm` elle valait déjà `1 × 10`. Recopier le voisin
   aurait posé un plancher de 10 qui n'existe pas — c'est exactement ce que le mutant
   `plus_target` mesure, et il déplace le port **à chaque cran**.
2. **La double adjacence** : les deux `op_Subtraction` internes retirent respectivement le caster
   et la cible, donc ni l'un ni l'autre n'entre au compte, **sans aucun test explicite**.
3. **Le terme ne dépend PAS de la tuile d'attaque.** La struct `AbilityEntities` est `memset` à 0
   puis ne reçoit que `Caster` (`+0x08`) et `Target` (`+0x10`) : `Owner` (`+0x18`), `TargetTile`
   (`+0x30`) et `CasterTile` (`+0x40`) restent NULS, et `case.CasterPosition`
   (`UtilityAttackCase@+0x18`) n'est jamais lu — donc `AdjacentTiles` ancre sur la MainTile RÉELLE.
   ⚠ Ce corps écrit **moins** de champs que `Boltstorm`, qui posait en plus `Owner = Caster` : sans
   conséquence (l'arbre ne lit ni `Owner@0x30` ni `Actor@0x40`), mais c'est une lecture.
4. **`AdjacentTiles` est le ring-1 STRICT**, pas `AreTilesAdjacent` : foyer `battle_query.is_adjacent`
   (porte `|Δelev| < 2`), surtout pas `are_entities_adjacent`, qui porte le court-circuit d'identité
   `t1 == t2` (#433-r1) et ferait compter la cible elle-même.
5. **Le poids est LU, pas deviné** : `probe_212_bc_key_literals.py` sur le symbole du `d__3$$MoveNext`
   résout le slot `+0x33b22a0` — exactement le `DAT_` du call-site du délégué — vers
   `RIGHTEOUSREPUGNANCE_AdjacentEnemy`, **seule** clé `RIGHTEOUSREPUGNANCE_*` du BC, = **10**.
6. **Le playbook estime EXACTEMENT ce que le combat va frapper en plus.** `GetAdditionalTargets` n'a
   que **deux** appelants (xrefs mesurées) : ce `MoveNext` et
   `RighteousRepugnance_NormalAttackAbility$$ExecuteRighteousRepugnance`, qui l'enroule dans un
   `DSLBehaviors.Foreach(sel, t => GetAdditionalTargetsAttackBehavior(t, abilityState))` exécuté en
   `ExecuteAtomic`. La cible principale, absente de l'arbre, est traitée à part par
   `ExecuteNormalAttack` + le fold de #446-r3.

## 4. Face MOVE : `yield Fix64(0)` CONSTANT — décompilé LU

`RighteousRepugnancePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` a un
seul état, et cet état est `Fix64.op_Implicit(0)` ; son wrapper n'écrit NI le case NI le playbook
dans la SM. `probe_212` confirme : aucun string literal, ni là ni au `.ctor`. Elle n'entre donc pas
au registre `TRIGGERED_MOVE_PLAYBOOKS`, et cette absence **EST** le comportement natif — même forme
que `Lakrimae`, `BarbedOvipositor`, `Neuroparasite`, `Boltstorm`, `FireOfAbsolution` et
`CosmicHorror`.

## 5. Mesure — six crans, accord ABSOLU exact

`MC1_67` / seed `41504`, caster `u83` @ `(3,4)`, cible `astraBullgryn` @ `(3,5)` (adjacente : c'est
la **seule** configuration dont le voisinage commun a deux tuiles, donc la seule qui installe
`count = 2`). `V1=(4,4)`, `V2=(2,4)`, témoins `W_T=(3,6)` (adjacent cible seule) et `W_C=(3,3)`
(adjacent caster seul).

| cran | ce qui bouge | cardinal | natif | port | terme porté | manque au port muté |
|---|---|---|---|---|---|---|
| `n0` | tout au garage | 0 | 13.514324 | **identique** | 0 | 0 |
| `wt` | E1 → `W_T` | 0 | 13.514324 | **identique** | 0 | 0 |
| `wc` | E1 → `W_C` | 0 | 13.514324 | **identique** | 0 | 0 |
| `n1` | E1 → `V1` | 1 | 23.514324 | **identique** | +10 | +10 |
| `n1a` | **ALLIÉ** → `V2` | 1 | 23.514324 | **identique** | +10 | +10 |
| `n2` | allié au garage, E2 → `V2` | 2 | 33.514324 | **identique** | +20 | +20 |

Écart natif/port : **6e-9** (bruit `Fix64` contre float). Le cardinal est **RE-DÉRIVÉ des positions
LIVE** avec l'adjacence NATIVE, sur **toutes** les unités de la vue — jamais lu du port ; un cran
dont le cardinal ne vaut pas l'attendu **refuse de mesurer** (`MontageError`).

Le cran `n0` est ce qui tranche le **plancher** (donc le `+ Target` de `Boltstorm`) ; le cran `n2`
ce qui tranche **produit contre poids plat** ; `wt`/`wc` la **double** adjacence ; `n1a` le filtre
de **camp**. Aucun n'est redondant, et chacun a son mutant dédié (§6).

## 6. Contre-épreuves — chaque mutant mord à SON cran, et nulle part ailleurs

Critère = **déplacement du port non muté**, jamais l'écart au natif (piège #441).

| mutant | `n0` | `wt` | `wc` | `n1` | `n1a` | `n2` |
|---|---|---|---|---|---|---|
| `flat` (poids plat) | 0 | 0 | 0 | 0 | 0 | **−10** |
| `target_only` (gate caster retiré) | 0 | **+10** | 0 | 0 | 0 | 0 |
| `caster_only` (gate cible retiré) | 0 | 0 | **+10** | 0 | 0 | 0 |
| `no_camp` (filtre `Enemies` retiré) | 0 | 0 | 0 | 0 | **+10** | 0 |
| `plus_target` (le `+ Target` de `Boltstorm`) | **+10** | **+10** | **+10** | **+10** | **+10** | **+10** |

La **réciproque** est le résultat : chaque mutant est inerte partout ailleurs, donc chaque cran
discrimine un axe précis. Un mutant qui mordrait partout ne prouverait que la sensibilité de la
mesure.

## 7. La porte d'élévation — pourquoi elle exige un montage SÉPARÉ

`no_elev_gate` (`hexgeo.distance == 1` au lieu de `bq.is_adjacent`) est **inerte** sur le montage
principal, et ce n'est **pas** un manque de board : c'est **structurel**. Deux hexs adjacents ont
exactement **deux** voisins communs, et le montage principal exige que ces deux-là soient adjacents
au sens NATIF (c'est ce qui installe `count = 2`) — il ne reste donc aucune tuile commune que
l'élévation puisse écarter. **MESURE : 0 hit sur les 779 boards de `data/boards/`.**

Le probe porte donc une **étape dédiée** (`--elev-gate`) sur un layout qui RELÂCHE `count = 2` :
parmi les deux voisins communs HEX, `G` est adjacent natif aux deux et `Z` ne l'est pas.
Sur **`C1_16`** (`C=(2,4)` élév. 2, `T=(3,5)` élév. 1, `G=(2,5)` élév. 2, `Z=(3,4)` élév. **3** —
`|1 − 3| = 2`, le natif écarte `Z` de la cible) :

| cran | E1 | cardinal | natif | port | mutant `no_elev_gate` |
|---|---|---|---|---|---|
| `elev-g` | `(2,5)` | 1 | 23.514324 | **identique** | 0 — inerte |
| `elev-z` | `(3,4)` | 0 | 13.514324 | **identique** | **+10 — MORD** |

Le résidu est donc **fermé** : les six contre-épreuves mordent.

## 8. Généralisation — un levier qui déplace tout SAUF le terme

**`C2_02` / seed `31337` / `--armor-target 3000`** : la base passe de `13.514324` à **`9.009550`**,
et le terme reste **exactement `10 × cardinal`** aux six crans, accord absolu (écart 1.1e-8). Les
cinq mutants y mordent aux mêmes crans. Le terme ne dépend donc ni du board, ni des dégâts, ni de
l'armure — ce que le décompilé dit (le corps ne lit ni stat, ni effet, ni prédiction), vérifié par
un levier qui déplace tout le reste.

> ⚠ Sur `C1_16` la base valait le **même** `13.514324` que sur `MC1_67` — coïncidence expliquée, pas
> un montage inerte : les deux layouts ont le **même delta d'élévation** caster→cible (+1) et les
> mêmes HP/armures forcés. C'est `--armor-target` qui fait bouger la base, et c'est pour ça qu'il
> est le levier de généralisation.

## 9. Livré

* `scripts/python/engine/playbook/righteous_repugnance.py` — le mirror (`count_additional_targets`
  + `RighteousRepugnancePlaybook`).
* `scripts/python/engine/playbook/psyker.py` — entrée `1107` au registre `TRIGGERED_ATTACK_PLAYBOOKS`.
* `scripts/python/probe_419r1tr10_righteous_repugnance.py` — montage attesté, six crans, six
  contre-épreuves, étape porte d'élévation, `--board`/`--seed`/`--armor-target`.
* `scripts/python/tests/engine/test_419r1tr10_righteous_repugnance_live.py` — 7 gardes.

## 10. Résidus NOMMÉS

* **`#419-r1-tr10-r1` — le régime `cardinal >= 3` est INATTEIGNABLE**, et c'est géométrique : deux
  hexs adjacents n'ont que deux voisins communs, et deux hexs à distance 2 en ont un ou deux. Le
  produit n'est donc confronté qu'à `{0, 1, 2}`. Rien ne suggère une non-linéarité (le natif
  multiplie un `int` par un `List.Count`), mais ce n'est pas mesuré.
* **`#419-r1-tr10-r2` — les unités MULTI-TUILES ne sont pas couvertes.** `AdjacentTiles` itère
  `EntityExtensions.IterateTiles(sujet)` (toutes les tuiles de l'entité) ; le port ne connaît que
  la MainTile (`scene.pos`). Sur un caster ou une cible occupant plusieurs tuiles, le voisinage
  natif serait plus large. **Montage qui le ferait** : une MACHINE OF WAR (ex. `adeptExorcist`,
  au pool MoW) en caster ou en cible, avec un ennemi sur une tuile adjacente à un pied NON principal
  — le cardinal natif devrait le compter, le port non. Le résidu est **PARTAGÉ** avec
  `boltstorm.count_all_targets` et `fire_of_absolution.count_adjacent_by_camp`, qui ont la même
  approximation.
* **`#419-r1-tr10-r3` — la face COMBAT de `GetAdditionalTargets` n'est pas portée.**
  `RighteousRepugnance_NormalAttackAbility$$ExecuteRighteousRepugnance` (le `Foreach` +
  `GetAdditionalTargetsAttackBehavior` + `ExecuteAtomic`) n'a aucun mirror dans `engine/runner` :
  un cast d'attaque normale de Morvenn ne frappe PAS les cibles additionnelles côté exécution. Même
  forme que `#419-r1-tr9-r4-r3` (`Boltstorm`). La face DÉCISION livrée ici ne dit **rien** de
  l'exécution.
* **`#419-r1-tr10-r4` — `selectionType = 3` n'est pas qualifié.** Le littéral `3` passé à
  `AdjacentEnemies` / `AdjacentUnits` / `SelectUniqueUnits` est un `UnitSelectionType` dont les
  membres n'ont pas été énumérés ; le port traite « unités vivantes occupant une tuile », ce qui est
  ce que fait le reste du port (`boltstorm`, `fire_of_absolution`) et ce que les six crans
  confirment. Un régime où `3` discriminerait autre chose (steppables, objets) n'est pas exercé.
