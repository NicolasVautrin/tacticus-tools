# `#419-r1-tr14-r5-r2` — la voie ACTIVE du dispatch d'attaque normale

Suite de `case-419-r1-tr14-r5-dispatch-attaque-normale.md`, qui a fermé la voie PASSIVE (table à 14
entrées, 14/14 confrontées) et nommé ce résidu : « la voie ACTIVE reste au kit ».

## 1. Ce que dit le décompilé (relu, non hérité)

`IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` — la cascade COMPLÈTE, verbatim :

```csharp
if (config.Traits.Contains(0x0e)) return;          // Erratic  -- porté (-r4)
if (config.Traits.Contains(0x15)) return;          // Harmless -- porté (-r4)
var fromPassive = GetCustomNormalAttackTypeFromPassive(this, config);   // config@+0xa8
if (fromPassive.HasValue) { type = fromPassive.Value; state = triggeredAbilityState; }
else {
    var fromActive = GetCustomNormalAttackTypeFromActive(this, config); // config@+0xa0
    if (fromActive.HasValue) { type = fromActive.Value; state = activeAbilityState; }
    else if (config.Traits.Contains(0x7e7)) { type = 0x406; state = activeAbilityState; }
    else {
        var already = ListExtensions.FilterNewList(comp.<+0x20>, <Func statique>);
        if (already.Count > 0) return;              // rien n'est ajouté
        type = this.<+0x20>;
        state = new AbilityState(Level(1), config.<+0x74>);
    }
}
ActiveAbilityComponent.Add(comp, type, state, null);
```

`IdunBattle.Entities.Factories.UnitFactory$$GetCustomNormalAttackTypeFromActive` :

```csharp
foreach (var active in config.<+0xa0> /* UnitConfiguration.ActiveAbilities */) {
    var custom = StaticBattleRules.ActiveAbility.GetCustomNormalAttack(active);
    if (custom.HasValue) return custom;             // le PREMIER actif gagnant s'impose
}
return null;                                        // PAS de branche tertiaire ici (≠ voie passive)
```

Trois différences avec la voie passive, toutes lues :

1. **le substrat** : `config@+0xa0`, pas `+0xa8` ;
2. **la table** : `StaticBattleRules.ActiveAbility` statics `+0xb8` → **`+0x28`**, une AUTRE table que
   `StaticBattleRules.TriggeredAbility` statics `+0xb8` → `+0x50` ;
3. **pas de branche TERTIAIRE** : la voie passive consulte `config@+0xb0` après avoir épuisé la
   liste, la voie active s'arrête à la boucle.

### 1.1 `config@+0xa0` = `UnitConfiguration.ActiveAbilities` — prouvé par un SECOND corps

Pas déduit du nom de la fonction. `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities`
lit les TROIS champs dans le même corps, et chacun va à un consommateur qui le nomme :

| champ | ce que le corps en fait |
|---|---|
| `config@+0xa8` | itéré → `TriggeredAbilityComponent$$TryAdd(..., hiérarchie **2**)` = les PASSIFS |
| `config@+0xb0` | `Nullable`, → `TryAdd(..., hiérarchie **3**)` = l'ability TERTIAIRE (relique) |
| `config@+0xa0` | itéré PAR INDEX → `UnitFactory$$AddActiveAbility(...)` = les ACTIVES |

Les hiérarchies 2 et 3 sont exactement celles que le port lit déjà (`snapshot.PASSIVE_HIERARCHY`,
`_load_tertiary_abilities`) : la lecture est donc recoupée par du code déjà confronté.

### 1.2 La table ACTIVE — UNE entrée, lue au `.cctor`

