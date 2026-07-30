#!/usr/bin/env python
"""probe 269 -- d'ou `stream_events` tire ses ordinaux, et le decodage tient-il face au BRUT.

TROIS MESURES, toutes re-derivables, aucune valeur heritee :

  ETAPE 0 (offline) -- la SOURCE. Nomme le fichier lu par `stream_events`, dit s'il est
    versionne (`git check-ignore`) et donc present dans un worktree frais. C'est l'invariant
    « un worktree frais est RUNNABLE par son seul checkout » applique a ce chemin (#254b-a :
    le module lisait `frida/data/meta/<version>/enums.json`, GITIGNORE -> table vide -> le
    premier `rl_duel.py act` levait `KeyError: StepType.UnitDamaged` APRES avoir applique
    l'action).

  ETAPE 1 (offline) -- l'EQUIVALENCE avec l'artefact host, quand il est la. Compare membre
    par membre `data/symbols/<CURRENT>/frida/enums.tsv` et `frida/data/meta/<v>/enums.json`
    sur `IdunBattle.Streams.StepType` / `IdunBattle.Streams.GroupType`. C'est ce qui justifie
    d'avoir choisi la table versionnee : changer de source ne change AUCUNE valeur decodee.
    Artefact host absent (cas normal en worktree) -> etape NON VERIFIEE, jamais « verte ».

  ETAPE 2 (live, optionnelle) -- le DECODAGE contre le BRUT. Joue un tour IA sur un runner
    existant et confronte `analyze()` au comptage direct des ordinaux dans la cascade brute :
    len(damage) == #{step == step_id("UnitDamaged")}, idem deaths/RemoveUnit et
    effects/ReceiveEffect. Un decalage d'ordinal (le motif de la MAJ `rnca9r7q6c`, qui a
    retire `RestoreArmorInfo` et decale tout ce qui suit de -1) casse ICI.

USAGE
    python scripts/python/probe_269_stream_events_source.py                     # etapes 0+1
    python scripts/python/probe_269_stream_events_source.py --state-file <abs>  # + etape 2

Sortie 0 = tout ce qui etait verifiable est CONFORME ; 1 = ecart. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

import stream_events as SE  # noqa: E402

HOST_META = REPO / "frida" / "data" / "meta"


def etape0() -> list[str]:
    lignes = ["ETAPE 0 -- la SOURCE des ordinaux"]
    p = SE.source_path()
    lignes.append("  fichier lu      : %s" % p.as_posix())
    lignes.append("  present         : %s" % p.is_file())
    r = subprocess.run(["git", "check-ignore", "-q", str(p)], cwd=str(REPO))
    ignore = (r.returncode == 0)
    lignes.append("  gitignore       : %s" % ignore)
    if ignore or not p.is_file():
        lignes.append("  ECART : la source doit etre VERSIONNEE et presente -- sinon un worktree")
        lignes.append("          frais ne peut pas decoder un compte rendu d'applyAction.")
        return lignes
    lignes.append("  StepType        : %d membres" % len(SE._step_par_nom()))
    lignes.append("  GroupType       : %d membres" % len(SE._group_par_nom()))
    lignes.append("  OK -- decodable par le seul checkout")
    return lignes


def _host_enums() -> tuple[Path | None, dict]:
    """L'artefact host le plus recent, s'il existe (gitignore -> souvent absent)."""
    if not HOST_META.is_dir():
        return None, {}
    cands = sorted(HOST_META.glob("*/enums.json"),
                   key=lambda q: [int(x) if x.isdigit() else 0
                                  for x in q.parent.name.split(".")])
    if not cands:
        return None, {}
    best = cands[-1]
    return best, json.loads(best.read_text(encoding="utf-8"))


def etape1() -> tuple[list[str], bool, bool]:
    """(lignes, verifiee, conforme)."""
    lignes = ["ETAPE 1 -- equivalence table VERSIONNEE <-> artefact HOST"]
    chemin, host = _host_enums()
    if not host:
        lignes.append("  artefact host absent (%s) -- NON VERIFIEE" % HOST_META.as_posix())
        lignes.append("  (normal dans un worktree : frida/data/ est gitignore)")
        return lignes, False, True
    lignes.append("  artefact host   : %s" % chemin.as_posix())
    conforme = True
    for court, fq, tsv in (("StepType", SE.STEP_ENUM, SE._step_par_nom()),
                           ("GroupType", SE.GROUP_ENUM, SE._group_par_nom())):
        h = {k: int(v) for k, v in (host.get(court) or {}).get("values", {}).items()}
        if not h:
            lignes.append("  %-9s : absent de l'artefact host -- non comparable" % court)
            continue
        seul_h = sorted(set(h) - set(tsv))
        seul_t = sorted(set(tsv) - set(h))
        diff = sorted(k for k in set(h) & set(tsv) if h[k] != tsv[k])
        lignes.append("  %-9s : tsv=%d host=%d | seul_tsv=%d seul_host=%d ordinaux_divergents=%d"
                      % (court, len(tsv), len(h), len(seul_t), len(seul_h), len(diff)))
        if seul_h or seul_t or diff:
            conforme = False
            for k in diff[:8]:
                lignes.append("      %-28s tsv=%d host=%d" % (k, tsv[k], h[k]))
            if seul_t:
                lignes.append("      seul_tsv : %s" % ",".join(seul_t[:8]))
            if seul_h:
                lignes.append("      seul_host: %s" % ",".join(seul_h[:8]))
    lignes.append("  %s" % ("OK -- les deux sources disent la meme chose"
                            if conforme else "ECART -- une des deux tables est perimee"))
    return lignes, True, conforme


def etape2(state_file: Path) -> tuple[list[str], bool]:
    """Decodage confronte au BRUT sur une cascade LIVE. (lignes, conforme)."""
    import rl_collect_batch as R  # noqa: E402  (tire psycopg3 -> import paresseux)

    lignes = ["ETAPE 2 -- decodage confronte au BRUT (cascade live)"]
    st = json.loads(state_file.read_text(encoding="utf-8"))
    rid = st["runnerId"]
    sid = R._resolve_session()
    r = (R._rpc(sid, "aiPlayByUnit",
                [{"runnerId": rid, "maxTurns": 1, "maxActivations": 9999,
                  "maxPump": 2000, "captureEvents": True}], timeout=300).get("result") or {})
    cascade = r.get("cascade") or []
    lignes.append("  runner %d -- %d events, stop=%s" % (rid, len(cascade), r.get("stopReason")))
    if not cascade:
        lignes.append("  cascade VIDE -- rien a confronter (NON VERIFIEE)")
        return lignes, True

    # Comptage BRUT, par ordinal resolu depuis la table (jamais un litteral fige).
    brut = {}
    for nom in ("UnitDamaged", "RemoveUnit", "ReceiveEffect"):
        oid = SE.step_id(nom)
        brut[nom] = sum(1 for ev in cascade
                        if ev.get("kind") == "action" and ev.get("step") == oid)
    an = SE.analyze(cascade, [])
    paires = (("UnitDamaged", "damage"), ("RemoveUnit", "deaths"),
              ("ReceiveEffect", "effects"))
    conforme = True
    for nom, seau in paires:
        n_brut, n_dec = brut[nom], len(an[seau])
        etat = "OK" if n_brut == n_dec else "ECART"
        if n_brut != n_dec:
            conforme = False
        lignes.append("  %-14s brut=%-4d analyze[%s]=%-4d  %s" % (nom, n_brut, seau, n_dec, etat))
    # Un pas VOISIN ne doit RIEN alimenter : c'est le defaut de #254b-a (12 lu pour
    # RemoveUnit alors que 12 = ChangeStats sur ce build).
    for voisin in ("ChangeStats", "LoseEffect"):
        oid = SE.step_id(voisin)
        n = sum(1 for ev in cascade if ev.get("kind") == "action" and ev.get("step") == oid)
        lignes.append("  %-14s brut=%-4d (voisin : ne doit alimenter NI deaths NI effects)"
                      % (voisin, n))
    # Tout event 'action' doit porter un NOM connu (aucun repli `Step#N`).
    inconnus = sorted({ev.get("step") for ev in cascade
                       if ev.get("kind") == "action"
                       and SE.step_name(ev.get("step")).startswith("Step#")})
    lignes.append("  ordinaux SANS nom dans la table : %s" % (inconnus or "aucun"))
    if inconnus:
        conforme = False
    return lignes, conforme


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="probe 269 -- source des ordinaux stream_events")
    ap.add_argument("--state-file", help="chemin ABSOLU d'un state-file rl_duel (active l'etape 2)")
    a = ap.parse_args(argv)

    ok = True
    l0 = etape0()
    print("\n".join(l0))
    if any("ECART" in x for x in l0):
        ok = False
    print()
    l1, _vue1, c1 = etape1()
    print("\n".join(l1))
    ok = ok and c1
    if a.state_file:
        print()
        l2, c2 = etape2(Path(a.state_file))
        print("\n".join(l2))
        ok = ok and c2
    print()
    print("VERDICT : %s" % ("CONFORME" if ok else "ECART"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
