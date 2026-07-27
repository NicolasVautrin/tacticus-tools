"""Telemetrie CONTEXTE de la flotte d'agents -- table console + page HTML rechargeable.

    python scripts/python/fleet_board.py            # table console + ecrit logs/fleet-board.html
    python scripts/python/fleet_board.py --open     # ... et l'ouvre dans le navigateur
    python scripts/python/fleet_board.py --all      # inclut les agents TERMINES

Boucle de rafraichissement : relancer la commande, puis recharger l'onglet (le bouton de la page
fait `location.reload()`). C'est le SEUL vrai refresh possible -- un artefact publie sur claude.ai
est sandboxe et ne peut pas relire ces transcripts, qui vivent sur le disque local.

CE QU'ON MESURE, et pourquoi ce n'est PAS la somme des tokens :
  - Le bloc `usage` d'un message assistant decrit UNE requete. La taille de son PROMPT est
    `input + cache_creation + cache_read` -- c'est-a-dire l'occupation de la fenetre a cet instant.
    Sommer toutes les requetes compte N fois le meme contexte relu : ca mesure la FACTURE, pas le
    REMPLISSAGE. Ecart constate : 417 M factures pour des fenetres qui plafonnent vers 500 K.
  - BASE SYSTEME = la taille de prompt de la PREMIERE requete : prompt systeme + definitions
    d'outils + CLAUDE.md + le brief. Socle constant (~55 K, mesure 53,7-56,2 K), aucun travail.
  - VITESSE = (contexte courant - base systeme) / minutes. Retrancher le socle est indispensable :
    sans ca, un agent lance il y a 2 minutes affiche une vitesse enorme alors qu'il n'a rien lu.

Sortie console ASCII (cp1252) ; le HTML est ecrit en utf-8.
"""
from __future__ import annotations

import argparse
import html
import json
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

WINDOW = 1_000_000                    # fenetre du modele (opus 1M)
REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "logs" / "fleet-board.html"


# ---------------------------------------------------------------- decouverte des transcripts
def project_dir() -> Path:
    """`~/.claude/projects/<slug>` ou <slug> = le chemin du repo, ':' et separateurs -> '-'."""
    root = Path.home() / ".claude" / "projects"
    slug = str(REPO).replace(":", "-").replace("\\", "-").replace("/", "-")
    cand = root / slug
    if cand.is_dir():
        return cand
    # Repli : le slug encode le chemin, donc un repo deplace ne matche plus -- on retient le
    # repertoire de projet qui porte le plus de transcripts d'agents.
    best = max(root.glob("*"), key=lambda p: len(list(p.glob("*/subagents/agent-*.jsonl"))),
               default=None)
    if best is None:
        raise SystemExit("aucun repertoire de projet Claude trouve sous %s" % root)
    return best


# ---------------------------------------------------------------- lecture d'un transcript
def _ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _prompt_size(u) -> int:
    return (int(u.get("input_tokens") or 0)
            + int(u.get("cache_creation_input_tokens") or 0)
            + int(u.get("cache_read_input_tokens") or 0))


def scan(path: Path) -> dict:
    first = last = None
    first_ts = last_ts = None
    says: list[str] = []
    tools = 0
    for ln in path.open(encoding="utf-8", errors="replace"):
        if '"usage"' not in ln and '"tool_use"' not in ln:
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            continue                       # ligne tronquee (transcript en cours d'ecriture)
        msg = rec.get("message") or {}
        if msg.get("role") != "assistant":
            continue
        for blk in (msg.get("content") or []):
            if not isinstance(blk, dict):
                continue
            if blk.get("type") == "tool_use":
                tools += 1
            elif blk.get("type") == "text" and blk.get("text", "").strip():
                says.append(blk["text"].strip())
        u = msg.get("usage")
        if not u:
            continue
        sz = _prompt_size(u)
        if sz <= 0:
            continue
        t = _ts(rec.get("timestamp"))
        if first is None:
            first, first_ts = sz, t
        last, last_ts = sz, t or last_ts
    return dict(first=first, last=last, first_ts=first_ts, last_ts=last_ts,
                says=says, tools=tools)


