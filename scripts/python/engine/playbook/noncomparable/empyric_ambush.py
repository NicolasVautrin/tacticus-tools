"""EmpyricAmbushPlaybook -- face DECISION de `1232 EmpyricAmbush` (`eldarLhykhis`). #1006.

BASE, LUE dans `data/symbols/<build>/frida/classes.tsv` :
`IdunBattle.AI.Playbook.Loki.EmpyricAmbushPlaybook` -> `IdunBattle.AI.Playbook.NonComparablePlaybook`1`.
Le `.ctor` decompile NOMME `ComparablePlaybook<__Il2CppFullySharedGenericType>..ctor(this, 0x4d0)`
-- corps gshared trivial DEDUPLIQUE, donc mislabele.

REACHABILITY, LUE dans `data/symbols/<build>/metadata/active_playbook_builders.tsv` :
`active 1232 -> ...EmpyricAmbushPlaybook`. ⚠ Le build porte AUSSI un
`...EmpyricAmbush_ResetPlaybook` (classe DISTINCTE, autre ability) : ne pas les confondre.
"""
from __future__ import annotations

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait

import engine.playbook.noncomparable._targets as TGT              # FORME B, ABSOLU (#962)
from ._base import NCContext, NonComparablePlaybook, _traits


class EmpyricAmbushPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.EmpyricAmbushPlaybook$$EvaluateNonComparable` (0x4d0 = 1232).

    LE CORPS, TERME A TERME
    -----------------------
        bucket = new Bucket<UnitAction>( 0, Nullable(<statics+0x00>) )   # `.cctor` : Fix64(1)
        if (this.battleQuery@+0x28 == null) throw
        hi = battleQuery.<IBattleQuery slot 170 = GetHighestMaxHealthFromNoneBossConfig>()
        foreach entities in GetEligibleTargetsSelectable(caster, casterPosition):
            t    = entities.Target@+0x10
            hp   = UnitExtensions.GetStat(t, 5, 0, 0)
            util = Fix64.Max( Fix64(hi - hp), Fix64(1) )
            bucket.AddAction( GenerateAction(casterPosition, t, util) )

    Soit : **(le plus haut PV MAX non-boss de la bataille) MOINS les PV COURANTS de la cible**,
    plancher `1`. C'est un score de FINISSEUR -- plus la cible est BLESSEE, plus l'utilite monte --
    et le terme `hi` est une CONSTANTE de bataille qui ne sert qu'a rendre le score positif et
    comparable ; il ne discrimine aucune cible.

    ⚠ `hi` EST HISSE HORS DE LA BOUCLE PAR LE NATIF LUI-MEME (un seul appel, avant
    `GetEligibleTargetsSelectable`). Ce n'est donc pas une optimisation du port.

    ⚠ `statPart = 0 = Current`, PAS `Maximum`. Contraste DIRECT avec `InfernalCannonPlaybook`
    (1209, meme tranche) qui ecrit `GetStat(u, 5, 2, 0)` = `StatPart.Maximum`. Meme stat, meme
    squelette, deux ordinaux -- et confondre les deux INVERSERAIT le classement (viser le plus
    gros au lieu du plus blesse) sans lever la moindre erreur. Les noms sont lus dans
    `frida/enums.tsv` (`IdunBattle.Entities.Enum.StatPart`), jamais devines.

    ⚠ `GetStat` est appele sur `entities.Target` **DIRECTEMENT**, sans `UnitExtensions.GetUnit`
    prealable (contraste 1209 et `MalleusRocketLauncher`) : la cible est donc deja une UNITE pour
    ce playbook, jamais une tuile.

    LE SLOT 170, LU dans `data/symbols/<build>/metadata/interface_slots.tsv`
    -----------------------------------------------------------------------
    `IBattleQuery 170 = GetHighestMaxHealthFromNoneBossConfig(0 params)`. Corps de
    `IdunBattle.Core.Services.BattleQuery$$GetHighestMaxHealthFromNoneBossConfig` :

        best = int.MinValue                                  # 0x80000000
        foreach (cfg in this.<+0xa0>.<+0x80>)                # les UnitConfiguration de la BATAILLE
            if (!cfg.<+0xd0 = traits>.Contains(0x7e7))       # 0x7e7 = 2023 = UnitTrait.Boss
                best = Math.Max(cfg.<+0x38 = maxHealth>, best)
        return best

    Trois lectures qui comptent : il balaie la **CONFIGURATION** de la bataille (les deux camps,
    morts compris), il **EXCLUT les Boss**, et il rend `int.MinValue` si tout est boss (regime
    inatteignable en pratique, mais c'est ce qui est ecrit).

    `GetUseProbability` EST SURCHARGEE, ET ELLE OUVRE UN VRAI TIRAGE -- NON PORTE
    ----------------------------------------------------------------------------
    `...EmpyricAmbushPlaybook$$GetUseProbability(unit)` rend `<FixMath.NET.Fix64 statics>+0x30`.
    `FixMath.NET.Fix64$$.cctor` ecrit a cet offset `op_Division(0x100000000, 0x200000000)` =
    `Fix64(1) / Fix64(2)` = **0.5**. Le consommateur `BasePlaybook$$ShouldEvaluate` fait alors :
    `0.5 >= 1` faux, `0.5 <= 0` faux -> **tirage RNG autobot a 50 %**.

    C'est EXACTEMENT l'ecart assume que `_base.NonComparablePlaybook.should_evaluate` documente
    pour `BlackRagePlaybook` (0.4) et `ItItchesPlaybook` : le moteur porte est DETERMINISTE, donc
    `should_evaluate` rend `True` et l'ability est TOUJOURS evaluee la ou le natif la saute une
    fois sur deux. On ne l'invente pas, on le NOMME -- residu `#1006-r1`.
    ⚠ Contraste avec `DoomboltPlaybook` de la MEME tranche, dont le `GetUseProbability` surcharge
    rend un POURCENTAGE (33) : la, `prob >= 1` est vrai et le `True` constant est un mirror EXACT.
    Deux surcharges du meme getter, deux regimes opposes -- d'ou l'obligation de lire la VALEUR et
    pas seulement l'existence de la surcharge."""
    ABILITY_ID = int(ActiveAbilityType.EmpyricAmbush)    # 0x4d0 = 1232 (argument du ctor natif)
    MIN_UTILITY = 1.0     # `EmpyricAmbushPlaybook$$.cctor` : `FixMath.NET.Fix64.op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    #: `Fix64.Max(..., Fix64(1))` -- le plancher, qui est aussi `MIN_UTILITY` : toute cible
    #: eligible passe donc le gate `Bucket.AddAction`, comme `ForwardSpotterPlaybook` (1143).
    UTILITY_FLOOR = 1.0

    def _highest_max_health_non_boss(self, ctx: NCContext) -> int | None:
        """`IBattleQuery` slot 170 `GetHighestMaxHealthFromNoneBossConfig()`.

        Substrat : `ctx.obs_units` (`observeBattle.units`), qui porte `hpMax` et `visualId`. Le
        trait `Boss` se lit au gameconfig sur le `visualId`, comme le natif le lit sur la
        `UnitConfiguration`.

        ⚠ LES MORTS SONT COMPTES, ET C'EST VOULU : le natif balaie la CONFIGURATION de la bataille,
        pas l'etat vivant -- aucun filtre `isDead` n'apparait dans son corps. `obs_units` garde les
        depouilles (`isDead`), donc ne pas filtrer EST le mirror.

        DEUX ECARTS NOMMES, tous deux dans le sens d'une SOUS-estimation de `hi` :
          * les **MACHINES OF WAR** sont hors de ce canal (`observeBattle` les publie dans `.mows`,
            et `state_bridge._obs_units` les exclut explicitement) ;
          * une unite CONFIGUREE mais jamais spawnee (summon non invoque) n'y est pas.
        Une sous-estimation de `hi` translate TOUTES les utilites du meme montant : le CLASSEMENT
        des cibles est inchange tant que le plancher `1` ne mord pas. Il ne mord que si
        `hi - hp <= 1` pour la cible, c'est-a-dire sur des cibles quasiment a plein PV du plus gros
        gabarit -- ou l'ecart peut aplatir des cibles que le natif separait.

        `None` = **PAS MESURE** (canal muet), distingue d'un zero : l'appelant retombe alors sur le
        plancher plutot que d'inventer un `hi`."""
        best = None
        for u in (ctx.obs_units or []):
            hp_max = u.get("hpMax")
            if hp_max is None:
                continue
            names = _traits(u.get("visualId")) or []
            if UnitTrait.Boss.name in [str(n) for n in names]:
                continue                                  # `!traits.Contains(0x7e7 = Boss)`
            v = int(hp_max)
            if best is None or v > best:
                best = v                                  # `Math.Max(cfg.maxHealth, best)`
        return best

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        # Domaine UNITE : `GetStat(entities.Target, ...)` est appele SANS `GetUnit` prealable.
        elig = TGT.eligible_units(ctx, self.ABILITY_ID)
        if not elig:
            return []
        hi = self._highest_max_health_non_boss(ctx)        # HISSE, comme le natif
        best, scored = None, []
        for tid, _pos in elig:                            # LISTE : ordre natif, jamais un `set`
            hp = ctx.hp_cur_by_id.get(tid)                # GetStat(t, Health = 5, Current = 0)
            if hi is None or hp is None:
                util = self.UTILITY_FLOOR                 # canal muet -> le plancher, jamais un
                #                                           `hi` invente (cf. le tri-etat ci-dessus)
            else:
                util = max(float(hi) - float(hp), self.UTILITY_FLOOR)   # `Fix64.Max(hi - hp, 1)`
            scored.append((tid, util))
            if best is None or util > best[1]:            # `AddAction` : remplacement STRICT
                best = (tid, util)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] EmpyricAmbush target=%s util=%s hi=%s scored=%s"
                  % (ctx.uid, best[0], best[1], hi, scored), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]
