"""`IdunBattle.AI.Playbook.Loki.HeavyBoltPistolPlaybook` -- face ATTACK du triggered
`HeavyBoltPistol` (1083), passif du SUMMON `templInitiate` et du npc `templNpc1Initiate` :
2 porteurs DISPATCHES, tranche 14 des residus ATTACK de #419-r1.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(35), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae, BarbedOvipositor, Neuroparasite, SaviorProtocols,
AvalancheOfMuscle, Boltstorm, FireOfAbsolution, CosmicHorror, LightImUp, RapidFire,
RighteousRepugnance, SpecialIssueCombiMelta, ElectroShock et Shrapnel
(`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

(!) PIEGE DU NOM, leve AVANT toute lecture : `1083` designe TROIS artefacts natifs sans rapport.
Enums QUALIFIES (`data/symbols/<build>/frida/enums.tsv`) --
`TriggeredAbilityType.HeavyBoltPistol = 1083` (CE playbook), `ActiveAbilityType.NeedsMoreDakka =
1083`, `EffectType.ChampionOfTheFeast_ReduceArmor = 1083`. Corollaire OUTILLAGE, MESURE :
`gameconfig.ability_name(1083)` rend **"NeedsMoreDakka"** (son index est celui d'`ActiveAbilityType`)
-- toute lecture de config passe donc par le NOM `"HeavyBoltPistol"`, jamais par l'id. Aucun autre
enum ne porte ce NOM : il n'y a pas de mold d'attaque normale sous un autre id (a l'inverse de
`RighteousRepugnance` 1107 -> 1182 ou d'`ElectroShock` 1303 -> 1178).

## Ce que le passif fait (tooltip i2, qui recoupe le decompile)

  << Deals an additional 1x 1091 Bolter Damage in melee. >>

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.HeavyBoltPistolPlaybook$$CalculateAttackUtilityInStepsInternal` monte la
SM `d__2` -- disposition LUE DANS LE WRAPPER, jamais par analogie : `sm@+0x10 = state`,
`sm@+0x18 = current`, `sm@+0x20 = this` (le PLAYBOOK), `sm@+0x28 = case`. Le troisieme parametre,
le delegue `getUtilityVal`, **n'est PAS capture** (comme `Neuroparasite`, `LightImUp` et `Shrapnel`) :
la sortie n'est AUCUNE cle de `Utilities.Default.TriggeredAbilities`. Le corps est
`HeavyBoltPistolPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`, DEUX etats
de yield, dont un SEUL est atteint par execution :

    if (IsRegularAttack(case)) {                       // TriggeredAbilityPlaybook<T>$$IsRegularAttack
        var dsl  = this.<DSLFactory @playbook+0x20>;
        var trig = DSLTriggers.IsAdjacent(dsl.<DSLTriggers @+0x88>,
                                          dsl.<DSLSelectors @+0x90>.Get(case.Caster),   // case@+0x10
                                          dsl.<DSLSelectors @+0x90>.Get(case.Target),   // case@+0x20
                                          unitSelectionType: 3);
        if (trig.ShouldTrigger(new AbilityEntities(/* memset 0x128 a 0 */))) {
            var cfg = this.<BaseTriggeredAbility @playbook+0x58>.<AbilityConfiguration @+0x20>;
            int dmg = AbilityConfiguration.GetVariableForLevel(
                          cfg, 0xb /* dmg */, GetAbilityState(case.Caster), fallbackToDefault: false);
            var pred = this.<IBattleQuery @playbook+0x60>.<slot 0x24>(
                          case.Caster, case.Target, case.CasterPosition,   // case@+0x10/+0x20/+0x18
                          case.AbilityType,                                // case@+0xf0
                          dmg, AbilityConfiguration.GetDamageProfile(cfg),
                          defenderInitialHealth: null, previousHitsPrediction: null);
            yield return CalculateUtilityFromDamageEvent(
                             new ProbableDamageEvent(case.Target, pred, null, null),
                             case.Caster, case.CasterPosition);            // etat 1
        }
    }
    yield return Fix64.op_Implicit(0);                                      // etat 2

Six lectures qui ne se devinent pas, et dont aucune ne se generalise depuis un voisin de la liste :

1. **La gate d'adjacence porte sur les positions REELLES, PAS sur la tuile d'attaque balayee.**
   C'est la lecture centrale de cette tranche, et elle est CONTRE-INTUITIVE : le corps construit un
   TRIGGER DSL `IsAdjacent(sel(case.Caster), sel(case.Target), 3)` dont les deux operandes sont des
   **ENTITES** (`IdunBattleLogic.Entities.DSLSelectors$$Get(entity)` capture l'entite a la
   CONSTRUCTION du selecteur -- c'est pourquoi l'`AbilityEntities` passe a `ShouldTrigger` peut etre
   entierement memset a 0 sans consequence). `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$
   ShouldTrigger` fait alors `a.Any() && b.Any() && a.All(x => b.All(y => query.<slot 0x60>(x, y)))`,
   et le slot 0x60 est `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent` ->
   `IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent(GetTiles(x), GetTiles(y))` : les tuiles
   REELLEMENT occupees. `case.CasterPosition` (`UtilityAttackCase@+0x18`) n'entre PAS dans la gate.
   Consequence directe et MESURABLE : le terme est CONSTANT sur tout le balayage de tuiles d'une
   meme cible -- il vaut 0 partout si le caster n'est pas deja au contact, et sa valeur pleine
   partout s'il l'est, y compris depuis une tuile d'attaque a 3 hex. Meme famille de quirk que
   `boltstorm` / `SavageEchoesAbility$$GetDamage` (#216), mais ici la conclusion s'INVERSE par
   rapport a `avalanche_of_muscle`, dont la gate `<slot 0x60>(casterTile, target)` prend bien la
   TUILE. Recopier le voisin donnerait un terme faux dans les deux sens.

2. **La tuile d'attaque, elle, entre PAR la prediction** (`case.CasterPosition` est le 3e argument du
   slot 0x24). Les modifiers positionnels, l'elevation et le predicat `is_melee` des effets
   d'attaquant s'evaluent donc DEPUIS ELLE, pendant que la gate reste ancree sur la tuile reelle.
   Les deux ancrages coexistent dans le MEME corps : les confondre deplace soit la gate, soit le
   dommage.

3. **Le canal de prediction est le slot 0x24, la surcharge `casterPosition` -- pas le 0x23.** Les
   slots d'`IBattleQuery` se lisent sur les proxys NOMMES de
   `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery`, dont chaque corps porte son
   `FUN_1801e7040(inner, <klass IBattleQuery>, <slot>)` :

       0x21 GetNormalAttackPrediction(caster, target, casterTile)
       0x22 GetNormalAttackPrediction(caster, target, casterPosition)
       0x23 GetAttackPrediction(caster, target, casterTILE,     ability, amount, profile, hp0, prev)
       0x24 GetAttackPrediction(caster, target, casterPOSITION, ability, amount, profile, hp0, prev)
       0x25/0x26/0x27 les surcharges a delegues `calculateDamageAtTile`
       0x28 GetMultiHitAttackPrediction(caster, target, casterPosition, ability, dmg, profile, hits)

   `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` (la surcharge `casterPosition`) ecrit
   le LITTERAL `1` comme nombre de coups au slot 10 d'`IDamagePredictionQuery` : **hits FORCES a 1**,
   exactement comme le 0x23 de `psyker` / `avalanche_of_muscle` / `shrapnel`. La difference 0x23 vs
   0x24 est le TYPE du 3e argument (`Tile` contre `UnitPosition`), sans effet observable ici -- mais
   elle est notee parce qu'elle a failli faire lire la mauvaise signature.

4. **Le montant est la variable `dmg` SEULE** -- `GetVariableForLevel(cfg, 0xb, state, false)`, et
   `AbilityVariableType` **11 = `dmg`** (`frida/enums.tsv`), la SEULE variable de la config
   `HeavyBoltPistol`. Ni `minDmg`/`maxDmg` (12/13, la paire de `LightImUp` et de `Shrapnel`), ni
   moyenne, ni tirage : le corps n'appelle `GetVariableForLevel` qu'UNE fois. `dmg` est dans
   `variablesAffectedByRarityBonus` -> `ability_var` applique le multiplicateur de rarete.

5. **Le profil est celui de l'ABILITY (`Bolter`), jamais l'arme du caster.** Le 6e argument du slot
   0x24 est `AbilityConfiguration.GetDamageProfile(cfg)` = `constants.damageProfile` = `Bolter`
   (`PiercingRatio` 20). Le corps ne consulte donc du caster NI arme, NI stat, NI trait -- seulement
   son identite (pipeline modifiers), sa position, et le NIVEAU de son propre passif 1083
   (`GetAbilityState`). C'est exactement ce qui rend la GREFFE legitime pour la confrontation
   (cf. case-doc §montage). `nrOfHits` (= 1) est present au gameconfig mais **le playbook ne le lit
   pas** : aucun `GetNumberConstant` dans le corps -- contrairement a `Shrapnel`, dont la boucle
   `for (i < nrOfHits)` multiplie l'utilite.

6. **`case.AbilityType` est l'ability transmise a la prediction, et c'est la MEME struct
   (`UtilityAttackCase@+0xf0`) que la gate `IsRegularAttack` interroge.**
   `TriggeredAbilityPlaybook<T>$$IsRegularAttack` deroule `Nullable<Nullable<ActiveAbilityType>>`
   depuis `case+0xf0` puis appelle
   `Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`.
   Consequence non devinable, identique a `LightImUp` : les gates `IsNormalAttack` / `IsMeleeAttack`
   des effets d'ATTAQUANT s'evaluent sur l'ATTAQUE NORMALE -- d'ou `is_normal_attack=True` dans le
   builder de modifiers, et `ExtraPierceMelee(21)` vs `ExtraPierceRanged(22)` choisis par le
   predicat `IsMeleeAttack` **re-evalue depuis la TUILE D'ATTAQUE**, non par la gate du corps.

## L'ability prise a l'envers -- un ECART NATIF assume

`IdunBattleLogic.Entities.Abilities.Active.Loki.HeavyBoltPistolAbility$$CreateBehaviour` :

    damageProfile = GetDamageProfile(cfg)                       // Bolter
    dmg           = GetVariableForLevel(cfg, 0xb, abilityState) // la MEME variable
    hits          = GetNumberConstant(cfg, 0x2f)                // nrOfHits = 1
    If( IsMeleeAttack(dsl.Triggers),                            // <- la gate de la face COMBAT
        InformWeapon(dsl.Behaviors, damageProfile, true, null)
        & AttackDamage(dsl.Behaviors, Owner@0x30, Target@0x60,
                       Direct(dmg), Direct(damageProfile), Direct(hits), ...),
        null )

La face COMBAT gate sur **`IsMeleeAttack`** (le slot 2, qui traverse `GetAbilityAttackRangeType` et
peut rendre vrai pour une ability typee `Melee` a n'importe quelle distance) ; la face DECISION gate
sur **`IsAdjacent(caster, target)`** (geometrie pure). Les deux corps sont lus separement et ne
partagent aucun predicat : le playbook APPROXIME la gate de l'ability. Meme forme d'ecart que
`FireOfAbsolution` (le caster compte parmi ses propres amis cote playbook, exclu cote behaviour) et
que `Shrapnel` (pas de cap `nrOfProjectiles` cote playbook).

## Face MOVE : `yield Fix64(0)` CONSTANT -- ce n'est PAS un residu

`HeavyBoltPistolPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` a ete LU :
un unique etat, `Fix64.op_Implicit(0)`, aucun champ de la SM consulte. Elle n'entre donc pas dans
`TRIGGERED_MOVE_PLAYBOOKS`, et **son absence EST le comportement natif** (meme forme que `Lakrimae`,
`BarbedOvipositor`, `Neuroparasite`, `Boltstorm`, `FireOfAbsolution`, `CosmicHorror`, `ElectroShock`
et `Shrapnel`).

## Registre `ABILITY_CLASSES` : sans objet

`HeavyBoltPistol` est un TRIGGERED (`PassiveAbilityType` 1083), pas une ACTIVE : il n'entre pas dans
`ABILITY_CLASSES` et ne porte donc ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` (ces deux donnees
sont celles du registre des abilities ACTIVES, et `HeavyBoltPistolAbility` est declenchee, jamais
castee). Le seul registre concerne est `TRIGGERED_ATTACK_PLAYBOOKS` (`playbook/psyker.py`), pose dans
le meme commit.
"""
from __future__ import annotations

