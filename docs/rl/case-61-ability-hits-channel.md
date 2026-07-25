# case-61 — Canal de COUPS des attaques d'ABILITY

**Statut : LIVRÉ.** Le vecteur COMBAT des attaques d'ability traverse désormais la formule de coups
partagée ; la face PRÉDICTION reste sur la base seule (verdict natif) ; `FrenziedFiring` (1036) a sa
base géométrique portée.

Artefacts : `engine/runner/operations/damage_ops.py` (`execute_ability_attack`),
`engine/services/attack_hits_formula.py`, `engine/playbook/prediction/abilities.py`
(`_frenzied_firing_inputs`), `probe_61_ability_hits.py`,
`tests/engine/runner/test_ability_hits_channel_live.py`.

---

## 1. La chaîne native

Le nombre de coups d'une attaque n'est **jamais** lu directement d'une config : il est produit par une
**base** (un nœud DSL propre à l'ability, ou le nb de coups de l'arme pour l'attaque normale) qui
traverse — ou non, selon le vecteur — une **formule commune**.

### 1.1 D'où vient la BASE

`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` construit un
`IdunBattle.Entities.Behaviours.AttackDamageBehaviour` dont le champ **+0x80** porte le nœud `hits`
(`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$.ctor`, 7e paramètre). Il existe deux surcharges
de la factory : l'une reçoit un **int** qu'elle emballe dans un nœud constant, l'autre reçoit
directement un **nœud**. `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` évalue ce
nœud et le range dans le `Nullable<int>` de l'AttackData (**+0x18** du struct passé à l'opération).

L'attaque NORMALE emprunte la même mécanique : `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetAttackDamageBehaviour`
appelle `IdunBattleLogic.Entities.DSLFactory$$AttackDamage` avec, en 6e argument, le nœud de coups
dérivé de l'arme sélectionnée.

### 1.2 Où la formule s'applique — et où elle NE s'applique PAS

| Vecteur | Fonction native | Formule interposée ? |
|---|---|---|
| COMBAT, attaque normale | `IdunBattle.Operations.AttackDamageOperation$$Execute` → `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` | **OUI** |
| COMBAT, ability famille **ATTACK** (`AttackWithAttackDamage`) | idem — **même `Execute`, même `GetAttackHits`** | **OUI** |
| COMBAT, ability famille **ABILITY** (`AttackWithAbilityDamage`) | `IdunBattle.Operations.AbilityDamageOperation$$Execute` | **NON** — lit le `Nullable<int>` et l'utilise brut (défaut 1) ; aucun appel à `GetAttackHits` |
| PRÉDICTION d'une ability | `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions` | **NON** — évalue le nœud `hits` et le passe tel quel à `PredictAttack` (slot 0x27) |

`IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` résout le slot d'interface **0xb5** et
délègue à `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`, qui calcule :

```
hits  = base + GetStat(0x11 ExtraHits) + (IsMeleeAttack ? GetStat(0x17 ExtraHitsMelee))
hits  = Math.Max(hits, 0)
        puis, sur la liste GLOBALE des effets : bonus positifs, malus négatifs (skippables par un
        flag d'immunité), clamps `Max(hits, Min(base, minValue))`, override absolu, et un flag de
        retour à la base — chacun lu par un slot virtuel sur le descripteur d'effet
hits  = Math.Max(hits, 0)
```

Cette **unique boucle** porte à la fois les bonus attaquant (`OwnerIsCaster` : LetTheGalaxyBurn,
PowerTrip, FightingRetreat_HitReduction, AstartesBanner) et les malus cible (`OwnerIsTarget` : Parry,
LightCover, Camouflage, Diminutive, BigTarget, MasterAnnihilator). Il n'y a donc **pas** deux canaux à
brancher séparément : brancher l'appel branche les deux.

`IsMeleeAttack` y est **positionnel** (`IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack`), pas
la nature déclarée de l'ability — une ability « melee » castée à distance 2 est ranged pour ce canal.

### 1.3 Court-circuit

`GetAttackHits` renvoie la base **sans formule** quand l'octet +0x28 de l'AttackData est vrai (un flag
des options du behaviour, 9e argument de la factory, celui-là même dont un autre octet porte
`alwaysOverkilled`). Aucun porteur porté ne l'arme aujourd'hui.

---

## 2. Ce que le port faisait — et ce qu'il fait

`execute_ability_attack` recevait un `hits` **fixe** et le passait directement à `_run_hits` : ni la
base (`ExtraHits`/`ExtraHitsMelee`) ni **aucun** bonus/malus du canal n'atteignaient les attaques
d'ability.

Le vecteur ability de la famille ATTACK appelle désormais `attack_hits_with_modifiers` avec
`weapon_hits = <nœud hits du DSL>`, `is_normal_attack=False`, `is_melee` **positionnel**, et le même
couple d'entrées d'état (`tile_effects_by_pos`, `persistent_data`) que la façade de l'attaque normale.
La famille ABILITY garde la base brute.

`attack_hits_with_modifiers` gagne un paramètre `is_normal_attack` : seul
`IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect$$CreateEffectHitsBonusForAttack` porte le
gate `IsNormalAttack` ; tous les autres bonus/malus du canal s'appliquent aux deux vecteurs.

`FightingRetreat_HitReductionEffect` (`IdunBattle.Entities.Effects.Loki.FightingRetreat_HitReductionEffect$$CreateEffectHitsBonusForAttack`,
trigger `OwnerIsCaster` **seul**, `ForAdditionWithMinimum(-hitsReduction, min=1)`) était déjà porté sans
gate mêlée/ranged : il devient actif sur le vecteur ability par le simple branchement du canal — aucune
ligne de plus.

