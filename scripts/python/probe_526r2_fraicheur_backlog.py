"""Probe #526-r2 -- LE DECLENCHEUR de fraicheur du backlog, et pourquoi ce n'est PAS un cliquet.

    python scripts/python/probe_526r2_fraicheur_backlog.py            # cliquet (rc = fautes)
    python scripts/python/probe_526r2_fraicheur_backlog.py --etat     # ce que le depot REEL porte

POURQUOI IL EXISTE
------------------
La fraicheur d'un residu n'est pas derivable, et la cause est en AMONT : **une PR qui ferme un
residu ne retire pas sa ligne de `backlog.md`, et rien ne l'y oblige**. Mesure #526 (2026-08-07) :
10 PERIME-CANDIDAT sur 278. Re-mesure du 2026-08-08 : **19 sur 285**. La derive a DOUBLE en un
jour -- notre propre cadence de livraison l'alimente plus vite qu'aucune passe ne la resorbe.

CE QU'ON A ECARTE, ET SUR QUEL CRITERE
--------------------------------------
Un CLIQUET << 0 residu perime >> est la reponse reflexe, et elle est INTERDITE ici -- pas par
son cout, par le MERGE. Pour partir de zero il faudrait retirer les 19 lignes d'un coup, soit
une modification de MASSE de `docs/rl/backlog.md` ; or `CLAUDE.md` l'interdit, mesure a l'appui :
36 des 40 dernieres PR mergees touchent ce fichier (90 %, le suivant est a 15), donc une passe
qui reecrit des lignes de tableau partout entre en conflit avec CHAQUE PR en vol, sur des lignes
modifiees des DEUX cotes. Et un cliquet a SEUIL se degraderait en silence.

D'ou un signal RESTITUE, pas un verdict. Il vit dans `loop_status`, qui tourne au hook `Stop` --
donc JUSTE APRES un merge, quand il reste UNE ligne a retirer et pas dix-neuf. C'est le
<< au fil de l'eau, jamais en masse >> que la doctrine prescrit deja pour ce fichier, applique
a la fraicheur plutot qu'aux champs `FOYER:`/`BLOCAGE:`.

LE CRITERE : LE TITRE D'UNE PR MERGEE, ET RIEN D'AUTRE
------------------------------------------------------
Mesure #526 sur les quatre signaux essayes -- DEUX sont refutes et ne doivent pas etre re-tentes :

    `git log` corps compris        187/278   ne discrimine RIEN : un residu est cite par le
                                             commit qui l'OUVRE
    case-doc au numero exact         5/278   trop rare pour porter quoi que ce soit
    id en SUJET d'un commit posterieur au blame      7/278   RETENU
    id dans un TITRE de PR mergee                   10/278   RETENU (dont 6 invisibles du 1er)

Ce probe garde le second, qui est celui que `loop_status` peut servir GRATUITEMENT : la fenetre
PR est deja lue pour la livraison des branches (#479-r4), le titre y est deja demande.

CE QU'IL GARDE, ET QUI N'EXISTAIT PAS
-------------------------------------
1. LE TEMOIN NON NUL. Le signal a ete livre MUET une premiere fois -- `_SECTION_OUVERTE` etait
   ecrit sans son accent (`## Taches ouvertes`), donc il ne matchait rien. Le tri-etat l'a
   montre (la cause etait NOMMEE) la ou une liste vide l'aurait cache. L'etape 1 exige donc de
   voir le signal TIRER sur le vrai backlog avant de croire un silence.
2. LES TROIS FAUX POSITIFS a ne pas produire : une PR OUVERTE (pas mergee), un residu qui n'est
   plus dans la section ouverte, et un COMPTEUR ROULANT (`#217`, `#419-r1` -- mis a jour a
   chaque livraison partielle, donc nomme sans etre ferme).
3. LE TRI-ETAT : `gh` muet ne rend jamais << 0 residu perime >>.

Sortie ASCII stricte. Code de sortie = nombre d'epreuves fautives.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import livraison as LV                                                     # noqa: E402
import loop_status as LS                                                   # noqa: E402

ECHECS: list[str] = []


def verifie(cond: bool, quoi: str) -> None:
    print(("  OK    " if cond else "  ROUGE ") + quoi)
    if not cond:
        ECHECS.append(quoi)


def _pr(titre: str, num: int = 999, etat: str = "MERGED") -> object:
    return LV.fenetre_des_prs(
        [{"number": num, "headRefName": "worktree-agent-x", "state": etat, "title": titre}], 120)


def _residus_ouverts(src) -> list[str]:
    """Les ids DEFINIS dans `## Taches ouvertes` -- en position de 1re cellule, comme #468."""
    texte = (src.repo / "docs" / "rl" / "backlog.md").read_text(encoding="utf-8")
    parts = texte.split(LS._SECTION_OUVERTE, 1)
    if len(parts) != 2:
        return []
    return re.findall(r"^\|\s*(#\d+(?:-r\d+)+)\s*\|", parts[1], re.MULTILINE)


