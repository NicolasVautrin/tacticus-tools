"""#1025 -- `ElectrochaffBackups` (MYTHIQUE 1454 de la MoW `tauBroadside`), face POSE, CONFRONTEE
AU LIVE. Port : `engine/runner/operations/triggers/loki/electrochaff_backups.py`.

MONTAGE -- `rl_duel build --p-mow tauBroadside --equip-mythic tauBroadside` (voie TERTIAIRE, #999).
`tauBroadside` est dans les **8 MoW spawnables** du pool rank 17 : aucune injection catalogue.

QUATRE ETAGES, et le TROISIEME est le seul qui puisse distinguer `Set` de `Add` :

  1. branche A `On(0x3e = EffectAdded) & TriggeringEffectIs(Markerlight)` -- le cast
     `TwinSmartMissileSystem` (1161) du Broadside pose un `Markerlight` sur sa cible ; l'Electrochaff
     s'enchaine DESSUS, sans qu'aucun degat ne soit requis ;
  2. **CONTRE-EPREUVE SEPARANTE** -- le MEME cast sur un runner monte SANS `--equip-mythic` pose le
     `Markerlight` et **RIEN d'autre**. Sans cet etage, l'etage 1 pourrait passer pour une raison
     qui n'a rien a voir avec la mythique (un effet homonyme, un seed) ;
  3. branche B `On(0x0f = DamageTaken) & IsRangedAttack()` -- une attaque normale RANGED pose
     l'Electrochaff sur la victime. MESURE : le natif emet **UN bloc par COUP** ; la duree observee
     reste celle d'UN `TurnsFromRounds(nrOfRounds)`, ce qui REFUTE `ChangeType.Add` ;
  4. le PORT sur le MEME etat pre-attaque : `Runner.Apply(AttackUnitMessage)` doit poser le meme
     effet, sur la meme cible, avec la meme duree.

NE COUVRE PAS -- et c'est le residu `#1025-r1` : le CANAL DE DEGAT de l'effet 1446
(`$$CreateDamageModifier` = `ForPercentDecrease(get_OwnerIsCaster & HasRarity(Target, 5 = Mythic) &
AreFriends(Target, EffectSource), ConfigVar(dmgReductionPct))`). Aucun canal `rarity` n'existe cote
port, donc l'effet reste hors `EFFECT_CLASSES` et ne modifie aucun degat -- ni live-vs-offline, ni
offline tout court. Ce fichier mesure la POSE, pas la REDUCTION.

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
        "scripts/python/engine/runner/operations/triggers/loki/electrochaff_backups.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/move_death.py",
        "scripts/python/probe_1025_electrochaff_port.py",
        # Le MONTAGE de la mythique (voie TERTIAIRE) et le rail qui la publie au port.
        "scripts/python/rl_duel.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/engine/runner/snapshot.py",
        # Le pipeline de degat PARTAGE : c'est lui qui emet `On(0x0f = DamageTaken)`.
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/damage_ops/*.py",
        "scripts/python/engine/runner/operations/effects.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Ce fichier confronte au LIVE le TRIGGER d'une ability montee par une voie de "
              "SEED (`--equip-mythic` -> `BC.Units[].TertiaryAbility`) : le verdict depend du "
              "gameconfig (`nrOfRounds`), du seed BC, du board `MC1_67` et du nombre de joueurs "
              "(`ConvertRoundsToTurns`), c'est-a-dire de donnees qui vivent HORS de tout chemin "
              "de code enumerable.",
}

ELECTROCHAFF = 1446                  # EffectType.ElectrochaffBackups_DamageReductionPct (0x5a6)
MARKERLIGHT = 1122                   # EffectType.Markerlight (0x462)
MOW = "tauBroadside"                 # MoW porteuse, DANS le pool rank 17
MISSILE = 1161                       # ActiveAbilityType TwinSmartMissileSystem (pose le Markerlight)
PYDIR = Path(__file__).resolve().parents[3]            # scripts/python
ROOT = PYDIR.parents[1]                                # racine repo


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _build(with_mythic: bool, extra=()):
    """Runner : MOI = `tauCrisis` + la MoW `tauBroadside` ; ADVERSE = `orksRuntherd` + `tauCrisis`.
    `--place` amene mon `tauCrisis` a portee de tir de l'ennemi (etage 3) sans avoir a bouger."""
    sf = ROOT / "logs" / "runners" / f"electrochaff-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", "777", "--state-file", str(sf),
            "--board", "MC1_67", "--p-units", "tauCrisis", "--p-mow", MOW,
            "--a-units", "orksRuntherd,tauCrisis", *extra]
    if with_mythic:
        argv += ["--equip-mythic", MOW]
    proc = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not sf.exists():
        return None, (proc.stderr or proc.stdout or "")[-400:]
    return int(json.loads(sf.read_text())["runnerId"]), None


