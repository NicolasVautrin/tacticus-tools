# #977-r5 / #931-r2 / #977-r1 / #977-r4 — quatre résidus, trois substrats et un énoncé faux

Tranche de l'agent F. Les quatre portent sur **ce que la face DÉCISION LIT, et d'où elle le lit**.

---

## 1. #977-r5 — le DOMAINE de cible était dérivé de la ROUTE de décision

### La cause, et pourquoi elle est structurelle

`engine/ai/state_bridge.py::_ability_kind` — le prédicat qui dit *quelles cibles énumérer* —
appelait `_is_attack_ability`, dont la dernière clause est `return not is_noncomp(int(ability_id))`.

Or `is_noncomp` répond à une question de **ROUTE** : « quel générateur d'action sert cette
ability ? ». Le natif ne confond pas les deux axes :

| axe | corps natif | ce qu'il décide |
|---|---|---|
| ROUTE | `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists` | range chaque ability par `get_IsComparable` de SON playbook |
| DOMAINE | `IdunBattle.Core.Services.TargetingQuery$$GetPossibleTargetsForOptions` | quelles entités entrent dans l'énumération |

Aucun des deux corps ne lit l'autre.

### Ce que le décompilé établit (LU sur `rnca9r7q6c`)

`GetPossibleTargetsForOptions` **n'applique AUCUN filtre de camp**. Sa séquence :

1. `GetUnitsInRange` — ou `GetTilesInRange` si le bit `TargetIsTile` est posé, ou si l'appelant
   force `onlyTiles` ;
2. l'ajout du caster sous `CasterIsPossibleTarget` (bit 15) ou le bit 57 ;
3. **trois `RemoveWhere`** :
   * `<GetPossibleTargetsForOptions>b__0` — retire les entités mortes (`!IsAlive`) et
     `HasSteppableUnit` ;
   * `<GetPossibleTargetsForOptions>b__1` — `IsFriend(target, caster) -> return false`, donc **un
     ami n'est JAMAIS retiré par ce prédicat** ; il ne retire que les NON-amis qu'un terrain
     obscurcit (`GetTilesObscuringTerrain`) ;
   * `<GetPossibleTargetsForOptions>b__2`, sous le bit 1 — la règle dynamique de l'ability ;
4. intersection avec `GetOnlyTargets(caster)` sous les bits 14 / 57.

Le camp n'est tranché qu'**ensuite**, par `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`
— exactement les deux règles que `refuses_all_enemy_targets` reconnaît (`TargetIsFriendly`,
`TargetIsCaster`).

⇒ **un masque LU sans règle de camp laisse survivre les DEUX camps.**

### La mesure

`probe_977r5_domaine_vs_route.py`, 100 % offline :

| | avant | après |
|---|---|---|
| playbooks NonComparable | 87 | 87 |
| dont `constants.damageProfile` | 42 | 42 |
| … sans veto de camp, rabattues sur `self` | **29** | **0** |
| `ability_targets_offline(caster, 1122 CordClaw)` | `[caster]` | `[caster, ennemi]` |
| `CordClawPlaybook._eligible_ids` | `{caster}` | `{caster, ennemi}` |

L'effet n'était pas « l'ability disparaît des `attackPlans` » (l'énoncé du résidu) mais **plus
grave** : `_eligible_ids` filtre ses cibles par cet ensemble (`tid not in eligible -> continue`),
donc **tous** les ennemis étaient écartés et l'ability ne produisait **aucune action offline**.
Dégradation RESTRICTIVE et silencieuse. **11 des 29** playbooks lisent `ctx.ability_targets` sur
leur propre `ABILITY_ID`.

### La réparation

Nouveau domaine `any` (les DEUX camps), branche insérée **avant** le `self` résiduel :

* `_enumerates_enemy_units` — le DOMAINE (veto de camp + `damageProfile`), sans la clause de route ;
* `_is_attack_ability` — la ROUTE, = le domaine ET `not is_noncomp`. **Inchangée** ;
* `_enumerates_both_camps` — le domaine ET un masque LU sans `TargetIsTile`.

L'ensemble émis est **strictement élargi** : non-régressif par construction pour tout lecteur qui
ne cherchait que le caster (`1192 NovaBoost`, qui teste seulement la non-vacuité).

