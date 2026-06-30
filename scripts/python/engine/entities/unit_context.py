"""`UnitContext` — état résolu d'une unité, assemblé depuis les sources OFFLINE autorisées.

Sources (cf. directive 100% offline + capture one-shot config d'arme) :
  • `combatSnapshot.units[*]` (one-shot live) : stats de combat RÉSOLUES + `normalAttack` (dégât de
    base d'arme capté) ;
  • gameconfig-units (offline) : traits, damageType (profil de l'attaque normale), range, faction, class.

Sert d'« entité » que les ports d'ability/prédiction consomment (mirror : IEntity + ses composants).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class UnitContext:
    entity_id: int
    visual_id: str | None = None
    # stats résolues (combatSnapshot.units[*].stats)
    attack: int = 0
    health: int = 0                 # PV courants (StatType.Health, Current)
    fixed_armor: int = 0
    extra_hits: int = 0
    extra_hits_melee: int = 0
    extra_pierce: int = 0
    extra_pierce_melee: int = 0
    extra_pierce_ranged: int = 0
    active_ability_level: int = 0
    passive_ability_level: int = 0     # niveau des PASSIVES (indexe leurs variables ; ex. ArcaneShield.shieldHp)
    number_of_members: int = 1
    crit_chance: int = 0
    crit_damage: int = 0
    block_chance: int = 0
    block_damage: int = 0
    # AbilityVariablesMultiplierPercentage (BC Units[*], dérivé progression ; défaut 100=neutre). Scale
    # les variables d'ability « affectées par la rareté » (ex. PowerTrip.armorIgnored) §17.21. Capté hors
    # combatSnapshot (BC) pour l'instant ; non figé par from_snapshot.
    ability_variables_multiplier: int = 100
    # gameconfig-units (offline)
    traits: list[int] = field(default_factory=list)
    damage_type: int = 0            # DamageProfileType index de l'attaque normale
    range: int = 0                  # 0 = mêlée
    faction: str | None = None
    unit_class: int = 0
    # attaque normale captée (combatSnapshot.normalAttack) : dégât de base d'arme résolu
    normal_min: int = 0
    normal_max: int = 0
    normal_hits: int = 1
    # arme de l'attaque normale résolue depuis gameconfig (pour la chaîne fidèle base=Attack)
    normal_profile: str | None = None      # nom DamageProfile de l'arme (ex. "Toxic", "Power")
    normal_profile_pierce: int = 0          # damage_profile(profile).PiercingRatio (base, pré-stats)
    normal_weapon_hits: int = 1             # weapon.hits (gameconfig ; ≠ normal_hits capté parfois)
    normal_ranged: bool = False             # weapon.Range présent → tir (sinon mêlée)
    # effets ACTIFS captés (decisionView.effects : [{name, level, …}]) — sources des modifiers de
    # dégât (§17.8). Re-évalués PAR DÉCISION (changent par tour) ; NON figés par from_snapshot (cold).
    active_effects: list[dict] = field(default_factory=list)

    @property
    def is_melee(self) -> bool:
        return self.range <= 0

    def attacker_modifiers(self):
        """`DamageModifiers` attaquant (`CalculateAttackerModifiersForPrediction` @181000590) bâti depuis
        les EFFETS actifs de l'unité (§17.8 ; vide si aucun = no-op). `active_effects` = instances
        `BaseEffect` (matérialisées/filtrées par EffectsState) OU dicts captés. Lazy import (entities.effects)
        ; re-évalué par-décision — ne pas figer."""
        from .effects import build_attacker_modifiers_from_effects
        return build_attacker_modifiers_from_effects(self.active_effects)

    def trait_objects(self):
        """Traits matérialisés de l'unité (instances `BaseTrait` via la factory) — innés/statiques, exploités
        par le contrat raw-prediction §17.17 (hit-twice, ignore-armure, GetStuckIn, Resilient/Impervious…).
        `self.traits` = noms gameconfig. Lazy import (entities.traits)."""
        from .traits import TraitFactory
        return TraitFactory.create_many(self.traits)

    @property
    def normal_base(self) -> int:
        """Base mono-valeur de l'attaque normale (pré-spread) = avg(min,max) capturé.
        Le port de prédiction ré-applique le spread (CalculateDamageSpread)."""
        return (self.normal_min + self.normal_max) // 2

    @classmethod
    def from_snapshot(cls, snap_unit: dict, unit_cfg: dict | None) -> "UnitContext":
        s = snap_unit.get("stats") or {}
        na = snap_unit.get("normalAttack") or {}
        g = lambda k: int(s.get(k) or 0)
        cfg = unit_cfg or {}
        na_ok = not na.get("error")
        # Résoudre l'arme de l'attaque normale (gameconfig) : celle dont hits==normal_hits capté,
        # sinon la 1re. → DamageProfile / PiercingRatio / hits-arme. (GetAttackPiercingDamageRatio
        # ré-appliquera ExtraPierce ; ici on capte la base PiercingRatio du profil.)
        nh = int(na.get("hits") or 1) if na_ok else 1
        weapons = cfg.get("weapons") or []
        w = next((x for x in weapons if int(x.get("hits") or 0) == nh),
                 weapons[0] if weapons else None)
        prof_name = w.get("DamageProfile") if w else None
        prof_pierce = w_hits = 0
        ranged = False
        if w:
            import gameconfig as _GC  # source de données offline (cf. docstring)
            dp = _GC.damage_profile(prof_name) or {}
            prof_pierce = int(dp.get("PiercingRatio") or 0)
            w_hits = int(w.get("hits") or 1)
            ranged = bool(w.get("Range"))
        return cls(
            entity_id=snap_unit.get("entityId"), visual_id=snap_unit.get("visualId"),
            attack=g("attack"), health=g("health"), fixed_armor=g("fixedArmor"),
            extra_hits=g("extraHits"), extra_hits_melee=g("extraHitsMelee"),
            extra_pierce=g("extraPierce"), extra_pierce_melee=g("extraPierceMelee"),
            extra_pierce_ranged=g("extraPierceRanged"),
            active_ability_level=g("activeAbilityLevel"),
            number_of_members=max(1, g("numberOfMembers")),
            crit_chance=g("critChance"), crit_damage=g("critDamage"),
            block_chance=g("blockChance"), block_damage=g("blockDamage"),
            traits=list(cfg.get("traits") or []),
            damage_type=int(cfg.get("damageType", 0) or 0),
            range=int(cfg.get("range", 0) or 0),
            faction=cfg.get("faction"), unit_class=int(cfg.get("class", 0) or 0),
            normal_min=int(na.get("minDmg") or 0) if na_ok else 0,
            normal_max=int(na.get("maxDmg") or 0) if na_ok else 0,
            normal_hits=nh,
            normal_profile=prof_name, normal_profile_pierce=prof_pierce,
            normal_weapon_hits=max(1, w_hits), normal_ranged=ranged,
        )
