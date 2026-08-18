"""Coeur du dispatch : collecte des triggers portes et evaluation d'un `TriggerEvent`,
extraits de `triggers/dispatch.py` (scission du module >1000 lignes, tache #169 --
deplacement VERBATIM, zero changement de comportement).

  - `collect_triggered_abilities` / `collect_effect_triggers` : mirror du registre
    `AbilityAndEffectCache` (volets ability-trigger et effet-trigger) ;
  - `evaluate_trigger_operation` : le point de passage de TOUS les vecteurs d'event ;
  - `_trigger_phase_component` : le composant de phase du porteur."""
from __future__ import annotations

from typing import Optional

from .....dsl.event_trigger_type import EventTriggerType
from ....state import State
from ....components import StatsComponent, UnitComponent, TriggeredAbilityComponent
from ..base import TriggerEvent, TriggeredAbility, EffectTrigger, PHASE_TRIGGER_CAP
from .registry import (TRAIT_TRIGGERS, ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS,
                       PASSIVE_HELPER_ABILITY_TRIGGERS, RELIC_ABILITY_TRIGGERS, EFFECT_TRIGGERS)
from .registry import GLOBAL_TRIGGERS


def _triggers_du_cadavre_au_chargement(e, eid: int, GC, behaviour_trait_triggers) -> list:
    """Les triggered-abilities EXEMPTEES d'un CADAVRE-AU-CHARGEMENT (#547-r12).

    ===============================================================================================
    LE PARTAGE NATIF -- LE CACHE GARDE, `CanGetAbilityTrigger` TRIE
    ===============================================================================================

    `IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache$$AddEntity` (relu VERBATIM sur
    `t6dpr4k06g`) n'a AUCUN gate de vivacite : il aiguille sur `IsEffect` -> `AddEffect`, sinon
    `TryGetComponent<TriggeredAbilityComponent>` -> `AddAbility`. Ni `IsAlive`, ni HP, ni stats. Le
    tri se fait un cran plus bas, A LA LECTURE :

        IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger
            if (!ability.get_AllowForDeadOwner()) {            // ITriggeredAbility slot 8
                if (IsUnit(owner) && !IsAlive(owner))  return 0; }
            if (IsUnit(owner) && IsTriggersDisabled(owner))    return 0;

    `get_AllowForDeadOwner` = le mirror `fire_on_death` du port (#10015 -- ce n'est PAS `IsAtomic`).

    ===============================================================================================
    CE QUE LE PORT FAISAIT, ET POURQUOI C'ETAIT UN ECART
    ===============================================================================================

    `collect_triggered_abilities` ouvre sur `if sc is None: continue`. Or le `StatsComponent` n'est
    pose que depuis une ligne de `combatSnapshot.units[]`, et ce capteur FILTRE `IsAlive` : une
    entite chargee depuis `decisionView.units[]` (qui, elle, CONSERVE les morts AVEC leurs effets)
    et absente du snapshot n'a donc AUCUN `StatsComponent` -- et sortait du registre AVANT tout
    gate. Pour les abilities NON exemptees les deux verdicts coincident (le gate d'aval les
    couperait de toute facon) ; pour une exemptee, le port PERDAIT une ability que le natif evalue.

    CAS MOTIVANT, MESURE : `LifewardsAbility` (`TriggeredAbilityType` 0x419 = 1049, passif du summon
    `adeptSmnGeminaeSuperia`). Son `CreateTrigger` porte

        On(0x39 = PreDamageTaken) & <DSLTriggers+0x70 = YesTrigger>
          & ( IsAlive(Owner@<DSLSelectors+0x30>)
              | HasEffect(Owner@+0x30, 0x4d8 = 1240, onlyActive: 0, effectTarget: 6) )
          & AreEqual(Target@<DSLSelectors+0x60>, Parent(Owner@+0x30))
          & IsAdjacent(Owner@+0x30, Target@+0x60, 0)

    -- la disjonction est ecrite EXPRES pour qu'une Geminae MORTE portant encore le marqueur 1240
    absorbe le coup destine a Celestine. Sans inscription, Celestine encaisse des degats que le
    natif lui epargne.

    ===============================================================================================
    LE SUBSTRAT -- LES MEMES CHEMINS, AVEC CE QUI RESTE LISIBLE
    ===============================================================================================

    Sans `StatsComponent` il n'y a plus de `UnitContext`, donc plus AUCUN canal MESURE
    (`passive_abilities`, `config_active_abilities`, `tertiary_ability`, `traits` mesures). Reste la
    `visual_id` du `UnitComponent` -- posee par `snapshot.load_state` depuis
    `decisionView.units[].visualId`, donc presente sur un cadavre. On rejoue alors les chemins de
    registration par le REPLI GAMECONFIG, c'est-a-dire exactement ce que le port fait deja pour
    toute unite dont le canal est muet (`UnitContext.from_snapshot` derive lui aussi `traits` de
    `cfg.get("traits")`). CINQ des six chemins sont donc servis ; le SIXIEME
    (`UnitConfiguration.TertiaryAbility`, relique EQUIPEE) n'a QUE le canal `unitAbilityStates`,
    qui ecrit dans le ctx : il reste muet ici, et c'est NOMME (residu, cf. la fiche #547-r12).

    ===============================================================================================
    DEUX RESTRICTIONS, ASSUMEES ET ECRITES
    ===============================================================================================

    1. **Le filtre `fire_on_death`.** Ce n'est PAS le mirror du cache (qui garde TOUT) : c'est une
       restriction qui COINCIDE avec le gate d'aval -- `evaluate_trigger_operation` coupe
       `not uc.alive and not fire_on_death`, donc inscrire les non-exemptees serait un surcout sans
       effet observable. Le SEUL regime ou les deux differeraient est la RESURRECTION d'un
       cadavre-au-chargement (`uc.alive` redevient vrai sans qu'aucun `StatsComponent` soit pose) ;
       il reste hors de ce port et est nomme au residu.
    2. **Le gate `not uc.alive`.** Une entite-unite VIVANTE sans `StatsComponent` n'est pas
       inscrite ici : elle demanderait d'inscrire TOUT son kit, pas seulement les exemptees, ce qui
       est un elargissement d'un autre ordre. `uc is None` (entite non-unite) sort aussi -- mirror
       d'`IdunBattle.Entities.EntityExtensions$$IsUnit`, que `CanGetAbilityTrigger` place devant
       ses deux gates.

    Le tri fin reste ou le natif le met : dans `matches` (le `CreateTrigger` de chaque ability),
    rejoue a chaque evenement contre l'etat COURANT."""
    uc = e.get_component(UnitComponent)
    if uc is None or uc.alive:
        return []
    vid = getattr(uc, "visual_id", None)
    if not vid:
        return []
    gu = GC.unit(vid) or {}
    out: list = []

    def _pose(table, cles) -> None:
        for cle in (cles or []):
            for cls in table.get(cle, ()):
                if getattr(cls, "fire_on_death", False):     # = `get_AllowForDeadOwner()`
                    out.append(cls(eid))

    _pose(TRAIT_TRIGGERS, gu.get("traits"))                  # 1. trait
    _pose(behaviour_trait_triggers, gu.get("traits"))        #    (meme substrat, table distincte)
    _pose(ABILITY_TRIGGERS, gu.get("passiveAbilities"))      # 2. passiveAbility
    _pose(ACTIVE_ABILITY_TRIGGERS, gu.get("activeAbilities"))        # 3. derivee d'une active
    _pose(PASSIVE_HELPER_ABILITY_TRIGGERS, gu.get("activeAbilities"))  # 6. helper d'une active
    _pose(RELIC_ABILITY_TRIGGERS, gu.get("relicAbilities"))  # 4. relique EN DUR (gameconfig)
    return out                                               # 5. TertiaryAbility : cf. la docstring


