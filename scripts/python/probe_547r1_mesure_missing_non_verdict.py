"""#547-r1 -- CLIQUET : `probe_457 --measure-missing` ne peut PAS se lire comme un verdict de VERDEUR.

LE VICE, MESURE. Ce mode est le geste joue EN PREMIER apres chaque merge. Sur `027cb485` -- l'arbre
qui portait **23 tests offline rouges** -- il rendait **`rc = 0` en 2,8 s**, en affichant
<< les 261 fichier(s) du perimetre ont deja un poids ET une entree d'empreinte, rien a mesurer >>.
Ce `0` a ete lu comme << l'offline est vert >> pendant toute une campagne.

CE QU'IL MESURE, ET CE QU'IL NE MESURE PAS. Il juge la COMPLETUDE des artefacts de selection
(poids + entree d'empreinte) sur les fichiers NEUFS. Il ne joue JAMAIS un fichier deja mesure --
par construction et a dessein : le lui faire jouer serait un `--measure` complet (~976 s), paye a
chaque merge par tout le monde. La verdeur d'un fichier EXISTANT lui est donc structurellement
inaccessible.

LE CORRECTIF EST LE SILENCE SUR CET AXE, PAS UNE MESURE DE PLUS -- et c'est un RESULTAT, pas un
pis-aller : une passe PARTIELLE rend desormais `1` (pytest a vu un rouge parmi ce qu'elle a joue)
ou `EX_NON_MESURE = 99`, **jamais `0`**. Il n'y a plus de lecture rassurante a en tirer, ce qui est
exactement l'etat des connaissances qu'elle produit.

CE QUE CE CLIQUET PROUVE, ET DANS LES DEUX SENS
------------------------------------------------
  * etage 1 -- le DISCRIMINANT est bien `complete` : `--measure` COMPLET garde son `0` (il joue
    tout le perimetre, son rc EST un verdict), la passe PARTIELLE rend 99. Exerce sur le FOYER
    (`_ecrire_mesure`), sans ecrire une ligne dans le depot ;
  * etage 2 -- le chemin << rien a mesurer >>, celui du `rc = 0` historique, ne rend plus `0` ;
  * etage 3 -- LE TEMOIN REEL : un `assert False` injecte dans un fichier de test offline
    EXISTANT, commite dans un worktree temoin. Le fichier EST rouge (verifie), et le geste ne rend
    PAS `0` ;
  * etage 4 -- LE MUTANT DU CORRECTIF : on remet `return 0` dans l'arbre temoin, et le geste
    REDEVIENT vert sur cet arbre rouge. Sans cet etage, l'etage 3 ne prouverait pas que c'est LE
    CORRECTIF qui agit.

⚠ LES ETAGES 3 ET 4 JUGENT L'ARBRE **COMMITE**, pas le working tree : leur worktree temoin part de
`HEAD`. C'est la meme semantique que `probe_547`, qui juge le ledger VERSIONNE -- un cliquet
atteste ce qui sera livre. Concretement : commite ton correctif AVANT de le jouer, sinon l'etage 3
mesure l'ancien code et rend le `0` du vice (ce qui est un resultat JUSTE sur cet arbre-la, et le
probe le dit).

100 % OFFLINE. N'ECRIT RIEN dans `scripts/python` (#455) : les poids de l'etage 1 vont dans un
`tmp`, les etages 3-4 vivent dans un worktree jetable. ASCII only.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

import probe_457_offline_tests_green as P         # noqa: E402

ROOT = PYDIR.parent.parent

#: ANCRAGE de la MUTATION de l'etage 4 : la SIGNATURE du foyer, pas un call-site. Muter le foyer
#: restaure le comportement HISTORIQUE des DEUX chemins d'un coup (<< rien a mesurer >> et
#: `not complete`), et l'ancrage tient meme si un call-site est reindente ou reformule. Il est
#: verifie PRESENT avant substitution : un mutant qui ne matche pas rendrait l'etage vert pour une
#: raison etrangere au critere.
ANCRAGE_CORRECTIF = "def _non_verdict_de_verdeur(constat: str) -> int:\n"
MUTANT_CORRECTIF = ("def _non_verdict_de_verdeur(constat: str) -> int:\n"
                    "    return 0  # MUTANT #547-r1 : le `rc` historique, celui du vice\n")


class _Horloge:
    """Double de `_TimePerFile` : ce que `_ecrire_mesure` lui demande, et rien de plus."""

    def __init__(self, rels):
        self.sec = {r: 0.01 for r in rels}
        self.n = {r: 3 for r in rels}


def _git(args, cwd=ROOT, tolere=False):
    p = subprocess.run(["git"] + list(args), cwd=str(cwd), capture_output=True, text=True,
                       errors="replace")
    if p.returncode != 0 and not tolere:
        raise SystemExit("[547-r1] git %s -> rc=%d : %s"
                         % (" ".join(args[:2]), p.returncode, (p.stderr or "").strip()[:200]))
    return p.stdout


#: ⚠ LE GARDE ANTI-RECURSION, ET IL N'EST PAS THEORIQUE -- IL A TOURNE.
#: Ce cliquet lance `probe_457` en sous-process. Or `probe_457 --measure-missing` JOUE les
#: fichiers de test sans entree d'empreinte, dont la GARDE de ce cliquet
#: (`tests/test_547r1_mesure_missing_non_verdict_offline.py`), qui re-appelle ce cliquet, qui
#: relance `probe_457`... Mesure du 2026-08-08 : **~150 processus chainés**, un toutes les 12 s,
#: pendant 35 minutes, avant qu'un `taskkill /T` n'arrete l'arbre. Le sous-process porte donc
#: cette variable, et la garde SAUTE ses etages a worktree quand elle la voit -- la recursion
#: s'arrete au niveau 1, et les etages restent exerces quand le cliquet est joue normalement.
TEMOIN_ENV = "TACTICUS_547R1_DANS_TEMOIN"


def _joue_457(cwd, args):
    """Lance `probe_457` en SOUS-PROCESS : c'est son `rc` de PROCESSUS qu'on garde, pas un retour
    de fonction -- c'est ce que lisent `ratchets.ps1`, les briefs et l'orchestrateur."""
    env = dict(os.environ, TACTICUS_ALLOW_RATCHETS="1", **{TEMOIN_ENV: "1"})
    p = subprocess.run([sys.executable, "probe_457_offline_tests_green.py"] + list(args),
                       cwd=str(Path(cwd) / "scripts" / "python"), capture_output=True, text=True,
                       errors="replace", env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ------------------------------------------------------------------- etage 1 : le DISCRIMINANT

def etape1() -> list:
    """`complete=True` rend 0, `complete=False` rend 99 -- exerce sur le FOYER, sans rien ecrire.

    Les poids sont rediriges vers un `tmp` et l'empreinte est `None` : `_ecrire_mesure` traverse
    alors tout son corps jusqu'au verdict, sans toucher a un fichier versionne."""
    fautes = []
    tmp = Path(tempfile.mkdtemp(prefix="p547r1_"))
    ancien = P._weights_path
    try:
        P._weights_path = lambda: tmp / "poids.json"
        rels = ["tests/a.py", "tests/b.py"]
        h = _Horloge(rels)
        rc_complet = P._ecrire_mesure(rels, rels, h, None, 0, 1.0, {}, complete=True)
        rc_partiel = P._ecrire_mesure(rels, rels[:1], h, None, 0, 1.0, {}, complete=False)
    finally:
        P._weights_path = ancien
        shutil.rmtree(tmp, ignore_errors=True)
    print("   `--measure` COMPLET   -> rc=%s (attendu 0, son rc EST un verdict)" % rc_complet)
    print("   passe PARTIELLE       -> rc=%s (attendu %d)" % (rc_partiel, P.EX_NON_MESURE))
    if rc_complet != 0:
        fautes.append("le mode COMPLET ne rend plus 0 : la non-regression est cassee")
    if rc_partiel != P.EX_NON_MESURE:
        fautes.append("une passe PARTIELLE rend %r au lieu de %d" % (rc_partiel, P.EX_NON_MESURE))
    return fautes


