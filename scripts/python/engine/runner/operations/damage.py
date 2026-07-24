"""Operations de dégât — `IdunBattle.Operations.AttackDamageOperation` (gqfc5mff6c).

Tranche DAMAGE. **Palier 1 (porté + validé ici) : le TIRAGE de dégât par coup**
(`HitDamage.GetDamage`), bit-exact via le MT porté (`engine/runner/prng.py`).

Chaîne native RE'd (VA citées) :

    AttackDamageOperation.Execute        @180e60c70
      → GetAttackHits                    @180e613d0   (nb de coups ; 1 par défaut)
      → ExecuteHits (boucle nbHits)      @180e607b0
          → ExecuteHit (PAR COUP)        @180e5eff0   — per-coup PARTAGÉ : attaque NORMALE **et**
            attaques d'ABILITY `AttackWithAttackDamage` (AttackDamageBehaviour.ExecuteTarget
            @180fba140 → stream slot 0x3c → même opération). Corrigé cas fable rngcrit-1202 :
              1. HitDamage.GetDamage     @181007bf0   sur le STRUCT d'entrée — tirage SSI min!=max :
                 NORMALE = struct DÉGÉNÉRÉ → 0 tirage ; ABILITY bounds = [minDmg,maxDmg] config
                 → 1 tirage = LA VALEUR BRUTE (roll-then-reduce).
              2. RollCritical (IDamagePrediction slot 0xa → DamagePrediction.RollCritical
                 @1810387a0 : gate `cc<1 → false SANS tirage` → DamageCalculations.RollCritical
                 @1810057b0 = NextBool brut, atteint seulement à travers le gate)  ← SI cc≥1
              3. slot 4 CalculateDamageOperation @18102dc30 : shield-part/armure/caps → cellules
                 min/max (0 RNG) — NORMALE : bornes RÉDUITES ; ABILITY : cellules DÉGÉNÉRÉES.
              4. slot 8 RandomlyResolveMinMaxDamage @181038600 : Next(min,max+1) — TOUJOURS
                 1 tirage (AUCUN gate min==max) : NORMALE = LA VALEUR (plage réduite) ;
                 ABILITY = tirage GASPILLÉ (largeur 1).
              5. sub-op 0x42 : block rolls + split bouclier/armure-pool (calculate_damage_operation)
              6. EvaluateAfterHitTriggers @180e25fc0 (cascade)

**Ordre RNG CONFIRMÉ (genrand brut live, necroDestroyer CC=100 ; re-mesuré probe_rngcrit_1202
2026-07-23, custoKyrus 3-hit cc=0, 5 seeds x 2 cibles)** : attaque NORMALE par coup =
RollCritical si cc≥1 (tirage PAIR) PUIS valeur (resolve slot 8, tirage IMPAIR). À cc=0,
RollCritical ne tire RIEN (gate `cc<1` de @1810387a0) → 1 tirage/coup (validé 18/18 + probe A).
Attaque d'ABILITY bounds-mode par coup à cc=0 : **2 tirages** = valeur BRUTE (GetDamage-top)
puis resolve GASPILLÉ — cf. `_one_hit`. La désync #220/#205 (« 6 rng pour 3 coups ») était ce
resolve dégénéré, PAS un crit-roll : aucun chemin natif ne consomme un tirage crit à cc=0.

**CRIT (combat ≠ prédiction)** : le crit du COMBAT s'ajoute à la BASE D'ATTAQUE AVANT
spread/perçage (`GetBaseDamageFix64` param_4=isCrit ⇒ `eff_attack=attack+critDamage`,
même pipeline) — PAS l'`ApplyCritDamage` post-réduction (base+bonus) de la PRÉDICTION.
Confirmé bit-exact : crit per-coup [675,1012] = non-crit [435,652]×(906+500)/906, et
next_internal(675,1013) aux tirages impairs = live [932,882,967,867,961,955] à l'unité.

**#73 (RE close, 2026-07-09) : le crit N'A PAS de gating inter-coups** (contrairement au block #72).
`RollCritical @1810387a0`→`@1810057b0` = NextBool(GetStat(9)+bonus) SANS ETAT ; pas d'"AddFailedCrit"
dans `ExecuteHit @180e5eff0` (le block, lui, a `AddFailedBlockIds`). Chaque coup tire le crit INDÉPENDAMMENT
avec la même chance ⇒ `_run_hits` (crit par-coup, aucun accumulateur) est déjà fidèle. Le block gate PARCE
QUE multi-source (id par source) ; le crit est chance unique ⇒ rien à exclure. (Détail : docs/rl/case-68.)

    #74 (RE close, 2026-07-09) : la crit-chance est RELUE PAR COUP par le natif, MAIS constante sur les coups
    d'une attaque -> le calcul UNE FOIS du port (`_crit_params`) est fidele. `ExecuteHit @180e5eff0` dispatche
    `RollCritical` (slot 0xa IDamagePrediction) A CHAQUE coup (chance re-lue GetStat(9)+bonus) + EvaluateAfterHit
    Triggers en fin de CHAQUE coup -> un buff crit-chance on-hit escaladerait entre coups. MAIS recherche gameconfig
    (559 abilities) : AUCUNE cle per-hit/consecutive/timesAttacked ; les 19 abilities crit-chance sont des buffs
    extraCritChance per-attaque/aura/per-tour/on-kill (TrophyTaker=kill-snowball, ThrillSeekers=re-trigger PAR TOUR,
    cf. hypotheses.md H22), JAMAIS per-coup-intra-attaque. => crit-chance constante sur les coups d'UNE attaque =>
    `_crit_params` (avant `_run_hits`) == valeur re-lue par coup. Rien a porter. RESIDU (non observe) : un futur effet
    crit-chance on-hit-intra-attaque exigerait l'application des triggers PAR COUP (le port les applique post-attaque)
    -- axe separe, pas un gap crit actuel.

**ORDRE réduction↔tirage (CORRIGÉ — confirmé live 18/18 coups, 3 seeds, necroDestroyer 6h**
**mêlée → eldarFarseer)** : la réduction perçage/armure/modifiers est appliquée aux BORNES
du `HitDamage` D'ABORD (le struct porte la plage RÉDUITE `[reduce(base−delta), reduce(base+delta)]`),
PUIS `GetDamage` tire DANS cette plage réduite : `next_internal(min_réduit, max_réduit+1)`.
⚠ PAS « spread brut puis réduit » : les deux donnent la MÊME plage totale, mais des valeurs
par coup DIFFÉRENTES (l'offset RNG ne dépend que de la LARGEUR de plage, qui diffère entre
brut et réduit). `delta = Round(base × DamageSpreadPercentage/100)` (cf.
`engine/services/damage_calculations.py`).
"""
from __future__ import annotations

from ...services.damage_calculations import spread_to_min_max
from ...services.damage_prediction import get_base_damage_fix64, apply_pierce_and_modifiers
from ...services.damage_combat import (calculate_damage_operation, Damage, could_crit,
                                       roll_critical, BlockSource)
from ...services.trait_damage_limits import (apply_trait_damage_limits_to_damage,
                                             compute_prediction_overkill)
from ...entities.damage_trait import DamageTrait
from ...entities.damage_profile_type import DamageProfileType
from ...services.damage_modifiers import apply_all_modifiers, capped_reduction_flat
from ...services.battle_query import are_tiles_adjacent
from ...services.attack_hits_formula import attack_hits_with_modifiers
from ...entities.stats import StatType
from ..prng import IntBasedMersenneTwister
from ..state import State
from ..components import (StatsComponent, HealthComponent, PositionComponent, UnitComponent,
                         ShieldComponent, OwnerComponent)
from ..damage_model import (select_weapon, select_weapon_pierce, attacker_modifiers,
                            defender_modifiers, build_hits_board, apply_elevation_bonus,
                            apply_trench_reduction, ice_crit_damage_addition,
                            target_trait_names, getstuckin_combat_chance,
                            defender_fixed_armor)
from ...entities.effects import (hits_bonus_from_effects, crit_chance_bonus_from_effects,
                                 crit_damage_bonus_from_effects, defender_effect_block_sources,
                                 additional_hit_groups, aura_additional_hits_from_allies)
from ...entities.effects.loki import LIGHT_COVER_TILE_ID
from ...entities.traits import target_hit_multiplier
from .additional_hits import collect_additional_hit_groups, execute_additional_hits


class HitDamage:
    """`IdunBattle.Core.HitDamage` — struct {Min, Max} du dégât d'UN coup (avant réduction).

    Layout natif : Min @+0 (uint), Max @+4 (uint)."""
    __slots__ = ("min", "max")

    def __init__(self, min_: int, max_: int):
        self.min = min_
        self.max = max_

    @classmethod
    def from_base(cls, base: int, spread_pct: int = 20) -> "HitDamage":
        """Construit le {Min,Max} d'un coup depuis le dégât de base (spread BC).

        Le moteur bâtit ce MinMaxDamage en amont (SetupHitGroup) ; ici on le
        reconstruit fidèlement via `spread_to_min_max` (= CalculateDamageSpread)."""
        mm = spread_to_min_max(base, spread_pct)
        return cls(mm.min, mm.max)

    def get_damage(self, rng: IntBasedMersenneTwister, use_midpoint: bool = False) -> int:
        """`HitDamage.GetDamage` @181007bf0.

          • Min == Max            → Min            (AUCUN tirage RNG)
          • use_midpoint (prédiction) → (Min+Max)/2 (troncature entière, aucun tirage)
          • sinon                 → rng.Next(Min, Max+1) = next_internal(Min, Max+1)
                                    (uniforme [Min,Max], 1 tirage)
        """
        if self.min == self.max:
            return self.min
        if use_midpoint:
            return (self.min + self.max) // 2      # (int)((Max+Min)/2)
        return rng.next_internal(self.min, self.max + 1)


