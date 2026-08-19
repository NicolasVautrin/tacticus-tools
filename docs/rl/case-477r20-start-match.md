# #477-r20 — `System_StartMatch` : l'ENVELOPPE portée, le CONTENU chiffré

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp, session Frida **1** (le host a été ré-injecté en cours
de tranche ; amorce rejoué avant tout RPC).
**Le déblocage d'`Effect_Refresh` annoncé par #477-r19 § 5 est RÉFUTÉ, chiffré : 0 / 42 et
0 / 44.** § 4.

```powershell
python scripts/python/probe_477r20_start_match.py              # live, 2 boards
python -m pytest scripts/python/tests/engine/test_477r20_start_match_offline.py -q
```

## 1. La RE — la surcharge de `Visit` n'ouvre RIEN, c'est sa LAMBDA qui ouvre

`IdunBattle.Messages.InputMessageProcessor$$Visit(message: IdunBattle.Messages.StartBattleMessage)`
mémorise le composant de match dans son propre champ (`+0x28`, relu par la garde de `RunPhase`),
construit une `Action` et appelle
`RunPhase(PhaseType.StartBattle /*0*/, action, isInternalPhase: true, isManualTurnEnd: false)`.

L'émission est dans `IdunBattle.Messages.InputMessageProcessor$$u003CVisitu003Eb__18_0`, et elle
tient en trois choses :

```
Events.StartGroup(GroupType.System_StartMatch /*4*/,
                  StateExtensions.GetMatchEntity(state).<Id>, String.Empty, default(BEntityId?));
processor.<slot 0x12>();                     // -> `Core.Services.OperationProcessor$$StartMatch`
Events.FinishGroup();
```

**La lambda n'est pas un `<>c__DisplayClass`, et c'est ce qui permet de l'apparier.** Elle ne
capture rien : son `this` est l'`InputMessageProcessor` (`+0x10` l'état, `+0x18` le processeur
d'opérations, `+0x20` le dispatcher — les champs posés par `Initialize`). Le binaire n'en porte que
**trois** de cette forme ; `<Visit>b__20_0` ouvre `System_StartTurn` et n'est référencée que par
`Visit(StartTurnMessage)`, `<Visit>b__42_0` n'ouvre aucun groupe. Le pointeur de méthode que
`Visit(StartBattleMessage)` passe au ctor de délégué n'est lu par **aucune** autre fonction.

⚠ **Le `0` de `RunPhase` est un `IdunBattle.Core.PhaseType`** — troisième occurrence du même piège
(`4` au cran 1, `0xd` au cran 2). Ici le NOM tranche et se lit :
`data/symbols/<build>/frida/enums.tsv` donne `0=StartBattle, …, 4=AddUnit, …, 12=ProcessDeaths,
13=ProcessRemovals`. **Les trois crans concordent** — et cette lecture **confirme** `case-477r19`
§ 6 : la phase `0xd` est bien celle des RETRAITS, pas celle du revive (correction d'attribution de
`revive.py` / `damage.py` toujours à faire, hors périmètre de cette tranche, cf. § 6).

⚠ **`isInternalPhase: true` a une conséquence visible** : le bloc `if (isInternalPhase == 0)` de
`RunPhase` — celui qui appelle `VerifyAutomaticTurnEnd` puis `VerifyDrafting` — est
court-circuité. Ce qui suit malgré tout l'invocation (`VerifyDeaths`, `ProcessDamageEvents`,
`ProcessPendingTriggeredAbilities`) s'exécute **après** le `FinishGroup`. Le `Action=PrepareTurn`
et le `Group=StartTurn` que le flux montre **dedans** ne viennent donc pas de là.

### Le slot `0x12` — établi par RECOUPEMENT, et il est fermé

Les méthodes d'une **interface** n'ont aucun corps, donc aucune ligne dans `frida/methods.tsv`
(indexée par adresse) : l'ordre des slots de `Core.Services.IOperationProcessor` ne se **lit**
nulle part hors du metadata. L'ordre du dump de la **classe** ne le donne pas non plus.

