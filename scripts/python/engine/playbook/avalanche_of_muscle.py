"""`IdunBattle.AI.Playbook.Loki.AvalancheOfMusclePlaybook` -- face ATTACK du triggered
`AvalancheOfMuscle` (1028), passif d'`astraBullgryn` << Kut >> (HERO, au pool) et de 4 npc
`astraBossBullgryn*` / `astraNpcBullgryn` : 5 porteurs DISPATCHES, quatrieme des residus ATTACK
de #419.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(35), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae et BarbedOvipositor
(`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

(!) PIEGE DU NOM, leve : `1028` designe TROIS artefacts distincts, et l'entree deja portee cote
EFFET n'est AUCUN des deux autres. Enums QUALIFIES :
`TriggeredAbilityType.AvalancheOfMuscle = 1028` (CE playbook), `ActiveAbilityType.SupremeCommander
= 1028`, `EffectType.HeadClaimer_ExtraDmg = 1028`. L'effet du passif, lui, est
`EffectType.AvalancheOfMuscle_ExtraDamage = 1025` (`AvalancheOfMuscleExtraDamageEffect`, deja
porte) -- c'est la face COMBAT du MEME passif, pas cette face-ci.

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.AvalancheOfMusclePlaybook$$CalculateAttackUtilityInStepsInternal`
monte la SM `d__2` (case @+0x20, playbook @+0x28) ; le corps est
`AvalancheOfMusclePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`,
**SEPT** etats de yield, dans CET ordre :

    mainTile   = EntityExtensions.GetMainTile(case.Caster)          // case@+0x10
    casterTile = case.CasterPosition.MainTile                       // case@+0x18

    if (case.AbilityType.HasValue                                   // case@+0xf0
        && case.AbilityType.Value == (AbilityOrEffect)(TriggeredAbilityType)1028)
        yield Fix64(0)                                              // etat 1 (ANTI-RECURSION)
    if (!EntityExtensions.IsUnit(case.Target))                      // case@+0x20
        yield Fix64(0)                                              // etat 2
    else if (casterTile == mainTile)
        yield Fix64(0)                                              // etat 3  (le caster NE BOUGE PAS)
    else if (!battleQuery.<slot 0x60>(casterTile, case.Target))
        yield Fix64(0)                                              // etat 4  (pas adjacent APRES)
    else {
        w = battleQuery.<slot 0xaf>(case.Caster, [casterTile], case.Target)
        if (w == null) yield Fix64(0)                               // etat 5  (aucune arme)
        else if (!CameIntoContactWithEnemy(case)) yield Fix64(0)    // etat 6  (deja au contact AVANT)
        else {
            extra = ability.GetExtraDamage(UnitExtensions.GetAbilityState(case.Caster, 1028).Value)
            pred  = battleQuery.<slot 0x23>(case.Caster, case.Target, casterTile,
                                            case.AbilityType, extra, (DamageProfileType?)w.<+0x10>,
                                            false, null)
            yield CalculateUtilityFromDamageEvent(new ProbableDamageEvent(case.Target, pred),
                                                  case.Caster, case.CasterPosition)   // etat 7
        }
    }

`IdunBattle.AI.Playbook.Loki.AvalancheOfMusclePlaybook$$CameIntoContactWithEnemy(case)` (methode
PROPRE au playbook, decompilee separement -- et le corps de `d__2` la RE-INLINE a l'identique) :

    return  <slot 0x62>( [casterTile],            GetTiles(case.Target) )
         && !<slot 0x62>( GetTiles(case.Caster),  GetTiles(case.Target) )

Sept lectures qui ne se devinent pas, et dont aucune ne se generalise depuis un voisin :

1. **Ce playbook ne lit PAS `case.DamagePrediction`** (contrairement a `BarbedOvipositor`, #438) :
   il en fabrique une NOUVELLE, celle du bonus de charge. Le parametre `prediction` est donc
   accepte et IGNORE, exactement comme le corps natif ignore `case@+0x28`.

2. **L'etat 1 est un ANTI-RECURSION, pas un gate metier.** `TriggeredAbilityPlaybook<T>$$
   CalculateUtilityFromDamageEvent` (l'etat 7) reconstruit un `UtilityAttackCase` par
   `IdunBattle.AI.Utilities.UtilityAttackCase$$ForDamagePrediction` en y posant
   `abilityType = (AbilityOrEffect)T` -- soit **triggered 1028** -- puis evalue le composite
   `UtilityType.Damage` (0x23 = 35), qui contient la feuille `TriggeredAbilities(2)`, qui
   re-dispatche ce meme playbook. L'etat 1 est ce qui coupe la boucle. **Il n'est atteignable
   par AUCUN chemin du port** : `calculate_utility_from_damage_event` n'evalue que les trois
   feuilles dominantes du composite (`engine/utilities/damage.py::DAMAGE_UTILITY`), la feuille
   triggered etant ajoutee HORS composite par `playbook/base.py`. Le porter en
   `ability_id == 1028` serait FAUX : `ability_id` porte ici un `ActiveAbilityType`, dont la
   valeur 1028 est `SupremeCommander`. Residu nomme, cf. la case-doc.

3. **L'etat 3 exige un MOUVEMENT REEL** (`casterTile != mainTile`), pas seulement l'adjacence
   finale. `get_MovementTile` est un corps DEDUPLIQUE (`UnitPosition$$get_MainTile(this+0x18)`) :
   applique a un `UtilityAttackCase`, `+0x18` est `casterPosition`
   (`IdunBattle.AI.Utilities.UtilityAttackCase$$.ctor` : caster@+0x10, casterPosition@+0x18,
   target@+0x20, damagePrediction@+0x28, heal@+0xd0, repair@+0xdc, effectType@+0xe8,
   abilityType@+0xf0). Le nom `UtilityMovementCase` de la table est un mislabel de deduplication,
   pas un indice de type.

4. **Le predicat n'est PAS `IsCharging`** meme s'il en est le jumeau semantique. Le natif ne route
   pas ici vers `IdunBattle.Core.Services.BattleQuery$$IsCharging` (qui lit
   `UnitComponent.ChargedUnitIds@+0x190`) : il compare les tuiles AVANT/APRES. La difference est
   observable -- `CameIntoContactWithEnemy` ignore les charges DEJA acquises ce tour. On mirrore
   donc le decompile, pas le foyer `battle_query.is_charging`.

5. **L'adjacence est celle de `MovementUtil$$AreTilesAdjacent(Tile, Tile)`** (decompile lu) =
   `|elev1 - elev2| < 2 && (tile1 == tile2 || ConnectivityComponent.IsNeighbour)`. Porte
   d'elevation INCONDITIONNELLE -> le foyer du port est `battle_query.is_adjacent`, jamais une
   adjacence hex nue.

6. **Le montant est `extraDmg`, la MEME variable que la face COMBAT.**
   `IdunBattleLogic.Entities.Abilities.Active.Loki.AvalancheOfMuscleAbility$$GetExtraDamage` =
   `AbilityConfiguration.GetVariableForLevel(config, 8, abilityState, fallbackToDefault: false)`,
   et `AvalancheOfMuscleTargetEffect$$CreateEffectDamageBonusForAttack` appelle
   `ConfigVar(config, 8, GetAbilityState, ...)` sur la MEME config. `AvalancheOfMuscle` n'a qu'UNE
   variable au gameconfig (`extraDmg`) et `fallbackToDefault` vaut `false` (le natif LEVE si la
   variable manque) -> l'index 8 ne peut designer qu'elle. `extraDmg` est dans
   `variablesAffectedByRarityBonus` : `ability_var` applique le multiplicateur de rarete, comme
   `AvalancheOfMuscleExtraDamageEffect`.

7. **La prediction est celle du slot 0x23**, `IdunBattle.Core.Services.BattleQuery$$
   GetAttackPrediction(caster, target, casterTile, ability, amount, Nullable<DamageProfileType>,
   ...)` : montant DONNE, **hits FORCES a 1** (litteral `1` passe au slot 10 d'
   `IDamagePredictionQuery`), et le montant PASSE PAR LE SPREAD +/-20 % -- meme canal que
   `psyker.py` et `fury_of_the_ancients.py`, et le meme que le slot 0x28 de `LightImUp`.
   ⚠ #449 : la premiere version de ce port ecrivait << canal predefini, spread 0 >>. C'est FAUX,
   et la faute etait invisible du canal qui l'avait validee (`pairUtility` -> composite Damage
   -> `MinMaxDamage$$Avg`, la MOYENNE des deux bornes : `avg(0.8d, 1.2d) == d`).
   `IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` ecrit le LITTERAL `1` a
   `DamagePredictionRequest+0x6a`, et c'est exactement l'octet que
   `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` teste pour router vers
   `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64` (slots 8/9 = 0,8 / 1,2).
   MESURE : montant `extraDmg` -> bornes natives [11, 13], la lecture << predefinie >> [12, 12].
   Le profil n'est PAS une constante d'ability : c'est `w.<+0x10>`, le `DamageProfile` de l'arme
   rendue par `GetAttackWeaponForDefaultNormalAttack(caster, [casterTile], target)` (foyer porte :
   `services/battle_query.py::select_weapon_pierce`, cf. `case-184`).

## Face MOVE : `yield Fix64(0)` CONSTANT

`AvalancheOfMusclePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` est
decompile LU : un unique `yield return Fix64.op_Implicit(0)`, rien d'autre. Elle n'entre donc pas
au registre `TRIGGERED_MOVE_PLAYBOOKS`, et son absence EST le comportement natif (meme forme que
`Lakrimae` et `BarbedOvipositor`).
"""
from __future__ import annotations

