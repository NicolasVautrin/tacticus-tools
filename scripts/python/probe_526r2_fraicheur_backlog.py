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
    """Les ids DEFINIS dans `## Taches ouvertes` -- en position de 1re cellule, comme #468.

    ⚠ IL NE RECOPIE PLUS LA GRAMMAIRE (#526-r4) : il APPELLE `LS._residus_ouverts`. Elle
    vivait ici en double, donc ce probe pouvait rester vert sur une regle que le lecteur
    n'employait deja plus. Un cran qui juge une regle qu'il a recopiee ne juge que sa copie.
    """
    m = LS._residus_ouverts(src)
    return sorted(m.valeur) if m.mesuree else []


def _roulant_ouvert(ouverts: list[str]) -> str | None:
    """Un COMPTEUR ROULANT ouvert ET EXTRACTIBLE d'un titre. EXACT, jamais un prefixe.

    Le DERIVER plutot que de le fabriquer : `"#217".rstrip("-r1") + "-r1"` rendait `#217-r1`,
    qui n'existe pas -- la mutation ne mordait alors sur RIEN et se lisait comme un vert.

    ⚠ Il rendait auparavant le premier id COMMENCANT PAR un roulant, ce qui melangeait le
    compteur et ses descendants. Depuis #526-r4 l'appariement est EXACT des deux cotes : un
    descendant est un residu a part entiere, et l'epreuve qui le confond ne garde rien.

    ⚠ ET IL EXIGE L'EXTRACTIBILITE, seconde fois que la meme faute se paie : `#217` est une
    RACINE NUE, que `_RE_ID_TITRE` ne produit JAMAIS (exigence anti-numero-de-PR). Une
    epreuve batie dessus ne mordait sur RIEN et passait pour un vert -- exactement ce que la
    docstring ci-dessus reprochait deja a `rstrip`. Les entrees inertes sont RECENSEES par
    `_roulants_inertes`, pas silencieusement choisies.
    """
    for r in LS.RESIDUS_ROULANTS:
        if r in ouverts and re.fullmatch(LS._RE_ID_TITRE, r):
            return r
    return None


def _roulants_inertes(ouverts: list[str]) -> list[tuple[str, str]]:
    """`(entree, raison)` pour chaque entree de `RESIDUS_ROULANTS` qui ne peut JAMAIS tirer.

    Une entree d'allowlist qui ne masque rien n'est pas une faute -- mais la taire en est
    une : c'est exactement par la que `#419-r1` a passe neuf tours a masquer une TRONCATURE
    plutot qu'un compteur roulant (#526-r4). On la NOMME, on ne la devine pas.
    """
    inertes = []
    for r in LS.RESIDUS_ROULANTS:
        if r not in ouverts:
            inertes.append((r, "n'est PAS un residu ouvert du backlog"))
        elif not re.fullmatch(LS._RE_ID_TITRE, r):
            inertes.append((r, "RACINE NUE : `_RE_ID_TITRE` exige un segment (anti-numero "
                               "de PR), donc aucun titre ne peut la produire"))
    return inertes


def _descendant_ouvert_d_un_roulant(ouverts: list[str]) -> tuple[str, str] | None:
    """`(roulant, descendant)` : un residu OUVERT dont l'id commence par celui d'un roulant.

    C'est le TEMOIN NON NUL du cran << appariement exact >> : sans lui, l'epreuve porterait
    sur un ensemble vide et passerait pour un vert. Mesure du 2026-08-08 : 31 descendants
    ouverts sous `#419-r1`.
    """
    for r in LS.RESIDUS_ROULANTS:
        for o in ouverts:
            if o.startswith(r + "-") and o != r:
                return r, o
    return None


def _hors_ancienne_grammaire(ouverts: list[str]) -> str | None:
    """Un id OUVERT que l'ancienne grammaire `#\\d+(?:-r\\d+)*` ne savait PAS produire.

    Temoin du cran << grammaire elargie >> : `#462-r4b`, `#419-r1-tr14`, `#BF-chance`...
    Mesure du 2026-08-08 : 212 des 619 1res cellules sont dans ce cas.
    """
    ancienne = re.compile(r"^#\d+(?:-r\d+)*$")
    for o in ouverts:
        if not ancienne.match(o) and o not in LS.RESIDUS_ROULANTS:
            return o
    return None


