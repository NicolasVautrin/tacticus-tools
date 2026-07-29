# case-249 — `TargetTileHasEnemyUnit` (bit 19) portée, et deux « seul porteur » commités qui étaient FAUX

> Fiche #249 (post-campagne des masques). Ne pas confondre avec `case-249-deathguard-targeting.md`,
> qui porte le même numéro d'ordre mais un autre lot.

## 0. Ce que ce cas a trouvé

La campagne de masques est soldée (**94 abilities au registre, 94 masques posés, 0 manquant**), mais
l'inventaire des règles NON PORTÉES en tête de `scripts/python/engine/runner/abilities/targeting.py`
n'a **jamais consigné combien d'abilities portent chaque règle non portée**. Résultat : deux
affirmations écrites, commitées et fausses, toutes deux **dans le sens qui minimise le trou**.

| affirmation commitée | réalité mesurée |
|---|---|
| `CasterHasFreeAdjacentTile` « INATTEIGNABLE chez son **seul** porteur 1028 » (`targeting.py`, `case-253` §5) | **DEUX** porteurs : 1028 `SupremeCommander` **et** 1047 `ScarabSummon`, masque `0x208000` identique |
| même règle, « son **seul** porteur du registre est `ScarabSummon` (1047) » (`backlog.md`, `case-250-summon-targeting` §4) | idem — **le compte désignait l'AUTRE porteur unique** |
| même règle, « **aucun** porteur au registre, donc rien à valider » (`port-residuals-inventory.md`, entrée case-243) | idem — vrai à l'époque, **périmé sans que rien ne le dise** |
| 1113 `Stormcaller` « **seul porteur du registre** » de `TargetIsNotAnObject` (`case-254-loki-solo-targeting.md`) | **QUATRE** porteurs : 1029, 1113, 1202, 1214 |

Le brief n'en signalait que deux ; la recherche en a trouvé **quatre**, dont trois sur la MÊME règle,
**et qui se contredisaient entre elles** (0 porteur / 1028 seul / 1047 seul). C'est cette
contradiction qui aurait dû alerter : trois documents commités, trois comptes différents, aucun juste.

Un « seul porteur » faux fait classer un gap comme anecdotique — exactement le mode de défaillance
que la campagne traque. Le compte est désormais une **colonne de l'inventaire**, et il se RE-DÉRIVE.

## 1. Le recensement, re-dérivé (ne pas citer ces chiffres de mémoire)

`python scripts/python/probe_249_unported_rule_carriers.py` recompte depuis les **deux** sources de
masque du port (`ABILITY_CLASSES[aid].TARGETING_OPTIONS` et `TARGETING_OPTIONS_UNPORTED`) et vérifie
au passage qu'aucun masque ne pose de bit hors enum `TargetingRule`.

Mesure du 2026-07-29, sur les 13 règles que l'inventaire déclarait non portées :

```
TargetIsHealable          (bit  8)  -> 2 porteurs : 1002, 1037   <- PORTEE depuis (fiche #245)
TargetTileHasEnemyUnit    (bit 19)  -> 4 porteurs : 1017, 1026, 1092, 1213   <- PORTEE ICI
CasterHasFreeAdjacentTile (bit 21)  -> 2 porteurs : 1028, 1047
TargetIsNotAnObject       (bit 33)  -> 4 porteurs : 1029, 1113, 1202, 1214
les NEUF autres                     -> 0 porteur
```

- `TargetIsRepairable`, `TargetTileIsFreeOrEnemy`, `TargetIsDisplaceable`,
  `TargetIsAllowedForCaster`, `TargetHas1/3/7Tiles`, `TargetIsHero`, `TargetIsNotSteppable` ne sont
  portées par **aucun** des masques du registre : ce ne sont pas des résidus, **il n'y a rien à y
  porter**. Les nommer coûte moins cher que de les re-chercher.
- **0 bit hors enum** sur les 95 masques lisibles.
- Abilities touchées par au moins une règle non portée : **12 avant** ce cas, **8 après** (le bit 19
  en ferme 4).

## 2. La règle portée — `TargetTileHasEnemyUnit` (bit 19, `0x80000`)

### 2.1 La clause native

`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge **7 arguments**),
imbriquée dans la clause du bit 17 et immédiatement avant `TargetIsNotAdjacent` :

```c
if ((rules & 0x80000) != 0
    && ( TileExtensions.IsEmptyOrSteppable(<cible resolue>, state)
         || !TargetingQuery.UnitsCanAttackEachOther(caster, GetUnit(target)) ))
   -> GenericBrokenTargetingRule(0x80000);
