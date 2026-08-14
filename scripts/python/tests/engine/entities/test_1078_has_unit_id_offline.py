"""#1078 -- `has_unit_id` : le foyer partage compare l'id de CONFIG, plus la `VisualId`.

CE QUE CE FICHIER GARDE, et pourquoi il est OFFLINE. La MESURE vit dans
`tests/engine/runner/test_1078_hail_of_living_ammunition_live.py` (le natif rend +0 la ou le port
rendait +2 pour un voisin `tyranNpc3TermagantKronos`). Ici on fige les DEUX crans que cette mesure
a imposes au foyer partage `engine/entities/selectors/units.py`, et le RAYON DE SOUFFLE mesure --
c'est-a-dire ce qui, chez les autres consommateurs du noeud, ne doit PAS avoir bouge.

    `IdunBattle.Entities.UnitExtensions$$HasUnitId(unit, id, state)`
        = `GetUnitIdWithoutRarity(GetUnitId(GetUnit(unit))) == id`
    `IdunBattle.Entities.UnitExtensions$$GetUnitId` lit le champ **+0x10** du composant d'identite
    (l'id de CONFIG) ; la `VisualId` vit a **+0x20**, et c'est la SEULE des deux qu'un canal live
    publie (`decisionView.units[].visualId` <- `UnitComponent.VisualId`, `frida/hooks/game/
    match-state.ts`).
"""
from __future__ import annotations

import gameconfig as GC
from engine.entities.selectors.units import UnitsWithIds, has_unit_id

#: Ce fichier ne monte AUCUN runner et ne lit ni le binaire ni `data/symbols/**` : il lit le
#: gameconfig (via `engine/entities/selectors/units.py`) et le port du noeud.
DECLENCHEUR = {
    "chemins": (),
    "build": False,
    "toujours": True,
    "raison": (
        "Fige les deux crans imposes au foyer partage `has_unit_id` par la mesure live #1078 "
        "(l'id compare est celui de CONFIG ; une unite ne satisfait qu'UN volet de l'union) et le "
        "rayon de souffle mesure sur les autres consommateurs du noeud. Entierement offline : "
        "gameconfig + port, aucun runner."
    ),
}

HAIL_IDS = ["tyranNpc3Termagant", "tyranSmnTermagant", "GuildBoss1Npc1TyranTermagantLeviathan",
            "GuildBoss1Npc2TyranTermagantKronos", "GuildBoss1Npc3TyranTermagantGorgon"]
SWARM_IDS = ["tyranNpc1Hormagaunt", "tyranNpc2RipperSwarm",
             "tyranSmnHormagaunt", "tyranSmnRipperSwarm"]
SUPREME_IDS = ["astraSmnGuardsman", "astraNpc1Guardsman"]


def _presented(uid: str) -> str:
    """L'identite OBSERVABLE d'une unite du gameconfig = son `visualId`, ou son id de config a
    defaut. C'est ce que `decisionView` rend, et donc ce que le port voit."""
    return (GC.unit(uid) or {}).get("visualId") or uid


def _identites_observables() -> list:
    """TOUTES les identites qu'un `decisionView` peut rendre, derivees du gameconfig.

    ⚠ Le non-vide s'assertionne par un INVARIANT, pas par un seuil : le recensement doit
    CONTENIR les identites des unites que les consommateurs balayes listent -- sinon la boucle
    qui suit ne visite rien et rend un VERT vide (le vice que `probe_270r1` a du corriger)."""
    ids = sorted({_presented(u) for kind in GC.all_unit_ids().values() for u in kind})
    temoins = {_presented(u) for u in SWARM_IDS + SUPREME_IDS + ["tyranNpc3Termagant",
                                                                "tyranNpc3TermagantKronos"]}
    manquants = temoins - set(ids)
    assert not manquants, \
        f"le recensement des identites observables ne voit pas ses propres temoins : {manquants}"
    return ids


# --- Cran 1 : l'id compare est celui de CONFIG -----------------------------------------------

def test_le_kronos_ne_compte_pas_malgre_son_visualid_liste():
    """LA MESURE LIVE, figee offline. `tyranNpc3TermagantKronos` presente
    `GuildBoss1Npc2TyranTermagantKronos`, qui EST dans `unitIds` ; son id de CONFIG ne l'est pas.
    Le natif rend +0 -- donc le port doit refuser ce voisin."""
    v = _presented("tyranNpc3TermagantKronos")
    assert v == "GuildBoss1Npc2TyranTermagantKronos", \
        "le `visualId` du Kronos a change -> ce test ne mesure plus le meme ecart"
    assert v in HAIL_IDS, \
        "le `visualId` du Kronos n'est plus dans `unitIds` -> les deux lectures ne divergent plus"
    assert not any(has_unit_id({"visualId": v}, i) for i in HAIL_IDS), \
        ("le port compte le Kronos : il compare la `VisualId` la ou le natif compare l'id de "
         "CONFIG (`UnitExtensions$$GetUnitId`, champ +0x10)")


