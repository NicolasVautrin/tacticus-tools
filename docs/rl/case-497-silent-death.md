# #497 — `1068 SilentDeath` : une CHAINE de degat, pas un splash

**Etat : LIVRE.** Face COMBAT portee, confrontee LIVE bit-exact (topologie + degat coup par coup),
sur `rnca9r7q6c`. Porteur : `eldarJainZar` « Jain Zar » (Aeldari, HERO, dans le pool rank 17) ;
quatre autres porteurs sont npc (`eldarBossJainZar`, `...Camp`, `...LEG`, `...LHE`).

Avant : 1068 etait absente d'`ABILITY_CLASSES` -> la decision CHOISISSAIT le cast et l'execution
l'IGNORAIT (0 degat, 0 effet, aucune erreur). Le no-op silencieux, dans sa forme la plus couteuse :
l'ability fait **12 coups sur 4 unites** en jeu.

## 1. L'artefact natif

`IdunBattleLogic.Entities.Abilities.Active.Loki.SilentDeathAbility$$ExecuteBehaviour` construit son
arbre **par une BOUCLE C#** — c'est le seul de son module dans ce cas, et c'est ce qui en fait une
CHAINE :

    ennemis = DSLSelectors$$Cache( DSLSelectors$$Enemies( of = <DSLSelectors+0x48> Caster,
                                                         entities = <DSLSelectors+0x20> AllUnits,
                                                         selectionType = 3 ), 1 )
    amorce  = DSLBehaviors$$SetCache( ennemis )
    prev    = <DSLSelectors+0x60> Target ;  vus = [ prev ]
    b       = DSLBehaviors$$Nothing()  op_Addition  b__0( prev )
    for (i = 0 ; i < GetNumberConstant(0x11 = nrOfTargets) ; i++) :
        pool = DSLSelectors$$AdjacentUnits( prev, unique = 1, selectionType = 3 )  &  ennemis
        foreach (s in vus) : pool = pool op_Subtraction s
        pris = DSLSelectors$$Cache( DSLSelectors$$PickRandomly(pool, 1, 0, 0x7fffffff, 0), 1 )
        b    = b op_Addition b__0( pris ) ;  vus.Add(pris) ;  prev = pris
    AActiveAbility$$Execute( DSLBehaviors$$Group( amorce & b, DSLSelectors$$None(), 0x1d ), entities )

`b__0(cible)` (le lambda du `<>c__DisplayClass1_0`) est **UNE seule methode**, invoquee avec des
cibles differentes :
`AttackWithAttackDamage(Caster, cible, MinMaxDamage(abilityState), Nullable(GetDamageProfile()),
Get(GetNumberConstant(0x2f = nrOfHits)), AbilityOrEffect(this+0x10), <options VIDE>)`.

**Cinq lectures qui ne se devinent pas** — detail dans la docstring de module de
`engine/runner/abilities/aeldari.py` : (a) le pool part du **maillon precedent**, pas de la cible ;
(b) les selecteurs sont LAZY, donc le pick du maillon `i` s'evalue APRES les degats du maillon
`i-1` ; (c) le `SetCache` fige le camp adverse AVANT le premier coup ; (d) `vus` retranche TOUS les
deja-frappes, la cible primaire comprise ; (e) le degat est IDENTIQUE sur les 4 feuilles.

Config 1068 (BC **et** gameconfig, concordants) : `damageProfile = Piercing`, `nrOfHits = 3`,
`nrOfTargets = 3`, `attackRangeType = Melee`. i2 : « … dealing 3x Piercing Damage to it **and up to
3 additional enemies adjacent to each other** ». `nrOfTargets` compte les maillons **ADDITIONNELS**
-> cardinal maximal **1 + 3 = 4**.

`Group(..., 0x1d)` = `GroupType.DamageChain`, membre LU dans `data/symbols/<build>/frida/enums.tsv`
— et **confirme live** : la cascade du cast natif porte exactement un groupe 29.

## 2. Le ctor — forme PRESET STATIQUE COPIE

`SilentDeathAbility$$.ctor` n'appelle **aucun** `TargetingOptions$$.ctor` : il recopie les 0x40
octets du preset `<TargetingOptions statics>+0x40`, puis `AActiveAbility..ctor(this, &opts, 0)`.

| champ | source `TargetingOptions$$.cctor` | valeur |
|---|---|---|
| `isSelfCasting` | `*(statics+0x40)` | `0` |
| `range` | copie de `<TargetingRange statics+0x30>` | `RANGE_ADJACENT` |
| `forceMeleeTarget` | `*(statics+0x60)` | `1` = `RangedBool.False` |
| `Rules` | `*(statics+0x68)` | `0x4000` = `TargetIsEnemy` **seul** |
| 3e arg d'`AActiveAbility..ctor` | litteral | `0` = `AbilityAttackType.DirectTargetAttack` |

Le masque **migre** depuis `TARGETING_OPTIONS_UNPORTED` vers la classe du registre (contrat de
disjonction) ; apres rebase, le compteur `STATIC-COPY` du bloc passe de 9 a 8. Le ctor a ete
**relu**, pas recopie de l'entree heritee : deux lectures independantes, meme resultat.

