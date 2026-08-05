"""#270-r4-r2-r2 -- HISSER au niveau module les imports differes classes `hissable`.

Entree : le JSON produit par `probe_270r4r2r2_tri_differes.py --mesurer --sortie`.
Seuls les sites de categorie `hissable` sont candidats -- la categorie est MESUREE
(hissage simule + import depuis plusieurs ordres d'entree), jamais devinee.

Un hissage n'est PAS un simple deplacement de ligne : il fait passer un nom du scope
LOCAL au scope MODULE. Quatre gardes REFUSENT le site plutot que de risquer un
changement de comportement silencieux -- chacune imprime son motif, et le total des
refus est ventile (un refus muet serait pire qu'un site non traite) :

  parent-non-fonction  -- l'import n'est pas directement dans un corps de fonction
                          (corps de classe imbrique) : hisser change le SCOPE du nom.
  deja-au-module       -- un des noms lies existe deja au niveau module. Hisser
                          l'ECRASERAIT (ou serait ecrase) -> shadowing silencieux.
  reassigne-localement -- le nom est aussi une cible d'affectation dans la fonction
                          porteuse. Sans l'import local, le nom devient local par
                          affectation -> `UnboundLocalError` avant le premier `Store`.
  conflit-de-nom       -- deux sites du fichier lient le MEME nom depuis des sources
                          DIFFERENTES : hisser les deux ecraserait l'un des deux.
  ligne-partagee       -- l'instruction partage sa ligne avec autre chose (`a; import b`).
  corps-viderait       -- la fonction n'aurait plus aucune instruction.
  fermerait-une-boucle -- l'arete hissee refermerait une boucle d'import. La mesure du tri
                          est INDIVIDUELLE (une instruction a la fois) ; l'ENSEMBLE, lui,
                          peut refermer une boucle qu'aucun hissage isole ne fermait --
                          MESURE : un premier lot a casse l'import de 405 des 409 modules.
                          Le graphe du filtre porte donc l'arete `module -> paquet PARENT`,
                          que Python execute qu'on l'ecrive ou non. Glouton DETERMINISTE
                          (module, ligne), pour que deux executions rendent le meme resultat.

Usage :
    python migrate_270r4r2r2_hisser_differes.py --tri tri.json --simuler
    python migrate_270r4r2r2_hisser_differes.py --tri tri.json --ecrire [--paquet engine.runner]
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

RACINE = Path(__file__).resolve().parent
PAQUET = "engine"


def _chemin(module: str) -> Path:
    p = RACINE / Path(*module.split("."))
    if (p / "__init__.py").is_file():
        return p / "__init__.py"
    return p.with_suffix(".py")


# ---------------------------------------------------------------- analyse

def _noms_lies(noeud) -> list[str]:
    out = []
    for alias in noeud.names:
        if alias.name == "*":
            return []                      # `import *` : indecidable -> refus par vide
        out.append(alias.asname or alias.name.split(".")[0])
    return out


def _source(noeud) -> tuple:
    """La SOURCE d'un import, independante du texte ecrit.

    Deux instructions `from X import a, b` et `from X import b` ont des SEGMENTS differents
    mais la meme source pour `b`. Comparer les segments declarait un conflit la ou il n'y en
    a aucun -- 67 refus, tous faux, a la premiere mesure.
    """
    if isinstance(noeud, ast.ImportFrom):
        return ("from", noeud.level, noeud.module or "")
    return ("import", 0, "")


def _liaisons(noeud) -> dict[str, tuple]:
    """nom lie -> (source, nom d'origine). C'est la cle d'identite d'une liaison."""
    out = {}
    for alias in noeud.names:
        if alias.name == "*":
            return {}
        out[alias.asname or alias.name.split(".")[0]] = (_source(noeud), alias.name)
    return out


def _imports_preambule(arbre: ast.Module) -> dict[str, tuple]:
    """nom -> (source, origine) pour les imports du PREAMBULE (avant la 1re def/class).

    Un import place APRES une definition (recette du PLACEMENT) n'y entre pas : supprimer
    un differe au profit d'un tel import ne garantirait pas que la cible soit chargee.
    """
    out: dict[str, tuple] = {}
    for n in arbre.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            break
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            out.update(_liaisons(n))
    return out


def _noms_module(arbre: ast.Module) -> set[str]:
    """Noms lies au NIVEAU MODULE (imports, def, class, affectations)."""
    out: set[str] = set()
    for n in arbre.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            out.update(_noms_lies(n))
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Assign):
            for c in n.targets:
                out.update(_cibles(c))
        elif isinstance(n, (ast.AnnAssign, ast.AugAssign)):
            out.update(_cibles(n.target))
        elif isinstance(n, ast.If):
            for enfant in list(n.body) + list(n.orelse):
                if isinstance(enfant, (ast.Import, ast.ImportFrom)):
                    out.update(_noms_lies(enfant))
                elif isinstance(enfant, ast.Assign):
                    for c in enfant.targets:
                        out.update(_cibles(c))
                elif isinstance(enfant, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    out.add(enfant.name)
        elif isinstance(n, ast.Try):
            for enfant in list(n.body) + list(n.orelse) + list(n.finalbody):
                if isinstance(enfant, (ast.Import, ast.ImportFrom)):
                    out.update(_noms_lies(enfant))
    return out


def _cibles(noeud) -> list[str]:
    if isinstance(noeud, ast.Name):
        return [noeud.id]
    if isinstance(noeud, (ast.Tuple, ast.List)):
        out = []
        for e in noeud.elts:
            out.extend(_cibles(e))
        return out
    return []


def _stores(portee) -> set[str]:
    """Tous les noms LIES dans le sous-arbre d'une fonction (hors imports)."""
    out: set[str] = set()
    for n in ast.walk(portee):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n is not portee:
            out.add(n.name)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            out.update(n.names)
    return out


class _Parents(ast.NodeVisitor):
    def __init__(self):
        self.parent: dict[int, ast.AST] = {}

    def generic_visit(self, noeud):
        for enfant in ast.iter_child_nodes(noeud):
            self.parent[id(enfant)] = noeud
        super().generic_visit(noeud)


def _point_insertion(arbre: ast.Module, lignes: list[str]) -> int:
    """Index de ligne (0-based) OU inserer : juste apres le dernier import du PREAMBULE.

    Le preambule s'arrete a la premiere `def`/`class`/instruction non triviale. Les
    imports places APRES une definition (recette du PLACEMENT, `# noqa: E402`) ne sont
    donc jamais pris pour reference -- les ecraser reintroduirait le cycle qu'ils evitent.
    """
    dernier = None
    for n in arbre.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            break
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            dernier = n
            continue
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            continue                       # docstring / commentaire-chaine
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.If, ast.Try)):
            continue                       # constantes de module, gardes
        break
    if dernier is not None:
        return dernier.end_lineno          # 0-based index APRES la derniere ligne
    # pas d'import : apres le docstring
    for n in arbre.body:
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant):
            return n.end_lineno
        break
    return 0