import hexgeo
import gameconfig as GC

from .. import battle_query as bq
from ..entities.effects import calculate_attacker_modifiers_for_prediction
from ..entities.effects.magnitude import ability_var
from ..entities.stats import ARMOR_STAT_TYPES
from ..entities.traits import target_hit_multiplier
from ..entities.traits.factory import TraitFactory
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..services.battle_query import select_weapon_pierce
from ..services.damage_prediction import get_attack_prediction
from .probable_damage_event import ProbableDamageEvent, calculate_utility_from_damage_event
from .prediction._shared import (
    _PROFILE_INDEX, _add_positional_and_defender_mods, _apply_ally_attack_dmg_bonus,
    _entity_traits, _target_damage_limits, prediction_has_moved, prediction_has_teleported
)
from .prediction._shared import _prediction_is_charging
from .prediction._shared import _entity_rarity   # #1025-r1 (rarete de la CIBLE)

# Cle gameconfig de l'ability : l'enum membre EST le nom de config.
_ABILITY_NAME = TriggeredAbilityType.AvalancheOfMuscle.name          # "AvalancheOfMuscle"
# `GetVariableForLevel(config, 8, ...)` -- var index 8 = `extraDmg`, SEULE variable de l'ability
# (cf. lecture 6 de l'en-tete ; MEME index que la face COMBAT `AvalancheOfMuscleExtraDamageEffect`).
_VAR_EXTRA_DAMAGE = "extraDmg"