```

**Réponse au critère du cas** : oui, la tuile-cible doit porter une unité **ennemie du caster**, et
la résolution passe par **DEUX chemins différents**, qu'il ne faut pas confondre :

| terme | ce qui est résolu | symbole natif | helper du port (déjà existant) |
|---|---|---|---|
| 1 — la tuile est-elle vide / steppable ? | la cible **résolue par la tête de domaine**, donc `GetMainTile(target)` pour les 4 porteurs (tous `TargetIsTile`) | `IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable` | `entity_tiles(...)[0]` (comme le bit 12) |
| 2 — l'occupant est-il attaquable ? | `local_c8`, calculé **une fois** en tête de cascade sur la cible d'origine | `IdunBattle.Entities.UnitExtensions$$GetUnit` | `unit_of_entity` |

Le décompilateur nomme le 2e terme `pcVar9`. **Ce n'est pas `GetMachine`** : ghidra réassigne
`pcVar9 = local_c8` juste avant le bloc `TargetIsTargetable`, et c'est cette valeur qui traverse le
bloc TUILE. `GetUnit` sur une entité-TUILE lit son `TileContentComponent`, et si `IsFilled` remonte
à `state.GetEntity(content.UnitId)` : **l'occupant**, pas la tuile.

`TileExtensions$$IsEmptyOrSteppable` (les deux surcharges ont le même corps) :

```c
if (tile.TileContentComponent.IsEmpty())                            return true;
u = UnitExtensions.GetUnit(tile, state);
if (u != null && GetBaseUnitComponent(u).HasTrait(0x1b Steppable))  return true;
return false;
```

⚠ **Fonction native DISTINCTE de `TileExtensions$$CanAddUnit`** — `CanAddUnit` ne l'appelle pas, il
ré-écrit le même test et l'encadre de trois rejets qu'`IsEmptyOrSteppable` n'a pas (blocker,
`NotWalkable`, tuile réservée). Une tuile non marchable et vide est `IsEmptyOrSteppable` = **vrai**
et `CanAddUnit` = **faux**. Le port les garde séparées : la structure offline suit la structure
native.

**Aucune troisième variante de résolution de tuile n'a été introduite** — c'est la faute que ce
module a déjà payée deux fois (#251/#254, `GetUnitFeetIds` qui rend `[]` sur une tuile au lieu
d'`EntityExtensions$$GetTiles` ; #250, `TargetTileIsFree` testé sur les ids du board au lieu de
`GetMainTile`). `entity_tiles` et `unit_of_entity` étaient déjà là, ce sont eux qui servent.

### 2.2 Position dans la cascade

`TargetTileIsFree` (12) → `TargetTileIsFreeOrEnemy` (17) → **`TargetTileHasEnemyUnit` (19)** →
`TargetIsNotAdjacent` (32) → `TargetIsNotAdjacentToEnemy` (42) → `TargetMatchesDynamicRule` (1) →
`TargetIsCasterOrEnemy` (57).

L'ordre n'est pas cosmétique : il fixe la raison rendue quand plusieurs règles sont rompues. Deux
conséquences directes :
- la **portée** (`TargetIsInRange`) est testée **bien avant** le bit 19 : sur 1017 (`RANGE_ADJACENT`)
  une cible hors adjacence rompt sur la portée, pas ici ;
- chez 1213 `DeathOnTheWind`, le bit 19 précède `TargetMatchesDynamicRule` : une cible **alliée**
  rompt en `0x80000` et **n'atteint jamais** la règle dynamique (non portée).

### 2.3 Sémantique et porteurs

Refus ssi la tuile visée est vide / occupée par une unité `Steppable`, **ou** si son occupant n'est
pas attaquable par le caster. Donc : tuile vide → refus ; tuile d'un **allié** → refus ; tuile d'un
**ennemi** → valide. Le **caster lui-même** est refusé aussi
(`UnitsCanAttackEachOther(caster, caster)` est faux).

| id | ability | porteur | catégorie |
|---|---|---|---|
| 1017 | `FragBomb` | `astraBullgryn` | HERO |
| 1026 | `BasiliskBarrage` | `astraOrdnance` | HERO |
| 1092 | `DarkTalonStrike` | `darkaAzrael` | HERO |
| 1213 | `DeathOnTheWind` | `darkaStormSpeeder` | MACHINE OF WAR |

Aucun NPC : **les quatre sont confrontables**, trois par le pool, la MoW par `catalog_inject.py`
(c'est déjà ce que fait `test_targeting_masks_live.py`).

**Le gap était MESURÉ et écrit** : le commentaire de 1092 dans `darkangels.py` disait mot pour mot
« le port rend 0 sur toutes les cibles, y compris celles que le natif refuse en
`TargetTileHasEnemyUnit` ». C'est ce trou-là qui est fermé.

## 3. `CasterHasFreeAdjacentTile` (bit 21) — l'inertie REFAITE pour 1047, et elle tient

L'argument d'inertie avait été construit sur 1028 et jamais vérifié sur 1047. Il a été refait, au
décompilé, et il tient — les deux ctors posent **la même paire** :

```
IdunBattleLogic.Entities.Abilities.Active.Loki.ScarabSummonAbility$$.ctor
    TargetingOptions..ctor(&opts, isSelfCasting=1, &<TargetingRange statics+0x60>,
                           forceMeleeTarget=1, 0x208000, 0, 0, 0)
IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$.ctor
    idem — même preset, même littéral
```

`IdunBattle.Core.Services.TargetingRange$$.cctor` écrit à `statics+0x60` :
`{+0x60 = 1 (onlyAdjacent = RangedBool.False), +0x68 = Nullable(0), +0x70 = null}` = `RANGE_SELF`,
portée **0**.

Deux chemins, tous deux fermés **avant** le bit 21 :
- cible == caster (ou la tuile du caster, que `GetUnit` résout en lui) → l'aiguillage self-cast de
  l'overload 5 arguments branche sur `TargetingQuery$$GetCasterNotAddedReason` et la cascade CIBLE
  n'est **jamais** évaluée ;
- cible ailleurs → `d > 0` rompt `TargetIsInRange`, qui **précède** le bit 21 dans la cascade.

**Verdict : la règle reste NON PORTÉE, et c'est délibéré** — la porter serait du code non
confrontable, exactement ce que l'argument d'inertie visait à éviter. Ce qui était faux, c'est le
compte, pas le raisonnement.

Chemin **indirect** qui l'atteindrait, nommé pour mémoire : `GetCasterNotAddedReason` termine sur
`IdunBattle.Core.Services.TargetingQuery$$GetValidTargets`, qui ré-applique la cascade complète à
toutes les cibles candidates. `GetValidTargets` n'est pas porté (cf. `get_caster_not_added_reason`),
donc rien à y gagner tant que ce maillon-là n'est pas porté.

## 4. Validation

### 4.1 Ce qui a été mesuré

**Offline, sans le jeu** — `python scripts/python/probe_249_tile_has_enemy_targeting.py
--offline-cascade` : le triplet **sur LA MÊME tuile**, contre la cascade portée seule.

```
T VIDE   attendu=0x80000 | 1017: avec=0x80000 sans=0x0 OK | 1026: avec=0x80000 sans=0x0 OK
T ALLIE  attendu=0x80000 | 1017: avec=0x80000 sans=0x0 OK | 1026: avec=0x80000 sans=0x0 OK
T ENNEMI attendu=0x0     | 1017: avec=0x0     sans=0x0 OK | 1026: avec=0x0     sans=0x0 OK
cible=UNITE (1017) : caster=0x80000 ennemi=0x0 allie=0x80000  OK
verdicts que le bit 19 DEPLACE (contrefactuel sansBit19) : 4
```

Le contrefactuel `sansBit19` déplace 4 verdicts : la règle **n'est pas inerte**, elle décide.

**Recensement** — `probe_249_unported_rule_carriers.py` (cf. §1), re-dérivé du code, pas hérité.

**Tests offline rejoués, verts** : `test_targeting_options_sources.py`,
`test_ability_registry_ratchet.py`,
`test_targeting_masks_live.py::test_every_mask_matches_the_literal_read_in_the_native_ctor`
(13 passed). Plus `probe_targeting_rule_bits.py` : les 58 bits concordent sur les trois sources.

**Après rebase sur `origin/master`** (qui a apporté `#247` sur le même fichier — conflit résolu par
FUSION : `units_are_friends` de #247 et `tile_is_empty_or_steppable` d'ici cohabitent) : les trois
probes et les 13 tests offline **rejoués, tous verts**.

