"""La RAMPE d'un agent : ce qu'il paie AVANT de produire quoi que ce soit.

Objection mesuree : decouper une tranche en deux AUGMENTE le nombre de requetes,
parce que le second agent doit se refaire un contexte sans rien produire. Ce script
chiffre cette rampe -- requetes et cout jusqu'a la PREMIERE ecriture (Edit/Write/
NotebookEdit) -- pour la confronter a ce que le decoupage economise.

Sortie ASCII stricte.
"""
import json
import sys
from pathlib import Path

ECRITURE = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def scan(p: Path):
    n = 0
    cout = 0.0
    rampe_n = None
    rampe_cout = None
    total = 0.0
    ctx_final = 0
    for l in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if not l.strip():
            continue
        try:
            o = json.loads(l)
        except Exception:
            continue
        msg = o.get("message") or {}
        u = msg.get("usage") or o.get("usage")
        if isinstance(u, dict):
            i = u.get("input_tokens") or 0
            cr = u.get("cache_read_input_tokens") or 0
            cw = u.get("cache_creation_input_tokens") or 0
            ou = u.get("output_tokens") or 0
            if i or cr or cw:
                n += 1
                c = i + cr * 0.1 + cw * 1.25 + ou * 5.0
                cout += c
                total = cout
                ctx_final = i + cr + cw
        # premiere ECRITURE
        if rampe_n is None:
            contenu = msg.get("content")
            if isinstance(contenu, list):
                for bloc in contenu:
                    if (isinstance(bloc, dict) and bloc.get("type") == "tool_use"
                            and bloc.get("name") in ECRITURE):
                        rampe_n = n
                        rampe_cout = cout
                        break
    return {"n": n, "cout": total, "ctx_final": ctx_final,
            "rampe_n": rampe_n, "rampe_cout": rampe_cout}


def main():
    print("%-14s %5s %10s %13s | %7s %12s %8s %9s" % (
        "agent", "req", "ctx_final", "cout total",
        "rampe", "cout rampe", "% cout", "% req"))
    for a in sys.argv[1:]:
        p = Path(a)
        if not p.exists():
            continue
        s = scan(p)
        if not s["n"]:
            continue
        if s["rampe_n"] is None:
            print("%-14s %5d %10d %13.0f | %7s %12s %8s %9s" % (
                p.stem.replace("agent-", "")[:14], s["n"], s["ctx_final"], s["cout"],
                "AUCUNE", "-", "-", "-"))
            continue
        print("%-14s %5d %10d %13.0f | %7d %12.0f %7.1f%% %8.1f%%" % (
            p.stem.replace("agent-", "")[:14], s["n"], s["ctx_final"], s["cout"],
            s["rampe_n"], s["rampe_cout"],
            s["rampe_cout"] / s["cout"] * 100, s["rampe_n"] / s["n"] * 100))
    return 0


if __name__ == "__main__":
    sys.exit(main())
