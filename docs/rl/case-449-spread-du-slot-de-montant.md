# #449 — le slot de montant APPLIQUE le spread ±20 % (et le canal qui l'avait « validé » ne savait pas le dire)

Deux ports lisaient le **même** slot natif de façon **incompatible**. Ce n'est pas un arbitrage :
le décompilé tranche, et une mesure directe le confirme sur les deux porteurs.

| lecture | où | ce qu'elle affirmait | verdict |
|---|---|---|---|
| (A) | `light_im_up.py` (#419-r1 tranche 5, PR #495), slot `0x28` | le montant **passe** par le spread ±20 % | **JUSTE** |
| (B) | `psyker.py`, `avalanche_of_muscle.py` (+ `fury_of_the_ancients.py`), slot `0x23` | canal « prédéfini », `spread_pct=0` | **FAUX** |

## 1. La convergence, lue au décompilé

Les deux slots atteignent le **même corps**, et il n'y a **pas de régime propre** à l'un ou à l'autre :

```
BattleQuery$$GetMultiHitAttackPrediction            (slot 0x28)
   -> boucle `hits` fois sur
BattleQuery$$GetAttackPrediction  (surcharge à montant ; l'autre surcharge à montant
   construit d'abord un `UnitPosition` puis appelle celle-ci)     (slot 0x23)
   -> `IDamagePredictionQuery` slot 10, avec le LITTÉRAL `hits = 1`
DamagePredictionQuery$$GetAttackPrediction  (surcharge `initialDamage` / `hits`)
   -> boxe le montant en `Nullable<int>` à `DamagePredictionRequest+0x58`
   -> écrit le LITTÉRAL `1` à `DamagePredictionRequest+0x6a`
DamagePrediction$$PredictAttackRaw
       damage = Math.Max(0, request<+0x58>.GetValueOrDefault())
   if (request<+0x6a> == 0)                    -> MinMaxDamageFix64(damage, maxOverride ?? damage)
   else if (this.<+0x10> == null)              -> NRE
   else if (this.<+0x10>.<+0x31> != 0)         -> MÊME branche PLATE
   else -> DamagePrediction$$GetBaseDamageFix64(request, Fix64(damage), isMaxOut)
                = { <IDamageCalculations slot 8>(d), <IDamageCalculations slot 9>(d) } = ±20 %
```

Trois faits qui ferment la question :

* **`+0x6a` vaut `1`, en dur, dans les TROIS surcharges** de
  `DamagePredictionQuery$$GetAttackPrediction` (offsets recalculés deux fois : depuis la base du
  `memset(0xb8)` de la requête, puis depuis la recopie faite juste avant l'appel d'interface).
* **`this.<+0x10>` est `configuration`** — `DamagePrediction$$.ctor` le nomme
  (`configuration@+0x10`, `damageCalculations@+0x20`, ce dernier étant celui que
  `GetBaseDamageFix64` interroge par ses slots 8/9). C'est un fait de la **BATAILLE**, identique
  pour les trois playbooks : aucun d'eux ne peut prendre une branche que l'autre ne prend pas.
* `GetBaseDamageFix64` **est** le foyer ±20 % déjà porté
  (`services/damage_prediction.get_base_damage_fix64`).

⇒ `spread_pct=0` et « le spread par défaut » ne peuvent pas être vrais ensemble, et c'est (B) qui
tombe.

## 2. La mesure DIRECTE — `probe_449`, MC1_67 / seed 41504

Le canal : les `ProbableDamageEvent` que le playbook **natif** construit, capturés sur
`IdunBattle.AI.Playbook.ProbableDamageEvent$$.ctor` (`ncPlaybookPredict`, champ `captured`), lus
sur leurs **bornes brutes** `willKillDmg` / `mightKillDmg` (= `DamagePredictionResult@+0x24/+0x28`,
non capées par les PV). Trois hypothèses, séparées par la même mesure : prédéfini ⇒ `min == max` ;
`RandomAmount(min,max)` ⇒ le rapport de la config ; spread ⇒ `{0,8·d ; 1,2·d}`.

| régime | montant | natif | port `spread_pct=0` | port spread défaut |
|---|---|---|---|---|
| `A_CHARGE` — `astraBullgryn` charge `astraCreed`, `AvalancheOfMuscle` (1028) | `extraDmg` 599 | **[11, 13]** | [12, 12] | **[11, 13]** |
| `P_SPLASH` — `spaceStormcaller` tire à 2 hex, `PsykerExtraAttack` (1013) | 402 | **[322, 482]** | [402, 402] | **[322, 482]** |

`0,8 × 402 = 321,6 → 322` et `1,2 × 402 = 482,4 → 482` : les deux bornes tombent EXACTEMENT, et
la lecture au spread par défaut reproduit le natif **sur les deux bornes, sur les deux playbooks**.
Le **rapport** des bornes n'est PAS un critère (11 → 13 n'est pas 1,5) : l'armure est
**soustractive**, elle déplace les deux bornes ensemble ; ce qu'elle conserve, c'est leur **écart**.

