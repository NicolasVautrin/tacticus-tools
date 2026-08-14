"""Feuilles DSL d'ATTAQUE runner-couplees : `AttackWithAttackDamage` (attaque d'ability crit/block),
`AttackWithAbilityDamage` (degat DIRECT sans crit/block), `EvaluateAbilities` (evalue les passifs
declenches inline), `UseActiveAbility` (dispatch recursif d'une ability). Wrappers au-dessus de
`runner/operations/damage.py` + `triggers/dispatch.py`. Namespace natif `Entities.Behaviours.*`."""
from __future__ import annotations

from typing import Optional

from ....dsl.base import (TargetsSelector, resolve_unit, _units_of, _pos, _is_alive,
                          _occupants_by_tile)
from ....entities.damage_profile_type import DamageProfileType, PROFILE_NAME_BY_INDEX
from ....entities.invalid_target_policy import InvalidTargetPolicy
from ....entities.selectors._shared import _entity_pos
from ....services.battle_query import weapon_is_melee
from ....services.damage_config import resolve_spread_pct
from ....streams.inform_ops import get_inform_weapon_tags
from ....streams.tag_key import TagKey
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...components import StatsComponent
from ..base import ability_attack_params
from ...operations.damage import AttackDamageOperation
from ..base import profile_pierce
from ..attack_type import is_regular_attack


