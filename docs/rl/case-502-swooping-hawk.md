# #502 — `1064 Loki_SwoopingHawk` : une VAGUE EN LIGNE, et un atterrissage

**Etat : LIVRE.** Face COMBAT portee, confrontee LIVE bit-exact (topologie + degat rang par rang +
position finale), sur `rnca9r7q6c`. Porteur : `eldarAutarch` « Aethana » (Aeldari, HERO, dans le
pool rank 17) ; trois autres porteurs sont npc (`eldarBossAutarch`, `...Camp`, `...LHE`).

Avant : 1064 etait absente d'`ABILITY_CLASSES` -> la decision CHOISISSAIT le cast et l'execution
l'IGNORAIT (0 degat, 0 deplacement, aucune erreur).

## 1. L'artefact natif

`IdunBattleLogic.Entities.Abilities.Active.Loki.SwoopingHawkAbility$$.ctor` a pour corps ENTIER
`return DiveAttackAbilityBase$$.ctor(this);` — **aucune methode propre**. Toute la mecanique vit sur
`IdunBattleLogic.Entities.Abilities.Active.Loki.DiveAttackAbilityBase` (`.ctor`, `ExecuteBehaviour`,
`GetTargetTilesSelector`, `GetTargetUnitsSelector`, `GetMovementBehavior`). L'autre heritiere est
`1091 SlashingDive` — meme code, config differente (profil `Power`). **PORTEE depuis #507**
(`case-507-slashing-dive.md`), qui a aussi deplace la base partagee dans son namespace natif
(`engine/runner/abilities/loki/dive_attack.py`) : les deux heritieres n'y ajoutent plus que leur
identite et leurs deux donnees de registre — comme le natif, dont les classes filles n'ont qu'un ctor.

    GetTargetTilesSelector() =
      DSLSelectors$$First( DSLSelectors$$TilesBehindInLine(
            origin    = <DSLSelectors+0x50> CasterTile,
            direction = DSLSelectors$$First(
                            DSLSelectors$$SortByDistance(
                                DSLSelectors$$Tiles(<DSLSelectors+0x60> Target),
                                <DSLSelectors+0x50> CasterTile), 1),
            settings = NULL, maxAmount = NULL ), 3 )

    ExecuteBehaviour(abilityState, entities) =
      dmg   = AbilityConfiguration$$GetVariableArrayForLevel(cfg, 0xb = AbilityVariableType.dmg)   # 3 valeurs
      hitsF = DSLFormulas$$Direct( GetNumberConstant(cfg, 0x2f = AbilityConstantType.nrOfHits) )
      prev  = DSLSelectors$$None() ;  last = <DSLSelectors+0x60> Target ;  result = DSLBehaviors$$Nothing()
      for (i = 0 ; i < 3 ; i++) :
          cur   = DSLSelectors$$Cache( Enemies(Caster@0x48, Units(AtIndex(tiles, i), 0, 0), 0), 1 )
          next_ = Enemies( Caster@0x48, Units(AtIndex(tiles, i+1), 0, 0), 0 )
          b = Nothing()
              & If( !AreEqual(cur, prev),  DSLBehaviors$$StartAttack(Caster@0x48, cur, aoe) )
              & DSLBehaviors$$AbilityDamage(Caster@0x48, cur, Direct(dmg[i]), profS, hitsF, aoe, false, 2)
              & If( !AreEqual(cur, next_), DSLBehaviors$$FinishAttack(Caster@0x48, cur, aoe) )
          result &= If( AmountIsGreaterThanZero(cur), b )
          if (cur.<vtable+0x2b8>(entities) > 0)  last = AtIndex(tiles, i)     # EVALUE A LA CONSTRUCTION
          prev = cur
      return AActiveAbility$$ExecuteAtomic( result + GetMovementBehavior(last), entities, 0x2a )

    GetMovementBehavior(last) =
      behind   = DSLSelectors$$CanAddUnit( DSLSelectors$$TileBehindTargetFromSourceDirection(last, Owner@0x30) )
      fallback = First( SortByDistance( Randomize(CanAddUnit(AllTiles@0x18)) + CasterTile@0x50, last ), 1 )
      sel      = DSLSelectors$$ConditionalSelector( AmountIsGreater(Count(behind), Get(0)), behind, fallback )
      return     If( DSLTriggers$$CanMove(Caster@0x48), DSLBehaviors$$MoveUnit(Caster@0x48, sel, options = {0}) )

