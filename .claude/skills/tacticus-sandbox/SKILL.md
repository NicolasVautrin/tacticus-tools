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

## Buffs & debuffs — le banc a un RÉGLAGE FIXE, il ne se redemande pas

**Dès qu'une sandbox sert à répéter une mécanique, on pose le même réglage :** ennemis à
**−100 % de dégâts**, ma lineup à **+1000 % de dégâts + trait `Immune`**. C'est une constante
du projet, pas un choix à refaire à chaque montage.

```powershell
python scripts/python/env_ability_patch.py --etat
python scripts/python/env_ability_patch.py --poser --config-ability "EnhancementDamageBoost=extraDmgPct:-100" `
    --enhancement "EnhancementDamageBoost=<ennemis>;stack=1" `
    --enhancement "EnhancementDamageBoost=<ma lineup>;stack=-10" `
    --enhancement "EnhancementAddTrait:Immune=<ma lineup>"
```

**Le signe vient du `stack`, pas de la constante** — et c'est le point qu'on oublie. `extraDmgPct`
est **une seule valeur par bataille** (catalogue keyé par ability), mais `stack` est **par entrée**
et **n'est pas clampé**. Avec `extraDmgPct = -100` posé une fois :

| entrée | `stack` | pct effectif | facteur |
|---|---|---|---|
| ennemis | `1` | −100 | **×0** |
| ma lineup | `-1` | +100 | ×2 |
| ma lineup | `-10` | **+1000** | **×11** |

⚠ **`EnhancementsEnvironmentAbilities` est la SEULE liste qui cible des unités NOMMÉES.** L'autre
(`EnvironmentAbilities`) a son ciblage écrit dans le `CreateTrigger` de l'ability — aucun argument
d'équipe à passer.

⚠ **Un `%` de dégât ne couvre QUE `AttackWithAttackDamage`.** Toute la famille
`AttackWithAbilityDamage` — détonations (Spore Mines), DoT de tuile, novas de mort — **échappe au
debuff en le PORTANT**. Mesuré : des mines à −100 % ont explosé à pleine puissance. Vérifier la
VOIE de dégât avant de promettre qu'un pourcentage la neutralise.

⚠ **Le nom d'un trait ne dit pas sa sémantique** : `Harmless` et `Immovable` se posent et ne
changent rien. `Immune` est à éprouver, pas à supposer.

Détail : `docs/rl/case-10046-debuff-d-environnement.md`.

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

## Les 19 relais d'écriture — ce que chacun fait

Un montage sandbox arme **19 relais qui ÉCRIVENT dans le jeu**, plus 4 observateurs qu'on
laisse. La liste vit dans `scripts/python/relais_sandbox.py` (`ECRIVENT`), source unique —
le hook `sandbox-fenetre.ts` ne la duplique pas, le pilote la lui PASSE à l'armement.

**Le roster et les bornes de l'écran de déploiement** — sans eux la sandbox montre un écran vide :

| relais | ce qu'il fait |
|---|---|
| `deploymentPoolArmer` | **délègue** les méthodes de source à une VRAIE source (campagne, mowEvent…). Sans lui `GetUnitModel` rend un `HotseatUnitModel` qui échoue à `IsUnlocked`, `GetUnitsForDeploymentHUD` une liste VIDE |
| `deploymentPlafondArmer` | observe et sur demande IMPOSE le min/max d'unités. Agit sur le relais `VisualBattleQuery`, jamais sur `SandboxGameModeSource$$AmountOfUnlockedUnits` qui résout sur un `return 0;` |
| `deploymentPoolSansFiltre` | lève le filtre de nœud sur le roster emprunté (`Nullable<Int32>`). Observation par défaut : masquer un pointeur au lieu d'une valeur le corromprait |

**La pose des unités** :

| relais | ce qu'il fait |
|---|---|
| `deploymentPhaseArmer` | la phase de déploiement — observe, ou FORCE le retour de `Enable` |
| `deploymentBoutonArmer` | **la voie de pose des héros**. Armé, la pose passe par `StateMachineActions$$UnitDeployment_PlaceUnitOnBoard` — celle du clic humain — donc les héros deviennent des PLACEHOLDERS comptés par le HUD, au lieu d'unités réelles qu'il ne voit pas (START à 0/5) |
| `deploymentMemoire` | retient chaque pose et la **rejoue** au `Show` suivant, pour qu'un retry reparte avec l'équipe composée. Ne rejoue que si le camp du joueur est VIDE |
| `deploymentSyncArmer` | déclare au HUD les unités déjà présentes sur une BC pré-remplie, et rafraîchit le bouton — rend START vivant sans geste manuel |
| `deploymentClearArmer` | le bouton CLEAR : armé, il ôte AUSSI les unités réelles |
| `deploymentDeposeArmer` | son pendant unité par unité (ôter du plateau ôte du runner) |
| `deploymentCheminsArmer` | le robinet des neuf ancrages de bascule (`EmptySpawnPointTapped`, `PutUnitIntoHand`, `RemoveUnit`…). Existe parce qu'une observation pure n'était pas ÔTABLE, et qu'on INVOQUE certains de ces chemins |

**Les capteurs de diagnostic du START** — ils n'écrivent rien mais sont dans la liste :

| relais | ce qu'il fait |
|---|---|
| `deploymentPrefabArmer` | capture le patron sur `UnitIdToPrefabDictionary$$Add`. À armer AVANT le montage : c'est `StartBattle` qui fait tirer `Add` |
| `deploymentStartArmer` | capteur pur sur `UnitDeploymentState$$StartBattle` |
| `deploymentRunnerStartArmer` | capteur pur sur `IdunRunner$$StartMatch` |
| `deploymentDraftArmer` | régime transparent |
| `deploymentJetArmer` | s'ancre sur le **lanceur de jet** IL2CPP lui-même (`NullReferenceException`), pas sur le symptôme |
| `deploymentVidangeArmer` | s'ancre sur `Dictionary.Clear` — c'est la réponse à « l'erreur arrive trop tard » : quand le « system error » du START tombe, la cause a déjà eu lieu |

**Les trois de `sandbox-mode`, et ce sont les DANGEREUX pour une bataille réelle** :

| relais | ce qu'il fait |
|---|---|
| `sandboxModeBcOverride` | **SUBSTITUE la BC** que `LoadBattle` rend. Laissé armé, il détourne la première bataille RÉELLE venue |
| `sandboxModeSeed` | impose le seed de la prochaine bataille (`unCoup: true` par défaut) |
| `sandboxModeGameViews` | injecte `_gameViews` sur la source ; son journal dit ce qui a ÉTÉ ÉCRIT |

⛔ **Leur désarmement se LIT, il ne se déduit pas.** `desarmer_relais.py` désarme **sans
condition** et imprime `desarme` pour chaque entrée, qu'elle ait été armée ou non : sa sortie
ne prouve donc RIEN sur l'état d'avant. Le seul contrôle qui tranche est la lecture
(`sandboxModeBcOverride {}`, `deploymentMemoire {}` → `arme`). Payé le 2026-08-28 : un
« 19 relais armés, ta BC réelle serait détournée » annoncé sans mesure, alors que la fenêtre
s'était déjà fermée sur la retraite du joueur et que tout était éteint.

⚠ **Et le désarmement automatique ne couvre que les fenêtres qui MEURENT.** Les quatre
déclencheurs de `sandbox-fenetre.ts` sont des fins de bataille (`stage -> Finished`, runner
mort, `_runner -> null`, `HandleBattleSurrender`). Monter puis partir **sans jamais jouer**
ne déclenche rien : les relais restent armés, en silence.

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
