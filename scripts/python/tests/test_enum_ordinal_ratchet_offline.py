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


def _exec_hits(src: str, sigs: "dict | None" = None) -> list:
    tree = ast.parse(src)
    refs = {c: SW._by_name(SW.enum_map(SW.current_build(), fq))
            for c, fq in SW.ENUMS.items()}
    sw = SW._ExecSweep(SW._prose_par_ligne(src), refs, sigs)
    sw.visit(tree)
    return sw.hits


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
    refs = {c: SW._by_name(SW.enum_map(SW.current_build(), fq)) for c, fq in SW.ENUMS.items()}
    olds = {c: SW._by_name(SW.enum_map(SW.previous_build(), fq)) for c, fq in SW.ENUMS.items()}
    amb = SW._ambigus(SW.current_build())
    rxs = {c: SW._compile_prose(r, amb) for c, r in refs.items()}
    cites, _ = SW._scan_prose_fichier(
        '# nb de coups bonus : GetNumberConstant(cfg, 0x2b) = extraHit\n', refs, olds, rxs)
    assert not cites, "l'homonyme extraHit a ete signale -- un sed suivrait et casserait le code"


def test_la_prose_detecte_la_citation_perimee_et_la_qualifie_ancien():
    """`On(0x2b = PreUnitAbility)` : le NOM donne l'attendu (42 = 0x2a), et l'origine `ancien`
    PROUVE que 0x2b etait bien son ordinal sur le build precedent -- c'est ce qui autorise la
    reecriture automatique."""
    refs = {c: SW._by_name(SW.enum_map(SW.current_build(), fq)) for c, fq in SW.ENUMS.items()}
    olds = {c: SW._by_name(SW.enum_map(SW.previous_build(), fq)) for c, fq in SW.ENUMS.items()}
    amb = SW._ambigus(SW.current_build())
    rxs = {c: SW._compile_prose(r, amb) for c, r in refs.items()}
    cites, _ = SW._scan_prose_fichier('# le trigger = On(0x2b = PreUnitAbility) & gate\n',
                                      refs, olds, rxs)
    assert cites, "la citation perimee n'est plus detectee"
    assert cites[0][2] == "PreUnitAbility" and cites[0][5] == "ancien"


# ------------------------------------------------------- 3. le diff des tables reste derivable

def test_le_diff_des_quatre_enums_est_derivable_offline():
    """Les deux tables sont VERSIONNEES : le rapport de changement doit rester calculable dans
    un worktree frais, sans session ni dump."""
    prev = SW.previous_build()
    assert prev, "aucun build archive sous data/symbols -- le diff n'est plus derivable"
    for court, fq in SW.ENUMS.items():
        o, n = SW.enum_map(prev, fq), SW.enum_map(SW.current_build(), fq)
        assert o and n, "enum %s absent d'une des deux tables" % court
    # Le fait mesure qui ouvre le dossier, re-derive : `PreUnitAbility` a bien recule d'un cran.
    ett = SW.ENUMS["EventTriggerType"]
    assert SW._by_name(SW.enum_map(prev, ett))["PreUnitAbility"] == 43
    assert SW._by_name(SW.enum_map(SW.current_build(), ett))["PreUnitAbility"] == 42
