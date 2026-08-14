"""#1036 -- `CabalOfSorcerers` (1496) et `GuardianConstruct` (1530), les deux MYTHIQUES de MoW dont
les porteurs `lineup` sont HORS SEED : face POSE de l'owner-effect, CONFRONTEE AU LIVE.
Port : entrees `ABILITY_INIT_OWNER_EFFECTS[...]` (`engine/entities/effects/factory.py`).

RE (detail : `docs/rl/case-1036-mythiques-cabale-et-construct.md`) -- les deux posent un
owner-effect PERMANENT a l'init, par DEUX chemins natifs DIFFERENTS qui donnent le meme resultat :

  * `GuardianConstructAbility` derive d'`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`
    (`frida/classes.tsv`) et n'override QUE `$$GetEffectType` (corps ENTIER `return 0x60c` = 1548).
    La base fait le reste : `$$CreateTrigger = OnOwnerSpecificAbilityInit(this.AbilityType)` et
    `$$CreateBehaviour = If(CreateCondition(...), AddEffect(GetEffectType(), AbilityState(Owner),
    source = Owner, targets = Owner, options = <Nullable ZERO>))`.
  * `CabalOfSorcerersAbility` derive de `IdunBattle.Entities.Abilities.BaseTriggeredAbility` et
    DECLARE ses deux methodes -- meme pose, SANS le `If` :
    `$$CreateTrigger = DSLTriggers.OnOwnerSpecificAbilityInit(0x5d8)` et
    `$$CreateBehaviour = DSLBehaviors.AddEffect(0x5d6 = 1494, AbilityStateReference,
    source = Owner@<DSLSelectors+0x30>, targets = Owner@<DSLSelectors+0x30>,
    turns = <Nullable ZERO-initialise>)`.

TROIS ETAGES par ability, calques sur `test_1025_more_gitz_over_ere_live.py` :
  1. LIVE avec `--equip-mythic` : la MoW porte l'effet, duree PERMANENTE (`remaining == 0`) ;
  2. **CONTRE-EPREUVE SEPARANTE** : le porteur est injecte par `catalog_inject.augment` NU -- le
     MEME arbre moins les trois ecritures tertiaires -- et ne porte alors RIEN. Sans cet etage,
     l'etage 1 mesurerait l'absence du PORTEUR (les deux MoW sont HORS SEED) et non celle du
     MONTAGE, et passerait vert pour la mauvaise raison ;
  3. le PORT charge le MEME etat et voit la MEME instance.

NE COUVRE PAS -- residus `#1036-r1` / `#1036-r2` : aucun des deux effets n'est dans
`EFFECT_CLASSES`, donc aucun ne CONTRIBUE a un degat cote port. Leurs `$$CreateTargetSelector`
finissent tous deux par `UnitsWithRarity(..., Rarity.Mythic = 5)`, qui lit
`GetBaseUnitComponent(e)+0x74` -- canal ABSENT du port. Ce fichier mesure la POSE, pas le BONUS.
ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effects/factory.py",
        "scripts/python/engine/runner/operations/spawn.py",
        "scripts/python/engine/runner/snapshot.py",
        # Le MONTAGE de la mythique (voie TERTIAIRE) + l'injection catalogue des porteurs hors seed.
        "scripts/python/rl_duel.py",
        "scripts/python/catalog_inject.py",
        # Les mirrors d'enum dont les ordinaux 1494 / 1548 sont figes au site.
        "scripts/python/engine/entities/effect_type.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Le verdict depend du SEED BC et du gameconfig (`<mow>.mythicAbilities`), pas "
              "seulement des chemins ci-dessus ; et il MESURE une pose native que le port recoit "
              "par DEUX canaux (capture + seed) -- un changement de l'un ou l'autre le concerne. "
              "Mesure sur le jumeau #1025 : ce test passe encore SANS l'entree "
              "`ABILITY_INIT_OWNER_EFFECTS` (c'est le cliquet OFFLINE qui la garde).",
}

PYDIR = Path(__file__).resolve().parents[3]            # scripts/python
ROOT = PYDIR.parents[1]                                # racine repo

#: Les deux items de la tranche. `etype` / `ename` sont LUS au decompile (`$$GetEffectType` pour
#: `GuardianConstruct`, le call-site d'`AddEffect` pour `CabalOfSorcerers`), jamais deduits du nom.
CAS = {
    "GuardianConstruct": {
        "mow": "necroReanimator",
        "etype": 1548, "ename": "GuardianConstruct_ExtraDamagePct",
        "p_units": "necroDestroyer,necroWarden", "a_units": "tyranParasite,tyranTyrantGuard",
    },
    "CabalOfSorcerers": {
        "mow": "thousDaemonPrince",
        "etype": 1494, "ename": "CabalOfSorcerers_ExtraDamagePct",
        "p_units": "thousInfernalMaster,thousSorcerer", "a_units": "tyranParasite,tyranTyrantGuard",
    },
}


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _state_file(tag: str) -> Path:
    sf = ROOT / "logs" / "runners" / f"m1036-{tag}-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    return sf


def _run_build(argv, sf: Path):
    proc = subprocess.run([sys.executable, "rl_duel.py", "build", *argv, "--state-file", str(sf)],
                          cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, (proc.stderr or proc.stdout or "")[-600:]
    return int(json.loads(sf.read_text())["runnerId"]), None


def build_mythic_runner(nom: str, *, avec_montage: bool):
    """FIXTURE NOMMEE ET REUTILISABLE -- monte un runner portant la MoW de `nom`, avec ou sans les
    trois ecritures tertiaires du montage mythique (#999).

    Les DEUX bras injectent le porteur (il est HORS SEED dans les deux cas) ; seul le montage
    tertiaire change. Le bras `avec_montage=False` reprend EXACTEMENT le contre-bras de
    `probe_999_mythic_monte.py --sans-montage` : `catalog_inject.augment` NU, c'est-a-dire la
    primitive que `write_mythic_seed_bc` appelle AVANT `equip_mythic` -- donc le meme arbre moins
    les ecritures qu'on veut isoler. Rendre `(runnerId, cas)` ou `(None, raison)`.
    """
    cas = CAS[nom]
    argv = ["--seed", "777", "--board", "MC1_67",
            "--p-units", cas["p_units"], "--a-units", cas["a_units"], "--p-mow", cas["mow"]]
    if avec_montage:
        argv += ["--equip-mythic", cas["mow"]]
    else:
        import catalog_inject
        seed = catalog_inject._load_seed(None)
        bc, _added, _ab, _unres = catalog_inject.augment(seed, [cas["mow"]], rank=17)
        aug = _state_file(f"aug-{nom}").with_suffix(".bc.json")
        aug.write_text(json.dumps(bc), encoding="utf-8")
        argv += ["--seed-bc", str(aug)]
    return _run_build(argv, _state_file(nom if avec_montage else f"nu-{nom}"))


@pytest.fixture(scope="module", params=sorted(CAS))
def mythic_runner(request, live_session, rpc):
    """Le bras AVEC montage, partage par les etages 1 et 3 (un runner par ability, pas six)."""
    nom = request.param
    rid, err = build_mythic_runner(nom, avec_montage=True)
    if rid is None:
        pytest.skip(f"build KO ({nom}) : {err}")
    yield nom, rid
    rpc("disposeRunner", {"runnerId": rid}, 20)


@pytest.fixture(scope="module", params=sorted(CAS))
def mythic_runner_sans_montage(request, live_session, rpc):
    """Le CONTRE-BRAS : porteur injecte, aucune ecriture tertiaire."""
    nom = request.param
    rid, err = build_mythic_runner(nom, avec_montage=False)
    if rid is None:
        pytest.skip(f"build KO contre-bras ({nom}) : {err}")
    yield nom, rid
    rpc("disposeRunner", {"runnerId": rid}, 20)


def _mow_row(rpc, rid, mow):
    """La MoW vit dans `decisionView.mows` (HORS-PLATEAU : ni PV ni tuile), pas dans `units`."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv):
        return None, None
    row = next((m for m in (dv.get("mows") or [])
                if m.get("casterId") is not None and m.get("visualId") == mow), None)
    return row, dv


def _eff(row, etype):
    return next((e for e in ((row or {}).get("effects") or [])
                 if e.get("effectType") == etype), None)


# ==================================================== (1) LIVE : l'owner-effect est pose a l'init

def test_owner_effect_pose_a_l_init_live(mythic_runner, rpc):
    nom, rid = mythic_runner
    cas = CAS[nom]
    row, _ = _mow_row(rpc, rid, cas["mow"])
    if row is None:
        pytest.skip(f"MoW {cas['mow']} absente de decisionView.mows")
    e = _eff(row, cas["etype"])
    assert e is not None, (
        f"{cas['etype']} absent de la MoW {cas['mow']} : effets publies = "
        f"{[(x.get('effectType'), x.get('name')) for x in (row.get('effects') or [])]}")
    assert e.get("name") == cas["ename"], e
    # `AddEffect(..., turns/options = <Nullable ZERO>)` -> aucune duree -> effet PERMANENT.
    assert int(e.get("remaining") or 0) == 0, (
        f"remaining={e.get('remaining')} : le natif pose SANS TurnsFromRounds (permanent)")


# ============================================ (2) CONTRE-EPREUVE : sans le montage, aucun effet

def test_sans_le_montage_aucun_owner_effect_live(mythic_runner_sans_montage, rpc):
    """Le regime est-il SEPARANT ? Le porteur est la DANS LES DEUX BRAS (il est injecte des deux
    cotes) ; seules les trois ecritures tertiaires changent. Sans cet etage, l'etage 1 mesurerait
    l'absence du PORTEUR et non celle du MONTAGE."""
    nom, rid = mythic_runner_sans_montage
    cas = CAS[nom]
    row, _ = _mow_row(rpc, rid, cas["mow"])
    if row is None:
        pytest.skip(f"MoW {cas['mow']} absente de decisionView.mows (contre-bras)")
    assert _eff(row, cas["etype"]) is None, (
        f"{cas['etype']} present SANS montage tertiaire -- le montage ne separe pas ; "
        f"effets = {[(x.get('effectType'), x.get('name')) for x in (row.get('effects') or [])]}")


# =========================================== (3) le PORT voit la MEME instance sur le MEME etat

def test_le_port_voit_l_owner_effect_live_offline(mythic_runner, rpc):
    """`load_state` sur l'etat live -> la MoW porte l'instance cote PORT aussi.

    Deux canaux peuvent l'y mettre, et les DEUX comptent : la CAPTURE
    (`decisionView.mows[].effects`) et le SEED `ABILITY_INIT_OWNER_EFFECTS`, filet des chemins
    purement offline. Ce test verifie le RESULTAT, pas le canal -- c'est le cliquet offline
    (`tests/engine/test_1036_mythiques_owner_effect_offline.py`) qui garde l'entree de registre."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state

    nom, rid = mythic_runner
    cas = CAS[nom]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles") and _ok(dv) and _ok(ob) and _ok(snap)):
        pytest.skip("capture incomplete")
    row = next((m for m in (dv.get("mows") or [])
                if m.get("casterId") is not None and m.get("visualId") == cas["mow"]), None)
    if row is None:
        pytest.skip(f"MoW {cas['mow']} absente de decisionView.mows")
    st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="evenq"))
    assert st.effects is not None
    mid = int(row["casterId"])
    inst = [e for e in st.effects.by_unit.get(mid, [])
            if e.effect_type == cas["etype"] and not e.consumed]
    assert inst, (
        f"le PORT ne porte aucune instance {cas['etype']} sur la MoW {mid} : "
        f"{[(e.effect_type, e.name) for e in st.effects.by_unit.get(mid, [])]}")
    assert inst[0].remaining_turns in (None, 0), (
        f"duree portee {inst[0].remaining_turns} : l'effet natif est PERMANENT")
