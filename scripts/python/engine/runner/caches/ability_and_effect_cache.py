"""`IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache` -- le cache qui CHOISIT ce qui
s'active, et dans QUEL ORDRE (#477-r21-r2 volet B).

C'est la structure que `IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal` parcourt :

    IdunBattle.Core.AOperation$$get_AbilityAndEffectCache(this)
      .<slot 3>(trigger)                      -- resolu : `$$GetActiveTriggeredAbilitiesAndEffects`
    foreach (item in cette liste)
        EvaluateAbilityOrEffectTrigger(trigger, item, createAbilityEntities, onlyNonAtomic)

⚠ CE N'EST PAS UNE FACE STREAM. Le cache vit dans l'ETAT : il n'emet aucune ligne, il rend un
ENSEMBLE ORDONNE. Les quatre crans #477-r18..r22 comparaient deux textes ; ici on confronte une
SEQUENCE (`probe_477r21r2b_activation_cache.py`).

LA STRUCTURE, lue au ctor (`AbilityAndEffectCache$$.ctor(effects, abilities)`) et confirmee par
`frida/classes.tsv` (`AbilityAndEffectCache` = 96 octets = champs `+0x10`..`+0x58`) :

    +0x10 IEffectsDatabase    effects        -- resolution `EffectType   -> IEffect`   (slot 0)
    +0x18 IAbilitiesDatabase  abilities      -- resolution `configId     -> List<ITriggeredAbility>`
    +0x20 Dictionary<EventTriggerType, List<SortedTriggered>>         <- LE parcours d'ExecuteInternal
    +0x28 Dictionary<EventTriggerType, List<SortedTriggeredAbility>>  <- volet SIMULATION
    +0x30 List<SortedEffect>                 -- `GetEffects`
    +0x38 List<SortedEffect>                 -- `GetRefreshingEffects`
    +0x40 List<SortedEffect>                 -- `GetEffectsWithBonuses`
    +0x48 List<SortedEffect>                 -- `GetRefreshingInSimulatedEffects`
    +0x50 List<SortedTriggeredAbility>       -- `GetTriggeredAbilityForNonOwnerPlaybook`

⚠ L'APPARIEMENT OFFSET -> GETTER EST LU UN PAR UN, ET IL N'EST PAS CELUI QU'ON DEVINE :
`GetRefreshingEffects` rend `+0x38` et `GetEffectsWithBonuses` rend `+0x40` -- soit l'INVERSE de
l'ordre dans lequel `AddEffect` les alimente (`+0x38` sous la garde `HasTurns`, `+0x40` sous le
slot 0x2e). Deduire l'un de l'autre intervertit deux listes que rien ne distingue ensuite.

LES DEUX DICTIONNAIRES SONT PRE-PEUPLES, ET C'EST CE QUI REND `get_Item` TOTAL. Le ctor fait
`foreach (t in Enum.GetValues<EventTriggerType>()) { d20.Add(t, new List<>()); d28.Add(t, new
List<>()); }` -- il n'y a donc jamais de `KeyNotFoundException`, et une cle absente cote port
serait une INFIDELITE (le natif rendrait une liste vide, pas une erreur).

L'ORDRE -- `AddSorted<T>` est le SEUL point qui l'etablit :

    static void AddSorted<T>(T value, List<T> list) where T : SortedTriggered
        int idx = list.FindIndex(x => x.CompareTo(value) == -1);
        if (idx < 0) idx = list.Count;
        list.Insert(idx, value);

et `IdunBattleLogic.Core.Services.Caches.SortedTriggered$$CompareTo` :

    public int CompareTo(SortedTriggered other)
        if (other == null) return 1;
        int o = other.Priority;              // slot 0x188 de la vtable -- `get_Priority` VIRTUEL
        int m = this.Priority;
        return m.CompareTo(o);

=> la liste est maintenue en ordre DECROISSANT de `Priority`, et l'insertion est STABLE : on
s'arrete au premier element STRICTEMENT inferieur, donc on passe APRES tous les egaux. A
priorites egales -- le regime mesure sur le corpus temoin -- `AddSorted` degenere exactement en
`append`, et l'ordre observable est celui des INSERTIONS.

⚠ LA VALEUR DE `Priority` PAR PORTEUR N'EST PAS UNE DONNEE QUE CE MODULE POSSEDE, et le dire est
le point. `SortedTriggeredAbility.Priority` delegue au slot 7 de l'ability, `SortedEffect.Priority`
au slot 9 de l'effet ; ces getters sont des corps `mov eax,<imm32> ; ret` que IL2CPP DEDUPLIQUE --
ils n'ont qu'un proprietaire arbitraire dans `frida/methods.tsv`, et Ghidra n'en nomme aucun (meme
faux negatif que #170, ou 22 surcharges reelles n'occupaient que 3 lignes). Le port expose donc
`priority` comme une ENTREE (defaut `AbilityPriority.Normal`), jamais comme une valeur devinee :
un porteur dont le tier serait faux ordonnerait FAUX, en silence.

QUATRE PEUPLEURS, tous mirrors 1:1 (details dans chaque methode) :

    AddEntity(entity)      -- aiguillage sur le TYPE de l'entite (effet -> AddEffect, sinon
                              TryGetComponent<TriggeredAbilityComponent> -> AddAbility)
    AddAbility(entity, checkIfAlreadyExist, abilities)
    AddEffect(effectEntity, effectComponent)
    RefreshEntity(entity)  -- le SEUL appelant avec `checkIfAlreadyExist: true`

et trois retraits : `RemoveEntity`, `RemoveTriggered`, plus le volet simulation
`AddSimulatedTriggeredOrEffect`.
"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Sequence

from ...dsl.event_trigger_type import EventTriggerType
from ...entities.ability_priority import AbilityPriority


# --------------------------------------------------------------------------- les trois valeurs
class SortedTriggered:
    """`IdunBattleLogic.Core.Services.Caches.SortedTriggered` -- 16 octets, donc AUCUN champ
    propre (`frida/classes.tsv` : taille 16 = le seul header d'objet). C'est une base abstraite
    dont tout le contenu vit dans les deux sous-classes ; elle ne porte que `CompareTo` et le
    `get_Priority` VIRTUEL (slot de vtable `+0x188`) que celui-ci appelle."""

    __slots__ = ()

    #: `SortedTriggered$$get_Priority` -- virtuel. Le defaut est `AbilityPriority.Normal`, le
    #: membre `0` de l'enum ; les sous-classes le DELEGUENT a leur porteur.
    def get_priority(self) -> int:
        return int(AbilityPriority.Normal)

    def compare_to(self, other: Optional["SortedTriggered"]) -> int:
        """`IdunBattleLogic.Core.Services.Caches.SortedTriggered$$CompareTo`.

        ⚠ L'ORDRE DES DEUX LECTURES EST CELUI DU DECOMPILE, et il compte pour la lecture, pas
        pour le resultat : le natif lit `other.Priority` PUIS `this.Priority`, et rend
        `this.Priority.CompareTo(other.Priority)`. `other == null` rend **1**, jamais 0 --
        un `null` est donc toujours « plus petit », ce qui le laisserait en queue."""
        if other is None:
            return 1
        o = int(other.get_priority())
        m = int(self.get_priority())
        return (m > o) - (m < o)          # System.Int32.CompareTo


class SortedEffect(SortedTriggered):
    """`IdunBattleLogic.Core.Services.Caches.SortedEffect` -- 40 octets = trois champs.

        +0x10 IEntity          entity           (l'entite ECS de l'EFFET, pas son porteur)
        +0x18 EffectComponent  effect_component
        +0x20 IEffect          effect

    `ToString()` rend `((EffectType)effectComponent.<+0x58>).ToString()` -- ce qui NOMME `+0x58`
    comme le champ `EffectType` du composant, deja lu par #477-r21.
    `get_Priority()` rend le slot 9 de `IEffect`."""

    __slots__ = ("entity", "effect_component", "effect")

    def __init__(self, entity, effect_component=None, effect=None):
        self.entity = entity
        self.effect_component = effect_component
        self.effect = effect

    def get_priority(self) -> int:
        """`SortedEffect$$get_Priority` = `this.effect.<slot 9>` -- LEVE si l'effet est nul
        (`FUN_1801f51f0` = le `NullReferenceException` d'IL2CPP). Le port lit un attribut
        `priority` sur l'objet d'effet et retombe sur `Normal` quand le porteur n'en declare
        pas : c'est l'ENTREE manquante nommee dans l'entete du module, pas une valeur devinee."""
        if self.effect is None:
            raise ValueError("SortedEffect.get_priority : effect nul "
                             "(le natif y leve NullReference)")
        return int(getattr(self.effect, "priority", AbilityPriority.Normal))

    def __repr__(self) -> str:                      # `SortedEffect$$ToString`
        et = getattr(self.effect_component, "effect_type", None)
        return "SortedEffect(%s)" % (et if et is not None else "?")


class SortedTriggeredAbility(SortedTriggered):
    """`IdunBattleLogic.Core.Services.Caches.SortedTriggeredAbility` -- 48 octets = quatre champs
    (le `TriggeredAbilityConfigId` en occupe deux, il fait 16 octets) :

        +0x10 IEntity                     entity      (l'UNITE porteuse)
        +0x18 TriggeredAbilityConfigId    config_id   -- `+0x18` = son premier mot = l'ORDER,
                                                         c'est le `int` que `RemoveTriggered`
                                                         compare a son `triggeredAbilityType`
        +0x28 ITriggeredAbility           ability

    `ToString()` rend `IdunShared.TriggeredAbilityConfigId$$GetStringValue(&this.<+0x18>)`.
    `get_Priority()` rend le slot 7 de `ITriggeredAbility`."""

    __slots__ = ("entity", "order", "config_id", "ability")

    def __init__(self, entity, order: int, ability=None, config_id=None):
        self.entity = entity
        #: `+0x18` lu en `int` -- ce que `<RemoveTriggered>b__0` et `<AddAbility>b__0` comparent.
        self.order = int(order)
        self.config_id = config_id
        self.ability = ability

    def get_priority(self) -> int:
        """`SortedTriggeredAbility$$get_Priority` = `this.ability.<slot 7>` -- LEVE si l'ability
        est nulle. Meme entree manquante que pour `SortedEffect` (cf. entete du module)."""
        if self.ability is None:
            raise ValueError("SortedTriggeredAbility.get_priority : ability nulle "
                             "(le natif y leve NullReference)")
        return int(getattr(self.ability, "priority", AbilityPriority.Normal))

    def __repr__(self) -> str:                      # `SortedTriggeredAbility$$ToString`
        return "SortedTriggeredAbility(%s@%s)" % (self.order, self.entity)


# --------------------------------------------------------------------------- l'insertion triee
def add_sorted(value: SortedTriggered, lst: List[SortedTriggered]) -> None:
    """`IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache$$AddSortedu003Cobjectu003E`.

        int idx = list.FindIndex(x => x.CompareTo(value) == -1);
        if (idx < 0) idx = list.Count;
        list.Insert(idx, value);

    ⚠ LE SENS DE LA COMPARAISON EST `x.CompareTo(value)`, PAS `value.CompareTo(x)`. C'est le
    receveur qui est l'element DEJA EN PLACE : on cherche le premier element dont la priorite est
    STRICTEMENT INFERIEURE a celle de l'arrivant, et on s'insere AVANT lui. Inverser le sens
    rendrait un ordre croissant, et -- a priorites egales -- une insertion en TETE au lieu de la
    queue : deux fautes qu'un corpus a priorites uniformes ne distingue pas l'une de l'autre mais
    qui changent toutes deux la sequence.

    ⚠ `FindIndex` rend `-1` sur liste VIDE comme sur « aucun element inferieur » ; les deux cas
    retombent donc sur `idx = Count`, soit un `append`. Le port garde le `-1` explicite plutot
    qu'un `else` : c'est la forme du natif, et elle rend le degenere lisible."""
    idx = -1
    for i, x in enumerate(lst):
        if x.compare_to(value) == -1:
            idx = i
            break
    if idx < 0:
        idx = len(lst)
    lst.insert(idx, value)


# --------------------------------------------------------------------------- le cache
class AbilityAndEffectCache:
    """Mirror 1:1 d'`IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache`.

    Les deux dependances du ctor sont des RESOLVEURS, fournis par l'appelant :

        effects_database(effect_type)  -> l'objet `IEffect`         (`IEffectsDatabase` slot 0)
        abilities_database(config_id)  -> `list[ITriggeredAbility]` (`IAbilitiesDatabase` slot 2)

    Le port les prend en `Callable` plutot qu'en objets : cote natif ce sont deux interfaces dont
    seul le slot appele ici compte, et un objet factice cacherait cette mesure du besoin.
    `None` = resolveur absent -- les peupleurs qui en dependent le DISENT en levant, ils ne
    degradent pas en no-op silencieux (une entree jamais inscrite est exactement le mode de panne
    que ce cache existe pour rendre visible)."""

    __slots__ = ("effects_database", "abilities_database", "active", "simulated", "effects",
                 "refreshing_effects", "effects_with_bonuses", "refreshing_in_simulated_effects",
                 "triggered_ability_for_non_owner_playbook")

    def __init__(self, effects_database: Optional[Callable] = None,
                 abilities_database: Optional[Callable] = None) -> None:
        self.effects_database = effects_database        # +0x10
        self.abilities_database = abilities_database    # +0x18
        # LE PRE-PEUPLEMENT DU CTOR : une entree par valeur de l'enum, LISTE VIDE. Le natif fait
        # `Enum.GetValues(typeof(EventTriggerType))` -- le port itere le mirror, qui EST ce jeu de
        # valeurs. C'est ce qui rend `get_active_triggered_abilities_and_effects` TOTAL.
        self.active: Dict[int, List[SortedTriggered]] = {                        # +0x20
            int(t): [] for t in EventTriggerType}
        self.simulated: Dict[int, List[SortedTriggeredAbility]] = {              # +0x28
            int(t): [] for t in EventTriggerType}
        self.effects: List[SortedEffect] = []                                    # +0x30
        self.refreshing_effects: List[SortedEffect] = []                         # +0x38
        self.effects_with_bonuses: List[SortedEffect] = []                       # +0x40
        self.refreshing_in_simulated_effects: List[SortedEffect] = []            # +0x48
        self.triggered_ability_for_non_owner_playbook: List[SortedTriggeredAbility] = []   # +0x50

    # ----------------------------------------------------------------- les huit accesseurs
    def get_active_triggered_abilities_and_effects(self, trigger: int) -> List[SortedTriggered]:
        """`$$GetActiveTriggeredAbilitiesAndEffects(trigger)` -- LE slot 3, celui
        qu'`EvaluateTriggerOperation$$ExecuteInternal` parcourt.

        Le natif fait `ListPool<SortedTriggered>.GetDisposable(this.active[trigger])`, c'est-a-dire
        une COPIE dans une liste empruntee au pool, jetee en fin de `foreach`. Cette copie n'est
        pas cosmetique : elle rend le parcours INSENSIBLE aux mutations que les triggers
        provoquent en s'executant (un effet ajoute pendant l'evaluation n'entre pas dans CE
        parcours). Le port rend donc `list(...)`, jamais la liste vive."""
        return list(self.active[int(trigger)])

    def get_simulated_active_triggered_abilities(self, trigger: int) -> List[SortedTriggeredAbility]:
        """`$$GetSimulatedActiveTriggeredAbilities(trigger)` -- meme forme sur `+0x28`."""
        return list(self.simulated[int(trigger)])

    def get_effects(self) -> List[SortedEffect]:
        """`$$GetEffects` -> `+0x30`."""
        return list(self.effects)

    def get_refreshing_effects(self) -> List[SortedEffect]:
        """`$$GetRefreshingEffects` -> `+0x38` (et NON `+0x40` -- cf. entete)."""
        return list(self.refreshing_effects)

    def get_effects_with_bonuses(self) -> List[SortedEffect]:
        """`$$GetEffectsWithBonuses` -> `+0x40` (et NON `+0x38` -- cf. entete)."""
        return list(self.effects_with_bonuses)

    def get_refreshing_in_simulated_effects(self) -> List[SortedEffect]:
        """`$$GetRefreshingInSimulatedEffects` -> `+0x48`."""
        return list(self.refreshing_in_simulated_effects)

    def get_triggered_ability_for_non_owner_playbook(self) -> List[SortedTriggeredAbility]:
        """`$$GetTriggeredAbilityForNonOwnerPlaybook` -> `+0x50`."""
        return list(self.triggered_ability_for_non_owner_playbook)

    # ----------------------------------------------------------------- les deux ajouts nus
    def add_ability_or_effect(self, value: SortedTriggered,
                              lst: List[SortedTriggered]) -> None:
        """`$$AddAbilityOrEffect(value, list)` -- corps ENTIER : `AddSorted(value, list)`.
        Il n'existe que pour figer l'instanciation generique `<SortedTriggered>`."""
        add_sorted(value, lst)

    def add_simulated_triggered_or_effect(self, value: SortedTriggeredAbility,
                                          sorted_simulation: List[SortedTriggeredAbility]) -> None:
        """`$$AddSimulatedTriggeredOrEffect(value, sortedSimulation)` -- idem, instanciation
        `<SortedTriggeredAbility>`."""
        add_sorted(value, sorted_simulation)

    # ----------------------------------------------------------------- l'aiguillage
    def add_entity(self, entity) -> None:
        """`$$AddEntity(entity)` -- le point d'entree UNIQUE des deux peupleurs.

            if (entity is EffectEntity ee) { AddEffect(ee, ee.<+0x20>); return; }
            if (entity.TryGetComponent<TriggeredAbilityComponent>(out c)) AddAbility(entity, false, c);

        ⚠ LE PREMIER TEST EST UN TEST DE TYPE D'ENTITE (`IdunBattle.Core.EffectEntity`, lu dans la
        signature de `AddEffect`), PAS un test de composant : le composant d'effet est lu ENSUITE,
        directement a `entity.<+0x20>`, sans `TryGetComponent`. Une entite d'effet ne passe donc
        JAMAIS par la branche ability, meme si elle portait un `TriggeredAbilityComponent`.

        ⚠ `checkIfAlreadyExist` vaut **false** ici -- la deduplication n'est demandee que par
        `RefreshEntity`. Poser `true` ici rendrait `AddEntity` idempotent, ce qu'il N'EST PAS :
        appeler deux fois inscrit deux fois."""
        eff_comp = self._effect_component_of(entity)
        if eff_comp is not None:
            self.add_effect(entity, eff_comp)
            return
        comp = self._triggered_ability_component_of(entity)
        if comp is not None:
            self.add_ability(entity, False, comp)

    def refresh_entity(self, entity) -> None:
        """`$$RefreshEntity(entity)` -- corps ENTIER :

            if (entity.TryGetComponent<TriggeredAbilityComponent>(out c)) AddAbility(entity, true, c);

        Le SEUL site qui passe `checkIfAlreadyExist: true`, et il n'a AUCUNE branche effet : une
        entite d'effet rafraichie ne re-inscrit rien."""
        comp = self._triggered_ability_component_of(entity)
        if comp is not None:
            self.add_ability(entity, True, comp)

    # ----------------------------------------------------------------- les deux peupleurs
    def add_ability(self, entity, check_if_already_exist: bool, abilities) -> None:
        """`$$AddAbility(entity, checkIfAlreadyExist, abilities)`.

        Structure du natif, lue :

            foreach (configId in abilities.<+0x18>)                  // la KeyedCollection du composant
                var order = <configId>.<Type>;                       // le `TriggeredAbilityType`
                var list  = this.abilities.<slot 2>(configId);       // List<ITriggeredAbility>
                bool simulate = StaticBattleRules.TriggeredAbility.ShouldBeSimulated(order);
                foreach (ability in list)
                    foreach (kvp in this.active)                     // TOUTES les cles de l'enum
                        if (ability.<slot 3>.Contains(kvp.Key)) {    // les triggers de l'ability
                            if (checkIfAlreadyExist && kvp.Value.Any(<AddAbility>b__0)) continue;
                            var v = new SortedTriggeredAbility(entity, configId, ability);
                            AddAbilityOrEffect(v, kvp.Value);
                            if (simulate) AddSimulatedTriggeredOrEffect(v, this.simulated[kvp.Key]);
                        }
                if (<slot 0 de this.<+0x58>>(order, simulate) && list.Count > 0)
                    AddSorted(new SortedTriggeredAbility(entity, configId, list.First()),
                              this.triggeredAbilityForNonOwnerPlaybook);

        ⚠ LE BALAYAGE EST SUR LES CLES DU DICTIONNAIRE, PAS SUR LES TRIGGERS DE L'ABILITY. Le natif
        enumere `this.active` et demande a l'ability si elle contient la cle -- l'inverse
        (enumerer les triggers de l'ability) donnerait le meme ENSEMBLE mais pas la meme
        DEPENDANCE : une valeur d'enum absente du dictionnaire ne serait plus ignoree en silence.
        Le port garde la forme native pour cette raison, et parce que le dictionnaire est TOTAL.

        ⚠ `<AddAbility>b__0` (la garde `checkIfAlreadyExist`) compare TROIS choses, pas une :
        `s is SortedTriggeredAbility && s.entity == entity && s.order == order && s.ability is
        ability`. Ne comparer que l'entite dedupliquerait des abilities distinctes du meme porteur.

        ⚠ LA DERNIERE INSCRIPTION EST HORS de la boucle des cles, et son ability est
        `list.First()` -- PAS celle de la derniere iteration. `list.Count > 0` est teste APRES le
        predicat, sur le `List<ITriggeredAbility>` du configId.

        DEUX DONNEES QUE LE PORT N'A PAS, et qui restent des ENTREES fournies par l'appelant :
        `ability.triggers` (le slot 3, un ensemble d'`EventTriggerType`) et le predicat
        non-owner-playbook (slot 0 de `+0x58`, un service que le ctor n'initialise pas). Sans
        `triggers`, l'ability n'est inscrite NULLE PART -- le port le dit en levant plutot qu'en
        n'inscrivant rien."""
        if self.abilities_database is None:
            raise ValueError("add_ability : `abilities_database` absent -- le natif y leve "
                             "(`IAbilitiesDatabase` est un champ non nullable du ctor)")
        for config_id in self._ability_config_ids(abilities):
            order = int(getattr(config_id, "order", config_id))
            lst = list(self.abilities_database(config_id) or ())
            simulate = bool(_should_be_simulated(order))
            for ability in lst:
                for trigger, bucket in self.active.items():
                    if not _ability_listens(ability, trigger):
                        continue
                    if check_if_already_exist and any(
                            isinstance(s, SortedTriggeredAbility) and s.entity == entity
                            and s.order == order and s.ability is ability
                            for s in bucket):
                        continue
                    v = SortedTriggeredAbility(entity, order, ability, config_id)
                    self.add_ability_or_effect(v, bucket)
                    if simulate:
                        self.add_simulated_triggered_or_effect(v, self.simulated[trigger])
            if lst and _for_non_owner_playbook(order, simulate):
                add_sorted(SortedTriggeredAbility(entity, order, lst[0], config_id),
                           self.triggered_ability_for_non_owner_playbook)

    def add_effect(self, entity, effect_component) -> None:
        """`$$AddEffect(entity, effectComponent)`.

        Structure du natif, lue :

            var effect = this.effects.<slot 0>(effectComponent.<+0x58>);       // EffectType -> IEffect
            var v      = new SortedEffect(entity, effectComponent, effect);
            foreach (grp in effect.<slot 0x12>)                                 // ArraySet
                foreach (trigger in <les triggers du grp>)
                    var list = this.active[trigger];
                    if (!list.Any(s => s is SortedEffect se && se.entity == entity))
                        AddAbilityOrEffect(v, list);
            var extra = effect.<slot 0x2d>;
            if (extra != null)
                foreach (t in extra) AddSorted(v, this.active[t.<slot 0>]);
            if (effect.<slot 10> || effectComponent.<+0x5d>)  AddSorted(v, this.refreshingEffects);
            if (StaticBattleRules.Effect.ShouldRefreshDuringSimulation(effectComponent.<+0x58>))
                                                              AddSorted(v, this.refreshingInSimulatedEffects);
            if (effect.<slot 0x2e>)                           AddSorted(v, this.effectsWithBonuses);
                                                              AddSorted(v, this.effects);

        ⚠ LES DEUX BOUCLES NE SE GARDENT PAS PAREIL, et c'est le piege : la premiere refuse
        d'inscrire un SECOND `SortedEffect` de la MEME ENTITE dans une liste qui en contient deja
        un (`<AddEffect>b__0` : `s is SortedEffect && s.entity == entity`) ; la seconde n'a AUCUNE
        garde. Uniformiser les deux ajouterait des doublons -- ou en supprimerait.

        ⚠ `effectComponent.<+0x5d>` est `HasTurns` -- nom LU dans la format-string de
        `EffectComponent$$GetPropertiesString` (cf. #477-r21-r2 volet A), pas devine.

        ⚠ L'ORDRE DES QUATRE DERNIERS AJOUTS EST CELUI DU DECOMPILE, et le port le conserve meme
        s'il porte sur QUATRE listes distinctes : ces listes n'ont pas d'ordre relatif observable
        aujourd'hui, mais reordonner un mirror « parce que ca ne se voit pas » est exactement ce
        qui rend une divergence future inattribuable.

        Les quatre donnees venues de `IEffect` (slots 0x12, 0x2d, 10, 0x2e) sont des ENTREES,
        comme `ability.triggers` pour `add_ability`."""
        if self.effects_database is None:
            raise ValueError("add_effect : `effects_database` absent -- le natif y leve "
                             "(`IEffectsDatabase` est un champ non nullable du ctor)")
        effect_type = getattr(effect_component, "effect_type", None)
        effect = self.effects_database(effect_type)
        v = SortedEffect(entity, effect_component, effect)
        for trigger in _effect_ability_triggers(effect):
            bucket = self.active[int(trigger)]
            if any(isinstance(s, SortedEffect) and s.entity == entity for s in bucket):
                continue
            self.add_ability_or_effect(v, bucket)
        for trigger in _effect_own_triggers(effect):
            add_sorted(v, self.active[int(trigger)])
        if bool(getattr(effect, "refreshes", False)) or bool(
                getattr(effect_component, "has_turns", False)):
            add_sorted(v, self.refreshing_effects)
        if _should_refresh_during_simulation(effect_type):
            add_sorted(v, self.refreshing_in_simulated_effects)
        if bool(getattr(effect, "has_bonuses", False)):
            add_sorted(v, self.effects_with_bonuses)
        add_sorted(v, self.effects)

    # ----------------------------------------------------------------- les deux retraits
    def remove_entity(self, entity) -> None:
        """`$$RemoveEntity(entity)` -- DEUX branches, et elles ne retirent PAS de la meme facon.

            if (EntityExtensions.IsEffect(entity)) {
                foreach (list in this.active.Values) {
                    int i = list.FindIndex(s => s.<+0x10> == entity);   // UN SEUL
                    if (i != -1) list.RemoveAt(i);
                }
                foreach (l in [refreshingEffects, refreshingInSimulated, effectsWithBonuses, effects])
                    { int i = l.FindIndex(...); if (i != -1) l.RemoveAt(i); }
            } else if (EntityExtensions.IsUnit(entity)) {
                foreach (list in this.active.Values)     list.RemoveAll(s => s is Sorted* && s.entity == entity);
                foreach (list in this.simulated.Values)  list.RemoveAll(...);
                this.triggeredAbilityForNonOwnerPlaybook.RemoveAll(...);
            }
            // ni effet ni unite -> RIEN

        ⚠ `FindIndex` + `RemoveAt` D'UN COTE, `RemoveAll` DE L'AUTRE, et l'asymetrie est REELLE :
        une entite d'effet ne peut avoir qu'UNE entree par liste (la premiere boucle d'`AddEffect`
        s'en assure explicitement), alors qu'une unite en a autant que d'abilities declenchees.
        Remplacer le premier par un `RemoveAll` serait sans effet AUJOURD'HUI et masquerait toute
        rupture future de cet invariant ; l'inverse, lui, laisserait des entrees mortes.

        ⚠ L'ORDRE DES QUATRE LISTES D'EFFET EST `refreshing, refreshingInSimulated, withBonuses,
        effects` -- soit un ordre DIFFERENT de celui des ajouts d'`AddEffect`. Conserve tel quel.

        ⚠ LA BRANCHE UNITE NE TOUCHE PAS AUX QUATRE LISTES D'EFFET. Une unite qui meurt laisse
        donc dans `effects` les `SortedEffect` des entites-effet qu'elle portait : c'est leur
        propre `RemoveEntity` qui les retire, pas le sien.
        """
        if _is_effect_entity(entity):
            for bucket in self.active.values():
                i = _find_index(bucket, lambda s: s.entity == entity)
                if i != -1:
                    bucket.pop(i)
            for lst in (self.refreshing_effects, self.refreshing_in_simulated_effects,
                        self.effects_with_bonuses, self.effects):
                i = _find_index(lst, lambda s: s.entity == entity)
                if i != -1:
                    lst.pop(i)
            return
        if not _is_unit_entity(entity):
            return
        for bucket in self.active.values():
            bucket[:] = [s for s in bucket if not (isinstance(s, SortedTriggeredAbility)
                                                   and s.entity == entity)]
        for bucket in self.simulated.values():
            bucket[:] = [s for s in bucket if not (isinstance(s, SortedTriggeredAbility)
                                                   and s.entity == entity)]
        self.triggered_ability_for_non_owner_playbook[:] = [
            s for s in self.triggered_ability_for_non_owner_playbook
            if not (isinstance(s, SortedTriggeredAbility) and s.entity == entity)]

    def remove_triggered(self, target, triggered_ability_type: int) -> None:
        """`$$RemoveTriggered(target, triggeredAbilityType)` -- corps ENTIER :

            foreach (kvp in this.active)
                kvp.Value.RemoveAll(s => s is SortedTriggeredAbility sta
                                      && sta.entity == target
                                      && sta.order  == triggeredAbilityType);

        ⚠ IL NE TOUCHE QUE `+0x20`. Ni le dictionnaire de simulation, ni la liste
        non-owner-playbook, ni les quatre listes d'effet ne sont purges -- une ability retiree
        d'une unite y RESTE. Ce n'est pas un oubli qu'on corrige au portage."""
        order = int(triggered_ability_type)
        for bucket in self.active.values():
            bucket[:] = [s for s in bucket
                         if not (isinstance(s, SortedTriggeredAbility)
                                 and s.entity == target and s.order == order)]

    # ----------------------------------------------------------------- adaptateurs d'etat
    # Ces quatre lectures sont les SEULS points ou le cache touche au modele d'entites du port.
    # Elles sont isolees ici pour que le mirror ci-dessus reste lisible contre le decompile.
    @staticmethod
    def _effect_component_of(entity):
        """`entity is EffectEntity ? entity.<+0x20> : null`."""
        return getattr(entity, "effect_component", None)

    @staticmethod
    def _triggered_ability_component_of(entity):
        """`entity.TryGetComponent<TriggeredAbilityComponent>(out c)`."""
        return getattr(entity, "triggered_ability_component", None)

    @staticmethod
    def _ability_config_ids(abilities) -> Sequence:
        """`abilities.<+0x18>` -- la `KeyedCollection<TriggeredAbilityType, TriggeredAbilityConfigId>`
        du `TriggeredAbilityComponent`. L'ORDRE de cette collection est l'ordre d'ajout par
        `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` ; il n'est PAS trie,
        et c'est lui qui decide de l'ordre intra-unite dans le cache."""
        return list(getattr(abilities, "config_ids", abilities) or ())


# --------------------------------------------------------------------------- entrees externes
# Les six fonctions ci-dessous sont les DONNEES que le cache consomme et que le decompile ne rend
# PAS (corps dedupliques, blobs `global-metadata.dat`). Le port les isole pour que le manque soit
# NOMME et substituable, jamais fondu dans le mirror.

def _find_index(lst: Sequence, pred: Callable) -> int:
    """`List<T>.FindIndex(Predicate<T>)` -- `-1` si aucun."""
    for i, x in enumerate(lst):
        if pred(x):
            return i
    return -1


def _ability_listens(ability, trigger: int) -> bool:
    """`ability.<slot 3>.Contains(trigger)` -- l'ensemble des `EventTriggerType` de l'ability.

    ENTREE : le port lit `ability.triggers`. Sur les classes `TriggeredAbility` du port, c'est
    l'ensemble derive de leur `event_id` / `event_ids`."""
    trs = getattr(ability, "triggers", None)
    if trs is None:
        ev = getattr(ability, "event_id", None)
        evs = getattr(ability, "event_ids", ()) or ()
        trs = ({int(ev)} if ev is not None and int(ev) >= 0 else set()) | {int(e) for e in evs}
    return int(trigger) in {int(t) for t in trs}


def _effect_ability_triggers(effect) -> Iterable[int]:
    """`effect.<slot 0x12>` aplati -- les triggers des ABILITIES portees par l'effet."""
    return [int(t) for t in (getattr(effect, "ability_triggers", None) or ())]


def _effect_own_triggers(effect) -> Iterable[int]:
    """`effect.<slot 0x2d>` -- la liste (nullable) de triggers PROPRES a l'effet."""
    return [int(t) for t in (getattr(effect, "own_triggers", None) or ())]


def _should_be_simulated(triggered_ability_type: int) -> bool:
    """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.TriggeredAbility$$ShouldBeSimulated`.

    NON PORTE : la table vit cote `StaticBattleRules`, hors du perimetre de cette tranche. Rendre
    `False` laisse le volet SIMULATION (`+0x28`, `+0x50`) vide -- ce qui est exactement le regime
    d'un deroule REEL, le seul que le harnais joue (`EvaluateTriggerOperation$$ExecuteSimulation`
    est l'autre voie). Un `True` par defaut, lui, peuplerait une liste que personne ne relit."""
    return False


def _should_refresh_during_simulation(effect_type) -> bool:
    """`...StaticBattleRules.Effect$$ShouldRefreshDuringSimulation` -- meme statut que ci-dessus."""
    return False


def _for_non_owner_playbook(triggered_ability_type: int, simulate: bool) -> bool:
    """Le slot 0 de `this.<+0x58>` -- le service qui decide si l'ability entre dans la liste
    `GetTriggeredAbilityForNonOwnerPlaybook`.

    NON PORTE, et le champ lui-meme est un ANGLE MORT LU : `+0x58` existe (la classe fait 96
    octets) mais le ctor ne l'initialise PAS -- il est ecrit par un autre site, non identifie.
    Rendre `False` laisse `+0x50` vide ; son seul consommateur porte cote natif est
    `IdunBattle.AI.Utilities.TriggeredAbilitiesNonOwnerUtility$$IsInvalidEntityForPlaybook`, hors
    de la face executee ici."""
    return False


def _is_effect_entity(entity) -> bool:
    """`IdunBattle.Entities.EntityExtensions$$IsEffect(entity)`."""
    return getattr(entity, "effect_component", None) is not None


def _is_unit_entity(entity) -> bool:
    """`IdunBattle.Entities.EntityExtensions$$IsUnit(entity)`."""
    return getattr(entity, "is_unit", False) or getattr(
        entity, "triggered_ability_component", None) is not None
