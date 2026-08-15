# #10005 — le foyer `scripts/python/rl_duel.py` : neuf résidus, six fermés, trois prémisses réfutées

Tranche du 2026-08-15, build **`t6dpr4k06g`** (session Frida 93), sur les neuf résidus ouverts qui
nomment `scripts/python/rl_duel.py` dans leur champ `FOYER:`. Ghidra servait encore l'ancien build
(`rnca9r7q6c`) : **aucun verdict de cette page ne repose sur du décompilé neuf** — tout se tranche
par le code Python, les métadonnées du build courant (`data/symbols/t6dpr4k06g/frida/*.tsv`, RPC
`classFields`) et le live.

| résidu | verdict | blocage AVANT | APRÈS |
|---|---|---|---|
| `#237-r1` | **FERMÉ** — correctif + garde | `aucun` | *(fermé)* |
| `#914-r1` | **FERMÉ** — correctif + garde, **foyer de la fiche FAUX** | `aucun` | *(fermé)* |
| `#419-r1-tr9-r5` | **PRÉMISSE RÉFUTÉE deux fois** — garde posée | `aucun` | *(fermé)* |
| `#605-r1` | **NON REPRODUIT** — 6 bras, les deux lectures éliminées | `aucun` | *(fermé)* |
| `#448-r3-r1-r1-r1` | **FERMÉ** — deux portes, pas une | `aucun` | *(fermé)* |
| `#449-r2-r4-r1` | **FERMÉ** — canal ambiant ; **+1 rouge de `master` éteint** | `seeding` | *(fermé)* |
| `#589-r1-r1-r2-r1-r2` | **DÉJÀ FERMÉ** — ligne restée au backlog | `aucun` | *(fermé)* |
| `#1044-r1` | **OUVERT** — prémisse confirmée, question ouverte tranchée | `aucun` | **`capteur`** |
| `#593` | **OUVERT** — chiffres re-dérivés, contrainte de façade établie | `aucun` | `aucun` |

---

## 1. `#237-r1` — l'état 3 d'une relique tenait en deux commandes, et rien ne le disait

**Prémisse VRAIE.** `--equip-relic` s'applique au BC **normalisé** (la pose doit suivre
`_normalize_and_extract_pool`, sans quoi `buildNormalizedBC` réécrit `TertiaryAbilityLevel = 50`),
donc un porteur absent du seed BC n'est dans aucun des deux BC et la commande sortait en `rc 2`.
Le `--equip-mythic` voisin, lui, augmentait le catalogue tout seul.

**Gisement** (gameconfig de `t6dpr4k06g`) : sur les 32 abilities de relique, **5** n'ont **aucun**
porteur au seed BC — `BladeOfTheAncestors`/`votanUthar`, `DawnBlade`/`tauFarsight`,
`TheArdentBlade`/`adeptCelestine`, `VolummsMasterArtifice`/`votanIronmaster`,
`WyrdmakersHelm`/`spaceWolfPriest` — et **9 porteurs sur 65** sont hors seed.

**Correctif** : injection catalogue AVANT la normalisation (pendant exact du bloc mythique), la
pose restant APRÈS. Plus `_diag_porteur_ecarte`, qui distingue « absent du catalogue » de « écarté
par `buildNormalizedBC` » — dans le second cas le message d'origine était **trompeur** (il demande
d'injecter un porteur qu'on vient d'injecter).

**Live** : `[relic] catalogue: +1 unites ['adeptCelestine']` puis
`EFFETS ACTIFS — u79 [adeptCelestine] <MOI>: TheArdentBlade`, en **une** commande. Contre-épreuve
avec le code d'avant : `rc 2`, message identique à la fiche.

## 2. `#914-r1` — le foyer écrit dans la fiche ne pouvait pas voir le problème

