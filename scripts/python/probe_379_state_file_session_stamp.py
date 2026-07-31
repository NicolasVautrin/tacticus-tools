"""Probe #379 -- un state-file peut-il piloter un runner d'une AUTRE session Frida ?

LA QUESTION BINAIRE
-------------------
Le fichier est PRIVE (il vit dans le `logs/` du worktree de son agent, et son chemin absolu
est la cle `owner` du harnais) -- mais l'ESPACE D'IDENTIFIANTS est PARTAGE : un seul registre
de runners, dans le script injecte, commun a tous les appelants RPC. #377/#395 a etabli que
`counter` y est strictement monotone, donc qu'un id perime se fait REFUSER... DANS une
session. Une (re)injection remet ce compteur a `0` pendant que les state-files SURVIVENT sur
disque. Question : un `--state-file` d'avant la fenetre peut-il alors piloter le runner de
QUELQU'UN D'AUTRE, sans erreur ni refus ?

REPONSE (avant ce correctif) : OUI. Rien dans `rl_duel.py` ne rattachait un state-file a une
session. Et ce sont les PETITS numeros le danger : les ids sont distribues en ordre CROISSANT,
donc un id BAS (2, 5, 12) tenu a travers la fenetre devient collisionnable en QUELQUES
MINUTES, tandis qu'un id HAUT (261) reste refuse longtemps. Un test qui exercerait un id eleve
ne verrait qu'un refus benin et conclurait a tort que la garde ne sert a rien.

LE CORRECTIF, ET SON TRI-ETAT
-----------------------------
`scripts/python/runner_state.py` estampe le state-file du triplet `/api/admin/status`
(`id`, `pid`, `startedAt`) au `build`, et le reconfronte a chaque relecture :

    MATCH            -> passe, SILENCIEUX
    MISMATCH         -> REFUS franc (nomme l'estampille et la session courante)
    UNSTAMPED_STALE  -> REFUS franc  (pas d'estampille, mais mtime ANTERIEUR au startedAt
                                      de la session : l'anteriorite PROUVE la divergence)
    UNSTAMPED        -> AVERTISSEMENT non bloquant -- "non verifiable", jamais "OK"

CE QUE CE CLIQUET GARDE (etape 0, statique, AUCUNE session requise)
-------------------------------------------------------------------
La garde n'est pas une propriete declaree : elle tient a QUATRE cablages dans `rl_duel.py`,
chacun perdable en une ligne, et dont la perte est SILENCIEUSE (aucun test ne rougirait) :

  G1  `_save_state` passe son payload par `runner_state.stamp`   -> sans lui, plus rien n'est
      estampe, et tous les fichiers retombent en UNSTAMPED : la garde s'eteint sans bruit ;
  G2  `_load_state` appelle `verify` PUIS `enforce`, et `sys.exit(2)` sur refus ;
  G3  le `disposeRunner` de `cmd_build` -- LE site le plus dangereux, il frappe un id relu
      sur disque -- est garde par le verdict (`.ok`) ;
  G4  `cmd_attach` confronte son `--from` : sans ca, un id perime serait recopie dans un
      state-file NEUF et recevrait une estampille FRAICHE -- le mensonge deviendrait
      indetectable en aval ;
  G5  tout module TIERS qui ecrit un state-file via `rl_duel._save_state` pose `SESSION`.
      `SESSION` est un global de `rl_duel` pose par son `main()` ; un module qui refait son
      propre build en le court-circuitant (`_wave_build.py`) laisserait `SESSION` a `None`,
      `stamp` n'ecrirait rien, et la garde ne garderait rien -- sans erreur ni refus.
      Lu par AST : un balayage textuel s'attrape LUI-MEME sur les commentaires qui citent
      `X._save_state(` (mesure faite en ecrivant ce probe).

ETAPE 1 (offline, toujours jouee) -- les quatre etats, sur des fichiers fabriques
--------------------------------------------------------------------------------
Fabrique un state-file par etat et verifie le verdict ET la decision (`enforce`). C'est la
demonstration que les quatre etats sont bien QUATRE, et notamment qu'"absente" ne se lit
jamais comme une validation.

ETAPE 2 (--live, OPT-IN) -- le refus vu ROUGE de bout en bout
------------------------------------------------------------
Monte un runner A SOI, falsifie l'estampille de son state-file avec un id de session VOISIN
(et un `runnerId` BAS, celui qui est reellement collisionnable), et verifie que `view` sort en
rc 2 en NOMMANT les deux sessions -- puis restaure et dispose SON runner. Ne touche jamais un
runner d'autrui : la falsification porte sur l'estampille, pas sur l'id vise.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PYDIR))

import runner_state  # noqa: E402

DUEL_REL = "scripts/python/rl_duel.py"


# ---- etape 0 : cablage statique ------------------------------------------- #

def _func_body(src: str, name: str) -> str | None:
    """Corps d'une fonction de premier niveau (`def <name>(` en colonne 0)."""
    m = re.search(r"^def %s\(" % re.escape(name), src, re.M)
    if m is None:
        return None
    rest = src[m.start():]
    nxt = re.search(r"^(?:def |class |# ====)", rest[1:], re.M)
    return rest[:nxt.start() + 1] if nxt else rest


