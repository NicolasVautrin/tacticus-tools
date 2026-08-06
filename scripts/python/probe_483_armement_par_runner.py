"""#483 -- CLIQUET OFFLINE : une capture PAR RUNNER doit avoir une porte PAR RUNNER.

LE DEFAUT QU'IL GARDE. Six features de `frida/hooks/features/` capturent PAR RUNNER
(`OriginBuffers` + `getTraceOrigin()`, champ `originRunnerId`) et leurs RPC `*Dump`/`*Clear`
filtrent bien par `runnerId` -- mais leur PORTE d'armement etait un booleen de MODULE,
session-global. Les probes appellent leur `*Off` dans un `finally`, donc il s'execute
TOUJOURS : en regime 4-en-parallele, le premier probe qui finit DESARME la capture des
autres. La victime dumpe alors un seau TRONQUE, sans aucune erreur -- un vert qui ment.

CE QU'IL MESURE, en quatre etages, et pourquoi chacun existe :

  E1  Toute feature du perimetre CONSULTE l'origine (`capturing` de `game/armed-runners`).
      Sans lui, la porte ne peut structurellement pas distinguer deux acteurs.
  E2  AUCUNE affectation `<x>.on = ` / `<x>.enabled = ` ne subsiste dans le perimetre.
      C'est l'etage qui MORD : ce sont exactement les 15 sites qui portaient le defaut.
      Une porte qui se REASSIGNE est un booleen de module ; une porte qui se LIT est un
      accesseur. L'etage E1 seul serait contournable (importer `capturing` sans s'en servir).
  E3  Tout RPC d'armement (nom finissant par On/Off/Arm/Disarm/Enable/Disable/SetEnabled)
      DECLARE un `runnerId` dans sa signature. Sans lui l'appelant n'a aucun moyen de scoper,
      et le defaut se rouvre cote appel meme si la porte est correcte.
  E4  Cote PYTHON, tout site qui arme/desarme passe un `runnerId` -- ou porte le marqueur
      `ARMEMENT GLOBAL ASSUME`, echappatoire CONSCIENTE pour les sites qui arment AVANT que
      le runner existe. Un site muet est refuse : c'est par la que le defaut est ne.

PERIMETRE **DERIVE**, jamais liste : est dans le perimetre tout fichier de
`frida/hooks/features/` qui instancie `new OriginBuffers<`. Une liste blanche des six ne
pourrait pas montrer la SEPTIEME -- exactement le vice « un recenseur ne rend pas zero sur
ce qu'il ne visite pas ». Le perimetre s'ASSERTIONNE NON VIDE : un perimetre vide sort en
NON MESURE (rc 3), jamais en vert.

MUTANT (`--mutant`) : chaque etage recoit une version MUTEE en memoire et doit ROUGIR.
Un cliquet qui ne sait pas rougir est un inventaire deguise en garde-fou (#430).

ASCII only. Offline pur -- aucune session Frida, aucun runner.

Usage :
  python scripts/python/probe_483_armement_par_runner.py
  python scripts/python/probe_483_armement_par_runner.py --mutant
  python scripts/python/probe_483_armement_par_runner.py --verbeux

Codes de sortie : 0 = VERT, 1 = ROUGE, 3 = NON MESURE.
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / "frida" / "hooks" / "features"
PY_DIR = ROOT / "scripts" / "python"

#: Ce qui fait entrer un module dans le perimetre : il capture PAR RUNNER.
MARQUEUR_PERIMETRE = "new OriginBuffers<"
#: Le predicat du foyer, seul autorise a decider d'une capture.
PREDICAT_FOYER = "capturing("
MODULE_FOYER = "game/armed-runners"
#: Un RPC dont le nom finit par l'un de ces suffixes ARME ou DESARME.
SUFFIXES_ARMEMENT = ("On", "Off", "Arm", "Disarm", "Enable", "Disable", "SetEnabled")
#: Echappatoire consciente cote Python.
MARQUEUR_GLOBAL_ASSUME = "ARMEMENT GLOBAL ASSUME"


# --------------------------------------------------------------- outils de lecture TS

def denuder_ts(src: str) -> str:
    """Rend le source PRIVE de ses commentaires et de ses litteraux de chaine.

    Sans ca, E2 rougirait sur une PROSE qui cite `trace.on = ok` -- et le correctif de
    #483 en contient une, deliberement (elle documente ce qui a ete remplace). Un cliquet
    qui accuse la documentation de son propre correctif fait renoncer a documenter.
    Les caracteres retires sont remplaces par des espaces : les numeros de ligne et les
    colonnes restent exacts, donc un diagnostic reste localisable.
    """
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                out.append(" ")
                i += 1
            continue
        if c == "/" and nxt == "*":
            while i < n and not (src[i] == "*" and i + 1 < n and src[i + 1] == "/"):
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            out.append("  ")
            i += 2
            continue
        if c in ("'", '"', "`"):
            quote = c
            out.append(" ")
            i += 1
            while i < n:
                if src[i] == "\\":
                    out.append("  ")
                    i += 2
                    continue
                if src[i] == quote:
                    out.append(" ")
                    i += 1
                    break
                out.append("\n" if src[i] == "\n" else " ")
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def lire_perimetre(sources: dict[str, str]) -> list[str]:
    """Fichiers du perimetre, DERIVES : ceux qui capturent par runner."""
    return sorted(k for k, v in sources.items() if MARQUEUR_PERIMETRE in v)


def charger_sources() -> dict[str, str]:
    """Chemin relatif POSIX -> contenu, pour tout `frida/hooks/features/**/*.ts`."""
    out: dict[str, str] = {}
    if not FEATURES.is_dir():
        return out
    for p in sorted(FEATURES.rglob("*.ts")):
        out[p.relative_to(ROOT).as_posix()] = io.open(
            p, "r", encoding="utf-8", errors="replace").read()
    return out


def bloc_parametres(src: str, pos_ouvrante: int) -> str:
    """Texte entre la parenthese ouvrante `pos_ouvrante` et sa fermante appariee."""
    prof, i, n = 0, pos_ouvrante, len(src)
    while i < n:
        if src[i] == "(":
            prof += 1
        elif src[i] == ")":
            prof -= 1
            if prof == 0:
                return src[pos_ouvrante + 1:i]
        i += 1
    return src[pos_ouvrante + 1:]


RE_RPC = re.compile(r"ctx\.rpc\.(\w+)\s*=\s*\(")


def rpcs_armement(src_nu: str) -> list[tuple[str, str]]:
    """(nom, bloc de parametres) des RPC d'ARMEMENT declares dans ce source."""
    out = []
    for m in RE_RPC.finditer(src_nu):
        nom = m.group(1)
        if not nom.endswith(SUFFIXES_ARMEMENT):
            continue
        out.append((nom, bloc_parametres(src_nu, m.end() - 1)))
    return out


