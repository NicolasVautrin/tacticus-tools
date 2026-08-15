"""Face **ATTACK** de la famille `TriggeredAbilityNonOwnerPlaybook<T>` (#271-r4).

Le dispatcher `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility` a TROIS entrees, une par
face de `ITriggeredAbilityNonOwnerPlaybook` : `$$EvaluateMovementInSteps` (slot 0),
`$$EvaluateAttackInSteps` (slot 1) et `$$EvaluateRepairInSteps` (slot 2). La face MOVE vit dans
`engine/playbook/non_owner.py` ; CE module porte la face ATTACK. Les deux registres sont SEPARES,
et c'est structurel : la feuille `TriggeredAbilitiesNonOwner(4)` est membre de TROIS composites
distincts, et un corps inscrit dans le mauvais registre partirait dans le mauvais composite.

CE QUI SEPARE LA FACE ATTACK DE LA FACE MOVE -- deux points, tous deux LUS
--------------------------------------------------------------------------

```c
// IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.<EvaluateAttackInSteps>d__1$$MoveNext
Fix64 total = 0;
foreach ((playbook, owner) in IterateAbilities(case.<+0x10>))     // surcharge (IEntity)
    total += playbook.<slot 1>(case, owner);                       // CalculateAttackUtilityInSteps
yield total;
```

1. **AUCUN gate de nullite du sujet.** La face MOVE ouvre sur
   `if (case.unit == null && case.parent == null) { yield 0; return; }` ; celle-ci n'a rien --
   elle appelle directement la surcharge `$$IterateAbilities(IEntity)`.
2. **Le SUJET est le CASTER**, `case+0x10`. `IdunBattle.AI.Utilities.UtilityAttackCase$$.ctor`
   ecrit `caster` a `+0x10`, `casterPosition` a `+0x18` et `target` a `+0x20` -- lu, pas suppose.

```c
// IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility.<IterateAbilities>d__4$$MoveNext
foreach (ta in <utility+0x50 = abilityAndEffectCache>.<slot 5>()) {
    if (ta.Owner == subject) continue;                   // INCONDITIONNEL (d__3 le garde par
                                                         //  `case.unit != null`)
    pb = PlaybookDatabase.LoadPlaybookNonOwner(ta.Type);  // null -> skip
    if (pb.<slot 4> || UnitExtensions.IsFriend(subject, ta.Owner, State))
        yield (pb, ta.Owner);
}
```

LES QUATRE CORPS CONCRETS, ET CE QUE CE MODULE PORTE
-----------------------------------------------------
La ventilation par FACE est LUE dans `data/symbols/<build>/metadata/non_owner_slot4.tsv`
(#477-r37) : **24 MOVE / 3 ATTACK / 1 REPAIR** sur les 28 concrets. Les trois ATTACK :

| classe | blocage | etat |
|---|---|---|
| `NoHidingFromTheWatchersNonOwnerPlaybook` | `aucun` | **PORTEE ici** |
| `WayOfTheShortBladeNonOwnerPlaybook`      | `aucun` | **PORTEE ici** |
| `ShieldOfFaithNonOwnerPlaybook`           | ~~`capteur`~~ **`aucun`** | NON portee -- residu
  **`#1024-r7`**, et son BLOCAGE EST PERIME (cf. ci-dessous). |

⚠ **LE VERROU DE `ShieldOfFaith` EST TOMBE, ET CETTE TABLE L'A AFFIRME UN TEMPS DE TROP.** Le texte
qui vivait ici -- << son 1er gate est `HasRarity(caster, Mythic)` et AUCUN canal `rarity` n'existe
cote port ; il faudrait `combatSnapshot.units[].rarity`, donc une fenetre de reinject >> -- etait
vrai a l'ecriture et ne l'est plus : le capteur est ARME depuis #1039 et CONSOMME depuis #999-r3,
par le foyer unique `UnitContext.rarity` (mirror `engine/entities/rarity.py`, noeud
`entities/triggers.HasRarity`). MESURE le 2026-08-14, en live et sur cette ability meme :
`test_1024r1_shield_of_faith_live.py` lit `ctx.rarity == 5` sur l'attaquant, et sa contre-epreuve
`--unit-stat <att>:Rarity=4` ETEINT le bouclier des DEUX cotes -- donc le gate est exercable, pas
seulement lisible. La face COMBAT est portee depuis #1024-r1.

Ce qui reste vrai : porter le corps SANS le gate serait un terme PERMISSIF. Ce qui a change : le
gate est desormais portable. Le blocage de ce residu est donc `aucun`.
⚠ Et c'est le mode de defaillance que le CLAUDE.md nomme -- un champ `BLOCAGE` n'est JAMAIS
re-mesure : il fait ECARTER le residu au dispatch, indefiniment, longtemps apres que sa cause a
disparu. Re-mesurer avant d'ecarter, jamais citer la ligne.

La face **REPAIR** n'est pas montee du tout, et ce n'est pas un oubli : son unique corps
(`VoltagheistFieldPlaybook`) DELEGUE a `<utilitiesDatabase>.GetUtility(0x30 =
UtilityType.RepairedAmount, 0).<slot 6>(case)`. La feuille `RepairedAmount(48)` EST portee
(`engine/utilities/repair.py`), mais le `<slot 6>` d'`IUtility` n'est PAS dans
`data/symbols/<build>/metadata/interface_slots.tsv` (l'interface n'y figure pas) : le canal n'est
donc pas etabli. Monter un dispatcher REPAIR dont le registre serait VIDE serait du code que rien
n'itere -- le patron #419 que ce depot refuse. Residu `#271-r7`.

⚠ **`NoHidingFromTheWatchersNonOwnerPlaybook` porte `<slot 4> = true`** (entree versionnee,
`declare=1 valeur=1 corps=b0 01 c3`). L'inscrire sans cette valeur rendrait sa branche ENNEMI
STRUCTURELLEMENT inatteignable, puisque son corps ouvre precisement sur `if (IsFriend(caster,
owner)) yield break` : le pre-gate `<slot 4> || IsFriend` serait alors le seul filtre, et il ne
laisserait passer que des AMIS -- que le corps refuse. Terme identiquement nul, sans erreur. C'est
le bug de #477-r35, transpose d'une face.

ASCII only dans les sorties ; les accents restent dans les docstrings non imprimees.
"""
from __future__ import annotations