import gameconfig as GC

from .. import battle_query as bq
from ..entities.effects import calculate_attacker_modifiers_for_prediction
from ..entities.effects.magnitude import ability_var
from ..entities.stats import ARMOR_STAT_TYPES
from ..entities.traits import target_hit_multiplier
from ..entities.traits.factory import TraitFactory
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..runner.abilities.attack_type import is_regular_attack
from ..services.battle_query import is_melee_attack
from ..services.damage_prediction import get_attack_prediction
from .probable_damage_event import ProbableDamageEvent, calculate_utility_from_damage_event
from .prediction._shared import (
    _PROFILE_INDEX, _add_positional_and_defender_mods, _apply_ally_attack_dmg_bonus,
    _entity_traits, _target_damage_limits, prediction_has_moved, prediction_has_teleported
)
from .prediction._shared import _prediction_is_charging, defender_prediction_block_amount
from .prediction._shared import _entity_rarity   # #1025-r1 (rarete de la CIBLE)

# Cle gameconfig de l'ability : le membre d'enum EST le nom de config. Le passer par
# `GC.ability_name(1083)` rendrait `"NeedsMoreDakka"` (index `ActiveAbilityType`) -- cf. en-tete.
_ABILITY_NAME = TriggeredAbilityType.HeavyBoltPistol.name        # "HeavyBoltPistol"
# `GetVariableForLevel(cfg, 0xb, ...)` -- `AbilityVariableType` 11 = `dmg` (en-tete, lecture 4).
_VAR_DAMAGE = "dmg"
# `AbilityConfiguration$$GetDamageProfile(cfg)` = `constants.damageProfile` (en-tete, lecture 5).
_CONST_PROFILE = "damageProfile"


