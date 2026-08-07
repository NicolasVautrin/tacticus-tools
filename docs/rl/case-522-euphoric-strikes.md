# #522 — `1198 EuphoricStrikes` : la marque qui donne son crit à l'attaque SUIVANTE

`emperExultant` « Laviscus » (Emperor's Children / Chaos, **lineup**, seul porteur ; **hors seed
BC** → `catalog_inject`, cf. `case-92` §6). Avant cette tranche l'ability était un **no-op
silencieux** : absente d'`ABILITY_CLASSES`, le cast partait, `ported` valait `False`, et **rien**
ne se produisait — ni dégât, ni effet, ni erreur.

i2 : « Deals {nrOfHits}x {minDmg}-{maxDmg} Power Damage to an adjacent enemy. The next attack
against that enemy this turn has +{extraCritChance}% Crit Chance. Using Euphoric Strikes does not
end Laviscus' turn. »

## 1. Ce que le natif fait — `Execute`, PAS `ExecuteAtomic`

`IdunBattleLogic.Entities.Abilities.Active.Loki.EuphoricStrikesAbility$$ExecuteBehaviour` :

```
Execute(
    AttackWithAttackDamage( Caster@DSLSelectors+0x48, Target@+0x60,
                            AActiveAbility$$MinMaxDamage(this, abilityState),
                            AbilityConfiguration$$GetDamageProfile(config@+0x60),
                            AActiveAbility$$GetHits(this),
                            AbilityOrEffect(this+0x10),
                            options = Nullable<AttackDamageBehaviourOptions> VIDE )
  op_BitwiseAnd
    AddEffect( 0x595 = 1429 EuphoricStrikes_ExtraCrit,
               AActiveAbility$$get_AbilityStateReference(this),
               source  = Caster@+0x48,
               targets = Target@+0x60,
               turns   = <DSLFormulas+0x20> = Direct(1) ) )
```

Quatre lectures que le décompilé impose :

* **`Execute`, pas `ExecuteAtomic`** — les deux symboles existent et sont distincts
  (`AActiveAbility$$Execute` / `$$ExecuteAtomic`). Donc **aucun `AtomicGroup`**.
* **le dégât n'a aucun override** : bornes config brutes, et le 8ᵉ argument
  `Nullable<AttackDamageBehaviourOptions>` est passé **VIDE** — ni `alwaysCrit`, ni
  `alwaysOverkilled`, ni variance d'arme.
* **la source de la marque est `Caster@+0x48`**, pas `Owner@+0x30` (contraste `EmpyricAmbush`).
  C'est le défaut de la feuille `AddEffect` (`source_ref=None` ⇒ `entities.caster`).
* **`turns = Direct(1)`** — un nombre de TOURS déjà résolu → `duration_turns=1`, surtout pas
  `duration_rounds` (qui passerait par `BattleQuery$$ConvertRoundsToTurns`).

**Hors de cet arbre** : « does not end Laviscus' turn » ne vient pas d'ici (aucun nœud de turn-flow
dans `ExecuteBehaviour`). Même situation qu'`ArmoriumCherub` (1014) — concern turn-order, axe
séparé.

## 2. Le masque — le MÊME preset que `ThunderousAssault`, mais PAS la même surcharge

`...EuphoricStrikesAbility$$.ctor` est de la 3ᵉ forme (**preset statique copié**) : il recopie les
0x40 octets de `<TargetingOptions statics>+0x40` et les passe **tels quels** à
`AActiveAbility..ctor(this, &preset, 0)`.

Contenu du preset, relu dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :

