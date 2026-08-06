"""Telemetrie CONTEXTE de la flotte d'agents -- table console + page HTML rechargeable.

    python scripts/python/fleet_board.py            # table console + ecrit logs/fleet-board.html
    python scripts/python/fleet_board.py --open     # ... et l'ouvre dans le navigateur
    python scripts/python/fleet_board.py --all      # inclut les agents TERMINES

Boucle de rafraichissement : RELANCER CETTE COMMANDE, puis recharger l'onglet. C'est le SEUL vrai
refresh possible -- un artefact publie sur claude.ai est sandboxe et ne peut pas relire ces
transcripts, qui vivent sur le disque local.

(Il y avait un bouton « Recharger » dans la page : retire. Il ne faisait qu'un `location.reload()`,
qui reaffiche le MEME HTML fige a la generation -- un geste qui promet une mise a jour et n'en
produit aucune est pire que pas de bouton du tout.)

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
import os
import subprocess
import time
# `webbrowser` est importe PARESSEUSEMENT (dans `main`) : il tire une chaine de modules qui
# pesait ~0,2 s a l'import, pour un service rendu au seul `--open`. Ce module est desormais
# importe par `loop_status`, dont le budget total est celui d'un hook de fin de tour.
from datetime import datetime, timezone
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


def _texte_du_message(msg) -> str:
    """Le `content` d'un message est soit une chaine, soit une liste de blocs typés."""
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def scan(path: Path) -> dict:
    first = last = None
    first_ts = last_ts = None
    says: list[str] = []
    tools = 0
    brief = ""
    for ln in path.open(encoding="utf-8", errors="replace"):
        if '"usage"' not in ln and '"tool_use"' not in ln and '"user"' not in ln:
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            continue                       # ligne tronquee (transcript en cours d'ecriture)
        msg = rec.get("message") or {}
        # Le BRIEF n'est PAS dans le meta.json (qui ne porte que agentType / description /
        # worktree* / toolUseId / spawnDepth) : c'est le PREMIER message `user` du transcript.
        # Les suivants sont les relances par SendMessage -- on ne garde que le premier.
        if msg.get("role") == "user" and not brief:
            t = _texte_du_message(msg).strip()
            if t and not t.startswith("<"):     # ecarte les injections systeme (<system-reminder>)
                brief = t
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
                says=says, tools=tools, brief=brief)


# Un agent qui TRAVAILLE ecrit dans son transcript a chaque aller-retour d'outil. Au-dela de ce
# silence il est arrete -- mesure du 2026-07-27 sur 15 agents : les vivants etaient TOUS a 12 min
# ou moins, les morts TOUS a 30 min ou plus, aucun entre les deux. 15 min tombe dans ce trou et
# laisse passer un test live long (le plus lent mesure : ~12 min).
SILENCE_MORT_MIN = 15.0

# Ordre d'affichage des trois etats. « attente » passe AVANT « fini » parce que c'est le seul des
# deux sur lequel il reste une decision a prendre : reprendre l'agent, ou recuperer sa branche.
RANG = {"vif": 0, "attente": 1, "fini": 2}


def est_vif(last_ts) -> tuple[bool, float]:
    """VIF = a ecrit recemment dans son transcript. Rend (vif, minutes de silence).

    NE PAS revenir au `git worktree lock` : mesure du 2026-07-27, 0 verrou pose sur 15 agents
    dont 8 travaillaient. Le verrou n'est pose qu'au LANCEMENT (outil Agent) ; une reprise par
    `SendMessage` n'en pose aucun -- le critere devient donc aveugle des la premiere reprise, et
    il l'est SILENCIEUSEMENT (tout le monde affiche « fini »). L'existence du repertoire ne vaut
    pas mieux : un agent arrete garde son worktree jusqu'au nettoyage.
    """
    if last_ts is None:
        return False, float("inf")
    silence = (datetime.now(timezone.utc) - last_ts).total_seconds() / 60.0
    return silence < SILENCE_MORT_MIN, silence


