# case-489 — `1048 FragstormGrenadeLauncher` : la face EXECUTION

`templAggressor` « Brother Burchard » (Black Templars, **lineup**, dans le pool rank 17). Quatre
autres porteurs, tous npc (`templBossAggressor`, `...Camp`, `...LEG`, `..._LHE`).

i2 : « Deals up to 6x 1746-2183 Blast Damage to a target within 2 hexes. Any leftover hits are
allocated to enemy units within 2 hexes, prioritising kills. »

**Seule la face EXECUTION manquait.** La face DECISION est portee depuis #352
(`playbook/prediction/abilities.py::_fragstorm_grenade_launcher_inputs` : base = `nrOfHits x maxDmg`
en UN coup). 1048 etait absente d'`ABILITY_CLASSES` -> `AbilityHandler.visit_ActiveAbilityMessage`
posait `ported: False` et rendait la main : 0 degat, 0 effet, aucune erreur.

Build de lecture : `rnca9r7q6c` (= `data/symbols/CURRENT`).

## 1. Le ctor — forme PRESET + FLAGS

`IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormGrenadeLauncherAbility$$.ctor` :

```
copie 0x40 octets depuis TargetingOptions statics +0x180        # le PRESET
TargetingOptions$$.ctor(&opts, &preset, 0x2000000)              # surcharge PRESET+FLAGS
AActiveAbility$$.ctor(this, &opts, 0)                           # 0 = AbilityAttackType.DirectTargetAttack
```

La surcharge PRESET+FLAGS fait `opts.Rules = flags | preset.Rules` : le litteral visible
(`0x2000000`) **n'est pas** le masque effectif.

