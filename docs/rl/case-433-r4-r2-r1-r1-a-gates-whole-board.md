# #433-r4-r2-r1-r1-a — les gates `UseWholeBoard` qui n'avaient pas été lus

**Verdict : FERMÉ.** Les gates restants ont été lus au décompilé. **Aucun n'est réductible à un
rayon** — la réponse au critère binaire est donc négative, et c'est un résultat, pas un échec : la
lecture a fait apparaître **deux autres étages**, dont l'un rend la zone **EXACTE** (pas une borne)
pour deux abilities, et l'autre justifie le statu quo pour les sept restantes au lieu de le subir.

## 1. Le compte : **9**, pas 11

Re-dérivé du code sur `origin/master` (`probe_433_r4_r2_r1_r1_a_whole_board_gates.py --step read`) :
**32** abilities `UseWholeBoard` connues du port, **19** surchargent le slot `klass+0x478`, ventilées
en 2 lues-dérivables (`#558`), 8 lues-non-dérivables (`#558`) et **9** `GATE_NOT_READ`. Le « 11 » de
la fiche héritée comptait les deux gates **déjà lus** avec les non lus.

    1011 TunnelingHorror   1025 SkyStrike        1100 SorcerousFacade
    1143 ForwardSpotter    1145 SporeMineLauncher 1168 EntropyCannons
    1200 SquigLaunchas     1201 SquigMine        1213 DeathOnTheWind

## 2. Les trois étages, LUS

```
AttackQuery$$GetAllTilesInAbilityRange(unit, position, ability)      # slot 0xe, 3 args
    <slot 0x14 CanCurrentlyBeUsed> && !<slot 0x13 IsAbilityBlocked> && !IsInvalid(GetInvalidCasterReason)
    tiles = <slot 9 GetPossibleTargetTiles>(ability, unit, position.MainTile)   # + slot 10

AActiveAbility$$GetPossibleTargetTiles -> TargetingQuery$$GetPossibleTargetTiles
    (1) if ((rules >> 0xa & 1) && !(rules >> 0xe & 1)) return new OrderedSet<Tile>();
    (2) range = GetRange(...) ; set = GetTilesInRange(...)          # UseWholeBoard -> GetAllTiles()
    (3) GetPossibleTargetsForOptions(..., onlyTiles: 1)
            RemoveAll(b__0) ; RemoveAll(b__1) ; if (rules & 2) RemoveAll(b__2)
```

**(1) est neuf, et c'est le résultat principal.** `TargetIsFriendly` **sans** `TargetIsEnemy` ⇒
zone **VIDE**, avant `GetRange` et avant tout gate. C'est purement statique (le masque du ctor),
donc **exact**. `1100 SorcerousFacade` et `1143 ForwardSpotter` y tombent : elles surchargent bien
le slot, mais **leur gate n'est jamais atteint**.

**(3) décide sur quoi porte le gate.** La lambda
`TargetingQuery.u003Cu003Ec__DisplayClass34_0$$u003CGetPossibleTargetsForOptionsu003Eb__2` ne passe
pas l'élément au délégué, mais l'entité qu'elle en **résout** :

```
entity = (rules & TargetIsTile) ? EntityExtensions.GetMainTile(elem)
                                : UnitExtensions.GetUnit(elem)
delegate.Invoke(caster, casterTiles, entity, GetTiles(entity) ?? GetTiles(elem))
```

Or `GetPossibleTargetTiles` force `onlyTiles: 1` : les éléments **sont des tuiles**. Sur une tuile
**vide**, une ability sans `TargetIsTile` reçoit donc `entity == null` — et
`IdunBattle.Entities.EntityExtensions$$IsUnit` teste le nul **avant tout**, donc rend `false`.

## 3. Les neuf, un par un

