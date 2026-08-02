# case-337 -- les 47 `CITE_A_QUALIFIER` de `DSLTriggers`, tranchees

**Tache d'ATTESTATION, pas de portage.** Rien n'a ete porte. Perimetre : la famille `DSLTriggers`
(165 primitives), dont **47** sortaient `CITE_A_QUALIFIER` de `probe_326_dsl_port_matching.py` --
ni portees, ni absentes : l'aveu que l'outil ne savait pas attribuer. Elles sont desormais **0**.

| | avant | apres |
|---|---:|---:|
| `DSLTriggers` `CITE_A_QUALIFIER` | 47 | **0** |
| toutes familles `CITE_A_QUALIFIER` | 104 | **37** |
| porte atteste (toutes familles) | 197 | **261 / 613** |

(Le doc genere partait de 46/102/197 : `master` avait bouge entre-temps, et rebouge apres rebase.
Re-deriver, ne pas citer -- `probe_326_dsl_primitive_inventory` -> `_port_matching` ->
`_ability_reachability` -> `_dsl_join --p1 docs/rl/dsl-usage/dsl-usage-edges.tsv`.)

## Verdict : 43 PORTEES, 4 NON PORTEES

Les quatre **NON PORTEES** sont des mentions documentaires CONFIRMEES par lecture, pas des
silences -- elles portent une ligne d'attestation avec leur motif :

| primitive | pourquoi la citation n'est qu'une mention |
|---|---|
| `Direct` | **piege d'homonymie entre familles** : `DSLTriggers$$Direct(bool)` rend le TRIGGER CONSTANT cache par `DSLTriggers$$.ctor` (`+0x40` vrai / `+0x48` `Not(vrai)`), pas le noeud VALEUR `DSLFormulas$$Direct` que porte `Const`. Levier propre non nul, mais l'action serait un noeud neuf. |
| `ActorHasTriggeredAbility` | cite pour NOMMER le producteur du `triggerType = Custom` (`AdaptiveStrategyAbility`, active 1005), hors `ABILITY_CLASSES`. |
| `IsFirstHitGroupInAttack` | frere de `IsFirstHitInSeries` sur `AbilityEntities+0x118` (contre `+0x110`) -- le port le dit deja « NON porte ». |
| `IsInTeamSynapseRange` | face CIBLAGE d'AlphaWarrior (`GetDynamicInvalidTargetReason`), hors `ExecuteBehaviour` -- residu deja nomme, l'IA offline est SUR-PERMISSIVE. |

Les 43 autres sont portees. La raison pour laquelle l'heuristique les ratait TOUTES est structurelle
et vaut d'etre retenue : **`DSLTriggers` est la famille des PREDICATS, et la doctrine du port les
COLLAPSE imperativement dans un `matches()` / un gate.** Aucun rapprochement lexical ne peut relier
`IdunBattleLogic.Entities.DSLTriggers$$TargetIsOverkilled` a `if ev.overkill:` de `final_justice.py`.

Trois sont PORTEES AVEC ECART, nomme :

* `IsDefeatedByMeleeAttack` -- branche `IsDead` mirroree, marqueur « MELEE » approxime
  POSITIONNELLEMENT (`_is_ranged_position`) faute de canal natif sur `On(UnitDeath)` ;
* `TileHasTriggeredAbility` -- mirror structurel qui rend **toujours False** : la table
  `TriggeredAbilityType -> tileDefId` vit dans les assets Unity de tuile, hors gameconfig ;
* `OnOwnerSpecificAbilityInit` -- COLLAPSE assume : la pose est SEEDEE au spawn
  (`ABILITY_INIT_OWNER_EFFECTS`) au lieu d'emettre un vecteur `On(49)`.

## Comment le verdict est RE-DERIVABLE

**1. Deux corrections systematiques de l'heuristique** (`probe_326_dsl_port_matching.py`) --
elles ferment aussi **21 items des autres familles**, mesure :

