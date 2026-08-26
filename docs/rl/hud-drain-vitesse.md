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

## Ce que ça donne — MESURÉ, sur la MÊME file

Mesuré le 2026-08-26, sandbox `elite1 40` (100 vagues × 10 nécrons, 194 tours d'IA, 6 288
messages en attente à file figée). La bascule se fait **en cours de drain**, donc les messages
sont les mêmes des deux côtés : une seule variable.

```
BattleSpeed.Absurd  (15x) :  622 msg / 3324 frames / 36,1 s  ->  17,2 msg/s   0,187 msg/frame   92,0 fps
BattleSpeed.Fastest ( 2x) :  166 msg / 3566 frames / 36,1 s  ->   4,6 msg/s   0,047 msg/frame   98,7 fps

GAIN REEL : x3,75 en msg/s
```

**1. La référence se reproduit.** Les `0,047 msg/frame` à `Fastest` retombent sur les **0,05**
relevés sur une bataille de campagne RÉELLE, autres unités, autres visuels. Deux mesures
indépendantes qui coïncident : le chiffre de référence tient.

**2. `timeScale` ne coûte PAS le frame rate — et il a fallu arrêter l'IA pour le savoir.** Pendant
que `cheatRunAi` tournait, le jeu rendait **~6 fps**, ce qui accusait `Absurd` de façon
convaincante. File figée, `Absurd` rend **92 fps** contre 98,7 à `Fastest` : **7 %**, rien de
plus. Le coupable était le runner sur le fil principal. Une mesure prise pendant que l'IA joue
aurait conclu l'inverse de la vérité.

**3. LE GAIN EST x3,75, PAS x7,5 — la moitié du rapport de réglage n'arrive jamais.** Le réglage
passe de 2 à 15. Ce fichier avait écrit « attendu ×7,5 » en le donnant pour attendu et non
acquis : c'était la bonne prudence, et l'écart est réel. Cause probable, **non attribuée** : une
part des animations passe par des tweens `Go$$timeScaleIndependentUpdate`, insensibles au
`timeScale` par construction. Ne pas convertir ce ×3,75 en règle de trois pour un autre réglage —
`SuperFast` (5×) n'a pas été mesuré.

⚠ **`SetGameSpeed` appelle `thor.Settings$$Save()` : le réglage PERSISTE** sur disque, donc il
survit au reinject ET au prochain lancement du jeu, batailles réelles comprises. Ce n'est pas un
état de session.

⚠ **`SetGameSpeed` a DEUX surcharges à un paramètre** (`180730f80` int, `180730c70` float) et
`findMethodByParamCount` rend la PREMIÈRE — mesurée au 2026-08-26 : l'**int**. On passe donc
l'**ordinal** (`Absurd` = 1500). Passer `15.0` partirait dans la surcharge float, qui balaie
l'enum en comparant des VALEURS, et écrirait autre chose — puis le sauvegarderait.

## Ce qui reste à établir

1. **D'où vient la moitié perdue** (×3,75 au lieu de ×7,5). Piste non éprouvée : les tweens
   `Go$$timeScaleIndependentUpdate`. Le tri se ferait en comptant, sur un même lot de messages,
   ceux dont le handler passe par un tween indépendant du `timeScale`.
2. **`SuperFast` (5×) n'a pas été mesuré**, et le ×3,75 ne s'y transpose pas par règle de trois —
   c'est précisément le genre d'extrapolation que le §3 ci-dessus démonte.
3. **`Abort` / `Stop` / `StopAllHandlers`** (`IMessageHandler` slots 2-3, `IGroupHandlerFactory`
   slot 5) sont la voie « couper », distincte de « accélérer ». Non lue. À n'ouvrir que si le
   ×3,75 ne suffit pas : couper une animation peut laisser la vue en arrière de la logique.
4. **`EndMatchImmediately`** est encore une autre voie (fin de match), à ne pas confondre.

**Le chemin d'accès, pour ne pas le re-chercher** : `IdunMainView` → `gameViews`
(`IdunGameViews`, +0xb0) → `_settings` (`Settings`) → `settingsData.BattleSpeed` (+0x1c).
`Settings` n'a **aucun statique**, donc on descend depuis la vue — ce qui **exige une bataille
chargée** (les RPC de vue passent par `queueOnMainThread`, donc par la pompe). Hors bataille,
rien ne draine et l'appel part en timeout.

⛔ **Et hors bataille, `viewSurface`/`viewInstances` ne se contentent pas de timeouter : ils
appellent `FindObjectsByType` sur le fil principal et ont FIGÉ le jeu** (2026-08-26 :
`Responding: False`, `frameNo` immobile, CPU à plat, redémarrage obligatoire). Pour nommer une
classe ou lire un pointeur, `objetChamps` / `staticFieldProbe` / `resolveMethodPtr` suffisent et
tournent sur le fil Frida.

⛔ Tout essai se fait en **SANDBOX**.
