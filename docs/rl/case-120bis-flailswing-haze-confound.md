# case-120bis / #209 -- le montage « mono-cible » du probe de re-resolution etait CONFONDU par le PASSIF du caster

**Verdict : le TEST est en tort, pas le port.** Le montage offline de l'etape 2 de
`probe_120bis_execute_for_replaced_target.py` a cesse d'etre discriminant le jour ou case-209 a
rendu vivante la charge utile de `HazeOfCorruption` -- sans qu'aucune ligne de #120bis ne change.

## 1. Symptome

`scripts/python/tests/engine/runner/test_pre_unit_ability_fork_live.py::test_port_reproduces_replaced_target_offline`
echouait sur `origin/master` vierge (HEAD `77bbb71`) :

```
[2] voie CAST (1042) : last.target=3 replaced_from=1 replaced_target=3 | hp creed=398481 kell=0
AssertionError: Creed a encaisse un cast mono-cible (hp=398481) alors que Kell avait pris sa place
   probe_120bis_execute_for_replaced_target.py:189
```

## 2. Datation

`git bisect run` sur `2b5a3bb..ccd3e8e`, critere = l'etape 2 isolee (« Creed reste a 400000 »).

| commit | date | verdict |
|--------|------|---------|
| `2b5a3bb` #120bis, creation du probe | 2026-07-26 19:02 | PASSE (`hp creed = 400000`) |
| `fb90b1b` (= `ed45582^`) | 2026-07-28 | PASSE |
| **`ed45582`** `feat(rl): #209 HazeOfCorruption -- la charge utile du bond 1077` | 2026-07-28 23:14 | **PREMIER ECHEC** |
| `ccd3e8e` / `77bbb71` (HEAD au lancement) | 2026-07-29 | ECHEC |

Les quatre refontes de la nuit citees comme suspectes (file de morts `8f91dc4`, mode `amount` /
`amount_spread_pct`, gates `MinDist`, gate `IsAffectedByHealType`) sont **hors de cause** : le probe
echouait deja a `fb90b1b`, donc avant elles.

## 3. Cause : un TROISIEME canal de degat, ouvert par case-209

L'etape 2 caste `FlailSwing` (1042) depuis **`deathBlightlord`**, choisi parce que l'ability est
`3x Power melee MONO-CIBLE` -- « aucun degat collateral possible ». La premisse est vraie de
l'**ability** et fausse de l'**unite** : `deathBlightlord` porte le passif `HazeOfCorruption`.

Chaine native, deja RE-ee et validee live par case-207 / case-209 :

