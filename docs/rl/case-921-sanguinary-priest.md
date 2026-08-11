# #921 — `SanguinaryPriest` : le premier `RandomAmount` du port qui frappe PLUSIEURS cibles

Passif de kit de `bloodSanguinary` « Nicodemus » (HERO Blood Angels, **au pool** rank 17).
`TriggeredAbilityType.SanguinaryPriest` = 0x510 = 1296. Build `rnca9r7q6c`.

## 1. État réel du port AVANT la tranche — mesuré, pas supposé

`SanguinaryPriest` n'existait que comme **membre d'enum** (`entities/triggered_ability_type.py`,
`enum_maps.py`, `frida/hooks/data/triggered-ability-names.ts`). Aucune des trois voies de câblage
d'un passif ne le portait :

| voie | présence |
|---|---|
| `triggers.dispatch.ABILITY_TRIGGERS` | **absente** |
| `effects.factory.ABILITY_INIT_OWNER_EFFECTS` | absente |
| classe d'effet | absente |
| `playbook` (face DÉCISION) | **absente** |

Les deux faces étaient donc ouvertes. `docs/rl/case-576-blood-chalice.md` §4 l'avait déjà rencontré
comme **étage voisin non porté** : le live y rendait `floor(hp_max × 50 %) + 2049`, et le `2049`
venait de ce passif, pas de `BloodChalice`.

## 2. Les trois artefacts natifs

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SanguinaryPriestAbility$$CreateTrigger` :

```
On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive = 1)
  op_BitwiseAnd  <DSLTriggers+0x28>          # = IsTurnOf(Owner)
  op_BitwiseAnd  get_OwnerIsActor
```

⚠ **TROIS termes** là où son voisin de forme `SpiritualLeaderAbility$$CreateTrigger` n'en a que
**deux** (`On(0x1c) & get_OwnerIsActor`). Le terme supplémentaire est écrit par
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` (`ctor(<DSLSelectors+0x30> = Owner,
<dsl+0x10> = state)`) et vaut `IsTurnOf(Owner)` (identification : `case-366-r1` §2, partagée par
huit call-sites déjà portés). Recopier la forme du voisin aurait perdu ce gate.

`...$$GetTargets` :

```
adj  = DSLSelectors.AdjacentFriends(Owner@DSLSelectors+0x30, unique = 1, selectionType = 3)
mech = DSLSelectors.MechanicalUnits(adj, 3)
return adj op_Subtraction mech
```

`...$$CreateBehaviour` :

```
lo      = GetVariableForLevel(cfg, 0x20 = hpToHeal,    abilityState)
hi      = GetVariableForLevel(cfg, 0x47 = maxHpToHeal, abilityState)
targets = <le MÊME sous-arbre que GetTargets, reconstruit inline>
amount  = DSLFormulas.RandomAmount(lo, hi)
options = HealBehaviourOptions.ForRegenerate(AbilityOrEffect(this.Id))
return DSLBehaviors.Heal(healer = Owner@+0x30, selector = targets, amount, options)
```

**Ce que le passif n'a PAS et que son plus proche voisin a** :
`IdunBattleLogic.Entities.Abilities.Active.BloodChaliceAbility$$GetTargets` — l'ACTIF du **même
porteur** — ajoute `UnitsWithoutTrait(adj − mech, 0x19 = UnitTrait.Immune, 3)`. Le passif s'arrête à
la soustraction : **aucun filtre `Immune`**.

### Surcharges tranchées par les XREFS ENTRANTES

* `RandomAmount` : le build en porte deux (`(Int32, Int32)` et `(IAmountFormula, IAmountFormula)`),
  indiscernables dans le pseudo-C. `list_xrefs` place `SanguinaryPriestAbility$$CreateBehaviour`
  dans les appelants de la **première** — donc deux bornes CONSTANTES, pas des `ConfigVar` paresseux.
* `AdjacentFriends` : deux surcharges d'arité 4 aussi. Les xrefs désignent la **UNIT-ancrée**
  `(unit, unique, selectionType)` — la même que `BloodChaliceAbility$$GetTargets`, **pas** la
  TILE-ancrée qu'appelle `RitesOfRestorationAbility$$GetHealTargets`. Le `3` est donc un
  `UnitSelectionType.OnlyAliveAndTargetable`, jamais un rayon.

## 3. LE FIX DE FOND : `HealBehaviour$$Execute` évalue le montant **PAR CIBLE**