# --------------------------------------------------- etage 2 : le chemin << rien a mesurer >>

def etape2() -> list:
    rc, out = _joue_457(ROOT, ["--measure-missing"])
    rien = "rien a mesurer" in out
    print("   `--measure-missing` sur CE checkout -> rc=%d (rien a mesurer : %s)" % (rc, rien))
    if rc == 0:
        return ["`--measure-missing` rend 0 : la lecture rassurante est de retour"]
    if not rien:
        print("   (ce checkout avait des fichiers a mesurer -- l'etage reste valable : rc != 0)")
    return []


# ----------------------------------------------- etages 3 et 4 : le TEMOIN REEL et son MUTANT

def _fichier_le_moins_cher() -> str:
    """Choisi MECANIQUEMENT dans les durees VERSIONNEES -- jamais un nom en dur."""
    p = ROOT / "scripts" / "ratchets-457-durations.json"
    poids = json.loads(p.read_text(encoding="utf-8"))
    poids = poids.get("weights", poids)
    cands = sorted((v, k) for k, v in poids.items()
                   if isinstance(v, (int, float)) and k.endswith(".py"))
    if not cands:
        raise SystemExit("[547-r1] aucune duree exploitable dans %s" % p)
    return cands[0][1]


def _temoin(mute_le_correctif: bool) -> tuple:
    """Monte un worktree, y rend ROUGE un fichier de test offline EXISTANT, et joue le geste.

    Rend `(rc_du_geste, rc_de_pytest_sur_le_fichier, rel)`."""
    base = Path(tempfile.mkdtemp(prefix="wt547r1_"))
    cible = base / "t"
    _git(["worktree", "add", "--detach", str(cible), "HEAD"], tolere=True)
    try:
        rel = _fichier_le_moins_cher()
        f = cible / "scripts" / "python" / rel.replace("/", os.sep)
        if not f.exists():
            raise SystemExit("[547-r1] le fichier choisi n'existe pas dans le temoin : %s" % rel)
        with io.open(f, "a", encoding="utf-8") as fh:
            fh.write("\n\ndef test_547r1_contre_epreuve_injectee():\n"
                     "    assert False, 'ROUGE injecte par le cliquet #547-r1'\n")
        if mute_le_correctif:
            g = cible / "scripts" / "python" / "probe_457_offline_tests_green.py"
            src = g.read_text(encoding="utf-8")
            if ANCRAGE_CORRECTIF not in src:
                raise SystemExit("[547-r1] ANCRAGE du correctif introuvable -- le code a bouge, "
                                 "le mutant ne prouverait rien")
            g.write_text(src.replace(ANCRAGE_CORRECTIF, MUTANT_CORRECTIF, 1), encoding="utf-8")
        _git(["add", "-A"], cwd=cible)
        _git(["-c", "user.email=x@x", "-c", "user.name=x", "commit", "-m", "contre-epreuve"],
             cwd=cible, tolere=True)
        # (a) le fichier est-il REELLEMENT rouge ? Sans ce controle, l'etage ne prouve rien.
        pr = subprocess.run([sys.executable, "-m", "pytest", rel, "-q", "--no-header",
                             "-p", "no:cacheprovider"],
                            cwd=str(cible / "scripts" / "python"), capture_output=True, text=True,
                            errors="replace")
        rc_geste, _ = _joue_457(cible, ["--measure-missing"])
        return rc_geste, pr.returncode, rel
    finally:
        _git(["worktree", "remove", "--force", str(cible)], tolere=True)
        shutil.rmtree(base, ignore_errors=True)


