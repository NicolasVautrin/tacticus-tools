# case-305 — `MassDriverAcceleratorPlaybook$$MakeDamagePredictions` : le splash par ennemi adjacent à la cible

Résidu **N15** (ouvert par #27-r1, `port-residuals-inventory.md` §4.a) — **FERMÉ**.

L'ability **1222 `MassDriverAccelerator`** (`votanChampion` « Kimm », hero hors pool) prédisait un
seul event de dégât côté port : celui de la cible. Le natif en émet **un de plus par ennemi du
caster adjacent à la cible**, avec un **autre profil de dégât**. L'IA sous-évaluait donc la charge
exactement dans la situation où elle vaut le plus : une cible entourée.

---

## 1. L'artefact natif, étage par étage

`IdunBattle.AI.Playbook.Loki.MassDriverAcceleratorPlaybook$$MakeDamagePredictions(caster,
casterPosition, target, abilityState)` enchaîne **deux** batchs
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
et concatène le second dans la liste du premier :

```
damage = <GetDamage>                            // AActiveAbility$$MinMaxDamage(state, isPrediction: false)
list   = GenerateMultiHitAttackPredictions(caster, casterPosition, target, <Target>,
             damage, AActiveAbility$$GetHits, Nullable(AActiveAbility$$GetDamageProfile), null, 0)
foreach (e in <GetAdjacentAttackTargets>.Select(AbilityEntities(caster: caster, target: target)))
    list.AddRange( GenerateMultiHitAttackPredictions(caster, casterPosition, e,
                       DSLSelectors$$Entity(e), damage, AActiveAbility$$GetHits2,
                       Nullable(AActiveAbility$$GetDamageProfile2), null, 0) )
return list;
```

Le SET :
`IdunBattleLogic.Entities.Abilities.Active.Loki.MassDriverAcceleratorAbility$$GetAdjacentAttackTargets`
= `Enemies(DSLSelectors+0x48 = caster, AdjacentUnits(DSLSelectors+0x60 = target, unique: 1, sel: 3), 3)`
— les **ennemis du caster** posés sur les tuiles **adjacentes à la cible** (la cible elle-même est
déjà retirée par `AdjacentUnits`). C'est le **même artefact que la face COMBAT** :
`...MassDriverAcceleratorAbility$$ExecuteBehaviour` ré-inline `Enemies(caster@0x48,
AdjacentUnits(target@0x60, 1, 3), 3)`, le passe à `DSLSelectors$$Cache` / `DSLBehaviors$$SetCache`,
puis attaque `DSLSelectors$$Alive(<cache>)` avec son second `DSLBehaviors$$AttackWithAttackDamage`.

### Trois lectures que le décompilé impose

1. **Le splash porte sur l'ENNEMI ADJACENT, pas sur la cible principale.** `param_5` est
   `IdunBattleLogic.Entities.DSLSelectors$$Entity(<entité itérée>)`, un sélecteur mono-entité
   reconstruit à chaque tour de boucle — alors que
   `IdunBattle.AI.Playbook.Loki.StikkbombPlaybook$$MakeDamagePredictions` et
   `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility` repassent, eux, le
   sélecteur `Target` (d'où leur quirk « n events identiques sur la cible principale », porté par
   `prediction.make_secondary_multihit_event`). `GenerateMultiHitAttackPredictions` le confirme
   étage par étage : `param_4` ne sert qu'à peupler l'`AbilityEntities`
   (`Target` + `EntityExtensions$$GetTiles(param_4)`), et **les cibles réellement prédites sont
   celles que rend `SelectUniqueUnits(param_5, entities, 3)`**, chacune passée au slot
   `PredictAttack` avec ses propres PV / armure / traits.
2. **Le dégât du splash est celui du batch PRINCIPAL, pas `MinMaxDamage2`.** Le playbook évalue
   `<GetDamage>` = `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(abilityState,
   isPrediction: false)` **une seule fois**, dans une locale, et repasse cette locale en `param_6`
   aux deux batchs. La face COMBAT, elle, appelle bien `MinMaxDamage2` pour son second
   `AttackWithAttackDamage` — c'est une divergence natif/natif entre décision et exécution. Elle est
   sans conséquence numérique sur cette config (`minDmg_2`/`maxDmg_2` y sont égaux à
   `minDmg`/`maxDmg`), mais l'écrire explicitement évite de re-dériver la base du splash depuis
   `minDmg_2`, ce qui serait faux dès qu'un build les désaccorderait.
3. **Seuls les COUPS et le PROFIL diffèrent entre les deux batchs** :
   `AActiveAbility$$GetHits2` = `GetNumberConstant(0x32 = nrOfHits_2)` et
   `AActiveAbility$$GetDamageProfile2` = `AbilityConfiguration$$GetDamageProfile2` =
   `GetEnumConstant(0x3f = damageProfile_2)`.

`param_10` (fournisseur de poids `Fix64`) vaut **0** sur les deux batchs ⇒ `Fix64.FromInt(1)`, donc
aucune pondération `GetMaxSecondaryTargets`.

### Ce qui rend le volet observable — et ce n'est pas les coups

Config 1222 : `nrOfHits` = `nrOfHits_2` = **1**, `minDmg_2`/`maxDmg_2` **égaux** à `minDmg`/`maxDmg`.
Le volet ne se distingue donc ni par les coups ni par la base. Le seul discriminant de valeur est le
**profil** : `damageProfile` = `DirectDamage` (**PiercingRatio 100**) contre `damageProfile_2` =
`Physical` (**PiercingRatio 1**). Contre une cible blindée, les deux profils s'écartent d'autant
plus que l'armure est haute — d'où `--armor-target` haut dans le montage.

---

## 2. Le port

Le volet passe par le **chemin générique** (`prediction.make_damage_predictions` → `get_aoe_targets`
+ `aoe_overrides`), donc `MassDriverAcceleratorPlaybook` n'a **aucun** `make_damage_predictions`
propre. Trois foyers, chacun mirror d'un morceau natif distinct :

| Foyer | Ce qu'il porte |
|---|---|
| `engine/entities/abilities/active_ability.py::MassDriverAcceleratorAbility` | le SET — `_AOE = dsl.AdjacentEnemies(dsl.TargetTile(), dsl.Const(1))` = `GetAdjacentAttackTargets`. Le référent d'équipe de `Enemies` est le caster, ce que `AdjacentEnemies` mirrore par construction. Le filtre VIVANT n'est pas un nœud : il vient de `Units(...)` (`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`, occupation de tuile), déjà mirroré par `_within` (#57m) — d'où `AdjacentEnemies` **nu**. |
| `engine/playbook/prediction/abilities.py::_mass_driver_accelerator_inputs` | les entrées per-batch : `hits_override = nrOfHits` (batch principal, littéral) et `aoe_overrides = {hits_override: nrOfHits_2, profile_override: damageProfile_2}` (batch splash). La **base n'est pas surchargée** : elle est héritée du batch principal — mirror exact du `param_6` partagé. |
| `engine/playbook/loki_custom.py::MassDriverAcceleratorPlaybook` | inchangé (le terme `CalculateCustomUtility` reste le no-op de #27-r1) ; sa docstring pointe désormais les deux foyers ci-dessus. |

`hits_override` du batch **principal** : `AActiveAbility$$GetHits` est `GetNumberConstant(0x2f)`
**littéral**, alors que le chemin générique passe par `ab.get_special_hits` =
`GetDefaultAttackHits(nrOfHits, ExtraHits[, Melee])`, qui **ajoute la stat `ExtraHits` du caster**.
Même écart et même correctif que `_stikkbomb_inputs`. Sans `ExtraHits` les deux coïncident.

---

## 3. Confrontation live

Montage : `probe_305_massdriver_splash.py` (hérite de `MDA_FIXTURE`, seed BC augmentée par
`catalog_inject`). Kimm **jamais déplacée** (un `act move` consomme son mouvement et rend 1222
illégale) ; cible à distance hex 2 ; **deux ennemis supplémentaires** qui sont le levier :
bras `n = 0` (tous deux loin), `n = 1`, `n = 2`. Appâts alliés et porteurs d'aura de dégât figés
loin dans tous les bras ; la tuile d'attaque réservée par la géométrie reste libre.

Les deux ennemis-leviers portent des **armures distinctes** (`--unit-stat`). Ce n'est pas du confort
d'affichage : avec l'armure uniforme de `--armor-target`, leurs deux events sortent avec des bornes
identiques, et un port qui prédirait le splash contre la **mauvaise entité** passerait sur les
valeurs pour n'être attrapé que par le `targetId`.

Oracle : `aiPlaybookPredict` (= `<Ability>Playbook.MakeDamagePredictions` natif) depuis chaque tuile
d'attaque rankée. Confrontation de **tous** les events, par `targetId` :
`appliedHits`, `healthDmgMin/Max`, `rawHealthDmgMin/Max`.

### Verdicts, sur trois montages

| Montage | V1 exercice | V2 accord | V3 mutation SET | V4 mutation PROFIL | V5 contraste |
|---|---|---|---|---|---|
| `MC1_67` / 909 / armure 3000 | 1+n events, bonnes cibles | **MATCH 3/3 bras** | DELTA dès n=1 | DELTA dès n=1 | oui |
| `C4_09` / 31337 / armure 2000 | idem | **MATCH 3/3 bras** | DELTA dès n=1 | DELTA dès n=1 | oui |
| `MC1_67` / 909 / `--splash-hp 900` | idem | **MATCH 3/3 bras** | DELTA dès n=1 | DELTA dès n=1 | oui |

Bornes natives mesurées (`MC1_67`, armure cible 3000, leviers 1200 / 5200) :

| event | profil | armure de la cible | `raw` natif | `raw` porté |
|---|---|---|---|---|
| principal (cible) | `DirectDamage` (pierce 100) | 3000 | `[5385, 8078]` | `[5385, 8078]` |
| splash (levier 1) | `Physical` (pierce 1) | 1200 | `[3135, 5828]` | `[3135, 5828]` |
| splash (levier 2) | `Physical` (pierce 1) | 5200 | `[54, 81]` | `[54, 81]` |

Les deux mutations **débordent zéro** : elles laissent le bras `n = 0` d'accord (le volet y est
inerte) et ne cassent que les bras où un ennemi est adjacent. C'est ce qui distingue « le volet est
porté » de « le port ajoute un event de trop ».

Garde committée : `tests/engine/test_mass_driver_splash_prediction_live.py` (5 tests).

---

## 4. Le trou de harnais traité au passage

`MDA.build_fixture` lançait `rl_duel build` avec `check=False` **et** `stdout=DEVNULL`, puis relisait
le `--state-file`. **Un build refusé ne levait donc rien** : le state-file gardait l'ancien
`runnerId` et l'appelant mesurait un bras qu'il croyait neuf en rendant, à la ligne près, les
chiffres du bras précédent (vécu sur `--board C2_19`, 3 spawns joueur < 5 unités). #322 avait durci
**son** appelant (`probe_312.build_arm`) ; la fixture **partagée** restait permissive, donc tout
nouveau montage la ré-héritait — celui-ci compris.

La fixture exige désormais un **runner neuf** à chaque build et **remonte la sortie du builder**. Un
échec rendu ne peut plus se lire comme une mesure.

Deux extensions de la même fixture, requises par ce montage et réutilisables :
`a_units` / `extra_args` (roster adverse et options `rl_duel build`), et `derive=True` qui force la
géométrie dérivée. Ce dernier n'est pas cosmétique : les tuiles figées de `_geom_ref()` supposent le
roster de référence, et une unité ajoutée peut spawner exactement dessus — mesuré, `ultraTitus`
spawne en `(6,7)`, le `aura_far` figé, donc `act move` refusé et aucun bras monté. `derive_geometry`
exclut désormais les tuiles occupées par les unités que la fixture ne pilote pas.

---

## 5. Ce qui n'est PAS couvert

- **Caster portant `ExtraHits`.** Le `hits_override` littéral du batch principal ne change rien tant
  que `ExtraHits = 0` (le régime mesuré). La branche n'est pas confrontable sur ce montage :
  `ExtraHits` est une stat runtime (effets/traits), pas un champ du seed BC, donc `--unit-stat` ne
  peut pas la poser, et aucun porteur d'`ExtraHits` ne porte 1222.
- **`MinMaxDamage` vs `MinMaxDamage2`.** La divergence décision/exécution du point 2 est
  **structurellement invisible sur cette config** (`minDmg_2` = `minDmg`). Le port suit le décompilé
  (base héritée du batch principal) ; aucun montage ne peut aujourd'hui la départager.
- **La face COMBAT de 1222** (`ExecuteBehaviour` : buff de mouvement + `MoveUnit` + double attaque)
  n'est pas portée — hors périmètre, inchangée.
- **Effet de la correction sur la DÉCISION de Kimm.** La confrontation porte sur l'étage
  PRÉDICTION. Un écart antérieur de `pairUtility(69)` (`case-312`) masque toute comparaison de
  décision complète sur ce porteur ; c'est la raison pour laquelle `case-304` mesurait déjà par
  étage, et le protocole est repris tel quel ici.
