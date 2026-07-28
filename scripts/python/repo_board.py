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
OUT = REPO / "logs" / "repo-board.html"

# Artefact genere, versionne expres, mais ce n'est pas du code ecrit -- cf. docstring.
EXCLUDE = ":(exclude)data/symbols"


def sh(args: list[str], cwd: Path = REPO) -> str:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


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
def _cost(u) -> tuple[int, int]:
    """Rend (output, cost-weighted). Ponderation billing : cw*1.25 + cr*0.10 (cf. session-tokens)."""
    o = int(u.get("output_tokens") or 0)
    i = int(u.get("input_tokens") or 0)
    cw = int(u.get("cache_creation_input_tokens") or 0)
    cr = int(u.get("cache_read_input_tokens") or 0)
    return o, int(i + cw * 1.25 + cr * 0.10 + o)


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
                out, cost = _cost(u)
                day = t.astimezone().strftime("%Y-%m-%d")
                by_day[day]["out"] += out
                by_day[day]["cost"] += cost
                by_day[day]["turns"] += 1
                if aid:
                    by_day[day]["agent_out"] += out
                    a = by_agent[aid]
                    a["out"] += out
                    a["cost"] += cost
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
        pr["agent_out"] = a["out"] if a else 0
        pr["agent_cost"] = a["cost"] if a else 0
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
        rows.append(dict(
            day=d, opened=len(opened), merged=len(merged),
            closed=len([p for p in opened if p["state"] == "CLOSED"]),
            commits=g.get("commits", 0), add=g.get("add", 0), dele=g.get("del", 0),
            out=t.get("out", 0), cost=t.get("cost", 0), turns=t.get("turns", 0),
            agent_out=t.get("agent_out", 0),
            pr_add=sum(p["add"] for p in merged),
            cost_per_pr=(t.get("cost", 0) / len(merged)) if merged else 0))
    return dict(days=rows, prs=prs, joined=joined, net=git_net, since=since,
                agents=tok_agent, project_dir=str(pdir))


# ---------------------------------------------------------------- console
def n(x) -> str:
    return f"{int(x):,}".replace(",", " ")


def console(data: dict) -> None:
    print("%-12s%7s%7s%9s%10s%10s%13s%12s" % (
        "jour", "PR+", "PR ok", "commits", "+lignes", "-lignes", "cost-w tok", "tok/PR"))
    tot = defaultdict(int)
    for r in data["days"]:
        for k in ("opened", "merged", "commits", "add", "dele", "out", "cost"):
            tot[k] += r[k]
        print("%-12s%7d%7d%9d%10d%10d%13s%12s" % (
            r["day"], r["opened"], r["merged"], r["commits"], r["add"], r["dele"],
            n(r["cost"]), n(r["cost_per_pr"]) if r["merged"] else "-"))
    print("%-12s%7d%7d%9d%10d%10d%13s%12s" % (
        "TOTAL", tot["opened"], tot["merged"], tot["commits"], tot["add"], tot["dele"],
        n(tot["cost"]), n(tot["cost"] / tot["merged"]) if tot["merged"] else "-"))
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
