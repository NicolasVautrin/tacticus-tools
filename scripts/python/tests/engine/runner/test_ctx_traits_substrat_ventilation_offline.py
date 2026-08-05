"""#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1 -- GARDE de la VENTILATION du patron `ctx.traits` BRUT.

CE QUE CE FICHIER VERROUILLE. `#462-...-r3` (PR #646) a ferme le defaut sur `barbed_ovipositor` et
l'a annonce comme un PATRON. Cette tranche l'a INVENTORIE (AST) puis VENTILE. Le resultat n'est pas
<< N sites a convertir >> : c'est que **presque tout est INERTE**, et pour une raison DERIVABLE --
d'ou une garde en deux etages.

  1. La LOI qui rend la ventilation valide. Deux premisses, verifiees executablement :
       P1  `StatsComponent` absent <=> `UnitComponent.alive == False` AU CHARGEMENT ;
       P2  aucune voie du port ne rend VIVANTE une entite chargee morte.
     Si l'une tombe, les 39 verdicts INERTE-VIVANT de la table sont VOIDS et le gisement doit etre
     re-instruit. C'est le seul endroit du depot ou cette dependance est ecrite ET exercee.

  2. Les DEUX seuls sites que la loi rend ATTEIGNABLES, et leur conversion. Sur ces deux-la,
     remplacer NAIVEMENT la lecture brute par le foyer AURAIT ETE UNE REGRESSION : le natif
     (`ADecoysAndMisdirectionAbility$$GetValidDeadDecoys`, relu VERBATIM) porte un conjoint
     `IsKilledThisTurn(it)` que le port COLLAPSE en co-localisation -- et le `set()` de la lecture
     brute excluait le cadavre-au-chargement PAR ACCIDENT, dans le bon sens. La conversion livree
     NOMME cette exclusion (`sc is None`) avant de reparer le substrat. Les tests de comportement
     ci-dessous figent les DEUX faces : refus du cadavre-au-chargement, acceptation du mort du run.

POURQUOI UN TEST ET PAS SEULEMENT LE PROBE : un probe MESURE, il ne GARDE pas -- aucune passe ne le
joue. Le montage vit dans le probe (aucun fork : ce fichier l'IMPORTE).

OFFLINE, et c'est un choix : tout est predicat pur, aucun runner ni tirage.

ASCII only (cp1252).
"""
from __future__ import annotations

import pytest

import probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_substrat_traits as P


# ================================================================================================
# ETAGE 1 -- l'INVENTAIRE ne derive pas sous la table
# ================================================================================================
def test_la_table_ventile_exactement_l_inventaire():
    """CLIQUET. Un site neuf (ou un site disparu) rend la ventilation de cette tranche MUETTE sur
    lui : elle ne dit rien de son sujet. On exige la coincidence exacte -- pas un seuil, un
    INVARIANT (une garde en seuil cesse de mordre des qu'un contributeur ne remonte pas le seuil)."""
    trouves = {P._cle(s) for s in P.sites()}
    table = set(P.VENTILATION)
    manquantes = sorted(trouves - table)
    orphelines = sorted(table - trouves)
    assert not manquantes, (
        "%d lecture(s)/ecriture(s) de `traits` que la table ne ventile PAS : %r. Ventiler le site "
        "(son sujet peut-il etre une entite chargee MORTE ?) fait partie du changement qui l'a "
        "cree -- cf. docs/rl/case-462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-substrat-traits-inventaire.md"
        % (len(manquantes), manquantes))
    assert not orphelines, (
        "%d entree(s) de table sans site : %r. Le site a ete deplace ou supprime ; mettre la table "
        "a jour, sans quoi elle decrit un etat perime." % (len(orphelines), orphelines))


def test_aucun_verdict_ATTEIGNABLE_ne_reste_non_traite():
    """La table ne doit plus porter d'`ATTEIGNABLE` : les deux qu'elle portait sont CONVERTIS.
    Si quelqu'un en ajoute un, il doit soit le convertir, soit dire pourquoi il ne le fait pas --
    pas le laisser dormir dans une table qui se lit comme un inventaire clos."""
    restants = sorted(k for k, v in P.VENTILATION.items() if v[0] in P.VERDICTS_ATTEIGNABLES)
    assert not restants, (
        "site(s) ATTEIGNABLE(s) non traite(s) : %r. Un ATTEIGNABLE est un gate potentiellement "
        "AVEUGLE sur un cadavre -- le convertir, ou requalifier son verdict avec son motif."
        % (restants,))


