"""#521-r7 / #521-r4 -- les GARDES de l'etage `On(0x4a = AttackInAtomicGroup)` et de `1316`.

`probe_521r7_calibanite_sweep.py` MESURE (live, une fois) ; ce fichier GARDE (offline, a chaque
passe). Les deux se commitent. Cinq etages, et chacun a ete VU ROUGE par mutation adversariale
avant d'etre livre -- une garde jamais vue rouge ne garde rien :

  1. `test_..._rayon_du_vecteur`      -- le RAYON de l'elargissement d'`evaluate_abilities_for_event`
                                         (mesure a trois etages, pas une affirmation de docstring) ;
  2. `test_..._emetteur_voie_normale` -- l'emetteur `On(0x4a)` EST sur la voie de l'attaque normale ;
  3. `test_..._rang_entre_fold_et_cleave` -- son RANG, qui n'est pas decoratif (chaque coup consomme
                                         `state.rng`) ;
  4. `test_..._anti_double_fire`      -- `fire_of_absolution=False` sur la voie NORMALE ;
  5. `test_..._config_lue_de_1189`    -- `1316` n'a AUCUNE config propre, donc la config LUE est
                                         celle de l'ACTIVE 1189.

⚠ Ce que ce fichier NE garde PAS : la MAGNITUDE. Elle diverge (residu `#521-r9`) et son attribution
est EN AMONT de cette tranche -- la figer ici graverait un ecart connu comme s'il etait la loi.
"""
from __future__ import annotations

import ast
import inspect
import json
import os
from types import SimpleNamespace

import pytest

import gameconfig as GC
from engine.dsl.event_trigger_type import EventTriggerType
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.effect_type import EffectType
from engine.entities.effects_state import BaseEffect, EffectsState
from engine.entities.triggered_ability_type import TriggeredAbilityType

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        # le perimetre EST le balayage : ce fichier PARSE `engine/**` (rayon du vecteur) et LIT
        # `data/seed-bc.json`. Un glob etroit mentirait au selecteur.
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
        "data/seed-bc.json",
    ),
    "build": True,            # les trois enums et le gameconfig sont per-build
    "toujours": False,
    "raison": ("garde l'etage On(0x4a = AttackInAtomicGroup) de la voie d'attaque normale et le "
               "port de 1316 : rayon du vecteur, presence de l'emetteur, son rang, l'anti-double-"
               "fire de FireOfAbsolution, et la config LUE de 1189"),
}

_PY = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))                       # .../scripts/python
_ROOT = os.path.dirname(os.path.dirname(_PY))           # racine du depot
_DAMAGE = os.path.join(_PY, "engine", "runner", "operations", "damage.py")

CG_ACTIVE = ActiveAbilityType.CalibaniteGreatsword.name                 # 0x4a5 = 1189
CG_SWEEP_TRIGGERED = TriggeredAbilityType.CalibaniteGreatsword_NormalAttackAdditionalDamage
CG_SWEEP_EFFECT = int(EffectType.CalibaniteGreatswordSweep)            # 0x57d = 1405


# ------------------------------------------------------------------ 1. le RAYON de l'elargissement

def _events_reachable(sources: "dict[str, str] | None" = None) -> set:
    """Les `EventTriggerType` qu'un appel a `evaluate_abilities_for_event` peut porter, DERIVES de
    l'arbre (jamais recopies) : les call-sites DIRECTS **et** les constructions du noeud DSL
    `EvaluateAbilities`, qui est le second chemin vers la meme fonction.

    `sources` = surcharge `{chemin: texte}` pour les MUTATIONS (un fichier reecrit en memoire).
    """
    out, seen_site = set(), 0
    for d, _dirs, fs in os.walk(os.path.join(_PY, "engine")):
        for f in fs:
            if not f.endswith(".py"):
                continue
            p = os.path.join(d, f)
            txt = (sources or {}).get(p)
            if txt is None:
                with open(p, encoding="utf-8") as fh:
                    txt = fh.read()
            try:
                tree = ast.parse(txt)
            except SyntaxError:                      # pragma: no cover -- arbre non parsable
                continue
            for n in ast.walk(tree):
                if not isinstance(n, ast.Call):
                    continue
                fn = n.func
                nm = fn.attr if isinstance(fn, ast.Attribute) else (
                    fn.id if isinstance(fn, ast.Name) else None)
                if nm not in ("evaluate_abilities_for_event", "EvaluateAbilities"):
                    continue
                seen_site += 1
                # l'EVENT est le 4e positionnel de la fonction, le 1er du noeud -- on prend TOUS les
                # `int(EventTriggerType.X)` de l'appel : un litteral nu y serait invisible, et c'est
                # justement ce que la regle « un ENTIER qui DESIGNE passe par un ENUM » interdit.
                for a in ast.walk(n):
                    if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) \
                            and a.value.id == "EventTriggerType":
                        out.add(a.attr)
    assert seen_site > 0, ("aucun call-site d'`evaluate_abilities_for_event` ni de `EvaluateAbilities` "
                           "trouve -- le balayage est VIDE, il ne peut rien garder")
    return out


