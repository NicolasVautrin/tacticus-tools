# #419-r1-tr9-r4 — `nrOfHits` n'est pas le compte de coups du fold, c'est sa BASE D'ARME

**Verdict : BUG DE PORT, LOCALISÉ ET FERMÉ.** Le facteur ~2 relevé par #419-r1-tr9 sur la prédiction
de `1128 Boltstorm_NormalAttack` n'était ni un étage compté deux fois, ni une base doublée, ni un
artefact de montage : c'était un **compte de coups**. Le correctif vit dans
`scripts/python/engine/playbook/prediction/normal_attack.py`.

## 1. La re-mesure — le relevé se reproduit, et il se décompose

Le relevé d'origine (`port [1762, 2642]` contre `natif [876, 1314]`) a été **rejoué tel quel** sur
`origin/master` courant, en remontant le régime `foreign` de tr9 : il est intact. Il ne portait
qu'un champ, invisible dans le relevé d'origine parce que celui-ci ne publiait que les bornes :

```
[necroWarden] nat=(876, 1314, h2)   port=(1762, 2642, h4)
             meta port : base=1806 hits=1 pierce=20 mods=[1.5]
                         followup={'min': 1329, 'max': 1992}      <- 3 coups
             ctx : terrain=DryBush  tgt_effects=[..., 'LightCover']  weapon_hits=3
```

Le port fait **1 coup de base + 3 de fold**, le natif **2 au total**. La cible est sur une tuile
`DryBush`, donc porteuse de `LightCover` : **−2 coups, plancher 1**. Le port appliquait ce malus à
la base (3 → 1) mais **pas au fold** (3, la constante brute).

⚠ Le second écart du même relevé — **3 points contre `astraBullgryn`** (`#419-r1-tr9-r3`) — a
**DISPARU** : les mêmes cibles rendent aujourd'hui `natif == port` au bit près. C'est #503
(l'arrondi INTER-FACES) qui l'a fermé ; le rejeu le confirme, il n'y a plus rien à y faire.

## 2. Ce que dit le décompilé — le fold appelle la MÊME façade de coups que la base

`IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$GetAdditionalDamagePrediction`
fait **deux** appels d'interface, et le premier alimente le second :

```csharp
amount  = <slot 4>( TalonOfHorus_NormalAttackAbility.GetAdditionalDamageAmount(...) ); // CalculateAverage
nrHits  = AbilityConfiguration.GetNumberConstant(cfg, 0x2f);   // « nrOfHits »
profile = AbilityConfiguration.GetDamageProfile(cfg);

hits    = <slot 0xb5>( caster, target, /*hitGroupIndex*/ 0, <AbilityOrEffect>, nrHits );
return    <slot 0x28>( caster, target, casterPosition, <AbilityOrEffect>, amount, profile, hits );
```

Le slot `0xb5` est **`GetAttackHits`** — identifié par le proxy
`IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass216_0$$u003CGetAttackHitsu003Eb__0`,
dont tout le corps est cet appel sur la MÊME interface, au MÊME slot, avec la MÊME forme
d'arguments. Il mène à `IdunBattle.Core.Services.BattleQuery$$GetAttackHits(attacker, defender,
hitGroupIndex, ability, attackWeaponHits)` puis à
`IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`, dont les paramètres sont NOMMÉS dans le
binaire et dont le corps est celui que le port mirrore déjà
(`engine/services/attack_hits_formula.py`) : `weaponHits + GetStat(0x11 ExtraHits)`
`[+ GetStat(0x17 ExtraHitsMelee) si IsMeleeAttack]`, puis les descripteurs de bonus/malus de coups
(dont les malus DÉFENSEUR), et `System.Math.Max(hits, 0)` en sortie.

Trois lectures en découlent, dont deux ne se devinent pas :

* **`nrOfHits` occupe la place de `weapon.Hits`.** C'est le paramètre `attackWeaponHits`, pas le
  résultat. Le fold est donc « une attaque de plus » au sens plein : elle repasse par toute la
  chaîne des coups.
* **Le couple passé est celui de la BASE** : `caster` = `AbilityEntities@+0x08`, `target` = `@+0x10`,
  lus sur la copie de l'`abilityState`. Aucun canal ne peut donc diverger entre les deux étages —
  c'est pourquoi le port partage désormais un seul dict d'arguments, `weapon_hits` mis à part.
* **Le mold KLAW n'est PAS concerné.**
  `IdunBattleLogic.Entities.Abilities.Active.Loki.ProperKilly_NormalAttackAbility$$GetKlawAttack1Prediction`
  lit le MÊME `GetNumberConstant(cfg, 0x2f)` mais **boucle** dessus (`GetKlawAttack1HitPrediction`
  répété, sommé par `DamagePredictionResult$$Add`) et n'appelle **jamais** `GetAttackHits`. Y
  propager le correctif par analogie aurait été un fork de port.

Le mold MÊLÉE jumeau
(`RighteousRepugnance_NormalAttackAbility$$GetAdditionalDamagePrediction`) porte le corps
**identique**, slot `0xb5` compris — vérifié ligne à ligne, pas supposé. Le port partageant déjà la
fonction, il reçoit le correctif du même coup.

## 3. Les quatre régimes, et ce que chacun est SEUL à trancher

`python scripts/python/probe_419r1tr9_r4_boltstorm_pred.py --state-file <abs> --regime <r> --mutants`

| régime | caster | ce qu'il installe | ce qu'il tranche |
|---|---|---|---|
| `plain` | `templAggressor` | 3 cibles à distance 2, même élévation, hors cover | le socle SANS malus — le régime où l'ancien port était déjà juste (non-régression) |
| `cover` | `templAggressor` | une cible sur `DryBush` → `LightCover` (−2, plancher 1) | qu'un malus DÉFENSEUR traverse le fold |
| `bigtarget` | `templAggressor` | une cible adjacente au porteur `BigTarget` (−1 RANGED aux alliés) | la même conclusion par une **provenance** (aura d'un tiers) et une **amplitude** (−1) différentes |
| `melee` | `adeptMorvenn` | cible AU CONTACT (gate `IsMelee` du mold jumeau) | que la base d'arme du fold est `nrOfHits` (**3**) et **non** les coups de l'arme (**2**) |

Le régime `melee` n'est pas un doublon : c'est le **seul** montage où les deux modèles candidats
divergent. Sur `templAggressor`, `nrOfHits` et les coups du `Bolter` valent tous deux 3 — aucune
mesure ne pourrait y trancher, et le décompilé seul le fait. `adeptMorvenn` porte une arme `Power` à
**2** coups pour un `RighteousRepugnance.nrOfHits` de **3** : le natif y rend un fold de 3.

### Mesures (board `MC1_67`, seed 41904, bras apparié `PassiveAbilities=[]`)

Chaque ligne est `(rawMin, rawMax, coups)`, natif **et** port, décomposés en BASE et FOLD :

```
[cover]     necroWarden   TOTAL nat=(876,1314,h2)  port=(876,1314,h2)
                          BASE  nat=(433, 650,h1)  port=(433, 650,h1)
                          FOLD  nat=(443, 664,h1)  port=(443, 664,h1)
            temoins       astraBullgryn h6, tauAunShi h6 -- accord exact