def transcripts(racine: Path, only_alive: bool) -> list[Path]:
    """Transcripts d'agents. En `only_alive`, PRE-FILTRES par mtime. Preuve, pas heuristique.

    `last_ts` (dernier horodatage INTERNE d'un transcript) est ecrit AU MOMENT ou la
    ligne part sur disque, donc `last_ts <= mtime`. Si `now - mtime >= SILENCE_MORT_MIN`,
    alors `silence = now - last_ts >= now - mtime >= SILENCE_MORT_MIN` : `est_vif`
    rendrait False de toute facon. Ecarter le fichier ne peut donc PAS changer l'etat
    « vif » d'un seul agent.

    C'est ce qui rend `only_alive` utilisable dans un hook de fin de tour : 870
    transcripts pour 1,23 Go relus a chaque appel (54,8 s mesurees le 2026-08-04)
    contre 5 fichiers et 0,4 s.

    `os.scandir` plutot que `Path.glob` + `stat()` : sous Windows le mtime vient de
    l'ENUMERATION du repertoire, donc `DirEntry.stat()` ne fait aucun aller-retour --
    le pre-filtre devient a peu pres gratuit.
    """
    limite = time.time() - SILENCE_MORT_MIN * 60.0
    out: list[Path] = []
    try:
        sessions = list(os.scandir(racine))
    except OSError:
        return out
    for s in sessions:
        if not s.is_dir():
            continue
        try:
            entrees = list(os.scandir(Path(s.path) / "subagents"))
        except OSError:
            continue
        for e in entrees:
            if not (e.name.startswith("agent-") and e.name.endswith(".jsonl")):
                continue
            if only_alive:
                try:
                    if e.stat().st_mtime < limite:
                        continue
                except OSError:
                    pass                   # illisible : on ne l'ecarte pas, on le scanne
            out.append(Path(e.path))
    return sorted(out)


def collect(include_done: bool, only_alive: bool = False) -> list[dict]:
    """Lignes de la flotte. `only_alive` ne rend QUE les « vif », et vite.

    Le mode complet lit TOUS les transcripts (c'est ce qu'exige l'etat « attente » :
    un agent en pause n'ecrit plus, seul son worktree le distingue d'un agent fini).
    `only_alive` renonce a cet etat -- il repond a « qui TRAVAILLE maintenant », et
    rien d'autre -- ce qui autorise le pre-filtre prouve ci-dessus.
    """
    rows = []
    for p in transcripts(project_dir(), only_alive):
        aid = p.stem.replace("agent-", "")
        meta_p = p.with_name("agent-%s.meta.json" % aid)
        meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
        s = scan(p)
        if not s["first"]:
            continue
        alive, silence = est_vif(s["last_ts"])
        # ET le worktree doit EXISTER. Un transcript reste sur disque pour toujours ; son worktree,
        # lui, est supprime au nettoyage -- c'est ce qui separe un agent d'aujourd'hui d'un agent
        # d'il y a trois jours dont l'horodatage serait mal lu. Piege : `Path("")` vaut `Path(".")`,
        # qui existe TOUJOURS, d'ou le test de chaine non vide. Un agent lance SANS worktree
        # (`worktreePath` absent) reste juge sur la seule activite.
        wtp = (meta.get("worktreePath") or "").strip()
        has_wt = bool(wtp) and Path(wtp).exists()
        if wtp and not has_wt:
            alive = False
        # TROIS etats, pas deux -- et le WORKTREE est le discriminant du troisieme.
        #
        # Un agent SUSPENDU (arrete, mais repris plus tard par `SendMessage` avec son contexte
        # intact) GARDE son worktree ; un agent fini ET nettoye ne l'a plus. Le silence, lui, ne
        # sait pas les distinguer : un agent en pause ne peut pas ecrire dans son transcript, donc
        # il tombe dans le meme sac que celui qui a atterri il y a trois jours. Resultat mesure le
        # 2026-07-27 : SIX branches d'agents portant 9 abilities dormaient sur disque sans que le
        # board les montre -- et elles ont failli etre supprimees comme des worktrees perimes.
        state = "vif" if alive else ("attente" if has_wt else "fini")
        if state == "fini" and not include_done:
            continue
        # `only_alive` ne PROMET que les vifs : un « attente » survivant au pre-filtre
        # (worktree present ET transcript ecrit il y a moins de 15 min mais worktree
        # disparu entre-temps) serait rendu de facon NON REPRODUCTIBLE selon l'heure.
        # On le retire, pour que le mode rapide ait un contrat exact.
        if only_alive and state != "vif":
            continue
        mins = ((s["last_ts"] - s["first_ts"]).total_seconds() / 60.0
                if s["first_ts"] and s["last_ts"] else 0.0)
        work = max(0, s["last"] - s["first"])
        rows.append(dict(
            id=aid, name=meta.get("description") or aid, alive=alive, state=state,
            wt=wtp if has_wt else "", silence=silence,
            base=s["first"], ctx=s["last"], work=work, mins=mins,
            # < 30 s : le denominateur est trop petit pour que le quotient veuille dire quelque
            # chose (un seul aller-retour d'outil ferait 100 000 tok/min).
            rate=(work / mins) if mins > 0.5 else 0.0,
            pct=100.0 * s["last"] / WINDOW, tools=s["tools"], says=s["says"][-2:],
            # ni la date ni le brief ne sont dans le meta.json : le lancement est le PREMIER
            # horodatage du transcript, l'atterrissage le DERNIER, le brief le 1er message `user`.
            born=s["first_ts"], land=s["last_ts"], agent_type=meta.get("agentType") or "",
            branch=meta.get("worktreeBranch") or "", brief=s["brief"],
            # LA PARENTE, publiee telle qu'elle est ECRITE dans le meta -- elle ne se devine pas.
            # `spawnDepth` 1 = tranche DISPATCHEE ; >= 2 = sous-agent lance par un solveur (il
            # porte alors `parentAgentId`). Mesure du 2026-08-06 : 5 tranches a `depth=1` avec
            # worktree, 1 sous-agent a `depth=2` sans worktree.
            # ⚠ Ne PAS deriver la parente de l'absence de worktree : un agent de tete lance sans
            # `isolation: worktree` n'en a pas non plus, et serait pris pour un enfant. La
            # profondeur, elle, dit ce qu'elle dit.
            depth=int(meta.get("spawnDepth") or 1),
            parent=meta.get("parentAgentId") or ""))
    rows.sort(key=lambda r: (RANG[r["state"]], -r["ctx"]))
    return rows


