# `ViewCommandExecutor` — le canal de LECTURE de l'état joueur hors bataille

**Ce que c'est** : le singleton par lequel toute l'UI du jeu lit la progression du compte.
On l'atteint **en lecture pure, sans aucun scan de heap**, et il donne accès à l'état des
live-events, du Guild War, des Machines of War, des quêtes, des événements héros — c'est-à-dire
à tout ce que `gameconfig.py` ne peut pas dire, parce que ça vit dans la session, pas dans la
config.

Écrit le 2026-08-13 après une exploration live qui n'existait nulle part dans le dépôt.

## Le chemin

```
idun.UI.IdunNavigation._viewCommandExecutor   ->   idun.shared.commands.ViewCommandExecutor
```

`IdunNavigation$$Init` reçoit l'exécuteur et le garde en champ nommé ; le module le résout par
`getFieldOffset`, jamais par une adresse. Aucun `Memory.scan`, aucun `enumerateRanges` — donc
aucun risque de gel / `UnityFreezeDetector`.

Foyer : `frida/hooks/features/view-command.ts`.

## Re-dériver (les chiffres ci-dessous se périment)

```powershell
# la surface : la cible est-elle résolue, où est l'instance
$b = '{"method":"viewSurface","args":[]}'
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/scripts/<SID>/rpc" -Method Post -Body $b -ContentType 'application/json'

# les champs et leurs offsets (args POSITIONNELS : ns, cls)
$b = '{"method":"classFields","args":["idun.shared.commands","ViewCommandExecutor"]}'
```

**Mesuré le 2026-08-13, build `rnca9r7q6c`** : **273 champs**, dont **44** dont le nom *et* le
type finissent par `Progression(s)` (**42** derrière une interface `I*Progression`), sur des
offsets de **928 à 2032** ; **74** champs typés interface au total.

⚠ Une note de session antérieure annonçait « 100 interfaces de progression ». **Faux** — le
compte réel est 44. Re-dériver, ne jamais citer ce paragraphe.

⚠ Ces offsets ne sont **pas** lisibles hors ligne : `data/symbols/<build>/frida/classes.tsv` ne
porte **aucune colonne de champs** (cf. `CLAUDE.md`). Un nom/offset de champ se lit **au runtime**,
point.

## Les modules qui comptent — offsets vérifiés le 2026-08-13

| champ | offset | classe réelle |
|---|---|---|
| `_questProgression` | +936 | `QuestProgression` |
| `_campaignProgressions` | +1000 | `CampaignProgressions` |
| `_guildWarPhaseProgression` | +1040 | `GuildWarPhaseProgression` |
| `_guildWarProgression` | +1048 | `GuildWarProgression` |
| `_heroReleaseEventProgression` | +1184 | `HeroReleaseEventProgression` |
| `_machinesOfWarEventProgression` | +1256 | `MachinesOfWarEventProgression` |
| `_liveEventsProgression` | +1656 | `LiveEventsProgression` |
| `_linearHeroEventProgression` | +1928 | `LinearHeroEventProgression` |
| `_liveEventsSurvivalModuleProgression` | +1992 | `LiveEventsSurvivalModuleProgression` |
| `_honorYourHeroesProgression` | +2032 | `HonorYourHeroesProgression` |

Entrée la plus utile : `LiveEventsProgression$$GetAllCurrentlyActiveLiveEvents()` — **0 argument**,
donc invocable sans rien construire.

## Le contrat RPC (`frida/hooks/features/view-command.ts`)

| RPC | rôle |
|---|---|
| `viewSurface` | quelles cibles sont résolues, et pourquoi une ne l'est pas |
| `viewField` | descend un **chemin pointé** de champ en champ (`{chemin: "_liveEventsProgression"}`) |
| `viewList` | énumère les méthodes d'une cible |
| `viewInvoke` | invoque — **exige `confirmer: true`** |

- `viewField` prend un **objet** `{cible?, surPointeur?, chemin?}`, pas une chaîne positionnelle.
  Il ne suit que des **pointeurs** (`cur.add(off).readPointer()`) : il ne lit pas un primitif.
- `viewInvoke` **décode** le retour et **dit ce qu'il ne sait pas lire** (`decode: false` + note) —
  jeter le retour rendrait « a refusé » et « a marché » indiscernables. Décodés : les 10 types
  valeur primitifs (`Boolean`, `Byte`, `SByte`, `Int16`, `UInt16`, `Int32`, `UInt32`, `Int64`,
  `Single`, `Double`) et `String`. Un `Nullable<T>` ou un type référence ressort en **pointeur**.

## ⛔ Ce qu'on n'invoque JAMAIS

- **La famille `Cheat_*` / `Cheat*`** : elle mute le compte. Le module la **refuse
  inconditionnellement** — aucun `confirmer` ne l'ouvre. (`IdunMainView` porte `CheatFinishBattle`.)