### Ce qui reste ouvert — #977-r7

Les **10** NonComparable qui portent `TargetIsTile` restent en `self`. Sous ce bit le natif rend des
**TUILES** (`GetTilesInRange`), et l'énumérateur de tuiles offline est le patron **SUMMON** (ring-1
des tuiles-caster), pas le patron **AIM à portée** dont `1092 DarkTalonStrike`,
`1116 RadBombardment`, `1142 MalleusRocketLauncher`, `1152 UnstoppableMomentum`,
`1188 DevastatingRefrain`, `1194 NovaShield`, `1201 SquigMine`, `1209 InfernalCannon`,
`1213 DeathOnTheWind`, `1087 ExemplarOfTheKauyon` ont besoin. Les basculer sans porter ce second
patron remplacerait une erreur par une autre.

---

## 2. #931-r2 — les abilities ACCORDÉES venaient du KIT, pas de l'ENTITÉ

`_granted_abilities(vid)` bouclait sur `GC.unit(vid)["passiveAbilities"]`. Le natif monte l'ability
accordée depuis `UnitConfiguration.PassiveAbilities` (= `BC.Units[].PassiveAbilities`), un fait
d'**ENTITÉ** — `...TwistedScienceAbility$$CreateBehaviour`, `On(AbilityInit) & OwnerIsActor`.