# ---------------------------------------------------------------- rendu
def hm(mins) -> str:
    m = int(round(mins))
    return "%dh%02d" % (m // 60, m % 60) if m >= 60 else "%d min" % m


def eta(r):
    """Minutes avant saturation de la fenetre, au rythme courant."""
    return None if r["rate"] <= 0 else (WINDOW - r["ctx"]) / r["rate"]


ETIQ = {"vif": "en vol", "attente": "ATTENTE", "fini": "-"}


def console(rows) -> None:
    print("%-34s %-8s %9s %9s %9s %7s %9s %6s %8s"
          % ("agent", "etat", "contexte", "base sys", "travail", "min", "tok/min", "%fen", "sature"))
    for r in rows:
        e = eta(r)
        print("%-34s %-8s %9d %9d %9d %7.0f %9.0f %6.1f %8s"
              % (r["name"][:34], ETIQ[r["state"]], r["ctx"], r["base"], r["work"],
                 r["mins"], r["rate"], r["pct"], "--" if e is None else hm(e)))
    n_att = sum(1 for r in rows if r["state"] == "attente")
    if n_att:
        print("\n%d agent(s) EN ATTENTE -- arretes, worktree conserve, reprenables par SendMessage :"
              % n_att)
        for r in rows:
            if r["state"] == "attente":
                print("   %-34s silence %s   %s" % (r["name"][:34], hm(r["silence"]), r["wt"]))


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
         line-height:1.5; -webkit-font-smoothing:antialiased;
         /* garde-fou : le corps ne doit JAMAIS defiler horizontalement. Un debordement lateral
            sur mobile detourne le geste et donne l'impression que le defilement vertical est mort. */
         overflow-x:hidden; }
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

  /* --- tri, pastille de vol, brief deplie ------------------------------------------------- */
  .sorts { display:inline-flex; align-items:center; gap:6px; font-size:.78rem;
           color:var(--muted); letter-spacing:.02em; }
  .sort { font:inherit; color:var(--muted); background:transparent; cursor:pointer;
          border:1px solid var(--line); border-radius:999px; padding:3px 10px;
          transition:color .12s, border-color .12s; }
  .sort:hover { color:var(--ink); border-color:var(--muted); }
  .sort[data-on="1"] { color:var(--ink); border-color:currentColor; font-weight:600; }
  .sort[data-on="1"][data-dir="desc"]::after { content:' ↓'; }
  .sort[data-on="1"][data-dir="asc"]::after  { content:' ↑'; }

  /* la pastille ne clignote QUE si l'onglet est visible et que l'utilisateur accepte le mouvement */
  .dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:7px;
         background:var(--ok); vertical-align:middle; animation:pulse 2.4s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:.35 } }
  @media (prefers-reduced-motion:reduce) { .dot { animation:none } }
  /* EN ATTENTE : creux et FIXE. Il ne clignote pas parce qu'il ne se passe rien -- mais il est la,
     parce qu'il reste une decision a prendre dessus (reprendre, ou recuperer sa branche). */
  .dot.wait { background:transparent; border:2px solid var(--warn); width:9px; height:9px;
              box-sizing:border-box; animation:none; }

  .figs.meta { margin-top:3px; font-size:.74rem; opacity:.72; }
  .brief { margin-top:10px; border-top:1px dashed var(--line); padding-top:8px; }
  .brief summary { cursor:pointer; font-size:.76rem; color:var(--muted); letter-spacing:.02em; }
  .brief summary:hover { color:var(--ink); }
  /* PAS de `max-height` + `overflow-y:auto` ici : un scroller IMBRIQUE est un piege tactile. Sur
     mobile, un doigt qui atterrit dans le bloc est capture par lui et ne fait plus defiler la PAGE
     -- le defilement parait casse alors que rien ne l'empeche. Le brief est deja replie dans un
     <details> : quand on l'ouvre, on veut le lire en entier, pas dans une lucarne de 22 em. */
  .brief pre { margin:8px 0 0; padding:10px 12px; background:var(--track); border-radius:6px;
               font-family:var(--mono); font-size:.74rem; line-height:1.5; color:var(--ink);
               white-space:pre-wrap; overflow-wrap:anywhere; }