| champ | valeur |
|---|---|
| `+0x00 isSelfCasting` | 0 |
| `+0x08 range` | `TargetingRange` statics **+0x30** = `onlyAdjacent = RangedBool.True`, `overrideRange = Nullable(1)` ⇒ **`RANGE_ADJACENT`** |
| `+0x20 forceMeleeTarget` | 1 = `RangedBool.False` (aucun clamp à poser : la portée EST l'adjacence) |
| `+0x28 rules` | **0x4000** = `TargetIsEnemy` — un seul bit, aucun résidu |
| `+0x30/+0x38 délégués` | 0, 0 ⇒ aucun `GetDynamicInvalid*Reason` |

⚠ **Le voisin ment, et il est à portée de copier-coller.**
`...ThunderousAssaultAbility$$.ctor` lit **le même preset `+0x40`**, mais le passe ensuite à la
surcharge **PRESET + FLAGS** (`TargetingOptions..ctor(&opts, &preset, 0x10000000)`), qui fait
`Rules <- flags | preset.Rules` : son masque effectif vaut `0x10004000`. EuphoricStrikes n'a
**aucun** flag à OR-er — le bit 28 `CasterCanMove` ne lui appartient pas. Un test dédié garde cette
distinction (`test_522_euphoric_strikes_live.py::test_registre_offline`).

`ABILITY_ATTACK_TYPE` = 3ᵉ argument = **0 = `DirectTargetAttack`**, lu sur l'appel.

## 3. L'effet 1429 — UN SEUL canal, et le porteur est le DÉFENSEUR

`...EuphoricStrikes_ExtraCritEffect$$.ctor` : `mov edx, 0x4ae` (= **1198**, un
`ActiveAbilityType`) + `hasAutomaticActivation: 1`, relu **octet à octet**. La config lue est donc
`abilities.EuphoricStrikes`, indexée par le niveau de l'ability **ACTIVE** de la source — pas par
un niveau de passif. L'`EffectType`, lui, vaut 1429 : les deux ne se confondent pas.

`$$CreateCritChanceBonus` :

```
EffectBonus.ForAddition(
    get_OwnerIsTarget
      & AmountIsGreaterThanZero( StatAmount(Caster@+0x48, 0x9 = CritChance, 0 = Current, null, 0) ),
    ConfigVar( 0x41 = extraCritChance, GetAbilityState(effect), config@+0x60 ) )
```

`DSLFormulas$$StatAmount(this, unit, statType, statPart, modificationEntity, selectionType)` —
signature relue : le `0x9` est le `statType`, le `0` qui suit le `statPart`.

⚠ **UN SEUL canal** : le build ne porte que `$$CreateCritChanceBonus`,
`$$CreateRemoveEffectTrigger` et `$$.ctor` pour cette classe — **aucun** `CreateCritDamageBonus`
(contraste `EmpyricAmbush` 1578 et `InescapableAccuracy` 1115/1116). En ajouter un serait une
invention.

⚠ **Les deux nœuds n'ont pas le même sujet.** `get_OwnerIsTarget` porte sur le **porteur** (il doit
être le défenseur) ; `AmountIsGreaterThanZero(StatAmount(Caster, …))` porte sur l'**attaquant** —
une unité à crit chance de base nulle ne gagne rien. Même forme de gate que `PathOfCommand`
(`crit_aura.py`), où l'`eldarFarseer` à cc = 0 ne recevait rien.

`extraCritChance` n'est **pas** dans `variablesAffectedByRarityBonus` (`["minDmg", "maxDmg"]`) ⇒
aucun scaling de rareté ; `ability_var` applique la règle config-driven.

## 4. Le retrait — ce qui fait du +crit une CHARGE À USAGE UNIQUE

`$$CreateRemoveEffectTrigger` :

```
  On( 9 = Attack,    ownerNeedsToBeAlive: true ) & get_OwnerIsTarget
| On( 0 = UnitDeath, ownerNeedsToBeAlive: true ) & AreEqual( Target@+0x60, EffectSource(Effect@+0x38) )
```

`DSLTriggers$$On(this, triggerType, ownerNeedsToBeAlive)` — le second littéral est le **drapeau**,
pas un second event ; à VRAI il fait choisir le conjoint `<DSLTriggers+0x20>` =
`OwnerIsAliveAbilityTrigger` (nommé par `case-224` item 5), porté ici sur les deux disjoints.

Sans cette entrée (`EFFECT_TRIGGERS[1429]`), le +crit bufferait **toutes** les attaques du tour au
lieu de la **prochaine** — régression PERMISSIVE et silencieuse, forme exacte de 1550
(`Chronometron_ExtraDamage`) et 1000 (`ShockAssault_Buff`). Le 2ᵉ disjoint fait sauter la marque si
Laviscus meurt avant qu'elle serve.

## 5. Ce qui est mesuré — `probe_522_euphoric_strikes.py`, board `MC1_67`, positions FORCÉES

Deux régimes, cinq étages. Chiffres du 2026-08-07, build `rnca9r7q6c` :

| étage | `nominal` (`--crit 70,700`, kit COMPLET) | `gate0` (`--crit 0,700`, trait isolé) |
|---|---|---|
| E0 `ported` | `True`, `emitted = [AttackWithAttackDamage, AddEffect]` | idem |
| E1 dégât du cast | natif 7403 / port 7403, séquence `[7403]` des deux côtés, **3 = 3** tirages | 6353 / 6353, `[6353]`, **2 = 2** tirages |
| E2 pose de 1429 | présent des deux côtés | idem |
| E3a crit chance effective | marquée **100** / sans **70** / autre cible **70** | **0 / 0 / 0** (gate FERMÉ) |
| E3 attaque de l'allié | natif **21747** = port AVEC ; port SANS **17993** ; 4/4 coups critent | natif 17799 = AVEC = SANS ; 0/4 crit |
| E4 retrait | 1429 disparu des deux côtés | idem |

