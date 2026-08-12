"""`RadBombardmentPlaybook` (0x45c = 1116, `admecDominus` << Dominus >>) -- face DECISION, #975.

REACHABILITY, LUE ET NON SUPPOSEE
---------------------------------
`data/symbols/rnca9r7q6c/metadata/active_playbook_builders.tsv` :

    active      1116   IdunBattle.AI.Playbook.Loki.RadBombardmentPlaybook
    triggered   1116   IdunBattle.AI.Playbook.Loki.ShrapnelPlaybook

⚠ **L'id 1116 designe DEUX playbooks natifs**, dans DEUX dicts differents : `ActiveAbilityType.
RadBombardment` (ici) et `TriggeredAbilityType.Shrapnel` (`engine/playbook/shrapnel.py`, deja
porte). Il en existe meme une troisieme face, `EffectType.InescapableAccuracy_extraCritDmg`. Le
discriminant est l'ENUM, jamais l'entier -- c'est le piege que `shrapnel.py` documente deja.

BASE DE HIERARCHIE -- `NonComparablePlaybook<T>`, LUE dans `frida/classes.tsv`
------------------------------------------------------------------------------
    IdunBattle.AI.Playbook.Loki.RadBombardmentPlaybook  112  IdunBattle.AI.Playbook.NonComparablePlaybook`1

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.RadBombardmentPlaybook$$EvaluateNonComparable` :

    bucket   = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))    # cctor : Fix64(**2**)
    mainTile = casterPosition.get_MainTile()
    foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, mainTile):
        Fix64.op_Implicit(0)                                   # valeur JETEE (init morte)
        gs    = this@+0x18.@+0x90                              # le contexte DSL
        of    = gs@+0x48                                       # le referent d'equipe (caster)
        tiles = RadBombardmentAbility.GetAffectedTiles(this@+0x68)
        sel   = DSLSelectors.Enemies(gs, of, DSLSelectors.Units(gs, tiles, unique: 1, sel: 3), 3)
        units = TargetsSelector.SelectAllUnits(sel, entities, 3)
        u     = Fix64.op_Implicit( units.<ICollection.get_Count> )
        bucket.AddAction(BasePlaybook.GenerateAction(casterPosition, entities@+0x10, u))
    return bucket

`IdunBattle.AI.Playbook.Loki.RadBombardmentPlaybook$$.cctor` :

    <statics+0x00> = FixMath.NET.Fix64$$op_Implicit(**2**)

TROIS POINTS QUI SE LISENT
---------------------------
1. **`MIN_UTILITY = 2`, pas 1.** Le `.cctor` pose `Fix64.op_Implicit(2)` -- SEUL du lot #975 a ne
   pas valoir 1. Le Dominus n'aime donc pas sa bombe pour un seul ennemi : il lui en faut **au
   moins DEUX** sur la ligne, sinon le bucket est rejete et le fallback Comparable reprend la main.

2. **L'UTILITE EST UN COMPTE NU, SANS COEFFICIENT.** Le corps ne porte NI `op_Multiply` NI
   `op_Addition` -- seulement `Fix64.op_Implicit(count)`. ⚠ Le commentaire du registre
   `_NONCOMPARABLE_ABILITIES` (`engine/entities/abilities/active_ability.py`) annonce
   « (#ennemis dans GetAffectedTiles) **x 2** » : cette citation est **FAUSSE** et corrigee par
   cette tranche. Le `2` qui existe reellement est le `MIN_UTILITY` du `.cctor`, pas un facteur.
   (L'`op_Implicit(0)` en tete de boucle est une initialisation dont le resultat n'est jamais lu :
   le compilateur l'a laissee, elle ne participe a rien.)

3. **LE SELECTEUR EST RE-EVALUE PAR PAIRE, ET C'EST LUI QUI PORTE LA GEOMETRIE.**
   `GetAffectedTiles` ne prend aucun argument : il rend un ARBRE. C'est `SelectAllUnits(sel,
   entities, 3)` qui l'evalue avec l'`AbilityEntities` de la paire courante -- donc avec
   `casterTile@+0x40` et la tuile visee `+0x10`. Le compte change bien d'une tuile d'aim a l'autre.

   `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$GetAffectedTiles`, deja
   porte cote COMBAT (`engine/runner/abilities/admec.py::rad_bombardment_affected_tiles`) :

       line = TilesBehindInLine(from = CasterTile@0x168, to = TargetTiles@0x190,
                                settings{+0x10 = 0 checkWalkable, +0x11 = 1 updateReference},
                                count = AffectedTileAmount())
       rev  = SortReverse(line)
       return rev op_Subtraction Blocking(rev)

   et `...RadBombardmentAbility$$AffectedTileAmount` :

       Sum( Get(1), RoundsStarted(caster@0x160),
            TotalRepairActionsAmount(UnitsWithTrait(Friends(...), 0xc = Mechanic, 3)) )

   `SortReverse` n'a AUCUN observable ici (on compte, on n'ordonne pas) ; `- Blocking(rev)` retire
   les tuiles NON marchables ; `checkWalkable = 0` DESARME aussi la porte d'elevation (elle vit
   dans la branche walkable d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList`), donc la
   ligne traverse les denivelees. Les trois sont mirrores par le foyer PARTAGE
   `engine.battle_query.get_tiles_behind` -- le meme que consomment `DarkTalonStrike`,
   `ExcruciatingFrequencies` et la face COMBAT de 1116.

BORNES DE PORT, toutes nommees
-------------------------------
* **AIM depuis l'ORIGINE seule** (`abilityTargets(...).fromHere`, `kind = "tile"`) : le natif
  balaie AUSSI les tuiles de move. Meme borne, meme raison et meme signe que
  `DarkTalonStrikePlaybook` -- le sweep est origine-first et `Bucket$$AddAction` ne remplace que
  sur amelioration STRICTE, donc le port ne peut que RATER un aim meilleur apres deplacement,
  jamais en inventer un. Residu `#975-r2`.
* `TotalRepairActionsAmount` rend **0** : le compteur `<component>+0xe8` n'est capte par AUCUN
  canal (residu deja documente sur le noeud `TotalRepairActionsAmount`). La longueur vaut donc
  `1 + turnsStarted(caster)` -- EXACTE tant qu'aucun Mechanic ami n'a soigne, ce qui est le regime
  de tout runner frais.
* `turnsStarted` non mesurable (`ctx.scene` absente) -> longueur rabattue au terme `Get(1)` seul,
  soit **1** tuile : borne INFERIEURE stricte (le port sous-compte), jamais une longueur inventee.
* `walkable_by_pos` vide (canal muet) -> `Blocking` ne retire rien : la ligne est plus longue que
  la native, borne SUPERIEURE. Les deux sens sont donc possibles selon le canal muet ; chacun est
  nomme a son site.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, NonComparablePlaybook


def affected_tile_amount(ctx: NCContext) -> int:
    """`...RadBombardmentAbility$$AffectedTileAmount` = `Sum(Get(1), RoundsStarted(caster),
    TotalRepairActionsAmount(amis Mechanic))`.

    `RoundsStarted(<selecteur d'UNE unite>)` = `UnitComponent.turnsStarted@+0x58` du caster (le
    noeud SOMME sur son selecteur, qui ne porte ici que le caster). Meme grandeur que la stat 12
    `TURNS_STARTED` que `_turns_started_gate` lit deja. Le 3e terme rend 0 offline (cf. l'en-tete).

    Plancher `1` = le terme `Get(1)` seul, servi quand `turnsStarted` n'est pas mesurable."""
    n = 1                                          # `Get(1)`
    sc = getattr(ctx, "scene", None)
    if sc is not None:
        ts = sc.turns_started(ctx.uid)             # `RoundsStarted(caster@0x160)`
        if ts is not None:
            n += int(ts)
    return n                                       # `+ TotalRepairActionsAmount(...)` = 0 offline


def affected_tiles(ctx: NCContext, caster_tile: tuple, aim: tuple, n_tiles: int) -> list:
    """`...RadBombardmentAbility$$GetAffectedTiles` en domaine POSITION.

    `TilesBehindInLine(from = casterTile, to = aim, settings{cw = 0, ur = 1}, count = n)` puis
    `SortReverse` (sans observable sur un COMPTE) puis `op_Subtraction Blocking(.)`.

    ⚠ `check_walkable = False` est LU (`*(short*)(settings+0x10) = 0x100` = `+0x10 -> 0`,
    `+0x11 -> 1`) : le gate de tuile d'`IsTileValidForList` est desarme, donc la ligne ne s'arrete
    NI sur une tuile non marchable NI sur une marche d'elevation. C'est `Blocking` -- un FILTRE, pas
    une troncature -- qui retire ensuite les non-marchables. Les deux etages sont distincts et
    les confondre changerait la longueur."""
    walkable_at, _elev_at, tile_exists = bq.tiles_behind_accessors(ctx.walkable_by_pos,
                                                                   ctx.elev_by_pos)
    line = bq.get_tiles_behind(caster_tile, aim, max_count=int(n_tiles),
                               check_walkable=False, update_reference=True,
                               tile_exists=tile_exists)
    wk = ctx.walkable_by_pos or {}
    if not wk:
        return line                                # canal muet -> `Blocking` ne retire rien
    return [t for t in line if wk.get(t, True)]    # `rev op_Subtraction Blocking(rev)`


class RadBombardmentPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.RadBombardmentPlaybook$$EvaluateNonComparable` (0x45c = 1116).

    utilite(tuile visee) = `|Enemies(Units(GetAffectedTiles()))|` = le nombre d'ENNEMIS VIVANTS sur
    la ligne de tir. Compte NU (aucun coefficient) ; `MIN_UTILITY = 2` (le `.cctor`), donc la bombe
    n'est proposee qu'a partir de DEUX ennemis alignes."""
    ABILITY_ID = int(ActiveAbilityType.RadBombardment)   # 0x45c = 1116
    MIN_UTILITY = 2.0     # `...RadBombardmentPlaybook$$.cctor` : `Fix64$$op_Implicit(2)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        """`ActiveAbilityActionGenerator` + `Bucket$$ChooseAction` pour un cast TILE-TARGET.

        Les tuiles d'aim viennent d'`abilityTargets(uid, 1116).fromHere` (`kind = "tile"`) = le
        mirror de `GetEligibleTargetsSelectable(caster, casterPosition.MainTile)` A L'ORIGINE.
        `Bucket$$AddAction` ne remplace que sur `>` STRICT -> keep-first au tie, dans l'ordre
        d'enumeration du selector natif (que `fromHere` preserve, cf. `eligible_target_tiles`)."""
        if ctx.ability_targets is None or ctx.origin is None:
            return []
        at = ctx.ability_targets(ctx.uid, self.ABILITY_ID) or {}
        aims: list = []
        for u in (at.get("units") or []):
            if u.get("unitId") != ctx.uid:
                continue
            for a in (u.get("abilities") or []):
                if a.get("abilityId") != self.ABILITY_ID:
                    continue
                for t in (a.get("fromHere") or []):
                    tile = t.get("tile")
                    if t.get("kind") == "tile" and tile and tile.get("col") is not None:
                        aims.append((tile.get("col"), tile.get("row")))
        if not aims:
            return []
        n_tiles = affected_tile_amount(ctx)
        enemy_set = {p for p in (ctx.epos or []) if p and p[0] is not None}
        best_aim, best_c = None, None
        for T in aims:
            line = affected_tiles(ctx, ctx.origin, T, n_tiles)
            c = sum(1 for t in line if t in enemy_set)   # `|Enemies(Units(tiles))|`
            if best_c is None or c > best_c:             # `>` STRICT : 1re tuile du max gagne
                best_aim, best_c = T, c
        if best_aim is None or best_c < self.MIN_UTILITY:
            return []
        tile_id = (ctx.tile_id_by_pos or {}).get(best_aim)
        if tile_id is None:
            return []                    # pas d'entite-tuile -> la cible n'est pas emettable
        if ctx.debug:
            import sys
            print(f"    [dbg NC u{ctx.uid}] RadBombardment aim={best_aim} n={n_tiles} "
                  f"enemies={best_c} tileId={tile_id}", file=sys.stderr)
        return [{"target": tile_id, "ability": self.ABILITY_ID, "to": None, "pred": float(best_c)}]
