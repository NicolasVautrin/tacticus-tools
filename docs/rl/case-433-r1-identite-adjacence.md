# #433-r1 — le court-circuit d'IDENTITÉ de `MovementUtil$$AreTilesAdjacent`

**Verdict : QUIRK PORTÉ (4 foyers), et le terme joint — la porte d'élévation — est CONFRONTÉ LIVE.**
Le résidu d'ORDRE de #448-r2d tombe avec lui, par conséquence et non par coïncidence.

## 1. Le fait natif, lu

`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`, surcharge **scalaire** `(tile1, tile2)` :

```
elev1 = GetComponent<Elevation>(tile1)+0x18     # les DEUX lues AVANT tout branchement ;
elev2 = GetComponent<Elevation>(tile2)+0x18     # composant absent  ->  la fonction LEVE
dElev = |elev2 - elev1|
b     = (tile1 == tile2) ? 1
                         : ConnectivityComponent$$IsNeighbour(tile1.Connectivity, tile2)
return (dElev < 2) & b
```

Trois lectures qui ne se déduisent d'aucun nom, et qui répondent aux trois questions du brief :

* **Sur quoi porte le test d'identité** : sur l'**identité de référence des deux entités-tuile**
  (`tile1 == tile2` compare les pointeurs `void*` des objets IL2CPP), ni des coordonnées, ni un `Id`.
* **Ce qu'il rend** : `b = 1`, en **court-circuitant** la résolution de `ConnectivityComponent` — le
  chemin dédié est *avant* le voisinage, *après* les deux lectures d'élévation.
* **Ce que ça vaut au total** : sur une même entité `dElev = 0 < 2`, donc le gate d'élévation ne peut
  pas le contredire. **Une tuile est adjacente à elle-même, inconditionnellement.**

La surcharge **liste × liste** `(IList, IList)` est une double boucle sur la scalaire (vrai dès
qu'UNE paire l'est) : elle hérite des deux termes.

## 2. Les XREFS entrantes — qui peut recevoir deux fois la même tuile

Appelants **directs** de la scalaire (`UNCONDITIONAL_CALL`, les autres xrefs sont des entrées DATA
de metadata) :

| appelant natif | forme | régime d'identité |
|---|---|---|
| `IdunBattle.Entities.TileExtensions$$IsAdjacentTo` (surcharge `(tile, otherTile)`) | passe-plat | selon l'appelant, cf. ci-dessous |
| `IdunBattle.Entities.TileExtensions$$IsAdjacentTo` (surcharge `(tile, otherTiles)`) | boucle sur la liste | idem |
| `IdunBattle.Entities.TileExtensions$$IsAdjacentToAll` | boucle, conjonction | 1 appelant (`LivingBatteringRamAbility`) |
| `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent` (surcharge LISTE) | double boucle | hérite |