from .. import battle_query as bq
from ..entities.ability_constant_type import AbilityConstantType
from ..entities.effect_type import EffectType
from ..entities.rarity import Rarity
from ..entities.traits.unit_trait import UnitTrait
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.unit_faction import UnitFaction
from .non_owner import TriggeredAbilityNonOwnerPlaybook
from .adjacent_unit_preference import _has_ranged_weapon as _hrw
from .adjacent_unit_preference import _unit_faction


def _has_trait(scene, uid, trait_id) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasTrait(u, <id>)` sur le substrat d'ENTITE.

    `Scene.ctx(uid).traits` porte les IDS `UnitTrait` -- kit gameconfig, ou la MESURE live quand
    `traits_measured` (elle inclut alors le pseudo-trait de GRANDE-ALLIANCE que le gameconfig
    ignore, cf. `FirstAmongTraitorsNonOwnerPlaybook`)."""
    c = scene.ctx(uid) if scene is not None else None
    return bool(c is not None and int(trait_id) in (c.traits or ()))


def _has_faction(scene, uid, faction) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasFaction(u, <id>)`.

    DELEGUE au mirror deja porte (`engine/playbook/adjacent_unit_preference._unit_faction`) : le
    natif ne compare PAS un entier, il fait `Enum.ToString(UnitFaction)` puis `String.Equals` avec
    `FactionComponent+0x30`, et le pendant offline est le `FactionId` du gameconfig. ⚠ NE PAS
    passer par `Scene.faction` : ce champ-la est seede depuis `cfg.get("faction")`, une cle que le
    gameconfig d'unite ne porte PAS (mesure : `None` sur les six unites Tau du catalogue) -- le
    gate aurait ete identiquement faux, en silence."""
    vis = (scene.vis_by_id or {}).get(uid) if scene is not None else None
    return bool(vis) and _unit_faction({"vis": vis}) == UnitFaction(faction).name


def _has_ranged_weapon(scene, uid) -> bool:
    """`IdunBattle.Entities.UnitExtensions$$HasRangedWeapon(u, minRange = null)`.

    DELEGUE au mirror deja porte (`engine/playbook/adjacent_unit_preference._has_ranged_weapon`,
    qui lit `WeaponsComponent$$HasRangedWeapon` = « au moins UNE arme non-melee », avec le seuil
    `Range >= 2` de `WeaponProfile$$get_IsMelee`) plutot que de re-tester `normal_ranged` : ce
    dernier ne parle que de l'arme NORMALE, alors que le natif balaie TOUTES les armes. Un fork
    ici serait exactement la faute de #175-e sur `IsMechanical`."""
    vis = (scene.vis_by_id or {}).get(uid) if scene is not None else None
    return bool(vis) and bool(_hrw({"vis": vis}))


