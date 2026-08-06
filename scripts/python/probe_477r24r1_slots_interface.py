"""#477-r24-r1 -- le mapping slot <-> methode de `Core.Services.IOperationProcessor`.

    python scripts/python/probe_477r24r1_slots_interface.py
    python scripts/python/probe_477r24r1_slots_interface.py --regenerer
    python scripts/python/probe_477r24r1_slots_interface.py --mutants

CE QUE CE PROBE TRANCHE
-----------------------
Deux lectures publiees se contredisaient sur ce mapping. Elles etaient TOUTES LES DEUX
JUSTES : leurs slots concordent avec le metadata. Ce qui etait faux, c'est la grandeur
intermediaire par laquelle on les comparait -- une « position dans la classe », qui n'indexe
RIEN. Le slot d'interface est un rang dans la table de l'INTERFACE ; la position d'une methode
dans le dump de la CLASSE est un tout autre ordre, et le « decalage » entre les deux n'a aucune
raison d'etre constant. Deux decalages locaux differents ne sont donc PAS une contradiction.

Detail : `docs/rl/case-477r24r1-mapping-slot-interface.md`.

LES QUATRE ETAGES
-----------------
1. DERIVATION -- relit le `slot` dans `global-metadata.dat` (via `il2cpp_metadata`, qui localise
   les tables PAR CONTENU, sans lire le header). Tri-etat : metadata absent ou desynchronise
   => `PAS MESURE`, jamais un zero ni un vert.
2. CLIQUET -- confronte la derivation a l'entree VERSIONNEE
   `data/symbols/<build>/metadata/ioperationprocessor_slots.tsv`. C'est elle qui rend les
   etages 3 et 4 jouables dans un worktree frais, ou le jeu n'est pas forcement installe.
3. CITATIONS -- balaie le depot et confronte CHAQUE citation « slot X = NomDeMethode » portant
   sur cet OperationProcessor. Perimetre DERIVE : on visite tous les fichiers, on extrait toutes
   les citations de slot, et ce qui est ECARTE est COMPTE ET IMPRIME (une citation de slot vise
   le plus souvent une AUTRE interface -- `battleQuery`, `attackQuery`, un effet -- et le seul
   discriminant fiable est le RECEPTEUR ecrit au site).
4. ARITE -- quand la citation montre ses arguments, les compte et les confronte au
   `param_count` du metadata. C'est le cran qui a effectivement trouve la faute de #477-r24-r2 :
   `RemoveUnit` prend 3 arguments, le site n'en passe que 2.

CE QUE CE PROBE NE VOIT PAS, ET C'EST DIT
-----------------------------------------
* les citations de slot SANS nom de methode (« slot 0x55 `(entity, false)` ») : il n'y a rien a
  contredire, donc rien a garder. Elles sont COMPTEES et imprimees sous `SANS NOM` ;
* les slots des AUTRES interfaces (`IBattleQuery`, `IAttackQuery`, `IMatchState`, les effets).
  Ils sont ecartes, comptes, et c'est le residu #477-r25 ;
* la PROSE : « le processeur retire l'unite » ne porte aucun slot.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_pin                                                        # noqa: E402
import il2cpp_metadata                                                  # noqa: E402
from symbols_layout import build_dir, current_build                     # noqa: E402

REPO = HERE.parent.parent

#: La classe qui IMPLEMENTE l'interface. Son ordre de methodes, lu cote Frida, sert d'ancre
#: pour localiser la table du metadata -- il n'est PAS la verite (cf. `class_method_order`).
KLASS = "Core.Services.OperationProcessor"

#: Noms de methodes, uniques dans le metadata, portes par l'interface cherchee. Ils fixent le
#: debut de sa table ; s'ils ne designent pas tous le MEME debut, le module REFUSE.
ANCRES = ("ContinueTurnPhase", "VerifyAutomaticTurnEnd", "ReviveUnit", "HealUnit",
          "RunComputerActionsForCurrentPlayer", "MarkUnitAsNoActionAvailable")

#: L'entree versionnee, relative a `data/symbols/<build>/`.
TSV_REL = ("metadata", "ioperationprocessor_slots.tsv")

#: Les fichiers balayes a l'etage 3. Perimetre DERIVE d'un `git ls-files`, jamais d'une liste.
BALAYAGE_GLOBS = ("docs/rl/*.md", "docs/*.md", "scripts/python/*.py",
                  "scripts/python/tests/**/*.py", "engine/**/*.py", "frida/hooks/**/*.ts")

#: Un slot cite. Toutes les formes que le depot ecrit :
#:   `<slot 0x16>`, `slot 0x16`, `slot **0x16**`, `slot `0x16``, `slot +6`, `slot 6`, `vslot`
_SLOT = r"v?slot\s*(?:d'interface\s*)?[`*]{0,2}\+?(?P<n%d>0x[0-9a-fA-F]+|\d+)[`*]{0,2}"

#: Le RECEPTEUR ecrit au site -- seul discriminant fiable de l'interface visee.
RE_RECEVEUR = re.compile(r"IOperationProcessor|OperationProcessor|(?<![A-Za-z])processor\s*\.")

#: Un nom de methode RATTACHE a cet OperationProcessor : symbole natif verbatim, acces pointe,
#: ou `$$Nom` isole (le `$$` non precede d'un identifiant, sinon `KillUnitOperation$$Execute`
#: passerait pour la methode `Execute` de l'interface).
_QUAL = (r"(?:(?:[A-Za-z0-9_.]*\.)?I?OperationProcessor(?:\$\$|\.)|(?<![A-Za-z])processor\."
         r"|(?<![A-Za-z0-9_])\$\$)")
#: Un nom SUIVI de `$$` est un nom de CLASSE (`FinishAttackOperation$$Execute`), pas une methode
#: de l'interface -- le rejeter est ce qui separe l'attestation de la chaine d'appel citee.
#: La classe negative doit inclure les CARACTERES DE MOT, sinon le moteur backtracke et rend un
#: nom TRONQUE qui, lui, n'est plus suivi de `$$` (mesure : `FinishAttackOperatio`).
_NOM = r"(?P<nom%d>[A-Z][A-Za-z0-9]{3,})(?![A-Za-z0-9$])"
#: Rien d'autre ne doit s'intercaler entre le slot et son nom -- ni un AUTRE `slot`, ni une
#: parenthese FERMANTE. Sans la premiere exclusion, `... StartAttack slot 0x3a -> ...
#: FinishAttack slot 0x3b ...` attribue le nom du second au premier ; sans la seconde,
#: `$$StartAttack` (slot 0x3a) avant CHAQUE cible / `$$FinishAttack`' saute par-dessus la
#: fermeture et attrape le nom de la PROPOSITION SUIVANTE. Les deux faux positifs sont mesures.
_ENTRE = r"(?:(?!slot)[^\n)]){0,%d}?"

#: LES TROIS FORMES DE COUPLE (slot, nom) RETENUES COMME ATTESTATION. Un nom simplement PRESENT
#: sur la ligne ne compte pas : il faut qu'il soit ADJACENT au slot. Sans cette contrainte, une
#: ligne de `backlog.md` fournit trente « noms » et le controle devient du bruit (mesure : 32
#: desaccords, 30 faux).
RE_COUPLES = (
    #: A -- `slot 0x7e = MoveUnit`, `slot **0x43** = `OperationProcessor$$ApplyDamage``
    re.compile((_SLOT % 0) + r"\s*(?:=|->|:)\s*[`*]{0,2}(?:" + _QUAL + r")?" + (_NOM % 0)),
    #: B -- `processor.FinishAttack` slot 0x3b   (nom PUIS slot, colles)
    re.compile(_QUAL + (_NOM % 1) + (_ENTRE % 40) + (_SLOT % 1)),
    #: C -- slot 0x3a ... `OperationProcessor$$StartAttack`   (slot PUIS nom, colles)
    re.compile((_SLOT % 2) + (_ENTRE % 60) + _QUAL + (_NOM % 2)),
)

#: Le probe est EXCLU de son propre balayage : ses regex de documentation contiennent des
#: exemples de syntaxe (`slot 0x7e = MoveUnit`) qui ne sont pas des attributions. Un controle
#: qui rougit sur son propre artefact fait renoncer a des mesures justes. L'exclusion est
#: NOMMEE et imprimee, jamais silencieuse.
EXCLUS = ("scripts/python/probe_477r24r1_slots_interface.py",)

#: L'arite n'est confrontee que si le site montre VRAIMENT ses arguments juste apres le couple
#: (`processor.<slot 0x60>(killer, u, opts)`), jamais sur une parenthese quelconque de la ligne.
#: AUCUNE espace n'est toleree : un appel s'ecrit `Nom(args)`, jamais `Nom (args)` -- sans quoi
#: une parenthese de PROSE (« ... $$EvaluateAbilities` (litteral `0x17`) ») compte pour un argument.
RE_APPEL = re.compile(r"\A[`*>]{0,2}\(")

#: Marqueur d'EXEMPTION au site : une ligne qui CITE une attribution refutee pour la nommer
#: comme telle porte legitimement un couple (slot, nom) faux. Compte et imprime, jamais muet.
MARQUEUR_REFUTE = "[slot-attribution:refute]"


@dataclass(frozen=True)
class Citation:
    fichier: str
    ligne: int
    slot: int
    noms: tuple[str, ...]
    args: int | None
    texte: str


# ------------------------------------------------------------------ etage 1 : DERIVATION


def deriver() -> list[il2cpp_metadata.MethodDef] | None:
    """Les methodes de l'interface indexees par slot, ou `None` si le metadata n'est pas la.

    `None` = PAS MESURE. Ce n'est ni une table vide ni un vert : les appelants doivent le
    distinguer, et l'impression le dit en toutes lettres.
    """
    try:
        meta_path = build_pin.global_metadata()
    except build_pin.BuildPinRefused as exc:
        print("[1] DERIVATION : PAS MESURE -- %s" % str(exc).splitlines()[0])
        return None
    reader = il2cpp_metadata.read(meta_path)
    order = il2cpp_metadata.class_method_order(
        build_dir() / "frida" / "methods.tsv", KLASS)
    reader.locate(order)
    table = reader.interface_table(ANCRES)
    print("[1] DERIVATION : %d slots lus dans le metadata (pas=%d octets), %d ancres concordantes"
          % (len(table), reader.entry_size or 0, len(ANCRES)))
    return table


# --------------------------------------------------------------------- etage 2 : CLIQUET


def tsv_path(build: str | None = None) -> Path:
    return build_dir(build).joinpath(*TSV_REL)


def lire_tsv() -> dict[int, tuple[str, int]]:
    p = tsv_path()
    if not p.is_file():
        raise SystemExit(
            "ROUGE : l'entree versionnee est absente (%s).\n"
            "  La regenerer sur une machine ou le jeu est installe :\n"
            "  python scripts/python/probe_477r24r1_slots_interface.py --regenerer"
            % p.as_posix())
    out: dict[int, tuple[str, int]] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        slot, nom, nargs = line.split("\t")[:3]
        out[int(slot)] = (nom, int(nargs))
    return out


def ecrire_tsv(table: list[il2cpp_metadata.MethodDef]) -> Path:
    p = tsv_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    lignes = [
        "# Core.Services.IOperationProcessor -- slot d'interface -> methode, LU dans le champ",
        "# `slot` d'`Il2CppMethodDefinition` (global-metadata.dat du build %s)." % current_build(),
        "# Entree VERSIONNEE : c'est ce qui rend la garde jouable sans le jeu installe.",
        "# Regenerer : python scripts/python/probe_477r24r1_slots_interface.py --regenerer",
        "#slot\tmethode\tparam_count\tflags",
    ]
    lignes += ["%d\t%s\t%d\t0x%04x" % (m.slot, m.name, m.param_count, m.flags) for m in table]
    p.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return p


def cliquet(table: list[il2cpp_metadata.MethodDef] | None,
            versionne: dict[int, tuple[str, int]]) -> list[str]:
    if table is None:
        print("[2] CLIQUET   : PAS MESURE (pas de derivation a confronter) -- "
              "%d slots dans l'entree versionnee, utilises tels quels par les etages 3-4"
              % len(versionne))
        return []
    ecarts: list[str] = []
    for m in table:
        attendu = versionne.get(m.slot)
        if attendu is None:
            ecarts.append("slot %d (%s) absent de l'entree versionnee" % (m.slot, m.name))
        elif attendu != (m.name, m.param_count):
            ecarts.append("slot %d : metadata %s/%d != versionne %s/%d"
                          % (m.slot, m.name, m.param_count, attendu[0], attendu[1]))
    for slot in sorted(set(versionne) - {m.slot for m in table}):
        ecarts.append("slot %d (%s) versionne mais ABSENT du metadata"
                      % (slot, versionne[slot][0]))
    print("[2] CLIQUET   : %d ecart(s) derivation vs entree versionnee" % len(ecarts))
    for e in ecarts[:20]:
        print("      %s" % e)
    return ecarts


# ------------------------------------------------------------------- etage 3 : CITATIONS


def fichiers_balayes() -> list[Path]:
    try:
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", *BALAYAGE_GLOBS],
                             capture_output=True, text=True, timeout=60, check=True)
    except (OSError, subprocess.SubprocessError) as exc:                # noqa: BLE001
        raise SystemExit("PAS MESURE : `git ls-files` muet (%s) -- le perimetre du balayage "
                         "ne peut pas etre DERIVE, et on n'en invente pas un." % exc)
    return [REPO / rel for rel in out.stdout.split("\0") if rel]


def _compter_args(texte: str, apres: int) -> int | None:
    """Nombre d'arguments du premier appel parenthese apres `apres`, ou None s'il n'y en a pas."""
    ouvre = texte.find("(", apres)
    if ouvre < 0:
        return None
    prof, arg, vus = 0, 0, False
    for ch in texte[ouvre:]:
        if ch in "([<{":
            prof += 1
        elif ch in ")]>}":
            prof -= 1
            if prof == 0:
                return arg + 1 if vus else 0
        elif ch == "," and prof == 1:
            arg += 1
        elif prof == 1 and not ch.isspace():
            vus = True
    return None


