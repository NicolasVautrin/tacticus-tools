"""Cout REEL d'une tranche d'agent : la SOMME des contextes relus a chaque aller-retour.

`subagent_tokens` de la notification est l'OCCUPATION FINALE de la fenetre (mesure du
2026-08-07 : ecart 0,1-0,2 % avec la colonne `contexte` de `fleet_board`). Elle ne dit rien
du cout : chaque requete re-envoie tout le contexte accumule, donc le cout est l'INTEGRALE,
pas la borne. Ce script la mesure sur le transcript, requete par requete.

Sortie ASCII stricte (console Windows cp1252).
"""
import json
import sys
from pathlib import Path

# Tarifs RELATIFS Anthropic (input = 1 unite). Le cache-read est facture une fraction de
# l'input ; le cache-write un peu plus cher. On raisonne en UNITES D'INPUT, pas en dollars --
# on compare des tranches entre elles, pas un budget.
PRIX_INPUT = 1.0
PRIX_CACHE_READ = 0.1
PRIX_CACHE_WRITE = 1.25
PRIX_OUTPUT = 5.0


def mesurer(chemin: Path):
    n_req = 0
    s_in = s_cr = s_cw = s_out = 0
    ctx_max = 0
    ctx_final = 0
    for ligne in chemin.read_text(encoding="utf-8", errors="replace").splitlines():
        if not ligne.strip():
            continue
        try:
            o = json.loads(ligne)
        except Exception:
            continue
        u = (o.get("message") or {}).get("usage") or o.get("usage")
        if not isinstance(u, dict):
            continue
        inp = u.get("input_tokens") or 0
        cr = u.get("cache_read_input_tokens") or 0
        cw = u.get("cache_creation_input_tokens") or 0
        out = u.get("output_tokens") or 0
        if inp == 0 and cr == 0 and cw == 0:
            continue
        n_req += 1
        s_in += inp
        s_cr += cr
        s_cw += cw
        s_out += out
        ctx = inp + cr + cw
        ctx_final = ctx
        ctx_max = max(ctx_max, ctx)
    cout = (s_in * PRIX_INPUT + s_cr * PRIX_CACHE_READ
            + s_cw * PRIX_CACHE_WRITE + s_out * PRIX_OUTPUT)
    return {
        "requetes": n_req,
        "ctx_final": ctx_final,
        "ctx_max": ctx_max,
        "somme_contextes": s_in + s_cr + s_cw,
        "input": s_in, "cache_read": s_cr, "cache_write": s_cw, "output": s_out,
        "cout_unites_input": cout,
    }


def main():
    if len(sys.argv) < 2:
        print("usage: mesure_cout_agent.py <transcript.jsonl> [...]")
        return 2
    lignes = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if not p.exists():
            print("ABSENT : %s" % p)
            continue
        m = mesurer(p)
        m["nom"] = p.stem.replace("agent-", "")[:18]
        lignes.append(m)
    if not lignes:
        return 1
    print("%-20s %8s %10s %14s %14s %10s" % (
        "agent", "req", "ctx_final", "somme_ctx", "cout(u.input)", "cout/req"))
    for m in lignes:
        print("%-20s %8d %10d %14d %14.0f %10.0f" % (
            m["nom"], m["requetes"], m["ctx_final"], m["somme_contextes"],
            m["cout_unites_input"], m["cout_unites_input"] / max(1, m["requetes"])))
    print("")
    print("detail (tokens cumules sur toutes les requetes) :")
    for m in lignes:
        print("  %-18s input=%d cache_read=%d cache_write=%d output=%d"
              % (m["nom"], m["input"], m["cache_read"], m["cache_write"], m["output"]))
    if len(lignes) == 2:
        a, b = sorted(lignes, key=lambda x: x["cout_unites_input"])
        print("")
        print("RAPPORT DE COUT   %s / %s = %.2fx" % (
            b["nom"], a["nom"], b["cout_unites_input"] / max(1.0, a["cout_unites_input"])))
        print("RAPPORT DE FENETRE (ce que `subagent_tokens` laissait croire) = %.2fx" % (
            b["ctx_final"] / max(1.0, a["ctx_final"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
