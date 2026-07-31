"""CLIQUET #379 -- un state-file ne pilote JAMAIS le runner d'une autre session Frida.

Le fichier est PRIVE (il vit dans le `logs/` du worktree de son agent), mais l'ESPACE DE
`runnerId` est PARTAGE : un seul registre, dans le script injecte, commun a tous les agents.
#377/#395 a etabli que son compteur est strictement monotone -- donc qu'un id perime se fait
refuser -- mais SEULEMENT dans une session. Une (re)injection le remet a `0` alors que les
state-files survivent sur disque : l'id relu peut desormais designer le runner d'un AUTRE
agent, qui ne verrait ni erreur ni refus, seulement une bataille qui avance toute seule.

Ce test tient les deux moities du correctif :

  * le TRI-ETAT de `runner_state.py` -- et surtout que l'etat "estampille ABSENTE" ne se
    degrade jamais en "tout va bien" (meme discipline que `host_inputs`, ou `[introuvable]`
    reste distinct de `[vide]`) ;
  * le CABLAGE dans `rl_duel.py` (G1..G4), dont la perte serait SILENCIEUSE -- un
    `_save_state` qui n'estampe plus eteint la garde sans qu'aucune autre assertion ne bouge.

Les cas de MUTATION prouvent que le cliquet MORD : un cliquet dont on n'a jamais vu le rouge
ne garantit rien.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parents[1]          # scripts/python
ROOT = Path(__file__).resolve().parents[3]           # racine du checkout
sys.path.insert(0, str(PYDIR))

import probe_379_state_file_session_stamp as p379    # noqa: E402
import runner_state as rs                            # noqa: E402

IDENT = rs.SessionIdentity(id=7, pid=4242, started_at="2026-07-31T10:00:00.000Z")
T0 = 1785492000.0                                    # epoch de reference (valeur libre)


def _sf(tmp_path: Path, payload: dict, mtime: float) -> Path:
    p = tmp_path / "state.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


# ---- tri-etat -------------------------------------------------------------- #

def test_match_passes_silently(tmp_path):
    p = _sf(tmp_path, rs.stamp({"runnerId": 2}, IDENT), T0 + 60)
    v = rs.verify(json.loads(p.read_text(encoding="utf-8")), IDENT, p)
    assert v.state == rs.MATCH and v.ok and v.verified


def test_mismatch_on_session_id_refuses_and_names_both(tmp_path):
    """L'id BAS est le cas dangereux : apres un reinject le compteur y revient en minutes."""
    other = dict(IDENT.as_dict())
    other["id"] = IDENT.id - 1
    p = _sf(tmp_path, {"runnerId": 2, rs.SESSION_KEY: other}, T0 + 60)
    v = rs.verify(json.loads(p.read_text(encoding="utf-8")), IDENT, p)
    assert v.state == rs.MISMATCH and not v.ok
    txt = rs.render(v, "test")
    assert "REFUS" in txt
    assert f"id={other['id']}" in txt and f"id={IDENT.id}" in txt, txt
    assert "state-file PROPRE" in txt, "le refus ne dit pas quoi faire"


def test_mismatch_on_started_at_alone(tmp_path):
    """Host redemarre => `nextSessionId` repart a 1 : deux sessions peuvent partager l'`id`.

    Une estampille reduite au seul `sessionId` VALIDERAIT ici un state-file mort.
    """
    restarted = dict(IDENT.as_dict())
    restarted["startedAt"] = "2026-07-30T08:00:00.000Z"
    p = _sf(tmp_path, {"runnerId": 2, rs.SESSION_KEY: restarted}, T0 + 60)
    assert rs.verify(json.loads(p.read_text(encoding="utf-8")), IDENT, p).state == rs.MISMATCH


def test_unstamped_recent_passes_but_never_reads_as_ok(tmp_path):
    """Etat NON VERIFIABLE : passe (un agent qui rebase mi-run doit continuer), mais le dit."""
    p = _sf(tmp_path, {"runnerId": 2}, T0 + 60)
    v = rs.verify(json.loads(p.read_text(encoding="utf-8")), IDENT, p)
    assert v.state == rs.UNSTAMPED
    assert v.ok and not v.verified, "UNSTAMPED ne doit JAMAIS compter comme verifie"
    txt = rs.render(v, "test")
    assert "NON VERIFIABLE" in txt and "PAS une validation" in txt, txt
    assert "REFUS" not in txt


def test_unstamped_but_older_than_session_is_refused(tmp_path):
    """Ce qui rend l'etat "absente" OPERANT : le mtime prouve l'anteriorite.

    Au moment ou la garde entre en service, AUCUN state-file du disque n'est estampe -- donc
    l'etat le plus dangereux est justement celui que l'estampille ne sait pas juger.
    """
    p = _sf(tmp_path, {"runnerId": 2}, T0 - 3600)
    v = rs.verify(json.loads(p.read_text(encoding="utf-8")), IDENT, p)
    assert v.state == rs.UNSTAMPED_STALE and not v.ok
    assert "REFUS" in rs.render(v, "test")


