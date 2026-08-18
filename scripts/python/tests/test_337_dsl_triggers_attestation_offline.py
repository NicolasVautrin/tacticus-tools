"""#337 -- l'ATTESTATION des primitives `DSLTriggers` tient-elle, et tient-elle TOUTE SEULE ?

Le livrable de #337 n'est pas une prose : c'est un verdict RE-DERIVABLE par l'outil. Deux
mecanismes, deux familles de tests ici :

  1. la NORMALISATION d'identifiant (`_norm_ident`) et la DESAMBIGUISATION de famille
     (`_family_ok`) -- corrections systematiques de l'heuristique d'appariement ;
  2. la table d'attestation `docs/rl/dsl-port-attestations.tsv` -- le canal ou un humain tranche,
     avec ses quatre cliquets. Une table d'attestation non verifiee serait PIRE que le
     `CITE_A_QUALIFIER` qu'elle remplace : elle mentirait avec l'autorite d'une mesure.

OFFLINE et AUTO-PORTANTS (meme regle que `test_326_dsl_join_offline.py`) : rien n'est lu dans le
repertoire de sortie gitignore -- l'inventaire natif est RE-DERIVE des tables de symboles
VERSIONNEES, et les cas negatifs fabriquent leurs entrees dans `tmp_path`.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PYDIR))

import probe_326_dsl_port_matching as M               # noqa: E402
import probe_326_dsl_primitive_inventory as INV       # noqa: E402

ATTESTATIONS = ROOT / "docs" / "rl" / "dsl-port-attestations.tsv"

# PERIMETRE DECLARE de la table d'attestation -- litteral NOMME, jamais un effet de bord.
# #337 l'a ouverte sur `DSLTriggers` SEULE ; #393-r1 y ajoute `DSLFormulas`. Les deux familles
# n'ont PAS le meme regime, et c'est VOULU :
#   * `DSLTriggers` : COMPLETE -- les 165 primitives sont tranchees, cliquet de completude
#     `test_la_famille_DSLTriggers_est_INTEGRALEMENT_TRANCHEE` ci-dessous.
#   * `DSLFormulas` : PARTIELLE -- attestations a la carte, AUCUN cliquet de completude. Une
#     primitive `DSLFormulas` non attestee reste donc `CITE_A_QUALIFIER`, ce qui est l'aveu
#     honnete que l'outil ne sait pas l'attribuer -- pas un verdict.
# Elargir cette liste est une decision de CADRAGE : elle se prend ici, explicitement.
PERIMETRE_ATTESTATIONS = {"DSLTriggers", "DSLFormulas"}


def _native():
    """Inventaire natif RE-DERIVE de `data/symbols/<CURRENT>/` (versionne)."""
    prim = INV.native_primitives(INV._current_build())
    return [{"family": f, "name": n, "symbol": e["symbol"],
             "ov_frida": e["overloads_frida"], "ov_ghidra": e["overloads_ghidra"]}
            for (f, n), e in sorted(prim.items())]


def _symbol_by_key(native):
    return {(p["family"], p["name"]): p["symbol"] for p in native}


# --- 1. Normalisation d'identifiant ------------------------------------------------------------

def test_norm_ident_apparie_les_trois_formes_manquees():
    """Les trois formes MESUREES sur `DSLTriggers` : accesseur C#, snake_case, porteur snake."""
    assert M._norm_ident("get_OwnerIsCaster") == M._norm_ident("OwnerIsCaster")
    assert M._norm_ident("IsMechanical") == M._norm_ident("is_mechanical")
    assert M._norm_ident("AbilityHasAttackType") == M._norm_ident("ability_has_attack_type")


def test_norm_ident_ne_mutile_pas_un_get_snake_case():
    """`get_spawn_tile_selector` (Python) et `GetSpawnTileSelector` (natif) sont la MEME chose :
    amputer le `get_` d'un seul cote casserait la paire. D'ou la garde MAJUSCULE dans
    `ACCESSOR_RE` -- seul `get_<Upper>` est une propriete C#."""
    assert M._norm_ident("get_spawn_tile_selector") == M._norm_ident("GetSpawnTileSelector")
    assert M._norm_ident("get_OwnerIsCaster") != M._norm_ident("GetOwnerIsCaster")


def test_family_ok_ne_filtre_que_les_noms_AMBIGUS():
    """`Direct` existe dans TROIS familles ; un nom porte par une seule garde l'ancien
    comportement (toute citation compte)."""
    amb = {"Direct"}
    assert M._family_ok("DSLFormulas", "DSLTriggers", "Direct", amb) is False
    assert M._family_ok("DSLTriggers", "DSLTriggers", "Direct", amb) is True
    # orthographe HERITEE : le build `gqfc5mff6c` n'avait qu'UNE classe-factory -> ambigue par
    # construction, donc acceptee partout.
    assert M._family_ok("DSLFactory", "DSLTriggers", "Direct", amb) is True
    # nom non ambigu : aucun filtre.
    assert M._family_ok("DSLFormulas", "DSLTriggers", "IsUnit", set()) is True


