"""`CallRipperSwarmsPlaybook` (1052, `tyranBossHiveTyrantLeviathan`) -- face DECISION (#1032-r1).

BASE LUE, JAMAIS DEDUITE DU `.ctor`
------------------------------------
`data/symbols/<build>/frida/classes.tsv` :

    IdunBattle.AI.Playbook.Loki.CallRipperSwarmsPlaybook | 112 |
        IdunBattle.AI.Playbook.Loki.ABossSummonAbilityPlaybook`1
    IdunBattle.AI.Playbook.Loki.ABossSummonAbilityPlaybook`1 | 0 |
        IdunBattle.AI.Playbook.NonComparablePlaybook`1

C'est donc bien un NonComparable, mais **par une base INTERMEDIAIRE**, et cette base porte du code
que la classe fille n'a pas : c'est elle qui definit `GetUseProbability` (cf. plus bas). Ghidra
etiquette le `.ctor` `ComparablePlaybook<...>$$.ctor` -- corps gshared DEDUPLIQUE, meme piege que
#487-r1 / #945 / #957.

REACHABILITE : `data/symbols/<build>/metadata/active_playbook_builders.tsv` monte CETTE MEME classe
pour **TROIS** ids -- `1052 CallRipperSwarms`, `1054 CallRipperSwarms2`, `1055 CallRipperSwarms3` --
parce que `...CallRipperSwarmsPlaybook$$.ctor(this, activeAbilityType)` prend son id EN PARAMETRE
(contrairement a tous ses voisins, qui l'ecrivent en dur). **Seul `1052` entre au registre du port**
: `1054` et `1055` n'ont AUCUNE face COMBAT (`ABILITY_CLASSES` ne les porte pas), et une face
DECISION qui proposerait une ability que le runner ne sait pas executer est exactement le no-op
silencieux de #996 -- on ne l'ouvre pas.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.CallRipperSwarmsPlaybook$$EvaluateNonComparable` :

    min    = <statics[0]>                                     # `.cctor` = Fix64.op_Implicit(1)
    bucket = new Bucket<UnitAction>(0, Nullable(min))         # surcharge a QUATRE arguments
    foreach entities in BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition):
        bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, entities.<+0x10 = target>,
                                                      <statics[0]>))
    return bucket

=> **utilite PLATE = 1**, sans AUCUN terme. Le corps ne lit ni la cible, ni la position, ni une
stat : le MEME `Fix64` statique sert de borne au bucket ET d'utilite a chaque action. C'est le
patron deja porte par `WarHowlPlaybook` (#969) et `RevealPlaybook`.

`...CallRipperSwarmsPlaybook$$GetMaxSummons` (surcharge du slot 31 abstrait de la base) :
`WaaaghAbility$$GetNumSummons(this.ability@+0x68)` -- le symbole est celui de `Waaagh` parce que
IL2CPP DEDUPLIQUE le corps `GetNumberConstant(config@+0x60, 0x10)`, identique pour les deux
abilities. La cle est donc `AbilityConstantType.nrOfSummons`, LUE dans le gameconfig de
`CallRipperSwarms` (= 4), surtout pas celui de `Waaagh`.

LA CIBLE EST LE CASTER -- SELF-CAST
------------------------------------
`...CallRipperSwarmsAbility$$.ctor` ne construit AUCUN `TargetingOptions` : il recopie les 0x40
octets du preset statique `<TargetingOptions statics>+0x280`, dont le `.cctor` ecrit
`isSelfCasting = 1`, `range = RANGE_SELF` et `rules = 0x8004` (`CasterMatchesDynamicRule |
CasterIsPossibleTarget`) -- deja transcrit par `engine/runner/abilities/tyranids.py::
CallRipperSwarmsAbility.TARGETING_OPTIONS` (#1032). L'unique cible que
`GetEligibleTargetsSelectable` peut rendre est donc le CASTER lui-meme, et c'est ce que
`GenerateAction` reemet.

AUCUN DEPLACEMENT : l'utilite est PLATE, donc toutes les positions de `reach_nc` sont a egalite, et
`Bucket$$AddAction` ne remplace que sur un STRICTEMENT superieur -> la premiere position enumeree
gagne, c'est-a-dire l'ORIGINE (`ai.context.action_tiles_for` la met en tete). `to = None`.

⚠ LA PROBABILITE D'USAGE VIENT DE LA BASE, ET ELLE A DEUX REGIMES
------------------------------------------------------------------
`IdunBattle.AI.Playbook.Loki.ABossSummonAbilityPlaybooku003Cobjectu003E$$GetUseProbability(unit)`
-- MIRROR, lu verbatim sur le corps gshared inflate :

    if (unit.GetComponent<BaseUnitComponent>().StartedTurns < 2)
        return FIRST_TURN_PROBABILITY;                 # `.cctor` = Fix64.FromIntFraction(1, 2)
    n   = UnitExtensions$$GetChildren(unit, state, u => UnitExtensions$$IsAlive(u, state)).Count
    max = this.<vtable +0x328> GetMaxSummons()
    return Fix64(1) - (Fix64.FromIntFraction(8, 10) * Fix64(n)) / Fix64(max)

TROIS lectures qui ne se devinent pas :

1. **Le champ compare a `2` est `BaseUnitComponent.StartedTurns @+0x58`** -- le nom du STATIQUE le
   dit (`FIRST_TURN_PROBABILITY`, lu au dump `Il2CppDumper`), et l'offset le confirme : c'est le
   MEME compteur que le corps folde `AlphaWarriorPlaybook$$ShouldEvaluate` (`GetStat(unit, 0xc =
   TurnsStarted) > 1`) interroge. `< 2` est donc la NEGATION exacte de ce gate-la, et le port
   reutilise son substrat (`ctx.scene.turns_started`), pas un second.
2. **`GetChildren` filtre `IsAlive`, donc les DEPOUILLES ne comptent PAS** -- contraste
   `UnitExtensions$$GetChildrenCount` (predicat NUL), que `DoctrinaImperativesPlaybook` mirrore et
   dont la liste est append-only. Deux natifs voisins, deux semantiques : ne pas transposer.
3. **La formule ne rend JAMAIS `<= 0`.** `0.8 * n / max <= 0.8` tant que `n <= max`, donc
   `p >= 0.2` ; et le regime `n > max` n'existe pas (le cast est cape par `max`). Aucune des deux
   branches ne peut donc faire REFUSER `BasePlaybook$$ShouldEvaluate` : ce mirror ne deplace AUCUN
   verdict. Il est porte quand meme parce que `p` est desormais une VALEUR confrontable -- le
   capteur `shouldEvaluateTrace` publie la `prob` EXACTE passee a `NextBool` (meme raison que
   `WarHowlPlaybook`, #969-r1).
"""
from __future__ import annotations