| id | symbole du gate | ce qu'il teste | classement |
|---|---|---|---|
| 1100 | `SorcerousFacadeAbility$$GetDynamicInvalidTargetReason` | `HasTrait(target, 0x3ea)` + nœud DSL | **jamais atteint** — zone VIDE |
| 1143 | `ForwardSpotterAbility$$GetDynamicInvalidTargetReason` | `IsUnit(target) ? caster == target : 1` | **jamais atteint** — zone VIDE |
| 1011 | `TunnelingHorrorAbility$$GetDynamicInvalidTargetReason` | `DSLTriggers$$HasEffect(…, 0x459)`, sinon 1re `TileExtensions$$IsTemporary` des `casterTiles` | `GATE_VALID_ON_EMPTY_TILE` |
| 1025 | `SkyStrikeAbility$$GetDynamicInvalidTargetReason` | `UnitExtensions$$DidMove(caster)` + voisines libres de la cible | `GATE_VALID_ON_EMPTY_TILE` |
| 1145 | `SporeMineLauncherAbility$$GetDynamicInvalidTargetReason` | `TileExtensions$$HasSteppableUnit` puis `UnitExtensions$$IsEnemy` | `GATE_VALID_ON_EMPTY_TILE` |
| 1168 | `EntropyCannonsAbility$$GetDynamicInvalidTargetReason` | `IsUnit`, puis `DSLTriggers$$IsInTeamContagionsOfNurgleAura` / `HasNegativeModifier` | `GATE_VALID_ON_EMPTY_TILE` |
| 1200 | `SquigLaunchasAbility$$GetDynamicInvalidTargetReason` | `IsUnit`, puis `HasMinimumAdjacentOrks` / `HasMinimumAdjacentFriendlyUnits` | `GATE_VALID_ON_EMPTY_TILE` |
| 1201 | `SquigMineAbility$$GetDynamicInvalidTargetReason` | `HasEffect(tile, 0x5a1)` ou `HasSteppableUnit(tile)` | `GATE_VALID_ON_EMPTY_TILE` |
| 1213 | `DeathOnTheWindAbility$$GetDynamicInvalidTargetReason` | `GetUnit(tile)` puis `GetNumAttacksReceivedThisTurn != 0` | `GATE_VALID_ON_EMPTY_TILE` |

**Aucun ne borne une distance.** Les deux seuls régimes de rayon restent `1153` et `1177`.

## 4. Confrontation live — les neuf, mesurées

Montage : branche A pure d'`EarlyWarningOverridePlaybook` (`bonus = util + 10·Σ_E d(P,E)` ; `0` = en
zone), sweep **40 positions `d = 2..10`**, **un seul ennemi vivant**, board `MC1_67`. L'ability est
**greffée seule** (`catalog_inject`, `replace=True`) sur `custoBladeChampion`, **arme de mêlée
seule** — le probe **refuse** un greffon dont l'arme porterait au-delà de `d = 1`, sans quoi « zone
= portée d'arme » donnerait le bon résultat par coïncidence. Les deux modèles en compétition rendent
alors `40/40` ou `0/40` : séparation maximale.

| ability | porteur | natif | port | écart |
|---|---|---|---|---|
| 1100 SorcerousFacade | **natif `thousTzaangor`** | **2/40** (`d = 2` = son arme) | **EXACT** | 0 |
| 1143 ForwardSpotter | greffe | **0/40** | **EXACT** | 0 |
| 1145 SporeMineLauncher | greffe | 40/40 | **EXACT** | 0 |
| 1201 SquigMine | greffe | 40/40 | **EXACT** | 0 |
| 1025 SkyStrike | greffe | 40/40 | **EXACT** | 0 |
| 1011 TunnelingHorror | greffe (+`1060` monté par le natif) | 35/40 | 5 FP | obscurcissement |
| 1168 EntropyCannons | greffe | 34/40 | 6 FP | 5 + tuile **occupée** |
| 1200 SquigLaunchas | greffe | 34/40 | 6 FP | idem |
| 1213 DeathOnTheWind | greffe | 34/40 | 6 FP | idem |

**Avant cette tranche, les neuf rendaient le plateau entier** : `1100` faisait **38 faux positifs**
sur son propre porteur natif, `1143` en faisait **40**. Après : **0 et 0**, et **0 faux négatif
partout** — le port ne rétrécit jamais.

## 5. L'écart résiduel est ATTRIBUÉ, pas supposé