def _registered_by_event() -> "tuple[dict, int]":
    """`{event -> [(registre, classe)]}` sur les SEPT registres, plus le nombre total de classes."""
    from engine.runner.operations.triggers.dispatch import registry as R
    named = ("TRAIT_TRIGGERS", "ABILITY_TRIGGERS", "ACTIVE_ABILITY_TRIGGERS",
             "PASSIVE_HELPER_ABILITY_TRIGGERS", "RELIC_ABILITY_TRIGGERS", "EFFECT_TRIGGERS")
    classes = set()
    for n in named:
        for _k, v in getattr(R, n).items():
            for c in v:
                classes.add((n, c))
    for c in getattr(R, "GLOBAL_TRIGGERS", ()):
        classes.add(("GLOBAL_TRIGGERS", c))
    by_ev: dict = {}
    for reg, c in classes:
        evs = set()
        e = getattr(c, "event_id", None)
        if e is not None:
            evs.add(int(e))
        for x in (getattr(c, "event_ids", ()) or ()):
            evs.add(int(x))
        for e in evs:
            by_ev.setdefault(e, []).append((reg, c.__name__))
    return by_ev, len(classes)


def test_521r7_rayon_du_vecteur():
    """LE RAYON, MESURE A TROIS ETAGES -- pas une affirmation de docstring.

    `evaluate_abilities_for_event` rend desormais `out + evaluate_trigger_operation(state, ev)`,
    INCONDITIONNELLEMENT. La question n'est donc pas « 1316 fire-t-elle ? » mais « QUOI D'AUTRE
    devient joignable ? ». Trois etages, chacun derive :

      (a) quels EVENTS un appel peut porter -> l'AST des call-sites (fonction + noeud DSL) ;
      (b) quelles CLASSES du registre ecoutent ces events -> les sept registres ;
      (c) le rayon SECONDAIRE : `_publish_unit_triggered_ability` republie `On(0xd =
          UnitTriggeredAbility)` apres chaque trigger porteur d'un `TRIGGERED_ABILITY_ID`.

    Temoin NON NUL a chaque etage (un balayage vide passerait pour un vert)."""
    events = _events_reachable()
    assert events == {"AttackInAtomicGroup"}, (
        f"le rayon a CHANGE : `evaluate_abilities_for_event` peut desormais porter {sorted(events)} "
        f"-- re-mesurer les consommateurs de CHAQUE nouvel event avant de livrer")

    by_ev, total = _registered_by_event()
    assert total > 100 and len(by_ev) > 20, (
        f"balayage des registres VIDE ou amputé ({total} classes, {len(by_ev)} events) -- il ne "
        f"peut rien garder")

    atteignables = sorted(by_ev.get(int(EventTriggerType.AttackInAtomicGroup), []))
    # MESURE du 2026-08-15 (#521-r8), a la TROISIEME entree de ce vecteur -- ce que ce garde exige :
    #   * `1316 CalibaniteGreatsword_NormalAttackAdditionalDamage` (#521-r4) ;
    #   * `1465 OrbsOfDecay` (relique Death Guard), qui porte `On(0x4a) & get_OwnerIsCaster &
    #     IsMeleeAttack` -- et SANS `IsNormalAttack`, contrairement a 1316 ;
    #   * `1098 Pyreblaster` (#1052), entree au registre SANS que ce cliquet soit rejoue -- il
    #     rougissait donc sur `master` depuis. C'EST UN RESULTAT, ET IL EST STRUCTUREL :
    #     `...PyreblasterAbility$$CreateTrigger` a le corps DEDUPLIQUE par ICF (MEME RVA) que
    #     `...FireOfAbsolutionAbility$$CreateTrigger`, donc EXACTEMENT le meme trigger
    #     `On(0x4a) & get_OwnerIsActor & IsRangedAttack`. Les deux passifs jumeaux vivaient sur deux
    #     canaux DIFFERENTS (Pyreblaster sur le bus, FireOfAbsolution en imperatif depuis
    #     `after_hit_normal_attack`) ; #521-r8 les reunit sur le bus, au meme rang.
    # LE RAYON SUPPLEMENTAIRE OUVERT PAR `OrbsOfDecay` EST **VIDE**, et c'est derive, pas suppose :
    # les DEUX seuls call-sites du noeud DSL `EvaluateAbilities(AttackInAtomicGroup)` du port sont
    # dans `abilities/loki/strike.py` (`ArmoriumCherub`), et ils passent tous deux `ranged=True` ->
    # le gate `IsMeleeAttack` d'`OrbsOfDecay` (`not ev.ranged`) les REFUSE. Seconde raison,
    # INDEPENDANTE : `get_OwnerIsCaster` exigerait que le porteur de la relique SOIT le caster
    # d'`ArmoriumCherub` (une active `admec`), ce qu'aucune unite ne peut etre.
    # ⚠ `FireOfAbsolution` n'apparait PAS dans cette liste et ne doit pas y apparaitre : il n'est
    # dans AUCUN des sept registres -- son canal est `IMPERATIVE_ABILITY_VECTORS` (5e voie de
    # couverture, #951-r2), appele en dur par `evaluate_abilities_for_event`. C'est le test
    # `test_521r8_fire_of_absolution_a_migre_sur_son_vecteur` qui garde CE canal-la.
    assert atteignables == [("ABILITY_TRIGGERS", "PyreblasterAbility"),
                            ("PASSIVE_HELPER_ABILITY_TRIGGERS",
                             "CalibaniteGreatswordNormalAttackAdditionalDamageAbility"),
                            ("RELIC_ABILITY_TRIGGERS", "OrbsOfDecayAbility")], (
        f"le RAYON de l'elargissement a CHANGE : {atteignables}. Ce n'est pas un "
        f"echec en soi -- c'est un RESULTAT a lire (chaque entree devient joignable depuis la voie "
        f"d'attaque normale ET depuis `ArmoriumCherub`), mais il doit etre MESURE, pas subi")

    secondaire = by_ev.get(int(EventTriggerType.UnitTriggeredAbility), [])
    assert secondaire == [], (
        f"le rayon SECONDAIRE s'est ouvert : {secondaire} ecoute(nt) `On(0xd)`, que "
        f"`_publish_unit_triggered_ability` republie apres CHAQUE trigger declenche -- donc "
        f"desormais aussi depuis la voie d'attaque normale")