def _adjacent_friend_count(scene, uid, pos, elev_by_pos, neigh) -> int:
    """`IBattleQuery.<slot 132 = GetAdjacentFriends(pos, unit)>.Count` -- les allies de `uid`
    (SELF EXCLU) dont la tuile est voisine NATIVE de `pos`.

    Le voisinage est celui de `IdunBattle.Core.Services.TileQuery.<IterateAdjacentTiles>d__8`, qui
    applique un gate INCONDITIONNEL `|elev(a) - elev(b)| < 2` : deux tuiles cote a cote separees de
    deux niveaux ne sont PAS voisines (le piege de `case-271` §4). `battle_query.is_adjacent` le
    porte ; `hexgeo.distance == 1` ne le porte pas."""
    if scene is None or pos is None:
        return 0
    my_team = scene.team(uid)
    n = 0
    for u in (scene.units or []):
        u_id = u.get("id")
        if u_id is None or int(u_id) == int(uid):        # GetAdjacentFriends exclut l'unite meme
            continue
        if scene.team(u_id) != my_team:
            continue
        p = scene.pos(u_id)
        if p is None:
            continue
        if bq.is_adjacent((pos[0], pos[1]), (p[0], p[1]), elev_by_pos, neigh):
            n += 1
    return n


class TriggeredAbilityNonOwnerAttackPlaybook(TriggeredAbilityNonOwnerPlaybook):
    """Base de la face ATTACK :
    `IdunBattle.AI.Playbook.TriggeredAbilityNonOwnerPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateAttackUtilityInSteps`
    yield 0 (la base ne pese rien ; seuls les concrets qui overrident comptent).

    Signature du port -- eclatement du `UtilityAttackCase` que le natif passe entier :
      * `caster`      = `case+0x10` (`UtilityAttackCase$$.ctor`), le SUJET de `IterateAbilities` ;
      * `caster_tile` = `case+0x18` (`casterPosition`), d'ou `case.CasterPosition.MainTile` ;
      * `target`      = `case+0x20` ;
      * `owner`       = le porteur de la `TriggeredAbility`, 2e element du tuple yielde ;
      * `is_friend`   = `UnitExtensions.IsFriend(caster, owner, State)`, deja calcule par le
                        dispatcher pour son pre-gate (les corps le RE-testent quand le natif le
                        re-teste -- on mirrore le corps, pas l'economie qu'on pourrait en faire) ;
      * `ctx`         = l'`AiDecisionContext` de la decision (porte `scene`, `elev_by_pos`, ...)."""

    #: La FACE du corps natif, LUE dans `data/symbols/<build>/metadata/non_owner_slot4.tsv`. Elle
    #: dit dans QUEL composite le terme part : `Damage(35)` pour ATTACK, `Tile(7)` pour MOVE,
    #: `Repair(47)` pour REPAIR. Jamais deduite du nom de la classe.
    FACE = "ATTACK"

    def calculate_attack_utility_in_steps(self, ctx, caster: int, caster_tile, target: int,
                                          owner: int, is_friend: bool, wt) -> float:
        return 0.0


