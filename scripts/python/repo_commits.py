"""Cout d'un COMMIT : tokens et temps, attribues par flux de travail.

Complement de `repo_board.py`, qui agrege par JOUR. Ici l'unite est le commit, parce qu'un jour
melange des commits de tailles incomparables et des flux concurrents.

=== LES TROIS DECISIONS DE METHODE, ET CE QUI LES JUSTIFIE (mesures du 2026-07-28) ===

1. LES MERGES SONT EXCLUS DU DENOMINATEUR.
   841 commits dont 118 de merge -> 723 commits de CONTENU. Les compter gonflait tous les ratios
   par commit de 14 %. Les LIGNES, elles, n'ont jamais ete affectees : `git log --numstat` ignore
   deja le diff d'un merge (457 684 lignes avec ou sans).
   Le cout propre du geste de merge a ete mesure : 429 tours sur 168 747 (0,25 %), soit 2 790 690
   tokens marginaux = 0,19 % du total -- et c'est une borne HAUTE (le filtre attrape aussi les
   sondes qui citent `git merge`). Sous le seuil de bruit : on le signale, on ne le repartit pas.

2. `cache_read` N'EST JAMAIS ATTRIBUE A UN COMMIT.
   C'est par construction la relecture de tout ce qui precede, y compris le travail des commits
   anterieurs. Preuve chiffree : les 429 tours de merge portent 145 432 519 de `cache_read` pour
   2 790 690 de cout marginal -- 52x. Imputer le PROMPT d'un tour au commit reviendrait a lui
   facturer le contexte accumule de toute la session.
   D'ou `unique = input_tokens + cache_creation + output_tokens` : le contenu NEUF du tour.

3. LE TEMPS ACTIF EST PLAFONNE A 300 s PAR INTERVALLE -- seuil MESURE, pas choisi.
   p99,5 des 168 432 intervalles entre tours vaut 361 s : au-dela, ce n'est plus un tour de
   travail. Et la queue le confirme -- 0,07 % des intervalles (> 1 h) portent 42,8 % du temps
   brut. Ce sont les nuits. Sur 2 068 h calendaires, 1 082 h sont actives.
   RESERVE ASSUMEE : le plafond impute 300 s a un intervalle qui peut en durer 87 h. Un agent
   bloque 20 min sur un test live compte donc 5 min. La mesure SOUS-ESTIME les attentes longues
   et legitimes -- elle est conservatrice, pas neutre.

=== L'ATTRIBUTION, ET POURQUOI ELLE EST HYBRIDE ===

Le discriminant est l'EXCLUSIVITE du transcript, et il est testable :

  - SOUS-AGENT -> transcript DEDIE, donc pris EN ENTIER. Il n'existe que pour produire sa
    branche ; rien n'y est partage avec un autre commit.
  - ORCHESTRATEUR -> transcript PARTAGE, donc MARGINAL sur l'intervalle. Mesure : un segment de
    contexte (entre deux compactages) porte mediane 2 commits, moyenne 6,6, maximum 266. Imputer
    le transcript entier a un commit le compterait jusqu'a 266 fois.

La jointure commit -> agent se fait par le SHA : un transcript qui a produit un commit en contient
le SHA (git l'affiche au retour de `git commit`). Mesure : 358/724 commits de contenu (49 %) sont
cites par un transcript d'agent. Le rebase ne casse pas ce lien -- l'agent rebase, puis voit
lui-meme les SHA reecrits.

VOIE ECARTEE -- le trailer `Claude-Session` du message de commit. Il est present sur 618/840
commits et identifie bien un flux, mais : (a) son espace de noms (`session_01...`) est disjoint des
noms de fichiers de transcript, qu'aucun champ n'enregistre ; (b) la relation est N sessions -> 1
transcript (sept identifiants pointent le seul fichier `b2170732`), parce qu'un transcript est une
CONVERSATION, pas une session -- chaque reprise ouvre une session API et continue d'ecrire dans le
meme JSONL ; (c) il nomme la session PARENTE, jamais l'agent (11 identifiants pour 475 agents).
La jointure par SHA lui est superieure sur les deux axes : 89 % de couverture contre 74 %, et elle
pointe le fichier directement.
"""
from __future__ import annotations

import bisect
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXCLUDE = ":(exclude)data/symbols"

# Seuil MESURE (p99,5 = 361 s), pas un reglage. Cf. decision 3 de la docstring.
CAP_S = 300.0
# Bascule serie -> parallele : premiere PR du depot. Avant, un seul flux produisait les commits.
ERA_SPLIT = "2026-07-16"

SHA_RX = re.compile(r"\b[0-9a-f]{7,40}\b")


def sh(args: list[str]) -> str:
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


def _ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------- commits de contenu
def load_content_commits() -> list[dict]:
    """Commits SANS les merges, avec date du committer et lignes hors `data/symbols`."""
    raw = sh(["git", "log", "--no-merges", "--pretty=format:C|%H|%cI|%s", "--numstat",
              "--", ".", EXCLUDE])
    out = []
    for ln in raw.splitlines():
        if ln.startswith("C|"):
            _, sha, iso, subj = ln.split("|", 3)
            out.append(dict(sha=sha[:8], full=sha, t=_ts(iso), subj=subj, add=0, dele=0))
            continue
        p = ln.split("\t")
        if len(p) == 3 and out and p[0] != "-":
            out[-1]["add"] += int(p[0])
            out[-1]["dele"] += int(p[1])
    out = [c for c in out if c["t"]]
    out.sort(key=lambda c: c["t"])
    return out


