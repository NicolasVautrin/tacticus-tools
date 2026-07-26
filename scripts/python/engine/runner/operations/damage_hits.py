"""Machinerie de degat PAR COUP extraite d'`operations/damage.py` (scission du module >1000
lignes, tache #60 -- deplacement VERBATIM, zero changement de comportement).

Contenu :
  - `HitDamage` : struct {Min, Max} du degat d'UN coup (`IdunBattle.Core.HitDamage`).
  - `_DamageHitsMixin` : la boucle PAR COUP partagee `_run_hits` (`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, attaque normale ET ability), heritee telle quelle par `AttackDamageOperation`
    (`AttackDamageOperation._run_hits` resout via MRO ; appele aussi par `additional_hits`).

Module FEUILLE : ne reference que des fonctions de `services` + ses arguments -> AUCUNE dependance
sur `damage` (pas de cycle d'import).
"""
from __future__ import annotations

from ...services.damage_calculations import spread_to_min_max
from ...services.damage_combat import calculate_damage_operation, Damage, roll_critical
from ...services.damage_modifiers import capped_reduction_flat
from ...services.trait_damage_limits import (apply_trait_damage_limits_to_damage,
                                             compute_prediction_overkill)
from ..prng import IntBasedMersenneTwister


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
        """`IdunBattle.Core.HitDamage$$GetDamage.

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


class _DamageHitsMixin:
    """Mixin PAR COUP de `AttackDamageOperation` : la boucle `_run_hits` (attaque normale ET
    ability). Sans etat (staticmethod) ; herite tel quel -> `AttackDamageOperation._run_hits`."""
    __slots__ = ()

    @staticmethod
    def _run_hits(rng: IntBasedMersenneTwister, hit_nc: "HitDamage", hit_cr: "HitDamage",
                  crit_chance: int, crit_enabled: bool, hits: int, block_sources,
                  shield: int = 0, armor_pool: int = 0, armor_pct: int = 0, post_roll=None,
                  bonus_hit_chance: Optional[int] = None, capped_reductions=None,
                  limits: Optional[dict] = None, limits_hp: int = 0,
                  is_attack_damage_op: bool = True, force_overkill: bool = False) -> dict:
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
        (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.GetStuckInAbility$$CreateBehaviour`, roll `IdunBattle.Entities.Behaviours.MaybeBehaviour$$Execute`) évalué dans
        `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` (dernière instr. de `ExecuteHit`). Chaque SUCCÈS d'un coup de
        BASE ajoute 1 coup bonus DÉFÉRÉ (FIFO, `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithoutDamageProfileType`,
        gate natif `attack.count==1 && !additionalHitsFlag`) exécuté APRÈS la boucle de base, MÊME profil
        réduit. Un coup bonus d'index impair RE-tire un Maybe (tirage consommé) mais son succès est IGNORÉ
        (anti-récursion). `bonus_hit_chance is None` (défaut) => strict no-op (rétro-compat totale).

        `force_overkill` (défaut False) = flag « always overkilled » d'un `AttackWithAttackDamage` natif
        (Nullable<bool>=true, 8e arg de `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -> `AttackDamageBehaviour`
        -> `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage`) : force `overkill=True` a CHAQUE coup dans les 3 sites de
        calcul `_ovk`, ce qui BYPASSE le cap Resilient (`IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` :
        `if not overkill: cap = curHP-1`). N'affecte QUE le cap Resilient (member-cap/boss/impervious ne lisent
        PAS `overkill`) -> NO-OP sur cible non-Resilient (zero regression) ET aucune conso RNG supplementaire
        (change seulement la VALEUR capee, pas le nombre de tirages). Porteur unique : FlailSwing (1042).
        Renvoie total/per_hit/rolls/crits + flags. Pools déplétés entre coups (0 -> invariant)."""
        total = shield_dmg = armor_dmg = 0
        did_crit = did_block = did_evade = False
        crits: list[bool] = []
        rolls: list[int] = []
        per_hit: list[int] = []
        # Part PV SEULE par coup (`Damage.health`) — expose EN PLUS de `per_hit` (qui somme PV+bouclier+
        # armure-pool). Consommateur : `ChainLeftOverHitsAttackDamage` (MultiThreatEliminator #116), qui
        # doit savoir A QUEL COUP la cible tombe a 0 PV pour compter les coups GASPILLES sur le cadavre
        # (`ApplyDamageOperation.AddLeftoverHit`). PUREMENT ADDITIF (aucune branche modifiee).
        per_hit_health: list[int] = []
        failed_block: set = set()          # ids de sources de block AYANT ECHOUE (accumule ENTRE coups, #72)
        # #91 : réduction CAPÉE défenseur (GuardianOrganism) = scalaire FLAT pré-évalué (natif IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers) où
        # D = CurrentDamage = CENTRE des bornes réduites (post pierce/armure/%-mods) -> soustrait IDENTIQUE à
        # chaque coup, PAS 33%×valeur-tirée (confirmé LIVE #91). Un flat par type de coup (non-crit/crit).
        _capped_flat_nc = capped_reduction_flat((hit_nc.min + hit_nc.max) / 2.0, capped_reductions) \
            if capped_reductions else 0
        _capped_flat_cr = capped_reduction_flat((hit_cr.min + hit_cr.max) / 2.0, capped_reductions) \
            if capped_reductions else 0
        _rogne = [0]        # #67 : rogne cumule des cellules MIN des coups precedents (porte overkill)

        def _one_hit_tail(idx: int, crit: bool, roll: int) -> bool:
            """Queue PARTAGÉE d'un coup : split combat (sub-op 0x42) + comptabilité + Maybe GetStuckIn.
            #72 : mirror `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances(param_4=failedList) -> une source de block
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
            per_hit_health.append(dmg.health)     # part PV SEULE du coup (hors bouclier/armure-pool)
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

            CONSOMMATION RNG PER-COUP — mirror `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` (per-coup
            PARTAGÉ attaque normale ET ability AttackWithAttackDamage ; cas fable rngcrit-1202, 2026-07-23) :
              1. `IdunBattle.Core.HitDamage$$GetDamage` sur le STRUCT d'entrée — tirage SSI struct.min != max :
                 - NORMALE : struct DÉGÉNÉRÉ (Attack,Attack) -> 0 tirage (la vraie valeur = étape 4) ;
                 - ABILITY bounds-mode : struct = [minDmg,maxDmg] config -> 1 tirage = LA VALEUR (brut).
              2. `RollCritical` slot 0xa -> `IdunBattle.Core.Services.DamagePrediction$$RollCritical` : gate `cc<1 ->
                 false SANS tirage` (le NextBool brut `IdunBattle.Core.Services.DamageCalculations$$RollCritical` n'est
                 atteint QU'À travers ce gate) + bypass crit-garanti (byte +0x2c / buff slot 4) qui SKIPPE
                 le roll. Il n'existe AUCUN chemin consommant un tirage crit à cc=0 — ni par vecteur, ni
                 par « éligibilité » : l'éligibilité crit d'une ability se matérialise par cc=0.
              3. slot 4 `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation` : shield-part/armure/caps -> cellules
                 min/max (0 RNG ; les block CHANCES y sont calculées, pas roulées).
              4. slot 8 `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` : `Next(min, max+1)` — TOUJOURS 1 tirage
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
                    # `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage` -> `IdunBattle.Core.Services.DamageCalculations$$ApplyCritDamage` : critBonus
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
                # (`IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage` : Next(v, v+1) SANS gate largeur-1). C'EST le
                # tirage « fantôme » mesuré par #220/#205 — le fix du désync multi-coups cc=0.
                # `is_attack_damage_op` = LA FAMILLE DE FACTORY NATIVE (deux operations distinctes) :
                #   True  = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (+overloads IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage/350/
                #           520/6b0) -> AttackDamageBehaviour -> AttackDamageOperation.ExecuteHit
                #           IdunBattle.Operations.AttackDamageOperation$$ExecuteHit -> le resolve slot-8 consomme (2 tirages/coup a cc=0) ;
                #   False = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage/IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage -> core IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`
                #           -> AbilityDamageBehaviour -> IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits
                #           (GetDamage par coup) + IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage (0 RNG) : AUCUN
                #           resolve -> 1 tirage/coup. Mesure live : Stormcaller 3-hit bit-exact SANS
                #           tirage gaspille (probe_217 PASS pre-fix, FAIL avec un resolve inconditionnel).
                if is_attack_damage_op:
                    rng.next_internal(max(0, roll), max(0, roll) + 1)
                return _one_hit_tail(idx, crit, roll)
            crit = roll_critical(rng, crit_chance) if crit_enabled else False
            crits.append(crit)
            hd = hit_cr if crit else hit_nc
            # #67 : etage LIMITES du natif (`IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage`) — MEME etage
            # partage que la prediction (`services/trait_damage_limits.py`, bit-exact 1357 s16) :
            # member-cap Swarm (443/443/444/444, live run 60102 + probe 67061 vs scarab plein) +
            # Resilient HP-1 (porte overkill) + bypass Blast (HitsMultipleMembers, probe 67071).
            # `_rem` = HP restant avant CE coup (le natif relit le HealthComponent entre coups ; ici
            # `limits_hp - total`). Deux ORDRES natifs distincts, discrimines live (probe 67101) :
            #  - ATTAQUE (mode 1) : les caps s'appliquent aux BORNES min/max PUIS le tirage se fait
            #    DANS la plage capee (routine per-coup slot-4 -> resolution slot-8 d'`ExecuteHit
            #    IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` ; le core cape *param_3/*param_4 = cellules min et max). Preuve : tour
            #    letal live [505,541,602,206] — coup 3 tire 602 dans [lo, cap=808] (largeur CAPEE :
            #    le meme tirage donnait >=809 en pleine largeur), coup 4 degenere [206,206] = rem-1.
            #    Le tirage est TOUJOURS consomme (IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage appelle
            #    Next(min,max+1) SANS gate min==max — largeur 1 = 1 tirage quand meme) -> les caps
            #    TOTAUX (swarm : cap < lo, plage degeneree) restent bit-exacts en consommation.
            #  - ABILITY/splash (mode 2) : cap SCALAIRE post-tirage — `CalculateAbilityDamage
            #    IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` recoit le degat DEJA resolu et passe la MEME cellule deux fois
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
                "per_hit_health": per_hit_health,
                "bonus_hits": base_bonus}
