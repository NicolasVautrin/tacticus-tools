# #10022-r1 — `configurationRandomizeAiInput` : l'etage `UnitPicker` EST ACTIF

Build `t6dpr4k06g`. **Verdict : `RandomizeAiInput = false` partout ou une bataille se joue —
l'etage `UnitPicker` MORD.** La chaine est fermee de bout en bout au decompile, et le seul
`true` du binaire vit dans le harnais `AutomatedTesting`.

Effet de bord de la mesure : **le capteur `randomizeAiInput` de `frida/hooks/features/battle-config.ts`
lisait le MAUVAIS OCTET** (`+0xE7` = `DisableRandomness`). Corrige ici ; residu **#10022-r6** pour
la fenetre de reinject.

---

## 1. La chaine, maillon par maillon (chaque maillon LU)

```
BaseBattleConfig..ctor(..., randomizeAiInput, ...)      -> BaseBattleConfig.<+0x24>
CreateBattleConfig(gameMode, baseBattleConfig)          -> BattleConfiguration.<+0xe8>
IdunRunner$$Initialize(configuration, ...)              -> lit configuration.<+0xe8>
AiControl$$Init(..., configurationRandomizeAiInput, ...) -> AiControl.<+0x70>
AiControl$$GetAi(playerEntityId)                        -> DefaultPlayerStrategy | WithSomeRandomnessStrategy
```

**Maillon 1** — `Idun.Source.IdunBattle.View.BattleConfigBuilder.BaseBattleConfig$$.ctor` ecrit
`*(byte*)(this + 0x24) = randomizeAiInput` (signature LUE dans `frida/methods.tsv` :
`(id, boardId, spawnPointsSet, players, randomizeAiInput, abilitiesToHide, unitsConfig,
environmentAbilities)`).

**Maillon 2** — `Idun.Source.IdunBattle.View.BattleConfigBuilder$$CreateBattleConfig`, derniere
instruction avant son `return`, sur la `BattleConfiguration` qu'elle construit :

```c
*(undefined1 *)((longlong)this + 0xe0) = 1;                            // UseGroupForAddUnit = true
*(undefined1 *)((longlong)this + 0xe8) = *(undefined1 *)(param_3 + 0x24);   // <- LA COPIE
return this;
```

Copie **directe et inconditionnelle**. Aucun autre site n'ecrit `+0xe8`.

