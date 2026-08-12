# #963 — `RedRampage` + `GeminaeSuperia` : deux passifs de kit, et un ÉMETTEUR qui n'existait pas

Build `rnca9r7q6c`. Décompilé = vérité, live = confirmation.

## 1. Le NON du critère d'émetteur — `On(PreDamageTaken)` n'avait aucun producteur

Recensement **exécutable** au moment de l'ouverture (tout `TriggerEvent(EventTriggerType.X, …)`
construit dans `engine/**`, AST) : **40 types d'événement émis, `PreDamageTaken` absent des 40.**

`GeminaeSuperiaAbility$$CreateTrigger` écoute `On(0x39 = PreDamageTaken)`. L'inscrire au registre
sans rien d'autre l'aurait fait entrer ***registered-but-dead*** — aucun test d'appartenance au
registre ne l'aurait vu, et le passif n'aurait jamais fait apparaître une seule Geminae.

Le vecteur a donc été **créé** : `pre_damage_taken_triggers`
(`engine/runner/operations/triggers/dispatch/attack.py`), place d'émission **lue aux octets** dans
`IdunBattle.Operations.ApplyDamageOperation$$Execute` — les trois publications de cette opération
ont été relues :

| event | gate natif | place |
|---|---|---|
| `On(0x39 = PreDamageTaken)` | `0 < DamageAppliedResult$$get_Damage(result)` | après le gate `Overkilled`, **AVANT** `FillUpStatComponent$$Reduce` |
| `On(0xf = DamageTaken)` | `0 < réduction RÉELLEMENT appliquée` | après la mutation de PV |
| `On(0x10 = DamageDealt)` | dégât santé **DEMANDÉ** ≥ 1 | dernier |

C'est ce « avant la mutation de PV » qui fait que **Celestine est encore à pleine vie quand la
Geminae apparaît**.

Au passage, la citation `sequence 0x3a -> 0xf -> 0x10` d'`operations/damage.py` était une
**coquille** (`0x3a` = `PhaseEnd`) — corrigée.

## 2. Recensement natif (colonne « classe déclarante » de `frida/classes.tsv`, jamais un grep)

| classe native | base **LUE** | corps propres | fondu ICF |
|---|---|---|---|
| `…Triggered.Loki.RedRampage_AttackAbility` | `BaseTriggeredAbility` | 3 — `CreateTrigger`, `CreateBehaviour`, `GetTargets` | `.ctor` **oui** |
| `…Triggered.Loki.RedRampage_BuffAbility` | `BaseTriggeredAbility` | 4 — `CreateTrigger`, `CreateBehaviour`, `NeedsEffectUpdateAfterDefeatedEnemy`, `GetEffectTurnsAfterDefeatedEnemy` | `.ctor` **oui** |
| `…Abilities.**Active**.Loki.GeminaeSuperiaAbility` | **`BaseTriggeredAbility`** | 4 — `CreateTrigger`, `CreateBehaviour`, `GetPossibleSpawnTiles`, `SummonLimit` | `.ctor` **oui** |
| `IdunBattle.AI.Playbook.Loki.RedRampagePlaybook` | `AdjacentUnitPreferenceTriggeredAbilityPlaybook<RedRampage_AttackAbility>` | 3 — `GetAdjacentEnemyUtility`, `.ctor`, `.cctor` | non |
| `IdunBattle.AI.Playbook.Loki.GeminaeSuperiaPlaybook` | `TriggeredAbilityPlaybook\`1` | 3 — `CalculateMovementUtilityInStepsInternal`, `OwnerInAdjacentTile`, `.ctor` | non |
| `IdunBattleLogic.Entities.Abilities.Triggered.LifewardsAbility` | `BaseTriggeredAbility` | 2 — `CreateTrigger`, `CreateBehaviour` | non |
| `…Triggered.LifewardsAddEffectAbility` | `BaseTriggeredAbility` | 1 — `CreateBehaviour` | `CreateTrigger` **oui** |
| `IdunBattle.Entities.Effects.Loki.LifewardsBondEffect` | `ABondEffect` | 2 | non |
| `IdunBattle.Entities.Effects.Loki.LifewardsProtectingEffect` | `BaseEffect` | 2 | non |

⚠ `GeminaeSuperiaAbility` porte `.Active.` dans son **namespace** pour une base
`BaseTriggeredAbility` : c'est un **passif**. Même piège que `MedicusMinistorum`. La base se lit dans
`classes.tsv`, jamais dans le nom.

