# case-366-r1 — `1117 InescapableAccuracy_overrideHits` : le canal qui n'est pas une somme

> Troisième et dernier volet du passif `InescapableAccuracy` d'`eldarMauganRa`, après
> `1115 extraCritChance` (PR #411) et `1116 extraCritDmg` (PR #414). Les deux fiches précédentes
> l'annonçaient « canal `BaseEffect$$BlockHitsReduction`, NON porté côté moteur ». **C'était exact**
> — le canal n'existait nulle part dans `engine/`, et cette tranche l'ouvre.
>
> **La structure de famille a été RELUE au décompilé, pas héritée.** Elle tient. Ce qui ne tenait
> pas, c'est une étiquette que les deux fiches précédentes se transmettaient (§7.1).

## 1. Identité — relue, pas héritée

Les **trois** classes du passif partagent un unique corps de `$$.ctor` et se distinguent par **une**
méthode chacune. `CreateBlockHitReductionTrigger` a un corps **unique** (non dédupliqué) et son
symbole porte donc le nom de sa classe déclarante RÉELLE :

| bloc | méthode propre | classe | id |
|---|---|---|---|
| 1 | `CreateBlockHitReductionTrigger` | `…_OverridHitsEffect` | **1117** |
| 2 | `CreateCritChanceBonus` | `…_ExtraCritChanceEffect` | **1115** |
| 3 | `CreateCritDamageBonus` | `…_ExtraCritDamageEffect` | **1116** |

Trois faits indépendants verrouillent `1117` :

1. `IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracyAbility$$CreateBehaviour`
   pose exactement trois effets — `AddEffect(0x45b) + AddEffect(0x45c) + AddEffect(0x45d)`, targets
   = `<DSLSelectors+0x30>` = Owner, `turns = NULL` (**permanents**) — et deux des trois ids sont déjà
   attribués aux volets crit ;
2. le nom de classe du symbole (`_OverridHitsEffect`) correspond à `EffectType 1117 =
   InescapableAccuracy_overrideHits` (`enum_maps.EFFECT_TYPE`) ;
3. i2 (`Abilities/InescapableAccuracy_CurrentLevelDescription`) le dit dans les mêmes mots :
   « If Maugan Ra has not moved, then his ranged attacks **ignore hit reductions**, have +X% Crit
   Chance, and deal an additional Y Crit Damage ».

La `CreateActiveCondition` est bien la même : le corps que Ghidra nomme
`…_OverridHitsEffect$$ActiveCondition` est **instruction pour instruction** celui de
`…_ExtraCritDamageEffect$$CreateActiveCondition` — même `HasFlag(<DSLSelectors+0x30> = Owner,
flag = 0)` suivi du même `IdunBattle.DSL.AbilityTrigger$$op_LogicalNot`. Deux corps distincts dans
la table (l'un lit le DSL par son argument, l'autre par `this+0x48`), **une** sémantique.

## 2. Le canal — un TRIGGER NU, donc aucune magnitude

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.InescapableAccuracy_OverridHitsEffect$$CreateBlockHitReductionTrigger` :

```
get_OwnerIsCaster & IsRangedAttack
```

Mêmes deux nœuds que ses sœurs, mêmes surcharges
(`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster`,
`IdunBattleLogic.Entities.DSLTriggers$$IsRangedAttack` **sans argument**), même fusion par
`IdunBattle.DSL.AbilityTrigger$$op_BitwiseAnd`.

**Ce qui change tout** : le corps rend le trigger **NU**, là où `1115`/`1116` rendent un
`EffectBonus.ForAddition(trigger, ConfigVar(…))`. Donc :

* **aucun `ConfigVar`, aucune variable, aucune magnitude** ;
* le piège de #414 (« `variablesAffectedByRarityBonus` est PAR VARIABLE ») est **inerte ici, par
  STRUCTURE et non par configuration** : `gameconfig.ability("InescapableAccuracy").variables` ne
  contient que `extraCritChance` et `extraCritDmg`, toutes deux consommées par les deux autres
  volets. Vérifié plutôt que supposé, et verrouillé par
  `test_no_config_variable_read_offline` (le verdict est identique à `mult` 100 / 180 / 300).

## 3. Le consommateur — un INTERRUPTEUR, pas un terme

`IdunBattle.Entities.Effects.BaseEffect$$BlockHitsReduction(entities)` évalue le trigger mis en
cache à `<effect>+0x460` par `IdunBattle.Entities.Effects.BaseEffect$$InitializeBonusCacheIfNeeded`
(seul champ scalaire 8 octets de ce cache, écrit par `vtable+0x688` — les autres slots y déposent
des structs `EffectBonus`). Un effet qui ne surcharge pas la méthode a un cache **nul** et rend
`false`.

Lecteur **unique** : `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`. Sa structure, relue :

```
base   = Math.Max(weaponHits + GetStat(0x11 ExtraHits) + (isMelee ? GetStat(0x17 ExtraHitsMelee)), 0)
liste  = EffectsQuery$$GetActiveEffectsWithBonuses()        // effets ACTIFS de TOUT le board
        (filtre `EffectComponent@+0x5c` = IsActive, et targets.Count > 0)

pour chaque effet : b = HitsBonusForAttack(entities)         // slot 0x1e
    si b.HasValue :  b.addition < 0  ->  listeB (REDUCTIONS)
                     sinon           ->  listeA (ADDITIONS)

pour chaque effet : block |= BlockHitsReduction(entities)    // slot 0x24, Nullable<bool>

hits = base
pour b dans listeA : hits += b.addition ; si b.minimum : hits = Max(hits, Min(base, b.minimum))
SI NON block :
  pour b dans listeB : hits += b.addition ; si b.minimum : hits = Max(hits, Min(base, b.minimum))
pour b dans listeA : si b.override  : hits = b.override
pour b dans listeA : si b.resetFlag : hits = weaponHits
return Math.Max(hits, 0)
```

Trois conséquences, toutes portées :

* **le tri est au SIGNE, pas à la provenance.** Un `Parry` de la cible, un `BigTarget` d'aura et un
  `FightingRetreat_HitReduction` de l'**attaquant** tombent dans la même liste, donc s'éteignent
  ensemble. Restreindre le blocage aux effets du défenseur — la lecture « intuitive » — laisserait
  passer le troisième. Verrouillé par `test_sign_not_provenance_offline` ;
* **le flag est calculé AVANT toute somme**, dans une boucle dédiée sur la même collection ;
* **l'`ActiveCondition` est à sa place NATIVE et y suffit** : contrairement à
  `GetCritChanceBonusFromEffects` / `GetCritDamageBonusFromEffects` (qui ne filtrent rien),
  `GetActiveEffectsWithBonuses` filtre son énumération sur le flag `IsActive`. Le port rend quand
  même le gate `has_moved` une seconde fois dans le canal, par cohérence de famille — redondant,
  jamais faux, même store `UnitFlagsComponent`.

**Les DEUX faces passent par ce même point.** `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits`
délègue au slot 0xb6 de `BattleQuery`, qui délègue à `DamagePrediction$$GetAttackHits` — donc le
port n'a qu'un seul point de câblage, `engine/services/attack_hits_formula.py`, et il couvre
COMBAT (attaque normale + attaque d'ability famille ATTACK) **et** PRÉDICTION.

## 4. Le port

| natif | port |
|---|---|
| `BaseEffect$$BlockHitsReduction` | `BaseEffect.block_hits_reduction(att_ctx) -> bool` (défaut `False`) |
| la boucle BLOCK de `GetAttackHits` | `entities.effects.block_hits_reduction_from_effects` |
| le tri par signe + le saut de listeB | `entities.effects._hits_contribution` (foyer unique des 4 agrégateurs de l'axe) |
| `…_OverridHitsEffect$$CreateBlockHitReductionTrigger` | `InescapableAccuracyOverrideHitsEffect.block_hits_reduction` |
| `CreateActiveCondition` | `_InescapableAccuracyEffect.is_active` (hérité, corps partagé) |

⚠ **Le gate d'attaque lit `att_ctx["is_melee"]`, PAS `is_ranged`.** Sur l'axe COUPS la clé du `board`
est `is_melee` ; les canaux CRIT de `1115`/`1116` lisent `is_ranged`, posé par
`AttackDamageOperation._crit_params`. Transposer l'une pour l'autre rendrait le gate muet partout,
en silence. Tri-état #106 conservé : seule une nature **prouvée** distance (`is_melee is False`)
ouvre le canal.

La clé `has_moved` est ajoutée aux **deux** boards de la formule (combat
`runner/damage_model.py::build_hits_board` → `unit_has_moved` ; prédiction
`playbook/prediction/normal_attack.py` → le `_hm` **déjà calculé** pour le canal DÉGÂT, pas un
second read).

## 5. Le criterion, et les trois bras qui le tranchent

> « Le port IGNORE-t-il — **et refuse-t-il d'ignorer après un mouvement, et au contact** — les
> réductions de coups comme le natif ? », mesuré sur **le NOMBRE de coups**.

**Le nombre, pas la valeur, et c'est structurel** : `1117` n'a aucune magnitude, son seul observable
est la cardinalité de la salve. C'est aussi le seul criterion **immunisé** au résidu
`#366-r1-crit-multihit` (l'étage CRIT diverge dès le 3ᵉ coup, indépendamment de toute ability) — ce
résidu décale les VALEURS, jamais le COMPTE. D'où une salve **PLEINE** (6 coups ranged / 5 mêlée) là
où #411 et #414 devaient se rabattre sur une salve d'UN coup.

**AUCUN seed BC custom, et c'est une contrainte, pas une simplification.** Le nombre de coups vient
du BC côté natif et du gameconfig côté port (résidu de SOURCE, #411 §7.2) ; les deux coïncident tant
qu'on ne patche rien (`eldarMauganRa` = 5 mêlée / 6 ranged des deux côtés, vérifié). Patcher
`Weapons[].Hits` — ce que font les cliquets de `1115` et `1116` — **désynchroniserait les deux
modèles sur l'étage même qu'on mesure**.

Autres contraintes de montage, chacune payée par une mesure fausse évitée :

* **la cible doit PORTER une réduction, et du bon vecteur.** RANGED → `tyranDeathleaper` (trait
  `Camouflage` → `Camouflage_HitReduction`, `OwnerIsTarget & IsRangedAttack`, **−2** au-delà de
  2 hexes) ; MÊLÉE → `custoAtlacoya` (trait `Parry` → `Parry_ReduceHits`, `OwnerIsTarget &
  IsMeleeAttack`, **−1**). Sans réduction sur la cible, `1117` est **inerte** et un accord
  live == offline ne prouverait rien ;
* **ni l'une ni l'autre ne porte `Overwatch`** (le montage déplace les deux camps, et Maugan Ra
  porte lui-même `Overwatch`), **ni de `TertiaryAbility` au seed BC** — c'est ce qui a écarté
  `admecRuststalker`, pourtant porteur de `Camouflage` : il arrive avec la relique `1457` ;
* **d = 3 EXACT avant ET après le pas** : le bras MOVED doit changer le flag `Moved` et **rien
  d'autre** de ce que lit le canal. À d ≤ 2, Camouflage bascule sur sa branche `−1` et les deux bras
  cesseraient d'être comparables ;
* **`--crit 0,700`** : dans MOVED et MELEE le volet `1115` est fermé (mouvement / mêlée), donc
  `clamp(0 + 0) = 0` — la salve ne crite **pas du tout** et les VALEURS y sont confrontables en plus
  du compte. Dans NOMOVE, `1115` ouvre `clamp(0 + 15) = 15` et des crits tombent : c'est exactement
  le régime du résidu multi-hit, et le compte reste juste.

### 5.1 Le carré, mesuré

`probe_366_r1_inescapable_accuracy_override_hits.py` — porteur `eldarMauganRa`.

| bras | board/seed | LIVE | OFFLINE | mutation → rejeu |
|---|---|---|---|---|
| **NOMOVE** | MC1_67/777 | n=**6** `[4548, 1618, 2026, 1967, 1682, 1597]` | n=**6** | `NOCHANNEL` → n=**4** |
| **MOVED** | MC1_67/777 | n=**4** `[1267, 1239, 1629, 1619]` | n=**4**, **bit-exact** | `NOGATE` → n=**6** |
| **MELEE** | MC1_67/777 | n=**4** `[584, 641, 657, 511]` | n=**4**, **bit-exact** | `NORANGEGATE` → n=**5** |
| **NOMOVE** | C1_25/31337 | n=**6** `[1285, 1125, 914, 1196, 935, 1220]` | n=**6** | `NOCHANNEL` → n=**4** |
| **MOVED** | C1_25/31337 | n=**4** `[956, 1014, 1070, 840]` | n=**4**, **bit-exact** | `NOGATE` → n=**6** |
| **MELEE** | C1_25/31337 | n=**4** `[702, 700, 651, 556]` | n=**4**, **bit-exact** | `NORANGEGATE` → n=**5** |

Les six cellules s'accordent sur le compte, les quatre bras sans crit sont **bit-exacts jusqu'à la
valeur**, et les **six** mutations changent toutes le rejeu :

* `NOCHANNEL` (inscription retirée d'`EFFECT_CLASSES`) — **c'est la vue ROUGE d'avant le fix** : le
  port comptait **4** coups là où le natif en joue **6** ;
* `NOGATE` (les deux mirrors de l'`ActiveCondition` désarmés) — le port bloquerait la réduction là
  où le natif, qui a vu `HasFlag(Moved)`, la subit ;
* `NORANGEGATE` (nœud `IsRangedAttack` désarmé) — le port bloquerait le `Parry` d'une frappe de
  contact.

⚠ **`NORANGEGATE` a d'abord été écrite INERTE, et elle est passée VERTE.** Désarmer un gate
tri-état n'est pas retirer sa clé : `is_melee` absent rend la nature « non prouvée distance », ce
qui **ferme** le gate au lieu de l'ouvrir — la mutation rendait 4 coups comme la référence, et le
probe l'a refusée (garde de discrimination). La forme correcte est de **forcer** `is_melee = False`.
C'est le cas d'école de « sur une contre-épreuve, VERT est le résultat SUSPECT ».

Cliquet : `tests/engine/runner/test_inescapable_accuracy_override_hits_live.py` — **11 passed**
(4 structurels offline + 7 live).

## 6. Ce qui n'est PAS couvert

* **La face PRÉDICTION n'est pas CONFRONTÉE live.** Elle est *couverte par construction* — la
  formule est le foyer partagé, et `playbook/prediction/normal_attack.py` l'appelle avec le même
  `has_moved` et le même `is_melee` — mais aucun bras de ce cas ne lit une prédiction. C'est une
  différence réelle avec `1115`/`1116`, dont la face prédiction est, elle, **absente** (le canal
  crit n'entre pas dans `services/damage_prediction.py`) : ici il n'y a pas de gap de canal, il y a
  un gap de MESURE.
* **Le vecteur ABILITY** (famille ATTACK) traverse la même formule et le natif ne porte **pas** de
  `IsNormalAttack` ⇒ le blocage y vaut aussi. Verrouillé **offline seulement**
  (`test_sign_not_provenance_offline` passe par la formule, pas par un cast) : aucun montage live ne
  l'exerce.
* **Le vecteur OVERWATCH** de Maugan Ra n'est pas exercé. Il passe par `damage_ops/normal.py` avec
  `_ranged = True`, donc `IsRangedAttack` s'y ouvrirait ; l'`ActiveCondition` porte sur le
  `UnitFlag.Moved` de l'OWNER, purgé au `StartTurnOperation`. Non mesuré.
* **Les autres réductions du canal** ne sont pas confrontées une par une : le carré exerce
  `Camouflage` (ranged) et `Parry` (mêlée). `LightCover`, `Diminutive`, `BigTarget` (aura) et
  `FightingRetreat_HitReduction` (porté par l'ATTAQUANT) empruntent le **même** foyer
  `_hits_contribution` — le tri par signe est verrouillé offline, pas mesuré live pour chacun.
* **Les deux dernières boucles de `GetAttackHits`** — `b.override` (`hits = valeur`) et
  `b.resetFlag` (`hits = weaponHits`) — ne sont **pas** portées. Elles ne balaient que la listeA
  (additions), et aucun effet porté ne les alimente ; elles ne sont pas dans le périmètre de cette
  tranche, mais elles existent nativement et ne sont documentées nulle part ailleurs.
* **Le clamp `minimum` PAR EFFET** (`Math.Max(hits, Math.Min(base, minimum))`) reste approximé par
  le `max(_floor, …)` global du port — résidu **préexistant**, déjà documenté dans l'en-tête de
  `attack_hits_formula.py`, que ce port n'aggrave pas (quand le flag est armé, le natif saute le
  bonus **et** son clamp, le port ne compte ni l'un ni l'autre).

## 7. Résidus

### 7.1 RECTIFICATION — `--block-target 0,0` n'a JAMAIS neutralisé `1117`

Les montages de `1115` (#411) et `1116` (#414) écrivaient, dans leur probe et dans leur cliquet, que
`--block-target 0,0` « neutralise le canal BLOCK de la cible, celui que porte le jumeau non porté
`1117` ». **C'est faux, et sur les deux moitiés de la phrase.** L'option pose
`BlockChance`/`BlockDamage` des a-units (`rl_duel._patch_combat_stat`) — le **blocage de DÉGÂT**
(`GetStat(7/8)` → `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`), qui n'a
aucun rapport avec `BaseEffect$$BlockHitsReduction` : l'un est une stat de la cible, l'autre un
interrupteur de l'axe COUPS.

**Sans conséquence sur les deux mesures**, et pour une raison qu'il faut écrire plutôt que
supposer : `1117` était **inerte** dans ces montages, faute de la moindre réduction de coups sur
`necroWarden` / `necroOverlord` (aucun des deux ne porte `Parry`, `Camouflage`, `LightCover`,
`Diminutive` ni `BigTarget`). Depuis qu'il est porté, il reste inerte **pour la même raison, des
deux côtés** — et les deux cliquets ont été re-joués : **17 passed**.

Les deux docstrings et le test concerné ont été rectifiés sur place.

### 7.2 `#366-r1-blockhits-purgeresponse` — le SECOND implémenteur natif du canal, non porté

`IdunBattle.Entities.Effects.Loki.PurgeResponseEffect$$CreateBlockHitReductionTrigger` est le seul
autre implémenteur de `BlockHitsReduction` du binaire, et son trigger est **structurellement
différent** :

```
TriggeringAbilityIs( <AbilityOrEffect> )        // AUCUN get_OwnerIsCaster
```

Conséquence pour le port : l'agrégateur `block_hits_reduction_from_effects` ne balaie que les effets
de l'**attaquant** — ce qui est le rendu exact du `get_OwnerIsCaster` de `1117`, et ce qui rendrait
`PurgeResponse` invisible. Le porter exige donc d'**élargir le balayage** (cible + auras), pas
seulement d'ajouter une classe. C'est écrit dans la docstring de l'agrégateur pour que
l'élargissement soit un geste explicite.

Porteurs de `PurgeResponse` (`EffectType 1538`) : `votanNpc2Steeljack` (**npc**) et
`votanSmnSteeljack` (**SUMMON**) — donc confrontable par la voie summon, en spawnant son summoner.
L'ability associée est `PurgeResponse_ActiveOverwatchAbility` (`…$$CreateBehaviour` /
`…$$CreateTrigger`), non portée.

### 7.3 Donnée NEUVE sur `#366-r1-crit-multihit` — il ne touche PAS la cardinalité

Ce cas ne corrige pas le résidu, mais il le **borne**, ce que ni #411 ni #414 ne pouvaient faire
(tous deux confinés à une salve d'un coup) :

* sur une salve **PLEINE de 6 coups** à crit ouvert (NOMOVE, `clamp(0 + 15) = 15`), le **compte**
  live et offline s'accorde dans les deux couples (board, seed) — la divergence est purement dans
  les valeurs : MC1_67/777 live `[4548, 1618, 2026, 1967, 1682, 1597]` contre port
  `[4548, 1618, 1967, 1597, 4846, 1867]` (les deux premières cellules coïncident, la suite se
  décale) ;
* sur une salve pleine de **4** ou **5** coups à crit **nul** (MOVED, MELEE), les quatre bras sont
  **bit-exacts jusqu'à la valeur** — l'étage de base reste sain au-delà du 3ᵉ coup.

⇒ le résidu est bien dans le **flux de tirages du crit**, pas dans le nombre de coups ni dans la
base. Toute garde qui n'observe que la cardinalité reste donc confrontable en multi-coups.
