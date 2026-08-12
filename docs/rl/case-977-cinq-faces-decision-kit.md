# #977 — cinq faces DÉCISION de kit, un seul montage

`1131 JakhalStimms` (`worldJakhal`) · `1141 OverwhelmingWrath` (`worldEightbound`) ·
`1165 MightFromBelow` (`genesPatriarch`) · `1168 EntropyCannons` (`deathCrawler`, MoW) ·
`1043 ThunderousAssault` (`templSwordBrother`).

**0/5 existaient** dans l'un des quatre registres de décision au commit de départ (`git grep` sur
les cinq noms ET les cinq ids ; `PLAYBOOKS`, `REGISTRY`, `_SPECIAL_ABILITY_CLASSES`,
`BESPOKE_SELFCAST`). Les cinq porteurs sont **au pool** (4 réguliers + 1 MoW) : aucune injection
catalogue, **un seul montage** paie pour les cinq — co-injection vérifiée (5/5 porteurs, une seule
`teamId`).

Mesure : `scripts/python/probe_977_faces_decision_kit.py` ·
garde : `tests/engine/test_977_faces_decision_kit_live.py` (32 tests).

---

## 1. Les verdicts

| id | base LUE (`frida/classes.tsv`) | ce qui est porté | confrontation |
|---|---|---|---|
| 1131 | `NonComparablePlaybook\`1` | `evaluate_at` = `1 + Count(AoE)`, gate `IsDisallowedTarget` | utilité **15/15** positions, ordre `fromHere` **exact**, décision native **identique** |
| 1141 | `NonComparablePlaybook\`1` | `evaluate_at` = `Count(cibles éligibles)`, cible = `First` | utilité **24/24**, ordre **exact** (caster compris), décision **identique** |
| 1043 | `NonComparablePlaybook\`1` | deux stratégies, la 1ʳᵉ non nulle gagne, `MIN_UTILITY = -inf` | ordre **exact**, décision **identique** ; `ncEvaluate` **AVEUGLE** (§4) |
| 1165 | `ComparablePlaybook\`1` | `CalculateCasterPositionUtility` (slot +0x348) — **crochet neuf** | prédiction **4/4 bit-exacte**, terme mesuré **non nul** sur montage Decoy, décision **identique** |
| 1168 | `ComparablePlaybook\`1` | **RIEN** — forme canonique, le chemin générique EST le mirror | prédiction **4/4 bit-exacte** `(1214, 1822, 2)` |

⚠ **La base se lit dans `classes.tsv`, jamais dans le nom du `.ctor`** : ghidra étiquette les
**cinq** corps de `.ctor` `ComparablePlaybook<__Il2CppFullySharedGenericType>$$.ctor` (corps
gshared partagé qui ne fait que relayer `Playbook<T>..ctor(<id>)`), alors que trois d'entre elles
sont NonComparable.

---

## 2. `1131` — le gate a TROIS clauses, et n'en porter qu'une supprimerait l'ability

`IdunBattle.AI.Playbook.Loki.JakhalStimmsPlaybook$$IsDisallowedTarget`, relu verbatim :

```
WillNormalAttackKill(entities)                                  // la normale sure-kill la cible
  && !(nAoE > 0)                                                // le splash ne touche personne
  && (battleQuery.<slot itf 0x7f>(caster, casterTile).Count - 1) < 1   // <= 1 cible normale d'ici
```

Les trois sont **conjointes**. L'erreur naturelle — celle de `KillMaimBurn`, qui n'a QUE la
première — aurait supprimé 1131 dans presque tout régime de fin de combat : dès que Macer a deux
cibles d'attaque normale, l'ability reste proposée même sur une cible déjà condamnée.

Le set d'AoE (`JakhalStimmsAbility$$GetAdjacentTargets` =
`AdjacentUnits(<CasterTile>) & AdjacentFriends(<TargetTile>)`) est **le même** que celui que
`ExecuteBehaviour` construit — mêmes deux sélecteurs cachés (`dsl+0x50` / `dsl+0x60`), même
`TargetsSelector$$op_BitwiseAnd`. `GetAdjacentTargets` n'a **qu'un appelant** (xrefs) : ce
playbook. Les deux faces ne peuvent donc diverger que si l'une se trompe — et le port COMBAT en
avait déjà le mirror.

---

