"""#282 -- QUAND le registre `PERTES_CONNUES` s'est-il vide, et le zero est-il le BON etat ?

QUESTION BINAIRE. Quatre tests de `tests/test_symbols_coverage_guard_offline.py` tombaient en
`StopIteration` sur `master` parce que `symbols_sync.PERTES_CONNUES` est VIDE. Deux lectures
s'excluent :
  (a) PERTE ACCIDENTELLE -- le registre a ete vide par accident (migration de build, passe de
      re-symbolisation) et son contenu doit etre RESTAURE ;
  (b) ETAT NOMINAL -- l'entree a ete retiree DELIBEREMENT parce que la perte qu'elle excusait
      etait REPAREE, et ce sont les TESTS qui doivent cesser de prelever leur fixture dessus.

Ce probe rend les deux mesures qui tranchent, sans rien croire d'un message de commit :
  ETAPE 1 (datation)  -- l'historique du littéral `PERTES_CONNUES`, commit par commit : combien
                         d'entrees a chaque etat de l'arbre, et a quelle DATE. C'est cette date
                         qu'on confronte a la cause soupconnee, pas l'inverse.
  ETAPE 2 (couverture) -- le compte REEL de la famille GSHARED dans les deux tables versionnees.
                         Si la famille est remontee, l'excuse n'a plus d'objet : le zero est le
                         bon etat, et il se re-derive sans lire aucun commit.
  ETAPE 3 (garde)     -- le registre vide desamorce-t-il l'axe 5 ? On lui soumet une chute
                         effondree sur une transition absente du registre.

Offline PUR : lit `data/symbols/` (versionne) et l'historique git. Aucune session Frida, aucun
runner, aucune (re)injection.
ASCII only (console Windows cp1252).

    python scripts/python/probe_282_registre_pertes.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

import symbols_sync as S  # noqa: E402

FICHIER_REGISTRE = "scripts/python/symbols_sync.py"
FICHIER_TEST = "scripts/python/tests/test_symbols_coverage_guard_offline.py"

# La cause SOUPCONNEE au moment d'ouvrir #282, a confronter aux dates -- pas a croire.
CAUSES_SOUPCONNEES = ("#251", "#259", "#261")


def _git(*args: str) -> str:
    return subprocess.run(("git", "-C", str(REPO)) + args,
                          capture_output=True, text=True, check=True).stdout


def _entrees_du_litteral(source: str) -> int | None:
    """Nombre d'entrees du dict `PERTES_CONNUES` dans une version du fichier.

    Lu sur le TEXTE (la version historique n'est pas importable), en comptant les cles
    `("...", "...", "..."):` du bloc. `None` = le symbole n'existe pas encore a ce commit."""
    m = re.search(r"^PERTES_CONNUES[^=]*=\s*(\{.*?^\})", source, re.S | re.M)
    if m is None:
        m = re.search(r"^PERTES_CONNUES[^=]*=\s*(\{\s*\})", source, re.M)
        if m is None:
            return None
    return len(re.findall(r"\(\s*\"[^\"]+\"\s*,\s*\"[^\"]+\"\s*,\s*\"[^\"]+\"\s*\)\s*:", m.group(1)))


def etape1_datation() -> tuple[str, str] | None:
    """Rend (commit, date) du passage NON VIDE -> VIDE, ou None s'il n'a jamais eu lieu."""
    print("=" * 78)
    print("ETAPE 1 -- DATATION : historique du litteral PERTES_CONNUES")
    print("=" * 78)
    lignes = _git("log", "--reverse", "--format=%H\t%ad\t%s", "--date=iso-strict",
                  "--", FICHIER_REGISTRE).splitlines()
    precedent, bascule, naissance = None, None, None
    for ligne in lignes:
        sha, date, sujet = ligne.split("\t", 2)
        try:
            source = _git("show", "%s:%s" % (sha, FICHIER_REGISTRE))
        except subprocess.CalledProcessError:
            continue
        n = _entrees_du_litteral(source)
        etat = "ABSENT" if n is None else ("VIDE" if n == 0 else "%d entree(s)" % n)
        print("  %s  %s  %-13s  %s" % (sha[:8], date, etat, sujet[:64]))
        if naissance is None and n is not None:
            naissance = (sha[:8], date)
        if precedent is not None and precedent > 0 and n == 0:
            bascule = (sha[:8], date, sujet)
        precedent = -1 if n is None else n

    print("")
    if bascule is None:
        print("  VERDICT ETAPE 1 : aucun passage non-vide -> vide dans l'historique.")
        return None
    sha, date, sujet = bascule
    print("  VERDICT ETAPE 1 : le registre s'est vide en %s (%s)" % (sha, date))
    print("                    %s" % sujet)

    # Les tests qui en dependaient sont-ils ANTERIEURS a ce vidage ? Si oui, le commit qui a
    # vide a laisse un rouge derriere lui.
    pose = _git("log", "--reverse", "--format=%H\t%ad", "--date=iso-strict",
                "--", FICHIER_TEST).splitlines()
    if pose:
        sha_test, date_test = pose[0].split("\t")
        print("  Tests du registre poses en %s (%s)" % (sha_test[:8], date_test))
        print("  -> le vidage est %s la pose des tests"
              % ("POSTERIEUR a" if date_test < date else "ANTERIEUR a"))

    # Confrontation aux causes soupconnees. LE TEST QUI TRANCHE N'EST PAS « avant le vidage »
    # mais « avant la NAISSANCE du registre » : une cause livree avant que le symbole n'existe
    # ne peut pas l'avoir vide, quel que soit son sujet.
    print("")
    if naissance:
        print("  Registre CREE (premiere version du symbole) en %s (%s)" % naissance)
    print("  Causes soupconnees, datees (dernier commit portant le numero) :")
    for tag in CAUSES_SOUPCONNEES:
        hits = _git("log", "--format=%H\t%ad\t%s", "--date=iso-strict",
                    "--grep=%s" % tag).splitlines()
        if not hits:
            print("    %-6s : aucun commit" % tag)
            continue
        sha_c, date_c, sujet_c = hits[0].split("\t", 2)
        if naissance and date_c < naissance[1]:
            rel = "LIEN IMPOSSIBLE : anterieur a la naissance du registre"
        elif date_c < date:
            rel = "anterieur au vidage"
        else:
            rel = "posterieur au vidage"
        print("    %-6s : %s  %s  %s" % (tag, sha_c[:8], date_c, sujet_c[:40]))
        print("             %s" % rel)
    return sha, date


def etape2_couverture() -> bool:
    """La famille que l'entree excusait est-elle RETABLIE dans les tables versionnees ?"""
    print("")
    print("=" * 78)
    print("ETAPE 2 -- COUVERTURE REELLE de la famille GSHARED (tables versionnees)")
    print("=" * 78)
    ref = S._reference_la_plus_recente()
    if ref is None:
        print("  aucune archive avec table ghidra -- etape NON MESUREE")
        return False
    courant = S.versioned_build()
    v, n = S._familles_de(ref), S._familles_de(courant)
    g_v, g_n = v.get("GSHARED", 0), n.get("GSHARED", 0)
    ratio = (g_n / g_v) if g_v else float("nan")
    print("  reference %-12s GSHARED = %6d" % (ref.name, g_v))
    print("  courant   %-12s GSHARED = %6d" % (courant.name, g_n))
    print("  ratio = %.3f   (seuil de la garde : %.2f)" % (ratio, S.SEUIL_COUVERTURE))
    repare = g_v >= S.PLANCHER_FAMILLE and ratio >= S.SEUIL_COUVERTURE
    print("  -> la famille est %s : une excuse pour elle serait %s"
          % ("RETABLIE" if repare else "TOUJOURS EFFONDREE",
             "SANS OBJET" if repare else "ENCORE NECESSAIRE"))
    return repare


def etape3_garde() -> bool:
    """Registre vide == garde desamorcee ? Une chute hors registre doit toujours lever."""
    print("")
    print("=" * 78)
    print("ETAPE 3 -- le registre VIDE desamorce-t-il l'axe 5 ?")
    print("=" * 78)
    print("  entrees du registre : %d" % len(S.PERTES_CONNUES))
    fam, ref, cur = "il2cpp:FamilleAbsenteDuRegistre", "refAbsente", "curAbsente"
    try:
        S.comparer_couverture({fam: 4882}, {fam: 0}, ref, cur)
    except S.Desync:
        print("  chute 4882 -> 0 sur une transition hors registre : LEVEE  -> garde ACTIVE")
        return True
    print("  chute 4882 -> 0 sur une transition hors registre : PASSEE  -> garde DESAMORCEE")
    return False


def main() -> int:
    etape1_datation()
    repare = etape2_couverture()
    active = etape3_garde()

    print("")
    print("=" * 78)
    print("VERDICT")
    print("=" * 78)
    if repare and active and not S.PERTES_CONNUES:
        print("  ETAT NOMINAL. Le registre est vide parce que la perte qu'il excusait est")
        print("  REPAREE, et la garde reste active sur tout le reste. Rien a restaurer : ce")
        print("  sont les tests qui ne doivent pas prelever leur fixture sur ce contenu.")
        return 0
    if not repare:
        print("  A EXAMINER : la famille est toujours effondree alors que le registre ne la")
        print("  couvre plus -- soit l'excuse a ete retiree trop tot, soit la garde hurle.")
        return 1
    print("  A EXAMINER : la garde ne leve pas sur une chute hors registre.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
