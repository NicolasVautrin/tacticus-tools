"""Base du namespace `IdunBattle.AI.Playbook` — hiérarchie + registry (RE playbook/architecture.md §2.2).

Hiérarchie native : `BasePlaybook -> {ComparablePlaybook<T>, NonComparablePlaybook<T>}`. Un générateur
d'action fait `LoadPlaybook(abilityType) -> playbook.Evaluate(unit, tile)` ; c'est le playbook qui
énumère ses cibles et les score. Deux régimes :

- **Comparable** (`ComparablePlaybook<T>`, attaques/soins) : `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$EvaluateInternal` boucle les
  cibles éligibles à position caster FIXÉE, `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility` par cible
  (`= predictionUtility + Σ CalculateUtilityFromPredictions + [gate ShouldExecute] + Tile(7)`), argmax
  dans un Bucket. `MakeDamagePredictions` (vtable) = le fournisseur de prédiction, OVERRIDÉ par playbook.
- **NonComparable** (`NonComparablePlaybook<T>`) : heuristique entière dans la feuille -> package `noncomparable/`.

PRÉDICTEUR : `ComparablePlaybook.make_damage_predictions` délègue à `engine.playbook.prediction`
(orchestration mince) sur le MODÈLE OBJET — `Scene` (état live) + `AActiveAbility`/`UnitContext`
(entities) + services (`BattleQuery` sélection d'arme, `DamagePrediction`/`DamageCalculations`) — et
produit des `ProbableDamageEvent`. Couvre AoE, multi-hit, split bouclier, modifiers d'effets, self-damage.
"""
from __future__ import annotations

from typing import Callable

import engine.playbook.prediction as prediction   # sous-paquet FRERE, pas `from . import` (#270-r4-r2)
from ..weights import Weights
from ..utilities import damage_composite
from ..utilities.tile import tile_composite
from ..utilities.tile import (terrain_tile_effects, tile_leaf_ctx,   # lazy : évite tout cycle
                                  apply_tile_attributes)
from ..utilities.tile import (triggered_abilities_attack_utility,
                              triggered_abilities_non_owner_attack_utility)
from ..utilities.wireweave_net import wireweave_net_first_attack_utility
from ..predict import heal_action_utility


class _NoActionUtility:
    """Sentinelle de PORT : « le custom a rendu une valeur que `CalculateActionUtility` traduit en
    `Nullable` VIDE » — c'est-à-dire AUCUNE action générée pour ce (tuile, cible).

    Ce n'est pas une convention inventée, c'est un mirror. `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
    commence par appeler `CalculateCustomUtility` (slot de vtable +0x338) puis compare son résultat à
    TROIS constantes de `IdunBattle.AI.Utilities.BaseUtility`, AVANT toute prédiction :

        u = CalculateCustomUtility(...)
        if (u == BaseUtility.<statics+0x18>) return null;          // Nullable VIDE
        if (u == BaseUtility.<statics+0x20>) return null;          // Nullable VIDE
        if (u == BaseUtility.<statics+0x10>) return Nullable(BaseUtility.<statics+0x10>);
        u += CalculateUtilityFromPredictions(...); ...

    Les trois valeurs, lues dans `IdunBattle.AI.Utilities.BaseUtility$$.cctor` (qui les dérive de
    `FixMath.NET.Fix64$$.cctor` : `Fix64.<statics+0x10>` = `0x7fffffffffffffff` = MaxValue,
    `Fix64.<statics+0x18>` = `0x8000000000000000` = MinValue) :

        BaseUtility.<statics+0x10> = Fix64.MaxValue
        BaseUtility.<statics+0x18> = Fix64.MinValue / Fix64.FromIntFraction(1000001, 1000000)
        BaseUtility.<statics+0x20> = Fix64.MinValue

    Ce sont donc des VETOS : une utilité au voisinage de `MinValue` ne « perd » pas la comparaison,
    elle SUPPRIME l'action. Le port les représente par une IDENTITÉ (`is NO_ACTION`) plutôt que par
    un flottant proche de `-2**31` : la comparaison native est une égalité EXACTE sur un Fix64, qu'un
    port en `float` ne peut pas reproduire de façon fiable, et une valeur très négative laissée dans
    l'arithmétique serait sommée aux termes suivants au lieu d'annuler l'action.

    Porteur actuel : `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$CalculateCustomUtility`
    (1098), qui rend `BaseUtility.<statics+0x18>` dès que sa somme vaut `Fix64(0)`."""

    __slots__ = ()

    def __repr__(self) -> str:            # diagnostic lisible en trace de décision
        return "NO_ACTION"


