"""Joint chaque PULL REQUEST a l'AGENT qui l'a produite, et sort des stats de transcript.

LA CLE DE JOINTURE EXISTE DEJA, elle n'a jamais ete ecrite nulle part
-------------------------------------------------------------------
Un agent lance en `isolation: "worktree"` travaille sur la branche
`worktree-agent-<agentId>`, et c'est cette branche qui devient le `headRefName`
de sa PR. Le meme identifiant nomme son transcript. La chaine est donc :

    PR.headRefName  ==  <meta>.worktreeBranch  ==  worktree-agent-<agentId>
                                                   |
                    ~/.claude/projects/<projet>/<session>/subagents/
                        agent-<agentId>.jsonl        <- le transcript (des Mo)
                        agent-<agentId>.meta.json    <- agentType, description

⚠ PIEGE : `<tmp>/<session>/tasks/<agentId>.output` fait **0 octet** -- c'est un
emplacement leurre. Mesure du 2026-08-11 : 34 PR sur 40 y pointaient vers du vide.
Le contenu est TOUJOURS dans `subagents/agent-<agentId>.jsonl`.

⚠ La jointure est SANS COUTURE tant que la branche suit la convention. Une branche
nommee a la main (`agent-921-sanguinary-priest`) ne joint RIEN, et c'est dit
explicitement -- jamais rabattu sur un zero.

TRI-ETAT
--------
Comme `host_inputs.py` : `null` = PAS MESURE, jamais un zero. Une PR sans meta,
un transcript illisible, un `gh` muet sortent NOMMES, pas silencieux.
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import os
import subprocess
import sys

CHAMPS_PR = "number,title,state,headRefName,createdAt,closedAt,mergedAt,additions,deletions,changedFiles"


def _racine_projets(depot: str) -> str:
    """Repertoire ou Claude Code range les transcripts de CE depot.

    Le nom du dossier est le chemin absolu dont CHAQUE separateur -- `:` compris --
    devient un `-`. D'ou le double tiret apres la lettre de lecteur :
    `C:\\Users\\...` -> `C--Users-...`. On le DERIVE, on ne le code pas en dur.
    """
    encode = depot.replace(":", "-").replace("\\", "-").replace("/", "-")
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", encode)


def indexer_agents(racine: str) -> dict:
    """branche -> {agentId, agentType, description, jsonl, meta, session}."""
    par_branche = {}
    if not os.path.isdir(racine):
        return par_branche
    for session in sorted(os.listdir(racine)):
        dossier = os.path.join(racine, session, "subagents")
        if not os.path.isdir(dossier):
            continue
        for nom in os.listdir(dossier):
            if not nom.endswith(".meta.json"):
                continue
            chemin = os.path.join(dossier, nom)
            try:
                meta = json.load(open(chemin, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            branche = meta.get("worktreeBranch")
            if not branche:
                continue
            agent_id = nom[len("agent-"):-len(".meta.json")]
            jsonl = os.path.join(dossier, "agent-%s.jsonl" % agent_id)
            par_branche[branche] = {
                "agentId": agent_id,
                "agentType": meta.get("agentType"),
                "description": meta.get("description"),
                "spawnDepth": meta.get("spawnDepth"),
                "session": session,
                "jsonl": jsonl if os.path.isfile(jsonl) else None,
                "taille": os.path.getsize(jsonl) if os.path.isfile(jsonl) else None,
            }
    return par_branche


def lire_transcript(chemin: str) -> dict:
    """Depouille un transcript. Rend None sur toute valeur NON MESUREE."""
    outils = collections.Counter()
    tours_assistant = 0
    tours_user = 0
    out_tokens = 0
    in_tokens = 0
    cache_read = 0
    premier = dernier = None
    lignes = 0

    try:
        flux = open(chemin, encoding="utf-8")
    except OSError:
        return {"lisible": False}

    with flux:
        for ligne in flux:
            ligne = ligne.strip()
            if not ligne:
                continue
            try:
                o = json.loads(ligne)
            except ValueError:
                continue
            lignes += 1
            horo = o.get("timestamp")
            if horo:
                if premier is None:
                    premier = horo
                dernier = horo
            msg = o.get("message")
            if not isinstance(msg, dict):
                continue
            if msg.get("role") == "assistant":
                tours_assistant += 1
            elif msg.get("role") == "user":
                tours_user += 1
            usage = msg.get("usage")
            if isinstance(usage, dict):
                out_tokens += usage.get("output_tokens") or 0
                in_tokens += usage.get("input_tokens") or 0
                cache_read += usage.get("cache_read_input_tokens") or 0
            contenu = msg.get("content")
            if isinstance(contenu, list):
                for bloc in contenu:
                    if isinstance(bloc, dict) and bloc.get("type") == "tool_use":
                        outils[bloc.get("name") or "?"] += 1

    duree = None
    if premier and dernier:
        try:
            a = _dt.datetime.fromisoformat(premier.replace("Z", "+00:00"))
            b = _dt.datetime.fromisoformat(dernier.replace("Z", "+00:00"))
            duree = (b - a).total_seconds()
        except ValueError:
            duree = None

    return {
        "lisible": True,
        "lignes": lignes,
        "tours_assistant": tours_assistant,
        "tours_user": tours_user,
        "outils_total": sum(outils.values()),
        "outils": dict(outils.most_common()),
        "out_tokens": out_tokens,
        "in_tokens": in_tokens,
        "cache_read": cache_read,
        "debut": premier,
        "fin": dernier,
        "duree_s": duree,
    }


def lister_pr(limite: int, depot: str):
    """Rend (liste, None) ou (None, raison) -- jamais une liste vide en cas de panne."""
    cmd = ["gh", "pr", "list", "--state", "all", "--limit", str(limite), "--json", CHAMPS_PR]
    try:
        p = subprocess.run(cmd, cwd=depot, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return None, "gh INTROUVABLE sur le PATH"
    except subprocess.TimeoutExpired:
        return None, "gh DELAI DEPASSE (60 s)"
    except OSError as exc:
        return None, "gh ERREUR SYSTEME : %s" % exc
    if p.returncode != 0:
        return None, "gh rc=%d : %s" % (p.returncode, (p.stderr or "").strip()[:200])
    try:
        return json.loads(p.stdout), None
    except ValueError as exc:
        return None, "sortie gh illisible : %s" % exc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=40, help="nombre de PR a examiner")
    ap.add_argument("--depot", default=None, help="racine du depot (defaut: deduit du script)")
    ap.add_argument("--tsv", default=None, help="ecrit le detail dans ce TSV")
    ap.add_argument("--outils", action="store_true", help="detaille l'usage par outil")
    args = ap.parse_args()

    depot = args.depot or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    racine = _racine_projets(depot)

    agents = indexer_agents(racine)
    print("transcripts indexes : %d branches d'agent" % len(agents))
    print("racine              : %s" % racine)
    if not agents:
        print("  ⚠ AUCUN transcript trouve -- la jointure ne rendra rien (PAS MESURE, pas zero)")

    prs, panne = lister_pr(args.limit, depot)
    if prs is None:
        print("PR : PAS MESURE -- %s" % panne)
        return 2

    lignes_tsv = []
    joints = orphelins = sans_jsonl = 0
    par_type = collections.Counter()
    tot_outils = collections.Counter()
    somme_out = somme_duree = 0

    print("")
    entete = "%-6s %-8s %-14s %-34s %8s %7s %9s  %s"
    print(entete % ("PR", "etat", "agentType", "description", "duree", "outils", "out_tok", "agentId"))
    print("-" * 120)

    for pr in prs:
        branche = pr.get("headRefName") or ""
        info = agents.get(branche)
        if info is None:
            orphelins += 1
            # Un index VIDE ne prouve rien sur la branche : c'est le RECENSEMENT
            # qui manque, pas la convention qui est violee. Ne jamais fabriquer
            # un diagnostic que la mesure ne porte pas.
            cause = "AUCUN AGENT JOINT" if agents else "INDEX VIDE -- PAS MESURE"
            print(entete % ("#%d" % pr["number"], (pr.get("state") or "")[:8],
                            "-", cause, "-", "-", "-", "(branche: %s)" % branche))
            lignes_tsv.append([pr["number"], pr.get("state"), branche, "", "", "", "", "", "", "", "", ""])
            continue

        joints += 1
        par_type[info["agentType"]] += 1
        st = lire_transcript(info["jsonl"]) if info["jsonl"] else {"lisible": False}
        if not st.get("lisible"):
            sans_jsonl += 1
            duree = outils = out_tok = "PAS MESURE"
        else:
            duree = "%.0fmin" % (st["duree_s"] / 60) if st["duree_s"] is not None else "?"
            outils = st["outils_total"]
            out_tok = st["out_tokens"]
            somme_out += st["out_tokens"]
            if st["duree_s"]:
                somme_duree += st["duree_s"]
            tot_outils.update(st["outils"])

        print(entete % ("#%d" % pr["number"], (pr.get("state") or "")[:8],
                        (info["agentType"] or "?")[:14], (info["description"] or "?")[:34],
                        duree, outils, out_tok, info["agentId"]))

        lignes_tsv.append([
            pr["number"], pr.get("state"), branche, info["agentId"], info["agentType"],
            info["description"], st.get("duree_s"), st.get("outils_total"),
            st.get("out_tokens"), pr.get("additions"), pr.get("deletions"), pr.get("changedFiles"),
        ])

    print("-" * 120)
    print("")
    print("JOINTURE  : %d joints | %d SANS AGENT (branche hors convention) | %d sans transcript lisible"
          % (joints, orphelins, sans_jsonl))
    if joints:
        print("par type  : %s" % dict(par_type))
        print("cumul     : %s tokens de sortie, %.1f h d'agent" % ("{:,}".format(somme_out).replace(",", " "), somme_duree / 3600))
    if args.outils and tot_outils:
        print("")
        print("OUTILS (tous agents joints) :")
        for nom, n in tot_outils.most_common(15):
            print("  %-36s %6d" % (nom, n))

    if args.tsv:
        with open(args.tsv, "w", encoding="utf-8", newline="\n") as f:
            f.write("\t".join(["pr", "etat", "branche", "agentId", "agentType", "description",
                               "duree_s", "outils", "out_tokens", "additions", "deletions",
                               "changed_files"]) + "\n")
            for l in lignes_tsv:
                f.write("\t".join("" if v is None else str(v) for v in l) + "\n")
        print("")
        print("TSV ecrit : %s (%d lignes)" % (args.tsv, len(lignes_tsv)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