def scan_guard_sites(root: Path) -> list[str]:
    """Violations de G1..G4 dans `rl_duel.py`. Liste VIDE = cablage intact."""
    path = root / DUEL_REL
    if not path.exists():
        return [f"G0 {DUEL_REL} INTROUVABLE sous {root.as_posix()} -- rien n'a ete verifie"]
    src = path.read_text(encoding="utf-8")
    bad: list[str] = []

    save = _func_body(src, "_save_state")
    if save is None:
        bad.append("G1 `_save_state` introuvable")
    elif "runner_state.stamp(" not in save:
        bad.append("G1 `_save_state` n'estampe plus (pas de `runner_state.stamp(`) -- "
                   "les state-files repartent SANS estampille, la garde s'eteint en silence")

    load = _func_body(src, "_load_state")
    if load is None:
        bad.append("G2 `_load_state` introuvable")
    else:
        if "runner_state.verify(" not in load or "runner_state.enforce(" not in load:
            bad.append("G2 `_load_state` ne confronte plus le state-file a la session "
                       "(`runner_state.verify` + `runner_state.enforce` attendus)")
        # La sortie doit suivre l'`enforce` -- pas n'importe ou dans la fonction. Elle en
        # contient deja une (state-file absent) qui masquerait la disparition de l'autre.
        elif "sys.exit(2)" not in load[load.index("runner_state.enforce("):]:
            bad.append("G2 `_load_state` ne SORT plus sur refus (`sys.exit(2)` attendu "
                       "APRES l'`enforce`) -- un refus qui n'arrete rien n'est pas un refus")

    build = _func_body(src, "cmd_build")
    if build is None:
        bad.append("G3 `cmd_build` introuvable")
    else:
        disp = [ln for ln in build.splitlines() if '"disposeRunner"' in ln]
        if not disp:
            bad.append("G3 `cmd_build` ne dispose plus l'ancien runner -- verifier que le "
                       "site garde n'a pas ete deplace hors de cette fonction")
        elif "runner_state.verify(" not in build or ".ok" not in build:
            bad.append("G3 le `disposeRunner` de `cmd_build` n'est plus garde par un verdict "
                       "de session -- il frappe un id relu sur DISQUE, qui peut designer le "
                       "runner d'un AUTRE agent apres un reinject")

    att = _func_body(src, "cmd_attach")
    if att is None:
        bad.append("G4 `cmd_attach` introuvable")
    elif "runner_state.enforce(" not in att or "runner_state.verify(" not in att:
        bad.append("G4 `cmd_attach` ne confronte plus son `--from` -- un id perime serait "
                   "recopie dans un state-file NEUF avec une estampille FRAICHE")

    bad += _scan_external_writers(root)
    return bad


