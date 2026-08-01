# case-389 — `RammingSpeed` (1059) face COMBAT : le nœud `<DSLTriggers+0x20>` est NOMMÉ, l'ability entre au registre

Clôt le résidu `#383-r1`. Suite ouverte : `#389-r1` (§5).

## 1. Le verrou, et comment il tombe

`#383` §6 refusait de porter `RammingSpeedAbility$$ExecuteBehaviour` pour UNE raison : le `If` qui
gate les deux attaques lit `<DSLTriggers+0x20>`, un champ alloué par
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` (`new <DAT_183343468>(dsl.state@+0x10)`)
dont **la classe n'est nommée nulle part**. Le slot de metadata-usage n'a **qu'une seule xref** dans
tout le binaire — donc la classe n'est instanciée nulle part ailleurs, donc aucun
`DSLTriggers$$<X>` nommé ne la désigne.

**Verdict : `<DSLTriggers+0x20>` = `IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger`**, la
propriété DSL `OwnerIsAlive`. Trois sources indépendantes, aucune n'étant suffisante seule :

1. **GABARIT.** Le ctor pose UN champ (`+0x10`) ⇒ taille 24, parent `IdunBattle.DSL.AbilityTrigger`
   (taille 16). `data/symbols/<build>/frida/classes.tsv` en compte **23**.
2. **TYPE DU CHAMP.** L'argument est `dsl.state` (un `MatchState`), pas un sélecteur. Sur les 23,
   **21** ont un allocateur NOMMÉ (`DSLTriggers$$CanMove` → `DAT_18333f810`, `$$HasTile` →
   `DAT_183329628`, `$$IsMoving` → `DAT_1833aa4c0`, `$$IsWounded`, `$$IsEffectActive`,
   `$$IsEffectCreatedThisTurn`, `$$TriggeringAbilityIsNone`, `$$IsAbilityCountedOnlyOnce`,
   `$$IsPartialAttackAbility`, `$$CanBeDisplaced`, `$$IsSpecialActiveAbility`, …) qui leur passe un
   **SÉLECTEUR** — leur slot de classe n'est donc pas `DAT_183343468`. Restent **DEUX** classes sans
   allocateur nommé, et ce sont exactement les deux qu'`InitializeShared` alloue :
   * `IsMeleePositionAbilityTrigger` — son `ShouldTrigger` invoque le **slot d'interface 9
     d'`IBattleQuery`** SUR `this+0x10` ⇒ son champ est un **BattleQuery** = `dsl+0x28` = `<+0x18>` ;
   * `OwnerIsAliveAbilityTrigger` — son champ part en 2ᵉ argument d'`UnitExtensions$$IsAlive(unit,
     state)` ⇒ un **MatchState** = `dsl+0x10` = `<+0x20>`.
   L'appariement est FORCÉ par le type, il n'y a pas de degré de liberté.
3. **CORPS TRIVIAL DONT LE SLOT EST L'UNIQUE OPÉRANDE.** `DSLTriggers$$IsRangedPosition` est
   littéralement `AbilityTrigger$$op_LogicalNot(this+0x18)` — ce qui NOMME `<+0x18>` =
   « IsMeleePosition » indépendamment, et confirme la moitié battleQuery. (Même voie que celle qui
   avait nommé `<+0x28>` = `IsTurnOf(Owner)` : `DSLTriggers$$IsTurnOf` alloue le MÊME
   `DAT_1833ab568` avec les MÊMES arguments — reproduit ici.)

Corps du nœud (`OwnerIsAliveAbilityTrigger$$ShouldTrigger`) :

```
if (!EntityExtensions.IsUnit(entities.Owner@+0x18))  return true;
return UnitExtensions.IsAlive(entities.Owner@+0x18, this._state@+0x10);
```

Les TROIS porteurs de `<+0x20>` (xrefs du motif `<dsl+0x88>+0x20`) le placent au même endroit —
APRÈS un déplacement, AVANT l'attaque : `RammingSpeedAbility`, `SkyStrikeAbility`,
`ExemplarOfTheKauyonAbility`. C'est le gate « le porteur a-t-il SURVÉCU au déplacement ? ».

⚠ **Correction d'un mirror FAUX déjà en place** : `sky_strike_tree` écrivait
`If(IsAlive(caster) & IsAlive(target), …)` pour ce MÊME nœud. Le nœud natif est **sans opérande** et
ne teste que l'Owner. Les deux lectures coïncident sur tout montage joué (la cible ne peut pas
mourir entre le move et l'attaque), mais le conjoint `IsAlive(Target())` était inventé. Corrigé.

## 2. L'arbre porté, mirror 1:1

```
amount = RandomAmount( GetVariableForLevel(0xc = minDmg), GetVariableForLevel(0xd = maxDmg) )
prof   = GetDamageProfile(config@0x60)                                    # constants.damageProfile
ifMove = If( NOT IsAdjacent(Caster@0x48, Target@0x60, 3),
             MoveUnit(Caster@0x48, GetTileToMoveTo(), <options ZERO>) )