[bigtarget] tauAunShi     TOTAL nat=(1168,2330,h4) port=(1168,2330,h4)
                          BASE  h2 / FOLD h2       -- le -1 traverse
[melee]     tauAunShi     TOTAL nat=(4324,6871,h5) port=(4324,6871,h5)
                          BASE  nat=(2314,3856,h2) FOLD nat=(2010,3015,h3)
            temoins       a distance : AUCUN fold des deux cotes (gate `IsMelee`)
[plain]     les 3 cibles  h6 partout, accord exact base ET fold
```

**Le fold natif est mesuré par différence de deux mesures NATIVES** (bras greffé moins le passif,
même board, même seed, même placement, apparié par `visualId`) : le port n'entre pas dans sa
définition. `DamagePredictionResult$$Add` étant une somme champ à champ, la soustraction est exacte.

### Contre-épreuves — critère = DÉPLACEMENT par rapport au port NON MUTÉ

| mutant | ce qu'il coupe | régime où il mord | déplacement |
|---|---|---|---|
| `hits_raw` | le fold reprend `nrOfHits` BRUT (l'état d'avant) | `cover` / `bigtarget` | `(+886, +1328, +2)` / `(+295, +606, +1)` |
| `hits_from_base` | le fold prendrait les coups de l'ARME | `melee` | `(−670, −1005, −1)` |
| `amount_min` | montant = `minDmg` seul | les quatre | jusqu'à `(−252, −378, 0)` |

Et la **réciproque est gardée** : `hits_raw` ne mord **pas** sur `plain`. C'est ce qui atteste que le
correctif est un raffinement du compte de coups et non un décalage global — s'il mordait là, il
aurait cassé tous les régimes que #446-r1 avait déjà mis en accord.

L'hypothèse « le fold est ajouté deux fois », que le facteur ~2 suggérait, est **réfutée par la
mesure** et non par un argument : le fold natif est non nul, égal au fold du port sur les quatre
régimes, et l'écart d'origine est reproduit **exactement** par le seul mutant `hits_raw`.

## 4. Ce qui a été rejoué

Garde jumelle `scripts/python/tests/engine/test_419r1tr9_r4_boltstorm_pred_live.py` : **6 tests,
0 skip** (51 s, 4 régimes, 6 runners construits et libérés au fil de l'eau). **Contre-épreuve de la
garde elle-même** : le fix retiré (`hits_ctx=None`), elle rougit sur **3** tests
(`fields_match_native_everywhere`, `defender_malus_traverses_the_fold`, `counter_probes_bite_somewhere`).

Non-régression du foyer, 0 skip : `test_446_r1_boltstorm_followup_live` (5), `test_446_r3_repugnance_followup_live`
(5), `test_446_boltstorm_pair_term_live` (5), `test_419r1tr9_rapid_fire_live` (7) — **22 passés**.
Banque de cliquets `pwsh -File scripts/ratchets.ps1` : **27 cliquets, VERTE**, mur 120,8 s.

## 5. Résidus NOMMÉS

* **`#419-r1-tr9-r4-r1`** — le contexte passé à `GetAttackHits` par le fold est l'`AbilityOrEffect`
  du **passif**, pas celle de l'attaque normale ; le port réutilise les arguments de l'attaque
  porteuse, donc `is_normal_attack=True`. Le seul consommateur de ce nœud est
  `IdunBattle.Entities.Effects.Loki.PowerTrip_FullHealthEffect$$CreateEffectHitsBonusForAttack`
  (`IsNormalAttack & OwnerIsCaster`) — aucun porteur dans les montages joués. **NON CONFRONTÉ** : il
  faudrait un attaquant portant `PowerTrip` **et** l'un des deux passifs de fold.
