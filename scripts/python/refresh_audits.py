"""Regenere TOUS les audits generes de `docs/rl/` et dit LESQUELS etaient perimes.

POURQUOI CE SCRIPT EXISTE
=========================
Les audits de couverture (`kit-coverage.md`, `passive-ability-coverage.md`, `npc-registry.md`,
`summons-registry.md`, ...) sont GENERES a partir du gameconfig et des registres moteur. Rien ne
les regenere au merge, et AUCUN cliquet ne rougit dessus -- une PR qui porte une ability les
perime donc EN SILENCE. Mesure des 2026-08-13 / 2026-08-14 : quatre peremptions trouvees a la
main sur `master` en deux tours d'orchestration (`summons-registry` une fois, `npc-registry`
deux fois, `passive-ability-coverage` une fois). A chaque fois le fichier lu servait a DISPATCHER
du travail.

CE N'EST VOLONTAIREMENT PAS UN CLIQUET PAR PR, et la raison est mesuree : les quatre audits
coutent ~60 s (14,4 + 3,6 + 19,2 + 22,3), et surtout un cliquet forcerait CHAQUE PR touchant
`engine/**` a regenerer -- soit N PR paralleles reecrivant les memes fichiers generes, c'est-a-dire
exactement les conflits que `CLAUDE.md` interdit de resoudre (<< ne jamais resoudre un conflit
dessus -- les REGENERER >>). Le bon declencheur n'est pas la PR, c'est le MERGE : un seul acteur,
une seule regeneration, aucun conflit. D'ou un outil d'orchestrateur, joue APRES chaque merge.

CE QU'IL NE FAIT PAS : il ne commit rien. Il regenere et il DIT. L'indexation reste une decision.

LA LISTE DES AUDITS EST DERIVEE, JAMAIS ENUMEREE
================================================
Une liste ecrite a la main se perime -- c'est le vice qui a deja fait rater des cliquets a
l'orchestrateur (une liste figee qui ne voyait pas les cliquets ajoutes depuis). Ici le perimetre
se DERIVE du marqueur que chaque generateur ecrit lui-meme dans son en-tete :

    > Genere par `scripts/python/<script>.py`

Un audit neuf qui ecrit ce marqueur entre donc tout seul dans le perimetre. Un fichier de
`docs/rl/` qui ne le porte PAS est ecrit a la main et reste dehors (mesure : `unit-trait-coverage.md`
est dans ce cas -- une recon de 2026-07-24, pas un genere).

LE TRI-ETAT EST OBLIGATOIRE
===========================
Un generateur qui echoue ne rend PAS << cet audit est a jour >>. Il rend NON MESURE, et le verdict
global devient rc 2. Meme discipline que `host_inputs.py` et `loop_status.py` : un echec RENDU se
lit comme une mesure, donc il doit LEVER. De meme, un balayage qui ne trouve AUCUN audit est un
rc 2, pas un << tout est frais >> : un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas.
"""
import argparse
import os
import re
import subprocess
import sys

_ICI = os.path.dirname(os.path.abspath(__file__))
_RACINE = os.path.abspath(os.path.join(_ICI, "..", ".."))
_DOCS = os.path.join("docs", "rl")

#: Le marqueur que chaque generateur ecrit dans l'en-tete de sa sortie. C'est LUI qui definit le
#: perimetre -- pas une liste. Tolere les retours a la ligne du markdown (`> Genere par\n> `...).
_MARQUEUR = re.compile(r"Genere par\s*`(scripts/python/[A-Za-z0-9_]+\.py)`")

#: Nombre de lignes de tete ou l'on cherche le marqueur. Au-dela ce n'est plus un en-tete, c'est
#: du corps -- et une PROSE qui cite un generateur ne fait pas du fichier un genere.
_LIGNES_ENTETE = 8


def _git(*args):
    """Rend (rc, stdout) -- jamais d'exception, l'appelant tranche."""
    p = subprocess.run(("git",) + args, cwd=_RACINE, capture_output=True, text=True)
    return p.returncode, p.stdout


def _versionnes():
    """Les fichiers `docs/rl/*.md` SUIVIS par git. Un non-suivi n'est pas un artefact du depot."""
    rc, out = _git("ls-files", "--", _DOCS.replace("\\", "/") + "/*.md")
    if rc != 0:
        return None
    return [l.strip() for l in out.splitlines() if l.strip()]


