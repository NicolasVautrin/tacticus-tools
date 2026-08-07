# #287-r8 — l'étage `battleQuery`, l'aura Synapse, et les deux crans sous eux

Trois règles dynamiques de ciblage portées **et confrontées live**. Dettes réelles **13 → 10**,
re-dérivé des deux côtés par `probe_287r5_etages_bloquants.py` (le recensement est la vérité
courante, pas cette page — le re-jouer).

| id | ability | porteur | canal | étage demandé |
|---|---|---|---|---|
| 1025 | `SkyStrike` | `adeptCelestine` (hors pool → seed BC augmenté) | surcharge | `BattleQuery$$GetAdjacentTiles`, surcharge IList |
| 1087 | `ExemplarOfTheKauyon` | `tauShadowsun` (pool) | table | `BattleQuery$$GetAdjacentUnits`, slot 122 |
| 1112 | `AlphaWarrior` | `tyranWingedPrime` (pool) | surcharge | `SynapseEffect` comme `IAuraEffect` |

## 1. Les trois corps, verbatim

`SkyStrikeAbility$$GetDynamicInvalidTargetReason` :

    first    = casterTiles[0];
    moved    = UnitExtensions.DidMove(caster) || GetMainTile(caster, state) != first;
    adjacent = battleQuery.AreEntitiesAdjacent(casterTiles, targetTiles);   # slot 0x62
    if (moved && !adjacent) return 0x10;                                    # CasterHasNotMoved
    tiles = battleQuery.GetAdjacentTiles(targetTiles, 1, 1, 0);             # slot 0x51
    if (adjacent) return 0;
    return tiles.Count() > 0 ? 0 : 0x20;                                    # TargetHasFreeAdjacentTile

`ExemplarOfTheKauyonAbility$$GetDynamicInvalidTargetReason` :

    if (!TileExtensions.IsFreeTile(target, state, true, false, false)) return 2;
    units = battleQuery.GetAdjacentUnits(target, null, null, false);        # slot 122
    units.Remove(caster);                                                   # ICollection<T> slot 6
    units.RemoveAll(u => UnitExtensions.IsEnemy(u, caster, state));
    return units.Count() == 0 ? 2 : 0;                                      # slot 0

`AlphaWarriorAbility$$GetDynamicInvalidTargetReason` → `$$IsInSynapseRange(caster, target)` :

    trigger = DSLTriggers.IsInTeamSynapseRange(DSLSelectors.Entity(target),
                                               DSLSelectors.Entity(caster));
    return trigger.ShouldTrigger(AbilityEntities(caster, caster, target, ...)) ? 0 : 2;

`0x10` = `TargetingRule.CasterHasNotMoved`, `0x20` = `TargetHasFreeAdjacentTile`,
`2` = `TargetMatchesDynamicRule`, `0x41c` = `EffectType.Synapse_Effect`,
`0x7e8` = `UnitTrait.Synapse`.

## 2. Quatre points que la RE a tranchés, et qu'un mirror naïf rate

- **`1025` rend DEUX codes de refus, et AUCUN n'est dans son masque** (`0x6004002`). La cascade
  retourne le code de la règle-délégué tel quel (`GenericBrokenTargetingRule(reason)`), sans le
  confronter aux `Rules` : le recensement se fait sur le **bit posé au masque** (`0x2`), jamais sur
  le code rendu. Une bascule à deux bras ne verrait pas un port qui confond les deux.
- **La surcharge d'`IsInSynapseRange` est tranchée par ses XREFS**, pas par sa place dans le
  fichier : les deux homonymes ont la même signature `(this, caster, target)`. Celle que
  `GetDynamicInvalidTargetReason` appelle est celle qui construit les sélecteurs et **évalue** ;
  l'autre rend l'objet trigger, dont l'octet bas du pointeur n'a aucun sens comme prédicat.