L'i2 dit exactement cela : « *deals a wave of damage from an initial melee target to targets up to
2 hexes behind. 1x dmg[0] ... to first target, 1x dmg[1] to the second, 1x dmg[2] to the third.
Lands in the hex directly behind the last target hit, or - in case that hex is occupied - to the
closest free hex to it.* »

## 2. Cinq lectures qui ne se devinent pas

Detail dans la docstring de section de `engine/runner/abilities/aeldari.py`.

1. **`DSLSelectors$$First(source, amount, ignoreForcedTargets)` est un CARDINAL, pas un index.** Il
   boxe son `amount` en `DirectAmount` et construit un `PickFirstNSelector` ; `DSLFactory$$First`,
   lui, construit un `PickAtIndexSelector`. Homonymes, factories distinctes. Le deroulage de la
   boucle passe par `DSLSelectors$$AtIndex`, qui EST le PickAtIndex.
2. **`settings = NULL` n'est pas une absence.** `TilesBehindInLineSelector$$.ctor` construit alors
   un `TilesBehindSettings` par defaut (tous champs a zero) -> `check_walkable = False` ET
   `update_reference = False`. La ligne n'est bornee que par le **bord du plateau** — ni
   walkabilite, ni elevation. Lire « NULL » comme un crash potentiel etait la premiere hypothese ;
   le ctor la refute.
3. **L'ordre `(source, target)` se tranche au CTOR, pas au nom.** La factory
   `DSLSelectors$$TileBehindTargetFromSourceDirection` prend `(target, source)` ; le ctor du
   selecteur ecrit `+0x18 = sourceTileSelector`, `+0x20 = targetTileSelector`, et `Select` appelle
   `query.<slot 0x59>(Select(+0x18), Select(+0x20))` = `(source, target)`. Les deux ordres sont
   **inverses** ; s'en remettre au nom ferait atterrir le caster ENTRE lui et sa cible.
4. **`last` est fige AU CAST, sur la derniere tuile PORTANT un ennemi.** La boucle native fait deux
   choses de natures differentes : elle ASSEMBLE le behaviour *et* elle EVALUE `cur` immediatement
   (`<vtable+0x2b8>`, un cardinal). Consequences observables : une unite tuee par le 1er coup compte
   quand meme comme « derniere cible touchee », et l'evaluation **remplit le `Cache`** — l'ensemble
   des ennemis de chaque tuile ne change plus pendant l'execution.
5. **`CasterTile` est UNIONNEE au pool de repli.** Le caster peut donc « atterrir » sur sa propre
   tuile, c'est-a-dire ne pas bouger : c'est ce qui garantit que le repli n'est jamais vide.

`CubeCoordinate$$DirectionTo` a demande sa propre lecture (convention x64 : `RCX` = buffer de
retour, `RDX` = `this`, `R8` = l'argument — Ghidra decale d'un cran) : **`a.DirectionTo(b) =
clamp(a - b, -1, +1)`**, un pas unitaire pointant de `b` VERS `a`. Le sens est contre-intuitif et
c'est le seul autre consommateur porte (`get_tiles_behind`) qui le confirme.

## 3. Ce qui a ete mesure LIVE

`probe_502_swooping_hawk.py` — trois scenarios sur `MC1_67`, positions FORCEES (`--place` /
`--a-place`), MT offline cale sur `dumpRng` avant chaque comparaison. Cibles de MELEE (`orksNob`) :
le premier montage utilisait des `eldarRanger`, dont l'`Overwatch_AutoAttack` **tue le caster a
l'atterrissage** et rend l'etage position inobservable.

| scenario | topologie | degat (port == natif) | position finale |
|---|---|---|---|
| VAGUE — 3 ennemis alignes | 3 tuiles | `2871 / 73 (block) / 1597` | `(3,0) -> (3,4)` |
| REPLI — tuile d'atterrissage occupee | 3 tuiles | idem | `(3,0) -> (4,3)` |
| ANCRE — 1 seule cible | 1 tuile | `2871` | `(3,0) -> (3,2)` |

