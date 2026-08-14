"""#1020 -- la feuille DSL `TransferDamage`, couplee a l'Operation
`engine/runner/operations/transfer_damage.py` (mirror `IdunBattle.Operations.TransferDamageOperation`).

Frontiere DSL/imperatif (doctrine #149) : l'artefact natif est un `CreateBehaviour`
(`IdunBattleLogic.Entities.Abilities.Triggered.Loki.SaviorProtocolsAbility$$CreateBehaviour` =
`If(Maybe(ConfigConst(chance)), TransferDamage(...), null)`), donc la STRUCTURE est un arbre DSL ;
la feuille, elle, appelle l'Operation impérative, comme `DirectDamage` appelle
`AttackDamageOperation.execute_direct`.
"""
from __future__ import annotations

from typing import Optional

from ....dsl.base import TargetsSelector, resolve_unit
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...operations.transfer_damage import transfer_damage_operation


class TransferDamage(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$TransferDamage(caster, originalTarget,
    transferTargets, transferAbility, attackAbility)` ->
    `IdunBattle.Entities.Behaviours.TransferDamageBehaviour$$Execute`, LU :

        caster         = <behaviour+0x50>.SelectSingle(entities)     # nul -> return (rien)
        originalTarget = <behaviour+0x58>.SelectSingle(entities)
        transferTargets= <behaviour+0x60>.Select(entities)           # une LISTE
        transferAbility= <behaviour+0x68>   (Nullable<AbilityOrEffect>)  # !HasValue -> return
        attackAbility  = <behaviour+0x70>   (Nullable<AbilityOrEffect>)  # !HasValue -> return
        hitIndex       = GetValueOrDefault(entities.<+0x108>)         # le coup COURANT
        -> processor.<slot 68 = TransferDamage>(caster, originalTarget, transferTargets,
                                                transferAbility, attackAbility, hitIndex)

    Le natif prend le caster de `<+0x58>` quand `<+0x50>` rend nul (`lVar20 = lVar17 != 0 ? lVar17
    : local_res8`) -- porte tel quel par le repli `source_sel -> entities.caster`.

    `transfer_ability` / `attack_ability` (#1020-r2, FERME) -- les deux `Nullable<AbilityOrEffect>`
    n'ont PAS le meme role, et l'un des deux est un GATE :

    * **GATE** : `Execute` exige `HasValue` sur LES DEUX (`if (*pcVar14 != '\\0')` imbriques) et
      `return` SANS RIEN FAIRE sinon. Un degat qui ne nomme AUCUNE ability source ne se transfere
      donc PAS -- divergence PERMISSIVE que le port avait (il transferait toujours).
    * **`attack_ability`** est le SEUL des deux que `TransferDamageOperation$$Execute` consomme :
      ses 0x18 octets sont recopies et passes en 5e argument `abilityOrEffect` du slot
      `64 = DirectDamage`. C'est lui qui NOMME la source du degat porte par le protecteur.
    * **`transfer_ability`** n'a, dans ce corps, aucun usage au-dela du null-check du pointeur --
      d'ou son absence cote operation. Il n'est pas inerte pour autant : il compte dans le gate.

    LES DEUX VALEURS, au moment ou ce behaviour tourne (RE recoupee par deux lectures
    independantes) : le ctor range `transferAbility` = `<DSLSelectors+0x88>` =
    `AbilityTypeSelector.CurrentAbilitySelector` = `AbilityEntities+0x60`, et `attackAbility` =
    `<+0x90>` = `TriggeringAbilitySelector` = `+0x98`. Or
    `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` ecrit `+0x60` **AVANT** d'appeler
    le behaviour et `+0x98` **APRES**. Donc ici `+0x60` vaut la triggered elle-meme
    (`SaviorProtocols`) et `+0x98` a garde ce que le publieur y avait mis -- l'ability qui inflige
    les degats. L'asymetrie de moment n'est pas un detail : si `BaseTriggeredAbility` ecrivait
    `+0x98` avant, `attackAbility` vaudrait `SaviorProtocols` au lieu de l'attaque.

    COLLAPSE ASSUME : le natif passe deux `IAbilityTypeSelector` (une famille de selecteurs dont le
    port n'a aucun mirror, et dont ces deux-la sont les seuls representants utilises) ; le port
    recoit les VALEURS deja resolues, que son appelant lit sur les deux memes canaux
    (`state.triggering_ability` pour `+0x60`, `ev.triggering_effect` pour `+0x98`). Meme forme de
    collapse que `_record_death_reason`, et nommee comme lui.

    Emet `TransferDamage` PAR CIBLE (le natif emet un pas de flux `0x23` par cible). PUR
    (stop=False) : `TransferDamageBehaviour$$Execute` recopie les 8 slots de l'`OperationResult`
    de l'operation, dont l'octet `+0x20` que `TransferDamageOperation$$Execute` ne pose jamais
    (il ne fait que `Combine` des resultats de `DirectDamage`)."""

    __slots__ = ("caster_sel", "original_target_sel", "transfer_targets_sel",
                 "transfer_ability", "attack_ability")

    def __init__(self, caster_sel: TargetsSelector, original_target_sel: TargetsSelector,
                 transfer_targets_sel: TargetsSelector,
                 transfer_ability=None, attack_ability=None):
        self.caster_sel = caster_sel
        self.original_target_sel = original_target_sel
        self.transfer_targets_sel = transfer_targets_sel
        self.transfer_ability = transfer_ability
        self.attack_ability = attack_ability

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            ectx.emit("TransferDamage", original_target=None, transfer_target=None, result=None)
            return OperationResult.ok()
        src_u = (resolve_unit(self.caster_sel, entities) if self.caster_sel is not None
                 else entities.caster)
        orig_u = resolve_unit(self.original_target_sel, entities)
        orig = (orig_u or {}).get("id")
        if orig is None:                       # `originalTarget` nul -> `Execute` RETOURNE
            ectx.emit("TransferDamage", original_target=None, transfer_target=None, result=None)
            return OperationResult.ok()
        src = (src_u or {}).get("id")
        # LE GATE, #1020-r2 : `if (transferAbility.HasValue) { if (attackAbility.HasValue) { ... } }`
        # -- sinon `return this`, sans operation ni pas de flux. Un degat qui ne nomme aucune
        # ability source ne se transfere donc PAS. Le port transferait toujours (PERMISSIF).
        if self.transfer_ability is None or self.attack_ability is None:
            ectx.emit("TransferDamage", original_target=int(orig), transfer_target=None, result=None)
            return OperationResult.ok()
        hit_index = getattr(entities, "hit_index", None)     # `AbilityEntities+0x108`
        # NORMALISATION du selecteur -- mirror du contrat natif `TargetsSelector` (IEnumerable) :
        # un selecteur MONO-ENTITE (`Owner()`/`Caster()`/`Target()`) rend un DICT d'unite, et
        # l'iterer donnerait ses CLES. Meme piege, meme parade que `entities/behaviours.py::Foreach`.
        # `SaviorProtocols` passe justement `Owner@<DSLSelectors+0x30>` en `transferTargets` : sans
        # cette normalisation, la boucle ne voit AUCUNE cible et le transfert est un no-op SILENCIEUX
        # (mesure live #1020 : le trigger matchait, le behaviour s'executait, et rien ne partait).
        raw = self.transfer_targets_sel.evaluate(entities)
        cibles = [] if raw is None else ([raw] if isinstance(raw, dict) else list(raw))
        for u in cibles:
            tid = u.get("id") if isinstance(u, dict) else None
            if tid is None:
                continue
            res = transfer_damage_operation(state, src, int(orig), int(tid),
                                            hit_index=hit_index,
                                            attack_ability=self.attack_ability)
            ectx.emit("TransferDamage", original_target=int(orig), transfer_target=int(tid),
                      result=res)
        return OperationResult.ok()
