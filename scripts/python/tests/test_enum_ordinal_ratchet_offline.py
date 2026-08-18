#!/usr/bin/env python
"""Cliquet #283 -- les QUATRE enums renumerotes ne reviennent pas en dur.

POURQUOI UN CLIQUET, ET PAS SEULEMENT UNE CORRECTION
----------------------------------------------------
La MAJ `gqfc5mff6c` -> `rnca9r7q6c` a renumerote `EventTriggerType` (retrait d'`ArmorChanged`,
36 membres decales), `UtilityType` (insertion d'`AttackTile` en 8, 73 membres decales),
`StepType` (retrait de `RestoreArmorInfo`, 55 decales) et `DisplaceDirection` (retrait de
`Pull`, les 7 membres restants decales). Un ordinal fige ne casse pas : il designe un AUTRE
membre. #272 l'a mesure sur du code EXECUTABLE -- `CAPTURE_POINT = 24` rendait `MoltenForm`,
donc `0.0`, en silence.

Ce fichier verifie DEUX choses, et la seconde n'est pas decorative :

1. le depot est PROPRE sur les trois gates executables (mirrors / litteraux / tables) ;
2. le DETECTEUR mord vraiment. Un cliquet qui ne detecte rien passerait au vert sur un depot
   pourri -- et deux des motifs testes ici sont ceux qui ont REELLEMENT fait des faux positifs
   ou des faux negatifs pendant la mise au point (cf. les docstrings de chaque test).

Offline pur : aucun runner, aucune session Frida. ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts" / "python"))

import probe_283_enum_ordinal_sweep as SW  # noqa: E402


def _refs() -> dict:
    return {c: SW._by_name(SW.enum_map(SW.current_build(), fq)) for c, fq in SW.ENUMS.items()}


def _olds() -> dict:
    """LA MEME SOURCE QUE LE PROBE, et c'est le point (#10023).

    Ce fichier construisait `olds` lui-meme, a partir de `SW.previous_build()`. Il DUPLIQUAIT donc
    le cablage au lieu de le LIRE -- et quand le probe a change de source, les tests ont continue
    d'interroger l'ancienne. Un cliquet qui reconstruit ce qu'il garde ne garde pas ce qui tourne."""
    return SW.memoire_archivee_par_enum()


def _exec_hits(src: str, sigs: "dict | None" = None) -> list:
    tree = ast.parse(src)
    sw = SW._ExecSweep(SW._prose_par_ligne(src), _refs(), sigs)
    sw.visit(tree)
    return sw.hits


def _temoins(court: str = "EventTriggerType", n: int = 1) -> list:
    """(MEMBRE, ordinal ARCHIVE, ordinal COURANT) -- DERIVES des tables versionnees, jamais ecrits.

    ⚠ CE HELPER EST LA REPARATION DE FOND DE CE FICHIER (#10023). Ses fixtures figeaient
    `PreUnitAbility` / `0x2b`, `UnitDefeated` / `0x37`, `UnitRevived` / `0x2e` -- les couples du
    renumerotage `gqfc5mff6c -> rnca9r7q6c`. Un littéral qui suit un build est un cliquet qui se
    re-casse : au versionnement de `t6dpr4k06g`, les sept tests sont devenus ROUGES sans qu'une
    ligne du detecteur ait bouge. Derive, le temoin suit la table ; fige, il suit le calendrier.

    ⚠ LE CORPS A MIGRE DANS LE PROBE (#10028), et ce n'est pas cosmetique : `tests/test_1031_...`
    portait la MEME fixture, mais en version FIGEE, et elle est devenue rouge au meme
    versionnement -- la reparation de #10023 ne l'avait pas atteinte parce qu'elle vivait ICI, dans
    un fichier de test que personne d'autre n'importe. Deux copies d'un helper, c'est deux dates de
    peremption. Le foyer est `probe_283_enum_ordinal_sweep.temoins_de_decalage` ; cette fonction
    n'est plus qu'un alias local, garde pour ne pas renommer les appels de ce fichier."""
    return SW.temoins_de_decalage(court, n)         # `n = 0` -> TOUS (recensement, pas fixture)


# ------------------------------------------------- 1. le cliquet : les trois gates sont verts

