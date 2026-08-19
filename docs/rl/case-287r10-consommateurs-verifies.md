# #287-r10 — les 7 consommateurs d'`abilityReason` EXPOSÉS sont VÉRIFIÉS ; et deux énoncés tombent

`#287-r9` avait nommé sept consommateurs « exposés, personne n'a mesuré ». Cette tranche mesure les
sept — plus un **huitième**, arrivé depuis et que le cliquet a montré (`master` était **ROUGE** sur
`probe_287r9_consommateurs_oracle`). **Aucun** ne mesure à travers un oracle court-circuité. Deux
résultats dépassent le mandat : la fiche déclarait « indéterminable offline » une question qui se
**dérive du gameconfig**, et le capteur de ligne de vue **ment réellement** — mesuré en direct.

## 1. Les huit verdicts

| consommateur | ids exercés par le RPC | verdict | voie |
|---|---|---|---|
| `probe_249_deathguard_targeting` | `1169` (MoW `deathCrawler`) | **JUSTE** — cran POSÉ | mesure live |
| `probe_250_blacklegion_targeting` | `1148` (MoW `blackForgefiend`) | **JUSTE** — gardé déjà | mesure live |
| `probe_253_astramilitarum_targeting` | `1142`, `1143` (MoW `astraOrdnanceBattery`) | **JUSTE** — gardé déjà | mesure live |
| `probe_447_add_caster_dynamic_rule` | `1115` | **JUSTE** — le canal n'entre dans aucun verdict | lecture |
| `probe_433_r4_…_caster_reason` | `1115`, `1152` (dérivés du kit) | **JUSTE**, **8/60 lignes DÉGÉNÉRÉES** — ventilation POSÉE | mesure live |
| `probe_444_obscured_targeting` | `69`, `1180`, `1202` — **hors gisement** | **JUSTE** | lecture |
| `test_ability_target_gate_live` | `1058` seul — **hors gisement** | **JUSTE** | lecture |
| `probe_287r11r1r1_caster_has_2_turns_left` | `1142` | **JUSTE** — gardé déjà | lecture |

`NON_VERIFIE` : **7 → 0**. `EXPOSE_NON_DECLARE` : **1 → 0**.
Chiffres re-dérivables : `python scripts/python/probe_287r9_consommateurs_oracle.py --tout`.

## 2. Le régime EXISTE — il n'était simplement pas mesuré

`probe_287r9_expose_mesure_live.py --ability 1169 --mow deathCrawler --board C1_02` :

| | `casterReason` | `abilityState` |
|---|---|---|
| tour 1 | `ValidRequest` | `cooldown: 1`, `hasAmmo: true` |
| un tour plus tard | `0` | `cooldown: 0` |

Donc le couple est bien **exposable**, et par le **cooldown seul** — pas par les munitions
(`1169` n'a pas de `munitionsCost`, et le capteur `hasAmmo` livré par #287-r9 est **injecté** :
il répond). Ce que le re-jeu de `probe_249 --only mow` montre ensuite : ses six `endturn` de amorce
**suffisaient**, et six lignes `natif=0x0` sur des tuiles marchables l'attestent **sur le montage
même**. Mais rien ne le vérifiait — c'est du déblocage par **comptage**. Le cran est désormais posé
(`O.debloquer_oracle(..., jouer_adverse=False)` : le montage est GÉOMÉTRIQUE, l'IA adverse le
détruirait). Re-jeu après cran : `8/8`, `VERDICT PASS` — identique. **Le cran ne corrige pas un
résultat, il garantit ce qui n'était qu'un effet de bord de l'amorce.**

Les deux lignes `natif=0x1 ValidRequest` de ce montage sont des **tuiles non marchables** : c'est le
littéral de la branche `TargetIsTile`, pas le court-circuit amont. Le discriminant qui les sépare est
qu'**au même instant les six tuiles marchables rendent `0x0`** — un court-circuit amont refuse
**toutes** les cibles à la fois.

## 3. « Indéterminable offline » était FAUX — le kit le tranche

La fiche rangeait trois consommateurs en « ils itèrent `ABILITY_CLASSES`, on ne sait pas ce que leurs
porteurs portent ». Deux fois sur trois, la lecture suffit ; la troisième se **dérive** :

* `probe_444` — l'`ABILITY_CLASSES` qu'il « itère » est un **test d'appartenance**
  (`if aid_disarmed in ABILITY_CLASSES`), qui n'exerce que l'id testé. Les seuls ids passés au RPC
  sont `69`, `1180`, `1202`. Le recenseur distingue désormais `Compare/In` d'une itération.