## 3. Pourquoi (B) avait « passé » — le canal était DÉGÉNÉRÉ

L'accord qui validait (B) portait sur une **utilité finale**. Or le composite `Damage` consomme
`IdunBattle.AI.Utilities.DamageUtility$$GetHealthDamage` = `MinMaxDamage$$Avg(...)`, la **MOYENNE**
des deux bornes — et `avg(0,8·d ; 1,2·d) == d`. Hors cap PV et hors bascule de kill, les deux
lectures rendent le **même** nombre. Mesuré, sur le même montage que ci-dessus :

```
A_CHARGE   u(spread 0) = 0.132758048   u(spread 20) = 0.132758048   delta = +0.000000000
P_SPLASH   u(spread 0) = 4.214278226   u(spread 20) = 4.214278226   delta = +0.000000000
```

Et le même verdict tombe sur `probe_32d_fury`, re-joué : ses variantes `avg0` et `avg20` rendent
`9.660285492973332` / `10.866318147871546` **toutes les deux**, à 1e-15 près. Ce que cette matrice
avait réellement discriminé (canal *plage* vs *moyenne*, `hits=1` vs `hits=2`) reste acquis ;
l'axe **spread** n'y était **pas mesuré**. Idem pour l'accord psyker à `4e-5` : ce n'était pas
« presque juste », c'était **exactement le même chiffre des deux côtés** — l'écart venait d'ailleurs.

> La leçon opérationnelle : un accord obtenu sur un canal qui **ne peut pas** exprimer la
> différence n'est pas une validation faible, c'est un **non-événement**. Avant de citer un accord,
> vérifier que le montage EXERCE la grandeur qu'on prétend valider.

## 4. Ce que le correctif CHANGE — la généralisation `P_KILLFLIP`

Un régime où la lecture est **observable**. Les PV de la cible de splash sont calés à **363**,
strictement entre la borne basse à spread (322) et le montant plat (402) :

```
natif       [322, 482]   willBeKill = False    mightBeKill = True
port sp=0   [402, 402]   killSure   = True     u = 199.452054795
port sp=20  [322, 482]   killSure   = False    u = 143.698630137
                                               delta u = -55.753424658
```

