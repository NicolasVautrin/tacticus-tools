"""#443-r2-b2 -- l'emetteur d'`On(0x11 = PostDamageTaken)` : la file, son drain, son RANG.

GARDE OFFLINE, six etages. Chacun a ete VU ROUGE par mutation avant d'etre livre :

  1. `test_..._enqueue_et_ses_gardes`  -- `AddDamageEvent` : cible NULLE = pas d'`Enqueue`,
                                          caster nul = accepte (les DEUX gardes sont LUS) ;
  2. `test_..._snapshot_puis_clear`    -- l'ordre, et les VAGUES qu'il implique ;
  3. `test_..._reentrance`             -- le garde `draining_damage_events` ;
  4. `test_..._le_chokepoint_enfile`   -- le site d'enfilement est ADJACENT a `On(0xf)` (AST) ;
  5. `test_..._rang_avant_les_differees` -- `ProcessDamageEvents` PRECEDE le drain des differees ;
  6. `test_..._consommateurs`          -- les TROIS classes qui l'ecoutaient a vide sont atteintes.

⚠ Ce que ce fichier NE garde PAS : `skipDamageEventTrigger` (argument d'APPELANT, aucun site du
port ne le pose -- residu nomme dans `damage.py`), ni le SECOND couple
`ProcessDamageEvents`/`ProcessPendingTriggeredAbilities` du bloc de fin de tour (meme residu, deja
nomme, que le second drain des differees).
"""
from __future__ import annotations

import ast
import os

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/damage_events.py",
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/runner.py",
        "scripts/python/engine/runner/state.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/loki/reactivate_overwatch.py",
    ),
    "build": True,            # `EventTriggerType` est per-build
    "toujours": False,
    "raison": ("garde l'emetteur d'On(0x11 = PostDamageTaken) : les gardes de l'Enqueue, le "
               "snapshot-puis-clear et ses vagues, la re-entrance, l'adjacence du site "
               "d'enfilement a On(0xf), le rang du drain avant celui des triggered-abilities "
               "differees, et l'atteinte des trois consommateurs"),
}

import pytest                                                                    # noqa: E402

from engine.dsl.event_trigger_type import EventTriggerType                       # noqa: E402
from engine.runner.operations.triggers.dispatch import damage_events as DE       # noqa: E402
from engine.runner.state import State                                            # noqa: E402

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))                       # .../scripts/python
_DAMAGE = os.path.join(_PY, "engine", "runner", "operations", "damage.py")
_RUNNER = os.path.join(_PY, "engine", "runner", "runner.py")


# ------------------------------ [1] LES DEUX GARDES DE L'ENQUEUE ------------------------------
def test_443r2b2_enqueue_et_ses_gardes():
    """`IdunBattle.Core.MatchState$$AddDamageEvent(source, caster, target)` -- les DEUX gardes sont
    LUS, et ils ne sont PAS symetriques :
      * `if (caster != null) item.casterId = caster.Id;`  -> caster NUL = champ a zero, ENQUEUE ;
      * `if (target != null) { ... Queue.Enqueue(item); }` -> cible NULLE = **PAS d'Enqueue**.
    Les confondre ferait soit perdre des events (refus sur caster nul), soit en fabriquer sur une
    cible inexistante."""
    st = State()
    assert st.pending_damage_events == []
    DE.add_damage_event(st, 1148, 5, 7)
    DE.add_damage_event(st, None, None, 9)          # caster NUL -> accepte
    DE.add_damage_event(st, 1, 2, None)             # cible NULLE -> refuse
    assert st.pending_damage_events == [(1148, 5, 7), (None, None, 9)]
    DE.add_damage_event(None, 1, 2, 3)              # state absent -> no-op, aucune exception