# ------------------------------------------------------------------------- les etages

#: L'IMPORT reel, pas la sous-chaine : `game/armed-runners` apparait AUSSI en PROSE dans
#: les six features (« Cf. game/armed-runners.ts »). Chercher la sous-chaine rendait E1
#: aveugle a la suppression de l'import -- mesure faite : le mutant E1 passait au VERT.
RE_IMPORT_FOYER = re.compile(r'from\s+"[^"]*armed-runners\.js"')


def etage1_consulte_origine(sources: dict[str, str], perim: list[str]) -> list[str]:
    """Toute feature du perimetre importe ET utilise le predicat du foyer."""
    ecarts = []
    for f in perim:
        nu = denuder_ts(sources[f])
        if not RE_IMPORT_FOYER.search(sources[f]):
            ecarts.append("%s : n'IMPORTE PAS %s -- sa porte ne peut pas voir l'origine"
                          % (f, MODULE_FOYER))
            continue
        if PREDICAT_FOYER not in nu:
            ecarts.append("%s : importe le foyer mais n'appelle jamais `%s`"
                          % (f, PREDICAT_FOYER))
    return ecarts


#: ⚠ Le receveur n'est PAS force d'etre un identifiant : `(trace as {on: boolean}).on = false`
#: est la meme faute, ecrite pour passer sous un `\w+`. Mesure faite : le mutant caste
#: passait au VERT avec `\b(\w+)\.`. On accepte donc `)`/`]` comme receveur.
RE_PORTE_ASSIGNEE = re.compile(r"(\w+|\)|\])\s*\.\s*(on|enabled)\s*=\s*(?!=)")


