"""EuphoricStrikesPlaybook (1198, `emperExultant` « Laviscus ») -- face DECISION.

Base `NonComparablePlaybook`1` -- **LUE dans `data/symbols/<build>/frida/classes.tsv`**, jamais
dans le nom du `.ctor` : ghidra etiquette celui-ci
`ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor` (corps DEDUPLIQUE par ICF), et
`AlphaWarriorPlaybook$$.ctor` -- NonComparable AVEREE et deja portee -- appelle EXACTEMENT le meme
corps. Le nom du ctor ne dit donc pas la base.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.EuphoricStrikesPlaybook$$EvaluateNonComparable` (0x4ae = 1198) :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics[0]>))       # `.cctor` : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
        if (BasePlaybook.WillNormalAttackKill(this, entities@+0x08, entities@+0x10,
                                              entities@+0x40))  continue;      # <- LE GATE
        utility = Fix64.op_Implicit( UnitExtensions.GetStat(entities@+0x10, 5, 0, 0) )
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10, utility))

et `IdunBattle.AI.Playbook.Loki.EuphoricStrikesPlaybook$$.cctor` = `Fix64.op_Implicit(1)`.

**`MIN_UTILITY = 1` et le seuil `Fix64(10)` de la famille Comparable NE S'APPLIQUE PAS ICI.** Le
statique est LU par `EvaluateNonComparable` lui-meme (xrefs sur le `Il2CppClass*` de la classe :
`.cctor` ECRIT, `EvaluateNonComparable` LIT deux fois) : c'est le `minUtility` du `Bucket`, pas le
seuil d'un `ShouldExecute`. `EuphoricStrikesPlaybook$$ShouldExecute` **n'existe pas** -- et ici
l'absence CONCLUT, contrairement au cas general : les corps de `ShouldExecute` de cette famille
lisent CHACUN le static de SA classe, donc ils sont deux a deux distincts, donc non dedupliquables
par ICF et tous nommes par ghidra (29 corps `<X>Playbook$$ShouldExecute` nommes dans ce build).

`StatType 5 = Health` -- LU dans `data/symbols/<build>/frida/enums.tsv`
(`IdunBattle.Entities.Enum.StatType`), pas deduit. Les deux derniers arguments de `GetStat` sont le
litteral `0` : c'est la valeur ABSOLUE (PV COURANTS), pas la part en pourcentage que prend
`BloodChalicePlaybook` avec `GetStat(Health, 1)`.

LE GATE EST *AVANT* L'UTILITE, ET CET ORDRE-LA EST OBSERVABLE
--------------------------------------------------------------
Le `continue` de `VexillaMagnificaPlaybook` est SOUS son calcul d'utilite (le natif calcule puis
jette) ; ici il est AU-DESSUS. Sur l'utilite c'est indiscernable (`GetStat` n'a pas d'effet de
bord), mais pas sur la TRACE : `BasePlaybook$$WillNormalAttackKill` **CONSTRUIT un
`ProbableDamageEvent`** (prediction de l'attaque NORMALE depuis `entities@+0x40`) avant de n'en
retenir que `DamagePredictionResult$$get_WillBeKill`. L'oracle `ncPlaybookPredict`, ancre sur
`ProbableDamageEvent$$.ctor`, le VOIT donc -- d'ou `damage_predictions` ci-dessous.

⚠ **ET LE PLAYBOOK NE CONSTRUIT AUCUNE PREDICTION D'ABILITY**, contrairement a
`KillMaimBurnPlaybook` qui porte le meme gate : son utilite est un `GetStat`, pas un
`CalculateUtilityFromDamageEvent`. La trace de 1198 contient donc AU PLUS UN event -- celui du
gate -- et jamais deux. Recopier la forme de `kill_maim_burn` en emettrait un second, inexistant.

LA SURCHARGE DE `GetEligibleTargetsSelectable` EST TRANCHEE PAR LES XREFS, PAS PAR LA FORME
-------------------------------------------------------------------------------------------
`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` a **TROIS** surcharges dans ce
build. 1198 appelle celle qui prend une `UnitPosition` (`possibleCasterPosition`) et delegue a
`BasePlaybook$$GetEligibleTargetsEntities` -- **la meme que `VexillaMagnificaPlaybook` et
`VigilanceEternalPlaybook`**, et PAS celle d'`AlphaWarriorPlaybook`/`DarkTalonStrikePlaybook` (qui
prend une TUILE et applique un `ListExtensions$$Remove`). Tranche par les xrefs ENTRANTES de
chacune des trois adresses, jamais par le pseudo-C, qui se ressemble.

Cote port, les deux surcharges se mirrorent par la MEME voie -- l'enumeration (cible, position) du
plan natif, `_PlanTargetPlaybook` -- parce que 1198 porte une config de degat (`minDmg`/`maxDmg`,
`damageProfile: Power`, `nrOfHits: 1`, `attackRangeType: Melee`), donc ses paires sont dans
`decisionView.attackPlans`. C'est le meme regime que `VexillaMagnifica` et `KillMaimBurn`.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook, _will_normal_attack_kill
# FORME B, differe CLASSE GRATUIT depuis le degraissage du baril `engine.playbook` (#485-r1-r4).
# `make_normal_attack_predictions` est SUBSTITUE par un patcheur : une liaison `from X import f`
# au niveau module rendrait le patch inerte.
from engine.playbook.prediction import normal_attack as _pred_na


class EuphoricStrikesPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.EuphoricStrikesPlaybook$$EvaluateNonComparable` -- utilite =
    PV COURANTS de la cible, avec VETO sur les cibles que l'attaque normale tue deja.

    Le natif ne gaspille donc pas la marque `+crit` de 1198 sur une unite qui va mourir de toute
    facon, et parmi les survivantes il vise la PLUS ROBUSTE (max PV courants) -- pas la plus
    faible. Ce sens-la est celui du decompile ; l'inverser serait un contresens muet."""

    ABILITY_ID = int(ActiveAbilityType.EuphoricStrikes)   # 0x4ae = 1198
    MIN_UTILITY = 1.0   # `EuphoricStrikesPlaybook$$.cctor` : `Fix64.op_Implicit(1)` -> statics[0]
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    # `should_evaluate` = l'implementation de BASE (`BasePlaybook$$ShouldEvaluate` ->
    # `GetUseProbability` = `Fix64(1)` -> True constant), et c'est MESURE, pas suppose.
    # Ce point ne PEUT pas se trancher offline : le gate de tour `GetStat(unit, 0xc =
    # TurnsStarted) > 1` est un corps COMDAT unique (`_base._turns_started_gate`, etiquete
    # `AlphaWarriorPlaybook$$ShouldEvaluate`, refcount 7), donc son absence sous le nom de CETTE
    # classe ne prouve RIEN -- le raisonnement par nommage qui conclut pour `ShouldExecute` (corps
    # deux a deux distincts) ne vaut PAS ici.
    # MESURE LIVE (`probe_974_decision_gates_live.py`, runner MC1_67/seed 777, porteur co-injecte) :
    # `pbGate(itf=Playbook, slot=4)` sur `emperExultant` rend **True** alors que
    # `turnsStarted == 1` -- regime ou un playbook PORTEUR du gate rendrait `False`. 1198 n'a donc
    # AUCUN gate de tour. Residu `#974-r1` FERME par cette mesure.

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`WillNormalAttackKill` -> `continue`, puis `Fix64(GetStat(cible, 5 = Health))`.

        ⚠ L'ORDRE des deux clauses est celui du natif, et il n'est pas cosmetique : voir la
        docstring de module (le gate construit un `ProbableDamageEvent` que l'oracle capte)."""
        if tile is None or target is None:
            return None
        if _will_normal_attack_kill(ctx, target, tile):
            return None                     # `continue` natif : la normale sure-kill deja la cible
        hp = ctx.hp_cur_by_id.get(target)   # `UnitExtensions.GetStat(entity, 5 = Health, 0, 0)`
        if not hp or hp <= 0:
            return None                     # PV non mesures, ou 0 -- sous `MIN_UTILITY` de toute
            #                                 facon (`AddAction` gate a `util >= 1`)
        return float(hp)

    def damage_predictions(self, tile, target, ctx: NCContext) -> list:
        """AU PLUS UN event, et il vient du GATE -- jamais de l'ability.

        `BasePlaybook$$WillNormalAttackKill` construit un `ProbableDamageEvent` pour l'attaque
        NORMALE depuis `tile` ; `EvaluateNonComparable` n'en construit aucun autre (son utilite est
        un `GetStat`). La sequence que l'oracle `ncPlaybookPredict` voit vaut donc `[gate]`, que le
        gate morde ou non -- le `continue` ne supprime pas l'event deja construit."""
        if tile is None or ctx.scene is None or target is None:
            return []
        na = _pred_na.make_normal_attack_predictions(ctx.scene, ctx.uid, target, tile)
        return [] if na is None else [("WillNormalAttackKill", na.prediction)]