def collect_triggered_abilities(state: State) -> list[TriggeredAbility]:
    """Mirror du registre `AbilityAndEffectCache` (volet ability-trigger) : itère TOUTES les entités et,
    pour chaque trait à trigger porté, instancie l'ability correspondante (owner = l'entité). (Le volet
    effet-trigger — Overwatch, on-hit — n'est pas encore collecté ici.)

    SIX chemins de registration, tous mirrors de `IdunBattle.Entities.Factories.UnitFactory$$Add*
    Abilities` : trait, passiveAbility, activeAbility (dérivée), relicAbility EN DUR (gameconfig),
    -- depuis #357 -- l'item RELIQUE ÉQUIPÉ (`UnitConfiguration.TertiaryAbility`, cf. plus bas), et
    -- depuis #521-r1 -- la triggered-ability HELPER d'une active
    (`...StaticBattleRules.ActiveAbility$$GetPassiveHelperAbility`, dict statique DISTINCT de celui
    des dérivées)."""
    import gameconfig as GC
    from ...behaviour import BEHAVIOUR_TRAIT_TRIGGERS            # lazy : evite circular import behaviour<->triggers
    out: list[TriggeredAbility] = []
    for eid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is None:
            # CADAVRE-AU-CHARGEMENT (#547-r12) -- le `continue` reste, mais il ne mange plus les
            # abilities EXEMPTEES. Detail et decompile : `_triggers_du_cadavre_au_chargement`.
            out.extend(_triggers_du_cadavre_au_chargement(e, eid, GC, BEHAVIOUR_TRAIT_TRIGGERS))
            continue
        for trait in (sc.ctx.traits or []):
            for cls in TRAIT_TRIGGERS.get(trait, ()):            # un trait peut accorder >1 trigger
                out.append(cls(eid))
            for cls in BEHAVIOUR_TRAIT_TRIGGERS.get(trait, ()):  # mecaniques de comportement (Battle Fatigue)
                out.append(cls(eid))
        # passiveAbilities (TheBetrayer…).
        # SOURCE (#366-r1) : la liste MESUREE des passives REELLEMENT montees quand le canal
        # `unitAbilityStates` a parle (`UnitContext.passive_abilities`, hierarchie 2 =
        # `UnitConfiguration.PassiveAbilities`, cf. `snapshot._load_passive_abilities`) ; sinon,
        # et SEULEMENT sinon, la derivation gameconfig par `visualId` d'avant. C'est le meme
        # arbitrage que `traits_measured` (#264) : le natif monte `BC.Units[].PassiveAbilities`,
        # jamais le kit gameconfig -- une reconstruction laissait INERTE, sans erreur, tout passif
        # que le BC porte et que le kit ignore (cas d'une GREFFE, seul chemin de confrontation
        # d'une ability a porteur npc).
        vid = getattr(sc.ctx, "visual_id", None)
        relics: list[str] = []
        measured_pas = getattr(sc.ctx, "passive_abilities", None)
        gu = (GC.unit(vid) or {}) if vid else {}
        passives = measured_pas if measured_pas is not None else list(gu.get("passiveAbilities") or [])
        for pa in passives:
            for cls in ABILITY_TRIGGERS.get(pa, ()):
                out.append(cls(eid))
        # SUBSTRAT DES DEUX REGISTRES D'ACTIVE, et il est TRI-ETAT (meme discipline que
        # `passive_abilities` juste au-dessus) : `config_active_abilities` EST
        # `UnitConfiguration.ActiveAbilities` mesuree (canal `unitAbilityStates.units[].configActives`,
        # #466) ; `None` = canal non mesure -> repli sur le kit gameconfig. Le repli n'est PAS
        # equivalent : une active GREFFEE sur une unite du pool (seul chemin de confrontation d'une
        # ability a porteur npc) n'existe QUE dans la mesure.
        #
        # UNE SEULE LECTURE POUR LES DEUX REGISTRES (#521-r5), et c'est le NATIF qui l'impose --
        # `config@+0xa0` est le MEME champ des deux cotes, LU au decompile :
        #   * `IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities(entity, config,
        #     activeAbilityState, triggeredAbilityState)` ouvre sur
        #     `List<ActiveAbilityType>.GetEnumerator(config@+0xa0)` et, par element,
        #     `StaticBattleRules.ActiveAbility$$HasDerivedTriggeredAbilities` ->
        #     `...$$GetDerivedTriggeredAbilities` -> `TriggeredAbilityComponent$$TryAdd`
        #     (= `ACTIVE_ABILITY_TRIGGERS`) ;
        #   * `IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` boucle sur ce MEME
        #     `config@+0xa0` pour appeler `...$$AddActiveAbility`, qui interroge
        #     `StaticBattleRules.ActiveAbility$$GetPassiveHelperAbility`
        #     (= `PASSIVE_HELPER_ABILITY_TRIGGERS`).
        # Les faire lire deux substrats DIFFERENTS etait donc un artefact du port, pas une nuance du
        # natif : `ACTIVE_ABILITY_TRIGGERS` sur le seul kit gameconfig etait AVEUGLE a une active
        # greffee -- exactement le regime qu'il faut pour confronter une ability a porteur npc.
        measured_actives = getattr(sc.ctx, "config_active_abilities", None)
        config_actives = (measured_actives if measured_actives is not None
                          else list(gu.get("activeAbilities") or []))
        for aa in config_actives:
            # activeAbilities -> triggered-abilities DERIVEES
            # (`StaticBattleRules.ActiveAbility$$GetDerivedTriggeredAbilities`) : portee des l'init
            # de l'unite, sans cast prealable.
            for cls in ACTIVE_ABILITY_TRIGGERS.get(aa, ()):
                out.append(cls(eid))
            # SIXIEME chemin (#521-r1) : la triggered-ability HELPER d'une ability ACTIVE
            # (`StaticBattleRules.ActiveAbility$$GetPassiveHelperAbility`, dict statique DISTINCT de
            # celui des derivees -- cf. l'en-tete de `PASSIVE_HELPER_ABILITY_TRIGGERS`), montee par
            # `IdunBattle.Entities.Factories.UnitFactory$$AddActiveAbility`.
            for cls in PASSIVE_HELPER_ABILITY_TRIGGERS.get(aa, ()):
                out.append(cls(eid))
        if vid:
            # relicAbilities -> triggered-ability(s) accordee(s) par une RELIQUE cablee EN DUR sur
            # l'unite (#317). QUATRIEME chemin de registration ; les 25 abilities dans ce cas sont
            # TOUTES sur des npc.
            relics = list(gu.get("relicAbilities") or [])
        # CINQUIEME chemin (#357) : l'item RELIQUE **EQUIPE**, `UnitConfiguration.TertiaryAbility`
        # (+0xb0). C'est la branche TERTIAIRE d'`IdunBattle.Entities.Factories.UnitFactory$$
        # AddConfiguredAbilities` : `if (config.TertiaryAbility.HasValue) TriggeredAbilityComponent
        # $$TryAdd(id, tertiaryAbilityState, 3)`. Etat JOUEUR, invisible du gameconfig -- d'ou un
        # canal PROPRE (`snapshot._load_tertiary_abilities`, RPC `unitAbilityStates`) et non une
        # derivation -- ON PAR DEFAUT depuis #363 (transport ambiant lie par le harnais). Sans ce
        # canal (State nu, capture rejouee hors harnais live, ou `ability_states=False`),
        # `tertiary_ability` vaut None et cette branche est un no-op : le comportement d'avant.
        # DEDUPLICATION -- le natif TryAdd sur une `KeyedCollection` indexee par l'ability-type :
        # monter DEUX FOIS la meme ability n'ajoute qu'UNE entree. Un npc qui porte la relique en dur
        # ET se la voit equipee (montage synthetique) ne doit donc etre inscrit qu'une fois.
        tertiary = getattr(sc.ctx, "tertiary_ability", None)
        if tertiary and tertiary not in relics:
            relics.append(tertiary)
        for ra in relics:
            for cls in RELIC_ABILITY_TRIGGERS.get(ra, ()):
                out.append(cls(eid))
    return out