NO_ACTION = _NoActionUtility()


class BasePlaybook:
    """Racine `BasePlaybook`. `ability_id` = l'AbilityType (clé du registry). `priority` = le tier de
    préférence (`get_Priority`, interface slot 0 ; défaut 0 = `AbilityPriority.Normal`, surchargé par
    22 playbooks — cf. `engine.playbook.noncomparable.NATIVE_PRIORITY`). Les sous-classes concrètes
    (Comparable/NonComparable) définissent l'énumération + le scoring."""

    ability_id: int = -1
    priority: int = 0                     # tier de préférence (0 = AbilityPriority.Normal)

    def will_normal_attack_kill(self, ctx, target, caster_tile) -> bool:
        """`IdunBattle.AI.Playbook.BasePlaybook$$WillNormalAttackKill` — **surcharge à 4 arguments**
        `(this, caster, target, casterTile)`, lue verbatim :

            if (target == null) return false;
            pred = battleQuery.<slot d'interface 0x21>(caster, target, casterTile);   // this@+0x28
            return new ProbableDamageEvent(target, pred, default, default)
                       .<DamagePredictionResult @+0x8>.get_WillBeKill();

        `this@+0x28` EST le `IBattleQuery` : `IdunBattle.AI.Playbook.BasePlaybook$$Init` pose
        `this+0x20 = state`, `this+0x28 = query`, `this+0x18 = dsl`, `this+0x40 = utilitiesDatabase`
        (lu, pas déduit). Le slot `0x21` est la prédiction de l'attaque NORMALE — le même que celui
        que `MakeDamagePredictions` de l'attaque normale emprunte, `0x22` étant celui de l'ability.

        `get_WillBeKill` = le SURE-kill (borne MIN des dégâts >= PV courants), donc `killSure` du
        composite du port, PAS `killChance`.

        La seconde surcharge, `BasePlaybook$$WillNormalAttackKill(this, entities)`, n'est qu'un
        relais qui déplie `entities` (`+0x8` = caster, `+0x10` = target, `+0x40` = casterTile) sur
        celle-ci ; c'est elle que les playbooks NonComparable appellent.

        FOYER UNIQUE du port : `noncomparable/_base.py::_will_normal_attack_kill` et
        `loki_custom.SorcerousFacadePlaybook` y délèguent — trois corps auraient été un fork.
        BORNES DE PORT (les deux au-delà du `target == null` natif, toutes deux vers `False` = « le
        gate ne mord pas ») : prédicteur absent (`ctx.scene is None`) et tuile de cast absente. Le
        natif ne teste ni l'un ni l'autre parce qu'il ne peut pas les recevoir nuls."""
        return will_normal_attack_kill(ctx, target, caster_tile)


def will_normal_attack_kill(ctx, target, caster_tile) -> bool:
    """Corps du foyer ci-dessus, en fonction libre — la route NonComparable l'appelle sans instance
    (`noncomparable/_base.py::_will_normal_attack_kill`, mirror de la surcharge `(this, entities)`
    qui relaie vers celle-ci)."""
    if target is None or caster_tile is None:
        return False
    scene = getattr(ctx, "scene", None)
    if scene is None:
        return False
    ev = prediction.make_normal_attack_predictions(scene, ctx.uid, target, caster_tile)
    if ev is None:
        return False
    return bool((ev.composite_fields() or {}).get("killSure"))


