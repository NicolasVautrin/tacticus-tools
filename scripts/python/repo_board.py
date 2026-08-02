"""Board « sante du depot » : croisement PULL REQUESTS x TRANSCRIPTS x GIT, par jour.

Pendant de `fleet_board.py`, qui montre la flotte MAINTENANT. Celui-ci montre ce que la flotte a
PRODUIT, dans la duree : combien de PR, a quel cout en tokens, pour combien de lignes retenues.

TROIS SOURCES INDEPENDANTES, jointes sur la date locale :

  1. GitHub -- `gh pr list --state all`. Etat, dates, additions/deletions, branche, merge commit.
  2. Transcripts Claude Code -- `~/.claude/projects/<slug>/*.jsonl` (boucle principale) et
     `*/subagents/agent-*.jsonl` (agents). Tokens par jour, dedupes par uuid.
  3. Git -- `git log --numstat`. Commits et lignes par jour.

L'UNITE DE LIVRAISON EST LE MERGE D'UNE PR, PAS LE COMMIT. Les lignes d'une PR sont lues au DIFF
NET de son merge contre son premier parent (`git diff <merge>^1 <merge>`), et rattachees au jour du
MERGE. Une PR = une livraison atomique.

  - Insensible a la forme de l'historique de la branche : un `wip` puis son correctif comptent une
    fois. Mesure du 2026-08-01 : +427 449 lignes en net contre +430 816 en sommant les commits,
    soit 3 367 de churn interne (1 %).
  - Immunise contre les ALLERS-RETOURS DE REBASE. Quand l'orchestrateur renvoie une PR a son agent,
    elle revient sur un master qui a bouge, et deux PR mergees coup sur coup peuvent revendiquer
    les memes commits -- 831 revendications pour 816 commits distincts, 13 reclames deux ou trois
    fois. Au niveau du merge, la question ne se pose plus : `^1` est master AVANT le merge, donc
    le diff ne contient jamais ce qu'une PR precedente a deja fait entrer.
  - Marche uniformement sur les merges SQUASHES : `^1` existe toujours, le merge porte le diff.
    Necessaire ici -- seules 263 des 422 PR mergees ont produit un vrai merge a deux parents.

Le reste -- pushs directs sur master par l'orchestrateur : correctifs a chaud, docs, outillage --
est compte A PART et affiche, jamais melange au denominateur. Mesure du 2026-08-01, fenetre depuis
le 2026-07-10 : 1 290 commits de contenu, dont 819 arrives par une PR (63 %) et 471 pousses
directement.

LA JOINTURE PR <-> AGENT a DEUX voies, qui se corroborent :

  1. LA BRANCHE -- `worktreeBranch` du meta d'agent == `headRefName` de la PR. 381/422 PR mergees
     (90 %).
  2. LE MESSAGE DU MERGE -- un `agent-<id>` cite dans le corps, resolvable en
     `<session>/subagents/agent-<id>.jsonl`. 247/422 (59 %), dont 243 sur des commits
     « Merge pull request ».

La voie 2 est un SOUS-ENSEMBLE STRICT de la voie 1 : l'union reste 381, elle n'ajoute aucune PR.
Elle est gardee quand meme parce que, sur les 247 cas ou les deux repondent, elles sont d'accord
247 fois sur 247 -- validation croisee gratuite -- et parce qu'elle survit a un meta disparu.
VOIE ECARTEE -- le trailer `Claude-Session` : il nomme une SESSION API, or une conversation en
enchaine plusieurs. Mesure : 14 identifiants, dont 13 presents dans DEUX transcripts principaux ou
plus, et chacun present en outre dans 0 a 84 transcripts d'agent (l'agent herite du pied de page de
son parent). Il ne designe donc ni un transcript ni un agent -- et il ne figure que sur 16 des 263
commits « Merge pull request ».

Les 41 PR sans agent resolu portent une branche qui n'est celle d'aucun worktree
(`worktree-agent-350r3bc`, `agent/192-...`, `feat/113-votann-lot1`) -- ce sont des PR D'AGENT elles
aussi, avec un meta introuvable, pas des PR d'une autre provenance. Le denominateur les GARDE donc
par defaut ; les exclure amputait de 46 commits bien reels et basculait +39 791 lignes a tort du
cote « hors PR ». `--strict-agent` fournit la lecture etroite pour qui veut l'ecart.

CE QUE LES CHIFFRES NE DISENT PAS, et qu'il ne faut pas leur faire dire :

  - Les tokens d'un jour couvrent TOUTE l'activite du projet (RE, audits, conversation), pas
    seulement ce qui a fini en PR. Un `tokens / PR` est donc un indicateur de TENDANCE entre
    periodes, jamais un cout unitaire de production.
  - Les lignes de `git log --numstat` incluent le CHURN de scission de modules : un fichier eclate
    compte N ajouts + N suppressions pour zero code neuf. La croissance NETTE de l'arbre
    (`git diff base..HEAD`) est la mesure honnete, et elle est calculee a part. Elle couvre
    l'arbre ENTIER, PR et pushs directs confondus -- ce n'est pas le pendant net des colonnes.
  - `data/symbols` est exclu partout : c'est un artefact genere (table de symboles), pas du code
    ecrit. L'inclure gonflait les journees de re-dump de ~300 000 lignes.

Usage :
    python scripts/python/repo_board.py            # table console + logs/repo-board.html
    python scripts/python/repo_board.py --open      # ouvre la page
    python scripts/python/repo_board.py --since 2026-07-01
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Le corps d'un message de merge cite l'agent auteur sous cette forme -- c'est le NOM DE FICHIER
# de son transcript, `<session>/subagents/agent-<id>.jsonl`, donc un lien direct et non ambigu.
AGENT_RX = re.compile(r"agent-([0-9a-f]{8,})")
REC_SEP = "\x1e"

REPO = Path(__file__).resolve().parents[2]
# Le NOM DU FICHIER est l'identite de l'artefact publie : republier le meme chemin conserve
# l'URL, un chemin different en cree une neuve. Ne pas le renommer sans republier derriere.
OUT = REPO / "logs" / "repo-board.html"

# Artefact genere, versionne expres, mais ce n'est pas du code ecrit -- cf. docstring.
EXCLUDE = ":(exclude)data/symbols"


def sh(args: list[str], cwd: Path = REPO) -> str:
    """Rend stdout, et REMONTE stderr en cas d'echec.

    Sans ca, un `gh` qui echoue rend une chaine vide et l'appelant ne peut qu'ACCUSER l'auth --
    diagnostic faux vu le 2026-07-28 sur un simple `HTTP 502: Bad Gateway` de l'API GitHub.
    """
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0 and not r.stdout.strip():
        raise SystemExit("%s a echoue (rc=%d) : %s"
                         % (args[0], r.returncode, (r.stderr or "").strip()[:300]))
    return r.stdout


def sh_soft(args: list[str]) -> str:
    """Variante TOLERANTE : rend "" sur echec au lieu de lever.

    Indispensable pour `rev-list <sha>^1..<sha>` : un merge de PR SQUASHE n'a qu'un parent, donc
    `^2` n'existe pas et git sort en erreur. C'est un cas NORMAL, pas une panne -- l'appelant
    retombe alors sur le merge lui-meme.
    """
    r = subprocess.run(args, cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else ""


def project_dir() -> Path:
    """`~/.claude/projects/<slug>` ou <slug> = chemin du repo, ':' et separateurs -> '-'."""
    root = Path.home() / ".claude" / "projects"
    slug = str(REPO).replace(":", "-").replace("\\", "-").replace("/", "-")
    cand = root / slug
    if cand.is_dir():
        return cand
    best = max(root.glob("*"), key=lambda p: len(list(p.glob("*/subagents/agent-*.jsonl"))),
               default=None)
    if best is None:
        raise SystemExit("aucun repertoire de projet Claude sous %s" % root)
    return best


def _ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------- 1. pull requests
def load_prs() -> list[dict]:
    raw = sh(["gh", "pr", "list", "--state", "all", "--limit", "500", "--json",
              "number,title,state,createdAt,mergedAt,closedAt,additions,deletions,"
              "changedFiles,headRefName,mergeCommit"])
    if not raw.strip():
        raise SystemExit("gh n'a rien rendu -- `gh auth status` ?")
    out = []
    for p in json.loads(raw):
        created, merged = _ts(p["createdAt"]), _ts(p.get("mergedAt"))
        out.append(dict(
            num=p["number"], title=p["title"], state=p["state"], branch=p["headRefName"],
            created=created, merged=merged,
            merge_sha=(p.get("mergeCommit") or {}).get("oid") or "",
            day=created.astimezone().strftime("%Y-%m-%d") if created else "",
            merged_day=merged.astimezone().strftime("%Y-%m-%d") if merged else "",
            # duree de vie : ouverture -> merge. Sur une campagne d'agents elle mesure la
            # latence d'INTEGRATION, pas le temps de travail (l'agent a deja fini).
            ttm=((merged - created).total_seconds() / 60.0) if (merged and created) else None,
            add=p["additions"], dele=p["deletions"], files=p["changedFiles"]))
    return out


# ---------------------------------------------------------------- 2. transcripts
def _ctx(u) -> int:
    """Tokens de CONTEXTE d'un tour = `input + cache_creation + cache_read`.

    C'est la taille du PROMPT envoye, ni plus ni moins : ce que le modele a du lire pour repondre.
    L'`output` en est exclu (c'est ce qu'il a ecrit, pas ce qu'il a lu), et aucune ponderation de
    facturation n'est appliquee (pas de cw*1.25 / cr*0.10) -- on compte des tokens, pas des euros.

    Somme sur une journee, ce total compte N FOIS le meme contexte relu d'un tour a l'autre. C'est
    voulu : c'est precisement la charge de lecture du jour. Ne pas le confondre avec l'occupation
    de fenetre du fleet-board, qui est le prompt d'UN SEUL tour (le dernier).
    """
    return (int(u.get("input_tokens") or 0)
            + int(u.get("cache_creation_input_tokens") or 0)
            + int(u.get("cache_read_input_tokens") or 0))


def load_tokens(pdir: Path) -> tuple[dict, dict]:
    """Rend (par_jour, par_agent_id). Streaming : on ne parse que les lignes portant `usage`."""
    by_day = defaultdict(lambda: defaultdict(int))
    by_agent = defaultdict(lambda: defaultdict(int))
    seen = set()
    for fp in sorted(pdir.glob("*.jsonl")) + sorted(pdir.glob("*/subagents/agent-*.jsonl")):
        aid = fp.stem.replace("agent-", "") if "subagents" in fp.parts else None
        try:
            fh = fp.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for ln in fh:
                if '"usage"' not in ln:
                    continue
                try:
                    rec = json.loads(ln)
                except Exception:
                    continue
                uid = rec.get("uuid")
                if uid:
                    if uid in seen:
                        continue
                    seen.add(uid)
                u = (rec.get("message") or {}).get("usage") or {}
                if not u:
                    continue
                t = _ts(rec.get("timestamp"))
                if not t:
                    continue
                ctx = _ctx(u)
                day = t.astimezone().strftime("%Y-%m-%d")
                by_day[day]["ctx"] += ctx
                by_day[day]["turns"] += 1
                if aid:
                    by_day[day]["agent_ctx"] += ctx
                    a = by_agent[aid]
                    a["ctx"] += ctx
                    a["turns"] += 1
                    if not a.get("first") or t < a["first"]:
                        a["first"] = t
                    if not a.get("last") or t > a["last"]:
                        a["last"] = t
    return by_day, by_agent


def agents_on_disk(pdir: Path) -> set:
    return {p.stem.replace("agent-", "") for p in pdir.glob("*/subagents/agent-*.jsonl")}


def merge_msg_agents(known: set) -> dict:
    """SHA de merge -> id d'agent CITE dans son message, filtre sur les transcripts existants.

    Deuxieme voie de jointure, corroborante (cf. docstring du module) : elle couvre moins que la
    branche mais n'est jamais en desaccord avec elle, et elle survit a un meta disparu. Le filtre
    par `known` est ce qui empeche de fabriquer un lien : un id sans transcript n'est pas retenu.
    """
    raw = sh(["git", "log", "--format=%H\x1f%B" + REC_SEP])
    out = {}
    for blk in raw.split(REC_SEP):
        f = blk.strip("\n").split("\x1f")
        if len(f) < 2:
            continue
        ids = [i for i in AGENT_RX.findall(f[1]) if i in known]
        if ids:
            out[f[0]] = ids[0]
    return out


def load_metas(pdir: Path) -> dict:
    """branche -> {id, name}. Double indexation : le meta, et l'id lu DANS le nom de branche.

    Certaines PR portent une branche `worktree-agent-<id>` dont le meta est absent (transcript
    dans un autre repertoire de projet, ou meta jamais ecrit). Reconstruire l'id depuis le nom
    rattrape ces cas sans inventer de correspondance : l'id EST dans la chaine.
    """
    by_branch = {}
    for p in pdir.glob("*/subagents/agent-*.meta.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        aid = p.name.replace("agent-", "").replace(".meta.json", "")
        br = (m.get("worktreeBranch") or "").strip()
        rec = dict(id=aid, name=m.get("description") or aid, type=m.get("agentType") or "")
        if br:
            by_branch[br] = rec
        by_branch.setdefault("worktree-agent-%s" % aid, rec)
    return by_branch


# ---------------------------------------------------------------- 3. git
def pr_commits(prs: list[dict], strict: bool) -> dict:
    """SHA -> numero de PR, pour chaque commit AMENE par une PR mergee.

    `rev-list <merge>^1..<merge>` = ce que le merge a fait entrer, et rien d'autre : le premier
    parent est master avant le merge, le second la tete de la branche. Un merge SQUASHE n'a qu'un
    parent -- `^2` echoue, et c'est le merge lui-meme qui PORTE le contenu : on le compte pour un.
    `strict` restreint aux PR dont l'agent est identifie par sa branche (cf. docstring du module).

    UN COMMIT N'EST COMPTE QU'UNE FOIS, ET POUR LA PREMIERE PR QUI L'A FAIT ENTRER. Quand
    l'orchestrateur renvoie une PR a son agent pour rebase, la branche repart d'un master qui a
    bouge : deux PR mergees coup sur coup peuvent alors revendiquer les memes commits.
    Mesure du 2026-08-01 : 831 revendications pour 816 commits distincts -- 13 commits reclames
    par deux ou trois PR (grappe #378-#386). D'ou le parcours par date de MERGE croissante :
    `setdefault` attribue au premier arrive, qui est celui qui a reellement fait entrer le code.
    Ce que ces allers-retours coutent VRAIMENT est en tokens, dans le transcript de l'agent
    repris -- pas en commits. Verifie par ailleurs : 0 branche porte plusieurs PR, 0 groupe de
    `git patch-id` partage (aucun contenu reapplique sous un autre SHA), et 0 des 31 PR fermees
    sans merge n'a vu sa tache remergee sous un autre numero.
    """
    owner = {}
    for p in sorted(prs, key=lambda q: q["merged"] or datetime.max.replace(tzinfo=timezone.utc)):
        if not p["merge_sha"] or (strict and not p.get("agent_id")):
            continue
        sha = p["merge_sha"]
        # --no-merges : une branche d'agent qui a merge master en cours de route amene ses propres
        # merges, qui n'apportent aucune ligne. Les compter gonflait le perimetre de 174 sur 993
        # (mesure du 2026-08-01) pour zero contenu.
        shas = [s for s in sh_soft(["git", "rev-list", "--no-merges",
                                    "%s^1..%s" % (sha, sha)]).split() if s]
        n = 0
        for s in (shas or [sha]):
            if s not in owner:
                owner[s] = p["num"]
                n += 1
        p["n_commits"] = n
        # LA LIVRAISON : diff NET du merge contre master-avant-merge. C'est cette mesure-la qui
        # alimente les colonnes, pas la somme des commits ci-dessus (gardee pour le compte seul).
        for ln in sh_soft(["git", "diff", "--numstat", "%s^1" % sha, sha,
                           "--", ".", EXCLUDE]).splitlines():
            f = ln.split("\t")
            if len(f) == 3 and f[0] != "-":
                p["net_add"] += int(f[0])
                p["net_del"] += int(f[1])
    return owner


def load_git(since: str, keep: set) -> tuple[dict, dict]:
    """Agrege par jour. `commits`/`add` = PR SEULEMENT ; `direct_*` = les pushs hors PR.

    Les deux sont retenus : un board qui n'afficherait que le perimetre PR laisserait croire que
    le depot n'a pas d'autre activite, alors que les pushs directs de l'orchestrateur en portent
    plus du tiers.
    """
    # %P donne les parents SUR LA LIGNE : deux parents = merge. Le demander a `git log` evite un
    # `rev-parse` par commit -- 1 459 sous-processus sous Windows, plusieurs minutes pour rien.
    raw = sh(["git", "log", "--pretty=format:C|%H|%aI|%P", "--numstat",
              "--since", since, "--", ".", EXCLUDE])
    by_day = defaultdict(lambda: defaultdict(int))
    day = None
    pfx = "direct_"
    for ln in raw.splitlines():
        if ln.startswith("C|"):
            _, sha, iso, parents = ln.split("|", 3)
            day = _ts(iso).astimezone().strftime("%Y-%m-%d")
            # Un merge ne tombe dans AUCUN des deux seaux, et le test passe AVANT `keep` : une
            # branche d'agent qui a merge master en cours de route amene ses propres merges, que
            # `rev-list` rapporte donc comme commits de la PR. Les compter gonflait le perimetre
            # PR de 174 sur 993 (mesure du 2026-08-01) pour zero ligne -- --numstat ignore leur
            # diff. La partition doit rester : PR + direct + merges = tous les commits.
            merge = len(parents.split()) > 1
            pfx = None if merge else ("" if sha in keep else "direct_")
            if pfx is not None:
                by_day[day][pfx + "commits"] += 1
            continue
        parts = ln.split("\t")
        if len(parts) != 3 or day is None or parts[0] == "-" or pfx is None:
            continue
        by_day[day][pfx + "add"] += int(parts[0])
        by_day[day][pfx + "del"] += int(parts[1])
    # croissance NETTE de l'arbre sur la fenetre -- annule le churn de scission de modules
    base = sh(["git", "rev-list", "-1", "--before", "%s 00:00" % since, "HEAD"]).strip()
    net = {}
    if base:
        stat = sh(["git", "diff", "--shortstat", base, "HEAD", "--", ".", EXCLUDE]).strip()
        net["shortstat"] = stat
    return by_day, net


# ---------------------------------------------------------------- assemblage
def build(since: str, strict: bool = False) -> dict:
    pdir = project_dir()
    prs = load_prs()
    tok_day, tok_agent = load_tokens(pdir)
    metas = load_metas(pdir)

    known = agents_on_disk(pdir)
    by_msg = merge_msg_agents(known)

    joined = via_msg = agree = clash = 0
    for pr in prs:
        m = metas.get(pr["branch"])
        cited = by_msg.get(pr["merge_sha"]) if pr["merge_sha"] else None
        if m and cited:
            # Confrontation des deux voies. `clash` doit rester a 0 : un desaccord signifierait
            # qu'une des deux attribue la PR au mauvais agent, et il faudrait trancher avant de
            # facturer quoi que ce soit. Mesure du 2026-08-01 : 247 accords, 0 desaccord.
            if m["id"] == cited:
                agree += 1
            else:
                clash += 1
        # La BRANCHE prime : voie la plus couvrante. Le message la RELAIE quand le meta manque.
        pr["agent_id"] = m["id"] if m else (cited or "")
        pr["agent"] = m["name"] if m else (("agent %s" % cited[:8]) if cited else "")
        pr["via"] = "branche" if m else ("message" if cited else "")
        a = tok_agent.get(pr["agent_id"]) if pr["agent_id"] else None
        pr["agent_ctx"] = a["ctx"] if a else 0
        pr["agent_mins"] = ((a["last"] - a["first"]).total_seconds() / 60.0
                            if a and a.get("first") and a.get("last") else 0.0)
        pr["n_commits"] = 0
        pr["net_add"] = pr["net_del"] = 0
        joined += bool(pr["agent_id"])
        via_msg += pr["via"] == "message"

    # L'enumeration des commits de PR vient APRES la jointure d'agent : `--strict-agent` en depend.
    owner = pr_commits(prs, strict)
    git_day, git_net = load_git(since, set(owner))

    days = sorted({d for d in set(tok_day) | set(git_day) | {p["day"] for p in prs if p["day"]}
                   if d >= since})
    rows = []
    for d in days:
        g, t = git_day.get(d, {}), tok_day.get(d, {})
        opened = [p for p in prs if p["day"] == d]
        merged = [p for p in prs if p["merged_day"] == d]
        # Les colonnes sont portees par les PR MERGEES ce jour-la, au diff net de leur merge.
        # `commits` reste le compte des commits qu'elles ont fait entrer : c'est une INDICATION
        # de granularite, jamais le denominateur des lignes.
        ctx = t.get("ctx", 0)
        commits = sum(p["n_commits"] for p in merged)
        add = sum(p["net_add"] for p in merged)
        rows.append(dict(
            day=d, opened=len(opened), merged=len(merged),
            closed=len([p for p in opened if p["state"] == "CLOSED"]),
            commits=commits, add=add, dele=sum(p["net_del"] for p in merged),
            direct_commits=g.get("direct_commits", 0), direct_add=g.get("direct_add", 0),
            ctx=ctx, turns=t.get("turns", 0), agent_ctx=t.get("agent_ctx", 0),
            # Les deux ratios demandes. Denominateur nul -> 0, jamais une division qui explose ni
            # un « infini » qui polluerait les echelles de barres.
            ctx_per_pr=(ctx / len(merged)) if merged else 0,
            ctx_per_commit=(ctx / commits) if commits else 0,
            ctx_per_line=(ctx / add) if add else 0))
    return dict(days=rows, prs=prs, joined=joined, net=git_net, since=since, strict=strict,
                agents=tok_agent, project_dir=str(pdir), n_pr_commits=len(owner),
                via_msg=via_msg, agree=agree, clash=clash)


# ---------------------------------------------------------------- console
def n(x) -> str:
    return f"{int(x):,}".replace(",", " ")


def console(data: dict) -> None:
    hdr = "%-12s%9s%16s%10s%14s%12s%7s%7s%9s"
    print("unite = le MERGE d'une PR%s : lignes au diff net, rattachees au jour du merge."
          % (" (agent identifie)" if data["strict"] else ""))
    print("`direct` = commits pousses sur master hors PR.")
    print(hdr % ("jour", "commits", "context", "+lignes",
                 "ctx/commit", "ctx/ligne", "PR+", "PR ok", "direct"))
    tot = defaultdict(int)
    for r in data["days"]:
        for k in ("opened", "merged", "commits", "add", "dele", "ctx",
                  "direct_commits", "direct_add"):
            tot[k] += r[k]
        print(hdr % (r["day"], r["commits"], n(r["ctx"]), n(r["add"]),
                     n(r["ctx_per_commit"]) if r["commits"] else "-",
                     n(r["ctx_per_line"]) if r["add"] else "-",
                     r["opened"], r["merged"], r["direct_commits"] or "-"))
    print(hdr % ("TOTAL", tot["commits"], n(tot["ctx"]), n(tot["add"]),
                 n(tot["ctx"] / tot["commits"]) if tot["commits"] else "-",
                 n(tot["ctx"] / tot["add"]) if tot["add"] else "-",
                 tot["opened"], tot["merged"], tot["direct_commits"]))
    prs = data["prs"]
    merged = [p for p in prs if p["state"] == "MERGED"]
    ttm = sorted(p["ttm"] for p in merged if p["ttm"] is not None)
    print()
    print("PR            : %d ouvertes, %d mergees (%.0f%%), %d fermees sans merge"
          % (len(prs), len(merged), 100 * len(merged) / max(1, len(prs)),
             len(prs) - len(merged)))
    print("jointure agent: %d/%d (%.0f%%) -- dont %d par le message de merge seul"
          % (data["joined"], len(prs), 100 * data["joined"] / max(1, len(prs)),
             data["via_msg"]))
    print("  confrontation des deux voies : %d accords, %d desaccords%s"
          % (data["agree"], data["clash"], "" if not data["clash"] else "  <-- A TRANCHER"))
    tot_c = tot["commits"] + tot["direct_commits"]
    print("commits       : %d par PR (%.0f%%), %d pousses directement sur master"
          % (tot["commits"], 100 * tot["commits"] / max(1, tot_c), tot["direct_commits"]))
    print("lignes        : +%s par PR, +%s hors PR" % (n(tot["add"]), n(tot["direct_add"])))
    if ttm:
        print("latence merge : mediane %.0f min, p90 %.0f min"
              % (ttm[len(ttm) // 2], ttm[int(len(ttm) * 0.9)]))
    if data["net"].get("shortstat"):
        print("croissance nette de l'arbre depuis %s : %s" % (data["since"], data["net"]["shortstat"]))


# ---------------------------------------------------------------- rendu HTML
def esc(s) -> str:
    return html.escape(str(s), quote=True)


def render(data: dict) -> str:
    from repo_board_render import page          # noqa: E402  (rendu isole, cf. module)
    return page(data)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", default="2026-07-10", help="date de debut (defaut 2026-07-10)")
    ap.add_argument("-o", "--out", default=str(OUT))
    ap.add_argument("--open", action="store_true", help="ouvre la page dans le navigateur")
    ap.add_argument("--json", action="store_true", help="sortie machine")
    ap.add_argument("--strict-agent", action="store_true",
                    help="ne garder que les PR dont l'agent est identifie par sa branche")
    args = ap.parse_args()

    data = build(args.since, args.strict_agent)
    if args.json:
        def enc(o):
            return o.isoformat() if isinstance(o, datetime) else str(o)
        print(json.dumps(data, default=enc, ensure_ascii=False))
        return

    console(data)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print("\n-> %s" % out)
    if args.open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
