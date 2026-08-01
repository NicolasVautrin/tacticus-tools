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
* **Les 37 `CITE_A_QUALIFIER` restants** sont hors perimetre (`DSLBehaviors` 12, `DSLFormulas` 11,
  `DSLSelectors` 12, `DSLFactory` 2) -- le meme travail reste a faire, et le mecanisme est pret.
* **`DSLTriggers$$Not`** reste `PORTE_ARTEFACT_AUTRE` (verdict anterieur, hors des 47 ; levier
  mesure a zero).
* **Le backlog SEC de la famille est INCHANGE** -- ces primitives etaient deja `NON_PORTE` avant
  #337, et le restent : `OnDeath` (8 abilities confrontables),
  `CurrentAttackDamageProfilesContain` (6), `HasRarity` (6), `IsNormalUnit` (6),
  `get_OwnerOrOwnerTileIsTarget` (6). (`DamageProfileIs` y figurait : c'etait un FAUX NEGATIF de
  l'outil, tranche depuis -- cf. #392 ci-dessous.)

## Suite #392 / #393 -- TROIS primitives, meme mecanisme

Le cliquet de livraison a rougi TROIS fois depuis #337, sur des primitives que le port CITE sans
que l'outil sache les attribuer. La forme est identique et vaut d'etre retenue : **une PR qui
ajoute une CITATION d'artefact natif dans `engine/**` peut faire basculer une primitive de
`NON_PORTE` (aucune trace) a `CITE_A_QUALIFIER`** -- sans rien casser, et sans que son auteur le
voie, puisque chaque PR est verte a SA base. Le cliquet est le seul endroit ou ca se voit.

| primitive | PR qui l'a fait basculer | verdict apres RE |
|---|---|---|
| `DamageProfileIs` | `635a3431` (#372, DefenderOfTheGreaterGood) | `PORTE_HORS_FACADE` -- cf. ci-dessous |
| `IsEffectTarget` | #418 (`1014 CamoCloak_DmgReduction`) | `PORTE_HORS_FACADE` -- les 2 ecarts de `#418-r1` sont FERMES (`case-418-r1-is-effect-target.md`) : geometrie indexee PAR effectType, et le regime << apres deplacement, avant refresh >> ne diverge pas |
| `HasBlockedThisTurn` | #426 (`1227 HarlequinsPanoply`) | `PORTE_HORS_FACADE` -- cf. §#393 |

Dans les TROIS cas, le `NON_PORTE` d'avant etait un FAUX NEGATIF : les primitives etaient portees,
collapsees en imperatif, et invisibles a toute heuristique de nom. **Le taux est desormais de 3/3 :
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

**Ce qui N'EST PAS ferme** (residu `#393-r1`, backlog) : `DSLFormulas$$TimesBlockedThisTurn` a
bascule par la MEME citation et reste `CITE_A_QUALIFIER`. Sa RE est faite -- meme verdict, meme
porteur -- mais l'inscrire violerait le perimetre que `test_337` DECLARE
(`fams == {"DSLTriggers"}`) : elargir la table a une 2e famille est une decision de cadrage, pas de
RE. Y est joint le seul ecart de mirror trouve : `RegisterBlockMade` incremente **deux** compteurs
(`+0x8c` ce tour, `+0x88` la bataille) et le port ne mirroir que le premier -- `+0x88` n'est lu que
par `BattleStatisticQuery$$GetTotalBlocksMadeByUnit`, sans pendant porte.