* `_norm_ident` : l'homonymie se lit modulo casse, separateurs et prefixe d'accesseur C#. Ferme
  d'un coup les rangs 1/3/5 du classement par levier (`get_OwnerIsCaster` <-> `OwnerIsCaster`,
  128 abilities / 104 confrontables), `IsMechanical` <-> `is_mechanical`, et tous les porteurs
  snake_case (`AbilityHasAttackType` <-> `ability_has_attack_type`). La condition « l'export CITE
  la primitive » est INCHANGEE : la normalisation n'assouplit que le premier des deux signaux.
* `_family_ok` : le build a eclate `DSLFactory` en quatre classes-factory, mais l'index de
  citations est keye par NOM DE METHODE. Les 14 citations de `DSLFormulas$$Direct` etaient donc
  comptees aussi pour `DSLTriggers$$Direct`. Filtre applique aux seuls noms portes par PLUSIEURS
  familles ; l'orthographe heritee `DSLFactory` reste acceptee partout (ambigue par construction).

Diff item par item contre `origin/master` : **68 changements, 0 regression** (aucun verdict
`PORTE*` n'est retrograde ; les 68 partent tous de `CITE_A_QUALIFIER`).

**2. Une table d'attestation** -- `docs/rl/dsl-port-attestations.tsv`, 31 lignes, chacune issue
d'une lecture (decompile natif + code du port). Quatre cliquets FATAUX a chaque run : symbole
present dans le vocabulaire du build, fichier porteur existant, **ancre** (nom de `class`/`def`/
constante, jamais un numero de ligne) resolue, et le fichier doit CITER la primitive. Une
attestation ne s'applique QUE sur un verdict non atteste -- elle ne peut donc jamais degrader une
mesure qui tient toute seule ; le probe imprime les lignes devenues redondantes.

Garde : `scripts/python/tests/test_337_dsl_triggers_attestation_offline.py` (11 tests, offline,
auto-portants) -- dont le cliquet de livraison « `DSLTriggers` ne contient plus aucun
`CITE_A_QUALIFIER` », qui rejoue la chaine sur un inventaire re-derive des tables versionnees.

## Ce qui n'est PAS couvert

* **Aucune confrontation live** : la tache ne modifie aucun code de `engine/**` (seulement de
  l'outillage de mesure et de la doc), et le host Frida etait injoignable pendant le run
  (`127.0.0.1:8787` refuse). Rien ici ne change un observable de bataille.
* **Les `CITE_A_QUALIFIER` restants** sont hors perimetre -- le meme travail reste a faire, et le
  mecanisme est pret. Compte RE-DERIVE le 2026-08-01, attestations appliquees : **44** au total
  (`DSLSelectors` 16, `DSLBehaviors` 14, `DSLFormulas` 12, `DSLFactory` 2, `DSLTriggers` **0**).
  Ces chiffres MONTENT au fil des ports -- mesure : **43 puis 44 en DEUX merges le meme jour**
  (#436 a ajoute une citation `DSLSelectors`). Les re-deriver, jamais citer cette ligne.

  **La re-derivation tient en DEUX commandes, et sauter la premiere ECHOUE** (`FileNotFoundError`,
  rc=1) : le matching lit `logs/326_dsl_primitives_native.tsv`, qui est une **SORTIE** du probe
  d'inventaire, donc absente d'un checkout FRAIS (mesure #381-r4). Depuis la racine du depot :

  ```
  python scripts/python/probe_326_dsl_primitive_inventory.py          # ecrit logs/326_dsl_*.tsv
  python scripts/python/probe_326_dsl_port_matching.py --attestations <CHEMIN ABSOLU de la table>
  ```

  ⚠ Le chemin d'attestations doit etre **ABSOLU** : un chemin relatif est joint a la racine du
  depot par l'appelant, donc un relatif plausible resout HORS du depot -- et le probe rendait alors
  un balayage complet SANS AUCUNE attestation. Il LEVE desormais au lieu de rendre `{}` en silence.
* **`DSLTriggers$$Not`** reste `PORTE_ARTEFACT_AUTRE` (verdict anterieur, hors des 47 ; levier
  mesure a zero).
* **Le backlog SEC de la famille est INCHANGE** -- ces primitives etaient deja `NON_PORTE` avant
  #337, et le restent : `OnDeath` (8 abilities confrontables),
  `CurrentAttackDamageProfilesContain` (6), `HasRarity` (6), `IsNormalUnit` (6),
  `get_OwnerOrOwnerTileIsTarget` (6). (`DamageProfileIs` y figurait : c'etait un FAUX NEGATIF de
  l'outil, tranche depuis -- cf. #392 ci-dessous.)

## Suite #392 / #393 / #433 -- CINQ primitives, meme mecanisme

Le cliquet de livraison a rougi QUATRE fois depuis #337, sur CINQ primitives que le port CITE sans
que l'outil sache les attribuer. La forme est identique et vaut d'etre retenue : **une PR qui
ajoute une CITATION d'artefact natif dans `engine/**` peut faire basculer une primitive de
`NON_PORTE` (aucune trace) a `CITE_A_QUALIFIER`** -- sans rien casser, et sans que son auteur le
voie, puisque chaque PR est verte a SA base. Le cliquet est le seul endroit ou ca se voit.

| primitive | PR qui l'a fait basculer | verdict apres RE |
|---|---|---|
| `DamageProfileIs` | `635a3431` (#372, DefenderOfTheGreaterGood) | `PORTE_HORS_FACADE` -- cf. ci-dessous |
| `IsEffectTarget` | #418 (`1014 CamoCloak_DmgReduction`) | `PORTE_HORS_FACADE` -- les 2 ecarts de `#418-r1` sont FERMES (`case-418-r1-is-effect-target.md`) : geometrie indexee PAR effectType, et le regime << apres deplacement, avant refresh >> ne diverge pas |
| `HasBlockedThisTurn` | #426 (`1227 HarlequinsPanoply`) | `PORTE_HORS_FACADE` -- cf. §#393 |
| `HasTile` | #448-r2b (`1140 StormboyzStrike_TeleportingIn`) | `PORTE_HORS_FACADE` -- cf. §#433 |
| `IsAdjacentTiles` | #448-r2d (`1573 TitanhammerSquad_TeleportingIn`) | `PORTE_HORS_FACADE` -- cf. §#433 ; le residu `#433-r1` est FERME (`case-433-r1-identite-adjacence.md`) |

Dans les CINQ cas, le `NON_PORTE` d'avant etait un FAUX NEGATIF : les primitives etaient portees,
collapsees en imperatif, et invisibles a toute heuristique de nom. **Le taux est desormais de 5/5 :
sur cette famille, un `NON_PORTE` qui BASCULE en `CITE_A_QUALIFIER` n'a jamais signifie « absent ».**

### `DamageProfileIs`, la 166e

Le cliquet de livraison a ROUGI sur `master` le 2026-08-01 : `['DamageProfileIs']`. Il a fait
exactement son travail. Bascule datee : `635a3431` (#372, 2026-07-31 19:33, apres le `185a4ed1`
de #337) introduit `IdunBattle.Entities.Triggers.DamageProfileIsTrigger$$IsMatchingDamageProfileInEntities`
dans `engine/entities/effects/loki/hits.py` -- **la seule citation captable** de la primitive. Elle
fait passer le verdict de `NON_PORTE` (aucune trace) a `CITE_A_QUALIFIER` (citee, porteur non
attribuable : aucun fichier ni classe du port ne s'appelle `DamageProfileIs*`).

Verdict de la RE : **PORTE_HORS_FACADE**. Le `NON_PORTE` d'avant etait un faux negatif -- la
primitive est portee sur ~30 sites, tous collapses en gates imperatifs.

* Les **trois** surcharges de `IdunBattleLogic.Entities.DSLTriggers$$DamageProfileIs` (scalaire,
  `Nullable<T>`, tableau) passent `attacker = defender = NULL` au `DamageProfileIsTrigger$$.ctor`
  (`+0x20`/`+0x28`). Donc `DamageProfileIsTrigger$$ShouldTrigger` prend **toujours** la branche
  `IsMatchingDamageProfileInEntities` : lecture d'`AbilityEntities+0xbc`
  (`Nullable<DamageProfileType>`) comparee au tableau `+0x30`, `HasValue == false` -> **FAUX**.
  La branche `IsMatchingDamageProfileInWeapons` (arme resolue par le slot virtuel `0xaf` de
  `battleQuery`) est **morte depuis la factory** -- seule une construction directe du trigger
  l'atteindrait.
* La surcharge `Nullable` rend en plus le trigger CONSTANT VRAI `DSLTriggers+0x40` quand le profil
  est absent (le meme slot que `DSLTriggers$$Direct(true)`).
* Port : le canal `damage_profile: Optional[str]` threade par `damage_model.attacker_modifiers` /
  `defender_modifiers`, collapse dans chaque gate d'effet. Ancre retenue :
  `TerminatorArmourReduceDmgEffect` -- le seul port de la surcharge TABLEAU sous `NOT`
  (`OwnerIsTarget & NOT DamageProfileIs(terminatorArmourExcludedDmgProfiles)`), et il porte
  correctement le cas nul : `if damage_profile and damage_profile in _terminator_excluded_profiles()`
  -> profil absent = predicat faux = reduction appliquee, exactement le `HasValue` natif.
* Apres desambiguisation de famille, `DSLTriggers$$Direct` tombe a **1 ability / 1 confrontable** :
  les 149/101 du classement appartiennent a `DSLFormulas$$Direct`, pas a lui.

## #393 -- `HasBlockedThisTurn`, la 3e bascule

Le cliquet a rougi sur `master` le 2026-08-01 : `['HasBlockedThisTurn']`. Bascule datee : **#426**
(`1227 HarlequinsPanoply`) introduit `engine/runner/operations/triggers/loki/harlequins_panoply.py`
et le bloc `blocks_made_this_turn` de `engine/runner/components.py`, dont les docstrings citent la
primitive -- premiere trace captable, donc `NON_PORTE` -> `CITE_A_QUALIFIER`.

**Verdict : `PORTE_HORS_FACADE`.** Le decompile ne laisse aucune marge :

* `IdunBattleLogic.Entities.DSLTriggers$$HasBlockedThisTurn(unit)` a **deux appels et rien
  d'autre** : `AmountIsGreaterThanZero(DSLFormulas$$TimesBlockedThisTurn(unit))`.
* **UN SEUL consommateur natif**, mesure par xref -- `IdunBattleLogic.Entities.Abilities.Triggered.
  Loki.HarlequinsPanoplyAbility$$CreateTrigger`, qui lui passe `DSLSelectors+0x60` = Target (les
  deux autres xrefs sont des entrees DATA de metadata). C'est ce qui distingue ce cas d'
  `IsEffectTarget` et de ses **6 constructeurs natifs** (`case-418-r1-is-effect-target.md`, ou la
  couverture partielle a fini par livrer un vrai bug) : ici il n'y a **rien a decouvrir**, la
  primitive est MONO-CONSOMMATEUR, donc l'attestation ne peut pas etre partielle par construction.
* Port : le gate `if _blocks_made_this_turn(state, self.owner_id) > 0: return False` de
  `HarlequinsPanoplyAbility.matches` -- le `> 0` EST l'`AmountIsGreaterThanZero`. Sur ce vecteur
  `owner == target`, donc `self.owner_id` est bien le `Target@+0x60` natif.
* La chaine de donnees est mirroree des **trois** cotes, et c'est ce qui rend le verdict solide
  plutot que nominal :

  | | natif | port |
  |---|---|---|
  | ECRITURE | `ActorStatisticsComponent$$RegisterBlockMade` (`+0x8c += 1`), poussee par `ADamageOperation$$RegisterBlocks` que `AttackDamageOperation$$ExecuteHits` appelle **au retour** d'`ExecuteHit` | `register_block_made`, appelee par `HarlequinsPanoplyHitInterceptor.on_blocked` **apres** l'evenement -- c'est cet ORDRE qui rend le predicat FAUX au premier coup bloque du tour, donc le gate `NOT` VRAI |
  | RESET | `ActorStatisticsComponent$$ResetBlocksMadeThisTurn` (`+0x8c = 0`), 3e instruction de la sequence de `StartTurnOperation$$ResetUnit` -- corps **INLINE** dans `StartTurnOperation$$Execute`, son unique site (aucun appel direct) | `operations/turnflow.py`, meme sequence, meme portee |
  | LECTURE | `TimesBlockedThisTurnFormula$$Calculate` -> `+0x8c` | `_blocks_made_this_turn` |

### `#393-r1` -- ARBITRE ET FERME (2026-08-01)

**Le perimetre est elargi a DEUX familles, avec des regimes DISTINCTS.** `test_337` ne declare plus
`fams == {"DSLTriggers"}` mais un litteral nomme `PERIMETRE_ATTESTATIONS = {"DSLTriggers",
"DSLFormulas"}`, teste en INCLUSION (`fams <= perimetre`, plus `"DSLTriggers" in fams` pour qu'une
table videe ne passe pas). `DSLTriggers` garde son cliquet de COMPLETUDE (165/165, 0
`CITE_A_QUALIFIER`) ; `DSLFormulas` entre en famille PARTIELLE, attestations a la carte, SANS
cliquet de completude -- une primitive `DSLFormulas` non attestee reste `CITE_A_QUALIFIER`, ce qui
est l'aveu honnete que l'outil ne sait pas l'attribuer, pas un verdict.

`DSLFormulas$$TimesBlockedThisTurn` est donc inscrite : **`PORTE_HORS_FACADE`**, ancre
`harlequins_panoply.py:_blocks_made_this_turn`. Verifie au decompile ce jour : son unique appelant
natif (xref `UNCONDITIONAL_CALL`) est `DSLTriggers$$HasBlockedThisTurn`, et
`TimesBlockedThisTurnFormula$$Calculate` resout le selecteur puis rend `+0x8c`.

**L'ecart de mirror joint est CORRIGE** : `ActorStatisticsComponent$$RegisterBlockMade` incremente
**deux** compteurs (`+0x8c` ce tour, `+0x88` la bataille) et le port n'en mirrorait qu'un. Le champ
`blocks_made_this_battle` existe desormais (`UnitComponent`), pousse par `register_block_made`, et
n'est PAS remis a zero au turn-start -- `ResetBlocksMadeThisTurn` n'ecrit que `+0x8c` (lu au
decompile). Aucun lecteur porte (seul `BattleStatisticQuery$$GetTotalBlocksMadeByUnit` le
consomme, cote statistiques de fin de bataille) : meme statut que `tiles_moved_this_battle`, ecrit
pour rester le mirror exact du `+=` double. Garde :
`test_harlequins_panoply_live.py::test_only_the_first_block_of_the_turn_arms_it`.

**Trouve en marge, et corrige** : `probe_326_dsl_port_matching.py` rendait `{}` en SILENCE quand la
table d'attestation etait introuvable, et son `--attestations` RELATIF est joint a la racine du
depot -- un chemin relatif plausible resolvait donc hors du depot et produisait un balayage complet
SANS AUCUNE attestation, lu comme une mesure (77 `CITE_A_QUALIFIER` au lieu de 43). La table etant
versionnee, son absence est toujours une erreur d'invocation : le probe LEVE desormais, et imprime
le chemin RESOLU au lieu de l'argument brut.

## #433 -- `HasTile` et `IsAdjacentTiles`, les 4e et 5e bascules (2026-08-01)

Le cliquet a rougi sur `master` avec **DEUX** primitives d'un coup :
`['HasTile', 'IsAdjacentTiles']` (1 failed / 10 passed sur `f7df861e`). Bascules datees : les deux
merges de la famille `ATeleportingEffect` -- **#448-r2b** (`1140 StormboyzStrike_TeleportingIn`,
premiere citation captable de `DSLTriggers$$HasTile`) et **#448-r2d**
(`1573 TitanhammerSquad_TeleportingIn`, premiere citation captable d'`IsAdjacentTilesTrigger`).
Verdicts : **`PORTE_HORS_FACADE` tous les deux** -- 5/5 pour le taux ci-dessus.

### `HasTile` : le slot 12 EST `SelectTile`, et les DEUX consommateurs sont portes

`IdunBattle.Entities.Triggers.HasTileTrigger$$ShouldTrigger` invoque le **slot de vtable 12** du
selecteur `+0x10` et rend `resultat != null` -- rien d'autre. Ce slot est
`IdunBattle.DSL.TargetsSelector$$SelectTile`, LU : il resout la selection, l'itere, et rend la
PREMIERE entite qui EST une tuile (`EntityExtensions$$IsTile`), sinon la
`EntityExtensions$$GetMainTile` d'une unite ou d'un pied (`IsUnit | IsUnitFoot`) ; enumeration
epuisee -> `null`. Le predicat est donc << le selecteur designe-t-il une TUILE >>, pas << la
selection est-elle non vide >>.

L'identification du slot 12 n'est PAS une inference de nom : elle est recoupee par une **seconde
source independante**. `IdunBattle.Entities.Triggers.TileHasTriggeredAbilityTrigger$$ShouldTrigger`
invoque ce meme slot 12 sur son unique selecteur, teste le resultat non nul, et le passe a
`IdunBattle.Entities.UnitExtensions$$HasTriggeredAbility` -- le slot rend donc **UNE entite**, en
domaine TUILE. Recherche litterale sur le motif d'appel : **9** fonctions du binaire l'utilisent,
toutes en domaine tuile singulier (`TileBehindTargetFromSourceDirectionSelector$$Select`,
`MinPathLengthFormula$$Calculate`, `TilesInPathSelector$$Select`, ...). A comparer aux trois autres
slots lus sur la meme classe : **0** et **10** rendent des collections (elles sont ENUMEREES par
`XContainsYTrigger` et `IsAdjacentTilesTrigger`), **1** rend une entite unique.

`DSLTriggers$$HasTile` n'a que **DEUX** xrefs `UNCONDITIONAL_CALL` (les deux autres sont des
entrees DATA de metadata), et les deux sont portees :

| consommateur natif | arbre | porteur du port |
|---|---|---|
| `IdunBattle.Entities.Effects.Loki.ATeleportingEffect$$CreateHandleTriggerAbilitiesInternal` (T3) | `On(0x28 UnitFinishedTurn) & OwnerIsActor & HasTile(Owner) & <vslot 0x738>` | `teleporting_in.py:ATeleportingRemoveOnUnitFinishedTurn._event_gate` -- `bool(get_unit_feet(state, owner))` |
| `IdunBattleLogic.Entities.Abilities.Triggered.Loki.Camouflage_HitReductionEffect$$CreateEffectHitsBonusForAttack` | `HasTile(TilesWithTriggeredAbility(Tiles(Target), 0x39 = 57 DryBushFireSpread))` | `entities/effects/loki/hits.py:CamouflageHitReductionEffect` -- le flag `defender_on_cover`, branche `-3` << Tall Grass >> |

Le premier est LOAD-BEARING et son contre-bras existe deja au port : `1140` est le seul des quatre
poseurs de la famille dont le `CreateBehaviour` appelle `RemoveUnitFromItsTiles`, donc le seul pour
lequel `HasTile(Owner)` est FAUX (cf. `StormboyzStrikeTeleportingInRemoveOnUnitFinishedTurn`).

### `IsAdjacentTiles` : mono-consommateur, porte, et PARTIEL sur un court-circuit

UNIQUE xref `UNCONDITIONAL_CALL` : `IdunBattle.Entities.Effects.Loki.TitanhammerSquad_Teleporting
InEffect$$GetCustomMovingEffectCondition` (vslot 0x748), bras DROIT du `op_BitwiseOr`. Porte par
`teleporting_in.py:_TitanhammerSquadTargetTileCondition._custom_moving_condition`.

L'asymetrie de resolution etablie par #448-r2d est **re-verifiee ici, au decompile** :
`IsAdjacentTilesTrigger$$ShouldTrigger` resout ses DEUX selecteurs (`+0x18`, `+0x20`) par le MEME
**slot 10** (liste de tuiles) et double-boucle, la ou `XContainsYTrigger$$ShouldTrigger` reduit son
2e operande a UNE entite par le **slot 1** puis compare les `Id`.

**Residu `#433-r1`, trouve en descendant la chaine -- FERME, detail dans
`case-433-r1-identite-adjacence.md`** : le ctor recoit en 3e argument le `query` =
`<ctx DSL>+0x10 -> +0x28`, dont le slot `0x60` est
`IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` -> `IdunBattle.Core.Services.
MovementUtil$$AreTilesAdjacent`. Sa surcharge SCALAIRE rend `(abs(elev1 - elev2) < 2) & b`, avec
`b = 1` par **COURT-CIRCUIT si `tile1 == tile2`**, sinon `ConnectivityComponent$$IsNeighbour`. Le
port lisait `board.neighbours(dest)` NU sur ce bras : il ratait les DEUX termes foldes.

Ce que la fermeture apprend, et qui n'etait pas vu ici :

* **le terme qui MORD n'est pas celui qu'on avait nomme.** L'identite y est SANS OBJET a
  cardinalite 1 (le bras `Contains` couvre deja `dest == marked[0]`) ; c'est la porte d'ELEVATION,
  perdue par le meme `board.neighbours`, qui discrimine -- **695 des 779** boards du depot portent
  une paire VOISINE a `|dElev| >= 2`. Confronte LIVE sur `MC1_67`/777 : le natif ne pose AUCUN
  `1574` sur une destination voisine a `|dElev| = 2`, le port mute en pose un.
* **le residu d'ORDRE de #448-r2d tombe AVEC lui**, par consequence : `AreTilesAdjacent(t, t)` etant
  vrai, `Contains(X, marked[0])` IMPLIQUE `IsAdjacentTiles(X, marked)` -- le premier bras est
  SUBSUME par le second cote natif aussi, et l'ordre d'enumeration ne decide plus rien, a toute
  cardinalite. Il n'etait donc pas protege par << une seule marque posee >> : il ne l'est plus par
  rien, ce qui est mieux.

### Le point de MECANISME : ce rouge n'a AUCUN porteur, et c'est la 4e fois

Mesure, pas impression. ⚠ **Etat RE-MESURE APRES REBASE** : #430 (PR #471) a ete mergee pendant
cette tranche et a livre `scripts/ratchets.ps1`, la banque EXECUTABLE des cliquets. Le constat qui
suit vaut donc contre l'artefact, plus contre une prose recopiee.

* **`test_337` n'est PAS dans la banque** : `pwsh scripts/ratchets.ps1 -List` rend **19** entrees,
  aucune ne le porte. Avant #430 il n'etait dans aucune des compositions qui circulaient non plus
  (le CLAUDE.md en nommait 4, toutes des PROBES) -- c'est le constat de `#427-r1`.
* `probe_326_dsl_port_matching.py`, lui, **rend `rc 0` meme avec des `CITE_A_QUALIFIER`** : l'y
  ajouter ne rougirait pas. Le SEUL artefact executable qui rougit sur ce gisement est `test_337`.
* Consequence mesuree : le rouge de #393 a ete vu par un orchestrateur, celui de #418-r1 a ete
  CONSTATE par un solveur qui l'a documente et laisse (<< ROUGE, et il l'etait deja sur la base >>,
  `case-418-r1` §6), et celui-ci l'a ete par un orchestrateur, **deux merges apres** son
  introduction. C'est le mode d'echec EXECUTION de #427 : << etre un test >> et << etre joue >> sont
  independants, la suite complete etant proscrite par le CLAUDE.md.

**Parade LOCALE proposee ici, LIVREE par #435** (le brief de #433 demandait de la proposer, pas de
la livrer) : ajouter `test_337` a `scripts/ratchets.ps1` -- UNE entree versionnee, le format pytest
y existant deja (`pytest_signatures`). L'entree elle-meme n'est PAS recopiee ici : la banque est la
source unique (`case-430` §6). Voir §#435 ci-dessous.

Il y est eligible sans reserve : **OFFLINE PUR** (aucun runner, aucun RPC -- il re-derive son
inventaire natif de `data/symbols/<CURRENT>/`, versionne) et **~15-23 s** mesurees, soit un ordre de
grandeur sous le mur de la banque. C'est la seule chose qui manque pour que la regle << un port qui
CITE une primitive DSL neuve pose son attestation DANS LE MEME COMMIT >> ait un porteur mecanique,
exactement comme `probe_181` / `probe_120` le sont pour `TARGETING_OPTIONS` / `ABILITY_ATTACK_TYPE`.

## #435 -- l'entree est posee, et elle a rougi AUSSITOT sur `WasBlock` (2026-08-01)

`pytest_attestations` entre dans `scripts/ratchets.ps1` (**20 -> 21** entrees ; les 19 relevees par
#433 avaient deja bouge). Le constat de #433 a ete re-verifie avant d'agir, pas suppose :
`-List` = 20, aucune ne portait `test_337` ; et le `main` de `probe_326_dsl_port_matching.py` finit
par un `return 0` **inconditionnel** -- il INVENTORIE les verdicts, il n'en rougit d'aucun.

**Le premier passage a rougi sur l'arbre NON MUTE** -- ce n'est pas une contre-epreuve, c'est une
6e bascule : `BANQUE ROUGE -- 1/21 : pytest_attestations`, cause en clair
`primitives DSLTriggers encore non tranchees : ['WasBlock']`. Ouverture datee par `git log -S` :
`5e9765cd` (#432, PR #475) a introduit la citation `WasBlock` dans `engine/` sans porteur homonyme.
**C'est la premiere de ces bascules vue par un ARTEFACT et non par un humain** (#393 : orchestrateur ;
#418-r1 : constatee puis laissee ; #433 : orchestrateur, deux merges apres).

### `WasBlock` : le predicat le plus court de la famille

    DSLTriggers$$WasBlock            = new WasBlockTrigger()      # ctor a UN argument nul, AUCUN selecteur
    WasBlockTrigger$$ShouldTrigger   = return *(byte *)(entities + 0xfa)

Une lecture DIRECTE d'un flag booleen de `AbilityEntities`, sans formule intermediaire -- a
contraster avec `HasBlockedThisTurn(unit)` (#393), qui prend un selecteur et passe par
`DSLFormulas$$TimesBlockedThisTurn`. Port : le `bool(ev.was_block)` du gate (d) de
`TerminatorArmourDeactivateOnAttack.matches`, seconde branche de la disjonction
`AmountIsGreaterThanZero(HealthDamageFromEvent()) | WasBlock()` de
`TerminatorArmour_ReduceDmg_Effect$$CreateTargetTrigger` ; `TriggerEvent.was_block` EST le mirror de
`AbilityEntities+0xfa`, threade par `triggers/dispatch/attack.py` sur les deux voies de cloture.
=> **`PORTE_HORS_FACADE`**. Le SECOND consommateur natif, `DeathwingAbility$$CreateTrigger`, n'est
**pas** porte (`abilities/darkangels.py` le declare no-op) : dit dans la note d'attestation, sans
changer le verdict de la PRIMITIVE. **6e bascule `NON_PORTE` -> `CITE_A_QUALIFIER` -> `PORTE_*`,
taux 6/6.**

### Ce que la contre-epreuve a etabli

Deux mutations, chacune en **run COMPLET** (jamais `-Only` : le point est qu'un rouge ne soit pas
avale au milieu de 21), jouees dans un **clone temporaire** du depot -- le TSV versionne n'a jamais
ete touche. Mutation verifiee par **sha256 + relecture AVANT** de lire le verdict (sur une
contre-epreuve, VERT est le resultat suspect) :

| Mutant (dans le clone) | Face visee | Resultat |
|---|---|---|
| ligne d'attestation `WasBlock` retiree | primitive retombee `CITE_A_QUALIFIER` | `rc 1`, cliquet nomme, 1 test |
| ancre `final_justice.py:FinalJusticeAbility` deplacee | attestation devenue MORTE | `rc 1`, cliquet nomme, 2 tests, `ancre ... introuvable` |

Arbre bit-exact apres coup (sha256 du TSV identique a l'etat pre-epreuve, `git diff` vide), banque
re-jouee **verte 21/21** -- y compris APRES rebase sur le `probe_283` reecrit par #434 : mur
**86,2 s** dont **32,4 s** pour cette entree, cout marginal nul. ⚠ Chiffres a re-deriver, pas a
citer.
