#!/usr/bin/env python3
"""GARDE de synchronisation : build installe <-> `data/symbols/<HASH>` <-> binaire charge par ghidra-mcp.

POURQUOI (residu #103 / O1) -- la procedure existait, la GARDE non
-------------------------------------------------------------------
`CLAUDE.md` et le skill d'orchestration decrivent trois etapes MANUELLES a passer apres une
mise a jour du jeu. Rien ne les verifiait : `ghidra_symbols.py build` se contentait
d'IMPRIMER le hash charge, sans le comparer a quoi que ce soit, et le hook `SessionStart`
ne regardait aucun hash. Le garde-fou etait documentaire -- c'est-a-dire inexistant des que
quelqu'un ne le lit pas.

Ce qui EXISTAIT deja, mais sur un AUTRE axe : `il2cpp_provenance.assert_matches` est
fail-closed et consomme par `preprocess_il2cpp_dump.py` et `GhidraApplyIl2CppSymbols.java`.
Mais son defaut visait `data/il2cpp_{methods,classes,enums}.tsv` -- des fichiers qui
N'EXISTENT PLUS depuis que les tables sont versionnees sous `data/symbols/<HASH>/`. La
verification par defaut ne verifiait donc plus rien.

LES SIX AXES, ET CE QUE CHACUN ATTRAPE
--------------------------------------
1. **binaire installe <-> tables versionnees** (sha256, pivot de la provenance). Attrape la
   mise a jour du jeu non suivie d'un re-dump : toute RVA lue devient fausse.
2. **coherence INTERNE des tables** : nom du repertoire == fichier `BUILD` == champ `build=`
   de l'estampille == en-tete `# build=` de la table Ghidra. Attrape un repertoire renomme a
   la main, ou une table Ghidra extraite d'un autre projet que les TSV Frida d'a cote.
3. **ghidra-mcp <-> tables versionnees**. C'EST LE PLUS SILENCIEUX : si le serveur sert encore
   l'ANCIEN projet pendant que les tables sont celles du NOUVEAU build, un agent **decompile un
   binaire et cite les symboles d'un autre**, et rien ne proteste -- les deux reponses sont
   plausibles separement, incoherentes ensemble.
4. **FORME** : la table parle-t-elle la meme langue que les citations du depot (`Classe$$Membre`) ?
5. **COUVERTURE par grande famille** : la table NEUVE nomme-t-elle encore, famille par famille,
   ce que nommait la precedente ?
6. **ARCHIVE D'EMPREINTE** (#482-r3) : le build COURANT a-t-il deja son empreinte structurelle
   rangee sous `data/symbols/<build>/fingerprints/` ? C'est le SEUL axe qui ne juge pas l'etat
   present mais une CAPACITE FUTURE -- pouvoir encore repondre, dans six mois, a « ce symbole
   a-t-il change de corps ? ». Il est ici parce qu'il faut agir AVANT la mise a jour : le
   lanceur efface `games/<HASH>/` sans preavis, et une empreinte qui n'a pas ete calculee
   pendant que le binaire existait ne se rattrape que par le projet Ghidra -- ou pas du tout.

Les axes 1 a 4 verifient la PROVENANCE ou la FORME. AUCUN ne compte ce qu'il y a DEDANS --
c'est exactement pourquoi la disparition de 4 015 symboles est passee sans un mot (#259).

L'axe 3 exige un serveur allume (lancement MANUEL, `start-ghidra-mcp.ps1`). Serveur eteint
n'est PAS un echec -- mais ce n'est PAS un succes non plus : c'est rapporte comme NON VERIFIE.
Taire la difference reproduirait exactement le defaut qu'on corrige.

L'axe 6 ne fait echouer la garde que sur une archive DISCORDANTE (un artefact incoherent, comme
l'axe 2). Une archive MANQUANTE le fait seulement PARLER : c'est une action a mener, pas une
desynchronisation -- rien de ce qui est lu aujourd'hui n'en devient faux. Et il PARLE plutot
qu'il ne se tait parce que l'action est BORNEE (~70 s, une fois par build) et que le message
disparait des qu'elle est faite : ce n'est pas une alarme permanente qu'on apprendrait a
ignorer. Une perte DEFINITIVE (`PERDUE`) est imprimee sans faire echouer -- aucune action ne
peut plus l'eteindre, et repeter une alarme inextinguible est exactement ce qui desarme un
garde-fou.

SORTIE : 0 = tout ce qui etait verifiable est SYNCHRONE ; 1 = DESYNCHRONISATION (ou artefact
illisible). ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "python"))

from il2cpp_provenance import (ProvenanceError, assert_matches, installed_dll,  # noqa: E402
                               read_stamp, sha256_of)
from symbols_layout import LayoutError, archived_builds, build_dir as _build_dir  # noqa: E402

SYMBOLS = REPO / "data" / "symbols"
FRIDA_TABLES = ("classes.tsv", "enums.tsv", "methods.tsv")


class Desync(RuntimeError):
    """Incoherence AVEREE entre deux artefacts -- toujours bloquante."""


def versioned_build() -> Path:
    """Le repertoire du build qui FAIT FOI, designe par `data/symbols/CURRENT`.

    CHANGE le 2026-07-29 : cette fonction exigeait auparavant qu'il n'y ait QU'UN SEUL
    repertoire, et prescrivait de SUPPRIMER l'ancien apres une MAJ. Mauvais marche -- la
    multiplicite n'etait qu'un PROXY d'ambiguite, alors que l'axe 1 sait deja trancher
    EXACTEMENT par sha256. On garde donc tous les builds (leur diff est le rapport de
    changement du jeu, et il doit rester consultable APRES la fenetre de migration) et on
    nomme explicitement celui qui fait foi. Detail : `symbols_layout.py`."""
    try:
        return _build_dir()
    except LayoutError as e:
        raise Desync(str(e)) from e


def axe1_binaire(build_dir: Path, dll: Path) -> list[str]:
    """sha256 du binaire installe contre l'estampille de CHAQUE table Frida."""
    lignes = []
    for nom in FRIDA_TABLES:
        p = build_dir / "frida" / nom
        st = assert_matches(p, dll)        # leve ProvenanceError si absent / illisible / discordant
        lignes.append("  OK  frida/%-12s sha256 == binaire installe (genere %s)"
                      % (nom, st.get("generated", "?")))
    return lignes


