# #547-r12 — le CACHE garde, la LECTURE trie : un cadavre-au-chargement entre au registre

**Foyer** : `scripts/python/engine/runner/operations/triggers/dispatch/core.py`
(`_triggers_du_cadavre_au_chargement`, neuf).
**Build** : `t6dpr4k06g`, aligné sur les trois axes.

## 1. Le partage natif, relu verbatim

Le natif sépare deux gestes que le port confondait.

* `IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache$$AddEntity` n'a **aucun gate de
  vivacité**. Son corps entier aiguille sur le type d'entité (`IsEffect` → `AddEffect`, sinon
  `TryGetComponent<TriggeredAbilityComponent>` → `AddAbility`) : ni `IsAlive`, ni HP, ni stats.
* `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` trie **à la lecture** :

```
if (ability == null) throw;
if (!ability.get_AllowForDeadOwner()) {                 // ITriggeredAbility slot 8
    if (IsUnit(owner) && !IsAlive(owner))    return 0; }
if (IsUnit(owner) && IsTriggersDisabled(owner))         return 0;
```

`get_AllowForDeadOwner` est le mirror `fire_on_death` (#10015 — ce n'est **pas** `IsAtomic`, qui
est `ITriggerable` slot 0 `get_AllowInAtomicMode`).

## 2. L'écart, et le substrat qui le produit

`collect_triggered_abilities` ouvrait sur `if sc is None: continue`. Or le `StatsComponent` n'est
posé que depuis une ligne de `combatSnapshot.units[]`, capteur qui **filtre `IsAlive`**. Une entité
chargée depuis `decisionView.units[]` et absente du snapshot n'avait donc **aucune**
triggered-ability inscrite — exemptée comprise, et **avant** tout gate.

**Le substrat est CONFIRMÉ LIVE** (runner 638, board MC1_67, `adeptCelestine` injectée au catalogue
+ ses ennemis nécrons) :

| canal | contenu mesuré |
|---|---|
| `decisionView.units[]` | 77, 79, 81 **et 95** (`adeptSmnGeminaeSuperia`, `alive=false`) |
| `combatSnapshot.units[].entityId` | **77, 79, 81** — pas 95 |
| `State` après `load_state` | eid 95 : `UnitComponent` présent, `StatsComponent` **absent** |

## 3. Le correctif — inscrire, et laisser `matches` trier

`_triggers_du_cadavre_au_chargement(e, eid, GC, behaviour_trait_triggers)` rejoue les chemins de
registration avec le seul substrat qui survit à l'absence de ctx : la `visual_id` du
`UnitComponent`, donc le **repli gameconfig** — celui que le port applique déjà à toute unité dont
le canal est muet (`UnitContext.from_snapshot` dérive lui aussi `traits` de `cfg.get("traits")`).
Cinq des six chemins sont servis ; le sixième (`UnitConfiguration.TertiaryAbility`, relique
équipée) n'a que le canal `unitAbilityStates`, qui écrit dans le ctx — il reste muet, et c'est
nommé.

Deux restrictions **assumées et écrites au foyer** :

1. **Filtre `fire_on_death`.** Ce n'est pas le mirror du cache (qui garde tout) : c'est une
   restriction qui **coïncide** avec le gate d'aval — `evaluate_trigger_operation` coupe
   `not uc.alive and not fire_on_death`. Le seul régime où les deux différeraient est la
   résurrection d'un cadavre-au-chargement.
2. **Gate `not uc.alive`**, et `uc is None` sort aussi (mirror d'`EntityExtensions$$IsUnit`, que
   `CanGetAbilityTrigger` place devant ses deux gates). Une unité **vivante** sans `StatsComponent`
   n'est pas inscrite : cela demanderait tout son kit, pas les seules exemptées.

**Mesure du delta, LIVE** : sur l'état chargé du runner 638, le correctif ajoute exactement
`LifewardsAbility@95` au registre — 8 entrées → 9, rien d'autre.

## 4. L'étage adversarial — les 23 autres, EXERCÉS

