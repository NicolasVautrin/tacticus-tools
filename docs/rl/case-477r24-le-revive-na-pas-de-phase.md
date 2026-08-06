# #477-r24 — `RunPhase(0xd)` n'est pas la phase du revive : le revive n'a **pas de phase**

> Dispatché sous l'étiquette `#477-r19-r2`. Ce numéro était **déjà pris** par le résidu
> « `Effect_Refresh` attend un groupe racine porteur » du backlog ; `probe_468` a rendu
> **`#477-r24`**, qui est le numéro retenu. La collision est signalée aux deux endroits.

## 1. Le constat, et pourquoi aucun test ne le voyait

`engine/runner/operations/revive.py` et `damage.py` décrivaient `RunPhase(0xd)` comme la phase de
`Core.Services.OperationProcessor$$ReviveUnit`. Deux tranches l'avaient contredit sans le corriger
(`case-477r19` § 6 par la signature de la lambda, `case-477r20` § 6 par le nom de l'enum).

**L'erreur était 100 % documentaire**, donc structurellement invisible d'une passe verte : aucun
littéral exécutable ne portait le `0xd`, aucun test n'en dépendait. C'est le régime que le cliquet
livré ici couvre.

## 2. Ce que le décompilé dit — trois voies indépendantes

**(a) Le NOM.** `data/symbols/rnca9r7q6c/frida/enums.tsv` :

```
IdunBattle.Core.PhaseType   0=StartBattle, 1=StartTurn, 2=EndTurn, 3=FinishUnitTurn, 4=AddUnit,
                            5=MoveUnit, 6=ActiveAbility, 7=Damage, 8=Surrender, 9=PickUnit,
                            10=RerollDraftOption, 11=SkipToNextWave, 12=ProcessDeaths,
                            13=ProcessRemovals, 14=ProcessDamageEvents,
                            15=ProcessPendingTriggeredAbilities, 16=Cheat
```

**Aucun membre ne nomme un revive.** C'est le seul `PhaseType` du dump d'enums (pas d'homonyme,
contrairement à `Corner`/`Edge`).

**(b) La LAMBDA.** `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` lance deux phases,
et la seconde est le corps **inliné** d'`IdunBattle.Messages.InputMessageProcessor$$VerifyRemovedUnits` —
mêmes `DAT_` de drapeau d'init, de `Il2CppClass*` du `<>c__DisplayClass50_0` et de pointeur de
lambda dans les deux fonctions :

```
if (deaths.Count > 0) RunPhase(PhaseType.ProcessDeaths /*0xc*/,   <VerifyDeaths>b__0,       isInternalPhase: true, false);
...                   RunPhase(PhaseType.ProcessRemovals /*0xd*/, <VerifyRemovedUnits>b__0, isInternalPhase: true, false);
```

`IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass50_0$$u003CVerifyRemovedUnitsu003Eb__0`
copie la file dans une `List`, la `Clear()`, ouvre `GroupType.System_ProcessRemovals` et retire
chaque entité. Elle ne touche à aucun revive.

**(c) LES XREFS.** `Core.Services.OperationProcessor$$ReviveUnit(this, killed)` — **un seul
paramètre** — n'a **aucune xref CODE** dans le binaire : ses deux seules xrefs sont des entrées
DATA de tables de méthodes. Il est donc invoqué exclusivement par slot d'interface
`Core.Services.IOperationProcessor`.

## 3. Où le revive est réellement appliqué

Dans `IdunBattle.Operations.KillUnitOperation$$Execute`, **branche `else` de la garde** qui teste le
`hasValue` du `Nullable<ReviveData>` @`UnitComponent + 0xa8` :

```c
pcVar26 = thunk_FUN_1801f5f80(unitComponent + 0xa8, <hasValue>);   // KillUnitOperation$$Execute+0x82e
if (*pcVar26 == '\0') {
    ... RegisterDefeatedUnit, On(PreUnitDeath_2), On(UnitDeath), On(UnitDefeated), On(PostUnitKill),
        KillUnitOperation$$RemoveEffects, puis le retrait de l'unité ...
} else {
    <slot 99>(killed);                       // 1 SEUL argument
}
// puis, DANS LES DEUX BRANCHES : purge des 9 qwords +0xa8 .. +0xe8
```

**Le slot `99` est `ReviveUnit`** — et Ghidra l'imprime en **décimal**, ce qui le rend invisible à
toute recherche portant sur `0x63`. ✅ **CONFIRMÉ depuis, par lecture DIRECTE du champ `slot` du
metadata IL2CPP** (`#477-r24-r1`, `case-477r24r1-mapping-slot-interface.md`) : slot 99 =
`ReviveUnit(killed)`, 1 paramètre. Le recoupement ci-dessous reste exact ; il n'est simplement
plus la seule voie.

- l'appel passe **exactement un** argument (`killed`) — le helper d'invocation utilisé est celui à
  un argument, le même que pour `FUN_180003c00(4, DAT_183364c10, ..., killed)` ;
- l'ordre des slots de `Core.Services.IOperationProcessor` reproduit celui de la classe avec un
  **décalage de 12** dans cette zone, mesuré sur **trois** ancrages indépendants :
  `IdunBattle.Entities.Behaviours.HealBehaviour$$Execute` → slot `0x57` → position 99 =
  `HealUnit(healer, target, amount, scope, removeEffects, abilityOrEffect)` (6 arguments, exacts) ;
  `<VerifyDeaths>b__0` → slot `0x60` → position 108 = `KillUnit(killer, killed, options)` (3 args,
  précédé de `KillUnitOperationOptions.ForDefault()`) ; et slot `0x61` → position 109 =
  `DestroyMachine(killer, killed)` (2 args, branche `else` du test « est-ce une machine »).
  `99 + 12 = 111 = ReviveUnit(killed)`. Les positions voisines sont exclues par l'arité :
  110 = `RecordKill(killer, killed, context)` = 3 args, 112 = `ResurrectUnit(...)` = 6 args ;
- il n'existe aucun autre lecteur du champ `+0xa8` avec cette garde, et la purge des 9 qwords qui
  suit consomme précisément la `ReviveData`.

⚠ **LE « DÉCALAGE SLOT↔CLASSE » N'EXISTE PAS — cette grandeur était une ILLUSION, et c'est
`#477-r24-r1` qui l'a démontré.** Ce paragraphe disait le décalage « non constant, donc mesuré
localement », et concluait que le couple `ContinueTurnPhase` / slot `0x16` de `case-477r20` était
**incompatible** avec les trois ancrages ci-dessus. **Cette conclusion est FAUSSE : les deux
lectures sont justes, et tiennent ensemble.** <!-- [slot-attribution:refute] -->

Le slot d'interface est un rang dans la table de l'**interface** ; la « position » à laquelle on
le comparait est celle d'une méthode dans le dump de la **classe**. Deux ordres différents, qu'aucune
relation ne lie — le « décalage » n'était que leur soustraction, et il n'avait aucune raison d'être
constant. Pire, la « position » n'est même pas bien définie : `frida/methods.tsv` est indexée par
adresse, donc elle **perd les surcharges à corps dédupliqué** (mesuré : 149 lignes pour 150 entrées
réelles, l'écart s'installant dès l'index 87). Comparer deux décalages locaux ne pouvait donc rien
prouver, ni dans un sens ni dans l'autre.

Ce qu'il fallait lire est le champ `slot` d'`Il2CppMethodDefinition`, dans `global-metadata.dat` :
`0x26` = `AddTrait` (3 args), `0x57` = `HealUnit` (6), `0x60` = `KillUnit` (3), `0x61` =
`DestroyMachine` (2), `0x63` = `ReviveUnit` (1) — **et** `0x16` = `ContinueTurnPhase` (3),
`0x20` = `VerifyAutomaticTurnEnd` (2), `0x12` = `StartMatch` (0). Les huit sont dans la **même**
table. Table complète : `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`.

⇒ **Le revive s'exécute synchroniquement à l'intérieur du kill**, donc dans la phase de l'action
qui a provoqué ce kill : `PhaseType.ProcessDeaths` quand le kill vient du drain de `VerifyDeaths`,
mais aussi bien `PhaseType.Damage` ou `PhaseType.ActiveAbility` quand `KillUnit` est appelé en
ligne. **« Aucune phase » est le résultat, et il est mesuré — ce n'est pas une absence de preuve.**

## 4. Ce qui a changé dans le port

**Le comportement ECS n'a pas bougé — et c'est le résultat, pas un renoncement.** `kill_unit_revive_gate`
mettait déjà garde et application au même endroit ; le décompilé montre que **le natif les y met
aussi**. Ce que le port appelait « un collapse » est en fait la structure lue : la correction est
donc textuelle, et elle est livrée courte.

| Fichier | Ce qui est corrigé |
|---|---|
| `engine/streams/phase_type.py` | **mirror neuf** d'`IdunBattle.Core.PhaseType` (17 valeurs), inscrit au registre `probe_313` dans le même commit |
| `engine/runner/operations/revive.py` | cran 3 « DRAIN de `RunPhase(0xd)` » → « APPLICATION, branche `else`, même fonction native » + le § d'attribution mesurée |
| `engine/runner/operations/damage.py` | « il n'y a AUCUN `else` » (faux) → « il y a bien un `else`, et c'est lui qui applique le revive » |
| `probe_hazeord_death_queue.py`, `test_death_queue_ordering_live.py`, `test_tainted_narthecium_revive_live.py` | schémas de séquence ré-attribués |
| `docs/rl/case-66-revive-in-place.md`, `case-haze-ord.md` | « `RunPhase(0xd)` = les revives » → les RETRAITS |
| 24 sites (12 fichiers) | ordinal de phase **nommé** : `RunPhase(0xd)` → `RunPhase(PhaseType.ProcessRemovals /*0xd*/)` |

## 5. Le balayage — les chiffres

Balayage de `scripts/python/**` (`.py`) + `docs/rl/**` (`.md`), 2 568 fichiers :

| grandeur | avant | après |
|---|---|---|
| sites `RunPhase(<phase>)` détectés | 62 | 62 |
| ordinaux de phase **nus** sous `scripts/python/**` | **24** | **0** |
| attributions **fausses** (phase → opération qu'elle ne draine pas) | **5** | **0** |
| phases dont le drain est **lu au décompilé** | 0 | 2 (`ProcessDeaths`, `ProcessRemovals`) |
| phases **NON COUVERTES**, imprimées comme telles | — | 7 (`StartBattle` ×2, `AddUnit` ×4, `MoveUnit` ×5, `ActiveAbility` ×3, `ProcessDamageEvents` ×1, `ProcessPendingTriggeredAbilities` ×16, `Cheat` ×1) |

Les 5 attributions fausses : `revive.py` (§ DRAIN), `probe_hazeord_death_queue.py`,
`test_death_queue_ordering_live.py`, `case-66-revive-in-place.md`, `case-haze-ord.md`. Les autres
ordinaux nus étaient **bien attribués** (`0xf` = `ProcessPendingTriggeredAbilities`, `0x4` =
`AddUnit`, `5` = `MoveUnit`, `6` = `ActiveAbility`, `0xc` = `ProcessDeaths`) — seul `0xd` mentait.

## 6. La garde

`scripts/python/probe_477r24_phase_attribution.py` (mesure) +
`tests/engine/test_477r24_phase_attribution_offline.py` (cliquet), 3 étages :

1. **MIRROR + ORDINAUX ÉCRITS FIGÉS.** Bijection avec `enums.tsv`, **plus** les 7 ordinaux
   réellement écrits à un site, figés en dur. Ce second cran n'est pas redondant avec `probe_313` :
   celui-ci redevient vert dès qu'on régénère le mirror après un renumérotage, alors que la valeur
   écrite au site, elle, a changé.
2. **NOMMAGE** (invariant 0) : sous `scripts/python/**`, un ordinal en position `RunPhase(<ord>` porte
   son `PhaseType.<Membre>` sur la même ligne. C'est la parade **à la racine** — on ne peut plus
   écrire une phase sans la nommer, donc plus l'attribuer de tête.
3. **ATTRIBUTION** (invariant 0) : sur une ligne portant une phase, tout jeton d'opération doit
   appartenir au drain mesuré. Les jetons sont **dérivés** des 141 noms de méthode de
   `Core.Services.OperationProcessor` lus dans `frida/methods.tsv` — la sonde ne cherche pas
   `ReviveUnit` en dur, elle cherche n'importe quelle opération et la confronte.

**Contre-épreuve** : 6 mutants, `a_mordu` rendu **séparément** du verdict → 0 inerte. Et deux
mutations de la faute **réelle** réintroduites dans de vrais fichiers (`revive.py`, `state.py`) :
la garde rougit sur les deux, avec vérification préalable que la mutation avait bien mordu.

**Échappatoire consciente et bornée** : une ligne qui *cite* une attribution réfutée porte le
marqueur `[phase-attribution:refute]`. Ce n'est pas une liste blanche de fichiers — c'est une
déclaration **au site**, que la sonde **compte et imprime** (3 aujourd'hui, plafond 5 dans le test).

**Ce que la garde ne voit pas, et c'est dit** : la **prose** (« la phase du revive » en français ne
porte aucun jeton d'opération) ; les phases dont le drain n'a pas été lu (imprimées `NON COUVERT`,
jamais vertes en silence) ; les fichiers hors `scripts/python/**` et `docs/rl/**`.

## Résidus

- ~~**#477-r24-r1**~~ — **FERMÉ (2026-08-06) : le mapping EST dérivable, et les deux lectures
  publiées étaient JUSTES toutes les deux.** Ce résidu affirmait que les couples de `case-477r20`
  « sont incompatibles avec les trois ancrages de cette tranche » — **c'était faux**. Le champ
  `slot` d'`Il2CppMethodDefinition` donne le mapping directement ; la « position dans la classe »
  par laquelle on comparait n'indexe rien (cf. l'avertissement du § 3). Les **150** slots sont
  désormais une entrée versionnée, et un cliquet interdit qu'une citation fausse revienne.
  `case-477r24r1-mapping-slot-interface.md`.
- ~~**#477-r24-r2**~~ — **FERMÉ (2026-08-06), et la réponse n'était AUCUNE des deux proposées.**
  Le slot `0x55` n'est ni `RemoveUnit` (lecture de `#477-r19`, slot 6, **3** arguments) ni
  `RotateUnit` (crainte de cette tranche, slot `0x86`) : c'est
  **`UnregisterEntityFromTriggers`**, 2 paramètres — exactement ce que le site passe. La lecture
  de `#477-r19` a été corrigée, ainsi que `DRAIN_MESURE[ProcessRemovals]`. Effet de bord :
  `#477-r19-r1` (« le contenu de `System_ProcessRemovals` n'est pas porté ») est **dissous** — il
  n'y a pas de contenu, cette opération n'émet rien.
