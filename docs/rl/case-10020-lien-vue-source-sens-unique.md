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

## 10. ✅ FORCÉ POUR DE VRAI — l'écran de déploiement s'ouvre sur une sandbox, et le roster se remplit

Mesuré le 2026-08-17, session 30. **Confirmé À L'ÉCRAN par l'utilisateur**, pas seulement par des
compteurs.

```
relaisRetours: [0]         la sandbox rend FALSE
relaisForces: 1            remplace par TRUE
etatCourant                "UnitDeploymentState"        <- la phase EXISTE
enableObservations         [{ skip: 0 }]                le drapeau n'y est pour rien
```

**Le roster était VIDE**, et c'est le stub du §6 qui revient — cette fois APPELÉ. Le chemin réel,
décompilé :

```
StateMachineActions$$UnitDeployment_ShowHud(callbacks)
    <slot 0x2b sur _source>  -> PooledList          = GetUnitsForDeploymentHUD
    MapAsList(converter)     -> List<IUnitModel>
    <slot 0xe sur _hud>(units, options, callbacks)   = IdunGameHud$$UnitDeployment_ShowHud
```

⚠ **Le stub ne tirait pas parce que l'ÉCRAN N'ÉTAIT PAS RECONSTRUIT** — `relaisFires` figé, le
second `sandbox_mode start` ayant été un no-op (le script prévient lui-même que « l'appel est
passé » ne dit rien du montage). **`Enter()` rejoué sur l'état courant le reconstruit**, et le stub
tire. C'est le geste qui manquait, et il ne coûte rien.

### Le refus du module a MESURÉ la forme du conteneur

```
`Add` (1 param) INTROUVABLE sur `PooledListElement`1` -- NE RIEN ÉCRIRE
```

Le retour est un **wrapper de pool**, pas la liste : `classFields` sur la classe VIVANTE donne
`_object : List\`1`, hérité de `PooledElement\`1`. **C'est le garde qui a établi la forme** — sans
son exigence de trouver `Add`, la première version aurait écrit dans le wrapper.
Correctif : descente d'un cran, champ résolu **par son nom** (`getFieldOffset`, qui remonte la
chaîne de parents), voie publiée. Résultat :

```
dernierRemplissage: { ajoutes: 5, erreur: null, voie: "PooledListElement`1._object -> List`1" }
```

⇒ **Le roster affiche les unités.** Objectif de la tranche atteint : une sandbox avec écran de
déploiement peuplé, ce que le jeu ne fait jamais.

### ⚠ LA POSE REFUSE ENCORE — et la porte a CINQ gardes, tous MUETS

`idun.ui.UnitDeploymentHud$$TryMarkUnitAsPlaced` rend `false` sans rien dire. Champs **nommés sur la
classe vivante** (`classFields`), jamais cités par offset nu :

| champ | garde |
|---|---|
| `_disabledInput` | vrai ⇒ refus |
| `_unitProgression` | désaccord sur `isMachineOfWar` ⇒ refus |
| `_currentlyPlacedUnits` / `_maxUnitsPossible` | `count >= max` ⇒ refus |
| `_currentlyPlacedUnits` | contient déjà l'unité ⇒ refus |
| `_allUnlockedUnitModels` | `TryGetValue` échoue ⇒ refus |
| `_unitDeploymentHudGameMode` | slot 8 rend faux ⇒ refus |

`UnitDeployment_PlaceUnitOnBoard` étant **`void`**, un refus au cran 1 est **totalement
silencieux** — d'où l'obligation de lire `TryPlaceUnitOnBoard` séparément pour le voir.

**Mesures qui ORIENTENT** : `MaxUnitsPossibleToStartBattle` = **5**, `MinUnitsNeededToStartBattle` =
**3** (invoqués sur la source vivante) — la source n'est donc PAS stubbée là-dessus, hypothèse
écartée. Et l'utilisateur voit **5 unités déjà déployées** : le sandbox **pré-place son équipe**,
donc `count(_currentlyPlacedUnits)` vaut vraisemblablement 5 pour un plafond de 5.

⚠ **Mais `HandleOnRemoveAllHeroesPressed()` n'a PAS débloqué** (porte toujours `false` après), et
`GetPlayerPower()` rend **0 avant comme après** — donc ce témoin-là ne mesure rien ici et **ne doit
pas servir à conclure**. Deux candidats restent, non départagés :

1. le `Clear` ne vide pas `_currentlyPlacedUnits` (ou la pré-pose vient de la BC, hors HUD) ;
2. garde `_allUnlockedUnitModels` — nos ids injectés n'ont pas de `IUnitModel` associé, la
   conversion `MapAsList` les affichant sans les enregistrer.

**La mesure qui tranche** : lire les COMPTES de `_currentlyPlacedUnits` et `_allUnlockedUnitModels`
sur le HUD vivant. Aucun RPC ne le fait aujourd'hui — c'est le prochain geste, et il est en lecture
pure.

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

## 11. LE ROSTER NE S'INJECTE PAS LIBREMENT -- son vivier vient de la BC

Mesure du 2026-08-17, session 30. Trois faits qui recadrent la tranche.

**a. Le remplissage atteint l'ecran, mais SEULEMENT pour les unites DE LA BC.** Le lot de 5 --
exactement les `--units` du montage -- a fait passer le roster de VIDE a 5 visibles (confirme a
l'ecran par l'utilisateur). Les lots de 40 puis 18 ids **etrangers a la bataille** rendent
`ajoutes: 40` / `18` sans erreur cote conteneur, **puis font LEVER la reconstruction** : `Enter()`
rend `system error` en **0,2 s**. La duree est le discriminant : elle exclut l'hypothese
<< reconstruction trop lente >> que le premier 500 avait suggeree, et que j'ai d'abord retenue.

=> **Le << n >> de << 5 max parmi n >> vient de la BC, pas du hook.** Le levier est
`sandbox_mode.py start --units <n ids>`. Injecter le roster reste utile pour OBSERVER le contrat du
stub ; ce n'est pas la voie pour composer un vivier.

**b. Un second `start` dans la MEME session est un NO-OP pour la scene.** Apres un montage reussi,
tout `start` suivant rend de nouveaux pointeurs source/config et **n'appelle pas**
`IdunBattle.View.Game.IdunGameViews$$Enable` -- `relaisFires` reste fige. Seul le PREMIER montage
apres une session fraiche reconstruit. Le script l'annonce deja (<< l'appel est passe >> ne dit rien
du montage) ; le compteur du hook en fait une **mesure** au lieu d'un avertissement.
=> toute variation de `--units` exige un cycle propre.

**c. `GetPlayerPower()` ne mesure RIEN dans ce regime** -- il rend 0 avant comme apres un `Clear`,
avec ou sans unites au roster. Ne pas s'en servir pour conclure ici, contrairement a l'usage qu'en
fait `case-596` sur une bataille de campagne. Un temoin valide ailleurs ne l'est pas partout.

## 12. IL Y A **DEUX** STUBS, PAS UN -- et c'est le second qui bloque la pose

Mesure du 2026-08-17, session 31. Le montage a 12 unites a fait tomber les deux hypotheses
precedentes d'un coup, et designe le vrai bloqueur.

### Ce que le montage a 12 a montre