# ------------------------------------------------- 2. l'EMETTEUR est sur la voie d'attaque normale

def _emitter_calls(src: str) -> list:
    """Les appels a `evaluate_abilities_for_event` DANS `visit_AttackUnitMessage`, avec les
    mots-cles qui nous interessent. Liste vide = l'emetteur n'est plus sur cette voie."""
    tree = ast.parse(src)
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef) or fn.name != "visit_AttackUnitMessage":
            continue
        for n in ast.walk(fn):
            if not isinstance(n, ast.Call):
                continue
            f = n.func
            nm = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name)
                                                              else None)
            if nm != "evaluate_abilities_for_event":
                continue
            ev = {a.attr for a in ast.walk(n)
                  if isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name)
                  and a.value.id == "EventTriggerType"}
            kw = {k.arg: k.value for k in n.keywords}
            out.append({"events": ev, "kwargs": kw})
    return out


def test_521r7_emetteur_voie_normale():
    """`ALoki_NormalAttackAbility$$ExecuteNormalAttack` emet `EvaluateAbilities(0x4a, immediately:
    true)` sur TOUTE attaque normale. Le port l'emet depuis `DamageHandler.visit_AttackUnitMessage`.

    CONTRE-EPREUVE (mutation adversariale, source RESTAUREE en memoire seulement) : la meme lecture
    sur une source ou l'appel a ete retire DOIT rendre une liste vide -- sans quoi cette garde ne
    verrait pas la regression qu'elle pretend garder."""
    with open(_DAMAGE, encoding="utf-8") as fh:
        src = fh.read()
    calls = _emitter_calls(src)
    assert len(calls) == 1, (f"l'emetteur `On(0x4a)` n'est plus UNIQUE sur la voie normale : "
                             f"{len(calls)} appel(s)")
    assert calls[0]["events"] == {"AttackInAtomicGroup"}, calls[0]["events"]
    assert "ability_type" in calls[0]["kwargs"], (
        "`ability_type` n'est plus threade -- le gate `IsNormalAttack` de 1316 ne serait plus "
        "satisfait et le trigger deviendrait INERTE, sans erreur")

    # MUTATION (en memoire, la source n'est jamais touchee) : le RENOMMAGE de l'appelee. Il
    # preserve la syntaxe -- une suppression de LIGNES la cassait, et un test qui echoue sur sa
    # propre mutation ne prouve rien non plus.
    mute = src.replace("_atomic_dispatch.evaluate_abilities_for_event(",
                       "_atomic_dispatch.MUTE_evaluate_abilities_for_event(")
    assert mute != src, "la mutation n'a rien remplace -- la contre-epreuve serait vide"
    ast.parse(mute)                       # la mutation DOIT rester parsable
    assert _emitter_calls(mute) == [], (
        "MUTATION SANS EFFET : la source privee de l'appel rend quand meme un emetteur -- "
        "cette garde ne peut pas voir la regression")


