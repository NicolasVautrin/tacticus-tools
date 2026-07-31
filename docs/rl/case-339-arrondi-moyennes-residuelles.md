# case-339 — trois moyennes natives, trois comportements

Résidu `#333-r1` : « deux autres sites de moyenne gardent une division entière `// 2` ».
La question posée était l'ARRONDI. La réponse est que **les deux sites n'ont pas le même artefact
natif**, et qu'un seul des deux était faux — mais bien plus gravement qu'un arrondi.

| moyenne native | corps | comportement |
|---|---|---|
| `IdunBattle.Core.Services.MinMaxDamage$$Avg` | `(int)Fix64.Round(Fix64(Min+Max)/Fix64(2), 0)` | demi-vers-le-PAIR |
| `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamageAverage` (jumeau `BaseTriggeredAbility`) | `Half(Sum(Direct(min), Direct(max)), rule=0)` | demi-vers-le-PAIR |
| `IdunBattle.DSL.AAmountFormula$$CalculateAverage` | `(CalculateMin() + CalculateMax()) / 2`, entier | **TRONCATURE** |

Elles divergent **exactement quand `min + max` vaut 3 mod 4**. Sur une somme paire, et sur
`1 mod 4` (floor pair, demi-vers-le-pair descend), les trois coïncident.

---

## 1. `Half(Sum(...))` passe-t-il par le même `Fix64$$Round(0)` ? — OUI

Lu au décompilé `rnca9r7q6c`, de bout en bout :

```
AActiveAbility$$MinMaxDamageAverage(this, abilityState) =
    DSLFormulas.Half( DSLFormulas.Sum( Direct(GetVariableForLevel(0xc = minDmg)),
                                       Direct(GetVariableForLevel(0xd = maxDmg)) ),
                      roundingRule = 0 )

DSLFormulas$$Half(a, rule)  =  new <Divide>(a, Direct(2), rule)      # ctor gshared, STRUCTURE lue

IdunBattle.Entities.Formulas.DivideAmount$$Calculate(this, entities, result) :
    a = this@+0x10.Calculate(...)
    b = this@+0x18.Calculate(...)
    return AAmountFormula$$RoundFix64Result(this,
               Fix64.op_Division(Fix64.op_Implicit(a), Fix64.op_Implicit(b)),
               rule = this@+0x20)

IdunBattle.DSL.AAmountFormula$$RoundFix64Result(this, result, rule) :
    rule == 1 -> Fix64.Ceiling(result)
    rule == 2 -> Fix64.Floor(result)
    sinon     -> Fix64.Round(result, 0)          # <<< le midpointRounding = 0 de #333
    return Fix64.op_Explicit(value)
```

`rule = 0` ⇒ **le même `Fix64.Round(., ToEven)` que `MinMaxDamage$$Avg`**. Le port le faisait déjà
(`engine/entities/formulas.py::Half` → `_round_fix64`) ; c'est le décompilé qui manquait.

## 2. Site (a) `engine/playbook/fury_of_the_ancients.py` — le `// 2` est JUSTE

**Mais son artefact n'est ni l'un ni l'autre.** L'attribution héritée de `case-333` §7
(« `MinMaxDamageAverage`, un `Half(Sum(...))` DSL ») est **fausse** : la chaîne réelle est

```
FuryOfTheAncientsPlaybook$$GetDamagePrediction
  -> <Ability>$$GetDamage                        (corps DÉDUPLIQUÉ — ghidra l'étiquette
                                                  `MassiveScythingTalonsAbility$$GetDamage`)
  -> IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamage
       = IdunBattleLogic.Entities.DSLFormulas$$RandomAmount(minDmg 0xc, maxDmg 0xd)
  -> slot 4 de l'interface `IAmountFormula` = IdunBattle.DSL.AAmountFormula$$CalculateAverage
```

`RandomAmount` ne surcharge pas `CalculateAverage` (il n'a que `Calculate` / `CalculateMin` /
`CalculateMax`), donc c'est le corps de base qui tourne :