**Prémisse VRAIE, foyer FAUX.** La fiche nommait `rl_duel.py` + `catalog_inject.py`. Ni l'un ni
l'autre ne tient les **trois** termes nécessaires. Un seul site les voit :
`rl_collect_batch._normalize_and_extract_pool`, qui a le seed BC reçu **et** le BC rendu. Il couvre
donc aussi les seed BC écrits par un `json.dump` direct — ce que ni le balayage statique ni un
`[warn]` de `catalog_inject --out` (les pistes (b) et (c) de la fiche) n'auraient vu, alors que
**c'est ainsi qu'écrivaient les deux probes de #914**.

`CHAMPS_RECALCULES_PAR_NORMALISATION` = **16** champs **dérivés** de
`frida/hooks/features/normalize-bc/json-build.ts` (toutes ses écritures `u.<champ> = …`), sous
cliquet de bijection dans les deux sens.

**Live** : sur un seed BC patché à la main,
`Health=900000 -> 9539, RemainingHealth=900000 -> 9539` — le `~9539` de la fiche retrouvé au bit
près. Build témoin sans patch : **silence total**.

> **Ce qu'une mutation a appris.** Une quatrième condition (« l'unité est dans
> `result.normalized` »), posée pour éviter le faux positif du *carrier de summon*, a été
> **retirée** : la mutation qui la neutralise laissait la garde **intégralement verte**. Elle est
> redondante, et pour une raison lisible dans le TS — une unité `skipped` n'est pas modifiée du
> tout (les écritures suivent l'appel de formule, une levée saute au `catch`), donc sa valeur sort
> identique et le test d'écrasement la couvre déjà. Deuxième faux vert trouvé dans mes propres
> crans : le test du filtre par liste comparait `Shield` **identique** des deux côtés — il passait
> même en remplaçant le filtre par `list(u.keys())`.

## 3. `#419-r1-tr9-r5` — la prémisse était fausse, et sa re-qualification aussi

La fiche disait « `--unit-stat necroWarden:RemainingHealth=N` ne mord pas — 300 ressort à 2008 »,
puis se re-qualifiait en « **2008 est l'ARMURE** de `necroWarden`, relue par trois runners
indépendants ». **Les deux sont réfutées**, au même montage (board MC1_67, trois unités) :

* le BC envoyé à `initAndStart` porte `RemainingHealth = 300` pour `necroWarden` **comme pour ses
  deux témoins** (lu dans le state-file) — le patch **mord** ;
* `observeBattle` : `armor=0 / armorMax=0` — `2008` n'est pas son armure ;
* `necroWarden` sort à `hp=1154/8536` quand `astraBullgryn` et `tauAunShi` sortent à `300` ;
* **après un tour complet, `necroWarden` passe à `hp=2008`** — le nombre exact de la fiche, les
  deux témoins restant à `300`.

**Cause** : le trait `LivingMetal` (« Regenerates {[hpPct]}% of its max Health at the start of the
players' turn », `globalValues.traitVariables.livingMetalHp = 10`).
`1154 = 300 + round(8536 × 10 %)` et `2008 = 300 + 2 × 854`.

Ce n'est pas un défaut de l'outil mais un **piège de mesure**, de la famille de #342 (champ jamais
lu) et #914-r1 (champ recalculé) — et donc traité comme eux : `--unit-stat RemainingHealth|Health`
**avertit** quand la cible porte un trait régénérant. La liste est **dérivée** (description i2
`~/regenerat/i` + montant apparié dans `traitVariables`) : un seul trait répond, porté par **13**
entrées du seed BC.

## 4. `#605-r1` — six bras, tous à deux coups

La fiche mesurait, le 2026-08-10, qu'un porteur posé par `--place` n'émettait **qu'un** coup là où
le même porteur laissé à son SpawnPoint en émettait **deux**, et laissait ouvertes deux lectures :
(a) artefact de harnais, (b) canal natif positionnel.

`probe_605r1_place_vs_spawn.py`, sur `t6dpr4k06g` :

| bras | départ | cast depuis | d | coups |
|---|---|---|---|---|
| A SPAWN | (1,0) | (6,5) | 3 | **2** `[1352, 1599]` |
| B PLACE | (6,5) | (6,5) | 3 | **2** `[1689, 1999]` |
| C PLACE+ | (6,5) | (6,6) | 2 | **2** `[1352, 1599]` |
| D FICHE | (3,4) | (3,4) | 3 | **2** `[1126, 1333]` |
| E TEST | — | (1,0) | 2 | **2** `[1689, 1999]` |
| F TEST+PLACE | (3,4) | (3,4) | 3 | **2** `[1689, 1999]` |

D reprend la tuile **littérale** de la fiche ; F reprend en plus son **roster exact** (deux
porteurs du même `unitId`, deux cibles par `--a-place` — le montage de
`test_605_hellfire_shells_live.py`). Les bras A–C ne partageaient ni ce roster ni cette géométrie :
**ils n'auraient pas suffi à réfuter**, et c'est pour cela que D et F ont été ajoutés.

Les deux lectures sont donc **éliminées** dans ce régime. Ce qui varie d'un bras à l'autre est la
**magnitude**, pas le compte : les bras ayant consommé un déplacement partagent leurs rolls
(`[1352, 1599]`), les bras immobiles les leurs (`[1689, 1999]`) — c'est le flux RNG, et le
confondre avec un coup manquant est précisément le piège qu'un comptage d'events dissout.

> `hasMoved` ressort à `None` dans les six bras : `decisionView` ne publie pas ce champ. Le bras C
> établit néanmoins que le mouvement ne change pas le compte — ce qui re-confirme l'écartement de
> `RapidFire`.

**La prescription en tête de `test_605_hellfire_shells_live.py` est CONSERVÉE**, mais datée : la
cause de la mesure du 2026-08-10 reste inconnue, et rien ne dit qu'elle ne peut pas revenir. Elle
n'est plus un fait du build courant, et elle est désormais **rejouable** — c'est le probe qui la
refonde ou la lève, pas la relecture d'un paragraphe.

## 5. `#448-r3-r1-r1-r1` — il fallait DEUX portes, pas une

La fiche décrivait une porte : un registre de greffes **par runner** sur disque, relu par
`snapshot._declared_grafts` via `runner_label`. Elle est nécessaire — mais **pas suffisante**, et
la mesure l'a montré : dans le patron décrit, le processus qui **construit le runner** peut
n'avoir rien greffé lui-même (il ne fait que charger un BC déjà greffé), donc il ne publie **rien**.

Seconde porte, qui est la piste que la fiche nommait **en premier** : la marque portée par le seed
BC lui-même. Les **7** writers de seed BC estampent `declaredGrafts` dans le sidecar existant, et
`_load_seed_bc` **re-déclare** au chargement. Le sidecar porte désormais trois mécanismes (#375
épingles, #380 retenues, celui-ci) : `stamp_grafts` et `write_pins` se **préservent mutuellement**.

Le message du refus **nomme l'origine** : accuser « ce processus » quand la greffe vient d'ailleurs
envoie le lecteur dans le mauvais fichier — et c'est justement le régime où le greffeur est le plus
dur à retrouver.

**Live**, deux processus réels : `build --equip-relic` (runner 38) puis un processus qui n'a jamais
greffé → **REFUS**, avec l'origine correcte. Registre absent après `dispose`.

## 6. `#449-r2-r4-r1` — le blocage `seeding` ne tenait pas

**Prémisse VRAIE** : seuls `probe_449r2r4_spread_from_bc.py` et `probe_449r2r4r4_bc_damage_fields.py`
passent `damage_config`. Tout runner retombait donc sur le défaut dérivé de `data/seed-bc.json`.

**Blocage RÉFUTÉ.** `seeding` signifie « le substrat ne publie pas la donnée ». Ici le substrat la
publie très bien — c'est la BC elle-même, que le montage tient. Ce qui manquait était un canal
**entre deux processus du harnais**, pas une mesure absente du jeu. Même chaînon que #448 : le
**runner** est le seul terme commun, `load_state` ne recevant ni la BC ni le state-file.

**Live**, seed BC à `DamageSpreadPercentage = 7` : défaut dérivé de la seed = **20**,
`state.damage_spread_percentage` = **7**, spread résolu = **7**. Contre-témoin sans `--seed-bc` :
20 / 20 / 20.

**En prime, un rouge de `master` éteint** — trouvé en mesurant le rayon de souffle.
`test_449_r2_spread_face_combat_offline` échouait sur
`ancient_fury.py::execute_widened_normal_attack`, porte de variance arrivée avec #1050-r1 (PR
#1077) et jamais inscrite dans `EXPECTED_DEFAULT`. Le fichier fautif **et** le test sont identiques
à `origin/master` : le rouge préexistait. L'attestation est mécanique (`LU_BC` via
`resolve_spread_pct`) et n'a demandé **aucun décompilé** — ce qui comptait, Ghidra servant encore
l'ancien build.

## 7. `#589-r1-r1-r2-r1-r2` — une ligne de résidu déjà fermée

La ligne portait elle-même « ✅ CONFRONTÉ ET FERMÉ (#419-r7) ». Vérifié : le correctif
(`rl_duel._split_hors_json`) est en place, le cliquet
`test_589r1r1r2r1r2_union_non_dedupliquee_offline.py` passe (3 étages), et la mesure vit dans
`case-419r7-confrontation-des-trois-capteurs.md` §1. Rien d'ouvert — ligne retirée.

## 8. `#1044-r1` — prémisse confirmée, question ouverte tranchée : `AddUnitMessage` ne peut PAS

Les deux points laissés ouverts, tranchés **sans Ghidra** (métadonnées du build courant, RPC
`classFields`) :

**(a) Disposition.** `IdunBattle.Operations.AddUnitOptions` : 112 octets, 14 champs, `OverrideType`
(`Nullable\`1`) à **+0x8** dans la struct (+0x18 boxé). C'est **exactement** l'offset que la fiche
citait — prémisse confirmée au bit près sur le nouveau build.
`IdunBattle.Operations.UnitOverrideType` = `0=Hero, 1=NPC, 2=Summon`, relu dans `enums.tsv`.

> ⚠ **Homonyme** : le build porte aussi `IdunBattle.View.Game.AddUnitOptions` (40 octets). Viser
> celle-là donnerait une disposition entièrement fausse.
> ⚠ **Boxing** : `classFields` rend des offsets boxés (en-tête de 16 octets). L'offset de la fiche
> et celui du probe désignent le même champ.

**(b) La voie — et la réponse est NON.** `IdunBattle.Messages.AddUnitMessage` a **8** champs et ne
transporte que **deux** des 14 options (`IsBoss`, `OverrideStats`). `OverrideType` en est absent,
comme 11 autres. La voie qu'emprunte `rl_duel --a-place` (`buildAddUnitMessage`, ctor 4 arguments)
est donc **structurellement** incapable de porter l'option.

La seule signature qui accepte des `AddUnitOptions` complètes est
`Core.Services.OperationProcessor.AddUnit(unitId, unitFeetTileIds, playerId, spawnSource, options)` ;
la seule fabrique non triviale d'options est `SpawnUnitBehaviour$$GetAddUnitOptions` (chemin
SUMMON). **Aucun RPC du harnais n'expose ni l'une ni l'autre.**

⇒ **BLOCAGE `aucun` → `capteur`.** Porter `UnitOverrideType` exige un RPC neuf dans
`frida/hooks/`, donc une fenêtre de reinject. Aucun code hooks n'est livré ici.

**NON RE-VÉRIFIÉ, et dit comme tel** : le corps d'`AddUnitTypeTraits` (« quand `OverrideType` a une
valeur, elle décide ») reste **cité** de la fiche — Ghidra sert encore `rnca9r7q6c`.