def test_les_mirrors_python_collent_au_build_courant():
    """`engine/dsl/event_trigger_type.py` et `engine/utilities/utility_type.py` sont les DEUX
    mirrors dont le moteur lit les membres : une seule valeur fausse s'y propage partout."""
    bad = SW.step_mirror(verbose=False)
    assert not bad, ("mirror(s) d'enum desynchronise(s) de enums.tsv :\n"
                     + "\n".join("  %s : %s.%s = %s ; le build dit %s" % (r[0], r[1], r[2],
                                                                          r[3], r[4])
                                 for r in bad))


def test_aucun_ordinal_des_quatre_enums_en_dur_dans_scripts_python():
    """Y COMPRIS ceux qui sont JUSTES aujourd'hui : `TURN_END = 23` etait exact sur les deux
    builds versionnes, et c'est precisement ce qui le rendait invisible."""
    bad = SW.step_exec(verbose=False)
    assert not bad, ("ordinal(aux) en dur en contexte enum -- resoudre par MEMBRE :\n"
                     + "\n".join("  %s:%d %s = %s" % (r[0], r[1], r[2], r[4]) for r in bad))


def test_les_tables_de_noms_indexees_par_ordinal_suivent_le_build():
    """Le motif le plus muet : aucune annotation, aucun nom d'enum, et pourtant 100 %
    executable. `UTILITY_TYPE_NAMES` (hook `ai-utility-trace`) etiquetait chaque utilite du
    libelle de sa VOISINE a partir de l'id 8, et n'interrogeait jamais le dernier ordinal."""
    bad = SW.step_tables(verbose=False)
    assert not bad, ("table(s) de noms desynchronisee(s) de enums.tsv :\n"
                     + "\n".join("  %s:%d %s[%d] = %r (attendu %r)"
                                 % (r[0], r[1], r[2], r[4], r[5], r[6]) for r in bad))


# --------------------------------- 2. le detecteur mord (sinon le cliquet ne prouve rien)

def test_detecte_la_constante_ordinal_annotee():
    """LE motif de #272 : `CAPTURE_POINT = 24  # UtilityType.CapturePoint`. L'annotation est
    dans le COMMENTAIRE ; le littéral, lui, est evalue."""
    h = _exec_hits("CAPTURE_POINT = 24  # UtilityType.CapturePoint\n")
    assert h, "le motif #272 n'est plus detecte"
    assert h[0][1] == "UtilityType" and h[0][3] == 24 and h[0][7] is False


def test_detecte_la_comparaison_sur_un_nom_qui_trahit_l_enum():
    """`assert t.event_id == 19` : aucune annotation d'enum, mais le NOM de l'attribut suffit.
    Trois assertions de tests vivaient sous cette forme."""
    h = _exec_hits('assert t.event_id == 19, "le trigger ecoute On(TurnStart_Other)"\n')
    assert h and h[0][1] == "EventTriggerType" and h[0][3] == 19


def test_detecte_l_argument_positionnel_dont_la_signature_nomme_l_enum():
    """#315 -- LE motif que les quatre autres rataient : rien, sur la ligne du littéral, ne
    nomme l'enum. `TriggerEvent(61, 1, 2, ...)` a vecu deux fois dans
    `tests/engine/runner/test_effect_trigger_channels.py` pendant que l'etape 2 rendait
    `0 a lire` -- le nom de l'enum est dans la SIGNATURE de l'appele, pas au site d'appel."""
    sigs = {"TriggerEvent": (0, "EventTriggerType")}
    h = _exec_hits("ev = TriggerEvent(61, 1, 2, ranged=False, profile=None)\n", sigs)
    assert h, "le motif positionnel #315 n'est plus detecte"
    assert h[0][1] == "EventTriggerType" and h[0][2] == "posarg" and h[0][3] == 61
    # sans la signature, ce meme code est MUET : c'est bien elle qui porte le contrat.
    assert not _exec_hits("ev = TriggerEvent(61, 1, 2, ranged=False, profile=None)\n")


