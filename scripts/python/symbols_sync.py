#!/usr/bin/env python3
"""GARDE de synchronisation : build installe <-> `data/symbols/<HASH>` <-> binaire charge par ghidra-mcp.

POURQUOI (residu #103 / O1) -- la procedure existait, la GARDE non
-------------------------------------------------------------------
`CLAUDE.md` et le skill d'orchestration decrivent trois etapes MANUELLES a passer apres une
mise a jour du jeu. Rien ne les verifiait : `ghidra_symbols.py build` se contentait
d'IMPRIMER le hash charge, sans le comparer a quoi que ce soit, et le hook `SessionStart`
ne regardait aucun hash. Le garde-fou etait documentaire -- c'est-a-dire inexistant des que
quelqu'un ne le lit pas.

Ce qui EXISTAIT deja, mais sur un AUTRE axe : `il2cpp_provenance.assert_matches` est
fail-closed et consomme par `preprocess_il2cpp_dump.py` et `GhidraApplyIl2CppSymbols.java`.
Mais son defaut visait `data/il2cpp_{methods,classes,enums}.tsv` -- des fichiers qui
N'EXISTENT PLUS depuis que les tables sont versionnees sous `data/symbols/<HASH>/`. La
verification par defaut ne verifiait donc plus rien.

LES TROIS AXES, ET CE QUE CHACUN ATTRAPE
----------------------------------------
1. **binaire installe <-> tables versionnees** (sha256, pivot de la provenance). Attrape la
   mise a jour du jeu non suivie d'un re-dump : toute RVA lue devient fausse.
2. **coherence INTERNE des tables** : nom du repertoire == fichier `BUILD` == champ `build=`
   de l'estampille == en-tete `# build=` de la table Ghidra. Attrape un repertoire renomme a
   la main, ou une table Ghidra extraite d'un autre projet que les TSV Frida d'a cote.
3. **ghidra-mcp <-> tables versionnees**. C'EST LE PLUS SILENCIEUX : si le serveur sert encore
   l'ANCIEN projet pendant que les tables sont celles du NOUVEAU build, un agent **decompile un
   binaire et cite les symboles d'un autre**, et rien ne proteste -- les deux reponses sont
   plausibles separement, incoherentes ensemble.

L'axe 3 exige un serveur allume (lancement MANUEL, `start-ghidra-mcp.ps1`). Serveur eteint
n'est PAS un echec -- mais ce n'est PAS un succes non plus : c'est rapporte comme NON VERIFIE.
Taire la difference reproduirait exactement le defaut qu'on corrige.

SORTIE : 0 = tout ce qui etait verifiable est SYNCHRONE ; 1 = DESYNCHRONISATION (ou artefact
illisible). ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

from il2cpp_provenance import (ProvenanceError, assert_matches, installed_dll,  # noqa: E402
                               read_stamp, sha256_of)
from symbols_layout import LayoutError, archived_builds, build_dir as _build_dir  # noqa: E402

SYMBOLS = REPO / "data" / "symbols"
FRIDA_TABLES = ("classes.tsv", "enums.tsv", "methods.tsv")


class Desync(RuntimeError):
    """Incoherence AVEREE entre deux artefacts -- toujours bloquante."""


def versioned_build() -> Path:
    """Le repertoire du build qui FAIT FOI, designe par `data/symbols/CURRENT`.

    CHANGE le 2026-07-29 : cette fonction exigeait auparavant qu'il n'y ait QU'UN SEUL
    repertoire, et prescrivait de SUPPRIMER l'ancien apres une MAJ. Mauvais marche -- la
    multiplicite n'etait qu'un PROXY d'ambiguite, alors que l'axe 1 sait deja trancher
    EXACTEMENT par sha256. On garde donc tous les builds (leur diff est le rapport de
    changement du jeu, et il doit rester consultable APRES la fenetre de migration) et on
    nomme explicitement celui qui fait foi. Detail : `symbols_layout.py`."""
    try:
        return _build_dir()
    except LayoutError as e:
        raise Desync(str(e)) from e


def axe1_binaire(build_dir: Path, dll: Path) -> list[str]:
    """sha256 du binaire installe contre l'estampille de CHAQUE table Frida."""
    lignes = []
    for nom in FRIDA_TABLES:
        p = build_dir / "frida" / nom
        st = assert_matches(p, dll)        # leve ProvenanceError si absent / illisible / discordant
        lignes.append("  OK  frida/%-12s sha256 == binaire installe (genere %s)"
                      % (nom, st.get("generated", "?")))
    return lignes


