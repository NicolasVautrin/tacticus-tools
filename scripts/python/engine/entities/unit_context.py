"""`UnitContext` — état résolu d'une unité, assemblé depuis les sources OFFLINE autorisées.

Sources (cf. directive 100% offline + capture one-shot config d'arme) :
  • `combatSnapshot.units[*]` (one-shot live) : stats de combat RÉSOLUES + `normalAttack` (dégât de
    base d'arme capté) ;
  • gameconfig-units (offline) : traits, damageType (profil de l'attaque normale), range, faction, class.

Sert d'« entité » que les ports d'ability/prédiction consomment (mirror : IEntity + ses composants).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .rarity import Rarity, measured_rarity
from .stats import UnitStats, StatType, seed_unit_stats
from .effects import build_attacker_modifiers_from_effects
from .effects import stat_modifications_by_source as _by_source
from .effects import stat_modifications_by_source, stat_overrides_by_stat
from .effects.loki.hits import SWARM_HIT_REDUCTION_SOURCE
from .traits.factory import TraitFactory


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
    # `extra_pierce` / `extra_pierce_melee` / `extra_pierce_ranged` NE SONT PLUS des champs plats :
    # ce sont des PROPRIETES adossees a `get_stat(Current)` (26 / 21 / 22), comme les 8 stats de base
    # ci-dessus. Le natif les LIT ainsi -- `IdunBattle.Core.Services.DamagePrediction$$GetAttackPiercingDamageRatio`
    # fait `GetStat(attacker, 0x1a)` + `GetStat(attacker, isMelee ? 0x15 : 0x16)`. En champ plat, la
    # valeur etait FIGEE a l'instant de la capture : une stat-mod de percage qui ENTRE ou SORT en cours
    # de bataille (`VisionsOfHeresy_ExtraPierce{Melee,Ranged}` sous 50 % PV, case-366-r1) n'etait jamais
    # vue -- le port restait INERTE alors que le natif changeait le percage.
    active_ability_level: int = 0
    passive_ability_level: int = 0     # niveau des PASSIVES (indexe leurs variables ; ex. ArcaneShield.shieldHp)
    number_of_members: int = 1
    # AbilityVariablesMultiplierPercentage (BC Units[*], dérivé progression ; défaut 100=neutre). Scale
    # les variables d'ability « affectées par la rareté » (ex. PowerTrip.armorIgnored) §17.21. Capté hors
    # combatSnapshot (BC) pour l'instant ; non figé par from_snapshot.
    ability_variables_multiplier: int = 100
    # --- ability TERTIAIRE = l'item RELIQUE EQUIPE (#357) -------------------------------------------
    # Les trois champs de `IdunBattle.Configuration.UnitConfiguration` que
    # `IdunBattle.Entities.Factories.UnitFactory$$Build` lit pour fabriquer le TROISIEME `AbilityState`
    # (les deux autres etant l'actif et le passif, deja portes ci-dessus) :
    #     TertiaryAbility                              +0xb0  Nullable<TriggeredAbilityType>
    #     TertiaryAbilityLevel                         +0xc0  (0 = VERROUILLE, jamais un niveau)
    #     TertiaryAbilityVariablesMultiplierPercentage +0x78  (l'actif/passif lisent +0x74)
    # `AddConfiguredAbilities` monte ensuite l'ability par
    # `IdunBattle.Entities.Components.TriggeredAbilityComponent$$TryAdd(id, tertiaryState, 3)` -- le
    # `3` est la hierarchie Tertiary (les passives entrent avec `2`), c'est le discriminant qui
    # distingue une relique d'un passif de kit. `None` = aucune relique equipee (171 des 175 entrees
    # `Units` du seed BC). Peuple par `snapshot._load_tertiary_abilities` (canal `unitAbilityStates`).
    # Le NOM est porte plutot que l'id parce que les registres de dispatch et le gameconfig sont
    # tous deux indexes par nom (`RELIC_ABILITY_TRIGGERS`, `gameconfig.abilities`).
    tertiary_ability: str | None = None
    tertiary_ability_level: int = 0
    tertiary_ability_variables_multiplier: int = 100
    # --- passiveAbilities REELLEMENT MONTEES (#366-r1) ----------------------------------------------
    # Pendant EXACT de `traits_measured` sur l'axe ABILITY, et mirror de la PREMIERE boucle
    # d'`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` :
    #     foreach (id in config+0xa8 = UnitConfiguration.PassiveAbilities)
    #         TriggeredAbilityComponent$$TryAdd(id, passiveAbilityState, 2)
    # -> la HIERARCHIE 2 est exactement l'image de `BC.Units[].PassiveAbilities`, lue au decompile
    # (la 3 est la relique, cf. ci-dessus ; les actives passent par `AddActiveAbility`).
    # Le port DERIVAIT cette liste du gameconfig par `visualId`
    # (`triggers/dispatch/core.py::collect_triggered_abilities`) -- une RECONSTRUCTION a partir d'une
    # autre source, exactement la faute que #264 a corrigee pour les traits. Consequence mesurable :
    # un passif GREFFE sur une unite du pool (`catalog_inject.graft_passive_ability`, seul chemin de
    # confrontation d'une ability dont l'unique porteur est un npc) etait monte LIVE et INERTE cote
    # port, sans erreur ni trace.
    # TRI-ETAT : `None` = canal non mesure -> fallback gameconfig (comportement strictement d'avant) ;
    # une LISTE (fut-elle vide) = mesure, et elle FAIT AUTORITE. Les NOMS sont portes, comme
    # `tertiary_ability`, parce que les registres de dispatch sont indexes par nom.
    passive_abilities: list[str] | None = None
    # --- activeAbilities REELLEMENT MONTEES (#419-r1-tr14-r5-r2) -------------------------------------
    # Le PENDANT de `passive_abilities` sur l'autre voie de la cascade d'attaque normale. Le natif
    # lit `config@+0xa0` = `UnitConfiguration.ActiveAbilities` (prouve par un SECOND corps :
    # `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` lit `+0xa8` -> TryAdd
    # hierarchie 2, `+0xb0` -> TryAdd hierarchie 3, et `+0xa0` -> `UnitFactory$$AddActiveAbility`).
    #
    # ⚠ CE QU'ON MESURE EST UN SUR-ENSEMBLE, et il faut le savoir pour s'en servir. Le canal est
    # `unitAbilityStates.actives[].type`, c.-a-d. l'`ActiveAbilityComponent` -- qui contient AUSSI
    # l'attaque normale que la fabrique vient de poser et les abilities de `AddDerivedAbilities`.
    # Mesure du montage (probe_419r1tr14r5r2) : une unite a qui l'on ecrit
    # `ActiveAbilities = [PoundThemToDust]` rend `[1124, 1126]`, une autre `[1005, 69]`. Le
    # sur-ensemble est SUR pour la seule cle de la table ACTIVE (`1124`) parce qu'elle n'y apparait
    # QUE la ou on l'a ecrite -- controle mesure sur les quatre bras, temoins compris. Un ajout a
    # cette table demandera de refaire ce controle-la.
    #
    # TRI-ETAT, meme discipline que `passive_abilities` : `None` = canal non mesure -> repli kit
    # gameconfig (comportement strictement d'avant) ; une LISTE (fut-elle vide) = mesure.
    # Seede par `snapshot._load_active_abilities` (COMBAT) et `playbook.scene._seed_measured_actives`
    # (DECISION), tous deux sur le parsing PARTAGE `snapshot.active_ability_names_by_unit`.
    active_abilities: list[str] | None = None
    # --- `UnitConfiguration.ActiveAbilities` : l'etat PRE-FABRIQUE (#419-r1-tr14-r5-r2-r2-r1) --------
    # Le champ CI-DESSUS est l'`ActiveAbilityComponent`, donc l'etat APRES la fabrique. Celui-ci est
    # `config@+0xa0` LUI-MEME, c'est-a-dire `BC.Units[].ActiveAbilities` : ce que
    # `IdunBattle.Entities.Factories.UnitFactory$$AddNormalAttackAbility` voit AVANT d'ecrire quoi
    # que ce soit. C'est le seul substrat sur lequel la garde `FilterNewList` du repli generique
    # (`normal_attack_already_present`) puisse etre autre chose qu'une tautologie -- branchee sur le
    # canal POST, elle repondait juste MEME les trois voies amont coupees.
    #
    # Canal : `unitAbilityStates.units[].configActives` (capteur #466), joint a l'entite par
    # `BaseUnitComponent.Id` == `UnitConfiguration.Id` (jointure LUE dans
    # `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent`).
    #
    # TRI-ETAT, meme discipline que les deux voisins : `None` = canal non mesure (capteur absent,
    # cle de jointure illisible, ou entite sans configuration dans la BC) -> la garde ne gate PAS,
    # comportement strictement d'avant ; une LISTE (fut-elle vide) = mesure. Le `[]` n'est PAS un
    # `None` deguise : il vaut « cette configuration ne porte aucun actif », le cas de 50 des 175
    # entrees du seed -- et il est CONFRONTE (une unite invoquee `orksGrot` rend `[]` live, et son
    # entree du seed BC porte bien `ActiveAbilities: []`).
    # Seede par `snapshot._load_config_active_abilities` (COMBAT) et
    # `playbook.scene._seed_measured_config_actives` (DECISION), tous deux sur le parsing PARTAGE
    # `snapshot.config_active_ability_names_by_unit`.
    config_active_abilities: list[str] | None = None
    # --- l'`AbilityState` PAR ABILITY ACTIVE (#890) --------------------------------------------------
    # `{ActiveAbilityType: (level, mult)}`. Le champ scalaire `active_ability_level` ci-dessus est une
    # REDUCTION : le natif resout chaque `GetVariableForLevel` contre l'`AbilityState` de l'ability
    # CASTEE, et deux actives d'une meme unite peuvent etre a des niveaux differents -- mesure sur
    # `ultraCalgar`, qui porte `1000` au niveau 50 et son attaque normale `69` au niveau 1.
    #
    # TRI-ETAT, meme discipline que les trois voisins : `None` = canal non mesure -> les lecteurs
    # retombent sur le scalaire (comportement strictement d'avant) ; un DICT (fut-il vide) = mesure.
    # Canal : `unitAbilityStates.units[].actives[]` (`type`/`level`/`mult`).
    # Seede par `snapshot._load_active_ability_levels`.
    active_ability_levels: dict | None = None
    # --- l'`AbilitiesComponent` ENTIER (#456-r1) -----------------------------------------------------
    # `passive_abilities` ci-dessus ne porte que la HIERARCHIE 2. Le dispatcher d'utilite, lui, itere
    # la collection COMPLETE : `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.
    # u003CEvaluateMovementInStepsu003Ed__2$$MoveNext` fait `case.unit@+0x10` -> GetComponent ->
    # `+0x18` (la Collection) -> `GetEnumerator`, sans aucun filtre de hierarchie -- passifs de kit
    # (2), relique (3) et abilities derivees d'un TRAIT y sont indistinctes.
    # Ce champ porte donc les IDS (`TriggeredAbility.AbilityName`, `raw[0]` du RPC
    # `unitAbilityStates`), et non des noms : le registre de playbooks est indexe par id.
    # TRI-ETAT, meme discipline que `passive_abilities` : `None` = canal non mesure -> repli
    # gameconfig (`triggered_ability_ids`, comportement strictement d'avant) ; une LISTE (fut-elle
    # vide) = mesure, et elle FAIT AUTORITE -- elle peut donc RETIRER un passif que le gameconfig
    # connait et que la bataille ne monte pas (mesure #456-r1 : `tauCrisis` greffe rend `[1120, 1030]`
    # la ou le gameconfig annonce `[1133]`).
    # Seede par `snapshot._load_triggered_abilities` ; lu par le foyer unique
    # `entities.triggered_ability_type.entity_triggered_ability_ids`.
    triggered_abilities: list[int] | None = None
    # gameconfig-units (offline) — SAUF quand `traits_measured` est vrai (cf. ci-dessous).
    traits: list[int] = field(default_factory=list)
    # #264 — `traits` a-t-il ete SEEDE depuis la MESURE live (`combatSnapshot.units[].traits`) plutot
    # que RECONSTRUIT depuis le substrat gameconfig ? Faux = reconstruction (kit gameconfig, auquel
    # `entity_trait_names` ajoute le pseudo-trait de grande-alliance) ; vrai = `traits` porte
    # l'ensemble EFFECTIF que rend `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`
    # (permanents +0x40 | temporaires +0x48, moins le veto +0x50), grande-alliance INCLUSE.
    # Le drapeau n'est PAS decoratif : il dit a `entity_trait_names` de NE PAS re-deriver l'alliance
    # par-dessus une mesure — sans quoi le port RE-AJOUTERAIT un trait que le natif n'a pas forcement
    # pose, c.-a-d. reconstruirait par-dessus la source qu'il vient de lire.
    traits_measured: bool = False
    # --- RARETE EN BATAILLE (#999-r3, canal #1039) ---------------------------------------------
    # `IdunBattle.Entities.Components.BaseUnitComponent.Rarity` (+0x74), l'UNIQUE champ que lisent
    # les TROIS gates natifs de rarete -- `IdunBattle.Entities.UnitExtensions$$HasRarity`,
    # `IdunBattle.Entities.Triggers.HasRarityTrigger$$ShouldTrigger` et
    # `IdunBattle.Entities.Formulas.UnitsWithRaritySelector$$Select`. Ecrit une fois pour toutes par
    # `IdunBattle.Entities.Factories.UnitFactory$$InitBaseComponent` (`[+0x74] = config->[+0x80]`).
    # Type : `idun.meta.Rarity` (`engine.entities.rarity.Rarity`) -- PAS un des quatre
    # `IdunMetaLogic.UserProgress.Model.*Rarity`, qui portent les MEMES six membres aux MEMES
    # ordinaux (la confusion serait SILENCIEUSE EN ORDINAL, cf. `entities/rarity.py`).
    # TRI-ETAT : `None` = canal NON MESURE (etat reconstruit sans `combatSnapshot`, capteur
    # anterieur a #1039, ou canal refuse par son resolveur) -> les gates de rarete rendent FAUX et
    # le DISENT ; un membre = mesure. JAMAIS `Rarity.Common` en repli -- `0` est une valeur
    # plausible, et un repli la rendrait indiscernable d'une absence.
    # ⚠ NE PAS le re-deriver de `GC.unit(vis)["BaseRarity"]` (rarete de BASE : `"Common"` pour des
    # MoW qui sont `Mythic` en bataille) ni du `targetRarity = 5` de `rl_duel build` (vrai dans le
    # SEUL regime par defaut du harnais, faux des qu'une unite est montee par
    # `--unit-stat "<vis>:Rarity=N"`) : ce serait reconstruire la source depuis une autre source,
    # exactement la faute que #264 a corrigee sur l'axe TRAITS.
    # Seede par le foyer UNIQUE `from_snapshot` (donc les DEUX faces : COMBAT via
    # `snapshot._load_stats_and_effects`/`_load_machine_stats`, DECISION via
    # `playbook.scene._hydrate_static_unit`).
    rarity: "Rarity | None" = None
    # #969-r4 -- `EntityExtensions$$CurrentOwnerIsEnvironment`, TRI-ETAT. `None` = PAS MESURE
    # (bundle sans le capteur, ou `invokeBoolOrNull` en echec) ; `False` est une MESURE, et c'est
    # la reponse pour la quasi-totalite des unites -- confondre les deux rendrait une panne de
    # capteur indiscernable du cas normal. Seede par le foyer UNIQUE `from_snapshot`.
    current_owner_is_environment: "bool | None" = None
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
        return build_attacker_modifiers_from_effects(self.active_effects)

    def trait_objects(self):
        """Traits matérialisés de l'unité (instances `BaseTrait` via la factory) — innés/statiques, exploités
        par le contrat raw-prediction §17.17 (hit-twice, ignore-armure, GetStuckIn, Resilient/Impervious…).
        `self.traits` = noms gameconfig. Lazy import (entities.traits)."""
        return TraitFactory.create_many(self.traits)

    # #344 — `normal_base` (= `(normal_min + normal_max) // 2`) RETIRÉE : elle ne citait AUCUN symbole
    # natif et n'avait AUCUN consommateur dans le dépôt (grep exhaustif, y compris accès dynamiques).
    # Le rail vivant passe par `AActiveAbility.get_min_max_damage` qui rend les bornes CAPTURÉES telles
    # quelles (`MinMaxDamage(min=caster.normal_min, max=caster.normal_max)`) — aucune moyenne n'y est
    # prise. Une moyenne tronquée sans artefact, jamais exercée par un test, était un piège : le
    # prochain consommateur aurait hérité d'un arrondi non lu. cf. docs/rl/case-344.

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

    # ── PERÇAGE : les trois stats que lit `GetAttackPiercingDamageRatio` (`GetStat(0x1a)` et
    #    `GetStat(isMelee ? 0x15 : 0x16)`). Mêmes propriétés lecture-seule que les 8 ci-dessus.
    @property
    def extra_pierce(self) -> int:
        return self.stat(StatType.EXTRA_PIERCE)

    @property
    def extra_pierce_melee(self) -> int:
        return self.stat(StatType.EXTRA_PIERCE_MELEE)

    @property
    def extra_pierce_ranged(self) -> int:
        return self.stat(StatType.EXTRA_PIERCE_RANGED)

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
        # Canal OVERRIDE (part 7, `StatOverrideEffect`) — SÉPARÉ de l'attribution additive : le
        # natif écrit dans `ValueOverride` (`StatComponent+0x20`), pas dans la `ValueModification`,
        # et `get_CurrentValue` ignore alors la base. Indépendant du `ctx` (la valeur est une donnée
        # de l'entité-effet, cf. `BaseEffect.applied_stat_overrides`) → calculé UNE fois et passé
        # aux DEUX passes de seed ci-dessous.
        _overrides = None
        if stat_ids and effects:
            attributed = stat_modifications_by_source(effects)
            _overrides = stat_overrides_by_stat(effects)
        # #60 : attribution du malus Swarm_HitReduction (effet 0x3fd=1021, trait Swarm) — la part
        # `-min(n-1, membres morts)` du delta EXTRA_HITS est attribuée sous la CLÉ PARTAGÉE avec le
        # refresh runner (AddOrUpdate = replace par-source), sinon elle resterait dans CAPTURED_SOURCE
        # et le 1er refresh offline la DOUBLERAIT. Membres morts lus du stat capté (numberOfMembers =
        # GetStat(20, Current) = restants ; delta = Current - Initial(+0x10=base)) — pas de dépendance
        # à hpMax. Attribution indépendante de la visibilité de l'effet dans decisionView.effects.
        _swarm: dict = {}
        if stat_ids and "Swarm" in (cfg.get("traits") or []):
            _d_members = int((snap_unit.get("statDelta") or {}).get("numberOfMembers") or 0)
            _n_base = g("numberOfMembers") - _d_members
            _swarm_amt = -min(_n_base - 1, -_d_members) if (_n_base > 1 and _d_members < 0) else 0
            if _swarm_amt:
                _swarm = {int(StatType.EXTRA_HITS): {SWARM_HIT_REDUCTION_SOURCE: _swarm_amt}}
        # Garantit que les 8 stats de base (propriétés) sont seedées même si `stat_ids` est absent /
        # incomplet : `ensure_seeded` est idempotent (ne touche pas un composant déjà seedé par
        # seed_unit_stats, qui porte delta + attribution). Les valeurs plates snapshot = base identité.
        _core_snapshot = {StatType.ATTACK: g("attack"), StatType.HEALTH: g("health"),
                          StatType.FIXED_ARMOR: g("fixedArmor"), StatType.EXTRA_HITS: g("extraHits"),
                          StatType.CRIT_CHANCE: g("critChance"), StatType.CRIT_DAMAGE: g("critDamage"),
                          StatType.BLOCK_CHANCE: g("blockChance"), StatType.BLOCK_DAMAGE: g("blockDamage"),
                          # PERÇAGE (case-366-r1) : les propriétés `extra_pierce*` remplacent les anciens
                          # champs plats — `ensure_seeded` garantit ici la MÊME valeur qu'eux (la valeur
                          # captée) même quand `stat_ids` est absent/incomplet, donc aucun régime ne perd
                          # de perçage par rapport au comportement historique.
                          StatType.EXTRA_PIERCE: g("extraPierce"),
                          StatType.EXTRA_PIERCE_MELEE: g("extraPierceMelee"),
                          StatType.EXTRA_PIERCE_RANGED: g("extraPierceRanged")}

        def _seed(attr):
            """Un SEUL point de seed, rejoué à l'identique pour les deux passes ci-dessous : seule
            l'ATTRIBUTION change. `seed_unit_stats` calcule `Initial = Current − delta` (indépendant de
            l'attribution) puis ventile le delta entre les sources fournies, le reste en résidu opaque
            ⇒ `get_stat(Current)` reproduit Current dans TOUS les cas."""
            us = (seed_unit_stats(s, snap_unit.get("statDelta"), stat_ids, attr, _overrides)
                  if stat_ids else UnitStats())
            for _idx, _val in _core_snapshot.items():
                us.ensure_seeded(_idx, _val)
            return us

        _uc = snap_unit.get("unitConfig") or {}
        ctx = cls(
            entity_id=snap_unit.get("entityId"), visual_id=snap_unit.get("visualId"),
            extra_hits_melee=g("extraHitsMelee"),
            # (extraPierce/extraPierceMelee/extraPierceRanged : plus de kwargs — ce sont des PROPRIÉTÉS
            #  adossées à `stats`, seedées par `seed_unit_stats`/`_core_snapshot` ci-dessus.)
            # activeAbilityLevel vit dans `unitConfig` (BattleQuery.GetUnitConfig), PAS dans `stats` →
            # indexe les variables[level] des ABILITIES (minDmg/maxDmg par niveau). Fallback stats/0.
            active_ability_level=int(_uc.get("activeAbilityLevel")
                                     or s.get("activeAbilityLevel") or 0),
            # #60 : nrOfMembers de BASE (NumberOfMembersComponent+0x10, = part Initial du stat 20) — le stat
            # capté `numberOfMembers` est GetStat(20, Current) = membres RESTANTS (5→3 sur un swarm
            # blessé, case-52) ; base = Current − delta. Aligné sur spawn.py (gameconfig nrOfMembers).
            number_of_members=max(1, g("numberOfMembers")
                                  - int((snap_unit.get("statDelta") or {}).get("numberOfMembers") or 0)),
            traits=list(cfg.get("traits") or []),
            # RARETE EN BATAILLE (#999-r3) : LUE sur la ligne de snapshot, jamais re-derivee du
            # gameconfig. Foyer UNIQUE `entities.rarity.measured_rarity` (tri-etat + refus d'un
            # ordinal hors mirror) -- cf. le champ `rarity` ci-dessus.
            rarity=measured_rarity(snap_unit),
            # #969-r4 -- `IdunBattle.Entities.EntityExtensions$$CurrentOwnerIsEnvironment(e, state)`
            # = `GetCurrentPlayer(e, state).<+0x20>.<+0x20> == PlayerType.Environment (2)`, publie
            # par `combatSnapshot.units[].currentOwnerIsEnvironment` (capteur #1072, `invokeBool
            # OrNull`). C'est le PREMIER des deux termes du predicat que
            # `IdunBattle.AI.Playbook.BasePlaybook$$ShouldEvaluateTarget` applique aux cibles de
            # TOUT playbook -- et le seul qu'aucun autre canal ne porte (`decisionView.units[].owner`
            # publie l'`ownerId`, jamais l'`Owner.Type`).
            # TRI-ETAT STRICT, et il est ici plus glissant qu'ailleurs : ce predicat est FAUX pour
            # la quasi-totalite des unites, donc un repli sur `False` serait d'accord avec le natif
            # PARTOUT sauf dans le seul regime qui existe pour le mesurer. `None` = PAS MESURE.
            current_owner_is_environment=snap_unit.get("currentOwnerIsEnvironment"),
            damage_type=int(cfg.get("damageType", 0) or 0),
            range=int(cfg.get("range", 0) or 0),
            faction=cfg.get("faction"), unit_class=int(cfg.get("class", 0) or 0),
            normal_min=int(na.get("minDmg") or 0) if na_ok else 0,
            normal_max=int(na.get("maxDmg") or 0) if na_ok else 0,
            normal_hits=nh,
            normal_profile=prof_name, normal_profile_pierce=prof_pierce,
            normal_weapon_hits=max(1, w_hits), normal_ranged=ranged,
            # PASSE 1 — seed avec l'attribution lisible SANS ctx (forme mono-stat de la base +
            # Swarm). Les parts Initial/Current y sont DÉJÀ exactes : elles ne dépendent pas de
            # l'attribution, seule la ventilation du delta en dépend.
            stats=_seed({**(attributed or {}), **_swarm} if (attributed or _swarm) else None),
        )
        if not (stat_ids and effects):
            return ctx
        # Ces deux champs vivent dans `unitConfig` (BattleQuery.GetUnitConfig), PAS dans `stats` — ils
        # sont lus ICI (et plus seulement re-posés par l'appelant après retour) parce que la PASSE 2
        # ci-dessous en dépend : la magnitude d'un stat-mod contextuel s'indexe sur le niveau d'ability
        # et le multiplier de rareté du porteur. Portée STRICTEMENT limitée à la voie « avec effets »
        # (`snapshot._load_stats_and_effects`/`_load_machine_stats`), qui re-pose ensuite les MÊMES
        # valeurs ⇒ idempotent ; la voie prédiction (`playbook.scene`) passe `effects=None` et garde son
        # comportement au bit près (elle tient le multiplier hors-ctx, dans `mult_by_id`).
        if _uc.get("abilityVariablesMultiplier") is not None:
            ctx.ability_variables_multiplier = int(_uc["abilityVariablesMultiplier"])
        if _uc.get("passiveAbilityLevel"):
            ctx.passive_ability_level = int(_uc["passiveAbilityLevel"])
        # PASSE 2 (R16) — stat-mods dont la magnitude se lit SUR LE CTX (forme OVERRIDE d'
        # `ApplyModification` : `ActOfFaithBuffEffect`, `ProtectorImperativeEffect`, `AncestralFortune*`,
        # `AugmentedAssault_ReduceArmor`…). Ils n'étaient pas attribuables en passe 1 (le ctx n'existait
        # pas encore) : leur contribution restait dans le résidu opaque `CAPTURED_SOURCE`, donc NON
        # RETIRABLE — le buff d'un effet SEEDÉ ne redescendait jamais à son retrait, alors que le natif
        # le reverte inconditionnellement (`AStatModifierEffect$$RevertModification`, même entité-effet
        # en source). On ré-attribue en REJOUANT le MÊME seed : `get_stat(Current)` est inchangé (le
        # montant sort du résidu et entre sous la clé `statmod_source_key`, celle-là même que
        # `effect_stat_mod_key` retrouve au retrait), seule la VENTILATION du delta change.
        # ⚠ MAGNITUDE APPROCHÉE = régime DÉJÀ en vigueur pour la forme mono-stat (#118) : pour un effet
        # CROSS-UNITÉ la capture ne dit pas le niveau de la SOURCE, on prend celui du porteur et le
        # résidu absorbe l'écart. Le revert retire alors la magnitude CALCULÉE — strictement mieux que
        # l'état antérieur, où il ne retirait RIEN (buff conservé à vie, écart de 100 %).
        full = _by_source(effects, stats_ctx=ctx)
        if full != (attributed or {}):
            for _idx, _d in _swarm.items():
                full.setdefault(_idx, {}).update(_d)
            ctx.stats = _seed(full)
        return ctx
