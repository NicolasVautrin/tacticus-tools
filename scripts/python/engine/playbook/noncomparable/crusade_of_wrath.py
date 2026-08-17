"""CrusadeOfWrathPlaybook -- face DECISION de `1049 CrusadeOfWrath` (`templHelbrecht`). #969.

Residu `#893-r1` FERME : la face COMBAT etait portee (#893), la face DECISION ne l'etait pas.
"""
from __future__ import annotations

import hexgeo
import gameconfig as _gc
from engine.entities.ability_constant_type import AbilityConstantType
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook, _sweep_origin_first

_ABILITY_NAME = "CrusadeOfWrath"

#: `<statics +0x08>` de `IdunBattle.AI.Playbook.Loki.CrusadeOfWrathPlaybook$$.cctor` =
#: `FixMath.NET.Fix64$$FromIntFraction(1, 10)` -- le SEUL facteur de `GetUseProbability`. C'est un
#: SCALAIRE (une fraction), pas un identifiant : il n'appartient a aucun enum.
_USE_PROBABILITY_FACTOR = 0.1


def _buff_range() -> int | None:
    """`IdunBattle.Configuration.AbilityConfiguration$$GetNumberConstant(0x16)` = `constants["range"]`
    de `CrusadeOfWrath`. (La citation portait `DSLFormulas$$GetNumberConstant` : AUCUNE des cinq
    classes DSL ne declare cette methode -- c'est un accesseur de CONFIG, pas un noeud, #1032-r3.)

    LU dans le gameconfig, jamais ecrit en dur : le natif le lit lui aussi par constante
    (`AbilityConstantType.range` = 22 = 0x16).

    TRI-ETAT : `None` = PAS MESURE (entree de config absente ou illisible). Surtout PAS `0` --
    un rayon nul ferait rendre un compte nul, donc un `should_evaluate` FALSE, donc une ability
    INVISIBLE du moteur : le trou silencieux de #967, fabrique par un canal muet."""
    consts = ((_gc.ability(_ABILITY_NAME) or {}).get("constants") or {})
    brut = consts.get(AbilityConstantType.range.name)
    if brut is None:
        return None
    try:
        return int(brut)
    except (TypeError, ValueError):
        return None


class CrusadeOfWrathPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.CrusadeOfWrathPlaybook` -- MIRROR du decompile.

    ⚠ **BASE `NonComparablePlaybook`1`, LUE dans `frida/classes.tsv`.** Le `.ctor` decompile en
    `ComparablePlaybook<...>..ctor(this, 0x419)` (corps gshared DEDUPLIQUE) -- et la fiche
    `#893-r1` du backlog avait recopie ce nom en annoncant
    `ComparablePlaybook<CrusadeOfWrathAbility>`. C'est FAUX, et c'est la 5e occurrence du meme
    piege (#487-r1, #552, #590, #945). `0x419 = 1049`.

    `...CrusadeOfWrathPlaybook$$.cctor` ecrit **DEUX** statiques, et c'est ce qui distingue ce
    playbook des quatre autres de la tranche :

        <statics +0x00> = Fix64.op_Implicit(1);              // MIN_UTILITY *et* facteur d'utilite
        <statics +0x08> = Fix64.FromIntFraction(1, 10);      // = 0.1, facteur de GetUseProbability

    `...CrusadeOfWrathPlaybook$$EvaluateNonComparable(caster, casterPosition, abilityState)` :

        bucket = new Bucket<UnitAction>( priority: 0, minUtility: Nullable(<+0x00> = 1) );
        var entities = default(AbilityEntities);
        entities.<+0x08> = caster; entities.<+0x18> = caster;
        entities.<+0x40> = casterPosition.MainTile;
        var sel = this.GetBuffTargetsSelector(caster, casterPosition.MainTile);
        int n = sel.<vtable +0x2b8 = ITargetsSelector slot 2 Count>(entities);
        if (n > 0) {
            var utility = <statics +0x00> * Fix64.op_Implicit(n);      // = 1 * n = n
            bucket.AddAction( BasePlaybook$$GenerateAction(this, casterPosition, CASTER, utility) );
        }
        return bucket;

    => **utilite = nombre d'ALLIES QUE LE BUFF TOUCHERAIT DEPUIS CETTE POSITION**, et la cible
    emise est **le CASTER** (`self_cast = True`, cf. `runner/abilities/blacktemplars.py`). UNE SEULE
    action par appel, gatee par `n > 0`.

    `...CrusadeOfWrathPlaybook$$GetBuffTargetsSelector(unit, tile)` =
    `CrusadeOfWrathAbility$$GetBuffTargets( DSLSelectors$$Entity(unit), DSLSelectors$$Entity(tile) )`
    -- le MEME corps natif que la face COMBAT, deja porte par
    `engine.runner.abilities.blacktemplars.crusade_of_wrath_buff_targets` (#893) :

        Friends( of = Owner,
                 entities = SurroundingUnits(CasterTile, GetNumberConstant(0x16 = range),
                                             unique = 1, includeCenter = 0, selectionType = 3)
                            op_Subtraction Caster,
                 selectionType = 3 )

    Le natif n'a donc qu'UN foyer pour les deux faces : decider compte exactement ce qu'executer
    buffera.

    ⚠ **LE TERME EST POSITION-DEPENDANT, ET C'EST TOUT LE PLAYBOOK.** `GetBuffTargetsSelector` est
    reconstruit AVEC la tuile candidate ; le `AbilityEntities` hisse hors de tout, lui, ne porte que
    le caster. Un lecteur presse qui annoterait << terme constant >> parce que l'`entities` est
    construit une fois se tromperait exactement comme #957 : c'est `SurroundingUnits(CasterTile)`
    qui varie, et il varie DANS le selecteur, pas dans le contexte. Conséquence concrete :
    **Helbrecht SE DEPLACE** pour envelopper le plus d'allies possible -- `to` n'est pas `None`.

    `...CrusadeOfWrathPlaybook$$GetUseProbability(unit)` (slot `0x1f8`, celui que
    `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate(unit)` consulte) :

        return <statics +0x08 = 0.1> * Fix64.op_Implicit( this.GetMaxFriendlyUnitsBuffed(unit) );

    `...CrusadeOfWrathPlaybook$$GetMaxFriendlyUnitsBuffed(unit)` :

        int max = 0;
        foreach (var tile in <IBattleQuery slot 10>.GetCurrentAndMovableTilesOf(unit, null, null))
            max = Math.Max(max, this.GetBuffTargets(Entity(unit), Entity(tile))
                                    .<Count>(entities{ +0x08 = unit, +0x18 = unit }));
        return max;

    (slot LU dans `metadata/interface_slots.tsv` : `IBattleQuery 10 GetCurrentAndMovableTilesOf 3`.)

    CE QUE `should_evaluate` REND. `BasePlaybook$$ShouldEvaluate` applique
    `prob >= 1 -> True ; prob <= 0 -> False ; sinon RNG` :

      * `maxBuffed == 0` -> `prob = 0` -> **FALSE, deterministe**. PORTE : si aucune tuile
        atteignable ne met un seul allie a portee, l'ability n'est jamais evaluee.
      * `maxBuffed >= 10` -> `prob >= 1` -> True deterministe. Rendu aussi.
      * `1 <= maxBuffed <= 9` -> `prob` dans `]0, 1[` -> tirage RNG, non modelise -> True (ecart
        assume, cf. `NonComparablePlaybook.should_evaluate`).

    Les trois branches se resument donc a `maxBuffed > 0`, ce que le port ecrit tel quel.

    ⚠ **ET CET ECART A UN PRIX, MESURE (#969-r1).** Le regime intermediaire `1 <= maxBuffed <= 9`
    est celui qui DOMINE en partie (rayon 2, equipes de trois) : le natif y tire a `0.1 x n`, donc
    il s'abstient le plus souvent, la ou le port propose TOUJOURS. Confrontation live
    (`probe_969_contre_epreuve.py`, seed 777 / MC1_67, porteurs `templHelbrecht` +
    `spaceBlackmane` + `ultraInceptorSgt`, tour d'IA OBSERVE, mutation temoin VERIFIEE avant
    d'etre jouee) :

        sans le port   ability match 6/7 (85 %)   positioning exact 8/9 (88 %)
        avec le port   ability match 4/7 (57 %)   positioning exact 6/9 (66 %)

    Les deux MATCH perdus sont `1049` (pas 6) et `1106` (pas 7), ou le natif a joue son ATTAQUE
    NORMALE : dans les deux cas son `GetUseProbability` etait dans `]0, 1[` et le tirage est tombe
    contre le cast. `1049` coute en outre une position (pas 1 : le port emet un cast `to = None`
    la ou le natif se deplace en (3, 2)). Ce n'est PAS un defaut de transcription -- le seul
    canal qui le fermerait est le tirage natif lui-meme, hors de portee offline. Le port reste
    PERMISSIF, conformement a `NonComparablePlaybook.should_evaluate` (meme regime que `BlackRage`
    0.4 et `ItItches`), parce que l'alternative -- refuser -- rendrait l'ability INVISIBLE, ce qui
    est le defaut le plus cher (#967). Residu `#969-r1`.

    `PRIORITY` reste au defaut `0` (`AbilityPriority.Normal`) : `1049` est ABSENTE de
    `NATIVE_PRIORITY` (22 entrees, sweep #170)."""
    ABILITY_ID = int(ActiveAbilityType.CrusadeOfWrath)   # 1049 = 0x419 (argument du ctor natif)
    #: `<statics +0x00>` -- le MEME `Fix64(1)` sert de plancher au `Bucket` ET de facteur a
    #: l'utilite (`utilite = <+0x00> * n`). Un seul statique, deux roles : c'est ce qu'ecrit le
    #: `.cctor`, et les separer donnerait deux constantes la ou le natif n'en a qu'une.
    MIN_UTILITY = 1.0

    @staticmethod
    def _buff_targets_count(ctx: NCContext, tile: tuple, radius: int | None) -> int:
        """`|GetBuffTargets(Entity(caster), Entity(tile))|` = les ALLIES, caster exclu, a distance
        hex <= `radius` de `tile`.

        Substrat : `ctx.fpos` -- les positions des allies VIVANTS, self DEJA exclu
        (`engine.ai.context` : `ctrl and alive and id != uid`). C'est le pendant exact de
        `Friends(of = Owner, ...) op_Subtraction Caster` avec `selectionType = 3`
        (`OnlyAliveAndTargetable`) : le volet `alive` est porte, le volet `Untargetable` ne l'est
        pas -- ECART NOMME, de sens PERMISSIF (un allie en DEEP STRIKE serait compte ici et pas par
        le natif, cf. la mesure `spaceRockfist` de #585).

        ⚠ **DISQUE GEOMETRIQUE, PAS LA LISTE D'ADJACENCE.** `SurroundingUnits` descend sur
        `TileQuery$$IterateSurroundingTiles` (triple boucle cube `x+y+z == 0`), donc SANS la porte
        d'elevation ni le voisinage stocke -- exactement ce que `GrotTankPlaybook` a mesure pour son
        disque r=3, et ce que `ThriceBlessedConflagrationPlaybook` a mesure pour son ring r=1. Y
        cabler `bq.is_adjacent` serait l'erreur inverse de #943 : juste pour `GetAdjacentTiles`,
        fausse pour `GetSurroundingTiles`.

        `includeCenter = 0` : la tuile `tile` elle-meme est exclue (`d >= 1`). INERTE au cas
        nominal -- le caster l'occupe si `tile` est l'origine, et une tuile de move est libre par
        construction -- mais transcrit parce que le natif l'ecrit."""
        if not radius or radius <= 0:      # rayon PAS MESURE (`None`) ou nul -> aucun buffe
            return 0
        n = 0
        for f in (ctx.fpos or ()):
            d = hexgeo.distance(tile, f)
            if 1 <= d <= radius:                     # includeCenter = 0 -> `d >= 1`
                n += 1
        return n

    def _max_friendly_units_buffed(self, ctx: NCContext) -> int:
        """`...CrusadeOfWrathPlaybook$$GetMaxFriendlyUnitsBuffed(unit)` : le MAX du compte sur
        `GetCurrentAndMovableTilesOf(caster)`.

        `ctx.reach_nc` EST cette liste cote port (origine + tuiles de move ; cf. `_sweep_origin_first`
        et `engine.ai.context.action_tiles_for`)."""
        radius = _buff_range()
        best = 0
        for P in _sweep_origin_first(ctx):
            n = self._buff_targets_count(ctx, P, radius)
            if n > best:
                best = n
        return best

    def use_probability(self, ctx: NCContext) -> float | None:
        """`...CrusadeOfWrathPlaybook$$GetUseProbability(unit)` = `<statics +0x08> *
        Fix64.op_Implicit(GetMaxFriendlyUnitsBuffed(unit))`, soit **`0.1 * maxBuffed`** -- rendu
        comme PROBABILITE, le triage des trois branches restant au foyer `_base.probability_gate`.

        DEUX canaux peuvent fabriquer un faux zero, et AUCUN ne doit faire refuser : `reach_nc`
        vide (aucune position candidate mesuree) et un rayon non mesurable au gameconfig. Dans ces
        deux cas on rend `None` = **PAS MESURE**, que `probability_gate` traduit en `True` --
        degradation PERMISSIVE. Un `0.0` a l'aveugle rendrait l'ability INVISIBLE du moteur,
        exactement le trou silencieux de #967. Le zero n'est rendu que sur une mesure complete qui
        dit vraiment << aucun allie a portee, d'aucune tuile >>.

        `fpos` VIDE n'est PAS un canal muet : c'est la mesure << Helbrecht est seul >>, et le natif
        rend `0` dans ce cas aussi (`maxBuffed = 0`).

        ⚠ **CE QUE CE RETOUR CHANGE, ET CE QU'IL NE CHANGE PAS.** Les verdicts sont IDENTIQUES a
        ceux de l'ancien `should_evaluate` (`maxBuffed > 0`), branche par branche : `n = 0` ->
        `0.0` -> refus ; `n >= 10` -> `>= 1` -> accepte ; `1 <= n <= 9` -> bande OUVERTE ->
        accepte (le tirage natif, non reproductible -- cf. `probability_gate`). Ce qui change est
        que `p` est desormais une valeur EXPOSEE, donc confrontable au `prob` que
        `shouldEvaluateTrace` lit dans l'appel natif a `NextBool`. Residu `#969-r1`."""
        if not (ctx.reach_nc or ()) or _buff_range() is None:
            return None
        return _USE_PROBABILITY_FACTOR * float(self._max_friendly_units_buffed(ctx))

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """Sweep natif des positions (ORIGINE en tete), utilite = compte des allies buffes, cible =
        le CASTER. `Bucket$$AddAction` ne remplace que sur un STRICTEMENT superieur -> a compte
        egal, la premiere position -- donc l'origine -- gagne."""
        radius = _buff_range()
        best_p, best_u = None, None
        for P in _sweep_origin_first(ctx):
            n = self._buff_targets_count(ctx, P, radius)
            if n <= 0:                                 # `if (n > 0)` du natif
                continue
            u = self.MIN_UTILITY * float(n)            # `<statics +0x00> * Fix64(n)`
            if u < self.MIN_UTILITY:                   # admission `Bucket$$AddAction`
                continue
            if best_u is None or u > best_u:           # `>` STRICT -> keep-first
                best_p, best_u = P, u
        if best_p is None:
            return []
        return [{"target": ctx.uid, "ability": self.ABILITY_ID,
                 "to": (None if best_p == ctx.origin else best_p), "pred": best_u}]
