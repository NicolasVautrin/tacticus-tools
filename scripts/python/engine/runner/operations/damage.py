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

from ...services.damage_combat import could_crit, BlockSource
from ...entities.damage_trait import DamageTrait
from ...entities.damage_profile_type import DamageProfileType
from ...entities.stats import StatType
from ..prng import IntBasedMersenneTwister
from ..state import State
from ..components import UnitComponent, ShieldComponent, unit_is_dead
from ...entities.effects import (crit_chance_bonus_from_effects, crit_damage_bonus_from_effects,
                                 defender_effect_block_sources)
from .damage_hits import HitDamage, _DamageHitsMixin
from .damage_ops import _DamageOpsMixin


class AttackDamageOperation(_DamageOpsMixin, _DamageHitsMixin):
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
        """Si le coup a fait passer la cible de >0 à 0 PV → elle meurt : marque `alive=False` et lance la
        SÉQUENCE d'événements de mort. `damage` = dégât LÉTAL total du coup (pour le flag OVERKILL =
        `dmg >= 2*PV`). No-op si pas de mort.

        ORDRE DES ÉVÉNEMENTS — RE TRANCHÉE au décompilé (2026-07-25). L'émetteur réel est
        **`KillUnitOperation$$Execute` @180e76470** (et NON `ApplyDamageOperation$$Execute` @180e5a540, qui
        n'émet que 0x3a/0xf/0x10, ni les lambdas de `InputMessageProcessor$$VerifyDeaths` @180ebb0a0, qui ne
        font qu'appeler `OperationProcessor$$KillUnit` @180e0a9f0). Ordre des INSTRUCTIONS dans
        `KillUnitOperation$$Execute` (adresses de retour des call-sites de dispatch) :

            On(1  = PreUnitDeath)    ret 0x180e76c4c   <- AVANT la garde `if (*pcVar21 == '\\0')` @0x180e76c9e
            On(2  = PreUnitDeath_2)  ret 0x180e76dea   <- sous la garde
            On(0  = UnitDeath)       ret 0x180e77269   (aucun consommateur porté)
            On(55 = UnitDefeated)    ret 0x180e7731c
            On(54 = PostUnitKill)    ret 0x180e7749c   (aucun consommateur porté)

        => **1 -> 2 -> 55** est CONFIRMÉ (auparavant une simple inférence par numérotation). Les 3 vecteurs
        portés sont donc émis dans cet ordre ci-dessous.

        - `On(1)` : accumulations ActOfFaith (allié Imperial qui meurt/tue), FinalJustice (riposte du
          mourant, gate overkill dans son BEHAVIOUR), TaintedNarthecium (revive).
        - `On(2)` : famille DEATH-NOVA (`Explodes` 1008->1021, `PutridExplosion` 2028->1074) — `OnPreDeath2`
          @180df7ee0. Les deux passent `a=1` => **AUCUN gate overkill** : la nova part même en overkill.
        - `On(55)` : Ambush_SummonAbility (mort -> decoy) + `turn_defeated`.

        RÉSIDU DOCUMENTÉ (hors périmètre, cf. le retrofit REVIVE) : natif, `On(1)` est émis AVANT la garde
        @0x180e76c9e alors que 2/0/55/54 sont dedans — un `KillUnit` qui ne franchit pas cette garde
        n'émettrait que `On(1)`. La sémantique exacte de cette garde (dictionnaire `entities+0xa8` indexé
        par une clé du singleton de bataille) n'a PAS été résolue ; en particulier, savoir si un REVIVE
        déclenché sur `On(1)` court-circuite `On(2)`/`On(55)` reste OUVERT. Le port émet les trois
        inconditionnellement — c'est le comportement DÉJÀ en place pour `On(55)`, inchangé ici."""
        if hp_before is None or hp_before <= 0 or hp_after != 0:
            return None
        uc = tgt.get_component(UnitComponent) if tgt is not None else None
        if uc is not None:
            uc.alive = False
        from .triggers import (after_death_triggers, is_overkill, unit_defeated_triggers,
                               pre_unit_death_2_triggers)
        overkill = is_overkill(hp_before, damage)
        out = after_death_triggers(state, target_id, attacker_id, overkill=overkill)
        # `On(PreUnitDeath_2 = 2)` — émis par `KillUnitOperation$$Execute` APRÈS `On(1)` et AVANT `On(55)`
        # (ordre d'instruction lu au décompilé, cf. docstring). Vecteur des death-novas Explodes/Putrid.
        out = (out or []) + pre_unit_death_2_triggers(state, target_id, attacker_id, overkill=overkill)
        # #G3 : `On(UnitDefeated=55)` (event DISTINCT de 1 et 2) -> Ambush_SummonAbility (mort -> decoy +
        # record turn_defeated). L'unité est déjà alive=False (fire-on-death).
        return out + unit_defeated_triggers(state, target_id, attacker_id)

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
    def _block_sources(tsc, tgt_active_effects, defender_armor: int, damage_profile=None):
        """Sources de block du DEFENSEUR pour `apply_random_block_damage` : block de BASE (scalaire
        `GetStat(7/8)` -> ctx.block_chance/block_damage) PUIS les sources SUPPLEMENTAIRES posees par ses
        effets (`AddExtraBlockEffectToOwner`, ex. BeastSlayer @180e18b70 : chance beastSlayerBlockChance /
        amount = blockDmgPct% du FixedArmor courant) — ABSENTES du scalaire (verifie live orksNob
        blockChance=0), que le natif tient dans `GetMultiValueStat(7)` (`CalculateBlockChances @181002350`).
        ORDRE : base d'abord, effets ensuite (cible sans block de base -> effet = seule source, ordre moot).
        None si aucune source (retro-compat : 0 tirage). Consomme par les 3 vecteurs (normale/ability/splash). #72.

        #65 : GATE `NoBlocking` (DamageTrait 0) du PROFIL de degat — un profil NoBlocking (ex. `Psychic`,
        Traits=['NoBlocking'], PiercingRatio 100 ; cf. wiki « Cannot be blocked ») BYPASSE le block. Mirror
        de `AttackDamageOperation.ExecuteHit @180e5eff0` : `DamageProfile.HasTrait(0=NoBlocking)` pose le flag
        (metadata +0x2a) qui SKIP toute la branche block/evade de `CalculateDamageOperation @18102dc30`
        (`if ((metadata>>0x30)==0) { ...block/evade... }`). AUCUN tirage block consomme => 0 tirage RNG (le
        natif ne roule pas le block). Sans ce gate, l'offline sur-roulait un block spurious sur les attaques
        Psychic (seed 123 u95 astraPrimarisPsy -> u79 genesKelermorph BeastSlayer : off 1569 vs live 2873).
        Cable dans les 3 vecteurs (execute/execute_ability_attack/execute_normal_like) via `damage_profile`."""
        if damage_profile is not None:
            import gameconfig as GC
            _dp_traits = (GC.damage_profile(damage_profile) or {}).get("Traits") or []
            if DamageTrait.NoBlocking.name in _dp_traits:
                return None            # profil NoBlocking -> block bypasse (0 tirage), mirror ExecuteHit
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
        # --- #70 GATE ACTEUR-MORT (mirror `ActiveAbilityOperation.ExecuteInternal @180e44ec0` :
        # `if (EntityExtensions.IsUnit(caster) && UnitExtensions.IsDead(caster)) return 0;`). L'attaque
        # normale native EST une ActiveAbility per-unite (#139) -> passe par le MEME gate. Un attaquant MORT
        # (hp<1, non-Fled ; `UnitExtensions.IsDead @180ed8050`) => NO-OP complet (0 tirage RNG, 0 degat,
        # aucun after-hit, aucun flag), AVANT toute selection d'arme / boucle de coups. Le port `execute`
        # mirror `AttackDamageOperation.Execute @180e60c70` qui n'a AUCUN gate liveness natif -> le gate vit
        # au niveau OPERATION ici (upstream de la boucle RNG). Inerte pour tout attaquant vivant (replay/AI :
        # les tours sont pris sur des unites vivantes) -> zero regression. Repro : seed 123, u95 (mort en
        # attaquant u79) -> u81/u83 : live 0 tirage/0 degat, offline sur-executait 2924. cf. case-70.
        _att = self.state.get_entity(msg.attacker_id)
        if unit_is_dead(_att):
            self.last = None
            self.after_hit = []
            return
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