class NoHidingFromTheWatchersNonOwnerPlaybook(TriggeredAbilityNonOwnerAttackPlaybook):
    """`NoHidingFromTheWatchersNonOwnerPlaybook`
    (`IdunBattleLogic.Playbook.Triggered.Loki.NoHidingFromTheWatchersNonOwnerPlaybook$$.ctor` :
    litteral `0x5f3` = 1523 `NoHidingFromTheWatchers`, PASSIF d'unite).

    `IdunBattleLogic.Playbook.Triggered.Loki.NoHidingFromTheWatchersNonOwnerPlaybook.u003CCalculateAttackUtilityInStepsu003Ed__4$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS : `owner @+0x20, playbook @+0x28,
    case @+0x30`) :

        ITile ownerTile = EntityExtensions.GetMainTile(owner, State);
        ITile casterTile = case.CasterPosition.MainTile;          // `<get_MovementTile>` = `+0x18`
                                                                  //  puis `UnitPosition.MainTile`
        if (case.Target != owner) yield break;
        if (casterTile == null) yield break;
        if (ownerTile == null) yield break;
        if (UnitExtensions.IsFriend(case.Caster, owner, State)) yield break;
        var pos = EntityExtensions.GetUnitPosition(owner, State);
        if (Query.<slot 0x84 = GetAdjacentFriends(pos, owner)>.Count != 0)
            yield return GetUtilityValue("NoHidingFromTheWatchers_AttackIfAdjacentToFriendAndMele");

    ⚠ **CE CORPS EST INATTEIGNABLE SANS LE `<slot 4>`.** Il ouvre sur `if (IsFriend(caster, owner))
    yield break` : sa SEULE branche utile est le caster ENNEMI. Or le pre-gate d'`IterateAbilities`
    est `pb.<slot 4> || IsFriend(subject, owner)` -- sans le `true` du slot, aucun caster ennemi
    n'atteindrait jamais ce corps. La classe le DECLARE bien (`declare=1 valeur=1 corps=b0 01 c3`,
    entree versionnee `non_owner_slot4.tsv`) et c'est LOAD-BEARING.

    ⚠ `0x84` = 132 est une des QUATRE surcharges `GetAdjacentFriends` d'`IBattleQuery` (slots
    129/130/131/132, toutes d'arite 2) -- slot LU dans
    `data/symbols/<build>/metadata/interface_slots.tsv`, pas devine. La surcharge est fixee par le
    type des arguments : `(pos: UnitPosition, unit: IEntity)`. Toutes passent par le meme voisinage
    NATIF (gate d'elevation `< 2`), d'ou `battle_query.is_adjacent`.

    ⚠ Le corps ne lit JAMAIS `case.DamagePrediction` : le terme ne depend ni du degat ni de la
    prediction, seulement de la GEOMETRIE et du camp. Il vaut donc `10` ou `0`.

    Cle BC LUE (`probe_212_bc_key_literals.py` sur le symbole du `MoveNext`) :
    `NoHidingFromTheWatchers_AttackIfAdjacentToFriendAndMele` -- notez le `Mele` TRONQUE, exactement
    comme dans le binaire ; au gameconfig vivant `Default.TriggeredAbilitiesNonOwner` = **10**.

    Porteurs (voie PASSIF d'unite, `unit_map.py find --ability NoHidingFromTheWatchers`) :
    `darkaSmnWatcher` (**SUMMON**) et `darkaNpc4Watcher` (npc). Le summon compte : on l'amene en
    bataille en spawnant son summoner, et c'est LUI qui doit etre la CIBLE de l'attaque
    (`case.Target == owner`)."""

    ABILITY_ID = int(TriggeredAbilityType.NoHidingFromTheWatchers)        # 0x5f3 = 1523
    KEY = "NoHidingFromTheWatchers_AttackIfAdjacentToFriendAndMele"       # gameconfig vivant = 10
    #: `get_ShouldIncludingEnemiesWhenCalculate` -- VRAI, et c'est ce qui rend le corps atteignable.
    SLOT_4 = True

    def calculate_attack_utility_in_steps(self, ctx, caster: int, caster_tile, target: int,
                                          owner: int, is_friend: bool, wt) -> float:
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        if target is None or owner is None or int(target) != int(owner):   # case.Target != owner
            return 0.0
        if caster_tile is None:                        # case.CasterPosition.MainTile == null
            return 0.0
        opos = sc.pos(owner)
        if opos is None:                               # GetMainTile(owner, State) == null
            return 0.0
        if is_friend:                                  # IsFriend(case.Caster, owner) -> break
            return 0.0
        elev = getattr(ctx, "elev_by_pos", None)
        neigh = getattr(ctx, "neigh_by_pos", None) or sc.neigh_by_pos
        if _adjacent_friend_count(sc, owner, opos, elev, neigh) == 0:
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