Appelants de la surcharge LISTE : `IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack`
et les **trois** surcharges de `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` (slots
d'interface `0x5f`/`0x60`/`0x61`), elles-mêmes appelées **par vtable** — donc par
`TargetingQuery$$GetInvalidTargetReason` (portée `OnlyAdjacent`, bit 32), `IsAdjacentTilesTrigger`,
`IsAdjacentAbilityTrigger`, `AreUnitsInMelee`, `IsCharging`, `IsMeleeAttack`, `IsRangedAttack`,
`GetNearestEnemy`, `GetAttackRangeType`.

**Le régime « deux fois la même tuile » est ATTEIGNABLE, et il l'était déjà mesuré** :

1. **Cible = la tuile SOUS le caster**, sous `OnlyAdjacent` — `IronkinSteeljack` (1219) cast sur sa
   propre tuile passe la portée et rend `TargetTileIsFree` (0x1000) là où un port en `dist == 1`
   rendait `TargetIsInRange`. BIT-DIFF mesuré par `probe_targeting_masks_lot4.py --groups steeljack`.
   **Déjà porté** (`runner/abilities/targeting.py::are_tiles_adjacent`).
2. **Structurellement dégénéré** — `IdunBattle.AI.Utilities.WireweaveNet_FirstAttack.u003CEvaluate
   AttackInStepsu003Ed__1$$MoveNext` : à l'assembleur, les trois appels sortent du **même champ**,
   donc `IsAdjacentTo(t, t)` — conjoint trivialement vrai. Déjà porté (`utilities/wireweave_net.py`).
3. **Destination d'un pas = tuile marquée** — `IsAdjacentTilesTrigger` sous le vslot 0x748 du
   Titanhammer. C'est le foyer du présent résidu (§3).
4. **Tuile candidate = tuile cible** — `FilterTilesIfCanAttackTargetTileFromSelector$$Select`,
   `LivingBatteringRamAbility$$GetPossibleTilesToThrowTo` : sélecteurs NON PORTÉS, hors périmètre.

Régimes **inatteignables**, et par quoi : deux unités distinctes ne partagent jamais une tuile
(`is_charging`, `CalculateTrenchReduction`), et une tuile candidate de déplacement n'est pas la
position d'une cible vivante (`AvalancheOfMuscle` état 4, `AggressiveOnslaught` gate 1). Ils sont
**portés quand même**, par fidélité — cf. §4.

## 3. Le foyer du résidu : le vslot 0x748, et ce que le port en ratait

`IdunBattle.Entities.Effects.Loki.TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition`
= `Contains(<Sel+0x78>, tgt) op_BitwiseOr IsAdjacentTiles(<Sel+0x78>, tgt)`.

`IsAdjacentTilesTrigger$$ShouldTrigger` résout ses deux sélecteurs par le **slot 10** (listes de
tuiles), double-boucle, et tranche **chaque paire par le slot `0x60`** du query
(`BattleQuery$$AreEntitiesAdjacent` → la primitive). Le port, lui, faisait
`any(t in board.neighbours(dest) for t in marked)` : **ni identité, ni élévation**.

Fix : le bras délègue à `runner/abilities/targeting.py::are_tiles_adjacent`, le foyer mirror qui
porte déjà les deux termes.

### Ce que le port gagne, terme par terme

* **(I) identité** — une destination QUI EST une marque satisfait aussi ce bras, pas seulement
  `Contains`. Le bras `Contains` ne regarde que la **première** marque (`XContainsYTrigger` réduit
  son 2ᵉ opérande à UNE entité par le slot 1) ; le court-circuit rattrape les autres.
* **(E) élévation** — une voisine à `|dElev| >= 2` n'est **pas** adjacente. `board.neighbours` nu
  l'ignorait.

### Le résidu d'ORDRE de #448-r2d est FERMÉ par la même mesure

Puisque `AreTilesAdjacent(t, t)` est vrai, `Contains(X, marked[0])` **implique**
`IsAdjacentTiles(X, marked)` : le premier bras est **subsumé** par le second, **côté natif aussi**,
et la disjonction se réduit à `∃ j : AreTilesAdjacent(dest, marked[j])`. Le port garde `Contains` en
tête par fidélité structurelle (mirror de l'`op_BitwiseOr`), mais il ne décide plus rien seul :
l'ordre de `EffectsState.by_unit` — qui n'est **pas** celui du natif — est devenu sans effet sur le
verdict, **à toute cardinalité**. Ce n'était protégé que par « `TitanhammerSquadAbility$$Execute
Behaviour` ne pose qu'UNE marque » ; ça ne dépend plus de rien.

## 4. Les quatre foyers du port, et le CONTRE-EXEMPLE

**Deux natifs d'adjacence coexistent, et les confondre est la faute — dans les deux sens :**

```
MovementUtil$$AreTilesAdjacent(t1, t2)     = (|dElev| < 2) & (t1 == t2 || IsNeighbour(t1, t2))
TileQuery$$IterateAdjacentTiles(t, ...)    parcourt la liste d'adjacence STOCKEE sur `t`
                                           -> ne rend JAMAIS `t` elle-meme
```

| foyer du port | état avant | après |
|---|---|---|
| `runner/abilities/targeting.py::are_tiles_adjacent` (+ `are_entities_adjacent`) | **portait déjà** les deux termes | inchangé |
| `services/battle_query.py::are_tiles_adjacent` | portait l'identité **avec** board ; la branche dégradée SANS board rendait `hexgeo.distance(p, p) == 1` = **FAUX** | court-circuit posé avant les deux branches |
| `runner/operations/triggers/loki/teleporting_in.py` (vslot 0x748) | `board.neighbours` nu — **ni (I) ni (E)** | délègue au foyer mirror |
| `battle_query.py` (playbook) | `is_adjacent` (le mirror d'`IterateAdjacentTiles`) servait aussi à porter `AreEntitiesAdjacent` / `IsAdjacentTo` | nouveau foyer `are_entities_adjacent`, câblé sur `is_charging`, `AvalancheOfMuscle` (état 4), `AggressiveOnslaught` (gate 1) et le NonOwner `KustomForceField` |

`battle_query.is_adjacent` **reste inchangé** et le test en fait un **contre-exemple explicite** :
l'aligner « par cohérence » ferait compter chaque unité comme sa propre voisine — inflation
silencieuse de toutes les utilités de voisinage.

⚠ Sur `is_charging`, le court-circuit est **sans effet observable par COMPOSITION**, pas par chance :
le 2ᵉ terme (`ChargedUnitIds.Contains`) est écrit par `MoveUnitOperation$$UpdateCharging`, qui
n'ajoute que les unités **nouvellement** rendues par `GetAdjacentUnits` — donc par
`IterateAdjacentTiles`, qui ne rend jamais la tuile d'arrivée. La conjonction reste fausse des deux
côtés.

## 5. Ce qui a été MESURÉ

**Gisement du terme (E)** (`probe_433_r1_identity_shortcircuit.py`, étape C, offline) : sur les
**779** boards de `data/boards/**`, **739** ont un span d'élévation ≥ 2 et **695** portent au moins
une paire de tuiles **voisines** à `|dElev| >= 2` — **11 935** paires au total. Le terme n'est pas
théorique. *(Chiffres à re-dériver, pas à citer.)*

**Confrontation LIVE du terme (E)** — `MC1_67`/`777`, étape D. La cible du cast est choisie pour que
le régime soit **atteint et non subi** : une tuile marquable ayant une voisine à `|dElev| >= 2`
**déjà dans le pool de marche** d'un futur porteur (le pool ne peut que grandir après le cast,
`ATeleportPathfinder$$IterateReachableTiles` étant un décorateur).

| | marque `(4,2)` elev **4** → destination `(3,2)` elev **2**, `|dElev| = 2` |
|---|---|
| natif | `1574 cascade = {'effect_ids': [], 'received': [], 'lost': []}` — **aucun marqueur** |
| port (après) | `PENDANT le pas = [1147, 1375, 1573]` — **pas de 1574** ⇒ accord |
| port **muté** (`board.neighbours` nu) | `[1147, 1375, 1573, 1574]` ⇒ `DESACCORD sur 1574 -- port=True natif=False` |

Le critère est le **déplacement par rapport au port non muté**, pas l'écart au natif.

**Régime (I) NON CONFRONTÉ LIVE dans ce foyer, et pourquoi** : il exige `|marked| > 1`, or le cast
mesuré pose `[(4,2)]`, **cardinalité 1** (publiée par le probe). À cardinalité 1, `Contains` couvre
déjà `dest == marked[0]` : (I) y est **sans objet**. L'attestation live de (I) passe par un autre
consommateur — le filtre statique sous `OnlyAdjacent`, où elle est déjà acquise (§2, cas 1).

**Non-régression** : `probe_448_r2d_titanhammer_squad.py` VERT sur ses deux couples (`MC1_67`/777 et
`C3_26`/31337), bras `ARM-NEAR-ADJ` exercé ; `test_445_avalanche_of_muscle_pair_term_live` (5),
`test_kustom_force_field_reworked_live` (9), `test_ischarging_extra_damage_live` (7),
`test_353r1_ramming_speed_charge_tile_offline` (10) — **31 passed**.

## 6. Le cliquet

`pytest_adjacency` entre dans `scripts/ratchets.ps1` (le fichier est la source unique — sa
composition n'est pas recopiée ici). Offline pur, ~1,2 s.
**Peut rougir, mesuré** : sous mutation RÉELLE des deux foyers (retour à `board.neighbours` nu +
retrait du court-circuit sans board), **4 des 7 tests tombent** ; l'arbre a été restauré ensuite.

## 7. Résidus NOMMÉS, non portés ici

* **`#433-r3` — FERMÉ le 2026-08-02, fiche `docs/rl/case-433-r3-isadjacent-noeud-dsl.md`.** Les
  trois termes sont portés et le terme d'élévation est confronté LIVE sur deux géométries. Deux
  corrections à ce qui est écrit ci-dessous : le prédicat par paire est le **slot 0x60** sur
  `rnca9r7q6c` (pas 0x5f — décalage uniforme d'un cran depuis le build précédent), et **« threader
  le board » n'était pas un verrou** : `DslContext.board` est déjà alimenté sur les deux faces, les
  six consommateurs portés y passent tous. Le quantificateur, lui, reste **non atteint** par les
  ~20 call-sites lus (tous mono-sélecteur) — même forme de verdict que le régime (I) ci-dessus.
  Énoncé d'origine, conservé :
  `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger`, lu : il résout ses deux
  sélecteurs (`+0x20`, `+0x28`) par le **slot 3** en leur passant `+0x18` (le 3ᵉ argument de
  `DSLFactory$$IsAdjacent(a, b, n)`, qui va au SÉLECTEUR et **non** au prédicat par paire), exige les
  deux listes non vides, puis rend **FAUX dès qu'UNE paire ne l'est pas** — c'est un `∀`, pas un `∃`.
  Le port fait `any(hexgeo.distance(x, y) == 1 ...)` : **quantificateur inversé**, **pas d'identité**,
  **pas de porte d'élévation**. Non observable dans les consommateurs portés (`IsAdjacent(Caster(),
  Target())` — sélecteurs mono-entité, donc `∃ ≡ ∀`, et caster ≠ target) **sauf** le terme
  d'élévation, qui lui mord (§5). Le porter exige de threader le board jusqu'au nœud DSL : c'est un
  cas à part entière, pas une ligne.
* **`#433-r4` — les consommateurs natifs NON PORTÉS du régime d'identité** :
  `FilterTilesIfCanAttackTargetTileFromSelector$$Select`,
  `LivingBatteringRamAbility$$GetPossibleTilesToThrowTo` / `$$AlternativeThrowTiles`,
  `TilesInConeShapeForBossWideSelector`, `BattleQuery$$IsTargetInAttackRangeForSummon`. Aucun n'a de
  porteur côté port ; ils sont listés pour que le prochain qui les porte sache par où passer.
