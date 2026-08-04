# case-589-r1-r1-r1 — la POSE d'`EmpyricAmbush` (ability **1232**), portée en arbre DSL

`#589-r1-r1-r1`. `case-589-r1-r1` avait porté l'EFFET 1578 et son gate, et l'avait confronté
jusqu'au seuil `movement = 4`. Mais `IdunBattleLogic.Entities.Abilities.Active.Loki.EmpyricAmbushAbility$$ExecuteBehaviour`
restait un **no-op combat** : l'effet n'entrait dans l'état du port que par la **capture live**, donc
un replay-diff qui aurait fait caster Lhykhis **par le port** divergeait. C'est fermé.

## 1. La question binaire, et sa réponse mesurée

> « Quand `eldarLhykhis` caste 1232, le port reproduit-il les TROIS observables du natif — la TUILE
> d'atterrissage, la salve par coup, et la marque 1578 sur la cible — à partir du même état et du
> même flux PRNG ? »

**Oui, sur les trois, sur 3 boards.** `--crit 0,0` (salve nue, aucun canal crit) :

| board / seed | landing natif == port | salve natif == port | marque 1578 | `NOPORT` mord |
|---|---|---|---|---|
| `MC1_67` / 777 | `(0,1)` | `[861, 889, 793, 949, 766, 979, 773, 947]` | oui | oui (3/3) |
| `C1_74` / 31337 | `(1,2)` | `[1196, 1100, 1370, 1254, 1440, 1272, 1095, 1238]` | oui | oui (3/3) |
| `C3_14` / 777 | `(6,3)` | `[886, 776, 700, 866, 743, 849, 804, 798]` | oui | oui (3/3) |

`NOPORT` = 1232 retirée d'`ABILITY_CLASSES` (la vue d'AVANT ce port) : ni vol, ni dégât, ni marque.
Sans ce témoin, « ça concorde » ne vaudrait rien.

**La DURÉE est un quatrième observable, et elle a failli passer.** Le natif pose
`turns = <DSLFormulas+0x20> = Direct(1)` — un nombre de TOURS déjà résolu. `Direct(1)` et
`TurnsFromRounds(1)` posent **tous deux** la marque : seule la durée les sépare. Mesuré sur
`EffectComponent.RemainingTurns` (`decisionView`, `frida/hooks/game/effects.ts`) —
natif **1**, port **1**, et le témoin `ROUNDS` (la même pose en `TurnsFromRounds(1)`) rend **2**.
Le cran discrimine donc, et le choix `duration_turns=1` est validé par mesure, pas par lecture seule.

## 2. L'arbre natif — et le `If` ne couvre PAS le vol

    tiles = First( SortTilesByUtility( Randomize( CanAddUnit(AdjacentTiles(Target@+0x60))
                                                  op_Subtraction <DSLSelectors+0x50 = CasterTile> ),
                                       Caster@+0x48, 7 = Tile, 0 ), 1, 0 )
    Execute( FlyUnit(Caster@+0x48, tiles)
           & If( <DSLTriggers+0x20> = OwnerIsAlive,
                   AttackWithAttackDamage(Caster, Target, MinMaxDamage, GetDamageProfile(),
                                          Get(GetHits()), AbilityOrEffect(this+0x10), options VIDE)
                 & AddEffect(0x62a = 1578, AbilityStateReference, source = Owner@+0x30,
                             targets = Target@+0x60, turns = <DSLFormulas+0x20> = Direct(1)) ) )

`<DSLTriggers+0x20>` est le **même slot** que chez `WallOfMirrors` / `RammingSpeed` / `SkyStrike` /
`ExemplarOfTheKauyon` : APRÈS un déplacement, AVANT l'attaque — « le porteur a-t-il survécu au vol ? ».
Le 8ᵉ argument `Nullable<AttackDamageBehaviourOptions>` est passé **VIDE** : ni `alwaysOverkilled`, ni
`alwaysCrit`, ni variance d'arme. Config 1232 relue : `attackRangeType = Melee`,
`damageProfile = Eviscerate`, `nrOfHits = 8` — le port les **lit**, il ne les code pas en dur.

## 3. `Randomize` — où le natif tire, et la preuve que le port tire au même endroit

`IdunBattleLogic.Entities.DSLSelectors$$Randomize` alloue un `PickRandomAmountSelector` à
`amount = 0x7fffffff`, `allowRepeat = 0`, `maxRepeats = 0x7fffffff` : la boucle native pioche jusqu'à
**épuisement** du pool. C'est une **permutation aléatoire complète**, donc **`len(pool)` tirages**
(bornes décroissantes ; le dernier, `range == 1`, consomme quand même — loi #130/#215).

Il est enveloppé par `SortTilesByUtility`, dont le `Select` finit par un `Enumerable.OrderBy` —
tri **STABLE**. L'aléa ne survit donc que sur les **ex aequo** d'utilité. Le tirage a lieu à
l'exécution de `FlyUnit` (le sélecteur n'est évalué que là), donc **avant** les tirages de dégât.

