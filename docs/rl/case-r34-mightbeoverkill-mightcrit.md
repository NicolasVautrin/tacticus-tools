# R34 — la face DÉCISION de l'overkill : `MightBeOverkill` passe `MightCrit`, le port passait 0

**Build** `gqfc5mff6c` · **fermé le 2026-07-28** · gardes :
`scripts/python/tests/engine/runner/test_overkill_decision_live.py` (6 tests, vus **ROUGES par 3
mutations distinctes**) · montage : `scripts/python/probe_r34_overkill_decision.py` · fixtures :
`tests/engine/runner/conftest.py`.

Suite directe de `case-r33-overkill-isoverkill-args.md`, qui a fermé la face COMBAT et a laissé
celle-ci en non-couvert **délibéré** — à raison : la moitié du fix (lire sans poser, ou poser sans
lire) aurait créé un canal mort.

## 1. Le verdict, au décompilé

`IdunBattle.Core.Services.DamagePredictionResult$$MightBeOverkill` et son jumeau
`…$$WillBeOverkill` appellent **tous deux** la surcharge PRIVÉE 8-args de
`IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (celle qui porte la formule), et ils ne
diffèrent **que par deux arguments** :

| argument | `MightBeOverkill` | `WillBeOverkill` |
|---|---|---|
| `targetInitialHealth` | `result@+0x00` | `result@+0x00` |
| `healthDamage` | **`result@+0x28`** (raw MAX) | **`list[0]@0x50`** si scénario de block, sinon `result@+0x24` (raw MIN) |
| **`isCritical`** | **`result@+0xB1` = `MightCrit`** | **littéral `0`** |
| `isForceOverkill` | `result@+0xB2` | `result@+0xB2` |
| `isPreventOverkill` | `result@+0xB3` | `result@+0xB3` |
| `allowOverkill` | `HasValue(result@+0xB4)` | idem |
| `overkillDmgPctOfHealth` | `Value(result@+0xB4)` | idem |
| `targetMinimumHealth` | `null` | `null` |

L'ordre des arguments a été **re-dérivé au désassemblage du site d'appel** (le rendu Ghidra du
`call` ne suffit pas : le décompilateur ne connaît pas le prototype). Séquence lue en fin de
`MightBeOverkill` :

```
mov ecx, esi                  ; arg1 = result@+0x00
mov edx, ebp                  ; arg2 = result@+0x28
movzx r8d, r14b               ; arg3 = result@+0xB1   <-- MightCrit
movzx r9d, r15b               ; arg4 = result@+0xB2
mov [rsp+0x20], r12b          ; arg5 = result@+0xB3
mov [rsp+0x28], bl            ; arg6 = HasValue(Nullable@+0xB4)
mov [rsp+0x30], eax           ; arg7 = GetValueOrDefault(Nullable@+0xB4)
mov [rsp+0x38], rax (=0)      ; arg8 = targetMinimumHealth = null
mov [rsp+0x40], rax (=0)      ; arg9 = MethodInfo*
```

`WillBeOverkill` pose **`0` en dur** à la place de `r8d` — l'asymétrie est native : la borne
GARANTIE ne parie pas sur un crit, la borne OPTIMISTE si.

Et le corps privé **RENVOIE `isCritical`** dans le cas « létal mais SOUS le seuil » :

```
if (targetInitialHealth <= healthDamage) return pct < overkillDmgPctOfHealth ? isCritical : true;
```

⇒ **tout coup critique qui tue sans doubler les PV EST un overkill.** Le port passait `0` des DEUX
côtés : la borne optimiste (`PossibleOverkill`, feuille `OverkillUnit` = utilité 37) sous-estimait
**tout** kill critique dans `[PV, 2 × PV)`.

### Confirmation croisée du nommage des quatre flags

`…$$PredictAttackRaw` écrit les quatre octets `@+0xB0..0xB3`, et le décompilé les nomme sans
ambiguïté :

```
@+0xB0 LimitedByMinHp = out-bool de CalculateDamagePredictionScenario (scénario SANS blocage)
                      = FillUpStatComponent.MaxReduceByMinimum(cible, dmgMax, out limited)
@+0xB1 MightCrit      = IDamageCalculations slot 7 = DamageCalculations$$CouldCrit(attaquant)
@+0xB2 ForceOverkill  = data(+0x68) || (HasTrait(attaquant,1056 ThrillSeekers)
                                        && HasEffect(attaquant,1434 Thrilled)
                                        && (data(+0x69) || data(+0xB8)))
