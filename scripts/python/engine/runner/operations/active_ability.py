"""RE-RESOLUTION DE CIBLE d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` et sa
re-entree `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget` (#120bis).

POURQUOI CE MODULE EXISTE
-------------------------
Le natif n'a QU'UN site d'execution d'ability active (`ExecuteInternal`) : l'attaque normale EST une
active ability (`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility`). Le port,
lui, a DEUX portes d'operation -- `AttackDamageOperation.execute` (attaque normale, `damage_ops.py`)
et `AbilityHandler.visit_ActiveAbilityMessage` (cast, `abilities/handler.py`). #120 a de-forke sur ce
meme site l'emission du vecteur `On(0x2a = PreUnitAbility)` ; l'etage IMMEDIATEMENT SUIVANT -- la
re-resolution de cible -- restait absent des DEUX portes. Il vit ici, en UN foyer, appele par les
deux (le cabler sur une seule recreerait exactement le fork que #120 a ferme).

SEQUENCE NATIVE (decompile ghidra, build gqfc5mff6c) -- les etages qui nous concernent, dans l'ordre
d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` :

    ability     = AbilitiesDatabase.Get(abilityType)
    casterTiles = IdunBattle.Entities.EntityExtensions$$GetTiles(caster, state)
    target      = ability.GetActualTarget(caster, rawTarget)        # slot vtable 0x10
    if (target == null) return 0
    if (IsDeadUnitAndNotAllowedByAbility(abilityType, target)) return 0
    if (IsInvalidTarget(caster, casterTiles, target)) return 0      # gate de cible (#115)
    entities    = IdunBattle.Operations.ActiveAbilityOperation$$GetAbilityEntities(
                      caster, casterTiles, target, abilityType, options)
                  # entities@+0x38 <- EntityExtensions.GetTiles(target, state)   << LE SNAPSHOT >>
    skipEndTurn = GetSkipEndTurnFlag(options, ability, entities)
    skipUsed    = GetSkipAbilityUsedFlag(options, ability, entities)
    On(0x2a = PreUnitAbility)                       # <- la cascade de triggers PEUT bouger la cible
    if (!options@+0x4a && IsUnit(caster) && IsDead(caster)) return 0
    if (IsUnit(target) && Count(entities@+0x38) > 0) {              # << LA RE-RESOLUTION >>
        replaced = IdunBattle.Entities.UnitExtensions$$GetUnit(First(entities@+0x38), state)
        if (replaced != target)
            return ExecuteForReplacedTarget(caster, replaced, abilityType, options)
    }
    ... execution de la behaviour, puis On(0xb)/On(0xc)/AddFlags/On(0xe) ...

Le point de bascule est que `entities@+0x38` est fige AVANT le `On(0x2a = PreUnitAbility)` (c'est la liste de tuiles
que la cible occupait ALORS), tandis que `GetUnit(...)` est resolu APRES : si la cascade de triggers
a fait entrer une AUTRE unite sur cette tuile, c'est ELLE que l'ability frappe. La provenance du
slot est lue dans `GetAbilityEntities` lui-meme (`param_1[7] = EntityExtensions.GetTiles(finalTarget)`,
struct de 0x130 octets : +0x10 target, +0x30 GetMainTile(target), +0x38 GetTiles(target), +0x48
casterTiles).

`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget` :

    ability     = AbilitiesDatabase.Get(abilityType)
    newTarget   = ability.GetActualTarget(caster, replaced)         # slot vtable 0x10
    casterTiles = EntityExtensions.GetTiles(caster, state)
    entities    = GetAbilityEntities(caster, casterTiles, newTarget, abilityType, options)
    skipEndTurn = GetSkipEndTurnFlag(options, ability, entities)    # RECALCULES sur les NOUVELLES
    skipUsed    = GetSkipAbilityUsedFlag(options, ability, entities)#   AbilityEntities
    if (IsDeadUnitAndNotAllowedByAbility(abilityType, newTarget)) {
        AddFlagsAfterAbilityExecution(caster, skipUsed, skipEndTurn);  return 1;
    }
    options@+0x8 = Nullable(2)
    return IdunBattle.Operations.ActiveAbilityOperation$$Execute(caster, newTarget, abilityType, options)

-> ce n'est PAS un « on remplace la cible et on continue » : c'est une VRAIE RE-ENTREE dans
`Execute` -> `ExecuteInternal`, qui REJOUE toute la chaine sur la nouvelle cible (gate acteur-mort,
gate de cible `IsInvalidTarget`, un NOUVEAU `On(0x2a = PreUnitAbility)`, la behaviour, puis les flags de tour). Le
`ExecuteInternal` appelant, lui, `return`e immediatement : il ne pose NI behaviour NI flags -- les
flags sont poses UNE seule fois, par l'appel re-entrant.

CE QUE LE PORT MATERIALISE, ET CE QU'IL NE MATERIALISE PAS
---------------------------------------------------------
* `GetActualTarget` (`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`) : PORTE depuis
  #287-r14 (`actual_target` ci-dessous). La phrase qui vivait ici -- « le port passe deja une cible
  RESOLUE dans son message, la branche self-cast/tile/machine n'a donc pas de contrepartie offline »
  -- etait FAUSSE, et mesuree fausse : le port recoit tantot une UNITE (tous les tests live :
  `_ringed_cast.cast_and_confront` envoie `targetId: <unite>`), tantot une TUILE (la face DECISION
  portee : `abilityTargets` rend `kind: "tile"`). Le natif, lui, ne connait qu'UN regime parce qu'il
  TRANSFORME lui-meme. Consequence MESUREE (#287-r12, live `MC1_67` seed 777) : `1018 ValkyrieStrike`
  pose son effet `1022` sur la **TUILE** cote natif (`tileMeta.tiles[].effects` ; `decisionView.
  units[].effects` reste inchange) et sur l'**UNITE** des que le port recoit un id d'unite.
* `options@+0x8 <- Nullable(2)` : champ ECRIT par `ExecuteForReplacedTarget` et RELU par PERSONNE
  dans la chaine d'execution de ce build -- `ExecuteInternal` ne lit `options` qu'a +0x49/+0x4a/
  +0x4b/+0x4c/+0x50, `GetAbilityEntities` ne recopie que +0x10..+0x4f, `GetSkipEndTurnFlag` lit
  +0x49 et `GetSkipAbilityUsedFlag` +0x4b. Marqueur consomme hors moteur (publication de step/vue) ->
  no-op offline, comme les `Inform(...)` du DSL.
* Les `skip*` RECALCULES ne sont consommes QUE par la branche cible-morte (dans la branche vivante,
  c'est le `ExecuteInternal` re-entrant qui recalcule les siens). Cette branche est STRUCTURELLEMENT
  inatteignable offline (cf. `execute_for_replaced_target`) -> aucun code mort ecrit ici.
* `IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` est PORTE depuis
  #429-r1 (`is_dead_unit_and_not_allowed_by_ability` ci-dessous). Il est cable en TROIS points, un
  par PORTE du port -- le natif, lui, n'en a qu'UNE (`ExecuteInternal`) :
    - `AbilityHandler.visit_ActiveAbilityMessage`     (#429-r1)   -- cast commande ;
    - `DamageHandler.visit_AttackUnitMessage`         (#429-r1-r1) -- attaque normale commandee,
      AVANT le dispatch `NormalAttackType` concret (MV71 SPAWNE un drone) ;
    - `AttackDamageOperation.execute` (tete)          (#429-r1-r1) -- le FOYER des attaques normales
      DECLENCHEES (overwatch, riposte, drone commande, summon), qui n'empruntent AUCUN des deux
      visiteurs et appellent l'operation directement. Cote natif elles passent toutes par
      `IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$Execute` ->
      `Core.Services.OperationProcessor$$ActiveAbility` -> `ActiveAbilityOperation$$Execute` ->
      `ExecuteInternal`, donc par le MEME gate.
  Il etait
  acte NON PORTE parce que son gate `!ability.CanContinueOnDeadTarget()` lit un bit de
  `TargetingOptions` « RE-lu pour AUCUNE ability » -- l'inventaire de ses overrides est desormais
  releve par deux sources independantes, et le bit est le 38 du masque de CONTINUE
  (`_targetingOptionsForContinue` a +0xb0, donc +0xd8), PAS du masque principal a +0x70 : c'est
  pourquoi aucun `TARGETING_OPTIONS` du registre ne pouvait le porter.

RESIDU NOMME -- ESPACE D'IDS PARTAGE TUILE/ENTITE
-------------------------------------------------
Le natif distingue une cible-TUILE d'une cible-UNITE par le TYPE de l'entite (`IsUnit(actualTarget)`,
et `GetActualTarget` rend `GetMainTile(target)` des que la regle `TargetIsTile` (0x40) est posee).
Offline, une ability tile-target recoit un **id de tuile de `state.board`** dans le meme champ
`target_id` que les casts unite-target, et les deux espaces d'ids se CHEVAUCHENT (petits entiers) :
`is_unit(state, <id de tuile>)` peut donc rendre True par collision numerique.

Ce n'est PAS un risque introduit ici, et il ne peut PAS se manifester seul : la re-resolution ne
bascule que si l'OCCUPANT de la tuile snapshotee a change pendant la cascade, et le seul consommateur
porte de `On(0x2a = PreUnitAbility)` qui deplace une unite est `SwornProtector`/`SwornProtector_Protect` -- dont le
propre gate est exactement la meme comparaison d'id (`ev.target_id == owner_id`, `triggers/loki/
sworn_protector.py`). Un mis-fire de la re-resolution est donc STRICTEMENT EN AVAL d'un mis-fire deja
possible de SwornProtector, jamais une defaillance independante. Le fix propre est de separer les
deux espaces d'ids cote port (chantier transverse), pas d'ajouter ici un garde partiel :
`TARGETING_OPTIONS` n'est RE-lu que pour une poignee d'abilities, un garde base dessus serait inerte
pour toutes les autres et donnerait une fausse impression de couverture.
"""
from __future__ import annotations

