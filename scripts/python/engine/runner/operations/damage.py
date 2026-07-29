"""Operations de dégât — `IdunBattle.Operations.AttackDamageOperation` (gqfc5mff6c).

Tranche DAMAGE. **Palier 1 (porté + validé ici) : le TIRAGE de dégât par coup**
(`HitDamage.GetDamage`), bit-exact via le MT porté (`engine/runner/prng.py`).

Chaîne native RE'd (VA citées) :

    IdunBattle.Operations.AttackDamageOperation$$Execute
      → IdunBattle.Operations.AttackDamageOperation$$GetAttackHits   (nb de coups ; 1 par défaut)
      → ExecuteHits (boucle nbHits)      IdunBattle.Operations.AttackDamageOperation$$ExecuteHits
          → ExecuteHit (PAR COUP)        IdunBattle.Operations.AttackDamageOperation$$ExecuteHit   — per-coup PARTAGÉ : attaque NORMALE **et**
            attaques d'ABILITY `AttackWithAttackDamage` (IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget → stream slot 0x3c → même opération). Corrigé cas fable rngcrit-1202 :
              1. IdunBattle.Core.HitDamage$$GetDamage   sur le STRUCT d'entrée — tirage SSI min!=max :
                 NORMALE = struct DÉGÉNÉRÉ → 0 tirage ; ABILITY bounds = [minDmg,maxDmg] config
                 → 1 tirage = LA VALEUR BRUTE (roll-then-reduce).
              2. RollCritical (IDamagePrediction slot 0xa → IdunBattle.Core.Services.DamagePrediction$$RollCritical : gate `cc<1 → false SANS tirage` → IdunBattle.Core.Services.DamageCalculations$$RollCritical = NextBool brut, atteint seulement à travers le gate)  ← SI cc≥1
              3. slot 4 IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation : shield-part/armure/caps → cellules
                 min/max (0 RNG) — NORMALE : bornes RÉDUITES ; ABILITY : cellules DÉGÉNÉRÉES.
              4. slot 8 IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage : Next(min,max+1) — TOUJOURS
                 1 tirage (AUCUN gate min==max) : NORMALE = LA VALEUR (plage réduite) ;
                 ABILITY = tirage GASPILLÉ (largeur 1).
              5. sub-op 0x42 : block rolls + split bouclier/armure-pool (calculate_damage_operation)
              6. IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers (cascade)

**Ordre RNG CONFIRMÉ (genrand brut live, necroDestroyer CC=100 ; re-mesuré probe_rngcrit_1202
2026-07-23, custoKyrus 3-hit cc=0, 5 seeds x 2 cibles)** : attaque NORMALE par coup =
RollCritical si cc≥1 (tirage PAIR) PUIS valeur (resolve slot 8, tirage IMPAIR). À cc=0,
RollCritical ne tire RIEN (gate `cc<1` de IdunBattle.Core.Services.DamagePrediction$$RollCritical) → 1 tirage/coup (validé 18/18 + probe A).
Attaque d'ABILITY bounds-mode par coup à cc=0 : **2 tirages** = valeur BRUTE (GetDamage-top)
puis resolve GASPILLÉ — cf. `_one_hit`. La désync #220/#205 (« 6 rng pour 3 coups ») était ce
resolve dégénéré, PAS un crit-roll : aucun chemin natif ne consomme un tirage crit à cc=0.

**CRIT (combat ≠ prédiction)** : le crit du COMBAT s'ajoute à la BASE D'ATTAQUE AVANT
spread/perçage (`GetBaseDamageFix64` param_4=isCrit ⇒ `eff_attack=attack+critDamage`,
même pipeline) — PAS l'`ApplyCritDamage` post-réduction (base+bonus) de la PRÉDICTION.
Confirmé bit-exact : crit per-coup [675,1012] = non-crit [435,652]×(906+500)/906, et
next_internal(675,1013) aux tirages impairs = live [932,882,967,867,961,955] à l'unité.

**#73 (RE close, 2026-07-09) : le crit N'A PAS de gating inter-coups** (contrairement au block #72).
`IdunBattle.Core.Services.DamagePrediction$$RollCritical`→`IdunBattle.Core.Services.DamageCalculations$$RollCritical` = NextBool(GetStat(9)+bonus) SANS ETAT ; pas d'"AddFailedCrit"
dans `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (le block, lui, a `AddFailedBlockIds`). Chaque coup tire le crit INDÉPENDAMMENT
avec la même chance ⇒ `_run_hits` (crit par-coup, aucun accumulateur) est déjà fidèle. Le block gate PARCE
QUE multi-source (id par source) ; le crit est chance unique ⇒ rien à exclure. (Détail : docs/rl/case-68.)

    #74 (RE close, 2026-07-09) : la crit-chance est RELUE PAR COUP par le natif, MAIS constante sur les coups
    d'une attaque -> le calcul UNE FOIS du port (`_crit_params`) est fidele. `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` dispatche
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
from ..components import (UnitComponent, ShieldComponent, UnitFlagsComponent, HealthComponent,
                          StatsComponent, unit_is_dead, can_be_overkilled, unit_prevents_overkill)
from ...services.trait_damage_limits import unit_is_overkill
from ...entities.effects import (crit_chance_bonus_from_effects, crit_damage_bonus_from_effects,
                                 defender_effect_block_sources)
from .damage_hits import HitDamage, _DamageHitsMixin
from .damage_ops import _DamageOpsMixin


def _revert_ability_modifications_of_dead(state: State, dead_id: int) -> list:
    """Volet `RemoveEffects` de `IdunBattle.Operations.KillUnitOperation$$Execute` limite aux
    MODIFICATIONS D'ABILITY : chaque effet ACTIF porte par l'unite qui vient de mourir voit ses
    `AddUnitActiveAbilityModification` annules (mirror `<Effect>.RevertInternal`). L'effet est aussi
    marque `consumed` (il ne survit pas a son porteur).

    Seul porteur du build : `ListenUpMaggotsEffect` (0x426) sur `astraSmnKell` — a la mort de Kell,
    Creed reperd son `+1 nrOfSummons` et son `range 3`. Les effets sans `ability_modifications` ne
    sont PAS touches (perimetre etroit, cf. le commentaire du call-site)."""
    from .ability_modifications import revert_ability_modifications
    if getattr(state, "effects", None) is None:
        return []
    out = []
    for eff in list(state.effects.by_unit.get(int(dead_id), [])):
        if eff.consumed or not (getattr(eff, "applied_ability_modifications", None) or []):
            continue
        out.extend(revert_ability_modifications(state, eff))
        eff.consumed = True
    return out


class AttackDamageOperation(_DamageOpsMixin, _DamageHitsMixin):
    """`IdunBattle.Operations.AttackDamageOperation` IdunBattle.Operations.AttackDamageOperation$$Execute (squelette fidèle).

    Palier 1 : seul le TIRAGE par coup (`execute_hit`) est porté+validé. Les paliers
    suivants (crit, block, réduction, triggers after-hit) sont marqués TODO avec leur
    VA, en miroir 1:1 de la structure native (cf. en-tête de module)."""
    __slots__ = ()

    @staticmethod
    def get_attack_hits(default_hits: int = 1) -> int:
        """`IdunBattle.Operations.AttackDamageOperation$$GetAttackHits — nb de coups. Mono-coup → 1 (sans requête, donc
        sans RNG avant le 1er coup). Le cas multi-coups (requête composant 0xb5) =
        palier ultérieur."""
        return default_hits

    @staticmethod
    def execute_hit(hit: HitDamage, rng: IntBasedMersenneTwister,
                    use_midpoint: bool = False) -> int:
        """`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit — PALIER 1 : renvoie le dégât de BASE tiré du coup
        (`HitDamage.GetDamage`). Crit (composant 0xb), block (composant 10), réduction
        perçage/armure et EvaluateAfterHitTriggers = paliers 2-4 (non portés ici)."""
        return hit.get_damage(rng, use_midpoint)

    @staticmethod
    def _damage_source_ability(current_ability, triggering_ability):
        """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules$$GetDamageSourceAbility
        (currentAbility, triggeringAbility)` (MIRROR du decompile) :

            if (currentAbility.<Nullable<ActiveAbilityType>>.HasValue
                && ActiveAbility.IsRegularAttack(currentAbility.Value)
                && triggeringAbility.HasValue)   return triggeringAbility.Value
            return currentAbility

        = « une ATTAQUE REGULIERE declenchee par autre chose s'attribue a son DECLENCHEUR ». Appelee
        PAR COUP par `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` et
        `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` pour renseigner l'`AbilityOrEffect`
        de la `DamageSource` du coup -- c'est LUI que `HasDeathReasonTrigger` compare.

        Consequence load-bearing : un tir d'OVERWATCH (`Overwatch_AutoAttackEffect$$GetAttackBehaviour`
        = `UseActiveAbility(NormalAttack)`, donc une attaque REGULIERE, declenchee par l'effet
        `Overwatch_AutoAttack` 1009) s'enregistre comme venant de **1009**, pas de l'attaque normale.

        Le test natif est `IsRegularAttack` sur l'`ActiveAbilityType` CONCRET de l'attaque normale
        (per-unite : 69, 1030, ...). Le port ne materialise PAS cet id sur la voie normale : il y
        thread le marqueur de KIND `0x3f5` (cf. `abilities/attack_type.py`, 2e branche de
        `DSLFactory$$IsNormalAttack`). On teste donc la DISJONCTION `is_normal_attack` = « id concret
        d'attaque reguliere OU marqueur de kind » -- meme extension sur les deux voies du port."""
        from ..abilities.attack_type import is_normal_attack   # lazy : cycle damage<->abilities
        if current_ability is not None and is_normal_attack(current_ability) \
                and triggering_ability is not None:
            return int(triggering_ability)
        return None if current_ability is None else int(current_ability)

    @staticmethod
    def _record_death_reason(state: State, dying_id: int, killer_id: Optional[int],
                             source_ability) -> None:
        """`IdunBattle.Operations.KillUnitOperation$$RecordDeathReason(killer, killed,
        killedUnitComponent, deathReason)` : ecrit le `Nullable<DamageSource>` @`UnitComponent+0x108`
        de la victime. Appelee par `KillUnitOperation$$Execute` **AVANT** l'emission d'`On(PreUnitDeath
        = 1)` (ordre lu au decompile) -- c'est ce qui rend le champ lisible par les
        `HasDeathReasonTrigger` de ce vecteur.

        COLLAPSE ASSUME : le natif tient DEUX morceaux (le `RecordDeathReason` ci-dessus pose
        killer + `DamageReason` ; l'`AbilityOrEffect` vient de la `DamageSource` du coup letal,
        construite par `A*DamageOperation$$ExecuteHit` via `GetDamageSourceAbility` et transportee
        dans le `DamageAppliedResult`). Le port n'a pas ce transport : il FUSIONNE les deux au moment
        du kill, avec l'`AbilityOrEffect` deja resolue par `_damage_source_ability`. `DamageReason` =
        `Ability` (0) -- les deux autres valeurs de l'enum (`Knockback` 1 / `Steppable` 2) sont les
        morts NON-DEGAT, qui ne passent pas par ce pipeline (le crush d'un steppable est traite par
        `movement.py::_kill_steppable_units`, hors `_fire_death_if_killed`)."""
        uc = tgt_uc = None
        e = state.get_entity(int(dying_id))
        if e is not None:
            tgt_uc = e.get_component(UnitComponent)
        uc = tgt_uc
        if uc is None:
            return
        uc.death_source = (None if killer_id is None else int(killer_id), 0,
                           None if source_ability is None else int(source_ability))

    @staticmethod
    def _did_overkill(state: State, target_id: int, tgt, hp_before, damage,
                      hits_result=None, is_force_overkill: bool = False) -> bool:
        """`didOverkill` du chemin COMBAT — RE-JOUE la sequence des coups, parce que le natif appelle
        `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` (surcharge d'INSTANCE, inlinee dans
        `...$$CalculateDamageOperation`) **UNE FOIS PAR COUP**, et que
        `IdunBattle.Operations.ApplyDamageOperation$$Execute+0x17d5` pose `UnitFlag.Overkilled (8)` des
        qu'UN coup rend vrai. Deux des trois arguments qui decident VARIENT d'un coup a l'autre :

            IsOverkill(target, hitDamage       = degat SANTE de CE coup,
                               deniedDamage    = degat REFUSE par l'etage limites aux coups PRECEDENTS,
                               isCritical      = crit de CE coup,
                               isForceOverkill = flag d'attaque (constant sur l'attaque),
                               targetHealthBeforeAttack = PV au debut de l'attaque,
                               minimumHealth   = plancher Hypersensory de la cible)

        et la surcharge d'instance re-agrege elle-meme le degat des coups precedents
        (`hitDamage += targetHealthBeforeAttack.Value - currentHealth`) : l'argument compare est donc le
        CUMUL. On boucle ici sur `(degat sante du coup, denied AVANT le coup, crit du coup)`.

        `hits_result` = le dict rendu par `_run_hits` (`per_hit_health` / `crits` / `denied_before`).
        Absent (DoT, knockback, coups additionnels) -> degenerescence en UN coup non-critique sans
        denied : strictement l'ancien comportement."""
        cbo = can_be_overkilled(tgt)
        if not cbo or hp_before is None or damage is None:
            return False
        prv = unit_prevents_overkill(state, target_id)
        thc = tgt.get_component(HealthComponent) if tgt is not None else None
        floor = getattr(thc, "minimal_health", None) if thc is not None else None
        seq = None
        if hits_result:
            hh = hits_result.get("per_hit_health") or []
            cr = hits_result.get("crits") or []
            db = hits_result.get("denied_before") or []
            if hh:
                seq = [(int(hh[i]),
                        int(db[i]) if i < len(db) else 0,
                        bool(cr[i]) if i < len(cr) else False) for i in range(len(hh))]
        if not seq:
            seq = [(int(damage), 0, False)]
        cum = 0
        for health_dmg, denied_before, crit in seq:
            cum += health_dmg
            if unit_is_overkill(hp_before, cum, can_be_overkilled=cbo,
                                denied_damage=denied_before, prevent_overkill=prv,
                                is_critical=crit, is_force_overkill=is_force_overkill,
                                target_minimum_health=floor):
                return True
        return False

    @staticmethod
    def _fire_death_if_killed(state: State, target_id: int, attacker_id: int,
                             hp_before, hp_after, tgt, damage=None,
                             source_ability=None, hits_result=None,
                             is_force_overkill: bool = False) -> Optional[list]:
        """Si le coup a fait passer la cible de >0 à 0 PV → elle meurt : marque `alive=False`,
        ENREGISTRE le kill puis ENQUEUE la mort, et draine la file. `damage` = dégât LÉTAL total du
        coup (pour le flag OVERKILL = `dmg >= 2*PV`). No-op si pas de mort.

        **DEUX OPERATIONS NATIVES, PAS UNE (case-haze-ord)** — le corps ci-dessous est
        `IdunBattle.Operations.RecordKillOperation$$Execute` (flag `Overkilled`, `RecordDeathReason`,
        `On(PendingDeathAdded = 3)`, `IdunBattle.Core.MatchState$$AddDeath`) ; l'APPLICATION de la mort
        vit dans `_kill_unit_operation` (`IdunBattle.Operations.KillUnitOperation$$Execute`) et n'est
        atteinte que par le DRAIN `_verify_deaths`
        (`IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`). Le drain est NON REENTRANT : une
        mort causee PENDANT une sequence de mort (death-nova, riposte `FinalJustice`, report
        `HazeOfCorruption`) est traitee APRES elle, jamais en son milieu. Au premier appel de la pile,
        enqueue et drain restent consecutifs -> comportement inchange pour tout appelant top-level.

        ORDRE DES ÉVÉNEMENTS — RE TRANCHÉE au décompilé (2026-07-25). L'émetteur réel est
        **`KillUnitOperation$$IdunBattle.Operations.KillUnitOperation$$Execute** (et NON `ApplyDamageOperation$$IdunBattle.Operations.ApplyDamageOperation$$Execute, qui
        n'émet que 0x3a/0xf/0x10, ni les lambdas de `InputMessageProcessor$$IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths, qui ne
        font qu'appeler `OperationProcessor$$Core.Services.OperationProcessor$$KillUnit). Ordre des INSTRUCTIONS dans
        `KillUnitOperation$$Execute` (adresses de retour des call-sites de dispatch) :

            On(1  = PreUnitDeath)    ret IdunBattle.Operations.KillUnitOperation$$Execute+0x7dc   <- AVANT la garde `if (*pcVar21 == '\\0')` @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e
            On(2  = PreUnitDeath_2)  ret IdunBattle.Operations.KillUnitOperation$$Execute+0x97a   <- sous la garde
            On(0  = UnitDeath)       ret IdunBattle.Operations.KillUnitOperation$$Execute+0xdf9   (aucun consommateur porté)
            On(55 = UnitDefeated)    ret IdunBattle.Operations.KillUnitOperation$$Execute+0xeac
            On(54 = PostUnitKill)    ret IdunBattle.Operations.KillUnitOperation$$Execute+0x102c   (aucun consommateur porté)

        => **1 -> 2 -> 55** est CONFIRMÉ (auparavant une simple inférence par numérotation). Les 3 vecteurs
        portés sont donc émis dans cet ordre ci-dessous.

        - `On(PreUnitDeath)` : accumulations ActOfFaith (allié Imperial qui meurt/tue), FinalJustice (riposte du
          mourant, gate overkill dans son BEHAVIOUR), TaintedNarthecium (revive).
        - `On(PreUnitDeath_2)` : famille DEATH-NOVA (`Explodes` 1008->1021, `PutridExplosion` 2028->1074) — `IdunBattleLogic.Entities.DSLFactory$$OnPreDeath2. Les deux passent `a=1` => **AUCUN gate overkill** : la nova part même en overkill.
        - `On(UnitDeath)` : TerrifyingCrescendo branche OVERKILL (`On(UnitDeath) & OwnerIsActor & TargetIsOverkilled`).
        - `On(UnitDefeated)` : Ambush_SummonAbility (mort -> decoy) + `turn_defeated`.

        **SÉMANTIQUE DE LA GARDE @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e — TRANCHÉE (case-89 volet C, 2026-07-25).** Elle lit le
        `hasValue` du `Nullable<ReviveData>` @`UnitComponent + 0xa8` (même champ, même helper
        `thunk_FUN_1801f3000(ptr, <fieldInfo hasValue>)`, que `IdunBattle.Operations.ReviveUnitOperation$$Execute`
        qui le DRAINE puis le remet à 0, et que `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute` qui l'ÉCRIT) :

            if (!unitComponent.PendingRevive.HasValue) { ...tout le reste de la mort... }

        ⇒ **un REVIVE posé pendant `On(PreUnitDeath)` COURT-CIRCUITE `On(PreUnitDeath_2)`, `On(UnitDeath)`, `On(UnitDefeated)`, `On(PostUnitKill)`**, ainsi
        que `RegisterDefeatedUnit`, `Remove(flag 0xf)` / `Add(flag 6)` et `RemoveEffects`. Vérifié à la
        profondeur d'accolades du décompilé : `On(PreUnitDeath)` est au niveau 7, les quatre autres au niveau 9,
        et il n'y a AUCUN `else`. Le port applique donc la garde ci-dessous (`kill_unit_revive_gate`),
        qui draine aussi le revive — mirror de la phase `RunPhase(0xd)` de `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`,
        qui suit la phase de kill `RunPhase(0xc)`."""
        if hp_before is None or hp_before <= 0 or hp_after != 0:
            return None
        uc = tgt.get_component(UnitComponent) if tgt is not None else None
        if uc is not None:
            uc.alive = False
        from .triggers import pending_death_added_triggers
        # #178 — le `didOverkill` du chemin COMBAT est la surcharge d'INSTANCE de
        # `IdunBattle.Core.Services.DamagePrediction$$IsOverkill`, inlinee par
        # `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation` : elle applique DEUX gates
        # d'unite AVANT la formule (`CanBeOverkilled` = pas de trait Steppable, et `HasFlag(target, 0x13)`
        # = `UnitFlag.PreventOverkill`). Le port appelait ici un doublon 2-args qui les avait perdus : il
        # declarait « overkill » des `dmg >= 2*PV`, y compris sur une cible que le natif refuse d'overkiller.
        # #R33 — les TROIS champs restants du `DealDamageInfo` natif descendent maintenant jusqu'ici :
        # `isCritical` (@+0x1c), `isForceOverkill` (@+0x2c) et `deniedDamage` (@+0x18). Le premier est
        # le plus lourd : `IsOverkill` RENVOIE `isCritical` dans le cas « letal mais sous le seuil »,
        # donc tout crit qui tue sans doubler les PV EST un overkill -- le port, qui passait 0 en dur,
        # ne marquait jamais ces morts-la. cf. `_did_overkill`.
        overkill = AttackDamageOperation._did_overkill(
            state, target_id, tgt, hp_before, damage,
            hits_result=hits_result, is_force_overkill=is_force_overkill)
        # `UnitFlag.Overkilled (8)` — le natif le pose dans `IdunBattle.Operations.ApplyDamageOperation$$
        # Execute+0x17d5` (`if (result.didOverkill) UnitFlagsComponent.Add(target, 8)` : le `mov edx,8`
        # precede immediatement le call a `IdunBattle.Entities.Components.UnitFlagsComponent$$Add`), donc
        # AVANT le kill. Cote port l'overkill n'est resolu qu'ici -> on pose le flag ICI, en tete de la
        # sequence de mort et AVANT tout vecteur `On(...)`. DIVERGENCE D'ORDRE NOMMEE : un consommateur
        # natif qui lirait le flag ENTRE l'application du degat et le kill le verrait plus tot ; aucun
        # consommateur porte n'est dans cette fenetre (`DoomSiren` lit le flag APRES tout son volet
        # d'attaque). DIVERGENCE DE GRANULARITE NOMMEE (pre-existante) : le natif calcule `didOverkill`
        # PAR COUP dans `CalculateDamageOperation` ; le port n'a qu'un chokepoint PAR ATTAQUE
        # (`_apply_damage_pipeline`), donc `hp_before`/`damage` sont ceux de l'attaque entiere.
        if overkill:
            fl = tgt.get_component(UnitFlagsComponent) if tgt is not None else None
            if fl is None and tgt is not None:
                fl = tgt.add_component(UnitFlagsComponent())
            if fl is not None:
                fl.add(UnitFlagsComponent.OVERKILLED)
        # `KillUnitOperation$$RecordDeathReason` : la `DamageSource` de la victime est enregistree
        # AVANT `On(PreUnitDeath)` -- c'est la seule raison pour laquelle `HasDeathReason` peut matcher sur ce
        # vecteur (`AReactivateOverwatchEffect$$LegitDeathReasons`, #114).
        AttackDamageOperation._record_death_reason(state, target_id, attacker_id, source_ability)
        # `On(PendingDeathAdded = 3)` — emis par `IdunBattle.Operations.RecordKillOperation$$Execute`
        # (`Core.Services.OperationProcessor$$RecordKill`), qui ENREGISTRE le kill puis ENQUEUE la mort
        # (`MatchState.AddDeath`). La file n'est drainee que plus tard par
        # `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` -> `KillUnitOperation$$Execute`, qui
        # emet `On(PreUnitDeath)` : `On(PendingDeathAdded)` PRECEDE donc strictement `On(PreUnitDeath)` pour une meme mort, d'ou sa place ici.
        # {acteur = caster = le TUEUR, cible = la VICTIME} + le `TriggeringAbility` courant.
        # Consommateur porte : `FuelledByFury_ReviveAbility` (Titus se revive quand SA riposte
        # FinalJustice tue) -- et c'est ce revive-la qui, pose sur Titus pendant SON `On(PreUnitDeath)`, fait
        # ECHOUER la garde `kill_unit_revive_gate` plus bas et ANNULE sa propre mort.
        out = pending_death_added_triggers(state, target_id, attacker_id)
        # `IdunBattle.Core.MatchState$$AddDeath(killer, killed, killTrigger, attackTrigger,
        # AttackRangeType)` : la mort est ENQUEUEE, pas appliquee.
        AttackDamageOperation._add_death(state, target_id, attacker_id, overkill)
        # `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` : le DRAIN. No-op si un drain est
        # deja en cours (cette mort-ci sera prise par son tour de boucle).
        return out + AttackDamageOperation._verify_deaths(state)

    @staticmethod
    def _add_death(state: State, dying_id: int, killer_id, overkill: bool) -> None:
        """`IdunBattle.Core.MatchState$$AddDeath(killer, killed, killTrigger, attackTrigger,
        AttackRangeType)` -- l'ENQUEUE, seul effet « mort » de
        `IdunBattle.Operations.RecordKillOperation$$Execute` (qui, autour, pose
        `UnitFlag.PendingDeath = 0xf`, incremente les compteurs de kills du `PlayerComponent` et publie
        `On(PendingDeathAdded = 3)` -- residus deja nommes pour les deux premiers).

        Le 3e argument, `killTrigger`, est LU DANS le `KillUnitContext` a CET instant
        (`RecordKillOperation$$Execute` le recopie tel quel dans l'appel) : c'est lui que
        `IdunBattle.Operations.KillUnitOperation$$Execute` rejoue ensuite dans l'`AbilityEntities+0x138`
        des evenements de mort, donc lui que comparent `IdunBattleLogic.Entities.DSLFactory$$
        TriggeringAbilityIs` / `$$TriggeringEffectIs`. Cote port ce canal est
        `state.triggering_ability` : on le CAPTURE ici et `_verify_deaths` le REPOSE le temps du drain.
        Sans cette capture, une mort causee DANS le behaviour d'une triggered-ability (le report
        `HazeOfCorruption` 1077) serait drainee hors de ce behaviour et perdrait son declencheur --
        c'est-a-dire exactement le gate anti-chaine que case-haze-bonded a etabli.

        Gate `UnitFlagsComponent.Has(dying, 6)` du natif (« deja retire ») : cote port le gate
        equivalent est en amont (`hp_before > 0 and hp_after == 0` dans `_fire_death_if_killed`, qu'une
        cible a 0 PV ne repasse jamais) ; on double d'une deduplication sur la file, parce qu'entre
        l'enqueue et le drain la cible reste JOIGNABLE par d'autres coups."""
        q = state.pending_deaths
        if any(int(d[0]) == int(dying_id) for d in q):
            return
        q.append((int(dying_id), None if killer_id is None else int(killer_id), bool(overkill),
                  state.triggering_ability))

    @staticmethod
    def _verify_deaths(state: State) -> list:
        """`IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` -- le DRAIN de la file remplie par
        `MatchState.AddDeath` : `RunPhase(0xc)` -> lambda `IdunBattle.Messages.InputMessageProcessor.
        u003Cu003Ec__DisplayClass49_0$$u003CVerifyDeathsu003Eb__0` -> `Core.Services.
        OperationProcessor$$KillUnit` -> `IdunBattle.Operations.KillUnitOperation$$Execute`, **une mort
        a la fois, tant que la file n'est pas vide**.

        NON REENTRANT (case-haze-ord). Une mort ENQUEUEE pendant un drain est traitee au tour de boucle
        SUIVANT -- jamais au milieu du `KillUnitOperation` en cours, ni au milieu du behaviour qui l'a
        causee. C'est ce qui separe le port du natif au regime OVERKILL : les **N** feuilles
        `AttackDamage` d'un `IdunBattle.Entities.Behaviours.AttackBehaviour` UNIQUE (le
        `Attack(bonded, Owner@0x148, N x AttackDamage)` de
        `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$
        CreateTargetTriggerBehaviour`) partent TOUTES avant que la mort de leur cible ne soit traitee,
        donc la `List<LeftOverDamage>` que lit le bond SUIVANT est COMPLETE. Le port drainait a chaque
        feuille : le 2e relais ne recevait qu'UN report au lieu de quatre (mesure seed 777 / PV 1200,
        board MC1_67 : natif 14 `genrand_int32`, port 12).

        `state.triggering_ability` est REPOSE a la valeur capturee par `_add_death` le temps de chaque
        `KillUnitOperation` (mirror du `killTrigger` porte par l'entree de file), puis restaure."""
        if state.draining_deaths:
            return []
        state.draining_deaths = True
        saved_trigger = state.triggering_ability
        out: list = []
        try:
            while state.pending_deaths:
                dying_id, killer_id, overkill, kill_trigger = state.pending_deaths.pop(0)
                state.triggering_ability = kill_trigger
                out = out + (AttackDamageOperation._kill_unit_operation(
                    state, dying_id, killer_id, overkill) or [])
        finally:
            state.triggering_ability = saved_trigger
            state.draining_deaths = False
        return out

    @staticmethod
    def _kill_unit_operation(state: State, target_id: int, attacker_id,
                             overkill: bool) -> list:
        """`IdunBattle.Operations.KillUnitOperation$$Execute` -- l'APPLICATION d'une mort deja
        enqueuee. Emet la SEQUENCE 1 -> 2 -> 0 -> 0x37 -> 0x36 ; les quatre premiers sont portes, DANS
        CET ORDRE (le 5e, `PostUnitKill = 0x36`, n'a pas de consommateur porte). La garde
        `IdunBattle.Operations.KillUnitOperation$$Execute+0x82e` (revive en attente) court-circuite
        tout ce qui suit `On(PreUnitDeath)` -- cf. la docstring de `_fire_death_if_killed`."""
        from .triggers import (after_death_triggers, unit_defeated_triggers,
                               pre_unit_death_2_triggers, unit_death_triggers)
        from .revive import kill_unit_revive_gate
        out = after_death_triggers(state, target_id, attacker_id, overkill=overkill)
        # GARDE @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e : `if (!unitComponent.PendingRevive.HasValue)`. Un `Revive` posé par un
        # consommateur d'`On(PreUnitDeath)` (ReviveEffect, PhoenixGem, ...) fait ÉCHOUER la garde -> la mort est
        # ANNULÉE : on applique le revive (phase 0xd) et on n'émet NI On(PreUnitDeath_2), NI On(UnitDeath), NI On(UnitDefeated), NI On(PostUnitKill).
        revived = kill_unit_revive_gate(state, target_id)
        if revived is not None:
            return (out or []) + [{"kill_cancelled_by_revive": revived}]
        # `On(PreUnitDeath_2 = 2)` — vecteur des death-novas Explodes/PutridExplosion.
        out = (out or []) + pre_unit_death_2_triggers(state, target_id, attacker_id, overkill=overkill)
        # `On(UnitDeath = 0)` — consommateur : TerrifyingCrescendo branche OVERKILL
        # (cf. loki/terrifying_crescendo.py).
        out = out + unit_death_triggers(state, target_id, attacker_id, overkill=overkill)
        # `RemoveEffects` de `IdunBattle.Operations.KillUnitOperation$$Execute` (sous la MEME garde
        # revive) — VOLET PORTE : les MODIFICATIONS D'ABILITY que les effets du mort avaient posees sur
        # d'AUTRES unites sont annulees (`RevertInternal`). Sans ca, un buff comme `ListenUpMaggots`
        # (Kell -> +1 summon / range 3 sur Creed) SURVIVRAIT a la mort de son porteur = divergence
        # silencieuse. ⚠ PERIMETRE VOLONTAIREMENT ETROIT : le `RemoveEffects` natif retire TOUS les
        # effets du mort ; le port ne porte ici que la part `ability_modifications` (les stat-mods d'un
        # cadavre ne sont lus par personne, un retrait global serait un changement de comportement
        # transverse hors perimetre).
        _revert_ability_modifications_of_dead(state, target_id)
        # #G3 : `On(UnitDefeated=55)` (event DISTINCT de 1, 2 et 0) -> Ambush_SummonAbility (mort -> decoy +
        # record turn_defeated). L'unité est déjà alive=False (fire-on-death).
        return out + unit_defeated_triggers(state, target_id, attacker_id)

    @staticmethod
    def _refresh_swarm(state: State, target_id: int) -> None:
        """#60 : bras `On(UnitMemberDeath=48) & OwnerIsTarget` du `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger` — apres toute baisse de PV de la cible, re-evalue le stat-mod EXTRA_HITS du trait
        Swarm (`AddOrUpdateStaticStatModifierEffect 0x3fd`, cf. runner/abilities/loki/swarm.py). No-op
        rapide pour une cible non-swarm ou morte. Lazy import (cycle damage <-> abilities)."""
        from ..abilities.loki.swarm import on_group_unit_hp_changed
        on_group_unit_hp_changed(state, target_id)

    @staticmethod
    def _apply_damage_pipeline(state: State, target_id: int, attacker_id: int, tgt, thc,
                               total: int, profile: Optional[str],
                               shield_dmg: int = 0, armor_dmg: int = 0,
                               is_attack: bool = True,
                               source_ability=None, last_hit: Optional[int] = None,
                               hits_result: Optional[dict] = None,
                               is_force_overkill: bool = False,
                               is_first_hit: Optional[bool] = None,
                               triggering_effect: Optional[int] = None) -> Optional[list]:
        """#202 : CHOKEPOINT post-resolution PARTAGE des 4 vecteurs de degat — mirror du pipeline natif
        unique qui suit toute application de degat : `ApplyDamageOperation` (mutation HP, clamp HP-floor)
        -> OnDeathEvent (`_fire_death_if_killed`) -> compteurs per-tour (`_record_attacked`, attaques
        seulement) -> `RegisterDamageOperation IdunBattle.Operations.RegisterDamageOperation$$Execute` (`_register_received_damage`) -> re-eval Swarm
        (`_refresh_swarm`, On(UnitMemberDeath=48)). Avant ce foyer, chaque vecteur inlinait le meme bloc
        x4 (divergence structurelle vs le chokepoint natif). `is_attack=False` = degat DIRECT (DoT) :
        pas de `_record_attacked` (un DoT n'est PAS une attaque, compteur HasBeenAttackedAmountThisTurn).

        `is_first_hit` / `triggering_effect` = payload du vecteur `On(DamageDealt = 0x10)` emis ci-dessous
        (mirror du champ `AbilityEntities+0x110` et du gate `TriggeringEffectIs` natif). `is_first_hit=True`
        signifie « ce GROUPE de degat contient le coup d'index 0 » : la phase d'arme d'une attaque et la
        1re serie sur une cible le portent ; un groupe de coups ADDITIONNELS (#179, index de sortie > 0)
        ne le porte pas. `None` (defaut) = aucun index de coup dans cet evenement (degat DIRECT / DoT /
        knockback) -> `IsFirstHitInSeries` FAUX, mirror du `Nullable<int>` vide natif.
        Renvoie la liste d'events de mort (ou None si pas de mort / pas de HP)."""
        if thc is None or thc.hp is None:
            return None
        hp_before = thc.hp
        # case-209 : `IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` -- les degats
        # GASPILLES du groupe (coup fatal : reste d'overkill ; coups sur cadavre : la base
        # nominale). AVANT la mutation de PV, parce que le re-jeu part de `hp_before`. Purement
        # additif : aucune branche existante n'en depend, seul `HazeOfCorruption_DamageTransferEffect`
        # relit la liste.
        from .left_over_damage import record_left_over_damages     # lazy : cycle damage<->ops
        record_left_over_damages(state, target_id, tgt, hp_before, total, profile, hits_result,
                                 (hits_result or {}).get("base_nominal"))
        # SITE (A) d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` -- RELU VERBATIM :
        #
        #     cVar15 = IdunBattle_Entities_UnitExtensions__HasFlag(param_4, 8, 0);   // 8 = Overkilled
        #     if (cVar15 != '\0') {
        #       ApplyDamageOperation__RecordHitStatistics(...);
        #       ApplyDamageOperation__AddLeftoverHit(param_2, param_4, &dmg, &hit, 1, 0);
        #       return param_1;                                   // <- TOUT LE RESTE EST SAUTE
        #     }
        #
        # Le `return` precede l'emission d'`On(0x3a)`, la mutation de PV (`FillUpStatComponent$$Reduce`),
        # `On(DamageTaken = 0xf)`, l'ecriture `lastHitDamageTaken` (`stats+0x68` / `+0x6c`) et
        # `On(DamageDealt = 0x10)` : un coup porte sur une cible DEJA OVERKILLEE ne fait qu'empiler sa
        # `LeftOverDamage` (base nominale) et n'emet RIEN. Le port emettait `On(0x10)` -- donc, sur un
        # profil Toxic, le `Maybe(25)` d'`OnToxicDamageAbility` : UN TIRAGE `genrand_int32` de trop.
        # MESURE qui le tranche (`probe_hazeord_death_queue.py`, seed 777 / PV 1200 / MC1_67) : le coup
        # bonus de `HazeCorruption_BonusHitAbility` tombe sur une cible overkillee des le 1er coup
        # d'arme -- le flux natif ne contient AUCUN evenement pour lui, le port en tirait un.
        # GRANULARITE : le natif teste le flag PAR COUP, le port n'a qu'un chokepoint PAR GROUPE -- mais
        # le flag n'est POSE qu'a la fin d'un groupe (`_fire_death_if_killed`), donc « pose a l'entree du
        # groupe » vaut pour TOUS ses coups. Le flag est RETIRE par un revive
        # (`IdunBattle.Operations.ReviveUnitOperation$$Execute` : `Remove(0xf)`, `Remove(8)`,
        # `Add(0x14)`, porte dans `revive.py`) -> une unite ressuscitee redevient frappable.
        fl_entry = tgt.get_component(UnitFlagsComponent) if tgt is not None else None
        if fl_entry is not None and fl_entry.has(UnitFlagsComponent.OVERKILLED):
            return None
        applied = thc.reduce(total)         # #G6a : clamp au HP-floor Hypersensory, pas de PV<0
        # `On(DamageTaken=0xf)` — `IdunBattle.Operations.ApplyDamageOperation$$Execute` emet cet event
        # JUSTE APRES la mutation de PV (`FillUpStatComponent.Reduce`), sous le gate `0 < reduction
        # REELLEMENT appliquee` (variable `local_7dc` du decompile = la valeur de retour de Reduce, PAS
        # le degat demande) -- d'ou `applied > 0` ici. AVANT `_fire_death_if_killed` : cote natif la mort
        # n'est traitee qu'ensuite (`VerifyDeaths` -> `KillUnitOperation`), donc une victime tombee a 0 PV
        # est encore vivante quand l'event part. Seul consommateur porte : ThrillSeekers (branche 2).
        from .triggers.dispatch import (damage_taken_triggers,       # lazy : cycle damage<->triggers
                                        damage_dealt_triggers)
        if applied > 0:
            damage_taken_triggers(state, attacker_id, target_id, profile=profile)
        # `On(DamageDealt=0x10)` (#85) — le TROISIEME et DERNIER event de
        # `IdunBattle.Operations.ApplyDamageOperation$$Execute` (sequence `0x3a` -> `0xf` -> `0x10`).
        #
        # case-221 : son gate n'est PAS celui de `On(0xf)`. RELECTURE du decompile — les deux emissions
        # vivent dans des blocs DISTINCTS, avec des conditions distinctes :
        #   * `On(0xf)`  sous `(0 < local_7dc) || !HealthComponent.IsUnitWithHealthStat(cible)`
        #                 -> `local_7dc` = la valeur de retour de `FillUpStatComponent.Reduce`, donc
        #                    bien « reduction REELLEMENT appliquee > 0 » (porte ci-dessus, inchange) ;
        #   * `On(0x10)` sous `local_7e8 == 0` SEUL (plus le composant de stats et la liste d'events
        #                 non nuls) -- AUCUN terme `0 < local_7dc`. Et `local_7e8` vaut 1 des que
        #                 `degat_sante_demande < 1`, ou que l'octet `hitInfo+0x94` est non nul.
        # => le gate porte est le degat SANTE **DEMANDE** >= 1, PAS l'applique. La difference ne se voit
        # QUE sur un coup qui tombe sur une cible deja a 0 PV : le natif emet, le port ne le faisait pas.
        # MESURE qui tranche (`probe_221_haze_rng_flow.py`, `HazeCorruption_BonusHitAbility` : un coup
        # Toxic sur le cadavre, `Amount 0`) -- 19 confrontations (2 regimes k=0/k=1 x 15 seeds) : le
        # rang du flux qui suit le jet du coup bonus est un `Maybe(25)` d'`OnToxicDamageAbility`, et la
        # tuile de la CIBLE devient `Contaminated` exactement quand `NextBool` <= 25. Les bornes sont
        # exercees des DEUX cotes (seed 55 : valeur 25 -> pose ; seeds 123/64 : valeur 26 -> rien).
        # L'octet `hitInfo+0x94` reste NON modelise (residu nomme : il ne peut que RESTREINDRE).
        if int(total or 0) >= 1:
            # Consommateurs portes : `FleshmetalGunsTileEffectAbility` (pose DespoiledGround 0x5c4
            # pendant le round WarpHail) et, DEPUIS LE DE-FORK, les deux abilities GLOBALES de profil
            # `OnFireDamageAbility` (1016) / `OnToxicDamageAbility` (1203) — qui etaient appelees
            # IMPERATIVEMENT apres l'attaque, donc APRES les vecteurs de mort emis quelques lignes plus
            # bas. Cette place-ci est la place NATIVE, et l'ecart est OBSERVABLE (arbitrage live : ordre
            # bus 6/6 vs ordre imperatif 3/6, cf. la docstring de `damage_dealt_triggers`).
            # `is_first_hit` = « CE groupe de degat contient le coup d'index 0 » -> reproduit le gate
            # natif `IsFirstHitInSeries` sans derouler les coups.
            damage_dealt_triggers(state, attacker_id, target_id, profile=profile,
                                  is_first_hit=is_first_hit, triggering_effect=triggering_effect)
        death = AttackDamageOperation._fire_death_if_killed(
            state, target_id, attacker_id, hp_before, thc.hp, tgt, damage=total,
            # `AbilityOrEffect` de la `DamageSource` du coup letal (`GetDamageSourceAbility`) : ce que
            # `KillUnitOperation$$RecordDeathReason` grave sur la victime pour `HasDeathReason`.
            source_ability=source_ability,
            # #R33 : decomposition PAR COUP (`_run_hits`) — le natif evalue `didOverkill` coup par coup
            # avec le crit ET le `deniedDamage` DE CE COUP. `None` (DoT, knockback, coups additionnels)
            # -> degenerescence en un coup non-critique, = comportement anterieur.
            hits_result=hits_result, is_force_overkill=is_force_overkill)
        if is_attack:
            AttackDamageOperation._record_attacked(state, target_id)    # #G6a : compteur + revert du floor
        AttackDamageOperation._register_received_damage(
            state, target_id, profile, total, shield_dmg, armor_dmg)
        AttackDamageOperation._record_last_hit_damage_taken(
            state, target_id, total, shield_dmg, armor_dmg, last_hit)
        AttackDamageOperation._register_damaged_this_phase(
            state, attacker_id, target_id, total, shield_dmg, armor_dmg)
        AttackDamageOperation._refresh_swarm(state, target_id)          # #60 : On(UnitMemberDeath=48)
        # #100 : `IdunBattle.Operations.RefreshEffectsOperation` (volet stat-modifier) — les PV viennent
        # de changer, donc les `CreateActiveCondition` qui lisent `StatAmount(Self, HEALTH, CURRENT_PCT)`
        # peuvent basculer. Cas porte : `AnvilShield_BlockChanceBelowHealthCap` (1200) dont la
        # contribution BLOCK_CHANCE (+20) doit ENTRER quand Arjac tombe sous 35 % PV (et sortir s'il
        # repasse au-dessus). Idempotent/no-op pour tout autre effet (cf. refresh_effects.py).
        from .refresh_effects import refresh_stat_modifier_effects
        refresh_stat_modifier_effects(state, target_id)
        return death

    @staticmethod
    def _register_received_damage(state: State, target_id: int, profile: Optional[str],
                                  health: int, shield: int = 0, armor: int = 0) -> None:
        """#202 : mirror `IdunBattle.Operations.RegisterDamageOperation$$Execute` -> `ActorStatisticsComponent.
        IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterReceivedDamage` : incremente `received_damage_this_turn[profil]` de la CIBLE
        (TryAdd(profil,1) sinon +1). Consomme par le selecteur `UnitsThatTakenDamageThisTurn IdunBattle.Entities.Formulas.UnitsThatTakenDamageThisTurnSelector$$Select`
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
    def _record_last_hit_damage_taken(state: State, target_id: int, health: int,
                                      shield: int = 0, armor: int = 0,
                                      last_hit: Optional[int] = None) -> None:
        """Mirror des DEUX ecritures que `IdunBattle.Operations.ApplyDamageOperation$$Execute` fait
        sur l'`ActorStatisticsComponent` de la VICTIME (`local_528` = le composant de `param_4`) :

            *(int *)(stats + 0x68) = (int)*param_1;   # lastHitDamageTaken (all-time, non porte)
            *(int *)(stats + 0x6c) = (int)*param_1;   # lastHitDamageTaken THIS TURN  <- porte ici

        `(int)*param_1` = 1er champ du `DamageAppliedResult` = la SOMME des reductions REELLEMENT
        appliquees par CE COUP (`FillUpStatComponent$$Reduce` sante + 2e pool +
        `IdunBattle.Operations.ApplyDamageOperation$$ReduceShield`) -> `last_hit` = `per_hit[-1]` de
        `AttackDamageOperation._run_hits` (qui somme exactement PV + bouclier + armure-pool par coup).

        GRANULARITE : le natif ecrit PAR COUP, le port n'a qu'un chokepoint PAR ATTAQUE -> les callers
        qui connaissent la decomposition passent `last_hit` (le DERNIER coup) ; ceux qui n'ont qu'un
        coup unique (DoT `execute_direct`, knockback `displace`) laissent None et la degenerescence
        `health + shield + armor` est alors EXACTE. Un caller multi-coups qui oublierait `last_hit`
        surestimerait (total de l'attaque au lieu du dernier coup) -- c'est pour ca que la valeur est
        explicite, jamais devinee.

        Le roulement `@+0x6c -> @+0x70` est fait au turn-start du proprietaire
        (`StartTurnOperation.execute`, mirror `IdunBattle.Operations.StartTurnOperation$$ResetUnit`).
        Consommateur : la regen `TimeFlux` (`LastHitDamageTakenLastTurn`)."""
        # INCONDITIONNEL — la chaine de gardes au-dessus de l'ecriture native (remontee au decompile :
        # `if (local_768 != 0)` puis 4 tests de NON-NULLITE de pointeurs) ne contient AUCUN
        # `if (degat > 0)` : un coup entierement bloque ECRASE la valeur precedente par 0.
        amount = int(last_hit) if last_hit is not None else int(health) + int(shield) + int(armor)
        ent = state.get_entity(target_id)
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is not None:
            uc.last_hit_damage_taken_this_turn = amount

    @staticmethod
    def _register_damaged_this_phase(state: State, attacker_id: Optional[int], target_id: int,
                                     health: int, shield: int = 0, armor: int = 0) -> None:
        """Alimente la `List<BEntityId>` @`ActorStatisticsComponent + 0x48` de l'ATTAQUANT (« unites
        endommagees pendant CETTE phase ») -- la source du selecteur
        `IdunBattle.Entities.Formulas.UnitsDamagedThisPhaseSelector$$Select`
        (`IdunBattleLogic.Entities.DSLFactory$$UnitsDamagedThisPhase(attacker)`). Cote port la liste vit
        sur le `UnitComponent` de l'attaquant (`damaged_units_this_phase`, meme residu structurel que
        `received_damage_this_turn`, case-202 §6) et se vide au boundary de phase
        (`State.reset_trigger_phases`, mirror `IdunBattle.Operations.EndPhaseOperation$$ResetEntityPhase`
        qui `Clear()` CE champ dans la MEME boucle que `TriggeredAbilityComponent$$ResetPhase`).

        MEME gate que `_register_received_damage` (du degat a REELLEMENT ete inflige : sante OU bouclier
        OU armure) : le call-site natif exact (l'op enqueue par le pipeline) n'est pas isolable aux xrefs
        -- residu documente, sans effet observable tant que le seul consommateur porte (DoomSiren) tourne
        APRES son propre volet d'attaque. Liste SANS doublon (`OrderedSet`-like : un meme cible frappee
        par plusieurs coups n'y figure qu'une fois), ordre = ordre de premiere frappe."""
        if attacker_id is None or (health <= 0 and shield <= 0 and armor <= 0):
            return
        ent = state.get_entity(int(attacker_id))
        uc = ent.get_component(UnitComponent) if ent is not None else None
        if uc is None:
            return
        if int(target_id) not in uc.damaged_units_this_phase:
            uc.damaged_units_this_phase.append(int(target_id))

    @staticmethod
    def _apply_max_out(state: State, attacker_id: int, hit_nc: "HitDamage",
                       hit_cr: "HitDamage") -> tuple:
        """#202 WeaverOfFate : mirror de la branche max-out des DEUX foyers de degat natifs
        (`IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage` / `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$GetDamage`) :
        si `IsAttackMaxOutDamage(attaquant) == true`, le HitDamage est construit `(max, null)` — le noeud
        est invoque sur son slot GetMaxDamage, AUCUN tirage. Port = degenerer les bornes a (max, max) :
        - voie `get_damage` (limits None / ability roll-then-reduce) : min==max -> AUCUN tirage consomme,
          comme le natif (`IdunBattle.Core.HitDamage$$GetDamage` gate min==max) ;
        - voie slot-8 mode-1 (#67, limits actifs) : le tirage TOUJOURS consomme tire dans [max, max] —
          consommation RNG bit-exacte preservee (IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage sans gate).
        La branche crit d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` prend aussi le max comme base (uVar26 = struct.max) —
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
        """(ShieldComponent|None, total) du bouclier COURANT de la cible — `IdunBattle.Entities.UnitExtensions$$GetShield /
        `IdunBattle.Entities.Components.ShieldComponent$$GetTotalShield. 0 si pas de composant (rétro-compat : cibles sans bouclier)."""
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
        effets (`AddExtraBlockEffectToOwner`, ex. BeastSlayer IdunBattleLogic.Entities.Abilities.Triggered.Loki.BeastSlayerAbility$$CreateAddBlockEffectBehaviour : chance beastSlayerBlockChance /
        amount = blockDmgPct% du FixedArmor courant) — ABSENTES du scalaire (verifie live orksNob
        blockChance=0), que le natif tient dans `GetMultiValueStat(7)` (`IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances`).
        ORDRE : base d'abord, effets ensuite (cible sans block de base -> effet = seule source, ordre moot).
        None si aucune source (retro-compat : 0 tirage). Consomme par les 3 vecteurs (normale/ability/splash). #72.

        #65 : GATE `NoBlocking` (DamageTrait 0) du PROFIL de degat — un profil NoBlocking (ex. `Psychic`,
        Traits=['NoBlocking'], PiercingRatio 100 ; cf. wiki « Cannot be blocked ») BYPASSE le block. Mirror
        de `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` : `DamageProfile.HasTrait(0=NoBlocking)` pose le flag
        (metadata +0x2a) qui SKIP toute la branche block/evade de `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`
        (`if ((metadata>>0x30)==0) { ...block/evade... }`). AUCUN tirage block consomme => 0 tirage RNG (le
        natif ne roule pas le block). Sans ce gate, l'offline sur-roulait un block spurious sur les attaques
        Psychic (seed 123 u95 astraPrimarisPsy -> u79 genesKelermorph BeastSlayer : off 1569 vs live 2873).
        Cable dans les 3 vecteurs (execute/execute_ability_attack/execute_normal_like) via `damage_profile`.

        #221 : l'`Attack` COURANTE du defenseur est THREADEE aux sources d'effet. Le natif construit la
        liste par `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances(attacker, defender,
        failedBlockIds)` = `defender.GetMultiValueStat(7)` -> `IdunBattle.Entities.Components.
        MultiValueStatComponent$$GetAllValues`, qui ajoute D'ABORD l'entree PAR DEFAUT
        `{entityId 0, GetStatPart(comp7, Current)}` (= le scalaire GetStat(7)) puis les entrees
        PAR-ENTITE du dictionnaire (une par effet ExtraBlock). L'amount d'une entree vient de
        `IdunBattle.Entities.UnitExtensions$$GetBlockDamageForBlockChance` = `comp8.GetValueByEntity(
        entityId)` avec fallback `comp8.GetDefaultEntry()` (= GetStat(8)).
        `Daemon_ExtraBlock` (0x40a) est pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.
        DaemonAbility$$CreateUpdateEffectBehaviour` = `AddExtraBlockEffectToOwner(0x40a,
        Direct(GetNumberConstant(0x2d=daemonBlockChance)), GetBlockDamage())` avec
        `IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonAbility$$GetBlockDamage` =
        `PercentageOf(StatAmount(Self@0x148, statType=0=Attack, statPart=0=Current),
        Direct(GetNumberConstant(0x36=daemonBlockDamagePercentage)))`. Sans cette Attack, l'amount
        tombait a 0 -> `DaemonExtraBlockEffect.create_effect_block_source_for_defense` renvoyait None
        -> la source DISPARAISSAIT et le port SAUTAIT le jet de block que le natif roule
        (+1 tirage natif par attaque contre toute unite Daemon, et desync RNG de tout l'aval).
        `ctx.attack` == `GetStat(ATTACK=0, Current)` == le `StatAmount` du DSL (fold documente : le
        natif fige l'amount dans le MultiValueStat a la pose et le RAFRAICHIT sur l'event 0x3b via
        `DaemonAbility$$GetUpdateEffectCondition` = `Not(AmountIsEqual(MultiStatValueFromEffect(0x40a,
        8), GetBlockDamage()))` -- l'entree vaut donc TOUJOURS l'Attack courante).

        `block_id` = le `BEntityId` natif de la source (`BlockChanceInfo.entityId` @+0x0, la cle du
        `failedBlockIds: List<BEntityId>` teste par `Contains`), PAS la chance : entree par defaut =
        **0** (les 4 octets bas laisses a zero par `GetAllValues`), source d'effet = son entite-effet
        (offline : son `effect_type`, cf. `BaseEffect.block_source_id`). Deux sources de MEME chance
        (ex. defenseur Daemon dont le scalaire vaudrait 25) etaient auparavant confondues par le filtre
        d'exclusion inter-coups de `_run_hits` -> un tirage perdu des le coup 2.

        TRI : `CalculateBlockChances` termine par `list.Sort(DamageCalculations.<>c.
        <CalculateBlockChances>b__15_0)` dont le corps est `mov eax,[r8+8]; sub eax,[rdx+8]; ret` =
        `b.blockDamage - a.blockDamage` => **decroissant par AMOUNT**. C'est l'ordre dans lequel
        `ApplyRandomBlockDamage` tente les sources, donc l'ordre des tirages. Tri STABLE ici (Python)
        -> a amount egal, l'ordre pre-tri (base puis effets, = l'ordre de `GetAllValues`) est conserve ;
        le `List.Sort` natif est un introsort NON stable, ecart possible seulement a >=3 sources de
        meme amount (jamais observe -- residu documente)."""
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
            # entree PAR DEFAUT de `GetAllValues` : entityId = 0, chance = GetStat(7), amount = GetStat(8).
            sources.append(BlockSource(chance=block_chance, amount=block_amount, block_id=0))
        sources.extend(defender_effect_block_sources(
            tgt_active_effects, defender_armor,
            defender_attack=int(getattr(tsc.ctx, "attack", 0) or 0)))
        # `list.Sort((a,b) => b.blockDamage - a.blockDamage)` de CalculateBlockChances (decroissant).
        sources.sort(key=lambda s: -int(s.amount or 0))
        return sources or None

    @staticmethod
    def _crit_params(ctx, attacker_effects, state: Optional[State] = None,
                     att_id: Optional[int] = None, tgt_id: Optional[int] = None) -> tuple:
        """(crit_chance, crit_damage, crit_enabled) de l'ATTAQUANT — GetStat(9/10) + bonus calc-time des
        effets (`IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects` / `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects`) ;
        `could_crit` = `IdunBattle.Core.Services.DamageCalculations$$CouldCrit`. Partage par les 3 vecteurs (normale/ability/splash).

        CONTEXTE DU CANAL CRIT (`att_ctx`) -- **FOYER UNIQUE**, pose ICI et nulle part ailleurs.
        `_crit_params` est a l'axe CRIT ce que `runner/damage_model.py::build_hits_board` est a l'axe
        COUPS : la facade COMBAT PARTAGEE des trois vecteurs d'attaque (`damage_ops/normal.py`,
        `damage_ops/ability.py`, `damage_ops/normal_like.py`). Un seul point de calcul, pas un par
        call-site ; les vecteurs ne transmettent que les IDENTITES du coup.

        C'est aussi la place NATIVE. `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage(
        this, attaquant, cible, ...)` passe **les deux entites** a `GetCritDamageBonusFromEffects`, qui
        construit LUI-MEME l'`IdunBattle.Entities.Abilities.AbilityEntities` (caster = owner =
        l'attaquant, target = la cible) avant d'evaluer le trigger de chaque `EffectBonus` via le slot
        d'interface `IdunBattle.Entities.Effects.BaseEffect$$CritDamageBonus`. Le canal natif n'est donc
        PAS aveugle : `get_OwnerIsCaster`, `IsCharging(owner@0x148, target@0x178)`, `HasTrait(target, ...)`
        y sont tous evaluables. C'etait le PORT qui perdait le contexte (residu `N14`).

        `state`/`att_id`/`tgt_id` absents (appelant historique, probe) -> `att_ctx` reste None et TOUT
        gate se tait (« present != applique ») : aucune contribution inconditionnelle possible. Le gate
        reutilise le FOYER du predicat, il ne le duplique pas : `damage_model.battle_query_is_charging`
        -> `engine/battle_query.py::is_charging`, le MEME que les canaux DEGAT et COUPS."""
        att_ctx = None
        if state is not None and att_id is not None and tgt_id is not None:
            from ..damage_model import battle_query_is_charging
            att_ctx = {"is_charging": battle_query_is_charging(state, int(att_id), int(tgt_id))}
        cc = ctx.stat(StatType.CRIT_CHANCE) + crit_chance_bonus_from_effects(attacker_effects)
        cd = ctx.stat(StatType.CRIT_DAMAGE) + crit_damage_bonus_from_effects(attacker_effects, att_ctx)
        return cc, cd, could_crit(cc, cd)

    @staticmethod
    def _target_limits(tgt, thc, damage_profile: Optional[str] = None,
                       is_special: int = 1) -> Optional[dict]:
        """#67 : champs STATIQUES cible de l'etage LIMITES du COMBAT (`IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage`) — mirror ECS du `_target_damage_limits` de la PREDICTION (playbook/prediction.py),
        MEME etage partage (`services/trait_damage_limits.py`). Le natif applique cet etage a
        l'EXECUTION aussi : attaque normale via le per-coup d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (wrappers mode-1
        `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToAttackDamage/IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToAttackDamage`, virtual-only — l'execution
        reutilise la routine per-coup de prediction, cellules min/max capees AVANT la resolution),
        ability/splash via `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` (mode 2 : `ApplyTraitDamageLimitsTo
        Damage(2, &dmg, &dmg, profil, cible, ..., hp=hc+0x18, ...)`). `is_special` = le mode natif
        (1=attack -> Impervious applique ; 2=ability) — sans effet offline tant que
        `impervious_stat_current=None` (no-op documente, comme la prediction).
        None = fast-path retro-compat : cible mono-membre sans Resilient -> etage strictement no-op
        (Impervious charge / boss 0x5d4 = no-op documentes de toute facon).

        #264 -- les TRAITS viennent du substrat d'ENTITE (`entity_trait_names`), pas d'une relecture
        du kit gameconfig par visualId. Le natif lit `HasTrait(cible, Resilient)` sur le
        `BaseUnitComponent`, dont le contenu est celui de `BC.Units[].Traits` plus/moins ce que la
        bataille a accorde/retire -- pas le kit (les deux different, cf. `_load_unit_traits`). MESURE
        (2026-07-30) : `necroOverlord` porte `Resilient` au gameconfig et NE le porte PAS en
        bataille ; ce lecteur capait donc son degat a `HP-1` et le rendait IMPOSSIBLE A TUER
        offline, alors que le natif le tue. `nrOfMembers` reste gameconfig : ce n'est pas un trait
        (c'est `GroupUnitComponent`, autre canal, hors #264)."""
        from ...entities.traits.unit_trait import entity_trait_names
        tuc = tgt.get_component(UnitComponent) if tgt is not None else None
        if tuc is None or thc is None or not thc.hp_max:
            return None
        import gameconfig as GC
        gu = GC.unit(tuc.visual_id) or {}
        tsc = tgt.get_component(StatsComponent)
        utraits = entity_trait_names(tsc.ctx if tsc is not None else None, tuc.visual_id)
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
            "member_count": n,                 # GroupUnitComponent (IdunBattle.Core.Services.DamagePrediction$$ApplyGroupUnitDamageLimit lit le composant cible)
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
        """#120 : additif DÉFENSEUR plat PRÉ-perçage (Nightshroud_DmgReduction IdunBattle.Entities.Effects.Loki.Nightshroud_DmgReduction_Effect$$CreateDamageDefenseModifier =
        `ForSubtraction(OwnerIsTarget, ConfigVar 0x12=dmgReduction×mult)`) fusionné dans le slot additif
        @+0x10 — le MÊME que l'additif ATTAQUANT #75. `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` ne
        consomme @+0x10 qu'UNE fois, AVANT perçage. Mirror EXACT du merge PRÉDICTION
        (`_add_positional_and_defender_mods`, prediction.py:172) : on SOUSTRAIT de `mods.additive`
        (l'accumulateur ATTAQUANT, consommé pré-perçage via `attacker_additive_pre=True`) → la réduction
        est DILUÉE par perçage/armure PUIS scalée ×%-list UNE fois, comme l'additif #75. SANS pré-scale ×M
        (≠ ForAddition Neuroparasite, qui compense le placement post-%-list). Canal SÉPARÉ de `def_mods.additive`
        (appliqué à part par `apply_all_modifiers`) → aucune double-application. Vide → no-op (rétro-compat)."""
        if def_mods.flat_reductions:
            mods.additive -= sum(def_mods.flat_reductions)
        # #112 : axe PERCAGE porte par un effet de la CIBLE (`<Effect>.CreatePiercingBonusForAttack`
        # avec trigger `OwnerIsTarget`, ex. `IdunBattle.Entities.Effects.Loki.
        # Supercharge_ExtraPiercingEffect$$CreatePiercingBonusForAttack` = `ForPiercing(
        # DamageProfileIs(Plasma) & OwnerIsTarget, ConfigVar(0x3f=extraPierceRatio))`). Le natif SOMME
        # le champ Piercing@+0x20 de l'accumulateur ATTAQUANT ET de l'accumulateur DEFENSEUR avant
        # `GetBaseDamageWithFixedPiercedArmor` (`pierce_eff = clamp(pierce + extra, 0, 100)`) ; le port
        # ne passe que `mods` (attaquant) a `apply_pierce_and_modifiers` -> on FUSIONNE ici, au MEME
        # endroit que la reduction plate defenseur. Vide -> no-op strict (aucun effet PREEXISTANT
        # n'alimentait ce canal : `create_piercing_bonus_for_attack` par defaut = None).
        if def_mods.extra_pierce:
            mods.extra_pierce += def_mods.extra_pierce


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
        # --- #70 GATE ACTEUR-MORT (mirror `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` :
        # `if (EntityExtensions.IsUnit(caster) && UnitExtensions.IsDead(caster)) return 0;`). L'attaque
        # normale native EST une ActiveAbility per-unite (#139) -> passe par le MEME gate. Un attaquant MORT
        # (hp<1, non-Fled ; `IdunBattle.Entities.UnitExtensions$$IsDead`) => NO-OP complet (0 tirage RNG, 0 degat,
        # aucun after-hit, aucun flag), AVANT toute selection d'arme / boucle de coups. Le port `execute`
        # mirror `IdunBattle.Operations.AttackDamageOperation$$Execute` qui n'a AUCUN gate liveness natif -> le gate vit
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
            # #120bis : la cible du vecteur after-hit = celle que l'attaque a REELLEMENT frappee
            # (`last["target"]`), pas celle du message — la re-resolution d'`ActiveAbilityOperation$$
            # ExecuteInternal` peut avoir bascule l'attaque sur une remplacante (SwornProtector/Kell).
            # Le natif emet ces vecteurs depuis `AttackDamageOperation$$ExecuteHit`, donc avec
            # l'AttackData de l'attaque re-entrante. Defaut = la cible du message (retro-compat).
            self.after_hit = after_hit_normal_attack(
                self.state, msg.attacker_id, self.last.get("target", msg.target_id),
                bool(self.last.get("ranged")), self.last.get("profile"),
                is_crit=bool(self.last.get("did_crit")), profiles=_profs,
                did_block=bool(self.last.get("did_block")))
        # #139 : l'attaque normale native EST une ActiveAbility (NormalAttack per-unite ; AttackUnitMessage
        # n'existe pas en natif — c'est la simplification port de l'ActiveAbilityMessage) et traverse la
        # MEME queue `IdunBattle.Operations.ActiveAbilityOperation$$AddFlagsAfterAbilityExecution — base `SetsEndTurnFlags`/
        # `SetsActiveAbilityUsedFlag` = `_dsl.True` IdunBattle.Entities.Abilities.AActiveAbility$$SetsEndTurnFlags (aucune classe NormalAttack dans la famille
        # d'overrides) -> flag ActiveAbilityUsed(2) + FinishUnitTurn (flags 1+3). Bookkeeping observable ;
        # aucun gate du port ne le lit encore (PickNextUnit/VerifyUnitsTurnFinished = couche non portee).
        if self.last is not None:
            from .turnflow import add_flags_after_ability_execution
            self.last["flags"] = add_flags_after_ability_execution(
                self.state, int(msg.attacker_id), skip_ability_used=False, skip_end_turn=False)