def collect_global_triggers() -> list[TriggeredAbility]:
    """Volet GLOBAL du registre : les abilities `IdunBattleLogic.Entities.Abilities.Damage.Loki.*`,
    inscrites UNE SEULE FOIS pour la bataille et non par entité.

    Leur `CreateTrigger` ne porte AUCUN prédicat d'owner -- il ne teste que le PROFIL du coup :
        IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateTrigger
            On(0x10, 1) & DamageProfileHasTrait(1 = OnFire)  & !TriggeringEffectIs(5)
        IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateTrigger
            On(0x10, 1) & DamageProfileHasTrait(4 = OnToxic) & !TriggeringEffectIs(0x4dc)
    Elles se déclenchent donc pour N'IMPORTE QUEL attaquant dont le coup porte le trait, ce qui est
    exactement ce qu'un registre par-entité ne sait pas exprimer.

    CARDINALITE -- l'inscription est UNIQUE, et c'est une MESURE, pas une hypothèse : le canal 1203
    consomme EXACTEMENT un `NextBool` par série de coups en live (`test_on_toxic_damage_live.py`,
    oracle = l'état MT). Une inscription par unité en consommerait un PAR unité du plateau.
    RESIDU DOCUMENTE : le SITE natif de cette inscription unique n'est pas RE'd
    (`IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache$$AddEntity` n'ajoute que les
    abilities PORTEES par l'entité) ; c'est la cardinalité observée qui fonde ce registre."""
    return [cls(None) for cls in GLOBAL_TRIGGERS]


