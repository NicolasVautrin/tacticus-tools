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
    resolve_import,
)

# Extensions qui portent du code EXECUTABLE (par opposition a la doc `.md`).
EXT_EXEC = (".py", ".js", ".ts", ".cjs", ".mjs", ".ps1", ".sh", ".bat")
# `hooks-legacy/` est VERSIONNE et consultable, mais le CLAUDE.md en fixe le statut : « rien de
# vivant ne doit en dependre ». Un appelant qui n'existe QUE la ne prouve donc aucune vie -- il
# prouve le contraire, une survivance historique. Il est compte et NOMME a part, jamais fondu
# dans le compte des appelants vivants. #480-r6 le rangeait dans son groupe `autre`, ce qui
# faisait passer pour cable un RPC dont le seul appelant est archive.
GROUPES_HISTORIQUES = frozenset({"legacy"})
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


#: Les trois lectures du depot, memoisees (#941-r2). Elles ne dependent QUE du disque, et rien
#: dans ce probe ni chez ses appelants n'ecrit dans l'arbre. Mesure du 2026-08-11 : recensement
#: 6,32 s, corpus executable 7,90 s (2718 fichiers), corpus doc 1,66 s (864). Le CLI les appelle
#: une fois chacune -- le memo ne sert donc qu'aux appelants IN-PROCESS, ou il vaut ~16 s.
#: Chaque valeur retenue est RE-CONSTRUITE au retour : un appelant ne peut pas muter le corpus
#: que verra le suivant.
_LECTURES_CACHE: dict = {}


def recenser_rpc() -> tuple[dict[str, list[str]], int]:
    """Les RPC declares dans les fichiers de hooks ATTEIGNABLES. Meme critere que #480-r6."""
    fige = _LECTURES_CACHE.get("rpc")
    if fige is None:
        fige = _balayer_rpc()
        _LECTURES_CACHE["rpc"] = fige
    decl, n = fige
    return {k: list(v) for k, v in decl.items()}, n


def _balayer_rpc() -> tuple[dict[str, list[str]], int]:
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
    fige = _LECTURES_CACHE.get("exec")
    if fige is None:
        fige = _balayer_corpus_executable()
        _LECTURES_CACHE["exec"] = fige
    return dict(fige)


def _balayer_corpus_executable() -> dict[str, str]:
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
    fige = _LECTURES_CACHE.get("doc")
    if fige is None:
        fige = _balayer_corpus_doc()
        _LECTURES_CACHE["doc"] = fige
    return dict(fige)


def _balayer_corpus_doc() -> dict[str, str]:
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
    # Windows refuse un `\x00` dans un argument de processus (`ValueError: embedded null
    # character`) : le separateur est donc textuel, et choisi hors de l'alphabet des
    # identifiants pour ne jamais scinder un nom de RPC.
    sep = "@@480R8@@"
    brut = _git_brut("log", "--all", "--format=%H" + sep + "%s%n%b" + sep + sep)
    idx: dict[str, set[str]] = {}
    n = 0
    for bloc in brut.split(sep + sep):
        if not bloc.strip():
            continue
        parts = bloc.split(sep, 1)
        sha = parts[0].strip()[:8] if parts else "?"
        corps = parts[1] if len(parts) > 1 else ""
        n += 1
        for m in IDENT_RE.findall(corps):
            idx.setdefault(m, set()).add(sha)
    return idx, n


COMMENTAIRE_BLOC_RE = re.compile(r"/\*.*?\*/", re.S)
COMMENTAIRE_LIGNE_RE = re.compile(r"//[^\n]*")
IMPORT_NS_RE = re.compile(r"""import\s+\*\s+as\s+([A-Za-z_$][\w$]*)\s+from\s+['"]([^'"]+)['"]""")
IMPORT_NOMME_RE = re.compile(
    r"""import\s*\{([^}]*)\}\s*from\s+['"](\./[^'"]+)['"]""")


