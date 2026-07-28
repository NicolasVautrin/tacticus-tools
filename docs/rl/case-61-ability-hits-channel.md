# case-61 — Canal de COUPS des attaques d'ABILITY

**Statut : LIVRÉ.** Le vecteur COMBAT des attaques d'ability traverse désormais la formule de coups
partagée ; la face PRÉDICTION reste sur la base seule (verdict natif) ; `FrenziedFiring` (1036) a sa
base géométrique portée, son volet AoE **côté DÉCISION** (§4bis) **et côté COMBAT** (§4ter).

Artefacts : `engine/runner/operations/damage_ops.py` (`execute_ability_attack`),
`engine/services/attack_hits_formula.py`, `engine/playbook/prediction/abilities.py`
(`_frenzied_firing_inputs`, `make_damage_predictions`),
`engine/entities/abilities/active_ability.py` (`FrenziedFiringAbility`),
`engine/runner/abilities/blacklegion.py` (`frenzied_firing_tree`, `FrenziedFiringAbilityCombat`),
`probe_61_ability_hits.py`, `probe_61c_frenzy_aoe.py`, `probe_61d_frenzy_aoe_combat.py`,
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

Cette **unique boucle** porte à la fois les bonus attaquant (`OwnerIsCaster` : PowerTrip,
FightingRetreat_HitReduction) et les malus cible (`OwnerIsTarget` : Parry, LightCover, Camouflage,
Diminutive, BigTarget). Il n'y a donc **pas** deux canaux à brancher séparément : brancher l'appel
branche les deux.