# ---------------------------------------------------------------- transformation

def traiter(module: str, sites: list[dict], refus: dict) -> tuple[str, int] | None:
    chemin = _chemin(module)
    src = chemin.read_text(encoding="utf-8")
    # `split("\n")`, JAMAIS `splitlines()` : ce dernier coupe aussi sur `\x0c` (form feed),
    # `\x85`, ` `... que le compilateur Python IGNORE. Sept fichiers d'`engine/` en
    # portent un -- avec `splitlines` la numerotation AST decale et on supprime la MAUVAISE
    # ligne (mesure : 3 fichiers rendus syntaxiquement invalides).
    lignes = src.split("\n")
    arbre = ast.parse(src, filename=str(chemin))
    p = _Parents()
    p.visit(arbre)
    au_module = _noms_module(arbre)

    # index des instructions d'import par ligne de depart
    par_ligne: dict[int, ast.AST] = {}
    for n in ast.walk(arbre):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            par_ligne[n.lineno] = n

    pre = _imports_preambule(arbre)
    retenus = []
    lies_par_nom: dict[str, set[tuple]] = defaultdict(set)
    for s in sites:
        noeud = par_ligne.get(s["ligne"])
        if noeud is None:
            refus["site-introuvable"].append("%s:%d" % (module, s["ligne"]))
            continue
        liaisons = _liaisons(noeud)
        noms = list(liaisons)
        if not noms:
            refus["import-etoile"].append("%s:%d" % (module, s["ligne"]))
            continue
        parent = p.parent.get(id(noeud))
        if not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            refus["parent-non-fonction"].append("%s:%d (%s)"
                                                % (module, s["ligne"], type(parent).__name__))
            continue
        # DEJA au module : identite comparee sur la SOURCE, pas sur le texte. Si toutes les
        # liaisons sont deja produites A L'IDENTIQUE par le preambule, l'instruction est un
        # DOUBLON PUR -> on la SUPPRIME, sans rien inserer.
        doublon = all(pre.get(n) == liaisons[n] for n in noms)
        if not doublon:
            deja = [n for n in noms if n in au_module and pre.get(n) != liaisons[n]]
            if deja:
                refus["deja-au-module"].append("%s:%d (%s)"
                                               % (module, s["ligne"], ",".join(deja)))
                continue
        stores = _stores(parent)
        # le nom est bien un Store DANS la fonction : celui de l'import lui-meme n'y est
        # pas (un alias d'import n'est pas un `ast.Name`), donc toute presence est ailleurs.
        mauvais = [n for n in noms if n in stores]
        if mauvais:
            refus["reassigne-localement"].append("%s:%d (%s)"
                                                 % (module, s["ligne"], ",".join(mauvais)))
            continue
        # ligne partagee ? un COMMENTAIRE de fin de ligne n'en est pas une -- le confondre
        # avait produit 78 refus, tous faux.
        seg = ast.get_source_segment(src, noeud) or ""
        brute = lignes[noeud.end_lineno - 1].rstrip("\r")
        reste = brute[noeud.end_col_offset:].strip()
        if reste and not reste.startswith("#"):
            refus["ligne-partagee"].append("%s:%d (reste %r)" % (module, s["ligne"], reste[:30]))
            continue
        if lignes[noeud.lineno - 1][: noeud.col_offset].strip():
            refus["ligne-partagee"].append("%s:%d (avant l'import)" % (module, s["ligne"]))
            continue
        # corps qui se viderait ?
        restant = [x for x in parent.body
                   if not (x.lineno == noeud.lineno and x.end_lineno == noeud.end_lineno)]
        if not restant:
            refus["corps-viderait"].append("%s:%d" % (module, s["ligne"]))
            continue
        for n in noms:
            lies_par_nom[n].add(liaisons[n])
        retenus.append((noeud, seg, liaisons, doublon))

    # conflit de nom : MEME nom lie a des sources DIFFERENTES -> hisser ecraserait l'un des deux
    conflits = {n for n, srcs in lies_par_nom.items() if len(srcs) > 1}
    if conflits:
        garde = []
        for noeud, seg, liaisons, doublon in retenus:
            if any(n in conflits for n in liaisons):
                refus["conflit-de-nom"].append(
                    "%s:%d (%s)" % (module, noeud.lineno,
                                    ",".join(n for n in liaisons if n in conflits)))
            else:
                garde.append((noeud, seg, liaisons, doublon))
        retenus = garde
    if not retenus:
        return None

    # -- reecriture : supprimer les lignes, inserer les segments dedupliques en tete
    a_supprimer: set[int] = set()
    segments: list[str] = []
    vus: set[str] = set()
    for noeud, seg, liaisons, doublon in sorted(retenus, key=lambda t: t[0].lineno):
        for i in range(noeud.lineno, noeud.end_lineno + 1):
            a_supprimer.add(i)
        if doublon:
            continue                        # deja au preambule A L'IDENTIQUE : rien a inserer
        cle = seg.strip()
        if cle not in vus:
            vus.add(cle)
            segments.append(cle)
    ins = _point_insertion(arbre, lignes)
    sortie: list[str] = []
    for i, ligne in enumerate(lignes, start=1):
        if i in a_supprimer:
            continue
        sortie.append(ligne)
        if i == ins:
            sortie.extend(sorted(segments))
    if ins == 0:
        sortie = sorted(segments) + sortie
    texte = "\n".join(sortie)
    # controle : le resultat DOIT parser
    try:
        ast.parse(texte, filename=str(chemin))
    except SyntaxError as e:
        # UN refus PAR SITE, sinon la partition ne boucle plus : un fichier rejete emporte
        # tous ses sites, et n'en compter qu'un les rendrait invisibles.
        for noeud, _, _, _ in retenus:
            refus["resultat-invalide"].append("%s:%d (%s)" % (module, noeud.lineno, e))
        return None
    return texte, len(retenus)


