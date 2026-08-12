"""#935-r1 -- LA CONTRE-EPREUVE de `probe_935` : sa classe AST, confrontee a l'empreinte MESUREE.

`probe_935` classe un cliquet INSELECTIONNABLE en lisant l'AST du fichier de test et de la cloture
de ses imports locaux. C'est une DEDUCTION, et elle SUR-APPROXIME de son propre aveu -- un module
qui `glob` un repertoire de donnees avec un motif contenant `.py`, un `--name-only` cite en prose.
Sa doc le dit et imprime le compte des deux classes << donc une derive de l'approximation se voit >>.

⚠ RIEN NE LA VOYAIT. Un compte imprime n'est pas un garde-fou : personne ne le lit, et il ne rougit
pas. C'est le vice exact que `probe_181` portait avant #430 -- << un inventaire deguise en
garde-fou >>. Ce probe est la piece qui manquait : il oppose a la deduction une MESURE.

LA MESURE, ET D'OU ELLE VIENT. L'empreinte de `probe_457` porte depuis #935-r1 un axe `py` : les
REPERTOIRES des `.py` qu'un fichier de test a ouverts APPLICATIVEMENT (le discriminant est pris a
l'ECRITURE, sur la frame appelante -- cf. `_FilesPerTest._vient_d_un_import`). Une entree ecrite
avant cet axe n'en porte pas la cle ; on retombe alors sur les `.py` de ses `temoins`, et la
SOURCE est DITE pour chaque ligne. Mesure du 2026-08-12 sur les 7 entrees qui portent les deux :
le repli rend EXACTEMENT le meme ensemble que l'axe mesure (0 ecart dans les deux sens).

LES DEUX SENS N'ONT PAS LE MEME POIDS, ET C'EST TOUT LE POINT :

  * SUR-APPROXIMATION -- AST dit << balayeur >>, la mesure ne voit aucun `.py` applicatif. Le prix
    est du temps de test. TOLEREE, mais COMPTEE et sous CLIQUET : c'est elle qui derive.
  * FAUX NEGATIF -- AST dit << selectionnable >>, la mesure voit un balayage. Le prix est un
    cliquet qu'une composition `{insellectionnables} UNION {selection}` laisserait tomber. Cette
    direction-la doit valoir ZERO, et c'est un INVARIANT, pas un seuil.

⚠ CE QU'ELLE NE PEUT PAS TRANCHER, et il faut le dire : un fichier que la passe n'a jamais joue
n'a pas d'entree -- il sort en NON CONFRONTABLE, jamais en accord. Un accord fabrique a partir
d'une absence serait exactement le zero qu'un recenseur rend sur ce qu'il ne visite pas.

Usage (depuis `scripts/python`) :

    python probe_935r1_contre_epreuve_classes.py
    python probe_935r1_contre_epreuve_classes.py --verbose

Issues : 0 = aucun faux negatif ; 1 = au moins un faux negatif ; 99 = RIEN n'a pu etre confronte.
ASCII only (console cp1252). 100 % OFFLINE : aucun runner, aucun RPC.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PYDIR = Path(__file__).resolve().parent
if str(_PYDIR) not in sys.path:
    sys.path.insert(0, str(_PYDIR))

import probe_457_offline_tests_green as P457                                  # noqa: E402
import probe_935_cliquets_insellectionnables as P935                          # noqa: E402

#: Ce qui doit changer pour que ce cliquet puisse changer d'avis (#486-r15).
DECLENCHEUR = {
    "chemins": ("scripts/python/probe_935_cliquets_insellectionnables.py",
                "scripts/python/probe_457_offline_tests_green.py",
                "scripts/ratchets-457-footprints.json",
                "scripts/python/tests/**", "scripts/python/**/*.py"),
    "build": False,
    "toujours": False,
    "raison": "Il confronte la classe AST de `probe_935` (fonction de tout `scripts/python/**`) a "
              "l'empreinte VERSIONNEE de `probe_457`. Les deux cotes bougent avec l'arbre Python.",
}

#: LE PLAFOND DE SUR-APPROXIMATION -- UN DETECTEUR DE REGIME, PAS UN CLIQUET PAR FICHIER, et le
#: choix est deliberatif. Un cliquet sur le COMPTE ABSOLU rougirait des qu'un fichier de test NEUF
#: entre par un module deja balayeur (`symbols_layout.py` en accuse 15 a lui seul) : toute PR sans
#: rapport paierait la maintenance d'un artefact partage -- l'incitation exacte qui fait desarmer
#: un cliquet (#547-r6). Ce qu'on veut voir, c'est la DEGENERESCENCE du critere, et elle est
#: massive quand elle arrive : mesure du 2026-08-11, un critere par NOM D'APPEL seul rendait
#: **289 insellectionnables sur 323** -- la sur-approximation aurait bondi d'un facteur ~3.
#: Valeur MESUREE le 2026-08-12 : 76 / 333 confrontables = **22,8 %**.
#: L'INVARIANT, lui, est ailleurs et ne tolere rien : `FAUX NEGATIFS == 0`.
SUR_APPROXIMATION_MAX_PCT = 35.0


class MontageImpossible(RuntimeError):
    """Ce dont ce probe depend et qui n'est PAS son gisement (empreinte illisible, perimetre vide)."""