def recolter() -> tuple[list[Citation], int, int, int]:
    """(citations retenues, ecartees-autre-interface, sans-couple, exemptees)."""
    retenues: list[Citation] = []
    autre_iface = sans_couple = exemptees = 0
    for path in fichiers_balayes():
        if path.relative_to(REPO).as_posix() in EXCLUS:
            continue
        try:
            texte = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "slot" not in texte:
            continue
        for no, ligne in enumerate(texte.splitlines(), 1):
            if "slot" not in ligne:
                continue
            if not RE_RECEVEUR.search(ligne):
                autre_iface += 1
                continue
            if MARQUEUR_REFUTE in ligne:
                exemptees += 1
                continue
            vus: set[tuple[int, str]] = set()
            for k, rx in enumerate(RE_COUPLES):
                for m in rx.finditer(ligne):
                    slot = int(m.group("n%d" % k), 0)
                    nom = m.group("nom%d" % k)
                    if (slot, nom) in vus:
                        continue
                    vus.add((slot, nom))
                    queue = ligne[m.end():]
                    args = _compter_args(queue, 0) if RE_APPEL.match(queue) else None
                    retenues.append(Citation(
                        fichier=path.relative_to(REPO).as_posix(), ligne=no, slot=slot,
                        noms=(nom,), args=args, texte=ligne.strip()[:150]))
            if not vus:
                sans_couple += 1
    return retenues, autre_iface, sans_couple, exemptees


