"""#966-r3 -- GARDE de l'EXECUTION du cast de `1212 HealingBalms_Heal` (LIVE).

Le probe qui MESURE est `probe_966r3_execution_du_cast.py` ; ce fichier fige ce qu'il a etabli.

⚠ Le champ `FOYER` du residu nommait `tests/engine/test_966_healing_balms_combat_live.py` -- ce
fichier N'EXISTE PAS dans l'arbre (seul `test_966_healing_balms_offline.py` existe). Ce fichier-ci
le remplace, et le residu de suite (#966-r6) porte le bon chemin.

CE QUI EST GARDE, et pourquoi
------------------------------
1. LA FORME D'ACTION. `#966` avait envoye `{"kind":"ability","unitId","abilityId","targetId"}` et
   recu `ok = None`, sans mutation -- d'ou la conclusion « rien n'a ete execute ». La forme
   acceptee est celle que `rl_duel.py cmd_act` CONSTRUIT :
   `{"kind":"ability","casterId":<uid>,"targetId":<tid>,"abilityType":<aid>}`. Aucune des deux cles
   ne se devine ; ce test les fige.
2. LES TROIS EFFETS SONT POSES SUR LA CIBLE, pas sur le caster -- et leur source commune est le
   `TriggeredAbilityType` **1502**, pas les `EffectType` 1503/1504/1508 que l'enonce du residu
   citait. Qualifier l'enum est ici le seul canal ou la faute serait visible.
3. LES MAGNITUDES SONT RECOUPEES PAR DEUX CANAUX INDEPENDANTS : les EVENTS d'`applyAction` et le
   RPC `statModSources`. Un seul canal ne prouverait pas que la valeur est POSEE sur l'entite.
4. `decisionView.effects` est AVEUGLE a ces instances -- il rend `{}` sur la cible. Le test le
   MESURE au lieu de le subir : c'est exactement ce qui avait fait conclure a un no-op.
5. LE RE-ARMEMENT EST PARTIEL. Au re-cast, les deux stat-mods sont RETIRES puis re-poses sous de
   nouveaux ids (pas d'empilement), mais le marqueur `HealingBalms` ne l'est PAS : une seconde
   instance est posee EN PLUS. C'est un fait NATIF mesure, pas un choix de port.

Le montage tient en UNE bataille : `spaceWolfPriest` co-injecte, un allie adjacent, deux ennemis.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[2]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc            # noqa: E402

CASTER_VIS = "spaceWolfPriest"
ALLIE_VIS = "spaceBlackmane"
HEAL_ABILITY = 1212
SOURCE_TRIGGERED = 1502          # `TriggeredAbilityType` source des TROIS effets
NOMS = ("HealingBalms_ExtraCritDamage", "HealingBalms_ExtraCritChance", "HealingBalms")
MARQUEUR = "HealingBalms"        # celui que le `RemoveEffect` en tete d'arbre NE couvre PAS


def _res(out):
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _rc(sid, method, params, timeout=120):
    return _res(_rpc(sid, method, [params], timeout=timeout) or {}) or {}


def _events(ap_out):
    out = []
    for act in (ap_out.get("actions") or []):
        for ev in (act.get("events") or []):
            tags = ev.get("tags")
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:                                  # noqa: BLE001
                    tags = {}
            out.append((ev.get("kind"), ev.get("step"), ev.get("group"), ev.get("entity"),
                        ev.get("source"), tags or {}))
    return out


@pytest.fixture(scope="module")
def cast_966r3(tmp_path_factory):
    """UNE bataille, UN cast, UN re-cast. Rend le dictionnaire de tout ce qui a ete observe."""
    sf = tmp_path_factory.mktemp("966r3") / "state.json"
    seed_bc = tmp_path_factory.mktemp("966r3bc") / "bc.json"
    r = subprocess.run([sys.executable, "catalog_inject.py", "--units", CASTER_VIS,
                        "--out", str(seed_bc)], cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        pytest.skip("catalog_inject indisponible : %s" % (r.stderr or "")[-400:])
    rb = subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", "31337",
                         "--seed-bc", str(seed_bc), "--board", "MC1_67",
                         "--state-file", str(sf),
                         "--p-units", "%s,%s" % (CASTER_VIS, ALLIE_VIS),
                         "--a-units", "blackTerminator,blackAbaddon", "--hp-player", "200"],
                        cwd=str(PYDIR), capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    if rb.returncode != 0:
        pytest.skip("build refuse (drain ?) : %s" % (rb.stdout or "")[-400:])

    rid = (json.loads(sf.read_text(encoding="utf-8")).get("runnerId")
           or json.loads(sf.read_text(encoding="utf-8")).get("runner_id"))
    sid = _resolve_session()
    try:
        dv = _rc(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 2}, 240)
        caster = next((u for u in (dv.get("units") or [])
                       if u.get("visualId") == CASTER_VIS and u.get("alive")), None)
        allie = next((u for u in (dv.get("units") or [])
                      if u.get("visualId") == ALLIE_VIS and u.get("alive")), None)
        assert caster is not None and allie is not None, "montage : un porteur manque"
        cid, tid = int(caster["id"]), int(allie["id"])
        action = {"kind": "ability", "casterId": cid, "targetId": tid,
                  "abilityType": HEAL_ABILITY}
        ap1 = _rc(sid, "applyAction", {"runnerId": rid, "action": action}, 120)
        dv2 = _rc(sid, "decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 2}, 240)
        sms = _rc(sid, "statModSources", {"runnerId": rid, "unitId": tid}, 60)
        # Le cast pose `UnitStats_ActionsAvailable: 0` sur le caster : un RE-CAST IMMEDIAT n'est
        # PAS rejoue (mesure -- il ne rend que `group 12` + `finish`, zero retrait) et le test du
        # re-armement mesurerait alors le harnais, pas le natif. On lui rend la main d'abord.
        for _ in range(2):
            _rc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)
        ap2 = _rc(sid, "applyAction", {"runnerId": rid, "action": action}, 120)
        yield {"cid": cid, "tid": tid, "ap1": ap1, "ap2": ap2, "dv2": dv2, "sms": sms,
               "ev1": _events(ap1), "ev2": _events(ap2)}
    finally:
        _rc(sid, "disposeRunner", {"runnerId": rid}, 30)


def test_la_forme_d_action_est_acceptee(cast_966r3):
    ap1 = cast_966r3["ap1"]
    assert ap1.get("ok") is True, ap1
    acts = ap1.get("actions") or []
    assert acts and acts[0].get("ok") is True, acts
    assert len(cast_966r3["ev1"]) > 0, "aucun event : le cast n'a rien execute"


def test_les_trois_effets_sont_poses_sur_la_CIBLE(cast_966r3):
    """Et pas sur le caster -- c'est le discriminant que viser un ALLIE rend lisible."""
    tid, cid = cast_966r3["tid"], cast_966r3["cid"]
    poses = {}
    entite_courante = None
    for kind, _step, _grp, ent, source, tags in cast_966r3["ev1"]:
        if kind == "group" and source in NOMS:
            entite_courante = source
        if kind == "action" and tags.get("Effect_SourceId") is not None:
            poses.setdefault(entite_courante, []).append((ent, tags))
    assert set(poses) == set(NOMS), "effets poses : %r (attendus %r)" % (sorted(poses), NOMS)
    for nom, occurrences in poses.items():
        for ent, tags in occurrences:
            assert int(ent) == tid, "%s pose sur u%s au lieu de la cible u%d" % (nom, ent, tid)
            assert int(tags.get("Effect_SourceId")) == cid, tags
            assert int(tags.get("Effect_SourceTriggeredAbility")) == SOURCE_TRIGGERED, (
                "%s : source %r au lieu du TriggeredAbilityType %d"
                % (nom, tags.get("Effect_SourceTriggeredAbility"), SOURCE_TRIGGERED))