Le preset `+0x180` est **lu dans `IdunBattle.Core.Services.TargetingOptions$$.cctor`** (pas repris
d'une case-doc) :

| champ | offset | valeur |
|---|---|---|
| `isSelfCasting` | `+0x180` | `0` |
| `range` | `+0x188` | copie de `TargetingRange` statics `+0x18` = `RANGE_FROM_CONFIG` (-> 2) |
| `forceMeleeTarget` | `+0x1a0` | **`1` = `RangedBool.False`** |
| `rules` | `+0x1a8` | `0x4002` |

| source du masque effectif | valeur |
|---|---|
| lecture (`0x2000000 \| 0x4002`) | `0x2004002` |
| mesure independante `docs/rl/case-302-4/tile-target-population.tsv` ligne 1048 (`state=measured`, `form=preset+flags`) | `0x2004002` |

Decomposition exhaustive (aucun bit residuel) :

| bit | `IdunBattle.Core.Services.TargetingRule` | effet porte |
|---|---|---|
| `0x2` | `TargetMatchesDynamicRule` | 1048 ne surcharge pas `GetDynamicInvalidTargetReason` -> defaut 0 |
| `0x4000` | `TargetIsEnemy` | **porte** |
| `0x2000000` | `AllowObscuredTargetByElevation` | desarme une regle de ligne de vue non portee -> sans effet, dans le bon sens |

⚠ Le preset **voisin** `+0x140` (Stikkbomb 1051, PlasmaGrenade 1098) ne differe QUE par
`forceMeleeTarget` (`RangedBool.True`). Recopier le masque d'une voisine aurait donne le bon `rules`
et la mauvaise PORTEE : `TargetingQuery$$GetRange` rabat a 1 au contact quand `ForceMeleeTarget` est
vrai — Fragstorm, lui, **garde sa portee 2**.

`ABILITY_ATTACK_TYPE` = **0** `DirectTargetAttack` (3e argument d'`AActiveAbility$$.ctor`).

## 2. `ExecuteBehaviour` — un arbre DSL a un seul noeud terminal

`…FragstormGrenadeLauncherAbility$$ExecuteBehaviour` construit un arbre `DSLFactory` passe a
`AActiveAbility$$Execute` -> le port **est** un arbre DSL, aucun ciblage recable a la main.

```
dmg   = DSLFormulas$$Cache( AActiveAbility$$MinMaxDamage(this, abilityState) )
other = Damageable( SurroundingEnemies(Owner@+0x30, GetNumberConstant(0x16 = range), 1, 3)
                    op_Subtraction Target@+0x60 )            # == $$GetOtherTargets
chain = DSLSelectors$$SortTargetsByDamagePredictionSelector(
            attacker = Owner@+0x30,
            units    = SortByFormula(other, StatAmount(ActiveTarget@+0x68, Health), ascending: 1),
            ability  = Direct(AbilityOrEffect(this+0x10)),
            damage   = dmg,
            hits     = Direct(GetNumberConstant(0x2f = nrOfHits)),
            damageProfileType = Direct(Nullable(GetDamageProfile(config))),
            attackerSelectionType = 3)
DSLBehaviors$$ChainLeftOverHitsAttackDamage(
    caster = Owner@+0x30, firstTarget = Target@+0x60, dmgAmount = dmg,
    damageProfileType = Direct(Nullable(profile)), hits = Direct(nrOfHits),
    abilityType = this+0x10, otherTargetSelector = chain,
    extraHitsAfterTargetKilled = **null**)
```

Signatures **nommees** (`frida/methods.tsv`) — c'est elles qui donnent le mapping des arguments, pas
l'ordre du decompile.

### 2.1 Quatre ecarts LUS avec `1006 MultiThreatEliminator` (meme feuille, `necrons.py`)

| | 1006 MTE | 1048 Fragstorm |
|---|---|---|
| `extraHitsAfterTargetKilled` | `Get(GetNumberConstant(0x2b))` = 1 | **`null`** — aucun coup bonus par kill |
| formule de degat | `MinMaxDamage` nu | wrappee `DSLFormulas$$Cache` |
| caster | `Caster@+0x48` | **`Owner@+0x30`** |
| selecteur de cible suivante | `And(Unobscured(Enemies(SurroundingUnits(CasterTile, range))), AdjacentUnits(ActiveTarget))` | **`SortTargetsByDamagePredictionSelector`** |
| execution | `ExecuteAtomic(..., 0x41)` | `Execute(this, tree)` |

MTE re-cible **adjacent a la cible precedente** ; Fragstorm re-cible **dans le disque du CASTER**.

## 3. `SortTargetsByDamagePredictionSelector` — le « prioritising kills »

`IdunBattle.Entities.Selectors.SortTargetsByDamagePredictionSelector$$Select` + son lambda
`…u003Cu003Ec__DisplayClass9_0$$u003CSelectu003Eb__0`, lus integralement :

```
targets  = (+0x20).SelectUniqueUnits(entities, attackerSelectionType)   # ITargetsSelector slot 4
attacker = (+0x18).SelectUnit(entities, attackerSelectionType)          #                  slot 7
if attacker == null : return new List<IEntity>()
dmgMin = damage.CalculateMin(entities)       # IAmountFormula slot 2
dmgAvg = damage.CalculateAverage(entities)   #                slot 4
dmgMax = damage.CalculateMax(entities)       #                slot 3
nbHits = hits.Calculate(entities)            #                slot 1
return targets.OrderByDescending(u => key(u)).ToList()

key(u) : pX = query.GetMultiHitAttackPrediction(attacker, u, position, ability, X, profile, nbHits)
    if pMax.WillBeKill  : return 0x7fffffff
    if pMin.MightBeKill : return 0x7ffffffe
    return MinMaxDamage.Avg(pAvg.<+0x60>)
```

**Les slots d'`IAmountFormula` sont LUS**, pas deduits de la semantique :
`data/symbols/rnca9r7q6c/metadata/interface_slots.tsv` donne
`0 IsSimple · 1 Calculate · 2 CalculateMin · 3 CalculateMax · 4 CalculateAverage`. C'est donc bien le
**MAX** qui alimente `WillBeKill` et le **MIN** qui alimente `MightBeKill` — l'inverse de l'intuition.

`GetMultiHitAttackPrediction` = `hits` appels de `GetAttackPrediction` avec `previousHitsPrediction`
threade + `DamagePredictionResult$$Add` : c'est exactement ce que fait deja
`services/damage_prediction.get_attack_prediction` cote port.

⚠ **Le port de ce selecteur est un noeud a `state`, et c'est un MIRROR** : le ctor natif STOCKE
`query` (`+0x50`) et `state` en champs de l'instance.

## 4. Le cran qui a MORDU : `ActiveTarget`, jamais `Subject`

La formule de tri est `StatAmount(DSLSelectors+0x68, Health)`. Le mapping des slots de `DSLSelectors`
est lu dans `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` (onze champs `+0x30..+0x80`),
aligne sur la carte `DSLFactory` (`+0x148 Owner … +0x180 ActiveTarget`) par l'ecart constant `0x118` :

```
+0x30 Owner · +0x38 Effect · +0x40 Actor · +0x48 Caster · +0x50 CasterTile · +0x58 CasterTiles ·
+0x60 Target · +0x68 ActiveTarget · +0x70 PreviousActiveTarget · +0x78 TargetTiles · +0x80 UnitFeetTiles
```

Donc `+0x68` = **ActiveTarget**. Cote port, ce slot est expose par `ActiveTarget()`
(`ctx.active_target`), que `SortByFormula.select` ne re-lie PAS (il re-lie `subject`) : **la formule
est CONSTANTE sur la source, le tri par PV est un NO-OP**, et l'ordre SOURCE (geometrique,
`SurroundingEnemies`) survit jusqu'au selecteur de prediction.

Le premier port ecrivait `Subject()` — le tri devenait ACTIF. **MESURE LIVE** (board `MC1_67`, seed
4242, caster `templAggressor` u83, cible `astraBullgryn` u79 a 2600 PV, candidats au report
`u77`/`u81`/`u107`) :

| | 2e maillon |
|---|---|
| port avec `Subject()` | **`u81`** puis `u107` |
| port avec `ActiveTarget()` | **`u107`** |
| **natif** | **`u107`** |

Le flag d'ordre est confirme au passage : `IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select`
fait `if (this+0x28 == 0) OrderByDescending else OrderBy` -> `ascending: 1` = **ascendant**.

## 5. Mesures live (`probe_489_fragstorm_grenade_launcher.py`)

Board `MC1_67`, seed 4242, `--p-units templAggressor`, `--a-units eldarRanger,astraBullgryn,tauCrisis`.
Replay-diff : capture (`decisionView` + `observeBattle` + `combatSnapshot` + `dumpRng`) -> rejeu
OFFLINE par le CHEMIN REEL (`AbilityHandler`) -> rejeu du MEME cast LIVE (`applyAction captureEvents`).

### Regime A — cible `tauSmnDroneShield` u107 (3989 PV), tuee a l'avant-dernier coup

| etage | offline | live | verdict |
|---|---|---|---|
| `ported` | `True` | — | **OK** (le no-op est ferme) |
| coups appliques sur la cible | 5 (pour `nrOfHits` 6) | 5 events | **OK** |
| degat par coup (clampe PV) | `[1191, 1305, 935, 558, 0]` | `[1191, 1305, 935, 558, 0]` | **BIT-EXACT** |
| report (2e maillon) | **0** coup | **1** coup (`u79`, 2710) | **ECART** -> `#489-r1` |

### Regime B — cible `astraBullgryn` u79 (2600 PV), tuee au 1er coup

| etage | offline | live | verdict |
|---|---|---|---|
| `ported` | `True` | — | **OK** |
| chaine (cibles, dans l'ordre) | `[u79, u107]` | `[u79, u107]` | **OK** (apres le correctif §4) |
| degat par coup sur `u79` (clampe) | `[2600, 0, 0, 0, 0]` | `[2600, 0]` puis plus rien | **OK** — le natif cesse d'EMETTRE apres `UnitFlag.Overkilled` |
| report (nb de coups) | **3** | **3** | **OK** |
| coups appliques au 2e maillon | **2** | **3** | **ECART** -> `#489-r1` |
| degat par coup sur `u107` | `[1214, 917]` | `[1214, 917, 1359]` | **BIT-EXACT sur les 2 coups communs** |

## 6. Residu `#489-r1` — le foyer PARTAGE du chainage, pas cet arbre

Les deux ecarts restants vivent dans `ChainLeftOverHitsAttackDamage`
(`abilities/behaviours/combat.py`), **partage avec `1006 MultiThreatEliminator`**. Ils ne sont pas
touches ici : les modifier sans re-jouer la campagne de calibration #125 risquerait de casser MTE.

### 6.1 `GetLeftOverHits` — le `-1` est le coup d'OVERKILL, pas « le 1er coup sur le cadavre »

La loi portee est `report = max(0, H - k - 1) + extraHits` (H = coups appliques, k = index 1-based du
coup fatal). La docstring de `_left_over_hits` porte un **residu ouvert** depuis #125 : la LECTURE des
trois call-sites d'`ApplyDamageOperation$$AddLeftoverHit` predit `H - k` entrees flag-vrai, « la
mesure en donne une de moins ; la mesure ne dit pas LEQUEL des coups ne compte pas (le 1er coup sur
le cadavre et le coup d'OVERKILL coincident sur les 4 regimes) ».

**Mes deux regimes les SEPARENT** — c'est le regime A qui manquait :

| regime | H | k | overkill ? | `H-k` | loi portee | natif |
|---|---|---|---|---|---|---|
| A (#489) | 5 | 4 | **non** (over-shoot 1749 < PV 3989) | 1 | **0** | **1** |
| B (#489) | 5 | 1 | **oui** (events coupes des le 2e coup) | 4 | **3** | **3** |
| MTE 2500 (#125) | 6 | 2 | oui | 4 | 4 (avec `extra`=1) | 4 |
| MTE 3000 (#125) | 6 | 2 | oui | 4 | 4 | 4 |
| MTE 4000 (#125) | 6 | 3 | oui | 3 | 3 | {1,2,3} (LightCover ecrase) |
| MTE 10000 (#125) | 6 | 6 | non | 0 | 1 | >= 1 |

La loi `report = (H - k) - (1 si overkill sinon 0) + extraHits` reproduit **6 regimes sur 6** ;
la loi portee en rate un (A). Le `-1` correspond donc au **coup d'OVERKILL**, dont l'entree
`LeftOverDamage` n'est pas comptee — et il n'existe pas quand la cible meurt sans etre overkillee.

**Non porte ici** : le retour d'`AttackDamageOperation.execute_ability_attack` n'expose aucun flag
d'overkill (il rend `per_hit_health` / `hp_before` / `hp_after`), donc la correction demande d'ouvrir
ce retour — un foyer partage par TOUS les vecteurs d'attaque d'ability. A instruire avec un 3e regime
discriminant et un re-jeu de `probe_125_leftover_hits.py --mode sweep`.

### 6.2 Le 2e maillon repart d'une attaque NEUVE

Regime B : `hits = 3` demandes au 2e maillon -> le port en APPLIQUE 2, le natif 3. Le port monte
chaque maillon par `execute_ability_attack` avec `hit_index0 = 0` / `crit_allowed0 = True`, c'est-a-dire
une `OngoingAttack` **neuve** ; c'est precisement le canal du residu `#419-r3` (`isOutsideAttack`),
qui note que 15 des 18 call-sites de `DSLBehaviors$$AttackDamage` posent `isOutsideAttack = false`.
Sur le 1er maillon les deux cotes s'accordent (5 coups pour `nrOfHits` 6), donc l'ecart apparait bien
a la 2e iteration.

## 7. Ce qui n'est PAS couvert

- **Un seul couple (board, seed)** : `MC1_67` / 4242. La discipline de generalisation demande un 2e
  couple des qu'une mecanique touche la geometrie — ici l'ordre SOURCE de `SurroundingEnemies`
  gouverne le tie-break du selecteur.
- **Le champ `+0x60`** dont `<Select>b__0` prend l'`Avg` n'est pas identifie NOMINALEMENT (l'une des
  trois `MinMaxDamage` cumulees par `DamagePredictionResult$$Add`) ; le port prend
  `accurate_health_damage`. N'affecte que les cibles qui ne franchissent NI `WillBeKill` NI
  `MightBeKill`.
- **Bouclier et scenarios de BLOCK** ne sont pas modelises dans la prediction montee par le
  selecteur (meme residu que `damage_utility.py`).
- **La sortie en tete de `get_WillBeKill` sur `CannotBeGuaranteedKilled@0x89`** n'est pas modelisee
  (aucun porteur dans le lot mesure).
