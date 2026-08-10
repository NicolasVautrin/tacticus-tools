# #600 — le gel du dispatch natif, et l'explication qui n'a pas survecu a son remede

**2026-08-10**, build `rnca9r7q6c`. Envoyer une Operation par
`ExpeditionGameEvents$$DispatchExpedition` au lieu de l'ecran.

## Le tableau des cinq tentatives

| # | callback | resultat |
|---|---|---|
| 1 | nul, equipe INCOMPLETE (2/3) | process MORT, rien enregistre |
| 2 | nul, `this` de la MAUVAISE classe | exception capturee, jeu vivant, rien envoye |
| 3 | **nul**, tout le reste vert | **ENREGISTRE par le serveur**, PUIS process mort |
| 4 | `NativeCallback` JS dans `invoke_impl` | **JEU GELE** |
| 5 | page native `ret` dans `invoke_impl` | **JEU GELE, a l'identique** |

## Ce que #5 refute

Apres #4 j'avais ecrit : *le delegate est invoque depuis le thread de reponse reseau, Frida
doit entrer dans QuickJS qui est mono-thread et occupe, donc deadlock*. Remede : remplacer le
`NativeCallback` par une page contenant un seul `0xC3`. **Zero JavaScript dans le chemin.**

Le gel s'est reproduit **a l'identique**. Une explication qui survit a la suppression de sa
cause supposee n'explique rien — elle est **refutee**, pas a affiner. La regle generale
(« pas de callback JS sur un thread natif ») reste bonne ; elle n'etait simplement pas la
cause ici, et je l'avais deja ecrite en memoire comme si elle l'etait.

## Ce que la mesure dit

Lecture du process fige par `OpenThread` + `GetThreadContext` (script :
`scratchpad/ou_bloque.ps1`, pas de debugger installe sur la machine) :

- **142 threads sur 142** ont leur RIP dans `ntdll.dll`. **Aucun** dans `GameAssembly.dll`.
  Personne ne boucle : tout le monde **attend**. CPU du process plat (+0,05 s en 3 s).
- Le main thread porte exactement **trois** cadres `GameAssembly`, du plus externe au plus
  interne :

```
FUN_1801f7b30+0x59    il2cpp_runtime_invoke   (pose exc = 0, puis appelle)
FUN_1801f8090+0x49    Runtime::Invoke         (retour d'invoker_method(...))
FUN_1801eb760+0xd5    primitive de VERROU     (compteur de recursion en TLS, LOCK/UNLOCK,
                                               puis attente)  <-- le plus interne
```

Notre `invokeMethod` entre donc dans le natif, et le natif se bloque sur un verrou que
personne ne relache. Les trois fonctions sont des `FUN_*` : IL2CPP runtime, sans metadonnee,
donc sans nom — c'est attendu a cet etage.

## Pourquoi on ne peut RIEN conclure de plus, et l'isolateur

**Deux gestes nouveaux sont apparus ensemble** en #4/#5 : une **allocation managee**
(`il2cpp_object_new` d'un `Action<System.Boolean>`) et un **appel natif avec un 4e argument
non nul**. La #3 faisait le second **sans** le premier et ne gelait pas. Deux candidats, une
seule mesure.

`expeditionCallbackForge` coupe le paquet : il fabrique le delegate et **n'envoie rien**.

- il **gele** -> la cause est l'allocation (init de classe, GC, ou l'un des deux sous Frida) ;
- il **rend la main** -> l'allocation est innocente, le verrou appartient a l'appel natif.

## VERDICT DE L'ISOLATEUR (session 58, jeu relance)

**L'allocation est INNOCENTE.** Six fabrications consecutives : `ok: true`, **0 ms** chacune,
jeu `Responding: True` apres. Classe obtenue == classe attendue (`0x21fa115a4d0`), les cinq
champs se relisent identiques a ce qu'on a ecrit, et le compteur de gchandles monte 0 -> 6.

Donc le blocage est **dans l'appel natif** `DispatchExpedition`, pas dans la preparation.

## L'hypothese qui reste, et pourquoi elle change le coupable