Les **12 unites de `--units` sont sur le PLATEAU** (confirme a l'ecran) -- le sandbox pre-place tout
ce que la BC porte, et **deborde meme le plafond** `MaxUnitsPossibleToStartBattle = 5`.
Pendant ce temps `GetPlayerPower()` rend **0** et la porte de pose refuse toujours.

=> **Les deux couches sont DECOUPLEES** : le sandbox spawne ses unites directement dans la
bataille, et le HUD de deploiement est une couche VIDE posee par-dessus. Le garde `count >= max`
est donc HORS DE CAUSE : `_currentlyPlacedUnits` est vide (d'ou le `PlayerPower` a 0), pendant que
le plateau porte 12 entites.

### Le vrai bloqueur : un SECOND stub, symetrique du premier

```
IdunBattle.ViewLogic.BattleSource.SandboxGameModeSource$$GetUnlockedUnitsPooled(this):
    return DictionaryPooler<K,V>.Get()      # dictionnaire FRAICHEMENT LOUE, aucun champ de `this` lu
```

C'est lui qui alimente `UnitDeploymentHud._allUnlockedUnitModels`, et c'est ce dictionnaire que
consulte le garde `TryGetValue` de `TryMarkUnitAsPlaced`. Vide => **toute pose est refusee, quel que
soit ce qu'on affiche**.

⚠ **D'ou l'erreur de methode que j'ai commise pendant deux heures** : les six methodes de la source
se repartissent en DEUX ROLES, et je les traitais comme une seule surface.
`GetUnitsForDeploymentHUD` alimente **l'AFFICHAGE** (le remplir marche : `ajoutes: 12`, roster
visible), `GetUnlockedUnitsPooled` alimente le **MODELE** que la pose interroge. Remplir le premier
ne peut pas debloquer le second, et aucune quantite de sondage du HUD ne l'aurait dit -- il fallait
lire le corps.

### La recette est ECRITE dans la version campagne, et l'ingredient est DEJA LA

```
CampaignGameModeSource$$GetUnlockedUnitsPooled(this):
    <slot 0x15 sur this+0x20 = unitProgression>(Nullable(this+0x70), 1)   -> PooledList
    .Map(converter)                                                        -> Dictionary poole
```

**`SandboxGameModeSource` porte le MEME `unitProgression` a `+0x20`** -- 2e parametre de son ctor,
etabli au SS3. La sandbox a donc la vraie progression du compte sous la main **et ne s'en sert
pas**. Le correctif est un mirror 1:1 de la version campagne, pas une invention.

⚠ **Ce que ca coute de plus que le premier stub** : le retour n'est plus une `List<String>` mais un
**Dictionary<UnitConfigId, IUnitModel>** -- cles STRUCT et valeurs OBJET. On ne peut pas le peupler
avec des chaines comme on l'a fait pour l'affichage ; il faut faire produire les modeles par la
progression elle-meme, c'est-a-dire rejouer l'appel de la campagne.

### Etat de la tranche

| | |
|---|---|
| phase de deploiement forcee sur sandbox | **ACQUIS**, confirme a l'ecran |
| roster AFFICHE peuple | **ACQUIS** (`ajoutes: 12`, ids de la BC uniquement) |
| pose d'une unite | **BLOQUE** par `GetUnlockedUnitsPooled`, recette identifiee |

## 13. ⚠ CORRECTION DU SS12 -- `GetUnlockedUnitsPooled` n'est JAMAIS APPELEE, et le mirror est INERTE

Mesure du 2026-08-17, session 32, mirror arme et confirme.

Le SS12 enonce comme un FAIT que `GetUnlockedUnitsPooled` << alimente
`UnitDeploymentHud._allUnlockedUnitModels` >>. **C'est FAUX**, et c'est mon propre hook qui le
refute : ancre sur `SandboxGameModeSource$$GetUnlockedUnitsPooled`, il rend **`fires: 0`** apres le
montage ET apres un `Enter()` de reconstruction. La methode n'est pas appelee sur ce chemin.

L'enchainement etait plausible -- meme classe, meme famille de nom, un dictionnaire des deux cotes --
et je l'ai ecrit sans l'avoir mesure. C'est exactement la faute du SS6 (<< atteignable >> lu comme
<< appelee >>), commise une seconde fois dans le meme dossier.

**La piste qui reste** : `idun.ui.UnitDeploymentHud$$Init(logger, unitProgression, featureUnlocker,
battlePassProgression, crusadeProgression, liveEventsProgression, heroReleaseEventProgression)` --
le HUD porte SA PROPRE progression et construit vraisemblablement son dictionnaire LA, une fois,
hors de tout mode de jeu. Si c'est le cas, le dictionnaire n'est pas vide et le garde qui refuse est
un AUTRE des cinq -- `_disabledInput` etant le plus credible pour un HUD que le sandbox n'affiche
jamais. **Non mesure** : departager exige de lire les champs du HUD vivant, ce qu'aucun RPC ne fait.

### Ce qui est livre malgre tout

`deploymentPoolArmer` / `deploymentPoolStatus` (`frida/hooks/features/deployment-draft.ts`) --
mirror par EMPRUNT a la source campagne vivante. Il est **arme, resolu et inerte** :

```
ancrage sandbox   0x18053cc10     (identique a la RE hors ligne)
ancrage campagne  0x1805121c0     (identique)
sourceCampagne    capturee, non nulle
fires             0
```

⚠ Il reste utile comme **capteur negatif** : c'est lui qui etablit le `fires: 0`. Et son refus
d'armer sans `CampaignGameModeSource` capturee documente une dependance reelle au warmup.

⚠ **Pourquoi l'emprunt plutot qu'un port** : `CampaignGameModeSource$$GetUnlockedUnitsPooled` lit
`this+0x20` ET `this+0x70` ; or `SandboxGameModeSource` fait **0x58 octets**, il n'a PAS de `+0x70`.
Rejouer ce corps sur un `this` sandbox lirait hors des bornes. L'emprunt evite l'invention -- au
prix d'un ecart non mesure (les unites debloquees << selon la campagne >>).

## 14. LE PLAFOND D'UNITES EST GLOBAL, ET NOTRE OUTILLAGE LE CONTOURNE SANS RIEN DIRE

Trouve par l'utilisateur (<< c'est pas normal que tu aies reussi a deployer plus d'unites que ce que
la BC autorise >>), puis mesure.

```
SandboxGameModeSource$$MaxUnitsPossibleToStartBattle(this):
    return *(this+0x28 = gameConfig)->+0x10->+0x80
```

C'est une valeur **GLOBALE du gameconfig** (5), pas une propriete de la BC : elle rend **5** aussi
bien sur un montage a 5 unites que sur un montage a **12**. Et le chemin de PRE-PLACEMENT du sandbox
ne la consulte jamais -- seul le HUD de deploiement s'en sert, or le sandbox ne l'affiche pas.

=> **`sandbox_mode.py start --units` accepte et place N unites sans aucun controle**, et produit
une BC que le jeu ne fabriquerait jamais (12 heros poses pour un plafond de 5). Ce n'est pas un bug
du jeu : c'est un piege de notre outillage, et il fabrique un specimen hors-spec sur lequel on
diagnostique ensuite le HUD. Garde a poser : refuser (ou au moins NOMMER) un `--units` plus long que
`MaxUnitsPossibleToStartBattle`.

## 15. LE GARDE EST `IsUnlocked` -- et `Show` alimente le dictionnaire LUI-MEME

Decompile de `idun.ui.UnitDeploymentHud$$Show(units, minUnitsPossible, maxUnitsPossible,
gameModeSpecificOptions)`, le 2026-08-17. Il repond a toutes les questions ouvertes du SS13.

```c
this+0x228 = maxUnitsPossible      this+0x224 = minUnitsPossible
this+0x230 = units                 this+0x22c = 0        // _disabledInput remis a FAUX ici meme
foreach (u in units) {
    Dictionary.Add(this+0x240, configId(u), u)                  // TOUS les modeles
    if (IdunMetaLogic.UserProgress.Model.IUnitModelExtensions$$IsUnlocked(u))
        Dictionary.Add(this+0x248, configId(u), u)              // _allUnlockedUnitModels
}
```