La migration a un **cout de maintenance obligatoire, dans le meme commit**, et trois cliquets l'ont
impose (ils ont ROUGI, ils n'ont pas ete anticipes) :

* `tests/engine/test_433_r4_r2_r1_r2_ability_range_offline.py` — `POOL_ABILITIES_WITHOUT_COMBAT_CLASS`
  (« masque non lu : [1068] ») : la liste RETRECIT a chaque port, sa docstring le dit deja.
* `tests/engine/test_270r1_volet2_dict_keys_enum_offline.py` — le SNAPSHOT d'ordinaux
  (`SNAP_TARGETING_UNPORTED` + `test_cardinalites_du_volet`, 39 -> 38 cles). Il fige l'ordinal
  **ecrit au site** ; le site a change, la VALEUR non — et elle a ete reconfrontee au ctor relu.
* `tests/engine/runner/test_ability_registry_ratchet.py` — il a mordu sur un `0x4000` que le test
  neuf ecrivait en dur, corrige en `TR.TargetIsEnemy`.

## 3. Ce que la confrontation LIVE a mesure

`probe_497_silent_death.py` (nominal) et `--variantes` (4 generalisations). Montage : Jain Zar +
4-5 orks sur `MC1_67`, positions FORCEES par `--place`/`--a-place`, MT offline cale sur le MT live
(`dumpRng`) — sans ce calage `execute_ability_attack` SKIP le degat (repli defensif documente).

| scenario | chaine PORT | chaine NATIF | degat coup par coup | verdict |
|---|---|---|---|---|
| nominal (colonne 2, rangees 6→3) | `[81, 83, 85, 87]` | idem | `[2925,1336,1360] [959,994,1078] [1018,1015,1138] [1018,1171,1157]` | **bit-exact** |
| `branche` (pools de 3 puis 2) | `[81, 83, 87, 85]` | idem | egal | **bit-exact** |
| `cap` (5 ennemis alignes) | 4 frappes, le 5e jamais | idem | egal | **bit-exact** |
| `mort` (PV 3000, **4 morts**) | `[81, 83, 85, 87]` | idem | egal | **bit-exact** |
| `elevation` (marche 2→4) | `[81, 83, 85, 87]` | `[81]` | — | **DIVERGENT** à la livraison ; **ACCORD** depuis #515, cf. §4 |

Trois de ces mesures tranchent une question qu'aucune autre ne tranche :

* **`nominal` separe CHAINE et SPLASH.** Le 4e maillon est a **3 hex** de la cible primaire : un
  port bati sur le patron voisin du meme module (`HarvesterOfSouls` : ennemis adjacents A LA CIBLE)
  ne peut pas l'atteindre. C'etait la question binaire de la tranche.
* **`branche` separe « tirer » de « prendre le premier ».** L'ordre obtenu, `[81, 83, 87, 85]`,
  n'est PAS l'ordre des ids — un port qui prendrait toujours la tete du pool passerait sur le
  nominal (pools singleton) et echouerait ici.
* **`mort` n'est valable QUE parce que 4 unites meurent reellement.** Aux PV nominaux
  (8 000–12 000 contre ~4 500 de degat) **personne ne meurt** : l'accord y aurait ete un accord en
  regime degenere. Le temoin `morts` publie par le probe est ce qui l'interdit. Reponse mesuree :
  **la chaine traverse les cadavres**, des deux cotes.

Gate de ciblage : `ennemi -> 0`, `allie -> TargetIsEnemy`, `soi -> TargetIsEnemy`, et l'oracle natif
concorde (`abilityTargets.targets`, superset move-inclus, n'enumere que des ennemis).

## 4. Residu `#497-r1` — l'adjacence du RUNNER ignorait la porte d'elevation — **FERME (#515)**

**Ce n'etait pas un defaut de ce port ; c'etait un residu HERITE, deja nomme dans le code, que
cette tranche a rendu MESURABLE.** Il est **reparé** — detail : `docs/rl/case-515-adjacence-du-runner.md`.
Ce qui suit reste l'etat au moment de #497, et le §4bis dit ce qui a change.

`engine/dsl/base.py::_within` decide l'appartenance par `hexgeo.distance <= r`. Le natif, lui,
enumere la liste d'adjacence **STOCKEE** :
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` parcourt
`tile.ConnectivityComponent.Neighbours` puis applique `|dElev| < 2`. La couronne hex SUR-ATTEINT
donc la liste native des que le terrain saute une marche.

Mesure sur `MC1_67` (etage [6] du probe) : **18 aretes dirigees sur 316** sur-atteintes,
**11 tuiles** touchees. Effet sur 1068 : la variante `elevation` fait une chaine de **4** la ou le
natif s'arrete a **1** — 9 706 PV de degat fantome.

Deux faits qui rendent le residu actionnable :

1. **Le port a DEJA la primitive juste, et il l'utilise ailleurs.** `AdjacentTiles`
   (`engine/entities/selectors/tiles.py`, mirror d'`AdjacentTilesSelector$$Select`) passe par
   `Board.neighbours_native` ; `battle_query.is_adjacent` porte les deux etages (liste stockee +
   porte d'elevation) pour la face DECISION. Seule la voie UNITE du RUNNER (`_within`) ne les a pas.
   `_tile_enum_rank` lit deja `neighbours_native` — mais pour l'ORDRE seulement, et laisse en fin de
   liste les unites hors graphe au lieu de les EXCLURE.
2. **La reparation est monotone** : elle ne peut que RETIRER de la sur-atteinte, donc tout test qui
   passe aujourd'hui contre un oracle NATIF est dans une geometrie ou les deux coincident.

**Pourquoi cette tranche ne l'a PAS prise** : `_within` est le foyer de **294** call-sites
`AdjacentUnits`/`AdjacentEnemies`/`AdjacentFriends` dans `engine/` ; le flip demande une
re-validation de surface qu'une tranche mono-ability ne peut pas payer. A dispatcher avec son
propre budget de re-jeu.

**Aucun test n'est ecrit sur cette divergence** : un test qui l'ASSERTE figerait le bug. Elle vit
comme MESURE dans `probe_497_silent_death.py --variantes`.

### 4bis. Ce que #515 a change

`_within` branche desormais l'etage `order='adjacent'` (rayon 1) sur `_adjacent_tiles_native`, qui
lit la liste STOCKEE. La variante `elevation` est passee de `port [81,83,85,87]` / `natif [81]` a
**`[81]` des deux cotes** — meme montage, meme board, meme seed. Les quatre autres scenarios
restent bit-exacts. Le residu porte donc bien sur `_within`, et sur rien d'autre du port de 1068.

La divergence est maintenant GARDEE, dans le bon sens : `tests/engine/runner/
test_515_adjacence_elevation_live.py` (le montage `elevation` retourne, contre l'oracle natif) et
`test_515_adjacence_elevation_offline.py` (le foyer, sa contre-epreuve, son tri-etat, et la BORNE
— `order='surrounding'` n'a AUCUNE porte d'elevation et doit rester geometrique).

L'etage `[6]` du probe reste, mais il a change de role : il ne chiffre plus un ecart de PORT, il
chiffre une propriete du BOARD et sert de temoin de non-degenerescence (`sur_atteintes == 0` =
plateau plat = variante `elevation` sans portee).

## 5. Livrables

* `engine/runner/abilities/aeldari.py` — `SilentDeathAbility`, `silent_death_tree`,
  `_silent_death_attack`, `silent_death_profile`, `silent_death_num_targets`, `TARGETING_OPTIONS`.
* `engine/runner/abilities/handler.py` — entree au registre.
* `engine/runner/abilities/attack_type.py` — `DirectTargetAttack` (litteral transcrit).
* `engine/runner/abilities/targeting.py` — migration hors de `TARGETING_OPTIONS_UNPORTED`.
* `probe_497_silent_death.py` — la MESURE (nominal + 4 variantes + l'ecart d'adjacence).
* `tests/engine/runner/test_silent_death_live.py` — la GARDE (8 tests, 2 runners).

Cliquets rejoues verts : `probe_181` (0 manquante), `probe_120` etape 0,
`test_ability_registry_ratchet.py` (9 — il a **mordu** sur un `0x4000` ecrit en dur dans le test,
corrige en `TR.TargetIsEnemy`), `probe_313` (34 mirrors), `probe_429`, `probe_273 --only-scan`,
`probe_365`, `probe_455`. Audits REGENERES apres rebase (conflit sur un fichier GENERE : on
regenere, on ne fusionne pas) — `combat-ability-coverage` : PORTED **105 -> 106**, NO-OP
**70 -> 69**, `DAMAGE` **41 -> 40** ; `kit-coverage` : items manquants **92 -> 91**, Aeldari
**5 -> 4**.

**DEUX rouges PREEXISTANTS, non causes par cette tranche** :

1. `probe_486r15_declencheurs_tests.py` echoue sur
   `tests/engine/runner/test_489_fragstorm_grenade_launcher_offline.py` (« DECLARE TROP ETROIT :
   138 chemins »). Verifie par `git stash` : le rouge est identique sans aucune de mes
   modifications. Ce fichier declare une liste EXPLICITE de ~20 chemins ; les manquants listes
   (`board.py`, tout `engine/ai/`) n'ont aucun rapport avec #497.
2. `probe_433_r4_r2_r1_r2_r2_r1_r1_pool_masks.py` leve `KeyError: 1069` — il code en dur
   `WALK_ABILITY = 1069`, et #491 a retire 1069 de `TARGETING_OPTIONS_UNPORTED`. Verifie :
   `git show origin/master:.../targeting.py` ne porte deja plus l'entree. Meme forme de dette que
   celle que cette tranche vient de payer sur les deux tests ci-dessus — sauf qu'ici c'est un
   PROBE (hors banque de cliquets), donc rien ne l'a fait rougir au merge de #491.
