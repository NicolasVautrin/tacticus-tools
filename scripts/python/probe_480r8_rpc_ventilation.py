"""Probe #480-r8 -- les 155 RPC sans appelant : QU'EST-CE QUE CHACUN EST ?

CE QUE CE PROBE AJOUTE A `probe_480r6_code_mort.py` ETAGE 3
-----------------------------------------------------------
#480-r6 a mesure que 155 des 321 RPC du bundle n'ont AUCUN appelant executable, et a
explicitement laisse ce chiffre comme un AXE DE TRI : « 48 % n'est pas un verdict ». Un RPC
sans appelant statique peut etre un outil de diagnostic invoque a la main, la moitie d'une
paire dont le jumeau est cable, ou reellement mort. Ce probe SEPARE ces cas par des criteres
DERIVES, jamais par une liste de noms.

CINQ CANAUX DE JOIGNABILITE, mesures independamment
----------------------------------------------------
  C1  APPEL EXECUTABLE      -- le nom entre quotes, ou dans une forme d'appel RPC, dans un
                               fichier executable versionne. C'est le critere de #480-r6.
  C2  TOKEN NU EXECUTABLE   -- le nom en token nu dans un fichier executable. Attrape ce que
                               C1 rate : f-string, constante intermediaire, nom concatene.
  C3  DOCUMENTE             -- le nom cite dans un `.md` VERSIONNE. #480-r6 construisait deja
                               ce corpus mais ne le faisait PAS entrer dans le verdict : un
                               RPC cite dans une case-doc comme geste de diagnostic est
                               VIVANT, et c'est mecanique, pas un jugement.
  C4  CITE EN COMMIT        -- le nom present dans un message de commit (`git log --all`).
                               Trace historique : le RPC a ete annonce ou utilise.
  C5  MODULE CABLE          -- son fichier declarant expose au moins un AUTRE RPC qui a C1.
                               C'est le critere « moitie de paire » : on invoque `xTraceArm`
                               puis `xTraceStatus`, et seul le premier est cable en dur.

Un RPC sans AUCUN des cinq est un CANDIDAT MORT -- et seulement un candidat : l'etape 4 va
lui chercher son archeologie (`git log -S`) avant qu'on touche a quoi que ce soit.

POURQUOI LE CORPUS EST PRIS PAR COMPLEMENT, ET PAS PAR LISTE
-------------------------------------------------------------
#480-r6 enumerait SIX groupes ecrits a la main (`frida/host`, `frida/public`,
`scripts/python`, ses tests, `*.md`, puis `scripts`+`hooks-legacy`+`.claude`). Une liste ne
peut pas montrer le repertoire qu'elle a oublie -- et elle en oubliait un : `frida/tools/`,
qui contient un harnais executable (`probe-279-layout-by-name.ts`). Ici le corpus executable
est le COMPLEMENT : tout fichier versionne d'extension executable qui n'est pas sous
`frida/hooks/` (le declarant). Le groupe d'affichage est DERIVE du chemin, et un chemin qui
n'entre dans aucun groupe connu sort sous `autre (<racine>)` -- il ne peut pas disparaitre.

CE QUE CE PROBE NE VOIT PAS -- imprime a chaque passe, jamais tu
----------------------------------------------------------------
  * un RPC invoque a la main et JAMAIS ecrit nulle part (curl jetable, console) : il est
    indiscernable d'un mort par toute mesure statique. C'est la borne du probe.
  * ce que la SESSION injectee expose reellement -- residu `#480-r3`, toujours ouvert : un
    RPC ecrit mais non enregistre rend un `HTTP 500` indiscernable d'une erreur d'execution.
  * un appelant hors du depot (script d'un agent, note personnelle).

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probe_480r6_code_mort import (  # noqa: E402
    APPEL_RE,
    QUOTE_ID_RE,
    RPC_DECL_RE,
    RPC_NON_METHODE,
    ROOT,
    closure,
    entrees_declarees,
    rel,
)

# Extensions qui portent du code EXECUTABLE (par opposition a la doc `.md`).
EXT_EXEC = (".py", ".js", ".ts", ".cjs", ".mjs", ".ps1", ".sh", ".bat")
# Le declarant lui-meme : un RPC cite chez lui n'est pas un appelant.
PREFIXE_DECLARANT = "frida/hooks/"
# Plancher d'auto-accusation du capteur : sous ce seuil, c'est la MESURE qui est cassee,
# pas le depot qui serait vide. #480-r6 a mesure ce piege -- un lookbehind fautif rendait
# `ref=0 neuf=0` et concluait VERT sur un contrat vide.
PLANCHER_RPC = 50
PLANCHER_CORPUS = 500

IDENT_RE = re.compile(r"[A-Za-z_$][\w$]*")


def _git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=True)
    return [l.rstrip() for l in out.stdout.splitlines()]


def _git_brut(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", check=True)
    return out.stdout


def groupe_de(rf: str) -> str:
    """Groupe d'AFFICHAGE, derive du chemin. Un chemin inconnu sort sous `autre (<racine>)`,
    il ne peut pas etre avale silencieusement."""
    if rf.startswith("frida/host/"):
        return "host"
    if rf.startswith("frida/public/"):
        return "front"
    if rf.startswith("frida/tools/"):
        return "tools"
    if rf.startswith("scripts/python/"):
        return "test" if "/tests/" in rf else "python"
    if rf.startswith("scripts/"):
        return "scripts"
    if rf.startswith("hooks-legacy/"):
        return "legacy"
    if rf.startswith(".claude/"):
        return "claude"
    return "autre (%s)" % (rf.split("/", 1)[0] if "/" in rf else "<racine>")


def recenser_rpc() -> tuple[dict[str, list[str]], int]:
    """Les RPC declares dans les fichiers de hooks ATTEIGNABLES. Meme critere que #480-r6."""
    ent, _ = entrees_declarees()
    atteints, _, _ = closure(ent)
    hooks = sorted(p for p in atteints if rel(p).startswith(PREFIXE_DECLARANT))
    decl: dict[str, list[str]] = {}
    for f in hooks:
        try:
            txt = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in RPC_DECL_RE.findall(txt):
            if m in RPC_NON_METHODE:
                continue
            decl.setdefault(m, []).append(rel(f))
    return decl, len(hooks)


