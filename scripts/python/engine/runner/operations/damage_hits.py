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
                                             compute_prediction_overkill, unit_is_overkill)
from ..prng import IntBasedMersenneTwister


class HitDamage:
    """`IdunBattle.Core.HitDamage` — struct {Min, Max} du dégât d'UN coup (avant réduction).

    Layout natif : Min @+0 (uint), Max @+4 (uint)."""
    __slots__ = ("min", "max")

    def __init__(self, min_: int, max_: int):
        self.min = min_
        self.max = max_

    @classmethod
    def from_base(cls, base: int, spread_pct: int) -> "HitDamage":
        """Construit le {Min,Max} d'un coup depuis le dégât de base (spread BC).

        Le moteur bâtit ce MinMaxDamage en amont (SetupHitGroup) ; ici on le
        reconstruit fidèlement via `spread_to_min_max` (= CalculateDamageSpread).

        ⚠ `spread_pct` est OBLIGATOIRE (#449-r2-r4). Il portait `= 20` en dur, alors que le natif
        le lit dans `BattleConfiguration.Damage.DamageSpreadPercentage`
        (`IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64`) — et cette
        méthode n'a AUCUN appelant sous `scripts/python` (mesuré : 0 site `.from_base(`). Un défaut
        y aurait donc été un littéral que rien n'exerce, donc que rien ne peut invalider : le
        rendre obligatoire est ce qui force le futur appelant à dire d'où vient sa valeur."""
        mm = spread_to_min_max(base, spread_pct)
        return cls(mm.min, mm.max)

    def get_damage(self, rng: IntBasedMersenneTwister, use_midpoint: bool = False) -> int:
        """`IdunBattle.Core.HitDamage$$GetDamage`.

          • Min == Max            → Min            (AUCUN tirage RNG)
          • use_midpoint (prédiction) → (Min+Max)/2 (troncature entière, aucun tirage)
          • sinon                 → rng.Next(Min, Max+1) = next_internal(Min, Max+1)
                                    (uniforme [Min,Max], 1 tirage)

        ⚠ La branche midpoint TRONQUE, et c'est JUSTE — relu au décompilé `rnca9r7q6c` par #344 :
        `return (ulonglong)(uint)((iVar1 + *(int *)this) / 2)`, division entière C sur les deux `int`
        du struct, **aucun Fix64 sur ce chemin**. Ce n'est donc ni `IdunBattle.Core.Services.MinMaxDamage$$Avg`
        ni `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamageAverage`, qui arrondissent tous
        deux demi-vers-le-PAIR : sur `Min+Max` valant 3 mod 4 cette fonction rend UNE unité de MOINS
        qu'eux, et c'est le comportement natif. Ne pas « corriger » (cf. docs/rl/case-344).
        """
        if self.min == self.max:
            return self.min
        if use_midpoint:
            return (self.min + self.max) // 2      # (int)((Max+Min)/2) — TRONCATURE native, cf. supra
        return rng.next_internal(self.min, self.max + 1)


def crit_gate_open(crit_allowed: bool, is_attack_damage_op: bool) -> bool:
    """Le gate « never crit » d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHits`
    (`options[+0x29] |= (hitGroup.isCriticalDamageAllowed == 0)`), lu par
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` juste avant `RollCritical` :
    fermé => `isCrit = 0` **sans aucun tirage**.

    Fonction de MODULE, et pas une expression inline, pour une seule raison : c'est le point de
    MUTATION des probes/cliquets (`probe_366r1_crit_multihit.py --mutate nogate`,
    `test_crit_multihit_stops_live.py`). La rendre toujours vraie restaure exactement le port
    d'AVANT #366-r1-crit-multihit (un crit-roll par coup) -- une contre-épreuve qui DOIT diverger
    du live. Même pattern que `apply_all_modifiers` pour #131.

    `is_attack_damage_op` False = famille ABILITY (`AbilityDamageOperation$$ExecuteHits`, boucle
    PLATE : ni `|=`, ni recalcul) -> le gate n'y existe pas."""
    return (not is_attack_damage_op) or crit_allowed


def attack_state_out(r: dict, ah: Optional[dict] = None) -> dict:
    """L'etat de l'`OngoingAttack` EN SORTIE d'une operation de degat (#419-r3) -- les trois champs
    qu'une feuille composee APRES elle DANS LE MEME `IdunBattle.Entities.Behaviours.AttackBehaviour`
    lirait par `IdunBattle.Operations.ADamageOperation$$GetCurrentAttackOrDefault(isOutsideAttack: 0)`
    (slot **200** `GetCurrentAttackOrDefault` d'`IBattleQuery`, arite 0) :

        `next_hit_index` = `OngoingAttack+0x30`   (`ADamageOperation$$UpdateCurrentAttackAfterHit`)
        `crit_allowed`   = `OngoingAttack+0x40`   (`attack[+0x40] &= hitGroup[+0x3c]`)
        `failed_block`   = `OngoingAttack+0x48`   (`FailedBlockIds`, semee par `SetupHitGroup`)

    `ah` = le retour d'`execute_additional_hits` (None si aucun groupe). Quand il existe, c'est LUI
    qui porte l'etat final : les sous-operations de groupe tournent sur la MEME `OngoingAttack` et
    la mutent apres la phase d'arme.

    ⚠ FONCTION D'OBSERVATION : elle ne branche rien. Ce qui BRANCHE, c'est l'appelant qui repasse
    ces trois valeurs a la feuille suivante."""
    src = ah if ah is not None else r
    return {"next_hit_index": int(src["next_hit_index"]),
            "crit_allowed": bool(src["crit_allowed"]),
            "failed_block": set(src["failed_block"] or ())}


def damage_amount_applied(health: int, shield: int, hp_left: int,
                          hp_floor: Optional[int] = None) -> tuple:
    """Le tag `Amount` (TagKey 225) de l'event `UnitDamaged` d'UN coup, et les PV restants APRES.

    `IdunBattle.Core.Services.StreamHelper$$GetDamageTags` ecrit ce tag depuis le champ @+0 de la
    valeur de retour d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` : un accumulateur
    memset a 0 en tete d'`Execute` et alimente par EXACTEMENT DEUX termes, tous deux des retraits
    REELLEMENT appliques -- jamais le degat demande :

        amount  = FillUpStatComponent.Reduce(healthComponent, dar.healthDamage, ignoreMinimum:false)
        amount += ApplyDamageOperation.ReduceShield(unit, dar.shieldDamage)

    et `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` est L'ETAGE QUI BORNE :

        applied = Math.Min(Math.Max(0, damage), Current)                  # @+0x18 = PV courants
        if (!ignoreMinimum && Minimum.HasValue)                           # @+0x1c = Nullable<int>
            applied = Math.Min(Current - Math.Min(Current, Minimum.Value), applied)
        Current -= applied ; <compteur @+0x24> += Math.Max(0, damage - applied) ; return applied

    -- le SURPLUS part dans le compteur @+0x24, PAS dans la valeur de retour. C'est le meme
    accumulateur que le natif grave ensuite dans `ActorStatisticsComponent+0x68`/`+0x6c`
    (`last_hit_damage_taken`, cf. `components.py`), ce qui recoupe la lecture.

    La part ARMURE-POOL n'y entre PAS : `IdunBattle.Core.Services.DamageAppliedResult$$.ctor` recoit
    bien un `armorDamage` mais ne le STOCKE dans aucun champ, et
    `IdunBattle.Core.Services.DamageAppliedResult$$get_Damage` rend `@+0x8 + @+0x4` = bouclier +
    sante. Sans effet mesurable ici : aucun call-site de `_run_hits` ne passe `armor_pool`, donc
    `Damage.armor` vaut 0 sur tous les chemins cables.

    Fonction de MODULE, et pas une expression inline, pour la meme raison que `crit_gate_open` et
    `block_runs_after_evasion` : c'est le point de MUTATION des contre-epreuves. La faire rendre
    `(health + shield, hp_left)` restaure exactement le port d'AVANT #462-r4e-o (le degat BRUT
    rapporte), qui DOIT diverger du live des que la cible meurt pendant la salve."""
    applied = min(max(0, int(health)), hp_left)                # Min(Max(0, damage), Current)
    if hp_floor is not None:
        floor = min(hp_left, int(hp_floor))                    # Min(Current, Minimum.Value)
        applied = min(hp_left - floor, applied)
    return applied + int(shield), hp_left - applied            # + ReduceShield (deja borne)