def test_les_signatures_positionnelles_se_derivent_du_depot():
    """La table des appelables est DERIVEE, jamais ecrite a la main : un appelable renomme ou
    ajoute reste couvert sans toucher au probe. `TriggerEvent` est le ctor de reference --
    `__init__(self, event_id, ...)` donne bien l'index 0 apres retrait de `self`."""
    sigs = SW._signatures_positionnelles(
        {"x.py": ast.parse("class TriggerEvent:\n"
                           "    def __init__(self, event_id, actor_id):\n"
                           "        pass\n"
                           "def get_utility(utility_type, ctx):\n"
                           "    return 0\n")})
    assert sigs["TriggerEvent"] == (0, "EventTriggerType")
    assert sigs["get_utility"] == (0, "UtilityType")


def test_ne_signale_PAS_l_usage_symbolique_correct():
    """Anti-faux-positif MESURE : `TILE_LEAVES[UtilityType.CapturePoint][1]` a ete signale 7
    fois par la 1re version, qui cherchait l'annotation dans la ligne BRUTE. Le `1` y est un
    index de tuple, et le code est DEJA correct -- il passe par le membre."""
    h = _exec_hits("leaf = TILE_LEAVES[UtilityType.CapturePoint][1]\n")
    assert not h, "faux positif : l'usage symbolique ne doit pas etre signale"


def test_la_prose_ne_signale_pas_l_homonyme_extraHit():
    """LE piege qui interdit tout `sed` : `0x2b` est aussi la cle de config `extraHit`
    (~100 occurrences legitimes). Sans le NOM du membre accole, rien ne doit sortir."""
    refs, olds = _refs(), _olds()
    amb = SW._ambigus(SW.current_build())
    rxs = {c: SW._compile_prose(r, amb) for c, r in refs.items()}
    cites, _, _ = SW._scan_prose_fichier(
        '# nb de coups bonus : GetNumberConstant(cfg, 0x2b) = extraHit\n', refs, olds, rxs)
    assert not cites, "l'homonyme extraHit a ete signale -- un sed suivrait et casserait le code"


def test_la_prose_detecte_la_citation_perimee_et_la_qualifie_ancien():
    """`On(<ordinal ARCHIVE> = <Membre>)` : le NOM donne l'attendu, et l'origine `ancien` PROUVE
    que ce nombre etait bien son ordinal sur un build archive -- c'est ce qui autorise la
    reecriture automatique.

    Le couple est DERIVE (`_temoins`), plus figé sur `0x2b = PreUnitAbility` : c'est ce littéral
    qui a rendu ce test rouge au versionnement de `t6dpr4k06g` (#10023)."""
    membre, ancien, courant = _temoins()[0]
    refs, olds = _refs(), _olds()
    amb = SW._ambigus(SW.current_build())
    rxs = {c: SW._compile_prose(r, amb) for c, r in refs.items()}
    cites, _, _ = SW._scan_prose_fichier(
        '# le trigger = On(0x%x = %s) & gate\n' % (ancien, membre), refs, olds, rxs)
    assert cites, "la citation perimee n'est plus detectee"
    assert cites[0][2] == membre and cites[0][5] == "ancien", cites
    assert cites[0][4] == courant, cites


# ----------------------------- 2bis. les TROIS surfaces ajoutees par #420 mordent, et elles
#                                     seules (chaque anti-cas ci-dessous a ete MESURE faux)

def _larges(src: str) -> list:
    """La 3e valeur de `_scan_prose_fichier` = les hits du GATE 4bis."""
    refs, olds = _refs(), _olds()
    amb = SW._ambigus(SW.current_build())
    rxs = {c: SW._compile_prose(r, amb) for c, r in refs.items()}
    lgs = {c: SW._compile_larges(r, olds.get(c, {}), amb) for c, r in refs.items()}
    return SW._scan_prose_fichier(src, refs, olds, rxs, ".py", lgs)[2]


def test_4bis_mord_sur_le_separateur_LARGE_que_l_etape_4_ratait():
    """LA raison d'etre du gate : `` `...,0x37` UnitDefeated `` a vecu dans le depot sans
    rougir nulle part -- le backtick sort du separateur `[\\s=:]{0,4}` de l'etape 4.

    Les DEUX couples sont derives (`_temoins`), pas recopies de la citation d'epoque."""
    (m1, a1, _), (m2, a2, _) = _temoins(n=2)
    h = _larges("# sequence : `...,0x%x` %s -> `...,0x%x` %s\n" % (a1, m1, a2, m2))
    noms = {x[2] for x in h}
    assert noms == {m1, m2}, h


