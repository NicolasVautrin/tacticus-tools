"""SpawnPoxwalkersPlaybook — summon self-cast NonComparable (utilite plate 1.5, cible = SOI)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


class SpawnPoxwalkersPlaybook(NonComparablePlaybook):
    """`SpawnPoxwalkersPlaybook.EvaluateNonComparable @18115c6f0` (id 0x410=1040, deathBlightbringer).
    Summon SELF-CAST : `SpawnPoxwalkersAbility.ExecuteBehaviour @181208b80` fait apparaitre des
    Poxwalkers sur les `SurroundingTiles(caster)` placables (`CanAddUnit`) puis
    `PerformAIAttackFromCurrentPosition`. La cible de DECISION = le CASTER lui-meme (spawn centre sur soi).

    Structure native (mirror EvaluateNonComparable) : Bucket min = `Fix64.FromInt(1)` (cctor @18115ca90).
    Pour chaque position balayee, enumere `GetEligibleTargetsSelectable(MainTile=position)` @18111f0d0
    (= `GetValidTargets` slot 0x41 moins predicat) ; pour CHAQUE cible eligible ->
    `GenerateAction(position, cible, Fix64.FromIntFraction(3,2)=1.5)` + `Bucket.AddAction`. Utilite
    CONSTANTE 1.5 par cible. La cible eligible native = SOI uniquement (targeting self ; VALIDE LIVE
    seed 2468 s5 : `abilityTargets(u87,1040) = [(unit, 87)]`, ncEvaluate util=1.5 tgt=self).

    - utilite = 1.5 CONSTANTE (Fix64.FromIntFraction(3,2)) ; MIN_UTILITY = 1 (cctor) -> 1.5 toujours admise.
    - cible = SOI (`ctx.uid`) ; la seule cible eligible (self-cast). VALIDE LIVE (miss 2468 s5 tgt=87=self).
    - position : utilite POSITION-INDEPENDANTE (1.5 partout ou self est eligible = toute position) ->
      `Bucket.AddAction` keep-first au tie -> 1re position du sweep = ORIGINE -> cast EN PLACE (to=None).
      VALIDE LIVE (natif caste 1040 sur place a (1,2)=origine ; ncEvaluate n'a que la position courante).
    - ctor @18115cb00 = `NonComparablePlaybook(0x410)` -> 1er arg = ability_id ; PRIORITY=0 (defaut #115).
    - ShouldEvaluate (base @18111fb70) lit `GetUseProbability @18115ca00 = GetStat(unit,0xc=TurnsStarted)
      * Fix64.FromIntFraction(1,5)` = TurnsStarted*0.2 : porte ALEATOIRE (prob>=1 <=> turnsStarted>=5 ->
      True deterministe ; sinon tirage RNG). Comme BlackRage/ItItches (#44 §5), la porte RNG N'EST PAS
      modelisee dans un moteur deterministe -> should_evaluate = True (defaut). FLAG validateur : risque
      d'over-fire aux tours ou le natif RNG-skippe (turnsStarted<5). Au miss s5 le natif a caste."""
    ABILITY_ID = int(ActiveAbilityType.Poxwalkers)  # 1040
    MIN_UTILITY = 1.0     # cctor @18115ca90 = Fix64.FromInt(1) ; util 1.5 constante toujours admise
    PRIORITY = 0
    _UTIL = 1.5           # Fix64.FromIntFraction(3,2) @18115c6f0 = utilite constante par cible eligible

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        # cibles eligibles (GetEligibleTargetsSelectable) : self-cast -> attend SOI. On genere une action
        # ssi SOI est eligible (l'ability est castable a cette position). util constante 1.5.
        self_eligible = False
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    if t.get("kind") == "unit" and t.get("targetId") == ctx.uid:
                        self_eligible = True
        if not self_eligible:
            return []
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] SpawnPoxwalkers self-cast util={self._UTIL}", file=sys.stderr)
        # util constante -> keep-first au tie -> cast en place (origine). Cible = SOI.
        return [{"target": ctx.uid, "ability": self.ABILITY_ID, "to": None, "pred": self._UTIL}]
