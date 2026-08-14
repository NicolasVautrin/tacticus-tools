"""#1035 -- CONFRONTATION LIVE de `HyperCorrosiveAcid` (mythique 1455 de `tyranBiovore`).

Ce que ce fichier etablit, et pourquoi il faut du LIVE pour l'etablir :

  1. le natif POSE bien `HyperCorrosiveAcid_ExtraDamagePct` (1448) sur un ennemi qui vient
     d'encaisser du degat d'une **Spore Mine amie**, et la duree observee est exactement
     `TurnsFromRounds(nrOfRounds = 1)` -- c'est-a-dire le nombre de joueurs du `turnOrder`, une
     donnee qui ne vit dans AUCUN chemin de code (elle depend du board et du roster) ;
  2. **CONTRE-BRAS** : le MEME montage SANS `--equip-mythic` rejoue les MEMES coups (memes
     degats au point pres) et ne pose RIEN. Sans lui, l'etage 1 pourrait mesurer un effet pose
     par un tout autre chemin ;
  3. l'`unitId` que le gate `IsUnitWithVisualId` compare (`"tyranSmnSporeMine"`, constante
     gameconfig) est bien le `visualId` que la mine SPAWNEE porte en bataille. C'est le seul
     etage qui puisse le dire : le gameconfig porte `visualId = null` pour cette entree, donc
     `VisualUnitIdFromUnitId` ne rend QUE l'id de config -- si le natif nommait la mine
     autrement en bataille, le gate serait FAUX en live et VRAI offline, silencieusement.

MONTAGE, et pourquoi celui-la (mesure de cette tranche) : une Spore Mine n'inflige du degat que
par deux voies, toutes deux hors de portee d'un `applyAction` direct (un summon s'OBSERVE, il ne
se COMMANDE pas) -- son attaque normale `FloatingDeath_NormalAttack` jouee par
`PlayAutomaticUnits` au turn-start, et l'explosion
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.FloatingDeath_AttackAbility`, dont le
`$$CreateTrigger` est `On(0x2 = PreUnitDeath_2, alive: 0) & get_OwnerIsTarget &
NOT TargetIsOverkilled`. Le `NOT TargetIsOverkilled` est ce qui rend le montage etroit : une mine
a 1664 PV et un ork la SURKILL, donc l'explosion n'a PAS lieu et rien n'est mesurable. D'ou
`--unit-stat "orksNob:Damage=1"` : l'ennemi survit, frappe sans surkiller, les mines ripostent, et
le vecteur `DamageTaken` existe enfin. Trois montages sans ce patch n'ont rien produit.

ASCII only.
"""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]            # scripts/python
ROOT = PYDIR.parents[1]                                # racine repo
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/hyper_corrosive_acid.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/registry.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/core.py",
        "scripts/python/engine/runner/operations/triggers/dispatch/attack.py",
        # Le MONTAGE de la mythique (voie TERTIAIRE) et le rail qui la publie au port.
        "scripts/python/rl_duel.py",
        "scripts/python/catalog_inject.py",
        "scripts/python/engine/runner/snapshot.py",
        # Le pipeline de degat PARTAGE : c'est lui qui emet `On(0x0f = DamageTaken)`.
        "scripts/python/engine/runner/operations/damage.py",
        "scripts/python/engine/runner/operations/effects.py",
    ),
    "build": True,
    "toujours": True,
    "raison": "Ce fichier confronte au LIVE une ability montee par une voie de SEED "
              "(`--equip-mythic` -> `BC.Units[].TertiaryAbility`) : le verdict depend du "
              "gameconfig (`nrOfRounds`, `unitId`), du seed BC, du board `MC1_67` et du nombre de "
              "joueurs (`ConvertRoundsToTurns`) -- des donnees qui vivent HORS de tout chemin de "
              "code enumerable.",
}

