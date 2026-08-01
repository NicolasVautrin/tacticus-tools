"""`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook` -- face ATTACK du triggered
`SaviorProtocols` (1120), 3e des 20 residus ATTACK de #419. Porteurs DISPATCHES : 6, tous hors
lineup -- 3 npc (`tauNpc2DroneSniper`, ...) et 3 SUMMONS (`tauSmnDroneCommandLink`,
`tauSmnDroneSniper`, `tauSmnDroneShield`).

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(34), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae et BarbedOvipositor
(`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.SaviorProtocolsPlaybook$$CalculateAttackUtilityInStepsInternal` monte la
SM `d__5` avec **TROIS** champs -- case @+0x20, `this` (le playbook) @+0x28, delegue scorer @+0x30 --
la ou `BarbedOvipositor$$CalculateAttackUtilityInStepsInternal` n'en ecrit que DEUX (case @+0x20,
delegue @+0x28) : son corps n'a pas besoin du playbook, celui-ci si (il y lit `state`). La disposition
se LIT dans la methode-usine, elle ne se transpose pas d'un voisin. Corps :
`SaviorProtocolsPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__5$$MoveNext` -- UN SEUL
`yield`, deux sorties :

    Fix64 u = Fix64.op_Implicit(0);
    if (EntityExtensions.HasEffect(case.Target, this.<state>, (EffectType)0x462, onlyActive: true))
        u = Fix64.op_Addition(u, Fix64.op_Implicit(GetUtilityValue("SAVIORPROTOCOLS_MarkedTarget")));
    yield return u;

Quatre lectures qui ne se devinent pas -- et aucune ne se generalise depuis un voisin de la liste :

1. **Le predicat porte sur la CIBLE et sur RIEN d'autre.** Ni stats, ni traits, ni faction, ni
   position du caster ; ni la tuile d'attaque (contrairement a `SuppressiveFire`, qui NIE
   `AreEntitiesAdjacent(casterTile, target)`) ; ni la prediction de degat du case (contrairement a
   `BarbedOvipositor`, qui lit `UtilityAttackCase@+0x28`). Le corps ne touche que `case@+0x20` (la
   cible) et le champ `state` du playbook. C'est ce qui rend l'ability GREFFABLE (`case-92` §5bis)
   sur une unite du pool : le code exerce est bien celui de 1120, et aucune propriete du greffon
   n'entre dans le resultat.

2. **`0x462` = 1122 = `EffectType.Markerlight`** (enum QUALIFIE : `IdunBattle.Entities.Enum.EffectType`,
   ni `TriggeredAbilityType` -- ou 1122 vaut `NoctilithBeacons` -- ni `ActiveAbilityType`). La cible
   est celle que les T'au ont MARQUEE ; le drone se jette d'autant plus volontiers sur elle.

3. **`onlyActive: true`, et c'est l'INVERSE de `SuppressiveFire`.** Le 4e argument du call-site est le
   litteral `1` (`SuppressiveFire` passe `0`, `ForwardObservers` passe `null`). Ce byte-la change ce
   que le natif regarde : `IdunBattle.Entities.EntityExtensions$$HasEffect` =
   `IsOwnerOfEffect(e, state, type, onlyActive) || IsTargetOfEffect(e, state, type)`, et dans
   `IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` le flag `EffectComponent.IsActive @+0x5c`
   n'est consulte QUE si `onlyActive != 0`. Le mirror est donc `EffectsState.active_effects`, PAS
   `has_effect` -- exactement le choix inverse de `suppressive_fire.py`, pour un call-site voisin.
   (La seconde branche, `IdunBattle.Entities.EntityExtensions$$IsTargetOfEffect`, exige `+0x5c`
   INCONDITIONNELLEMENT : elle est deja « active-only » dans les deux regimes.)

4. **La cle est un LITTERAL DE CHAINE du corps** (`FUN_1801f4fb0(&DAT_...)` au prologue), pas un
   champ statique : `SaviorProtocolsPlaybook` n'a **pas de `.cctor`** -- meme forme que
   `BarbedOvipositor`, l'inverse de `Lakrimae`. Les TROIS litteraux de la classe sont
   `SAVIORPROTOCOLS_MarkedTarget` (cette face) et `SAVIORPROTOCOLS_AdjacentTauFriend` /
   `SAVIORPROTOCOLS_AdjacentTauParent` (face MOVE). Poids au gameconfig **et** au seed BC servi (les
   deux concordent, pas de piege #271) : **60 / 20 / 30**. L'assignation du 60 a cette face n'est pas
   deduite du nom : elle est TRANCHEE par la mesure live (`probe_443`), ou les trois valeurs sont
   distinctes.

## La face MOVE : corps PROPRE et NON trivial -- RESIDU OUVERT, pas un constant

`SaviorProtocolsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__4$$MoveNext` est
decompile LU et il est bien vivant (pour chaque unite dans un rayon autour de `case.MovementTile` :
`SaviorProtocolsAbility$$TargetIsValidTrigger` -> `+AdjacentTauFriend`, puis
`UnitExtensions$$GetParent(case.unit, state) == unite` -> `+AdjacentTauParent`). Le playbook
surcharge EN PLUS `SaviorProtocolsPlaybook$$FilterMovementTiles` (slot 1 d'`IPlaybook`, non porte
globalement -- cf. `case-r1b`) et delegue au meme `TargetIsValidTrigger`. Ce n'est donc PAS le
`yield Fix64(0)` constant de `Lakrimae`/`BarbedOvipositor` : c'est un item a part entiere (residu
`#443-r1`, cf. `docs/rl/case-443-savior-protocols-playbook.md`), et son absence de
`TRIGGERED_MOVE_PLAYBOOKS` reste un TROU, pas le comportement natif.
"""
from __future__ import annotations

