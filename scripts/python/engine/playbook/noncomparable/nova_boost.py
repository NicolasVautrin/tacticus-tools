"""NovaBoostPlaybook — self-buff NonComparable (marque hex adjacents)."""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first, native_priority


class NovaBoostPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.NovaBoostPlaybook$$EvaluateNonComparable` : util = `Fix64.FromInt(1)` CONSTANTE par
    cible éligible (self ; marque les hex adjacents au caster). IdunBattle.AI.Playbook.Loki.NovaBoostPlaybook$$.cctor : MIN_UTILITY=1.
    IdunBattle.AI.Playbook.Loki.NovaBoostPlaybook$$.ctor (id 0x4a8=1192 = 1er arg = ABILITY_ID, PAS priorite). Tier get_Priority=**1000**
    (`AbilityPriority.First`) : `NovaBoostPlaybook` SURCHARGE le slot 0 de l'interface IPlaybook.
    MESURE #170 (sweep exhaustif des 257 ActiveAbilityType, invocation du slot 0 via `pbGate` +
    voie independante `abilityPreferences`, 0 divergence) ; `get_IsComparable` = False, donc le tier
    est REELLEMENT exerce. Le 0 pose par #115 etait un FAUX NEGATIF de methode : les corps
    `mov eax,imm32 ; ret` sont dedupliques par IL2CPP, invisibles a une recherche de symboles.

    STATUT : DECOMPILE-PROVEN, **ARENE-INAGREABLE** (Riptide non spawnable au rank 17 -> pas de test
    d'agreement live ; le mecanisme repose sur le decompile, tiers tranches a l'octet par le validateur).
    - R1 RESOLU (#80) : NovaBoost est un SELF-buff (cible = self, util=1 CONSTANTE) -> MEME CLASSE que les
      self-cast heals. Le generateur `<GenerateActions>d__7 IdunBattle.AI.ActionGenerators.ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext` GATE chaque tuile de move par
      `HasValidTargets(0x3f)(unit, movePos, ability)` puis `Bucket.AddAction` garde le 1er ajoute (NullPosition
      = cast EN PLACE, TOUJOURS evaluee). Pour un SELF-target la cible (self) est position-INDEPENDANTE -> le
      gate ne motive aucune tuile de move -> le natif CASTE EN PLACE. CONFIRME LIVE (self-cast heal #76 :
      deathRotbone self-heal RESTE EN PLACE a util constante). FIX = `_sweep_origin_first` (origine d'abord ->
      to=None), mirror du comportement heal confirme. [La fonction exacte de `HasValidTargets` est derriere un
      dispatch d'interface (@180028910 = trampoline), non lisible statiquement -> la base est la COHERENCE
      GENERATEUR + la classe self-target confirmee, PAS un agreement (arene-inagreable). Cf. NovaShield =
      classe TILE-target, comportement OPPOSE.]
    - N1 : gate `IdunBattle.AI.Playbook.Loki.NovaBoostPlaybook$$ShouldEvaluate` = `if query.slot0x1a(unit,2) then base.ShouldEvaluate else 0`
      (précondition Nova, prob. charge, + base) NON modélisé -> on s'appuie sur le filtre driver
      `usable is False` (supposé encoder la précondition). L'eligible-empty (`GetEligibleTargetsSelectable`
      vide -> le natif n'émet rien) est modélisé ci-dessous."""
    ABILITY_ID = int(ActiveAbilityType.NovaBoost)  # 1192
    MIN_UTILITY = 1.0
    PRIORITY = native_priority(int(ActiveAbilityType.NovaBoost))   # 1000 = AbilityPriority.First (surcharge mesuree, #170)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        if not self._has_eligible_target(ctx):
            return []   # N1 : GetEligibleTargetsSelectable vide -> le natif n'émet rien
        # R1 RESOLU (#80) : SELF-target (util=1 CONSTANTE) = MEME CLASSE que les self-cast heals #76 -> le
        # generateur gate les tuiles de move (self-cible position-independante) -> keep-first sur NullPosition
        # => le natif RESTE EN PLACE. `_sweep_origin_first` (origine d'abord) -> to=None.
        to = next(iter(_sweep_origin_first(ctx)), None)
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (to if to != ctx.origin else None), "pred": 1.0}]

    def _has_eligible_target(self, ctx: NCContext) -> bool:
        """`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` non-vide. Cible éligible d'un self-buff =
        self (via abilityTargets, qui inclut les cibles NON-attaque). PERMISSIF si la source d'éligibilité
        est indisponible (le driver filtre déjà `usable is False`)."""
        if ctx.ability_targets is None:
            return True
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        for u in (at.get("units") or []):
            for a in (u.get("abilities") or []):
                if a.get("abilityId") == self.ABILITY_ID and (a.get("targets") or []):
                    return True
        return False
