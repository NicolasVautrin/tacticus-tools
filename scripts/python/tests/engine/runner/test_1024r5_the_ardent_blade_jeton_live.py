"""#1024-r5 -- `TheArdentBlade` : le JETON 1462 est POSE ET ACTIF, au NATIF comme au PORT.

CE QUE CE FICHIER REFUTE. L'audit de couverture d'item comptait `TheArdentBlade` **PARTIELLE** --
<< le montage est ECRIT et il ne s'execute RIEN >> -- au motif que l'effet pose par
`ABILITY_INIT_OWNER_EFFECTS` n'a aucune classe dans `EFFECT_CLASSES`. La mesure OFFLINE dit que le
NATIF n'en a aucune non plus (ZERO symbole `.Entities.Effects.*` pour 1462 dans tout le build) :
1462 est un JETON a un coup, relu par le `HasEffect(Owner, 1462, onlyActive: true)` du
`CreateTrigger` de `TheArdentBlade_TriggerAbility`, et le `BaseEffect` generique du port en est le
mirror FIDELE. Ce fichier-ci en fait la preuve LIVE, des DEUX cotes.

⚠ **L'ETAT 3 D'UNE RELIQUE, ET IL EXIGE DEUX TEMPS.** `adeptCelestine` est HORS POOL, et
`rl_duel build --equip-relic` REFUSE (`'adeptCelestine' absent de BC.Units`) : contrairement a
`--equip-mythic`, il n'injecte PAS son porteur au catalogue -- il s'applique au BC **normalise**,
donc apres que le pool est fige. Le montage est donc :

    1. `catalog_inject.write_relic_seed_bc(...)`  -- injecte le porteur PUIS equipe la relique,
       c'est-a-dire les TROIS ecritures de #237 (`TertiaryAbility`, la config d'ability dans
       `BC.Abilities.PassiveAbilities`, et `TertiaryAbilityLevel >= 1`) ;
    2. `rl_duel build --seed-bc <ce fichier>`     -- la normalisation reecrit le niveau a 50, que
       le natif clampe au dernier palier.

C'est ce montage-la que `case-1013r2` nommait comme NON JOUE. Il l'est ici.

TROIS ETAGES, et une CONTRE-EPREUVE :

  [1] NATIF   -- `decisionView.units[<Celestine>].effects` porte l'`EffectType` 1462.
  [2] PORT    -- la MEME capture, seedee : l'instance 1462 existe, elle est ACTIVE, et
                 `TheArdentBladeTriggerAbility` est INSCRITE sur le porteur.
  [3] LE GATE -- le conjoint `HasEffect(Owner, 1462, onlyActive: true)` de l'arbre de trigger rend
                 VRAI. C'est LUI qui consomme le jeton ; s'il fermait, la relique ne partirait
                 jamais et le << rien ne s'execute >> serait vrai.
  [C] SANS LA RELIQUE -- meme porteur injecte, relique NON equipee : aucun 1462 des deux cotes, et
      aucune inscription. Sans ce bras, les trois etages ci-dessus pourraient tenir a une cause
      etrangere a la relique.
"""
from __future__ import annotations

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/green_skip_guard.py", "scripts/python/declencheur_guard.py",
        "scripts/python/rl_duel.py", "scripts/python/catalog_inject.py",
        "scripts/python/gameconfig.py", "scripts/python/kit_item_voies.py",
        "scripts/python/engine/runner/snapshot.py",
        # PROPRE A CE FICHIER
        "scripts/python/engine/runner/operations/triggers/loki/the_ardent_blade.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/abilities/behaviours/context.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Test LIVE : monte l'etat 3 d'une relique (porteur HORS POOL injecte au catalogue "
              "puis relique equipee) et etablit, au NATIF comme au PORT, que le JETON 1462 est "
              "pose ET actif et que le gate `HasEffect` de l'arbre de trigger le lit.",
}

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

import catalog_inject  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.runner.components import StatsComponent  # noqa: E402
from engine.runner.operations.triggers.loki import the_ardent_blade as TAB  # noqa: E402
from engine.runner.snapshot import load_state  # noqa: E402

PORTEUR = "adeptCelestine"          # HORS POOL -> etat 3 (cf. l'en-tete)
RELIQUE = "TheArdentBlade"
JETON = TAB.THE_ARDENT_BLADE_EFFECT                     # `EffectType` 0x5b6 = 1462
FIGURANT = "adeptCanoness"
CIBLE = "tyranTyrantGuard"
LOIN = "tyranParasite"
BOARD = "MC1_67"

