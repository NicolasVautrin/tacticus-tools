"""Carte des ALLER-RETOURS serveur des agents, et chiffrage d'une delegation.

Repond a : « une recurrence dans les aller-retours permettrait-elle d'y inserer un modele
moins pousse, et pour quel gain ? »

DEUX ETAPES, volontairement separees :

  --map     lit les transcripts des agents d'un perimetre (defaut : les PR qui touchent
            `scripts/python/engine/`) et PERSISTE une serie de tours par agent. C'est la
            seule etape qui lit du transcript -- 659 Mo pour 326 agents, ~4 min.
  --report  n'ouvre QUE la carte (2,5 Mo) : recurrence, ventilation, chiffrage.

⛔ UN ALLER-RETOUR N'EST PAS UN ENREGISTREMENT JSONL. Claude Code ecrit les blocs
`thinking` / `text` / `tool_use` d'une MEME reponse dans des enregistrements SEPARES qui
RECOPIENT le meme `usage`. Mesure sur 6 transcripts : 1 408 enregistrements pour 765
requetes, soit 1,84 -- et le `ctx` des continuations est IDENTIQUE, donc le sommer double
compte. La cle est `requestId`, jamais `uuid` ni le compte de lignes. Compter les
enregistrements gonfle ici les aller-retours de 1,72x (92 653 -> 53 706) et le contexte de
1,64x (29,0 G -> 17,7 G).

DECOMPOSITION EXACTE DU COUT, sans modele : ctx_k = prompt du tour k, N = nombre de tours,

    L = somme(ctx_k) = N * ctx_1  +  somme_{k>=2} delta_k * (N - k + 1)

Chaque ajout (sortie d'un tour + ses tool_results) est donc refacture autant de fois qu'il
reste d'aller-retours derriere lui. On attribue `delta_k` a la SIGNATURE d'outils du tour
qui l'a produit ; `N * ctx_1` est le socle isole.
"""
import argparse
import collections
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))
import repo_board as rb  # noqa: E402

DEFAULT_MAP = REPO / "logs" / "agent-roundtrips.json"
# Signatures dont le tour est un GESTE, pas une decision : executer une commande, appliquer
# une edition deja decidee. Ce sont les seules candidates a la delegation.
MECHANICAL = {"PowerShell", "Bash", "Edit", "Write", "PowerShell+Read", "Grep+PowerShell"}
# 98 % du prompt est du cache_read (x0.10), 2 % du cache_write (x1.25) -- mesure, pas hypothese.
WEIGHT = 0.98 * 0.10 + 0.02 * 1.25
PRICE = dict(opus=15.0, sonnet=3.0, haiku=1.0)   # $/M input, TARIF LISTE, INDICATIF


# ------------------------------------------------------------------ etape 1 : la carte
def touched_merges(since: str, prefix: str) -> set:
    """sha des merges dont le diff CONTRE LEUR PREMIER PARENT touche `prefix`. Un appel git."""
    out = rb.sh(["git", "log", "--first-parent", "--merges", "--since", since,
                 "--format=@%H", "--name-only"])
    cur, hits = None, set()
    for ln in out.splitlines():
        ln = ln.strip()
        if ln.startswith("@"):
            cur = ln[1:]
        elif ln.startswith(prefix) and cur:
            hits.add(cur)
    return hits


