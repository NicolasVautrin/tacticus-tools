"""Matérialisation OFFLINE des effets actifs — **seed one-shot + évolution** (directive user 2026-06-27).

Pour rester 100% offline, l'engine ne lit PAS `decisionView.effects` à chaque décision : il capte
l'ensemble des effets actifs **une seule fois** (snapshot one-shot au chargement) puis l'**ÉVOLUE
offline** via le cycle de vie de chaque effet. Le cycle de vie est porté en **méthodes sur les classes
d'effet** (`engine.entities.effects` : BaseEffect + sous-classes + factory), pas en table de données :
chaque effet capté devient une instance `BaseEffect` (via `EffectFactory`), et l'évolution interroge
ses méthodes (`is_active`/`removed_after_attack`/`one_shot`/`expired`). cf. playbook-engine.md §17.13.

⚠ La capture one-shot des effets (côté hook) reste à brancher dans `combatSnapshot` (extension à venir) ;
en attendant, le harnais peut seeder depuis un `decisionView` (oracle). L'API ici est indépendante de
la source de seed.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from .effects.base import BaseEffect
from .effects.factory import EffectFactory
# #998 : feuille d'enum (aucune cascade -- `entities/triggered_ability_type.py` n'importe rien
# d'`engine`). Le litteral 0x5b4 est un `TriggeredAbilityType` ; en `EffectType` il nomme
# `AmuletOfTheVoidwyrm_CritDamageReduction`, un AUTRE objet.
from .triggered_ability_type import TriggeredAbilityType
from ..runner.operations import remove_effects as _remove_effects   # FORME B (liaison de MODULE),
#     donc `monkeypatch.setattr` sur le foyer MORD encore. Le cycle annonce au site
#     (`effects_state -> runner.operations.remove_effects -> runner.state -> effects_state`) est
#     REFUTE par la mesure : `import engine.runner.operations` en process frais ne charge PAS ce
#     module. Arete GRATUITE (#485).

#: `(multiplier %, abilityLevel, activeAbilityLevel)` — l'`AbilityState` applique a UN effet.
AbilityStateTriple = tuple

#: `TriggeredAbilityType 0x5b4 = 1460` -- l'ability testee par `ActorHasTriggeredAbility` dans
#: `BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee`.
_TALISMAN_OF_RAGE = int(TriggeredAbilityType.TalismanOfRage)


def melee_defeats_from_units(units) -> int:
    """Compte de base de `IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$
    GetMultiplierBasedOnDefeatedInMelee` = `Count(NormalUnits(UnitsDefeatedByMeleeAttack(AllUnits)))`.

    Flag `UnitComponent.DefeatedByMeleeAttack @0x178` (ecrit par
    `IdunBattle.Operations.KillUnitOperation$$Execute`), publie sous `decisionView.units[].
    defeatedByMelee` ; `isDead` requis en mirror de
    `IdunBattle.Entities.Selectors.UnitsDefeatedByMeleeAttackSelector$$IsValidUnit` (une unite
    RESSUSCITEE ne compte plus). GLOBAL : les DEUX camps, quel que soit le tueur."""
    return sum(1 for u in (units or [])
               if isinstance(u, Mapping) and u.get("defeatedByMelee") and not u.get("alive"))


def melee_defeats_by_killer(units) -> dict:
    """#998 -- le terme `mine` de `IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$
    GetMultiplierBasedOnDefeatedInMelee` :

        Count( Filter( NormalUnits(UnitsDefeatedByMeleeAttack(AllUnits, 0, 1), 0),
                       AreEqual( Killer(<DSLSelectors+0x68>), Owner@DSLSelectors+0x30 ) ) )

    Le `Filter` porte sur les MEMES entites que le compte de base -- donc les memes deux gates
    (`defeatedByMelee` ET mort) -- et n'y ajoute QUE l'egalite du tueur avec l'Owner. On rend donc
    `{killer_id: nombre de ses defaites de MELEE}`, et l'appelant y lit son porteur.

    `killerId` = `UnitComponent.DeathReason` -> `DamageSource$$get_KillerId`, publie sous
    `decisionView.units[].killerId` (`frida/hooks/features/.../projection.ts`). Une unite defaite
    dont le `killerId` est `null` (mort sans tueur imputable) n'entre dans AUCUNE case -- elle reste
    comptee par le terme de base, jamais par le terme `mine`."""
    out: dict = {}
    for u in (units or []):
        if not (isinstance(u, Mapping) and u.get("defeatedByMelee") and not u.get("alive")):
            continue
        k = u.get("killerId")
        if k is None:
            continue
        try:
            k = int(k)
        except (TypeError, ValueError):
            continue
        out[k] = out.get(k, 0) + 1
    return out


def units_with_triggered_ability(units, ability_id: int) -> set:
    """#998 -- mirror de `IdunBattleLogic.Entities.DSLTriggers$$ActorHasTriggeredAbility(unit, id)`,
    evalue en MASSE sur la capture : rend l'ensemble des ids d'unite qui portent `ability_id`.

    `decisionView.units[].triggered` est la collection d'ids de `TriggeredAbilityType` du composant
    `TriggeredAbilityComponent` -- la MEME que lit `playbook/savior_protocols.py`. Elle porte les
    passifs de kit ET la relique (hierarchie 3), ce qui est exactement le point : c'est le seul
    canal ou une relique EQUIPEE devient visible sans relire le BC."""
    aid, out = int(ability_id), set()
    for u in (units or []):
        if not isinstance(u, Mapping):
            continue
        uid = u.get("id")
        if uid is None:
            continue
        if aid in {int(t) for t in (u.get("triggered") or ()) if isinstance(t, int)}:
            out.add(int(uid))
    return out


def seed_battle_counters(eff_state, units) -> "int | None":
    """Pousse le compteur `melee_defeats` sur chaque instance d'effet qui le declare (duck-typing --
    aucun import `loki` ici). **FOYER PARTAGE PAR LES DEUX FACES** : `playbook/scene.py::
    _seed_battle_counters` (DECISION) et `runner/snapshot.py::_load_battle_counters` (COMBAT).

    ⚠ POURQUOI LES DEUX -- et ce que ca a coute quand une seule le faisait (#953). La face COMBAT
    ne posait RIEN : sur un etat RECHARGE, `BlessingsOfKhorneModifiersEffect.melee_defeats` restait
    `None`, donc `N = 0`, donc le `+3 % x N` de TOUT le degat sortant d'un World Eater DISPARAISSAIT
    apres le premier kill de melee -- silencieusement, et sans qu'aucun test ne le voie (le regime
    exige un kill de melee AVANT la mesure). MESURE (`probe_953_954`, bras `sk_stun`, `worldJakhal`
    apres UN kill) : natif `[1210, 1204, 503]` = 2917, port `[791, 607, 1089]` = 2487 ; en forcant
    `melee_defeats = 1` le port rend **exactement** `[1210, 1204, 503]`. L'ecart n'est PAS un facteur
    de 3 % : le bonus deplace `min`/`max`, donc chaque tirage tombe sur un autre entier -- c'est ce
    qui le rendait illisible comme un simple facteur.

    ## #998 -- DEUX compteurs de plus, et ils sont PAR PORTEUR

    Le multiplicateur natif porte un second terme, conditionne a
    `ActorHasTriggeredAbility(Owner@+0x30, 0x5b4 = TalismanOfRage)` : le nombre de defaites de MELEE
    imputables AU PORTEUR. Contrairement a `melee_defeats`, qui est GLOBAL, ces deux-la dependent de
    l'unite qui porte l'effet -- d'ou l'iteration sur `bu.items()` (l'uid etait deja la, seulement
    ignore). Toujours en duck-typing : **aucun import `loki` ici**.

    Rend le compte pose, ou `None` si l'etat d'effets est absent (rien a seeder)."""
    bu = getattr(eff_state, "by_unit", None) if eff_state is not None else None
    if not bu:
        return None
    n = melee_defeats_from_units(units)
    # Les deux tables du terme `mine` ne sont calculees QU'UNE FOIS pour toute la passe.
    by_killer = melee_defeats_by_killer(units)
    porteurs = units_with_triggered_ability(units, _TALISMAN_OF_RAGE)
    for uid, effs in bu.items():
        uid = int(uid)
        for e in effs:
            if hasattr(e, "melee_defeats"):
                e.melee_defeats = n
            if hasattr(e, "melee_defeats_by_owner"):
                e.melee_defeats_by_owner = by_killer.get(uid, 0)
            if hasattr(e, "owner_has_talisman_of_rage"):
                e.owner_has_talisman_of_rage = uid in porteurs
    return n


def baked_ability_state(captured: Mapping, carrier_id: int,
                        carrier_state: tuple,
                        ability_state_by_unit: Mapping | None) -> tuple:
    """`(multiplier, abilityLevel, activeAbilityLevel)` d'UN effet capte -- celui de sa **SOURCE**,
    pas celui de son PORTEUR. Foyer UNIQUE : `EffectsState.seed` et
    `runner/snapshot.py::_load_stats_and_effects` passent tous les deux par ici.

    MIRROR de la **POSE**, pas de la lecture -- le natif *bake*.
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder(id, abilityState)`
    construit l'entite-effet (`IdunBattle.Entities.Blueprints$$Effect`), prend son `EffectComponent`
    et y **COPIE les 0x24 octets** de l'`AbilityStateReference` recue, a `+0x18`..`+0x38`. Cette
    reference vient du noeud DSL `AddEffect(<type>, <abilityStateReference>, source, targets, turns)`,
    ou elle est evaluee sur l'ability QUI POSE
    (`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$get_AbilityStateReference` ->
    `IdunBattleLogic.Entities.DSLSelectors$$AbilityState(entities, owner, abilityType)`, owner =
    `AbilityEntities.Owner`) -- donc sur le CASTER. A la lecture,
    `IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` /
    `IdunBattle.DSL.AbilityStateFromEffectSelector$$Select` relisent ce MEME `EffectComponent+0x18`
    et rien d'autre : **l'effet ne consulte JAMAIS son porteur**.

    Porteur == source uniquement pour un owner-effect. Des que le behaviour pose sur AUTRUI
    (`SagaOfTheWarriorBorn_OtherSpaceWolves` 1224 :
    `targets = UnitsFromFaction(Friends(Owner, <pool>, OnlyAlive) - Owner, ...)`), les deux different
    PAR CONSTRUCTION. `buildNormalizedBC` MASQUE la moitie de l'ecart -- il ecrit le MEME
    `targetAbilityLevel` dans `ActiveAbilityLevel` et `PassiveAbilityLevel` de toutes les unites
    (`normalize-bc/json-build.ts`) -- mais PAS le multiplicateur de rarete, qui reste per-unite.

    `captured["source"]` = `EffectComponent.SourceUnitId @+0x10`, ecrit par
    `IdunBattle.Operations.AddEffectOperation$$AddNewEffect` depuis le meme `source` que le noeud DSL.
    C'est le seul canal de la capture qui designe l'entite-poseuse.

    REPLI = le PORTEUR (`carrier_state`), **jamais un neutre** : source absente de la capture
    (`None`), non entiere, ou non chargee (posee par une entite hors snapshot). C'est le
    comportement anterieur, conserve a l'identique -- le changement ne mord QUE quand la source est
    RESOLVABLE et DIFFERENTE du porteur. (Une TUILE n'a, elle, aucun porteur a qui se replier : sa
    voie est `runner/snapshot.py::_source_ability_state`, dont le repli est neutre.)"""
    if ability_state_by_unit is None or not isinstance(captured, Mapping):
        return carrier_state
    src = captured.get("source")
    if src is None:
        return carrier_state
    try:
        src = int(src)
    except (TypeError, ValueError):
        return carrier_state
    if src == int(carrier_id):
        return carrier_state
    st = ability_state_by_unit.get(src)
    if st is None:
        return carrier_state
    return (int(st[0] or 100), st[1], st[2])


@dataclass
class EffectsState:
    """État matérialisé des effets actifs (par unité) = instances `BaseEffect`, seedées une fois puis
    évoluées offline. Source de seed = capture one-shot `{unit_id: [{name, effectType, level, remaining,
    source}]}`. `active_effects(uid, state)` = ce que l'engine consomme à chaque décision (au lieu d'une
    relecture live)."""
    by_unit: dict[int, list[BaseEffect]] = field(default_factory=dict)

    @classmethod
    def seed(cls, effects_by_unit: Mapping | None, mult_by_unit: Mapping | None = None,
             ability_level_by_unit: Mapping | None = None,
             ability_state_by_unit: Mapping | None = None) -> "EffectsState":
        """`mult_by_unit` = {unit_id: AbilityVariablesMultiplierPercentage} (BC, défaut 100) ;
        `ability_level_by_unit` = {unit_id: niveau d'ability source} (indexe les `variables[level]`,
        ≠ stack level capté) — tous deux propagés aux effets matérialisés (§17.21). Ces deux tables
        sont clées par PORTEUR : elles décrivent le REPLI.

        `ability_state_by_unit` = {unit_id: (multiplier, abilityLevel, activeAbilityLevel)} — l'état
        d'ability de CHAQUE entité, consulté **par la SOURCE de l'effet** (`captured["source"]`).
        C'est le mirror du bake natif : cf. `baked_ability_state`. Absent (défaut) → comportement
        strictement antérieur, l'état du PORTEUR pour tous ses effets.

        LE TROISIÈME MEMBRE DU TRIPLE — `activeAbilityLevel` — EST LU, Y COMPRIS EN REPLI
        (case-366-r1). `GetAbilityState(effet)` résout l'`AbilityState` de l'ability SOURCE, et cette
        source est une ACTIVE pour toute une famille d'effets (`<Effect>$$.ctor` écrit
        l'`ActiveAbilityType` puis la surcharge `IdunBattle.Core.AbilityOrEffect$$op_Implicit` qui
        appelle `set_ActiveAbility`). **19 classes d'effet** écrivent la cascade
        `active_ability_level -> ability_level -> level`, et elle retombait TOUJOURS sur le passif :
        le repli porteur forçait `None`. L'écart est INVISIBLE en runner normalisé
        (`buildNormalizedBC` met les deux niveaux à `targetAbilityLevel`) — mesuré en les dissociant
        (`--unit-stat "eldarRanger:ActiveAbilityLevel=30"`, passif 50), le natif retire
        `dmgReduction[30] x 1.8 = 716` là où le port retirait `dmgReduction[50] x 1.8 = 2992`.
        Le repli tire donc le triple d'`ability_state_by_unit[porteur]` quand il y est ; à défaut
        (appelant qui ne passe pas la table) il reste `(mult, abilityLevel, None)`, comportement
        strictement antérieur."""
        bu: dict[int, list[BaseEffect]] = {}
        for uid, effs in (effects_by_unit or {}).items():
            uid = int(uid)
            # REPLI = le porteur. `ability_state_by_unit` porte DÉJÀ son triple complet (même
            # lecture que pour une source) : on s'en sert, sinon on retombe sur les deux tables
            # historiques (et `activeAbilityLevel` inconnu -> None, jamais un niveau deviné).
            carrier = (ability_state_by_unit or {}).get(uid)
            if carrier is None:
                carrier = (int((mult_by_unit or {}).get(uid, 100) or 100),
                           (ability_level_by_unit or {}).get(uid), None)
            out: list[BaseEffect] = []
            for c in (effs or []):
                if not (isinstance(c, Mapping) and c.get("name")):
                    continue
                mult, albl, actl = baked_ability_state(c, uid, carrier, ability_state_by_unit)
                out.append(EffectFactory.create(c, mult, albl, actl))
            bu[uid] = out
        return cls(by_unit=bu)

    def active_effects(self, unit_id: int, unit_state: Mapping | None = None) -> list[BaseEffect]:
        """Effets ACTIFS de l'unité = non consommés, non expirés, flag `EffectComponent.IsActive @+0x5c`
        (`e.active`) posé, ET `is_active(state)` (la `CreateActiveCondition`) vraie. Renvoie des
        instances `BaseEffect` (consommées par `build_attacker_modifiers_from_effects` / `hits_bonus_from_effects`).

        Les DEUX conjoints sont natifs et distincts : le FLAG est ce qu'ecrivent les feuilles DSL
        `ActivateEffect`/`DeactivateEffect` (et ce que lit `EntityExtensions$$IsOwnerOfEffect` en mode
        `activeOnly`) ; la CONDITION est reevaluee a la lecture (mirror de `CreateActiveCondition`, cf.
        `runner/operations/refresh_effects.py`). Un effet desactive par une feuille ne contribue plus —
        exactement comme il disparait de `decisionView.units[].effects` cote live.

        EXCEPTION NOMMEE (case-322) : `BaseEffect.active_condition_ported`. Le flag capte decrit
        l'etat REEL au moment de la capture ; pour un effet dont la `CreateActiveCondition` porte sur
        l'etat SIMULE (tuile candidate), le natif le RECALCULE avant d'evaluer
        (`RefreshEffectsOperation$$RefreshEffect` sur `RefreshTrigger.Simulation`), donc le flag
        capte n'est PAS la reponse. Pour ces classes SEULES, la condition portee fait foi. Blast
        radius nul ailleurs : le defaut de l'attribut est `False`."""
        return [e for e in self.by_unit.get(int(unit_id), [])
                if not e.consumed and not e.expired
                and (e.active or getattr(e, "active_condition_ported", False))
                and e.is_active(unit_state)]

    def has_effect(self, unit_id: int, effect_type: int | None = None,
                   name: str | None = None) -> bool:
        """L'unité porte-t-elle DÉJÀ un effet (non consommé) de ce type/nom ? Gate « déjà-présent »
        de la matérialisation (cf. `AddEffectOperation` : query 0x28 sur la def vs cible, + base de
        `UpdateExistingEffect`). Match par `effect_type` si fourni, sinon par `name`."""
        for e in self.by_unit.get(int(unit_id), []):
            if e.consumed:
                continue
            if effect_type is not None and e.effect_type == effect_type:
                return True
            if name is not None and e.name == name:
                return True
        return False

    def add_effect(self, unit_id: int, effect: BaseEffect) -> BaseEffect:
        """Enregistre un effet matérialisé sur l'unité (`AddNewEffect` : ajout à la liste portée de la
        cible). `effect.target` doit être l'unité porteuse. Mirror de l'ajout à
        `EffectsOwnedComponent` côté entité-effet (la liste structurée ici)."""
        self.by_unit.setdefault(int(unit_id), []).append(effect)
        return effect

    def on_attack(self, unit_id: int) -> None:
        """L'unité attaque → consomme les effets one-shot stricts."""
        for e in self.by_unit.get(int(unit_id), []):
            if e.one_shot:
                e.consumed = True

    def on_turn_end(self, unit_id: int, attacked: bool, state=None) -> list:
        """Fin de tour de l'ENTITÉ PORTEUSE (unité **ou tuile** — cf. ci-dessous) : retrait des effets
        « removed-after-attack » si elle a attaqué, puis décrément des timers, puis RETRAIT des instances
        arrivées à 0, puis CASCADE composite : un effet PARENT disparu (expiré/consommé) retire ses
        ENFANTS (lien `parent_type`).

        Renvoie la liste des `effect_type` retirés PAR ÉCHÉANCE (trace ; la cascade et le
        `removed_after_attack` n'y sont pas).

        DOMAINE — `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` n'itère PAS les unités : il
        énumère **TOUTES les entités-EFFET du state** (la MÊME collection générique que consomme
        `IdunBattle.Entities.EntityExtensions$$GetEffectsBySourceUnit`, et dont il lit directement
        l'`EffectComponent`). Il n'y a donc AUCUNE distinction porteur-unité / porteur-tuile dans le tick
        de durée. L'appelant (`EndTurnOperation.execute`, `runner/operations/turnflow.py`) balaye pour
        cette raison TOUTES les clés de `by_unit`, ids d'entité-tuile compris (#102).

        DÉCRÉMENT — `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` =
        `if (0 < Duration@+0x64) Duration -= 1` : le compteur est **CLAMPÉ à 0**, il ne descend jamais
        sous zéro. Le gate d'entrée du natif est `!Removed@+0x5f && HasTurns@+0x5d` — une instance déjà
        retirée ne tick plus, une instance permanente (`HasTurns` faux, ici `remaining_turns is None`)
        non plus.

        RETRAIT — `IdunBattle.Entities.Components.EffectComponent$$ShouldBeRemoved` =
        `HasTurns && Duration == 0`. C'est le prédicat que teste
        `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` (enfilée par la fin de
        `EndTurnOperation$$RefreshEffects`) pour prendre la branche `DeactivateEffect` + retrait de
        l'entité-effet : à 0, l'effet **N'EXISTE PLUS**, il ne peut donc plus ni être vu par un gate de
        présence, ni déclencher ses triggers. Offline, la marque de retrait est `consumed` — la SEULE
        que TOUS les lecteurs honorent (`has_effect`, `collect_effect_triggers`, `active_effects`) ;
        `expired` n'est lu que par `active_effects`/`refresh_stat_modifier_effects`, d'où le trou
        MESURÉ (résidu O3) : un effet à timer arrivé à échéance restait visible de `has_effect` et
        continuait d'être collecté comme effet-trigger — pour une tuile, dont c'est le SEUL chemin de
        lecture, le feu (`FireEffect` 5) brûlait pour toujours et re-tickait son DoT à chaque tour.

        Mirror du cycle de vie natif d'un effet composite (ex. Stunned 1162) : à l'expiration du parent,
        `<Effect>.RevertInternal` (IdunBattle.Entities.Effects.Loki.StunnedEffect$$RevertInternal) fait `RemoveEffect` de ses enfants permanents (1166/1167)
        et l'enfant same-turns (1165) expire sur son propre timer synchronisé — NET : toute la famille
        part ensemble. La cascade `parent_type` reproduit ce NET (et couvre le retrait anticipé du parent).

        ## `state` — LE RETRAIT PASSE PAR LE FOYER, IL N'EST PAS UNE MARQUE (#936-r1)

        Le décrément et le retrait sont DEUX Operations natives distinctes, et c'est LU :
        `IdunBattle.Operations.EndTurnOperation$$RefreshEffects` n'appelle que
        `IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` (plus ses events de flux) ;
        c'est l'appel du slot 0x2f qui SUIT sa boucle (`RefreshEffectOptions(trigger =
        RefreshEffectTrigger.TurnChanged)`) qui atteint
        `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect`, lequel, sur
        `EffectComponent$$ShouldBeRemoved`, fait `RefreshEffectsOperation$$DeactivateEffect` PUIS
        enfile une `System.Action` différée. Cette action est
        `RefreshEffectsOperation.<>c__DisplayClass9_0$$<RemoveEffect>b__0`, dont le corps ENTIER est
        le **slot 0x11** de `Core.Services.OperationProcessor` sur l'entité-effet capturée — donc
        `IdunBattle.Operations.RemoveEffectOperation$$Execute`, le MÊME corps qu'un retrait explicite.
        ⇒ une expiration par TIMER publie `On(0x3f = PreEffectRemoved)`, `On(0x40 = EffectRemoved)`
        et, sous son gate de type, `On(0x3b = UnitBecameTargetable)`.

        Le port posait ici `consumed = True` en direct : les trois vecteurs n'étaient émis NULLE PART
        sur cette voie, et le NOM de l'effet restait collé à l'`EffectsOwnedComponent` du porteur.
        Quand `state` est fourni, la branche « échéance » route par
        `runner/operations/remove_effects.py::remove_effect_instance` — le foyer unique du corps natif.

        REPLI `state is None` = `consumed = True`, le comportement strictement antérieur. Il n'est pas
        une alternative : c'est le régime d'un `EffectsState` SANS `OperationProcessor` (la face
        DÉCISION n'a pas de `runner.State`, et rien n'y appelle ce tick). Le chemin de production
        (`runner/operations/turnflow.py`, `EndTurnOperation`) passe TOUJOURS `state`.

        ⚠ ÉCART D'ORDRE NOMMÉ : le natif reverte via `DeactivateEffect` AVANT d'enfiler l'action, donc
        avant `On(0x3f)` ; `remove_effect_instance` publie `On(0x3f)` puis reverte (c'est l'ordre du
        corps de `RemoveEffectOperation$$Execute`, où le revert est conditionné par `IsActive`, déjà
        remis à 0 par le `DeactivateEffect` qui précède). Inobservable tant qu'aucun consommateur porté
        n'écoute `On(0x3f)` — il n'y en a aucun.

        ⚠ Les ENFANTS d'un composite expiré passent EUX AUSSI par le foyer depuis #936-r1-r2 : la
        cascade `parent_type` ci-dessous route par `remove_effect_instance` dès que `state` est
        fourni. Elle posait `consumed` en direct, ce qui sautait non seulement les trois vecteurs
        mais aussi `unregister_name` — donc laissait le NOM de l'enfant collé à
        l'`EffectsOwnedComponent` du porteur, sur le canal que LIT la couche décision."""
        lst = self.by_unit.get(int(unit_id), [])
        due: list = []
        for e in lst:
            if e.removed_after_attack and attacked:
                e.consumed = True
            if e.remaining_turns is None or e.consumed:
                continue                       # gate natif `!Removed && HasTurns`
            if e.remaining_turns > 0:          # `RemoveOneTurn` : décrément CLAMPÉ à 0
                e.remaining_turns -= 1
            if e.remaining_turns <= 0:         # `ShouldBeRemoved` -> DeactivateEffect + RemoveEffect
                due.append(e)
        removed: list = []
        if due:
            if state is None:
                for e in due:
                    e.consumed = True          # REPLI (cf. docstring) : la marque, sans le foyer
                    removed.append(e.effect_type)
            else:
                for e in due:
                    et = e.effect_type
                    if _remove_effects.remove_effect_instance(state, int(unit_id), e):
                        removed.append(et)
        # cascade : tant qu'un parent vient de disparaître, retirer ses enfants (point fixe — gère un
        # éventuel chaînage parent->enfant->petit-enfant ; aujourd'hui 1 niveau pour Stunned).
        #
        # #936-r1-r2 — ELLE PASSE PAR LE FOYER, elle aussi. Le natif retire les enfants par
        # `IdunBattle.Operations.RemoveEffectOperation$$RemoveSubEffects`, dont le corps est un appel
        # au slot 0x11 sur CHAQUE enfant — donc le MÊME `RemoveEffectOperation$$Execute` que le
        # parent, récursivement. Poser `consumed` en direct sautait tout ce corps.
        #
        # ⚠ CE N'EST PAS QUE LES TROIS VECTEURS, et la fiche du résidu l'annonçait « INOBSERVABLE » :
        # `remove_effect_instance` appelle aussi `unregister_name`, et les enfants SONT inscrits à
        # l'`EffectsOwnedComponent` à la pose (`AddEffectOperation._spawn_sub_effects` ->
        # `_register_name`, une ligne par enfant). Un enfant seulement marqué gardait donc son NOM
        # COLLÉ sur le porteur — exactement la fuite que #936-r1 a corrigée pour le PARENT, et ce
        # canal-là EST lu par la couche décision (`ai/state_bridge.py`, `playbook/scene.py`).
        #
        # POURQUOI CETTE CASCADE SUBSISTE À CÔTÉ de `_remove_sub_effects` (appelé par le foyer sur le
        # parent) : ce dernier dérive les enfants de `parent.sub_effects_on_apply()` et sort tout de
        # suite si le parent n'en déclare AUCUN. Les liens reconstruits à l'hydratation
        # (`snapshot._load_effect_parent_links`) n'ont pas de specs — la cascade est leur seul
        # chemin. Les deux domaines se recouvrent partiellement ; l'idempotence de
        # `remove_effect_instance` (gates `+0x5f`/`+0x5e` -> `eff.consumed`) rend le recouvrement
        # inoffensif : le second passage est un no-op qui rend `False`.
        #
        # REPLI `state is None` = `consumed = True`, le comportement strictement antérieur — même
        # raison que la branche « échéance » ci-dessus (un `EffectsState` sans `OperationProcessor`).
        while True:
            gone = {e.effect_type for e in lst
                    if (e.consumed or e.expired) and e.effect_type is not None}
            changed = False
            # COPIE de la liste : `remove_effect_instance` publie des vecteurs, et un consommateur
            # peut poser un effet -> muter `lst` pendant l'itération (mirror du `new List<int>(...)`
            # que `RemoveSubEffects` fait pour exactement cette raison).
            for e in list(lst):
                if e.consumed or e.parent_type not in gone:
                    continue
                if state is None:
                    e.consumed = True
                    changed = True
                elif _remove_effects.remove_effect_instance(state, int(unit_id), e):
                    changed = True
                else:
                    # Le foyer a REFUSÉ (gate d'idempotence). Sans cette marque l'enfant resterait
                    # non consommé et serait re-tenté à chaque tour de boucle -> point fixe jamais
                    # atteint. On ne relâche pas la garde, on la termine.
                    e.consumed = True
                    changed = True
            if not changed:
                break
        return removed
