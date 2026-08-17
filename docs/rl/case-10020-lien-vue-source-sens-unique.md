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

## 6. Ce qui change pour la suite — et la CONSOLATION annoncée ici a été RÉFUTÉE le même jour

La voie « remplir `+0x48` » est **fermée** par la poule-et-l'œuf du §3. La voie ouverte serait
d'**ancrer `HandleStartGame`** pour neutraliser la branche Draft — mais on ne sait pas ce qu'on
neutraliserait (§5).

⚠ **Ce paragraphe promettait un lot de consolation qui n'existe pas, et la correction est le seul
enseignement qui vaille ici.** Il déclarait la surface de déploiement « atteignable » et le choix
d'équipe « probablement à portée ». **Mesuré quelques heures plus tard, et négatif** :
`SandboxGameModeSource$$GetUnitsForDeploymentHUD`, ancrée sur une bataille RÉELLEMENT montée
(`sandboxModeStart`, stage 1 `Running`, 11 unités), rend **`fires: 0`** — elle n'est **JAMAIS
APPELÉE**. Le sandbox pré-place l'équipe et démarre directement : il n'y a pas de HUD vide à
remplir, **il n'y a pas de HUD**. Le stub n'était donc pas le bloqueur.

Six méthodes vivent bien sur `SandboxGameModeSource` sans dépendre d'aucun champ de vue —
`GetUnitsForDeploymentHUD`, `GetGameModeSpecificDeploymentHudOptions`, `GetUnlockedUnitsPooled`,
`GetBattleLineup`, `MinUnitsNeededToStartBattle`, `MaxUnitsPossibleToStartBattle`. Mais
**« ATTEIGNABLE » N'IMPLIQUE PAS « APPELÉE »**, et c'est exactement le pas que ce paragraphe avait
franchi sans le mesurer. Non-bloqueur vérifié au passage :
`IdunBattle.View.FSM.UnitDeployment.UnitDeploymentHudGameModeFactory$$Create` dispatche sur la
NON-NULLITÉ de champs d'options, pas sur un enum de mode, et retombe sur
`UnitDeploymentHudGameModeDefault` — ce n'est pas lui qui ferme la voie.

**LA QUESTION OUVERTE, qui est la vraie suite** : qu'est-ce qui fait entrer une bataille en
**PHASE** de déploiement au lieu de sauter en `Running` ? Pistes non explorées :
`MinUnitsNeededToStartBattle` / `MaxUnitsPossibleToStartBattle`, et le banc natif dédié
`battle_unit_deployment_test`.