def walk(fp: Path):
    """[(ctx, out, sig, cw, cr, inp)] par REQUETE, dans l'ordre, + octets de tool_result."""
    order, seen, pend, res = [], {}, {}, collections.Counter()
    with fp.open("r", encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            if '"usage"' not in ln and '"tool_result"' not in ln:
                continue
            try:
                rec = json.loads(ln)
            except Exception:
                continue
            msg = rec.get("message") or {}
            content = msg.get("content") if isinstance(msg.get("content"), list) else []
            if rec.get("type") == "assistant" and msg.get("usage"):
                # `requestId` absent : on retombe sur l'uuid, qui isole le tour au pire en
                # le sur-comptant -- jamais en fusionnant deux requetes distinctes.
                rq = rec.get("requestId") or ("_u:%s" % rec.get("uuid"))
                u = msg["usage"]
                if rq not in seen:
                    seen[rq] = dict(
                        ctx=(int(u.get("input_tokens") or 0)
                             + int(u.get("cache_creation_input_tokens") or 0)
                             + int(u.get("cache_read_input_tokens") or 0)),
                        out=int(u.get("output_tokens") or 0),
                        cw=int(u.get("cache_creation_input_tokens") or 0),
                        cr=int(u.get("cache_read_input_tokens") or 0),
                        inp=int(u.get("input_tokens") or 0), names=set())
                    order.append(rq)
                else:
                    seen[rq]["out"] = max(seen[rq]["out"], int(u.get("output_tokens") or 0))
                for b in content:
                    if b.get("type") == "tool_use":
                        seen[rq]["names"].add(b.get("name"))
                        pend[b.get("id")] = b.get("name")
            else:
                for b in content:
                    if b.get("type") == "tool_result":
                        nm = pend.get(b.get("tool_use_id")) or "?"
                        c = b.get("content")
                        res[nm] += len(c if isinstance(c, str) else json.dumps(c))
    turns = []
    for rq in order:
        e = seen[rq]
        turns.append([e["ctx"], e["out"],
                      "+".join(sorted(e["names"])) if e["names"] else "(aucun outil)",
                      e["cw"], e["cr"], e["inp"]])
    return turns, res


def build_map(since: str, prefix: str, kind: str, out: Path) -> None:
    merges = touched_merges(since, prefix)
    pdir = rb.project_dir()
    cache = rb.load_cache(True)
    metas = rb.load_metas(pdir, cache)
    by_msg = rb.merge_msg_agents(rb.agents_on_disk(pdir))

    targets = []
    for p in rb.load_prs():
        if p["merge_sha"] not in merges:
            continue
        m = metas.get(p["branch"])
        aid = m["id"] if m else (by_msg.get(p["merge_sha"]) or "")
        if not aid:
            continue
        fp = next(pdir.glob("*/subagents/agent-%s.jsonl" % aid), None)
        if fp and (cache["metas"].get(aid) or {}).get("type") == kind:
            targets.append((p["num"], aid, fp))

    agents, resb, nb = [], collections.Counter(), 0
    for i, (num, aid, fp) in enumerate(targets):
        turns, res = walk(fp)
        resb.update(res)
        nb += fp.stat().st_size
        agents.append(dict(pr=num, agent=aid, turns=turns))
        if i % 50 == 0:
            print("  ... %d/%d" % (i, len(targets)), flush=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump(dict(schema="requestId", since=since, prefix=prefix, kind=kind,
                   agents=agents, resb=dict(resb)), out.open("w", encoding="utf-8"))
    nt = sum(len(a["turns"]) for a in agents)
    print("\n%d agents %s, %d aller-retours, %.0f Mo lus -> %s (%.1f Mo)"
          % (len(agents), kind, nt, nb / 1e6, out, out.stat().st_size / 1e6))


# ------------------------------------------------------------------ etape 2 : la lecture
def simulate(agents, meca, minrun, summary, sub_ctx):
    """Remplace chaque serie de >= `minrun` tours de meme signature mecanique par UN tour."""
    rt = ctx = subc = 0
    per = collections.Counter()
    for a in agents:
        T = a["turns"]
        N = len(T)
        k = 0
        while k < N:
            sig = T[k][2]
            j = k
            while j + 1 < N and T[j + 1][2] == sig:
                j += 1
            R = j - k + 1
            if R >= minrun and sig in meca:
                # les aller-retours retires, PLUS ce que le bloc n'ajoute plus au prefixe
                # de tous les tours suivants (le parent ne recoit que `summary`).
                s = sum(T[m][0] for m in range(k + 1, j + 1))
                if j + 1 < N:
                    s += max(0, T[j + 1][0] - T[k][0] - summary) * (N - j - 1)
                rt += R - 1
                ctx += s
                per[sig] += s
                subc += R * sub_ctx
            k = j + 1
    return rt, ctx, subc, per


def report(mp: Path, sub_ctx: int, minrun: int, summary: int) -> None:
    d = json.loads(mp.read_text(encoding="utf-8"))
    AG = d["agents"]
    carry, hits, runs = collections.Counter(), collections.Counter(), collections.Counter()
    L = OUT = CW = CR = INP = NT = socle = 0
    for a in AG:
        T = a["turns"]
        N = len(T)
        if N < 2:
            continue
        NT += N
        L += sum(t[0] for t in T)
        OUT += sum(t[1] for t in T)
        CW += sum(t[3] for t in T)
        CR += sum(t[4] for t in T)
        INP += sum(t[5] for t in T)
        socle += T[0][0] * N
        cur, ln = None, 0
        for k, t in enumerate(T):
            hits[t[2]] += 1
            if k:
                dlt = t[0] - T[k - 1][0]
                if dlt > 0:
                    carry[T[k - 1][2]] += dlt * (N - k)
            if t[2] == cur:
                ln += 1
            else:
                if cur is not None and ln >= minrun:
                    runs[cur] += ln
                cur, ln = t[2], 1
        if ln >= minrun:
            runs[cur] += ln

    print("=== %d agents / %d ALLER-RETOURS / %.1f G de contexte relu"
          % (len(AG), NT, L / 1e9))
    print("    %.0f aller-retours par agent, %s tokens de prompt par aller-retour"
          % (NT / len(AG), format(L // NT, ",d")))
    print("    cache_read %.0f%% | cache_write %.0f%% | socle relu N fois %.0f%%"
          % (100 * CR / L, 100 * CW / L, 100 * socle / L))
    print("    equivalents-input ponderes %.2f G | output %.0f M"
          % ((INP + 1.25 * CW + 0.10 * CR) / 1e9, OUT / 1e6))

    print("\n%-34s %7s %6s %9s %6s %8s"
          % ("signature", "tours", "part", "carry G", "part", "en serie"))
    for sig, n in sorted(hits.items(), key=lambda kv: -kv[1])[:12]:
        print("%-34s %7d %5.1f%% %9.2f %5.1f%% %8d"
              % (sig[:34], n, 100 * n / NT, carry[sig] / 1e9, 100 * carry[sig] / L,
                 runs.get(sig, 0)))

    base = L * WEIGHT * PRICE["opus"] / 1e6
    rt, ctx, subc, per = simulate(AG, MECHANICAL, minrun, summary, sub_ctx)
    print("\n=== DELEGATION DES BOUCLES (serie >= %d, resume rendu %d tokens,"
          " sous-agent mesure a %s/requete)" % (minrun, summary, format(sub_ctx, ",d")))
    print("    %d aller-retours retires du parent (%.0f%%), %.2f G de contexte Opus evite"
          " (%.0f%%)" % (rt, 100 * rt / NT, ctx / 1e9, 100 * ctx / L))
    print("    %-42s %9.0f $" % ("aujourd'hui, tout en Opus", base))
    for m in ("opus", "sonnet", "haiku"):
        v = ((L - ctx) * WEIGHT * PRICE["opus"] + subc * WEIGHT * PRICE[m]) / 1e6
        tag = "   <- TEMOIN : isolement SEUL" if m == "opus" else ""
        print("    %-42s %9.0f $   -%2.0f%%%s"
              % ("sous-agent " + m, v, 100 * (base - v) / base, tag))
    print("    prix LISTE, INDICATIFS -- hors forfait/remise. Le rang compte, pas l'absolu.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", action="store_true", help="(re)construire la carte -- LIT les transcripts")
    ap.add_argument("--report", action="store_true", help="lire la carte seule")
    ap.add_argument("--out", type=Path, default=DEFAULT_MAP)
    ap.add_argument("--since", default="2026-07-26")
    ap.add_argument("--prefix", default="scripts/python/engine/")
    ap.add_argument("--kind", default="opus-solver")
    ap.add_argument("--sub-ctx", type=int, default=95507,
                    help="ctx/requete d'un sous-agent (defaut : mesure des Explore du depot)")
    ap.add_argument("--min-run", type=int, default=3)
    ap.add_argument("--summary", type=int, default=1500)
    a = ap.parse_args()
    if a.map:
        build_map(a.since, a.prefix, a.kind, a.out)
    if a.report or not a.map:
        if not a.out.exists():
            raise SystemExit("carte absente : %s -- lancer --map d'abord" % a.out)
        report(a.out, a.sub_ctx, a.min_run, a.summary)


if __name__ == "__main__":
    main()
