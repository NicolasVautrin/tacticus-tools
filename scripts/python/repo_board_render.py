"""Rendu HTML du board « sante du depot » (cf. `repo_board.py` pour les donnees).

Le rendu vit dans son propre module parce qu'il n'a AUCUNE logique de mesure : tout ce qui est
calcule l'est en amont. Separer les deux garde `repo_board.py` lisible comme une chaine de
sources -> jointure -> agregats, et permet de retoucher la page sans relire la mesure.

PARENTE VISUELLE. Cette page est le FRERE de `fleet-board.html` : memes neutres, memes roles
typographiques, meme grille de cellules de resume. Seule la livree change -- sarcelle ici,
indigo la-bas -- pour qu'on distingue les deux onglets d'un coup d'oeil sans que l'un paraisse
etranger a l'autre. Ne pas « moderniser » l'un sans l'autre.

Le sematique (mergee / ouverte / fermee-sans-merge) est TENU A L'ECART de l'accent : une couleur
d'etat doit rester lisible comme etat, pas comme decoration de marque.
"""
from __future__ import annotations

import html
import json
from datetime import datetime


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def n(x) -> str:
    return f"{int(x):,}".replace(",", " ")


def compact(x) -> str:
    """Chiffre court pour les cellules de resume : 4,7 G / 392 M / 12,3 k."""
    x = float(x)
    for lim, suf in ((1e9, " G"), (1e6, " M"), (1e3, " k")):
        if abs(x) >= lim:
            v = x / lim
            return (f"{v:.1f}" if v < 10 else f"{v:.0f}").replace(".", ",") + suf
    return f"{x:.0f}"