# =====================================================================================
#  1. LE TEMOIN NON NUL -- voir le signal TIRER avant de croire un silence
# =====================================================================================
def _cible(ouverts: list[str]) -> str:
    """Un id OUVERT qui n'est pas un compteur roulant -- sinon l'epreuve se masque elle-meme."""
    for o in ouverts:
        if o not in LS.RESIDUS_ROULANTS:
            return o
    return "#1-r1"


def etape_1_temoin(src) -> None:
    print("\n[1] TEMOIN NON NUL : le signal tire-t-il sur le VRAI backlog ?")
    ouverts = _residus_ouverts(src)
    verifie(len(ouverts) > 50,
            "la section %r est LUE et porte %d residus definis -- sans ce temoin, un titre de "
            "section mal ecrit rendrait le signal muet SANS QU'ON LE VOIE (faute commise, "
            "l'accent manquait)" % (LS._SECTION_OUVERTE, len(ouverts)))
    if not ouverts:
        return
    cible = _cible(ouverts)
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
    cible = _cible(ouverts)

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

    # LE CHAMP `title` MANQUANT EST UNE PANNE, PAS UN CONSTAT (#526-r4). La fenetre est
    # MESUREE et porte des PR mergees, mais le critere (le TITRE) n'a pas ete lu : rendre `[]`
    # ici s'imprimait << aucun -- mesure, pas suppose >> chez l'appelant. Mesure du
    # 2026-08-08 : voie manuelle 0, voie du hook 4, le meme jour.
    sans_titre = LV.fenetre_des_prs(
        [{"number": 1, "headRefName": "worktree-agent-x", "state": "MERGED"}], 120)
    m4 = LS._residus_livres(src, sans_titre)
    verifie(not m4.mesuree and "title" in (m4.erreur or ""),
            "fenetre MESUREE mais SANS le champ `title` -> NON MESURE, avec sa cause : le "
            "critere est le titre, donc une fenetre sans titre ne conclut RIEN (%s)" % m4.txt())

    # ... et la fenetre MESUREE, AVEC titres, mais sans aucune PR mergee, elle, conclut.
    m5 = LS._residus_livres(src, _pr("fix(%s) : en vol" % _cible(_residus_ouverts(src)),
                                     etat="OPEN"))
    verifie(m5.mesuree and m5.valeur == [],
            "aucune PR MERGEE dans la fenetre -> liste vide MESUREE : c'est la difference "
            "exacte avec le cas ci-dessus (%s)" % m5.txt())


# =====================================================================================
#  4. MUTATIONS
# =====================================================================================
def sous(nom: str, patch, epreuve) -> None:
    """Joue `epreuve` sous la mutation `patch`, et exige qu'elle TOMBE. Restaure toujours.

    Au niveau module depuis #526-r4 : l'etage 5 en a besoin aussi, et une mutation recopiee
    est une mutation qui derive.
    """
    avant = ECHECS[:]
    restaure = patch()
    try:
        try:
            ok = bool(epreuve())
        except Exception:                                        # noqa: BLE001
            ok = False
    finally:
        restaure()
    del ECHECS[:]
    ECHECS.extend(avant)
    verifie(not ok, "mutation vue ROUGE : %s" % nom)


def _patch(attr: str, valeur):
    """Substitue `LS.<attr>` et rend le restaurateur."""
    def poser():
        vrai = getattr(LS, attr)
        setattr(LS, attr, valeur)
        return lambda: setattr(LS, attr, vrai)
    return poser


def etape_4_mutations(src) -> None:
    print("\n[4] MUTATIONS : un cran qu'on n'a jamais vu ROUGE ne prouve rien")
    ouverts = _residus_ouverts(src)
    cible = _cible(ouverts)

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


