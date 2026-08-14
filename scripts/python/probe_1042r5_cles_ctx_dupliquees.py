"""#1042-r5 -- recense les CHAINES de cle de contexte DECLAREES dans plusieurs modules.

Le vice (trouve en resolvant le merge #1055 x #1056) : deux tranches ont pose la MEME
chaine de cle dans le MEME literal de dict de `runner/damage_model.defender_modifiers`,
chacune via SA propre constante, chacune se declarant << foyer unique >>. Python garde la
derniere, en silence. Tant que N constantes portent la meme chaine, une tranche qui
renomme l'une croit deplacer le foyer et n'en deplace qu'une fraction -- les autres
continuent de poser l'ancienne chaine, sans erreur.

CE QUE CE PROBE VISITE, et pourquoi le critere est DERIVE et non une liste blanche :
un recenseur ne peut pas rendre zero sur ce qu'il ne visite pas. Il balaye donc TOUTES
les affectations de constante-chaine de `engine/**` -- au niveau MODULE et au niveau
CLASSE (le gisement en portait une de chaque : `damage_reduction.CTX_TERTIARY_ABILITY_
STATE_OF` est un module, `damage_reduction.<classe>.CTX_ABILITY_STATE_OF` est un
attribut de classe) -- et retient celles dont le NOM porte le marqueur `CTX`. Le nom est
le seul discriminant disponible : la chaine, elle, ne dit pas qu'elle est une cle de ctx.

Ce qu'il NE voit PAS, et il le DIT :
  * un literal NU pose directement dans un dict de ctx (`"tertiary_ability_state_of":
    ...` au site de pose) -- il n'y a pas de constante a apparier. Ils sont comptes a
    part, sous ETAGE 2, comme un gisement DISTINCT ;
  * une constante de cle de ctx qui ne porterait pas `CTX` dans son nom.

Sortie ASCII stricte (cp1252). rc 0 = aucune chaine multi-modules ; rc 1 sinon.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_MARQUEUR = "CTX"


def _racine_engine() -> Path:
    return Path(__file__).resolve().parent / "engine"


def _constantes_ctx(chemin: Path, table_globale=None):
    """Rend [(nom_qualifie, chaine, ligne, directe)] des constantes-chaines a marqueur CTX.

    Visite le niveau MODULE et le niveau CLASSE. Le corps d'une fonction est ecarte :
    une constante locale n'est lisible par personne d'autre, donc elle ne peut pas
    fabriquer un second foyer.

    `directe` = la chaine est ecrite ICI en LITTERAL. Seules les declarations DIRECTES
    entrent dans le verdict multi-modules : une RE-EXPORTATION depuis le foyer
    (`CTX_X = _ctx_keys.Y`) est exactement la reparation qu'on veut, pas le vice.

    ⚠ Ce second mode existe parce que le probe s'est rendu AVEUGLE tout seul : apres la
    migration #1042-r5, les 14 sites ne sont plus des `NOM = "literal"` mais des
    `NOM = _ctx_keys.TERTIARY_ABILITY_STATE_OF`. La table de resolution s'etait videe, et
    l'etage 3 -- qui en depend -- rendait 0 sur une mutation qui reproduisait pourtant la
    cause racine EXACTE. Trouve par MUTATION, jamais par relecture.
    """
    try:
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    trouves = []
    alias_importes = {}

    def _resoudre_indirect(valeur):
        if table_globale is None:
            return None
        nom = None
        if isinstance(valeur, ast.Attribute):
            nom = valeur.attr
        elif isinstance(valeur, ast.Name):
            nom = alias_importes.get(valeur.id, valeur.id)
        if nom is None:
            return None
        vals = table_globale.get(nom)
        return next(iter(vals)) if vals and len(vals) == 1 else None

    def _visiter(corps, prefixe):
        for noeud in corps:
            if isinstance(noeud, ast.ClassDef):
                _visiter(noeud.body, prefixe + noeud.name + ".")
                continue
            if isinstance(noeud, ast.ImportFrom):
                for alias in noeud.names:
                    alias_importes[alias.asname or alias.name] = alias.name
                    if _MARQUEUR in (alias.asname or alias.name) or _MARQUEUR in alias.name:
                        chaine = _resoudre_indirect(ast.Name(id=alias.asname or alias.name))
                        if chaine is not None:
                            trouves.append((prefixe + (alias.asname or alias.name), chaine,
                                            noeud.lineno, False))
                continue
            if not isinstance(noeud, ast.Assign):
                continue
            for cible in noeud.targets:
                if not (isinstance(cible, ast.Name) and _MARQUEUR in cible.id):
                    continue
                if isinstance(noeud.value, ast.Constant) and isinstance(noeud.value.value, str):
                    trouves.append((prefixe + cible.id, noeud.value.value, noeud.lineno, True))
                else:
                    chaine = _resoudre_indirect(noeud.value)
                    if chaine is not None:
                        trouves.append((prefixe + cible.id, chaine, noeud.lineno, False))

    _visiter(arbre.body, "")
    return trouves


def _cles_nues(chemin: Path, chaines):
    """Rend [(chaine, ligne)] des literaux NUS utilises comme CLE d'un dict litteral.

    Restreint aux chaines que l'etage 1 a vues declarees quelque part : un literal nu
    n'est un doublon que s'il double une constante existante.
    """
    try:
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return []
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Dict):
            continue
        for cle in noeud.keys:
            if isinstance(cle, ast.Constant) and isinstance(cle.value, str) and cle.value in chaines:
                trouves.append((cle.value, cle.lineno))
    return trouves


def _liaisons_locales(arbre, par_nom_court):
    """Rend {nom_lie_dans_ce_fichier: chaine} pour les constantes de cle de ctx.

    Trois voies de liaison, et il en fallait TROIS parce que le gisement les emploie
    toutes : l'affectation directe (`X = "s"`), l'import avec alias
    (`from m import CTX_A as _B` -- la forme employee par `damage_model.py`), et
    l'attribut (`_ctx_keys.TERTIARY_...`, `self.CTX_ABILITY_STATE_OF`), resolu par le
    NOM COURT de l'attribut contre la table globale. Une resolution AMBIGUE (deux
    chaines pour un meme nom court) est ECARTEE plutot que devinee.
    """
    liaisons = {}
    classes_locales = set()

    def _par_nom(nom):
        vals = par_nom_court.get(nom)
        return next(iter(vals)) if vals and len(vals) == 1 else None

    def _visiter(corps, dans_classe=False):
        for noeud in corps:
            if isinstance(noeud, ast.ClassDef):
                # ⚠ NE PAS descendre dans le corps d'une classe en APLATISSANT ses attributs.
                # Mesure du 2026-08-14 : `power_up.py` definit CINQ classes portant chacune un
                # `ABILITY_NAME` DIFFERENT ; les aplatir faisait resoudre les cinq cles
                # `PowerUpXxxAbility.ABILITY_NAME` vers la MEME chaine, donc un faux
                # << cle posee 5 fois dans le meme dict >>. Un attribut de classe n'est
                # accessible que via SON receveur -- il n'appartient pas a l'espace plat.
                classes_locales.add(noeud.name)
                continue
            if isinstance(noeud, ast.ImportFrom):
                for alias in noeud.names:
                    chaine = _par_nom(alias.name)
                    if chaine is not None:
                        liaisons[alias.asname or alias.name] = chaine
            elif isinstance(noeud, ast.Assign):
                for cible in noeud.targets:
                    if not isinstance(cible, ast.Name):
                        continue
                    if isinstance(noeud.value, ast.Constant) and isinstance(noeud.value.value, str):
                        liaisons[cible.id] = noeud.value.value
                    elif isinstance(noeud.value, ast.Attribute):
                        chaine = _par_nom(noeud.value.attr)
                        if chaine is not None:
                            liaisons[cible.id] = chaine
                    elif isinstance(noeud.value, ast.Name) and noeud.value.id in liaisons:
                        liaisons[cible.id] = liaisons[noeud.value.id]

    _visiter(arbre.body)
    return liaisons, classes_locales


def _cles_dupliquees_dans_un_dict(chemin: Path, par_nom_court):
    """Rend [(ligne_du_dict, chaine, [lignes des cles])] -- LE cran de la cause racine.

    C'est exactement le defaut de #1055 x #1056 : deux tranches ont pose la MEME chaine
    dans le MEME literal de dict de `defender_modifiers`, chacune via SA constante.
    Python garde la derniere, sans erreur. Aucun test ne pouvait le voir : la valeur
    gagnante etait la bonne par chance.

    Une cle est resolue si elle est un literal, un nom lie localement, ou un attribut
    dont le nom court designe UNE seule chaine. Les cles non resolues sont ignorees --
    elles ne peuvent pas prouver un doublon.
    """
    try:
        source = chemin.read_text(encoding="utf-8")
        arbre = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return []
    liaisons, classes_locales = _liaisons_locales(arbre, par_nom_court)

    def _resoudre(cle):
        if isinstance(cle, ast.Constant) and isinstance(cle.value, str):
            return cle.value
        if isinstance(cle, ast.Name):
            return liaisons.get(cle.id)
        if isinstance(cle, ast.Attribute):
            # Un attribut porte par une CLASSE definie ici n'est PAS resolvable par son nom
            # court : deux classes du meme module peuvent porter le meme nom d'attribut avec
            # des valeurs DIFFERENTES (mesure : les cinq `PowerUpXxxAbility.ABILITY_NAME`).
            if isinstance(cle.value, ast.Name) and cle.value.id in classes_locales:
                return None
            if cle.attr in liaisons:
                return liaisons[cle.attr]
            vals = par_nom_court.get(cle.attr)
            return next(iter(vals)) if vals and len(vals) == 1 else None
        return None

    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Dict):
            continue
        vues = {}
        for cle in noeud.keys:
            if cle is None:                       # `**autre` : pas une cle
                continue
            chaine = _resoudre(cle)
            if chaine is None:
                continue
            vues.setdefault(chaine, []).append(cle.lineno)
        for chaine, lignes in vues.items():
            if len(lignes) > 1:
                trouves.append((noeud.lineno, chaine, lignes))
    return trouves


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbeux", action="store_true", help="liste TOUTES les chaines, pas seulement les partagees")
    args = ap.parse_args()

    racine = _racine_engine()
    fichiers = sorted(racine.rglob("*.py"))
    if not fichiers:
        print("[1042-r5] ECHEC : aucun fichier sous %s" % racine)
        return 2

    # etage 1 -- les constantes. DEUX passes : les LITTERAUX d'abord (ils fondent la
    # table de resolution), les indirects ensuite (ils s'y resolvent).
    directes = {}
    for f in fichiers:
        for nom, chaine, ligne, _d in _constantes_ctx(f):
            directes.setdefault(chaine, []).append((f.relative_to(racine).as_posix(), nom, ligne))
    table = {}
    for chaine, decls in directes.items():
        for _m, nom, _l in decls:
            table.setdefault(nom.rsplit(".", 1)[-1], set()).add(chaine)

    par_chaine, indirectes = {}, 0
    for f in fichiers:
        for nom, chaine, ligne, directe in _constantes_ctx(f, table):
            par_chaine.setdefault(chaine, []).append(
                (f.relative_to(racine).as_posix(), nom, ligne, directe))
            indirectes += 0 if directe else 1

    print("[1042-r5] PORTEE : %d fichier(s) sous engine/, marqueur de nom = %r" % (len(fichiers), _MARQUEUR))
    print("[1042-r5] ETAGE 1 -- cles de ctx : %d chaine(s) distincte(s), %d liaison(s) "
          "(%d LITTERALES, %d re-exportees depuis un foyer)"
          % (len(par_chaine), sum(len(v) for v in par_chaine.values()),
             sum(len(v) for v in par_chaine.values()) - indirectes, indirectes))

    partagees = {}
    for chaine, decls in sorted(par_chaine.items()):
        mod_litt = {m for (m, _n, _l, d) in decls if d}
        if len(mod_litt) > 1:
            partagees[chaine] = [x for x in decls if x[3]]
        if args.verbeux:
            print("    %-46s %d liaison(s) / %d module(s) LITTERAL"
                  % (chaine, len(decls), len(mod_litt)))

    if partagees:
        print("[1042-r5] MULTI-MODULES (le vice) : %d chaine(s)" % len(partagees))
        for chaine, decls in sorted(partagees.items()):
            print("  chaine %r -- %d declaration(s) LITTERALE(s) dans %d module(s) :"
                  % (chaine, len(decls), len({m for (m, _n, _l, _d) in decls})))
            for module, nom, ligne, _d in sorted(decls):
                print("      %s:%d  %s" % (module, ligne, nom))
    else:
        print("[1042-r5] MULTI-MODULES : aucune -- chaque chaine de cle a UN seul module DECLARANT")

    # etage 2 -- les literaux NUS, gisement DISTINCT (non bloquant, compte seulement)
    connues = set(par_chaine)
    nus = {}
    for f in fichiers:
        for chaine, ligne in _cles_nues(f, connues):
            nus.setdefault(chaine, []).append((f.relative_to(racine).as_posix(), ligne))
    total_nus = sum(len(v) for v in nus.values())
    print("[1042-r5] ETAGE 2 -- literaux NUS en cle de dict doublant une constante : %d site(s) sur %d chaine(s)"
          % (total_nus, len(nus)))
    print("           (gisement DISTINCT : un literal nu n'a pas de constante a apparier ;")
    print("            il est COMPTE, jamais rendu comme un zero, et n'entre pas dans le verdict)")
    if args.verbeux:
        for chaine, sites in sorted(nus.items()):
            for module, ligne in sorted(sites):
                print("      %s:%d  %r" % (module, ligne, chaine))

    # etage 3 -- LE cran de la cause racine : deux cles d'un MEME dict pour une MEME chaine
    par_nom_court = {}
    for chaine, decls in par_chaine.items():
        for _m, nom, _l, _d in decls:
            par_nom_court.setdefault(nom.rsplit(".", 1)[-1], set()).add(chaine)
    doublons = []
    for f in fichiers:
        for ligne_dict, chaine, lignes in _cles_dupliquees_dans_un_dict(f, par_nom_court):
            doublons.append((f.relative_to(racine).as_posix(), ligne_dict, chaine, lignes))
    print("[1042-r5] ETAGE 3 -- meme chaine posee DEUX fois dans un MEME dict litteral : %d cas"
          % len(doublons))
    for module, ligne_dict, chaine, lignes in sorted(doublons):
        print("      %s: dict ligne %d -- %r aux lignes %s (Python garde la DERNIERE)"
              % (module, ligne_dict, chaine, lignes))

    if partagees or doublons:
        if partagees:
            print("[1042-r5] FAIL -- une chaine de cle de ctx declaree dans plusieurs modules")
        if doublons:
            print("[1042-r5] FAIL -- une cle de ctx posee deux fois dans le meme dict")
        return 1
    print("[1042-r5] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
