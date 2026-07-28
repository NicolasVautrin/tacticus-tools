"""Board « sante du depot » : croisement PULL REQUESTS x TRANSCRIPTS x GIT, par jour.

Pendant de `fleet_board.py`, qui montre la flotte MAINTENANT. Celui-ci montre ce que la flotte a
PRODUIT, dans la duree : combien de PR, a quel cout en tokens, pour combien de lignes retenues.

TROIS SOURCES INDEPENDANTES, jointes sur la date locale :

  1. GitHub -- `gh pr list --state all`. Etat, dates, additions/deletions, branche.
  2. Transcripts Claude Code -- `~/.claude/projects/<slug>/*.jsonl` (boucle principale) et
     `*/subagents/agent-*.jsonl` (agents). Tokens par jour, dedupes par uuid.
  3. Git -- `git log --numstat`. Commits et lignes par jour.

LA JOINTURE PR <-> AGENT passe par la BRANCHE : `worktreeBranch` du meta d'agent == `headRefName`
de la PR. Mesure du 2026-07-28 : 157/191 PR (82 %). Les 34 autres portent une branche qui n'est PAS
celle du worktree (`agent/192-...`, `case-n8b-...`) -- elles sont COMPTEES a part, jamais perdues :
une PR sans agent identifie reste une PR.

CE QUE LES CHIFFRES NE DISENT PAS, et qu'il ne faut pas leur faire dire :

  - Les tokens d'un jour couvrent TOUTE l'activite du projet (RE, audits, conversation), pas
    seulement ce qui a fini en PR. Un `tokens / PR` est donc un indicateur de TENDANCE entre
    periodes, jamais un cout unitaire de production.
  - Les lignes de `git log --numstat` incluent le CHURN de scission de modules : un fichier eclate
    compte N ajouts + N suppressions pour zero code neuf. La croissance NETTE de l'arbre
    (`git diff base..HEAD`) est la mesure honnete, et elle est calculee a part.
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
import subprocess
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# Le NOM DU FICHIER est l'identite de l'artefact publie : republier le meme chemin conserve
# l'URL, un chemin different en cree une neuve. Ne pas le renommer sans republier derriere.
OUT = REPO / "logs" / "repo-registry.html"

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
              "changedFiles,headRefName"])
    if not raw.strip():
        raise SystemExit("gh n'a rien rendu -- `gh auth status` ?")
    out = []
    for p in json.loads(raw):
        created, merged = _ts(p["createdAt"]), _ts(p.get("mergedAt"))
        out.append(dict(
            num=p["number"], title=p["title"], state=p["state"], branch=p["headRefName"],
            created=created, merged=merged,
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
def load_git(since: str) -> tuple[dict, dict]:
    raw = sh(["git", "log", "--pretty=format:C|%H|%aI", "--numstat",
              "--since", since, "--", ".", EXCLUDE])
    by_day = defaultdict(lambda: defaultdict(int))
    day = None
    for ln in raw.splitlines():
        if ln.startswith("C|"):
            _, _sha, iso = ln.split("|", 2)
            day = _ts(iso).astimezone().strftime("%Y-%m-%d")
            by_day[day]["commits"] += 1
            continue
        parts = ln.split("\t")
        if len(parts) != 3 or day is None or parts[0] == "-":
            continue
        by_day[day]["add"] += int(parts[0])
        by_day[day]["del"] += int(parts[1])
    # croissance NETTE de l'arbre sur la fenetre -- annule le churn de scission de modules
    base = sh(["git", "rev-list", "-1", "--before", "%s 00:00" % since, "HEAD"]).strip()
    net = {}
    if base:
        stat = sh(["git", "diff", "--shortstat", base, "HEAD", "--", ".", EXCLUDE]).strip()
        net["shortstat"] = stat
    return by_day, net


# ---------------------------------------------------------------- assemblage
def build(since: str) -> dict:
    pdir = project_dir()
    prs = load_prs()
    tok_day, tok_agent = load_tokens(pdir)
    metas = load_metas(pdir)
    git_day, git_net = load_git(since)

    joined = 0
    for pr in prs:
        m = metas.get(pr["branch"])
        pr["agent"] = m["name"] if m else ""
        pr["agent_id"] = m["id"] if m else ""
        a = tok_agent.get(pr["agent_id"]) if pr["agent_id"] else None
        pr["agent_ctx"] = a["ctx"] if a else 0
        pr["agent_mins"] = ((a["last"] - a["first"]).total_seconds() / 60.0
                            if a and a.get("first") and a.get("last") else 0.0)
        if m:
            joined += 1

    days = sorted({d for d in set(tok_day) | set(git_day) | {p["day"] for p in prs if p["day"]}
                   if d >= since})
    rows = []
    for d in days:
        g, t = git_day.get(d, {}), tok_day.get(d, {})
        opened = [p for p in prs if p["day"] == d]
        merged = [p for p in prs if p["merged_day"] == d]
        ctx, commits, add = t.get("ctx", 0), g.get("commits", 0), g.get("add", 0)
        rows.append(dict(
            day=d, opened=len(opened), merged=len(merged),
            closed=len([p for p in opened if p["state"] == "CLOSED"]),
            commits=commits, add=add, dele=g.get("del", 0),
            ctx=ctx, turns=t.get("turns", 0), agent_ctx=t.get("agent_ctx", 0),
            pr_add=sum(p["add"] for p in merged),
            # Les deux ratios demandes. Denominateur nul -> 0, jamais une division qui explose ni
            # un « infini » qui polluerait les echelles de barres.
            ctx_per_commit=(ctx / commits) if commits else 0,
            ctx_per_line=(ctx / add) if add else 0))
    return dict(days=rows, prs=prs, joined=joined, net=git_net, since=since,
                agents=tok_agent, project_dir=str(pdir))


# ---------------------------------------------------------------- console
def n(x) -> str:
    return f"{int(x):,}".replace(",", " ")


def console(data: dict) -> None:
    hdr = "%-12s%9s%16s%10s%14s%12s%7s%7s"
    print(hdr % ("jour", "commits", "context", "+lignes",
                 "ctx/commit", "ctx/ligne", "PR+", "PR ok"))
    tot = defaultdict(int)
    for r in data["days"]:
        for k in ("opened", "merged", "commits", "add", "dele", "ctx"):
            tot[k] += r[k]
        print(hdr % (r["day"], r["commits"], n(r["ctx"]), n(r["add"]),
                     n(r["ctx_per_commit"]) if r["commits"] else "-",
                     n(r["ctx_per_line"]) if r["add"] else "-",
                     r["opened"], r["merged"]))
    print(hdr % ("TOTAL", tot["commits"], n(tot["ctx"]), n(tot["add"]),
                 n(tot["ctx"] / tot["commits"]) if tot["commits"] else "-",
                 n(tot["ctx"] / tot["add"]) if tot["add"] else "-",
                 tot["opened"], tot["merged"]))
    prs = data["prs"]
    merged = [p for p in prs if p["state"] == "MERGED"]
    ttm = sorted(p["ttm"] for p in merged if p["ttm"] is not None)
    print()
    print("PR            : %d ouvertes, %d mergees (%.0f%%), %d fermees sans merge"
          % (len(prs), len(merged), 100 * len(merged) / max(1, len(prs)),
             len(prs) - len(merged)))
    print("jointure agent: %d/%d (%.0f%%) -- les autres portent une branche hors worktree"
          % (data["joined"], len(prs), 100 * data["joined"] / max(1, len(prs))))
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
    args = ap.parse_args()

    data = build(args.since)
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
