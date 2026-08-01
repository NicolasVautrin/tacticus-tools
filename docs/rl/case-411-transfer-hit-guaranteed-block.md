# case-411 — `DealDamageInfo[+0x1D]` : l'écrivain est le TRANSFERT DE COUP, et il est CONFRONTABLE

> Résidu nommé en §7 de `case-407` : « le premier n'a pas de porteur identifié ». **Il en a deux.**
> L'écrivain est `IdunBattle.Operations.TransferHitOperation$$Execute` ; ses deux seuls déclencheurs
> DSL sont `DrawFireAbility` (1109) et `PrimarchOfTheFirstLegionAbility` (1511). La mécanique est
> **confrontée live** (§4). Le PORT reste ouvert — deux inconnues de RE nommées en §6.

## 1. La chaîne, lue de bout en bout

```
IdunBattle.Operations.AttackDamageOperation$$ExecuteHit         (per-COUP, familles ATTACK et ABILITY)
  1. IdunBattle.Core.HitDamage$$GetDamage(<struct du message>)          -> damage
  2. defenderUnitComponent[+0x98] = Nullable<AttackHit>(damage, profile, discard: 0)
  3. gate crit : msg[+0x29] (« never crit ») / msg[+0x2c] (« always crit ») -> slot 0xa RollCritical
  4. dispatch  EventTriggerType.PreAttackHit (6)  PUIS  PreAttackDamageHit (7)
  5. RELECTURE de defenderUnitComponent[+0x98] :
       !HasValue      -> damage = 0 ; msg[+0x29] = 1 ; critInfo = {0,0}
                         et  DealDamageInfo[+0x1D] = 1        <-- LE CHAMP
       HasValue+discard -> return (OperationResult memset 0)  <-- l'autre mécanique (#366-r1)
  6. IdunShared.Battle.DamageProfile$$HasTrait(0) -> msg[+0x2a] = 1  -> DealDamageInfo[+0x1E]
  7. sub-op 0x42 (DealDamage) avec la DealDamageInfo
```

`DealDamageInfo` (le type est nommé : `IdunBattle.Operations.DealDamageInfo`, 3ᵉ paramètre de
`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`) porte donc trois octets
voisins, **et chacun vient d'une source distincte** :