def etage2_pas_de_booleen_de_module(sources: dict[str, str],
                                    perim: list[str]) -> list[str]:
    """Aucune AFFECTATION de porte (`x.on = `, `x.enabled = `) dans le perimetre."""
    ecarts = []
    for f in perim:
        nu = denuder_ts(sources[f])
        for i, ligne in enumerate(nu.splitlines(), start=1):
            m = RE_PORTE_ASSIGNEE.search(ligne)
            if m:
                ecarts.append("%s:%d : porte REASSIGNEE `%s.%s = ` -- un booleen de module, "
                              "pas un accesseur sur l'origine" % (f, i, m.group(1), m.group(2)))
    return ecarts


def etage3_rpc_prennent_runnerid(sources: dict[str, str],
                                 perim: list[str]) -> tuple[list[str], int]:
    """Tout RPC d'armement du perimetre DECLARE un `runnerId`. Rend (ecarts, nb vus)."""
    ecarts, vus = [], 0
    for f in perim:
        nu = denuder_ts(sources[f])
        for nom, params in rpcs_armement(nu):
            vus += 1
            if "runnerId" not in params:
                ecarts.append("%s : `ctx.rpc.%s` n'accepte PAS de runnerId -- l'appelant "
                              "n'a aucun moyen de scoper son armement" % (f, nom))
    return ecarts, vus


RE_COMMENTAIRE_PY = re.compile(r"^\s*#")


def bloc_appel_py(txt: str, pos: int) -> str:
    """L'APPEL qui contient la position `pos`, parentheses APPARIEES.

    ⚠ Ce decoupage exact remplace une fenetre de 3 lignes, qui rendait un FAUX VERT
    MESURE : dans `probe_462r4ar1`, la ligne qui suit `effectBonusTraceOff {}` est
    `capture["runnerId"] = rid` -- le mot `runnerId` etait donc dans la fenetre sans
    etre un ARGUMENT de l'appel. Une fenetre par LIGNES ne peut pas distinguer les deux ;
    seul l'appariement des parentheses le peut.
    """
    prof, i = 0, pos
    while i >= 0:                       # remonte a la `(` ouvrante de CET appel
        if txt[i] == ")":
            prof += 1
        elif txt[i] == "(":
            if prof == 0:
                break
            prof -= 1
        i -= 1
    if i < 0:
        return ""
    debut, prof, j, n = i, 0, i, len(txt)
    while j < n:                        # descend a sa fermante appariee
        if txt[j] == "(":
            prof += 1
        elif txt[j] == ")":
            prof -= 1
            if prof == 0:
                return txt[debut:j + 1]
        j += 1
    return txt[debut:]


def etage4_sites_python(noms_rpc: set[str],
                        sources_py: dict[str, str]) -> tuple[list[str], int]:
    """Tout site Python qui arme/desarme passe un runnerId, ou l'ASSUME explicitement."""
    ecarts, vus = [], 0
    motifs = {n: re.compile(r'"%s"\s*[,)]' % re.escape(n)) for n in noms_rpc}
    for f, txt in sorted(sources_py.items()):
        lignes = txt.splitlines()
        for nom, rx in motifs.items():
            for m in rx.finditer(txt):
                ligne_no = txt.count("\n", 0, m.start()) + 1
                if RE_COMMENTAIRE_PY.match(lignes[ligne_no - 1]):
                    continue
                vus += 1
                if "runnerId" in bloc_appel_py(txt, m.start()):
                    continue
                # Echappatoire CONSCIENTE : le site DIT qu'il arme globalement.
                amont = "\n".join(lignes[max(0, ligne_no - 11):ligne_no - 1])
                if MARQUEUR_GLOBAL_ASSUME in amont:
                    continue
                ecarts.append("%s:%d : `%s` sans runnerId et sans marqueur `%s`"
                              % (f, ligne_no, nom, MARQUEUR_GLOBAL_ASSUME))
    ecarts.sort()
    return ecarts, vus


