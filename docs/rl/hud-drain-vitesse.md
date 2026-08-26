# Le HUD dépile 20 fois moins vite que la logique — où est le frein, et où est le levier

Mesuré le 2026-08-26, build `t6dpr4k06g`, sur une bataille de campagne réelle
(`Campaign1_40`, 100 vagues de 10 nécrons, 1 025 entités créées).

## Le fait

La logique finit **très** avant l'affichage. `stage: Finished`, `runner` encore vivant, et
`viewQueueDump` rend **2 119 messages en attente**. Drain complet mesuré :

```
t+0     enAttente = 1425
t+337   enAttente = 0    enCours=False  arretee=True
```

**1 425 messages en 5 min 37**, soit **4,2 msg/s** et **0,05 msg/frame**, stable du début à la
fin. Le jeu tournait à ~85 fps : il rend donc **~20 frames par message**. La frame n'est jamais
le facteur limitant.

⇒ **Toute mesure d'accélération se fait en msg/frame, contre 0,05.** Un gain visible à l'écran
qui ne déplace pas ce nombre n'a rien accéléré.

⚠ En atteignant 0, la file passe `arretee: true` — elle ne se vide pas, elle se **ferme**
(`_isStopped`, testé en 2ᵉ condition par `ProcessNextMessage`). Pousser dans une file close ne
ferait rien.

## Le mécanisme, une fois les caches NOMMÉS

`ProcessNextMessage` initialise neuf caches `DAT_*` au runtime — le décompilé statique ne peut
donc nommer aucun d'eux. Nommés par lecture pure (§ « Comment on les a nommés ») :

| cache | classe |
|---|---|
| `DAT_183367a48` | `IdunBattle.ViewLogic.BattleStream.IMessage` |
| `DAT_1833a8cf0` | `System.Collections.Generic.IReadOnlyCollection\`1` |
| `DAT_183358d40` | `IdunBattle.ViewLogic.BattleStream.IGroupHandlerFactory` |
| `DAT_1833803c8` | `IdunBattle.ViewLogic.BattleStream.IStepHandlerFactory` |
| `DAT_183367e20` | `IdunBattle.ViewLogic.BattleStream.IMessageHandler` |
| `DAT_18333fc48` | `System.Action\`1` |

D'où la fonction, en clair :

```
msg = _messages.Dequeue()
si msg.get_IsGroup() :
    grp = msg.get_Group()
    si grp == null ou grp.<+0x48> == null                 -> sortie
    si IReadOnlyCollection.get_Count(grp.<+0x48>) == 0 :   // VOIE RAPIDE
        _currentlyProcessingMessage = false ; ProcessNextMessage(this)   // SANS animer
    sinon :
        h = _groupHandlerFactory.CreateHandler(msg.get_Group())
sinon :
    si !msg.get_IsStep()                                  -> sortie
    h = _stepHandlerFactory.CreateHandler(msg.get_Step().<+0x38>)
si h != null : IMessageHandler.Execute(h, msg, <Action>, 0)      // <<< C'EST ICI QU'ON ANIME
OnMessageFinishedProcessing : _currentlyProcessingMessage = false ; ProcessNextMessage(this)
```

**Il n'y a ni budget par frame ni délai inter-message.** Le seul coût est la durée d'animation,
dans `IMessageHandler.Execute` (slot 1, 3 paramètres).

⚠ **`_disableTimeouts` (+0x68) n'est PAS un accélérateur**, contrairement à ce que son nom
suggère : `Update` ne s'en sert que pour appeler `CheckLastActivityTimeout`. C'est un **chien de
garde**.

## ⚠ CORRECTION — le prédicat de la voie rapide n'a RIEN de global

Ce fichier a d'abord conclu que `FUN_180002590(0, DAT_1833a8cf0)` était **appelé sans argument
d'instance**, donc qu'il lisait un **compteur ou drapeau global**, donc qu'il existait un
**interrupteur**. **Les trois propositions sont fausses**, et la première est la cause des deux
autres.

`FUN_180002590(slot, interface, instance)` est le **répartiteur d'interface** d'IL2CPP : il
cherche `interface` dans `klass->interfaceOffsets`, puis saute dans
`vtable[offset + slot]`. Ghidra n'avait simplement **pas récupéré le 3ᵉ argument** à ce site
d'appel — il était déjà en registre. Une absence dans un décompilé n'est pas une absence dans le
code.

Le prédicat est donc `IReadOnlyCollection.get_Count(grp.<+0x48>) == 0` : **une propriété DU
MESSAGE** — « ce groupe est vide » — et non un état du monde. Le même appel est comparé `< 1`
dans `AbilityVisualsUtils.StreamMessages$$GetUnitOrTileIdFromMessage`, ce qui confirme un
`Count`, pas un drapeau. Il n'y a **aucun interrupteur** à ce niveau, et forcer ce prédicat
reviendrait à ne **jamais** appeler `IMessageHandler.Execute` — donc à ne plus rien afficher.

