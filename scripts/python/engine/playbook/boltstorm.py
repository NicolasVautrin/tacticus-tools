"""`IdunBattle.AI.Playbook.Loki.BoltstormPlaybook` -- face ATTACK du triggered `Boltstorm` (1090),
passif de `templAggressor` << Burchard >> (HERO) et de 4 npc `templBossAggressor*` : 5 porteurs
DISPATCHES, quatrieme des residus ATTACK de #419-r1.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(35), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae, BarbedOvipositor et Neuroparasite
(`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.BoltstormPlaybook$$CalculateAttackUtilityInStepsInternal` monte la SM
`d__3` -- structure LUE dans le wrapper : `sm@+0x20 = this` (le PLAYBOOK), `sm@+0x28 = case`,
`sm@+0x30 = getUtilityVal` (le delegue scorer, CAPTURE contrairement a `Neuroparasite`). Le corps
est `BoltstormPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`, DEUX etats de
yield :

    weapon = this.<IBattleQuery @playbook+0x60>.FindRangedWeapon(case.Caster);   // slot 0xb3
    if (weapon == null)
        yield return Fix64.op_Implicit(0);                                       // etat 1
    else {
        int range = weapon.Range.Value;                       // `Nullable<int>` @ WeaponProfile+0x24
        var sel = BoltstormAbility.GetAllTargets(this.<DSLFactory @playbook+0x20>,
                                                 DSLFormulas.Direct(range));
        var entities = new AbilityEntities {                  // struct de 0x128 o, memset a 0 d'abord
            Actor = null, Caster = case.Caster, Target = case.Target, Owner = case.Caster };
        int count = sel.Count(entities);                      // vslot 0x18 de `TargetsSelector`
        yield return Fix64.op_Implicit(GetUtilityValue("BOLTSTORM_AdjacentEnemies") * count);
    }                                                                            // etat 2

Cinq lectures qui ne se devinent pas, et dont aucune ne se generalise depuis un voisin de la liste :

1. **La sortie est un PRODUIT poids x CARDINAL**, pas un terme plat. C'est le premier playbook
   attack porte dont la valeur croit avec le nombre de cibles : `local_res8[0] * iVar12` ou
   `local_res8[0]` est le retour du delegue scorer (meme forme d'appel que `BarbedOvipositor` --
   `(**(deleg+0x18))(*(deleg+0x40), <literal de cle>, local_res8, *(deleg+0x28))`, la valeur
   revenant dans `local_res8`) et `iVar12` le retour du vslot `0x18`.

2. **Le `range` vient de l'ARME, pas d'une variable d'ability.** `FindRangedWeapon(unit)` est la
   surcharge a UN argument (identifiee par le proxy
   `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.u003Cu003Ec__DisplayClass213_0$$u003CFindRangedWeaponu003Eb__0`,
   dont tout le corps est cet appel d'interface) : ni distance, ni cible, ni porte de portee -- elle
   rend l'arme de plus longue portee (`SelectMaxRangeWeapon`). Le champ `+0x24` est qualifie par un
   TROISIEME site qui le NOMME : `IdunBattle.Entities.Formulas.AttackWeaponRangeFormula$$Calculate`
   lit le MEME `Nullable<int>` du MEME type (`get_IsMelee ? 1 : Range.Value`). **`weapon == null`
   rend 0** -- un porteur sans arme distance ne vaut rien a ce playbook.

3. **`GetAllTargets` compte la CIBLE PRINCIPALE.**
   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BoltstormAbility$$GetAllTargets(dsl, range)` :

       Target@0x60
       + ( SurroundingEnemies(Owner@0x30, range, unique: 1, unitSelectionType: 3)
           & Unobscured(Owner@0x30, Enemies(Caster@0x48,
                                            AdjacentUnits(Target@0x60, unique: 1, sel: 3), 3)) )

   (mapping `DSLSelectors` : `+0x30 Owner · +0x40 Actor · +0x48 Caster · +0x60 Target`, deja etabli
   par le port -- cf. `runner/abilities/deathguard.py`.) Le `op_Addition` sur le volet gauche fait
   donc que **toute cible vaut deja 1 x le poids**, meme isolee ; le terme n'est jamais nul quand
   l'arme existe. C'est l'ability elle-meme, prise a l'envers : la face COMBAT
   `IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$ExecuteBoltstorm`
   appelle `GetAdditionalTargets` (le MEME arbre SANS `+ Target`) avec `Direct(attackWeapon.Range)`
   -- le playbook estime donc EXACTEMENT le nombre d'unites que le tir va toucher.

4. **Le terme ne depend PAS de la tuile d'attaque balayee.** La struct `AbilityEntities` que le
   playbook construit est memset a 0 puis ne recoit QUE `Caster`, `Target` et `Owner` : `CasterTile`
   (`AbilityEntities+0x40`) et `TargetTile` (`+0x30`) restent NULS, et `case.CasterPosition`
   (`UtilityAttackCase+0x18`) n'est jamais lu. Or `SurroundingEnemies` (surcharge 5 args) et
   `Unobscured` ancrent tous deux sur la MainTile REELLE de leur sujet
   (`EntityExtensions.IterateTiles` / `GetMainTile`) -- meme quirk que
   `IdunBattleLogic.Entities.Abilities.Active.Loki.SavageEchoesAbility$$GetDamage` (#216) et que
   `surrounding_enemies` (#49x). Le terme discrimine donc les CIBLES entre elles, jamais les tuiles
   d'une meme cible. Offsets de la struct lus dans
   `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` (`+0x00 actor · +0x08 caster · +0x10
   target · +0x18 owner · +0x30 targetTile · +0x40 casterTile`).

5. **Le poids est `BOLTSTORM_AdjacentEnemies`** (`Utilities.Default.TriggeredAbilities`), = **10**
   sur le gameconfig courant -- SEULE cle `BOLTSTORM_*` du BC, et le nom dit bien ce que compte
   l'arbre. Le litteral de chaine n'est pas lisible au decompile (cache `DAT_` initialise au
   runtime) : l'identification est par le BC servi, et elle est CONFRONTEE live (le terme observe
   vaut exactement `10 x count`).

## Ce que l'arbre exige d'une cible collaterale (les quatre gates, dans l'ordre natif)

`ennemi du caster` (`Enemies(Caster, ..., 3)`) ET `adjacent a la CIBLE` (`AdjacentUnits(Target)` =
`Units(AdjacentTiles(target))`, donc ring-1 hex AVEC la porte d'elevation `|delta| < 2`
d'`IterateAdjacentTiles`) ET `a distance <= range du CASTER` (`SurroundingEnemies`, disque cube
SANS porte d'elevation) ET `non obscurcie depuis le caster` (`Unobscured` ->
`IdunBattle.Entities.Selectors.UnobscuredEntitiesSelector$$Select` ->
`TargetingQuery.IsTargetUnitObscured` depuis `GetMainTile(caster)`). Les quatre sont des foyers
DEJA partages du port (`battle_query.is_adjacent`, `.surrounding_enemies_in_range`,
`.is_target_tile_obscured`) : aucune copie locale.

Les deux volets du `op_Addition` sont DISJOINTS par construction (`AdjacentUnits(Target)` exclut son
origine), donc la question « union distincte ou concatenation » est sans objet pour le cardinal.

## Face MOVE : `yield Fix64(0)` CONSTANT

`BoltstormPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` est deja
inventorie par #193 comme rendant 0 (les 13 corps MOVE triviaux). Elle n'entre donc pas au registre
`TRIGGERED_MOVE_PLAYBOOKS`, et son absence EST le comportement natif (meme forme que `Lakrimae`,
`BarbedOvipositor` et `Neuroparasite`).
"""
from __future__ import annotations