**Et la voie qui reste ouverte est NOMMÉE ailleurs — c'est la face VUE, pas la face SOURCE.**
`#596` du backlog établit que le raycast est **HORS** du FSM (`IdunBattle.View.Game.InputEntityAdapter`
résout l'entité et la tuile, puis appelle le FSM avec elles), donc qu'on peut désigner la tuile
soi-même sans un pixel — et nomme l'étage :
`IdunBattle.View.FSM.UnitDeployment.UnitDeploymentState`, qui porte `OnUnitInHand(unitId,
isMachineOfWar)`, `OnFingerDownThisFrameInternal(mousePosition, entityHit)`,
`RemoveAllDeployedUnits` et `StartBattle(units)`. `BLOCAGE: capteur`.

Le module d'observation écrit pour la mesure ci-dessus vit dans
`frida/hooks/features/deployment-draft.ts`. Il est en régime **OBSERVER-d'abord** : il refuse de
remplir tant qu'aucune observation n'a établi la classe derrière le retour — c'est ce qui a évité
d'écrire dans un conteneur que rien ne lit.

## 7. LA QUESTION DU §6 EST RÉPONDUE — le gate a un NOM, et la sandbox répond `false`

**Mesuré le 2026-08-17, build `t6dpr4k06g`.** Décompilé pour la chaîne, **invocation sur les
objets VIVANTS** pour les deux valeurs.

### La chaîne, de bout en bout

```
idun.IdunMainView$$StartBattle(battleConfig, skipUnitDeployment)
    IdunMainView+0x120 <- skipUnitDeployment        # le drapeau est STOCKE, pas seulement passe
    ...
    IdunBattle.View.Game.IdunGameViews$$Enable(views, IdunMainView+0x120)

IdunBattle.View.Game.IdunGameViews$$Enable(this, skipUnitDeployment):
    si skipUnitDeployment == 0 :
        cVar1 = <appel d'interface slot 0x34>(this+0x138)      # _visualBattleQuery
        si cVar1 == 0 : UnitSelectionFsm$$StartMatch(this+0x70, false)   # -> DIRECT EN JEU
        sinon         : UnitSelectionFsm$$UnitDeployment(this+0x70)      # -> PHASE DE DEPLOIEMENT
    sinon :
        UnitSelectionFsm$$StartMatch(this+0x70, skipUnitDeployment)
```

Offsets **lus sur la classe vivante** (`classFields`), pas déduits : `IdunGameViews+0x60`
`_gameModeSource : IGameModeSource`, `+0x70` `_unitSelectionFsm`, `+0x138` `_visualBattleQuery`,
`+0x170` `_stateMachineActions`. Et le prédicat est un **relais pur** :

```
IdunBattle.View.FSM.VisualBattleQuery$$ShouldShowUnitDeploymentHud(this):
    return <appel d'interface slot 0x29>(this+0x80)     # _gameModeSource : IGameModeSource
```

⇒ **C'est la SOURCE DE MODE DE JEU qui décide s'il y a une phase de déploiement.** Le nom du
slot `0x29` est `ShouldShowUnitDeployment` (`IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$ShouldShowUnitDeployment`
est le seul porteur visible en table ; cf. la réserve ci-dessous).

### Les deux valeurs, MESURÉES sur les objets vivants

Sur une bataille sandbox montée (`fsmStateInvoke`, `voie: "pompe"`, `etatApres` inchangé) :

| appel | retour |
|---|---|
| `_actions._views._gameModeSource` → `ShouldShowUnitDeployment()` | **`Boolean false`** |
| `_visualBattleQuery` → `ShouldShowUnitDeploymentHud()` | **`Boolean false`** |

Les deux concordent, ce qui **confirme le relais** décompilé et l'appariement nom ↔ slot.

⇒ **Le `fires: 0` du §6 est expliqué, et ce n'est pas un stub qui manque : c'est la sandbox qui
DÉCLARE ne pas vouloir de phase de déploiement.** `Enable` prend donc la branche `StartMatch` et
le FSM naît en `NormalState` — jamais en `UnitDeploymentState`.

### ⚠ Ce que la TABLE ne pouvait pas dire, et qui a failli faire conclure de travers

`ShouldShowUnitDeployment` **n'apparaît sur AUCUNE source hors `CampaignGameModeSource`** dans
`frida/methods.tsv` — pourtant elle **existe** sur `SandboxGameModeSource` : `fsmStateMethods` sur
l'objet vivant la liste (**72 méthodes**), et elle répond. C'est la déduplication IL2CPP des corps
triviaux (`return false` = `xor eax,eax ; ret`), exactement le piège que le `CLAUDE.md` décrit —
appliqué ici sur la méthode qui commande tout le dossier. **Compter les porteurs en table aurait
rendu « une seule source gère le déploiement », ce qui est faux.**

⚠ **Corollaire, et c'est la limite du résultat** : puisque le corps est dédupliqué, on ne l'a
**pas lu**. On ignore si le `false` de la sandbox est une **constante** ou la lecture d'un champ.
S'il est constant, aucun réglage de BC ni de config ne le fera basculer — la seule voie serait de
coiffer le retour. Cette question est **ouverte**, et elle décide entre « paramétrable » et
« il faut un hook ».

⚠ **Mesure prise APRÈS coup** : le prédicat a été invoqué sur une bataille déjà lancée, pas au
moment où `Enable` l'a consulté. Rien n'établit qu'il valait la même chose à cet instant — c'est
cohérent (le FSM est bien en `NormalState`), ce n'est pas la même chose que mesuré.

### Le second gate, indépendant du premier

`skipUnitDeployment` est un **drapeau porté par `IdunMainView+0x120`**, écrit par `StartBattle` et
relu par `EnableBattle` comme par `StartNextBattle` (qui se le repasse à lui-même). Il court-circuite
le prédicat entièrement. Il est **exposé en paramètre** sur
`idun.IdunMainView$$idun.levelEditor.battleAndEditorFlow.IBattleAndEditorFlowActions.StartBattleOfActiveGameSource(skipUnitDeployment)`
— surface d'éditeur de niveau, non explorée.

⇒ Pour obtenir une phase de déploiement sur une sandbox il faut **les deux** : le drapeau à `0`
**et** le prédicat à `true`. Résidu **#10020-r1**.

### Ce que ça ne remet PAS en cause

Le déploiement manuel lui-même est **ACQUIS depuis le 2026-08-08** sur une bataille qui a sa phase
(`docs/rl/case-596-fsm-entree-par-entite.md`) : `StateMachineActions$$UnitDeployment_PlaceUnitOnBoard(unitId,
column, row, isManual, playerId)`, 5/5 unités posées sur l'hex demandé. Ce qui manquait n'a jamais
été le geste — c'est l'**entrée dans la phase**, côté sandbox.

⚠ Et le capteur du FSM est **déjà livré** (`frida/hooks/features/fsm-input.ts`, enregistré au
contrôleur, dans le bundle) : re-confronté ce jour sur `t6dpr4k06g`, `fsmStatus` rend
`classeTrouvee: true`, `captures: 2`, `pret: true`, et le `fsmMatchState` **égale** le match state
vivant. La ligne `#596` du backlog qui le présente encore comme une tranche à faire (`BLOCAGE:
capteur`) est **périmée** — vérifier le code avant de dispatcher, comme le `CLAUDE.md` le demande.

## 8. LE CORPS EST UNE CONSTANTE — et l'ancrer serait une CATASTROPHE, parce qu'il est PARTAGÉ

Suite directe du §7, même jour. Le corps dédupliqué a été lu par la voie propre : **résolution au
RUNTIME**, jamais une RVA de table.

```
resolveMethodPtr({targets: [{ns: "IdunBattle.ViewLogic.BattleSource",
                             cls: "SandboxGameModeSource", method: "ShouldShowUnitDeployment"}]})
```

| méthode | `ghidraVA` résolue au runtime |
|---|---|
| `SandboxGameModeSource$$ShouldShowUnitDeployment` | `0x1802b45a0` |
| `CampaignGameModeSource$$ShouldShowUnitDeployment` | `0x180515740` |

**Contrôle de la chaîne de résolution** : la campagne tombe sur `0x180515740`, soit exactement la
RVA `515740` que porte `frida/methods.tsv`. La conversion base runtime → base Ghidra est donc
vérifiée par un témoin indépendant, et pas seulement supposée.

### Le corps

```c
undefined1 Stash_Native_StashNative__get_IsPurchaseProcessing(void)
{
  return 0;
}
```

⇒ **C'est une CONSTANTE.** `SandboxGameModeSource$$ShouldShowUnitDeployment` ne lit aucun champ,
aucune option, aucun DTO. **Aucun réglage de BC, de gameconfig ou de `Sandbox*BattleConfig` ne le
fera jamais rendre `true`.** La question laissée ouverte au §7 — « paramétrable ou hook ? » — est
tranchée : **hook**.

Le nom qu'affiche Ghidra est celui d'une classe sans aucun rapport (`Stash.Native.StashNative`) :
c'est le propriétaire arbitraire que l'outil a retenu pour un corps mis en commun. Lire ce nom
comme celui de la fonction appelée serait un contresens complet.

### ⚠ ET C'EST ICI QUE LE REMÈDE ÉVIDENT EST UN PIÈGE

`Interceptor.attach(0x1802b45a0, { onLeave(r) { r.replace(1) } })` est **exactement ce qu'il ne
faut pas faire**. Xrefs de cette adresse, mesurées :

| type | compte | ce que c'est |
|---|---|---|
| `DATA` | **745** | autant de `MethodInfo` pointant sur CE corps |
| `UNCONDITIONAL_CALL` | 122 | appels directs |

⇒ **~745 méthodes du binaire partagent ce `return 0`.** Les coiffer ferait basculer à `true`
tout ce qui rend « faux constant » dans le jeu — `Stash.get_IsPurchaseProcessing` compris.

**LA RÈGLE, et elle généralise au-delà de ce dossier : un corps trivial DÉDUPLIQUÉ n'est pas
seulement ILLISIBLE en table, il est INHOOKABLE PAR ADRESSE.** Le dépôt savait que l'absence en
table ne prouve rien — c'était énoncé pour la LECTURE. Le versant ÉCRITURE est pire : l'adresse
résolue est juste, le hook s'installe sans erreur, et le dégât est massif et silencieux.
**Le témoin qui l'attrape est le COMPTE D'XREFS de l'adresse résolue** — deux chiffres, avant tout
`attach`.

### Le point d'ancrage correct est le relais, un étage au-dessus

`IdunBattle.View.FSM.VisualBattleQuery$$ShouldShowUnitDeploymentHud` — résolu au runtime sur
`0x18057fbc0`, ce qui concorde avec la table (`57fbc0`) — porte un **vrai corps** (le relais du §7)
et **2 xrefs DATA seulement** (son propre `MethodInfo` + son entrée de vtable). Il est donc
**spécifique** : le coiffer ne touche que la décision de déploiement.

`IdunBattle.View.Game.IdunGameViews$$Enable` (`0x1805a2840`, 1 paramètre) est le second candidat,
un cran plus haut encore.

⚠ **Ce que ça ne dit pas** : `VisualBattleQuery` sert **tous** les modes, pas seulement la sandbox.
Un hook qui force `true` doit donc être **armé explicitement** et se désarmer, sous peine de faire
apparaître une phase de déploiement là où le jeu n'en veut pas.

## 9. LE HOOK EST POSÉ — et son garde est prouvé DANS LES DEUX SENS

Livré dans `frida/hooks/features/deployment-draft.ts` (RPC `deploymentPhaseArmer` /
`deploymentPhaseStatus`). Deux ancrages, `forcer` **faux par défaut** — armer n'écrit rien.

| ancrage | rôle |
|---|---|
| `VisualBattleQuery$$ShouldShowUnitDeploymentHud` | lit le retour ; le remplace par `true` **si et seulement si** `forcer` |
| `IdunGameViews$$Enable` | **observation pure** : lit le `skipUnitDeployment` que le jeu passe |

Le second n'est pas décoratif : c'est lui qui dira si le drapeau court-circuite le prédicat, auquel
cas forcer le relais ne servirait à rien. **Sans lui, un forçage sans effet serait indiscernable
d'un forçage raté.**

### Le garde exécutable, et sa contre-épreuve

Une prose n'arrête pas un comportement : `armerPhase()` lit les 8 premiers octets du corps résolu
et **REFUSE** l'attache si un `ret` (`0xC3`) y tombe — critère mécanique de « corps constant, donc
probablement dédupliqué, donc partagé ». Le refus publie les octets.

**Mesuré des deux côtés, et c'est ce qui le rend non vacant** :

| corps | tête (8 octets) | `ret` à | verdict |
|---|---|---|---|
| relais `0x18057fbc0` | `40 53 48 83 ec 20 80 3d` | — | **passe** (prologue réel + garde de cctor) |
| `Enable` `0x1805a2840` | `48 89 5c 24 10 48 89 4c` | — | **passe** |
| source dédupliquée `0x1802b45a0` | `32 c0 c3 cc cc cc cc cc` | **octet 2** | **refuserait** (`xor al,al ; ret`) |

Un garde qu'on n'a jamais vu refuser ne prouve rien ; celui-ci discrimine les deux régimes qu'il
existe pour séparer.

⚠ **Les adresses résolues AU RUNTIME concordent avec la RE hors ligne** (`0x18057fbc0`,
`0x1805a2840`). C'est un contrôle, pas une redondance : la chaîne de résolution et la lecture Ghidra
sont deux sources indépendantes.

### ✅ LE RÉGIME OBSERVER EST CONFRONTÉ — et il rend le CONTRASTE

Warmup joué hook armé (bataille de **campagne**, chemin éprouvé, aucune sandbox impliquée) :

```
relaisFires: 1     relaisRetours: [1]              <- la CAMPAGNE rend TRUE
enableObservations: [{ skip: 0 }]                  <- skipUnitDeployment == 0
relaisForces: 0                                    <- forcer etait FAUX, rien n'a ete ecrit
Responding = True, delta CPU = 1,97                <- jeu vivant APRES coup
```

Trois choses tombent d'un coup :

1. **L'ancrage tire, et au bon moment** — une fois, à l'entrée en bataille.
2. **Le contraste est mesuré par le MÊME capteur** : `true` en campagne contre le `false` relevé
   en sandbox au §7. Ce n'est plus deux mesures de provenances différentes qu'on rapproche, c'est
   une seule sonde qui voit les deux régimes.
3. **`skip == 0` : le second gate est DÉJÀ OUVERT sur ce chemin.** Le drapeau ne court-circuite
   rien — donc forcer le relais suffirait, sans avoir à toucher `IdunMainView+0x120`. C'est
   précisément ce que l'ancrage sur `Enable` était là pour dire, et il l'a dit.

⚠ **Mesuré sur un départ de CAMPAGNE, pas de sandbox.** Rien n'établit que le chemin sandbox passe
par `IdunGameViews$$Enable` avec le même drapeau — il monte par `ViewCommandExecutor$$StartMatch` →
`thor.Loader$$LoadBattle`. `enableObservations` répondra au premier montage sandbox ; d'ici là,
la conclusion « un seul gate à forcer » ne vaut **que pour la campagne**.

⚠ **RESTE NON CONFRONTÉ** : `forcer` n'a jamais mordu (`relaisForces: 0`), et aucun FSM n'a été vu
naître en `UnitDeploymentState`. On a confirmé la sonde, pas encore l'effet.

⛔ **Et le montage qui manque a un COÛT connu** : confronter `forcer` demande une bataille sandbox,
dont la SORTIE est la voie létale documentée (§9 ci-dessous). Il faut donc prévoir la relance du
jeu **dans le plan**, pas la découvrir après.

### ⚠ CE QUE LA POSE A COÛTÉ — un warmup VERT sur un jeu qu'il venait de FIGER

Le reinject de cette tranche a été joué **alors qu'une bataille montée en sandbox était à
l'écran**. Le warmup, autonome, a fait son cycle (démarrer une bataille de campagne, capturer, se
retirer par `OnBattleSurrender` → `ContinueSurrender`) et a rendu **`ok: true` sur ses 13 crans**,
dont le dernier affirme « la scène meta est remontée, le jeu affiche un écran ».