* `test_ability_target_gate_live` — son itération (`ABILITY_CLASSES.items()`) va à
  `is_invalid_target` **offline** ; le seul id passé au RPC est `1058`. Un recenseur statique ne
  suit pas le flux de données : c'est un `SAIN_LU`, pas un angle mort.
* `probe_433_r4_…` — `_kit_ability_ids(visual)` intersecte le **kit gameconfig** de chaque unité du
  roster avec les masques RE-lus. Le gisement exercé se calcule donc **sans runner** :
  `{1115 tyranDeathleaper, 1152 orksNob}`, tous deux `initialCooldownTurns = 1`.

## 4. `probe_433_r4` — l'accord était VRAI et DÉGÉNÉRÉ, et rien ne le disait

Mesure `--step cascade`, rosters par défaut, board `MC1_67` :

| | avant | après |
|---|---|---|
| paires confrontées | 60 | 60 |
| accord EXACT | 60 | 60 |
| **dont DÉGÉNÉRÉES** | *(non compté)* | **8** |
| **cascade UTILE** | *(non compté)* | **52** |

Les 8 lignes sont `1115` et `1152` aux itérations 0 et 1 : `natif = 0x1 ValidRequest`. Le port rend
`1` **lui aussi** — `_port_caster_reason` mirroire la marche (d) `ActiveAbility.CanCurrentlyBeUsed`.
L'accord est donc **exact et honnête**, mais il ne dit **rien** de la cascade des onze règles, que le
natif n'a pas évaluée. Les compter avec les autres, c'est l'« accord en régime dégénéré ».
`_verdict_cascade` les ventile, les **nomme avec leur `initialCooldownTurns`**, et rend `INCOMPLET`
si le témoin non dégénéré est vide.

## 5. Le capteur MENT — mesuré, et le recensement qui l'avait raté est un faux négatif de TABLE

`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments) commence,
**avant le moindre test de masque**, par :

```c
foreach (tile in EntityExtensions.GetTiles(targetUnitOrTile, state))
    if (tile.<TileComponent>.IsInFogOfWar)          // TileComponent+0x40
        return <box InFogOfWarBrokenTargetingRule>;
```

Le hook (`NON_GENERIC_RULE_CODES` de `rpc-targeting.ts`) ne connaissait que `NoBrokenTargetingRule`
et `ObscuredTerrainBrokenTargetingRule` ; toute autre classe sort en `hex: "0x0"`.

**Mesure live** — `probe_287r10_fog_capteur_live.py`, board `C6_09` :

| | valeur |
|---|---|
| tuiles du board | 63, dont **34 `isInFog`** |
| `casterReason` | `0x0` (pas de court-circuit amont) |
| tuile EN BROUILLARD | `ruleClass: "InFogOfWarBrokenTargetingRule"`, `hex: "0x0"`, `reasons: []` |
| tuile CLAIRE (contraste) | `ruleClass: "GenericBrokenTargetingRule"`, `hex: 0x200000000000` |

Donc : un **REFUS** que tout `int(payload["hex"], 16)` lit **« cible valide »**.

**Pourquoi le recensement était faux, et c'est la faute que `CLAUDE.md` nomme.** La ligne « `get_Type`
n'a qu'UN seul porteur non générique » venait de l'**absence** de
`InFogOfWarBrokenTargetingRule$$get_Type` dans les tables. IL2CPP **déduplique les corps triviaux** :
ce `return 1` est publié sous le nom `AK.Wwise.AuxBus$$get_WwiseObjectType`, et le `return 0` de
`NoBrokenTargetingRule$$get_Type` sous `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId`.
Le recensement se fait par les **CLASSES** (`frida/classes.tsv` : 4, dont 3 non génériques), jamais
par la présence d'un symbole.

**La valeur `1` est établie par les `ToString`**, qui boxent tous exactement le `Type` de leur classe :
`No` → `0` ; `Generic` → le champ ; `ObscuredTerrain` → `0x1000000` (confirmé par son `get_Type`
NOMMÉ) ; `InFogOfWar` → **`1`**.

⚠ **`1` est donc réutilisé à TROIS rangs** : le `ValidRequest` du court-circuit amont d'`AttackQuery`,
le littéral `1` de la branche `TargetIsTile` (tuile non marchable), et ce `Type`. Le `hex` seul ne les
sépare pas — la `ruleClass`, elle, oui, et le RPC la publie déjà.
⚠ **`oracle_court_circuite` n'est PAS concerné** : `TargetingQuery$$GetInvalidCasterReason` n'a
**aucune** branche brouillard (lu : il ne boxe que `Generic` et `No`), donc un `casterReason == 1`
reste sans ambiguïté le court-circuit amont.

**Livré** : la classe est inscrite dans `targeting_reason.RULE_CLASS_CODES` (effet **immédiat**, côté
Python) **et** dans `NON_GENERIC_RULE_CODES` du hook — cette seconde moitié demande une **fenêtre de
reinject** (résidu `#287-r10-r1`, `BLOCAGE: capteur`). Avant reinject, `native_target_reason` rendait
`None` sur cette classe : une **exclusion silencieuse**, pas un faux zéro — `probe_444` y échappait
donc, et son montage (`C1_09`) est de toute façon mono-salle.