def etape3() -> list:
    rc_geste, rc_pytest, rel = _temoin(mute_le_correctif=False)
    print("   temoin : `%s` rendu ROUGE (pytest rc=%d)" % (rel, rc_pytest))
    print("   `--measure-missing` sur cet arbre ROUGE -> rc=%d" % rc_geste)
    fautes = []
    if rc_pytest == 0:
        fautes.append("le fichier temoin n'est pas rouge : l'injection n'a pas mordu")
    if rc_geste == 0:
        fautes.append("le geste rend 0 sur un arbre ROUGE -- le vice est de retour")
    return fautes


def etape4() -> list:
    rc_geste, rc_pytest, rel = _temoin(mute_le_correctif=True)
    print("   MUTANT du correctif (`return 0` remis) sur le MEME arbre rouge -> rc=%d" % rc_geste)
    fautes = []
    if rc_pytest == 0:
        fautes.append("le fichier temoin n'est pas rouge : le mutant ne prouve rien")
    if rc_geste != 0:
        fautes.append("le MUTANT ne restaure PAS le `0` : l'etage 3 ne demontre donc pas que "
                      "c'est le CORRECTIF qui agit (rc=%d)" % rc_geste)
    return fautes


ETAGES = [
    ("1 -- le DISCRIMINANT est `complete`, et le mode COMPLET garde son verdict", etape1),
    ("2 -- le chemin << rien a mesurer >> ne rend plus 0", etape2),
    ("3 -- TEMOIN REEL : un rouge INJECTE dans un fichier EXISTANT", etape3),
    ("4 -- MUTANT du correctif : le `0` revient quand on le retire", etape4),
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--etage", type=int, help="ne jouer qu'un etage (1-4)")
    args = ap.parse_args(argv)

    print("== #547-r1 -- `--measure-missing` ne se lit plus comme un verdict de VERDEUR")
    fautes = []
    for i, (titre, fn) in enumerate(ETAGES, start=1):
        if args.etage and args.etage != i:
            continue
        print("-- etage %s" % titre)
        fautes += ["etage %d : %s" % (i, f) for f in fn()]
    print("-- PORTEE DE LA MESURE")
    print("   Ce cliquet NE PROUVE PAS que `--measure-missing` VOIT un rouge existant : il ne le")
    print("   peut pas, et c'est un choix de COUT assume (le lui faire jouer = `--measure`")
    print("   complet, ~976 s a chaque merge). Il prouve qu'aucune LECTURE RASSURANTE n'en sort.")
    print("   Les gestes qui VOIENT, mesures : `--since <ref>` (16 fichiers / 293 s sur un diff")
    print("   d'UN fichier de test), `--depuis-ledger`, `--shard k/8`, et le ledger versionne")
    print("   qu'ils alimentent -- lu sans rien rejouer par `probe_547_ledger_sans_verdict_non_vert.py`.")
    if fautes:
        for f in fautes:
            print("   !! %s" % f)
    print("VERDICT: %s" % ("PASS" if not fautes else "FAIL"))
    return 1 if fautes else 0


if __name__ == "__main__":
    raise SystemExit(main())
