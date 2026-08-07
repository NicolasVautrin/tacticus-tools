# case-489 — `1048 FragstormGrenadeLauncher` : la face EXECUTION

`templAggressor` « Brother Burchard » (Black Templars, **lineup**, dans le pool rank 17). Quatre
autres porteurs, tous npc (`templBossAggressor`, `...Camp`, `...LEG`, `..._LHE`).

i2 : « Deals up to 6x 1746-2183 Blast Damage to a target within 2 hexes. Any leftover hits are
allocated to enemy units within 2 hexes, prioritising kills. »

**La face DECISION etait deja portee** (`_fragstorm_grenade_launcher_inputs`,
`engine/playbook/prediction/abilities.py`, #352 : base = `nrOfHits x maxDmg` en **un** coup, volet
secondaire mort). Ce cas ne porte que la face **EXECUTION** : 1048 etait absente d'`ABILITY_CLASSES`
-> `AbilityHandler.visit_ActiveAbilityMessage` posait `ported: False` et rendait la main. 0 degat,
0 effet, aucune erreur.

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

| source | valeur |
|---|---|
| lecture (preset `+0x180`.Rules `0x4002` \| flags `0x2000000`) | `0x2004002` |
| mesure independante `docs/rl/case-302-4/tile-target-population.tsv` ligne 1048 (`state=measured`, `form=preset+flags`) | `0x2004002` |

Decomposition exhaustive (aucun bit residuel) :

| bit | `IdunBattle.Core.Services.TargetingRule` | effet porte |
|---|---|---|
| `0x2` | `TargetMatchesDynamicRule` | point d'extension ; 1048 ne surcharge pas `GetDynamicInvalidTargetReason` -> defaut 0 |
| `0x4000` | `TargetIsEnemy` | **porte** |
| `0x2000000` | `AllowObscuredTargetByElevation` | desarme une regle de ligne de vue non portee -> sans effet, dans le bon sens |

Preset `+0x180` (a re-verifier dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` — le
relever depuis `case-247` ne vaut pas lecture) : `isSelfCasting = 0`, `range` = `TargetingRange`
statique `+0x18` = `RANGE_FROM_CONFIG`, `forceMeleeTarget = 1` = `RangedBool.False`.
C'est le **meme preset** que `1078 Fragstorm` — et le voisin `+0x140` (Stikkbomb, PlasmaGrenade) n'en
differe que par `forceMeleeTarget`, donc recopier la voisine donnerait le bon `rules` et la mauvaise
portee.

`ABILITY_ATTACK_TYPE` = **0** `DirectTargetAttack` (3e argument d'`AActiveAbility$$.ctor`).

## 2. `ExecuteBehaviour` — un arbre DSL a un seul noeud terminal

`IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormGrenadeLauncherAbility$$ExecuteBehaviour`
construit un arbre `DSLFactory` et le passe a `AActiveAbility$$Execute` -> le port **doit** etre un
arbre DSL, aucun ciblage recable a la main.

```
dmg      = DSLFormulas.Cache( AActiveAbility$$MinMaxDamage(this, abilityState) )
nrOfHits = AbilityConfiguration$$GetNumberConstant(cfg, 0x2f)
range    = AbilityConfiguration$$GetNumberConstant(cfg, 0x16)
profile  = AbilityConfiguration$$GetDamageProfile(cfg)                    # Nullable<DamageProfile>

others   = DSLSelectors$$Damageable(
             DSLSelectors$$SurroundingEnemies(caster@sel+0x30, range, unique: 1, sel: 3)
             - Target@sel+0x60 )                                          # == $$GetOtherTargets
sorted   = DSLSelectors$$SortByFormula(others,
             DSLFormulas$$StatAmount(Target@sel+0x68, StatType 5), asc: 1)
chain    = DSLSelectors$$SortTargetsByDamagePredictionSelector(
             caster@sel+0x30, sorted, Direct(AbilityOrEffect(this)),
             dmg, Direct(nrOfHits), Direct(Nullable(profile)), 3)

DSLBehaviors$$ChainLeftOverHitsAttackDamage(
    caster@sel+0x30, Target@sel+0x60, dmg, Direct(Nullable(profile)),
    Direct(nrOfHits), this+0x10, chain, extraHits: 0 /* null */)
```

`$$GetOtherTargets` est la meme expression, extraite : elle est aussi appelee par le volet
secondaire (mort) du playbook.

## 3. Ce qui differe du patron deja porte `1006 MultiThreatEliminator`

`ChainLeftOverHitsAttackDamage` est **deja** mirrore dans
`engine/runner/abilities/behaviours/combat.py` (avec son `GetLeftOverHits` et sa garde 100
iterations), consomme par `necrons.py:multi_threat_eliminator_tree`. Les differences sont **lues**,
pas supposees :

| | 1006 MTE | 1048 Fragstorm |
|---|---|---|
| `extraHits` | `DSLFormulas$$Get(GetNumberConstant(0x2b))` | **`0`** (argument nul) — pas de coup bonus par kill |
| formule de degat | `MinMaxDamage` nu | **wrappee `DSLFormulas$$Cache`** |
| caster | `sel+0x48` | `sel+0x30` |
| selecteur de chaine | `And(Unobscured(Enemies(SurroundingUnits(casterTile, range))), AdjacentUnits(ActiveTarget()))` | **`SortTargetsByDamagePredictionSelector`** |
| forme d'execution | `ExecuteAtomic(this, tree, entities, 0x41)` | `Execute(this, tree)` |
| ctor | static-copy `+0x140`, rules `0x4002` | preset+flags `+0x180`, rules `0x2004002` |

Le selecteur de chaine est le « prioritising kills » du tooltip, et c'est la piece qui n'existe pas
encore cote port.

## 4. Etat

RE des trois fonctions de l'ability : **faite**. Restent a lire :
`DSLSelectors$$SortTargetsByDamagePredictionSelector` + `SortTargetsByDamagePredictionSelector$$Select`,
`DSLBehaviors$$ChainLeftOverHitsAttackDamage` (positions d'arguments), `TargetingOptions$$.cctor`
(preset `+0x180`).
