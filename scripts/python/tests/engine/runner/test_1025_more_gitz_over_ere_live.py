"""#1025 -- `MoreGitzOverEre` (MYTHIQUE 1456 de la MoW `orksRukkatrukk`), face POSE de l'
OWNER-EFFECT, CONFRONTEE AU LIVE. Port : entree `ABILITY_INIT_OWNER_EFFECTS["MoreGitzOverEre"]`
(`engine/entities/effects/factory.py`).

RE -- `frida/classes.tsv` : `MoreGitzOverEreAbility` derive d'
`IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` et n'override QUE `$$GetEffectType`
(corps ENTIER `return 0x5a9` = 1449). La base fait tout le reste :
    `$$CreateTrigger`   = OnOwnerSpecificAbilityInit(this.AbilityType)
    `$$CreateBehaviour` = If( CreateCondition(...),
                              AddEffect(GetEffectType(), AbilityState(Owner), source = Owner,
                                        targets = Owner, options = <Nullable ZERO>) )
-> owner-effect PERMANENT pose a l'INIT, patron `Vitarus` / `NornCrown` / `ToughToKill`.

TROIS ETAGES :
  1. LIVE, avec `--equip-mythic` : la MoW porte l'effet 1449, et sa duree est PERMANENTE
     (`remaining == 0`, mirror du `Nullable` d'options ZERO) ;
  2. **CONTRE-EPREUVE SEPARANTE** : sans `--equip-mythic`, la MoW ne porte RIEN de 1449 ;
  3. le PORT charge le MEME etat et voit la MEME instance -- c'est ce qui relie l'entree
     `ABILITY_INIT_OWNER_EFFECTS` au comportement natif.

NE COUVRE PAS -- residu `#1025-r1` : l'effet 1449 n'est PAS dans `EFFECT_CLASSES`, donc il ne
CONTRIBUE a aucun degat cote port. Ses DEUX faces natives sont gatees sur la RARETE :
  * `$$CreateEffectDamageBonusForAttack` = `ForPercentIncrease(get_OwnerIsTarget
    & AreFriends(Caster@+0x48, EffectSource) & HasRarity(Caster@+0x48, 5 = Mythic)
    & IsMeleeAttack & IsNormalAttack, ConfigVar(0xa = extraDmgPct))` ;
  * `$$CreateTargetSelector` = `Unique(Enemies(Owner, AdjacentUnits(Friends(Owner,
    UnitsWithVisualId(VisualUnitIdFromUnitId(Get(GetStringConstant(unitId = "orksSmnSquig"))))))
    + Filter(AllAliveUnits@+0x20, AmountIsEqualOrGreater(Friends(Owner, UnitsWithRarity(
    AdjacentUnits(ActiveTarget@+0x68), 5 = Mythic)), Direct(2)))))`
    -- la SECONDE branche compte les amis **Mythic** adjacents.
`HasRarity` / `UnitsWithRarity` lisent `GetBaseUnitComponent(e)+0x74` et rien d'autre ; aucun canal
`rarity` n'existe cote port. Ce fichier mesure la POSE, pas le BONUS. ASCII only.
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
        # Le MONTAGE de la mythique (voie TERTIAIRE).
        "scripts/python/rl_duel.py",
        "scripts/python/catalog_inject.py",
        # Le mirror d'enum dont l'ordinal 1449 est fige au site.
        "scripts/python/engine/entities/effect_type.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Le verdict depend du SEED BC et du gameconfig (`orksRukkatrukk.mythicAbilities`), "
              "pas seulement des chemins ci-dessus ; et il MESURE une pose native que le port "
              "recoit par DEUX canaux (capture + seed) -- un changement de l'un ou l'autre le "
              "concerne, mesure : ce test passe encore SANS l'entree `ABILITY_INIT_OWNER_EFFECTS` "
              "(c'est le cliquet OFFLINE qui la garde).",
}

MORE_GITZ = 1449                     # EffectType.MoreGitzOverEre_ExtraDamagePct (0x5a9)
MOW = "orksRukkatrukk"               # MoW porteuse, DANS les 8 MoW spawnables du pool rank 17
PYDIR = Path(__file__).resolve().parents[3]            # scripts/python
ROOT = PYDIR.parents[1]                                # racine repo


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _build(with_mythic: bool):
    sf = ROOT / "logs" / "runners" / f"moregitz-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(sf),
            "--board", "MC1_67", "--p-units", "orksRuntherd", "--p-mow", MOW,
            "--a-units", "tauCrisis,orksRuntherd"]
    if with_mythic:
        argv += ["--equip-mythic", MOW]
    proc = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, (proc.stderr or proc.stdout or "")[-400:]
    return int(json.loads(sf.read_text())["runnerId"]), None


def _mow_row(rpc, rid):
    """La MoW vit dans `decisionView.mows` (HORS-PLATEAU : ni PV ni tuile), pas dans `units`."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv):
        return None
    return next((m for m in (dv.get("mows") or [])
                 if m.get("casterId") is not None and m.get("visualId") == MOW), None)


