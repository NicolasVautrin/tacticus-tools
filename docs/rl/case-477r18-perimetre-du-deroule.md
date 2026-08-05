# #477-r18 — le périmètre du DÉROULÉ DE BATAILLE dans le flux de replay

**INVENTAIRE, rien de porté.** Build `rnca9r7q6c`, ghidra-mcp sur le binaire installé, session Frida
**9**. Probe : `scripts/python/probe_477r18_deroule_perimetre.py` (deux volets : statique
`--json`, live `--flux-live`). Flux témoin conservé : `logs/477r18-flux-C1_02.txt`.

## Verdict en une ligne

Le déroulé n'est **pas** un chantier de mécanique — elle est déjà portée. C'est un chantier
d'**ANCRAGE** : les 15 groupes RACINES sont tous ouverts par `IdunBattle.Messages.InputMessageProcessor`,
la seule couche du chemin qui n'existe **nulle part** dans `engine/`. Et la première tranche est
**`User_PlaceUnit`** : **10,1 %** du flux pour **+1 `GroupType`, +0 `StepType`, +0 `TagKey`**.

## 1. Le périmètre, dérivé — trois canaux, aucun énuméré à la main

L'émetteur natif est `IdunBattle.Streams.IStreamListener` (slots **0/1/2** =
`StartGroup`/`FinishGroup`/`Action`). En IL2CPP l'appel passe par un helper
`FUN_*(<slot>, <Il2CppClass* de l'interface>, <this>, <args…>)` : le probe **dérive** ce
`Il2CppClass*` de deux témoins et refuse de continuer s'ils ne concordent pas.

| canal | ce qu'il rend |
|---|---|
| **1** — xrefs du `Il2CppClass*` de `IStreamListener` | **386** sites, **133** fonctions productrices |
| **2** — xrefs de `IdunBattle.Core.AOperation$$get_Events` (indépendant) | **77** fonctions, **toutes** incluses dans le canal 1 ; 56 en plus côté canal 1 |
| **3** — méthodes dont la **signature** déclare le type (lu dans `frida/methods.tsv`) | **32** porteuses de `GroupType`, **20** de `StepType` |

Vocabulaire atteint par un littéral **lu** : `GroupType` **35 / 104**, `StepType` **54 / 62**,
`TagKey` **115 / 244**.

**Les 69 `GroupType` restants ne sont pas morts — ils sont DÉCLARATIFS.** Ils ne passent par aucun
call-site du flux : une ability les pousse au nœud DSL
`IdunBattleLogic.Entities.DSLBehaviors$$AtomicGroup(groupType, …)`. Témoin lu :
`IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$ExecuteBehaviour` passe
`0x4e` = `GroupType.FrenziedFiring`. Il y a **3** surcharges homonymes d'`AtomicGroup` et **2** de
`Group` — `list_xrefs` par NOM rend une erreur sur un nom ambigu, donc « 0 appelant » : le probe
interroge par **adresse**.

**Ce que la mesure ne voit pas**, imprimé à chaque run : les arguments portés par une variable
(propagés d'**un** cran, pas plus), les corps trop gros pour le budget de décompilation (deuxième
tentative large), les porteurs sans symbole Ghidra.

## 2. La structure : un groupe RACINE = un message d'entrée

Les 15 `System_*` / `User_*` sont ouverts par les lambdas de
`IdunBattle.Messages.InputMessageProcessor$$Visit` — **14 sur 15** ont leur producteur lu
(`User_RemoveUnit` seul n'en a aucun). Tout le reste (`StartTurn`, `EndTurn`, `Damage`,
`Effect_Refresh`, `Ability_Power`…) est ouvert par des **Operations**.

Séquence mesurée d'une transition de tour, dans l'ordre :

```
User_EndTurn -> EndTurn -> Action=PrepareTurn (HORS groupe) -> StartTurn
```

⚠ **Une `Action=` existe à profondeur 0**, hors de tout groupe : `PrepareTurn` après chaque
`EndTurn`, `ChangeStats` après chaque `User_MoveUnit`. **29** lignes du flux témoin sont dans ce cas.

## 3. Le poids MESURÉ, et le classement qui en découle