# --------------------- [2] SNAPSHOT PUIS CLEAR, ET LES VAGUES QUE CA IMPLIQUE ------------------
def test_443r2b2_snapshot_puis_clear_et_vagues(monkeypatch):
    """`snapshot = new List<T>(q) ; q.Clear()` -- dans CET ordre. Consequence LUE : un event enfile
    PENDANT le drain n'est pas vu par CETTE vague, mais par la SUIVANTE (le natif rattrape par le
    `RunPhase(0xe, isInternalPhase: 1)` qui re-draine).

    LE VICE QUE CE TEST GARDE : un drain en FIFO plat (qui verrait l'event ré-enfilé dans la meme
    passe) OU un drain qui le perdrait (clear APRES l'iteration)."""
    st = State()
    vagues: list = []
    reenfile = {"fait": False}

    def _fake_eval(state, ev):
        vagues.append((int(ev.event_id), ev.actor_id, ev.target_id))
        if not reenfile["fait"]:
            reenfile["fait"] = True
            DE.add_damage_event(state, 99, 1, 2)     # enfile PENDANT le drain
        return []

    monkeypatch.setattr(DE, "evaluate_trigger_operation", _fake_eval)
    DE.add_damage_event(st, 7, 3, 4)
    DE.process_damage_events(st)
    # DEUX vagues : l'event initial, puis celui enfile pendant la premiere.
    assert vagues == [(int(EventTriggerType.PostDamageTaken), 3, 4),
                      (int(EventTriggerType.PostDamageTaken), 1, 2)]
    assert st.pending_damage_events == []            # la file est VIDE a la sortie


def test_443r2b2_caster_nul_retombe_sur_la_cible(monkeypatch):
    """`EvaluateAbilities(caster, caster, target, ...)` : `actor` ET `caster` sont LE MEME argument
    natif. Caster nul -> le port pose la cible en acteur (le contexte doit rester resoluble)."""
    st = State()
    vus: list = []

    def _fake_eval(state, ev):
        vus.append((ev.actor_id, ev.target_id, ev.ability_type))
        return []

    monkeypatch.setattr(DE, "evaluate_trigger_operation", _fake_eval)
    DE.add_damage_event(st, 1148, None, 9)
    DE.process_damage_events(st)
    assert vus == [(9, 9, 1148)]


def test_443r2b2_file_vide_est_un_noop(monkeypatch):
    """`if (q.Count > 0)` -- le natif n'ouvre meme pas la phase. C'est un GATE, pas une optimisation."""
    st = State()
    appels = []

    def _fake_eval(state, ev):
        appels.append(ev)
        return []

    monkeypatch.setattr(DE, "evaluate_trigger_operation", _fake_eval)
    assert DE.process_damage_events(st) == []
    assert appels == []


# --------------------------------- [3] LA RE-ENTRANCE -----------------------------------------
def test_443r2b2_reentrance_du_drain(monkeypatch):
    """`draining_damage_events` -- pendant exact de `draining_pending_abilities`. Un drain relance
    DEPUIS l'interieur d'une vague ne doit PAS re-entrer dans la boucle.

    ⚠ **LE SCENARIO A DU ETRE CONSTRUIT DEUX FOIS, ET C'EST LA MESURE QUI L'A EXIGE.** Les deux
    formes naives ne prouvent RIEN :
      * re-drainer sans avoir enfile -> la file est VIDE apres le snapshot-puis-clear, donc le
        garde `not pending_damage_events` suffit seul ;
      * enfiler puis re-drainer avec **UN SEUL** item dans la vague -> la sortie est `[3, 7]` des
        DEUX cotes (la re-entree joue `7`, ou bien la vague suivante le joue -- meme ordre).
    Il faut **DEUX items dans la vague initiale** : sans le garde, le `7` enfile par le PREMIER
    est joue par la re-entree, donc **AVANT** le second item de la vague ; avec le garde, il
    attend la vague SUIVANTE, donc **APRES**. C'est exactement le sens du traitement par VAGUES,
    et c'est le seul observable qui les separe (mesure du 2026-08-15 : la mutation restait VERTE
    sur les deux formes precedentes)."""
    st = State()
    vus: list = []

    def _fake_eval(state, ev):
        vus.append(ev.target_id)
        if ev.target_id == 3:                       # une seule fois, sinon recursion infinie
            DE.add_damage_event(state, 9, 8, 7)     # la file n'est plus VIDE...
            assert state.draining_damage_events is True
            DE.process_damage_events(state)         # ...donc SEUL le garde arrete la re-entree
        return []

    monkeypatch.setattr(DE, "evaluate_trigger_operation", _fake_eval)
    DE.add_damage_event(st, 1, 2, 3)
    DE.add_damage_event(st, 1, 2, 4)                # SECOND item de la MEME vague
    DE.process_damage_events(st)
    # L'event re-enfile (`7`) attend la vague SUIVANTE : il passe APRES le second item (`4`).
    assert vus == [3, 4, 7], vus
    assert st.draining_damage_events is False       # le garde est RELEVE a la sortie
    assert st.pending_damage_events == []


