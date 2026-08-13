"""#949-r1 -- RECENSEUR des LECTEURS de ledger d'attaque, et de ceux qui SOUS-COMPTENT le canal #179.

LE VICE (mesure #949) : `damage_ops/normal.py::execute` publie la phase d'ARME dans `per_hit` /
`total` / `hits`, et les coups du canal #179 (les sous-operations
`IdunBattle.Operations.ExecuteAdditionalHitsWithDamageProfileTypeOperation$$Execute`) A COTE, dans
`additional_hits` -- deux sous-operations natives distinctes, donc deux cles. Tout lecteur qui
confronte un ledger NATIF (un flux d'events UNIQUE) au seul `per_hit`/`total` SOUS-COMPTE des que
l'attaquant porte un descripteur #179 actif, et la degradation est SILENCIEUSE : elle se lit comme
un bug de port (<< 8 coups natif contre 6 port >>).

LE DISCRIMINANT EST LA **PROVENANCE**, PAS LE NOM DE LA CLE. Un premier recensement par nom de cle
a rendu **478** fichiers porteurs et **412** a trier : `total` et `hits` sont des cles generiques du
corpus, et le vice ne porte QUE sur le dict produit par l'operation d'attaque du port. Ce probe
derive donc, par fichier, les expressions SOURCE DE LEDGER, propage leurs alias, et ne compte que
les lectures faites SUR CES ALIAS.

CE QUE CE PROBE NE FAIT PAS : trancher. Le critere final -- << ce site COMPARE-t-il un ledger
natif ? >> -- se lit site par site (c'est ecrit dans le residu). Ce probe DERIVE le perimetre et le
reduit, il ne le decide pas.

POURQUOI IL VISITE TOUT (doctrine << un recenseur ne peut pas rendre zero sur ce qu'il ne visite
pas >>) :
  * il visite TOUS les `.py` sous `scripts/python/` -- aucune liste blanche de repertoire ;
  * les SOURCES de ledger sont DERIVEES du code du port (les trois producteurs du dict), pas
    enumerees a l'intuition, et toute expression source non reconnue reste comptee sous
    `sources non nommees` ;
  * les roles des constantes-cles sont derives du noeud PARENT ; un role inconnu sort sous
    `autre (<Noeud>)`, jamais ignore ; la somme des roles est une PARTITION EXHAUSTIVE ;
  * tout compte filtre DIT ce qu'il filtre.

Sortie : ASCII strict.

    python probe_949r1_lecteurs_de_ledger.py             # recensement + ventilation
    python probe_949r1_lecteurs_de_ledger.py --liste      # + la liste NOMMEE de chaque classe
    python probe_949r1_lecteurs_de_ledger.py --par-cle    # le recensement PAR NOM DE CLE (temoin)
"""
from __future__ import annotations

import argparse
import ast
import collections
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

#: Les cles du contrat de `normal.py::execute` qui portent le vice : les canaux de la PHASE D'ARME
#: (ce que le lecteur fautif lit seul).
CLES_ARME = ("per_hit", "total", "hits")
#: Le canal #179 -- ce que le lecteur doit RECOLLER.
CLE_179 = "additional_hits"
CLES = CLES_ARME + (CLE_179,)

#: SOURCES DE LEDGER. Derivees du code du port, pas de l'intuition :
#:   * `damage_handler.last` -- le champ que `DamageHandler.handle` affecte depuis
#:     `AttackDamageOperation.execute` (`engine/runner/operations/damage.py`), et le seul que le
#:     residu #949-r1 nomme ;
#:   * `AttackDamageOperation.execute` / `execute_normal_attack` -- les producteurs directs ;
#:   * `execute_additional_hits` -- le producteur du canal #179 lui-meme.
#: Toute expression dont l'`unparse` contient l'un de ces marqueurs est une source.
MARQUEURS_SOURCE = (".damage_handler.last", "damage_handler.last",
                    "AttackDamageOperation.execute", "execute_normal_attack",
                    "execute_additional_hits")


def _fichiers_py(racine):
    """PERIMETRE. Tous les `.py` sous `racine`, sans exception de repertoire.

    Le seul ecart possible est un fichier illisible ou non parsable : il est COMPTE et NOMME
    (`illisibles`), jamais silencieusement absent.
    """
    out = []
    for dp, dn, fn in os.walk(racine):
        dn[:] = [d for d in dn if d not in (".git", "__pycache__")]
        for f in fn:
            if f.endswith(".py"):
                out.append(os.path.join(dp, f))
    return sorted(out)


def _annoter_parents(tree):
    for node in ast.walk(tree):
        for enfant in ast.iter_child_nodes(node):
            enfant._949_parent = node
    return tree