def _empreinte() -> dict:
    chemin = P457.repo_root() / "scripts" / "ratchets-457-footprints.json"
    try:
        emp = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise MontageImpossible("empreinte illisible (%s: %s)"
                                % (type(exc).__name__, str(exc)[:120])) from exc
    if emp.get("_format") != P457.FORMAT_EMPREINTE:
        raise MontageImpossible("empreinte au format %s, attendu %d"
                                % (emp.get("_format"), P457.FORMAT_EMPREINTE))
    return emp


def mesure_par_test(emp: dict) -> dict:
    """`{rel -> (balayeur mesure ?, source, detail)}` -- l'entree ABSENTE n'y figure PAS.

    La source distingue l'axe MESURE du REPLI sur temoins : les deux repondent a la meme question,
    mais seul le premier sait separer une lecture d'IMPORT d'une lecture APPLICATIVE."""
    out: dict = {}
    for rel, entree in (emp.get("par_test") or {}).items():
        if not isinstance(entree, dict):
            continue
        axe = entree.get("py")
        if axe is None:
            # MEME RETRAIT QU'A L'ECRITURE : la traceback d'un test qui TOMBE fait lire sa propre
            # source. Sans lui, tout fichier ROUGE se presente comme un balayeur -- mesure du
            # 2026-08-12, DEUX des dix-neuf premiers faux negatifs etaient exactement cela.
            axe = sorted({t.rsplit("/", 1)[0] for t in (entree.get("temoins") or ())
                          if t.endswith(".py") and "/" in t and not t.endswith("/" + rel)})
            source = "repli temoins"
        else:
            source = "axe mesure"
        fils = bool(entree.get("fils"))
        detail = ("%d repertoire(s) de `.py`%s" % (len(axe), ", SOUS-TRAITE" if fils else "")
                  if (axe or fils) else "aucun `.py`, aucun fils")
        out[rel] = (bool(axe) or fils, source, detail)
    return out


