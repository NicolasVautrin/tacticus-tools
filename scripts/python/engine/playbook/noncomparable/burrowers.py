"""BurrowersPlaybook -- deplacement NonComparable self-target : plus c'est LOIN, mieux c'est."""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _normal_attack_ids


class BurrowersPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.BurrowersPlaybook$$EvaluateNonComparable` (id 0x3ff = 1023).

    ## Le corps, verbatim (`rnca9r7q6c`)

        bucket = new Bucket<T>()                       # ctor SANS borne (2 args)
        d = IBattleQuery<this+0x28>.<slot 0x6c = 108 GetDistance>(
                IdunBattle.Entities.EntityExtensions$$GetMainTile(caster, this+0x20),
                IdunBattle.Core.UnitPosition$$get_MainTile(casterPosition))
        x = Fix64(d)
        if (d > 0):
            x += IPseudoRNG<this+0x30>.<slot 3 = Next(min, max)>(
                     FixMath.NET.Fix64$$op_UnaryNegation(<statique>), <statique>)
        bucket.AddAction(IdunBattle.AI.Playbook.BasePlaybook$$GenerateAction(casterPosition, caster, x))
        return bucket

    `d` est la distance hexagonale entre la tuile ACTUELLE du caster et la tuile CANDIDATE : la
    cible de l'action est le CASTER lui-meme (`GenerateAction(casterPosition, caster, x)`), donc
    c'est un playbook de DEPLACEMENT, et l'utilite CROIT avec l'eloignement -- Burrowers preferent
    la destination la plus LOINTAINE.

    Les DEUX slots sont RESOLUS, jamais devines : `IBattleQuery` slot 108 = `GetDistance` (2
    parametres) est LU dans `data/symbols/<build>/metadata/interface_slots.tsv`, et le port delegue
    a `engine.battle_query.get_distance`, mirror de
    `IdunBattle.Core.Services.MovementQuery$$GetDistance` (distance hexagonale minimale entre deux
    ENSEMBLES de tuiles -- aucun pathfinding, aucune elevation).

    ## Le statique de classe : BORNE DU RNG, et RIEN D'AUTRE (#1021-r2)

    `IdunBattle.AI.Playbook.Loki.BurrowersPlaybook$$.cctor` ecrit `Fix64(1)` dans le statique de
    classe, exactement comme `IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$.cctor` -- ou il
    tient le role de `MIN_UTILITY`. ICI il ne le tient PAS, et la lecture le tranche sans ambiguite :
    le statique n'apparait qu'aux DEUX arguments du tirage (`op_UnaryNegation(S)` puis `S`), il
    n'est compare a rien, et le `Bucket<T>` est construit par la surcharge a **2** arguments --
    celle SANS borne (`HeavyRailRiflePlaybook`, elle, appelle la surcharge a 4 arguments, qui en
    prend une). `AddAction` est donc inconditionnel.

    ⇒ `MIN_UTILITY = 0.0` (le defaut), et le meme littéral `Fix64(1)` porte ici l'amplitude du
    bruit. Recopier le role du voisin de forme aurait pose un seuil qui n'existe pas.

    ## L'ECART, nomme et BORNE

    Le terme `IPseudoRNG` n'est pas porte : le moteur est deterministe, et c'est le regime deja
    assume pour les playbooks a `GetUseProbability` conditionnelle (`_base.NonComparablePlaybook
    .should_evaluate`). Le port prend donc `u = d`, c'est-a-dire l'ESPERANCE du terme natif -- le
    tirage est symetrique sur `[-1, +1]`.

    Ce que cela coute est BORNE, et c'est ce qui rend le port confrontable : `u_i = d_i + r_i` avec
    `r_i` dans `[-1, +1]`, donc l'ecart de bruit entre deux positions vaut au plus **2**. Une
    position strictement plus loin de **plus de 2** hexs qu'une autre gagne donc QUEL QUE SOIT le
    tirage : l'argmax du port est exact partout ou l'ecart de distance depasse 2, et indetermine
    seulement sur les quasi-ex-aequo. Une confrontation live doit donc porter sur une DISTRIBUTION,
    ou sur un montage dont la meilleure tuile devance la suivante de 3 hexs ou plus.

    ## Le gate amont

    `IdunBattle.AI.Playbook.Loki.BurrowersPlaybook$$ShouldEvaluate` = `GetAllNormalAttackTargets(
    this, unit).<+0x10>.<count @0x18> < 1` : Burrowers n'est evaluee que si le caster n'a AUCUNE
    cible d'attaque normale. `GetAllNormalAttackTargets` est `IBattleQuery` slot 0x45 =
    `GetAllValidTargetsFromAllPossibleMovementTiles(unit, GetNormalAttackType(unit), 0)` -- donc
    TOUTES les positions de mouvement, pas la seule position courante (ce n'est PAS
    `_has_valid_targets`, qui est le slot 0x40 et ne regarde que la tuile actuelle). Le substrat
    porte de ce balayage est le PLAN, comme pour `HammerOfWrathPlaybook`.

    PIEGE DE BASE ECARTE : le `.ctor` se decompile en `ComparablePlaybook<T>$$.ctor(this, 0x3ff)`,
    mislabel systematique des ctors gshared -- `data/symbols/<build>/frida/classes.tsv` donne
    `IdunBattle.AI.Playbook.NonComparablePlaybook`1`.

    PORTEURS : 6 (npc + summons), le plus peuple des 15 de la dette #1021."""
    ABILITY_ID = int(ActiveAbilityType.Burrowers)   # 0x3ff = 1023
    #: `Bucket<T>` construit par la surcharge SANS borne -> `AddAction` inconditionnel. Le `Fix64(1)`
    #: du `.cctor` est l'amplitude du RNG, pas un seuil (cf. docstring).
    MIN_UTILITY = 0.0
    PRIORITY = 0            # hors NATIVE_PRIORITY -> AbilityPriority.Normal

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`ShouldEvaluate` = « le caster n'a AUCUNE cible d'attaque normale ».

        TRI-ETAT, et il est DERIVE plutot que suppose : un plan qui porte des `evals` mais aucune
        pour l'attaque normale concrete du caster est une mesure -- `count == 0`, le gate PASSE.
        Un plan ABSENT (ou sans `evals` du tout) n'est pas cette mesure : on ne peut pas distinguer
        « aucune cible » de « rien n'a ete balaye ». On rend alors `False`, c'est-a-dire on
        N'EVALUE PAS -- borne RESTRICTIVE assumee et nommee, du meme cote que celle de
        `_enemy_killed_by_normal_attack` : un canal muet n'AJOUTE jamais une action que le natif
        pourrait refuser."""
        evals = (ctx.plan or {}).get("evals")
        if not evals:
            return False                       # canal muet -> on n'invente pas de cast
        normal_ids = _normal_attack_ids(ctx, ctx.uid)
        if not normal_ids:
            return False                       # attaque normale introuvable : meme borne
        for ev in evals:
            if ev.get("abilityId") in normal_ids and (ev.get("rankCount") or ev.get("ranked")):
                return False                   # au moins une cible -> count >= 1
        return True

    def evaluate_non_comparable(self, tile, ctx: NCContext) -> float:
        """`x = Fix64(GetDistance(mainTile(caster), mainTile(casterPosition)))`, terme RNG exclu
        (cf. docstring de classe). `ctx.origin` absent -> 0.0, jamais une distance inventee."""
        if tile is None or ctx.origin is None:
            return 0.0
        return float(bq.get_distance([ctx.origin], [tile]))

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        best_t, best_u = None, None
        for T in ctx.reach_nc:
            u_ = self.evaluate_non_comparable(T, ctx)
            if best_u is None or u_ > best_u:   # strict > : premier max garde (ordre reach_nc)
                best_t, best_u = T, u_
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] Burrowers aid={self.ABILITY_ID} "
                  f"reach={len(ctx.reach_nc)} best={best_t} u={best_u}", file=sys.stderr)
        if best_u is None or best_u < self.MIN_UTILITY:
            return []
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (best_t if best_t != ctx.origin else None), "pred": best_u}]