**Constat utile pour la migration** : l'enum `IdunBattle.Core.Services.TargetingRule` est **identique
bit pour bit** entre `data/symbols/gqfc5mff6c/frida/enums.tsv` et
`data/symbols/rnca9r7q6c/frida/enums.tsv`. Cela ne prouve pas que la cascade est inchangée — seul un
re-décompilé de `TargetingQuery$$GetInvalidTargetReason` sur `rnca9r7q6c` le dirait — mais aucun bit
n'a bougé sous les masques, donc la transcription des littéraux tient.

### 4.2 Ce qui n'est PAS couvert — **NON CONFRONTÉ LIVE, différé par la MAJ `gqfc5mff6c` → `rnca9r7q6c`**

Le jeu est passé en mise à jour pendant ce cas ; aucun runner n'était montable. **Rien de ce port
n'a été confronté à l'oracle natif `abilityReason`.** Ce qui reste à mesurer, et par quel montage :

1. **Le triplet, contre l'oracle natif** — `python probe_249_tile_has_enemy_targeting.py` (mode live,
   sans `--offline-cascade`), puis `--seed 31337 --board C1_02` pour le second couple. Il monte
   `astraBullgryn` + `astraOrdnance` + un allié, choisit une tuile `T` adjacente au Bullgryn, et la
   met successivement dans les trois états en **déplaçant** les unités. Attendu : natif == port sur
   chaque ligne, et le triplet `0x80000 / 0x80000 / 0`.
2. **Les deux autres porteurs** (1092 `DarkTalonStrike`, 1213 `DeathOnTheWind`) — c'est
   `tests/engine/runner/test_targeting_masks_live.py` qui les couvre : ils **ont changé de colonne**
   dans `DA_CASES` (de « masque sans bit porté » à `expect = TR.TargetTileHasEnemyUnit`), donc le
   test 3 (`test_armed_mask_reproduces_a_native_refusal`) exige désormais qu'un refus natif
   `0x80000` soit reproduit à l'identique. **Ce test n'a pas pu tourner.** Pour 1092, la ligne
   attendue est le caster lui-même (distance 0, donc jamais filtré par la portée en amont) ; pour
   1213 (`RANGE_WHOLE_BOARD`), n'importe quel allié.
3. **Le résidu MoW-cible** : le natif rend `GetUnit(MoW)` **nul**, là où le port pose un
   `UnitComponent` d'identité sur les machines. Sur une MoW **prise pour cible**, le natif refuse en
   `0x80000` et le port accepte — divergence **permissive**, donc conforme au contrat, mais non
   mesurée. Elle n'apparaît pas dans les montages ci-dessus (`decisionView.units` ne contient pas
   les MoW).
4. **La règle du bit 21 chez 1047** n'est pas confrontable **par construction** (§3) : son inertie
   est établie au décompilé, pas par la mesure. C'est assumé.
5. **`TargetIsNotAnObject`** (4 porteurs) reste non portée : il faut une cible portant le trait
   `0xd Object`, qu'aucun montage connu ne produit. Résidu **nommé**, non fermé ici.
6. ~~**`TargetIsHealable`** (1002, 1037) : hors périmètre, fiche #245.~~ — **PORTÉE depuis**, cf.
   `docs/rl/case-245-target-is-healable.md` : le prédicat est `AttackQuery$$EntityCanBeHealed`
   (slot `0x11` d'`IAttackQuery`), pas la garde de mutation `healable_heal_type_0`.

## 5. Fichiers

- `scripts/python/engine/runner/abilities/targeting.py` — `tile_is_empty_or_steppable` (mirror de
  `TileExtensions$$IsEmptyOrSteppable`), la clause du bit 19 dans `get_invalid_target_reason`,
  l'inventaire avec sa colonne « porteurs » et le paragraphe du bit 21 réécrit.
- `scripts/python/probe_249_unported_rule_carriers.py` — recensement règle → porteurs (offline).
- `scripts/python/probe_249_tile_has_enemy_targeting.py` — confrontation live + `--offline-cascade`.
- `scripts/python/engine/runner/abilities/darkangels.py` — commentaires 1092 / 1213 (le bit 19 n'est
  plus « NON PORTE »).
- `scripts/python/tests/engine/runner/test_targeting_masks_live.py` — 1092 et 1213 passent en
  colonne « masque armé ».
- `docs/rl/case-254-loki-solo-targeting.md` — « seul porteur du registre » corrigé (quatre).
- `docs/rl/case-250-summon-targeting.md`, `docs/rl/case-253-astramilitarum-targeting.md`,
  `docs/rl/backlog.md`, `docs/rl/port-residuals-inventory.md` — les trois autres comptes faux du
  bit 21, corrigés et datés.