def confronter(cits: list[Citation], table: dict[int, tuple[str, int]]) -> tuple[list[str], list[str]]:
    faux_nom: list[str] = []
    faux_arite: list[str] = []
    for c in cits:
        attendu = table.get(c.slot)
        if attendu is None:
            faux_nom.append("%s:%d slot %d INCONNU de l'interface (%d slots) | %s"
                            % (c.fichier, c.ligne, c.slot, len(table), c.texte))
            continue
        nom, nargs = attendu
        if nom not in c.noms:
            faux_nom.append("%s:%d slot 0x%x : le site nomme %s, le metadata dit %s | %s"
                            % (c.fichier, c.ligne, c.slot, "/".join(c.noms), nom, c.texte))
            continue
        if c.args is not None and c.args != nargs:
            faux_arite.append("%s:%d slot 0x%x %s : %d argument(s) au site, %d dans la "
                              "signature | %s" % (c.fichier, c.ligne, c.slot, nom, c.args,
                                                  nargs, c.texte))
    return faux_nom, faux_arite


# ------------------------------------------------------------------- contre-epreuve


MUTANTS = {
    "slot-decale": "decale tous les slots de 1 (etage 2 doit MORDRE)",
    "nom-permute": "permute deux noms de la table (etages 2 et 3 doivent MORDRE)",
    "table-tronquee": "coupe la table a 40 slots (etage 3 doit MORDRE)",
    "arite-fausse": "ajoute 1 a tous les param_count (etage 4 doit MORDRE)",
}