def locked_worktrees() -> set[str]:
    """Worktrees VERROUILLES = agents qui tournent encore.

    Le simple fait que le repertoire existe ne suffit pas : un agent TERMINE garde son worktree
    jusqu'au nettoyage (typiquement un sous-agent lance par un autre agent). Le harnais pose un
    `git worktree lock` pour la duree du vol -- c'est le seul signal qui separe « en vol » de
    « fini, pas encore nettoye ». Repli sur l'existence du repertoire si git n'est pas joignable."""
    try:
        out = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=str(REPO),
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return set()
    locked, cur = set(), None
    for ln in out.splitlines():
        if ln.startswith("worktree "):
            cur = str(Path(ln[9:].strip()).resolve()).lower()
        elif ln.startswith("locked") and cur:
            locked.add(cur)
    return locked


def collect(include_done: bool) -> list[dict]:
    locked = locked_worktrees()
    rows = []
    for p in sorted(project_dir().glob("*/subagents/agent-*.jsonl")):
        aid = p.stem.replace("agent-", "")
        meta_p = p.with_name("agent-%s.meta.json" % aid)
        meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
        s = scan(p)
        if not s["first"]:
            continue
        # VIF = worktree VERROUILLE (cf. locked_worktrees). Piege : `Path("")` vaut `Path(".")`,
        # qui existe TOUJOURS -- sans le test de chaine non-vide, tout agent lance sans worktree
        # passe pour vif (mesure : 193 « en vol » au lieu de 11).
        wtp = (meta.get("worktreePath") or "").strip()
        alive = bool(wtp) and Path(wtp).exists()
        if alive and locked:                       # signal fin, seulement si git a repondu
            alive = str(Path(wtp).resolve()).lower() in locked
        if not alive and not include_done:
            continue
        mins = ((s["last_ts"] - s["first_ts"]).total_seconds() / 60.0
                if s["first_ts"] and s["last_ts"] else 0.0)
        work = max(0, s["last"] - s["first"])
        rows.append(dict(
            id=aid, name=meta.get("description") or aid, alive=alive,
            base=s["first"], ctx=s["last"], work=work, mins=mins,
            # < 30 s : le denominateur est trop petit pour que le quotient veuille dire quelque
            # chose (un seul aller-retour d'outil ferait 100 000 tok/min).
            rate=(work / mins) if mins > 0.5 else 0.0,
            pct=100.0 * s["last"] / WINDOW, tools=s["tools"], says=s["says"][-2:]))
    rows.sort(key=lambda r: (-r["alive"], -r["ctx"]))
    return rows