⚠ **Ce paragraphe justifiait cela par un « décalage non constant » entre le slot et une
« position » dans la classe — la comparaison était SANS OBJET, et elle a produit une fausse
contradiction avec `case-477r24`** (résolue par `#477-r24-r1`,
`case-477r24r1-mapping-slot-interface.md`). Les deux ordres ne sont liés par rien, et la
« position » n'est même pas définie : `frida/methods.tsv` perd les surcharges à corps dédupliqué.
Les slots cités ici sont **exacts** — `0x12` = `StartMatch` (0 argument), `0x16` =
`ContinueTurnPhase` (3), `0x20` = `VerifyAutomaticTurnEnd` (2), `0x51` = `EvaluateAbilities` (5),
`0xd` = `UpdatePlayerAverageUnitLevels` (0) — mais ils se **lisent** désormais, au lieu de se
reconstruire : `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`.
<!-- [slot-attribution:refute] -->

Le recoupement qui avait servi ici reste exact, et il est reproduit tel quel :

- la lambda appelle **un** slot **sans argument** ;
- `Core.Services.OperationProcessor$$StartMatch` est sans argument et délègue à
  `IdunBattle.Operations.StartMatchOperation$$Execute` ;
- cette opération est le **seul** producteur de `StepType.StartMatch` du binaire ;
- le flux montre `Action=StartMatch` comme **première** ligne du groupe ;
- **aucun autre call-site** du binaire n'appelle ce slot sur ce `Il2CppClass*` (recherche
  littérale, 1 résultat).

### Ce que l'opération écrit, lu — et ce qui en est porté

Portée : la **première** émission seulement.

```
processor.<slot 0xd>();                       // = `UpdatePlayerAverageUnitLevels` -- pas d'emission de flux
var tags = new Dictionary<TagKey,int>();      // AUCUN `Add` -- le dictionnaire est VIDE
Events.Action(StepType.StartMatch /*1*/, 1, tags);
```

Le dictionnaire vide est **LU** (aucun `Dictionary$$Add` entre le ctor et l'appel), pas déduit du
flux. L'entité y est un **littéral** `1`, là où l'**ouverture** du groupe la calcule
(`GetMatchEntity(state).Id`) : deux voies natives distinctes, plus celle de
`SetupGameOperation$$Execute` pour `System_GameSetup`. Le port les fait toutes suivre le même
paramètre, et le probe **exige** que les trois coïncident sur le flux.

Non porté, et **nommé** (§ 4) :

1. l'**arbre d'activation** des effets permanents, qui sort de **deux** appels au même slot `0x51`
   à cinq arguments : `EvaluateAbilities(GetMatchEntity(state), null, null,
   EventTriggerType.MatchInit /*0x19*/, null)` puis le même avec `MatchStart /*0x1a*/`. Les deux
   ordinaux sont **nommés** par `engine/dsl/event_trigger_type.py` (`MatchInit = 25`,
   `MatchStart = 26`) — c'est le nom qui identifie le bloc, pas sa forme dans le flux ;
2. `Action=PrepareTurn` + le `Group=StartTurn` **complet**, qui sortent du **dernier** appel de
   l'opération : `processor.<slot 0x16>(TurnStage.Start /*3*/, false, true)`, c'est-à-dire
   `ContinueTurnPhase` — même slot et mêmes trois arguments que la lambda `<Visit>b__20_0` de
   `Visit(StartTurnMessage)` ;
3. le groupe `RarityCapTransform` (`StepType.PlayerInitialRarity`), émis seulement si le joueur
   humain porte une rareté initiale — **absent** du flux témoin. Son unique tag est la clé `0xd4`,
   que `TagKey` **nomme `Rarity`** : le nom recoupe la lecture du fragment.

## 2. Le résultat, mesuré

| scénario | flux | groupe | contenu hors périmètre | `Effect_Refresh` | égalité (enveloppe) | ancrage | delta PORTÉ |
|---|---:|---:|---:|---:|---|---|---|
| C1_02, 2 tours | 2 776 l. | 477 l. | 474 l. | 42 | **3 / 3** | 4/4 | +1 / +1 / +0 |
| MC1_67, 2 tours | 2 930 l. | 521 l. | 518 l. | 44 | **3 / 3** | 4/4 | +1 / +1 / +0 |
| C1_02, **4 tours** | 4 502 l. | 477 l. | 474 l. | 42 | **3 / 3** | 4/4 | +1 / +1 / +0 |
| MC1_67, **roster 2v2 crafté** | 1 169 l. | **142 l.** | **139 l.** | **12** | **3 / 3** | 4/4 | +1 / +1 / +0 |

Le critère écrit avant la tranche est tenu **sur ce qui est porté** : `GroupType` **+1**
(`System_StartMatch`), `StepType` **+1** (`StartMatch`), `TagKey` **+0** — dérivé du **même flux
natif**, pas du port.

**Les deux scénarios de généralisation portent la preuve, chacun sur un axe** :

- le **régime long** (4 tours) fait passer le flux de **2 776 à 4 502 lignes** et de **40 à 70**
  groupes racines, et ne change **rien** au groupe (477 / 474, aux mêmes numéros de ligne 1153 et
  1157 pour A4 et A3) ni aux quatre prédictions. C'est ce qui compte pour A3/A4 : elles portent sur
  la **première** occurrence du flux entier, donc plus le flux s'allonge après le groupe, plus
  elles auraient d'occasions de tomber ;
- le **roster crafté** (`adeptHospitaller,astraBullgryn` vs `blackTerminator,worldJakhal`) fait
  varier le **contenu d'un facteur 3,7** (521 → 142 lignes, 44 → 12 `Effect_Refresh`, 30 → 13
  `Ability_Power`) — et l'enveloppe est **caractère pour caractère la même**. C'est ce qui montre
  que ce qui est porté est bien l'invariant, et non un ajustement au flux témoin.