**TROIS CHOSES TOMBENT.**

1. **`_allUnlockedUnitModels` EST alimente par la liste qu'on injecte** -- via `Show`, donc via
   `GetUnitsForDeploymentHUD` -> `MapAsList`. Le SS12 avait raison sur la CIBLE (c'est bien ce
   dictionnaire que le garde interroge) et tort sur la SOURCE (ce n'est pas
   `GetUnlockedUnitsPooled`, cf. SS13). Le mirror est donc inutile a ce blocage.

2. **LE FILTRE EST `IsUnlocked(u)`.** Seuls les modeles DEBLOQUES entrent dans le dictionnaire que
   `TryMarkUnitAsPlaced` consulte. C'est exactement l'ecart mesure : le roster S'AFFICHE (depuis
   `_units`, `+0x230`, sans filtre) et la pose REFUSE (rien n'a passe `IsUnlocked`).
   => La question n'est plus << pourquoi le dictionnaire est-il vide >> mais **<< pourquoi nos
   modeles ne sont-ils pas DEBLOQUES >>**, ce qui porte sur le CONVERTISSEUR de `MapAsList`.

3. **`_disabledInput` N'A JAMAIS ETE LE BLOCAGE** : `Show` le remet a `0` lui-meme. Le test
   `UpdateDisableInput(false)` (garde inchange apres) etait donc juste, mais pour une raison que je
   n'avais pas : le champ etait deja faux. Le setter, lui, ecrit bien `this+0x22c` -- verifie au
   decompile, la conclusion n'etait pas vacante.

⚠ **Et `Show` FILTRE ENCORE APRES** : `List.RemoveAll(units, predicate)` avant
`ShowStandardUnitSelection`. Ce que le joueur voit n'est donc pas exactement ce qu'on a injecte.

### Ce que ca laisse comme prochain geste

Invoquer `IUnitModelExtensions$$IsUnlocked` sur un modele issu du convertisseur, et regarder
pourquoi il rend faux. Deux directions, non departagees : le convertisseur fabrique un modele
MINIMAL depuis la seule chaine d'id (donc sans etat de possession), ou il resout contre une
progression qui n'est pas celle du compte.

⚠ **NE PAS conclure de la reussite de l'AFFICHAGE que les modeles sont valides** : c'est
precisement l'ecart que ce paragraphe explique, et c'est la troisieme fois dans ce dossier qu'un
succes visible masque un contrat non rempli (apres << atteignable != appelee >> au SS6, et
<< meme famille de nom => meme role >> au SS12).

## 16. LE PLAFOND VARIE PAR NOEUD -- le SS14 ne vaut QUE pour la sandbox

Precision apportee par l'utilisateur : **certains noeuds de campagne n'autorisent que 3 heros.**

Le SS14 mesure `SandboxGameModeSource$$MaxUnitsPossibleToStartBattle`, qui lit
`gameConfig->+0x10->+0x80` -- une valeur GLOBALE. Cette lecture est juste **pour la sandbox**, et
le SS14 ne doit pas se lire comme << le plafond du jeu est 5 partout >>. Chaque source a SA
methode ; celle de la campagne lit vraisemblablement le noeud, et le `Min = 3` releve au SS10 est
coherent avec un plafond qui varie par bataille.

=> Le garde a poser sur `sandbox_mode.py --units` compare a la valeur de **la source montee**,
jamais a un 5 ecrit en dur.

## 17. UNITE OBLIGATOIRE -- le mecanisme existe, et mon premier candidat etait FAUX

Signale par l'utilisateur : **des events rendent obligatoire le deploiement d'une unite donnee.**

J'ai d'abord attribue ca a un bloc de `Show` qui filtre par un predicat et remplit une liste :

```c
if (<slot 0x37 sur le modele>(u)) { List.Add(this+0x250, u); this+0x222 = 1; }
```

**FAUX.** `classFields` sur la classe VIVANTE nomme les deux champs : `+0x250` = **`_mows`**,
`+0x222` = **`_hasMachinesOfWar`**. Ce bloc separe les **Machines of War**, il n'a aucun rapport
avec une unite obligatoire. Le predicat du slot `0x37` est un `IsMachineOfWar`, pas un `IsRequired`.

⚠ C'est la **quatrieme** fois dans ce dossier qu'une inference par le NOM ou la FORME aurait fait
ecrire un faux (apres << atteignable != appelee >> SS6, << meme famille de nom => meme role >> SS12,
et `GetUnlockedUnitsPooled` jamais appelee SS13). Le remede est le meme a chaque fois et il est
bon marche : **nommer les champs par `classFields` avant d'ecrire une phrase sur eux.**

### Le vrai mecanisme, nomme mais NON CONFRONTE

```
IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$HasGameModeReasonNotToStartMatch(
    units: List<String>, reasonNotToStartMatch: GameModeReasonNotToStartMatch&) -> Boolean
IdunBattle.View.FSM.StateMachineActions$$HandleReasonNotToStartMatch(reasonNotToStartMatch)
idun.ui.UnitDeploymentHud$$SortUnitsWithRequiredFirst(unitA, unitB) -> Int32
```

C'est la porte du bouton **Start!** : elle recoit la composition et rend un MOTIF de refus type.
Cote catalogue, `requiredUnits` existe sur les noeuds de campagne (releve dans `case-596`, ou il est
etabli qu'il designe le trio de la CAMPAGNE et ne discrimine pas le noeud -- a ne pas confondre avec
l'obligation d'event decrite ici).

**NON MESURE** : quelle source porte l'obligation d'event, et si `SandboxGameModeSource` la porte du
tout. A instruire avant toute conclusion.

## 18. LA CHAINE EST COMPLETE -- et les restrictions vivent sur la **SOURCE**, pas sur la BC

Recadrage donne par l'utilisateur (<< si c'est pas la BC qui contient les restrictions c'est la
gameModeSource >>), et le decompile le confirme de bout en bout.

### Le chemin complet, du roster a la pose

```
StateMachineActions$$UnitDeployment_ShowHud(callbacks)
  <slot 0x2b sur _source>  GetUnitsForDeploymentHUD      -> PooledList<String>   [STUB sandbox]
  MapAsList(convertisseur) ................................ String -> IUnitModel
  <slot 0xe sur _hud>      IdunGameHud$$UnitDeployment_ShowHud(units, options, callbacks)
     UnitDeploymentHud$$Show(units, min, max, options)
        _units <- units                     (AFFICHAGE, sans filtre)
        si IsUnlocked(u) : _allUnlockedUnitModels[configId] <- u    (LE DICTIONNAIRE DE LA POSE)

convertisseur = StateMachineActions$$<UnitDeployment_ShowHud>b__118_0(unitId):
     return <slot 0x27 sur this+0x100 = LA SOURCE>(unitId, false)   = GetUnitModel

IUnitModelExtensions$$IsUnlocked(u) = <slot 0x17 sur u>() == 0
```

### Le verrou, lu au corps

```c
SandboxGameModeSource$$GetUnitModel(this, unitId, isPvpEnemyUnit):
    prog = this+0x20                                  // le vrai IUnitProgression du compte
    si <slot 0x2b>(prog, unitId) OU <slot 0x2c>(prog, unitId) :
        return <slot 0x1a>(prog, unitId, true)        // MODELE REEL de progression
    si (cfg = this+0x18) est un `SandboxCampaignEventBattleConfig` et cfg.Player1Type != 0 :
        return <slot 0x1c>(prog, unitId)              // autre modele reel
    return new IdunMetaLogic.UserProgress.Model.HotseatUnitModel(unitId, prog, 2, 0, 0)
```

