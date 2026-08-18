# #10034 -- trois citations fausses et quatre foyers morts : la meme cause, deux formes

Trois tests rouges sur `master` = `3395871c`, tous causes par des references FAUSSES dans
`docs/rl/backlog.md`. Aucun defaut de cliquet, aucun defaut de cache.

## 1. Les trois citations : ce n'est pas le NOM qui etait faux, c'est l'INTERFACE

Le discriminant de `probe_477r24r1` est le RECEPTEUR ecrit au site. Sur une ligne de tableau qui
nomme `IOperationProcessor`, **tout** slot ecrit `slot N = Nom` lui est rapporte. Les fiches
citaient, sur cette meme ligne, des slots d'une AUTRE interface.

| fiche | ce qui etait ecrit | ce que dit le natif | ou c'est LU |
|---|---|---|---|
| `#10015-r1` | `slot 9 = AddBattleEvent` | `IMatchState` **9** = `IdunBattle.Core.MatchState$$AddBattleEvent` (1 arg) | `EvaluateTriggerOperation$$Execute`, ses DEUX surcharges : `FUN_18002a380(9, DAT_183367008, ...)` |
| `#10015-r1` | `slot 10 = TryDequeueBattleEvent` | `IMatchState` **10** = `IdunBattle.Core.MatchState$$TryDequeueBattleEvent` (1 arg) | `AtomicGroupOperation$$Execute`, walk d'itable `DAT_183367008` rang 10 |
| `#576-r2` | « le **PREMIER** geste est le slot **46** » | le **DERNIER** geste est le slot **47** | `AddEffectOperation$$AddNewEffect` |

Lues contre `IOperationProcessor`, les deux premieres tombaient sur `RemoveMachine` (9) et
`ReAddMachine` (10) -- d'ou le rouge.

**Le discriminant natif est le `DAT_` de l'itable**, et il se lit sans ambiguite parce que les deux
champs sont a des offsets differents d'`AOperation` :

    DAT_183367008  =  IMatchState           a  AOperation+0x18
    DAT_18336edb0  =  IOperationProcessor   a  AOperation+0x20

`AtomicGroupOperation$$Execute` porte les DEUX dans une seule fonction, ce qui les confronte :
rangs 20/21/10/41 sur `+0x18`, rangs 78/85 sur `+0x20`. Les arites concordent une a une avec
`metadata/interface_slots.tsv` et `metadata/ioperationprocessor_slots.tsv`. Confirmation
independante : le CLAUDE.md etablit deja `DAT_18336edb0` = `IOperationProcessor` par la recherche
litterale `(6,DAT_18336edb0` (#10015-r2).

### Le piege de `#576-r2` : le MEME ORDINAL existe des deux cotes

`AddNewEffect` commence par `IMatchState` rang **46** = `Add(effect)` et finit par
`IOperationProcessor` rang **47** = `RefreshEffects(options)`. L'auteur a fusionne les deux : il a
pris l'ordinal du premier geste et le nom du dernier. C'est la forme la plus couteuse de l'erreur,
parce qu'elle est **silencieuse en ordinal** -- exactement ce que le CLAUDE.md decrit pour les
enums, transpose aux tables d'interface.

S'y ajoute que `RefreshEffects` est **SURCHARGEE** : rangs 46 ET 47, un parametre chacune. Le nom
cite n'etait donc pas faux, seul l'ordinal l'etait -- et aucun cliquet ne pouvait le voir, puisque
le nom concorde aux deux rangs.

**Le verdict de `#576-r2` ne bouge pas** : les DEUX surcharges relaient directement
`RefreshEffectsOperation$$Execute`, sans file d'attente. Le refresh reste synchrone, et il reste le
geste qui decide de l'application.

### La reparation DEPLACE la garde, elle ne la retire pas

Ecrire le qualificateur (`IdunBattle.Core.MatchState$$`) fait deux choses a la fois :

* `probe_477r24r1` cesse d'apparier -- son `_NOM` refuse une tete de namespace (`IdunBattle` suivi
  de `.C`), et son `_QUAL` n'accepte que `OperationProcessor`/`processor.`/`$$` isole ;
* `probe_477r25` **capte** le couple et le confronte a la table `IMatchState`, ou il est JUSTE.
  C'est le regime multi-interfaces de ce cliquet, qui exige precisement un qualificateur quand
  plusieurs interfaces sont nommees sur la ligne.

