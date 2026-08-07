# #499 — `1019 StormOfWrath` : la chaîne `ChainAbilityDamage`

**État : RÉSOLU.** `1019` était un **no-op silencieux** (absente d'`ABILITY_CLASSES` : la décision
choisissait le cast, l'exécution l'ignorait — 0 dégât, 0 effet, aucune erreur). Portée end-to-end,
confrontée live sur **4 régimes**, accord **per-coup bit-exact** dans les quatre.

Porteur : `ultraTigurius` (lineup, **dans le pool** rank 17). Trois autres porteurs npc
(`ultraBossTigurius`, `ultraBossTiguriusLHE`, `ultraNpcTigurius`).

## 1. Ce que fait l'artefact natif

`IdunBattleLogic.Entities.Abilities.Active.Loki.StormOfWrathAbility$$ExecuteBehaviour` construit **un
seul nœud** :

```
ExecuteAtomic(
    DSLBehaviors$$ChainAbilityDamage(
        preselectedTargets  = <DSLSelectors+0x60> = Target,
        jumpTargetSelector  = Func(<ExecuteBehaviour>b__1_0),
        maxTargets          = DSLFormulas$$Direct(GetVariableForLevel(0 = maxAdjacentTargets)),
        dmgAmount           = AActiveAbility$$MinMaxDamage(state, isPrediction: 0)
                              = DSLFormulas$$RandomAmount(0xc = minDmg, 0xd = maxDmg),
        abilityOrEffect     = AbilityOrEffect$$op_Implicit(this),
        extraBehaviour      = null,
        damageOptions       = { isOutsideAttack: 0, damageProfile: Direct(GetDamageProfile()),
                                hits: null, 0 },
        chainOptions        = new <ChainOptions> { +0x12 = 1 } ),
    groupType = 0x44 = GroupType.StormOfWrath_Attack )
```

et le `Func` de saut est
`...StormOfWrathAbility$$u003CExecuteBehaviouru003Eb__1_0(lastTargets)` =
`DSLSelectors$$Enemies(of = <DSLSelectors+0x48> = Caster,
DSLSelectors$$AdjacentUnits(lastTargets, unique: 1, sel: 3), 3)`.

**La colonne `categorie` de l'audit disait `DAMAGE(Psychic)` et, cette fois, elle ne mentait pas** —
mais la forme n'est pas celle d'une attaque mono-cible : c'est une **chaîne**.

### 1.1 Les deux lectures que le décompilé impose

1. **L'origine du saut est l'ENSEMBLE des cibles déjà piquées, pas la dernière.**
   `IdunBattle.Entities.Behaviours.ChainBehaviourBehaviour$$Execute` invoque le `Func` avec
   `DSLSelectors$$Entities(pickedTargets)` — la **liste complète**. Le paramètre du lambda est
   d'ailleurs nommé `lastTargets`, au **pluriel**. Lire « la dernière cible » ferait rater tout saut
   depuis un maillon antérieur.
2. **Le coup est DIFFÉRÉ d'un cran** (`chainOptions+0x12 = 1`, posé par les **deux** consommateurs
   natifs de la factory — 1019 et
   `IdunBattleLogic.Entities.Abilities.Active.ChainLightningAbility$$CreateBehaviour`). Le dégât sur
   la cible N n'est appliqué qu'une fois la cible N+1 **choisie** :
   `<Execute>g__assignAndExecuteTarget|12_2` appelle
   `<Execute>g__performBehaviourOnLastTarget|12_3` **avant** de réassigner `lastTarget`. Le tirage du
   maillon N+1 se fait donc sur un plateau où le maillon N est encore vivant.

### 1.2 Le compteur, et ce qu'il borne