# ── Terme de tuile Tile(7) partagé (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromTilePrediction`) ────────────────
def tile_utility(ctx, pos) -> float:
    """Composite Tile(7) évalué sur la tuile caster `pos` — MÊME Composed que le sweep MOVE (case-49 :
    le natif émet `ComposedUtility` identique sous le playbook d'ATTAQUE, L3 s14 31337 — feuille
    TriggeredAbilities(2) incluse : natif (3,4)=25=30elev-25effets+20trig vs (4,3)=40=30+10trig).
    Meta et leaf_ctx MIRROIR de `engine.move` (élévation min/max BOARD, effets dynamiques + covers
    terrain, kit passif + fpos via `tile_leaf_ctx`). Sur carte plate ≈ 0. Bonus additif."""
    meta: dict = {}
    e = ctx.elev_by_pos.get(pos)
    if e is not None:
        _elevs = [x for x in ctx.elev_by_pos.values() if x is not None]
        meta = {"elevation": e, "elevation_max": max(_elevs), "elevation_min": min(_elevs)}
    if pos in ctx.is_temporary_by_pos:
        meta["is_temporary"] = ctx.is_temporary_by_pos[pos]
    _effs = list(ctx.effects_by_pos.get(pos) or [])          # feuille TileEffects (ex. Thorns=-25)
    # ctx POLYMORPHE : NCContext (NovaShield via get_movement_utility) n'a pas `terrain_by_pos`.
    # covers hebergés (case-37) + repli Loop1 non hydraté ; `_effs` = canal dynamique (#155)
    _effs += terrain_tile_effects((getattr(ctx, "terrain_by_pos", None) or {}).get(pos), _effs)
    if _effs:
        meta["effects"] = _effs
    leaf_ctx = tile_leaf_ctx(ctx)
    apply_tile_attributes(meta, pos, leaf_ctx)   # isTerritory / effects[].effectType (cf. tile.py)
    return tile_composite(pos, meta, leaf_ctx, ctx.wt)


class _UnitView:
    """Vue de l'`AiDecisionContext` recentrée sur une AUTRE unité que le mover — l'`unit` que porte
    le `UtilityAttackCase` quand ce n'est pas le caster.

    Ce n'est pas une commodité : c'est ce que le natif fait. `IdunBattle.AI.Playbook.Playbooku003C
    __Il2CppFullySharedGenericTypeu003E$$GetTargetUtilityDiffOnDisplace` construit
    `UtilityAttackCase$$Base(target, UnitPosition(tile), tile, aoe)` — le `caster` du case (`+0x10`)
    est **la cible**, pas le lanceur —, et les feuilles Tile(7) recopient ce champ dans
    `UtilityMovementCase+0x10` (`IdunBattle.AI.Utilities.UtilityMovementCase$$.ctor(attackCase)`)
    avant de le passer à `HasTrait(case.unit, …)` / `HasFaction(case.unit, …)` et aux comptes
    d'adjacence. Évaluer `Tile(7)` avec le kit du CASTER serait donc un fork de port, pas une
    approximation.

    Trois champs sont redérivés, le reste est délégué tel quel (les cartes par-position
    — élévation, effets, walkable — ne dépendent pas de l'unité) :

    - `me` / `uid` : l'entrée `ctx.units` de l'unité visée ;
    - `units` : la MÊME liste, mais `ctrl` recalculé **du point de vue de cette unité**
      (`ctrl' = (ctrl == ctrl_de_l_unite)`). `_adjacent_units` classe `friends`/`enemies` sur ce
      booléen, et le natif dérive ses deux ensembles de `GetCurrentPlayer(case.unit)` : pour une
      cible ENNEMIE, amis et ennemis sont donc échangés ;
    - `fpos` / `enemies` : les positions des deux camps, réalignées sur ce même point de vue."""

    __slots__ = ("_ctx", "me", "uid", "units", "fpos", "enemies")

    def __init__(self, ctx, unit: dict):
        self._ctx = ctx
        self.me = unit
        self.uid = unit.get("id")
        mine = bool(unit.get("ctrl"))
        self.units = [dict(u, ctrl=(bool(u.get("ctrl")) == mine))
                      for u in (getattr(ctx, "units", None) or [])]
        self.fpos = [(u["pos"]["col"], u["pos"]["row"]) for u in self.units
                     if u.get("ctrl") and u.get("alive") and u.get("pos")]
        self.enemies = [u for u in self.units if not u.get("ctrl") and u.get("alive")]

    def __getattr__(self, name):
        return getattr(self._ctx, name)


