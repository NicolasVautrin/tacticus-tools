"""Les playbooks Comparable dont `ShouldExecute` refuse le cast quand l'ATTAQUE NORMALE tuerait deja
la cible (`#419-r1-tr14-r5-r2-r1-r1-r1`).

Trois corps natifs LUS, QUINZE classes portees, une seule primitive : `BasePlaybook$$WillNormalAttackKill`
(portee sur `BasePlaybook.will_normal_attack_kill`, `base.py`). Le sens tactique est le meme partout
-- ne pas gaspiller une ability speciale sur une cible que la frappe de base acheve deja.

Le gate vit au slot de vtable `+0x328`, appele par
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
APRES `CalculateCustomUtility + CalculateUtilityFromPredictions` et AVANT les trois termes
positionnels ; `false` ==> `Nullable` VIDE, donc AUCUNE action poussee dans le `Bucket` pour ce
couple (tuile, cible). La degradation qu'il ferme est PERMISSIVE : sans lui le port propose des casts
que le natif ecarte, sans erreur ni crash.

## Les trois corps, et pourquoi ils sont TROIS classes ici

Les corps sont DEDUPLIQUES par IL2CPP, donc la table des symboles n'en nomme qu'un proprietaire par
corps. Le recensement s'est fait NIVEAU PAR NIVEAU (`class_get_methods` de la chaine de parents, RPC
`resolveMethodPtr`) sur les 94 classes concretes dont la chaine passe par `ComparablePlaybook`1` --
la seule technique qui distingue « herite » de « REDECLARE sur le meme corps ». Resultat re-derive :
16 heritent le gate d'`ALoki_NormalAttackPlaybook`1`, 35 declarent le corps trivial `return true`,
**43 declarent un corps PROPRE** (29 distincts). Ces trois-la en couvrent **17**.

* `IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$ShouldExecute` -- **14** classes :
  1004 MortisRound (portee dans `loki_custom.py`, qui delegue ici), 1008 HarbingerOfDestruction,
  1022 BringerOfDespair, 1025 SkyStrike, 1027 PsychicMaelstrom, 1044 IncendiaryShells,
  1048 FragstormGrenadeLauncher, 1062 SanctorumMissile, 1078 Fragstorm, 1080 HellfireShells,
  1089 GreatFrostAxe, 1104 SpiritLeech, 1105 CrushingClaws, 1171 DakkaDakkaDakka.
* `IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$ShouldExecute` -- **2** classes :
  1017 FragBomb, 1026 BasiliskBarrage.
* `IdunBattle.AI.Playbook.Loki.MultiThreatEliminatorPlaybook$$ShouldExecute` -- **1** classe :
  1006 MultiThreatEliminator.

Chaque `ability_id` est LU dans le `.ctor` de sa classe native (`ComparablePlaybook<T>..ctor(this,
<id>, klass)`), jamais devine du nom de la classe.

## Ce que ce module ne change PAS

Les 17 ids retombaient jusqu'ici sur `DefaultActiveAbilityPlaybook` (aucune entree au registre). Les
classes d'ici en HERITENT, donc `make_damage_predictions`, `calculate_custom_utility` et
`make_effect_predictions` restent EXACTEMENT ce qu'ils etaient : le seul delta est `should_execute`.
"""
from __future__ import annotations

from .base import register
from .common import DefaultActiveAbilityPlaybook
from ..entities.active_ability_type import ActiveAbilityType


class SpiritLeechPlaybook(DefaultActiveAbilityPlaybook):
    """`IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$ShouldExecute`, lu verbatim :

        return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

    Une seule clause, et elle N'UTILISE PAS `attackHealUtility` -- consequence directe : le rang du
    terme lifesteal de 1104 (`#419-r1-tr14-r5-r2-r1-r1-r3`, somme APRES `CalculateActionUtility` cote
    port, AVANT cote natif) reste SANS EFFET sur ce gate. Porter le gate ne rend donc pas ce residu
    mordant, contrairement a ce qu'annoncait sa fiche.

    Cette UNIQUE classe porte les QUATORZE identites que le corps natif dedouble (liste au module) :
    meme motif que `NormalAttackPlaybook`, qui porte les seize identites d'attaque normale. Une
    instance par identite (`ability_id` d'instance) -- c'est ce qui mirrore les quatorze classes
    natives, toutes concretes, chacune avec son propre `MethodInfo` sur le meme corps.

    NON PORTE ici, et ce n'en est pas le sujet : `SpiritLeechPlaybook$$MakeEffectPredictions` (le
    seul override de ce slot dans le build -- effet `Pinned` de poids 0, donc inerte)."""

    def __init__(self, ability_id: int):
        self.ability_id = int(ability_id)

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        return not self.will_normal_attack_kill(ctx, target, caster_tile)


