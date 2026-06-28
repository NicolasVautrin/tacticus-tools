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
              1. HitDamage.GetDamage     @181007bf0   ← TIRAGE (1er conso RNG) DANS la plage réduite
              2. roll crit (CritDamageInfo, composant 0xb)        — palier 2
              3. roll block (composant 10)                        — palier 2
              4. split bouclier/armure-pool (CalculateDamageOperation) — palier 3
              5. EvaluateAfterHitTriggers (cascade)               — palier 4

**Ordre RNG confirmé** : `HitDamage.GetDamage` est le PREMIER consommateur de RNG
d'`ExecuteHit` (crit/block viennent APRÈS). Rien avant le 1er coup ne tire de RNG
pour une attaque mono-coup (GetAttackHits renvoie 1 sans requête). Le tirage de
dégât d'un coup mono-coup propre est donc le tirage RNG #1 — base de la validation
bit-exact (`tests/engine/runner/test_damage_roll_live.py`).

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
from ...services.damage_combat import calculate_damage_operation, Damage
from ...services.damage_modifiers import apply_all_modifiers
from ..prng import IntBasedMersenneTwister
from ..state import State
from ..components import StatsComponent, HealthComponent, PositionComponent
from ..damage_model import select_weapon_pierce, attacker_modifiers, defender_modifiers, _cheby
from ...entities.effects import hits_bonus_from_effects


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
        dist = (_cheby((ap.col, ap.row), (tp.col, tp.row))
                if ap is not None and tp is not None else None)
        pierce, _ranged, whits = select_weapon_pierce(ctx, dist)
        ahc = att.get_component(HealthComponent)
        mods, active = attacker_modifiers(state, attacker_id, ahc.hp if ahc else None)
        hits = max(1, whits + ctx.extra_hits + hits_bonus_from_effects(active))
        tsc = tgt.get_component(StatsComponent)
        armor = tsc.ctx.fixed_armor if tsc is not None else 0
        # DÉFENSEUR : réductions de dégât reçu portées par les effets de la CIBLE (symétrique attaquant ;
        # CalculateDefenderModifiersForPrediction). Vide → no-op (apply_all_modifiers identité). Couvre la
        # famille ADamageDefenseModifierAbilityEffect ; STAT/Parry/triggers = axes séparés (cf. §1.8).
        def_mods, _def_active = defender_modifiers(state, target_id, thc.hp)
        # ORDRE RÉEL (confirmé live 18/18 coups, 3 seeds, necroDestroyer 6h) : le HitDamage natif
        # porte la plage RÉDUITE — la réduction (perçage/armure/modifiers attaquant+défenseur) est
        # appliquée aux BORNES base±spread D'ABORD, puis le tirage `GetDamage` se fait DANS cette plage
        # réduite (next_internal(min_réduit, max_réduit+1)). PAS spread-brut-puis-réduit (qui donne la
        # bonne PLAGE totale mais de mauvaises valeurs par coup — le modulo dépend de la largeur).
        mm = get_base_damage_fix64(ctx.attack, spread_pct=spread_pct)
        ph_min = apply_all_modifiers(apply_pierce_and_modifiers(mm.min, pierce, armor, mods), def_mods)
        ph_max = apply_all_modifiers(apply_pierce_and_modifiers(mm.max, pierce, armor, mods), def_mods)
        hit = HitDamage(ph_min, ph_max)           # plage RÉDUITE par coup
        clean_min = ph_min * hits
        clean_max = ph_max * hits
        # Pools DÉPLÉTABLES de la cible (bouclier / ArmorComponent) — PAS encore exposés par
        # l'ECS (HealthComponent = hp seul) ⇒ 0 pour l'instant (toutes les cibles live testées :
        # RemainingArmor=0/Shield=0). Le split combat se réduit alors à health=raw (no-op validé).
        # TODO : sourcer shield/armor_pool/armor_pct + crit (stat9/10 attaquant) depuis l'ECS.
        shield = armor_pool = armor_pct = 0
        total = shield_dmg = armor_dmg = 0
        did_crit = did_block = did_evade = False
        rolls: list[int] = []      # tirage par coup DANS la plage réduite (= dégât avant split pools)
        per_hit: list[int] = []    # dégât FINAL par coup (après split bouclier/armure-pool)
        for _ in range(hits):
            # 1. tirage DANS la plage RÉDUITE (1 tirage RNG) = dégât du coup avant split pools
            roll = hit.get_damage(state.rng)
            rolls.append(roll)
            # 2. SPLIT combat (CalculateDamageOperation : bouclier/armure-pool/block/evasion). Pools=0
            #    ⇒ dmg.health == roll, aucun tirage RNG supplémentaire (block_sources=None).
            dmg: Damage = calculate_damage_operation(
                roll, shield=shield, armor_pool=armor_pool, armor_pct=armor_pct, rng=state.rng)
            # dépletion des pools entre coups (multi-coups consomme le pool ; ici 0 → invariant)
            shield = max(0, shield - dmg.shield)
            armor_pool = max(0, armor_pool - dmg.armor)
            per_hit.append(dmg.get_total())
            total += dmg.health
            shield_dmg += dmg.shield
            armor_dmg += dmg.armor
            did_crit |= dmg.did_crit
            did_block |= dmg.did_block
            did_evade |= dmg.did_evade
        if thc.hp is not None:
            thc.hp = max(0, thc.hp - total)
        return {"hits": hits, "total": total, "base": ctx.attack, "pierce": pierce,
                "armor": armor, "clean_min": clean_min, "clean_max": clean_max,
                "shield_dmg": shield_dmg, "armor_dmg": armor_dmg,
                "did_crit": did_crit, "did_block": did_block, "did_evade": did_evade,
                "rolls": rolls, "per_hit": per_hit,
                "effects": [getattr(e, "name", None) for e in active]}


class DamageHandler:
    """Visiteur des messages d'attaque (mirror du handler natif lançant AttackDamageOperation).
    `spread_pct` = `BattleConfiguration.Damage.DamageSpreadPercentage` (défaut 20)."""
    __slots__ = ("state", "spread_pct", "last")

    def __init__(self, state: State, spread_pct: int = 20):
        self.state = state
        self.spread_pct = spread_pct
        self.last: Optional[dict] = None       # résultat du dernier coup (diagnostic/test)

    def visit_AttackUnitMessage(self, msg) -> None:
        self.last = AttackDamageOperation.execute(
            self.state, msg.attacker_id, msg.target_id, self.spread_pct)