`while (pickedTargets.Count - preselectedTargets.Count < GetCurrentMaxTargets())` — c'est un
**delta**. `maxAdjacentTargets` borne les **sauts**, pas le total frappé. C'est une **variable
per-niveau** (3 jusqu'au niveau 26, 4 de 27 à 35, **5** au-delà), pas une constante.
`IdunBattle.Entities.Behaviours.ChainBehaviourBehaviour$$GetCurrentMaxTargets` a un second terme,
gaté par `this+0x70 maxTargetsExtra` — **toujours `null`** pour `ChainAbilityDamage` (le corps de
`IdunBattleLogic.Entities.DSLBehaviors$$ChainAbilityDamage` passe littéralement `0`).

### 1.3 Famille de dégât : ABILITY, pas ATTACK

Le `.ctor` de `IdunBattle.Entities.Behaviours.ChainAbilityDamageBehaviour` alloue un
`AbilityDamageBehaviour` — **la même classe** qu'alloue
`IdunBattleLogic.Entities.DSLBehaviors$$AbilityDamage` (identité de classe LUE, pas déduite d'un
nom). Donc `IdunBattle.Operations.AbilityDamageOperation` : **aucun crit**, **aucun tirage de valeur
dans l'opération** (la valeur est celle de la formule, évaluée **une fois par cible** dans
`IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$ExecuteTarget` → `$$GetDamage`).

Layout des 32 octets de `damageOptions`, **lu** dans `DSLBehaviors$$AbilityDamage` :
`isOutsideAttack@+0x00`, `damageProfile@+0x08`, `hits@+0x10`, `0@+0x18`. 1019 y met
`{0, Direct(Psychic), null, 0}` → **un** coup par maillon (le natif ne lit **pas** `nrOfHits` ici ;
la config de 1019 n'a d'ailleurs que `damageProfile` en constante).

### 1.4 Le masque de ciblage

`...StormOfWrathAbility$$.ctor` — **surcharge A, flags directs** (tranchée par les **xrefs
entrantes**, jamais par le nom que ghidra rend aux trois surcharges) :

```
TargetingOptions..ctor(&opts, isSelfCasting: 0, range: &<TargetingRange statics+0x00>,
                       forceMeleeTarget: 1, rules: 0x4000, dynCaster: 0, dynTarget: 0)
AActiveAbility..ctor(this, &opts, 0)            # 3e argument = AbilityAttackType.DirectTargetAttack
```

