---
name: tacticus-sandbox
description: Monter une bataille de Tacticus en SANDBOX — boss de guilde, guerre de guilde, onslaught — sans consommer de tentative ni toucher au compte. MUST BE USED dès que l'utilisateur demande de lancer / relancer une sandbox, ou de monter un boss / une zone / une vague pour l'observer. Encapsule un ORDRE de gestes non intuitif : TOUT s'arme AVANT le montage, sinon la phase de déploiement n'existe pas.
---

# Sandbox — monter une bataille sans la jouer pour de vrai

## Boss de guilde — une commande

```powershell
python scripts/python/sandbox_boss.py              # LECTURE : boss courant, PV, roster, etat
python scripts/python/sandbox_boss.py --confirmer  # MONTE, phase de deploiement comprise
```

Jouer la forme **sans `--confirmer` d'abord** : elle dit quel boss est en cours et ce que le
mode autorise, sans rien armer. Le lanceur découvre la session Frida vivante tout seul.

Ce qui sort, et qui change à chaque saison — **le lire, jamais le citer** :

    BOSS     GuildBoss10Boss1AdmecBelisarius:22   board=GB_Belisarius_03   sps=0
    PV       13538457 / 15000000                  rounds=6
    ROSTER   102 deployables   disallowedFactions=['AdeptusMechanicus']

## Les autres modes

| mode | voie | note |
|---|---|---|
| **onslaught / vagues** | `python scripts/python/sandbox_mode.py start --mode waves --session <SID> --onslaught-tier 5 --confirmer` | la seule voie qui se passe d'override |
| **guerre de guilde** | recette dans `docs/rl/case-10038-guild-war-en-sandbox.md` §3 | même patron que le boss, prêteur `guildWar` |
| **BC déjà capturée** | `sandboxModeBcOverride {configJson}` puis un `start` quelconque | le mode importe peu, ce qui compte est la SOURCE |

## Les quatre pièges

1. **TOUT S'ARME AVANT LE MONTAGE.** Une douzaine de RPC (`deployment*Armer`,
   `sandboxModeGameViews`) doivent être posés avant `StartMatch`. Armer après, c'est une
   bataille sans phase de déploiement — et rien ne le signale. `sandbox_boss.py` porte cet
   ordre ; ne le rejoue pas à la main.

2. **LE CATALOGUE NE SE CHOISIT PAS, IL SE LIT.** Construire une `Sandbox<Mode>BattleConfig`
   avec des arguments *choisis* produit une BC dont `BC.Units` ne contient QUE ce qu'on a
   passé — alors que le HUD offre les ~100 unités déployables du mode. Poser une des autres
   crée une entité dont la définition manque. D'où l'override : `guildBossSourceBc` fait
   produire à la source du mode SON catalogue, ses modificateurs et ses environment abilities.

3. **AUCUNE TENTATIVE CONSOMMÉE — et c'est le décompilé qui l'établit, pas le nom des
   méthodes.** On monte par `SandboxGameModeSource` (surface SANS aucun `Send*GameEvent`) et
   on invoque `GuildBossGameModeSource$$LoadBattleInternal`, qui CONSTRUIT la BC et la rend ;
   `SendLoadBattleGameEventInternal` est une méthode SÉPARÉE, jamais appelée. Passer par
   `LoadBattle` coûterait une tentative AU CHARGEMENT.
   ⚠ Corollaire : `StartMatch` **écrase** le match courant, donc écraser un match enregistré
   et non terminé PERD la tentative. `checkIfAlreadyRunning` reste à `true` (le désarmer a
   déjà coûté 2 jetons), et le lanceur REFUSE si `sandboxProbe.instance` n'est pas nul.

4. **SORTIR** : `retreatInvoke OnBattleSurrender`, UN appel, vérifié par
   `sandboxProbe.instance == null`. La retraite ne marche que sur `SandboxGameModeSource`
   (elle porte les six `Handle*`) — `TestSceneBattleModeSource` n'a pas
   `HandleBattleSurrender`, et on ne pourrait plus sortir sans relancer le jeu.

## Retoucher le déploiement — sans jamais passer par le CLEAR

Le clear est un geste **total** : il vide le camp et fait tout re-saisir. Trois verbes le
rendent inutile, tous sur le runner vivant, sans remontage ni jeton :

| geste | RPC |
|---|---|
| échanger une unité | `deploymentRemplacer {sortante \| entityId, entrante:{unitId}, confirmer:true}` |
| ôter | `deploymentRetirer {entityIds, confirmer:true}` |

⚠ **`deploymentCommit` N'EXISTE PLUS** (supprimé le 2026-08-21, avec `deploymentPoseFsmArmer` et
`deploymentPoseCommitArmer`) : il appliquait les `AddUnitMessage` de tout un plateau au runner
vivant. Les poses passent **TOUJOURS** par l'étage FSM, donc par un `PlaceholderUnitView` que le
START natif convertit avec les autres. Cette ligne est restée dans ce tableau jusqu'au 2026-08-25 —
l'appeler rend **500**, ce qui se lit comme une panne de harnais au lieu d'une ligne périmée.

