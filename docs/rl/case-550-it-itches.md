# #550 — `1121 ItItches` : la fiche disait SUMMON, le behaviour en fait CINQ

Porteur : `tyranParasite` (Parasite of Mortrex), dans le pool. Artefact natif :
`IdunBattleLogic.Entities.Abilities.Active.Loki.ItItchesAbility$$ExecuteBehaviour`.

L'ability était un **no-op silencieux** : absente d'`ABILITY_CLASSES`, donc ignorée par
`AbilityHandler.visit_ActiveAbilityMessage` — 0 dégât, 0 effet, **aucune erreur** — alors que sa face
DÉCISION (`playbook/noncomparable/it_itches.py`) était déjà portée et pouvait la choisir.

## 1. La catégorie annoncée n'était pas fausse — elle était incomplète, et c'est pire

`docs/rl/combat-ability-coverage.md` classe 1121 en **SUMMON**. C'est exact et ça ne dit qu'un
cinquième de l'ability. La colonne dérive du `damageProfile` de l'arme du porteur, jamais du
behaviour ; pour une ability non portée, l'`ExecuteBehaviour` n'est connu de personne.

Le décompilé est un **composite de cinq mécaniques**, et les cinq propositions du tooltip i2
s'apparient une à une aux nœuds — c'est ce qui a validé la lecture :

| i2 | nœud natif |
|---|---|
| « Suppresses » | `AddEffect(0x429 = Pinned)` |
| « pushes … one hex backwards » | `DisplaceUnitInAdjacentDirection(VectorFromAdjacentTo(CasterTile, Tiles(Target), 1))` |
| « Enemy steppables … are destroyed » | tête d'`IdunBattle.Operations.DisplaceUnitOperation$$Execute` + `Kill(DeadUnits)` |
| « summons a Ripper Swarm in each hex vacated » | `Foreach(CanAddUnit(<tuiles des cibles>), t => Spawn(t))` |
| « may move again » | `ResetMovement(Owner)` |

## 2. La structure, lue

Trois exécutions natives distinctes (le décompilé re-copie les 0x148 octets du contexte avant
chacune) :

```
[1] ExecuteAtomic( ((Pinned & Reserve) & DisplaceUnitInAdjacentDirection) & RemoveReservation,
                   entities, GroupType.Ability_AtomicGroup /* 0x2a */ )
[2] Execute( ResetMovement(Owner@0x30), entities )
[3] Execute( Group( ((Reserve & Kill(Caster, DeadUnits(targetUnits), ForClearDeadUnits))
                     & Foreach(CanAddUnit(targetTiles, Owner, isSteppable), t => Spawn(...)))
                    & RemoveReservation,
                    Owner@0x30, GroupType.Ability_Summon /* 0x22 */ ), entities )
```

Sélecteurs partagés (slots `DSLSelectors` lus dans `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`) :

```
targetUnits = Cache(Enemies(Caster@0x48,
                            Target@0x60 + AdjacentTilesIntersection(CasterTile@0x50, Target@0x60),
                            UnitSelectionType.OnlyAliveAndTargetable), true)
targetTiles = Cache(Tiles(targetUnits), true)
```

## 3. Ce qui aurait pu être porté « plausible mais faux »

**La poussée n'est pas radiale.** `DisplaceUnitInAdjacentDirection` construit un
`DisplaceUnitBehaviour(direction: 3, …)` — la case **`AdjacentVector`** du switch d'`Execute`, non
portée jusqu'ici. Sa destination vient d'un **vecteur fourni en options**
(`DisplaceUnitBehaviourOptions+0x28`), pas de la géométrie pousseur/poussée : **toutes** les cibles
reculent d'un hex dans la **même** direction, celle `casterTile -> tuile ciblée`.

Un port par `FindTileToPush` (direction 0) aurait coïncidé sur la cible principale et divergé sur les
latérales. **Mesuré** (mutation M1, configuration craftée) : le port radial envoie `orksRuntherd` en
`(1,6)`, le natif en `(2,6)`. C'est exactement le cas où « ça marche sur mon smoke » aurait tenu.

Les trois écarts de la direction 3, tous lus : direction unique · **un seul pas** (pas de boucle) ·
**aucun test d'occupation** dans le calcul de la destination (traité en aval par `content.IsFilled()`).

## 4. Deux découvertes de foyer partagé

**(a) Un steppable poussé est TUÉ, jamais déplacé.** Deuxième tête d'`Execute`, commune aux sept
directions, antérieure au switch :

```
if (UnitExtensions.IsSteppable(target)) { KillUnit(caster, target, ForSteppable()); return; }
```

Le port ne l'avait pas. Ajouté, au **foyer unique** existant
(`operations/movement.py::_kill_steppable_kill_unit`, qui joue `KillUnitOperation$$Execute` en
entier). Nouveau mirror `runner/components.py::unit_extensions_is_steppable`, à côté de son jumeau
`unit_extensions_is_displaceable`.

**(b) `allowSteppable` est un TRIGGER, et il est INVERSÉ.**
`IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select` fait
`allowSteppable = !(<+0x28>.ShouldTrigger(entities, 0x20))`. Le call-site passe
`<DSLTriggers+0x48>`, que `DSLTriggers$$.ctor` pose comme `op_LogicalNot(<le trigger sans opérande
de +0x40/+0x70>)` — et ce slot `+0x70` est **déjà nommé `YesTrigger`** par deux modules du port
(`effects/loki/martial_superiority.py`, `.../counter_attack.py`). Donc `allowSteppable` est
**toujours VRAI** ici, alors que le port n'implémentait que la branche `== 0`. Paramètre
`CanAddUnit(..., allow_steppable=…)`, défaut `False` = comportement historique inchangé.