def _role(noeud, parent):
    """DERIVE le role d'une constante-cle depuis son noeud PARENT. Jamais une liste blanche :
    tout parent non reconnu sort sous `autre (<Noeud>)`."""
    if parent is None:
        return "autre (racine)"
    if isinstance(parent, ast.Subscript) and parent.slice is noeud:
        return "LECTURE (d[cle])"
    if isinstance(parent, ast.Call):
        fn = parent.func
        if isinstance(fn, ast.Attribute) and fn.attr in ("get", "pop", "setdefault"):
            if parent.args and parent.args[0] is noeud:
                return "LECTURE (d.%s(cle))" % fn.attr
        return "argument d'appel"
    if isinstance(parent, ast.Dict) and noeud in parent.keys:
        return "ECRITURE (cle de dict litteral)"
    if isinstance(parent, ast.Compare):
        return "test (in / ==)"
    if isinstance(parent, (ast.Tuple, ast.List, ast.Set)):
        return "element de conteneur"
    if isinstance(parent, ast.keyword):
        return "argument nomme"
    if isinstance(parent, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return "affectation"
    if isinstance(parent, ast.Return):
        return "valeur de retour"
    if isinstance(parent, (ast.JoinedStr, ast.FormattedValue)):
        return "chaine formatee"
    if isinstance(parent, ast.Expr):
        return "expression"
    return "autre (%s)" % type(parent).__name__


def _est_source(expr):
    """Une expression est SOURCE DE LEDGER si son texte porte l'un des marqueurs derives."""
    try:
        txt = ast.unparse(expr)
    except Exception:
        return False
    return any(m in txt for m in MARQUEURS_SOURCE)


def _alias_du_fichier(tree):
    """Propage les alias de ledger jusqu'au POINT FIXE (borne a 8 tours -- le corpus ne depasse
    pas 3). Un nom devient alias s'il est affecte depuis une expression qui est deja une source,
    OU depuis une lecture `<alias>.get("additional_hits")` (le canal #179 est lui-meme un ledger).
    """
    alias = set()
    for _tour in range(8):
        avant = len(alias)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.withitem)):
                continue
            val = getattr(node, "value", None) or getattr(node, "context_expr", None)
            if val is None:
                continue
            src = _est_source(val)
            if not src:
                try:
                    txt = ast.unparse(val)
                except Exception:
                    txt = ""
                src = any(("%s[" % a) in txt or ("%s.get(" % a) in txt or txt.strip() == a
                          for a in alias)
                # un alias derive ne compte que s'il porte encore le DICT (pas une de ses valeurs
                # scalaires) : on ne retient que les acces au canal #179, qui est lui-meme un dict.
                if src and CLE_179 not in txt and not any(txt.strip() == a for a in alias):
                    src = False
            if not src:
                continue
            cibles = node.targets if isinstance(node, ast.Assign) else [
                getattr(node, "target", None) or getattr(node, "optional_vars", None)]
            for t in cibles:
                if isinstance(t, ast.Name):
                    alias.add(t.id)
                elif isinstance(t, (ast.Tuple, ast.List)):
                    for e in t.elts:
                        if isinstance(e, ast.Name):
                            alias.add(e.id)
        if len(alias) == avant:
            break
    return alias


def _base_de_lecture(noeud, parent):
    """Rend le TEXTE de l'objet sur lequel la lecture est faite (`d` dans `d["per_hit"]`)."""
    try:
        if isinstance(parent, ast.Subscript):
            return ast.unparse(parent.value)
        if isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute):
            return ast.unparse(parent.func.value)
    except Exception:
        return ""
    return ""


