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
      `c = u.GetComponent<ChildComponent>()`
      `return c.ParentId<+0x10> == EntityId(caster) && UnitExtensions.IsFriend(u, caster)`
      => « u est un ENFANT du caster ET son allie » (le selecteur amont inclut `AllDeadUnits()` :
      un Kell MORT satisfait encore le gate). #119 : le composant lu est `ChildComponent`
      (`ParentId`, BEntityId @+0x10 — offset CONFIRME live par `dumpEntityComponents` sur Kell),
      PAS `ParentComponent` (qui porte `ChildrenIds`, une `List` @+0x10 : la lire comme un int
      n'aurait aucun sens). Les DEUX composants sont presents sur toute unite (Creed compris),
      d'ou l'absence de branche null dans le natif.

  `IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$EvaluateNonComparable(entities, position)` :
      `bucket  = new Bucket(0, Nullable(MIN_UTILITY = 1))`
      `targets = BasePlaybook.GetEligibleTargetsSelectable(this, entities, position.MainTile)`
      `foreach t in targets: bucket.AddAction(GenerateAction(position, t, Fix64(3/2)))`
      => utilite **PLATE 3/2 = 1.5** par cible (aucun terme de scoring), admise car `1.5 >= 1.0`.

ETAGE (3) — le TIRAGE, et pourquoi le port est EXACT a PV PLEINS (#119, RE relue) :
`FillUpStatComponent.RemainingPercentage` = `Max(0, remaining@+0x18 / get_CurrentMaximumValue())`.
Le composant interroge est celui du stat **5 = Health** : `ShouldEvaluate` fait le MEME
`GetComponent` que la branche `param_2 == 5` de `IdunBattle.Entities.UnitExtensions$$GetFillUpStatComponent`
(meme classe generique, meme static de type). Ce n'est donc PAS une « jauge de fill-up » abstraite
non materialisee offline : c'est le **ratio de PV du CASTER**.

  `chance = Fix64(1/2) + hp(caster)/hpMax(caster) / 2`   ->   PV PLEINS => chance = 1

Le tirage est `IRandom.Chance(chance)` (meme slot que `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate`,
champ `this@+0x30`, interface slot 4). A chance = 1 il passe TOUJOURS — CONFIRME LIVE (#119) :
20/20 tirages `CalculateNextActionForUnit` d'affilee sur le meme etat rendent le cast 1028.
=> a PV PLEINS le port (qui rend True des que (1) et (2) passent) est EXACT.
GAP ASSUME, borne et mesure : sous les PV pleins le port SUR-PREDIT (il propose 1028 la ou le natif
peut sauter, avec une probabilite d'abstention `(1 - hp%)/2`, donc au pire 1/2 a l'agonie). Meme
classe de gap que `BlackRagePlaybook` (`GetUseProbability` = 0.4) — moteur deterministe, pas de RNG
d'IA porte.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _kit_spawn_visual_ids
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
        """`Any(u => IsFriendlyKell(u, caster))` sur `baseSelector@+0x80 + AllDeadUnits()`.

        Le selecteur amont est l'union « toutes les unites VIVANTES » (`DSLFactory@+0x80`, pose par
        `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`) et « toutes les MORTES »
        (`IdunBattleLogic.Entities.DSLSelectors$$AllDeadUnits`) = TOUTES les unites, les deux camps :
        c'est `IsFriend` qui filtre l'equipe, pas le selecteur. D'ou le pool = `ctx.units` (dv, qui
        garde les depouilles — `project_decisionview_keeps_dead`) + `ctx.obs_units` (observeBattle,
        qui porte `isDead`), SANS filtre de vie : un Kell MORT satisfait encore le gate.

        `IsFriend(u, caster)` = meme equipe. Le caster est exclu de son propre pool d'enfants (une
        unite n'est jamais son propre parent).

        `c.ParentId == EntityId(caster)` est LU (#378) des que le canal le porte : le capteur publie
        `ChildComponent.ParentId` dans `decisionView.units[].parentId`, avec son discriminant
        `parentMeasured`. C'est le mirror EXACT du natif, qui ne fait rien d'autre --
        `IdunBattle.AI.Playbook.Loki.SupremeCommanderPlaybook$$IsFriendlyKell` prend le
        `ChildComponent` de `unit`, compare `*(int *)(comp + 0x10)` a l'`EntityId` du caster, et
        delegue a `IdunBattle.Entities.UnitExtensions$$IsFriend`.

        REPLI, unite par unite : celles dont le champ n'est PAS mesure (hook anterieur a #378, ou
        ligne venue d'`observeBattle` qui ne porte pas ce champ) restent traitees par
        `_kit_spawn_visual_ids` -- la derivation config, exacte tant qu'une equipe ne porte pas deux
        summoners du meme summon (cf. sa docstring). Le repli est PAR LIGNE et non global pour que
        la couverture ne baisse jamais : `obs_units` reste la source des MORTS, qu'un Kell tombe
        satisfait encore le gate.

        AVANT #119 ce predicat lisait `u["parentId"]`, ABSENT de toute reponse RPC -> il rendait
        False EN PERMANENCE : `should_evaluate` etait constant False et le playbook, quoique
        enregistre, ne proposait JAMAIS 1028. Desaccord MESURE avec l'IA native (le natif caste,
        le port attaque)."""
        me = None
        for u in (ctx.units or []):
            if u.get("id") == ctx.uid:
                me = u
                break
        if me is None:
            return False
        kids = _kit_spawn_visual_ids(me.get("visualId"))
        my_team = me.get("team")
        for u in (list(ctx.units or []) + list(ctx.obs_units or [])):
            if u.get("id") == ctx.uid or u.get("squadId") == ctx.uid:
                continue                                   # pas son propre enfant
            # `c.ParentId == EntityId(caster)` -- LECTURE quand le capteur a mesure, derivation
            # config sinon. `parentMeasured is True` + `parentId != uid` est un NON franc : on ne
            # retombe PAS sur l'heuristique derriere une mesure, ce serait la rendre permissive.
            if u.get("parentMeasured") is True:
                if u.get("parentId") != ctx.uid:
                    continue
            elif not kids or u.get("visualId") not in kids:
                continue
            team = u.get("team") if u.get("team") is not None else u.get("teamId")
            if my_team is None or team is None or team == my_team:   # IsFriend(u, caster)
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
