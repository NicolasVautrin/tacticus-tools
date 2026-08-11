"""#306 -- MONTAGE NOMME : sur les vecteurs d'EFFET, quel canal `AbilityEntities` porte l'effet ?

    `CurrentAbility`    = `AbilityEntities+0x60` -> `ev.triggering_ability` / `state.triggering_ability`
    `TriggeringAbility` = `AbilityEntities+0x98` -> `ev.triggering_effect`  / `state.trigger_ability_type`

--------------------------------------------------------------------------- LE FAIT NATIF

Les DEUX Operations batissent un `AbilityEntities` NEUF par `memset(0, 0x128)` (= les 312 octets
boxes de `classes.tsv` moins l'en-tete 0x10) -- l'ambiant de l'appelant n'y survit donc PAS -- puis
remplissent, et ELLES NE REMPLISSENT PAS LES MEMES CHAMPS. Sequence LUE au decompile du build
`rnca9r7q6c`, controle negatif fait a l'assembleur :

  `IdunBattle.Operations.AddEffectOperation$$Execute`
      memset(0x128)
      `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor` -- ctor NOMME, donc le mapping
      parametre -> champ ne se deduit pas, il se LIT :
          caster: source -> +0x08 ; actor: source -> +0x00 ; target: owner -> +0x10 ; owner -> +0x18
          currentAbilityOrEffect: Nullable(AbilityOrEffect(effectType)) -> +0x60
          parentAbilityOrEffect:  Nullable VIDE                         -> +0x7c
          triggerAbilityOrEffect: Nullable(AbilityOrEffect(effectType)) -> +0x98
      Les DEUX Nullable viennent de DEUX appels distincts a `IdunBattle.Core.AbilityOrEffect$$
      op_Implicit` sur le MEME argument (l'asm montre `mov edx, edi` avant chacun, `edi` = le
      parametre `effectType` charge une fois) -> MEME valeur dans les deux champs.
      Publie ensuite, avec CETTE struct : `On(0x3d = 61 PreEffectAdded)`,
      `On(0x3e = 62 EffectAdded)`, `On(0x46 = 70 UnitBecameUntargetable)`.

  `IdunBattle.Operations.RemoveEffectOperation$$Execute`
      memset(0x128)
      **AUCUN ctor** -- quatre ecritures directes, et rien d'autre :
          +0x10 (`target`) = +0x18 (`owner`) = Entity(effectComponent.OwnerId @+0x14)
          +0x60..+0x7c (`currentAbilityOrEffect`) =
              Nullable(AbilityOrEffect(effectComponent.Type @+0x58))
      CONTROLE NEGATIF (asm, pas deduction) : entre le memset et la copie publiee, aucune ecriture
      ne touche +0x00 (`actor`), +0x08 (`caster`), +0x7c (`parent`) ni **+0x98** (`triggering`).
      Publie : `On(0x3f = 63 PreEffectRemoved)`, `On(0x40 = 64 EffectRemoved)`,
      `On(0x3b = 59 UnitBecameTargetable)`.

Les deux lecteurs sont des copies plates a offset FIXE -- il n'y a rien a deduire, seulement a lire :

    IdunBattleLogic.Entities.AbilityTypeSelector.CurrentAbilitySelector$$Select      lit +0x60/+0x68/+0x70/+0x78
    IdunBattleLogic.Entities.AbilityTypeSelector.TriggeringAbilitySelector$$Select   lit +0x98/+0xa0/+0xa8/+0xb0

et cote DSL, `IdunBattleLogic.Entities.DSLTriggers$$CurrentAbilityIs` prend le slot
`DSLSelectors+0x88`, tandis que `$$TriggeringAbilityIs`, `$$TriggeringEffectIs` et
`$$TriggeringAbilityIsNone` prennent TOUS LES TROIS `DSLSelectors+0x90`.

=> POSE   : `CurrentAbilityIs(effet)` ET `TriggeringEffectIs(effet)` sont VRAIS (meme valeur).
   RETRAIT: `TriggeringEffectIs` / `TriggeringAbilityIs` sont **TOUJOURS FAUX**,
            `TriggeringAbilityIsNone` est VRAI, et c'est **`CurrentAbilityIs` qui porte l'effet
            retire**.

------------------------------------------------------------------------- CE QUE LE PORT FAISAIT

`dispatch/move_death.py::pre_effect_added_triggers` posait le SEUL `triggering_effect` (`+0x98`) et
laissait `triggering_ability` (`+0x60`) a None -- alors que le natif ecrit les DEUX. Pire, il ne
touchait pas l'AMBIANT : une pose faite DANS le behaviour d'une triggered-ability laissait
`state.triggering_ability` = l'id de cette triggered, la ou le memset natif l'ECRASE par l'effet.
Cote retrait, aucun vecteur n'etait emis du tout : l'asymetrie etait litteralement inexprimable.

--------------------------------------------------------------------------- LE MONTAGE

Un `State` nu (OFFLINE, deterministe, zero RNG, zero runner), deux entites, `EffectsState` vide.
L'AMBIANT des deux canaux est arme AVANT (ce qu'une triggered englobante y aurait mis), puis :

    1. `AddEffectOperation.execute(state, source, target, EFFECT_TYPE)`  -> On(61 = PreEffectAdded)
    2. la feuille DSL `RemoveEffect(EFFECT_TYPE, Caster())`              -> On(63 = PreEffectRemoved) puis On(64 = EffectRemoved)

Trois espions dans le registre, chacun relevant le QUADRUPLET
`(payload +0x60, payload +0x98, ambiant +0x60, ambiant +0x98)` dans `matches` ET dans
`execute_behaviour`. Deroule NATIF attendu :

  | site        | ev +0x60 | ev +0x98 | st +0x60 | st +0x98 | etablit                        |
  |-------------|----------|----------|----------|----------|--------------------------------|
  | A.matches   | EFFECT   | EFFECT   | EFFECT   | EFFECT   | la POSE ecrit les DEUX         |
  | A.exec      | EFFECT   | EFFECT   | EFFECT   | EFFECT   | ... et ECRASE l'ambiant        |
  | R63.matches | EFFECT   | **None** | EFFECT   | **None** | le RETRAIT n'ecrit que +0x60   |
  | R63.exec    | EFFECT   | None     | EFFECT   | None     | idem cote behaviour            |
  | R64.matches | EFFECT   | None     | EFFECT   | None     | idem sur le 2e event           |
  | R64.exec    | EFFECT   | None     | EFFECT   | None     | idem                           |
  | final       |    -     |    -     | AMBIENT_C| AMBIENT_T| les deux canaux restaures      |

La SEPARATION recherchee n'est pas « deux non-nuls differents » (la pose met la MEME valeur des deux
cotes) : c'est **le retrait qui rend `+0x98` VIDE alors que `+0x60` porte l'effet**. C'est la seule
configuration ou un port qui confondrait les deux vecteurs est detectable.

--------------------------------------------------------------- CONTRE-EPREUVES (`--mutate`)

  `legacy`    l'etat AVANT #306 : la pose n'ecrit que `+0x98` et ne touche pas l'ambiant ; le
              retrait n'emet AUCUN vecteur -> R63/R64 jamais atteints
  `symmetric` le retrait ecrit `+0x98` comme la pose -> `TriggeringEffectIs` redevient satisfiable
              sur On(63 = PreEffectRemoved)/On(64 = EffectRemoved), ce que le memset natif interdit
  `noambient` payload correct mais AMBIANT non ecrase -> l'id d'une triggered englobante FUIT dans
              le vecteur d'effet (`CurrentAbilityIs(<la triggered>)` y deviendrait vrai)
  `persist`   pas de restauration -> l'effet FUIT apres le vecteur

Reproduire :

    cd scripts/python
    python probe_306_effect_trigger_channels.py
    python probe_306_effect_trigger_channels.py --mutate legacy
    python probe_306_effect_trigger_channels.py --mutate symmetric
    python probe_306_effect_trigger_channels.py --mutate noambient
    python probe_306_effect_trigger_channels.py --mutate persist
    python probe_306_effect_trigger_channels.py --add-only     # face POSE seule : tourne AUSSI
                                                               # sur le code d'AVANT le fix
"""
from __future__ import annotations

