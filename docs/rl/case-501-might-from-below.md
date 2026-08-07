# #501 — `1165 MightFromBelow` : trois `Execute`, et l'ORDRE est la mécanique

**Porteur** : `genesPatriarch` « The Patermine » (HERO Genestealer Cults, **dans le pool** rank 17).
Trois autres porteurs, tous npc (`genesBossPatriarch`, `genesBossPatriarchLHE`, `genesNpcPatriarch`).
**Avant** : absente d'`ABILITY_CLASSES` → le cast était choisi par la décision et **ignoré à
l'exécution** (0 dégât, 0 summon, aucune erreur). **Après** : portée, séquence coup par coup
bit-exacte, chaînage kill → decoy → summon confronté live.

## 1. L'artefact natif

`IdunBattleLogic.Entities.Abilities.Active.Loki.MightFromBelowAbility$$ExecuteBehaviour`
n'appelle **pas** `ExecuteAtomic` : il appelle `AActiveAbility$$Execute` **TROIS FOIS**.

```
dmg     = AActiveAbility$$MinMaxDamage(this, abilityState, isPrediction: 0)
          = DSLFormulas$$RandomAmount(GetVariableForLevel(0xc minDmg),
                                      GetVariableForLevel(0xd maxDmg))
profile = AActiveAbility$$GetDamageProfile(this)          # constants.damageProfile = Psychic
hits    = AActiveAbility$$GetHits(this)                   # GetNumberConstant(0x2f nrOfHits) = 5

attack  = DSLBehaviors$$AttackWithAbilityDamage(caster = <DSLSelectors+0x48>,
                                                target = <DSLSelectors+0x60>,
                                                amount = dmg, damageProfile = Nullable(profile),
                                                hits = hits,                 # INT, pas un noeud
                                                abilityOrEffect = AbilityOrEffect(this),
                                                selectionType = 2)
tiles   = DSLSelectors$$Tiles(
              DSLSelectors$$UnitsWithTrait(
                  DSLSelectors$$AdjacentFriends(unit = <+0x48>, unitTile = <+0x50>, unique = 1),
                  0x41d = UnitTrait.Decoy, 3))
opts    = SpawnUnitOptions$$WithStatsFromConfig(config@+0x60, abilityState, 0, 0)
opts.<+0x18> = DSLBehaviors$$PerformAIAttackFromCurrentPosition(<DSLSelectors+0x68 ActiveTarget>)
spawn   = DSLBehaviors$$Spawn(<+0x48>, tiles, GetStringConstant(config, 0 = unitId), opts)

[1] Execute( Group(attack, <+0x48>, 0x20 = GroupType.Ability_Attack) )
[2] Execute( KillDeadUnits(<+0x48>, UnitsDamagedThisPhase(<+0x48>)) )
[3] Execute( IfAlive(<+0x48>, Group(spawn, <+0x48>, 0x22 = GroupType.Ability_Summon), null) )
```

`MightFromBelowAbility$$GetPossibleSpawnTiles` reconstruit **exactement** le même `tiles` (mêmes
trois appels, mêmes arguments) → un seul artefact, un seul foyer porté
(`might_from_below_spawn_tiles()`).

## 2. Ce qui tranche, et comment

