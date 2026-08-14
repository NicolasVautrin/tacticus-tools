"""L'ELARGISSEMENT MULTI-CIBLE de l'attaque normale d'`AncientFury` (#1050-r1).

`AncientFury` (1256) substitue l'attaque normale de son porteur par `AncientFury_NormalAttack`
(1162), et cette classe-la surcharge **le SELECTEUR DE CIBLES** de l'attaque normale. Ce n'est PAS
la famille du cleave (#478) : ici il n'y a pas de second `Attack(...)` aux bornes de config -- il y
a UN SEUL `Attack(...)`, dont le selecteur rend N cibles, et **chacune recoit l'attaque d'ARME
COMPLETE**.

## La chaine, relue de bout en bout sur `rnca9r7q6c`

    ALoki_NormalAttackAbility$$ExecuteBehaviour :
        weapon = FindAttackWeapon(entities)          # UNE fois, contre la cible du MESSAGE
        if (weapon == null) return default
        ExecuteInformWeapon(weapon, entities, 0)     # UNE fois
        ExecuteNormalAttack(abilityState, entities, weapon)
        return ExecuteTriggerAbilities(entities, weapon)     # On(0x26), UNE fois

    ALoki_NormalAttackAbility$$ExecuteNormalAttack :
        target = this.vslot(0x4a8)()                          # <- $$GetTarget, ELARGI ici
        b = GetAttackDamageBehaviour(abilityState, entities, attackWeapon, target)
        b = b op_BitwiseAnd DSLBehaviors$$EvaluateAbilities(0x4a, immediately: true)
        return AActiveAbility$$ExecuteAtomic(b, entities, 0x3d)

    ALoki_NormalAttackAbility$$GetAttackDamageBehaviour(..., attackWeapon, target) :
        b1 = DSLBehaviors$$AttackDamage(Caster@0x48, Target@0x60,
                                        <vslot 0x4d8 AttackAmount>, Direct(attackWeapon+0x10),
                                        <vslot 0x4c8 AttackHits>, source, options)
        b2 = <vslot 0x4e8 GetCustomNormalAttackBehaviour>(abilityState)
        b  = b1 op_BitwiseAnd b2
        b3 = DSLBehaviors$$ExecuteAdditionalHitsWithDamageProfileType(Caster@0x48, target, ...)
        b  = b  op_BitwiseAnd b3
        return IdunBattleLogic.Entities.DSLBehaviors$$Attack(Caster@0x48, target, b, source)

⚠ **LE VSLOT `0x4a8` N'EST PAS LE FOLD.** Trois citations du depot ecrivaient
`$$GetCustomNormalAttackBehaviour @ vslot 0x4a8` ; le fold est `0x4e8`, appele DANS
`$$GetAttackDamageBehaviour`, et `0x4a8` est `$$GetTarget`, appele EN TETE d'`ExecuteNormalAttack`
et passe en 5e argument. `AncientFury_NormalAttackAbility$$GetTargets` -- un
`return this.vslot(0x4a8)()` nu -- apparie le slot a son unique surcharge nommee du build. Cette
confusion est ce qui masquait le present residu : elle faisait lire le 5e argument comme un
behaviour, alors que c'est un SELECTEUR.

## L'artefact porte : `AncientFury_NormalAttackAbility$$GetTarget`

    GetTarget = Target@0x60
              op_Addition
                ConditionalSelector( IsMeleeAttack,
                    AdjacentEnemies(Caster@0x48, unique, 3) & AdjacentUnits(Target@0x60, unique, 3),
                    AdjacentUnits(Target@0x60, unique, 3)
                      & ( SurroundingEnemies(CasterTiles@0x58,
                                             MinDistance(CasterTiles@0x58, TargetTiles@0x78),
                                             unique, 3)
                        op_Subtraction
                          SurroundingEnemies(First(SortByDistance(CasterTiles@0x58,
                                                                  Tiles(Target@0x60)), 1),
                                             Sum(MinDistance, <DSLFormulas+0x38> = Direct(-1)),
                                             unique, 3) ) ) )

-- mot pour mot l'i2 : << Normal **melee** attacks also deal damage to each enemy that is adjacent
to both the target and Galatian. Normal **ranged** attacks also deal damage to each enemy that is
both adjacent to the target and **exactly 2 hexes** away from Galatian >>. L'anneau EXACT est la
soustraction `Surrounding(d) - Surrounding(d-1)`.

Les DEUX `SurroundingEnemies` sont la surcharge **4-args** (`SurroundingEnemies(this, unit, range,
unique, unitSelectionType)`), LUE au decompile : le meme selecteur sert de CENTRE (`SurroundingTiles
(unit, 1, range) - Tiles(unit)`) **ET** de reference d'equipe (`Enemies(unit, ...)`). Le port passe
donc le MEME noeud en `center` et en `reference`, comme le prescrit `entities/selectors/units.py`.

`First(source, 1, 0)` : le 3e parametre natif se nomme **`amount`**, pas `index` -- la surcharge
`DSLSelectors$$First(this, entities, amount, ignoreForcedTargets)` boxe l'entier avant de deleguer.
`amount = 1` = << le PREMIER >>, ce que rend `units.First(source)` (defaut `index=0`).

## Ce que `AttackBehaviour$$Execute` fait de ces N cibles -- et ce que le port en garde

    caster  = <behaviour+0x50>.SelectFirst(entities)        # slot 1
    targets = <behaviour+0x58>.Select(entities)             # slot 0  -> LISTE
    if (targets.Count > 1) targets = targets.OrderBy(<>c.b__5_0).ToList()
    GetAttackOptions(entities, &options)
    for (i = 0 ; i < targets.Count ; i++) {
        cur = targets[i] ; next = (i < Count-1) ? targets[i+1] : null
        e = AbilityEntities(entities) ; e.caster = caster ; e.target = cur
        if (prev == null || prev != cur) processor.<slot 0x3a StartAttack>()
        <behaviour+0x60>.Execute(e)                          # les coups d'ARME sur `cur`
        if (next == null || next != cur) processor.<slot 0x3b FinishAttack>()
        prev = cur
    }

Trois faits que le port mirrore, et un qu'il ne peut pas :

* **le behaviour interne recoit `entities.target = la cible COURANTE`** -- c'est pourquoi
  l'`AttackDamage(Caster@0x48, Target@0x60, ...)` frappe chaque cible avec les coups d'ARME
  COMPLETS, et non un paquet aux bornes du passif comme le cleave #478 ;
* **un `StartAttack`/`FinishAttack` par cible** (donc `On(PreAttack = 5)` et `On(Attack = 9)` par
  cible) -- ils ne sont groupes que pour des cibles CONSECUTIVES IDENTIQUES, ce que `unique` rend
  impossible ici ;
* **l'ARME est choisie UNE SEULE FOIS**, dans `ExecuteBehaviour`, contre la cible du MESSAGE, et
  PASSEE : `$$AttackHits(abilityState, attackWeapon)` = `Direct(attackWeapon+0x20)`. Une cible
  additionnelle plus loin ne fait donc PAS basculer l'attaque sur l'autre arme -- d'ou le parametre
  `weapon_ref_target_id` du vecteur normal (sans lui, le port re-choisirait l'arme par cible) ;
* **ce que le port NE PEUT PAS mirrorer sans decouper le vecteur normal** : le rang de la cible
  PRIMAIRE dans le tri. Cf. `#1076` ci-dessous.

## RESIDU `#1076` -- LE RANG DE LA CIBLE PRIMAIRE DANS LE TRI

Le natif trie **toutes** les cibles ensemble (`OrderBy(b__5_0)`, cle = l'entite) : la cible du
message n'est PAS forcement frappee en premier. Le port, lui, la frappe toujours en tete, parce que
le preambule d'`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` (`On(PreUnitAbility
= 0x2a)`, gate acteur-mort, re-resolution de cible `SwornProtector`, choix d'arme) n'est PAS
separable du premier coup dans `damage_ops/normal.py` -- ces quatre etages y vivent dans le meme
corps que l'attaque. Conserquence MESURABLE : des qu'une cible additionnelle porte un id INFERIEUR
a celui de la primaire, l'ordre des tirages `state.rng` differe du natif (les montants sont alors
justes mais permutes entre cibles). Les cibles ADDITIONNELLES entre elles, elles, sont bien dans
l'ordre natif.

## Ce qui N'EST PAS de cette tranche

* la face DECISION : `IdunBattle.AI.Playbook.Loki.AncientFury_NormalAttackAbilityPlaybook$$
  MakeDamagePredictions` existe et n'est pas portee -- la prediction de degat de l'IA ignore donc
  les cibles additionnelles (residu, cf. le backlog) ;
* le collapse `CasterTile@0x50` / `CasterTiles@0x58` du port (#478-r1) : les deux `CasterTiles` de
  cet arbre passent par le meme noeud `CasterTile()` (l'EMPREINTE). Inerte pour un caster MONO-hex
  -- ce que sont tous les greffons du pool ; le VRAI porteur `ultraSmnDreadnought` porte le trait
  `BigTarget`, donc si son empreinte est multi-hex, `First(SortByDistance(CasterTiles, ...))` (une
  SEULE tuile) et `CasterTiles` (toutes) cesseraient de coincider -- l'anneau n'est alors plus
  centre au meme endroit dans les deux `SurroundingEnemies`.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.selectors.accessors import CasterTile, Target, TargetTile
from ....entities.selectors.geometry import ConditionalSelector
from ....entities.selectors.tiles import Caster
from ....entities.selectors.units import (
    AdjacentEnemies, AdjacentUnits, And, First, SortByDistance, Sub, SurroundingEnemies, Tiles,
    Union
)
from ....entities.formulas import MinDistance, Sum
from ....entities.triggers import IsMeleeAttack
from ....entities.unit_selection_type import UnitSelectionType
from ..behaviours.context import entities_from_state
from ....services.custom_normal_attack import substitutes_normal_attack

if TYPE_CHECKING:
    from ...state import State

#: `UnitSelectionType` LU au DERNIER argument de chaque `DSLSelectors$$*` de
#: `AncientFury_NormalAttackAbility$$GetTarget` -- les quatre appels portent le litteral `3`
#: EXPLICITEMENT dans le decompile (`(void *)0x3`), aucun n'emprunte une variante a `3` implicite.
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


def _adjacent_units_of_target():
    """`AdjacentUnits(Target@0x60, unique: 1, 3)`.

    Le natif l'INSTANCIE DEUX FOIS -- une par branche du `ConditionalSelector` -- et non une fois
    partagee : deux `call` distincts dans le corps. On rend un noeud NEUF a chaque appel pour la
    meme raison (les noeuds du port sont sans etat, mais l'arbre doit rester le mirror de ce qui
    est ECRIT)."""
    return AdjacentUnits(Target(), Const(1), selection_type=SELECTION)


def ancient_fury_targets():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.AncientFury_NormalAttackAbility$$GetTarget`
    (vslot `0x4a8`) -- MIRROR 1:1, dans l'ORDRE de construction du decompile.

    ⚠ `Union` = `IdunBattle.DSL.TargetsSelector$$op_Addition`, et son operande GAUCHE est
    `Target@0x60` : la cible du message est DANS le selecteur, en TETE avant tri. Les deux branches
    du conditionnel sont intersectees avec `AdjacentUnits(Target)`, qui EXCLUT son propre centre --
    donc aucune cible additionnelle ne peut etre la primaire, et l'union est sans doublon."""
    # Ordre du decompile : SortByDistance/First d'abord, MinDistance ensuite, puis les deux
    # `SurroundingEnemies`, puis la soustraction, puis le trigger, puis les deux `AdjacentUnits`.
    #
    # `CasterTiles@0x58` et `TargetTiles@0x78` passent par `CasterTile()`/`TargetTile()`, les noeuds
    # d'EMPREINTE du port (`_feet`) -- cf. le collapse #478-r1 note en en-tete.
    _min_distance = MinDistance(CasterTile(), TargetTile())
    # `First(SortByDistance(CasterTiles@0x58, Tiles(Target@0x60)), 1)` = la tuile du CASTER la plus
    # proche de la cible. Centre ET reference d'equipe du second `SurroundingEnemies` (surcharge
    # 4-args). Noeud RECONSTRUIT pour les deux roles : le natif passe le MEME `pvVar5` aux deux
    # positions du meme appel, et le port n'a pas de partage de noeud.
    def _nearest_caster_tile():
        return First(SortByDistance(CasterTile(), Tiles(Target())))

    melee = And(AdjacentEnemies(Caster(), Const(1), selection_type=SELECTION),
                _adjacent_units_of_target())
    ranged = And(
        _adjacent_units_of_target(),
        Sub(SurroundingEnemies(CasterTile(), _min_distance, reference=CasterTile(),
                               selection_type=SELECTION),
            SurroundingEnemies(_nearest_caster_tile(),
                               # `Sum(MinDistance, <DSLFormulas+0x38>)` : le slot partage vaut
                               # `Direct(-1)` (identification etablie et multi-source du depot,
                               # cf. `entities/effects/loki/terrors_lament.py`).
                               Sum(_min_distance, Const(-1)),
                               reference=_nearest_caster_tile(),
                               selection_type=SELECTION)))
    return Union(Target(), ConditionalSelector(IsMeleeAttack(), melee, ranged))


