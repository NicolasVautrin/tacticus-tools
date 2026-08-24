# #10045 — Où le jeu pose la lineup : une règle DÉRIVÉE, pas un stockage

**Règle** : la i-ème unité de la lineup va sur la i-ème case de spawn du groupe du joueur,
**dans l'ordre auteur de la `BattleConfiguration`**.

```
GetBattleLineup(lineupIndex) -> System.String[]        # QUI, dans un ORDRE
BC.Board.SpawnPointSets[i].SpawnPointGroups[g].SpawnPoints   # OU, dans un ORDRE
        zip                                             #  -> le placement
```

## Ce que ça corrige

J'avais écrit l'inverse, dans le code, le 2026-08-24 : « **les positions sont arbitraires** »
et « le jeu sauvegarde l'équipe, pas le placement ». Les deux constats qui y menaient étaient
**justes** — tout le contrat de source est `String[]`/`String`, et
`IdunMetaLogic.UserProgress.Data.UnitProgressionData$$SetLineup(key, unitIds)` ne stocke que
des identifiants — mais la conclusion était **fausse**. Une coordonnée absente d'un stockage
peut être **dérivée d'un ordre**. Corrigé sur signalement de l'utilisateur : « le jeu arrive
très bien à retrouver le placement ».

⇒ **Une absence dans une famille de symboles ne prouve rien.** Le balayage disait où la
coordonnée n'est pas ; il ne pouvait pas dire qu'elle n'existe pas.

## La mesure

`scripts/python/probe_10045_regle_de_placement.py` — corpus **dérivé de `git ls-files`**, donc
identique dans un worktree frais (`data/replays/_captures/` n'est pas versionné et sort du
compte en le disant).

| étage | nature | résultat au 2026-08-24 |
|---|---|---|
| 1 | **invariant, bloquant** — les cases jouées sont les N premières cases auteur, à l'ordre près | **63 / 63** |
| 2 | **inventaire, jamais bloquant** — l'ORDRE suit-il la règle | campagne 46/50 · boss 3/4 · **guerre de guilde 0/9** |

Re-dériver ces chiffres, ne pas les citer.

L'ordre est un inventaire et **pas** une assertion : un seuil sur sa proportion se périmerait
à chaque capture ajoutée, alors que trois régimes s'en écartent légitimement.

## Les trois régimes d'écart

1. **Restrictions de bataille** — la lineup traverse un `HashSet<System.String>`
   (`IdunBattle.ViewLogic.BattleSource.LineupHelper$$GetCampaignBattleLineupUsingRequiredUnits`,
   paramètre `savedLineup`). Un `HashSet` n'a pas d'ordre : le zip n'a plus de sens. C'est le
   candidat pour les 4 écarts de campagne, tous des `elite*`/`eliteMirror*`.
2. **Guerre de guilde** — 0/9, systématique : sa lineup ne vient pas de ce tableau.
3. **Réarrangement manuel** — et c'est celui qui a coûté.

## Le contre-exemple qui avait fait douter

Le combat de boss du 2026-08-24 (16:45 UTC, `GuildBoss3Boss1NecroSilentKing`, seed 29710292)
sort en écart : cases auteur `[(0,1),(1,1),(3,1),(5,1),(6,1)]`, poses `(3,1),(5,1),(6,1),(1,1),(0,1)`.
L'utilisateur y avait **déplacé ses unités à la main** pour reproduire un de nos replays — donc
le seul des trois régimes que la règle ne couvre pas. Un placement réarrangé n'est reproductible
d'**aucune** lineup : il faut `--depuis-replay`.

Ce qui l'établit : nos six répétitions (15:42→16:11) et le combat réel donnent le **même**
unité→case (`orksWarboss`→0, `admecDominus`→1, `admecManipulus`→3, `admecMarshall`→5,
`admecRuststalker`→6) avec des **ordres de pose différents**, et la lineup sauvée
(`user_progression.json` → `lineup.gb`) porte l'ordre du **dernier** combat. Le placement ne
peut donc pas être une fonction de cette lineup-là.

## Où lire les faits

- Le jeu écrit lui-même un replay par bataille :
  `%USERPROFILE%\AppData\LocalLow\Snowprint\Warhammer 40,000_ Tacticus\replays\<Mode>-<date>-<hhmm UTC>.replay.txt`,
  en **base64(gzip(json))**. ⚠ Le même répertoire contient aussi des **instantanés d'état** sous
  le même suffixe (`{"_pendingDeaths":…}`) qui ne sont **pas** des replays : essayer les trois
  encodages et sortir en NON MESURÉ, jamais en conforme.
- La lineup sauvée : `user_progression.json`, clés `lineup` / `machineOfWarLineup`
  (`gb`, `gb_<Faction>`, `pvp`, `spvp`, `pp`, `campaign<n>_<m>`…). **Aucune coordonnée.**
- PlayerPrefs (`HKCU:\Software\Snowprint\Warhammer 40,000: Tacticus`) : rien de positionnel —
  `idun.screens.battle.current` ne porte que le nom d'écran.