def charger_sources_py() -> dict[str, str]:
    out: dict[str, str] = {}
    if not PY_DIR.is_dir():
        return out
    for p in sorted(PY_DIR.rglob("*.py")):
        if p.name == Path(__file__).name:
            continue
        out[p.relative_to(ROOT).as_posix()] = io.open(
            p, "r", encoding="utf-8", errors="replace").read()
    return out


# ---------------------------------------------------------------------------- mutants

def _muter(sources: dict[str, str], cible: str, avant: str, apres: str) -> dict[str, str]:
    mute = dict(sources)
    if avant not in mute.get(cible, ""):
        raise AssertionError("mutant impossible : %r absent de %s" % (avant[:60], cible))
    mute[cible] = mute[cible].replace(avant, apres, 1)
    return mute


def jouer_mutants(sources: dict[str, str], perim: list[str],
                  sources_py: dict[str, str], noms_rpc: set[str]) -> list[str]:
    """Chaque etage recoit une mutation qui doit le faire ROUGIR. Rend les etages MUETS."""
    muets = []
    cible = "frida/hooks/features/scorer-damage-trace.ts"
    if cible not in perim:
        raise AssertionError("mutant : %s hors perimetre -- la mutation ne prouverait rien"
                             % cible)

    # E1 : on retire l'import du foyer.
    m1 = _muter(sources, cible,
                'import { arm, disarm, capturing, armedReport } from "../game/armed-runners.js";',
                "// (mutant #483 : import du foyer retire)")
    if not etage1_consulte_origine(m1, perim):
        muets.append("E1 est MUET : l'import du foyer retire ne le fait pas rougir")

    # E2 : on reintroduit une affectation de porte -- SOUS DEUX FORMES. La forme directe est
    # la faute historique ; la forme CASTEE est celle qu'ecrirait quelqu'un qui contourne le
    # `readonly`. Un cliquet qui n'attrape que la premiere se laisse contourner par la
    # seconde -- et c'est exactement ce qu'il faisait avant cette mesure.
    ancre = "    ctx.rpc.scorerDamageTraceOff = (body?: { runnerId?: number }): unknown => {"
    for etiquette, faute in (
        ("directe", "        trace.on = false;   // mutant #483"),
        ("castee", "        (trace as { on: boolean }).on = false;   // mutant #483"),
    ):
        m2 = _muter(sources, cible, ancre, ancre + "\n" + faute)
        if not etage2_pas_de_booleen_de_module(m2, perim):
            muets.append("E2 est MUET sur la forme %s : `%s` ne le fait pas rougir"
                         % (etiquette, faute.strip()))

    # E3 : on retire le runnerId de la signature d'un RPC d'armement.
    m3 = _muter(sources, cible,
                "ctx.rpc.scorerDamageTraceOn = (body?: { runnerId?: number }): Promise<unknown> =>",
                "ctx.rpc.scorerDamageTraceOn = (): Promise<unknown> =>")
    if not etage3_rpc_prennent_runnerid(m3, perim)[0]:
        muets.append("E3 est MUET : une signature sans runnerId ne le fait pas rougir")

    # E4 : un site Python perd son runnerId.
    cible_py = "scripts/python/probe_212_spiritual_leader_tile_term.py"
    m4 = _muter(sources_py, cible_py,
                '_r(sid, "scorerDamageTraceOn", {"runnerId": rid}, 90)',
                '_r(sid, "scorerDamageTraceOn", {}, 90)')
    if not etage4_sites_python(noms_rpc, m4)[0]:
        muets.append("E4 est MUET : un site Python sans runnerId ne le fait pas rougir")

    return muets