Le couple `nominal`/`gate0` est ce qui rend le gate `AmountIsGreaterThanZero(StatAmount(Caster,
CritChance))` **mesurable** : un port qui l'oublierait rendrait `+extraCritChance` dans les deux, le
natif rend 30 puis 0. Et la contre-épreuve hors ligne (même capture, marque consommée) est ce qui
empêche l'accord d'E3 d'être un accord en **régime dégénéré** : 21747 ≠ 17993.

Garde : `tests/engine/runner/test_522_euphoric_strikes_live.py` (8 bras, 4 offline + 4 live).
Contre-épreuve du garde : désarmer `_owner_is_target` fait rougir 2 bras sur 8.

## 6. Deux résidus, tous deux MESURÉS et ATTRIBUÉS — hors #522

### `#522-r1` — `ThrillSeekers` applique son +15 au coup DÉCLENCHANT, le natif non — **RÉSOLU**

> **Fermé le 2026-08-07.** La loi a été établie au décompilé (`RollCritical` précède
> `On(PreAttackHit)` dans `AttackDamageOperation$$ExecuteHit`, et `GetStat(9)` est relu par coup),
> le correctif porté par `crit_chance_after` / `crit_enabled_after`. Le même correctif ferme
> **`#524-r2`**. Détail : `docs/rl/case-522-r1-thrill-seekers-timing.md`. Le constat d'origine est
> conservé ci-dessous parce que c'est lui qui a servi de point d'entrée.

Avec le kit COMPLET à `--crit 0,700`, le port consomme **un tirage `genrand_int32` de plus** que le
natif sur le cast (**3 contre 2**), à **dégât et séquence identiques** (6353, `crits=[False]`).
Attribution, trois mesures :

```
kit complet,   --crit 0,700 : natif 2 / port 3
trait ThrillSeekers RETIRÉ  : natif 2 / port 2      <- l'écart DISPARAÎT
témoin 1043 ThunderousAssault (`templSwordBrother`, même board, même `--crit 0,700`,
même famille ATTACK, mêlée adjacente — porteur SANS le trait) : natif 5 / port 5
```

Cause : `ThrillSeekers` (trait `UnitTrait` 1056, les cinq kits Emperor's Children) pose « Thrilled »
(`EffectType` 0x59a = 1434), un `StaticStatModifierEffect` de +15 CRIT_CHANCE, sur
`On(PreAttackHit = 6) & IsFirstHitInSeries & OwnerIsCaster & NOT IsWounded(target)`. Le natif le
pose bien (`decisionView` du caster porte 1434 après le cast) mais **n'en tient pas compte pour le
crit du coup déclenchant** : sa crit chance reste 0, donc `DamageCalculations$$CouldCrit(0, 700)`
est faux et `RollCritical` n'est jamais appelé. Le port, lui, applique le +15 au coup courant
(`could_crit(15, 700)` vrai) → un crit-roll de plus.
`runner/operations/triggers/loki/thrill_seekers.py` écrit explicitement l'inverse (« le buff
s'applique bien a l'attaque declenchante ») — c'est cette lecture que la mesure contredit.

Observable : **rien** sur le dégât ici (le crit-roll à cc = 15 échoue), mais le RNG est
désynchronisé pour la suite, et dans un régime où ce tirage réussirait le port critterait là où le
natif ne le peut pas. Corriger le timing touche les **5** porteurs du trait et exige la RE du point
où le natif lit `GetStat(9)` dans `ExecuteHit`.

### `#522-r2` — le passif `RefusalToBeOutdone` de Laviscus n'est pas porté

Même mesure, autre lecture : après le cast, le caster porte côté natif `[1226, 1430, 1434, 1511]`
et côté port `[1226, 1434]`. `RefusalToBeOutdone_ExtraDamage` (1430) et
`RefusalToBeOutdone_ExtraCritDamage` (1511) viennent du passif `RefusalToBeOutdone`
(`TriggeredAbilityType` 1441), **non porté**. Aucun effet observable sur les dégâts de ce montage
(7403 et 6353 des deux côtés), mais l'écart d'état est réel.

## 7. Ce qui n'est PAS couvert

* le 2ᵉ disjoint du retrait (`On(UnitDeath) & Target == EffectSource`, « Laviscus meurt ») est
  **porté et gardé offline** (`test_retrait_registre_offline` vérifie les deux `event_ids`,
  `matches` branche sur `ev.event_id`), mais **non confronté live** : aucun montage de cette tranche
  ne tue le caster avant que la marque serve ;
* le turn-flow « does not end Laviscus' turn » (hors `ExecuteBehaviour`) ;
* les deux résidus du §6.