atk1   = AttackWithAttackDamage( Owner@0x30, Target@0x60, amount, prof,
                                 hits = GetNumberConstant(0x2f = nrOfHits), …, 2 )
atk2   = AttackWithAttackDamage( Owner@0x30, Owner@0x30,  amount, prof,
                                 hits = GetNumberConstant(0x32 = nrOfHits_2), …, 2 )
addEff = AddEffect( 0x44a = 1098 RammingSpeed_ExtraExplode, AbilityStateReference,
                    source = Owner@0x30, targets = Owner@0x30, <options ZERO> )
Execute( (ifMove + addEff) + If(OwnerIsAlive, atk1 + atk2) )              # PLAIN, pas d'ExecuteAtomic
```

**Deux surcharges homonymes résolues PAR L'ADRESSE DU CALL**, pas par le nom :

| appel | overload retenu | ce qui tranche |
|---|---|---|
| `AttackWithAttackDamage` | celui dont `hits` est un **INT** (il l'emballe lui-même en `ConstantAmount`) | le natif passe le retour d'un `GetNumberConstant` (un int) ; les deux autres surcharges de même arité prennent un NŒUD, et leurs xrefs entrantes ne contiennent pas `RammingSpeedAbility$$ExecuteBehaviour`. Elle construit `AttackDamageBehaviour` + `AttackBehaviour` ⇒ famille **ATTACK**, `native_factory="attack"`. |
| `AddEffect` | l'overload 6-args dont le dernier paramètre est une **struct d'options de 0x20 octets copiée par valeur** | l'autre 6-args prend un NŒUD de durée ; le natif zéroifie 4 qwords et passe leur adresse. Options ZERO ⇒ **aucun override de durée** (`duration_rounds=None`) et une SOURCE explicite (`Owner`). |

## 3. Les deux données de registre, LUES au ctor

```
RammingSpeedAbility$$.ctor  — forme « FLAGS DIRECTS » (7 arguments, le `range` est une struct
                              TargetingRange de 0x18 octets copiée depuis les statiques) :
    TargetingOptions..ctor(&opts, isSelfCasting = 0, range = &<TargetingRange statics>+0x18,
                           forceMeleeTarget = 1, rules = 0x4002, 0, 0)
    AActiveAbility..ctor(this, &opts, 0)          <- 0 = AbilityAttackType.DirectTargetAttack