## 3. `GeminaeSuperia` n'était pas absente — elle était portée sur l'AUTRE FACE

Recensé **avant** de porter quoi que ce soit (séparation code exécutable / prose par AST) :
**10 lignes de code**, 3 de commentaire, 18 de docstring.

* `engine/playbook/geminae_superia.py` — face **DÉCISION/MOUVEMENT**, inscrite dans
  `TRIGGERED_MOVE_PLAYBOOKS`. **RE-CONFRONTÉE au décompilé** pour cette tranche : les **trois termes
  sont JUSTES**. Une seule **citation** était fausse (`get_CasterTile` là où le natif appelle
  `IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile`) — corrigée.
* Deux **lecteurs** de l'effet `1061 GeminaeSuperia_JustSummonedEffect`
  (`operations/spawn.py`, `abilities/loki/momentum.py`), tous deux annotés « NO-OP offline tant
  qu'aucun poseur de 1061 n'est porté ». **Ce port est le poseur qui manquait : il les arme.**

Ce qui manquait : la face **COMBAT** (aucune entrée dans les quatre registres de trigger).

## 4. Ce qui a été tranché au décompilé, contre l'intuition

1. **`RedRampage` frappe TOUS les ennemis adjacents.** Son `CreateBehaviour` passe le sélecteur
   **NU** ; son voisin de forme `ChampionOfTheFeast` (même event `On(0x1c)`, même gate) l'enveloppe
   dans `Cache(Otherwise(PickRandomly, PickRandomly))` et ne frappe qu'**une** cible. Recopier le
   voisin aurait donné un port faux **et** un tirage PRNG parasite : l'arbre de `RedRampage` n'en
   consomme **aucun**.
2. **Le buff `RedRampage` ne cumule pas** : `If(HasEffect, ChangeEffectTurns(…, `ChangeType.Set`),
   AddStaticStatModifierEffect)`. Deux kills dans un tour = **+1** Movement, pas +2.
3. **Le cap de `GeminaeSuperia` compte les Geminae POSÉES, mortes comprises** :
   `UnitsWithId(Children(Owner), unitId, `UnitSelectionType.Any = 0`)` et
   `DSLSelectors$$Children` **sans filtre `alive`**. Le « twice per battle » de l'i2 est un cap
   d'**usages**. Écrire `Alive(…)` aurait été **plus permissif** que le natif.
4. **`Get(2)` est un LITTÉRAL** de l'ability native : aucune clé de config ne porte ce cap.
5. **`IsFirstDamagingHitInSeries` ≠ `IsFirstHitInSeries`.** Trois champs voisins d'`AbilityEntities`,
   et **deux citations du dépôt étaient fausses** :

   | trigger natif | lit | via |
   |---|---|---|
   | `IsFirstHitInSeriesTrigger` | **`+0x108`** | `get_IsFirstHit` (= `hitIndex == 0`) |
   | `IsFirstHitGroupInAttackTrigger` | **`+0x110`** | `get_IsFirstHitGroup` |
   | `IsFirstDamagingHitInSeriesTrigger` | **`+0x118`** | **aucun getter** — champ lu directement |

   Le nom `isFirstDamagingHit` est **LU** : 29ᵉ paramètre nommé du ctor à 32 paramètres
   d'`AbilityEntities$$.ctor`, juste avant `movementSteps` (+0x11c). Les confondre ferait spawner la
   Geminae sur un coup entièrement bloqué.
6. **Le marqueur 1061 va sur `Target@+0x60`**, donc — le trigger exigeant `OwnerIsTarget` — sur
   **Celestine**, pas sur la Geminae. Et contrairement à son jumeau `SwornProtector` (même champ
   `SpawnUnitOptions+0x10`), l'arbre **ne le retire pas**.

## 5. Confrontation LIVE (board MC1_67, seed 777, injection catalogue des deux porteurs)

Les deux porteurs sont **hors pool** ; `catalog_inject --units "bloodTerminator,adeptCelestine"`
les y fait entrer (97 → 99).

**`RedRampage_AttackAbility`** — Cezare @(3,4) se déplace en (4,4), au contact de `tauCrisis` et
`tauMarksman` :

