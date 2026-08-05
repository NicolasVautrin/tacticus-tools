# #477-r22 — le BLOC 2 de `System_StartMatch` : le TOUR, et sa RÉCOLTE hors du groupe

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp, session Frida **1** (chaude, aucun reinject).
Le port reproduit à l'**égalité brute** **29 / 29** couples `Action=PrepareTurn` + `Group=StartTurn`
sur **cinq** scénarios, **1 193 lignes** égales. **24 des 29 sont HORS du groupe
`System_StartMatch`** — c'est la mesure que la tranche devait rendre, et elle est **mesurée, pas
déduite d'une ventilation**.
Sur le roster 2v2 crafté, `System_StartMatch` devient **INTÉGRALEMENT porté : 142 / 142 lignes**.

```powershell
python scripts/python/probe_477r22_turn_phase.py            # live, 3 scenarios
python -m pytest scripts/python/tests/engine/test_477r22_turn_phase_offline.py -q
```

## 1. La RE — de `StartMatchOperation` jusqu'aux deux émissions

La chaîne est fermée de bout en bout, chaque maillon étant une fonction **nommée** :

```
IdunBattle.Operations.StartMatchOperation$$Execute
  processor.<slot 0x2f>(RefreshEffectOptions{8, null});          -- AVANT ContinueTurnPhase
  ... le groupe RarityCapTransform, conditionnel (#477-r23) ...
  processor.<slot 0x16>(TurnStage.Start /*3*/, forceEndTurn: false, isManual: true);
-> Core.Services.OperationProcessor$$ContinueTurnPhase
-> IdunBattle.Operations.ContinueTurnPhaseOperation$$Execute        <- la BOUCLE
     turn.<+0x14> = requested;  while (GetNextTurnStage() is T) HandleNextTurn(T, ...)
-> IdunBattle.Entities.Components.TurnComponent$$GetNextTurnStage
     +0x14 != +0x10 ? Nullable(EnumExt.NextValueOrFirst(+0x10)) : null
-> IdunBattle.Operations.ContinueTurnPhaseOperation$$HandleNextTurn  <- les GARDES d'etat
-> IdunBattle.Operations.ContinueTurnPhaseOperation$$ExecuteStage    <- le SWITCH
     0 Change  -> <slot 0x17> ChangeTurnOperation$$Execute      -- n'ecrit RIEN dans le flux
     1 Prepare -> <slot 0x18> PrepareTurnOperation$$Execute     <- `Action=PrepareTurn`
     2 Draft   -> <slot 0x19> (non identifie)                   -- rien sur le regime confronte
     3 Start   -> <slot 0x1c> StartTurnOperation$$Execute       <- `Group=StartTurn`
     4 End     -> <slot 0x1d>(!forceEndTurn) EndTurnOperation$$Execute
```

`ContinueTurnPhase(Start)` depuis `Change` traverse donc **Prepare, Draft, Start** — et c'est ce
qui met `Action=PrepareTurn` juste avant `Group=StartTurn`, sans rien entre les deux.

### Les deux émissions, lues verbatim

```
PrepareTurnOperation$$Execute
    tags.Add(TagKey.Match_CurrentPlayerId /*0x9d*/, TurnComponent.get_CurrentPlayerId(turn));
    tags.Add(TagKey.Match_PreviousPlayerId /*0x9e*/, turn.<+0x18>);
    tags.Add(TagKey.Match_AmountOfTurnsStartedByCurrentPlayer /*0x9f*/,
             TurnComponent.GetAmountOfTurnsStartedByCurrentPlayer(turn));
    Events.Action(StepType.PrepareTurn /*0x26*/, GetMatchEntity(state).<Id>, tags);

StartTurnOperation$$Execute
    Events.StartGroup(GroupType.StartTurn /*0x2f*/, GetMatchEntity(state).<Id>,
                      "" /*litteral d'index 0*/, default(BEntityId?));
    tags.Add(TagKey.Match_PreviousPlayerId /*0x9e*/, turn.<+0x18>);
    Events.Action(StepType.StartTurn /*2*/, GetMatchEntity(state).<Id>, tags);
    processor.<slot 0x2f>(refreshOptions);
    processor.<slot 0x4d>(EventTriggerType.TurnStart_EffectActivation /*0x12*/, entities);
    ... TurnStart_Other, TurnStart_EnvironmentEffects, TurnStart_DelayedAttacks, TurnStart_Actions
    processor.<slot 0x21>();
    Events.FinishGroup();
```