# =====================================================================================
#  5. LA GRAMMAIRE DE L'ID (#526-r4) -- borne droite, largeur, appariement exact
# =====================================================================================
def etape_5_grammaire(src) -> None:
    """Les trois crans que #526-r4 a mesures, chacun avec son TEMOIN NON NUL.

    Le defaut repare : `#\\d+(?:-r\\d+)+` sans borne droite s'arrete au premier segment
    non-`r<chiffres>` et FABRIQUE un ancetre. Sur les 200 dernieres PR mergees (2026-08-08),
    24 extractions tronquees en 3 familles, et 14 des 18 signaux emis etaient ce faux positif.
    """
    print("\n[5] GRAMMAIRE DE L'ID (#526-r4) : borne droite, largeur, appariement exact")
    ouverts = _residus_ouverts(src)

    # --- (a) LA BORNE DROITE. Temoin NON NUL : un descendant a segment non-`r` dont l'ANCETRE
    #         tronque est lui-meme un residu OUVERT. Sans les deux, l'epreuve ne prouve rien.
    tronque, descendant = None, None
    for o in ouverts:
        m = re.match(r"^(#\d+(?:-r\d+)+)[a-z]", o)
        if m and m.group(1) in ouverts:
            tronque, descendant = m.group(1), o
            break
    verifie(descendant is not None,
            "temoin de la borne : un residu OUVERT (%s) dont l'ancetre TRONQUE (%s) est lui "
            "aussi ouvert -- c'est la configuration exacte du faux positif `#462-r4 (PR #724)`"
            % (descendant, tronque))
    if descendant:
        m = LS._residus_livres(src, _pr("fix(%s) : le vrai sujet" % descendant))
        sortis = [t["residu"] for t in m.valeur] if m.mesuree else None
        verifie(m.mesuree and tronque not in (sortis or []),
                "un titre nommant %s ne FABRIQUE pas son ancetre %s (sorti : %s)"
                % (descendant, tronque, sortis))
        verifie(m.mesuree and sortis == [descendant],
                "et il nomme le residu REELLEMENT livre, %s (sorti : %s)"
                % (descendant, sortis))

        # MUTATION (a1) : LA GRAMMAIRE D'ORIGINE, verbatim -- etroite ET sans borne. C'est le
        # regime qui a produit les 24 troncatures et le `#462-r4 (PR #724)` du hook `Stop`.
        sous("la grammaire d'origine `#\\d+(?:-r\\d+)+` (etroite, SANS borne) revient -> "
             "l'ancetre TRONQUE est FABRIQUE",
             _patch("_RE_ID_TITRE", r"#\d+(?:-r\d+)+"),
             lambda: (lambda mm: mm.mesuree and tronque not in
                      [t["residu"] for t in mm.valeur])(
                 LS._residus_livres(src, _pr("fix(%s) : le vrai sujet" % descendant))))

    # --- (a2) LA BORNE, ISOLEE. Sous la grammaire ELARGIE, la borne ne joue plus contre un
    #     segment `-<mot>` (elle l'absorbe) : ce qu'elle garde encore, c'est le suffixe colle
    #     hors classe (`_`, un mot). Le dire, plutot que de laisser croire qu'elle porte seule
    #     la reparation -- c'est la LARGEUR qui la porte, cran (b).
    cible = _cible(ouverts)
    m = LS._residus_livres(src, _pr("fix(%s_bis) : suffixe colle" % cible))
    verifie(m.mesuree and cible not in [t["residu"] for t in m.valeur],
            "un titre portant `%s_bis` ne FABRIQUE pas `%s` -- c'est ce que la borne droite "
            "garde encore sous la grammaire elargie (%s)"
            % (cible, cible, [t["residu"] for t in m.valeur] if m.mesuree else m.txt()))
    sous("la borne droite `(?![-\\w])` disparait -> un suffixe colle fabrique l'id `%s`" % cible,
         _patch("_RE_ID_TITRE", r"#[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+"),
         lambda: (lambda mm: mm.mesuree and cible not in [t["residu"] for t in mm.valeur])(
             LS._residus_livres(src, _pr("fix(%s_bis) : suffixe colle" % cible))))

    # --- (b) LA LARGEUR. Temoin NON NUL : un residu ouvert que l'ANCIENNE grammaire ne savait
    #         pas produire (212 des 619 1res cellules au 2026-08-08).
    hors = _hors_ancienne_grammaire(ouverts)
    verifie(hors is not None,
            "temoin de la largeur : au moins un residu OUVERT (%s) est hors de l'ancienne "
            "grammaire `#<n>(-r<k>)*` -- sans lui, l'elargissement ne garderait rien" % hors)
    if hors:
        m = LS._residus_livres(src, _pr("fix(%s) : livre" % hors))
        verifie(m.mesuree and [t["residu"] for t in m.valeur] == [hors],
                "un residu a segment non-`r<chiffres>` (%s) est SIGNALE (%s)"
                % (hors, [t["residu"] for t in m.valeur] if m.mesuree else m.txt()))

        # MUTATION : on retrecit la grammaire aux seuls `-r<chiffres>` -> il redevient invisible.
        sous("la grammaire retrecit a `#<n>(-r<k>)+` -> les 212 ids a segment non-`r` "
             "redeviennent INVISIBLES",
             _patch("_RE_ID_TITRE", r"#\d+(?:-r\d+)+(?![-\w])"),
             lambda: (lambda mm: mm.mesuree and [t["residu"] for t in mm.valeur] == [hors])(
                 LS._residus_livres(src, _pr("fix(%s) : livre" % hors))))

    # --- (c) L'APPARIEMENT EXACT DES ROULANTS. Temoin NON NUL : un DESCENDANT ouvert d'un
    #         roulant (31 sous `#419-r1` au 2026-08-08). Il ne doit PAS heriter du baillon.
    couple = _descendant_ouvert_d_un_roulant(ouverts)
    verifie(couple is not None,
            "temoin de l'appariement : au moins un residu OUVERT descend d'un compteur "
            "roulant (%s) -- sans lui, `startswith` et l'egalite seraient indiscernables"
            % (couple,))
    if couple:
        roulant, desc = couple
        m = LS._residus_livres(src, _pr("fix(%s) : tranche livree" % desc))
        verifie(m.mesuree and [t["residu"] for t in m.valeur] == [desc],
                "le DESCENDANT %s d'un roulant (%s) est signale : il a sa propre ligne et son "
                "propre cycle de vie (%s)"
                % (desc, roulant, [t["residu"] for t in m.valeur] if m.mesuree else m.txt()))

        # MUTATION : l'appariement redevient un PREFIXE -> le descendant est baillonne.
        def p_prefixe():
            vrai = LS._residus_nommes

            def par_prefixe(s, f):
                mm = vrai(s, f)
                if not mm.mesuree:
                    return mm
                gard, ecart = [], list(mm.valeur["ecartes_roulants"])
                for t in mm.valeur["retenus"]:
                    (ecart if t["residu"].startswith(LS.RESIDUS_ROULANTS)
                     else gard).append(t)
                return LS._ok({"retenus": gard, "ecartes_roulants": ecart}, mm.source)
            LS._residus_nommes = par_prefixe                      # type: ignore[assignment]
            return lambda: setattr(LS, "_residus_nommes", vrai)
        sous("l'appariement des ROULANTS redevient un PREFIXE -> %d descendants ouverts "
             "baillonnes" % sum(1 for o in ouverts if o.startswith(roulant + "-")),
             p_prefixe,
             lambda: (lambda mm: mm.mesuree and [t["residu"] for t in mm.valeur] == [desc])(
                 LS._residus_livres(src, _pr("fix(%s) : tranche livree" % desc))))

    # --- (d) L'ALLOWLIST DIT CE QU'ELLE NE PEUT PAS MASQUER. Une entree inerte n'est pas une
    #     faute ; la TAIRE en est une -- c'est par la que `#419-r1` a masque une TRONCATURE
    #     neuf tours durant en se faisant passer pour un compteur roulant (#526-r4).
    inertes = _roulants_inertes(ouverts)
    for entree, raison in inertes:
        print("  NOTE  RESIDUS_ROULANTS[%s] est INERTE : %s" % (entree, raison))
    verifie(len(inertes) < len(LS.RESIDUS_ROULANTS),
            "au moins une entree de RESIDUS_ROULANTS est EFFECTIVE (ouverte et extractible "
            "d'un titre) -- %d/%d inertes ; une allowlist entierement inerte ne garde RIEN"
            % (len(inertes), len(LS.RESIDUS_ROULANTS)))

    # --- (e) L'ECART N'EST PLUS MUET : quand un roulant est ecarte, la PROVENANCE le dit.
    roulant = _roulant_ouvert(ouverts)
    if roulant:
        m = LS._residus_livres(src, _pr("fix(%s) : lot partiel" % roulant))
        verifie(m.mesuree and m.valeur == [] and "RESIDUS_ROULANTS" in m.source
                and roulant in m.source,
                "un ecart par RESIDUS_ROULANTS est COMPTE dans la provenance (%r) -- une "
                "entree qui ne masque RIEN devient ainsi visible, au lieu d'etre de l'inertie"
                % m.source[-90:])

    # --- (f) UN NUMERO DE PR N'EST PAS UN ID. La racine nue est hors grammaire, par exigence.
    racines = [o for o in ouverts if re.match(r"^#\d+$", o)]
    verifie(bool(racines),
            "temoin : au moins une RACINE nue (%s) est un residu ouvert -- c'est ce qui rend "
            "la collision avec un numero de PR possible" % (racines[:3],))
    if racines:
        m = LS._residus_livres(src, _pr("fix(#526-r4) : voir la discussion de la PR %s" % racines[0]))
        verifie(m.mesuree and racines[0] not in [t["residu"] for t in m.valeur],
                "une racine nue citee dans un titre (`%s`, indiscernable d'un numero de PR) "
                "n'est PAS prise pour un residu livre (%s)"
                % (racines[0], [t["residu"] for t in m.valeur] if m.mesuree else m.txt()))