def axe2_coherence(build_dir: Path) -> list[str]:
    """Nom du repertoire, fichier BUILD, champ `build=` des estampilles, en-tete Ghidra."""
    attendu = build_dir.name
    lignes = []

    marqueur = build_dir / "BUILD"
    if not marqueur.is_file():
        raise Desync("%s/BUILD absent -- le hash n'est ecrit nulle part en clair" % attendu)
    vu = marqueur.read_text(encoding="utf-8").strip()
    if vu != attendu:
        raise Desync("BUILD dit '%s' mais le repertoire s'appelle '%s'" % (vu, attendu))
    lignes.append("  OK  BUILD == nom du repertoire (%s)" % attendu)

    for nom in FRIDA_TABLES:
        st = read_stamp(build_dir / "frida" / nom)
        if st.get("build") != attendu:
            raise Desync("frida/%s est estampillee build=%s, rangee sous %s"
                         % (nom, st.get("build"), attendu))

    ghidra = build_dir / "ghidra" / "functions.tsv"
    if not ghidra.is_file():
        raise Desync(
            "%s/ghidra/functions.tsv absent -- les frontieres de fonctions manquent.\n"
            "  Sans elles, aucune adresse ne se resout en `<symbole>+0x<offset>`.\n"
            "  L'extraire : python scripts/python/ghidra_symbols.py dump" % attendu)
    entete = ghidra.open(encoding="utf-8").readline()
    if ("build=%s" % attendu) not in entete:
        raise Desync(
            "ghidra/functions.tsv n'annonce pas build=%s dans son en-tete : %r\n"
            "  Table Ghidra et tables Frida ne viennent pas du meme build -- c'est exactement\n"
            "  la configuration ou l'on decompile un binaire en citant les symboles d'un autre."
            % (attendu, entete[:120]))
    lignes.append("  OK  estampilles frida + en-tete ghidra == %s" % attendu)
    return lignes


