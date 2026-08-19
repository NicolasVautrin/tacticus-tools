# #595 — Se balader dans le jeu : les primitives existaient, **injoignables**

**Mesure du 2026-08-08, session 3, build `rnca9r7q6c`.** Client :
`python scripts/python/game_nav.py ou|boutons|clic|maison`.

## Ce qui bloquait n'était pas une capacité

`frida/hooks/features/ui-nav.ts` publie `uiList`, `uiListAll` et `uiClick` depuis toujours,
et elles sont dans le bundle vivant. Un recensement les classait « RPC sans appelant » —
elles ne sont pas mortes : **aucune route host ne les exposait et aucun client ne les
appelait**. Le passe-plat générique `POST /api/scripts/<id>/rpc` suffit, il existait déjà.

⇒ Ni fenêtre de reinject, ni changement de bundle, ni route neuve. **Zéro modification côté
jeu** pour voir et agir.

## Le fait qui gouverne tout : le retour de `uiClick` ne dit rien, **dans les deux sens**

| régime | retour | réalité | source |
|---|---|---|---|
| clic avalé (`interactable` avant la fin de l'animation) | `ok:true` | **n'a pas porté** | `#332`, mesuré |
| onglets `Idun_UI_Tabs` | `ok:false` — `onClick.Invoke threw: system error` | **a porté, 3 fois sur 3** | ici |
| bouton ordinaire (`CloseArea` d'un popup) | `ok:true` | a porté | ici |

La règle du dépôt — *ne jamais conclure du retour d'un clic qu'il a porté* — vaut donc aussi
**à l'envers** : un `ok:false` ne prouve pas l'échec. Le seul signal fiable est l'**effet**.

`game_nav.cliquer()` prend donc une **empreinte** de l'écran avant, clique, et attend un
changement d'empreinte. `retour_brut` est conservé pour la trace, jamais pour décider.

⚠ L'empreinte ne peut pas être un **compte de boutons** : mesuré, `HomeScreen` passe de 38 à
57 boutons sans changer d'écran, quand des widgets finissent de charger. On hache l'ensemble
des chemins, plus les prefabs d'écran (`Idun_UI_<X>Screen(Clone)`) et de popup.

## Un garde qui enferme au lieu de protéger

Première version du garde anti-dépense : `"/Shop" in chemin`. Il a bloqué
`ShopPopup(Clone)/CloseArea` — **la sortie de secours du popup qu'il prétendait protéger**.

Le verdict porte désormais sur la **feuille**, pas sur le chemin, et toute sortie
(`CloseArea`, `Blocker`, `Close*`, `BackButton`) est **inconditionnellement autorisée**. Un
garde ne doit jamais interdire de sortir.

## Ce qui marche, et ce qui ne marche pas

Marche : lire l'écran, identifier les prefabs, fermer un popup (64 → 48 boutons, 0,5 s),
revenir à l'accueil (`maison`, 15 → 44 boutons).

**Ne marche pas : l'onglet Héros ne monte pas.** 3/3 — l'écran d'accueil se démonte, il ne
reste que le chrome (barre d'onglets + barre de ressources, 15 boutons), et aucun prefab
d'écran n'apparaît. L'accueil, lui, se remonte. Non attribué : la trace de `crash-trap`
montre un `native_crash` répété via `il2cpp_unhandled_exception` (compteur à **646**), mais
**il précède la navigation** — son dernier flush est antérieur aux clics. Rien n'autorise
à l'imputer aux clics, ni à l'écarter.

## Les garde-fous du client

- **La session est partagée** : `exiger_calme()` refuse d'agir tant qu'un runner vit. Une
  panne de capteur refuse **aussi** — on ne déplace pas le jeu sur un budget inconnu.
- **Tri-état** : `None` = pas mesuré. Jamais un écran vide rendu comme « rien à l'écran » —
  ce qui compte, puisque l'écran transitoire *est* légitimement presque vide.
- Le jeu n'est **jamais lancé** par ce module : c'est un geste utilisateur.

## L'architecture — quatre couches, chacune adossée à une mesure

Le paquet `scripts/python/gamenav/` remplace le script plat. `game_nav.py` n'est plus qu'une
façade CLI, en **forme B** (`import X` puis `X.foo()` — la forme A désarmerait les patchs,
cf. `#485-r1-r1`).

| couche | module | la mesure qui la justifie |
|---|---|---|
| L0 transport | `transport` | deux voies pour une intention ; le clic UI et l'invoke IL2CPP (ce dernier **déclaré et refusé** — aucun RPC générique n'existe) |
| L1 observation | `vue` | l'écran s'identifie par ses **prefabs** ; 38 → 57 boutons sans changer d'écran |
| L1 bis pixels | `regard` | capturer, **diffuser** deux captures, redimensionner avec mémoire du rect |
| L2 agir | `agir` | « agir » n'existe pas : seul « agir **et prouver** » existe |
| L3 carte | `carte` | le graphe est une **donnée** ; presque vide, et c'est honnête |

Plus deux transverses : `journal` (qui rend **comptable** l'écart retour-vs-effet) et
`secours` (jamais gaté, hors du graphe).

`vue.identifier` rend **trois** valeurs, et la troisième est le point : `TRANSITOIRE` n'est
pas une erreur, c'est un état où le jeu se tient réellement. Démonstration de bout en bout :
`HomeScreen` → onglet Héros → `TRANSITOIRE` (2,8 s) → `maison` → `HomeScreen` (1,3 s), les
deux transitions avec `ok=False` au retour et l'effet contraire.

## Les pixels : quatre râteaux, tous silencieux

1. **Deux process nommés « tacticus »** — le premier rendu est le **launcher** (minimisé,
   160×28). Discriminer par le **chemin**, jamais par le nom, et surtout pas par « l'image
   n'est pas noire », qui était vert dessus.
2. **`PrintWindow` ne voit pas la swap chain d'Unity** — fragment obsolète, 464/576 pixels
   non noirs. **Non noir n'est pas bon.**
3. **`SetProcessDPIAware` ne suffit pas sur un bureau étendu.** Il rend le process conscient
   du DPI *système*, soit celui du moniteur **primaire** ; l'écran de gauche est à 250 %, si
   bien qu'on prélevait 1549×925 dans une fenêtre de 3872×2312 — **son coin supérieur
   gauche**, lu à tort comme « l'UI déborde la fenêtre ». La bonne primitive est
   `SetThreadDpiAwarenessContext(-4)`, per-monitor v2.
4. **Capturer un rectangle ≠ capturer la fenêtre.** Ce qui la recouvre entre dans l'image :
   deux captures ont ramassé les applications de l'utilisateur. `WindowFromPoint` au centre
   le vérifie, et la capture est **abandonnée** plutôt que livrée non située.

⚠ **Et il n'y avait aucune contrainte de proportion.** J'avais conclu que le jeu refusait le
portrait après un retour spontané à 1549×925. Faux : 560×600, 500×600 et 440×600 tiennent
tous les trois. Le rejet de 620×1040 venait de la **hauteur** — 2600 px physiques sur un
écran qui en fait 2400. Une contrainte de débordement, pas de forme.

**Le point d'équilibre mesuré** : `440×600` logique = **1100×1500** physique. Le jeu occupe
~89 % du cadre (contre 39 % à 1549×925), et le grand côté passe sous le seuil de réduction
(~1568 px) — donc lecture **1:1**. Coût ≈ 2 200 tokens, soit deux `Read`.

## Le pont libellé ↔ chemin (fenêtre du 2026-08-08, session 4)

**Le déclencheur** : `uiList` rendait des **noms d'objets** là où l'humain lit des
**libellés**. Mesuré — *aucun* bouton de l'arbre ne contient « mission » dans son chemin,
alors que l'écran en affiche un (c'est `button_special_quests`). Sans ce pont, aucun pilote
ne peut prendre une instruction dans le vocabulaire de l'utilisateur.

`ButtonRow` porte désormais `label`, `pos` et `space`. Résolution **best effort** : une
classe absente dégrade le champ, jamais `ensureRefs` — faire tomber tout `uiList` pour un
champ d'agrément serait une régression bien pire que l'absence du champ.

**`label` : livré.** 22 boutons sur 77 en portent, et ils sont justes — numéros de nœuds de
campagne (60–75), `Anuphet` (nom de chapitre), `60k` / `26k` (ressources). Ordre d'essai
`TMPro.TMP_Text` puis `UnityEngine.UI.Text` ; viser la **base** `TMP_Text` attrape aussi
`TextMeshProUGUI`.

**`pos` : NON livré, et le module le dit.** `space` vaut **`camera`** sur les 77 boutons :
les canvases du jeu sont en **ScreenSpaceCamera**, donc `Transform.position` est en unités
**monde**, pas en pixels écran. Le garde a rendu `null` en nommant le mode au lieu d'émettre
des nombres plausibles et faux. Suite en `#595-r2`.

⚠ **Deux gardes, parce qu'une seule hypothèse pouvait tomber de deux façons.** Le mode de
canvas est l'un ; l'autre est le **domaine** : sur Win64 un `Vector3` (12 octets) se rend par
**pointeur caché**, pas dans les registres xmm, et une déclaration d'ABI fausse ne lève pas —
elle rend trois flottants crédibles. `lirePosition` borne donc par `Screen.width/height`
(deux statiques rendant un `int`, aucune ABI douteuse) et rend `null` hors domaine. Sans ce
second cran, le premier n'aurait rien prouvé.

**La charge de la fenêtre n'était pas celle annoncée.** Sur six volets en attente : `#347-r3`,
`#350-r3a` et `#347-r1` étaient **déjà dans l'arbre** — donc déjà dans le bundle, et le
reinject les active gratuitement. `#552-r2`, `#545-r1` et `#487-r2` ne sont cités par **aucun**
fichier de `frida/hooks` : ce ne sont pas des volets à embarquer, ce sont trois tranches de RE
à écrire. Qualifier avant d'ouvrir évite de remplir une fenêtre avec du vide.

Fenêtre : drain armé, `liveRunners` 0, inject **54,1 s**, `amorceError` nul, session 4.
⚠ `session.warmed` reste à `false` alors que l'amorce a réussi — le drapeau de l'amorce
n'est pas posé par le chemin d'inject. Sans conséquence ici, mais c'est un capteur qui ment.

## Ce que ça n'est pas

Ce n'est pas un pilote de campagne. La chaîne de l'amorce reste codée en dur
(`PLAY_BUTTON_KEY`, `"campaign1"`, `NODE_SUFFIX`), et rien ici ne la remplace. Ce module
donne l'**observation** et le **clic honnête** ; en faire une navigation dirigée demande un
« où suis-je » plus riche que la liste des prefabs présents.
