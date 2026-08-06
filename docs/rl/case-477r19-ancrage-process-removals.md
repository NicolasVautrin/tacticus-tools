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
foreach (id in list) { e = state.<Get(id)>; if (e != null) processor.<slot 0x55>(e, true); }
Events.FinishGroup();
```

⚠ **Ce slot avait d'abord été écrit `processor.RemoveUnit(e, true, keepActive)` ici — c'était
FAUX** (corrigé par `#477-r24-r1`). Le slot `0x55` est `UnregisterEntityFromTriggers`, et le site
passe **deux** arguments, pas trois. Voir § 6.

Trois points **lus**, pas déduits :

- **`entityId` n'est pas un littéral** — le décompilé caste le state en `IEntity` et lit son
  identifiant. L'expression est **caractère pour caractère la même** que celle de
  `<VerifyDeaths>b__0` qui ouvre `System_ProcessDeaths` : les deux groupes portent donc toujours
  la même entité sur un même flux. C'est un recoupement mesurable, et le probe l'exige (`1` = `1`
  sur les 3 scénarios).
- **`sourceId` = `String.Empty`** (le premier champ statique de `System.String`), même motif
  qu'au cran 1 ; `initialTarget` = `default(BEntityId?)`.
- **Le contenu est VIDE, et la raison en est STRUCTURELLE** : le seul appel de la boucle est
  `UnregisterEntityFromTriggers` (slot `0x55`), qui **n'émet aucune action de flux**. Le groupe
  `System_ProcessRemovals` est donc une enveloppe, toujours — pas « vide dans le régime
  confronté ».

  ⚠ **Ce paragraphe disait le contraire, et se trompait de deux façons à la fois.** Il attribuait
  au slot `0x55` le nom `RemoveUnit`, donc l'opération `IdunBattle.Operations.RemoveUnitOperation$$Execute`
  (`Action=RemoveUnit`, `TagKey.Unit_IsDying`, `TagKey.Unit_WasOverkilled`), et expliquait le vide
  observé par ses trois gardes de tête (`unit != null`, `EntityExtensions$$IsUnit`,
  `!UnitExtensions$$HasFlag(unit, 0x1a)`). **Le nom était faux** (`#477-r24-r1`), donc
  l'explication l'était aussi — elle sauvait une prédiction fausse par un mécanisme qui ne
  s'exécute jamais là. Les 11 occurrences vides étaient la mesure JUSTE d'un contenu qui n'existe
  pas. <!-- [phase-attribution:refute] -->

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

`engine/runner/operations/revive.py` (§ DRAIN) et `damage.py` (~l. 303) décrivaient
`RunPhase(PhaseType.ProcessRemovals /*0xd*/)` comme la phase qui appelle `Core.Services.OperationProcessor$$ReviveUnit`. <!-- [phase-attribution:refute] -->
**La lambda de la phase `0xd` est `<VerifyRemovedUnits>b__0`**, et elle appelle un slot à **deux**
arguments, contre **un seul** pour `ReviveUnit(killed)`. La phase `0xd` est celle des **retraits**.

⚠ **Ce slot avait été nommé `RemoveUnit` ici, et c'était FAUX** — corrigé par `#477-r24-r1`
(`case-477r24r1-mapping-slot-interface.md`). C'est le slot `0x55` de
`Core.Services.IOperationProcessor`, soit **`UnregisterEntityFromTriggers`**, lu dans le champ
`slot` du metadata IL2CPP. `RemoveUnit` est au slot `6` et prend **trois** arguments — l'arité du
site (2) l'excluait déjà. La lambda ne retire donc aucune unité : elle **désinscrit des triggers**
chaque entité de la file. Rien de tout cela n'émet de flux, ce qui **explique** le résidu
`#477-r19-r1` ci-dessous (« 11 occurrences, 11 vides ») sans recourir aux gardes de tête de
`RemoveUnitOperation`.

Non corrigé ici : ces fichiers portent la mécanique ECS du revive, pas la face stream, et leur
comportement n'est pas en cause — seule l'attribution du numéro de phase l'est.

→ **CORRIGÉ depuis, par `#477-r24`** (dispatché sous l'étiquette `#477-r19-r2`, numéro déjà pris
par le résidu `Effect_Refresh` ci-dessous). La correction va plus loin que le renommage :
`ReviveUnit` n'a **aucune** phase — son unique site d'invocation est la branche `else` de la garde
`pendingRevive.HasValue`, dans `IdunBattle.Operations.KillUnitOperation$$Execute`.
cf. `docs/rl/case-477r24-le-revive-na-pas-de-phase.md`.

## Résidus

- ~~**#477-r19-r1**~~ — **DISSOUS par `#477-r24-r1` : il n'y a PAS de contenu à porter.** Le
  résidu postulait un contenu (`Action=RemoveUnit` + `Unit_IsDying` + `Unit_WasOverkilled`) que
  quatre gardes auraient masqué, et cherchait le montage qui le ferait apparaître — un montage
  qui n'existe pas. La boucle appelle `UnregisterEntityFromTriggers`, qui n'émet rien : les
  **11 occurrences vides** sont le comportement natif, pas un régime dégénéré. Le port de
  l'enveloppe seule est donc **complet**, et le chercher plus loin était une chasse à un
  fantôme créé par une attribution de slot fausse. <!-- [phase-attribution:refute] -->
- **#477-r19-r2** — **`Effect_Refresh` attend un groupe racine porteur.** 0/147 atteignable
  aujourd'hui (§ 5). Débloqueur nommé : `System_StartMatch`, ou le couple `StartTurn`/`EndTurn`.
  Porte aussi la correction d'attribution de `RunPhase(0xd)` dans `revive.py` / `damage.py` (§ 6).