import argparse
from typing import Optional

# Type d'effet REEL (`Pinned`, 0x429) : c'est celui du seul consommateur porte de `On(61 = PreEffectAdded)`
# (`TerrifyingCrescendoAbility` branche 2). Les deux ambiants sont ARBITRAIRES et distincts entre
# eux et de l'effet -- le montage teste le CANAL, pas une ability reelle.
EFFECT_TYPE = 1065
AMBIENT_CURRENT = 6161      # ce qu'une triggered englobante a mis sur `+0x60`
AMBIENT_TRIGGER = 6262      # ... et sur `+0x98`
KILL_TRIGGER_NESTED = 6363  # le `killTrigger` du regime IMBRIQUE (pose d'effet dans le drain de mort)

MUTATIONS = ("legacy", "symmetric", "noambient", "persist")

# Sites du deroule complet, dans l'ordre d'evaluation attendu.
SITES_ADD = ("A.matches", "A.exec")
SITES_REMOVE = ("R63.matches", "R63.exec", "R64.matches", "R64.exec")


def _snapshot(state, ev) -> tuple:
    """`(payload +0x60, payload +0x98, ambiant +0x60, ambiant +0x98)` tels que les verrait un noeud
    DSL evalue ICI. Acces DIRECT aux slots de `State` : un objet qui ne les a pas n'est pas un
    `State`, et ca doit LEVER plutot que rendre un `None` qui se lirait « canal vide »."""
    return (ev.triggering_ability, ev.triggering_effect,
            state.triggering_ability, state.trigger_ability_type)


