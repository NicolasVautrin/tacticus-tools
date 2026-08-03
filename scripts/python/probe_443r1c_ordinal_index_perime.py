#!/usr/bin/env python
"""Probe #443-r1c -- un INDICE litteral qui vaut l'ordinal ARCHIVE d'un membre cite sur sa ligne.

POURQUOI CE CLIQUET EXISTE
--------------------------
#443-r1c a mesure la faute sur `probe_193c_move_playbook_terms.py` :

    p_x = p_tot - leaves.get(8, 0.0) - leaves.get(9, 0.0)      # 8=Elevation 10=TileEffects

`8` et `9` sont les ordinaux de `gqfc5mff6c`. Depuis l'insertion d'`AttackTile` en 8 (#252),
`Elevation` vaut 9 et `TileEffects` 10. Le site retranchait donc une feuille INEXISTANTE
(`AttackTile`, absente de `TILE_LEAVES` -> `.get` rend `0.0`) et ne retranchait JAMAIS
`TileEffects`, alors que le membre natif de la comparaison, lui, l'exclut. Ecart silencieux, nul
tant qu'aucune tuile candidate ne porte d'effet : c'est ce qui l'a fait durer.

CE QUE `probe_283` NE POUVAIT PAS VOIR -- les deux angles morts, MESURES
-----------------------------------------------------------------------
1. `--step exec` ne visite que `ast.Subscript`. Un indice passe par ACCESSEUR
   (`.get` / `.pop` / `.setdefault`) n'est visite par aucun de ses motifs : `visit_Call` ne sert
   que les signatures POSITIONNELLES derivees, et `get` n'en est pas une. S'y ajoute que son
   heuristique `_root_of` lit le NOM du recepteur : `leaves` ne porte aucune racine `_ROOTS`.
2. `--step prose` ecarte les membres AMBIGUS -- ceux qui existent dans PLUSIEURS enums du build a
   des ordinaux differents -- quand la ligne ne NOMME pas l'enum (etape 4), et
   INCONDITIONNELLEMENT a l'etape 4bis. Or `Elevation` est ambigu : mesure du 2026-08-02,
   `IdunBattle.Configuration.UtilityType` = 9, `IdunBattle.Core.Services.DamageModifierSource` = 0,
   `idun.meta.ObscuringType` = 2.

D'ou le vice qui a fait durer le bug : LE COMMENTAIRE S'AUTO-ATTESTE A MOITIE. Sa moitie JUSTE
(`10=TileEffects`, non ambigu) est vue par l'etape 4 et comptee parmi ses ~1200 citations justes ;
sa moitie FAUSSE (`8=Elevation`, ambigu) est structurellement invisible. Le rapport de couverture
etait donc VERT sur une ligne a moitie fausse.

LE CRITERE, ET POURQUOI IL EST SUR SUR LES AMBIGUS
--------------------------------------------------
Un indice litteral `v` est ROUGE si, pour un membre `m` cite dans la PROSE de sa ligne :

  * il existe un enum ou `m` valait `v` sur le build ARCHIVE et ne le vaut PLUS aujourd'hui
    (donc `v` est l'ancien ordinal de `m`) ;
  * et `m` ne vaut `v` dans AUCUN enum du build COURANT.

C'est cette seconde clause qui rend l'ambiguite inoffensive, et c'est ce qui permet d'aller la ou
4bis renonce : un nom ambigu n'est ecarte que s'il existe une lecture ACTUELLE qui justifie le
nombre. Sinon, un nombre qui vaut exactement l'ordinal archive d'un membre cite a cote n'a aucune
autre explication qu'une citation perimee -- c'est le meme raisonnement que 4bis, mais rendu
decidable membre par membre au lieu d'etre abandonne en bloc.

Rien n'est saisi a la main : les enums surveilles se DERIVENT du diff entre le build archive et le
build courant (`data/symbols/<build>/frida/enums.tsv`, VERSIONNE). Aucune allowlist.

CE QU'IL NE VOIT PAS, ET IL FAUT LE DIRE
----------------------------------------
Il ne voit qu'un indice dont la ligne CITE le membre en prose. Un `leaves.get(8)` sans commentaire
reste invisible a tout balayage syntaxique -- rien dans la source ne dit alors que `leaves` est
keye par un ordinal d'enum. Ce residu est nomme dans `docs/rl/case-443-r1c-indices-perimes.md` ;
le seul remede general est d'ecrire les cles en MEMBRES (`int(UtilityType.Elevation)`), ce que la
correction de #443-r1c fait et ce que `TILE_LEAVES` impose deja par assertion (#254).

ETAPE 0 -- AUTO-TEST, DANS LE VERDICT
-------------------------------------
Le detecteur est confronte a CHAQUE run a des sources SYNTHETIQUES : la faute exacte de #443-r1c
(qui DOIT rougir, par les deux angles) et ses voisines legitimes (qui NE DOIVENT PAS). Un cliquet
qui a cesse de mordre rend vert sur un depot fautif -- vice trouve TROIS fois dans ce depot
(`probe_181` #430, `probe_326` #435). `probe_439` garde << peut rendre un code non nul >> ; cette
etape-ci garde << rougit sur SON gisement >>, qui en est le residu declare (`#439-r1`).

ASCII only (console Windows cp1252).
Usage: python probe_443r1c_ordinal_index_perime.py [-v]
Code de sortie = nombre de rouges (auto-test compris).
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
REPO = PYDIR.parents[1]
sys.path.insert(0, str(PYDIR))

# Source UNIQUE des helpers de balayage (perimetre, prose token-aware, lecture d'`enums.tsv`).
# Les redupliquer ferait diverger deux definitions du meme perimetre -- exactement la cause de
# #430. `probe_283` n'execute rien a l'import.
import repo_read  # noqa: E402
from probe_283_enum_ordinal_sweep import (  # noqa: E402
    _ignore, _prose_par_ligne, all_enums, current_build, previous_build)

# Accesseurs de dict qui portent une CLE en 1er argument. `probe_283 --step exec` ne visite que
# `ast.Subscript` : ces trois formes sont son angle mort syntaxique.
ACCESSEURS = ("get", "pop", "setdefault")

# Un identifiant de moins de 4 caracteres cite en prose n'identifie rien (`Add`, `On`, `Up`...).
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")


def _lit_int(node) -> "int | None":
    if isinstance(node, ast.Constant) and isinstance(node.value, int) \
            and not isinstance(node.value, bool):
        return node.value
    return None


class _Indices(ast.NodeVisitor):
    """Tout litteral entier en position de CLE : `x[3]`, `x.get(3)`, `x.pop(3)`, `x.setdefault(3)`."""

    def __init__(self) -> None:
        self.hits: list = []                       # (lineno, forme, nom du recepteur, valeur)

    @staticmethod
    def _recepteur(node) -> "str | None":
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return None

    def visit_Subscript(self, node):
        v = _lit_int(node.slice)
        if v is not None:
            self.hits.append((node.lineno, "[]", self._recepteur(node.value), v))
        self.generic_visit(node)

    def visit_Call(self, node):
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in ACCESSEURS and node.args:
            v = _lit_int(node.args[0])
            if v is not None:
                self.hits.append((node.lineno, "." + f.attr, self._recepteur(f.value), v))
        self.generic_visit(node)


def _index_par_nom(build: str) -> dict:
    """{nom de membre: {enum pleinement qualifie: ordinal}} pour TOUT le build."""
    out: dict = {}
    for fq, membres in all_enums(build).items():
        for o, nom in membres.items():
            out.setdefault(nom, {})[fq] = o
    return out


def _rouges_de_ligne(v: int, txt: str, cur_par_nom: dict, arch_par_nom: dict) -> list:
    """[(membre, enum, ordinal courant)] -- les citations PERIMEES que `v` porte sur cette ligne."""
    out = []
    for m in set(_IDENT.findall(txt)):
        cur = cur_par_nom.get(m)
        arch = arch_par_nom.get(m)
        if not cur or not arch:
            continue
        # Clause 2 d'abord : une lecture ACTUELLE du nombre disculpe le site, ambigu ou non.
        if v in cur.values():
            continue
        for fq, o_arch in arch.items():
            if o_arch == v and fq in cur and cur[fq] != v:
                out.append((m, fq, cur[fq]))
                break
    return out


def _noms_a_risque(cur_par_nom: dict, arch_par_nom: dict) -> "re.Pattern | None":
    """Regex alternee des membres dont l'ordinal a CHANGE entre les deux builds.

    PRE-FILTRE, et il est EXACT : une ligne ne peut rougir que si elle CITE un tel membre, donc un
    fichier qui n'en contient aucun ne peut produire aucun rouge -- on peut lui epargner le parse
    AST et le tokenize sans perdre un seul site. Mesure du 2026-08-02 : 47,7 s -> 23,3 s sur les
    1518 fichiers de `scripts/python/**`, dont 683 retenus. Verdict IDENTIQUE dans les deux sens,
    contre-epreuve jouee sur le depot REEL et pas seulement sur l'echantillon : `probe_193c` a
    l'etat fautif de #443-r1c rougit avec le pre-filtre comme sans lui."""
    noms = {m for m, arch in arch_par_nom.items()
            for fq, o in arch.items()
            if len(m) >= 4 and fq in cur_par_nom.get(m, {}) and cur_par_nom[m][fq] != o}
    if not noms:
        return None
    return re.compile(r"\b(?:%s)\b" % "|".join(re.escape(n) for n in sorted(noms, key=len,
                                                                           reverse=True)))