def _scan_external_writers(root: Path) -> list[str]:
    """G5 -- tout module TIERS qui ecrit un state-file via `rl_duel` doit poser `SESSION`.

    `SESSION` est un global de `rl_duel`, pose par son `main()`. Un module qui importe
    `rl_duel` et appelle `_save_state` SANS passer par `main()` (c'est le cas de
    `_wave_build.py`, qui refait son propre `build`) laisserait `SESSION` a `None` :
    `stamp` n'ecrirait rien et le fichier produit resterait indefiniment "non verifiable".
    Panne SILENCIEUSE -- ni erreur, ni refus, juste une garde qui ne garde rien.
    """
    out: list[str] = []
    pydir = root / "scripts" / "python"
    if not pydir.is_dir():
        return out
    for p in sorted(pydir.glob("*.py")):
        if p.name in ("rl_duel.py", "runner_state.py"):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        # Lecture par AST, pas par regex : un balayage textuel s'attrape LUI-MEME sur les
        # commentaires et docstrings qui CITENT `X._save_state(` -- mesure faite.
        writes = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == "_save_state" for n in ast.walk(tree))
        if not writes:
            continue
        poses = any(isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Attribute) and t.attr == "SESSION"
                            for t in n.targets)
                    for n in ast.walk(tree))
        if not poses:
            out.append(f"G5 {p.name} ecrit un state-file via rl_duel._save_state sans "
                       f"poser `SESSION` -- le fichier produit ne sera PAS estampe")
    return out


# ---- etape 1 : les quatre etats, offline ---------------------------------- #

_IDENT = runner_state.SessionIdentity(id=7, pid=4242,
                                      started_at="2026-07-31T10:00:00.000Z")


def _write(tmp: Path, name: str, payload: dict, mtime: float | None = None) -> Path:
    p = tmp / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    if mtime is not None:
        os.utime(p, (mtime, mtime))
    return p


def check_tristate(tmp: Path) -> list[str]:
    """Un state-file par etat -> (etat attendu, decision attendue). Violations rendues."""
    tmp.mkdir(parents=True, exist_ok=True)
    # startedAt = 2026-07-31T10:00:00Z ; on place les mtime de part et d'autre.
    t_started = 1785492000.0            # epoch de reference (valeur exacte sans importance)
    cases = []

    ok = runner_state.stamp({"runnerId": 3}, _IDENT)
    cases.append(("MATCH", runner_state.MATCH, True,
                  _write(tmp, "match.json", ok, t_started + 60)))

    other = dict(_IDENT.as_dict())
    other["id"] = 8
    cases.append(("MISMATCH id", runner_state.MISMATCH, False,
                  _write(tmp, "mismatch_id.json",
                         {"runnerId": 3, runner_state.SESSION_KEY: other},
                         t_started + 60)))

    # MEME id, host redemarre : seul `startedAt` trahit. C'est le cas qu'une estampille
    # reduite au `sessionId` validerait a tort.
    restarted = dict(_IDENT.as_dict())
    restarted["startedAt"] = "2026-07-30T08:00:00.000Z"
    cases.append(("MISMATCH startedAt", runner_state.MISMATCH, False,
                  _write(tmp, "mismatch_started.json",
                         {"runnerId": 3, runner_state.SESSION_KEY: restarted},
                         t_started + 60)))

    cases.append(("UNSTAMPED", runner_state.UNSTAMPED, True,
                  _write(tmp, "unstamped.json", {"runnerId": 3}, t_started + 60)))

    cases.append(("UNSTAMPED_STALE", runner_state.UNSTAMPED_STALE, False,
                  _write(tmp, "stale.json", {"runnerId": 3}, t_started - 3600)))

    bad: list[str] = []
    print("  %-22s %-16s %-8s %s" % ("cas", "etat", "passe?", "fichier"))
    for label, want_state, want_ok, path in cases:
        v = runner_state.verify(json.loads(path.read_text(encoding="utf-8")), _IDENT, path)
        print("  %-22s %-16s %-8s %s" % (label, v.state, str(v.ok), path.name))
        if v.state != want_state:
            bad.append(f"{label}: etat {v.state}, attendu {want_state}")
        if v.ok != want_ok:
            bad.append(f"{label}: passe={v.ok}, attendu {want_ok}")

    # Une identite courante ILLISIBLE ne doit jamais rendre MATCH.
    v = runner_state.verify(ok, None, None)
    if v.state == runner_state.MATCH:
        bad.append("session illisible: rend MATCH -- une comparaison qui n'a pas eu lieu "
                   "ne peut pas conclure a la concordance")
    # Et l'avertissement UNSTAMPED ne doit jamais se lire comme une validation.
    txt = runner_state.render(runner_state.verify({"runnerId": 3}, _IDENT,
                                                  tmp / "unstamped.json"), "probe")
    if "NON VERIFIABLE" not in txt or "PAS une validation" not in txt:
        bad.append("UNSTAMPED: le message ne dit pas qu'il n'est PAS une validation")
    return bad


