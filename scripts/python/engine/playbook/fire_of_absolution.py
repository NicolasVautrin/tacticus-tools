"""`IdunBattle.AI.Playbook.Loki.FireOfAbsolutionPlaybook` -- face ATTACK du triggered
`FireOfAbsolution` (**TriggeredAbilityType 1017**), passif des quatre `adept*Retributor`
(`adeptRetributor` + 3 npc `adeptBossRetributor` / `adeptBossRetributorLHE` /
`adeptNpcRetributor`) : cinquieme des residus ATTACK de #419-r1.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(35), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae, BarbedOvipositor, Neuroparasite, SaviorProtocols,
AvalancheOfMuscle et Boltstorm (`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

## L'HOMONYMIE 1017 -- trois enums, trois abilities SANS RAPPORT

`1017` n'identifie rien a lui seul. Sur ce build (`data/symbols/<build>/frida/enums.tsv`) :

    IdunBattle.Entities.Enum.TriggeredAbilityType  1017 = FireOfAbsolution     <- CE MODULE
    IdunBattle.Entities.Enum.ActiveAbilityType     1017 = FragBomb
    IdunBattle.Entities.Enum.EffectType            1017 = ActOfFaith_Effect

Le `1017` que cite `docs/rl/case-249-tile-has-enemy-unit.md` (regle de ciblage
`TargetTileHasEnemyUnit`, bit 19) et `docs/rl/case-astramilitarum-fragbomb-basilisk.md` est
l'**ActiveAbilityType FragBomb**, une ability ACTIVE avec son `TARGETING_OPTIONS` -- rien de ce qui
est ici n'etait donc « deja porte ». Le playbook triggered 1017 n'a NI `TARGETING_OPTIONS` NI
`ABILITY_ATTACK_TYPE` : ce sont les donnees du registre `ABILITY_CLASSES` (abilities ACTIVES), et
`FireOfAbsolutionAbility` est declenchee (`CreateTrigger`, cf. plus bas), jamais castee.

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.FireOfAbsolutionPlaybook$$CalculateAttackUtilityInStepsInternal` monte
la SM `d__4` -- disposition LUE DANS LE WRAPPER, jamais par analogie avec un voisin (elle DIFFERE de
celle de `Boltstorm`, ou `sm@+0x20` porte le playbook et `sm@+0x28` le case) :

    sm@+0x10 = state      sm@+0x18 = current (Fix64)
    sm@+0x20 = case       sm@+0x28 = this (le PLAYBOOK)      sm@+0x30 = getUtilityVal

Le corps est `FireOfAbsolutionPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__4$$MoveNext`,
**un SEUL etat de yield** (aucune sortie anticipee : toute degradation tombe dans le
`FUN_1801f51f0` de fin, cf. « degradations » plus bas) :

    var owner    = case.Caster.GetComponent<OwnerComponent>();
    int playerId = owner.CurrentPlayerEntityId;
    var query    = this.<IBattleQuery @playbook+0x60>;

    var friends  = query.GetAdjacentFriends(case.Target, playerId);          // slot 0x81
    int wFriend  = GetUtilityValue("FIREOFABSOLUTION_AdjacentFriend");       // -20
    int a        = friends.Count * wFriend;

    var enemies  = query.GetAdjacentEnemies(case.Target, playerId, false);   // slot 0x7d
    int wEnemy   = GetUtilityValue("FIREOFABSOLUTION_AdjacentEnemy");        //  20
    yield return Fix64.op_Implicit(enemies.Count * wEnemy + a);

Six lectures qui ne se devinent pas, et dont aucune ne se generalise depuis un voisin de la liste :

1. **La sortie est une SOMME DE DEUX produits poids x cardinal, de SIGNES OPPOSES.** Les cinq
   voisins portes avant lui different tous de forme (terme plat, litteral constant, produit unique,
   prediction lue du case, prediction fabriquee) ; `Boltstorm` etait le premier produit
   poids x cardinal, celui-ci est le premier a en sommer DEUX -- et le premier dont un terme est
   **negatif**. Le playbook peut donc rendre une utilite < 0, ce qu'aucun autre du registre ne fait.

2. **L'ancre geometrique est la CIBLE, pas la tuile d'attaque.** Les deux slots recoivent
   `case.Target` (`UtilityAttackCase@+0x20`) ; `case.CasterPosition` (`+0x18`) n'est jamais lu, et
   la SM ne capture aucune tuile. Le terme discrimine donc les CIBLES entre elles, jamais les tuiles
   d'une meme cible -- meme quirk que `Boltstorm`, pour une raison DIFFERENTE (la, une struct
   `AbilityEntities` memset a 0 ; ici, l'argument est litteralement l'entite cible).

3. **Le camp se lit sur le CASTER, via le composant ECS.** `playerId` vient de
   `IdunBattle.Entities.Components.OwnerComponent$$get_CurrentPlayerEntityId` applique au
   `case.Caster` (`+0x10`) -- « amis » et « ennemis » sont donc relatifs au **porteur du passif**,
   pas au proprietaire de la cible.

4. **Le CASTER LUI-MEME COMPTE parmi les amis.** Le natif n'oppose AUCUN retrait au resultat du slot
   0x81 : ni `op_Subtraction`, ni `Remove`, ni test `!= case.Caster`. C'est une divergence assumee
   avec la face COMBAT de la meme ability, qui EXCLUT explicitement le caster de son splash
   (`FireOfAbsolutionAbility$$CreateBehaviour` : `AdjacentUnits(Target) - Caster@0x48 - Target@0x60`).
   La famille MOVE, elle, retire bien le sien (`AdjacentUnitPreference...d__1` : « MINUS self ») --
   ce n'est donc pas une constante de la couche playbook, mais une lecture par corps.
   Consequence mesurable : un `adeptRetributor` qui tire sur une cible ADJACENTE se compte lui-meme,
   et s'inflige -20.

5. **`ignoreSteppables: false`** au call-site de `GetAdjacentEnemies` (le 6e argument litteral `0` de
   l'appel d'interface) : les unites `Steppable` (objets/decoys traversables) **COMPTENT**.
   `GetAdjacentFriends` n'a pas ce parametre et laisse le champ a `false` de meme.

6. **Les poids sont deux cles distinctes de `Utilities.Default.TriggeredAbilities`**,
   `FIREOFABSOLUTION_AdjacentFriend` = **-20** et `FIREOFABSOLUTION_AdjacentEnemy` = **20** sur le
   gameconfig courant : les SEULES cles `FIREOFABSOLUTION_*` du BC. Les litteraux de chaine ne sont
   pas lisibles au decompile (caches `DAT_` initialises au runtime) ; l'appariement cle <-> terme
   n'est PAS un pari sur l'ordre, il est **force par la semantique du slot** -- le poids negatif est
   consomme par le compte du slot 0x81 (`GetAdjacentFriends`) et le positif par celui du slot 0x7d
   (`GetAdjacentEnemies`), identifies chacun par le proxy nomme correspondant (cf. ci-dessous). Il
   est en outre CONFRONTABLE : tout montage a `nFriends != nEnemies` distingue les deux
   appariements.

## Les deux slots d'interface, identifies par le proxy NOMME

`DAT_1833407b0` est le cache de classe d'`IBattleQuery` (meme DAT que `Boltstorm`, dont le slot
0xb3 = `FindRangedWeapon` est deja porte). Les slots se lisent sur
`IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery`, dont chaque lambda
`u003Cu003Ec__DisplayClassNNN_0$$u003C<Methode>u003Eb__0` a pour corps entier l'appel d'interface :

    DisplayClass152 <GetAdjacentEnemies>b__0 -> slot 0x7d   (ref, int, bool)   <- CE MODULE
    DisplayClass153 <GetAdjacentEnemies>b__0 -> slot 0x7e   (ref, int, bool)
    DisplayClass154/155 <GetAdjacentEnemies> -> 0x7f / 0x80 (ref, ref, bool)
    DisplayClass156 <GetAdjacentFriends>b__0 -> slot 0x81   (ref, int)         <- CE MODULE
    DisplayClass157 <GetAdjacentFriends>b__0 -> slot 0x82   (ref, int)
    DisplayClass158/159 <GetAdjacentFriends> -> 0x83 / 0x84 (ref, ref)

Ce sont **les deux memes slots** que la face MOVE de la famille `AdjacentUnitPreference`
(`adjacent_unit_preference.py`, ou 0x81/0x7d sont ancres sur la TUILE candidate). L'arite tranche
la paire `int` (0x7d/0x81, playerId entier) contre la paire `ref` (0x7f-0x80 / 0x83-0x84, qui
DERIVENT le playerId d'une unite passee en argument).

⚠ Chaque paire `int` contient encore deux surcharges, l'une prenant UNE entite et l'autre un
`IEnumerable`. Le choix est **sans effet observable** : `IdunBattle.Core.Services.BattleQuery$$
GetAdjacentUnits` (variante collection) fait `foreach (e in from) IterateAdjacentTiles(e)`, ce qui
sur un singleton rend exactement l'ensemble de la variante unitaire. Le call-site passe une entite
unique (`case.Target`), donc la question ne se pose que sur le papier.

## Ce que les deux slots calculent, jusqu'a la feuille

`GetAdjacentFriends(from, playerId)` et `GetAdjacentEnemies(from, playerId, ignoreSteppables)`
convergent tous deux vers `IdunBattle.Core.Services.BattleQuery$$CountOrGetUnitsOnTiles`, lu
integralement :

    foreach (tile in IterateAdjacentTiles(from, onlyEmptyOrSteppable: false,
                                          onlyWalkableTiles: true, allowTemporary: true)) {
        var unit = UnitExtensions.GetUnit(tile, state);           // L'OCCUPANT de la tuile
        if (unit == null) continue;
        if (ignoreSteppables && UnitExtensions.IsSteppable(unit)) continue;
        if (friendsOf != null && !UnitExtensions.IsFriend(unit, friendsOf, state)) continue;
        if (enemiesOf != null && !UnitExtensions.IsEnemy(unit, enemiesOf, state)) continue;
        ...                                                        // Add / count++
    }

Trois consequences pour le port :

* **ring-1 avec la porte d'elevation.** `IterateAdjacentTiles` applique le gate INCONDITIONNEL
  `abs(elev(a) - elev(b)) < 2` (`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003E
  d__8$$MoveNext`). Foyer DEJA porte et mesure : `battle_query.is_adjacent` -- **0 faux sur 4 963
  paires** de voisinage natif sur trois boards (#271). `hexgeo.distance == 1` seul SUR-COMPTE.
* **un occupant par tuile, et les morts ne sont sur aucune.** Le filtre est `GetUnit(tile)`, pas une
  liste d'unites : un mort a quitte sa tuile (meme regle que `dsl/base.py::_within`, #57m, et que
  `boltstorm.count_all_targets`).
* **la CIBLE ne se compte jamais** -- non par un test, mais parce qu'elle n'est pas sur une tuile
  adjacente a elle-meme (`is_adjacent` rend `False` a distance 0). Le port ne pose donc AUCUN gate
  explicite dessus : ce serait ajouter une regle que le natif n'a pas.

## L'ability, prise a l'envers (pourquoi le poids ami est negatif)

`IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateTrigger` :
`On(0x4a, true) & OwnerIsActor & IsRangedAttack` -- elle se declenche sur l'attaque a DISTANCE de son
porteur. `...$$CreateBehaviour` :

    AttackWithAttackDamage(caster,
                           AdjacentUnits(Target@0x60, unique: 0, sel: 3) - Caster@0x48 - Target@0x60,
                           Direct(GetVariableForLevel(0xb)), GetDamageProfile(),
                           GetNumberConstant(0x2f), ...)
    & Maybe(tile => AddEffect(5, abilityState, tile, null),
            AdjacentTiles(Target@0x60), GetNumberConstant(0x2a))
    & Inform(0xb3, EntityId(Target@0x60))

Le splash frappe **toutes** les unites adjacentes a la cible, ALLIEES COMPRISES (le selecteur ne
filtre pas par camp -- il ne retire nommement que le caster et la cible). C'est exactement ce que le
playbook chiffre : +20 par ennemi qui sera touche, -20 par ami qui le sera. Le decalage du point 4
(le caster compte cote playbook alors que le behaviour l'exclut) est un ecart NATIF, pas une erreur
de lecture : les deux corps sont lus separement et ne partagent pas ce selecteur.

## Face MOVE : `yield Fix64(0)` CONSTANT -- ce n'est PAS un residu

⚠ L'inventaire `probe_419_triggered_playbook_inventory.py` classe cette face `SM` (machine a etats),
ce qui dit seulement qu'un corps EXISTE -- pas qu'il calcule quelque chose. Il a ete LU :
`FireOfAbsolutionPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__3$$MoveNext` n'a qu'un
etat, et cet etat est `Fix64.op_Implicit(0)`. Aucun champ de la SM n'est meme lu.

Elle n'entre donc PAS dans `TRIGGERED_MOVE_PLAYBOOKS`, et **son absence EST le comportement natif**
(meme forme que `Lakrimae`, `BarbedOvipositor`, `Neuroparasite` et `Boltstorm`) : il n'y a rien a
porter et aucun residu a nommer sur cet axe.
"""
from __future__ import annotations

