# #462-r4b-r1-r1-r1-r1-c-r3-r1 — le `Steppable` écrasé perd ses effets, comme dans le natif

Le résidu ouvert par `-c-r3` disait : `_kill_steppable_units` (`operations/movement.py`) pose
`alive = False` + `hp = 0` **et rien d'autre**, alors que le natif y appelle les **trois**
`IdunBattle.Operations.KillUnitOperation$$RemoveEffects`. C'est vrai, c'est re-vérifié, et **le
retrait est porté**.

La tranche se ventile en **deux volets qu'il ne faut pas confondre**, et elle n'en porte qu'un :

| volet | verdict |
|---|---|
| **RETRAIT** des effets (`RemoveEffects` × 3) | **PORTÉ** — mirror, régime vide côté kit, garde de structure |
| **ÉMISSION** des cinq événements de mort | **NON PORTÉ** — blast radius **mesuré à 27 classes**, non confrontable ici (résidu `-r1`) |

## 1. Le crush est une mort ORDINAIRE pour le natif

Les **quatre** `*$$KillSteppableUnits` du binaire construisent INLINE le même
`IdunBattle.Operations.KillUnitOperationOptions$$ForSteppable` — `+0x00 = 2`
(`DamageReason.Steppable`), `+0x44 = 0x0101` donc `+0x44 = +0x45 = 1`, `+0x46 = 0` — puis appellent
le slot `KillUnit` de l'`IOperationProcessor`, c'est-à-dire
`IdunBattle.Operations.KillUnitOperation$$Execute`, **le même corps que pour une mort par dégât** :

* `IdunBattle.Operations.MoveUnitOperation$$KillSteppableUnits` — teste `UnitExtensions$$IsAlive`
  avant de tuer ;
* `IdunBattle.Operations.ReviveUnitOperation$$KillSteppableUnits` et
  `IdunBattle.Operations.ResurrectUnitOperation$$KillSteppableUnits` — **sans** ce test ;
* `IdunBattle.Operations.AddUnitOperation$$KillSteppableUnits` — **le seul différent** : il passe par
  un autre slot avec un `IdunBattle.Core.Services.DamageAppliedResult` portant le même
  `DamageReason` 2, donc par le pipeline de mort COMPLET (enqueue → drain → le même
  `KillUnitOperation$$Execute`). Le retrait a lieu là aussi, par un chemin plus long.

⇒ sur les quatre sites, les trois `RemoveEffects` ont lieu. Le port ne les faisait sur **aucun**.

## 2. Les QUATRE tests sur `options` — et aucun n'est sur le chemin du retrait

Décompilé relu **intégralement** (1088 lignes, build `rnca9r7q6c`). `KillUnitOperation$$Execute` ne
teste `options` qu'à quatre endroits, tous identifiés par l'octet lu :

| offset | ce qu'il gate | valeur sous `ForSteppable` |
|---|---|---|
| `+0x45` | court-circuite le prédicat `UnitExtensions$$IsSteppable(killed)` qui décide du flag `0xd` | `1` |
| `+0x44` | `KillUnitOperation$$RecordDeathReason(killer, killed, uc, deathReason = options+0x00)` | `1` |
| `+0x46` | le flag `UnitFlag.Overkilled` (sous `UnitExtensions$$CanBeOverkilled`) | `0` |
| `+0x44` | une seconde fois, pour une émission **analytics** (`Dictionary` + slot `0x19`) | `1` |

Les trois retraits (`+0x9be` step 0, `+0xd9c` step 1, `+0xf59` step 2) ne sont sous **aucun** d'eux.
Ils sont sous la seule **GARDE REVIVE** (`if (!unitComponent.PendingRevive@+0xa8 .HasValue)`),
qu'un `Steppable` ne peut pas armer côté port — aucun consommateur de `On(PreUnitDeath)` ne peut
poser de revive sur lui, puisque le port n'émet même pas cet événement.

Le seul endroit où `Steppable` change quelque chose dans tout `Execute`, en dehors du gate `+0x45`,
est `ActorStatisticsComponent$$RegisterDefeatedUnit`, sauté quand
`UnitExtensions$$IsSteppable(killed)` — ce qui confirme en creux que **le reste du corps s'exécute**
pour un `Steppable`.

