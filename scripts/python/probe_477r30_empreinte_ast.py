"""L'EMPREINTE AST : une tranche de CITATIONS n'a pas le droit de bouger du CODE.

    python scripts/python/probe_477r30_empreinte_ast.py --attendu <declaration.tsv>
    python scripts/python/probe_477r30_empreinte_ast.py            # LISTE, sans verdict

CE QUE CE PROBE TRANCHE
-----------------------
Corriger des slots d'interface cites dans des docstrings et des commentaires touche des
dizaines de fichiers du moteur. Rien, dans un diff de cette taille, ne distingue a l'oeil une
docstring reecrite d'une ligne de code deplacee -- et une relecture qui doit chercher ca sur
des centaines de lignes de prose ne le trouvera pas.

L'empreinte le tranche mecaniquement : pour chaque fichier Python modifie, on parse les DEUX
versions, on RETIRE les docstrings, et on compare les arbres. Un fichier qui ne devait porter
que des corrections de citation doit rendre des arbres IDENTIQUES.

CE QUI DIVERGE LEGITIMEMENT EST NOMME, JAMAIS TU
------------------------------------------------
Les fichiers dont le CODE change legitimement dans la tranche sont DECLARES par l'APPELANT,
un par un, avec la raison -- un TSV `chemin<TAB>raison` passe par `--attendu`. Tout autre
divergent est un ROUGE.

⚠ LA DECLARATION EST UNE ENTREE, PAS UNE CONSTANTE DU FICHIER, ET C'EST UNE MESURE QUI L'A
IMPOSE (2026-08-06). Elle a d'abord ete figee dans ce module sur les 3 fichiers de la tranche
qui l'a cree (#477-r30). Consequence : sur la branche de TOUTE AUTRE tranche, ses fichiers
sortaient en « NON DECLARE » et l'instrument rendait ROUGE -- il accusait la branche mesuree
d'une faute qui etait la sienne, celle de n'etre calibre que pour une tranche. Mesure sur
#477-r22-r1 : 7 fichiers rouges, 0 faute. Un instrument qui rougit sur tout le monde ne se
lit plus, exactement comme le seuil qui se degrade en silence.

⚠ SANS DECLARATION, IL NE REND AUCUN VERDICT -- ni vert ni rouge. Il LISTE les divergents et
sort en NON MESURE (rc 2). Un vert sans declaration ne garderait rien (tout serait tolere) ;
un rouge accuserait l'appelant. Le tri-etat est le seul honnete : `2` = PAS MESURE, `1` =
ROUGE, `0` = VERT.

⚠ LES COMMENTAIRES NE SONT PAS DANS L'AST. Ce probe ne dit donc RIEN d'un commentaire modifie
-- et c'est voulu : c'est exactement la classe de modification qu'on revendique. Ce qu'il
garantit, c'est qu'aucune de ces modifications n'a EMPORTE du code avec elle.

⚠ IL ASSERTIONNE SON PROPRE NON-VIDE. Un perimetre vide rendrait « 0 divergent » et se lirait
comme un vert, alors qu'il n'aurait RIEN mesure.

ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

#: Code de sortie du NON MESURE -- distinct du ROUGE. Un instrument qui ne peut pas mesurer et
#: un port qui a une faute ne se disent pas avec le meme chiffre (cf. `host_inputs.py`).
RC_PAS_MESURE = 2


def _pas_mesure(motif: str) -> "int":
    """Sort en NON MESURE. JAMAIS en `1` : un rc de rouge ferait chercher une faute la ou il n'y
    a qu'une mesure manquante -- c'est la faute que ce probe s'est faite a lui-meme."""
    print("PAS MESURE : %s" % motif)
    return RC_PAS_MESURE


def lire_declaration(chemin: Path) -> dict:
    """Le TSV `chemin<TAB>raison` passe par `--attendu`. Lignes vides et `#` ignorees.

    ⚠ UNE RAISON VIDE EST REFUSEE. « declarer » sans dire pourquoi rendrait la liste blanche
    utilisable comme echappatoire silencieuse -- or c'est une DECLARATION qu'on relit avec le
    diff, pas une case a cocher."""
    attendus, fautes = {}, []
    for n, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        rel, _sep, raison = ligne.partition("\t")
        if not raison.strip():
            fautes.append("ligne %d : `%s` n'a pas de raison (attendu `chemin<TAB>raison`)"
                          % (n, rel.strip()))
            continue
        attendus[rel.strip().replace("\\", "/")] = raison.strip()
    if fautes:
        raise ValueError("; ".join(fautes))
    return attendus