def _recenser():
    """Derive [(chemin_relatif, script, kind_ou_None)] du marqueur d'en-tete. None si git muet."""
    fichiers = _versionnes()
    if fichiers is None:
        return None
    trouves = []
    for rel in fichiers:
        chemin = os.path.join(_RACINE, rel.replace("/", os.sep))
        try:
            with open(chemin, "r", encoding="utf-8", errors="replace") as fh:
                tete = "".join(fh.readline() for _ in range(_LIGNES_ENTETE))
        except OSError:
            continue
        m = _MARQUEUR.search(tete)
        if not m:
            continue
        script = os.path.basename(m.group(1))
        # UN generateur peut servir PLUSIEURS perimetres (`audit_npc_registry.py --kind npc` et
        # `--kind summons` ecrivent deux fichiers). Le perimetre se lit dans le NOM du fichier,
        # `<kind>-registry.md` -- c'est la convention du generateur lui-meme (`--out` par defaut).
        base = os.path.basename(rel)
        kind = None
        mk = re.match(r"^([a-z]+)-registry\.md$", base)
        if mk:
            kind = mk.group(1)
        trouves.append((rel, script, kind))
    return trouves


def _cibles_de(rel):
    """Le markdown ET son jumeau `.tsv` s'il est versionne (les generateurs les emettent ensemble)."""
    cibles = [rel]
    tsv = rel[:-3] + ".tsv"
    rc, out = _git("ls-files", "--error-unmatch", "--", tsv)
    if rc == 0 and out.strip():
        cibles.append(tsv)
    return cibles


def _modifies(cibles):
    """Les cibles DEJA modifiees dans l'arbre (avant toute regeneration)."""
    rc, out = _git("diff", "--name-only", "--", *cibles)
    if rc != 0:
        return None
    return set(l.strip() for l in out.splitlines() if l.strip())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true",
                    help="regenere meme si des cibles sont deja modifiees (le verdict devient "
                         "alors ambigu sur celles-la, et il le DIT)")
    ap.add_argument("--dry-run", action="store_true",
                    help="recense le perimetre et sort, sans rien regenerer")
    a = ap.parse_args(argv)

    audits = _recenser()
    if audits is None:
        print("[refresh] git muet (ls-files en echec) -- NON MESURE, rien regenere")
        return 2
    if not audits:
        # Un balayage vide n'est PAS un << tout est frais >> : soit le marqueur a change, soit le
        # chemin est faux. Dans les deux cas le recenseur ne visite rien et ne peut rien conclure.
        print("[refresh] AUCUN audit genere trouve sous %s -- le marqueur `Genere par ...` a-t-il "
              "change ? NON MESURE." % _DOCS)
        return 2

    print("[refresh] perimetre DERIVE du marqueur d'en-tete : %d audit(s)" % len(audits))
    toutes_cibles = []
    plan = []
    for rel, script, kind in sorted(audits):
        cibles = _cibles_de(rel)
        toutes_cibles.extend(cibles)
        cmd = [sys.executable, script] + (["--kind", kind] if kind else [])
        plan.append((rel, cmd, cibles))
        print("   %-34s <- %s%s" % (rel[len(_DOCS) + 1:], script,
                                    (" --kind %s" % kind) if kind else ""))
    if a.dry_run:
        return 0

    deja = _modifies(toutes_cibles)
    if deja is None:
        print("[refresh] git muet (diff en echec) -- NON MESURE, rien regenere")
        return 2
    if deja and not a.force:
        print("\n[refresh] REFUS : %d cible(s) DEJA modifiee(s) dans l'arbre -- le verdict "
              "<< etait perime >> serait ambigu dessus :" % len(deja))
        for c in sorted(deja):
            print("     M %s" % c)
        print("   Commite ou restaure ces fichiers, ou relance avec --force.")
        return 2

    non_mesures = []
    for rel, cmd, _cibles in plan:
        p = subprocess.run(cmd, cwd=_ICI, capture_output=True, text=True)
        if p.returncode != 0:
            non_mesures.append((rel, cmd[1], p.returncode,
                                (p.stderr or p.stdout or "").strip().splitlines()[-1:]))

    apres = _modifies(toutes_cibles)
    if apres is None:
        print("[refresh] git muet apres regeneration -- NON MESURE")
        return 2
    # Ce qui etait deja modifie AVANT ne prouve rien sur la peremption : on ne l'impute pas.
    perimes = sorted(apres - deja)

    print("")
    if non_mesures:
        print("[refresh] %d generateur(s) EN ECHEC -- leur audit est NON MESURE, pas << a jour >> :"
              % len(non_mesures))
        for rel, script, rc, fin in non_mesures:
            print("     %s (%s) rc=%d %s" % (rel, script, rc, (fin[0] if fin else "")))
    if perimes:
        print("[refresh] %d fichier(s) etaient PERIMES sur ce commit, regeneres a l'instant :"
              % len(perimes))
        for c in perimes:
            print("     M %s" % c)
        print("   -> a INDEXER et commiter (`git add` chemin par chemin).")
    elif not non_mesures:
        print("[refresh] les %d audits etaient A JOUR -- rien a commiter." % len(audits))

    if non_mesures:
        return 2
    return 1 if perimes else 0


if __name__ == "__main__":
    sys.exit(main())
