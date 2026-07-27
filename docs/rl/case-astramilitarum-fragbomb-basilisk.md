# FragBomb (1017) & BasiliskBarrage (1026) — face COMBAT

> Deux actives **Astra Militarum** classées `DAMAGE(Blast)` par `combat-ability-coverage.md`, toutes
> deux **absentes du registre de combat** : `AbilityHandler.visit_ActiveAbilityMessage` rendait
> `ported:False` → **0 dégât, aucune erreur**. Divergence d'état SILENCIEUSE de 6 + 3×N coups
> (FragBomb) et de 5 obus × 2 coups (BasiliskBarrage).
>
> Vérification préalable exigée (contre-exemple `FrenziedFiring`) : **mesurée**, pas supposée — un cast
> live des deux abilities, rejoué offline avant port, rendait `ported:False` et zéro attaque. Aucune
> partie n'était couverte par un canal générique.

Porteurs (les DEUX dans `rl_duel.py build --list-pool`) : `astraBullgryn` « Kut Skoden » (HERO,
FragBomb, **mêlée**) et `astraOrdnance` « Thaddeus Noble » (HERO, BasiliskBarrage, **ranged, portée
illimitée**).

---

## 1. FragBomb (1017) — main + splash plombé par un `SortedAttackSeries`

### 1.1 Artefact natif

`IdunBattleLogic.Entities.Abilities.Active.Loki.FragBombAbility$$ExecuteBehaviour` (MIRROR) :

```
profile = Direct( GetDamageProfile(config, 0) )                       # Blast
h1      = GetNumberConstant(config, 0x2f)                             # nrOfHits   = 6
h2      = GetNumberConstant(config, 0x32)                             # nrOfHits_2 = 3
splash  = AdjacentUnits(Target@0x178, 0, 3) - Caster@0x160
dmg     = MinMaxDamage(this, entities)                                # minDmg/maxDmg[level]
main    = AttackDamage(Caster@0x160, ActiveTarget@0x180, dmg, profile, Get(h1), <AbilityOrEffect>)
splashA = AttackDamage(Caster@0x160, ActiveTarget@0x180, dmg, profile, Get(h2), <AbilityOrEffect>)
ExecuteAtomic( SortedAttackSeries(Caster@0x160, Units(Target@0x178,1,1), main,
                                  splash, splashA, <AbilityOrEffect>), entities, 0x43 )
```

`IdunBattleLogic.Entities.DSLFactory$$AdjacentUnits(x, a, b)` = `Units(AdjacentTiles(x), a, b) - x`
(décompilé) → le splash = occupants des tuiles **hex-adjacentes à la cible**, MOINS la cible, MOINS le
caster. **Aucun wrapper `Enemies(...)`** → FRIENDLY-FIRE (i2 : « ALL units adjacent to the target hex,
except Kut Skoden himself »). Config 1017 : aucune variable `_2` → plage de dégât PARTAGÉE, seule la
constante de coups diffère.

### 1.2 Ce que `SortedAttackSeries` change (le vrai point du cas)

`IdunBattle.Entities.Behaviours.SortedAttackSeriesBehaviour` (ctor `+0x50` acteur, `+0x58` tableau de
2 paires `(sélecteur, behaviour)`, `+0x60..0x70` `AbilityOrEffect`) :

- `$$GetAttacks` construit un `Dictionary<unité, List<behaviour>>` en **parcourant les paires dans
  l'ordre du tableau**, puis chaque sélecteur **dans son ordre** ;
- `$$Execute` itère ce dictionnaire **en ordre d'insertion**, pose `entities[slot 4]` (=
  `ActiveTarget@0x180`) sur l'unité courante, exécute ses behaviours, et encadre chaque changement de
  cible par les opérations `0x3a`/`0x3b` (Start/EndAttackSeries — bornes d'ANIMATION, aucune mutation,
  aucun tirage : non portées).

Deux conséquences, toutes deux observables :

1. **AUCUN `OrderBy`** — contraste `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`, qui trie
   dès que `Count > 1` (c'est ce tri que le mode `multi=True` de la feuille mirrorait jusqu'ici).
   L'ordre d'attaque, donc la SÉQUENCE de tirages `state.rng`, est celui du SÉLECTEUR.
2. **L'ordre du sélecteur est le voisinage NATIF de la tuile ciblée**, pas l'ordre trié par id que rend
   `Board.neighbours`. MESURÉ (`probe_fragbomb_splash.py`, MC1_67, cible tuile 44, voisins natifs
   `[45, 53, 52, 43, 34, 35]`) : coups splash live dans l'ordre `53, 52, 43, 35` = l'ordre natif privé
   du caster (45) et de la tuile vide (34). L'ordre trié `[34,35,43,45,52,53]` aurait donné
   `35, 43, 52, 53`.