def collect_effect_triggers(state: State) -> list[EffectTrigger]:
    """Mirror du registre `AbilityAndEffectCache` (volet effet-trigger) : itère TOUS les effets portés
    par chaque unité (via `state.effects`), ACTIFS OU NON, et, pour chaque effet d'un type enregistré,
    instancie son effet-trigger (owner = le porteur). Seul `consumed` exclut. No-op si `state.effects`
    absent.

    ⚠ **« ACTIFS » SERAIT FAUX, ET LA FAUTE SERAIT DEFINITIVE (#1045-r2).** Le rail natif
    `IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities` n'accede
    JAMAIS a `EffectComponent+0x5c` (le drapeau d'activite) : relu sur `t6dpr4k06g`, il ne lit du
    composant que `+0x14` (l'unite porteuse, resolue en amont par
    `...$$EvaluateAbilityOrEffectTrigger`) et `+0x58` (le type d'effet, cle de l'`IEffectsDatabase`),
    puis enumere l'`ArraySet` rendu par `IEffect` slot 18 = `CreateHandleTriggerAbilities`. Le CODE
    ci-dessous a donc raison contre toute prose qui dirait « actifs ».

    **Pourquoi ce n'est pas cosmetique** : un lecteur qui « aligne le code sur la doc » poserait un
    gate `is_active` ici et **gelerait a zero POUR TOUJOURS** tout compteur porte par un effet ne
    INACTIF -- mesure sur `HeadwoppasKillchoppa_ExtraDmg` (1568), qui nait au niveau 0 (`Direct(0)`)
    et ne monte que par `IncreaseEffectLevelOnKill` : sa condition
    `AmountIsGreaterThanZero(EffectLevel)` ne pourrait alors plus jamais devenir vraie. Contre-epreuve
    executee en #1045 : instance `active=False` -> 1 trigger collecte (dont 1 `IncreaseLevelOnKill`) ;
    `consumed=True` -> 0."""
    out: list[EffectTrigger] = []
    eff = getattr(state, "effects", None)
    if eff is None:
        return out
    for uid, effs in eff.by_unit.items():
        for e in effs:
            if e.consumed:
                continue
            for cls in EFFECT_TRIGGERS.get(e.effect_type, ()):   # ArraySet natif : N triggers par effet
                out.append(cls(int(uid)))
    return out


