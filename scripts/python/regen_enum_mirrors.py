#!/usr/bin/env python3
"""#313 -- REPARATEUR des mirrors `IntEnum` du moteur : reecrit leurs membres depuis `enums.tsv`.

POURQUOI UN REPARATEUR, ET PAS SEULEMENT UN CLIQUET
---------------------------------------------------
#275 l'a etabli sur `enum_maps.py` : la derive est ARRIVEE parce que le REPARATEUR etait en
panne (`rl_gen_enum_columns.py` lisait un `dump.cs` Il2CppDumper supprime depuis). Un cliquet qui
rougit sans offrir de reparation pousse a la reparation A LA MAIN -- 476 lignes retranscrites,
c'est-a-dire exactement la transcription approximative qu'on cherche a eliminer.

Ce script est le pendant de `regen_enum_maps.py` pour les mirrors du MOTEUR (`engine/**`), et il
lit la MEME source VERSIONNEE : `data/symbols/<CURRENT>/frida/enums.tsv`. Aucun dump a refaire,
aucune session Frida, aucun RPC.

CE QU'IL PRESERVE, ET POURQUOI C'EST LE POINT DELICAT
------------------------------------------------------
Un mirror n'est pas qu'une table : ses commentaires portent du savoir RE qu'aucune regeneration
ne peut re-deriver ("1545/1548/1551 corriges depuis le RPC live `dumpEnum`", la provenance d'un
membre, une mesure d'inertie). Le script rattache donc chaque commentaire -- bloc precedent ET
commentaire de fin de ligne -- au NOM du membre qu'il documente, et le reinjecte apres
regeneration. Un commentaire rattache a un membre SUPPRIME n'est jamais jete en silence : il est
signale, et c'est a l'humain de decider ou il va.

CE QU'IL NE FAIT PAS
--------------------
  * il ne touche QUE les mirrors STRICTS du registre `probe_313_enum_mirror_bijection.REGISTRE`.
    `StatType` (port UPPER_CASE + abreviations) en est exclu : le regenerer ecraserait une
    convention DELIBEREE par les noms natifs ;
  * il ne choisit jamais entre deux noms d'une meme valeur : si le port porte deja un des noms
    (mesure : 9999 = {STRIPPED, testAssetBundles}, le port dit `testAssetBundles`), il le GARDE ;
  * il ne retire pas un membre a l'aveugle. `probe_313 --porteurs` (etape 3 + etape 4) doit
    d'abord montrer que le nom n'est ni reference `<Classe>.<membre>` dans du Python, ni nomme
    par le gameconfig -- sinon la suppression casse `triggered_ability_ids()`.

Sans `--ecrire` : affiche le diff (membres ajoutes / retires) et ne touche a rien.
ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"/"python"))

import probe_313_enum_mirror_bijection as P  # noqa: E402

PY = REPO / "scripts"/"python"

RX_MEMBRE = re.compile(r"^(\s{4})([A-Za-z_]\w*)\s*=\s*(-?\d+)\s*(#.*)?$")
RX_COMMENT = re.compile(r"^\s{4}#")


def bornes_classe(lignes: list[str], cls: str) -> tuple[int, int]:
    """[premiere, derniere] lignes (0-based, inclusives) du BLOC DE MEMBRES d'une classe.

    Delimite par la premiere et la derniere assignation de membre -- pas par la classe entiere :
    la docstring reste intacte, et tout ce qui suit la classe (fonctions, tables) aussi."""
    deb = next((i for i, l in enumerate(lignes)
                if l.startswith("class %s(" % cls)), -1)
    if deb < 0:
        raise SystemExit("classe %s introuvable" % cls)
    prem, dern = -1, -1
    for i in range(deb + 1, len(lignes)):
        l = lignes[i]
        if RX_MEMBRE.match(l):
            prem = i if prem < 0 else prem
            dern = i
        elif l and not l.startswith(" ") and prem >= 0:
            break
    if prem < 0:
        raise SystemExit("aucun membre dans %s" % cls)
    # remonter sur le bloc de commentaires qui precede le premier membre
    while prem > deb + 1 and RX_COMMENT.match(lignes[prem - 1]):
        prem -= 1
    return prem, dern


def lire_bloc(lignes: list[str], prem: int,
              dern: int) -> tuple[dict[str, tuple[list[str], str]], dict[int, str]]:
    """({nom: (commentaires precedents, commentaire inline)}, {valeur: nom porte par le port})."""
    deco: dict[str, tuple[list[str], str]] = {}
    porte: dict[int, str] = {}
    en_cours: list[str] = []
    for i in range(prem, dern + 1):
        l = lignes[i]
        m = RX_MEMBRE.match(l)
        if m:
            _, nom, val, com = m.groups()
            deco[nom] = (en_cours, (com or "").rstrip())
            porte[int(val)] = nom
            en_cours = []
        elif RX_COMMENT.match(l):
            en_cours.append(l.rstrip())
        elif l.strip() == "":
            en_cours.append("")
    return deco, porte


def _echappe_py(nom: str) -> str:
    """Le jeu dit `None` ; Python en fait un mot-clef -> `None_`. Seul echappement observe."""
    return "None_"if nom =="None" else nom


def regenerer(m: P.Mirror, build: str, ecrire: bool) -> int:
    p = PY / m.rel
    src = p.read_text(encoding="utf-8")
    lignes = src.splitlines()
    prem, dern = bornes_classe(lignes, m.cls)
    deco, porte = lire_bloc(lignes, prem, dern)

    jeu = P.enum_natif(build, m.cle)
    # Choix du nom : celui que le port porte deja s'il est valide (9999 = STRIPPED |
    # testAssetBundles), sinon le premier par ordre alphabetique -- deterministe.
    choisi = {v: (porte[v] if v in porte and P._echappe(porte[v]) in ns else sorted(ns)[0])
              for v, ns in jeu.items()}

    ajoutes = sorted(set(jeu) - set(porte))
    retires = sorted(set(porte) - set(jeu))
    corriges = sorted(v for v in set(porte) & set(jeu)
                      if P._echappe(porte[v]) not in jeu[v])

    out: list[str] = []
    for v in sorted(jeu):
        nom = _echappe_py(choisi[v])
        avant, inline = deco.get(nom, ([], ""))
        out.extend(x for x in avant if x != "" or out)   # jamais de ligne vide en tete de bloc
        out.append("    %s = %d%s" % (nom, v, ("" + inline) if inline else ""))

    orphelins = [(n, deco[n][0], deco[n][1]) for n in deco
                 if n not in {_echappe_py(choisi[v]) for v in jeu}
                 and (deco[n][0] or deco[n][1])]

    print("  %-22s ajoutes=%d retires=%d noms corriges=%d" % (m.cls, len(ajoutes), len(retires),
                                                              len(corriges)))
    for v in ajoutes:
        print("      + %-6d %s" % (v, choisi[v]))
    if retires:
        print("      - %d membre(s) retire(s) : %s%s"
              % (len(retires), ", ".join("%d=%s" % (v, porte[v]) for v in retires[:10]),
                 " ..."if len(retires) > 10 else""))
    for v in corriges:
        print("      ~ %-6d %s -> %s" % (v, porte[v], choisi[v]))
    for nom, avant, inline in orphelins:
        print("      ! COMMENTAIRE ORPHELIN (membre %s retire) : %s"
              % (nom, (avant[:1] or [inline])[0].strip()[:110]))

    if not ecrire:
        return 1 if (ajoutes or retires or corriges) else 0
    neuf = lignes[:prem] + out + lignes[dern + 1:]
    p.write_text("\n".join(neuf) + "\n", encoding="utf-8")
    print("      ECRIT %s (%d membres)" % (m.rel, len(jeu)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mirror", action="append", default=[],
                    help="classe a regenerer (defaut : tous les mirrors STRICTS du registre)")
    ap.add_argument("--ecrire", action="store_true", help="ecrire (sinon : diff seulement)")
    a = ap.parse_args()
    build = P.current_build()
    print("build : %s" % build)
    cibles = [m for m in P.REGISTRE if m.strict and (not a.mirror or m.cls in a.mirror)]
    if a.mirror:
        inconnus = sorted(set(a.mirror) - {m.cls for m in cibles})
        if inconnus:
            raise SystemExit("mirror(s) inconnu(s) ou non STRICT(s) : %s"%", ".join(inconnus))
    rc = 0
    for m in cibles:
        rc |= regenerer(m, build, a.ecrire)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