def _patched_effect_vector(mutate: Optional[str]):
    """Remplacant de `move_death._effect_vector_triggers` appliquant la mutation.

    On reecrit le FOYER ENTIER plutot que de patcher un attribut, parce que c'est precisement le
    quadruplet (ce qu'on pose sur `+0x60`/`+0x98`, en payload et en ambiant) qui est sous test."""
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.operations.triggers.dispatch.core import evaluate_trigger_operation

    def _vec(state, event_id, actor_id, target_id, effect_type, *, removing):
        et = int(effect_type)
        if mutate == "legacy" and removing:
            return []                       # AVANT #306 : aucun vecteur de retrait n'etait emis
        if mutate == "legacy":              # ... et la pose ne posait que `+0x98`, sans ambiant
            ev = TriggerEvent(int(event_id), actor_id if actor_id is not None else -1,
                              target_id if target_id is not None else -1,
                              ranged=False, profile=None, triggering_effect=et)
            return evaluate_trigger_operation(state, ev)
        plus98 = et if (mutate == "symmetric" or not removing) else None
        ev = TriggerEvent(int(event_id), actor_id if actor_id is not None else -1,
                          target_id if target_id is not None else -1,
                          ranged=False, profile=None,
                          triggering_ability=et, triggering_effect=plus98)
        prev_current = state.triggering_ability
        prev_trigger = state.trigger_ability_type
        if mutate != "noambient":
            state.triggering_ability = et
            state.trigger_ability_type = plus98
        try:
            return evaluate_trigger_operation(state, ev)
        finally:
            if mutate != "persist":
                state.triggering_ability = prev_current
                state.trigger_ability_type = prev_trigger
    return _vec


def run(mutate: Optional[str] = None, verbose: bool = False, add_only: bool = False) -> dict:
    """Monte la POSE (et, sauf `--add-only`, le RETRAIT) et rend la TRACE ordonnee des observations.

    Sans `--mutate`, AUCUNE substitution n'est installee : le montage exerce le foyer DU DEPOT
    (`AddEffectOperation.execute` reel, feuille DSL `RemoveEffect` reelle). C'est ce mode qui donne
    son ROUGE au fix.

    `add_only=True` n'exerce QUE la face POSE et n'importe AUCUN des vecteurs de retrait -> le
    module reste executable sur le code d'AVANT #306, ou ces vecteurs n'existent pas.

    Retour :
      `obs`     liste de `(site, ev+0x60, ev+0x98, st+0x60, st+0x98)` dans l'ordre d'evaluation
      `final`   `(st+0x60, st+0x98)` apres retour complet
      `removed` nb de stacks retires par la feuille `RemoveEffect` (0 en `--add-only`)
    """
    assert mutate in (None,) + MUTATIONS, "mutation inconnue : %s" % (mutate,)
    from engine.runner.state import State
    from engine.runner.components import UnitComponent, OwnerComponent
    from engine.runner.operations.triggers.base import TriggeredAbility
    from engine.runner.operations.effects import AddEffectOperation
    from engine.entities.effects_state import EffectsState
    from engine.dsl.event_trigger_type import EventTriggerType
    import engine.runner.operations.triggers.dispatch.core as CORE
    import engine.runner.operations.triggers.dispatch.move_death as MD

    obs: list[tuple] = []

    def _spy(tag: str, event_id: int):
        """Fabrique un observateur PUR (aucun `TRIGGERED_ABILITY_ID`, comme la grande majorite des
        classes du registre) : il ne touche aucun canal, il ne fait que LIRE ce que l'Operation a
        publie."""
        class _S(TriggeredAbility):
            pass
        _S.event_id = int(event_id)

        def matches(self, state, ev):
            obs.append(("%s.matches" % tag,) + _snapshot(state, ev))
            return True

        def execute_behaviour(self, state, ev):
            obs.append(("%s.exec" % tag,) + _snapshot(state, ev))
            return {"who": tag}
        _S.matches = matches
        _S.execute_behaviour = execute_behaviour
        _S.__name__ = "_Spy%s" % tag.replace(".", "")
        return _S

    spies = [_spy("A", EventTriggerType.PreEffectAdded)]
    if not add_only:
        spies += [_spy("R63", EventTriggerType.PreEffectRemoved),
                  _spy("R64", EventTriggerType.EffectRemoved)]

    state = State()
    # Deux entites VIVANTES : la source de l'effet et son porteur. Le gate d'owner de
    # `evaluate_trigger_operation` impose un porteur vivant -> les espions sont sur le porteur.
    src = state.add_entity(1)
    src.add_component(UnitComponent("probe306Source", True))
    src.add_component(OwnerComponent(team=1))
    tgt = state.add_entity(2)
    tgt.add_component(UnitComponent("probe306Holder", True))
    tgt.add_component(OwnerComponent(team=2))
    state.effects = EffectsState()

    saved_collect = CORE.collect_triggered_abilities
    CORE.collect_triggered_abilities = lambda st: [cls(2) for cls in spies]
    saved_vec = getattr(MD, "_effect_vector_triggers", None)
    if mutate is not None:
        MD._effect_vector_triggers = _patched_effect_vector(mutate)
    removed = 0
    try:
        # L'AMBIANT hors vecteur : ce que les deux canaux valent AVANT (une triggered englobante).
        state.triggering_ability = AMBIENT_CURRENT
        state.trigger_ability_type = AMBIENT_TRIGGER
        AddEffectOperation.execute(state, 1, 2, EFFECT_TYPE, name="Pinned")
        if not add_only:
            from engine.runner.abilities.behaviours.effects import RemoveEffect
            from engine.runner.abilities.behaviours.context import entities_from_state
            from engine.entities.selectors.tiles import Caster
            from engine.dsl.effects import ExecutionContext
            ectx = ExecutionContext(state=state, rng=None)
            RemoveEffect(EFFECT_TYPE, Caster()).execute(entities_from_state(state, 2, 2), ectx)
            removed = sum(p.get("removed", 0) for n, p in ectx.emitted if n == "RemoveEffect")
        final = (state.triggering_ability, state.trigger_ability_type)
    finally:
        CORE.collect_triggered_abilities = saved_collect
        if mutate is not None and saved_vec is not None:
            MD._effect_vector_triggers = saved_vec

    res = {"obs": obs, "final": final, "removed": removed,
           "mutate": mutate, "add_only": add_only}
    if verbose:
        print("site          ev+0x60  ev+0x98  st+0x60  st+0x98")
        for row in obs:
            print("%-13s %-8s %-8s %-8s %s" % row)
        print("%-13s %-8s %-8s %-8s %s" % ("final", "-", "-", final[0], final[1]))
        print("stacks retires par la feuille RemoveEffect : %d" % removed)
    return res