# ------------------------------------------------------------------- 3. le RANG (fold -> 0x4a -> cleave)

class _RecordingNode:
    def __init__(self, tag, log):
        self.tag, self.log = tag, log

    def execute(self, _entities, _ectx):
        self.log.append(self.tag)


def test_521r7_rang_entre_fold_et_cleave(monkeypatch):
    """LE RANG N'EST PAS DECORATIF : chaque coup consomme `state.rng`. Le natif compose
    `GetAttackDamageBehaviour(...)` -- qui porte les coups d'ARME **et** le fold primaire -- PUIS
    `EvaluateAbilities(0x4a)`, et c'est seulement ensuite que `Execute<X>` enchaine sur son
    `ExecuteAtomic(0x2a)` (le CLEAVE). Jouer le vecteur du mauvais cote decalerait le flux.

    Un test qui ne verifierait que << ca fire >> ne verrait pas cette faute-la : on mesure l'ORDRE.
    Temoin NON NUL : sans `after_primary`, l'ordre est `fold -> cleave` (donc les deux volets sont
    bien joues et la sonde n'est pas vide)."""
    import engine.runner.abilities.loki.additional_targets as AT

    log: list = []
    monkeypatch.setattr(AT, "entities_from_state", lambda *a, **k: object())
    monkeypatch.setattr(AT, "ExecutionContext",
                        lambda **k: SimpleNamespace(emitted=[], state=None, rng=None))
    monkeypatch.setattr(AT, "is_melee_position", lambda *a, **k: True)
    monkeypatch.setattr(AT, "primary_fold_tree",
                        lambda *a, **k: _RecordingNode("fold", log))
    monkeypatch.setattr(AT, "cleave_tree", lambda *a, **k: _RecordingNode("cleave", log))

    entry = AT._Cleave("Fealty", True, lambda: None, primary_fold_when_melee_position=True)
    state = SimpleNamespace(rng=None)

    AT.execute_additional_targets_attacks(state, 1, 2, entry, is_melee=True,
                                          after_primary=lambda: log.append("On(0x4a)"))
    assert log == ["fold", "On(0x4a)", "cleave"], (
        f"RANG FAUX : {log} -- le vecteur `On(0x4a)` doit s'intercaler ENTRE le fold primaire "
        f"(compose dans `GetAttackDamageBehaviour`) et le CLEAVE (`ExecuteAtomic(0x2a)`)")

    log.clear()
    AT.execute_additional_targets_attacks(state, 1, 2, entry, is_melee=True)
    assert log == ["fold", "cleave"], (
        f"TEMOIN VIDE : sans `after_primary` les deux volets devraient quand meme etre joues, "
        f"or {log} -- l'assertion ci-dessus ne prouverait alors rien")


# ------------------------------------------------- 4. la MIGRATION de `FireOfAbsolution` (#521-r8)