def _classer(chemin):
    with open(chemin, encoding="utf-8") as f:
        src = f.read()
    tree = _annoter_parents(ast.parse(src, filename=chemin))
    alias = _alias_du_fichier(tree)
    roles = collections.Counter()
    lectures_par_cle = collections.Counter()     # toutes cles, toutes bases (temoin)
    lectures_ledger = 0                          # lectures d'un canal d'ARME SUR un alias
    lit_179_sur_alias = False
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if node.value not in CLES:
            continue
        parent = getattr(node, "_949_parent", None)
        r = _role(node, parent)
        roles[(node.value, r)] += 1
        if not r.startswith("LECTURE"):
            continue
        lectures_par_cle[node.value] += 1
        base = _base_de_lecture(node, parent)
        sur_ledger = any(base == a or base.startswith(a + ".") or base.startswith(a + "[")
                         for a in alias) or any(m in base for m in MARQUEURS_SOURCE)
        if not sur_ledger:
            continue
        if node.value in CLES_ARME:
            lectures_ledger += 1
        else:
            lit_179_sur_alias = True
    # Filet : un fichier peut recoller par une voie que l'AST ne relie pas a un alias (helper,
    # attribut, chaine construite). Le token brut est le filet, et il est DIT.
    lit_179_token = CLE_179 in src
    return {
        "roles": roles,
        "lectures_par_cle": lectures_par_cle,
        "lectures_ledger": lectures_ledger,
        "alias": sorted(alias),
        "lit_179_sur_alias": lit_179_sur_alias,
        "lit_179_token": lit_179_token,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="#949-r1 : recenseur des lecteurs de ledger")
    ap.add_argument("--liste", action="store_true", help="imprime la liste nommee de chaque classe")
    ap.add_argument("--par-cle", action="store_true",
                    help="imprime aussi le recensement PAR NOM DE CLE (le temoin sur-compte)")
    ap.add_argument("--racine", default=_HERE)
    args = ap.parse_args(argv)

    fichiers = _fichiers_py(args.racine)
    print("PERIMETRE : %d fichiers .py sous %s"
          % (len(fichiers), os.path.relpath(args.racine, _HERE) or "."))
    print("FILTRE APPLIQUE AU PERIMETRE : aucun (tous les .py, tous les repertoires).")
    print("")

    illisibles = []
    roles_globaux = collections.Counter()
    par_cle_globaux = collections.Counter()
    porteurs_par_cle = 0
    porteurs = []
    for p in fichiers:
        try:
            info = _classer(p)
        except (SyntaxError, UnicodeDecodeError, RecursionError) as exc:
            illisibles.append((p, type(exc).__name__))
            continue
        roles_globaux.update(info["roles"])
        par_cle_globaux.update(info["lectures_par_cle"])
        if any(info["lectures_par_cle"].get(c, 0) for c in CLES_ARME):
            porteurs_par_cle += 1
        if info["lectures_ledger"]:
            porteurs.append((p, info))

    print("ROLES DERIVES (partition exhaustive des constantes-cles visitees) :")
    total_roles = 0
    for (cle, role), n in sorted(roles_globaux.items(), key=lambda kv: (-kv[1], kv[0])):
        print("  %-18s %-32s %d" % (cle, role, n))
        total_roles += n
    print("  %-18s %-32s %d" % ("TOTAL", "(somme des roles)", total_roles))
    print("")
    if illisibles:
        print("ILLISIBLES (comptes, pas ignores) : %d" % len(illisibles))
        for p, k in illisibles:
            print("  %s  [%s]" % (os.path.relpath(p, _HERE), k))
        print("")

    if args.par_cle:
        print("TEMOIN -- recensement PAR NOM DE CLE (sans provenance) :")
        print("  fichiers portant au moins une LECTURE d'un canal d'arme : %d" % porteurs_par_cle)
        for c in CLES_ARME:
            print("    lectures de `%s` : %d" % (c, par_cle_globaux.get(c, 0)))
        print("  -> ce compte SUR-COMPTE : `total`/`hits` sont des cles generiques du corpus.")
        print("     Le vice ne porte que sur le dict produit par l'operation d'attaque.")
        print("")

    recollent = [x for x in porteurs if x[1]["lit_179_sur_alias"]]
    filet = [x for x in porteurs
             if not x[1]["lit_179_sur_alias"] and x[1]["lit_179_token"]]
    sous_comptent = [x for x in porteurs
                     if not x[1]["lit_179_sur_alias"] and not x[1]["lit_179_token"]]
    print("PERIMETRE DU VICE -- fichiers lisant un canal d'ARME **SUR UN LEDGER** : %d"
          % len(porteurs))
    print("  RECOLLENT (lisent `additional_hits` sur le meme ledger)         : %d" % len(recollent))
    print("  FILET (le token `additional_hits` est present, lien AST non vu) : %d" % len(filet))
    print("  NE RECOLLENT PAS (le token est absent du fichier)               : %d"
          % len(sous_comptent))
    print("")
    print("  -> les %d de la derniere classe sont le perimetre A TRIER. Le critere reel est"
          % len(sous_comptent))
    print("     << ce site compare-t-il un ledger NATIF ? >>, qui se lit site par site :")
    print("     un site qui ne confronte RIEN (diagnostic, assertion sur un seul coup) ne porte")
    print("     pas le vice, meme s'il ne recolle pas.")
    print("")

    if args.liste:
        print("--- NE RECOLLENT PAS (%d) ---" % len(sous_comptent))
        for p, info in sorted(sous_comptent, key=lambda x: (-x[1]["lectures_ledger"], x[0])):
            print("  %-70s lect=%d alias=%s"
                  % (os.path.relpath(p, _HERE), info["lectures_ledger"],
                     ",".join(info["alias"][:4]) or "-"))
        print("")
        print("--- FILET (%d) ---" % len(filet))
        for p, info in sorted(filet):
            print("  %-70s lect=%d" % (os.path.relpath(p, _HERE), info["lectures_ledger"]))
        print("")
        print("--- RECOLLENT (%d) ---" % len(recollent))
        for p, info in sorted(recollent):
            print("  %-70s lect=%d" % (os.path.relpath(p, _HERE), info["lectures_ledger"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