# ================================================================================================
# ETAGE 2 -- la LOI, exercee (c'est elle qui rend 39 verdicts INERTE-VIVANT legitimes)
# ================================================================================================
def test_premisse_P1_ctx_absent_equivaut_a_mort_au_chargement():
    """P1 -- `snapshot.load_state` pose un `StatsComponent` sur la VIVANTE et sur elle seule.

    Cote capteur, c'est la MEME methode native `IsAlive` qui filtre `combatSnapshot.units`
    (`rpc-snapshot.ts`, bloc `allUnits`) et qui publie `decisionView.units[].alive`
    (`projection.ts`) -- d'ou l'equivalence. Ici on verifie la CONSEQUENCE cote port."""
    from engine.runner.components import StatsComponent, UnitComponent
    st = P._etat_charge()
    vivante, morte = st.get_entity(1), st.get_entity(2)
    assert vivante is not None and morte is not None, \
        "`load_state` n'a pas cree les deux entites de `decisionView` -- montage a reparer."
    assert morte.get_component(UnitComponent).alive is False
    assert vivante.get_component(StatsComponent) is not None, \
        "l'unite VIVANTE n'a pas de `StatsComponent` : le montage ne reproduit plus un chargement."
    assert morte.get_component(StatsComponent) is None, (
        "l'unite MORTE a desormais un `StatsComponent`. C'est peut-etre une BONNE nouvelle (le "
        "substrat cadavre disparaitrait), mais elle INVALIDE la ventilation de cette tranche : "
        "les verdicts INERTE-* reposent tous sur << ctx absent == cadavre >>. Re-instruire.")


def test_premisse_P2_aucun_cadavre_au_chargement_ne_revient_a_la_vie():
    """P2 -- la seule voie de RESURRECTION du port (`EnvAmbushResurrectAbility` ->
    `ResurrectUnitOperation`) exige `UnitComponent.turn_defeated`, ecrit UNIQUEMENT par
    `AmbushSummonAbility` a la mort, PENDANT le run. Un cadavre-au-chargement ne le porte pas.

    C'est cette premisse qui autorise a dire << sujet gate VIVANT => INERTE >> : sans elle, un
    cadavre pourrait redevenir vivant sans ctx et TOUS les sites redeviendraient atteignables."""
    from engine.runner.operations.triggers.genestealer import _eligible_for_resurrect
    # NB : le montage vit dans le probe, `--step loi`. On le rejoue via ses briques publiques.
    import gameconfig as GC
    from engine.runner.state import State, Entity
    from engine.runner.components import (UnitComponent, OwnerComponent, StatsComponent,
                                          UnitFlagsComponent)
    from engine.entities.unit_context import UnitContext

    def _mk(horodate: bool):
        st = State()
        e = Entity(7)
        uc = UnitComponent(visual_id="genesPrimus", alive=False)
        if horodate:
            uc.turn_defeated = 0
        e.add_component(uc)
        e.add_component(OwnerComponent(team=1, player=3))
        e.add_component(UnitFlagsComponent())
        ctx = UnitContext.__new__(UnitContext)
        ctx.visual_id = "genesPrimus"
        ctx.traits = list((GC.unit("genesPrimus") or {}).get("traits") or ())
        ctx.traits_measured = False
        e.add_component(StatsComponent(ctx))
        st.entities[7] = e
        st.turn_counts = {3: 1}
        return st

    assert _eligible_for_resurrect(_mk(True), 3) == [7], (
        "un porteur Ambush mort PENDANT le run n'est plus eligible : le montage ne discrimine "
        "plus rien, la premisse n'est pas mesuree.")
    assert _eligible_for_resurrect(_mk(False), 3) == [], (
        "un cadavre AU CHARGEMENT (sans `turn_defeated`) est devenu eligible a la resurrection. "
        "La voie 2 est ROUVERTE : tous les verdicts INERTE-VIVANT de la table sont a re-instruire, "
        "puisqu'une entite sans ctx pourrait desormais etre VIVANTE.")


def test_le_substrat_diverge_bien_sur_un_cadavre():
    """LA MESURE qui justifie tout le reste, figee : sur une entite SANS `StatsComponent`, la
    lecture BRUTE s'effondre a `[]` alors que le foyer rend le kit (repli #226)."""
    from engine.entities.traits.unit_trait import entity_trait_names
    from engine.runner.components import StatsComponent, UnitComponent
    import gameconfig as GC
    for vis in ("genesSmnDecoy", "necroWarden"):
        kit = set((GC.unit(vis) or {}).get("traits") or ())
        st = P.etat_crush(vis, avec_stats=False)
        e = st.get_entity(2)
        sc = e.get_component(StatsComponent)
        uc = e.get_component(UnitComponent)
        assert sc is None, "le montage CADAVRE ne reproduit plus l'absence de `StatsComponent`."
        foyer = set(entity_trait_names(None, uc.visual_id))
        assert foyer >= kit, (
            "le substrat FOYER (%r) ne couvre plus le kit gameconfig (%r) de %r."
            % (sorted(foyer), sorted(kit), vis))


