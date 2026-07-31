# case-372 — `get_WillBeKill` : les deux entrées qu'on ne voyait pas

Deux résidus sans rapport (`#353-r1` volet b, `#344-r2`) ont nommé le même verrou le même jour :
`IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` lit `CannotBeGuaranteedKilled@0x89`
et `BlockScenarios[0]+0x0c`, et **ni l'un ni l'autre n'était exposé**. Tout verdict sur une gate
`WillBeKill` se prenait en aveugle.

---

## 1. Le décompilé, verbatim (`rnca9r7q6c`)

```
get_WillBeKill(this):
    if (*(char*)(this + 0x89)) return false;                    // CannotBeGuaranteedKilled
    m = (*(long*)(this+0x38) == 0 || *(int*)(*(long*)(this+0x38)+0x18) < 1)
        ? *(int*)(this + 0x1c)                                  // DefaultScenario.Damage.HealthDamage.Min
        : List.get_Item(BlockScenarios, 0)[+0x0c];              // idem, du scénario de BLOCAGE
    return *(int*)this <= m;                                    // CurrentHealth <= m

get_MightBeKill(this):
    return *(int*)this <= *(int*)(this + 0x20);                 // AUCUN gate, AUCUNE liste
```

Que `BlockScenarios[0]` soit un `DamagePredictionScenario` (même type que `DefaultScenario`) n'est pas
supposé : `DamagePredictionResult$$GetBlockScenarioOrDefault` le prouve — son fallback recopie les 36
octets de `DefaultScenario@0x10` — et `get_HealthDamageWithBlock` le recoupe (mêmes deux branches,
bornes `+0x0c`/`+0x10` du scénario).

## 2. Le fait qui tranche les deux résidus : **UN seul écrivain**

`CannotBeGuaranteedKilled@0x89` n'est écrit qu'à un endroit du binaire —
`IdunBattle.Core.Services.DamagePrediction$$PredictNormalAttack`, dernière instruction avant son
`return` — et `DamagePrediction$$CannotBeGuaranteedKilled` n'a lui-même que **ce** seul appelant
(xrefs lues).

| voie de construction | slot `IDamagePrediction` | flag |
|---|---|---|
| `BattleQuery$$GetNormalAttackPrediction` | **9** = `PredictNormalAttack` | **VIVANT** |
| `BattleQuery$$GetAttackPrediction` | `0xb` = `PredictAttack` | 0 |
| `BattleQuery$$GetMultiHitAttackPrediction` | `memset(0xa0)` puis délègue à `GetAttackPrediction` | 0 |

`DamagePredictionResult$$Add` ne fusionne **aucun** des cinq booléens contigus `@0x88..0x8c` — il ne
somme que les bornes, `AppliedHits@0x98`, concatène `IndividualHitDamage@0x80` et fusionne
`BlockScenarios@0x38` par index. Le cumul multi-coups ne peut donc pas rallumer le flag.

Conséquences, chacune répondant à un résidu :

* **`#344-r2`** — `SortAttackersByDamagePredictionSelector.<Select>b__0` appelle `IBattleQuery` slot
  `0x28` = `GetMultiHitAttackPrediction` (7 arguments : attacker, target, attackerPosition, ability,
  damage, damageProfile, hits). Le flag y est **structurellement 0** : la borne `will_be_kill` du port
  n'était **pas permissive**, elle était **exacte sans preuve**. Verdict : *inerte ici*.
* **`#353-r1` volet (b)** — même voie (`ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions`
  emprunte le même slot `0x28`). Le gate est donc **exclu** comme cause de la non-ouverture. Suite
  dans `case-353` §5ter.

## 3. Le capteur (`frida/hooks/game/damage-prediction.ts`)

Champs neufs : `cannotBeGuaranteedKilled`, `blockScenarioCount`, `blockProbability`, `blockKillDmg`,
`blockMightDmg`, `willKillDmgEffective`, et surtout **`willBeKill` / `mightBeKill` déjà calculés**.

Trois choix, chacun payé par une erreur passée :

1. **Le décodeur publie le VERDICT, pas seulement les bornes.** Trois sites ré-assemblaient
   `hp <= willKillDmg` chez eux — `rpc-predict.ts` (dont le champ se disait « mirror EXACT »),
   `projection.ts::applyDmg`, et le port Python. Trois occasions d'oublier le gate. Foyer unique
   désormais ; `projection.ts::applyDmg` prend le résultat décodé au lieu des deux bornes.
2. **Tri-état `null` = non mesuré**, jamais un zéro. Un `false` inventé serait indiscernable d'un vrai
   « pas de kill garanti » — exactement la dégradation silencieuse que #268/#276 ont payée.