class _Widened:
    """Une attaque normale dont `$$GetTarget` est SURCHARGE pour rendre N cibles.

    `passive` = le `TriggeredAbilityType` qui SUBSTITUE l'attaque normale (la cle de la cascade
    `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility`, MEME foyer que
    `NORMAL_ATTACK_CLEAVES`). `build` = le constructeur de l'arbre de `$$GetTarget`."""
    __slots__ = ("passive", "build")

    def __init__(self, passive: str, build):
        self.passive, self.build = passive, build


#: Les attaques normales substituees qui SURCHARGENT `$$GetTarget` (vslot `0x4a8`). La liste est
#: CLOSE et ce n'est pas une lecture par affinite de nom : `AncientFury_NormalAttackAbility$$
#: GetTarget` est la SEULE surcharge nommee de ce slot dans la table de symboles du build (recherche
#: `Abilities\..*\$\$GetTarget$` : les six autres appartiennent a des abilities ACTIVES ou
#: TRIGGERED, aucune n'est une `<X>_NormalAttackAbility`).
#:
#: ⚠ DISJOINT de `NORMAL_ATTACK_CLEAVES` (#478) PAR CONSTRUCTION -- les deux familles surchargent
#: des slots DIFFERENTS (`0x4a8 GetTarget` ici, `0x4e8 GetCustomNormalAttackBehaviour` + un
#: `Execute<X>` la-bas) et la cascade `AddNormalAttackAbility` ne monte qu'UN passif substituant par
#: unite. Le cran `test_1050_optimized_gait_offline.py` etage 4 garde cette disjonction.
WIDENED_NORMAL_ATTACKS: dict = {
    "AncientFury": _Widened("AncientFury", ancient_fury_targets),
}


