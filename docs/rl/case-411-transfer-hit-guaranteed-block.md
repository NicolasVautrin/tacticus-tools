# case-411 — `DealDamageInfo[+0x1D]` : le TRANSFERT DE COUP, RE fermée et PORTÉ

> Résidu nommé en §7 de `case-407` : « le premier n'a pas de porteur identifié ». **Il en a deux.**
> L'écrivain est `IdunBattle.Operations.TransferHitOperation$$Execute` ; ses deux seuls déclencheurs
> DSL sont `DrawFireAbility` (1109) et `PrimarchOfTheFirstLegionAbility` (1511).
>
> **État (#411-r1)** : les deux inconnues de RE sont **FERMÉES** (§6), une affirmation de §2 est
> **RÉFUTÉE** (§6.3), et **`DrawFire` est PORTÉ et confronté** (§5). `PrimarchOfTheFirstLegion`
> reste NON PORTÉ, délibérément (§7).

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
→ `ActorStatisticsComponent$$RegisterBlockMade`).

⚠ `msg[+0x29] = 1` (posé par la même branche) **n'éteint PAS le crit du reste de l'attaque** — la
struct est passée par VALEUR et l'écriture arrive APRÈS le gate crit. Démonstration et canal réel
(`OngoingHitGroup+0x3c`, déjà porté) : §6.3.

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
SANS greffe (témoin)  victim_lost=3266  carrier_lost=0
AVEC DrawFire greffé  victim_lost=1644  carrier_lost=1632
```

3 coups sur 6 (les indices IMPAIRS) quittent la cible et frappent le porteur. Le verdict
« pas de porteur identifié » de `case-407` §7 est donc levé, et « dead code » est réfuté par
la mesure.

> ⚠ **Ces scalaires ont été CORRIGÉS par #411-r2** (`case-411-r2-ability-implicite.md`). Les
> valeurs publiées d'abord — témoin `6597/0`, greffe `3153/3488` — ne mesuraient **pas**
> l'attaque normale : `rl_duel act ability` sans `--ability` auto-résolvait vers la **DERNIÈRE**
> entrée d'`attackPlans`, soit l'ACTIVE du caster (`1006 MultiThreatEliminator`), pas les
> « 6 coups de mêlée ». Le probe nomme désormais l'ability, et `rl_duel` refuse l'ambiguïté.
> **Le verdict qualitatif est inchangé** (transfert observé, indices impairs) ; seuls les
> scalaires bougent. Corollaire pour le port : la base de dégât du coup transféré est à lire au
> décompilé — **aucun** des deux jeux de scalaires ne doit servir à l'ajuster.

## 5. Le PORT — LIVRÉ (#411-r1)

`DrawFire` (1109) est porté, sur le foyer que #366-r1 avait ouvert : l'intercepteur per-coup
d'`ExecuteHit`. Trois pièces, chacune à sa place native :

| pièce | fichier | ce qu'elle mirrore |
|---|---|---|
| `guaranteed_block` | `engine/services/damage_combat.py` | la branche `else` de `CalculateDamageOperation` — slot 4 `ApplyBlockDamage`, `didBlock` en dur, **0 tirage** |
| `_transferred(idx)` | `engine/runner/operations/damage_hits.py` | l'étape 5 d'`ExecuteHit`, branche `!HasValue` : dégât 0, resolve sur `[0,0]`, extinction du crit |
| `DrawFireTransfer` | `engine/runner/operations/triggers/loki/draw_fire.py` | `CreateTrigger` (les 5 gates) + `CreateBehaviour` (la feuille `TransferHit`) |

**La sous-attaque est une RE-ENTRÉE** dans `AttackDamageOperation.execute` contre le porteur —
donc aucun montant recopié, aucun scalaire ajusté : la base du coup transféré est la stat `Attack`
brute, exactement ce que recalcule `_reduced_bounds` (§6.1). Le levier
`skip_hit_count_query` porte `AttackDamageOptions[+0x28]` ; il vaut `False` par défaut, donc
**strictement no-op** sur tous les chemins existants.

**L'anti-récursion est HÉRITÉE du natif, pas ajoutée** : la sous-attaque repart à `hit_index 0`,
donc `AmountIsOdd` y est faux.

### Ce que la confrontation a mesuré

`probe_411r1_transfer_port.py` — port et natif sur le MÊME état pré-attaque, bras TÉMOIN sans
greffe. Deux couples (board, seed) : `MC1_67`/31337 et `C3_01`/777, chiffres natifs distincts,
verdict identique.

```
                        NATIF                    PORT (per-coup)