## 3. La CONFIRMATION indépendante : `HaywireMineSteppableAbility`

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HaywireMineSteppableAbility$$CreateTrigger` lit,
nœud par nœud :

```
OnPreDeath(<null>, true)                       # On(1 = PreUnitDeath)
& OwnerIsTarget                                # l'owner (la mine) EST le mourant
& HasDeathReason(<sel +0x30>, 2, <vide>)       # DamageReason.Steppable == 2
& NOT HasTrait(<sel +0x40>, 0x1b = Steppable)
& IsAlive(<sel +0x40>)
& AreEnemies(<sel +0x30>, <sel +0x40>)
```

C'est **une ability du jeu qui n'existe QUE pour ce régime** : la mine Haywire qui explose quand un
ennemi marche dessus. Elle prouve, sans aucune déduction, deux choses que la RE ci-dessus affirme —
`On(PreUnitDeath)` **est** publié pour un `Steppable` écrasé, et le `deathReason` **2** y **est**
enregistré (donc `+0x44` vaut bien 1 sous `ForSteppable`). Symétriquement,
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.CosmicHorror_OnKillAbility$$CreateTrigger` et
`PutridExplosion_Ability` portent un `NOT HasTrait(Steppable)` explicite : ce gate n'aurait aucun
sens si les événements de mort n'étaient pas publiés pour un `Steppable`.

⇒ `HaywireMineSteppable` n'est portée par **aucun** registre du port (résidu `-r3`).

## 4. Ce qui est porté

`movement.py::_kill_steppable_remove_effects(state, dead_id)` — mirror de la sous-séquence, appelée
depuis la boucle de `_kill_steppable_units` (le natif joue `KillUnit` **entièrement** pour chaque
`Steppable` avant de passer au suivant, donc le retrait du crushé N précède le crush du N+1) :

```
+0x9be  RemoveEffects(killed, KillUnitStep.PreUnitRemove = 0)
+0xd9c  RemoveEffects(killed, KillUnitStep.AfterUnitRemove = 1)
+0xf35  GARDE HEAL : if (health.hp > 0) RETURN          <- portée, INERTE ici
+0xf59  RemoveEffects(killed, KillUnitStep.AfterDeathTrigger = 2)
```