def modules_non_enregistres(decl: dict[str, list[str]]) -> dict[str, list[str]]:
    """Modules qui DECLARENT des RPC mais dont le `register` n'est jamais appele.

    C'est le residu `#480-r3` vu par le bout STATIQUE : un RPC ecrit mais jamais enregistre
    n'est PAS expose par la session, et un appelant recoit un `HTTP 500` indiscernable d'une
    erreur d'execution. `frida/hooks/main.ts` a un foyer d'enregistrement UNIQUE (`wireRpc` de
    `controller.ts`, verifie : aucun `Object.assign(rpc, ...)` ni `rpc[nom] =` ailleurs), donc
    il suffit de confronter ce que `controller.ts` IMPORTE a ce qu'il APPELLE reellement --
    commentaires retires, sans quoi un `/* movementTrace, */` compte comme un appel.
    """
    ctrl = ROOT / "frida" / "hooks" / "controller.ts"
    if not ctrl.is_file():
        return {}
    brut = ctrl.read_text(encoding="utf-8", errors="replace")
    code = COMMENTAIRE_LIGNE_RE.sub("", COMMENTAIRE_BLOC_RE.sub("", brut))

    # alias de module -> chemin resolu ; et fonctions `registerX` importees nommement.
    alias: dict[str, str] = {}
    for ident, spec in IMPORT_NS_RE.findall(brut):
        alias[ident] = spec
    nommes: dict[str, str] = {}
    for grp, spec in IMPORT_NOMME_RE.findall(brut):
        for item in grp.split(","):
            item = item.strip()
            if not item:
                continue
            m = re.match(r"([A-Za-z_$][\w$]*)\s+as\s+([A-Za-z_$][\w$]*)", item)
            nom = m.group(2) if m else item.split()[0]
            if nom.startswith("register"):
                nommes[nom] = spec

    # Ce qui est REELLEMENT appele, dans le code sans commentaires.
    appeles: set[str] = set()
    for ident in alias:
        if re.search(r"(?<![\w$])%s\s*\.\s*register\s*\(" % re.escape(ident), code):
            appeles.add(ident)
    # Forme collective : `[a, b, c]\n    .forEach((f) => f.register(ctx))`.
    # ⚠ NE PAS ecrire `\.forEach\s*\([^)]*register` : la classe negative bute sur la
    # parenthese de `(f)` et le motif ne matche JAMAIS. Mesure du 2026-08-05 -- cette
    # version rendait 48 modules « non enregistres » dont `amorce-singletons` et `launch`,
    # c'est-a-dire `autoBootExtraire`/`playTurn`/`initRunner`, qui tournent tous les
    # jours. Un faux positif massif, rattrape parce que le resultat contredisait un fait
    # connu -- pas parce que le probe s'en est apercu.
    for bloc in re.findall(r"\[([^\]]*)\]\s*\.\s*forEach\s*\(.{0,80}?register", code, re.S):
        for ident in IDENT_RE.findall(bloc):
            if ident in alias:
                appeles.add(ident)
    for nom in nommes:
        if re.search(r"(?<![\w$])%s\s*\(" % re.escape(nom), code):
            appeles.add(nom)

    # chemin d'un module -> alias, pour rattacher un fichier declarant a son enregistrement.
    def _resout(spec: str) -> str | None:
        p = resolve_import(ctrl, spec)
        return rel(p) if p is not None else None

    enregistre_par_chemin: dict[str, bool] = {}
    for ident, spec in list(alias.items()):
        ch = _resout(spec)
        if ch:
            enregistre_par_chemin[ch] = enregistre_par_chemin.get(ch, False) or ident in appeles
    for nom, spec in nommes.items():
        ch = _resout(spec)
        if ch:
            enregistre_par_chemin[ch] = enregistre_par_chemin.get(ch, False) or nom in appeles

    orphelins: dict[str, list[str]] = {}
    for n, fichiers in decl.items():
        for f in fichiers:
            if enregistre_par_chemin.get(f) is False:
                orphelins.setdefault(f, []).append(n)
    return orphelins