def _view(rpc, rid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    return dv if _ok(dv) else {}


def _units(rpc, rid):
    return _view(rpc, rid).get("units") or []


def _effect(units, uid, etype):
    u = next((x for x in units if x.get("id") == uid), {})
    return next((e for e in (u.get("effects") or []) if e.get("effectType") == etype), None)


def _find(units, vis, team):
    return next((u for u in units if u.get("visualId") == vis and u.get("alive")
                 and u.get("team") == team), None)


def _mow_id(rpc, rid):
    """Une MACHINE OF WAR n'est PAS dans `decisionView.units` : elle est HORS-PLATEAU (ni PV ni
    tuile, cf. `snapshot._load_machines`) et vit dans `decisionView.mows`, clef `casterId`.
    La chercher dans `units` rendait un `skip` silencieux -- mesure de cette tranche."""
    dv = _view(rpc, rid)
    m = next((x for x in (dv.get("mows") or [])
              if x.get("casterId") is not None and x.get("visualId") == MOW), None)
    return m["casterId"] if m else None


def _cast(rpc, rid, cid, tid, ability):
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ability},
        "captureEvents": True}, 120)


def _turn_count(rpc, rid) -> int:
    """`ConvertRoundsToTurns(1)` = nombre de joueurs du `turnOrder` hors Environment. Le port le
    lit dans `observeBattle.counts.player - 1` (`load_state`) : on prend la MEME source, pour que
    la comparaison de duree soit un lien port <-> live et non une constante recopiee."""
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    n = ((ob.get("counts") or {}).get("player") if _ok(ob) else None)
    return int(n) - 1 if n else 0


# ============================================================ (1) branche A : Markerlight -> pose

def test_markerlight_pose_l_electrochaff_live(live_session, rpc):
    rid, err = _build(with_mythic=True)
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        units = _units(rpc, rid)
        mow, victime = _mow_id(rpc, rid), _find(units, "orksRuntherd", 2)
        if mow is None or victime is None:
            pytest.skip("MoW ou cible absente du board")
        assert _effect(units, victime["id"], ELECTROCHAFF) is None, (
            "l'effet est present AVANT tout cast : le montage ne separe rien")
        res = _cast(rpc, rid, mow, victime["id"], MISSILE)
        if not _ok(res):
            pytest.skip(f"cast {MISSILE} refuse: {res}")
        units = _units(rpc, rid)
        ml = _effect(units, victime["id"], MARKERLIGHT)
        ec = _effect(units, victime["id"], ELECTROCHAFF)
        assert ml is not None, "le cast n'a pas pose de Markerlight : l'etage ne teste rien"
        assert ec is not None, "Markerlight pose mais AUCUN ElectrochaffBackups (branche A morte)"
        attendu = _turn_count(rpc, rid)
        assert attendu > 0, "TEMOIN DEGENERE : ConvertRoundsToTurns(1) mesure 0"
        assert int(ec.get("remaining") or 0) == attendu, (
            f"duree {ec.get('remaining')} != TurnsFromRounds(nrOfRounds=1) = {attendu}")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)


# ================================================ (2) CONTRE-EPREUVE : sans la mythique, RIEN

def test_sans_la_mythique_seul_le_markerlight_est_pose_live(live_session, rpc):
    """Le regime est-il SEPARANT ? Meme seed, meme board, meme cast -- seul `--equip-mythic`
    change. Si cet etage rendait AUSSI l'Electrochaff, l'etage 1 ne prouverait rien."""
    rid, err = _build(with_mythic=False)
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        units = _units(rpc, rid)
        mow, victime = _mow_id(rpc, rid), _find(units, "orksRuntherd", 2)
        if mow is None or victime is None:
            pytest.skip("MoW ou cible absente du board")
        res = _cast(rpc, rid, mow, victime["id"], MISSILE)
        if not _ok(res):
            pytest.skip(f"cast {MISSILE} refuse: {res}")
        units = _units(rpc, rid)
        assert _effect(units, victime["id"], MARKERLIGHT) is not None, (
            "meme le Markerlight est absent : le cast n'a pas mordu, l'etage ne separe rien")
        assert _effect(units, victime["id"], ELECTROCHAFF) is None, (
            "ElectrochaffBackups pose SANS la mythique equipee -- le montage ne separe pas")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)


# ================================== (3) branche B : degat RANGED -> pose, et la duree REFUTE `Add`

