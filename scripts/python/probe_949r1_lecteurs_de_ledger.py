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


#: Vocabulaire de la VALEUR NATIVE dans ce corpus. Il ne designe pas une voie (un fichier peut
#: importer `rl_duel` sans rien confronter) mais une VALEUR issue du jeu, posee a cote de la
#: lecture du ledger port. Derive des 15 lecteurs deja conformes + des deux que #949 a corriges.
TOKENS_NATIFS = ("live", "hp_delta", "natif", "nat_", "amt", "observ")


def _fonctions_englobantes(tree):
    """Rend {lineno de la lecture -> corps source de la fonction englobante}. La CONFRONTATION se
    lit dans la fonction, pas sur la ligne : `off_total = last.get("total")` puis, dix lignes plus
    bas, `assert off_total == live_amt`."""
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fin = getattr(node, "end_lineno", None) or node.lineno
            spans.append((node.lineno, fin, node))
    return spans


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


def _classer(chemin, rapide=False):
    with open(chemin, encoding="utf-8") as f:
        src = f.read()
    if rapide and not any(m in src for m in MARQUEURS_SOURCE):
        # Mode CLIQUET : la partition des roles est un diagnostic du probe, pas du garde. Un
        # fichier sans marqueur ne peut porter aucun alias (cf. le pre-filtre ci-dessous), donc
        # aucun role de LECTURE SUR LEDGER -- le sauter ne change AUCUN des comptes du garde.
        return None
    tree = _annoter_parents(ast.parse(src, filename=chemin))
    # PRE-FILTRE, exact et DIT : tout alias de ledger derive, par construction du point fixe, d'une
    # expression SOURCE ; toute source porte l'un des marqueurs en TEXTE. Un fichier sans marqueur ne
    # peut donc porter aucun alias, et ne peut pas etre un lecteur de ledger. Ce filtre ne retire
    # aucun porteur -- il evite seulement l'`ast.unparse` des 2 700 fichiers sans marqueur. La
    # partition des ROLES, elle, reste calculee sur TOUS les fichiers.
    porte_marqueur = any(m in src for m in MARQUEURS_SOURCE)
    alias = _alias_du_fichier(tree) if porte_marqueur else set()
    roles = collections.Counter()
    lectures_par_cle = collections.Counter()     # toutes cles, toutes bases (temoin)
    lectures_ledger = 0                          # lectures d'un canal d'ARME SUR un alias
    lignes = []
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
            lignes.append(node.lineno)
        else:
            lit_179_sur_alias = True
    # Filet : un fichier peut recoller par une voie que l'AST ne relie pas a un alias (helper,
    # attribut, chaine construite). Le token brut est le filet, et il est DIT.
    lit_179_token = CLE_179 in src
    # ETAGE 3 -- la CONFRONTATION. Une lecture de ledger ne porte le vice que si la fonction qui la
    # contient met cette lecture EN FACE d'une valeur native. Le perimetre est la FONCTION (pas la
    # ligne) : `off_total = last.get("total")` puis, dix lignes plus bas, `== live_amt`.
    lignes_src = src.splitlines()
    spans = _fonctions_englobantes(tree)
    confrontations = {}
    for ln in set(lignes):
        englobantes = [(d, f) for d, f, _n in spans if d <= ln <= f]
        if englobantes:
            d, f = min(englobantes, key=lambda x: x[1] - x[0])
            corps = "\n".join(lignes_src[d - 1:f])
        else:
            corps = src            # lecture au niveau module : le fichier entier
        toks = sorted({t for t in TOKENS_NATIFS if t in corps})
        if toks:
            confrontations[ln] = toks
    return {
        "roles": roles,
        "lectures_par_cle": lectures_par_cle,
        "lectures_ledger": lectures_ledger,
        "lignes": sorted(set(lignes)),
        "confrontations": confrontations,
        "alias": sorted(alias),
        "lit_179_sur_alias": lit_179_sur_alias,
        "lit_179_token": lit_179_token,
        "natif": sorted({s for s in SIGNAUX_NATIF if s in src}),
        "src": src,
    }


#: SIGNAUX de confrontation a du NATIF. Ils ORDONNENT le tri, ils ne le TRANCHENT pas (le residu
#: dit que le critere se lit site par site). Deux familles, derivees du corpus :
#:   * la voie LIVE, par ou arrive le flux d'events natif ;
#:   * le vocabulaire de LEDGER natif (`hp_delta` est l'arbitre decisif de #949).
SIGNAUX_NATIF = ("observeBattle", "applyAction", "hp_delta", "aiPredict", "decisionView",
                 "runner_client", "rl_duel", "buildRunner", "Amount")