**La surcharge de la feuille, par ses XREFS ENTRANTES.** `DSLBehaviors$$AttackWithAbilityDamage` a
quatre surcharges homonymes. `list_xrefs` place l'appel de 1165 sur
`(caster, target, amount, damageProfile, hits:System.Int32, abilityOrEffect, selectionType)` — celle
qui enveloppe le profil et les coups dans des `Direct(...)` avant de déléguer au **cœur**
`(caster, target, amount, abilityOrEffect, options, selectionType)`. Le nombre de coups est donc un
**scalaire** ici — contraste exact avec `1027 PsychicMaelstrom` (#490), dont la même famille reçoit
un `IAmountFormula`. Recopier la surcharge voisine aurait donné un `hits` dynamique là où le natif
lit `nrOfHits`.

**Le masque, relu preset par preset.** `MightFromBelowAbility$$.ctor` n'appelle **aucun**
`TargetingOptions$$.ctor` : forme STATIC-COPY, il recopie les 0x40 octets de
`<TargetingOptions statics>+0x40` et les passe à `AActiveAbility$$.ctor(this, &opts, 0)`. Valeurs
**lues dans `IdunBattle.Core.Services.TargetingOptions$$.cctor`** à ce preset :

| champ | offset | valeur |
|---|---|---|
| `isSelfCasting`    | `+0x40` | `0` |
| `range`            | `+0x48` | recopie de `<TargetingRange statics>+0x30` = `RANGE_ADJACENT` |
| `forceMeleeTarget` | `+0x60` | `1` = `RangedBool.False` |
| `rules`            | `+0x68` | **`0x4000` = `TargetIsEnemy`, et rien d'autre** |

Le preset **voisin** `+0x180` porte `0x4002` **et** `RANGE_FROM_CONFIG` : recopier une voisine aurait
changé à la fois le masque et le régime de portée.

**`ABILITY_ATTACK_TYPE` = `0` = `DirectTargetAttack`** — le 3ᵉ argument d'`AActiveAbility$$.ctor`
(écrit en `this+0x68`), transcrit tel quel. Il vaut `0` **même si l'arbre summone** :
`1 = SummonAndAttackTarget` est ce que porte `IncursionAbility`, pas celle-ci.

## 3. LE CŒUR DU CAS — les tuiles sont évaluées APRÈS l'attaque

Le sous-arbre `tiles` est **construit** avant le premier `Execute`, mais un arbre DSL est **LAZY** :
il n'est **évalué** qu'au troisième. Entre les deux, l'attaque a pu **tuer** la cible, et le passif
`CosmicHorror` du même porteur pose alors un `genesSmnDecoy` sur la tuile du mort
(`CosmicHorror_OnKillAbility$$CreateBehaviour` : le `Spawn` y est **inconditionnel**, hors du
`Maybe(chance)`). Comme le masque impose une cible **adjacente**, ce decoy neuf est adjacent au
Patermine : `AdjacentFriends & Decoy` le ramasse, et le Genestealer apparaît dessus.

**MESURE (2026-08-07, `MC1_67` seed 50102, `--hp-target 4000`)** — l'ordre brut des steps du cast :

```
group Ability_Attack (0x20) @3   entity 81   source MightFromBelow
  ... 5 coups sur la cible ...
step 27 Clear_Unit_Tiles + step 11 Unit_IsDying=1   entity 79   <- la cible MEURT
group 21 @26   entity 81   source CosmicHorror
step 9 AddUnit @28   entity 105  parent 81  tile 73             <- le DECOY
group Ability_Summon (0x22) @42  entity 81
step 9 AddUnit @48   entity 108  parent 81  tile 73             <- le GENESTEALER, MEME tuile
group 12/21 @66      entity 108  source Loki_NormalAttack       <- son attaque IA immediate
```

Figer les tuiles avant l'attaque rendrait **0 summon SANS ERREUR** — le no-op silencieux que cette
tranche ferme. Côté port, l'`AbilityEntities` natif porte une **ref d'état** là où
`entities_from_state` **fige** sa liste `units` : les trois phases sont donc jouées chacune sur un
`AbilityEntities` **reconstruit**, et c'est ce qui rend le decoy visible au troisième arbre.

## 4. Deux pièges de MESURE, tous deux payés

**(a) Une vue filtrée `alive` a fait conclure « le natif ne summone pas ».** Le Genestealer posé
attaque immédiatement, la riposte adverse le tue **dans la même cascade**, et il disparaît d'un
`decisionView` filtré. Le premier verdict a été `live=[] offline=[(6,7)]` — c'est-à-dire **le port
accusé d'un summon fantôme alors qu'il avait raison**. Ce sont les `step 9 AddUnit` des events qui
tranchent, pas l'état final : un summon se mesure à sa **création**, jamais à sa survie.

**(b) Un accord `0 == 0` sur l'attaque du summon.** `--hp-target` force **une** valeur sur tout le
camp adverse : la cible du summon mourait elle aussi, son `FuelledByFury_CanRevive` la ramenait à
plein PV, et le delta HP retombait à `0` **des deux côtés**. Accord en régime dégénéré, zéro preuve.
Le montage descend donc les PV **PER-UNIT** (`--unit-stat necroWarden:Health=4000,RemainingHealth=4000`)
et laisse le camp à 400 000 → témoin non nul (`8778` des deux côtés).

## 5. Une réparation de FOYER, mesurée : le crush au spawn

Écart restant après le port : `decoys live=[(6,7) MORT] offline=[(6,7) VIVANT]`.
`IdunBattle.Operations.AddUnitOperation$$Execute` appelle
`$$KillSteppableUnits(killer, steppableUnits)` (**xref unique**) : poser une unité sur la tuile d'un
`Steppable` le **détruit**. Le port n'avait ce crush que sur le **move**
(`movement.py::_kill_steppable_units`, mirror complet de `KillUnitOperation$$Execute`) ; le foyer du
spawn ne l'appelait pas. Il l'appelle désormais — **une** implémentation, deux appelants natifs.

- **`killer` = l'unité QUI VIENT D'ÊTRE POSÉE**, pas le summoner. Discriminant **mesuré** : le
  Patermine porte `CosmicHorror_OnMoveAbility` (« se soigne dès qu'il est le **tueur** d'un decoy
  ami ») et son delta HP live sur ce cast vaut **0** → `OwnerIsActor` échoue → ce n'est pas lui.
- **Rayon de souffle, mesuré** : le crush ne mord que si la tuile de spawn porte un `Steppable`
  vivant. Tous les call-sites qui choisissent leurs tuiles par `CanAddUnit` en sont exclus **par
  construction** (`TileExtensions$$IsFreeTile` à `allowSteppable = 0` exige `content.IsEmpty()`).
  Le seul call-site porté qui pose **sur** un occupant est 1165, dont le sélecteur est
  `Tiles(<decoys adjacents>)` sans aucun `CanAddUnit`.
- Sans lui, le port laissait un decoy **fantôme** qui resservirait de tuile de summon au cast
  suivant.

## 6. Validation

`probe_501_might_from_below.py` — trois volets, tous **VERTS**, re-joués **après rebase** sur
`origin/master` (`b77feac6`).

| volet | ce qu'il mesure | résultat |
|---|---|---|
| **A** SÉQUENCE | replay-diff bit-exact, **coup par coup** (events `Amount` @`Active_Ability_Type=1165` vs `attack["per_hit"]`), 3 casts | `[1014,1166,1030,1154,1024]`, `[1008,1014,1078,1113,1156]`, `[1104,1149,1139,1134,1156]` — **3/3 identiques**, longueur `5` = `nrOfHits` |
| **B** CHAÎNAGE | kill → decoy → summon + attaque IA du summon | séquence `[1046,1079,1072,803,0]` ; mort `True/True` ; decoy `(6,7) mort` des deux côtés ; summon `(6,7) vivant` des deux côtés ; **deltas HP de TOUTES les unités identiques** `{77: 8778, 79: mort, 81: 0, 83: 0}` ; coups du summon live `[2368,2032,2333,2045]` somme **8778** = total offline |
| **C** GATE DE CIBLE | cibles légales port vs `abilityTargets` natif | `{79}` = `{79}` — l'allié (`83`) et l'ennemi non adjacent (`77`) sont refusés des deux côtés |

**Généralisation** — volet B rejoué sur un **autre couple (board, seed)** : `C1_74` / `60100` →
séquence `[1068,1163,1090,679,0]`, decoy et summon en `(3,6)` (tuile `45`), coups du summon
`[2166,1704,1719,2067]` somme **7656** = total offline. Bit-exact.

**Test committé** : `tests/engine/runner/test_501_might_from_below_offline.py` (12 tests) — contrat
de disjonction, ordinaux figés (`0x4000`, `0x41d`, `0x20`, `0x22`, `AbilityAttackType 0`), structure
des trois arbres feuille par feuille, cadence des trois `AbilityEntities`, et présence du crush au
spawn.

## 7. Ce qui n'est PAS couvert

- **`N` decoys → `N` summons, en LIVE.** Le natif n'a **ni `PickRandomly` ni `First`** dans son
  sélecteur (lu), et le port passe `pick_n=None` (gardé par le test offline) — mais le montage live
  n'a pas tenu : `CultDemagogue` sème ses decoys sur des tuiles **libres tirées au hasard** dans un
  rayon 2 de **sa** cible, et sur les trois couples (board, seed) essayés aucun n'est tombé adjacent
  au Patermine tout en le laissant au contact d'un ennemi. **NON CONFRONTÉ** — pas « non
  pertinent ». Le montage qui le fermerait : faire poser les decoys par une source dont on choisit
  la géométrie, ou piloter une unité adverse pour amener une cible au contact du Patermine une fois
  celui-ci placé sur les decoys.
- **La cascade AVAL du summon** — riposte adverse, mort du Genestealer, decoy laissé par son trait
  `Ambush` — est **observée** dans les steps mais appartient à d'autres mécaniques ; le volet B
  n'assertionne que ce que la 3ᵉ phase pose.
- Les deux gates par-cible d'`AbilityDamageBehaviour$$Execute`
  (`MatchesUnitSelectionType(unit, 2)`, `HasTrait(unit, 0x40e Invincible)`) : inertes en mono-cible
  sur une cible vivante déjà validée par le masque.
- `UnitExtensions$$IsAttackMaxOutDamage(caster)` : régime commun à toute la famille, sans porteur
  dans un roster de duel.
