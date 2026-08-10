"""#603 -- ECRIRE les champs `FOYER:`/`BLOCAGE:` dans le backlog, et PROJETER l'index de dispatch.

DEUX ETAGES, ET LE SECOND NE PROPOSE RIEN
------------------------------------------
  * `ecrire_backlog()` consomme `migration_603_foyers.tsv` -- des decisions prises par LECTURE
    (la derivation mecanique est REFUTEE, cf. `probe_603_index_foyers.py --calibrer`) -- et les
    inscrit dans `docs/rl/backlog.md`.
  * `ecrire_index()` PROJETTE ce que le backlog PORTE, sans jamais rien deviner. L'index ne peut
    donc pas se perimer autrement que le backlog lui-meme : il se regenere d'une commande.

L'ECRITURE EST AU NIVEAU OCTET, ET CE N'EST PAS UN DETAIL
-----------------------------------------------------------
`core.autocrlf` vaut `true` ici et `docs/rl/backlog.md` n'est PAS dans `.gitattributes` : le
blob est en LF, le fichier de travail en CRLF. Mesure du 2026-08-10 : une branche en vol
(`worktree-agent-a3e30a25a2d866050`) porte un blob backlog en **CRLF sur ses 3 709 lignes**, ce
qui produit un diff de **7 416 lignes pour 12 blocs de contenu reels** -- et donc un conflit
avec TOUTE autre PR touchant ce fichier. On lit et on reecrit donc les OCTETS, en ne touchant
qu'au contenu des lignes visees et jamais a leurs terminateurs.

CE QUI EST REFUSE, PLUTOT QU'ECRIT DE TRAVERS
----------------------------------------------
  * un chemin de foyer absent de `git ls-files` -> REFUS NOMME (jamais ecrit) ;
  * un mot de blocage hors des cinq -> REFUS ;
  * une fiche du TSV qui n'existe pas / une fiche non annotee absente du TSV -> REFUS.
    C'est ce dernier cran qui rend la couverture EXHAUSTIVE par construction : on ne peut pas
    en oublier une en silence.

Sortie ASCII stricte (console Windows cp1252).
"""
from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path

import backlog_entries as B

RACINE = Path(__file__).resolve().parents[2]

EX_OK = 0
EX_ROUGE = 1

#: valeurs de foyer qui ne designent aucun fichier -- chacune est un RESULTAT, pas un defaut
FOYERS_SANS_FICHIER = {
    "aucun": "residu d'arbitrage ou de mesure : rien a editer",
    "?": "la fiche dit elle-meme que le foyer depend d'une mesure NON FAITE",
    "livree": "fiche LIVREE dont la 1re cellule n'est pas barree : a FERMER, pas a annoter",
    "perime": "la fiche cite un artefact SUPPRIME du depot : a requalifier, pas a annoter",
}

#: Les valeurs qui font SAUTER l'ecriture : la fiche ne doit pas recevoir de champs, elle doit
#: etre traitee (fermee ou requalifiee). Elles sont COMPTEES et NOMMEES, jamais tues.
FOYERS_A_TRAITER = ("livree", "perime")


def cle(ident: str) -> str:
    """Identifiant canonique d'une fiche : ce qui precede le premier espace.

    Une fiche porte parfois une glose dans sa cellule d'identifiant (`#448-r1-r1-r3 (ex-...)`).
    """
    return ident.split(" ")[0].strip().strip("*").strip()