def corpus_executable() -> dict[str, str]:
    """Tout fichier versionne d'extension executable HORS `frida/hooks/`. Pris par COMPLEMENT."""
    out: dict[str, str] = {}
    for rf in _git("ls-files"):
        if not rf or not rf.endswith(EXT_EXEC):
            continue
        if rf.startswith(PREFIXE_DECLARANT):
            continue
        p = ROOT / rf
        if not p.is_file():
            continue
        try:
            out[rf] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    return out


def corpus_doc() -> dict[str, str]:
    out: dict[str, str] = {}
    for rf in _git("ls-files", "*.md"):
        if not rf:
            continue
        p = ROOT / rf
        if not p.is_file():
            continue
        try:
            out[rf] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    return out


def index_inverse(corpus: dict[str, str], quote_seulement: bool) -> dict[str, set[str]]:
    """Index nom -> {fichiers}. Construit dans CE sens : une regex par RPC x 3 000 documents
    ne finit pas (mesure par #480-r6 : > 600 s)."""
    idx: dict[str, set[str]] = {}
    rx = QUOTE_ID_RE if quote_seulement else IDENT_RE
    for rf, txt in corpus.items():
        for m in rx.findall(txt):
            idx.setdefault(m, set()).add(rf)
    return idx


def index_appels(corpus: dict[str, str]) -> dict[str, set[str]]:
    idx: dict[str, set[str]] = {}
    for rf, txt in corpus.items():
        for tup in APPEL_RE.findall(txt):
            for m in tup:
                if m:
                    idx.setdefault(m, set()).add(rf)
    return idx


