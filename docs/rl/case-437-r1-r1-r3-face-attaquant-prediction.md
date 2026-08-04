# #437-r1-r1-r3 — la divergence prédiction/combat N'EXISTAIT PAS : c'était le montage

**VERDICT : lecture MONTAGE.** Sur les mêmes entrées d'étage, `aiPredict` rend **exactement** les
bornes du COMBAT et du PORT — `(1130, 1695)` — dès que la lecture est prise dans un état où le
coup mesuré est bien celui qu'on croit mesurer. Le `(904, 1356)` du résidu venait d'une seule
cause native, `IdunBattle.Entities.UnitExtensions$$SetMovedFlag`, atteinte par deux chemins.

## 1. Le critère, posé AVANT de mesurer

*Dans l'état exact où la lecture rend `(904, 1356)`, la face ATTAQUANT `HeavyWeapon_ExtraDmg`
est-elle non neutre pour le COMBAT ?*

* **MONTAGE** — elle est neutre : le combat sur ce même état rend aussi `(904, 1356)`, aucun
  modèle ne diverge.
* **RÉELLE** — elle est vivante et seule la prédiction l'ignore : il faut alors remonter à
  l'appelant natif qui construit les `Nullable<DamageModifiers>`.

Ce qui aurait fait conclure l'inverse : que la prédiction reste à `(904, 1356)` **en portée et
attaquant non déplacé**. Elle ne l'est pas.

## 2. La mesure qui tranche — un seul run, attaquant JAMAIS déplacé

`probe_437r1r3_prediction_attacker_face.py`, board `MC1_67`, seed 4321, `eldarRanger` (overwatcher,
trait `HeavyWeapon`) contre `spaceStormcaller` (`TerminatorArmour`). Le seul paramètre qui varie
d'une ligne à l'autre est la position de la **CIBLE**.

| distance | `abilityTargets(...).fromHere` contient la cible | `aiPredict` |
|---|---|---|
| 5 | **non** | `(904, 1356)` = `Round(P x 0.25)` |
| 3 | **oui** | **`(1130, 1695)`** |

Au même instant, entrées d'étage lues par instrumentation du foyer réel : base `3614 / 5422`,
perçage 30, armure 0, `pct_att = [1.25]`, `pct_def = [0.25]`, bornes du PORT `(1130, 1695)`.
Tir réel déclenché depuis cet état : natif **1475**, port **1475**.

**Généralisation aux trois bases de #437-r1** (`--dmg-target`), `aiPredict` EN PORTÉE contre les
bornes natives que #437-r1 avait obtenues par inversion du COMBAT :

| base d'attaque | bornes brutes | `aiPredict` HORS portée | `aiPredict` EN portée | bornes natives #437-r1 |
|---|---|---|---|---|
| 4518 | 3614 / 5422 | (904, 1356) | **(1130, 1695)** | (1130, 1695) |
| 4526 | 3621 / 5431 | (905, 1358) | **(1132, 1697)** | (1132, 1697) |
| 4538 | 3630 / 5446 | (908, 1362) | **(1135, 1702)** | (1135, 1702) |

3/3, **dont 4538, la cellule DISCRIMINANTE** de #437-r1 (le modèle « chaîne unique » y donnerait
1134). ⇒ **la voie PRÉDICTION confirme la loi « un `Round` par face », indépendamment de
l'inversion PRNG.** C'est un second canal sur le résultat de #437-r1, qui ne reposait jusqu'ici
que sur l'inversion.

Hors portée, les six valeurs sont **exactement** `Round(P x 0.25)` : face attaquant strictement
neutre, face défenseur intacte, **un seul** `Round`.

## 3. Contre-épreuve — le gate `Moved` est un SECOND chemin, et il MORD

Vert est le résultat suspect : il fallait vérifier que la garde change bien quelque chose, et que
`inRange` n'est pas à lui seul suffisant. Mode `--attacker-moves` : depuis l'état EN PORTÉE déjà
mesuré, l'ATTAQUANT fait **un pas qui conserve la distance** (3 → 3).

```
d_before=3  d_after=3  inRange=true  armour=[true, true]
ow_effs=["HeavyWeapon_ExtraDmg", "WireweaveNet_CounterAttack", "Overwatch_AutoAttack"]
pred = (904, 1356)          <- etait (1130, 1695) au pas precedent
```

**L'effet est TOUJOURS POSÉ et son bonus ne mord plus.** C'est la mesure directe de ce que
#437-r1-r1 §5 inférait, et elle établit que *« `HeavyWeapon_ExtraDmg` est dans les effets »* ne
prouve **rien** sur la face attaquant.

