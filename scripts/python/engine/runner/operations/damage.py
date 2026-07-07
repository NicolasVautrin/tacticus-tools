"""Operations de dégât — `IdunBattle.Operations.AttackDamageOperation` (gqfc5mff6c).

Tranche DAMAGE. **Palier 1 (porté + validé ici) : le TIRAGE de dégât par coup**
(`HitDamage.GetDamage`), bit-exact via le MT porté (`engine/runner/prng.py`).

Chaîne native RE'd (VA citées) :

    AttackDamageOperation.Execute        @180e60c70
      → GetAttackHits                    @180e613d0   (nb de coups ; 1 par défaut)
      → SetupHitGroup : construit le `HitDamage` {Min,Max} PAR COUP = plage RÉDUITE
        (perçage/armure/modifiers appliqués aux bornes base±spread AVANT le tirage)
      → ExecuteHits (boucle nbHits)      @180e607b0
          → ExecuteHit (PAR COUP)        @180e5eff0
              1. RollCritical (IDamagePrediction slot 0xa → DamageCalculations.RollCritical
                 @1810057b0 → NextBool(critChance))  ← 1er conso RNG SI cc≥1 (tirage PAIR)
              2. HitDamage.GetDamage     @181007bf0   ← spread DANS la plage réduite SÉLECTIONNÉE
                 (crit → bornes eff_attack=attack+critDamage ; sinon non-crit) — tirage IMPAIR
              3. roll block (composant 10)                        — palier 2 (non porté)
              4. split bouclier/armure-pool (CalculateDamageOperation) — palier 3
              5. EvaluateAfterHitTriggers (cascade)               — palier 4

**Ordre RNG CONFIRMÉ (genrand brut live, necroDestroyer CC=100)** : par coup =
RollCritical (tirage PAIR) PUIS spread (tirage IMPAIR) = 2 tirages/coup. À cc=0,
RollCritical ne tire RIEN (NextBool gate cc≥1) → 1 tirage/coup → rétro-compat exacte
du multi-coups non-crit (validé 18/18). Le spread d'un coup non-crit propre reste le
tirage RNG #1 — base de la validation bit-exact (`tests/engine/runner/test_damage_roll_live.py`).

**CRIT (combat ≠ prédiction)** : le crit du COMBAT s'ajoute à la BASE D'ATTAQUE AVANT
spread/perçage (`GetBaseDamageFix64` param_4=isCrit ⇒ `eff_attack=attack+critDamage`,
même pipeline) — PAS l'`ApplyCritDamage` post-réduction (base+bonus) de la PRÉDICTION.
Confirmé bit-exact : crit per-coup [675,1012] = non-crit [435,652]×(906+500)/906, et
next_internal(675,1013) aux tirages impairs = live [932,882,967,867,961,955] à l'unité.

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
from ...services.damage_modifiers import apply_all_modifiers
from ...services.battle_query import are_tiles_adjacent
from ...services.attack_hits_formula import attack_hits_with_modifiers
from ...entities.stats import StatType
from ..prng import IntBasedMersenneTwister
from ..state import State
from ..components import (StatsComponent, HealthComponent, PositionComponent, UnitComponent,
                         ShieldComponent)
from ..damage_model import (select_weapon, select_weapon_pierce, attacker_modifiers,
                            defender_modifiers, build_hits_board, apply_elevation_bonus)
from ...entities.effects import (hits_bonus_from_effects, crit_chance_bonus_from_effects,
                                 crit_damage_bonus_from_effects)


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
        from .triggers import after_death_triggers, is_overkill
        return after_death_triggers(state, target_id, attacker_id,
                                    overkill=is_overkill(hp_before, damage))

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
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None, is_ranged=_ranged)
        # #58 : feuille positionnelle ELEVATION (+surplomb) ajoutee au `mods` de l'attaquant, comme la
        # prediction (service PARTAGE `calculate_elevation_bonus_modifier` de DamageCalculations ; positions
        # REELLES depuis l'ECS/board).
        apply_elevation_bonus(state, mods, attacker_id, target_id)
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
            hits = attack_hits_with_modifiers(
                weapon_hits=whits, extra_hits=ctx.stat(StatType.EXTRA_HITS),
                extra_hits_melee=ctx.extra_hits_melee,
                attacker_effects=active, trait_objects=ctx.trait_objects(),
                target_effects=_tgt_eff, aura_sources=_auras, board=_board,
                is_melee=not _ranged, damage_profile=_profile,
                include_bonus_hit_behaviours=False)  # combat: GetStuckIn = behaviour chance-gate non porte (BITE 2)
        else:                                     # positions manquantes -> base seule (pas de GetStuckIn/aura)
            hits = max(1, whits + ctx.stat(StatType.EXTRA_HITS) + hits_bonus_from_effects(active))
        tsc = tgt.get_component(StatsComponent)
        # armure = GetStat(16) DÉJÀ effet-inclusif : les bonus +armor d'effet sont des StatModifications
        # (aucun `GetArmorBonusFromEffects` séparé n'existe — seuls crit/hits ont une couche calc-time) →
        # cuits dans GetStat → dans le combatSnapshot → dans ctx.fixed_armor. Rien à sommer en plus.
        armor = tsc.ctx.stat(StatType.FIXED_ARMOR) if tsc is not None else 0
        # BLOCK (cible) — sources issues de `GetMultiValueStat(target, 7)` (CalculateBlockChances@181002350) :
        # les bonus +block d'effet sont aussi des StatModifications (pas de couche calc-time) → déjà dans
        # GetStat(7/8) → ctx.block_chance/block_damage. Le patch BC --block-target = item I_Block équivalent.
        # chaque entrée {chance → blockDmg(GetBlockDamageForBlockChance)}. Notre patch BC (BlockChance/
        # BlockDamage via rl_duel --block-target) = UNE source {chance, amount}. La chaîne (apply_random_
        # block_damage) tire NextBool par source triée jusqu'à 1ʳᵉ réussite → dmg=max(0,dmg−amount), DidBlock.
        # Vide (chance/amount≤0) → aucune source → 0 tirage → rétro-compat exacte (cibles sans block).
        block_chance = int(getattr(tsc.ctx, "block_chance", 0) or 0) if tsc is not None else 0
        block_amount = int(getattr(tsc.ctx, "block_damage", 0) or 0) if tsc is not None else 0
        block_sources = ([BlockSource(chance=block_chance, amount=block_amount)]
                         if block_chance > 0 and block_amount > 0 else None)
        # DÉFENSEUR : réductions de dégât reçu portées par les effets de la CIBLE (symétrique attaquant ;
        # CalculateDefenderModifiersForPrediction). Vide → no-op (apply_all_modifiers identité). Couvre la
        # famille ADamageDefenseModifierAbilityEffect ; STAT/Parry/triggers = axes séparés (cf. §1.8).
        # #59 : threade is_melee (= coup mêlée = arme non-rangée) + profil de dégât → malus gatés corrects
        # (Terrifying_ExtraDefense gate IsMeleeAttack ; TerminatorArmour exclut Psychic/DirectDamage). Mirror
        # de la prédiction. #59 suite : les chemins ABILITY (execute_ability_attack/execute_normal_like)
        # câblent DÉSORMAIS ces gates aussi (params damage_profile/is_melee threadés par tous leurs callers).
        def_mods, _def_active = defender_modifiers(state, target_id, thc.hp,
                                                   is_melee=not _ranged, damage_profile=_profile)
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
        # (tirage impair). `roll_critical` ne tire QUE si cc≥1 (NextBool) — cc=0 ⇒ 0 tirage ⇒ rétro-compat
        # exacte du multi-coups non-crit validé (18/18). Gate `could_crit` = cc>0 ET cd>0 (CouldCrit@181004fb0).
        # crit = GetStat(9/10) [DÉJÀ effet-inclusif : les effets StatModification sur la crit sont
        # cuits dans GetStat → dans le combatSnapshot → dans ctx] + couche calc-time SÉPARÉE
        # GetCritChanceBonusFromEffects/GetCritDamageBonusFromEffects (PAS dans GetStat → sommée ici
        # depuis les effets ACTIFS de l'attaquant). Mirror exact de RollCritical/CalculateCriticalDamage.
        crit_chance = ctx.stat(StatType.CRIT_CHANCE) + crit_chance_bonus_from_effects(active)
        crit_damage = ctx.stat(StatType.CRIT_DAMAGE) + crit_damage_bonus_from_effects(active)
        crit_enabled = could_crit(crit_chance, crit_damage)

        def _reduced_bounds(eff_attack: int) -> "HitDamage":
            mm = get_base_damage_fix64(eff_attack, spread_pct=spread_pct)
            lo = apply_all_modifiers(apply_pierce_and_modifiers(mm.min, pierce, armor, mods), def_mods)
            hi = apply_all_modifiers(apply_pierce_and_modifiers(mm.max, pierce, armor, mods), def_mods)
            return HitDamage(lo, hi)

        hit_nc = _reduced_bounds(ctx.stat(StatType.ATTACK))               # plage NON-crit par coup
        hit_cr = _reduced_bounds(ctx.stat(StatType.ATTACK) + crit_damage) if crit_enabled else hit_nc
        clean_min = hit_nc.min * hits          # référence affichée = plage non-crit (× hits)
        clean_max = hit_nc.max * hits
        # BOUCLIER cible : absorbe le coup réduit AVANT les PV (CalculateDamageOperation shield-first) ;
        # _run_hits déplète le bouclier entre coups (shield -= dmg.shield), total = part SANTÉ seule.
        shc, shield_total = AttackDamageOperation._target_shield(tgt)
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources, shield=shield_total)
        AttackDamageOperation._deplete_shield(shc, r)
        death = None
        if thc.hp is not None:
            hp_before = thc.hp
            thc.hp = max(0, thc.hp - r["total"])
            death = AttackDamageOperation._fire_death_if_killed(
                state, target_id, attacker_id, hp_before, thc.hp, tgt, damage=r["total"])
        return {"hits": hits, "total": r["total"], "base": ctx.stat(StatType.ATTACK), "pierce": pierce,
                "armor": armor, "clean_min": clean_min, "clean_max": clean_max, "death": death,
                "shield_dmg": r["shield_dmg"], "armor_dmg": r["armor_dmg"],
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"],
                "ranged": _ranged, "profile": _profile,
                "effects": [getattr(e, "name", None) for e in active]}

    @staticmethod
    def _run_hits(rng: IntBasedMersenneTwister, hit_nc: "HitDamage", hit_cr: "HitDamage",
                  crit_chance: int, crit_enabled: bool, hits: int, block_sources,
                  shield: int = 0, armor_pool: int = 0, armor_pct: int = 0, post_roll=None) -> dict:
        """Boucle PAR COUP partagée (attaque normale ET ability) : pour chaque coup, crit-roll D'ABORD
        (1 tirage NextBool si cc>=1, sinon 0) PUIS tirage dans `hit_cr`/`hit_nc`, PUIS split combat
        (bouclier/armure-pool/block, `calculate_damage_operation`). Ordre RNG crit->spread->block confirmé.

        `post_roll` = réduction perçage/armure/mods APPLIQUÉE APRÈS le tirage (None = déjà appliquée aux
        bornes). DEUX ordres distincts (confirmés live) :
          • ATTAQUE NORMALE = reduce-then-roll : `hit_nc`/`hit_cr` = bornes DÉJÀ réduites, `post_roll=None`.
          • ABILITY = roll-then-reduce : `hit_nc`/`hit_cr` = bornes BRUTES config (RandomAmount(min,max)),
            `post_roll=_reduce` → on tire le BRUT puis on réduit (modulo sur la largeur BRUTE != réduite ;
            confirmé bit-exact ThunderousAssault: roll-then-reduce draw0 = live 6948).
        Renvoie total/per_hit/rolls/crits + flags. Pools déplétés entre coups (0 -> invariant)."""
        total = shield_dmg = armor_dmg = 0
        did_crit = did_block = did_evade = False
        crits: list[bool] = []
        rolls: list[int] = []
        per_hit: list[int] = []
        for _ in range(hits):
            crit = roll_critical(rng, crit_chance) if crit_enabled else False
            crits.append(crit)
            hd = hit_cr if crit else hit_nc
            roll = hd.get_damage(rng)
            if post_roll is not None:
                roll = post_roll(roll)        # ability : réduction APRÈS le tirage (roll-then-reduce)
            rolls.append(roll)
            dmg: Damage = calculate_damage_operation(
                roll, shield=shield, armor_pool=armor_pool, armor_pct=armor_pct,
                block_sources=block_sources, evasion_branch=False, rng=rng)
            shield = max(0, shield - dmg.shield)
            armor_pool = max(0, armor_pool - dmg.armor)
            per_hit.append(dmg.get_total())
            total += dmg.health
            shield_dmg += dmg.shield
            armor_dmg += dmg.armor
            did_crit |= crit
            did_block |= dmg.did_block
            did_evade |= dmg.did_evade
        return {"total": total, "shield_dmg": shield_dmg, "armor_dmg": armor_dmg,
                "did_crit": did_crit, "did_block": did_block, "did_evade": did_evade,
                "crits": crits, "rolls": rolls, "per_hit": per_hit}

    @staticmethod
    def execute_ability_attack(state: State, attacker_id: int, target_id: int,
                               base_min: int, base_max: int, profile_pierce: int,
                               hits: int, damage_profile: Optional[str] = None,
                               is_melee: Optional[bool] = None) -> Optional[dict]:
        """Attaque d'une ABILITY active (mirror `AttackWithAttackDamage` + `MinMaxDamage`/`GetHits`/
        `GetDamageProfile`). DIFFÈRE de l'attaque normale par la BASE : les bornes du coup = `[base_min,
        base_max]` données par la config d'ability (`GetVariableForLevel` clés 0xc/0xd = minDmg/maxDmg),
        PAS `Attack ± spread%`. Le perçage = celui du PROFIL de l'ability (`GetDamageProfile`). Le RESTE
        du pipeline est IDENTIQUE (réduction perçage/armure/modifiers sur les bornes -> tirage dans la
        plage réduite -> crit -> block), donc réutilise `_run_hits`. Mute les PV de la cible.

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
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None)
        tsc = tgt.get_component(StatsComponent)
        armor = tsc.ctx.stat(StatType.FIXED_ARMOR) if tsc is not None else 0
        block_chance = int(getattr(tsc.ctx, "block_chance", 0) or 0) if tsc is not None else 0
        block_amount = int(getattr(tsc.ctx, "block_damage", 0) or 0) if tsc is not None else 0
        block_sources = ([BlockSource(chance=block_chance, amount=block_amount)]
                         if block_chance > 0 and block_amount > 0 else None)
        # #59 suite : threade is_melee + profil de l'ability -> malus DÉFENSEUR gatés (Terrifying_ExtraDefense
        # IsMeleeAttack ; TerminatorArmour DamageProfileIs). None (caller non mis à jour) = comportement
        # historique (gates non appliqués) — INERTE pour une cible sans effet de défense gaté.
        def_mods, _da = defender_modifiers(state, target_id, thc.hp,
                                           is_melee=is_melee, damage_profile=damage_profile)
        crit_chance = ctx.stat(StatType.CRIT_CHANCE) + crit_chance_bonus_from_effects(active)
        crit_damage = ctx.stat(StatType.CRIT_DAMAGE) + crit_damage_bonus_from_effects(active)
        crit_enabled = could_crit(crit_chance, crit_damage)

        def _reduce(value: int) -> int:
            return apply_all_modifiers(
                apply_pierce_and_modifiers(value, profile_pierce, armor, mods), def_mods)

        # ABILITY = roll-then-reduce : on tire dans les bornes BRUTES config (RandomAmount(min,max)) PUIS
        # on réduit (perçage/armure/mods) via `post_roll`. (≠ attaque normale reduce-then-roll.) Confirmé
        # bit-exact live (ThunderousAssault necroOverlord : roll-then-reduce = live 6948, à l'unité).
        hit_nc = HitDamage(base_min, base_max)                            # bornes BRUTES
        # CRIT pour ability = HYPOTHÈSE (non RE/validée) : crit plie sur les bornes brutes (min/max +
        # critDamage) avant réduction. NON exercé tant que cc=0 (crit = item normalisé) ; à confirmer live.
        hit_cr = HitDamage(base_min + crit_damage, base_max + crit_damage) if crit_enabled else hit_nc
        hits = max(1, int(hits))
        shc, shield_total = AttackDamageOperation._target_shield(tgt)      # bouclier shield-first
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources, shield=shield_total,
                                            post_roll=_reduce)
        AttackDamageOperation._deplete_shield(shc, r)
        if thc.hp is not None:
            hp_before = thc.hp
            thc.hp = max(0, thc.hp - r["total"])
            AttackDamageOperation._fire_death_if_killed(
                state, target_id, attacker_id, hp_before, thc.hp, tgt, damage=r["total"])
        return {"hits": hits, "total": r["total"], "base_min": base_min, "base_max": base_max,
                "pierce": profile_pierce, "armor": armor,
                "clean_min": hit_nc.min * hits, "clean_max": hit_nc.max * hits,
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"]}


    @staticmethod
    def execute_normal_like(state: State, attacker_id: int, target_id: int, base: int,
                            profile_pierce: int, hits: int = 1, spread_pct: int = 20,
                            damage_profile: Optional[str] = None,
                            is_melee: Optional[bool] = None) -> Optional[dict]:
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
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None)
        tsc = tgt.get_component(StatsComponent)
        armor = tsc.ctx.stat(StatType.FIXED_ARMOR) if tsc is not None else 0
        block_chance = int(getattr(tsc.ctx, "block_chance", 0) or 0) if tsc is not None else 0
        block_amount = int(getattr(tsc.ctx, "block_damage", 0) or 0) if tsc is not None else 0
        block_sources = ([BlockSource(chance=block_chance, amount=block_amount)]
                         if block_chance > 0 and block_amount > 0 else None)
        # #59 suite : threade is_melee + profil -> malus DÉFENSEUR gatés (cf. execute_ability_attack).
        # None (caller non mis à jour) = comportement historique — INERTE sans effet de défense gaté.
        def_mods, _da = defender_modifiers(state, target_id, thc.hp,
                                           is_melee=is_melee, damage_profile=damage_profile)
        crit_chance = ctx.stat(StatType.CRIT_CHANCE) + crit_chance_bonus_from_effects(active)
        crit_damage = ctx.stat(StatType.CRIT_DAMAGE) + crit_damage_bonus_from_effects(active)
        crit_enabled = could_crit(crit_chance, crit_damage)

        def _reduced(eff_base: int) -> "HitDamage":
            mm = get_base_damage_fix64(eff_base, spread_pct=spread_pct)
            lo = apply_all_modifiers(apply_pierce_and_modifiers(mm.min, profile_pierce, armor, mods), def_mods)
            hi = apply_all_modifiers(apply_pierce_and_modifiers(mm.max, profile_pierce, armor, mods), def_mods)
            return HitDamage(lo, hi)

        hit_nc = _reduced(base)
        hit_cr = _reduced(base + crit_damage) if crit_enabled else hit_nc
        hits = max(1, int(hits))
        shc, shield_total = AttackDamageOperation._target_shield(tgt)      # bouclier shield-first
        r = AttackDamageOperation._run_hits(state.rng, hit_nc, hit_cr, crit_chance,
                                            crit_enabled, hits, block_sources,
                                            shield=shield_total)   # post_roll=None (reduce-then-roll)
        AttackDamageOperation._deplete_shield(shc, r)
        if thc.hp is not None:
            hp_before = thc.hp
            thc.hp = max(0, thc.hp - r["total"])
            AttackDamageOperation._fire_death_if_killed(
                state, target_id, attacker_id, hp_before, thc.hp, tgt, damage=r["total"])
        return {"hits": hits, "total": r["total"], "base": base, "pierce": profile_pierce,
                "armor": armor, "clean_min": hit_nc.min * hits, "clean_max": hit_nc.max * hits,
                "did_crit": r["did_crit"], "did_block": r["did_block"], "did_evade": r["did_evade"],
                "crits": r["crits"], "rolls": r["rolls"], "per_hit": r["per_hit"]}


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
        self.last = AttackDamageOperation.execute(
            self.state, msg.attacker_id, msg.target_id, self.spread_pct)
        # VECTEUR AFTER-HIT : dispatcher GÉNÉRIQUE de triggers (mirror `EvaluateAfterHitTriggers` →
        # `EvaluateTriggerOperation`). Itère le registre des triggers (traits/effets) ; chaque entrée
        # scope elle-même via sa condition (ex. Psyker OwnerIsActor). No-op si aucun trigger ne matche.
        if self.last is not None:
            from .triggers import after_hit_normal_attack
            self.after_hit = after_hit_normal_attack(
                self.state, msg.attacker_id, msg.target_id,
                bool(self.last.get("ranged")), self.last.get("profile"),
                is_crit=bool(self.last.get("did_crit")))