Tous les montants sont **bit-exacts** des deux cotes, et les positions finales concordent.
`crit = 0` sur tous les coups (famille ABILITY : `AbilityDamageOperation` n'a **aucun** slot
`RollCritical` — c'est un OBSERVABLE, pas une simplification) ; `DamageProfileType = 20` = `Piercing`
lu au gameconfig ; le `GroupType` natif **42 = `0x2a`** confirme `ExecuteAtomic(..., 0x2a)`.

**Les trois faces du kit sont SEPAREES**, jamais absorbees dans un total : `pierce` par le
`DamageProfileType` de chaque coup, `dmg_bonus` par le **ratio `montant / dmg[rang]`** (0,7999 et
0,8001 aux deux rangs non bloques — identique, donc le port indexe bien `dmg[i]` au lieu de figer un
montant), `crit` par son absence mesuree.

**Temoin de non-degenerescence** assertionne, pas suppose : les montants doivent etre non nuls ET
deux a deux differents. Sans lui, un splash serait indiscernable d'une vague. Le scenario ANCRE est
le seul ou « derniere tuile OCCUPEE » et « derniere tuile de la ligne » divergent — un port qui
prendrait la fin de la ligne passe les deux autres scenarios et tombe la.

`tests/engine/runner/test_swooping_hawk_live.py` : **11 tests**, tous verts.

## 4. Ce qui est ENTRE et ce qui est SORTI (contrat de disjonction)

Entrees : `ABILITY_CLASSES` (`handler.py`) et `ABILITY_ATTACK_TYPE` (3e argument du
`AActiveAbility$$.ctor` de la BASE = `0` = `DirectTargetAttack`, valable pour les deux heritieres).
Sorties, dans le meme commit : `TARGETING_OPTIONS_UNPORTED` (+ compteur d'en-tete `STATIC-COPY`
**8 -> 7**), `POOL_ABILITIES_WITHOUT_COMBAT_CLASS`, et le snapshot `SNAP_TARGETING_UNPORTED`
(cardinalites **38 -> 37** et **122 -> 121**).

Masque RELU sur ce ctor, pas recopie d'une voisine : preset statique `+0x40`, `*(statics+0x68) =
0x4000` = `TargetIsEnemy` SEUL, `forceMeleeTarget = RangedBool.False`, `range = RANGE_ADJACENT`.
Aucun bit dynamique -> l'absence de 1064 dans `DYNAMIC_TARGET_RULE_UNPORTED` est EXACTE.

## 5. Noeuds DSL neufs

`AtIndex` et `ConditionalSelector` (`entities/selectors/geometry.py`),
`TileBehindTargetFromSourceDirection` (`entities/selectors/tiles.py`), trigger `CanMove`
(`entities/triggers.py`), primitives `direction_to` et
`get_tile_behind_target_from_source_direction` (`engine/battle_query.py`), accesseur vectoriel
`ability_var_array` (`entities/effects/magnitude.py` — la cellule de niveau de `dmg` est une chaine
CSV `"164,128,91"`, que `ability_var` ne sait pas lire).

## Residus

- **`#502-r1` — `StartAttack` / `FinishAttack` ne sont pas portes.** Le natif encadre chaque maillon
  par ces deux behaviours, dont le seul effet observable est de **FUSIONNER en UNE attaque** les
  tuiles consecutives occupees par la MEME unite (une grande unite couchee sur deux rangs de la
  ligne). Le port n'a pas de substrat DSL pour la pile de contexte d'attaque (`MatchState+0x60`) et
  emet une attaque PAR TUILE : **total de degats identique**, nombre d'attaques encadrantes
  different — donc rang des triggers on-attack different. NON mesure : il faut une unite multi-hex
  alignee sur la vague. Aucun test ne l'asserte (un test qui figerait la divergence figerait le
  residu).
- ~~**`1091 SlashingDive` reste non portee.**~~ **LEVE (#507, 2026-08-07)** — `case-507-slashing-dive.md`.
  Le partage de la base a ete PROUVE (slot de methode runtime : `.ctor` a la MEME adresse d'entree
  que celui de 1064, aucune surcharge a depth=0), la config relue par ability, et tout ce qui
  precede l'a effectivement portee. Le residu `-r1` de #507 nomme le seul axe que le porteur ne
  permet pas d'exercer (`attackRangeType` : le Screamer n'a qu'une arme).
- **`DSLTriggers$$CanMove` est porte a un etage pres.** Le natif est
  `!HasTrait(0x418 = Stationary) && MovementComponent.IsAllowedToMove()` ; le port tient le trait et
  NOMME le second etage comme non publie — meme constat que `CasterCanMove`
  (`services/ability_caster_gates.py`) et `selectors/tiles.py`. Degradation **permissive et bornee**
  au seul etage manquant.
- **`Units(..., unique = 0)`** — le call-site est en regime `SelectAllUnits` (sans dedoublonnage) la
  ou le port dedoublonne toujours (residu herite `#433-r3-r1a-r1`). **INERTE ici** : `AtIndex` rend
  UNE tuile, donc au plus un occupant.