def _roulant_ouvert(ouverts: list[str]) -> str | None:
    """Un id de COMPTEUR ROULANT effectivement present dans la section ouverte, ou None.

    Le DERIVER plutot que de le fabriquer : `"#217".rstrip("-r1") + "-r1"` rendait `#217-r1`,
    qui n'existe pas -- la mutation ne mordait alors sur RIEN et se lisait comme un vert.
    """
    for r in LS.RESIDUS_ROULANTS:
        for o in ouverts:
            if o == r or o.startswith(r + "-r"):
                return o
    return None


# =====================================================================================
#  1. LE TEMOIN NON NUL -- voir le signal TIRER avant de croire un silence
# =====================================================================================
def etape_1_temoin(src) -> None:
    print("\n[1] TEMOIN NON NUL : le signal tire-t-il sur le VRAI backlog ?")
    ouverts = _residus_ouverts(src)
    verifie(len(ouverts) > 50,
            "la section %r est LUE et porte %d residus definis -- sans ce temoin, un titre de "
            "section mal ecrit rendrait le signal muet SANS QU'ON LE VOIE (faute commise, "
            "l'accent manquait)" % (LS._SECTION_OUVERTE, len(ouverts)))
    if not ouverts:
        return
    cible = ouverts[0]
    m = LS._residus_livres(src, _pr("fix(%s) : quelque chose de livre" % cible))
    verifie(m.mesuree and [t["residu"] for t in m.valeur] == [cible],
            "une PR MERGEE dont le TITRE nomme %s, encore ouvert -> SIGNALE (%s)"
            % (cible, [t["residu"] for t in m.valeur] if m.mesuree else m.txt()))
    verifie(m.mesuree and m.valeur and m.valeur[0]["pr"] == 999,
            "et la PR qui a tranche est NOMMEE, comme partout ailleurs dans ce lecteur")


# =====================================================================================
#  2. LES TROIS FAUX POSITIFS QU'IL NE DOIT PAS PRODUIRE
# =====================================================================================
def etape_2_faux_positifs(src) -> None:
    print("\n[2] FAUX POSITIFS : trois formes, et aucune ne doit sortir")
    ouverts = _residus_ouverts(src)
    cible = ouverts[0] if ouverts else "#1-r1"

    m = LS._residus_livres(src, _pr("fix(%s) : en vol" % cible, etat="OPEN"))
    verifie(m.mesuree and m.valeur == [],
            "une PR OUVERTE ne ferme rien -- elle n'est pas encore livree (%s)" % m.valeur)

    m = LS._residus_livres(src, _pr("fix(#99999-r9) : residu inexistant"))
    verifie(m.mesuree and m.valeur == [],
            "un id qui n'est PAS dans la section ouverte ne sort pas (deja ferme, ou jamais "
            "ouvert) (%s)" % m.valeur)

    roulant = _roulant_ouvert(ouverts)
    verifie(roulant is not None,
            "temoin : au moins un COMPTEUR ROULANT (%s) est effectivement OUVERT -- sans lui, "
            "l'epreuve suivante serait vide et passerait pour un vert"
            % ", ".join(LS.RESIDUS_ROULANTS))
    if roulant:
        m = LS._residus_livres(src, _pr("fix(%s) : lot partiel" % roulant))
        verifie(m.mesuree and m.valeur == [],
                "un COMPTEUR ROULANT (%s) est nomme a chaque livraison partielle SANS etre "
                "ferme : il est ecarte, et c'est le faux positif que #526-r2 exigeait de "
                "preserver (%s)" % (roulant, m.valeur))


# =====================================================================================
#  3. TRI-ETAT : aucun chemin ne fabrique un zero
# =====================================================================================
def etape_3_tri_etat(src) -> None:
    print("\n[3] TRI-ETAT : `gh` muet ne rend JAMAIS << 0 residu perime >>")
    m = LS._residus_livres(src, LV.FenetrePR(cause="gh: delai depasse (3 s)"))
    verifie(not m.mesuree and "delai" in m.txt(),
            "fenetre PR NON MESUREE -> poste NON MESURE, avec sa cause (%s)" % m.txt())

    # Une fenetre MESUREE mais vide, elle, est un constat : c'est la difference exacte.
    m2 = LS._residus_livres(src, LV.fenetre_des_prs([], 120))
    verifie(m2.mesuree and m2.valeur == [],
            "fenetre MESUREE et vide -> liste vide MESUREE (un ensemble vide EST une mesure)")

    # Et le backlog illisible ne se degrade pas non plus en zero.
    class _Ailleurs:
        repo = Path(__file__).resolve().parent / "n-existe-pas"
    m3 = LS._residus_livres(_Ailleurs(), _pr("fix(#1-r1) : x"))
    verifie(not m3.mesuree, "backlog ILLISIBLE -> NON MESURE, pas une liste vide (%s)" % m3.txt())