# ================================================================================================
# ETAGE 3 -- les DEUX sites convertis : PROVENANCE (AST) puis COMPORTEMENT
# ================================================================================================
@pytest.mark.parametrize("cle", sorted(P.CONVERTIS))
def test_le_site_converti_passe_par_le_foyer_et_porte_son_gate(cle):
    """PROVENANCE, par AST et pas par grep (un appel dans un commentaire ne compte pas).

    Contre-epreuve mesuree en #643 puis en #646 : un mutant qui remplace le foyer par une recopie
    LOCALE strictement equivalente ne fait rougir AUCUN critere de VALEUR -- il est
    comportementalement indistinguable AUJOURD'HUI, et le risque qu'il porte est la DIVERGENCE
    FUTURE. D'ou une assertion sur le SOURCE.

    Le gate `sc is None` est verifie dans le MEME test parce que les deux ne valent que
    ENSEMBLE : reparer le substrat SANS le gate fait entrer un mort que le natif refuse."""
    etat = {c: (b, a, g) for c, b, a, g, _m in P.etat_conversion()}
    brut_absent, appelle_foyer, gate = etat[cle]
    assert brut_absent, (
        "`%s::%s` porte de nouveau une lecture BRUTE de `traits` : la conversion est defaite."
        % cle)
    assert appelle_foyer, (
        "`%s::%s` n'APPELLE plus `entity_trait_names` : le substrat est recompose localement. "
        "Meme a l'identique, c'est la recopie que ce residu ferme." % cle)
    assert gate, (
        "`%s::%s` a perdu son gate `sc is None`. C'est lui qui NOMME le collapse du conjoint natif "
        "`IsKilledThisTurn` : sans lui, le foyer rend ses traits a un cadavre-au-chargement et le "
        "port selectionne un mort que le natif REFUSE." % cle)


@pytest.mark.parametrize("regime,attendu", [(True, [2]), (False, [])],
                         ids=["mort-PENDANT-le-run", "cadavre-AU-CHARGEMENT"])
def test_valid_dead_decoys_refuse_le_cadavre_au_chargement(regime, attendu):
    """`ADecoysAndMisdirectionAbility$$GetValidDeadDecoys` -- conjoint `IsKilledThisTurn(sel@0x68)`.

    Les deux regimes ont le MEME decoy (memes traits natifs) et la MEME co-localisation : seul
    change << etait-il deja mort a la capture >>. Le natif repond par `IsKilledThisTurn`, le port
    par la presence du `StatsComponent`. Ce test fige que le verdict SUIT le natif."""
    from engine.runner.operations.triggers.genestealer import _valid_dead_decoys
    st = P.etat_crush("genesSmnDecoy", avec_stats=regime)
    got = _valid_dead_decoys(st, owner_id=1, stepper_id=1)
    assert got == attendu, (
        "regime %s : `_valid_dead_decoys` rend %r, attendu %r. Le conjoint `IsKilledThisTurn` est "
        "COLLAPSE cote port ; son seul discriminant est le `StatsComponent`."
        % ("mort du run" if regime else "cadavre au chargement", got, attendu))


@pytest.mark.parametrize("cle", sorted(P.DISPARUS))
def test_le_site_disparu_a_bien_transmis_sa_garantie(cle):
    """Le pendant du precedent pour un site SUPPRIME, et non converti.

    `move_death.py::post_unit_kill_triggers_for_move` a disparu en
    #462-r4b-r1-r1-r1-r1-c-r3-r1-r4 : `On(0x35 = PostUnitKill)` est publie par le foyer
    `damage.py::_kill_unit_operation`, a son rang natif, donc plus rien ne re-identifie le crushe
    par co-localisation. Une garantie qui disparait avec son site est une garantie PERDUE -- sauf
    si un porteur la reprend. Ce test verifie les trois cotes a la fois :

      * le site n'est pas REVENU (s'il revenait, le chemin MOVE emettrait l'event DEUX fois) ;
      * le porteur nomme existe ;
      * il porte le gate qui tient la garantie (`uc.alive`).

    La garantie elle-meme (COMPORTEMENT) est exercee par le test suivant, sur le chemin reel."""
    etat = {c: (a, p, g) for c, a, p, g in P.etat_disparus()}
    absent, porteur, gate = etat[cle]
    _tranche, fich, fn = P.DISPARUS[cle]
    assert absent, (
        "`%s::%s` est REVENU. Il publiait `On(0x35 = PostUnitKill)` depuis `after_move_triggers` ; "
        "le foyer `_kill_unit_operation` le publie desormais lui-meme -> le chemin MOVE emettrait "
        "l'event DEUX FOIS. Si la resurrection est voulue, retirer l'emission du foyer d'abord."
        % cle)
    assert porteur, (
        "le porteur annonce `%s::%s` n'existe plus : la garantie du site supprime n'a PLUS de "
        "titulaire." % (fich, fn))
    assert gate, (
        "`%s::%s` a perdu son gate `uc.alive`. C'est LUI qui empeche un cadavre-au-chargement "
        "d'etre << crushe >> et donc d'entrer dans la sequence de mort : sans lui, le port emet "
        "les cinq events pour un kill QUI N'A PAS EU LIEU." % (fich, fn))