def test_les_magnitudes_sont_recoupees_par_DEUX_canaux(cast_966r3):
    """EVENTS d'`applyAction` vs RPC `statModSources`. Un seul canal ne prouverait pas la POSE."""
    par_event = {}
    for _k, _s, _g, _e, _src, tags in cast_966r3["ev1"]:
        for stat in ("CritDamage", "CritChance"):
            v = tags.get("UnitStats_%s_Modification" % stat)
            if v is not None and int(v) != 0:
                par_event[stat.lower()] = int(v)
    assert par_event, "aucune modification de stat dans les events : temoin DEGENERE"

    tid = cast_966r3["tid"]
    unite = next((u for u in (cast_966r3["sms"].get("units") or [])
                  if int(u.get("entityId", -1)) == tid), None)
    assert unite is not None, cast_966r3["sms"]
    mods = unite.get("mods") or {}
    for cle, attendu in (("critDamage", par_event.get("critdamage")),
                         ("critChance", par_event.get("critchance"))):
        if attendu is None:
            continue
        assert int((mods.get(cle) or {}).get("total")) == attendu, (cle, mods.get(cle), attendu)


def test_decisionView_est_AVEUGLE_a_ces_instances(cast_966r3):
    """Mesure, pas plainte : c'est ce canal muet qui avait fait conclure a un no-op. Si un jour il
    se met a les publier, ce test doit tomber pour qu'on le SACHE."""
    tid = cast_966r3["tid"]
    fx = [e for e in (cast_966r3["dv2"].get("effects") or [])
          if int(e.get("unitId", -1)) == tid]
    assert fx == [], ("decisionView publie desormais les effets de 1212 : %r -- mettre a jour la "
                      "case-doc et preferer ce canal aux events" % fx)


def test_le_re_armement_est_PARTIEL(cast_966r3):
    """Les deux stat-mods sont RETIRES puis re-poses ; le marqueur `HealingBalms`, lui, est pose EN
    PLUS. Fait NATIF, mesure -- le `RemoveEffect` en tete d'arbre ne le couvre pas."""
    poses2 = [source for kind, _s, _g, _e, source, _t in cast_966r3["ev2"]
              if kind == "group" and source in NOMS]
    retires = {tags.get("Effect_Id") for kind, step, _g, _e, _src, tags in cast_966r3["ev2"]
               if kind == "action" and step == 18 and tags.get("Effect_Id") is not None}
    assert retires, "aucun RETRAIT au re-cast : le RemoveEffect en tete d'arbre ne mord pas"
    assert poses2.count(MARQUEUR) >= 1, poses2
    # Le marqueur n'est jamais dans le lot RETIRE : on le verifie par son ABSENCE de tout groupe
    # de retrait, pas par un id fige (les ids d'entite-effet changent d'un run a l'autre).
    ids_marqueur = set()
    courant = None
    for kind, step, _g, _e, source, tags in cast_966r3["ev2"]:
        if kind == "group" and source in NOMS:
            courant = source
        if courant == MARQUEUR and tags.get("Effect_Id") is not None:
            ids_marqueur.add(tags["Effect_Id"])
    assert not (ids_marqueur & retires), (
        "le marqueur %s est desormais RETIRE au re-cast (%r) : le re-armement est devenu COMPLET, "
        "mettre a jour #966-r6" % (MARQUEUR, ids_marqueur & retires))