def tile_utility_for_unit(ctx, unit: dict, pos) -> float:
    """`Tile(7)` évalué sur la tuile `pos` POUR l'unité `unit` — `GetUtility(UtilityType.Tile)
    .EvaluateAttack(UtilityAttackCase$$Base(unit, UnitPosition(pos), pos, aoe))`.

    Le mode ATTACK n'est PAS un chemin distinct : chaque feuille de tuile convertit son
    `UtilityAttackCase` en `UtilityMovementCase` et délègue au slot `EvaluateMovementInSteps`
    (corps identiques de `IdunBattle.AI.Utilities.ElevationUtility$$EvaluateAttackInSteps`,
    `…AUnitEffectsUtility$$EvaluateAttackInSteps`, `…CapturePointTileUtility$$EvaluateAttackInSteps`).
    Le facteur de `IdunBattle.AI.Utilities.ComposedUtility$$CalculateAttackModifier` vaut 1 pour ce
    composite : les TROIS seules utilities qui l'overrident (`DislikeBossUtility`,
    `DislikeEnvironmentUnitsUtility`, `DislikeObjectsUtility`) sont des feuilles du composite
    d'ATTAQUE, aucune n'est une feuille de Tile(7). => même somme que `tile_utility`, au point de
    vue d'unité près."""
    return tile_utility(_UnitView(ctx, unit), pos)