def muter(table: dict[int, tuple[str, int]], nom: str,
          cits: list[Citation]) -> dict[int, tuple[str, int]]:
    if nom == "slot-decale":
        return {s + 1: v for s, v in table.items()}
    if nom == "nom-permute":
        #: Les deux slots a permuter sont DERIVES des citations reelles, jamais choisis en dur :
        #: permuter deux slots que personne ne cite rend une contre-epreuve INERTE qui passe
        #: pour mordante (mesure : `22 <-> 99` ne mordait pas -- aucun site ne les nomme).
        attestes = [s for s in dict.fromkeys(c.slot for c in cits) if s in table]
        if len(attestes) < 2:
            raise SystemExit("contre-epreuve IMPOSSIBLE : moins de 2 slots attestes -- "
                             "ce mutant ne peut pas mordre, et on ne le fait pas semblant.")
        out = dict(table)
        a, b = attestes[0], attestes[1]
        out[a], out[b] = out[b], out[a]
        return out
    if nom == "table-tronquee":
        return {s: v for s, v in table.items() if s < 40}
    if nom == "arite-fausse":
        return {s: (n, k + 1) for s, (n, k) in table.items()}
    raise SystemExit("mutant inconnu : %s" % nom)


def jouer(table: dict[int, tuple[str, int]], cits: list[Citation],
          derive: list[il2cpp_metadata.MethodDef] | None) -> tuple[int, int, int]:
    """(ecarts etage 2, noms faux etage 3, arites fausses etage 4) pour cette table."""
    if derive is None:
        ecarts = 0
    else:
        ecarts = sum(1 for m in derive if table.get(m.slot) != (m.name, m.param_count))
    faux_nom, faux_arite = confronter(cits, table)
    return ecarts, len(faux_nom), len(faux_arite)