</style>

<div class="wrap">
  <header>
    <p class="eyebrow">tacticus-tools · campagne de portage</p>
    <h1>Ce que la flotte a mis dans sa fenêtre</h1>
    <p class="lede">__N__ agents en vol sur __TOT__ affichés, chacun avec sa propre fenêtre d'un
    million de tokens. La jauge mesure ce qu'elle contient <em>maintenant</em> — pas ce qu'elle a
    coûté.</p>
    <div class="tools">
      <span class="stamp">Instantané du <time datetime="__ISO__">__STAMP__</time><span class="age" id="age"></span></span>
      <span class="sorts">trier par
        <button type="button" class="sort" data-key="ctx">contexte</button>
        <button type="button" class="sort" data-key="born">lancement</button>
        <button type="button" class="sort" data-key="land">atterrissage</button>
      </span>
    </div>
  </header>

  <dl class="summary">
    <div class="cell"><dt>en vol</dt><dd>__N__<small>agents isolés</small></dd></div>
    <div class="cell"><dt>en attente</dt><dd>__ATT__<small>worktree conservé</small></dd></div>
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
    puis recharger l'onglet. Cette page ne peut pas se recalculer seule : elle lit des transcripts
    qui vivent sur le disque local, et elle est servie depuis un bac à sable.</p>
  </div>
</div>

<script>
const ROWS = __PAYLOAD__, STAMP = new Date("__ISO__");
const fmt = n => n.toLocaleString('fr-FR').replace(/\\u202f|\\u00a0/g, ' ');
const carte = r => `
  <div class="gauge" data-band="${r.band}" data-alive="${r.alive ? 1 : 0}" data-state="${r.state}">
    <div class="grow">
      <div class="gname">${r.state === 'vif' ? '<span class="dot" title="en vol"></span>'
          : r.state === 'attente' ? '<span class="dot wait" title="en attente — worktree conservé, reprenable"></span>' : ''}${r.name}</div>
      <div class="figs">
        <span><b>${fmt(r.ctx)}</b> ctx</span>
        <span><b>${fmt(r.rate)}</b> tok/min</span>
        <span>${r.minsLabel} de vol</span>
        <span>saturation&nbsp;<b>${r.etaLabel}</b></span>
      </div>
      <div class="figs meta">
        <span>lancé <b>${r.bornLabel}</b></span>
        <span>${r.state === 'vif' ? 'dernier signe' : r.state === 'attente' ? 'en pause depuis' : 'atterri'} <b>${r.landLabel}</b></span>
        ${r.state === 'attente' && r.branch ? `<span>branche <b>${r.branch}</b></span>` : ''}
        ${r.type ? `<span>${r.type}</span>` : ''}
      </div>
    </div>
    <div class="bar">
      <div class="seg-base" style="width:${r.basePct}%"></div>
      <div class="seg-work" style="width:${r.workPct}%"></div>
      <span class="pct">${r.pct} %</span>
    </div>
    ${r.says.length ? `<ul class="says">${r.says.map(s => `<li>${s}</li>`).join('')}</ul>` : ''}
    ${r.brief ? `<details class="brief"><summary>le brief envoyé${r.briefCut ? ' — début' : ''}</summary><pre>${r.brief}${r.briefCut ? '\\n\\n[…] tronqué : agent atterri, voir son rapport final.' : ''}</pre></details>` : ''}
  </div>`;