Le natif **refuse** le kill garanti ; la lecture `spread_pct=0` le **garantissait**. C'est la
bascule `DefinitelyKill` → `PossibleKill` de `IdunBattle.AI.Utilities.KillUnitUtility`, plus le
décalage du terme `DamageUtility` sous cap PV : **~56 points d'utilité** sur une seule cible de
splash. La dégradation était donc réelle et **optimiste** (l'IA se croyait sûre de tuer), pas
cosmétique — simplement invisible du canal qui l'avait validée.

## 5. Le correctif

Trois lecteurs du même foyer, tous corrigés (le `spread_pct=0` retiré, donc le défaut ±20 %) :

* `engine/playbook/psyker.py::PsykerPlaybook._predict_amount_vs_target` — **MESURÉ** (§2)
* `engine/playbook/avalanche_of_muscle.py::AvalancheOfMusclePlaybook._predict_extra_vs_target` —
  **MESURÉ** (§2)
* `engine/playbook/fury_of_the_ancients.py::FuryOfTheAncientsPlaybook._get_damage_prediction` —
  corrigé **PAR STRUCTURE** (§1) ; son call-site natif est
  `IdunBattle.AI.Playbook.Loki.FuryOfTheAncientsPlaybook$$GetDamagePrediction`, qui appelle la
  **même** famille `BattleQuery$$GetAttackPrediction` (interface `IBattleQuery`, slot `0x24` de la
  klass — une AUTRE surcharge du même nom, qui converge sur les mêmes trois surcharges de
  `DamagePredictionQuery$$GetAttackPrediction`).

Les docstrings qui affirmaient « canal predefined SANS spread ±20 % » sont réécrites — c'était la
racine documentaire de la contradiction, recopiée d'un port à l'autre (`psyker.py` ->
`fury_of_the_ancients.py` -> `avalanche_of_muscle.py`, chacun citant le précédent).

## 6. Validation

* `probe_449_spread_slot_predefini.py` — **PASS** (les 3 régimes ci-dessus). Contre-épreuve
  intégrée : la lecture `spread_pct=0` doit rendre `min == max`, sinon le bouton de mesure ne mord
  pas et la comparaison ne prouve rien.
* `probe_32d_fury.py` — re-joué : `avg0 == avg20` (voir §3). Le repère historique de `case-32`
  (feuille `20.52660365588963`) est **inchangé** par le correctif.
* Gardes de non-régression re-jouées : voir §8.

## 7. Résidus NOMMÉS

* **`#449-r1`** — les bornes propres de `FuryOfTheAncients` ne sont **NON CONFRONTÉES** : sa face
  est **MOVE**, et `ncPlaybookPredict` n'expose que des voies ATTACK
  (`attackUtilityInSteps` / `...ForMainTarget` / `...ForSecondaryTarget`). Le capteur manquant est
  nommé : une voie `movementUtilityInSteps` sur `rpc-nc-predict.ts` rendrait ce porteur mesurable
  au même titre que les deux autres (elle demande une fenêtre de reinject).
* **`#449-r2`** — la **face COMBAT** n'est pas dans ce périmètre et n'a pas été touchée :
  `runner/operations/triggers/loki/psyker.py` passe `spread_pct=0` à `execute_normal_like`, et
  `.../cursed_plague_bell.py` pose `amount_spread_pct=0`. L'artefact natif y est un
  `AttackDamageBehaviour` / `Operation`, **pas** `PredictAttackRaw` — la conclusion de ce cas ne
  s'y transporte pas telle quelle, et l'exécution y est validée par des hp-diff. À RE séparément.
* **`#449-r3`** — le byte `DamagePredictionRequest+0x6a` n'est pas **nommé** : on a lu qu'il vaut
  `1` en dur dans les trois surcharges de `DamagePredictionQuery$$GetAttackPrediction` et qu'il
  route vers `GetBaseDamageFix64`. Les producteurs de requête qui y écriraient `0` (donc la branche
  plate) n'ont **pas** été énumérés. De même, `configuration.<+0x31>` (le second aiguillage vers la
  branche plate) est lu comme faux **en pratique** — les mesures de §2 le prouvent — mais son
  champ n'est pas nommé.
* **`#449-r4`** — régime **ÉLÉVATION** non couvert : le montage se tient sur un palier unique
  (les gates d'adjacence portent une porte `|Δelev| < 2` qui changerait les régimes mesurés, pas
  le canal de spread).

## 8. Relevé de validation (2026-08-02, APRÈS rebase sur `origin/master` = `497aa9b7`)

| ce qui a été joué | résultat |
|---|---|
| `test_449_spread_slot_predefini_live.py` (garde neuve) | **5 passed** |
| `test_445_avalanche_of_muscle_pair_term_live.py` (garde du port modifié) | **5 passed** |
| `test_419_t6_cosmic_horror_pair_term_live.py` (mergé APRÈS ma base) | **9 passed** |
| `test_419_r1_fire_of_absolution_pair_term_live.py` (mergé APRÈS ma base) | **7 passed** |
| `test_446_boltstorm_pair_term_live.py` (voisin du même registre, avant rebase) | **5 passed** |
| `tests/engine/runner/test_psyker_splash_live.py` (face COMBAT, non touchée) | **1 passed** |
| `probe_45_psyker.py` (repère historique) | `17.853817519579994` vs L3 `17.85381752299145`, **delta −3,4e-9** — inchangé par le correctif (canal aveugle) |
| `probe_32d_fury.py` | `avg0 == avg20` sur les deux cibles ; repère `case-32` inchangé |
| `pwsh -File scripts/ratchets.ps1` | **25 cliquets, BANQUE VERTE, rc=0**, mur 82,7 s |

**Contre-épreuve du garde lui-même** (jouée, puis annulée) : `spread_pct=0` ré-injecté dans
`psyker.py` et `avalanche_of_muscle.py` → `test_449` rend **1 rouge / 4 verts**, et le rouge est
`test_source_reading_matches_the_native`. Les quatre autres restent vertes — c'est la
démonstration que les gardes qui FORCENT le spread des deux côtés sont indifférentes à la source,
et qu'une garde sans cette cinquième assertion **n'aurait pas pu rougir** sur une régression.

**Ce qui N'EST PAS couvert** : les régimes ÉLÉVATION (`#449-r4`), les bornes propres de
`FuryOfTheAncients` (`#449-r1`), la face COMBAT (`#449-r2`), et l'énumération des producteurs de
requête qui écriraient `0` à `+0x6a` (`#449-r3`).