from typing import Callable, Optional

from ..components import (PositionComponent, UnitComponent, unit_extensions_is_alive,
                          unit_is_alive)
from ..state import State


def is_unit(state: State, entity_id: Optional[int]) -> bool:
    """`IdunBattle.Entities.EntityExtensions$$IsUnit` — l'entite porte un `UnitComponent`. Une cible
    TUILE (abilities tile-target) ou une entite absente rend False, exactement comme le natif : la
    re-resolution ne concerne QUE les cibles-unites (une ability qui vise une tuile garde sa tuile
    quoi qu'il arrive au-dessus)."""
    if entity_id is None:
        return False
    e = state.get_entity(int(entity_id))
    return e is not None and e.get_component(UnitComponent) is not None


def get_tiles(state: State, entity_id: Optional[int]) -> list:
    """`IdunBattle.Entities.EntityExtensions$$GetTiles(entity, state)` — les tuiles OCCUPEES par
    l'entite, telles que `GetAbilityEntities` les fige dans `AbilityEntities@+0x38`.

    Offline la tuile est identifiee par sa position `(col, row)` (representation canonique du port ;
    l'id de tuile de `state.board` n'existe pas quand le board n'est pas charge). Le port ne modelise
    qu'UNE tuile par unite (les seules entites multi-tuiles sont les plateformes de MoW, jamais
    cibles d'un cast) -> liste de 0 ou 1 element.

    UNITE MORTE -> liste VIDE. C'est le mirror du board natif, d'ou une unite tuee est RETIREE
    (meme convention d'occupation que le selecteur `Units(tiles)` #57m, `CanAddUnit` et
    `walk_pathfinder`) -- et c'est ce qui rend le `Count(targetTiles) > 0` du natif protecteur :
    un cast sur une cible MORTE (revive, `ReviveEffect`/`ReviveUnitOperation` #66) ne re-resout
    jamais rien."""
    if entity_id is None:
        return []
    e = state.get_entity(int(entity_id))
    if e is None or not unit_is_alive(e):
        return []
    p = e.get_component(PositionComponent)
    if p is None:
        return []
    return [(p.col, p.row)]