1. `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateTrigger`
   = `On(0x2b = PreUnitAbility, 1) & get_OwnerIsCaster` -- il part donc **a chaque emission**, y
   compris a la RE-ENTREE d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget`,
   ou `Target@0x178` vaut deja Kell ;
2. `…HazeOfCorruption_TargetFinderAbility$$CreateBehaviour` bonde (effet `0x435 = 1077`)
   `PickRandomly(Damageable(AdjacentEnemies(Self@0x148, 1, 3) & AdjacentFriends(Target@0x178, 1, 3)), 2)` ;
3. Kell tombe sous les coups -> `IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit`
   enregistre le degat GASPILLE (site C = reste d'overkill du coup fatal, puis site A/B = la base
   nominale du coup Toxic bonus de `HazeCorruption_BonusHitAbility`) ;
4. `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger`
   fait encaisser au RELAIS bonde chaque `LeftOverDamage` de la source.

Mesure offline sur le montage du probe :

```
creed=(1,2)  kell=(2,2)  blightlord=(2,1)     -- Creed adjacent a Kell ET au caster
leftover(kell) = [{976, 'Power'}, {543, 'Toxic'}]  -> somme 1519
hp creed 400000 -> 398481                          -> ecart 1519   (egalite EXACTE)
```

Creed est **toujours** `AdjacentFriends(Kell)` apres le switch (le switch les echange, ils sont
adjacents par construction). Le seul terme qui peut l'exclure du pool est donc
`AdjacentEnemies(caster)`.

## 4. Pourquoi le LIVE ne le voyait pas : la TUILE DE SPAWN

`test_mono_target_cast_hits_kell_not_creed_live` passe (re-joue le 2026-07-29), avec le MEME caster
et la MEME ability. Diagnostic live du montage :

```
CREED pos (1,6) -> (2,5) | hp 400000 -> 400000
CASTER (0,5) | KELL (1,6) hp 0/8973 isDead=True
d(caster, creed) = 2 ; d(creed, kell) = 1
```

Kell **meurt** aussi en live -- les `LeftOverDamage` existent donc -- mais Creed finit a **distance
2** du caster, donc hors d'`AdjacentEnemies(Self)` : pool VIDE, aucun bond, aucun report.
Verifie sur **3/3** montages live (`MC1_67`/777, `MC1_67`/31337, `C3_26`/777) : `d(caster, creed) == 2`
a chaque fois. Le natif fait apparaitre Kell **du cote oppose a l'attaquant**, via
`IdunBattleLogic.Entities.Abilities.Active.Loki.SwornProtectorAbility$$GetSpawnTile`, RELU au
decompile pour cette fiche :

    b = UtilityBucket([ WeightedUtility(7), WeightedUtility(0x33) ])   # deux ctors successifs
    p = TestUnitProvider(b)                                           # << le bucket est ENVELOPPE
    First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(tilesC)), p, owner@0x148 ), 1 )

(la docstring du port cite `UtilityBucket{...}` directement en 2e argument ; le decompile montre
qu'il passe par `IdunBattleLogic.AI.Utilities.TestUnitProvider$$.ctor` -- precision qui compte pour
qui portera le tri.)

Le port **ne porte pas** ce tri (residu deja declare dans
`engine/runner/operations/triggers/loki/sworn_protector.py` : « le POOL et le CARDINAL sont exacts,
la TUILE choisie peut differer du live ») : il prend `First(CanAddUnit(AdjacentTiles(Caster())))`,
c'est-a-dire le premier voisin libre dans l'ordre `board.neighbours`. Sur `MC1_67`, **163 des 316**
couples (Creed, caster adjacent) laissent alors Creed a distance 1 -- dont exactement celui que le
probe utilisait.

**La divergence live/offline est donc GEOMETRIQUE, pas une infidelite du port** : dans une
configuration ou Creed EST adjacent au caster, le natif reporterait aussi. Ce residu, jusque-la
inobservable, est devenu observable le jour ou le canal 1077 a eu une charge utile -> entree
`#120bis-spawn` au backlog.

## 5. Correction

Aucune ligne de moteur n'est touchee. Deux fichiers de MESURE :

* **`probe_120bis_execute_for_replaced_target.py`**
  * `_fresh` gagne `foe_pos` ; deux constantes nommees : `FOE_POS = (2,1)` (Creed reste relais) et
    `FOE_POS_OPPOSITE = (3,2)` (Kell spawne du cote oppose -> `d(caster, creed) == 2`, la geometrie
    que le natif produit).
  * **etape 2** joue `FOE_POS_OPPOSITE`. Le critere strict `hp creed == 400000` est **inchange**,
    et deux gardes de MESURE l'encadrent desormais : `d(caster, creed) > 1` et « aucun effet 1077
    sur Creed ». Le montage ne contourne pas le canal en silence, il PROUVE qu'il en est sorti.
  * **etape 9, nouvelle** : le regime oppose (`FOE_POS`), ou Creed EST relais. Ce qu'il encaisse
    doit valoir **exactement** la somme des `LeftOverDamage` de Kell -- donc rien du cast. Cette
    etape reste un test de la re-resolution : si `ExecuteForReplacedTarget` regressait, les 3 coups
    d'arme partiraient sur Creed (bien plus que le report) **et** Kell n'aurait aucun leftover ;
    l'egalite tomberait des deux cotes.
* **`tests/engine/runner/test_pre_unit_ability_fork_live.py`** : la docstring de la fixture
  `mono_target_cast` affirmait « zero degat collateral possible » -- corrigee (l'ability ne peut rien
  eclabousser, le CASTER si), et `test_mono_target_cast_hits_kell_not_creed_live` **asserte**
  desormais `d(caster, creed) > 1` au lieu de le supposer. Sans cette garde, le verdict live
  deviendrait silencieusement non discriminant si la geometrie changeait.

## 6. Chiffres avant / apres