`playerId`/`col`/`row` sont **hérités de la sortante**. Rien n'est synchronisé avec la mémoire
de déploiement, et c'est voulu : la composition retenue pour le retry est prise **en une fois
au START**, sur le plateau réel — donc on échange autant qu'on veut, dans n'importe quel ordre.

⚠ **La remplaçante doit être dans la BC montée** : sinon `Apply` passe **sans erreur** et rien
n'apparaît. Le verdict se lit à `deploymentPoseDiag` / `deploymentPlateau`, jamais au retour
du RPC — lui ne dit que « la pose est enfilée ».

⚠ **ÔTER UNE UNITÉ À L'ÉCRAN NE L'ÔTE PAS DU PLATEAU, sauf si `deploymentDeposeArmer` est
armé** (le lanceur le fait). Le HUD ne connaît que des `PlaceholderUnitView` ; nos unités sont
RÉELLES sur le runner. Sans relais, la dépose rend l'unité au roster et **la laisse en jeu**.
`deploymentClearArmer` ne couvre que le bouton *tout enlever*.

⚠ **Et le chemin n'est PAS celui que son nom désigne.** Mesuré le 2026-08-19 :
`UnitDeploymentHud$$RemoveUnit(unitConfigId)` ne tire **jamais** (0 tir sur un cycle complet,
ancrage contrôlé). C'est `PutUnitIntoHand(unitId)` qui porte le geste — et **les deux** : 2 tirs
pour 1 pose, même argument. L'argument ne discrimine donc pas ; c'est la **présence sur le
plateau** qui sépare la dépose de la saisie.

## Le replay

Armé **par défaut** par le lanceur (`--sans-replay` l'écarte). Un runner monté en sandbox porte
bien un `ReplayRecorder` armé — mesuré le 2026-08-19, `recorderArmed: true` en pleine bataille.

⚠ **Le replay ne se SONDE pas, il se PREND À LA FRAME.** Le runner disparaît à la fin de la
bataille : un sondage externe arrive toujours trop tard et rend `runner has no ReplayRecorder` —
un message qui accuse le mécanisme alors que seul le TIMING est en cause. Un replay entier a
déjà été perdu ainsi. `replayFinAuto` capture dans la pompe, à la transition, donc sans course.
Deux déclencheurs : `stage -> Finished`, et `_runner -> null` (retraite, changement de scène).

Relire : `replayFinEtat {avecReplay: true}`.

## Quand ça REFUSE

Le lanceur nomme toujours la cause. Les trois qu'on rencontre :

| ce qui s'affiche | ce que ça veut dire |
|---|---|
| `progression cablee=True donnees=False` | pas de guilde, pas de saison active, ou pas encore synchronisé. **Pas** un bug de harnais. |
| `une bataille tourne DEJA` | sortir d'abord (piège 4), puis relancer |
| `aucune source <X> (preteur <n>)` | le `*SourceForger` du mode n'a pas été appelé — le lanceur le fait, donc c'est un vrai défaut à lire |

⚠ **Une garde qui accuse une dépendance dont le chemin ne se sert pas fait réparer la mauvaise
cause.** Mesuré le 2026-08-19 : `deploymentPoolArmer` testait la `CampaignGameModeSource`
*quel que soit* le prêteur, reste de l'époque où la campagne était le seul. Un montage guild
boss entièrement gréé était refusé au motif « rejouer l'amorce » — et l'amorce a été rejouée,
en pure perte, alors qu'`armerUneDelegation` résout sur `sourcePreteuse()` et n'aurait pas lu
la campagne une seule fois. La garde porte désormais sur le prêteur retenu.

## Ne pas faire

- **Ne jamais lancer Tacticus** ni le relancer : geste UTILISATEUR.
- **Ne pas (ré)injecter si tu es un agent.** Un correctif `frida/hooks/*` se LIVRE et se DIT
  au rapport ; la fenêtre appartient à l'orchestrateur.
- **Ne pas ancrer ce qu'on invoque.** `sandboxModeBuildBc` appelle `LoadBattle` lui-même :
  avec l'override armé, ça a déjà coûté un gel. Le RPC le refuse, ne le contourne pas.

## Aller plus loin

- `scripts/python/sandbox_boss.py` — le lanceur, ordre des gestes en tête de fichier.
- `scripts/python/sandbox_mode.py` — la fabrique par mode ; vérifie la signature du ctor
  contre le build vivant avant tout envoi, et REFUSE sur désaccord.
- `frida/hooks/features/sandbox-mode.ts` — pourquoi `SandboxGameModeSource` et pas
  `TestSceneBattleModeSource` (les six `Handle*`).
- `frida/hooks/features/guild-boss-config.ts` — la lecture de la progression guild boss.
- `docs/rl/case-10038-guild-war-en-sandbox.md` — la recette guerre de guilde, et les deux
  méthodes de diagnostic qui l'ont débloquée.
