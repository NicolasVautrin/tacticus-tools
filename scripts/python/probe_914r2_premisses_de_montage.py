"""#914-r2 -- RECENSEUR des PREMISSES DE MONTAGE non executables portant sur une STAT DE BASE.

LE VICE (mesure #914) : deux des trois rouges de `master` du 2026-08-11 viennent d'une PREMISSE
ECRITE EN COMMENTAIRE -- << le crit est structurellement impossible >>, << la normalisation met la
crit a 0 >> -- vraie le jour ou elle a ete ecrite, FAUSSE depuis la bascule #419-r5 /#419-r6
(`_normalize_and_extract_pool` equipe les items Best-In-Slot PAR DEFAUT ; mesure sur le seed BC au
rank 17 : `could_crit` **0/106 -> 98/106**, `could_block` **0/106 -> 46/106**). Une premisse en
commentaire NE S'EXECUTE PAS : rien ne la confronte au harnais, et elle se signale des mois plus
tard par un test qui rougit **en accusant le port**.

LES QUATRE STATS CONCERNEES sont derivees du mirror `engine.entities.stats.StatType`, pas
enumerees a la main : ce sont celles que la formule rend a **0** sans items, donc les seules qui ne
vivent QUE dans l'equipement -- `BLOCK_CHANCE`, `BLOCK_DAMAGE`, `CRIT_CHANCE`, `CRIT_DAMAGE`
(`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` = `GetStat(9) > 0 && GetStat(10) > 0`).

DEUX FACTEURS, ET LE SECOND EST **VENTILE**, PAS APPLIQUE EN SILENCE :
  (a) le fragment NON EXECUTABLE (commentaire ou docstring) mentionne une de ces stats ;
  (b) il AFFIRME son absence / sa nullite / son impossibilite.
Le compte (a) est imprime EN ENTIER, et le compte de ce que (b) ECARTE aussi : un recenseur qui
n'imprimerait que (a et b) ne pourrait pas montrer la formulation qu'il a oubliee.

CE QU'IL NE FAIT PAS : trancher. Une premisse peut etre JUSTE (le montage force la stat par
`--unit-stat`, ou l'unite n'a structurellement pas de slot). Le tri se lit site par site.

Sortie : ASCII strict.

    python probe_914r2_premisses_de_montage.py            # ventilation
    python probe_914r2_premisses_de_montage.py --sites     # + chaque fragment, avec sa ligne
"""
from __future__ import annotations

import argparse
import ast
import collections
import io
import os
import re
import sys
import tokenize

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _stats_items_seuls():
    """Les stats qui valent 0 sans items -- DERIVEES du mirror, pas ecrites ici. Le critere est
    la famille CRIT/BLOCK, qui est exactement ce que les slots d'equipement portent (mesure
    #419-r5 : `Health`, `Damage`, `FixedArmor` restent INCHANGES quand on equipe)."""
    from engine.entities.stats import StatType
    return tuple(m for m in StatType if m.name.startswith(("CRIT_", "BLOCK_")))


#: Vocabulaire de la MENTION (facteur a). Derive des NOMS d'enum ci-dessus : le corpus ecrit
#: `crit`, `critique`, `block`, `bloc`, et les deux predicats natifs portes par le harnais.
def _tokens_mention(stats):
    toks = set()
    for m in stats:
        toks.add(m.name.lower())                     # crit_chance
        toks.add(m.name.lower().replace("_", ""))    # critchance
        toks.add(m.name.split("_")[0].lower())       # crit / block
    toks |= {"could_crit", "could_block", "couldcrit", "couldblock", "critique", "criti"}
    return tuple(sorted(toks))


def _regex_mention(toks):
    """Les tokens se cherchent en MOTS ENTIERS. Sans cela, `crit` matche `critere`, `critique de`,
    `description` -- mesure : le facteur (a) passait de 5 853 fragments a 1 137, soit **4 716 faux
    positifs** (81 %), et le complement de #933 de 49 fichiers a 12. Le texte est d'abord passe en
    minuscules, donc `critChance` -> `critchance` matche bien `\\bcritchance\\b`."""
    return re.compile(r"\b(?:%s)\b" % "|".join(re.escape(t) for t in sorted(toks, key=len,
                                                                           reverse=True)))


