"""`SupremeCommanderPlaybook` — face DECISION de l'active 1028 (`astraCreed` « Creed »).

DEBLOQUE PAR #95-RESTE2 : ce playbook etait volontairement NON PORTE parce que son gate (2)
`IsFriendlyKell` exige un ENFANT du caster, et que la seule source d'enfant avant le premier cast est
`SwornProtector` (spawn de Kell) — non portee jusqu'ici. Un port l'aurait rendu systematiquement
`False` = code enregistre-mais-mort. `SwornProtector` etant desormais portee (et confrontee live),
le gate est ATTEIGNABLE offline : le port devient legitime.

RE (decompile ghidra, build `gqfc5mff6c`) — relue integralement, pas reprise du doc :

  `IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$.ctor`  = `NonComparablePlaybook<...>(0x404 = 1028)`
  `IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$.cctor` = `MIN_UTILITY = Fix64.FromInt(1)` = **1.0**

  `IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$ShouldEvaluate(unit)` :
      1. `if (BasePlaybook.EnemyWillBeKilledWithNormalAttack(this, unit)) return false;`
      2. `sel   = ability.baseSelector@+0x80 op_Addition DSLFactory.AllDeadUnits()`
         `units = sel.SelectUniqueUnits(entities)`
         `if (!units.Any(u => IsFriendlyKell(u, unit))) return false;`
      3. `pct    = FillUpStatComponent.RemainingPercentage(unit)`
         `chance = Fix64(1/2) + pct / Fix64(2)`
         `return this@0x30.<slot 4>(chance)`            # TIRAGE de chance

  `IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$IsFriendlyKell(u, caster)` :
      `pc = u.GetComponent<ParentComponent>()`
      `return pc.<+0x10> == EntityId(caster) && UnitExtensions.IsFriend(u, caster)`
      => « u est un ENFANT du caster ET son allie » (le selecteur amont inclut `AllDeadUnits()` :
      un Kell MORT satisfait encore le gate).

  `IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$EvaluateNonComparable(entities, position)` :
      `bucket  = new Bucket(0, Nullable(MIN_UTILITY = 1))`
      `targets = BasePlaybook.GetEligibleTargetsSelectable(this, entities, position.MainTile)`
      `foreach t in targets: bucket.AddAction(GenerateAction(position, t, Fix64(3/2)))`
      => utilite **PLATE 3/2 = 1.5** par cible (aucun terme de scoring), admise car `1.5 >= 1.0`.

GAP ASSUME (meme classe et meme traitement que `BlackRagePlaybook`, dont le natif tire 0.4) : le
TIRAGE de chance de l'etage (3) n'est pas reproduit — le port rend `True` des que les gates
DETERMINISTES (1) et (2) passent. Consequence : offline le playbook propose 1028 la ou le natif peut
le sauter. La formule exacte est citee ci-dessus ; `FillUpStatComponent.RemainingPercentage` (jauge de
« fill-up ») n'est de toute facon pas materialise offline. A pleine jauge la chance vaut 1 (100 %) et
le port est EXACT ; a jauge vide elle vaut 1/2.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook
from .hammer_of_wrath import _enemy_killed_by_normal_attack

# `Fix64.FromIntFraction(3, 2)` de `EvaluateNonComparable` : utilite PLATE par cible.
SUPREME_COMMANDER_FLAT_UTILITY = 1.5


class SupremeCommanderPlaybook(NonComparablePlaybook):
    """`SupremeCommanderPlaybook` (0x404 = 1028, `astraCreed`) — summon NonComparable a utilite PLATE.

    Ne s'evalue QUE si (a) l'attaque normale ne tue pas deja un ennemi et (b) Creed a un ENFANT allie
    (= Kell, vivant OU mort). Toutes les cibles eligibles recoivent la MEME utilite 1.5 : le playbook
    n'exprime aucune preference de cible, il exprime « caste maintenant »."""
    ABILITY_ID = int(ActiveAbilityType.SupremeCommander)   # 1028 = 0x404
    MIN_UTILITY = 1.0     # `.cctor` : Fix64.FromInt(1)
    PRIORITY = 0

    def should_evaluate(self, ctx: NCContext) -> bool:
        """Etages (1) et (2) du `ShouldEvaluate` natif (l'etage (3) = tirage de chance, cf. en-tete)."""
        if _enemy_killed_by_normal_attack(ctx):            # (1) EnemyWillBeKilledWithNormalAttack
            return False
        return self._has_friendly_kell(ctx)                # (2) Any(IsFriendlyKell)

    def _has_friendly_kell(self, ctx: NCContext) -> bool:
        """`Any(u => IsFriendlyKell(u, caster))` sur `baseSelector + AllDeadUnits()`.

        Port : un enfant du caster, de la MEME equipe, VIVANT OU MORT. La source des morts est
        `ctx.obs_units` (`decisionView` garde les depouilles, cf. `project_decisionview_keeps_dead`) ;
        le lien parent vient de `parentId` (pose au spawn). Aucune de ces deux seams -> False
        (degradation fidele : sans lien parent le natif rendrait False aussi)."""
        me = None
        for u in (ctx.units or []):
            if u.get("id") == ctx.uid:
                me = u
                break
        my_team = me.get("team") if me else None
        pool = list(ctx.units or []) + list(ctx.obs_units or [])
        for u in pool:
            if u.get("parentId") != ctx.uid:               # pc.<+0x10> == EntityId(caster)
                continue
            team = u.get("team", u.get("teamId"))
            if my_team is None or team == my_team:         # UnitExtensions.IsFriend(u, caster)
                return True
        return False

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`EvaluateNonComparable` : une action par cible eligible, utilite PLATE 3/2.

        `GetEligibleTargetsSelectable(position.MainTile)` = les cibles legales du cast depuis la
        position balayee -> le port les lit du RPC `abilityTargets` (meme seam que les autres NC
        summon). 1028 est un cast SELF (`now[1]:u<self>` live) : la seule cible est le caster."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        targets: list = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("targets") or []):
                    tid = t.get("targetId")
                    if tid is not None and tid not in targets:
                        targets.append(tid)
        if not targets:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] SupremeCommander targets=%s util=%.1f"
                  % (ctx.uid, targets, SUPREME_COMMANDER_FLAT_UTILITY), file=sys.stderr)
        return [{"target": t, "ability": self.ABILITY_ID, "to": None,
                 "pred": SUPREME_COMMANDER_FLAT_UTILITY} for t in targets]