def widened_for(passive_abilities, active_abilities=None, visual_id=None, traits=None,
                config_active_abilities=None) -> "Optional[_Widened]":
    """L'entree de `WIDENED_NORMAL_ATTACKS` que la CASCADE native attribue a cette unite, ou `None`.

    Delegue a `engine.services.custom_normal_attack.substitutes_normal_attack` -- le FOYER de la
    cascade `UnitFactory$$AddNormalAttackAbility` (voie PASSIVE, puis voie ACTIVE, puis branche
    trait `Boss`, puis garde du repli generique), exactement comme `additional_targets.cleave_for`.
    Passer par lui plutot que par un `passive in passives` est ce qui garantit que l'elargissement
    part exactement quand l'attaque normale CONCRETE `AncientFury_NormalAttack` est montee."""
    for name, entry in WIDENED_NORMAL_ATTACKS.items():
        if substitutes_normal_attack(name, passive_abilities=passive_abilities,
                                     visual_id=visual_id, active_abilities=active_abilities,
                                     traits=traits,
                                     config_active_abilities=config_active_abilities):
            return entry
    return None


def widened_targets(state: "State", caster_id: int, target_id: Optional[int],
                    entry: "_Widened", is_melee: bool) -> list:
    """Les cibles de `$$GetTarget`, DANS L'ORDRE NATIF -- `Select` puis, si plus d'une,
    `OrderBy(<>c.b__5_0)` d'`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`.

    La cle du tri est l'ENTITE (cle scalaire par-unite) : le port trie par `id`, MEME mirror que le
    mode `multi=True` d'`AttackWithAttackDamage` (`runner/abilities/behaviours/combat.py`), et pour
    la meme raison -- c'est le meme `OrderBy` du meme `AttackBehaviour$$Execute`.

    ⚠ Le tri n'a lieu QUE si `Count > 1` cote natif (`if (1 < iVar12)`). Il est stable et sur une
    liste d'un element il est l'identite : le port trie inconditionnellement, ce qui est le meme
    resultat.

    `is_melee` = la nature de l'ARME CHOISIE par `ALoki_NormalAttackAbility$$FindAttackWeapon`,
    threadee dans `ctx.attack_kind` que lit `IdunBattle.Entities.Triggers.IsMeleeAttackAbility
    Trigger$$ShouldTrigger`. C'est la MEME entree que la gate `cleaves_when_melee` du #478, et c'est
    ce que dit l'i2 (<< normal melee attacks >> / << normal ranged attacks >>). Le corps natif du
    trigger est un corps DEDUPLIQUE commun aux `AbilityTrigger` composites, donc illisible tel quel
    -- l'entree est etablie par le precedent porte (`runner/operations/triggers/loki/act_of_faith.py`
    pose `attack_kind` depuis la nature du coup), pas par ce corps."""
    if target_id is None:
        return []
    entities = entities_from_state(state, caster_id, target_id)
    # `IsMeleeAttack` lit `ctx.attack_kind` ; le natif lit la nature de l'ARME du cast.
    entities.attack_kind = "melee" if is_melee else "ranged"
    ectx = ExecutionContext(state=state, rng=state.rng)
    del ectx                                   # l'arbre est PUR : aucun tirage, aucun emit
    picked = entry.build().evaluate(entities)
    out = [u for u in picked if isinstance(u, dict) and u.get("id") is not None]
    return sorted(out, key=lambda u: int(u.get("id")))