def site(res: dict, name: str) -> tuple:
    """La PREMIERE observation `(ev+0x60, ev+0x98, st+0x60, st+0x98)` faite au site `name`. Leve si
    le site n'a pas ete atteint -- un site absent est un montage qui ne s'est pas monte, jamais un
    « rien a signaler »."""
    for row in res["obs"]:
        if row[0] == name:
            return row[1:]
    raise AssertionError("site '%s' non atteint ; sites observes = %s"
                         % (name, sorted({r[0] for r in res["obs"]})))


def verdict(res: dict) -> tuple:
    """(ok, message). Les faits que le montage doit etablir, chacun nomme et teste dans un ordre
    qui donne a chaque contre-epreuve une signature PROPRE."""
    by_site: dict[str, list] = {}
    for row in res["obs"]:
        by_site.setdefault(row[0], []).append(tuple(row[1:]))
    expected = SITES_ADD if res["add_only"] else SITES_ADD + SITES_REMOVE
    # 1 : les vecteurs sont EMIS. Un site manquant = le vecteur n'existe pas cote port.
    for s in expected:
        if s not in by_site:
            return (False, "ROUGE -- site '%s' non atteint ; sites observes = %s "
                           "(le vecteur n'est pas emis par le port)" % (s, sorted(by_site)))
    # 2 : POSE -- le ctor ecrit `currentAbilityOrEffect` (+0x60) ET `triggerAbilityOrEffect`
    #     (+0x98) avec le MEME `AbilityOrEffect(effectType)`.
    for s in SITES_ADD:
        ev60, ev98, _, _ = by_site[s][0]
        if (ev60, ev98) != (EFFECT_TYPE, EFFECT_TYPE):
            return (False, "ROUGE -- '%s' voit (ev+0x60, ev+0x98) = (%s, %s) ; la POSE ecrit les "
                           "DEUX avec AbilityOrEffect(%s)" % (s, ev60, ev98, EFFECT_TYPE))
    # 3 : POSE -- le memset ECRASE l'ambiant sur les deux canaux (une triggered englobante ne fuit
    #     PAS dans le vecteur d'effet).
    for s in SITES_ADD:
        _, _, st60, st98 = by_site[s][0]
        if (st60, st98) != (EFFECT_TYPE, EFFECT_TYPE):
            return (False, "ROUGE -- '%s' voit (st+0x60, st+0x98) = (%s, %s) ; le memset de "
                           "AddEffectOperation ECRASE l'ambiant (%s, %s) par l'effet %s"
                    % (s, st60, st98, AMBIENT_CURRENT, AMBIENT_TRIGGER, EFFECT_TYPE))
    if not res["add_only"]:
        # 4 : RETRAIT -- `+0x98` VIDE (le memset non suivi d'ecriture), `+0x60` = l'effet retire.
        for s in SITES_REMOVE:
            ev60, ev98, st60, st98 = by_site[s][0]
            if ev98 is not None or st98 is not None:
                return (False, "ROUGE -- '%s' voit +0x98 = (%s, %s) ; RemoveEffectOperation ne "
                               "l'ecrit JAMAIS -> attendu VIDE des deux cotes" % (s, ev98, st98))
            if (ev60, st60) != (EFFECT_TYPE, EFFECT_TYPE):
                return (False, "ROUGE -- '%s' voit +0x60 = (%s, %s) ; c'est CurrentAbilityIs qui "
                               "porte l'effet retire (%s)" % (s, ev60, st60, EFFECT_TYPE))
        # 5 : la feuille a bien retire un stack (sinon les vecteurs seraient partis a vide).
        if res["removed"] < 1:
            return (False, "ROUGE -- aucun stack retire ; le montage n'a pas exerce le retrait")
    # 6 : restauration des DEUX canaux (le natif jette son `AbilityEntities` avec l'operation).
    if res["final"] != (AMBIENT_CURRENT, AMBIENT_TRIGGER):
        return (False, "ROUGE -- final = %s ; attendu (%s, %s) : les deux canaux doivent revenir a "
                       "leur valeur d'avant le vecteur"
                % (res["final"], AMBIENT_CURRENT, AMBIENT_TRIGGER))
    return (True, "VERT -- pose : +0x60 = +0x98 = effet et ambiant ecrase ; retrait : +0x60 = effet "
                  "et +0x98 VIDE ; les deux canaux restaures")