def axe2_coherence(build_dir: Path) -> list[str]:
    """Nom du repertoire, fichier BUILD, champ `build=` des estampilles, en-tete Ghidra."""
    attendu = build_dir.name
    lignes = []

    marqueur = build_dir / "BUILD"
    if not marqueur.is_file():
        raise Desync("%s/BUILD absent -- le hash n'est ecrit nulle part en clair" % attendu)
    vu = marqueur.read_text(encoding="utf-8").strip()
    if vu != attendu:
        raise Desync("BUILD dit '%s' mais le repertoire s'appelle '%s'" % (vu, attendu))
    lignes.append("  OK  BUILD == nom du repertoire (%s)" % attendu)

    for nom in FRIDA_TABLES:
        st = read_stamp(build_dir / "frida" / nom)
        if st.get("build") != attendu:
            raise Desync("frida/%s est estampillee build=%s, rangee sous %s"
                         % (nom, st.get("build"), attendu))

    ghidra = build_dir / "ghidra" / "functions.tsv"
    if not ghidra.is_file():
        raise Desync(
            "%s/ghidra/functions.tsv absent -- les frontieres de fonctions manquent.\n"
            "  Sans elles, aucune adresse ne se resout en `<symbole>+0x<offset>`.\n"
            "  L'extraire : python scripts/python/ghidra_symbols.py dump" % attendu)
    entete = ghidra.open(encoding="utf-8").readline()
    if ("build=%s" % attendu) not in entete:
        raise Desync(
            "ghidra/functions.tsv n'annonce pas build=%s dans son en-tete : %r\n"
            "  Table Ghidra et tables Frida ne viennent pas du meme build -- c'est exactement\n"
            "  la configuration ou l'on decompile un binaire en citant les symboles d'un autre."
            % (attendu, entete[:120]))
    lignes.append("  OK  estampilles frida + en-tete ghidra == %s" % attendu)
    return lignes


def axe3_ghidra(build_dir: Path, timeout: float) -> tuple[list[str], bool]:
    """Build REELLEMENT charge par ghidra-mcp. Serveur eteint => non verifie, PAS un succes."""
    try:
        import ghidra_symbols as G
    except ImportError as exc:
        return (["  ??  ghidra: client indisponible (%s) -- axe NON VERIFIE" % exc], False)
    GhidraDown = G.GhidraDown
    try:
        # Attente BORNEE : le defaut du client est 120 s (dimensionne pour un `dump` pagine).
        # Ici on ne fait qu'interroger, et l'appelant peut etre un hook de demarrage de session
        # -- un serveur a moitie mort ne doit pas le retenir deux minutes.
        charge = G.loaded_build(G.GhidraMCP(timeout=timeout).connect())
    except GhidraDown:
        return (["  ??  ghidra-mcp ETEINT -- axe NON VERIFIE (lancement manuel :",
                 "      pwsh -File C:\\Users\\nicolasv\\ghidra-mcp\\start-ghidra-mcp.ps1)"], False)
    except Exception as exc:                                    # noqa: BLE001
        return (["  ??  ghidra-mcp injoignable (%s) -- axe NON VERIFIE" % type(exc).__name__],
                False)
    if charge != build_dir.name:
        raise Desync(
            "ghidra-mcp a charge le build '%s', les tables versionnees sont '%s'.\n"
            "  Un agent RE lance maintenant DECOMPILERAIT un binaire en citant les symboles\n"
            "  d'un autre -- chaque reponse plausible seule, incoherentes ensemble.\n"
            "  Relancer le serveur sur le bon projet AVANT tout agent RE."
            % (charge, build_dir.name))
    return (["  OK  ghidra-mcp a charge %s == tables versionnees" % charge], True)


# Combien de citations distinctes echantillonner, et combien doivent resolver. Le seuil est
# volontairement TRES BAS : la panne visee est TOTALE (mesure du 2026-07-29 : 0 sur 1 266), pas
# graduelle. Un seuil bas ne peut donc pas crier au loup sur la derive normale d'une MAJ
# (81,9 % conservees ce jour-la), et attrape quand meme le desastre.
ECHANTILLON = 400
PLANCHER_PCT = 10.0
# MARGE MESUREE le 2026-07-29 : regime sain = 27 % (114/420), panne simulee = 0 %. Les 73 %
# qui ne resolvent pas en regime sain sont des citations en forme COURTE (sans namespace), qui
# ne resolvent JAMAIS -- ce n'est pas de la derive. Pour qu'un faux positif survienne, une MAJ
# devrait effacer les deux tiers des symboles reellement resolvables, ce qui meriterait l'alerte.

_CITE = re.compile(r"[A-Za-z_][\w.`]*\$\$[\w.`]+")