def additional_target_ids(state: "State", caster_id: int, target_id: Optional[int],
                          entry: "_Widened", is_melee: bool) -> list:
    """Les cibles ADDITIONNELLES seules (la primaire retiree), dans l'ordre natif.

    La primaire est retiree par son ID et non par position : le `Union` la place en tete AVANT le
    tri, mais l'`OrderBy` peut l'envoyer ailleurs -- c'est exactement le residu `#1076` de
    l'en-tete, et retirer << le premier element >> l'aurait masque en retirant la mauvaise unite."""
    tid = None if target_id is None else int(target_id)
    return [int(u["id"]) for u in widened_targets(state, caster_id, target_id, entry, is_melee)
            if int(u["id"]) != tid]


def execute_widened_normal_attack(state: "State", caster_id: int, target_id: Optional[int],
                                  entry: "_Widened", is_melee: bool,
                                  spread_pct: Optional[int] = None) -> list:
    """La QUEUE de la boucle d'`AttackBehaviour$$Execute` : l'attaque d'ARME COMPLETE sur chaque
    cible ADDITIONNELLE, dans l'ordre natif. Rend `[{"target": id, "attack": {...}}, ...]`.

    Chaque cible passe par le vecteur d'attaque NORMALE (`AttackDamageOperation.execute`), et pas
    par une feuille aux bornes de config : c'est le point qui separe cette famille du cleave #478.
    Les deux parametres qui suivent sont le mirror des etages que la boucle native NE REJOUE PAS :

    * `in_attack_loop=True` -- `On(PreUnitAbility = 0x2a)` et la re-resolution de cible
      (`SwornProtector`) appartiennent a `IdunBattle.Operations.ActiveAbilityOperation$$
      ExecuteInternal`, EN AMONT d'`ExecuteBehaviour` : un seul passage par cast, pas un par cible.
    * `weapon_ref_target_id=<la primaire>` -- `FindAttackWeapon` est appele une seule fois dans
      `ExecuteBehaviour` et l'arme est PASSEE jusqu'a `$$AttackHits(abilityState, attackWeapon)`.
      Sans ce parametre, une cible additionnelle plus eloignee ferait basculer le port sur l'autre
      arme, alors que le natif garde celle du cast.

    Le `On(PreAttack = 5)` et le `On(Attack = 9)` restent, EUX, par cible : ils viennent des slots
    `0x3a StartAttack` / `0x3b FinishAttack` que la boucle pousse a chaque tour."""
    from ...operations.damage import AttackDamageOperation      # lazy : cycle abilities<->damage
    out = []
    for tid in additional_target_ids(state, caster_id, target_id, entry, is_melee):
        atk = AttackDamageOperation.execute(state, caster_id, tid, spread_pct,
                                            in_attack_loop=True,
                                            weapon_ref_target_id=target_id)
        if atk is not None:
            out.append({"target": tid, "attack": atk})
    return out


__all__ = ["WIDENED_NORMAL_ATTACKS", "SELECTION", "ancient_fury_targets", "widened_for",
           "widened_targets", "additional_target_ids", "execute_widened_normal_attack"]
