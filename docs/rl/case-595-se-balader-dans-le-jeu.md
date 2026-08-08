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

## Ce que ça n'est pas

Ce n'est pas un pilote de campagne. La chaîne du warmup reste codée en dur
(`PLAY_BUTTON_KEY`, `"campaign1"`, `NODE_SUFFIX`), et rien ici ne la remplace. Ce module
donne l'**observation** et le **clic honnête** ; en faire une navigation dirigée demande un
« où suis-je » plus riche que la liste des prefabs présents.