def _owner_gate_applies(entry) -> bool:
    """Cette entree du registre passe-t-elle par un gate d'OWNER ? (#462-r4b-r1-r1-r1-r1-c-r3)

    Le natif a DEUX fonctions de gate, et elles ne gatent PAS la meme chose. Ce predicat EST cette
    bifurcation -- il decide LAQUELLE des deux `evaluate_trigger_operation` applique.

    FACE ABILITY -> `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` : deux
    gates, tous deux SOUS `IdunBattle.Entities.EntityExtensions$$IsUnit(owner)` --
    `UnitExtensions$$IsAlive` (sauf `get_AllowForDeadOwner`, cf. ci-dessous) et
    `UnitExtensions$$IsTriggersDisabled`.

    ⚠ **LA DISPENSE NE S'APPELLE PAS `IsAtomic` -- C'EST `ITriggeredAbility.get_AllowForDeadOwner`,
    ET LE DEPOT SE TROMPAIT DE PROPRIETE (#10015).** Le pseudo-C rend
    `FUN_180002590(8, DAT_183389188, ability)`, c'est-a-dire un appel au SLOT 8 d'une interface. Les
    deux ont ete LUS, pas devines :
      * `DAT_183389188` = `IdunBattle.Entities.Abilities.ITriggeredAbility` -- le type DECLARE du
        parametre (`frida/methods.tsv`), et TROIS concordances slot/arite le confirment dans
        `...$$EvaluateEffectTriggerEffectAbilities` : slot 2 = `ShouldTrigger` (2 args), slot 4 =
        `ExecuteBy` (3 args), slot 8 = `get_AllowForDeadOwner` (0 arg, booleen) ;
      * les slots viennent du champ `slot` d'`Il2CppMethodDefinition` (`global-metadata.dat`, meme
        derivation que `data/symbols/<build>/metadata/interface_slots.tsv`).
    Il existe bien une propriete d'ATOMICITE, mais c'est une AUTRE : `ITriggerable` slot 0 =
    `get_AllowInAtomicMode`, lue plus bas dans la MEME fonction sous
    `IMatchState slot 22 = get_InAtomicMode` et sous le parametre `onlyNonAtomic`. Les deux jeux de
    declarants sont DISJOINTS (43 vs 24 surchargeurs, un seul type -- `ThrillSeekersAbility`,
    `DrawFireAbility`, `FloatingDeath_AttackAbility`, `LifewardsAbility` -- en porte les deux).
    Confondre les deux, c'est lire la mauvaise propriete SANS AUCUNE ERREUR.
    Ce second gate n'est PAS porte : residu `#10015-r1`.

    ⚠ **ET IL NE DOIT PAS L'ETRE SEUL -- LE GATE N'EST PAS UN FILTRE, C'EST LA MOITIE D'UN
    AIGUILLAGE VERS UNE FILE (#10015-r3).** Le residu `#10015-r1` proposait d'<< etablir quels
    vecteurs du port courent sous `AtomicGroup` avant d'ecrire le moindre gate >>. Les vecteurs
    EXISTENT (`entities/behaviours.py::AtomicGroup`, utilise par `ExplosivePresents`,
    `VexillaMagnifica`, `FrenziedFiring`, `MortisRound`, `StormOfWrath`, `IncendiaryShells`,
    `HarvesterOfSouls`, ...), donc ce n'est pas la le blocage. Le blocage est que **poser le seul
    predicat PERDRAIT les triggers que le natif DIFFERE**. Chaine LUE de bout en bout sur
    `t6dpr4k06g`, tous les slots nommes par les entrees versionnees
    (`metadata/interface_slots.tsv`, `metadata/ioperationprocessor_slots.tsv`) :

      * `IdunBattle.Operations.AtomicGroupOperation$$Execute` ouvre par `IMatchState` slot 20 =
        `IncreaseAtomicModeCounter`, execute le behaviour INLINE, ferme par slot 21 =
        `DecreaseAtomicModeCounter`, **puis DRAINE** : `while (slot 10 = TryDequeueBattleEvent(&ev))`
        -> `ev.kind == 0` : `IOperationProcessor` slot 78 = `EvaluateAbilities(ev)` ;
           `ev.kind == 1` : `IMatchState` slot 41 = `Get(entityId)` puis `IOperationProcessor`
           slot 85 = `UnregisterEntityFromTriggers`.
      * `IdunBattle.Core.MatchState$$get_InAtomicMode` = `MatchState+0x54 > 0` -- un COMPTEUR, donc
        les groupes s'imbriquent.
      * `IdunBattle.Operations.EvaluateTriggerOperation$$Execute` : `if (!InAtomicMode)
        ExecuteInternal(..., onlyNonAtomic: 0)` **sinon** `AddBattleEvent(new BattleEvent(trigger,
        entities, onlyNonAtomic: 0))` -- en mode atomique elle **n'evalue RIEN**, elle ENFILE.
      * `IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteImmediately` : `if (InAtomicMode)
        AddBattleEvent(new BattleEvent(trigger, entities, **onlyNonAtomic: 1**))` PUIS, dans tous
        les cas, `ExecuteInternal(..., onlyNonAtomic: 0)`.

    **La partition est EXACTE et SANS PERTE**, et c'est ce qui rend le gate lisible : sous
    `ExecuteImmediately` en mode atomique, le premier test (`if (InAtomicMode) { if
    (!AllowInAtomicMode) return false; }`) ne laisse passer TOUT DE SUITE que les
    `AllowInAtomicMode == TRUE` ; le rejeu enfile porte `onlyNonAtomic: 1`, dont le second test
    (`if (onlyNonAtomic) { if (AllowInAtomicMode) return false; }`) ne laisse passer que les
    `AllowInAtomicMode == FALSE` -- exactement le complement. Aucune ability n'est perdue, aucune
    n'est jouee deux fois. Un port qui ecrirait le premier test sans la file inverserait ce
    resultat : les **24** declarants a TRUE joueraient, et TOUS LES AUTRES seraient SUPPRIMES au
    lieu d'etre differes -- une regression d'autant plus large que FAUX est le defaut de
    `IdunBattle.Entities.Abilities.BaseTriggeredAbility`.

    L'ETAGE MANQUANT SE NOMME DONC, et ce n'est ni le compteur ni le predicat (tous deux triviaux) :
    c'est la **file de `BattleEvent` du `MatchState`** (slots 9 / 10), son **drain en fin
    d'`AtomicGroup`**, et la **distinction `Execute` / `ExecuteImmediately` chez les publieurs** --
    que le port fond aujourd'hui en un unique `evaluate_trigger_operation`. Residu re-enonce.

    ⚠ **ET LA VALEUR SE LIT, MEME QUAND LA TABLE NE LA MONTRE PAS.** `get_AllowForDeadOwner` a un
    corps TRIVIAL, donc DEDUPLIQUE : `<Classe>$$get_AllowForDeadOwner` n'apparait ni dans
    `frida/methods.tsv` ni dans `ghidra/functions.tsv` (0 proprietaire sur les 44 declarants). La RVA
    se resout par le TOKEN via `Il2CppCodeGenModule.methodPointers`, et le corps se LIT :
    `b0 01 c3` (`mov al,1 ; ret`) = vrai, `32 c0 c3` (`xor al,al ; ret`) = faux. `BaseTriggeredAbility`
    rend FAUX (le defaut), et **surcharger ne veut PAS dire vrai** : sur les 43 surcharges, 4 rendent
    FAUX (`DevastatingRefrain_AttackAbility`, `MalleusRocketLauncher_AttackAbility`,
    `GazeOfMagnus_ApplyEngagementAbility`, `GazeOfMagnus_AttackAbility`). Un a priori
    « surcharge => vrai » aurait donc ecrit 4 valeurs fausses. Entree versionnee + cliquet :
    `data/symbols/<build>/metadata/allow_for_dead_owner.tsv`, `probe_10015_allow_for_dead_owner.py`.

    FACE EFFET -> **AUCUN gate d'owner**, et ce n'est pas une simplification du port :
    `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetEffectTrigger` et la branche EFFET
    d'`IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityOrEffectTrigger` commencent
    TOUTES DEUX par le MEME appel, dont le corps fait DEUX INSTRUCTIONS -- `mov al,1 ; ret`
    (`b0 01 c3`, corps DEDUPLIQUE par IL2CPP, 772 proprietaires dans la table ; le nom ghidra
    `UnityEngine.U2D.IK.Solver2D$$DoValidate` est celui d'un proprietaire ARBITRAIRE et ne dit RIEN
    de l'appelant). Ni `IsUnit` ni `IsAlive` n'y sont appeles. Le porteur est resolu par
    `EffectComponent+0x14`, puis pose TEL QUEL -- `null` compris -- dans l'`AbilityEntities` par
    `$$EvaluateEffectTriggerEffectAbilities`, qui ne le teste pas davantage.

    Ce que le port gardait sur cette face etait donc un SURPLUS a DEUX branches : porteur
    INTROUVABLE et porteur MORT. Les deux sont levees. Consequences directes :
      * la TUILE n'a plus a etre RECONNUE (`_owner_is_tile_entity`, #462-r4b-r1-r1-r1-r1-c-r1,
        n'avait plus de lecteur -- il conditionnait un gate qui n'existe plus sur cette face) ;
      * l'attribut `fire_on_death` d'un `EffectTrigger` est INERTE -- il compensait exactement ce
        surplus. Il reste porte sur `TriggeredAbility`, ou il mirrore
        `ITriggeredAbility.get_AllowForDeadOwner` (cf. ci-dessus).
        ⚠ La fiche du residu enumerait **4** classes nommees ; re-DERIVE le 2026-08-15 par
        `probe_10015_allow_for_dead_owner.py --inertie`, l'ensemble en compte **6**, et deux des
        quatre noms cites n'y sont plus seuls (`ArmourOfShriekingSoulsResurrectOnRemoved` et
        `FinalVengeanceUnitEffectTrigger` s'y sont ajoutees). Ne pas recopier une liste : la DERIVER
        (`getattr(cls, "fire_on_death", False)` sur `EFFECT_TRIGGERS`), sans quoi l'ensemble derive
        sous la citation, en silence -- ce qui vient de se produire.

    ⚠ **L'INERTIE EST STRUCTURELLE, PAS UNE OBSERVATION (#462-r4b-r1-r1-r1-r1-c-r3-r3).** Ce
    predicat est le SEUL lecteur de `fire_on_death` du depot (`engine/**` n'en a pas d'autre), et il
    rend FAUX pour tout `EffectTrigger` -- `TileEffectTrigger` compris, qui en DERIVE. Aucun chemin
    ne peut donc lire l'attribut sur une de ces 4 classes. Le cliquet qui garde ce fait le prouve par
    MORSURE, pas par lecture : `probe_10015_allow_for_dead_owner.py --inertie` remplace
    `fire_on_death` par une property qui LEVE, rejoue un dispatch sur chacune des 4 classes, et exige
    que rien ne leve ; le meme montage sur un `TriggeredAbility` DOIT lever, sinon le controle
    ne prouverait rien (un test qui ne mord d'aucun cote est vert par vacuite).
    Il n'est pas RETIRE : il documente `OwnerIsTarget` (le porteur EST le mourant) et son retrait ne
    changerait aucun comportement.

    `owner_is_global` : les abilities `IdunBattleLogic.Entities.Abilities.Damage.Loki.*` sont
    inscrites SANS owner (`owner_id is None`) -- il n'y a rien a gater."""
    return not (isinstance(entry, EffectTrigger) or getattr(entry, "owner_is_global", False))