from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effects.magnitude import ability_var

from ._base import NCContext, NonComparablePlaybook

#: `GetNumberConstant(config@+0x60, 0x10)` du corps DEDUPLIQUE etiquete
#: `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetNumSummons`. Membre nomme.
CONST_NR_OF_SUMMONS = AbilityConstantType.nrOfSummons

#: `ABossSummonAbilityPlaybook<T>$$.cctor` : `Fix64.FromIntFraction(1, 2)` -> le statique
#: `FIRST_TURN_PROBABILITY` (nom LU au dump `Il2CppDumper`, pas devine).
_FIRST_TURN_PROBABILITY = 0.5
#: `Fix64.FromIntFraction(8, 10)` du numerateur de la penalite d'occupation.
_CHILDREN_PENALTY = 0.8
#: Le litteral `2` de `StartedTurns < 2` (`BaseUnitComponent+0x58`).
_FIRST_TURN_THRESHOLD = 2


class CallRipperSwarmsPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.CallRipperSwarmsPlaybook$$EvaluateNonComparable` (0x41c = 1052).

    Utilite PLATE `Fix64(1)` sur l'unique cible eligible (le caster, self-cast) ; toute la
    modulation vit dans `GetUseProbability`, herite d'`ABossSummonAbilityPlaybook<T>`. Detail
    terme a terme : l'en-tete du module."""

    ABILITY_ID = int(ActiveAbilityType.CallRipperSwarms)   # 0x41c = 1052
    #: `...CallRipperSwarmsPlaybook$$.cctor` = `Fix64.op_Implicit(1)`, passe au ctor du `Bucket` par
    #: la surcharge a QUATRE arguments (`Bucket$$.ctor(b, 0, &Nullable(min), <type>)`). Gate
    #: d'`AddAction` INCLUSIF (`utilite >= min`), donc l'utilite plate 1 est admise.
    MIN_UTILITY = 1.0
    #: 1052 est ABSENTE de `NATIVE_PRIORITY` (sweep exhaustif #170) -> `AbilityPriority.Normal`.
    PRIORITY = 0

    # ------------------------------------------------------------------ la base `ABossSummon...`

    def _max_summons(self) -> int | None:
        """`...CallRipperSwarmsPlaybook$$GetMaxSummons` = `GetNumberConstant(config, 0x10)`.

        La cle est lue sur le gameconfig de **1052**, pas sur celui de `Waaagh` : le symbole
        `WaaaghAbility$$GetNumSummons` ne designe que le corps DEDUPLIQUE, pas la config.
        Absente -> `None` (jamais un `0`, qui ferait une division par zero)."""
        v = ability_var(ActiveAbilityType(self.ABILITY_ID).name, CONST_NR_OF_SUMMONS.name,
                        is_constant=True)
        try:
            n = int(v)
        except (TypeError, ValueError):
            return None
        return n if n > 0 else None

    def _alive_children(self, ctx: NCContext) -> int | None:
        """`UnitExtensions$$GetChildren(unit, state, u => IsAlive(u, state)).Count`.

        Substrat, SANS CAPTEUR NEUF : `decisionView.units[].parentId` + son discriminant
        `parentMeasured` (#378, le canal que `SupremeCommanderPlaybook` consomme deja). Le natif lit
        `ParentComponent.children` sur le PARENT ; le port lit `ChildComponent.ParentId` sur chaque
        ENFANT -- les deux faces de la meme relation.

        TRI-ETAT STRICT : si AUCUNE ligne ne porte `parentMeasured is True`, le canal n'a rien
        mesure -> `None`. Rendre `0` ferait croire << ce boss n'a aucun summon vivant >> et donc
        `p = 1.0` (le maximum), c'est-a-dire la valeur la plus permissive INVENTEE -- exactement le
        contraire du tri-etat.

        `IsAlive` : `decisionView` GARDE les depouilles (`project_decisionview_keeps_dead`), donc
        le filtre `alive` est OBLIGATOIRE ici, et c'est ce qui separe ce mirror de
        `GetChildrenCount` (predicat NUL, liste append-only) que `DoctrinaImperativesPlaybook`
        porte."""
        lignes = list(ctx.units or [])
        if not any(u.get("parentMeasured") is True for u in lignes):
            return None                       # canal MUET -> non mesure, jamais un `0` invente
        n = 0
        for u in lignes:
            if u.get("parentMeasured") is not True or u.get("parentId") != ctx.uid:
                continue
            if u.get("id") == ctx.uid:
                continue                      # une unite n'est jamais son propre enfant
            if u.get("alive"):                # `u => UnitExtensions$$IsAlive(u, state)`
                n += 1
        return n

    def use_probability(self, ctx: NCContext) -> float | None:
        """`ABossSummonAbilityPlaybooku003Cobjectu003E$$GetUseProbability(unit)` -- MIRROR 1:1 :

            if (StartedTurns(unit) < 2)  return FIRST_TURN_PROBABILITY;   # 1/2
            return 1 - (0.8 * |children vivants|) / GetMaxSummons();

        TRI-ETAT : `None` = PAS MESURE (compteur de tours absent, canal parent muet, ou
        `nrOfSummons` introuvable) -> `probability_gate` rend `True`, degradation PERMISSIVE.
        Jamais `0.0` : `Fix64.Zero` est la valeur qui fait REFUSER, et le natif ne la produit
        JAMAIS ici (cf. l'en-tete, point 3)."""
        scene = getattr(ctx, "scene", None)
        ts = scene.turns_started(ctx.uid) if scene is not None else None
        if ts is None:
            return None                       # compteur non capte -> non mesure
        if int(ts) < _FIRST_TURN_THRESHOLD:
            return _FIRST_TURN_PROBABILITY    # `return FIRST_TURN_PROBABILITY`
        n = self._alive_children(ctx)
        mx = self._max_summons()
        if n is None or mx is None:
            return None
        return 1.0 - (_CHILDREN_PENALTY * float(n)) / float(mx)

    # ------------------------------------------------------------------ le corps propre

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`EvaluateNonComparable` : utilite PLATE `Fix64(1)` sur la cible eligible (= le caster,
        self-cast), position = l'ORIGINE par keep-first.

        On lit quand meme la cible par `ability_targets` plutot que de la poser d'office : c'est ce
        qui evite de proposer un cast que la cascade de ciblage refuse (cooldown,
        `CasterMatchesDynamicRule`). Meme montage que `WarHowlPlaybook.generate_candidates`.

        ⚠ `fromHere` et non `targets` : l'utilite etant plate, seule l'ELIGIBILITE compte, et
        `fromHere` est la vue PAR POSITION (a l'origine) -- `targets` est l'UNION sur toutes les
        tuiles de move, donc il declarerait eligible un cast que le natif refuse depuis l'origine.
        Le natif, lui, ne bougera pas : `AddAction` est keep-first et l'origine est en tete."""
        if ctx.ability_targets is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    if t.get("kind") == "unit" and t.get("targetId") == ctx.uid:
                        # Utilite plate 1 == MIN_UTILITY -> admise par `Bucket$$AddAction`
                        # (`utilite >= min`, gate INCLUSIF).
                        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                                 "to": None, "pred": 1.0}]
        return []


__all__ = ["CallRipperSwarmsPlaybook"]
