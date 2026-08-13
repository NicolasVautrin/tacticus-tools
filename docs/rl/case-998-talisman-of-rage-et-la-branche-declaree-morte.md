# #998 — `TalismanOfRage`, et la branche du multiplicateur qu'un « 0 porteur » avait tuée

**Question binaire.** Les six abilities de relique à trois porteurs sont-elles portables, et
laquelle rend le plus ?

**Réponse.** Une seule a été portée (`TalismanOfRage`), et ce qu'elle a ouvert vaut plus que le
port : le multiplicateur qu'elle partage avec le trait `BlessingsOfKhorne` portait une branche
**déclarée morte à tort**, sur un chemin à **6 porteurs**.

Build de mesure : `rnca9r7q6c`.

---

## 1. Le fait central — un verdict de dead-code falsifié par le vice #323

`engine/entities/effects/loki/status.py` portait, en toutes lettres :

> La branche self-kills (`ActorHasTriggeredAbility(owner, 1460=TalismanOfRage)`) est
> **INERTE-PAR-ROSTER : AUCUN unit du gameconfig courant ne porte TalismanOfRage (vérifié
> unit_map)** — non codée, à activer si un carrier apparaît.

**Re-mesuré, l'outil cité dit l'inverse** :

```
python scripts/python/unit_map.py find --ability TalismanOfRage      -> 6 unites
  worldJakhal / worldEightbound / worldExecutions      lineup  voie:item    (relique EQUIPABLE)
  worldBossJakhalLHE / ...EightboundLHE / ...ExecutionsLHE   npc  voie:relic (CABLEE AU KIT)
```

Le verdict venait de l'angle mort **#323** : `unit_map` lisait alors 2 voies d'attribution sur 5 et
était **aveugle aux reliques**. Il en lit 5 depuis, donc l'affirmation est aujourd'hui contredite
par sa propre source. Et le régime où la branche mord n'est pas exotique : **les trois porteurs
`lineup` sont exactement les World Eaters qui portent le trait `BlessingsOfKhorne`** — les deux
termes se rencontrent sur la même unité.

Les trois bosses npc la portent **au kit** (voie `relic`) : la branche est donc vivante **même sans
aucun montage de relique**.

## 2. Le multiplicateur, relu nœud par nœud

`IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee` :

```
base  = Count( NormalUnits( UnitsDefeatedByMeleeAttack(AllUnits, 0, 1), 0 ) )
mine  = Count( Filter( <les MEMES entites>,
                       AreEqual( Killer(<DSLSelectors+0x68>), Owner@DSLSelectors+0x30 ) ) )
extra = If( ActorHasTriggeredAbility(Owner@+0x30, 0x5b4 = TalismanOfRage), mine, Direct(0) )
return  Min( Sum(base, extra), ConfigConst(0x4c0 = BlessingsOfKhorne, 0x43 = MaxDefeatedUnits) )
```

**`Sum` PUIS `Min`** — le cap porte sur la somme, pas sur chaque terme. C'est le seul point où un
mirror plausible mais faux (`Min(base,cap) + Min(extra,cap)`) diverge, et c'est le cas discriminant
du test. Foyer unique porté : `status.py::multiplier_based_on_defeated_in_melee`, **trois** lecteurs
(les deux value-modifications de `BlessingsOfKhorne` + le canal crit de la relique).

⚠ Le substrat existait déjà et n'était pas lu : `decisionView.units[].killerId`
(`UnitComponent.DeathReason` → `DamageSource$$get_KillerId`, publié par `projection.ts`). Aucun
capteur neuf, aucune fenêtre de reinject.

## 3. `TalismanOfRage_CritDamageReduction` (1453) — le port

`.ctor` = `AOwnerEffectSpecificTriggeredAbility$$.ctor(this, 0x5b4)` (écrit `this+0x60`, que relit
`CreateTrigger` pour `OnOwnerSpecificAbilityInit`) ; `GetEffectType` rend `0x5ad`.

```
CreateCritDamageBonus = ForSubtraction( get_OwnerIsTarget,                <- trigger NU
                                        Multiply( ConfigVar(0x97 = critDmgReduction),
                                                  GetMultiplierBasedOnDefeatedInMelee() ) )
```