# ------------------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mutant", action="store_true",
                    help="joue les mutations qui doivent faire rougir chaque etage")
    ap.add_argument("--verbeux", action="store_true")
    a = ap.parse_args()

    print("=== #483 : la porte d'armement d'une capture PAR RUNNER ===\n")

    sources = charger_sources()
    if not sources:
        print("NON MESURE : `%s` introuvable ou vide -- rien a auditer."
              % FEATURES.relative_to(ROOT).as_posix())
        return 3
    perim = lire_perimetre(sources)
    print("E0  PERIMETRE (derive : fichiers portant `%s`) : %d / %d features"
          % (MARQUEUR_PERIMETRE, len(perim), len(sources)))
    for f in perim:
        print("      %s" % f)
    if not perim:
        # Assertion de NON-VIDE : un perimetre vide rendrait tous les etages verts pour
        # rien. C'est le controle qui a sauve d'autres cliquets (#270-r1-r1-r3).
        print("\nNON MESURE : perimetre VIDE -- aucune feature ne capture par runner ?")
        return 3

    sources_py = charger_sources_py()
    noms_rpc: set[str] = set()
    for f in perim:
        for nom, _ in rpcs_armement(denuder_ts(sources[f])):
            noms_rpc.add(nom)
    if not noms_rpc:
        print("\nNON MESURE : aucun RPC d'armement trouve dans le perimetre.")
        return 3
    print("\n    RPC d'armement DERIVES (suffixes %s) : %d"
          % ("/".join(SUFFIXES_ARMEMENT), len(noms_rpc)))
    if a.verbeux:
        for n in sorted(noms_rpc):
            print("      %s" % n)

    rouges: list[str] = []

    e1 = etage1_consulte_origine(sources, perim)
    print("\nE1  la porte CONSULTE l'origine : %s" % ("OK" if not e1 else "ROUGE"))
    rouges += e1

    e2 = etage2_pas_de_booleen_de_module(sources, perim)
    print("E2  aucune porte REASSIGNEE (booleen de module) : %s"
          % ("OK" if not e2 else "ROUGE"))
    rouges += e2

    e3, vus3 = etage3_rpc_prennent_runnerid(sources, perim)
    print("E3  les RPC d'armement declarent un runnerId : %s (%d RPC vus)"
          % ("OK" if not e3 else "ROUGE", vus3))
    if vus3 == 0:
        print("\nNON MESURE : E3 n'a vu AUCUN RPC d'armement -- il ne peut rien conclure.")
        return 3
    rouges += e3

    if not sources_py:
        print("E4  sites Python : NON MESURE (`scripts/python` introuvable)")
        return 3
    e4, vus4 = etage4_sites_python(noms_rpc, sources_py)
    print("E4  les sites Python passent leur runnerId : %s (%d sites vus)"
          % ("OK" if not e4 else "ROUGE", vus4))
    if vus4 == 0:
        print("\nNON MESURE : E4 n'a vu AUCUN site d'appel Python -- il ne peut rien conclure.")
        return 3
    rouges += e4

    if a.mutant:
        print("\n--- MUTANTS (chaque etage doit ROUGIR) ---")
        muets = jouer_mutants(sources, perim, sources_py, noms_rpc)
        for m in muets:
            print("  %s" % m)
        if muets:
            print("\nROUGE : %d etage(s) MUET(S) -- le cliquet ne garde rien." % len(muets))
            return 1
        print("  E1/E2/E3/E4 rougissent tous sous mutation.")

    if rouges:
        print("\nROUGE -- %d ecart(s) :" % len(rouges))
        for r in rouges:
            print("  %s" % r)
        print("\nUne capture PAR RUNNER dont la porte est GLOBALE se fait desarmer par le")
        print("`finally` du voisin, et dumpe un seau TRONQUE sans erreur. Cf. #483 et")
        print("`frida/hooks/game/armed-runners.ts`.")
        return 1

    print("\nVERT : %d feature(s) du perimetre, %d RPC d'armement, %d site(s) Python."
          % (len(perim), vus3, vus4))
    return 0


if __name__ == "__main__":
    sys.exit(main())