class WayOfTheShortBladeNonOwnerPlaybook(TriggeredAbilityNonOwnerAttackPlaybook):
    """`WayOfTheShortBladeNonOwnerPlaybook`
    (`IdunBattleLogic.Playbook.Triggered.Loki.WayOfTheShortBladeNonOwnerPlaybook$$.ctor` : litteral
    `0x5dc` = 1500 `WayOfTheShortBlade`, PASSIF d'unite).

    `IdunBattleLogic.Playbook.Triggered.Loki.WayOfTheShortBladeNonOwnerPlaybook.u003CCalculateAttackUtilityInStepsu003Ed__2$$MoveNext`,
    remis en C# depuis le decompile (champs de la SM LUS : `case @+0x20, playbook @+0x28,
    owner @+0x30` -- l'ORDRE N'EST PAS celui de `NoHidingFromTheWatchers`, qui met owner @+0x20) :

        IEntity caster = case.Caster;                                   // `case+0x10`
        if (!UnitExtensions.HasTrait(caster, 0x10)) yield break;        // UnitTrait.Hero
        if (!( UnitExtensions.HasFaction(caster, 9)                     // UnitFaction.Tau
            && UnitExtensions.HasRangedWeapon(caster, null)
            && Query.<slot 0x61 = AreEntitiesAdjacent>(case.CasterPosition, case.Target) ))
            yield break;
        int range = AbilityConfiguration.GetNumberConstant(playbook.<+0x58>.<+0x20>, 0x16);
        if (Query.<slot 0x6d = GetDistance>(owner, case.CasterPosition) <= range)
            yield return GetUtilityValue("WayOfTheShortBlade_TauAdjacentToEnemy");

    ⚠ **LES TROIS GATES PORTENT SUR LE CASTER, PAS SUR LE PORTEUR.** Farsight (l'owner) n'entre que
    par la DISTANCE finale. Le terme recompense donc « un HERO Tau a arme de tir, au CONTACT de sa
    cible, a portee de Farsight » -- une preference de POSITIONNEMENT du camp Tau, pas une propriete
    de Farsight.

    ⚠ `0x16` est un **`AbilityConstantType`** (`range`), TYPE DECLARE lu dans `frida/methods.tsv`
    (`AbilityConfiguration.GetNumberConstant(constantType: IdunBattle.Configuration.
    AbilityConstantType)`) -- pas un ordinal nu. Au gameconfig vivant
    `abilities.WayOfTheShortBlade.constants.range` vaut **2**, et la comparaison est `<=` (donc 2
    INCLUS, tuile du porteur comprise a distance 0). MEME lecture que
    `FirstAmongTraitorsNonOwnerPlaybook.range_tiles`.

    ⚠ `0x61` = 97 et `0x6d` = 109 : deux slots d'`IBattleQuery` dont le NOM est partage par
    plusieurs surcharges (`AreEntitiesAdjacent` 96/97/98, `GetDistance` 108/109/110) -- slots LUS
    dans `data/symbols/<build>/metadata/interface_slots.tsv`. Les surcharges deleguent au meme
    corps : `MovementUtil$$AreTilesAdjacent` (gate d'elevation `< 2`) et
    `MovementQuery$$GetDistance(originTiles, destinationTiles)` (distance HEXAGONALE minimale entre
    deux ENSEMBLES, `int.MaxValue` sur un ensemble vide). Foyers portes :
    `battle_query.are_entities_adjacent` et `battle_query.get_distance`.

    ⚠ `<slot 4> = false` (la classe ne declare pas le getter) : c'est donc le PRE-GATE
    d'`IterateAbilities` qui restreint aux porteurs AMIS du caster. Le corps, lui, ne teste PAS
    `IsFriend` -- et le port ne l'ajoute pas.

    Cle BC LUE : `WayOfTheShortBlade_TauAdjacentToEnemy`, au gameconfig vivant
    `Default.TriggeredAbilitiesNonOwner` = **5**.

    Porteurs (voie PASSIF d'unite) : `tauFarsight` (kind `lineup`, **HORS du pool** -> injection
    catalogue) et cinq npc `tauBossFarsight*`."""

    ABILITY_ID = int(TriggeredAbilityType.WayOfTheShortBlade)             # 0x5dc = 1500
    KEY = "WayOfTheShortBlade_TauAdjacentToEnemy"                        # gameconfig vivant = 5
    CONFIG_ID = "WayOfTheShortBlade"
    #: `GetNumberConstant(config, 0x16)` -- la constante, PAS son ordinal nu.
    RANGE_CONSTANT = AbilityConstantType.range                           # 0x16 = 22

    def range_tiles(self):
        """`GetNumberConstant(config, AbilityConstantType.range)`.

        `None` = constante absente -> `GetNumberConstant` LEVE cote natif ; le port se degrade en
        « aucun terme » plutot que d'inventer un rayon (meme convention que #477-r37)."""
        import gameconfig as GC
        consts = (GC.ability(self.CONFIG_ID) or {}).get("constants") or {}
        v = consts.get(self.RANGE_CONSTANT.name)
        return None if v is None else int(v)

    def calculate_attack_utility_in_steps(self, ctx, caster: int, caster_tile, target: int,
                                          owner: int, is_friend: bool, wt) -> float:
        sc = getattr(ctx, "scene", None)
        if sc is None or caster_tile is None:
            return 0.0
        if not _has_trait(sc, caster, UnitTrait.Hero):            # HasTrait(caster, 0x10)
            return 0.0
        if not _has_faction(sc, caster, UnitFaction.Tau):         # HasFaction(caster, 9)
            return 0.0
        if not _has_ranged_weapon(sc, caster):                    # HasRangedWeapon(caster, null)
            return 0.0
        tpos = sc.pos(target)
        if tpos is None:
            return 0.0
        elev = getattr(ctx, "elev_by_pos", None)
        neigh = getattr(ctx, "neigh_by_pos", None) or sc.neigh_by_pos
        if not bq.are_entities_adjacent((caster_tile[0], caster_tile[1]), (tpos[0], tpos[1]),
                                        elev, neigh):             # AreEntitiesAdjacent
            return 0.0
        rng = self.range_tiles()
        if rng is None:
            return 0.0
        opos = sc.pos(owner)
        # `GetDistance` sur un ensemble VIDE rend `int.MaxValue` : porteur sans tuile -> jamais
        # `<= range`, exactement comme le natif.
        d = bq.get_distance([(opos[0], opos[1])] if opos else (),
                            [(caster_tile[0], caster_tile[1])])
        if d > rng:
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