⇒ **Le sandbox fabrique un `HotseatUnitModel`** -- un modele de banc d'essai, pas un modele de
compte -- et c'est lui qui echoue a `IsUnlocked`. D'ou : le roster S'AFFICHE, le dictionnaire reste
VIDE, et **toute pose est refusee**.

**DEUX SORTIES existent, et toutes deux sont sur la SOURCE ou sa CONFIG** :
1. les deux predicats de progression en tete (slots `0x2b` / `0x2c`, avec un `unitId`) -- selon
   toute vraisemblance une verification de POSSESSION. Corroboration independante : le RPC
   `rosterOwned` cherche une methode nommee **`HasUnitUnlocked`** ;
2. la branche `SandboxCampaignEventBattleConfig` + `Player1Type != 0` -- inatteignable en mode
   `waves` (le test de type echoue ; `SandboxWavesBattleConfig` n'a meme pas de champ a `+0x34`,
   verifie par `classFields` sur les neuf configs).

⚠ **`rosterOwned` est CASSE sur `t6dpr4k06g`** : il rend `HasUnitUnlocked NON RESOLUE`. La
possession n'est donc PAS mesurable par cette voie aujourd'hui -- l'hypothese (1) reste **NON
CONFRONTEE**, et il ne faut pas l'ecrire comme etablie.

### LE RECADRAGE, et c'est le vrai enseignement de la tranche

**TOUTES les portes rencontrees sont des methodes de `IGameModeSource`** -- `GetUnitModel`,
`GetUnitsForDeploymentHUD`, `GetUnlockedUnitsPooled`, `Min`/`MaxUnitsNeededToStartBattle`,
`HasGameModeReasonNotToStartMatch`, `ShouldShowUnitDeployment`. **Aucune n'est un champ de la BC.**

J'ai passe la tranche a chercher cote BC (`--units`, factions, `Units[]`) ce qui est cote SOURCE :
c'est ce qui m'a fait injecter 40 ids etrangers, puis 18, puis raisonner sur les factions
imperiales. Le sandbox n'a pas << des restrictions vides >> : sa source REPOND VIDE ou FAUX a tout
ce que la couche deploiement lui demande.

⇒ Rendre le deploiement utilisable en sandbox = **faire repondre la SOURCE comme une vraie
source**, methode par methode. Le mirror du SS13 en visait une (la mauvaise) ; `GetUnitModel` est
celle qui commande la pose.

## 19. LE WRAPPER MARCHE -- mais on n'emprunte pas des REGLES, on emprunte un ETAT

Livre le 2026-08-17 (session 33) : `deploymentPoolArmer` n'est plus un mirror ponctuel mais une
**table de delegation**. Chaque methode d'`IGameModeSource` que la sandbox stubbe est ancree, et
son retour est remplace par celui de la MEME methode invoquee sur la source CAMPAGNE vivante.
Direction donnee par l'utilisateur : << il faut que la sandbox soit un wrapper sur une vraie
source >>.

### La table, et ce que chaque entree apporte

| methode | role | ancrage sandbox / campagne |
|---|---|---|
| `GetUnitModel` | commande la POSE | `0x18053ca00` / `0x180511f80` |
| `GetGameModeSpecificDeploymentHudOptions` | apporte les RESTRICTIONS | `0x18053c8e0` / `0x180511370` |
| `GetUnitsForDeploymentHUD` | apporte le ROSTER | `0x18053cb90` / `0x180511fe0` |
| `GetUnlockedUnitsPooled` | dictionnaire des debloques | `0x18053cc10` / `0x1805121c0` |

⚠ `CampaignGameModeSource$$GetUnitModel` est **ABSENTE de `methods.tsv`** et existe pourtant
(resolue au runtime a `0x180511f80`, arite 2, depth 0). **CINQUIEME** occurrence du piege de
deduplication dans ce seul dossier.

### Mesure : le mecanisme est bon, le preteur est VIDE

```
GetGameModeSpecificDeploymentHudOptions   fires 1  emprunts 1   -> substitue
GetUnitsForDeploymentHUD                  fires 1  emprunts 1   -> substitue
GetUnitModel                              fires 0
```

La delegation TIRE et SUBSTITUE : le mecanisme est demontre. Mais `GetUnitModel` n'est jamais
appele, donc le **convertisseur n'a pas tourne**, donc la liste empruntee etait **VIDE**.

**CAUSE : le preteur est INACTIF.** La `CampaignGameModeSource` capturee a ete **retiree de sa
bataille par le warmup** (cf. SS9 : le cycle de warmup ouvre une bataille de campagne, capture, puis
se retire). Elle prete donc l'etat d'une source au repos.

### CE QUE CA ETABLIT, ET C'EST L'OBJECTION DE L'UTILISATEUR, VERIFIEE

<< C'est bizarre que des conditions specifiques a un noeud soient fournies par la source. >>
Reponse mesuree : **la source ne STOCKE pas les regles, elle porte l'IDENTITE du noeud et les
RESOUT.** `classFields` sur `CampaignGameModeSource` :

```
+0x68  _currentCampaignId      String
+0x70  _currentLocationIndex   Int32
+0x78  _currentMatch           CampaignConfigDto      <- la config RESOLUE du noeud
```

C'est un **RESOLVEUR lie a une selection courante**, pas un magasin de regles. Donc :

⇒ **DELEGUER IMPORTE UN ETAT, PAS DES REGLES.** On n'obtient pas << les vraies regles >> mais
<< celles du noeud ou le preteur pointe >> -- et s'il ne pointe nulle part, on emprunte du vide.
Mon argumentaire de la veille (<< faire repondre la source comme une vraie source >>) surestimait
donc le wrapper : il fait IMPERSONNER UN NOEUD PARTICULIER, ce qui n'est pas la meme chose.

**La suite, et elle est nommee** : rendre le preteur ACTIF sur un noeud CHOISI -- ecrire
`_currentCampaignId` / `_currentLocationIndex` et faire re-resoudre `_currentMatch`. **NON MESURE**,
et un DTO deja resolu deviendrait perime : c'est une tranche a part entiere, pas un reglage.

## 20. POSITIONNER LE PRETEUR : la recette EXISTE, et elle interdit qu'on la TIENNE OUVERTE

Le SS19 laissait comme suite << rendre le preteur actif sur un noeud choisi >>. Mesure : **c'est
deja ecrit**, dans `frida/hooks/features/campaign-builder.ts`, et la forme de ce qui est ecrit est
elle-meme la reponse.

### La recette, telle qu'elle est deja livree

`buildCampaignConfig({campaignType, campaignId, locationIndex})` positionne la source vivante puis
la RESTAURE :

```
SOURCE        _currentCampaignId  _currentLocationIndex  _currentMatch  _currentBattle
PROGRESSION   +0x18 _campaignType   +0x28 _campaignId   +0x88 _battlesConfigCampaigns
   (source+0x20)
  -> LoadBattle(true)  ->  restauration dans un `finally`
```

Il n'y a donc **aucun setter natif** a chercher : le noeud est un parametre du **CONSTRUCTEUR**
(`CampaignGameModeSource$$.ctor(..., campaignId: String, initialLocationIndex: Int32, ...)`), et le
depot contourne ca par un ECHANGE TEMPORAIRE.

### ⛔ ET C'EST POURQUOI ON NE TIENT PAS LE SWAP OUVERT

Le module le dit deux fois, et ce sont des contraintes, pas des precautions :

> *The swap window is a single synchronous queueOnMainThread invocation -- no other code observes
> the swapped state.*
> *Restore progression -- critical to avoid leaving the live progression in a corrupted state for
> the rest of the game.*