`rules = 0x4000 = TargetIsEnemy`, et **rien d'autre** (0x4000 = 0x4000, aucun résidu) ;
`forceMeleeTarget = 1 = RangedBool.False` (l'enum natif est **inversé** : True=0, False=1) ;
`range = <TargetingRange statics+0x00> = RANGE_ADJACENT_IF_MELEE_CASTER`.

Ces valeurs vivaient **déjà** dans `TARGETING_OPTIONS_UNPORTED` (lot #433-r4) ; la relecture les
**confirme à l'identique**, et #499 les **déplace** sur la classe — le contrat de disjonction des
deux tables interdit qu'un masque soit déclaré aux deux endroits
(`tests/engine/runner/test_targeting_options_sources.py`).

⚠ **Le 3e argument d'`AActiveAbility$$.ctor` est `0 = DirectTargetAttack` alors que le behaviour
n'attaque pas « en direct »** (c'est une chaîne, famille ABILITY). On **transcrit le littéral**,
jamais le profil de l'arbre.

## 2. Le port

| Étage natif | Port |
|---|---|
| `DSLBehaviors$$ChainAbilityDamage` + `ChainAbilityDamageBehaviour$$.ctor` + boucle `ChainBehaviourBehaviour$$Execute` | `engine/runner/abilities/behaviours/chain.py::ChainAbilityDamage` (nœud DSL **neuf**) |
| `AbilityDamageBehaviour` interne | `AttackWithAbilityDamage(Units(ActiveTarget()), …, native_operation="ability")` |
| `<ExecuteBehaviour>b__1_0` | `ultramarines.py::storm_of_wrath_jump_targets` = `Enemies(adjacent_units(picked_sel))` |
| `ExecuteBehaviour` complet | `ultramarines.py::storm_of_wrath_tree` |
| l'ability | `ultramarines.py::StormOfWrathAbility` (+ `handler.ABILITY_CLASSES`, `attack_type.ABILITY_ATTACK_TYPE`) |

⚠ **`ChainAbilityDamage` (nouveau) ≠ `engine.entities.behaviours.ChainBehaviour` (existant)** : le
second mirrore `IdunBattleLogic.Entities.DSLFactory$$ChainBehaviour` (la boucle bornée d'Incursion),
pas la chaîne à cibles accumulées. Les deux classes natives dérivent de `ChainBehaviourBehaviour`
mais sont distinctes.

**Résidus nommés** (rien d'inventé) : la paire `StartAttackBehaviour`/`FinishAttackBehaviour` que le
`.ctor` natif pose en `this+0x80` / `this+0x90` n'est pas portée en nœuds distincts — le port
matérialise une attaque **neuve** par cible dans `AttackDamageOperation.execute_ability_attack`
(défauts `hit_index0=0`, `crit_allowed0`, `failed_block0=None`), ce que la paire produit aussi par
cible ; les déclencheurs éventuellement attachés à ces deux Operations ne sont donc pas émis
séparément. Idem pour le `UnitSelectionType.OnlyTargetable` de `+0xa8` et le gate
`HasTrait(Invincible)` d'`AbilityDamageBehaviour` (même résidu que celui déjà nommé par
`AttackWithAttackDamage`).

## 3. Validation live — 4 régimes, accord per-coup bit-exact

`probe_499_storm_of_wrath.py` (mesure) / `tests/engine/runner/test_499_storm_of_wrath_live.py`
(garde). Board `MC1_67`, seed 777, `ultraTigurius` vs 4 orks, `--hp-target 400000` (armure 0, cibles
survivantes), `--crit 0,0`, `--no-ai`. Comparaison **par cible et par coup** : `Amount` des
événements live filtrés sur `Active_Ability_Type == 1019`, contre le `per_hit` du diagnostic offline.

| régime | montage | live | offline | verdict |
|---|---|---|---|---|
| `chaine` | 3 ennemis en **ligne**, le 4e exilé | `[(77,1857),(79,2832),(81,2680)]` | **identique** | 3 unités frappées |
| `coupe` | mêmes unités, maillons **hors adjacence** | `[(77,1916)]` | **identique** | **1 seule** unité |
| `grappe` | 3 ennemis **tous voisins** de la cible | `[(77,1857),(81,2832),(79,2681),(83,2556)]` | **identique** | 4 unités, **ordre du tirage** reproduit |
| `block` | géométrie `chaine` + `--block-target 100,500` | `[(77,1857),(79,2832),(81,2680)]` | **identique** | **aucun block**, des deux côtés |

**Ce que chaque régime interdit, séparément :**

* `chaine` vs `coupe` — le **cardinal** change avec la seule géométrie (3 → 1). Un port mono-cible
  échoue le premier ; un forfait « toujours N unités » échoue le second.
* `grappe` — **le régime non dégénéré du tirage.** En ligne, `PickRandomly(cand, 1)` n'a **qu'un**
  candidat par pas : l'accord y serait dégénéré et ne prouverait rien. En grappe le pool vaut 3, puis
  2, puis 1 — et l'ordre mesuré est `77, 81, 79, 83`, **pas** l'ordre des ids. Le port reproduit cet
  ordre-là et les valeurs qui en découlent : c'est la loi de consommation RNG du pick **et** l'ordre
  des `RandomAmount` qui sont validés d'un coup.
* `block` — **contre-épreuve non vacue.** Les cibles portent `BlockChance = 100` (témoin
  **assertionné** : sans lui, « aucun block observé » serait un vert qui ment) et **personne** ne
  bloque, ni le natif ni le port. Cause **lue** : le profil `Psychic` porte
  `DamageTrait.NoBlocking` (gate #65 de `AttackDamageOperation._block_sources`, mirror
  d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`) — le flux RNG est d'ailleurs
  **identique** au régime sans block, donc aucun tirage de block n'a même été consommé.

**Piège de montage mesuré en route** : écarter une unité « loin de la cible » seulement l'a laissée
**adjacente au 3e maillon**, et la chaîne l'a bel et bien atteinte (u83 frappée dans une première
version du régime `chaine`). L'ancrage d'exil porte désormais sur **tout le tracé**, pas sur la seule
cible — sinon le régime `coupe` aurait mesuré autre chose que ce qu'il annonce.

## 4. Ce qui n'est PAS couvert

* **Le CAP `maxAdjacentTargets`.** Il vaut **5** au niveau du runner, et le montage n'amène que
  4 ennemis : la chaîne s'arrête toujours faute de candidats, jamais par le compteur. Le mécanisme
  est **lu** (le delta `picked.Count - preselected.Count`) mais **non exercé**. Le montage qui le
  ferait : ≥ 7 ennemis mutuellement adjacents, ou un porteur dont le niveau d'ability descend sous 27
  (`maxAdjacentTargets = 3`).
* **`dmg_reduction`** (annoncé par la colonne `mecaniques` du kit) n'appartient pas à `1019` : son
  `ExecuteBehaviour` n'en contient aucune trace. C'est un passif du kit de Tigurius, hors périmètre.
* **Le régime MÊLÉE de Tigurius** (`1hmp1` = 1 % de chance) reste non exercé — et n'est pas un
  paramètre de cette ability : `1019` est `attackRangeType: Ranged`.
* **La paire `StartAttack`/`FinishAttack` par cible** (cf. §2) : non portée en nœuds distincts.
* **La face DÉCISION** (`IdunBattle.AI.Playbook.Loki.StormOfWrathPlaybook$$EvaluateNonComparable`)
  n'est pas dans le périmètre de #499. À noter : le corps du lambda de saut est **partagé** par
  déduplication IL2CPP avec la vague 2 de `PlagueWind`/`MortarionsPlagueWind`, déjà mirrorée dans
  `engine/runner/abilities/deathguard.py::plague_wind_wave_selectors`.

## 5. Le contrat de disjonction se paie en QUATRE endroits, pas un

Retirer la ligne de `TARGETING_OPTIONS_UNPORTED` **ne suffit pas** : trois autres artefacts
indexent la même table et rendaient `master` rouge tant qu'ils n'étaient pas mis à jour. Aucun n'est
vu par `probe_181`, qui vérifie qu'un masque **existe**, jamais qu'il n'est déclaré **qu'une fois** —
son `112/112` vert est parfaitement compatible avec les trois rouges.

| endroit | ce qu'il faut faire |
|---|---|
| `TARGETING_OPTIONS_UNPORTED` (`abilities/targeting.py`) | retirer l'entrée, poser la note de migration, **re-compter les 4 compteurs de section** |
| `SNAP_TARGETING_UNPORTED` (`tests/engine/test_270r1_volet2_dict_keys_enum_offline.py`) | retirer le couple **et re-compter** `test_cardinalites_du_volet` |
| `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` (`tests/engine/test_433_r4_r2_r1_r2_ability_range_offline.py`) | retirer l'id de la liste, l'inscrire au journal des sorties |
| `DYNAMIC_TARGET_RULE_UNPORTED` | **vérifié : rien à faire ici** — 1019 n'y a jamais eu d'entrée, son masque ne porte pas `TargetMatchesDynamicRule` |

**Les probes qui indexent la table ne sont gardés par rien** — celui-là s'est déjà cassé trois merges
durant. Les deux qui touchent 1019 sont **immunisés, et c'est vérifié, pas supposé** :
`probe_433_r4_r2_r1_r2_r2_r1_r1_pool_masks.py` **résout la source** (classe d'abord, table ensuite)
au lieu de l'indexer, et `probe_419r1tr14r5r2r1r2r1r1_range_only_adjacent.py` passe par
`ability_range`, dont la valeur de portée est **inchangée** par la migration (rejoué : `PASS`).

**Les compteurs se RE-COMPTENT, ils ne se soustraient pas — et c'est une mesure, pas un principe.**
Ils étaient déjà périmés avant #499, et **trois** tranches en vol ont retiré une entrée **chacune**,
en parallèle, chaque branche aveugle aux deux autres : #498 (`1152`), #499 (`1019`), #500 (`1038`).
Trois soustractions successives sur le même chiffre périmé en auraient manqué deux. Les trois
fichiers portent désormais cet avertissement **à l'endroit où la faute se commet**.

Comptes **re-dérivés** après rebase sur `ec797628` : **31 entrées écrites** dans le bloc
(10 / 4 / 1 / 16 par section) ; snapshot du volet 2 **35** (somme **119**) ; `probe_181` **113**.
Neuf sorties à ce jour : 1088 (#487), 1087 (#488), 1048 (#489), 1027 (#490), 1069 (#491),
1068 (#497), 1152 (#498), 1019 (#499), 1038 (#500).

⚠ **`32` reste le périmètre MESURÉ de #433-r4, jamais le compte d'entrées.** Les deux nombres
bougent indépendamment et se sont déjà croisés : au rebase précédent le total du bloc valait lui
aussi 32, par pure coïncidence — un lecteur pressé y aurait lu le périmètre. Le commentaire
d'en-tête sépare désormais les deux explicitement ; la mesure historique de #433-r4 (et son
contre-contrôle 32/32 contre `docs/rl/case-302-4/tile-target-population.json`) est **gardée et
attribuée**, pas réécrite.
