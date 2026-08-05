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


@pytest.mark.parametrize("regime,attendu", [(True, 1), (False, 0)],
                         ids=["mort-PENDANT-le-run", "cadavre-AU-CHARGEMENT"])
def test_post_unit_kill_triggers_for_move_refuse_le_cadavre_au_chargement(regime, attendu,
                                                                         monkeypatch):
    """Pendant de `On(0x35 = PostUnitKill)` : le port re-identifie le crushe par CO-LOCALISATION.
    Un cadavre-au-chargement peut etre co-localise avec le mover (un mort ne bloque PAS
    l'occupation, donc le mover peut s'arreter sur sa tuile) -- et le natif ne l'a pas tue.

    `post_unit_kill_triggers` est SUBSTITUE : on mesure la SELECTION, pas ce que les triggers
    aval produisent (ils rendraient `[]` dans les deux regimes, et le test ne discriminerait rien
    -- l'accord en regime degenere ne prouve rien)."""
    from engine.runner.operations.triggers.dispatch import move_death as MD
    appels = []

    def _faux(state, mover_id, uid):
        appels.append(uid)
        return [{"crushe": uid}]

    monkeypatch.setattr(MD, "post_unit_kill_triggers", _faux)
    st = P.etat_crush("genesSmnDecoy", avec_stats=regime)
    st.board = object()                       # le site ne teste que `board is None`
    got = MD.post_unit_kill_triggers_for_move(st, mover_id=1)
    assert len(got) == attendu and len(appels) == attendu, (
        "regime %s : %d event(s) / %d appel(s), attendu %d. Un `On(PostUnitKill)` emis pour un "
        "cadavre-au-chargement est un kill QUI N'A PAS EU LIEU."
        % ("mort du run" if regime else "cadavre au chargement", len(got), len(appels), attendu))