## 3. L'ORDRE du sélecteur est le VOISINAGE NATIF — et ça se mesure

`1141` ne garde que `Enumerable.First(targets)` : l'ordre **décide de la cible émise**.

`abilityTargets` publie deux vues, et elles ne sont pas interchangeables : `fromHere` est l'ordre
natif **à l'origine**, `targets` est l'**union** sur toutes les tuiles de move. Le premier jet du
port prenait l'union aux positions de move — et c'était **faux, mesurément** : 2 positions sur 6 y
désignaient une autre cible que le natif.

La règle juste était déjà écrite ailleurs, pour le même sélecteur (`CordClawPlaybook`, slot
0x41/0x42) : `AttackQuery$$GetValidTargets` **scanne les tuiles d'attaque**, donc son ordre de
sortie EST l'ordre des voisins. Re-mesuré ici sur **trois** abilities et trois origines :

| ability | origine | voisins natifs de la tuile | liste reconstruite | `fromHere` |
|---|---|---|---|---|
| 1131 | (3,4) | (3,5) (4,4) (4,3) (3,3) (2,3) (2,4) | `[86, 88, 90]` | `[86, 88, 90]` |
| 1141 | (2,5) | (2,6) (3,6) (3,5) (2,4) (1,5) (1,6) | `[86, 90, 80]` | `[86, 90, 80]` |
| 1043 | (4,3) | (4,4) (5,4) (5,3) (4,2) (3,3) (3,4) | `[88, 92]` | `[88, 92]` |

**3/3**, élément par élément. C'est ce qui autorise à appliquer la même règle aux tuiles de MOVE,
où aucune vue RPC n'existe — et qui **referme** le résidu « ordre approché hors origine ».

### Le caster self-cast entre dans le COMPTE, et il entre EN DERNIER

`1141` porte `isSelfCasting = 1`. `TargetingQuery$$GetCasterNotAddedReason` ajoute le caster aux
cibles légales **s'il reste au moins une autre cible** (`0x800 AddCasterIfAtLeastOneTarget`).
Conséquence directe sur l'utilité, qui **est** un compte : à l'origine (2,5), deux ennemis
adjacents et `ncEvaluate` rend **3**. Et son **rang** décide de la cible : `fromHere` = `[86, 90,
80]` — le caster APRÈS. L'union, elle, le place en 2ᵉ ; s'y fier faisait désigner le CASTER comme
cible en (1,5).

---

## 4. `1043` — l'oracle `ncEvaluate` est STRUCTURELLEMENT aveugle à ce playbook

C'est le seul playbook porté qui passe par
`NonComparablePlaybook<T>$$GenerateBucketWithMultipleStrategies`. Trois conséquences.

**(a) `MIN_UTILITY = -inf`, pas `0.0`.** Le `Bucket<T>..ctor` y est appelé avec **UN** argument —
la surcharge à trois écrit `this+0x10..0x18 = Nullable<Fix64> minUtility`, celle à un ne l'écrit
pas → `HasValue == false`. Et la classe **n'a aucun `.cctor`**. Le défaut `0.0` de la classe de
base Python aurait tué le playbook **en silence** : son utilité est un écart d'utilité de TUILE,
nul sur tout plateau plat.

**(b) La PREMIÈRE stratégie non nulle gagne** (`break` natif), ce n'est pas un argmax. L'`order`
(2 puis 1) ne choisit que le sous-bucket ; avec une seule action ajoutée il est **inerte** — le
port ne le modélise pas, et l'écrire ferait croire l'inverse.

**(c) Le capteur ne peut pas le voir.** `ncEvaluate` décode `Bucket+0x20`, le champ que
`Bucket$$AddAction` écrit. Or `GenerateBucketWithMultipleStrategies` passe par
`Bucket$$AddActionToBucket`, qui range l'action dans un **sous-bucket** de la `SortedList` à
`+0x28` : `+0x20` reste nul **même quand une action existe**. Mesuré : `bucket: "empty"` sur les
**23** positions, pendant que `aiDryRunAllUnits` propose
`ActiveAbilityMessage(caster=84, target=88, ability=1043)` depuis l'origine — exactement ce que le
port rend (`(88, 15.0)`, sans déplacement).

Le probe **diagnostique** cette cécité (`capteurAveugle`, établi par la conjonction « toutes les
buckets vides » + « le port score ») et rend `NON CONFRONTÉ`, jamais un écart. C'est
« l'absence d'un ÉVÉNEMENT ne prouve rien », appliqué à un capteur plutôt qu'à un événement.