def test_direct_est_bien_porte_par_plusieurs_familles():
    """La premisse de `_family_ok`, RE-DERIVEE du build (pas heritee de ce fichier)."""
    prim = INV.native_primitives(INV._current_build())
    fams = {fam for (fam, name) in prim if name == "Direct"}
    assert {"DSLTriggers", "DSLFormulas"} <= fams, fams


# --- 2. La table d'attestation, et ses quatre cliquets ------------------------------------------

def test_la_table_versionnee_est_VALIDE_sur_le_build_courant():
    """CLIQUET PRINCIPAL. Chaque ligne est re-verifiee : symbole present dans le vocabulaire du
    build, fichier porteur existant, ancre resolue, primitive effectivement citee. Un port
    renomme/deplace fait donc ROUGIR ce test au lieu de laisser survivre une attestation morte."""
    native = _native()
    att = M.read_attestations(str(ATTESTATIONS), _symbol_by_key(native))
    assert att, "table d'attestation vide ou introuvable"
    fams = {k[0] for k in att}
    hors = sorted(fams - PERIMETRE_ATTESTATIONS)
    assert not hors, (
        "famille HORS du perimetre declare %s : %s -- l'elargir se decide dans "
        "`PERIMETRE_ATTESTATIONS`, ce n'est pas un effet de bord d'une attestation"
        % (sorted(PERIMETRE_ATTESTATIONS), hors))
    # `<=` seul laisserait passer une table VIDEE de DSLTriggers ; la famille COMPLETE doit y etre.
    assert "DSLTriggers" in fams, fams


def _write(tmp_path, line):
    p = tmp_path / "att.tsv"
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("symbol\tverdict\tancre\tnote\n")
        fh.write(line + "\n")
    return str(p)


def test_cliquet_symbole_disparu_du_build(tmp_path):
    p = _write(tmp_path, "IdunBattleLogic.Entities.DSLTriggers$$CeNoeudNExistePas\tNON_PORTE\t"
                         "scripts/python/engine/dsl/base.py:Const\t-")
    with pytest.raises(SystemExit, match="perimee"):
        M.read_attestations(p, _symbol_by_key(_native()))


def test_cliquet_porteur_introuvable(tmp_path):
    p = _write(tmp_path, "IdunBattleLogic.Entities.DSLTriggers$$IsUnit\tPORTE_HORS_FACADE\t"
                         "scripts/python/engine/nexiste_pas.py:foo\t-")
    with pytest.raises(SystemExit, match="porteur introuvable"):
        M.read_attestations(p, _symbol_by_key(_native()))


def test_cliquet_ancre_introuvable(tmp_path):
    """On attache a un NOM (class/def/constante), jamais a un numero de ligne -- une ancre qui ne
    se resout plus est le signal qu'un port a bouge."""
    p = _write(tmp_path, "IdunBattleLogic.Entities.DSLTriggers$$IsUnit\tPORTE_HORS_FACADE\t"
                         "scripts/python/engine/runner/damage_model.py:CeSymboleNExistePas\t-")
    with pytest.raises(SystemExit, match="ancre"):
        M.read_attestations(p, _symbol_by_key(_native()))


def test_cliquet_le_porteur_doit_CITER_la_primitive(tmp_path):
    """Le coeur du dispositif : une attestation qui pointe un artefact MUET sur son artefact natif
    n'atteste rien. `dsl/base.py:Const` existe, mais ne cite pas `TargetIsOverkilled`."""
    p = _write(tmp_path, "IdunBattleLogic.Entities.DSLTriggers$$TargetIsOverkilled\t"
                         "PORTE_HORS_FACADE\tscripts/python/engine/dsl/base.py:Const\t-")
    with pytest.raises(SystemExit, match="ne CITE pas"):
        M.read_attestations(p, _symbol_by_key(_native()))


def test_cliquet_verdict_hors_vocabulaire(tmp_path):
    p = _write(tmp_path, "IdunBattleLogic.Entities.DSLTriggers$$IsUnit\tPRESQUE_PORTE\t"
                         "scripts/python/engine/runner/damage_model.py:defender_modifiers\t-")
    with pytest.raises(SystemExit, match="verdict"):
        M.read_attestations(p, _symbol_by_key(_native()))


# --- 3. Le resultat de bout en bout -------------------------------------------------------------