def _get_unit(entity, entities, state=None):
    """`IdunBattle.Entities.UnitExtensions$$GetUnit(entity, state)` -- l'etage qui re-resout une
    ENTITE en l'UNITE qu'on frappe. Il MANQUAIT au port, et c'est ce qui faisait lever un
    `AttributeError: 'int' object has no attribute 'get'` des qu'un selecteur rendait des TUILES.

    LE NATIF, verbatim (surcharge `IEntity`, celle a 99 xrefs) :

        while (true) {
            if (entity == null)       return null;
            if (entity is <UnitEntity>) return entity;            // une UNITE se rend elle-meme
            if (entity is <TileEntity>) {                         // une TUILE rend son OCCUPANT
                content = entity.<+0x38 = TileContentComponent>;
                if (!content.IsFilled()) return null;
                entity = state.GetEntity(content.<+0x10>);        // -> l'entite-PIED
                if (entity == null) return null;
                continue;                                         // et on RE-BOUCLE
            }
            if (entity is <FootEntity>) return GetUnit(<foot>, state);   // le pied -> son proprietaire
            return null;                                          // tout le reste -> null
        }

    OU IL VIT, **DERIVE des xrefs entrantes** de `IdunBattle.Entities.UnitExtensions$$GetUnit`
    (pas une enumeration a la main) : parmi tous les `*Behaviour$$Execute` du build, EXACTEMENT
    TROIS l'appellent --

        IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$Execute
        IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$Execute
        IdunBattle.Entities.Behaviours.DirectDamageBehaviour$$Execute

    et le squelette y est le MEME :

        targets = <targetSel>.Select(entities)     // slot 0 d'`ITargetsSelector` -> des ENTITES BRUTES
        foreach (entity in targets) {
            unit = UnitExtensions.GetUnit(entity, state);
            if (unit == null) { <operation 0x25, tag 0xa1 = l'id de l'entite> ; continue }
            ...
        }

    ⚠ Ce n'est PAS `IdunBattle.DSL.TargetsSelector$$SelectAllUnits`, et le distinguer importe :
    cette methode-la existe (elle appelle `TargetsSelector$$SelectUnit` sur chaque element), mais
    c'est le slot **3** de l'interface et **aucun** de ces trois behaviours ne le demande -- ils
    appellent tous le slot **0 `Select`**, puis re-resolvent eux-memes. Slots LUS dans
    `data/symbols/<build>/metadata/interface_slots.tsv`, invocation LUE dans l'invoker d'interface
    (`<slot relatif> + interfaceOffsets[<ITargetsSelector>]`, indexe dans la vtable a `+0x138`).

    ⚠ ET DEUX BEHAVIOURS QU'ON POURRAIT CROIRE CONCERNES NE LE SONT PAS -- ils sont ABSENTS de ces
    xrefs, donc ils recoivent bien l'entite BRUTE : `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute`
    (il `SelectFirst` son caster, `Select` ses cibles, les trie et pousse chacune telle quelle dans
    l'`AbilityEntities` de son enfant -- c'est l'ENFANT qui resout) et
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` (son seul gate est
    `UnitExtensions$$HasFlag(entity, 6)`, puis il pose l'effet sur l'entite telle quelle). Donc un
    `AddEffect` sur un domaine TUILE pose bien l'effet sur la TUILE cote natif : ne PAS y greffer
    cette resolution.

    CE QUI N'EST PAS PORTE ICI -- residu **#1034**, les deux gates que les deux behaviours d'ATTAQUE
    (pas `DirectDamageBehaviour`) posent APRES ce `GetUnit`, et la deduplication qui les suit :
    `UnitExtensions$$MatchesUnitSelectionType(unit, <behaviour+0xa8 | +0xc0>, state)` (le
    `selectionType` n'est capte par AUCUN call-site du port -- meme verrou que le residu #433-r3-r2)
    et `UnitExtensions$$HasTrait(unit, 0x40e)` (= `UnitTrait.Invincible`), plus l'`OrderedSet` dont
    le `Contains` pilote l'argument `isFirstHit` de `ExecuteTarget`.

    COTE PORT : un dict EST une unite (branche `is <UnitEntity>`) ; un id de tuile (`int`) ou une
    position `(col,row)` est une TUILE, resolue par `dsl.base._occupants_by_tile` -- le foyer UNIQUE
    de la resolution d'occupant (#433-r3-r1a), indexe par les PIEDS, ce qui est litteralement la
    boucle native `tuile -> pied -> proprietaire` (n'importe quel pied d'une multi-hex rend SON
    unite). Tout le reste rend `None`, et l'appelant SKIPPE la cible -- comme le natif.

    ⚠ ET LE PORT N'A PAS L'ESPACE D'IDS DU NATIF, ce qui cree un piege que le natif ne peut pas
    avoir. Cote ECS, un `Entity` est unite OU tuile OU pied, jamais ambigu. Cote port, les ids
    d'unites (`state.entities`) et les ids de tuiles (`state.board`) **se CHEVAUCHENT** (residu deja
    nomme dans `operations/active_ability.py`), et les deux conventions coexistent :
    `behaviours/context.py::unit_id` suit l'ORDRE NATIF (unite d'abord, tuile en repli) parce qu'il
    recoit un id d'ENTITE ; `entities/selectors/_shared.py::_entity_pos` traite tout `int` comme une
    TUILE parce qu'il recoit la sortie d'un SELECTEUR. Ici on est au second cas -- un selecteur DSL
    rend des dicts d'unite ou des ids de TUILE, jamais des ids d'unite.

    D'ou le REFUS EXPLICITE ci-dessous. Un `UnitSet([<id d'unite>])` est un arbre FAUTIF (#929-r3 en
    garde la contre-epreuve), et si on le laissait passer par la voie tuile il resoudrait sur la
    tuile HOMONYME : soit l'unite qui l'occupe -- silencieusement FAUSSE -- soit rien du tout, ce qui
    transformerait un crash immediat en no-op silencieux. Le discriminant est celui qu'ecrit deja
    `unit_id` : l'id designe-t-il une entite de `state` ? On LEVE, en nommant la cause, plutot que de
    rendre `None`."""
    if isinstance(entity, dict):                 # `entity is <UnitEntity>` -> elle se rend elle-meme
        return entity
    if state is not None and isinstance(entity, int) and not isinstance(entity, bool):
        # ⚠ Pas une tuile : un id d'ENTITE du port (unite ou MoW). Cf. le paragraphe ci-dessus.
        if state.get_entity(entity) is not None:
            raise TypeError(
                "selecteur a domaine UNITE mal cable : l'element " + repr(entity) + " est l'ID "
                "d'une entite de `state`, pas une entite-tuile. Un selecteur DSL rend des dicts "
                "d'unite ou des ids de TUILE (cf. #929-r3 et `_get_unit`)")
    p = _entity_pos(entity, getattr(entities, "board", None))
    if p is None:                                # ni unite, ni tuile resolvable -> `null`
        return None
    return _occupants_by_tile(entities.units or ()).get((int(p[0]), int(p[1])))


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

    `pick_n` = FOLD du `IdunBattleLogic.Entities.DSLSelectors$$PickRandomly(selecteur, n)` natif quand il ENVELOPPE le selecteur de cibles
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
    RESIDU NOMME **#1034** : les deux gates par-cible que `AbilityDamageBehaviour$$Execute` -- et
    `AttackDamageBehaviour$$Execute`, meme forme -- posent APRES leur `GetUnit` ne sont PAS portes :
    `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType(unit, <behaviour+0xa8 | +0xc0>,
    state)` et `IdunBattle.Entities.UnitExtensions$$HasTrait(unit, 0x40e = UnitTrait.Invincible)`.
    ⚠ Le premier etait cite ici sous `UnitExtensions.IsTargetable` -- un symbole que le behaviour
    N'APPELLE PAS. Le gate LU est `MatchesUnitSelectionType`, dont l'intargetabilite n'est qu'UNE
    branche (`!HasFlag(0x11)`, cas `2` et `3`), et qui est gouverne par un `selectionType` que le
    port ne capte a aucun call-site (meme verrou que le residu `#433-r3-r2`).

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
    Executioner `hits = IdunBattleLogic.Entities.DSLFormulas$$RoundsStarted` = valeur DYNAMIQUE lue au cast, PAS une constante config)."""
    __slots__ = ("target_sel", "ability_id", "profile", "is_melee", "min_key", "max_key", "hits_key",
                 "damage_override", "multi", "pick_n", "amount", "hits", "ability_type", "hits_add_key",
                 "native_factory", "force_overkill", "hits_override", "level_slot", "tile_domain",
                 "force_crit", "is_first_hit", "amount_spread_pct", "attack_state0",
                 "is_outside_attack", "skip_hits_modifiers")

    def __init__(self, target_sel: TargetsSelector, ability_id: str, profile: str, is_melee: bool = True,
                 min_key: str = "minDmg", max_key: str = "maxDmg", hits_key: str = "nrOfHits",
                 damage_override=None, multi: bool = False, pick_n=None, amount=None, hits=None,
                 ability_type=None, hits_add_key=None, native_factory: str = "attack",
                 force_overkill: bool = False, hits_override=None, level_slot: str = "active",
                 tile_domain: bool = False, force_crit: bool = False,
                 is_first_hit: bool = True, amount_spread_pct: int = 0,
                 attack_state0: Optional[dict] = None, is_outside_attack: bool = True,
                 skip_hits_modifiers: bool = False):
        # #419-r1-tr5-r7 : l'OCTET **+3** du `Nullable<AttackDamageBehaviourOptions>` -- le nombre
        # de coups passe est DEJA FINAL, `AttackDamageOperation$$GetAttackHits` rend la base sans
        # traverser le slot 0xb6 (`AttackHitsWithModifiersFormula`). Mode BORNES uniquement (le mode
        # `amount` route par `execute_normal_like`, qui n'a pas ce canal). Cf. la docstring de
        # `AttackDamageOperation.execute_ability_attack` pour la chaine d'offsets LUE.
        self.skip_hits_modifiers = bool(skip_hits_modifiers)
        # #512-r2 : `isOutsideAttack`, le litteral natif. `True` = cette feuille EST celle que
        # `DSLBehaviors$$AttackWith{Attack,Ability}Damage` emballe dans son propre `AttackBehaviour`
        # -> elle pousse `StartAttack`, donc `On(PreAttack = 5)`. `False` = feuille NUE
        # (`$$AttackDamage` / `$$AbilityDamage`) composee dans un noeud qui a DEJA ouvert l'attaque.
        # `SortedAttackSeries.__init__` le pose a `False` sur ses paires (cf. sa docstring).
        self.is_outside_attack = bool(is_outside_attack)
        # #419-r3 : `attack_state0` = l'etat de l'`OngoingAttack` HERITEE (`+0x30` index de coup,
        # `+0x40` `isCriticalDamageAllowed`, `+0x48` `FailedBlockIds`), au format rendu par
        # `operations/damage_hits.attack_state_out`. `None` (defaut) = attaque NEUVE, ce qui est la
        # semantique de `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` : cette
        # factory-la finit par `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor`, donc pousse
        # un `OngoingAttack` neuf par cible (`StartAttackOperation$$Execute`).
        # On le RENSEIGNE quand la feuille tient lieu d'un `IdunBattleLogic.Entities.DSLBehaviors$$
        # AttackDamage` NU -- un `AttackDamageBehaviour` SANS `AttackBehaviour`, compose dans le
        # `Attack(...)` d'une autre attaque, qui lit donc l'attaque en cours
        # (`GetCurrentAttackOrDefault(isOutsideAttack: 0)`, slot 200, arite 0). C'est le meme
        # gisement que le `is_first_hit` de case-221, dont ce champ est la forme COMPLETE.
        self.attack_state0 = attack_state0
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
        #   "ability" = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage/IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage -> core IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`
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
            # `AttackDamageBehaviour$$Execute` : `unit = UnitExtensions.GetUnit(entity, state)` sur
            # CHAQUE entite rendue par `Select` -- une TUILE resout en son occupant, `null` -> la cible
            # est SAUTEE (le natif n'emet alors que l'operation `0x25`). Cf. `_get_unit`.
            targets = [u for u in (_get_unit(e, entities, state)
                                   for e in _units_of(self.target_sel, entities))
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
                    is_first_hit=self.is_first_hit,
                    # #925-r2 : le drapeau ne pilotait QUE la voie BORNES. Ce vecteur-ci n'exprimait
                    # pas `isOutsideAttack`, donc il n'emettait JAMAIS `On(PreAttack = 5)` -- alors
                    # que trois de ses quatre call-sites portent une feuille EMBALLEE. Cf.
                    # `execute_normal_like` pour les quatre factories natives, lues une par une.
                    is_outside_attack=self.is_outside_attack)
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
                _as0 = self.attack_state0 or {}
                atk = AttackDamageOperation.execute_ability_attack(
                    state, caster, tgt, bmin, bmax, pierce, hits,
                    damage_profile=self.profile, is_melee=self.is_melee,
                    ability_type=self.ability_type,
                    is_attack_damage_op=(self.native_factory != "ability"),
                    # #512-r2 : cette feuille ouvre-t-elle l'attaque (`StartAttack` -> `On(5)`) ?
                    is_outside_attack=self.is_outside_attack,
                    force_overkill=self.force_overkill, force_crit=self.force_crit,
                    # #419-r3 : etat de l'`OngoingAttack` heritee (cf. `__init__`). Absent = neuve.
                    hit_index0=int(_as0.get("next_hit_index", 0)),
                    crit_allowed0=bool(_as0.get("crit_allowed", True)),
                    failed_block0=_as0.get("failed_block"),
                    # #419-r1-tr5-r7 : octet +3 des options natives (coups DEJA finaux).
                    skip_hits_modifiers=self.skip_hits_modifiers)
            ectx.emit("AttackWithAttackDamage", caster=caster, target=tgt,
                      total=(atk or {}).get("total"), attack=atk)
        return OperationResult.ok()


class SortedAttackSeries(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$SortedAttackSeries(actor, sel1, atk1, sel2, atk2, source)` ->
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
    ⚠⚠ **`0x3a`/`0x3b` NE SONT PAS DES BORNES D'ANIMATION** -- cette docstring l'a affirme, et c'est
    FAUX (#512-r2). Les deux ordinaux sont LUS dans
    `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv` : `58 StartAttack` (arite 3) et
    `59 FinishAttack` (arite 3) -- les MEMES slots que `IdunBattle.Entities.Behaviours.
    AttackBehaviour$$Execute` pousse autour de chaque cible. Et
    `IdunBattle.Operations.StartAttackOperation$$Execute` appelle
    `EvaluateAbilitiesImmediately(EventTriggerType.PreAttack = 5, ...)`. Ce noeud est donc le
    **QUATRIEME** emetteur de `On(5)` du binaire (avec `AttackBehaviour$$Execute`,
    `StartAttackBehaviour$$Execute` et la voie MESSAGE), et il l'emet **par cible DISTINCTE de la
    serie**, pas par feuille -- une cible presente dans les DEUX selecteurs recoit ses deux attaques
    A L'INTERIEUR d'une seule ouverture (c'est litteralement ce que dit `if (unit != prevUnit)`).

    CONSEQUENCE PORTEE : ce noeud EMET `On(5)` lui-meme, et il pose `is_outside_attack = False` sur
    ses feuilles -- sinon `1088 HellfyreMissileRack` (deux feuilles sur la MEME cible) emettrait
    DEUX `On(5)` la ou le natif en emet UN. Voir `damage_ops/ability.py`.
    RESIDU NOMME, non porte : le pendant `On(Attack = 9)` de `FinishAttack` (`0x3b`) -- le port ne
    l'emet que sur la voie NORMALE (`damage_ops/normal.py`), pour AUCUNE ability, et l'y ajouter
    reveillerait d'un coup tous les consommateurs de `finish_attack_triggers` (armure Terminator,
    reset de crit d'ActOfFaith, MoveAndSpawnDecoy, Neuroparasite) sur un rayon non mesure. Le seul
    consommateur porte que l'asymetrie concerne est le CLEAR de `LetTheGalaxyBurn` ; MESURE du
    2026-08-07 : les **33** porteurs du trait n'ont que **5** actives distinctes
    (`BringerOfDespair`, `Drachnyen`, `FrenziedFiring`, `HeraldOfTheApocalypse`, `Incursion`) et
    **aucune** n'est famille ABILITY ni ne passe par un `SortedAttackSeries` -> l'asymetrie est
    INERTE sur tout porteur reel.

    `pairs` = liste de `(TargetsSelector, AbilityBehaviour)`. Emet 'SortedAttackSeries' (ordre resolu,
    diagnostic). PUR."""
    __slots__ = ("pairs", "ability_type")

    def __init__(self, pairs, ability_type: Optional[int] = None):
        self.pairs = list(pairs)
        # `+0x60..0x70` = l'`AbilityOrEffect` de la source, 6e argument de la factory native. Il
        # n'etait PAS porte ; il l'est parce que l'`On(5)` que ce noeud emet le transporte, et que
        # `BattleQuery$$IsRangedAttack` (slot 3) commence par `if (!ability.HasValue) return false`.
        self.ability_type = ability_type
        # `GetAttacks` ne construit QUE des feuilles NUES : c'est ce noeud-ci qui ouvre l'attaque
        # (slot 58) et la ferme (slot 59). Toute feuille qui sait exprimer `isOutsideAttack` est donc
        # rabattue a `False` ici -- une feuille qui ne le sait pas garde son comportement.
        for _sel, beh in self.pairs:
            if beh is not None and hasattr(beh, "is_outside_attack"):
                beh.is_outside_attack = False

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
        state = ectx.state
        actor = (entities.caster or {}).get("id") if entities.caster else None
        for uid in order:
            u, behs = by_id[uid]
            ents = replace(entities, active_target=u)      # `entities[slot 4] = unit` (ActiveTarget)
            # slot 58 `StartAttack` -> `StartAttackOperation$$Execute` ->
            # `EvaluateAbilitiesImmediately(PreAttack = 5)` -- UNE fois par cible DISTINCTE de la
            # serie, AVANT ses behaviours (#512-r2, cf. la docstring). L'`actor` du natif est
            # `(+0x50).SelectSingle(entities)` ; le port prend le caster du contexte, qui est ce que
            # ce selecteur rend a tous les call-sites portes.
            if state is not None and actor is not None:
                from ...operations.triggers.dispatch.attack import pre_attack_triggers
                # `ranged` est un canal LEGACY du port (la branche positionnelle `Normal(3)`) ; le
                # gate PORTEUR est `ability_type`, que `_is_ranged_attack` resout en
                # `GetAbilityAttackRangeType`. Sans id, le slot 3 rend `false` -- soit exactement
                # l'etat d'avant #512-r2 pour ce noeud (aucune emission).
                pre_attack_triggers(state, int(actor), int(uid), ranged=False,
                                    ability_type=self.ability_type)
            for beh in behs:
                beh.execute(ents, ectx)
        ectx.emit("SortedAttackSeries", order=list(order))
        return OperationResult.ok()