from engine import battle_query as bq

from . import adjacency as adj          # foyer PARTAGE multi-tuiles + UnitSelectionType (#419-r1-tr10-r2/-r4)
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.unit_selection_type import UnitSelectionType
from ..services.battle_query import find_ranged_weapon

# Cle du poids plat `Utilities.Default.TriggeredAbilities` (delegue `GetUtilityValue`), = 10 sur le
# gameconfig courant. SEULE cle `BOLTSTORM_*` du BC (cf. en-tete, point 5).
_WEIGHT_KEY = "BOLTSTORM_AdjacentEnemies"


def count_all_targets(scene, caster_uid: int, target_uid: int, weapon_range: int) -> int:
    """`BoltstormAbility.GetAllTargets(dsl, Direct(range)).Count(entities)` -- le CARDINAL de l'arbre
    de ciblage, evalue contre l'`AbilityEntities` que le playbook construit (`Caster = Owner =
    case.Caster`, `Target = case.Target`, tout le reste NUL -- cf. en-tete point 4).

    = 1 (le volet `Target` de l'`op_Addition`) + les ennemis du caster, VIVANTS, adjacents a la
    cible, a distance <= `weapon_range` de la tuile REELLE du caster, et non obscurcis depuis elle.

    Degradations, toutes PERMISSIVES-EN-MOINS et nommees : cible absente -> 0 (aucun `Target` a
    compter) ; position du caster ou de la cible inconnue -> le seul volet `Target` (le natif, lui,
    deref sans garde -- il n'a pas de repli a mirrorer). Les unites MORTES sont exclues parce que
    `AdjacentUnits` resout des OCCUPANTS DE TUILE et qu'un mort a quitte la sienne (meme regle que
    `dsl/base.py::_within`, #57m)."""
    if target_uid is None or caster_uid is None:
        return 0
    n = 1                                              # `Target@0x60` (volet gauche de `op_Addition`)
    cpos = scene.pos(caster_uid)
    tpos = scene.pos(target_uid)
    cteam = scene.team(caster_uid)
    if cpos is None or tpos is None or cteam is None:
        return n
    elev = getattr(scene, "elev_by_pos", None)
    neigh = bq.neigh_map(scene)
    # `Enemies(Caster@0x48, ..., 3)` : equipe != celle du caster, vivantes (occupants de tuile).
    foes = []
    for u in (scene.units or ()):
        uid = u.get("id")
        if uid is None or uid == caster_uid or uid == target_uid:
            continue
        # `sel: 3` = `UnitSelectionType.OnlyAliveAndTargetable` : `IsAlive && !HasFlag(Untargetable)`
        # (`UnitExtensions$$MatchesUnitSelectionType`). Le volet `Untargetable` manquait au port
        # (#419-r1-tr10-r4) ; tri-etat -> canal muet = clause degradee en VRAI.
        if not adj.unit_matches(scene, u, UnitSelectionType.OnlyAliveAndTargetable):
            continue
        if u.get("team") == cteam:
            continue
        p = scene.pos(uid)
        if p is not None:
            foes.append((p, uid))
    # `SurroundingEnemies(Owner@0x30, range, unique: 1, sel: 3)` -- disque cube autour de la tuile
    # REELLE du caster, `- Tiles(unit)`, AUCUN `Unobscured` (foyer `battle_query`).
    in_range = bq.surrounding_enemies_in_range(cpos, [p for p, _ in foes], int(weapon_range))
    for p, uid in foes:
        pk = (p[0], p[1])
        if pk not in in_range:
            continue
        # `AdjacentUnits(Target@0x60, unique: 1, sel: 3)` = `Units(AdjacentTiles(target))` : ring-1
        # hex AVEC la porte d'elevation `|delta| < 2` d'`IterateAdjacentTiles`, sur TOUTES les
        # tuiles des deux entites (`AdjacentTilesSelector$$Select` itere `IterateTiles`,
        # #419-r1-tr10-r2). Foyer PARTAGE `playbook.adjacency`.
        if not adj.unit_in_adjacent_tiles(scene, target_uid, uid, elev, neigh):
            continue
        # `Unobscured(Owner@0x30, ...)` depuis `GetMainTile(caster)`.
        if bq.is_target_tile_obscured(cpos, pk, elev):
            continue
        n += 1
    return n