Le travail lui-même n'est pas ré-implémenté : l'appel passe par
`damage.py::_kill_unit_remove_effects` (l'adaptateur natif `KillUnitOperation$$RemoveEffects`), donc
par le foyer `operations/remove_effects.py` (#389-r2) que la mort par dégât utilise déjà. Le fix
couvre du même coup les **trois** sites du port (`movement`, `revive.set_revive_position`,
`resurrect`, plus le crush de `spiritual_leader`), qui partagent tous ce helper.

La garde HEAL est portée bien qu'inatteignable (le crush vient de poser `hp = 0` et n'émet, entre
les deux, aucun événement qui pourrait soigner) : l'omettre créerait un écart **silencieux** le jour
où l'émission sera portée.

## 5. Pourquoi ça mordait — le lien avec `-c-r3`

`-c-r3` a **levé les deux gates d'owner de la face EFFET** (mirror de
`IdunBattle.Operations.EvaluateTriggerOperation$$CanGetEffectTrigger`, qui n'en a aucun) : cette
face ne gate plus ni l'existence ni la vivacité du porteur. Un `Steppable` écrasé était alors le
**SEUL** régime du port où un effet-trigger pouvait firer alors que le natif l'avait déjà retiré —
et de façon **persistante**, puisque rien ne retirait jamais ces effets.

Le retrait ferme ce régime **du bon côté** : l'effet n'existe plus, plutôt qu'un gate que le natif
n'a pas. Mesuré (`probe_462_r4b_r1_r1_r1_r1_c_r3_r1_crush_steppable --step retrait`) :

| bras | montage | mesuré |
|---|---|---|
| A | 3 effets sur le decoy, crush | actifs **3 → 0** |
| C | TÉMOIN : effet du registre, **aucun** crush | **1** passage de `matches` |
| B | le même, **après** le crush | **0** passage |

Sous `--mutate sans-retrait` (l'état du port d'avant) : A rend **3 → 3** et B rend **1**. La mesure
discrimine.

## 6. Le RÉGIME du retrait est VIDE côté kit — et le dire fait partie du livrable

Mesure **dérivée du gameconfig** (`--step gisement`), qui **confirme** les chiffres du résidu :

* **27** kits portent `Steppable` (25 npc + 2 summons), dont **20** `Immune` ;
* traits vus sur ces kits : `Decoy`, `Immune`, `Invincible`, `Steppable` — **aucun** n'a d'entrée
  dans `TRAIT_TRIGGERS` ;
* abilities vues : **21**, toutes des `PowerUp_*` plus `HaywireMineSteppable` — **aucune** n'a
  d'entrée dans `ABILITY_TRIGGERS` / `ACTIVE_ABILITY_TRIGGERS` / `RELIC_ABILITY_TRIGGERS` ;
* ⇒ **0** kit `Steppable` inscrit à un registre d'ability-trigger porté.

**Ce que ce croisement ne dit PAS**, et c'est le point : il porte sur le **KIT**. Un effet **posé de
l'extérieur** (DoT de tuile, aura, bond) n'y apparaît pas — et c'est **lui** que les trois
`RemoveEffects` emportent. Aucun poseur naturel ne vise aujourd'hui un `Steppable`, donc la garde de
comportement passe par des **montages synthétiques explicitement étiquetés**, jamais par un porteur
naturel fabriqué.

## 7. Le BLAST RADIUS de l'émission — mesuré, et c'est pourquoi elle n'est PAS portée

`--step blast` dérive des registres les classes qui écoutent les cinq événements de mort : **28**,
dont **27** sur les quatre que le port n'émet pas.

| événement | classes | dont l'owner est le MOVER ou un TIERS (donc atteignable) |
|---|---|---|
| `On(1 = PreUnitDeath)` | 12 | `ActOfFaithAccumulateAbility`, `TheBetrayerAddEffectAbility`, `HazeCorruptionBonusHitAbility`, `EarlyWarningOverrideReactivateOverwatch`, les quatre revives |
| `On(2 = PreUnitDeath_2)` | 5 | `BondRemoveOnBondedEntityDeath` (×3 `effect_type`) ; `ExplodesAbility` / `PutridExplosionAbility` ont pour owner le MOURANT |
| `On(0 = UnitDeath)` | 7 | `TerrifyingCrescendoOverkillAbility`, `HazeOfCorruptionDamageTransferTrigger`, `BarbedOvipositorSummonAbility`, `DawnBladeHealAbility` |
| `On(0x36 = UnitDefeated)` | 3 | `CosmicHorrorOnKillAbility` (gate `NOT Steppable`), `AmbushSummonAbility`, `EmpyricAmbushResetAbility` |
| `On(0x35 = PostUnitKill)` | 1 | **DÉJÀ émis** par le port, chemin MOVE (`post_unit_kill_triggers_for_move`) |

La voie « owner = le MOURANT » est **fermée** (§6 : aucun kit `Steppable` inscrit). La voie
« owner = le MOVER ou un tiers » est, elle, **atteignable dès le premier decoy écrasé** : n'importe
quelle unité du plateau portant `ActOfFaith`, `TheBetrayer`, `HazeOfCorruption` ou
`EarlyWarningOverride` verrait son trigger firer sur un crush.

⇒ **émettre est un changement de comportement réel et non confronté**. Il est ouvert en résidu
(`-r1`) plutôt que livré à l'aveugle.

## 8. Validation

`tests/engine/runner/test_462_r4b_r1_r1_r1_r1_c_r3_r1_crush_steppable_live.py` — **6 verts**
(board `MC1_67`, roster `necroSpyder,orksKillaKan,adeptMorvenn` vs
`genesPatriarch,genesMagus,tyranNeurothrope`, **différents** de ceux de `-c-r1` et de `-c-r3`).
Le montage refuse **bruyamment** (`pytest.fail` / `assert`), jamais par un skip.

Les six bras : la STRUCTURE (les trois retraits, dans l'ordre natif — c'est elle qui tient le port,
le régime étant vide) ; la garde HEAL (montage synthétique **assumé**) ; le crush par le VRAI
pipeline de move vide la liste d'effets ; le régime `-c-r3` est fermé (bras qui MORD + son TÉMOIN,
qui prouve qu'il discrimine) ; les quatre événements de mort restent **non émis** (garde du RÉSIDU) ;
l'ÉNONCÉ du vide (rougira quand un porteur naturel apparaîtra — signal, pas régression).

**Matrice de mutants**, jouée sur l'arbre, arbre restauré après chacune :

| mutant | ce qu'il casse | rouges |
|---|---|---|
| M1 — `_kill_steppable_remove_effects` rend `[]` (état pré-tranche) | le retrait | **4** |
| M2 — garde HEAL supprimée | le mirror de `+0xf35` | **1** |
| M3 — ordre des steps inversé (1 puis 0) | l'ordre natif | **2** |
| M4 — `after_death_triggers` émis au crush | la garde du RÉSIDU | **1** |

M4 est le mutant qui compte le plus : il prouve que le bras
`test_les_quatre_evenements_de_mort_restent_non_emis` **mord** — quiconque portera l'émission le
verra rougir, ce qui est exactement le signal voulu (27 classes à confronter, §7).

**Non-régression : 106 verts sur 16 fichiers** — `decoy_foundation_live` (3),
`decoys_misdirection_migration_live` (3), `cosmic_horror_live` (6),
`389r2_kill_unit_remove_effects_offline` (10), `462_..._c_r3_owner_gates_effet_live` (8),
`462_..._c_r1_tile_owner_gate_live` (7), `spiritual_leader_live` (5), `ambush_migration_live` (5),
`death_queue_ordering_live` (22), `kill_unit_trigger_channels_live` (3),
`hypersensory_moveandspawndecoy_live` (5), `revive_cancels_death_events_live` (3),
`tile_effect_dynamics_live` (5), `462_..._bond_removal_live` (4),
`589r1r1r1r1_empyric_ambush_reset_live` (5), `kill_unit_trigger_channels` (12).

## 9. Résidus ouverts

* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r1`** — **l'ÉMISSION des cinq événements de mort du crush**.
  Le natif publie `On(1)`, `On(2)`, `On(0)`, `On(0x36)`, `On(0x35)` pour un `Steppable` écrasé ; le
  port n'émet que le dernier, et seulement sur le chemin MOVE. Blast radius **mesuré : 27 classes**
  (§7), dont plusieurs portées par le MOVER, donc atteignables immédiatement. Le porter exige de
  confronter chacune — hors du périmètre de cette tranche. Gardé en l'état par
  `test_les_quatre_evenements_de_mort_restent_non_emis`.
* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r2`** — **`RecordDeathReason(..., DamageReason.Steppable = 2)`
  n'est pas porté pour le crush**. `+0x44` vaut 1 sous `ForSteppable`, donc le natif écrit bien
  `UnitComponent+0x108` avec le tueur et la raison **2** ; `damage.py::_record_death_reason` n'est
  appelé que depuis `_fire_death_if_killed`, jamais depuis le crush. Aucun consommateur porté ne lit
  `death_source` avec `reason == 2` (le seul lecteur natif connu est `HaywireMineSteppableAbility`,
  résidu `-r3`), donc le régime est vide — mais il le cessera dès que `-r1` ou `-r3` sera porté, et
  `-r1` sans `-r2` publierait `On(1)` avec un `death_source` **manquant**.
* **`#462-r4b-r1-r1-r1-r1-c-r3-r1-r3`** — **`HaywireMineSteppable` n'est portée par aucun registre**.
  Son `CreateTrigger` est lu (§3) et son porteur `astarSmnHaywireMine` est un **SUMMON**, donc
  confrontable en spawnant son summoner (gate SUMMON du CLAUDE.md) — le second porteur,
  `astarNpc1HaywireMine`, est npc. Elle dépend de `-r1` (elle écoute `On(1)`) **et** de `-r2` (elle
  teste `HasDeathReason(..., 2)`) : les trois résidus forment une seule tranche naturelle, et c'est
  elle qui rendrait l'émission confrontable sur un porteur **réel**.

## 10. Non couvert, et nommé

* **Aucun porteur NATUREL n'exerce le retrait.** Les effets des bras live sont **posés à la main** ;
  seul le crush est réel. C'est la limite honnête du régime vide (§6), pas un raccourci de montage.
* **Le second prédicat de `RemoveEffectsOptions` (`+0x08`)** reste non porté — résidu antérieur de
  #389-r2, inchangé ici (les call-sites de mort le passent tous à 0).
* **`KillUnitStep` par défaut** : l'hypothèse nommée de #389-r2 (le step par défaut d'un effet est
  `PreUnitRemove`) est **héritée**, pas re-mesurée. Conséquence nulle à la sortie du crush — les
  trois steps tournent, donc tous les effets partent quel que soit leur step — mais elle mordrait
  sur un consommateur intercalé, c'est-à-dire précisément le jour où `-r1` sera porté.
* **Le flag `0xd`** que `+0x45` fait poser sur le mort (`UnitFlagsComponent.Add(killed, 0xd)`) n'est
  pas porté, non plus que `Remove(0xf)` / `Add(6)`. Écart préexistant, hors périmètre : le port
  collapse l'état « mort » dans `UnitComponent.alive`.
