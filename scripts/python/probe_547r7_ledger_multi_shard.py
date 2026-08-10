"""#547-r7 -- MESURE : le ledger MULTI-SHARD rend EXACTEMENT le ledger MONO-SHARD.

CE QU'IL MESURE, ET POURQUOI CETTE QUESTION-LA
-----------------------------------------------
`_ecrire_ledger` REFUSAIT d'ecrire des que `n_shards > 1`, et ce refus interdisait de rejouer le
ledger au merge en quelques minutes (mesure #547-r5 : merge median **1098 s en serie, 275 s a 4
shards, 139 s a 8**). La levee du refus est une ACCELERATION -- et une acceleration ne se juge pas
au chronometre : **une acceleration qui change un verdict est un bug, pas un gain**.

La question posee ici est donc binaire et se pose ENTREE PAR ENTREE :

    le ledger produit par N shards + consolidation est-il, champ par champ, celui que la
    passe MONO-SHARD aurait produit sur LE MEME ARBRE ?

CE QUI EST COMPARE, ET CE QUI EST EXCLU -- explicitement
--------------------------------------------------------
Comparer tout le fichier serait un faux rouge : deux passes ne partagent ni l'instant ni la duree.
Sont donc EXCLUS, et le probe les IMPRIME plutot que de les taire :

  * `_at`  -- l'horodatage de l'ecriture ;
  * `sec`  -- la duree mesuree du fichier de test.

Tout le reste est compare a l'IDENTIQUE, y compris ce qui porte la VALIDITE (`_blob`, `_depuis`,
`_base`) et ce qui porte le VERDICT (`verdict` + les 5 champs de bilan). Un ecart sur l'un
quelconque de ces champs est un ROUGE : c'est exactement la forme d'un verdict qui aurait change.

LE MONTAGE EST REEL, PAS SIMULE
--------------------------------
Un depot git JETABLE (tmpdir SYSTEME), ou l'on recopie `probe_457` et la CLOTURE DERIVEE de ses
imports (`probe_471._dependances_locales` -- meme foyer, pour la meme raison : une liste ecrite a
la main se perime au premier import ajoute). Le vrai binaire, le vrai pytest, le vrai git.

Les huit fichiers de test du faux depot couvrent les QUATRE verdicts du ledger -- `VERT`, `ROUGE`,
`VIDE` (tout skippe, le garde #455), `SETUP` (fixture qui leve) -- parce qu'un accord mesure sur
des verts seuls serait un accord en regime DEGENERE : il ne separerait pas << les deux chemins
ecrivent la meme chose >> de << les deux chemins ecrivent la meme chose FACILE >>.

ECRITURES : uniquement dans un tmpdir SYSTEME (`mkdtemp()` sans `dir=`). Le vrai depot n'est
jamais touche -- ni son ledger, ni ses poids, ni ses parts.

ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import ledger_vert_offline as ledger                                        # noqa: E402
import probe_471_tri_etat_cliquets as tri_etat                              # noqa: E402

PROBE_457 = _PYDIR / "probe_457_offline_tests_green.py"

#: Ce qui doit changer pour que ce probe puisse changer d'avis.
DECLENCHEUR = {
    "chemins": ("scripts/python/probe_457_offline_tests_green.py",
                "scripts/python/ledger_vert_offline.py",
                "scripts/python/probe_471_tri_etat_cliquets.py",
                "scripts/python/probe_547r7_ledger_multi_shard.py"),
    "build": False,
    "raison": "Il confronte le ledger ecrit par N shards a celui qu'ecrit la passe mono-shard. "
              "Son verdict ne depend que du mecanisme d'ecriture (`probe_457`, "
              "`ledger_vert_offline`) et du harnais de depot jetable qu'il emprunte a "
              "`probe_471`.",
}

#: Les huit fichiers du faux depot. QUATRE verdicts couverts -- cf. l'en-tete.
_FICHIERS = {
    "test_vert_a_offline.py": (
        '"""Temoin VERT. ASCII only."""\n\n\ndef test_un():\n    assert 1 + 1 == 2\n\n\n'
        'def test_deux():\n    assert "a".upper() == "A"\n'),
    "test_vert_b_offline.py": (
        '"""Temoin VERT. ASCII only."""\n\n\ndef test_trois():\n    assert sum([1, 2]) == 3\n'),
    "test_vert_c_offline.py": (
        '"""Temoin VERT. ASCII only."""\n\n\ndef test_quatre():\n    assert len("abc") == 3\n'),
    "test_vert_d_offline.py": (
        '"""Temoin VERT. ASCII only."""\n\n\ndef test_cinq():\n    assert max([3, 1]) == 3\n'),
    "test_vert_e_offline.py": (
        '"""Temoin VERT. ASCII only."""\n\n\ndef test_six():\n    assert sorted([2, 1]) == [1, 2]\n'),
    "test_rouge_offline.py": (
        '"""Temoin ROUGE -- il DOIT echouer. ASCII only."""\n\n\n'
        'def test_rouge_par_construction():\n    assert False, "rouge voulu"\n'),
    "test_vide_offline.py": (
        '"""Temoin VIDE -- tout skippe (garde #455). ASCII only."""\n\nimport pytest\n\n\n'
        '@pytest.mark.skip(reason="temoin de vert vacueux")\ndef test_saute():\n    assert True\n'),
    "test_setup_offline.py": (
        '"""Temoin SETUP -- la fixture leve, ce n est pas un echec d assertion. ASCII only."""\n\n'
        'import pytest\n\n\n@pytest.fixture\ndef montage():\n'
        '    raise RuntimeError("panne de montage voulue")\n\n\n'
        'def test_avec_montage(montage):\n    assert True\n'),
}