| offset | valeur écrite par `ExecuteHit` | sens |
|---|---|---|
| `+0x1C` | `critInfo.didCrit` (slot 0xb `CalculateCriticalDamage`) | a crité — cf. `case-407` §2 |
| `+0x1D` | `!defenderUnitComponent[+0x98].HasValue` | **le coup a été TRANSFÉRÉ** |
| `+0x1E` | `DamageProfile.HasTrait(0)` | `NoBlocking` — porté (#65) |

⚠ Le même booléen `+0x1D` est recopié une seconde fois dans la struct, à **`+0xA4`**
(`CalculateDamageOperation` le reporte en `DamageAppliedResult+0x94`). Deux lecteurs, une source.

## 2. Ce que `+0x1D` change, exactement

`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation` :

```
if (damageInfo[+0x1E] == 0) {                       // pas de trait NoBlocking
    if (damageInfo[+0x1D] == 0) {
        r = slot 3  ApplyRandomEvasion(evasionChance, damage, attacker, defender)
        if (!r.didEvade) { b = slot 2  ApplyRandomBlockDamage(blockChances, damage) ;
                           damage = b.damage ; didBlock = b.didBlock }
        else didEvade = 1
    } else {
        damage  = slot 4  ApplyBlockDamage(blockChances, damage)      // AUCUN tirage
        didBlock = 1                                                  // posé EN DUR
    }
}
```

et la surcharge slot 4 (`IdunBattle.Core.Services.DamageCalculations$$ApplyBlockDamage(blockChances,
currentDamage)`) est **purement arithmétique** :

```
d = (blockChances == null || blockChances.Count == 0) ? currentDamage
                                                      : currentDamage - blockChances[0].<+0x10>
return Math.Max(0, d)
```

⇒ **un coup transféré ne consomme NI tirage d'évasion NI tirage de block** — la même signature RNG
que l'exclusion par la failed-list de `case-407`, mais obtenue par un chemin entièrement différent.
Il compte malgré tout comme un BLOCK (`didBlock = 1` → `OperationResult[+0x22]` → `RegisterBlocks`
→ `ActorStatisticsComponent$$RegisterBlockMade`) et il éteint le crit du RESTE de l'attaque
(`msg[+0x29] = 1` est relu par tous les coups suivants de la même série, qui sautent alors
`RollCritical` : **un tirage crit de moins par coup restant**).

## 3. L'écrivain, nommé

`IdunBattle.Operations.TransferHitOperation$$Execute(caster, originalTarget, transferTargets,
abilityOrEffect)` — les paramètres de Ghidra sont décalés d'un cran (retour struct + `this` de
l'opération), le décalage est **vérifié** par `Core.Services.OperationProcessor$$TransferHit`, qui
l'appelle avec `op = processor[+0x120]` et repasse les quatre arguments tels quels :

```
comp = originalTarget.GetComponent<UnitComponent>()          // même classe qu'ExecuteHit
if (comp[+0x98].HasValue) { hit = comp[+0x98].Value ;
                            comp[+0x98] = default ; }        // <-- L'ÉCRITURE
                                                             //     (les 0x10 octets remis à 0)
else return
foreach (t in transferTargets) {
    <event de flux 0x23 : {0xb4: caster.Id, 0xb7: originalTarget.Id, 0xb8: t.Id}>
    opts = new AttackDamageOptions(new HitDamage(hit.damage))
    opts[+0x10] = Nullable<DamageProfileType>(hit.damageProfile)
    opts[+0x28] = 1 ; opts[+0x2E] = 1 ; opts[+0x50] = 1        // <-- non mappés, cf. §6
    result.Combine( processor.<slot 0x3c AttackDamage>(caster, t, abilityOrEffect, opts) )
}
```

`IdunBattle.Operations.TransferHitOperation$$GetPendingHit(originalTarget)` fait la **même** écriture
(lire-puis-effacer) ; il n'a aucune xref de code (uniquement des entrées de vtable).

`IdunBattle.Core.AttackHit$$.ctor(damage:Int32, damageProfile:DamageProfileType, discard:Boolean)`
donne la disposition : `+0x00 damage`, `+0x04 damageProfile`, `+0x08 discard`. Ses quatre appelants
sont `AttackDamageOperation$$ExecuteHit`, `AbilityDamageOperation$$ExecuteHit` (donc `+0x1D` est
atteignable des DEUX familles), `DiscardHitOperation$$Execute` (la mécanique VOISINE — elle réécrit
`discard = 1` au lieu d'effacer, c'est `HarlequinsPanoply`, portée en #366-r1) et
`UnitComponent$$Copy`.

### Les deux déclencheurs, et rien d'autre

Xrefs entrantes de `IdunBattleLogic.Entities.DSLBehaviors$$TransferHit` : **exactement deux**
`CreateBehaviour`. Recoupé par une seconde source indépendante,
`docs/rl/dsl-usage/dsl-usage-primitives.tsv`, qui compte `owners = 2` pour cette primitive.

```
DrawFireAbility$$CreateTrigger                       (TriggeredAbilityType.DrawFire = 1109)
    On(EventTriggerType.PreAttackDamageHit = 7, ownerNeedsToBeAlive: <slot 0x298 de la classe>)
  & !AreEqual(Owner@DSLSelectors+0x30, Target@+0x60)
  &  AreFriends(Owner@+0x30, Target@+0x60, ByCurrentTeam, anyEntity: false)
  &  IsAdjacent(Owner@+0x30, Target@+0x60, UnitSelectionType.OnlyTargetable = 2)
  &  AreEnemies(Caster@+0x48, Target@+0x60, ByCurrentTeam)
  &  AmountIsOdd(CurrentHitIndex)                    <-- « half of the hits (rounded down) »

DrawFireAbility$$CreateBehaviour
    Inform({ 0x83 : TriggerBoolNumber(AmountIsEqual(CurrentHitIndex, <DSLFormulas+0x20>)) })
  & TransferHit(caster: Caster@+0x48, originalTarget: Target@+0x60, transferTarget: Owner@+0x30)
```

i2 : « Any friendly adjacent units hit by enemy attacks have half of the hits (rounded down) hit the
Terminator instead. » — l'arbre le dit mot pour mot. `PrimarchOfTheFirstLegionAbility` a la même
feuille `TransferHit`, avec un `transferTarget` sélectionné parmi les alliés adjacents de faction
Dark Angels (`AdjacentFriends` → `UnitsFromFaction(0xa)` → `Randomize` → `SortByFormula` → `First`),
plus un `AddEffect(0x5f3 = 1523 PrimarchOfTheFirstLegion_ExtraDamage)`.

Slots `DSLSelectors` utilisés : mapping déjà établi par le dépôt (`case-224-is-in-contagions-…` §3,
`case-303` §1) — `+0x30 Owner`, `+0x48 Caster`, `+0x60 Target`.

## 4. Gate de confrontabilité — CONFRONTÉ

| ability | porteurs (`unit_map find --ability`, re-dérivé du gameconfig) | catégorie |
|---|---|---|
| `DrawFire` 1109 | `blackNpc2Terminator`, `blackSmnTerminator` | **npc + SUMMON** |
| `PrimarchOfTheFirstLegion` 1511 | `darkaBossLion` | npc |

Aucun HERO, aucune MoW, **aucune relique** — les trois états de la gate relique ne s'appliquent pas.
La voie SUMMON est **fermée par mesure, pas par supposition** : l'unique ability qui déclare
`blackSmnTerminator` est `EnvFactionSummons:BlackLegion`
(`units.abilities[…].constants.unitId`), et **aucune unité du catalogue ne la porte** (balayage des
trois buckets `lineup`/`npc`/`summons`). C'est le cas `case-92` §5bis recours 2 : summon SANS
invocateur ⇒ recours 3, la **GREFFE du passif** sur une unité du pool.

La greffe est légitime ici : `CreateTrigger` ne lit du porteur que sa POSITION (`IsAdjacent`) et son
camp (`AreFriends`) ; `CreateBehaviour` ne lit ni stat, ni trait, ni arme ; et l'entrée gameconfig de
`DrawFire` n'a **ni variable ni constante** (`{"upgrades": null, "variables": {}}`).

**Mesure** — `probe_411_transfer_hit_guaranteed_block.py`, `MC1_67` / seed 31337,
`necroDestroyer` (6 coups de mêlée) attaque `astraBullgryn`, `astraCreed` adjacent porte la greffe.
Deux runners identiques à un bit près (la greffe), `--crit 0,0 --crit-target 0,0 --block-target 0,0`,
`--unit-stat "necroDestroyer:Movement=12"` :

```
SANS greffe (témoin)  victim_lost=6597  carrier_lost=0
AVEC DrawFire greffé  victim_lost=3153  carrier_lost=3488
```

3 coups sur 6 (les indices IMPAIRS) quittent la cible et frappent le porteur. **Rejoué à
l'identique sur deux sessions Frida distinctes (7 puis 8, même build `rnca9r7q6c`) : chiffres
bit-identiques.** Le verdict « pas de porteur identifié » de `case-407` §7 est donc levé, et
« dead code » est réfuté par la mesure.

## 5. État du PORT

**Non porté.** Le moteur ne modélise ni `TransferHit`, ni le `PendingHit` : `grep` rend zéro sur
`TransferHit` / `pending_hit` dans `scripts/python/engine`. Conséquence : `+0x1D` est aujourd'hui
**inatteignable** dans le port — rien n'efface jamais de `PendingHit`, donc la route de garantie
n'est jamais prise, et le port est *localement* correct tant que 1109/1511 n'y entrent pas.

Garde de câblage : `tests/engine/test_411_transfer_hit_wiring_offline.py` (4 verts + 1 skip
tri-état). Elle verrouille les trois données périssables (ids d'enum, porteurs, absence
d'invocateur) et le **montage** de greffe ; son 5ᵉ test est l'invariant : *si* 1109 ou 1511 entre
dans `ABILITY_TRIGGERS`/`CUSTOM_TRIGGERED_ABILITIES`, l'intercepteur per-coup DOIT exposer la route
de garantie. Sans elle, un port de `TransferHit` ferait tirer le block d'un coup transféré alors que
le natif ne tire pas — désynchronisation SILENCIEUSE de tout le flux RNG de l'attaque à partir de
ce coup.

Le foyer d'accueil existe déjà : `HarlequinsPanoplyHitInterceptor.should_discard(idx)`
(`operations/damage_hits.py`, étape 5 d'`ExecuteHit`) est **exactement** le point où `+0x1D` se
décide. Le port se pose là, à côté du `discard`, pas ailleurs.

## 6. Ce qui MANQUE pour porter (deux inconnues de RE, nommées)

1. **La base de dégât de l'attaque de transfert.** `TransferHitOperation` rejoue
   `AttackDamage(caster, transferTarget, opts)` avec `opts.damage = HitDamage(hit.damage)`, où
   `hit.damage` est la sortie de `HitDamage$$GetDamage` en TÊTE d'`ExecuteHit` — pour une attaque
   NORMALE, la struct y est dégénérée (`Attack, Attack`), donc une valeur **brute** (pré-armure,
   pré-perçage). Reste à lire `IdunBattle.Operations.AttackDamageOperation$$Execute` /
   `$$GetHitDamage` pour savoir si cette borne unique subit encore le `DamageSpreadPercentage` et si
   le coup transféré peut critiquer. **Ne pas ajuster ce paramètre sur le scalaire `3488`** : c'est
   exactement l'anti-patron « fitter un scalaire ».
2. **Les trois octets d'options** posés après le ctor — `AttackDamageOptions[+0x28]`, `[+0x2E]`,
   `[+0x50]` = 1. `IdunBattle.Operations.AttackDamageOptions$$.ctor(damage)` met tout à zéro de
   `+0x10` à `+0x88` et ne copie que le `HitDamage` en `+0x00` : ces trois-là sont donc des
   intentions explicites (au moins l'une doit interdire la re-transmission du coup transféré, sans
   quoi deux porteurs adjacents boucleraient). Le mapping se lit dans
   `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` /
   `AttackDamageOperation$$Execute`.

Un troisième point, mesurable et non mesuré : le coup transféré consomme-t-il quand même le tirage
du slot 8 (`RandomlyResolveMinMaxDamage`, appelé sans garde de largeur par la sub-op 0x42) sur une
cellule `[0,0]` ? La lecture dit oui ; aucun capteur ne l'a confirmé.

## 7. Ce qui n'est PAS couvert

* **`PrimarchOfTheFirstLegionAbility`** : arbre lu, non confronté (seul porteur `darkaBossLion`, npc
  — la même greffe s'y applique, non jouée).
* **La face ABILITY** : `AbilityDamageOperation$$ExecuteHit` pose lui aussi un `PendingHit`, donc
  `+0x1D` y est atteignable ; non confronté.
* **La collision `discard` × `transfer`** sur un même coup (`On(6)` pose `discard = 1`, `On(7)`
  efface le Nullable ⇒ la branche `!HasValue` gagne) : lue, jamais exercée.
* **`ownerNeedsToBeAlive`** de `On(7)` : l'argument est le retour d'un virtuel de la classe
  d'ability (slot `+0x298`), non résolu.