3. **Résolution par nom, sauf pour ce qui n'en a pas.** La chaîne du scénario est composée sur la
   classe du champ `DefaultScenario` (`fieldTypeClass`) : ni la classe ni son stride ne sont écrits.
   En revanche `List<T>._items`/`._size` **échappent** à la voie nommée, et c'est mesuré :
   ``classFields("System.Collections.Generic", "List`1")`` rend `boxedSize 0`, `fieldsSize -16` et ses
   **cinq** champs à `offset 0` — la définition générique n'est jamais initialisée, donc n'a pas de
   disposition. Ce sont des constantes de FORME, comme `IL2CPP_BOX_HEADER` et `ARRAY_FIRST` (+0x20),
   et le codebase les portait déjà ainsi. Un contrôle opportuniste les confronte quand même : une
   divergence part en `drift`, pas en erreur.

## 4. Le port (`engine/services/damage_prediction.py`)

`DamagePredictionResult.cannot_be_guaranteed_killed` + gate en tête de `will_be_kill()`. Le défaut
`False` est **exact** (§2), pas une borne inférieure — sur toutes les voies portées le natif laisse 0.

`composite_fields()["killSure"]` porte le **même** gate : c'est lui que lisent les consommateurs de la
face prédiction (`_will_normal_attack_kill`, `_enemy_killed_by_normal_attack`), pas `will_be_kill()`.
Les deux restent **deux lignes distinctes** — le port ajoute à `will_be_kill()` un gate `hp > 0`
PORT-SIDE que le natif n'a pas (`0 <= m` rend `true`), et `decisionView` conserve les unités mortes :
les unifier aurait changé un verdict.

**Résidu nommé** : le CALCUL de `DamagePrediction$$CannotBeGuaranteedKilled` n'est pas porté.
Structure lue — il balaie les abilities TRIGGERED du défenseur et interroge chacune ; le seul override
du binaire est
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HarlequinsPanoplyAbility$$CannotBeGuaranteedKilled`
(qui fourche sur `HarlequinsPanoplyAbility$$SurvivesByDiscardingHits`). Tant qu'il n'est pas porté,
les prédictions d'attaque NORMALE laissent le flag à `False` — borne inférieure assumée. Le capteur
est ce qui permettra de mesurer s'il vaut jamais 1 en bataille.

## 5. Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `frida/tools/probe-279-layout-by-name.ts` étape 3 (15 cas) | le gate est un champ REQUIS (renommé ⇒ `layout=null`) ; la chaîne du scénario aussi ; les offsets résolus (`+0x0c` du décompilé) ; la table de vérité de `computeWillBeKill`, dont **les deux lignes qui opposent `blockKillDmg` à `willKillDmg`** (seules à discriminer le choix de borne) ; le tri-état ; les sentinelles de forme |
| `tests/engine/runner/test_372_cannot_be_guaranteed_killed_offline.py` (7) | le gate mord, et AVANT le choix de borne ; il ne contamine pas `might_be_kill` ; la voie multi-hit ne l'arme jamais (1/2/5 coups + groupes hétérogènes) ; `Add` ne le fusionne dans **aucun** sens ; `killSure` le porte ; le mirror reste NU à `hp == 0` |

Étapes 1+2 de `probe-279` rejouées **contre la session live** : 0 écart figé/live sur 24 chemins,
snapshot embarqué identique au live.

## 6. Ce qui n'est PAS couvert

* ~~Le capteur n'a jamais tourné.~~ **DÉPLOYÉ et mesuré** (session 3, 2026-07-31) :
  `blockScenarioCount = 0`, `cannotBeGuaranteedKilled = 0`, `willBeKill` bascule correctement.
  Le flag est en outre CONFRONTÉ de bout en bout par `probe_361_will_be_kill_gate_direct.py`
  (volet A, `StormOfFlensingBlades` : 2 events quand faux, 0 quand vrai — le décodeur et
  `get_WillBeKill` s'accordent). Suite du résidu #353 : `case-361-explosion-batches-gate.md`.
* **La voie `GetAllPredictions`** (= `aiPredict`, `decisionView.attackPlans`) :
  `DamagePredictionQuery$$GetAllPredictions` construit sa prédiction par un slot d'interface à 3
  arguments `(attacker, position, target)` — la signature de `GetNormalAttackPrediction`, donc la voie
  où le gate est VIVANT. L'interface n'a pas été résolue nominalement : **hypothèse forte, non
  tranchée**. Si elle se confirme, les deux corrections de `rpc-predict.ts` / `projection.ts` ferment
  un bug OBSERVABLE sur `killSure`.
* **Le calcul du flag** (§4) et, côté `#353`, la lecture effective de `BlockScenarios` (`case-353`
  §5ter).