### Les deux unités du `UtilityAttackCase` ne sont pas les mêmes

Piège central de ce playbook : stratégie 1 évalue `Tile(7)` **pour la CIBLE**
(`UtilityAttackCase.Base(target, …)` → `base.tile_utility_for_unit`), stratégie 2 **pour le
CASTER** sur la tuile de la cible (`base.tile_utility`). Les feuilles Tile(7) recopient ce champ
dans `UtilityMovementCase+0x10` avant `HasTrait(case.unit, …)` / `HasFaction(…)` et les comptes
d'adjacence — l'évaluer avec le mauvais kit serait un fork, pas une approximation.

---

## 5. `1165` — un crochet neuf sur un foyer partagé, et son terme est un DÉPARTAGEUR

`MightFromBelowPlaybook$$CalculateCasterPositionUtility` (slot +0x348) était **inatteignable** :
la route Comparable d'attaque ne sommait ce slot nulle part (résidu nommé de `case-27`). #977 pose
le crochet sur `ComparablePlaybook` et le somme **à son rang natif** — après le gate
`ShouldExecute`, avant la clé `0x37` puis `Tile(7)`.

L'ajout est un **no-op mesuré** : le corps de base natif est `return Fix64.op_Implicit(0)` (deux
instructions), et le test vérifie que `1165` est la **seule** entrée du registre à l'override.

Le corps :

```
Count( Tiles(UnitsWithTrait(AdjacentFriends(caster @ casterPosition), 0x41d)) ) × GetUtilityValue("MIGHTFROMBELOW_ExistingAdjacentDecoy")
```

`0x41d` = **1053** = `UnitTrait.Decoy` (ordinal LU dans `enums.tsv` ; le nom de la clé de poids le
confirme indépendamment). `GetUtilityValue` = `utilities.GetDict(0x44 = UtilityType.ActiveAbilities)
.TryGetValue(clé)`, absente → `Fix64(0)`. Sur le BC courant la clé vaut **3**.

**Le terme est un DÉPARTAGEUR, pas un moteur** : 3 points par leurre adjacent contre une utilité
de prédiction de l'ordre de **250**. Il ne décide qu'entre tuiles à dégât (quasi) égal.

### Le régime non dégénéré exige un montage

Aucun `Decoy` n'existe au départ : les deux porteurs du trait (`genesDecoy` npc, `genesSmnDecoy`
summon) doivent être **invoqués**, et le seul invocateur du build est `1179 CultDemagogue`
(`constants.unitId = genesSmnDecoy`), porté par `genesPrimus` — **une unité du pool**. Montage :
les deux Genestealer dans la même équipe, cast NATIF de 1179 par `applyAction`, puis mesure. Sans
lui, la contre-épreuve sur ce terme est **structurellement muette** (il vaut 0 partout).

Mesuré : 4 leurres vivants, terme non nul sur **9** tuiles, `cpu(3,3) = 6` (deux leurres
adjacents), et la décision native (`move (4,3)` puis `1165` sur 81) **égale** celle du port.

---

## 6. `1168` — « rien à porter » est un verdict, et il se PROUVE

`EntropyCannonsPlaybook$$MakeDamagePredictions` est la forme **canonique** : `GetDamage`
(corps dédupliqué `VigilanceEternalAbility$$GetDamage` = `MinMaxDamage(state, FALSE)`),
`AActiveAbility$$GetHits` (= `GetNumberConstant(0x2f = nrOfHits)`), `AActiveAbility$$GetDamageProfile`
(= la config), puis `GenerateMultiHitAttackPredictions`. Aucune entrée n'est surchargée, et 1168
figure **déjà** dans `_PREDICTION_MINMAX_RANDOM_READ` — la famille (b), lue et confirmée, qui
coïncide avec le défaut.

⚠ **`probe_909` le compte comme « non porté » par construction** : il classe par « la classe a un
corps `MakeDamagePredictions` », or la base générique est **abstraite** — *toute* classe Comparable
en a un. Ce bucket surcompte donc structurellement.

La garde prouve le verdict au lieu de le supposer : 4 cibles bit-exactes `(1214, 1822, 2)`, **et**
un test qui rougit si 1168 gagnait un jour une entrée de registre ou un override d'entrée.