def test_4bis_mord_sur_la_forme_TRIPLE_du_depot():
    """`On(<Membre> = <dec> = <hex>)` : les deux bases encadrent le membre, donc le 2e nombre
    n'est adjacent a AUCUN nom. C'est ainsi que `On(UnitRevived = 45 = 0x2e)` -- moitie juste,
    moitie perime -- a survecu."""
    membre, ancien, courant = _temoins()[0]
    h = _larges("# emet `On(%s = %d = 0x%x)` puis purge\n" % (membre, courant, ancien))
    assert [(x[2], x[3]) for x in h] == [(membre, "0x%x" % ancien)], h


def test_4bis_ne_mord_PAS_sur_un_nombre_type_par_On():
    """FAUX POSITIF MESURE (3 sites) : `` `On(0x12)` -> ActivateEffect ``. `0x12` est un
    `EventTriggerType` JUSTE ; `ActivateEffect` est un membre de `StepType` dont 0x12 etait
    l'ordinal archive. Le contrat natif `IdunBattleLogic.Entities.DSLTriggers$$On(EventTriggerType, ...)` type le
    nombre : aucun AUTRE enum ne peut le revendiquer."""
    assert not _larges("# `On(0x21)&OwnerIsActor`, `On(0x12)` -> ActivateEffect ;\n")


def test_4bis_ne_mord_PAS_a_travers_un_separateur_de_LISTE():
    """FAUX POSITIF MESURE (2 sites, virgule et slash) : dans
    `(SummonDislikeDoorOpening 30 / HeroLikeDoorOpening 31)` le `30` etiquette l'element
    PRECEDENT. La ligne est JUSTE, et 30 est pourtant l'ordinal archive de sa voisine."""
    assert not _larges("#  door : (SummonDislikeDoorOpening 30 / HeroLikeDoorOpening 31)\n")
    assert not _larges('#  "SummonDislikeDoorOpening 30, HeroLikeDoorOpening 31, X 57"\n')


def test_4bis_exempte_le_rappel_HISTORIQUE_qui_nomme_le_build_archive():
    """Une citation qui documente le bug PASSE ne doit pas etre « corrigee » -- ce serait
    detruire ce qu'elle prouve. L'exemption porte sur +/-3 LIGNES, pas sur le token : un bloc
    de commentaires `#` est decoupe en un token PAR LIGNE, et le nom du build est en general
    sur la ligne suivante (cas mesure : `probe_hazeord_blast_radius.py`)."""
    membre, ancien, _courant = _temoins()[0]
    tete = "# cette table portait `%d: %s`, ce qui etait juste\n" % (ancien, membre)
    sans = tete + "# avant la MAJ\n"
    avec = tete + "# sur le build %s -- plus depuis\n" % SW.builds_avec_table_enums()[0]
    assert _larges(sans), "le detecteur ne mord plus : l'exemption ne prouverait rien"
    assert not _larges(avec), "le rappel historique n'est pas exempte"


def test_etape2_ne_compte_PAS_un_litteral_HORS_PLAGE():
    """`WeightedUtility(utility_type=99999)` EXIGE un type hors base (il verifie que
    `UtilityDecider.CalculateUtility` LEVE au lieu de compter 0). Aucun membre ne porte 99999
    sur aucun des deux builds -> ce n'est pas un ordinal fige, c'est une sentinelle. C'etait
    l'unique faux positif du probe, et il le faisait echouer sur `origin/master`."""
    refs, olds = _refs(), _olds()
    src = "x = f(utility_type=99999)\n"
    sw = SW._ExecSweep(SW._prose_par_ligne(src), refs, None, olds)
    sw.visit(ast.parse(src))
    assert not sw.hits and len(sw.hors) == 1, (sw.hits, sw.hors)
    # ... mais un ordinal REEL du meme contexte reste signale :
    src2 = "x = f(utility_type=24)\n"
    sw2 = SW._ExecSweep(SW._prose_par_ligne(src2), refs, None, olds)
    sw2.visit(ast.parse(src2))
    assert sw2.hits and not sw2.hors, (sw2.hits, sw2.hors)