# ---------------------------------------------------------------- flux de tours
def load_turns(pdir: Path) -> tuple[list, dict]:
    """Rend (tours tries, index agent_id -> agregat).

    Un tour porte : horodatage, les 4 compteurs, sa duree ACTIVE (plafonnee), et l'id d'agent
    quand il vient d'un transcript de sous-agent.
    """
    turns = []
    agents = {}
    seen = set()
    for fp in sorted(pdir.glob("*.jsonl")) + sorted(pdir.glob("*/subagents/agent-*.jsonl")):
        aid = fp.stem.replace("agent-", "") if "subagents" in fp.parts else None
        prev = None
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
                u = (rec.get("message") or {}).get("usage") or {}
                t = _ts(rec.get("timestamp") or "")
                if not u or not t:
                    continue
                uid = rec.get("uuid")
                if uid:
                    if uid in seen:
                        continue
                    seen.add(uid)
                # La duree d'un tour est l'ecart depuis le PRECEDENT du meme flux : c'est le seul
                # ecart qui mesure ce flux-la. Un ecart global melangerait les agents concurrents.
                dur = min((t - prev).total_seconds(), CAP_S) if (prev and t > prev) else 0.0
                prev = t
                row = dict(t=t, aid=aid, dur=dur,
                           fresh=int(u.get("input_tokens") or 0),
                           write=int(u.get("cache_creation_input_tokens") or 0),
                           read=int(u.get("cache_read_input_tokens") or 0),
                           out=int(u.get("output_tokens") or 0))
                row["uniq"] = row["fresh"] + row["write"] + row["out"]
                turns.append(row)
                if aid:
                    a = agents.setdefault(aid, dict(uniq=0, dur=0.0, turns=0,
                                                    first=None, last=None))
                    a["uniq"] += row["uniq"]
                    a["dur"] += dur
                    a["turns"] += 1
                    if a["first"] is None or t < a["first"]:
                        a["first"] = t
                    a["last"] = t if (a["last"] is None or t > a["last"]) else a["last"]
    turns.sort(key=lambda r: r["t"])
    return turns, agents


def sha_to_agent(pdir: Path, shas: set) -> dict:
    """SHA de commit -> id d'agent, par citation dans le transcript de l'agent.

    Un transcript qui a produit un commit en contient le SHA (retour de `git commit`). C'est la
    jointure la plus directe : pas d'identifiant intermediaire a resoudre.
    """
    pref = {s[:7] for s in shas}
    out = {}
    for fp in sorted(pdir.glob("*/subagents/agent-*.jsonl")):
        aid = fp.stem.replace("agent-", "")
        try:
            fh = fp.open("r", encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for ln in fh:
                for tok in SHA_RX.findall(ln):
                    p = tok[:7]
                    if p in pref:
                        out.setdefault(p, aid)
    return out


# ---------------------------------------------------------------- assemblage
def build(pdir: Path) -> dict:
    commits = load_content_commits()
    turns, agents = load_turns(pdir)
    if not commits or not turns:
        return dict(commits=[], eras=[], cap=CAP_S)

    s2a = sha_to_agent(pdir, {c["full"] for c in commits})
    keys = [r["t"] for r in turns]

    # --- attribution ------------------------------------------------------------------
    prev_i = 0
    for c in commits:
        i = bisect.bisect_left(keys, c["t"])
        aid = s2a.get(c["sha"][:7])
        if aid and aid in agents:
            # EXCLUSIF : le transcript de l'agent n'a servi qu'a ca.
            a = agents[aid]
            c.update(source="agent", agent=aid, uniq=a["uniq"], dur=a["dur"], turns=a["turns"])
        else:
            # PARTAGE : seul le contenu NEUF de l'intervalle est imputable.
            seg = turns[prev_i:i]
            c.update(source="orchestrateur", agent="",
                     uniq=sum(r["uniq"] for r in seg),
                     dur=sum(r["dur"] for r in seg), turns=len(seg))
        c["era"] = "serielle" if c["t"].strftime("%Y-%m-%d") < ERA_SPLIT else "parallele"
        prev_i = i

    # --- agregats par ere -------------------------------------------------------------
    eras = []
    for name in ("serielle", "parallele"):
        cs = [c for c in commits if c["era"] == name and c["turns"] > 0]
        if not cs:
            continue
        act = sum(c["dur"] for c in cs) / 3600.0
        elapsed = (max(c["t"] for c in cs) - min(c["t"] for c in cs)).total_seconds() / 3600.0
        uniq = sum(c["uniq"] for c in cs)
        add = sum(c["add"] for c in cs)
        eras.append(dict(
            name=name, n=len(cs), uniq=uniq, add=add, active_h=act, elapsed_h=elapsed,
            # > 1 n'est PAS une anomalie : le temps actif somme les flux concurrents, il peut
            # donc legitimement depasser le temps ecoule. C'est ce qu'on cherche a mesurer.
            parallelism=(act / elapsed) if elapsed else 0.0,
            uniq_per_commit=uniq / len(cs), uniq_per_line=(uniq / add) if add else 0,
            min_per_commit=act * 60 / len(cs), s_per_line=(act * 3600 / add) if add else 0,
            agents=sum(1 for c in cs if c["source"] == "agent"),
            start=min(c["t"] for c in cs), end=max(c["t"] for c in cs)))
    return dict(commits=commits, eras=eras, cap=CAP_S, split=ERA_SPLIT,
                n_agent=sum(1 for c in commits if c.get("source") == "agent"))