def axe3_ghidra(build_dir: Path, timeout: float) -> tuple[list[str], bool]:
    """Build REELLEMENT charge par ghidra-mcp. Serveur eteint => non verifie, PAS un succes."""
    try:
        import ghidra_symbols as G
    except ImportError as exc:
        return (["  ??  ghidra: client indisponible (%s) -- axe NON VERIFIE" % exc], False)
    GhidraDown = G.GhidraDown
    try:
        # Attente BORNEE : le defaut du client est 120 s (dimensionne pour un `dump` pagine).
        # Ici on ne fait qu'interroger, et l'appelant peut etre un hook de demarrage de session
        # -- un serveur a moitie mort ne doit pas le retenir deux minutes.
        charge = G.loaded_build(G.GhidraMCP(timeout=timeout).connect())
    except GhidraDown:
        return (["  ??  ghidra-mcp ETEINT -- axe NON VERIFIE (lancement manuel :",
                 "      pwsh -File C:\\Users\\nicolasv\\ghidra-mcp\\start-ghidra-mcp.ps1)"], False)
    except Exception as exc:                                    # noqa: BLE001
        return (["  ??  ghidra-mcp injoignable (%s) -- axe NON VERIFIE" % type(exc).__name__],
                False)
    if charge != build_dir.name:
        raise Desync(
            "ghidra-mcp a charge le build '%s', les tables versionnees sont '%s'.\n"
            "  Un agent RE lance maintenant DECOMPILERAIT un binaire en citant les symboles\n"
            "  d'un autre -- chaque reponse plausible seule, incoherentes ensemble.\n"
            "  Relancer le serveur sur le bon projet AVANT tout agent RE."
            % (charge, build_dir.name))
    return (["  OK  ghidra-mcp a charge %s == tables versionnees" % charge], True)


# Combien de citations distinctes echantillonner, et combien doivent resolver. Le seuil est
# volontairement TRES BAS : la panne visee est TOTALE (mesure du 2026-07-29 : 0 sur 1 266), pas
# graduelle. Un seuil bas ne peut donc pas crier au loup sur la derive normale d'une MAJ
# (81,9 % conservees ce jour-la), et attrape quand meme le desastre.
ECHANTILLON = 400
PLANCHER_PCT = 10.0
# MARGE MESUREE le 2026-07-29 : regime sain = 27 % (114/420), panne simulee = 0 %. Les 73 %
# qui ne resolvent pas en regime sain sont des citations en forme COURTE (sans namespace), qui
# ne resolvent JAMAIS -- ce n'est pas de la derive. Pour qu'un faux positif survienne, une MAJ
# devrait effacer les deux tiers des symboles reellement resolvables, ce qui meriterait l'alerte.

_CITE = re.compile(r"[A-Za-z_][\w.`]*\$\$[\w.`]+")