**Portée du régime** : les tuiles en brouillard n'existent que sur les **15 boards `C6_*`** du
catalogue (les seuls à porter plusieurs `RoomID` **et** des `Doors` — balayage offline des 779
boards). Dire cette borne fait partie du résultat : le mensonge est réel, son rayon est fini.

## 6. `#287-r13` — l'énoncé du résidu était FAUX, le silence était ailleurs

Le résidu disait « un `--place`/`--a-place` dont l'unité n'arrive pas en bataille est SILENCIEUX ».
**Réfuté par mesure**, montage `C1_02` / seed 4242 :

| montage | résultat |
|---|---|
| 4 `--a-place` `necroWarden`, la 4ᵉ en `(0,6)` | `[error] placement NON HONORE par le natif: necroWarden (team2) demande @(0,6) mais present @[(2,3),(1,1),(4,6)]` — **rc 3** |
| **le même**, 4ᵉ tuile en `(3,6)` | `placements verifies OK (8)`, **4 `necroWarden` montés**, rc 0 |
| 3 `--a-place` seulement, `--a-units necroWarden x4` | `placements verifies OK (4)`, **3 montés sur 4**, **rc 0, aucun message** |

Trois choses tombent :

1. `_verify_placements` **couvre déjà** le cas `--place`, et son message est juste.
2. La cause écrite dans `probe_287r11` (« `necroWarden` n'existe qu'en TROIS exemplaires dans le
   seed BC ») est **fausse** : `BC.Units` n'en porte qu'**un** template, et la 4ᵉ occurrence monte
   dès qu'on change de tuile. La vraie cause était `(0,6)`, refusée par une des quatre gardes
   muettes d'`AddUnitOperation$$Execute`.
3. Le **vrai** silence est le cas voisin : une unité du roster **confiée au placement natif**, que
   `_verify_placements` ne visite jamais.

**Parade posée** : `rl_duel._verify_roster` confronte le roster DEMANDÉ au roster MONTÉ, camp par
camp, sur le **même** `decisionView` que les placements. Seul le **DÉFICIT** fait faute ; un surplus
(summon, boss) ne rougit pas. Les `unitId` à palier sont normalisés (`tauNpc5StealthSuit:5` →
`tauNpc5StealthSuit`), la troncature n'étant faite que si la partie droite est un entier.

**Avertir ou refuser — la mesure sur laquelle j'ai tranché.** Rayon de souffle mesuré sur quatre
montages représentatifs, **0 faux positif** :

| montage | déficit |
|---|---|
| `--roster 5` aléatoire, `MC1_67` | aucun |
| MoW (`--p-mow deathCrawler`), `C1_02` | aucun |
| unités à PALIER (`tauNpc5StealthSuit:5` ×2, `--explicit-stats`) | aucun |
| montage de `probe_444` (4 `necroWarden`, `C1_09`) | aucun |

Quatre montages ne sont pas les ~500 probes du dépôt : le rayon de souffle d'un **refus dur** n'est
pas dérivable de la config, il faudrait rejouer chaque montage. La garde **avertit** (`[error]` +
cause nommée) sans changer le `rc`. Ce qui manquait n'était pas le refus — c'était le **signal**.
Le passage en refus dur est le résidu `#287-r13-r1`.

## 7. Ce qui n'est PAS couvert

- **La moitié HOOK du correctif brouillard** attend une fenêtre de reinject (`#287-r10-r1`). Tant
  qu'elle n'est pas injectée, tout consommateur qui lit `int(targetReason["hex"], 16)` **au lieu de**
  `targeting_reason.native_target_reason` lira « cible valide » sur un refus de brouillard.
- **Le brouillard n'est mesuré que sur `C6_09`** (le premier board à salles du balayage). Les 14
  autres `C6_*` ne sont pas confrontés ; le probe les balaye et s'arrête au premier qui en porte.
- **Le refus dur du roster** (`#287-r13-r1`) : la garde signale, elle ne bloque pas.
- **`test_targeting_options_masks_live` garde son `if nt == 0x1: continue`** — écartement silencieux
  sans lire `casterReason`. Inoffensif tant que `POOL_CASES` n'intersecte pas le gisement ; c'est
  déjà noté au registre, cette tranche ne le change pas.
