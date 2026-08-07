"""`IdunBattle.AI.Playbook.Loki.ElectroShockPlaybook` -- face ATTACK du triggered `ElectroShock`
(**TriggeredAbilityType 1303**), passif du SUMMON `admecSmnElectropriest` et de 2 npc
(`admecNpc3Electropriest`, `admecNpc3ElectropriestSurv`) : tete des residus ATTACK de #419-r1.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(35), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae, BarbedOvipositor, Neuroparasite, SaviorProtocols,
AvalancheOfMuscle, Boltstorm, FireOfAbsolution, CosmicHorror, LightImUp, RapidFire et
RighteousRepugnance (`utilities/tile.py::evaluate_attack_in_steps`, vslot 3 -- SOMME des yields,
donc un `yield break` sans valeur y est indistinguable d'un `yield 0`).

## L'inventaire des artefacts natifs qui portent le nom `ElectroShock` (SIX, un seul est porte ici)

Un id ne designe rien a lui seul, et le nom non plus. Sur ce build :

    IdunBattle.AI.Playbook.Loki.ElectroShockPlaybook$$CalculateAttackUtilityInStepsInternal   <- CE MODULE
    IdunBattle.AI.Playbook.Loki.ElectroShockPlaybook$$CalculateMovementUtilityInStepsInternal (yield 0, cf. bas)
    IdunBattle.AI.Playbook.Loki.ElectroShock_NormalAttackPlaybook$$.ctor        (playbook de l'ACTIVE 1178)
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.ElectroShockAbility$$CreateTrigger
    IdunBattleLogic.Entities.Abilities.Active.Loki.ElectroShock_NormalAttackAbility$$GetCustomNormalAttackBehaviour
                                                  ...$$PossibleTargets / ...$$GetAttackDamage
    (+ les `IdunBattle.View.AbilityConfigs.Loki.ElectroShock*Visuals`, hors perimetre moteur)

Homonymie d'id : `EffectType` **1303** = `WrathfulDevotionKilled_Visual`, sans aucun rapport ; il
n'existe PAS d'`ActiveAbilityType` 1303. L'attaque normale du porteur, elle, vit sous
`ActiveAbilityType` **1178** = `ElectroShock_NormalAttack` (deja au registre `ABILITY_ATTACK_TYPE`).
Ce module ne porte QUE la face ATTACK du playbook triggered 1303 ; le triggered n'a NI
`TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` (ce sont les donnees du registre `ABILITY_CLASSES`,
reserve aux abilities ACTIVES -- `ElectroShockAbility` est declenchee, jamais castee).

## Le corps natif, remis en C#

`ElectroShockPlaybook$$CalculateAttackUtilityInStepsInternal` monte la SM `d__3`. Disposition LUE
DANS LE WRAPPER, jamais par analogie avec un voisin -- elle DIFFERE de celle de `FireOfAbsolution`
(`d__4`, ou `sm@+0x20` porte le CASE et `sm@+0x28` le playbook), et coincide avec celle de
`Boltstorm` :

    sm@+0x10 = state    sm@+0x18 = current (Fix64)
    sm@+0x20 = this (le PLAYBOOK)    sm@+0x28 = case    sm@+0x30 = getUtilityVal

Le corps est `ElectroShockPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`,
**UN seul etat de yield**, et une SORTIE ANTICIPEE SANS VALEUR :

    var enemies = this.<IBattleQuery @playbook+0x60>
                      .GetAdjacentEnemies(case.Target, case.Caster, ignoreSteppables: false); // slot 0x7f
    if (enemies.Count == 0)
        yield break;                                    // AUCUN yield -- pas meme un 0
    yield return Fix64.op_Implicit(
        GetUtilityValue("ElectroShock_TargetHasAdjacentEnemy"));                              // etat 1

Cinq lectures qui ne se devinent pas, et dont aucune ne se generalise depuis un voisin de la liste :

1. **La sortie est un BOOLEEN x poids, PAS un produit poids x cardinal.** Le cardinal est calcule
   (`FUN_180002590(0, <ICollection>, list)` = le vslot `get_Count`) mais il n'est **jamais
   multiplie** : il ne sert qu'au test `== 0`. C'est le piege exact de ce filon -- `Boltstorm`
   (#446), `FireOfAbsolution` (#419-r1) et `RighteousRepugnance` (#419-r1-tr10) comptent tous des
   voisins de la cible avec le MEME helper `get_Count`, et tous les trois MULTIPLIENT. Ici l'octet
   qui suit l'appel n'est pas un `imul` mais un `test/jz`. Une recopie par analogie aurait rendu
   `50 x n` la ou le natif rend `50`.
   La raison est LISIBLE dans l'ability prise a l'envers (cf. plus bas) : le splash ne touche
   qu'**UNE** unite (`PickRandomly(..., 1, ...)`), donc la valeur ne croit pas avec le nombre de
   voisins. Le nom de la cle du BC dit exactement cela : `TargetHasAdjacentEnemy`.

2. **`yield break`, pas `yield 0`.** Quand `Count == 0`, `MoveNext` rend `false` **sans** avoir
   ecrit `current` -- l'enumeration est VIDE. Le dispatcher `TriggeredAbilitiesUtility` SOMME les
   yields, donc c'est observationnellement `0.0` et le port rend `0.0` ; la distinction est notee
   parce qu'elle ne serait PAS neutre sous un agregateur qui moyenne (la famille `LightImUp`).

3. **L'ancre geometrique est la CIBLE, et le camp se lit sur le CASTER.** Le slot recoit
   `(case.Target, case.Caster, false)` -- `UtilityAttackCase@+0x20` puis `@+0x10`, offsets LUS dans
   `IdunBattle.AI.Utilities.UtilityAttackCase$$.ctor` (`+0x10 caster · +0x18 casterPosition ·
   +0x20 target · +0x28 damagePrediction · +0xd0 heal · +0xdc repair · +0xe8 effectType ·
   +0xf0 abilityType`). `case.CasterPosition` n'est JAMAIS lu et la SM ne capture aucune tuile : le
   terme discrimine les CIBLES entre elles, jamais les tuiles d'une meme cible. `prediction`
   (`+0x28`) n'est pas lu non plus.

4. **`ignoreSteppables: false`** (le 6e argument litteral `0` de l'appel d'interface) : les unites
   `Steppable` (objets/leurres traversables) COMPTENT. Meme litteral que `FireOfAbsolution`.

5. **Le poids est `ElectroShock_TargetHasAdjacentEnemy` = 50** sur le gameconfig courant, SEULE cle
   `ELECTRO*` de `Utilities.Default.TriggeredAbilities`. Le litteral de chaine n'est pas lisible au
   decompile (cache `DAT_` initialise au runtime) : l'identification passe par le BC servi, et elle
   est CONFRONTEE live.

## Le slot 0x7f, identifie par le proxy NOMME (et par un second site deja porte)

`DAT_1833407b0` est le cache de classe d'`IBattleQuery`. Le decorateur
`IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery` re-appelle l'inner par le MEME
index d'interface depuis des lambdas NOMMEES, dont le corps entier est cet appel -- releve sur CE
build (`rnca9r7q6c`), pas herite :

    DisplayClass151 <GetAdjacentUnits>b__0    -> slot 0x7c
    DisplayClass152 <GetAdjacentEnemies>b__0  -> slot 0x7d   (ref, int, bool)   <- FireOfAbsolution
    DisplayClass153 <GetAdjacentEnemies>b__0  -> slot 0x7e   (ref, int, bool)
    DisplayClass154 <GetAdjacentEnemies>b__0  -> slot 0x7f   (ref, ref, bool)   <- CE MODULE
    DisplayClass155 <GetAdjacentEnemies>b__0  -> slot 0x80   (ref, ref, bool)

⚠ L'inventaire de `docs/rl/case-243-targeting-adjacency.md` (build ANTERIEUR) donnait
`DisplayClass151..154 = GetAdjacentEnemies` ; sur `rnca9r7q6c` le 151 est `GetAdjacentUnits`. Le
verdict « 0x7f = GetAdjacentEnemies » est le meme des deux cotes, mais la table a ete **re-derivee**
plutot que recopiee -- c'est exactement l'ambiguite d'ancrage a +/-1 slot que signale
`docs/rl/case-343-cible-tuile-emise.md` §6.

L'arite tranche la paire `int` (0x7d/0x7e, playerId entier) de la paire `ref` (0x7f/0x80, qui
DERIVE le playerId de l'unite passee en 2e argument). C'est la SEULE difference entre ce site et
celui de `FireOfAbsolution` : `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies` (variante
`ref`) commence par `unit.GetComponent<OwnerComponent>().CurrentPlayerEntityId` avant de rejoindre
le MEME `GetAdjacentUnits` -> `GetUnitsOnTiles` -> `CountOrGetUnitsOnTiles`. Les deux sites
convergent donc sur le meme foyer, d'ou la reutilisation ci-dessous.

Le `get_Count` est le MEME helper au MEME cache que celui de `FireOfAbsolution`
(`FUN_180002590(0, DAT_183364c10, list)`), qui l'y consomme comme cardinal d'un produit -- c'est
cette identite qui qualifie le vslot 0 comme `get_Count` et non comme un `GetEnumerator`.

## Ce que compte `CountOrGetUnitsOnTiles` (lu integralement, cf. `fire_of_absolution`)

    foreach (tile in IterateAdjacentTiles(from, onlyEmptyOrSteppable: false,
                                          onlyWalkableTiles: true, allowTemporary: true)) {
        var unit = UnitExtensions.GetUnit(tile, state);        // L'OCCUPANT de la tuile
        if (unit == null) continue;
        if (ignoreSteppables && UnitExtensions.IsSteppable(unit)) continue;   // ici: false
        if (enemiesOf != null && !UnitExtensions.IsEnemy(unit, enemiesOf, state)) continue;
        ...
    }

ring-1 AVEC la porte d'elevation `abs(dElev) < 2` d'`IterateAdjacentTiles` (foyer
`battle_query.is_adjacent`) ; un occupant par tuile, donc les morts ne comptent pas ; et la CIBLE ne
se compte jamais -- non par un test, mais parce qu'elle n'est pas adjacente a elle-meme.

## L'ability prise a l'envers -- pourquoi le terme est PLAT

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ElectroShockAbility$$CreateTrigger` :
`On(0xf) & OwnerIsCaster`, ou `0xf` = `IdunBattle.DSL.EventTriggerType.DamageTaken` -- le passif
part quand une attaque de son porteur inflige des degats.

`IdunBattleLogic.Entities.Abilities.Active.Loki.ElectroShock_NormalAttackAbility$$GetCustomNormalAttackBehaviour`
(mold de l'ACTIVE 1178, le meme arbre que son `$$PossibleTargets`) :

    If( IsMeleeAttack,
        AttackWithAttackDamage(
            Caster@0x48,
            PickRandomly( Damageable( Enemies(Caster@0x48,
                                              AdjacentUnits(Target@0x60, unique: 1, sel: 3), 3) ),
                          count: 1, 0, 0x7fffffff, false ),
            PercentageOf( StatAmount(Owner@0x30, ...), Direct(GetNumberConstant(0x3b)), 0 ),
            GetDamageProfile(), GetHits(), ... ) )

**`count: 1`** : l'arc electrique saute sur UNE SEULE unite, tiree au sort parmi les ennemis
adjacents a la cible. D'ou un playbook qui ne demande que « y en a-t-il au moins un ». Deux ecarts
NATIFS entre les deux corps, assumes et non mirrorables l'un dans l'autre (ils sont lus separement
et ne partagent aucun selecteur) : le playbook n'applique NI le filtre `Damageable`, NI le gate
`IsMeleeAttack` de la face combat. Un porteur qui attaque a distance, ou dont le seul voisin de
cible est non-damageable, marque quand meme ses 50 points.

## Face MOVE : `yield Fix64(0)` CONSTANT -- ce n'est PAS un residu

⚠ `probe_419_triggered_playbook_inventory.py` classe cette face `SM`, ce qui dit seulement qu'un
corps EXISTE. Il a ete LU :
`ElectroShockPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` n'a qu'un
etat, et cet etat est `Fix64.op_Implicit(0)` ; aucun champ de la SM n'est meme lu. Elle n'entre donc
PAS dans `TRIGGERED_MOVE_PLAYBOOKS`, et **son absence EST le comportement natif** (meme forme que
`Lakrimae`, `BarbedOvipositor`, `Neuroparasite`, `Boltstorm` et `FireOfAbsolution`).
"""
from __future__ import annotations