`IdunBattle.Entities.Behaviours.HealBehaviour$$Execute` appelle `<+0x60>.Calculate(entities)`
**DANS** la boucle d'énumération des cibles — entre le `get_Current` de l'énumérateur et l'appel
`processor.<slot 0x57>(healer, target, amount, scope, removeEffects, source)`. Même structure que
`RepairBehaviour$$Execute`, que `operations/repair.py` cite verbatim depuis #299 et que
`operations/heal.py` **écrivait déjà dans sa docstring** — mais la feuille
`abilities/behaviours/stats.py::Heal`, elle, hissait l'évaluation **avant** la boucle.

Sur un `Direct(...)` la différence ne s'observe pas. Sur un `RandomAmount` **si**, et
`SanguinaryPriest` est le premier call-site porté à réunir les deux conditions (formule aléatoire ×
sélecteur multi-cibles). Deux corollaires, tous deux mesurés :

1. deux alliés adjacents reçoivent **deux tirages indépendants** ;
2. quand le sélecteur ne rend **aucune** cible, le natif n'entre jamais dans la boucle donc
   n'appelle **jamais** `Calculate` — le port consommait un **tirage fantôme** qui décalait le PRNG.

Corrigé dans le même commit ; le montant par cible est désormais dans chaque entrée de `heals`, et
la clé `amount` de l'émission `Heal` porte le dernier montant évalué (identique à l'unique quand la
formule est déterministe — le cas de tous les call-sites portés avant cette tranche).

## 4. Validation live — `probe_921_sanguinary_priest.py`

Montage : `bloodSanguinary` + DEUX alliés non mécaniques blessés (`astraBullgryn`,
`bloodDeathCompany`) + UN allié **mécanique** blessé (`admecMarshall`, traits `{Hero, Mechanical}`)
vs `blackTerminator`, `worldJakhal`. `--unit-stat <vis>:RemainingHealth=1` blesse au maximum sans
toucher la santé MAX. Les trois alliés sont **amenés** autour d'une tuile de rendez-vous par des
`applyAction move` vérifiés — le premier montage, qui laissait la géométrie de spawn décider, ne
rendait qu'**une** cible adjacente et ne discriminait donc pas le tirage par cible.

| étage | mesure |
|---|---|
| E1 CONFIG | passif L50, multiplier 180 % → plage `[1496, 2194]` |
| E2 SÉLECTEUR | `AdjacentFriends` = `[83, 87, 85]` · `MechanicalUnits` = `[87]` · différence = `[83, 85]` |
| E3 MOVE SEUL (MC1_67 / 777) | natif **+2179 / +1912**, port **+2179 / +1912** — écart 0 |
| E3 GÉNÉRALISATION (MC1_63 / 38704) | natif **+1535 / +1863**, port idem |
| E3b tirage par cible | montants natifs **DISTINCTS** sur les deux boards |
| E4 CONTRÔLE | 2e move dans le même tour : 0 des deux côtés |
| E5 `OwnerIsActor` | les moves des alliés eux-mêmes ne soignent personne (0/0/0) |
| E6 mécanique | `admecMarshall` intact des deux côtés |

L'accord est **bit-exact** parce que le PRNG est calé sur l'état MT live (`dumpRng`) : le port
consomme `NextInternal(lo, hi + 1)` au même point et autant de fois que le natif.

## 5. Les mutants

| mutant | verdict | ce qu'il dit |
|---|---|---|
| `tirage-hisse` | **TUÉ** | `port 2179 / 2179` contre `natif 2179 / 1912` — la régression d'origine |
| `sans-mecanique` | **TUÉ** | `port 2179 / 2087` — voir ci-dessous |
| `borne-exclusive` | **TUÉ** | `port 2139 / 2139` — le `+ 1` de `NextInternal(min, max + 1)` |
| `sans-scope-groupe` | **SURVIVANT** | témoin aveugle, cause mesurée ci-dessous |

⚠ **`sans-mecanique` est tué par le PRNG, pas par le soin.** Retirer le filtre
`op_Subtraction MechanicalUnits(.)` ne fait PAS soigner le mécanique — le gate
`AttackQuery$$EntityCanBeHealed` de `HealUnitOperation` le refuse en aval. Mais son tirage, lui, est
déjà consommé, et il **décale** le montant de la cible suivante (l'ordre du sélecteur est
`[83, 87, 85]`). L'observabilité du filtre passe donc entièrement par le décalage PRNG — conséquence
directe du tirage par cible, et raison pour laquelle ce mutant n'aurait rien dit avant le fix §3.