- **Les 4 `INDETERMINE`** du recensement ne fixent aucun id au source : le recensement statique ne
  peut pas les trancher, et ils ne sont **pas** déclarés sains.
- **Le troisième terme amont** (`IsDamagedMachine && !IsMachinePrimaryAbilityType`) reste non publié
  — `cause_du_court_circuit` le range en `indeterminee`.

## 7. `#287-r13-r1` : le refus dur est POSE, et le rayon etait DERIVABLE

**Tranche le 2026-08-08.** Le residu disait que le refus n'avait pas ete pose << faute de
mesure : le rayon de souffle n'est pas derivable de la config, il faudrait REJOUER chaque
montage >>. C'est vrai de la FREQUENCE. Ce ne l'est pas du RAYON -- parce qu'**un `rc` ne casse
que ce qui le LIT**.

### Etage 1 -- le rayon (statique, exact)

| classe | invocations |
|---|--:|
| `rl_duel ... build` au total | **259** |
| dont `--list-pool` (n'atteint jamais `_verify_roster`) | 14 |
| **dont montent une bataille** | **245** |
| `rc IGNORE` (resultat lie, jamais teste) | 203 |
| resultat meme pas lie | 26 |
| `.returncode` teste | 14 |
| `check=True` (leve) | 2 |
| **RAYON** | **16 / 245 = 6,5 %** |

Ce qui rend le rayon *petit* est une propriete de POSITION, pas de chance : le `return 3`
arrive **apres `_save_state`**. Le runner existe, le state-file est ecrit, et un appelant qui
n'inspecte pas le `rc` poursuit exactement comme avant. Sortir plus tot ferait passer le rayon
de 16 a 245 -- et laisserait en plus un runner **orphelin**, qui mangerait le cap partage sans
proprietaire. C'est garde (`test_le_refus_arrive_APRES_save_state`).

⚠ L'etage 1 penche du cote **bruyant**, et c'est declare : `.returncode` est cherche dans tout
le FICHIER, pas dans la seule fonction appelante. Sur-estimer un rayon fait renoncer a un refus
qu'on aurait pu poser ; sous-estimer le fait poser un refus qui casse.

### Etage 2 -- la frequence (live, echantillon)

**0 deficit sur 8** montages representatifs (roster aleatoire, MoW, multiplicites x4 et x6,
5v5, 1v1, board etroit, deux camps nommes). Resultat inattendu et instructif : le cas le plus
evident, `x6` sur un board a 4 spawns, est **deja refuse en amont** par le garde de capacite de
spawn JOUEUR (`N spawns joueur < M units`, rc 2). Le deficit residuel vient donc du cote
**ADVERSE**, confie au placement natif (`SetupGameOperation$$AddPredefinedUnits`), qui n'a pas
d'equivalent -- exactement le cas fondateur de #287-r13.

Le risque reel est le **produit** des deux etages, jamais l'un des deux seul.

### Ce qui est pose

* `rl_duel.cmd_build` : `roster_problems` conditionne desormais le `return 3`, au meme titre que
  `placement_problems` et `modifier_problems` ;
* **les trois diagnostics sont imprimes AVANT tout retour.** Avant, `placement_problems` rendait
  3 sans jamais laisser parler `modifier_problems` : l'appelant relancait pour decouvrir le
  second ;
* **echappatoire par ENVIRONNEMENT** -- `TACTICUS_ALLOW_ROSTER_DEFICIT=1`, meme forme que
  `TACTICUS_ALLOW_GREEN_SKIP` (#455). Par ENV et non par drapeau, deliberement : un appelant que
  ce refus bloquerait est un probe **deja ecrit**, souvent celui d'un autre agent -- lui
  demander de modifier son fichier pour se debloquer lui ferait payer notre cliquet. La variable
  se pose devant la commande. Et le **message d'erreur la NOMME** : une echappatoire qu'il faut
  deviner n'en est pas une (garde).

### La contre-epreuve, a DEUX bras sur le MEME montage

`C1_02` / seed 4242, quatre `necroWarden` pour trois `--a-place` (le montage de #287-r13) :

| bras | deficit detecte | `rc` |
|---|---|--:|
| defaut | oui | **3** |
| `TACTICUS_ALLOW_ROSTER_DEFICIT=1` | oui | **0** |

Les deux bras sont necessaires : sans le bras leve, un `rc == 3` ne distinguerait pas un refus
d'un echec de montage ; sans le bras dur, un `rc == 0` ne distinguerait pas l'echappatoire d'une
absence de deficit.

Livre : `probe_287r13r1_rayon_refus_roster.py` (`--live` joue les trois etages) et
`tests/test_287r13r1_refus_roster_offline.py` (8 tests, dont le cran
<< si le rayon franchit le tiers des appelants, re-arbitrer le refus par defaut >>).