def run_nested(verbose: bool = False) -> dict:
    """GENERALISATION -- une pose d'effet IMBRIQUEE dans le drain de mort.

    Regime ATTEIGNABLE (un trigger de mort qui pose un effet : c'est la forme d'`ActOfFaith`
    accumulate) et le seul ou l'ambiant d'entree n'est PAS celui d'une triggered ordinaire :
    `operations/damage.py::_verify_deaths` a deja pose `(+0x60, +0x98) = (None, killTrigger)` --
    le mirror du memset de `IdunBattle.Operations.KillUnitOperation$$Execute` (#301).

    Ce que le natif fait : `AddEffectOperation` batit son PROPRE `AbilityEntities` (memset + ctor),
    donc le vecteur d'effet publie `(effectType, effectType)` -- il n'HERITE RIEN du contexte de
    mort -- et le `KillUnitOperation` en cours garde le sien intact.

    Ce que le port faisait AVANT #306 : la pose ne touchait aucun canal, donc les triggers de
    `On(61 = PreEffectAdded)` y voyaient `(None, killTrigger)` -- le contexte de MORT, publie sous un evenement
    d'EFFET. C'est le regime ou le fix change le plus, et il n'est couvert par aucun test existant.

    Retour : `during` = `(payload +0x60, payload +0x98, ambiant +0x60, ambiant +0x98)` vu par le
    trigger de `On(61 = PreEffectAdded)` ; `restored` = les deux canaux JUSTE APRES le vecteur, toujours dans le
    drain (ils doivent etre revenus au contexte de mort)."""
    from engine.runner.state import State
    from engine.runner.components import UnitComponent, OwnerComponent
    from engine.runner.operations.triggers.base import TriggeredAbility
    from engine.runner.operations.effects import AddEffectOperation
    from engine.entities.effects_state import EffectsState
    from engine.dsl.event_trigger_type import EventTriggerType
    import engine.runner.operations.triggers.dispatch.core as CORE

    seen: dict = {}

    class _Death(TriggeredAbility):
        """Trigger de MORT qui POSE un effet dans son behaviour (forme d'ActOfFaith accumulate)."""
        event_id = int(EventTriggerType.PreUnitDeath)
        fire_on_death = True

        def matches(self, state, ev):
            return True

        def execute_behaviour(self, state, ev):
            seen["at_death"] = (state.triggering_ability, state.trigger_ability_type)
            AddEffectOperation.execute(state, 2, 2, EFFECT_TYPE, name="Pinned")
            seen["restored"] = (state.triggering_ability, state.trigger_ability_type)
            return {"who": "death"}

    class _OnAdd(TriggeredAbility):
        """Observateur PUR du vecteur de POSE imbrique."""
        event_id = int(EventTriggerType.PreEffectAdded)

        def matches(self, state, ev):
            seen.setdefault("during", (ev.triggering_ability, ev.triggering_effect,
                                       state.triggering_ability, state.trigger_ability_type))
            return False
        # pas de behaviour : `matches` False suffit a relever les canaux

    state = State()
    dying = state.add_entity(1)
    dying.add_component(UnitComponent("probe306Dying", False))
    dying.add_component(OwnerComponent(team=2))
    killer = state.add_entity(2)
    killer.add_component(UnitComponent("probe306Killer", True))
    killer.add_component(OwnerComponent(team=1))
    state.effects = EffectsState()

    saved = CORE.collect_triggered_abilities
    CORE.collect_triggered_abilities = lambda st: [_Death(2), _OnAdd(2)]
    try:
        from engine.runner.operations.damage import AttackDamageOperation
        state.triggering_ability = AMBIENT_CURRENT
        state.pending_deaths.append((1, 2, False, KILL_TRIGGER_NESTED))
        AttackDamageOperation._verify_deaths(state)
        final = (state.triggering_ability, state.trigger_ability_type)
    finally:
        CORE.collect_triggered_abilities = saved

    res = {"at_death": seen.get("at_death"), "during": seen.get("during"),
           "restored": seen.get("restored"), "final": final}
    if verbose:
        print("contexte de MORT vu par le trigger      : %s" % (res["at_death"],))
        print("canaux vus par On(61 = PreEffectAdded) IMBRIQUE          : %s" % (res["during"],))
        print("canaux JUSTE APRES le vecteur (in drain): %s" % (res["restored"],))
        print("canaux apres le drain complet           : %s" % (res["final"],))
    return res