# ---- etape 2 : live -------------------------------------------------------- #

def _run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=str(PYDIR), timeout=timeout,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def live(board: str, seed: int) -> list[str]:
    """Build a SOI -> falsification de l'estampille -> refus vu -> restauration -> dispose."""
    bad: list[str] = []
    sf = ROOT / "logs" / "runners" / f"_probe379_{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    ident = runner_state.current_identity()
    print(f"  session courante : {ident.label() if ident else '(illisible)'}")
    if ident is None:
        return ["session courante ILLISIBLE -- etape 2 non jouee (host muet)"]

    r = _run(["rl_duel.py", "build", "--seed", str(seed), "--board", board,
              "--state-file", str(sf)])
    if r.returncode != 0:
        return [f"build rc={r.returncode} :\n{(r.stderr or r.stdout)[-1200:]}"]
    st = json.loads(sf.read_text(encoding="utf-8"))
    rid = st.get("runnerId")
    print(f"  build OK -- runnerId={rid}, estampille={st.get(runner_state.SESSION_KEY)}")

    if runner_state.SESSION_KEY not in st:
        bad.append("le `build` n'a PAS estampe le state-file")

    v = runner_state.verify(st, ident, sf)
    if v.state != runner_state.MATCH:
        bad.append(f"state-file frais : etat {v.state}, attendu MATCH")
    r = _run(["rl_duel.py", "status", "--state-file", str(sf)])
    if r.returncode != 0:
        bad.append(f"`status` sur state-file CONCORDANT refuse (rc={r.returncode}) -- "
                   f"faux refus :\n{(r.stderr or '')[-800:]}")

    # --- falsification. `runnerId` BAS : c'est CELUI-LA qui est reellement collisionnable
    # apres un reinject (les ids sont distribues en ordre croissant, le compteur repart de
    # 0 et rattrape un petit numero en quelques minutes). Un id HAUT ne montrerait qu'un
    # `runner N not found` benin et ferait croire la garde inutile.
    forged = dict(st)
    forged["runnerId"] = 2
    stale = dict(ident.as_dict())
    stale["id"] = max(1, ident.id - 1)
    stale["startedAt"] = "2026-01-01T00:00:00.000Z"
    forged[runner_state.SESSION_KEY] = stale
    sf.write_text(json.dumps(forged), encoding="utf-8")

    for cmd in ("view", "status", "dispose"):
        r = _run(["rl_duel.py", cmd, "--state-file", str(sf)])
        out = (r.stderr or "") + (r.stdout or "")
        if r.returncode == 0:
            bad.append(f"`{cmd}` ACCEPTE un state-file d'une autre session (rc=0)")
        elif "REFUS" not in out:
            bad.append(f"`{cmd}` sort rc={r.returncode} sans message de refus lisible")
        elif str(ident.id) not in out or str(stale["id"]) not in out:
            bad.append(f"`{cmd}` : le refus ne NOMME pas les deux sessions "
                       f"(attendue {stale['id']}, courante {ident.id})")
        else:
            print(f"  `{cmd}` REFUSE (rc={r.returncode}) -- refus franc, deux sessions "
                  f"nommees")

    # --- estampille ABSENTE + fichier ANTERIEUR : refus, sans estampille du tout.
    naked = {k: v for k, v in st.items() if k != runner_state.SESSION_KEY}
    sf.write_text(json.dumps(naked), encoding="utf-8")
    old = time.time() - 86400
    os.utime(sf, (old, old))
    r = _run(["rl_duel.py", "status", "--state-file", str(sf)])
    if r.returncode == 0:
        bad.append("`status` ACCEPTE un state-file SANS estampille et ANTERIEUR a la "
                   "session -- l'etat 'absente' se lit alors comme une validation")
    else:
        print(f"  UNSTAMPED_STALE REFUSE (rc={r.returncode})")

    # --- estampille ABSENTE, fichier RECENT : avertissement, PAS de refus (un agent qui a
    # build avant la garde puis rebase mi-run doit continuer a piloter son runner).
    sf.write_text(json.dumps(naked), encoding="utf-8")
    r = _run(["rl_duel.py", "status", "--state-file", str(sf)])
    if r.returncode != 0:
        bad.append(f"`status` REFUSE un state-file sans estampille mais ecrit pendant la "
                   f"session courante (rc={r.returncode}) -- faux refus, il casserait les "
                   f"agents en vol")
    elif "NON VERIFIABLE" not in (r.stderr or ""):
        bad.append("l'etat UNSTAMPED passe SANS avertissement -- il se lit comme un OK")
    else:
        print("  UNSTAMPED : passe en AVERTISSANT (non bloquant)")

    # --- menage : restaurer l'estampille vraie, disposer MON runner (et lui seul).
    sf.write_text(json.dumps(st), encoding="utf-8")
    r = _run(["rl_duel.py", "dispose", "--state-file", str(sf)])
    print(f"  dispose runner {rid} : rc={r.returncode}")
    if r.returncode != 0:
        bad.append(f"dispose de MON runner refuse apres restauration (rc={r.returncode})")
    try:
        sf.unlink()
    except OSError:
        pass
    return bad


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--live", action="store_true", help="joue AUSSI l'etape 2 (build reel)")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", type=int, default=777)
    a = ap.parse_args(argv)

    rc = 0
    print("== etape 0 : cablage de la garde dans rl_duel.py (statique) ==")
    bad0 = scan_guard_sites(ROOT)
    for v in bad0:
        print(f"  ROUGE {v}")
    print("  OK -- G1..G5 intacts" if not bad0 else f"  {len(bad0)} violation(s)")
    rc |= 1 if bad0 else 0

    print("== etape 1 : les quatre etats (offline) ==")
    tmp = ROOT / "logs" / "probe379" / uuid.uuid4().hex[:8]
    bad1 = check_tristate(tmp)
    for v in bad1:
        print(f"  ROUGE {v}")
    print("  OK -- tri-etat conforme" if not bad1 else f"  {len(bad1)} violation(s)")
    rc |= 2 if bad1 else 0

    if a.live:
        print("== etape 2 : refus vu ROUGE de bout en bout (live) ==")
        bad2 = live(a.board, a.seed)
        for v in bad2:
            print(f"  ROUGE {v}")
        print("  OK -- refus franc et flux normal intact" if not bad2
              else f"  {len(bad2)} violation(s)")
        rc |= 4 if bad2 else 0
    else:
        print("== etape 2 : NON JOUEE (--live pour la jouer) ==")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