def overkill_hit_emits(overkilled: bool) -> bool:
    """SITE (A) d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`, lu A L'ENTREE de CHAQUE
    coup -- il PRECEDE toute emission :

        cVar15 = IdunBattle_Entities_UnitExtensions__HasFlag(target, 8);   // UnitFlag.Overkilled
        if (cVar15 != '\\0') {
          ApplyDamageOperation__RecordHitStatistics(...);
          ApplyDamageOperation__AddLeftoverHit(..., 1, 0);
          return param_1;                       // <- TOUT LE RESTE EST SAUTE
        }

    Le `return` precede `On(0x39 = PreDamageTaken)`, la mutation de PV
    (`FillUpStatComponent$$Reduce`), `On(0xf = DamageTaken)`, l'ecriture `lastHitDamageTaken` et
    `On(0x10 = DamageDealt)` -- ET l'evenement `UnitDamaged` qui porte le tag `Amount`
    (`IdunBattle.Core.Services.StreamHelper$$GetDamageTags`). Un coup gate ici ne produit donc
    AUCUNE entree de `per_hit`, alors qu'il reste un coup EXECUTE (index avance, tirages
    consommes : le gate est dans `ApplyDamageOperation`, en AVAL du resolve d'`ExecuteHit`).

    Fonction de MODULE, et pas une expression inline, pour la meme raison que `crit_gate_open` et
    `damage_amount_applied` : c'est le point de MUTATION des contre-epreuves. La faire rendre
    `True` inconditionnellement restaure exactement le port d'AVANT #462-r4e-o-r1 (un event par
    coup restant, `off=[2000, 0, 0, 0]` la ou le natif rend `[2000, 0]`)."""
    return not overkilled


def discarded_hit_emits() -> bool:
    """ETAPE 5 d'`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, branche `discard` --
    la SECONDE porte par laquelle un coup n'emet AUCUN event `UnitDamaged` (#462-r4e-o-r1-r1).

    Meme vice, autre porte que le SITE (A) d'`overkill_hit_emits` : la ou celui-la gate un coup
    a l'entree d'`ApplyDamageOperation$$Execute` (donc en AVAL de la resolution), celui-ci sort
    d'`ExecuteHit` BIEN AVANT -- juste apres la relecture d'`OngoingAttack+0x98` :

        pcVar18 = <Nullable<AttackHit>.HasValue>(attack + 0x98);
        if (*pcVar18 != '\\0') {                          // HasValue
          Nullable<AttackHit>.get_Value(attack + 0x98, &hit);
          if (hit.discard != 0) { return this; }          // <- `this` = OperationResult MEMSET A 0
          ...
        }

    Le `return this` PRECEDE la sub-op **0x42**
    (`IdunBattle.Operations.DealDamageOperation$$Execute`), et c'est celle-la -- et elle seule --
    qui atteint l'application : `DealDamageOperation$$Execute` invoque le slot **0x43**
    (`IdunBattle.Core.Services.OperationProcessor$$ApplyDamage` ->
    `IdunBattle.Operations.ApplyDamageOperation$$Execute`), unique appelant de code du corps qui
    emet l'evenement `UnitDamaged` porteur du tag `Amount`
    (`IdunBattle.Core.Services.StreamHelper$$GetDamageTags`, TagKey 225).
    Chaine LUE de bout en bout au build `rnca9r7q6c` :

        ExecuteHit --(etape 5: discard)--> return          => AUCUN 0x42, AUCUN 0x43, AUCUN event
        ExecuteHit --(sinon)--> 0x42 DealDamage --> 0x43 ApplyDamage --> UnitDamaged{Amount}

    => un coup DISCARDE ne laisse **aucune entree** dans `per_hit`, la ou le port en appendait une
    a 0. Ecart de RAPPORT pur (meme etat, meme somme), donc invisible de tout test d'ETAT -- meme
    signature que #462-r4e-o-r1.

    ⚠ A NE PAS CONFONDRE avec le coup TRANSFERE (`_transferred`, #411), qui relit le MEME champ au
    MEME instant sur `!HasValue` : celui-la, le natif NE le sort PAS. Il pose `damage = 0` et
    poursuit jusqu'a la sub-op 0x42 -> `ApplyDamage` tourne -> l'event EXISTE, a `Amount` 0. La
    distinction est exactement ce que la docstring de
    `test_411r1_transfer_port_offline.py::test_le_transfert_est_teste_AVANT_le_discard` annoncait
    deja (« aucune entree dans `per_hit` » contre « y laisse un 0 ») sans que le port l'applique.

    Fonction de MODULE, sans argument, pour la meme raison que `crit_gate_open` /
    `damage_amount_applied` / `overkill_hit_emits` : c'est le point de MUTATION des contre-epreuves.
    La faire rendre `True` restaure exactement le port d'AVANT #462-r4e-o-r1-r1 (une entree a 0 par
    coup discarde), qui DOIT diverger du live des qu'un `HarlequinsPanoply` jette des coups."""
    return False