def verdict_nested(res: dict) -> tuple:
    """(ok, message) du regime imbrique."""
    if res["at_death"] is None or res["during"] is None:
        return (False, "ROUGE -- montage non monte : at_death=%s during=%s"
                % (res["at_death"], res["during"]))
    # 1 : le contexte de MORT est bien celui de #301 (sinon on ne teste pas l'imbrication voulue).
    if res["at_death"] != (None, KILL_TRIGGER_NESTED):
        return (False, "ROUGE -- contexte de mort = %s ; attendu (None, %s) : le montage n'exerce "
                       "pas le regime imbrique" % (res["at_death"], KILL_TRIGGER_NESTED))
    # 2 : le vecteur d'effet NE PORTE PAS le contexte de mort -- il a son propre memset+ctor.
    if res["during"] != (EFFECT_TYPE, EFFECT_TYPE, EFFECT_TYPE, EFFECT_TYPE):
        return (False, "ROUGE -- On(61 = PreEffectAdded) imbrique voit %s ; attendu (%s, %s, %s, %s) : "
                       "AddEffectOperation batit son PROPRE AbilityEntities, il n'herite rien du "
                       "KillUnitOperation en cours"
                % ((res["during"],) + (EFFECT_TYPE,) * 4))
    # 3 : le contexte de mort est RENDU intact au drain qui continue.
    if res["restored"] != (None, KILL_TRIGGER_NESTED):
        return (False, "ROUGE -- apres le vecteur d'effet, le drain voit %s ; attendu (None, %s) : "
                       "l'AbilityEntities du KillUnitOperation n'est pas touche par l'AddEffect"
                % (res["restored"], KILL_TRIGGER_NESTED))
    # 4 : sortie du drain -> l'ambiant d'avant la mort.
    if res["final"] != (AMBIENT_CURRENT, None):
        return (False, "ROUGE -- final = %s ; attendu (%s, None)" % (res["final"], AMBIENT_CURRENT))
    return (True, "VERT -- le vecteur d'effet imbrique publie l'EFFET sur les deux canaux et rend "
                  "le contexte de mort intact")


def consumers(verbose: bool = True) -> dict:
    """POURQUOI CE FIX EST LATENT -- le compte RE-DERIVE (jamais herite) des classes du registre
    porte qui ecoutent chacun des SIX evenements d'effet natifs.

    Le fix corrige un CANAL, pas un comportement : tant qu'aucune classe portee ne lit
    `CurrentAbilityIs` sur un vecteur d'effet, aucune observable de bataille ne bouge. Ce compte est
    ce qui l'ATTESTE -- et il est aussi le declencheur : le jour ou il passe a non-zero sur un
    vecteur de RETRAIT, le canal lu devient decisif.

    Rend `{event_id: [noms de classes]}` pour les six events, plus `readers` = les classes portees
    qui lisent l'un ou l'autre canal via le payload de l'evenement."""
    from engine.dsl.event_trigger_type import EventTriggerType
    from engine.runner.operations.triggers.dispatch.registry import (
        TRAIT_TRIGGERS, ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS, EFFECT_TRIGGERS,
        GLOBAL_TRIGGERS)

    seen: dict = {}
    for reg in (TRAIT_TRIGGERS, ABILITY_TRIGGERS, ACTIVE_ABILITY_TRIGGERS, EFFECT_TRIGGERS):
        for classes in reg.values():
            for cls in classes:
                seen[cls.__name__] = cls
    for cls in GLOBAL_TRIGGERS:
        seen[cls.__name__] = cls

    events = {
        int(EventTriggerType.UnitBecameTargetable): "59 UnitBecameTargetable (REMOVE)",
        int(EventTriggerType.PreEffectAdded): "61 PreEffectAdded (ADD)",
        int(EventTriggerType.EffectAdded): "62 EffectAdded (ADD)",
        int(EventTriggerType.PreEffectRemoved): "63 PreEffectRemoved (REMOVE)",
        int(EventTriggerType.EffectRemoved): "64 EffectRemoved (REMOVE)",
        int(EventTriggerType.UnitBecameUntargetable): "70 UnitBecameUntargetable (ADD)",
    }
    by_event: dict = {e: [] for e in events}
    for name, cls in seen.items():
        ids = set(int(x) for x in getattr(cls, "event_ids", ()) or ())
        if getattr(cls, "event_id", -1) is not None:
            ids.add(int(getattr(cls, "event_id", -1)))
        for e in events:
            if e in ids:
                by_event[e].append(name)
    # `_classes` : le nom ne suffit pas a MESURER un consommateur -- `verdict_canal_retrait` doit
    # l'instancier pour lire son `matches`. Sans ce canal, la seule verification possible serait un
    # grep de source, qui ne voit ni les `getattr` ni les lectures faites dans une classe de base.
    res = {"registry_size": len(seen), "by_event": by_event, "labels": events, "_classes": seen}
    if verbose:
        print("classes-triggers portees au registre : %d" % len(seen))
        for e, label in events.items():
            names = sorted(by_event[e])
            print("  On(%-3d) %-34s : %d  %s" % (e, label, len(names), names or ""))
    return res