---

## 3. Ground truth live

Runner isolé, board `MC1_67`, positions drivées, **une seule variable** entre les deux runs : le trait
de la cible. Oracle combat = un événement de dégât par coup appliqué
(`Active_Ability_Type` + `Target_Id`) ; oracle prédiction = `aiPlaybookPredict.appliedHits`.

`FlailSwing` (1042, `deathBlightlord`) — `constants.nrOfHits = 3`, famille ATTACK :

| Cible | COMBAT natif | COMBAT port (après) | COMBAT port (avant) | PRÉDICTION natif |
|---|---|---|---|---|
| `necroWarden` (témoin) | 3 — `[4826, 4638, 4888]` | 3 — **bit-exact** | 3 | 3 |
| `templChampion` (`Parry_ReduceHits`) | **2** | **2** | 3 (faux) | **3** |

Counterfactuel sur le même état : forcer la famille ABILITY rend **3** coups — le gate de famille est le
seul écart et il change le résultat.

`FrenziedFiring` (1036, `blackObliterator`) — `constants.nrOfHits = 1`, `maxNrOfHits = 10` :

| Géométrie de la cible | voisins marchables | natif | port (après) | port (avant) |
|---|---|---|---|---|
| plein champ, un ALLIÉ du caster sur un voisin | 6 | 7 | 7 | 1 |
| un ENNEMI du caster sur un voisin | 5 | 6 | 6 | 1 |
| bord de plateau | 4 | 5 | 5 | 1 |
| coin de plateau | 3 | 4 | 4 | 1 |

Déplacer l'allié d'un voisin à un autre ne change rien ; un cadavre sur un voisin ne compte pas comme
unité.

---

## 4. Pourquoi 1036 et 1042 divergeaient

C'est la question qui débloque le cas, et la réponse n'est **pas** le canal :

- `FlailSwing` passe `IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(0x2f)` — une
  **constante** (3). Le port la lisait déjà : natif et moteur concordaient (3 partout), donc le cas
  n'était pas discriminant.
- `FrenziedFiring` passe le nœud
  `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetHitsForOriginalTarget` :

  ```
  Min( Cache( Sum( Get(GetHits),                                    # GetNumberConstant(0x2f) = 1
                   Count( Filter( Walkable(AdjacentTiles(target)),
                                  Not(HasUnit(tile)) | Not(AreEnemies(Units(tile), caster)) ) ) ) ),
       ConfigConst(0x48 = maxNrOfHits) )
  ```

  = base **géométrique**. Le port lisait `nrOfHits` (=1) et rendait 1 partout.

Le « 4 ou 5 coups selon la cible » relevé en #87 était donc **la géométrie autour de la cible**, pas le
trait `Diminutive` : ni `Diminutive` ni `Camouflage` ne modifient la prédiction d'une ability (§1.2,
ligne PRÉDICTION), et la mesure ci-dessus le confirme cible par cible.

Le playbook natif (`IdunBattle.AI.Playbook.Loki.FrenziedFiringPlaybook$$MakeDamagePredictions`) évalue ce
nœud pour l'event de la cible principale, puis émet un **second batch** sur
`FrenziedFiringAbility$$GetTargets` (les ennemis adjacents) avec `hits = 1` littéral.

---

## 5. Reproduction

```bash
# depuis scripts/python, runner deja monte (cf. runner.md)
python probe_61_ability_hits.py both    --sid S --runner R --caster U --ability 1042 --target T
python probe_61_ability_hits.py predict --sid S --runner R --caster U --ability 1042 --targets "t1,t2"
python probe_61_ability_hits.py combat  --sid S --runner R --caster U --ability 1036 --target T
python -m pytest tests/engine/runner/test_ability_hits_channel_live.py -q
```

---

## 6. Résidus

- **Volet AoE de `FrenziedFiring`** : le second batch du playbook (`GetTargets()` = ennemis adjacents à
  la cible, `hits = 1`) n'est pas émis par le port. Axe `get_aoe_targets`, séparé de la base de coups.
- **`On(PreAttack=5)` n'est pas émis par le vecteur ability** — fidèle : le natif l'émet depuis
  `ALoki_NormalAttackAbility$$ExecuteNormalAttack`, pas depuis le chemin ability. Conséquence : sur ce
  vecteur, `LetTheGalaxyBurn` ne peut s'armer que par sa branche `TargetHasTileEffect` (le flag
  persistant 33 % reste vide). Le threading des deux entrées d'état est en place ; si une mesure montre
  un +1 par la branche flag sur une attaque d'ability, c'est l'émission de `PreAttack` qu'il faudra
  ajouter, pas le canal.
- **Cap `maxNrOfHits` de `FrenziedFiring` non exercé** : un hexagone a au plus 6 voisins, donc la base
  plafonne à 7 < 10. Le `Min` est porté mais jamais mordant sur le board actuel.
- **Per-coup non bit-exact contre `templChampion`** (natif `[4654, 4640]` vs port `[5081, 4990]`, même
  nombre de coups) : axe DÉGÂT, hors canal de coups. La cible porte `MartialSuperiority` /
  `RapidAssault_ExtraDamage` ; le témoin `necroWarden`, lui, est bit-exact. À traiter comme un item de
  couverture d'effets, pas comme un résidu de #61.
- **Plancher de la formule** : le natif termine par `Math.Max(hits, 0)`, le port par `max(1, ...)`.
  Écart théorique seulement (aucune base connue ne descend à 0) ; le comportement du port est celui
  validé bit-exact de longue date sur l'attaque normale, il n'a pas été touché.
