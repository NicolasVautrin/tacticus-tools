# #419-r6-r2 — `ChampionOfTheFeast` (1086) : le passif qui n'était dans AUCUN registre

**PORTÉ + CONFRONTÉ LIVE (2026-08-06).** Porteur : `templSwordBrother` « Sword Brother Godswyl »
(lineup, **dans le pool**, `passiveAbilities = ['ChampionOfTheFeast']`, seed BC
`PassiveAbilities = [1086]`) + 3 npc.

## Le gap

`TriggeredAbilityType.ChampionOfTheFeast = 1086` n'était dans aucun des quatre registres
(`TRAIT_TRIGGERS`, `ABILITY_TRIGGERS`, `ACTIVE_ABILITY_TRIGGERS`, `EFFECT_TRIGGERS`). Offline,
Godswyl terminait son activation **sans frapper** et **sans poser son malus d'armure** — ni erreur,
ni crash. Mesure live : **1408 PV** et **−997 d'armure** que le port ne produisait pas.

⚠ **`docs/rl/combat-ability-coverage.md` ne pouvait pas le voir : cet audit n'énumère que les
`activeAbilities`.** Re-mesuré ici — après le port, `combat-ability-coverage.md` est **inchangé**
au bit près, alors que `kit-coverage.md` fait bien sortir `templSwordBrother` des kits à
travailler. Un passif triggered manquant est donc invisible du premier et visible du second : ne
jamais conclure « couvert » d'un audit qui n'a pas l'ability dans son périmètre.