`C1_02`, seed 777, 2 tours d'IA : **2 777** lignes, **116 459** octets, reproductible à l'octet.
Le déploiement déjà porté en représente **423** (15,2 %). « NOUVEAU » = ce que le groupe ajoute
au vocabulaire **déjà exercé par le déploiement**. **Deux boards** — un seul ne prouverait rien :
sur `MC1_67` (63 tuiles), le déploiement passe à **535** lignes sur **2 931**, mais
`User_PlaceUnit` reste à **281** lignes et **+1 / +0 / +0**.

| groupe racine | occ | lignes | NOUVEAU G/S/T | mécanique portée ? |
|---|---:|---:|---|---|
| `User_UseAbility` | 5 | 564 | +6 / +6 / +31 | oui (`active_ability.py`, `damage.py`) |
| `System_StartMatch` | 1 | 477 | +4 / +8 / +18 | partiel |
| `System_GameSetup` | 1 | 423 | — | **FAIT** |
| `User_MoveUnit` | 10 | 303 | +3 / +6 / +12 | oui (`movement.py`) |
| **`User_PlaceUnit`** | **5** | **281** | **+1 / +0 / +0** | **oui — c'est le MÊME `AddUnit` que le setup** |
| `StartTurn` | 4 | 274 | +3 / +6 / +7 | oui (`turnflow.py`) |
| `EndTurn` | 4 | 180 | +3 / +7 / +10 | oui (`turnflow.py`) |
| `System_ProcessDeaths` | 3 | 133 | +5 / +7 / +30 | oui (`damage.py`, `remove_unit.py`) |
| `Ability_Power` | 1 | 51 | +2 / +3 / +3 | oui (`effect_triggers.py`) |
| `User_EndTurn` | 2 | 50 | +2 / +2 / +2 | oui (`turnflow.py`) |
| `Effect_Refresh` | 1 | 6 | +1 / +2 / +1 | oui (`refresh_effects.py`) |
| `System_ProcessRemovals` | 3 | 6 | +1 / +0 / +0 | groupe **VIDE** |

**Le classement demandé** : la mécanique de **tous** les groupes du déroulé est déjà dans
`engine/` — sur les 131 producteurs natifs, **44** sont cités par leur symbole exact dans
`engine/`, **13** par leur classe. Les **74** absents sont, pour l'essentiel, les lambdas
d'`InputMessageProcessor` (l'ancrage) et des opérations hors combat (drafting, score, portes,
territoire). Il n'y a **aucun** groupe du déroulé dont l'opération native serait à porter de zéro.

⚠ `Effect_Refresh` est le motif **transversal** : il apparaît imbriqué dans presque tous les
groupes racines. Le porter tôt paie partout.

## 4. `Source=` — tranché par le PRODUCTEUR, ni par le nom ni par le groupe

Sur le flux témoin : **68** valeurs distinctes, **67** non vides (le déploiement seul n'en montrait
que 8). **Toutes** tombent dans un mirror déjà présent — il n'y a **aucune** source orpheline.

| groupe | sources distinctes | ce que le producteur LIT |
|---|---:|---|
| `Effect_Refresh` | 39 | `EffectComponent.EffectType` **@0x58** — `IdunBattle.Operations.RefreshEffectsOperation$$GenerateEventGroup`, puis `System.Enum$$ToString` |
| `Ability_Power` | 31 | **TROIS producteurs, trois types** (ci-dessous) |
| `User_UseAbility` | 3 | l'`ActiveAbilityType` du cast |

⚠ **Le nom ne discrimine pas** : **12** des 31 sources d'`Ability_Power` sont des membres valides
de **plusieurs** enums à la fois (`Ambush`, `BigTarget`, `TeleportStrike`, `TerminatorArmour`…).
⚠ **Le groupe non plus** : `Ability_Power` est ouvert par **trois** producteurs distincts, et
chacun boxe un type différent —
`EvaluateTriggerOperation$$EvaluateEffectTriggerTargets` lit `EffectComponent@0x58` (`EffectType`,
même `Il2CppClass*` que `RefreshEffectsOperation`), tandis que
`TriggerTriggeredAbilityOperation$$TriggerAbility` et
`EvaluateTriggerOperation$$EvaluateAbilityTrigger` boxent un **autre** `Il2CppClass*`, alimenté par
des porteurs nommés `abilityName` / `sortedTriggeredAbility` (`TriggeredAbilityType`).

⇒ **L'unité d'attribution est le SITE, pas le groupe.** Les mirrors existent tous
(`engine/entities/effect_type.py`, `active_ability_type.py`, `triggered_ability_type.py`) et
`format_enum_value` fait déjà le rendu : **`Source=` n'est un mur pour aucun groupe du déroulé** —
le travail est de lire, site par site, le champ que le producteur boxe.

