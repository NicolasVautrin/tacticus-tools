"""`IdunBattle.AI.Playbook.Loki.PsykerPlaybook` — face ATTACK des triggered (splash Psyker, #45-s18).

Consommé par la feuille `TriggeredAbilitiesUtility(2)` du composite Damage(34) (dispatcher face attack
`<EvaluateAttackInSteps>d__2 IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext` : itère les triggered de l'ATTAQUANT, `PlaybookDatabase.
LoadPlaybook`, Σ `ITriggeredAbilityPlaybook.CalculateAttackUtilityInSteps` vslot 3). Pendant ATTACK de
`adjacent_unit_preference.py` (face MOVE, case-36) — même protocole, autre vslot.

Corps `PsykerPlaybook.<CalculateAttackUtilityInStepsInternal>IdunBattle.AI.Playbook.Loki.PsykerPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` (RE intégral,
case-34 §MAJ #45quater) :

  1. GATES : `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$IsRegularAttack(case)` = l'ability du case est dans le set statique des
     attaques régulières (`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAttack`) — mirror
     `ability_id in ctx.normal_ids` ; arme du case (slot 0xae = sélection d'arme vs cible) NON mêlée
     (`WeaponProfile.get_IsMelee` -> 0) et profil Psychic (`profile+0x10 == 0xd`) ; non supprimé
     (`IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$IsPsykerAttackSuppressed` = IsEffectTarget(CASTER, 1191) || IsEffectTarget(CIBLE
     du case, 1533)).
  2. AMOUNT : `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$GetAttackDamage` = `PercentageOf(StatAmount(Self,
     Attack, Current), Direct(GetNumberConstant(0xf)))` évalué vs le CASTER = `round_fix64(
     psykerExtraDmg% x GetStat(Attack))` — MÊME formule que la face runner (`triggers/loki/psyker.py`,
     validée bit-exact ; pct = `GC.trait("Psyker").variables.psykerExtraDmg` = 50).
  3. TARGETS : `IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$PossibleTargets` = `Damageable(Enemies(caster, AdjacentUnits(CIBLE, 1)))`
     -> ennemis VIVANTS hex-adjacents à la cible du case (self/cible exclus) ; vide -> 0.
  4. PAR TARGET U : prédiction du montant vs U via l'interface query slot 0x23 =
     `IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` (amount, Nullable<profil 13>) -> hits FORCÉS 1,
     profil résolu, montant DONNÉ (`IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` le boxe
     en `Nullable<int>` à `DamagePredictionRequest+0x58`, et écrit le LITTÉRAL `1` à `+0x6a` --
     l'octet que `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` teste pour router
     vers `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64` : le montant PASSE donc
     par le spread ±20 %, ce N'EST PAS un canal « prédéfini ». #449, MESURÉ : montant 402 ->
     bornes natives [322, 482]) -> le pipeline standard applique la COUCHE MODIFIERS complète.
     PROUVÉ 31337 s18 (u89 Njal -> u81, splash sur {u77, u79}) : base 402 (50% x attack 803)
     + LordOfTempests_ExtraDamage ADDITIF 1200 (= 400/hex x 3 hexes glacés ring-1 de la TUILE DU CASE
     (2,4)) = 1602 ; u79 custoBladeChampion -20% MartialKatah_DmgReduction -> 1282 (== splash EXÉCUTÉ
     sur u79, hp-diff exact) ; u77 admecMarshall sans réduction -> 1602. Les deux effets sont gatés
     `IsNormalAttack` côté port -> le splash EST traité normal-attack par la couche modifiers
     (`is_normal_attack=True`), mesure à l'appui.
  5. `ProbableDamageEvent(U, prediction)` -> `TriggeredAbilityPlaybook.CalculateUtilityFromDamageEvent`
     (composite Damage standard, hpmax EFFECTIF part-2) ; **u = Σ / Count(targets) (MOYENNE)** —
     `Fix64.op_Division` de sortie du SM. Validé : mean(u77(1602)=21.3896, u79(1282)=14.3181)
     = 17.85385 == L3 natif 17.85381752299145 (`probe_45_psyker`, re-joué le 2026-08-02 :
     17.853817519579994, delta **-3,4e-9**).
     ⚠ #449 — cet accord ne dit RIEN du spread : le composite consomme la MOYENNE des deux
     bornes, donc `spread_pct=0` et le spread ±20 % rendent ici le MÊME nombre, à
     `0.000000000` près (mesuré). Le spread est établi sur les BORNES, pas sur cette valeur.
"""
from __future__ import annotations