def test_521r8_fire_of_absolution_a_migre_sur_son_vecteur(monkeypatch):
    """`FireOfAbsolutionAbility$$CreateTrigger` = `On(0x4a, 1) & get_OwnerIsActor & IsRangedAttack`
    -- AUCUN gate excluant l'attaque normale, et le natif emet cet event depuis
    `...ALoki_NormalAttackAbility$$ExecuteNormalAttack`. Le port le jouait IMPERATIVEMENT depuis
    `after_hit_normal_attack` (le vecteur `On(0x26)`) : comportement present, RANG faux. #521-r8 l'a
    migre sur le bus.

    **CE TEST GARDE LA PAIRE, PAS UNE MOITIE.** Les deux moities doivent bouger ENSEMBLE, et les
    deux modes de panne sont SILENCIEUX :
      * le call-site demande encore `fire_of_absolution=False` **et** l'appel imperatif a ete
        retire -> le splash ne part PLUS DU TOUT (zero erreur, juste des PV en moins) ;
      * l'appel imperatif est revenu **et** le call-site ne le desarme pas -> DOUBLE splash.
    Un test qui ne verifierait qu'un cote laisserait passer l'un des deux."""
    with open(_DAMAGE, encoding="utf-8") as fh:
        calls = _emitter_calls(fh.read())
    kw = calls[0]["kwargs"].get("fire_of_absolution")
    assert kw is None, (
        "la voie NORMALE desarme encore `FireOfAbsolution` alors que l'appel imperatif d'"
        "`after_hit_normal_attack` a ete retire : le splash ne partirait PLUS DU TOUT (#521-r8)")

    import engine.runner.operations.triggers.dispatch.attack as ATT
    src = inspect.getsource(ATT.after_hit_normal_attack)
    assert "_fire_of_absolution_after_attack" not in src, (
        "`after_hit_normal_attack` rappelle `FireOfAbsolution` alors que le vecteur `On(0x4a)` le "
        "joue deja : DOUBLE splash silencieux (#521-r8)")

    import engine.runner.operations.triggers.dispatch.ability as AB
    seen: list = []
    monkeypatch.setattr(AB, "_fire_of_absolution_after_attack",
                        lambda *a, **k: seen.append(1) or [])
    state = SimpleNamespace(entities={}, effects=None, triggering_ability=None,
                            trigger_ability_type=None)
    ev = int(EventTriggerType.AttackInAtomicGroup)
    AB.evaluate_abilities_for_event(state, 1, 2, ev, False)
    assert seen == [1], ("le vecteur `On(0x4a)` ne joue PAS `FireOfAbsolution` par defaut -- apres "
                         "la migration c'est son SEUL home")
    seen.clear()
    AB.evaluate_abilities_for_event(state, 1, 2, ev, False, fire_of_absolution=False)
    assert seen == [], ("TEMOIN : le point de MUTATION doit rester desarmable, sinon aucune "
                        "contre-epreuve ne peut isoler ce canal du bus")


def test_521r7_elargissement_atteint_le_registre(monkeypatch):
    """L'ELARGISSEMENT lui-meme, garde SEPAREMENT du trigger `1316` : avant #521-r7,
    `evaluate_abilities_for_event` rendait `out` (les seuls passifs IMPERATIFS) ; elle rend
    desormais `out + evaluate_trigger_operation(state, ev)`, ce qui est le SEUL chemin par lequel
    un registre devient joignable sur cet event.

    Ce test ne parle PAS de `1316` : il verifie que le rail existe et qu'il porte le bon event et
    le bon `AbilityEntities` (l'acteur, la cible, la nature du coup). Sans lui, une regression qui
    remettrait `return out` laisserait `1316` inscrite ET inerte -- exactement l'etat que #521-r4
    refusait de livrer."""
    import engine.runner.operations.triggers.dispatch.ability as AB
    from engine.runner.abilities.attack_type import NORMAL_ATTACK_KIND
    vus: list = []
    monkeypatch.setattr(AB, "evaluate_trigger_operation",
                        lambda _st, ev: vus.append(ev) or [{"marqueur": 1}])
    monkeypatch.setattr(AB, "_fire_of_absolution_after_attack", lambda *a, **k: [])
    state = SimpleNamespace(entities={}, effects=None, triggering_ability=None,
                            trigger_ability_type=None)
    out = AB.evaluate_abilities_for_event(state, 11, 22, int(EventTriggerType.AttackInAtomicGroup),
                                          False, profile="Power",
                                          ability_type=NORMAL_ATTACK_KIND,
                                          fire_of_absolution=False)
    assert out == [{"marqueur": 1}], (
        "`evaluate_abilities_for_event` ne route PLUS vers `evaluate_trigger_operation` : tout "
        "trigger inscrit sur cet event redeviendrait INERTE, sans erreur")
    assert len(vus) == 1, vus
    ev = vus[0]
    assert int(ev.event_id) == int(EventTriggerType.AttackInAtomicGroup)
    assert (ev.actor_id, ev.target_id) == (11, 22)
    assert int(ev.ability_type) == int(NORMAL_ATTACK_KIND)
    assert ev.is_normal_attack is True, (
        "`is_normal_attack` doit etre DERIVE de l'`ability_type` threade -- un canal muet ferait "
        "supposer au lieu de se taire")
    vus.clear()
    AB.evaluate_abilities_for_event(state, 11, 22, int(EventTriggerType.AttackInAtomicGroup), False)
    assert vus and vus[0].ability_type is None and vus[0].is_normal_attack is None, (
        "sans `ability_type`, le canal doit rester TRI-ETAT (`None`), pas etre rabattu sur un faux")