D'où, côté port : une feuille `SortedAttackSeries` qui mirror la boucle ci-dessus, alimentée par
`AdjacentTiles` — dont l'ordre est **déjà** `Board.neighbours_native` de façon INCONDITIONNELLE
(R28-1, arrivé sur `master` pendant ce cas). Ce call-site en est le **2ᵉ confront live** : la mesure
ci-dessus, faite indépendamment, retombe exactement sur la loi de R28-1.

### 1.3 Observable

Cible = `nrOfHits` (6) coups Blast ; **chaque** unité adjacente à la tuile ciblée — alliés du caster
COMPRIS — = `nrOfHits_2` (3) coups ; le CASTER = rien.

---

## 2. BasiliskBarrage (1026) — un barrage d'obus sur des TUILES

### 2.1 Artefact natif

`IdunBattleLogic.Entities.Abilities.Active.Loki.BasiliskBarrageAbility$$ExecuteBehaviour` (MIRROR) :

```
total      = Direct( GetNumberConstant(0x1f) = nrOfProjectiles )                 # $$GetNumShellsTotal
guaranteed = Min( Max( Zero@0xb8, Difference( StatAmount(Caster@0x160, 0xc = TurnsStarted),
                                              One@0xc0 ) ), total )              # $$GetNumShellsGuaranteed
miss       = Max( Zero@0xb8, Difference( Difference(total,
                                          Direct(GetNumberConstant(0x38) = nrOfProjectiles_2)),
                                         guaranteed ) )                          # $$GetNumShellsMiss
maybe      = Max( Zero@0xb8, Difference(total, Sum(guaranteed, miss)) )          # $$GetNumShellsMaybe
sel = ( Cache(PickRandomly(TilesAtDistance(Target@0x178, 2),                     miss,      1, 0x7fffffff, false))
      + Cache(PickRandomly(TargetTiles@0x190 + TilesAtDistance(Target@0x178, 1), maybe,     1, 0x7fffffff, false)) )
      + Cache(PickRandomly(TargetTiles@0x190,                                    guaranteed,1, 0x7fffffff, false))
Execute( AtomicGroup(0x54, AttackWithAbilityDamage(Caster@0x160, sel, MinMaxDamage,
                                                   GetDamageProfile(config,0)=Blast,
                                                   GetNumberConstant(0x2f)=nrOfHits, <AbilityOrEffect>)) )
```

`DSLFactory@0xb8`/`@0xc0` = `Direct(0)`/`Direct(1)` (posés par `IdunBattleLogic.Entities.DSLFactory$$.ctor`
— LUS, pas devinés). Config 1026 : `nrOfProjectiles=5`, `nrOfProjectiles_2=3`, `nrOfHits=2` →
`guaranteed` = nombre de **rounds terminés** par le caster, `miss = max(0, 2 - guaranteed)`, `maybe` =
le reste. C'est exactement l'i2 : « {nrOfProjectiles_2} randomly hit the target hex or surrounding
hexes and the remaining 2 hit the hexes surrounding those. For each round that has ended, 1 more of
the shells hits the target hex, starting with the shells hitting the outer hexes. »

### 2.2 Trois lectures qui décident du résultat

**(a) `allowRepeat = 1`.** `IdunBattle.Entities.Selectors.PickRandomAmountSelector$$.ctor` mappe
`(…, allowRepeat -> +0x30, maxRepeats -> +0x34, skipForced -> +0x38)` ; 1026 passe `1 / 0x7fffffff`
(contraste Fragstorm `0 / 0x7fffffff`). Dans `$$Select`, la branche `allowRepeat` ne retire le candidat
que lorsqu'il apparaît `maxRepeats` fois — jamais ici. **Le pool ne rétrécit pas et deux obus peuvent
tomber sur la même tuile** : une unité encaisse alors `2 × nrOfHits` coups (mesuré : 6 coups sur la
cible avec `guaranteed=2` + 1 obus `maybe` sur la même tuile).