class MultiThreatEliminatorPlaybook(DefaultActiveAbilityPlaybook):
    """`IdunBattle.AI.Playbook.Loki.MultiThreatEliminatorPlaybook$$ShouldExecute`, lu verbatim :

        if (!(attackHealUtility > Fix64(0))) return false;
        return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

    DEUX clauses, et l'ordre compte : le seuil d'utilite est evalue EN PREMIER, la prediction
    d'attaque normale n'est faite que s'il passe (court-circuit `&&`). C'est la conjonction du gate
    `utility > 0` deja porte par l'attaque normale (`#419-r1-tr14-r5-r2-r1-r1`) et du gate de kill
    ci-dessus -- le seul corps du build qui porte les deux.

    `attackHealUtility` = `CalculateCustomUtility + CalculateUtilityFromPredictions`, donc AVANT les
    trois termes positionnels : c'est ce que `calculate_action_utility` passe."""

    ability_id = int(ActiveAbilityType.MultiThreatEliminator)   # 1006 = 0x3ee

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        if not utility > 0.0:
            return False
        return not self.will_normal_attack_kill(ctx, target, caster_tile)


# `SpiritLeechPlaybook$$ShouldExecute` : les 14 identites, chacune lue dans son propre `.ctor`.
# 1004 MortisRound en fait partie mais a DEJA son entree au registre (`loki_custom.MortisRoundPlaybook`,
# pour son `CalculateCustomUtility`) : elle delegue au meme corps plutot que d'etre reinscrite ici.
SPIRIT_LEECH_BODY_IDS: tuple[int, ...] = (
    int(ActiveAbilityType.HarbingerOfDestruction),      # 1008 = 0x3f0
    int(ActiveAbilityType.BringerOfDespair),            # 1022 = 0x3fe
    int(ActiveAbilityType.SkyStrike),                   # 1025 = 0x401
    int(ActiveAbilityType.PsychicMaelstrom),            # 1027 = 0x403
    int(ActiveAbilityType.IncendiaryShells),            # 1044 = 0x414
    int(ActiveAbilityType.FragstormGrenadeLauncher),    # 1048 = 0x418
    int(ActiveAbilityType.SanctorumMissile),            # 1062 = 0x426
    int(ActiveAbilityType.Fragstorm),                   # 1078 = 0x436
    int(ActiveAbilityType.HellfireShells),              # 1080 = 0x438
    int(ActiveAbilityType.GreatFrostAxe),               # 1089 = 0x441
    # 1104 SpiritLeech (0x450) est SORTIE de cette liste : elle a en plus son propre
    # `SpiritLeechPlaybook$$MakeHealPredictions` (le terme lifesteal), et son entree au registre est
    # donc `spirit_leech.SpiritLeechLifestealPlaybook`, qui DERIVE de cette classe-ci. Les treize
    # autres identites gardent la base VIDE sur ce slot -- le symbole `$$MakeHealPredictions` n'a
    # qu'UN proprietaire de vtable dans le build.
    int(ActiveAbilityType.CrushingClaws),               # 1105 = 0x451
    int(ActiveAbilityType.DakkaDakkaDakka),             # 1171 = 0x493
)

# NON PORTE, et c'est une MESURE : `IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$ShouldExecute`
# (1017 FragBomb, 1026 BasiliskBarrage). Son corps est celui de `SpiritLeechPlaybook` PRECEDE d'un
# `target = UnitExtensions.GetUnit(target, this.<+0x20 = state>)` -- l'aiguillage PAR TYPE (une
# unite est rendue telle quelle, une TUILE rend son occupant, un PIED remonte a l'unite, sinon
# `null`), surcharge tranchee par ses XREFS ENTRANTES, les trois ayant la meme signature.
# Ce `GetUnit` n'est pas decoratif : le RPC `abilityTargets` rend pour ces deux abilities des cibles
# `kind: "tile"`, et le natif propose bien `ActiveAbilityMessage(1026, <entite tuile>)`. Le
# generateur Comparable du port, lui, enumere des UNITES -- domaine de ciblage different. La seule
# confrontation disponible (`astraOrdnance` bombardant deux cibles a 1 PV depuis son spawn) donne
# natif = PROPOSE / port gate-e = REFUSE : porter le gate sur ces deux-la retire une action que le
# natif choisit. Residu `#419-r1-tr14-r5-r2-r1-r1-r1-r1`.


def _register_all() -> None:
    for aid in SPIRIT_LEECH_BODY_IDS:
        register(SpiritLeechPlaybook(aid))
    register(MultiThreatEliminatorPlaybook())


_register_all()
