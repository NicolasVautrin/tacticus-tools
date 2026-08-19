# #989 — `CampaignGameModeSource` : TRANSIENT par bataille, pas une liaison DI

**Verdict : (B).** Il n'existe **aucune** instance de
`IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource` tant qu'aucune bataille de campagne
n'a été lancée. Il n'y a **rien à résoudre** : la piste « remplacer le pilotage d'UI de l'amorce
par un `Resolve` » est **CLOSE**.

Mesuré le 2026-08-12 sur le build `rnca9r7q6c` (jeu = dump = `data/symbols/CURRENT`).

## Le discriminant : le site de création

`CampaignGameModeSource$$.ctor` a **une seule xref de code** dans tout le binaire —
`idun.shared.commands.ViewCommandExecutor$$StartCampaignMatch` — qui fait, **en ligne** :

```
this_00 = il2cpp::vm::Object::New(<Il2CppClass* CampaignGameModeSource>)
CampaignGameModeSource$$.ctor(this_00, ...17 args...)
ViewCommandExecutor$$StartMatch(this, this_00, checkIfAlreadyRunning: true)
    -> thor.Loader$$LoadBattle(0)
```

C'est un `new` C# pur : allocation GC + ctor, aucun conteneur. **Créer l'instance et lancer la
bataille sont le même geste**, dans la même fonction, sans point de sortie entre les deux.

Les deux autres xrefs sont **structurelles** et présentes pour *toute* méthode du binaire :
la table `.pdata` (`RUNTIME_FUNCTION{Begin,End,UnwindInfo}`) et `g_MethodPointers`
(`Il2CppCodeRegistration`). Ni l'une ni l'autre n'est une liaison.

`ViewCommandExecutor$$StartMatch` dépose ensuite l'instance dans un **statique** (un holder
alloué puis écrit dans le champ statique lu par `thor.visualQuery.VisualQuery$$IsInBattle`,
`idun.IdunMainView$$StartBattle`, …). C'est ce qui la rend trouvable par heap scan — **après**,
jamais avant.

## Les trois faisceaux convergents

Aucun ne suffit seul ; ils confirment le site de création.

1. **Aucun conteneur DI n'existe.** `Zenject` = **0 symbole**. Idem `VContainer`, `Reflex`,
   `Microsoft.Extensions.DependencyInjection`, `Autofac`, `Ninject`. Les seuls `*ServiceProvider`
   du binaire sont crypto .NET, Unity Purchasing et VoxelBusters.
2. **La signature interdit le singleton.** Le ctor prend 17 paramètres, dont **trois décrivent la
   bataille lancée** : `campaignId:System.String`, `initialLocationIndex:System.Int32`,
   `enemyIsAiControlled:System.Boolean`. Aucune liaison ne peut les fournir avant qu'on sache
   *quelle* bataille on lance. Les 14 autres sont des interfaces
   (`ICampaignProgression`, `IUnitProgression`, `IGameConfigData`, …).
3. **Le nœud de composition est le `ViewCommandExecutor`, pas un conteneur.** **16 des 17
   arguments** sont lus dans ses propres champs — et le 9ᵉ (`viewCommandExecutor`) reçoit
   littéralement son `this`, ce qui recoupe tout le décodage. Les 3 restants viennent des
   arguments de `StartCampaignMatch`.

**Patron uniforme** sur les 21 ctors `*GameModeSource` : chacun a exactement **un** appelant de
code, un `ViewCommandExecutor$$Start<Mode>Match` (ou un `…SceneMain$$StartBattle` pour Endless et
Sandbox). Une architecture par liaisons n'aurait pas 21 sites d'appel explicites.

## Ce que ce verdict RÉFUTE — et qui était écrit dans notre propre code

`frida/hooks/features/campaign-builder.ts` affirmait, en **quatre endroits**, une injection
Zenject qui n'existe pas. La plus dommageable disait que l'instance est créée *« early during
Tacticus boot — Zenject DI eagerly resolves it »* : **les deux moitiés sont fausses**, et cette
phrase énonce exactement l'hypothèse (A). Les quatre mentions sont corrigées.

C'est le mécanisme à retenir : une prose fausse laissée dans le foyer **fabrique** l'hypothèse
que quelqu'un ira réfuter des semaines plus tard, à ses frais.

## Conséquence

Le cycle de l'amorce (campagne → nœud → play → capture au ctor → pause → retraite, ~14 s) est la
**seule** voie d'obtention du pointeur. Le durcissement de la retraite (**#390**) est donc **la**
bonne réponse à son coût, pas un palliatif en attendant une résolution directe : il n'y a rien
d'autre à attendre.

> Cette fiche a d'abord cité `eb9d6691` comme ce durcissement. Le SHA a **péri pendant la
> tranche** — `b0db23fc`, arrivé entre le lancement de cet agent et son rebase, corrige ce
> premier jet (`ToCampaign` était invoquée avant que la nav existe). D'où la citation par
> **numéro de tâche**, stable, plutôt que par commit.

## Ce qui n'est PAS couvert

- **Aucun contrôle live n'a été fait, et aucun n'aurait tranché** : la session Frida courante a
  déjà été warmée, donc elle a déjà vu une bataille. Elle ne peut pas répondre à « le pointeur
  est-il non nul *avant toute bataille* ? ».
- **Raccourcir le pilotage** (invoquer `StartCampaignMatch` au lieu de cliquer nœud + play) n'est
  **pas** évalué ici : ce serait toujours lancer une bataille, et c'est un natif qui **écrit** —
  à observer avant d'invoquer, jamais l'inverse. Hors périmètre de cette tranche.
- Le probe ci-dessous re-dérive les **faisceaux**, pas le site de création : une xref ne se lit
  que dans Ghidra. Un rouge y signifie « l'architecture a bougé, refais la RE », jamais
  « c'est devenu résolvable ».

## Re-dériver

```powershell
python scripts/python/probe_989_cgms_sans_liaison_di.py
```

Trois étages (paramètres per-bataille du ctor · aucun accesseur statique sur les 24 classes
`*GameModeSource` du dump · aucun type de conteneur DI parmi les 31 356 types), 100 % hors ligne
depuis `data/symbols/<build>/`. Contre-épreuve jouée : les trois étages **mordent** sur entrée
mutée, et ne rougissent ni sur une méthode d'instance homonyme, ni sur une sous-chaîne trompeuse
(`ReflexionUtils`).
