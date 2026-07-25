"""`UnitContext` — état résolu d'une unité, assemblé depuis les sources OFFLINE autorisées.

Sources (cf. directive 100% offline + capture one-shot config d'arme) :
  • `combatSnapshot.units[*]` (one-shot live) : stats de combat RÉSOLUES + `normalAttack` (dégât de
    base d'arme capté) ;
  • gameconfig-units (offline) : traits, damageType (profil de l'attaque normale), range, faction, class.

Sert d'« entité » que les ports d'ability/prédiction consomment (mirror : IEntity + ses composants).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .stats import UnitStats, StatType, seed_unit_stats


@dataclass
class UnitContext:
    entity_id: int
    visual_id: str | None = None
    # Les 8 stats « de base » (attack, health, fixed_armor, extra_hits, crit_chance, crit_damage,
    # block_chance, block_damage) NE SONT PLUS des champs plats : ce sont des PROPRIÉTÉS lecture-seule
    # adossées à `get_stat(Current)` (cf. plus bas + `CORE_STAT_FIELDS`). Elles sont toujours seedées
    # dans `stats` (from_snapshot / build_summon_context), donc `ctx.attack` == GetStat natif, effet-
    # inclusif, SANS stockage dupliqué ni synchro.
    extra_hits_melee: int = 0
    extra_pierce: int = 0
    extra_pierce_melee: int = 0
    extra_pierce_ranged: int = 0
    active_ability_level: int = 0
    passive_ability_level: int = 0     # niveau des PASSIVES (indexe leurs variables ; ex. ArcaneShield.shieldHp)
    number_of_members: int = 1
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
    # Système de stats natif porté (`UnitStats` : StatComponent/ValueModification par StatType) :
    # `GetStat = Initial + Σ(stat-modifications)` clampé, CALCULÉ au lieu de figé. Seedé par
    # `from_snapshot` (si `stat_ids` fourni) depuis combatSnapshot (Current + statDelta → Initial +
    # modification) ; `get_stat(Current)` reproduit exactement Current. Cf. stats.py / docs/rl/stat-system.md.
    stats: "UnitStats" = field(default_factory=UnitStats)

    @property
    def is_melee(self) -> bool:
        return self.range <= 0

    def attacker_modifiers(self):
        """`DamageModifiers` attaquant (`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction) bâti depuis
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

    def get_stat(self, stat_type: int, stat_part: int = 0, source: object = None) -> int:
        """`IdunBattle.Entities.UnitExtensions$$GetStat` sur les stats portées de l'unité. Défaut = Current
        (partie 0). Renvoie 0 si le StatType n'est pas seedé (unité sans UnitStats, ex. summon
        frais construit hors combatSnapshot)."""
        return self.stats.get_stat(int(stat_type), int(stat_part), source)

    def stat(self, stat_type: int) -> int:
        """Valeur COURANTE d'une stat pour la CONSOMMATION combat/prédiction = `get_stat(Current)`.
        Les 8 stats de base sont TOUJOURS seedées (from_snapshot / build_summon_context) → plus de
        fallback de champ plat ; les stat-mods appliqués par `ChangeStat` (`apply_change_stat`) sont
        vus directement. `get_stat` renvoie 0 pour un StatType sans composant (ex. summon + stat non
        seedée), ce qui reste le comportement natif (`default -> 0`)."""
        return self.stats.get_stat(int(stat_type), 0)   # StatPart.CURRENT

    # ── Les 8 stats de base = propriétés lecture-seule adossées à `get_stat(Current)` (CORE_STAT_FIELDS).
    #    Elles remplacent les anciens champs plats : plus de stockage dupliqué, `ctx.<stat>` == GetStat
    #    natif (effet-inclusif). Écriture INTERDITE — muter un stat passe par `apply_change_stat`.
    @property
    def attack(self) -> int:
        return self.stat(StatType.ATTACK)

    @property
    def health(self) -> int:
        """PV « Current » (StatType.Health) résolu par GetStat. NB le PV COURANT en cours de bataille
        vit dans `HealthComponent` (muté par les dégâts) — ceci = la valeur de stat (init/snapshot)."""
        return self.stat(StatType.HEALTH)

    @property
    def fixed_armor(self) -> int:
        return self.stat(StatType.FIXED_ARMOR)

    @property
    def extra_hits(self) -> int:
        return self.stat(StatType.EXTRA_HITS)

    @property
    def crit_chance(self) -> int:
        return self.stat(StatType.CRIT_CHANCE)

    @property
    def crit_damage(self) -> int:
        return self.stat(StatType.CRIT_DAMAGE)

    @property
    def block_chance(self) -> int:
        return self.stat(StatType.BLOCK_CHANCE)

    @property
    def block_damage(self) -> int:
        return self.stat(StatType.BLOCK_DAMAGE)

    @classmethod
    def from_snapshot(cls, snap_unit: dict, unit_cfg: dict | None,
                      stat_ids: dict | None = None, effects=None) -> "UnitContext":
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
        # Système de stats porté : seedé depuis combatSnapshot (Current + statDelta) si le mapping
        # nom→StatType (`stat_ids` = combatSnapshot.statTypes) est fourni ; sinon UnitStats vide
        # (les consommateurs actuels lisent encore les champs plats `attack`/… ; identiques à Current).
        # Si `effects` (BaseEffect matérialisés de l'unité) est fourni, la modification est ATTRIBUÉE
        # par source (stat-mods déclarés) + résidu opaque ; sinon tout le delta reste opaque.
        attributed = None
        if stat_ids and effects:
            from .effects import stat_modifications_by_source
            attributed = stat_modifications_by_source(effects)
        # #60 : attribution du malus Swarm_HitReduction (effet 0x3fd=1021, trait Swarm) — la part
        # `-min(n-1, membres morts)` du delta EXTRA_HITS est attribuée sous la CLÉ PARTAGÉE avec le
        # refresh runner (AddOrUpdate = replace par-source), sinon elle resterait dans CAPTURED_SOURCE
        # et le 1er refresh offline la DOUBLERAIT. Membres morts lus du stat capté (numberOfMembers =
        # GetStat(20, Current) = restants ; delta = Current - Initial(+0x10=base)) — pas de dépendance
        # à hpMax. Attribution indépendante de la visibilité de l'effet dans decisionView.effects.
        if stat_ids and "Swarm" in (cfg.get("traits") or []):
            _d_members = int((snap_unit.get("statDelta") or {}).get("numberOfMembers") or 0)
            _n_base = g("numberOfMembers") - _d_members
            _swarm_amt = -min(_n_base - 1, -_d_members) if (_n_base > 1 and _d_members < 0) else 0
            if _swarm_amt:
                from .effects.loki.hits import SWARM_HIT_REDUCTION_SOURCE
                attributed = attributed if attributed is not None else {}
                _d = attributed.setdefault(int(StatType.EXTRA_HITS), {})
                _d[SWARM_HIT_REDUCTION_SOURCE] = _d.get(SWARM_HIT_REDUCTION_SOURCE, 0) + _swarm_amt
        unit_stats = (seed_unit_stats(s, snap_unit.get("statDelta"), stat_ids, attributed)
                      if stat_ids else UnitStats())
        # Garantit que les 8 stats de base (propriétés) sont seedées même si `stat_ids` est absent /
        # incomplet : `ensure_seeded` est idempotent (ne touche pas un composant déjà seedé par
        # seed_unit_stats, qui porte delta + attribution). Les valeurs plates snapshot = base identité.
        _core_snapshot = {StatType.ATTACK: g("attack"), StatType.HEALTH: g("health"),
                          StatType.FIXED_ARMOR: g("fixedArmor"), StatType.EXTRA_HITS: g("extraHits"),
                          StatType.CRIT_CHANCE: g("critChance"), StatType.CRIT_DAMAGE: g("critDamage"),
                          StatType.BLOCK_CHANCE: g("blockChance"), StatType.BLOCK_DAMAGE: g("blockDamage")}
        for _idx, _val in _core_snapshot.items():
            unit_stats.ensure_seeded(_idx, _val)
        return cls(
            entity_id=snap_unit.get("entityId"), visual_id=snap_unit.get("visualId"),
            extra_hits_melee=g("extraHitsMelee"),
            extra_pierce=g("extraPierce"), extra_pierce_melee=g("extraPierceMelee"),
            extra_pierce_ranged=g("extraPierceRanged"),
            # activeAbilityLevel vit dans `unitConfig` (BattleQuery.GetUnitConfig), PAS dans `stats` →
            # indexe les variables[level] des ABILITIES (minDmg/maxDmg par niveau). Fallback stats/0.
            active_ability_level=int((snap_unit.get("unitConfig") or {}).get("activeAbilityLevel")
                                     or s.get("activeAbilityLevel") or 0),
            # #60 : nrOfMembers de BASE (GroupUnitComponent+0x10, = part Initial du stat 20) — le stat
            # capté `numberOfMembers` est GetStat(20, Current) = membres RESTANTS (5→3 sur un swarm
            # blessé, case-52) ; base = Current − delta. Aligné sur spawn.py (gameconfig nrOfMembers).
            number_of_members=max(1, g("numberOfMembers")
                                  - int((snap_unit.get("statDelta") or {}).get("numberOfMembers") or 0)),
            traits=list(cfg.get("traits") or []),
            damage_type=int(cfg.get("damageType", 0) or 0),
            range=int(cfg.get("range", 0) or 0),
            faction=cfg.get("faction"), unit_class=int(cfg.get("class", 0) or 0),
            normal_min=int(na.get("minDmg") or 0) if na_ok else 0,
            normal_max=int(na.get("maxDmg") or 0) if na_ok else 0,
            normal_hits=nh,
            normal_profile=prof_name, normal_profile_pierce=prof_pierce,
            normal_weapon_hits=max(1, w_hits), normal_ranged=ranged,
            stats=unit_stats,
        )