@+0xB3                = HasFlag(cible, 0x13) = PreventOverkill
@+0xB4 Nullable<int>  = config DI (this+0x10) : +0x30 HasValue, +0x34 seuil overkill %
```

Deux conséquences directes :

* `@+0xB4` **confirme** que `allowOverkill`/`overkillDmgPctOfHealth` du port
  (`allow_overkill=1`, `_overkill_threshold_pct()`) sont bien la config DI — la MÊME que lit la
  surcharge d'instance à `this+0x10 @+0x30/@+0x34`.
* **`DamagePredictionResult$$Add` ne fusionne AUCUN de ces quatre flags** — il ne somme que les
  champs de dégât et le dword `@+0xBC` (`AppliedHits`). Les flags gardent la valeur du **premier**
  `PredictAttackRaw`. Le port faisait `self.might_crit = self.might_crit or other.might_crit` : un
  fork sans effet numérique (tous les coups d'une attaque ont le même attaquant, donc le même
  `CouldCrit`) mais qui aurait divergé dès qu'un `Add` agrège deux prédictions d'attaquants
  différents. Retiré.

### Le crit n'entre dans AUCUNE borne de dégât

Lecture intégrale de `PredictAttackRaw` (3032 lignes) : ni `ApplyCritDamage` (slot 5) ni
`RollCritical` (slot 6) n'y sont appelés, `DamagePrediction$$CalculateCriticalDamage` et
`…$$RollCritical` n'ont **aucun appelant direct** (2 xrefs DATA chacune = les entrées de table), et
min/max sont traités symétriquement. **La borne MAX prédite est le dégât maximal NON critique.**
`MightCrit` est publié *uniquement* pour `MightBeOverkill`.

C'est aussi ce que la mesure montre : entre les régimes `--crit 0,0` et `--crit 100,1`, les bornes
RAW natives sont **identiques** (`[7218, 10836]` des deux côtés) et seule l'utilité bouge.

## 2. Le canal, de bout en bout — producteurs et consommateurs

**Producteur (le flag lui-même)** — foyer UNIQUE, à l'endroit où le natif l'évalue :
`services/damage_prediction.attacker_could_crit(attacker_ctx)`, appelé **dans**
`predict_attack_raw` (même pli que `is_attack_max_out_damage`, #202). Mirror de
`DamageCalculations$$CouldCrit` = `GetStat(9 CritChance) >= 1 ET GetStat(10 CritDamage) > 0`, via le
`could_crit` déjà porté dans `services/damage_combat.py` (**pas de second mirror**).
⚠ `CouldCrit` lit `GetStat` **NU** : pas la couche calc-time `GetCritChanceBonusFromEffects` /
`GetCritDamageBonusFromEffects` que le COMBAT ajoute (`AttackDamageOperation._crit_params`).
`ctx.crit_chance`/`ctx.crit_damage` SONT `GetStat(Current)` — le bon niveau de lecture.
Les appelants passent `attacker_ctx=` : `playbook/prediction/normal_attack.py` (4 sites : normale,
drone MV71, les 2 follow-ups de boss), `playbook/prediction/abilities.py`, `playbook/psyker.py`,
`playbook/fury_of_the_ancients.py`.

**Producteurs de la CLÉ `mightCrit`** du dict `pred` — **2**, et ce sont les deux seuls qui
alimentent la face DÉCISION :

1. `playbook/probable_damage_event.py::composite_fields` ← `dp.might_crit` (chaîne offline) ;
2. `engine_agreement_stages._fields_from_native_event` ← `mightCrit` de l'event NATIF
   (`aiPlaybookPredict`, décodeur `playbook-predict.ts` : `mightCrit: ev.add(0xb9)` =
   `prediction@+0x08` + `0xb1`). Sans elle, l'étage UTILITÉ du harnais d'agreement comparait une
   formule offline amputée à un scorer natif complet et classait l'écart « logic » alors que le
   feed était bon.

**Consommateurs de la clé** — **1** (`utilities/damage.py::might_be_overkill`), lui-même consommé
par `OverkillUnitUtility.evaluate` (feuille 37 du composite Damage 34) et, par ce composite, par
`playbook/base.py::calculate_action_utility`, `probable_damage_event.calculate_utility_from_damage_event`,
`engine_agreement_stages._formula_pair_utility`, `runner/operations/damage_utility.py`.
`will_be_overkill` **ne doit pas** le lire (asymétrie native, verrouillée par une garde).

**Preuve que le canal est VIVANT** (c'est la parade au « lu jamais écrit ») : sur les 15 paires
(attaquant, cible) × régimes du montage A, `composite_fields()["mightCrit"]` prend **les deux
valeurs** et vaut le flag NATIF **15/15**. Et l'utilité change de **15.0000 exactement** entre les
deux régimes, des deux côtés.

## 3. Mesure — trois étages, trois observables

### A. SOURCE du flag (`probe_r34_overkill_decision.py --part source`)

Cinq régimes de crit couvrant les **quatre cadrans** de la conjonction — sans `chance-only` et
`dmg-only`, une corrélation « tout à 1 / tout à 0 » ne prouverait pas que les DEUX `GetStat` sont
lus (un `MightCrit = CritDamage > 0` seul passerait aussi).

| régime | `--crit` | CritChance | CritDamage | `pred.mightCrit` live | `CouldCrit` | producteur offline |
|---|---|---|---|---|---|---|
| natural | *(aucun)* | 0 | 0 | False | False | False |
| crit-on | `100,1` | 100 | 1 | **True** | True | **True** |
| crit-off | `0,0` | 0 | 0 | False | False | False |
| chance-only | `100,0` | 100 | 0 | **False** | False | False |
| dmg-only | `0,1` | 0 | 1 | **False** | False | False |

Accord **15/15** sur les deux axes (live↔`CouldCrit`, natif↔producteur offline).

### B. CANAL D'UTILITÉ — formule ISOLÉE (`--part utility`)

Les DEUX côtés sont nourris des **mêmes prédictions NATIVES** (`aiPlaybookPredict`), le natif étant
le scorer invoqué en direct (`pairUtility` = `ComparablePlaybook$$CalculateUtilityFromPredictions`).
Tout écart est donc un gap de **LOGIQUE**, jamais de feed.

Régime imposé ET vérifié : `PV <= rawMax < 2 × PV` **et** `rawMin < PV` — létal MAIS sous le seuil
(`overkillDmgPctOfHealth` = 100). Tueur `ultraInceptorSgt`, **sans le trait `ThrillSeekers`** : le
rider « defeats an enemy with a Crit → always overkilled » forcerait `isForceOverkill` et rendrait
l'observation ambiguë (le confond que #R33 avait dû lever côté COMBAT). `forceOverkill = False`
est asserté dans les deux régimes.

PV = 10836, bornes RAW natives `[7218, 10836]` (identiques dans les deux régimes) :

| régime | `mightCrit` | utilité NATIVE | port **AVANT** | port **APRÈS** |
|---|---|---|---|---|
| crit-off | False | 133.2903 | 133.2903 | 133.2903 |
| crit-on | True | **148.2903** | **133.2903** | **148.2903** |
| Δ (on − off) | | **15.0000** | **0.0000** | **15.0000** |

**15.0000 = `PossibleOverkill` du BC, au centième.** Le port d'avant était d'accord au régime sans
crit et faux de tout le terme au régime avec crit.

3ᵉ régime `crit-on-min` (PV = borne RAW **MIN** = 7218) : les DEUX bornes deviennent létales et
sous le seuil, donc `WillBeOverkill` **atteint** le test de pourcentage. Le natif y passe `0` en
dur ⇒ natif == port == 214.9723. C'est la seule configuration où une mutation qui câblerait
`mightCrit` dans `WillBeOverkill` mord (écart mesuré sous mutation : **−25.0000** =
`DefinitelyOverkill(40) − PossibleOverkill(15)`) ; au régime PV = rawMax elle est **quiescente**.

### C. CLASSEMENT — le terme déplace un CHOIX (`--part rank`)

**2ᵉ porteur** (`orksRuntherd`, là où B tourne sur `ultraInceptorSgt`) et **2ᵉ régime** (deux cibles
descendues dans deux bandes d'overkill distinctes).

Le composite Damage(34) est **discontinu** — poids BC re-dérivés de la mesure : DamageDealt ≤ 100,
PossibleKill 33.33, DefinitelyKill 100, PossibleOverkill 15, DefinitelyOverkill 40. Passer de
`PossibleKill` à `DefinitelyKill` vaut **+66.67, quatre fois le terme sous test** : une cible qu'on
descend **saute par-dessus** la fenêtre de 15 points (mesuré : u(B) passe de 106.67 à 173.33 en
franchissant `hp = rawMin`). La seule fenêtre atteignable met les deux cibles dans la **même** classe
de kill et dans deux classes d'**overkill** différentes :

* A dans `(R/2, rawMin]` → `pct_max < 100` ⇒ verdict = `MightCrit` (le terme sous test) ;
* B dans `(rawMin/2, R/2]` → `pct_max >= 100` ⇒ overkill **inconditionnel** (+15 toujours) ;
* et l'écart de terme dégât `80 × (hp_A − hp_B) / H` doit rester < 15.

Descente pilotée (`--no-ai`, géométrie drivée, activations rafraîchies), R = 18817, rawMin = 12545 :

```
it5  PV A=10952  B=7883
     port AVANT   A=166.5551  B=168.5087  -> argmax B
     port APRES   A=181.5551  B=168.5087  -> argmax A
     natif        A=181.5551  B=168.5087  -> argmax A