| | avant | apres |
|---|---|---|
| probe etape 2, `hp creed` | **398 481** (echec) | **400 000** |
| probe etape 9 (nouvelle) | -- | `leftovers(kell) = [976, 543]`, somme **1519** = `400000 - 398481` |
| `probe_120bis` global | AssertionError l.189 | `PROBE OK` (9 etapes) |
| `test_pre_unit_ability_fork_live.py` | 5 passed, **1 failed** | **6 passed** |

Non-regression re-jouee : `test_sworn_protector_kell_live.py` + `test_haze_of_corruption_transfer_live.py`
(**16 passed**), `test_flail_swing_live.py` (**3 passed**).

## 7. Residus

* **`#120bis-spawn`** (backlog) : `SortTilesByUtilityForSummon` non porte. Tant qu'il l'est,
  n'importe quel montage offline melant un summon-protecteur et un caster a volet collateral
  d'adjacence peut diverger du live par la seule tuile de spawn.
* **Le patron de montage lui-meme est un piege** : « je prends une ability MONO-CIBLE pour qu'aucun
  degat ne fuie » ne dit RIEN du kit du caster. `deathBlightlord` etait le choix naturel (l'ability
  1042 est mono-cible et bien portee) et c'est precisement l'unite dont le passif eclabousse les
  allies adjacents de sa cible. Le bon reflexe est de qualifier le CASTER, pas seulement l'ability.
* **`#120bis-spawn` est LIVRE (2026-08-08)** -- cf. Sec.8. Ce residu-ci est donc ferme ; les deux
  autres puces restent ouvertes.
* **Non couvert** : le regime « Creed relais » (etape 9) n'a **pas** d'oracle live propre -- les
  3 montages live essayes placent tous Kell du cote oppose, donc Creed hors du pool. Le canal 1077
  lui-meme, lui, est valide live par case-209 (6/6 montages bit-exact) et case-221 ; ce qui n'est pas
  confronte est la COMPOSITION « re-resolution + report » dans une geometrie que le natif ne produit
  pas spontanement avec `SwornProtector`. Fermer ce point suppose soit de porter
  `SortTilesByUtilityForSummon`, soit de monter live une geometrie ou Creed arrive au contact du
  blightlord par un autre chemin que le switch.

## 8. `#120bis-spawn` -- PORTE (2026-08-08), et la citation de Sec.4 etait PERIMEE D'UN BUILD

`SwornProtectorAbility$$GetSpawnTile` relu sur `rnca9r7q6c`, terme a terme :

    utilities = [ WeightedUtility(0x7,  <Nullable vide>), WeightedUtility(0x34, <Nullable vide>) ]
    def       = new UtilityDefinition() ; def+0x10 = [ new UtilityBucket(utilities, <vide>) ]
    First( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(tilesC)), def, owner@+0x30 ), 1 )

TROIS lectures qui corrigent Sec.4 :

1. **`0x34 = 52 SwornProtector_AvoidAdjacentEnemies`, PAS `0x33`.** Cette fiche a ete ecrite sur
   `gqfc5mff6c`, ou `AttackTile` n'existait pas encore en 8 ; son insertion a decale de +1 les 73
   membres suivants d'`IdunBattle.Configuration.UtilityType` (meme decalage que `Damage` 34 -> 35,
   documente dans `operations/damage_utility.py`). `0x33 = 51` designe aujourd'hui
   **`RoyalGuard_AvoidAdjacentEnemies`** -- un homonyme quasi parfait, qui porte en plus la MEME
   cle BC (`AdjacentEnemy`) et la MEME valeur (-20). C'est exactement le regime ou un ordinal
   recopie ment en silence ; le port n'ecrit que le MEMBRE.
2. **`TestUnitProvider` est un mislabel ghidra.** La classe allouee (`DAT_18337e6d8`) est la MEME
   que celle que `DSLSelectors$$SortUnitsByDamageUtility` construit par
   `IdunBattleLogic.AI.Utilities.UtilityDefinition$$.ctor(this, 0x23)` : c'est un
   **`UtilityDefinition`**, dont le champ `+0x10` recoit le `UtilityBucket[1]`. Il n'y a pas
   d'enveloppe supplementaire.
