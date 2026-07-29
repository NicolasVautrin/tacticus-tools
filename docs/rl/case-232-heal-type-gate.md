# case-232 -- le gate `IsAffectedByHealType` etait ABSENT de la couche DECISION

**Question posee.** Les 6 gates de `engine/playbook/noncomparable/heals.py` rendent-ils le meme
verdict que `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(u, healType)` natif ?

**Reponse mesuree.** NON avant #232, sur DEUX axes independants (le disjunct `HasTrait(0x421)` et
deux des trois traits d'`IsMechanical`). OUI apres. Mais le gisement STATIQUE est **VIDE** : sur les
669 unites du gameconfig, aucune n'est `LivingMetal`/`Vehicle` sans `Mechanical` et **0** ne porte
`AffectedByHealAndRepair`. Le fix est donc **neutre au bit pres** sur le corpus courant et ne mord
que sur un **octroi EN BATAILLE**.

Rejouer la mesure : `python scripts/python/probe_232_heal_type_gate.py`.

---

## 1. Le natif (decompile, `gqfc5mff6c`)

```
IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(unit, healType)
    if (GetBaseUnitComponent(unit) != null && BaseUnitComponent$$HasTrait(comp, 0x421)) return true;
    if (healType == 0) { if (IsMechanical(unit)) return false; }        // 0 = Heal
    else if (healType == 1 && !IsMechanical(unit)) return false;        // 1 = Repair
    return true;                                                        // 2 = aucun filtre

IdunBattle.Entities.UnitExtensions$$IsMechanical(unit)
    return HasTrait(5 Mechanical) || HasTrait(0x3e8 = 1000 LivingMetal) || HasTrait(0x405 = 1029 Vehicle);
```

Les **litteraux de `healType`** ont ete lus site par site, jamais deduits :

| site natif | expression | healType |
|---|---|---|
| `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetPossibleResurrectTargets` | `UnitsAffectedByHealType(UnitsWithTrait(Friends(AllDeadUnits), 0x1a), **0**)` | 0 |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetHealTargets` | `Healable(caster, self@0x160 + AdjacentFriends(self, 1), **0**)` | 0 |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.RevitalizingMalignancyAbility$$GetAllHealTargets` | `Healable(caster@0x160, UnitsWithoutTrait(Friends(AdjacentUnits) + self@0x148, 0x1a), **0**)` | 0 |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$GetDynamicInvalidTargetReason` | cible AMIE != caster -> `return !IsAffectedByHealType(target, **1**)` | 1 |
| `IdunBattleLogic.Entities.Abilities.Active.Loki.CombatRestorativesAbility$$HealTargets` | `Friends(AdjacentUnits(caster, 1)) + self` -- **AUCUN** wrapper `Healable` | -- |

`CombatRestoratives` (1002) n'a donc **aucun** gate de heal-type : c'est un fait du decompile, pas un
oubli du port (le natif compte la fraction de PV manquante des allies MECANIQUES).

## 2. Le defaut

`heals.py` testait `"Mechanical" in gameconfig.unit(visualId).traits`. Trois ecarts :

1. **le disjunct `HasTrait(0x421)` absent** -- une unite mecanique portant `AffectedByHealAndRepair`
   est soignable pour le natif, exclue pour le port (et inversement pour le repair) ;
2. **`IsMechanical` reduit a 1 trait sur 3** -- `LivingMetal` (51 unites) et `Vehicle` (8) etaient
   ignores ;
3. **substrat STATIQUE par `visualId`** -- aveugle a tout `AddTraitOperation` en bataille, la
   couche COMBAT lisant elle le substrat d'ENTITE (`healable_heal_type_0` / `repairable_heal_type_1`
   via `entities.has_trait`). C'est l'asymetrie decision/combat sur la MEME entite du MEME etat.

## 3. Le fix

Un helper unique `engine/playbook/noncomparable/heals.py::_affected_by_heal_type(ctx, obs_unit,
heal_type)`, consomme par les 6 gates. Il ne **re-implemente rien** : il DELEGUE au mirror deja porte
`engine/runner/operations/triggers/revive_effect.py::is_affected_by_heal_type` (celui qu'appelle
`BattleQuery$$CanBeRevived`), en lui passant un resolveur de trait NAME-BASED bati sur le foyer #225
`entity_trait_names(unit_ctx, visualId)` -- kit gameconfig **+ traits accordes en bataille** (la
collection `BaseUnitComponent+0x40`/`+0x48` cote natif) **+** pseudo-trait de grande-alliance.

`unit_ctx` vient de `ctx.scene.ctx(obs_unit["squadId"])` : sur le chemin `state_bridge`
(`Scene.from_state`) c'est **le meme objet** `UnitContext` que `StatsComponent.ctx`, donc l'octroi y
est vu. `ctx.scene` absente (harnais de sonde) -> borne STATIQUE, exactement comme
`utilities/tile.py::_adjacent_units`.

Les 6 gates :

| # | playbook | ligne | avant | apres |
|---|---|---|---|---|
| 1 | `RitesOfRestoration` | `_resurrectable` (morts) | `Mechanical not in kit` | `IsAffectedByHealType(u, 0)` |
| 2 | `RitesOfRestoration` | allies vivants adjacents | idem | idem |
| 3 | `RitesOfRestoration` | self | idem | idem |
| 4 | `DefendTheDivineWork` | self | `Mechanical in kit` | `IsAffectedByHealType(u, 1)` |
| 5 | `DefendTheDivineWork` | allies adjacents | idem | idem |
| 6 | `RevitalizingMalignancy` | `_healable` | `Mechanical not in kit` | idem type 0 |

## 4. VALIDABLE LIVE ? -- oui pour la COHERENCE, non pour l'octroi NATIF

Le gate ne mord que sur un octroi en bataille, et le trait 0x421 n'a **qu'un** vecteur natif :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SupaCyborkBodyAbility_AddTrait$$CreateBehaviour`
= `AddTrait(dsl, Self@0x148, 0x421, isTemporary = 0)`, ability de la relique
`items/R_Defensive_SupaCyborkBody`.