def get_unit(state: State, tile) -> Optional[int]:
    """`IdunBattle.Entities.UnitExtensions$$GetUnit(tile, state)` — l'unite qui occupe la tuile
    MAINTENANT, ou None. Occupation = unite VIVANTE posee sur `(col, row)` (meme convention que
    `get_tiles` ci-dessus)."""
    if tile is None:
        return None
    col, row = int(tile[0]), int(tile[1])
    for uid, e in state.entities.items():
        if e.get_component(UnitComponent) is None or not unit_is_alive(e):
            continue
        p = e.get_component(PositionComponent)
        if p is not None and p.col == col and p.row == row:
            return int(uid)
    return None


def is_dead_unit_and_not_allowed_by_ability(state: State, ability_class,
                                            target_id: Optional[int]) -> bool:
    """`IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` — MIRROR 1:1
    du decompile (build courant) :

        ability = AbilitiesDatabase.Get(abilityType);
        if (!EntityExtensions.IsUnit(target))            return false;
        if (UnitExtensions.IsAlive(target, state))       return false;
        return !ability.CanContinueOnDeadTarget();       // slot 0x11 de `IActiveAbility`, resultat ^ 1

    C'est le PREMIER gate d'`ActiveAbilityOperation$$ExecuteInternal`, avant `IsInvalidTarget` : un
    cast sur une unite MORTE est un no-op complet (ni behaviour, ni flags, ni vecteur d'operation).

    #429-r1 -- POURQUOI IL EST PORTE MAINTENANT. Il etait acte NON PORTE ici meme et dans
    `abilities/targeting.py`, pour une raison NOMMEE : « l'inventaire des overrides [du slot 0x11]
    n'a pas ete releve », et un defaut « refuse » risquait de casser les abilities de resurrection.
    L'inventaire EST releve, par deux sources independantes :
      * dump Il2CppDumper (toutes les methodes de toutes les classes, sans deduplication de corps) :
        `CanContinueOnDeadTarget` n'a QU'UNE implementation, `AActiveAbility` -- aucun override ;
      * scan d'instructions du binaire (`probe_429r1_bit_readers_scan.py`) : un SEUL site pose le bit
        38 `AllowDeadTarget` que ce slot lit --
        `IdunBattleLogic.Entities.Abilities.Active.Loki.GreatFrostAxeAbility$$GetTargetingOptionsForContinue`.
    Le natif refuse donc pour TOUTE ability sauf `GreatFrostAxe` (1089), et le defaut « refuse » du
    port n'est pas une devinette mais la mesure. Une resurrection portee (`ReviveEffect` /
    `ReviveUnitOperation`, #66) n'est pas atteinte : elle ne passe pas par un `ActiveAbilityMessage`
    dont la CIBLE est le mort (`FoehammerAbility$$GetDeadHeroes` selectionne les cadavres DANS
    l'arbre, pas via `target_id`).

    `ability_class` = la classe du registre (`ABILITY_CLASSES[abilityType]`), ou `None` pour une
    ability NON PORTEE. `None` -> `can_continue_on_dead_target()` = False, ce qui est le comportement
    NATIF de toutes les abilities sauf une : le gate s'applique donc aussi aux non-portees, comme le
    vecteur d'operation et les flags de tour (#120/#139)."""
    if not is_unit(state, target_id):
        return False
    e = state.get_entity(int(target_id))
    # #429-r1-r3-r1-r2 : `UnitExtensions$$IsAlive` (flag `Dead` + pool `AliveUnits` + PV), PAS
    # `HealthComponent$$IsAlive` (hp >= 1) -- c'est le service que ce site appelle au decompile.
    # L'ecart mordait sur une unite a PV PLEINS sortie du pool (ENFUIE, RETIREE) : le gate la
    # laissait passer alors que le natif la refuse.
    if e is not None and unit_extensions_is_alive(e):
        return False
    if ability_class is None:
        return True
    return not ability_class.can_continue_on_dead_target()