**(b) L'ORDRE des pools** (il décide quelle tuile `ElementAt(idx)` désigne).
`TilesAtDistanceSelector$$Select` → `BattleQuery$$GetTilesAtDistance(tile, d, false)` =
`GetSurroundingTiles(tile, d, requireEmptyOrSteppable=false, checkWalkable=0, unitFilter=0,
includeSelf=1)` filtré à `PositionComponent.Distance == d`. L'ordre est celui de la **triple boucle
cube ASCENDANTE** de `IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`
(déjà mirrorée par `battle_query.get_surrounding_tiles`, #57g) — **pas** l'ordre trié par id, **pas**
l'ordre `neighbours`. CONFRONTÉ live (`probe_basilisk_shell_rng.py`, 7 seeds, MC1_67) : sur les
24 permutations du pool ring-2 × 6 ordres de tirage × 3 hypothèses de pool, **une seule** rejoue 7/7 les
tuiles d'impact depuis le MT capturé — `miss` puis `maybe` puis `guaranteed`, pools dans l'ordre cube,
`TargetTiles@0x190` EN TÊTE du pool « maybe ».

**(c) Le filtre du pool est `isWall`, PAS `walkable`.** `TileUtil$$IsTileValidForList(tile, ref,
checkWalkable=0, 0)` se réduit à `TileComponent+0x41 == 0 && TileComponent+0x40 == 0` : ni la porte
`IsWalkable` (mur **ET** occupation) ni la porte d'élévation. GROUND TRUTH : le board `C3_01` a
**14 tuiles `walkable=false` / `isWall=false`**, et le LIVE fait tomber un obus sur l'une d'elles
(tuile 41, ring-1 de la cible). Un filtre `walkable` l'excluait du pool → cardinal du pool faux →
**tout le tirage désynchronisé** (3 casts sur 3 divergents sur C3_01, 3/3 bit-exacts après correction).

### 2.3 Résolution tuile → unité

`AttackWithAbilityDamage` = `AttackBehaviour(caster, <tuiles>, AbilityDamageBehaviour(...))`. Deux
étages, tous deux couverts par le mode `tile_domain=True` de la feuille — mode **déjà présent sur
`master`** (porté pour le splash en HEXES de Fragstorm) : ce cas n'y ajoute que l'émission
diagnostique `AttackEmptyTile`, dont le test a besoin pour confronter les obus tombés à vide.

1. `AttackBehaviour$$Execute` résout la liste puis l'`OrderBy` quand `Count > 1` — clé mesurée sur des
   entités-TUILE = **id de tuile ASCENDANT** ; les DOUBLONS sont conservés (le natif itère la liste) ;
2. `AbilityDamageBehaviour$$Execute` fait `UnitExtensions.GetUnit(tile)` par entrée : tuile SANS unité
   → aucune attaque, seulement l'opération visuelle `0x25` (tag live `Damage_Empty_Target_Tile_Id`),
   portée en `emit('AttackEmptyTile')` (diagnostic, confronté au live dans le test).

Famille d'opération : `AbilityDamageOperation` (1 tirage/coup, AUCUN crit, aucune feuille positionnelle)
→ `native_factory="ability"` (même classification que PlasmaGrenade, rngcrit-1202).

### 2.4 Observable

`nrOfProjectiles` obus ; chacun inflige `nrOfHits` coups Blast à l'occupant de sa tuile. Les unités
touchées reçoivent en plus `Pinned`/Suppressed — trait `SuppressiveFire` du carrier (i2 : « The
Suppressive Fire trait applies also to this ability »), canal déjà porté côté trigger.

---

## 3. Validation (live, MT seedé avant le cast)

`probe_fragbomb_basilisk.py --ability {fragbomb|basilisk}` monte un runner isolé, DRIVE les deux camps,
capture `decisionView`/`observeBattle`/`combatSnapshot`/`dumpRng`, joue le cast LIVE, rejoue le MÊME
cast offline depuis l'état capturé et le MÊME MT, puis compare **coup par coup**.

| ability | couverture | résultat |
|---|---|---|
| FragBomb 1017 | boards MC1_67 / C3_01 / C4_09, seeds 777/31337/4242/999, géométries `crowded` (cible + 4 adjacents dont 1 ALLIÉ) et `alone` | **8/8 casts bit-exacts** (18 coups/cast en `crowded`) |
| BasiliskBarrage 1026 | boards MC1_67 / C3_01 / C4_09, seeds 777/31337/4242/999, `TurnsStarted` 1→4 (`guaranteed` 0/1/2/3), géométries `crowded` et `alone` | **15/15 casts bit-exacts** (tuiles d'impact, doublons, tuiles vides, per-coup) |

Cas discriminants couverts : obus DOUBLE sur la tuile ciblée (6 coups), obus double sur une tuile VIDE,
obus sur une tuile `walkable=false`, friendly-fire (allié touché par le splash FragBomb ET par un obus
Basilisk), caster JAMAIS touché par son propre splash, cible isolée → splash vide.

Gardes : `tests/engine/runner/test_frag_bomb_live.py` (2 tests) et
`tests/engine/runner/test_basilisk_barrage_live.py` (2 tests), tous deux montés sur la fixture
réutilisable `tests/engine/runner/_ringed_cast.py::ring_scenario` (cible au centre d'un hexagone
plein à 6 voisins **tous marchables**, un ALLIÉ dans l'anneau, N rounds écoulés avant le cast) —
extraite ici parce que les trois garanties qu'elle pose sont exactement celles dont l'absence rend
un test AoE silencieusement faux : voisinage sous-exercé, friendly-fire non discriminant, et bonus
de charge parasite.

---

## 4. Résidus nommés

- **`AvalancheOfMuscle_ExtraDamage` (1025) — gate `IsCharging` non porté.** HORS de ce port. Si le
  Bullgryn A BOUGÉ pendant le tour du cast, le natif ajoute `+extraDmg[niveau passif] × multiplicateur`
  FLAT par coup sur les ennemis **adjacents au caster**. MESURÉ (`probe_avalanche_charge_gate.py`,
  passif niveau 50, multiplicateur 180 % → `extraDmg = 599`) : sans charge, 4/4 coups bit-exacts ; avec
  charge, `+599` sur chaque coup. **Se reproduit à l'identique sur l'ATTAQUE NORMALE du même porteur**
  (chemin qui ne traverse aucune ligne de FragBomb) ⇒ résidu du PASSIF, pas de ce port. Le gate est déjà
  documenté comme non exprimable dans le canal modifier EAGER (`BlackRage_ExtraDamage`,
  `FeederTendrils_ExtraDamage`). Les gardes castent donc depuis un tour où le caster n'a pas bougé.
- **`TileComponent+0x41`** (2e drapeau de tuile du filtre `IsTileValidForList`) n'a aucun substrat
  offline distinct d'`isWall` → non filtré.
- **Gates par-cible d'`AbilityDamageBehaviour`** — `UnitExtensions.IsTargetable` et
  `HasTrait(0x40e = UnitTrait.Invincible)` — non portés (l'occupant résolu est déjà VIVANT ; aucun
  porteur d'`Invincible` dans un roster de duel).

## 5. Masques de ciblage — POSÉS, et l'un d'eux corrige une lecture de ce dossier

Les deux ctors passent l'overload à **7 arguments** de `IdunBattle.Core.Services.TargetingOptions$$.ctor`
(« flags directs »), dont le corps écrit `options+0x28 <- param_5` **sans OR** :

```
FragBombAbility$$.ctor        : TargetingOptions..ctor(&opts, 0, <TargetingRange statics+0x30>, 1, 0x80040, 0, 0)
BasiliskBarrageAbility$$.ctor : TargetingOptions..ctor(&opts, 0, <TargetingRange statics+0x48>, 1, 0x80050, 0, 0)
```

Ce n'est **pas** l'overload piège « PRESET + flags » (3 arguments), dont le corps fait
`+0x28 = flags | preset[+0x28]` : celui-ci ne reçoit qu'un `TargetingRange` de 0x18 octets, qui n'a
pas de champ `+0x28`. Le littéral **est** donc le masque effectif :

| ability | `rules` | décodage | `range` (`TargetingRange$$.cctor`) |
|---|---|---|---|
| 1017 FragBomb | `0x80040` | `TargetIsTile \| TargetTileHasEnemyUnit` | `statics+0x30` = `RANGE_ADJACENT` (cohérent avec `attackRangeType=Melee`) |
| 1026 BasiliskBarrage | `0x80050` | `CasterHasNotMoved \| TargetIsTile \| TargetTileHasEnemyUnit` | `statics+0x48` = `RANGE_WHOLE_BOARD` (i2 « any target on the battlefield ») |

`forceMeleeTarget` = 4ᵉ argument = `1` = `RangedBool.False` pour les deux.

**Ce que ça corrige** : le gate i2 « If Thaddeus Noble has not moved » n'est PAS une couche de
disponibilité séparée — c'est le bit `CasterHasNotMoved` **du masque de ciblage**. La première
rédaction de ce dossier le rangeait hors face COMBAT ; la lecture du ctor le ramène dedans, et le
port le gate désormais. Confirmation croisée : le masque, lu indépendamment de l'i2, prédit
exactement la contrainte que l'i2 énonce.

`ABILITY_ATTACK_TYPE` : les deux ctors appellent `AActiveAbility..ctor(this, &opts, 0)` → 3ᵉ argument
`0` = `DirectTargetAttack`. Le cliquet `tests/engine/runner/test_ability_registry_ratchet.py` couvre
les deux données (il rejetait les deux abilities avant ce commit).
