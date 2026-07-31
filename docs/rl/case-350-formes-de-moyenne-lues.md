# case-350 — l'inventaire des formes de moyenne de prédiction est CLOS

Résidu `#344-r1`. #344 avait lu **36** abilities (18 par forme) et laissé le reste sur le défaut
(troncature). #350 boucle l'inventaire et corrige **18** abilities de plus.

---

## 1. Pourquoi l'inventaire est CLOS, et pas « 18 de plus »

La moyenne `minDmg`/`maxDmg` d'une prédiction ne peut naître que de trois endroits, tous énumérables
par xrefs :

| source | ce qu'elle produit | xrefs côté PLAYBOOK |
|---|---|---|
| `AActiveAbility$$MinMaxDamageAverage` / `$$MinMaxDamage(isPrediction ≠ 0)` | `Half(Sum(min,max), 0)` → `DivideAmount$$Calculate` → `RoundFix64Result(.,0)` = **demi-vers-le-PAIR** | via des corps `<X>Ability$$Get*` (énumérés) |
| `AActiveAbility$$MinMaxDamage(isPrediction = 0)` / `BaseTriggeredAbility$$MinMaxDamage` | `RandomAmount(min,max)`, slot 4 = `AAmountFormula$$CalculateAverage` = **TRONCATURE** | idem |
| `DSLFormulas$$Half` / `$$Divide` appelés **INLINE** par un playbook | même `DivideAmount$$Calculate` | **2 playbooks seulement** : `SorcerousFacadePlaybook$$MakeDamagePredictions`, `IncendiaryShellsAbility$$GetDamageRange` |

Les xrefs de `DSLFormulas$$Half`, `$$Divide` et des deux surcharges de `$$RandomAmount` ont été
balayées : **aucun autre playbook** n'appelle ces primitives. Tout ce qui n'est dans aucun des deux
registres a donc une base qui **n'est pas une moyenne** — c'est un résultat, pas un trou.