Le cadre le plus interne (`FUN_1801eb760+0xd5`) est un **rendez-vous** : compteur de
recursion en TLS, `LOCK`/`UNLOCK`, puis une boucle « tant qu'il reste des attendeurs :
signaler, puis attendre ». Avec **142 threads sur 142 dans ntdll**, la lecture la plus
economique est un **stop-the-world qui ne repart pas** — typiquement un GC, ou un
rendez-vous de suspension de threads.

Ce que ca expliquerait, y compris ce qui semblait incoherent :

- le forge alloue **un** petit objet et ne declenche presque jamais de collecte ;
  `Execute` alloue plusieurs objets **et** part sur le reseau — beaucoup plus d'occasions ;
- `CLAUDE.md` porte deja l'avertissement jumeau : Frida suspend les threads pendant un scan
  de tas IL2CPP, et le detecteur de freeze d'Unity tue alors le process. Meme couple.
- surtout : ca ferait du callback un **faux coupable pour le gel**. Il y aurait alors DEUX
  pannes distinctes que je traitais comme une seule — le callback nul qui LEVE a la reception
  (#1, #3, etabli par le decompile), et un rendez-vous GC au moment de l'envoi (#4, #5).

⚠ **Ce n'est pas etabli.** Prediction falsifiable : si c'est un GC, l'echec est **flaky**, pas
deterministe, et forcer une collecte depuis le pump (`gcRoot.collect()`) doit geler le jeu
**sans aucun envoi**. C'est le prochain test, et il ne coute pas un dispatch.

Tant que cette question n'a pas de reponse mesuree, `AUTORISER_ENVOI_NATIF = false`.

## Un piege de lecture rencontre en chemin

`ExpeditionGameEvents$$DispatchExpedition` se decompile avec **trois** arguments (plus `this`),
et relaie `(commande, id, units, bonus)` — pas de callback en vue. Ne PAS en conclure que le
callback n'existe pas : Win64 passe les quatre premiers en registre et **le cinquieme sur la
pile**, que Ghidra ne modelise pas ici. La metadonnee IL2CPP, elle, donne bien **4** parametres
(`findMethodByParamCount(..., "DispatchExpedition", 4)` resout). La table prime sur le
decompile pour compter des parametres.

## Le defaut reel trouve en chemin (merci a l'utilisateur)

`il2cpp_object_new` rend un objet que **rien de manage ne reference** : notre seule prise est
un `NativePointer` dans le tas de Frida, que le GC IL2CPP ne scanne pas. Entre l'allocation et
le moment ou le natif range le delegate dans son display class, une collecte peut le liberer —
et `invoke_impl` serait alors invoque sur de la memoire recyclee, **a la reception de la
reponse**, loin du site fautif. Corrige par `gcRoot.add` (`il2cpp_gchandle_new(obj, pinned)`).

Vrai independamment du gel : c'est un defaut, pas une hypothese.

## Ce qui reste acquis

- Le `callback` **n'est pas optionnel** : `<Execute>b__0` tombe sur
  `raise_null_reference_exception` + `INT 3` quand il est nul. C'est ce qui a tue #1 et #3.
- Le callback du presenter (`ExpeditionDispatchScreenPresenter$$<OnDispatch>b__0`) ne fait
  **rien** en cas de succes ; en cas d'echec il affiche un message. C'est un rapporteur
  d'erreur d'UI. La mutation, elle, **precede** l'appel — d'ou #3 enregistre puis mort.
- `bonusFulfilled` **n'entre pas dans la requete reseau** : il n'alimente que le modele local
  et le contexte de quete. Le serveur tranche le bonus.
- ⚠ **Un envoi part meme si le jeu meurt ou gele.** Lire `expeditionBoardRead` AVANT toute
  reprise, sinon on dispatche deux fois. Verifie : apres le gel de #4, `chaos_tzeench_r_01_10`
  etait toujours en `status: 0`.
- ⚠ **Le gel ne se signale pas.** Process vivant, session Frida `running`,
  `/api/admin/status` serein. Le seul temoin est un RPC qui revient — et
  `Get-Process().Responding == False` le confirme de l'exterieur.
