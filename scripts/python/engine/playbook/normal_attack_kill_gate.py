"""Les playbooks Comparable dont `ShouldExecute` refuse le cast quand l'ATTAQUE NORMALE tuerait deja
la cible (`#419-r1-tr14-r5-r2-r1-r1-r1`).

Trois corps natifs, DIX-SEPT classes, une seule primitive : `BasePlaybook$$WillNormalAttackKill`
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


def normal_attack_reaches(ctx, target, caster_tile) -> bool:
    """L'ATTAQUE NORMALE du caster est-elle legale sur `target` DEPUIS `caster_tile` ?

    BORNE DE PORT, et elle est MESUREE, pas supposee. Le natif obtient `WillBeKill == false` quand
    la cible n'est pas atteignable a l'attaque normale depuis la tuile de cast -- constate live :
    `astraOrdnance` en `(1,0)` bombarde (`BasiliskBarrage`) deux `adeptRetributor` a **1 PV** en
    `(6,7)`/`(6,8)`, et le natif PROPOSE le cast. Le port, lui, rendait `killSure = True` avec
    `healthDmgMin = 1` -- le PLANCHER de degat -- parce que
    `engine.playbook.prediction.make_normal_attack_predictions` calcule une prediction HYPOTHETIQUE
    sans regarder la portee. Sans cette borne le gate mordait donc a tort, et refusait une action
    que le natif CHOISIT (le sens de divergence le plus grave : le port perd une action legale).

    Ce n'est PAS le mirror d'une clause native -- `IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill`
    n'en a pas -- mais du chemin par lequel le natif retombe sur `false` :
    `IdunBattle.Core.Services.BattleQuery$$GetNormalAttackPrediction` delegue a un slot de service
    qui n'a rien a rendre pour une paire hors portee. On le pose DANS le gate plutot que dans la
    primitive partagee : `noncomparable/_base.py::_will_normal_attack_kill` sert des playbooks
    valides live dont aucun n'exerce ce regime, et elargir leur comportement sortirait du perimetre.

    SUBSTRAT : `ctx.plans` (les `attackPlans` natifs) -- un eval d'attaque NORMALE du caster sur
    `target` dont les tuiles `ranked` contiennent `caster_tile`. Les tuiles rankees d'une paire
    (ability, cible) sont exactement les positions d'ou le cast est legal (meme lecture que
    `loki_custom.SorcerousFacadePlaybook._get_target`).

    TRI-ETAT : plans ABSENTS pour ce caster (bridge offline, qui ne peuple que l'unite ACTIVE) ->
    `True`, c.-a-d. la borne ne s'applique pas et le gate se comporte comme sans elle. Un `False`
    par defaut desarmerait le gate partout ou le substrat est muet."""
    plan = (getattr(ctx, "plans", None) or {}).get(ctx.uid)
    if not plan:
        return True
    nids = getattr(ctx, "normal_ids", None) or set()
    if not nids:
        return True
    seen_any = False
    for ev in (plan.get("evals") or ()):
        if ev.get("abilityId") not in nids:
            continue
        seen_any = True
        if ev.get("targetId") != target or not ev.get("rankCount"):
            continue
        if any((rk.get("col"), rk.get("row")) == caster_tile for rk in (ev.get("ranked") or ())):
            return True
    return not seen_any


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
        if not normal_attack_reaches(ctx, target, caster_tile):
            return True                      # borne de port : rien a predire -> pas de kill
        return not self.will_normal_attack_kill(ctx, target, caster_tile)


class FragBombPlaybook(SpiritLeechPlaybook):
    """`IdunBattle.AI.Playbook.Loki.FragBombPlaybook$$ShouldExecute`, lu verbatim :

        target = UnitExtensions.GetUnit(target, this.<+0x20 = state>);
        return !BasePlaybook.WillNormalAttackKill(caster, target, casterTile);

    UN SEUL delta avec le corps ci-dessus : la RESOLUTION de la cible. `this@+0x20` est le `state`
    (`IdunBattle.AI.Playbook.BasePlaybook$$Init`, lu). La surcharge appelee est celle qui prend
    `(entity, state)` et fait un aiguillage PAR TYPE -- tranchee par les xrefs entrantes, pas a
    l'oeil, les trois surcharges de `UnitExtensions$$GetUnit` ayant la meme signature :

        si l'entite EST deja une unite            -> la rendre telle quelle
        si c'est une TUILE (TileContentComponent) -> rendre l'unite qui l'occupe (recursif)
        si c'est un PIED d'unite                  -> remonter a l'unite
        sinon                                     -> null

    Cote port, `target` est TOUJOURS un identifiant d'UNITE (le generateur d'action Comparable
    enumere des unites, jamais des tuiles), donc cette resolution est l'IDENTITE et le corps se
    reduit au precedent. On garde la classe distincte quand meme : elle est le mirror d'un corps
    natif DIFFERENT, et elle documente le point ou un port qui enumererait des tuiles (route
    `nonattack.py` a domaine TUILE, ex. 1169/1148) devrait resoudre l'occupant. Herite de
    `SpiritLeechPlaybook` cote port alors qu'en natif les deux sont SOEURS -- meme arbitrage que
    `NormalBossAttackPlaybook` : on n'herite que ce qui est identique par mesure."""


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
        if not normal_attack_reaches(ctx, target, caster_tile):
            return True                      # borne de port (cf. `normal_attack_reaches`)
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
    int(ActiveAbilityType.SpiritLeech),                 # 1104 = 0x450
    int(ActiveAbilityType.CrushingClaws),               # 1105 = 0x451
    int(ActiveAbilityType.DakkaDakkaDakka),             # 1171 = 0x493
)

# `FragBombPlaybook$$ShouldExecute` : les 2 identites.
FRAG_BOMB_BODY_IDS: tuple[int, ...] = (
    int(ActiveAbilityType.FragBomb),                    # 1017 = 0x3f9
    int(ActiveAbilityType.BasiliskBarrage),             # 1026 = 0x402
)


def _register_all() -> None:
    for aid in SPIRIT_LEECH_BODY_IDS:
        register(SpiritLeechPlaybook(aid))
    for aid in FRAG_BOMB_BODY_IDS:
        register(FragBombPlaybook(aid))
    register(MultiThreatEliminatorPlaybook())


_register_all()