#: Champs EXCLUS de la comparaison, et la raison de chacun. Une exclusion muette serait une porte
#: par laquelle une divergence reelle passerait.
_EXCLUS = {
    "_at": "horodatage de l'ecriture -- deux passes ne partagent pas leur instant",
    "sec": "duree mesuree du fichier -- deux passes ne partagent pas leur chronometre",
}


def _git(base: Path, *argv) -> None:
    r = subprocess.run(["git", "-C", str(base), *argv], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("montage du faux depot : `git %s` rc=%d %s"
                           % (argv[0], r.returncode, (r.stderr or "")[:200]))


def _faux_depot(base: Path) -> Path:
    """Un depot git JETABLE portant `probe_457`, ses dependances DERIVEES, et les 8 temoins.

    COMMITE, contrairement au faux depot de `probe_471` : `_ecrire_ledger` exige un `HEAD` lisible
    (c'est le critere de rattachement d'une part a un arbre), et `git rev-parse HEAD` est muet tant
    qu'aucun commit n'existe. Un depot seulement `add`-e ferait donc mesurer le refus au lieu du
    mecanisme.
    """
    py = base / "scripts" / "python"
    (py / "tests").mkdir(parents=True)
    for src in sorted(tri_etat._dependances_locales(PROBE_457)):            # noqa: SLF001
        shutil.copy2(src, py / src.name)
    shutil.copy2(_PYDIR / "pytest.ini", py / "pytest.ini")
    for nom, contenu in _FICHIERS.items():
        (py / "tests" / nom).write_text(contenu, encoding="utf-8")

    # POIDS EGAUX, ECRITS. Sans fichier de poids, `bins_of` retombe sur le repli md5, qui repartit
    # par NOMBRE et peut laisser un shard VIDE sur 8 fichiers -- `probe_457` rend alors `FAIL shard
    # VIDE` (a raison : hors selection, un shard vide signe un perimetre effondre). La comparaison
    # mesurerait ce repli, pas le mecanisme d'ecriture.
    (base / "scripts").mkdir(parents=True, exist_ok=True)
    (base / "scripts" / "ratchets-457-durations.json").write_text(
        json.dumps({("tests/" + n): 1.0 for n in _FICHIERS}, indent=1, sort_keys=True) + "\n",
        encoding="utf-8")

    _git(base, "init", "-q")
    _git(base, "config", "user.email", "probe@547r7.local")
    _git(base, "config", "user.name", "probe 547r7")
    _git(base, "add", "-A")
    _git(base, "commit", "-q", "-m", "temoin 547r7")
    return base


def _env_du_faux(base: Path) -> dict:
    env = dict(os.environ)
    # Plafond git : sans lui, un scenario pourrait remonter au depot parent et mesurer autre chose.
    env["GIT_CEILING_DIRECTORIES"] = str(base.parent)
    # Echappatoire CONSCIENTE, comme `probe_471` : le refus de `probe_457` rend 99, soit le meme
    # code que << rien mesure >> -- sans elle, aucun scenario ne pourrait mordre.
    env["TACTICUS_ALLOW_RATCHETS"] = "1"
    # AUCUN jeton herite : chaque scenario pose le sien (ou pas). Un jeton du shell appelant
    # ferait passer le scenario << multi-shard SANS jeton >> pour un succes.
    env.pop(ledger.VAR_JETON, None)
    return env


def _jouer(base: Path, argv: list, env_extra: dict | None = None) -> tuple:
    py = base / "scripts" / "python"
    env = _env_du_faux(base)
    env.update(env_extra or {})
    debut = time.time()
    proc = subprocess.run([sys.executable, PROBE_457.name, *argv],
                          cwd=str(py), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return int(proc.returncode), (proc.stdout or "") + (proc.stderr or ""), time.time() - debut


def _ledger_de(base: Path) -> dict:
    entrees, anomalies = ledger.lire(base)
    if anomalies:
        print("       anomalies de lecture : %s" % "; ".join(anomalies[:3]))
    return entrees


def _comparer(mono: dict, multi: dict, verbeux: bool) -> int:
    """0 si les deux ledgers sont IDENTIQUES hors champs exclus, 1 sinon. Ecarts IMPRIMES."""
    ko = 0
    cles_mono, cles_multi = set(mono), set(multi)
    if cles_mono != cles_multi:
        ko = 1
        print("  ROUGE  jeux de cles DIFFERENTS : %d en mono, %d en multi"
              % (len(cles_mono), len(cles_multi)))
        for rel in sorted(cles_mono - cles_multi)[:5]:
            print("         MANQUE en multi : %s" % rel)
        for rel in sorted(cles_multi - cles_mono)[:5]:
            print("         EN TROP en multi : %s" % rel)

    champs_compares: set = set()
    ecarts = 0
    for rel in sorted(cles_mono & cles_multi):
        a, b = dict(mono[rel]), dict(multi[rel])
        for champ in _EXCLUS:
            a.pop(champ, None)
            b.pop(champ, None)
        champs_compares |= set(a) | set(b)
        if a != b:
            ecarts += 1
            ko = 1
            differents = sorted(set(a) | set(b))
            for champ in differents:
                if a.get(champ) != b.get(champ):
                    print("  ROUGE  %s : `%s` mono=%r multi=%r"
                          % (rel, champ, a.get(champ), b.get(champ)))
    if verbeux or ko:
        print("       %d entree(s) confrontee(s), %d champ(s) compare(s) par entree : %s"
              % (len(cles_mono & cles_multi), len(champs_compares),
                 ", ".join(sorted(champs_compares))))
        for champ, raison in sorted(_EXCLUS.items()):
            print("       EXCLU `%s` : %s" % (champ, raison))
    if not ko:
        print("  ok     ledgers IDENTIQUES entree par entree (%d entrees, %d champs)"
              % (len(cles_mono), len(champs_compares)))
    return ko


def _verdicts(entrees: dict) -> dict:
    out: dict = {}
    for e in entrees.values():
        v = e.get("verdict")
        out[v] = out.get(v, 0) + 1
    return out


def etape_equivalence(verbeux: bool) -> int:
    """LA mesure : mono-shard vs `--jobs 4`, sur le MEME arbre, entree par entree."""
    if not PROBE_457.is_file():
        print("  ROUGE  `probe_457` INTROUVABLE : %s" % PROBE_457)
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="probe547r7-"))
    ko = 0
    try:
        depot = _faux_depot(tmp / "depot")

        rc_mono, out_mono, sec_mono = _jouer(depot, ["--shard", "0/1"])
        mono = _ledger_de(depot)
        if not mono:
            print("  ROUGE  la passe MONO-SHARD n'a inscrit AUCUNE entree (rc=%d) -- rien a "
                  "confronter." % rc_mono)
            for ligne in [l for l in out_mono.splitlines() if l.strip()][-8:]:
                print("         | %s" % ligne[:110])
            return 1

        # Le ledger est RETIRE, pas seulement ecrase : la passe multi doit le RECONSTRUIRE, pas
        # heriter d'entrees que la passe mono aurait laissees. Sans ce retrait, une part perdue
        # serait INVISIBLE (l'entree de la passe mono survivrait a la fusion).
        ledger.chemin(depot).unlink()
        rc_multi, out_multi, sec_multi = _jouer(depot, ["--jobs", "4"])
        multi = _ledger_de(depot)

        print("  ..     mono `--shard 0/1` rc=%d en %.1f s ; multi `--jobs 4` rc=%d en %.1f s"
              % (rc_mono, sec_mono, rc_multi, sec_multi))
        print("  ..     verdicts mono=%s multi=%s"
              % (sorted(_verdicts(mono).items()), sorted(_verdicts(multi).items())))

        # UN ACCORD EN REGIME DEGENERE NE PROUVE RIEN : si les temoins n'avaient produit que des
        # VERT, l'egalite ne separerait pas << meme mecanisme >> de << cas facile >>.
        attendus = {ledger.VERT, ledger.ROUGE, ledger.VIDE, ledger.SETUP}
        vus = set(_verdicts(mono))
        if not attendus.issubset(vus):
            print("  ROUGE  le temoin MONO ne couvre pas les 4 verdicts (vus : %s) -- l'accord "
                  "mesure serait DEGENERE." % sorted(vus))
            ko = 1

        if rc_mono != rc_multi:
            print("  ROUGE  rc DIFFERENTS : mono=%d, multi=%d -- l'acceleration change le verdict "
                  "GLOBAL." % (rc_mono, rc_multi))
            ko = 1
        if "ledger CONSOLIDE" not in out_multi:
            print("  ROUGE  la passe multi n'a PAS consolide -- la mutation n'a pas mordu.")
            for ligne in [l for l in out_multi.splitlines() if l.strip()][-8:]:
                print("         | %s" % ligne[:110])
            ko = 1
        if "SHARD(S) SANS PART" in out_multi:
            print("  ROUGE  un shard n'a depose AUCUNE part -- la consolidation est amputee.")
            ko = 1

        ko |= _comparer(mono, multi, verbeux)
        return ko
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def etape_parts_orphelines(verbeux: bool) -> int:
    """CONTRE-EPREUVE DE PERMISSIVITE, en montage REEL : une part d'un AUTRE run est ECARTEE.

    C'est le mode de defaillance que le refus historique protegeait, et le seul qui compte : une
    part oubliee porte des verts gagnes sur un AUTRE arbre. Ici on la FABRIQUE -- avec un verdict
    VERT sur le fichier que l'on sait ROUGE -- et on exige qu'elle n'atteigne JAMAIS le ledger.
    """
    tmp = Path(tempfile.mkdtemp(prefix="probe547r7o-"))
    try:
        depot = _faux_depot(tmp / "depot")
        rc, out, _ = _jouer(depot, ["--shard", "0/1"])
        avant = _ledger_de(depot)
        if avant.get("tests/test_rouge_offline.py", {}).get("verdict") != ledger.ROUGE:
            print("  ROUGE  le temoin ROUGE n'est pas inscrit ROUGE (rc=%d) -- montage inexploitable"
                  % rc)
            return 1

        head = subprocess.run(["git", "-C", str(depot), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        perimetre = sorted("tests/" + n for n in _FICHIERS)
        sha = ledger.sha_perimetre(perimetre)
        menteuse = {"tests/test_rouge_offline.py": ledger.entree_neuve(
            {"passed": 1}, 0.1, "deadbeef", head, head, base=head)}

        cas = [
            ("jeton d'un AUTRE run", "run-etranger", head, sha),
            ("HEAD d'un AUTRE commit", "run-courant", "0" * 40, sha),
            ("PERIMETRE different", "run-courant", head, "0" * 40),
        ]
        ko = 0
        for nom, jeton_part, head_part, sha_part in cas:
            ledger.ecrire_part(depot, jeton_part, head_part, sha_part, 0, 1, menteuse, 0)
            cr = ledger.consolider(depot, "run-courant", head, perimetre)
            retenue = any(p.get("_jeton") == jeton_part and p.get("_head") == head_part
                          and p.get("_perimetre_sha") == sha_part for p in cr["gardees"])
            if retenue:
                print("  ROUGE  part avec %s RETENUE -- un vert d'un autre arbre entrerait au "
                      "ledger." % nom)
                ko = 1
            elif not cr["ecartees"]:
                print("  ROUGE  part avec %s ni retenue ni ECARTEE -- elle a disparu sans raison "
                      "dite." % nom)
                ko = 1
            elif verbeux:
                print("  ok     part avec %-24s ECARTEE : %s" % (nom, cr["ecartees"][0][1]))
            ledger.purger_parts(depot, cr["gardees"] + [p for p, _ in cr["ecartees"]])

        # ET LE LEDGER N'A PAS BOUGE : la contre-epreuve ne vaut que si l'on verifie l'ARTEFACT,
        # pas seulement le compte-rendu de la fonction.
        apres = _ledger_de(depot)
        if apres != avant:
            print("  ROUGE  le ledger versionne a CHANGE alors qu'aucune part n'etait valable.")
            ko = 1
        elif not verbeux:
            print("  ok     3 parts orphelines ECARTEES, ledger versionne INCHANGE")
        return ko
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def etape_sans_jeton(verbeux: bool) -> int:
    """Le refus TIENT quand il n'y a pas de jeton : multi-shard nu n'ecrit NI part NI ledger."""
    tmp = Path(tempfile.mkdtemp(prefix="probe547r7j-"))
    try:
        depot = _faux_depot(tmp / "depot")
        rc, out, _ = _jouer(depot, ["--shard", "0/4"])
        ko = 0
        if "part de ledger NON ECRITE" not in out:
            print("  ROUGE  un shard SANS jeton n'a pas dit son refus -- la mutation n'a pas mordu.")
            ko = 1
        if ledger.chemin(depot).exists():
            print("  ROUGE  un shard SANS jeton a ecrit le ledger VERSIONNE.")
            ko = 1
        parts, _ = ledger.lire_parts(depot)
        if parts:
            print("  ROUGE  un shard SANS jeton a depose %d part(s) -- elles seraient ORPHELINES."
                  % len(parts))
            ko = 1
        if not ko:
            print("  ok     multi-shard SANS jeton : refus DIT, 0 part, ledger absent (rc=%d)" % rc)
        return ko
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_ETAPES = (
    ("equivalence mono / multi", etape_equivalence),
    ("parts orphelines ecartees", etape_parts_orphelines),
    ("multi-shard sans jeton", etape_sans_jeton),
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbeux", action="store_true")
    args = ap.parse_args(argv)

    print("[547r7] le ledger multi-shard rend-il le ledger mono-shard ?")
    ko = 0
    for nom, fn in _ETAPES:
        print("[547r7] -- %s" % nom)
        ko += fn(args.verbeux)
    if ko:
        print("[547r7] ROUGE : %d etape(s) en echec." % ko)
        return 1
    print("[547r7] PASS : le multi-shard n'a change AUCUN verdict, et aucune part etrangere "
          "n'entre au ledger.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