def evaluate_trigger_operation(state: State, ev: TriggerEvent) -> list[dict]:
    """Mirror COLLAPSÉ du PUMP FIFO natif (#201) — `IdunBattle.Operations.EvaluateTriggerOperation$$ExecuteInternal`
    (dispatch) + `IdunBattle.Messages.InputMessageProcessor$$ProcessPendingTriggeredAbilities` (drain) + `IdunBattle.Messages.InputMessageProcessor$$RunPhase(PhaseType.ProcessPendingTriggeredAbilities /*0xf*/)`
    (item) + `IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths` (retrait-des-morts entre items), fondus en UNE boucle.

    Structure native (RE) :
      1. `ExecuteInternal` : itère le registre GLOBAL `AbilityAndEffectCache` (composant #3 = triggers de
         CET event) → `EvaluateAbilityOrEffectTrigger` par entrée → **ENFILE** un pending triggered-ability
         (file #5) — il n'EXÉCUTE PAS inline.
      2. `ProcessPendingTriggeredAbilities` : **SNAPSHOT** la file #5 dans une List + **`Queue.Clear`**, puis
         `foreach` item → `RunPhase(PhaseType.ProcessPendingTriggeredAbilities /*0xf*/, item)`. Chaque `RunPhase` = callback (le behaviour de l'item) PUIS
         `VerifyDeaths` PUIS `ProcessDamageEvents` PUIS `ProcessPendingTriggeredAbilities` (cascade imbriquée).
         => les morts causées par l'item N sont RETIRÉES avant l'item N+1.

    Collapse du port (équivalent observable, sans machinerie de file) :
      - `registry` = liste MATÉRIALISÉE une fois = le SNAPSHOT (mirror du snapshot+Clear : les effets/traits
        ajoutés PENDANT le drain n'entrent pas dans CE registre).
      - la boucle draine le snapshot en ordre FIFO ; le **re-appel de `matches` par item** (contre l'état
        COURANT) = la re-validation de cible du `RunPhase(PhaseType.ProcessPendingTriggeredAbilities /*0xf*/)` (un item tué par un item antérieur ne matche
        plus — cf. la leg target-validity `OverwatchAutoAttack.matches`, alive du mover).
      - les morts sont appliquées **INLINE** par `_fire_death_if_killed` (alive=False + `after_death_triggers`
        LIFO) DANS `execute_behaviour` = le `VerifyDeaths`-entre-items (la victime est morte avant l'entrée
        suivante). Équivalent au pump pour la cascade prouvée #201 (overwatch kill-cancel) ; une vraie file
        pending explicite (ordre snapshot-clear multi-rounds) n'ajoute AUCUN effet observable ici → non portée
        (blast-radius/ordre RNG) tant qu'aucune divergence ne l'exige.

    Gates par entrée : `event_id` écouté → gate d'owner **PAR FACE** (face ABILITY =
    `CanGetAbilityTrigger`, owner VIVANT sauf fire-on-death ; face EFFET = `CanGetEffectTrigger`,
    **aucun gate** — cf. le bloc ci-dessous) → cap-phase (`<0x33`, ability-triggers) → `matches` →
    behaviour. Renvoie la liste des résultats (diagnostic)."""
    out: list[dict] = []
    registry = (collect_triggered_abilities(state) + collect_global_triggers()
                + collect_effect_triggers(state))
    for entry in registry:
        # Un tile-effect écoute souvent PLUSIEURS events (`event_ids`) ; sinon `event_id` unique.
        if entry.event_id != ev.event_id and ev.event_id not in getattr(entry, "event_ids", ()):
            continue
        # GATE D'OWNER -- une branche PAR FACE (#462-r4b-r1-r1-r1-r1-c-r3, build `rnca9r7q6c`).
        if _owner_gate_applies(entry):
            # FACE ABILITY -- `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger`
            # place ses DEUX gates SOUS `EntityExtensions$$IsUnit(owner)` :
            #     if (!ability.get_AllowForDeadOwner()) {                    // ITriggeredAbility slot 8
            #         if (IsUnit(owner) && !IsAlive(owner))                              return 0; }
            #     if (IsUnit(owner) && IsTriggersDisabled(owner))                        return 0;
            # `fire_on_death` mirrore `get_AllowForDeadOwner` -- la propriete NOMMEE, dont la valeur
            # se LIT par classe (cf. `_owner_gate_applies`) ; ce n'est PAS `IsAtomic`, qui est une
            # autre propriete (`ITriggerable.get_AllowInAtomicMode`, gate non porte -- #10015-r1).
            # `IsTriggersDisabled` n'est pas porte (residu anterieur).
            owner = state.get_entity(entry.owner_id)
            if owner is None:
                # SURPLUS NOMME, et il reste : `IsUnit(null)` rend FAUX (LU -- le corps d'
                # `IdunBattle.Entities.EntityExtensions$$IsUnit` ouvre sur `if (entity == 0)
                # return 0`), donc le natif ne gaterait RIEN ici et passerait `owner = null`. Le
                # port refuse. Sans consequence observable, et c'est desormais MESURE plutot
                # qu'affirme (#462-r4b-r1-r1-r1-r1-c-r3-r2, re-mesure sur `t6dpr4k06g`) -- QUATRE
                # constats, chacun falsifiable :
                #   (a) AUCUN site d'`engine/**` ne retire d'entree de `state.entities` (0 occurrence
                #       de `entities.pop` / `del ....entities[` / `entities.clear()` / reaffectation) ;
                #   (b) `collect_triggered_abilities` n'instancie qu'en iterant `state.entities` ;
                #   (c) les DEUX classes de `GLOBAL_TRIGGERS` declarent bien `owner_is_global = True`
                #       -- sans quoi `state.get_entity(None)` tomberait ici et les tuerait en silence ;
                #   (d) `TileEffectTrigger` DERIVE d'`EffectTrigger`, donc `_owner_gate_applies` rend
                #       FAUX pour elle et ce bloc ne la voit jamais.
                # Le blocage de la fiche disait `porteur` : c'est FAUX, rien ne manque comme unite
                # confrontable -- le regime est inatteignable par la construction du modele d'etat du
                # port lui-meme. C'est justement ce qui garde ce `continue` : il rend la
                # DISCRIMINATION DE FACE attribuable (forcer le gate sur une entree d'effet la fait
                # tomber ici, et nulle part ailleurs).
                continue
            uc = owner.get_component(UnitComponent)
            if uc is not None and not uc.alive and not getattr(entry, "fire_on_death", False):
                continue
        if not entry.matches(state, ev):
            continue
        # #140 : CAP phase-triggers (mirror IdunBattle.Operations.EvaluateTriggerOperation$$EvaluateAbilityTrigger : GetTimesTriggeredThisPhase
        # < 0x33). S'applique aux ability-triggers (TriggeredAbility) — les effet-triggers passent par
        # EvaluateEffectTrigger (sans ce cap). Borne l'auto-récursion (splash Psyker qui re-déclenche le
        # splash Psyker via le vecteur after-hit). Clé = type d'ability-trigger (1 par trait-trigger).
        # `mark_as_triggered` AVANT le behaviour → la récursion voit le compteur incrémenté.
        # Le cap est PAR OWNER (`TriggeredAbilityComponent` de l'unité porteuse) -> il ne s'applique
        # ni aux tile-effects ni aux abilities GLOBALES (`owner_id is None`, aucun composant à porter).
        if (isinstance(entry, TriggeredAbility) and not getattr(entry, "owner_is_tile", False)
                and not getattr(entry, "owner_is_global", False)):
            tac = _trigger_phase_component(state, entry.owner_id)
            if tac is not None:
                pkey = type(entry).__name__
                tac.try_add(pkey)                                       # peuplement paresseux (idempotent)
                if tac.get_times_triggered_this_phase(pkey) >= PHASE_TRIGGER_CAP:
                    continue                                           # cap atteint cette phase → skip
                tac.mark_as_triggered(pkey)
        # `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` ecrit
        # `Nullable<AbilityOrEffect>(ability.Id)` dans le champ **`CurrentAbility`**
        # (`AbilityEntities+0x60`) **AVANT** d'executer le behaviour -> tout ce que le behaviour engendre
        # (attaque, degat, mort) porte cet id, et c'est lui que lit
        # `IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs`. C'est CE moment-la qui est mirrore
        # ici -- foyer UNIQUE du port. La sauvegarde/restauration reproduit l'imbrication native (une
        # triggered-ability declenchee DANS le behaviour d'une autre ecrase le champ pour SA duree, puis
        # rend la main) ; le natif ne fuit pas non plus d'une evaluation a la suivante, chaque
        # `EvaluateTriggerOperation` batissant son propre `AbilityEntities`.
        # ⚠ Le champ natif HOMONYME `TriggeringAbility` (`AbilityEntities+0x98`) est ecrit par la MEME
        # fonction mais **APRES** le behaviour, pour le seul `On(0xd = UnitTriggeredAbility)`. Le nom
        # du champ Python ci-dessous est historique ; sa semantique est celle de `CurrentAbility`
        # (case-292, `docs/rl/case-292-current-vs-triggering-ability.md`). Le SECOND canal (+0x98)
        # est `state.trigger_ability_type`, ecrit juste apres ce bloc (#294).
        prev_trig = getattr(state, "triggering_ability", None)
        if entry.TRIGGERED_ABILITY_ID is not None:
            state.triggering_ability = int(entry.TRIGGERED_ABILITY_ID)
        try:
            r = entry.execute_behaviour(state, ev)
        finally:
            state.triggering_ability = prev_trig
        if r is not None:
            out.append(r)
        _publish_unit_triggered_ability(state, ev, entry)
    return out


