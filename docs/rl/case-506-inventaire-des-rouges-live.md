# #506 -- Les cinq rouges LIVE de `master` n'en font qu'UN : la bascule « equiper » de #419-r6

**Pourquoi cette fiche.** Cinq familles de rouges LIVE ont ete signalees par cinq agents
differents pendant la journee du 2026-08-07, chacune prouvee ANTERIEURE a la tranche qui la
rapportait. Aucune n'a ete traitee : elles etaient hors du perimetre de chacun. **Aucun cliquet ne
les voit** -- ce sont des tests LIVE, et la banque qui tourne a chaque PR (`probe_457`) est
OFFLINE. Ils peuvent donc pourrir indefiniment : c'est le mode de defaillance que #455 a documente
sur l'axe du SKIP, transpose a l'axe LIVE/OFFLINE.

**Regime de mesure.** Worktree a `6f9f6071`, **exactement** `origin/master` au moment de la mesure
(`git rev-parse HEAD == git rev-parse origin/master`, verifie). Tout rejeu ci-dessous est donc un
rejeu sur `master` NU, sans aucune edition. Session Frida `5`, drain off, warmup passe. Build du
jeu `rnca9r7q6c` == `data/symbols/CURRENT` (verifie : le build du jeu n'a PAS bouge, ce n'est pas
la cause).

---

## 1. Inventaire -- les cinq, mesures un par un, puis le TEMOIN