#: `EffectType` 0x5a8 -- l'effet que `$$CreateBehaviour` pose sur la victime.
HYPER_CORROSIVE = 1448
#: `ActiveAbilityType` 1144 -- `BioMinefield`, la seule voie qui spawne 3 mines EN UN cast.
BIO_MINEFIELD = 1144
MOW = "tyranBiovore"
ENNEMI = "orksNob"
#: La constante `unitId` du gameconfig de l'ability -- ce que le gate compare.
SPORE_MINE = "tyranSmnSporeMine"


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _run(*argv) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *argv], cwd=str(PYDIR), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def monter_biovore_et_declencher(rpc, with_mythic: bool):
    """MONTAGE NOMME ET REUTILISABLE des deux bras (cf. l'en-tete pour le POURQUOI de chaque
    piece). Rend `(runnerId, state_file, degats_des_mines)` ou `(None, raison, None)`.

    Sequence, identique dans les deux bras -- SEUL `--equip-mythic` change :
      1. build : MOI = 2 tyranids + la MoW `tyranBiovore` ; ADVERSE = un `orksNob` a `Damage=1` ;
      2. la MoW caste `BioMinefield` sur l'ennemi -> **3** Spore Mines adjacentes a lui
         (`nrOfSummons = 3` au gameconfig) ;
      3. fin de tour + tour IA : l'ennemi frappe une mine sans la surkiller, les mines ripostent
         -> le vecteur `On(0x0f = DamageTaken)` existe, `actor` = une mine, `target` = l'ennemi.
    """
    sf = ROOT / "logs" / "runners" / f"hca-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    argv = ["rl_duel.py", "build", "--seed", "777", "--board", "MC1_67",
            "--state-file", str(sf),
            "--p-units", "tyranParasite,tyranTyrantGuard", "--p-mow", MOW,
            "--a-units", ENNEMI,
            # L'ennemi doit SURVIVRE aux ripostes et ne pas SURKILLER les mines : sans ce patch,
            # `NOT TargetIsOverkilled` eteint `FloatingDeath` et rien n'est mesurable.
            "--unit-stat", f"{ENNEMI}:Damage=1"]
    if with_mythic:
        argv += ["--equip-mythic", MOW]
    proc = _run(*argv)
    if not sf.exists():
        return None, (proc.stderr or proc.stdout or "")[-400:], None
    rid = int(json.loads(sf.read_text())["runnerId"])
    ids = _ids(rpc, rid)
    if ids["mow"] is None or ids["ennemi"] is None:
        return rid, f"MoW ou ennemi absent du decisionView: {ids}", None
    cast = _run("rl_duel.py", "act", "ability", "--caster", str(ids["mow"]),
                "--target", str(ids["ennemi"]), "--ability", str(BIO_MINEFIELD),
                "--state-file", str(sf))
    if "apparu" not in (cast.stdout or ""):
        return rid, f"BioMinefield n'a spawne aucune mine: {(cast.stdout or '')[-300:]}", None
    _run("rl_duel.py", "act", "endturn", "--state-file", str(sf))
    ai = _run("rl_duel.py", "aiturn", "--state-file", str(sf))
    degats = [l.strip() for l in (ai.stdout or "").splitlines() if "->u" in l]
    return rid, str(sf), degats