**C'était faux à l'instant où il l'écrivait.** Relevé juste après : `Responding = False`, **delta CPU
nul** sur 1,5 s, et `thor.Loader.__loadingStep = 12` — la signature EXACTE, déjà documentée dans ce
dépôt, de la sortie d'une bataille montée en sandbox. Le jeu a dû être relancé à la main.

Deux enseignements, et le second est le vrai :

1. Le premier cran du warmup (`prog-etat-initial`) a rendu **« aucune bataille active »** alors
   qu'une sandbox tournait. C'est cette lecture aveugle qui l'a autorisé à enchaîner.
2. **Un `ok: true` de warmup ne prouve pas un jeu vivant.** Le discriminant est ailleurs :
   `Responding` + **delta CPU** + un RPC **queué** qui revient. Résidu **#10021**.

⚠ Et le hook n'y est **pour rien** — établi, pas supposé : `deploymentPhaseStatus` (RPC NON queué,
donc lisible sur un jeu figé) rendait `arme: false`, `ancrage: {relais: null, enable: null}`. La
callback d'armement attendait dans une file que le thread principal ne drainait plus. Le `500`
qu'elle a rendu était un timeout de file, pas une faute de son code — **le lire comme une faute du
dernier code écrit aurait envoyé chercher au mauvais endroit.**