Les trois `Add` de `PrepareTurn` sont **inconditionnels** (aucun `if` entre le ctor du dictionnaire
et l'appel) — l'inverse de `StreamHelper$$GetRefreshEffectTags`, dont six tags sur onze sont gardés.

### Quatre lectures qui n'auraient pas été devinables

**(a) `TurnComponent+0x18` est le joueur PRÉCÉDENT — lu dans `SetCurrentPlayer`.**
`IdunBattle.Entities.Components.TurnComponent$$SetCurrentPlayer` écrit, dans cet ordre,
`this.<+0x24> = nextPlayerId` puis `this.<+0x18> = <l'ancien CurrentPlayerId>`. Le nom du tag
(`Match_PreviousPlayerId`) et la lecture du setter concordent : deux canaux natifs distincts.

**(b) Les noms Ghidra des deux setters de stage sont FAUX, et seuls les OFFSETS comptent.**
`TurnComponent+0x10` (stage COURANT) et `+0x14` (stage DEMANDÉ) ont des setters triviaux
(`mov [rcx+off], edx ; ret`) qu'IL2CPP **déduplique** : Ghidra les nomme
`VoxelBusters.CoreLibrary.NativePlugins.DateComponents$$set_Year` (écrit `+0x14`) et
`CenterSpace.Free.MersenneTwister$$set_Count` (écrit `+0x10`). C'est le pendant exact de
l'avertissement du CLAUDE.md sur l'ABSENCE dans les tables — ici c'est une **PRÉSENCE trompeuse**.

**(c) `NextValueOrFirst` avance par INDICE, pas par `+ 1` sur l'ordinal.**
`Idun.Shared.Extensions.EnumExt$$NextValueOrFirst<T>` fait
`values.GetValue((Array.IndexOf(values, v) + 1) % values.Length)`. Les deux coïncident sur
`TurnStage` (0..4 contigus) mais pas en général ; et le `OrFirst` du nom est le cas `IndexOf == -1`,
qui rend le PREMIER membre.

**(d) Le `Source=` vide est un LITTÉRAL, pas `String.Empty`.**
Quatrième `Source=` vide de ce dossier, mais la première dont la **lecture** diffère : les trois
précédents passaient le premier champ statique de `System.String` ; ici le décompilé passe un slot
de littéral, que `data/symbols/<build>/metadata/string_literals.tsv` résout — **index 0, valeur
`""`**. Le même slot sert au `Group=RarityCapTransform`. La valeur émise est identique ; la lecture,
non.

### Ce qui est LU et volontairement NON porté

- **Les gardes de `HandleNextTurn`**, qui peuvent ARRÊTER la boucle avant `Start` :
  `match.<+0x24> == 2` (match terminé), et surtout
  `turn.<+0x10> == TurnStage.Draft && DraftingComponent.get_IsPendingDraftingDecision(...)`, qui
  rend `false` sans rien émettre quand `forceEndTurn` est faux. Un montage avec drafting en attente
  n'aurait **pas** de `Group=StartTurn` — résidu **#477-r22-r2**.
- **La branche `nextTurnStage == Prepare`** de la même fonction : elle n'appelle `ExecuteStage` que
  si l'une des quatre conditions lues est vraie. `StartMatchOperation` passe `isManual: true` **en
  dur**, ce qui la rend vraie — c'est ce littéral qui garantit l'émission de `Action=PrepareTurn`.
- **`forceEndTurn`**, lu par la seule branche `End` (`<slot 0x1d>(!forceEndTurn)`), non portée.
- **Le CONTENU du groupe** : le `RefreshEffects` du slot `0x2f`, les CINQ
  `EvaluateAbilities(TurnStart_*)` du slot `0x4d`, et le slot `0x21` — dont le flux montre qu'il
  produit les `Action=ChangeStats` / `Tag=UnitStats_ActionsAvailable` de fin de groupe. Le slot
  `0x21` n'est **pas identifié** : l'ordre des slots d'une interface IL2CPP ne se lit nulle part
  hors du metadata (mesure de contrôle : **0** méthode déclarée par
  `Core.Services.IOperationProcessor` dans les 121 502 lignes de `frida/methods.tsv`). Il est laissé
  NON IDENTIFIÉ plutôt que deviné.

### Le slot `0x2f`, établi par la TAILLE de son argument

`OperationProcessor` porte deux `RefreshEffects`. Le call-site passe une struct de **16 octets**
par référence. `classes.tsv` publie la taille **boxée** : `IdunBattle.Operations.RefreshEffectOptions`
= 32 − 16 = **16**, `IdunBattle.Core.EffectRefreshEvent` = 24 − 16 = **8**. C'est donc
`RefreshEffects(refreshOptions: RefreshEffectOptions)` — établi, pas deviné. Même méthode pour le
slot `0x4d` : `EvaluateAbilities(trigger, entities: AbilityEntities)`, arité 2 dont une struct de
312 − 16 = **296** octets, exactement ce que le décompilé recopie.

## 2. Le résultat, mesuré

| scénario | flux | groupe | BLOC 2 | couples | conformes | dont **HORS** groupe | lignes égales |
|---|---:|---:|---:|---:|---:|---:|---:|
| `C1_02`, 2 tours | 2 776 l. | 477 l. | 27 l. | 5 | **5** | **4 / 4** | 279 |
| `MC1_67`, 2 tours | 2 930 l. | 521 l. | 27 l. | 5 | **5** | **4 / 4** | 261 |
| `MC1_67`, **roster 2v2 crafté** | 1 169 l. | 142 l. | **8 l.** | 5 | **5** | **4 / 4** | 112 |
| `C1_02`, **6 tours demandés (4 joués)** | 4 502 l. | 477 l. | 27 l. | 8 | **8** | **7 / 7** | 493 |
| `C1_02`, **roster 1v1 crafté** | 623 l. | **65 l.** | **8 l.** | 6 | **6** | **5 / 5** | 48 |
| **total** | | | | **29** | **29** | **24 / 24** | **1 193** |

La découpe du groupe est confrontée à chaque run — `1 + 1 + bloc1 + bloc2 + 1 == total`, **OK sur
5 / 5** — et le probe **exige** que la QUEUE de #477-r21 soit **exactement** le couple : si
`StartMatchOperation` émettait quoi que ce soit après `ContinueTurnPhase`, les deux différeraient.

**Couverture du groupe `System_StartMatch`**, en cumulant les trois crans :

| | avant (#477-r21) | après (#477-r22) |
|---|---:|---:|
| `C1_02` | 366 / 477 | **389 / 477** |
| `MC1_67` | 395 / 521 | **418 / 521** |
| roster 2v2 | 134 / 142 | **142 / 142 — INTÉGRAL** |

## 3. La RÉCOLTE — la mesure que la tranche devait rendre

> **24 des 29 couples sont HORS du groupe `System_StartMatch`, et les 24 sont reproduits.**

C'est **mesuré couple par couple**, jamais déduit : le probe parcourt le flux ENTIER, résout le
groupe racine de chaque `Group=StartTurn` par la pile, et confronte chacun. La cause est
structurelle et lue : `Group=StartTurn` n'a **qu'un** producteur dans le binaire
(`StartTurnOperation$$Execute`), atteint par le **même** slot `0x16` avec les **mêmes** trois
arguments depuis `StartMatchOperation$$Execute` et depuis la lambda
`InputMessageProcessor$$u003CVisitu003Eb__20_0` de `Visit(StartTurnMessage)`.

⚠ **Le « 26 » cité au dispatch ne compte PAS des `Group=StartTurn`.** Il vient de la ventilation de
#477-r19-r2 — « 147 `Effect_Refresh` répartis sur 9 groupes racines, dont `StartTurn` 26 » : ce sont
des **`Effect_Refresh` dont la racine est un `StartTurn`**. Les `Group=StartTurn` eux-mêmes sont bien
moins nombreux : **5** sur le même flux (`C1_02`, 2 tours), dont 4 hors du groupe. Confondre les deux
surestime la récolte d'un facteur 5. Le probe mesure donc **les deux** grandeurs :

| | `C1_02` | `MC1_67` | 2v2 |
|---|---:|---:|---:|
| `Group=StartTurn` reproduits, hors `System_StartMatch` | **4 / 4** | **4 / 4** | **4 / 4** |
| `Effect_Refresh` reproduits **dans les couples** | **28** | **26** | **8** |
| `Effect_Refresh` **AUTONOMES** | **0** | **0** | **0** |

Le second chiffre est celui qui répond à #477-r19-r2 : les `Effect_Refresh` que la racine `StartTurn`
enveloppe deviennent reproductibles. Le troisième reste **0**, mesuré et non déduit — il y faudrait la
SÉLECTION (`#477-r21-r2`) et l'ALLOCATION ECS des identifiants (`#477-r21-r3`), qui ne sont ni l'un ni
l'autre une face stream.

## 4. Ce qui est MESURÉ, et ce qui est COPIÉ

Le port émet une **forme** à partir de **données**. Les données viennent du flux : elles comptent en
borne (c) **sans rien prouver**. Ce qui est mesuré est ce que le port **dérive** — et chaque
dérivation publie son compte d'exercice :

| | dérivation | `C1_02` | `MC1_67` | 2v2 | 4 tours | 1v1 |
|---|---|---:|---:|---:|---:|---:|
| (D1) | séquence des stages : départs **compatibles** sur les 5 possibles | 2 | 2 | 2 | 2 | 2 |
| (D2) | tags de `PrepareTurn` hors ordre alphabétique ; `current != previous` | 5 ; 5 | 5 ; 5 | 5 ; 5 | 8 ; 8 | 6 ; 6 |
| (D3) | les TROIS entités coïncident | 5/5 | 5/5 | 5/5 | 8/8 | 6/6 |
| (D4) | `Group=StartTurn` **sans contenu** vs avec | 0 / 5 | 0 / 5 | **1** / 4 | 0 / 8 | **2** / 4 |
| (D5) | `Source=` et `InitialTarget=` vides | 5/5 | 5/5 | 5/5 | 8/8 | 6/6 |

**(D1) est la dérivation centrale, et elle RÉFUTE.** Le port reçoit deux entiers (`TurnStage`
courant et demandé) et calcule les étages traversés. Le probe balaie les **cinq** départs possibles
et publie lesquels produisent le texte natif : **3 sur 5 sont réfutés** (`Prepare` et `Draft`
suppriment l'`Action=PrepareTurn` ; `Start` ne produit RIEN). Restent `Change` et `End`,
**indiscernables par le flux** parce que le stage `Change` n'émet pas — et c'est publié, pas tu.

**(D4) est ce que le roster crafté apporte, et c'est l'axe qui compte ici.** Un `Group=StartTurn`
**sans aucun contenu** existe (1 sur le 2v2, 2 sur le 1v1) : c'est exactement le régime où
`RefreshEffectsOperation$$GenerateEventGroup` n'écrirait **rien** (`if (eventActions.Count > 0)`,
#477-r21) alors que `StartTurnOperation$$Execute` **ouvre quand même**. Les deux groupes se
ressemblent dans le flux et se comportent à l'inverse ; ce cas-là le prouve sur le flux, pas
seulement au décompilé.

**Copié, et déclaré en borne (c)** : les identifiants d'entité ECS et de joueur ; le **stage
courant** au moment de l'appel ; la sélection et l'ordre des sous-arbres du contenu
(`#477-r21-r2`) ; les lignes hors périmètre.

## 5. Les 9 contre-épreuves — et les DEUX inerties, qui ne sont pas la même chose

`entite_prepare`, `entite_start_turn`, `valeur_previous`, `prepare_permute`,
`prepare_tag_manquant`, `tag_startturn`, `ordre_action`, `source_groupe`, `depart_prepare` —
jouées sur **chaque** couple, pas sur un seul.

⚠ **Deux mesures successives ont imposé cette forme, et la seconde a imposé le DOMAINE.**

- La première version ne mutait que le couple du bloc 2. Sur le roster 2v2 ce couple a un contenu
  **vide**, et `ordre_action` (déplacer le contenu avant l'action) n'y change **rien** : elle rendait
  `a_morde=False`, donc un verdict sans objet.
- Jouées sur tous les couples, elles passaient — jusqu'au roster **1v1**, où `ordre_action` n'a mordu
  sur **aucun** des 6 couples : non parce qu'elle serait morte, mais parce qu'aucun couple de ce
  régime n'a de contenu **porté** à déplacer.

Le probe distingue donc désormais **deux inerties**, et le domaine est **calculé depuis les
données**, jamais déclaré à la main :

| | | verdict |
|---|---|---|
| **inerte par CONSTRUCTION** | la mutation est applicable et ne change rien | **ROUGE** |
| **inerte par ABSENCE DE DONNÉE** | aucun couple du corpus n'est dans son domaine | **ATTENTION**, publiée |

Résultat : **9 / 9 OK** sur les scénarios par défaut ; `ordre_action` **HORS DOMAINE** sur le 1v1,
dit explicitement.

## 6. Ce qui n'est PAS couvert

- **Le CONTENU du `Group=StartTurn` hors des formes de #477-r21** → **#477-r22-r1**. Deux motifs
  mesurés sur tout le flux : `Action=ChangeStats` + `Tag=UnitStats_ActionsAvailable` (13 occurrences
  sur `MC1_67`), et `Group=Ability_Power` à `Action=Info` / `Tag=Custom_Data` (3).
- **Les gardes de `HandleNextTurn`** → **#477-r22-r2**. Le port exécute **chaque** stage traversé ;
  sur un montage avec drafting en attente le natif s'arrêterait avant `Start` et le port émettrait
  un `Group=StartTurn` de trop. Non atteint par nos montages (aucun drafting en duel).
- **Le slot `0x21`** : son émission est observée (`ChangeStats` / `UnitStats_ActionsAvailable`), son
  **nom** ne l'est pas. Une interface IL2CPP n'a aucun corps, donc aucune ligne dans `methods.tsv`.
- **`ChangeTurnOperation` et `EndTurnOperation`** : la première est LUE comme n'écrivant rien (aucun
  appel à `StreamDispatcher` dans son décompilé entier), la seconde n'est pas portée — et
  `execute_stage` **LÈVE** si la séquence la traverse, plutôt que d'émettre un flux amputé.
- **La surcharge `requestedTurnStage == null`** de `ContinueTurnPhase` : lue, non portée (les deux
  call-sites confrontés passent tous deux une valeur).
- **Le stage de départ** reste une entrée : `Change` et `End` sont indiscernables par le flux (§ 4).

## Résidus

- **#477-r22-r1** — **le CONTENU du `Group=StartTurn` hors des formes portées.** Deux motifs, comptés
  sur tout le flux : les `Action=ChangeStats` + `Tag=UnitStats_ActionsAvailable` du slot `0x21`
  (13 occurrences sur `MC1_67`, 13 sur `C1_02`), et les `Group=Ability_Power` à `Action=Info` /
  `Tag=Custom_Data` (3). Les premières sortent d'un slot **non identifié** ; les secondes d'un
  `Ability_Power` que #477-r21 sait ouvrir mais dont le corps (`Info`) n'est porté par rien.
  RETOURNEMENT **déjà mesuré** : sur le roster 2v2 ce résidu vaut **0 ligne** dans le bloc 2 — c'est
  une propriété du roster, pas une limite du port.
- **#477-r22-r2** — **les gardes d'état de `ContinueTurnPhaseOperation$$HandleNextTurn`.** Trois,
  toutes lues : le match terminé (`match.<+0x24> == 2`), la décision de drafting en attente au stage
  `Draft`, et les quatre conditions de la branche `Prepare`. Aucune n'est atteinte par nos montages ;
  ⚠ **ce n'est pas une face stream** — comme `#477-r21-r2`, ce résidu vit dans l'ÉTAT ECS.
