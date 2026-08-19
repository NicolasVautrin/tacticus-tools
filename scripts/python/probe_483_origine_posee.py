"""#483 -- MESURE : un armement NOMINATIF rend-il une capture AVEUGLE ?

LE RISQUE QUE CE PROBE MESURE, et qui pouvait invalider toute la tranche #483. Un armement
PAR RUNNER ne capture que si `getTraceOrigin()` vaut ce runner AU MOMENT DU FIRE. Or seuls
certains RPC posent l'origine (`setTraceOrigin`, dans leur job `queueOnMainThread`). Un
probe qui armerait pour `rid` puis piloterait le natif par un RPC **qui ne la pose pas**
verrait ses events partir dans le bucket `null` : sa capture, qui marchait en armement
GLOBAL, deviendrait VIDE -- une regression introduite par le correctif lui-meme, et
silencieuse (un seau vide se lit comme « rien ne s'est passe »).

CE PROBE N'EST PAS UN CLIQUET. Il MESURE et il RANGE ; il ne rend pas de verdict rouge.
Les probes mesurent, les cliquets gardent -- le cliquet de #483 est
`probe_483_armement_par_runner.py`.

LES DEUX COTES SONT DERIVES, aucune liste en dur :
  * les RPC POSEURS : tout `ctx.rpc.<nom>` de `frida/hooks/` dont le corps appelle
    `setTraceOrigin` ;
  * les probes du PERIMETRE : tout `scripts/python/**.py` qui appelle un RPC d'ARMEMENT
    (suffixe On/Off/Arm/Disarm/Enable/Disable/SetEnabled) -- donc concerne par #483.

⚠ CE QU'IL NE VOIT PAS, et qu'il DIT : l'INDIRECTION. Un probe qui pilote par un helper
(`predict_samples._drive_into_range`) n'expose aucun RPC de pilotage a une lecture
syntaxique -- il apparait ici en `pilotage: (aucun)`, ce qui ne veut PAS dire qu'il ne
pilote rien. Ces cas se tranchent A LA MAIN, en lisant le helper. Un compte filtre doit
dire ce qu'il filtre.

ASCII only. Offline pur.

Usage : python scripts/python/probe_483_origine_posee.py [--verbeux]
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOKS = ROOT / "frida" / "hooks"
PY = ROOT / "scripts" / "python"

RE_RPC_DECL = re.compile(r"ctx\.rpc\.(\w+)\s*=")
RE_SET_ORIGIN = re.compile(r"setTraceOrigin\(")
RE_APPEL_PY = re.compile(r'"([a-z]\w+)"\s*[,)]')
SUFFIXES_ARMEMENT = ("On", "Off", "Arm", "Disarm", "Enable", "Disable", "SetEnabled")

#: RPC de LECTURE : ils n'ont pas a poser l'origine, ils la FILTRENT (ou lisent un etat).
#: `observeBattle` en fait partie -- c'est une projection d'etat, elle ne fait firer AUCUN
#: hook de trace.
RE_LECTEURS = re.compile(r"(Dump|Status|Clear|Reset|Layout|Counters|Backtraces|List)")
LECTEURS_NOMMES = {
    "observeBattle", "listRunners", "disposeRunner", "autoBootExtraire",
    "ping", "info", "hitTrace", "summary",
    # `dump` (status.ts) est un lecteur de log. Il apparait ici surtout comme HOMONYME :
    # une chaine `"dump"` d'un dict de probe coincide avec un nom de RPC declare. C'est
    # l'angle mort assume d'un recenseur syntaxique -- il lit des CHAINES, pas des appels.
    "dump",
}


def rpcs_poseurs() -> set[str]:
    """Tout `ctx.rpc.<nom>` dont le corps appelle `setTraceOrigin`."""
    out: set[str] = set()
    if not HOOKS.is_dir():
        return out
    for p in sorted(HOOKS.rglob("*.ts")):
        txt = io.open(p, encoding="utf-8", errors="replace").read()
        if "setTraceOrigin(" not in txt:
            continue
        courant = None
        for ligne in txt.splitlines():
            m = RE_RPC_DECL.search(ligne)
            if m:
                courant = m.group(1)
            if RE_SET_ORIGIN.search(ligne) and "import" not in ligne and courant:
                out.add(courant)
    return out


def tous_les_rpc() -> set[str]:
    """TOUT `ctx.rpc.<nom>` declare par les hooks.

    ⚠ Sans ce croisement, le recenseur cote Python prend pour des RPC toutes les chaines
    d'un appel -- cles de dict, `store_true`, noms d'unites... Mesure faite : il rendait
    des dizaines de « RPC qui ne posent pas l'origine » nommes `col`, `row`, `ok`. Un
    token qui n'est PAS un RPC declare n'est pas un RPC : c'est le build qui le dit, pas
    une liste d'exclusion, qui ne pourrait pas montrer le token qu'elle a oublie.
    """
    out: set[str] = set()
    if not HOOKS.is_dir():
        return out
    for p in sorted(HOOKS.rglob("*.ts")):
        txt = io.open(p, encoding="utf-8", errors="replace").read()
        for m in RE_RPC_DECL.finditer(txt):
            out.add(m.group(1))
    return out


def rpcs_armement() -> set[str]:
    """Les RPC d'ARMEMENT declares par les features -- ce qui definit le perimetre."""
    out: set[str] = set()
    feats = HOOKS / "features"
    if not feats.is_dir():
        return out
    for p in sorted(feats.rglob("*.ts")):
        txt = io.open(p, encoding="utf-8", errors="replace").read()
        if "new OriginBuffers<" not in txt:
            continue
        for m in RE_RPC_DECL.finditer(txt):
            if m.group(1).endswith(SUFFIXES_ARMEMENT):
                out.add(m.group(1))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbeux", action="store_true")
    a = ap.parse_args()

    poseurs = rpcs_poseurs()
    armeurs = rpcs_armement()
    connus = tous_les_rpc()
    if not poseurs or not armeurs or not connus:
        print("NON MESURE : poseurs=%d armeurs=%d connus=%d -- un cote est vide."
              % (len(poseurs), len(armeurs), len(connus)))
        return 3
    print("RPC DECLARES par les hooks (le referentiel)             : %d" % len(connus))
    print("RPC qui POSENT l'origine (derives de `setTraceOrigin`)  : %d" % len(poseurs))
    if a.verbeux:
        for n in sorted(poseurs):
            print("   %s" % n)
    print("RPC d'ARMEMENT (derives de `new OriginBuffers<`)        : %d" % len(armeurs))

    aveugles: dict[str, list[str]] = {}
    indirects: list[str] = []
    vus = 0
    print("\nProbes du perimetre (ils appellent un RPC d'armement) :")
    for p in sorted(PY.rglob("*.py")):
        if p.name.startswith("probe_483_"):
            continue
        txt = io.open(p, encoding="utf-8", errors="replace").read()
        appels = {m.group(1) for m in RE_APPEL_PY.finditer(txt)}
        if not (appels & armeurs):
            continue
        vus += 1
        nom = p.relative_to(PY).as_posix()
        pilotage = {x for x in (appels & connus)          # un RPC, pas une cle de dict
                    if x not in armeurs and x not in LECTEURS_NOMMES
                    and not RE_LECTEURS.search(x)}
        ok = sorted(x for x in pilotage if x in poseurs)
        non = sorted(x for x in pilotage if x not in poseurs)
        if not ok and not non:
            indirects.append(nom)
            print("   %-50s pilotage: (aucun vu -- INDIRECTION, a lire a la main)" % nom)
            continue
        print("   %-50s pose: %s" % (nom, ",".join(ok) or "-"))
        if non:
            aveugles[nom] = non
            print("        %-44s NE POSE PAS : %s" % ("", ",".join(non)))

    print("\n=== BILAN (%d probe(s) du perimetre) ===" % vus)
    if vus == 0:
        print("NON MESURE : aucun probe du perimetre -- rien a croiser.")
        return 3
    if aveugles:
        print("A EXAMINER -- ces RPC de pilotage ne posent pas l'origine. Un armement")
        print("NOMINATIF ne captera RIEN de ce qu'ils declenchent :")
        for k, v in sorted(aveugles.items()):
            print("   %s -> %s" % (k, ", ".join(v)))
    else:
        print("Tous les RPC de pilotage vus posent l'origine.")
    if indirects:
        print("\nNON TRANCHES PAR CE PROBE (%d) -- ils pilotent par un HELPER, invisible a une"
              % len(indirects))
        print("lecture syntaxique. `pilotage: (aucun)` ne veut PAS dire « ne pilote rien » :")
        for n in indirects:
            print("   %s" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