from ..entities.effect_type import EffectType
from ..entities.triggered_ability_type import TriggeredAbilityType

# `HasEffect(case.Target, state, (EffectType)0x462, onlyActive: true)` -- 0x462 = 1122 (cf. en-tete).
_MARKERLIGHT = int(EffectType.Markerlight)
# L'UNIQUE litteral de chaine de la face ATTACK, lu dans `Utilities.Default.TriggeredAbilities`.
_WEIGHT_KEY = "SAVIORPROTOCOLS_MarkedTarget"


def _target_has_active_markerlight(scene, target_uid: int) -> bool:
    """`EntityExtensions.HasEffect(target, state, 1122, onlyActive: TRUE)` =
    `IsOwnerOfEffect(target, state, 1122, onlyActive=1) || IsTargetOfEffect(target, state, 1122)`.

    `onlyActive = 1` ==> `IsOwnerOfEffect` consulte `EffectComponent.IsActive @+0x5c` : cote port
    c'est `EffectsState.active_effects` (flag `active` + `CreateActiveCondition`), surtout PAS
    `has_effect`, qui ne filtre que `consumed` et sert les call-sites `onlyActive = 0` (le voisin
    `suppressive_fire.py`). La seconde branche passe par le foyer unique `Scene.is_effect_target`,
    tri-etat : `None` = geometrie non portee pour ce type, on ne referme pas dessus (meme discipline
    que `playbook/psyker.py` et `playbook/suppressive_fire.py`)."""
    eff = getattr(scene, "eff_state", None)
    if eff is not None:
        st = scene.unit_state(int(target_uid)) if hasattr(scene, "unit_state") else None
        for e in eff.active_effects(int(target_uid), st):
            if e.effect_type == _MARKERLIGHT:
                return True
    return getattr(scene, "is_effect_target", lambda *_a: None)(
        int(target_uid), _MARKERLIGHT) is True


class SaviorProtocolsPlaybook:
    """`SaviorProtocolsPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1120). Face ATTACK portee
    ici ; face MOVE NON portee (corps natif propre et NON trivial -- residu `#443-r1`, cf. en-tete :
    c'est un trou, pas le comportement natif)."""

    ability_id: int = int(TriggeredAbilityType.SaviorProtocols)      # 1120 = 0x460

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__5$$MoveNext` (cf. en-tete) : la CIBLE
        porte-t-elle un `Markerlight` ACTIF ? oui -> le poids `SAVIORPROTOCOLS_MarkedTarget` ;
        non -> 0. AUCUN autre terme : ni tuile d'attaque, ni caster, ni prediction.

        `prediction` (= `case.DamagePrediction`, `UtilityAttackCase@+0x28`, canal ouvert par #438)
        est ACCEPTE et IGNORE -- comme le corps natif, qui ne lit pas ce champ du case."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        if not _target_has_active_markerlight(sc, int(case_tgt_id)):
            return 0.0
        return float(ctx.wt.triggered(_WEIGHT_KEY))            # `GetUtilityValue(<cle>)`