from fractions import Fraction

import hexgeo
import gameconfig as GC

from ..entities.effect_type import EffectType
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..entities.formulas import _round_fix64
from ..entities.stats import ARMOR_STAT_TYPES
from ..entities.traits import target_hit_multiplier, TraitFactory
from ..entities.effects import calculate_attacker_modifiers_for_prediction
from ..services.battle_query import select_weapon_pierce
from ..services.damage_prediction import get_attack_prediction
from .probable_damage_event import ProbableDamageEvent, calculate_utility_from_damage_event

# Effets de suppression du splash (`IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$IsPsykerAttackSuppressed`)
# = `IsEffectTarget(Caster@DSLSelectors+0x48, 1191) op_BitwiseOr IsEffectTarget(Target@+0x60, 1533)`.
#
# ⚠ `IsEffectTarget` != « l'unité PORTE l'effet ». L'instance `1191` est posée SUR SON PORTEUR
# (`HuntersBeyondDeathAbility$$CreateBehaviour` = `AddEffect(0x4a7, ref, Owner, Owner, …)`) et c'est le
# PSYKER ENNEMI qui figure dans sa liste `EffectComponent.Targets @+0x48`, maintenue par
# `RefreshEffectsOperation$$UpdateEffectTargets` depuis
# `HuntersBeyondDeathPsykerSuppressionEffect$$CreateTargetSelector`. Le gate lisait
# `decisionView.units[caster].effects` — structurellement TOUJOURS faux (case-418-r1).
_OWNER_SUPPRESS = int(EffectType.HuntersBeyondDeathPsykerSuppression)   # 1191, sur le CASTER
_TARGET_SUPPRESS = int(EffectType.WatchedOver_PsykerSuppression)        # 1533, sur la CIBLE du case