## 5. Le flux ne nomme pas le kit — non bloquant pour COMPARER

`#477-r17` reste vrai : aucun `visualId`. Mais l'`Entity=` est un discriminant **exact** et le
port l'apparie déjà (`observeBattle.units[].squadId`, mesuré 5/5 par `#477-r15`). Conséquence
réelle : ça ne gêne pas l'**égalité**, seulement la **lecture d'un rapport de divergence**. La
parade est côté rapporteur (joindre l'appariement `Entity= -> unitId` déjà disponible), pas côté
émetteur.

## 6. La PREMIÈRE TRANCHE — `User_PlaceUnit`, et son critère écrit à l'avance

**Pourquoi elle** : son contenu est un `Group=AddUnit` **strictement identique** à celui que le
port émet déjà dans `System_GameSetup` (tranches A + D). Le seul manque est l'**enveloppe**.
Mesuré : **281 lignes** (10,1 % du flux) pour **+1 `GroupType`** et **aucun** `StepType` ni `TagKey`
nouveau. C'est le meilleur rapport lignes-gagnées / vocabulaire-neuf du tableau, d'un facteur
**deux** sur son suivant.

Forme exacte, lue au flux :

```
Group=User_PlaceUnit Entity=NO_ENTITY Source= InitialTarget=
    Group=AddUnit Entity=59 Source= InitialTarget=
        Action=AddUnit Entity=59            (6 tags, dont Unit_SpawnSource:5)
        Action=ChangeStats Entity=59        (16 tags)
        Action=ChangeAbility Entity=59      (x4)
    Finish_Group
Finish_Group
```

**Critère de réussite, écrit AVANT** :

1. sur `C1_02` **et** `MC1_67` (tailles différentes), les **5** groupes racines `User_PlaceUnit`
   sont reproduits à l'**égalité BRUTE** ligne à ligne ; registre de divergences **VIDE** ;
2. la borne (a) republiée montre `GroupType` **2 → 3 / 104**, `StepType` **6 / 62** et `TagKey`
   **36 / 244** **inchangés** — si l'un des deux derniers bouge, c'est que la tranche a débordé ;
3. contre-épreuve, chaque mutation devant **rougir** : enveloppe supprimée ; `Entity=` du groupe
   racine ≠ `NO_ENTITY` ; `Unit_SpawnSource` faux ; ordre des cinq unités inversé ;
4. ce qui n'est **PAS** couvert est nommé : la valeur de `Unit_SpawnSource` hors du montage
   `rl_duel build`, et le fait qu'un `User_PlaceUnit` de partie réelle puisse contenir autre chose
   qu'un `AddUnit`.

**Crans suivants, dans l'ordre du tableau** : `System_ProcessRemovals` (groupe vide, +1 `GroupType`,
prouve l'ancrage temporel sans aucune donnée), puis `Effect_Refresh` (motif transversal, +1/+2/+1),
puis `User_EndTurn` (+2/+2/+2), qui l'englobe.

## Résidus

- **#477-r18-r1** — **le troisième `Il2CppClass*` boxé par `EvaluateTriggerOperation$$EvaluateAbilityTrigger`
  n'est pas nommé.** Cette fonction fait **trois** `Enum.ToString` sur **deux** types différents ; le
  second n'a été rattaché à aucun mirror. Condition de retournement : nommer ce `Il2CppClass*` (par
  un autre site qui l'initialise et appelle une méthode de la classe), puis vérifier que les sources
  qu'il produit sont bien celles du flux.
- **#477-r18-r2** — **`GroupType.User_RemoveUnit` n'a aucun producteur lu**, alors que les 14
  autres racines en ont un. Condition de retournement : trouver la surcharge de
  `InputMessageProcessor$$Visit` qui l'ouvre, ou établir qu'aucune ne le fait (dead code).
- **#477-r18-r3** — **les 69 `GroupType` déclaratifs ne sont pas ventilés par ability.** Le canal 3
  établit la voie (`DSLBehaviors$$AtomicGroup`) et la lit sur un témoin ; il ne l'a pas balayée
  exhaustivement. Condition de retournement : lire les littéraux chez tous les appelants des
  5 surcharges `AtomicGroup`/`Group`, et confronter le compte au nombre de membres restants.