class BoltstormPlaybook:
    """`BoltstormPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1090). Seule la face ATTACK a
    un corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.Boltstorm)     # 1090

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` (cf. en-tete), dans
        l'ORDRE natif : pas d'arme a distance -> 0 ; sinon le poids `BOLTSTORM_AdjacentEnemies`
        MULTIPLIE par le cardinal de `BoltstormAbility.GetAllTargets`.

        `attack_tile` est accepte et IGNORE : la struct `AbilityEntities` du corps natif ne porte NI
        `CasterTile` NI `TargetTile` (memset a 0), et les deux selecteurs geometriques ancrent sur la
        MainTile REELLE -- le terme ne varie donc pas d'une tuile d'attaque a l'autre (en-tete,
        point 4). `prediction` est accepte et IGNORE de meme : le corps ne lit que `case@+0x10`
        (Caster) et `case@+0x20` (Target), jamais `case.DamagePrediction` (`UtilityAttackCase+0x28`)."""
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        weapon = find_ranged_weapon(sc.vis_by_id.get(attacker_uid))
        if weapon is None:
            return 0.0                        # `FindRangedWeapon(caster) == null` -> etat 1
        rng = int(weapon.get("Range") or 0)   # `weapon.Range.Value` (`Nullable<int>` @+0x24)
        n = count_all_targets(sc, attacker_uid, case_tgt_id, rng)
        return float(ctx.wt.triggered(_WEIGHT_KEY)) * n     # `GetUtilityValue(cle) * count`


__all__ = ["BoltstormPlaybook", "count_all_targets"]