#: Les sorties du run vont dans `logs/` -- JAMAIS sous `data/`, qui ne porte que des ENTREES
#: versionnees (`catalog_inject.write_*` le REFUSE, rc 2).
_LOGS = Path(__file__).resolve().parents[4] / "logs"


def _seed_bc(avec_relique: bool) -> str:
    """Le seed BC de l'etat 3, ou son temoin SANS relique.

    Les deux bras injectent le MEME porteur au catalogue : seule l'ecriture de la relique change.
    C'est ce qui rend la contre-epreuve attribuable a la RELIQUE et non a la presence du porteur."""
    _LOGS.mkdir(parents=True, exist_ok=True)
    out = _LOGS / ("tab_seed_%s.json" % ("relique" if avec_relique else "sans"))
    if avec_relique:
        p, reports = catalog_inject.write_relic_seed_bc(
            str(out), ["%s:%s:1" % (PORTEUR, RELIQUE)], allow_unlisted=True)
        rep = reports[0]
        if not rep.get("unitsPatched"):
            pytest.fail("le montage relique n'a patche AUCUNE unite : %s" % rep)
        return str(p)
    import json
    seed = catalog_inject._load_seed(None)
    bc, _added, _ab, _unres = catalog_inject.augment(seed, [PORTEUR], rank=17)
    out.write_text(json.dumps(bc), encoding="utf-8")
    return str(out)


def _monte(rpc, build_runner, avec_relique: bool) -> dict:
    extra = ["--rank", "17", "--board", BOARD,
             "--seed-bc", _seed_bc(avec_relique),
             "--p-units", "%s,%s" % (PORTEUR, FIGURANT),
             "--a-units", "%s,%s" % (CIBLE, LOIN),
             "--place", "%s:3,4" % PORTEUR,
             "--a-place", "%s:3,5" % CIBLE]
    rid = build_runner("777", extra=extra, board=BOARD)["rid"]

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.fail("boardGraph indisponible -- AUCUNE mesure n'a eu lieu")
    board = Board(bg["tiles"], adjacency="native_sym")
    # `includeInactive` : le canal par defaut DROPPE les effets a `IsActive == 0`. On le demande
    # pour que << absent >> ne puisse pas se confondre avec << desactive >> (cf. #1013-r2).
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True,
                              "includeInactive": True}, 300)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
    row = next((u for u in (dv.get("units") or [])
                if u.get("visualId") == PORTEUR and u.get("alive")), None)
    if row is None:
        pytest.fail("le porteur %s n'est pas en bataille -- l'injection catalogue a echoue" % PORTEUR)

    # --- [1] NATIF -----------------------------------------------------------------------
    natif = [e for e in (row.get("effects") or []) if int(e.get("effectType") or -1) == JETON]

    # --- [2] PORT ------------------------------------------------------------------------
    state = load_state(dv, ob, snap, board=board)
    car = None
    for uid, e in state.entities.items():
        sc = e.get_component(StatsComponent)
        if sc is not None and getattr(sc.ctx, "visual_id", None) == PORTEUR:
            car = uid
    if car is None:
        pytest.fail("porteur absent du port -- le seed de l'etat a echoue")
    sc = state.get_entity(car).get_component(StatsComponent)
    inst = [e for e in ((state.effects.by_unit.get(car) if state.effects else None) or [])
            if int(getattr(e, "effect_type", -1) or -1) == JETON and not e.consumed]
    from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
    inscrites = sorted(type(x).__name__ for x in collect_triggered_abilities(state)
                       if getattr(x, "owner_id", None) == car)

    # --- [3] LE GATE ---------------------------------------------------------------------
    from engine.runner.abilities.behaviours.context import entities_from_state
    ents = entities_from_state(state, int(car), actor_id=int(car))
    gate = bool(TAB.ardent_blade_trigger_tree().should_trigger(ents))

    return {"rid": rid, "porteur": car, "natif": natif,
            "tertiary": getattr(sc.ctx, "tertiary_ability", None),
            "instances": [{"active": bool(getattr(i, "active", None)),
                           "effect_type": int(getattr(i, "effect_type", -1) or -1)}
                          for i in inst],
            "inscrites": inscrites, "gate": gate}


@pytest.fixture(scope="module")
def avec_relique(rpc, build_runner):
    return _monte(rpc, build_runner, True)


@pytest.fixture(scope="module")
def sans_relique(rpc, build_runner):
    return _monte(rpc, build_runner, False)


