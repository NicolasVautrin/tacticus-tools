# `data/replays/` — replays de bataille conservés, classés

Entrées qu'on **LIT** (règle `data/` = lecture, `logs/` = écriture). Un replay récupéré ici
ne se régénère pas : s'il vient d'un chat, le message peut disparaître, et la partie n'existe
plus. C'est la seule catégorie de `data/` qu'on ne peut pas re-dériver.

⚠ **Un fichier laissé NON SUIVI sous `data/` n'est protégé par RIEN** — `git clean` et un
`worktree remove --force` l'effacent sans trace. `git add` le fichier DANS LE MÊME geste que
la récupération, jamais « plus tard ».

## À LA RÉCUPÉRATION — trois gestes, dans le même commit

1. **Sauver le BRUT** (`.replay.txt`, base64+gzip), pas seulement le décodé. Le jeu fait
   tourner son répertoire : le brut n'est récupérable que le jour même.
2. **`git add`** immédiatement — cf. ci-dessus.
3. **Renseigner `rank`.** ⚠ **C'est la SEULE colonne qu'on ne peut pas retrouver après coup.**
   `boss`, `map`, `spawn` se re-dérivent du fichier à volonté ; le tier de raid, lui, n'est
   écrit NULLE PART dedans (cf. plus bas). Si on ne le note pas au moment où on récupère le
   replay — moment où on sait encore de quel raid il vient — l'information est perdue, et
   aucune relecture du fichier ne la rendra. Une ligne à `rank` vide est une dette, pas un
   simple champ manquant.

## Format — mesuré, pas supposé

Un `.replay.txt` du jeu est **`base64(gzip(JSON UTF-8))`**. Vérifié le 2026-08-16 sur les
10 fichiers du `persistentDataPath` : 10/10 décodent, ratio 7,3× à 10,6×.

Le JSON décodé porte, en tête :

```json
{"RngSeed":777,"BattleSpeed":2.0,
 "BattleConfiguration":{"Id":"waves","GameMode":"Waves","RuleSet":null,
   "SpawnPointSetIndex":0,"Player":{"Players":{"11":{...},"12":{...},"13":{...}}}}, ...
```

— donc la **`BattleConfiguration` complète** (joueurs, `PlayerType`, drafting, unités) puis le
flux de messages. Un replay est auto-suffisant : il n'a besoin ni du compte ni du serveur.

Le jeu écrit les siens dans
`%USERPROFILE%\AppData\LocalLow\Snowprint\Warhammer 40,000_ Tacticus\replays\`.
⚠ Le préfixe du nom de fichier est le **contexte de sauvegarde**, PAS le mode : nos fichiers
`Sandbox-*.replay.txt` portent tous `GameMode: "Waves"`. Classer sur le nom serait faux —
**classer sur le `GameMode` du JSON décodé**.

## Pourquoi les guild boss valent d'être gardés

`idun.Shared.Battle.GameMode` : `0=Campaign 1=PvP 2=Waves 3=EliteCampaign **4=GuildBoss**
5=TreasureBeach 6=Sandbox 7=Replay …`

`idun.shared.commands.StartUserReplayCommand$$Execute` dispatche par ce mode et **n'accepte
que 0, 3, 4, 6, 11, 12** — il retourne `false` en silence pour 1, 2 et 5. Donc :

* **GuildBoss (4) est LISIBLE en jeu**, via `ViewCommandExecutor.StartUserReplayMatch(replay)` ;
* nos `Waves` (2) ne le sont PAS par cette porte — il faut `ViewCommandExecutor.StartReplayMatch`,
  qui n'a aucun filtre de mode (chemin debug : `DebugReplayGameModeSource` + `Loader.LoadBattle`).

C'est ce qui rend une collecte de guild boss directement exploitable : on peut les **rejouer**,
pas seulement les lire.

## Arborescence — un répertoire PAR BOSS, chacun avec SON registre

```
data/replays/
  README.md                    <- ce fichier
  guild-boss/
    <boss>/
      registre.tsv             <- le registre DE CE BOSS (une ligne par replay)
      <sha256-court>.replay.txt   <- le fichier VERBATIM (jamais réencodé)
    <autre-boss>/
      registre.tsv
      ...