def test_la_famille_DSLTriggers_est_INTEGRALEMENT_TRANCHEE(tmp_path, capsys):
    """CLIQUET DE LIVRAISON #337 : plus AUCUN `CITE_A_QUALIFIER` dans `DSLTriggers`.

    `CITE_A_QUALIFIER` n'est pas une mesure, c'est l'aveu que l'outil ne sait pas attribuer. Les
    165 primitives de la famille sont desormais soit attestees PORTEES, soit LUES et declarees
    absentes. Le probe tourne ici sur un inventaire re-derive et ecrit dans `tmp_path`, mais lit
    la VRAIE table d'attestation : c'est elle qu'on valide.
    """
    native_tsv = tmp_path / "native.tsv"
    with io.open(native_tsv, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# schema=326.native.v1 (re-derive du build courant)\n")
        fh.write("family\tname\tsymbol\toverloads_frida\toverloads_ghidra\n")
        for p in _native():
            fh.write("%s\t%s\t%s\t%d\t%d\n"
                     % (p["family"], p["name"], p["symbol"], p["ov_frida"], p["ov_ghidra"]))
    out = tmp_path / "coverage.tsv"
    argv = sys.argv
    sys.argv = ["probe_326_dsl_port_matching.py", "--native", str(native_tsv),
                "--out", str(out), "--attestations", str(ATTESTATIONS)]
    try:
        M.main()
    finally:
        sys.argv = argv
    capsys.readouterr()

    rows = [ln.rstrip("\n").split("\t") for ln in io.open(out, encoding="utf-8")
            if not ln.startswith("#") and not ln.startswith("family\t")]
    trig = [r for r in rows if r[0] == "DSLTriggers"]
    assert len(trig) == 165, len(trig)
    a_qualifier = [r[1] for r in trig if r[5] == "CITE_A_QUALIFIER"]
    assert not a_qualifier, "primitives DSLTriggers encore non tranchees : %s" % a_qualifier

    # Les `NON_PORTE` LUES : leur verdict vient d'une lecture, pas d'un silence.
    # ⚠ CET ENSEMBLE EST UN INVENTAIRE, PAS UNE PROPRIETE : il CROIT des qu'une tranche cite une
    # primitive `DSLTriggers` a titre documentaire (ancrer une carte de slots, nommer un producteur).
    # L'y ajouter est le geste que ce cliquet EXIGE -- ce qui serait interdit, c'est de retirer la
    # ligne d'attestation pour faire taire le rouge. Les quatre premiers viennent de #337, les trois
    # `get_*` de #459 (identification des slots `CasterTile`/`TargetTile`, et la preuve que le natif
    # n'a PAS de slot `OwnerTile`).
    # ⚠ IL PEUT AUSSI DECROITRE, et c'est le sens SAIN : `ActorHasTriggeredAbility` en est SORTI
    # (#577) parce que son unique consommateur natif -- `AdaptiveStrategyAbility$$ExecuteBehaviour`,
    # active 1005 -- est entre dans `ABILITY_CLASSES`, donc l'arbre porte CONSTRUIT desormais le
    # noeud. Une mention documentaire qui devient un PORT change de colonne dans la table
    # d'attestation ET ici, dans le MEME commit -- et l'assertion suivante verifie qu'elle a bien
    # change de colonne, au lieu d'avoir simplement disparu de la table.
    # `IsPlayerDefeated` vient de #962 : #960 (`ArmourOfShriekingSouls`) l'a CITEE en portant le
    # gate `If(NOT AmountIsZero(Filter(PlayersByTeam, NOT IsPlayerDefeated)), ...)` de
    # `$$Resurrect`. Le natif alloue un trigger DEDIE dont le predicat
    # (`PlayerExtensions$$IsPlayerDefeated`) a TROIS branches, dont le port n'a de substrat que pour
    # UNE (`_team_has_living_unit`, degradation RESTRICTIF nommee) -- donc NON_PORTE, exactement la
    # croissance d'inventaire que le paragraphe ci-dessus decrit.
    # ⚠ `IsFirstHitGroupInAttack` en est SORTIE (#962), et c'est le mouvement SAIN decrit ci-dessus
    # -- le MEME qu'`ActorHasTriggeredAbility` en #577 : l'HEURISTIQUE l'attribue desormais
    # elle-meme (`PORTE_ALIAS_FACADE`, noeud `IsFirstHitGroupInAttackTrigger` porte par l'export
    # `IsFirstHitInSeries`), et une attestation ne s'applique QUE si l'heuristique n'a rien trouve.
    # Sa ligne du TSV, devenue redondante, est RETIREE dans le meme commit -- et l'assertion
    # `porte` ci-dessous verifie qu'elle a bien CHANGE DE COLONNE, pas seulement disparu.
    # `IsMoving` vient de #1082, et c'est EXACTEMENT la croissance d'inventaire decrite ci-dessus,
    # au meme motif qu'`AttackUsedAttackDamage` : #1080 (`BattleFocus`) a CITE le symbole en
    # documentant le collapse a VRAI de `NOT IsMoving(Owner)` (residu `#1080-r1`), ce qui a fait
    # basculer l'heuristique de `NON_PORTE` (aucune citation) vers `CITE_A_QUALIFIER`. Le port ne
    # CONSTRUIT toujours pas le noeud -> `NON_PORTE`. Ce rouge est arrive sur `master` par le merge
    # de #1080 (`d896e41a`, provenance mesuree `git log -S`), et il a ete trouve AU REJEU APRES
    # REBASE -- il ne s'etait vu dans aucune des deux PR.
    lus = {r[1] for r in trig if r[6].startswith("attestation:") and r[5] == "NON_PORTE"}
    assert lus == {"Direct", "IsMoving",
                   "IsInTeamSynapseRange", "IsPlayerDefeated",
                   "get_CasterIsCasterTile", "get_OwnerIsTargetTile", "get_OwnerTileIsTarget"}, lus

    # Les quatre premiers rangs du classement par levier (#337 les cible nommement).
    porte = {r[1] for r in trig if r[5] in ("PORTE", "PORTE_ALIAS_FACADE", "PORTE_HORS_FACADE")}
    assert {"get_OwnerIsCaster", "get_OwnerIsTarget", "get_OwnerIsActor",
            "TriggeringAbilityIs"} <= porte
    # L'AUTRE PORTE du mouvement ci-dessus : sorti de `lus`, le noeud doit etre atteste PORTE --
    # sans cette ligne, faire DISPARAITRE sa ligne de la table suffirait a faire taire le rouge.
    assert "ActorHasTriggeredAbility" in porte, (
        "ActorHasTriggeredAbility n'est plus NON_PORTE mais n'est pas atteste PORTE non plus : "
        "sa ligne a-t-elle ete SUPPRIMEE de `docs/rl/dsl-port-attestations.tsv` ?")
    # #962 -- MEME cran pour la seconde sortie de `lus`. Sans lui, retirer une ligne du TSV
    # suffirait a faire taire le rouge sans rien avoir porte.
    assert "IsFirstHitGroupInAttack" in porte, (
        "IsFirstHitGroupInAttack est sortie de `lus` mais n'est pas PORTEE : sa ligne a-t-elle "
        "ete retiree de `docs/rl/dsl-port-attestations.tsv` sans que rien ne la porte ?")
    # #10028 -- LES TROIS ATTESTATIONS `PORTE_HORS_FACADE` DU ROUGE DE `master`, nommees ICI.
    # Elles sont arrivees par la MEME porte que `IsMoving` ci-dessus : une tranche a CITE le
    # symbole `DSLTriggers$$<nom>` dans `engine/**`, ce qui fait basculer l'heuristique de
    # `NON_PORTE` (aucune citation) vers `CITE_A_QUALIFIER` -- et l'heuristique ne peut PAS les
    # attribuer, le porteur de chaque citation ne portant pas le nom de la primitive (mesure :
    # `owned = False` sur les 6 sites). Les trois ports SONT LUS, ce sont des predicats COLLAPSES.
    # PROVENANCE MESUREE (`git log -S` par fichier) -- TROIS PR INDEPENDANTES, donc aucune des
    # trois n'a vu le rouge qu'elle creusait, et le fichier ne rougit qu'a leur SOMME :
    #   `IsInTeam`               `8ff8c672` (#10004, PR #1104)
    #                            -> `power_up_spawn.py::_ActeurDansLaTeam`
    #   `IsPartialAttackAbility` `78a604de` (#419-r1-tr9-r4-r1-r2-r1a, PR #1112)
    #                            -> `static_battle_rules.py::ability_is_partial_attack`
    #   `IsSpawnTile`            `94f84dab` (PR #1123 ; le port lui-meme date de #368-r2)
    #                            -> `status.py::tile_status_effect_is_active`
    # ⚠ CE CRAN N'EST PAS REDONDANT avec l'assertion `a_qualifier` du haut. Retirer une des trois
    # lignes du TSV la ferait bien rougir, mais un futur `NON_PORTE` ecrit A LA PLACE la ferait
    # taire en SILENCE -- alors que ces trois primitives ONT un mirror LU au decompile. Le cran
    # exige donc le camp PORTE, pas seulement l'absence de `CITE_A_QUALIFIER`.
    assert {"IsInTeam", "IsPartialAttackAbility", "IsSpawnTile"} <= porte, (
        "attestation(s) #10028 perdue(s) ou degradee(s) en NON_PORTE : %s -- les trois ports sont "
        "LUS (cf. `docs/rl/case-10028-quatre-attestations-rouges.md`), ne pas les rabattre sur "
        "un aveu d'ignorance"
        % sorted({"IsInTeam", "IsPartialAttackAbility", "IsSpawnTile"} - porte))