## 5. L'unique hypothèse, et comment elle a été tranchée

`PerformAIAbility(ActiveTarget@0x68, <getAbilityType>, allowOnlyMove: false,
overrideMovement: <DSLFormulas+0x18> = Direct(0), null, null)`.

La lambda `...ItItchesAbility.<>c.<ExecuteBehaviour>b__2_0` est **absente des deux tables de symboles**
du build `rnca9r7q6c` — IL2CPP l'a dédupliquée, donc son corps n'est pas lisible statiquement.
Trois indices convergents : le seul autre producteur de ce paramètre
(`DSLBehaviors$$PerformAIAttackFromCurrentPosition`) a lui aussi sa lambda absente et le port l'a déjà
tranchée en `IdunBattle.Entities.UnitExtensions$$GetNormalAttackType` ; les deux `<>c` sont des classes
**sans capture**, et `GetNormalAttackType(unit:IEntity)` est statique à un seul argument ; les deux
call-sites construisent le **même** `PerformAIAbilityUnitBehaviour` champ pour champ.

**Tranchée LIVE**, et par deux observables : si la lambda rendait `1023 Burrowers` (la seule active du
Ripper Swarm), les summons auraient quitté le plateau — mesuré **3 sur le plateau, 0 hors**. Et le
total de dégât par cible est **bit-exact** : `{u81: 50, u83: 218}` des deux côtés.

## 6. `ABILITY_ATTACK_TYPE` contredit tout ce qu'on croirait

`...ItItchesAbility$$.ctor` → `AActiveAbility..ctor(this, &opts, 0)` = **`DirectTargetAttack`**, sur
une ability classée SUMMON, qui invoque réellement, et qui n'inflige aucun dégât direct.
`SummonAndAttackTarget` (1) et `Others` (2) auraient tous deux paru plus naturels. C'est le cas d'école
de la règle : lire le littéral, jamais le déduire.

Masque : `0x80040` = `TargetIsTile | TargetTileHasEnemyUnit`, `forceMeleeTarget = 0` =
`RangedBool.True` (enum inversé). L'entrée **migre** du dict de repli de `targeting.py` vers la classe
— contrat de disjonction, dans le même commit.

## 7. Confrontation live (board MC1_67, seed 777, positions craftées)

| étage | natif | port |
|---|---|---|
| E1/E3 ciblage + poussée | `(3,6)->(3,7)`, `(2,5)->(2,6)`, `(4,5)->(4,6)` | identique |
| E2 `Pinned` (0x429) | `[79, 81, 83]` | identique |
| E4 summons | 3, sur `(2,5) (3,6) (4,5)` | identique |
| E5 `ResetMovement` | caster toujours dans `toActivate` | identique |
| E6 on-appearance | 3 sur le plateau, dégât `{81: 50, 83: 218}` | **bit-exact** |

Sans `--place`, le Parasite démarre à 8 hex de la mêlée et la vue décision rend
`-> no-op certain` : la configuration à 3 cibles se **construit**, elle ne s'attend pas.

⚠ **Le summon natif porte `tyranNpc2RipperSwarm`, pas le constant config `tyranSmnRipperSwarm`.** La
substitution est faite en aval (`SpawnUnitBehaviour`, hors `ExecuteBehaviour`) — même écart que
`AlphaWarrior`/`tyranNpc4Warrior`. Compter les summons par `visualId` rend **0** : c'est ce que le
probe a mesuré à son premier passage. On les compte par **squadId neuf**.

Gardes : `tests/engine/runner/test_it_itches_live.py` (5 étages, **5 mutations vues rouges**, une par
test) · mesure : `probe_550_it_itches.py`.

## Résidus

- **#550-r1** — `Reserve`/`RemoveReservation` (quatre occurrences) sont des **no-op portés** : le port
  n'a aucun modèle de réservation de tuile (`IsTileReservedForOtherUnit`, `IsTilePendingDrafting`),
  déjà nommé par `CanAddUnit`. Ils journalisent, pour que l'arbre reste confrontable et que le rang
  soit tenu. Même statut pour `Kill(Caster, DeadUnits, ForClearDeadUnits)`, no-op **structurel** (la
  mort est finalisée inline côté port).
- **#550-r2** — l'écrasement de l'occupant **steppable de la destination** n'est atteint que par la
  direction 3. Les directions 0 et 2 le manquaient déjà (leur `FindTileToPush` porté fait `break` sur
  toute occupation) ; cette tranche ne les élargit pas, faute de porteur confrontable.
- **#550-r3** — le port passe en **domaine unité** (`Units(...)` explicite) là où le natif reste en
  domaine tuile de bout en bout (`UnitsByTeamSelector$$CountOrAdd` résout l'occupant pour le test
  `IsFriend` mais **ajoute l'entité source**). Écart de représentation, pas de sémantique ; le seul
  régime divergent serait une unité multi-hex, inatteignable ici (`IsDisplaceable` refuse `BigTarget`).