def axe4_forme(build_dir: Path) -> list[str]:
    """La table parle-t-elle la MEME LANGUE que les citations du depot ?

    POURQUOI CET AXE EXISTE (incident du 2026-07-29)
    ------------------------------------------------
    Les axes 1 a 3 verifient tous la PROVENANCE : sha256 du binaire, coherence des estampilles,
    build charge par le serveur. AUCUN ne regarde le CONTENU. Ce jour-la, la table produite pour
    le nouveau build etait en notation POINTEE (`Classe.Methode`) au lieu de `Classe$$Membre` :
    parfaitement estampillee, du bon build, servie par le bon serveur -- et INTEGRALEMENT
    inexploitable. Zero citation sur 1 266 resolvait, et le diff inter-build affichait 0,43 % de
    symboles communs, ce qui imitait une reecriture totale du jeu.

    La cause n'etait pas la MAJ mais un CHANGEMENT D'OUTILLAGE : le retrait de l'applier
    Il2CppDumper le 2026-07-25 sans re-jouer l'aval. L'ancienne sortie a continue de faire foi
    quatre jours, jusqu'a la premiere re-symbolisation complete.

    CE QU'IL NE FAUT PAS EN FAIRE : un thermometre de la derive inter-build. Pour cela il y a
    `probe_251_citation_resolution.py`, qui mesure proprement contre une population de reference.
    Ici on ne repond qu'a UNE question binaire : la table est-elle lisible du tout ?"""
    table = build_dir / "ghidra" / "functions.tsv"
    symboles = set()
    with table.open(encoding="utf-8") as fh:
        for ligne in fh:
            if ligne.startswith("#"):
                continue
            parts = ligne.rstrip("\n").split("\t")
            if len(parts) >= 2:
                symboles.add(parts[1])

    vues: set[str] = set()
    for f in sorted((REPO / "scripts" / "python" / "engine").rglob("*.py")):
        try:
            for m in _CITE.findall(f.read_text(encoding="utf-8", errors="replace")):
                vues.add(m)
        except OSError:
            continue
        if len(vues) >= ECHANTILLON:
            break

    if not vues:
        return ["  ??  aucune citation `$$` trouvee dans engine/ -- axe NON VERIFIE"]

    n = sum(1 for s in vues if s in symboles)
    pct = 100.0 * n / len(vues)
    if pct < PLANCHER_PCT:
        raise Desync(
            "la table ne parle PAS la langue des citations du depot : %d / %d resolvent (%.1f %%).\n"
            "  Ce n'est PAS une derive de mise a jour -- c'est une table INEXPLOITABLE.\n"
            "  Verifier la FORME avant tout : grep -c '\\$\\$' %s\n"
            "  Attendu `Namespace.Classe$$Membre` (chevrons echappes u003C/u003E), produit par\n"
            "  GhidraApplyIl2CppSymbols.canonicalName. Si la table est en notation pointee, c'est\n"
            "  l'applier qu'il faut corriger PUIS re-jouer -- re-dumper ne changera rien."
            % (n, len(vues), pct, table.as_posix()))
    return ["  OK  forme des symboles : %d / %d citations echantillonnees resolvent (%.0f %%)"
            % (n, len(vues), pct)]


# ============================ AXE 5 : COUVERTURE PAR FAMILLE ============================
#
# POURQUOI (#259). Les axes 1 a 4 repondent « d'ou vient cette table » et « est-elle lisible ».
# Aucun ne repond « nomme-t-elle encore ce qu'elle nommait ». Le 2026-07-29, la re-symbolisation
# du build courant a fait tomber de 4 015 a 0 les corps `__Il2CppFullySharedGenericType` -- une
# perte de 3,4 % de la table, PARFAITEMENT estampillee, du bon build, servie par le bon serveur,
# et dans la bonne FORME. Les quatre axes etaient verts.
#
# LA MAILLE. Compter par NAMESPACE seul n'aurait rien vu : les corps partages se repartissent sur
# tous les namespaces, et leur disparition ne fait bouger `IdunBattle.AI.Playbook` que de -1,8 %
# (2 122 -> 2 083, mesure). La famille `GSHARED` est donc definie sur le MECANISME, pas sur un
# prefixe -- c'est ce qui rend la chute visible (ratio 0,000).
#
# LE SEUIL, DIMENSIONNE SUR DU BRUIT MESURE ET NON CONTAMINE. On ne peut PAS calibrer sur le diff
# des deux tables Ghidra : l'ancienne vient de la chaine Il2CppDumper, la neuve de la chaine
# Frida -- leur ecart melange churn de MAJ et changement d'OUTILLAGE. Le bruit propre se lit sur
# les tables FRIDA, produites par le MEME outil des deux cotes. Mesure sur gqfc5mff6c ->
# rnca9r7q6c (`probe_259_gshared_coverage.py`, etape 2) :
#     26 familles >= 100 methodes ; ratio min 1,000, max 1,292 ; AUCUNE famille disparue.
#     Aucune famille >= 100 n'a PERDU un seul membre sur cette MAJ.
#     Familles < 100 : ratio min 0,750 (petits effectifs, bruit relatif eleve) -> exclues.
# Cote Ghidra (contamine), la pire famille legitime tombe a 0,863 (`BaseTest`, 124 -> 107, un
# artefact d'outillage : la table Frida, elle, donne 107 -> 107).
# Le seuil est donc pose a 0,60 : il laisse 0,26 de marge sous la pire valeur legitime OBSERVEE,
# et 0,60 au-dessus de la panne (0,000). Il ne crie pas sur le churn ; il ne peut pas rater ca.
SEUIL_COUVERTURE = 0.60
PLANCHER_FAMILLE = 100