Verifie apres coup : la recolte de `probe_477r25` porte
`Citation(fichier='docs/rl/backlog.md', iface='IMatchState', slot=10, nom='TryDequeueBattleEvent')`,
et il n'est pas dans les faux.

Pour `#576-r2`, la citation juste `slot 47 = Core.Services.OperationProcessor$$RefreshEffects` est
appariee **sans franchir de virgule**, ce qui fait CEDER le couple franchissant
`(47, AddNewEffect)` par `ceder_aux_locaux` (#477-r42). Le second test rouge tombe par le mecanisme
prevu, pas par un contournement.

## 2. Les quatre foyers morts : un commit avait corrige le GENERE, pas la SOURCE

Les quatre chemins ont ete supprimes par **`41a7b05a`** (« retrait des NEUF endpoints d'INTERFACE --
piloter l'ecran est proscrit »). Ce commit dit lui-meme avoir barre les foyers dans
`docs/rl/index-foyers.md`. Mais `index-foyers.md` est un **GENERE**, derive de `backlog.md` : la
reparation a ete faite du mauvais cote, et elle a tenu jusqu'a ce que #1174 re-derive l'index.

| fiche | sort | mesure qui le fonde |
|---|---|---|
| `#595-r1` | **SANS OBJET** | son discriminant EST un clic ; **0** des neuf endpoints (`uiClick`, `uiList`, ...) ne subsiste dans `frida/hooks/**` |
| `#595-r2` | **REQUALIFIEE, reste ouverte** | `invoke.ts` vit, et `sret`/`il2cpp_array_new` y sont toujours ABSENTS (0 occurrence) ; mais son consommateur (`pos` via `uiList`) est mort |
| `#596` | **RESOLU** | `frida/hooks/features/fsm-input.ts`, arrive par `2d7cc682 feat(#596)` : capture au `UnitSelectionFsm$$.ctor` + RPC `fsmTap`/`fsmInput`/`fsmStateInvoke` |
| `#596-r2` | **RESOLU** | `e31b36be` (#993) a retire `findButtonBySuffix` ; le warmup passe par `ViewCommandExecutor$$StartCampaignMatch(campaignId, locationIndex, ...)`, la voie 0-based que la fiche designait |

⚠ **Un foyer mort ne vaut pas une fiche morte, et l'inverse non plus.** `#596` etait VIVANTE et
RESOLUE avec des foyers morts ; `#595-r1` est morte pour une raison qui n'a rien a voir avec la
disparition de ses fichiers (une DECISION de doctrine). Le seul moyen de les separer est de lire ce
que la fiche demandait de FAIRE, jamais l'etat de ses chemins.

⚠ Et le foyer de `#596` etait **faux le jour ou il a ete ecrit** : la fiche etablit qu'on joue
« sans un seul pixel », et son foyer designait le pilotage d'ecran.

## 3. Ce que cette tranche ne couvre PAS

* **`master` porte un CINQUIEME rouge, non annonce et hors territoire** :
  `test_477r25 ... test_etage3_aucune_citation_fausse` sur `tau.py` L1829. Mesure par `git stash` :
  **identique sur l'arbre propre**, sans aucune de mes editions. Ouvert en **`#10034-r1`**.
* **`docs/rl/index-foyers.md` doit etre RE-DERIVE au merge** -- il est GENERE et je n'y touche pas.
  Delta mesure : **15 lignes (5 +, 10 -)**, et les quatre chemins morts y tombent de 4 a **0**.
  Commande : `python scripts/python/probe_603_index_foyers.py --index`.
  Consequence : `test_603 ... test_etage5_l_index_se_re_derive_a_l_identique` est ROUGE tant que ce
  n'est pas fait. C'est un rouge de REGENERATION, pas de fond ; il etait vert avant et le
  redeviendra.
* La repartition 46/47 entre les deux surcharges de `RefreshEffects` **n'est pas tranchee** : les
  deux ont un parametre et un corps de relais quasi identique. Ce qui EST etabli, et suffit, c'est
  que `AddNewEffect` invoque le rang **47** (`+0x2f` lu au walk d'itable).
* Les autres citations de slot de `#10015-r1` (rangs 20, 21, 41, 78, 85) sont **qualifiees** mais
  restent hors de portee des deux cliquets : elles n'emploient pas la forme `slot N = Nom`, et
  `Get` (3 caracteres) est sous le plancher de `_NOM`. Elles ne sont pas vertes, elles ne sont pas
  regardees.
