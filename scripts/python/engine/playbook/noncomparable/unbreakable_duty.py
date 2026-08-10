"""UnbreakableDutyPlaybook (1061, `templAncient`) -- face DECISION, #572-r2.

LES DEUX SLOTS D'INTERFACE QUE LA FICHE DECLARAIT << ETAGE MANQUANT >> SONT RESOLUS, ET OFFLINE
------------------------------------------------------------------------------------------------
`data/symbols/rnca9r7q6c/metadata/interface_slots.tsv` :

    IBattleQuery  117 (0x75)  GetSurroundingUnits  4 params
    IBattleQuery  125 (0x7d)  GetAdjacentEnemies   3 params

et l'ARITE tranche la surcharge, que le nom seul ne suffisait pas a fixer (`GetSurroundingUnits`
existe en 4 et 3 params ; `GetAdjacentEnemies` en quatre variantes) --
`data/symbols/<build>/frida/methods.tsv` donne les signatures :

    BattleQuery.GetSurroundingUnits(from: IEntity, range: Int32, friendsOf: IEntity,
                                    includeCenter: Boolean)
    BattleQuery.GetAdjacentEnemies (from: IEntity, playerEntityId: BEntityId,
                                    ignoreSteppables: Boolean)

⚠ Le `friendsOf` est LOAD-BEARING et la fiche `case-572` §9 l'omettait : le premier terme ne compte
pas << des unites >> autour du caster, il compte ses **ALLIES**, centre EXCLU.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.UnbreakableDutyPlaybook$$EvaluateNonComparable` :

    bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))       # cctor : Fix64(1)
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster,
                                                                  casterPosition.get_MainTile()):
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10,
                                                     <statics+0x00>))

L'utilite est donc **CONSTANTE**, et c'est le MEME statique que `MIN_UTILITY` -- le gate
`Bucket$$AddAction` (`util >= min`) passe toujours, et toutes les cibles eligibles sont a EGALITE.
L'argmax retombe alors entierement sur le keep-first du Bucket : PREMIERE position de `reach_nc`
(l'ORIGINE), PREMIERE cible du plan. Le porter comme une utilite variable serait une invention.

`IdunBattle.AI.Playbook.Loki.UnbreakableDutyPlaybook$$GetUseProbability(unit)` -- LE gate, et il
n'est PAS qu'aleatoire :

    mainTile = EntityExtensions.GetMainTile(unit, state@this+0x20)
    if (mainTile == null) return Fix64(0)                       # -> ShouldEvaluate FAUX
    playerId = unit.GetComponent<OwnerComponent>().get_CurrentPlayerEntityId()
    range    = AbilityConfiguration.GetNumberConstant(config@this+0x68+0x60, 0x16 = range)
    p        = 10 * battleQuery.<0x75>(mainTile, range, friendsOf: unit, includeCenter: false).Count
    n        = UnbreakableDutyAbility.GetAmountOfDeadImperialUnits(ability).Calculate(entities, _)
    if (n > 1) {
        p += 40
        if (battleQuery.<0x7d>(unit, playerId, ignoreSteppables: false).Count > 0)  p += 30
    }
    return <p>/100                    # Fix64(p)/100*100 arrondi /100 -- un POURCENTAGE

Le `/100` est LU, pas suppose : le helper terminal fait
`Round(Fix64(p) / Fix64(100) * Fix64(100), 0) / Fix64(100)` (l'idiome << pourcentage arrondi >> du
codebase natif). Sans lui, `p` valant 10/40/70 serait toujours `>= 1` et le gate ne pourrait
JAMAIS rendre faux -- la lecture change donc le comportement, elle ne le decore pas.

`GetAmountOfDeadImperialUnits` rend un `IdunBattle.DSL.IAmountFormula` (signature LUE dans
`methods.tsv`), invoque au slot **1 = `Calculate`** de cette interface : c'est un COMPTE. Le meme
sous-arbre est deja porte par la face COMBAT
(`engine.runner.abilities.blacktemplars.unbreakable_duty_dead_imperial_heroes`) --
`UnitsWithTraits(Friends(AllDeadOrResurrectedUnits, of: Owner), [Imperial, Hero])`, une CONJONCTION.

CE QUE `ShouldEvaluate` EN FAIT (`BasePlaybook$$ShouldEvaluate`, impl de base)
------------------------------------------------------------------------------
`prob >= 1 -> True` ; `prob <= 0 -> False` ; sinon TIRAGE. Le moteur porte est DETERMINISTE, donc
la porte aleatoire n'est pas modelisee (meme statut assume que `BlackRage` 0.4, `ItItches`,
`ScarabSummon` -- cf. `_base.NonComparablePlaybook.should_evaluate`). Ce qui EST porte, et qui
importe, c'est le **zero** : sans allie a portee ET sans deux heros imperiaux morts, `p == 0` et le
natif n'evalue PAS l'ability. Les trois termes participent donc au verdict BINAIRE -- le `+40`
seul suffit a faire passer un caster isole de FAUX a VRAI.

BORNES DE PORT, nommees
------------------------
* `AllDeadOrResurrectedUnits` inclut les RESSUSCITES ; le substrat offline (`obs_units.isDead`) ne
  voit que les morts COURANTS. Borne INF sur `n` : le port peut rendre FAUX la ou le natif rendrait
  VRAI apres une resurrection. Aucun autre canal de `NCContext` ne publie cette histoire.
* `GetSurroundingUnits` est PUREMENT geometrique (disque hex, aucune porte d'elevation) --
  `battle_query.count_surrounding` le mirrore, et `ctx.fpos` porte deja le filtre de camp
  (allies VIVANTS, self exclu), ce que `friendsOf: unit` demande.
* `GetAdjacentEnemies(unit, playerId, ...)` : `ctx.epos` + `battle_query.count_adjacent`, donc la
  porte d'elevation d'`IterateAdjacentTiles`, qui est bien celle de ce slot-la.
* `ignoreSteppables: false` et `includeCenter: false` sont transcrits ; le port ne modelise pas les
  unites STEPPABLE separement (elles sont dans `epos` comme les autres) -- ecart borne SUP sur le
  second terme.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.traits.unit_trait import UnitTrait
from engine.services.ability_caster_gates import try_get_number_constant

from ._base import NCContext, NonComparablePlaybook, _traits

#: `AbilityConfiguration$$GetNumberConstant(config, 0x16)` -- la cle gameconfig est le NOM du membre
#: `AbilityConstantType.range` (le natif indexe par ordinal, le kit par nom : meme table).
_CONST_RANGE = "range"                        # AbilityConstantType 0x16 = 22
#: Les DEUX traits de `UnitsWithTraits(..., [0x1a, 0x10])` -- CONJONCTION, pas union.
_DEAD_TRAITS = (UnitTrait.Imperial.name, UnitTrait.Hero.name)   # 0x1a = 26, 0x10 = 16
#: `10 *` le compte d'allies a portee. Puis le natif ECRASE le bonus par une CONSTANTE -- `p + 0x28`
#: (40) ou `p + 0x46` (70), jamais `40 + 30` : deux litteraux distincts au meme site, transcrits
#: tels quels. Tous en POURCENTS (la division par 100 est en aval).
_PCT_PER_FRIEND = 10
_PCT_DEAD_HEROES = 40             # `iVar13 + 0x28`
_PCT_DEAD_HEROES_AND_ADJACENT_ENEMY = 70   # `iVar13 + 0x46`
#: Le `1 <` du natif : `Count(GetAmountOfDeadImperialUnits) > 1`, soit >= 2 -- MEME seuil que le
#: gate de la face COMBAT (`UNBREAKABLE_DUTY_MIN_DEAD_IMPERIAL_HEROES`).
_MIN_DEAD_IMPERIAL_HEROES = 2


class UnbreakableDutyPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.UnbreakableDutyPlaybook$$EvaluateNonComparable` (0x425 = 1061).

    Base `NonComparablePlaybook`1` -- LUE dans `data/symbols/<build>/frida/classes.tsv`, jamais
    deduite du `.ctor` (qui NOMME `ComparablePlaybook<...>$$.ctor` : corps trivial DEDUPLIQUE,
    partage avec `HammerOfWrath`, `VexillaMagnifica`, `Stormcaller` et `GravitonRifle`, tous
    NonComparable). Meme piege, meme correction que #487-r1.

    Utilite CONSTANTE = `MIN_UTILITY` = `Fix64(1)` du `.cctor` : le playbook ne DEPARTAGE rien, il
    dit seulement << castable ici >>. Tout le discriminant est dans `should_evaluate`."""
    ABILITY_ID = int(ActiveAbilityType.UnbreakableDuty)   # 0x425 = 1061
    MIN_UTILITY = 1.0     # `UnbreakableDutyPlaybook$$.cctor` : `Fix64.op_Implicit(1)` -> statics+0x00
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`BasePlaybook$$ShouldEvaluate` nourri de `UnbreakableDutyPlaybook$$GetUseProbability` :
        `prob <= 0 -> False`, `prob >= 1 -> True`, sinon TIRAGE (non modelise -> True).

        Le port rend donc `use_probability_pct(ctx) > 0`. Pas de tuile d'origine -> le natif rend
        `Fix64(0)` sur `mainTile == null` : meme verdict, meme raison."""
        return self.use_probability_pct(ctx) > 0

    def use_probability_pct(self, ctx: NCContext) -> int:
        """`GetUseProbability` AVANT sa division par 100 -- rendu en POURCENTS ENTIERS pour rester
        exact (le natif arrondit a l'unite de pourcent, cf. l'en-tete du module).

        Expose separement de `should_evaluate` pour etre mesurable : le verdict binaire ne montre
        pas lequel des trois termes a mordu, et un banc qui ne verrait que lui ne pourrait pas
        distinguer << 1 allie >> de << 2 heros imperiaux morts >>."""
        origin = ctx.origin
        if origin is None:                                  # `GetMainTile(unit) == null`
            return 0
        rng = try_get_number_constant(self.ABILITY_ID, _CONST_RANGE)
        if rng is None:
            return 0     # `GetNumberConstant` LEVE sur cle absente ; le port refuse de deviner 0/1
        # <0x75> GetSurroundingUnits(mainTile, range, friendsOf: caster, includeCenter: false)
        pct = _PCT_PER_FRIEND * bq.count_surrounding(origin, ctx.fpos or [], int(rng),
                                                     include_center_tile=False)
        if self._dead_imperial_heroes(ctx) > _MIN_DEAD_IMPERIAL_HEROES - 1:
            # <0x7d> GetAdjacentEnemies(caster, playerId, ignoreSteppables: false) -- imbrique
            # DANS la branche des morts : sans les deux heros, il n'est jamais interroge.
            adj = bq.count_adjacent(origin, ctx.epos or [], ctx.elev_by_pos, bq.neigh_map(ctx))
            pct += (_PCT_DEAD_HEROES_AND_ADJACENT_ENEMY if adj > 0 else _PCT_DEAD_HEROES)
        return pct

    @staticmethod
    def _dead_imperial_heroes(ctx: NCContext) -> int:
        """`Count(UnitsWithTraits(Friends(AllDeadOrResurrectedUnits, of: Owner),
        [Imperial, Hero]))` -- CONJONCTION des deux traits, allies du caster UNIQUEMENT.

        Morts lus dans `obs_units.isDead` : `decisionView` GARDE les depouilles, donc
        `observeBattle` est la seule source (cf. `project_decisionview_keeps_dead`), exactement
        comme `RitesOfRestorationPlaybook`. Les RESSUSCITES du selecteur natif ne s'y voient pas --
        borne INF nommee dans l'en-tete."""
        obs = ctx.obs_units or []
        me = next((u for u in obs if u.get("squadId") == ctx.uid), None)
        if me is None:
            return 0
        team = me.get("teamId")
        n = 0
        for u in obs:
            if not u.get("isDead") or u.get("teamId") != team:
                continue
            tr = _traits(u.get("visualId"))
            if all(t in tr for t in _DEAD_TRAITS):
                n += 1
        return n

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`GenerateAction(casterPosition, entities@+0x10, <statics+0x00>)` -- l'utilite est le
        MEME `Fix64(1)` que `MIN_UTILITY`, pour TOUTE cible eligible. Aucune lecture de la cible,
        aucune lecture de la position : c'est ce que dit le corps, terme pour terme."""
        return self.MIN_UTILITY

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction`, pour une ability **ALLY-TARGETED**.

        ⚠ LE GENERATEUR DE `_PlanTargetPlaybook` NE CONVIENT PAS, ET C'EST MESURE : il enumere
        `ctx.plan["evals"]`, or `computeAttackPlans` (`frida/hooks/features/ai-step/projection.ts`)
        boucle `for (const tgt of enemies)` -- le plan ne porte AUCUNE cible ALLIEE. Le masque de
        1061 est `0x8400` = `TargetIsFriendly | CasterIsPossibleTarget` (LU au
        `UnbreakableDutyAbility$$.ctor`, surcharge a 7 arguments ou le litteral EST le masque), donc
        le plan rend `rankCount = 0` pour toute paire (1061, ennemi) -- confirme live : le natif
        propose `1061 -> u79`, un ALLIE, pendant que le plan annonce `(1061, u87, rankCount 0)`.
        Un port branche sur le plan serait donc MUET, sans erreur.

        Voie employee, la MEME que `ThriceBlessedConflagrationPlaybook` (ally-targeted lui aussi) :
        `abilityTargets(uid, 1061).fromHere` = le mirror de
        `BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition.MainTile)`.

        L'utilite etant CONSTANTE, `Bucket$$AddAction` (remplacement STRICT `>`) garde le PREMIER
        ajoute : la premiere position de `reach_nc` -- l'ORIGINE -- et la premiere cible de
        l'enumeration native. D'ou `to = None` (cast en place) et l'arret a la premiere cible.

        ECART NOMME, identique a celui de `ThriceBlessedConflagration` : `fromHere` n'enumere que
        depuis l'ORIGINE, alors que le natif balaie aussi les tuiles de MOVE. Ici l'ecart est
        BORNE INF et sans effet sur l'argmax tant qu'une cible existe depuis l'origine, l'utilite
        etant position-independante ; il ne mordrait que sur un caster dont AUCUN allie n'est a
        portee sans bouger."""
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
                    tid = t.get("targetId")
                    if tid is None:
                        continue
                    util = self.evaluate_non_comparable(ctx.origin, tid, ctx)
                    if util is None or util < self.MIN_UTILITY:
                        continue
                    return [{"target": tid, "ability": self.ABILITY_ID, "to": None, "pred": util}]
        return []