from .. import battle_query as bq

from ..entities.triggered_ability_type import TriggeredAbilityType

# Les deux SEULES cles `FIREOFABSOLUTION_*` de `Utilities.Default.TriggeredAbilities` : -20 et 20 sur
# le gameconfig courant. L'appariement cle <-> slot est force par la semantique du slot (cf. en-tete
# point 6), pas par l'ordre des caches `DAT_` du decompile.
_WEIGHT_FRIEND = "FIREOFABSOLUTION_AdjacentFriend"     # slot 0x81 `GetAdjacentFriends`, = -20
_WEIGHT_ENEMY = "FIREOFABSOLUTION_AdjacentEnemy"       # slot 0x7d `GetAdjacentEnemies`, =  20


def count_adjacent_by_camp(scene, caster_uid: int, target_uid: int) -> tuple:
    """`(|GetAdjacentFriends(target, playerId)|, |GetAdjacentEnemies(target, playerId, false)|)`.

    Un SEUL balayage pour les deux slots : ils ne different que par le filtre de camp de
    `CountOrGetUnitsOnTiles` (`IsFriend` vs `IsEnemy` contre la MEME entite joueur), et parcourent le
    MEME ring-1 de la cible. Les separer dupliquerait la geometrie sans rien porter de plus.

    Le camp est lu sur `scene.team` : c'est le substrat que tout le port utilise pour
    `IsFriend`/`IsEnemy` (cf. `boltstorm.count_all_targets`, `adjacent_unit_preference`). Le natif
    compare l'ENTITE JOUEUR (`CurrentPlayerEntityId` du caster) ; les deux coincident sur les duels
    que le harnais monte (un joueur = une team).

    ⚠ Le CASTER n'est PAS exclu (en-tete point 4) : s'il est adjacent a sa propre cible, il entre
    dans le compte des amis. C'est le natif, pas un oubli.

    Degradations, toutes nommees et rendant `(0, 0)` -- le natif, lui, n'a AUCUNE sortie anticipee :
    il deref sans garde et tombe sur `FUN_1801f51f0` (levee) si le composant ou la cible manque. On
    ne mirror pas une levee : cible ou caster inconnu -> aucun terme, meme degradation que l'absence
    du playbook au registre."""
    if target_uid is None or caster_uid is None:
        return (0, 0)
    tpos = scene.pos(target_uid)
    cteam = scene.team(caster_uid)
    if tpos is None or cteam is None:
        return (0, 0)
    elev = getattr(scene, "elev_by_pos", None)
    neigh = bq.neigh_map(scene)
    n_friend = 0
    n_enemy = 0
    for u in (scene.units or ()):
        uid = u.get("id")
        # Occupants de tuile UNIQUEMENT (`GetUnit(tile)`) : un mort a quitte la sienne. Aucun test
        # `uid != target_uid` : la cible est a distance 0 d'elle-meme, donc jamais `is_adjacent`.
        if uid is None or not u.get("alive"):
            continue
        p = scene.pos(uid)
        if p is None or not bq.is_adjacent(tpos, p, elev, neigh):
            continue
        if u.get("team") == cteam:
            n_friend += 1                 # `IsFriend(unit, playerOf(caster))`
        else:
            n_enemy += 1                  # `IsEnemy(unit, playerOf(caster))`
    return (n_friend, n_enemy)