Colonne « TEMOIN » = **le meme fichier, rejoue avec `TACTICUS_BIS_ITEMS=0`** (le drapeau qui
restitue le regime d'AVANT `c4be3896`, sans toucher a une ligne de code).

| # | Fichier (`scripts/python/`) | Signalement | Mesure sur `master` nu | TEMOIN `BIS_ITEMS=0` |
|---|---|---|---|---|
| 1 | `tests/engine/test_419r1tr14r5r2r1r1r1_normal_attack_kill_gate_live.py` | 1 failed / 9 passed | **1 failed / 9 passed** | (cf. §2.1) |
| 2 | `tests/engine/test_tile_term_unit_gated_playbooks_live.py` | 13 failed / 12 passed / 5 skipped | **13 failed / 12 passed / 5 skipped** | **30 passed** |
| 3 | `tests/engine/runner/test_steppable_targeting_live.py` | 2 failed / 6 passed | **2 failed / 6 passed** | **8 passed** |
| 4 | `tests/engine/runner/test_cultdemagogue_migration_live.py` | 6 errors `KeyError: 'units'` | **6 errors** | **6 passed** |
| 5 | `tests/engine/runner/test_summon_consumers_live.py` | 1 failed | **1 failed / 28 passed** | **29 passed** |

**Les cinq signalements sont EXACTS au test pres.** Et les quatre premiers temoins mesures
redeviennent **integralement verts** dans le regime d'avant la bascule.

## 2. La cause unique -- `c4be3896`, #419-r6, 2026-08-06 14:01

    #419-r6 : basculer le defaut a << equiper >> -- 17 fichiers repares, perimetre DERIVE,
    causalite etablie par TEMOIN (#742)

Depuis ce commit, `rl_duel build` **equipe** chaque unite de ses items Best-In-Slot avant la
formule de stats. La bascule est **JUSTE et reste** : sans items, `CouldCrit`
(`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` = `GetStat(9) > 0 && GetStat(10) > 0`)
etait FAUX sur **106/106** unites du seed, cote natif COMME port -- tout accord sur le crit etait
un accord en regime DEGENERE. Ce qui change aussi, mecaniquement : `FixedArmor` sur **49/106**
unites, les degats, les PV. Donc **toute trajectoire native, toute geometrie et tout seuil de
degat calibres AVANT le 2026-08-06 ont bouge**.

Le commit lui-meme nomme son residu : **`#419-r6-r1` -- « perimetre restant + face DECISION +
les 7 preexistants »**. Son perimetre derive couvrait trois canaux (coup propre exige **38**,
deja neutralises **34**, valeur en dur **25**) ; **aucun des cinq fichiers ci-dessus n'y figure**.
Les cinq rouges sont donc **exactement le residu annonce**, jamais ouvert.

**Ce que la reparation N'EST PAS.** Repasser les montages sous `TACTICUS_BIS_ITEMS=0` fabriquerait
des verts en regime degenere -- precisement ce que #419-r6 a supprime. Chaque montage se
**re-etalonne sous le regime EQUIPE**.

### 2.1 -- La forme du degat, montage par montage

* **#2 -- trajectoire NATIVE decalee.** Le montage epingle un PAS (`step=34`, `28`, `26`, `19`) sur
  une trajectoire marchee par `aiStepDryRun -> applyAction`, donc 100 % native. Les stats ayant
  change, l'ordre d'activation a glisse : au pas 34 c'est `bloodIntercessor` qui est active, pas
  `blackTerminator` ; au pas 28 et 26, `templChampion` au lieu de `darkaAsmodai` ; au pas 19,
  `bloodMephiston` au lieu de `deathBlightbringer`. Un cinquieme cas (`MC1_67/777` pas 25) part
  desormais en **skip** -- la bataille FINIT au pas 23. Fait notable : le 5e test de chaque cas,
  `test_best_attack_tile_agrees_with_native`, **passe partout** -- le PORT est d'accord avec le
  natif ; seul le montage est perime.
* **#3 -- geometrie du contrefactuel perdue.** Toutes les lignes s'accordent natif/port (`nat ==
  port` sur 18/18) ; ce qui tombe est le contrefactuel « le port d'AVANT acceptait » : desarme du
  bit `AllowSteppableUnit`, le port ne rend plus `0` sur les decoys mais `0x8000000` -- une AUTRE
  regle de refus mord d'abord. Le montage ne fabrique plus la fenetre ou le bit 51 est le SEUL
  refus.
* **#4 -- la bataille se termine avant le cast.** `decisionView` ne publie plus `units` quand la
  bataille est finie (comportement connu et deja gere ailleurs : `_summon_montage.py` lit
  `dv.get("units") or []`). Ici la lecture est nue (`dv["units"]`), donc `KeyError` au lieu d'un
  diagnostic. Deux defauts distincts : la trajectoire (cause) et la lecture nue (ce qui rend le
  symptome illisible).
* **#5 -- la garde conditionnelle est defaite par un effet TIERS.** Le volet live de
  `test_waaagh_buff_effects_posed_live_and_port` est garde par `if d["live_effects"]:`, et sa
  docstring explique pourquoi : dans ce roster le cast epuise les activations, le tour bascule, et
  les 3 buffs `Direct(1)` ont deja expire quand `decisionView` est relu -- `live_effects` etait
  donc VIDE et la garde sautait. Depuis la bascule, le caster porte `BigTarget_AdjacentEffect`
  (effet tiers, qui n'expire pas) : `live_effects` est non vide sans contenir aucun Waaagh, et
  l'assertion mord sur un regime qu'elle n'a jamais voulu juger.
* **#1 -- la premisse d'un BRAS n'est plus vraie.** Le carre apparie oppose un bras `nokill`
  (cible a PV pleins) a un bras `kill` (cible a 1 PV). Equipe, `ultraEliminatorSgt` tue desormais
  la cible A PV PLEINS d'une attaque normale : la contre-epreuve mord dans le bras `nokill`, ou
  elle doit etre inerte. Ce n'est pas le gate qui est faux -- c'est le bras qui ne realise plus sa
  propre premisse.

---

## 3. Ce que cette tranche a repare

Le critere de reussite n'est **pas** « c'est vert » : c'est **le compte du TEMOIN** (#419-r6-r1
§3.3). Un fichier qui rendrait plus de tests verts que son temoin aurait change d'objet.

| # | avant | apres | temoin | geste |
|---|---|---|---|---|
| 2 | 13F / 12P / 5S | **30 passed** | 30 | neutralisation crit/block, QUATRE faces, au montage |
| 3 | 2F / 6P | **8 passed** | 8 | l'attaquant de mesure est CHOISI puis AMENE au contact |
| 4 | 6 errors | **6 passed** | 6 | neutralisation crit/block + echec NOMME au lieu d'un `KeyError` |
| 5 | 1F / 28P | **29 passed** | 29 | la condition du volet live devient MESUREE, et les deux branches assertionnent |

### 3.1 -- #2, #4 : le remede-type, et POURQUOI pas `--no-bis-items`

Les deux fichiers mesurent une TRAJECTOIRE / des STATS DE SPAWN, jamais un montant de degat
inflige. On epingle donc **quatre scalaires sur CE montage**
(`--crit 0,0 --crit-target 0,0 --block-player 0,0 --block-target 0,0`) plutot que de restituer le
regime degenere global. Precedent exact : #419-r6-r3 sur `test_477r33_non_owner_playbooks_live`
(6 failed / 35 passed -> 41 passed). Les **quatre** faces sont necessaires : les deux montages ont
des porteurs des deux cotes.

⚠ **La neutralisation ne mord QUE sur les unites nommees.** `rl_duel build` applique
`--crit`/`--block-*` a `p_units`/`a_units`, c.-a-d. au roster EXPLICITE quand il y en a un, sinon
au tirage `rng.sample(pool, roster)`. Elle mord donc toujours -- mais elle ne suffit pas partout
(cf. residu `#506-r1`).

### 3.2 -- #3 : l'attaquant de mesure ne se SUBIT plus

Le probe prenait la VICTIME du cast (qui a les decoys au contact par construction) et retombait
sinon sur `foes[0]`, c.-a-d. l'ordre de `decisionView`. Depuis la bascule, les tours AI immediats
des Neophytes TUENT la victime, et `foes[0]` est un ennemi quelconque : les 5 decoys rendaient
`portDesarme = 0x8000000` (refus de PORTEE) au lieu de `0x0`, donc l'etage B n'avait plus de ligne
ou le port d'AVANT ACCEPTAIT -- le contrefactuel qui fait TOUT le sens de la regle, puisque sa
degradation est PERMISSIVE.

⚠ L'accord natif/port, lui, restait **18/18** : c'est la regle 51 qui PRECEDE le volet portee dans
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`, donc les deux cotes refusaient
en `TargetIsNotSteppable` sans jamais atteindre la portee. **Un accord peut survivre a la
disparition du regime qui le rendait probant** -- seul le contrefactuel l'a vu.

Le probe choisit desormais l'ennemi vivant le plus proche d'un decoy et l'**AMENE au contact**
(`_step_toward`, runner `--no-ai`, `applyAction` ne verifie pas la propriete du `unitId`).

### 3.3 -- #5 : une condition PROXY qui a lache

Le volet live etait garde par `if live_effects:` = « le caster porte au moins un effet », ce qui ne
valait que tant que le seul effet possible etait un buff Waaagh. Depuis la bascule, la cible SURVIT
au cast, `decisionView` publie encore le caster, et celui-ci porte `BigTarget_AdjacentEffect` (effet
TIERS qui n'expire pas) : la condition devenait vraie dans le regime qu'elle etait ecrite pour
EXCLURE. Elle est desormais MESUREE (`dv1.currentPlayer == owner du caster` = tour encore ouvert) et
**les deux branches assertionnent** -- tour ouvert => les 3 buffs sont la ; tour tique => ils n'y
sont PLUS (duree `Direct(1)`, mesure #95). Aucune branche n'est vide.

Le volet live INCONDITIONNEL vit ailleurs et il est VERT : `test_waaagh_buff_contrib_live.py`
**7 passed** (mesure de cette tranche) -- les buffs SONT bien poses live.

### 3.4 -- #1 : le SEUL des cinq qui soit un BUG DE PORT, et le temoin l'a designe

`test_419r1tr14r5r2r1r1r1_normal_attack_kill_gate_live.py` echoue **A L'IDENTIQUE** sous
`TACTICUS_BIS_ITEMS=0` (1 failed / 9 passed dans les deux regimes) : ce n'est **pas** la bascule.
C'est aussi le verdict de `#419-r6-r1` §2.2, qui le classait deja PREEXISTANT sans le diagnostiquer.

**Decomposition par etage** (`logs/mes506_killgate*.py`, seed 4242 / MC1_67, cible `adeptRetributor`
a **7530 PV pleins**), et c'est le 2e etage qui tranche :

| caster | ability | `hpBefore` du port | `rawHealthDmgMin` | `killSure` | natif (`decisionView.attackPlans`) |
|---|---|---|---|---|---|
| `ultraEliminatorSgt` u87 -> u77 | 1004 | **0** | **0** | **true** | `dmgMin 1958 / dmgMax 4166`, `killSure false` |
| `ultraEliminatorSgt` u87 -> u79 | 1004 | **0** | **0** | **true** | `dmgMin 2937 / dmgMax 6249`, `killSure false` |
| `astraPrimarisPsy` u83 -> u77 | 1027 | **0** | **0** | **true** | `dmgMin 2409`, `killSure false` |
| `astraPrimarisPsy` u83 -> u79 | 1027 | 7530 | 2409 | false | `dmgMin 2409 / dmgMax 3613` -- **BIT-EXACT** |
| `blackObliterator` u89 -> u77 | 1036 | 7530 | 4858 | false | -- |

Le port ne se trompe pas de VALEUR : quand il predit, il predit **exactement** comme le natif. Il
rend `hpBefore = 0` -- **les PV de la cible ne sont jamais lus** -- et
`IdunBattle.Core.Services.DamagePredictionResult$$get_WillBeKill` (borne MIN >= PV courants) lit
alors `0 >= 0` = **VRAI**. **Une prediction VIDE se lit comme un KILL CERTAIN.**

**Le site** : `engine/playbook/prediction/normal_attack.py`, branche SANS ARME de
`make_normal_attack_predictions` (introduite par `9ba79819`, #419-r1-tr14-r1-r1, 2026-08-06 01:37),
qui fabriquait `DamagePredictionResult(applied_hits=1)` -- structure a zero.

**Ce que le natif fait, LU au decompile**
(`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$PredictAttack`) : la
branche `else` (arme nulle, ou `TryGet<DamageProfile>` faux) **n'invente aucune structure** -- elle
appelle le **slot `0x26` d'`IBattleQuery`** sur `entities+0x20`, avec les deux listes de modifiers
VIDES (les deux widgets statiques crees juste avant) et les litteraux `0, 0`. C'est la MEME facade
de prediction que la branche avec arme, **contre la VRAIE cible** : sa `DamagePredictionResult`
porte donc `CurrentHealth@0`, `CurrentArmor@4`, `CurrentShield@8` de la cible, et seul le DEGAT est
nul. `get_WillBeKill` y rend `0 >= 7530` = **FAUX**.

**Le correctif** appelle la meme facade (`get_attack_prediction(initial_damage=0, hits=1, ...)`)
avec les PV / l'armure / le bouclier reels de la cible. Controle OFFLINE
(`logs/mes506_noweapon_offline.py`) : `appliedHits` reste **1** (le litteral natif), `killSure`
devient FAUX des `hp > 0` et reste VRAI sur `hp == 0` -- la cible morte que `decisionView`
conserve, comportement deja documente dans `probable_damage_event.composite_fields`.

**Deux consequences du bug, dont une que le test ne mesurait pas** :

1. `IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill` rendait VRAI **hors portee**, donc
   les **15** playbooks du gate `#419-r1-tr14-r5-r2-r1-r1-r1` REFUSAIENT leur ability des que
   l'attaque normale ne portait pas depuis la tuile de cast. Le port PERD une action legale -- le
   sens de divergence que le fichier appelle lui-meme « le plus grave ».
2. `KillUnitUtility` (`engine/utilities/damage.py`) lit `killSure` et rend `DefinitelyKill`,
   l'utilite MAXIMALE, pour une attaque qui n'atteint rien. Aucun test ne le mesurait.

#### Validation du correctif, et ce qu'il DEPLACE -- DEUX assertions a ARBITRER

| epreuve | resultat |
|---|---|
| controle OFFLINE (`logs/mes506_noweapon_offline.py`) | `appliedHits` = **1** ; `killSure` FAUX des `hp > 0`, VRAI sur `hp == 0` |
| `test_419r1tr14r1r1_range_gate_generalisation_live` + `test_419r1tr14r1_heavy_bolt_pistol_real_carriers_live` | **16 passed** -- les deux gardes de la porte de portee, seules consommatrices directes de la branche |
| GENERALISATION crafte (`logs/mes506_gen.py`) -- **autre board `C4_09`, autre seed 31337, autres unites**, positions DRIVEES | **PASS** : 3 couples hors portee (`hpBefore` = 8536 / 8536 / 1573, jamais 0 ; `killSure` faux) **et 1 temoin EN portee non degenere** (`rawMin 2195 / rawMax 4955` sur 1573 PV -> `killSure` VRAI). 0 violation |
| `test_tile_term_unit_gated_playbooks_live` rejoue APRES le fix | **30 passed** -- le plus gros fichier d'AGREEMENT de tuile ne bouge pas |
| le fichier cible | **2 failed / 8 passed** (il etait a 1 failed / 9 passed) |

Le correctif **ferme** `test_la_contre_epreuve...` sur le bras `nokill` -- la ligne du signalement --
et en **ouvre deux** sur le bras `kill`. Les deux reposent sur une premisse que le montage
**n'installe pas**, et qui n'a rien a voir avec le port :

* `reached` (= « l'attaque normale porte DEPUIS SA TUILE ») vaut **`ultraEliminatorSgt: False`** dans
  le bras `kill`. Ce n'est **pas** un plafond d'iterations trop bas : mesure
  (`logs/mes506_reached.py`) a `MAX_APPROACH_TURNS` = **8** puis **24**, `reached` est **IDENTIQUE**
  -- l'approche est structurellement bloquee pour ce caster ;
* `port_proposes` est un `any(... for t in foes)` sur les **DEUX** cibles. Avec le gate corrige, une
  cible HORS PORTEE cesse d'etre vetoee, donc `any` devient vrai des qu'UNE cible echappe a la
  portee -- et la contre-epreuve devient INERTE la ou elle mordait.

Le **critere B** du fichier, lui, filtre deja sur `reached` (`r["reached"]`) et reste **VERT** ; les
deux assertions en cause ne le filtrent pas. **Je ne les modifie pas** : changer un attendu demande
l'arbitrage. Ce que je proposerais, pour memoire : restreindre ces deux assertions aux casters dont
`reached` est vrai (le MEME filtre que le critere B), ce qui ne relache rien -- ou faire porter
`port_proposes` sur la cible que le natif a effectivement choisie.

⚠ **Ce que le fichier avait ecrit, et pourquoi il ne pouvait pas voir le bug.** Son en-tete porte
« UNE BORNE A ETE ESSAYEE PUIS REFUTEE : desarmer le gate quand l'attaque normale ne porte pas
depuis la tuile de cast fait passer trois lignes du bras `kill` de "port refuse" a "port accepte"
alors que le natif, lui, REFUSE. **Le natif predit donc l'attaque normale HORS PORTEE, comme le
port.** » Cette conclusion a ete tiree le **2026-08-04**, AVANT que `9ba79819` (2026-08-06) ne porte
la branche sans arme : a l'epoque le port ne gatait PAS sur la portee et predisait un degat reel
hors portee. La phrase decrivait donc un port qui n'existe plus, et elle a servi d'argument pour ne
pas re-examiner le sujet. **Un avertissement ecrit contre une borne datee peut survivre au regime
qui le justifiait.**

---

## 4. Residus

* **`#506-r1` -- DEUX fichiers de plus dans la meme famille, trouves par DERIVATION, NON REPARES.**
  `_move_tile_sweep_order.build_sweep_order_case` est partage par TROIS fichiers ; seul celui des
  cinq signalements l'etait. Les deux autres, mesures sur `master` nu (joues ensemble) :
  **3 failed / 8 passed / 7 skipped**.
  * `test_tile_term_triggered_playbooks_live.py` : au pas 14 de `C4_09/999` c'est `astraCreed` qui
    est active, pas `templAncient` ; le cas du pas 22 de `C4_09/31337` skippe
    (`pas 22 non atteint (stage Finished)`).
  * `test_move_tile_sweep_order_live.py` : le couple `C4_09/999` pas 14 -- **le seul des deux qui
    DISCRIMINE**, « le seul couple discriminant trouve sur 10 couples balayes » selon son propre
    en-tete -- part en `montage NON discriminant : les deux ordres coincident`. Le fichier reste
    vert au `rc`, et c'est exactement l'invisibilite que #455 decrit.

  La neutralisation crit/block a ete ESSAYEE sur ces deux fichiers et **NE SUFFIT PAS** : elle
  deplace les rouges (le pas 14 de `C4_09/999` redevient vert, le pas 22 tombe) sans les fermer,
  parce que ces cas n'ont pas de `--hp-*` et subissent donc AUSSI le `FixedArmor` des items
  (49/106 unites) et le `Health` (4/106). L'edition a ete **retiree** plutot que livree a moitie.
  Le remede qui reste a instruire est la **re-mesure des pas** -- ou, mieux, un montage qui
  **CHERCHE** son pas au lieu de l'epingler : la mesure des pas d'activation sous le regime equipe
  est deja faite pour les six cas de #2 (`blackTerminator` 34 -> {3, 35, 41}, `darkaAsmodai`
  28 -> {4, 5} et 26 -> {1, 2, 25, 30}, `deathBlightbringer` 25 -> {12, 18} et 19 -> {3, 13, 18,
  21}), et elle montre qu'un pas epingle est structurellement fragile.

* **`#506-r2` -- le MEME vice, un site plus loin, NON MESURE.**
  `engine/playbook/prediction/normal_attack.py` porte un second
  `ProbableDamageEvent(target=tgt_id, prediction=DamagePredictionResult())` : la branche du chemin
  DRONE `MV71` quand `pick_tile_scene` ne rend aucune tuile. Meme forme (`current_health = 0` donc
  `killSure` VRAI), mais **autre mecanisme** et **autre corps natif**
  (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$PredictAttack`),
  que je n'ai pas lu. Le reparer par analogie serait speculatif. A instruire : lire la branche
  « aucune tuile » de ce corps, et dire si elle appelle elle aussi la facade contre la vraie cible.

* **DEUX assertions de `test_419r1tr14r5r2r1r1r1_normal_attack_kill_gate_live.py` attendent un
  ARBITRAGE** (§3.4) -- le fichier passe de 1 failed / 9 passed a **2 failed / 8 passed**. Le
  correctif de port ferme la ligne signalee et en ouvre deux dont la premisse (`reached`) n'est pas
  installee par le montage. Non modifiees deliberement.

* **`#419-r6-r1` reste ouvert et cette tranche le CONFIRME de deux facons.** Son §2.2 classait deja
  `test_summon_consumers_live` en CAUSE (28/1 -> 29) et
  `test_419r1tr14r5r2r1r1r1_normal_attack_kill_gate_live` en PREEXISTANT -- mes deux mesures
  independantes rendent **exactement** ces deux verdicts. Les trois autres (#2, #3, #4) n'etaient
  dans AUCUNE des deux listes : ils font partie des « ~100 derniers fichiers non visites » que son
  §5 declare **NON MESURES**. Ils sont desormais mesures, ventiles et **reparés**.
