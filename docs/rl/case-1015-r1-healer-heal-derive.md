# #1015-r1 — `Healer` : le trait qui DONNE une ability, et que le port ne lisait nulle part

**Verdict : QUIRK PORTÉ + CONFRONTÉ LIVE (deux faces du même dict).** Le trait `Healer`
(18 porteurs, dont **6 en `lineup`**) n'était évalué **nulle part** dans `engine/**`. Sa sémantique
n'est ni un effet ni un trigger : il **accorde l'ability active `18 Heal`**, dont le corps était
déjà porté (#931-r1) mais qui n'entrait dans le kit d'**aucune** unité côté décideur offline.

## 1. Le porteur natif — un dict, pas un symbole homonyme

Aucun symbole ne sort sous `Healer`, et c'est normal : la mécanique vit dans un **dict de
`.cctor`**. Second dict de
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$.cctor`, écrit à
`<Trait statics>+0x08` et lu par
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Trait$$GetActiveAbility` —
**exactement deux `Dictionary$$Add`** :

```
Add(dict, key = 0x0a UnitTrait.Healer,   value = 0x12 ActiveAbilityType.Heal)
Add(dict, key = 0x0c UnitTrait.Mechanic, value = 0x1c ActiveAbilityType.Repair)
```

Matérialisé aux **deux** moments où une unité reçoit un trait :

* **fabrique** — `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities`, 3ᵉ boucle (sur
  `config@+0xd0` = `UnitConfiguration.Traits`) : `GetActiveAbility(trait)` → si le `Nullable` a une
  valeur, `Idun.Shared.Level$$.ctor(1, 0)` puis `IdunBattle.Configuration.AbilityState$$.ctor(level,
  config@+0x74)` puis `IdunBattle.Entities.Components.ActiveAbilityComponent$$Add(type, state)` ;
* **en bataille** — `IdunBattle.Operations.AddTraitOperation$$AddDerivedAbilities` (même lecture,
  même `Level..ctor(1, 0)`), et l'inverse `RemoveTraitOperation$$RemoveDerivedAbilities`.

Le **niveau** de la dérivée est le littéral `1`, pas celui des abilities de kit. Sans effet ici
(la magnitude de `18`/`28` vient de l'ARME, pas d'une variable de config) — mais c'est **lu**.

## 2. La voie inverse : un PASSIF retire la dérivée

`IdunBattleLogic.Entities.DSLBehaviors$$RemoveActiveAbility` n'a que **trois** appelants de code
(xrefs entrantes, exhaustives), tous des `CreateBehaviour` de passif substitutif :

| passif | littéral retiré | ability substituée |
|---|---|---|
| `...Triggered.Loki.TwistedScienceAbility$$CreateBehaviour` | `0x12` | `0x48f` = `1167 Heal_TwistedScience` |
| `...Triggered.Loki.HealingBalmsAbility$$CreateBehaviour` | `0x12` | `0x4bc` = `1212 HealingBalms_Heal` |
| `...Triggered.Loki.GalvanicFieldAbility$$CreateBehaviour` | `0x1c` | `0x45f` = `1119 Repair_GalvanicField` |

Sans ce second registre, deux porteurs `Healer` (`genesBiophagus`, `spaceWolfPriest`) et un porteur
`Mechanic` (`admecManipulus`) auraient **deux** abilities de soin/réparation là où le natif n'en
laisse qu'**une**.

## 3. Ce que le trou coûtait — dégradation MUETTE

`engine.ai.state_bridge._abilities_of` reconstruisait le kit depuis **trois** sources (attaque
normale, `activeAbilities` gameconfig, abilities accordées par un passif) — **pas** les dérivées de
trait. Or `18 Heal` n'apparaît dans **aucun** `activeAbilities` du gameconfig : le trait est sa
seule source. Conséquence, sur les 4 porteurs `lineup` qui la gardent
(`adeptHospitaller`, `bloodSanguinary`, `deathRotbone`, `ultraApothecary`) :
`ActionGenerators._heal_candidates` filtre `me["abilities"]` par `"Heal" in name`, donc il rendait
`[]` — **aucun soin jamais proposé** par le décideur offline. Ni erreur, ni cast refusé : une action
que le natif propose et que le port ne voyait pas.

⚠ **Le NOM est fonctionnel, pas décoratif.** `enum_maps.ACTIVE_ABILITY_TYPE` est orienté
`{id: nom}` ; l'inverser (comme le fait le reste de `_abilities_of` pour les noms de kit) rend
`None` sur `18`, le repli `str(aid)` donne `"18"`, et le filtre `"Heal" in name` **échoue** — le
trou serait redéposé un étage plus bas. Faute commise à l'écriture, attrapée par la mesure.

## 4. Le port

* **Donnée** — `engine/entities/active_abilities.py` : `TRAIT_DERIVED_ACTIVE_ABILITIES` (mirror du
  dict, **deux** entrées) et `PASSIVE_REMOVES_ACTIVE_ABILITY` (les trois littéraux de retrait), plus
  `trait_derived_active_ability` / `derived_active_ability_ids`.
* **Câblage** — `engine/ai/state_bridge.py` : `_abilities_of` prend un 3ᵉ substrat `traits`, propagé
  par `build_from_state` depuis **`entity_trait_names(ctx, vid)`** — le même foyer que `has_normal`
  juste au-dessus, lu **une** fois. `_attack_abilities`/`_plans_for_unit` le propagent aussi : ça ne
  change rien aujourd'hui (ni `18` ni `28` n'ont de `damageProfile`), ça empêche deux vues du kit de
  diverger demain.