def _filtrer_acyclique(par_module: dict, refus: dict, ancetres: bool = True) -> dict:
    """Retire les sites dont l'arete hissee refermerait un cycle NIVEAU MODULE.

    Le tri mesure une instruction A LA FOIS ; l'ENSEMBLE peut refermer une boucle qu'aucun
    hissage isole ne fermait. Glouton DETERMINISTE (module, ligne) sur le graphe reel, pour
    que deux executions rendent le meme resultat.
    """
    import probe_270r4r2_cycles_imports as CY

    ml, _, _ = CY.construire(RACINE / PAQUET)
    depart = CY._cycles(ml)
    if depart:
        print("[270-r4-r2-r2/hisser] ECHEC : l'arbre porte DEJA %d cycle(s) module-level -- "
              "le filtre mesurerait un graphe casse" % len(depart))
        raise SystemExit(2)
    g = {k: set(v) for k, v in ml.items()}

    def _succ(x: str) -> set[str]:
        """Successeurs REELS : les imports declares PLUS le paquet PARENT.

        Importer `engine.a.b` execute `engine/a/__init__.py` AVANT le corps de `b` -- que
        `b` le declare ou non. Le graphe des seules sources declarees est AVEUGLE a ces
        boucles-la, et c'est mesure : sans cette arete, le filtre a laisse passer un lot qui
        cassait l'import de 405 des 409 modules (`battle_query` -> `entities.effects.aura`
        -> [parent] `engine.entities` -> ... -> `entities.triggers` -> `battle_query`).
        """
        out = set(g.get(x, ()))
        if ancetres and "." in x:
            out.add(x.rsplit(".", 1)[0])
        return out

    def _accessible(src: str, dst: str) -> bool:
        vus, pile = {src}, [src]
        while pile:
            n = pile.pop()
            for w in _succ(n):
                if w == dst:
                    return True
                if w not in vus:
                    vus.add(w)
                    pile.append(w)
        return False

    out: dict[str, list] = defaultdict(list)
    for module in sorted(par_module):
        for s in sorted(par_module[module], key=lambda x: x["ligne"]):
            nouvelles = [c for c in s["cibles"] if c not in g.get(module, set())]
            if nouvelles and any(_accessible(c, module) for c in nouvelles):
                refus["fermerait-une-boucle"].append("%s:%d -> %s"
                                                % (module, s["ligne"], ",".join(nouvelles)))
                continue
            for c in nouvelles:
                g.setdefault(module, set()).add(c)
            out[module].append(s)
    apres = CY._cycles(g)
    print("[270-r4-r2-r2/hisser] filtre acyclique : %d retenu(s), %d refuse(s) ; "
          "SCC du graphe projete = %d"
          % (sum(len(v) for v in out.values()), len(refus["fermerait-une-boucle"]), len(apres)))
    if apres:
        print("[270-r4-r2-r2/hisser] ECHEC : le filtre laisse passer un cycle -- il ne "
              "discrimine plus")
        raise SystemExit(2)
    return dict(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tri", required=True)
    ap.add_argument("--paquet", default="")
    ap.add_argument("--categorie", default="hissable")
    ap.add_argument("--ecrire", action="store_true")
    ap.add_argument("--simuler", action="store_true")
    ap.add_argument("--sans-ancetres", action="store_true",
                    help="CONTRE-EPREUVE : retire l'arete `module -> paquet parent` du filtre. "
                         "Le lot obtenu DOIT casser l'import (mesure : 405/409 modules).")
    args = ap.parse_args()

    d = json.loads(Path(args.tri).read_text(encoding="utf-8"))
    cats = d["categories"]
    par_module: dict[str, list[dict]] = defaultdict(list)
    for s in d["sites"]:
        cle = "%s:%d" % (s["module"], s["ligne"])
        if cats.get(cle, {}).get("categorie") != args.categorie:
            continue
        if args.paquet and not (s["module"] == args.paquet
                                or s["module"].startswith(args.paquet + ".")):
            continue
        par_module[s["module"]].append(s)

    n_sites = sum(len(v) for v in par_module.values())
    print("[270-r4-r2-r2/hisser] TEMOIN : %d site(s) de categorie '%s' sur %d fichier(s) (%s)"
          % (n_sites, args.categorie, len(par_module), args.paquet or "TOUT engine/"))
    if n_sites == 0:
        print("[270-r4-r2-r2/hisser] ECHEC : 0 site -- un zero ne prouve RIEN")
        return 2

    refus: dict[str, list] = defaultdict(list)
    par_module = _filtrer_acyclique(par_module, refus, ancetres=not args.sans_ancetres)
    ecrits = 0
    hisses = 0
    for module in sorted(par_module):
        r = traiter(module, par_module[module], refus)
        if r is None:
            continue
        texte, n = r
        hisses += n
        ecrits += 1
        if args.ecrire:
            _chemin(module).write_text(texte, encoding="utf-8")
    n_refus = sum(len(v) for v in refus.values())
    print("[270-r4-r2-r2/hisser] %s : %d site(s) hisse(s) sur %d fichier(s) ; %d refus"
          % ("ECRIT" if args.ecrire else "SIMULE", hisses, ecrits, n_refus))
    for motif in sorted(refus):
        print("   refus %-22s %4d   ex. %s" % (motif, len(refus[motif]), refus[motif][0]))
    print("   PARTITION : %d hisses + %d refus = %d (candidats : %d) -> %s"
          % (hisses, n_refus, hisses + n_refus, n_sites,
             "OUI" if hisses + n_refus == n_sites else "NON -- INCOHERENT"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
