# #10020 — le lien vue↔source est à SENS UNIQUE : le Draft en sandbox ne peut pas démarrer

**Mesuré le 2026-08-17, build `t6dpr4k06g`, décompilé lu de bout en bout (6 fonctions).**

Question posée : peut-on **drafter** dans une sandbox ? La configuration existe et elle est
complète ; le montage, lui, part sur un throw. La cause n'est pas notre façon de monter — c'est
que **rien, dans tout le binaire tracé, ne remplit le champ que le chemin Draft lit**.

Ce document ferme aussi une inférence qui vivait en commentaire dans
`frida/hooks/features/sandbox-mode.ts` (« un sandbox Draft y buterait ») : elle est **juste**, et
elle était **trop large** — un seul des deux champs est en cause.

## 1. La configuration de draft existe, et elle est complète

```
IdunBattle.ViewLogic.BattleSource.SandboxBattleConfig.SandboxDraftBattleConfig$$.ctor(
    boardId, spawnPointSetIndex, player1, player2,
    powerUpUnits, player1DraftTurns, player2DraftTurns)
```

Noms de paramètres **lus dans le binaire**, pas devinés. Le ctor range `player1`/`player2`/
`powerUpUnits` en champs et replie `boardId` + `spawnPointSetIndex` + les deux compteurs de tours
dans un DTO interne. Deux joueurs, un pool de power-ups, un nombre de tours de draft chacun :
c'est un vrai draft, pas un vestige de nommage.

## 2. Le seul lecteur du champ, et sa condition

`IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$HandleStartGame` fait un test de type
sur la config, et **uniquement quand c'est un Draft** :

```c
if (config is SandboxDraftBattleConfig) {
    if (this+0x48 != 0) {                        // _stateMachineActions
        <appel d'interface slot 0x2e>(this+0x48, 0);
        if (this+0x48 != 0)
            return <appel d'interface slot 0x2e>(this+0x48, 1);
    }
    FUN_1801f5460();      // placeholder : le throw null-ref IL2CPP -- ne revient pas
}
return ...;               // tout autre mode : sort AVANT, sans rien lire
```