def _balayer_source(src: str, rel: str, cur_par_nom: dict, arch_par_nom: dict) -> tuple:
    """([(rel, lineno, forme, recepteur, valeur, membre, enum, ordinal courant)], nb d'indices)."""
    try:
        tree = ast.parse(src, filename=rel)
    except (SyntaxError, ValueError):
        return [], 0
    sw = _Indices()
    sw.visit(tree)
    prose = _prose_par_ligne(src)
    out = []
    for lineno, forme, recep, v in sw.hits:
        txt = prose.get(lineno, "")
        if not txt:
            continue
        for membre, fq, o_cur in _rouges_de_ligne(v, txt, cur_par_nom, arch_par_nom):
            out.append((rel, lineno, forme, recep, v, membre, fq, o_cur))
    return out, len(sw.hits)


# ------------------------------------------------------------------------------------------
# Etape 0 -- AUTO-TEST. Les echantillons sont du CODE, balaye par le MEME chemin que le depot.
# ------------------------------------------------------------------------------------------

# La faute EXACTE de #443-r1c. Doit rougir DEUX fois : par `Elevation` (membre AMBIGU, invisible
# aux etapes 4 et 4bis de `probe_283`) et par `TileEffects` (indice passe par `.get`, invisible a
# son etape exec). Les deux angles morts sont donc couverts par un seul echantillon.
_ECH_FAUTIF = (
    "def f(leaves, p_tot):\n"
    "    p_x = p_tot - leaves.get(8, 0.0) - leaves.get(9, 0.0)   # 8=Elevation 10=TileEffects\n"
    "    return p_x\n")