def test_le_montage_de_l_etat_3_arrive_en_bataille(avec_relique):
    """L'etat 3 (porteur HORS POOL + relique) tient : `ctx.tertiary_ability` porte la relique.

    C'est le premier des trois etages qui echouent EN SILENCE (#237). Le separer des deux autres
    evite d'attribuer a la mecanique ce qui serait un defaut de montage."""
    assert avec_relique["tertiary"] == RELIQUE, (
        "la relique n'atteint pas le porteur : `ctx.tertiary_ability`=%r. L'une des trois "
        "ecritures de #237 a echoue en silence." % (avec_relique["tertiary"],))


def test_le_JETON_1462_est_pose_et_ACTIF_au_natif_ET_au_port(avec_relique):
    """LE test. `TheArdentBlade_InitAbility.CreateBehaviour` = `AddEffect(1462, .., Owner, Owner)`
    & `ActivateEffect(Owner, 1462)`.

    Le natif le pose alors qu'il n'a AUCUNE classe d'effet pour 1462 -- l'entite-effet existe et
    porte son flag, un point c'est tout. C'est exactement ce que le `BaseEffect` generique du port
    reproduit, et c'est pourquoi << pas de classe >> ne veut PAS dire << rien ne s'execute >>."""
    r = avec_relique
    assert r["natif"], (
        "le NATIF ne porte AUCUN effet %d sur le porteur : la pose d'`ABILITY_INIT_OWNER_EFFECTS` "
        "n'a pas de contrepartie native ici, et tout le raisonnement tombe. Rien n'est conclu."
        % JETON)
    assert r["instances"], (
        "le PORT ne materialise AUCUNE instance %d alors que le natif en a une (%s) : "
        "`_materialize_owner_effect` n'a pas pose le jeton." % (JETON, r["natif"]))
    assert all(i["active"] for i in r["instances"]), (
        "l'instance du port existe mais est INACTIVE (%s). Le couple natif est "
        "`AddEffect` + `ActivateEffect` ; un jeton inactif ferme le `HasEffect(.., onlyActive: "
        "true)` du trigger et la relique ne partirait jamais." % r["instances"])


def test_le_gate_HasEffect_du_trigger_LIT_le_jeton(avec_relique):
    """[3] Le conjoint qui CONSOMME le jeton. Un jeton pose que personne ne lit ne prouverait rien
    -- c'est ce gate-la qui fait la difference entre << l'effet existe >> et << la mecanique
    tourne >>. `ardent_blade_trigger_tree()` est l'arbre EXTRAIT en fonction nommee precisement
    pour etre verifiable (#963-r1)."""
    assert avec_relique["gate"] is True, (
        "l'arbre de trigger de la relique rend FAUX alors que le jeton %d est pose et actif : "
        "le conjoint `HasEffect(Owner, %d, onlyActive: true)` ne le lit pas." % (JETON, JETON))


def test_la_relique_est_INSCRITE_sur_son_porteur(avec_relique):
    """La voie TERTIAIRE passe par `RELIC_ABILITY_TRIGGERS` -- sans inscription, le jeton serait
    pose et AUCUN trigger ne l'ecouterait."""
    assert "TheArdentBladeTriggerAbility" in avec_relique["inscrites"], (
        "`TheArdentBladeTriggerAbility` n'est pas inscrite sur le porteur : %s"
        % (avec_relique["inscrites"],))


def test_SANS_la_relique_aucun_jeton_ni_inscription_des_DEUX_cotes(sans_relique, avec_relique):
    """LA CONTRE-EPREUVE. MEME porteur injecte au catalogue, relique NON equipee. Sans ce bras, les
    quatre etages ci-dessus pourraient tenir a la seule presence du porteur."""
    assert avec_relique["natif"], (
        "le bras AVEC relique est vide : ce zero-ci ne separerait rien (regime degenere)")
    r = sans_relique
    assert r["tertiary"] is None, (
        "le temoin porte une relique alors qu'on ne lui en a pose aucune (%r) : les deux bras ne "
        "different pas par ce qu'on croit." % (r["tertiary"],))
    assert not r["natif"], (
        "le NATIF pose l'effet %d SANS relique equipee (%s) -- le jeton viendrait d'ailleurs."
        % (JETON, r["natif"]))
    assert not r["instances"], (
        "le PORT materialise le jeton %d SANS relique (%s) : la voie TERTIAIRE n'est pas ce qui "
        "le pose cote port." % (JETON, r["instances"]))
    assert "TheArdentBladeTriggerAbility" not in r["inscrites"], (
        "la relique est inscrite SANS avoir ete equipee : %s" % (r["inscrites"],))