# ------------------- [4] LE SITE D'ENFILEMENT EST ADJACENT A `On(0xf)` (AST) -------------------
def test_443r2b2_le_chokepoint_enfile_juste_apres_damage_taken():
    """`ApplyDamageOperation$$Execute` appelle `AddDamageEvent` **juste apres** `On(0xf)` et **dans
    le meme bloc garde** (le gate le plus interne etant `skipDamageEventTrigger`, qui couvre les
    DEUX gestes). Derive de l'ARBRE, jamais recopie : les deux appels doivent etre DEUX
    instructions CONSECUTIVES du MEME corps de `if`."""
    with open(_DAMAGE, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    def _nom(node):
        f = node.value.func if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) else None
        if isinstance(f, ast.Attribute):
            return f.attr
        return f.id if isinstance(f, ast.Name) else None

    trouve = 0
    for n in ast.walk(tree):
        corps = getattr(n, "body", None)
        if not isinstance(corps, list):
            continue
        noms = [_nom(x) for x in corps]
        for i, nm in enumerate(noms):
            if nm == "damage_taken_triggers":
                assert i + 1 < len(noms) and noms[i + 1] == "add_damage_event", (
                    "`add_damage_event` doit SUIVRE IMMEDIATEMENT `damage_taken_triggers` dans le "
                    "meme bloc -- c'est l'adjacence NATIVE, et le gate commun l'impose")
                trouve += 1
    assert trouve == 1, ("un seul site d'emission d'`On(0xf)` est attendu dans le chokepoint "
                         "(trouve : %d)" % trouve)


# ------------------------ [5] LE RANG : AVANT LE DRAIN DES DIFFEREES ---------------------------
def test_443r2b2_rang_avant_le_drain_des_differees():
    """`RunPhase`, LU verbatim : `action() ; VerifyDeaths() ; **ProcessDamageEvents()** ;
    <0x1e> ; ProcessPendingTriggeredAbilities() ; ...`

    LE VICE QUE CE TEST GARDE : inverser les deux drains ferait voir aux consommateurs d'`On(0x11)`
    un etat que le natif leur cache."""
    with open(_RUNNER, encoding="utf-8") as fh:
        src = fh.read()
    tree = ast.parse(src)
    appels = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id in ("process_damage_events", "process_pending_triggered_abilities")]
    assert len(appels) == 2, "les DEUX drains doivent etre appeles exactement une fois chacun"
    ordre = [n.func.id for n in sorted(appels, key=lambda x: x.lineno)]
    assert ordre == ["process_damage_events", "process_pending_triggered_abilities"], \
        "`ProcessDamageEvents` PRECEDE `ProcessPendingTriggeredAbilities` (RunPhase, LU)"


# ------------------- [6] LES TROIS CONSOMMATEURS SONT ATTEINTS PAR CE VECTEUR ------------------
def test_443r2b2_les_trois_consommateurs_ecoutaient_a_vide():
    """Le compte est DERIVE du registre, pas recopie : la fiche `#443-r2-b2` n'en nommait qu'UN.
    Les trois sous-classes d'`AReactivateOverwatchHitReductionPurge` declarent
    `event_ids = (UnitDeath, PostDamageTaken)` et n'avaient, jusqu'a cette tranche, AUCUN emetteur
    pour le second."""
    from engine.runner.operations.triggers.dispatch.registry import EFFECT_TRIGGERS
    p = int(EventTriggerType.PostDamageTaken)
    noms = sorted({c.__name__ for classes in EFFECT_TRIGGERS.values() for c in classes
                   if p in [int(i) for i in
                            (getattr(c, "event_ids", None) or (getattr(c, "event_id", None),))
                            if i is not None]})
    assert noms == ["EarlyWarningOverrideHitReductionPurge",
                    "FiringPositionHitReductionPurge",
                    "InescapableDeathHitReductionPurge"], noms
    # ASSERTION DE NON-VIDE : un balayage qui ne trouverait plus personne passerait pour vert.
    assert len(noms) == 3


@pytest.mark.parametrize("membre,attendu,ou", [
    (int(EventTriggerType.PostDamageTaken), 17,
     "`ProcessPostDamageEventOperation$$Execute` -> slot 0x51 avec le litteral **0x11**"),
    (int(EventTriggerType.DamageTaken), 15, "`On(0xf)`, le voisin immediat du site d'enfilement"),
])
def test_443r2b2_ordinaux_ecrits_au_site(membre, attendu, ou):
    """Fige l'ordinal MESURE a la conversion."""
    assert membre == attendu, "ordinal glisse -- lu au site %s" % (ou,)