class FireOfAbsolutionPlaybook:
    """`FireOfAbsolutionPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1017). Seule la face
    ATTACK est portee ; la face MOVE a un corps propre NON porte (residu, cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.FireOfAbsolution)     # 1017

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__4$$MoveNext` (cf. en-tete) :

            wFriend * |amis du caster adjacents a la CIBLE| + wEnemy * |ennemis adjacents a la CIBLE|

        `attack_tile` est accepte et IGNORE : les deux slots sont ancres sur `case.Target`, et
        `case.CasterPosition` (`UtilityAttackCase@+0x18`) n'est jamais lu -- le terme ne varie pas
        d'une tuile d'attaque a l'autre. `prediction` est accepte et IGNORE de meme : le corps ne lit
        que `case@+0x10` (Caster) et `case@+0x20` (Target), jamais `case.DamagePrediction` (`+0x28`).
        """
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        n_friend, n_enemy = count_adjacent_by_camp(sc, attacker_uid, case_tgt_id)
        # Ordre natif : le terme AMI est calcule d'abord (`iVar2`), le terme ENNEMI lui est ajoute.
        return (float(ctx.wt.triggered(_WEIGHT_FRIEND)) * n_friend
                + float(ctx.wt.triggered(_WEIGHT_ENEMY)) * n_enemy)


__all__ = ["FireOfAbsolutionPlaybook", "count_adjacent_by_camp"]