@pytest.mark.parametrize("vivant,avec_stats,attendu", [
    (True, True, 1),        # le regime NOMINAL : un Steppable vivant sous le mover
    (False, False, 0),      # CADAVRE-AU-CHARGEMENT : ecarte par le SUBSTRAT (pas de ctx)
    (False, True, 0),       # CADAVRE DU RUN       : ecarte par le GATE `uc.alive`, et LUI SEUL
], ids=["steppable-VIVANT", "cadavre-AU-CHARGEMENT", "cadavre-DU-RUN"])
def test_le_crush_refuse_le_cadavre_au_chargement(vivant, avec_stats, attendu, monkeypatch):
    """LA GARANTIE, exercee sur le CHEMIN REEL (`_kill_steppable_units`) plutot que sur la
    re-identification par co-localisation qui la portait avant #462-r4b-r1-r1-r1-r1-c-r3-r1-r4.

    Meme decoy, meme co-localisation, meme tuile : seul change son ETAT a l'entree du move. Un mort
    peut parfaitement etre sous le mover (un mort ne bloque pas l'occupation) et le natif ne le tue
    PAS -- `KillSteppableUnits` ne boucle que sur les VIVANTS.

    ⚠ LE 3e REGIME EXISTE PARCE QUE LES DEUX PREMIERS NE DISCRIMINENT PAS LE GATE QU'ILS PRETENDENT
    GARDER. Mesure (matrice de mutants de la tranche) : retirer `not uc.alive` de
    `_kill_steppable_units` laisse les deux premiers bras VERTS -- le cadavre-au-chargement est
    ecarte plus bas, par le substrat de traits VIDE (`sc is None` -> `has_trait([], Steppable)`
    faux). DEUX gates protegent, et le test n'en isolait aucun. Le cadavre DU RUN, lui, a son ctx
    et ses traits `Steppable` : seul `uc.alive` peut le refuser. C'est aussi le regime REEL du
    2e pas d'un chemin -- un steppable crushe au pas N est encore sur sa tuile au pas N+1.

    `post_unit_kill_triggers` est SUBSTITUE dans le PACKAGE `triggers` (c'est de la que
    `_kill_unit_operation` le resout, par import tardif) : on mesure la SELECTION, pas ce que les
    triggers aval produisent -- ils rendraient `[]` dans les trois regimes et le test ne
    discriminerait rien (accord en regime degenere)."""
    from engine.runner.operations import triggers as TRG
    from engine.runner.operations.movement import _kill_steppable_units
    vus = []

    def _faux(state, killed_id, killer_id=None):
        vus.append((killer_id, killed_id))
        return [{"post_unit_kill": killed_id}]

    monkeypatch.setattr(TRG, "post_unit_kill_triggers", _faux)
    st = P.etat_crush("genesSmnDecoy", avec_stats=avec_stats, vivant=vivant)
    tues = _kill_steppable_units(st, (3, 3), mover_id=1)
    regime = ("steppable vivant" if vivant else
              ("cadavre au chargement" if not avec_stats else "cadavre DU RUN"))
    assert len(tues) == attendu and len(vus) == attendu, (
        "regime %s : %d crushe(s) / %d `On(PostUnitKill)`, attendu %d. Un event de mort emis pour "
        "un MORT est un kill QUI N'A PAS EU LIEU (et, sur le cadavre DU RUN, la preuve que le gate "
        "`uc.alive` de `_kill_steppable_units` a saute) ; l'absence d'event pour un steppable "
        "VIVANT sous le mover est un crush MANQUE."
        % (regime, len(tues), len(vus), attendu))
    if attendu:
        assert vus == [(1, 2)], (
            "`On(PostUnitKill)` doit porter {actor = le TUEUR (le mover), target = le crushe} -- "
            "c'est le meme `AbilityEntities` que les quatre autres events de mort (`local_298 = "
            "killer` ; `+0x10 = killed`). Vu : %r" % (vus,))
