# #488-r1 — `OnMeltaDamageAbility` (1211) est VIVANTE : le +50 % vs `Vehicle` existe, et il est porté

**Statut : LIVRÉ (2026-08-07), build `rnca9r7q6c`.** Le verdict DEAD-CODE de `case-72` est **faux
sur ce build, et sa RAISON l'était déjà**. Le port applique désormais le bonus, en prédiction et en
combat.

## 1. La question, posée avant la méthode

`case-72` avait classé `1211` DEAD-CODE sur `gqfc5mff6c` au motif que l'ability n'override pas
`CreateTrigger`. #519 a falsifié cette racine au décompilé. La question de cette tranche n'était
donc **pas** « le symbole existe-t-il » — c'est :

> **Le chemin est-il VIVANT ?** Et si non, par quel mécanisme exactement ?

Deux réserves, nommées par #519, à lever avant tout port. **Les deux sont tombées, et chacune
tenait sur un raisonnement dont ce dépôt connaît déjà le vice.**

## 2. Réserve (a) — « le corps est dédupliqué » : levée par le SLOT DE VTABLE

Le corps `return DSLTriggers.On(0x19 MatchInit, true)` est bien **partagé** : son adresse porte
**8** xrefs DATA contre **2** chez `OnFire`/`OnToxic`, et il vit loin du bloc de la classe. La
présence du symbole ne prouvait donc pas plus l'override que son absence ne prouvait la
non-surcharge (`CLAUDE.md`, « L'ABSENCE d'une méthode dans les tables ne prouve RIEN »).

**Deux voies indépendantes concluent, et elles concordent.**