class AvalancheOfMusclePlaybook:
    """`AvalancheOfMusclePlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1028). Seule la face
    ATTACK a un corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.AvalancheOfMuscle)     # 0x404 = 1028

    # ---- mirror `AvalancheOfMuscleAbility$$GetExtraDamage` -----------------------------------
    def _extra_damage(self, scene, uid: int) -> int | None:
        """`AbilityConfiguration.GetVariableForLevel(config, 8 = extraDmg, abilityState)`.

        `abilityState` = `UnitExtensions.GetAbilityState(caster, 1028)` -- le couple
        `(Level, VariableMultiplierPercentage)` PER-ABILITY (`ActiveAbility._abilityState`, canal
        #100 `scene.ability_state`). Repli sur le canal GLOBAL (`ablvl_by_id` = niveau des passifs,
        `mult_by_id`) quand le capteur per-ability est absent (contexte offline `from_state`) --
        MEME cascade que `AvalancheOfMuscleExtraDamageEffect` cote COMBAT."""
        st = scene.ability_state(uid, self.ability_id) or {}
        lvl = st.get("level")
        if lvl is None:
            lvl = (scene.ablvl_by_id or {}).get(uid)
        mult = st.get("multiplier")
        if mult is None:
            mult = (scene.mult_by_id or {}).get(uid)
        return ability_var(_ABILITY_NAME, _VAR_EXTRA_DAMAGE, lvl,
                           multiplier_pct=int(mult or 100))

    # ---- mirror slot 0x23 : prediction d'un MONTANT predefini vs la cible du case -------------
    def _predict_extra_vs_target(self, scene, att_id: int, tgt_id: int, amount: int, attack_pos,
                                 profile_name: str, is_ranged: bool, pierce: int,
                                 is_normal_attack: bool):
        """`BattleQuery$$GetAttackPrediction` (slot 0x23) -> `DamagePredictionQuery$$
        GetAttackPrediction` : montant DONNE (`amount`), **hits forces 1**, spread +/-20 %
        (#449, cf. lecture 7 de l'en-tete), profil
        = celui de l'ARME rendue par `GetAttackWeaponForDefaultNormalAttack`. Pipeline modifiers /
        armure / bouclier / caps COMPLET vs la cible, depuis la tuile CANDIDATE `attack_pos`
        (mods positionnels). Meme foyer que `psyker.py` et `fury_of_the_ancients.py`.

        `is_normal_attack` mirror l'argument `ability = case.AbilityType` que le natif transmet :
        c'est l'ability EVALUEE par le case, pas 1028.

        `att_ctx["is_charging"]` = le foyer PARTAGE `_prediction_is_charging` (case-r32) evalue
        depuis `attack_pos`. Sans la cle, `is_not_charging` laisserait passer les bonus de charge
        d'un contexte inconnu (polarite permissive) -- ici le regime EST une charge (etats 3/4/6),
        mais on lit le foyer plutot que d'ecrire `True`."""
        actx = scene.ctx(att_id)
        if actx is None:
            return None
        is_melee = not is_ranged
        _hm = prediction_has_moved(scene, att_id, attack_pos)
        _tctx = scene.ctx(tgt_id)
        _tar = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                if _tctx is not None and _tctx.stats is not None else None)
        # #316/#267-r1 : substrat d'ENTITE pour les effets target-conditionnels de l'ATTAQUANT
        # (BeastSlayer vs BigTarget, MartialKatah vs Summon) -- MEME source que la normale et que
        # le vecteur ABILITY (`prediction/abilities.py`), qui a ete corrige par MESURE sur ce point.
        _tgt_traits = _entity_traits(scene, tgt_id)
        mods = calculate_attacker_modifiers_for_prediction(
            scene.effects(att_id), is_ranged=is_ranged, has_moved=_hm,
            is_normal_attack=is_normal_attack, target_traits=_tgt_traits,
            target_armor_reduced=_tar,
            att_ctx={"att_pos": attack_pos,
                     "tile_effects_by_pos": scene.tile_effects_by_pos,
                     "is_charging": _prediction_is_charging(scene, att_id, attack_pos, tgt_id),
                     "has_teleported": prediction_has_teleported(scene, att_id, attack_pos),
                     "att_grand_alliance": (GC.unit(scene.vis_by_id.get(att_id))
                                            or {}).get("GrandAllianceId"),
                     "damage_profile": profile_name,
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
        _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, is_melee, attack_pos,
                                          scene.pos(tgt_id), damage_profile=profile_name,
                                          is_normal_attack=is_normal_attack)
        _apply_ally_attack_dmg_bonus(mods, scene, att_id, attack_pos, is_melee, _tar,
                                     damage_profile=profile_name)
        hit_mult = target_hit_multiplier(TraitFactory.create_many(_entity_traits(scene, tgt_id)))
        return get_attack_prediction(
            target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount),
            hits=1,                                   # slot 0x23 : hits FORCES 1 (litteral natif)
            profile_type=_PROFILE_INDEX.get(profile_name, 0), pierce_pct=pierce,
            # spread_pct : le DEFAUT (+/-20 %). #449 -- MESURE DIRECTE sur les bornes capturees
            # (`ProbableDamageEvent$$.ctor`) : natif [11, 13], port a spread 0 [12, 12].
            armor=scene.armor(tgt_id), mods=mods, hit_mult=hit_mult,
            target_shield=scene.shield(tgt_id), target_limits=_target_damage_limits(scene, tgt_id),
            target_prevents_overkill=scene.prevents_overkill(tgt_id),
            attacker_effects=scene.effects(att_id),
            attacker_ctx=actx)

    # ---- mirror `AvalancheOfMusclePlaybook$$CameIntoContactWithEnemy` -------------------------
    @staticmethod
    def _came_into_contact_with_enemy(scene, caster_pos, attack_tile, tgt_pos) -> bool:
        """`<slot 0x62>([casterTile], GetTiles(target)) && !<slot 0x62>(GetTiles(caster),
        GetTiles(target))` -- devient adjacent PAR le pas, ne l'etait pas AVANT. Les deux appels
        sont `MovementUtil$$AreTilesAdjacent`, d'ou le foyer `battle_query.is_adjacent` (porte
        d'elevation `|delta| < 2` incluse)."""
        elev = getattr(scene, "elev_by_pos", None)
        neigh = bq.neigh_map(scene)
        after = bq.is_adjacent(attack_tile, tgt_pos, elev, neigh)
        before = bq.is_adjacent(caster_pos, tgt_pos, elev, neigh)
        return bool(after and not before)

    # ---- mirror `<CalculateAttackUtilityInStepsInternal>d__2$$MoveNext` -----------------------
    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror du corps natif (cf. en-tete), dans l'ORDRE des sept etats.

        `prediction` (`case.DamagePrediction`) est ACCEPTE et IGNORE : le corps natif ne lit pas
        `UtilityAttackCase@+0x28`, il fabrique sa PROPRE prediction (celle du bonus de charge)."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None:
            return 0.0
        # etat 2 -- `EntityExtensions.IsUnit(case.Target)`. `decisionView.units` ne porte que des
        # squads (les MACHINES sont une autre entite, sans `UnitComponent`) : l'appartenance a
        # `scene.units` EST le predicat, et une cible TUILE n'y figure pas davantage.
        tgt = next((u for u in (sc.units or []) if u.get("id") == case_tgt_id), None)
        if tgt is None:
            return 0.0
        tpos = sc.pos(case_tgt_id)
        cur = sc.pos(attacker_uid)
        if tpos is None or cur is None:
            return 0.0
        # etat 3 -- `casterPosition.MainTile == GetMainTile(caster)` : le caster NE BOUGE PAS.
        if tuple(attack_tile) == tuple(cur):
            return 0.0
        elev = getattr(sc, "elev_by_pos", None)
        neigh = bq.neigh_map(sc)
        # etat 4 -- `<slot 0x60>(casterTile, case.Target)` = `AreEntitiesAdjacent(Tile, IEntity)`.
        # Foyer `are_entities_adjacent`, PAS `is_adjacent` : la primitive de portee porte le
        # court-circuit d'identite (#433-r1) que le mirror d'`IterateAdjacentTiles` n'a pas.
        # REGIME INATTEIGNABLE ICI (`attack_tile` est une tuile ou le caster PEUT aller, donc pas la
        # position d'une cible vivante) -- pose par FIDELITE.
        if not bq.are_entities_adjacent(attack_tile, tpos, elev, neigh):
            return 0.0
        # etat 5 -- `GetAttackWeaponForDefaultNormalAttack(caster, [casterTile], target) == null`.
        # `select_weapon_pierce` rend `profile_name is None` exactement dans ce cas (`w is None`).
        actx = sc.ctx(attacker_uid)
        if actx is None:
            return 0.0
        d = hexgeo.distance(tuple(attack_tile), tuple(tpos))
        pierce, is_ranged, _hits, prof_name = select_weapon_pierce(actx, d <= 1, d)
        if prof_name is None:
            return 0.0
        # etat 6 -- `CameIntoContactWithEnemy(case)`.
        if not self._came_into_contact_with_enemy(sc, cur, attack_tile, tpos):
            return 0.0
        # etat 7 -- extraDmg -> prediction (slot 0x23) -> CalculateUtilityFromDamageEvent.
        extra = self._extra_damage(sc, attacker_uid)
        if not extra:
            return 0.0
        # `ability = case.AbilityType` : l'ability EVALUEE par le case (jamais 1028). `normal_ids`
        # = les ids d'attaque normale de l'unite (`ActiveAbility$$IsRegularAttack`, cf. psyker.py).
        is_normal = ability_id is not None and int(ability_id) in (ctx.normal_ids or ())
        pred = self._predict_extra_vs_target(sc, attacker_uid, case_tgt_id, int(extra),
                                             attack_tile, prof_name, is_ranged, pierce, is_normal)
        if pred is None:
            return 0.0
        ev = ProbableDamageEvent(target=case_tgt_id, prediction=pred)
        return calculate_utility_from_damage_event(ev, ctx.wt,
                                                   (ctx.hpmax_by_id or {}).get(case_tgt_id))