class AttackDamageOperation:
    """`IdunBattle.Operations.AttackDamageOperation` @180e60c70 (squelette fidèle).

    Palier 1 : seul le TIRAGE par coup (`execute_hit`) est porté+validé. Les paliers
    suivants (crit, block, réduction, triggers after-hit) sont marqués TODO avec leur
    VA, en miroir 1:1 de la structure native (cf. en-tête de module)."""
    __slots__ = ()

    @staticmethod
    def get_attack_hits(default_hits: int = 1) -> int:
        """`GetAttackHits` @180e613d0 — nb de coups. Mono-coup → 1 (sans requête, donc
        sans RNG avant le 1er coup). Le cas multi-coups (requête composant 0xb5) =
        palier ultérieur."""
        return default_hits

    @staticmethod
    def execute_hit(hit: HitDamage, rng: IntBasedMersenneTwister,
                    use_midpoint: bool = False) -> int:
        """`ExecuteHit` @180e5eff0 — PALIER 1 : renvoie le dégât de BASE tiré du coup
        (`HitDamage.GetDamage`). Crit (composant 0xb), block (composant 10), réduction
        perçage/armure et EvaluateAfterHitTriggers = paliers 2-4 (non portés ici)."""
        return hit.get_damage(rng, use_midpoint)

    @staticmethod
    def _fire_death_if_killed(state: State, target_id: int, attacker_id: int,
                             hp_before, hp_after, tgt, damage=None) -> Optional[list]:
        """Si le coup a fait passer la cible de >0 à 0 PV → elle meurt : marque `alive=False` et lance le
        vecteur MORT (`after_death_triggers`, `On(1)` {dying=cible, killer=attaquant}) qui déclenche les
        accumulations ActOfFaith des alliés Imperial + l'attaque de mort FinalJustice (worldKharn). No-op si
        pas de mort. Mirror de l'`OnDeathEvent` natif émis lors de l'application des dégâts. `damage` = dégât
        LÉTAL total du coup (pour le flag OVERKILL = `dmg >= 2*PV`, gate de FinalJustice)."""
        if hp_before is None or hp_before <= 0 or hp_after != 0:
            return None
        uc = tgt.get_component(UnitComponent) if tgt is not None else None
        if uc is not None:
            uc.alive = False
        from .triggers import after_death_triggers, is_overkill, unit_defeated_triggers
        out = after_death_triggers(state, target_id, attacker_id,
                                   overkill=is_overkill(hp_before, damage))
        # #G3 : le natif emet AUSSI `On(UnitDefeated=55)` (event DISTINCT de PreUnitDeath=1) apres la mort ->
        # Ambush_SummonAbility (mort -> decoy + record turn_defeated). L'unite est deja alive=False (fire-on-death).
        return (out or []) + unit_defeated_triggers(state, target_id, attacker_id)

    @staticmethod
    def _refresh_swarm(state: State, target_id: int) -> None:
        """#60 : bras `On(UnitMemberDeath=48) & OwnerIsTarget` du `SwarmAbility.CreateTrigger
        @181225f50` — apres toute baisse de PV de la cible, re-evalue le stat-mod EXTRA_HITS du trait
        Swarm (`AddOrUpdateStaticStatModifierEffect 0x3fd`, cf. runner/abilities/loki/swarm.py). No-op
        rapide pour une cible non-swarm ou morte. Lazy import (cycle damage <-> abilities)."""
        from ..abilities.loki.swarm import on_group_unit_hp_changed
        on_group_unit_hp_changed(state, target_id)

    @staticmethod
    def _apply_damage_pipeline(state: State, target_id: int, attacker_id: int, tgt, thc,
                               total: int, profile: Optional[str],
                               shield_dmg: int = 0, armor_dmg: int = 0,
                               is_attack: bool = True) -> Optional[list]:
        """#202 : CHOKEPOINT post-resolution PARTAGE des 4 vecteurs de degat — mirror du pipeline natif
        unique qui suit toute application de degat : `ApplyDamageOperation` (mutation HP, clamp HP-floor)
        -> OnDeathEvent (`_fire_death_if_killed`) -> compteurs per-tour (`_record_attacked`, attaques
        seulement) -> `RegisterDamageOperation @180e86de0` (`_register_received_damage`) -> re-eval Swarm
        (`_refresh_swarm`, On(UnitMemberDeath=48)). Avant ce foyer, chaque vecteur inlinait le meme bloc
        x4 (divergence structurelle vs le chokepoint natif). `is_attack=False` = degat DIRECT (DoT) :
        pas de `_record_attacked` (un DoT n'est PAS une attaque, compteur HasBeenAttackedAmountThisTurn).
        Renvoie la liste d'events de mort (ou None si pas de mort / pas de HP)."""
        if thc is None or thc.hp is None:
            return None
        hp_before = thc.hp
        thc.reduce(total)                   # #G6a : clamp au HP-floor Hypersensory, pas de PV<0
        death = AttackDamageOperation._fire_death_if_killed(
            state, target_id, attacker_id, hp_before, thc.hp, tgt, damage=total)
        if is_attack:
            AttackDamageOperation._record_attacked(state, target_id)    # #G6a : compteur + revert du floor
        AttackDamageOperation._register_received_damage(
            state, target_id, profile, total, shield_dmg, armor_dmg)
        AttackDamageOperation._refresh_swarm(state, target_id)          # #60 : On(UnitMemberDeath=48)
        return death

    @staticmethod
    def _register_received_damage(state: State, target_id: int, profile: Optional[str],
                                  health: int, shield: int = 0, armor: int = 0) -> None:
        """#202 : mirror `RegisterDamageOperation.Execute @180e86de0` -> `ActorStatisticsComponent.
        RegisterReceivedDamage @180f922c0` : incremente `received_damage_this_turn[profil]` de la CIBLE
        (TryAdd(profil,1) sinon +1). Consomme par le selecteur `UnitsThatTakenDamageThisTurn @180f2e230`
        (WeaverOfFate : ContainsKey(Psychic) — seule la PRESENCE de la cle compte). Enregistre quand du
        degat a ete inflige (sante OU bouclier OU armure-pool > 0) — le gate exact du natif (enqueue de
        l'op par le pipeline, dispatch virtuel invisible aux xrefs) est un RESIDU documente (case-202 §6),
        sans effet tant que seul WeaverOfFate lit le dict (cle Psychic posee par de VRAIS degats)."""
        if not profile or (health <= 0 and shield <= 0 and armor <= 0):
            return
        ent = state.get_entity(target_id)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None:
            return
        try:
            pid = int(DamageProfileType[profile])
        except KeyError:
            return                                  # profil inconnu -> pas de cle (fidele : enum natif)
        d = uc.received_damage_this_turn
        d[pid] = d.get(pid, 0) + 1

    @staticmethod
    def _apply_max_out(state: State, attacker_id: int, hit_nc: "HitDamage",
                       hit_cr: "HitDamage") -> tuple:
        """#202 WeaverOfFate : mirror de la branche max-out des DEUX foyers de degat natifs
        (`AttackDamageBehaviour.GetDamage @180fbb250` / `AbilityDamageBehaviour.GetDamage @180f8c560`) :
        si `IsAttackMaxOutDamage(attaquant) == true`, le HitDamage est construit `(max, null)` — le noeud
        est invoque sur son slot GetMaxDamage, AUCUN tirage. Port = degenerer les bornes a (max, max) :
        - voie `get_damage` (limits None / ability roll-then-reduce) : min==max -> AUCUN tirage consomme,
          comme le natif (`HitDamage.GetDamage @181007bf0` gate min==max) ;
        - voie slot-8 mode-1 (#67, limits actifs) : le tirage TOUJOURS consomme tire dans [max, max] —
          consommation RNG bit-exacte preservee (RandomlyResolveMinMaxDamage @181038600 sans gate).
        La branche crit d'`ExecuteHit @180e5eff0` prend aussi le max comme base (uVar26 = struct.max) —
        couvert par la degenerescence de `hit_cr`. No-op (retourne les bornes inchangees) si l'attaquant
        n'a pas l'effet 1185 (cas courant)."""
        from .triggers.loki.weaver_of_fate import is_attack_max_out_damage   # lazy : cycle damage<->triggers
        if not is_attack_max_out_damage(state, attacker_id):
            return hit_nc, hit_cr
        return HitDamage(hit_nc.max, hit_nc.max), HitDamage(hit_cr.max, hit_cr.max)

    @staticmethod
    def _record_attacked(state: State, target_id: int) -> None:
        """#G6a : la cible vient d'encaisser une ATTAQUE (via `execute`/`execute_ability_attack`/
        `execute_normal_like` ; PAS un DoT `execute_direct`) -> incremente son compteur d'attaques du tour +
        re-eval l'ActiveCondition du HP-floor Hypersensory (attacked>=1 -> RevertInternal efface le plancher ->
        le coup SUIVANT peut tuer). Lazy import (cycle damage<->minimal_health)."""
        from .minimal_health import record_attacked
        record_attacked(state, target_id)

    @staticmethod
    def _target_shield(tgt) -> tuple:
        """(ShieldComponent|None, total) du bouclier COURANT de la cible — `GetShield`@180ed2030 /
        `GetTotalShield`@180fa7f30. 0 si pas de composant (rétro-compat : cibles sans bouclier)."""
        shc = tgt.get_component(ShieldComponent) if tgt is not None else None
        return shc, (shc.get_total_shield() if shc is not None else 0)

    @staticmethod
    def _deplete_shield(shc, run_result: dict) -> None:
        """Déplète le bouclier de l'absorbé (`run_result['shield_dmg']`) après l'attaque (mirror de la
        déplétion `ApplyDamageOperation` ; le coup réduit l'instance, l'expiration à 0 par `deplete`)."""
        if shc is not None and int(run_result.get("shield_dmg") or 0) > 0:
            shc.deplete(int(run_result["shield_dmg"]))

    @staticmethod
    def _block_sources(tsc, tgt_active_effects, defender_armor: int):
        """Sources de block du DEFENSEUR pour `apply_random_block_damage` : block de BASE (scalaire
        `GetStat(7/8)` -> ctx.block_chance/block_damage) PUIS les sources SUPPLEMENTAIRES posees par ses
        effets (`AddExtraBlockEffectToOwner`, ex. BeastSlayer @180e18b70 : chance beastSlayerBlockChance /
        amount = blockDmgPct% du FixedArmor courant) — ABSENTES du scalaire (verifie live orksNob
        blockChance=0), que le natif tient dans `GetMultiValueStat(7)` (`CalculateBlockChances @181002350`).
        ORDRE : base d'abord, effets ensuite (cible sans block de base -> effet = seule source, ordre moot).
        None si aucune source (retro-compat : 0 tirage). Consomme par les 3 vecteurs (normale/ability/splash). #72."""
        if tsc is None:
            return None
        block_chance = int(getattr(tsc.ctx, "block_chance", 0) or 0)
        block_amount = int(getattr(tsc.ctx, "block_damage", 0) or 0)
        sources = []
        if block_chance > 0 and block_amount > 0:
            # block_id = la CHANCE (= `local_88`, l'id natif dans failedList/Contains @181002350) : distingue
            # les sources pour l'exclusion apres-echec inter-coups (cf. _run_hits #72).
            sources.append(BlockSource(chance=block_chance, amount=block_amount, block_id=block_chance))
        sources.extend(defender_effect_block_sources(tgt_active_effects, defender_armor))
        return sources or None

    @staticmethod
    def _crit_params(ctx, attacker_effects) -> tuple:
        """(crit_chance, crit_damage, crit_enabled) de l'ATTAQUANT — GetStat(9/10) + bonus calc-time des
        effets (`GetCritChanceBonusFromEffects @181031180` / `GetCritDamageBonusFromEffects @181031bb0`) ;
        `could_crit` = `CouldCrit @181004fb0`. Partage par les 3 vecteurs (normale/ability/splash)."""
        cc = ctx.stat(StatType.CRIT_CHANCE) + crit_chance_bonus_from_effects(attacker_effects)
        cd = ctx.stat(StatType.CRIT_DAMAGE) + crit_damage_bonus_from_effects(attacker_effects)
        return cc, cd, could_crit(cc, cd)

    @staticmethod
    def _target_limits(tgt, thc, damage_profile: Optional[str] = None,
                       is_special: int = 1) -> Optional[dict]:
        """#67 : champs STATIQUES cible de l'etage LIMITES du COMBAT (`ApplyTraitDamageLimitsToDamage
        @18102c650`) — mirror ECS du `_target_damage_limits` de la PREDICTION (playbook/prediction.py),
        MEME etage partage (`services/trait_damage_limits.py`). Le natif applique cet etage a
        l'EXECUTION aussi : attaque normale via le per-coup d'`ExecuteHit @180e5eff0` (wrappers mode-1
        `ApplyTraitDamageLimitsToAttackDamage @18102c510/@18102c5b0`, virtual-only — l'execution
        reutilise la routine per-coup de prediction, cellules min/max capees AVANT la resolution),
        ability/splash via `CalculateAbilityDamage @18102cb50` (mode 2 : `ApplyTraitDamageLimitsTo
        Damage(2, &dmg, &dmg, profil, cible, ..., hp=hc+0x18, ...)`). `is_special` = le mode natif
        (1=attack -> Impervious applique ; 2=ability) — sans effet offline tant que
        `impervious_stat_current=None` (no-op documente, comme la prediction).
        None = fast-path retro-compat : cible mono-membre sans Resilient -> etage strictement no-op
        (Impervious charge / boss 0x5d4 = no-op documentes de toute facon)."""
        tuc = tgt.get_component(UnitComponent) if tgt is not None else None
        if tuc is None or thc is None or not thc.hp_max:
            return None
        import gameconfig as GC
        gu = GC.unit(tuc.visual_id) or {}
        utraits = set(gu.get("traits") or [])
        n = int(gu.get("nrOfMembers") or 1)
        has_res = "Resilient" in utraits
        if n <= 1 and not has_res:
            return None
        _dp_traits = ((GC.damage_profile(damage_profile) or {}).get("Traits") or []
                      ) if damage_profile else []
        return {
            "is_special": int(is_special),
            "target_has_resilient": has_res,
            "target_has_impervious": "Impervious" in utraits,
            "impervious_stat_current": None,   # charge Impervious non captee offline -> no-op (comme la prediction)
            "member_count": n,                 # GroupUnitComponent (@18102bfe0 lit le composant cible)
            "member_total_hp": int(thc.hp_max),
            "profile_has_hits_multiple_members": DamageTrait.HitsMultipleMembers.name in _dp_traits,
            # `max_health` = param_11 du core : pour l'EXECUTION c'est le HP AU DEBUT DE L'ATTAQUE
            # (ancre per-attaque de l'executeur), PAS hpMax — discrimine live par probe 67201
            # (tour letal hp_depart 784 != hpMax 7530 : le coup rem=1 a TUE, seuil 2x784 ouvert ;
            # contre-datapoint 67111 hp_depart 1513 : rem=1 TENU a 0, seuil 2x1513 ferme). La
            # PREDICTION garde hpMax (son propre appelant PredictAttackRaw, valide tel quel).
            "max_health": int(thc.hp if thc.hp is not None else thc.hp_max),
            "target_has_boss_cap": False,      # HasTriggeredAbility(0x5d4) non verifie offline -> no-op
            "boss_cap_const": 0,
        }

    @staticmethod
    def _apply_defender_flat_reductions(mods, def_mods) -> None:
        """#120 : additif DÉFENSEUR plat PRÉ-perçage (Nightshroud_DmgReduction @180f5bff0 =
        `ForSubtraction(OwnerIsTarget, ConfigVar 0x12=dmgReduction×mult)`) fusionné dans le slot additif
        @+0x10 — le MÊME que l'additif ATTAQUANT #75. `CalculateBaseDamageWithAllModifiers @18102d3f0` ne
        consomme @+0x10 qu'UNE fois, AVANT perçage. Mirror EXACT du merge PRÉDICTION
        (`_add_positional_and_defender_mods`, prediction.py:172) : on SOUSTRAIT de `mods.additive`
        (l'accumulateur ATTAQUANT, consommé pré-perçage via `attacker_additive_pre=True`) → la réduction
        est DILUÉE par perçage/armure PUIS scalée ×%-list UNE fois, comme l'additif #75. SANS pré-scale ×M
        (≠ ForAddition Neuroparasite, qui compense le placement post-%-list). Canal SÉPARÉ de `def_mods.additive`
        (appliqué à part par `apply_all_modifiers`) → aucune double-application. Vide → no-op (rétro-compat)."""
        if def_mods.flat_reductions:
            mods.additive -= sum(def_mods.flat_reductions)

    @staticmethod
    def execute(state: State, attacker_id: int, target_id: int,
                spread_pct: int = 20) -> Optional[dict]:
        """Résolution d'une attaque normale (mirror Execute→ExecuteHits→ExecuteHit) depuis
        l'ECS : tire CHAQUE coup sur la plage BRUTE (`stat Attack` ± spread) avec le MT du
        runner (`state.rng`), réduit (perçage de l'arme par distance + armure cible, mods
        d'effet), puis MUTE les PV de la cible. Renvoie `{hits, total, base, pierce, armor,
        clean_min, clean_max, effects}` ou None si stats/positions manquantes.

        PALIER ACTUEL : crit/block NON tirés (paliers 2). Pour un coup MONO propre (no-crit/
        no-block), `total` == dégât réel live (le tirage de dégât est le 1er conso RNG).
        Multi-coups : tire `hits` fois (valable seulement si le live ne tire pas crit/block
        entre les coups — sinon désync RNG ; couvert au palier crit/block)."""
        if state.rng is None:
            raise ValueError("state.rng non calé (seed depuis dumpRng avant un replay-diff)")
        att = state.get_entity(attacker_id)
        tgt = state.get_entity(target_id)
        sc = att.get_component(StatsComponent) if att is not None else None
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        if sc is None or thc is None:
            return None
        ctx = sc.ctx
        ap = att.get_component(PositionComponent)
        tp = tgt.get_component(PositionComponent)
        # DISTANCE pour la sélection d'arme (mêlée si adjacent, sinon tir). Adjacence HEX via le service
        # PARTAGÉ `BattleQuery.are_tiles_adjacent` (MÊME que la prédiction) : `state.board` → voisins
        # natifs (evenq), fallback géométrie evenq — PAS chebyshev (cheby==1 peut être hex-dist-2 → fausse
        # sélection mêlée d'un tir, ex. overwatch ranged à dist 2).
        dist = None
        if ap is not None and tp is not None:
            adj = are_tiles_adjacent((ap.col, ap.row), (tp.col, tp.row), state.board)
            dist = 1 if adj else 2
        pierce, _ranged, whits = select_weapon_pierce(ctx, dist)
        _w = select_weapon(ctx, dist)
        _profile = _w.get("DamageProfile") if _w else None     # profil du coup (pour vecteurs after-hit)
        ahc = att.get_component(HealthComponent)
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, is_ranged=_ranged,
                                          target_traits=target_trait_names(state, target_id),
                                          target_id=target_id)
        # #58 : feuille positionnelle ELEVATION (+surplomb) ajoutee au `mods` de l'attaquant, comme la
        # prediction (service PARTAGE `calculate_elevation_bonus_modifier` de DamageCalculations ; positions
        # REELLES depuis l'ECS/board).
        apply_elevation_bonus(state, mods, attacker_id, target_id)
        # #181 : reduction TRENCH (feuille positionnelle soeur de l'elevation dans le meme builder natif) —
        # -50% si la cible porte l'effet Trench + conditions attaquant-tuile (calculate_trench_reduction).
        apply_trench_reduction(state, mods, attacker_id, target_id, _profile)
        # Nb de coups : cette execution EST la facade `AttackDamageOperation.GetAttackHits @180e613d0` — elle
        # rassemble les entrees depuis l'ECS puis appelle la FORMULE PARTAGEE `attack_hits_with_modifiers`
        # (`AttackHitsWithModifiersFormula.Calculate @180f0bf50`, MEME formule que la facade prediction) :
        # base weapon+ExtraHits+effets, +malus defenseur (LightCover/Parry) + auras (BigTarget). #62a : le
        # combat ne sommait que weapon+ExtraHits+effets -> divergeait sur (3). BITE 2 (verdict validateur) :
        # GetStuckIn est un behaviour d'exec chance-gate (`AddBonusHitsToCurrentHitGroupBehaviour @180f93410`,
        # roll `Maybe(GetBonusHitChance)` 30%/100%) NON porte -> `include_bonus_hit_behaviours=False` : le combat
        # l'OMET (folder en dur sur-comptait : orksNob 1v1 chance=30 -> natif 3 coups, port 4). TODO #62c.
        if ap is not None and tp is not None:
            _board, _auras, _tgt_eff = build_hits_board(
                state, attacker_id, target_id, (ap.col, ap.row), (tp.col, tp.row), is_melee=not _ranged)
            # A3 (#113) : gate compute-time LightCover -- `AreEqual(coverPatch, target)` @180f556b0 = la CIBLE
            # est-elle sur SA tuile de cover (DryBush) ? state.board porte le terrain (tileDefId, capteur
            # boardGraph #124). Terrain INCONNU (board None / build sans tileDefId) -> None = applique-sur-
            # presence (retro-compat). Empeche un LightCover PERIME (cible ayant quitte la tuile, effet non
            # encore retire faute de B1) de sur-reduire les coups en runner-sim multi-step.
            _t_terrain = state.board.terrain_at(tp.col, tp.row) if state.board is not None else None
            _on_cover = (_t_terrain == LIGHT_COVER_TILE_ID) if _t_terrain is not None else None
            hits = attack_hits_with_modifiers(
                weapon_hits=whits, extra_hits=ctx.stat(StatType.EXTRA_HITS),
                extra_hits_melee=ctx.extra_hits_melee,
                attacker_effects=active, trait_objects=ctx.trait_objects(),
                target_effects=_tgt_eff, aura_sources=_auras, board=_board,
                is_melee=not _ranged, damage_profile=_profile,
                include_bonus_hit_behaviours=False,  # combat: GetStuckIn = behaviour chance-gate non porte (BITE 2)
                defender_on_cover=_on_cover)
        else:                                     # positions manquantes -> base seule (pas de GetStuckIn/aura)
            hits = max(1, whits + ctx.stat(StatType.EXTRA_HITS) + hits_bonus_from_effects(active))
        tsc = tgt.get_component(StatsComponent)
        # armure défenseur = FOYER PARTAGÉ `defender_fixed_armor` : GetStat(16) [effet-inclusif : les stat-mods
        # +armor d'effet, dont le stat-mod EAGER self de ProtectorImperative, sont cuits dans GetStat] + AURA
        # +FixedArmor d'un ALLIÉ Mechanical ADJACENT porteur de ProtectorImperative (self auto-exclu ⇒ pas de
        # double-compte), ré-évaluée par adjacence. Court-circuit non-Mechanical ⇒ base seule (cas courant).
        armor = defender_fixed_armor(state, target_id)
        # DÉFENSEUR : réductions de dégât reçu portées par les effets de la CIBLE (symétrique attaquant ;
        # CalculateDefenderModifiersForPrediction). Vide → no-op (apply_all_modifiers identité). Couvre la
        # famille ADamageDefenseModifierAbilityEffect ; STAT/Parry/triggers = axes séparés (cf. §1.8).
        # #59 : threade is_melee (= coup mêlée = arme non-rangée) + profil de dégât → malus gatés corrects
        # (Terrifying_ExtraDefense gate IsMeleeAttack ; TerminatorArmour exclut Psychic/DirectDamage). Mirror
        # de la prédiction. #59 suite : les chemins ABILITY (execute_ability_attack/execute_normal_like)
        # câblent DÉSORMAIS ces gates aussi (params damage_profile/is_melee threadés par tous leurs callers).
        def_mods, _def_active = defender_modifiers(state, target_id, thc.hp,
                                                   is_melee=not _ranged, damage_profile=_profile,
                                                   attacker_id=attacker_id, is_normal_attack=True)  # #112
        # BLOCK (cible) = base (scalaire GetStat 7/8) + sources d'effet (ex. BeastSlayer) — helper PARTAGE
        # par les 3 vecteurs (normale/ability/splash), mirror du `GetMultiValueStat(7)`/CalculateBlockChances
        # @181002350 unique du natif. Besoin des effets actifs de la cible -> apres defender_modifiers.
        block_sources = AttackDamageOperation._block_sources(tsc, _def_active, armor)
        # ORDRE RÉEL (confirmé live 18/18 coups, 3 seeds, necroDestroyer 6h) : le HitDamage natif
        # porte la plage RÉDUITE — la réduction (perçage/armure/modifiers attaquant+défenseur) est
        # appliquée aux BORNES base±spread D'ABORD, puis le tirage `GetDamage` se fait DANS cette plage
        # réduite (next_internal(min_réduit, max_réduit+1)). PAS spread-brut-puis-réduit (qui donne la
        # bonne PLAGE totale mais de mauvaises valeurs par coup — le modulo dépend de la largeur).
        # CRIT — modèle CONFIRMÉ bit-exact (genrand brut live, necroDestroyer CC=100/CD=500 → 12 tirages
        # /6 coups : 1 crit-roll + 1 spread PAR COUP). Le crit du COMBAT n'est PAS l'`ApplyCritDamage`
        # post-réduction de la PRÉDICTION : il s'ajoute à la BASE D'ATTAQUE AVANT spread/perçage
        # (chemin `GetBaseDamageFix64`@181030ba0 param_4=isCrit/param_5=critBonus = +FromInt(critDamage)).
        # ⇒ `eff_attack = attack + critDamage` PAR COUP qui crite, puis MÊME pipeline (spread→perçage→mods).
        # Preuve : non-crit spread(906)=181→{725,1087}×0.6=[435,652] ; crit eff=1406, spread=281→
        # {1125,1687}×0.6=[675,1012] (=W338 du solveur, ×1.552=(906+500)/906) ; next_internal(675,1013)
        # aux tirages IMPAIRS = live [932,882,967,867,961,955] À L'UNITÉ.
        # ORDRE PAR COUP (confirmé par positions genrand) : RollCritical D'ABORD (tirage pair), spread APRÈS
        # (tirage impair). `roll_critical` ne tire QUE si cc≥1 — gate `cc<1 → false SANS tirage` de
        # `DamagePrediction.RollCritical @1810387a0` (l'UNIQUE chemin crit d'`ExecuteHit`, slot 0xa ;
        # `DamageCalculations.RollCritical @1810057b0` = le NextBool brut DERRIÈRE ce gate) — cc=0 ⇒ 0 tirage
        # ⇒ rétro-compat exacte du multi-coups non-crit validé (18/18 + probe_rngcrit_1202 branche A).
        # NB cas fable rngcrit-1202 : le « crit-roll fantôme » mesuré par #220/#205 sur les attaques
        # d'ABILITY multi-coups à cc=0 n'était PAS un crit-roll (réfuté décompile + live M1/M2) mais le
        # resolve slot-8 GASPILLÉ du vecteur ability — cf. `_one_hit`. Gate `could_crit` = cc>0 ET cd>0
        # (CouldCrit@181004fb0).
        # crit = GetStat(9/10) [DÉJÀ effet-inclusif : les effets StatModification sur la crit sont
        # cuits dans GetStat → dans le combatSnapshot → dans ctx] + couche calc-time SÉPARÉE
        # GetCritChanceBonusFromEffects/GetCritDamageBonusFromEffects (PAS dans GetStat → sommée ici
        # depuis les effets ACTIFS de l'attaquant). Mirror exact de RollCritical/CalculateCriticalDamage.
        crit_chance, crit_damage, crit_enabled = AttackDamageOperation._crit_params(ctx, active)
        # #120 : réduction PLATE défenseur (Nightshroud) fusionnée dans l'additif pré-perçage (mirror prédiction).
        AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)

        def _reduced_bounds(eff_attack: int, hit_mult: int = 1, flat_add: int = 0) -> "HitDamage":
            # #75 (case-68 MAJ 13) : additif ForAddition ATTAQUANT = PRÉ-perçage en COMBAT
            # (attacker_additive_pre=True : bornes (base±spread)+additif → GDWP → %-list ; le natif
            # passe à CalculateAbilityDamage @18102cb50 un dégât DÉJÀ additivé, CBDWAM @18102d3f0 ne
            # consomme pas Addition@+0x10). Bit-exact 3/3 orksNob SmashaEad (599, pierce 50, armure 2208).
            # `flat_add` (#45f) = EffectBonus.addition PER-BRANCHE (Ice crit-only) : POST-spread
            # PRE-perçage (même position que mods.additive #75), sans poluer `mods` (qui s'applique
            # aux DEUX branches nc/cr).
            mm = get_base_damage_fix64(eff_attack, spread_pct=spread_pct)
            lo = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.min + flat_add, pierce, armor, mods, hit_mult=hit_mult, attacker_additive_pre=True), def_mods)
            hi = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.max + flat_add, pierce, armor, mods, hit_mult=hit_mult, attacker_additive_pre=True), def_mods)
            return HitDamage(lo, hi)

        # MkXGravis (trait CIBLE 0x3f5=1013) : les dégâts entrants traversent l'armure 2× SAUF au crit
        # (i2 « Does not apply to Crits ») → hit_mult=2 sur la plage NON-crit, =1 (défaut) sur la plage
        # crit. Mirror `GetBaseDamageWithFixedPiercedArmor @181030d10` (HasTrait(0x3f5) && !isCrit) dans
        # le chemin COMBAT `CalculateAbilityDamage @18102cb50` → `CalculateBaseDamageWithAllModifiers
        # @18102d3f0` (décompile-confirmé, #180). No-op (=1) hors cible hit-twice.
        _tgt_hit_mult = target_hit_multiplier(tsc.ctx.trait_objects()) if tsc is not None else 1
        # #45f : bonus crit-sur-Ice (`IceEffect.CreateEffectDamageBonusForAttack @180f44940`) — flat
        # PER-COUP-CRIT = PercentageOf(GetStat(10), IceCritDmgBonusPct) si cible sur tuile Ice active
        # et non-Immune. 0 hors gate / cd=0 (no-op rétro-compat, mesuré +175 probe_45f --case crit).
        _ice_add = ice_crit_damage_addition(state, attacker_id, target_id, ctx) if crit_enabled else 0
        hit_nc = _reduced_bounds(ctx.stat(StatType.ATTACK), hit_mult=_tgt_hit_mult)   # NON-crit → double-armure MkXGravis
        hit_cr = _reduced_bounds(ctx.stat(StatType.ATTACK) + crit_damage,
                                 flat_add=_ice_add) if crit_enabled else hit_nc  # crit: hit_mult=1 (exempt)
        # #202 WeaverOfFate : attaquant max-out (effet 1185) -> bornes degenerees a (max, max), mirror
        # HitDamage(max, null) de `AttackDamageBehaviour.GetDamage @180fbb250` (cf. _apply_max_out).
        hit_nc, hit_cr = AttackDamageOperation._apply_max_out(state, attacker_id, hit_nc, hit_cr)
        clean_min = hit_nc.min * hits          # référence affichée = plage non-crit (× hits)
        clean_max = hit_nc.max * hits
        # BOUCLIER cible : absorbe le coup réduit AVANT les PV (CalculateDamageOperation shield-first) ;
        # _run_hits déplète le bouclier entre coups (shield -= dmg.shield), total = part SANTÉ seule.
        shc, shield_total = AttackDamageOperation._target_shield(tgt)
        # #62c GetStuckIn (combat) : chance des coups bonus (behaviour Maybe chance-gate @180f83280) — None si
        # l'attaquant ne porte pas GetStuckIn ou si la cible est a >2 hex. cf. getstuckin_combat_chance + _run_hits.
        _gsi = getstuckin_combat_chance(state, attacker_id, target_id,
                                        (ap.col, ap.row) if ap is not None else None,
                                        (tp.col, tp.row) if tp is not None else None, state.board)
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources, shield=shield_total,
                                            bonus_hit_chance=_gsi,
                                            capped_reductions=def_mods.capped_reductions,
                                            # #67 : etage limites (member-cap/Resilient/bypass Blast) —
                                            # mode 1 = attaque (wrapper @18102c510/@18102c5b0)
                                            limits=AttackDamageOperation._target_limits(
                                                tgt, thc, _profile, is_special=1),
                                            limits_hp=int(thc.hp or 0))
        AttackDamageOperation._deplete_shield(shc, r)
        death = AttackDamageOperation._apply_damage_pipeline(           # chokepoint partage (#202)
            state, target_id, attacker_id, tgt, thc, r["total"], _profile,
            r["shield_dmg"], r["armor_dmg"])
        # #202-B : coups additionnels HETEROGENES (canal #179, face COMBAT) — sous-operations APRES
        # les coups d'arme (mirror @180e70600), chacune son RegisterDamage au profil PROPRE.
        _ah = execute_additional_hits(
            state, attacker_id, target_id, tgt, thc,
            collect_additional_hit_groups(
                state, attacker_id, target_id, active, not _ranged, _def_active),
            mods, def_mods, armor, _tgt_hit_mult, block_sources, shc,
            spread_pct=spread_pct, extra_pierce=ctx.extra_pierce)
        if _ah is not None:
            death = death or _ah.get("death")
        return {"hits": hits, "total": r["total"], "base": ctx.stat(StatType.ATTACK), "pierce": pierce,
                "armor": armor, "clean_min": clean_min, "clean_max": clean_max, "death": death,
                "shield_dmg": r["shield_dmg"], "armor_dmg": r["armor_dmg"],
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"],
                "ranged": _ranged, "profile": _profile,
                "additional_hits": _ah,          # #202-B : sous-operations #179 (None = aucun groupe)
                "effects": [getattr(e, "name", None) for e in active]}

    @staticmethod
    def _run_hits(rng: IntBasedMersenneTwister, hit_nc: "HitDamage", hit_cr: "HitDamage",
                  crit_chance: int, crit_enabled: bool, hits: int, block_sources,
                  shield: int = 0, armor_pool: int = 0, armor_pct: int = 0, post_roll=None,
                  bonus_hit_chance: Optional[int] = None, capped_reductions=None,
                  limits: Optional[dict] = None, limits_hp: int = 0,
                  wasted_resolve: bool = True, force_overkill: bool = False) -> dict:
        """Boucle PAR COUP partagée (attaque normale ET ability) : pour chaque coup, crit-roll D'ABORD
        (1 tirage NextBool si cc>=1, sinon 0) PUIS tirage dans `hit_cr`/`hit_nc`, PUIS split combat
        (bouclier/armure-pool/block, `calculate_damage_operation`). Ordre RNG crit->spread->block confirmé.

        `post_roll` = réduction perçage/armure/mods APPLIQUÉE APRÈS le tirage (None = déjà appliquée aux
        bornes). DEUX ordres distincts (confirmés live) :
          • ATTAQUE NORMALE = reduce-then-roll : `hit_nc`/`hit_cr` = bornes DÉJÀ réduites, `post_roll=None`.
          • ABILITY = roll-then-reduce : `hit_nc`/`hit_cr` = bornes BRUTES config (RandomAmount(min,max)),
            `post_roll=_reduce` → on tire le BRUT puis on réduit (modulo sur la largeur BRUTE != réduite ;
            confirmé bit-exact ThunderousAssault: roll-then-reduce draw0 = live 6948).

        #62c GetStuckIn (COMBAT) : si `bonus_hit_chance` non None (attaquant porteur GetStuckIn + cible à
        <=2 hex, cf. `getstuckin_combat_chance`), APRÈS crit+spread+block de chaque coup d'INDEX IMPAIR
        (0-based) on tire 1 `next_bool(chance)` — mirror du behaviour `Maybe(AddBonusHits, GetBonusHitChance)`
        (`CreateBehaviour @180f83280`, roll `MaybeBehaviour.Execute @180fc9dc0`) évalué dans
        `EvaluateAfterHitTriggers @180e25fc0` (dernière instr. de `ExecuteHit`). Chaque SUCCÈS d'un coup de
        BASE ajoute 1 coup bonus DÉFÉRÉ (FIFO, `ExecuteAdditionalHitsWithoutDamageProfileType @180e5e7c0`,
        gate natif `attack.count==1 && !additionalHitsFlag`) exécuté APRÈS la boucle de base, MÊME profil
        réduit. Un coup bonus d'index impair RE-tire un Maybe (tirage consommé) mais son succès est IGNORÉ
        (anti-récursion). `bonus_hit_chance is None` (défaut) => strict no-op (rétro-compat totale).

        `force_overkill` (défaut False) = flag « always overkilled » d'un `AttackWithAttackDamage` natif
        (Nullable<bool>=true, 8e arg de `DSLFactory.AttackWithAttackDamage @180de9fb0` -> `AttackDamageBehaviour`
        -> `ApplyTraitDamageLimitsToDamage @18102c650`) : force `overkill=True` a CHAQUE coup dans les 3 sites de
        calcul `_ovk`, ce qui BYPASSE le cap Resilient (`ApplyResilientTraitDamageLimit @18102c3a0` :
        `if not overkill: cap = curHP-1`). N'affecte QUE le cap Resilient (member-cap/boss/impervious ne lisent
        PAS `overkill`) -> NO-OP sur cible non-Resilient (zero regression) ET aucune conso RNG supplementaire
        (change seulement la VALEUR capee, pas le nombre de tirages). Porteur unique : FlailSwing (1042).
        Renvoie total/per_hit/rolls/crits + flags. Pools déplétés entre coups (0 -> invariant)."""
        total = shield_dmg = armor_dmg = 0
        did_crit = did_block = did_evade = False
        crits: list[bool] = []
        rolls: list[int] = []
        per_hit: list[int] = []
        failed_block: set = set()          # ids de sources de block AYANT ECHOUE (accumule ENTRE coups, #72)
        # #91 : réduction CAPÉE défenseur (GuardianOrganism) = scalaire FLAT pré-évalué (natif @18102d3f0) où
        # D = CurrentDamage = CENTRE des bornes réduites (post pierce/armure/%-mods) -> soustrait IDENTIQUE à
        # chaque coup, PAS 33%×valeur-tirée (confirmé LIVE #91). Un flat par type de coup (non-crit/crit).
        _capped_flat_nc = capped_reduction_flat((hit_nc.min + hit_nc.max) / 2.0, capped_reductions) \
            if capped_reductions else 0
        _capped_flat_cr = capped_reduction_flat((hit_cr.min + hit_cr.max) / 2.0, capped_reductions) \
            if capped_reductions else 0
        _rogne = [0]        # #67 : rogne cumule des cellules MIN des coups precedents (porte overkill)

        def _one_hit_tail(idx: int, crit: bool, roll: int) -> bool:
            """Queue PARTAGÉE d'un coup : split combat (sub-op 0x42) + comptabilité + Maybe GetStuckIn.
            #72 : mirror `CalculateBlockChances(param_4=failedList)` @181002350 -> une source de block
            AYANT ECHOUE a un coup precedent est EXCLUE des coups suivants (Contains(failedList, id)) ;
            une source qui REUSSIT reste jouable (ApplyRandomBlockDamage return sans AddFailedBlockId).
            Donc une source est jouee chaque coup JUSQU'A son 1er echec, puis plus (aucun tirage). Preuve
            live (orksNob BeastSlayer chance=10) : hit1 succes + hit2 echec -> 0 roll hits 3-6 = 8 tirages."""
            nonlocal total, shield, armor_pool, shield_dmg, armor_dmg, did_crit, did_block, did_evade
            hit_block = ([s for s in block_sources if s.block_id not in failed_block] or None
                         ) if block_sources else None
            dmg: Damage = calculate_damage_operation(
                roll, shield=shield, armor_pool=armor_pool, armor_pct=armor_pct,
                block_sources=hit_block, evasion_branch=False, rng=rng)
            failed_block.update(dmg.failed_block_ids or [])
            shield = max(0, shield - dmg.shield)
            armor_pool = max(0, armor_pool - dmg.armor)
            per_hit.append(dmg.get_total())
            total += dmg.health
            shield_dmg += dmg.shield
            armor_dmg += dmg.armor
            did_crit |= crit
            did_block |= dmg.did_block
            did_evade |= dmg.did_evade
            # #62c : behaviour Maybe(GetBonusHitChance) sur coup d'INDEX IMPAIR (0-based), APRES le degat.
            if bonus_hit_chance is not None and (idx % 2 == 1):
                return rng.next_bool(bonus_hit_chance)      # 1 tirage genrand (chance 30/100, toujours >=1)
            return False

        def _one_hit(idx: int) -> bool:
            """Un coup complet crit->spread->block + le roll Maybe GetStuckIn si `idx` impair. Renvoie True
            si le Maybe a RÉUSSI (coup bonus à spawner) — le caller décide de l'exécuter (base) ou l'ignore
            (bonus, anti-récursion).

            CONSOMMATION RNG PER-COUP — mirror `AttackDamageOperation.ExecuteHit @180e5eff0` (per-coup
            PARTAGÉ attaque normale ET ability AttackWithAttackDamage ; cas fable rngcrit-1202, 2026-07-23) :
              1. `HitDamage.GetDamage @181007bf0` sur le STRUCT d'entrée — tirage SSI struct.min != max :
                 - NORMALE : struct DÉGÉNÉRÉ (Attack,Attack) -> 0 tirage (la vraie valeur = étape 4) ;
                 - ABILITY bounds-mode : struct = [minDmg,maxDmg] config -> 1 tirage = LA VALEUR (brut).
              2. `RollCritical` slot 0xa -> `DamagePrediction.RollCritical @1810387a0` : gate `cc<1 ->
                 false SANS tirage` (le NextBool brut `DamageCalculations.RollCritical @1810057b0` n'est
                 atteint QU'À travers ce gate) + bypass crit-garanti (byte +0x2c / buff slot 4) qui SKIPPE
                 le roll. Il n'existe AUCUN chemin consommant un tirage crit à cc=0 — ni par vecteur, ni
                 par « éligibilité » : l'éligibilité crit d'une ability se matérialise par cc=0.
              3. slot 4 `CalculateDamageOperation @18102dc30` : shield-part/armure/caps -> cellules
                 min/max (0 RNG ; les block CHANCES y sont calculées, pas roulées).
              4. slot 8 `RandomlyResolveMinMaxDamage @181038600` : `Next(min, max+1)` — TOUJOURS 1 tirage
                 (AUCUN gate min==max) :
                 - NORMALE : cellules = bornes RÉDUITES (largeur > 1) -> ce tirage EST la valeur ;
                 - ABILITY : cellules DÉGÉNÉRÉES (reduce(rolled), idem) -> tirage GASPILLÉ (largeur 1).
              5. sub-op 0x42 : block rolls + splits (= `calculate_damage_operation`, APRÈS le resolve —
                 prouvé par #72 valeur-puis-block bit-exact).
            => NORMALE cc=0 : 1 tirage/coup (validé 18/18 + probe A 4 seeds) ; ABILITY bounds cc=0 :
            2 tirages/coup (probe_rngcrit_1202 : M3 bit-exact per-hit 5 seeds x2 cibles, 6 tirages/3 coups
            = mesure #220 réconciliée : l'« extra tirage » N'EST PAS un crit-roll, c'est le GetDamage brut
            + resolve dégénéré). Les modèles « crit-roll par coup à cc=0 » (valeur aux tirages impairs)
            sont RÉFUTÉS par la mesure (M1/M2 mismatch total ET per-hit)."""
            nonlocal total, shield, armor_pool, shield_dmg, armor_dmg, did_crit, did_block, did_evade
            if post_roll is not None:
                # VECTEUR ABILITY bounds-mode (roll-then-reduce) — ordre natif ExecuteHit :
                # (1) VALEUR = tirage BRUT dans les bornes config (GetDamage-top, struct min<max).
                raw = hit_nc.get_damage(rng)
                # (2) crit-roll APRÈS le tirage de valeur (gate cc<1 -> 0 tirage, cf. bloc ci-dessus).
                crit = roll_critical(rng, crit_chance) if crit_enabled else False
                crits.append(crit)
                if crit:
                    # `CalculateCriticalDamage @18102da90` -> `ApplyCritDamage @181000210` : critBonus
                    # FLAT sur la valeur ROULÉE, PRE-reduce. Le montant = le SHIFT des bornes crit
                    # (hit_cr = bornes + critDamage, largeurs égales -> même modulo => numériquement ==
                    # l'ancien modèle bornes-décalées).
                    raw += hit_cr.min - hit_nc.min
                roll = post_roll(raw)         # réduction perçage/armure/mods APRÈS le tirage
                if capped_reductions:         # #91 : réduction CAPÉE défenseur (scalaire FLAT, D=centre)
                    roll = max(0, roll - (_capped_flat_cr if crit else _capped_flat_nc))
                rolls.append(roll)            # rolls = tirage POST-mods PRE-limites
                if limits is not None and roll > 0:
                    # ABILITY : cap scalaire post-tirage (cellule degeneree, CalculateAbilityDamage)
                    _rem = max(0, limits_hp - total)
                    _ovk = force_overkill or (compute_prediction_overkill(_rem, limits_hp, roll, p12=_rogne[0])
                                              if limits_hp > 0 else False)
                    _pre = roll
                    roll = apply_trait_damage_limits_to_damage(roll, current_health=_rem,
                                                               overkill=_ovk, **limits)
                    _rogne[0] += max(0, _pre - roll)
                # (4) resolve slot 8 sur la cellule DÉGÉNÉRÉE -> 1 tirage GASPILLÉ, valeur inchangée
                # (`RandomlyResolveMinMaxDamage @181038600` : Next(v, v+1) SANS gate largeur-1). C'EST le
                # tirage « fantôme » mesuré par #220/#205 — le fix du désync multi-coups cc=0.
                # `wasted_resolve` = LA FAMILLE DE FACTORY NATIVE (deux operations distinctes) :
                #   True  = `DSLFactory.AttackWithAttackDamage @180de9fb0` (+overloads @180dea180/350/
                #           520/6b0) -> AttackDamageBehaviour -> AttackDamageOperation.ExecuteHit
                #           @180e5eff0 -> le resolve slot-8 consomme (2 tirages/coup a cc=0) ;
                #   False = `DSLFactory.AttackWithAbilityDamage @180de9c90/@180de9dd0 -> core @180de9e50`
                #           -> AbilityDamageBehaviour -> AbilityDamageOperation.ExecuteHits @180e2a860
                #           (GetDamage par coup) + CalculateAbilityDamage @18102cb50 (0 RNG) : AUCUN
                #           resolve -> 1 tirage/coup. Mesure live : Stormcaller 3-hit bit-exact SANS
                #           tirage gaspille (probe_217 PASS pre-fix, FAIL avec un resolve inconditionnel).
                if wasted_resolve:
                    rng.next_internal(max(0, roll), max(0, roll) + 1)
                return _one_hit_tail(idx, crit, roll)
            crit = roll_critical(rng, crit_chance) if crit_enabled else False
            crits.append(crit)
            hd = hit_cr if crit else hit_nc
            # #67 : etage LIMITES du natif (`ApplyTraitDamageLimitsToDamage @18102c650`) — MEME etage
            # partage que la prediction (`services/trait_damage_limits.py`, bit-exact 1357 s16) :
            # member-cap Swarm (443/443/444/444, live run 60102 + probe 67061 vs scarab plein) +
            # Resilient HP-1 (porte overkill) + bypass Blast (HitsMultipleMembers, probe 67071).
            # `_rem` = HP restant avant CE coup (le natif relit le HealthComponent entre coups ; ici
            # `limits_hp - total`). Deux ORDRES natifs distincts, discrimines live (probe 67101) :
            #  - ATTAQUE (mode 1) : les caps s'appliquent aux BORNES min/max PUIS le tirage se fait
            #    DANS la plage capee (routine per-coup slot-4 -> resolution slot-8 d'`ExecuteHit
            #    @180e5eff0` ; le core cape *param_3/*param_4 = cellules min et max). Preuve : tour
            #    letal live [505,541,602,206] — coup 3 tire 602 dans [lo, cap=808] (largeur CAPEE :
            #    le meme tirage donnait >=809 en pleine largeur), coup 4 degenere [206,206] = rem-1.
            #    Le tirage est TOUJOURS consomme (RandomlyResolveMinMaxDamage @181038600 appelle
            #    Next(min,max+1) SANS gate min==max — largeur 1 = 1 tirage quand meme) -> les caps
            #    TOTAUX (swarm : cap < lo, plage degeneree) restent bit-exacts en consommation.
            #  - ABILITY/splash (mode 2) : cap SCALAIRE post-tirage — `CalculateAbilityDamage
            #    @18102cb50` recoit le degat DEJA resolu et passe la MEME cellule deux fois
            #    (`&dmg, &dmg` : degenere par construction).
            # PORTE OVERKILL (probes 67072/67081/67111/67201) : accum du core = `(param_11 -
            # param_9) + param_12 + *param_3` (cellule MIN pre-cap) avec param_11 = HP AU DEBUT DE
            # L'ATTAQUE (= limits_hp ; discrimine par 67201 vs 67111, cf. _target_limits), param_9
            # = rem frais, param_12 = ROGNE cumule des coups precedents (rogne de la cellule MIN :
            # 67081 coup2-cape/coup3-letal excluent p12=0 ET p12=brut-cumule). Seuil = 2x hp_depart
            # (overkillDmgPctOfHealth=100).
            # RESIDU documente : cible bouclier + multi-membre/Resilient — CalculateAbilityDamage
            # cape le reste POST-part-bouclier (iVar20=min(dmg,shield) re-additionne apres) alors
            # qu'ici le cap precede le split ; identique tant que shield=0 (tous les cas valides).
            if limits is not None and int(limits.get("is_special") or 1) == 1:
                # ATTAQUE : cap des bornes AVANT le tirage (largeur du modulo = plage capee)
                flat = (_capped_flat_cr if crit else _capped_flat_nc) if capped_reductions else 0
                lo_pre = max(0, hd.min - flat)
                hi_pre = max(0, hd.max - flat)
                _rem = max(0, limits_hp - total)
                _ovk = force_overkill or (compute_prediction_overkill(_rem, limits_hp, lo_pre, p12=_rogne[0])
                                          if limits_hp > 0 else False)
                lo = apply_trait_damage_limits_to_damage(lo_pre, current_health=_rem,
                                                         overkill=_ovk, **limits)
                hi = apply_trait_damage_limits_to_damage(hi_pre, current_health=_rem,
                                                         overkill=_ovk, **limits)
                _rogne[0] += max(0, lo_pre - lo)
                roll = rng.next_internal(lo, hi + 1)   # TOUJOURS 1 tirage (mirror slot 8, sans gate)
                rolls.append(roll)
            else:
                roll = hd.get_damage(rng)
                if capped_reductions:         # #91 : réduction CAPÉE défenseur (GuardianOrganism) = scalaire FLAT
                    roll = max(0, roll - (_capped_flat_cr if crit else _capped_flat_nc))  # (D=centre bornes)
                rolls.append(roll)            # rolls = tirage POST-mods PRE-limites (cap lisible dans per_hit)
                if limits is not None and roll > 0:
                    # cap scalaire post-tirage (cellule degeneree, CalculateAbilityDamage)
                    _rem = max(0, limits_hp - total)
                    _ovk = force_overkill or (compute_prediction_overkill(_rem, limits_hp, roll, p12=_rogne[0])
                                              if limits_hp > 0 else False)
                    _pre = roll
                    roll = apply_trait_damage_limits_to_damage(roll, current_health=_rem,
                                                               overkill=_ovk, **limits)
                    _rogne[0] += max(0, _pre - roll)
            return _one_hit_tail(idx, crit, roll)

        base_bonus = 0
        for i in range(hits):
            if _one_hit(i):
                base_bonus += 1
        # #62c : coups bonus DEFERES (FIFO) apres la boucle de base — exactement `base_bonus` coups (count=1
        # par succes). Chaque coup bonus repasse le corps complet (crit/spread/block + re-roll Maybe si son
        # index est impair) ; son succes eventuel est IGNORE (pas de recursion, garde native).
        bonus_idx = hits
        for _ in range(base_bonus):
            _one_hit(bonus_idx)
            bonus_idx += 1
        return {"total": total, "shield_dmg": shield_dmg, "armor_dmg": armor_dmg,
                "did_crit": did_crit, "did_block": did_block, "did_evade": did_evade,
                "crits": crits, "rolls": rolls, "per_hit": per_hit,
                "bonus_hits": base_bonus}

    @staticmethod
    def execute_ability_attack(state: State, attacker_id: int, target_id: int,
                               base_min: int, base_max: int, profile_pierce: int,
                               hits: int, damage_profile: Optional[str] = None,
                               is_melee: Optional[bool] = None,
                               ability_type: Optional[int] = None,
                               wasted_resolve: bool = True,
                               force_overkill: bool = False) -> Optional[dict]:
        """Attaque d'une ABILITY active (mirror `AttackWithAttackDamage` + `MinMaxDamage`/`GetHits`/
        `GetDamageProfile`). DIFFÈRE de l'attaque normale par la BASE : les bornes du coup = `[base_min,
        base_max]` données par la config d'ability (`GetVariableForLevel` clés 0xc/0xd = minDmg/maxDmg),
        PAS `Attack ± spread%`. Le perçage = celui du PROFIL de l'ability (`GetDamageProfile`). Même
        per-coup natif partagé (`ExecuteHit @180e5eff0`) via `_run_hits`, mais en mode ROLL-THEN-REDUCE :
        valeur = tirage BRUT dans [base_min, base_max] puis réduction, + 1 resolve GASPILLÉ par coup
        (cf. `_one_hit`, cas fable rngcrit-1202). Mute les PV de la cible.

        `RandomAmount(min,max)` natif = tirage uniforme dans [min,max] (= `get_damage` sur des bornes
        déjà = [min,max]). Perçage de l'arme normale + ExtraPierce stats : ici on applique le perçage du
        PROFIL d'ability + ExtraPierce de la cible-source comme l'attaque normale (réduction commune).

        DÉFENSIF : si `state.rng` n'est pas calé (replay effet-seul, sans dumpRng), on SKIP le dégât
        (return None) au lieu de lever — le wiring d'ability reste utilisable pour matérialiser un effet
        sans replay de dégât. Un replay de DÉGÂT doit caler rng (dumpRng) avant le cast."""
        if state.rng is None:
            return None
        att = state.get_entity(attacker_id)
        tgt = state.get_entity(target_id)
        sc = att.get_component(StatsComponent) if att is not None else None
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        if sc is None or thc is None:
            return None
        ctx = sc.ctx
        ahc = att.get_component(HealthComponent)
        # #217 : vecteur ABILITY -> is_normal_attack=False côté ATTAQUANT aussi (symétrique du #112
        # défenseur ci-dessous). MESURÉ live (probe_217 B, cast Stormcaller avec effet LordOfTempests
        # ACTIF + 3 hexes glacés ring-1 à l'attaque) : natif +0, offline-sans-gate +extraDmg x3 x3 hits
        # -> le natif n'applique PAS les bonus attaquant normal-only aux attaques d'ability.
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, target_id=target_id,
                                          is_normal_attack=False)
        # #45f (fable, cause racine du residu x1.5 GreatFrostAxe case-220) : les feuilles POSITIONNELLES
        # (elevation +ElevationBonus=50% si elev(att) > elev(cible), gate effet 0x423 ; trench -50%) du
        # builder de mods ATTAQUANT s'appliquent a la famille ATTACK **SEULEMENT** — gate par FAMILLE de
        # factory native (== `wasted_resolve`, cf. _one_hit) :
        #   - ATTACK (`AttackWithAttackDamage @180de9fb0` -> `AttackDamageOperation.ExecuteHit
        #     @180e5eff0`) : le per-coup construit les mods attaquant COMPLETS (slot +4, positional
        #     leaves incluses). MESURE (probe_45f_gfa_elevation, GreatFrostAxe, une variable = la
        #     relation d'elevation) : pre-fix high = live 1.5000x offline sur CHAQUE coup (DidCrit=0),
        #     flat/low = bit-exact ; post-fix 16/16 bit-exact.
        #   - ABILITY (`AttackWithAbilityDamage @180de9dd0` -> `AbilityDamageOperation.ExecuteHit
        #     @180e29d50`) : `CalculateAbilityDamage @18102cb50` recoit des mods ATTAQUANT **VIDES**
        #     (struct zeroee) — seuls les mods DEFENSEUR (slot 0xf) s'appliquent. AUCUNE elevation.
        #     MESURE (probe_217_stormcaller A : Njal elev 2 > cibles elev 1) : live SANS elevation ;
        #     un fix non-gate rendait l'offline 1.5006x TROP HAUT — le gate famille retablit bit-exact.
        # Le chemin attaque NORMALE (`execute`, #58/#181) reste inchange (ExecuteHit @180e5eff0 aussi).
        if wasted_resolve:                                   # famille ATTACK only
            apply_elevation_bonus(state, mods, attacker_id, target_id)
            apply_trench_reduction(state, mods, attacker_id, target_id, damage_profile)
        tsc = tgt.get_component(StatsComponent)
        armor = defender_fixed_armor(state, target_id)   # FOYER partagé (base GetStat(16) + aura Protector allié)
        # #59 suite : threade is_melee + profil de l'ability -> malus DÉFENSEUR gatés (Terrifying_ExtraDefense
        # IsMeleeAttack ; TerminatorArmour DamageProfileIs). None (caller non mis à jour) = comportement
        # historique (gates non appliqués) — INERTE pour une cible sans effet de défense gaté.
        def_mods, _da = defender_modifiers(state, target_id, thc.hp,
                                           is_melee=is_melee, damage_profile=damage_profile,
                                           attacker_id=attacker_id, is_normal_attack=False)  # #112 spéciale
        # BLOCK (cible) = base (GetStat 7/8) + sources d'effet (BeastSlayer...) via le helper PARTAGE
        # `_block_sources` (mirror du GetMultiValueStat(7)/CalculateBlockChances@181002350 unique du natif).
        block_sources = AttackDamageOperation._block_sources(tsc, _da, armor)
        crit_chance, crit_damage, crit_enabled = AttackDamageOperation._crit_params(ctx, active)
        # #45f : la famille ABILITY (`AbilityDamageOperation.ExecuteHit @180e29d50`) n'a AUCUN chemin
        # crit — pas d'appel RollCritical (le slot crit n'existe que dans `AttackDamageOperation.
        # ExecuteHit @180e5eff0`), l'AttackHit est construit isCrit=0, et `CalculateAbilityDamage
        # @18102cb50` est 0-RNG. MESURE (probe_45f --case scrit : Njal --crit 100,700, Stormcaller) :
        # live crits=[0,0,0] et 1 tirage/coup (valeurs = draws consecutifs) la ou l'offline non-gate
        # brulait 1 crit-roll/coup + ajoutait crit flat. cc=0 (tous les porteurs actuels) : strict
        # no-op (roll_critical deja gate cc<1). Le bonus crit-Ice suit (crit_enabled=False -> 0).
        if not wasted_resolve:                               # famille ABILITY : crit inexistant
            crit_chance, crit_damage, crit_enabled = 0, 0, False
        # #120 : réduction PLATE défenseur (Nightshroud, ungated -> spéciales aussi) fusionnée pré-perçage.
        AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)
        # MkXGravis (trait CIBLE 0x3f5) : armure traversée 2× aussi pour les spéciales (CBDWAM @18102d3f0
        # partagé quel que soit l'ability, #180). ⚠ `_reduce` (post_roll) ne connaît pas le flag crit du
        # coup, donc le hit_mult s'applique à TOUS les rolls sans exemption crit ici ; un porteur ability
        # cc>=1 + cible MkXGravis exigerait l'exemption (non exercé live). No-op (=1) hors cible hit-twice.
        _tgt_hit_mult = target_hit_multiplier(tsc.ctx.trait_objects()) if tsc is not None else 1

        def _reduce(value: int) -> int:
            # #75 (case-68 MAJ 13) : additif ForAddition ATTAQUANT = PRÉ-perçage en COMBAT (idem
            # attaque normale — même pipeline natif CalculateAbilityDamage/CBDWAM par coup).
            return apply_all_modifiers(
                apply_pierce_and_modifiers(value, profile_pierce, armor, mods,
                                           hit_mult=_tgt_hit_mult, attacker_additive_pre=True), def_mods)

        # ABILITY = roll-then-reduce : on tire dans les bornes BRUTES config (RandomAmount(min,max)) PUIS
        # on réduit (perçage/armure/mods) via `post_roll`. (≠ attaque normale reduce-then-roll.) Confirmé
        # bit-exact live (ThunderousAssault necroOverlord : roll-then-reduce = live 6948, à l'unité ;
        # re-confirmé probe_rngcrit_1202 : VigilanceEternal 3-hit, per-hit bit-exact 5 seeds x 2 cibles).
        # CONSOMMATION (cas fable rngcrit-1202) : ce vecteur = AttackDamageOperation.ExecuteHit @180e5eff0
        # avec un STRUCT NON dégénéré → 2 tirages/coup à cc=0 (valeur BRUTE + resolve slot-8 GASPILLÉ),
        # cf. `_one_hit`. ≠ attaque normale (struct dégénéré → 1 tirage/coup).
        hit_nc = HitDamage(base_min, base_max)                            # bornes BRUTES
        # CRIT ability : `CalculateCriticalDamage @18102da90` → `ApplyCritDamage @181000210` = critBonus
        # FLAT sur la valeur ROULÉE, PRE-reduce (appliqué dans `_one_hit` branche post_roll via le SHIFT
        # `hit_cr - hit_nc`). `hit_cr` sert aussi au flat #91 (`_capped_flat_cr`, centre bornes+cd) —
        # numériquement == l'ancien modèle bornes-décalées (largeurs égales → même modulo).
        # #45f : + bonus crit-sur-Ice (`IceEffect.CreateEffectDamageBonusForAttack @180f44940`) =
        # EffectBonus.addition per-coup-CRIT (PercentageOf(GetStat(10), IceCritDmgBonusPct=25) si cible
        # sur tuile Ice active et non-Immune) — MEME position pipeline (flat PRE-reduce). VALIDE live
        # bit-exact (probe_45f --case crit : GreatFrostAxe cc=100/cd=700 -> +175/coup crit, 4/4).
        _ice_add = ice_crit_damage_addition(state, attacker_id, target_id, ctx) if crit_enabled else 0
        hit_cr = HitDamage(base_min + crit_damage + _ice_add,
                           base_max + crit_damage + _ice_add) if crit_enabled else hit_nc
        # #202 WeaverOfFate : attaquant max-out (effet 1185) -> bornes BRUTES degenerees a (max, max),
        # mirror HitDamage(GetMax, null) d'`AbilityDamageBehaviour.GetDamage @180f8c560` (le tirage de
        # VALEUR est court-circuité par min==max — get_damage — mais le resolve slot-8 consomme TOUJOURS
        # 1 tirage/coup, désormais mirroré par `_one_hit` ; puis post_roll reduit le max, roll-then-reduce).
        hit_nc, hit_cr = AttackDamageOperation._apply_max_out(state, attacker_id, hit_nc, hit_cr)
        hits = max(1, int(hits))
        shc, shield_total = AttackDamageOperation._target_shield(tgt)      # bouclier shield-first
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources, shield=shield_total,
                                            post_roll=_reduce,
                                            capped_reductions=def_mods.capped_reductions,
                                            # #67 : etage limites — mode 2 = ability
                                            # (`CalculateAbilityDamage @18102cb50`)
                                            limits=AttackDamageOperation._target_limits(
                                                tgt, thc, damage_profile, is_special=2),
                                            limits_hp=int(thc.hp or 0),
                                            # famille de factory native (cf. _one_hit) : True =
                                            # AttackWithAttackDamage (resolve gaspille) ; False =
                                            # AttackWithAbilityDamage (AbilityDamageOperation, sans).
                                            wasted_resolve=wasted_resolve,
                                            # flag « always overkilled » (FlailSwing) : bypasse le cap
                                            # Resilient a chaque coup (no-op cible non-Resilient).
                                            force_overkill=force_overkill)
        AttackDamageOperation._deplete_shield(shc, r)
        AttackDamageOperation._apply_damage_pipeline(                   # chokepoint partage (#202)
            state, target_id, attacker_id, tgt, thc, r["total"], damage_profile,
            r["shield_dmg"], r["armor_dmg"])
        # POSE DE FEU (OnFireDamageAbility) — `EvaluateAfterHitTriggers @180e25fc0` tourne après CHAQUE coup
        # d'attaque, NORMALE **et** ability. Le port ne câblait ce vecteur que pour l'attaque normale
        # (DamageHandler) ; ici on porte la pose on-hit des tile-effects de profil pour les attaques
        # d'ABILITY à profil OnFire (ArmoriumCherub, splash FireOfAbsolution, BrazierOfHolyFire…). #136.
        # Idempotent (no-op si la tuile brûle déjà) → une pose post-attaque == per-coup pour le feu.
        from .triggers import _on_fire_damage_ability, after_hit_ability_attack  # lazy : cycle damage<->triggers
        fire = _on_fire_damage_ability(state, attacker_id, target_id, damage_profile)
        # VECTEUR AFTER-HIT (ability/splash) : dispatch générique — reset ActOfFaith au crit (#138) + tout
        # after-hit trigger (#140 : splash Psyker sur ability/splash psychique, chain borné par le cap).
        # `ranged` = POSITION-based (calculé dans after_hit_ability_attack, mirror IsRangedAttack).
        after_hit = after_hit_ability_attack(state, attacker_id, target_id, r["did_crit"],
                                             profile=damage_profile, ability_type=ability_type)
        return {"hits": hits, "total": r["total"], "base_min": base_min, "base_max": base_max,
                "pierce": profile_pierce, "armor": armor, "fire": fire, "after_hit": after_hit,
                "clean_min": hit_nc.min * hits, "clean_max": hit_nc.max * hits,
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"]}


    @staticmethod
    def execute_normal_like(state: State, attacker_id: int, target_id: int, base: int,
                            profile_pierce: int, hits: int = 1, spread_pct: int = 20,
                            damage_profile: Optional[str] = None,
                            is_melee: Optional[bool] = None,
                            ability_type: Optional[int] = None) -> Optional[dict]:
        """Attaque dont le node de dégât est un `StatAmount`/`PercentageOf(StatAmount(...))` (ex. splash
        Psyker = `PercentageOf(StatAmount(Attack), psykerExtraDmg%)`, profil Psychic). Pipeline
        **reduce-then-roll** (bornes pré-réduites puis tirage, post_roll=None), comme l'attaque normale
        (≠ ability RandomAmount), avec base + perçage de profil DONNÉS. Mute les PV de la cible.
        `spread_pct` = variance d'arme (DamageSpreadPercentage) : **0 pour un montant `StatAmount`**
        (mono-valeur, AUCUNE variance — confirmé live, splash Psyker = base exact) ; 20 seulement si le
        node porte de vraies bornes min/max d'arme. Renvoie le dict résultat (per_hit/total/...) ou None."""
        if state.rng is None:
            return None
        att = state.get_entity(attacker_id)
        tgt = state.get_entity(target_id)
        sc = att.get_component(StatsComponent) if att is not None else None
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        if sc is None or thc is None:
            return None
        ctx = sc.ctx
        ahc = att.get_component(HealthComponent)
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, target_id=target_id)
        # #45f : feuilles POSITIONNELLES du builder PARTAGE @181000590 (elevation/trench) — appliquees
        # a TOUT vecteur d'attaque par le natif (aucun gate normale/ability ; cf. execute_ability_attack,
        # meme fix, probe_45f_gfa_elevation). Le vecteur normal-like (splash Psyker / amount-mode) les
        # sautait aussi -> splash caste en surplomb ~33% bas.
        apply_elevation_bonus(state, mods, attacker_id, target_id)
        apply_trench_reduction(state, mods, attacker_id, target_id, damage_profile)
        tsc = tgt.get_component(StatsComponent)
        armor = defender_fixed_armor(state, target_id)   # FOYER partagé (base GetStat(16) + aura Protector allié)
        # #59 suite : threade is_melee + profil -> malus DÉFENSEUR gatés (cf. execute_ability_attack).
        # None (caller non mis à jour) = comportement historique — INERTE sans effet de défense gaté.
        def_mods, _da = defender_modifiers(state, target_id, thc.hp,
                                           is_melee=is_melee, damage_profile=damage_profile,
                                           attacker_id=attacker_id, is_normal_attack=False)  # #112 spéciale
        # BLOCK (cible) = base (GetStat 7/8) + sources d'effet (BeastSlayer...) via le helper PARTAGE
        # `_block_sources` (mirror du GetMultiValueStat(7)/CalculateBlockChances@181002350 unique du natif).
        block_sources = AttackDamageOperation._block_sources(tsc, _da, armor)
        crit_chance, crit_damage, crit_enabled = AttackDamageOperation._crit_params(ctx, active)
        # #120 : réduction PLATE défenseur (Nightshroud, ungated -> splash/normal-like aussi) fusionnée pré-perçage.
        AttackDamageOperation._apply_defender_flat_reductions(mods, def_mods)

        def _reduced(eff_base: int, flat_add: int = 0) -> "HitDamage":
            # #75 (case-68 MAJ 13) : additif ForAddition ATTAQUANT = PRÉ-perçage en COMBAT.
            # `flat_add` (#45f) = EffectBonus.addition PER-BRANCHE (Ice crit-only) : POST-spread
            # PRE-perçage, sans polluer `mods` (applique aux deux branches).
            mm = get_base_damage_fix64(eff_base, spread_pct=spread_pct)
            lo = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.min + flat_add, profile_pierce, armor, mods, attacker_additive_pre=True), def_mods)
            hi = apply_all_modifiers(apply_pierce_and_modifiers(
                mm.max + flat_add, profile_pierce, armor, mods, attacker_additive_pre=True), def_mods)
            return HitDamage(lo, hi)

        # #45f : bonus crit-sur-Ice per-coup-CRIT (cf. execute_ability_attack, meme mirror @180f44940).
        _ice_add = ice_crit_damage_addition(state, attacker_id, target_id, ctx) if crit_enabled else 0
        hit_nc = _reduced(base)
        hit_cr = _reduced(base + crit_damage, flat_add=_ice_add) if crit_enabled else hit_nc
        # #202 WeaverOfFate : attaquant max-out (effet 1185) -> bornes degenerees a (max, max) — le
        # splash Psyker / smite passe par `AbilityDamageBehaviour.GetDamage @180f8c560` (meme gate).
        hit_nc, hit_cr = AttackDamageOperation._apply_max_out(state, attacker_id, hit_nc, hit_cr)
        hits = max(1, int(hits))
        shc, shield_total = AttackDamageOperation._target_shield(tgt)      # bouclier shield-first
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources,
                                            shield=shield_total,   # post_roll=None (reduce-then-roll)
                                            capped_reductions=def_mods.capped_reductions,
                                            # #67 : etage limites — mode 2 = ability/splash
                                            # (`CalculateAbilityDamage @18102cb50`)
                                            limits=AttackDamageOperation._target_limits(
                                                tgt, thc, damage_profile, is_special=2),
                                            limits_hp=int(thc.hp or 0))
        AttackDamageOperation._deplete_shield(shc, r)
        AttackDamageOperation._apply_damage_pipeline(                   # chokepoint partage (#202)
            state, target_id, attacker_id, tgt, thc, r["total"], damage_profile,
            r["shield_dmg"], r["armor_dmg"])
        # VECTEUR AFTER-HIT (splash StatAmount) : idem execute_ability_attack — reset ActOfFaith au crit
        # (#138) + vecteur complet (#140). `ranged` = POSITION-based (mirror IsRangedAttack), calculé dedans.
        # `ability_type` = kind AbilityOrEffect du coup (smite Psyker 0x3f5 -> branche 2 AddIce #35).
        from .triggers import after_hit_ability_attack
        after_hit = after_hit_ability_attack(state, attacker_id, target_id, r["did_crit"],
                                             profile=damage_profile, ability_type=ability_type)
        return {"hits": hits, "total": r["total"], "base": base, "pierce": profile_pierce,
                "armor": armor, "after_hit": after_hit,
                "clean_min": hit_nc.min * hits, "clean_max": hit_nc.max * hits,
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"]}

    @staticmethod
    def execute_direct(state: State, source_id: int, target_id: int, base: int,
                       profile_pierce: int,
                       damage_profile: Optional[str] = None) -> Optional[dict]:
        """Dégât DIRECT d'un nœud `Direct(...)` (mirror `DSLFactory.AttackWithAbilityDamage @180de9c90`
        + `AttackDamageBehaviour` sur nœud `Direct` — factory DISTINCTE de `AttackWithAttackDamage`
        @180de9fb0). La `base` (déjà calculée par le dégât-node, ex. `PercentageOf(StatAmount(Health,
        Max), fireDmgPct)` du DoT feu) est routée par le SEUL perçage/armure (`apply_pierce_and_modifiers`,
        mods=None) — AUCUN crit / block / bouclier / spread / tirage RNG / after-hit (≠ l'attaque
        d'ability `execute_ability_attack`/`execute_normal_like`). Utilisé par le DoT de tuile `EnvFireTile`
        (`EnvFireTileAbility.CreateBehaviour @18121e040`) : occupant non-immune → `PercentageOf(20%, PV max)`
        percée par le PiercingRatio du profil (Flame=25), l'armure absorbant le non-percé. Mute les PV de la
        cible + route la mort (`_fire_death_if_killed`, source = la tuile). `<= 0 dmg` → no-op (return None).
        `source_id` = l'entité-source (tuile) pour l'attribution de mort ; `profile_pierce` = perçage effectif
        (le caller passe `profile_pierce(None, profile)` = PiercingRatio brut — la tuile n'a pas de stats
        ExtraPierce)."""
        tgt = state.get_entity(target_id)
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        if thc is None or thc.hp is None:
            return None
        armor = defender_fixed_armor(state, target_id)   # FOYER partagé (DoT tuile réduit par l'armure défenseur)
        dmg = int(round(apply_pierce_and_modifiers(int(base), pierce_pct=int(profile_pierce),
                                                   armor=armor, mods=None)))
        if dmg <= 0:
            return None
        # #30 (#60bis) MEMBER-CAP du degat DIRECT — mirror `ApplyTraitDamageLimitsToDirectDamage
        # @18102c9b0` (= `ApplyGroupUnitDamageLimit @18102bfe0` avec profile=NULL : PAS de bypass
        # Blast possible), meme wrapper que le chemin `CalculateDirectDamage @18102f130` de
        # `DirectDamageOperation.Execute @180e677f0`. Un degat direct ne tue AU PLUS qu'UN membre :
        # cap = hp - maxHealthWith(remaining-1), applique au montant NET (post percage/armure —
        # l'etage limites de `CalculateDamageOperation @18102dc30` opere apres la FixedArmor plate).
        # PROUVE LIVE (probe_60bis seeds 60112/60113) : scarab PLEIN (2218, 5 membres) sur tuile en
        # feu -> tick natif 443 = cap exact (vs 444 non-cape, modele verifie par ailleurs a 444 nu
        # rem=1 et 111 sous aura +886). Doc : case-60 par. 5 (resolu).
        tuc = tgt.get_component(UnitComponent)
        if tuc is not None and thc.hp_max:
            import gameconfig as GC
            n = int((GC.unit(tuc.visual_id) or {}).get("nrOfMembers") or 1)
            if n > 1:
                from ...services.trait_damage_limits import apply_group_unit_damage_limit
                dmg = apply_group_unit_damage_limit(dmg, False, n, int(thc.hp_max), int(thc.hp))
        hp_before = thc.hp
        # Chokepoint partage (#202), `is_attack=False` : PAS de `_record_attacked` (un DoT n'est PAS une
        # attaque — compteur HasBeenAttackedAmountThisTurn) ; la cle profil "recu ce tour" est posee
        # (le natif route tout HP-loss par ApplyDamage -> RegisterDamage) ; `damage_profile` None
        # (caller non threade) = pas de cle. NB : execute_direct ne consulte PAS IsAttackMaxOutDamage
        # (aucun call site natif sur la voie DirectDamage).
        AttackDamageOperation._apply_damage_pipeline(
            state, target_id, source_id, tgt, thc, dmg, damage_profile, is_attack=False)
        return {"total": dmg, "base": int(base), "pierce": int(profile_pierce), "armor": armor,
                "hp_before": hp_before, "hp_after": thc.hp}


class DamageHandler:
    """Visiteur des messages d'attaque (mirror du handler natif lançant AttackDamageOperation).
    `spread_pct` = `BattleConfiguration.Damage.DamageSpreadPercentage` (défaut 20)."""
    __slots__ = ("state", "spread_pct", "last", "after_hit")

    def __init__(self, state: State, spread_pct: int = 20):
        self.state = state
        self.spread_pct = spread_pct
        self.last: Optional[dict] = None       # résultat du dernier coup (diagnostic/test)
        self.after_hit: list = []              # extra-attaques after-hit (traits) du dernier coup

    def visit_AttackUnitMessage(self, msg) -> None:
        # --- #61bis tranche 3 : dispatch NormalAttackType CONCRET. L'attaque normale native est une
        # ActiveAbility PER-UNIT (`ActiveAbilityComponent.NormalAttackType@0x28`) ; pour un porteur du
        # passif MV71SniperDroneSquad (Sho'syl/tauMarksman), c'est `MV71SniperDroneSquadAttackAbility`
        # (1076) : à DISTANCE elle invoque un DRONE (spawn + attaque commandée + Markerlight), en MÊLÉE
        # elle délègue au pipeline normal. Les tours simulés (AttackUnitMessage) routent donc comme le
        # cast live 1076. `self.last` = l'attaque du VECTEUR (mêlée : celle du caster ; distance :
        # l'attaque commandée du drone) — même shape que le chemin générique.
        _ae = self.state.get_entity(msg.attacker_id)
        _uc = _ae.get_component(UnitComponent) if _ae is not None else None
        if _uc is not None:
            from ..abilities.loki.mv71 import (is_mv71_normal_attacker,
                                               MV71SniperDroneSquadAttackAbility)
            if is_mv71_normal_attacker(_uc.visual_id):
                res = MV71SniperDroneSquadAttackAbility().execute_behaviour(
                    self.state, msg.attacker_id, msg.target_id) or {}
                self.last = res.get("attack")
                self.after_hit = res.get("after_hit") or []
                # flags du CASTER (#139) — même queue que le chemin générique ci-dessous (les flags
                # du DRONE sont posés par execute_behaviour lui-même).
                from .turnflow import add_flags_after_ability_execution
                _fl = add_flags_after_ability_execution(
                    self.state, int(msg.attacker_id), skip_ability_used=False, skip_end_turn=False)
                if isinstance(self.last, dict):
                    self.last["flags"] = _fl
                return
        self.last = AttackDamageOperation.execute(
            self.state, msg.attacker_id, msg.target_id, self.spread_pct)
        # VECTEUR AFTER-HIT : dispatcher GÉNÉRIQUE de triggers (mirror `EvaluateAfterHitTriggers` →
        # `EvaluateTriggerOperation`). Itère le registre des triggers (traits/effets) ; chaque entrée
        # scope elle-même via sa condition (ex. Psyker OwnerIsActor). No-op si aucun trigger ne matche.
        if self.last is not None:
            from .triggers import after_hit_normal_attack
            # #202-C : set des profils de l'attaque = arme + bonus-hits #179 (lu par le gate
            # CurrentAttackDamageProfilesContain du trigger 1173).
            _profs = {self.last.get("profile")} - {None}
            _profs |= set((self.last.get("additional_hits") or {}).get("profiles") or [])
            self.after_hit = after_hit_normal_attack(
                self.state, msg.attacker_id, msg.target_id,
                bool(self.last.get("ranged")), self.last.get("profile"),
                is_crit=bool(self.last.get("did_crit")), profiles=_profs)
        # #139 : l'attaque normale native EST une ActiveAbility (NormalAttack per-unite ; AttackUnitMessage
        # n'existe pas en natif — c'est la simplification port de l'ActiveAbilityMessage) et traverse la
        # MEME queue `AddFlagsAfterAbilityExecution` @180e447f0 — base `SetsEndTurnFlags`/
        # `SetsActiveAbilityUsedFlag` = `_dsl.True` @180fb3150 (aucune classe NormalAttack dans la famille
        # d'overrides) -> flag ActiveAbilityUsed(2) + FinishUnitTurn (flags 1+3). Bookkeeping observable ;
        # aucun gate du port ne le lit encore (PickNextUnit/VerifyUnitsTurnFinished = couche non portee).
        if self.last is not None:
            from .turnflow import add_flags_after_ability_execution
            self.last["flags"] = add_flags_after_ability_execution(
                self.state, int(msg.attacker_id), skip_ability_used=False, skip_end_turn=False)
