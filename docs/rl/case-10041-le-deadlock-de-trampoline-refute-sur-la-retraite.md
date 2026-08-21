# #10041 — le « deadlock de trampoline » REFUTE sur la chaine de retraite (3/3, puis 3/3)

**Date** : 2026-08-21 · **Build** : `t6dpr4k06g` · **Sessions** : 114 (echappatoire), 116 (code livre)

## La premisse, et ce qu'elle coutait

En-tete d'`il2cpp/delegate.ts`, reprise par `retreat-capture.ts` :

> Invoquer une methode qu'on ancre, depuis du JS qui tourne sur le main thread, deadlocke a
> coup sur (**3 gels sur 3**) : l'appel natif retombe dans notre propre trampoline, Frida veut
> y executer un handler JS, et le runtime est deja tenu par ce thread.

`provoquerRetraite` la servait par un **churn d'`Interceptor`** : `deposerTout()` avant l'invoke,
`reposerTout()` apres — douze `detach` puis douze `attach` sur le thread principal, **en plein
demontage de la scene de bataille**. Puis, le 2026-08-21 au matin, par un **REFUS** quand des
ancres sont armees. Deux parades, une seule premisse.

## Ce qui a mis la premisse en doute : la DATE

| | |
|---|---|
| « 3 gels sur 3 » mesures | ~**2026-08-10** (ere `#600`) |
| `deposerTout` bati dessus | **2026-08-12** (`60fd039a`) |
| `il2cpp_runtime_invoke` passe en `exceptions: "propagate"` | **2026-08-20** (`95e88699`) |

La mesure fondatrice precede le correctif d'exceptions de **dix jours**. Or une exception managee
**confisquee** par Frida (`steal`, le defaut) et un deadlock de trampoline presentent le **meme
symptome** : un RPC qui ne revient jamais. L'attribution a la re-entrance n'etait donc pas
etablie — elle etait *plausible*.

## Le protocole, et pourquoi il compte

Meme nombre d'essais que la premisse qu'il vise : **3**. Un unique succes ne refute pas trois
echecs.

1. Armer les **12** ancrages **AVANT** le montage (l'ancrage sur `IdunMainView$$.ctor` capture
   alors l'instance a la naissance de la scene, ce qui donne le signal d'attente).
2. Monter une bataille de campagne en sandbox (`elite2` noeud 7).
3. Attendre `IdunMainView$$get_IsBattleActive() == true`.
4. Invoquer `IdunMainView$$OnBattleSurrender` — **elle-meme ancree**.

Un essai n'est retenu que s'il est **NON DEGENERE** : ancres effectivement posees pendant
l'appel, **au moins un handler JS ayant tire** (sans quoi on aurait seulement evite le piege, pas
traverse), et `get_IsBattleActive()` passe a FAUX (l'**effet** est produit, pas seulement le
retour).

## Resultat

| essai | session 114 (echappatoire `forcer`) | session 116 (code livre) |
|---|---|---|
| 1 | 1,64 s — 12 ancres, 3 fires, sortie | 1,34 s — 12 ancres, 3 fires, sortie |
| 2 | 1,44 s — 12 ancres, 3 fires, sortie | 0,70 s — 12 ancres, 3 fires, sortie |
| 3 | 1,20 s — 12 ancres, 3 fires, sortie | 0,25 s — 12 ancres, 3 fires, sortie |

**6/6**, `Responding=True` a chaque fois. Le trampoline a bien ete re-entre — les handlers ont
tire **pendant** l'appel — sans geler. Les deux parades sont supprimees.

## Sur la CAUSE, on ne tranche pas — et c'est delibere

Deux explications restent ouvertes :

* **(a) `propagate`.** La premisse date d'avant le correctif ; les trois gels pouvaient etre des
  exceptions confisquees.
* **(b) le REGIME differe.** `#600` mesurait un dispatch de **delegate natif**, pas
  `il2cpp_runtime_invoke`. La premisse pourrait rester vraie chez elle.

Rien ici ne les separe. Ce qui est etabli, c'est que **le piege ne se reproduit pas sur ce
chemin** ; `il2cpp/delegate.ts` garde donc son avertissement pour SON regime.

## Portee — ce qui n'est PAS couvert

La mesure porte sur « **charger, puis sortir aussitot** » (~2 s de bataille active). C'est le
geste que les parades protegeaient, et c'est aussi celui qui avait gele en guerre de guilde. Une
bataille **avancee de plusieurs tours** n'a pas ete eprouvee.

## Deux defauts d'instrument trouves en route

**1. `retreatStatus` ne publiait pas sa propre precondition.** `retreatInvoke` exige
`get_IsBattleActive()`, que le module evalue (`enBataille()`) mais ne publiait pas — un appelant
devait donc la **deviner** depuis `mainViewVivant`. Les deux sont **disjoints**, mesure a l'appui :
`mainViewVivant: true` (l'objet Unity existe) avec `batailleActive: false` (rien a quitter). Une
attente batie sur le premier rendait la main immediatement et l'invoke refusait —
**2 essais sur 3 sortis degeneres** avant correction. `batailleActive` et `mainViewJoignable` sont
desormais publies.

**2. `sandbox_campagne.py` lisait « instance non nulle » comme « bataille en cours ».** Apres une
sortie, `sandboxProbe.instance` reste **non nulle** : l'objet Unity survit a la bataille. Le refus
tombait donc sur un **RESIDU**, et **aucune sortie ne pouvait le lever** — `retreatInvoke` exige
lui-meme une bataille active. On restait coince, sans rien a quitter. Le predicat est desormais
`get_IsBattleActive` (`null` = non mesure -> on refuse aussi) ; l'instance residuelle n'est plus
qu'un avertissement.

⛔ **`sandbox_boss.py` et `sandbox_gw.py` gardent le refus sur l'instance**, et c'est voulu : cote
boss de guilde une **tentative est enregistree AU CHARGEMENT**, donc ecraser un match charge mais
pas encore actif la perdrait — et « `IsBattleActive` pendant la phase de deploiement » n'est **pas
mesure**.

## Residus

* La bataille **avancee** (plusieurs tours) reste non eprouvee sur ce chemin.
* `IsBattleActive` pendant la **phase de deploiement** : non mesure. C'est ce qui empeche
  d'aligner boss/GW sur le predicat de la campagne.
* Le gel de `retreatInvoke OnBattleSurrender` sur une source de **guerre de guilde**
  (2026-08-21, ~60 s puis blocage) n'est **toujours pas explique**. Le churn d'`Interceptor`
  etait l'un des deux suspects ; il a disparu, mais rien ne dit qu'il etait le coupable. L'autre
  suspect tient : le **geste incomplet** — l'UI fait `OnBattleSurrender` -> `PauseSurrender`
  (qui rend `true`, donc DIFFERE) -> bouton de confirmation -> `ContinueSurrender`, et on
  s'arretait au premier. ⚠ Sur une source de **campagne**, `OnBattleSurrender` **seul** sort
  (mesure ci-dessus, 6/6) : la branche prise depend donc de la source, ce qui rend le cas GW
  d'autant plus a mesurer separement.