def test_etape5_ancre_AUSSI_la_quote_verbatim_du_helper_de_publication():
    """18 quotes `FUN_<addr>(0x4d|0x50, .., <ordinal>)` portaient un ordinal PERIME sans
    qu'aucune etape ne les voie : ni ancre `On(`, ni membre accole. Le SLOT est ce qui rend
    l'ancre sure -- le nom `FUN_<addr>` change a chaque build."""
    txt = "        #     FUN_1800280e0(0x4d, .., 0x2a);\n"
    assert SW._FUN_PUB.search(txt), "l'ancre de quote ne mord pas"
    args = SW._FUN_PUB.search(txt).group(1)
    lits = [a.strip() for a in args.split(",") if SW._FUN_LIT.match(a.strip())]
    assert lits[-1] == "0x2a", lits
    # un slot qui n'est pas un slot de publication ne doit rien ancrer
    assert not SW._FUN_PUB.search("# FUN_1801f4390(DAT_1833ae538, 2)\n")


# --------------------------- 2ter. les DEUX formes que l'ancre ne voyait pas (#420-r2/-r3),
#                                   et la DECIDABILITE par annotation (#420-r5)

def _dernier_litteral(txt: str):
    """Ce que l'etape 5 retient d'une quote : le DERNIER littéral ENTIER de ses arguments."""
    g = SW._FUN_PUB.search(txt)
    if g is None:
        return None
    lits = [a.strip() for a in g.group(1).split(",") if SW._FUN_LIT.match(a.strip())]
    return lits[-1] if lits else None


def test_etape5_ancre_le_slot_0x51_dont_le_litteral_est_AVANT_dernier():
    """#420-r2. Le slot `0x51` porte un AUTRE helper que `0x4d`/`0x50` (8 arguments), et son
    littéral d'evenement est suivi d'un `&args`. LU au decompile de `rnca9r7q6c` :
    `IdunBattle.Operations.FinishUnitTurnOperation$$Execute` publie `0x1c`, `0x28` puis `0x29`
    par `FUN_1800284a0(0x51, .., unit, unit, unit, <n>, &args)`, et
    `IdunBattle.Operations.ResurrectUnitOperation$$Execute` publie `0x2e` de meme.

    Le residu decrivait la POSITION comme l'obstacle ; elle n'en est pas un -- `&args` n'est
    pas un littéral, donc l'avant-dernier argument EST le dernier littéral. Seul le slot
    manquait au motif."""
    assert _dernier_litteral("# FUN_1800284a0(0x51, .., 0x2e, &args)") == "0x2e"
    assert _dernier_litteral("# FUN_1800284a0(0x51, .., unit, unit, unit, 0x1c, &args)") == "0x1c"


def test_etape5_ancre_la_quote_dont_le_SLOT_est_ELIDE():
    """#420-r3. Deux quotes du depot elident le slot (`probe_120`, `sworn_protector.py`) :
    l'ellipse est NOTRE ecriture, elle remplace les arguments fixes du helper. Les deux formes
    d'ellipse existent dans l'arbre, ASCII (`..`) et Unicode."""
    assert _dernier_litteral("# FUN_1800280e0(.., 0x2a)") == "0x2a"
    assert _dernier_litteral("# FUN_1800280e0(…, 0x3d)") == "0x3d"


def test_etape5_ne_confond_PAS_un_slot_d_INTERFACE_avec_une_publication():
    """Un slot n'identifie une methode que DANS son interface : `0x51` d'`IBattleQuery` est
    `GetFreeAdjacentTiles` (`FUN_180003bd0(0x51, itf, service, caster)`, seul `0x51` du depot),
    sans rapport avec `0x51` du dispatcher d'evenements. Il n'a AUCUN littéral dans ses
    arguments, donc l'ancre elargie ne peut rien lui attribuer -- c'est ce qui autorise
    d'ajouter le slot sans risquer un faux positif."""
    assert _dernier_litteral("(`FUN_180003bd0(0x51, itf, service, caster)`)") is None
    assert _dernier_litteral("FUN_180002560(0, DAT_1831d4f88, playbook)") is None


def _ann(ligne: str, v: int):
    ref = _refs()["EventTriggerType"]
    old = SW.memoire_archivee(SW.ENUMS["EventTriggerType"])     # la source du probe (#10023)
    return SW.annotation_de_ligne(ligne, v, ref, old)