- **Tout ce qui DÉPENSE**, mesuré sur cette surface : `StartLinearHeroEventMatch` (jeton),
  `ClaimNextLinearHeroEventMilestone`, `ShowRefillLinearHeroEventTokensWithGemsConfirmationPopup`
  (gemmes), `ExecuteAdRefillLinearHeroEventToken` (pub), `StartSurvivalMatch` /
  `StartLiveEventSurvivalBattleCommand` (stamina — 5 max, ~12 h de regen), `RaidLocation` /
  `RaidAgainLocation` (tickets de raid).

Règle générale du dépôt qui s'applique ici : **un natif qui ÉCRIT s'OBSERVE d'abord**. Ce canal
est un lecteur ; le jour où on veut en écrire quelque chose, on décompile avant d'invoquer.

## Instantané du 2026-08-13 — DATÉ, à re-mesurer, jamais à citer

- **61 live-events actifs**. Saison courante `season_august_2026_week2_event`.
- **Survival N'EST PAS actif** : le seul événement portant un bloc `survival` est
  `season_may_2026_event`, **absent** des 61.
- MoW : `IsUnlocked = True`, aucune unité choisie. Guild War : saison active mais
  `IsGuildWarActive = False`. Hero Release : ThousandSons, semaine 1/2.
- Linear Hero Event (« Cezare's quest ») : porteur **`bloodTerminator`**, débloqué, score 0.
- **21 `GameModeSource`**, dont `SurvivalEventGameModeSource` — mais **pas** de
  `LinearHeroEventGameModeSource` : la quête de Cezare passe par un
  `ILinearHeroEventEncounterModel`, pas par une source de mode.

⚠ **Un identifiant n'est pas une date.** `season_may_2026_event` porte **39 clés et zéro champ
temporel** : « may 2026 » est une étiquette. Cette confusion a déjà été servie comme une mesure.

⚠ **La fraîcheur du gameconfig est un axe SÉPARÉ de celle du build** : il est livré par le
serveur et peut avoir plusieurs versions d'avance sur un build figé. Vérifier
`python scripts/python/gameconfig.py --which` avant de conclure quoi que ce soit de ces données.

## Pourquoi ce canal a été ouvert

Objectif énoncé par l'utilisateur : **s'entraîner sans dépenser de jetons**. Le coût zéro existe
déjà (`rl_duel build` monte un runner isolé depuis une seed BC, 0 ressource) ; ce qui manque,
c'est le **CONTENU** de ces modes. État de la piste :

- le battleSet survival est **dans le gameconfig** (`battles.battleSets.survival_may_2026` :
  1 bataille, board `survival_13`, 52 npc, vagues aux rounds 1/3/5, `armyAfterCompletion` = `powup*`) ;
- **BLOQUANT MESURÉ : `data/boards` est VIDE** — aucun board survival sur disque ;
- les `powup*` (`powupReinforcement`, `powupHits`, `powupReinforcementShield`,
  `powupSummonSpawn_*`) sont un canal d'attribution qu'**aucun de nos audits ne visite** ;
- **35 npc portent un suffixe `Surv`** (variantes du mode), déjà dans `docs/rl/npc-registry.tsv` ;
- `SandboxGameModeSource$$LoadBattle` appelle `BattleConfigBuilder.GetHotseatConfig(...)` — le jeu
  embarque un **composeur de bataille arbitraire**, 11 types de config (`Waves`, `Survival`, `Pvp`,
  `GuildBoss`, `Infested`, `Draft`, `Boosts`, `CampaignEvent`, `TreasureBeach`, `Territories`), et
  `SandboxContainer` porte `AddUnitToContainer`, `ForceSurvivalPowerUp`, `AddEnvironmentAbilities`.
  **Porte d'entrée native distincte de notre `buildNormalizedBC` — NON ÉVALUÉE.**

## Pièges de méthode, tous vécus

- **`findClassesNamed` rend des HOMONYMES**, et le mauvais sort en premier :
  `idun.tests.TestLiveEventsSurvivalModuleProgression` précède la vraie classe, et `classFields`
  y rend une structure **vide** — qui se lit comme « la classe n'a pas de champs ». Toujours
  vérifier le **namespace**.
- **`classFields` prend ses arguments en POSITIONNEL** (`["<ns>", "<cls>"]`). Passé en objet
  (`{classe: ...}` ou `{ns, cls}`), il rend `ok:false` ou **0 champ sans erreur**.
- **L'enveloppe RPC est `args` (un TABLEAU)**, jamais `params` : un `params` est ignoré en
  silence et l'appel se comporte en lecture seule.
- `HonorYourHeroesProgression$$GetTier` **lève** — la garde du module le rattrape proprement,
  mais ne pas lire l'exception comme « le module est cassé ».
