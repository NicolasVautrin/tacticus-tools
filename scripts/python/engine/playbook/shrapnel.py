"""`IdunBattle.AI.Playbook.Loki.ShrapnelPlaybook` -- face ATTACK du triggered `Shrapnel` (1116),
passif de 2 npc (`astraNpc4Mortar`, `astraNpc4MortarSurv`) et du SUMMON `astraSmnMortar` : 3 porteurs
DISPATCHES, tranche 13 des residus ATTACK de #419-r1.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(35), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae, BarbedOvipositor, Neuroparasite, SaviorProtocols,
AvalancheOfMuscle, Boltstorm, FireOfAbsolution, CosmicHorror, LightImUp, RapidFire,
RighteousRepugnance, SpecialIssueCombiMelta et ElectroShock
(`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

(!) PIEGE DU NOM, leve AVANT toute lecture : `1116` designe TROIS artefacts natifs distincts, et le
seul deja porte n'est AUCUN des deux autres. Enums QUALIFIES :
`TriggeredAbilityType.Shrapnel = 1116` (CE playbook), `ActiveAbilityType.RadBombardment = 1116`
(l'active tile-targeting de #217/#241/#254), `EffectType.InescapableAccuracy_extraCritDmg = 1116`
(porte par #414, `case-366-r1-inescapable-accuracy-crit-damage.md` -- axe CRIT, sans aucun rapport
avec ce passif). Aucun autre enum ne porte le NOM `Shrapnel` : il n'y a donc pas de mold d'attaque
normale sous un autre id pour ce passif (a l'inverse de `RighteousRepugnance` 1107 -> mold 1182 ou
d'`ElectroShock` 1303 -> mold 1178).

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.ShrapnelPlaybook$$CalculateAttackUtilityInStepsInternal` monte la SM
`d__2` -- disposition LUE dans le wrapper, PAS par analogie : `sm@+0x20 = this` (le PLAYBOOK),
`sm@+0x28 = case`, et **`getUtilityVal` N'EST PAS CAPTURE** (deux champs seulement, comme
`BarbedOvipositor`). Le corps est
`ShrapnelPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`, **UN SEUL yield**
en tete de sortie :

    if (!IsRegularAttack(case))                      // TriggeredAbilityPlaybook<T>$$IsRegularAttack
        yield break;                                 // AUCUN yield -- pas meme un 0

    Fix64 acc = Fix64.op_Implicit(0);
    var sel = DSLSelectors.Damageable(
                  DSLSelectors.AdjacentUnits(DSLSelectors.Get(case.Target),   // case@+0x20
                                             unique: true, unitSelectionType: 3));
    foreach (var u in sel.SelectUniqueUnits(new AbilityEntities(/* memset 0 */), 3)) {
        var pred = this.<IBattleQuery @playbook+0x60>.<slot 0x23>(
                       case.Caster,                       // case@+0x10
                       u,
                       case.CasterPosition.MainTile,      // case@+0x18 -> la TUILE D'ATTAQUE
                       case.AbilityType,                  // case@+0xf0
                       AbilityConfiguration.GetVariableForLevel(
                           config, 0xc /* minDmg */,
                           GetAbilityState(case.Caster), fallbackToDefault: false),
                       (DamageProfileType?)0x12 /* Blast */, false, null);
        var ev = new ProbableDamageEvent(u, pred, null, null);
        int hits = AbilityConfiguration.GetNumberConstant(config, 0x2f /* nrOfHits */);
        for (int i = 0; i < hits; i++)
            acc = Fix64.op_Addition(acc, CalculateUtilityFromDamageEvent(ev, case.Caster,
                                                                         case.CasterPosition));
    }
    yield return acc;                                // la SOMME, un seul step

Neuf lectures qui ne se devinent pas, et dont aucune ne se generalise depuis un voisin de la liste :

1. **AUCUN poids BC n'intervient.** Le wrapper n'ecrit que `state`, `this` et `case` dans la SM :
   le delegue scorer `getUtilityVal` n'est meme pas conserve, donc il n'y a ni `GetUtilityValue`, ni
   cle `SHRAPNEL_*` a chercher dans `Utilities.Default.TriggeredAbilities`. La sortie est une
   UTILITE DE DEGAT (composite Damage), pas un scalaire de config -- comme `AvalancheOfMuscle`,
   `Psyker` et `LightImUp`, a l'inverse de `Boltstorm` / `FireOfAbsolution` / `ElectroShock`.

2. **La sortie est une SOMME sur toutes les cibles, PAS une moyenne.** `Psyker` divise par
   `Count` (`Fix64.op_Division` de sortie) et `LightImUp` moyenne ses cibles secondaires : ici il
   n'y a **aucune** division dans le corps. Recopier la forme du voisin diviserait par |voisins|.

3. **`nrOfHits` multiplie l'UTILITE, pas les degats.** La prediction est celle du slot 0x23, dont
   `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` ecrit le LITTERAL `1` comme nombre de
   coups ; c'est la boucle `for (i < GetNumberConstant(0x2f))` du playbook qui repete
   `CalculateUtilityFromDamageEvent` sur le **MEME** event. `hits x U(1 coup)` n'est pas
   `U(hits coups)` : le composite Damage sature (`Clamp(D / combinedMax, 0, 1) * 80`, plus les
   feuilles kill/overkill qui sont des paliers), donc la difference est reelle des que la cible est
   fragile. On mirrore le code, pas l'intention.

4. **Le montant est `minDmg` SEUL** (`GetVariableForLevel(config, 0xc, ..., fallbackToDefault:
   false)`), la ou la face COMBAT tire `DSLFormulas.RandomAmount(minDmg, maxDmg)`. Les index sont
   les MEMES que ceux deja etablis par le port (`0xc = minDmg`, `0xd = maxDmg` --
   `loki_custom.StikkbombPlaybook`, `light_im_up`) et le corps n'appelle `GetVariableForLevel`
   qu'UNE fois : il n'y a pas de moyenne min/max ici. Le playbook SOUS-ESTIME donc structurellement
   le degat que l'ability infligera. `minDmg` est dans `variablesAffectedByRarityBonus` ->
   `ability_var` applique le multiplicateur de rarete, comme partout ailleurs.

5. **AUCUN filtre de camp : le friendly-fire est COMPTE, et il est NEGATIF.** L'arbre est
   `Damageable(AdjacentUnits(Get(Target)))` -- ni `Enemies(...)`, ni `Friends(...)`. Un allie du
   caster adjacent a la cible produit donc son propre `ProbableDamageEvent`, et les TROIS feuilles
   dominantes du composite le NIENT : `IdunBattle.AI.Utilities.DamageUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext`,
   `IdunBattle.AI.Utilities.KillUnitUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext` et
   `IdunBattle.AI.Utilities.OverkillUnitUtility.u003CEvaluateAttackInStepsu003Ed__2$$MoveNext`
   multiplient chacune par `Fix64(-1)` quand `IsFriend(case.Caster, case.Target)` -- decompile LU
   pour les trois. C'est ce que porte le champ `friendly` de `ProbableDamageEvent` (dont ce module
   est le PREMIER consommateur). L'absence de filtre est CORROBOREE par la face COMBAT :
   `ShrapnelAbility$$CreateBehaviour` frappe des TUILES tirees au sort autour de la cible, donc
   allies compris.
   ⚠ `KillUnitUtility` porte deux branches que le port ne distingue pas : si
   `UnitExtensions.HasFriendlyFire(caster)` la negation se fait sur `IsEnemy` (INVERSE), et un slot
   `0x93` d'`IBattleQuery` peut negger seul. Aucune des deux n'est atteignable dans le regime
   confronte (residu nomme dans la case-doc).

6. **La cible principale n'est JAMAIS comptee** -- non par un test, mais parce que
   `IdunBattleLogic.Entities.DSLSelectors$$AdjacentUnits` est
   `Units(AdjacentTiles(origin), unique, sel) op_Subtraction origin` : le `- origin` est DANS le
   selecteur. Meme forme que `RighteousRepugnance` (et l'INVERSE de `Boltstorm`, dont l'arbre a un
   `op_Addition` avec `Target@0x60` qui fait valoir 1 a toute cible isolee).

7. **Pas de cap a `nrOfProjectiles`.** La face COMBAT `ShrapnelAbility$$CreateBehaviour` fait
   `PickRandomly(AdjacentTiles(Target), GetNumberConstant(0x1f) = nrOfProjectiles = 3, ...)` puis
   `Cache` : elle ne frappe que 3 tuiles tirees au sort. Le playbook, lui, prend TOUTES les unites
   adjacentes damageables. C'est un ecart NATIF, assume : les deux corps sont lus separement et ne
   partagent aucun selecteur (meme forme d'ecart que `ElectroShock`, ou le playbook ignorait le
   `Damageable` et le gate `IsMeleeAttack` de sa face combat).

8. **`Damageable` = `UnitsWithoutTrait(Invincible)`, pas << vivant >>.**
   `IdunBattleLogic.Entities.DSLSelectors$$Damageable` = `UnitsWithoutTrait(entities, 0x40e, 3)`, et
   `0x40e` = 1038 = `UnitTrait.Invincible` -- enum a QUALIFIER : a id egal,
   `TriggeredAbilityType` 1038 = `HatefulAssault`, `ActiveAbilityType` 1038 = `FoulInfusion`,
   `EffectType` 1038 = `CloudOfFlies_DamageReduction`. Le filtre << vivant >>, lui, vient d'ailleurs :
   `AdjacentTiles` resout des OCCUPANTS DE TUILE et un mort a quitte la sienne.

9. **Le profil est le LITTERAL `Blast`**, pas l'arme du caster : le 6e argument du slot 0x23 est
   `Nullable<DamageProfileType>(0x12)`, et `0x12` = 18 = `Blast` (`PiercingRatio` 15, trait
   `HitsMultipleMembers`). MEME litteral que la face COMBAT. Le corps ne consulte donc NI l'arme, NI
   les stats, NI les traits du caster -- seulement son identite (pipeline modifiers), sa position, et
   le NIVEAU de son propre passif 1116 (`GetAbilityState`). C'est exactement ce qui rend la greffe
   legitime pour la confrontation (cf. case-doc §montage).

## La geometrie, jusqu'a la feuille

`AdjacentTiles(origin)` -> `IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select`, qui appelle
le slot `0x50` d'`IBattleQuery` avec les quatre litteraux `(entity, 0, 1, 1)` =
`IterateAdjacentTiles(from, onlyEmptyOrSteppable: false, onlyWalkableTiles: true,
allowTemporary: true)` puis EXCLUT les tuiles de l'origine. C'est le MEME
`IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext` que
`fire_of_absolution.count_adjacent_by_camp` et `boltstorm.count_all_targets`, donc la porte
d'elevation INCONDITIONNELLE `|elev(a) - elev(b)| < 2` s'applique : foyer `battle_query.is_adjacent`,
jamais `hexgeo.distance == 1` (qui SUR-COMPTE).

`SelectUniqueUnits(entities, 3)` (`IdunBattle.DSL.TargetsSelector$$SelectUniqueUnits`) resout chaque
entite par `SelectUnit(e, 3)` et DEDOUBLONNE (`ArraySet.Add` -> `ToList`). L'`AbilityEntities` que le
playbook lui passe est **entierement memset a 0** (aucun `Caster`, `Target`, `CasterTile`), ce qui est
sans effet ici : `DSLSelectors.Get(entity)` capture l'entite a la CONSTRUCTION du selecteur.

## Les deux sorties nulles ne sont PAS la meme

* `!IsRegularAttack(case)` -> `yield break` : **aucun** step emis.
* aucune unite adjacente damageable -> la boucle `MoveNext` rend faux au premier appel, et le corps
  yield `acc` qui vaut encore `Fix64(0)` -> **un** step a 0.

Le dispatcher SOMME les steps, donc les deux sont observationnellement `0.0` ; la distinction est
notee parce qu'elle ne serait pas neutre sous un agregateur qui moyenne (acquis de #514/#518).

## Face MOVE : `yield Fix64(0)` CONSTANT -- ce n'est PAS un residu

`ShrapnelPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` a ete LU : un
unique etat, `Fix64.op_Implicit(0)`, aucun champ de la SM consulte. Elle n'entre donc pas dans
`TRIGGERED_MOVE_PLAYBOOKS`, et **son absence EST le comportement natif** (meme forme que `Lakrimae`,
`BarbedOvipositor`, `Neuroparasite`, `Boltstorm`, `FireOfAbsolution`, `CosmicHorror`, `ElectroShock`).

## Registre `ABILITY_CLASSES` : sans objet

`Shrapnel` est un TRIGGERED (`PassiveAbilityType` 1116), pas une ACTIVE : il n'entre pas dans
`ABILITY_CLASSES` et ne porte donc ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` (ces deux donnees
sont celles du registre des actives). Le seul registre concerne est
`TRIGGERED_ATTACK_PLAYBOOKS` (`playbook/psyker.py`), pose dans le meme commit.
"""
from __future__ import annotations

