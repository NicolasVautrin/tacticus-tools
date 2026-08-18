"""`NovaChargePlaybook` (1193, `tauBossRiptide`) -- face DECISION (#1032-r1).

BASE LUE, JAMAIS DEDUITE DU `.ctor`
------------------------------------
`data/symbols/<build>/frida/classes.tsv` :

    IdunBattle.AI.Playbook.Loki.NovaChargePlaybook | 120 | IdunBattle.AI.Playbook.NonComparablePlaybook`1

(120 = 0x78 : la classe a **un champ de plus** que ses voisines a 112 -- c'est le cache `+0x70`
ci-dessous.) Ghidra etiquette son `.ctor` `ComparablePlaybook<...>$$.ctor(this, 0x4a9)` -- corps
gshared DEDUPLIQUE, meme piege que #487-r1 / #945 / #957. `0x4a9` = 1193 est le seul litteral utile.

REACHABILITE : `data/symbols/<build>/metadata/active_playbook_builders.tsv` ->
`active 1193 IdunBattle.AI.Playbook.Loki.NovaChargePlaybook` (dict `+0x68` de
`IdunBattle.AI.PlaybookDatabase$$InitializePlaybookBuilders`). Le playbook est ENREGISTRE.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.NovaChargePlaybook$$EvaluateNonComparable`, lu verbatim :

    min    = <statics[0]>                                    # `.cctor` = Fix64.op_Implicit(1)
    bucket = new Bucket<UnitAction>(0, Nullable(min))        # surcharge a QUATRE arguments
    targets = BasePlaybook$$GetEligibleTargetsSelectable(caster, casterPosition)
    if (this.<+0x70> == null)                                # LE CACHE
        this.<+0x70> = NovaChargeAbility$$GetLineTiles(this.ability@+0x68)
    foreach entities in targets:
        lines = this.<+0x70>.<ITargetsSelector slot 0 = Select>(entities)
        n     = lines.<slot 0 = get_Count>()
        e     = Playbook<T>$$CountEnemiesOnTiles(caster, lines)
        bucket.AddAction(BasePlaybook$$GenerateAction(casterPosition, entities.<+0x10 = target>,
                                                      Fix64.op_Implicit(e * 100 + n)))
    return bucket

=> **utilite = `100 x |ennemis sur les lignes| + |lignes|`**. AUCUN terme de mouvement (contraste
`NovaShieldPlaybook`, qui ajoute `GetMovementUtility(Tile)` + `DislikeStartingTiles`), aucune
lecture de stat, aucune prediction de degat.

`...NovaChargePlaybook$$ResetCaches` : `base.ResetCaches()` puis `this.<+0x70> = null`. Le cache est
donc un cache d'ARBRE (le noeud `ITargetsSelector`), pas de RESULTAT : `Select` est RE-EVALUE a
chaque cible eligible, et c'est ce qui rend l'utilite dependante de la cible. Cote port, l'arbre est
reconstruit par appel -- il est SANS ETAT (`nova_charge_line_tiles`), donc l'ecart est nul.

`Playbook<T>$$CountEnemiesOnTiles(caster, tiles)` (MIRROR, relu) :

    n = 0
    for i in 0 .. tiles.Count - 1:
        u = UnitExtensions$$GetUnit(tiles[i], state)
        if (u != null && !IBattleQuery.<slot 146 = AreFriends>(caster, u, null))  n++
    return n

-- l'OCCUPANT de chaque tuile, compte s'il n'est PAS ami du caster. Meme lecture, meme residu nomme
que `NovaShieldPlaybook` : `AreFriends` est a TROIS etats cote natif (une entite NEUTRE le rend faux
aussi), la ou le port compte `ctx.epos` -- les seules positions ENNEMIES publiees. Aucun regime
porte ne l'expose (les runners n'ont que deux camps).

LA GEOMETRIE EST LE FOYER DE LA FACE COMBAT
---------------------------------------------
`NovaChargeAbility$$GetLineTiles` est deja porte par `engine/runner/abilities/tau.py::
nova_charge_line_tiles` (#1032). Cette tranche le PARAMETRE (`target_sel`) au lieu de le recopier :
la face DECISION lui passe le vehicule de collapse `FixedTileIds([<tuile visee>])`, exactement
comme `macro_plasma_incinerator_tree` le fait pour `$$GetTargetAreaTiles` (#1066). Un second
mirror ferait diverger les deux faces sur les trois lignes, EN SILENCE.

LES DEUX GATES AMONT, LUS
--------------------------
`...NovaChargePlaybook$$ShouldEvaluate(unit)` :

    if (!IBattleQuery.<slot 27 = HasMinimumRemainingTurns>(unit, 2))  return false;
    return BasePlaybook$$ShouldEvaluate(unit);

`...NovaChargePlaybook$$GetUseProbability(unit)` :

    return UnitExtensions$$CanCurrentlyUseAbility(unit, 0x4aa) ? <Fix64 statics>+0x30
                                                              : <Fix64 statics>+0x20;

et les deux statiques sont LUS dans `FixMath.NET.Fix64$$.cctor` : `+0x20 = 0x100000000` = **One**,
`+0x30 = op_Division(0x100000000, 0x200000000)` = **Half**. Donc :

  * le Riptide PEUT encore lancer `0x4aa = 1194 NovaShield` -> probabilite **0,5** (il garde
    l'option ouverte, tirage RNG) ;
  * il ne le peut PLUS (cooldown, deja utilisee) -> probabilite **1** -> `ShouldEvaluate` VRAI
    DETERMINISTE.

⚠ **`0x4aa` EST UNE AUTRE ABILITY QUE CELLE DU PLAYBOOK.** Qualifie `ActiveAbilityType`, 1194 =
`NovaShield` (1193 = `NovaCharge`, celle-ci). Le corps interroge donc l'etat d'une ability SOEUR du
meme boss -- ce n'est PAS le `usable` que `choose_action` filtre deja en amont pour 1193, et le
confondre rendrait le terme constant.

⚠ **AUCUNE des deux valeurs n'est `<= 0`** : ce mirror ne peut donc jamais faire REFUSER
`BasePlaybook$$ShouldEvaluate` (`prob <= Fix64.Zero -> false`). Il est porte quand meme parce que
`p` est desormais une VALEUR confrontable au capteur `shouldEvaluateTrace`, qui publie la `prob`
EXACTE passee a `NextBool` (meme raison que `WarHowlPlaybook`, #969-r1). `HasMinimumRemainingTurns`,
lui, REFUSE pour de bon -- c'est le seul des deux gates qui deplace un verdict.

CE QUI N'EST PAS PORTE, ET SON SENS
-------------------------------------
* **Le sweep de POSITION change la geometrie**, et le port ne le suit qu'a moitie. Le natif appelle
  `EvaluateNonComparable` une fois par position candidate ; `CasterTile` resout alors la
  `UnitPosition` CANDIDATE, donc les trois lignes partent d'ailleurs. Le port pose `caster_pos` sur
  le contexte DSL et balaie bien `reach_nc` -- mais `CasterTile` n'en garde que la MAIN TILE
  (residu `#459-r1`, structurel), la ou le porteur reel occupe SEPT tuiles. `CenterTiles` d'une
  liste a un element rend cet element : sur le boss, le port prend donc la tuile principale pour le
  centre de l'empreinte. Ecart NOMME, non couvert.
* **`CasterHas7Tiles`** (bit 37 du masque de 1193) n'est porte par aucun gate cote port -- deja
  nomme par la face COMBAT (`runner/abilities/tau.py`). Degradation PERMISSIVE.
* **La confrontation LIVE** : le porteur est un BOSS npc (`tauBossRiptide`), montable par
  `--explicit-stats` sur sa carte dediee, et 1193 est GREFFABLE (precedent mesure : `1194 NovaShield`
  sur `tauCrisis`, `case-92` SS5bis). Non jouee par cette tranche.
"""
from __future__ import annotations