def _eff(row, etype):
    return next((e for e in ((row or {}).get("effects") or [])
                 if e.get("effectType") == etype), None)


# ==================================================== (1) LIVE : l'owner-effect est pose a l'init

def test_owner_effect_pose_a_l_init_live(live_session, rpc):
    rid, err = _build(with_mythic=True)
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        row = _mow_row(rpc, rid)
        if row is None:
            pytest.skip("MoW absente de decisionView.mows")
        e = _eff(row, MORE_GITZ)
        assert e is not None, (
            f"1449 absent de la MoW : effets publies = "
            f"{[(x.get('effectType'), x.get('name')) for x in (row.get('effects') or [])]}")
        assert e.get("name") == "MoreGitzOverEre_ExtraDamagePct", e
        # `AddEffect(..., options = <Nullable ZERO>)` -> aucune duree -> effet PERMANENT.
        assert int(e.get("remaining") or 0) == 0, (
            f"remaining={e.get('remaining')} : le natif pose SANS TurnsFromRounds (permanent)")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)


# ============================================ (2) CONTRE-EPREUVE : sans la mythique, aucun 1449

def test_sans_la_mythique_aucun_owner_effect_live(live_session, rpc):
    """Le regime est-il SEPARANT ? Meme seed, meme board, meme MoW -- seul `--equip-mythic`
    change. Sans cet etage, l'etage 1 pourrait mesurer un effet pose par autre chose."""
    rid, err = _build(with_mythic=False)
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        row = _mow_row(rpc, rid)
        if row is None:
            pytest.skip("MoW absente de decisionView.mows")
        assert _eff(row, MORE_GITZ) is None, (
            "1449 present SANS la mythique equipee -- le montage ne separe pas")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)


# =========================================== (3) le PORT voit la MEME instance sur le MEME etat

def test_le_port_voit_l_owner_effect_live_offline(live_session, rpc):
    """`load_state` sur l'etat live -> la MoW porte l'instance 1449 cote PORT aussi.

    Deux canaux peuvent l'y mettre, et les DEUX comptent : la CAPTURE
    (`decisionView.mows[].effects`, toujours vraie ici puisque la `CreateActiveCondition` de la
    base est la constante VRAIE) et le SEED `ABILITY_INIT_OWNER_EFFECTS`, qui est le FILET des
    chemins purement offline. Ce test verifie le resultat, pas le canal."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state

    rid, err = _build(with_mythic=True)
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles") and _ok(dv) and _ok(ob) and _ok(snap)):
            pytest.skip("capture incomplete")
        row = next((m for m in (dv.get("mows") or [])
                    if m.get("casterId") is not None and m.get("visualId") == MOW), None)
        if row is None:
            pytest.skip("MoW absente de decisionView.mows")
        st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="evenq"))
        assert st.effects is not None
        mid = int(row["casterId"])
        inst = [e for e in st.effects.by_unit.get(mid, [])
                if e.effect_type == MORE_GITZ and not e.consumed]
        assert inst, (
            f"le PORT ne porte aucune instance 1449 sur la MoW {mid} : "
            f"{[(e.effect_type, e.name) for e in st.effects.by_unit.get(mid, [])]}")
        assert inst[0].remaining_turns in (None, 0), (
            f"duree portee {inst[0].remaining_turns} : l'effet natif est PERMANENT")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