def _tile_effect_names(scene, pos) -> tuple:
    """Les NOMS d'effets portes par la tuile `pos`, cote `IsOwnerOfEffect(..., onlyActive: false)`.

    `IdunBattle.Entities.EntityExtensions$$HasEffect(entity, state, type, onlyActive)` = LU :

        return IsOwnerOfEffect(entity, state, type, onlyActive)
            || IsTargetOfEffect(entity, state, type);

    et `IsOwnerOfEffect` itere `GetComponent<EffectsOwnedComponent>(entity).<+0x10>` (la liste dont
    le nom `ActiveEffectIds` TROMPE : le filtre d'activite n'y est pas, il est applique par le
    parametre `onlyActive`). C'est EXACTEMENT le canal `Scene.tile_effects_owned_by_pos`, servi par
    `ai/context.py` avec `only_active=False` -- donc la bonne table pour un `onlyActive: false`.
    Repli sur `tile_effects_by_pos` (ACTIF-ONLY) quand la premiere n'est pas fournie : c'est le
    comportement d'avant #425-r1, jamais un vide invente. MEME cascade que `SceneTileState`.

    ⚠ ECART NOMME : la seconde branche, `IsTargetOfEffect` (les effets ACTIFS dont l'entite figure
    dans `EffectComponent.<+0x48>` = la liste des CIBLES), n'a AUCUN canal cote port -- aucune table
    ne dit « de quels effets cette tuile est la CIBLE ». Pour un effet de TUILE le regime normal est
    la premiere branche : `TileEffectsUtility.<EvaluateMovementInSteps>d__1` lit precisement
    l'`EffectsOwnedComponent` de la MainTile, donc une tuile en feu POSSEDE son `Fire`. L'ecart est
    RESTRICTIF et il est ici parce qu'il est commun a tout le port des effets de tuile."""
    if scene is None or pos is None:
        return ()
    p = (pos[0], pos[1])
    tbl = getattr(scene, "tile_effects_owned_by_pos", None)
    if tbl is None:
        tbl = getattr(scene, "tile_effects_by_pos", None)
    if tbl is None:
        return ()                       # canal NON MESURE -> le gate se tait (jamais un faux vrai)
    return tuple(n for n in (tbl.get(p) or ()) if n)