# PERTES DEJA CONSTATEES, DOCUMENTEES, ET DONT LE RETABLISSEMENT EST UNE TACHE OUVERTE.
# Cle = (famille, build de reference, build courant) : l'entree s'auto-perime a la MAJ suivante
# (la reference devient l'actuel courant, la famille est alors a 0 des deux cotes, ratio 0/0 =
# rien a signaler). Une perte connue est IMPRIMEE, jamais tue -- elle ne fait simplement pas
# echouer la garde, sinon le hook de session hurlerait a chaque demarrage et on apprendrait a
# l'ignorer, ce qui est pire que pas de garde du tout.
# VIDE, et c'est le bon etat. L'entree ("GSHARED", "gqfc5mff6c", "rnca9r7q6c") a ete RETIREE le
# 2026-07-29 des que la perte a ete REPAREE (#259-a) : `GhidraApplyIl2CppDumperNames.java` a repose
# 5 899 noms, la famille GSHARED est remontee de 0 a 4 874 dans `ghidra/functions.tsv`.
# ⚠ UNE EXCUSE QUI SURVIT A SON MOTIF EST PIRE QU'UNE ABSENCE DE GARDE : elle rend l'axe muet sur
# une famille qui pourrait re-tomber, sans que personne ne s'en apercoive. Retirer l'entree fait
# donc PARTIE de la reparation, au meme titre que le re-dump.
#
# REMPLIR OU VIDER CE DICT NE FAIT PLUS ROUGIR AUCUN TEST (#282). Les tests du mecanisme
# (`tests/test_symbols_coverage_guard_offline.py`) confrontent une entree SYNTHETIQUE et ne
# prelevent RIEN ici. La version d'origine y prenait sa fixture par `next(iter(...))` : le vidage
# ci-dessus -- pourtant la BONNE action -- a laisse quatre tests en `StopIteration` derriere lui,
# rouges pendant des heures sans qu'une ligne de `comparer_couverture` ait bouge.
# UNE ENTREE NEUVE PORTE UN NUMERO DE TACHE ET UN RENVOI VERS SA FICHE (`.md`) : le controle de
# forme l'exige, parce qu'une excuse sans renvoi est une excuse qu'on ne saura pas retirer.
PERTES_CONNUES: dict[tuple[str, str, str], str] = {}

MARQUEUR_GSHARED = "__Il2CppFullySharedGeneric"