⚠ **Le delta du groupe COMPLET est une propriété du ROSTER, pas du groupe** — et c'est ce
scénario qui l'a mesuré. Sur les deux boards du corpus par défaut il vaut `+4 / +8 / +18`, ce qui
concorde **au membre près** avec l'inventaire de #477-r18 (la ventilation les nomme un par un :
`Ability_Power`, `Effect_Refresh`, `StartTurn`, `System_StartMatch`). Sur le roster 2v2 il tombe à
`+4 / +5 / +8` : `DeactivateEffect`, `Info`, `LoseEffect` et dix `TagKey` (dont les six
`UnitStats_*_Modification*`, `Custom_Data`, `Effect_SourceTrait`) **disparaissent**. Citer
`+4 / +8 / +18` comme « le coût de la tranche » serait donc citer un plancher observé sur un
roster, pas une borne.

### Les quatre prédictions d'ancrage, et ce qui les rend discriminantes

| | prédiction | d'où elle vient |
|---|---|---|
| A1 | le groupe est **unique** | le montage envoie un seul `StartBattleMessage` — borne (c) nommée |
| A2 | tout groupe racine qui le **précède** est `System_GameSetup` ou `User_PlaceUnit` | idem — propriété du montage, prédiction falsifiable |
| A3 | le **premier** `Group=StartTurn` du flux entier est **imbriqué dedans** | **LU** : `ContinueTurnPhase` est le dernier appel de l'opération. Toutes les occurrences suivantes sont **racines** |
| A4 | le **premier** `Action=PrepareTurn` du flux entier est à profondeur 1 **dedans** | même cause. Les suivantes sont à profondeur **0** hors de tout groupe (#477-r18 § 2) |

A3 et A4 portent la mesure : elles opposent la **première** occurrence, imbriquée, à **toutes** les
suivantes, qui ne le sont pas.

### La découpe, et pourquoi elle n'est pas ajustée au port

C'est le point où un probe complaisant tricherait. La découpe n'est **pas** « tout ce que le port
n'émet pas » : elle est lue dans l'opération (une `Action` de `StepType.StartMatch` à dictionnaire
vide, puis tout le reste). Quatre refus l'arment, chacun capable de faire rougir la tranche :
l'entête doit être la cible à profondeur 0 ; la **première** ligne de profondeur 1 doit être
`Action=StartMatch` ; cette action ne doit porter **aucun** `Tag=` ; la dernière ligne doit être le
`Finish_Group` de profondeur 0. Et la somme est confrontée à chaque run —
`1 + 1 + tags + contenu + 1 == total`, **OK sur les 4 scénarios**, ainsi que la ventilation
(`sous-arbres + isolées == contenu`).

### Les 10 contre-épreuves rougissent, chacune après avoir MORDU

`enveloppe`, `entite`, `source`, `action` (l'`Action=StartMatch` omise), `tags` (un tag inventé sur
un dictionnaire vide), `steptype`, `grouptype` ; puis `position`, `premier_startturn`,
`premier_prepareturn`.

⚠ **Les trois d'ancrage mutent le FLUX, pas le verdict — et la première version faisait
l'inverse.** Elle inversait un booléen : elle rendait dix `OK` sans avoir rien mesuré de A3 ni de
A4. Corrigé en cours de tranche ; les deux mutations de flux sont construites pour ne faire tomber
**qu'une** prédiction (le `StartTurn` est inséré **imbriqué** dans le `System_GameSetup`, que A2
admet, sinon A2 tomberait aussi), et le probe **imprime laquelle** — mesuré :
`position -> avant_ok`, `premier_startturn -> a3`, `premier_prepareturn -> a4`, une chacune.