```
[Ability_Power e=77 «RedRampage»]
  [Damage e=79] Amount=5029 Attack_DidCrit=1 Attack_Is_First_Hit=1 DamageProfileType=14 Passive_Ability_Type=1551
  [Damage e=79] Amount=1810 Attack_Is_First_Hit=0                  DamageProfileType=14 Passive_Ability_Type=1551
  [Damage e=81] Amount=3843 Attack_DidCrit=1 Attack_Is_First_Hit=1 DamageProfileType=14 Passive_Ability_Type=1551
  [Damage e=81] Amount=1078 …
```

⇒ déclenché à l'arrivée sur la tuile finale, **2 coups sur CHACUN des deux ennemis adjacents**,
profil `Power` (14), `Passive_Ability_Type = 1551`. Le point 4.1 est confirmé au flux.

**`RedRampage_BuffAbility`** — Cezare tue `tauMarksman` pendant son tour : il porte ensuite
`RedRampage_ExtraMovement` (effet **1570**). Durée lue `r2` **post-tick** puis `r1` après un tour
adverse — cohérent avec `Sum(Direct(1), TurnsFromRounds(1))` = 3 tours à la pose.

**`GeminaeSuperia`** — Celestine @(3,4), `tauCrisis` @(3,5), un seul héros déployé :

| tour | observé | lecture |
|---|---|---|
| 1 (IA attaque) | Celestine **6025/6025 = PLEINE VIE**, **2 de mes unités tuées** alors qu'**une seule** était déployée | les 2 Geminae ont spawné et encaissé à sa place (`Lifewards`), puis sont mortes |
| 2 (IA attaque) | **AUCUN** spawn, Celestine encaisse 1566 dmg | **cap atteint malgré 0 Geminae vivante** |

⇒ le tour 2 est la **confirmation directe du point 4.3** : si le cap comptait les vivantes, une 3ᵉ
Geminae serait apparue.

## 6. Ce que la tranche livre

* `engine/runner/operations/triggers/loki/red_rampage.py` — 2 classes (faces attaque + buff) ;
* `engine/runner/operations/triggers/loki/geminae_superia.py` — face combat ;
* `engine/runner/operations/triggers/dispatch/attack.py` — **le vecteur `pre_damage_taken_triggers`** ;
* `engine/runner/operations/damage.py` — son câblage dans le pipeline, à la place native ;
* trois primitives portées : `PendingMovingTile` (sélecteur), `IsFirstDamagingHitInSeries`
  (trigger), `SpawnUnitOptions+0x10` (`Spawn(on_spawn_effect=…)`) ;
* `RedRampagePlaybook` (face décision, lookup plat `RedRampage_LikesAdjacentEnemies` = 20) ;
* `tests/engine/runner/test_963_red_rampage_geminae_offline.py` — **23 tests**, 7 étages,
  **3 contre-épreuves rouges** vérifiées.

⚠ Le garde du câblage a été **écrit deux fois** : la 1ʳᵉ version cherchait la chaîne
`pre_damage_taken_triggers(` dans le source, et la contre-épreuve l'a **réfutée** — remplacer
l'appel par `None and …` (donc le désarmer entièrement) la laissait **verte**. La version livrée
confronte l'**AST** : l'appel doit être une **instruction nue**.

## 7. Résidus ouverts

| # | quoi |
|---|---|
| `#963-r1` | `AreEnemies` ignore `UnitTeamSelectionType.ByOriginalTeam` (le nœud porté compare l'équipe **courante**) — résidu **partagé** par tous ses call-sites |
| `#963-r2` | `isFirstDamagingHit` est rendu par groupe (`is_first_hit`) et non par coup : si le coup d'index 0 est entièrement bloqué, le natif marque le premier coup damageant suivant, le port n'en marque aucun. Dégradation **restrictive** |
| `#963-r3` | `TriggerAbility(Lifewards)` rend `dispatched: False` (1049 absent de `TRIGGERED_ABILITY_BEHAVIOURS`) — le transfert de dégât (`AddBondEffect(0x424)` + `AddBondEffect(0x4d8)` + `TransferDamage`) reste à porter |

Non couvert et **nommé** : la durée exacte de `RedRampage_ExtraMovement` n'a été lue que **post-tick**
(`r2`, puis `r1`) ; l'event de pose (`Effect_RemainingTurns`) n'a pas été capturé — `aiturn`
n'imprime pas la cascade. Et l'ordre relatif de `SpawnUnitOptions+0x10` et `+0x18` n'est pas tranché
au décompilé (inerte : aucun call-site lu ne porte les deux).