def _famille(nom: str) -> str:
    """Grande famille d'un symbole Ghidra. L'ORDRE des tests porte le sens.

    `GSHARED` passe avant le namespace : les corps pleinement partages traversent TOUS les
    namespaces, donc les ranger par prefixe les dilue et rend leur perte invisible.
    `PLACEHOLDER` (FUN_/DAT_/PTR_) est compte mais JAMAIS alerte : une baisse y est une BONNE
    nouvelle (des adresses anonymes ont recu un nom).

    Ecrit sans `split` intermediaire : ce corps tourne ~300 000 fois par appel de la garde,
    qui s'execute a CHAQUE demarrage de session (hook `session-start.ps1`, budget 15 s)."""
    if MARQUEUR_GSHARED in nom:
        return "GSHARED"
    if nom.startswith(("FUN_", "DAT_", "PTR_")):
        return "PLACEHOLDER"
    i = nom.find("$$")
    if i < 0:
        return "AUTRE"
    racine = nom[:i]
    for sep in (".", "`"):
        j = racine.find(sep)
        if j >= 0:
            racine = racine[:j]
    return "il2cpp:" + racine


def _familles_de(build_dir: Path) -> dict:
    """Compte par famille de `ghidra/functions.tsv`.

    ECRIT POUR LE COUT, parce que la garde tourne a CHAQUE demarrage de session (hook
    `session-start.ps1`, budget 15 s) et lit DEUX tables de ~10 Mo / 150 000 lignes :
      * le fichier est lu en bloc et decode UNE fois (pas de decodage par ligne) ;
      * les fins de ligne sont normalisees en un seul passage C (pas de `strip` par ligne).

    CE QU'ON NE FAIT PAS, ET POURQUOI : memoiser la famille sur un PREFIXE du symbole. Le
    marqueur `__Il2CppFullySharedGeneric` n'est PAS en tete -- il tombe au milieu du nom
    (`...TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$Init`, ~45e
    caractere). Une cle de prefixe rangerait ces symboles sous `il2cpp:IdunBattle` et
    effacerait EXACTEMENT le signal que cet axe existe pour voir. Cout mesure de la version
    honnete : ~0,45 s par table, ~1,0 s pour les deux -- la garde complete passe de ~2,5 s a
    ~3,5 s, pour un budget de hook de 15 s."""
    from collections import Counter
    table = build_dir / "ghidra" / "functions.tsv"
    brut = table.read_bytes().decode("utf-8", "replace").replace("\r", "")
    compte: Counter = Counter()
    for ligne in brut.split("\n"):
        i = ligne.find("\t")
        if i < 0 or ligne[0] == "#":
            continue
        compte[_famille(ligne[i + 1:])] += 1
    return compte


def _reference_la_plus_recente() -> Path | None:
    """L'archive la PLUS RECEMMENT dumpee -- ordonnee par `generated=` de son estampille.

    Pas par ordre alphabetique du hash (il n'a aucun sens chronologique) et pas par mtime du
    fichier (un checkout git le reecrit). La date de generation voyage DANS l'artefact.

    Une archive SANS table Ghidra est ecartee, pas une erreur : c'est un etat REEL et transitoire
    du depot -- les trois TSV Frida d'un build sont commites (b8dba3c0) AVANT que la passe Ghidra
    n'existe (04980aa1). Comparer contre elle rendrait « toutes les familles a zero »."""
    candidats = []
    for nom in archived_builds():
        try:
            rep = _build_dir(nom)
            if not (rep / "ghidra" / "functions.tsv").is_file():
                continue
            st = read_stamp(rep / "frida" / "methods.tsv")
        except (ProvenanceError, LayoutError):
            continue
        candidats.append((st.get("generated", ""), nom))
    if not candidats:
        return None
    return _build_dir(max(candidats)[1])