def test_l_annotation_On_Membre_rend_la_quote_DECIDABLE_et_le_GATE_MORD():
    """#420-r5, LES DEUX DIRECTIONS. Une quote verbatim ne peut pas porter son membre DEDANS
    sans cesser d'etre verbatim ; le membre se pose A COTE, `On(<Membre>)` sur la meme ligne.

    * coherent avec le build courant -> `ancree` : la quote sort des indecidables ;
    * egal a l'ordinal ARCHIVE du membre nomme -> `perimee` : FAIL, meme critere PROUVE que
      4bis. C'est ce cas-la qui mordra au PROCHAIN changement de build, sans qu'une ligne du
      depot ait bouge -- le gisement exact de #283.

    Le couple est DERIVE. Ecrit en dur (`PreUnitAbility` / `0x2b`), il a mordu sur NOUS au
    versionnement de `t6dpr4k06g` : `0x2b` n'etait plus l'ordinal archive de personne (#10023) --
    le mode d'echec que ce test PREDIT, subi par le test lui-meme."""
    membre, ancien, courant = _temoins()[0]
    quote = "#  FUN_1800280e0(0x4d, .., 0x%x);   # On(%s)"
    assert _ann(quote % (courant, membre), courant)[0] == "ancree"
    etat, vu = _ann(quote % (ancien, membre), ancien)
    assert (etat, vu) == ("perimee", membre), (etat, vu)
    # ... et le detecteur DOIT mordre, sinon les deux assertions ci-dessus ne prouveraient rien
    assert ancien in SW._ords(
        SW.memoire_archivee(SW.ENUMS["EventTriggerType"]).get(membre)), membre


def test_une_ancre_NUE_ou_a_membre_INCONNU_reste_un_COMPTEUR():
    """Le gate ne mord QUE la ou un auteur a DECLARE le membre. Sans annotation, ou avec un nom
    qui n'est membre d'`EventTriggerType` sur AUCUN des deux builds, l'ancre reste indecidable
    -- on ne rougit jamais sur une annotation qu'on ne comprend pas. C'est ce qui rend l'ancre
    elargie (slot `0x51`, slot elide) incapable de fabriquer un faux rouge."""
    assert _ann("#  FUN_1800280e0(0x4d, .., 0x2a);", 0x2a)[0] == "nue"
    assert _ann("#  FUN_1800280e0(0x4d, .., 0x2a);  # On(Zorglub)", 0x2a)[0] == "nue"
    # la forme NOMMEE `On(<n> = <Membre>)` n'est PAS une annotation : elle porte un nombre,
    # et c'est l'etape 4 qui la confronte.
    assert _ann("#  On(0x2b = PreUnitAbility)", 0x2b)[0] == "nue"


def test_le_depot_ne_porte_AUCUNE_quote_de_publication_INDECIDABLE():
    """LE CLIQUET DE GISEMENT (#420-r5). Une quote `FUN_` dont l'ordinal a change de
    proprietaire entre les deux builds versionnes et qui ne porte PAS son `On(<Membre>)` est,
    par construction, invisible a toutes les etapes : elle peut etre juste ou perimee, rien ne
    le dira jamais. Elles etaient 16 le 2026-08-07 ; ce test garde le zero.

    Si tu ajoutes une quote et que ce test rougit : pose l'annotation `On(<Membre>)` sur sa
    ligne, apres avoir LU au decompile quel evenement ce site publie. Ne la retire pas."""
    _stables, decales, _ancrees, _fails, _amb = SW.step_on(verbose=False)
    fun = [d for d in decales if d[5] == "FUN"]
    assert not fun, ("quote(s) de publication INDECIDABLE(S) -- annoter `On(<Membre>)` sur la "
                     "ligne :\n" + "\n".join("  %s:%d  FUN_...(%s) : etait %s, vaut %s"
                                             % (d[0], d[1], d[2], d[3], d[4]) for d in fun))