La progression echangee (`source+0x20`) est **celle du compte reel, partagee et vivante**. La tenir
echangee pour la duree d'une session ferait lire a tout le jeu -- meta comprise -- un chapitre et
une liste de batailles qui ne sont pas les siens. **Le gain serait de la plomberie, le risque porte
sur le profil de l'utilisateur.** Cette voie est donc REFUSEE, pas << a faire plus tard >>.

### LA FORME CORRECTE, et elle decoule de la contrainte

Ne pas positionner le preteur DURABLEMENT, mais **deleguer DANS une fenetre positionnee** : le
`onLeave` de chaque delegation ferait, en une seule sequence synchrone, `swap -> invoke -> restore`
-- exactement la discipline de `buildCampaignConfig`, appliquee a l'appel emprunte au lieu de
`LoadBattle`.

Ce qu'il faut en plus, et qui existe deja dans `campaign-builder.ts` : le `CampaignConfigDto`
resolu du noeud vise (`targetMatch`) et la `List<CampaignConfigDto>` (`battlesList`), tous deux
derives du catalogue. La tranche consiste a **extraire cette preparation** pour la rendre
reutilisable, pas a la reecrire.

⚠ **NON MESURE** : que `GetUnitModel` / `GetUnitsForDeploymentHUD` se contentent d'un swap aussi
court. `LoadBattle` lit `_currentMatch` pendant l'appel ; rien ne dit que les methodes de
deploiement n'ont pas besoin d'un etat coherent AU-DELA de leur propre retour (les modeles rendus
survivent a la fenetre, eux). A confronter avant de s'engager.

## 21. ⛔ LA << FENETRE POSITIONNEE >> DU SS20 EST REFUTEE -- `UnitModel` est une VUE PARESSEUSE

Le SS20 proposait de deleguer DANS une fenetre `swap -> invoke -> restore`, en notant comme NON
MESURE le fait que les modeles rendus survivent a la fenetre. **Mesure faite, et elle tue le
design.** `classFields` sur les classes VIVANTES :

```
IdunMetaLogic.UserProgress.Model.UnitModel        2 CHAMPS
   +0x10  _unitId           String
   +0x18  _unitProgression  IUnitProgression

IdunMetaLogic.UserProgress.Model.HotseatUnitModel  10 champs
   ITEM_LEVEL / STAR_LEVEL / PROGRESSION_INDEX / RANK / RARITY / XP_LEVEL / ABILITY_LEVEL
   +0x28 _unitId   +0x30 _unitProgression   +0x38 _itemModels
```

**`UnitModel` ne stocke RIEN.** Un id, un pointeur vers la progression, et c'est tout : chaque
propriete -- y compris ce que le slot `0x17` calcule pour `IsUnlocked` -- est resolue **A LA
DEMANDE**, contre la progression, au moment de l'appel.

⇒ Apres `swap -> invoke -> restore`, le modele rendu relit la progression **RESTAUREE**. Il survit
a la fenetre, mais **il repond faux**. La fenetre courte convient a `LoadBattle`, qui CONSOMME
`_currentMatch` pendant l'appel et rend une `BattleConfiguration` deja materialisee ; elle ne
convient PAS a `GetUnitModel`, dont le produit est une VUE sur l'etat qu'on vient de defaire.

⚠ Et la progression echangee est **le meme objet** dans les deux regimes (`source+0x20` est
partage ; le swap ecrit SES champs). Il n'y a donc meme pas d'echappatoire par identite : le modele
pointe exactement sur l'instance qu'on restaure.

**Ce que HotseatUnitModel dit au passage** : il porte des CONSTANTES de progression
(`RANK`, `RARITY`, `XP_LEVEL`, `ABILITY_LEVEL`, `STAR_LEVEL`) en plus de la reference. C'est une vue
a stats FIXEES -- exactement ce qu'il faut a un banc d'essai, et exactement ce qui le fait echouer a
`IsUnlocked`, qui interroge la possession et non les stats.

### Ce qui reste debout

Les deux voies encore ouvertes sont donc celles qui ne dependent PAS d'un etat transitoire :

1. **Un vrai preteur actif** -- une `CampaignGameModeSource` reellement positionnee sur son noeud,
   c'est-a-dire une bataille de campagne OUVERTE. Le wrapper delegue alors sans aucun swap.
   Cout : le jeu est dans une bataille de campagne pendant qu'on joue la sandbox -- non confronte.
2. **Renoncer a la fidelite** et assumer un deploiement PERMISSIF : injecter le roster a la main
   (ce qui MARCHE, cf. SS10-SS11) et accepter qu'il n'y ait ni restriction de faction, ni unite
   obligatoire, ni objectif. Utilisable pour entrainer/tester un moteur, pas pour reproduire
   l'experience du jeu.

⚠ **NE PAS re-proposer la fenetre positionnee** : elle est refutee ici par mesure, pas ecartee par
prudence.

## 22. LE GATE EST NOMME : `SandboxPvpBattleConfig.UseAccountUnits` -- et il ne coute AUCUN jeton

Cette section **corrige les SS19 et SS21**. Les deux concluaient que la sandbox etait murée
et qu'il fallait un prêteur ; le décompilé dit autre chose.

### Le corps réel de `SandboxGameModeSource$$GetUnitModel`

Le repli `HotseatUnitModel` n'est PAS le comportement de la méthode : c'est sa **dernière
branche**. Il y a trois sorties avant lui.

```
prog = this->_unitProgression                       (+0x20, IUnitProgression)
si   prog.IsNpcConfig(unitId)                       -> prog.GetUnitOfAnyKind(unitId, stripLevel: true)
sinon si prog.IsSummon(unitId)                      -> prog.GetUnitOfAnyKind(unitId, stripLevel: true)
sinon si sandboxConfig est SandboxPvpBattleConfig
         ET sandboxConfig.UseAccountUnits           -> prog.GetUnit(unitId)     <- LE VRAI MODELE DE COMPTE
sinon                                               -> new HotseatUnitModel(unitId, prog, 2, 0, 0)
```

⇒ Sens réel : **les NPC et les summons reçoivent leur vrai modèle de config ; les unités de
JOUEUR reçoivent le banc d'essai à stats figées** — sauf si la config dit explicitement
d'utiliser les unités du compte. C'est la neutralité de stats d'une sandbox, pas une lacune.

### Comment les quatre index d'interface ont été nommés

Les appels du décompilé passent par les helpers d'invocation d'interface, avec un index
**relatif au bloc d'interface**, pas à la vtable de la classe. Le bloc de `IUnitProgression`
n'est **pas dupliqué** dans `IdunMetaLogic.UserProgress.UnitProgression` : il pointe dans les
virtuelles de la classe, à partir du **slot 4** (après les 4 slots de `System.Object`).

| index | méthode | signature (`frida/methods.tsv`) |
|---|---|---|
| `0x1a` | `UnitProgression$$GetUnitOfAnyKind` | `(unitId: String, stripLevel: Boolean) -> IUnitModel` |
| `0x1c` | `UnitProgression$$GetUnit` | `(unitId: String) -> IUnitModel` |
| `0x2b` | `UnitProgression$$IsNpcConfig` | `(unitId: String) -> Boolean` |
| `0x2c` | `UnitProgression$$IsSummon` | `(unitId: String) -> Boolean` |

Concordance **4/4** sur trois axes indépendants : arité, type de retour, et *lequel* des deux
helpers est employé (celui à 1 argument sur les deux booléens, celui à 2 arguments sur
`GetUnitOfAnyKind`, appelé avec le littéral `true` = `stripLevel`). Les signatures viennent de
la table de symboles **hors ligne**, donc d'une source indépendante de la vtable vivante.