⚠ **TROIS enums, et 1460 en désigne DEUX** : `EffectType` **1453** = cet effet, sa **CONFIG** est la
`TriggeredAbilityType` **1460** — tandis qu'`EffectType` 1460 est
`AmuletOfTheVoidwyrm_CritDamageReduction`, la relique voisine du **même canal**, avec la **même clé
de variable** et le **même signe**. Les confondre lirait `[390..579]` au lieu de `[295..438]`, sans
la moindre erreur.

⚠ **Pas de `CreateActiveCondition` propre** (contrairement à 1460) → `active_condition_ported` reste
à `False`, le flag capté fait foi. C'est un choix conservateur assumé, pas une lecture : l'absence
d'un symbole dans la table ne prouve rien.

⚠ L'effet **arme la branche par CONSTRUCTION** : son Owner *est* le porteur de 1460
(`AOwnerEffectTriggeredAbility$$CreateBehaviour` pose `source = targets = Owner`). Il ne dépend donc
pas de la question, non tranchée, de savoir si `decisionView.units[].triggered` publie les abilities
**tertiaires** (hiérarchie 3). `BlessingsOfKhorne`, lui, doit la mesurer — d'où les deux voies.

## 4. Les cinq autres — RE faite, port NON fait

| ability | artefact natif lu | verdict |
|---|---|---|
| **RelicPowerFist** 1466 | `On(Attack) & OwnerIsCaster & CurrentAttackDamageProfilesContain(Power)` → `Maybe(AddEffect(Pinned), c1) & Maybe(AddEffect(Stunned), c2)`, `c = ConditionalAmount(IsSpecialActiveAbility, Double(ConfigVar(chance)), ConfigVar(chance))` | **le moins cher des cinq** — les deux effets existent déjà (`#998-r4`) |
| **Maugetar** 1498 | DEUX abilities + effet 1497 : `AddEffect` sur `TurnStart_EffectActivation`, `If(HasEffect(Owner,1497), ResetMovement)`, et `EffectAdditionalHits.Create(OwnerIsCaster & AttackDamageIsCritical, …, ConfigConst(nrOfHits))` | **DAMAGE confirmé** (`#998-r5`) |
| **OrbsOfDecay** 1465 | `AttackWithAttackDamage` sur `Filter(AdjacentEnemies, ratio d'armure réduite > armorReductionPct)` `& AddEffect(Contaminated)` + effet 1463 additional-hits | `#998-r2` |
| **RelicOfLostCadia** 1459 | `If(OwnerIsCaster, AddEffect(1454, targets=UnitsWithTraits([Imperial, Summon]) sur `SurroundingFriends`), If(AreFriends & IsInRange, AddEffect(1454)))` + `RelicOfLostCadiaAbility_SummonUnit` | `#998-r3` — ⚠ 1454 se lit `FinalVengeance_UnitEffect` dans le mirror (sous cliquet `probe_313`) : à confirmer avant de porter |
| **BookOfFate** 1461 | trois branches `Randomize -> Cache -> SortByFormula(UnitLevel) -> First(1)` chaînées par `Otherwise`, puis `AddStaticStatModifierEffect(1452)` + `RemoveEffect` + `PerformAIAttackFromCurrentPosition` + `Group` | **le plus cher** (`#998-r1`) |

**La catégorie annoncée était juste pour `Maugetar`** (`DAMAGE(DirectDamage)`) : son
`CreateAdditionalHits` frappe réellement — vérifié au décompilé, pas déduit de la colonne d'audit.

## 5. Ce qui n'est PAS couvert

* **Aucune confrontation LIVE de `TalismanOfRage`.** Le port est gardé par un cliquet **offline**
  (`tests/engine/test_998_talisman_of_rage_offline.py`, 14 bras, 7/7 mutations vues rouges). Le
  montage live est pourtant écrit et disponible (`rl_duel build --equip-relic
  "worldJakhal:TalismanOfRage:<n>"`, #237) : il manque la salve de crit mesurée contre le natif.
  Résidu ouvert.
* **Le canal `triggered` pour une relique ÉQUIPÉE** n'a pas été mesuré : si
  `decisionView.units[].triggered` ne publie pas la hiérarchie 3, la branche `extra` de
  `BlessingsOfKhorne` restera muette sur un porteur qui a *équipé* la relique (elle mord sur les
  trois bosses, qui la portent au kit). Le port de la relique, lui, n'en dépend pas (§3).