class ShieldOfFaithNonOwnerPlaybook(TriggeredAbilityNonOwnerAttackPlaybook):
    """`IdunBattle.AI.Playbook.Loki.ShieldOfFaithNonOwnerPlaybook`
    (`$$.ctor` : litteral `0x5ad` = 1453 `ShieldOfFaith`, MYTHIQUE de MACHINE OF WAR).

    `...u003CCalculateAttackUtilityInStepsu003Ed__2$$MoveNext`, remis en C# depuis le decompile
    (methode-usine : `case @+0x20, playbook @+0x28` -- **`owner` n'est PAS ecrit**) :

        var caster = case.Caster;                                    // `case+0x10`
        if (caster.TryGetComponent<BaseUnitComponent>(out var buc) && buc.Rarity != 5)
            yield break;                                             // Rarity.Mythic
        if (AnyTileHasEffectOfUnit(case.Target, EffectType.Fire))     // `case+0x20`, litteral 5
            yield return GetUtilityValue("ShieldOfFaith_LikesEnemiesOnFire");

    et le helper NOMME `...ShieldOfFaithNonOwnerPlaybook$$AnyTileHasEffectOfUnit(target, type)` :

        foreach (t in EntityExtensions.GetTiles(target, State))
            if (EntityExtensions.HasEffect(t, State, type, onlyActive: false)) return true;
        return false;

    QUATRE lectures qui ne se devinent pas :

    * ⚠ **CE CORPS NE LIT JAMAIS `owner`.** Sa methode-usine n'ecrit pas l'argument -- il partage ce
      trait avec `MastersOfManoeuvreNonOwnerPlaybook` et `NornCrownNonOwnerPlaybook`. Le porteur
      n'intervient que par le PRE-GATE d'`IterateAbilities`, et son `<slot 4>` valant `false`
      (entree versionnee `metadata/non_owner_slot4.tsv` : `declare=0 valeur=0`), ce pre-gate se
      reduit a `IsFriend(caster, owner)` : seuls les casters AMIS du porteur voient le terme ;
    * **le gate de rarete est INLINE, pas `HasRarity`** : le corps lit
      `GetComponent<BaseUnitComponent>(caster)->[0x74]` sans le filtre `<EntityType> == 1` que porte
      la fonction nommee. Et **si `TryGetComponent` echoue, le corps CONTINUE** -- la comparaison
      est gardee par le succes de la resolution, pas l'inverse. Un caster sans `BaseUnitComponent`
      passe donc le gate ;
    * **`5` est un `EffectType`** -- TYPE DECLARE lu dans `frida/methods.tsv`
      (`AnyTileHasEffectOfUnit(target: IEntity, effectType: IdunBattle.Entities.Enum.EffectType)`),
      et `EffectType.Fire`. Le nom de la cle BC le CONFIRME independamment :
      `ShieldOfFaith_LikesEnemiesOnFire`. Les homonymes a ecarter (`UnitTrait` 5 = `Mechanical`,
      `UnitFaction` 5 = `Orks`) n'ont rien a voir ;
    * **le gate porte sur les TUILES DE LA CIBLE**, pas sur la cible elle-meme ni sur le caster.

    Cle BC LUE (`probe_212_bc_key_literals.py`) : `ShieldOfFaith_LikesEnemiesOnFire`, au gameconfig
    vivant `Default.TriggeredAbilitiesNonOwner` = 10.

    ⚠ ECART NOMME : `GetTiles(target)` rend TOUTES les tuiles de la cible ; le port n'interroge que
    sa MAIN TILE (`Scene.pos`). L'ecart n'existe que pour une cible MULTI-TUILES.

    ⚠⚠ **VOLONTAIREMENT ABSENTE DU REGISTRE `NON_OWNER_ATTACK_PLAYBOOKS` : BLOCAGE D'ETAGE MESURE
    (#1024-r7).** Ses DEUX porteurs (`adeptExorcist`, `adeptNpcMoWExorcist`) sont des MACHINES OF
    WAR (voie `mythicAbilities`), et `evaluate_attack_in_steps` itere `Scene.units` -- c'est-a-dire
    `decisionView.units`, d'ou le natif exclut les Machines par construction (canal `.mows`
    SEPARE). La paire `(playbook, owner)` ne serait donc jamais yieldee : l'inscrire serait le
    patron #419. Le corps est porte parce que la RE est faite et juste ; le cabler tiendra en UNE
    ligne le jour ou l'univers du dispatcher s'elargira.
    ⚠ Le blocage annonce par la fiche etait `capteur` (la RARETE), puis requalifie `aucun` par
    l'en-tete de ce module. Les DEUX sont faux : la rarete est arrivee (#1039 / #999-r3) et elle
    n'a jamais ete le verrou de cette classe. Mesure :
    `probe_1036r3_porteurs_non_owner_restants.py`."""

    ABILITY_ID = int(TriggeredAbilityType.ShieldOfFaith)                  # 0x5ad = 1453
    KEY = "ShieldOfFaith_LikesEnemiesOnFire"                              # gameconfig vivant = 10
    #: `<slot 4>` LU dans `metadata/non_owner_slot4.tsv` : la classe ne declare pas le getter.
    SLOT_4 = False
    #: Litteral `5` du call-site, QUALIFIE contre le type declare du parametre.
    TILE_EFFECT = EffectType.Fire                                         # 5

    def calculate_attack_utility_in_steps(self, ctx, caster: int, caster_tile, target: int,
                                          owner: int, is_friend: bool, wt) -> float:
        sc = getattr(ctx, "scene", None)
        if sc is None:
            return 0.0
        # `if (TryGetComponent(caster, BaseUnitComponent, out buc) && buc.Rarity != 5) yield break`
        # -- TRI-ETAT : `rarity is None` = canal NON MESURE, ce qui mirrore l'echec de resolution du
        # composant, et le natif CONTINUE dans ce cas-la (la comparaison est gardee par le succes).
        c = sc.ctx(caster)
        r = getattr(c, "rarity", None) if c is not None else None
        if r is not None and int(r) != int(Rarity.Mythic):
            return 0.0
        # `AnyTileHasEffectOfUnit(case.Target, EffectType.Fire)`.
        if self.TILE_EFFECT.name not in _tile_effect_names(sc, sc.pos(target)):
            return 0.0
        return float(wt.sub("TriggeredAbilitiesNonOwner", self.KEY))


