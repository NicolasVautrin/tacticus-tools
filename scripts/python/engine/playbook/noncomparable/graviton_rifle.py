"""`GravitonRiflePlaybook` (0x4b6 = 1206, `votanIronmaster` << Vynn >>) -- face DECISION, #975.

REACHABILITY, LUE ET NON SUPPOSEE
---------------------------------
`data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` :

    active   1206   IdunBattle.AI.Playbook.Loki.GravitonRiflePlaybook

UNE seule entree, dict `active` (+0x68). Pas de code registered-but-dead.

BASE DE HIERARCHIE -- `NonComparablePlaybook<T>`, LUE dans `frida/classes.tsv`
------------------------------------------------------------------------------
    IdunBattle.AI.Playbook.Loki.GravitonRiflePlaybook  112  IdunBattle.AI.Playbook.NonComparablePlaybook`1

(Le `.ctor` decompile s'appelle `ComparablePlaybook<...>$$.ctor(this, 0x4b6, klass)` -- corps
trivial DEDUPLIQUE. `fire_and_reposition.py` cite deja `GravitonRifle` dans la liste des classes
que ce piege concerne : c'est cette lecture-la qui est confirmee ici.)

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.GravitonRiflePlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # cctor : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
        target  = entities@+0x10
        utility = Fix64.op_Implicit( UnitExtensions.GetStat(target, 5 = Health, 0, 0) )
        bucket.AddAction( BasePlaybook.GenerateAction(casterPosition, target, utility) )
    return bucket

`IdunBattle.AI.Playbook.Loki.GravitonRiflePlaybook$$.cctor` :

    <statics+0x00> = FixMath.NET.Fix64$$op_Implicit(1)

Le corps de boucle est OCTET POUR OCTET celui d'`AugmentedAssaultPlaybook` (1221) -- meme
`GetStat(., 5)`, meme `GenerateAction` -- MAIS **sans le `if (1 < targets.Count)` de 1221**. La
liste est enumeree telle quelle. Tout le discriminant de 1206 vit dans `ShouldEvaluate`.

LE GATE -- `ShouldEvaluate`, SURCHARGE DIRECTE DU SLOT 4, DEUX CONDITIONS
-------------------------------------------------------------------------
`IdunBattle.AI.Playbook.Loki.GravitonRiflePlaybook$$ShouldEvaluate(unit)`, verbatim :

    if (BasePlaybook.EnemyWillBeKilledWithNormalAttack(unit))  return false;
    repairType = UnitExtensions.GetRepairType(unit);
    res        = <IBattleQuery slot 0x45>(unit, repairType, false);
    return res.<+0x10>.<+0x18> == 0;              # List._size == 0

La SECONDE moitie est le corps d'`IdunBattle.AI.Playbook.Loki.GravitonRiflePlaybook$$
HasAnyRepairTarget`, INLINE ici -- les deux fonctions sont identiques a la comparaison finale
pres (`!= 0` pour `HasAnyRepairTarget`, `== 0` ici). Donc, en clair :

    ShouldEvaluate = !EnemyWillBeKilledWithNormalAttack(unit)  ET  !HasAnyRepairTarget(unit)

⚠ **LE SECOND GATE EST LE POINT PROPRE A 1206, ET IL SE LIT SUR LE KIT.** `votanIronmaster` porte
le trait `Mechanic` (gameconfig : `['Hero', 'PrioritisedEfficiency', 'Mechanic']`) : Vynn REPARE.
Le natif lui interdit donc de tirer au Graviton tant qu'il reste **quoi que ce soit a reparer** --
la reparation prime sur le tir. C'est la meme famille tactique que le passif `EcogSupport` de la
meme unite (`engine/runner/operations/triggers/loki/ecog_support.py`, #964-r1).

Les deux slots sont RESOLUS, pas supposes -- `data/symbols/rnca9r7q6c/metadata/interface_slots.tsv` :

    IBattleQuery  69 (0x45)  GetAllValidTargetsFromAllPossibleMovementTiles  3 params

d'ou la forme du retour : un objet dont `+0x10` est la LISTE UNION des cibles (toutes tuiles de
move confondues) et `+0x18` la carte `{position: [cibles]}` (c'est ce second champ que lit
`ExemplarOfTheMontkaPlaybook$$HasNormalAttackTarget`). 1206 lit le PREMIER, donc l'union -- et
c'est exactement ce que publie `abilityTargets(...).targets`.

`EnemyWillBeKilledWithNormalAttack` n'est pas re-porte : `IdunBattle.AI.Playbook.BasePlaybook$$
EnemyWillBeKilledWithNormalAttack` est un relais d'UNE ligne vers
`EnemyCouldBeKilledWithNormalAttack(attacker, onlyCertainKills = 1)` (decompile RELU pour cette
tranche), dont le foyer porte est `hammer_of_wrath._enemy_killed_by_normal_attack`.

BORNES DE PORT, toutes nommees
-------------------------------
* `GetRepairType` lit `<ActiveAbilityComponent>+0x2c`, **qu'aucun capteur ne publie** : ni
  `unitAbilityTypes` (qui n'expose que `+0x28`, sous `kind: "normal"`) ni `observeBattle`. La
  derivation ci-dessous mirrore les TROIS etages de `engine.runner.abilities.targeting.
  normal_repair_type_for` -- meme corps natif, autre substrat (dv/observeBattle + gameconfig au
  lieu du `State` du runner). Ce n'est pas un fork : c'est le seul substrat dont dispose la face
  DECISION. Capteur a poser : cf. le residu #975-r1.
* Canal MUET (`ability_targets is None`, unite absente, ou l'RPC ne connait pas l'ability de
  reparation) -> `has_any_repair_target` rend **False**, donc le gate NE MORD PAS et l'ability
  reste evaluee. Degradation PERMISSIVE, et c'est aussi exactement le comportement d'avant ce
  module (1206 n'avait aucune entree au registre NonComparable). Un `True` fabrique depuis une
  non-mesure ferait DISPARAITRE un cast que le natif fait.
* `_enemy_killed_by_normal_attack` porte deja sa propre borne (tri-etat `killSure` non publie ->
  `False`), documentee dans `hammer_of_wrath`.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait

from ._base import NCContext, _PlanTargetPlaybook, _traits, _unit_cfg


def _visual_id_of(ctx: NCContext, unit_id) -> str | None:
    """`visualId` de l'unite -- `observeBattle.units[].visualId`, le seul canal de `NCContext` qui
    le porte (`dv.units` ne publie que les abilities).

    ⚠ LA CLE EST `squadId`, PAS `entityId` : les deux existent sur la meme ligne et designent des
    choses differentes (l'id d'unite du port vs l'entite ECS). Mesure #975 : `entityId` rendait
    `None` sur les 10 unites du banc. Ici la consequence aurait ete SILENCIEUSE et PERMISSIVE
    (repair-type indeterminable -> gate inactif), donc invisible sans la mesure."""
    for u in (ctx.obs_units or []):
        if u.get("squadId") == unit_id or u.get("id") == unit_id:
            v = u.get("visualId")
            if v:
                return str(v)
    return None


def normal_repair_type(ctx: NCContext, unit_id) -> int | None:
    """`IdunBattle.Entities.UnitExtensions$$GetRepairType(unit)` -- pendant DECISION du foyer
    runner `engine.runner.abilities.targeting.normal_repair_type_for`.

    MEME corps natif (`<ActiveAbilityComponent>+0x2c`), MEMES trois etages, autre SUBSTRAT (le
    `State` du runner n'existe pas ici) :

      1. une ability MONTEE qui redefinit la reparation exposerait un membre `<nom>_Repair`
         d'`ActiveAbilityType` -- aucun sur ce build, la branche existe parce que la fabrique la
         prevoit (symetrique des 14 `<nom>_NormalAttack`) ;
      2. sinon une active dont le NOM commence par `Repair` ;
      3. sinon le trait `Mechanic`, qui est la voie REELLE des porteurs -- et la seule qui tire
         sur `votanIronmaster`, dont `activeAbilities` ne contient que `GravitonRifle`.

    Les noms d'ability viennent de `dv.units[].abilities[].name` (MESURE, ce qui est reellement
    monte) quand ils sont la, du kit gameconfig sinon. `None` = pas d'ability de reparation."""
    names: list = []
    for u in (ctx.units or []):
        if u.get("id") != unit_id:
            continue
        names = [a.get("name") for a in (u.get("abilities") or []) if a.get("name")]
        break
    vis = _visual_id_of(ctx, unit_id)
    cfg = _unit_cfg(vis) if vis else {}
    if not names:
        names = list(cfg.get("activeAbilities") or [])
    passives = list(cfg.get("passiveAbilities") or [])
    for nm in list(names) + passives:                                     # (1)
        member = getattr(ActiveAbilityType, f"{nm}_Repair", None)
        if member is not None:
            return int(member)
    for nm in names:                                                      # (2)
        member = getattr(ActiveAbilityType, str(nm), None)
        if member is not None and str(nm).startswith("Repair"):
            return int(member)
    if UnitTrait.Mechanic.name in (_traits(vis) or ()):                   # (3)
        return int(ActiveAbilityType.Repair)
    return None


def has_any_repair_target(ctx: NCContext) -> bool:
    """`IdunBattle.AI.Playbook.Loki.GravitonRiflePlaybook$$HasAnyRepairTarget(unit)` :

        res = <IBattleQuery slot 0x45 GetAllValidTargetsFromAllPossibleMovementTiles>(
                  unit, UnitExtensions.GetRepairType(unit), false)
        return res.<+0x10>.Count != 0

    `+0x10` = la liste UNION des cibles sur toutes les tuiles de move -- mirroree par
    `abilityTargets(uid, <repairType>).targets`, qui EST cette union (`fromHere` serait la vue
    par-position, celle que le natif ne lit PAS ici).

    Substrat muet ou repair-type indeterminable -> `False` (cf. les bornes de l'en-tete)."""
    if ctx.ability_targets is None:
        return False
    rid = normal_repair_type(ctx, ctx.uid)
    if rid is None:
        return False                       # `Nullable` VIDE natif -> aucune cible de reparation
    try:
        at = ctx.ability_targets(ctx.uid, int(rid)) or {}
    except Exception:
        return False
    for u in (at.get("units") or []):
        if u.get("unitId") != ctx.uid:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != int(rid):
                continue
            if a.get("targets"):
                return True
    return False


class GravitonRiflePlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.GravitonRiflePlaybook$$EvaluateNonComparable` (0x4b6 = 1206).

    utilite(cible) = `Fix64(GetStat(cible, 5 = Health))` = les PV COURANTS de la cible ennemie.
    Tout le discriminant est dans `should_evaluate` (double gate, cf. l'en-tete du module)."""
    ABILITY_ID = int(ActiveAbilityType.GravitonRifle)   # 0x4b6 = 1206
    MIN_UTILITY = 1.0     # `...GravitonRiflePlaybook$$.cctor` : `Fix64$$op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`...GravitonRiflePlaybook$$ShouldEvaluate` =
        `!EnemyWillBeKilledWithNormalAttack(unit) && !HasAnyRepairTarget(unit)`.

        Aucun `GetUseProbability` dans le chemin (le slot 4 est surcharge DIRECTEMENT) : il n'y a
        donc AUCUNE porte aleatoire a ne pas modeliser -- le port peut etre exact."""
        from .hammer_of_wrath import _enemy_killed_by_normal_attack
        if _enemy_killed_by_normal_attack(ctx):
            return False                   # `return false` natif : court-circuit
        return not has_any_repair_target(ctx)

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64.op_Implicit(UnitExtensions.GetStat(entities@+0x10, 5 = Health, 0, 0))` -- aucun
        filtre dans le corps de boucle (contraste `VexillaMagnifica`, qui `continue` sur
        `HasEffect(Stunned)`)."""
        hp = ctx.hp_cur_by_id.get(target)                          # GetStat(cible, 5 = Health)
        if not hp or hp <= 0:
            return None
        return float(hp)