**Cette relique n'est PAS instanciable dans le harnais**, pour deux raisons independantes :

* ses **9 porteurs** gameconfig (`relicAbilities: ["SupaCyborkBody"]`) sont TOUS `kind=npc` --
  `orksBossBigMek(LHE)`, `orksNpcBigMek`, `orksBossRuntherd(LHE)`, `orksNpcRuntherd`,
  `orksBossNob(LHE)`, `orksNpcNob`. Aucun hero, aucune MoW, aucun summon ;
* **aucun canal de `rl_duel build` ne sait equiper un item** : le seul producteur d'`itemSpecs` est
  `frida/hooks/features/normalize-bc/items-catalog.ts::buildBisItemSpecs`, consomme par
  `normalize-bc` (construction d'une BC JSON) et **jamais** par `buildRunner` ; son defaut est en
  prime `excludeRelics: true`. Cote Python, `itemSpecs`/`excludeRelics` n'ont **aucune** occurrence.

Donc : **la voie NATIVE de l'octroi n'est pas confrontable**. Ce qui EST valide live, c'est la
**coherence decision/combat sur le meme etat**, par le montage de #225 -- le leaf DSL deja porte
`AddTrait` (mirror 1:1 de `IdunBattleLogic.Entities.DSLFactory$$AddTrait` ->
`IdunBattle.Operations.AddTraitOperation$$AddTrait`) ecrit dans la meme collection que le natif, et
la bataille, l'etat et les positions sont reels.

## 5. Validation

`scripts/python/tests/engine/test_heal_type_gate_decision_live.py` -- **28 tests, 28 verts**.

* **etage 0 (offline, 24 cas)** -- table de verite `traits x healType` confrontee a une
  re-derivation INDEPENDANTE du decompile (qui ne passe par aucun code du port), incluant les 4
  combinaisons que l'ancien critere ratait. Plus un **verrou anti-tautologie**
  (`test_old_criterion_was_wrong_on_at_least_one_case`, >= 4 divergences exigees) et la mesure du
  gisement (`test_gameconfig_has_no_static_divergence`).
* **etage 1 (LIVE, neutralite)** -- bataille reelle `MC1_67`/777, 3v3 Imperial : les **8** unites
  rendent le verdict de l'ANCIEN critere aux deux healTypes. La comparaison utilise `_traits`
  (`_unit_cfg` -> `resolve_unit_id`) et non `unit_trait_names`, sans quoi les deux cotes
  partageraient l'accesseur et la garde serait aveugle a une regression de RESOLUTION du `visualId`
  (une garde separee croise les deux accesseurs sur les 669 unites).
* **etage 2 (LIVE, discrimination)** -- montage CRAFTE (les unites sont DEPLACEES, la mort est
  posee) : `adeptHospitaller` caste `RitesOfRestoration`, `adeptRetributor` est mis a mort pour
  ouvrir `ShouldEvaluate`, `admecManipulus` (MECANIQUE) est pose sur une tuile libre adjacente.
  Avant l'octroi il est HORS de `GetHealTargets` -> `util = 2.0` ; apres l'octroi de 0x421 par le
  leaf `AddTrait`, il y entre -> `util = 3.0`. **`Count(GetHealTargets)` +1, exactement.**

**Non-regression rejouee** (apres rebase) : `test_combat_restoratives_live.py` +
`test_revitalizing_malignancy_live.py` + `test_nc_priority_tiers_offline.py` (10 verts) et
`test_playbook_live.py` (3 verts, agreement de decision complet).

## 6. Residus nommes (NON couverts)

1. **Les 5 autres disjuncts du wrapper `Healable`.** `IdunBattleLogic.Entities.DSLFactory$$Healable`
   construit un `HealableUnitsSelector` dont le `Select` appelle le **slot 0x11** de l'`IAttackQuery`
   = `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed(source, entity, checkGroupLimit, 1)` :

   ```
   if (EntityExtensions$$IsMachine(entity))              return false;   // EntityType == 6
   if (!(IsDamagedUnit(entity) || HasNegativeUnitEffect(entity)
         || (source != null && HasFlag(source, 0x17))))  return false;
   if (HasHealBlockers(entity))                          return false;
   if (checkGroupLimit && IsAtGroupUnitHealLimit(entity)) return false;
   if (HasTrait(entity, 0xd = Object))                   return false;
   return IsAffectedByHealType(entity, 0);
   ```

   Le 4e argument de `Healable` est donc `checkGroupLimit`, **pas** le healType (qui est cable a 0
   dans `EntityCanBeHealed`). #232 ne porte que le dernier disjunct ; les cinq autres restent hors
   du port cote DECISION -- notamment `IsDamagedUnit` (une unite a PV pleins est comptee par le port
   dans `Rites.GetHealTargets` alors que le natif l'exclut, **sauf** si elle porte un effet negatif,
   ce qui interdit de porter `IsDamagedUnit` seul comme restriction). Chantier par disjunct, pas
   retouche de ce gate.
2. **`DefendTheDivineWork` : gate non discriminable live.** Son unique porteur `admecManipulus` est
   lui-meme `Mechanical`, donc `self_repairable` est TOUJOURS vrai et le gate
   `GetEligibleTargetsEntities` passe quelle que soit la composition adjacente. Le changement y est
   un mirror de fidelite sans observable atteignable dans le harnais.
3. **Chemin LIVE pur** (decision montee par `engine/ai/context.py`, sans `State`) : aveugle a tout
   octroi, car aucun RPC ne publie la collection de traits RUNTIME (residu #225 §5.3). Point
   d'ancrage a hooker : `IdunBattle.Entities.UnitExtensions$$GetBaseUnitComponent` puis lecture des
   trois collections `+0x40`/`+0x48`/`+0x50`, a exposer dans `combatSnapshot.units[*]`. Non fait ici
   (exigerait une reinjection Frida).
4. **Traits RETIRES (`+0x50`)** : hors de portee, aucun `DSLFactory$$RemoveTrait` dans le binaire.
5. **PRE-EXISTANT, hors #232 -- 3 empreintes rotees de `probe_225_trait_gates.py`.** Les gates
   `P2 IndirectFire`, `P3 Resilient/damage-limit` et `P4 Impervious/damage-limit` pointent
   `playbook/prediction/_shared.py:203/310/311`, lignes qui ne portent plus leur token. **Verifie
   sur `origin/master` lui-meme** (`git show origin/master:.../\_shared.py`, memes 3 lignes
   fausses) : ce n'est pas une derive de #232, c'est une PR anterieure qui a decale `_shared.py`
   sans remettre la table a jour. Les tokens sont aujourd'hui aux lignes **207** (`UnitTrait.
   IndirectFire.name in att_ctx_traits`), **314** (`"target_has_resilient"`) et **315**
   (`"target_has_impervious"`) -- non corrige ici (gates de PREDICTION, hors du peri-metre de ce
   cas, et une empreinte re-pointee sans RE serait un faux vert).