## 3. Ce que la tranche NE fait PAS

Elle porte **2 lignes sur 477**. Ce n'est pas un aveu, c'est le résultat : les deux crans
précédents portaient un groupe dont le contenu était déjà émis (`User_PlaceUnit`) ou **vide**
(`System_ProcessRemovals`) ; ici ni l'un ni l'autre. Le contenu est **énuméré**, jamais
sous-entendu, et son total est confronté au total du groupe — une amputation muette serait la
« projection implicite » que `engine/streams/conformance.py` existe pour interdire.

Ventilation mesurée (C1_02 / MC1_67, 2 tours) :

| sous-arbre de profondeur 1 | occ | lignes |
|---|---:|---:|
| `Ability_Power` | 29 / 30 | 402 / 446 |
| `Effect_Refresh` | 5 / 5 | 45 / 45 |
| `StartTurn` | 1 / 1 | 23 / 23 |
| lignes isolées (`Action=PrepareTurn` + ses 3 tags) | — | 4 / 4 |

## 4. `Effect_Refresh` — le déblocage annoncé est RÉFUTÉ, et voici le chiffre

#477-r19 § 5 nommait `System_StartMatch` comme débloqueur : **42 / 147**. La mesure de cette
tranche est plus fine, et elle renverse la conclusion :

> **0 / 42** sur `C1_02`, **0 / 44** sur `MC1_67`, **0 / 12** sur le roster crafté.

La cause est structurelle : **un `Effect_Refresh` n'est comparable que si TOUT son chemin est
émis**, pas seulement sa racine. Ventilation par chemin, mesurée :

| chemin | C1_02 | MC1_67 |
|---|---:|---:|
| `System_StartMatch > Ability_Power` | 35 | 37 |
| `System_StartMatch` (enfant direct) | 5 | 5 |
| `System_StartMatch > StartTurn` | 2 | 2 |

Les 35/37 passent par un `Ability_Power` — non porté. Les 2 passent par le `StartTurn` imbriqué —
non porté. Et **même les 5 enfants directs ne sont pas atteignables** : leur *chemin* le serait,
mais leur **contenu** ne l'est pas — `Action=ActivateEffect` / `ReceiveEffect` et leurs
`Tag=Effect_Id`, qui sont des **ids d'entité ECS d'effets** (69, 70, 72, … sur le flux témoin),
plus `Effect_SourceTriggeredAbility` / `Effect_SourceTrait`.

⇒ Le raisonnement « il faut un groupe racine porteur » de #477-r19 est **juste mais insuffisant** :
la racine est **nécessaire**, elle n'est pas **suffisante**. Ce qui reste après cette tranche est
le vrai coût, et il est nommé au résidu `#477-r21` : la face stream de
`TriggerTriggeredAbilityOperation` (pour `Ability_Power`) et de `RefreshEffectsOperation`
(pour `Effect_Refresh` et ses actions), plus l'allocation ECS des entités d'effet.

## 5. Ce qui n'est PAS couvert