def _nature(chemin):
    """Ventile un site par NATURE. Un lecteur dans `engine/**` n'est pas un lecteur de
    confrontation : c'est le PORT lui-meme, et un canal manquant y serait un bug de PORT."""
    rel = os.path.relpath(chemin, _HERE).replace("\\", "/")
    if rel.startswith("engine/"):
        return "PORT (engine/**)"
    if rel.startswith("tests/"):
        return "TEST"
    if os.path.basename(rel).startswith("probe_"):
        return "PROBE"
    return "AUTRE"


def recenser(racine=None, rapide=True):
    """API du RECENSEMENT, appelable depuis un cliquet. Rend
    `{"porteurs": [...], "recollent": [...], "sous_comptent": [...], "confrontent": [...]}`,
    chemins RELATIFS a `scripts/python`, separateur `/` (stable entre Windows et POSIX).

    `rapide=True` saute les fichiers sans marqueur SOURCE : ce filtre est exact (aucun alias ne
    peut exister sans marqueur) et ne change aucun des quatre comptes.
    """
    racine = racine or _HERE
    porteurs, recollent, sous_comptent, confrontent = [], [], [], []
    for p in _fichiers_py(racine):
        try:
            info = _classer(p, rapide=rapide)
        except (SyntaxError, UnicodeDecodeError, RecursionError):
            continue
        if info is None or not info["lectures_ledger"]:
            continue
        rel = os.path.relpath(p, _HERE).replace("\\", "/")
        porteurs.append(rel)
        if info["lit_179_sur_alias"] or info["lit_179_token"]:
            recollent.append(rel)
            continue
        sous_comptent.append(rel)
        if info["confrontations"]:
            confrontent.append(rel)
    return {"porteurs": sorted(porteurs), "recollent": sorted(recollent),
            "sous_comptent": sorted(sous_comptent), "confrontent": sorted(confrontent)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="#949-r1 : recenseur des lecteurs de ledger")
    ap.add_argument("--liste", action="store_true", help="imprime la liste nommee de chaque classe")
    ap.add_argument("--confrontent", action="store_true",
                    help="restreint --sites/--liste aux fichiers de l'ETAGE 3 (confrontation)")
    ap.add_argument("--sites", action="store_true",
                    help="imprime CHAQUE site de lecture avec sa ligne source (tri site par site)")
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

    print("VENTILATION PAR NATURE des %d qui NE RECOLLENT PAS :" % len(sous_comptent))
    par_nature = collections.Counter(_nature(p) for p, _ in sous_comptent)
    for n, c in sorted(par_nature.items()):
        print("  %-22s %d" % (n, c))
    print("  -> un lecteur dans `engine/**` n'est PAS un lecteur de confrontation : c'est le PORT.")
    print("     Un canal manquant y serait un bug de PORT, pas un vice de lecteur.")
    print("")
    avec_natif = [x for x in sous_comptent if x[1]["natif"]]
    print("PARMI EUX, PORTENT UN SIGNAL DE VOIE NATIVE (import/appel) : %d (sur %d)"
          % (len(avec_natif), len(sous_comptent)))
    print("  signaux derives : %s" % ", ".join(SIGNAUX_NATIF))
    print("  -> une VOIE n'est pas une CONFRONTATION : un fichier peut monter un runner sans")
    print("     jamais mettre le ledger port en face d'une valeur du jeu.")
    print("")
    confrontent = [x for x in sous_comptent if x[1]["confrontations"]]
    print("ETAGE 3 -- CONFRONTENT (une valeur native est dans la FONCTION de la lecture) : %d"
          % len(confrontent))
    print("  vocabulaire derive : %s" % ", ".join(TOKENS_NATIFS))
    print("  ECARTES PAR CE CRITERE : %d fichiers -- ils lisent un canal d'arme sans le mettre"
          % (len(sous_comptent) - len(confrontent)))
    print("  en face d'aucune valeur du jeu (diagnostic, assertion de structure, rejeu")
    print("  offline contre offline). Le vice ne peut pas s'y exprimer.")
    print("")

    if args.sites:
        cible = confrontent if args.confrontent else sous_comptent
        for p, info in sorted(cible, key=lambda x: (-x[1]["lectures_ledger"], x[0])):
            lignes_src = info["src"].splitlines()
            print("=== %s  [%s] natif=%s"
                  % (os.path.relpath(p, _HERE), _nature(p), ",".join(info["natif"]) or "-"))
            for ln in info["lignes"]:
                txt = lignes_src[ln - 1].strip() if 0 < ln <= len(lignes_src) else "?"
                marque = "C" if ln in info["confrontations"] else " "
                print("  %s %5d | %s" % (marque, ln, txt[:140]))
        print("")

    if args.liste:
        print("--- NE RECOLLENT PAS (%d) ---" % len(sous_comptent))
        for p, info in sorted(sous_comptent, key=lambda x: (-x[1]["lectures_ledger"], x[0])):
            print("  %-70s lect=%d nat=%s alias=%s"
                  % (os.path.relpath(p, _HERE), info["lectures_ledger"],
                     ",".join(info["natif"][:3]) or "-",
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