#: Vocabulaire de l'AFFIRMATION D'ABSENCE (facteur b). Chaque forme est presente dans le corpus ;
#: ce qu'elles ECARTENT est imprime, donc une forme oubliee se voit au compte des ecartes.
TOKENS_ABSENCE = ("impossible", "jamais", "aucun", "aucune", "pas de", "sans ", " nul",
                  "= 0", "=0", "a 0", "à 0", "zero", "zéro", "0/106", "n'a pas", "ne peut pas",
                  "structurellement", "n'existe pas", "exclu", "ecarte", "écarte", "no crit",
                  "non-crit", "non crit")

#: Vocabulaire du MONTAGE : la premisse parle-t-elle de ce qui FABRIQUE l'etat (normalisation,
#: seed, pool, items) ? C'est le troisieme axe du residu (<< toute premisse de MONTAGE de la
#: forme "la normalisation met X a 0" >>). Ventile, jamais applique en silence.
TOKENS_MONTAGE = ("normalis", "buildnormalizedbc", "seed", "pool", "item", "bis",
                  "montage", "rank", "progression", "unit-stat", "unit_stat", "equip")


def _fichiers(racine):
    """PERIMETRE derive de l'enonce du residu : `scripts/python/tests/**` et `probe_*.py`."""
    out = []
    tests = os.path.join(racine, "tests")
    for dp, dn, fn in os.walk(tests):
        dn[:] = [d for d in dn if d not in ("__pycache__",)]
        for f in fn:
            if f.endswith(".py"):
                out.append(os.path.join(dp, f))
    for f in os.listdir(racine):
        if f.startswith("probe_") and f.endswith(".py"):
            out.append(os.path.join(racine, f))
    return sorted(out)