# La MEME ligne, corrigee : cles en MEMBRES. Aucun litteral d'indice -> rien a signaler.
_ECH_CORRIGE = (
    "def f(leaves, p_tot):\n"
    "    p_x = (p_tot - leaves.get(int(UtilityType.Elevation), 0.0)\n"
    "                 - leaves.get(int(UtilityType.TileEffects), 0.0))\n"
    "    return p_x\n")

# Voisines LEGITIMES, qui ne doivent PAS rougir :
#  * un indice qui vaut l'ordinal COURANT du membre cite (juste aujourd'hui) ;
#  * un indice de tuple sans rapport, sur une ligne qui cite un membre par ailleurs ;
#  * un nom ambigu dont le nombre a une lecture ACTUELLE dans un AUTRE enum (clause 2).
_ECH_SAIN = (
    "def g(d, t):\n"
    "    a = d.get(9)          # 9=Elevation aujourd'hui\n"
    "    b = t[0]              # le couple (col, row) ; cf. UtilityType.TileEffects\n"
    "    c = d.get(2)          # 2=Elevation cote ObscuringType\n"
    "    return a, b, c\n")


def _auto_test(cur_par_nom: dict, arch_par_nom: dict, verbose: bool) -> list:
    echecs = []
    fautif, _ = _balayer_source(_ECH_FAUTIF, "<auto-test:fautif>", cur_par_nom, arch_par_nom)
    membres = {h[5] for h in fautif}
    if len(fautif) < 2 or not {"Elevation", "TileEffects"} <= membres:
        echecs.append("l'echantillon FAUTIF de #443-r1c ne rougit plus par ses deux angles "
                      "(attendu Elevation ET TileEffects, obtenu %s)" % (sorted(membres) or "rien"))
    for nom, src in (("CORRIGE", _ECH_CORRIGE), ("SAIN", _ECH_SAIN)):
        faux, _ = _balayer_source(src, "<auto-test:%s>" % nom.lower(), cur_par_nom, arch_par_nom)
        if faux:
            echecs.append("l'echantillon %s rougit a tort : %s"
                          % (nom, [(h[1], h[4], h[5]) for h in faux]))
    print("[443-r1c] etape 0 : auto-test du detecteur -- %d rouge(s) attendu(s) sur l'echantillon "
          "fautif, %d obtenu(s) ; %d echec(s)" % (2, len(fautif), len(echecs)))
    if verbose:
        for h in fautif:
            print("        mord : %s[%s] ligne %d -- %s valait %s, vaut %s"
                  % (h[2], h[4], h[1], h[5], h[4], h[7]))
    for e in echecs:
        print("   ECHEC AUTO-TEST : %s" % e)
    return echecs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    cur, prev = current_build(), previous_build()
    if not prev:
        # Pas d'archive = rien a comparer. On le DIT : un « 0 rouge » muet se lirait comme une
        # mesure alors qu'aucune n'a eu lieu.
        print("[443-r1c] AUCUN build archive a cote de %s -- le critere (ordinal ARCHIVE) est "
              "indefinissable. Rien MESURE, et ce n'est pas un vert." % cur)
        return 1
    cur_par_nom = _index_par_nom(cur)
    arch_par_nom = _index_par_nom(prev)
    print("[443-r1c] builds : archive=%s -> courant=%s" % (prev, cur))

    echecs = _auto_test(cur_par_nom, arch_par_nom, args.verbose)

    risque = _noms_a_risque(cur_par_nom, arch_par_nom)
    fichiers = [p for p in sorted((REPO / "scripts" / "python").rglob("*.py"))
                if _ignore(p) is not None]
    rouges, lus, retenus, indices = [], 0, 0, 0
    # Lecture PARALLELE (#457-r6) : l'ouverture pese ~7 ms par fichier sous `scripts/`
    # (filtre systeme sur les extensions executables), soit plus que tout l'AST de ce probe.
    for p, data in zip(fichiers, repo_read.read_bytes_many(fichiers)):
        rel = _ignore(p)
        if data is None:
            continue
        try:
            src = repo_read.to_text(data)
        except UnicodeDecodeError:
            continue
        lus += 1
        if risque is not None and not risque.search(src):
            continue                       # aucun membre decale cite : ne peut produire aucun rouge
        retenus += 1
        r, n = _balayer_source(src, rel, cur_par_nom, arch_par_nom)
        rouges += r
        indices += n

    print("[443-r1c] etape 1 : %d fichier(s) lu(s), %d retenu(s) par le pre-filtre (citent un membre "
          "decale), %d indice(s) litteral(aux) chez eux ([] / %s) -- %d PERIME(S)"
          % (lus, retenus, indices, "/".join("." + a for a in ACCESSEURS), len(rouges)))
    for rel, ln, forme, recep, v, membre, fq, o_cur in rouges:
        print("   PERIME %s:%d  %s%s[%s] ; la ligne cite %s, qui valait %s sur %s et vaut %s "
              "sur %s" % (rel, ln, recep or "?", forme, v, membre, v, prev, o_cur, cur))
    if not rouges and not echecs:
        print("[443-r1c] aucun indice litteral ne porte l'ordinal archive d'un membre cite sur sa "
              "ligne. RESIDU ASSUME : un indice SANS citation en prose reste invisible.")
    n = len(rouges) + len(echecs)
    print("[443-r1c] VERDICT: %s" % ("PASS" if n == 0 else "FAIL (%d)" % n))
    return n


if __name__ == "__main__":
    raise SystemExit(main())