import dataclasses

from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.selectors.accessors import FixedTileIds
from engine.runner.abilities.tau import nova_charge_line_tiles
import engine.playbook.tile_targets as TT       # FORME B, ABSOLU (#962/#985-r1)

from ._base import (NCContext, NonComparablePlaybook, eligible_target_tiles,
                    has_minimum_remaining_turns, probability_gate)

#: `IBattleQuery` slot 27 = `HasMinimumRemainingTurns(unit, turns)` -- le litteral `2` du call-site
#: de `...NovaChargePlaybook$$ShouldEvaluate`.
_MIN_REMAINING_TURNS = 2
#: `<Fix64 statics>+0x30` = `op_Division(1, 2)` = `Fix64.Half`, lu dans `FixMath.NET.Fix64$$.cctor`.
_PROB_SHIELD_READY = 0.5
#: `<Fix64 statics>+0x20` = `0x100000000` = `Fix64.One`, meme lecture.
_PROB_SHIELD_SPENT = 1.0


class NovaChargePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.NovaChargePlaybook$$EvaluateNonComparable` (0x4a9 = 1193).

    Utilite = `100 x CountEnemiesOnTiles(caster, GetLineTiles()) + |GetLineTiles()|`, evaluee PAR
    CIBLE ELIGIBLE (les trois lignes dependent de la tuile visee). Detail : l'en-tete du module."""

    ABILITY_ID = int(ActiveAbilityType.NovaCharge)          # 0x4a9 = 1193
    #: `...NovaChargePlaybook$$.cctor` = `Fix64.op_Implicit(1)`, passe au ctor du `Bucket` par la
    #: surcharge a QUATRE arguments. Gate d'`AddAction` INCLUSIF (`utilite >= min`).
    MIN_UTILITY = 1.0
    #: 1193 est ABSENTE de `NATIVE_PRIORITY` (sweep exhaustif #170) -> `AbilityPriority.Normal`.
    PRIORITY = 0
    #: `Fix64.op_Implicit(e * 100 + n)` -- le `100` LITTERAL du corps.
    _ENEMY_WEIGHT = 100.0
    #: `UnitExtensions$$CanCurrentlyUseAbility(unit, 0x4aa)` -- l'ability SOEUR du meme boss,
    #: qualifiee `ActiveAbilityType` (surtout pas 1193, celle du playbook).
    _SISTER_ABILITY = int(ActiveAbilityType.NovaShield)      # 0x4aa = 1194

    # ------------------------------------------------------------------ les deux gates AMONT

    def _can_currently_use_sister(self, ctx: NCContext) -> bool | None:
        """`IdunBattle.Entities.UnitExtensions$$CanCurrentlyUseAbility(unit, 0x4aa)` -- MIRROR :

            if (unit.Type != Unit && unit.Type != 6)             return false;
            a = GetComponent<ActiveAbilityComponent>(unit).GetActive(type);
            if (a == null)                                       return false;
            return a.get_CanCurrentlyBeUsed();

        Substrat : la ligne `decisionView` du caster, dont `abilities[].usable` EST
        `ActiveAbility$$get_CanCurrentlyBeUsed` (cooldown / munitions) -- la meme lecture que
        `_base._has_valid_targets` et `InspiredToGreatnessPlaybook._active_ability`.

        TRI-ETAT : `None` = PAS MESURE (le caster n'a pas de ligne dans `ctx.units`, ou sa ligne ne
        porte aucune ability). **`False` est une MESURE**, pas un defaut : c'est la branche
        `GetActive(type) == null` du natif, atteinte des que le boss ne porte pas 1194 -- et elle
        rend alors la probabilite MAXIMALE, ce qui est le comportement natif."""
        me = next((u for u in (ctx.units or []) if u.get("id") == ctx.uid), None)
        if me is None:
            return None
        abis = me.get("abilities")
        if not abis:
            return None
        for a in abis:
            if a.get("abilityId") == self._SISTER_ABILITY or a.get("id") == self._SISTER_ABILITY:
                return a.get("usable") is not False   # `get_CanCurrentlyBeUsed`
        return False                                  # `GetActive(0x4aa) == null` -> false (MESURE)

    def use_probability(self, ctx: NCContext) -> float | None:
        """`...NovaChargePlaybook$$GetUseProbability(unit)` -- MIRROR 1:1 :

            return CanCurrentlyUseAbility(unit, 0x4aa) ? Fix64.Half : Fix64.One;

        Les deux statiques sont LUS dans `FixMath.NET.Fix64$$.cctor` (`+0x30` = `1/2`, `+0x20` = `1`),
        pas deduits d'un nom. TRI-ETAT : `None` = PAS MESURE -> `probability_gate` rend `True`
        (degradation PERMISSIVE) ; jamais `0.0`, que le natif ne produit JAMAIS ici."""
        v = self._can_currently_use_sister(ctx)
        if v is None:
            return None
        return _PROB_SHIELD_READY if v else _PROB_SHIELD_SPENT

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`...NovaChargePlaybook$$ShouldEvaluate(unit)` -- la classe SURCHARGE le slot 4 :

            if (!<IBattleQuery slot 27 = HasMinimumRemainingTurns>(unit, 2))  return false;
            return BasePlaybook$$ShouldEvaluate(unit);

        C'est le SEUL des deux gates qui puisse REFUSER (`GetUseProbability` ne rend jamais `<= 0`
        ici). Le second etage reste le foyer commun `probability_gate(self.use_probability(ctx))` --
        on ne recode pas le triage."""
        if not has_minimum_remaining_turns(ctx, _MIN_REMAINING_TURNS):
            return False
        return probability_gate(self.use_probability(ctx))

    # ------------------------------------------------------------------ le corps propre

    def _line_tiles(self, dctx, tile_id: int) -> list:
        """`this.<+0x70>.Select(entities)` = les TROIS lignes paralleles, ancrees sur la tuile visee.

        FOYER PARTAGE avec la face COMBAT (`tau.nova_charge_line_tiles`) : le recopier ferait
        diverger les deux faces sur la geometrie. `FixedTileIds([tileId])` est le vehicule de
        collapse du role `Target`, exactement comme `MacroPlasmaIncineratorPlaybook._area`."""
        return nova_charge_line_tiles(FixedTileIds([int(tile_id)])).select(dctx) or []

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`EvaluateNonComparable` + `Bucket$$ChooseAction` pour une ability TILE-TARGETED.

        Le natif balaie les positions candidates (`ctx.reach_nc`, origine EN TETE) et, par position,
        les cibles eligibles ; `AddAction` ne remplace que sur amelioration STRICTE, donc a utilite
        egale la PREMIERE paire (position, tuile) gagne. La position entre dans la formule par la
        GEOMETRIE (`CasterTile` du sous-arbre), pas par un terme de mouvement : `NovaShieldPlaybook`
        en a deux, celui-ci n'en a AUCUN.

        Le contexte DSL est repositionne par `caster_pos = T` -- c'est le mirror de la
        `UnitPosition` candidate que `CasterTileSelector` resout. Residu `#459-r1` : le port n'en
        garde que la MAIN TILE.

        Contexte DSL indisponible (`Scene` ou board absents) -> `[]` : aucune utilite INVENTEE."""
        from_here, union = eligible_target_tiles(ctx, self.ABILITY_ID)
        if not from_here and not union:
            return []
        dctx = TT.dsl_context_for_tile_target(ctx)
        if dctx is None or getattr(dctx, "board", None) is None:
            return []
        board = dctx.board
        epos = {(p[0], p[1]) for p in (ctx.epos or []) if p and p[0] is not None}
        best = None                                   # (tuile visee, position, utilite)
        for T in (ctx.reach_nc or [ctx.origin]):
            if T is None:
                continue
            dctx_t = dataclasses.replace(dctx, caster_pos=(T[0], T[1]))
            # `fromHere` EST la vue par-position a l'ORIGINE ; ailleurs le RPC n'a que l'union
            # (residu deja nomme par `_base.eligible_target_tiles`).
            cibles = from_here if (T == ctx.origin and from_here) else union
            for tpos in cibles:
                tid = (ctx.tile_id_by_pos or {}).get(tpos)
                if tid is None:
                    continue                          # pas d'entite-tuile -> rien a collapser
                lines = self._line_tiles(dctx_t, tid)
                if not lines:
                    continue                          # `Count == 0` -> utilite 0 < MIN_UTILITY
                # `CountEnemiesOnTiles` : l'OCCUPANT de chaque tuile, compte s'il n'est PAS ami.
                n_enemy = 0
                for t in lines:
                    c = board.coord(int(t))
                    if c is not None and (int(c[0]), int(c[1])) in epos:
                        n_enemy += 1
                u = self._ENEMY_WEIGHT * n_enemy + float(len(lines))
                if best is None or u > best[2]:       # strict > : 1re paire (T, tuile) du max gagne
                    best = (tpos, T, u)
        if best is None or best[2] < self.MIN_UTILITY:
            return []
        tpos, T, u = best
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] NovaCharge tile=%s T=%s u=%s" % (ctx.uid, tpos, T, u),
                  file=sys.stderr)
        tid = (ctx.tile_id_by_pos or {}).get(tpos)
        return [{"target": (tid if tid is not None else tpos), "ability": self.ABILITY_ID,
                 "to": (T if T != ctx.origin else None), "pred": u}]


__all__ = ["NovaChargePlaybook"]