## RE (build `rnca9r7q6c`, décompilé = vérité)

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ChampionOfTheFeastAbility$$CreateTrigger` =

    On(0x1c = ArrivedAtFinalTile, ownerNeedsToBeAlive = <DSLTriggers+0x20>)
      & get_OwnerIsActor
      & op_LogicalNot(AmountIsZero(Damageable(AdjacentEnemies(Caster@DSLSelectors+0x48,
                                              unique, OnlyAliveAndTargetable))))

`...$$CreateBehaviour` =

    AttackWithAttackDamage(Owner@DSLSelectors+0x30, <cible>, MinMaxDamage(abilityState),
                           GetDamageProfileOrDefault(DamageProfileType.Power = 0xe), GetHits(),
                           AbilityOrEffect(this), <default>, UnitSelectionType.OnlyTargetable = 2)
    op_Addition
    IfAlive(<cible>, AddStaticStatModifierEffect(<cible>, 0x43b, StatType.FixedArmor = 0x10,
                                                 Direct(-armorReduction), turns = NULL, false))

`<cible>` = `Cache(Otherwise(PickRandomly(UnitsWithoutTrait(pool, UnitTrait.Immune = 0x19), 1),
PickRandomly(pool, 1)), matchAbilityEntities: true)` — `...$$GetTarget` / `...$$GetPossibleTargets`.

### Quatre points tranchés au décompilé, pas au tooltip

1. **`UnitsWithoutTrait(Immune)` est une PRÉFÉRENCE, pas un filtre** — c'est un `Otherwise`. Un
   filtre sec priverait Godswyl de sa frappe face à un mur d'unités `Immune`.
2. **Le `Cache` est fonctionnel.** Sans lui l'arbre est évalué deux fois : **2 tirages** au lieu
   d'un, et potentiellement **2 cibles différentes** dès que le pool dépasse 1.
3. **`IfAlive` est après l'attaque** : une cible que la frappe tue ne reçoit pas le malus.
4. **`turns = NULL`** et `0x43b` absent du switch
   `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds`
   ⇒ **PERMANENT** (« for the rest of the battle » de l'i2).

`On(0x1c)` porte **à lui seul** les deux branches de l'i2 (« After moving » / « if he does not
move, at the end of his turn ») : ce sont les deux émetteurs du même flag
(`MoveUnitOperation$$Execute` et `FinishUnitTurnOperation$$Execute`).

## Forme du port

Arbre DSL 1:1 (doctrine #149) — **tout le vocabulaire existait**, le module ne fait que le câbler.
`engine/runner/operations/triggers/loki/champion_of_the_feast.py` +
`engine/entities/effects/loki/champion_of_the_feast.py`.

⚠ **L'effet 1083 expose le canal LECTURE (`get_stat_modification_*`), PAS `applied_stat_mods`.**
La feuille `AddStaticStatModifierEffect` appelle **déjà** `apply_change_stat` après
`AddEffectOperation` — et `AddEffectOperation` exécute `_apply_stat_mods`, qui lit
`applied_stat_mods`. Implémenter les deux compterait le malus **deux fois**, silencieusement. Même
forme que `ShockAssaultBuffEffect` et `SereneUnifierStormOfFireEffect`, les deux autres classes
dédiées posées par cette feuille. La classe reste nécessaire : une instance **captée au seed**
arriverait sinon en `BaseEffect` nu, contribution non retirable dans le résidu opaque (#118).

⚠ **Le slot de niveau est PASSIF.** `votann._source_level_mult` lit `active_ability_level` en
premier — correct pour `AugmentedAssault` (une ACTIVE), **faux ici**. Les deux coïncident dans un
runner rank-based, d'où l'intérêt de lire la bonne source avant de dépendre de la coïncidence.

## Mesure (probe `probe_419r6r2_champion_of_the_feast.py`, test `test_champion_of_the_feast_live.py`)

| montage | pool adjacent | natif | port |
|---|---:|---|---|
| MC1_67 / 777 | **2** | −1408 PV, −997 armure | −1408, −997 |
| MC1_63 / 38704 | 1 | −1330 PV, −997 armure | −1330, −997 |

Dans les deux cas la **cible frappée est la même** et l'autre adjacent reste intact.
`−997 == armorReduction[50] × 180 %`. Avant le port : **−0 / −0** des deux côtés.

⚠ **Le pool à 1 est un régime DÉGÉNÉRÉ** : ni le `PickRandomly` ni l'`Otherwise` ne peuvent y
diverger — n'importe quel port qui frappe « l'ennemi adjacent » passerait.
`test_regime_non_degenere` exige donc qu'**au moins une** mesure ait ≥ 2 candidats, pour que la
dégradation du montage se voie au lieu d'affaiblir les autres bras en silence.

## Deux pièges de HARNAIS, tous deux mesurés

- **`Runner.apply(MoveUnitMessage(...))` ne route pas le move** hors boucle de tour : la position
  reste inchangée et le probe conclut « port inerte » pour une raison de harnais. La voie est
  `MovementHandler.visit_MoveUnitMessage`.
- **`AttackDamageOperation.execute_ability_attack` SKIP le dégât (`return None`) quand `state.rng`
  n'est pas calé.** D'où le `dumpRng` — qui sert de toute façon au `PickRandomly`.

## Et un piège de MONTAGE, trouvé en écartant le 2ᵉ plateau

`walkable` + adjacence **ne garantissent pas** que le natif accepte le move. Sur `MC1_63` la
meilleure tuile était libre et adjacente à deux ennemis, et le natif a laissé Godswyl sur son
spawn : le probe rendait « témoin natif nul », ce qui **accuse le port** pour une panne de
géométrie. Le probe essaie désormais les candidates dans l'ordre, **relit la position atteinte**,
rejoue le port vers *cette* position, et nomme l'échec de géométrie s'il ne bouge pas.

## Résidus nommés

- `selectionType` (`OnlyTargetable` = 2 sur l'attaque, `OnlyAliveAndTargetable` = 3 sur les
  sélecteurs sources) : le port n'a pas ce paramètre côté sélecteurs — résidu **déjà partagé par
  tous** les call-sites d'`AdjacentEnemies`/`AdjacentFriends`, pas propre à ce port.
- `matchAbilityEntities = true` du `Cache` : mémoïsation par instance de nœud (slot unique), la
  variante dict-keyée par contexte n'est pas portée. Inerte ici — l'arbre est rebâti à chaque fire
  et n'est évalué que sous un contexte top-level.
- La branche **« ne bouge pas » (`FinishUnitTurnOperation`)** du même `On(0x1c)` n'a pas de bras de
  test dédié : elle est portée par le vecteur partagé (déjà couvert par `ArcaneShield` et
  `FabricatorClawArray`), mais non re-confrontée ici pour ce passif.
- Le gate `UnitTrait.Immune` n'a **pas** été confronté live : aucun des adversaires du montage ne
  porte le trait, donc la branche `Otherwise` de repli n'est jamais empruntée.
