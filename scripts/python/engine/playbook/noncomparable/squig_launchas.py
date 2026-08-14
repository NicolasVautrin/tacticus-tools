"""`SquigLaunchasPlaybook` (1200, `orksRukkatrukk` « Rukkatrukk » -- MACHINE OF WAR Orks) -- #970-r3.

Sa face COMBAT est portee et confrontee depuis #115/#585-r1 (`engine/runner/abilities/orks.py`) ;
c'est la face DECISION qui manquait, donc l'IA la choisissait avec un scoring qui n'etait pas celui
du natif -- divergence de POLITIQUE, INVISIBLE en replay puisque l'execution, elle, est fidele.

BASE LUE, JAMAIS DEDUITE DU `.ctor`
-----------------------------------
`data/symbols/<build>/frida/classes.tsv` :

    IdunBattle.AI.Playbook.Loki.SquigLaunchasPlaybook | 112 | IdunBattle.AI.Playbook.NonComparablePlaybook`1

Le `.ctor`, lui, est etiquete `ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor`
par ghidra (`..ctor(this, 0x4b0 = 1200)`) -- corps trivial DEDUPLIQUE, le piege #487-r1 que
`storm_speeder` documente deja. Lire la base dans `classes.tsv`, jamais dans le nom du `.ctor`.

REACHABILITY, LUE dans `data/symbols/<build>/metadata/active_playbook_builders.tsv`
-----------------------------------------------------------------------------------
    active   1200   IdunBattle.AI.Playbook.Loki.SquigLaunchasPlaybook

⚠ La MEME table porte `triggered 1200 IdunBattle.AI.Playbook.Loki.ControlEdictPlaybook` : c'est un
`TriggeredAbilityType` 1200, un AUTRE enum a ordinal egal. Qualifier l'enum avant de s'en servir.

RECENSEMENT DE LA CLASSE (`ghidra/functions.tsv`, prefixe de classe)
--------------------------------------------------------------------
TROIS corps : `.ctor`, `.cctor`, `EvaluateNonComparable`. Pas de `ShouldEvaluate` propre -- le
gate d'ouverture reste celui de la base (`should_evaluate` par defaut). Temoin que la mesure SAIT
voir une surcharge quand il y en a une : `...Loki.ArmoriumCherubPlaybook` porte SIX corps
(`.ctor`, `CalculateCustomUtility`, `CanKillTarget`, `GetNumEnemiesInNormalAttackRange`,
`MakeDamagePredictions`, `ShouldExecute`) et `...Loki.MightFromBelowPlaybook` TROIS.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.SquigLaunchasPlaybook$$EvaluateNonComparable`, lu verbatim :

    bucket = new Bucket<UnitAction>(0, Nullable(<premier statique de la classe>))   # `.cctor` : Fix64(1)
    foreach entities in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition):
        crit = <SquigLaunchasAbility>$$FulfillsSummonCriteria(this.ability@+0x68)
        e    = new AbilityEntities(target: entities@+0x10, caster: caster, <tout le reste NUL>)
        if (!crit.<vtable +0x188 = ShouldTrigger>(e, 0x20 = GroupType.Ability_Attack))
            continue
        util = Fix64.op_Implicit( this.rng@+0x30.<IPseudoRNG slot 2 = Next>(1, 10) )
        bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, entities@+0x10, util))
    return bucket

`IdunBattle.AI.Playbook.Loki.SquigLaunchasPlaybook$$.cctor` :
`<statique> = FixMath.NET.Fix64.op_Implicit(1)` -> `MIN_UTILITY = 1`.

Le champ `+0x30` de `BasePlaybook` EST l'`IPseudoRNG` : c'est celui que
`IdunBattle.AI.Playbook.Common.DefaultActiveAbilityPlaybook$$ShouldEvaluate` passe au slot 5
(`NextBool`) pour son tirage. `IPseudoRNG` slot **2** = `Next`/2 params, LU dans
`data/symbols/<build>/metadata/interface_slots.tsv` -- pas deduit d'un nom.

⚠ **LE GATE EST PLUS STRICT QUE LE CIBLAGE, ET C'EST TOUT L'EFFET OBSERVABLE.** Les deux
predicats natifs sont les MEMES, sur des seuils DIFFERENTS :

  * CIBLAGE (`...SquigLaunchasAbility$$GetDynamicInvalidTargetReason`, bit
    `TargetMatchesDynamicRule` du masque) : `>= nrOfUnits (0x78) = 1` Ork **OU**
    `>= nrOfUnits_2 (0x79) = 2` allies adjacents -- c'est lui qui filtre deja `abilityTargets` ;
  * SUMMON (`...SquigLaunchasAbility$$FulfillsSummonCriteria`, ce playbook ET l'`ExecuteBehaviour`) :
    `>= nrOfUnits_3 (0x81) = 2` Orks **OU** `>= nrOfUnits_4 (0x82) = 4` allies adjacents.

Une cible peut donc etre LEGALE et ne PAS remplir le critere de summon. Le natif ne propose alors
PAS 1200 sur elle ; un port sans cette face DECISION la proposait. C'est exactement le regime que
le montage de validation doit exhiber (temoin non nul).

`...SquigLaunchasAbility$$FulfillsSummonCriteria` est deja porte, en ARBRE DSL, par la face
COMBAT (doctrine #149 : l'artefact natif est un arbre de noeuds, donc le port est un arbre) --
`engine.runner.abilities.orks.squig_launchas_fulfills_summon_criteria`. Ce module ne le RE-ECRIT
pas comme arbre : il en re-exprime la SEMANTIQUE sur le substrat `NCContext`, comme
`silent_death` le fait pour son `Enemies(AdjacentUnits(...))` et `duty_eternal` pour son
`GetSurroundingUnits`. La route DECISION n'a pas d'executeur DSL sur `NCContext` (pas de `State`) ;
importer la face COMBAT ferait dependre un playbook d'un `State` qui n'existe pas ici.

L'UTILITE EST UN TIRAGE, ET LE SEUIL NE FILTRE RIEN
----------------------------------------------------
`NextInternal(min, max)` (relu : `range = max - min`, `return min + (g % range)`) exclut la borne
HAUTE -> `Next(1, 10)` est dans **[1, 9]**, neuf valeurs equiprobables. Le gate de `Bucket` est un
`>=` (`IdunBattle.AI.BucketSystem.Bucketu003C__Il2CppFullySharedGenericTypeu003E$$AddAction` ->
le predicat de seuil -> `Fix64.op_GreaterThanOrEqual(action.Utility, minUtility)`), et
`MIN_UTILITY = 1` : **tout** tirage franchit donc le seuil. Contrairement a `Hailstrike` (#967-r3),
il n'y a ici AUCUN regime ou le tirage decide de l'EXISTENCE de l'action -- la borne BASSE suffit,
et aucune borne haute n'est requise.

Ce que le tirage decide, en revanche, c'est **QUELLE** cible : il est refait a chaque iteration,
donc c'est un bruit INDEPENDANT par cible. `AddAction` ne remplace que sur `>` STRICT, donc :

  * le port pose le terme a sa borne BASSE **LUE** (1) -- constante sur toutes les cibles, donc
    l'argmax retombe sur le **keep-first** de l'ordre d'enumeration natif. Toute constante commune
    aux N cibles est l'IDENTITE sur l'argmax : ce `1` ne choisit donc rien, il refuse d'inventer un
    bruit -- et il franchit le seuil, ce que `0` ne ferait pas.
  * la cible EFFECTIVEMENT choisie par le natif est **INDETERMINABLE** dans un moteur
    deterministe : le port ne consomme aucun des tirages de l'IA, donc l'etat du Mersenne Twister
    diverge des le premier. On la NOMME (residu `#970-r6`), on ne la fitte pas.

Ce qui EST determinable, et que ce port rend fidele : **quelles cibles sont proposables** (le gate)
et **a quel tier** (`PRIORITY = 1000` = `AbilityPriority.First`, deja dans `NATIVE_PRIORITY`,
mesure #170) -- donc que 1200 PRIME sur toute autre action de `orksRukkatrukk` des qu'une cible
passe le gate.

VOIE D'ENUMERATION -- UNIT-TARGETED
------------------------------------
`...SquigLaunchasAbility$$.ctor` pose `TargetIsEnemy | TargetMatchesDynamicRule |
AllowNullCasterTile` (masque LU au litteral, cf. `runner/abilities/orks.py`) : la cible est une
UNITE ennemie. Cote port, `_targets.eligible_units` (`abilityTargets(uid, 1200).fromHere`,
`kind == "unit"`), dans l'ORDRE EXACT du selecteur natif. L'ecart connu du foyer (« `fromHere`
n'enumere que depuis l'ORIGINE ») est ici structurellement INERTE : le porteur est une MACHINE OF
WAR, entite SANS `PositionComponent`, donc `ctx.reach_nc` est vide.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effects.magnitude import ability_var
from engine.entities.unit_faction import UnitFaction
# FORME B pour le lecteur de traits : une liaison figee au chargement rendrait MUETTE toute
# contre-epreuve qui substitue le predicat (meme mesure que #977 sur `might_from_below`).
from engine.entities.traits import unit_trait as _UT
from engine.entities.traits.unit_trait import UnitTrait

import engine.playbook.noncomparable._targets as TGT   # FORME B, en ABSOLU (cf. #962)
from ._base import NCContext, NonComparablePlaybook, native_priority, _unit_cfg


class SquigLaunchasPlaybook(NonComparablePlaybook):
    """1200 -- gate `FulfillsSummonCriteria` par cible, utilite = un TIRAGE `rng.Next(1, 10)`.

    Cf. l'en-tete du module pour le corps natif terme a terme, et pour les deux axes que le tirage
    decide (aucun sur le SEUIL, tout sur le CHOIX de cible)."""

    ABILITY_ID = int(ActiveAbilityType.SquigLaunchas)   # 0x4b0 = 1200
    #: `...SquigLaunchasPlaybook$$.cctor` : `FixMath.NET.Fix64.op_Implicit(1)` -> le `minUtility`
    #: du `Bucket` (gate `AddAction`, compare en `>=`).
    MIN_UTILITY = 1.0
    PRIORITY = native_priority(int(ActiveAbilityType.SquigLaunchas))   # 1000 = AbilityPriority.First

    #: Borne BASSE **LUE** de `rng.Next(1, 10)`. `IdunBattle.Utils.PRNG.IntBasedMersenneTwister
    #: $$NextInternal` rend `min + (g % (max - min))` -> borne haute EXCLUE -> `[1, 9]`. Constante
    #: sur toutes les cibles (donc identite sur l'argmax -> keep-first), et `>= MIN_UTILITY` (donc
    #: le seuil est franchi, ce que `0` ne ferait pas). Le port ne fabrique aucun bruit.
    RNG_TERM = 1.0

    #: `GetNumberConstant(config@0x60, 0x81)` -- seuil ORKS du critere de SUMMON.
    VAR_ORKS_MIN = "nrOfUnits_3"
    #: `GetNumberConstant(config@0x60, 0x82)` -- seuil ALLIES du critere de SUMMON.
    VAR_FRIENDS_MIN = "nrOfUnits_4"

    #: `IdunBattleLogic.Entities.DSLSelectors$$NonSteppableOrObjectUnits` retire ces deux traits
    #: (intersection des deux complementaires, cf. le foyer `entities/selectors/units.py`).
    EXCLUDED_TRAITS = (UnitTrait.Steppable, UnitTrait.Object)
    #: `IdunBattleLogic.Entities.DSLSelectors$$UnitsFromFaction(., 5, 3)` -- le natif compare
    #: `System.Enum.ToString(UnitFaction)` au `FactionComponent+0x30` ; pendant offline = le
    #: `FactionId` gameconfig, et le NOM du membre d'enum EST cette chaine.
    FACTION = UnitFaction.Orks

    def _threshold(self, key: str) -> int:
        return int(ability_var(ActiveAbilityType(self.ABILITY_ID).name, key,
                               is_constant=True) or 0)

    def _adjacent_friends(self, ctx: NCContext, tpos: tuple) -> list[dict]:
        """`Friends( Owner@+0x148, NonSteppableOrObjectUnits( AdjacentUnits(target@+0x178, unique: 1,
        OnlyAliveAndTargetable) ) )` -- les unites ALLIEES DU CASTER, ni `Steppable` ni `Object`,
        adjacentes a la tuile de la CIBLE.

        Le referent de `Friends` est l'OWNER (le caster MoW), pas la cible : « friendly » = de MON
        camp. C'est la meme lecture que la face COMBAT, ou elle est confirmee live (case-mow §5 :
        amener 2 de MES unites au contact de l'ennemi ouvre le ciblage).

        Substrat, nomme canal par canal :
          * `AdjacentUnits(<tuile de la cible>)` -> `bq.is_adjacent` (voisinage NATIF stocke +
            porte d'elevation |dElev| < 2), le meme foyer que `might_from_below` ;
          * `Friends(Owner, .)` -> `ctx.fpos` = les positions ALLIEES vivantes, self exclu. L'ecart
            « self exclu » est INERTE ici : le caster est une MoW sans `PositionComponent`, elle
            n'occupe aucune tuile de ce canal ;
          * `NonSteppableOrObjectUnits(.)` -> traits d'ENTITE (`_UT.entity_trait_names`), jamais le
            kit par visualId seul.

        Canal `fpos` MUET (vide) -> aucun allie vu -> le critere ne peut pas etre rempli, donc
        l'ability n'est pas proposee. Degradation CONSERVATRICE, dans le meme sens que le gate
        natif (qui REFUSE) : le port ne propose jamais un cast que le natif refuserait."""
        fpos = set(getattr(ctx, "fpos", None) or [])
        if not fpos:
            return []
        scene = getattr(ctx, "scene", None)
        neigh = bq.neigh_map(ctx)
        out: list[dict] = []
        for u in (ctx.units or []):
            p = u.get("pos") or {}
            if p.get("col") is None or not u.get("alive"):
                continue
            pos = (p["col"], p["row"])
            if pos not in fpos:
                continue                       # pas un ALLIE du caster (self exclu par `fpos`)
            if not bq.is_adjacent(tpos, pos, ctx.elev_by_pos, neigh):
                continue                       # `AdjacentUnits(<tuile de la cible>)` : ring 1
            uctx = scene.ctx(u.get("id")) if scene is not None else None
            if _UT.has_any_trait(_UT.entity_trait_names(uctx, u.get("visualId")),
                                 self.EXCLUDED_TRAITS):
                continue                       # `NonSteppableOrObjectUnits`
            out.append(u)
        return out

    def fulfills_summon_criteria(self, ctx: NCContext, tpos: tuple) -> bool:
        """`...SquigLaunchasAbility$$FulfillsSummonCriteria` =
        `op_BitwiseOr( HasMinimumAdjacentOrks(Direct(0x81)), HasMinimumAdjacentFriendlyUnits(Direct(0x82)) )`.

        `IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr` = un OU logique des deux `ShouldTrigger`, et
        `AmountIsEqualOrGreater(sel, n)` = `Count(sel) >= n`
        (`IdunBattle.Entities.Conditions.AmountIsEqualOrGreaterAbilityTrigger$$ShouldTrigger` :
        `return seuil <= gauche`).

        Seuil non lisible dans le gameconfig -> `0`, donc `Count >= 0` est VRAI : le port ne
        REFUSE pas sur du non-mesure. C'est le sens permissif, mais il est ici SANS effet net --
        le ciblage natif (`abilityTargets`) a deja filtre les cibles, et il porte les MEMES
        predicats a des seuils plus bas."""
        friends = self._adjacent_friends(ctx, tpos)
        n_friends = len(friends)
        n_orks = sum(1 for u in friends
                     if (_unit_cfg(u.get("visualId")) or {}).get("FactionId")
                     == self.FACTION.name)
        return (n_orks >= self._threshold(self.VAR_ORKS_MIN)
                or n_friends >= self._threshold(self.VAR_FRIENDS_MIN))

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """La boucle de `EvaluateNonComparable` : gate par cible, puis `AddAction` a utilite
        CONSTANTE -> `Bucket$$AddAction` ne remplace que sur `>` STRICT, donc la PREMIERE cible qui
        passe le gate gagne (keep-first sur l'ordre natif de `fromHere`)."""
        elig = TGT.eligible_units(ctx, self.ABILITY_ID)
        if not elig:
            return []
        for tid, pos in elig:
            if tid is None or pos is None or pos[0] is None:
                continue                       # cible sans position mesuree -> gate non evaluable
            if not self.fulfills_summon_criteria(ctx, pos):
                continue
            if self.RNG_TERM < self.MIN_UTILITY:
                continue                       # gate `minUtility` du `Bucket` (`>=`), mirrore
                #                                EXPLICITEMENT : avec `RNG_TERM = 1` et
                #                                `MIN_UTILITY = 1` il ne filtre RIEN (c'est le
                #                                fait natif, cf. l'en-tete), mais l'ecrire evite
                #                                qu'un changement de borne le fasse diverger en
                #                                SILENCE.
            if ctx.debug:
                import sys
                print("    [dbg NC u%s] SquigLaunchas target=%s util=%s (tirage non porte, [1,9])"
                      % (ctx.uid, tid, self.RNG_TERM), file=sys.stderr)
            return [{"target": tid, "ability": self.ABILITY_ID, "to": None,
                     "pred": self.RNG_TERM}]
        return []


__all__ = ["SquigLaunchasPlaybook"]