class _SansDocstring(ast.NodeTransformer):
    """Retire la docstring d'un module, d'une classe et d'une fonction.

    ⚠ On retire le NOEUD, pas seulement sa valeur : remplacer la chaine par `None` laisserait
    un `Expr` dont la presence depend de l'existence d'une docstring, donc l'empreinte
    changerait quand meme si on en AJOUTAIT une -- ce qui n'est pas du code.
    """

    def _nettoyer(self, node):
        corps = getattr(node, "body", None)
        if (corps and isinstance(corps[0], ast.Expr)
                and isinstance(corps[0].value, ast.Constant)
                and isinstance(corps[0].value.value, str)):
            node.body = corps[1:] or [ast.Pass()]
        return self.generic_visit(node)

    visit_Module = _nettoyer
    visit_ClassDef = _nettoyer
    visit_FunctionDef = _nettoyer
    visit_AsyncFunctionDef = _nettoyer


def empreinte(source: str) -> str:
    arbre = _SansDocstring().visit(ast.parse(source))
    ast.fix_missing_locations(arbre)
    #: `include_attributes=False` : les numeros de ligne BOUGENT des qu'une docstring gagne
    #: ou perd une ligne. Les inclure ferait rougir toute la tranche, pour rien.
    return ast.dump(arbre, annotate_fields=True, include_attributes=False)


