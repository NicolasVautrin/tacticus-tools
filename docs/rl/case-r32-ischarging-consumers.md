# case-r32 — retrofit des consommateurs de `IsCharging` : le proxy `has_moved` sur-accordait

> **Build** `gqfc5mff6c`. Suite directe de `case-231` (qui a porté le socle `IsCharging`). Ici on ne
> porte pas une primitive : on **rabat sur elle** les effets qui la modélisaient par approximation.
> Décompilé = vérité ; live = confirmation (3 régimes COMBAT + 4 régimes PRÉDICTION, tous bit-exacts).

---

## 1. La question, et sa réponse

> Les effets d'`extra_damage.py` qui modélisent le gate natif `IsCharging` par le proxy
> `has_moved is False -> pas d'application` produisent-ils un verdict DIFFÉRENT du gate natif sur au
> moins une configuration atteignable en bataille ?

**OUI**, et la divergence est atteignable trivialement : **un acteur qui BOUGE vers une cible DÉJÀ
adjacente avant son pas**. Le flag `UnitFlag.Moved` est VRAI, `IsCharging` est FAUX.

Ça se lit au décompilé, pas à l'expérience. `IdunBattle.Core.Services.BattleQuery$$IsCharging` :

```
byte IsCharging(this, caster, target)
    bVar1 = AreEntitiesAdjacent(caster, target, 0)
    lVar3 = GetComponent<UnitComponent>(caster) -> +0x190          # ChargedUnitIds (List<int>)
    bVar2 = List<int>.Contains(lVar3, target.Id)
    return bVar2 & bVar1
```

et le SEUL alimentateur, `IdunBattle.Operations.MoveUnitOperation$$UpdateCharging`, n'ajoute que les
unités **NOUVELLEMENT** adjacentes (`after \ before`). Une cible déjà adjacente avant le pas n'y entre
jamais. Le proxy est donc **strictement plus large** — biais **UNILATÉRAL**, le port sur-accorde.

Trois familles de configurations où le proxy diverge, toutes atteignables :

| # | Configuration | `has_moved` | `IsCharging` natif |
|---|---|---|---|
| 1 | bouge vers une cible **déjà adjacente** avant le pas | VRAI | **FAUX** |
| 2 | bouge **sans arriver au contact** de la cible | VRAI | **FAUX** (terme `AreEntitiesAdjacent`) |
| 3 | a bougé au tour N, agit **hors de son activation** (overwatch, riposte) après le `FinishUnitTurn` qui a vidé la liste | VRAI | **FAUX** |

L'inverse (`has_moved` faux et `IsCharging` vrai) n'existe pas : la liste ne se remplit que dans un
`MoveUnitOperation`, qui pose le flag dans le même `Execute`.

---

## 2. Qui porte réellement ce nœud — la fiche d'inventaire se trompait

Xrefs de `IdunBattleLogic.Entities.DSLFactory$$IsCharging`, **16 appelants**, ventilés par canal :

| Canal | Appelants |
|---|---|
| **`CreateEffectDamageBonusForAttack`** (le périmètre) | `AvalancheOfMuscleTargetEffect` (1025), `FeederTendrils_ExtraDamageEffect` (1197), `BlackRage_ExtraDamageEffect` (1343) |
| `CreateEffectHitsBonusForAttack` | `RedThirst_ExtraDamageAndHitEffect`, `SagaOfTheWarriorBorn_OwnerEffect`, `UnstoppableFerocityOwnerEffect`, `ObeisanceGenerators_HitReductionEffect` |
| `CreateCritDamageBonus` | `SagaOfTheWarriorBorn_OwnerEffect` |
| `CreateAdditionalHits` | `FragLanceEffect` |
| `CreateActiveCondition` | `BloodChalice_ExtraPiercingEffect` |
| triggers / abilities | `AggressiveOnslaught_Prepare/SummonAbility`, `SabreOfSacrificeAbility`, `FeederTendrils_NormalAttackAbility`, `TacticalPrecisionAbility` (×2, déjà porté case-231) |

