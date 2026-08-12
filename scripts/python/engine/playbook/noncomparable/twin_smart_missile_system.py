"""TwinSmartMissileSystemPlaybook -- face DECISION de `1161` (`tauBroadside`, MACHINE OF WAR)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


def eligible_unit_targets(ctx: NCContext, ability_id: int) -> list:
    """`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsEntities(caster, casterPosition)`
    pour un domaine UNITE -> la liste des `targetId` DANS L'ORDRE DU NATIF.

    Pendant de `eligible_target_tiles` (`_base`), qui ne rend que le domaine TUILE. Meme source
    (`abilityTargets`) et meme regle : `fromHere` porte l'ordre EXACT du selecteur a la position
    d'origine, et c'est cet ordre qui tranche les egalites (`Bucket$$AddAction` ne remplace que si
    STRICTEMENT superieur -> keep-first).

    Pour une MACHINE OF WAR il n'existe qu'UNE evaluation, avec `UnitPosition$$NullPosition()`
    (`DefaultMachineTactic.<CalculateNextActionForUnit>d__5$$MoveNext` passe un `OrderedSet` de
    tuiles VIDE, ce qui fait tomber `ActiveAbilityActionGenerator.<GenerateActions>d__7` dans sa
    branche `Count == 0`) : `fromHere` est donc la SEULE vue pertinente, et l'union sur les tuiles
    de move n'a aucun sens pour un caster hors-plateau."""
    if ctx.ability_targets is None:
        return []
    at = ctx.ability_targets(ctx.uid, ability_id) or {}
    out: list = []
    for u in (at.get("units") or []):
        if u.get("unitId") != ctx.uid:
            continue
        for a in (u.get("abilities") or []):
            if a.get("abilityId") != ability_id:
                continue
            for t in (a.get("fromHere") or []):
                tid = t.get("targetId")
                if tid is not None and t.get("kind") != "tile":
                    out.append(tid)
    return out


class TwinSmartMissileSystemPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.TwinSmartMissileSystemPlaybook$$EvaluateNonComparable`
    (id `0x489` = 1161, `tauBroadside` -- Broadside, T'au, MACHINE OF WAR).

    Base `IdunBattle.AI.Playbook.NonComparablePlaybook`1` -- LUE dans
    `data/symbols/<build>/frida/classes.tsv`, surtout PAS le nom du corps de ctor, que ghidra
    etiquette `ComparablePlaybook<T>$$.ctor` (corps gshared DEDUPLIQUE, piege de #487-r1 / #945 /
    #957). `...$$.ctor` relaie `Playbook<T>$$.ctor(this, 0x489)`.

    CORPS NATIF, lu VERBATIM :

        bucket = new Bucket(<MethodInfo>)                          # <-- DEUX arguments
        targets = BasePlaybook$$GetEligibleTargetsEntities(caster, casterPosition)
        if (targets == null) throw
        if (targets.Count != 0) {
            target = pseudoRNG.<slot itf 6 = NextElement>(targets)
            if (target != null) {
                utility = Fix64.op_Implicit(1)
                bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, target, utility))
            }
        }
        return bucket

    QUATRE lectures ANCREES :

    1. **LE BUCKET N'A PAS DE BORNE, et c'est le seul des six du lot dans ce cas.** Les cinq
       autres construisent `Bucket(0, Nullable<Fix64>(<statique du .cctor>), <MI>)` -- quatre
       arguments, la borne etant le `Fix64(1)` ecrit par leur `.cctor`. Ici l'appel est
       `Bucket$$.ctor(bucket, <MI>)`, la surcharge SANS borne : le gate `util >= min` de
       `IdunBattle.AI.BucketSystem.Bucket<...>$$AddAction` n'est pas arme pour ce playbook.
       Le `.cctor` ecrit BIEN `Fix64(1)` dans son statique -- mais `EvaluateNonComparable` ne le
       LIT pas : le `DAT_` de ce statique est absent de la liste des symboles que le prologue de
       la methode initialise, alors que celui d'`HeavyRailRiflePlaybook` y figure ET est
       dereference deux instructions plus loin. On transcrit donc `MIN_UTILITY = 0`.
       Sans effet OBSERVABLE ici (l'utilite vaut 1, donc `1 >= 1` passait aussi), mais recopier
       le `1` ferait ecrire une borne que le natif n'arme pas.

    2. **LA CIBLE EST TIREE AU SORT** -- `IPseudoRNG` slot **6** = `NextElement` (arite 1,
       `data/symbols/<build>/metadata/interface_slots.tsv`). Le call-site passe par la resolution
       d'interface GENERIQUE (le playbook lit le slot dans le `MethodInfo*` inflate, d'ou la
       boucle sur la table d'interfaces du decompile) : signature d'un `NextElement<T>(IList<T>)`,
       la seule methode d'`IPseudoRNG` qui prenne une liste. Le champ `this+0x30` porte
       l'`IPseudoRNG` -- etabli par RECOUPEMENT, pas suppose : c'est le MEME champ et le MEME
       `Il2CppClass*` (`DAT_1833734e0`) que `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate`
       (`random.<slot 4 = NextBool>(prob)`) et que
       `IdunBattle.AI.Playbook.Loki.HeavyRailRiflePlaybook$$ShouldPreferMachine`
       (`random.<slot 5 = NextBool>(50)`).

       ECART ASSUME ET NOMME : le moteur porte est DETERMINISTE et ne rejoue pas le PRNG natif.
       `generate_candidates` retient donc la PREMIERE cible du selecteur. Ce que le port rend
       EXACT : qu'une action 1161 soit proposee, avec l'utilite 1, des qu'au moins une cible est
       eligible -- et c'est ce qui change le comportement, l'ability n'etant proposee par AUCUN
       chemin avant ce port. Ce qu'il ne rend pas : LAQUELLE des cibles. Meme famille d'ecart que
       les `GetUseProbability` fractionnaires deja assumes (BlackRage 0.4, ItItches -- cf.
       `NonComparablePlaybook.should_evaluate`), a ceci pres qu'ici l'alea porte sur la CIBLE.

    3. **AUCUNE PREDICTION DE DEGAT n'est construite** -- ni `Make*Predictions`, ni
       `CalculateUtilityFromDamageEvent`, ni `IAmountFormula`. L'utilite est le litteral
       `Fix64(1)`, alors meme que 1161 est une ability de DEGAT (`damageProfile: Blast`,
       `nrOfHits: 3`). Corroborable independamment : le natif ne doit annoncer AUCUN degat predit
       pour 1161 par la voie playbook.

    4. **LE SELECTEUR EST `GetEligibleTargetsEntities`, PAS `GetEligibleTargetsSelectable`** --
       les cinq autres du lot appellent la seconde. Le domaine est donc l'UNITE (la cible emise
       est un `targetId` d'unite), pas la tuile.

    PORTEUR : `tauBroadside`, `traits = ['MachineOfWar']`. La face DECISION d'une MoW est
    EXERCEE : `IdunBattle.AI.Tactics.DefaultMachineTactic$$.ctor` pose `@tactic+0x60 =
    GetDefaultActiveAbilityActionGenerators(this)`, c'est-a-dire la MEME liste de generateurs
    NonComparable par tier que le tactic unite (mirror `engine.ai.tactic.DefaultMachineTactic`).
    Corollaires structurels, tous mirrores ici : `ctx.origin is None`, `ctx.reach_nc == []`, et
    `to = None` -- une MoW ne bouge JAMAIS (`<CalculateMovementForUnit>d__8$$MoveNext` rend
    toujours une liste vide, il n'y a pas de `MovementActionGenerator`). Le sweep de positions de
    `_PlanTargetPlaybook` serait donc VIDE : ce playbook ne peut PAS en heriter, il derive de
    `NonComparablePlaybook` et lit `fromHere` directement, comme
    `ThriceBlessedConflagrationPlaybook` (1187, `adeptExorcist`, l'autre MoW portee).

    `PRIORITY` = 0 : 1161 est ABSENTE du sweep exhaustif des 258 valeurs d'`ActiveAbilityType`
    (#170), donc `get_Priority` n'est pas surchargee -> `AbilityPriority.Normal`."""

    ABILITY_ID = int(ActiveAbilityType.TwinSmartMissileSystem)   # 1161 = 0x489
    #: Le natif construit son `Bucket` SANS borne (surcharge a deux arguments) -- cf. lecture 1.
    MIN_UTILITY = 0.0
    PRIORITY = 0                                                 # absent de `NATIVE_PRIORITY`

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        targets = eligible_unit_targets(ctx, self.ABILITY_ID)
        if not targets:
            return []                       # branche native `targets.Count == 0` : bucket VIDE
        # `NextElement` -> PREMIERE cible (ecart d'alea nomme, lecture 2). L'utilite etant le
        # litteral `Fix64(1)`, aucun argmax n'a lieu : toutes les cibles sont a egalite cote
        # natif, et le tirage est ce qui les departage.
        target = targets[0]
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] TwinSmartMissileSystem target={target} "
                  f"(1er de {len(targets)}, natif = NextElement) u=1.0", file=sys.stderr)
        return [{"target": target, "ability": self.ABILITY_ID, "to": None, "pred": 1.0}]