```
AAmountFormula$$CalculateAverage(this, entities, result) :
    if (!<vtable+0x1c8>(this)) {
        min = <vtable+0x1e8>(...)        # CalculateMin
        max = <vtable+0x1f8>(...)        # CalculateMax
        return (max + min) / 2           # division ENTIÈRE C — AUCUN Fix64 ici
    }
    return <vtable+0x1d8>(...)           # Calculate
```

Le slot 4 est identifié par triangulation, pas supposé : slot 1 est `Calculate`
(`RandomAmount$$CalculateMin` l'invoque sur son enfant, `DivideAmount$$Calculate` sur ses deux
enfants) ; slots 2 et 3 sont `CalculateMin`/`CalculateMax` (`BaseEffect$$AdditionalHits` les
alimente dans `MinMaxDamage..ctor(min, max, cap)`) ; il reste le 4. Sept call-sites au total.

La branche « plage » est celle qui tourne : un `Calculate()` de `RandomAmount` est un **tirage**
(`rng.Range(min, max+1)`), il ne pourrait pas tomber sur `avg(599,797) = 698` **exactement**, pour
les DEUX cibles, comme le mesure `probe_32d_fury.py`.

⇒ **Rien à corriger sur la valeur.** Le `// 2` est remplacé par le mirror nommé
`engine.dsl.base.calculate_average` (homonyme de la fonction native) et le commentaire trompeur
(« somme paire ici : 599+797 ») par la chaîne de symboles.

## 3. Site (b) `engine/ai/action_generators.py::_spiritleech_lifesteal_util` — FAUX, sur trois axes

L'artefact est `SpiritLeechAbility$$GetHealAmountForPrediction` :

```
= DSLFormulas.PercentageOf( DSLFormulas.DamagePredictionFormula(attacker, attackerPos,
                                Entity(target), Direct(AbilityOrEffect(this)),
                                GetAttackDamage(state, isPrediction: true),
                                Direct(GetNumberConstant(0x2f)), GetDamageProfile(this),
                                prioritizeKills: FALSE),
                            DSLFormulas.ConfigVar(0x4b = hpToHealPct), rule = 1 (Ceiling) )
```

et la queue de `IdunBattle.Entities.Formulas.DamagePredictionFormula$$Calculate` :

```
result = <BattleQuery>.GetAttackPrediction(...)                # DamagePredictionResult (0xa0)
minmax = this.prioritizeKills@+0x54 ? <getter result+0x14>     # bornes du DefaultScenario
                                    : result + 0x40            # AccurateHealthDamage
avg    = IdunBattle.Core.Services.MinMaxDamage$$Avg(minmax)    # LE FOYER DE #333
if (<BattleQuery slot 0x92>(attacker, defender)) return -avg;
if (!prioritizeKills) return avg;                              # <-- la branche de SpiritLeech
```

`prioritizeKills` est le 10ᵉ argument de `DamagePredictionFormula$$.ctor` (champ `+0x54`) et
`GetHealAmountForPrediction` passe **0**. Le port lisait donc :

| axe | port avant | natif |
|---|---|---|
| champ moyenné | `rawHealthDmgMin/Max` (= `DefaultScenario` @+0x14, **non capées**) | `AccurateHealthDamage` @+0x40 (**capées aux PV**) |
| bouclier | `+ avg(shieldDmgMin, shieldDmgMax)` | **aucun terme** |
| arrondi | `/2.0`, `.5` conservé | `Avg` = demi-vers-le-pair |

Le dominant est le **premier**, pas la virgule.

---

## 4. La mesure LIVE — deux axes exercés, parité PILOTÉE

Oracle : `pairUtility` (`ComparablePlaybook$$CalculateUtilityFromPredictions`, Σ des 4 familles)
**moins** le terme dégât recalculé depuis les MÊMES events natifs (`aiPlaybookPredict`). Le résidu
vaut exactement le terme de soin — ce qui mesure au passage que l'effet natif observé (`1065`)
pèse **0**.