# =====================================================================================
#  4. MUTATIONS
# =====================================================================================
def etape_4_mutations(src) -> None:
    print("\n[4] MUTATIONS : un cran qu'on n'a jamais vu ROUGE ne prouve rien")
    ouverts = _residus_ouverts(src)
    cible = ouverts[0] if ouverts else "#1-r1"

    def sous(nom: str, patch, epreuve) -> None:
        avant = ECHECS[:]
        restaure = patch()
        try:
            try:
                ok = bool(epreuve())
            except Exception:                                    # noqa: BLE001
                ok = False
        finally:
            restaure()
        del ECHECS[:]
        ECHECS.extend(avant)
        verifie(not ok, "mutation vue ROUGE : %s" % nom)

    # (a) le titre de section perd son accent -- la faute REELLEMENT commise dans cette tranche
    def p_a():
        vrai = LS._SECTION_OUVERTE
        LS._SECTION_OUVERTE = "## Taches ouvertes"               # type: ignore[assignment]
        return lambda: setattr(LS, "_SECTION_OUVERTE", vrai)
    # ⚠ L'EPREUVE TESTE CE QUE LE CRAN GARDE : << le signal TIRE >>. Ecrite `.valeur != []`,
    # elle passait sous la mutation -- une `Mesure` NON MESUREE rend `None`, et `None != []`
    # est vrai. Le tri-etat doit etre lu, pas contourne.
    sous("le titre de section perd son accent -> le signal devient MUET",
         p_a, lambda: (lambda m: m.mesuree and m.valeur != [])(
             LS._residus_livres(src, _pr("fix(%s) : x" % cible))))

    # (b) le critere passe de la POSITION DE DEFINITION a la simple MENTION : il rougirait alors
    #     sur les renvois croises, exactement le vice que `probe_468` a du corriger.
    verifie(len(re.findall(r"#\d+(?:-r\d+)+", (src.repo / "docs" / "rl" / "backlog.md")
                           .read_text(encoding="utf-8"))) > 3 * len(ouverts),
            "temoin du critere : le backlog porte bien plus de MENTIONS que de DEFINITIONS -- "
            "c'est pourquoi le critere porte sur la 1re cellule, jamais sur la presence")

    # (c) les roulants ne sont plus ecartes
    def p_c():
        vrai = LS.RESIDUS_ROULANTS
        LS.RESIDUS_ROULANTS = ()                                 # type: ignore[assignment]
        return lambda: setattr(LS, "RESIDUS_ROULANTS", vrai)

    roulant = _roulant_ouvert(ouverts)

    def eprouve_c():
        # `roulant` a ete DERIVE hors mutation : il designe un id REELLEMENT ouvert. Sous la
        # mutation (`RESIDUS_ROULANTS` vide), il doit ressortir -- donc l'epreuve tombe.
        m = LS._residus_livres(src, _pr("fix(%s) : lot" % roulant))
        return m.mesuree and m.valeur == []
    sous("les compteurs ROULANTS ne sont plus ecartes -> faux positif a chaque passe",
         p_c, eprouve_c)


def etat(src) -> int:
    """Ce que le depot REEL porte, avec `gh`. Ne juge pas -- restitue."""
    print("=== ETAT REEL ===")
    f = LV.lire_fenetre_pr(LS.Sources(avec_host=False).gh, LV.LIMITE_MANUELLE)
    print(f.portee())
    m = LS._residus_livres(src, f)
    if not m.mesuree:
        print("residus livres : %s" % m.txt())
        return 0
    print("\n%d residu(s) nomme(s) par une PR MERGEE et TOUJOURS ouverts :" % len(m.valeur))
    for t in m.valeur:
        print("   %-14s PR #%-5s %s" % (t["residu"], t["pr"], t["titre"]))
    if not m.valeur:
        print("   (aucun -- mesure, pas suppose)")
    print("\nCe signal est SERVI par `loop_status` a chaque hook Stop, donc juste apres un merge :")
    print("le retrait se fait ligne a ligne, jamais en passe de masse (cf. docstring).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--etat", action="store_true", help="restitue l'etat du depot reel (gh)")
    args = ap.parse_args()
    src = LS.Sources(avec_host=False)
    if args.etat:
        return etat(src)
    etape_1_temoin(src)
    etape_2_faux_positifs(src)
    etape_3_tri_etat(src)
    etape_4_mutations(src)
    print("\nVERDICT: %s -- %s" % (
        "PASS" if not ECHECS else "FAIL",
        "le signal de fraicheur TIRE, et ne produit aucun des trois faux positifs."
        if not ECHECS else "%d epreuve(s) fautive(s)" % len(ECHECS)))
    for e in ECHECS:
        print("  - " + e)
    return len(ECHECS)


if __name__ == "__main__":
    sys.exit(main())
