# #375 — le capteur triggered « muet », et la fixture qui n'arrivait jamais

Build lu : `rnca9r7q6c`. Suite directe de #369 (`case-369-oracle-triggered-playbook.md`), dont le
troisième contrôle — « les `captured` portent **972** et non **971** » — n'avait pas été joué.

## 0. La question binaire

> Pourquoi `ncPlaybookPredict` répond, route juste (`1103 → LightImUpPlaybook`), et rend pourtant
> `capturedCount: 0` / `captured: []` ?

**DEUX verrous indépendants, aucun n'étant le capteur.** Le premier interdit à la voie
`attackUtilityInSteps` d'atteindre l'ancrage ; le second rendait le régime discriminant inatteignable
**quelle que soit la voie**.

## 1. Verrou A — le case ne NOMME aucune ability (voie `attackUtilityInSteps`)

`buildUtilityAttackCase` passait à `UtilityAttackCase$$Base` un `Nullable<AbilityOrEffect>`
**zéro-rempli**, donc `HasValue = false`. Or
`IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$IsRegularAttack`
commence par `Nullable<AbilityOrEffect>.get_HasValue()` sur `case+0xf0` et rend `false` sec. Et c'est
la **première** chose que testent les deux machines à états qui construisent un `ProbableDamageEvent` :

| machine à états | gates en tête | sortie si refus |
|---|---|---|
| `…Loki.LightImUpPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` | `IsMeleeAttack` **puis** `IsRegularAttack` | `yield Fix64(0)`, état 1 ou 2 |
| `…Loki.MassiveScythingTalonsPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` | `IsRegularAttack` (1ʳᵉ instruction) | `yield Fix64(0)`, état 1 |

⇒ **`capturedCount: 0` était la réponse EXACTE du natif au case soumis**, pas un capteur défaillant.
Mesure du 2026-07-31 (runner `MC1_67`, `orksWarboss` u81) : `ok: true`, aucune erreur,
`triggeredUtilities: [0]` — **un seul** `Fix64` yieldé, ce qu'aucune autre branche ne produit.

**Ce qui départage (a) « capteur non armé sur la voie » de (b) « ancrage non traversé »** : sur le
MÊME montage, le MÊME capteur, le MÊME RPC, `via: "attackUtilityForMainTarget"` rend
`capturedCount: 1` avec une prédiction complète. (a) est réfuté.

**Troisième cas, raison DIFFÉRENTE** — `1247` : `FuryOfTheAncientsPlaybook` **ne surcharge pas**
`CalculateAttackUtilityInStepsInternal` (aucun symbole dans `ghidra/functions.tsv`) ; le corps hérité
`TriggeredAbilityPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__37u003C__Il2CppFullySharedGenericTypeu003E$$MoveNext`
yielde un `Fix64(0)` et rien d'autre. Sa prédiction (slot 4, TRONCATURE) vit sur la voie MOUVEMENT :
`FuryOfTheAncientsPlaybook$$GetDamagePrediction` n'a qu'**un** appelant, `$$GetDamagedEnemyUtility`.

## 2. Verrou B — la fixture de #369 était ÉCRITE mais jamais JOUÉE

`rl_collect_batch._load_seed_bc` appelle `catalog_inject.refresh_ability_configs` à **chaque**
chargement, y compris sur un seed BC custom (rattrapage #254). Le refresh remplace toute config qui
diffère du gameconfig vivant par `synthesize_ability(name)` — donc **il écrase exactement ce qu'une
fixture vient d'y écrire**, sans un mot.

Mesuré : `LightImUp.minDmg[49]` écrit à `20000` sur disque, **relu `831`** après `_load_seed_bc`, et
`LightImUp` figure dans les « 4 rafraîchies » à chaque build, patch ou pas. Le couple réellement joué
était donc le NOMINAL `831 + 1109 = 1940 ≡ 0 mod 4` — le régime **non discriminant** que
`case-350r3b` §5 avait nommé comme second verrou.

**Suite → #380** : le recensement des AUTRES fixtures a trouvé **0 patch de valeur écrasé** mais un
**second axe** que ce §2 ne nommait pas — la 2ᵉ boucle du rattrapage *comble* une config
volontairement absente, ce qui rendait le bras négatif de `probe_226` indiscernable de ses témoins.
Clé symétrique `withheldAbilityConfigs` + recenseur `probe_380_seed_bc_patch_survival.py` :
`case-380-recensement-patchs-seed-bc.md`.

**Parade** : sidecar `<seed-bc>.pins.json` (`{"pinnedAbilityConfigs": ["PassiveAbilities/LightImUp"]}`),
écrit par `write_variable_patched_seed_bc` et lu par `_load_seed_bc`, qui le passe en `skip`.
Opt-in, nommé, jamais un interrupteur global ; et la config épinglée est **re-synthétisée AVANT**
d'être patchée, donc on fige du frais patché, jamais une capture périmée. Une épingle orpheline
**lève**.

## 3. Verrou C, découvert en confrontant — l'écart de 1 est écrasé par l'étage aval

La valeur demi-vers-le-pair entre dans le `DamagePredictionResult` par l'argument `damage` de
`GetAttackPrediction` ; l'étage aval la **multiplie** (profil de dégât × armure de la cible).

| armure de la cible | `damage = 971` | `damage = 972` |
|---|---|---|
| nominale (`necroWarden`) | `healthDmgMin = 175` | **175** — écart perdu |
| `--armor-target 0` | `1166` | **1167** — écart conservé |

⇒ **une mesure prise à l'armure nominale aurait été verte et entièrement vide** (les trois montages
coïncident, donc `test == high` est vrai par accident). L'étape 4 du probe le refuse désormais :
elle exige `REF 971 != REF 972` avant tout verdict, sinon **NON CONFRONTÉ** (`rc 2`).