def _fichiers_versionnes() -> set[str]:
    r = subprocess.run(["git", "-C", str(RACINE), "ls-files"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError("git ls-files a echoue : %s" % r.stderr.strip()[:200])
    return {l for l in r.stdout.split("\n") if l}


def resoudre_chemin(p: str, fichiers: set[str], reps: set[str]) -> str | None:
    """Forme CANONIQUE versionnee de `p`, ou None s'il ne designe rien dans l'arbre courant.

    ⚠ **L'ABREVIATION EST LA REGLE, PAS L'EXCEPTION -- et la resoudre n'est pas une
    complaisance, c'est ce qui rend l'index JUSTE.** Les fiches ecrites avant #603 abregent
    massivement : `engine/runner/abilities/targeting.py`, `abilities/worldeaters.py`,
    `runner/abilities/**`. Deux consequences MESUREES le 2026-08-10 :

      * sans resolution, **29 chemins sur 439** sortaient en << foyer MORT >> alors que les 29
        existent -- un cliquet qui accuse a tort se fait desactiver, et il aurait masque les
        VRAIS morts ;
      * bien pire, l'index groupait `engine/runner/abilities/targeting.py` et
        `scripts/python/engine/runner/abilities/targeting.py` sous DEUX cles distinctes, donc
        il SOUS-COMPTAIT les collisions. C'est le sens dangereux de l'erreur : deux residus
        qui partagent un fichier seraient apparus disjoints, et seraient partis ensemble.

    On canonicalise donc AVANT de grouper, en essayant les prefixes reellement observes.
    """
    for prefixe in ("", "scripts/python/", "scripts/python/engine/",
                    "scripts/python/engine/runner/"):
        c = prefixe + p
        if c in fichiers:
            return c
        cr = c.rstrip("/") + "/"
        if cr in reps:
            return cr
        if "*" in c:
            motif = re.escape(c).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
            if any(re.fullmatch(motif, f) for f in fichiers):
                return c
    return None


def _valide_chemin(p: str, fichiers: set[str], reps: set[str]) -> bool:
    return resoudre_chemin(p, fichiers, reps) is not None


def chemins_supprimes(chemins: list[str]) -> list[str]:
    """Parmi des chemins ABSENTS de l'arbre, ceux qui y ONT EXISTE -- les foyers POURRIS.

    ⚠ **<< Introuvable >> ne vaut PAS << mort >>, et les confondre rendrait ce cliquet
    inutilisable.** Un foyer nomme legitimement un fichier que la tranche va CREER : un mirror
    neuf, un probe a ecrire. Mesure du 2026-08-10 : sur les 7 chemins absents de l'arbre,
    **4 n'ont jamais existe** (`engine/playbook/noncomparable/war_howl.py`,
    `.../adaptive_strategy.py`, `engine/playbook/registry.py`,
    `probe_419r1tr14r5r2r1r1r1r3_gates.py` -- tous des fichiers A CREER) et **1 a ete
    SUPPRIME** (`frida/hooks/probes/try-to-campaign.ts`, par `0a61b0c6`).

    Le discriminant est donc l'HISTORIQUE, pas l'arbre : un chemin qui a existe et n'existe
    plus est un foyer qui pourrit ; un chemin qui n'a jamais existe est une intention.
    L'appel est borne aux seuls chemins absents (7 sur 439), donc il ne coute rien.
    """
    morts = []
    for p in chemins:
        r = subprocess.run(
            ["git", "-C", str(RACINE), "log", "--diff-filter=D", "--format=%H",
             "--name-only", "-1", "--", p],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode == 0 and r.stdout.strip():
            morts.append(p)
    return morts


def lire_decisions() -> dict[str, tuple[str, str, str]]:
    """Les decisions de #603, indexees par identifiant canonique.

    La source est un MODULE Python et non un `.tsv`, et c'est une mesure : `probe_457 --since`
    traite tout fichier NON-`.py` de `scripts/` comme une lecture GLOBALE (voie `dirs_glob`),
    donc un `.tsv` y faisait rendre << TOUT rejoue -- 294 fichiers, ~1755 s >> a chaque PR qui
    y touche, quand un diff purement Python ne le declenche JAMAIS.
    """
    from migration_603_foyers import DECISIONS
    return {cle(ident): (foyer, blocage, source)
            for ident, foyer, blocage, source in DECISIONS}


def ecrire_backlog(backlog: Path, verifier_seulement: bool = False) -> int:
    entrees = B.lire(backlog)
    non = [e for e in entrees if e.ouverte and not e.annotee]
    decisions = lire_decisions()
    fichiers = _fichiers_versionnes()
    reps: set[str] = set()
    for f in fichiers:
        p = f
        while "/" in p:
            p = p.rsplit("/", 1)[0]
            reps.add(p + "/")

    erreurs: list[str] = []

    # --- cran d'EXHAUSTIVITE : la correspondance doit etre BIJECTIVE
    idents = {cle(e.ident) for e in non}
    manquants = sorted(idents - set(decisions))
    orphelins = sorted(set(decisions) - idents)
    if manquants:
        erreurs.append("%d fiche(s) non annotee(s) SANS decision : %s"
                       % (len(manquants), ", ".join(manquants[:10])))
    if orphelins:
        erreurs.append("%d decision(s) sans fiche : %s"
                       % (len(orphelins), ", ".join(orphelins[:10])))

    # --- validation des valeurs
    for k, (foyer, blocage, _src) in sorted(decisions.items()):
        if blocage not in B.BLOCAGES:
            erreurs.append("%s : blocage `%s` hors des cinq mots" % (k, blocage))
        if foyer in FOYERS_SANS_FICHIER:
            continue
        for p in [x.strip() for x in foyer.split(",") if x.strip()]:
            if not _valide_chemin(p, fichiers, reps):
                erreurs.append("%s : chemin de foyer INTROUVABLE au depot -> %s" % (k, p))

    if erreurs:
        print("[603] REFUS -- %d probleme(s), AUCUNE ecriture :" % len(erreurs))
        for e in erreurs[:40]:
            print("   - %s" % e)
        return EX_ROUGE

    # --- ecriture OCTET
    octets = backlog.read_bytes()
    lignes = octets.split(b"\n")   # les `\r` restent en fin de chaque element : intacts

    ecrites = 0
    a_traiter: dict[str, list[str]] = defaultdict(list)
    for e in non:
        foyer, blocage, _src = decisions[cle(e.ident)]
        if foyer in FOYERS_A_TRAITER:
            a_traiter[foyer].append(cle(e.ident))
            continue
        if e.pos_modele is None:
            erreurs.append("%s : aucun point d'insertion (colonne Modele non localisee)" % e.ident)
            continue
        if foyer in FOYERS_SANS_FICHIER:
            rendu_foyer = "`%s`" % foyer
        else:
            rendu_foyer = ", ".join("`%s`" % p.strip()
                                    for p in foyer.split(",") if p.strip())
        champ = " -- **FOYER:** %s -- **BLOCAGE:** `%s` " % (rendu_foyer, blocage)

        idx = e.ligne - 1
        brute = lignes[idx]
        fin_cr = b""
        if brute.endswith(b"\r"):
            brute, fin_cr = brute[:-1], b"\r"
        txt = brute.decode("utf-8")
        if "FOYER:" in txt:
            erreurs.append("%s : la ligne porte DEJA un FOYER -- refus de doublon" % e.ident)
            continue
        # on insere juste AVANT le `|` qui ouvre la colonne Modele, sans toucher au reste
        avant = txt[:e.pos_modele].rstrip()
        apres = txt[e.pos_modele:]
        lignes[idx] = (avant + champ + apres).encode("utf-8") + fin_cr
        ecrites += 1

    if erreurs:
        print("[603] REFUS a l'ecriture -- %d probleme(s), AUCUNE ecriture :" % len(erreurs))
        for e in erreurs[:40]:
            print("   - %s" % e)
        return EX_ROUGE

    if not verifier_seulement:
        backlog.write_bytes(b"\n".join(lignes))
    print("[603] %d ligne(s) annotee(s)" % ecrites)
    for mot in FOYERS_A_TRAITER:
        ids = a_traiter.get(mot, [])
        if ids:
            print("[603] SAUTEES -- `%s` (%s) : %d -> %s"
                  % (mot, FOYERS_SANS_FICHIER[mot], len(ids), ", ".join(ids)))
    return EX_OK


# --------------------------------------------------------------------------- index


def ecrire_index(backlog: Path, index: Path) -> int:
    """Projette l'etat ECRIT du backlog en un index de DISPATCH, groupe par foyer."""
    entrees = B.lire(backlog)
    ouvertes = [e for e in entrees if e.ouverte]
    annotees = [e for e in ouvertes if e.annotee]
    non = [e for e in ouvertes if not e.annotee]

    fichiers = _fichiers_versionnes()
    reps: set[str] = set()
    for f in fichiers:
        p = f
        while "/" in p:
            p = p.rsplit("/", 1)[0]
            reps.add(p + "/")

    par_foyer: dict[str, list[B.Entree]] = defaultdict(list)
    par_blocage: dict[str, list[B.Entree]] = defaultdict(list)
    sans_fichier: dict[str, list[B.Entree]] = defaultdict(list)
    a_creer: dict[str, list[B.Entree]] = defaultdict(list)
    for e in annotees:
        par_blocage[e.blocage or "<absent>"].append(e)
        if not e.foyer_chemins:
            mot = (e.foyer_texte or "").strip().strip("`*").strip()
            sans_fichier[mot or "<vide>"].append(e)
            continue
        for p in e.foyer_chemins:
            # CANONICALISER AVANT DE GROUPER : sans ca, une abreviation et sa forme pleine
            # comptent pour deux foyers, et la collision qu'elles portent DISPARAIT.
            canon = resoudre_chemin(p, fichiers, reps)
            if canon is None:
                a_creer[p].append(e)
                continue
            if e not in par_foyer[canon]:
                par_foyer[canon].append(e)

    L: list[str] = []
    L.append("# Index des FOYERS -- projection de `docs/rl/backlog.md` pour le DISPATCH")
    L.append("")
    L.append("> **GENERE. Ne pas editer a la main.**")
    L.append("> `python scripts/python/probe_603_index_foyers.py --index`")
    L.append(">")
    L.append("> **Ce fichier ne PROPOSE rien** : il projette les champs `FOYER:`/`BLOCAGE:` que le")
    L.append("> backlog PORTE. La source de verite reste `backlog.md` ; cet index est une VUE, donc")
    L.append("> il ne peut pas se perimer autrement que lui. Un index ecrit a la main aurait peri")
    L.append("> exactement comme ce qu'il documente.")
    L.append(">")
    L.append("> **A quoi il sert** : grouper deux residus dans un meme agent exige des foyers")
    L.append("> DISJOINTS. La famille (`#419`, `#433`...) est le MAUVAIS axe -- le foyer la")
    L.append("> TRAVERSE. Ci-dessous, tout foyer partage par >= 2 residus est un point de")
    L.append("> COLLISION : ces residus-la ne partent pas ensemble.")
    L.append(">")
    L.append("> ⚠ **Le foyer est SUR-LISTE a dessein.** Un foyer surestime refuse un appariement")
    L.append("> qui aurait pu passer ; un foyer sous-estime envoie deux agents sur le meme")
    L.append("> fichier. L'asymetrie est totale : le doute se resout du cote LARGE.")
    L.append("")
    L.append("## Couverture")
    L.append("")
    L.append("| | nombre |")
    L.append("|---|---|")
    L.append("| lignes de tableau OUVERTES | %d |" % len(ouvertes))
    L.append("| dont ANNOTEES (`FOYER:` + `BLOCAGE:`) | %d |" % len(annotees))
    L.append("| dont NON ANNOTEES | %d |" % len(non))
    L.append("| foyers distincts (fichiers/repertoires) | %d |" % len(par_foyer))
    L.append("")
    if non:
        L.append("Non annotees restantes : %s" % ", ".join(sorted(cle(e.ident) for e in non)))
        L.append("")

    L.append("## Points de COLLISION -- un foyer, plusieurs residus")
    L.append("")
    L.append("Ces residus **ne partent pas ensemble**.")
    L.append("")
    L.append("| foyer | n | residus |")
    L.append("|---|---|---|")
    collisions = sorted(((p, es) for p, es in par_foyer.items() if len(es) >= 2),
                        key=lambda kv: (-len(kv[1]), kv[0]))
    for p, es in collisions:
        L.append("| `%s` | %d | %s |"
                 % (p, len(es), ", ".join(sorted(cle(x.ident) for x in es))))
    L.append("")

    L.append("## Foyers ISOLES -- un seul residu")
    L.append("")
    L.append("Candidats naturels a un dispatch parallele, sous reserve de croiser leurs autres foyers.")
    L.append("")
    L.append("| foyer | residu | blocage |")
    L.append("|---|---|---|")
    for p, es in sorted((kv for kv in par_foyer.items() if len(kv[1]) == 1)):
        e = es[0]
        L.append("| `%s` | %s | `%s` |" % (p, cle(e.ident), e.blocage))
    L.append("")

    L.append("## Par BLOCAGE")
    L.append("")
    L.append("Un residu `capteur` ne part pas tant qu'aucune fenetre de reinject n'est prevue.")
    L.append("")
    L.append("| blocage | n | residus |")
    L.append("|---|---|---|")
    for mot in B.BLOCAGES:
        es = par_blocage.get(mot, [])
        if not es:
            continue
        L.append("| `%s` | %d | %s |"
                 % (mot, len(es), ", ".join(sorted(cle(x.ident) for x in es))))
    autres = {k: v for k, v in par_blocage.items() if k not in B.BLOCAGES}
    for mot, es in sorted(autres.items()):
        L.append("| `%s` (HORS VOCABULAIRE) | %d | %s |"
                 % (mot, len(es), ", ".join(sorted(cle(x.ident) for x in es))))
    L.append("")

    L.append("## Foyers qui ne designent AUCUN fichier")
    L.append("")
    L.append("`aucun` = residu d'arbitrage ou de mesure, rien a editer.")
    L.append("`?` = la fiche dit elle-meme que le foyer depend d'une mesure NON FAITE : c'est un")
    L.append("resultat, pas un abandon. Ces residus se dispatchent SANS contrainte de disjonction")
    L.append("(`aucun`) ou APRES la mesure qui les determine (`?`).")
    L.append("")
    L.append("| valeur | n | residus |")
    L.append("|---|---|---|")
    for mot, es in sorted(sans_fichier.items()):
        L.append("| `%s` | %d | %s |"
                 % (mot, len(es), ", ".join(sorted(cle(x.ident) for x in es))))
    L.append("")

    L.append("## Foyers qui designent un fichier A CREER")
    L.append("")
    L.append("Absents de l'arbre courant et **jamais** presents dans l'historique : ce sont des")
    L.append("fichiers que la tranche ECRIRA (mirror neuf, probe a monter). Ils comptent comme")
    L.append("foyer pour la disjonction. Un chemin absent qui, LUI, a existe serait un foyer")
    L.append("POURRI -- `test_603_index_foyers_offline.py` etage 3 le refuse.")
    L.append("")
    L.append("| chemin | residus |")
    L.append("|---|---|")
    for p, es in sorted(a_creer.items()):
        L.append("| `%s` | %s |" % (p, ", ".join(sorted(cle(x.ident) for x in es))))
    L.append("")

    index.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    try:
        nom = index.relative_to(RACINE).as_posix()
    except ValueError:
        nom = str(index)          # cible hors depot : le cliquet regenere dans un `tmp_path`
    print("[603] index ecrit : %s (%d foyers, %d collisions)"
          % (nom, len(par_foyer), len(collisions)))
    return EX_OK
