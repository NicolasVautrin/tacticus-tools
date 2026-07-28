# case-231 — socle `IsCharging` + `force_crit` : TacticalPrecision (1154) et MomentShackle (1184)

> **Build** `gqfc5mff6c`. **Deux abilities**, mais surtout **deux primitives partagées** que le port
> n'avait pas : le prédicat de **charge** et le flag **« always crit »** d'une attaque d'ability.
> Décompilé = vérité ; live = confirmation (4 scénarios discriminants, tous bit-exacts).

---

## 1. `IsCharging` — ce n'est PAS `HasMoved`

`IdunBattleLogic.Entities.DSLFactory$$IsCharging(a, b)` construit un prédicat dont l'`Evaluate`
appelle le slot `IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)`, dont le corps
tient en **deux termes** :

```
return AreEntitiesAdjacent(caster, target)
       && GetComponent<UnitComponent>(caster).ChargedUnitIds@+0x190.Contains(target.Id)
```

Le second terme est un `List<int>` sur le `UnitComponent` (confirmé par
`IdunBattle.Entities.Components.UnitComponent$$Copy`, qui le recopie en `List<int>` depuis `+0x190`).
Il a **exactement deux** manipulateurs natifs :

| Site | Effet sur `+0x190` |
|---|---|
| `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging` | **AJOUTE** l'id de toute unité adjacente à la position d'ARRIVÉE qui ne l'était PAS à la position de DÉPART |
| `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` | **VIDE** la liste (`List<T>.Clear()` inliné : `_version++`, `_size = 0`, `Array.Clear(_items, 0, size)`) |

`UpdateCharging` est appelé par les **deux** call-sites de `MoveUnitOperation$$Execute`, toujours
entre `KillSteppableUnits` et `SetMovedFlag` — c'est ce rang exact qu'a repris le port.

**Conséquences, et c'est là que le port aurait pu se tromper :**

1. « charger » ≠ « avoir bougé ». Une unité qui bouge **sans arriver au contact** de la cible, ou
   qui était **déjà adjacente avant son pas**, n'a pas chargé.
