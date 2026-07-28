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
                  is_attack_damage_op: bool = True, force_overkill: bool = False,
                  force_crit: bool = False, hit_index0: int = 0) -> dict:
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
        BASE ajoute 1 coup bonus DÉFÉRÉ (FIFO, boucle de fin d'`IdunBattle.Operations.AttackDamageOperation$$Execute`
        sur `hitGroup+0x58`, alimenté par `IdunBattle.Operations.ADamageOperation$$UpdateHitGroupAfterHit`)
        exécuté APRÈS la boucle de base, MÊME profil
        réduit. Un coup bonus d'index impair RE-tire un Maybe (tirage consommé) mais son succès est IGNORÉ
        (anti-récursion : le natif itère une COPIE de la liste, prise APRÈS la boucle de base).
        `bonus_hit_chance is None` (défaut) => strict no-op (rétro-compat totale).

        `hit_index0` (R6-b', défaut 0) = valeur de `currentAttack+0x30` A L'ENTREE de cette série de
        coups. Le compteur natif n'est PAS local à `ExecuteHits` : c'est un champ de l'`OngoingAttack`
        (`IdunBattle.Core.OngoingAttack$$.ctor` l'initialise à 0), poussée UNE FOIS par attaque sur la
        pile `MatchState+0x60` par `IdunBattle.Core.MatchState$$StartAttack`
        (`IdunBattle.Operations.StartAttackOperation$$Execute`) et relue par `Peek`
        (`IdunBattle.Core.MatchState$$GetCurrentAttack` <- `IdunBattle.Core.Services.BattleQuery$$
        GetCurrentAttackOrDefault` <- `IdunBattle.Operations.ADamageOperation$$GetCurrentAttackOrDefault`).
        `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` relit `currentAttack+0x30` FRAIS à
        chaque tour de boucle et `IdunBattle.Operations.ADamageOperation$$UpdateCurrentAttackAfterHit`
        l'incrémente après CHAQUE coup => l'index CONTINUE à travers les sous-opérations d'une même
        attaque (coups bonus ET groupes de coups additionnels). Le retour porte `next_hit_index` pour
        que l'appelant le THREADE (cf. `operations/additional_hits.py`).

        `force_overkill` (défaut False) = flag « always overkilled » d'un `AttackWithAttackDamage` natif
        (Nullable<bool>=true, 8e arg de `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -> `AttackDamageBehaviour`
        -> `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage`) : force `overkill=True` a CHAQUE coup dans les 3 sites de
        calcul `_ovk`, ce qui BYPASSE le cap Resilient (`IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit` :
        `if not overkill: cap = curHP-1`). N'affecte QUE le cap Resilient (member-cap/boss/impervious ne lisent
        PAS `overkill`) -> NO-OP sur cible non-Resilient (zero regression) ET aucune conso RNG supplementaire
        (change seulement la VALEUR capee, pas le nombre de tirages). Porteur unique : FlailSwing (1042).

        `force_crit` (defaut False) = flag « always crit » du `Nullable<AttackOptions>` (8e arg de
        `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`, **octet +5 de la struct
        d'options**) -> chaque coup est CRITIQUE **sans tirage**. RE (mirror
        `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`) :

            local_628 = <slot 4 de BaseUnitComponent+0x68> ? 1 : message[+0x2c]
            if (message[+0x29] == 0) {            # flag « never crit »
                if (local_628 == 0) isCrit = RollCritical(...)      # <- 1 tirage possible
                # sinon : isCrit reste a 1, AUCUN appel a RollCritical
            } else isCrit = 0

        et `AttackDamageBehaviour$$ExecuteTarget` remplit `message[+0x2c]` depuis `options + 5`
        (packing lu : msg+0x28<-opt+3, +0x29<-opt+1, +0x2a<-opt+2, +0x2b<-opt+4, **+0x2c<-opt+5**,
        +0x2e<-opt+0, +0x2f<-opt+6 ; l'octet +4 est celui qu'utilise FlailSwing pour l'overkill, ce
        qui CALE le mapping). Consequences portees, toutes deux necessaires :
          * le crit est acquis meme si `CouldCrit` est faux (cc = 0 : le cas de TOUS les porteurs
            actuels) -> le caller doit fournir des bornes crit (`hit_cr`) meme sans `crit_enabled` ;
          * AUCUN tirage crit n'est consomme (le natif SAUTE `RollCritical`) -> a cc >= 1 le port
            ne doit pas rouler non plus, sous peine de desynchroniser le flux RNG.
        Porteur : TacticalPrecision (1154, branche CHARGE ; i2 « This attack is always a Crit »).
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

        def _limits_scalar(value: int) -> int:
            """Etage LIMITES en cap SCALAIRE sur la valeur DONNEE (cellule degeneree du core, mode 2).
            Cumule le rogne (`_rogne`, param_12 de la porte overkill) et calcule `IsOverkill` depuis
            CETTE cellule -- mirror `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage(2, &v, &v, ...)`."""
            if limits is None or value <= 0:
                return value
            rem = max(0, limits_hp - total)
            ovk = force_overkill or (compute_prediction_overkill(rem, limits_hp, value, p12=_rogne[0])
                                     if limits_hp > 0 else False)
            capped = apply_trait_damage_limits_to_damage(value, current_health=rem,
                                                         overkill=ovk, **limits)
            _rogne[0] += max(0, value - capped)
            return capped

        def _ability_shield_split(raw: int, reduce_fn, flat: int) -> tuple:
            """`IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` — mirror de l'ORDRE natif
            (famille ABILITY = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` ->
            `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit`, cf. `is_attack_damage_op`) :

                dmg        = Math.Max(param_2, 0)                                   # degat DEJA resolu
                shieldPart = Math.Min(dmg, UnitExtensions.GetShield(cible))         # `iVar20`
                v          = CalculateBaseDamageWithAllModifiers(dmg - shieldPart)  # `iVar17 - iVar20`
                v          = Fix64.Max(v + flat, 0)
                v          = ApplyTraitDamageLimitsToDamage(2, &v, &v, ...)         # cap sur le RESTE
                return       (int)(Fix64(shieldPart) + v)

            La part BOUCLIER est donc retiree AVANT les modificateurs ET avant l'etage limites, puis
            RE-ADDITIONNEE apres : ni les %-mods/percage ni les caps (member-cap, Resilient, cap boss)
            ne mordent sur ce qui est absorbe par le bouclier. Le total rendu ici repasse ensuite par
            le split shield-first de `calculate_damage_operation` (sub-op 0x42) qui redonne EXACTEMENT
            `shield_dmg = shieldPart` et `health = v` (min(shieldPart + v, shield) == shieldPart).

            RESIDU #67 §5 FERME : le port capait AVANT le split (= ordre de la famille ATTACK, ou les
            limites capent les CELLULES en amont de `CalculateDamageOperation`) -> sur une cible a
            bouclier NON NUL le cap Resilient/member rognait la part absorbee au lieu du reste, et la
            cible encaissait `cap - shield` PV au lieu de `cap`. Identique bit-a-bit quand shield == 0.

            `reduce_fn` = `CalculateBaseDamageWithAllModifiers` (mode bornes : le `post_roll` du caller) ;
            `None` = le montant recu est DEJA reduit (mode `amount`/normal-like, ou la reduction precede
            le tirage) -> seul l'etage LIMITES est deplace derriere le bouclier. `flat` = la reduction
            CAPEE defenseur #91 (composante du meme CBDWAM natif -> post-bouclier elle aussi).
            Renvoie `(shieldPart, rest)` PRE-limites (le caller cape `rest` puis re-additionne)."""
            dmg = max(0, raw)
            shield_part = min(dmg, max(0, shield))          # `Math.Min(local_65c, GetShield)`
            rest = dmg - shield_part                        # `iVar17 - iVar20`
            if reduce_fn is not None:
                rest = reduce_fn(rest)                      # CalculateBaseDamageWithAllModifiers
            if flat:
                rest -= flat                                # #91 : reduction CAPEE defenseur (scalaire)
            return shield_part, max(0, rest)                # `Fix64.Max(., 0)`

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
                # `force_crit` = flag options+5 : le natif SAUTE `RollCritical` -> crit acquis, 0 tirage.
                crit = True if force_crit else (roll_critical(rng, crit_chance) if crit_enabled else False)
                crits.append(crit)
                if crit:
                    # `IdunBattle.Core.Services.DamagePrediction$$CalculateCriticalDamage` -> `IdunBattle.Core.Services.DamageCalculations$$ApplyCritDamage` : critBonus
                    # FLAT sur la valeur ROULÉE, PRE-reduce. Le montant = le SHIFT des bornes crit
                    # (hit_cr = bornes + critDamage, largeurs égales -> même modulo => numériquement ==
                    # l'ancien modèle bornes-décalées).
                    raw += hit_cr.min - hit_nc.min
                _flat = (_capped_flat_cr if crit else _capped_flat_nc) if capped_reductions else 0
                if is_attack_damage_op:
                    # Famille ATTACK (`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`) : le
                    # split bouclier vit dans `IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`
                    # (`Math.Max(0, dmg - shieldPart)`) AVAL, les caps sont poses en amont sur les
                    # cellules -> cap sur le TOTAL, split apres. Inchange (#67, live bit-exact).
                    roll = post_roll(raw)     # réduction perçage/armure/mods APRÈS le tirage
                    if capped_reductions:     # #91 : réduction CAPÉE défenseur (scalaire FLAT, D=centre)
                        roll = max(0, roll - _flat)
                    rolls.append(roll)        # rolls = tirage POST-mods PRE-limites
                    roll = _limits_scalar(roll)
                else:
                    # Famille ABILITY (`IdunBattle.Operations.AbilityDamageOperation$$ExecuteHit` ->
                    # `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`) : part bouclier
                    # retiree AVANT mods + limites, re-additionnee apres (#67 §5, cf. `_ability_shield_split`).
                    _sp, _rest = _ability_shield_split(raw, post_roll, _flat)
                    rolls.append(_sp + _rest)     # rolls = POST-mods PRE-limites (== ci-dessus si shield==0)
                    roll = _sp + _limits_scalar(_rest)
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
            crit = True if force_crit else (roll_critical(rng, crit_chance) if crit_enabled else False)
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
            # BOUCLIER x LIMITES (residu #67 §5, FERME) : la famille ABILITY passe le degat par
            # `CalculateAbilityDamage`, qui retire `min(dmg, shield)` AVANT le core limites et le
            # re-additionne apres -> le cap ne mord que sur le RESTE. Porte ici par
            # `_ability_shield_split` sous le gate `not is_attack_damage_op` (la famille ATTACK, elle,
            # cape en amont du split de `CalculateDamageOperation` : ordre inverse, inchange).
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
                if is_attack_damage_op:
                    roll = _limits_scalar(roll)          # cap sur le TOTAL, split bouclier en aval
                else:
                    # mode `amount`/normal-like de la famille ABILITY : la reduction PRECEDE deja le
                    # tirage (bornes pre-reduites) -> seul l'etage LIMITES est deplace derriere le
                    # bouclier (`reduce_fn=None`), le reste de `CalculateAbilityDamage` est inchange.
                    _sp, _rest = _ability_shield_split(roll, None, 0)
                    roll = _sp + _limits_scalar(_rest)
            return _one_hit_tail(idx, crit, roll)

        base_bonus = 0
        for i in range(hits):
            if _one_hit(hit_index0 + i):        # index de l'ATTAQUE (continu), pas de la serie
                base_bonus += 1
        # #62c : coups bonus DEFERES (FIFO) apres la boucle de base — exactement `base_bonus` coups (count=1
        # par succes). Chaque coup bonus repasse le corps complet (crit/spread/block + re-roll Maybe si son
        # index est impair) ; son succes eventuel est IGNORE (pas de recursion, garde native).
        bonus_idx = hit_index0 + hits
        for _ in range(base_bonus):
            _one_hit(bonus_idx)
            bonus_idx += 1
        return {"total": total, "shield_dmg": shield_dmg, "armor_dmg": armor_dmg,
                "did_crit": did_crit, "did_block": did_block, "did_evade": did_evade,
                "crits": crits, "rolls": rolls, "per_hit": per_hit,
                "per_hit_health": per_hit_health,
                "bonus_hits": base_bonus,
                # R6-b' : `currentAttack+0x30` APRES cette serie — `UpdateCurrentAttackAfterHit`
                # incremente APRES CHAQUE `ExecuteHit`, coups bonus compris.
                "next_hit_index": hit_index0 + hits + base_bonus}