## 4. Ce qui est livré

- **`scripts/python/catalog_inject.py`** — `pins_path` / `read_pins` / `write_pins`,
  `refresh_ability_configs(bc, skip=)`, et `write_variable_patched_seed_bc` qui refresh-puis-patche
  et pose le sidecar.
- **`scripts/python/rl_collect_batch.py`** — `_load_seed_bc` lit le sidecar, l'ANNONCE, et **lève**
  sur une épingle orpheline.
- **`scripts/python/probe_369_playbook_keyspace.py`** — étape 2 : cliquet de survie de la fixture
  (relecture PAR `_load_seed_bc`, pas depuis le disque) ; étape 3 : assertion de la FORME du silence
  (`check_insteps_shape`, avec la raison native par ability) ; **étape 4 NEUVE** : l'échelle
  971/972 à trois montages (`check_half_even`).
- **`frida/hooks/*` — INERTE jusqu'à la prochaine fenêtre de reinject** :
  `buildUtilityAttackCase(..., attackAbility)` construit un vrai `Nullable<AbilityOrEffect>` via
  `IdunBattle.Core.AbilityOrEffect$$op_Implicit(ActiveAbilityType)` (classe, taille et champs
  `value`/`has_value` résolus PAR NOM depuis le paramètre lui-même — aucun offset écrit) ;
  `readTriggeredGates` rend `isRegularAttack`/`isMeleeAttack` ; le RPC accepte
  `attackAbility: <id> | "normalAttack"` et ÉCHOE `attackAbility` + `gates`. Un `capturedCount: 0`
  est désormais NOMMÉ.
- **`scripts/python/tests/test_369_playbook_keyspace_offline.py`** — 23 tests (13 neufs).

## 5. Validation

**Le troisième contrôle de #369 est JOUÉ et VERT** (`via: attackUtilityForMainTarget`, armure 0) :

| montage | minDmg+maxDmg | trunc / half-even | `(healthDmgMin, healthDmgMax, …)` |
|---|---|---|---|
| REF 971 | `831 + 1111 ≡ 2` | 971 / 971 | `(1166, 1748, …)` |
| **TEST** | `831 + 1112 ≡ 3` | **971 / 972** | **`(1167, 1749, …)`** |
| REF 972 | `831 + 1113 ≡ 0` | 972 / 972 | `(1167, 1749, …)` |

⇒ le natif joue **972**, le DEMI-VERS-LE-PAIR. Reproduit sur un **second couple discriminant**
(`700 + 1003` → 851/852 : `(1022,1532)` / `(1023,1533)` / `(1023,1533)`) et sur un **second couple
(board, seed)** (`C4_09` / 999, chiffres identiques).

**Contre-épreuve adversariale jouée** : le même étage 4 relancé à l'armure NOMINALE rend
`NON CONFRONTE` avec le message qui nomme la cause — il refuse de verdir sur une mesure vide.

**Non couvert** : la voie `attackUtilityInSteps` reste MUETTE tant que le hook n'est pas réinjecté ;
`1054 MassiveScythingTalons` n'a pas de porteur dans ce montage (`GetAbilityState` lève si le caster
ne porte pas l'ability) ; `attackUtilityForSecondaryTarget` rend 0 sans capture — lu au décompilé,
`LightImUpAbility$$GetPossibleSecondaryTargets` rend un ensemble VIDE dans cette géométrie
(`Count == 0` → `return Fix64(0)` avant tout `ProbableDamageEvent`), ce qui se lèverait en
rapprochant des unités.