def _git(*args: str):
    """Rend `(rc, texte)`, ou `(rc, None)` quand la CAPTURE a echoue.

    ⚠ `encoding="utf-8"` EXPLICITE, et ce n'est pas cosmetique -- c'est une panne MESUREE le
    2026-08-06. `text=True` seul decode avec l'encodage de la LOCALE (cp1252 sur cette machine) ;
    un octet parfaitement valide en UTF-8 mais indefini en cp1252 (`0x90`, rencontre dans
    `operations/damage.py` ET dans `catalog_inject.py`, position 4716) fait lever
    `UnicodeDecodeError` DANS LE THREAD LECTEUR de `subprocess`. L'exception n'est pas propagee :
    `p.returncode` reste **0** et `p.stdout` devient **None**. Une capture ratee se presentait donc
    comme une mesure reussie, et le probe partait en `TypeError` trois etages plus loin -- symptome
    illisible pour la vraie cause. (#477-r33 l'a rencontree independamment sur `catalog_inject.py`
    et a converge sur le MEME correctif ; la version gardee ici est celle de #477-r30-r2, qui garde
    EN PLUS le `stdout == None`.)

    ⚠ ET LE `None` EST GARDE PAR L'APPELANT, pas seulement evite ici : un `rc == 0` accompagne
    d'une sortie absente doit sortir en NON MESURE, jamais etre lu comme un fichier vide -- un
    fichier vide aurait une empreinte VALIDE, donc rendrait un verdict."""
    try:
        p = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:                # noqa: BLE001
        # une panne de capteur doit porter son NOM, pas juste un code
        print("  git muet sur `%s` : %s" % (" ".join(args), exc))
        return 1, None
    return p.returncode, p.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/master",
                    help="la revision TEMOIN (defaut : origin/master)")
    ap.add_argument("--attendu", type=Path, default=None,
                    help="TSV `chemin<TAB>raison` des divergents DECLARES. Sans lui, le probe "
                         "LISTE et ne rend aucun verdict (rc 2).")
    args = ap.parse_args()

    print("=== empreinte AST (docstrings retirees) vs %s ===" % args.base)
    attendus = {}
    if args.attendu is not None:
        if not args.attendu.is_file():
            return _pas_mesure("declaration introuvable : %s" % args.attendu)
        try:
            attendus = lire_declaration(args.attendu)
        except (OSError, UnicodeDecodeError, ValueError) as exc:          # noqa: BLE001
            return _pas_mesure("declaration illisible (%s) -- %s" % (args.attendu, exc))
        print("  declaration : %s (%d fichier(s) declare(s))" % (args.attendu, len(attendus)))
    #: ⚠ LE TEMOIN DOIT ETRE UN ANCETRE DE `HEAD`, et ce cran n'est pas cosmetique : mesure du
    #: 2026-08-06, un `origin/master` qui avait avance de quelques PR faisait rendre
    #: 17 divergents NON DECLARES -- tous etant le travail des AUTRES, pas le notre. Une
    #: empreinte qui accuse le voisin fait renoncer a un controle pourtant juste. On REFUSE,
    #: en disant quoi faire (`git rebase origin/master`), plutot que de rendre un rouge faux.
    rc_anc, _ = _git("merge-base", "--is-ancestor", args.base, "HEAD")
    if rc_anc != 0:
        return _pas_mesure(
            "`%s` n'est PAS un ancetre de HEAD -- le diff contiendrait le travail\n"
            "  d'autres branches, et chacun de leurs fichiers sortirait en NON DECLARE.\n"
            "  Rebaser (`git fetch origin && git rebase origin/master`) puis rejouer, ou\n"
            "  passer explicitement `--base $(git merge-base HEAD %s)`." % (args.base, args.base))
    rc, sortie = _git("diff", "--name-only", args.base, "--", "*.py")
    if rc != 0:
        return _pas_mesure("`git diff --name-only %s` a echoue (rc=%d)." % (args.base, rc))
    fichiers = [f.strip() for f in sortie.splitlines() if f.strip().endswith(".py")]
    if not fichiers:
        return _pas_mesure("AUCUN fichier Python ne differe de %s. Un perimetre vide rend "
                           "`0 divergent` et se lirait comme un vert." % args.base)

    identiques: list[str] = []
    divergents: list[tuple[str, str]] = []
    neufs: list[str] = []
    illisibles: list[tuple[str, str]] = []
    for rel in fichiers:
        courant = REPO / rel
        rc_base, base_src = _git("show", "%s:%s" % (args.base, rel))
        if rc_base != 0:
            neufs.append(rel)
            continue
        if base_src is None:
            # ⚠ `rc == 0` MAIS sortie absente : la capture a echoue sans le dire (cf. `_git`).
            # Surtout PAS traite comme un fichier vide -- un vide a une empreinte VALIDE, donc
            # rendrait un verdict sur une mesure qui n'a pas eu lieu.
            illisibles.append((rel, "capture git VIDE alors que rc == 0"))
            continue
        if not courant.is_file():
            divergents.append((rel, "SUPPRIME"))
            continue
        try:
            a = empreinte(base_src)
            b = empreinte(courant.read_text(encoding="utf-8"))
        except (SyntaxError, OSError, UnicodeDecodeError) as exc:       # noqa: BLE001
            illisibles.append((rel, str(exc)))
            continue
        (identiques if a == b else divergents).append(rel if a == b else (rel, "AST DIFFERENT"))

    print("  %d fichier(s) Python compare(s)" % len(fichiers))
    print("  %d identique(s) AST -- seules des docstrings/commentaires ont bouge"
          % len(identiques))
    print("  %d fichier(s) NEUF(S) (absent(s) du temoin) : %s"
          % (len(neufs), ", ".join(neufs) or "-"))
    for rel, quoi in illisibles:
        print("  ILLISIBLE : %s (%s)" % (rel, quoi))

    inattendus = [r for r, _ in divergents if r not in attendus]
    print("  %d divergent(s), dont %d DECLARE(S) :" % (len(divergents), len(divergents)
                                                       - len(inattendus)))
    for rel, quoi in divergents:
        motif = attendus.get(rel)
        print("      %-70s %s -- %s" % (rel, quoi, motif or "*** NON DECLARE ***"))
    inattendus += [r for r in neufs if r not in attendus]

    #: ⚠ SANS DECLARATION, ON NE REND PAS DE VERDICT. `inattendus` vaut alors « tous les
    #: divergents », ce qui n'accuse personne : l'appelant n'a rien declare. Rendre ROUGE ici
    #: reviendrait a imputer a la branche mesuree un defaut de CALIBRAGE de l'instrument --
    #: la faute exacte que ce probe s'est faite a lui-meme (cf. l'en-tete).
    if args.attendu is None:
        print()
        print("  divergents NON CONFRONTES (aucune declaration fournie) : %d -- %s"
              % (len(inattendus), ", ".join(inattendus) or "-"))
        return _pas_mesure(
            "aucune declaration (`--attendu`). Cet instrument ne garde une tranche que si\n"
            "  l'appelant DECLARE les fichiers dont le code bouge legitimement, avec la raison.\n"
            "  Sans elle, un vert ne garderait rien et un rouge accuserait la branche mesuree.")

    #: ⚠ Une declaration qui nomme un fichier ABSENT du perimetre est un ROUGE elle aussi : elle
    #: se lit comme une tolerance active alors qu'elle ne couvre plus rien -- une liste blanche
    #: perimee est ce qui fait passer pour garde ce qui ne garde plus.
    mortes = sorted(set(attendus) - {r for r, _ in divergents} - set(neufs))
    rouge = bool(inattendus or illisibles or mortes)
    print()
    print("VERDICT : %s" % ("ROUGE" if rouge else "VERT"))
    if inattendus:
        print("  %d fichier(s) dont le CODE a bouge sans etre declare : %s"
              % (len(inattendus), ", ".join(inattendus)))
    if mortes:
        print("  %d declaration(s) MORTE(S) (le fichier ne diverge pas) : %s"
              % (len(mortes), ", ".join(mortes)))
    return 1 if rouge else 0


if __name__ == "__main__":
    sys.exit(main())