- **`TileExtensions$$IsFreeTile` a le MÊME CORPS que `TileExtensions$$CanAddUnit`** — lu, pas
  supposé : mêmes quatre rejets dans le même ordre (composant tuile, `Blocker`, `NotWalkable`,
  contenu vide-ou-`Steppable` `0x1b`), même sortie de queue `Position+0x2c == 0` sous le flag. Les
  triplets coïncident (`(1, 0, 0)`), donc le terme est **inerte** : il redemande ce que le bit
  `TargetTileIsFree` du masque a déjà exigé en amont. Le seul terme discriminant de `1087` est
  l'**allié adjacent**.
- **`GetAdjacentUnits` est le MÊME étage que `GetAdjacentEnemies`/`GetAdjacentFriends`** déjà
  portés (`IterateAdjacentTiles(from, 0, 1, 1)` → `CountOrGetUnitsOnTiles`). Sa particularité est
  que les DEUX filtres sont des paramètres, et que le call-site les passe **nuls** : c'est le seul
  des trois natifs qui sache rendre « toute unité adjacente, amie comme ennemie ».

## 3. Le cran SOUS l'étage — `SynapseEffect` comme `IAuraEffect`

**L'étage synapse était déjà porté** (`triggers.IsInTeamAura`, générique sur `effect_type`), et
seul le call-site manquait — la vérification que la consigne « porte l'étage » impose dans les deux
sens. Mais **un cran plus bas manquait** : `EffectType.Synapse_Effect` n'était pas dans
`_AURA_EFFECTS`, donc le cast `as IAuraEffect` échouait, `GetInRangeAuraAmount` rendait `0`, et
`1112` aurait refusé **toute** cible — un **SUR-refus systématique**, l'exact contraire de la
dégradation permissive du module.

    $$GetTrait          = 0x7e8 = UnitTrait.Synapse       (corps constant)
    $$GetMaxRange       = Direct(2)   |  UN SEUL corps, PARTAGÉ par les trois slots
    $$GetCurrentRange   = Direct(2)   |
    $$GetNextTurnRange  = Direct(2)   |

⚠ **Seul `GetNextTurnRange` porte un nom dans la table**, et en conclure que les deux autres
n'existent pas aurait été faux (IL2CPP déduplique, la table n'attribue qu'UN propriétaire). Ce qui
l'établit est la **VTABLE** : quatre pointeurs consécutifs — `GetTrait`, puis **trois entrées vers
la même adresse**. Contre-épreuve sur le voisin :
`ContagionsOfNurgle_ArmorReduction_Effect$$GetMaxRange` a son PROPRE pointeur, ses trois slots sont
distincts. Conséquence de structure : chaque `IAuraEffect` porte désormais **sa** formule de portée
(constante pour Synapse, tabulée pour Contagions) — et un test garde que l'ajout n'a pas **aplati**
la seconde.

## 4. Ce que la MESURE a imposé, et que la lecture n'avait pas donné

**Le terme `units.Remove(caster)` de `1087`, trouvé par un SOUS-REFUS live.** `IsEnemy(caster,
caster)` est faux, donc le `RemoveAll` ne retire pas le caster : sans ce premier retrait, une tuile
dont le SEUL voisin est Shadowsun elle-même passait (natif `0x2`, port `0` sur `MC1_67`). Il est
logique — l'ability la TÉLÉPORTE, elle ne peut pas être son propre voisin à l'arrivée.