* **`#419-r1-tr9-r4-r2`** — même forme sur `hitGroupIndex` : le natif passe `0` au fold, et le port
  n'a pas de modèle de ce paramètre (il n'apparaît nulle part dans la façade portée). Sans effet
  mesurable ici ; à rouvrir si un descripteur de coups se met à le lire.
* **`#419-r1-tr9-r4-r3`** — la face **COMBAT** du fold n'est pas portée : `engine/runner` ne connaît
  de `1128` que son entrée `ABILITY_ATTACK_TYPE`, et il n'existe aucun mirror de
  `Boltstorm_NormalAttackAbility$$GetAdditionalDamageBehaviour` / `$$ExecuteBoltstorm`. La question
  « le fold d'EXÉCUTION compte-t-il ses coups pareil ? » ne se pose donc pas encore — mais elle se
  posera au portage de cette face, et la réponse ne se déduit PAS de celle-ci (le canal d'exécution
  a son propre chemin de coups, cf. `_run_hits`).
* **`#419-r1-tr9-r5` (hérité, RE-QUALIFIÉ)** — le relevé « `--unit-stat necroWarden:RemainingHealth=300`
  ressort à `2008` » : **2008 est l'ARMURE de `necroWarden`** dans ce montage, lue et re-lue par
  trois runners indépendants. La piste « le levier ne mord pas sur cette unité » est donc à
  reprendre en vérifiant d'abord **quel champ** le relevé lisait. Non tranché ici (hors périmètre) —
  mais un montage bâti sur ce résidu partirait d'une prémisse douteuse.

## 6. Ce que ce cas n'établit PAS

* **Le comportement du fold sous un bonus de coups** (et non un malus) : les trois canaux exercés
  sont un effet porté par la cible (`LightCover`), une aura d'un allié de la cible (`BigTarget`) et
  le socle. `ExtraHits` de l'attaquant, `GetStuckIn` et les overrides (`InescapableAccuracy`) passent
  par la même façade — ils traversent donc le fold **par construction**, mais aucun n'est confronté.
* **Le plancher.** `DamagePrediction$$GetAttackHits` termine par `Math.Max(hits, 0)` et le port
  approxime le clamp par-effet (`min(1, base)`), écart connu et documenté dans
  `attack_hits_formula.py`. Le régime `cover` s'arrête à 1 coup, jamais à 0 : le cas « fold réduit à
  zéro coup » n'est pas atteint.
* **Le mold KLAW** (`ProperKilly`) reste NON CONFRONTABLE — zéro porteur dans ce build. Son
  décompilé a été LU pour établir qu'il n'est pas concerné ; ce n'est pas une mesure.
