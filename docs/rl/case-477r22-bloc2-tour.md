# #477-r22 — le BLOC 2 de `System_StartMatch` : le TOUR, et sa RÉCOLTE hors du groupe

**LIVRÉ.** Build `rnca9r7q6c`, ghidra-mcp, session Frida **1** (chaude, aucun reinject).
Le port reproduit à l'**égalité brute** **28 / 28** couples `Action=PrepareTurn` + `Group=StartTurn`
sur **cinq** scénarios, **1 359 lignes** égales. **23 des 28 sont HORS du groupe
`System_StartMatch`** — c'est la mesure que la tranche devait rendre, et elle est **mesurée, pas
déduite d'une ventilation**.
Sur le roster 2v2 crafté, `System_StartMatch` devient **INTÉGRALEMENT porté : 142 / 142 lignes**.

**`#477-r22-r1` a fermé le CONTENU du groupe** (§ 7) : le slot `0x21` est **résolu**
(`Core.Services.IOperationProcessor` slot 33 = `VerifyUnitsTurnFinished`, **arité 0**), sa face
stream est portée, et la forme `Action=Info` / `Tag=Custom_Data` aussi. Les **63 marques** et les
**12 `Action=Info`** du corpus entrent au périmètre et s'y reproduisent.

```powershell
python scripts/python/probe_477r22_turn_phase.py            # live, 3 scenarios
python -m pytest scripts/python/tests/engine/test_477r22_turn_phase_offline.py \
                scripts/python/tests/engine/test_477r22r1_verify_turn_finished_offline.py -q
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

⚠ **Les numéros de slot ci-dessus sont des REPÈRES DE CALL-SITE, pas une attribution établie — et
ce port n'en dépend pas.** `#477-r24-r1` a mesuré sur `Core.Services.IOperationProcessor` un
décalage slot→classe **local de 12** (trois ancrages concordants dans la zone 96-99),
**incompatible** avec la lecture de `case-477r20` que cette tranche reprend (`ContinueTurnPhase` au
slot `0x16` pour la position 26). Une des deux lectures est fausse et **rien ne dit laquelle** :
une interface IL2CPP n'a aucun corps, donc **0** ligne dans `frida/methods.tsv`, et l'ordre des
slots ne se lit nulle part hors du metadata.
Ce qui est établi, et qui suffit : les deux opérations sont identifiées **par leur émission** —
`PrepareTurnOperation$$Execute` est le **seul** producteur de `StepType.PrepareTurn` du binaire,
`StartTurnOperation$$Execute` le **seul** de `GroupType.StartTurn` — et le flux les montre
exactement là où le `switch` les prédit (**29 / 29** couples à l'égalité brute). Si `#477-r24-r1`
tranche un jour, ce sont les **commentaires de slot** qu'il faudra corriger, pas le code ni les
mesures.

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
| `C1_02`, 2 tours | 2 776 l. | 477 l. | 27 l. | 5 | **5** | **4 / 4** | 317 |
| `MC1_67`, 2 tours | 2 930 l. | 521 l. | 27 l. | 5 | **5** | **4 / 4** | 299 |
| `MC1_67`, **roster 2v2 crafté** | 1 169 l. | 142 l. | **8 l.** | 5 | **5** | **4 / 4** | 124 |
| `C1_02`, **6 tours demandés** | — | 477 l. | 27 l. | 8 | **8** | **7 / 7** | 555 |
| `C1_02`, **roster crafté** (custo/blood vs genes/astra) | 1 031 l. | **214 l.** | **12 l.** | 5 | **5** | **4 / 4** | 64 |
| **total** | | | | **28** | **28** | **23 / 23** | **1 359** |

⚠ **Les lignes égales ont AUGMENTÉ de 150 sans qu'un seul couple change** : `#477-r22-r1` a fait
entrer au périmètre les **63 marques** du slot `0x21` (126 lignes) et les **12 `Action=Info`**
(48 lignes) — **174** lignes au total, dont **150** sur les quatre scénarios communs aux deux
mesures (279→317, 261→299, 112→124, 493→555). Le 5ᵉ scénario n'est PAS le même qu'à la tranche
précédente (le roster « 1v1 » qu'elle avait joué n'est écrit nulle part) : celui-ci est le roster
crafté de `#477-r21`, et il exerce le même régime — **1 `Group=StartTurn` SANS contenu** sur ses
5 couples.

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

- ~~**Le CONTENU du `Group=StartTurn` hors des formes de #477-r21**~~ → **FERMÉ par `#477-r22-r1`**
  (§ 7). Restent les familles que ce résidu n'avait **pas** énumérées : un sous-arbre
  `Group=ResurrectUnit` / `Ability_CustomGroup` (106 l. sur `MC1_67`) et un `Group=Damage`
  (47 l. sur le roster 2v2, 36 l. sur les 6 tours) → **#477-r34**.
- **Les gardes de `HandleNextTurn`** → **#477-r22-r2**. Le port exécute **chaque** stage traversé ;
  sur un montage avec drafting en attente le natif s'arrêterait avant `Start` et le port émettrait
  un `Group=StartTurn` de trop. Non atteint par nos montages (aucun drafting en duel).
- ~~**Le slot `0x21`**~~ : **RÉSOLU** par `#477-r22-r1` (§ 7) — `VerifyUnitsTurnFinished`, arité 0.
- **`ChangeTurnOperation` et `EndTurnOperation`** : la première est LUE comme n'écrivant rien (aucun
  appel à `StreamDispatcher` dans son décompilé entier), la seconde n'est pas portée — et
  `execute_stage` **LÈVE** si la séquence la traverse, plutôt que d'émettre un flux amputé.