⚠ **Il n'était pas lisible au premier passage** : Ghidra rend `FUN_180003c00(6, <MI>, liste,
caster)`, un invoke d'interface générique anonyme. Le `6` est le slot `Remove` d'`ICollection<T>`
(`get_Count` 0, `get_IsReadOnly` 1, `Add` 2, `Clear` 3, `Contains` 4, `CopyTo` 5, `Remove` 6), et ce
qui l'**établit** est un second call-site du même motif **dont le nom dit ce qu'il fait** :
`idun.Idun.Source.IdunMeta.View.Hud.Screens.GuildProjects.GuildProjectWidget$$HandleCheatRemoveTapped`,
dont le corps entier est ce seul appel. Le `Count` de queue est le slot 0 de la même interface.

## 5. Deux corrections de MESURE, toutes deux trouvées en jouant les probes

- **UN SOUS-REFUS NE SE DISCULPE PAS PAR LE DÉSARMEMENT.** L'attribution par désarmement ne
  discrimine que sur les SUR-refus : désarmer ne peut rendre le port que **plus permissif**, donc
  tout sous-refus survit au témoin par construction et serait compté « préexistant » — un vert
  automatique. C'est exactement ce qu'a fait la première version, qui a affiché `VERDICT : OK`
  **avec le sous-refus sous les yeux**.
- **LES IDS D'UNITÉ D'UN SUBSTRAT FABRIQUÉ DOIVENT ÊTRE DISJOINTS DE CEUX DES TUILES.** Deux des
  trois règles sont TILE-TARGET : la cible est un id de TUILE, et `EntityExtensions$$GetTiles`
  cherche d'abord une **unité** de cet id. Avec `CASTER, CIBLE, ALLIE, ENNEMI = 1, 2, 3, 4`, la
  tuile `id=4` résolvait sur les PIEDS de l'unité 4 et la cascade rendait `TargetTileIsFree` au lieu
  de la règle mesurée. **Le port a raison** — le natif garantit deux espaces d'ids disjoints ; c'est
  le substrat qui violait l'invariant. Les ids sont désormais dérivés du board, et l'étape 0 vérifie
  la disjonction. Seul l'étage 6 (le chaînon complet `is_invalid_target`) pouvait le voir : les cinq
  étages au-dessus étaient verts.

## 6. L'ADJACENCE DU BOARD EST UN ÉTAGE, pas un détail de confort

`Board(tiles, adjacency=...)` a deux modes : `native_sym` (l'adjacence que `boardGraph` **publie**,
c'est-à-dire `BattleQuery$$GetAdjacentTiles` natif) et `evenq` (recalcul géométrique). Les trois
règles de cette tranche sont bâties sur des voisinages — un board reconstruit fait diverger le port
du natif **pour une raison qui n'est pas la règle**, et le désaccord se lit alors comme une faute de
portage.

Mesuré : `MC1_67` a **11 tuiles** où les deux modes divergent ; `C1_02` en a **0**. Les probes #287
antérieurs utilisent tous `evenq`. Le probe de cette tranche prend `native_sym` par défaut,
**imprime** l'écart, et accepte `--adjacency evenq` comme contre-épreuve.

⚠ **ET LA CONTRE-ÉPREUVE A RÉFUTÉ L'HYPOTHÈSE QUI AVAIT FAIT AJOUTER CE VOLET.** Le mode était
suspecté d'expliquer le sous-refus de `MC1_67` ; re-mesuré après le correctif, `--adjacency evenq`
rend **exactement le même résultat** (10 refus reproduits, 0 sous-refus, 0 imputable) : les
11 tuiles divergentes ne touchent aucun des couples mesurés. **La cause du sous-refus était le terme
`Remove(caster)`, pas l'adjacence.** Le volet reste — l'écart est réel et la question se reposera
sur un autre montage — mais il est INERTE ici, et le dire évite d'attribuer à ce choix un mérite qui
revient à la RE.

## 7. Chiffres, re-dérivés des deux côtés

| | avant #287-r8 | après |
|---|---|---|
| règle ÉVALUABLE par le port (surcharge/table) | 25 | **28** |
| aucune règle (le `0` permissif) | 40 | **37** |
| dont **dette réelle** (surcharge native lisible) | **13** | **10** |
| dont `0` coïncidant avec le corps de base | 27 | 27 |
| entrées de `_AURA_EFFECTS` | 2 | **3** |

## 8. Confrontation LIVE, avec ATTRIBUTION

`probe_287r8_regles_battlequery_live.py` — géométrie **PILOTÉE** (cibles des deux côtés de chaque
bascule, ventilation imprimée ; un PAS réel joué pour exercer `CasterHasNotMoved`), oracle débloqué
(#287-r6), attribution par désarmement, décomposition par étage sur tout désaccord.

| board | couples | refus reproduits à l'identique | sur-refus imputables | SOUS-refus | divergence d'adjacence |
|---|---|---|---|---|---|
| `MC1_67` | 21 | **10** (1×`0x10`, 5×`0x2`, 4×`0x2`) | **0** | **0** | 11 tuiles |
| `C1_02` | 21 | **11** (2×`0x10`, 5×`0x2`, 4×`0x2`) | **0** | **0** | 0 tuile |

Contre-épreuves :

- **désarmées**, les mêmes couples tombent à **0** reproduction exacte sur les deux boards — le
  témoin est bien porté par ces règles et non par un autre étage du masque ;
- **`--pas-de-move`** : sans le pas joué, `MC1_67` tombe de **10 à 8** refus et le bras
  `CasterHasNotMoved` disparaît entièrement. Le pilotage est ce qui l'exerce, ce n'est pas une
  propriété du board.

## 9. La garde

`tests/engine/test_287r8_regles_battlequery_offline.py`, **six étages** : recensement bi-canal ;
bascule (5 bras, dont les DEUX codes de refus de 1025) ; mutants en **DELTA** ; le terme
`Remove(caster)` ; l'étage `IAuraEffect` **et sa contre-épreuve non-aplatissement** ; le chaînon
complet `is_invalid_target`.

Vue rouge sur l'arbre témoin (`git archive` du commit d'avant la tranche) : **7 failed / 2 passed** ;
**9 passed** après. Les deux verts d'avant sont ceux qui gardent un acquis antérieur (les masques,
la table de Contagions) — et c'est ce qui rend le rouge lisible.

## 10. Ce qui n'est PAS couvert

- **`#287-r12` — RÉSOLU.** Le rôle `target` d'une entité TUILE est matérialisé par
  `entities_from_state` lui-même, et la parade locale de `1112` a disparu. Le critère « passe son
  `target_id` au foyer » qui donnait **5** abilities ici n'était pas le bon : ce qui change avec
  l'élargissement, c'est ce qu'un arbre **LIT**, et le rayon effectif est **2** (`1017` FragBomb,
  `1018` ValkyrieStrike) — les deux confrontées au natif, `1026` étant muette pour une **autre**
  cause (son collapse impératif) et `1148`/`1169` portant leur propre normalisation. Détail :
  `case-287r12-role-target-entite-tuile.md`.