`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$GetCustomNormalAttack`
est un `ContainsKey` + `get_Item` sur `statics+0x28`. Ce champ est écrit UNE fois, par
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$.cctor` : `ctor`
du `Dictionary`, **un seul `Add`**, puis l'assignation. Aucun autre `Add` entre les deux.

| clé `ActiveAbilityType` | → valeur `ActiveAbilityType` |
|---|---|
| `1124 PoundThemToDust` | `1126 RogalDorn_NormalAttack` |

**Orientation clé/valeur** — la voie passive l'avait par un second corps
(`IsCustomNormalAttackDerivedFromTriggeredAbility`) ; ce corps n'a pas d'équivalent côté ACTIVE. Elle
se lit ici par la POSITION D'ARGUMENT, dans le foyer de lecture lui-même :
`GetCustomNormalAttack(activeAbilityType)` fait `ContainsKey(dict, <param>)` puis
`get_Item(dict, <param>, out <résultat>)` — le paramètre est donc la CLÉ. Le `.cctor` appelle
`Add(dict, 0x464, 0x466)`, mêmes positions d'argument. Clé = `0x464` = 1124, valeur = `0x466` = 1126.

⚠ Les deux membres sont des `ActiveAbilityType` (la voie passive, elle, mappe
`TriggeredAbilityType → ActiveAbilityType`). Les qualifier est obligatoire : `1124` et `1126` n'ont
aucun sens hors de leur enum.

## 2. Qui l'invoque — chaîne UNIQUE, et elle EXCLUT les Machines

Xrefs, à chaque étage un seul appelant de code :

```
UnitFactory$$Build
  └─ UnitFactory$$AddNormalAttackAbility        (SEUL appelant)
       └─ UnitFactory$$GetCustomNormalAttackTypeFromActive   (SEUL appelant)
            └─ StaticBattleRules.ActiveAbility$$GetCustomNormalAttack   (SEUL appelant de code)