def overkill_flag_posted_by_hit(health_damage: int, denied_before: int,
                                hp_start: int, hp_left_before: int, *,
                                over_reduce_before: int = 0,
                                can_be_overkilled: bool = True, is_critical: bool = False,
                                is_force_overkill: bool = False,
                                prevent_overkill: bool = False,
                                hp_floor: Optional[int] = None) -> bool:
    """`IdunBattle.Entities.Components.UnitFlagsComponent$$Add(flags, 8 = Overkilled)` de
    `ApplyDamageOperation$$Execute` : le flag est pose PAR CE COUP-CI ssi
    `dar.didOverkill && UnitExtensions.CanBeOverkilled(target)` -- et `didOverkill` est le retour de
    la surcharge d'INSTANCE d'`IdunBattle.Core.Services.DamagePrediction$$IsOverkill`, inlinee par
    `...$$CalculateDamageOperation`, RELUE VERBATIM au build `rnca9r7q6c` :

        if (!CanBeOverkilled(target)) return false;
        accum = hitDamage + deniedDamage;
        currentHealth = UnitExtensions.GetStat(target, Health = 5);        // PV COURANTS
        if (targetHealthBeforeAttack.HasValue) {
            accum        += (targetHealthBeforeAttack.Value - currentHealth) + unitComponent@+0x24;
            currentHealth = targetHealthBeforeAttack.Value;
        }
        return IsOverkill(currentHealth, accum, isCritical, isForceOverkill,
                          HasFlag(target, 0x13), cfg@+0x30, cfg@+0x34, minimumHealth);

    ⚠ LE TERME QUI RE-AGREGE LES COUPS PRECEDENTS EST `targetHealthBeforeAttack - GetStat(Health)`,
    c'est-a-dire les PV **REELLEMENT RETIRES**, PAS la somme des degats DEMANDES. Les deux
    coincident tant que la cible encaisse tout ; ils divergent des qu'un coup est ECRETE (cible
    morte, plancher `Minimum`). D'ou `hp_left_before` = les PV restants A L'ENTREE de ce coup
    (le `_hp_left` de `_run_hits`, deja borne par `damage_amount_applied`).

    ⚠⚠ ET `unitComponent@+0x24` N'EST PAS UN RESIDU INERTE : le composant que `IsOverkill` va
    chercher (`GetComponent(target, <meme id que le HealthComponent d'ApplyDamageOperation>)`) est
    le `FillUpStatComponent` des PV, et son `+0x24` est l'accumulateur de SUR-REDUCTION que
    `IdunBattle.Entities.Components.FillUpStatComponent$$Reduce` alimente en queue
    (`this[0x24] += Math.Max(0, damage - applied)`) -- nom confirme par
    `...$$ResetOverReduce` (`this+0x24 = 0`). Il vaut donc le degat DEJA GASPILLE
    sur cette cible. C'est `over_reduce_before` (lu AVANT le `Reduce` de ce coup-ci, puisque
    `didOverkill` est calcule en amont, dans `CalculateDamageOperation`).

    ⚠ `ResetOverReduce` n'a AUCUN xref de code, mais il ne faut PAS en conclure que l'accumulateur
    n'est jamais purge (#462-r4e-o-r2 -- c'est l'erreur de -r1) : `...$$FillUp` et `...$$Initialize`
    ecrivent `this[0x24] = 0` EN LIGNE. Cote port, foyer unique `HealthComponent.fill_up`.

    MESURE qui l'etablit (MC1_67/31337, `--hp-target 4000`, rolls `[3583, 3181, 3947, 4012]`) :
    natif `[3583, 417, 0]`, donc flag pose au coup 3. Sans le terme : `3947 + 4000 = 7947 < 8000`
    -> flag au coup 4 -> `[3583, 417, 0, 0]` (ce que le port rendait). Avec :
    `3947 + 4000 + (3181 - 417) = 10711 >= 8000` -> flag au coup 3, bit-exact.

    C'est CE calcul-la qui explique la cardinalite mesuree `live=[2000, 0]` : sur un coup letal qui
    ne DOUBLE pas les PV, `didOverkill` est FAUX au coup letal (accum = degat du coup seul) et ne
    devient VRAI qu'au coup SUIVANT. Le flag est donc pose au 2e coup, et seuls les coups 3+ sont
    gates par le SITE (A).

    IDENTITE REMARQUABLE, et elle VALIDE retrospectivement `AttackDamageOperation._did_overkill` :
    `+0x24` accumule `d - applied` et le terme de PV accumule `applied`, donc leur SOMME sur les
    coups precedents vaut `sum(d)` -- l'accum natif EST le degat DEMANDE cumule de l'attaque. Le
    port n'a donc pas deux modeles concurrents. Les deux formes se separent sur trois axes, tous
    hors d'une serie : un `+0x24` HERITE d'une attaque anterieure (le compteur n'est jamais remis a
    zero ; il faut un revive pour le voir), un SOIN entre deux coups, et le plancher `Minimum` (qui
    coupe l'accumulation... et l'overkill avec). On mirrore la forme NATIVE, pas l'identite."""
    if hp_start is None or hp_left_before is None:
        return False
    accum = (int(health_damage) + (int(hp_start) - int(hp_left_before))
             + int(over_reduce_before or 0))
    return unit_is_overkill(int(hp_start), accum,
                            can_be_overkilled=can_be_overkilled,
                            denied_damage=int(denied_before or 0),
                            prevent_overkill=prevent_overkill,
                            is_critical=bool(is_critical),
                            is_force_overkill=bool(is_force_overkill),
                            target_minimum_health=hp_floor)


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
                  prevent_overkill: bool = False,
                  force_crit: bool = False, hit_index0: int = 0,
                  # #1013 : branche `HasTriggeredAbility(1494 ParagonSpear)` d'
                  # `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage`. Le max-out y est
                  # gate par le champ `isCritical` de l'`AbilityEntities` -> il s'applique PAR
                  # COUP et seulement quand ce coup CRITE, contrairement au max-out de l'effet
                  # 1185 (`_apply_max_out`, bornes degenerees en amont). Defaut False = inchange.
                  max_out_on_crit: bool = False,
                  crit_allowed0: bool = True,
                  crit_chance_after: Optional[int] = None,
                  crit_enabled_after: Optional[bool] = None,
                  crit_chance_at=None, crit_after_index: Optional[int] = None,
                  hit_interceptor=None, failed_block0=None,
                  hp_current: Optional[int] = None,
                  hp_floor: Optional[int] = None,
                  overkilled0: bool = False,
                  can_be_overkilled: bool = True,
                  over_reduce0: int = 0,
                  # #1020-r4 : le CHOKEPOINT `On(0x39 = EventTriggerType.PreDamageTaken)`, appele
                  # DANS la boucle. Cf. le bloc `POSITION DU TIRAGE` de la docstring. `None` =
                  # aucun appelant threade -> l'emission reste au chokepoint de GROUPE
                  # (`_apply_damage_pipeline`), rigoureusement le comportement d'avant.
                  pending_sink=None) -> dict:
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

        `prevent_overkill` (defaut False, #195) = `UnitExtensions.HasFlag(defender, 0x13)`, que le natif
        lit LUI-MEME dans `ApplyTraitDamageLimitsToDamage` (son 5e parametre est `defender`) juste avant
        `IsOverkill` -- l'INVERSE de `force_overkill` : flag pose => JAMAIS d'overkill => le cap Resilient
        MORD. Threade ici pour que la face COMBAT lise le meme argument natif que la face PREDICTION
        (`predict_attack_raw(target_prevents_overkill=)`) : un seul cote cable recreerait un fork.
        ⚠ AXE QUIESCENT AUJOURD'HUI, et c'est une MESURE, pas une supposition : `overkill` n'est consomme
        que par `ApplyResilientTraitDamageLimit`, donc il faudrait une cible portant A LA FOIS le trait
        `Resilient` ET `UnitFlag.PreventOverkill`. Le seul poseur du flag est `FuelledByFury_BlockOverkill`
        (`ultraTitus`), qui n'a pas `Resilient` -- aucun scenario ne distingue donc ce gate sur la face
        COMBAT. Il est porte pour la fidelite, pas parce qu'il a ete confronte.

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

        `hit_interceptor` (defaut None, #366-r1) = les DEUX accroches PER-COUP d'`ExecuteHit(s)` que le
        bus per-attaque du port ne sait pas exprimer (cf.
        `triggers/loki/harlequins_panoply.py::HarlequinsPanoplyHitInterceptor`) :
          * `should_discard(idx)` -- l'etape que `IdunBattle.Operations.AttackDamageOperation$$
            ExecuteHit` execute JUSTE APRES avoir emis `On(6 = PreAttackHit)` / `On(7)` : elle relit
            `OngoingAttack+0x98` (`Nullable<AttackHit>`) et, si son octet `discard` (`+0x08`) est pose,
            fait `return this` sur un `OperationResult` **memset a 0** -- ni degat, ni block, ni
            `EvaluateAfterHitTriggers`. Les tirages DEJA consommes a ce point (le `GetDamage` de tete
            et le `RollCritical`) le restent : c'est pour ca que l'appel se place ICI, entre l'etape
            crit et l'etage de resolution, et pas en tete de coup ;
          * `on_blocked(idx)` -- la branche `param_6 != 0` d'`ADamageOperation$$EvaluateAfterHitTriggers`
            (emission de `On(0x3c = UnitBlocked)`), suivie de `RegisterBlocks`. Appele APRES le split
            combat, comme le natif (l'evenement part de la DERNIERE instruction d'`ExecuteHit`).
        `None` = strict no-op (retro-compat totale : aucun test, aucun tirage, aucune branche modifies).

        `crit_allowed0` (defaut True, #366-r1-crit-multihit) = `OngoingAttack+0x40`
        (`isCriticalDamageAllowed`), l'etat que `IdunBattle.Operations.ADamageOperation$$SetupHitGroup`
        recopie dans `OngoingHitGroup+0x3c` (son 5e parametre PORTE CE NOM dans la metadonnee) et que
        `IdunBattle.Core.OngoingAttack$$.ctor` initialise a **1** dans ses DEUX surcharges.

        `failed_block0` (defaut None, #407) = `OngoingAttack+0x48` (`FailedBlockIds`), le JUMEAU
        BLOCK de `crit_allowed0` -- meme portee (l'ATTAQUE), meme threading. Chaine LUE :
        `IdunBattle.Core.OngoingAttack$$.ctor` cree la liste (`+0x48 = new List<int>()`, NEUVE par
        attaque, comme `+0x40 = 1`) ; `IdunBattle.Operations.ADamageOperation$$GetFailedBlockIds` la
        rend (`HasCurrentAttack() ? GetCurrentAttack().FailedBlockIds : new List<int>()`) ;
        `IdunBattle.Operations.ADamageOperation$$SetupHitGroup` la seme PAR REFERENCE dans
        `OngoingHitGroup+0x60` ; `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` la passe
        a chaque coup (`options[+0x30] = hitGroup[+0x60]`) ; `IdunBattle.Operations.
        ADamageOperation$$RegisterBlocks` y AJOUTE les ids echoues du coup
        (`hitGroup[+0x60].AddRange(result[+0x28])`) ; et `IdunBattle.Core.Services.
        DamageCalculations$$CalculateBlockChances` en EXCLUT les sources (`Contains(failedBlockIds,
        id)` -> `continue`, donc 0 tirage). Comme `AttackDamageOperation$$Execute` ne cree qu'UN
        `OngoingHitGroup` pour la phase d'arme, les coups bonus ET
        `ExecuteAdditionalHitsWithoutDamageProfileType`, et que la voie A PROFIL
        (`ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute` -> nouvelle
        `AttackDamageOperation$$Execute` -> nouveau `SetupHitGroup`) RE-LIT la MEME liste de
        l'`OngoingAttack`, l'exclusion TRAVERSE toutes les sous-operations d'une attaque.
        A THREADER comme `crit_allowed0` (cf. `operations/additional_hits.py`).

        ⚠ POLARITE -- ce n'est PAS le gate crit. Le crit a un booleen d'attaque qui TOMBE au premier
        coup non-crite (`attack[+0x40] &= hitGroup[+0x3c]`) ; le block n'a AUCUN booleen equivalent
        (`AttackDamageOperation$$Execute` ne fait qu'un OR COLLANT `attack[+0x39] |= hitGroup[+0x3e]`,
        jamais lu comme gate). Cote block l'extinction est PAR SOURCE et seulement sur ECHEC : une
        source qui REUSSIT n'entre pas dans la liste (`ApplyRandomBlockDamage` sort en `return` avant
        `AddFailedBlockId`) et reste jouable au coup suivant.

        ⚠ **LE CRIT-ROLL N'EST PAS TIRE A CHAQUE COUP.** Mirror de la boucle
        `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` :

            for i in 0..numHits-1:
                options[+0x29] |= (hitGroup.isCriticalDamageAllowed == 0)   # flag « never crit »
                result = ExecuteHit(...)                                    # gate lu ci-dessus
                ...
                if result[+0x21] == 0:                                      # le coup n'a PAS crite
                    hitGroup.isCriticalDamageAllowed =
                        options[+0x40] != null
                        && options[+0x40].Any(hitIndex => hitIndex == i + 1)
                else:
                    hitGroup[+0x3d] = 1 ; hitGroup[+0x4c] += 1

        soit, avec `options[+0x40]` (= `AttackDamageBehaviour+0xa0`, recopie par
        `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget` dans le message a +0x40)
        **NUL pour l'attaque normale et pour tout ce que le port cable** : le crit-roll s'arrete
        DEFINITIVEMENT au premier coup qui ne crite pas. Le flag `never crit` du message est monotone
        (`|=`), et `IdunBattle.Operations.AttackDamageOperation$$Execute` le propage a l'attaque par
        `attack[+0x40] &= hitGroup[+0x3c]` -- donc l'extinction TRAVERSE les groupes de coups d'une
        meme attaque (coups bonus, groupes de profils additionnels), d'ou le threading de ce parametre.

        Un coup DISCARD (`hit_interceptor`) eteint AUSSI le crit : le natif sort sur un
        `OperationResult` **memset a 0**, donc son octet +0x21 vaut 0 et le recalcul a lieu.

        Le mecanisme est PROPRE A LA FAMILLE ATTACK : `IdunBattle.Operations.AbilityDamageOperation$$
        ExecuteHits` a une boucle PLATE (aucun `|=` sur les options, aucun recalcul) -> gate
        `is_attack_damage_op`.

        `hp_current` / `hp_floor` (defaut None, #462-r4e-o) = PV COURANTS de la cible a l'entree de
        la serie, et son plancher `minimal_health` (`Nullable<int>` @`FillUpStatComponent+0x1c`).
        Ils n'existent QUE pour composer `per_hit`, qui n'est pas le degat demande mais le
        montant que le natif ECRIT dans le tag `Amount` de l'event `UnitDamaged` (cf.
        `_amount_applied`). `None` = pas de PV captes -> aucune borne (comportement d'avant, strict).
        AUCUN autre etage n'en depend : `total`, `per_hit_health`, `rolls` restent le DEMANDE.

        `overkilled0` / `can_be_overkilled` / `over_reduce0` (defaut False/True/0, #462-r4e-o-r1) =
        l'etat du flag `UnitFlag.Overkilled` de la CIBLE a l'entree de la serie
        (`UnitExtensions.HasFlag(target, 8)`), son gate `UnitExtensions.CanBeOverkilled`, et
        l'accumulateur de sur-reduction `FillUpStatComponent+0x24` (cf.
        `overkill_flag_posted_by_hit`). Threades comme `crit_allowed0`/`failed_block0` :
        ce sont des etats de la CIBLE/ATTAQUE que le natif relit a chaque coup, et qui traversent
        les sous-operations (phase d'arme -> groupes de coups additionnels). Le flag ferme le SITE (A)
        (`overkill_hit_emits`) : les coups qui suivent sa pose n'ont PLUS d'entree dans `per_hit`.
        => **`len(per_hit)` n'est plus le nombre de coups EXECUTES** : c'est le nombre d'events
        `UnitDamaged` emis, comme le live. Le compte de coups est `hits_executed`.

        DEUX portes ferment l'emission, et elles sont a des ETAGES DIFFERENTS (#462-r4e-o-r1-r1) :
          * `overkill_hit_emits` -- le SITE (A), a l'entree d'`ApplyDamageOperation$$Execute`
            (donc EN AVAL de la resolution : le coup roule ses tirages, se resout, bloque) ;
          * `discarded_hit_emits` -- l'etape 5 d'`ExecuteHit`, EN AMONT de la sub-op 0x42 (le coup
            ne se resout meme pas : ni degat, ni block, ni `EvaluateAfterHitTriggers`).
        Les deux produisent le MEME ecart observable si on les manque : une entree `per_hit` de
        trop, a somme et etat INCHANGES -- donc invisible de tout test d'ETAT.

        POSITION DU TIRAGE (#1020-r4) -- `pending_sink`. Le chokepoint `On(0x39 =
        EventTriggerType.PreDamageTaken)` vivait au niveau du GROUPE
        (`operations/damage.py::_apply_damage_pipeline`), c.-a-d. APRES que TOUS les coups ont
        tire. Sa GRANULARITE etait deja juste (#1020 : un appel par coup, sur `per_hit_pending`),
        mais sa POSITION dans le flux PRNG ne l'etait pas : un trigger qui tire (`SaviorProtocols`
        et son `Maybe`) consommait ses N tirages APRES les N valeurs de coup, la ou le natif
        entrelace `[valeur i][Maybe i][valeur i+1]...`.

        LU. `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` boucle
        `while (i < numHits)` et appelle `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`
        UNE FOIS PAR TOUR, suivi d'`IdunBattle.Operations.ADamageOperation$$UpdateHitGroupAfterHit`
        / `$$UpdateCurrentAttackAfterHit` : un coup est donc INTEGRALEMENT resolu avant que le
        suivant ne tire quoi que ce soit. Et dans `ExecuteHit`, l'ordre est
        `IdunBattle.Core.HitDamage$$GetDamage` -> `IdunBattle.Core.AttackHit$$.ctor` ->
        `RollCritical` -> `AbilityEntities$$.ctor` -> `On(6)` -> `On(7)` -> sous-operation de split
        -> `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers`. L'emission d'`On(0x39)`
        est dans `IdunBattle.Operations.ApplyDamageOperation$$Execute`, dont
        `IdunBattle.Core.Services.OperationProcessor$$ApplyDamage` est le SEUL appelant (xref
        unique) : elle tombe donc entre le split et l'after-hit -- exactement le point ou
        `per_hit_pending` est renseigne ci-dessous.

        `pending_sink(health, shield)` rend `(kept_health, kept_shield)` ou `None` (pending
        CONSOMME = coup transfere) ; `None` en argument = aucun sink, et le chokepoint de groupe
        emet lui-meme : strictement l'ancien comportement.

        ⚠ **LE CUMUL NE PASSE PAS PAR LE RETOUR DE CETTE FONCTION.** Le dict rendu ci-dessous est
        le CONTRAT DE SORTIE du canal -- toute substitution de `_run_hits` doit pouvoir le rendre
        en entier, et deux gardes existantes le verifient (`test_additional_hits_variant_signatures
        _offline.py`, `test_failed_block_attack_scope_offline.py`). Y ajouter une cle casse ces
        substitutions par `KeyError`. Le cumul vit donc sur le SINK, que l'appelant possede deja.

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
        # #1020 : le couple `(healthDamage, shieldDamage)` DEMANDE de chaque coup qui atteint le
        # point d'ecriture du pending -- c.-a-d. les memes coups que `per_hit` (gate SITE (A) :
        # le natif `return` AVANT de poser `FillUpStatComponent+0x64`). C'est ce que
        # `_apply_damage_pipeline` re-deroule pour emettre `On(0x39 = PreDamageTaken)` PAR COUP,
        # comme le natif, au lieu d'une fois par groupe. Index-aligne sur `per_hit`.
        # PUREMENT ADDITIF : aucune branche existante ne le lit.
        per_hit_pending: list[tuple] = []
        # #R33 : `deniedDamage` du natif = le `previousHitsDeniedDamage` d'`ApplyTraitDamageLimitsTo
        # Damage`, c.-a-d. le rogne cumule AVANT le coup courant. `IdunBattle.Core.Services.
        # DamagePrediction$$IsOverkill` (surcharge d'instance) l'AJOUTE au degat compare aux PV de depart
        # -> il doit descendre jusqu'au chokepoint de mort, PAR COUP. On snapshot `_rogne` a l'entree de
        # chaque coup (index-aligne sur `crits` / `per_hit_health`). Purement additif.
        denied_before: list[int] = []
        # ids de sources de block AYANT ECHOUE (#72) -- `OngoingAttack+0x48` (`FailedBlockIds`),
        # seme PAR REFERENCE dans `OngoingHitGroup+0x60` par `ADamageOperation$$SetupHitGroup` :
        # l'accumulation traverse les coups ET les sous-operations de l'ATTAQUE (#407, cf. docstring).
        failed_block: set = set(failed_block0 or ())
        # #91 : réduction CAPÉE défenseur (GuardianOrganism) = scalaire FLAT pré-évalué (natif IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers) où
        # D = CurrentDamage = CENTRE des bornes réduites (post pierce/armure/%-mods) -> soustrait IDENTIQUE à
        # chaque coup, PAS 33%×valeur-tirée (confirmé LIVE #91). Un flat par type de coup (non-crit/crit).
        # #920-r1 : le helper ARRONDIT (`PercentageOf` demi-vers-le-PAIR), il ne tronque plus — c'était
        # le `DELTA [1, 1, 1, 1]` du bras `--porteur-defenseur` de `probe_920`.
        _capped_flat_nc = capped_reduction_flat((hit_nc.min + hit_nc.max) / 2.0, capped_reductions) \
            if capped_reductions else 0
        _capped_flat_cr = capped_reduction_flat((hit_cr.min + hit_cr.max) / 2.0, capped_reductions) \
            if capped_reductions else 0
        _rogne = [0]        # #67 : rogne cumule des cellules MIN des coups precedents (porte overkill)
        # #366-r1-crit-multihit : `OngoingHitGroup+0x3c` = `isCriticalDamageAllowed`, seme par
        # `SetupHitGroup` depuis `OngoingAttack+0x40` et eteint en fin de coup par la boucle
        # d'`AttackDamageOperation$$ExecuteHits` des qu'un coup ne crite pas (cf. docstring).
        _crit_allowed = [bool(crit_allowed0) if is_attack_damage_op else True]
        # #889-r1 : memo de `crit_chance_at(idx)` -- le natif RE-EVALUE le canal a chaque coup, mais
        # rien ne change entre deux coups de MEME index, donc un appel par index distinct suffit.
        _crit_at_cache: dict = {}
        # Index auquel l'appelant a MESURE `crit_chance_after`. Defaut = `hit_index0 + 1`, la valeur
        # que les trois vecteurs passent a `_crit_params` pour leur relecture post-`On(6)`.
        crit_after_index = int(hit_index0) + 1 if crit_after_index is None else int(crit_after_index)
        # #462-r4e-o : PV RESTANTS, decroissants COUP PAR COUP. Le natif applique un coup a la fois
        # (`DamageAppliedResult` porte un `hitIndex` @+0x14, `IdunBattle.Core.Services.
        # DamageAppliedResult$$.ctor`), donc la borne de `_amount_applied` se resserre a chaque coup.
        _hp_left = [None if hp_current is None else max(0, int(hp_current))]
        # #462-r4e-o-r1 : `UnitFlag.Overkilled` de la CIBLE, relu PAR COUP par le SITE (A). Il est
        # POSE ici (etat de serie) et non sur le composant : le port ne pose le vrai flag qu'au
        # chokepoint de mort (`_fire_death_if_killed`), APRES la serie -- or le natif le pose au
        # milieu, et c'est precisement ce qui coupe l'emission des coups suivants.
        _overkilled = [bool(overkilled0)]
        _ovk_at = [None]            # index (0-based dans CETTE serie) du coup qui a pose le flag
        _suppressed = [0]           # coups gates par le SITE (A) : executes, mais AUCUN event emis
        # `FillUpStatComponent+0x24` -- l'accumulateur de SUR-REDUCTION, seme par l'etat du
        # composant a l'entree de la serie (il traverse coups, sous-operations et attaques ; il
        # n'est purge que par `...$$FillUp`/`...$$Initialize`, donc par un SOIN, une REPARATION,
        # une RESURRECTION ou un spawn -- jamais par un REVIVE, cf. #462-r4e-o-r2). Suivi ICI parce que
        # `IsOverkill` le lit PAR COUP, la ou `HealthComponent.reduce` ne l'ecrit qu'au chokepoint.
        _over_reduce = [int(over_reduce0 or 0)]

        def _amount_applied(dmg: Damage) -> int:
            """Le tag `Amount` de CE coup + deplacement des PV restants (cf. `damage_amount_applied`)
            + la queue de `Reduce` (`this[0x24] += Max(0, damage - applied)`, sautee sous plancher)."""
            if _hp_left[0] is None:
                return dmg.get_total()
            before = _hp_left[0]
            amount, _hp_left[0] = damage_amount_applied(
                dmg.health, dmg.shield, _hp_left[0], hp_floor)
            if not (hp_floor is not None and int(hp_floor) > 0):
                _over_reduce[0] += max(0, int(dmg.health) - (before - _hp_left[0]))
            return amount

        def _roll_crit(idx: int) -> bool:
            """Le crit d'UN coup, gate compris -- foyer UNIQUE des deux branches de `_one_hit`.
            `never crit` (message +0x29) est arme des que `isCriticalDamageAllowed` est tombe :
            `ExecuteHit` rend alors `isCrit = 0` **sans appeler `RollCritical`** (0 tirage).

            #522-r1 -- LA CRIT CHANCE N'EST PAS LA MEME AU COUP 0 ET AUX SUIVANTS, et c'est LU :
            `IdunBattle.Core.Services.DamagePrediction$$RollCritical` relit
            `UnitExtensions.GetStat(attacker, 0x9 = CritChance, 0 = Current)` **a chaque appel**,
            et `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` appelle `RollCritical`
            **AVANT** d'emettre `On(PreAttackHit = 6)` (l'ordre du decompile est : slot 0xad
            profil -> `AttackHit..ctor` -> **slot 0xa `RollCritical`** -> `AbilityEntities..ctor`
            -> `EnqueueOperation(6)` -> `EnqueueOperation(7)` -> sub-op 0x42 -> after-hit).
            `ExecuteHits` boucle sur `ExecuteHit`, donc un stat-mod pose par `On(6)` du coup 0
            mord sur les coups SUIVANTS de la MEME salve, jamais sur le coup 0.

            `crit_chance_after` / `crit_enabled_after` = les valeurs RELUES **apres** l'event ;
            `None` = inchangees, donc strict no-op pour tout appelant qui ne les passe pas.
            `idx` est l'index CONTINU de l'attaque (`hit_index0 + i`), donc `idx == 0` est
            exactement l'`IsFirstHitInSeries` natif -- un groupe de coups additionnels
            (`hit_index0 > 0`) est deja au-dela, et prend donc les valeurs d'apres.

            #889-r1 -- DEUX AXES ETAIENT CONFONDUS DANS UN SEUL MECANISME, et ils sont
            INDEPENDANTS :

              * axe TEMPOREL (`crit_chance` / `crit_chance_after`) : `On(PreAttackHit = 6)` est
                emis UNE FOIS, entre le coup 0 et les suivants -- deux etats suffisent, et c'est
                juste ;
              * axe INDEX (`crit_chance_at`) : `IdunBattle.Core.Services.DamagePrediction$$
                RollCritical(this, attaquant, defenseur, abilityOrEffect, **hitIndex**)` passe
                l'index a `GetCritChanceBonusFromEffects`, qui le pose dans l'`AbilityEntities`
                qu'il construit -- le noeud `CurrentHitIndex()` le relit donc a CHAQUE coup, avec
                N valeurs possibles.

            Rabattre l'axe INDEX sur l'axe TEMPOREL n'est exact que pour une serie de 1 ou 2
            coups. `crit_chance_at(idx)` rend `(chance, enabled)` a l'index demande.

            ⚠ BORNE LUE, qui limite la reparation a la CHANCE : `CalculateCriticalDamage` appelle
            `GetCritDamageBonusFromEffects(this, attaquant, defenseur, abilityOrEffect)` -- QUATRE
            arguments, **pas de `hitIndex`**. Le canal crit-DEGAT n'est donc pas index-dependant,
            et `crit_damage` n'est pas retouche ici.

            Le rappel n'a lieu QUE pour un index que les deux points de mesure ne couvrent PAS :
            `crit_after_index` est l'index auquel l'appelant a effectivement mesure
            `crit_chance_after` (`hit_index0 + 1`), et le coup 0 garde `crit_avant`. Toute serie de
            1 ou 2 coups -- c'est-a-dire tout ce que le corpus mesure -- ne declenche donc AUCUN
            rappel et reste BIT-IDENTIQUE, surcout compris. Memoise : au plus un appel par index
            distinct."""
            if force_crit:                      # options+5 -> le natif SAUTE RollCritical
                return True
            if not crit_gate_open(_crit_allowed[0], is_attack_damage_op):
                return False                    # flag « never crit » arme -> 0 tirage
            cc, en = crit_chance, crit_enabled
            if idx != 0:                        # coups 1+ : `GetStat(9)` RELU apres `On(6)`
                if crit_chance_after is not None:
                    cc = crit_chance_after
                if crit_enabled_after is not None:
                    en = crit_enabled_after
                if crit_chance_at is not None and idx != crit_after_index:
                    if idx not in _crit_at_cache:
                        _crit_at_cache[idx] = crit_chance_at(idx)
                    _cc_i, _en_i = _crit_at_cache[idx]
                    if _cc_i is not None:
                        cc = _cc_i
                    if _en_i is not None:
                        en = _en_i
            return roll_critical(rng, cc) if en else False

        def _limits_scalar(value: int) -> int:
            """Etage LIMITES en cap SCALAIRE sur la valeur DONNEE (cellule degeneree du core, mode 2).
            Cumule le rogne (`_rogne`, param_12 de la porte overkill) et calcule `IsOverkill` depuis
            CETTE cellule -- mirror `IdunBattle.Core.Services.DamagePrediction$$ApplyTraitDamageLimitsToDamage(2, &v, &v, ...)`."""
            if limits is None or value <= 0:
                return value
            rem = max(0, limits_hp - total)
            ovk = force_overkill or (compute_prediction_overkill(rem, limits_hp, value, p12=_rogne[0],
                                                                 suppress=prevent_overkill)
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

        def _one_hit_tail(idx: int, crit: bool, roll: int,
                          guaranteed_block: bool = False) -> bool:
            """Queue PARTAGÉE d'un coup : split combat (sub-op 0x42) + comptabilité + Maybe GetStuckIn.
            #72 : mirror `IdunBattle.Core.Services.DamageCalculations$$CalculateBlockChances(param_4=failedList) -> une source de block
            AYANT ECHOUE a un coup precedent est EXCLUE des coups suivants (Contains(failedList, id)) ;
            une source qui REUSSIT reste jouable (ApplyRandomBlockDamage return sans AddFailedBlockId).
            Donc une source est jouee chaque coup JUSQU'A son 1er echec, puis plus (aucun tirage). Preuve
            live (orksNob BeastSlayer chance=10) : hit1 succes + hit2 echec -> 0 roll hits 3-6 = 8 tirages."""
            nonlocal total, shield, armor_pool, shield_dmg, armor_dmg, did_crit, did_block, did_evade
            hit_block = ([s for s in block_sources if s.block_id not in failed_block] or None
                         ) if block_sources else None
            # #407-r1 : plus de `evasion_branch` (le flag XOR n'existe pas dans le natif, cf.
            # `services/damage_combat.calculate_damage_operation`). `evasion_chance` n'est pas
            # passe : `CalculateEvasionChance` = `GetStat(defender, 0xf)` et AUCUNE unite n'arrive
            # en bataille avec cette stat non nulle (5 voies, `probe_407r1_evasion_carriers.py`)
            # -> 0 tirage, degat inchange. Le jour ou un porteur apparait, c'est ICI qu'il se cable.
            dmg: Damage = calculate_damage_operation(
                roll, shield=shield, armor_pool=armor_pool, armor_pct=armor_pct,
                block_sources=hit_block, guaranteed_block=guaranteed_block, rng=rng)
            failed_block.update(dmg.failed_block_ids or [])
            shield = max(0, shield - dmg.shield)
            armor_pool = max(0, armor_pool - dmg.armor)
            # #462-r4e-o-r1 -- SITE (A) d'`ApplyDamageOperation$$Execute`, evalue PAR COUP (le natif
            # appelle `Execute` une fois par coup). Etat lu A L'ENTREE du coup : le flag pose PAR ce
            # coup-ci ne le gate pas lui-meme (le `UnitFlagsComponent.Add(8)` precede l'emission dans
            # le MEME `Execute`), il gate les SUIVANTS.
            if overkill_hit_emits(_overkilled[0]):
                _hp_entry = _hp_left[0]           # PV restants AVANT ce coup (arg d'`IsOverkill`)
                _or_entry = _over_reduce[0]       # `+0x24` AVANT le `Reduce` de ce coup
                per_hit.append(_amount_applied(dmg))  # `Amount` de l'event = retraits REELS (borne PV)
                # #1020 -- le pending POSE par ce coup : les champs `+0x04 healthDamage` /
                # `+0x08 shieldDamage` du `DamageAppliedResult` que le natif ecrit dans
                # `FillUpStatComponent+0x64`. Le DEMANDE, pas l'applique : le natif construit le
                # resultat AVANT `Reduce`, et c'est ce montant-la que `TransferDamageOperation$$
                # GetDamage` empaquette quand il le consomme.
                per_hit_pending.append((int(dmg.health), int(dmg.shield)))
                # #1020-r4 -- LE CHOKEPOINT `On(0x39)` DE CE COUP, JOUE ICI. Position LUE dans
                # `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` : la sous-operation qui
                # calcule le split (celle dont le port est `calculate_damage_operation`, appelee
                # quelques lignes plus haut) precede immediatement
                # `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` -- et c'est
                # elle qui atteint `IdunBattle.Core.Services.OperationProcessor$$ApplyDamage`, SEUL
                # appelant d'`IdunBattle.Operations.ApplyDamageOperation$$Execute` (xref unique).
                # Donc, PAR COUP : [valeur + crit + spread + block] -> [emission 0x39] -> [after-hit],
                # puis `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` reboucle sur le
                # coup suivant. Un trigger qui consomme du PRNG (le `Maybe` de `SaviorProtocols`)
                # tire donc AVANT la valeur du coup i+1, jamais apres toute la salve.
                # ⚠ Le cumul est PORTE PAR LE SINK, jamais publie dans le dict rendu plus bas :
                # ajouter une cle au retour ELARGIT le CONTRAT DE SORTIE de ce canal, et toute
                # substitution de `_run_hits` restee en arriere leve alors `KeyError` (deux gardes
                # existantes l'ont attrape, cf. `damage.py::_PreDamageTakenSink`).
                if pending_sink is not None:
                    pending_sink(int(dmg.health), int(dmg.shield))
                # `UnitFlagsComponent$$Add(flags, 8)` : `dar.didOverkill && CanBeOverkilled(target)`.
                if not _overkilled[0] and overkill_flag_posted_by_hit(
                        dmg.health, denied_before[-1] if denied_before else 0,
                        hp_current, _hp_entry, over_reduce_before=_or_entry,
                        can_be_overkilled=can_be_overkilled, is_critical=crit,
                        is_force_overkill=force_overkill, prevent_overkill=prevent_overkill,
                        hp_floor=hp_floor):
                    _overkilled[0] = True
                    _ovk_at[0] = len(per_hit_health)      # index de CE coup dans la serie
            else:
                # Le natif RETOURNE avant `Reduce` : ni PV mutes, ni event. Il fait quand meme
                # `RecordHitStatistics` + `AddLeftoverHit(..., 1)` -- ce dernier est porte par
                # `record_left_over_damages`, qui lit `per_hit_health` (INCHANGE ci-dessous).
                _suppressed[0] += 1
            per_hit_health.append(dmg.health)     # part PV SEULE du coup (hors bouclier/armure-pool)
            # `total` reste le DEMANDE de TOUS les coups (comme `per_hit_health` / `rolls`). Le natif
            # n'applique rien pour un coup gate, mais le port ne mute les PV qu'au chokepoint de
            # groupe (`thc.reduce(total)`), qui BORNE deja aux PV restants -- et le flag n'est jamais
            # pose sans que la cible soit morte (il exige `accum >= 2 x PV de depart`). L'ecart est
            # donc structurellement INERTE sur l'etat ; il ne l'etait PAS sur le RAPPORT (`per_hit`).
            total += dmg.health
            shield_dmg += dmg.shield
            armor_dmg += dmg.armor
            did_crit |= crit
            did_block |= dmg.did_block
            did_evade |= dmg.did_evade
            # #366-r1 : `IdunBattle.Operations.ADamageOperation$$EvaluateAfterHitTriggers` branche
            # `param_6 != 0` -> `On(0x3c = UnitBlocked)`, PUIS `RegisterBlocks` (le compteur
            # `ActorStatisticsComponent+0x8c`). PAR COUP, comme le natif, et AVANT le Maybe GetStuckIn
            # (qui vit sur l'after-hit `On(8)`, emis APRES `On(0x3c = UnitBlocked)` par la meme fonction).
            if hit_interceptor is not None and dmg.did_block:
                hit_interceptor.on_blocked(idx)
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
            denied_before.append(_rogne[0])       # #R33 : rogne des coups PRECEDENTS (avant ce coup)

            def _discarded(crit_flag: bool) -> bool:
                """#366-r1 -- l'etape 5 d'`ExecuteHit` : `if (attackHit.discard != 0) return this;` sur
                un `OperationResult` MEMSET A 0. Appelee APRES le `GetDamage` de tete et le
                `RollCritical` (donc leurs tirages sont deja consommes) et AVANT le slot 4/8 et la
                sub-op 0x42 (donc AUCUN de ces tirages-la ne l'est). Le coup est compte (l'index
                avance, `ExecuteHits` fait `i++`) mais n'inflige RIEN et ne bloque RIEN.

                #462-r4e-o-r1-r1 -- et il n'EMET RIEN non plus. La sub-op 0x42
                (`IdunBattle.Operations.DealDamageOperation$$Execute`) est le SEUL chemin qui
                atteint le slot 0x43 (`IdunBattle.Core.Services.OperationProcessor$$ApplyDamage`
                -> `IdunBattle.Operations.ApplyDamageOperation$$Execute`), donc l'evenement
                `UnitDamaged` porteur du tag `Amount`. Le `return this` la PRECEDE => AUCUNE entree
                dans `per_hit` (foyer/point de mutation : `discarded_hit_emits`). `crits` /
                `rolls` / `per_hit_health` restent FULL-LENGTH -- ils comptent les coups EXECUTES,
                et `hits_executed = len(per_hit_health)` en depend."""
                if hit_interceptor is None or not hit_interceptor.should_discard(idx):
                    return False
                crits.append(crit_flag)
                rolls.append(0)
                if discarded_hit_emits():     # natif : FAUX -- `ExecuteHit` sort AVANT la 0x42
                    per_hit.append(0)
                per_hit_health.append(0)
                return True

            def _transferred(idx: int) -> bool:
                """#411 -- la branche JUMELLE de `_discarded`, au MEME point d'`ExecuteHit` (la
                relecture d'`UnitComponent+0x98` juste apres l'emission d'`On(6)` puis `On(7)`),
                mais sur `!HasValue` au lieu de `HasValue && discard` : le `PendingHit` a ete
                EFFACE par `IdunBattle.Operations.TransferHitOperation$$Execute`.

                DIFFERENCE CAPITALE avec le discard : le natif NE SORT PAS. Il pose `damage = 0`,
                arme `msg[+0x29]`, construit `critInfo = {0,0,0}` et `DealDamageInfo[+0x1D] = 1`,
                puis appelle la sub-op `0x42` NORMALEMENT. D'ou les trois consequences portees :
                  * le resolve slot 8 tourne sur une cellule `[0,0]` -> **1 tirage quand meme**
                    (`IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`
                    n'a AUCUN gate de largeur -- meme raison que case-221) ;
                  * `CalculateDamageOperation` prend la route `guaranteed_block` -> **0 tirage**
                    de block, **0** d'evasion, `didBlock = 1` pose en dur (cf.
                    `services/damage_combat.py`) ;
                  * le coup rejoint le meme label que le chemin « n'a PAS crite », donc il eteint
                    `OngoingHitGroup+0x3c` comme n'importe quel coup non-crite.

                L'APPEL LUI-MEME lance l'attaque de transfert sur le porteur (le natif l'execute
                DANS le dispatch d'`On(7)`, donc AVANT le resolve du coup courant) : l'ordre des
                tirages en depend.

                ⚠ ORDRE vis-a-vis de `_discarded` : la COLLISION `discard` x `transfer` sur un
                MEME coup est tranchee par le natif en faveur du TRANSFERT -- `On(6)` pose
                `discard = 1` dans le Nullable, `On(7)` EFFACE le Nullable, et la relecture teste
                `HasValue` en premier : elle voit donc `!HasValue`. D'ou l'appel a `_transferred`
                AVANT `_discarded`. Ecart nomme : quand le transfert gagne, le port n'execute pas
                le behaviour de pose du discard (qui consommerait le marqueur 1227). Cas de bord
                JAMAIS exerce -- il exige un porteur `HarlequinsPanoply` et un porteur `DrawFire`
                sur le meme coup."""
                return hit_interceptor is not None and hit_interceptor.should_transfer(idx)

            if post_roll is not None:
                # VECTEUR ABILITY bounds-mode (roll-then-reduce) — ordre natif ExecuteHit :
                # (1) VALEUR = tirage BRUT dans les bornes config (GetDamage-top, struct min<max).
                raw = hit_nc.get_damage(rng)
                # (2) crit-roll APRÈS le tirage de valeur (gate cc<1 -> 0 tirage, cf. bloc ci-dessus).
                # `force_crit` = flag options+5 : le natif SAUTE `RollCritical` -> crit acquis, 0 tirage.
                crit = _roll_crit(idx)
                if _transferred(idx):             # #411 : face ABILITY (NON CONFRONTEE, cf. §7)
                    _crit_allowed[0] = False
                    crits.append(crit)
                    roll = rng.next_internal(0, 1) if is_attack_damage_op else 0
                    rolls.append(roll)
                    return _one_hit_tail(idx, crit, roll, guaranteed_block=True)
                if _discarded(crit):              # `ExecuteHit` etape 5 (cf. `_discarded`)
                    _crit_allowed[0] = False      # OperationResult memset 0 -> +0x21 = 0
                    return False
                if not crit:
                    _crit_allowed[0] = False      # `ExecuteHits` : recalcul -> Any(null) = false
                crits.append(crit)
                if crit:
                    # #1013 : `ExecuteHit` intercale ICI, et SEULEMENT sur un coup critique,
                    #   if (IsAttackMaxOutDamage(attacker, entities, state)) damage = <max> ;
                    # `IdunBattle.Entities.UnitExtensions$$IsAttackMaxOutDamage` rend, pour un
                    # porteur de `1494 ParagonSpear`, le champ `isCritical` de l'`AbilityEntities`
                    # -- d'ou le gate `if crit` et non un max-out inconditionnel (celui de l'effet
                    # `1185 WeaverOfFate_MaxOutDamage`, lui, passe par `_apply_max_out` en amont et
                    # degenere DEJA les deux jeux de bornes). Le tirage a bien eu lieu et reste
                    # consomme : le natif l'ECRASE, il ne l'evite pas.
                    if max_out_on_crit:
                        raw = int(hit_nc.max)
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
            crit = _roll_crit(idx)
            if _transferred(idx):                 # #411 : `ExecuteHit` etape 5, branche !HasValue
                _crit_allowed[0] = False          # meme label que « n'a pas crite »
                crits.append(crit)
                roll = rng.next_internal(0, 1) if is_attack_damage_op else 0
                rolls.append(roll)
                return _one_hit_tail(idx, crit, roll, guaranteed_block=True)
            if _discarded(crit):                  # `ExecuteHit` etape 5 (cf. `_discarded`)
                _crit_allowed[0] = False          # OperationResult memset 0 -> +0x21 = 0
                return False
            if not crit:
                _crit_allowed[0] = False          # `ExecuteHits` : recalcul -> Any(null) = false
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
                _ovk = force_overkill or (compute_prediction_overkill(_rem, limits_hp, lo_pre,
                                                                      p12=_rogne[0],
                                                                      suppress=prevent_overkill)
                                          if limits_hp > 0 else False)
                lo = apply_trait_damage_limits_to_damage(lo_pre, current_health=_rem,
                                                         overkill=_ovk, **limits)
                hi = apply_trait_damage_limits_to_damage(hi_pre, current_health=_rem,
                                                         overkill=_ovk, **limits)
                _rogne[0] += max(0, lo_pre - lo)
                roll = rng.next_internal(lo, hi + 1)   # TOUJOURS 1 tirage (mirror slot 8, sans gate)
                rolls.append(roll)
            else:
                # case-221 : MEME etage que la branche `limits` mode 1 ci-dessus (ligne
                # `rng.next_internal(lo, hi + 1)`), donc MEME fonction native -- le slot 8
                # `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`, qui appelle
                # `Next(min, max + 1)` SANS gate largeur-1 (decompile relu : le corps ne teste que le
                # PRNG, il n'y a aucun `if (min == max) return min`). `IdunBattle.Core.HitDamage$$GetDamage`
                # a bien ce gate, mais c'est l'AUTRE etage (le jet dans les bornes BRUTES, en tete
                # d'`ExecuteHit`, cf. la branche `post_roll is not None`) et l'autre famille
                # (`AbilityDamageOperation$$ExecuteHits` l'appelle DIRECTEMENT, sans resolve derriere).
                # Les deux ne different QUE sur une cellule DEGENEREE : le port y perdait un tirage.
                # Strictement NO-OP des que `hd.min < hd.max` (meme appel, meme valeur).
                roll = (rng.next_internal(int(hd.min), int(hd.max) + 1) if is_attack_damage_op
                        else hd.get_damage(rng))
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
                # #1020 : `(healthDamage, shieldDamage)` par coup ATTEIGNANT le point d'ecriture du
                # pending `FillUpStatComponent+0x64` -- meme population que `per_hit`.
                "per_hit_pending": per_hit_pending,
                "per_hit_health": per_hit_health, "denied_before": denied_before,
                "bonus_hits": base_bonus,
                # #462-r4e-o-r1 -- le compte de coups EXECUTES (un par tour de `ExecuteHits`, coups
                # bonus GetStuckIn compris). Distinct de `len(per_hit)` des qu'un coup est gate par
                # le SITE (A) : celui-la s'execute mais n'emet rien.
                "hits_executed": len(per_hit_health),
                "overkill_suppressed": _suppressed[0],
                # Verdict `didOverkill` de la SERIE, au sens natif : vrai des qu'UN coup a pose
                # `UnitFlag.Overkilled`. `None` = non calculable ici (aucun PV capte, `hp_current`
                # absent) -> l'appelant retombe sur `AttackDamageOperation._did_overkill`.
                "overkilled": (None if hp_current is None else bool(_overkilled[0])),
                "overkill_at_hit": _ovk_at[0],
                # `FillUpStatComponent+0x24` en SORTIE de serie (mirror ; l'ECRITURE sur le
                # composant reste `HealthComponent.reduce`, foyer natif de `Reduce`).
                "over_reduce": _over_reduce[0],
                # case-209 : `param_5[0x98]` du message d'`IdunBattle.Operations.
                # ApplyDamageOperation$$Execute` = la BASE nominale du coup, ce que poussent les
                # call-sites (A)/(B) d'`AddLeftoverHit` quand le coup tombe sur un cadavre. MESUREE
                # egale au MILIEU de la cellule reduite (2609 pour `(2087, 3131)`, invariant sur
                # deux seeds aux jets differents, cf. `operations/left_over_damage.py`).
                # `post_roll` non nul = mode roll-then-reduce (ability) : `hit_nc` porte alors les
                # bornes BRUTES et le milieu n'est PAS la base reduite -> None (le consommateur
                # degrade en « pas de report », plutot qu'un montant invente).
                # `post_roll` non nul = mode roll-then-reduce (ability) : `hit_nc` porte les bornes
                # BRUTES, la base nominale REDUITE est donc `post_roll(milieu)` -- meme reduction que
                # celle appliquee a chaque jet, appliquee au centre de la cellule brute.
                "base_nominal": ((int(hit_nc.min) + int(hit_nc.max)) // 2 if post_roll is None
                                 else int(post_roll((int(hit_nc.min) + int(hit_nc.max)) // 2))),
                # R6-b' : `currentAttack+0x30` APRES cette serie — `UpdateCurrentAttackAfterHit`
                # incremente APRES CHAQUE `ExecuteHit`, coups bonus compris.
                "next_hit_index": hit_index0 + hits + base_bonus,
                # #366-r1-crit-multihit : `attack[+0x40] &= hitGroup[+0x3c]` en fin
                # d'`AttackDamageOperation$$Execute` -- a THREADER dans la serie suivante de la MEME
                # attaque (`operations/additional_hits.py`), comme `next_hit_index`.
                "crit_allowed": _crit_allowed[0],
                # #407 : `OngoingAttack+0x48` (`FailedBlockIds`) -- meme threading que `crit_allowed`,
                # la liste etant PARTAGEE PAR REFERENCE avec `OngoingHitGroup+0x60`.
                "failed_block": failed_block}