**Ce n'est pas une lecture, c'est une mesure** — bras `NORANDOM` (le nœud remplacé par l'identité) :

| | landing | salve |
|---|---|---|
| natif == port | `(0,1)` | `[861, 889, 793, 949, 766, 979, 773, 947]` |
| `NORANDOM` | **`(1,0)`** | `[865, 983, 985, 861, 889, 793, 949, 766]` |

La tuile **change**, et la salve du port réapparaît **décalée de 3 tirages** — exactement la taille du
pool consommée par le `Randomize`. Sans ce bras, l'accord sur le landing serait compatible avec un
port qui tire au mauvais moment, ou qui ne tire pas.

## 4. Les deux faces, mesurées SÉPARÉMENT

**DÉCIDER** — oracle `abilityReason` (le masque `TargetingRule` natif par cible), contrat de fidélité
`natif == 0 => port == 0` / `natif != 0 => port == natif ou 0` / jamais un refus pour la mauvaise
raison. Mesuré : 3 cibles, accord exact, dont `0x4000 TargetIsEnemy` sur l'allié.

Le masque est `0x6004020`, forme **FLAGS DIRECTS** (surcharge à 7 paramètres, tranchée par ses xrefs
entrantes — aucun preset, donc aucun `|` à appliquer) ; somme exacte, 0 bit résiduel :
`0x20 TargetHasFreeAdjacentTile` + `0x4000 TargetIsEnemy` + `0x6000000 AllowObscuredTarget`.
`range = TargetingRange statics+0x48 = useWholeBoard`, `forceMeleeTarget = 1 = RangedBool.False`,
puis `AActiveAbility..ctor(this, &opts, 0)` → `AbilityAttackType = 0 = DirectTargetAttack`.

⚠ **Le bit 5 a son propre bras** (`--encercle`) : cible dont tous les voisins marchables sont occupés
→ natif `0x20 TargetHasFreeAdjacentTile`, port `0x20`. C'est le pendant DÉCISION exact du
`CanAddUnit(AdjacentTiles(cible))` du behaviour. Sans lui, le masque n'aurait été validé qu'à
`TargetIsEnemy` près.

**EXÉCUTER** — le cast rejoué offline sur le snapshot pris juste avant, RNG calé sur le même instant.

## 5. Deux nœuds ajoutés, et pourquoi

* `Randomize` (`entities/selectors/geometry.py`) — sous-classe de `PickRandomly` portant les
  littéraux du call-site natif. Le nœud NOMMÉ, pas une paraphrase.
* `CasterTile(as_ids=True)` (`entities/selectors/accessors.py`) — même paramètre, même raison et même
  défaut que `Tiles(units, as_ids=...)` : les deux opérandes d'un `op_Subtraction` doivent vivre dans
  le même domaine, sinon la soustraction compare des positions à des ids et ne retranche **rien,
  silencieusement**. Aucun call-site existant n'est touché (les 18 autres passent `CasterTile()`).

⚠ Le `op_Subtraction <+0x50>` est **redondant en pratique** avec `CanAddUnit` (la tuile du caster est
déjà occupée, `TileExtensions$$CanAddUnit` lit le `TileContentComponent`). Il est mirroré tel quel.

## 6. Reproduction

    python probe_589r1r1r1_empyric_ambush_pose_live.py --verbose
    python probe_589r1r1r1_empyric_ambush_pose_live.py --board C1_74 --seed 31337
    python probe_589r1r1r1_empyric_ambush_pose_live.py --encercle --verbose
    python -m pytest tests/engine/runner/test_589r1r1r1_empyric_ambush_pose_live.py   # 7 passed

## 7. Ce qui n'est PAS couvert

* **`EmpyricAmbush_AnyMove` (1580) et `EmpyricAmbush_Reset` (1555) restent NON PORTÉS** — résidu
  **`#589-r1-r1-r1-r1`**. Lus au décompile, pas portés :
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.EmpyricAmbush_AnyMoveAbility$$CreateTrigger` =
  `On(PreUnitMove) & OwnerIsActor` → `CreateBehaviour` = `AddEffect(1580, targets = Owner, turns = 0)`,
  retiré par `IdunBattle.Entities.Effects.Loki.EmpyricAmbush_AnyMoveEffect$$CreateRemoveEffectTrigger`
  (`On(UnitAfterMove)`) ; `...EmpyricAmbush_ResetAbility$$CreateTrigger` = `On(UnitDefeated) &
  OwnerIsActor & AreEnemies(Owner, Target) & IsNormalAttack & IsMeleeAttack`.
  **Aucun des deux ne lit `TilesMovedThisTurn`** : ce n'est pas une extension du travail sur le
  compteur, c'est un autre mécanisme.
* **Le régime `Walk`** n'est pas joué (mesuré INERTE pour #589) — sans objet ici, la POSE ne lit aucun
  compteur de déplacement.
* **`GetNumHits`** (`IdunBattleLogic.Entities.Abilities.Active.Loki.EmpyricAmbushAbility$$GetNumHits`)
  n'a **pas** de call-site porté : il rend la même valeur que le `hits` du behaviour
  (`Get(GetHits())`), et la face PRÉDICTION de 1232 n'est pas dans ce périmètre.
* **La face DÉCISION du playbook** (`IdunBattle.AI.Playbook.Loki.EmpyricAmbushPlaybook`) n'est pas
  touchée : ce port est la face COMBAT. Ce qui est confronté ici du côté « décider », c'est le **gate
  de ciblage**, pas l'utilité.
* **`AllowObscuredTarget` (0x6000000)** n'a pas de bras dédié : aucun des trois boards joués ne place
  d'obstacle de ligne de vue entre Lhykhis et sa cible. Le bit est **permissif** (il RETIRE une
  contrainte), donc son absence de port se lirait comme un refus supplémentaire — que le contrat de
  fidélité aurait attrapé sur les 3 cibles mesurées. Non exercé pour autant.