def test_degat_ranged_pose_et_la_duree_refute_add_live(live_session, rpc):
    """Une attaque normale RANGED pose l'Electrochaff sur la victime. Le natif emet un bloc PAR
    COUP : si le behaviour accumulait (`ChangeType.Add`), la duree vaudrait `coups x turns`."""
    rid, err = _build(with_mythic=True, extra=("--place", "tauCrisis:4,6"))
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        units = _units(rpc, rid)
        tireur = _find(units, "tauCrisis", 1)
        victime = _find(units, "tauCrisis", 2)
        if tireur is None or victime is None or _mow_id(rpc, rid) is None:
            pytest.skip("tireur/cible/MoW absents du board")
        normal = next((a for a in (tireur.get("abilities") or [])
                       if a.get("kind") == "normal"), None)
        if normal is None:
            pytest.skip("pas d'attaque normale sur le tireur")
        assert _effect(units, victime["id"], ELECTROCHAFF) is None
        res = _cast(rpc, rid, tireur["id"], victime["id"], normal["id"])
        if not _ok(res) or not (res.get("actions") or [{}])[0].get("mutated"):
            pytest.skip(f"attaque normale refusee/no-op: {res}")
        units = _units(rpc, rid)
        ec = _effect(units, victime["id"], ELECTROCHAFF)
        assert _effect(units, victime["id"], MARKERLIGHT) is None, (
            "un Markerlight est present : cet etage mesurerait la branche A, pas la branche B")
        assert ec is not None, "aucun ElectrochaffBackups apres un degat RANGED (branche B morte)"
        attendu = _turn_count(rpc, rid)
        assert attendu > 0, "TEMOIN DEGENERE : ConvertRoundsToTurns(1) mesure 0"
        assert int(ec.get("remaining") or 0) == attendu, (
            f"duree {ec.get('remaining')} != {attendu} : le natif ACCUMULE (Add), or le port "
            f"mirrore ChangeType.Set")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)


# ================================================== (4) le PORT pose la meme chose sur le meme etat

def test_le_port_pose_le_meme_effet_live_offline(live_session, rpc):
    """Etat PRE-attaque charge dans le moteur Python, MEME attaque rejouee via
    `Runner.Apply(AttackUnitMessage)` -> l'effet 1446 doit apparaitre sur la MEME cible avec la
    MEME duree. C'est ce qui relie le trigger porte au vecteur natif mesure a l'etage 3."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.runner import Runner
    from engine.runner.messages import AttackUnitMessage
    from engine.runner.snapshot import load_state

    rid, err = _build(with_mythic=True, extra=("--place", "tauCrisis:4,6"))
    if rid is None:
        pytest.skip(f"build KO: {err}")
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            pytest.skip("boardGraph indispo")
        board = Board(bg["tiles"], adjacency="evenq")
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        ob = rpc("observeBattle", {"runnerId": rid}, 60)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
        if not (_ok(dv) and _ok(ob) and _ok(snap)):
            pytest.skip("capture incomplete")
        units = dv.get("units") or []
        tireur = _find(units, "tauCrisis", 1)
        victime = _find(units, "tauCrisis", 2)
        if tireur is None or victime is None:
            pytest.skip("tireur/cible absents")
        st = load_state(dv, ob, snap, board=board)
        # Le RNG est OBLIGATOIRE pour rejouer une attaque NORMALE (`damage_ops/normal.py` LEVE
        # sans lui) -- c'est ce qui fait de cet etage un vrai rejeu et non un no-op.
        from engine.runner.prng import IntBasedMersenneTwister
        s = rpc("dumpRng", {"runnerId": rid}, 30)
        if not (isinstance(s, dict) and s.get("mt")):
            pytest.skip("dumpRng indispo -- rejeu d'attaque normale impossible")
        rng = IntBasedMersenneTwister()
        rng.mt = list(s["mt"]); rng.mti = s["mti"]
        st.rng = rng
        # Le porteur DOIT etre inscrit cote port, sinon l'etage ne mesure rien : c'est le canal
        # TERTIAIRE (`unitAbilityStates`) qui l'apporte, lie en ambiant par la fixture live.
        from engine.runner.operations.triggers.dispatch.core import collect_triggered_abilities
        from engine.runner.operations.triggers.loki.electrochaff_backups import (
            ElectrochaffBackupsOnRangedDamageAbility)
        inscrits = [a for a in collect_triggered_abilities(st)
                    if isinstance(a, ElectrochaffBackupsOnRangedDamageAbility)]
        assert inscrits, ("la mythique n'est pas inscrite cote port : canal `tertiary_ability` "
                          "absent (le test ne mesurerait rien)")
        runner = Runner(st).install_default_handlers(20)
        runner.apply(AttackUnitMessage(tireur["id"], victime["id"]))
        assert st.effects is not None
        inst = next((e for e in st.effects.by_unit.get(int(victime["id"]), [])
                     if e.effect_type == ELECTROCHAFF and not e.consumed), None)
        assert inst is not None, "le PORT n'a pose aucun ElectrochaffBackups sur la victime"
        attendu = int((ob.get("counts") or {}).get("player") or 0) - 1
        assert attendu > 0
        assert inst.remaining_turns == attendu, (
            f"port: duree {inst.remaining_turns} != {attendu}")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