## 4. Le mécanisme, au décompilé — UNE seule cause

`IdunBattle.Core.Services.DamagePredictionQuery$$GetAllPredictions` remplit son dictionnaire en
**deux régimes**, lus verbatim (`rnca9r7q6c`) :

* `GetPredictionForTargetsReachableFromSelectionTile` — pour les cibles valides **depuis la tuile
  de sélection**, prédiction calculée à `UnitPosition(possibleAttackerTile)` ; ces cibles sont
  ensuite **RETIRÉES** de `possibleTargets`, donc le second régime ne peut plus les toucher ;
* `GetPredictionForTargetsUnreachableFromSelectionTile` — pour les autres : boucle sur
  `moveableTiles`, prédiction à `UnitPosition(<tuile du movable set>)`, arbitrage par
  `BetterDamagePrediction`.

Et une prédiction à une tuile **autre que la tuile courante** passe par
`IdunBattle.Operations.SimulateEffectsOperation$$DoActionInSimulatedTile`, qui appelle le **même**
`IdunBattle.Entities.UnitExtensions$$SetMovedFlag` que `MoveUnitOperation$$Execute` (RE déjà au
dossier : `engine/playbook/prediction/_shared.py::prediction_has_moved`, #266). Le gate
`!HasFlag(Moved)` de
`IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` tombe donc.

⇒ **Les deux pièges n'en font qu'un** : `Moved` **réel** quand l'attaquant a marché (`--bounds`),
`Moved` **simulé** quand la lecture est hors portée (`--predict-2faces`). Dans les deux cas la
prédiction native et le combat natif sont **d'accord entre eux** — ils décrivent simplement un
autre coup que celui qu'on croyait lire.

Le trigger complet de l'effet, lu verbatim :

```
cond = OwnerIsCaster & IsRangedAttack
     & ( (T@0x28 & !HasFlag(Self, 3)) | !T@0x28 )
     & ( !HasFlag(Self, 0 = Moved) | HasFlag(Self, 0xc = Teleported) )
amount = ConditionalAmount(TriggeringAbilityIs(self), base x2, base)
```

## 5. Ce que ça ferme, et ce que ça ne ferme pas

* **`#437-r1-r1-r3` est FERMÉ.** Il n'y a pas de divergence de modèle entre les vecteurs
  PRÉDICTION et COMBAT sur ce régime.
* **La piste au dossier est ÉCARTÉE POUR CE RÉSIDU** : « `DamagePrediction$$CalculateAbilityDamage`
  passe `attackModifiers` NULL » reste vraie pour *cet appelant-là*, mais `aiPredict` ne passe pas
  par lui — il descend `PredictAttack` → `PredictAttackRaw`, qui construit bien ses **deux**
  `Nullable<DamageModifiers>` (deux `System.Nullable..ctor` sur le même type juste avant chacun
  des deux `CalculateBaseDamageWithAllModifiers`).
* **AUCUN changement de `engine/`** n'est requis : le port lit déjà `has_moved` du flag natif côté
  COMBAT (`damage_model.attacker_modifiers`) et applique déjà la règle
  `has_moved = (attack_pos != position courante) OR HasFlag(Moved)` côté PRÉDICTION
  (`prediction_has_moved`). Les trois bases ci-dessus le confirment à l'unité.
* **NON COUVERT, nommé** : `BetterDamagePrediction` — l'arbitrage entre les tuiles du movable set
  n'a pas été RE ni mesuré. Il ne change rien au verdict (le régime en portée ne l'emprunte pas),
  mais tout futur usage d'`aiPredict` hors portée en dépend.

## 6. Livré

* `scripts/python/probe_437r1r3_prediction_attacker_face.py` — sweep par distance avec la garde
  `fromHere`, contre-épreuve `--attacker-moves`, tir réel `--shot` + inversion.
* `scripts/python/probe_437r1_overwatch_offbyone.py` — `--predict-2faces` **réparé** : garde EN
  PORTÉE obligatoire + approche en deux phases. Il rend désormais `1130 / 1695`.

## 7. Note de session

Mesures rejouées après la fenêtre de reinject #6 (session Frida 4, correctif `readAbilityState`
sur la lecture des `Nullable<T>`) : **aucun chiffre n'a bougé** sur cet axe. `(904, 1356)` hors
portée et les entrées d'étage sont identiques en session 3 et en session 4 — le canal lu ici est
`readDamagePredictionResult`, pas `readAbilityState`.
