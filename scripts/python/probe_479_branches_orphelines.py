"""#479 -- l'etat des branches `worktree-agent-*` : orphelines / ancetres / non-ancetres.

Ce gisement se REFORME a chaque campagne : chaque agent dispatche laisse derriere lui une
branche `worktree-agent-<id>`, et son worktree est auto-supprime bien avant la branche. Au
2026-08-05, 184 branches pour 6 worktrees vivants -- 178 refs orphelines, dont 162 deja
integralement dans `master`.

CE PROBE MESURE, IL NE SUPPRIME RIEN. La suppression est un geste a portee DEPOT (les
branches sont partagees par tous les worktrees) : elle reste manuelle, precedee d'un
manifeste. Cf. `docs/rl/case-479-branches-orphelines.md`.

Trois compartiments, et le troisieme n'est pas un detail :

  ANCETRE       `git merge-base --is-ancestor <b> <ref>` == 0. Le contenu est LITTERALEMENT
                dans la ref : supprimer la branche ne perd rien.
  NON-ANCETRE   rc == 1. Ne prouve RIEN sur la perte : un squash-merge ou un cherry-pick
                laisse exactement cette signature (et `git branch --contains` ment ici).
                C'est une liste A AUDITER, jamais une liste a supprimer.
  NON MESURE    git n'a pas repondu (delai, OSError, rc inattendu). JAMAIS rabattu sur
                l'un des deux autres -- un capteur muet qui rend << 0 non-ancetre >> ferait
                supprimer des branches non auditees.

Tri-etat partout : `Mesure.erreur is None` => mesure ; sinon `valeur is None` et la CAUSE
est nommee (delai depasse / OSError / rc=<n>), jamais une sentinelle nue -- meme doctrine
que `loop_status.py` (#467-r6).

Usage :
    python scripts/python/probe_479_branches_orphelines.py
    python scripts/python/probe_479_branches_orphelines.py --lister-non-ancetres
    python scripts/python/probe_479_branches_orphelines.py --lister-ancetres   # supprimables
    python scripts/python/probe_479_branches_orphelines.py --json

Code de retour : 0 = tout mesure ; 1 = au moins un capteur muet (INCAPACITE, pas verdict) ;
2 = erreur d'usage.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

MOTIF_DEFAUT = "worktree-agent-*"
REF_DEFAUT = "origin/master"

# Le process n'a pas repondu du tout. Ce n'est pas un verdict de git : chaque appelant le
# traite comme << pas mesure >>. La CAUSE part en parallele dans `Git._pannes`.
RC_MUET = 127


# ------------------------------------------------------------------ tri-etat
@dataclass(frozen=True)
class Mesure:
    """`erreur is None` => MESURE. Sinon PAS MESURE, et `valeur` vaut None."""

    valeur: object | None
    source: str
    erreur: str | None = None

    @property
    def mesuree(self) -> bool:
        return self.erreur is None

    def txt(self, fmt: str = "%s") -> str:
        return (fmt % (self.valeur,)) if self.mesuree else "? (%s)" % self.erreur


def _ok(valeur, source: str) -> Mesure:
    return Mesure(valeur=valeur, source=source, erreur=None)


def _ko(source: str, erreur: str) -> Mesure:
    return Mesure(valeur=None, source=source, erreur=erreur)


# ------------------------------------------------------------------ source git
class Git:
    """Le seul poste d'entree. Ne LEVE jamais -- il NOMME sa panne.

    `--no-optional-locks` est pose au FOYER (#474) : ce lecteur peut tourner pendant qu'un
    autre worktree fait un merge, et un git tue dans la fenetre de `.git/index.lock`
    laisse un residu orphelin.
    """

    def __init__(self, repo: Path = REPO, timeout: float = 20.0) -> None:
        self.repo = repo
        self.timeout = timeout
        self._pannes: dict[str, str] = {}

    def run(self, *args: str, cle: str | None = None) -> tuple[int, str]:
        argv = ["git", "-C", str(self.repo), "--no-optional-locks", *args]
        cle = cle or (args[0] if args else "git")
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout,
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            self._pannes[cle] = "delai depasse (%g s)" % self.timeout
            return RC_MUET, ""
        except (OSError, subprocess.SubprocessError) as ex:
            self._pannes[cle] = "%s: %s" % (type(ex).__name__, str(ex)[:60])
            return RC_MUET, ""
        if p.returncode != 0:
            err = (p.stderr or "").strip().splitlines()
            # Le stderr est LE seul texte qui nomme la panne cote git aussi (#467-r6) : un
            # `rc=128` couvre << ref inconnue >>, << pas un depot >> et << objet corrompu >>.
            self._pannes[cle] = ("rc=%d: %s" % (p.returncode, err[0][:90]) if err
                                 else "rc=%d" % p.returncode)
        return p.returncode, (p.stdout or "")

    def cause(self, rc: int, cle: str) -> str:
        panne = self._pannes.get(cle)
        if panne is not None:
            return panne
        return ("n'a pas repondu (rc=%d, cause non enregistree)" % rc
                if rc == RC_MUET else "rc=%d" % rc)


# ------------------------------------------------------------------ mesures
def branches_du_motif(g: Git, motif: str) -> Mesure:
    """Les branches LOCALES du motif. Un rc non nul => PAS MESURE (pas une liste vide)."""
    rc, out = g.run("branch", "--list", motif, "--format=%(refname:short)", cle="branch")
    if rc != 0:
        return _ko("git branch --list %s" % motif, g.cause(rc, "branch"))
    noms = [l.strip() for l in out.splitlines() if l.strip()]
    return _ok(sorted(noms), "git branch --list %s" % motif)


def branches_a_worktree(g: Git) -> Mesure:
    """Les branches protegees par un worktree -- a EXCLURE de toute suppression.

    DEUX voies, et la seconde n'est pas un supplement de confort :

    1. la ligne `branch refs/heads/<x>` de `git worktree list --porcelain` ;
    2. la CONVENTION DE NOM du repertoire : `.claude/worktrees/agent-<id>` protege
       `worktree-agent-<id>`, que le worktree expose une branche ou non.

    Pourquoi la seconde -- MESURE du 2026-08-05, sur ce depot, pendant cette tranche :
    `worktree-agent-a403b7d0c9170ac76` est apparu comme ORPHELIN entre deux passages du
    probe, alors que son worktree existait, etait `locked`, et que son agent commitait
    (db615aa4 -> 4741e4c0 en quelques minutes). Un worktree en HEAD DETACHE n'emet aucune
    ligne `branch` -- et c'est exactement l'etat d'un worktree PENDANT `git rebase`, que
    la doctrine impose a chaque agent avant d'ouvrir sa PR. La voie 1, seule, ouvre donc
    une fenetre ou la branche d'un agent en plein rebase se lit << orpheline >> ; pire,
    `git branch -D` ne la refuserait PAS, puisqu'elle n'est alors checkoutee nulle part.

    La voie 2 sur-protege legerement (elle garde la branche d'un worktree qui aurait
    volontairement change de branche). C'est le bon sens de l'erreur : on ne supprime
    jamais par defaut d'information.
    """
    rc, out = g.run("worktree", "list", "--porcelain", cle="worktree")
    if rc != 0:
        return _ko("git worktree list --porcelain", g.cause(rc, "worktree"))
    noms = set()
    for ligne in out.splitlines():
        if ligne.startswith("branch refs/heads/"):
            noms.add(ligne[len("branch refs/heads/"):].strip())
        elif ligne.startswith("worktree "):
            base = ligne[len("worktree "):].strip().replace("\\", "/").rstrip("/")
            base = base.rsplit("/", 1)[-1]
            if base.startswith("agent-"):
                noms.add("worktree-" + base)
    return _ok(noms, "git worktree list --porcelain (branch + convention de nom)")


def ref_existe(g: Git, ref: str) -> Mesure:
    rc, out = g.run("rev-parse", "--verify", "--quiet", ref + "^{commit}", cle="rev-parse")
    if rc != 0 or not out.strip():
        return _ko("git rev-parse %s" % ref, g.cause(rc if rc != 0 else 1, "rev-parse"))
    return _ok(out.strip(), "git rev-parse %s" % ref)


def est_ancetre(g: Git, branche: str, ref: str) -> Mesure:
    """rc 0 => ancetre ; rc 1 => non-ancetre ; tout le reste => PAS MESURE pour CETTE branche.

    `merge-base --is-ancestor` repond a << le contenu est-il dans l'historique de la ref >>,
    ce qui est SUFFISANT pour supprimer sans perte, mais pas NECESSAIRE : un squash-merge
    rend rc=1 alors que le contenu est dans la ref. D'ou l'audit du compartiment non-ancetre.
    """
    rc, _ = g.run("merge-base", "--is-ancestor", branche, ref, cle="merge-base")
    if rc == 0:
        return _ok(True, "git merge-base --is-ancestor")
    if rc == 1:
        return _ok(False, "git merge-base --is-ancestor")
    return _ko("git merge-base --is-ancestor", g.cause(rc, "merge-base"))


def detail_branche(g: Git, branche: str) -> dict:
    """SHA de pointe, date ISO, sujet -- ce qu'il faut pour retrouver un commit supprime."""
    rc, out = g.run("log", "-1", "--format=%H%x09%cI%x09%s", branche, cle="log")
    if rc != 0 or not out.strip():
        return {"sha": None, "date": None, "sujet": None,
                "erreur": g.cause(rc if rc != 0 else 1, "log")}
    champs = out.strip().split("\t")
    while len(champs) < 3:
        champs.append("")
    return {"sha": champs[0], "date": champs[1], "sujet": champs[2], "erreur": None}


def cherry(g: Git, branche: str, ref: str) -> Mesure:
    """`git cherry <ref> <branche>` : '-' = un patch EQUIVALENT existe deja dans la ref.

    Detecte le cherry-pick et le rebase (patch-id stable a travers eux). AVEUGLE au
    SQUASH-merge, qui fusionne N commits en un patch-id different -- d'ou `presence()`.
    """
    rc, out = g.run("cherry", ref, branche, cle="cherry")
    if rc != 0:
        return _ko("git cherry", g.cause(rc, "cherry"))
    plus = sum(1 for l in out.splitlines() if l.startswith("+"))
    moins = sum(1 for l in out.splitlines() if l.startswith("-"))
    return _ok({"sans_equivalent": plus, "avec_equivalent": moins}, "git cherry")


def homonymes(g: Git, branche: str, ref: str) -> Mesure:
    """Un commit de MEME SUJET existe-t-il dans la ref ? -- la trace d'une RELIVRAISON.

    Quand un agent voit sa branche refusee/perdue et que le travail est re-commite (ou
    rebase puis squash-merge), le SHA change, le patch-id change, mais le SUJET est
    recopie tel quel. Mesure du 2026-08-05 : c'est ce critere -- et lui seul -- qui a
    tranche `FragBomb/BasiliskBarrage`, ou `git cherry` disait `+1` (aucun equivalent) et
    ou master portait pourtant le meme port sous `aa3035a1`.

    INDICE, pas preuve : deux tranches d'un meme sujet peuvent porter le meme titre. A
    croiser avec la presence du contenu et avec le commit d'INTRODUCTION des fichiers neufs
    (`git log --diff-filter=A -- <fichier>`).
    """
    rc, out = g.run("log", "--format=%s", "%s..%s" % (ref, branche), cle="log")
    if rc != 0:
        return _ko("git log %s..%s" % (ref, branche), g.cause(rc, "log"))
    sujets = [l.strip() for l in out.splitlines() if l.strip()]
    trouves: list[tuple[str, str | None]] = []
    for s in sujets:
        rc2, o2 = g.run("log", ref, "-1", "--format=%h", "--fixed-strings", "--grep=" + s,
                        cle="log")
        trouves.append((s, o2.strip() or None if rc2 == 0 else None))
    return _ok({"sujets": trouves,
                "relivres": sum(1 for _, h in trouves if h),
                "total": len(trouves)}, "git log --fixed-strings --grep")


def _lignes_ajoutees(diff: str) -> dict[str, list[str]]:
    """Les lignes '+' du diff, par fichier DESTINATION. `--unified=0` => pas de contexte."""
    par_fichier: dict[str, list[str]] = {}
    courant: str | None = None
    for ligne in diff.splitlines():
        if ligne.startswith("+++ "):
            chemin = ligne[4:].strip()
            courant = None if chemin == "/dev/null" else chemin[2:] if chemin.startswith(
                "b/") else chemin
            if courant is not None:
                par_fichier.setdefault(courant, [])
        elif ligne.startswith("--- "):
            continue
        elif ligne.startswith("+") and courant is not None:
            corps = ligne[1:].strip()
            if corps:
                par_fichier[courant].append(corps)
    return par_fichier


def presence(g: Git, branche: str, ref: str) -> Mesure:
    """Le CONTENU de la branche est-il dans la ref ? -- ligne a ligne, pas par historique.

    << Pas ancetre >> ne prouve PAS << travail perdu >> : un squash-merge relivre le meme
    contenu sous un autre commit, et `git branch --contains` ment sur ce point precis. On
    mesure donc ce qui compte VRAIMENT : chaque ligne AJOUTEE par la branche (diff a trois
    points depuis le merge-base) se retrouve-t-elle dans le fichier tel qu'il est dans la
    ref ?

    C'est un INDICE FORT, pas une preuve formelle :
      - 100 % ne prouve pas l'identite (une ligne peut exister ailleurs dans le fichier) ;
      - < 100 % ne prouve pas la perte (reformulation, renommage de fichier, refactor).
    Il sert a TRIER : au-dela d'un taux eleve, lire le residu suffit ; en dessous, la
    branche part en audit manuel. Un fichier ABSENT de la ref est compte comme 0 %, et
    NOMME -- c'est le cas qui merite le coup d'oeil.
    """
    rc, diff = g.run("diff", "--unified=0", "--no-color", "%s...%s" % (ref, branche),
                     cle="diff")
    if rc != 0:
        return _ko("git diff %s...%s" % (ref, branche), g.cause(rc, "diff"))
    par_fichier = _lignes_ajoutees(diff)
    total = 0
    trouvees = 0
    manquants: list[tuple[str, int, int]] = []
    absents: list[str] = []
    for chemin, lignes in sorted(par_fichier.items()):
        if not lignes:
            continue
        rc2, contenu = g.run("show", "%s:%s" % (ref, chemin), cle="show")
        if rc2 != 0:
            absents.append(chemin)
            total += len(lignes)
            manquants.append((chemin, len(lignes), len(lignes)))
            continue
        corpus = {l.strip() for l in contenu.splitlines() if l.strip()}
        absentes = sum(1 for l in lignes if l not in corpus)
        total += len(lignes)
        trouvees += len(lignes) - absentes
        if absentes:
            manquants.append((chemin, absentes, len(lignes)))
    return _ok({"lignes": total, "presentes": trouvees,
                "pct": (100.0 * trouvees / total) if total else 100.0,
                "fichiers_avec_manque": manquants,
                "fichiers_absents_de_la_ref": absents},
               "git diff --unified=0 + git show")


def etat(g: Git, motif: str, ref: str, avec_detail: bool = False,
         avec_presence: bool = False, avec_pr: bool = False) -> dict:
    e: dict = {"motif": motif, "ref": ref}
    m_ref = ref_existe(g, ref)
    e["ref_sha"] = m_ref
    m_br = branches_du_motif(g, motif)
    m_wt = branches_a_worktree(g)
    e["toutes"] = m_br
    e["a_worktree"] = m_wt

    if not m_br.mesuree:
        for k in ("orphelines", "ancetres", "non_ancetres", "indecidables"):
            e[k] = _ko(m_br.source, m_br.erreur or "pas mesure")
        return e

    toutes = list(m_br.valeur or [])
    if not m_wt.mesuree:
        # On refuse de deviner l'ensemble protege : sans lui, un ancetre pourrait etre une
        # branche checkoutee. On mesure quand meme ce qui reste mesurable, mais << orphelines >>
        # et tout ce qui en decoule reste PAS MESURE.
        for k in ("orphelines", "ancetres", "non_ancetres", "indecidables"):
            e[k] = _ko(m_wt.source, m_wt.erreur or "pas mesure")
        return e

    protegees = set(m_wt.valeur or set())
    orphelines = [b for b in toutes if b not in protegees]
    e["orphelines"] = _ok(orphelines, "branch - worktree")

    if not m_ref.mesuree:
        for k in ("ancetres", "non_ancetres", "indecidables"):
            e[k] = _ko(m_ref.source, m_ref.erreur or "pas mesure")
        return e

    anc: list[str] = []
    non: list[str] = []
    ind: list[tuple[str, str]] = []
    for b in orphelines:
        m = est_ancetre(g, b, ref)
        if not m.mesuree:
            ind.append((b, m.erreur or "pas mesure"))
        elif m.valeur:
            anc.append(b)
        else:
            non.append(b)
    e["ancetres"] = _ok(anc, "git merge-base --is-ancestor")
    e["non_ancetres"] = _ok(non, "git merge-base --is-ancestor")
    e["indecidables"] = _ok(ind, "git merge-base --is-ancestor")

    if avec_pr:
        # LA VOIE QUI MANQUAIT. Sans elle, ce probe annonce N << non-ancetres A AUDITER >> --
        # ce qui a ete lu comme N audits MANUELS, alors que le squash-merge explique la
        # quasi-totalite d'entre eux et que `gh` sait le dire (mesure du 2026-08-07 : 16 sur 16
        # portaient une PR mergee). Le critere est celui de `livraison.py`, partage avec
        # `nettoyer_livraison` et `loop_status` : trois outils, une seule reponse.
        import livraison as LV
        import loop_status as LS
        fen = LV.lire_fenetre_pr(
            LS.Sources(repo=g.repo if hasattr(g, "repo") else REPO,
                       avec_host=False, timeout=20.0, timeout_gh=20.0).gh,
            limite=LV.LIMITE_MANUELLE)
        verd = LV.classer(non, set(), fen)
        e["portee_pr"] = fen.portee()
        e["livrees_par_pr"] = _ok([b for b in non if verd[b].livree],
                                  "gh pr list --state all (PR mergee sur cette head)")
        e["a_auditer"] = _ok([b for b in non if not verd[b].livree],
                             "non-ancetres QUE la PR n'explique pas")

    if avec_detail:
        e["details"] = {b: detail_branche(g, b) for b in (non + [x for x, _ in ind])}
    if avec_presence:
        # UNIQUEMENT sur les non-ancetres : pour un ancetre la question ne se pose pas, et
        # la mesure coute un `git show` par fichier touche.
        e["audit"] = {b: {"cherry": cherry(g, b, ref), "homonymes": homonymes(g, b, ref),
                          "presence": presence(g, b, ref)} for b in non}
    return e


# ------------------------------------------------------------------ rendu
def _n(m: Mesure) -> str:
    if not m.mesuree:
        return "? (%s)" % m.erreur
    v = m.valeur
    return str(len(v)) if isinstance(v, (list, set, tuple)) else str(v)


def rendu(e: dict, lister_anc: bool, lister_non: bool) -> str:
    L = []
    L.append("[479] branches '%s' vs %s" % (e["motif"], e["ref"]))
    L.append("  ref                : %s" % e["ref_sha"].txt())
    L.append("  branches du motif  : %s" % _n(e["toutes"]))
    # Ce compte n'est PAS filtre par le motif : c'est l'ensemble PROTEGE, et le montrer en
    # entier est le point -- une protection masquee par un filtre serait une protection perdue.
    L.append("  protegees (tous motifs): %s" % _n(e["a_worktree"]))
    L.append("  ORPHELINES         : %s" % _n(e["orphelines"]))
    L.append("    ancetres de la ref (contenu DANS la ref, supprimables) : %s"
             % _n(e["ancetres"]))
    L.append("    NON-ancetres (A AUDITER -- squash/cherry-pick possible) : %s"
             % _n(e["non_ancetres"]))
    L.append("    non mesurees (git muet, NE PAS supprimer)              : %s"
             % _n(e["indecidables"]))
    if "livrees_par_pr" in e:
        L.append("    dont LIVREES par une PR mergee (le squash, `--pr`)    : %s"
                 % _n(e["livrees_par_pr"]))
        L.append("    reste A AUDITER (ni ancetre, ni PR)                   : %s"
                 % _n(e["a_auditer"]))
        L.append("  %s" % e.get("portee_pr", ""))

    if e["a_worktree"].mesuree and e["a_worktree"].valeur:
        L.append("  branches protegees par un worktree :")
        for b in sorted(e["a_worktree"].valeur):
            L.append("    %s" % b)

    if lister_anc and e["ancetres"].mesuree:
        L.append("  -- ancetres (%d) --" % len(e["ancetres"].valeur))
        for b in e["ancetres"].valeur:
            L.append("    %s" % b)

    if lister_non and e["non_ancetres"].mesuree:
        L.append("  -- NON-ancetres (%d) --" % len(e["non_ancetres"].valeur))
        det = e.get("details") or {}
        for b in e["non_ancetres"].valeur:
            d = det.get(b) or {}
            if d.get("erreur"):
                L.append("    %-40s ? (%s)" % (b, d["erreur"]))
            else:
                L.append("    %-40s %s  %s  %s"
                         % (b, (d.get("sha") or "")[:9], (d.get("date") or "")[:10],
                            (d.get("sujet") or "")[:70]))

    audit = e.get("audit")
    if audit:
        L.append("  -- AUDIT des non-ancetres (le CONTENU est-il dans la ref ?) --")
        for b in sorted(audit):
            mc = audit[b]["cherry"]
            mp = audit[b]["presence"]
            mh = audit[b]["homonymes"]
            if not mc.mesuree or not mp.mesuree or not mh.mesuree:
                L.append("    %-40s ? (%s)"
                         % (b[-17:], mc.erreur or mh.erreur or mp.erreur))
                continue
            c = mc.valeur
            p = mp.valeur
            h = mh.valeur
            L.append("    %-18s cherry +%d/-%d  sujets relivres %d/%d  "
                     "lignes %d/%d presentes (%.1f%%)"
                     % (b[-17:], c["sans_equivalent"], c["avec_equivalent"],
                        h["relivres"], h["total"], p["presentes"], p["lignes"], p["pct"]))
            for sujet, sha in h["sujets"]:
                if sha:
                    L.append("        relivre par %s : %s" % (sha, sujet[:60]))
            for chemin, manque, tot in p["fichiers_avec_manque"]:
                marque = "ABSENT DE LA REF" if chemin in p["fichiers_absents_de_la_ref"] \
                    else "%d/%d manquantes" % (manque, tot)
                L.append("        %-62s %s" % (chemin[:62], marque))

    if e["indecidables"].mesuree and e["indecidables"].valeur:
        L.append("  -- NON MESUREES (%d) --" % len(e["indecidables"].valeur))
        for b, cause in e["indecidables"].valeur:
            L.append("    %-40s %s" % (b, cause))
    return "\n".join(L)


def _m_json(v: Mesure) -> dict:
    val = v.valeur
    if isinstance(val, set):
        val = sorted(val)
    return {"valeur": val, "source": v.source, "erreur": v.erreur, "mesuree": v.mesuree}


def _json_pret(e: dict) -> dict:
    out = {}
    for k, v in e.items():
        if isinstance(v, Mesure):
            out[k] = _m_json(v)
        elif k == "audit":
            out[k] = {b: {kk: _m_json(vv) for kk, vv in d.items()} for b, d in v.items()}
        else:
            out[k] = v
    return out


def _muets(e: dict) -> list[str]:
    muets = [k for k, v in e.items() if isinstance(v, Mesure) and not v.mesuree]
    for b, d in (e.get("audit") or {}).items():
        muets += ["audit/%s/%s" % (b[-17:], kk) for kk, vv in d.items() if not vv.mesuree]
    return muets


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="#479 -- etat des branches worktree-agent-*")
    ap.add_argument("--motif", default=MOTIF_DEFAUT)
    ap.add_argument("--ref", default=REF_DEFAUT,
                    help="ref de reference (defaut: %s)" % REF_DEFAUT)
    ap.add_argument("--lister-ancetres", action="store_true",
                    help="lister les branches dont le contenu est DANS la ref")
    ap.add_argument("--lister-non-ancetres", action="store_true",
                    help="lister les branches a auditer (avec sha/date/sujet)")
    ap.add_argument("--presence", action="store_true",
                    help="pour chaque non-ancetre : cherry + taux de lignes ajoutees "
                         "presentes dans la ref (indice de relivraison par squash)")
    ap.add_argument("--pr", action="store_true",
                    help="applique AUSSI la voie PR mergee aux non-ancetres (le squash-merge "
                         "les explique presque tous). Reseau : ~5 s.")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--timeout", type=float, default=20.0)
    a = ap.parse_args(argv)

    g = Git(timeout=a.timeout)
    e = etat(g, a.motif, a.ref, avec_detail=a.lister_non_ancetres or a.json,
             avec_presence=a.presence, avec_pr=a.pr)

    if a.json:
        print(json.dumps(_json_pret(e), indent=2, ensure_ascii=True))
    else:
        print(rendu(e, a.lister_ancetres, a.lister_non_ancetres))

    muets = _muets(e)
    if muets:
        if not a.json:
            print("  INCAPACITE : %s pas mesure(s) -- ne rien supprimer sur cette base."
                  % ", ".join(muets))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