⚠ **Le substrat est l'ENTITÉ, et son tri-état N'EST PAS celui de l'axe passif.**
`UnitContext.passive_abilities` vaut `None` par défaut (tri-état porté par le CHAMP) ;
`UnitContext.traits` a `default_factory=list`, donc une liste **vide y est déjà une mesure** et le
repli kit n'a lieu que si le `UnitContext` est **absent**. Confondre les deux fait écrire un test
qui rougit pour une raison inventée (faute commise, corrigée).

## 5. Confrontation LIVE — le témoin non-nul

`tests/engine/test_1015r1_healer_derived_heal_live.py`, board `MC1_67`, seed 777, deux runners.
Lecture natif = `decisionView.units[].abilities` ; lecture port = `build_from_state(...).me`.

| régime | natif | port |
|---|---|---|
| `adeptHospitaller` (`Healer` au kit) | `[granted] Heal (id18)` | `18` |
| `ultraTigurius` (pas `Healer`) | **rien** | **rien** |
| `ultraTigurius` + `--unit-stat 'Traits=["Hero","Psyker","Healer"]'` | `[granted] Heal (id18)` | `18` |
| `genesBiophagus` (`Healer` + `TwistedScience`) | `1167` seule, **18 absente** | idem |
| `necroSpyder` (`Mechanic`) | `28` | `28` |
| `admecManipulus` (`Mechanic` + `GalvanicField`) | `1119` seule, **28 absente** | idem |

Les lignes 2 et 3 sont **la même unité**, deux états de traits, deux comportements natifs
différents : c'est ce couple qui établit que le canal est le TRAIT et non le `visualId`.

⚠ **Aucune injection de config de trait n'a été requise** — `--unit-stat "<vis>:Traits=[...]"`
suffit, le natif monte la dérivée tout seul. Même mesure que la tranche sœur `CloseCombatWeakness` ;
ce n'est **pas** le verrou d'une relique (#237).

## 6. Contre-épreuve par mutation

Trois mutants, chacun sur un maillon distinct — tous **rougissent** :

| mutant | offline | live |
|---|---|---|
| dérivation morte (dict amputé de `Healer`) | 10 rouges | 2 rouges |
| retrait mort (`TwistedScience` retiré du registre) | 4 rouges | 1 rouge |
| nom en repli `str(aid)` | 4 rouges | (offline seul) |

## 7. Ce qui n'est PAS couvert

* **`spaceWolfPriest` reste sans soin offline** — le retrait de `18` par `HealingBalms` est porté,
  mais `state_bridge._granted_abilities` ne résout que la convention `Heal_<Passive>` alors que le
  membre s'appelle `HealingBalms_Heal`. C'est le **statu quo** (il n'avait pas `18` non plus avant),
  pas une régression, et un test le FIGE explicitement comme borne. Résidu **#1015-r4**.
* **La face COMBAT n'est pas re-confrontée ici** : `18 Heal` est au registre d'exécution avec son
  masque depuis #931-r1 (`engine/runner/abilities/heal.py`), gate `HealUnitOperation` compris. Ce qui
  manquait était le canal qui la MET dans le kit — donc la face DÉCISION.
* **L'utilité comparée du soin** (le tour IA natif choisit-il `Heal` plutôt qu'attaquer, sur une
  cible blessée donnée ?) n'est pas mesurée : `HealPlaybook` est porté et confronté par ailleurs
  (#45c, #419-r1-tr14-r5-r2-r1-r1-r1), et cette tranche n'a touché ni le scoreur ni le générateur.

## 8. Effet mesuré sur la couverture

`docs/rl/kit-coverage.md` régénéré : `lineup=127 complets=127 **avec-travail=0**`. `Healer(x18)`
était le seul manque des kits `bloodSanguinary`, `deathRotbone`, `genesBiophagus`,
`adeptHospitaller`, `spaceWolfPriest`, `ultraApothecary`.
`trait_channels.canaux("Healer")` : `[]` → `['registre:TRAIT_DERIVED_ACTIVE_ABILITIES']`.