3. **La feuille lit `get_UnitOrParent`, pas `case.unit`.**
   `SwornProtector_AvoidAdjacentEnemiesUtility.<EvaluateMovementInSteps>d__1$$MoveNext` =
   `Count( Enemies( Entity(case.get_UnitOrParent), AdjacentUnits(Entity(case.get_MovementTile), 1, 3), 3 ) )
   x GetUtilityValue("AdjacentEnemy")`. En regime SPAWN (`case.unit == null`) le sujet est donc le
   **PARENT** -- Creed. Son jumeau `RammingSpeed_MostAdjacentEnemies` lit `case.unit` et degrade a
   0 : **recopier sa garde `is_spawning` aurait rendu CETTE feuille inerte sur son unique
   call-site**, c'est-a-dire restaure le collapse qu'elle vient reparer.

Poids : `Utilities.Default.SwornProtector_AvoidAdjacentEnemies.AdjacentEnemy` = **-20** (cle
resolue par `probe_212_bc_key_literals.py`, SANS prefixe contrairement au `RAMMINGSPEED_` du
jumeau). Le signe NEGATIF est ce qui pose Kell du cote oppose a l'attaquant.

### La mesure, et sa contre-epreuve

`probe_120bis_spawn_tile.py` -- board `MC1_67`, seed 4242, Creed amene sur `(3,4)` (SIX voisins
jouables, meme geometrie que `test_sworn_protector_kell_live.py`), attaquant DEPLACE sur trois
voisins differents. Temoin = `git archive origin/master` (`a2fff7a4`) extrait en entier, joue sur
la MEME session et les MEMES trois montages :

| montage | temoin (collapse) | ce port | natif (live) |
|---|---|---|---|
| att (4,4) | `d = 1` | `d = 2` | `d = 2` |
| att (2,4) | `d = 1` | `d = 2` | `d = 2` |
| att (3,3) | `d = 2` | `d = 1` | `d = 1` |
| ACCORD | **0/3** | **3/3** | -- |

Le 3e montage est **INVERSE** : l'accord du port n'est pas un biais « toujours 2 », c'est bien le
TRI qui decide, montage par montage.

⚠ **DEUX gardes de mesure, et sans elles le probe aurait rendu un VERT sur un port faux.**
(a) La TUILE de Kell est rendue mais declaree **NON DISCRIMINANTE** : apres le `SwitchPosition`
elle vaut la tuile de DEPART de Creed des deux cotes, et elle est **egale meme sur le temoin qui se
trompe**. Un probe qui n'aurait garde qu'elle aurait valide n'importe quoi. (b) Un montage a moins
de 2 tuiles libres autour de Creed est ECARTE (regime degenere : le tri coincide avec
l'enumeration -- c'est ce qu'a rendu le premier jet, Creed etant sur un coin), et le probe REFUSE
de conclure si le natif rend la meme distance sur tous les montages.

### Cablage

Le noeud DSL `SortTilesByUtility` et l'accesseur `ctx.sort_tiles_by_utility` transportent desormais
une `utility_definition` batie a la main (le foyer `utilities/tile.py::sort_tiles_by_utility`
l'acceptait deja depuis #353-r1, mais aucun noeud ne savait l'exprimer). Parametre optionnel en fin
de signature : comportement INCHANGE pour tous les appelants existants. La feuille vit dans
`engine/utilities/sworn_protector.py`, qui s'inscrit lui-meme dans `UTILITY_BY_TYPE` (patron
`engine/utilities/move.py`) -- `engine/utilities/tile.py` etant le foyer d'une autre tranche en vol
au moment de la livraison, l'entree gagnerait a rejoindre le litteral quand ce foyer sera libre.

### ⚠ Un ROUGE PREEXISTANT de `master`, trouve en rejouant ce probe

`probe_120bis_execute_for_replaced_target.py` **etape 5** (`assert h.last.get("target") == creed`,
« cible re-resolue sans switch ») ECHOUE sur `origin/master` `a2fff7a4` **pur** : meme assertion,
meme valeur (`cible frappee=2`, `kell=None`), verifie sur l'arbre temoin extrait par `git archive`
AVANT toute edition. Ce n'est donc pas une regression de cette tranche, et il rend rouge
`tests/engine/runner/test_pre_unit_ability_fork_live.py::test_port_reproduces_replaced_target_offline`.
Non diagnostique ici (hors perimetre) -- signale pour attribution.
