# #477-r19 — `System_ProcessRemovals`, le cran d'ANCRAGE du DÉROULÉ

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp, session Frida **10**.
**Cran 3 (`Effect_Refresh`) NON LIVRÉ — non confrontable, mesuré : 0 / 147.** § 5.

```powershell
python scripts/python/probe_477r19_process_removals.py              # live, 2 boards
python -m pytest scripts/python/tests/engine/test_477r19_process_removals_offline.py -q
```

## 1. La RE — le groupe n'a qu'UN site d'émission, et il n'est pas dans `Visit`

`IdunBattle.Messages.InputMessageProcessor$$VerifyRemovedUnits` **n'a aucun appelant** : son
corps est **inliné** dans `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`. Mesure : le
`Il2CppClass*` du `<>c__DisplayClass50_0` et le pointeur de sa lambda sont référencés par
**exactement deux** fonctions — `VerifyDeaths` (l'inline) et `VerifyRemovedUnits` elle-même,
dont les deux seules xrefs sont des entrées DATA de table de méthodes. Il n'existe donc **aucun
autre** producteur de `GroupType.System_ProcessRemovals`.

La structure de `VerifyDeaths`, lue verbatim :

```
phases = state.<GetCurrentRunningPhaseCount>();
deaths = state.<les morts>;
if (state.<HasRunningPhase-like>() && phases > 1) return;
if (deaths != null) {
    if (deaths.Count > 0) { RunPhase(PhaseType.<0xc>, <VerifyDeaths>b__0, isInternalPhase: true, false);
                            processor.<0x8e>(); }
    if (phases > 1) return;
    queue = state.<les acteurs retires>;                    // `MatchState$$AddRemovedActor`
    if (queue != null) { if (queue.Count < 1) return;
                         RunPhase(PhaseType.<0xd>, <VerifyRemovedUnits>b__0, isInternalPhase: true, false); }
}
```

⚠ **Le `0xd` est un `IdunBattle.Core.PhaseType`, pas un `GroupType`** — même piège qu'au cran 1.
Le `GroupType` est le `6` que la **lambda** passe à `StartGroup`.

La lambda émet **exactement trois choses** :

```
Events.StartGroup(GroupType.System_ProcessRemovals /*6*/, ((IEntity)state).Id,
                  String.Empty, default(BEntityId?));
foreach (id in list) { e = state.<Get(id)>; if (e != null) processor.RemoveUnit(e, true, keepActive); }
Events.FinishGroup();
```

Trois points **lus**, pas déduits :

- **`entityId` n'est pas un littéral** — le décompilé caste le state en `IEntity` et lit son
  identifiant. L'expression est **caractère pour caractère la même** que celle de
  `<VerifyDeaths>b__0` qui ouvre `System_ProcessDeaths` : les deux groupes portent donc toujours
  la même entité sur un même flux. C'est un recoupement mesurable, et le probe l'exige (`1` = `1`
  sur les 3 scénarios).
- **`sourceId` = `String.Empty`** (le premier champ statique de `System.String`), même motif
  qu'au cran 1 ; `initialTarget` = `default(BEntityId?)`.
- **Le contenu est BORNÉ, pas supposé** : `IdunBattle.Operations.RemoveUnitOperation$$Execute`
  émet une `Action=RemoveUnit` (`StepType.RemoveUnit`) portant `TagKey.Unit_IsDying` et
  `TagKey.Unit_WasOverkilled` — **sauf** si l'une de ses trois gardes de tête coupe
  (`unit != null`, `EntityExtensions$$IsUnit`, `!UnitExtensions$$HasFlag(unit, 0x1a)`, ce dernier
  flag étant posé par l'opération elle-même sur toute unité qu'elle retire), ou si le
  `if (entity != null)` de la lambda coupe avant. Dans **tout** le régime confronté, le groupe
  ressort vide → l'enveloppe seule est portée (résidu `#477-r19-r1`).

## 2. L'ancrage — et la règle FAUSSE que le second board a tuée

La première version du probe **prédisait le nombre** : « une rafale de morts ⇒ un retrait ».
Sur `C1_02` elle rendait un **vert parfait** — 3 prédits, 3 réels, positions exactes.
`MC1_67` l'a réfutée **au premier run** : 3 occurrences pour **2** rafales de morts, la troisième
après un `StartTurn` **sans aucune mort en amont**. Le régime long l'a re-réfutée dans l'autre
sens : **6 rafales pour 5 retraits**.

Le décompilé le disait déjà : le garde `deaths.Count > 0` ne couvre que le `RunPhase` des
**morts** ; le bloc des retraits, lui, s'exécute dans tous les cas. Et la file qui l'arme
(`IdunBattle.Core.MatchState$$AddRemovedActor`) n'est observable par **aucun** canal.

⇒ **Le NOMBRE est une entrée (borne (c) nommée) ; ce qui se prédit, c'est le LIEU.**
`VerifyDeaths` a **trois** call-sites, qui se ramènent à **deux ancres visibles** dans le flux :

| ancre | d'où elle vient, lu |
|---|---|
| après `System_ProcessDeaths` | `RunPhase`, juste après `action.Invoke()` — donc après la clôture du groupe que la phase ouvre |
| après `StartTurn` | `VerifyTurnEnd` : `processor.<0x21>()` ; `processor.<0x20>(0, isManualTurnEnd)` (le flux de tour, qui écrit `EndTurn` **puis** `StartTurn`) ; `ProcessPendingTriggeredAbilities()` ; **`VerifyDeaths()`**. Le bloc `if (isInternalPhase == 0)` de `RunPhase` est ce même corps, inliné |

Depuis chaque ancre on avance tant que le groupe suivant n'est pas une **barrière**
(`PHASE_BARRIER_GROUPS`) : un autre message d'entrée — impossible, `Apply` n'a pas rendu la main —
ou un `StartTurn`/`EndTurn`, que `isInternalPhase: true` court-circuite. `System_ProcessDeaths`
n'en est **pas** : `VerifyDeaths` est ré-entrante, une rafale imbriquée s'intercale légitimement.

## 3. Le résultat, mesuré

| scénario | groupes racines | occurrences | égalité | ancrage | discrimination | delta vocab. |
|---|---:|---:|---|---|---|---|
| C1_02, 2 tours | 40 | 3 | **6 / 6** | 3/3 sur ancre | 7 ancres / 38 pos. (**18 %**) | +1 / +0 / +0 |
| MC1_67, 2 tours | 39 | 3 | **6 / 6** | 3/3 sur ancre | 6 / 37 (**16 %**) | +1 / +0 / +0 |
| C1_02, 4 tours | 70 | 5 | **10 / 10** | 5/5 sur ancre | 13 / 66 (**20 %**) | +1 / +0 / +0 |

**11 occurrences confrontées, toutes identiques au caractère près** :
`Group=System_ProcessRemovals Entity=1 Source= InitialTarget=` + `Finish_Group`.

Le critère écrit avant la tranche (`case-477r18` § 6) est tenu : `GroupType` **+1**,
`StepType` **+0**, `TagKey` **+0** — le delta est dérivé du **même flux natif**, pas du port.

**La discrimination est publiée parce qu'un test d'inclusion ne vaut que ce qu'elle vaut** : les
ancres couvrent ~17 % des positions possibles. Sur un ensemble large, « toutes les occurrences
sont à une ancre » serait satisfait par rien.

**Les 7 contre-épreuves rougissent, chacune après avoir MORDU** : `enveloppe` (rien émis),
`entite` (≠ entité MATCH), `source` (non vide), `contenu` (une `Action=RemoveUnit`), `garde`
(la garde `Count < 1` ignorée), `position` (décalage d'un cran), `barriere` (barrière vidée).
⚠ Sur le run qui a réfuté la règle, la mutation `garde` **n'a pas rougi** : elle ajoutait un
groupe qui **compensait** l'occurrence que le prédicteur ratait. C'est le garde du garde
(`a_mordu` + verdict séparés) qui l'a rendu visible.

## 4. Ce qui n'est PAS couvert

- **Le CONTENU du groupe** — jamais exercé : les 11 occurrences sont vides. Ce que le natif y
  mettrait est **lu** (§ 1), pas porté → `#477-r19-r1`.
- **La troisième forme d'ancre**, possible et non retenue : la branche `RunPhase` vaut pour
  **n'importe quelle** phase, donc après tout groupe racine ouvert par un `RunPhase`. La retenir
  rendrait l'ensemble admissible presque total, donc le contrôle vide. Le probe **imprime** toute
  occurrence hors ancre : c'est la condition de retournement, et elle est armée (0 sur 11).
- **Le NOMBRE d'occurrences** — entrée, pas prédiction (§ 2). Retournement : un canal qui exposerait
  `MatchState.RemovedActors`.
- **Les onze `System_*`/`User_*` de `PHASE_BARRIER_GROUPS` autres que `User_PlaceUnit`** : leur
  qualité de « groupe ouvert par un message d'entrée » est **héritée** du recensement 15/15 de
  #477-r18, pas relue ici.

## 5. Cran 3 — `Effect_Refresh` : NON CONFRONTABLE, et c'est un résultat chiffré

Mesuré avant d'écrire une ligne de code, sur le flux témoin `C1_02` (2 tours) :
**147 occurrences** d'`Effect_Refresh`, ventilées par groupe racine porteur —

| racine porteuse | occ | portée par le port ? |
|---|---:|---|
| `System_StartMatch` | 42 | non |
| `User_MoveUnit` | 27 | non |
| `EndTurn` | 26 | non |
| `StartTurn` | 26 | non |
| `User_UseAbility` | 15 | non |
| `System_ProcessDeaths` | 8 | non |
| `User_EndTurn`, `Ability_Power`, `Effect_Refresh` (racine) | 1 chacun | non |

⇒ **0 / 147** dans un groupe racine que le port émet déjà (`System_GameSetup`, `User_PlaceUnit`).
Profondeurs : `{0: 1, 1: 92, 2: 44, 3: 7, 4: 3}` — le motif est presque toujours **imbriqué**.

Il n'est donc **pas confrontable à l'égalité brute** aujourd'hui : le porter produirait du code
qu'aucun montage ne saurait exercer — un port spéculatif. **Ce qui le débloque** :
`System_StartMatch` (42/147, le plus gros gisement, et il englobe le seul `Effect_Refresh`
racine du flux), ou à défaut le couple `StartTurn`/`EndTurn` (52/147 à eux deux, et ce sont les
deux groupes qui portent déjà l'ancre (B) établie ici). → `#477-r19-r2`.

Note : `Source=` n'y est **pas** le mur — les 39 valeurs distinctes sortent toutes de
`RefreshEffectsOperation$$GenerateEventGroup` (`EffectComponent.EffectType` @0x58 →
`System.Enum$$ToString`), et `engine/entities/effect_type.py` + `format_enum_value` les rendent
déjà. Le mur est l'**enveloppe racine**, pas le vocabulaire.

## 6. Une lecture du port qu'il faut corriger — hors périmètre de cette tranche

`engine/runner/operations/revive.py` (§ DRAIN) et `damage.py` (~l. 303) décrivent
`RunPhase(0xd)` comme la phase qui appelle `Core.Services.OperationProcessor$$ReviveUnit`.
**La lambda de la phase `0xd` est `<VerifyRemovedUnits>b__0`**, et elle appelle le slot
`RemoveUnit(unit, removeEffects, keepActive)` — trois arguments, contre **un seul** pour
`ReviveUnit(killed)`. La phase `0xd` est celle des **retraits**.

Non corrigé ici : ces fichiers portent la mécanique ECS du revive, pas la face stream, et leur
comportement n'est pas en cause — seule l'attribution du numéro de phase l'est. → `#477-r19-r2`
en porte la mention ; à trancher par qui touchera ce foyer.

## Résidus

- **#477-r19-r1** — **le CONTENU de `System_ProcessRemovals` n'est pas porté.** Ce que le natif y
  écrirait est lu (`Action=RemoveUnit` + `Unit_IsDying` + `Unit_WasOverkilled`, sous quatre
  gardes), jamais observé : 11 occurrences, 11 vides. Condition de retournement : un montage où
  une unité entre dans `MatchState.RemovedActors` **sans** avoir déjà le flag `0x1a` ni avoir été
  détruite — puis vérifier que l'enveloppe, elle, reste inchangée.
- **#477-r19-r2** — **`Effect_Refresh` attend un groupe racine porteur.** 0/147 atteignable
  aujourd'hui (§ 5). Débloqueur nommé : `System_StartMatch`, ou le couple `StartTurn`/`EndTurn`.
  Porte aussi la correction d'attribution de `RunPhase(0xd)` dans `revive.py` / `damage.py` (§ 6).