def index_commits() -> tuple[dict[str, set[str]], int]:
    """Noms cites dans les MESSAGES de commit, toutes refs. Rend (index, nb de commits lus)."""
    sep = "\x00"
    brut = _git_brut("log", "--all", "--format=%s" + sep + "%b" + sep + "%H" + sep + sep)
    idx: dict[str, set[str]] = {}
    n = 0
    for bloc in brut.split(sep + sep):
        if not bloc.strip():
            continue
        parts = bloc.split(sep)
        sha = parts[-1].strip()[:8] if len(parts) >= 3 else "?"
        n += 1
        for m in IDENT_RE.findall(bloc):
            idx.setdefault(m, set()).add(sha)
    return idx, n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true", help="detail canal par canal")
    ap.add_argument("--cliquet", action="store_true",
                    help="rc != 0 si un RPC n'a AUCUN canal de joignabilite")
    ap.add_argument("--temoins", type=int, default=3,
                    help="nombre de temoins affiches par RPC (defaut 3)")
    a = ap.parse_args()

    # --- ETAPE 1 : recensement ------------------------------------------------------------
    decl, n_hooks = recenser_rpc()
    noms = sorted(decl)
    print("[480r8] ETAPE 1 -- RECENSEMENT")
    print("        %d RPC declares (`ctx.rpc.<nom> =`) dans %d fichiers de hooks atteignables"
          % (len(noms), n_hooks))
    if len(noms) < PLANCHER_RPC:
        print("  ROUGE  %d RPC < plancher %d : c'est le CAPTEUR qui est casse, pas le depot."
              % (len(noms), PLANCHER_RPC))
        return 2

    # --- ETAPE 2 : les cinq canaux --------------------------------------------------------
    cexec = corpus_executable()
    cdoc = corpus_doc()
    if len(cexec) < PLANCHER_CORPUS:
        print("  ROUGE  corpus executable = %d fichiers < plancher %d : capteur casse."
              % (len(cexec), PLANCHER_CORPUS))
        return 2

    quote_idx = index_inverse(cexec, quote_seulement=True)
    appel_idx = index_appels(cexec)
    nu_idx = index_inverse(cexec, quote_seulement=False)
    doc_idx = index_inverse(cdoc, quote_seulement=False)
    commit_idx, n_commits = index_commits()

    par_groupe: dict[str, int] = {}
    for rf in cexec:
        g = groupe_de(rf)
        par_groupe[g] = par_groupe.get(g, 0) + 1

    print()
    print("[480r8] ETAPE 2 -- CORPUS (pris par COMPLEMENT, groupe DERIVE du chemin)")
    print("        executable : %d fichiers versionnes hors `%s`"
          % (len(cexec), PREFIXE_DECLARANT))
    for g in sorted(par_groupe):
        print("           %-16s %d" % (g, par_groupe[g]))
    print("        doc        : %d fichiers `.md` versionnes" % len(cdoc))
    print("        commits    : %d messages lus (`git log --all`)" % n_commits)

    # C1 = quote OU forme d'appel, dans un fichier executable  (critere #480-r6)
    c1 = {n: quote_idx.get(n, set()) | appel_idx.get(n, set()) for n in noms}
    c2 = {n: nu_idx.get(n, set()) - c1[n] for n in noms}
    c3 = {n: doc_idx.get(n, set()) for n in noms}
    c4 = {n: commit_idx.get(n, set()) for n in noms}
    # C5 : un FRERE du meme fichier declarant possede C1.
    freres: dict[str, set[str]] = {}
    for n, fichiers in decl.items():
        for f in fichiers:
            freres.setdefault(f, set()).add(n)
    c5: dict[str, set[str]] = {}
    for n in noms:
        cables = set()
        for f in decl[n]:
            for autre in freres[f]:
                if autre != n and c1[autre]:
                    cables.add(autre)
        c5[n] = cables

    canaux = (("C1 appel executable (quote ou forme d'appel)", c1),
              ("C2 token nu dans un fichier executable", c2),
              ("C3 cite dans une doc .md versionnee", c3),
              ("C4 cite dans un message de commit", c4),
              ("C5 module cable (un frere a C1)", c5))
    print()
    print("[480r8] ETAPE 3 -- CANAUX DE JOIGNABILITE (mesures independamment)")
    for lib, d in canaux:
        print("        %-46s : %3d / %d" % (lib, sum(1 for n in noms if d[n]), len(noms)))

    sans_c1 = [n for n in noms if not c1[n]]
    print()
    print("        SANS C1 (le compte de #480-r6) : %d" % len(sans_c1))

    # --- ETAPE 4 : ventilation des SANS-C1 ------------------------------------------------
    # Partition EXHAUSTIVE : chaque RPC sans C1 tombe dans exactement une classe, et la somme
    # des classes est imprimee. Une classe est la COMBINAISON des canaux restants, pas un
    # jugement -- l'ordre ci-dessous ne sert qu'a nommer, il ne masque aucun canal.
    classes: dict[str, list[str]] = {}
    for n in sans_c1:
        sig = []
        if c2[n]:
            sig.append("C2")
        if c3[n]:
            sig.append("C3")
        if c4[n]:
            sig.append("C4")
        if c5[n]:
            sig.append("C5")
        cle = "+".join(sig) if sig else "AUCUN CANAL"
        classes.setdefault(cle, []).append(n)

    print()
    print("[480r8] ETAPE 4 -- VENTILATION DES %d SANS-C1 (partition exhaustive)" % len(sans_c1))
    total = 0
    for cle in sorted(classes, key=lambda k: (-len(classes[k]), k)):
        total += len(classes[cle])
        print("        %-24s %3d" % (cle, len(classes[cle])))
    print("        %-24s %3d  (doit egaler %d)" % ("SOMME", total, len(sans_c1)))
    if total != len(sans_c1):
        print("  ROUGE  la partition n'est pas exhaustive -- capteur casse.")
        return 2

    # Le detail par RPC, avec TEMOIN : la classe n'est pas une appreciation.
    if a.verbose:
        for cle in sorted(classes, key=lambda k: (-len(classes[k]), k)):
            print()
            print("        --- %s (%d) ---" % (cle, len(classes[cle])))
            for n in sorted(classes[cle]):
                print("        rpc.%-36s declare dans %s" % (n, ", ".join(sorted(set(decl[n])))))
                for lib, d in canaux:
                    if d[n]:
                        ech = sorted(d[n])[:a.temoins]
                        suite = " (+%d)" % (len(d[n]) - len(ech)) if len(d[n]) > len(ech) else ""
                        print("            %-4s %s%s" % (lib.split()[0], ", ".join(ech), suite))

    morts = sorted(classes.get("AUCUN CANAL", []))
    print()
    print("[480r8] ETAPE 5 -- CANDIDATS MORTS (aucun des cinq canaux) : %d" % len(morts))
    for n in morts:
        print("  MORT?  rpc.%-34s declare dans %s" % (n, ", ".join(sorted(set(decl[n])))))

    # Canal UNIQUE = fragilite : un RPC qui ne tient que par le message de commit n'a aucune
    # trace vivante dans l'arbre. On le NOMME, sans le declarer mort.
    fragiles = [n for n in sans_c1 if not c2[n] and not c3[n] and not c5[n] and c4[n]]
    print()
    print("[480r8] ETAPE 6 -- FRAGILES : joignables UNIQUEMENT par le message de commit "
          "(aucune trace dans l'arbre courant) : %d" % len(fragiles))
    for n in fragiles:
        print("  FRAGILE rpc.%-33s commits %s"
              % (n, ", ".join(sorted(c4[n])[:a.temoins])))

    print()
    print("[480r8] NON VU par ce probe : un RPC invoque a la main et jamais ecrit nulle part")
    print("        (indiscernable d'un mort par toute mesure statique) ; ce que la session")
    print("        injectee expose vraiment (residu #480-r3) ; un appelant hors du depot.")

    if a.cliquet:
        if morts:
            print()
            print("[480r8] CLIQUET ROUGE : %d RPC sans AUCUN canal de joignabilite." % len(morts))
            print("        Un RPC expose doit etre joignable -- appele, documente, ou frere")
            print("        d'un RPC cable. Le rendre vert : le cabler, l'ecrire dans une doc")
            print("        du depot (c'est ce que « outil de diagnostic » veut dire), ou le")
            print("        retirer. Le critere est DERIVE : il mord au 156e comme au 1er.")
            return 1
        print()
        print("[480r8] CLIQUET VERT : les %d RPC declares portent tous au moins un canal."
              % len(noms))
    return 0


if __name__ == "__main__":
    sys.exit(main())