```

**Le port d'avant choisissait une autre cible que le jeu.** Ce n'est donc pas « un scalaire qui
bouge » : c'est une décision qui change.

## 4. Pièges de harnais payés dans ce cas (tous attrapés par une garde, aucun deviné)

1. **`applyAction` rend `ok=True` SANS RIEN MUTER — quatre fois.** Trois causes distinctes, toutes
   silencieuses et toutes lisibles comme « pas de bascule » : (a) l'attaquant n'était pas à portée
   (attaque mêlée à distance) ; (b) l'attaque normale est un `ActiveAbilityType` **CONCRET
   per-unit** — `tauMarksman` a `1076` (`MV71SniperDroneSquadAttackAbility`), et la constante `69`
   ne vaut pas pour tout le monde ; (c) **placer les unités (`applyAction move`) ÉPUISE leurs
   activations**, et quand toutes mes unités ont agi le jeu auto-termine mon tour. Parades portées
   dans le probe : `normal_attack_id()`, `move_adjacent_to()`, `refresh_activations()`, et surtout
   une **relecture des PV après chaque coup** qui ARRÊTE le montage plutôt que de conclure.
2. **`--armor-target` n'est PAS un amortisseur gratuit** : il réduit le dégât RÉEL *et* la
   prédiction (utilité tombée à 16.66 à armure 8000), donc il détruit le régime au lieu de
   l'affiner.
3. **Le pas de descente doit être petit devant la largeur de bande** (`0.167 × R`) :
   `astraBullgryn` et `orksRuntherd` retirent `0.65 R` d'un coup et sautent les deux bandes
   (mesuré : 18817 → 6509 → 0). D'où `tauMarksman` comme pas de descente, et un re-essai sur
   plusieurs seeds — l'atterrissage dans la fenêtre dépend du tirage.

## 5. Ce qui n'est PAS couvert — résidus NOMMÉS

1. **`isPreventOverkill@+0xB3` n'est pas porté sur la face DÉCISION.** `might_be_overkill` /
   `will_be_overkill` passent `is_prevent_overkill=0` en dur, là où le natif passe
   `HasFlag(cible, 0x13)` (posé par `FuelledByFury_BlockOverkillEffect$$ApplyInternal`, porteur
   `ultraTitus` — HERO du pool). **Dégradation permissive** : l'IA sur-estime l'overkill contre une
   cible protégée. ⚠ Le décodeur d'events (`playbook-predict.ts`) **n'expose pas** ce champ →
   le chemin « prédictions natives » ne peut pas le porter sans **un changement de hook** (rebuild +
   reinject : hors de portée d'un agent). Le chemin OFFLINE, lui, pourrait le dériver des effets de
   la cible (`scene.effects(tgt)`), mais poser la clé d'un seul côté re-crée l'asymétrie que ce cas
   vient de fermer. À traiter en même temps que le capteur.
2. **`runner/operations/damage_utility.py::_target_utility` ne pose pas la clé.** C'est le port du
   sélecteur DSL `IdunBattle.Entities.Selectors.SortUnitsByDamageUtilitySelector$$Select`, qui bâtit
   nativement une vraie `DamagePrediction` (donc avec `MightCrit`). Le port y fabrique un `pred`
   synthétique depuis `(dmin, dmax)` et n'a pas l'attaquant sous la main : il faudrait faire
   descendre `owner_id` depuis les 3 call-sites (`abilities/votann.py::AncestralFortune`,
   `abilities/thousandsons.py::Doombolt`, `operations/triggers/loki/final_justice.py`). **Non porté
   ici faute de pouvoir le VALIDER** : il faudrait un montage FinalJustice/AncestralFortune en
   régime létal-sous-le-seuil avec un caster `CouldCrit` — un port spéculatif serait pire que
   l'absence. Comportement actuel = celui d'avant #R34 sur ce chemin (pas de demi-canal).
3. **`ForceOverkill@+0xB2` reste `False` offline.** Le décompilé montre que `DamagePredictionQuery$$
   GetAttackPrediction` `memset` sa struct d'entrée et n'écrit **jamais** `+0x68` (seul `+0x6a` est
   posé à 1) : dans le chemin de prédiction standard, `data.forceOverkill` est faux et le rider
   ThrillSeekers exige en plus `data(+0x69) || data(+0xB8)`, laissés à 0. Le défaut `False` du port
   est donc correct **pour ce chemin** ; les entrées `+0x69`/`+0xB8` n'ont pas été tracées
   individuellement jusqu'à leur écrivain, c'est la seule part d'hypothèse restante.
4. **Le producteur `attacker_ctx` n'est pas branché sur les call-sites RUNNER** de
   `get_attack_prediction` (`runner/damage_model.py::normal_attack_per_hit_range`,
   `runner/operations/triggers/loki/final_justice.py::_normal_attack_health_range`,
   `runner/abilities/darkangels.py`) : aucun d'eux ne lit `might_crit` (ils ne consomment que les
   bornes de dégât), donc c'est sans effet — mais ce sont les points d'entrée à câbler le jour où
   le résidu 2 sera fermé.
