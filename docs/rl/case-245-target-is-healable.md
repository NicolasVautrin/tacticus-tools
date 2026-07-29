# Case 245 — `TargetIsHealable` (bit 8) : la règle du filtre statique, et le prédicat qu'on aurait pu confondre

`TargetIsHealable` (`0x100`) était la dernière règle **avec porteurs** du filtre statique de
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` à rester non portée. Ses deux
porteurs — **1002** `CombatRestoratives` (`ultraApothecary`) et **1037** `RevitalizingMalignancy`
(`deathRotbone`) — posent le **même** masque `0x8500` et la même portée `RANGE_ADJACENT`, ce qui
n'autorise pourtant à valider ni l'un par l'autre : les deux ont été rejoués.

## 1. Ce que la règle teste, lu au décompilé

Dans la surcharge à **SEPT** arguments de `TargetingQuery$$GetInvalidTargetReason` — pas celle à
quatre, qui court-circuite pour un caster MoW sur `ActiveAbilityComponent.GetOrNull(...) == null` —
bloc TRAITS, après `TargetIsSummon` / `TargetIsHero` / `TargetIsNotAnObject`, avant son jumeau
`TargetIsRepairable` (bit 16, slot `0x12`) puis `TargetHasFreeAdjacentTile` :

```c
if ((rules & 0x100) != 0) {
    aq = this.<+0x10>;                                   // le champ attackQuery
    if (!aq.<slot 0x11>(caster, <cible résolue>, 0, 1))  // scope = 0, removeEffects = 1
        -> GenericBrokenTargetingRule(0x100);
}
```

* **`this+0x10` EST l'`attackQuery`** :
  `IdunBattle.Core.Services.TargetingQuery$$Init(this, attackQuery, battleQuery, movementQuery, state, config)`
  écrit `*(this+0x10) = attackQuery` (et `+0x18` battleQuery, `+0x20` movementQuery, `+0x28` state).
* Les deux derniers arguments sont des **littéraux du site d'appel** : ghidra rend le `scope` comme
  `in_stack_... & 0xffffffff00000000` (les 32 bits bas mis à zéro → `0`) et le dernier argument `1`
  (`removeEffects = true`).

### Le slot `0x11`, prouvé par un second call-site

`IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select` — **le sélecteur qui porte le nom
`Healable`** — résout `FUN_1801e7040(<query>, <la même classe d'interface que la cascade>, 0x11)` et
l'invoque avec `(caster, entity, scope, 1)`. Deux call-sites indépendants, même interface, même slot :
`0x11` = `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed`.

## 2. Le critère : `healable_heal_type_0` ne couvre PAS la règle

C'était la question posée, et la réponse est **non**. Mirror du décompilé de
`AttackQuery$$EntityCanBeHealed` (surcharge 4 arguments) :

```c
if (EntityExtensions.IsMachine(target))                          return false;
if (!(   AttackQuery.IsDamagedUnit(target)
      || (removeEffects && AttackQuery.HasNegativeUnitEffect(target))
      || (caster != null && UnitExtensions.HasFlag(caster, 0x17 CanHealFullHealthUnits))))
                                                                 return false;
if (UnitExtensions.HasHealBlockers(target))                      return false;
if (scope != 0 && AttackQuery.IsAtGroupUnitHealLimit(target))    return false;
if (UnitExtensions.HasTrait(target, 0xd Object))                 return false;
return UnitExtensions.IsAffectedByHealType(target, 0 NonMechanical);
```

| terme natif | `healable_heal_type_0` (garde de MUTATION) | `entity_can_be_healed` (mirror complet) |
|---|---|---|
| `!IsMachine(target)` | ✗ | ✔ |
| `IsDamagedUnit` (HP < max) | ✔ | ✔ |
| `HasNegativeUnitEffect` (sous `removeEffects`) | ✗ | ✔ (non porté, **nommé**) |
| flag caster `CanHealFullHealthUnits` (`0x17`) | ✗ | ✔ (non porté, **nommé**) |
| `!HasHealBlockers` | ✗ | ✔ (non porté, **nommé**) |
| `!HasTrait(0xd Object)` | ✗ | ✔ |
| `IsAffectedByHealType(_, 0)` | ✔ | ✔ |

`healable_heal_type_0` en couvre **2 sur 7** ; c'est le pré-filtre `HealableUnitsSelector` **côté
mutation** (feuille `Heal`), pas le gate **côté ciblage**. Sa signature elle-même est incompatible :
elle prend le triplet DSL `(entities, ectx, unit)`, pas `(state, caster, cible, scope, removeEffects)`.

Le prédicat correct existait **déjà** : `abilities/attack_query.py::entity_can_be_healed`, mirroré
par #247 pour la règle dynamique de 1082 `InspiredToGreatness`. Le port de #245 est donc un
**câblage**, pas une nouvelle transcription — et le module `attack_query.py` documente déjà, un par
un, ses trois non-ports (`HasNegativeUnitEffect`, `HasHealBlockers`, flag `0x17`), qui dégradent tous
dans le **même** sens : ils ne peuvent qu'élargir le refus.

## 3. Le port

`engine/runner/abilities/targeting.py`, dans `get_invalid_target_reason`, **entre**
`TargetIsSummon` et `TargetHasFreeAdjacentTile` — l'ordre n'est pas cosmétique : c'est lui qui fixe
la raison rendue quand plusieurs règles sont rompues.

* **cible** = `unit_of_entity(state, target_id)` (`GetUnit`, qui résout une TUILE en son occupant),
  le même helper que le bit 19 emploie pour `local_c8`. Les deux porteurs ne posent aucun bit de
  domaine, donc `pcVar12 == local_c8 == GetUnit(target)`.
* **garde d'honnêteté** `health_is_readable` : le refus natif tient à une conjonction dont deux
  disjuncts ne sont pas portés ; si le port ne sait pas même **lire** les PV de la cible, refuser
  serait fabriquer un verdict. PV illisibles → aucun gate (dégradation permissive du module).

## 4. Mesure — deux montages, deux porteurs, écart 0

Oracle = `abilityReason` live (`TargetingQuery$$GetInvalidTargetReason` natif). Probe :
`scripts/python/probe_245_target_is_healable.py` ; garde :
`scripts/python/tests/engine/runner/test_target_is_healable_live.py`.

**Trois lignes discriminantes fabriquées** (board `MC1_67`, seed `777`, `--hp-player/--hp-target
300000` pour blesser sans tuer) :

| ligne | natif | APRÈS (#245) | AVANT (`master`) | `sansHealable` |
|---|---|---|---|---|
| allié adjacent **blessé**, non mécanique | `0` | `0` | `0` | `0` |
| allié adjacent **à PV pleins** | `0x100` | **`0x100`** | `0` | `0` |
| allié adjacent **blessé** et **MÉCANIQUE** | `0x100` | **`0x100`** | `0` | `0` |
| allié hors contact | `0x8000000` `TargetIsInRange` | idem | `0` | idem |
| ennemi | `0x400` `TargetIsFriendly` | idem | `0` | idem |
| caster (self-cast, une cible valide existe) | `0` | `0` | `0` | `0` |

Accord natif/port : **7/7 pour 1002, 7/7 pour 1037**, **0 ligne de GAP**. Contrefactuel
`sansHealable` : **2 verdicts déplacés** sur chaque montage → le bit est bien celui qui rend le refus.
5 casts illégaux rattrapés par montage.

**La 3ᵉ ligne porte la thèse.** Un allié mécanique **blessé** est refusé quand même : c'est ce qui
sépare `IsAffectedByHealType(_, 0)` de `HP < max`, et ce qui interdit de faire passer la règle pour un
simple test de PV — donc de la porter avec la garde de mutation.

**Piège de montage, mesuré** : le premier jet utilisait `necroWarden` comme allié mécanique. Il porte
`LivingMetal`, donc la **régénération** : il rentrait à `300000/300000` avant l'interrogation et sa
ligne retombait sur le même terme que « PV pleins ». Les deux termes du prédicat n'étaient plus
séparés. Remplacé par `admecMarshall` (traits `Hero, Mechanical`, aucune régénération).

**Second piège, mesuré aussi** : `applyAction` n'a **pas** de `kind: "attack"` — ses seules formes sont
`move` / `ability` / `finish` / `endturn`. Une action `attack` est acceptée par le transport puis
rendue `ok: false` **sans message d'erreur** : 13 attaques de mise en place silencieusement perdues,
montage « sans blessure », et la ligne « natif accepte » manquante. On passe par
`{kind:"ability", casterId, targetId, abilityType: <NormalAttackType de l'unité>}`, l'id **concret**
lu dans `decisionView.units[].abilities` (l'entrée `kind == "normal"`, ex. `69 Loki_NormalAttack`) —
pas l'id générique 17.

## 5. Effet sur les résidus voisins

`probe_249_deathguard_targeting.py --only units`, ligne `ALLIE deathBlightlord d=1` : passée de
`GAP-permissif` à **`OK`**, et `sans_TargetIsHealable` y déplace 1 verdict. Le seul GAP restant du
montage 1037 est `0x800` `GetCasterNotAddedReason` — résidu **générique** (il dépend de
`TargetingQuery$$GetValidTargets`, qui énumère tout le plateau), pas propre à ce cas.

Compte re-dérivé (`probe_249_unported_rule_carriers.py`) : registre = **94** abilities, **94** masques
posés, **0** bit hors enum ; abilities touchées par au moins une règle non portée : **8 → 6**
(1028, 1047, 1029, 1113, 1202, 1214). Des 13 règles auditées, **9 ont zéro porteur** — il n'y a rien à
y porter.

## 6. Ce qui n'est PAS couvert

* **Les trois non-ports d'`entity_can_be_healed`** — `HasNegativeUnitEffect` (le canal de seed donne
  la liste des effets mais aucun marqueur « négatif »), `HasHealBlockers` (dict `HealthComponent+0x78`
  non exposé) et le flag caster `CanHealFullHealthUnits` (`0x17`, posé par aucun chemin du port). Tous
  **restrictifs** : ils ne peuvent qu'élargir le refus, jamais accepter un cast que le natif refuse.
  Aucune ligne des deux montages n'en dépend.
* **`TargetIsRepairable` (bit 16)** — le jumeau exact (slot `0x12`, même forme d'appel `(caster,
  cible, 0, 1)`), dont le mirror `entity_can_be_repaired` est **déjà écrit**. Non câblé : **0 porteur**
  au registre, donc rien à confronter. Le jour où une ability le pose, le câblage est un copier-coller
  de trois lignes — et il faudra le mesurer, pas le supposer.
* **`GetCasterNotAddedReason` (0x800)** — résidu générique préexistant, hors périmètre.
* **`test_ability_target_gate_lot181_live.py` et `test_ability_target_gate_live.py` n'ont pas pu être
  rejoués** : leur roster contient `ultraInceptorSgt`, et sur le build `rnca9r7q6c`
  **`rl_duel build` échoue en `initAndStart: system error` dès que ce héros est au roster** — y compris
  un roster **du pool**, hors de toute injection (isolé par bissection : `ultraInceptorSgt,
  ultraApothecary` échoue, `ultraEliminatorSgt,ultraApothecary` passe). Blocage **plateforme**, en
  amont de tout code Python de gate ; il élargit le constat de #254, qui ne visait que les rosters
  injectés. 1002 reste couvert par `test_combat_restoratives_live.py` et par le montage de #245.

## 7. Artefacts

* port : `scripts/python/engine/runner/abilities/targeting.py` (`get_invalid_target_reason`, bloc
  `TargetIsHealable` + inventaire de tête) ;
* prédicat (inchangé, mirroré par #247) : `scripts/python/engine/runner/abilities/attack_query.py` ;
* probe (MESURE) : `scripts/python/probe_245_target_is_healable.py` ;
* test (GARDE) : `scripts/python/tests/engine/runner/test_target_is_healable_live.py` ;
* recompte : `scripts/python/probe_249_unported_rule_carriers.py` (bit 8 → `PORTEE`).