import gameconfig as GC

from .. import battle_query as bq
from ..entities.effects import calculate_attacker_modifiers_for_prediction
from ..entities.effects.magnitude import ability_var
from ..entities.stats import ARMOR_STAT_TYPES
from ..entities.traits import target_hit_multiplier
from ..entities.traits.factory import TraitFactory
from ..entities.traits.unit_trait import UnitTrait
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..runner.abilities.attack_type import is_regular_attack
from ..services.damage_prediction import get_attack_prediction
from .probable_damage_event import ProbableDamageEvent, calculate_utility_from_damage_event
from .prediction._shared import _entity_traits, _prediction_is_charging
from .prediction._shared import (
    _PROFILE_INDEX, _add_positional_and_defender_mods, _apply_ally_attack_dmg_bonus,
from .prediction._shared import _entity_rarity   # #1025-r1 (rarete de la CIBLE)
    _target_damage_limits, prediction_has_moved, prediction_has_teleported
)

# Cle gameconfig de l'ability : l'enum membre EST le nom de config.
_ABILITY_NAME = TriggeredAbilityType.Shrapnel.name          # "Shrapnel"
# `GetVariableForLevel(config, 0xc, ...)` -- index 12 = `minDmg` (foyer deja etabli, cf. en-tete
# lecture 4). Le corps ne lit PAS `0xd = maxDmg`.
_VAR_MIN_DAMAGE = "minDmg"
# `GetNumberConstant(config, 0x2f)` -- `nrOfHits` (index deja etabli par `light_im_up`,
# `excruciating_frequencies`, `fire_of_absolution`, `loki_custom`).
_CONST_HITS = "nrOfHits"
# `Nullable<DamageProfileType>(0x12)` -- le LITTERAL du call-site du slot 0x23 (en-tete lecture 9).
_PROFILE_NAME = "Blast"
# `Damageable(x)` = `UnitsWithoutTrait(x, 0x40e, 3)` -- 1038, `UnitTrait.Invincible` (en-tete
# lecture 8 : enum QUALIFIE).
_INVINCIBLE = UnitTrait.Invincible.name