- **Le bras `TargetHasFreeAdjacentTile` de 1025 n'est pas exercé en LIVE** : il exige une cible dont
  aucune tuile adjacente n'est libre — une ceinture complète, que ni `MC1_67` ni `C1_02` ne
  produisent spontanément. Couvert **offline** (cible ceinturée par 4 unités), et le probe live
  l'imprime au lieu de se compter vert.
- **Le terme `GetMainTile(caster) != casterTiles[0]` de 1025 est INERTE offline, par construction** :
  `GetMainTileId` rend littéralement `unit._feet[0]`, et `casterTiles` énumère ce même `_feet`. Il
  n'a de mordant que là où le natif reçoit des `casterTiles` **simulés** (l'IA qui évalue « et si je
  castais depuis là-bas ? »), un régime que la signature du port n'expose pas.
- **`1179 CultDemagogue` reste NON PORTÉ**, et sa RE est faite (§11).
- Le volet **caster** (`options+0x30`, `CasterMatchesDynamicRule`) : inchangé, aucune règle portée.

## 11. `1179 CultDemagogue` — RE complète, port non fait

Troisième id de l'étage `battleQuery`, laissé hors tranche faute de budget. Corps lu :

    range     = GetNumberConstant(0x44 range_2);         # = 2 au gameconfig
    name      = GetStringConstant(0x0 unitId);           # = "genesSmnDecoy"
    freeTiles = battleQuery.GetFreeSurroundingTiles(GetMainTile(caster, state), range, 0, 1);
    allAlive  = battleQuery.GetAllAliveUnits(Nullable<int>(GetCurrentOwnerEntityId(caster)));
    enemies   = battleQuery.GetSurroundingEnemies(target, allAlive, range, 0);
    if (freeTiles.Count() != 0) return 0;
    return enemies.Where(u => UnitExtensions.GetUnitId(u) == name).Any() ? 0 : 2;