⚠ **Ce qui reste DÉRIVÉ** : le début de bloc (slot 4) est déduit de la disposition IL2CPP, il
n'a pas été lu dans `interfaceOffsets`. La contre-épreuve sur le second implémenteur
(`idun.tests.TestUnitProgression`) est **NON CONCLUANTE** — 16 slots non nuls, classe jamais
peuplée, ce qui est le tri-état correct de `il2cpp/class-init.ts` et **pas** une réfutation.

### Le sous-type et le champ, établis des DEUX côtés

Le test de type porte sur un `Il2CppClass*` statique. **Cinq** fonctions le consomment, et
elles sont **toutes PVP** : `idun.ui.SandboxContainer$$GetSandboxPvpBattleConfig`,
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetHotSeatGameModeSpecificConfig`,
`Idun.Source.IdunBattle.View.BattleConfigBuilder$$GetHotseatSyncPvpConfig`,
`IdunBattle.ViewLogic.BattleSource.EndlessBattleConfig.EndlessPvpBattleConfig$$GenerateSandboxBattleConfig`,
et notre site. Côté **écriture**, `GetSandboxPvpBattleConfig` alloue sur ce même statique puis
appelle `SandboxPvpBattleConfig$$.ctor` — l'identité est donc directe, pas inférée.

Balayage `classFields` des **11** configs de sandbox : deux seulement ont un champ à `+0x34`.

```
SandboxPvpBattleConfig            +0x28 BoardId String   +0x30 SpawnpointSet Int32
                                  +0x34 UseAccountUnits Boolean     <- CELUI-CI
                                  +0x38 Player1Type      +0x3c Player2Type   +0x40 PlayerUnits
SandboxCampaignEventBattleConfig  +0x34 Player1Type (PlayerType)    <- ecarte : pas un Boolean,
                                  et aucune de ses fonctions ne consomme le statique testé