def test_le_termagant_et_son_summon_comptent_tous_deux():
    """Le CONTROLE POSITIF -- sans lui, un `has_unit_id` qui rendrait toujours FAUX passerait le
    test ci-dessus. Le npc `tyranNpc3Termagant` et le summon `tyranSmnTermagant` presentent tous
    deux `tyranNpc3Termagant`, et les DEUX ids de config sont dans la liste."""
    assert _presented("tyranNpc3Termagant") == "tyranNpc3Termagant"
    assert _presented("tyranSmnTermagant") == "tyranNpc3Termagant"
    assert has_unit_id({"visualId": "tyranNpc3Termagant"}, "tyranNpc3Termagant")
    assert has_unit_id({"visualId": "tyranNpc3Termagant"}, "tyranSmnTermagant")


def test_un_id_inconnu_du_gameconfig_retombe_sur_la_comparaison_historique():
    """`GuildBoss1Npc1TyranTermagantLeviathan` est cite par la constante mais n'est une unite
    d'AUCUNE section de `units.*` : le gameconfig ne peut donc rien resoudre. Le repli garde la
    comparaison directe -- la reparation n'a RETIRE aucun comportement existant."""
    orphelin = "GuildBoss1Npc1TyranTermagantLeviathan"
    assert GC.unit(orphelin) is None, \
        f"{orphelin} est entre dans le gameconfig -> ce n'est plus le cas de repli"
    assert has_unit_id({"visualId": orphelin}, orphelin)
    assert not has_unit_id({"visualId": orphelin}, "tyranNpc3Termagant")


def test_sans_visualid_le_noeud_ne_retient_rien():
    """Degradation RESTRICTIVE : pas d'identite lue => aucune contribution, jamais un match."""
    assert not has_unit_id({}, "tyranNpc3Termagant")
    assert not has_unit_id({"visualId": None}, "tyranNpc3Termagant")


# --- Cran 2 : une unite ne satisfait qu'UN SEUL volet de l'union -------------------------------

class _Src:
    """Source minimale : rend telle quelle la liste d'unites qu'on lui donne."""
    def __init__(self, units):
        self.units = units

    def evaluate(self, ctx):
        return self.units


def test_l_union_ne_compte_pas_deux_fois_la_meme_unite():
    """LE SECOND CRAN, trouve par le RE-JEU live et pas par le recensement : la resolution rend
    VRAI pour PLUSIEURS ids (un Termagant npc peut etre `tyranNpc3Termagant` **ou**
    `tyranSmnTermagant`), donc l'union naive le comptait DEUX fois -- le port rendait +4 la ou le
    natif rend +2."""
    u = {"id": 1, "visualId": "tyranNpc3Termagant"}
    got = UnitsWithIds(_Src([u]), HAIL_IDS).select(None)
    assert len(got) == 1, f"l'union compte {len(got)} fois la meme unite (attendu 1)"


def test_un_id_repete_garde_son_doublon_natif():
    """Le natif n'insere AUCUN `Unique` : `ids = [A, A]` emet deux fois. Le cran ci-dessus ne doit
    pas manger CE doublon-la, qui vient de la liste et non de la resolution."""
    u = {"id": 1, "visualId": "tyranNpc3Termagant"}
    got = UnitsWithIds(_Src([u]), ["tyranNpc3Termagant", "tyranNpc3Termagant"]).select(None)
    assert len(got) == 2, f"le doublon natif d'un `ids` repete a disparu ({len(got)})"


# --- Rayon de souffle : ce qui ne doit PAS avoir bouge -----------------------------------------

def test_les_autres_consommateurs_du_noeud_ne_changent_pas_de_verdict():
    """RAYON DE SOUFFLE MESURE. Sur les listes de `HungeringSwarm` (#1018) et de
    `SupremeCommander` (#119), la resolution rend EXACTEMENT ce que rendait la comparaison
    directe, pour TOUTE identite observable du gameconfig. Les deux tests live correspondants
    ne peuvent donc pas regresser par cette voie."""
    identites = _identites_observables()
    for nom, ids in (("HungeringSwarm", SWARM_IDS), ("SupremeCommander", SUPREME_IDS)):
        for v in identites:
            ancien = v in ids
            nouveau = any(has_unit_id({"visualId": v}, i) for i in ids)
            assert ancien == nouveau, \
                (f"[{nom}] la reparation change le verdict pour l'identite {v!r} : "
                 f"ancien={ancien} nouveau={nouveau}")


def test_le_changement_est_borne_aux_deux_variantes_termagant():
    """Le pendant du test precedent : la reparation DOIT changer quelque chose, et exactement ce
    qui a ete mesure. Un test qui n'assertionne que l'invariance passerait sur un no-op."""
    identites = _identites_observables()
    change = {v for v in identites
              if (v in HAIL_IDS) != any(has_unit_id({"visualId": v}, i) for i in HAIL_IDS)}
    assert change == {"GuildBoss1Npc2TyranTermagantKronos",
                      "GuildBoss1Npc3TyranTermagantGorgon"}, \
        f"le rayon de souffle a bouge : {sorted(change)}"