def comparer_couverture(vieux: dict, neuf: dict, ref_nom: str, cur_nom: str) -> list[str]:
    """Coeur PUR de l'axe 5 : deux comptes par famille -> lignes, ou `Desync`.

    Extrait des E/S expres pour etre confrontable sans toucher `data/`
    (`tests/test_symbols_coverage_guard_offline.py`)."""
    chutes, connues = [], []
    for fam, n_vieux in sorted(vieux.items(), key=lambda kv: -kv[1]):
        if fam == "PLACEHOLDER" or n_vieux < PLANCHER_FAMILLE:
            continue
        n_neuf = neuf.get(fam, 0)
        ratio = n_neuf / n_vieux
        if ratio >= SEUIL_COUVERTURE:
            continue
        motif = PERTES_CONNUES.get((fam, ref_nom, cur_nom))
        (connues if motif else chutes).append((fam, n_vieux, n_neuf, ratio, motif))

    if chutes:
        detail = "\n".join(
            "    %-24s %6d -> %6d  (ratio %.3f)" % (f, v, n, r) for f, v, n, r, _ in chutes)
        raise Desync(
            "COUVERTURE EFFONDREE sur %d famille(s), reference %s -> courant %s :\n%s\n"
            "  Ce n'est pas du churn de mise a jour : sur la seule MAJ mesuree, AUCUNE famille\n"
            "  de plus de %d symboles n'avait perdu un seul membre (seuil pose a %.2f).\n"
            "  Une chute pareille signe un maillon de la CHAINE qui a change, pas le jeu.\n"
            "  Verifier D'ABORD l'outillage (quel applier a symbolise le projet, avec quelle\n"
            "  entree) avant de conclure quoi que ce soit sur le binaire."
            % (len(chutes), ref_nom, cur_nom, detail,
               PLANCHER_FAMILLE, SEUIL_COUVERTURE))

    lignes = ["  OK  couverture par famille vs %s : %d familles suivies, aucune chute inattendue"
              % (ref_nom, sum(1 for f, v in vieux.items()
                              if f != "PLACEHOLDER" and v >= PLANCHER_FAMILLE))]
    for fam, v, n, r, motif in connues:
        lignes.append("  --  PERTE CONNUE  %s : %d -> %d (ratio %.3f)" % (fam, v, n, r))
        lignes.append("      %s" % motif)
    return lignes


def axe5_couverture(build_dir: Path) -> tuple[list[str], bool]:
    """La table NEUVE nomme-t-elle encore, famille par famille, ce que nommait la precedente ?

    Pas d'archive = axe NON VERIFIE (et surtout pas un succes) : sans point de comparaison la
    question n'a pas de sens -- exactement comme l'axe 3 quand ghidra-mcp est eteint."""
    ref = _reference_la_plus_recente()
    if ref is None:
        return (["  ??  aucun build archive -- axe COUVERTURE non verifiable (rien a comparer)"],
                False)
    return (comparer_couverture(_familles_de(ref), _familles_de(build_dir),
                                ref.name, build_dir.name), True)