> ⚠ **CORRIGÉ par [case-227](case-227-let-the-galaxy-burn-canal179.md) et
> [case-204](case-204-ah-master-annihilator-astartes-banner.md)** — `LetTheGalaxyBurn`,
> `AstartesBanner` et `MasterAnnihilator` ont été retirés de cette liste : leur artefact natif est
> `CreateAdditionalHits` (descripteur `EffectAdditionalHits`, canal #179), pas
> `CreateEffectHitsBonusForAttack`. Ils ne passent donc **pas** par cette boucle.

> ⚠ **CORRIGÉ par [case-122](case-122-hits-malus-ability-vector.md) §2** — la phrase ci-dessous est
> FAUSSE. `IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack` ne calcule rien : il résout le
> slot d'interface 2 de la `BattleQuery` et délègue à
> `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`, qui part de
> `IdunBattle.Core.Services.BattleQuery$$GetAbilityAttackRangeType` → la nature est **DÉCLARÉE** par
> l'ability (`attackRangeType`), et n'est positionnelle que pour la seule valeur `Normal` (3).

~~`IsMeleeAttack` y est **positionnel** (`IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack`), pas
la nature déclarée de l'ability — une ability « melee » castée à distance 2 est ranged pour ce canal.~~

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
nœud pour l'event de la cible principale, puis émet un **second batch** — c'est l'objet du §4bis.

---

## 4bis. Le volet AoE : le 2ᵉ batch du playbook

`IdunBattle.AI.Playbook.Loki.FrenziedFiringPlaybook$$MakeDamagePredictions` appelle **deux fois**
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`,
et **concatène** le résultat du second dans la liste du premier (`List.Add` en boucle sur son
énumérateur) :

| | batch 1 — cible d'origine | batch 2 — **volet AoE** |
|---|---|---|
| `targets` (param 5) | `Target@0x178` | `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetTargets` |
| `hits` (param 7) | `Evaluate(GetHitsForOriginalTarget)` — géométrique (§4) | **`1`, immédiat du call-site** |
| `formula` (param 6) | `BlightGrenadesAbility$$GetDamageFormula` | *idem* |
| `profile` (param 8) | `Nullable(AActiveAbility$$GetDamageProfile)` | *idem* |
| poids Fix64 (param 10) | `0` → `Fix64.FromInt(1)` | *idem* — donc **aucune** pondération `GetMaxSecondaryTargets` |

`GenerateMultiHitAttackPredictions` résout `param_5` en énumérable d'unités puis émet **un
`ProbableDamageEvent` par unité**, chacun avec `param_7` coups → le batch 2 pose 1 coup sur chaque
ennemi de l'anneau.

Le `hits = 1` est bien un **littéral** : `nrOfHits` (`0x2f`) vaut aussi 1 en config, mais le natif
n'appelle **ni** `GetNumberConstant` **ni** `GetHits` pour ce batch — recopier la constante serait une
coïncidence, pas un mirror. D'où la constante `FrenziedFiringAbility.AOE_HITS`, portée dans la classe
d'ability et non lue de la config.

### Le sélecteur

`IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetTargets` =
`IdunBattleLogic.Entities.DSLFactory$$AdjacentEnemies(caster@0x160, TargetTiles@0x190, 1)` — la
surcharge à 4 arguments, qui se développe en :

```
Enemies( caster@0x160,
         Units(AdjacentTiles(TargetTiles@0x190), 1, 3) − TargetTiles@0x190,
         3 )
```

= les unités d'équipe **≠ celle du CASTER** posées sur les tuiles adjacentes (anneau hex 1) à la
tuile de la **CIBLE**. Le centre est déjà exclu par `AdjacentTiles` (le `op_Subtraction` est
défensif) ; la cible principale est retirée par `make_damage_predictions`. Le filtre « vivant » n'est
pas un nœud de l'arbre : il est porté par `Units(...)`
(`IdunBattle.Entities.Selectors.UnitsOnTilesSelector$$Select`, lecture par **occupation de tuile** —
un mort n'est plus sur le board), ce que `_within` mirrore déjà (#57m). Le port est donc
`AdjacentEnemies(TargetTile(), Const(1))` **nu**, sans wrapper `Damageable`.

> ⚠ Les deux volets sont **anti-corrélés** : chaque ennemi posé sur l'anneau retire une tuile du
> `Count` du batch 1 **et** ajoute un event au batch 2. Un port qui n'émettrait que le batch 1
> perdrait donc doublement — c'est le levier du test de garde (5).

### Ground truth live

Runner isolé, board `MC1_67`, `blackObliterator` (u85) vs 4 ennemis, **caster jamais déplacé**
(cf. l'avertissement ci-dessous), cible sur une tuile à 6 voisins marchables. Oracle =
`aiPlaybookPredict`, qui invoque le `MakeDamagePredictions` natif et décode **tous** ses events.

| voisins ennemis | events natifs | coups batch 1 | coups batch 2 | port |
|---|---|---|---|---|
| 0 | 1 | 7 | — | identique, **dégât bit-exact** |
| 1 | 2 | 6 | 1 | identique, **bit-exact** |
| 2 | 3 | 5 | 1, 1 | identique, **bit-exact** |
| 3 | 4 | 4 | 1, 1, 1 | identique, **bit-exact** |

Avant : le port n'émettait **que** l'event de la cible d'origine (1 event dans les 4 cas).

> ⚠ **Ne jamais déplacer le caster pour monter ce scénario** (case-101 §6). `applyAction move` pose
> `UnitFlag.Moved`, que le natif lit pour désarmer `HeavyWeapon_ExtraDmg` (+25 % ranged not-moved) —
> or aucun RPC n'expose les `UnitFlags` au port, qui garde le bonus. Mesuré ici : un **×1,25 uniforme
> sur tous les events** (natif `u77 [10772,16160]` vs port `[13464,20196]`), purement artefact de
> mesure. Caster immobile ⇒ dégât bit-exact sur les deux batchs.

---

## 4ter. Le volet AoE, face COMBAT

`IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$ExecuteBehaviour` — jamais lu
avant cette passe, et **rien ne garantissait a priori** que l'exécution reprenne le sous-arbre du
playbook. Elle le reprend. Transcription du décompilé :

```
hitsNode = GetHitsForOriginalTarget(this)                       # nœud VALEUR géométrique (§4)
dmg      = AActiveAbility.MinMaxDamage(this, level)             # bornes minDmg/maxDmg
prof     = Nullable(AActiveAbility.GetDamageProfile(this))      # profil config = HeavyRound
src      = AbilityOrEffect.op_Implicit(this+0x10)               # = ActiveAbilityType 1036
A = op_BitwiseAnd( SetCache(hitsNode),                                         # displayClass+0x10
                   AttackWithAttackDamage(caster@0x160, target@0x178, dmg, prof,
                                          hits = hitsNode,      src, opts=0) )
B = op_BitwiseAnd( SetCache(hitsNode),                                         # displayClass+0x18
                   AttackWithAttackDamage(caster@0x160,
                                          AdjacentEnemies(caster@0x160, targetTiles@0x190, 1),
                                          dmg, prof,
                                          hits = DSLFactory.Direct(1), src, opts=0) )
AtomicGroup( 0x4e, OnProjectileFinishedCallback(displayClass,
                       FrenziedFiringAbility.<>c__DisplayClass1_0$$<ExecuteBehaviour>b__0) )
    où b__0 = Execute( op_Addition(A, B) )                       # A PUIS B, dans cet ordre
```

Ce que la lecture apprend, et qui n'était **pas** déductible de la face DÉCISION :

1. la face COMBAT émet bien **deux** volets (elle n'est pas mono-cible), et le second reprend le
   **même** sélecteur que `FrenziedFiringAbility$$GetTargets` → la feuille `_AOE` déjà portée est
   réutilisée telle quelle (aucun second port) ;
2. le nombre de coups du volet AoE est un **`DSLFactory.Direct(1)`** — un nœud constant construit au
   call-site, **pas** `GetNumberConstant(0x2f)` (qui vaut aussi 1 : le recopier serait une
   coïncidence). C'est la même constante native que le `hits = 1` littéral du 2ᵉ batch du playbook →
   `AOE_HITS`, partagée par les deux faces ;
3. les deux volets partagent le **même** nœud `hitsNode`, et chacun est précédé de **son propre**
   `SetCache(hitsNode)` : la géométrie est FIGÉE avant la première attaque, donc le volet AoE ne peut
   pas la re-mesurer après que les coups du volet 1 ont muté l'état ;
4. `AttackWithAttackDamage` sur les deux volets ⇒ famille ATTACK ⇒ le canal de coups partagé (§1.2)
   s'interpose sur les **deux**, y compris sur la base 1 du volet AoE ;
5. aucun `Foreach` : le sélecteur multi-cible est passé directement à **une** feuille d'attaque
   (patron HarvesterOfSouls/PlasmaGrenade) → `multi=True`, l'`OrderBy` foldant en un tri par id ;
6. aucun nœud d'effet, aucun spawn, aucun stat-mod : la face COMBAT de 1036 est purement deux
   attaques (`SuppressiveFire`/`LetTheGalaxyBurn` de Volk sont des **traits**, hors de cet arbre).

**Une seule définition du nœud de coups.** `GetHitsForOriginalTarget` vit désormais en **arbre DSL**
sur `FrenziedFiringAbility.get_hits_for_original_target` (`entities/abilities/active_ability.py`) —
`Min(Cache(Sum(Get(nrOfHits), Count(Filter(Walkable(AdjacentTiles(Target())), Not(HasUnit(Subject()))
| Not(AreEnemies(Units(Subject()), Caster())))))), Const(maxNrOfHits))` — et les **deux** faces
l'évaluent (la PRÉDICTION contre un `DslContext` bâti de la scène, le COMBAT contre celui du runner).
Le recalcul impératif qu'avait `_frenzied_firing_inputs` est retiré : un artefact natif, un port.
L'instance est **fraîche par appel** (le `Cache` est stateful, comme côté natif où l'arbre est
reconstruit à chaque cast).

### Ground truth live

Runner isolé, board `MC1_67`, **caster jamais déplacé**, roster **témoin** (`necroWarden`,
`necroOverlord`, `admecMarshall`, `eldarAutarch` : aucun modificateur du canal de coups — voir le
piège ci-dessous). Oracle = un événement de dégât par coup appliqué, **ventilé par
`DamageProfileType`** (le caster porte en permanence un effet du cycle `FleshmetalGuns`, dont les
coups appartiennent au canal #179 et non à l'arbre 1036). `probe_61d_frenzy_aoe_combat.py`.

| voisins ennemis | cibles natives | coups natifs (HeavyRound) | coups port | per-coup |
|---|---|---|---|---|
| 0 | cible seule | 7 | 7 | **bit-exact** (2 seeds) |
| 1 | cible + 1 | 6 / 2 | 7 / 1 | 6 premiers coups bit-exacts |
| 3 | cible + 3 | 4 / 1 / 1 / 1 | 4 / 1 / 1 / 1 | — |

La base du volet 1 tombe exactement du nombre d'ennemis posés sur l'anneau (7 → 6 → 4) : chaque
voisin retire une tuile du `Count` **et** ajoute une cible au volet AoE. Avant ce port, `1036`
n'avait **aucun** handler de combat — le cast était un no-op complet (0 dégât).

### Deux forks de port fermés au passage (mesurés ici, décompilé-prouvés)

Le natif n'a **qu'une** `IdunBattle.Operations.AttackDamageOperation$$Execute`, empruntée par
l'attaque NORMALE **et** par toute ability `AttackWithAttackDamage` (§1.2). Le port en a deux façades
(`execute` / `execute_ability_attack`), et deux vecteurs n'étaient câblés que dans la première :

- **canal #179** (coups additionnels hétérogènes) :
  `AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType` a `Execute` pour **seul**
  appelant (XREF). Mesure : le natif applique 2 coups Melta (cycle `FleshmetalGuns`) **sur chaque
  cible** d'un cast de 1036, absents du port. Branché dans `execute_ability_attack`, gaté sur la
  famille ATTACK (`AbilityDamageOperation$$Execute` est une Operation distincte).
- **`On(PreAttack=5)`** : émis par cette même `Execute`, avant `GetAttackHits`. Le port ne l'émettait
  que sur l'attaque normale. Mesure discriminante : le natif applique **+1 coup sur une partie des
  cibles, et la partie change d'un run à l'autre à géométrie identique** (K=3 : `{77:4, 79:1, 81:1,
  83:1}` puis `{77:5, 79:2, 81:2, 83:1}`) — signature du `Maybe(ConfigConst(0x2a))` de
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LetTheGalaxyBurnAbility$$CreateTrigger`
  (`On(5) & OwnerIsCaster & Maybe(chance) & !HasTileStatusEffect(TargetTiles@0x190)`). C'est
  l'émission de ce vecteur qui rend le K=0 **bit-exact** : avant elle, le tirage du `Maybe` n'était
  pas consommé côté port et **tout** le flux `state.rng` était décalé d'un cran.

> ⚠ **Piège de mesure : le roster.** Avec un roster quelconque, les malus/bonus du canal de coups des
> cibles (§1.2) se mélangent au verdict du volet mesuré. Constaté : un `astraBullgryn` (aura
> `BigTarget_AdjacentEffect`) posé sur l'anneau retire 1 coup à la cible **côté port** alors que le
> natif n'en retire pas ; un `ultraTitus` porteur de `LightCover` donne 2 coups natifs pour une base
> de 1. Le roster témoin est donc une **condition de la mesure**, pas un détail.

---

## 5. Reproduction

```bash
# depuis scripts/python, runner deja monte (cf. runner.md)
python probe_61_ability_hits.py both    --sid S --runner R --caster U --ability 1042 --target T
python probe_61_ability_hits.py predict --sid S --runner R --caster U --ability 1042 --targets "t1,t2"
python probe_61_ability_hits.py combat  --sid S --runner R --caster U --ability 1036 --target T
python probe_61c_frenzy_aoe.py --board MC1_67 --seed 61203 --k 3   # volet AoE DECISION (monte son runner)
python probe_61c_frenzy_aoe.py --board MC1_67 --seed 61200 --k 0   # volet AoE DECISION inerte
python probe_61d_frenzy_aoe_combat.py --board MC1_67 --seed 61340 --k 0   # volet AoE COMBAT inerte
python probe_61d_frenzy_aoe_combat.py --board MC1_67 --seed 61341 --k 3   # volet AoE COMBAT mordant
python -m pytest tests/engine/runner/test_ability_hits_channel_live.py -q
```

---

## 6. Résidus

- ~~**`On(PreAttack=5)` n'est pas émis par le vecteur ability**~~ — **RÉFUTÉ** (§4ter) : cette lecture
  n'avait jamais été mesurée. Le natif l'émet depuis `AttackDamageOperation$$Execute`, partagée par
  les deux vecteurs ; le +1 `LetTheGalaxyBurn` apparaît bien sur un cast d'ability. Le vecteur est
  désormais émis dans `execute_ability_attack` (gaté famille ATTACK) — c'est ce qui rend le K=0 de
  1036 bit-exact.
- **Le VERDICT du `Maybe` de `LetTheGalaxyBurn` peut différer natif/port.** Le *tirage* est
  maintenant consommé des deux côtés (l'alignement per-coup est préservé jusque-là), mais le prédicat
  ne rend pas toujours le même booléen : mesuré K=1, natif 6 coups sur la cible (non armé) vs port 7
  (armé), les 6 premiers coups restant **bit-exacts** — donc le décalage n'est pas un décalage de
  flux mais un écart de **seuil**. Port :
  `LetTheGalaxyBurnArmAbility.matches` → `state.rng.next_internal(0, 100) < LetTheGalaxyBurnChancePct`
  vs natif `IdunBattleLogic.Entities.DSLFactory$$Maybe` → `MaybeBehaviour$$Execute`. Le mirror exact
  du tirage de `Maybe` (bornes, comparaison, générateur) reste à lire. Impact : ±1 coup par attaque
  pour les 5 porteurs `LetTheGalaxyBurn` (Black Legion) — le test de garde borne l'écart à 1.
- **Conso RNG du canal #179 non bit-exacte** (résidu case-202 §7, « à confirmer live ») : les 2 coups
  additionnels `FleshmetalGuns` diffèrent en valeur (mesure K=0 : port `[2735, 2553]` vs natif
  `[2481, 2754]`) alors que les coups d'arme sont bit-exacts. Comme ces coups sont exécutés **après**
  chaque attaque, tout ce qui suit la première attaque d'un caster porteur d'un effet #179 est
  désaligné — c'est pourquoi le per-coup n'est confronté qu'à K=0.
- **Cap `maxNrOfHits` de `FrenziedFiring` non exercé** : un hexagone a au plus 6 voisins, donc la base
  plafonne à 7 < 10. Le `Min` est porté mais jamais mordant sur le board actuel.
- **Cible morte et `TargetTiles@0x190`** : si le volet 1 tuait la cible, le natif la retire du board
  (`KillUnit`) alors que le port lui laisse sa position (`alive=False` seulement) — le sélecteur
  `AdjacentEnemies(TargetTile(), 1)` du volet AoE pourrait donc diverger. Non exercé (les mesures
  tournent à `--hp-target 90000`), non porté.
- **Per-coup non bit-exact contre `templChampion`** (natif `[4654, 4640]` vs port `[5081, 4990]`, même
  nombre de coups) : axe DÉGÂT, hors canal de coups. La cible porte `MartialSuperiority` /
  `RapidAssault_ExtraDamage` ; le témoin `necroWarden`, lui, est bit-exact. À traiter comme un item de
  couverture d'effets, pas comme un résidu de #61.
- **Plancher de la formule** : le natif termine par `Math.Max(hits, 0)`, le port par `max(1, ...)`.
  Écart théorique seulement (aucune base connue ne descend à 0) ; le comportement du port est celui
  validé bit-exact de longue date sur l'attaque normale, il n'a pas été touché.
- **Le flag `Moved` n'atteint pas la face PRÉDICTION** — résidu de `case-101` §6, re-mesuré ici sur
  1036 : le chemin `make_damage_predictions` dérive « a bougé » de `attack_pos != scene.pos(caster)`
  (donc `False` pour la tuile courante) au lieu de lire `UnitFlag.Moved`, qu'aucun RPC n'expose. Un
  caster ranged **déjà déplacé** garde donc `HeavyWeapon_ExtraDmg` côté port : **×1,25 uniforme sur
  tous les events** (mesuré `u77 [13464,20196]` port vs `[10772,16160]` natif). Débloqueur nommé dans
  `case-101` : exposer `UnitFlagsComponent` (`OrderedSet<int>` @+0x10) dans `combatSnapshot`.
  Hors périmètre #61 (axe DÉGÂT, tous vecteurs ranged concernés — pas propre à 1036).