// Tri : le critere est porte par le bouton (data-key), le sens par data-dir. « lancé » se lit
// naturellement du plus ANCIEN au plus recent, les deux autres du plus GROS / plus RECENT.
const CLES = { ctx: r => r.ctx, born: r => r.born, land: r => r.land };
let cle = 'ctx', sens = -1;
const fleet = document.getElementById('fleet');
const dessine = () => {
  const f = CLES[cle];
  // l'ETAT prime sur le critere de tri : vifs d'abord (on les surveille), puis ceux EN ATTENTE
  // (une decision reste a prendre dessus), puis le reste. Sans ca, un agent en pause se noie dans
  // l'historique des termines des qu'on trie par contexte.
  const RANG = { vif: 0, attente: 1, fini: 2 };
  const t = ROWS.slice().sort((a, b) =>
    (RANG[a.state] - RANG[b.state]) || (sens * (f(a) - f(b))));
  fleet.innerHTML = t.map(carte).join('');
  document.querySelectorAll('.sort').forEach(b => {
    b.dataset.on = b.dataset.key === cle ? '1' : '0';
    if (b.dataset.key === cle) b.dataset.dir = sens < 0 ? 'desc' : 'asc';
  });
};
document.querySelectorAll('.sort').forEach(b => b.addEventListener('click', () => {
  const k = b.dataset.key;
  sens = (k === cle) ? -sens : (k === 'born' ? 1 : -1);
  cle = k;
  dessine();
}));
dessine();

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
</script>
"""


def _quand(t, now) -> str:
    """« 08:12 » si c'est aujourd'hui, « 26/07 23:38 » sinon -- une flotte vit sur 2-3 jours."""
    if not t:
        return "--"
    loc = t.astimezone()
    return loc.strftime("%H:%M") if loc.date() == now.date() else loc.strftime("%d/%m %H:%M")


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
            "alive": bool(r["alive"]), "state": r["state"],
            # epoch en secondes : c'est ce que le tri JS compare, sans reparser de date.
            "born": r["born"].timestamp() if r["born"] else 0,
            "land": r["land"].timestamp() if r["land"] else 0,
            "bornLabel": _quand(r["born"], now), "landLabel": _quand(r["land"], now),
            "type": html.escape(r["agent_type"]), "branch": html.escape(r["branch"]),
            # Le brief est la seule trace de ce qu'on a demande a l'agent. ENTIER pour un agent EN
            # VOL (on veut pouvoir relire sa consigne pendant qu'il travaille) ; TRONQUE pour un
            # agent atterri, dont le rapport final dit mieux que son brief. Sans cette coupe, `--all`
            # pese 2 Mo (395 briefs) et la publication de l'artefact expire.
            # ENTIER tant qu'il reste une decision a prendre -- donc aussi pour un agent EN ATTENTE,
            # dont la consigne est exactement ce qu'on relit avant de decider de le reprendre.
            "brief": html.escape(r["brief"] if r["state"] != "fini" else r["brief"][:700]),
            "briefCut": r["state"] == "fini" and len(r["brief"]) > 700,
        })
    fastest = max(cards, key=lambda c: c["rate"]) if cards else None
    withe = [(c, r) for c, r in zip(cards, rows) if eta(r) is not None]
    nearest = min(withe, key=lambda cr: eta(cr[1]))[0] if withe else None
    med = sorted(c["pct"] for c in cards)[len(cards) // 2] if cards else 0.0
    return (TPL
            .replace("__PAYLOAD__", json.dumps(cards, ensure_ascii=False))
            .replace("__ISO__", now.isoformat())
            .replace("__STAMP__", now.strftime("%d/%m a %H:%M"))
            # __N__ = les VIFS, pas `len(cards)` : avec `--all` les cartes portent tout l'historique
            # des transcripts (394 mesures le 2026-07-27), et le titre annoncait donc « 394 agents
            # en vol ». Le total, lui, est __TOT__.
            .replace("__N__", str(sum(1 for r in rows if r["alive"])))
            .replace("__ATT__", str(sum(1 for r in rows if r["state"] == "attente")))
            .replace("__TOT__", str(len(cards)))
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
        import webbrowser
        webbrowser.open(uri)


if __name__ == "__main__":
    main()