#: Les trois vecteurs qu'`IdunBattle.Operations.RemoveEffectOperation$$Execute` publie. Sur eux
#: `+0x98` n'est JAMAIS ecrit (controle negatif a l'assembleur, cf. l'en-tete) -> un gate
#: `TriggeringEffectIs` y serait TOUJOURS faux, et c'est `CurrentAbilityIs` (`+0x60`) qui porte
#: l'effet retire.
VECTEURS_RETRAIT = ("PreEffectRemoved", "EffectRemoved", "UnitBecameTargetable")
#: Valeur ARBITRAIRE promenee dans les deux canaux. Elle ne sert qu'a rendre la lecture OBSERVABLE :
#: un `matches` lit son canal que la comparaison reussisse ou non.
_SONDE = 1035


def _event_tracant(journal: set, *args, **kw):
    """Un `TriggerEvent` qui NOTE quel canal on lui demande.

    C'est une MESURE, pas un grep : le canal effectivement lu se constate a l'execution du vrai
    `matches`, a travers les helpers, les `getattr` et les classes de base. Un balayage de source
    ne verrait ni `getattr(ev, "triggering_ability", None)` ni une lecture faite dans une methode
    heritee."""
    from engine.runner.operations.triggers.base import TriggerEvent

    class _Ev(TriggerEvent):
        __slots__ = ()

        def __getattribute__(self, nom):
            if nom in ("triggering_ability", "triggering_effect"):
                journal.add(nom)
            return TriggerEvent.__getattribute__(self, nom)
    return _Ev(*args, **kw)


def canaux_lus(cls, event_id: int, owner_id: int = 2) -> dict:
    """Quels canaux le `matches` de `cls` LIT-il sur ce vecteur, et par lequel est-il SATISFAIT ?

    Le `matches` d'un trigger commence par des gates de position (`OwnerIsActor` / `OwnerIsTarget`,
    porteur vivant) : une seule configuration d'evenement n'atteindrait pas forcement la lecture du
    canal. On BALAYE donc les placements du porteur (acteur, cible, les deux) et les trois formes de
    payload, et on rend l'UNION -- une union ne peut que SUR-estimer les lectures, jamais en manquer
    une, donc le critere qui s'appuie dessus ne peut pas rendre un faux VERT.

    Rend `{"lus": set, "vrai_par": set, "atteint": bool, "erreurs": [str]}` :
      * `lus`       -- les canaux dont la valeur a ete DEMANDEE ;
      * `vrai_par`  -- les formes de payload sur lesquelles `matches` a rendu VRAI. `natif` = la
                       forme que `RemoveEffectOperation` publie reellement (`+0x60` seul) ;
                       `inverse` = `+0x98` seul, une forme que le natif NE PRODUIT JAMAIS sur ce
                       vecteur : y etre VRAI, c'est lire le mauvais canal ;
      * `atteint`   -- au moins un `matches` s'est evalue sans lever. FAUX = montage insuffisant
                       pour cette classe, PAS un vice : il faut le DIRE, pas le compter vert.
    """
    from engine.runner.state import State
    from engine.runner.components import UnitComponent, OwnerComponent
    from engine.entities.effects_state import EffectsState

    state = State()
    for eid, team in ((owner_id, 1), (owner_id + 1, 1), (owner_id + 2, 2)):
        e = state.add_entity(eid)
        e.add_component(UnitComponent("probe306Unit%d" % eid, True))
        e.add_component(OwnerComponent(team=team))
    state.effects = EffectsState()

    formes = {"natif": (_SONDE, None), "inverse": (None, _SONDE), "pose": (_SONDE, _SONDE)}
    lus: set = set()
    vrai_par: set = set()
    erreurs: list = []
    atteint = False
    try:
        trig = cls(owner_id)
    except Exception as exc:                      # noqa: BLE001 -- un ctor exigeant est un MONTAGE
        return {"lus": lus, "vrai_par": vrai_par, "atteint": False,
                "erreurs": ["ctor(%s) : %s" % (owner_id, exc)]}
    autre = owner_id + 2
    for actor, target in ((owner_id, autre), (autre, owner_id), (owner_id, owner_id)):
        for nom, (ta, te) in formes.items():
            ev = _event_tracant(lus, int(event_id), actor, target, ranged=False, profile=None,
                                triggering_ability=ta, triggering_effect=te)
            try:
                ok = trig.matches(state, ev)
            except Exception as exc:              # noqa: BLE001 -- montage, jamais un verdict
                erreurs.append("%s/%s/%s : %s" % (actor, target, nom, exc))
                continue
            atteint = True
            if ok:
                vrai_par.add(nom)
    return {"lus": lus, "vrai_par": vrai_par, "atteint": atteint, "erreurs": erreurs}