⚠ **`sans-scope-groupe` survit, et c'est structurel.**
`HealBehaviourOptions$$ForRegenerate` = `(scope 1, removeEffects 0)`, `scope = 1` armant le cap
`GetGroupUnitHealLimit` de `DamagePrediction$$PredictHeal`. Or ce cap rend `int.MaxValue` dès que
`nrOfMembers < 2`, et **aucune unité du pool rank 17 n'est multi-membres** (mesuré : le pool est
fait de héros). Le `scope = 1` est donc établi par les **xrefs `ForRegenerate` du décompilé**, pas
par un régime confrontable — exactement le statut que `operations/triggers/loki/time_flux.py`
documente déjà pour le sien.

## 6. Face DÉCISION — RE complète, port NON FAIT (résidu #921-r1)

`IdunBattle.AI.Playbook.SanguinaryPriestPlaybook` a un **corps propre** (il n'hérite PAS du corps
commun `AdjacentUnitPreferenceTriggeredAbilityPlaybook`) :

```
IdunBattle.AI.Playbook.SanguinaryPriestPlaybook$$.ctor            -> base(0x510 = 1296, ...)
...<CalculateAttackUtilityInStepsInternal>d__4$$MoveNext          -> yield Fix64(0)   # AUCUNE utilité d'attaque
...<CalculateMovementUtilityInStepsInternal>d__3$$MoveNext :
    util = Fix64(0)
    units = query.<slot 0x7a>(case.MovementTile, case.Unit, null, false)
    foreach u in units :
        if (UnitExtensions.IsAffectedByHealType(u, 0)) {
            util += getUtilityVal("SanguinaryPriest_AdjacentNonMechanicalFriend")
            if (UnitExtensions.IsDamagedUnit(u))
                util += getUtilityVal("SanguinaryPriest_AdjacentDamagedNonMechanicalFriend")
        }
    yield util
```

* **slot `0x7a` = 122** = `IdunBattle.Core.Services.BattleQuery$$GetAdjacentUnits(from: IEntity,
  friendsOf: IEntity, enemiesOf: IEntity, ignoreSteppables: Boolean)` — lu dans
  `data/symbols/<build>/metadata/interface_slots.tsv` puis apparié à la signature de
  `frida/methods.tsv`. Les arguments sont `(MovementTile, case.Unit, null, false)` : `enemiesOf`
  nul désactive le volet ennemis.
* **les deux clés sont des littéraux CONFIRMÉS**, pas déduits :
  `metadata/string_literals.tsv` donne `0x33f6418 = "SanguinaryPriest_AdjacentNonMechanicalFriend"`
  et `0x33f62d8 = "SanguinaryPriest_AdjacentDamagedNonMechanicalFriend"` ; le seed BC les porte à
  **5** et **6** dans `Utilities.Default.TriggeredAbilities`.
* **AUCUN `RemoveAll(u.Id == case.Unit.Id)`** — contrairement à `SereneUnifierPlaybook` (#456-r1) et
  au corps commun. Le mover se compte donc lui-même dès que son origine tombe en ring-1 de la tuile
  candidate. C'est LU, et c'est le genre de détail qu'une recopie du voisin aurait inversé.
* Ni cap, ni `FilterAdjacent*`.

**Le bloqueur est un SUBSTRAT, et il est mesuré** : le prédicat `IsDamagedUnit(u)` (hp < hp_max)
n'est dérivable d'AUCUN des deux producteurs de contexte des feuilles `Tile(7)` —
`utilities/tile.py::_unit_record` (régime runner) rend `{pos, vis, id, triggered, active, traits,
effects}` et `utilities/tile.py::_adjacent_units` (régime décision) rend `{pos, traits, effects, id,
triggered}`. **Ni l'un ni l'autre ne porte `hp`/`hp_max`.** Ajouter la clé touche un foyer partagé
par les 27 feuilles portées de `Tile(7)` : c'est une tranche, pas un ajout de ligne. `#921-r1`.

## 7. Ce qui n'est PAS couvert

* le **cap de groupe** (`scope = 1`) — non confrontable, cf. §5 ;
* la face **DÉCISION** — cf. §6 ;
* le régime « le prêtre ne bouge PAS et clôt son tour » : le port passe par le **même** vecteur
  `arrived_at_final_tile_triggers`, dont les deux émetteurs sont déjà validés par `SpiritualLeader`
  et `ChampionOfTheFeast` — mais il n'est pas exercé par ce probe (qui mesure le MOVE) ;
* le gate `IsTurnOf(Owner)`, porté parce que le natif l'ÉCRIT : sur les deux émetteurs de `On(0x1c)`
  il est impliqué par `OwnerIsActor`, donc aucun régime porté ne le distingue.
