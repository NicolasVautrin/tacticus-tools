# #992 — entrer et sortir de bataille SANS TOUCHER A L'UI, et la surface de commandes rendue requetable

**Build** `rnca9r7q6c` · **sessions Frida** 73-76 · 2026-08-12

## Le resultat

Aller-retour complet, **zero interaction d'interface** — ni navigation, ni clic de noeud, ni
clic de *play*, ni menu de pause, ni popup de confirmation :

| geste | verdict |
|---|---|
| `ViewCommandExecutor$$StartCampaignMatch("campaign1", 74, Standard, 0x0101)` | en bataille ; **builder complet a froid** |
| `IdunMainView$$OnBattleSurrender()` | popup de confirmation (`PauseSurrender` **DIFFERE**) |
| `IdunMainView$$ContinueSurrender()` | retour campagne, **RENDU** (verifie a la capture) |

⚠ **ENTRER PAR LA BONNE PORTE — c'est toute la difference, et je l'ai apprise en cassant.**
Un premier essai appelait **`ContinueSurrender` SEULE** : la bataille se terminait bien
(`get_IsBattleActive -> False`) mais le jeu restait **sans aucun ecran rendu**, et il a fallu
`ToTacticiansMenu()` pour le recuperer. La chaine mesuree disait pourtant laquelle est
l'entree. Entrer par le milieu donne la FIN sans ce qui la PREPARE.
⚠ Et **`get_IsBattleActive: False` ne prouve pas qu'on est revenu quelque part** : dans les deux
cas il rendait `False`. Seule la CAPTURE distingue « sur la campagne » de « ecran noir ».

**~2 s**, contre **19-26 s** pour le meme aller-retour pilote a l'UI. Jeu `Responding: True`
apres coup, executeur toujours joignable, scene de bataille redechargee.

## ET CA NE COUTE PAS DE STAMINA — mesure, pas espoir

`GetCurrentAmount()` sur `CampaignProgression._staminaProgression` :
**848 avant / 848 apres lancement / 848 apres retraite**, `IsRegenerating: False` tout du long
(le drapeau bascule des qu'on passe sous le plafond).

⚠ **Un accord peut venir d'un capteur MORT** — d'ou deux temoins :
- **CONTROLE PAR LE CHEMIN NORMAL** : le warmup pilote a l'UI, joue juste apres, rend
  **848 / regen=False** lui aussi. Les deux chemins sont gratuits.
- **TEMOIN POSITIF SANS RIEN DEPENSER** : `CanSpend(n)`, predicat pur calcule par la
  comptabilite du jeu, bascule **exactement** entre `848 -> True` et `849 -> False`. Le nombre
  que rend le lecteur est donc le solde REEL, pas une constante.

**Cause** : on se retire **avant le deploiement**, ce que le natif nomme lui-meme
`hasSurrenderedBeforeDeployment`. La bataille n'est jamais facturee.
⇒ Corrige `feedback_no_warmup_until_asked`, qui chiffrait le warmup a « une DEFAITE ».

## Comment on ATTEINT ces objets — deux voies, et la difference est mesuree

| | parent | voie |
|---|---|---|
| `idun.shared.commands.ViewCommandExecutor` | **`System.Object`** | `FindObjectsByType` ne le trouvera JAMAIS. Champ **nomme** `_viewCommandExecutor` d'`idun.UI.IdunNavigation`. |
| `idun.IdunMainView` | **`UnityEngine.MonoBehaviour`** (352) | enumerable, surcharge a 3 arguments (`FindObjectsInactive.Include`) |

**Identite CONFIRMEE** : l'instance rendue par le champ nomme (`0x22f83083000`) est **exactement**
le `thisPtr` que le capteur relit quand l'UI appelle `StartCampaignMatch`. Meme objet, pas un
homonyme.

⇒ « ca ressemble a un composant » ne dit RIEN : c'est la CHAINE D'HERITAGE qui tranche, et
`viewSurface` la publie pour qu'un glissement de build se voie au lieu de rendre 0.

## La surface, requetable et COMPOSABLE

`features/view-command.ts` : `viewSurface` (qui est joignable, par quelle voie, chaine d'heritage)
· `viewList` (les methodes, filtrees, avec leur arite) · `viewField` (**chemin de champs
POINTES**, resolus par NOM sur la classe REELLE a chaque pas) · `viewInvoke` (appel garde).

`viewInvoke`/`viewList`/`viewField` acceptent `surPointeur` : les retours de type reference
sortent en pointeur + classe reelle, donc l'appelant **COMPOSE** le chemin. Mesure qui l'a rendu
necessaire — lire la stamina exige quatre pas heterogenes :

```
executor ._campaignProgressions            (champ)
         .GetCampaign(Standard, campaign1) (methode, 2 arguments)
         ._staminaProgression              (champ)
         .GetCurrentAmount()               (methode)
```

Aucune cible fixe n'exprime ca, et deux des pas sont des CHAMPS.

**483 methodes** sur `ViewCommandExecutor` (`class_get_methods` en live). ⚠ Le « 516 » d'un grep
de `methods.tsv` comptait les types imbriques generes — la table est indexee par nom PREFIXE,
pas par classe.

**7 statiques** sur `IdunMainView`, dont `get_IsActive` et `get_IsBattleActive` : un **oracle
d'etat de bataille sans instance et sans UI**, la ou le harnais deduisait l'etat des ECRANS.

**Refus executables** : famille `Cheat*` refusee **INCONDITIONNELLEMENT** (elle mute le compte —
une garde qu'un drapeau desarme n'est pas une garde) ; tout invoke exige `confirmer: true`.

## La chaine de retraite, LUE et non deduite

`features/retreat-capture.ts` ancre les 5 methodes de sortie d'`IdunMainView` et les 3 predicats
des sources de mode, et note **la pile complete** de chaque fire (RVA, resolues hors ligne). Six
fires du warmup :

```
IsSurrenderFromPauseMenuEnabled -> True   <- IdunGameHud.ShowPauseMenu+0x24f
OnBattleSurrender                         <- UnityEvent.Invoke (bouton)
PauseSurrender                  -> True   <- IdunMainView.OnBattleSurrender+0xd9
ContinueSurrender                         <- UnityEvent.Invoke (bouton de CONFIRMATION)
ProcessFinishSurrender
```

**`PauseSurrender` rend `True` : il DIFFERE.** Et `ContinueSurrender` n'est pas rappelee par lui
— elle est invoquee par un **UnityEvent**. C'est ce qui rend l'appel direct possible : il saute
le popup de confirmation.

⚠ **`ProcessFinishSurrender` n'est PAS « le terminal appele une fois par retraite sur les deux
branches »** — c'etait une deduction, et elle est REFUTEE. `UNCONDITIONAL_CALL` est le type
d'**INSTRUCTION** chez Ghidra (call direct vs indirect), **pas une propriete du flot** : dans les
deux appelants l'appel est sur une BRANCHE, l'alternative etant `ProcessFinishBattle`.

## Deux pieges payes en route

1. **Ne jamais ancrer la methode qu'on invoque** (`3 gels sur 3`, en-tete d'`il2cpp/delegate.ts`).
   `retreatInvoke` DEPOSE tous ses ancrages avant d'appeler et les repose apres — et il DIT que
   les fires de la chaine ne sont alors **pas mesures**, au lieu de rendre une liste vide qui se
   lirait « rien ne s'est produit ». Meme raison pour laquelle le capteur de `StartCampaignMatch`
   est laisse DESARME quand on invoque `StartCampaignMatch`.
2. **Une instance epinglee peut etre DETRUITE.** Apres un warmup, `retreatStatus` rendait un
   `mainView` non nul alors que `FindObjectsByType` rendait **0 instance** : `gcRoot` garde le
   POINTEUR, pas l'objet Unity. Confrontation ajoutee via `UnityEngine.Object$$op_Inequality` --
   l'operateur surcharge, le seul qui distingue « nulle » de « detruite » (c'est celui que
   `thor.Loader$$LoadBattle` utilise lui-meme).