def archeologie(noms: list[str]) -> dict[str, list[str]]:
    """Pour chaque nom : les commits ou il a vecu dans du code VIVANT hors de son declarant.

    `-S` (pickaxe) coute ~12 s par terme sur ce depot ; la mesure est purement OFFLINE, donc
    elle se parallelise sans toucher au budget des runners (CLAUDE.md : « le plafond de 4
    borne ce qui MONTE UN RUNNER, pas la parallelisation »).
    """
    from concurrent.futures import ThreadPoolExecutor

    def un(n: str) -> tuple[str, list[str]]:
        try:
            out = _git("log", "--all", "--oneline", "-S", n, "--",
                       ":!frida/hooks", ":!hooks-legacy", ":!*.md")
        except subprocess.CalledProcessError:
            return n, ["<MESURE ECHOUEE>"]
        return n, [l for l in out if l.strip()]

    res: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=8) as ex:
        for n, v in ex.map(un, noms):
            res[n] = v
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verbose", action="store_true", help="detail canal par canal")
    ap.add_argument("--cliquet", action="store_true",
                    help="rc != 0 si un RPC n'a AUCUN canal de joignabilite")
    ap.add_argument("--temoins", type=int, default=3,
                    help="nombre de temoins affiches par RPC (defaut 3)")
    ap.add_argument("--catalogue", action="store_true",
                    help="imprimer, en markdown, les RPC sans AUCUN canal groupes par module "
                         "declarant -- le bloc a coller dans `rpc-api.md`")
    ap.add_argument("--archeologie", action="store_true",
                    help="pour chaque candidat mort, chercher s'il a DEJA eu un appelant "
                         "(git log -S, ~12 s/terme, parallelise)")
    a = ap.parse_args(argv)

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

    # C1 = quote OU forme d'appel, dans un fichier executable VIVANT (critere #480-r6, corrige
    # de son biais `hooks-legacy`). C0 = le meme signal, mais dans l'ARCHIVE seule.
    def _vivants(s: set[str]) -> set[str]:
        return {f for f in s if groupe_de(f) not in GROUPES_HISTORIQUES}

    def _archives(s: set[str]) -> set[str]:
        return {f for f in s if groupe_de(f) in GROUPES_HISTORIQUES}

    brut1 = {n: quote_idx.get(n, set()) | appel_idx.get(n, set()) for n in noms}
    c1 = {n: _vivants(brut1[n]) for n in noms}
    c0 = {n: _archives(brut1[n]) for n in noms}
    c2 = {n: _vivants(nu_idx.get(n, set())) - c1[n] for n in noms}
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

    canaux = (("C0 appel depuis l'ARCHIVE `hooks-legacy/` seule", c0),
              ("C1 appel executable (quote ou forme d'appel)", c1),
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
    print("        SANS C1 (le compte de #480-r6, corrige du biais `hooks-legacy`) : %d"
          % len(sans_c1))
    seul_archive = [n for n in noms if not c1[n] and c0[n]]
    print("        dont appeles SEULEMENT depuis `hooks-legacy/` (archive : ne prouve aucune")
    print("        vie, et #480-r6 les comptait comme cables) : %d" % len(seul_archive))
    for n in sorted(seul_archive):
        print("        archive-seule  rpc.%-30s %s"
              % (n, ", ".join(sorted(c0[n])[:a.temoins])))

    # --- ETAPE 4 : ventilation des SANS-C1 ------------------------------------------------
    # Partition EXHAUSTIVE : chaque RPC sans C1 tombe dans exactement une classe, et la somme
    # des classes est imprimee. Une classe est la COMBINAISON des canaux restants, pas un
    # jugement -- l'ordre ci-dessous ne sert qu'a nommer, il ne masque aucun canal.
    classes: dict[str, list[str]] = {}
    for n in sans_c1:
        sig = []
        if c0[n]:
            sig.append("C0")
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

    # ⚠ LE CLIQUET NE PORTE PAS SUR C5 -- mesure du 2026-08-05, contre-epreuve par mutation :
    # un `ctx.rpc.zzMutationCliquet480r8` ajoute dans `status.ts` (aucun appelant, aucune doc,
    # aucun commit) laissait le cliquet VERT, parce que ses FRERES ont C1. C5 est donc une
    # echappatoire : tout RPC ajoute dans un fichier deja cable passerait automatiquement, et
    # la garde cesserait de mordre exactement sur le gisement qu'elle vise -- notre propre
    # cadence d'ajout. C5 reste un canal de TRI (il explique qu'un RPC sans appelant direct est
    # la commande annexe d'un module vivant), jamais une preuve de joignabilite.
    # Les canaux NOMINATIFS sont ceux ou le NOM LUI-MEME est ecrit hors de son declarant.
    # C0 (archive `hooks-legacy/`) en est exclu : le CLAUDE.md pose que rien de vivant n'en
    # depend, donc un nom qui n'existe QUE la n'est pas joignable -- il est archive.
    nominatifs = [n for n in noms if c1[n] or c2[n] or c3[n] or c4[n]]
    non_joignables = sorted(n for n in noms if n not in set(nominatifs))
    morts = sorted(classes.get("AUCUN CANAL", []))
    print()
    print("[480r8] ETAPE 5 -- CANDIDATS MORTS (aucun des canaux) : %d" % len(morts))
    print("        NON JOIGNABLES (aucun canal NOMINATIF C1/C2/C3/C4 -- C5 exclu, il ne")
    print("        mentionne pas le nom ; C0 exclu, l'archive ne prouve aucune vie) : %d"
          % len(non_joignables))
    for n in non_joignables:
        if n not in morts:
            print("  NON-JOIGNABLE rpc.%-28s declare dans %s  [C5 seul]"
                  % (n, ", ".join(sorted(set(decl[n])))))
    for n in morts:
        print("  MORT?  rpc.%-34s declare dans %s" % (n, ", ".join(sorted(set(decl[n])))))

    if a.catalogue and morts:
        par_module: dict[str, list[str]] = {}
        for n in morts:
            par_module.setdefault(decl[n][0], []).append(n)
        print()
        print("[480r8] CATALOGUE (markdown) -- a coller dans `rpc-api.md`")
        print("-" * 78)
        for mod in sorted(par_module, key=lambda m: (-len(par_module[m]), m)):
            court = mod[len("frida/hooks/"):] if mod.startswith("frida/hooks/") else mod
            print("- **`%s`** (%d) : %s"
                  % (court, len(par_module[mod]),
                     ", ".join("`%s`" % n for n in sorted(par_module[mod]))))
        print("-" * 78)

    if a.archeologie and morts:
        print()
        print("[480r8] ETAPE 5bis -- ARCHEOLOGIE : un candidat mort a-t-il DEJA eu un appelant ?")
        print("        `git log --all -S<nom>` restreint au code VIVANT (hors `frida/hooks/`,")
        print("        hors `hooks-legacy/`, hors `.md`). Un resultat NON VIDE veut dire que le")
        print("        nom a vecu hors de son declarant : feature retiree ou remplacant. Un")
        print("        resultat VIDE veut dire qu'il n'a JAMAIS eu d'appelant ecrit.")
        arch = archeologie(morts)
        jamais = [n for n in morts if not arch[n]]
        eurent = [n for n in morts if arch[n]]
        print("        JAMAIS d'appelant ecrit : %d  |  en ont EU un : %d"
              % (len(jamais), len(eurent)))
        for n in eurent:
            print("  A-VECU rpc.%-32s %s" % (n, ", ".join(arch[n][:a.temoins])))

    # Canal UNIQUE = fragilite : un RPC qui ne tient que par le message de commit n'a aucune
    # trace vivante dans l'arbre. On le NOMME, sans le declarer mort.
    fragiles = [n for n in sans_c1 if not c2[n] and not c3[n] and not c5[n] and c4[n]]
    print()
    print("[480r8] ETAPE 6 -- FRAGILES : joignables UNIQUEMENT par le message de commit "
          "(aucune trace dans l'arbre courant) : %d" % len(fragiles))
    for n in fragiles:
        print("  FRAGILE rpc.%-33s commits %s"
              % (n, ", ".join(sorted(c4[n])[:a.temoins])))

    orphelins = modules_non_enregistres(decl)
    n_orph = sum(len(v) for v in orphelins.values())
    print()
    print("[480r8] ETAPE 7 -- DECLARES MAIS JAMAIS ENREGISTRES (croise le residu #480-r3)")
    print("        Un module importe par `controller.ts` mais absent de ses appels `register`")
    print("        ne publie AUCUN de ses RPC : la session ne les expose pas, et l'appelant")
    print("        recoit un `HTTP 500` indiscernable d'une erreur d'execution.")
    print("        modules concernes : %d  |  RPC non exposes : %d" % (len(orphelins), n_orph))
    # TEMOIN AUTO-VERIFIANT, derive -- pas une liste de noms : un RPC que le HOST appelle est
    # forcement expose, sinon le harnais serait casse en permanence. S'il en apparait un ici,
    # c'est le CAPTEUR qui ment, et il doit le dire au lieu de publier son resultat. Cette
    # garde existe parce que la 1re version de cette etape a rendu 216 RPC « non exposes »,
    # dont `autoBootExtraire` et `playTurn`.
    faux = sorted(n for v in orphelins.values() for n in v
                  if any(groupe_de(f) == "host" for f in c1[n]))
    if faux:
        print("  ROUGE  CAPTEUR CASSE : %d RPC classes « non exposes » sont pourtant appeles"
              % len(faux))
        print("         par le HOST (donc necessairement exposes) : %s"
              % ", ".join(faux[:10]))
        return 2
    for f in sorted(orphelins):
        print("  NON-EXPOSE  %s : %s" % (f, ", ".join(sorted(orphelins[f]))))

    print()
    print("[480r8] NON VU par ce probe : un RPC invoque a la main et jamais ecrit nulle part")
    print("        (indiscernable d'un mort par toute mesure statique) ; ce que la session")
    print("        injectee expose vraiment (residu #480-r3) ; un appelant hors du depot.")

    if a.cliquet:
        if non_joignables:
            print()
            print("[480r8] CLIQUET ROUGE : %d RPC dont le NOM n'est ecrit nulle part hors de"
                  % len(non_joignables))
            print("        son fichier declarant. Un RPC expose doit etre JOIGNABLE : pour")
            print("        invoquer {\"method\": \"<nom>\"} il faut connaitre le nom, donc")
            print("        l'avoir lu quelque part. Le rendre vert : le cabler (C1/C2), ou")
            print("        l'ecrire dans une doc du depot -- c'est ce que « declarer outil de")
            print("        diagnostic » veut dire (`--catalogue` produit le bloc a coller dans")
            print("        `rpc-api.md`). Le critere est DERIVE du corpus, pas une liste de")
            print("        noms : il mord au 156e comme au 1er.")
            return 1
        print()
        print("[480r8] CLIQUET VERT : les %d RPC declares portent tous un canal NOMINATIF."
              % len(noms))
    return 0


if __name__ == "__main__":
    sys.exit(main())