class PsykerPlaybook:
    """`PsykerPlaybook` (`IdunBattle.AI.Playbook.Loki`) — playbook triggered de PsykerExtraAttack(1013).
    Seule la face ATTACK est portée (la face MOVE hérite du 0 de base `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateMovementUtilityInSteps`)."""

    ability_id: int = int(TriggeredAbilityType.PsykerExtraAttack)   # 1013

    # ---- mirror slot 0x23 : prédiction d'un MONTANT prédéfini vs U (pipeline modifiers complet) ----
    def _predict_amount_vs_target(self, scene, att_id: int, tgt_id: int, amount: int, attack_pos):
        """`IdunBattle.Core.Services.BattleQuery$$GetAttackPrediction` (slot 0x23) -> `DamagePredictionQuery.
        IdunBattle.Core.Services.DamagePredictionQuery$$GetAttackPrediction` (amount en Nullable<int>, hits=1, profil Psychic
        résolu via `GetDamageProfile`). Pipeline = LE MÊME chemin amount que `generate_multi_hit_attack_
        prediction` : mods attaquant (builder IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction, additifs positionnels LordOfTempests inclus
        via `att_ctx.att_pos` = tuile du case) + mods défenseur par-cible + hit_mult MkXGravis + caps
        cibles ; spread ±20 % (#449 : `request+0x6a = 1` -> `GetBaseDamageFix64`, MESURÉ sur les
        bornes capturées). `is_normal_attack=True` : mesuré (cf. docstring module)."""
        prof = GC.damage_profile("Psychic") or {}
        actx = scene.ctx(att_id)
        pierce = max(0, min(100, int(prof.get("PiercingRatio") or 0)
                            + actx.extra_pierce + actx.extra_pierce_ranged))
        from .prediction import prediction_has_moved, prediction_has_teleported
        _hm = prediction_has_moved(scene, att_id, attack_pos)
        _tctx = scene.ctx(tgt_id)
        _tar = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                if _tctx is not None and _tctx.stats is not None else None)
        mods = calculate_attacker_modifiers_for_prediction(
            scene.effects(att_id), is_ranged=True, has_moved=_hm, is_normal_attack=True,
            target_armor_reduced=_tar,
            att_ctx={"att_pos": attack_pos,
                     "tile_effects_by_pos": scene.tile_effects_by_pos,
                     "has_teleported": prediction_has_teleported(scene, att_id, attack_pos),
                     # `PsychicStalk_FriendlyChaosExtraDamage` (#366-r1, 1435) : aucun gate
                     # `IsNormalAttack` dans son trigger -> il entre AUSSI sur le vecteur SMITE
                     # (dont le profil EST Psychic, l'un des deux profils affectes). MEMES CLES
                     # que la normale / les abilities / la face COMBAT.
                     "att_grand_alliance": (GC.unit(scene.vis_by_id.get(att_id))
                                            or {}).get("GrandAllianceId"),
                     "damage_profile": "Psychic",
                     "t_pos": scene.pos(tgt_id),
                     "tgt_team": scene.team(tgt_id)})
        from .prediction import (_add_positional_and_defender_mods, _apply_ally_attack_dmg_bonus,
                                 _target_damage_limits, _PROFILE_INDEX, _entity_traits)
        _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, False, attack_pos,
                                          scene.pos(tgt_id), damage_profile="Psychic",
                                          is_normal_attack=True)
        _apply_ally_attack_dmg_bonus(mods, scene, att_id, attack_pos, False, _tar, damage_profile="Psychic")
        # #267-r1 : MkXGravis lu sur l'ENTITE (`GetBaseDamageWithFixedPiercedArmor` ->
        # HasTrait(defender, 0x3f5)), MEME foyer que `_target_damage_limits` deux lignes plus bas.
        hit_mult = target_hit_multiplier(TraitFactory.create_many(_entity_traits(scene, tgt_id)))
        return get_attack_prediction(
            target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount), hits=1,
            profile_type=_PROFILE_INDEX.get("Psychic", 0), pierce_pct=pierce,
            # spread_pct : le DEFAUT (+/-20 %). #449 -- MESURE DIRECTE sur les bornes capturees
            # (`ProbableDamageEvent$$.ctor`) : montant 402 -> natif [322, 482] == {0.8, 1.2} x 402.
            # Le `spread_pct=0` d'avant rendait [402, 402].
            armor=scene.armor(tgt_id), mods=mods, hit_mult=hit_mult,
            target_shield=scene.shield(tgt_id), target_limits=_target_damage_limits(scene, tgt_id),
            target_prevents_overkill=scene.prevents_overkill(tgt_id),   # #195 : HasFlag(cible, 0x13)
            attacker_effects=scene.effects(att_id),   # #202 : max-out evalue DANS predict_attack_raw
            attacker_ctx=actx)                        # #R34 : MightCrit = CouldCrit(attaquant)

    def possible_targets(self, scene, att_id: int, case_tgt_id: int) -> list[int]:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$PossibleTargets` = `Damageable(Enemies(caster, AdjacentUnits(CIBLE, 1)))` —
        ennemis du caster VIVANTS hex-adjacents à la cible du case (mirror du pool runner
        `_adjacent_damageable_enemies`, ici sur Scene). Adjacence GÉOMÉTRIQUE hex (evenq)."""
        my_team = scene.team(att_id)
        tpos = scene.pos(case_tgt_id)
        if tpos is None:
            return []
        out = []
        for u in (scene.units or []):
            u_id = u.get("id")
            if u_id in (att_id, case_tgt_id) or not u.get("alive"):
                continue
            if u.get("team") == my_team:
                continue
            p = scene.pos(u_id)
            if p is not None and hexgeo.distance(tpos, p) == 1:
                out.append(u_id)
        return out

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror `<CalculateAttackUtilityInStepsInternal>IdunBattle.AI.Playbook.Loki.PsykerPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext` (cf. docstring
        module : gates -> amount -> targets -> prédiction/utilité par target -> MOYENNE)."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None:
            return 0.0
        # 1. IsRegularAttack(case) : l'ability évaluée est l'attaque NORMALE de l'unité.
        if int(ability_id) not in (ctx.normal_ids or ()):
            return 0.0
        actx = sc.ctx(attacker_uid)
        tpos = sc.pos(case_tgt_id)
        if actx is None or tpos is None:
            return 0.0
        # 2. arme du case : mêlée -> 0 ; profil != Psychic -> 0.
        d = hexgeo.distance(attack_tile, tpos)
        _p, is_ranged, _h, prof_name = select_weapon_pierce(actx, d <= 1, d)
        if not is_ranged or prof_name != "Psychic":
            return 0.0
        # 3. IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$IsPsykerAttackSuppressed (caster 1191 || cible du case 1533).
        #    `1533` : géométrie NON LUE (le `CreateTargetSelector` de l'effet n'a aucun symbole) →
        #    le foyer rend `None`, on ne ferme PAS sur un inconnu (résidu nommé, case-418-r1).
        if (sc.is_effect_target(attacker_uid, _OWNER_SUPPRESS)
                or sc.is_effect_target(case_tgt_id, _TARGET_SUPPRESS) is True):
            return 0.0
        # 4. amount = IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$GetAttackDamage (PercentageOf Fix64, mirror runner psyker_smite_tree).
        #    StatAmount(Attack, Current) = le stat DU PAS (`scene.attack_current`, refresh par-pas) —
        #    PAS le cold ctx.attack : l'aura RitesOfBattle (+1298 par adjacence Calgar) va et vient
        #    (vécu 31337 : cold 2101 vs 803 au s18 -> feuille 24.37 au lieu de 17.85).
        pct = int((GC.trait("Psyker") or {}).get("variables", {}).get("psykerExtraDmg") or 0)
        amount = int(_round_fix64(Fraction(pct * int(sc.attack_current(attacker_uid)), 100), 0))
        if amount <= 0:
            return 0.0
        # 5. targets adjacents damageables ; vide -> 0.
        targets = self.possible_targets(sc, attacker_uid, case_tgt_id)
        if not targets:
            return 0.0
        # 6. Σ CalculateUtilityFromDamageEvent / Count (MOYENNE, Fix64.op_Division de sortie).
        total = 0.0
        for u_id in targets:
            pred = self._predict_amount_vs_target(sc, attacker_uid, u_id, amount, attack_tile)
            ev = ProbableDamageEvent(target=u_id, prediction=pred)
            total += calculate_utility_from_damage_event(ev, ctx.wt,
                                                         (ctx.hpmax_by_id or {}).get(u_id))
        return total / len(targets)


# `IdunBattle.AI.PlaybookDatabase$$LoadPlaybook` (singleton par type) — face ATTACK. Seuls les types dont
# le playbook a un corps attack NON-trivial sont enregistrés (base `TriggeredAbilityPlaybook.
# CalculateAttackUtilityInSteps` yield 0) : absence == 0, même dégradation que le natif. ~60 playbooks
# triggered ont un corps attack non-trivial (case-34 §MAJ #45quater) — port à la demande (agreement).
from .aggressive_onslaught import AggressiveOnslaughtPlaybook   # #58 (registre, cf. module dedie)
from .suppressive_fire import SuppressiveFirePlaybook           # #415 (registre, cf. module dedie)
from .lakrimae import LakrimaePlaybook                          # #419 (registre, cf. module dedie)
from .barbed_ovipositor import BarbedOvipositorPlaybook         # #438 (registre, cf. module dedie)
from .neuroparasite import NeuroparasitePlaybook                # #441 (registre, cf. module dedie)
from .savior_protocols import SaviorProtocolsPlaybook           # #443 (registre, cf. module dedie)
from .avalanche_of_muscle import AvalancheOfMusclePlaybook      # #445 (registre, cf. module dedie)
from .boltstorm import BoltstormPlaybook                        # #446 (registre, cf. module dedie)
from .fire_of_absolution import FireOfAbsolutionPlaybook        # #419-r1 (registre, cf. module dedie)
from .cosmic_horror import CosmicHorrorPlaybook                 # #419-t6 (registre, cf. module dedie)