from ..entities.triggered_ability_type import TriggeredAbilityType
from .fire_of_absolution import count_adjacent_by_camp

# SEULE cle `ELECTRO*` de `Utilities.Default.TriggeredAbilities`, = 50 sur le gameconfig courant.
# Le nom porte la semantique exacte du corps : un BOOLEEN sur la cible, pas un compte.
_WEIGHT_KEY = "ElectroShock_TargetHasAdjacentEnemy"


class ElectroShockPlaybook:
    """`ElectroShockPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1303). Seule la face ATTACK
    a un corps utile ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.ElectroShock)     # 1303

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` (cf. en-tete) :
        `ElectroShock_TargetHasAdjacentEnemy` si la CIBLE a au moins un ennemi du caster adjacent,
        `0.0` sinon (le natif, lui, ne yield RIEN dans ce cas -- indistinguable sous la SOMME du
        dispatcher).

        Le cardinal vient du MEME foyer que `FireOfAbsolution` : les deux sites appellent la meme
        `BattleQuery$$GetAdjacentEnemies` -> `CountOrGetUnitsOnTiles` sur le ring-1 de `case.Target`
        avec le camp du `case.Caster` ; ils ne different que par la surcharge qui porte ce camp
        (slot 0x7f, qui DERIVE le playerId de l'unite, contre slot 0x7d qui le recoit deja resolu).
        Aucune copie locale de la geometrie.

        `attack_tile` est accepte et IGNORE : le slot est ancre sur `case.Target` et
        `case.CasterPosition` (`UtilityAttackCase@+0x18`) n'est jamais lu -- le terme ne varie pas
        d'une tuile d'attaque a l'autre. `prediction` est accepte et IGNORE de meme : le corps ne lit
        que `case@+0x10` (Caster) et `case@+0x20` (Target), jamais `case.DamagePrediction` (`+0x28`).
        """
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        # `count_adjacent_by_camp` rend `(amis, ennemis)` d'un seul balayage ; ce corps-ci ne
        # consomme QUE le volet ENNEMIS -- le natif n'appelle pas `GetAdjacentFriends`.
        _n_friend, n_enemy = count_adjacent_by_camp(sc, attacker_uid, case_tgt_id)
        if n_enemy == 0:
            return 0.0                       # `if (enemies.Count == 0) yield break;`
        return float(ctx.wt.triggered(_WEIGHT_KEY))


__all__ = ["ElectroShockPlaybook"]
