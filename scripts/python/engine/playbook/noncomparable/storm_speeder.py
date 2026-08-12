"""Les DEUX faces DECISION de `darkaStormSpeeder` (MACHINE OF WAR Dark Angels) -- #967.

`DeathOnTheWind` (1213, DAMAGE/HeavyRound) et `Hailstrike` (1214, DAMAGE/Projectile -- en fait un
BUFF de percage pose sur un ALLIE). Les faces COMBAT des deux sont portees et confrontees depuis
case-117 ; c'est la face DECISION qui manquait, donc l'IA les choisissait avec un scoring qui
n'etait pas celui du natif -- divergence INVISIBLE en replay.

BASE, LUE dans `data/symbols/<build>/frida/classes.tsv` :
`IdunBattle.AI.Playbook.NonComparablePlaybook`1` pour les deux (le `.ctor` de 1213 NOMME
`ComparablePlaybook<...>..ctor` -- corps trivial DEDUPLIQUE, piege #487-r1).

REACHABILITY, LUE dans `metadata/active_playbook_builders.tsv` :
`active 1213 -> ...DeathOnTheWindPlaybook`, `active 1214 -> ...HailstrikePlaybook`.

RECENSEMENT AU BLOC (`probe_967_playbook_blocks.py`) :
  * 1213 : SIX corps contigus -- `EvaluateNonComparable`, `GetCustomUnitOrderUtility`,
    `HasPossibleTarget`, `ShouldEvaluate`, `.cctor`, `.ctor` -- puis `DeathScreamPlaybook`. S'y
    ajoute, dans la region des lambdas, `...DeathOnTheWindPlaybook.<>c__DisplayClass9_0$$
    <HasPossibleTarget>b__0`.
  * 1214 : SIX corps contigus -- `EvaluateNonComparable`, `GetPierceRatioUtility`,
    `GetTargetUtility`, `HasRangedAttackAndCanAttackThisTurn`, `.cctor`, `.ctor` -- puis
    `HammerOfWrathPlaybook`.
Rien de fondu DEDANS pour ni l'une ni l'autre.

`GetCustomUnitOrderUtility` (1213) N'EST PAS portee, et c'est deliberé : elle repond a « dans quel
ORDRE activer mes unites », pas a « quelle action prendre ». Son corps est
`Fix64(vtable[+0x1a8](this, unit) ? -99 : 0)`. Le moteur ne mirrore pas la selection d'unite
(`toActivate` vient du natif), donc la porter n'aurait aucun consommateur -> residu `#967-r1`.
"""
from __future__ import annotations

import gameconfig as _gc

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effects.magnitude import ability_var
from engine.entities.traits.unit_trait import UnitTrait

from . import _targets as TGT      # FORME B (liaison de MODULE)
from ._base import NCContext, NonComparablePlaybook, native_priority, _unit_cfg


# ================================================================================================ #
#  1213 DeathOnTheWind
# ================================================================================================ #

def _line_enemy_count(aim: tuple, direction: tuple, nr_of_tiles: int, enemy_set: set,
                      walkable_at, elevation_at, tile_exists) -> int:
    """`Count( Enemies(Owner@+0x48, Units(GetTilesInLine(Subject@+0x68))) )` -- le nombre d'ennemis
    sur la ligne partant de `aim` dans la direction `direction`.

    `IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$GetTilesInLine(from)`
    (le MEME corps que celui deja mirrore par la face COMBAT
    `engine.runner.abilities.darkangels.death_on_the_wind_get_tiles_in_line`) :

        n        = GetNumberConstant(config@0x60, 0x17 = nrOfTiles)
        settings = new TilesBehindInLineSettings { +0x10 = 0, +0x11 = 1 }
        return     TilesBehindInLine(Target@+0x60, from, settings, Get(n - 1))

    DEUX ECARTS avec `ThriceBlessedConflagration` (1187), meme famille geometrique, et les deux
    changent le compte :
      (a) la ligne est BORNEE a `nrOfTiles - 1` tuiles au-dela de la tuile de la cible (1187 :
          non bornee) ;
      (b) il n'y a **AUCUN `FilterContinuous`** (1187 en a un) -- tous les ennemis presents sur les
          hexes de la ligne comptent, TROUS COMPRIS. C'est la meme lecture que la face COMBAT, qui
          en tire « tous les ennemis PRESENTS sur ces hexes sont frappes, trous compris ».
    Copier la feuille de 1187 serait donc faux sur ces deux axes."""
    line = bq.get_tiles_behind(aim, direction, max_count=max(0, int(nr_of_tiles) - 1),
                               check_walkable=False, update_reference=True,
                               walkable_at=walkable_at, elevation_at=elevation_at,
                               tile_exists=tile_exists)
    return sum(1 for tile in line if tile in enemy_set)   # PAS de `break` : aucun FilterContinuous