class HeavyBoltPistolPlaybook:
    """`HeavyBoltPistolPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1083 -- l'id passe par
    `$$.ctor` a la base `TriggeredAbilityPlaybook<T>` est bien `0x43b`). Seule la face ATTACK a un
    corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.HeavyBoltPistol)   # 0x43b = 1083

    # ---- mirror `AbilityConfiguration.GetVariableForLevel(cfg, 0xb = dmg, state, false)` --------
    def _damage(self, scene, uid: int) -> "int | None":
        """Le montant PREDEFINI que le playbook predit contre `case.Target` (en-tete, lecture 4).

        `abilityState` = `TriggeredAbilityPlaybook<T>$$GetAbilityState(case.Caster)` : le couple
        `(Level, VariableMultiplierPercentage)` PER-ABILITY (canal #100 `scene.ability_state`).
        Repli sur le canal GLOBAL (`ablvl_by_id` = niveau des passifs, `mult_by_id`) quand le capteur
        per-ability est absent -- MEME cascade qu'`avalanche_of_muscle`, `light_im_up` et `shrapnel`.

        `fallbackToDefault: false` : le natif LEVE si la variable manque. Le port rend `None`, que
        l'appelant traite comme << aucun terme >>."""
        st = scene.ability_state(uid, self.ability_id) or {}
        lvl = st.get("level")
        if lvl is None:
            lvl = (scene.ablvl_by_id or {}).get(uid)
        mult = st.get("multiplier")
        if mult is None:
            mult = (scene.mult_by_id or {}).get(uid)
        return ability_var(_ABILITY_NAME, _VAR_DAMAGE, lvl, multiplier_pct=int(mult or 100))

    # ---- mirror `AbilityConfiguration$$GetDamageProfile(cfg)` -----------------------------------
    @staticmethod
    def _profile_name() -> str:
        """`constants.damageProfile` de la config `HeavyBoltPistol` (= `Bolter`, `PiercingRatio` 20).
        Ce N'EST PAS l'arme du caster (en-tete, lecture 5)."""
        return (((GC.ability(_ABILITY_NAME) or {}).get("constants") or {}).get(_CONST_PROFILE)
                or "")

    # ---- mirror `IsAdjacentAbilityTrigger$$ShouldTrigger` sur l'arbre du corps ------------------
    @staticmethod
    def should_trigger(scene, caster_uid: int, target_uid: int) -> bool:
        """`DSLTriggers.IsAdjacent(Get(case.Caster), Get(case.Target), 3).ShouldTrigger(NULL)`.

        Les deux selecteurs sont des CONSTANTES d'entite, donc les deux ensembles sont des
        singletons et la triple condition `a.Any() && b.Any() && a.All(x => b.All(y => ...))` se
        reduit a l'unique appel `<slot 0x60>(caster, target)` =
        `BattleQuery$$AreEntitiesAdjacent(IEntity, IEntity)` -> `MovementUtil$$AreTilesAdjacent`.
        Foyer `battle_query.are_entities_adjacent` (court-circuit d'identite #433-r1 compris), et
        surtout PAS `is_adjacent` (`IterateAdjacentTiles`, qui ne rend jamais la tuile source).

        L'ancre est la position REELLE des deux entites (en-tete, lecture 1) : `GetTiles(entity)`
        lit le `PositionComponent`, jamais `case.CasterPosition`.

        Degradation NOMMEE : position inconnue d'un des deux -> `False` (le natif, lui, deref sans
        garde -- une liste de tuiles vide rend deja `false` cote `AreTilesAdjacent(IList, IList)`,
        donc la polarite est la MEME)."""
        cpos = scene.pos(caster_uid)
        tpos = scene.pos(target_uid)
        if cpos is None or tpos is None:
            return False
        return bool(bq.are_entities_adjacent(cpos, tpos, getattr(scene, "elev_by_pos", None), bq.neigh_map(scene)))

    # ---- mirror slot 0x24 : prediction d'un MONTANT predefini vs `case.Target` ------------------
    def _predict_vs_target(self, scene, att_id: int, tgt_id: int, amount: int, attack_tile,
                           profile_name: str, is_melee: bool):
        """`IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` (slot 0x24, surcharge
        `casterPosition`) -> `IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` :
        montant DONNE, **hits FORCES a 1** (le litteral `1` que le call-site passe au slot 10
        d'`IDamagePredictionQuery`), spread +/-20 % (#449), profil = celui de l'ABILITY (`Bolter`).
        Pipeline modifiers / armure / bouclier / caps COMPLET vs la cible, depuis la TUILE D'ATTAQUE
        `attack_tile` (`case.CasterPosition`, en-tete lecture 2).

        `is_normal_attack=True` : la gate `IsRegularAttack` du corps garantit que l'`ability` que le
        natif transmet a la requete -- `case.AbilityType` -- EST une attaque normale (en-tete,
        lecture 6).

        `is_melee` SE RE-EVALUE DEPUIS LA TUILE D'ATTAQUE, et ce n'est PAS la gate du corps :
        `IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger` interroge
        `IBattleQuery.<slot 2>(entities.Ability, caster, casterPosition, entities.Target)` avec le
        `casterPosition` de la requete. Il commande `is_ranged` du builder de modifiers, la direction
        du percage (`ExtraPierceMelee(21)` vs `ExtraPierceRanged(22)`) et les faces
        positionnelle/alliee."""
        actx = scene.ctx(att_id)
        if actx is None or amount is None or int(amount) <= 0:
            return None
        prof = GC.damage_profile(profile_name) or {}
        dir_pierce = actx.extra_pierce_melee if is_melee else actx.extra_pierce_ranged
        pierce = max(0, min(100, int(prof.get("PiercingRatio") or 0)
                            + actx.extra_pierce + dir_pierce))
        _hm = prediction_has_moved(scene, att_id, attack_tile)
        _tctx = scene.ctx(tgt_id)
        _tar = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                if _tctx is not None and _tctx.stats is not None else None)
        # #316/#267-r1 : substrat d'ENTITE pour les effets target-conditionnels de l'ATTAQUANT.
        _tgt_traits = _entity_traits(scene, tgt_id)
        mods = calculate_attacker_modifiers_for_prediction(
            scene.effects(att_id), is_ranged=not is_melee, has_moved=_hm, is_normal_attack=True,
            target_traits=_tgt_traits, target_armor_reduced=_tar,
            att_ctx={"att_pos": attack_tile,
                     "tile_effects_by_pos": scene.tile_effects_by_pos,
                     "is_charging": _prediction_is_charging(scene, att_id, attack_tile, tgt_id),
                     "has_teleported": prediction_has_teleported(scene, att_id, attack_tile),
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
        _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, is_melee, attack_tile,
                                          scene.pos(tgt_id), damage_profile=profile_name,
                                          is_normal_attack=True)
        _apply_ally_attack_dmg_bonus(mods, scene, att_id, attack_tile, is_melee, _tar,
                                     tgt_id=tgt_id, is_normal_attack=True,
                                     damage_profile=profile_name)
        hit_mult = target_hit_multiplier(TraitFactory.create_many(_tgt_traits))
        return get_attack_prediction(
            target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount),
            hits=1,                                   # slot 0x24 : hits FORCES 1 (litteral natif)
            profile_type=_PROFILE_INDEX.get(profile_name, 0), pierce_pct=pierce,
            # spread_pct : le DEFAUT (+/-20 %), #449 -- `request+0x6a = 1` route vers
            # `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64`.
            armor=scene.armor(tgt_id), mods=mods, hit_mult=hit_mult,
            target_shield=scene.shield(tgt_id),
            target_limits=_target_damage_limits(scene, tgt_id, profile_name),
            target_prevents_overkill=scene.prevents_overkill(tgt_id),
            defender_block_amount=defender_prediction_block_amount(scene, tgt_id, profile_name),
            attacker_effects=scene.effects(att_id),
            attacker_ctx=actx)

    # ---- mirror `<CalculateAttackUtilityInStepsInternal>d__2$$MoveNext` -------------------------
    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror du corps natif (cf. en-tete), dans l'ORDRE des deux etats : gate `IsRegularAttack`,
        gate d'adjacence REELLE caster<->cible, puis l'utilite (composite Damage) d'une prediction de
        montant `dmg` au profil `Bolter`, hits FORCES 1. Toute autre issue est l'etat 2 = `Fix64(0)`.

        `prediction` (`case.DamagePrediction`, `UtilityAttackCase@+0x28`) est ACCEPTE et IGNORE : le
        corps natif ne lit pas ce champ, il fabrique sa PROPRE prediction."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None:
            return 0.0
        # etat 0a -- `TriggeredAbilityPlaybook<T>$$IsRegularAttack(case)` sur `case.AbilityType`
        # (`case@+0xf0`) : `Contains` sur l'`OrderedSet` statique de `StaticBattleRules.ActiveAbility`
        # (foyer `attack_type`). Faux -> l'etat 2, `Fix64(0)`.
        if ability_id is None or not is_regular_attack(int(ability_id)):
            return 0.0
        # etat 0b -- le TRIGGER `IsAdjacent(Get(Caster), Get(Target), 3)`, ancre sur les positions
        # REELLES (en-tete, lecture 1). Faux -> l'etat 2 aussi.
        if not self.should_trigger(sc, attacker_uid, case_tgt_id):
            return 0.0
        amount = self._damage(sc, attacker_uid)
        if not amount:
            return 0.0
        profile_name = self._profile_name()
        # `IsMeleeAttack` du pipeline de modifiers : re-evalue depuis la TUILE D'ATTAQUE, contre la
        # cible de CETTE prediction (en-tete, lecture 2). `ab_name_by_id` -> le nom gameconfig de
        # `case.AbilityType`, seul canal de `GetAbilityAttackRangeType`.
        tpos = sc.pos(case_tgt_id)
        ab_name = (getattr(ctx, "ab_name_by_id", None) or {}).get(int(ability_id))
        melee = is_melee_attack(ab_name, attack_tile, tpos, getattr(sc, "elev_by_pos", None),
                                neigh_by_pos=bq.neigh_map(sc))
        pred = self._predict_vs_target(sc, attacker_uid, case_tgt_id, int(amount), attack_tile,
                                       profile_name, melee)
        if pred is None:
            return 0.0
        # `friendly` = `IsFriend(case.Caster, event.Target)` que les trois feuilles dominantes du
        # composite Damage evaluent sur la cible de l'event (`UtilityAttackCase$$ForDamagePrediction`
        # la repose en `case.Target`). L'event porte ici `case.Target` lui-meme, donc le drapeau vaut
        # celui de l'attaque evaluee -- faux dans tout regime ou l'IA vise un ennemi.
        cteam, tteam = sc.team(attacker_uid), sc.team(case_tgt_id)
        friendly = cteam is not None and tteam is not None and cteam == tteam
        ev = ProbableDamageEvent(target=case_tgt_id, prediction=pred, friendly=friendly)
        return calculate_utility_from_damage_event(ev, ctx.wt,
                                                   (ctx.hpmax_by_id or {}).get(case_tgt_id))


__all__ = ["HeavyBoltPistolPlaybook"]