## Ce qui reste NON ETABLI

- **La disposition du `Nullable<Boolean>`** : l'UI passe `0x0101`, donc `hasValue` et `value`
  valent tous deux 1 et **les deux lectures concordent**. Non tranche. La forme d'argument
  `{brut, octets}` transporte les octets OBSERVES tels quels plutot que de les recomposer depuis
  une hypothese.
- **Le statique est-il efface en fin de bataille ?** `ViewCommandExecutor$$StartMatch` publie la
  source dans les statiques d'`IdunMainView` (`statics[0] = wrapper`, `wrapper+0x20 = source`)
  **avant** `thor.Loader$$LoadBattle`, et `IdunMainView$$Start` la relit : l'executeur DEPOSE, la
  scene RECUPERE. Ce que devient le slot apres coup n'est pas mesure.
## Remplacer le warmup : MESURE A FROID, et la limite qu'elle revele

Session **77**, injectee `{"warmup": false}` (`warmed: false`), **aucune UI jouee** :

| `campaignBuilderStatus` | `hasGameConfig` | `hasUnitProgression` | `hasInstance` |
|---|---|---|---|
| a froid, avant tout | **true** | **true** | **false** |
| apres le seul `StartCampaignMatch` | true | true | **true** (`0x231ddd0f1c0`) |

⇒ **L'ENTREE programmatique suffit a armer le builder.** Et les deux autres champs etaient
**deja vrais a froid** : ils viennent du hook de boot (`auto-boot.ts` sur `IdunNavigation$$Init`),
pas du warmup — l'idee qu'il faille une bataille pour les obtenir etait fausse.

⚠ **MAIS LA SORTIE NE L'EST PAS, et c'est mon propre garde qui l'interdit.** `retreatInvoke`
exige que la methode ait ete OBSERVEE dans le journal ; sur une session froide, aucune retraite
pilotee par l'UI n'a eu lieu, donc `ContinueSurrender` n'a jamais tire et le RPC **REFUSE** —
verbatim : « rien n'etablit que c'est l'entree que le jeu emprunte ». Le jeu reste alors en
bataille (`get_IsBattleActive: True`), et il faut `recover-from-battle` (voie UI) pour en sortir.

Le garde n'est pas a retirer : il a ete pose parce qu'une chaine deduite des NOMS a deja ete
dementie par la mesure. Mais il rend le chemin programmatique **non autosuffisant a froid** —
il lui faut une retraite UI par session pour s'amorcer. Deux issues, aucune tranchee :
graver l'observation entre sessions, ou faire porter la preuve par le DECOMPILE plutot que par
le fire. **Residu ouvert.**

- Le warmup capture aussi `IdunUniverse` ; ce chemin ne le touche pas, et ce n'est **pas mesure**
  ici (`campaignBuilderStatus` ne le publie pas).
- `CompleteLocationHandler$$HandleClearReconciliationData(hasSurrenderedBeforeDeployment)` :
  efface-t-il au lieu d'enregistrer ?

## Pointeurs

`frida/hooks/features/view-command.ts` · `frida/hooks/features/retreat-capture.ts` ·
`frida/hooks/il2cpp/delegate.ts` (delegate inerte + ses quatre pieges) ·
`docs/rl/case-991-start-campaign-match-invoke-direct.md` ·
`docs/rl/case-390-r2-signal-de-sortie-de-bataille.md`