`aiPlaybookPredict` ne rend pas les heal events pour ce playbook (`healCount = -1`, limite du
décodeur) : le résidu d'utilité est le seul canal, et il suffit.

Parité pilotée par `--hp-target H` (cape `AccurateHealthDamage`), **avec une contrainte de plus
qu'en #333** : le `Ceiling` de `PercentageOf` peut ABSORBER un écart d'une unité sur la moyenne
(à 60 %, `ceil(2759 × .6) == ceil(2760 × .6)`). Le probe ne retient donc que les `H` dont les
variantes rendent des montants de soin DISTINCTS — sinon le bras est vert sans rien discriminer.

`probe_339_spiritleech_lifesteal.py`, `tyranNeurothrope -> genesPrimus`, `MC1_67`, anneau (3,4),
bornes non capées `[2758, 4139]`, `hpToHealPct = 60` :

| bras | PV | bornes capées | somme | floor | résidu natif | `to_even` | `trunc` | `half_up` | `kept_half` | `port_avant` |
|---|---|---|---|---|---|---|---|---|---|---|
| UP | 2765 | `[2758, 2765]` | 5523 | 2761 **impair** | 19.4282 | **0** | +0.0117 | 0 | +0.0117 | **−4.8277** |
| DOWN | 2759 | `[2758, 2759]` | 5517 | 2758 **pair** | 19.3930 | **0** | 0 | −0.0117 | −0.0117 | **−4.8629** |

⇒ **`to_even` est la SEULE variante nulle sur les DEUX bras.** Et l'écart du port d'avant #339 vaut
**~4.83 points d'utilité**, soit ~410× un écart d'arrondi : le bug était le champ lu.

Le code LIVRÉ est confronté, pas seulement la formule : le probe appelle
`ComparableAbilityGenerator._spiritleech_lifesteal_util` sur le contexte IA RÉEL
(`engine.ai.context.build`), nourri de la prédiction native — **delta 0.0000 sur les deux bras**.

### Généralisation

| montage | verdict |
|---|---|
| `tyranNeurothrope -> genesPrimus`, `MC1_67`, anneau (3,4) | OK |
| `tyranNeurothrope -> necroWarden`, `MC1_67`, anneau (3,4) | OK |
| `tyranNeurothrope -> genesPrimus`, **`C1_03`**, anneau (3,6) | OK |

> Les trois rendent les MÊMES bornes `[2758, 4139]` : `--hp-target` met `Armor = 0`, donc la
> prédiction ne dépend plus que du caster. La généralisation porte sur la géométrie et la victime,
> **pas** sur une seconde plage de dégâts.

---

## 5. Le correctif

| fichier | changement |
|---|---|
| `engine/dsl/base.py` | **`calculate_average(min, max)`** — mirror de `AAmountFormula$$CalculateAverage`, TRONCATURE (division C, vers zéro), avec la lecture qui interdit de le confondre avec les deux autres moyennes |
| `engine/playbook/fury_of_the_ancients.py` | le `// 2` inline devient un appel à `calculate_average` ; le commentaire « somme paire ici » est remplacé par la chaîne de symboles |
| `engine/ai/action_generators.py` | `_spiritleech_lifesteal_util` : `min_max_avg(healthDmgMin, healthDmgMax)` (plus de bornes brutes, plus de bouclier) ; `math.ceil(... / 100.0)` devient `_round_fix64(Fraction(dmg*pct, 100), 1)` = le mode `Ceiling` de `RoundFix64Result` |