def axe6_archive_empreinte() -> tuple[list[str], bool]:
    """L'empreinte structurelle de chaque build est-elle ARCHIVEE, ou encore recuperable ?

    Rend (lignes, rien_a_signaler). `rien_a_signaler` est ce qui autorise le hook a se TAIRE :
    il n'est vrai que si TOUT est archive. Une archive manquante, une perte definitive ou une
    recuperabilite non mesuree font parler -- chacune pour une raison differente, et l'axe les
    NOMME au lieu de les fondre.

    Ne LEVE que sur DISCORDANTE. Detail du raisonnement : docstring du module.
    """
    try:
        import build_fingerprint_archive as A
    except ImportError as exc:                                  # noqa: BLE001
        return (["  ??  archive d'empreinte : capteur indisponible (%s) -- axe NON VERIFIE"
                 % exc], False)

    inv = A.inventaire()
    if not inv:
        return (["  ??  archive d'empreinte : aucun build versionne -- axe NON VERIFIE"], False)

    mauvais = [e for e in inv if e.echec]
    if mauvais:
        e = mauvais[0]
        raise Desync(
            "archive d'empreinte DISCORDANTE pour %s : %s\n"
            "  Une empreinte rangee sous le mauvais build compare deux binaires sans rapport\n"
            "  et rend un changement fabrique de toutes pieces. La regenerer :\n"
            "    %s --force" % (e.build, e.detail, e.commande or "(voie a determiner)"))

    lignes, propre = [], True
    a_faire = [e for e in inv if e.actionnable]
    for e in a_faire:
        propre = False
        urgence = ("le binaire est ENCORE la -- il disparaitra sans preavis"
                   if e.etat == A.RECUPERABLE_PE else "binaire deja disparu, rattrapage possible")
        lignes.append("  !!  empreinte NON ARCHIVEE  %s%s : %s"
                      % (e.build, " (COURANT)" if e.courant else "", urgence))
        lignes.append("      %s" % e.commande)
    for e in inv:
        if e.etat == A.PERDUE:
            propre = False
            lignes.append("  --  empreinte PERDUE  %s : %s" % (e.build, e.detail))
        elif e.etat == A.INDETERMINEE:
            propre = False
            lignes.append("  ??  empreinte %s : %s" % (e.build, e.detail))
        elif e.etat == A.SANS_TABLE:
            propre = False
            lignes.append("  ??  empreinte %s : %s" % (e.build, e.detail))
    if propre:
        lignes.append("  OK  empreinte structurelle archivee pour les %d build(s) versionne(s)"
                      % len(inv))
    return (lignes, propre)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--quiet", action="store_true",
                    help="n'imprimer QUE si desynchronise (mode hook de session)")
    ap.add_argument("--skip-ghidra", action="store_true",
                    help="ne pas interroger ghidra-mcp (axes 1 et 2 seuls)")
    ap.add_argument("--ghidra-timeout", type=float, default=10.0,
                    help="secondes d'attente max pour ghidra-mcp (defaut 10 ; ~230 ms mesure "
                         "serveur sain). Depasse = axe NON VERIFIE, jamais un faux vert")
    args = ap.parse_args()

    lignes, ghidra_vu, couverture_vue, archive_propre = [], False, False, False
    try:
        build_dir = versioned_build()
        dll = installed_dll()
        lignes += axe1_binaire(build_dir, dll)
        lignes += axe2_coherence(build_dir)
        lignes += axe4_forme(build_dir)
        l5, couverture_vue = axe5_couverture(build_dir)
        lignes += l5
        l6, archive_propre = axe6_archive_empreinte()
        lignes += l6
        if args.skip_ghidra:
            lignes.append("  --  ghidra: non interroge (--skip-ghidra)")
        else:
            l3, ghidra_vu = axe3_ghidra(build_dir, args.ghidra_timeout)
            lignes += l3
    except (Desync, ProvenanceError) as exc:
        print("SYMBOLES DESYNCHRONISES -- toute analyse offline est FAUSSE tant que ce n'est pas regle")
        print("  " + str(exc).replace("\n", "\n  "))
        print("  Procedure de remise a niveau : CLAUDE.md, section « Au changement de build »")
        return 1

    if args.quiet and ghidra_vu and couverture_vue and archive_propre:
        return 0                        # tout verifie et synchrone : le hook se tait
    print("symboles SYNCHRONES  build=%s  binaire=%s..."
          % (build_dir.name, sha256_of(dll)[:12]))
    for l in lignes:
        print(l)
    # Les autres builds sont des ARCHIVES conservees EXPRES : leur diff contre le build courant
    # est le rapport de changement du jeu, et il doit rester consultable bien apres la fenetre
    # de migration. On les nomme pour qu'ils soient VUS -- ce n'est pas un avertissement.
    autres = archived_builds()
    if autres:
        print("  --  %d build(s) archive(s) : %s (conserves pour le diff inter-build)"
              % (len(autres), ", ".join(autres)))
    if not ghidra_vu and not args.skip_ghidra:
        print("  ATTENTION : l'axe ghidra n'a PAS ete verifie -- ne pas lancer d'agent RE sans")
        print("  l'avoir confronte (c'est l'axe qui echoue le plus silencieusement).")
    if not couverture_vue:
        print("  ATTENTION : l'axe COUVERTURE n'a PAS ete verifie -- un seul build versionne, donc")
        print("  aucune reference. Ne pas lire ce vert comme « la table est complete ».")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