⚠ Deux pièges de MESURE, tous deux mordus : une MoW porte **trois** ids (`id` / `machineId` /
`casterId`) et `aiPlaybookPredict` ne répond que sur **`casterId`** (« unit 75 not found » sur
`id`) ; et elle est **absente d'`observeBattle.units`** (canal `decisionView.mows`) — la chercher
dans le seul premier canal aurait rendu un « porteur absent » FAUX.

---

## 7. Le déplacement, foyer partagé

`Playbook<T>$$GetPushableTiles` et `Playbook<T>$$GetTargetUtilityDiffOnDisplace` vivent sur la base
générique `Playbook\`1` : `1004 MortisRound` (Comparable) et `1043` (NonComparable) les appellent
**à l'identique**. Ils étaient portés en un exemplaire, INLINE dans
`MortisRoundPlaybook.calculate_custom_utility`. #977 les **déplace** vers
`playbook/displace_utility.py` (option (1) de la doctrine : le module est une feuille, aucun cycle
à fermer) plutôt que de les dupliquer — deux exemplaires libres de diverger sont exactement le
gisement que #498-r4 a fermé sur `NOT_DISPLACEABLE_TRAITS`.

Ce qui **reste** dans `MortisRound` : la troncature vers `int` (`Fix64$$op_Explicit` puis
`op_Implicit`), qui appartient à `CalculateCustomUtility` et **pas** au corps générique — `1043`
consomme la valeur brute.

---

## 8. La FORME D'IMPORT décide si une contre-épreuve mord — mesuré deux fois ici

Deux mutations d'ordre sur `1141` et une mutation de prédicat de trait sur `1165` sont sorties
**MUETTES** au premier passage. Cause unique, et c'est celle que le `CLAUDE.md` décrit :
`from ._targets import eligible_units_at_position` (**forme A**) gèle la liaison au chargement, donc
substituer le foyer ne mord pas. Passés en **forme B** (`from . import _targets as _T`,
`from ..entities.traits import unit_trait as _UT`), les **trois** mordent.

Bilan des 11 contre-épreuves : **9 MORDANTES**, 2 muettes **déclarées** et comptabilisées par un
test dédié (si l'une se met à mordre, la garde rougit et force à relire les résidus).

---

## 9. Résidus

* **`#977-r1`** — `battleQuery.<slot itf 0xb>` de `GetHighestTileUtilityUnitCanMoveTo` est
  approximé par `ctx.reach_nc` (position courante **+** tuiles de move = le slot `0xe`
  `GetCurrentAndMovablePositionsFor`). Le nom natif dit « can move to », donc `0xb` est
  probablement le movable SEUL. L'écart ne mord que si l'ORIGINE porte strictement la plus haute
  utilité de tuile ; il rend alors `highest` trop grand, donc la stratégie 2 trop sévère.
  Direction NOMMÉE : **restrictive**.
* **`#977-r3`** — la **stratégie 2** de `1043` n'est exercée par aucun montage trouvé : la
  stratégie 1 rend une action à chaque position où l'ability est légale (l'arc arrière est non
  vide et l'écart de tuile positif). Deux contre-épreuves en restent muettes.
* **`#977-r4`** — corollaire : `MIN_UTILITY = -inf` n'est pas exercé dans son régime décisif (une
  utilité `<= 0`). La mutation `20.0` prouve que le champ est **lu** ; la mutation `0.0`, elle,
  reste muette.
* **`#977-r5`** — **conséquence OFFLINE de l'inscription au registre NC, mesurée** : dès qu'une
  ability entre dans `noncomparable.PLAYBOOKS`, `state_bridge._is_attack_ability` rend `False` et
  `_ability_kind` passe de `enemy` à `self`. Les trois NC de ce lot rejoignent donc le régime
  **déjà en place** pour `1132 KillMaimBurn`, `1122 CordClaw`, `1202 VigilanceEternal`,
  `1163 BlackRage` : elles disparaissent des `attackPlans` OFFLINE et leur face décision n'existe
  plus que LIVE. Ce n'est pas une régression introduite ici — c'est une propriété structurelle du
  routage, qu'il faut nommer plutôt que découvrir.

Numéros **réservés et non utilisés** (allocation via `probe_468 --suggere`, pas de `--liberer`) :
`#977-r6`.