class ComparablePlaybook(BasePlaybook):
    """`ComparablePlaybook<T>` — régime somme-pondérée sur prédictions (attaques d'abord). Le playbook
    dispatché par le générateur ; `make_damage_predictions` (le fournisseur de prédiction) est OVERRIDÉ
    par sous-classe (NormalAttack -> PV.normal ; Default/spéciales -> PV.special)."""

    is_normal_attack: bool = False        # tie-break natif : à utilité TOTALE égale, la normale gagne

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        """`Playbook.MakeDamagePredictions` (vtable +0x358) : liste `[(target_id, event_dict), …]` =
        cible principale + AoE, ou None/[] si NON-attaque. Délègue au port PV (complet/validé)."""
        raise NotImplementedError

    def make_effect_predictions(self, ctx, caster_tile, target, ability_id):
        """`ComparablePlaybook.MakeEffectPredictions` (vtable +0x388) : liste de `ProbableEffectEvent`
        (pose d'effet probable). BASE = VIDE (`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$MakeEffectPredictions` = `new List()`) — l'immense majorité des
        abilities n'ajoute PAS d'effet-prédiction. SEUL `SpiritLeechPlaybook IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$MakeEffectPredictions` l'override dans
        ce build (effet Pinned=0x429, poids 0 -> inerte). Override par sous-classe au besoin."""
        return []

    def make_heal_predictions(self, ctx, caster_tile, target, ability_id, events) -> list:
        """`ComparablePlaybook<T>.MakeHealPredictions` — la TROISIÈME branche de prédiction, à côté de
        `MakeDamagePredictions` et `MakeEffectPredictions`. BASE = VIDE : la quasi-totalité des
        abilities d'attaque ne prédit aucun soin.

        Rend une liste de tuples `(effective_heal, target_max_hp, is_friend, is_boss)` — le format que
        `engine.predict.heal_action_utility` (mirror du fold `CalculateUtilityFromHealEvent`, slot
        +0x368, 2ᵉ boucle de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`)
        consomme.

        ⚠ `events` (les `ProbableDamageEvent` déjà produits) s'ajoute aux arguments natifs : le seul
        porteur du build, `IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$MakeHealPredictions`,
        appelle `SpiritLeechAbility$$GetHealAmountForPrediction(target, abilityState)`, qui refait sa
        PROPRE prédiction de dégât ; le port réutilise celle de `MakeDamagePredictions` —
        approximation CONFRONTÉE live (#339), pas un raccourci de commodité."""
        return []

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        """`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCustomUtility` = `Fix64.FromInt(0)`. Terme d'ACTION
        ajouté PAR-DESSUS `u_full` (pair + Tile) dans l'assemblage du BucketAction — il n'apparaît PAS
        dans le pairUtility (le scorer natif confronté à l'étage UTILITÉ ne le contient pas ; preuve
        L3 #64 : playbook_action u = pair + tile + custom exacts). Overrides natifs : NormalAttack +1
        (common.py) ; quirks per-ability NON portés à ce jour (MortisRound IdunBattle.AI.Playbook.Loki.MortisRoundPlaybook$$CalculateCustomUtility displacement,
        Drachnyen IdunBattle.AI.Playbook.Loki.DrachnyenPlaybook$$CalculateCustomUtility count>=2, HeraldOfTheApocalypse IdunBattle.AI.Playbook.Loki.HeraldOfTheApocalypsePlaybook$$CalculateCustomUtility, ProperKilly IdunBattle.AI.Playbook.Loki.ProperKilly_NormalAttackPlaybook$$CalculateCustomUtility...)."""
        return 0.0

    def calculate_caster_position_utility(self, ctx, caster_tile, ability_id) -> float:
        """`CalculateCasterPositionUtility` — **slot de vtable +0x348**, sommé par
        `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
        APRÈS le gate `ShouldExecute` et AVANT la clé `0x37` puis `Tile(7)` — c'est ce RANG-là qui
        est porté ici, pas une place de commodité.

        DÉFAUT `0.0`, et c'est le corps natif EXACT, pas une convention permissive :
        `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateCasterPositionUtility`
        est `return Fix64.op_Implicit(0);` (deux instructions). L'ajout est donc un **no-op mesuré**
        pour les 100+ membres actuels du registre : aucun ne l'override.

        Le terme ne prend NI la cible NI l'utilité déjà sommée — seulement le caster et sa position
        candidate (`caster, casterPosition, abilityOrEffect`). Il départage donc les POSITIONS, pas
        les cibles. Premier overrideur porté : `1165 MightFromBelow`
        (`playbook/might_from_below.py`) ; `1184 MomentShackle` porte le même slot mais par sa route
        BESPOKE (`playbook/bespoke.py`), où il est déjà sommé à la main.

        ⚠ La seconde route Comparable (`playbook/nonattack.py::nonattack_candidates`) somme le même
        terme côté natif ; elle ne l'appelle pas encore — résidu nommé de `case-27`, INERTE tant
        qu'aucun membre de `NONATTACK_PLAYBOOKS` ne l'override (mesure : 0 sur ce build)."""
        return 0.0

    def should_execute(self, ctx, caster_tile, target, ability_id, utility) -> bool:
        """`ComparablePlaybook<T>.ShouldExecute` — **slot de vtable +0x328**, appelé par
        `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`
        avec `(caster, casterPosition.MainTile, target, attackHealUtility)`. `False` ⇒ le natif rend
        un `Nullable` VIDE : **aucune action** n'est poussée dans le `Bucket` pour ce (tuile, cible).

        DÉFAUT = `return true`, et c'est une MESURE, pas une déduction — mais la forme native est
        plus subtile que « la base rend true », alors disons-la exactement. Le `MethodInfo` du
        niveau `ComparablePlaybook`1` porte un `methodPointer` **NUL** (la définition générique n'a
        pas de corps compilé) ; ce sont les classes CONCRÈTES qui déclarent chacune leur propre
        `MethodInfo`, et celles qui ne spécialisent rien pointent toutes sur le MÊME corps de trois
        octets `b0 01 c3` (`mov al,1 ; ret`) — mesuré sur six classes indépendantes
        (`Drachnyen`, `Chronometron`, `DoomSiren`, `ForwardObservers`, `PlasmaGrenade`,
        `MartialInspiration`). L'unique propriétaire NOMMÉ de ce corps dans les tables est
        `UnityEngine.U2D.IK.Solver2D$$DoValidate` : dédup IL2CPP d'un corps trivial. Le comportement
        par défaut EFFECTIF est donc bien « accepter », et c'est ce que cette base porte.

        ⚠ Corollaire de méthode : « `<Classe>$$ShouldExecute` n'est pas dans la table » ne prouve
        RIEN. `MortisRoundPlaybook` déclare le sien à `depth 0` sur le corps que la table attribue à
        `IdunBattle.AI.Playbook.Loki.SpiritLeechPlaybook$$ShouldExecute` — même corps, un seul
        propriétaire nommé.

        `utility` = `CalculateCustomUtility + CalculateUtilityFromPredictions`, donc AVANT les trois
        termes positionnels (`CalculateCasterPositionUtility` slot +0x348, la clé `0x37`
        `WireweaveNet_FirstAttack`, `CalculateUtilityFromTilePrediction`). Un playbook qui override
        (`ALoki_NormalAttackPlaybook<T>`, `Loki_NormalBossAttackPlaybook`, `HealPlaybook`, …)
        redéfinit cette méthode."""
        return True

    def calculate_utility_from_predictions(self, ctx, caster_tile, target, ability_id,
                                           events) -> tuple:
        """`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
        = Σ `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromDamageEvent`
        (= prob1 × prob2 × composite Damage ; event FRIENDLY -> utilité NÉGÉE) + Σ des events d'EFFET
        (branche +0x388, base vide). Renvoie `(u, bk)`.

        EXTRAIT de `calculate_action_utility` (aucun changement de comportement pour elle) pour être
        consommable par la SECONDE route Comparable (`playbook/nonattack.py`), dont le natif somme
        exactement le même terme : `CalculateActionUtility` fait `u = custom` PUIS
        `u += CalculateUtilityFromPredictions(...)` — le régime « sans prédiction » n'est que le cas
        où `MakeDamagePredictions` rend une liste vide, pas une route où le terme n'existe pas."""
        from .probable_damage_event import (calculate_utility_from_damage_event,
                                            calculate_utility_from_effect_event)
        u = 0.0
        bk = []
        for ev in (events or []):
            ua = calculate_utility_from_damage_event(ev, ctx.wt, ctx.hpmax_by_id.get(ev.target))
            # Feuille TriggeredAbilities(2) face ATTACK (#45-s18, splash Psyker) : évaluée DANS le
            # composite par event (`ForDamagePrediction`) -> même prob × signe que le composite.
            # #438 : le case natif de CET event porte sa `DamagePrediction` (`ForDamagePrediction`,
            # 4e argument) -> on la passe. Sans elle, `BarbedOvipositorPlaybook` lirait un case
            # `HasValue == false` et rendrait 0 en silence.
            trig = triggered_abilities_attack_utility(ctx, ctx.uid, ability_id, ev.target, caster_tile,
                                                      prediction=ev.prediction)
            # Feuille TriggeredAbilitiesNonOwner(4) face ATTACK (#271-r4) : l'AUTRE dispatcher du
            # composite Damage(35) — celui qui itère les abilities déclenchées des AUTRES unités.
            # Même rang, même prob x signe : la carte de composition MESURÉE
            # (`probe_271r4_composition_map.py`) donne 13 membres pour `Damage(35)`, dont les DEUX
            # feuilles de dispatch. Le natif ne passe AUCUNE prédiction à cette face-ci.
            trig += triggered_abilities_non_owner_attack_utility(ctx, ctx.uid, ev.target,
                                                                 caster_tile)
            if trig:
                ua += (-1.0 if ev.friendly else 1.0) * ev.probability * trig
            u += ua
            bk.append((ev.target, round(ua, 1)))
        # Fold EFFET (branche +0x388) : base vide -> no-op pour toute ability sans override (additif).
        for ee in self.make_effect_predictions(ctx, caster_tile, target, ability_id) or []:
            u += calculate_utility_from_effect_event(ee, ctx.wt)
        # Fold SOIN (slot +0x368, 2e boucle de `CalculateUtilityFromPredictions`) : base vide, donc
        # no-op pour toute ability sans override. C'est le RANG NATIF du terme lifesteal de
        # `1104 SpiritLeech` (#419-r1-tr14-r5-r2-r1-r1-r3) : il est sommé DANS
        # `CalculateUtilityFromPredictions`, donc DANS l'argument que `CalculateActionUtility` passe
        # à `ShouldExecute` — le port l'ajoutait au RETOUR de `calculate_action_utility`.
        heals = self.make_heal_predictions(ctx, caster_tile, target, ability_id, events)
        if heals:
            u += heal_action_utility(heals)
        return u, bk

    def calculate_action_utility(self, ctx, caster_tile, target, ability_id) -> dict | None:
        """`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility` pour (caster@caster_tile, target) : Σ des events (dégât)
        + Σ effet + `key-0x36(UtilityAttackCase)` + Tile(7)@tuile. Renvoie `{u, u_full, wwn, pred, aoe,
        bk}` (u = dégât+effet ; u_full = u + key-0x36 + tile ; pred = event principal), ou `None` —
        le `Nullable` VIDE natif, c.-à-d. AUCUNE action pour ce (tuile, cible). DEUX portes le
        rendent : la garde de PORT `not events` (le natif, lui, sommerait 0 — cf. `nonattack.py`) et
        le **gate `ShouldExecute`** (slot de vtable +0x328), porté ici à son RANG natif.

        `key-0x36` = `UtilityType.WireweaveNet_FirstAttack` (**55** sur ce build ; 54 sur `gqfc5mff6c`,
        d'où l'écriture `key-0x36` des docs). Terme PAR (tuile, cible), au même rang que `Tile(7)` — il ne
        figure donc PAS dans le `pairUtility` que l'étage UTILITÉ confronte (preuve L3 #64), d'où sa place
        dans `u_full` et pas dans `u`. Identiquement **0** partout où la cible ne porte pas de filet
        `1111` ARMÉ, donc dans toute bataille sans `eldarRanger`. RE : `engine/utilities/wireweave_net.py`
        (⚠ le conjoint d'adjacence natif est DÉGÉNÉRÉ — il compare la tuile du caster à elle-même)."""
        events = self.make_damage_predictions(ctx, caster_tile, target, ability_id)  # list[ProbableDamageEvent]
        if not events:
            return None
        u, bk = self.calculate_utility_from_predictions(ctx, caster_tile, target, ability_id, events)
        # GATE `ShouldExecute` (slot de vtable +0x328), au RANG NATIF : `CalculateActionUtility` fait
        # `u = CalculateCustomUtility` PUIS `u += CalculateUtilityFromPredictions` et passe CETTE
        # somme à `ShouldExecute` — donc AVANT les trois termes positionnels ci-dessous. Le custom
        # n'est pas sommé ici (il l'est par `ComparableAbilityGenerator._action_utility`, où il forme
        # `u_action`) : on le RELIT pour l'argument du gate, ce qui est sans effet de bord — tous les
        # `calculate_custom_utility` du port sont purs. `False` ⇒ `Nullable` vide ⇒ aucune action.
        custom = self.calculate_custom_utility(ctx, caster_tile, target, ability_id)
        if custom is NO_ACTION:
            return None                      # deux des trois sentinelles `BaseUtility` (cf. NO_ACTION)
        if not self.should_execute(ctx, caster_tile, target, ability_id, custom + u):
            return None
        main = events[0]
        wwn = wireweave_net_first_attack_utility(ctx, caster_tile, target)
        # RANG NATIF : `CalculateCasterPositionUtility` (slot +0x348) est le PREMIER des trois
        # termes positionnels, AVANT la clé `0x37` (`wwn`) et `Tile(7)`. Défaut `Fix64(0)` =>
        # no-op exact pour tout playbook qui ne l'override pas (#970).
        cpu = self.calculate_caster_position_utility(ctx, caster_tile, ability_id)
        return {"u": u, "u_full": u + cpu + wwn + tile_utility(ctx, caster_tile), "wwn": wwn,
                "cpu": cpu, "pred": main.composite_fields(), "aoe": events[1:], "bk": bk}


# Registry AbilityType id -> instance de playbook (Comparable ; les NonComparable ont leur propre
# registre dans le package noncomparable/). Port incrémental : les ids absents -> DefaultActiveAbilityPlaybook.
REGISTRY: dict[int, ComparablePlaybook] = {}


def register(pb: ComparablePlaybook) -> ComparablePlaybook:
    REGISTRY[pb.ability_id] = pb
    return pb


def get_playbook(ability_id: int) -> ComparablePlaybook | None:
    return REGISTRY.get(ability_id)