2. La portée temporelle « ce tour » vient de la **purge par `FinishUnitTurn`**, pas d'un compteur de
   tour. Le natif ne remet pas la liste à zéro au `StartTurnOperation$$ResetUnit` (relu : il ne
   touche que `+0x60`, `+0x179` et l'`ActorStatisticsComponent`).
3. Ni l'équipe ni la vie ne sont filtrées à l'écriture — le filtre vit chez le consommateur.

**Résidu nommé** : le lot d'effets extra-dégât `SmashaEad` / `AvalancheOfMuscle` / `FeederTendrils`
modélise ce même nœud natif par `has_moved` dans le canal *modifier*
(`engine/entities/effects/loki/extra_damage.py`). C'est une approximation **plus large** que le
prédicat réel, antérieure à ce lot, et **non touchée ici** (ses quatre datapoints live restent
valides). La rabattre sur `IsCharging` est une tranche séparée.

---

## 2. `force_crit` — l'octet **+5** du `Nullable<AttackOptions>`

Le 8ᵉ argument de `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` est un
`Nullable<AttackOptions>` de 0x28 octets, rangé par `AttackDamageBehaviour$$.ctor` en `this+0x98`.
`AttackDamageBehaviour$$ExecuteTarget` en **dépaquette les 7 octets de tête** dans le message de
dégât, dans un ordre qu'il faut lire pour ne pas se tromper de flag :

| octet des options | octet du message | rôle |
|---|---|---|
| `+0` | `+0x2e` | — |
| `+1` | `+0x29` | « never crit » |
| `+2` | `+0x2a` | overkill (posé aussi par `DamageProfile.HasTrait(0)`) |
| `+3` | `+0x28` | — |
| `+4` | `+0x2b` | **`force_overkill`** — celui de `FlailSwing` (1042), ce qui **CALE** la table |
| **`+5`** | **`+0x2c`** | **`force_crit`** |
| `+6` | `+0x2f` | — |

et `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` le consomme ainsi :

```
local_628 = <slot 4 de BaseUnitComponent+0x68> ? 1 : message[+0x2c]
if (message[+0x29] == 0) {
    if (local_628 == 0) isCrit = RollCritical(...)     # <- le SEUL chemin qui tire
    # sinon isCrit reste a 1, RollCritical n'est PAS appele
} else isCrit = 0
if (local_628 != 0) <slot 6 de BaseUnitComponent+0x68>   # consommation du crit garanti
```

Deux conséquences, **toutes deux nécessaires** au port :

* le crit est **acquis même si `CouldCrit` est faux** — et Titus a `CritChance = 0`, donc la voie
  normale ne peut *jamais* crit : sans le flag, le port rendrait tranquillement la valeur non-crit ;
* **aucun tirage n'est consommé** (le natif saute `RollCritical`) — à `cc >= 1` un port qui roulerait
  quand même désynchroniserait tout le flux RNG derrière.

`TacticalPrecision` est le **seul** porteur du registre à poser cet octet.

---

## 3. TacticalPrecision (1154, `ultraTitus`) — arbre

`IdunBattleLogic.Entities.Abilities.Active.Loki.TacticalPrecisionAbility$$ExecuteBehaviour` :

```
charging = IsCharging( caster@0x160, target@0x178 )
attack1  = AttackWithAttackDamage( caster@0x160, target@0x178, MinMaxDamage,
                                   Nullable(GetDamageProfile) = Bolter,
                                   Direct(GetHits() = nrOfHits = 1),
                                   AbilityOrEffect(0x482 = 1154),
                                   Nullable(AttackOptions{ octet +5 = 1 }) )   # ALWAYS CRIT
crit     = ConfigVar( 0x42 = extraCritDmg, level, config@0x60 )
add      = ChangeStat( owner@0x148, Position(10 = CriticalDamage, 0), mode 2 = Add,      Direct(crit) )
sub      = ChangeStat( owner@0x148, Position(10, 0),                  mode 3 = Subtract, Direct(crit) )
adjacent = AdjacentEnemies( caster@0x160, 1, 3 )          # == $$GetNonChargingAttackTargets
attack2  = AttackWithAttackDamage( caster@0x160, adjacent, MinMaxDamage2,
                                   Nullable(GetDamageProfile2) = Chain,        # == $$GetNonChargingAttackDamageProfile
                                   Direct(nrOfHits_2 = 3), AbilityOrEffect(1154), Nullable(<defaut>) )
inform   = Inform( 0xc0, charging )
ExecuteAtomic( inform & If(charging, (add & attack1) & sub, attack2) )
```

Les deux branches sont **exclusives** (`If` avec `else`), ce qui rend l'ability naturellement
discriminante : en charge = **1 coup Bolter force-crit sur la SEULE cible** ; sans charge = **3 coups
Chain sur TOUS les ennemis adjacents au CASTER** (la cible du message n'a alors aucun statut).

Le couple `ChangeStat` Add/Sub autour de l'attaque est le patron déjà porté pour
`HadesAutocannons` / `HeroicFusillade` (source `ChangeStat` partagée ⇒ net-nul).

**Hors périmètre, nommés** : le triggered `TacticalPrecision_ResetAbility$$CreateTrigger` =
`(On(0x2e revive) | On(0x2f resurrect)) & OwnerIsTarget` (ré-arme l'ability après un revive), et le
passif `FuelledByFury` (déjà entrée `R12` de l'inventaire).

---

## 4. MomentShackle (1184, `custoTrajann`) — arbre

`IdunBattleLogic.Entities.Abilities.Active.Loki.MomentShackleAbility$$ExecuteBehaviour` :

```
healAmt = ConfigVar( 0x20 = hpToHeal, level, config@0x60 )        # == $$GetHealAmount
heal    = Heal( caster@0x160, caster@0x160, healAmt, options = null )
turns   = TurnsFromRounds( GetNumberConstant(0x45 = nrOfRounds) )
<pred>  = AmountIsGreaterThanZero( StatAmount(caster@0x160, 7 = BlockChance, 0, 0, false) )
mod1    = AddDynamicStatModifierEffect( owner@0x148, 0x56f = 1391, stat 7 = BlockChance, turns )
mod2    = AddDynamicStatModifierEffect( owner@0x148, 0x570 = 1392, stat 8 = BlockDamage, turns )
eff     = AddEffect( 0x571 = 1393, AbilityStateReference, source = owner@0x148,
                     targets = owner@0x148, turns )
AActiveAbility.Execute( ((heal & mod1) & mod2) & eff )            # Execute PLAIN, pas ExecuteAtomic
```

**Pas de garde `Healable`** : contrairement à `CombatRestoratives` (1002), qui enveloppe son set dans
un `HealableUnitsSelector`, le call-site de 1184 passe le sélecteur CASTER **brut**. Le plafond
`hp_max` de `HealUnitOperation` suffit — un Trajann à PV pleins encaisse un heal de 0.

Les deux stat-mods n'ont **aucune classe d'effet dédiée** côté natif : ce sont des
`IdunBattle.Entities.Effects.DynamicStatModifierEffect` **génériques**, instanciés par deux lambdas
de `EffectsDatabase$$InitializeEffects` (localisées par les **XREFS** de
`DynamicStatModifierEffect$$.ctor` — 12 lambdas seulement, donc énumérables) :

| lambda | ctor lu | ⇒ effet |
|---|---|---|
| `…<InitializeEffects>b__14_400` | `DynamicStatModifierEffect(AbilityType(0x4a0 = 1184), 0x15 = 21 blockChance, isNegative = 0, 0)` | **1391** `MomentShackle_ExtraBlockChance` |
| `…<InitializeEffects>b__14_401` | `DynamicStatModifierEffect(AbilityType(0x4a0 = 1184), 0x14 = 20 blockDmg, isNegative = 0, 0)` | **1392** `MomentShackle_ExtraBlockDamage` |

**RÉSIDU NOMMÉ — le `<pred>`** : le décompilé **construit**
`AmountIsGreaterThanZero(StatAmount(caster, BlockChance))` puis n'en fait rien de visible (aucun des
trois nœuds suivants ne le reçoit dans ses arguments lus). Nœud réellement mort, ou consommateur
perdu par la décompilation d'un argument optionnel : le décompilé **ne tranche pas**. Le port ne le
matérialise donc PAS — l'inventer en gate ferait **disparaître** les deux stat-mods pour un porteur à
`BlockChance` de base 0, ce qui serait un refus **inventé**. La dégradation retenue va dans le sens
permissif (deux effets posés au lieu de zéro), comme toutes les règles de ciblage non portées.

**Hors périmètre, nommé** : la face TRIGGERED `MomentShackle_AttackAbility` (2× Bolter sur tout
ennemi qui QUITTE une case adjacente pendant la durée). Son trigger est LU —
`On(0x1f) & HasEffect(owner@0x148, 0x571, 0, 6) & (AreEnemies & IsAdjacent) & NOT(AreEqual(Tiles(actor@0x158), <selecteur dslFactory+0x190>))`
— et son behaviour est un `AttackWithAttackDamage` à `nrOfHits = 2`, profil
`GetDamageProfileOrDefault(0x14)`. L'effet 1393 est donc posé comme **marqueur inerte**, ce qui est
exactement sa nature côté natif.

---

## 5. `TARGETING_OPTIONS` — les deux masques sont des PRESETS statiques, pas des littéraux

Aucune des deux abilities n'appelle `TargetingOptions$$.ctor` : leur `.ctor` **recopie les 0x40
octets** d'un champ statique. Le masque effectif est donc la constante écrite par
`IdunBattle.Core.Services.TargetingOptions$$.cctor` à `<preset>+0x28` (piège documenté au CLAUDE.md,
2ᵉ forme). Lecture du `cctor`, preset par preset :

| ability | preset | `+0x00` isSelfCasting | `+0x08` range | `+0x20` forceMeleeTarget | **`+0x28` rules** |
|---|---|---|---|---|---|
| 1154 TacticalPrecision | `statics+0x40` | 0 | `TargetingRange statics+0x30` = `RANGE_ADJACENT` | 1 (`RangedBool.False`) | `TargetIsEnemy` |
| 1184 MomentShackle | `statics+0x280` | **1** | `TargetingRange statics+0x60` = `RANGE_SELF` | 1 | `CasterIsPossibleTarget \| CasterMatchesDynamicRule` |

Cohérence croisée : « cible ennemie adjacente » pour l'une, « self-cast, portée 0 » pour l'autre —
ce que disent aussi les i2. `AbilityAttackType` (3ᵉ argument d'`AActiveAbility..ctor`) : **0
DirectTargetAttack** pour 1154, **2 Others** pour 1184 (l'ACTIVE ne fait aucun dégât).

---

## 6. Validation live — 4 scénarios discriminants, tous bit-exacts

Runner isolé `MC1_67`, `ultraTitus` + `custoTrajann` vs `necroWarden` + `astraBullgryn`, rank 17.
Offline joué **avant** le live sur l'état dumpé + le PRNG dumpé ; comparaison des **deltas de PV par
unité**.

| # | Montage | Live | Offline | Verdict |
|---|---|---|---|---|
| 1 | Titus n'a PAS bougé, 2 ennemis adjacents, cast sur l'un | `u77 −3197`, `u79 −2203` | idem | **bit-exact** |
| 2 | Titus arrive AU CONTACT par son pas, 2 ennemis adjacents, cast sur l'un | `u79 −1944`, `u77 0` | idem | **bit-exact** |
| 3 | Titus **BOUGE**, mais la cible était **déjà adjacente avant le pas** | `u77 −4796`, `u79 −2203` | idem | **bit-exact** |
| 4a | MomentShackle, Trajann à PV pleins | heal 0 ; `blockChance +20`, `blockDamage +1197` | idem | **match** |
| 4b | MomentShackle, Trajann à 2361/10038 | heal **+5983** | idem | **bit-exact** |

**Le scénario 3 est le test du socle** : `HasMoved` est VRAI et pourtant c'est la branche
NON-CHARGE qui tourne (3 coups Chain sur *deux* cibles). Un port dont le pivot serait `HasMoved`
aurait pris la branche CHARGE — 1 coup sur *une* cible. Les deux observables sont incompatibles :
c'est ce qui rend la primitive vérifiable, et pas seulement plausible.

**A/B du flag `force_crit`** (offline, même état et même PRNG, avec le `ChangeStat(+extraCritDmg)` de
l'arbre appliqué) : `force_crit=True` → **4896** · `force_crit=False` → **3401**. Le flag porte donc
bien le nombre, et pas seulement le drapeau `crits`.

**Magnitudes des deux stat-mods** (rank 17 ⇒ `activeAbilityLevel = 50`, `multiplier = 180 %`) :
`blockChance[49] = 20` (absent de `variablesAffectedByRarityBonus` ⇒ **non** scalé) et
`blockDmg[49] = 665 × 1,8 = 1197` (présent ⇒ scalé). `statModSources` live rend **20** et **1197**.

### Confonds écartés (et pourquoi ils comptent)

* **`templChampion` comme cible** — première mesure : live 2971 vs offline 2615. Cause :
  `MartialSuperiority` riposte 2× Power **avant** l'attaque adverse (et `Parry` retire un coup aux
  multi-hits mêlée) ⇒ le flux RNG est décalé **avant** le tirage de Titus. Cible remplacée ; ce
  n'était pas un écart de port.
* **`necroWarden` et `LivingMetal`** — +854 PV observés hors cast (10 % du max, régénération de
  début de tour). On ne mesure donc jamais à cheval sur une fin de tour.
* **Harnais** : `applyAction {kind:"move"}` **ignore la portée** mais rend `ok = True` *même quand le
  pas est refusé* (tuile occupée / non marchable) ; et l'enveloppe `ok` du RPC `applyAction` vaut
  True même quand `actions[0].ok` est faux. Les deux ont produit un montage à moitié fait comparé à
  un offline complet. Le test relit désormais la position après chaque pose et lit `actions[0]`.

---

## 7. Ce qui n'est PAS couvert

* La face **TRIGGERED** de MomentShackle (`MomentShackle_AttackAbility`) : RE faite (§4), port non
  fait — le vecteur `On(0x1f)` (mouvement) n'a aucun consommateur porté.
* `TacticalPrecision_ResetAbility` (re-arme après revive) : RE faite (§3), port non fait.
* Le rabattement du lot `extra_damage` (`has_moved`) sur le vrai `IsCharging` (§1).
* Le `<pred>` mort/perdu de MomentShackle (§4).
* Le cas `>2 joueurs` de la purge `FinishUnitTurn` : inchangé, elle est per-unité.