# `IdunBattle.AI.PlaybookDatabase$$LoadPlaybookNonOwner` rend LE MEME singleton pour les trois
# faces -- c'est le DISPATCHER qui choisit le slot (0 / 1 / 2). Le port a deux registres parce que
# les deux dispatchers portes sont distincts ; une classe ne doit figurer que dans celui de SA
# face, lue dans l'entree versionnee `metadata/non_owner_slot4.tsv`.
#
# `ShieldOfFaithNonOwnerPlaybook` (3e face ATTACK) est PORTEE ci-dessus mais VOLONTAIREMENT ABSENTE
# d'ici -- residu `#1024-r7`, blocage `etage` MESURE : ses deux porteurs sont des MACHINES OF WAR,
# que `evaluate_attack_in_steps` ne voit pas (il itere `Scene.units`, d'ou `decisionView` exclut
# les Machines). L'inscrire serait le patron #419.
# Absence du registre == `LoadPlaybookNonOwner` rend null == la paire n'est jamais yieldee, donc
# MEME degradation que le natif sur un type sans classe -- mais ici la classe EXISTE, donc c'est
# un ECART assume et NOMME, pas un trou.
NON_OWNER_ATTACK_PLAYBOOKS: dict = {
    int(TriggeredAbilityType.NoHidingFromTheWatchers): NoHidingFromTheWatchersNonOwnerPlaybook(),
    int(TriggeredAbilityType.WayOfTheShortBlade): WayOfTheShortBladeNonOwnerPlaybook(),
}


def load_playbook_non_owner_attack(ability_id: int):
    """Mirror `PlaybookDatabase.LoadPlaybookNonOwner`, restreint aux corps de face ATTACK.
    None -> le dispatcher skip la paire (meme chemin que le `if (playbook == null) continue`)."""
    return NON_OWNER_ATTACK_PLAYBOOKS.get(int(ability_id))