def confronter(perimetre=None):
    """`(accords, sur_approximations, faux_negatifs, non_confrontables, sources)`."""
    if perimetre is None:
        perimetre = P457.candidate_files()
    if not perimetre:
        raise MontageImpossible("perimetre offline VIDE -- `candidate_files` n'a rien rendu")
    ins, sel = P935.classer(perimetre)
    mesures = mesure_par_test(_empreinte())

    accords, sur, faux, hors = [], [], [], []
    sources = {"axe mesure": 0, "repli temoins": 0}
    for rel in perimetre:
        if rel not in mesures:
            hors.append((rel, rel in ins))
            continue
        balayeur, source, detail = mesures[rel]
        sources[source] = sources.get(source, 0) + 1
        deduit = rel in ins
        if deduit == balayeur:
            accords.append(rel)
        elif deduit:
            sur.append((rel, ins[rel][0], ins[rel][1].split(" : ")[0], source))
        else:
            faux.append((rel, source, detail))
    return accords, sur, faux, hors, sources, len(ins), len(sel)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--verbose", action="store_true",
                    help="Liste chaque sur-approximation (module accuse par l'AST) et chaque "
                         "fichier NON CONFRONTABLE.")
    a = ap.parse_args(argv)

    try:
        accords, sur, faux, hors, sources, n_ins, n_sel = confronter()
    except MontageImpossible as exc:
        print("[935-r1] MONTAGE EN ECHEC : %s" % exc)
        print("[935-r1] RIEN n'a ete confronte -- ce n'est ni un vert ni un rouge.")
        print("[935-r1] rc=99")
        return 99

    total = len(accords) + len(sur) + len(faux)
    print("[935-r1] classe AST (`probe_935`) : %d insellectionnable(s) / %d selectionnable(s)"
          % (n_ins, n_sel))
    print("[935-r1] CONFRONTABLES : %d (dont %d par l'axe `py` MESURE, %d par REPLI sur temoins) ; "
          "NON CONFRONTABLES : %d (aucune entree d'empreinte)"
          % (total, sources.get("axe mesure", 0), sources.get("repli temoins", 0), len(hors)))
    pct = 100.0 * len(sur) / total if total else 0.0
    print("[935-r1] accords : %d  |  SUR-APPROXIMATIONS : %d (%.1f %% des confrontables, plafond "
          "de REGIME %.1f %%)  |  FAUX NEGATIFS : %d"
          % (len(accords), len(sur), pct, SUR_APPROXIMATION_MAX_PCT, len(faux)))
    accusants = {}
    for _rel, accuse, _cause, _src in sur:
        accusants[accuse] = accusants.get(accuse, 0) + 1
    if accusants:
        tete = sorted(accusants.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
        print("[935-r1] modules ACCUSANTS distincts : %d ; en tete : %s"
              % (len(accusants), ", ".join("%s (%d)" % (m, n) for m, n in tete)))

    if not total:
        print("[935-r1] AUCUN fichier confrontable -- l'empreinte ne couvre pas le perimetre.")
        print("[935-r1] La combler : cd scripts/python ; python "
              "probe_457_offline_tests_green.py --measure-missing")
        print("[935-r1] rc=99")
        return 99

    if a.verbose:
        print("")
        print("[935-r1] SUR-APPROXIMATIONS (l'AST deduit un balayage, la mesure n'en voit aucun) :")
        for rel, accuse, cause, source in sur:
            print("    %-62s %-26s <- %s [%s]" % (rel, cause, accuse, source))
        print("")
        print("[935-r1] NON CONFRONTABLES (aucune entree d'empreinte -- jamais joues sous mesure) :")
        for rel, deduit in hors:
            print("    %-62s AST=%s" % (rel, "INSELECTIONNABLE" if deduit else "selectionnable"))

    if faux:
        print("")
        print("[935-r1] FAUX NEGATIFS -- l'AST les dit SELECTIONNABLES, la mesure voit un "
              "balayage `.py` ou une sous-traitance :")
        for rel, source, detail in faux:
            print("    %-62s %s [%s]" % (rel, detail, source))
        print("[935-r1] C'est la seule direction DANGEREUSE : une composition")
        print("[935-r1] `{insellectionnables} UNION {selection --since}` les laisserait tomber.")
        print("[935-r1] Remede : etendre le critere de `probe_935` (`_APPELS_DE_BALAYAGE`,")
        print("[935-r1] `_enumere_des_sources`) a la forme que ces fichiers emploient.")
        print("[935-r1] Si le doute porte sur la SOURCE `repli temoins` (elle ne separe pas import")
        print("[935-r1] et lecture applicative), re-mesurer l'entree : `python "
              "probe_457_offline_tests_green.py --measure-only <rel>`.")
        print("[935-r1] VERDICT: FAIL -- rc=1")
        return 1

    if pct > SUR_APPROXIMATION_MAX_PCT:
        print("")
        print("[935-r1] le REGIME du critere a DEGENERE : %.1f %% > %.1f %%. Ce n'est pas un faux "
              "vert -- c'est du temps de test paye pour rien, a l'echelle du perimetre."
              % (pct, SUR_APPROXIMATION_MAX_PCT))
        print("[935-r1] Chercher un critere de `probe_935` qui a perdu son DISCRIMINANT : sans le "
              "motif `.py`, `_enumere_des_sources` rendait 289/323 (mesure du 2026-08-11).")
        print("[935-r1] VERDICT: FAIL -- rc=1")
        return 1

    print("[935-r1] VERDICT: PASS -- aucun faux negatif, regime de sur-approximation nominal.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