def etat(src) -> int:
    """Ce que le depot REEL porte, avec `gh`. Ne juge pas -- restitue."""
    print("=== ETAT REEL ===")
    f = LV.lire_fenetre_pr(LS.Sources(avec_host=False).gh, LV.LIMITE_MANUELLE)
    print(f.portee())
    m = LS._residus_livres(src, f)
    if not m.mesuree:
        print("residus livres : %s" % m.txt())
        return 0
    ouv = LS._residus_ouverts(src)
    print("residus OUVERTS lus dans le backlog : %s" % (len(ouv.valeur) if ouv.mesuree
                                                       else ouv.txt()))
    print("\n%d residu(s) nomme(s) par une PR MERGEE et TOUJOURS ouverts :" % len(m.valeur))
    for t in m.valeur:
        print("   %-42s PR #%-5s %s" % (t["residu"], t["pr"], t["titre"]))
    if not m.valeur:
        print("   (aucun -- mesure, pas suppose)")
    # L'ECART N'EST PAS MUET (#526-r4) : ce que `RESIDUS_ROULANTS` a masque est restitue.
    print("\nprovenance : %s" % m.source)
    v = LS._residus_nommes(src, f)
    if v.mesuree and v.valeur["ecartes_roulants"]:
        print("ecartes comme COMPTEURS ROULANTS :")
        for t in v.valeur["ecartes_roulants"]:
            print("   %-42s PR #%-5s %s" % (t["residu"], t["pr"], t["titre"]))
    else:
        print("ecartes comme COMPTEURS ROULANTS : aucun sur cette fenetre -- les entrees "
              "%s n'y masquent RIEN (mesure, pas inertie)" % (LS.RESIDUS_ROULANTS,))
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
    etape_5_grammaire(src)
    print("\nVERDICT: %s -- %s" % (
        "PASS" if not ECHECS else "FAIL",
        "le signal de fraicheur TIRE, et ne produit aucun des trois faux positifs."
        if not ECHECS else "%d epreuve(s) fautive(s)" % len(ECHECS)))
    for e in ECHECS:
        print("  - " + e)
    return len(ECHECS)


if __name__ == "__main__":
    sys.exit(main())