Slots LUS dans `data/symbols/<build>/metadata/interface_slots.tsv` : `IBattleQuery 104
GetFreeSurroundingTiles 4`, `IBattleQuery 137 GetAllAliveUnits 1`, `IBattleQuery 120
GetSurroundingEnemies 4`. Signatures LUES au décompilé des implémentations :
`GetFreeSurroundingTiles(center, distance, includeCenter, onlyMovable)` =
`GetSurroundingTiles(center, distance, requireEmptyOrSteppable: 1, checkWalkable: 1, onlyMovable,
includeCenter)` puis `FilterInPlace` ; `GetSurroundingEnemies(actor, from, range, includeCenter)` =
`GetSurroundingUnits(from, range, includeCenter)` puis `FilterInPlace(u => IsEnemy(u, actor))`.

**Ce qui reste ouvert et exige une mesure** : le second argument passé au slot 120 est le résultat
de `GetAllAliveUnits`, quand la signature de l'implémentation nomme ce paramètre `from`. Deux
lectures restent possibles (`GetSurroundingUnits` a une surcharge qui prend une COLLECTION, ou
Ghidra a perdu l'affectation du résultat), et les départager demande soit la surcharge exacte du
slot, soit une confrontation live. Écrire le port sans trancher inventerait un étage.

Quatre primitives manquent au port pour ce corps : les trois slots ci-dessus et
`AbilityConfiguration$$GetStringConstant`. Porteur `genesPrimus`, **dans le pool** : confrontable.

## 12. Les dettes restantes, telles que recensées

`trigger DSL` 2 (`1168 EntropyCannons`, `1200 SquigLaunchas`) — les deux à porteur **MoW**
(`deathCrawler`, `orksRukkatrukk`), tous deux dans les 8 MoW spawnables ; `battleQuery` 1
(`1179 CultDemagogue`, §11) ; `sélecteur DSL` 2 (`1016 SendInTheNextWave`,
`1197 ExcruciatingFrequencies`) ; `pathfinding` 1 (`1180 HeroicFusillade`) ; et quatre isolés
(`1076`, `1101`, `1164`, `1213`). Le re-dériver par `probe_287r5_etages_bloquants.py`, ne pas citer
cette ligne.

Deux corps ont été LUS pendant cette tranche et sont directement réutilisables :

- `1112`-comme-`1200` : `SquigLaunchasAbility$$HasMinimumAdjacent{Orks,FriendlyUnits}` =
  `AmountIsEqualOrGreater(UnitsFromFaction(Friends(NonSteppableOrObjectUnits(AdjacentUnits(...))),
  faction 5), Direct(GetNumberConstant(0x78 / 0x79)))` — les deux prédicats sont **déjà portés**
  (`orks.py`), mais sur les seuils du **SUMMON** (`nrOfUnits_3`/`nrOfUnits_4`), pas sur ceux du
  CIBLAGE (`0x78`/`0x79`).
- `1168 EntropyCannons` : `(IsInTeamContagionsOfNurgleAura(target) || (HasNegativeModifier(target,
  0x10 FixedArmor) && <composant>.<+0x48> > 0)) ? 0 : 2`, avec `IsUnit(target)` en garde d'entrée.
  Les deux triggers sont **déjà portés** ; reste à identifier le composant du troisième terme.