def splash_targets(scene, caster_uid: int, target_uid: int) -> list:
    """`Damageable(AdjacentUnits(Get(case.Target), unique: 1, sel: 3)).SelectUniqueUnits(∅, 3)`.

    = les unites qui OCCUPENT une tuile du ring-1 de la cible (porte d'elevation `|delta| < 2`
    d'`IterateAdjacentTiles`) et qui n'ont PAS le trait `Invincible`. AUCUN filtre de camp : les
    ALLIES du caster en font partie (en-tete lecture 5), et le CASTER lui-meme aussi s'il est
    adjacent a sa propre cible -- le selecteur ne soustrait QUE l'origine.

    La cible principale n'y figure jamais : elle est a distance 0 d'elle-meme, donc hors de son
    propre ring-1 (`- origin` du selecteur, en-tete lecture 6). Les unites MORTES sont exclues parce
    que le selecteur resout des occupants de tuile et qu'un mort a quitte la sienne (meme regle que
    `dsl/base.py::_within` #57m, `boltstorm.count_all_targets` et `fire_of_absolution`).

    Degradation, NOMMEE et rendant `[]` : cible sans position connue. Le natif, lui, n'a aucune
    sortie anticipee -- il deref sans garde et tombe sur une levee ; on ne mirrore pas une levee."""
    if target_uid is None:
        return []
    tpos = scene.pos(target_uid)
    if tpos is None:
        return []
    elev = getattr(scene, "elev_by_pos", None)
    neigh = bq.neigh_map(scene)
    out = []
    for u in (scene.units or ()):
        uid = u.get("id")
        if uid is None or uid == target_uid or not u.get("alive"):
            continue
        p = scene.pos(uid)
        if p is None or not bq.is_adjacent(tpos, (p[0], p[1]), elev, neigh):
            continue
        if _INVINCIBLE in _entity_traits(scene, uid):     # `UnitsWithoutTrait(0x40e)`
            continue
        out.append(uid)
    return out