def resolve_replaced_target(state: State, target_id: Optional[int],
                            target_tiles: list) -> tuple:
    """Le bloc de re-resolution d'`ActiveAbilityOperation$$ExecuteInternal`, JUSTE APRES le
    `On(0x2a = PreUnitAbility)` :

        if (IsUnit(target) && Count(targetTiles) > 0) {
            replaced = UnitExtensions.GetUnit(First(targetTiles), state);
            if (replaced != target) -> ExecuteForReplacedTarget(...)
        }

    `target_tiles` = le SNAPSHOT pris AVANT l'emission (`get_tiles(state, target_id)` appele au rang
    de `GetAbilityEntities`) : c'est tout l'interet du montage, la liste est figee, la resolution ne
    l'est pas.

    Renvoie `(replaced, new_target_id)` : `replaced=False` = aucune re-resolution (cible non-unite,
    snapshot vide, ou meme occupant) ; `replaced=True` = il FAUT re-entrer, avec `new_target_id` qui
    peut valoir None (tuile devenue vide : le natif appelle bien `ExecuteForReplacedTarget(.., null)`)."""
    if not is_unit(state, target_id) or not target_tiles:
        return (False, None)
    replaced = get_unit(state, target_tiles[0])
    if replaced == (None if target_id is None else int(target_id)):
        return (False, None)
    return (True, replaced)