def _machine_attack_enemy_count(aim: tuple, nr_of_tiles: int, enemy_set: set,
                                walkable_by_pos: dict | None,
                                elev_by_pos: dict | None) -> int:
    """`|GetMachineAttackTargets(GetMachineAttackTiles())|` -- l'utilite NonComparable d'une cible.

    `IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$GetMachineAttackTiles` :

        ring  = SurroundingTiles(Target@+0x60, includeCenter: 0, radius: 1, 0, 1)
        cnt   = Count( Enemies(Owner@+0x48, Units(GetTilesInLine(Subject@+0x68))) )
        best  = First( SortByFormula(ring, cnt, 0 = DESC), 1 )
        line  = GetTilesInLine(best)
        start = First( SortByDistance( Tiles(Target@+0x60), First(line, 1) ), 1 )
        return  Tiles( start op_Addition line )

    et `...DeathOnTheWindAbility$$GetMachineAttackTargets(tiles)` :

        return Enemies(Owner@+0x48, Units(tiles, unique: 1, 3), 3)

    TROIS REDUCTIONS, les MEMES que celles deja etablies et confrontees par la face COMBAT
    (case-117, #585-r1) : `start` porte sur un SINGLETON (la MainTile de la cible) -> tri et
    `First` sont l'IDENTITE ; le `Tiles(...)` enveloppant est l'identite sur un ensemble deja
    tile-domain ; `Target@+0x60` EST deja tile-domain (`abilityTargets` live rend `kind=tile`).
    L'ensemble se reduit donc a `{tuile de la cible} UNION ligne(best)`.

    Le tri `SortByFormula(..., 0 = DESC)` est STABLE
    (`IdunBattle.Entities.Selectors.SortByFormulaSelector$$Select` -> `OrderByDescending`) : a
    comptes EGAUX c'est l'ordre du `ring` qui tranche, celui de la triple boucle cube de
    `TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext` que `bq.get_surrounding_tiles`
    mirrore.

    ⚠ Le CINQUIEME argument natif de `SurroundingTiles` vaut `1` ici et `0` pour 1187. Le noeud
    DSL porte (`engine.entities.selectors.accessors.SurroundingTiles`) n'expose que
    `(center, radius, include_center)` -- ni la face COMBAT de 1213, ni celle de 1187 ne mappent
    ce dernier octet, et les deux sont confrontees. Il est donc LU et NON MAPPE : residu
    `#967-r2`, nomme plutot que maquille."""
    walkable_at, elevation_at, tile_exists = bq.tiles_behind_accessors(walkable_by_pos, elev_by_pos)
    ring = bq.get_surrounding_tiles(aim, radius=1, include_center=False, check_walkable=True,
                                    walkable_at=walkable_at, elevation_at=elevation_at,
                                    tile_exists=tile_exists)
    # `{tuile de la cible}` : elle entre dans `Units(tiles)` puis `Enemies(...)`, donc elle compte
    # SSI son occupant est un ennemi -- ce qui est le cas nominal (bit `TargetTileHasEnemyUnit`
    # du masque de 1213, cf. la face COMBAT), mais le terme est mirrore et non presume.
    cnt = 1 if aim in enemy_set else 0
    if not ring:
        return cnt
    scored = [(d, _line_enemy_count(aim, d, nr_of_tiles, enemy_set,
                                    walkable_at, elevation_at, tile_exists)) for d in ring]
    scored.sort(key=lambda s: -s[1])                      # SortByFormula DESC, STABLE
    return cnt + scored[0][1]                             # First(1)


class DeathOnTheWindPlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.DeathOnTheWindPlaybook$$EvaluateNonComparable` (0x4bd = 1213).

    LE CORPS, TERME A TERME
    -----------------------
        bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # `.cctor` : Fix64(2)
        foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
            tiles   = <DeathOnTheWindAbility>$$GetMachineAttackTiles(this.ability@+0x68)
            targets = <DeathOnTheWindAbility>$$GetMachineAttackTargets(this.ability, tiles)
            util    = Fix64.op_Implicit( targets.<ITargetsSelector slot 2 = Count>(entities) )
            bucket.AddAction(GenerateAction(casterPosition, entities@+0x10, util))

    ⚠ **LE TERME N'EST PAS CONSTANT SUR LES CIBLES, ET C'EST TOUT LE PIEGE.** `GetMachineAttackTiles`
    et `GetMachineAttackTargets` ne prennent QUE l'ability : on lirait volontiers « arbre construit
    une fois, donc utilite identique partout ». Faux -- l'arbre est un SELECTEUR DSL, et c'est
    `Count(entities)` qui l'EVALUE, `entities` etant le contexte de la cible COURANTE. Les
    referents `Target@+0x60` / `Subject@+0x68` s'y resolvent donc cible par cible. Un terme qu'on
    croit constant sur les cibles doit etre PROUVE constant (le bug de #957) : ici la preuve va
    dans l'autre sens.

    Le slot **2 d'`ITargetsSelector` est `Count` (1 param)** -- `metadata/interface_slots.tsv`,
    pas une deduction de nom (slot 0 = `Select`, 1 = `SelectFirst`).

    UTILITE = **le nombre d'ennemis que le barrage frapperait** si l'ability etait castee sur cette
    tuile. `MIN_UTILITY = 2` (`...DeathOnTheWindPlaybook$$.cctor` : `Fix64.op_Implicit(2)` --
    la SEULE des six a ne pas valoir 1) : l'occupant de la tuile visee comptant deja pour 1, il
    faut donc **au moins un second ennemi aligne** pour que l'IA propose 1213.

    PRIORITY = **1000** (`AbilityPriority.First`, corps `mov eax,0x3E8 ; ret` deduplique, mesure
    #170). Consequence EXERCEE : `darkaStormSpeeder` porte aussi `Hailstrike` (1214), tier 0 --
    1213 est donc evaluee AVANT, et si elle passe son seuil elle GAGNE, quelle que soit l'utilite
    de 1214. C'est de l'ordre de generateur, pas de la comparaison d'utilites.

    LE GATE `ShouldEvaluate`, ET IL EST PROPRE A CETTE CLASSE
    ---------------------------------------------------------
    `...DeathOnTheWindPlaybook$$ShouldEvaluate` (corps PROPRE, pas le corps folde
    `AlphaWarriorPlaybook$$ShouldEvaluate`) :

        if (!UnitExtensions.CanCurrentlyUseAbility(unit, 0x4bd)) return false
        return HasPossibleTarget(this.query@+0x28, this.state@+0x20, unit)

    et `...DeathOnTheWindPlaybook$$HasPossibleTarget(query, state, unit)` :

        tiles = query.<slot itf 66 = GetValidTargets>(unit, UnitPosition.NullPosition(), 0x4bd)
        set   = new OrderedSet<BEntityId>(tiles)
        set.FilterInPlace(t => query.<slot itf 131 = GetAdjacentFriends>(
                                   t, UnitExtensions.GetUnit(t, state)).Count > 0)
        return set.Count > 0

    Les slots 66 et 131 sont LUS dans `metadata/interface_slots.tsv` (`GetValidTargets`/3 params,
    `GetAdjacentFriends`/2 params). `GetAdjacentFriends(t, <occupant de t>)` prend le referent
    d'amitie sur l'OCCUPANT : celui-ci etant un ennemi du caster (bit `TargetTileHasEnemyUnit`),
    « ses amis » sont d'AUTRES ennemis du caster. Le gate est donc : **il existe une tuile ciblable
    ayant au moins un ennemi ADJACENT** -- un pre-filtre de grappe, coherent avec `MIN_UTILITY = 2`
    sans lui etre equivalent (un ennemi a distance 2 sur la ligne donnerait util 2 sans voisin
    adjacent ; le natif refuserait quand meme).

    `CanCurrentlyUseAbility` n'est pas re-teste : `choose_action` filtre deja sur `usable`."""
    ABILITY_ID = int(ActiveAbilityType.DeathOnTheWind)   # 0x4bd = 1213
    MIN_UTILITY = 2.0     # `DeathOnTheWindPlaybook$$.cctor` : `Fix64.op_Implicit(2)`
    PRIORITY = native_priority(int(ActiveAbilityType.DeathOnTheWind))   # 1000 = AbilityPriority.First

    #: `GetNumberConstant(config@0x60, 0x17 = nrOfTiles)` -- CONSTANTE (hors niveau) de 1213.
    VAR_NR_OF_TILES = "nrOfTiles"

    def _nr_of_tiles(self) -> int:
        return int(ability_var(ActiveAbilityType(self.ABILITY_ID).name, self.VAR_NR_OF_TILES,
                               is_constant=True) or 0)

    def should_evaluate(self, ctx: NCContext) -> bool:
        """`...DeathOnTheWindPlaybook$$ShouldEvaluate` -> `HasPossibleTarget` (cf. l'en-tete).

        TRI-ETAT sur `ctx.epos` : canal muet (`None`/vide alors qu'aucun ennemi n'est publie) ->
        `True`. Ce gate REFUSE, donc le gater a l'aveugle supprimerait l'ability entiere -- meme
        arbitrage que `_base._turns_started_gate`."""
        epos = [p for p in (ctx.epos or []) if p and p[0] is not None]
        if not epos:
            return True                                   # canal muet -> on ne gate pas a l'aveugle
        tiles = TGT.eligible_tiles(ctx, self.ABILITY_ID)
        if not tiles:
            return True                                   # cibles non mesurees -> statu quo
        neigh = bq.neigh_map(ctx)
        for pos, _tid in tiles:
            if bq.count_adjacent(pos, epos, ctx.elev_by_pos, neigh) > 0:
                return True
        return False

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        tiles = TGT.eligible_tiles(ctx, self.ABILITY_ID)
        if not tiles:
            return []
        n = self._nr_of_tiles()
        if n <= 0:
            return []                                     # `nrOfTiles` non lisible -> pas de devinette
        enemy_set = {p for p in (ctx.epos or []) if p and p[0] is not None}
        best, scored = None, []
        for pos, tid in tiles:
            if tid is None:
                continue                                  # pas d'entite-tuile -> cible inemissible
            u = float(_machine_attack_enemy_count(pos, n, enemy_set,
                                                  ctx.walkable_by_pos, ctx.elev_by_pos))
            scored.append((tid, pos, u))
            if best is None or u > best[1]:               # `AddAction` : remplacement STRICT
                best = (tid, u)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] DeathOnTheWind target=%s util=%s nrOfTiles=%s scored=%s"
                  % (ctx.uid, best[0], best[1], n, scored), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]


# ================================================================================================ #
#  1214 Hailstrike
# ================================================================================================ #

class HailstrikePlaybook(NonComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.HailstrikePlaybook$$EvaluateNonComparable` (0x4be = 1214).

    LE CORPS, TERME A TERME
    -----------------------
        bucket = new Bucket<UnitAction>(0, Nullable(<statics+0x00>))     # `.cctor` : Fix64(1)
        foreach entities in BasePlaybook.GetEligibleTargetsSelectable(caster, casterPosition):
            util = HailstrikePlaybook$$GetTargetUtility(this, entities@+0x10)
            bucket.AddAction(GenerateAction(casterPosition, entities@+0x10, util))

    `...HailstrikePlaybook$$GetTargetUtility(target)` -- TROIS termes, additionnes :

        bonus = 0
        if (UnitExtensions.HasTrait(target, 0x3eb = UnitTrait.Overwatch))            bonus = 500
        else if (   (UnitExtensions.HasRangedWeapon(target)
                  || UnitExtensions.HasRangedAbility(target, query))
                 && query.<slot itf 56 = CanAttackAnyUnitFromAnyTileWithAnyAbility>(target))
                                                                                    bonus = 500
        pierce = 0
        w = query.<slot 179 = FindRangedWeapon>(target) ?? query.<slot 178 = FindMeleeWeapon>(target)
        if (w != null && w->+0x18 != null)  pierce = 100 - (w->+0x18)->+0x14
        rnd = rng@+0x30.<IPseudoRNG slot 2 = Next>(0, 10)
        return Fix64.op_Implicit(pierce + rnd + bonus)

    (Les deux corps nommes `GetPierceRatioUtility` et `HasRangedAttackAndCanAttackThisTurn`
    existent separement dans le bloc, mais `GetTargetUtility` les INLINE -- c'est le corps inline
    qui est transcrit ci-dessus, lu tel quel.)

    Le `+0x18` d'une arme est son `DamageProfile` et le `+0x14` de celui-ci son `PiercingRatio` --
    la lecture est confirmee par le gameconfig, qui range `PiercingRatio` sous le profil et non
    sous l'arme (`gameconfig.damage_profile("HeavyRound") == {"PiercingRatio": 55}`). L'utilite
    **DECROIT** avec le percage deja possede : Hailstrike buffe le percage, donc l'IA le donne a
    l'allie qui en manque le plus.

    Les slots sont LUS dans `metadata/interface_slots.tsv` : `IBattleQuery` 56
    `CanAttackAnyUnitFromAnyTileWithAnyAbility`/1, 178 `FindMeleeWeapon`/1, 179
    `FindRangedWeapon`/1 ; `IPseudoRNG` 2 `Next`/2. Le champ `+0x30` EST l'`IPseudoRNG` : c'est
    celui que `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluate` passe au slot 4 (`NextBool`)
    pour son tirage de `GetUseProbability`.

    TROIS ECARTS, TOUS NOMMES
    -------------------------
    1. **`rng.Next(0, 10)` N'EST PAS PORTE** -- le port pose ce terme a **0**. Le moteur est
       deterministe et ne mirrore pas le flux `IPseudoRNG` de l'IA ; c'est le meme arbitrage que
       pour `GetUseProbability` (`_base.NonComparablePlaybook.should_evaluate`). Poser 0 est une
       BORNE, pas un ajustement : la moyenne (4,5) serait un fit. Portee de l'ecart, chiffree par
       la structure du score : le terme vaut au plus 9 (ou 10), la ou le bonus vaut 500 -- il ne
       peut donc JAMAIS renverser la classe de bonus, seulement departager deux cibles de meme
       classe dont les `PiercingRatio` different de moins de 10. Residu `#967-r3`.
    2. **`HasRangedAbility(target, query)` n'est pas porte** : le mirror offline n'a pas de lecture
       fiable de « cette unite possede une ability a portee ». Consequence DIRECTIONNELLE : une
       cible sans arme a distance mais avec une ability a distance perd son bonus de 500 dans le
       port. Le premier disjoint (`HasRangedWeapon`, gameconfig) est porte. Residu `#967-r4`.
    3. `CanAttackAnyUnitFromAnyTileWithAnyAbility(target)` est mirrore par la PRESENCE d'un plan
       d'attaque pour la cible dans `ctx.plans` (le plan natif enumere les paires
       (ability, cible) avec leurs tuiles rankees, donc un plan non vide EST « peut attaquer
       quelqu'un depuis quelque part avec quelque chose »). Quand AUCUN plan n'est publie (bridge
       offline : seule l'unite ACTIVE en a un), le conjoint est NON MESURE et le port retient le
       seul premier disjoint -- il ne fabrique pas un `False` qui supprimerait le bonus partout.

    CIBLES : des unites ALLIEES (le buff `Hailstrike_ExtraPierce` 1509 se pose sur elles, cf. la
    face COMBAT `engine/runner/abilities/darkangels.py` et
    `engine/entities/effects/loki/darkangels.py`).

    MIN_UTILITY = 1 (`...HailstrikePlaybook$$.cctor`). PRIORITY = 0 (hors `NATIVE_PRIORITY`)."""
    ABILITY_ID = int(ActiveAbilityType.Hailstrike)   # 0x4be = 1214
    MIN_UTILITY = 1.0     # `HailstrikePlaybook$$.cctor` : `Fix64.op_Implicit(1)`
    PRIORITY = 0          # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    #: `HasTrait(target, 0x3eb)` -- le trait, pas l'ordinal nu.
    TRAIT_OVERWATCH = UnitTrait.Overwatch          # 0x3eb = 1003
    #: la constante `500` du corps natif, pour les DEUX branches.
    RANGED_BONUS = 500.0
    #: `100 - PiercingRatio` : le `100` du corps natif.
    PIERCE_BASE = 100.0
    #: `rng.Next(0, 10)` NON PORTE -- borne basse assumee (#967-r3), jamais la moyenne.
    RNG_TERM = 0.0

    def _visual_id(self, ctx: NCContext, uid: int):
        for u in (ctx.units or []):
            if u.get("id") == uid and u.get("visualId"):
                return u["visualId"]
        for u in (ctx.obs_units or []):
            if u.get("entityId") == uid and u.get("visualId"):
                return u["visualId"]
        return None

    def _pierce_utility(self, visual_id) -> float:
        """`100 - (FindRangedWeapon(target) ?? FindMeleeWeapon(target)).DamageProfile.PiercingRatio`.

        `FindRangedWeapon` = l'arme portant une `Range` ; `FindMeleeWeapon` = celle qui n'en a pas.
        Arme (ou profil) absent -> `0`, exactement comme la branche `w == null` du natif."""
        weapons = _unit_cfg(visual_id).get("weapons") or []
        w = next((x for x in weapons if x.get("Range")), None)
        if w is None:
            w = next((x for x in weapons if not x.get("Range")), None)
        if w is None:
            return 0.0
        prof = w.get("DamageProfile")
        if not prof:
            return 0.0
        ratio = (_gc.damage_profile(prof) or {}).get("PiercingRatio")
        if ratio is None:
            return 0.0
        return self.PIERCE_BASE - float(ratio)

    def _ranged_bonus(self, ctx: NCContext, uid: int, visual_id) -> float:
        """`HasTrait(Overwatch) ? 500 : (HasRangedAttackAndCanAttackThisTurn ? 500 : 0)`."""
        cfg = _unit_cfg(visual_id)
        if self.TRAIT_OVERWATCH.name in (cfg.get("traits") or []):
            return self.RANGED_BONUS
        weapons = cfg.get("weapons") or []
        has_ranged = any(w.get("Range") for w in weapons)
        # `HasRangedAbility` NON PORTE (#967-r4) -- seul le 1er disjoint est mirrore.
        if not has_ranged:
            return 0.0
        if ctx.plans:                       # canal MESURE -> le conjoint mord
            plan = (ctx.plans or {}).get(uid) or {}
            if not any(ev.get("rankCount") for ev in (plan.get("evals") or [])):
                return 0.0
        return self.RANGED_BONUS            # plans non publies -> conjoint NON MESURE

    def generate_candidates(self, ctx: NCContext) -> list[dict]:
        elig = TGT.eligible_units(ctx, self.ABILITY_ID)
        if not elig:
            return []
        best, scored = None, []
        for tid, _pos in elig:
            vid = self._visual_id(ctx, tid)
            u = (self._pierce_utility(vid) + self.RNG_TERM
                 + self._ranged_bonus(ctx, tid, vid))
            scored.append((tid, vid, u))
            if best is None or u > best[1]:               # `AddAction` : remplacement STRICT
                best = (tid, u)
        if best is None or best[1] < self.MIN_UTILITY:
            return []
        if ctx.debug:
            import sys
            print("    [dbg NC u%s] Hailstrike target=%s util=%s scored=%s"
                  % (ctx.uid, best[0], best[1], scored), file=sys.stderr)
        return [{"target": best[0], "ability": self.ABILITY_ID, "to": None, "pred": best[1]}]