- **La surcharge `requestedTurnStage == null`** de `ContinueTurnPhase` : lue, non portée (les deux
  call-sites confrontés passent tous deux une valeur).
- **Le stage de départ** reste une entrée : `Change` et `End` sont indiscernables par le flux (§ 4).

## 7. `#477-r22-r1` — le CONTENU du groupe : slot `0x21` RÉSOLU, et `Action=Info` portée

**LIVRÉ.** Le résidu tenait à un « nulle part » qui n'était plus vrai : `#477-r25` a livré
`data/symbols/<build>/metadata/interface_slots.tsv`, et `#477-r24-r1` y couvre
`Core.Services.IOperationProcessor`.

### 7.1 Le slot, lu — et son ARITÉ, qui fait partie de son identité

| slot | méthode | `param_count` |
|---|---|---:|
| `0x21` (33) | `VerifyUnitsTurnFinished` | **0** |
| `0x76` (118) | `MarkUnitAsNoActionAvailable` | 1 |
| `0x77` (119) | `MarkUnitAsActionAvailable` | 1 |

**Trois canaux concordent, et aucun ne suffit seul** : (a) la table du metadata ; (b) le
call-site — `IdunBattle.Operations.StartTurnOperation$$Execute` invoque le slot `0x21` **sans
aucun argument**, ce qui écarte ses deux voisins homonymes (`VerifyAutomaticTurnEnd` à 2
arguments au slot 32, `VerifyAndRefreshUnitTurnFinished` à 1 au slot 34) ; (c) l'émission
observée, qui est celle de `MarkUnitAsNoActionAvailableOperation$$Execute`, seule atteignable
depuis `VerifyUnitsTurnFinishedOperation` à cet endroit.

Les trois citations entrent au **cliquet** `probe_477r24r1_slots_interface.py` (49 → **52**
attestations) — vérifié en **muant** le nom : le cliquet passe ROUGE et nomme le fichier, la
ligne et le nom attendu.

### 7.2 La chaîne, et ce que le port en DÉRIVE

```
Core.Services.OperationProcessor$$VerifyUnitsTurnFinished              <- slot 0x21, arite 0
  -> IdunBattle.Operations.VerifyUnitsTurnFinishedOperation$$Execute
       if (GetMatch(state).<+0x24> != 1) return;              // NON PORTE (meme champ que la
                                                              //  garde `== 2` de ContinueTurnPhase)
       foreach (id in PlayerComponent.get_CurrentlyOwnedUnitIds(player)) VerifyUnitTurnEnded(...)
       VerifyMachineTurnEnded(player.<+0x78>)                  // INLINE dans Execute
  -> $$VerifyUnitTurnEnded(unit)
       if (UnitFlagsComponent.TurnEnded(comp))                            return;
       if (TryGetComponent<HealthComponent>(out hp) && hp.IsDead())       return;
       if (!Has(UnitFlag.NoActionAvailable)) { if (HasTilesToMoveTo || HasActionAvailable) return;
                                               <slot 0x76>(unit); }      // POSE  -> valeur 0
       else                                  { if (!HasTilesToMoveTo && !HasActionAvailable) return;
                                               <slot 0x77>(unit); }      // RETIRE -> valeur 1
  -> $$MarkUnitAsNoActionAvailableOperation$$Execute(unit, reverse)
       change = reverse ? Remove(flag) : Add(flag);   if (!change) return;   // LE GATE
       Events.Action(StepType.ChangeStats /*0xc*/, unit.Id,
                     { TagKey.UnitStats_ActionsAvailable /*0x6f*/ : reverse ? 1 : 0 });
```