# ------------------------------------------------------- 5. la CONFIG de 1316 est celle de 1189

def _bc_ability_keys() -> "tuple[set, set]":
    p = os.path.join(_ROOT, "data", "seed-bc.json")
    with open(p, encoding="utf-8") as fh:
        bc = json.load(fh)
    ab = bc.get("Abilities") or {}
    return set(ab.get("ActiveAbilities") or {}), set(ab.get("PassiveAbilities") or {})


def test_521r7_config_lue_de_1189():
    """`...CalibaniteGreatsword_NormalAttackAdditionalDamageAbility$$GetAdditionalTargetsAttackBehavior`
    lit `nrOfHits_2` et `damageProfile` sur `this@+0x20` (la config de l'ability), et les bornes sur
    le LITTERAL `0x4a5` = 1189. La question qui reste au port est : QUELLE config est `this@+0x20` ?

    LA MESURE QUI TRANCHE, et elle est LOAD-BEARING : **1316 n'a AUCUNE configuration propre** --
    ni gameconfig, ni `BC.Abilities.{Active,Passive}Abilities`. Les DEUX autres helpers de
    `GetPassiveHelperAbility` deja identifies sont dans le meme cas, alors que leurs TROIS actives
    porteuses sont, elles, presentes. La seule config atteignable est donc celle de l'ACTIVE 1189 --
    et le gameconfig le corrobore : c'est bien SUR 1189 que vivent `damageProfile` et `nrOfHits_2`,
    deux constantes que l'ACTIVE relit elle-meme pour sa propre passe de balayage
    (`CalibaniteGreatswordAbility$$GetAdditionalTargetsHits` = `ConfigConst(0x4a5, Caster, 0x32)`).
    """
    actives, passives = _bc_ability_keys()
    helpers = ("TalonsOfTheEmperor_UsedAbilities", "DoctrinaImperatives_SetStart",
               "CalibaniteGreatsword_NormalAttackAdditionalDamage")
    porteuses = ("TalonsOfTheEmperor", "DoctrinaImperatives", "CalibaniteGreatsword")
    assert all(p in actives for p in porteuses), (
        f"TEMOIN VIDE : les actives porteuses ne sont pas dans le seed BC -- l'absence des helpers "
        f"ne prouverait alors rien (elle dirait juste que le seed ne les contient pas)")
    for h in helpers:
        assert h not in actives and h not in passives, (
            f"{h} a desormais une config PROPRE dans le seed BC -- la deduction << `this@+0x20` "
            f"est la config de l'ACTIVE >> doit etre RE-LUE au decompile")
        assert GC.ability(h) is None, f"{h} a desormais une entree gameconfig -- meme conclusion"

    cfg = (GC.ability(CG_ACTIVE) or {}).get("constants") or {}
    assert cfg.get("damageProfile") == "Power", cfg
    assert int(cfg.get("nrOfHits_2")) == 3, cfg

    from engine.runner.operations.triggers.loki import calibanite_greatsword as CGM
    from engine.entities.selectors.accessors import Subject
    leaf = CGM.sweep_attack_leaf(Subject())
    assert leaf.ability_id == CG_ACTIVE, leaf.ability_id
    assert leaf.hits_key == "nrOfHits_2", leaf.hits_key
    assert (leaf.min_key, leaf.max_key) == ("minDmg", "maxDmg"), (leaf.min_key, leaf.max_key)
    assert leaf.profile == "Power", leaf.profile
    assert leaf.level_slot == "active", leaf.level_slot
    assert leaf.is_melee is True, "le trigger porte `IsMeleeAttack` -- la feuille doit l'exprimer"
    assert leaf.multi is False, "le natif enveloppe CHAQUE cible dans son propre `Attack(...)`"
    assert leaf.attack_state0 is None, "chaque cible ouvre un `OngoingAttack` NEUF"
    assert int(leaf.ability_type) == int(CG_SWEEP_TRIGGERED), (
        "la SOURCE du coup est l'`AbilityOrEffect(this)` de la TRIGGERED 1316, pas l'active")