def execute_for_replaced_target(state: State, caster_id: int, replaced_id: Optional[int],
                                reenter: Callable[[int], Optional[dict]]) -> Optional[dict]:
    """`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteForReplacedTarget` — la RE-ENTREE.

    `reenter(new_target)` = le `ActiveAbilityOperation$$Execute(caster, newTarget, abilityType,
    options)` de la voie appelante : `AbilityHandler.visit_ActiveAbilityMessage` pour un cast,
    `AttackDamageOperation.execute` pour l'attaque normale. C'est bien une re-entree COMPLETE (gates
    + nouveau `On(0x2a = PreUnitAbility)` + behaviour + flags de tour), pas un simple echange de cible.

    `replaced_id is None` (la tuile visee s'est VIDEE pendant la cascade) : le natif re-entre avec
    `null`, et `ExecuteInternal` sort aussitot sur `GetActualTarget(caster, null) == null -> return 0`
    (`IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` = `UnitExtensions.GetUnit(null)`) --
    AVANT la behaviour ET avant `AddFlagsAfterAbilityExecution` : l'ability est un NO-OP complet.
    Le port rend donc None. (La branche self-cast de `GetActualTarget`, qui renverrait le caster, ne
    peut pas etre atteinte ici : un cast self-cast a `target == caster`, donc l'occupant de la tuile
    snapshotee est le caster lui-meme -> `replaced == target` -> aucune re-resolution.)

    BRANCHE `IsDeadUnitAndNotAllowedByAbility` du natif (AddFlags seuls, sans behaviour) :
    STRUCTURELLEMENT inatteignable offline -- `replaced` sort de `get_unit`, donc c'est un occupant
    VIVANT ou None, et `IsUnit(null)` est faux. Rien a ecrire (pas de code mort), rien a deviner
    (`CanContinueOnDeadTarget` n'est RE-lu pour aucune ability, cf. l'en-tete)."""
    if replaced_id is None:
        return None
    return reenter(int(replaced_id))
