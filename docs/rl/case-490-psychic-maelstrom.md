# #490 — `1027 PsychicMaelstrom` : le nombre de coups est une FORMULE, pas un scalaire

**Verdict : RÉSOLU.** La face COMBAT est portée et confrontée live ; la face DÉCISION l'était déjà.

## Le symptôme

`1027 PsychicMaelstrom` était absente d'`ABILITY_CLASSES` : la décision choisissait le cast,
l'exécution l'ignorait. 0 dégât, 0 effet, **aucune erreur** — le no-op combat silencieux.

Porteur lineup : `astraPrimarisPsy` (héros Sibyll), dans le pool rank 17. Quatre autres porteurs,
tous npc (`astraBossPrimarisPsy`, `astraBossPrimarisPsyLHE`, `astraBossPrimarisPsySurv`,
`astraNpcPrimarisPsy`).

## L'artefact natif

`IdunBattleLogic.Entities.Abilities.Active.Loki.PsychicMaelstromAbility$$ExecuteBehaviour` est un
**arbre de nœuds `DSLFactory`** à UNE feuille — donc port DSL, pas `execute_*` impératif (#149).

    nbRolls = Sum( <DSLFormulas+0x20 = Direct(1)>,
                   ConditionalAmount( Maybe(GetNumberConstant(0x2a chance)),   Direct(1) ),
                   ConditionalAmount( Maybe(GetNumberConstant(0x33 chance_2)), Direct(1) ),
                   ConditionalAmount( Maybe(GetNumberConstant(0x39 chance_3)), Direct(1) ),
                   ConditionalAmount( Maybe(GetNumberConstant(0x3a chance_4)), Direct(1) ) )

    hits    = Multiply( nbRolls, Direct(GetNumberConstant(0x2f nrOfHits)) )

    attack  = AttackWithAbilityDamage(
                  caster  = <DSLSelectors+0x48>,     # singleton CASTER
                  target  = <DSLSelectors+0x60>,     # singleton TARGET -> MONO-CIBLE
                  amount  = AActiveAbility$$MinMaxDamage(this, abilityState, isPrediction: 0),
                  abilityOrEffect = AbilityOrEffect(this+0x10 = 1027),
                  options = { +0x00 flags 0,
                              +0x08 DSLSelectors$$Direct(GetDamageProfile()),
                              +0x10 hits,
                              +0x18 killerOverride null },
                  selectionType = 2 )

    AActiveAbility$$ExecuteAtomic( attack, entities, 0x46 )   # GroupType.PsychicMaelstrom_Attack

Kit gameconfig : `damageProfile=Psychic`, `range=2`, `nrOfHits=1`, `chance=75`, `chance_2=50`,
`chance_3=25`, `chance_4=10`, `minDmg`/`maxDmg`[level] (rarity-affected).

## Ce que ce cas apprend

### 1. Le nombre de coups est un NŒUD, et le figer casse plus que le compte

Le natif passe un `IAmountFormula` que
`IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$ExecuteTarget` évalue **à l'exécution**,
par cible (`if (this+0x98 != 0) nrOfHits = <slot 1>(...)`, défaut 1 sinon). Les quatre `Maybe`
tirent donc quatre `NextBool` au cast : **1 à 5 coups** (× `nrOfHits`), jamais une constante.

Le port passe le nœud par `AttackWithAttackDamage.hits_override`, qui l'évalue au même point du
pipeline. **Mesure de la contre-épreuve** (`probe_490_contre_epreuve.py`) : avec `hits` figé à
`Const(1)`, le contrôle rougit **4/4** — et le cas le plus instructif est celui où le live n'a fait
qu'**un seul** coup : **3424 live vs 3461 offline**. Les quatre `NextBool` non consommés décalent
le flux `IntBasedMersenneTwister`, donc le **tirage de dégât lui-même**. Un port qui figerait les
coups serait faux même là où le compte, par chance, coïncide.

### 2. La surcharge se tranche par ses XREFS ENTRANTES, jamais à l'œil

`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` a **quatre** surcharges, que
ghidra décompile toutes sous le même nom. `list_xrefs` place l'appel de 1027 sur celle à
`(caster, target, amount, abilityOrEffect, options, selectionType)` — le **cœur**, auquel les trois
autres délèguent. Ce n'est **pas** la surcharge `hits:System.Int32`, qui aurait figé les coups sans
que rien ne le signale. C'est le même nœud natif que Stormcaller/SpiritLeech, donc la même route
portée `execute_ability_attack(..., is_attack_damage_op=False)`, déjà live-validée bit-exact.

### 3. `ConditionalAmount(trigger, formulaTrue)` a DEUX arguments, et le troisième est caché

La surcharge lue construit le nœud avec `(trigger, formulaTrue, this+0x18)`. Les cinq constantes
cachées de la factory sont posées par `IdunBattleLogic.Entities.DSLFormulas$$.ctor` :
`+0x18 = Direct(0)`, `+0x20 = Direct(1)`, `+0x28 = Direct(2)`, `+0x30 = Direct(100)`,
`+0x38 = Direct(-1)`. La branche fausse vaut donc **0**, `formulaTrue` (= `+0x20`) vaut **1** :
chaque jet réussi ajoute exactement 1. Rien de tout cela n'est visible au site d'appel.

### 4. L'ordre des tirages se lit dans `SumAmount$$Calculate`

`Sum` a quatre surcharges natives (2, 3, 4, 5 branches) qui construisent **la même classe** ;
`SumAmount$$Calculate` additionne `a, b, c, d, e` dans cet ordre (`a` et `b` inconditionnels,
`c`/`d`/`e` sous un `if (champ != 0)`). Comme une branche **consomme du RNG**, permuter les
branches changerait le flux de tirages — donc le dégât. Le port a gagné ses surcharges 3/4/5
branches, purement additives (les 12 call-sites à 2 arguments sont inchangés, vérifié).

### 5. Le masque est une STATIC-COPY — la forme sans aucun ctor

`PsychicMaelstromAbility$$.ctor` **n'appelle aucun** `TargetingOptions$$.ctor` : il recopie les
0x40 octets de `<TargetingOptions statics>+0x180` et les passe à `AActiveAbility$$.ctor`. Le masque
effectif est la constante écrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` :

| champ | offset | valeur |
|---|---|---|
| `isSelfCasting` | `+0x180` | 0 |
| `range` | `+0x188` | `TargetingRange` statics `+0x18` = `RANGE_FROM_CONFIG` (→ portée 2) |
| `forceMeleeTarget` | `+0x1a0` | 1 = `RangedBool.False` |
| `rules` | `+0x1a8` | **0x4002** = `TargetIsEnemy \| TargetMatchesDynamicRule` |

⚠ Le preset `+0x140` porte le **même** masque et la **même** portée, et ne diffère que par
`forceMeleeTarget = 0` : recopier la voisine aurait donné le bon masque et le mauvais régime de
portée au contact.

⚠ **« Maelstrom » ne désigne pas une zone.** Le masque n'ouvre aucun domaine de TUILE et l'arbre
cible le singleton TARGET : **une** unité, **ennemie**. Le nom était une fausse piste.

`ABILITY_ATTACK_TYPE` = `DirectTargetAttack`, littéral `0` du 3ᵉ argument d'`AActiveAbility..ctor`.

### 6. Une face COMBAT portée fait DÉCROÎTRE deux inventaires figés

Le masque **migre** de `TARGETING_OPTIONS_UNPORTED` vers la classe (contrat de disjonction : une
ability a UNE source de masque). Ce mouvement traverse deux cliquets qui figent des comptes :

- `test_433_r4…` `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` — la liste **est** le complément
  d'`ABILITY_CLASSES`, donc porter une face COMBAT l'en retire par définition (32 → 31 ; 1069 était
  sortie de même en #491) ;
- `test_270r1_volet2` `SNAP_TARGETING_UNPORTED` — 44 → 43, total 128 → 127. Ce snapshot fige
  **l'ordinal écrit au site**, et le site a changé. Rien n'est perdu : les trois sites qui portent
  désormais 1027 l'écrivent par le **membre** (`ActiveAbilityType.PsychicMaelstrom`), jamais
  l'ordinal nu, et `probe_313` garde la bijection membre ↔ build.

La migration est **observationnellement neutre**, vérifié : `targeting_options_for(1027)` rend le
même masque (0x4002), la même portée (2) et le même lookup par ordinal nu qu'avant.

## Validation

| contrôle | mesure |
|---|---|
| `probe_490_psychic_maelstrom.py` (seed 49001, MC1_67) | **8/8** casts bit-exacts, coups **{2, 3, 4}** |
| `probe_490_contre_epreuve.py` (`hits` figé) | rougit **4/4** — le probe mord |
| `probe_490_generalisation.py` G1 (board `C1_74`, seed 59001, cible blindée) | **5/5** bit-exacts, coups {2, 3, 4} |
| `probe_490_generalisation.py` G2 (`blackAbaddon` Resilient, 6000 PV) | cap `ApplyResilientTraitDamageLimit` : **5999/6000**, vivant à 1 PV, pendant que `necroWarden` meurt — verdict qualitatif en accord |
| `probe_490_generalisation.py` G3 (gate de cible, 2 phases) | **10 couples**, code `TargetingRule` identique à l'octet |
| `test_490_psychic_maelstrom_live.py` | 3 tests (nœud offline, registres offline, replay-diff live) |

**Pourquoi G2 est le montage obligatoire** : le profil `Psychic` a `PiercingRatio 100` et le trait
`NoBlocking`, donc ni l'armure ni le block ne peuvent mordre. Le cap `Resilient` est le **seul**
étage défensif que ce vecteur laisse s'exercer — sans lui, la route ABILITY resterait non exercée.

**L'oracle du gate est `abilityReason`, pas `abilityTargets`** : au spawn, `abilityTargets` rend
`fromHere = []`, ce qui est **correct** (aucun ennemi à portée 2) mais ne dit rien par cible — un
port muet y serait d'accord pour la mauvaise raison. Et le court-circuit amont (#287-r6) est
vérifié **avant** toute comparaison.

### Ce qui n'est PAS couvert

- `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage(caster)` — gate de `GetDamage` qui, s'il
  est vrai, force `HitDamage(max)` (min == max). Non porté ; régime commun à toute la famille, pas
  propre à 1027, et aucun porteur dans un roster de duel.
- Les deux gates par-cible d'`AbilityDamageBehaviour$$Execute`
  (`MatchesUnitSelectionType(unit, selectionType = 2)`, `HasTrait(unit, 0x40e Invincible)`) —
  inertes en mono-cible sur une cible vivante déjà validée par le masque.
- Le bit `TargetMatchesDynamicRule` (0x2) du masque : non surchargé côté port → défaut 0
  (permissif), comme pour les autres porteurs de ce preset.
- Les quatre porteurs **npc** : non confrontés (le lineup `astraPrimarisPsy` suffit, l'arbre ne lit
  ni stats ni traits du caster).

### Deux fautes de PROBE trouvées en route

Les deux auraient accusé le port, et c'est le probe qui était faux :

1. `is_invalid_target(state, caster_id, target_id, ability)` prend l'ability en **dernier**, et une
   **instance** (la cascade appelle une méthode). Appelée à l'envers, elle acceptait tout.
2. `targetReason` est une **structure** `{ruleClass, hex, reasons}`, pas un scalaire. Lue comme un
   scalaire, elle faisait passer un accord parfait pour une divergence totale.

## Rouges PRÉEXISTANTS (mesurés, non causés par cette tranche)

Rejoués sur la base `a15bba26` **sans** cette tranche, comptes et messages identiques :

- `test_419r1tr14r5r2r1r1r1_normal_attack_kill_gate_live.py` — 1 failed / 9 passed
  (`test_la_contre_epreuve_mord_exactement_sur_les_gate_ees_du_bras_kill`, `ultraEliminator`) ;
- `test_tile_term_unit_gated_playbooks_live.py` — 13 failed / 12 passed / 5 skipped
  (`bloodMephiston`, ability 1071).