TEMOIN   victim=3433  carrier=0        [14, 14, 142, 100, 44, 112]   24 tirages
GREFFE   victim=1730  carrier=1608     [14,  0, 103,   0, 112,   0]  30 tirages
```

Le check de fond n'est pas un scalaire mais le **ledger de tirages** : `rng_draws = 2 × (resolve +
block_rolls)`. Bras greffé = **9 resolve** (6 coups + 3 sous-attaques) et **6 tirages de block**
(3 coups pairs + 3 sous-attaques). Si les coups transférés roulaient leur block, on lirait **9**.
C'est la propriété portée, mesurée et falsifiable.

⚠ **Écart d'échelle port/natif, PRÉ-EXISTANT et hors périmètre** : le port sous-estime le total
(426 contre 3433 sur le bras TÉMOIN, où aucun chemin #411 n'est actif). Le témoin le prouve
pré-existant ; les **ratios** sont cohérents (greffé/témoin : 0,504 natif contre 0,538 port ;
victime/porteur : 0,904 natif contre 0,935 port). À investiguer séparément —
`necroDestroyer` vs `astraBullgryn`, régime `--block-target 100,500`.

### Gardes

* `tests/engine/test_411r1_transfer_port_offline.py` — **17 tests**, qui comptent les TIRAGES et
  pas seulement les dégâts. **4 mutants tués** (route garantie qui roule le block → 7 rouges ;
  câblage débranché → 3 ; coup transféré remis dans la chaîne aléatoire → 2 ; crit non éteint → 1).
* `tests/engine/test_411_transfer_hit_wiring_offline.py` (#452) reste, et **skippe toujours** :
  son invariant interroge `ABILITY_TRIGGERS`, or ce port passe par l'intercepteur — le bus du port
  émet `On(6)`/`On(7)` une fois par ATTAQUE, `DrawFire` se déclenche par COUP. C'est le même choix
  qu'`HarlequinsPanoply`, pour la même raison. L'invariant garde donc la voie registre, la nouvelle
  garde couvre la voie livrée.

## 6. Les deux inconnues — FERMÉES (#411-r1)

### 6.0 Le fait structurant : le « message » d'`ExecuteHit` EST `AttackDamageOptions`

`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` passe à `ExecuteHit` une **copie des
0x90 octets** de la struct d'options. Tous les `msg[+0x2x]` de §1/§2 sont donc des champs
d'`AttackDamageOptions`, et `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget`
les remplit depuis `AttackDamageBehaviour+0x98..0x9e` (packing lu : `+0x28←b+0x9b`, `+0x29←b+0x99`,
`+0x2a←b+0x9a`, `+0x2b←b+0x9c`, `+0x2c←b+0x9d`, `+0x2e←b+0x98`, `+0x2f←b+0x9e` ; `+0x2d` reste 0,
`AttackDamageOperation$$Execute` l'écrit lui-même à `1` après la 1ʳᵉ série). Ce mapping était déjà
porté dans `operations/damage_hits.py` (`force_crit` = octet `+5` du `Nullable<AttackOptions>`).

### 6.1 La base de dégât du coup transféré — AUCUN second tirage

`IdunBattle.Core.HitDamage$$.ctor(damage)` (la surcharge à **un** argument, dont `TransferHit` est
le SEUL appelant de code) pose `min = max = damage` et `damageCap = null`. Or
`IdunBattle.Core.HitDamage$$GetDamage(random, ignoreSpread)` commence par

```
if (min == max) return min;                       // sortie IMMEDIATE, `random` jamais touche
if (ignoreSpread)  return (max + min) / 2;
return random.Range(min, max + 1);                // 1 tirage
```

⇒ **le coup transféré ne refait AUCUN spread** — sa base est exactement `hit.damage`, la valeur de
tête d'`ExecuteHit` sur la cible ORIGINALE (pour une normale, struct dégénérée `(Attack, Attack)`,
donc la stat brute pré-armure/pré-perçage). Cette base repasse ensuite **tout** le pipeline contre
le PORTEUR (armure, perçage, %-mods, limites), ce qui explique que `3488 != 3153` sans qu'aucun
scalaire n'ait à être ajusté.

**Le coup transféré PEUT criter** : rien dans les options du transfert ne pose `+0x29` (never crit)
ni `+0x2c` (always crit), donc son `ExecuteHit` exécute le gate crit normalement et **tire son
`RollCritical`** sur le porteur.

**Il vaut exactement 1 coup** : `GetAttackHits` lit `options[+0x18]` (`Nullable<int> hits`), laissé
à zéro par le ctor ⇒ `HasValue == false` ⇒ compte de base `1`.

### 6.2 Les trois octets — nommés par leur LECTEUR

| octet | lecteur unique | effet |
|---|---|---|
| `+0x28` | `AttackDamageOperation$$GetAttackHits` : `if (options[+0x28] != 0) return <compte brut>` | **court-circuite la requête de modificateurs de nombre de coups** (slot `0xb6` de `BattleQuery`). Le coup transféré reste à 1 coup quoi qu'il arrive — ni LightCover `-2`, ni bonus |
| `+0x2E` | `ADamageOperation$$GetCurrentAttackOrDefault` — **le paramètre PORTE CE NOM dans la métadonnée : `isOutsideAttack`** : `slot = isOutsideAttack ? 201 : 200` | le coup transféré s'exécute dans une attaque **SÉPARÉE**, pas dans l'`OngoingAttack` du frappeur. Aussi passé à `ExecuteAdditionalHitsWithoutDamageProfileType` |
| `+0x50` | `AttackDamageOperation$$Execute` : `if (options[+0x50] == 0 && attack[+0x34] == 1) ExecuteAdditionalHitsWithoutDamageProfileType(...)` | **pas de coups additionnels** pour le coup transféré |

**Réponse à « lequel interdit la re-transmission » : AUCUN des trois, directement.** Le dispatch
`On(7)` du coup transféré est inconditionnel — rien ne l'éteint. Ce qui rompt la chaîne est
**`+0x2E`**, et indirectement : l'attaque séparée repart avec son propre compteur de coups
(`attack+0x30` = `CurrentHitIndex`, cf. `Entities.Formulas.CurrentHitIndexFormula$$Calculate`),
donc à `0` — et le prédicat `AmountIsOdd(CurrentHitIndex)` de `DrawFire` est **faux sur 0**.
⚠ La garde est donc **propre au prédicat de l'ability**, pas au mécanisme : une ability de
transfert sans gate de parité boucle. `PrimarchOfTheFirstLegion` n'a pas d'`AmountIsOdd` — sa garde
reste **NON LUE**. Non lu également : si le slot `201` rend une attaque NEUVE à chaque transfert ou
une attaque « outside » réutilisée.

### 6.3 Correction de §2 — le crit du RESTE de l'attaque

« `msg[+0x29] = 1` éteint le crit du reste de l'attaque, un tirage crit de moins par coup restant »
est **FAUX**, pour deux raisons lues :

1. **`options` est passé par VALEUR.** `ExecuteHits` recharge sa copie depuis la struct d'origine
   **avant chaque** `ExecuteHit` ; l'écriture d'`ExecuteHit` sur `+0x29` meurt donc avec l'appel.
   Elle ne sert qu'aux relectures internes du même coup (construction de la `DealDamageInfo`).
2. **Elle a lieu APRÈS le gate crit** — le `RollCritical` du coup transféré est déjà consommé quand
   la relecture d'`UnitComponent+0x98` détecte le transfert.

Le canal réel d'extinction est `OngoingHitGroup+0x3c` (`isCriticalDamageAllowed`), **déjà porté**
(`crit_allowed` de `operations/damage_hits.py`) : `ExecuteHits` fait
`options[+0x29] |= (hitGroup[+0x3c] == 0)` en tête de coup et remet `hitGroup[+0x3c]` à
`options[+0x40] != null && Any(...)` — donc à `false` — dès qu'un coup **ne crite pas**. Un coup
transféré rend `didCrit = 0`, il éteint donc le crit **exactement comme n'importe quel coup
non-crité** : ce n'est pas un effet propre au transfert, et à `--crit 0,0` l'écart est nul.

**Le seul effet RNG propre au transfert** est donc celui de §2 : le coup transféré ne consomme
**ni tirage d'évasion ni tirage de block** sur la cible originale, tandis que l'attaque de
transfert en consomme un jeu complet (crit + évasion + block + resolve) sur le porteur.

### 6.4 Le tirage du slot 8 sur `[0,0]` — TRANCHÉ par la lecture

`ExecuteHit` n'appelle **aucun** slot 8 : la construction de la `DealDamageInfo` s'achève par la
sub-op `0x42` (`FUN_180028580(&., 0x42, ..)`), et c'est `DealDamage` qui enchaîne
`CalculateDamageOperation` puis `RandomlyResolveMinMaxDamage`. La branche transfert pose
`damage = 0` **en amont** de cette sub-op (`this[+0x34] = local_res10`), donc la cellule est
dégénérée et le resolve tourne dessus — sans gate de largeur, exactement comme `case-221`.
⇒ **un tirage consommé, valeur 0**. Le port le fait (`rng.next_internal(0, 1)`), et le ledger de
§5 le confirme indirectement : le bras greffé compte **9** resolve pour 6 coups + 3 sous-attaques.

## 7. Ce qui n'est PAS couvert

* **`1511 PrimarchOfTheFirstLegion` — NON PORTÉ, délibérément.** Arbre lu, jamais confronté. Son
  `transferTarget` sort d'un `AdjacentFriends → UnitsFromFaction(0xa) → Randomize → SortByFormula
  → First` : le `Randomize` **consomme du RNG** et l'ordre du pool source n'est pas lu. Le porter
  sans cette lecture donnerait un port au flux RNG faux — c'est-à-dire pire que pas de port. Il
  ajoute en plus un `AddEffect(1523)`. Seul porteur `darkaBossLion` (npc) : la même greffe s'y
  applique, non jouée.
* **La face ABILITY** : `AbilityDamageOperation$$ExecuteHit` pose lui aussi un `PendingHit`, donc
  `+0x1D` y est atteignable. Le port CÂBLE la branche dans les deux vecteurs de `_run_hits` (le
  mirror est le même), mais **elle n'est pas confrontée** de ce côté.
* **La collision `discard` × `transfer`** sur un même coup : l'ORDRE est désormais porté (le
  transfert gagne — `On(7)` efface le Nullable, la relecture teste `HasValue` en premier) et gardé
  par un test, mais jamais exercée LIVE : elle exige un porteur `HarlequinsPanoply` et un porteur
  `DrawFire` sur le même coup. Écart connu quand le transfert gagne : le port n'exécute pas le
  behaviour de pose du discard (qui consommerait le marqueur 1227).
* **`options[+0x50]`** : aucun gate posé. Le port FUSIONNE les deux voies natives de coups
  additionnels dans `execute_additional_hits`, alors que `+0x50` ne gate que
  `ExecuteAdditionalHitsWithoutDamageProfileType`. En poser un SUR-APPLIQUERAIT le natif. Écart :
  un coup transféré d'un attaquant portant des coups additionnels SANS profil en jouerait.
* **Plusieurs porteurs adjacents au même défenseur** : le natif évalue le trigger PAR PORTEUR, donc
  plusieurs `TransferHit` sur le même coup. Le port rend UN porteur (l'id le plus petit) — l'ordre
  d'abonnement natif n'est pas lu.
* **`ownerNeedsToBeAlive`** de `On(7)` : l'argument est le retour d'un virtuel de la classe
  d'ability (slot `+0x298`), non résolu. Le port exige le porteur vivant (choix conservateur).
* **L'écart d'échelle port/natif** mesuré en §5 (426 contre 3433 sur le TÉMOIN) : **pré-existant**,
  hors périmètre #411, non diagnostiqué.