class ChainLeftOverHitsAttackDamage(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$ChainLeftOverHitsAttackDamage` ->
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
                 "extra_hits", "is_melee", "native_factory", "min_key", "max_key", "ability_type")

    MAX_ITERATIONS = 100                     # garde native (`iVar19 = 100`)

    def __init__(self, caster_sel: TargetsSelector, target_sel: TargetsSelector,
                 next_target_sel: TargetsSelector, ability_id: str, profile: str, hits,
                 extra_hits, is_melee: bool = False, native_factory: str = "attack",
                 min_key: str = "minDmg", max_key: str = "maxDmg",
                 ability_type: Optional[int] = None):
        self.caster_sel, self.target_sel, self.next_target_sel = caster_sel, target_sel, next_target_sel
        self.ability_id, self.profile = ability_id, profile
        self.hits, self.extra_hits = hits, extra_hits
        self.is_melee, self.native_factory = is_melee, native_factory
        self.min_key, self.max_key = min_key, max_key
        # #512-r2 volet 2 : l'`AbilityOrEffect` du champ `+0x70`, que le behaviour d'attaque
        # construit a la volee recoit en `source`. Le port ne le THREADAIT PAS -> l'evenement
        # `On(PreAttack = 5)` de chaque maillon partait avec `ability_type = None`, et le gate
        # `IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` (slot 3) -- qui commence par
        # `if (!ability.HasValue) return false` puis switche sur `GetAbilityAttackRangeType` --
        # retombait sur sa branche POSITIONNELLE `Normal(3)`. Mesure #512-r1 : `1048
        # FragstormGrenadeLauncher` est `attackRangeType = Ranged(2)`, donc INCONDITIONNELLEMENT
        # ranged ; sans l'id, une cible ADJACENTE etait declaree melee et `SuppressiveFire`
        # SOUS-suppressait. `None` reste le defaut (feuille montee sans id -> comportement
        # anterieur, gates inertes).
        self.ability_type = ability_type

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
        bit-exact trompeur de #116 et la divergence de #122 des que k <= 3.

        ⚠⚠ RESIDU OUVERT, MESURE ET NON FERME (#505) : CETTE LOI N'EST PAS UNIFORME, ET LE DECOMPILE
        DIT POURQUOI. Sur `1129 BloodyFury` (`extraHits` **null**, donc `extra = 0`), la mesure LIVE
        DIRECTE -- un seul ennemi fragile, les autres immortels, donc le 2e maillon SURVIT et son
        nombre d'events EST son nombre de coups (`probe_505_bloody_fury.py --only report --attackers
        0,1,3 --attacks 3 --main-hp 3000,10000,15000,21000`) -- donne, a H = 4 :

            PV cible | k | report LIVE | cette loi `max(0,H-k-1)+0` | `max(0,H-k)`
            -------- | - | ----------- | -------------------------- | ------------
            3000     | 1 | 3           | 2  X                       | 3  OK
            10000    | 2 | 2           | 1  X                       | 2  OK
            15000    | 3 | 1           | 0  X                       | 1  OK
            21000    | 4 | 0           | 0  OK                      | 0  OK

        et `max(0,H-k)` fait AUSSI passer `tests/engine/runner/test_chain_leftover_hits_live.py`
        (1006, seeds 4242 ET 777) -- parce que pour 1006 `extra = 1` et que
        `max(0,H-k-1)+1 == max(0,H-k)` des que `H-k >= 1`. La SEULE mesure qui separe les deux est
        le regime `H == k` de `probe_125_leftover_hits.py --mode sweep --hp-target 10000`, ou le
        LIVE frappe un 2e maillon (report >= 1) alors que `max(0,H-k)` rendrait 0. AUCUNE des deux
        formes ne couvre donc les SIX points mesures.

        LA CAUSE, LUE : le predicat qui decide si un coup laisse une entree FLAG-VRAIE est
        `IdunBattle.Core.Services.DamagePrediction$$IsOverkill`, et c'est un SEUIL, pas un index --

            if (!allowOverkill) return false
            if (minimumHealth.HasValue && minimumHealth.Value > 0) return false
            if (healthDamage >= targetInitialHealth && isForceOverkill) return true
            if (!isPreventOverkill && healthDamage >= targetInitialHealth) {
                pct = (healthDamage - targetInitialHealth) / targetInitialHealth * 100   # Fix64
                return (pct < overkillDmgPctOfHealth) ? isCritical : true
            }
            return false

        -> le coup FATAL pose lui-meme `UnitFlag.Overkilled` quand son EXCEDENT depasse
        `overkillDmgPctOfHealth` (ou qu'il est CRITIQUE) ; sinon c'est le coup SUIVANT qui le pose.
        L'indice du premier coup « deja overkill » vaut donc `k` ou `k+1` SELON LA MAGNITUDE, et
        c'est exactement l'unite d'ecart entre les deux formes ci-dessus (1129 ecrase sa cible a
        +167 % -> `k` ; 1006 la depasse de +24 % -> `k+1`). Fermer ce residu demande de porter
        `IsOverkill` (constante `overkillDmgPctOfHealth` des battle-rules, `deniedDamage` cumule,
        `CanBeOverkilled`, `HasFlag(0x13)`, `minimumHealth`) -- hors perimetre #505, qui ne pouvait
        pas changer une feuille PARTAGEE par 1006/1048/1129 sur une loi qu'aucune forme simple ne
        satisfait. CE QUI EST ACQUIS : la forme actuelle SOUS-ESTIME le report d'exactement 1 quand
        le coup fatal ecrase la cible (BloodyFury), et est JUSTE quand il l'effleure.
        ⚠ Et `probe_489_fragstorm_grenade_launcher.py` VERDICT-4 ne l'aurait jamais vu : il compare
        `off_chain[1]["hits"]` a la formule qui l'a produit -- une TAUTOLOGIE, pas une confrontation.
        Le verdict qui mord est celui qui lit le report DANS LE LIVE, sur un maillon SURVIVANT."""
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
                # #512-r2 volet 2 : `abilityType = this+0x10` -- le natif le passe au behaviour
                # construit a la volee ; sans lui les gates qui lisent l'`AbilityOrEffect` du coup
                # (dont `_is_ranged_attack`) sont FAUX, pas seulement inertes.
                ability_type=self.ability_type,
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
    """`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (LU) -> `IdunBattle.Entities.Behaviours.
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
    factory native enveloppe TOUJOURS (`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` = `AbilityDamageBehaviour` +
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
                 "multi", "native_operation", "is_outside_attack", "ability_type")

    def __init__(self, target_sel: TargetsSelector, profile: str, amount, is_melee: bool = True,
                 hits: int = 1, source_ref=None, multi: bool = False,
                 native_operation: str = "direct", is_outside_attack: bool = True,
                 ability_type=None):
        self.target_sel, self.profile, self.amount = target_sel, profile, amount
        self.is_melee, self.hits, self.source_ref = is_melee, int(hits), source_ref
        self.multi, self.native_operation = multi, native_operation
        # `ability_type` = l'`AbilityOrEffect` NUMERIQUE du coup -- le 7e argument de la surcharge
        # RACINE `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`
        # (`IdunBattle.Core.AbilityOrEffect$$op_Implicit(*this+0x10)` au call-site). Le jumeau
        # `AttackWithAttackDamage` le porte deja ; ici il manquait, donc TOUT coup de la famille
        # ABILITY partait SANS son attributeur (`TriggerEvent.ability_type` des after-hit, cle
        # `received_damage_this_turn`). `None` (defaut) = comportement historique STRICTEMENT
        # inchange pour les trois appelants d'avant (DoT de tuile `EnvFireTile`, `PutridExplosion`,
        # `Explodes`), dont aucun ne l'ecrivait.
        self.ability_type = ability_type
        # #512-r2 -- cf. `AttackWithAttackDamage.__init__` : `isOutsideAttack` natif, gate de
        # l'emission d'`On(PreAttack = 5)`.
        self.is_outside_attack = bool(is_outside_attack)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        su = resolve_unit(self.source_ref, entities) if self.source_ref is not None else entities.caster
        src = (su or {}).get("id")
        if src is None:
            return OperationResult.ok()
        if self.multi:                                     # AttackBehaviour.Execute : selecteur -> N cibles
            # `AbilityDamageBehaviour$$Execute` : `unit = UnitExtensions.GetUnit(entity, state)` par
            # entite rendue par `Select` (tuile -> occupant, `null` -> cible SAUTEE). Cf. `_get_unit`.
            targets = sorted((u for u in (_get_unit(e, entities, state)
                                          for e in _units_of(self.target_sel, entities))
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
                    ability_type=self.ability_type,        # `AbilityOrEffect` du coup (7e arg natif)
                    is_attack_damage_op=False,             # famille ABILITY : pas de crit, pas de resolve
                    is_outside_attack=self.is_outside_attack,          # #512-r2 : gate d'`On(5)`
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


class DirectDamage(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$DirectDamage(caster, target, amount, abilityOrEffect,
    selectionType, options)` -> `IdunBattle.Entities.Behaviours.DirectDamageBehaviour$$.ctor` --
    la factory qui construit VRAIMENT un `IdunBattle.Operations.DirectDamageOperation`, contrairement
    a `AttackWithAbilityDamage` dont le nom l'a longtemps laisse croire (cf. sa docstring).

    `DirectDamageBehaviour$$Execute`, lu verbatim :

        caster  = <+0x50>.SelectSingle(entities)        # UNE entite ; nulle -> return (rien)
        targets = <+0x58>.Select(entities)              # la LISTE des cibles ; nulle -> return
        foreach (t in targets) {
            unit = UnitExtensions.GetUnit(t, entities.State)
            if (unit == null) { <log d'erreur> ; continue }
            processor.<slot 0x20> = unit                # cible courante
            if (<+0x60> != null) <+0x60>.Calculate(entities, ...)     # le noeud MONTANT
            result.Combine( processor.<slot 0x40 = DirectDamage>(
                                <+0x88..+0xb0 = abilityOrEffect>, <+0x68..+0x78 = options>) )
        }

    Le slot `0x40` de l'`IOperationProcessor` est `DirectDamage` (arite 6) --
    `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`, pas une deduction.

    Cote port, l'Operation est DEJA portee : `AttackDamageOperation.execute_direct`, mirror de
    `IdunBattle.Core.Services.DamagePrediction$$CalculateDirectDamage` (percage/armure SEULS, mods
    None, member-cap ; ni crit, ni block, ni bouclier, ni cap Resilient). Elle etait exposee sans
    consommateur << pour le jour ou une feuille mirrorera vraiment `DirectDamageOperation` >> : c'est
    ce jour-la, et cette feuille-ci est la premiere.

    ⚠ **AUCUN `damageProfile` dans la signature native** : le profil ne fait partie ni des six
    arguments de la factory, ni de la struct `options` que le seul call-site porte
    (`IdunBattle.Entities.Effects.Loki.ArmourOfShriekingSoulsEffect$$CreateTargetTriggerBehaviour`)
    passe INTEGRALEMENT ZEROEE. `profile=None` cote port -> `profile_pierce(None, None)` =
    `PiercingRatio` d'un profil introuvable = **0** : le degat est alors integralement soumis a
    l'armure du defenseur. C'est le mirror LITTERAL de ce que le port sait lire ; la face
    `CalculateDirectDamage`-sur-profil-nul n'a PAS ete RE-derivee (residu nomme au call-site).

    `source_sel` = `<+0x50>`, resolu en UNE entite (`SelectSingle`) ; `target_sel` = `<+0x58>`,
    ITERE (le natif boucle, meme si tous les call-sites lus rendent une cible). `amount` = le noeud
    `IAmountFormula` (`.calculate(ctx)` ou scalaire). `hits` n'existe pas : UNE application par
    cible. Emet 'DirectDamage' PAR CIBLE. PUR (stop=False)."""
    __slots__ = ("target_sel", "amount", "source_sel", "profile", "ability_type")

    def __init__(self, target_sel: TargetsSelector, amount, source_sel: TargetsSelector = None,
                 profile: Optional[str] = None, ability_type=None):
        self.target_sel, self.amount, self.source_sel = target_sel, amount, source_sel
        self.profile, self.ability_type = profile, ability_type

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            ectx.emit("DirectDamage", source=None, target=None, total=None, attack=None)
            return OperationResult.ok()
        # `<+0x50>.SelectSingle(entities)` -- UNE entite. Nulle -> le natif RETOURNE (aucune cible
        # n'est traitee), il ne retombe pas sur le caster ambiant.
        src_u = resolve_unit(self.source_sel, entities) if self.source_sel is not None else entities.caster
        src = (src_u or {}).get("id")
        if src is None:
            ectx.emit("DirectDamage", source=None, target=None, total=None, attack=None)
            return OperationResult.ok()
        base = int(self.amount.calculate(entities) if hasattr(self.amount, "calculate")
                   else (self.amount.evaluate(entities) if hasattr(self.amount, "evaluate")
                         else self.amount) or 0)
        pierce = profile_pierce(None, self.profile)     # profil ABSENT de la signature native
        # `DirectDamageBehaviour$$Execute` : `unit = UnitExtensions.GetUnit(t, <behaviour+0xb8 = state>)`
        # par entite rendue par `Select`. Cet etage-la etait DECRIT dans la docstring ci-dessus et
        # ABSENT du code : la ligne d'avant jetait tout element non-dict au lieu de le RESOUDRE, donc
        # un selecteur a domaine TUILE ne frappait rien. Cf. `_get_unit`.
        for e in _units_of(self.target_sel, entities):
            u = _get_unit(e, entities, state)
            tgt = u.get("id") if isinstance(u, dict) else None
            if tgt is None:
                continue                                 # `GetUnit(t) == null` -> log + continue
            atk = AttackDamageOperation.execute_direct(state, src, tgt, base, pierce,
                                                       damage_profile=self.profile)
            ectx.emit("DirectDamage", source=src, target=tgt,
                      total=(atk or {}).get("total"), attack=atk)
        return OperationResult.ok()


# Table INVERSE nom -> ordinal de `IdunBattle.Entities.Enum.DamageProfileType`, DERIVEE de l'enum
# (source unique `PROFILE_NAME_BY_INDEX`) -- jamais une seconde table transcrite a la main.
_PROFILE_INDEX_BY_NAME: dict[str, int] = {n: i for i, n in PROFILE_NAME_BY_INDEX.items()}


class InformWeapon(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon(damageProfileType, isMelee, useSpecial)`
    -> `IdunBattle.Entities.Behaviours.InformBehaviour` : construit un `Dictionary<TagKey,int>` de
    TAGS DE FLUX et l'emballe dans un `InformBehaviour`. Les trois cles sont des
    `IdunBattle.Streams.TagKey`, LUS dans `data/symbols/<build>/frida/enums.tsv` :

        0x93 TagKey.Attack_Weapon_DamageProfile = damageProfileType.HasValue ? (int)value : -1
                                                 (`-1` == `DamageProfileType.None_`)  -- INCONDITIONNEL
        0x92 TagKey.Attack_Weapon_IsMelee       = le 2e argument `isMelee`             -- INCONDITIONNEL
        0x94 TagKey.Attack_Weapon_Use_Special   = le 3e argument `useSpecial`
                                                 -- pose SEULEMENT si non nul (`if ((char)useSpecial != 0)`)

    ⚠ Ce n'est NI un `ActivateEffectBehaviour`, NI l'operation `0x2c` : la docstring qui l'affirmait
    etait FAUSSE sur les deux points (et intervertissait 0x92/0x93). `ActivateEffectBehaviour$$.ctor`
    n'a aucune surcharge prenant un `Dictionary` (ses deux ctors : `(ITargetsSelector)` et
    `(ITargetsSelector, EffectType)`) ; et `InformWeapon` instancie le MEME `Il2CppClass*` que
    `IdunBattleLogic.Entities.DSLBehaviors$$Inform(Dictionary<TagKey,Int32>)` -- meme site de
    construction, meme ctor a 3 arguments. C'est donc `InformBehaviour`, le noeud DSL de TAGS.

    La surcharge a DEUX arguments `DSLBehaviors$$InformWeapon(weapon: WeaponProfile, useSpecial)`
    ne fait que DERIVER les deux premiers de l'arme puis deleguer : `damageProfileType =
    Nullable(weapon->{+0x10})`, `isMelee = IdunShared.Battle.WeaponProfile$$get_IsMelee(weapon)`.

    COMBAT-INERTE, et voici PAR QUOI : `IdunBattle.Entities.Behaviours.InformBehaviour$$Execute`
    itere le dictionnaire, evalue chaque `IAmountFormula` sur les entities et remplit le dict de tags
    de SORTIE du behaviour -- il n'appelle AUCUNE Operation mutante (ni HealthComponent, ni
    StatsComponent, ni pose d'effet), et ne consomme AUCUN tirage. L'emission, elle, se fait par
    `IdunBattle.Operations.InformOperation$$Execute`, qui ne fait QUE dispatcher un pas de flux
    `StepType.Info` (29) portant ces tags. Donc : invisible de la face COMBAT (HP/degat/effets),
    mais BIEN VISIBLE dans le flux de replay -- ce n'est pas un no-op, c'est un canal STREAM.
    Deterministe et sans tirage -> n'altere PAS l'ordre `state.rng` de l'attaque qui le suit dans le
    `op_and`/`op_add` : bit-exactness de l'attaque preservee BY CONSTRUCTION.

    `is_melee` / `use_special` sont LUS au litteral de CHAQUE porteur, jamais deduits du profil ni du
    nom de l'ability -- ils DIFFERENT d'un porteur a l'autre (cf. `docs/rl/case-419-r1-tr14-r4-r2-*`).
    Emet 'InformWeapon' (profil + les deux bits + le dict de tags). PUR.

    ⚠ SUR LA VOIE ATTAQUE NORMALE, `is_melee` N'EST PAS UN LITTERAL -- il est DERIVE de l'arme, et
    c'est `from_weapon` qui porte cette derivation (#419-r1-tr14-r4-r2-r1). Le porteur le plus
    FREQUENT de ce noeud est `ALoki_NormalAttackAbility$$ExecuteInformWeapon` (**9** appelants,
    contre 6 pour la surcharge a trois arguments) : ecrire une constante y serait faux d'une unite
    a l'autre ET d'une DISTANCE a l'autre pour la meme unite."""
    __slots__ = ("profile", "is_melee", "use_special")

    def __init__(self, profile: Optional[str], is_melee: bool = False, use_special: bool = False):
        self.profile = profile
        self.is_melee = bool(is_melee)
        self.use_special = bool(use_special)

    @classmethod
    def from_weapon(cls, weapon: Optional[dict], use_special: bool = False) -> "InformWeapon":
        """`IdunBattleLogic.Entities.DSLBehaviors$$InformWeapon(weapon: WeaponProfile, useSpecial)`
        -- la surcharge a DEUX arguments, qui DERIVE les deux premiers de l'arme puis delegue :

            if (weapon == null) throw;                              // FUN_1801f51f0
            damageProfileType = new Nullable<DamageProfileType>(weapon->{+0x10});
            isMelee           = WeaponProfile.get_IsMelee(weapon);
            return InformWeapon(damageProfileType, isMelee, useSpecial);

        C'est LA voie de l'attaque normale (son unique appelant est
        `ALoki_NormalAttackAbility$$ExecuteInformWeapon`), et les deux grandeurs y sont DYNAMIQUES :
        la MEME unite rend `IsMelee=1` au contact et `IsMelee=0` a distance, parce que
        `BattleQuery$$GetAttackWeaponForDefaultNormalAttack` (slot `0xaf`) lui a choisi une AUTRE
        arme. Un port qui ecrirait une constante passerait sur un seul montage.

        `weapon` = le dict de profil d'arme du gameconfig, tel que `select_weapon` /
        `battle_query.get_attack_weapon_for_default_normal_attack` le rend. `weapon+0x10` = sa cle
        `DamageProfile` (le NOM, converti en ordinal a l'emission) ; `get_IsMelee` = le predicat
        PARTAGE `battle_query.weapon_is_melee` (`Range is None || Range < 2`), pas un test local.

        ⚠ `weapon is None` LEVE, comme le natif -- et ce n'est pas de la severite gratuite : le
        gate `if (weapon == null) return default;` vit EN AMONT, dans `ExecuteBehaviour`. Une arme
        nulle arrivee jusqu'ici signale que l'appelant a saute ce gate, pas qu'il faut ecrire -1."""
        if weapon is None:
            raise ValueError("InformWeapon.from_weapon : arme nulle -- le gate `if (weapon == null) "
                             "return default;` d'ALoki_NormalAttackAbility$$ExecuteBehaviour "
                             "n'a pas ete joue en amont")
        return cls(profile=weapon.get("DamageProfile"), is_melee=weapon_is_melee(weapon),
                   use_special=use_special)

    def tags(self) -> dict:
        """Le `Dictionary<TagKey,int>` de ce noeud -- DELEGUE au foyer unique
        `engine.streams.inform_ops.get_inform_weapon_tags`, que partage la face STREAM
        (`InformOperation$$Execute`). Une seconde table de cles ici pourrait diverger de celle
        qu'emet le flux sans que rien ne le dise."""
        if self.profile is None:            # `Nullable<DamageProfileType>` vide -> le natif ecrit -1
            profile_index = int(DamageProfileType.None_)
        else:                               # nom inconnu -> KeyError : un bug de port, jamais un -1 muet
            profile_index = _PROFILE_INDEX_BY_NAME[self.profile]
        return get_inform_weapon_tags(profile_index, self.is_melee, self.use_special)

    def execute(self, entities, ectx):
        ectx.emit("InformWeapon", profile=self.profile, is_melee=self.is_melee,
                  use_special=self.use_special, tags=self.tags())
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
        from ...operations.triggers.dispatch.ability import evaluate_abilities_for_event
        state = ectx.state
        caster = (entities.caster or {}).get("id")
        target = (entities.target or {}).get("id")
        if state is None or caster is None or target is None:
            return OperationResult.ok()
        res = evaluate_abilities_for_event(state, caster, target, self.event, self.ranged) or []
        ectx.emit("EvaluateAbilities", caster=caster, target=target, results=res)
        return OperationResult.ok()


class UseActiveAbility(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$UseActiveAbility` ->
    `IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour$$Execute` : le CASTER (`caster_sel`)
    utilise son ability active (`activeAbilityType`) sur la cible (`target_sel`) -- dispatch
    RECURSIF via le slot **2** d'`IOperationProcessor` (`ActiveAbility(caster, target, abilityType,
    options)`, arite 4, LU dans `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`).

    MAPPING DES CHAMPS -- lu dans `UseActiveAbilityBehaviour$$.ctor`, dont la signature est NOMMEE
    (`(this, caster, target, activeAbilityType, parentAbility, triggerAbilityOrEffect, options)`) :

        +0x50  activeAbilityType        +0x68..+0x80  parentAbility (28 o)
        +0x58  caster                   +0x84..+0x9c  triggerAbilityOrEffect (28 o)
        +0x60  target                   +0xa0..+0xb3  options (20 o)

    ⚠ **LA BOUCLE DU NATIF PORTE SUR LES CASTERS, ET LA CIBLE EST `SelectFirst`** (#889-r5-r1,
    ferme par #944). Lu aux slots d'interface (`interface_slots.tsv`, `ITargetsSelector` : slot 0 =
    `Select`, slot 1 = `SelectFirst`), `$$Execute` fait, DANS CET ORDRE :

        targets = (+0x60 target).SelectFirst(entities)      // ITargetsSelector -- UNE cible, la 1re
        foreach (caster in (+0x58 caster).Select(entities)) // ITargetsSelector -- la boucle est ICI
            processor.ActiveAbility(caster, targets, abilityType, options)

    (#943 -- les deux numeros de slot d'`ITargetsSelector` sont donnes DANS LA PROSE juste au-dessus
    et plus en fin des deux lignes de pseudo-C : ecrits la, `probe_477r24r1` les appariait au
    `processor.<Nom>` de la ligne SUIVANTE -- il juge le recepteur sur le SPAN du couple, et cette
    ligne-la en porte un. Le couple faux etait `(slot 0, ActiveAbility)`, alors que le slot 0 cite
    ici est celui d'une AUTRE interface. Les noms `Select` / `SelectFirst`, eux, restent au site.)

    Ce noeud ITERAIT LES CIBLES, triees par id -- l'exact contraire. La divergence etait INERTE sur
    les **14** call-sites portes (RE-COMPTES au recensement AST : le compte « un seul, FinalJustice »
    de cette docstring etait perime de treize), tous ayant un selecteur de cible collapse a UNE
    unite (`Target()` 9 fois, `First(...)` / `PickRandomly(..., 1)` 5 fois) ET un selecteur de
    caster mono. Elle aurait mordu au PREMIER call-site dont le selecteur de cibles rend N :
    `MartialExemplarAbility$$ExecuteBehaviour` passe `SortUnitsByDamageUtility(<attaquables
    adjacents>)` **SANS `First`**, et iterer les cibles y frapperait N unites la ou le natif n'en
    frappe qu'UNE, la mieux classee. **Aucun tri** : le natif n'appelle pas `OrderBy` ici (contraste
    `AttackBehaviour$$Execute`, qui trie quand `Count > 1`) -- l'ordre des casters est celui du
    selecteur.

    `UseNormalAttack` / `UseNormalAttackIfAble` (ci-dessous) sont le MEME behaviour natif avec
    `activeAbilityType = DSLSelectors$$UnitNormalAttackType(caster)` : ils HERITENT donc de ce
    corps, au lieu de le dupliquer. C'etait le second volet de #889-r5-r1 (« les trois devraient
    partager un seul corps »).

    LES DEUX DISPATCHES, ET CE QUI LES SEPARE (`ability_type`, #996-r1-r3)
    ---------------------------------------------------------------------
    Le 3e champ natif (`+0x50`) n'est PAS un entier : c'est un `IAbilityTypeSelector`, resolu PAR
    CASTER dans la boucle (`processor[+0x20] = caster` PUIS `(+0x50).Select(entities)`), et le
    dispatch n'a lieu QUE si le `Nullable` rendu a `HasValue`. Les deux factories qui le
    remplissent :

      * `DSLBehaviors$$UseNormalAttack` / la surcharge d'`$$UseActiveAbility` a **selecteur**
        (`180ea6a20`, 17 call-sites) -> `UnitNormalAttackType(caster)` : l'ATTAQUE NORMALE du
        caster. C'est `ability_type = None` ici, le comportement historique, specialise a
        `AttackDamageOperation.execute` (resolveur ECS : arme par distance, spread, reduce/armure,
        DEJA bit-exact) ;
      * la surcharge a `ActiveAbilityType` **ENTIER** (`180ea6b30`, 3 call-sites), qui emballe le
        litteral dans un `AbilityTypeSelector.DirectAbilitySelector(AbilityOrEffect(<type>))`.
        TRANCHEE AUX XREFS ENTRANTES, jamais au pseudo-C : les deux surcharges ont sept parametres
        et le meme nom affiche.

    Des 3 call-sites de la seconde, DEUX passent `0x45 = Loki_NormalAttack`
    (`UnbreakableDutyAbility$$ExecuteBehaviour`, `RedemptionOfTheRisenAbility$$CreateBehaviour`) --
    donc le meme dispatch normal. Le SEUL a passer un type NON-NORMAL est
    `PrecisionShotAbility$$ExecuteBehaviour` (`0x3f4 = 1012 PrecisionShot_Aim`), et c'est lui qui
    exigeait cet etage : lui donner le chemin d'attaque normale lui ferait INVENTER une attaque
    que le natif ne porte pas -- pire qu'un no-op.

    DISPATCH NON-NORMAL : `processor.<slot 2 IOperationProcessor>(caster, targets, abilityType,
    options)` = `Core.Services.OperationProcessor$$ActiveAbility` ->
    `IdunBattle.Operations.ActiveAbilityOperation$$Execute` -> `$$ExecuteInternal`. Le port y entre
    par `AbilityHandler.active_ability_operation`, qui est le mirror de CE rang-la -- donc SANS le
    gate de message d'`InputMessageProcessor$$Visit` (le natif ne repasse pas par le visiteur,
    #429-r1-r3), et AVEC les gates de l'operation : acteur-mort, cible-morte, `IsInvalidTarget`
    (volet CASTER inclus, donc la regle dynamique du sous-cast). Un sous-cast REFUSE est donc un
    no-op COMPLET, exactement comme cote natif -- et il reste LISIBLE : son diagnostic part dans
    `sub_cast` de l'evenement emis.

    `is_regular_attack` est le mirror d'`idun.Idun.Source.Shared.Battle.StaticBattleRules.
    StaticBattleRules.ActiveAbility$$IsRegularAttack` : c'est LUI qui separe les deux chemins, pas
    une liste ecrite ici.

    `spread_pct` = variance d'arme du dispatch normal ; `None` (le cas normal) = LU de
    `BattleConfiguration.Damage.DamageSpreadPercentage` a l'EXECUTION, quand l'etat de bataille est
    connu (#449-r2-r4 -- le natif lit lui aussi la config au moment du calcul, jamais a la
    construction du behaviour).

    Emet `type(self).__name__` par caster. PUR (non court-circuitant)."""
    __slots__ = ("caster_sel", "target_sel", "spread_pct", "ability_type")

    #: Le champ `+0x00` des `UseActiveAbilityBehaviourOptions` : un
    #: `System.Nullable<IdunBattle.Operations.ActiveAbilityOperation.InvalidTargetPolicy>`.
    #: `None` = le `Nullable` VIDE que `$$UseActiveAbility` et `$$UseNormalAttack` laissent, et dont
    #: `ActiveAbilityOperation$$ExecuteInternal` prend le `GetValueOrDefault` = `Error`.
    #: `UseNormalAttackIfAble` le pose a `Skip` (#889-r5-r2, ferme par #944 -- cf. le mirror
    #: `engine/entities/invalid_target_policy.py` pour la chaine LUE et la semantique).
    INVALID_TARGET_POLICY: Optional[int] = None

    def __init__(self, caster_sel: TargetsSelector, target_sel: TargetsSelector,
                 spread_pct: Optional[int] = None, ability_type: Optional[int] = None):
        self.caster_sel, self.target_sel = caster_sel, target_sel
        # NON resolu ici : l'arbre DSL est construit AVANT toute bataille (aucun `State`). La
        # resolution vit dans `execute`, ou `ectx.state` porte la BC.
        self.spread_pct = None if spread_pct is None else int(spread_pct)
        # `None` = le selecteur `UnitNormalAttackType(caster)` des factories a selecteur (le cas de
        # tous les call-sites historiques). Un ENTIER = le `DirectAbilitySelector` de la surcharge a
        # `ActiveAbilityType`, cf. la docstring : REGULAR -> meme chemin normal, sinon dispatch.
        self.ability_type = None if ability_type is None else int(ability_type)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        # `targets = (+0x60).SelectFirst(entities)` -- slot 1, UNE cible, la PREMIERE de l'ordre du
        # selecteur, et EVALUEE AVANT la boucle (le natif lit `+0x60` puis `+0x58`).
        target = None
        for t in _units_of(self.target_sel, entities):
            if isinstance(t, dict) and t.get("id") is not None:
                target = t
                break
        if target is None:
            return OperationResult.ok()
        tid = target["id"]
        for cu in _units_of(self.caster_sel, entities):       # `(+0x58).Select(entities)`, slot 0
            if not isinstance(cu, dict) or cu.get("id") is None:
                continue
            sid = cu["id"]
            # --- DISPATCH NON-NORMAL (#996-r1-r3) ------------------------------------------------
            # `(+0x50).Select(entities)` rend un type qui n'est PAS une attaque reguliere -> le
            # natif appelle le slot 2 du processeur, pas `AttackDamage`. Le port entre au MEME rang
            # (`ActiveAbilityOperation$$Execute`), donc la sous-ability rejoue TOUTE la chaine :
            # gates (acteur-mort, cible-morte, `IsInvalidTarget` volet caster inclus), `On(0x2a)`,
            # sa behaviour, les flags de tour, `On(0xb)/On(0xc)/On(0xe)`.
            if self.ability_type is not None and not is_regular_attack(self.ability_type):
                # Import DIFFERE, classe PORTEUR (mesure `probe_996r1r3_import_differe.py`) :
                # charger `abilities.handler` seul dans un process FRAIS fait deja atterrir
                # `abilities.behaviours.combat` dans `sys.modules` (le registre importe les 30
                # modules d'abilities, qui construisent tous leurs arbres depuis ces feuilles) --
                # hisser fermerait donc un cycle. Forme MODULE (`import X` puis `X.Y`) : une
                # substitution posee sur `handler` MORD, contrairement au `from X import Y` de
                # niveau module (cf. la regle des trois formes, CLAUDE.md).
                from .. import handler as _handler            # noqa: PLC0415
                diag = _handler.AbilityHandler(state).active_ability_operation(
                    sid, tid, self.ability_type)
                ectx.emit(type(self).__name__, subject=sid, target=tid, attack=None, after_hit=[],
                          skipped=None, ability_type=self.ability_type, sub_cast=diag,
                          invalid_target_policy=type(self).INVALID_TARGET_POLICY)
                continue
            # TRI-ETAT sur l'absence d'attaque, et il est NECESSAIRE : un `attack=None` nu ne dit
            # pas SI l'operation a ete refusee (gate cible-morte / stats absentes) ou si le RNG
            # n'etait pas cale -- deux causes opposees, l'une fidele au natif, l'autre un trou de
            # harnais. Sans ce champ, une confrontation live lit « le port ne frappe pas » sans
            # pouvoir dire pourquoi. Meme discipline de nommage que `host_inputs` (#889-r5).
            if state.rng is None:
                # DEFENSIF (mirror `execute_ability_attack` : rng non cale -> None au lieu de
                # lever) : le wiring d'ability reste utilisable pour un replay EFFET-SEUL
                # (`load_state` sans `dumpRng`), la SEQUENCE (setHealth/buffs/move) restant fidele ;
                # le dispatch normal `AttackDamageOperation.execute` leverait sinon (ValueError rng
                # non cale). Un replay de DEGAT cale rng (dumpRng) avant.
                ectx.emit(type(self).__name__, subject=sid, target=tid, attack=None, after_hit=[],
                          skipped="rng_non_cale",
                          invalid_target_policy=type(self).INVALID_TARGET_POLICY)
                continue
            # `allow_dead_caster=True` = le LITTERAL `1` que `UseActiveAbilityBehaviour$$Execute`
            # force dans les `AbilityOptions` qu'il assemble (`uStack_210._0_2_ =
            # CONCAT11(*(behaviour + 0xa8), 1)` -- le SEUL octet en dur d'une struct autrement
            # recopiee champ par champ) : cette voie autorise un caster MORT, et c'est
            # indispensable au death-rattle FinalJustice (mesure live #88 : Titus a hp=0 porte sa
            # riposte pour 10502 et tue). Sans lui, le gate acteur-mort de `damage_ops/normal.py`
            # (#133 MartialSuperiority) avalait toute la riposte.
            res = AttackDamageOperation.execute(
                state, sid, tid, resolve_spread_pct(self.spread_pct, state),
                allow_dead_caster=True)
            # VECTEUR `On(0x26 = NormalAttack)` -- #BL-1029r, volet du residu `#478-r3`.
            # Le natif n'a qu'UN site d'emission : `ALoki_NormalAttackAbility$$
            # ExecuteTriggerAbilities`, a la CLOTURE de l'attaque normale, donc quelle que soit la
            # PORTE qui l'a ouverte. Le port, lui, l'emettait UNIQUEMENT depuis la voie MESSAGE
            # (`DamageHandler.visit_AttackUnitMessage` -> `after_hit_normal_attack`) : une attaque
            # normale dispatchee par CETTE feuille ne reveillait donc AUCUN trigger `On(0x26)`.
            # MESURE qui l'etablit (`probe_bl_1029_1020_baseline.py`, seed 777, board MC1_67) :
            # le cast de `Drachnyen` rend **10 coups live** sur la cible et n'en rendait que **6**
            # offline -- les 4 manquants sont ceux de `Drachnyen_ExtraAttackAbility` (triggered
            # 1485), dont le trigger est precisement `On(0x26)`. Les 6 premiers etaient deja
            # bit-exacts, ce qui isole l'ecart a CE vecteur et a lui seul.
            # `finish_attack` (les resultats du `On(9)` emis DANS l'operation) est remis EN TETE,
            # meme ordre natif et meme forme que `DamageHandler` (`FinishAttack` precede
            # `ExecuteTriggerAbilities`).
            after = []
            if res is not None:
                from ...operations.triggers.dispatch.attack import after_hit_normal_attack
                after = (res.get("finish_attack") or []) + after_hit_normal_attack(
                    state, sid, res.get("target", tid), bool(res.get("ranged")),
                    res.get("profile"), is_crit=bool(res.get("did_crit")),
                    did_block=bool(res.get("did_block")))
            ectx.emit(type(self).__name__, subject=sid, target=tid, attack=res, after_hit=after,
                      skipped=None if res is not None else "operation_refusee",
                      invalid_target_policy=type(self).INVALID_TARGET_POLICY)
        return OperationResult.ok()


class UseNormalAttack(UseActiveAbility):
    """`IdunBattleLogic.Entities.DSLBehaviors$$UseNormalAttack(caster, target, parentAbility,
    triggerAbilityOrEffect, options)`.

    Le corps natif tient en deux lignes -- il alloue `DSLSelectors$$UnitNormalAttackType(caster)`
    puis `new UseActiveAbilityBehaviour(caster, target, <ce type>, parentAbility,
    triggerAbilityOrEffect, options)`, en recopiant `options` TEL QUEL. C'est donc EXACTEMENT le
    behaviour de `UseActiveAbility` ci-dessus, dont cette classe herite le corps entier : la
    distinction existe pour que l'arbre CITE la factory que le natif cite.

    `parent_ability` / `trigger_ability_or_effect` sont ZEROES aux call-sites lus, et le port ne
    leur prete aucun effet.

    Emet 'UseNormalAttack' (subject/target/attack/after_hit/skipped/invalid_target_policy)."""
    __slots__ = ()


class UseNormalAttackIfAble(UseNormalAttack):
    """`IdunBattleLogic.Entities.DSLBehaviors$$UseNormalAttackIfAble(caster, target, parentAbility,
    triggerAbilityOrEffect, options)`.

    Corps natif IDENTIQUE a `UseNormalAttack` (meme allocation d'`UnitNormalAttackType`, meme
    `UseActiveAbilityBehaviour..ctor`, memes six arguments -- verifie ligne a ligne) A UNE ECRITURE
    PRES, faite AVANT le ctor :

        Nullable<InvalidTargetPolicy>.ctor(&tmp, 2) ; *(long*)options = tmp ;

    ⚠ **SA SEMANTIQUE EST DESORMAIS LUE** (#889-r5-r2, ferme par #944) -- et elle dit que ce champ
    n'a AUCUN effet sur l'etat de bataille. Chaine suivie de bout en bout : le champ `+0x00` des
    `UseActiveAbilityBehaviourOptions` arrive en tete des `ActiveAbilityOptions` du slot 2, et
    `IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` le passe en **6e argument**
    d'`$$IsInvalidTarget`, dont la signature le NOMME `invalidTargetPolicy`. Son corps :

        if (invalidTargetPolicy == Allow) return false;      # gate court-circuite
        ...
        if (!IBrokenTargetingRuleExtensions.IsInvalid(rule)) return false;
        if (invalidTargetPolicy != Error) return true;       # invalide, SANS log
        <LogError(...)>;                                     # invalide, AVEC log
        return true;

    -> `Skip` et `Error` (le defaut du `Nullable` vide) rendent le **MEME verdict** : seul le
    `LogError` les separe. C'est bien le sens de << IfAble >> -- un cast opportuniste dont le refus
    n'est pas un bug -- mais ce n'est PAS un gate supplementaire. Le port a donc raison de ne pas en
    inventer un ; il NOMME desormais la valeur au lieu de la transporter en entier nu. La seule
    valeur qui changerait quelque chose est `Allow`, qu'**aucun** call-site lu ne pose.

    Le MEME champ est renseigne, a `Skip` lui aussi, par
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.AutoCounterAttackAbility$$CreateBehaviour` --
    il n'est donc pas specifique a << IfAble >>. La voie JOUEUR
    (`InputMessageProcessor.<>c__DisplayClass13_0$$<Visit>b__0`) le prend de `message+0x20`."""
    __slots__ = ()
    INVALID_TARGET_POLICY = int(InvalidTargetPolicy.Skip)   # le litteral `2` du corps natif