class ShrapnelPlaybook:
    """`ShrapnelPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1116 -- l'id passe par `$$.ctor` a
    la base `TriggeredAbilityPlaybook<T>` est bien `0x45c`). Seule la face ATTACK a un corps ; la face
    MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.Shrapnel)        # 0x45c = 1116

    # ---- mirror `AbilityConfiguration.GetVariableForLevel(config, 0xc = minDmg, state, false)` ----
    def _min_damage(self, scene, uid: int) -> "int | None":
        """Le montant PREDEFINI que le playbook predit contre chaque voisin (en-tete lecture 4).

        `abilityState` = `TriggeredAbilityPlaybook<T>$$GetAbilityState(case.Caster)` ->
        `TriggeredAbilityComponent$$GetAbilityState` : le couple `(Level,
        VariableMultiplierPercentage)` PER-ABILITY (canal #100 `scene.ability_state`). Repli sur le
        canal GLOBAL (`ablvl_by_id` = niveau des passifs, `mult_by_id`) quand le capteur per-ability
        est absent -- MEME cascade que `avalanche_of_muscle._extra_damage`.

        `fallbackToDefault: false` : le natif LEVE si la variable manque. Le port rend `None`, que
        l'appelant traite comme << aucun terme >>."""
        st = scene.ability_state(uid, self.ability_id) or {}
        lvl = st.get("level")
        if lvl is None:
            lvl = (scene.ablvl_by_id or {}).get(uid)
        mult = st.get("multiplier")
        if mult is None:
            mult = (scene.mult_by_id or {}).get(uid)
        return ability_var(_ABILITY_NAME, _VAR_MIN_DAMAGE, lvl, multiplier_pct=int(mult or 100))

    # ---- mirror `AbilityConfiguration.GetNumberConstant(config, 0x2f = nrOfHits)` ----------------
    @staticmethod
    def _hits() -> int:
        """`nrOfHits` de la config `Shrapnel` (= 2 sur le gameconfig courant). Le natif le relit a
        CHAQUE iteration de la boucle de cibles ; il est invariant, donc hisse ici. `GetNumberConstant`
        LEVE sur cle absente (`GetStringConstant` -> `TryGetValue`), le port rend 0 = aucun terme."""
        c = ((GC.ability(_ABILITY_NAME) or {}).get("constants") or {}).get(_CONST_HITS)
        return int(c or 0)

    # ---- mirror slot 0x23 : prediction d'un MONTANT predefini vs un voisin ----------------------
    def _predict_vs(self, scene, att_id: int, tgt_id: int, amount: int, attack_pos):
        """`IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` (slot 0x23) ->
        `IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` : montant DONNE,
        **hits FORCES a 1** (le litteral `1` que le call-site passe au slot 10 d'
        `IDamagePredictionQuery`), spread +/-20 % (#449), profil = le LITTERAL `Blast` resolu par
        `BattleQuery$$GetDamageProfile(caster, 0x12)`. Pipeline modifiers / armure / bouclier / caps
        COMPLET vs la cible, depuis la TUILE D'ATTAQUE `attack_pos` (mods positionnels).

        MEME regime que `psyker._predict_amount_vs_target` -- profil LITTERAL, pas d'arme selectionnee
        -- donc le pierce vient du `PiercingRatio` du profil (15 pour `Blast`) plus les bonus de
        percage de l'attaquant, et non de `select_weapon_pierce`.

        `is_ranged=True` : le passif ne se declenche QUE sur une attaque a distance
        (`ShrapnelAbility$$CreateTrigger` = `On(0x26) & OwnerIsCaster & IsRangedAttack`) et sa config
        porte `attackRangeType: Ranged`. Le corps du playbook ne calcule PAS ce booleen lui-meme (il
        n'appelle ni `IsMeleeAttack` ni `FindRangedWeapon`) : c'est la requete native qui le derive.
        Les deux sources concordent -- residu nomme si aucun modifier ranged-conditionnel ne
        l'exerce.

        `is_normal_attack=True` : la gate `IsRegularAttack` du corps garantit que le `ability =
        case.AbilityType` transmis a la requete EST une attaque normale (meme raisonnement que
        `light_im_up`)."""
        actx = scene.ctx(att_id)
        if actx is None:
            return None
        prof = GC.damage_profile(_PROFILE_NAME) or {}
        pierce = max(0, min(100, int(prof.get("PiercingRatio") or 0)
                            + actx.extra_pierce + actx.extra_pierce_ranged))
        _hm = prediction_has_moved(scene, att_id, attack_pos)
        _tctx = scene.ctx(tgt_id)
        _tar = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                if _tctx is not None and _tctx.stats is not None else None)
        # #316/#267-r1 : substrat d'ENTITE pour les effets target-conditionnels de l'ATTAQUANT.
        _tgt_traits = _entity_traits(scene, tgt_id)
        mods = calculate_attacker_modifiers_for_prediction(
            scene.effects(att_id), is_ranged=True, has_moved=_hm, is_normal_attack=True,
            target_traits=_tgt_traits, target_armor_reduced=_tar,
            att_ctx={"att_pos": attack_pos,
                     "tile_effects_by_pos": scene.tile_effects_by_pos,
                     "is_charging": _prediction_is_charging(scene, att_id, attack_pos, tgt_id),
                     "has_teleported": prediction_has_teleported(scene, att_id, attack_pos),
                     "att_grand_alliance": (GC.unit(scene.vis_by_id.get(att_id))
                                            or {}).get("GrandAllianceId"),
                     "damage_profile": _PROFILE_NAME,
                     "t_pos": scene.pos(tgt_id),
                     "tgt_team": scene.team(tgt_id),
                     # #1025-r1 -- `HasRarity(Target@<DSLSelectors+0x60>, idun.meta.Rarity
                     # .Mythic = 5)` + `AreFriends(Target@<DSLSelectors+0x60>, EffectSource(
                     # Effect@<DSLSelectors+0x38>))`, les deux conjoints utiles d'`Electrochaff
                     # Backups_DamageReductionPct` (1446). Son `$$CreateDamageModifier` ne porte
                     # NI `IsNormalAttack` NI `IsMeleeAttack` -> il entre AUSSI sur ce vecteur.
                     # MEMES cles que la normale et que la face COMBAT -- pas de fork. TRI-ETAT
                     # sur la rarete (`None` = non mesure -> gate FERME), cf. `_entity_rarity`.
                     "tgt_rarity": _entity_rarity(scene, tgt_id),
                     "team_by_id": scene.team_by_id})
        _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, False, attack_pos,
                                          scene.pos(tgt_id), damage_profile=_PROFILE_NAME,
                                          is_normal_attack=True)
        _apply_ally_attack_dmg_bonus(mods, scene, att_id, attack_pos, False, _tar,
                                     damage_profile=_PROFILE_NAME)
        hit_mult = target_hit_multiplier(TraitFactory.create_many(_tgt_traits))
        return get_attack_prediction(
            target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount),
            hits=1,                                   # slot 0x23 : hits FORCES 1 (litteral natif)
            profile_type=_PROFILE_INDEX.get(_PROFILE_NAME, 0), pierce_pct=pierce,
            # spread_pct : le DEFAUT (+/-20 %), #449 -- `request+0x6a = 1` route vers
            # `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64`.
            armor=scene.armor(tgt_id), mods=mods, hit_mult=hit_mult,
            target_shield=scene.shield(tgt_id), target_limits=_target_damage_limits(scene, tgt_id),
            target_prevents_overkill=scene.prevents_overkill(tgt_id),
            attacker_effects=scene.effects(att_id),
            attacker_ctx=actx)

    # ---- mirror `<CalculateAttackUtilityInStepsInternal>d__2$$MoveNext` -------------------------
    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror du corps natif (cf. en-tete), dans l'ORDRE : gate `IsRegularAttack`, puis la SOMME
        sur les voisins damageables de la cible de `nrOfHits x` l'utilite d'une prediction de montant
        `minDmg` au profil `Blast`.

        `prediction` (`case.DamagePrediction`, `UtilityAttackCase@+0x28`) est ACCEPTE et IGNORE : le
        corps natif ne lit pas ce champ, il fabrique ses PROPRES predictions (celles du splash)."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None:
            return 0.0
        # gate -- `TriggeredAbilityPlaybook<T>$$IsRegularAttack(case)` : `Contains` sur l'`OrderedSet`
        # statique de `StaticBattleRules.ActiveAbility` (foyer `attack_type`). Faux -> `yield break`.
        if ability_id is None or not is_regular_attack(int(ability_id)):
            return 0.0
        targets = splash_targets(sc, attacker_uid, case_tgt_id)
        if not targets:
            return 0.0                     # boucle vide -> `yield acc` avec `acc == Fix64(0)`
        amount = self._min_damage(sc, attacker_uid)
        if not amount:
            return 0.0
        hits = self._hits()
        if hits <= 0:
            return 0.0
        cteam = sc.team(attacker_uid)
        total = 0.0
        for u_id in targets:
            pred = self._predict_vs(sc, attacker_uid, u_id, int(amount), attack_tile)
            if pred is None:
                continue
            # `friendly` = `IsFriend(case.Caster, case.Target)` des trois feuilles dominantes du
            # composite Damage, qui multiplient chacune par `Fix64(-1)` (en-tete lecture 5). Le
            # CASTER est son propre ami -- s'il est adjacent a sa cible, son propre event est nie.
            t_u = sc.team(u_id)
            friendly = cteam is not None and t_u is not None and t_u == cteam
            ev = ProbableDamageEvent(target=u_id, prediction=pred, friendly=friendly)
            u = calculate_utility_from_damage_event(ev, ctx.wt,
                                                    (ctx.hpmax_by_id or {}).get(u_id))
            total += hits * u              # `for (i < nrOfHits) acc += CalculateUtility...`
        return total


__all__ = ["ShrapnelPlaybook", "splash_targets"]