Le tri « régime divergent VIDE » des 23 autres porteurs reposait sur une **lecture de code**
(#547-r11) que rien n'exerçait ; le correctif les inscrit pour de vrai. `probe_547r12
--step ventilation` exerce donc leur `matches` sur un cadavre-au-chargement, dans **cinq régimes** :

| régime | statut | MATCH mesurés |
|---|---|---|
| R1a — tiers, montage minimal | **bloquant** | 0 |
| R1b — tiers, montage enrichi (parent = la cible, adjacent, porteur du 1240) | **bloquant** | **1** — `LifewardsAbility`, le témoin |
| R2 — le cadavre est la CIBLE | inventaire | 1 (`HunterOfSoulsKilledAbility`) |
| R3 — le cadavre est l'ACTEUR | inventaire | 3 (`ControlEdict`, `LightImUp`, `LordOfTempestsAddIce`) |
| R4 — le cadavre est le MOURANT | inventaire | 7 |

**0 exception levée** sur les 36 classes concrètes × leurs événements — c'était le vrai risque de la
tranche (un `matches` qui lève remonterait `evaluate_trigger_operation` et casserait le dispatch).

Les trois MATCH de R3 sont **exactement** les trois que #547-r11 rangeait « l'owner mort ne peut pas
être l'acteur » : confirmation indépendante de son tri, par exécution et non par lecture.

## 5. Ce que le correctif NE ferme PAS — et la prémisse mesurée FAUSSE

La fiche #547-r12 promettait un observable (« Celestine encaisse des dégâts que le natif lui
épargne ») en s'appuyant sur « `decisionView.units[]` conserve les morts **avec leurs effets** ».
**La moitié de cette prémisse est fausse, et c'est mesuré en live** :

* les morts **sont** conservés dans `decisionView.units[]` — vrai, c'est ce qui produit l'entité
  sans `StatsComponent` ;
* mais ils n'y portent **aucun effet**, y compris sous **`includeInactive: true`** — le mode qui
  publie justement les effets posés-mais-inactifs. Mesure sur **trois** cadavres
  `adeptSmnGeminaeSuperia` (eid 95 au runner 638 ; eid 104 et 110 au runner 669) : `effects=[]`
  dans les deux modes.

Le natif retire les effets à la mort : `IdunBattle.Operations.KillUnitOperation$$Execute` appelle
**trois** fois `...$$RemoveEffects(killed, step)` avec `step` = 0, 1, 2
(`IdunBattle.Operations.KillUnitStep` = `PreUnitRemove` / `AfterUnitRemove` / `AfterDeathTrigger`),
qui route sur `IOperationProcessor` slot 90 = `RemoveEffects` →
`IdunBattle.Operations.RemoveEffectsOperation$$Execute`.

**Conséquence** : sur un état issu d'une **capture**, les deux membres de la disjonction de
`LifewardsAbility` sont faux pour un cadavre-au-chargement — `IsAlive(Owner)` par construction,
`HasEffect(Owner, 1240)` parce que le marqueur n'est pas seedé. Le correctif ferme donc un écart de
**fidélité** dont le régime **observable via capture** est vide. Ce qui reste est un écart de
**SEEDING**, pas de dispatch → résidu **#547-r13**.

⚠ **Le régime réel de la disjonction native est INTRA-RÉSOLUTION, et le port le couvrait déjà.**
`IdunBattle.Entities.UnitExtensions$$IsAlive` est lu :

```
!UnitFlagsComponent.Has(6) && <présente sur le plateau> && HealthComponent$$IsAlive()
```

Une Geminae tombée à 0 PV est donc `IsAlive == false` **avant** que `KillUnitOperation` ne retire
ses effets : elle porte encore 1240 et absorbe les coups suivants de la **même** résolution, jusqu'à
ce que `LifewardsProtectingRemove` (`On(0x9 = Attack)`) le retire — ce qui est exactement la
« protection posthume bornée à un coup » déjà écrite dans `loki/lifewards.py`. Dans ce régime
l'entité a été **spawnée dans le run**, donc elle a son `StatsComponent` et était déjà au registre.

## 6. Validation

* `probe_547r12_cadavre_au_registre.py` — six étages, chacun avec sa morsure ou son témoin ;
  `tests/engine/runner/test_547r12_cadavre_au_registre_offline.py` les fige (**6 passed**).
* **327 passed / 1 failed** sur 24 fichiers offline du dispatch. Le seul rouge,
  `test_421_effect_active_gate_offline::test_the_probe_rail_covers_the_whole_registry`, est
  **PRÉEXISTANT** : rejoué dans un worktree témoin à `origin/master` **pur** (`7ba694ef`), il rend le
  même **1 failed / 12 passed**, même assertion. C'est le rouge déclaré de #547-r2/#547-r6.
* **Live** : `test_462_r4b_r1_r1_r1_r1_c_r3_owner_gates_effet_live.py` (8), `test_synaptic_linchpin_live.py`
  + `test_hammer_of_wrath_corpse_decision_live.py` (16), `test_runner_attack_live.py` (2) — **26 passed**.
* Value-preserving mesuré : un état sans cadavre-au-chargement rend un registre **identique** avec
  et sans correctif (étage `preservation`, deux montages dont le mort **du run**).

## 7. Ce qui n'est PAS couvert

* Le **seeding** des effets d'un mort (→ #547-r13) : tant qu'aucun canal ne les publie, le régime
  observable de `LifewardsAbility` sur cadavre-au-chargement reste vide.
* Le sixième chemin de registration (`TertiaryAbility`, relique équipée) reste muet pour un cadavre.
* Une unité **vivante** sans `StatsComponent`, et un cadavre-au-chargement **ressuscité** en cours de
  run : hors du gate posé, nommés au foyer.
* `IsTriggersDisabled` reste non porté (résidu antérieur, inchangé par cette tranche).