def axe4_forme(build_dir: Path) -> list[str]:
    """La table parle-t-elle la MEME LANGUE que les citations du depot ?

    POURQUOI CET AXE EXISTE (incident du 2026-07-29)
    ------------------------------------------------
    Les axes 1 a 3 verifient tous la PROVENANCE : sha256 du binaire, coherence des estampilles,
    build charge par le serveur. AUCUN ne regarde le CONTENU. Ce jour-la, la table produite pour
    le nouveau build etait en notation POINTEE (`Classe.Methode`) au lieu de `Classe$$Membre` :
    parfaitement estampillee, du bon build, servie par le bon serveur -- et INTEGRALEMENT
    inexploitable. Zero citation sur 1 266 resolvait, et le diff inter-build affichait 0,43 % de
    symboles communs, ce qui imitait une reecriture totale du jeu.

    La cause n'etait pas la MAJ mais un CHANGEMENT D'OUTILLAGE : le retrait de l'applier
    Il2CppDumper le 2026-07-25 sans re-jouer l'aval. L'ancienne sortie a continue de faire foi
    quatre jours, jusqu'a la premiere re-symbolisation complete.

    CE QU'IL NE FAUT PAS EN FAIRE : un thermometre de la derive inter-build. Pour cela il y a
    `probe_251_citation_resolution.py`, qui mesure proprement contre une population de reference.
    Ici on ne repond qu'a UNE question binaire : la table est-elle lisible du tout ?"""
    table = build_dir / "ghidra" / "functions.tsv"
    symboles = set()
    with table.open(encoding="utf-8") as fh:
        for ligne in fh:
            if ligne.startswith("#"):
                continue
            parts = ligne.rstrip("\n").split("\t")
            if len(parts) >= 2:
                symboles.add(parts[1])

    vues: set[str] = set()
    for f in sorted((REPO / "scripts" / "python" / "engine").rglob("*.py")):
        try:
            for m in _CITE.findall(f.read_text(encoding="utf-8", errors="replace")):
                vues.add(m)
        except OSError:
            continue
        if len(vues) >= ECHANTILLON:
            break

    if not vues:
        return ["  ??  aucune citation `$$` trouvee dans engine/ -- axe NON VERIFIE"]

    n = sum(1 for s in vues if s in symboles)
    pct = 100.0 * n / len(vues)
    if pct < PLANCHER_PCT:
        raise Desync(
            "la table ne parle PAS la langue des citations du depot : %d / %d resolvent (%.1f %%).\n"
            "  Ce n'est PAS une derive de mise a jour -- c'est une table INEXPLOITABLE.\n"
            "  Verifier la FORME avant tout : grep -c '\\$\\$' %s\n"
            "  Attendu `Namespace.Classe$$Membre` (chevrons echappes u003C/u003E), produit par\n"
            "  GhidraApplyIl2CppSymbols.canonicalName. Si la table est en notation pointee, c'est\n"
            "  l'applier qu'il faut corriger PUIS re-jouer -- re-dumper ne changera rien."
            % (n, len(vues), pct, table.as_posix()))
    return ["  OK  forme des symboles : %d / %d citations echantillonnees resolvent (%.0f %%)"
            % (n, len(vues), pct)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quiet", action="store_true",
                    help="n'imprimer QUE si desynchronise (mode hook de session)")
    ap.add_argument("--skip-ghidra", action="store_true",
                    help="ne pas interroger ghidra-mcp (axes 1 et 2 seuls)")
    ap.add_argument("--ghidra-timeout", type=float, default=10.0,
                    help="secondes d'attente max pour ghidra-mcp (defaut 10 ; ~230 ms mesure "
                         "serveur sain). Depasse = axe NON VERIFIE, jamais un faux vert")
    args = ap.parse_args()

    lignes, ghidra_vu = [], False
    try:
        build_dir = versioned_build()
        dll = installed_dll()
        lignes += axe1_binaire(build_dir, dll)
        lignes += axe2_coherence(build_dir)
        lignes += axe4_forme(build_dir)
        if args.skip_ghidra:
            lignes.append("  --  ghidra: non interroge (--skip-ghidra)")
        else:
            l3, ghidra_vu = axe3_ghidra(build_dir, args.ghidra_timeout)
            lignes += l3
    except (Desync, ProvenanceError) as exc:
        print("SYMBOLES DESYNCHRONISES -- toute analyse offline est FAUSSE tant que ce n'est pas regle")
        print("  " + str(exc).replace("\n", "\n  "))
        print("  Procedure de remise a niveau : CLAUDE.md, section « Au changement de build »")
        return 1

    if args.quiet and ghidra_vu:
        return 0                        # tout verifie et synchrone : le hook se tait
    print("symboles SYNCHRONES  build=%s  binaire=%s..."
          % (build_dir.name, sha256_of(dll)[:12]))
    for l in lignes:
        print(l)
    # Les autres builds sont des ARCHIVES conservees EXPRES : leur diff contre le build courant
    # est le rapport de changement du jeu, et il doit rester consultable bien apres la fenetre
    # de migration. On les nomme pour qu'ils soient VUS -- ce n'est pas un avertissement.
    autres = archived_builds()
    if autres:
        print("  --  %d build(s) archive(s) : %s (conserves pour le diff inter-build)"
              % (len(autres), ", ".join(autres)))
    if not ghidra_vu and not args.skip_ghidra:
        print("  ATTENTION : l'axe ghidra n'a PAS ete verifie -- ne pas lancer d'agent RE sans")
        print("  l'avoir confronte (c'est l'axe qui echoue le plus silencieusement).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