- **Les 474 / 518 / 393 lignes de contenu**, par construction (§ 3, § 4) → `#477-r21`.
- **L'égalité brute porte sur 3 lignes**, et c'est peu en soi : ce sont les étages ANCRAGE (4
  prédictions), RECOUPEMENT (3 voies d'entité) et DÉCOUPE (4 refus + 2 sommes exactes) qui portent
  la mesure, pas le diff textuel. C'est publié plutôt que sous-entendu.
- **Le recoupement d'entité vaut `1 = 1 = 1`** sur tous les scénarios : un port qui écrirait `1` en
  dur passerait. C'est le test offline `test_l_entite_SUIT_le_parametre_et_n_est_pas_une_constante_recopiee`
  qui l'interdit (le port émet `Entity=4242` quand on lui passe 4242), pas le probe live.
- **A1 et A2 sont des propriétés du MONTAGE**, pas du natif : un seul `StartBattleMessage`, envoyé
  après les placements. Nommées en borne (c). A3 et A4, elles, sont lues.
- **Le bloc `RarityCapTransform`** : jamais exercé (aucun joueur du seed ne porte de rareté
  initiale non nulle). Lu, pas confronté.
- **La branche `*(this+0x28)+0x24 == 2` de `RunPhase`** (le match déjà terminé), qui rendrait le
  groupe **absent** : non atteinte par le montage.

## 6. Une correction d'attribution, confirmée mais NON APPLIQUÉE

`engine/runner/operations/revive.py` et `damage.py` décrivaient `RunPhase(PhaseType.ProcessRemovals /*0xd*/)` comme la phase de `ReviveUnit`. <!-- [phase-attribution:refute] -->
`case-477r19` § 6 l'avait réfuté par la signature de la lambda ; cette tranche le
confirme par le **nom** : `frida/enums.tsv` donne `IdunBattle.Core.PhaseType` `13=ProcessRemovals`,
et `11=SkipToNextWave`, `12=ProcessDeaths`, `14=ProcessDamageEvents`. Aucun `PhaseType` ne nomme un
revive. La correction reste **hors périmètre** de cette tranche (ces fichiers portent la mécanique
ECS, pas la face stream).

→ **APPLIQUÉE depuis, par `#477-r24`** (dispatché sous l'étiquette `#477-r19-r2`, numéro déjà pris
par le résidu `Effect_Refresh`). Résultat plus fort que prévu : `ReviveUnit` n'a **aucune** phase.
cf. `docs/rl/case-477r24-le-revive-na-pas-de-phase.md`.

## Résidus

- **#477-r21** — **le CONTENU de `System_StartMatch` : 474 / 518 lignes, et c'est ce qui bloque
  vraiment `Effect_Refresh`.** Trois blocs nommés et lus (§ 1) : (1) l'arbre
  `Ability_Power` / `Effect_Refresh` des deux `EvaluateAbilities(MatchInit)` / `(MatchStart)` ;
  (2) `Action=PrepareTurn` + `Group=StartTurn` de `ContinueTurnPhase(TurnStage.Start, false,
  true)` ; (3) le groupe `RarityCapTransform`, jamais exercé. Ce que le porter exige, mesuré :
  la face stream de `TriggerTriggeredAbilityOperation` (les 29/30 `Ability_Power`), celle de
  `IdunBattle.Operations.RefreshEffectsOperation$$GenerateEventGroup` (les 42/44
  `Effect_Refresh` et leurs `ActivateEffect` / `ReceiveEffect` / `ChangeStats` / `LoseEffect`), et
  **l'allocation ECS des entités d'effet** (`Tag=Effect_Id` — 86/94 occurrences, valeurs 69…113 sur
  le flux témoin), dont #477-r16 n'a porté que le versant unités/tuiles.
  RETOURNEMENT : un montage où le contenu de `System_StartMatch` deviendrait **vide** rendrait
  l'enveloppe seule suffisante. Mesuré : il **se réduit fortement** (518 → **139** lignes avec un
  roster de 2 unités par camp, soit un facteur 3,7) mais **ne s'annule pas** — il reste 13
  `Ability_Power`, 12 `Effect_Refresh` et le `StartTurn`. Le régime « groupe vide », celui qui
  avait fait la valeur du cran `System_ProcessRemovals`, **n'existe pas ici**.