```

Le décompilé lit un **octet** (`*(char *)(cfg + 0x34) != 0`) : `UseAccountUnits`, `Boolean`,
correspond exactement. Dans l'écran de sandbox natif, l'argument vient d'un octet du
`SandboxContainer` — c'est une **case à cocher du mode développeur**.

### Ce que ça change pour nous

1. **La bataille montée est `SandboxWavesBattleConfig`** — qui n'est pas un
   `SandboxPvpBattleConfig` et **n'a aucun champ `UseAccountUnits`**. La troisième branche
   est donc inatteignable pour elle, quel que soit le réglage. Ce n'est pas un prêteur qui
   manquait : c'est le mauvais type de config.
2. **Deux leviers, aucun ne coûte de jeton** :
   * monter une sandbox **PVP** avec `UseAccountUnits = true` — voie nativement prévue ;
   * substituer `prog.GetUnit(unitId)` au retour de `SandboxGameModeSource$$GetUnitModel` —
     indépendant du mode, mais c'est du `frida/hooks/*`, donc une fenêtre de reinject.
3. ⚠ **Asymétrie native relevée, NON CHASSÉE** : `SandboxCampaignEventBattleConfig` porte lui
   aussi un `UseAccountUnits` (à `+0x30`), mais `GetUnitModel` ne teste **que** le type PVP.
   Un sandbox d'événement de campagne rendrait donc des `HotseatUnitModel` malgré son drapeau.

### Deux corrections de plus

* **Le SS19 attribuait le roster vide au prêteur au repos. C'est structurel.**
  `SandboxGameModeSource$$GetUnitsForDeploymentHUD` et `$$GetUnlockedUnitsPooled` ont un corps
  **identique** : un `DictionaryPooler` vide, et ils **ne lisent jamais `this`**. Aucune
  configuration de la sandbox ne leur fera rendre un roster — d'où le fait que l'injection
  manuelle (SS10-SS11) soit la seule chose qui ait marché.
* **La voie « vrai prêteur actif » (SS21, option 1) est ÉCARTÉE, et pour deux raisons.**
  D'abord elle **coûte un jeton** : positionner un prêteur veut dire ouvrir une vraie bataille,
  or la tentative est enregistrée **AU CHARGEMENT** — établi sur le boss de guilde
  (`GuildBossGameModeSource$$SendLoadBattleGameEventInternal` ->
  `TempBattleData$$GenerateNewBattleId` + game-event) — et l'abandonner ne décrémente aucun
  compteur local. Sur un mode sans retraite, le montage brûlerait le jeton avant le premier
  tour. Ensuite elle **n'apporte rien** : `CampaignGameModeSource$$GetUnitModel` est un relais
  PUR vers exactement `prog.GetUnitOfAnyKind(unitId, true)`, sans lire aucun champ de position
  (`_currentCampaignId`, `_currentLocationIndex`, `_currentMatch`). Emprunter rendait donc
  l'appel que la sandbox fait déjà dans sa première branche.

⚠ **Le vice commun aux SS12, SS15, SS17, SS19 et SS21 : ranger deux méthodes ensemble parce
qu'elles portent le même préfixe et vivent sur la même interface.** `GetUnitsForDeploymentHUD`
dépend de l'état du mode, `GetUnitModel` n'en dépend pas du tout. Lire le CORPS aurait coûté
un appel.

## 23. LE ROSTER : le filtre est SOUS `HasValue`, l'appariement etait JUSTE, et il reste UN FAIT INEXPLIQUE

Cette section **corrige la section precedente sur un point**, et laisse une question ouverte
plutot que de la refermer sur une troisieme hypothese.

### Le mecanisme, entierement decompile

```
CampaignGameModeSource$$GetUnitsForDeploymentHUD(this) :
    prog     = this->_campaignProgression          (+0x20, ICampaignProgression)
    nullable = new Nullable<Int32>( this->_currentLocationIndex )    (+0x70)
    liste    = prog.<index 0x15>(nullable, onlyUnlocked: false)
    return PooledList.Map(liste, converteur)

CampaignProgression$$GetDeployableUnits(locationIndex: Nullable<Int32>, onlyUnlocked) :
    info = null
    si locationIndex.HasValue :                    <-- TOUT le filtrage est sous ce test
        info = (this->_battles[idx], GetStarsOfLocation(idx))
    unites = this->_unitProgression.GetUnits(flags, null)     // la collection ENTIERE
    return CampaignBattleInfo.GetDeployableUnits(info, ..., unites, ...)
```

Deux consequences, toutes deux mesurees :

1. **La collection complete est chargee a CHAQUE appel** ; c'est le noeud qui la vide. Un
   `Nullable` sans valeur rendrait le roster non filtre — mais `CampaignGameModeSource` en
   construit toujours un AVEC valeur, donc ce chemin est inatteignable sans intervenir.
2. **Positionner le preteur ne demande NI bataille NI jeton.** Cette methode ne lit ni
   `_currentMatch` ni `_currentCampaignId` : un seul `Int32` commande le roster. La crainte
   ecrite au SS19 (« un DTO deja resolu deviendrait perime ») vaut pour `LoadBattle`, pas ici.
   `deploymentPoolPreteur` lit et ecrit ce champ ; eprouve 74 -> 12 -> 74.

### L'APPARIEMENT DE SLOT ETAIT JUSTE — et ma « refutation » etait fausse

Un commit intermediaire a conclu que « index 0x15 = `GetDeployableUnits` » etait FAUX, sur la
foi d'un compteur a zero. **Mesure faite depuis, par `classInterfaceSlots` qui LIT
`interfaceOffsets` au lieu de deriver** :

```
CampaignProgression  nbInterfaces=2
  ICampaignProgression  offset=4
      0x14 -> slot 24  GetBattleRestrictions
      0x15 -> slot 25  GetDeployableUnits
      0x16 -> slot 26  IsDeploymentUnlocked
```

Le decalage de bloc **est** 4, et l'appariement etait bon. L'heuristique disait vrai ; c'est ma
conclusion qui etait pressee. ⇒ **Le meme raisonnement au SS22 (`IUnitProgression`,
0x1a/0x1c/0x2b/0x2c) n'est donc PAS entache** — mais il reste a confirmer par la meme voie, et
c'est desormais un appel de RPC, plus une derivation.

### LE FAIT QUI RESTE INEXPLIQUE, et il est REPRODUCTIBLE

Sur deux sessions independantes, meme montage :

```
delegation GetUnitsForDeploymentHUD   fires 1   emprunts 1   (retour non nul substitue)
ancrage    GetDeployableUnits         fires 0   (compteur INCONDITIONNEL)
```

Tous les maillons sont mesures et concordants :
* l'ancrage vise `0x181708ff0` — `resolveMethodPtr` rend cette adresse pour
  `CampaignProgression$$GetDeployableUnits` ;
* le slot de vtable 25 CONTIENT cette meme adresse (`resolveVtableSlot @0x2c8`) ;
* l'objet vivant en `_campaignProgression` EST un `CampaignProgression` ;
* le decalage d'interface est lu, pas suppose.

Et pourtant la methode n'est jamais entree. **On ne conclut pas.** L'hypothese restante — que
`invokeMethod` rende un pointeur sans que le corps emprunte s'execute — se testerait en ancrant
la methode qu'on invoque, **ce que le depot interdit** (c'est le motif qui gele le jeu). Il faut
donc une voie d'observation indirecte, pas une hypothese de plus.

### Cran de methode : le COMPTEUR doit etre INCONDITIONNEL

Le premier compteur etait conditionne par la fenetre d'emprunt. Il ne distinguait pas
« jamais appelee » de « appelee hors fenetre » — les deux rendent zero, et ce zero-la ne designe
rien. Le compteur inconditionnel est ce qui a rendu le fait ci-dessus **exploitable**.

## 24. LA VOIE D'OBSERVATION INDIRECTE : faire appeler par le JEU -- et ce qu'elle a renverse

Le SS23 laissait un fait reproductible et inexplique : nos emprunts ne faisaient jamais tirer
l'ancrage sur `CampaignProgression$$GetDeployableUnits`, alors que tous les maillons statiques
concordaient. Le tester directement demandait d'ancrer la methode qu'on invoque -- **interdit**,
c'est le motif qui gele le jeu.

### La voie, et elle ne coute rien

**Ne rien invoquer, et laisser le JEU appeler.** L'ancrage reste en place, on lance un warmup
ordinaire (il navigue la campagne), et on lit le compteur. Aucun forcage, aucune invocation :
aucun risque ajoute au-dela du warmup qu'on joue de toute facon.

Resultat immediat : **`fires: 2`, `dansEmprunt: false`**. L'ancrage est SAIN. Le zero du SS23
n'accusait donc pas l'execution, mais notre OBSERVATION.

### Le discriminant, puis le verdict

`deploymentPoolEmprunterUneFois` fait le MEME emprunt depuis la file du thread principal, **hors
de tout callback d'interception** (et respecte la regle : on invoque `GetUnitsForDeploymentHUD`,
on ancre `GetDeployableUnits` -- deux methodes distinctes).

    firesAvant 0 -> firesApres 1   delta = 1

⇒ **Le corps emprunte S'EXECUTE.** Un `Interceptor` Frida ne re-observe pas un appel declenche
depuis l'interieur d'un autre callback d'interception, sur le meme thread.

**Consequences, dans les deux sens :**

* La delegation du SS19 est CONFIRMEE : elle emprunte vraiment. L'alarme du SS23
  (<< toutes nos substitutions sont des illusions >>) est REFUTEE.
* Mais le regime `sansFiltre` ne pouvait PAS fonctionner : il n'agit que `dansEmprunt`,
  c'est-a-dire exactement dans la fenetre ou l'ancrage est aveugle. Il n'etait pas mal reglé,
  il etait structurellement inerte.

### LA DISPOSITION DU `Nullable<Int32>` EST L'INVERSE DE CELLE QU'ON SUPPOSE

L'appel naturel donne `0x4a00000001` pour `_currentLocationIndex = 74` :

    32 bits BAS  = hasValue (1)
    32 bits HAUTS = la valeur (0x4a = 74)

Donc `{ bool hasValue; int value; }`, pas `{ int value; bool hasValue; }`. Le masque prevu
(effacer les bits HAUTS) aurait garde `hasValue = 1` et mis l'index a **0** : un AUTRE noeud, pas
l'absence de filtre. Il aurait << marche >> en faisant tout autre chose, et le roster different
aurait servi de fausse confirmation. **C'est precisement ce que le regime observation-d'abord
existe pour attraper** -- et c'est la deuxieme fois dans ce dossier qu'il paie.

Masque corrige (`and(0xffffffff00000000)`), applique et verifie sur un emprunt isole :
`ecrit: true`, jeu vivant (temoin `Responding` + delta CPU avant ET apres).

### CE QUI SUIT, ET IL EST NOMME

Puisque l'ancrage est aveugle pendant la delegation, la modification ne peut pas s'y faire.
La forme correcte est **PRE-EMPRUNTER PUIS SUBSTITUER** : faire l'appel emprunte hors de tout
hook (la ou l'ancrage voit, donc ou le masque agit), garder le resultat, et ne laisser au
`onLeave` de la delegation qu'un `retval.replace` de cette valeur deja calculee.

### CLIQUET DE METHODE

**Un compteur d'`Interceptor` ne vaut RIEN tant qu'il n'a pas ete valide sur un appel NATUREL.**
Son zero ne distingue pas << jamais appelee >> de << appelee la ou je ne vois pas >>, et ce
dossier a produit les deux lectures fausses de suite : d'abord une refutation d'appariement de
slot (fausse, cf. SS23), puis une accusation contre `invokeMethod` (fausse aussi). Le controle
coute un warmup.

## 25. LE ROSTER S'AFFICHE -- pre-emprunt + deboxage + masque, confirme A L'ECRAN

Chaine complete jouee en session 45, **confirmee par l'utilisateur a l'ecran** apres quatre
sections d'echecs :

```
1. deploymentPoolSansFiltre {armer, ecrire, confirmer}   -> masque arme
2. deploymentPoolPreEmprunt {confirmer}                  -> appel HORS hook :
      boite   PooledList`1          (runtime_invoke BOXE les types valeur)
      deboxe  PooledListElement`1   (+0x10) <- le type que le stub sandbox rend nativement
      deltaGetDeployableUnits = 1   <- l'appel a VRAIMENT traverse la methode filtrante
      ecrit: true                   <- hasValue efface, donc AUCUN filtre de noeud
3. deploymentPhaseArmer {forcer} + sandboxModeGameViews + deploymentPoolArmer {only: roster}
4. sandboxModeStart mode=pvp, useAccountUnits=true
   -> "PRE-EMPRUNT substitue", relais 1/1, jeu vivant
```

### LES TROIS CAUSES QUI SE MASQUAIENT L'UNE L'AUTRE

Le roster vide n'avait pas UNE cause mais trois, empilees -- et chacune rendait les deux autres
invisibles :

1. **Le filtre de noeud.** `GetDeployableUnits(Nullable(74), false)` rend vide a ce noeud. Tout
   le filtrage est sous `HasValue` (SS23).
2. **L'`Interceptor` aveugle aux appels imbriques.** Le masque ne pouvait donc pas agir depuis
   la delegation, quelle que soit sa justesse (SS24). D'ou le pre-emprunt.
3. **LE DEBOXAGE MANQUANT.** `runtime_invoke` boxe les types valeur ; la delegation substituait
   la BOITE (`PooledList`1`) la ou l'appelant attend la VALEUR (`PooledListElement`1`). Type
   faux, silencieux, et suffisant a lui seul pour un roster vide **meme avec un emprunt
   parfaitement reussi**.

⇒ Corriger l'un des trois n'aurait rien change a l'ecran. C'est pourquoi quatre tentatives
successives ont toutes rendu << vide >> en accusant chaque fois un etage different.

### CE QUI RESTE A CONFRONTER

La POSE. `useAccountUnits: true` doit faire rendre `GetUnit(unitId)` -- un vrai modele de
compte -- donc faire passer `IsUnlocked` et peupler `_allUnlockedUnitModels` (SS22). Non
confronte : afficher n'est pas poser.

## 26. LE PREFAB : ce qui manque n'est pas un CHARGEMENT, c'est une ENTREE -- et un delegue ne se re-cible pas

Symptome de depart : on selectionne une unite du roster, elle se GRISE, et rien n'apparait.
`IdunGameViews$$AddPlaceholderUnit` sort par `UnitIdToPrefabDictionary$$Get` -> `TryGet` -> faux.

### Le chargement paresseux EST DEJA DANS LE JEU

```
UnitIdToPrefabDictionary$$Get(unitId) :
    si !ContainsKey(GetUnitIdForUniverse(unitId)) : log ; return 0
    ref = dico[cle]                              // AssetBundleBattleReference
    si ref._prefab == null :                     // <- LE CHARGEMENT A LA DEMANDE
        ref._prefab = ref._loader.Invoke()       //    est deja la
    return NullableRefUnity(ref._prefab)
```

Il n'y a donc **rien a charger** : il y a une **entree a creer**. `Add` n'a qu'UN appelant,
`idun.IdunMainView$$StartBattle`, qui itere `BattleConfiguration.Units` -- et notre roster est
EMPRUNTE a la campagne, donc dans aucune BC.

⚠ **`bc.Units` n'est PAS une source de roster** : sur un montage `useAccountUnits`, les 68 ids
inscrits sont **3 heros** (l'equipe adverse declaree) et **65 SUMMONS** (`*Smn*`, `orksGrot`,
`deathPoxwalker`...). L'idee « afficher bc.Units comme roster » est donc morte-nee.

### L'anatomie d'une entree, mesuree sur un exemplaire VIVANT

```
AssetBundleBattleReference   _prefab:GameObject @+0x10   _loader:Func`1 @+0x18
Func`1                       -> cible : <>c__DisplayClass65_1
<>c__DisplayClass65_1        visualUnitConfig:IdunUnitType @+0x10
                             CS$<>8__locals1:<>c__DisplayClass65_0 @+0x18  (porte l'EffectPool)
```

Rien de tout ca n'est ecrit en dur : Ghidra nomme le ctor de `AssetBundleBattleReference`
`UnityEngine.EventSystems.BaseEventData$$.ctor` (corps DEDUPLIQUE) et la classe porteuse n'est
qu'un `DAT_`. On **capture un patron** en ancrant `Add`, qui tire a chaque montage.

### CE QUI A COUTE LA JOURNEE : UN DELEGUE NE SE RE-CIBLE PAS PAR ECRITURE DE CHAMP

`Get` invoque le loader par `invoke_impl(delegue->method_code, &retour, delegue->method)`.
`method_code` (+0x40) n'est PAS la cible : c'est un pointeur de CODE, vers un trampoline ou la
cible est **deja scellee**. Les deux ecritures possibles echouent, chacune a sa maniere :

| ecriture | resultat MESURE |
|---|---|
| `m_target` seul (+0x20) | pas de crash, mais le trampoline appelle la fermeture DU PATRON -> **deux unites distinctes affichent le meme modele** |
| `method_code` (+0x40) | l'invocateur saute sur des donnees -> `access violation accessing 0x...` |

**La forme juste est de CONSTRUIRE le delegue**, comme `StartBattle` :
`.ctor(cible, MethodInfo*)`. ⚠ Et le second argument est le champ **`method` (+0x28)**, PAS
`method_ptr` (+0x10) : en IL2CPP `ldftn` rend un `MethodInfo*` deguise en `IntPtr`. Passer le
pointeur de code construit un delegue dont l'invocateur part sur une sentinelle
(`access violation accessing 0xffffffffffffffff`).

Disposition de `System.Delegate` sur ce build, LUE (`classFields`) et non deduite :
`method_ptr@0x10 · invoke_impl@0x18 · m_target@0x20 · method@0x28 · method_code@0x40`.

### LE REGIME LIVRE : a la demande, sur defaut de cle

On ancre `Get` ; si la cle manque, on fabrique l'entree DANS LE `onEnter`, puis on laisse le
corps natif s'executer -- il trouve la cle et declenche SON propre chargement paresseux.
Une entree par unite REELLEMENT posee, aucun prechargement, et c'est le jeu qui charge.

⚠ **Le regime d'epreuve doit etre le regime reel.** Precharger les 55 entrees du roster « pour
tester » validerait un mecanisme qu'on ne livre pas. Refuse a raison par l'utilisateur.

### QUATRE CAPTEURS QUI ONT MENTI -- c'est la vraie lecon

1. **`il2cpp_runtime_invoke` BOXE les retours de type valeur.** Lire `retour.toInt32()` lit les
   32 bits bas du POINTEUR DE BOITE : `HasPrefabForUnitId` rendait donc **`true`
   inconditionnellement**. Cout : la bonne cause refutee, et un `deploymentPrefabCharger` qui
   repondait « deja present -- rien fait » sans rien creer. Le booleen est a **+0x10**.
2. **Aller CHERCHER le dictionnaire au lieu d'utiliser celui que le jeu passe.**
   `FindObjectsByType` / le `this` publie par le pump rendent *une* vue, pas *celle qui deploie* :
   d'ou une contradiction apparente entre `HasPrefabForUnitId` et `Get`. On lit desormais le
   `this` des appels du jeu (`Get`, `AddPlaceholderUnit`, `Continue`), et la SOURCE est publiee.
3. **Un compteur sur la mauvaise adresse.** `loaderFires` ancrait `method_ptr` alors que
   l'invocateur dispatche par le `MethodInfo` : son `0` ne prouvait pas que le loader n'avait pas
   tourne. Meme vice que #1 sous une autre forme.
4. **`AddPlaceholderUnit` rend `0` AUSSI sur le chemin de SUCCES** (sa derniere instruction est
   une emission d'evenement, pas un booleen). Le `rendu=False` de nos capteurs est donc un FAUX
   NEGATIF -- l'ecran est la verite, et il l'a ete a chaque desaccord de ce dossier.

⚠ **Un `onLeave` qui ne tire pas est un SIGNAL, pas un trou.** C'est l'ecart « `listenerDemande`
voit 5 appels, `listenerGet` en enregistre 3 » qui a designe l'exception silencieuse. L'appel
encadre (`deploymentPrefabEprouver`, ancrages DEPOSES pendant l'invocation) rend le message
manage decode -- sans lui on ne voyait qu'un ecran vide.

### CRAN D'EXPLOITATION

Chaque essai rate **grise l'unite definitivement** (`TryMarkUnitAsPlaced` est appele au clic du
portrait, pas seulement a la pose) : tous les tests posterieurs au premier sont CONTAMINES.
Un montage neuf est obligatoire entre deux epreuves.
