"""`IdunBattle.AI.Playbook.Loki.LakrimaePlaybook` -- face ATTACK du triggered `Lakrimae` (1541),
accorde par la RELIQUE `R_Crit_Lakrimae` (`items[].abilityId` + `allowedUnits = [deathTyphus]`,
voie `item` de #323) et EN DUR sur 5 npc `deathBossTyphus*` (`relicAbilities`).

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(35), MEME dispatcher que Psyker,
AggressiveOnslaught et SuppressiveFire (`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

Corps natif mirrore -- `IdunBattle.AI.Playbook.Loki.LakrimaePlaybook$$CalculateAttackUtilityInStepsInternal`
monte la SM `d__3` (case @+0x20, delegue scorer @+0x28 -- le playbook lui-meme n'est PAS stocke,
le corps n'en a pas besoin) ; le corps est
`LakrimaePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`, remis en C# :

    target = case@+0x20                              # la CIBLE du case
    if (EntityExtensions.HasTrait(target, (UnitTrait)5))     # 5 = Mechanical
        yield return Fix64.FromInt(0)
    else
        yield return Fix64.FromInt(GetUtilityValue(<cle statique>))

Trois lectures qui ne se devinent pas :

1. **Le predicat porte sur la CIBLE, pas sur le caster** -- `case@+0x20` est le meme champ que celui
   lu par `SuppressiveFirePlaybook` (dont le port est confronte). Le playbook ne consulte NI les
   stats NI les traits du porteur : c'est ce qui le rend greffable et, surtout, ce qui fait que sa
   valeur ne depend que de l'adversaire.

2. **`UnitTrait` 5 = `Mechanical`** -- l'enum est a qualifier (id 5 existe aussi ailleurs) ; ici il
   est confirme des DEUX cotes : le mirror `engine.entities.traits.unit_trait.UnitTrait(5).name`
   rend `Mechanical`, et le nom de la cle BC dit la meme chose en toutes lettres
   (`Lakrimae_LikesNonMechanicalEnemies`). Le predicat est NIE : le poids tombe quand la cible
   N'EST PAS mecanique.

3. **Le poids vient du BC, jamais code en dur** : la cle est le champ STATIQUE unique pose par
   `IdunBattle.AI.Playbook.Loki.LakrimaePlaybook$$.cctor` (une seule ecriture, `statics+0xb8`), lue
   par le delegue `TriggeredAbilityPlaybook<T>$$GetUtilityValue` (lookup plat `Dict<string,int>`,
   defaut 0). Valeur au gameconfig courant : `Utilities.Default.TriggeredAbilities.
   Lakrimae_LikesNonMechanicalEnemies` = **5**.

La face MOVE (`LakrimaePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`)
est un `yield Fix64.FromInt(0)` CONSTANT -- decompile lu, rien a porter. Elle n'est donc pas au
registre `TRIGGERED_MOVE_PLAYBOOKS`, et son absence == le comportement natif (#419).
"""
from __future__ import annotations

from ..entities.traits.unit_trait import UnitTrait, entity_trait_ids
from ..entities.triggered_ability_type import TriggeredAbilityType

# `UnitExtensions.HasTrait(target, (UnitTrait)5)` -- 5 = Mechanical (enum QUALIFIE, cf. en-tete).
_MECHANICAL = int(UnitTrait.Mechanical)
# Cle du poids plat `Utilities.Default.TriggeredAbilities` (champ statique pose par le `.cctor`).
_WEIGHT_KEY = "Lakrimae_LikesNonMechanicalEnemies"


class LakrimaePlaybook:
    """`LakrimaePlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1541). Seule la face ATTACK a un
    corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.Lakrimae)          # 1541

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` (cf. en-tete) :
        0 si la CIBLE porte le trait `Mechanical`, le poids sinon.

        Le substrat de traits est le foyer d'ENTITE `entity_trait_ids` (#225) -- kit gameconfig
        seede dans `UnitContext.traits` PLUS les traits accordes en bataille par le leaf DSL
        `AddTrait`. Lire le seul kit statique laisserait passer un `Mechanical` accorde en cours de
        bataille, que le natif, lui, voit (il interroge l'entite ECS)."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        tgt_ctx = sc.ctx(int(case_tgt_id)) if hasattr(sc, "ctx") else None
        vis = (getattr(sc, "vis_by_id", None) or {}).get(int(case_tgt_id))
        if _MECHANICAL in entity_trait_ids(tgt_ctx, vis):
            return 0.0
        return float(ctx.wt.triggered(_WEIGHT_KEY))