```

**Le registre vit à côté de ses replays, pas au-dessus.** Un index global unique serait le
fichier que toutes les collectes réécrivent en même temps — exactement la forme de conflit
qu'on paie déjà sur `docs/rl/backlog.md` (90 % des PR le touchent). Un registre par boss fait
que deux collectes sur deux boss différents ne se croisent jamais.

**La clé `<boss>` se DÉRIVE du JSON**, jamais du nom de fichier ni du message qui l'a apporté —
même raison que ci-dessus, le nom ment. Le champ est **`BattleConfiguration.BossUnit.UnitId`**
(mesuré le 2026-08-16 : `GuildBoss12Boss1DarkaLion`). Ce n'est PAS `BattleConfiguration.Id`,
qui vaut la même chose ici mais ne porte le boss que par coïncidence — sur nos onslaughts il
vaut `waves`, sur une campagne `Campaign1_75`.

Le répertoire porte le nom **court et humain** (`lion/`) ; l'identifiant natif complet vit dans
la colonne `boss_unit_id` du registre. C'est délibéré : `GuildBoss12Boss1DarkaLion` encode
aussi la saison (`12`) et le créneau (`Boss1`), donc l'utiliser comme nom de dossier
éclaterait le même boss en autant de répertoires que de saisons.

**Nom de fichier = préfixe du `sha256` du fichier.** Stable, sans collision, indépendant de ce
que raconte le message d'origine — et la **déduplication est gratuite** : mesuré, deux captures
qu'on croyait distinctes (`…-2151` et `…-2214`) avaient le même sha256, donc un seul fichier
est gardé au lieu de deux.

⚠ **`forme` dit ce qu'on a VRAIMENT.** L'idéal est `brut` — l'octet exact du `.replay.txt`,
jamais réencodé. Mais le jeu **FAIT TOURNER** son répertoire de replays : au 2026-08-16 les
`.replay.txt` d'origine de nos trois guild boss n'y étaient DÉJÀ plus (il ne restait que les
10 batailles du jour). Les trois entrées sont donc en `forme: decode` — le JSON décodé, seule
copie survivante. Un `decode` ne peut plus être re-vérifié contre son brut : c'est une perte
réelle, et la colonne la déclare au lieu de la masquer. **Sauver le brut LE JOUR MÊME.**

**Ne jamais réencoder un replay récupéré.** On garde l'octet exact : c'est ce qui permet de
vérifier plus tard qu'il n'a pas été altéré, et un round-trip base64/gzip ne redonne pas
forcément le même flux.

## `registre.tsv` — court, et deux familles de colonnes à ne pas confondre

`fichier · boss · rank · map · spawn · role`. Tout le reste (seed, PV du boss, `user_id`,
version de jeu, nombre de messages) est **dans le fichier** et se re-dérive — l'y recopier
n'ajoute qu'une chose à périmer.

**DÉRIVÉES du fichier** (re-calculables, vérifiables) :

* `boss` ← `BattleConfiguration.BossUnit.UnitId` (`GuildBoss12Boss1DarkaLion` → `lion`) ;
* `map` ← **`BattleConfiguration.Board.Id`** (`GB_Lion_01`). ⚠ PAS `BoardId`, qui est `null` :
  la carte est **embarquée** dans la BC, pas référencée par un identifiant ;
* `spawn` ← `BattleConfiguration.SpawnPointSetIndex`. **Colonne à part entière** : à carte
  égale, c'est parfois le seul écart entre deux rencontres.

⚠ **`rank` (le tier de raid, ex. `mythic2`) n'est PAS dans le replay — colonne DÉCLARÉE, à
remplir à la main.** Cherché mot à mot sur deux fichiers : `mythic` n'apparaît que dans une clé
de poids IA (`MastersOfManoeuvre_AdjacentFriendlyMythicDA`), `legendary` que dans
`LegendaryCommander`, `tier` que dans `UnitSpawningOverTime.Tiers` (vide), et `rank` **que sur
les unités du JOUEUR** (`Rank: 16`, `Rank: 17` — le roster, pas le boss). Le tier est une
notion META : la BC n'en porte que les EFFETS.

⚠ **Deux fausses pistes, toutes deux réfutées — ne pas les rouvrir :**

* **le `12` de `GuildBoss12Boss1DarkaLion` (et `BossUnit.Id = 12`) n'est PAS le rang, c'est
  QUEL BOSS.** Mesuré sur les 13 identifiants du build : `GuildBoss5…Mortarion`,
  `GuildBoss7…Rogaldorn`, `GuildBoss8…EldarAvatar`, `GuildBoss9…ThousMagnus` — donc 12 = Lion.
  Et `Boss1/2/3` est la VARIANTE (`…Boss1TyranTervigonLeviathan` / `Boss2…Kronos` /
  `Boss3…Gorgon`). Qu'un tier « mythic 2 » tombe aussi sur 12 par une arithmétique
  6 raretés × 2 niveaux est une COÏNCIDENCE ;
* **le suffixe du nom de carte non plus** : `GB_Mortarion_05`, `GB_RogalDorn_02`, `GB_Lion_01`,
  `GB_Dakka_01` — l'indice varie d'un boss à l'autre sans former de série, il désigne une
  variante de carte.

**Le seul discriminant DÉRIVABLE du tier est `BossUnit.Health`** (37 500 000 pour Lion
mythic2). Il ne le NOMME pas, mais il le sépare : à mesure qu'on collecte d'autres tiers, il
permettra de contrôler un `rank` saisi à la main. Se re-dérive du fichier, donc pas de colonne.

**DÉCLARÉES** (invérifiables depuis le fichier — elles viennent du chat ou de nous) :
`source`, `role`.

`role` est le plus important, et c'est une **décision**, pas une mesure :

* **`reference`** — le flux de messages qu'on **rejoue coup par coup** dans notre runner au lieu
  de laisser l'IA décider, pour confronter le moteur à une partie réelle dont on connaît
  l'issue. C'est le rôle de `9d462d87a131` (54 messages, partie de NBar) ; l'outil qui
  l'exploite est `orch-rejouer-nbar.py`. Une référence ne se remplace pas à la légère : tout
  écart mesuré contre elle perd son point de comparaison.
* **`capture-partielle`** — même bataille, capture tronquée (13 messages contre 54). Gardée
  parce qu'elle documente ce que la voie de récupération rendait à ce moment-là, **pas** pour
  servir d'oracle. Ne jamais la confondre avec la référence : même seed, mêmes PV de boss,
  même `user_id` — seul le compte de messages les distingue.
* vide — collecté, pas encore qualifié.

⚠ **Les colonnes déclarées ne sont PAS mesurées** et le manifeste doit le dire. Un `auteur`
recopié d'un message Discord est une affirmation de tiers : elle peut être fausse sans que le
replay le soit. Ne jamais s'en servir pour conclure quoi que ce soit sur la bataille elle-même —
pour ça, il y a le JSON.

⚠ **Le schéma des colonnes déclarées reste OUVERT** : au 2026-08-16 aucun message de chat n'a
été lu, donc on ne sait pas ce qu'ils portent réellement (boss ? rang ? dégâts ? équipe ?).
Les figer maintenant serait inventer. À arrêter sur un vrai lot de messages, pas avant.