```

* `rules = 0x4002` = `TargetMatchesDynamicRule (0x2) | TargetIsEnemy (0x4000)` — le littéral EST le
  masque (ce n'est ni la surcharge `(this, template)` ni `(this, template, additionalRules)`, dont
  les listes d'appelants ne contiennent pas ce ctor) ;
* `range` = `TargetingRange` statics `+0x18` = `RANGE_FROM_CONFIG` → `overrideRange =
  GetNumberConstant(0x16 = range)` = 5 ;
* `forceMeleeTarget = 1` = `RangedBool.False`.

`getDynamicInvalidTargetReason` est passé **nul** : le bit `0x2` consulte l'**override virtuel**
`RammingSpeedAbility$$GetDynamicInvalidTargetReason`, porté ici :

```
casterTile = casterTiles[0]
movedOrOffTile = DidMove(caster) || GetMainTile(caster) != casterTile
isAdjacent     = battleQuery.<slot 0x61>(casterTiles, target)
if (movedOrOffTile && !isAdjacent)                         return 0x10;       # CasterHasNotMoved
if (!isAdjacent) {
    if (battleQuery.<slot 0x4f>(target,1,1,1).Count < 1)   return 0x20;       # TargetHasFreeAdjacentTile
    tile = GetTileToMoveTo().SelectTile(<ctx: caster, target, casterTile>)
    if (tile != null && battleQuery.<slot 0x14>(caster, tile, 0) non vide) return 0;
    return 0x8000000;                                                        # TargetIsInRange
}
return 0;                                                  # DÉJÀ au contact -> toujours valide
```

Le test de CHEMIN (`slot 0x14`) est SUBSUMÉ côté port : `ramming_speed_tile_to_move_to` n'émet que
des tuiles issues du nœud DSL `MovableTilesInRange`, qui porte le gate d'expansion #131 depuis
`case-381-r1`. Les résidus qui restent sur ce pool (`#381-r2` `FlyPathfinder`, `#381-r3` voisinage
`evenq` vs `boardGraph.neighbours`) peuvent donc faire ACCEPTER une cible que le natif refuse.
Écart d'acceptation, jamais de refus inventé.

## 4. La confrontation LIVE

`probe_389_ramming_speed_combat_port.py` — **état + rng dumpés AVANT le cast** (recette
`probe_226r`), cinq observables comparés : tuile d'arrivée, coups sur la CIBLE, coups sur SOI,
POSE de l'effet 1098, et **les PV finaux de toutes les unités**. Montage hérité de `probe_353r1`
(greffe `orksKillaKan ← 1059`, `drive_to` + `ensure_turn`, board CHOISI).

| bras (board / seed / PV joueur) | tuile | coups cible | coups soi | pose 1098 | PV finaux |
|---|---|---|---|---|---|
| MC1_67 / 38900 / 900k | (5,7) **==** | 6 **bit-exact** | 2 **bit-exact** | oui/oui | **4/4 ==** |
| MC1_67 / 38901 / **5000** (caster TUÉ) | (5,7) **==** | 5 **bit-exact** | 2 **==** | oui/oui | **4/4 ==** |
| C1_20 / 38903 / 900k | (2,6) **==** | 4 **bit-exact** | 3 **bit-exact** | oui/oui | **4/4 ==** |
| MC1_63 / 38903 / 900k | (0,3) **==** | 4 **bit-exact** | 3 **bit-exact** | oui/oui | **4/4 ==** |
| C1_03 / 38905 / **5000** (caster TUÉ) | (3,3) **==** | 4 **bit-exact** | 2 **==** | oui/oui | **4/4 ==** |

(Tous re-joués APRÈS le rebase sur `origin/master` — dont `case-381-r1`, qui a changé le nœud
`MovableTilesInRange` sous ce port : le gate d'expansion #131 et la signature `ignore_flags` /
`ignore_units_on_tiles`. La tuile de charge est inchangée sur les 5 bras.)

**Le bras LÉTHAL est le seul canal où la POSE de 1098 est observable EN DÉGÂT**, et il clôt un
résidu de `#383` §7. `orksKillaKan` porte le trait `Explodes` : quand le contrecoup le tue, la nova
part PENDANT le cast et `ExplodesAbility$$GetDamage` lit `HasEffect(Owner, 1098)`. Mesure MC1_67 :
le voisin perd **3750** PV = **75 %** du maxPV du caster (5000) = `explodesDmg` (25) +
`extraDmgPct` (50) — donc la **branche VRAIE du `ConditionalAmount`**, jusqu'ici exercée
uniquement offline. La garde `--mutate no-effect` en mode léthal rend **1250** (25 % seuls) : le
bras DISCRIMINE.

Sept gardes adversariales, **chacune ROUGE** (le port muté DIVERGE du natif) :