Deux témoins **sans aucun gate** (`rules & 2 == 0` : le troisième prédicat n'est même pas construit)
tranchent :

* **`1161 TwinSmartMissileSystem`** — pas de gate, pas les bits d'obscurcissement : **mêmes 5
  refus**. Un écart qu'une ability sans gate reproduit ne peut pas être imputé au gate.
* **`1147 HadesAutocannons`** — pas de gate, mais `AllowObscuredTargetByElevation` (`0x2000000`)
  **et** `AllowObscuredTargetByWalls` (`0x4000000`) : **40/40**.

Le discriminant est donc **le masque**, et l'étage responsable est le **deuxième** prédicat de
`GetPossibleTargetsForOptions` — le résidu **`#433-r4-r2-r1-r2`**, hors de cette tranche. Il se
prédit désormais : les `UseWholeBoard` qui y sont soumises sont exactement celles à qui manque un
des deux bits.

La **sixième** position n'appartient qu'aux gates qui lisent l'occupant (`1168`, `1200`, `1213`) et
c'est **exactement la tuile du caster** — la seule occupée du sweep. C'est l'écart nommé du régime
`GATE_VALID_ON_EMPTY_TILE`, **observé** et chiffré à **1 tuile sur 40**.

## 6. Ce qui est porté

`engine/services/ability_range.py` — `target_tiles_zone_is_empty` (étage 1, exact) en tête de
`ability_range_value` et de `_ability_covers_tile` ; régime `GATE_VALID_ON_EMPTY_TILE` dans
`DYNAMIC_TARGET_GATE_BY_ABILITY`. **Rayon de souffle mesuré** : sur les 105 unités du pool, **une
seule** voit son `unit_threat_reach` changer — `thousTzaangor`, plateau entier → **2**. Les autres
porteuses d'une ability *friendly-only* gardent leur zone par une **autre** ability (ex.
`astraOrdnanceBattery` par `1142 MalleusRocketLauncher`).

Le court-circuit ne s'applique qu'aux abilities du **registre** : `TARGETING_RANGE_BY_ABILITY` ne
porte que le volet portée, pas le masque. Sans masque lu, le port ne retire rien — l'écart ne peut
qu'élargir, même arbitrage que `GATE_NOT_READ`.

## 7. Résidus

* **`-a-r1` — la tuile OCCUPÉE**, mesurée à 1/40. Trois des sept gates la retirent ; le port ne
  modélise pas l'occupation. Même canal manquant que **`-r1-r1-b`**, à qui il se rattache.
  *Point d'ancrage* : publier l'occupation par tuile dans le canal qui porte déjà l'élévation.
* **`#433-r4-r2-r1-r2` (obscurcissement) — FERMÉ (2026-08-04).** L'attribution par le masque était
  juste, et elle a suffi à porter l'étage : `docs/rl/case-433-r4-r2-r1-r2-ligne-de-vue.md`.
  Le `ObscuringType` prédit les **douze** mesures de ce dossier sans une réfutation, et les cinq
  écarts de `1161`/`1011` tombent à **0**. Les 6 FP de `1168`/`1200`/`1213` deviennent **1** — la
  seule tuile OCCUPÉE, soit le résidu `-a-r1` ci-dessus, seul survivant.
* **`GATE_NOT_READ` subsiste sur 16 abilities**, toutes **non-`UseWholeBoard`** : leur borne
  supérieure reste bornée, donc ne pas rétrécir y coûte au plus le disque de leur portée. Un test
  offline le verrouille — un `GATE_NOT_READ` sur une zone whole-board rougirait.
* **NON COUVERT** : `1187 ThriceBlessedConflagration` et `1214 Hailstrike`, `UseWholeBoard` et
  *friendly-only*, bénéficient du même court-circuit sans avoir été confrontées (aucun porteur du
  pool n'isole leur zone). Leur classement suit du **masque lu**, pas d'une mesure.

## 8. Validation

* **OFFLINE** — `tests/engine/test_433_r4_r2_r1_r1_a_whole_board_gates_offline.py` : **26 passed**.
* **LIVE** — `tests/engine/test_433_r4_r2_r1_r1_a_whole_board_gates_live.py` : **3 passed** (zone
  vide sur porteur natif, plateau entier sur greffe, et l'attribution par les deux témoins).
* **NON-RÉGRESSION** — `test_433_r4_r2_r1_ability_range_live.py` **6 passed**,
  `test_433_r4_r2_adjacency_foyer_live.py` **7 passed**,
  `test_433_r4_r2_r1_r2_ability_range_offline.py` + `test_433_r4_r2_r1_r1_dynamic_target_gate_offline.py`
  + `test_433_r4_r2_adjacency_foyer_offline.py` **46 passed**.