(`FUN_1801f5460` reste en VA déguisée : c'est un helper sans `MethodInfo`, il ne résout sur aucun
symbole. Cf. la règle « reste en VA, et c'est voulu ».)

**C'est exactement pourquoi l'onslaught est passé et pourquoi un draft ne passera pas** : tous les
autres modes sortent de `HandleStartGame` avant la lecture. Le Draft est le seul qui touche la
couche vue.

## 3. Personne ne remplit `+0x48` — quatre étages, tous négatifs

`SandboxGameModeSource` fait **88 octets = `0x58`** (`data/symbols/t6dpr4k06g/frida/classes.tsv`),
soit **9 champs** de `+0x10` à `+0x50`.

**a. Le ctor — il n'y en a qu'un — en remplit 5.**

```
IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$.ctor(
    sandboxConfig, unitProgression, gameConfig, logger, featureUnlocker)

+0x18 sandboxConfig   +0x20 unitProgression   +0x28 gameConfig
+0x30 logger          +0x40 featureUnlocker
```

Restent NULS : `+0x10`, `+0x38`, **`+0x48`**, `+0x50`.

**b. Les deux appelants du ctor ne remplissent rien de plus.**

| appelant | ce qu'il fait |
|---|---|
| `idun.shared.commands.ViewCommandExecutor$$StartSandboxMatch` | prend `unitProgression`/`logger`/`featureUnlocker` sur l'exécuteur, construit la source, l'installe dans le statique du match courant, puis `thor.Loader$$LoadBattle` |
| `idun.Idun.Source.IdunBattle.View.IdunSandboxSceneMain$$StartBattle` | idem via `thor.Globals$$Get` ; pose en plus un `Nullable` sur l'objet-match, pas sur la source |

**c. `IdunBattle.View.Game.IdunGameViews$$.ctor` (38 paramètres) REÇOIT la source** — 7ᵉ paramètre,
fourni par `idun.IdunMainView$$LoadGameViews`. Il la range **chez lui** à `+0x60`, la transmet à
`StateMachineActions`, `SpawnPoints` et `UnitSelectionFsm` — **et n'écrit jamais dedans**. Un seul
appel d'interface sur elle dans tout le corps : **slot `0xd`**, avec le `MessageExecutionQueue`.

**d. `IdunBattle.View.FSM.StateMachineActions$$.ctor` (23 paramètres) reçoit la source** aussi
(18ᵉ paramètre), la range à `+0x100` — **et n'écrit jamais dedans** non plus.

> **Le lien est à SENS UNIQUE : la couche vue connaît la source ; la source ne connaît jamais la
> couche vue.** Et c'est `IdunGameViews$$.ctor` qui CONSTRUIT le `StateMachineActions` (`+0x170`),
> donc l'objet n'existe même pas avant le chargement de la scène — alors que `HandleStartGame`
> tire **pendant**. Remplir le champ après coup ne suffirait pas : il faudrait le remplir avant
> que son producteur existe.

## 4. L'indice qui recadre : ce n'est pas un hook générique de source

`HandleStartGame` n'existe que sur **trois** classes du binaire :

- `IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource`
- `IdunBattle.ViewLogic.BattleSource.SyncPvpGameModeSource`
- `IdunBattleLogic.Synchronous.SynchronousNetwork`

C'est la famille **synchrone / réseau**, pas un cran du cycle de vie de toute source. Un draft est
un échange de tours entre deux joueurs — d'où la parenté avec le PvP synchrone, et d'où le fait que
la pièce manquante soit précisément celle-là. Le chemin Draft du sandbox ressemble à du code de
développement laissé incomplet dans le build livré.

## 5. Ce que ce verdict ne couvre PAS

- **Un setter trivial serait INVISIBLE.** `set__stateMachineActions { … }` compile en
  `mov [rcx+0x48], rdx ; ret` — exactement le genre de corps qu'IL2CPP **déduplique**, donc absent
  de la table des symboles. « Personne ne le pose » est établi **sur le chemin tracé** (4 étages),
  pas prouvé dans l'absolu. Cf. la règle « l'absence dans la table ne prouve RIEN ».
- **L'interface du slot `0x2e` n'est pas résolue.** Même le champ rempli, on ignore ce que la
  branche Draft ferait. Aucun nom de méthode n'est avancé ici, volontairement.
- **Rien n'a été joué sur le jeu.** Lecture pure ; aucun montage Draft n'a été tenté (il partirait
  sur le throw, et un throw natif remonte en « system error » qui ne nomme rien).

## 6. Ce qui change pour la suite — le lot de consolation vaut mieux que le lot principal

La voie « remplir `+0x48` » est **fermée** par la poule-et-l'œuf du §3. La voie ouverte serait
d'**ancrer `HandleStartGame`** pour neutraliser la branche Draft — mais on ne sait pas ce qu'on
neutraliserait (§5).

**En revanche, la surface de DÉPLOIEMENT n'est PAS derrière cette branche.** Six méthodes vivent
sur `SandboxGameModeSource` et ne dépendent d'aucun champ de vue :

```
GetUnitsForDeploymentHUD          GetGameModeSpecificDeploymentHudOptions
GetUnlockedUnitsPooled            GetBattleLineup
MinUnitsNeededToStartBattle       MaxUnitsPossibleToStartBattle
```

Elles sont donc atteignables **sur un mode non-Draft** — c'est-à-dire sur l'onslaught qu'on sait
déjà monter (`sandboxModeStart`) et dont on sait déjà **sortir** (retraite éprouvée le 2026-08-16).
Choisir son équipe et la déployer dans une sandbox est probablement à portée ; c'est le draft à
deux joueurs qui ne l'est pas.

**NON CONFRONTÉ** : aucune de ces six méthodes n'a été appelée. C'est le prochain montage.