def _fragments_non_executables(chemin):
    """Rend [(lineno, kind, texte)] : les COMMENTAIRES et les DOCSTRINGS.

    Les messages d'assertion sont volontairement EXCLUS : ce sont des chaines EXECUTABLES, donc
    exactement le cran que #914 a pose (<< la premisse devient une assertion sur l'etat live >>).
    Les compter comme premisses inverserait la mesure.
    """
    out = []
    with open(chemin, "rb") as fh:
        try:
            for tok in tokenize.tokenize(fh.readline):
                if tok.type == tokenize.COMMENT:
                    out.append((tok.start[0], "commentaire", tok.string))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
    try:
        with io.open(chemin, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=chemin)
    except (SyntaxError, UnicodeDecodeError):
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            d = ast.get_docstring(node, clean=False)
            if d:
                ln = getattr(node, "lineno", 1)
                for i, ligne in enumerate(d.splitlines()):
                    if ligne.strip():
                        out.append((ln + i, "docstring", ligne.strip()))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="#914-r2 : recenseur des premisses de montage")
    ap.add_argument("--sites", action="store_true", help="imprime chaque fragment retenu")
    ap.add_argument("--tout", action="store_true", help="--sites sur (a+b) au lieu de (a+b+c)")
    ap.add_argument("--racine", default=_HERE)
    args = ap.parse_args(argv)

    stats = _stats_items_seuls()
    mention = _tokens_mention(stats)
    rx_mention = _regex_mention(mention)
    print("STATS DERIVEES du mirror StatType (valent 0 sans items) : %s"
          % ", ".join("%s(%d)" % (m.name, int(m)) for m in stats))
    print("TOKENS DE MENTION derives de leurs noms : %s" % ", ".join(mention))
    print("")

    fichiers = _fichiers(args.racine)
    print("PERIMETRE : %d fichiers (tests/** + probe_*.py)" % len(fichiers))
    print("FILTRE APPLIQUE AU PERIMETRE : celui de l'enonce du residu. Le reste de "
          "`scripts/python/**` (engine/, outils) est ECARTE : il ne porte pas de MONTAGE.")
    print("")

    total_frag = 0
    a_seul = []          # facteur (a) : mentionne une stat crit/block
    a_et_b = []          # (a) + affirmation d'absence
    a_b_et_c = []        # (a) + (b) + vocabulaire de MONTAGE
    par_kind = collections.Counter()
    for p in fichiers:
        for ln, kind, txt in _fragments_non_executables(p):
            total_frag += 1
            bas = txt.lower()
            if not rx_mention.search(bas):
                continue
            par_kind[kind] += 1
            rec = (os.path.relpath(p, _HERE).replace("\\", "/"), ln, kind, txt.strip())
            a_seul.append(rec)
            if not any(t in bas for t in TOKENS_ABSENCE):
                continue
            a_et_b.append(rec)
            if any(t in bas for t in TOKENS_MONTAGE):
                a_b_et_c.append(rec)

    print("FRAGMENTS NON EXECUTABLES VISITES (commentaires + docstrings) : %d" % total_frag)
    print("  (a) MENTIONNENT une stat crit/block                          : %d" % len(a_seul))
    for k, n in sorted(par_kind.items()):
        print("        dont %-12s : %d" % (k, n))
    print("  (a+b) AFFIRMENT en plus une absence / nullite / impossibilite : %d" % len(a_et_b))
    print("        ECARTES PAR LE FACTEUR (b) : %d fragments -- ils parlent de crit/block"
          % (len(a_seul) - len(a_et_b)))
    print("        sans rien AFFIRMER de son absence (citation du natif, nom de variable,")
    print("        renvoi a un autre cas). Une formulation d'absence oubliee se lirait ICI.")
    print("  (a+b+c) parlent en plus de MONTAGE (normalisation/seed/pool/items)  : %d"
          % len(a_b_et_c))
    print("")
    fichiers_ab = sorted({r[0] for r in a_et_b})
    fichiers_abc = sorted({r[0] for r in a_b_et_c})
    # ETAGE 4 -- LE COMPLEMENT DE #933. `probe_933_premisses_regime.py` a livre le cran executable
    # que #914 §4.1 reclamait, et il DIT son perimetre : << Il visite TOUS les `test_*.py` de
    # `scripts/python/tests/`. Il ne visite PAS les probes `scripts/python/probe_*.py`, ni la face
    # DECISION hors tests, ni ce qu'un test atteint via la fixture d'un autre paquet. >>
    # Ce qui reste de #914-r2 est donc exactement ce complement.
    couvert = [f for f in fichiers_abc
               if f.startswith("tests/") and os.path.basename(f).startswith("test_")]
    complement = [f for f in fichiers_abc if f not in couvert]
    print("ETAGE 4 -- COUVERTURE PAR LE CLIQUET #933 (`test_933_premisse_regime_offline.py`) :")
    print("  DEJA VISITES par #933 (tests/**/test_*.py)         : %d" % len(couvert))
    print("  COMPLEMENT -- que #933 declare NE PAS visiter      : %d" % len(complement))
    print("     -> probes `probe_*.py` et helpers de test hors `test_*.py`. Un probe ne ROUGIT")
    print("        pas : une premisse fausse n'y casse rien, elle fait CONCLURE faux -- c'est")
    print("        exactement ce qui a produit le faux verdict << 8 coups natif contre 6 >> de #949.")
    for f in complement:
        print("        %s" % f)
    print("")
    print("FICHIERS PORTEURS D'AU MOINS UNE PREMISSE (a+b)   : %d" % len(fichiers_ab))
    print("FICHIERS PORTEURS D'AU MOINS UNE PREMISSE (a+b+c) : %d  <- le perimetre du residu"
          % len(fichiers_abc))
    for f in fichiers_abc:
        n = sum(1 for r in a_et_b if r[0] == f)
        m = sum(1 for r in a_b_et_c if r[0] == f)
        print("  %-70s (a+b)=%d (a+b+c)=%d" % (f, n, m))
    print("")

    if args.sites:
        cible = a_b_et_c if not args.tout else a_et_b
        print("--- FRAGMENTS %s, par fichier ---" % ("(a+b)" if args.tout else "(a+b+c)"))
        courant = None
        for r in sorted(cible):
            if r[0] != courant:
                courant = r[0]
                print("=== %s" % courant)
            marque = "M" if r in a_b_et_c else " "
            print("  %s %5d [%-11s] %s" % (marque, r[1], r[2], r[3][:170]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