Parade **transposée** de `services/custom_normal_attack.py` (#419-r1-tr14-r5), tri-état :

* un **tuple** (fût-il vide) = la MESURE (`UnitContext.passive_abilities`, hiérarchie 2, posée par
  `runner.snapshot._load_passive_abilities`) — elle prime ;
* `None` = canal MUET → repli KIT, **exactement** le comportement d'avant.

Propagé : `_granted_abilities` → `_abilities_of` → `_attack_abilities` → `_plans_for_unit`, et
`build_from_state` lit la mesure par `measured_passive_abilities(ctx)`.

Mesure des **deux** sens (`probe_931r2_substrat_passifs.py`) :

| bras | kit | entité mesurée | `1167 Heal_TwistedScience` |
|---|---|---|---|
| GREFFE — `admecRuststalker` + `TwistedScience` | `()` | `("TwistedScience",)` | **RETROUVÉE** |
| RETRAIT — `genesBiophagus`, aucun passif monté | `(1167,)` | `()` | **ÉCARTÉE** |

Population : **4** unités du catalogue (683 kits) reçoivent une active par cette voie, toutes
`TwistedScience` → `1167` (`ActiveAbilityType` ne porte qu'**un** membre `Heal_*` sur ce build).
La divergence n'est donc pas hypothétique mais elle est **étroite aujourd'hui** ; ce qui la rend
importante, c'est que tout bras `catalog_inject.write_grafted_seed_bc(..., replace=True)` la
déclenche, et qu'un membre `Heal_*` de plus l'élargirait sans que rien ne le signale.

---

## 3. #977-r1 — le slot `IBattleQuery` `0x0b` est RÉSOLU

`interfaceSlotProbe` sur `IdunBattle.Core.Services.IBattleQuery` (219 méthodes) :

```
slot 0x0a  GetCurrentAndMovableTilesOf          params=3
slot 0x0b  GetMovableTilesFor                   params=3      <- celui-ci
slot 0x0c  GetMovableTilesFor                   params=4
slot 0x0d  GetMovablePositionsFor               params=3
slot 0x0e  GetCurrentAndMovablePositionsFor     params=3
slot 0x40  HasValidTargets                      params=3
slot 0x42  GetValidTargets                      params=3
```

Table **CALÉE** par quatre ancres concordantes avec ce que le port affirme déjà par ailleurs
(`0x0e`, `0x40`, `0x42`). Le corps de
`IdunBattle.AI.Playbook.Loki.ThunderousAssaultPlaybook$$GetHighestTileUtilityUnitCanMoveTo` le
confirme : il invoque ce slot avec `(unit, ignoreFlags: 0, options: default)` — 48 octets à zéro —
et évalue `UtilityAttackCase.Base(unit, t, t, aoe)` sur chaque élément **sans `.MainTile`** (les
éléments SONT déjà des tuiles, d'où le nom `...TilesFor`).

⇒ c'est le **movable SEUL**. `ctx.reach_nc` (slot `0x0e`) y ajoute la position courante — ce seed
est précisément ce qui distingue les deux slots. Le port l'incluait : `highest` trop grand, gate
`r.Value >= highest` trop sévère, actions REFUSÉES que le natif émet.

**Direction confirmée** : RESTRICTIVE, comme le résidu l'avait nommée.

**Borne qui reste** : `GetMovableTilesFor` rend des TUILES, `GetMovablePositionsFor` des
`UnitPosition` (footprint). Le port ne modélise qu'une tuile par unité — exact pour toute unité
mono-tuile.

---

## 4. #977-r4 — l'ÉNONCÉ est FAUX, et c'est le verdict

Le résidu cherchait « le régime où le défaut `MIN_UTILITY = 0.0` mord ». **Il n'existe pas** :

* le gate du port est `if util < self.MIN_UTILITY: return None` — **STRICT**. À `util == 0`, `0.0`
  et `-inf` **admettent tous deux**. Le natif est identique (`Bucket$$AddAction` admet `util >= min`) ;
* `util < 0` est **INATTEIGNABLE** : la stratégie 1 gate chaque cible à `diff > 0`, et la
  stratégie 2 n'émet que si `r.Value >= highest`, où `highest` part du plancher `Fix64(0)` et ne
  fait que croître.

La prose du module et du registre — « le défaut `0.0` aurait TUÉ ce playbook en silence » — était
donc **fausse quand elle a été écrite**. Elle est corrigée. `MIN_UTILITY` reste `-inf` **par
fidélité** au `Bucket<T>..ctor` à UN argument (`minUtility.HasValue == false`), pas parce qu'un
montage l'exigerait.

---

## 5. Un ROUGE de `master` trouvé en chemin — attribué, puis CORRIGÉ

`test_977_faces_decision_kit_live.py::test_utilite_par_position_exacte[1043]` échouait :

| arbre | verdict |
|---|---|
| ma base (`be03c4e1` + probe), fix ABSENT | `ok=True capteurAveugle=False nComparees=23` — **FAIL** |
| mon arbre, fix #977-r1 PRÉSENT | `ok=True capteurAveugle=False nComparees=23` — **FAIL identique** |

**Attribution faite avant d'accuser** : le rouge est étranger à cette tranche, et le fix #977-r1
**ne change rien** à l'accord (23/23 positions concordent des deux côtés — le montage est plat,
donc l'origine n'y porte pas une utilité de tuile strictement supérieure : régime NON
DISCRIMINANT, d'où la garde offline à carte d'utilité choisie).

**Cause** : le test gardait le verdict de #977 (« le capteur `ncEvaluate` est structurellement
aveugle à `GenerateBucketWithMultipleStrategies` : l'action va dans un SOUS-bucket de la
`SortedList` à `+0x28`, jamais dans le `best` de la racine »). **#988 (`16f995ce`) a fermé cette
cécité** — `frida/hooks/features/ai-step/rpc-nc-predict.ts` décode l'arbre entier et mirrore
`Bucket<T>$$ChooseAction` (`bucketVia = "subBuckets"`). Le test n'a pas été mis à jour.

Il est désormais **RENFORCÉ** (il exige l'ACCORD pour les trois abilities) et non assoupli ; la
branche `capteurAveugle` reste lue et fait échouer explicitement si le capteur redevenait muet.

---

## 6. #966-r3 — l'EXÉCUTION du cast de `1212`, CONFRONTÉE

### Le blocage était une FORME D'ACTION, et il se LIT

`#966` avait envoyé `{"kind":"ability","unitId","abilityId","targetId"}` → `ok = None`, aucune
mutation. La forme acceptée est celle que `rl_duel.py cmd_act` **construit** :

```
{"kind": "ability", "casterId": <uid>, "targetId": <tid>, "abilityType": <aid>}
```

`casterId` (pas `unitId`), `abilityType` (pas `abilityId`). Aucune des deux clés ne se devine — le
résidu disait déjà « lire `rl_duel.py act` plutôt que deviner », et c'était la bonne consigne.

### Ce que le cast FAIT (mesure, `probe_966r3_execution_du_cast.py`, runner `build#236`, MC1_67/31337)

`applyAction` rend `ok: true`, **22 events**. Les trois effets sont posés **sur la CIBLE** (u83),
pas sur le caster (u81) :

| effet natif | id d'entité | `Effect_SourceTriggeredAbility` | `RemainingTurns` | modification |
|---|---|---|---|---|
| `HealingBalms_ExtraCritDamage` | 108 | **1502** | 4 | `CritDamage_Modification: 797` |
| `HealingBalms_ExtraCritChance` | 109 | **1502** | 4 | `CritChance_Modification: 20` |
| `HealingBalms` | 110 | **1502** | *(aucun)* | — (marqueur) |

Recoupé **indépendamment** par `statModSources(u83)` : `critDamage.total = 797` source `108`,
`critChance.total = 20` source `109`. Deux canaux, même mesure.

⚠ **La source est `1502`**, pas les `1503`/`1504`/`1508` que l'énoncé du résidu citait comme
« les trois effets posés ». Ces trois-là sont les `EffectType` ; `1502` est le
`TriggeredAbilityType` qui les pose. Ne pas les confondre (le CLAUDE.md : « qualifier les enums »).

⚠ **`decisionView.effects` est AVEUGLE à ces trois instances** — il rend `{}` sur la cible pendant
que les events ET `statModSources` les voient. C'est précisément ce qui avait fait conclure « rien
n'a été exécuté ». Un canal muet n'est pas une absence.

### Le RÉ-ARMEMENT est mesuré — et il est PARTIEL

Au re-cast (32 events) :

* `108` et `109` sont **RETIRÉS** (steps 16 puis 18, `..._Modification_Change: -2147483648`,
  `Modification: 0`) puis **RE-POSÉS** sous de nouveaux ids `111` / `112`, mêmes valeurs
  (797 / 20). ⇒ le `RemoveEffect` en tête d'arbre fait bien son travail : **pas d'empilement** ;
* **`110` (`HealingBalms`) n'est PAS retiré** : `113` est posé **en plus**. Le marqueur du soin
  différé **EMPILE**. Résidu ouvert **#966-r6**.

### Le soin

Le soin part **au CAST**, pas plus tard : le même `applyAction` porte
`step 5 {UnitStats_RemainingHealth, UnitStats_WasWoundedBeforeHeal, Amount, Caster_Id}`.

Mais **la MAGNITUDE reste NON CONFRONTÉE** : `--hp-player 200` force `Health` **et**
`RemainingHealth`, donc la cible est à PV pleins et `Amount: 0` — régime DÉGÉNÉRÉ. Un
`--unit-stat "<vis>:RemainingHealth=40"` ajouté après n'a **pas mordu** (`RemainingHealth: 200`
mesuré). Et les deux `endturn` ont rendu **0 event** : le `TurnStart_Other` n'a pas été atteint,
donc ni le soin différé ni sa CONSOMMATION ne sont confrontés. Résidu **#966-r6**.

---

## 7. Ce qui n'est PAS couvert

* **#942-r2** (magnitude de `1210 ExemplarOfTheMontka` confrontée au dégât NATIF) : **non traité**,
  faute de budget. Rien n'a été mesuré dessus, son énoncé n'a pas été re-vérifié.
* La **magnitude** du soin de `1212` et son volet **différé** (cf. §6).
* Les **10** abilities `TargetIsTile` (#977-r7).
* Deux rouges offline **préexistants** de `master`, mesurés sur ma base avant tout fix et donc
  étrangers à cette tranche :
  `test_448_r2b_stormboyz_teleporting_in_offline.py::test_the_just_summoned_family_stays_out_because_nothing_POSES_it`
  et
  `test_498r4_face_decision_is_displaceable_offline.py::test_le_recenseur_ne_credite_pas_une_condition_seulement_CITEE`
  (`playbook/loki_custom.py::_is_displaceable` rendu `NON-PORTE` au lieu de `MIROIR`).

## 8. Résidus ouverts

* **#977-r7** — le domaine TUILE d'`ability_targets_offline` est le patron SUMMON ring-1 ; les 10
  NonComparable à `TargetIsTile` ont besoin du patron AIM à portée.
* **#966-r6** — magnitude du soin de `1212` en régime BLESSÉ, soin différé + consommation, et
  l'EMPILEMENT mesuré du marqueur `HealingBalms`.
