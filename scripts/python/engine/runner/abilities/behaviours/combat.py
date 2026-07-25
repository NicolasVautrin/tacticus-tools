"""Feuilles DSL d'ATTAQUE runner-couplees : `AttackWithAttackDamage` (attaque d'ability crit/block),
`AttackWithAbilityDamage` (degat DIRECT sans crit/block), `EvaluateAbilities` (evalue les passifs
declenches inline), `UseActiveAbility` (dispatch recursif d'une ability). Wrappers au-dessus de
`runner/operations/damage.py` + `triggers/dispatch.py`. Namespace natif `Entities.Behaviours.*`."""
from __future__ import annotations

from ....dsl.base import TargetsSelector, resolve_unit, _units_of
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...components import StatsComponent
from ..base import ability_attack_params


class AttackWithAttackDamage(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -> `AttackDamageBehaviour`+`AttackBehaviour.Execute` :
    l'attaque d'une ability (bornes `MinMaxDamage(minDmg/maxDmg[level])`, profil `GetDamageProfile`, nb de
    coups `GetNumberConstant(0x2f)=nrOfHits`) portee sur la cible. Wrapper MINCE au-dessus de l'Operation
    DEJA bit-exact `AttackDamageOperation.execute_ability_attack` (meme pipeline reduce/crit/block/after-hit
    que l'imperatif) : `caster` = `ctx.caster`, `target` = `target_sel` (dict d'unite), et
    `(base_min,base_max,pierce,hits)` via `ability_attack_params(ability_id, profile)` — MEME source que
    l'imperatif -> bit-exact BY CONSTRUCTION (memes args, meme `state.rng`).

    ⚠ Le ciblage natif complet = `Units(Cache(First(Nearest(Tiles(target), casterPos))))` : pour une
    ability MONO-cible melee (ThunderousAssault) il COLLAPSE en la cible du message (`ctx.target`) — que
    l'IA/caller a deja choisie (== l'imperatif live-valide). La chaine Tiles->Nearest->First->Cache->Units
    n'est materialisee que si une ability re-derive sa cible (differe). Emet 'AttackWithAttackDamage'. PUR.

    `min_key`/`max_key`/`hits_key` = cles config du volet de degat (defaut `minDmg`/`maxDmg`/`nrOfHits` =
    `MinMaxDamage`/`GetDamageProfile`/`GetNumberConstant(0x2f)`) ; une ability a DEUX volets (ex. CrushingClaws
    principal vs splash) passe le 2e jeu (`minDmg_2`/`maxDmg_2`/`nrOfHits_2` = `MinMaxDamage2`/`GetDamageProfile2`
    /`GetNumberConstant(0x32)`).

    `damage_override` = callable `(state, caster, target, bmin, bmax) -> (bmin, bmax)` mirror d'un
    `AActiveAbility.GetAttackDamage` SURCHARGE par-ability (le natif passe la node de degat calculee a
    `AttackWithAttackDamage` — cf. `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$GetAttackDamage` = ConditionalAmount(cible Pinned
    -> +extraDmg)). Defaut None = degat generique `MinMaxDamage` (bornes config brutes) ; sinon le callable
    ajuste (bmin,bmax) APRES `ability_attack_params`, AVANT le tirage per-coup.

    `multi` = mode MULTI-CIBLE (`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` : quand le `targets` natif est un
    SELECTEUR resolvant N unites — le volet SPLASH de PlasmaGrenade/Stikkbomb/... `Enemies(caster,
    AdjacentUnits(target,1))` — le behaviour resout la LISTE, l'`OrderBy` (b__5_0, cle scalaire par-unite =
    ordre de lecture) puis attaque CHAQUE cible dans l'ordre). Port : `evaluate` -> liste, tri par `id`
    (= ordre de lecture natif == l'ordre `sorted` de l'imperatif `_splash_ability_behaviour` -> bit-exact),
    une attaque + un `emit` par cible. `multi=False` (defaut) = mono-cible `resolve_unit` (mirror du collapse
    `Units(Cache(First(Nearest(...))))` -> la cible du message) : chemin INCHANGE pour ThunderousAssault/
    CrushingClaws/SpiritLeech.

    `pick_n` = FOLD du `IdunBattleLogic.Entities.DSLFactory$$PickRandomly(selecteur, n)` natif quand il ENVELOPPE le selecteur de cibles
    d'une attaque (SPLASH de Fragstorm IdunBattleLogic.Entities.Abilities.Active.Loki.FragstormAbility$$ExecuteBehaviour : `PickRandomly(AdjacentTiles(target) − Tiles(Friends), 4)`).
    Comme `multi=True` folde l'`OrderBy`, `pick_n` folde le PickRandomly DANS la resolution du selecteur
    d'attaque : apres `evaluate`+tri par id, on tire `n` cibles via `_pick_randomly_n(state.rng)` (== l'imperatif
    `_pick_randomly_n(_adjacent_enemies_of, n)` -> bit-exact, meme pool id-trie/meme pick/meme rng). Defaut None
    = pas de tirage (toutes les cibles). Requiert `multi=True`. ⚠ GAP #215 (RNG-exact) : le natif tire des HEXES
    (tuiles VIDES incluses = coup gaspille) et l'ordre/cout exact du tirage ne sont pas cales ; le port tire des
    OCCUPANTS (pas de tuile vide) -> divergence possible quand >n tuiles adjacentes candidates.

    `amount` = FOLD du degat-node `Direct(amountFormula)` quand le natif passe une **valeur calculee** a
    `AttackWithAttackDamage` en lieu de bornes d'arme (`MinMaxDamage`) — ex. Psyker
    `PercentageOf(StatAmount(Self, Attack), psykerExtraDmg%)` IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateBehaviour. Defaut None = mode bornes
    (`ability_attack_params`). Quand fourni (un `AAmountFormula`), la feuille calcule `base =
    amount.evaluate(entities)` (Fix64, mirror natif — `entities` porte `get_stat` pour `StatAmount`) et route
    via `AttackDamageOperation.execute_normal_like(base, pierce=profile_pierce, hits, spread_pct=0)` (montant
    MONO-valeur = AUCUNE variance d'arme), meme pipeline reduce/crit/block/after-hit que l'attaque normale.
    `hits` = nb de coups EXPLICITE du degat-node (defaut 1 en mode `amount` ; en mode bornes, None → `hits`
    de la config via `ability_attack_params`, sinon OVERRIDE la config `nrOfHits` — cas d'une ability dont le
    natif passe un nb de coups CALCULE a `AttackWithAttackDamage` en lieu de `GetNumberConstant(0x2f)` : ex.
    Executioner `hits = IdunBattleLogic.Entities.DSLFactory$$RoundsStarted` = valeur DYNAMIQUE lue au cast, PAS une constante config)."""
    __slots__ = ("target_sel", "ability_id", "profile", "is_melee", "min_key", "max_key", "hits_key",
                 "damage_override", "multi", "pick_n", "amount", "hits", "ability_type", "hits_add_key",
                 "native_factory", "force_overkill", "hits_override", "level_slot")

    def __init__(self, target_sel: TargetsSelector, ability_id: str, profile: str, is_melee: bool = True,
                 min_key: str = "minDmg", max_key: str = "maxDmg", hits_key: str = "nrOfHits",
                 damage_override=None, multi: bool = False, pick_n=None, amount=None, hits=None,
                 ability_type=None, hits_add_key=None, native_factory: str = "attack",
                 force_overkill: bool = False, hits_override=None, level_slot: str = "active"):
        self.target_sel, self.ability_id, self.profile, self.is_melee = target_sel, ability_id, profile, is_melee
        self.min_key, self.max_key, self.hits_key = min_key, max_key, hits_key
        self.damage_override, self.multi, self.pick_n = damage_override, multi, pick_n
        self.amount, self.hits = amount, hits
        # `level_slot` = source du niveau qui indexe minDmg/maxDmg (mode bornes) : "active" (defaut, ability
        # ACTIVE) ou "passive" (ability PASSIVE/TRIGGERED, ex. MartialApotheosis -> passive_ability_level).
        self.level_slot = level_slot
        # `hits_add_key` = 2e constante de coups AJOUTEE au `hits_key` (bande dont le nb de coups est la
        # SOMME de deux GetNumberConstant -- Gauntlets bande adjacente = nrOfHits + nrOfHits_2). Mode bornes
        # uniquement (le mode `amount` a un `hits` explicite). Defaut None.
        self.hits_add_key = hits_add_key
        # `ability_type` = AbilityOrEffect NUMERIQUE du coup, threade au payload des events after-hit
        # (`TriggerEvent.ability_type`, mirror du champ d'event natif lu par DirectAbilitySelector) —
        # ex. smite Psyker = 0x3f5=1013 (gate branche 2 LordOfTempests AddIce #35). None = non threade.
        self.ability_type = ability_type
        # `native_factory` = LA FACTORY NATIVE de la feuille (cas fable rngcrit-1202) — deux operations
        # natives DISTINCTES avec des consommations RNG per-coup differentes :
        #   "attack"  (defaut) = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (+overloads IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage/
        #             350/520/6b0) -> AttackDamageBehaviour -> `AttackDamageOperation.ExecuteHit
        #             IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` : valeur BRUTE (GetDamage-top) + resolve slot-8 GASPILLE = 2 tirages/
        #             coup a cc=0 (mesure bit-exact VigilanceEternal, 5 seeds x 2 cibles).
        #   "ability" = `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage/IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage -> core IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`
        #             -> AbilityDamageBehaviour -> `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` :
        #             GetDamage par coup SEUL (IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage = 0 RNG) = 1 tirage/
        #             coup (mesure bit-exact Stormcaller 3-hit, probe_217). Classifier par les XREFS de
        #             l'`ExecuteBehaviour` natif de l'ability (quelle factory est appelee), JAMAIS au juge.
        self.native_factory = native_factory
        # `force_overkill` = flag « always overkilled » (Nullable<bool>=true, 8e arg de
        # `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`) : force `overkill=True` par coup ->
        # BYPASSE le cap Resilient (`IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit`). No-op cible
        # non-Resilient. Porteur : FlailSwing (1042, deathBlightlord). Defaut False. Mode bornes
        # uniquement (route par `execute_ability_attack`).
        self.force_overkill = force_overkill
        # `hits_override` = nb de coups EXPLICITE du mode BORNES, quand le nb de coups natif N'EST PAS une
        # constante config `GetNumberConstant` mais un NODE dynamique (ex. SkyStrike `MeleeWeaponHits(caster)`
        # = nrOfHits de l'arme melee du caster, WeaponHitsFormula IdunBattle.Entities.Formulas.WeaponHitsFormula$$Calculate ; la config d'ability 1025 n'a pas
        # de `nrOfHits`). Defaut None = coups lus de la config (`hits_key`, comportement historique). Mode bornes
        # uniquement (le mode `amount` a deja un `hits` explicite). Exclusif avec `hits` (Executioner).
        self.hits_override = hits_override

    def execute(self, entities, ectx):
        from ...operations.damage import AttackDamageOperation
        state = ectx.state
        caster = (entities.caster or {}).get("id")
        if state is None or caster is None:
            return OperationResult.ok()
        if self.multi:                                     # AttackBehaviour.Execute : selecteur -> N cibles
            targets = sorted((u for u in _units_of(self.target_sel, entities) if (u or {}).get("id") is not None),
                             key=lambda u: u.get("id"))     # OrderBy (b__5_0) = ordre de lecture == id
            if self.pick_n is not None:                    # PickRandomly(selecteur, n) folde (state.rng), == imperatif
                from ..loki import _pick_randomly_n
                targets = _pick_randomly_n(state, targets, int(self.pick_n))
        else:                                              # collapse mono-cible (cible du message)
            tu = resolve_unit(self.target_sel, entities)
            targets = [tu] if tu and tu.get("id") is not None else []
        for tu in targets:
            tgt = tu.get("id")
            if self.amount is not None:                    # degat-node Direct(StatAmount/PercentageOf) (Psyker/Fire)
                from ..base import profile_pierce
                base = int(self.amount.evaluate(entities))  # Fix64 mirror (entities.get_stat -> StatAmount)
                ce = state.get_entity(caster)
                csc = ce.get_component(StatsComponent) if ce is not None else None
                pierce = profile_pierce(csc.ctx if csc is not None else None, self.profile,
                                        ranged=not self.is_melee)
                atk = AttackDamageOperation.execute_normal_like(  # montant mono-valeur -> spread_pct=0
                    state, caster, tgt, base, pierce,
                    hits=int(self.hits) if self.hits is not None else 1, spread_pct=0,
                    damage_profile=self.profile, is_melee=self.is_melee,
                    ability_type=self.ability_type)
            else:
                bmin, bmax, pierce, hits = ability_attack_params(
                    state, caster, self.ability_id, self.profile, ranged=not self.is_melee,
                    min_key=self.min_key, max_key=self.max_key, hits_key=self.hits_key,
                    hits_add_key=self.hits_add_key, level_slot=self.level_slot)
                if self.hits is not None:                  # hits DYNAMIQUE (Executioner RoundsStarted) override config nrOfHits
                    hits = int(self.hits)
                elif self.hits_override is not None:       # coups = NODE dynamique (SkyStrike MeleeWeaponHits)
                    hits = int(self.hits_override)
                if self.damage_override is not None:       # GetAttackDamage surchargee (ex. SpiritLeech +extraDmg)
                    bmin, bmax = self.damage_override(state, caster, tgt, bmin, bmax)
                atk = AttackDamageOperation.execute_ability_attack(
                    state, caster, tgt, bmin, bmax, pierce, hits,
                    damage_profile=self.profile, is_melee=self.is_melee,
                    ability_type=self.ability_type,
                    is_attack_damage_op=(self.native_factory != "ability"),
                    force_overkill=self.force_overkill)
            ectx.emit("AttackWithAttackDamage", caster=caster, target=tgt,
                      total=(atk or {}).get("total"), attack=atk)
        return OperationResult.ok()


class AttackWithAbilityDamage(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` -> `AttackDamageBehaviour` sur un noeud de degat
    `Direct(...)` : degat DIRECT (base = un `AAmountFormula`) porte sur la cible, route par le SEUL
    percage/armure — AUCUN crit / block / bouclier / spread / tirage RNG / after-hit. Factory NATIVE
    DISTINCTE de `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (l'attaque d'ability crit/block ci-dessus). #149
    slice-19 : la classe Python homonyme precedente mirrorait en realite `AttackWithAttackDamage` et a
    ete RENOMMEE (directive « coller au natif ») — cette classe-ci est la VRAIE `AttackWithAbilityDamage`.

    Seul usage porte = le DoT de tuile `EnvFireTile` (`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour` :
    `Foreach(<occupants non-immunes sur tuile en feu>, AttackWithAbilityDamage(Tiles(@0x180), PercentageOf(
    StatAmount(@0x180, Health=5, Max=2), ConfigConst(fireDmgPct)), Direct(Nullable(3)), source=AbilityOrEffect(
    Fire=5)))`). Wrapper MINCE au-dessus de `AttackDamageOperation.execute_direct` (= l'ancien corps imperatif
    de `FireTileDoT`) → bit-exact BY CONSTRUCTION (meme base, meme percage, meme mutation/mort).

    `amount` = le degat-node `AAmountFormula` (la base ; pour le feu `PercentageOf(fireDmgPct, StatAmount(
    Target(), Health, Max))` — `entities` porte `get_stat`, la base est calculee Fix64 = mirror natif
    `PercentageOf.Calculate`). `profile` = profil de percage (Flame). `is_melee` n'affecte PAS le percage :
    la source est une TUILE sans stats ExtraPierce → `profile_pierce(None, profile)` = PiercingRatio brut.
    `hits` = nb d'applications (defaut 1 = 1 tick, live-valide : net 477 = base 1908 × PiercingRatio Flame
    25%). `source_ref` = l'entite-source pour l'attribution de mort (defaut None → `entities.caster` = la
    tuile). Emet 'AttackWithAbilityDamage'. PUR.

    ⚠ `Direct(Nullable(3))` natif : le `3` n'est PAS le nb de coups (live = 1 tick) ; sa semantique exacte
    (DamageTrait / tag de source) n'est pas RE'd et reste INERTE pour un degat DIRECT (rien a taguer : pas de
    crit/block/after-hit). Non porte (ne change aucun nombre).

    `multi` (case death-nova) = mode MULTI-CIBLE, mirror du `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` que la
    factory native enveloppe TOUJOURS (`IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` = `AbilityDamageBehaviour` +
    `AttackBehaviour(caster, targetsSelector, dmgBehaviour, profile)`) : quand le selecteur resout N unites
    (Explodes/PutridExplosion : tous les adjacents), le behaviour resout la LISTE, l'`OrderBy` (b__5_0,
    cle scalaire par-unite = ordre de lecture) puis attaque CHAQUE cible. Port : `evaluate` -> liste triee
    par `id` (== `AttackWithAttackDamage.multi`, meme mirror). `multi=False` (defaut) = mono-cible
    `resolve_unit` : chemin INCHANGE pour le DoT feu.

    `native_operation` = l'OPERATION native que la feuille route (le `AttackBehaviour` est le meme, c'est
    l'`ADamageBehaviour` enveloppe qui differe cote port) :
      - `"ability"` = `AbilityDamageBehaviour` -> `IdunBattle.Operations.AbilityDamageOperation$$ExecuteHits` +
        `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage` : percage/armure + mods DEFENSEUR + block + bouclier + caps
        (member/Resilient, mode 2), AUCUN crit (la famille ABILITY n'a pas de slot RollCritical, #45f),
        AUCUNE feuille positionnelle (elevation/trench), 0 tirage de valeur (amount FIXE => min==max).
        Port = `execute_ability_attack(base, base, ..., is_attack_damage_op=False)` — MEME route deja
        live-validee bit-exact pour Stormcaller (probe_217) et #45f.
      - `"direct"` (defaut) = route HISTORIQUE du DoT de tuile `EnvFireTile` :
        `AttackDamageOperation.execute_direct` (percage/armure SEULS, mods=None, ni block ni bouclier ni
        cap Resilient). C'est une SIMPLIFICATION heritee, numeriquement equivalente pour une source TUILE
        (pas de crit, cible sans block/bouclier dans les mesures) — conservee telle quelle (zero
        regression sur un chemin live-valide) et documentee comme RESIDU : la migration du feu vers
        `"ability"` est un chantier separe."""
    __slots__ = ("target_sel", "profile", "amount", "is_melee", "hits", "source_ref",
                 "multi", "native_operation")

    def __init__(self, target_sel: TargetsSelector, profile: str, amount, is_melee: bool = True,
                 hits: int = 1, source_ref=None, multi: bool = False,
                 native_operation: str = "direct"):
        self.target_sel, self.profile, self.amount = target_sel, profile, amount
        self.is_melee, self.hits, self.source_ref = is_melee, int(hits), source_ref
        self.multi, self.native_operation = multi, native_operation

    def execute(self, entities, ectx):
        from ...operations.damage import AttackDamageOperation
        from ..base import profile_pierce
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        su = resolve_unit(self.source_ref, entities) if self.source_ref is not None else entities.caster
        src = (su or {}).get("id")
        if src is None:
            return OperationResult.ok()
        if self.multi:                                     # AttackBehaviour.Execute : selecteur -> N cibles
            targets = sorted((u for u in _units_of(self.target_sel, entities)
                              if (u or {}).get("id") is not None), key=lambda u: u.get("id"))
        else:                                              # mono-cible (DoT feu : l'occupant resolu)
            tu = resolve_unit(self.target_sel, entities)
            targets = [tu] if tu and tu.get("id") is not None else []
        for tu in targets:
            tgt = tu.get("id")
            base = int(self.amount.evaluate(entities))     # Fix64 mirror (entities.get_stat -> StatAmount)
            if self.native_operation == "ability":         # AbilityDamageOperation (famille ABILITY)
                se = state.get_entity(src)
                ssc = se.get_component(StatsComponent) if se is not None else None
                pierce = profile_pierce(ssc.ctx if ssc is not None else None, self.profile,
                                        ranged=not self.is_melee)
                atk = AttackDamageOperation.execute_ability_attack(
                    state, src, tgt, base, base, pierce, max(1, self.hits),
                    damage_profile=self.profile, is_melee=self.is_melee,
                    is_attack_damage_op=False,             # famille ABILITY : pas de crit, pas de resolve
                    # etage MULTIPLICATEUR de CBDWAM IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers (slot 0x10 = Round(dmg x mult,
                    # AwayFromZero) IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers) : inconditionnel des que param_7 HasValue, ce qui est
                    # TOUJOURS le cas dans `IdunBattle.Core.Services.DamagePrediction$$CalculateAbilityDamage`. MESURE live (nova
                    # base 200 -> 140, base 201 -> 141 ; floor donnerait 139/140).
                    round_materialize=True)
            else:                                          # route DIRECT historique (DoT feu)
                pierce = profile_pierce(None, self.profile, ranged=not self.is_melee)  # source=tuile : ratio brut
                atk = None
                for _ in range(max(1, self.hits)):
                    atk = AttackDamageOperation.execute_direct(state, src, tgt, base, pierce,
                                                               damage_profile=self.profile)  # #202 : cle "recu ce tour"
            ectx.emit("AttackWithAbilityDamage", source=src, target=tgt,
                      total=(atk or {}).get("total"), attack=atk)
        return OperationResult.ok()


class InformWeapon(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$InformWeapon` -> `ActivateEffectBehaviour` (IdunBattle.Entities.Behaviours.ActivateEffectBehaviour$$Execute) :
    POSE une metadata d'arme (dict {key 0x93 = weaponId derive du profil->nom d'arme, 0x92 = damageProfile,
    0x94 = flag optionnel}) via l'operation 0x2c (`ActivateEffectBehaviour.Execute` itere le dict et applique
    l'op 0x2c a chaque entree). C'est le CANAL weapon-inform : PAS un degat, PAS un stat-mod, PAS un effet
    de combat, AUCUN tirage RNG, AUCUNE mutation de PV/stat -> COMBAT-INERTE (verifie decompile
    `IdunBattle.Entities.Behaviours.ActivateEffectBehaviour$$Execute` = pose de metadata, pas de HealthComponent/StatComponent).

    Consommateurs de ce canal = les triggers on-attack SPECIFIQUES a l'arme (ex. `HazeOfCorruption` du
    deathBlightlord, passif SEPARE hors face COMBAT) + la couche VISUELLE (`FlailSwingVisuals`). Porte pour
    MIRRORER la structure de l'arbre (`op_BitwiseAnd(InformWeapon, AttackWithAttackDamage)`, FlailSwing
    IdunBattleLogic.Entities.Abilities.Active.Loki.FlailSwingAbility$$ExecuteBehaviour) — precedent structurel-no-op : `KillDeadUnits` (ThunderousAssault, mort deja finalisee inline).
    Deterministe et sans effet observable -> n'altere PAS l'ordre `state.rng` de l'attaque qui le suit dans le
    `op_and` : bit-exactness de l'attaque preservee BY CONSTRUCTION. Emet 'InformWeapon' (diagnostic). PUR."""
    __slots__ = ("profile",)

    def __init__(self, profile: str):
        self.profile = profile

    def execute(self, entities, ectx):
        # Canal weapon-inform (metadata) : no-op pour la face COMBAT (HP/degat/effets). Le trigger
        # consommateur (Haze) est un passif separe, hors scope de ce behaviour.
        ectx.emit("InformWeapon", profile=self.profile)
        return OperationResult.ok()


class EvaluateAbilities(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$EvaluateAbilities` -> `IdunBattle.Entities.Behaviours.EvaluateAbilitiesBehaviour$$Execute` (IdunBattle.Entities.Behaviours.EvaluateAbilitiesBehaviour$$.ctor, champ +0x50 = `EventTriggerType`) : EVALUE les abilities DECLENCHEES du CASTER pour un
    `EventTriggerType`, INLINE dans un behaviour-tree. Noeud DSL GENERIQUE du natif (callers : NormalAttack
    `EvaluateAbilities(0x26)`, ArmoriumCherub `EvaluateAbilities(0x4b=AttackInAtomicGroup)`, ArmouredMight/
    TheQuickening). Wrapper MINCE au-dessus de la couche dispatch runner (`evaluate_abilities_for_event`) qui
    rejoue les passifs declenches PORTES de cet event (AttackInAtomicGroup + attaque ranged -> FireOfAbsolution).

    `event` = `EventTriggerType` (int) ; `ranged` = nature de l'attaque du tree (le natif la derive de la
    position — ici fournie par l'ability : ArmoriumCherub est range-2 -> ranged=True, == le `ranged=True`
    litteral de l'ancien imperatif). Emet 'EvaluateAbilities' (la liste de resultats des passifs). PUR."""
    __slots__ = ("event", "ranged")

    def __init__(self, event: int, ranged: bool = False):
        self.event, self.ranged = int(event), ranged

    def execute(self, entities, ectx):
        from ...operations.triggers.dispatch import evaluate_abilities_for_event
        state = ectx.state
        caster = (entities.caster or {}).get("id")
        target = (entities.target or {}).get("id")
        if state is None or caster is None or target is None:
            return OperationResult.ok()
        res = evaluate_abilities_for_event(state, caster, target, self.event, self.ranged) or []
        ectx.emit("EvaluateAbilities", caster=caster, target=target, results=res)
        return OperationResult.ok()


class UseActiveAbility(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$UseActiveAbility` -> `IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$Execute` : pour
    CHAQUE cible du selecteur `targets_sel` (+0x58), le SUJET (`subject_sel`, +0x50) UTILISE son ability
    active `ability_type` (+0x60) -- dispatch RECURSIF de l'ability sur la cible (le natif emet 1 Operation
    <<use-ability>> par cible via le collecteur `proc`, en fixant `subject`=cible courante dans le ctx).

    Seul usage porte (Groupe 3) : FinalJustice `UseActiveAbility(Self@0x148, SortUnitsByDamageUtility(
    ValidNormalAttackTargets(...)), UnitNormalAttackType(self))` = en MOURANT, Kharn porte UNE attaque
    NORMALE sur la meilleure cible. `UnitNormalAttackType` = l'attaque normale du sujet ; chez nous, la
    dispatcher = `AttackDamageOperation.execute` (resolveur d'attaque normale ECS : selection d'arme par
    distance, spread, reduce/armure -- DEJA bit-exact). ⇒ la feuille SPECIALISE le dispatch a l'attaque
    normale (== le corps imperatif `_finaljustice_attack` valide) : `subject`=Caster(), `target`=la cible.

    COLLAPSE du selecteur AI-target (doctrine slice-18/19) : `SortUnitsByDamageUtility(ValidNormalAttack
    Targets)` = un selecteur AI LOURD (kind S, chevauche le playbook), reste IMPERATIF (`_finaljustice
    _target`) et resolu AVANT le cast -> passe comme `Target()` (meme collapse que ThunderousAssault
    `Units(Cache(First(Nearest(...))))` -> la cible du message). DSL-ification du selecteur = tache S-family.

    NON porte / flagge : (1) dispatch d'une ability NON-normale -- aucun usage Groupe 3 ; si un jour une
    ability `UseActiveAbility(<active non-normale>)` apparait, il faudra re-entrer le pipeline d'ability via
    le handler (`visit_ActiveAbilityMessage`), pas `AttackDamageOperation.execute` ; (2) les OPTIONS
    +0x68..+0xac (source AbilityOrEffect, flags) inertes pour une attaque normale. `spread_pct` = variance
    d'arme du dispatch normal (defaut 20 = defaut de `AttackDamageOperation.execute`). Itere les cibles
    triees par id (ordre de lecture natif). Emet 'UseActiveAbility' par cible. PUR (non court-circuitant)."""
    __slots__ = ("subject_sel", "targets_sel", "spread_pct")

    def __init__(self, subject_sel: TargetsSelector, targets_sel: TargetsSelector, spread_pct: int = 20):
        self.subject_sel = subject_sel
        self.targets_sel = targets_sel
        self.spread_pct = int(spread_pct)

    def execute(self, entities, ectx):
        from ...operations.damage import AttackDamageOperation
        state = ectx.state
        subject = resolve_unit(self.subject_sel, entities)
        if state is None or subject is None:
            return OperationResult.ok()
        sid = subject.get("id")
        targets = [u for u in _units_of(self.targets_sel, entities)
                   if isinstance(u, dict) and u.get("id") is not None]
        for tu in sorted(targets, key=lambda x: x["id"]):    # ordre de lecture = id (mirror OrderBy natif)
            tid = tu["id"]
            # DEFENSIF (mirror `execute_ability_attack` IdunBattle.Entities.Behaviours.ChangeStatBehaviour$$Execute+0x360 : rng non cale -> None au lieu de lever) :
            # le wiring d'ability reste utilisable pour un replay EFFET-SEUL (load_state sans dumpRng), la
            # SEQUENCE (setHealth/buffs/move) restant fidele ; le dispatch normal `AttackDamageOperation.
            # execute` leverait sinon (ValueError rng non cale). Un replay de DEGAT cale rng (dumpRng) avant.
            res = None if state.rng is None else AttackDamageOperation.execute(state, sid, tid, self.spread_pct)
            ectx.emit("UseActiveAbility", subject=sid, target=tid, attack=res)
        return OperationResult.ok()
