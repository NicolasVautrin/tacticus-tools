"""HeavyRailRiflePlaybook -- utilite de DEGAT du TRIGGERED, branche MACHINE a tirage (#985).

Ferme `#970-r2`, dont la premisse -- << la config du triggered `1260` n'est pas lisible offline >>
-- est REFUTEE par `probe_985_config_du_triggered.py` : le triggered n'a pas de config PROPRE, il
partage l'`AbilityConfiguration` de l'active `1160`.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _unit_cfg

#: Nom gameconfig de l'ability ACTIVE. C'est AUSSI la config que lit le triggered `1260` (mesure
#: `probe_985_config_du_triggered.py` : les deux constantes qu'il lit ne coexistent que la).
_ABILITY_NAME = "HeavyRailRifle"

#: Le symbole du CALL-SITE natif, clef de `TRIGGERED_PREDICTION_AVERAGE_FORM`. La ligne y existait
#: DEJA (posee par #350-r3b) et n'avait aucun consommateur : c'est ce module qui la consomme.
_CALL_SITE = "IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$EvaluateNonComparable"

#: `BaseTriggeredAbility$$GetDamageProfileOrDefault(this, 0x12)` -- le defaut LU au site.
#: `IdunBattle.Entities.Enum.DamageProfileType` : `18 = Blast`.
_DEFAULT_PROFILE_BLAST = 18

#: `HeavyRailRifle_AttackAbility$$GetAttackHits` = `DSLFormulas$$ConfigConst(0x2f)`, lu au slot 1
#: (`Calculate`). `AbilityConstantType` : `0x2f = nrOfHits`.
_CONST_NR_OF_HITS = "nrOfHits"

#: `AbilityConstantType.damageProfile` -- present dans la config de `HeavyRailRifle`, donc le
#: defaut `Blast` ci-dessus ne mord pas ici. Porte quand meme : c'est le corps natif.
_CONST_DAMAGE_PROFILE = "damageProfile"


#: Le champ qui separe Machines of War et unites dans le gameconfig (cf. `_is_machine`).
_CONST_MYTHIC = "mythicAbilities"


def _is_machine(visual_id) -> bool | None:
    """`IdunBattle.Entities.EntityExtensions$$IsMachine(entity)` = `GetEntityType(entity) == 6`
    (`IdunBattle.Entities.Enum.EntityType` : `6 = Machine`).

    ⚠ Le type d'entite n'a AUCUN canal cote DECISION (`engine/services/ability_range.py` le dit
    deja pour `is_machine`), et une Machine n'est JAMAIS dans `decisionView.units` -- elle vit dans
    `decisionView.mows`, un canal que `NCContext` ne porte pas. On DERIVE donc le predicat du
    gameconfig, par le seul champ qui separe les deux populations : `mythicAbilities`.

    MESURE (`probe_985_six_faces.py --machines`) : sur la section `lineup`, `mythicAbilities`
    designe **11** unites, et 11 est exactement le compte de Machines of War du build -- les 8 du
    pool spawnable plus `darkaStormSpeeder`, `necroReanimator`, `thousDaemonPrince`. Zero faux
    negatif sur les 8 confrontables.

    Tri-etat DELIBERE : `None` = visualId inconnu (donc NON MESURE). L'appelant ne doit pas le
    rabattre sur `False`, qui prendrait la branche degat sur une cible peut-etre Machine."""
    if not visual_id:
        return None
    cfg = _unit_cfg(visual_id)
    if not cfg:
        return None
    return _CONST_MYTHIC in cfg


class HeavyRailRiflePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$EvaluateNonComparable` (id 0x488 = 1160, `tauBroadside`, MoW).

    Base LUE dans `data/symbols/<build>/frida/classes.tsv` :
    `IdunBattle.AI.Playbook.NonComparablePlaybook`1` (le `.ctor` est etiquete
    `ComparablePlaybook<...>$$.ctor` -- mislabel systematique, 2/2 sur ce lot).
    `IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$.cctor` : `MIN_UTILITY = Fix64(1)`.
    `PRIORITY = 0` -- 1160 est hors `NATIVE_PRIORITY`.

    ## Le corps, verbatim

        ab = Playbook<T>$$GetAbility<T>(this, 0x4ec)          # le TRIGGERED 1260
        profile  = BaseTriggeredAbility$$GetDamageProfileOrDefault(ab, 0x12 = Blast)
        hitsNode = HeavyRailRifle_AttackAbility$$GetAttackHits(ab)
        hits     = hitsNode.<IAmountFormula slot 1 = Calculate>(...)
        dmgNode  = HeavyRailRifle_AttackAbility$$GetDamage(ab, abilityState)
        dmg      = dmgNode.<IAmountFormula slot 4 = CalculateAverage>(...)  # TRONCATURE
        foreach target in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition):
            utility = Fix64(1)
            if !EntityExtensions.IsMachine(target):
                utility = Playbook<T>$$CalculateUtilityFromDamageEvent(target, dmg, profile, hits)
            elif HeavyRailRiflePlaybook$$ShouldPreferMachine(this):
                utility = Fix64(0x7fffffff)
            bucket.AddAction(GenerateAction(casterPosition, target, utility))

    ⚠ LES DEUX APPELS DE FORMULE ONT LEUR RECEVEUR DEVANT, ET LEURS ARGUMENTS ELIDES (#1031).
    Ils s'ecrivaient `<IAmountFormula slot 1 = Calculate>(hitsNode)`  [slot-attribution:refute]
    -- le NOEUD dans la parenthese. Or `hitsNode` est le RECEVEUR : la signature est
    `Calculate(entities: AbilityEntities, result: OperationResult)`, **deux** parametres, lus
    dans `data/symbols/<build>/frida/methods.tsv`. La convention du depot (mesuree : 43/43 avec
    receveur colle, 59/61 sans) est << la parenthese porte les ARGUMENTS >>, donc la citation
    d'origine annoncait une arite de 1 pour une methode qui en prend 2. Le slot et le nom,
    eux, etaient JUSTES. Les arguments restent ELIDES parce que ce corps-la n'a pas ete relu :
    `(...)` DIT qu'on ne les enumere pas, plutot que de les deviner depuis la signature.

    Les deux corps `GetAttackHits` / `GetDamage` sont etiquetes par Ghidra
    `VisionsOfHeresy_AttackAbility$$GetAttackHits` et `MassiveScythingTalonsAbility$$GetDamage` :
    corps DEDUPLIQUES, le nom ne dit pas l'ability. Ce qui est lu ici, ce sont les ARGUMENTS et
    les SLOTS, pas les noms.

    ## Ce que #970-r2 tenait pour un blocage, et qui n'en est pas un

    La fiche concluait `BLOCAGE: seeding` sur : << `HeavyRailRifle_Attack` est ABSENTE du
    gameconfig (572 abilities, seul `HeavyRailRifle` y figure), donc ni `minDmg`/`maxDmg` ni
    `nrOfHits` du TRIGGERED ne sont lisibles -- or c'est cette config-la que le playbook evalue. >>

    La premisse confond << pas d'entree a SON nom >> et << config introuvable >>. Mesure
    (`probe_985_config_du_triggered.py`, 4 etages) :

      * `HeavyRailRifle_Attack` est bien ABSENTE des DEUX substrats (gameconfig ET seed BC -- ce
        dernier n'a meme aucune section `TriggeredAbilities`) ;
      * mais `HeavyRailRifle_AttackAbility$$GetFinalUnitDamageAmount` lit `ConfigConst(0x4c)` et
        `ConfigConst(0xf)` sur son `this@+0x20`, soit `dmgPctReduction` et `extraDmgPct` ;
      * ces deux constantes coexistent dans **UNE SEULE** des 572 abilities : `HeavyRailRifle`
        (prises separement : 6 et 8 porteuses, soit 1,0 % et 1,4 %). L'appariement est donc
        UNIQUE, pas une concordance vague.

    ⇒ le triggered partage l'`AbilityConfiguration` de son active parente, et `minDmg` / `maxDmg` /
    `nrOfHits` / `damageProfile` sont LISIBLES. Le `BLOCAGE: seeding` tombe.

    ## L'ECART, nomme et borne

    `ShouldPreferMachine` = `pseudoRNG.<slot 5 = NextBool>(50)` : un tirage a 50 %. Il ne gouverne
    QUE la branche `IsMachine(target)`, ou l'utilite vaut alors `int.MaxValue` (tirage vrai) ou
    `1` (tirage faux). Le port prend `1` -- la branche DETERMINISTE des deux -- et le dit.

    Consequence PRATIQUE, qui rend le port confrontable : sur un montage dont aucune cible n'est
    une Machine of War, la branche n'est jamais prise et le port est integralement deterministe.
    C'est le regime a confronter ; un montage MoW-contre-MoW ne l'est pas, et il faut le dire
    plutot que de faire passer un tirage pour une mesure."""
    ABILITY_ID = int(ActiveAbilityType.HeavyRailRifle)  # 0x488 = 1160
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$.cctor = Fix64(1)
    PRIORITY = 0          # hors NATIVE_PRIORITY -> AbilityPriority.Normal

    #: `Fix64.op_Implicit(0x7fffffff)` -- la valeur LUE au site de la branche machine preferee.
    MACHINE_PREFERRED_UTILITY = float(0x7fffffff)

    def _entrees(self, ctx: NCContext):
        """`(dmg, hits, profile)` -- les TROIS entrees que le natif calcule UNE FOIS, avant la
        boucle sur les cibles. `None` si l'une manque : le natif sortirait par `FUN_1801f51f0`
        (`lVar11 == 0`), le port rend `None` plutot que de fabriquer un zero."""
        import gameconfig as GC
        from engine.entities.abilities.ability_configuration import AbilityConfiguration
        from engine.entities.abilities.triggered_ability import triggered_prediction_damage

        cfg = AbilityConfiguration.from_gameconfig(_ABILITY_NAME, GC.ability(_ABILITY_NAME))
        if cfg is None:
            return None
        st = ctx.scene.ability_state(ctx.uid, self.ABILITY_ID) if ctx.scene else None
        lvl = (st or {}).get("level")
        mult = (st or {}).get("multiplier", 100)
        dmg = triggered_prediction_damage(_ABILITY_NAME, lvl, mult, _CALL_SITE)
        if dmg is None:
            return None
        hits = cfg.get_variable_for_level(_CONST_NR_OF_HITS, lvl or 1, fallback_to_default=0)
        if hits < 1:
            return None
        profile = cfg.constants.get(_CONST_DAMAGE_PROFILE)
        profile = _DEFAULT_PROFILE_BLAST if profile is None else int(profile)
        return int(dmg), int(hits), profile

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None or ctx.scene is None:
            return []
        entrees = self._entrees(ctx)
        if entrees is None:
            return []
        dmg, hits, profile = entrees
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        tgt_ids = []                      # ordre PRESERVE = enumeration GetEligibleTargetsSelectable
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") is not None:
                        tgt_ids.append(t["targetId"])
        tgt_ids = list(dict.fromkeys(tgt_ids))
        if not tgt_ids:
            return []

        from engine.playbook.prediction.abilities import generate_multi_hit_attack_prediction
        from engine.playbook.probable_damage_event import (ProbableDamageEvent,
                                                           calculate_utility_from_damage_event)
        by_id = {u.get("id"): u for u in (ctx.units or [])}
        best, best_u = None, None
        for tid in tgt_ids:
            mach = _is_machine((by_id.get(tid) or {}).get("visualId"))
            if mach:
                # `ShouldPreferMachine` = tirage a 50 % : le port prend la branche DETERMINISTE.
                u = 1.0
            else:
                dp = generate_multi_hit_attack_prediction(
                    ctx.scene, ctx.uid, tid, self.ABILITY_ID, _ABILITY_NAME,
                    base_override=dmg, hits_override=hits, profile_override=profile)
                if dp is None:
                    continue
                ev = ProbableDamageEvent(target=tid, prediction=dp)
                u = calculate_utility_from_damage_event(ev, ctx.wt, ctx.scene.hpmax(tid))
            if u < self.MIN_UTILITY:          # gate `Bucket.AddAction` (util >= MIN_UTILITY)
                continue
            if best_u is None or u > best_u:  # AddAction : remplace sur STRICTEMENT superieur
                best, best_u = tid, u
        if best is None:
            return []
        if ctx.debug:
            import sys
            print(f"    [dbg HeavyRailRifle u{ctx.uid}] tgt={best} u={best_u:.1f} "
                  f"(dmg={dmg} hits={hits} profile={profile})", file=sys.stderr)
        return [{"target": best, "ability": self.ABILITY_ID, "to": None, "pred": float(best_u)}]
