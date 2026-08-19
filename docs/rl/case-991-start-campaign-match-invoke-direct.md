# #991 — Remplacer le pilotage d'UI de l'amorce par un invoke de `StartCampaignMatch` ?

**Etat : TRANCHE PARTIELLE.** La RE offline est faite et deux mesures live (lecture seule) sont
acquises. **L'invoke n'est PAS confronte** : il exige d'observer l'appel reel, donc une fenetre de
reinject pour armer le capteur livre ici. Verdict a ce stade : **NON TRANCHE**, et ce qui manque
est nomme au §5.

Build `rnca9r7q6c`. `master` de depart `62b57a95`.

## 1. La question

Le cycle de `frida/hooks/features/auto-boot.ts` pilote l'UI sur trois etapes —
`to-campaign`, `click-node`, `click-play` — dont l'unique effet utile est un appel a

```
idun.shared.commands.ViewCommandExecutor$$StartCampaignMatch(
    campaignId: System.String, locationIndex: System.Int32,
    campaignType: Idun.Shared.CampaignType,
    enemyIsAiControlled: System.Nullable<System.Boolean>)
```

Ces trois etapes sont la moitie fragile du cycle : clics AVALES (#332), repos de 800 ms, chemin de
noeud qui change a chaque run. Les remplacer par un invoke supprimerait cette fragilite — **pas**
le chargement de bataille lui-meme (`StartCampaignMatch -> StartMatch -> thor.Loader$$LoadBattle`),
donc **pas** la retraite.

## 2. Question 1 — l'instance est-elle joignable ? OUI, par `IdunNavigation`

**`ViewCommandExecutor` n'est PAS un MonoBehaviour.** `data/symbols/rnca9r7q6c/frida/classes.tsv`
lui donne pour parent `System.Object` (taille 2040). `Object.FindObjectsByType` ne le trouvera
jamais — c'est exactement le piege que l'en-tete de `frida/hooks/features/ui-windows.ts` documente
sur `thor.Menu.MenuSystems` (`instances: 0`, discriminant `m_CachedPtr`). Le seul accesseur publie
est d'ailleurs `thor.Menu.MenuSystems$$get_ViewCommandExecutor`, sur cette meme classe non
enumerable ; et `thor.Menu.MenuSystems$$.ctor` est l'un des deux seuls sites qui CONSTRUISENT un
`ViewCommandExecutor` (l'autre est `IdunSandboxSceneMain$$<Start>b__4_0`).

**Mais un chemin de champs existe, et il part d'un objet qu'on tient deja.**
`idun.UI.IdunNavigation$$Init` prend `viewCommandExecutor` en **premier parametre** et le range
dans un champ de `this` — lu verbatim au decompile :

```
*(deps + 0x18)          = viewCommandExecutor;      // objet de dependances construit par Init
*((longlong)this+0x248) = *(deps + 0x18);           // ... recopie dans IdunNavigation
```

**Mesure live du 2026-08-12** (RPC `classFields("idun.UI","IdunNavigation")`, session 73,
lecture seule) :

| offset | champ | type |
|---|---|---|
| `0x228` | `_menuSystems` | `MenuSystems` |
| `0x240` | `_gameConfig` | `IGameConfigData` |
| **`0x248`** | **`_viewCommandExecutor`** | **`IViewCommandExecutor`** |

`IdunNavigation` est deja resolue par le depot (`features/auto-boot.ts`,
`features/auto-boot.ts`). Le chemin est donc **le meme patron que `_unitProgression` /
`_gameConfig`** d'`auto-boot.ts` : instance vivante, puis `getFieldOffset(navClass, "<nom>")`.
**Jamais l'offset en dur** — `auto-boot.ts` documente un `_unitProgression` qui a glisse
`0x1F0 -> 0x1D8` entre deux builds.

⚠ **Ce qui n'est PAS encore mesure** : que ce champ soit **non nul** en session, et que la classe
CONCRETE au bout soit bien `ViewCommandExecutor` (l'interface a au moins deux implementations,
dont `idun.tests.TestViewCommandExecutor`). C'est ce que rend le RPC `viewCommandExecutorReach`
livre ici.

## 3. Question 2 — ce que les appelants verifient AVANT

L'appelant UI est `idun.shared.commands.ShowCampaignBattlePreviewPopupCommand$$OnPlayBattleTapped`
(lui-meme appele par `<>c__DisplayClass6_0$$<Execute>b__0`, le callback du bouton play). Il evalue
**deux tests**, tous deux sur `ICampaignProgression`, tous deux de profil `(locationIndex) -> bool` :

1. **slot `0x21`** — faux ⇒ appel du slot `0x102` de `IViewCommandExecutor`, et **retour sans
   lancer**.
2. **slot `0x23`** — faux ⇒ popup portant
   `I2.Loc.ScriptLocalization.UI.NotEnoughResources_campaignBattleTokens_Description`, et **retour
   sans lancer**.

`IdunMetaLogic.UserProgress.CampaignProgression` n'expose que **deux** methodes de ce profil :
`IsLocationReached(locationIndex)` et `HasStaminaToPlayCampaignBattle(locationIndex)`. Le message
du second test les **desambigue** : `0x23` = stamina/tokens, donc `0x21` = noeud atteint.
⚠ L'appariement slot -> nom reste une **inference contextuelle**, pas une lecture de table : la
table `metadata/interface_slots.tsv` ne porte pas cette interface. A fermer.

Puis, seulement si les deux passent : `idun.ui.Screen$$Hide` sur le popup, construction du
`Nullable<bool>`, et appel du slot `0x126` de `IViewCommandExecutor` = `StartCampaignMatch`.

**Le jeu lui-meme court-circuite deja ces deux tests.** `ShowCampaignBattlePreviewPopupCommand$$LoadCampaignMatch`
— l'autre chemin, celui du retour de raid — appelle le **meme slot `0x126`** avec les memes
arguments et **n'evalue AUCUNE precondition**. Un invoke direct n'est donc pas un regime que le
binaire ignore : c'est le regime de `LoadCampaignMatch`.

**Ce que `StartCampaignMatch` garde elle-meme** (donc conserve par un invoke) :

- `this + 0x3E8` non nul (les `campaignProgressions`), sinon `NullReferenceException` ;
- `enemyIsAiControlled` VIDE ⇒ le champ passe au ctor vaut **`1`** — l'absence de valeur ne vaut
  donc **pas** `false` ;
- et surtout `StartMatch(source, checkIfAlreadyRunning: true)`, dont le **premier** geste est
  precisement « une bataille tourne-t-elle deja ? » : si oui, `IIdunLoggerExtensions$$LogError` et
  **retour sans lancer**. C'est le garde-fou « deja en cours », et il est **dans le natif appele**,
  pas dans l'UI.

## 4. Portee — les 21 autres `Start*Match`

`ViewCommandExecutor$$StartMatch` a **14 appelants CALL** dans le binaire (`StartCampaignMatch`,
`StartCampaignEventMatch`, `StartFriendlyMatch`, `StartGuildBossMatch`, `StartGuildWarsMatch`,
`StartLegendaryEventMatch`, `StartLinearHeroEventMatch`, `StartMachinesOfWarEventMatch`,
`StartOnslaughtMatch`, `StartPvpMatch`, `StartPvpStarterSeasonMatch`, `StartSurvivalMatch`,
`StartSyncPvpEventMatch`, `StartTreasureBeachMatch`). Le patron `Object::New` + ctor inline +
`StartMatch` est donc **commun**, et la reponse a la question 1 (joignabilite du `this`) vaut
**identiquement** pour tous : c'est le meme `this`. Seules changent les preconditions de leurs
appelants UI respectifs, qui sont **par mode**.

## 5. Ce qui manque pour trancher

1. **Armer le capteur** (`startCampaignMatchCaptureArm`) puis jouer une amorce nominal, et lire
   `startCampaignMatchCaptures` : `this`, `campaignId`, `locationIndex`, membre nomme de
   `CampaignType`, et les **deux octets bruts** du `Nullable<bool>`. **Exige une fenetre de
   reinject** (le module est neuf).
2. **`viewCommandExecutorReach`** : confronter le pointeur lu via `_viewCommandExecutor` a celui
   que la capture a vu passer. Egalite ⇒ le chemin de champs est confirme **par confrontation**,
   pas par lecture de decompile.
3. **Entrer ET pouvoir sortir.** `IdunMainView$$StartMatch` lit son `IGameModeSource` dans son
   propre champ `+0xd0` et appelle le slot `0x11` de `IGameModeSource`. Reste a etablir par quel
   chemin ce champ est renseigne — s'il vient du meme slot statique que
   `ViewCommandExecutor$$StartMatch` ecrit (`**(<statique> + 0xb8) = <wrapper>`, `wrapper+0x20 =
   gameModeSource`), alors une bataille lancee par invoke est enregistree **exactement comme**
   une bataille lancee par l'UI, et la retraite reste entiere. **Non etabli.**
4. **Fermer l'appariement slot -> nom** des deux preconditions (§3).

## 6. Ce qui reste ouvert et n'a pas ete explore

- `StartSandboxMatch(sandboxConfig: ISandboxBattleConfig)` — un mode SANDBOX existe, et
  `IdunSandboxSceneMain$$<Start>b__4_0` construit son PROPRE `ViewCommandExecutor`. Piste non
  instruite.
- `ShowHeadlessBattleRunnerPopup(endlessBattlesConfiguration: IEndlessBattleConfig)` — le jeu
  embarque un runner de bataille **headless**. Signale, non explore.

⛔ La famille `Cheat_*` est hors-jeu : elle mute le compte du joueur. Si une precondition
critique bloquait, le verdict serait NON REMPLACABLE — jamais un cheat.