## 6. Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `tests/engine/test_339_moyennes_residuelles_offline.py` (5 tests) | la table de divergence des TROIS moyennes ; exhaustif jusqu'à somme 400 (`ToEven == trunc + 1` ssi `3 mod 4`) ; les 3 modes de `RoundFix64Result` ; que le site Fury est câblé sur `calculate_average` **et pas** sur `min_max_avg` ; la chaîne du lifesteal sur le régime mesuré |
| `tests/engine/test_339_spiritleech_lifesteal_live.py` (8 tests) | que les bornes capées DIFFÈRENT des brutes (sinon l'axe champ-lu n'est pas exercé) ; les deux parités ; que le `Ceiling` n'écrase pas l'écart d'une unité ; le code LIVRÉ == natif sur les deux bras ; que le résidu vaut le terme de soin SEUL ; `to_even` seul nul partout ; la mutation `port_avant` rouge d'un ordre de grandeur au-dessus d'un arrondi |

**Mutations jouées** : `calculate_average` → ToEven = **3 rouges** offline ; `Half` → troncature =
**1 rouge** offline ; le port d'avant #339 remis dans `action_generators` = **2 rouges** live.

---

## 7. Ce qui n'est PAS couvert

- **L'axe BOUCLIER n'est pas exercé live.** `AccurateShieldDamage` vaut `[0,0]` sur tous les
  montages (même limite que `case-333` §7). Que le natif ne l'additionne pas est lu au décompilé
  (`DamagePredictionFormula$$Calculate` ne lit QUE `+0x40`), pas mesuré.
- **La branche `prioritizeKills = true`** (bornes du `DefaultScenario` @+0x14, puis `×2` si
  `MightBeKill` et `×3` si `WillBeKill`) n'est empruntée par aucun call-site porté : non transcrite.
- **La branche de NÉGATION** (`<BattleQuery slot 0x92>(attacker, defender)` → `-avg`) est lue mais
  le slot n'est pas identifié ; SpiritLeech vise un ennemi et ne l'emprunte pas.
- **Le régime `3 mod 4` du site Fury n'est pas confronté live.** Le verdict « troncature » repose
  sur le décompilé (aucun Fix64 dans la branche) ; le live confirme la BRANCHE (moyenne, pas
  tirage) via `probe_32d_fury.py`, mais son couple `599 + 797` est PAIR. Confronter la troncature
  demanderait un oracle de la feuille MOVE de `TriggeredAbilitiesUtility(2)`, qui n'existe qu'en
  trace L3 — hors d'atteinte d'un agent (hooks session-globaux).
- **Aucun renversement de DÉCISION n'a été construit.** L'écart mesuré (4.83 pts sur ce montage)
  est largement suffisant pour renverser un argmax entre deux candidats proches, mais aucun tel
  couple n'a été monté : ce qui est mesuré est l'utilité PAR PAIRE, bit-exacte contre l'oracle.

## 8. Résidus NOMMÉS, hors périmètre

Cinq autres sites moyennent des bornes à la main. Aucun n'a été ouvert ici (périmètre = les deux
sites de #333-r1) ; les deux premiers sont des **bugs avérés** au vu de la RE ci-dessus.

| site | ce qu'il cite | verdict au vu de §1 |
|---|---|---|
| `engine/entities/abilities/active_ability.py:110` | « Half (Fix64) — somme impaire : x.5 tronqué » | **FAUX** : c'est `AActiveAbility$$MinMaxDamageAverage`, donc demi-vers-le-pair. Le commentaire admet lui-même l'hypothèse. Rayon LARGE (base générique de la prédiction d'ability) ⇒ sa propre confrontation |
| `engine/runner/abilities/votann.py:387` | « Half(Sum(minDmg, maxDmg)) » | **FAUX** pour la même raison. Face COMBAT ⇒ sa propre confrontation |
| `engine/runner/abilities/darkangels.py:910` | « MinMaxDamage.Avg » | à qualifier : le nom cité arrondit, le code tronque |
| `engine/runner/operations/damage_hits.py:52` | « `(int)((Max+Min)/2)` » | à qualifier : quel artefact ? |
| `engine/entities/unit_context.py:93` | aucun symbole cité | à qualifier |