## 9. `#593` — chiffres re-dérivés, et une observation que la fiche n'avait pas

`probe_593_rl_duel_surface.py`. **Aucun** chiffre de la fiche ne tient encore :

| | fiche (2026-08-08) | mesure (2026-08-15) |
|---|---|---|
| fonctions top-level | 72 | **76** |
| `cmd_build` | 523 lignes | **643** (20 % du fichier) |
| fichiers qui CITENT | 780 | **1032** |
| fichiers qui l'IMPORTENT | **12** | **40** |

Le chiffre qui commande la difficulté — « 12 l'importent comme MODULE » — est périmé d'un facteur
**3,3**.

**Ce que la fiche ne mesurait pas**, et qui décide de la faisabilité : **quels symboles** les
importeurs lient. Réponse : **21 distincts, dont 16 privés**. Les plus liés :
`main` (22), `_resolve_session` (10), `_load_seed_bc` (10), `_rpc` (8), `_load_board_dump` (7).

**Observation neuve** : **11 des 21** ne sont même pas définis dans `rl_duel.py` — ce sont des
**re-exports** de `rl_collect_batch` (`_rpc`, `_load_seed_bc`, `_resolve_session`,
`_normalize_and_extract_pool`, `_patch_predefined_units`, `_spawn_points_by_twpi`,
`PLAYER_ID_HUMAN`, `_load_board_dump`…). **`rl_duel.py` est déjà une façade de fait pour
`rl_collect_batch`**, sans que ce soit écrit nulle part. Un découpage n'a donc pas à *inventer* une
façade : il doit **reconnaître celle qui existe** et la déclarer.