**Trois lectures qui n'auraient pas été devinables** :

**(a) La VALEUR est l'INVERSE du sens du drapeau.** `MarkUnitAs**No**ActionAvailable` **pose** le
drapeau et écrit **`0`** ; `MarkUnitAsActionAvailable` le **retire** et écrit **`1`**. Le nom de
l'opération et le nom du tag s'opposent — écrire `int(<drapeau posé>)` était la faute naturelle.

**(b) L'émission est GATÉE par le retour de la mutation.**
`IdunBattle.Entities.Components.UnitFlagsComponent$$Add` rend `false` si le drapeau était **déjà**
là, `$$Remove` `false` s'il n'y était **pas**, et l'opération **retourne** sur ce `false` sans
même construire le dictionnaire. Deux appels de même sens n'écrivent donc **qu'une** ligne. C'est
pour ce gate — et pour lui seul — que la face stream tient un registre du bit
(`NoActionAvailableFlags`, un seul drapeau ; l'axe ECS complet reste dans
`engine/runner/components.py`, #287-r1).

**(c) L'entité écrite est celle de l'UNITÉ**, là où les deux autres émissions du même groupe
(`Action=PrepareTurn`, `Action=StartTurn`) portent celle du MATCH. Les runners portent tous
l'entité de match `1` : un port qui l'écrirait en dur passerait toutes les comparaisons live.

**Le second motif** (`Group=Ability_Power Source=StandVigil` → `Action=Info` /
`Tag=Custom_Data`) sort de
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.StandVigil_UpdateEffectRangeAbility$$CreateBehaviour`,
qui appelle la surcharge **à UNE CLÉ** de `IdunBattleLogic.Entities.DSLBehaviors$$Inform(TagKey,
IAmountFormula)` avec `TagKey.Custom_Data` — surcharge identifiée par ses **XREFS entrantes**, le
build en portant **six** du même nom. `InformOperation$$Execute` était déjà porté
(`engine/streams/inform_ops.py`) ; il ne manquait que le constructeur du dictionnaire
(`get_inform_tags`). **Le périmètre est le couple ACTION + CLÉ** : une `Action=Info` portant les
clés d'ARME (`Attack_Weapon_*`, l'autre foyer) reste HORS PÉRIMÈTRE, énumérée.

### 7.3 Ce que le port dérive, et ce qu'il copie

La face stream n'a ni pathfinding ni prédiction de dégât : les **deux prédicats de mobilité**
(`HasTilesToMoveTo` → `MovementQuery$$HasAnyMovablePositionsFor`, `HasActionAvailable` →
`DamagePredictionQuery$$CanAttackAnyUnitFromTilesWithAnyAbility`, identifiés par `#287-r1-r1`)
sont des **ENTRÉES**, déclarées en borne (c). Ce qui est **MESURÉ** :

| | dérivation | `C1_02` | `MC1_67` | 2v2 | 6 tours | crafté |
|---|---|---:|---:|---:|---:|---:|
| (D6) | marques / candidats **dérivés** de `Unit_Owner_Id` ; marques **hors** candidats | 13/26 ; **0** | 13/26 ; **0** | 6/10 ; **0** | 25/42 ; **0** | 6/10 ; **0** |
| (D7) | VALEUR dérivée du registre `UnitFlag.NoActionAvailable` | 13/13 | 13/13 | 6/6 | 25/25 | 6/6 |
| (D8) | ORDRE des marques = ordre des `Action=AddUnit` | 3/3 | 3/3 | 3/3 | 6/6 | 3/3 |
| (D9) | `Action=Info` entrées au périmètre | 3 | 3 | 0 | 3 | 3 |

**(D6) est la dérivation centrale.** Le port n'apprend pas de la queue quelles unités visiter :
il les **dérive** de deux canaux qui l'ignorent — la carte `Action=AddUnit` → `Tag=Unit_Owner_Id`
du flux, filtrée par le `Tag=Match_CurrentPlayerId` de l'`Action=PrepareTurn`. Une unité marquée
qui ne serait pas candidate ferait rougir ; **0 sur 63**. La carte est **incrémentale** : sur
`C1_02` l'entité `123` entre en cours de bataille, elle est bien candidate, et le natif ne la
marque jamais.

**`turn_ended` est LU, pas copié** : le slot `0x21` est appelé en **fin** de
`StartTurnOperation$$Execute`, après la boucle qui applique
`IdunBattle.Entities.Components.UnitFlagsComponent$$RemoveTurnFlags` à chaque unité de
`CurrentlyOwnedUnitIds` — et `RemoveTurnFlags` retire `UnitFlag.TurnFinished` **sans condition**.

### 7.4 La GÉNÉRALISATION : le foyer confronté sur TOUT le flux

⚠ **Le `Group=StartTurn` n'exerce QU'UNE des deux valeurs.** Sur les cinq scénarios, **63 marques
sur 63** valent `1` : une unité qui commence son tour a toujours une tuile où aller, donc la
branche qui écrit `0` n'y apparaît jamais. Un vert obtenu sur ce seul régime ne dirait rien de la
correspondance `reverse → 0/1`.

Le probe rejoue donc le flux **entier** : pour chaque émission du foyer — y compris celles des
call-sites que cette tranche **ne porte pas** (`FinishUnitTurnOperation$$Execute`,
`ActiveAbilityOperation$$ExecuteInternal`, `MoveUnitOperation`) — il **dérive** le sens depuis le
registre construit par les émissions **précédentes**, émet avec le port, et confronte.

| | `C1_02` | `MC1_67` | 2v2 | 6 tours | crafté | **total** |
|---|---:|---:|---:|---:|---:|---:|
| émissions reproduites | 33/33 | 34/34 | 14/14 | 59/59 | 17/17 | **157 / 157** |
| valeur `0` / valeur `1` | 20 / 13 | 20 / 14 | 8 / 6 | 34 / 25 | 10 / 7 | **92 / 65** |

Ce n'est **pas circulaire** : à l'instant `k` le registre ne connaît que les lignes `1..k-1`, donc
la valeur de la ligne `k` est une **prédiction**. Une prédiction fausse se voit de deux façons —
une VALEUR différente, ou une ligne **MANQUANTE** si le port croit le drapeau déjà dans l'état
demandé. Contre-épreuve jouée : inverser `1 if reverse else 0` dans le port fait tomber le compte
à **0 / 33**.

### 7.5 Les SEPT contre-épreuves de la tranche

`marque_valeur`, `marque_entite`, `marque_tag`, `marque_branche`, `marque_ordre`,
`verif_avant_corps`, `info_entite`, `info_tag_arme` — **8 / 8 OK**, jouées sur chaque couple de
leur domaine, `mord` séparé de `rougit`.

⚠ **DEUX d'entre elles ont d'abord été mises dans le MAUVAIS PROBE, et le garde-fou de ce
probe-là les a refusées.** `info_entite` / `info_tag_arme` avaient été ajoutées à
`probe_477r21_activation_tree.py` : leur domaine y est **NUL sur les QUATRE scénarios** du BLOC 1,
qui ne porte aucune `Action=Info`. Le verdict « `N` mutation(s) au domaine NUL sur TOUS les
scénarios — rien ne les confronte » a rougi, et il avait raison : une mutation qu'aucun scénario
n'exerce ne mesure rien. Elles vivent désormais en `MUTATIONS_RELAYEES` — le module sait les
émettre, `probe_477r22` les **joue** (domaine 3) — et le **même garde est ajouté à
`probe_477r22`**.

⚠ **Le régime 2v2 est un TÉMOIN D'INERTIE ATTENDUE, et il est déclaré** : ce roster ne produit
aucune `Action=Info`, donc `info_entite` / `info_tag_arme` y sont **HORS DOMAINE** — publié comme
ATTENTION, jamais compté vert.

### 7.6 Le compte AVANT / APRÈS, par scénario

| scénario | hors périmètre AVANT | marques entrées | `Info` entrées | hors périmètre APRÈS |
|---|---:|---:|---:|---:|
| `C1_02`, 2 tours | 38 l. | 26 l. | 12 l. | **0** |
| `MC1_67`, 2 tours | 144 l. | 26 l. | 12 l. | **106** (`ResurrectUnit`) |
| `MC1_67`, 2v2 | 59 l. | 12 l. | 0 | **47** (`Damage`) |
| `C1_02`, 6 tours | 98 l. | 50 l. | 12 l. | **36** (`Damage`) |
| `C1_02`, crafté | 24 l. | 12 l. | 12 l. | **0** |

**Le critère de la tranche est tenu** : les 13 + 13 lignes du résidu **entrent au périmètre et
s'y reproduisent** — elles ne disparaissent pas du compte, elles changent de colonne. Les
restes (`Group=ResurrectUnit` / `Ability_CustomGroup`, `Group=Damage`) sont **deux familles que
le résidu #477-r22-r1 n'avait pas énumérées** : il nommait deux motifs, le flux en portait
quatre. Elles ouvrent **#477-r34**.

### 7.7 Ce que `#477-r22-r1` ne couvre PAS

- **La DÉCISION** de `VerifyUnitTurnEnded` : les deux prédicats de mobilité restent des entrées.
  Leur calcul existe côté ECS (`engine/runner/operations/turnflow.py`, #287-r1-r1) mais le flux
  rejoué ne fournit aucun état à leur donner ;
- **La garde `GetMatch(state).<+0x24> != 1`** : même champ que la garde `== 2` de
  `ContinueTurnPhaseOperation$$Execute`, déjà non portée. **Aucun accesseur NOMMÉ du build ne lui
  donne un type** — `frida/methods.tsv` ne publie aucune méthode de retour `MatchStage` — donc
  l'attribuer à cet enum serait une hypothèse déguisée en mirror. Elle est citée par son OFFSET ;
- **`VerifyMachineTurnEnded`** : portée (son prédicat est `MachineCanAttackAnyUnitWithAnyAbility`,
  slot `IDamagePredictionQuery` 2, et elle n'a **pas** de test de mort) mais **NON EXERCÉE** —
  aucun de nos montages n'amène de Machine of War. Gardée offline seulement ;
- **La valeur `0` DANS un `Group=StartTurn`** : jamais observée. Elle exigerait une unité qui, au
  début de son tour, ne peut ni bouger ni agir alors qu'elle n'est pas déjà marquée. Elle est
  exercée **offline** (table de vérité) et **live hors du groupe** (92 occurrences, § 7.4).

## Résidus

- **#477-r34** — **LIVRÉ pour sa moitié `Group=Damage`** (`docs/rl/case-477r34-groupe-damage.md`) :
  61 groupes reproduits à l'égalité brute sur tout le flux, 8 contre-épreuves.
  ⚠ **Le « 47 lignes sur le roster 2v2 » du § 7.6 ci-dessus est SURESTIMÉ pour cette famille** :
  la ventilation mesurée par `#477-r34` y trouve **36** lignes de `Group=Damage` et **11** d'une
  `Action=HealInfo` — c'est cette dernière, neuf lignes, qui retient tout le bloc. Nommer un bloc
  par l'une des formes qu'il porte surestime ce que porter cette forme rapporte.
  Restent ouverts : **#477-r38** (`Group=ResurrectUnit` / `Ability_CustomGroup`, 106 l.),
  **#477-r39** (`Action=HealInfo`) et **#477-r40** (`Group=Ability_Power` à `Source=` d'`EffectType`).
- **#477-r22-r2** — **les gardes d'état de `ContinueTurnPhaseOperation$$HandleNextTurn`.** Trois,
  toutes lues : le match terminé (`match.<+0x24> == 2`), la décision de drafting en attente au stage
  `Draft`, et les quatre conditions de la branche `Prepare`. Aucune n'est atteinte par nos montages ;
  ⚠ **ce n'est pas une face stream** — comme `#477-r21-r2`, ce résidu vit dans l'ÉTAT ECS.
