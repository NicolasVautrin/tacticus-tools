#!/usr/bin/env python
"""#477-r15 -- l'identite des unites dans le flux de replay : par quelle CLE apparier ?

Ce probe MESURE. Il tranche la question qui commande toute la strategie de comparaison
de flux : le flux natif permet-il d'apparier deux unites qui PARTAGENT LE MEME KIT ?

L'AFFIRMATION CONFRONTEE
------------------------
`docs/rl/case-477r11-format-du-flux-de-replay.md` § 5b ecrit :

    « Sans aucun porteur : `visualId`, `squadId`, `rank`. Le plus lourd est `visualId` :
      le flux ne nomme jamais l'unite. [...] L'identite ne se reconstitue qu'indirectement,
      par la signature du kit emise juste apres. »

et en tire : « l'appariement des entites entre deux flux repose sur l'ORDRE d'apparition ou
sur cette signature de kit, jamais sur un identifiant ».

Ce probe montre que c'est **faux pour `squadId`** et **vrai pour `visualId`**, et que la
consequence pratique s'inverse : l'appariement N'A PAS besoin de la signature du kit.

CE QUI EST MESURE (trois montages, boards de tailles differentes)
----------------------------------------------------------------
1. `Action=AddUnit Entity=<N>` -- le `<N>` de CHAQUE ligne du flux coincide avec le champ
   `squadId` de `observeBattle`, unite par unite. `squadId` A donc un porteur : ce n'est pas
   un TAG, c'est le `Entity=` porte par la ligne elle-meme. Un recenseur qui ne cherche un
   porteur que parmi les `Tag=` le manque -- meme vice que l'appariement par sous-chaine
   deja corrige au § 5a de la meme fiche.
2. La SIGNATURE DU KIT est AMBIGUE : sur deux unites du meme `unitId`, les tags de kit
   (stats, ids d'ability, niveaux) sont STRICTEMENT EGAUX. Apparier par signature de kit,
   comme la fiche le proposait, est donc IMPOSSIBLE des que le roster porte un doublon --
   ce qui est un roster parfaitement legal (`--p-units "X,X"` passe).
3. L'id d'entite est un COMPTEUR D'ALLOCATION GLOBAL : il depend du nombre d'entites creees
   avant les unites, donc du nombre de TUILES du board. C'est la contrainte structurante
   pour un futur emetteur cote port -- pas un detail cosmetique.

USAGE
    python scripts/python/probe_477r15_identite_par_kit.py --session <sid>
    python scripts/python/probe_477r15_identite_par_kit.py --session <sid> --boards MC1_67,C1_02

⚠ Monte des runners (un par board, dispose au fil de l'eau). Budget partage : garder
`--boards` court. Le volet OFFLINE de la tranche (couverture de l'emetteur) est dans
`probe_477r15_stream_emitter_coverage.py` et ne consomme aucun runner.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
HOST = "http://127.0.0.1:8765"

# Le roster DECISIF : deux unites du MEME `unitId` (donc kit identique au tag pres) plus un
# temoin d'un autre kit. Sans le doublon, la question de l'ambiguite ne se pose meme pas --
# c'est exactement pour ca que le regime n'avait jamais ete joue.
ROSTER_P = "adeptCanoness,adeptCanoness,adeptRetributor"
ROSTER_A = "adeptHospitaller,adeptMorvenn"
KIT_DOUBLE = "adeptCanoness"

# Les deux boards par defaut sont choisis pour AVOIR DES TAILLES DIFFERENTES (63 vs 35
# tuiles). Deux boards de meme taille rendraient les memes ids et se liraient, a tort,
# comme une preuve d'independance -- piege effectivement rencontre a la mesure (MC1_67 et
# C1_70 font tous deux 63 tuiles et donnent les MEMES ids).
BOARDS_DEFAUT = ("MC1_67", "C1_02")

# Les tags qui varient LEGITIMEMENT entre deux instances du meme kit sans rien dire du kit :
# ids d'entites derivees (effets alloues sequentiellement) et position. Les exclure est ce
# qui rend la comparaison de signature HONNETE -- les garder ferait croire a tort que la
# signature discrimine.
TAGS_HORS_SIGNATURE = ("Effect_Id", "Effect_SourceId", "Effect_TargetId",
                       "Tile", "Foot", "Target_Id", "Attacker_Id", "Source_Id")


class MesureImpossible(RuntimeError):
    """Une source manque -- on le DIT, on ne rend pas un verdict."""


def rpc(session: int, method: str, args: dict, timeout: int = 40) -> dict:
    body = json.dumps({"method": method, "args": [args], "timeout": 30000}).encode()
    req = urllib.request.Request("%s/api/scripts/%d/rpc" % (HOST, session), data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()).get("result") or {}
    except (urllib.error.URLError, OSError) as e:
        raise MesureImpossible("RPC %s injoignable : %s" % (method, e)) from e


def build(board: str, state_file: Path) -> int:
    """Monte un runner avec le roster a kit double. Rend le runnerId."""
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", "777", "--board", board,
           "--p-units", ROSTER_P, "--a-units", ROSTER_A,
           "--record-replay", "--no-ai", "--state-file", str(state_file)]
    p = subprocess.run(cmd, cwd=str(HERE), capture_output=True, text=True, timeout=600)
    if not state_file.is_file():
        raise MesureImpossible("build %s echoue : %s" % (board, (p.stderr or p.stdout)[-400:]))
    return int(json.loads(state_file.read_text(encoding="utf-8"))["runnerId"])


def blocs_addunit(flux: str) -> list[dict]:
    """[{entity, tags}] pour chaque `Action=AddUnit`, tags lus a depth+1."""
    lignes = flux.split("\n")
    out, i = [], 0
    while i < len(lignes):
        s = lignes[i]
        m = re.match(r"\s*Action=AddUnit Entity=(\S+)", s)
        if not m:
            i += 1
            continue
        indent = len(s) - len(s.lstrip())
        tags, j = {}, i + 1
        while j < len(lignes):
            t = lignes[j]
            if not t.strip():
                j += 1
                continue
            if len(t) - len(t.lstrip()) <= indent:
                break
            mt = re.match(r"\s*Tag=(\w+):(-?\d+)", t)
            if mt:
                tags[mt.group(1)] = mt.group(2)
            j += 1
        out.append({"entity": m.group(1), "tags": tags})
        i = j
    return out


def signature_kit(flux: str, entity: str) -> list:
    """Tags rattaches a `entity`, PURGES de ce qui varie hors kit.

    On suit la derniere `Action=... Entity=N` rencontree : c'est la portee d'un tag dans la
    grammaire (un tag par ligne, a depth+1 de son action)."""
    out, cur = [], None
    for s in flux.split("\n"):
        st = s.strip()
        ma = re.match(r"Action=(\w+) Entity=(\S+)", st)
        if ma:
            cur = ma.group(2)
            continue
        mt = re.match(r"Tag=(\w+):(-?\d+)", st)
        if mt and cur == entity:
            cle = mt.group(1)
            if any(x in cle for x in TAGS_HORS_SIGNATURE):
                continue
            out.append((cle, mt.group(2)))
    return out


def mesurer_board(session: int, board: str) -> dict:
    tmp = Path(tempfile.gettempdir()) / ("r15-ident-%s.json" % board)
    rid = build(board, tmp)
    try:
        flux = rpc(session, "replayOutputStream", {"runnerId": rid}).get("outputStream") or ""
        obs = rpc(session, "observeBattle", {"runnerId": rid}).get("units") or []
        if not flux:
            raise MesureImpossible(
                "flux VIDE sur %s -- l'enregistreur etait-il arme (--record-replay) ?" % board)
        units = blocs_addunit(flux)
        tuiles = re.findall(r"Action=AddTile Entity=(\d+)", flux)
        # correspondance Entity= (flux)  <->  squadId (observeBattle), unite par unite
        ent_flux = [u["entity"] for u in units]
        squads = [str(u.get("squadId")) for u in obs]
        doubles = [str(u.get("squadId")) for u in obs if u.get("visualId") == KIT_DOUBLE]
        sigs = [signature_kit(flux, e) for e in doubles]
        return {
            "board": board, "runner": rid, "nb_tuiles": len(tuiles),
            "entites_flux": ent_flux, "squad_ids": squads,
            "concordance": ent_flux == squads,
            "kit_double": KIT_DOUBLE, "entites_du_double": doubles,
            "signatures_egales": (len(sigs) >= 2 and all(s == sigs[0] for s in sigs)),
            "taille_signature": len(sigs[0]) if sigs else None,
            "visual_ids": [u.get("visualId") for u in obs],
        }
    finally:
        try:
            rpc(session, "disposeRunner", {"runnerId": rid}, timeout=30)
        except MesureImpossible:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--session", type=int, required=True, help="id de session Frida (running)")
    ap.add_argument("--boards", default=",".join(BOARDS_DEFAUT),
                    help="boards a jouer, TAILLES DIFFERENTES de preference")
    a = ap.parse_args()

    res = []
    for b in [x.strip() for x in a.boards.split(",") if x.strip()]:
        try:
            res.append(mesurer_board(a.session, b))
        except MesureImpossible as e:
            print("PAS MESURE (%s) : %s" % (b, e))
    if not res:
        print("VERDICT : PAS MESURE -- aucun board n'a pu etre monte.")
        return 2

    print("=" * 78)
    print("#477-r15 -- cle d'appariement des unites dans le flux")
    print("=" * 78)
    for r in res:
        print("\n[%s] runner=%d, %d tuiles" % (r["board"], r["runner"], r["nb_tuiles"]))
        print("    Entity= du flux    : %s" % r["entites_flux"])
        print("    squadId observe    : %s" % r["squad_ids"])
        print("    concordance        : %s" % ("OUI" if r["concordance"] else "NON"))
        print("    kits               : %s" % r["visual_ids"])
        print("    '%s' porte %d fois -> entites %s"
              % (r["kit_double"], len(r["entites_du_double"]), r["entites_du_double"]))
        print("    signatures de kit EGALES entre les doublons : %s (%s tags compares)"
              % ("OUI" if r["signatures_egales"] else "NON", r["taille_signature"]))

    concordant = all(r["concordance"] for r in res)
    ambigu = all(r["signatures_egales"] for r in res)
    decale = len({tuple(r["entites_flux"]) for r in res}) > 1

    print("\n" + "-" * 78)
    print("VERDICT")
    print("  1. `squadId` A UN PORTEUR : c'est le `Entity=` de chaque ligne -- concordance %s."
          % ("VERIFIEE sur tous les boards" if concordant else "MISE EN DEFAUT"))
    print("  2. La signature du kit %s entre deux unites du meme kit."
          % ("NE DISCRIMINE PAS" if ambigu else "discrimine"))
    print("     => apparier par signature de kit est IMPOSSIBLE sur un roster a doublon ;")
    print("        apparier par `Entity=` marche, et ne demande aucune reconstruction.")
    print("  3. L'id d'entite %s avec la taille du board (compteur d'allocation global)."
          % ("SE DECALE" if decale else "n'a pas varie ici -- rejouer avec des tailles distinctes"))
    if not decale:
        print("     ATTENTION : boards de meme taille => ce point n'est PAS mesure.")
    print("     => un emetteur cote port doit reproduire l'ORDRE ET LE NOMBRE d'allocations")
    print("        d'entites (tuiles comprises), sinon TOUTES les lignes divergent.")
    return 0 if (concordant and ambigu) else 1


if __name__ == "__main__":
    raise SystemExit(main())