# ------------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--regenerer", action="store_true",
                    help="reecrit l'entree versionnee depuis le metadata installe")
    ap.add_argument("--mutants", action="store_true",
                    help="contre-epreuve : chaque mutant doit faire MORDRE un etage")
    args = ap.parse_args()

    print("=== #477-r24-r1 -- slots de Core.Services.IOperationProcessor ===")
    print("build qui fait foi : %s" % current_build())

    table = deriver()

    if args.regenerer:
        if table is None:
            raise SystemExit("REFUSE : impossible de regenerer sans metadata (cf. etage 1).")
        p = ecrire_tsv(table)
        print("    entree versionnee reecrite : %s (%d slots)"
              % (p.relative_to(REPO).as_posix(), len(table)))
        print("    NE PAS OUBLIER : `git add %s`" % p.relative_to(REPO).as_posix())
        return 0

    versionne = lire_tsv()
    ecarts = cliquet(table, versionne)

    cits, autre_iface, sans_couple, exemptees = recolter()
    print("[3] CITATIONS : %d attestation(s) (slot ET nom ADJACENTS) sur %d fichier(s)"
          % (len(cits), len({c.fichier for c in cits})))
    print("      ECARTEES, et c'est DIT : %d ligne(s) dont le recepteur ne designe pas cet"
          " OperationProcessor (autre interface)" % autre_iface)
    print("      %d ligne(s) qui citent un slot SANS lui accoler de nom -- rien a contredire,"
          " donc rien a garder" % sans_couple)
    print("      %d ligne(s) exemptees au site par %s" % (exemptees, MARQUEUR_REFUTE))
    print("      %d fichier(s) EXCLU(S) et nomme(s) : %s" % (len(EXCLUS), ", ".join(EXCLUS)))
    faux_nom, faux_arite = confronter(cits, versionne)
    print("      %d citation(s) au NOM faux" % len(faux_nom))
    for f in faux_nom:
        print("        %s" % f)
    print("[4] ARITE     : %d citation(s) dont le compte d'arguments contredit la signature"
          % len(faux_arite))
    for f in faux_arite:
        print("        %s" % f)

    if args.mutants:
        print()
        print("=== CONTRE-EPREUVE (a_mordu est rendu SEPAREMENT du verdict) ===")
        base = jouer(versionne, cits, table)
        for nom, quoi in MUTANTS.items():
            mut = jouer(muter(versionne, nom, cits), cits, table)
            mordu = mut != base
            print("  %-16s a_mordu=%-5s  cliquet %d -> %d, nom %d -> %d, arite %d -> %d   (%s)"
                  % (nom, str(mordu).upper(), base[0], mut[0], base[1], mut[1],
                     base[2], mut[2], quoi))

    rouge = bool(ecarts or faux_nom or faux_arite)
    print()
    print("VERDICT : %s" % ("ROUGE" if rouge else "VERT"))
    if table is None:
        print("  NB : l'etage 1 n'a PAS ete mesure -- ce vert ne dit rien du metadata,")
        print("       seulement que le depot est coherent avec l'entree versionnee.")
    return 1 if rouge else 0


if __name__ == "__main__":
    raise SystemExit(main())