def hm(mins) -> str:
    if mins is None:
        return "-"
    mins = int(mins)
    if mins < 60:
        return "%d min" % mins
    if mins < 1440:
        return "%dh%02d" % (mins // 60, mins % 60)
    return "%d j" % (mins // 1440)


CSS = """
:root{
  color-scheme: light dark;
  /* Neutres partages avec fleet-board -- c'est ce qui fait la parente. */
  --ground:#f7f8fa; --panel:#ffffff; --ink:#161c24; --muted:#687484; --line:#dfe4ec;
  --track:#e8ecf3;
  /* Livree PROPRE a ce board : sarcelle. fleet-board est indigo. */
  --accent:#0f6f78; --accent-soft:#0f6f7822;
  /* Semantique, tenue a l'ecart de l'accent. */
  --ok:#3f8f5e; --warn:#c1841f; --crit:#c0453a;
  --mono: ui-monospace,"Cascadia Mono","SF Mono",Consolas,monospace;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
  --sans:"Inter Tight","Segoe UI Variable Display","Segoe UI",system-ui,sans-serif;
}
@media (prefers-color-scheme: dark){
  :root{ --ground:#0d1015; --panel:#141922; --ink:#e6ecf4; --muted:#8592a3; --line:#232c39;
         --track:#1d2531; --accent:#54b8c2; --accent-soft:#54b8c229;
         --ok:#5cb37c; --warn:#dfa440; --crit:#e0665a; }
}
:root[data-theme="dark"]{ --ground:#0d1015; --panel:#141922; --ink:#e6ecf4; --muted:#8592a3;
  --line:#232c39; --track:#1d2531; --accent:#54b8c2; --accent-soft:#54b8c229;
  --ok:#5cb37c; --warn:#dfa440; --crit:#e0665a; }
:root[data-theme="light"]{ --ground:#f7f8fa; --panel:#ffffff; --ink:#161c24; --muted:#687484;
  --line:#dfe4ec; --track:#e8ecf3; --accent:#0f6f78; --accent-soft:#0f6f7822;
  --ok:#3f8f5e; --warn:#c1841f; --crit:#c0453a; }

*{ box-sizing:border-box }
body{ margin:0; background:var(--ground); color:var(--ink); font-family:var(--sans);
      line-height:1.5; -webkit-font-smoothing:antialiased; overflow-x:hidden; }
.wrap{ max-width:1140px; margin:0 auto; padding:clamp(20px,4vw,52px) clamp(16px,3vw,32px) 80px; }

header{ border-bottom:2px solid var(--ink); padding-bottom:18px; }
.eyebrow{ font-family:var(--mono); font-size:11px; letter-spacing:.16em; text-transform:uppercase;
          color:var(--accent); margin:0 0 10px; }
h1{ font-size:clamp(26px,4.2vw,40px); line-height:1.08; margin:0 0 10px; letter-spacing:-.02em;
    text-wrap:balance; font-weight:640; }
.lede{ margin:0; color:var(--muted); max-width:64ch; font-size:15px; }
.stamp{ font-family:var(--mono); font-size:11.5px; color:var(--muted); margin-top:16px;
        font-variant-numeric:tabular-nums; display:block; }

h2{ font-size:13px; font-family:var(--mono); letter-spacing:.1em; text-transform:uppercase;
    color:var(--accent); font-weight:600; margin:44px 0 4px; }
.sub{ margin:0 0 18px; color:var(--muted); font-size:14px; font-family:var(--serif);
      max-width:66ch; }

/* --- registre 1 : le solde ------------------------------------------------------------ */
.summary{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:1px;
          background:var(--line); border:1px solid var(--line); margin:26px 0 8px; }
.cell{ background:var(--panel); padding:14px 16px; }
.cell dt{ font-family:var(--mono); font-size:10.5px; letter-spacing:.11em; text-transform:uppercase;
          color:var(--muted); margin:0 0 6px; }
.cell dd{ margin:0; font-family:var(--mono); font-size:21px; font-variant-numeric:tabular-nums; }
.cell dd small{ display:block; font-size:11.5px; color:var(--muted); letter-spacing:0;
                font-family:var(--sans); margin-top:3px; }

/* --- registre 2 : le journal ----------------------------------------------------------- */
/* Grille commune a l'en-tete et aux lignes : une seule declaration, sinon les colonnes
   derivent des que l'une des deux est retouchee. */
.ledger{ border-top:1px solid var(--line) }
.day{ display:grid; gap:14px; align-items:center; padding:10px 0;
      border-bottom:1px solid var(--line);
      grid-template-columns:74px minmax(120px,1fr) 68px 88px 104px 92px; }
.day.head{ border-bottom:1px solid var(--ink); padding-bottom:7px }
.day.head span{ font-family:var(--mono); font-size:9.5px; letter-spacing:.09em;
                text-transform:uppercase; color:var(--muted) }
.day.head span.r{ text-align:right }
.dlabel{ font-family:var(--mono); font-size:12.5px; font-variant-numeric:tabular-nums }
.dlabel b{ font-weight:600 }
.dlabel i{ font-style:normal; color:var(--muted); display:block; font-size:10.5px }
.bars{ display:grid; gap:3px; min-width:0 }
.bar{ height:9px; background:var(--track); border-radius:2px; overflow:hidden }
.bar.thin{ height:4px }
.bar i{ display:block; height:100%; border-radius:2px }
.b-ctx i{ background:var(--accent) }
/* Le ratio ctx/ligne est une EFFICACITE : plus la barre est courte, mieux c'est. Elle est donc
   volontairement discrete -- c'est une trace de tendance sous la quantite, pas une quantite. */
.b-eff i{ background:var(--muted); opacity:.45 }
.num{ font-family:var(--mono); font-size:12.5px; text-align:right;
      font-variant-numeric:tabular-nums }
.num.dim{ color:var(--muted) }
.num i{ font-style:normal; display:block; font-size:10px; color:var(--muted) }

/* --- registre 3 : les PR --------------------------------------------------------------- */
.controls{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin:0 0 14px;
           font-size:.78rem; color:var(--muted) }
button.chip{ font:inherit; font-family:var(--mono); font-size:11px; color:var(--muted);
             background:transparent; border:1px solid var(--line); border-radius:999px;
             padding:4px 11px; cursor:pointer; transition:color .12s,border-color .12s }
button.chip:hover{ color:var(--ink); border-color:var(--muted) }
button.chip[aria-pressed="true"]{ color:var(--ink); border-color:currentColor; font-weight:600 }
button.chip:focus-visible, th button:focus-visible{ outline:2px solid var(--accent);
                                                    outline-offset:2px }
.scroll{ overflow-x:auto; border:1px solid var(--line); background:var(--panel) }
table{ border-collapse:collapse; width:100%; min-width:820px; font-size:13px }
th,td{ text-align:left; padding:8px 12px; border-bottom:1px solid var(--line); white-space:nowrap }
th{ position:sticky; top:0; background:var(--panel); z-index:1;
    border-bottom:1px solid var(--ink) }
th button{ font:inherit; font-family:var(--mono); font-size:10px; letter-spacing:.09em;
           text-transform:uppercase; color:var(--muted); background:none; border:0; padding:0;
           cursor:pointer }
th button:hover{ color:var(--ink) }
th[aria-sort] button{ color:var(--ink); font-weight:700 }
th[aria-sort="descending"] button::after{ content:" \\2193" }
th[aria-sort="ascending"] button::after{ content:" \\2191" }
td.num{ font-family:var(--mono); font-variant-numeric:tabular-nums; text-align:right }
td.ttl{ white-space:normal; min-width:260px; max-width:420px }
td.ag{ color:var(--muted); white-space:normal; max-width:220px }
tr:hover td{ background:var(--accent-soft) }
.pill{ font-family:var(--mono); font-size:10px; letter-spacing:.04em; padding:2px 7px;
       border-radius:999px; border:1px solid currentColor }
.s-MERGED{ color:var(--ok) } .s-CLOSED{ color:var(--crit) } .s-OPEN{ color:var(--warn) }
.none{ color:var(--muted); font-style:italic }

.note{ margin-top:44px; padding:18px 20px; border-left:3px solid var(--accent);
       background:var(--panel); font-size:14.5px; font-family:var(--serif) }
.note h3{ margin:0 0 10px; font-size:13px; font-family:var(--mono); letter-spacing:.09em;
          text-transform:uppercase; color:var(--accent); font-weight:600 }
.note p{ margin:0 0 10px; max-width:72ch }
.note p:last-child{ margin-bottom:0 }
code{ font-family:var(--mono); font-size:.88em; background:var(--track); padding:1px 5px;
      border-radius:3px }
@media (max-width:640px){
  .day{ grid-template-columns:88px 1fr; }
  .dcost{ grid-column:2; text-align:left }
}
"""

JS = """
const PRS = __PRS__;
let sortKey = 'num', sortDir = -1, filter = 'all';
const tbody = document.getElementById('prbody');

const FMT = v => (v === null || v === undefined || v === '') ? '' :
  (typeof v === 'number' ? v.toLocaleString('fr-FR') : v);

function hm(m){
  if (m === null || m === undefined) return '-';
  m = Math.round(m);
  if (m < 60) return m + ' min';
  if (m < 1440) return Math.floor(m/60) + 'h' + String(m%60).padStart(2,'0');
  return Math.floor(m/1440) + ' j';
}

function draw(){
  const rows = PRS
    .filter(p => filter === 'all' ? true
               : filter === 'noagent' ? !p.agent
               : p.state === filter)
    .sort((a,b) => {
      const x = a[sortKey], y = b[sortKey];
      if (x === y) return a.num - b.num;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      return (x > y ? 1 : -1) * sortDir;
    });
  tbody.innerHTML = rows.map(p => `<tr>
    <td class="num">#${p.num}</td>
    <td><span class="pill s-${p.state}">${p.state === 'MERGED' ? 'mergee'
        : p.state === 'CLOSED' ? 'fermee' : 'ouverte'}</span></td>
    <td class="ttl">${p.title}</td>
    <td class="ag">${p.agent || '<span class="none">branche hors worktree</span>'}</td>
    <td class="num">${p.agent_ctx ? FMT(Math.round(p.agent_ctx/1e6)) + ' M' : '-'}</td>
    <td class="num">${p.agent_mins ? hm(p.agent_mins) : '-'}</td>
    <td class="num">+${FMT(p.add)}</td>
    <td class="num">-${FMT(p.dele)}</td>
    <td class="num">${p.files}</td>
    <td class="num">${hm(p.ttm)}</td>
    <td class="num">${p.day}</td></tr>`).join('');
  document.getElementById('count').textContent = rows.length + ' PR affichees';
}

document.querySelectorAll('th[data-key]').forEach(th => {
  th.querySelector('button').addEventListener('click', () => {
    const k = th.dataset.key;
    if (k === sortKey) sortDir = -sortDir; else { sortKey = k; sortDir = -1; }
    document.querySelectorAll('th[data-key]').forEach(o => o.removeAttribute('aria-sort'));
    th.setAttribute('aria-sort', sortDir === -1 ? 'descending' : 'ascending');
    draw();
  });
});
document.querySelectorAll('button.chip').forEach(b => {
  b.addEventListener('click', () => {
    filter = b.dataset.filter;
    document.querySelectorAll('button.chip').forEach(o =>
      o.setAttribute('aria-pressed', String(o === b)));
    draw();
  });
});
draw();
"""


def page(data: dict) -> str:
    days = data["days"]
    prs = data["prs"]
    merged = [p for p in prs if p["state"] == "MERGED"]
    closed = [p for p in prs if p["state"] == "CLOSED"]
    ttms = sorted(p["ttm"] for p in merged if p["ttm"] is not None)
    med = ttms[len(ttms) // 2] if ttms else None
    p90 = ttms[int(len(ttms) * 0.9)] if ttms else None
    tot_ctx = sum(d["ctx"] for d in days)
    tot_add = sum(d["add"] for d in days)
    tot_commits = sum(d["commits"] for d in days)
    tot_turns = sum(d["turns"] for d in days)
    agents_with_pr = len({p["agent_id"] for p in prs if p["agent_id"]})
    # Ratios GLOBAUX = somme/somme, PAS la moyenne des ratios quotidiens : une journee a 2 commits
    # peserait autant qu'une journee a 82 et le chiffre ne voudrait plus rien dire.
    ctx_per_commit = tot_ctx / tot_commits if tot_commits else 0
    ctx_per_line = tot_ctx / tot_add if tot_add else 0

    mx_ctx = max([d["ctx"] for d in days] + [1])
    mx_eff = max([d["ctx_per_line"] for d in days] + [1])

    # --- registre 2 : une ligne reglee par jour -----------------------------------------
    ledger = ['<div class="day head"><span>jour</span><span>context</span>'
              '<span class="r">commits</span><span class="r">+lignes</span>'
              '<span class="r">ctx / commit</span><span class="r">ctx / ligne</span></div>']
    for d in days:
        dt = datetime.strptime(d["day"], "%Y-%m-%d")
        wc = 100.0 * d["ctx"] / mx_ctx
        we = 100.0 * d["ctx_per_line"] / mx_eff
        ledger.append(
            '<div class="day">'
            f'<div class="dlabel"><b>{dt.strftime("%d/%m")}</b>'
            f'<i>{["lun","mar","mer","jeu","ven","sam","dim"][dt.weekday()]}</i></div>'
            '<div class="bars">'
            f'<div class="bar b-ctx"><i style="width:{wc:.1f}%"></i></div>'
            f'<div class="bar thin b-eff"><i style="width:{we:.1f}%"></i></div>'
            f'<div class="num dim" style="text-align:left">{compact(d["ctx"])}</div>'
            '</div>'
            f'<div class="num">{d["commits"] or "-"}</div>'
            f'<div class="num">{("+" + n(d["add"])) if d["add"] else "-"}</div>'
            f'<div class="num">{compact(d["ctx_per_commit"]) if d["commits"] else "-"}</div>'
            f'<div class="num">{compact(d["ctx_per_line"]) if d["add"] else "-"}</div>'
            '</div>')

    cols = [("num", "PR"), ("state", "etat"), ("title", "titre"), ("agent", "agent"),
            ("agent_ctx", "context"), ("agent_mins", "duree"), ("add", "+"), ("dele", "-"),
            ("files", "fichiers"), ("ttm", "latence merge"), ("day", "ouverte le")]
    thead = "".join(
        f'<th data-key="{k}"{" aria-sort=\'descending\'" if k == "num" else ""}>'
        f'<button type="button">{esc(lbl)}</button></th>' for k, lbl in cols)

    js_rows = [dict(num=p["num"], title=esc(p["title"]), state=p["state"],
                    agent=esc(p["agent"]), agent_ctx=p["agent_ctx"],
                    agent_mins=round(p["agent_mins"]) or None, add=p["add"], dele=p["dele"],
                    files=p["files"], ttm=round(p["ttm"]) if p["ttm"] is not None else None,
                    day=p["day"]) for p in prs]

    stamp = datetime.now().astimezone()
    net = data["net"].get("shortstat", "")

    return f"""<title>Registre du depot &mdash; PR, tokens, lignes</title>
<style>{CSS}</style>
<div class="wrap">
<header>
  <p class="eyebrow">tacticus-tools &middot; registre de production</p>
  <h1>Ce que la flotte a livre, et ce qu'il a fallu depenser</h1>
  <p class="lede">Trois sources independantes croisees par jour&nbsp;: les pull requests de
  GitHub, les transcripts des agents, et l'historique git. Le board de flotte montre qui vole
  maintenant&nbsp;; celui-ci montre ce qui a atterri.</p>
  <span class="stamp">Instantane du {stamp.strftime("%d/%m a %H:%M")} &middot;
  fenetre depuis le {data["since"]} &middot; {len(prs)} PR, {len(days)} jours</span>
</header>

<h2>Le solde</h2>
<dl class="summary">
  <div class="cell"><dt>context</dt><dd>{compact(tot_ctx)}<small>tokens lus, sur
    {n(tot_turns)} tours</small></dd></div>
  <div class="cell"><dt>commits</dt><dd>{n(tot_commits)}<small>hors data/symbols</small></dd></div>
  <div class="cell"><dt>lignes ajoutees</dt><dd>{compact(tot_add)}<small>churn de scission
    compris</small></dd></div>
  <div class="cell"><dt>context / commit</dt><dd>{compact(ctx_per_commit)}<small>somme sur somme,
    pas moyenne de moyennes</small></dd></div>
  <div class="cell"><dt>context / ligne</dt><dd>{compact(ctx_per_line)}<small>plus c'est bas,
    mieux c'est</small></dd></div>
  <div class="cell"><dt>pull requests</dt><dd>{len(prs)}<small>{len(merged)} mergees,
    {len(closed)} fermees sans merge</small></dd></div>
</dl>

<h2>Le journal</h2>
<p class="sub">Une ligne par jour. La barre pleine est le <strong>context</strong> &mdash; les
tokens que les modeles ont eu a lire ce jour-la, a l'echelle du jour le plus lourd. Le filet gris
dessous est le ratio <strong>context&nbsp;/&nbsp;ligne</strong>&nbsp;: c'est une efficacite, donc
une barre courte est un bon jour.</p>
<div class="ledger">{"".join(ledger)}</div>

<h2>Le registre des PR</h2>
<p class="sub">Chaque PR jointe a l'agent qui l'a produite, via sa branche de worktree. Le cout
affiche est celui de <em>cet agent</em>, transcript compris&nbsp;: c'est la mesure la plus proche
d'un cout de livraison qu'on puisse etablir. Les colonnes se trient, les pastilles filtrent.</p>
<div class="controls">
  <button type="button" class="chip" data-filter="all" aria-pressed="true">toutes</button>
  <button type="button" class="chip" data-filter="MERGED" aria-pressed="false">mergees</button>
  <button type="button" class="chip" data-filter="CLOSED" aria-pressed="false">fermees</button>
  <button type="button" class="chip" data-filter="noagent" aria-pressed="false">sans agent</button>
  <span id="count"></span>
</div>
<div class="scroll"><table><thead><tr>{thead}</tr></thead>
<tbody id="prbody"></tbody></table></div>

<div class="note">
  <h3>Rapprochement &mdash; ce que ces chiffres ne disent pas</h3>
  <p><strong>Le cout par PR n'est pas un cout de production.</strong> Les tokens d'une journee
  couvrent toute l'activite du projet &mdash; retro-ingenierie, audits, conversation &mdash; et
  pas seulement ce qui a fini en pull request. Le rapport vaut comme tendance d'une periode a
  l'autre, jamais comme prix unitaire.</p>
  <p><strong>Les lignes de commits comptent le churn.</strong> Un module scinde compte N ajouts
  et N suppressions pour zero code neuf. La croissance nette de l'arbre sur la fenetre, elle,
  annule ce bruit&nbsp;: <code>{esc(net)}</code>. C'est ce chiffre-la qui mesure ce qui a
  reellement ete ajoute au depot. <code>data/symbols</code> est exclu partout &mdash; table de
  symboles generee, pas du code ecrit.</p>
  <p><strong>{len(prs) - data["joined"]} PR sur {len(prs)} n'ont pas d'agent identifie.</strong>
  Leur branche n'est pas celle d'un worktree (<code>agent/192-sense-of-stone</code>,
  <code>case-n8b-endturn-order</code>)&nbsp;: la jointure passe par le nom de branche, et ces
  PR-la ont ete poussees autrement. Elles restent comptees partout ailleurs &mdash; une PR sans
  agent identifie reste une PR &mdash; et le filtre <em>sans agent</em> les isole.</p>
  <p><strong>Pour rafraichir</strong>&nbsp;: relancer
  <code>python scripts/python/repo_board.py</code>, puis recharger l'onglet. La page lit des
  transcripts qui vivent sur le disque local et elle est servie depuis un bac a sable&nbsp;: elle
  ne peut pas se recalculer seule.</p>
</div>
</div>
<script>{JS.replace("__PRS__", json.dumps(js_rows, ensure_ascii=False))}</script>
"""