**Maillon 3** — `IdunBattle.Runner.IdunRunner$$Initialize` (l'overload a `IPseudoRNG`) : le seul
appel virtuel sur `this.<+0x68>` (l'`AiControl` qu'elle vient d'allouer par
`IdunBattle.Core.Services.AiControl$$.ctor`) passe **18 valeurs**, ce qui apparie exactement les
17 parametres d'`Init` + le `MethodInfo*`. Aux positions 11 et 12 :

```c
uVar2   = *(undefined1 *)((longlong)configuration + 0xe6);   // -> disableActiveAbilities
logger  = CONCAT71(..., *(undefined1 *)((longlong)configuration + 0xe8));  // -> configurationRandomizeAiInput
```

Les **seuls** offsets de `configuration` lus par cette fonction sont `+0x60`, `+0x68`, `+0x70`,
`+0x90`, `+0xa8`, `+0xb8`, `+0xe6`, `+0xe8` — donc pas d'ambiguite sur quel octet part vers l'IA.

**Maillon 4** — `IdunBattle.Core.Services.AiControl$$Init` termine par
`*(undefined1 *)((longlong)this + 0x70) = configurationRandomizeAiInput._0_1_;`.

**Maillon 5** — `IdunBattle.Core.Services.AiControl$$GetAi`, LU verbatim :

| `PlayerComponent.<+0x20>` | `AiControl.<+0x70>` | strategie rendue |
|---|---|---|
| `2` | — | `this+0x30` (`IdunBattle.AI.EnvironmentPlayerStrategy`) |
| `4` | `0` / non-`0` | `this+0x28` / `this+0x68` (humanAi : Default / WithSomeRandomness) |
| autre | `0` / non-`0` | `this+0x20` / `this+0x60` (Default / WithSomeRandomness) |

⇒ `+0x70 == 0` **est** la condition d'activation de `DefaultGroupOperator`, donc des 8 buckets.

---

## 2. Le champ `+0xe8` EST `RandomizeAiInput` — cinq ancres, aucune deduction

Le doute etait reel : `BattleConfiguration` porte **neuf booleens consecutifs** a partir de `+0xe0`,
et notre propre base de code en donnait **deux valeurs contradictoires** (`+0xE7` dans
`battle-config.ts`, `+0xe7` = `DisableRandomness` dans `sandbox-mode.ts`). Table etablie :

| offset | champ | ANCRE (symbole natif qui la fixe) |
|---|---|---|
| `+0xe0` | `UseGroupForAddUnit` | `IdunBattle.Core.Services.BattleQuery$$get_UseGroupForAddUnit` — `return *(byte*)(this.<+0xa0> + 0xe0)` |
| `+0xe1` | `NoAutomaticUnitTurns` | `IdunBattle.Core.Services.BattleQuery$$get_NoAutomaticUnitTurns` — `+0xe1` |
| `+0xe2` | `EnableIdunAbilities` | (position) |
| `+0xe3` | `IsTestBattle` | (position) |
| `+0xe4` | `DisableTimeouts` | (position) |
| `+0xe5` | `DisableAnimatorRecovery` | (position) |
| `+0xe6` | `DisableActiveAbilitiesOnAI` | `IdunRunner$$Initialize` -> parametre **nomme** `disableActiveAbilities` d'`AiControl$$Init` ; et `BattleConfigBuilder$$GetHotseatConfig` y ecrit le slot 0 d'`ISandboxBattleConfig` |
| `+0xe7` | `DisableRandomness` | `idun.IdunMainView$$ShowBattle` : `if (*(char *)(bc + 0xe7) == '\0') seed = DateTime.Now.Ticks` — le gate du seed horloge |
| `+0xe8` | **`RandomizeAiInput`** | `IdunRunner$$Initialize` -> parametre **nomme** `configurationRandomizeAiInput` ; et `CreateBattleConfig` y copie `BaseBattleConfig.randomizeAiInput` |

Les cinq ancres sont **nommees** (getter natif, ou nom de parametre lu dans `frida/methods.tsv`) et
**mutuellement compatibles avec l'ordre de serialisation Newtonsoft** de `data/seed-bc.json`, qui
liste ces neuf booleens dans cet ordre exact (`UseGroupForAddUnit` ... `RandomizeAiInput`).
Deux d'entre elles se recoupent sans partager de source : `+0xe0 = UseGroupForAddUnit` est fixe par
son getter **et** par `CreateBattleConfig` qui y ecrit `1`, ce que le JSON confirme (`True`).

---

## 3. Ce que chaque mode PASSE — huit call-sites lus, un seul `true`

`randomizeAiInput` n'est **pas** une constante du binaire : c'est un **parametre** de treize
`BattleConfigBuilder$$Get<X>Config`. Il faut donc lire les APPELANTS.

| appelant (symbole) | mode | valeur passee |
|---|---|---|
| `IdunBattle.ViewLogic.BattleSource.CampaignGameModeSource$$LoadBattle` | Campagne | **`0`** |
| `IdunBattle.ViewLogic.BattleSource.PvpGameModeSource$$LoadBattleInternal` | Arene | **`0`** |
| `IdunBattle.ViewLogic.BattleSource.PvpStarterSeasonGameModeSource$$LoadBattleInternal` | Arene starter | **`0`** |
| `IdunBattle.ViewLogic.BattleSource.FriendlyGameModeSource$$LoadBattle` | Amical | **`0`** |
| `IdunBattle.ViewLogic.BattleSource.GuildWarsGameModeSource$$LoadBattleInternal` | Guild Wars | **`0`** |
| `BattleConfigBuilder$$GetHotSeatGameModeSpecificConfig` -> `GetTreasureBeachConfig` | sandbox | **`0`** (`& 0xffffffffffffff00`) |
| `BattleConfigBuilder$$GetHotSeatGameModeSpecificConfig` -> `GetOnslaughtConfig` | sandbox | **`0`** |
| `BattleConfigBuilder$$GetHotSeatGameModeSpecificConfig` -> `GetGuildBossBattleConfig` | sandbox | **`0`** (`& 0xffffffffffffff00`) |
| `Idun.Source.AutomatedTesting.Factories.AutomaticTestingPvpConfigFactory$$Build` | **harnais de test Idun** | **`1`** |

Le `true` existe donc, et il est **localise** : le harnais `AutomatedTesting`. Ce meme call-site
passe aussi `mainPlayerType = 4` — le `PlayerType` qui bascule `GetAi` sur la branche humanAi.
C'est coherent : ce factory monte des batailles bot-contre-bot et veut de la variete.

⚠ **NON COUVERT** : les autres `Get<X>Config` porteurs du parametre dont je n'ai pas lu l'appelant
(`GetCampaignEventConfig`, `GetMachinesOfWarEventConfig`, `GetSurvivalConfig`,
`GetLegendaryEventConfig`, `GetLinearHeroEventConfig`, `GetTerritoriesConfig`, `GetBoostsConfig`,
et les six `GetHotseat*Config` a un argument). Aucun de ces modes n'est le regime confrontable ;
la mesure ci-dessous, elle, l'est.

---

## 4. Le REGIME CONFRONTABLE — le runner — a l'etage ACTIF, et ca se mesure sans decompile

Le runner (`rl_duel build`) ne passe **pas** par `BattleConfigBuilder` : sa `BattleConfiguration`
est **deserialisee** depuis `data/seed-bc.json`. La valeur effective y est donc lisible **par NOM**,
sans dependre d'aucun offset :

```
data/seed-bc.json : "RandomizeAiInput": false
```

Et `buildNormalizedBC` ne la touche pas : aucun fichier de `frida/hooks/**` n'ecrit cette cle
(le seul ecrivain du depot est `scripts/python/_wave_build.py`, un wrapper de vague RL qui la force
a `True` **explicitement**, en disant que `build` n'a pas de drapeau pour ca).

⇒ **Sur tout runner monte par la voie standard, `AiControl.<+0x70> == 0` et `GetAi` rend
`DefaultPlayerStrategy`.** Le chantier `#10022-r2..r5` a un objet.

⚠ Corollaire pour qui voudra la contre-epreuve : `_wave_build.py` est le levier existant pour
monter un runner a `RandomizeAiInput = True` (bascule vers `RandomGroupOperation`, tirage
uniforme). Ne PAS s'en servir pour valider un port du picker — ce serait valider l'etage dans le
regime ou il est justement debranche.

---

## 5. Le capteur `battle-config.ts` lisait `DisableRandomness` sous le nom `randomizeAiInput`

`BC_OFF_RANDOMIZE_AI = 0xE7`. D'apres §2, `+0xE7` est `DisableRandomness`. Deux consequences,
toutes deux **silencieuses** :

- **en lecture** (`bcInspect`) : le champ `randomizeAiInput` du snapshot rapporte
  `DisableRandomness`. Sur le seed BC les deux valent `false`, donc l'erreur ne se voit pas —
  c'est un **accord en regime degenere**, exactement la forme qui fait passer un capteur faux
  pour bon ;
- **en ecriture** (`bcPatch({ randomizeAi: true })`) : on ecrit `DisableRandomness = true`, donc
  on **fige le seed** de la bataille (cf. `idun.IdunMainView$$ShowBattle`) au lieu de randomiser
  l'ordre d'activation IA. Un effet non seulement absent mais **different**, sur une BC vivante.

Corrige a `0xE8` dans le meme commit, avec la table des neuf booleens en commentaire de tete pour
que l'octet suivant ne soit plus a portee de faute. Meme correction dans
`.claude/skills/tacticus/SKILL.md`, qui propageait le meme `+0xE7`.

⚠ **La correction n'est PAS active tant que le bundle n'est pas reinjecte** — residu **#10022-r6**.
Le verdict de cette fiche, lui, n'en depend pas : il est etabli au decompile et sur le JSON du
seed, deux sources qui ne passent par aucun offset code en dur.

---

## 6. Cliquet

`scripts/python/probe_10022r1_randomize_ai_input.py` — offline, `rc 0/1/2` (jamais un vert sur
non-mesure). Il garde les quatre choses que cette tranche a etablies :

1. l'offset ecrit dans `battle-config.ts` vaut `0xE8`, et **pas** `0xE7` (assertion **negative
   explicite** : c'est la valeur fautive qui est nommee, pas seulement la bonne qui est exigee) ;
2. la table des neuf booleens est presente et complete dans le commentaire de tete du meme
   fichier, dans le bon ordre ;
3. `data/seed-bc.json` porte `RandomizeAiInput == false` — si un jour le seed change, le verdict
   « l'etage est actif » doit etre re-examine, pas herite ;
4. aucun autre fichier de `frida/hooks/**` n'ecrit la cle `RandomizeAiInput` (l'ecrivain legitime
   `scripts/python/_wave_build.py` est hors de ce perimetre et reste autorise).

---

## 7. Ce qui n'est PAS couvert

- Les sept `Get<X>Config` dont l'appelant n'a pas ete lu (§3) — aucun n'est confrontable.
- **Aucune lecture live du champ `AiControl.<+0x70>`** n'a ete jouee. Le probe qui saurait la faire
  existe deja (`frida/hooks/game/ai-control.ts::dumpAiRngProbe`, qui lit `aiCtrl.add(0x70)` — le
  BON offset) mais il est **one-shot par session** et tire depuis `recorder.ts` sur l'`AiControl`
  **live**, pas sur celui d'un runner. Le rendre interrogeable par RPC exigerait une fenetre de
  reinject : c'est le second volet de **#10022-r6**.
- `IdunBattle.AI.EnvironmentPlayerStrategy` (joueur `2`) reste hors perimetre, comme dans
  l'inventaire.