⚠ Le nom du corps ne dit **jamais** la forme (les corps sont dédupliqués). Deux lectures obligatoires :
les **xrefs entrantes** du corps, puis — pour `StaffOfStarsAbility$$GetDamage`, qui **forwarde**
`isPrediction` — le **littéral du call-site** (`mov r8b, 1` lu à l'octet sur les 11 sites).

## 2. Les quatre voies vers la forme (a), et ce qu'elles ajoutent

Registre `_PREDICTION_MINMAX_AVERAGE` (`entities/abilities/active_ability.py`), désormais l'union de
quatre sous-ensembles tracés :

| voie | corps natif | nouvelles |
|---|---|---|
| a1 | `StranglethornCannonAbility$$GetDamageAmountMain` → `MinMaxDamageAverage` | 0 (les 18 de #344) |
| a2 | `StaffOfStarsAbility$$GetDamage(state, isPrediction)`, **11 call-sites tous à `isPrediction = 1`** | **10** — 1207 AncestralFortune, 1078 Fragstorm, 1147 HadesAutocannons, 1132 KillMaimBurn, 1204 LeadingTheCharge, 1177 LightOfSanguinius, 1111 LivingBatteringRam, 1074 ScytheOfDust, 1069 SeekerMissileFrequencyLock, 1073 StaffOfStars |
| a3 | corps PROPRE de l'ability | **6** — 1157 BladeOfMagnus, 1148 DaemonicOrdnance, 1093 MortarionsPlagueWind (`GetDamage1`), 1137 MurderousSwing (`GetCorrectDamage`, les DEUX branches du `If`), 1095 ReapingScythe, 1104 SpiritLeech |
| a4 | moyenne INLINE dans le playbook | **2** — 1044 IncendiaryShells (`Divide(Sum(Get(mn),Get(mx)), Get(2), 0)`), 1100 SorcerousFacade (`Half(Sum(Get,Get), 0)`) |

Forme (b) : **+1**, `1230 SavageEchoes` — `SavageEchoesAbility$$GetDamage` code `isPrediction` **en dur
à FAUX**. Comportement inchangé (le défaut est déjà la troncature), mais désormais **lu**.

## 3. Ce qui n'est NI (a) NI (b) — nommé, jamais forcé

Table `_PREDICTION_DAMAGE_NOT_MINMAX_AVERAGE` (7 entrées). Leur base n'est pas une moyenne du tout :
l'erreur y est **plus profonde que l'arrondi**.

| id | natif | corrigé ? |
|---|---|---|
| 1080 HellfireShells | `Direct(minDmg)` seul | oui (`_hellfire_shells_inputs`) |
| 1089 GreatFrostAxe | `Get(minDmg)` seul | oui |
| 1051 Stikkbomb | `Get(minDmg)` seul | oui |
| 1191 MartialInspiration | `round(minDmg × buff)`, hits = 1 | oui |
| **1098 PlasmaGrenade** | `Get(minDmg)` seul, hits const `0x2f` / secondaires `0x32` | **non → `#350-r2`** |
| **1048 FragstormGrenadeLauncher** | `maxDmg` (var `0xd`) seul | **non → `#350-r2`** |
| **1059 RammingSpeed** | `ExplodesAbility$$GetDamage` = `PercentageOf(StatAmount(Health), …)` — aucun min/max | **non → `#350-r2`** |

Hors table (pas de `minDmg`/`maxDmg` en config, donc le port n'émet rien) : `1010 StormOfFlensingBlades`
(prédiction d'attaque NORMALE, slot `0x22`), `1025 SkyStrike` (`Sum(NormalAttackDamage, Direct(var8))`).

**`1160 HeavyRailRifle` — NON inscrit, volontairement** : `HeavyRailRiflePlaybook$$EvaluateNonComparable`
appelle `MassiveScythingTalonsAbility$$GetDamage` → `BaseTriggeredAbility$$MinMaxDamage` (`RandomAmount`,
donc (b)), **mais** ce corps lit sa config à `+0x20`, l'offset d'une `BaseTriggeredAbility`, pas d'une
`AActiveAbility` (`+0x60`). L'objet évalué n'est donc pas l'ability 1160 elle-même. L'inscrire au registre
`ActiveAbilityType` serait une extrapolation (`#350-r3`).

## 4. Mesure LIVE — quatre abilities, deux voies, deux boards

`probe_344_ability_damage_average.py` tel quel (deux leviers : `--unit-stat ActiveAbilityLevel` pour la
parité, `--armor-target 0` pour que l'écart d'une unité survive à l'armure). Bornes
`(healthDmgMin, healthDmgMax, hits)` de l'event de la cible principale, oracle `aiPlaybookPredict` :

| ability (voie) | porteur / board | bras `3 mod 4` natif | ce que rendait la TRONCATURE |
|---|---|---|---|
| 1177 LightOfSanguinius (a2) | `bloodDante` / MC1_67, lvl 7 | `(120, 180, 5)` | `(115, 175, 5)` ✗ |
| 1204 LeadingTheCharge (a2) | `astraDreir` / MC1_67, lvl 2 | `(81, 123, 3)` | `(78, 120, 3)` ✗ |
| 1104 SpiritLeech (a3) | `tyranNeurothrope` / MC1_67, lvl 4 | `(45, 67, 1)` | `(44, 65, 1)` ✗ |
| 1069 SeekerMissileFrequencyLock (a2) | `tauMarksman` / **C1_03**, lvl 8 | `(213, 319, 1)` | `(211, 318, 1)` ✗ |

Sur les quatre, `to_even` est la **seule** variante nulle sur les deux bras, et le code LIVRÉ égale le
natif. Non-régression de la famille (b) : `1150 PlasmaCannon` (montage #344) tronque toujours.

> **Bras MUET, ré-observé** : `SorcerousFacade` (1100) rend `(3935, 5903, 1)` pour les **quatre**
> variantes **et** pour les deux niveaux. Cause lue : le port délègue 1100 entièrement à l'attaque
> normale (`_PREDICT_VIA_NORMAL_ATTACK`), donc `get_damage` n'y est jamais appelé — et l'oracle rend
> **2 events** là où le port en rend 1. Le probe **échoue** au lieu de verdir. L'inscription (a4) reste
> juste : elle deviendra active dès que le 2ᵉ batch sera porté (`#350-r1`).

## 5. Ce qui n'est PAS couvert

- **Non confrontables par `aiPlaybookPredict`** : les playbooks **NonComparable** rendent 0 event à cet
  oracle (mesuré sur `1132 KillMaimBurn`). Concerne 1132, 1111, et les deux déjà lues par #344 (1173, 1202).
- **Porteur MoW** : `1147 HadesAutocannons` / `1148 DaemonicOrdnance` (`blackForgefiend`) — le gabarit
  #344 passe le caster par `--p-units`, qui **refuse** un MoW. Montage à étendre, pas une impossibilité.
- **Porteur hors pool** : 1044, 1073, 1074, 1078, 1093, 1095, 1157, 1207 (injection catalogue non tentée).
- **1137 MurderousSwing** : porteur au pool (`worldExecutions`) mais son playbook émet `count²` events
  (double boucle) — non confronté, la lecture (`GetCorrectDamage` → `MinMaxDamageAverage` sur les deux
  branches) tient au décompilé.

## 6. Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `tests/engine/test_350_prediction_average_forms_offline.py` (5) | la partition des 4 sous-chaînes (provenance de chaque id) ; la disjonction des 3 tables ; le cliquet « les 3 abilities confrontées MONTENT d'une unité au-dessus de la troncature » ; l'inertie assumée de 1100 ; la véracité de la colonne « corrigé » de la table non-moyenne |
| `tests/engine/test_350_prediction_average_forms_live.py` (5) | les deux parités PILOTÉES + niveau effectif relu ; chaque bras DISCRIMINE ; le code LIVRÉ == natif sur 3 montages × 2 bras ; la troncature REFUSÉE par le natif sur les trois |

**Mutations jouées, rouges** : retrait de `1104` du registre → live `(44,65,1)` vs natif `(45,67,1)` ;
duplication d'un id entre deux sous-chaînes → la partition tombe. Les 7 gardes live et 8 gardes offline
de #344 sont rejouées vertes.