| mutation | ce qu'elle ampute | ce qui diverge |
|---|---|---|
| `no-move` | la feuille `MoveUnit` | tuile, coups cible, coups soi |
| `no-self-attack` | le 2ᵉ `AttackWithAttackDamage` (= l'état d'AVANT #389) | coups soi |
| `swap-hits` | `nrOfHits_2` lu comme `nrOfHits` | coups soi |
| `gate-closed` | `<DSLTriggers+0x20>` forcé à FAUX | coups cible **et** coups soi |
| `self-attack-on-target` | le contrecoup dirigé sur la CIBLE | PV finaux |
| `no-effect` | la feuille `AddEffect` | pose 1098 |
| `no-effect` **en mode léthal** | idem, mais mesuré EN DÉGÂT | PV du voisin (1250 vs 3750) |

Gardes offline : `tests/engine/runner/test_389_ramming_speed_combat_offline.py` (13 cliquets) —
dont la **face que le live n'atteint pas** : gate FERMÉE (owner mort ⇒ aucune attaque, mais le
`MoveUnit` et l'`AddEffect`, qui sont HORS du `If`, restent), la garde structurelle « le nœud est un
`OwnerIsAlive` SANS opérande » (sur les DEUX ports, RammingSpeed et SkyStrike), et les quatre
branches de `GetDynamicInvalidTargetReason`.

## 5. `#389-r1` — l'effet 1098 est POSÉ puis RETIRÉ dans le MÊME `applyAction`

MESURE (tags d'événements du cast natif, `captureEvents`) : l'entité-effet est **créée**
(`Effect_SourceActiveAbility = 1059`, `Effect_SourceId = <caster>`, `Effect_CurrentLevel = 1`) puis
**retirée** avant la fin du même `applyAction` — après le cast, `decisionView` (canal
`includeInactive`) ne la liste plus. Le port, lui, la laisse. **La POSE est donc le bon point de
confrontation pour ce leaf** (et elle est confirmée deux fois : par l'événement, et par le +50 % de
la nova en mode léthal) ; la PERSISTANCE est un autre mécanisme, non RE, et le résidu est nommé.

⚠ **Piège de CANAL, mesuré** : `decisionView` par DÉFAUT laisse tomber les effets INERTES ; seul
`snapshot.decision_view_seed_body` (`includeInactive`) est comparable à `State.effects.by_unit`.
Le premier jet du probe croisait les deux canaux et voyait un faux écart (`PowerTrip_FullHealth`
1362 « disparu » alors qu'il était seulement désactivé).

**Deuxième résidu, GÉNÉRIQUE au pipeline d'attaque** (pas propre à 1059) : quand un coup TUE le
défenseur, le tag `Amount` natif porte le dégât RÉELLEMENT appliqué (borné par les PV restants) et
la série S'ARRÊTE ; le port continue la boucle et rapporte le montant BRUT. **L'ÉTAT est identique
des deux côtés** (`HealthComponent.reduce` borne à 0) — seule la TRACE diffère. Le probe convertit
donc la série roulée du port en série RAPPORTÉE (`_as_reported`, transformation définie, aucun degré
de liberté) : sur C1_03 léthal, port `[3105, …]` roulé → `[3105, 1895]` rapporté == natif.

## 6. Ce qui n'est PAS couvert

* **La gate `OwnerIsAlive` FERMÉE n'est pas confrontée LIVE** : il faudrait un tir RÉACTIF
  (overwatch/piège) qui tue le charger pendant son `MoveUnit`. Elle est verrouillée OFFLINE.
* **Les résidus de pool `#381-r2` / `#381-r3`** (`FlyPathfinder`, voisinage `evenq` vs
  `boardGraph.neighbours`) mordent sur DEUX faces de 1059 : l'étage MOVE et le gate de ciblage.
  Aucun bras joué ici n'est en régime ring-saturé. (`#381-r1` lui-même est FERMÉ — le nœud DSL
  porte le gate d'expansion #131 depuis `case-381-r1`.)
* **`#389-r1`** ci-dessus : la durée de vie de l'effet 1098 après le cast.
* **Un seul niveau d'ability** (celui du build, rank 17) et **un seul greffon** (`orksKillaKan`) :
  1059 a ZÉRO porteur au gameconfig, donc aucune autre voie n'existe.
* **Le `2` en dernier argument des deux `AttackWithAttackDamage`** (`selectionType`) n'est pas
  modélisé séparément — même résidu que tous les autres call-sites portés.
* **`TargetsSelector$$SelectUniqueUnits`** et le flag `0x11 NotTargetable` : hors de cet arbre
  (mono-cible des deux côtés), sans objet ici.