```

**`IdunBattle.Entities.Factories.MachineFactory$$Build` n'appelle JAMAIS
`AddNormalAttackAbility`.** Son corps appelle `UnitFactory$$InitBaseComponent`,
`MachineFactory$$AddConfiguredAbilities` et `UnitFactory$$AddDerivedAbilities` — et c'est tout.

C'est mécanique, pas interprétatif : `AddNormalAttackAbility` a **un seul** xref de code, et c'est
`UnitFactory$$Build`.

## 3. Confrontabilité — trois états, et c'est le troisième

`PoundThemToDust` n'a **aucun porteur** : `unit_map find --ability` rend 0 sur les 5 voies, un
balayage direct des **683** kits (`lineup` 127, `npc` 491, `summons` 65) rend 0 en `activeAbilities`
comme en `passiveAbilities`, et les **175** unités du seed BC n'en portent pas non plus.
`RogalDorn` n'est aucun `unitId` du gameconfig — le contexte natif dit *guild boss*
(`IdunBattle.View.AbilityConfigs.Loki.GuildBossRunAwayWalkRogalDornVisuals`,
`Loki_RogalDornBossAttackVisuals`).

**Ce zéro n'est pas un verdict de mort.** Le substrat est `BC.Units[].ActiveAbilities`, qui est
**écrivable** — `catalog_inject.graft_active_ability` (#447) fait les deux écritures nécessaires
(l'id dans `BC.Units[].ActiveAbilities`, la config dans `BC.Abilities.ActiveAbilities[<nom>]`).
C'est le pendant exact, sur l'autre champ, du chemin B de `-r1`.

### 3.1 Les quatre bras, et ce que chacun porte

Un runner, board `MC1_67`, quatre unités du pool, chacune son bras :

| unité | `PassiveAbilities` | `ActiveAbilities` | natif MESURÉ | rôle |
|---|---|---|---|---|
| `astraBullgryn` | `[]` | `[PoundThemToDust]` | **`RogalDorn_NormalAttack`** | PREUVE |
| `necroWarden` | `[]` | (origine) | `Loki_NormalAttack` | TÉMOIN |
| `orksNob` | `[Boltstorm]` | `[PoundThemToDust]` | **`Boltstorm_NormalAttack`** | BORNE |
| `eldarRanger` | `[Boltstorm]` | (origine) | `Boltstorm_NormalAttack` | contrôle apparié |

**4/4.** Le TÉMOIN sépare « la voie active ne substitue pas » de « le montage est mort ». La BORNE
est le régime où les deux modèles (avec et sans voie active) donnent la même réponse — elle ne
prouve donc rien à elle seule, elle **borne**. Mais elle n'est pas décorative pour autant, et c'est
le volet CANAL qui le montre.

### 3.2 Le canal, et pourquoi la BORNE n'est pas dégénérée

Le natif dispatche sur `config@+0xa0`. Le port n'a pas ce champ : le seul canal disponible sans
capteur neuf est `unitAbilityStates.actives[].type`, c'est-à-dire l'`ActiveAbilityComponent` — un
**SUR-ENSEMBLE** (il porte en plus l'attaque normale que la fabrique vient d'y écrire, et les
abilities de `UnitFactory$$AddDerivedAbilities`). Mesuré sur les mêmes quatre bras :

| unité | `ActiveAbilityComponent` | contient `1124` |
|---|---|---|
| `astraBullgryn` | `[1124, 1126]` | oui |
| `necroWarden` | `[1005, 69]` | non |
| `orksNob` | **`[1124, 1128]`** | oui |
| `eldarRanger` | `[1063, 1128]` | non |

`1124` n'apparaît **que** là où on l'a écrit : le sur-ensemble est sûr pour la seule clé de la table.
Et la ligne `orksNob` est ce qui rend la **cascade** obligatoire : la clé active EST montée, et
pourtant l'attaque normale est celle de la voie passive. Un port qui répondrait « `1124` présent
donc `1126` » se tromperait exactement là — ce que la mutation « priorité inversée » confirme (§6).

### 3.3 Ce que cette voie NE change PAS — mesuré, pas supposé

Le discriminant chiffré était posé **avant** la mesure : deux runners identiques à une écriture près
(`templAggressor` passifs vidés, board `C2_02`, même cible, même tuile `(0,2)`), `aiPlaybookPredict` :

| bras | attaque normale native | bornes de dégât | coups |
|---|---|---|---|
| `ctrl` | `69 Loki_NormalAttack` | `1299..1950` | 3 |
| `act` | `1126 RogalDorn_NormalAttack` | **`1299..1950`** | 3 |

**Identiques.** Le port rend `1299..1950` des deux côtés lui aussi. Et `1299..1950 / 3` est
exactement la valeur publiée par la généralisation de `-r1` pour le bras `strip` : le montage se
raccorde à un chiffre déjà établi ailleurs, ce qui le contrôle.

Le playbook ne bouge pas non plus, et ça se lit :
`IdunBattle.AI.Playbook.Loki.RogalDorn_NormalAttackPlaybook$$.ctor` délègue au **même** générique
`ALoki_NormalAttackPlaybook<T>$$.ctor` que `IdunBattle.AI.Playbook.Loki.Loki_NormalAttackPlaybook$$.ctor` —
seul l'`ActiveAbilityType` passé en argument change (`0x466` contre `0x45`), et il n'a aucun
override. Contraste sur le **même gisement**, qui vaut mieux qu'une absence :
`ProperKilly_NormalAttackPlaybook` en porte cinq, donc la table de symboles sait montrer un override
quand il y en a un.

⚠ Cette invariance n'était pas prévisible : `RogalDorn_NormalAttackAbility$$.ctor` dérive de
`IdunBattle.Entities.Abilities.ADeprecatedActiveAbility`, pas d'`ALoki_NormalAttackAbility`.
C'est bien la mesure qui tranche.

**Conséquence assumée** : la table ACTIVE est portée pour la **fidélité de la cascade**, pas pour
refermer un écart de dégât. Il n'y en a pas — et c'est écrit ici pour que personne n'aille en
chercher un.

## 4. Le piège annoncé — RÉFUTÉ, et le natif dit mieux

`engine/ai/context.py::build_machine` pose `normal_ids = set()` en écrivant « les 8 MoW du pool ont
`weapons=[]` en gameconfig ». C'est une dérivation du **KIT** — la forme de raisonnement que #551 a
fermée sur la voie passive. La question posée était : même faute ?

**Non.** Le résultat est juste, et pour une raison bien plus forte que le kit :
`IdunBattle.Entities.Factories.MachineFactory$$Build` n'appelle **jamais**
`AddNormalAttackAbility`. Son corps appelle `UnitFactory$$InitBaseComponent`,
`MachineFactory$$AddConfiguredAbilities` et `UnitFactory$$AddDerivedAbilities`, et c'est tout. Le
constat est mécanique : `AddNormalAttackAbility` a **un seul** xref de code, `UnitFactory$$Build`.

Confronté, et avec le bras qui tranche :

| bras | `MoW.ActiveAbilities` | abilities `kind == "normal"` |
|---|---|---|
| `ctrl` | (origine) | **aucune** |
| `active` | `[PoundThemToDust]` **écrit** | **aucune** |

Le second bras est ce qui sépare « le natif ne monte rien sur une Machine » de « le kit de ces 8
MoW-là est vide » : si la voie active mordait sur une Machine, elle mordrait là.

**Ce qui reste à corriger est donc la JUSTIFICATION, pas la valeur.** Un `set()` posé au motif que le
kit est vide est juste par coïncidence : le jour où une MoW recevrait une arme au gameconfig, la
ligne se lirait comme périmée et quelqu'un la « corrigerait » à tort. Le commentaire est réécrit sur
la lecture native.

## 5. Le port

Foyer unique, `engine/services/custom_normal_attack.py` :

* `CUSTOM_NORMAL_ATTACK_BY_ACTIVE` — la table, une entrée, transcrite du `.cctor` ;
* `custom_normal_attack_from_actives` — mirror 1:1 de la boucle « le PREMIER actif gagnant » ;
* `custom_normal_attack(passive_abilities, active_abilities, visual_id)` — la **cascade**, avec sa
  priorité. C'est la fonction qui répond « QUELLE attaque normale la fabrique pose-t-elle » ;
* `substitutes_normal_attack` consomme désormais la cascade complète, et non plus la seule voie
  passive : une entité dont la voie ACTIVE a gagné ne porte l'attaque normale d'**aucun** passif.

**Tri-état PAR VOIE.** Chaque liste a son canal, donc son repli. `None` = canal muet → cette
voie-là retombe sur le kit ; une liste (fût-elle vide) = mesure, et elle fait autorité pour cette
voie seulement.

### 5.1 Le repli ne fusionne plus les deux sources

`_kit_ability_names(visual_id)` lisait `kit["passive"]` **et** `kit["active"]` en un seul ensemble,
si bien qu'un passif de la table trouvé dans les ACTIVES du kit faisait répondre VRAI à un prédicat
que le natif ne pose que sur `UnitConfiguration.PassiveAbilities`. Il prend maintenant la voie en
paramètre. Trois mesures sur les **683** kits, avant correction :

| gisement | compte |
|---|---|
| clé de la table PASSIVE présente en `activeAbilities` (l'ancien faux positif) | **0** |
| clé de la table ACTIVE présente en `activeAbilities` (le repli actif) | **0** |
| kits portant ≥ 2 passifs de la table (l'ordre du repli devient discriminant) | **0** |

Le faux positif était donc **latent** : la correction est structurelle, pas déclenchée par un
symptôme. Dit ici avec son chiffre pour que personne ne cherche l'incident qui l'aurait révélée.

⚠ Le repli a AUSSI changé de FORME : il répondait « ce passif est-il dans le kit ? » (appartenance),
il répond maintenant « le premier passif substituant du kit est-il celui-là ? » (la boucle native).
C'est plus fidèle, mais c'est un changement de comportement, donc il est **mesuré** :
les **14** clés de la table × les **683** kits = **9 562** couples évalués en mode repli,
**0 divergence** avec l'ancien prédicat — et **38** réponses VRAIES, donc le contrôle n'est pas
trivialement vide.

### 5.2 Le canal, et son coût

`snapshot.active_ability_names_by_unit` est le **foyer unique de parsing**, pendant exact de
`passive_ability_names_by_unit` : `_load_active_abilities` (COMBAT) et
`playbook.scene._seed_measured_actives` (DÉCISION) l'appellent tous les deux. Deux parsings distincts
recréeraient le fork « ce que la prédiction annonce ≠ ce que le moteur fait ».

**Coût : nul.** Le payload est celui que le seed des passifs consomme déjà (`unitAbilityStates`,
capturé une fois par runner) — aucun RPC supplémentaire.

**Rang** : identique aux passifs. Les actives de configuration sont figées au spawn, donc le COLD de
`build_predictor` suffit et `refresh_shields` ne les re-seede que pour les **arrivants**.

## 6. Ce que la garde éprouve — et qu'elle ROUGIT

`tests/engine/test_419r1tr14r5r2_active_normal_attack_live.py`, **6 crans** : la taille de la table
(cran OFFLINE), l'entrée contre le natif, la priorité de la cascade avec son témoin et son contrôle,
le port sur les **canaux de production** (donc la chaîne entière : capteur, parsing, seed, foyer), la
contre-épreuve, et les deux bras MoW.

**Éprouvée par MUTATION DU CODE LIVRÉ**, motif vérifié avant écriture à chaque fois :

| mutation | rouges | ce que le message accuse |
|---|---|---|
| entrée de la table ACTIVE retirée | **2 failed** / 4 passed | `('preuve', 'astraBullgryn', natif `RogalDorn_NormalAttack`, port `Loki_NormalAttack`)` |
| priorité de la cascade INVERSÉE (active avant passive) | **1 failed** / 5 passed | `('borne', 'orksNob', natif `Boltstorm_NormalAttack`, port `RogalDorn_NormalAttack`)` |
| restauration (fichier vérifié identique) | **6 passed** | — |

La seconde mutation est ce qui établit que le bras BORNE **n'est pas dégénéré** : les deux modèles y
coïncident sur la table, mais pas sur l'ORDRE, et c'est lui qui l'attrape.

⚠ La première tentative de mutation a été **refusée par son propre garde** (motif introuvable :
séparateurs CRLF). Un patch qui ne matche pas rend VERT — le contrôle « motif trouvé avant
exécution » est ce qui a évité de lire ce vert comme une mesure.

## 7. Tests rejoués (54 verts, 0 rouge)

| fichier | verdict |
|---|---|
| `test_419r1tr14r5r2_active_normal_attack_live.py` (neuf) | 6 passed |
| `test_419r1tr14r5_normal_attack_dispatch_live.py` (le foyer touché) | 6 passed |
| `test_419r1tr14r5_r1r4_normal_attack_table_live.py` (la table jumelle) | 9 passed |
| `runner/test_mv71_sniper_drone_live.py` (le prédicat threadé) | 5 passed |
| `runner/test_363_ability_states_default_live.py` (le canal consommé) | 10 passed |
| `test_446_r1_boltstorm_followup_live.py` | 5 passed |
| `test_446_r3_repugnance_followup_live.py` | 5 passed |
| `test_419r1tr14_heavy_bolt_pistol_live.py` | 6 passed |
| `runner/test_damage_roll_live.py` (garde COMBAT) | 2 passed |
| `runner/test_skitarii_turn_live.py` (la face OFFLINE) | 3 passed |
| `test_419r1tr13_shrapnel_live.py` | 7 passed |
| `test_419r1tr12_electro_shock_live.py` | 7 passed |

## 8. Ce qui n'est PAS couvert

* **Un seul cran de prédiction.** Le volet `pred` mesure une tuile à distance `(0,2)`. L'invariance
  du dégât n'est donc établie que sur ce régime ; elle n'a pas été mesurée en mêlée. Le raisonnement
  décompilé (même base `ADeprecatedActiveAbility`, aucun `PredictAttack` propre, même playbook
  générique) porte au-delà, mais **la mesure, non**.
* **Le canal est un SUR-ENSEMBLE**, et son contrôle vaut pour la clé `1124` **seule**. Une entrée
  ajoutée à la table ACTIVE devra refaire le contrôle du §3.2 pour SA clé. Le cran (1) de la garde
  rougit précisément pour forcer ce passage.
* **La face COMBAT de la voie active** n'a pas de bras dédié. Le prédicat y est threadé (`damage.py`),
  mais l'unique valeur de la table n'a pas de classe portée côté runner, donc aucun chemin porté ne
  la consomme — il n'y a rien à mesurer aujourd'hui.
* **Aucun chiffre de coût dédié** n'a été pris pour le seed des actives. Il ne coûte aucun RPC (même
  payload que les passifs) et son travail Python est un parcours de liste, mais ce n'est pas mesuré.

## 9. Résidus NOMMÉS

* **`#419-r1-tr14-r5-r2-r1` — la branche TRAIT `0x7e7` — FERMÉ (2026-08-04),
  `case-419-r1-tr14-r5-r2-r1-branche-trait.md`.** Troisième substitution de la même cascade,
  `else if (config.Traits.Contains(0x7e7)) { type = 0x406; state = activeAbilityState; }` — soit
  `2023 Boss` → `1030 Loki_NormalBossAttack`, littéraux qualifiés enum par enum. Portée à son RANG et
  confrontée 8/8 par montage écrit sur `BC.Units[].Traits`, dont deux bras où le trait COEXISTE avec
  une source de rang supérieur. Elle a ouvert deux résidus, dont **`-r2-r1-r1`** : le gate
  `ShouldExecute` (`!HasTriggeredAbility(target, 0x48 Explosive)`) est le SEUL différentiel de
  décision entre `69` et `1030`, et il n'est porté d'aucun côté.
