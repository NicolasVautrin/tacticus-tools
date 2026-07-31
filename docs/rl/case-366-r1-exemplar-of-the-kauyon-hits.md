# #366-r1 (G3) — `1181 ExemplarOfTheKauyon_AdditionalHits` : canal #179, pas celui de `1183`

**Question binaire** : les coups accordés par `1181` sont-ils comptés par le port comme par le natif,
sur un montage où ils MORDENT ?

**Réponse** : NON avant ce cas (aucune inscription) — OUI après, **bit-exact sur trois géométries**.

## 1. Le canal — l'hypothèse « même canal que `1183` » est RÉFUTÉE

`1181` et `1183` partagent le porteur (`tauShadowsun`) et la colonne « COUPS » de l'inventaire #366.
Les deux marqueurs natifs sont pourtant **différents**, et le canal commande tout le port :

| effet | fonction native | ce que gagne l'attaque |
|---|---|---|
| `1183` (#372) | `...DefenderOfTheGreaterGood_ExtraHitsEffect$$CreateEffectHitsBonusForAttack` | un coup d'**ARME** de plus (terme de `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`) |
| **`1181`** | `IdunBattle.Entities.Effects.Loki.ExemplarOfTheKauyon_AdditionalHitsEffectEffect$$CreateAdditionalHits` | un **GROUPE** à dégât et profil PROPRES (`IdunBattle.Entities.Effects.EffectAdditionalHits$$Create`, canal #179) |

Le suffixe `EffectEffect` de la classe native est celui du **binaire**, pas une coquille.

Corps natif lu verbatim (ordre des `DSLFactory`) :

```
amount  = DSLFormulas.ConfigVar( 0xb = dmg, GetAbilityState(effet), config@0x60 )
nrOfHits= AbilityConfiguration.GetNumberConstant( config, 0x2f )                 # = 2
profile = AbilityConfiguration.GetDamageProfile( config ).Value                  # = Blast
trigger = DSLTriggers.get_OwnerIsCaster                                          # SEUL conjoint
hits    = DSLFormulas.Get( nrOfHits )
EffectAdditionalHits.Create( &out, trigger, amount, 1, profile, hits,
                             forceOverkill = false, param_8 = **0** )
```

`.ctor` = `BaseEffect(AbilityOrEffect(0x43f = 1087 ExemplarOfTheKauyon), hasAutomaticActivation = 1)`
— l'immédiat `mov edx, 0x43f` est lu à l'octet, pas déduit du nom.

Trois lectures qui auraient pu être devinées faux, et qui sont LUES :

* **`Get` vs `Direct`** — le nœud de comptage est l'overload `DSLFormulas$$Get(int)` tranché **par ses
  xrefs entrantes**, le même que `SquigHound`/`CordClaw`/`SorcerousFacade`/`CyclicIonBlaster`
  (`FoulInfusion`, lui, passe par `Direct`). Les deux rendent un nœud constant ; le distinguer à l'œil
  sur trois homonymes n'aurait rien prouvé.
* **Aucun gate melee/ranged** — `get_OwnerIsCaster` est le seul nœud du trigger (contrairement à
  `FoulInfusion`/`FearOfTheUnseen`), et ce gate est rendu par le canal PORTEUR lui-même.
* **`param_8 = 0` ⇒ cellule DEGENEREE** — `EffectAdditionalHits$$Create` exécute son repli
  `if (param_8 != 0) param_3 = param_8; param_1[2] = param_3` : `minNode` retombe sur l'`amountNode`,
  un `ConfigAmount` **scalaire** ⇒ `MinMaxDamage(v, v)`, et `IdunBattle.Core.HitDamage$$GetDamage`
  ouvre sur `if (*param_1 == param_1[1]) return *param_1;` → **0 tirage**. C'est ce qui rend les deux
  coups **égaux et déterministes**, donc mesurables sans statistique — et c'est le discriminant qui a
  été observé live.

`gameconfig` : `constants = {unitId: tauSmnDroneCommandLink, damageProfile: Blast, nrOfHits: 2,
initialCooldownTurns: 1}`, `variables = {dmg, summonHp, summonDmg, summonArmor}`, les quatre
rarity-scalées. i2 : « This attack deals an additional {[nrOfHits]}x {[dmg]} Blast Damage. »

## 2. Le poseur — UN seul site, et il est TRANSITOIRE

`IdunBattleLogic.Entities.Abilities.Active.Loki.ExemplarOfTheKauyonAbility$$ExecuteBehaviour` :

```
Teleport(Caster, TargetTile)
& If( <trigger@dsl.triggers+0x20>,
      AddEffect(0x49d, AbilityStateReference, Caster, Caster)
      & PerformAIAttackFromCurrentPosition(...)
      & RemoveEffect(Caster, Nullable(0x49d)),
      null )
& Spawn( First(CanAddUnit( Entity(<tuile du caster AVANT téléport>)
                           + SortByDistance(Randomize(AllTiles), <cette tuile>) ), 1),
         GetStringConstant(0x0) = "tauSmnDroneCommandLink",
         SpawnUnitOptions.WithStatsFromConfig(...)
           .onAppearance(+0x18) = AddTrait(0x418 = Stationary) )
```

L'effet **naît et meurt dans le cast** : il n'apparaît dans AUCUN snapshot RPC. Porteur == source
(Shadowsun se le pose à elle-même) ⇒ le régime **#382 / #366-r1-src** (porteur ≠ source) ne
s'applique pas ici.

## 3. Ce qui est confronté LIVE — deux bras, parce que `1087` est un NO-OP combat

`1087` figure toujours parmi les 81 abilities NO-OP de `docs/rl/combat-ability-coverage.md` : le port
ne sait pas rejouer le cast. La contribution de l'effet est donc mesurée **par décomposition
d'étage** (`probe_366r1_exemplar_kauyon_hits.py`) :

* **A** — Shadowsun CASTE `1087` sur une tuile lue du NATIF (`abilityTargets`, jamais re-dérivée) ;
* **B** — MÊME géométrie, Shadowsun **posée** sur cette tuile, attaque normale NUE.

`nA − nB` doit valoir `nrOfHits = 2`. Le PORT est ensuite confronté sur le snapshot du **bras B**
(positions déjà post-téléport ⇒ **aucune chirurgie de position offline**), sans puis avec l'effet.

| board | seed | ennemi | A (live) | B (live) | port sans 1181 | port avec 1181 |
|---|---|---|---|---|---|---|
| MC1_67 | 777 | `orksNob` | `[3162, 2678, 3979, 3979]` | `[3162, 2678]` | `[3162, 2678]` + `[]` | `[3162, 2678]` + `[3979, 3979]` |
| C3_01 | 909 | `orksNob` | `[2663, 2203, 2992, 2992]` | `[2663, 2203]` | idem B | + `[2992, 2992]` |
| C4_09 | 31337 | `necroWarden` | `[3606, 3686, 4488, 4488]` | `[3606, 3686]` | idem B | + `[4488, 4488]` |

**Rien n'est fitté** : le groupe porté est le MÊME sur les trois (`amount = min = max = 2992` =
`dmg[50] = 1662 × mult 180 %`, `count = 2`, `profile = Blast`) — c'est le **pipeline aval** qui varie
(2992 → ×1.33 = 3979 → ×1.50 = 4488 selon les %-mods et l'armure), et le port le suit bit-exact.
Les coups d'ARME de A et de B sont eux aussi bit-exacts entre eux : le téléport n'introduit aucun
écart (pas de confusion `HasMoved`).

## 4. Vue ROUGE

Mutant = le port d'AVANT, reconstitué par RETRAIT de l'inscription (l'effet retombe sur `BaseEffect`,
dont `additional_hit_groups` rend `None`) :

```
[MUTANT sans inscription] weapon=[3162, 2678] extra=[] -> n=2 (live A n=4, delta=-2)
```

Delta **−2 exactement** — c'est `GetNumberConstant(0x2f)` qui manque, pas un étage de dégât.
Garde : `tests/engine/runner/test_exemplar_of_the_kauyon_hits_live.py` (6 tests, 2 géométries,
65 s).

## 5. Le port

| pièce | fichier |
|---|---|
| classe d'effet | `engine/entities/effects/loki/hits.py::ExemplarOfTheKauyonAdditionalHitsEffect` |
| inscription | `engine/entities/effects/factory.py` (`"ExemplarOfTheKauyon_AdditionalHits"`) |
| mesure | `scripts/python/probe_366r1_exemplar_kauyon_hits.py` |
| garde | `tests/engine/runner/test_exemplar_of_the_kauyon_hits_live.py` |

## 6. Ce qui n'est PAS couvert

* **L'ability poseuse `1087` reste un NO-OP combat.** L'inscription est donc **DORMANTE dans le
  pipeline** : en self-play/replay-diff, le port ne pose jamais `1181` puisqu'il ne joue pas le cast.
  Elle mord dès que `1087` est portée. Le RE de l'ability est **fait et utilisable** (§2), y compris
  ses deux données de registre, relues au décompilé :
  `ExemplarOfTheKauyonAbility$$.ctor` = forme **FLAGS DIRECTS** (le littéral EST le masque effectif)
  `TargetingOptions..ctor(&opts, isSelfCasting = 0, &<TargetingRange statics>+0x48, forceMeleeTarget = 1,
  rules = 0x6001042, 0, 0)` puis `AActiveAbility..ctor(this, &opts, 2)` ⇒ `AbilityAttackType` = **2**
  (`Others`). `statics+0x48` est le MÊME champ que `DutyEternalAbility$$.ctor` (= `RANGE_WHOLE_BOARD`).
  Gate dynamique : `...$$GetDynamicInvalidTargetReason` = `IsFreeTile(target)` puis un `Any(...)` sur
  un prédicat capturant `(caster, this)` — l'i2 le dit « adjacent to an allied unit ».
* **La face PRÉDICTION n'est pas confrontée** : `IdunBattle.AI.Playbook.Loki.ExemplarOfTheKauyonPlaybook$$EvaluateNonComparable`
  n'appelle **aucun** `MakeDamagePredictions` — il émet une action d'utilité `Fix64(1)` par cible
  éligible. Il n'y a donc pas d'oracle de dégât natif à confronter pour ce cast.
* **`forceOverkill = false`** est lu mais non transporté (le canal `additional_hit_groups` ne porte
  pas ce flag) — no-op ici, `false` étant la valeur par défaut du port.
* **Le drone `tauSmnDroneCommandLink`** apparaît bien au cast (vérifié : `summons=['tauSmnDroneCommandLink']`)
  mais ses jumeaux d'aura `1306`/`1307` (#372) ne sont pas exercés par ce montage.