def _publish_unit_triggered_ability(state: State, ev: TriggerEvent, entry) -> None:
    """Queue de `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$Execute` — les DEUX gestes que
    le natif pose APRES le retour du behaviour, dans cet ordre (#294) :

        4. `AbilityOrEffect.op_Implicit(this)` -> `Nullable<>..ctor` -> ecrit `entities+0x98`
           (`TriggeringAbility`)
        5. copie de `entities` -> local
        6. `<processor>.Publish(<slot>, ..., 0xd, <la copie>)`
           = `On(0xd = EventTriggerType.UnitTriggeredAbility)`

    C'est le MOMENT D'ECRITURE qui separe `+0x98` de `+0x60`, pas la valeur : la MEME
    `AbilityOrEffect(this.Id)` part dans les deux. `+0x60` est pose AVANT le behaviour (donc herite
    par tout ce qu'il engendre) ; `+0x98` est pose APRES, donc il ne couvre QUE cet `On(0xd)`.

    Consequence, et c'est le regime discriminant : une triggered `B` declenchee PAR cet `On(0xd)`
    ecrit `+0x60 = B` avant SON behaviour, tandis que `+0x98` vaut toujours `A` -- le natif ne le
    reecrit qu'a la fin de `B`. `IdunBattle.Operations.EvaluateTriggerOperation$$PopulateAbilityEntities`
    ne touche ni `+0x60` ni `+0x98` (relu : il n'ecrit que `+0x40`, `+0x48`, `+0x50`), donc les deux
    champs TRAVERSENT l'evaluation imbriquee -> pendant le behaviour de `B`, les deux canaux portent
    DEUX VALEURS NON NULLES DIFFERENTES.

    RESTAURATION : le natif ecrit dans l'`AbilityEntities` de l'appelant (passe par reference) et le
    jette avec l'evaluation ; le port n'a qu'UN canal global, donc il restaure -- meme raisonnement
    et meme geste que pour `+0x60`. Le supprimer FAIT FUIR l'id d'une evaluation a la suivante
    (contre-epreuve `--mutate persist` de `probe_294_trigger_ability_channels.py`).

    EMISSION INCONDITIONNELLE : le natif publie `On(0xd)` a chaque execution de triggered-ability,
    sans gate. Le `TriggerEvent` reprend les champs de `ev` : le natif republie le MEME
    `AbilityEntities` (mute par le behaviour), pas un contexte neuf.

    ⚠ CET EVENEMENT N'A AUCUN CONSOMMATEUR CONNU -- ni porte, ni NATIF. Mesure #294, re-derivable :
    cote port, 86 classes-triggers enregistrees couvrent 37 `event_id` distincts et AUCUNE n'ecoute
    13 ; cote natif, le balayage des voies de construction d'un noeud d'evenement
    (`IdunBattleLogic.Entities.DSLTriggers$$On` et ses deux overloads, `$$OnDeathEvent`,
    `$$OnOwnerSpecificAbilityInit`, `$$OnNormalAttackOrSmite`, `$$OnAttackFromAbility`,
    `IdunBattle.Entities.Effects.BaseEffect$$On`) ne rend AUCUN `CreateTrigger` sur `0xd` -- a
    l'exception declaree de 4 `Env*Ability$$CreateTrigger` dont la liste d'events arrive par
    `RuntimeHelpers.InitializeArray` (blob non lisible depuis Ghidra ; abilities d'environnement,
    hors perimetre confrontable).
    L'emission reste portee malgre ca, pour deux raisons : (a) c'est le mirror -- le natif publie ;
    (b) sans elle le canal `+0x98` est INOBSERVABLE, donc invalidable, donc sans valeur.
    COUT MESURE : sur les 86 classes-triggers du registre, **7** declarent un `TRIGGERED_ABILITY_ID`
    -- les 79 autres sortent d'ici par le `return` ci-dessous. Bout-en-bout,
    `test_death_queue_ordering_live.py` (22 tests) rend 148,43 s AVANT et 147,07 s APRES : le
    surcout est dans le bruit."""
    if entry.TRIGGERED_ABILITY_ID is None:
        return                                          # aucun id a poser -> rien a publier
    # Acces DIRECT, pas `getattr(..., None)` : le slot est declare dans `State.__slots__` et
    # initialise par `State.__init__`. Un objet qui ne l'a pas n'est pas un `State` -> ca doit
    # LEVER, pas dégrader en `None` (un canal absent lu comme « vide » est exactement le mode de
    # panne silencieuse que ce cas documente).
    prev = state.trigger_ability_type
    state.trigger_ability_type = int(entry.TRIGGERED_ABILITY_ID)
    try:
        evaluate_trigger_operation(state, TriggerEvent(
            EventTriggerType.UnitTriggeredAbility, ev.actor_id, ev.target_id,
            ranged=ev.ranged, profile=ev.profile, is_crit=ev.is_crit,
            killer_id=ev.killer_id, dying_id=ev.dying_id, player_id=ev.player_id,
            overkill=ev.overkill, ability_type=ev.ability_type, profiles=ev.profiles,
            triggering_effect=ev.triggering_effect, is_first_hit=ev.is_first_hit,
            triggering_ability=ev.triggering_ability))
    finally:
        state.trigger_ability_type = prev


def _trigger_phase_component(state: State, owner_id: int) -> Optional[TriggeredAbilityComponent]:
    """Get-or-create le `TriggeredAbilityComponent` de l'unité `owner_id` (mirror du composant natif ;
    absent d'une unité spawnée avant #140 → créé paresseusement). None si l'entité n'existe pas."""
    e = state.get_entity(owner_id)
    if e is None:
        return None
    c = e.get_component(TriggeredAbilityComponent)
    if c is None:
        c = TriggeredAbilityComponent()
        e.add_component(c)
    return c