* **`#419-r1-tr14-r5-r2-r2` — la garde `FilterNewList` du repli générique n'est pas portée.**
  Toujours le même `else` : avant de poser l'attaque normale générique, la fabrique filtre la
  collection de l'`ActiveAbilityComponent` (`comp@+0x20`) par un `Func` statique mis en cache et
  **rend sans rien ajouter** si le résultat est non vide (`if (0 < list.Count) return;`). Le port ne
  modélise pas ce court-circuit. Le prédicat du `Func` n'a pas été lu — c'est le premier geste à
  faire pour ouvrir ce résidu.
* **`#419-r1-tr14-r5-r3` reste ouvert** (branche TERTIAIRE de la voie passive) — inchangé par cette
  tranche, et sans équivalent côté ACTIVE : la voie active s'arrête à sa boucle.

## 10. Livré

* `scripts/python/engine/services/custom_normal_attack.py` — la table ACTIVE, la boucle, la cascade,
  le repli séparé par voie.
* `scripts/python/engine/entities/unit_context.py` — `active_abilities` (tri-état).
* `scripts/python/engine/runner/snapshot.py` — `active_ability_names_by_unit` (parsing partagé) +
  `_load_active_abilities` + `seededActives` dans la trace du seed.
* `scripts/python/engine/playbook/scene.py` — `_seed_measured_actives` + appels COLD et arrivants.
* `scripts/python/engine/playbook/prediction/normal_attack.py`,
  `scripts/python/engine/runner/abilities/loki/mv71.py`,
  `scripts/python/engine/runner/operations/damage.py` — la seconde liste threadée jusqu'au prédicat.
* `scripts/python/engine/ai/context.py` — le commentaire de `normal_ids = set()` réécrit sur la
  lecture native (§4).
* `scripts/python/probe_419r1tr14r5r2_active_normal_attack.py` — quatre volets, contre-épreuve.
* `scripts/python/tests/engine/test_419r1tr14r5r2_active_normal_attack_live.py` — 6 gardes.