TRIGGERED_ATTACK_PLAYBOOKS: dict[int, object] = {
    int(TriggeredAbilityType.PsykerExtraAttack): PsykerPlaybook(),
    # #58 : AggressiveOnslaught (1248) — summon d'attaque, valeur = min(free_adj(target), nrOfSummons-1)
    # x weight (AggressiveOnslaught_PerFreeTileAfterCharge=40). Corps IdunBattle.AI.Playbook.Loki.AggressiveOnslaughtPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext.
    int(TriggeredAbilityType.AggressiveOnslaught): AggressiveOnslaughtPlaybook(),
    # #415 : SuppressiveFire (1044, accorde par le TRAIT 1010) — +35 quand la CIBLE porte un
    # overwatch (1009) et que la tuile d'attaque n'est PAS adjacente (le bonus du TIR). Corps
    # IdunBattle.AI.Playbook.Loki.SuppressiveFirePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext.
    # Trou MESURE a l'oracle natif `pairUtility` : 274.6678 contre 239.6678 rendus par le port.
    int(TriggeredAbilityType.SuppressiveFire): SuppressiveFirePlaybook(),
    # #419 : Lakrimae (1541, accorde par la RELIQUE `R_Crit_Lakrimae`) -- `Lakrimae_
    # LikesNonMechanicalEnemies` = 5 quand la CIBLE n'a PAS le trait `Mechanical`, 0 sinon. Corps
    # IdunBattle.AI.Playbook.Loki.LakrimaePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext.
    # C'est le PREMIER playbook attack dont le porteur arrive par une voie que le kit gameconfig
    # ignore : sans le cablage du canal live de `evaluate_attack_in_steps` (meme commit), il serait
    # INERTE -- exactement le patron « porte + non cable » que #419 recense.
    int(TriggeredAbilityType.Lakrimae): LakrimaePlaybook(),
    # #438 : BarbedOvipositor (1204, passif de `tyranParasite` + 6 npc `tyranBossParasite*`) --
    # 0 si la prediction du case est absente, si le kill n'est meme pas POSSIBLE, ou si la cible
    # est `Mechanical` ; sinon `BARBEDOVIPOSITOR_DefinitelyKill` (50) quand le kill est GARANTI,
    # `BARBEDOVIPOSITOR_PossibleKill` (25) sinon. Corps IdunBattle.AI.Playbook.Loki.
    # BarbedOvipositorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__4$$MoveNext.
    # PREMIER playbook attack porte qui lit `case.DamagePrediction` (`UtilityAttackCase@+0x28`) --
    # d'ou le parametre `prediction` de la face ATTACK, sans lequel il serait INERTE.
    int(TriggeredAbilityType.BarbedOvipositor): BarbedOvipositorPlaybook(),
    # #441 : Neuroparasite (1183, passif de `tyranNeurothrope` + 6 npc) -- le LITTERAL `1` quand la
    # CIBLE porte deja l'effet `Neuroparasite` (EffectType 1218, a ne pas confondre avec l'ability
    # 1183 du meme nom), 0 sinon. Corps IdunBattle.AI.Playbook.Loki.
    # NeuroparasitePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext.
    # SEUL playbook attack porte dont la sortie n'est PAS une cle de `Utilities.Default.
    # TriggeredAbilities` : la SM ne capture meme pas le delegue scorer, il n'y a donc ni
    # `GetUtilityValue` ni `.cctor` a lire. Il n'a pas non plus besoin du canal `prediction` de
    # #438 -- son corps ne lit que `case@+0x20`.
    int(TriggeredAbilityType.Neuroparasite): NeuroparasitePlaybook(),
    # #443 : SaviorProtocols (1120, porteurs 3 npc + 3 SUMMONS `tauSmn*Drone*`) --
    # `SAVIORPROTOCOLS_MarkedTarget` (60) quand la CIBLE porte un `Markerlight` (1122) ACTIF, 0
    # sinon. Corps IdunBattle.AI.Playbook.Loki.
    # SaviorProtocolsPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__5$$MoveNext.
    # `onlyActive: true` au call-site de `EntityExtensions$$HasEffect` -- l'INVERSE de
    # SuppressiveFire (qui passe 0) : substrat `active_effects`, pas `has_effect`.
    int(TriggeredAbilityType.SaviorProtocols): SaviorProtocolsPlaybook(),
    # #445 : AvalancheOfMuscle (1028, passif d'`astraBullgryn` + 4 npc `astra*Bullgryn*`) -- le
    # gain de la CHARGE : 0 si le caster ne bouge pas, s'il n'arrive pas au contact, s'il y etait
    # DEJA, ou s'il n'a aucune arme ; sinon l'utilite (composite Damage) d'une prediction de
    # montant PREDEFINI `extraDmg[niveau passif] x mult`, hits FORCES 1, au profil de l'arme
    # normale. Corps IdunBattle.AI.Playbook.Loki.AvalancheOfMusclePlaybook.
    # u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext (SEPT etats de yield).
    # PREMIER playbook attack porte qui FABRIQUE sa prediction au lieu de lire celle du case.
    int(TriggeredAbilityType.AvalancheOfMuscle): AvalancheOfMusclePlaybook(),
    # #446 : Boltstorm (1090, passif de `templAggressor` + 4 npc `templBossAggressor*`) --
    # `BOLTSTORM_AdjacentEnemies` (10) MULTIPLIE par le cardinal de
    # `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BoltstormAbility$$GetAllTargets`, 0 quand le
    # caster n'a pas d'arme a distance (`BattleQuery.FindRangedWeapon(caster) == null`). Corps
    # IdunBattle.AI.Playbook.Loki.BoltstormPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext.
    # PREMIER playbook attack porte dont la sortie est un PRODUIT poids x CARDINAL (les autres sont
    # des termes plats) -- et dont le cardinal COMPTE LA CIBLE elle-meme (`op_Addition` avec
    # `Target@0x60`), donc toute cible vaut deja 10. Il n'a besoin ni du canal `prediction` (#438) ni
    # de la tuile d'attaque : la struct `AbilityEntities` du corps natif ne porte pas `CasterTile`.
    int(TriggeredAbilityType.Boltstorm): BoltstormPlaybook(),
    # #419-r1 : FireOfAbsolution (1017, passif des quatre `adept*Retributor`) --
    # `FIREOFABSOLUTION_AdjacentFriend` (-20) x |amis du caster adjacents a la CIBLE|
    # + `FIREOFABSOLUTION_AdjacentEnemy` (20) x |ennemis adjacents a la CIBLE|. Corps
    # IdunBattle.AI.Playbook.Loki.FireOfAbsolutionPlaybook.
    # u003CCalculateAttackUtilityInStepsInternalu003Ed__4$$MoveNext.
    # PREMIER playbook attack porte qui SOMME DEUX produits poids x cardinal, et le premier dont un
    # poids est NEGATIF (il peut donc rendre une utilite < 0). Il compte le CASTER parmi les amis
    # -- aucun retrait au natif, la ou la face COMBAT de la MEME ability exclut nommement le caster
    # de son splash. `1017` est un homonyme a trois faces : `ActiveAbilityType` 1017 = FragBomb
    # (celui de #249/`TargetTileHasEnemyUnit`), `EffectType` 1017 = ActOfFaith_Effect.
    int(TriggeredAbilityType.FireOfAbsolution): FireOfAbsolutionPlaybook(),
    # #419-t6 : CosmicHorror (1277, passif de `genesPatriarch` HERO + 3 npc `genes*Patriarch*`) --
    # `COSMICHORROR_StepOnDecoyToAttack` (10) quand la TUILE D'ATTAQUE (`case.CasterPosition.
    # MainTile`, `UtilityAttackCase@+0x18`) est OCCUPEE par un leurre AMI (`HasTrait(u, 0x41d)` =
    # `UnitTrait.Decoy` + `IsFriend(u, case.Caster)`), 0 sinon. Corps IdunBattle.AI.Playbook.Loki.
    # CosmicHorrorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext.
    # PREMIER playbook attack porte dont la sortie ne depend d'AUCUNE propriete de la cible : c'est
    # un terme de TUILE, constant a cible variable, qui ne bouge qu'en DEPLACANT le caster. Il
    # n'exige aucune piece neuve (`attack_tile` est deja le 5e parametre du dispatcher) -- ni le
    # canal `prediction` (#438), qu'il accepte et ignore comme son corps natif.
    int(TriggeredAbilityType.CosmicHorror): CosmicHorrorPlaybook(),
}


def load_attack_playbook(ability_id: int) -> PsykerPlaybook | None:
    """Mirror `PlaybookDatabase.LoadPlaybook` (attack-relevant uniquement). None -> le dispatcher skip
    (même chemin que le `if playbook == null: continue` natif)."""
    return TRIGGERED_ATTACK_PLAYBOOKS.get(int(ability_id))