**Voie 1 — RUNTIME** (RPC `resolveMethodPtr`, la voie de #507). Profondeur du premier corps dans la
chaîne de parents ; `0` = la classe **déclare** :

| classe | `CreateTrigger` | `CreateBehaviour` | `GetTargetTiles` |
|---|---|---|---|
| `OnFireDamageAbility` | **0** | 0 | **0** |
| `OnToxicDamageAbility` | **0** | 0 | *absente* |
| **`OnMeltaDamageAbility`** | **0** | 0 | *absente* |

Le **contre-cas** est ce qui rend l'étage crédible : `GetTargetTiles`, que seul `OnFire` déclare,
rend bien « absente » pour les deux autres. Un étage qui répondrait « profondeur 0 » à tout aurait
été vert sans rien mesurer.

**Voie 2 — TABLE DE MÉTHODES** (offline, `ghidra`). Le tableau contigu de pointeurs de méthodes est
lisible bloc par bloc, et les deux jumeaux y ont **la même forme** :

| bloc | slots (dans l'ordre déclaratif) | classe |
|---|---|---|
| `…29e0`–`…29f0` | ctor trivial *partagé* · **corps `On(MatchInit)`** · `OnMeltaDamageAbility$$CreateBehaviour` | `OnMeltaDamageAbility` |
| `…29f8`–`…2a08` | ctor trivial *partagé* · `OnToxicDamageAbility$$CreateTrigger` · `OnToxicDamageAbility$$CreateBehaviour` | `OnToxicDamageAbility` |

Le ctor est **le même corps** pour les deux (déduplication, exactement le mécanisme de #507).
Contrôle de lecture : le slot 3 du bloc `OnFire` résout en
`IdunBattleLogic.Entities.Abilities.Active.OnFireAbility$$CreateBehaviour` — un corps mislabellé
mais bien celui qu'on attend (`AddEffect(5 Fire, Tiles(Target))`).

⇒ **`OnMeltaDamageAbility` déclare `CreateTrigger`. La racine de `case-72` est falsifiée.**

## 3. Réserve (b) — « aucun effet observé » : le canal mesurait le MAUVAIS SUPPORT

`$$CreateBehaviour`, relu en entier :

```
AddEffect( effectType = 0x511 = 1297 Melta_ExtraDmg,
           abilityState = BaseTriggeredAbility$$get_AbilityStateReference(this),
           targets = DSLSelectors$$First( <DSLSelectors+0x18>, amount: 1, ignoreForcedTargets: 0 ),
           turns = null )
```

`<DSLSelectors+0x18>` est **lu, pas déduit** :
`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` y écrit nommément
`new AllTilesSelector(state, onlyEmpty: 0)`. Le support de l'effet est donc **UNE TUILE**, la
première du plateau — pas l'attaquant.

Or #519 avait cherché l'effet dans `decisionView.effects`, **une vue PAR UNITÉ**. Son silence ne
pouvait rien dire. Le bon canal est `tileMeta` :

```
(0,0) : Melta_ExtraDmg            <- l'effet, bien posé
(1,3) (1,6) (4,6) (5,3) : BlockEnteringUnits, Thorns_DefenseReduction   (les Swamp)
```

⇒ **L'effet EST posé.** (Le dépôt le savait déjà sans le voir : `static_battle_rules.py` cite
`Melta_ExtraDmg` parmi les effets de tuile **non-status** mesurés live en #102.)

## 4. Le verdict : VIVANT — et le bonus ne dépend PAS de la tuile

Régime discriminant : armure **égalisée** à 2000 sur les trois cibles, géométrie identique
(attaquant `(4,0)`, cible `(2,0)` — distance 2, donc l'arme **RANGED** `Melta` ; à distance 1 le
natif prend la mêlée, dont le profil n'est pas `Melta`), PV à 400000 pour que la borne haute ne soit
pas clampée, crit et block éteints.

| cible | trait | bande NATIVE |
|---|---|---|
| `admecDestroyer` | **`Vehicle`** | **[9014 – 13520]** |
| `orksNob` | — | [6008 – 9014] |
| `adeptCanoness` | — | [6008 – 9014] |

Rapport **1,50033 / 1,49989** — le `meltaDamageExtraDmgPct = 50` du gameconfig. **Deux** témoins et
non un : ils coïncident exactement, donc l'écart tient au **trait**, pas à la cible. Et il
**disparaît** en mêlée (profil non-`Melta`) : le gate de profil mord aussi.

**Le bonus est indépendant de la position** — mesuré, et c'est ce qui explique tout le reste :
l'attaquant physiquement posé **sur** la tuile porteuse `(0,0)` rend la **même** bande que depuis
`(4,0)`, qui ne porte rien.

La cause est architecturale, et elle est lue :
`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` **n'itère pas
les effets de l'attaquant** — il itère une collection reçue en paramètre et invoque le slot de bonus
sur chaque effet **sans aucun filtre de propriétaire, de position ni d'adjacence** : il passe
l'`AbilityEntities` complet (attaquant `+0x08`, cible `+0x10`, tuile `+0x40`, arme `+0x48`) et laisse
l'effet décider seul. Or les deux conjoints du gate de `Melta_ExtraDmg` portent sur le **coup** et sur
la **cible** :

```
IdunBattle.Entities.Effects.Loki.Melta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack
    ForPercentIncrease( DamageProfileHasTrait(0x5 = OnMelta)
                        & HasTrait(Target@DSLSelectors+0x60, 0x405 = Vehicle),
                        ConfigConst(0xf) = meltaDamageExtraDmgPct = 50 )
```

La tuile n'est qu'un **support d'existence**. L'ability étant GLOBALE (aucun owner — même famille
`Damage.Loki.*` que `OnFire`/`OnToxic`) et son trigger `MatchInit` inconditionnel, l'effet est
présent dans **toute** bataille.

## 5. Le port

* **`MeltaExtraDmgEffect`** (`entities/effects/loki/extra_damage.py`) — mirror 1:1, jumeau
  structurel de `BeastSlayerExtraDmgEffect` à une différence lue : le premier conjoint n'est pas un
  nœud mêlée mais `DamageProfileHasTrait(OnMelta)`. Helper `_damage_profile_has_trait` (name-based,
  comme `LasCannon`). Enregistré dans `EFFECT_CLASSES` sous `"Melta_ExtraDmg"`.
* **`MATCH_WIDE_EFFECTS`** (`entities/effects/__init__.py`) — la **patte manquante**. Le port avait
  scindé la boucle native unique en pattes (self / aura alliée / aura ennemie) ; il manquait celle
  de l'effet dont le porteur n'est **ni l'attaquant ni une unité**. Les effets match-wide entrent
  dans la **même** boucle `_attacker_effect_bonuses` — le foyer PARTAGÉ prédiction+combat, ce qui
  couvre les deux faces d'un seul geste.

⚠ **Pourquoi PAS « lire l'effet de tuile depuis l'état »**, qui semblait le mirror le plus littéral :
le canal `load_state(tiles=tileMeta)` est **OPT-IN**, et la plupart des états ne le passent pas
(mesure citée par `ai/state_bridge.py`). Un port qui en dépendrait serait **inerte en silence** sur
ces chemins — la dégradation permissive que la doctrine proscrit. La présence de l'effet n'est pas
une donnée d'état : c'est une **invariante de bataille**.
Aucun double comptage : cette boucle ne reçoit que les effets de l'ATTAQUANT, et aucun agrégateur du
port ne balaie les effets portés par une tuile (trou déjà documenté de `board_effect_carriers`).

Rien à poser au registre de ciblage : `1211` est une **triggered**, elle n'entre pas dans
`ABILITY_CLASSES`.

## 6. Validation — et ce qui la rend contraignante

| bras | port | natif | verdict |
|---|---|---|---|
| `admecDestroyer` (**Vehicle**) | (9014, 13520) | (9014, 13520) | **ACCORD** |
| `orksNob` (témoin) | (6008, 9014) | (6008, 9014) | ACCORD |
| `adeptCanoness` (témoin) | (6008, 9014) | (6008, 9014) | ACCORD |
| **contre-épreuve** `Vehicle`, `MATCH_WIDE_EFFECTS` vidé | (6008, 9014) | (9014, 13520) | **DÉSACCORD** `(-3006, -4506)` |
| **contre-épreuve** témoins, idem | inchangés | inchangés | **le correctif ne déborde pas** |

**COMBAT** (attaque réelle, crit et block éteints) : `5328 + 6186 = 11514`, dans la bande corrigée
`[9014, 13520]` et **hors** de `[6008, 9014]` — la face combat porte donc le bonus elle aussi.

**GÉNÉRALISATION — autre porteur, autre vecteur, autre oracle.** Le gate porte sur le **profil du
coup**, jamais sur le vecteur : sur ce build, `Melta` est porté par 2 armes de lineup **et par 6
abilities**. `bloodDante` castant `LightOfSanguinius` (voie ACTIVE), confronté à `aiPlaybookPredict` :
port `(8840, 13270)` == natif ; sans le correctif, `(5890, 8845)` — rapport 1,5008 / 1,5003.

**Garde** : `tests/engine/runner/test_488r1_melta_vehicle_live.py` — **9 verts**, six étages
(vtable + son contre-cas, natif, port ×3, morsure, axe ability + sa contre-épreuve, gate offline
conjoint par conjoint). L'oracle de tous les étages est le **NATIF** : si un futur build retire le
bonus, l'étage [1] rougit et dit de **RE-CLASSER**, pas de patcher.

**Rayon de souffle re-validé** (`_attacker_effect_bonuses` touche toutes les attaques) : 9 fichiers,
**44 tests verts** — `test_prediction_trait_gates_live` (6), `test_normal_attack_bonus_decision_live`
(8), `test_ability_prediction_target_traits_live` (7), `test_419r1tr14r5_normal_attack_dispatch_live`
(6), `test_beast_slayer_extradmg_live` (4), `test_damage_ability_live` (1),
`test_attack_nature_normal_like_live` (2), `test_ability_hits_attack_nature_live` (2), et la garde (9).

## 7. Ce qui n'est PAS couvert

* La **POSE** de l'effet n'est pas rejouée par le port : il n'y a pas de `MatchInit` offline, et la
  présence de `Melta_ExtraDmg` est traitée comme une invariante de bataille (cf. §5). Si un futur
  build rendait la pose **conditionnelle**, le port l'ignorerait — l'étage [1] de la garde le verrait,
  mais par son effet, pas par sa cause.
* **5 des 6 abilities** à profil `Melta` non confrontées (`FleshmetalGuns`, `SolarAtomizer` — npc ;
  `TheWailingDoomSweeps`/`Strikes` via `damageProfile_2`, un second champ dont le threading dans
  `att_ctx["damage_profile"]` n'a **pas** été vérifié ; `ArmouredMight`, absente des 5 voies
  dérivables). Résidu **#488-r2**.
* `darkaSternguard`, l'autre porteur lineup du profil `Melta` (en **mêlée**) : non confronté.
* Les 6 autres porteurs du trait `Vehicle` (summons/npc) : non confrontés — le gate est un test de
  trait, sans dépendance à la cible, mais ce n'est pas mesuré.

## 8. Ce qu'on retient

**Un verdict de mort se démontre par un MÉCANISME, jamais par deux absences.** `case-72` en a
empilé deux, et les deux étaient des faux négatifs connus de ce dépôt : une table indexée par
adresse ne voit qu'un propriétaire par corps dédupliqué, et une vue PAR UNITÉ ne peut pas montrer un
effet posé sur une TUILE. Le verdict est resté vrai un build de plus par coïncidence — le trigger
manquait réellement sur `gqfc5mff6c` — ce qui est le pire des cas : la conclusion juste a validé la
méthode fausse, et c'est la méthode qui a été recopiée.

## Symboles cités

- `IdunBattleLogic.Entities.Abilities.Damage.Loki.OnMeltaDamageAbility$$CreateTrigger` / `$$CreateBehaviour` ;
  jumeaux `OnFireDamageAbility$$CreateTrigger` / `$$GetTargetTiles`, `OnToxicDamageAbility$$CreateTrigger` / `$$CreateBehaviour` ;
  `IdunBattleLogic.Entities.Abilities.Active.OnFireAbility$$CreateBehaviour` (corps dédupliqué).
- `IdunBattle.Entities.Effects.Loki.Melta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`.
- `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` (écrit `<+0x18>` = `AllTilesSelector`) ;
  `IdunBattleLogic.Entities.DSLSelectors$$First` (2 surcharges) ;
  `IdunBattle.Entities.Selectors.AllTilesSelector$$Select` / `$$.ctor` ;
  `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect` (4 surcharges) ;
  `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute`.
- `IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` ;
  `IdunBattle.Core.Services.BaseCalculations$$GetFloatMultiplierFromPercentage` ;
  `IdunBattle.Core.Services.DamageModifiers$$Add`.
- Enums : `TriggeredAbilityType.OnOnMeltaDamageAbility` = 1211 ; `EffectType.Melta_ExtraDmg` = 1297 ;
  `UnitTrait.Vehicle` = 1029 ; `DamageTrait.OnMelta` = 5 ; `EventTriggerType.MatchInit` = 25.