Corollaire de risque : ces re-exports sont en **forme A**, donc un
`monkeypatch.setattr("rl_duel._rpc", …)` mord sur `rl_duel` et **pas** sur `rl_collect_batch` —
exactement le piège #485-r1-r1, déjà armé dans l'arbre.

**Le refactor n'est PAS fait**, et c'est un choix motivé : la fiche elle-même prescrit de ne pas
ouvrir ce fichier pendant une campagne de portage, le rayon est le plus grand du dépôt (1032
fichiers), et cette tranche même y a livré quatre correctifs — un découpage simultané aurait
conflicté avec ses propres PR. Le résidu reste ouvert, mais il est désormais **chiffré et
instrumenté** : le probe rend la liste exacte à re-exporter.

---

## Ce qui n'est PAS couvert

* Le **corps** d'`AddUnitTypeTraits` (#1044-r1) n'a pas été relu : Ghidra sert encore
  `rnca9r7q6c`. Les métadonnées, elles, sont du build courant.
* La **cause** de la mesure du 2026-08-10 de #605-r1 reste inconnue — seule sa non-reproduction est
  établie, sur six bras.
* Le **découpage** de #593 n'est pas fait ; seule sa contrainte est mesurée.
* Le garde de #914-r1 compare au seed BC **de référence** : une unité injectée par
  `catalog_inject.augment` est absente de cette référence, donc **ignorée** (on ne sait rien de ce
  qu'elle « aurait dû » valoir). Un patch sur une telle unité n'est pas signalé.
* Le canal de #449-r2-r4-r1 publie **`Damage` seulement**. `Targeting` (#444) relève du même
  chaînon et le mécanisme est prêt à l'accueillir (`BC_SECTIONS_PUBLIEES`), mais rien n'est publié
  ni lu pour lui — publier une section que personne ne lit fabriquerait du code mort à l'air de
  canal.
* Les tests **live** rejoués l'ont été sur un périmètre ciblé (reliques, dégât, spread) : la suite
  complète n'a pas été jouée.