⚠ **`SmashaEad` N'EN FAIT PAS PARTIE.** `IdunBattle.Entities.Effects.Loki.SmashaEadEffect$$CreateEffectDamageBonusForAttack`
vaut `ForAddition(get_OwnerIsCaster & IsNormalAttack, ConfigVar(8))` — deux nœuds, pas trois. Sa
condition « a traversé ≥ 2 hexes » vit dans son TRIGGER et est déjà bakée à la matérialisation de
l'effet. Le port ne lui avait d'ailleurs **jamais** posé de gate `has_moved` : la fiche `N9` et le §1
de `case-231` le nommaient à tort. Corrigé aux deux endroits.

Le lot réellement concerné par le proxy était donc de **deux** classes, pas trois.

---

## 3. Le fix — un foyer, deux faces

`engine/battle_query.py::is_charging(caster_pos, target_pos, target_id, charged_unit_ids, elev_by_pos)`
= mirror littéral des deux termes. **Aucun fork** : les deux faces l'appellent, avec la même
sémantique et des entrées différentes.

| face | `charged_unit_ids` passé | fourni par |
|---|---|---|
| COMBAT | la liste RÉELLE du `UnitComponent` | `runner/damage_model.py::battle_query_is_charging` (lit `components.charged_unit_ids`) |
| PRÉDICTION | charges DÉJÀ acquises **∪** ce que le pas CANDIDAT ajouterait | `playbook/prediction/_shared.py::_prediction_is_charging` (`scene.charged()` ∪ `battle_query.newly_adjacent_ids`) |