# ---------------------------------------------------------------- rendu
def hm(mins) -> str:
    m = int(round(mins))
    return "%dh%02d" % (m // 60, m % 60) if m >= 60 else "%d min" % m


def eta(r):
    """Minutes avant saturation de la fenetre, au rythme courant."""
    return None if r["rate"] <= 0 else (WINDOW - r["ctx"]) / r["rate"]


def console(rows) -> None:
    print("%-34s %-4s %9s %9s %9s %7s %9s %6s %8s"
          % ("agent", "vif", "contexte", "base sys", "travail", "min", "tok/min", "%fen", "sature"))
    for r in rows:
        e = eta(r)
        print("%-34s %-4s %9d %9d %9d %7.0f %9.0f %6.1f %8s"
              % (r["name"][:34], "oui" if r["alive"] else "-", r["ctx"], r["base"], r["work"],
                 r["mins"], r["rate"], r["pct"], "--" if e is None else hm(e)))


TPL = """<title>Flotte d'agents — occupation de contexte</title>
<style>
  :root {
    color-scheme: light dark;
    --ground:#f7f8fa; --panel:#ffffff; --ink:#161c24; --muted:#687484; --line:#dfe4ec;
    --accent:#5b57c9; --ok:#3f8f5e; --warn:#c1841f; --crit:#c0453a; --track:#e8ecf3;
    --mono: ui-monospace, "Cascadia Mono", "SF Mono", Consolas, monospace;
    --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
    --sans: "Inter Tight", "Segoe UI Variable Display", "Segoe UI", system-ui, sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root { --ground:#0d1015; --panel:#141922; --ink:#e6ecf4; --muted:#8592a3; --line:#232c39;
            --accent:#8f8bf0; --ok:#5cb37c; --warn:#dfa440; --crit:#e0665a; --track:#1d2531; }
  }
  :root[data-theme="dark"] {
    --ground:#0d1015; --panel:#141922; --ink:#e6ecf4; --muted:#8592a3; --line:#232c39;
    --accent:#8f8bf0; --ok:#5cb37c; --warn:#dfa440; --crit:#e0665a; --track:#1d2531;
  }
  :root[data-theme="light"] {
    --ground:#f7f8fa; --panel:#ffffff; --ink:#161c24; --muted:#687484; --line:#dfe4ec;
    --accent:#5b57c9; --ok:#3f8f5e; --warn:#c1841f; --crit:#c0453a; --track:#e8ecf3;
  }
  body { margin:0; background:var(--ground); color:var(--ink); font-family:var(--sans);
         line-height:1.5; -webkit-font-smoothing:antialiased; }
  .wrap { max-width:1080px; margin:0 auto; padding:clamp(20px,4vw,52px) clamp(16px,3vw,32px) 72px; }
  header { border-bottom:2px solid var(--ink); padding-bottom:18px; }
  .eyebrow { font-family:var(--mono); font-size:11px; letter-spacing:.16em; text-transform:uppercase;
             color:var(--accent); margin:0 0 10px; }
  h1 { font-size:clamp(26px,4.2vw,40px); line-height:1.08; margin:0 0 10px; letter-spacing:-.02em;
       text-wrap:balance; font-weight:640; }
  .lede { margin:0; color:var(--muted); max-width:62ch; font-size:15px; }
  .tools { display:flex; align-items:center; justify-content:space-between; gap:14px;
           flex-wrap:wrap; margin-top:18px; }
  .stamp { font-family:var(--mono); font-size:11.5px; color:var(--muted);
           font-variant-numeric:tabular-nums; }
  .age { color:var(--ink); opacity:.8; }
  .age[data-stale="1"] { color:var(--warn); opacity:1; }
  #reload { font-family:var(--mono); font-size:12.5px; color:var(--ink); background:var(--panel);
            border:1px solid var(--line); border-radius:3px; padding:6px 13px; cursor:pointer;
            display:inline-flex; align-items:center; gap:8px;
            transition:border-color .15s, color .15s; }
  #reload:hover { border-color:var(--accent); color:var(--accent); }
  #reload:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  #reload .glyph { font-size:14px; line-height:1; display:inline-block; }
  #reload[data-busy="1"] .glyph { animation:spin .8s linear infinite; }
  @keyframes spin { to { transform:rotate(360deg); } }
  @media (prefers-reduced-motion:reduce) { #reload[data-busy="1"] .glyph { animation:none; } }
  .summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(158px,1fr)); gap:1px;
             background:var(--line); border:1px solid var(--line); margin:26px 0 30px; }
  .cell { background:var(--panel); padding:14px 16px; }
  .cell dt { font-family:var(--mono); font-size:10.5px; letter-spacing:.11em; text-transform:uppercase;
             color:var(--muted); margin:0 0 6px; }
  .cell dd { margin:0; font-family:var(--mono); font-size:21px; font-variant-numeric:tabular-nums; }
  .cell dd small { display:block; font-size:11.5px; color:var(--muted); letter-spacing:0;
                   font-family:var(--sans); margin-top:3px; }
  .legend { display:flex; gap:22px; flex-wrap:wrap; font-family:var(--mono); font-size:11px;
            color:var(--muted); margin:0 0 26px; }
  .swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px;
            vertical-align:-1px; }
  .gauge { border-top:1px solid var(--line); padding:16px 0 18px; }
  .gauge:last-of-type { border-bottom:1px solid var(--line); }
  .grow { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin-bottom:9px; }
  .gname { font-weight:600; font-size:15.5px; letter-spacing:-.01em; flex:1 1 240px; min-width:0; }
  .figs { display:flex; gap:18px; flex-wrap:wrap; font-family:var(--mono); font-size:12.5px;
          font-variant-numeric:tabular-nums; color:var(--muted); }
  .figs b { color:var(--ink); font-weight:600; }
  .bar { position:relative; height:11px; background:var(--track); border-radius:2px;
         overflow:hidden; display:flex; }
  .seg-base { background:var(--accent); opacity:.34; }
  .seg-work { background:var(--fill); }
  .gauge[data-band="ok"]   { --fill:var(--ok); }
  .gauge[data-band="warn"] { --fill:var(--warn); }
  .gauge[data-band="crit"] { --fill:var(--crit); }
  .pct { position:absolute; right:6px; top:-1px; font-family:var(--mono); font-size:9.5px;
         line-height:13px; color:var(--ink); opacity:.62; font-variant-numeric:tabular-nums; }
  .says { margin:11px 0 0; padding:0; list-style:none; font-family:var(--serif); font-size:14px; }
  .says li { position:relative; padding-left:17px; margin-top:6px; opacity:.9; }
  .says li::before { content:""; position:absolute; left:0; top:.62em; width:8px; height:1px;
                     background:var(--muted); }
  .says li:first-child { opacity:.58; }
  .note { margin-top:40px; padding:18px 20px; border-left:3px solid var(--accent);
          background:var(--panel); font-size:14.5px; }
  .note h2 { margin:0 0 8px; font-size:13px; font-family:var(--mono); letter-spacing:.09em;
             text-transform:uppercase; color:var(--accent); font-weight:600; }
  .note p { margin:0 0 9px; max-width:70ch; }
  .note p:last-child { margin-bottom:0; }
  code { font-family:var(--mono); font-size:.9em; background:var(--track); padding:1px 5px;
         border-radius:3px; }
</style>

<div class="wrap">
  <header>
    <p class="eyebrow">tacticus-tools · campagne de portage</p>
    <h1>Ce que la flotte a mis dans sa fenêtre</h1>
    <p class="lede">__N__ agents en vol, chacun avec sa propre fenêtre d'un million de tokens.
    La jauge mesure ce qu'elle contient <em>maintenant</em> — pas ce qu'elle a coûté.</p>
    <div class="tools">
      <span class="stamp">Instantané du <time datetime="__ISO__">__STAMP__</time><span class="age" id="age"></span></span>
      <button type="button" id="reload"><span class="glyph" aria-hidden="true">⟳</span> Recharger</button>
    </div>
  </header>

  <dl class="summary">
    <div class="cell"><dt>en vol</dt><dd>__N__<small>agents isolés</small></dd></div>
    <div class="cell"><dt>remplissage médian</dt><dd>__MED__ %<small>de 1 M</small></dd></div>
    <div class="cell"><dt>le plus rapide</dt><dd>__FRATE__<small>__FNAME__ · tok/min</small></dd></div>
    <div class="cell"><dt>saturation la plus proche</dt><dd>__ETA__<small>__ENAME__</small></dd></div>
  </dl>

  <div class="legend">
    <span><span class="swatch" style="background:var(--accent);opacity:.34"></span>socle système (prompt + outils + brief)</span>
    <span><span class="swatch" style="background:var(--ok)"></span>&lt; 40 %</span>
    <span><span class="swatch" style="background:var(--warn)"></span>40–60 %</span>
    <span><span class="swatch" style="background:var(--crit)"></span>&gt; 60 %</span>
  </div>

  <div id="fleet"></div>

  <div class="note">
    <h2>Pourquoi la vitesse exclut le socle</h2>
    <p>Chaque agent démarre avec <strong>~55 000 tokens</strong> déjà en fenêtre : prompt système,
    définitions d'outils, <code>CLAUDE.md</code> et son brief. C'est un socle constant qui ne
    représente aucun travail accompli. Rapporter la fenêtre entière au temps écoulé donnerait une
    vitesse énorme à un agent lancé il y a deux minutes, et masquerait qu'il n'a encore rien lu.</p>
    <p>La vitesse affichée est donc <code>(contexte − socle) ÷ minutes</code> : elle ne compte que
    ce que l'agent a effectivement accumulé — fichiers lus, sorties d'outils, son propre
    raisonnement. C'est aussi elle qui donne l'échéance de saturation, la seule qui dise quel agent
    doit atterrir en premier.</p>
    <p>À ne pas confondre avec le total de tokens facturés, qui compte <em>N fois</em> le même
    contexte relu à chaque requête : il mesure la dépense, pas le remplissage.</p>
    <p><strong>Rafraîchir :</strong> relancer <code>python scripts/python/fleet_board.py</code>,
    puis recharger. Le bouton ne fait que recharger la page — il ne peut pas recalculer, les
    transcripts sont des fichiers locaux.</p>
  </div>
</div>

<script>
const ROWS = __PAYLOAD__, STAMP = new Date("__ISO__");
const fmt = n => n.toLocaleString('fr-FR').replace(/\\u202f|\\u00a0/g, ' ');
document.getElementById('fleet').innerHTML = ROWS.map(r => `
  <div class="gauge" data-band="${r.band}">
    <div class="grow">
      <div class="gname">${r.name}</div>
      <div class="figs">
        <span><b>${fmt(r.ctx)}</b> ctx</span>
        <span><b>${fmt(r.rate)}</b> tok/min</span>
        <span>${r.minsLabel} de vol</span>
        <span>saturation&nbsp;<b>${r.etaLabel}</b></span>
      </div>
    </div>
    <div class="bar">
      <div class="seg-base" style="width:${r.basePct}%"></div>
      <div class="seg-work" style="width:${r.workPct}%"></div>
      <span class="pct">${r.pct} %</span>
    </div>
    ${r.says.length ? `<ul class="says">${r.says.map(s => `<li>${s}</li>`).join('')}</ul>` : ''}
  </div>`).join('');

// L'age vieillit tout seul : c'est lui qui dit si recharger sert a quelque chose. Au-dela de
// 5 min, il passe en ambre -- un chiffre fige sans age visible se lit a tort comme du temps reel.
const ageEl = document.getElementById('age');
const tick = () => {
  const m = Math.max(0, Math.round((Date.now() - STAMP.getTime()) / 60000));
  ageEl.textContent = m < 1 ? ' · a l\\u2019instant'
    : ' · il y a ' + (m < 60 ? m + ' min' : Math.floor(m / 60) + 'h' + String(m % 60).padStart(2, '0'));
  ageEl.dataset.stale = m >= 5 ? '1' : '0';
};
tick(); setInterval(tick, 20000);

const btn = document.getElementById('reload');
btn.addEventListener('click', () => { btn.dataset.busy = '1'; location.reload(); });
</script>
"""


def render(rows) -> str:
    now = datetime.now().astimezone()
    cards = []
    for r in rows:
        e = eta(r)
        cards.append({
            "name": html.escape(r["name"]), "ctx": r["ctx"],
            "pct": round(r["pct"], 1),
            "basePct": round(100.0 * r["base"] / WINDOW, 2),
            "workPct": round(100.0 * r["work"] / WINDOW, 2),
            "rate": int(round(r["rate"])), "minsLabel": hm(r["mins"]),
            "etaLabel": "--" if e is None else hm(e),
            "band": "crit" if r["pct"] >= 60 else ("warn" if r["pct"] >= 40 else "ok"),
            "says": [html.escape(s.replace("\n", " ").strip())[:320] for s in (r["says"] or [])],
        })
    fastest = max(cards, key=lambda c: c["rate"]) if cards else None
    withe = [(c, r) for c, r in zip(cards, rows) if eta(r) is not None]
    nearest = min(withe, key=lambda cr: eta(cr[1]))[0] if withe else None
    med = sorted(c["pct"] for c in cards)[len(cards) // 2] if cards else 0.0
    return (TPL
            .replace("__PAYLOAD__", json.dumps(cards, ensure_ascii=False))
            .replace("__ISO__", now.isoformat())
            .replace("__STAMP__", now.strftime("%d/%m a %H:%M"))
            .replace("__N__", str(len(cards)))
            .replace("__MED__", ("%.1f" % med).replace(".", ","))
            .replace("__FRATE__", "{:,}".format(fastest["rate"]).replace(",", " ") if fastest else "--")
            .replace("__FNAME__", fastest["name"] if fastest else "--")
            .replace("__ETA__", nearest["etaLabel"] if nearest else "--")
            .replace("__ENAME__", nearest["name"] if nearest else "--"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--open", action="store_true", help="ouvrir la page dans le navigateur")
    ap.add_argument("--all", action="store_true", help="inclure les agents TERMINES")
    ap.add_argument("-o", "--out", default=str(OUT), help="chemin du HTML (defaut : logs/)")
    a = ap.parse_args()

    rows = collect(include_done=a.all)
    if not rows:
        raise SystemExit("aucun agent %s trouve" % ("" if a.all else "EN VOL"))
    console(rows)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(rows), encoding="utf-8")
    alive = sum(1 for r in rows if r["alive"])
    # URI `file:///` ENTRE PARENTHESES : c'est la seule forme cliquable dans Claude Code, et elle
    # evite d'avoir a recopier un chemin Windows a la main pour ouvrir la page.
    uri = out.resolve().as_uri()
    print("\n%d agents (%d en vol) -> (%s)" % (len(rows), alive, uri))
    if a.open:
        webbrowser.open(uri)


if __name__ == "__main__":
    main()