def test_stale_margin_does_not_refuse_at_the_boundary(tmp_path):
    """Horloge FS != horloge host : on ne refuse qu'AU-DELA de la marge."""
    p = _sf(tmp_path, {"runnerId": 2}, T0 - rs.STALE_MARGIN_S / 2)
    assert rs.verify(json.loads(p.read_text(encoding="utf-8")), IDENT, p).state == rs.UNSTAMPED


def test_unreadable_session_never_reports_match(tmp_path):
    """Une comparaison qui N'A PAS EU LIEU ne peut pas conclure a la concordance."""
    p = _sf(tmp_path, rs.stamp({"runnerId": 2}, IDENT), T0 + 60)
    v = rs.verify(json.loads(p.read_text(encoding="utf-8")), None, p)
    assert v.state == rs.UNSTAMPED and not v.verified


def test_stamp_refuses_to_forge_from_an_unknown_identity():
    """Identite inconnue -> on n'ECRIT PAS d'estampille : elle mentirait a la relecture."""
    assert rs.SESSION_KEY not in rs.stamp({"runnerId": 2}, None)


def test_enforce_decides_per_state(capsys):
    """`enforce` : silencieux sur MATCH, bruyant partout ailleurs, bloquant sur les refus."""
    assert rs.enforce(rs.Verdict(rs.MATCH, IDENT, IDENT, None), "t") is True
    assert capsys.readouterr().err == "", "MATCH doit etre SILENCIEUX"
    for state, expect in ((rs.MISMATCH, False), (rs.UNSTAMPED_STALE, False),
                          (rs.UNSTAMPED, True)):
        assert rs.enforce(rs.Verdict(state, IDENT, None, None), "t") is expect
        assert capsys.readouterr().err, f"{state} doit etre IMPRIME"


# ---- cablage dans rl_duel.py (G1..G4) ------------------------------------- #

def test_guard_sites_are_wired():
    bad = p379.scan_guard_sites(ROOT)
    assert not bad, "la garde de session a saute dans rl_duel.py :\n  " + "\n  ".join(bad)


def _mutant_root(tmp_path: Path, old: str, new: str) -> Path:
    src = (ROOT / p379.DUEL_REL).read_text(encoding="utf-8")
    assert old in src, "motif de mutation absent de rl_duel.py : %r" % old
    dst = tmp_path / p379.DUEL_REL
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.replace(old, new, 1), encoding="utf-8")
    return tmp_path


def test_ratchet_bites_when_save_state_stops_stamping(tmp_path):
    """La regression la plus SILENCIEUSE : plus rien n'est estampe, tout retombe UNSTAMPED."""
    root = _mutant_root(tmp_path,
                        "json.dumps(runner_state.stamp(d, SESSION))", "json.dumps(d)")
    assert any(v.startswith("G1") for v in p379.scan_guard_sites(root))


def test_ratchet_bites_when_load_state_stops_verifying(tmp_path):
    root = _mutant_root(
        tmp_path,
        "    if not runner_state.enforce(runner_state.verify(st, SESSION, STATE), context):\n"
        "        sys.exit(2)\n",
        "")
    assert any(v.startswith("G2") for v in p379.scan_guard_sites(root))


def test_ratchet_bites_when_refusal_stops_exiting(tmp_path):
    """Un refus qui n'arrete rien n'est pas un refus."""
    root = _mutant_root(tmp_path,
                        "        sys.exit(2)\n    return st",
                        "        pass\n    return st")
    assert any(v.startswith("G2") for v in p379.scan_guard_sites(root))


def test_ratchet_bites_when_build_disposes_unconditionally(tmp_path):
    """LE site dangereux : `disposeRunner` sur un id relu sur DISQUE."""
    root = _mutant_root(tmp_path,
                        "        verdict = runner_state.verify(old, SESSION, STATE)",
                        "        verdict = None")
    assert any(v.startswith("G3") for v in p379.scan_guard_sites(root))


def test_ratchet_bites_when_attach_stops_checking_from(tmp_path):
    root = _mutant_root(
        tmp_path,
        "    if not runner_state.enforce(runner_state.verify(src, SESSION, src_path),\n"
        "                                \"rl_duel attach (--from)\"):\n"
        "        return 2\n",
        "")
    assert any(v.startswith("G4") for v in p379.scan_guard_sites(root))


def test_ratchet_bites_on_an_external_writer_without_session(tmp_path):
    """G5 -- un module tiers qui ecrit un state-file via `rl_duel` sans poser `SESSION`.

    `_wave_build.py` refait son propre `build` en court-circuitant `rl_duel.main()` : sans
    `RD.SESSION`, `stamp` n'ecrit rien et le fichier produit reste "non verifiable" a vie.
    """
    src = (ROOT / "scripts" / "python" / "_wave_build.py").read_text(encoding="utf-8")
    assert "RD.SESSION = runner_state.current_identity()" in src
    d = tmp_path / "scripts" / "python"
    d.mkdir(parents=True)
    (d / "_wave_build.py").write_text(
        src.replace("RD.SESSION = runner_state.current_identity()", "pass", 1),
        encoding="utf-8")
    assert any(v.startswith("G5") for v in p379._scan_external_writers(tmp_path))


def test_ratchet_reports_missing_file(tmp_path):
    """rl_duel.py introuvable => on le DIT, jamais un vert par defaut."""
    bad = p379.scan_guard_sites(tmp_path)
    assert bad and "INTROUVABLE" in bad[0]