def verdict_canal_retrait(verbose: bool = True) -> tuple:
    """(ok, message, details) -- les consommateurs de vecteurs de RETRAIT lisent-ils `+0x60` ?

    CE N'EST PAS UNE INTERDICTION. Un consommateur de vecteur de retrait est parfaitement legitime
    (`WrathfulDevotionAbility` en est un, LU : `On(UnitBecameTargetable) & get_OwnerIsTarget &
    CurrentAbilityIs(AbilityOrEffect((EffectType)0x40b))`). Ce qui ne l'est pas, c'est d'y lire le
    canal `+0x98` que `RemoveEffectOperation` laisse VIDE : le gate serait alors TOUJOURS faux cote
    natif, donc l'ability serait morte -- ou, cote port, vraie sur un canal que le natif ne remplit
    pas.

    DEUX faits par consommateur, et le second existe parce que le premier ne suffit pas :
      1. il n'est jamais VRAI sur la forme `inverse` (`+0x98` seul) -- c'est le vice ;
      2. s'il lit `triggering_effect`, il doit AUSSI lire `triggering_ability` -- une classe qui ne
         lirait QUE `+0x98` sur un vecteur de retrait est morte a coup sur.
    """
    from engine.dsl.event_trigger_type import EventTriggerType

    c = consumers(verbose=False)
    details: list = []
    fautes: list = []
    for nom_ev in VECTEURS_RETRAIT:
        eid = int(getattr(EventTriggerType, nom_ev))
        for nom_cls in sorted(c["by_event"][eid]):
            cls = c["_classes"][nom_cls]
            m = canaux_lus(cls, eid)
            details.append((nom_ev, nom_cls, m))
            if "inverse" in m["vrai_par"]:
                fautes.append("%s sur On(%d = %s) est VRAI sur la forme `inverse` (+0x98 seul) : "
                              "il lit `TriggeringEffectIs` la ou RemoveEffectOperation laisse "
                              "+0x98 VIDE -- il doit lire `CurrentAbilityIs` "
                              "(`ev.triggering_ability`)" % (nom_cls, eid, nom_ev))
            elif "triggering_effect" in m["lus"] and "triggering_ability" not in m["lus"]:
                fautes.append("%s sur On(%d = %s) ne lit QUE `+0x98` : ce canal est structurellement "
                              "VIDE sur un vecteur de retrait, donc le gate est mort"
                              % (nom_cls, eid, nom_ev))
    if verbose:
        for (nom_ev, nom_cls, m) in details:
            print("  %-22s %-38s lus=%s vrai_par=%s%s"
                  % (nom_ev, nom_cls, sorted(m["lus"]) or "-", sorted(m["vrai_par"]) or "-",
                     "" if m["atteint"] else "  [NON ATTEINT : montage insuffisant]"))
        if not details:
            print("  aucun consommateur porte sur les trois vecteurs de RETRAIT")
    if fautes:
        return (False, "ROUGE -- " + " | ".join(fautes), details)
    return (True, "VERT -- %d consommateur(s) de vecteur de RETRAIT, tous sur `+0x60`"
            % len(details), details)


def main() -> int:
    ap = argparse.ArgumentParser(description="#306 : canaux d'ability des vecteurs d'EFFET")
    ap.add_argument("--mutate", choices=MUTATIONS, default=None)
    ap.add_argument("--add-only", action="store_true",
                    help="face POSE seule (executable sur le code d'AVANT #306)")
    ap.add_argument("--consumers", action="store_true",
                    help="compte re-derive des consommateurs portes par vecteur d'effet")
    ap.add_argument("--nested", action="store_true",
                    help="GENERALISATION : pose d'effet IMBRIQUEE dans le drain de mort")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.consumers:
        consumers(verbose=True)
        return 0
    if a.nested:
        r = run_nested(verbose=not a.quiet)
        ok, msg = verdict_nested(r)
        print("[306-nested] %s" % msg)
        return 0 if ok else 1
    res = run(a.mutate, verbose=not a.quiet, add_only=a.add_only)
    ok, msg = verdict(res)
    print("[306] mutate=%s add_only=%s : %s" % (a.mutate or "-", a.add_only, msg))
    if a.mutate is None:
        return 0 if ok else 1
    # Une contre-epreuve DOIT rougir : un vert y est l'echec.
    if ok:
        print("[306] ANTI-CONTRE-EPREUVE : la mutation '%s' n'a RIEN casse -- "
              "le montage ne discrimine pas." % a.mutate)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
