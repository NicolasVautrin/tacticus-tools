"""KillMaimBurnPlaybook -- frappe NonComparable (utilite = degat de l'ability, gate WillNormalAttackKill)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook, _will_normal_attack_kill
# FORME B, differes CLASSES GRATUITS depuis le degraissage du baril `engine.playbook`
# (#485-r1-r4). `generate_multi_hit_attack_prediction` et `make_normal_attack_predictions` sont
# tous deux SUBSTITUES par des patcheurs : une liaison `from X import f` les GELERAIT.
from engine.playbook.prediction import abilities as _pred_ab
from engine.playbook.prediction import normal_attack as _pred_na
from engine.playbook import probable_damage_event as _pde

_ABILITY_NAME = "KillMaimBurn"


class KillMaimBurnPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.KillMaimBurnPlaybook$$EvaluateNonComparable` (id 0x46c=1132, worldKharn).

    NonComparable (parent `NonComparablePlaybook`1` lu dans `data/symbols/<build>/frida/classes.tsv` --
    surtout PAS le nom du corps de ctor, que ghidra etiquette `ComparablePlaybook<T>$$.ctor` : les
    deux ctors gshared partagent un corps qui ne fait que relayer `Playbook<T>$$.ctor(0x46c)`).

    CORPS NATIF, lu VERBATIM (les trois getters d'entree sont des corps PARTAGES que ghidra nomme
    d'apres UN de leurs proprietaires -- lire le CORPS, jamais le nom) :

        bucket = new Bucket(0, Nullable(MIN_UTILITY))                    # .cctor = Fix64(1)
        profile = ability.GetDamageProfile()                             # `TacticalPrecisionAbility$$Get
        #   ChargingAttackDamageProfile` -> `IdunBattle.Entities.Abilities.AActiveAbility$$GetDamageProfile`
        #   = `AbilityConfiguration$$GetDamageProfile` = la constante `damageProfile` (= Piercing)
        foreach entities in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition.MainTile):
            if BasePlaybook$$WillNormalAttackKill(entities): continue    # <-- LE gate propre a 1132
            dmgNode  = ability.GetDamage(abilityState, isPrediction: TRUE)
            #   `StaffOfStarsAbility$$GetDamage` -> `AActiveAbility$$MinMaxDamage(state, TRUE)`
            #   = `DSLFormulas.Half(Sum(Direct(var 0xc = minDmg), Direct(var 0xd = maxDmg)), 0)`
            damage   = IAmountFormula slot 4 `AAmountFormula$$CalculateAverage`(dmgNode, entities)
            hitsNode = ability.GetHitsFormula()
            #   `TwinSmartMissileSystemAbility$$GetHitsFormula` = `DSLFormulas.ConfigConst(0x2f)`
            #   (0x2f = la meme cle que `AActiveAbility$$GetHits` = `nrOfHits`)
            hits     = IAmountFormula slot 4 (hitsNode, entities)
            util     = Playbook<T>$$CalculateUtilityFromDamageEvent(caster, target, casterPosition,
                                                                    damage, profile, hits)
            bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, target, util))

    UNE SEULE ENTREE DE DEGAT, PAS TROIS. Le kit de `KillMaimBurn` porte trois profils
    (`nrOfHits:1 Piercing`, `nrOfHits_2:6 Eviscerate`, `nrOfHits_3:1 Plasma`) mais le PLAYBOOK n'en
    lit qu'UN : `GetDamageProfile`/`GetHitsFormula` resolvent les cles NON suffixees (`damageProfile`,
    `nrOfHits` = cle 0x2f) et `MinMaxDamage` les variables 0xc/0xd (`minDmg`/`maxDmg`). Les suffixes
    `_2`/`_3` appartiennent a la face COMBAT (`KillMaimBurnAbility$$ExecuteBehaviour`), pas a la face
    DECISION. Le chemin GENERIQUE `generate_multi_hit_attack_prediction` est donc EXACTEMENT le sien.

    `AAmountFormula$$CalculateAverage` (slot 4) teste d'abord le predicat de vtable `+0x1c8` et, s'il
    est vrai, retombe sur `Calculate` (`+0x1d8`) ; sinon seulement il fait `(max + min) / 2` en
    division ENTIERE. Le noeud est ici un `Half(Sum(...))` DETERMINISTE -> branche `Calculate` ->
    `DivideAmount$$Calculate` -> `AAmountFormula$$RoundFix64Result(., 0)` = `Fix64.Round` DEMI-VERS-
    LE-PAIR. C'est la famille (a) du registre `_PREDICTION_MINMAX_AVERAGE`, ou `1132` figure deja --
    donc `ab.get_damage()` prend d'office la bonne moyenne, sans rien a poser ici.

    - `MIN_UTILITY` = `KillMaimBurnPlaybook$$.cctor` = `Fix64.op_Implicit(1)` = 1.
    - `PRIORITY` = 0 (defaut `AbilityPriority.Normal` ; 1132 hors `NATIVE_PRIORITY`, sweep #170).
    - Enumeration (cible, tuile de cast) = plan natif rank (`_PlanTargetPlaybook`) : 1132 a une
      config de degat, donc ses paires sont dans `attackPlans`.

    LE GATE `WillNormalAttackKill` EST LE POINT QUI SE MESURE (et celui qui a fait lire de travers la
    divergence de `#356-r1`). `BasePlaybook$$WillNormalAttackKill(entities)` relaie vers la surcharge
    `(caster = entities+0x08, target = entities+0x10, casterTile = entities+0x40)`, qui invoque
    `IBattleQuery` slot 0x21 (`PredictAttack`, attaque NORMALE depuis `casterTile`), **CONSTRUIT un
    `ProbableDamageEvent`** et rend `DamagePredictionResult$$get_WillBeKill`. Deux consequences :

      1. le natif SAUTE toute cible que l'attaque normale tue deja a coup sur -- il ne gaspille pas
         KillMaimBurn dessus (meme gate que `StormcallerPlaybook`) ;
      2. l'oracle `ncPlaybookPredict`, ancre sur `ProbableDamageEvent$$.ctor`, capture AUSSI cet
         event d'attaque NORMALE -- meme `targetId` que l'event d'ability. Sur `worldKharn` (arme
         normale : 4 coups Eviscerate) contre `necroWarden` a pleine vie, la normale sur-tue : la
         capture ne contient QUE `(PV, PV, 4)` -- bornes CAPEES a la sante restante par
         `AccurateHealthDamage` (`DamagePrediction$$PredictAttackRaw` : `health = min(health,
         rem_HP)` par coup) -- et le bucket est VIDE, parce que toutes les cibles ont ete sautees.
         Le `(8536, 8536, 4)` de `#356-r1` etait donc l'attaque NORMALE de Kharn, pas 1132 : le
         `4` est `worldKharn.weapons[0].hits`, pas `nrOfHits` (= 1).
    """
    ABILITY_ID = int(ActiveAbilityType.KillMaimBurn)  # 1132
    MIN_UTILITY = 1.0     # IdunBattle.AI.Playbook.Loki.KillMaimBurnPlaybook$$.cctor = Fix64(1)
    PRIORITY = 0
    # `should_evaluate` = l'implementation de BASE (`IdunBattle.AI.Playbook.BasePlaybook$$Should
    # Evaluate` -> `GetUseProbability` = `Fix64(1)` -> True constant). MESURE, pas supposee : RPC
    # `pbGate` slot 4 de `IPlaybook` sur `worldKharn` au PREMIER tour (`turnsStarted == 1`) rend
    # **1**, quand `1202 VigilanceEternal` -- qui porte, lui, le corps folde
    # `AlphaWarriorPlaybook$$ShouldEvaluate` (`GetStat(unit, 0xc) > 1`) -- rend **0** au meme
    # instant. 1132 n'a donc AUCUN gate de tour ; ne pas heriter `_turns_started_gate`.

    def _ability_prediction(self, tile, target, ctx: NCContext):
        """`GetDamage(state, isPrediction: TRUE)` + `GetDamageProfile` + `GetHitsFormula` -> le
        `DamagePredictionResult` que `CalculateUtilityFromDamageEvent` score. Foyer UNIQUE, partage
        par `damage_predictions` (trace de construction) et `evaluate_non_comparable` (utilite)."""
        return _pred_ab.generate_multi_hit_attack_prediction(
            ctx.scene, ctx.uid, target, self.ABILITY_ID, _ABILITY_NAME, attack_pos=tile)

    def damage_predictions(self, tile, target, ctx: NCContext) -> list:
        """DEUX events par cible, ou UN SEUL quand le gate mord -- l'ordre est celui du corps natif.

        `BasePlaybook$$WillNormalAttackKill` est la PREMIERE instruction du corps de boucle et il
        construit son propre `ProbableDamageEvent` (prediction de l'attaque NORMALE depuis
        `entities+0x40` = la tuile du caster). S'il rend vrai, le `continue` natif tombe et AUCUNE
        prediction d'ability n'est construite pour cette cible.

        MESURE (`probe_362_kill_maim_burn_nc.py`, `worldKharn` rank 17 vs `necroWarden`, anneau
        centre en (3,4), niveau 3) :
          * PV du seed (8536) -> capture `[(8536, 8536, 4)]`, bucket VIDE -- l'attaque normale de
            Kharn sur-tue, la cible est sautee ;
          * PV forces a 400000 -> capture `[(10052, 15072, 4), (86, 129, 1)]` -- le gate ne mord
            plus, l'ability est evaluee ensuite. Le port rend les MEMES deux tuples, dans le meme
            ordre."""
        if tile is None or ctx.scene is None or target is None:
            return []
        seq = []
        na = _pred_na.make_normal_attack_predictions(ctx.scene, ctx.uid, target, tile)
        if na is not None:
            seq.append(("WillNormalAttackKill", na.prediction))
            if na.prediction.will_be_kill():
                return seq                 # `continue` natif : pas d'event d'ability
        dp = self._ability_prediction(tile, target, ctx)
        if dp is not None:
            seq.append(("ability", dp))
        return seq

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        if tile is None or ctx.scene is None or target is None:
            return None
        if _will_normal_attack_kill(ctx, target, tile):
            return None      # `continue` natif : l'attaque normale sure-kill deja cette cible
        dp = self._ability_prediction(tile, target, ctx)
        if dp is None:
            return None
        ev = _pde.ProbableDamageEvent(target=target, prediction=dp)
        u = _pde.calculate_utility_from_damage_event(ev, ctx.wt, ctx.scene.hpmax(target))
        if ctx.debug:
            import sys
            print(f"    [dbg KillMaimBurn u{ctx.uid}] tgt={target} tile={tile} u={u:.1f}",
                  file=sys.stderr)
        return u