def test_aucune_ancre_ANNOTEE_du_depot_ne_cite_un_ordinal_PERIME():
    """Le GATE, joue sur l'arbre. Il est vert aujourd'hui et le restera tant que le build ne
    bougera pas ; au prochain build il rougira sur chaque annotation dont l'ordinal a glisse --
    c'est exactement ce qu'on lui demande, et ce qu'aucun declencheur sur diff ne peut voir."""
    _stables, _decales, ancrees, fails, ambigues = SW.step_on(verbose=False)
    assert not fails, ("citation(s) PROUVEE(S) perimee(s) :\n"
                       + "\n".join("  %s:%d  (%s) annote On(%s)" % (f[0], f[1], f[2], f[3])
                                   for f in fails))
    # non-vide : un gate joue sur un ensemble VIDE passerait pour vert sans rien garder.
    assert ancrees, "aucune ancre annotee -- le gate ne s'applique a RIEN"
    #: ⚠ ET LE GATE NE PORTE QUE SUR DES QUOTES (#1031). Une ancre `On(<n>)` n'a PAS besoin
    #: d'annotation adjointe -- sa voie propre est la forme NOMMEE `On(<n> = <Membre>)`, que
    #: l'etape 4 confronte. L'apparier a un `On(<Membre>)` voisin, c'est apparier deux MENTIONS
    #: d'une meme phrase : le depot n'en portait que deux, une juste par accident et une fausse
    #: par accident (le rouge de `master`). Si cette assertion tombe, c'est que le gate s'est
    #: RE-etendu au voisinage -- relire `annotation_de_ligne`, ne pas relacher ici.
    assert all(a[4] == "FUN" for a in ancrees), (
        "ancre(s) NON-quote ancree(s) par voisinage :\n"
        + "\n".join("  %s:%d  On(%s) <- On(%s)" % (a[0], a[1], a[2], a[3])
                    for a in ancrees if a[4] != "FUN"))
    #: Ce qui est ECARTE doit rester VISIBLE : un releve neuf que personne n'assertionne est
    #: un compteur qu'on peut faire enfler sans que rien ne le dise.
    assert isinstance(ambigues, list)


# ------------------------------------------------------- 3. le diff des tables reste derivable

def test_le_diff_des_quatre_enums_est_derivable_offline():
    """Les tables archivees sont VERSIONNEES : le rapport de changement doit rester calculable
    dans un worktree frais, sans session ni dump.

    ⚠ CE TEST FIGEAIT `PreUnitAbility == 43` SUR `previous_build()`, ET C'EST CE LITTERAL QUI L'A
    FAIT ROUGIR (#10023). `43` etait l'ordinal du membre sur `gqfc5mff6c` ; au versionnement de
    `t6dpr4k06g`, `previous_build()` a designe `rnca9r7q6c`, ou le membre vaut deja `42`. Le fait
    mesure n'avait pas change -- c'est la QUESTION qui avait bouge sous lui. Reecrire `43` en `42`
    aurait rendu le test vert ET vacant (il aurait compare une table a elle-meme), en le
    reprogrammant pour re-casser au build suivant.

    Ce qui est garde ici est donc l'ENONCE, pas son instance : la memoire archivee est LISIBLE et
    porte EFFECTIVEMENT un decalage. Le fait historique, pour memoire :
    `gqfc5mff6c -> rnca9r7q6c` a deplace 171 membres, dont `PreUnitAbility` (43 -> 42)."""
    archives = SW.builds_avec_table_enums()
    assert archives, "aucun build archive PORTANT frida/enums.tsv -- le diff n'est plus derivable"
    cur = SW.current_build()
    for court, fq in SW.ENUMS.items():
        n = SW.enum_map(cur, fq)
        assert n, "enum %s absent de la table du build courant" % court
        for b in archives:
            assert SW.enum_map(b, fq), "enum %s absent de la table archivee %s" % (court, b)
    # NON-VIDE : sans un seul decalage archive, tout le volet DISCRIMINATION de ce fichier
    # (5 tests) tourne a vide. Le compte est imprime dans le message pour que la perte se lise.
    decales = {court: len(_temoins(court, n=0)) for court in SW.ENUMS}
    assert sum(decales.values()) > 0, (
        "aucun ordinal decale sur les archives %s : le detecteur d'ordinaux perimes n'a plus de "
        "quoi mordre -- ventilation %s" % (archives, decales))
    # Et le temoin d'`EventTriggerType` doit exister NOMMEMENT : c'est celui qu'exercent les cinq
    # fixtures de discrimination ci-dessus.
    membre, ancien, courant = _temoins()[0]
    assert ancien != courant and membre