# --------------------------------------------------------------- 6. le GATE de POSTURE (1405)

def _matches(effets: "tuple[int, ...]", **ev_kw) -> bool:
    from engine.runner.operations.triggers.loki.calibanite_greatsword import (
        CalibaniteGreatswordNormalAttackAdditionalDamageAbility as A)
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.abilities.attack_type import NORMAL_ATTACK_KIND
    st = EffectsState()
    for e in effets:
        st.add_effect(7, BaseEffect(name=str(e), effect_type=int(e)))
    state = SimpleNamespace(effects=st)
    kw = {"ranged": False, "profile": "Power", "ability_type": NORMAL_ATTACK_KIND}
    kw.update(ev_kw)
    ev = TriggerEvent(int(EventTriggerType.AttackInAtomicGroup), 7, 9, **kw)
    return A(7).matches(state, ev)


def test_521r7_gate_posture_et_nature_du_coup():
    """Les QUATRE gates du `CreateTrigger`, chacun avec sa contre-epreuve (le regime nominal seul ne
    prouverait rien -- il passe aussi si les gates sont absents) :

        On(0x4a) & <OwnerIsAlive> & get_OwnerIsActor & IsNormalAttack & IsMeleeAttack
                 & HasEffect(Owner@+0x30, 0x57d = 1405 CalibaniteGreatswordSweep, onlyActive: 0)
    """
    assert _matches((CG_SWEEP_EFFECT,)) is True, "regime NOMINAL refuse -- rien n'est mesurable"
    # POSTURE : c'est le TOGGLE 1189 qui bascule 1404 STRIKE -> 1405 SWEEP. En STRIKE, rien.
    assert _matches((int(EffectType.CalibaniteGreatswordStrike),)) is False, \
        "le gate `HasEffect(Owner, 1405)` ne mord pas : Forcas balaierait en posture STRIKE"
    assert _matches(()) is False, "sans aucune posture, le balayage part quand meme"
    # IsMeleeAttack
    assert _matches((CG_SWEEP_EFFECT,), ranged=True) is False, \
        "le gate `IsMeleeAttack` ne mord pas : le balayage partirait sur un tir"
    # IsNormalAttack : un CAST thread son propre `ActiveAbilityType`, jamais le kind 0x3f5 --
    # c'est ce qui empeche 1316 de fire sur le `EvaluateAbilities(0x4a)` d'`ArmoriumCherub`.
    assert _matches((CG_SWEEP_EFFECT,),
                    ability_type=int(ActiveAbilityType.ArmoriumCherub)) is False, \
        "le gate `IsNormalAttack` ne mord pas : 1316 firerait sur le groupe atomique d'une ABILITY"
    assert _matches((CG_SWEEP_EFFECT,), ability_type=None) is False, \
        "canal `ability_type` muet -> le gate de kind doit se TAIRE, pas supposer"
    # get_OwnerIsActor : l'attaque d'un TIERS ne declenche pas le balayage de Forcas.
    from engine.runner.operations.triggers.loki.calibanite_greatsword import (
        CalibaniteGreatswordNormalAttackAdditionalDamageAbility as A)
    from engine.runner.operations.triggers.base import TriggerEvent
    from engine.runner.abilities.attack_type import NORMAL_ATTACK_KIND
    st = EffectsState()
    st.add_effect(7, BaseEffect(name="sweep", effect_type=CG_SWEEP_EFFECT))
    ev = TriggerEvent(int(EventTriggerType.AttackInAtomicGroup), 8, 9, ranged=False,
                      profile="Power", ability_type=NORMAL_ATTACK_KIND)
    assert A(7).matches(SimpleNamespace(effects=st), ev) is False, \
        "le gate `get_OwnerIsActor` ne mord pas : Forcas balaierait sur l'attaque d'un tiers"
