"""Feuilles DSL d'ATTAQUE runner-couplees : `AttackWithAttackDamage` (attaque d'ability crit/block),
`AttackWithAbilityDamage` (degat DIRECT sans crit/block), `EvaluateAbilities` (evalue les passifs
declenches inline), `UseActiveAbility` (dispatch recursif d'une ability). Wrappers au-dessus de
`runner/operations/damage.py` + `triggers/dispatch.py`. Namespace natif `Entities.Behaviours.*`."""
from __future__ import annotations

from typing import Optional

from ....dsl.base import TargetsSelector, resolve_unit, _units_of, _pos, _is_alive
from ....services.damage_config import resolve_spread_pct
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...components import StatsComponent
from ..base import ability_attack_params
from ...operations.damage import AttackDamageOperation
from ..base import profile_pierce


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
    d'attaque. ORDRE DES TROIS ETAGES, MIRROR STRICT (R28-1, decompile) :

        candidates = source.Select(entities).ToList()   # PickRandomAmountSelector$$Select : AUCUN tri
        picked     = <boucle de tirage sur `candidates`>
        if (picked.Count > 1) picked.OrderBy(b__5_0)    # AttackBehaviour$$Execute, APRES la resolution

    -> le port evalue le selecteur, TIRE dans l'ordre SOURCE (celui que rendent les selecteurs
    d'occupation = l'ordre des TUILES, cf. `_tile_enum_rank`), PUIS trie par id. Le tri par id AVANT le
    tirage qui existait ici jusqu'au 2026-07-27 n'avait aucun homologue natif : il ecrasait l'ordre
    source et decidait donc QUI etait pique des que `|pool| > n`.
    #130 : la CONSOMMATION rng du pick est EXACTE meme quand le pool tient dans `n`
    (`min(len(pool), n)` tirages, bornes decroissantes -- cf. `_pick_randomly_n`) ; confronte live
    bit-exact sur PlasmaCannon (`probe_215_pick_randomly_rng.py`).

    `tile_domain` = le selecteur de cibles rend des ENTITES-TUILE (ids), pas des unites -- Fragstorm :
    `PickRandomly(AdjacentTiles(target) − Tiles(Friends), 4)` echantillonne des HEXES, tuiles VIDES
    INCLUSES. Le natif ne resout l'occupant qu'a `AttackDamageBehaviour$$ExecuteTarget`, APRES le
    tirage et APRES l'`OrderBy` : une tuile piquee sans occupant est un COUP GASPILLE. Le port mirror
    l'ordre exact : evaluate -> ids de tuile -> pick -> `OrderBy` par id de tuile -> occupant vivant de
    chaque tuile (aucun -> rien) -> attaque. Requiert `multi=True` et un `state.board`.
    2e consommateur : `IdunBattleLogic.Entities.Abilities.Active.Loki.BasiliskBarrageAbility$$ExecuteBehaviour`
    (`AttackWithAbilityDamage(caster@0x160, <tuiles d'impact des obus>, ...)`), qui exerce en plus
    deux proprietes du meme etage : les **DOUBLONS sont conserves** (`allowRepeat=1` -> deux obus sur
    la meme tuile = deux attaques sur son occupant ; `sorted` les garde adjacents) et les tuiles VIDES
    sont MESUREES live (tag `Damage_Empty_Target_Tile_Id`) -> emit DIAGNOSTIQUE `AttackEmptyTile`.
    RESIDU NOMME : les deux gates par-cible d'`AbilityDamageBehaviour` -- `UnitExtensions.IsTargetable`
    et `HasTrait(0x40e = UnitTrait.Invincible)` -- ne sont PAS portes (l'occupant resolu est deja
    VIVANT ; aucun porteur d'`Invincible` dans un roster de duel).

    `amount` = FOLD du degat-node `Direct(amountFormula)` quand le natif passe une **valeur calculee** a
    `AttackWithAttackDamage` en lieu de bornes d'arme (`MinMaxDamage`) — ex. Psyker
    `PercentageOf(StatAmount(Self, Attack), psykerExtraDmg%)` IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$CreateBehaviour. Defaut None = mode bornes
    (`ability_attack_params`). Quand fourni (un `AAmountFormula`), la feuille calcule `base =
    amount.evaluate(entities)` (Fix64, mirror natif — `entities` porte `get_stat` pour `StatAmount`) et route
    via `AttackDamageOperation.execute_normal_like(base, pierce=profile_pierce, hits, spread_pct=...)`, meme
    pipeline reduce/crit/block/after-hit que l'attaque normale. La VARIANCE du montant est pilotee par
    `amount_spread_pct` (cf. ci-dessous), PAS deduite du node.
    `hits` = nb de coups EXPLICITE du degat-node (defaut 1 en mode `amount` ; en mode bornes, None → `hits`
    de la config via `ability_attack_params`, sinon OVERRIDE la config `nrOfHits` — cas d'une ability dont le
    natif passe un nb de coups CALCULE a `AttackWithAttackDamage` en lieu de `GetNumberConstant(0x2f)` : ex.
    Executioner `hits = IdunBattleLogic.Entities.DSLFactory$$RoundsStarted` = valeur DYNAMIQUE lue au cast, PAS une constante config)."""
    __slots__ = ("target_sel", "ability_id", "profile", "is_melee", "min_key", "max_key", "hits_key",
                 "damage_override", "multi", "pick_n", "amount", "hits", "ability_type", "hits_add_key",
                 "native_factory", "force_overkill", "hits_override", "level_slot", "tile_domain",
                 "force_crit", "is_first_hit", "amount_spread_pct")

    def __init__(self, target_sel: TargetsSelector, ability_id: str, profile: str, is_melee: bool = True,
                 min_key: str = "minDmg", max_key: str = "maxDmg", hits_key: str = "nrOfHits",
                 damage_override=None, multi: bool = False, pick_n=None, amount=None, hits=None,
                 ability_type=None, hits_add_key=None, native_factory: str = "attack",
                 force_overkill: bool = False, hits_override=None, level_slot: str = "active",
                 tile_domain: bool = False, force_crit: bool = False,
                 is_first_hit: bool = True, amount_spread_pct: int = 0):
        # case-221 : `IsFirstHitInSeries()` = `AbilityEntities.IsFirstHit` = `hitIndex == 0`. Quand un
        # SEUL `IdunBattle.Entities.Behaviours.AttackBehaviour` porte N feuilles `AttackDamage`
        # (`HazeOfCorruption_DamageTransferEffect$$CreateTargetTriggerBehaviour` : une feuille par
        # `LeftOverDamage`), le hitIndex court d'une feuille a l'autre -> seule la PREMIERE porte le
        # drapeau. Le port instancie une feuille par transfert, donc l'appelant le lui dit.
        self.is_first_hit = bool(is_first_hit)
        self.tile_domain = bool(tile_domain)
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
        # Accepte un INT (valeur deja resolue par la classe d'ability) **ou un NOEUD `AAmountFormula`** :
        # le 6e argument natif d'`IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` est un NOEUD
        # (`AttackDamageBehaviour+0x80`, EVALUE par
        # `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget`) — passer le noeud le laisse
        # s'evaluer A L'EXECUTION contre l'`entities` du behaviour, ce qu'exige un arbre dont un `Cache` a ete
        # FIGE en amont par un `SetCache` (FrenziedFiring : `SetCache(hitsNode) & Attack(..., hits=hitsNode)`).
        self.hits_override = hits_override
        # `force_crit` = octet **+5** du `Nullable<AttackOptions>` (8e arg d'`AttackWithAttackDamage`,
        # le meme struct dont l'octet +4 porte `force_overkill`) : « always crit ». Le natif
        # (`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`) SAUTE alors `RollCritical` ->
        # chaque coup est critique SANS tirage, meme a `CouldCrit` faux. Defaut False. Mode bornes
        # uniquement (route par `execute_ability_attack`). Porteur : TacticalPrecision (1154) branche
        # CHARGE -- i2 « This attack is always a Crit and deals an additional +extraCritDmg ».
        self.force_crit = force_crit
        # `amount_spread_pct` (#226-r) = VARIANCE appliquee au montant du mode `amount`.
        #   0  (DEFAUT) : montant MONO-valeur, aucune variance d'arme. C'est le cas du smite Psyker
        #                 (`IdunBattleLogic.Entities.Abilities.Active.Loki.PsykerExtraAttackAbility$$
        #                 CreateBehaviour` : le 8e argument `Nullable<AttackDamageBehaviourOptions>` est
        #                 passe VIDE -- `local_78..local_58 = 0`, HasValue=0) et du transfert HazeOfCorruption.
        #   20        : le montant est traite comme une BASE D'ARME -> `IdunBattle.Core.Services.
        #                 DamagePrediction$$GetBaseDamageFix64` etale les BORNES de +-DamageSpreadPercentage
        #                 avant le tirage (reduce-then-roll, 1 tirage/coup) = LE pipeline de l'attaque NORMALE.
        # Ce que le DECOMPILE distingue : l'OCTET +6 du `Nullable<AttackDamageBehaviourOptions>` (le meme
        # struct dont +4 porte `alwaysOverkilled` et +5 `alwaysCrit`).
        #   * `IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$
        #     GetAttackDamageBehaviour` ECRIT cet octet depuis un getter booleen de l'ability
        #     (`local_1d8._0_7_ = CONCAT16(<slot 0x4b8>, ...)`) -> c'est le drapeau « ce coup est
        #     l'attaque NORMALE / utilise le calcul de degat d'arme ».
        #   * `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` le pose
        #     a **1** en dur (`uStack_1e2 = 1`, seul octet non nul de la struct) ; Psyker passe le Nullable VIDE.
        # Il transite `AttackDamageBehaviour+0x9e` -> `AttackDamageOperation$$ExecuteHit` (options+0x2f) ->
        # `AttackPredictionRequest+0x6a` -> slot 4 `IdunBattle.Core.Services.DamagePrediction$$PredictAttack`.
        # MESURE bit-exacte (`probe_226r_skystrike_spread.py`, meme etat + meme rng dumpe) : SkyStrike live
        # = [3334, 3156, 2477] == `execute_normal_like(V, spread_pct=20)` 3/3, != bornes degenerees (V,V)
        # et != bornes brutes roll-then-reduce. Defaut 0 => strict no-op pour les call-sites existants.
        #
        # ⚠ Le DEFAUT 0 est PORTEUR DE SENS, donc invisible a tout grep (#449-r2) : deux des trois
        # porteurs a variance nulle (`triggers/loki/psyker.py`, `triggers/loki/haze_of_corruption.py`)
        # ne l'ECRIVENT PAS -- ils le prennent ici. L'inventaire de ce parametre se fait par AST sur les
        # CALL-SITES (`probe_449r2_spread_inventory.py`, dans la banque de cliquets), jamais sur le texte
        # du mot-cle : mesure du 2026-08-02, `spread_pct=0` rend 6 lignes dans `engine/` dont UNE SEULE
        # executable. Tout nouveau call-site en mode `amount` doit LIRE le 8e argument
        # `Nullable<AttackDamageBehaviourOptions>` de son `CreateBehaviour` natif et inscrire sa raison.
        self.amount_spread_pct = int(amount_spread_pct)

    def execute(self, entities, ectx):
        state = ectx.state
        caster = (entities.caster or {}).get("id")
        if state is None or caster is None:
            return OperationResult.ok()
        if self.multi and self.tile_domain:                 # selecteur d'ENTITES-TUILE (Fragstorm)
            tiles = [t for t in _units_of(self.target_sel, entities) if isinstance(t, int)]
            if self.pick_n is not None:                     # PickRandomly sur les HEXES, tuiles vides incluses
                from ..loki import _pick_randomly_n
                tiles = _pick_randomly_n(state, tiles, int(self.pick_n))
            tiles = sorted(tiles)                           # OrderBy (b__5_0) sur l'id d'entite-tuile
            # occupant VIVANT de chaque tuile piquee (`AttackDamageBehaviour$$ExecuteTarget` resout la
            # cible APRES le tirage) ; tuile vide = COUP GASPILLE -> aucune attaque.
            targets = []
            board = state.board
            occ = {}
            if board is not None:
                for u in entities.units:
                    p = _pos(u) if _is_alive(u) else None
                    if p is None:
                        continue
                    tid = board.id_at(p[0], p[1])
                    if tid is not None and tid not in occ:
                        occ[tid] = u
            for t in tiles:
                u = occ.get(t)
                if u is not None and u.get("id") is not None:
                    targets.append(u)
                else:
                    # Tuile SANS occupant : `AbilityDamageBehaviour$$Execute` n'attaque pas et n'emet
                    # que l'operation VISUELLE 0x25 (tag live `Damage_Empty_Target_Tile_Id`). Porte en
                    # emit DIAGNOSTIQUE (aucune mutation) -> les tests peuvent confronter au live les
                    # obus tombes a vide (BasiliskBarrage 1026), qui sont le gros du signal quand la
                    # zone est peu peuplee.
                    ectx.emit("AttackEmptyTile", caster=caster, tile=t)
        elif self.multi:                                   # AttackBehaviour.Execute : selecteur -> N cibles
            targets = [u for u in _units_of(self.target_sel, entities)
                       if (u or {}).get("id") is not None]   # ordre SOURCE (aucun tri avant le tirage)
            if self.pick_n is not None:                    # PickRandomly(selecteur, n) folde (state.rng)
                from ..loki import _pick_randomly_n
                targets = _pick_randomly_n(state, targets, int(self.pick_n))
            # `OrderBy` (b__5_0) de `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
            # (`if (Count > 1) targets.OrderBy(b__5_0).ToList()`) : APRES la resolution du selecteur.
            targets = sorted(targets, key=lambda u: u.get("id"))
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
                atk = AttackDamageOperation.execute_normal_like(  # variance pilotee par l'octet +6 des options
                    state, caster, tgt, base, pierce,
                    hits=int(self.hits) if self.hits is not None else 1,
                    spread_pct=self.amount_spread_pct,
                    damage_profile=self.profile, is_melee=self.is_melee,
                    ability_type=self.ability_type,
                    # meme classification que le mode bornes (cf. `native_factory`) : elle pilote
                    # l'ordre bouclier x limites (`CalculateAbilityDamage` cape le RESTE post-bouclier).
                    is_attack_damage_op=(self.native_factory != "ability"),
                    is_first_hit=self.is_first_hit)
            else:
                # `BaseEffect$$PiercingBonusForAttack` : les effets ACTIFS du caster peuvent ajouter au
                # ratio de perçage du coup (gates `OwnerIsCaster` / `CurrentAbilityIs` / `HasTrait(target)`
                # -> le contexte a besoin de la CIBLE, donc calculé ICI et non dans la config).
                from ..base import ability_pierce_effect_bonus
                pbonus = ability_pierce_effect_bonus(state, caster, tgt, self.ability_type,
                                                     is_ranged=not self.is_melee)
                bmin, bmax, pierce, hits = ability_attack_params(
                    state, caster, self.ability_id, self.profile, ranged=not self.is_melee,
                    min_key=self.min_key, max_key=self.max_key, hits_key=self.hits_key,
                    hits_add_key=self.hits_add_key, level_slot=self.level_slot,
                    pierce_effect_bonus=pbonus)
                if self.hits is not None:                  # hits DYNAMIQUE (Executioner RoundsStarted) override config nrOfHits
                    hits = int(self.hits)
                elif self.hits_override is not None:       # coups = NODE dynamique (SkyStrike MeleeWeaponHits)
                    # Noeud `AAmountFormula` (6e arg natif de `AttackWithAttackDamage`) -> EVALUE ICI, comme
                    # `AttackDamageBehaviour$$ExecuteTarget` ; un int deja resolu passe tel quel.
                    hits = int(self.hits_override.evaluate(entities)
                               if hasattr(self.hits_override, "evaluate") else self.hits_override)
                if self.damage_override is not None:       # GetAttackDamage surchargee (ex. SpiritLeech +extraDmg)
                    bmin, bmax = self.damage_override(state, caster, tgt, bmin, bmax)
                atk = AttackDamageOperation.execute_ability_attack(
                    state, caster, tgt, bmin, bmax, pierce, hits,
                    damage_profile=self.profile, is_melee=self.is_melee,
                    ability_type=self.ability_type,
                    is_attack_damage_op=(self.native_factory != "ability"),
                    force_overkill=self.force_overkill, force_crit=self.force_crit)
            ectx.emit("AttackWithAttackDamage", caster=caster, target=tgt,
                      total=(atk or {}).get("total"), attack=atk)
        return OperationResult.ok()


class SortedAttackSeries(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$SortedAttackSeries(actor, sel1, atk1, sel2, atk2, source)` ->
    `IdunBattle.Entities.Behaviours.SortedAttackSeriesBehaviour$$Execute` -- MIRROR du decompile.

    CHAMPS (mapping factory -> `.ctor` LU) : `+0x50` selecteur d'ACTEUR · `+0x58` tableau de 2 paires
    `(selecteur, behaviour)` (`[0] = (sel1, atk1)`, `[1] = (sel2, atk2)`) · `+0x60..0x70` `AbilityOrEffect`.

    `$$GetAttacks(entities)` (MIRROR) :

        dict = new Dictionary<UnitEntity, List<behaviour>>()
        foreach (sel, beh) in pairs:                 # DANS L'ORDRE DU TABLEAU
            if sel == null or beh == null: continue
            foreach u in sel.Select(entities):       # DANS L'ORDRE DU SELECTEUR
                if dict.TryGetValue(u, out l): l.Add(beh) else dict[u] = [beh]
        return dict

    `$$Execute(entities, proc)` (MIRROR) :

        foreach (unit, behs) in GetAttacks(entities):        # ordre d'INSERTION du Dictionary
            foreach beh in behs:
                actor = (+0x50).SelectSingle(entities)
                if unit != prevUnit:                          # frontiere de SERIE
                    if prevUnit != null: proc.Op(0x3b, prevActor, prevUnit, ctx)   # EndAttackSeries
                    proc.Op(0x3a, actor, unit, ctx)                                # StartAttackSeries
                entities[slot 4] = unit                       # == ActiveTarget@0x180
                result.Combine(beh.Execute(entities))
        if prevUnit != null: proc.Op(0x3b, ...)

    DEUX consequences STRUCTURELLES, et c'est tout l'interet du noeud :
      1. **AUCUN `OrderBy`** (contraste `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`, qui
         trie quand `Count > 1`) : l'ordre d'attaque -- donc la SEQUENCE DE TIRAGES `state.rng` -- est
         l'ordre d'INSERTION, c'est-a-dire selecteur 1 puis selecteur 2, chacun dans SON ordre.
      2. **la cible est passee par `ActiveTarget@0x180`** : les behaviours d'attaque du tableau ciblent
         `ActiveTarget()`, que ce noeud RELIE avant chaque execution (une unite presente dans les DEUX
         selecteurs recevrait les DEUX attaques, consecutivement).
    Les operations `0x3a`/`0x3b` (Start/EndAttackSeries) sont des bornes d'ANIMATION : aucune mutation
    d'etat, aucun tirage -> non portees (meme classe de no-op structurel que `InformWeapon`/`Inform`).

    `pairs` = liste de `(TargetsSelector, AbilityBehaviour)`. Emet 'SortedAttackSeries' (ordre resolu,
    diagnostic). PUR."""
    __slots__ = ("pairs",)

    def __init__(self, pairs):
        self.pairs = list(pairs)

    def execute(self, entities, ectx):
        from dataclasses import replace
        order: list = []                                   # ids, dans l'ORDRE D'INSERTION du Dictionary
        by_id: dict = {}
        for sel, beh in self.pairs:                        # `GetAttacks` : parcours du tableau +0x58
            if sel is None or beh is None:
                continue
            for u in _units_of(sel, entities):
                uid = (u or {}).get("id")
                if uid is None:
                    continue
                if uid not in by_id:
                    by_id[uid] = (u, [])
                    order.append(uid)
                by_id[uid][1].append(beh)
        for uid in order:
            u, behs = by_id[uid]
            ents = replace(entities, active_target=u)      # `entities[slot 4] = unit` (ActiveTarget)
            for beh in behs:
                beh.execute(ents, ectx)
        ectx.emit("SortedAttackSeries", order=list(order))
        return OperationResult.ok()


class ChainLeftOverHitsAttackDamage(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$ChainLeftOverHitsAttackDamage` ->
    `IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$Execute` — MIRROR du decompile.

    CHAMPS (mapping factory -> `..ctor` LU, pas devine) : `+0x58` caster · `+0x60` cible INITIALE ·
    `+0x68` noeud de degat (`MinMaxDamage`) · `+0x70..0x80` `AbilityOrEffect` de la source · `+0x88`
    selecteur de CIBLE SUIVANTE · `+0x90` noeud `extraHits` · `+0x98` noeud `hits` · `+0xa0` noeud profil.

    BOUCLE NATIVE (`$$Execute`) :

        hits   = (+0x98).Calculate(entities)
        target = (+0x60).SelectSingle(entities)
        guard  = 100
        if hits > 0:
            while guard > 0 and target != null:
                <behaviour d'attaque construit a la volee : caster=+0x58, cible=Entity(target),
                 degat=+0x68, profil=+0xa0, hits=Direct(hits), source=+0x70> .Execute(entities)
                entities[slot 4] = target                     # == ActiveTarget@0x180
                hits   = GetLeftOverHits(this, target, entities)
                target = (+0x88).SelectSingle(entities)       # cible suivante, ActiveTarget = la precedente
                if hits == 0 : return
                guard -= 1
                if hits < 1  : return

    `$$GetLeftOverHits(this, target, entities)` (MIRROR) :

        list  = target.GetComponent<...>.LeftOverDamages (+0x90)
        count = # d'entrees dont le FLAG est vrai ET dont l'AbilityOrEffect == la notre
        if list.Count > 0 and (+0x90) != null : count += (+0x90).Calculate(entities)   # extraHits
        return count

    D'ou viennent les entrees, lu dans `IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` et ses
    TROIS call-sites de `$$Execute` : (a) cible portant DEJA le flag de mort (`UnitExtensions.HasFlag(.., 8)`)
    -> entree, flag litteral **1** ; (b) coup FATAL (`HealthComponent.IsDead` APRES application) -> entree
    portant le RESTE d'overkill (`Damage(requested - applied)`), flag = `IsDead` **AVANT**, donc **0**.
    `list.Count > 0` (donc >= 1 entree) declenche le `+ extraHits` — c'est le canal du « +1 coup par ennemi
    tue » de l'i2 (`extraHits` = `Get(GetNumberConstant(0x2b) = extraHit)` = 1).

    ⚠ COMBIEN d'entrees COMPTE le predicat de flag : cf. `_left_over_hits` — le report vaut
    `max(0, H - k - 1) + extraHits` (H = coups appliques, k = index du coup fatal), et **0** si la cible
    survit. La lecture « report CONSTANT = 1 + extraHits des que la cible meurt » (#116) etait calibree
    sur un SEUL regime (PV 8000 -> k=5) et cassait des que k <= 3 (#122) : elle est REFUTEE par
    `probe_125_leftover_hits.py --mode sweep` (4 regimes, table dans `_left_over_hits`).

    FLUX `state.rng` DES COUPS GASPILLES (#125) : le natif ROULE bien TOUS ses `hits` coups, y compris
    ceux qui tombent sur un cadavre. `IdunBattle.Operations.AttackDamageOperation$$ExecuteHits` est une
    boucle `while (i < hits)` SANS aucune sortie anticipee sur la mort de la cible, et les trois tirages
    d'un coup (`IdunBattle.Core.HitDamage$$GetDamage`, `IdunBattle.Core.Services.DamagePrediction$$RollCritical`,
    `IdunBattle.Core.Services.DamagePrediction$$RandomlyResolveMinMaxDamage`) sont consommes dans
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` **avant** la sous-operation 0x42
    (`IdunBattle.Operations.ApplyDamageOperation$$Execute`), seul endroit ou un cadavre court-circuite.
    Le port fait pareil (`_run_hits` boucle sur `hits` sans gate de mort) -> AUCUN desalignement de flux
    de ce fait. RESIDU nomme : sur un cadavre DEJA `UnitFlag.Overkilled`, `ApplyDamageOperation$$Execute`
    retourne AVANT les jets de block/esquive qu'il porte, alors que le port les joue encore — no-op tant
    que la cible n'a aucune source de block (cas mesures), sinon 1 tirage d'ecart par coup gaspille.

    PORT : l'attaque d'une iteration passe par l'Operation deja bit-exacte
    `AttackDamageOperation.execute_ability_attack` (memes bornes/profil/percage/`state.rng`, meme
    consommation per-coup) ; l'etat vital est DERIVE de son retour (`per_hit_health` + `hp_before`, exposes
    pour ce port) : on rejoue la sequence PV coup par coup pour savoir SI et A QUEL coup la cible tombe. Le
    port applique le degat en UN bloc la ou le natif cesse d'appliquer sur un cadavre : aucune difference
    observable (la cible est morte des deux cotes, PV clampes a 0). Seul le `total` rapporte pour
    l'iteration fatale est sur-estime (diagnostic).

    `caster_sel`/`target_sel`/`next_target_sel` = les 3 selecteurs natifs ; `hits`/`extra_hits` = les 2
    noeuds VALEUR (int ou `AAmountFormula`). `MAX_ITERATIONS` = la garde native `100`. Emet
    'ChainLeftOverHitsAttackDamage' par iteration. PUR."""
    __slots__ = ("caster_sel", "target_sel", "next_target_sel", "ability_id", "profile", "hits",
                 "extra_hits", "is_melee", "native_factory", "min_key", "max_key")

    MAX_ITERATIONS = 100                     # garde native (`iVar19 = 100`)

    def __init__(self, caster_sel: TargetsSelector, target_sel: TargetsSelector,
                 next_target_sel: TargetsSelector, ability_id: str, profile: str, hits,
                 extra_hits, is_melee: bool = False, native_factory: str = "attack",
                 min_key: str = "minDmg", max_key: str = "maxDmg"):
        self.caster_sel, self.target_sel, self.next_target_sel = caster_sel, target_sel, next_target_sel
        self.ability_id, self.profile = ability_id, profile
        self.hits, self.extra_hits = hits, extra_hits
        self.is_melee, self.native_factory = is_melee, native_factory
        self.min_key, self.max_key = min_key, max_key

    @staticmethod
    def _left_over_hits(atk: dict, extra: int) -> int:
        """`IdunBattle.Entities.Behaviours.ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits` —
        `count` = nb d'entrees `LeftOverDamages` (composant de la CIBLE, champ +0x90) dont le FLAG
        (`IdunBattle.Core.LeftOverDamage$$.ctor` param_4 -> champ +0x7c) est vrai ET dont
        l'`AbilityOrEffect` (+0x18) egale la notre (+0x70) ; `+ extraHits` (noeud +0x90) des que
        `list.Count > 0` — donc des qu'il existe AU MOINS UNE entree, quel que soit son flag.

        LOI PORTEE (H = coups APPLIQUES, k = index 1-based du coup qui met la cible a 0 PV) :

            cible SURVIVANTE                -> 0            (aucune entree, pas meme le `+ extraHits`)
            tuee au coup k                  -> max(0, H - k - 1) + extraHits
            deja morte a l'entree           -> H + extraHits          (modelise, non confronte)

        MESURE LIVE (`probe_125_leftover_hits.py --mode sweep`, seed 4242, board MC1_67, chaine
        MultiThreatEliminator ; le report est FORCE maillon par maillon et le tuple est confronte au
        per-coup LIVE du maillon dont la cible SURVIT — seul maillon ou le per-coup live n'est ni
        clampe par les PV ni tronque) :

            PV 1re cible | k | report LIVE mesure | max(0,H-k-1)+1
            ------------ | - | ------------------ | ---------------
            2500         | 2 | 4                  | 4
            3000         | 2 | 4                  | 4
            4000         | 3 | {1,2,3} (LightCover ecrase) | 3
            10000        | 6 | >= 1 (le 2e maillon EST frappe) | 1

        Les regimes 2500 et 3000 ont le MEME k et un index d'overkill DIFFERENT (3 vs 4, lisible au nb
        d'events : `ApplyDamageOperation$$Execute` retourne des l'entree sur
        `UnitExtensions.HasFlag(target, UnitFlag.Overkilled = 8)` -> les coups suivants n'emettent plus
        rien) et donnent le MEME report 4 : le report depend de **k**, pas de l'index d'overkill. Le
        regime 10000 (k = H, AUCUN coup gaspille) rend >= 1 : c'est lui qui pin le terme `+ extraHits`
        (`extraHit` = 1 en gameconfig pour 1006).

        ⚠ ECART LECTURE/MESURE, documente : les TROIS call-sites d'`ApplyDamageOperation$$AddLeftoverHit`
        lus au decompile — (a) `HasFlag(target, Overkilled)` -> entree flag LITTERAL 1 puis `return` ;
        (b) `Damage.GetTotal(requested) > 0 && HealthComponent.IsDead(apres)` -> flag = `IsDead` AVANT ;
        (c) reste d'overkill (`requested - applied`), meme flag — predisent `H - k` entrees flag-vrai
        (un coup sur cadavre = `IsDead` avant = vrai, et `HealthComponent$$IsDead` est bien
        `CurrentValue < 1 && CurrentMaximumValue > 0`, sans differe). La mesure en donne **une de
        moins**. Exactement UN coup-sur-cadavre ne laisse donc pas d'entree comptee ; la mesure ne dit
        pas LEQUEL (le 1er coup sur le cadavre et le coup d'OVERKILL coincident sur les 4 regimes) —
        residu nomme, pas un scalaire fitte : la loi est entiere et confrontee sur 4 regimes dont deux
        qui separent k de l'index d'overkill.

        AVANT ce port, le branche « tuee » rendait `1 + extraHits` en dur (mesure #116 lue sur un SEUL
        regime, PV 8000 -> k=5, H=6, ou `1` se trouve etre `max(0,H-k-1)+1 - 1`... et surtout ou le
        malus `LightCover` du maillon suivant ecrase 1 et 2 sur la MEME valeur appliquee) : d'ou le
        bit-exact trompeur de #116 et la divergence de #122 des que k <= 3."""
        per_hit = list(atk.get("per_hit_health") or [])
        if not per_hit:
            return 0
        hp = int(atk.get("hp_before") or 0)
        if hp <= 0:                       # (a) deja morte : chaque coup tombe sur le cadavre
            return len(per_hit) + int(extra)
        for i, h in enumerate(per_hit):   # (b) l'attaque tue-t-elle, et A QUEL coup
            hp -= int(h)
            if hp <= 0:
                return max(0, len(per_hit) - (i + 1) - 1) + int(extra)
        return 0                          # cible SURVIVANTE -> AUCUNE entree -> pas de `+ extraHits`

    def execute(self, entities, ectx):
        from dataclasses import replace
        state = ectx.state
        cu = resolve_unit(self.caster_sel, entities)
        caster = (cu or {}).get("id")
        if state is None or caster is None:
            return OperationResult.ok()
        hits = int(self.hits.evaluate(entities) if hasattr(self.hits, "evaluate") else self.hits)
        extra = int(self.extra_hits.evaluate(entities) if hasattr(self.extra_hits, "evaluate")
                    else self.extra_hits)
        tu = resolve_unit(self.target_sel, entities)
        bmin, bmax, pierce, _cfg_hits = ability_attack_params(
            state, caster, self.ability_id, self.profile, ranged=not self.is_melee,
            min_key=self.min_key, max_key=self.max_key)
        guard = self.MAX_ITERATIONS
        chain: list = []
        while hits > 0 and guard > 0 and tu is not None and tu.get("id") is not None:
            tgt = tu.get("id")
            atk = AttackDamageOperation.execute_ability_attack(
                state, caster, tgt, bmin, bmax, pierce, hits,
                damage_profile=self.profile, is_melee=self.is_melee,
                is_attack_damage_op=(self.native_factory != "ability"))
            if atk is None:                              # rng non cale : degradation fidele (cf. #217)
                break
            # `hits` = la BASE passee a l'Operation ; `applied_hits`/`per_hit` = ce que la FORMULE de
            # coups partagee (`AttackHitsWithModifiersFormula$$Calculate`, traversee par la famille
            # ATTACK) a REELLEMENT applique -- les deux different des que la cible porte un malus de
            # coups (Parry/LightCover/Camouflage). Exposes pour la confrontation par maillon (#122).
            # `per_hit_health`/`hp_before` exposes DANS le maillon (additif, #125) : ce sont les DEUX
            # entrees de `_left_over_hits` -- un probe/test qui veut recalculer le report doit lire la
            # part PV, pas `per_hit` (qui somme PV + bouclier + armure-pool).
            chain.append({"target": tgt, "hits": hits, "applied_hits": atk.get("hits"),
                          "per_hit": atk.get("per_hit"),
                          "per_hit_health": atk.get("per_hit_health"),
                          "hp_before": atk.get("hp_before"),
                          "total": atk.get("total"), "attack": atk})
            ectx.emit("ChainLeftOverHitsAttackDamage", caster=caster, target=tgt, hits=hits,
                      total=atk.get("total"), attack=atk)
            hits = self._left_over_hits(atk, extra)      # GetLeftOverHits
            # `entities[slot 4] = target` AVANT d'evaluer le selecteur de cible suivante (== ActiveTarget)
            entities = replace(entities, active_target=tu, subject=tu)
            tu = resolve_unit(self.next_target_sel, entities)
            guard -= 1
        ectx.emit("ChainLeftOverHits", chain=[{k: v for k, v in c.items() if k != "attack"}
                                              for c in chain])
        return OperationResult.ok()


class AttackWithAbilityDamage(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` (LU) -> `IdunBattle.Entities.Behaviours.
    AbilityDamageBehaviour$$.ctor` + `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor` : famille ABILITY
    (`IdunBattle.Operations.AbilityDamageOperation`), factory NATIVE DISTINCTE de
    `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` (l'attaque d'ability crit/block ci-dessus). #149
    slice-19 : la classe Python homonyme precedente mirrorait en realite `AttackWithAttackDamage` et a
    ete RENOMMEE (directive « coller au natif ») — cette classe-ci est la VRAIE `AttackWithAbilityDamage`.

    ⚠ Le nom natif `AttackWithAbilityDamage` et le noeud `Direct(...)` de son 3e argument ont longtemps fait
    lire cette factory comme « degat DIRECT » (= `IdunBattle.Operations.DirectDamageOperation`). C'est FAUX :
    `Direct(...)` est un noeud de DEGAT (une formule a valeur fixe), pas une Operation ; le corps de la
    factory construit `AbilityDamageBehaviour` + `AttackBehaviour`, jamais un `DirectDamageOperation`.

    Usages portes : le DoT de tuile `EnvFireTile`
    (`IdunBattleLogic.Entities.Abilities.Active.Loki.EnvFireTileAbility$$CreateBehaviour` :
    `Foreach(<occupants non-immunes sur tuile en feu>, AttackWithAbilityDamage(Tiles(@0x180), @0x180,
    PercentageOf(StatAmount(@0x180, Health=5, Max=2), ConfigConst(fireDmgPct)), AbilityOrEffect(Fire=5),
    {0, Direct(Nullable(3))}))`) et la nova de mort `PutridExplosion` (mode `multi`).

    `amount` = le degat-node `AAmountFormula` (la base ; pour le feu `PercentageOf(fireDmgPct, StatAmount(
    Target(), Health, Max))` — `entities` porte `get_stat`, la base est calculee Fix64 = mirror natif
    `PercentageOf.Calculate`). `profile` = profil de percage (Flame). `is_melee` = la nature DECLAREE du coup
    (`attackRangeType` ; **None** = absent -> `IsMeleeAttack` et `IsRangedAttack` tous deux FAUX, cas du DoT
    de tuile dont l'`AbilityOrEffect` est l'EFFET Fire) ; il n'affecte PAS le percage quand la source est une
    TUILE sans stats ExtraPierce (`profile_pierce(None, profile)` = PiercingRatio brut).
    `hits` = nb d'applications (defaut 1 = 1 tick, live-valide : net 477 = base 1908 × PiercingRatio Flame
    25%). `source_ref` = l'entite-source pour l'attribution de mort (defaut None → `entities.caster` = la
    tuile). Emet 'AttackWithAbilityDamage'. PUR.

    ⚠ `Direct(Nullable(3))` natif = le champ +0x90 de l'`AbilityDamageBehaviour`, evalue par
    `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$ExecuteTarget` dans une cellule de l'AttackData
    (les champs voisins +0x98 = nrOfHits, defaut 1, et +0xa0 = ability id sont NULS pour le feu). Le `3`
    n'est PAS le nb de coups (live = 1 tick) ; sa semantique exacte n'est pas RE'd et reste INERTE (aucun
    nombre porte n'en depend).

    `multi` (case death-nova) = mode MULTI-CIBLE, mirror du `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` que la
    factory native enveloppe TOUJOURS (`IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage` = `AbilityDamageBehaviour` +
    `AttackBehaviour(caster, targetsSelector, dmgBehaviour, profile)` ; `Execute` resout +0x50 = le CASTER en
    UNE entite — `SelectOne` — et +0x58 = la LISTE des cibles) : quand le selecteur resout N unites
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
      - `"direct"` = `AttackDamageOperation.execute_direct`, mirror de `IdunBattle.Operations.
        DirectDamageOperation` / `IdunBattle.Core.Services.DamagePrediction$$CalculateDirectDamage`
        (percage/armure SEULS, mods=None, ni block ni bouclier ni cap Resilient). PLUS AUCUN
        CONSOMMATEUR depuis la migration du DoT de tuile `EnvFireTile` vers `"ability"` : la factory
        native `AttackWithAbilityDamage` ne construit JAMAIS un `DirectDamageOperation` (elle construit
        `AbilityDamageBehaviour` + `AttackBehaviour`, LU). Le mode reste expose pour le jour ou une
        feuille mirrorera vraiment `DirectDamageOperation` ; il n'est plus le defaut.

    MIGRATION du DoT de tuile (residu STRUCTUREL clos) : le port routait le feu sur `"direct"`, ce qui
    est numeriquement equivalent tant que la cible n'a ni bouclier, ni block, ni cap de trait — mais FAUX
    des que l'un des trois entre en jeu. DISCRIMINANT MESURE LIVE (probe_envfire_resilient_cap, board
    MC1_67, `--hp-target 500000` -> dot = 20 % PVmax = 100000, armure 0) : tick de feu sur une cible
    RESILIENT a 62076 PV -> le natif inflige **62075 = hp-1** et la laisse VIVANTE a 1 PV (signature de
    `IdunBattle.Core.Services.DamagePrediction$$ApplyResilientTraitDamageLimit`) ; TEMOIN au montage
    STRICTEMENT identique avec une cible NON-Resilient (astraBullgryn, 61362 PV) -> elle MEURT. La route
    `"direct"` tuait les deux."""
    __slots__ = ("target_sel", "profile", "amount", "is_melee", "hits", "source_ref",
                 "multi", "native_operation")

    def __init__(self, target_sel: TargetsSelector, profile: str, amount, is_melee: bool = True,
                 hits: int = 1, source_ref=None, multi: bool = False,
                 native_operation: str = "direct"):
        self.target_sel, self.profile, self.amount = target_sel, profile, amount
        self.is_melee, self.hits, self.source_ref = is_melee, int(hits), source_ref
        self.multi, self.native_operation = multi, native_operation

    def execute(self, entities, ectx):
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
    `EvaluateAbilities(0x26)`, ArmoriumCherub `EvaluateAbilities(0x4a=AttackInAtomicGroup)`, ArmouredMight/
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
    d'arme du dispatch normal ; `None` (le cas normal) = LU de `BattleConfiguration.Damage.
    DamageSpreadPercentage` a l'EXECUTION, quand l'etat de bataille est connu (#449-r2-r4 -- le
    natif lit lui aussi la config au moment du calcul, jamais a la construction du behaviour).
    Itere les cibles triees par id (ordre de lecture natif). Emet 'UseActiveAbility' par cible.
    PUR (non court-circuitant)."""
    __slots__ = ("subject_sel", "targets_sel", "spread_pct")

    def __init__(self, subject_sel: TargetsSelector, targets_sel: TargetsSelector,
                 spread_pct: Optional[int] = None):
        self.subject_sel = subject_sel
        self.targets_sel = targets_sel
        # NON resolu ici : l'arbre DSL est construit AVANT toute bataille (aucun `State`). La
        # resolution vit dans `execute`, ou `ectx.state` porte la BC.
        self.spread_pct = None if spread_pct is None else int(spread_pct)

    def execute(self, entities, ectx):
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
            # `allow_dead_caster=True` = le LITTERAL `1` que `IdunBattle.Entities.Behaviours.
            # UseActiveAbilityBehaviour$$Execute` force dans les `AbilityOptions` qu'il assemble
            # (`uStack_210._0_2_ = CONCAT11(*(behaviour + 0xa8), 1)` -- le SEUL octet en dur d'une
            # struct autrement recopiee champ par champ) : cette voie autorise un caster MORT, et
            # c'est indispensable au death-rattle FinalJustice (mesure live #88 : Titus a hp=0
            # porte sa riposte pour 10502 et tue). Sans lui, le gate acteur-mort de
            # `damage_ops/normal.py` (#133 MartialSuperiority) avalait toute la riposte.
            res = None if state.rng is None else AttackDamageOperation.execute(
                state, sid, tid, resolve_spread_pct(self.spread_pct, state),
                allow_dead_caster=True)
            ectx.emit("UseActiveAbility", subject=sid, target=tid, attack=res)
        return OperationResult.ok()