def _ids(rpc, rid: int) -> dict:
    """Ids d'entite du porteur et de l'ennemi, lus sur le MEME canal que le port.

    ⚠ Une MACHINE OF WAR n'est PAS dans `decisionView.units` : elle est HORS-PLATEAU (ni PV ni
    tuile, cf. `snapshot._load_machines`) et vit dans `decisionView.mows`, clef `casterId`."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv):
        return {"mow": None, "ennemi": None}
    mow = next((m for m in (dv.get("mows") or [])
                if m.get("casterId") is not None and m.get("visualId") == MOW), None)
    ennemi = next((u for u in (dv.get("units") or [])
                   if u.get("visualId") == ENNEMI and u.get("alive")), None)
    return {"mow": (mow or {}).get("casterId"), "ennemi": (ennemi or {}).get("id")}


def _effets_de(rpc, rid: int, uid: int) -> list:
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv):
        return []
    u = next((x for x in (dv.get("units") or []) if x.get("id") == uid), {})
    return list(u.get("effects") or [])


def _ennemi_vivant(rpc, rid: int):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv):
        return None
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == ENNEMI and u.get("alive")), None)


def _mines(rpc, rid: int) -> list:
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    if not _ok(dv):
        return []
    return [u for u in (dv.get("units") or []) if u.get("visualId") == SPORE_MINE]


def _turn_count(rpc, rid: int) -> int:
    """`ConvertRoundsToTurns(1)` = nombre de joueurs du `turnOrder` hors Environment. Le port le
    lit dans `observeBattle.counts.player - 1` (`load_state`) : on prend la MEME source, pour que
    la comparaison de duree soit un lien port <-> live et non une constante recopiee."""
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    n = ((ob.get("counts") or {}).get("player") if _ok(ob) else None)
    return int(n) - 1 if n else 0


# ================================================ (1) le natif POSE 1448, et la duree est LUE

def test_une_spore_mine_amie_fait_poser_l_effet_live(live_session, rpc):
    rid, sf, degats = monter_biovore_et_declencher(rpc, with_mythic=True)
    if rid is None:
        pytest.skip(f"build KO: {sf}")
    try:
        if degats is None:
            pytest.skip(f"montage KO: {sf}")
        ennemi = _ennemi_vivant(rpc, rid)
        if ennemi is None:
            pytest.skip("l'ennemi est mort avant la mesure -- le regime ne separe rien")
        assert degats, ("aucun degat echange au tour IA : les mines n'ont pas riposte, "
                        "l'etage ne mesure rien")
        effets = _effets_de(rpc, rid, ennemi["id"])
        hca = next((e for e in effets if e.get("effectType") == HYPER_CORROSIVE), None)
        assert hca is not None, (
            f"aucun HyperCorrosiveAcid_ExtraDamagePct sur l'ennemi apres un degat de Spore Mine "
            f"(effets vus: {[e.get('effectType') for e in effets]})")
        attendu = _turn_count(rpc, rid)
        assert attendu > 0, "TEMOIN DEGENERE : ConvertRoundsToTurns(1) mesure 0"
        assert int(hca.get("remaining") or 0) == attendu, (
            f"duree {hca.get('remaining')} != TurnsFromRounds(nrOfRounds=1) = {attendu}")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)


# ================================================ (2) CONTRE-BRAS : sans la mythique, RIEN

def test_sans_la_mythique_aucun_effet_live(live_session, rpc):
    """Le regime est-il SEPARANT ? Meme seed, meme board, meme cast, memes coups -- seul
    `--equip-mythic` change. Si cet etage rendait AUSSI l'effet, l'etage 1 ne prouverait rien."""
    rid, sf, degats = monter_biovore_et_declencher(rpc, with_mythic=False)
    if rid is None:
        pytest.skip(f"build KO: {sf}")
    try:
        if degats is None:
            pytest.skip(f"montage KO: {sf}")
        assert degats, ("aucun degat echange au tour IA : le CONTRE-BRAS serait vert pour la "
                        "mauvaise raison (rien ne s'est passe)")
        ennemi = _ennemi_vivant(rpc, rid)
        if ennemi is None:
            pytest.skip("l'ennemi est mort avant la mesure -- le regime ne separe rien")
        effets = _effets_de(rpc, rid, ennemi["id"])
        assert not any(e.get("effectType") == HYPER_CORROSIVE for e in effets), (
            "HyperCorrosiveAcid_ExtraDamagePct pose SANS la mythique equipee -- le montage ne "
            "separe pas, et l'etage 1 ne prouve rien")
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)


# ============ (3) l'id que le GATE compare est bien celui que la mine PORTE en bataille

def test_le_visual_id_de_la_mine_est_celui_du_gate_live(live_session, rpc):
    """`IsUnitWithVisualId(Actor, VisualUnitIdFromUnitId(GetStringConstant(unitId)))`.

    Le gameconfig porte `visualId = null` pour `tyranSmnSporeMine`, donc le noeud formule ne rend
    QUE l'id de config. Si le natif nommait la mine autrement en bataille, le gate serait VRAI
    offline et FAUX en live, sans erreur -- c'est le seul etage qui puisse l'exclure."""
    from engine.runner.operations.triggers.loki.hyper_corrosive_acid import (   # noqa: PLC0415
        hyper_corrosive_unit_id)
    rid, sf, degats = monter_biovore_et_declencher(rpc, with_mythic=True)
    if rid is None:
        pytest.skip(f"build KO: {sf}")
    try:
        mines = _mines(rpc, rid)
        assert mines, ("aucune unite de `visualId == tyranSmnSporeMine` en bataille : soit le "
                       "spawn a echoue, soit le natif la nomme AUTREMENT -- dans les deux cas le "
                       "gate du port ne peut pas etre confronte")
        assert hyper_corrosive_unit_id() == SPORE_MINE
        assert all(m.get("visualId") == hyper_corrosive_unit_id() for m in mines)
    finally:
        rpc("disposeRunner", {"runnerId": rid}, 20)