## Le levier, lui, existe — et c'est celui du JEU

`IdunGameViews$$UpdateSpeed`, atteint par `IdunMainView$$OnBattleSpeedChanged` :

```
v = <IBattleSource>.<slot 7>()          // Nullable<float>, override de rejeu
si !v.HasValue : v = thor.Settings$$GetGameSpeedValue(settings)
UnityEngine.Time$$set_timeScale(v)      // <<< LA VITESSE DE BATAILLE EST LE timeScale UNITY
IdunRunner$$SetReplaySpeed(runner, 0)
```

et `thor.Settings$$GetGameSpeedValue` :

```
n = settings.settingsData.<+0x1c>
n == 0 -> 1.0     n == 1 -> 1.5     n == 2 -> 2.0     sinon -> n / 100.0
```

⇒ **N'IMPORTE QUEL entier hors {0,1,2} donne `n/100`**, et l'enum `thor.Settings.BattleSpeed`
porte **déjà** les membres que le curseur n'expose pas :

```
Normal=0 (1x)  Faster=1 (1.5x)  Fastest=2 (2x)  SlowMo=10  Slow=50
SuperFast=500 (5x)             Absurd=1500 (15x)
```

`Fastest` est le maximum du curseur. **`BattleSpeed.Absurd` vaut 15×, soit 7,5× de plus** — un
membre d'enum livré, écrit par les développeurs, atteint par
`PauseMenu$$OnCheatBattleSpeedChanged`. Rien à inventer, rien à falsifier, aucune désynchronisation
possible : c'est le chemin normal du jeu.

Les deux surcharges de `thor.Settings$$SetGameSpeed` diffèrent, et ça compte :
`SetGameSpeed(float)` **balaie les membres de l'enum** et prend celui qui approche à 0,1 près ;
`SetGameSpeed(int)` **écrit l'entier tel quel**. Les deux appellent `Save()` — c'est donc une
**écriture PERSISTANTE** du réglage client (réversible en reposant `Fastest`).

⚠ **PIÈGE — `BattleTime._timeScale` n'est PAS la vitesse.** Le nom appelle la confusion, et
`SetTimeScale` est même le seul symbole du binaire qui ressemble à un réglage de vitesse. C'est
en fait le drapeau de **PAUSE** : ses deux seuls appelants sont `IdunGameViews$$Pause` et
`$$Continue`, et le statique lu en session vaut `0` hors bataille. L'écrire n'accélérerait rien.

## Comment on les a nommés — la ruse, et pourquoi elle est sûre

`objetChamps` lit `*(adresse)` comme le slot de classe d'un objet géré, puis le nomme par
`il2cpp_class_get_name`. Lui donner **l'adresse du cache** lui fait donc lire la valeur
*stockée* — l'`Il2CppClass*` cherché — et la nommer. Une lecture de pointeur, un `class_get_name` :
aucune écriture, aucune invocation du jeu.

La base du module ne se devine pas (ASLR) : elle se **dérive** d'une mesure — `resolveMethodPtr`
publie `va` et `rva` — et la `rva` obtenue est confrontée à `functions.tsv` avant qu'on s'en
serve. Une base fausse nommerait une classe au hasard, **sans erreur**.

Les slots viennent de `interfaceSlotProbe` : l'ordre d'énumération du metadata **est** l'ordre des
slots pour une interface. Scripts : `nommer_caches.py`, `nommer_slots.py`.

## Ce qui reste à établir

1. **Mesurer le gain réel de `BattleSpeed.Absurd`**, en msg/frame, contre les 0,05 d'aujourd'hui.
   Attendu ×7,5 (0,375 msg/frame, le drain de 337 s tombant vers ~45 s) — **attendu, pas acquis** :
   Unity **clampe** `deltaTime` à `Time.maximumDeltaTime`, et les tweens
   `Go$$timeScaleIndependentUpdate` sont par construction **insensibles** au `timeScale`. Le
   plafond effectif est donc une mesure, pas une division.
2. **Atteindre l'instance `Settings`** : elle n'a **aucun statique** (`settingsData`, `_logger`,
   `_isCheatModeEnabled` sont tous des champs d'instance). La voie est `IdunGameViews._settings`,
   donc les RPC de vue — qui passent par `queueOnMainThread`, donc par la pompe, donc **exigent
   une bataille chargée** : hors bataille, `viewSurface` part en timeout.
3. **`Abort` / `Stop` / `StopAllHandlers`** (`IMessageHandler` slots 2-3, `IGroupHandlerFactory`
   slot 5) sont la voie « couper », distincte de « accélérer ». Non lue. À n'ouvrir que si le
   §1 plafonne : couper une animation peut laisser la vue en arrière de la logique.
4. **`EndMatchImmediately`** est encore une autre voie (fin de match), à ne pas confondre.

⛔ Tout essai se fait en **SANDBOX**.