Le verdict est threadé per-coup dans `att_ctx["is_charging"]` et consommé par un gate PARTAGÉ,
`engine/entities/effects/base.py::is_not_charging(att_ctx)` — à côté de `is_melee_attack` /
`is_ranged_attack`, même discipline de tri-état : clé absente ⇒ le gate ne mord pas (contextes
d'attaque sans cible, ex. les prédictions internes de `FinalJustice`), seul un `False` explicite ferme.

`has_moved` **reste threadé, inchangé** : il porte l'AUTRE prédicat natif, `HasFlag(UnitFlag.Moved)`
(`HeavyWeapon_ExtraDmg`, `CrushingStrike`). Les deux existent nativement ; les confondre était
précisément le défaut.

`Scene` gagne `charged_by_id`, peuplé par `Scene.from_state` depuis l'ECS.

---

## 4. Ce que le natif fait en PRÉDICTION — mesuré, pas déduit

Le décompilé **ne tranche pas** : `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery$$IsCharging`
enveloppe l'appel dans `RunWithoutSimulation<T>`, ce qui suggère une lecture hors-simulation, mais
rien ne dit que la chaîne display passe par cette query. `probe_r32_ischarging_prediction.py` mesure
les deux termes séparément (`aiPlaybookPredict(col,row)` = l'oracle de DÉCISION, pas le preview
`aiPredict`) — `astraBullgryn` L50 mult 180 %, `extraDmg = 599/coup`, 4 coups :

| cas | montage | natif | offline | `off+chg` | `off−chg` |
|---|---|---|---|---|---|
| **A** CHARGE_CANDIDAT | caster à distance 2, tour NEUF (liste vide), tuile candidate adjacente | **12032** | 12032 | 12032 | 9636 |
| **B** CHARGE_ACQUISE | le pas est JOUÉ ; prédiction depuis la tuile courante (aucun pas de plus) | **12032** | 12032 | 12032 | 9636 |
| **C1** NO_CHARGE | adjacent, tour NEUF, tuile courante | **9636** | 9636 | 12032 | 9636 |
| **C2** ADJ_NOCHG | adjacent, tour NEUF, décalage vers une AUTRE tuile adjacente | **9636** | 9636 | 12032 | 9636 |

Les colonnes `off+chg` / `off−chg` (gate forcé) diffèrent partout : chaque MATCH est **probant**, aucun
n'est le MATCH trivial « aucun bonus des deux côtés ».

**Les deux termes sont nécessaires** : A tombe sans le terme CANDIDAT (la prédiction native SIMULE
donc le pas), B tombe sans le terme RÉEL (elle lit donc AUSSI la liste acquise). **C2 est le cas
discriminant en prédiction** — le natif rend 9636, le proxy `has_moved` aurait rendu 12032 (la tuile
candidate diffère de la position courante). L'écart du proxy est le même des deux côtés : +599/coup.

---

## 5. Validation live COMBAT — la garde vue ROUGE avant le fix

Fixture nommée `tests/engine/runner/_charge_regime.py` (pendant d'`_ability_cast_replay.py`) : elle
monte les trois régimes, joue le pas et l'attaque normale en LIVE, et rejoue OFFLINE depuis le
snapshot PRÉ-pas en **rejouant le pas** (`MoveUnitMessage`) — jamais en déclarant la liste à la main,
ce qui court-circuiterait le morceau de port confronté.

Message d'échec **avant** le fix, verbatim :

```
AssertionError: STEP_ADJACENT : le port sur-applique le +extraDmg de charge --
live=[3336, 3158, 2479, 2533] offline=[3935, 3757, 3078, 3132] (delta/coup=[599, 599, 599, 599])
```

| régime | avant le fix | après |
|---|---|---|
| `STEP_ADJACENT` (bouge, cible déjà adjacente) | **ROUGE**, +599 × 4 de trop | bit-exact |
| `CHARGE` (arrive au contact) | déjà bit-exact | bit-exact |
| `NO_STEP` (aucun pas) | déjà bit-exact | bit-exact |

Que les deux autres régimes passent **déjà** avant le fix est le point qui rend la mesure
concluante : la magnitude, le canal, le niveau et le multiplicateur étaient justes — **seul le gate
divergeait**. La divergence est donc localisée par étage, pas ajustée par un scalaire.

### Généralisation, et épreuve par mutation

Le cas discriminant est rejoué sur un **autre board, un autre seed et d'autres cibles** — `C1_25`,
seed 31337, `orksNob` + `tyranTyrantGuard` — et y est bit-exact lui aussi. La magnitude de l'écart y
diffère (**+401/coup**, contre +599 sur `MC1_67`) : le `+599` est PRÉ-perçage, ce qui reste après
armure dépend de la cible. Un port qui aurait « fitté 599 » ne passerait pas ce second montage.

Épreuve adversariale du fix par mutation : en remettant `att_ctx["is_charging"] = has_moved` (le
proxy), **les deux** tests `STEP_ADJACENT` tombent — `MC1_67` `[3935,…]` vs `[3336,…]`, `C1_25`
`[2642, 2046, 2770, 2669]` vs `[2241, 1645, 2369, 2268]` — tandis que les régimes `CHARGE` et
`NO_STEP` restent verts. La garde discrimine donc bien le gate, et rien d'autre.

### Ce que la fiche `R32` disait, et pourquoi c'était faux

`R32` annonçait « offline **+0** » et « le gate n'est porté sur AUCUN des trois ». Les deux sont des
artefacts, pas des mesures du port :

* `probe_avalanche_charge_gate.py` reconstruit l'état par `load_state`, **qui ne seede pas le
  `UnitFlagsComponent`** — donc `unit_has_moved` rendait FAUX offline, donc le proxy fermait le gate,
  d'où le « +0 ». Dès que le pas est rejoué offline, le régime CHARGE est bit-exact **avant même** ce
  fix (mesuré ci-dessus).
* le gate ÉTAIT porté sur 1025 et 1197 (par le proxy) ; il ne l'était pas sur 1343, qui est un cas
  séparé (§6).

L'écart réel n'est donc ni « +45 % » ni « +0 » : c'est **+599/coup accordé à tort** dans le seul
régime « bouge vers une cible déjà adjacente », soit **+24,9 %** du coup sans bonus (9636 → 12032 en
prédiction) et **+18 %** du coup natif en combat.

---

## 6. `BlackRage_ExtraDamage` (1343) — RE faite, port BLOQUÉ, bloqueur chiffré

Le troisième consommateur n'est **pas** porté, et la raison a changé de nature :

* « magnitude négligeable, `extraDmg[L] = [10, 12, 14, …]` » (fiche antérieure) est **FAUX** —
  c'était la tête du tableau. `extraDmg[1] = 10`, **`[50] = 554`**, **`[65] = 728`**, soit ~997/coup
  à multiplicateur 180 %, ~4 000 sur l'attaque 4 coups de Lucien.
* « le gate n'est pas exprimable dans le canal modifier EAGER » est **levé** par ce travail.
* Le bloqueur RÉEL, mesuré en tentant le port : l'`AddEffect(1343, caster)` du `black_rage_tree`
  **ne propage pas le niveau d'ability de la source**. L'effet arrive au niveau ~1 ⇒ contribution
  **18/coup au lieu de 997**. A/B live sur le delta de PV de la cible :
  `off(+charge) − off(−charge) = 52` sur 4 coups, là où le port juste vaudrait ~3 900.
  **Livrer le canal dans cet état produirait une valeur FAUSSE, pas une valeur manquante.**

Débloqueur : le `scale_from_source` du vecteur de pose
(`runner/abilities/behaviours/effects.py::_source_scaling`, déjà utilisé par `Waaagh_ExtraDamage`
1100) — **pas** le fichier d'effet. Entrée d'inventaire `N10`.

Verrou posé : `test_ischarging_extra_damage_live.py::test_black_rage_effect_level_not_propagated`
constate le bloqueur et **tombe le jour où il est levé**, avec le message qui dit quoi faire.

Écart tiers croisé sur le même vecteur, sans rapport avec le canal dégât : le
`SetHealth(30 % de MaxHealth)` du cast rend **56 871 live vs 60 000 offline** (⇒ `hp_max` 189 570 vs
200 000 sur un état rechargé par `load_state`). Il rend ce vecteur non bit-exact tant qu'il tient.

---

## 7. Ce qui n'est PAS couvert

* **Les autres canaux de `IsCharging`** (§2) : `CreateEffectHitsBonusForAttack` (RedThirst,
  SagaOfTheWarriorBorn, UnstoppableFerocity, ObeisanceGenerators), `CreateCritDamageBonus`
  (SagaOfTheWarriorBorn), `CreateAdditionalHits` (FragLance), `CreateActiveCondition`
  (BloodChalice_ExtraPiercing), et les triggers `AggressiveOnslaught_*` / `SabreOfSacrifice`.
  Aucun ne portait de proxy `has_moved` — ils ne sont pas portés du tout. Le gate leur est désormais
  disponible ; chacun reste une tranche de port à part entière.
* **`FeederTendrils` (1197) n'a pas été rejoué live depuis le retrofit.** Il partage le foyer de gate,
  le canal et la forme de magnitude d'`AvalancheOfMuscle`, validé ici sur 7 régimes ; mais son propre
  porteur (Deathleaper) n'a pas été confronté dans cette passe.
* **Le terme RÉEL en prédiction sur un état RECHARGÉ** : `scene.charged_by_id` n'est peuplé que par
  `Scene.from_state`. Aucun RPC n'expose `UnitComponent+0x190`, donc une prédiction faite sur un état
  rechargé par `load_state` ignore les charges déjà acquises et OMET le bonus. Dégradation
  **restrictive** (à l'inverse du proxy, qui sur-accordait). Point d'ancrage à hooker pour la fermer :
  `UnitComponent+0x190` côté `combatSnapshot`.
* **La porte d'élévation** de `AreEntitiesAdjacent` : le natif vaut
  `abs(elev(b) − elev(a)) < 2 && (a == b || ConnectivityComponent(a).IsNeighbour(b))`
  (`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`). Le foyer l'applique quand `elev_by_pos`
  est fourni ; la face COMBAT ne le fournit PAS, pour rester au niveau d'approximation du socle
  (`components.update_charging` et le nœud DSL `entities.triggers.IsCharging` comparent en hex pur).
  Aucun régime mesuré ne l'exerce.
